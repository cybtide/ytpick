import argparse
import locale
import os
import re
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp fehlt / yt-dlp is missing. pip install -U yt-dlp")

__version__ = "0.5.0"

NAME_PRESETS = {
    "title": "%(title).150B [%(id)s]",
    "channel": "%(channel)s - %(title).150B [%(id)s]",
    "rank": "{rank} - %(title).150B [%(id)s]",
}
BROWSERS = ["firefox", "chrome", "edge", "brave", "vivaldi", "opera", "safari"]
VIDEO_RE = re.compile(r"youtu\.be/|/watch\?|/shorts/|/live/|/embed/")
YOUTUBE_RE = re.compile(r"^(@\S+|https?://(?:\S*youtube\.com|youtu\.be)/\S+)\s*(.*)$")


def system_language():
    try:
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    except Exception:
        loc = os.environ.get("LANG", "").lower()
    return "de" if loc.startswith("de") else "en"


LANG = system_language()


def t(de, en):
    return de if LANG == "de" else en


def fmt_duration(sec):
    if not sec:
        return "live/?"
    sec = int(sec)
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_views(v):
    if v is None:
        return "?"
    for unit, div in ((t("Mrd", "B"), 1e9), (t("Mio", "M"), 1e6), (t("Tsd", "K"), 1e3)):
        if v >= div:
            return f"{v / div:.1f} {unit}"
    return str(v)


def parse_time(text):
    text = (text or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(text)
    total = 0.0
    for part in parts:
        total = total * 60 + float(part.replace(",", "."))
    if total < 0:
        raise ValueError(text)
    return total


def parse_cut(text):
    if not text:
        return None, None
    parts = re.split(r"\s*-\s*", text.strip(), maxsplit=1)
    if len(parts) != 2:
        raise ValueError(text)
    start, end = parse_time(parts[0]), parse_time(parts[1])
    if start is None and end is None:
        raise ValueError(text)
    if start is not None and end is not None and end <= start:
        raise ValueError(text)
    return start, end


def parse_query(query):
    query = query.strip()
    m = YOUTUBE_RE.match(query)
    if not m:
        if re.match(r"https?://", query):
            return {"kind": "video", "url": query, "term": ""}
        return {"kind": "search", "url": "", "term": query}
    target, term = m.group(1), m.group(2).strip()
    if VIDEO_RE.search(target):
        return {"kind": "video", "url": target, "term": ""}
    if target.startswith("@"):
        url = f"https://www.youtube.com/{target}/videos"
    else:
        url = target.rstrip("/")
        if (not re.search(r"/(videos|streams|shorts|playlists|search|featured)(/|\?|$)", url)
                and "/watch" not in url and "/playlist" not in url):
            url += "/videos"
    if "/playlist" in url and "list=" in url:
        return {"kind": "playlist", "url": url, "term": term}
    return {"kind": "channel", "url": url, "term": term}


def parse_selection(text, maximum):
    text = text.strip().lower()
    if text in ("all", "a", "alle"):
        return list(range(1, maximum + 1))
    picked = []
    for part in re.split(r"[,\s]+", text):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            picked.extend(range(min(lo, hi), max(lo, hi) + 1))
        elif part.isdigit():
            picked.append(int(part))
        else:
            raise ValueError(t("Ungültige Eingabe: {p}", "Invalid input: {p}").format(p=part))
    bad = [p for p in picked if not 1 <= p <= maximum]
    if bad:
        raise ValueError(t("Außerhalb des Bereichs 1-{m}: {b}", "Out of range 1-{m}: {b}").format(
            m=maximum, b=bad))
    return list(dict.fromkeys(picked))


def entry_url(e):
    return e.get("url") or f"https://www.youtube.com/watch?v={e['id']}"


def base_opts(args):
    opts = {}
    if args.cookies:
        opts["cookiesfrombrowser"] = (args.cookies,)
    if args.rate and args.rate > 0:
        opts["ratelimit"] = int(args.rate * 1048576)
    return opts


def fetch(spec, n, args):
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "skip_download": True}
    opts.update(base_opts(args))
    terms = [w for w in spec["term"].lower().split() if w]
    if spec["kind"] == "search":
        url = f"ytsearch{n}:{spec['term']}"
    else:
        url = spec["url"]
        opts["playlistend"] = max(n * 10, 300) if terms else n
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    out = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        title = e.get("title") or "?"
        if spec["kind"] != "search" and terms and not all(w in title.lower() for w in terms):
            continue
        out.append({
            "id": e["id"], "title": title, "url": entry_url(e),
            "channel": e.get("channel") or e.get("uploader") or info.get("channel")
                       or info.get("uploader") or "?",
            "duration": e.get("duration"), "views": e.get("view_count"),
        })
    return out[:n]


def show_results(entries):
    print()
    for i, e in enumerate(entries, 1):
        print(f"{i:>3}. {e['title']}")
        print(f"     {e['channel']}  |  {fmt_duration(e['duration'])}  |  "
              + t("{v} Aufrufe", "{v} views").format(v=fmt_views(e["views"])))
    print()


def build_opts(args, outdir, rank=None):
    mode = "mp3" if args.mp3 else "audio" if args.audio else "mp4" if args.mp4 else "mkv"
    template = NAME_PRESETS[args.name].replace("{rank}", f"{int(rank or 0):02d}")
    start, end = args.cut_range
    cut = start is not None or end is not None
    folder = "%(channel)s/" if args.channel_folder else ""
    opts = base_opts(args)
    opts.update({
        "outtmpl": str(outdir / (folder + template + (" clip" if cut else "") + ".%(ext)s")),
        "noplaylist": True,
        "windowsfilenames": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
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
        h = int(args.max_height or 0)
        opts["format"] = f"bv*[height<={h}]+ba/b[height<={h}]/bv*+ba/b" if h else "bv*+ba/b"
        if mode == "mp4":
            opts.update(format_sort=["res", "ext:mp4:m4a"], merge_output_format="mp4")
        else:
            opts["merge_output_format"] = "mkv"
        langs = [x.strip() for x in (args.subs or "").split(",") if x.strip()]
        if langs:
            opts["writesubtitles"] = True
            opts["subtitleslangs"] = langs
    embed = bool(args.embed) and mode != "audio"
    add_meta = mode == "mp3" or embed
    add_chapters = bool(args.chapters) and not audio
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


def download(entries, args, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for i, e in enumerate(entries, 1):
        print(f"\n[{i}/{len(entries)}] {e['title']}")
        rank = i if args.name == "rank" else None
        try:
            with yt_dlp.YoutubeDL(build_opts(args, outdir, rank)) as ydl:
                ydl.download([e["url"]])
        except Exception as err:
            failed += 1
            print(t("Fehler: {e}", "Error: {e}").format(e=str(err).strip()[:300]), file=sys.stderr)
    ok = len(entries) - failed
    print(t("\nFertig: {ok} geladen, {f} fehlgeschlagen. Ordner: {d}",
            "\nDone: {ok} downloaded, {f} failed. Folder: {d}").format(ok=ok, f=failed, d=outdir))
    return failed


def make_parser():
    p = argparse.ArgumentParser(
        prog="ytpick-cli",
        description=t("YouTube suchen und in bester Qualität laden (Terminal-Version von ytpick)",
                      "Search YouTube and download in best quality (terminal version of ytpick)"),
        epilog=t("Eingaben: Suchbegriff, @Kanal [Filterwort], Kanal-, Playlist- oder Video-URL.",
                 "Input: search term, @channel [filter word], channel, playlist or video URL."))
    p.add_argument("query", nargs="?", help=t("Suchbegriff, @Kanal oder URL", "search term, @channel or URL"))
    p.add_argument("-n", type=int, default=10,
                   help=t("Anzahl Treffer (Standard 10)", "number of results (default 10)"))
    p.add_argument("-o", "--output", default=str(Path.home() / "Downloads" / "YouTube"),
                   help=t("Zielordner", "target folder"))
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--mp4", action="store_true", help=t("MP4 statt MKV", "MP4 instead of MKV"))
    fmt.add_argument("--audio", action="store_true",
                     help=t("Nur Audio (Originalformat)", "audio only (original format)"))
    fmt.add_argument("--mp3", action="store_true", help=t("Audio als MP3", "audio as MP3"))
    p.add_argument("--max-height", type=int, default=0, metavar="PX",
                   help=t("Maximale Auflösung, z.B. 1080", "maximum resolution, e.g. 1080"))
    p.add_argument("--cut", metavar=t("START-ENDE", "START-END"),
                   help=t("Nur einen Ausschnitt laden, z.B. 1:20-3:45", "download only a clip, e.g. 1:20-3:45"))
    p.add_argument("--embed", action="store_true",
                   help=t("Cover und Metadaten einbetten", "embed cover and metadata"))
    p.add_argument("--chapters", action="store_true", help=t("Kapitel einbetten", "embed chapters"))
    p.add_argument("--subs", metavar=t("SPRACHEN", "LANGS"),
                   help=t("Untertitel einbetten, z.B. de,en", "embed subtitles, e.g. de,en"))
    p.add_argument("--name", choices=sorted(NAME_PRESETS), default="title",
                   help=t("Dateiname: title, channel oder rank (Nummer)",
                          "file name: title, channel or rank (number)"))
    p.add_argument("--channel-folder", action="store_true",
                   help=t("Eigener Ordner pro Kanal", "own folder per channel"))
    p.add_argument("--cookies", choices=BROWSERS,
                   help=t("Cookies aus diesem Browser nutzen", "use cookies from this browser"))
    p.add_argument("--rate", type=float, default=0, metavar="MB/S",
                   help=t("Maximale Geschwindigkeit in MB/s (0 = unbegrenzt)",
                          "maximum speed in MB/s (0 = unlimited)"))
    pick = p.add_mutually_exclusive_group()
    pick.add_argument("--pick", metavar=t("AUSWAHL", "SELECTION"),
                      help=t("Ohne Rückfrage laden, z.B. 1,3 oder 2-4", "download without prompt, e.g. 1,3 or 2-4"))
    pick.add_argument("--all", action="store_true",
                      help=t("Alle Treffer ohne Rückfrage laden", "download all results without prompt"))
    pick.add_argument("--list", action="store_true", help=t("Treffer nur anzeigen", "only list the results"))
    p.add_argument("--version", action="version", version=f"ytpick-cli {__version__}")
    return p


def run_query(query, args, outdir):
    spec = parse_query(query)
    if spec["kind"] == "video":
        return download([{"id": "", "title": spec["url"], "url": spec["url"]}], args, outdir)
    n = max(1, args.n)
    interactive = sys.stdin.isatty() and not (args.pick or args.all or args.list)
    while True:
        print(t("Lade Treffer für: {q} …", "Loading results for: {q} …").format(q=query))
        entries = fetch(spec, n, args)
        if not entries:
            print(t("Keine Treffer.", "No results."))
            return 0
        show_results(entries)
        if args.list:
            return 0
        if args.all:
            return download(entries, args, outdir)
        if args.pick:
            idx = parse_selection(args.pick, len(entries))
            return download([entries[i - 1] for i in idx], args, outdir)
        if not interactive:
            print(t("Kein Terminal: mit --pick oder --all laden.", "No terminal: use --pick or --all to download."))
            return 0
        while True:
            sel = input(t("Auswahl (z.B. 1,3 | 2-4 | all | m = mehr | Enter = neue Suche | q = Ende): ",
                          "Selection (e.g. 1,3 | 2-4 | all | m = more | Enter = new search | q = quit): ")).strip()
            if not sel:
                return 0
            if sel.lower() == "q":
                raise SystemExit(0)
            if sel.lower() == "m":
                n += max(1, args.n)
                break
            try:
                idx = parse_selection(sel, len(entries))
            except ValueError as err:
                print(err)
                continue
            return download([entries[i - 1] for i in idx], args, outdir)


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        args.cut_range = parse_cut(args.cut)
    except ValueError:
        parser.error(t("--cut erwartet START-ENDE, z.B. 1:20-3:45", "--cut expects START-END, e.g. 1:20-3:45"))
    outdir = Path(args.output).expanduser()
    failed = 0
    if args.query:
        return 1 if run_query(args.query, args, outdir) else 0
    if not sys.stdin.isatty():
        parser.error(t("Suchbegriff oder URL fehlt.", "Search term or URL is missing."))
    while True:
        query = input(t("Suchbegriff, @Kanal oder URL (leer = Ende): ",
                        "Search term, @channel or URL (empty = quit): ")).strip()
        if not query:
            return 1 if failed else 0
        failed += run_query(query, args, outdir)


def entry():
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(t("\nAbgebrochen.", "\nCancelled."))
        sys.exit(130)
    except Exception as err:
        print(t("Fehler: {e}", "Error: {e}").format(e=str(err).strip()[:300]), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    entry()
