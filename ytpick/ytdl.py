"""Alles rund um yt-dlp: Suche, Download-Optionen, Prüfung heruntergeladener Dateien."""

import re
import subprocess
import sys
from pathlib import Path

from .compat import yt_dlp
from .constants import FROZEN, NAME_PRESETS, POOL
from .i18n import _
from .util import QuietLogger, clean_text


def parse_query(query):
    m = re.match(r"^(@\S+|https?://(?:\S*youtube\.com|youtu\.be)/\S+)\s*(.*)$", query.strip())
    if not m:
        q = query.strip()
        return {"kind": "search", "key": "s:" + q.lower(), "url": f"ytsearch{POOL}:{q}",
                "term": "", "label": _("Suche „{q}“").format(q=q)}
    target, term = m.group(1), m.group(2).strip()
    if re.search(r"youtu\.be/|/watch\?|/shorts/|/live/|/embed/", target) and "list=" not in target:
        return {"kind": "video", "key": f"v:{target}", "url": target, "term": "",
                "label": _("Video {t}").format(t=target)}
    if target.startswith("@"):
        url = f"https://www.youtube.com/{target}/videos"
    else:
        url = target.rstrip("/")
        if (not re.search(r"/(videos|streams|shorts|playlists|search|featured)(/|\?|$)", url)
                and "/watch" not in url and "/playlist" not in url):
            url += "/videos"
    if "/playlist" in url and "list=" in url:
        return {"kind": "playlist", "key": f"p:{url}|{term.lower()}", "url": url, "term": term,
                "label": _("Playlist {t}").format(t=target) + (_(" · Filter „{f}“").format(f=term) if term else "")}
    label = _("Kanal {t}").format(t=target) + (_(" · Filter „{f}“").format(f=term) if term else "")
    return {"kind": "channel", "key": f"c:{url}|{term.lower()}", "url": url,
            "term": term, "label": label}


def normalize(e, info):
    info = info or {}
    return {
        "id": e["id"],
        "title": clean_text(e.get("title")) or "?",
        "channel": clean_text(e.get("channel") or e.get("uploader")
                              or info.get("channel") or info.get("uploader")) or "?",
        "channel_id": e.get("channel_id") or e.get("uploader_id")
                      or info.get("channel_id") or "",
        "duration": e.get("duration"),
        "views": e.get("view_count"),
        "date": e.get("upload_date") or None,
        "verified": e.get("channel_is_verified", info.get("channel_is_verified")),
    }


class Cancelled(Exception):
    pass


def installed_ytdlp_version():
    try:
        from importlib.metadata import version
        return version("yt-dlp")
    except Exception:
        return "?"


def upgrade_ytdlp():
    if FROZEN:
        raise RuntimeError(_("In der .exe ist yt-dlp fest eingebaut. Lade die neueste ytpick-Version von GitHub."))
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp[default]"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=flags)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        raise RuntimeError(tail[-1] if tail else f"pip exit {proc.returncode}")
    return installed_ytdlp_version()


def fetch_flat(url, limit=None, ydl_opts=None):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "logger": QuietLogger()}
    if ydl_opts and "cookiesfrombrowser" in ydl_opts:
        opts["cookiesfrombrowser"] = ydl_opts["cookiesfrombrowser"]
    if limit:
        opts["playlistend"] = limit
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or ([info] if info.get("id") else [])
    return info, [e for e in entries if e and e.get("id")]


def name_template(fmt, rank=None):
    template = NAME_PRESETS.get(fmt.get("name", "title"), NAME_PRESETS["title"])
    return template.replace("{rank}", f"{int(rank or 0):02d}")


def download_opts(base, outdir, mode, fmt, hook, rank=None):
    opts = dict(base)
    folder = "%(channel)s/" if fmt.get("channel_folder") else ""
    start, end = fmt.get("cut_start"), fmt.get("cut_end")
    cut = start is not None or end is not None
    suffix = " clip" if cut else ""
    opts.update({
        "outtmpl": str(outdir / (folder + name_template(fmt, rank) + f"{suffix}.%(ext)s")),
        "noplaylist": True,
        "windowsfilenames": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [hook],
    })
    if cut:
        opts["download_ranges"] = yt_dlp.utils.download_range_func(
            [], [(start or 0, end if end is not None else float("inf"))])
        opts["force_keyframes_at_cuts"] = True
    audio = mode in ("audio", "mp3")
    pp = []
    if audio:
        opts["format"] = "bestaudio/best"
        if mode == "mp3":
            pp.append({"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "0"})
        else:
            pp.append({"key": "FFmpegExtractAudio", "preferredcodec": "best"})
    else:
        h = int(fmt.get("height") or 0)
        opts["format"] = f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b" if h else "bv*+ba/b"
        if mode == "mp4":
            opts.update(format_sort=["res", "ext:mp4:m4a"], merge_output_format="mp4")
        else:
            opts["merge_output_format"] = "mkv"
        if fmt.get("subs"):
            langs = [x.strip() for x in str(fmt.get("sub_langs", "")).split(",") if x.strip()]
            if langs:
                opts["writesubtitles"] = True
                opts["subtitleslangs"] = langs
    embed = bool(fmt.get("embed")) and mode != "audio"
    add_meta = mode == "mp3" or embed
    add_chapters = bool(fmt.get("chapters")) and not audio
    if add_meta or add_chapters:
        pp.append({"key": "FFmpegMetadata", "add_chapters": add_chapters, "add_metadata": add_meta})
    if not audio and opts.get("writesubtitles"):
        pp.append({"key": "FFmpegEmbedSubtitle"})
    if embed:
        opts["writethumbnail"] = True
        pp.insert(0, {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
        pp.append({"key": "EmbedThumbnail"})
    if pp:
        opts["postprocessors"] = pp
    return opts


def verify_download(info, vid, outdir):
    if not info:
        return False, _("keine Antwort von yt-dlp"), ""
    if info.get("id") != vid:
        return False, _("falsche Video-ID ({a} statt {b})").format(a=info.get("id"), b=vid), ""
    paths = [d.get("filepath") for d in info.get("requested_downloads") or [] if d.get("filepath")]
    if not paths and info.get("filepath"):
        paths = [info["filepath"]]
    for p in paths:
        f = Path(p)
        if f.is_file() and f.stat().st_size > 0 and f"[{vid}]" in f.name and outdir.resolve() in f.resolve().parents:
            return True, "", str(f)
    return False, _("fertige Datei nicht gefunden oder leer"), ""
