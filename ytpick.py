import argparse
import json
import locale
import os
import queue
import re
import shutil
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.request import Request, urlopen

try:
    import yt_dlp
except ImportError:
    raise SystemExit("yt-dlp fehlt. Installieren mit: pip install -U yt-dlp[default]")

try:
    from yt_dlp.version import __version__ as YTDLP_VERSION
except Exception:
    YTDLP_VERSION = "?"

try:
    from PIL import Image, ImageOps, ImageTk
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False

LANG = "de"
TRANSLATIONS = {}


def _(text):
    if LANG == "en":
        return TRANSLATIONS.get(text, text)
    return text


def detect_language(choice):
    if choice in ("de", "en"):
        return choice
    try:
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    except Exception:
        loc = ""
    return "de" if loc.startswith("de") else "en"


def refresh_windows_path():
    if sys.platform != "win32":
        return
    try:
        import winreg
        parts = []
        for hive, sub in (
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, "Environment"),
        ):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    val, __ = winreg.QueryValueEx(k, "Path")
                    parts.append(os.path.expandvars(val))
            except OSError:
                pass
        cur = os.environ.get("PATH", "")
        known = set(cur.split(";"))
        extra = [p for p in ";".join(parts).split(";") if p and p not in known]
        if extra:
            os.environ["PATH"] = cur + ";" + ";".join(extra)
    except Exception:
        pass


refresh_windows_path()

__version__ = "0.1.0"

STATE_FILE = Path.home() / ".ytdl_gui.json"
CACHE_FILE = Path.home() / ".ytdl_gui_cache.json"
LOG_FILE = Path.home() / ".ytdl_gui.log"
THUMB_DIR = Path.home() / ".ytdl_gui_thumbs"
THUMB_W, THUMB_H = 96, 54
MAX_THUMBS = 600
THUMB_WORKERS = 3
WATCH_LIMIT = 30
WATCH_SEEN_MAX = 300
WATCH_NEW_MAX = 60
HEIGHTS = [0, 2160, 1440, 1080, 720, 480]
DEFAULT_FMT = {"height": 0, "subs": False, "sub_langs": "de,en", "chapters": False,
               "channel_folder": False}
RESULTS = 50
POOL = 150
CHANNEL_POOL = 300
CACHE_TTL = 12 * 3600
MAX_CACHED_SEARCHES = 40
DATE_WORKERS = 2
BROWSERS = ["keine", "firefox", "chrome", "edge", "brave", "vivaldi", "opera", "safari"]

COLUMNS = [
    ("pin", "★", 34, "center"),
    ("rank", "#", 40, "e"),
    ("titel", "Titel", 330, "w"),
    ("kanal", "Kanal", 150, "w"),
    ("verif", "Status", 90, "w"),
    ("datum", "Upload", 90, "w"),
    ("dauer", "Dauer", 82, "e"),
    ("aufrufe", "Aufrufe", 100, "e"),
]

COLUMN_KEYS = [c[0] for c in COLUMNS]
COLUMN_LABELS = {
    "pin": "Merken (★)", "rank": "Rang (#)", "titel": "Titel", "kanal": "Kanal",
    "verif": "Kanal-Status (verifiziert)", "datum": "Upload-Datum", "dauer": "Dauer",
    "aufrufe": "Aufrufe",
}
LOCKED_COLUMNS = {"titel"}
DEFAULT_VISIBLE = ["pin", "rank", "titel", "kanal", "datum", "dauer", "aufrufe"]

DARK = {"bg": "#1e1f22", "panel": "#2b2d31", "field": "#25272b", "header": "#313338",
        "fg": "#e3e5e8", "muted": "#9aa0a6", "sel": "#2f5fa8", "accent": "#4c8dff",
        "border": "#3a3c41", "dl": "#7a7f87", "hid": "#5c6168", "ok": "#5fd37c", "bad": "#ff6b6b"}
LIGHT = {"bg": "#f3f3f3", "panel": "#e6e6e6", "field": "#ffffff", "header": "#e1e1e1",
         "fg": "#1b1b1b", "muted": "#666666", "sel": "#3b82f6", "accent": "#2563eb",
         "border": "#c4c4c4", "dl": "#8a8a8a", "hid": "#b5b5b5", "ok": "#1a8f3c", "bad": "#c62828"}

HELP_TEXT = [
    ("h", "Kurzanleitung"),
    ("p", "1. Suchen\n"
          "   Suchbegriff eingeben und Enter drücken. Für einen Kanal: @handle oder Kanal-URL, "
          "optional mit Filterwort (z.B. @HSV training).\n"
          "   Shift+Enter oder \"Ohne Cache\" lädt frisch von YouTube, sonst hilft der Cache gegen Limits."),
    ("p", "2. Auswählen\n"
          "   Klicken (Strg/Shift = mehrere). Spaltenköpfe sortieren. Entf blendet Videos aus, "
          "neue Treffer rücken nach.\n"
          "   Rechtsklick: Download, Mehr von diesem Kanal, Kanal blockieren."),
    ("p", "3. Herunterladen\n"
          "   Doppelklick oder \"Auswahl herunterladen\". MKV = beste Qualität, MP4 = kompatibler, "
          "Audio = nur Ton.\n"
          "   Geladene Videos erscheinen grau mit ✓."),
    ("p", "Merken und Einstellungen\n"
          "   Leertaste oder Klick auf ☆ merkt ein Video. Gemerkte Videos stehen oben und bleiben bei jeder "
          "neuen Suche erhalten.\n"
          "   Unter \"Einstellungen\" wählst du Spalten aus und legst ihre Reihenfolge fest. "
          "Die Spalte Status zeigt ein Häkchen bei von YouTube verifizierten Kanälen."),
    ("p", "4. Blockliste\n"
          "   Zeigt geblockte Kanäle und ausgeblendete Videos mit Zeitpunkt, Entsperren und Log."),
    ("p", "5. Bot-Check von YouTube?\n"
          "   Unten bei \"Cookies aus Browser\" einen Browser wählen, in dem du bei YouTube eingeloggt bist."),
    ("p", "Nur Inhalte herunterladen, die du herunterladen darfst."),
]


HELP_TEXT_EN = [
    ("h", "Quick guide"),
    ("p", "1. Search\n"
          "   Type a search term and press Enter. For a channel use @handle or the channel URL, "
          "optionally followed by a filter word (e.g. @HSV training).\n"
          "   Shift+Enter or \"No cache\" loads fresh from YouTube; otherwise the cache helps against rate limits."),
    ("p", "2. Pick\n"
          "   Click (Ctrl/Shift = several). Column headers sort. Del hides videos, "
          "new results move up.\n"
          "   Right click: download, more from this channel, block channel."),
    ("p", "3. Download\n"
          "   Double click or \"Download selection\". MKV = best quality, MP4 = more compatible, "
          "audio = sound only. Downloads run in the queue (pause, cancel).\n"
          "   Downloaded videos appear grey with ✓."),
    ("p", "Pin and settings\n"
          "   Space or a click on ☆ pins a video. Pinned videos stay on top and survive every "
          "new search.\n"
          "   \"Settings\" lets you choose columns, their order, thumbnails and the language. "
          "The Status column shows a check mark for channels verified by YouTube."),
    ("p", "4. Blocklist\n"
          "   Shows blocked channels and hidden videos with timestamps, unblocking and the log."),
    ("p", "5. YouTube bot check?\n"
          "   Choose a browser at \"Cookies from browser\" in which you are signed in to YouTube."),
    ("p", "Only download content you are allowed to download."),
]

TRANSLATIONS.update({
    "live": "live",
    "gerade eben": "just now",
    "vor {n} Std": "{n} h ago",
    "vor {n} Min": "{n} min ago",
    "fertige Datei nicht gefunden oder leer": "finished file missing or empty",
    "keine Antwort von yt-dlp": "no response from yt-dlp",
    "falsche Video-ID ({a} statt {b})": "wrong video ID ({a} instead of {b})",
    "Kurzanleitung": "Quick guide",
    "Einstellungen": "Settings",
    "Einstellungen…": "Settings…",
    "Blockliste": "Blocklist",
    "Blockliste…": "Blocklist…",
    "Download-Optionen": "Download options",
    "pausiert": "paused",
    "Warteschlange": "Queue",
    "Warteschlange…": "Queue…",
    "Kanal wird hinzugefügt …": "Adding channel …",
    "Beobachtete Kanäle": "Watched channels",
    "Beobachtete Kanäle…": "Watched channels…",
    "Neue Videos beobachteter Kanäle": "New videos from watched channels",
    "Kanal {t}": "Channel {t}",
    "Suche „{q}“": "Search “{q}”",
    " · Filter „{f}“": " · filter “{f}”",
    "Suchbegriff, @Kanal oder Kanal-URL eingeben und Enter drücken.":
        "Enter a search term, @channel or channel URL and press Enter.",
    "Herunterladen": "Download",
    "Herunterladen mit Optionen…": "Download with options…",
    "Kanal beobachten": "Watch channel",
    "Merken/Merkung aufheben": "Pin/unpin",
    "Mehr von diesem Kanal": "More from this channel",
    "Video ausblenden/einblenden": "Hide/show video",
    "Kanal blockieren": "Block channel",
    "Video MKV (beste Qualität)": "Video MKV (best quality)",
    "Video MP4": "Video MP4",
    "Nur Audio": "Audio only",
    "Gemerkte Videos": "Pinned videos",
    "Systemcheck": "System check",
    "Vorschaubilder anzeigen": "Show thumbnails",
    "Die Sprache wird nach einem Neustart übernommen.": "The language changes after a restart.",
    "Für diesen Kanal ist keine Kanal-ID bekannt. Nutze @handle oder die Kanal-URL.":
        "No channel ID is known for this channel. Use @handle or the channel URL.",
    "Kanal": "Channel",
    "Kanal-ID": "Channel ID",
    "Geblockt am": "Blocked on",
    "Kanäle": "Channels",
    "Video": "Video",
    "Videos": "Videos",
    "Ausgeblendet am": "Hidden on",
    "Log": "Log",
    "vor dem Logging": "before logging",
    "unbekannt": "unknown",
    "YouTube verlangt einen Bot-Check. Wähle unten einen Browser bei 'Cookies aus Browser' (Datum bleibt bis dahin leer).":
        "YouTube asks for a bot check. Choose a browser at 'Cookies from browser' below (dates stay empty until then).",
    "Hinweis": "Note",
    "Bitte erst ein oder mehrere Videos auswählen.": "Please select one or more videos first.",
    "Beste": "Best",
    "Warteschlange: {d}/{t} fertig": "Queue: {d}/{t} done",
    "wartet": "waiting",
    "lädt": "downloading",
    "fertig": "done",
    "Fehler": "error",
    "abgebrochen": "cancelled",
    "Pause": "Pause",
    "Fortsetzen": "Resume",
    "Titel": "Title",
    "Status": "Status",
    "Fortschritt": "Progress",
    "Info": "Info",
    "Kanal wird bereits beobachtet.": "Channel is already being watched.",
    "Neu": "New",
    "Zuletzt geprüft": "Last checked",
    "Bitte @handle oder eine Kanal-URL eingeben.": "Please enter an @handle or a channel URL.",
    "Keine Kanäle in der Beobachtungsliste.": "No channels in the watch list.",
    "Prüfung beendet: {n} neue Videos": "Check finished: {n} new videos",
    ", {e} Fehler (siehe Log)": ", {e} errors (see log)",
    "Keine neuen Videos. Erst „Alle prüfen“ ausführen.": "No new videos. Run “Check all” first.",
    "gefunden": "found",
    "fehlt (nötig zum Zusammenfügen von Video und Ton)": "missing (needed to merge video and audio)",
    "fehlt (nötig für YouTube-Downloads)": "missing (needed for YouTube downloads)",
    "Cookies: {b}. Gilt für Datum-Abruf und Downloads.": "Cookies: {b}. Applies to date lookup and downloads.",
    "Kanal blockiert: ": "Channel blocked: ",
    "{l} … lädt": "{l} … loading",
    "{n} Videos": "{n} videos",
    "Verarbeite …": "Processing …",
    ", {f} fehlgeschlagen": ", {f} failed",
    "Für diesen Kanal fehlt die Kanal-ID. Bitte über @handle hinzufügen.":
        "The channel ID is missing for this channel. Please add it via @handle.",
    "Prüfe {n} Kanal/Kanäle …": "Checking {n} channel(s) …",
    "Suchen": "Search",
    "Ohne Cache": "No cache",
    "Ausgeblendete/Geblockte anzeigen": "Show hidden/blocked",
    "Bereits geladene ausblenden": "Hide already downloaded",
    "Merken (Leertaste)": "Pin (Space)",
    "Video ausblenden/einblenden (Entf)": "Hide/show video (Del)",
    "Ordner…": "Folder…",
    "Cookies aus Browser:": "Cookies from browser:",
    "Upload-Datum nachladen": "Fetch upload date",
    "Datum erneut versuchen": "Retry dates",
    "Hilfe": "Help",
    "Dark Mode": "Dark mode",
    "Auswahl herunterladen": "Download selection",
    "Optionen…": "Options…",
    "Version {v}": "version {v}",
    "Beim Start anzeigen": "Show at startup",
    "Los geht's": "Let's go",
    "Fehlende Teile installiert setup.bat (im Installer-Ordner).": "setup.bat (in the installer folder) installs missing parts.",
    "Angezeigte Spalten und Reihenfolge": "Visible columns and order",
    "Nach oben": "Move up",
    "Nach unten": "Move down",
    "Ein/Aus": "On/off",
    "Standard": "Default",
    "Titel ist immer sichtbar. Doppelklick schaltet eine Spalte ein oder aus.":
        "Title is always visible. Double click toggles a column.",
    "Übernehmen": "Apply",
    "Abbrechen": "Cancel",
    "{n} Video(s) wieder eingeblendet.": "{n} video(s) shown again.",
    "{n} Video(s) ausgeblendet, neue Treffer rücken nach.": "{n} video(s) hidden, new results move up.",
    "Ausgewählte Kanäle entsperren": "Unblock selected channels",
    "Ausgewählte Videos wieder einblenden": "Show selected videos again",
    "Aktualisieren": "Refresh",
    "(Titel unbekannt) [{v}]": "(title unknown) [{v}]",
    "{l} · aus Cache ({a})": "{l} · from cache ({a})",
    "{l} · frisch geladen": "{l} · freshly loaded",
    "{note} · {n} sichtbar (Pool {p})": "{note} · {n} visible (pool {p})",
    "Format": "Format",
    "Max. Auflösung": "Max. resolution",
    "Untertitel einbetten, Sprachen:": "Embed subtitles, languages:",
    "Kapitel einbetten": "Embed chapters",
    "Eigener Ordner pro Kanal": "Separate folder per channel",
    "Als Standard speichern": "Save as default",
    "Fertige entfernen": "Remove finished",
    "Alle abbrechen": "Cancel all",
    "Auswahl abbrechen": "Cancel selected",
    "Kanal beobachtet: {n}": "Watching channel: {n}",
    "Hinzufügen (@handle oder URL)": "Add (@handle or URL)",
    "Alle prüfen": "Check all",
    "Entfernen": "Remove",
    "Neue Videos anzeigen": "Show new videos",
    "(benötigt: pip install pillow)": "(requires: pip install pillow)",
    "✔ verifiziert": "✔ verified",
    "Fehler bei der Suche: {e}": "Search error: {e}",
    " · Datum fehlt bei {m}": " · date missing for {m}",
    "Lade Upload-Datum … {d}/{t}": "Loading upload dates … {d}/{t}",
    "Prüfung fehlgeschlagen: {r}": "Verification failed: {r}",
    "Kanal konnte nicht hinzugefügt werden: {e}": "Could not add channel: {e}",
    "Datum bei {n} Video(s) nicht ladbar. Grund: {r}": "Date not loadable for {n} video(s). Reason: {r}",
    "{n} Treffer sichtbar. Datum vollständig geladen.": "{n} results visible. All dates loaded.",
    "unbekannt (siehe Log)": "unknown (see log)",
    "Upload": "Upload",
    "Dauer": "Duration",
    "Aufrufe": "Views",
    "Merken (★)": "Pin (★)",
    "Rang (#)": "Rank (#)",
    "Kanal-Status (verifiziert)": "Channel status (verified)",
    "Upload-Datum": "Upload date",
})


def set_titlebar(win, dark):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


class QuietLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action, text):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{now()} | {action:<14} | {text}\n")
    except Exception:
        pass


def clean_text(s):
    return "".join(c for c in (s or "") if ord(c) <= 0xFFFF).strip()


def fmt_dur(sec):
    if not sec:
        return _("live")
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_date(d):
    if d is None:
        return "…"
    if len(d) == 8:
        return f"{d[6:8]}.{d[4:6]}.{d[0:4]}"
    return "?"


def fmt_views(v):
    return f"{v:,}".replace(",", ".") if v else "?"


def age_text(ts):
    mins = int((time.time() - ts) / 60)
    if mins < 1:
        return _("gerade eben")
    if mins < 90:
        return _("vor {n} Min").format(n=mins)
    return _("vor {n} Std").format(n=mins // 60)


def is_bot_error(err):
    s = str(err).lower()
    return "sign in to confirm" in s or "not a bot" in s


def short_err(err, n=110):
    s = re.sub(r"\x1b\[[0-9;]*m", "", str(err)).replace("\n", " ").strip()
    s = re.sub(r"^ERROR:\s*", "", s)
    return s[:n]


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_query(query):
    m = re.match(r"^(@\S+|https?://\S*youtube\.com/\S+)\s*(.*)$", query.strip())
    if not m:
        q = query.strip()
        return {"kind": "search", "key": "s:" + q.lower(), "url": f"ytsearch{POOL}:{q}",
                "term": "", "label": _("Suche „{q}“").format(q=q)}
    target, term = m.group(1), m.group(2).strip()
    if target.startswith("@"):
        url = f"https://www.youtube.com/{target}/videos"
    else:
        url = target.rstrip("/")
        if (not re.search(r"/(videos|streams|shorts|playlists|search|featured)(/|\?|$)", url)
                and "/watch" not in url and "/playlist" not in url):
            url += "/videos"
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


def download_opts(base, outdir, mode, fmt, hook):
    opts = dict(base)
    folder = "%(channel)s/" if fmt.get("channel_folder") else ""
    opts.update({
        "outtmpl": str(outdir / (folder + "%(title).150B [%(id)s].%(ext)s")),
        "noplaylist": True,
        "windowsfilenames": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
        "progress_hooks": [hook],
    })
    pp = []
    if mode == "audio":
        opts["format"] = "bestaudio/best"
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
    if fmt.get("chapters"):
        pp.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True})
    if mode != "audio" and opts.get("writesubtitles"):
        pp.append({"key": "FFmpegEmbedSubtitle"})
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


class App(tk.Tk):
    def __init__(self):
        global LANG
        super().__init__()
        self.title(f"ytpick {__version__}")
        self.set_icon()
        self.geometry("1050x700")

        st = load_json(STATE_FILE, {})
        hidden = st.get("hidden", {})
        if isinstance(hidden, list):
            hidden = {v: {"title": "?", "channel": "?", "at": "?"} for v in hidden}
        self.hidden = hidden
        self.blocked = st.get("blocked_channels", {})
        self.history = set(st.get("downloaded", []))
        self.pinned = st.get("pinned", {})
        s = st.get("settings", {})
        order = [k for k in s.get("col_order", []) if k in COLUMN_KEYS]
        self.col_order = order + [k for k in COLUMN_KEYS if k not in order]
        vis = s.get("col_visible", DEFAULT_VISIBLE)
        self.col_visible = {k for k in vis if k in COLUMN_KEYS} | LOCKED_COLUMNS
        self.set_win = None
        self.watch = st.get("watch", {})
        self.fmt = {**DEFAULT_FMT, **s.get("fmt", {})}
        self.lang_choice = s.get("lang", "auto")
        LANG = detect_language(self.lang_choice)
        self.title(f"ytpick {__version__}")
        self.jobs = []
        self.job_seq = 0
        self.job_event = threading.Event()
        self.paused = False
        self.q_win = None
        self.w_win = None
        self.fmt_win = None
        self.thumbs = {}
        self.thumb_req = set()
        self.thumbq = queue.Queue()
        self.blank_thumb = None

        cache = load_json(CACHE_FILE, {})
        self.cache = {"searches": cache.get("searches", {}), "dates": cache.get("dates", {})}
        self.cache_dirty = 0

        self.disk_ids = set()
        self.items = []
        self.by_id = {}
        self.shown = []
        self.token = 0
        self.date_total = self.date_done = self.date_fail = 0
        self.date_last_err = ""
        self.date_abort = False
        self.dateq = queue.Queue()
        self.sort_col = "rank"
        self.sort_rev = False
        self.bl_win = None
        self.bl_log = None
        self.readme_win = None
        self.readme_text = None
        self.pal = DARK

        self.outdir = tk.StringVar(value=s.get("outdir", str(Path.home() / "Downloads" / "YouTube")))
        self.mode = tk.StringVar(value=s.get("mode", "mkv"))
        self.cookies = tk.StringVar(value=s.get("cookies", "keine"))
        self.fetch_dates = tk.BooleanVar(value=s.get("fetch_dates", True))
        self.dark = tk.BooleanVar(value=s.get("dark", True))
        self.show_readme = tk.BooleanVar(value=s.get("show_readme", True))
        self.show_thumbs = tk.BooleanVar(value=bool(s.get("show_thumbs", False)) and HAVE_PIL)
        self.show_hidden = tk.BooleanVar(value=False)
        self.hide_downloaded = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value=_("Suchbegriff, @Kanal oder Kanal-URL eingeben und Enter drücken."))

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.q = ttk.Entry(top)
        self.q.pack(side="left", fill="x", expand=True)
        self.q.bind("<Return>", lambda e: self.do_search())
        self.q.bind("<Shift-Return>", lambda e: self.do_search(force=True))
        self.q.focus()
        ttk.Button(top, text=_("Suchen"), command=self.do_search).pack(side="left", padx=(6, 0))
        ttk.Button(top, text=_("Ohne Cache"), command=lambda: self.do_search(force=True)).pack(
            side="left", padx=(6, 0))

        filt = ttk.Frame(self, padding=(8, 0))
        filt.pack(fill="x")
        ttk.Checkbutton(filt, text=_("Ausgeblendete/Geblockte anzeigen"), variable=self.show_hidden,
                        command=self.render).pack(side="left")
        ttk.Checkbutton(filt, text=_("Bereits geladene ausblenden"), variable=self.hide_downloaded,
                        command=self.render).pack(side="left", padx=12)
        tools = ttk.Frame(self, padding=(8, 4, 8, 0))
        tools.pack(fill="x")
        ttk.Button(tools, text=_("Warteschlange…"), command=self.open_queue).pack(side="left")
        ttk.Button(tools, text=_("Beobachtete Kanäle…"), command=self.open_watch).pack(side="left", padx=6)
        ttk.Button(tools, text=_("Blockliste…"), command=self.open_blocklist).pack(side="left")
        ttk.Button(tools, text=_("Einstellungen…"), command=self.open_settings).pack(side="right")
        ttk.Button(filt, text=_("Kanal blockieren"), command=self.block_channels).pack(side="right")
        ttk.Button(filt, text=_("Merken (Leertaste)"), command=self.toggle_pin).pack(side="right", padx=6)
        ttk.Button(filt, text=_("Video ausblenden/einblenden (Entf)"),
                   command=self.toggle_hide).pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS],
                                 show="headings", selectmode="extended", height=6)
        self.tree.column("#0", width=THUMB_W + 10, minwidth=THUMB_W + 10, stretch=False)
        for key, text, width, anchor in COLUMNS:
            self.tree.heading(key, text=_(text), command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "titel"))
        self.apply_columns()
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.do_download())
        self.tree.bind("<Delete>", lambda e: self.toggle_hide())
        self.tree.bind("<space>", lambda e: self.toggle_pin() or "break")
        self.tree.bind("<Button-1>", self.on_click, add="+")
        self.tree.bind("<Button-3>", self.on_context)
        self.tree.bind("<Button-2>", self.on_context)
        self.ctx = tk.Menu(self, tearoff=0)
        self.ctx.add_command(label=_("Herunterladen"), command=self.do_download)
        self.ctx.add_command(label=_("Herunterladen mit Optionen…"), command=self.do_download_options)
        self.ctx.add_command(label=_("Kanal beobachten"), command=self.watch_selected_channel)
        self.ctx.add_command(label=_("Merken/Merkung aufheben"), command=self.toggle_pin)
        self.ctx.add_command(label=_("Mehr von diesem Kanal"), command=self.more_from_channel)
        self.ctx.add_separator()
        self.ctx.add_command(label=_("Video ausblenden/einblenden"), command=self.toggle_hide)
        self.ctx.add_command(label=_("Kanal blockieren"), command=self.block_channels)
        self.update_headings()

        opt = ttk.Frame(self, padding=(8, 4))
        opt.pack(fill="x")
        for text, val in ((_("Video MKV (beste Qualität)"), "mkv"),
                          (_("Video MP4"), "mp4"), (_("Nur Audio"), "audio")):
            ttk.Radiobutton(opt, text=text, value=val, variable=self.mode).pack(side="left", padx=4)
        ttk.Button(opt, text=_("Ordner…"), command=self.pick_dir).pack(side="right")
        ttk.Entry(opt, textvariable=self.outdir, width=40).pack(side="right", padx=6)

        opt2 = ttk.Frame(self, padding=(8, 0))
        opt2.pack(fill="x")
        ttk.Label(opt2, text=_("Cookies aus Browser:")).pack(side="left")
        cb = ttk.Combobox(opt2, textvariable=self.cookies, values=BROWSERS,
                          state="readonly", width=10)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_cookies_changed())
        ttk.Checkbutton(opt2, text=_("Upload-Datum nachladen"), variable=self.fetch_dates,
                        command=self.on_fetch_dates_toggle).pack(side="left", padx=12)
        ttk.Button(opt2, text=_("Datum erneut versuchen"), command=self.retry_dates).pack(side="left")
        ttk.Button(opt2, text=_("Hilfe"), command=self.show_readme_dialog).pack(side="right")
        ttk.Checkbutton(opt2, text=_("Dark Mode"), variable=self.dark,
                        command=self.on_theme_toggle).pack(side="right", padx=10)

        bot = ttk.Frame(self, padding=8)
        bot.pack(fill="x")
        ttk.Label(bot, textvariable=self.status).pack(side="left")
        ttk.Button(bot, text=_("Auswahl herunterladen"), command=self.do_download).pack(side="right")
        ttk.Button(bot, text=_("Optionen…"), command=self.do_download_options).pack(side="right", padx=6)

        self.apply_theme()
        self.apply_thumbs()
        for _i in range(DATE_WORKERS):
            threading.Thread(target=self._date_worker, daemon=True).start()
        for _i in range(THUMB_WORKERS):
            threading.Thread(target=self._thumb_worker, daemon=True).start()
        threading.Thread(target=self._queue_worker, daemon=True).start()
        self.prune_thumbs()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_disk()
        if self.pinned:
            self.token += 1
            self._show([], self.token, _("Gemerkte Videos"))
        if self.show_readme.get():
            self.after(400, self.show_readme_dialog)

    def set_icon(self):
        assets = Path(__file__).resolve().parent / "assets"
        ico, png = assets / "icon.ico", assets / "icon.png"
        try:
            if sys.platform == "win32" and ico.exists():
                self.iconbitmap(default=str(ico))
            elif png.exists():
                self.app_icon = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self.app_icon)
        except tk.TclError:
            pass

    def row_height(self):
        return THUMB_H + 6 if self.show_thumbs.get() else 22

    def apply_thumbs(self):
        on = self.show_thumbs.get()
        self.tree.configure(show="tree headings" if on else "headings")
        ttk.Style(self).configure("Treeview", rowheight=self.row_height())
        if on:
            self.ensure_thumbs()

    def prune_thumbs(self):
        try:
            files = sorted(THUMB_DIR.glob("*.jpg"), key=lambda f: f.stat().st_mtime)
            for f in files[:max(0, len(files) - MAX_THUMBS)]:
                f.unlink()
        except Exception:
            pass

    def ensure_thumbs(self):
        if not (self.show_thumbs.get() and HAVE_PIL):
            return
        for it in self.shown:
            if it["id"] not in self.thumb_req:
                self.thumb_req.add(it["id"])
                self.thumbq.put(it["id"])

    def _thumb_worker(self):
        while True:
            vid = self.thumbq.get()
            img = None
            try:
                path = THUMB_DIR / f"{vid}.jpg"
                if not path.exists():
                    THUMB_DIR.mkdir(parents=True, exist_ok=True)
                    req = Request(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                                  headers={"User-Agent": "Mozilla/5.0"})
                    with urlopen(req, timeout=15) as r:
                        data = r.read()
                    path.write_bytes(data)
                with Image.open(path) as im:
                    img = ImageOps.fit(im.convert("RGB"), (THUMB_W, THUMB_H))
            except Exception:
                img = None
            if img is not None:
                self.after(0, lambda v=vid, i=img: self._set_thumb(v, i))

    def _set_thumb(self, vid, img):
        photo = ImageTk.PhotoImage(img)
        self.thumbs[vid] = photo
        if self.show_thumbs.get() and self.tree.exists(vid):
            self.tree.item(vid, image=photo)

    def style_text(self, widget):
        p = self.pal
        widget.configure(bg=p["field"], fg=p["fg"], selectbackground=p["sel"],
                         selectforeground="#ffffff", relief="flat", highlightthickness=0,
                         borderwidth=0)
        if isinstance(widget, tk.Text):
            widget.configure(insertbackground=p["fg"])

    def theme_window(self, win):
        win.configure(bg=self.pal["bg"])
        set_titlebar(win, self.dark.get())

    def apply_theme(self):
        p = DARK if self.dark.get() else LIGHT
        self.pal = p
        st = ttk.Style(self)
        st.theme_use("clam")
        self.configure(bg=p["bg"])
        st.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                     bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"],
                     troughcolor=p["panel"], focuscolor=p["bg"], insertcolor=p["fg"])
        st.configure("TButton", background=p["panel"], foreground=p["fg"],
                     padding=(8, 3), borderwidth=1)
        st.map("TButton", background=[("active", p["sel"]), ("pressed", p["sel"])],
               foreground=[("disabled", p["muted"]), ("active", "#ffffff")])
        for w in ("TCheckbutton", "TRadiobutton"):
            st.configure(w, background=p["bg"], foreground=p["fg"])
            st.map(w, background=[("active", p["bg"])],
                   indicatorcolor=[("selected", p["accent"]), ("!selected", p["field"])])
        st.configure("TEntry", fieldbackground=p["field"], foreground=p["fg"], insertcolor=p["fg"])
        st.configure("TCombobox", fieldbackground=p["field"], background=p["panel"],
                     foreground=p["fg"], arrowcolor=p["fg"],
                     selectbackground=p["field"], selectforeground=p["fg"])
        st.map("TCombobox", fieldbackground=[("readonly", p["field"])],
               foreground=[("readonly", p["fg"])],
               selectbackground=[("readonly", p["field"])],
               selectforeground=[("readonly", p["fg"])])
        self.option_add("*TCombobox*Listbox.background", p["field"])
        self.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", p["sel"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        st.configure("Treeview", background=p["field"], fieldbackground=p["field"],
                     foreground=p["fg"], rowheight=self.row_height(), borderwidth=0)
        st.map("Treeview", background=[("selected", p["sel"])],
               foreground=[("selected", "#ffffff")])
        st.configure("Treeview.Heading", background=p["header"], foreground=p["fg"],
                     relief="flat", padding=(6, 4))
        st.map("Treeview.Heading", background=[("active", p["sel"])])
        st.configure("TNotebook", background=p["bg"], borderwidth=0)
        st.configure("TNotebook.Tab", background=p["panel"], foreground=p["fg"], padding=(12, 5))
        st.map("TNotebook.Tab", background=[("selected", p["sel"])],
               foreground=[("selected", "#ffffff")])
        st.configure("TScrollbar", background=p["header"], troughcolor=p["bg"],
                     arrowcolor=p["fg"], bordercolor=p["bg"])
        st.map("TScrollbar", background=[("active", p["sel"])])

        self.tree.tag_configure("downloaded", foreground=p["dl"])
        self.tree.tag_configure("hidden", foreground=p["hid"])
        self.ctx.configure(bg=p["panel"], fg=p["fg"], activebackground=p["sel"],
                           activeforeground="#ffffff", bd=0)
        set_titlebar(self, self.dark.get())
        if self.bl_win and self.bl_win.winfo_exists():
            self.theme_window(self.bl_win)
            if self.bl_log:
                self.style_text(self.bl_log)
        for w in (self.q_win, self.w_win, self.fmt_win):
            if w and w.winfo_exists():
                self.theme_window(w)
        if self.set_win and self.set_win.winfo_exists():
            self.theme_window(self.set_win)
            self.style_text(self.set_list)
        if self.readme_win and self.readme_win.winfo_exists():
            self.theme_window(self.readme_win)
            if self.readme_text:
                self.style_text(self.readme_text)
                self.readme_text.tag_configure("ok", foreground=p["ok"])
                self.readme_text.tag_configure("bad", foreground=p["bad"])

    def on_theme_toggle(self):
        self.apply_theme()
        self.save()

    def system_check(self):
        return [
            ("ffmpeg", shutil.which("ffmpeg") is not None,
             _("gefunden") if shutil.which("ffmpeg") else _("fehlt (nötig zum Zusammenfügen von Video und Ton)")),
            ("deno", shutil.which("deno") is not None,
             _("gefunden") if shutil.which("deno") else _("fehlt (nötig für YouTube-Downloads)")),
            ("ytpick", True, _("Version {v}").format(v=__version__)),
            ("yt-dlp", True, _("Version {v}").format(v=YTDLP_VERSION)),
        ]

    def show_readme_dialog(self):
        if self.readme_win and self.readme_win.winfo_exists():
            self.readme_win.lift()
            return
        win = tk.Toplevel(self)
        win.title(_("Kurzanleitung"))
        win.geometry("700x600")
        win.transient(self)
        self.readme_win = win

        btns = ttk.Frame(win, padding=10)
        btns.pack(side="bottom", fill="x")
        ttk.Checkbutton(btns, text=_("Beim Start anzeigen"), variable=self.show_readme,
                        command=self.save).pack(side="left")
        ttk.Button(btns, text=_("Los geht's"), command=win.destroy).pack(side="right")

        text = tk.Text(win, wrap="word", padx=16, pady=12, font=("Segoe UI", 10), cursor="arrow")
        text.pack(fill="both", expand=True)
        self.readme_text = text
        text.tag_configure("h", font=("Segoe UI", 14, "bold"), spacing3=8)
        text.tag_configure("sub", font=("Segoe UI", 11, "bold"), spacing1=10, spacing3=4)
        text.tag_configure("p", spacing3=10)
        text.tag_configure("ok")
        text.tag_configure("bad")
        for tag, content in (HELP_TEXT_EN if LANG == "en" else HELP_TEXT):
            text.insert("end", content + "\n", tag)
        text.insert("end", _("Systemcheck") + "\n", "sub")
        for name, ok, detail in self.system_check():
            text.insert("end", ("✓ " if ok else "✗ ") + f"{name}: {detail}\n", "ok" if ok else "bad")
        if not all(ok for __, ok, ___ in self.system_check()):
            text.insert("end", "\n" + _("Fehlende Teile installiert setup.bat (im Installer-Ordner).") + "\n", "p")
        text.configure(state="disabled")
        self.apply_theme()

    def save(self):
        data = {
            "hidden": self.hidden,
            "blocked_channels": self.blocked,
            "downloaded": sorted(self.history),
            "pinned": self.pinned,
            "watch": self.watch,
            "settings": {
                "col_order": self.col_order,
                "col_visible": [k for k in self.col_order if k in self.col_visible],
                "outdir": self.outdir.get(),
                "mode": self.mode.get(),
                "cookies": self.cookies.get(),
                "fetch_dates": self.fetch_dates.get(),
                "dark": self.dark.get(),
                "show_readme": self.show_readme.get(),
                "show_thumbs": self.show_thumbs.get(),
                "lang": self.lang_choice,
                "fmt": self.fmt,
            },
        }
        try:
            STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    def save_cache(self):
        searches = self.cache["searches"]
        if len(searches) > MAX_CACHED_SEARCHES:
            keep = sorted(searches, key=lambda k: searches[k]["at"], reverse=True)[:MAX_CACHED_SEARCHES]
            self.cache["searches"] = {k: searches[k] for k in keep}
        try:
            CACHE_FILE.write_text(json.dumps(self.cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self.cache_dirty = 0

    def on_close(self):
        self.save()
        self.save_cache()
        self.destroy()

    def refresh_disk(self):
        ids = set()
        root = Path(self.outdir.get()).expanduser()
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                depth = len(Path(dirpath).relative_to(root).parts)
                if depth >= 1:
                    dirnames[:] = []
                for name in filenames:
                    m = re.search(r"\[([A-Za-z0-9_-]{11})\]", name)
                    if m:
                        ids.add(m.group(1))
        except Exception:
            pass
        self.disk_ids = ids

    def is_downloaded(self, vid):
        return vid in self.history or vid in self.disk_ids

    @staticmethod
    def chan_key(it):
        return it["channel_id"] or ("name:" + it["channel"])

    def ydl_opts(self):
        opts = {"quiet": True, "no_warnings": True, "logger": QuietLogger()}
        b = self.cookies.get()
        if b and b != "keine":
            opts["cookiesfrombrowser"] = (b,)
        return opts

    def on_cookies_changed(self):
        self.save()
        self.status.set(_("Cookies: {b}. Gilt für Datum-Abruf und Downloads.").format(b=self.cookies.get()))
        self.retry_dates()

    def on_fetch_dates_toggle(self):
        self.save()
        self.ensure_dates()

    def retry_dates(self):
        self.date_abort = False
        self.date_total = self.date_done = self.date_fail = 0
        for it in self.items:
            if it["date"] == "":
                it["date"] = None
                it["queued"] = False
        self.render()

    def apply_columns(self):
        show = [k for k in self.col_order if k in self.col_visible]
        self.tree.configure(displaycolumns=show)

    def open_settings(self):
        if self.set_win and self.set_win.winfo_exists():
            self.set_win.lift()
            return
        win = tk.Toplevel(self)
        win.title(_("Einstellungen"))
        win.geometry("460x540")
        win.transient(self)
        self.set_win = win
        self.set_order = list(self.col_order)
        self.set_vis = set(self.col_visible)
        self.set_thumbs = tk.BooleanVar(value=self.show_thumbs.get())
        self.set_lang = tk.StringVar(value={"auto": "Auto", "de": "Deutsch", "en": "English"}[self.lang_choice])

        ttk.Label(win, text=_("Angezeigte Spalten und Reihenfolge"), padding=(12, 10, 12, 4)).pack(anchor="w")
        body = ttk.Frame(win, padding=(12, 0))
        body.pack(fill="both", expand=True)
        lb = tk.Listbox(body, activestyle="none", exportselection=False, font=("Segoe UI", 10))
        lb.pack(side="left", fill="both", expand=True)
        self.set_list = lb
        side = ttk.Frame(body)
        side.pack(side="left", fill="y", padx=(10, 0))
        ttk.Button(side, text=_("Nach oben"), command=lambda: self.move_setting(-1)).pack(fill="x")
        ttk.Button(side, text=_("Nach unten"), command=lambda: self.move_setting(1)).pack(fill="x", pady=6)
        ttk.Button(side, text=_("Ein/Aus"), command=self.toggle_setting).pack(fill="x")
        ttk.Button(side, text=_("Standard"), command=self.reset_settings).pack(fill="x", pady=(18, 0))
        lb.bind("<Double-1>", lambda e: self.toggle_setting())
        lb.bind("<space>", lambda e: self.toggle_setting() or "break")

        ttk.Label(win, text=_("Titel ist immer sichtbar. Doppelklick schaltet eine Spalte ein oder aus."),
                  padding=(12, 8)).pack(anchor="w")
        extra = ttk.Frame(win, padding=(12, 0))
        extra.pack(fill="x")
        thumb_cb = ttk.Checkbutton(extra, text=_("Vorschaubilder anzeigen"), variable=self.set_thumbs)
        thumb_cb.grid(row=0, column=0, sticky="w")
        if not HAVE_PIL:
            thumb_cb.state(["disabled"])
            ttk.Label(extra, text=_("(benötigt: pip install pillow)")).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(extra, text=_("Sprache / Language")).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(extra, textvariable=self.set_lang, values=["Auto", "Deutsch", "English"],
                     state="readonly", width=10).grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))
        btns = ttk.Frame(win, padding=12)
        btns.pack(fill="x")
        ttk.Button(btns, text=_("Übernehmen"), command=self.apply_settings).pack(side="right")
        ttk.Button(btns, text=_("Abbrechen"), command=win.destroy).pack(side="right", padx=6)
        self.fill_setting_list(0)
        self.apply_theme()

    def fill_setting_list(self, select):
        lb = self.set_list
        lb.delete(0, "end")
        for k in self.set_order:
            mark = "☑" if k in self.set_vis else "☐"
            lb.insert("end", f"{mark}  {_(COLUMN_LABELS[k])}")
        lb.selection_set(select)
        lb.activate(select)

    def current_setting(self):
        sel = self.set_list.curselection()
        return sel[0] if sel else 0

    def move_setting(self, d):
        i = self.current_setting()
        j = i + d
        if 0 <= j < len(self.set_order):
            self.set_order[i], self.set_order[j] = self.set_order[j], self.set_order[i]
            self.fill_setting_list(j)

    def toggle_setting(self):
        i = self.current_setting()
        k = self.set_order[i]
        if k in LOCKED_COLUMNS:
            return
        if k in self.set_vis:
            self.set_vis.discard(k)
        else:
            self.set_vis.add(k)
        self.fill_setting_list(i)

    def reset_settings(self):
        self.set_order = list(COLUMN_KEYS)
        self.set_vis = set(DEFAULT_VISIBLE) | LOCKED_COLUMNS
        self.fill_setting_list(0)

    def apply_settings(self):
        self.col_order = list(self.set_order)
        self.col_visible = set(self.set_vis) | LOCKED_COLUMNS
        self.apply_columns()
        self.show_thumbs.set(self.set_thumbs.get() and HAVE_PIL)
        old_lang = self.lang_choice
        self.lang_choice = {"Auto": "auto", "Deutsch": "de", "English": "en"}[self.set_lang.get()]
        self.apply_theme()
        self.apply_thumbs()
        self.render()
        self.save()
        self.set_win.destroy()
        if old_lang != self.lang_choice:
            messagebox.showinfo("ytpick", _("Die Sprache wird nach einem Neustart übernommen."))

    def on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        cols = self.tree.cget("displaycolumns")
        idx = int(self.tree.identify_column(event.x)[1:]) - 1
        if 0 <= idx < len(cols) and cols[idx] == "pin":
            row = self.tree.identify_row(event.y)
            if row in self.by_id:
                self.set_pin([row])
                return "break"

    def toggle_pin(self):
        ids = [it["id"] for it in self.selected_items()]
        if ids:
            self.set_pin(ids)

    def set_pin(self, ids):
        mark = not all(i in self.pinned for i in ids)
        for i in ids:
            it = self.by_id[i]
            if mark:
                self.pinned[i] = {k: it.get(k) for k in
                                  ("id", "title", "channel", "channel_id", "duration",
                                   "views", "date", "verified")}
                log("PIN", f"{i} | {it['title']} | {it['channel']}")
            else:
                self.pinned.pop(i, None)
                log("UNPIN", f"{i} | {it['title']} | {it['channel']}")
        self.save()
        self.render()

    def update_headings(self):
        for key, text, __, ___ in COLUMNS:
            arrow = ""
            if key == self.sort_col:
                arrow = " ▼" if self.sort_rev else " ▲"
            self.tree.heading(key, text=_(text) + arrow)

    def sort_by(self, key):
        if self.sort_col == key:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col = key
            self.sort_rev = key in ("datum", "dauer", "aufrufe")
        self.update_headings()
        self.render()

    def sort_key(self, it):
        c = self.sort_col
        if c == "rank":
            return it["rank"]
        if c == "titel":
            return it["title"].lower()
        if c == "kanal":
            return it["channel"].lower()
        if c == "pin":
            return 0 if it["id"] in self.pinned else 1
        if c == "verif":
            return 1 if it.get("verified") else 0
        if c == "datum":
            return it["date"] or ""
        if c == "dauer":
            return it["duration"] or 0
        return it["views"] or 0

    def render(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        rows = []
        kept = []
        for it in self.items:
            hid = it["id"] in self.hidden
            blk = self.chan_key(it) in self.blocked
            dl = self.is_downloaded(it["id"])
            pin = it["id"] in self.pinned
            if not pin:
                if (hid or blk) and not self.show_hidden.get():
                    continue
                if dl and self.hide_downloaded.get():
                    continue
                if len(rows) - len(kept) >= RESULTS:
                    continue
            else:
                kept.append(it["id"])
            rows.append((it, hid, blk, dl))
        rows.sort(key=lambda r: self.sort_key(r[0]), reverse=self.sort_rev)
        rows.sort(key=lambda r: r[0]["id"] not in self.pinned)
        for it, hid, blk, dl in rows:
            tags = []
            if hid or blk:
                tags.append("hidden")
            if dl:
                tags.append("downloaded")
            prefix = ("⊘ " if (hid or blk) else "") + ("✓ " if dl else "")
            extra = {}
            if self.show_thumbs.get():
                extra["image"] = self.thumbs.get(it["id"], self.blank_image())
            self.tree.insert("", "end", iid=it["id"], tags=tags, **extra, values=(
                "★" if it["id"] in self.pinned else "☆", it["rank"], prefix + it["title"],
                it["channel"], _("✔ verifiziert") if it.get("verified") else "",
                fmt_date(it["date"]), fmt_dur(it["duration"]), fmt_views(it["views"]),
            ))
        keep = [i for i in selected if self.tree.exists(i)]
        if keep:
            self.tree.selection_set(keep)
        self.shown = [r[0] for r in rows]
        self.ensure_dates()
        self.ensure_thumbs()

    def blank_image(self):
        if self.blank_thumb is None:
            self.blank_thumb = tk.PhotoImage(width=THUMB_W, height=THUMB_H)
        return self.blank_thumb

    def set_status(self, text):
        self.after(0, lambda: self.status.set(text))

    def pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get())
        if d:
            self.outdir.set(d)
            self.refresh_disk()
            self.save()
            self.render()

    def selected_items(self):
        return [self.by_id[i] for i in self.tree.selection() if i in self.by_id]

    def on_context(self, event):
        row = self.tree.identify_row(event.y)
        if row:
            if row not in self.tree.selection():
                self.tree.selection_set(row)
            self.ctx.tk_popup(event.x_root, event.y_root)

    def more_from_channel(self):
        sel = self.selected_items()
        if not sel:
            return
        it = sel[0]
        if not it["channel_id"]:
            self.status.set(_("Für diesen Kanal ist keine Kanal-ID bekannt. Nutze @handle oder die Kanal-URL."))
            return
        self.q.delete(0, "end")
        self.q.insert(0, f"https://www.youtube.com/channel/{it['channel_id']}")
        self.do_search()

    def toggle_hide(self):
        sel = self.selected_items()
        if not sel:
            return
        if all(it["id"] in self.hidden for it in sel):
            for it in sel:
                self.hidden.pop(it["id"], None)
                log("UNHIDE video", f"{it['id']} | {it['title']} | {it['channel']}")
            self.status.set(_("{n} Video(s) wieder eingeblendet.").format(n=len(sel)))
        else:
            n = 0
            for it in sel:
                if it["id"] not in self.hidden:
                    self.hidden[it["id"]] = {"title": it["title"], "channel": it["channel"], "at": now()}
                    log("HIDE video", f"{it['id']} | {it['title']} | {it['channel']}")
                    n += 1
            self.status.set(_("{n} Video(s) ausgeblendet, neue Treffer rücken nach.").format(n=n))
        self.save()
        self.render()

    def block_channels(self):
        sel = self.selected_items()
        if not sel:
            return
        names = []
        for it in sel:
            k = self.chan_key(it)
            if k not in self.blocked:
                self.blocked[k] = {"name": it["channel"], "at": now()}
                log("BLOCK channel", f"{k} | {it['channel']}")
                names.append(it["channel"])
        self.save()
        self.render()
        if names:
            self.status.set(_("Kanal blockiert: ") + ", ".join(dict.fromkeys(names)))

    def open_blocklist(self):
        if self.bl_win and self.bl_win.winfo_exists():
            self.bl_win.lift()
            self.refresh_blocklist()
            return
        win = tk.Toplevel(self)
        win.title(_("Blockliste"))
        win.geometry("820x500")
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        f1 = ttk.Frame(nb, padding=6)
        self.bl_ch = ttk.Treeview(f1, columns=("name", "key", "at"), show="headings",
                                  selectmode="extended")
        for c, t, w in (("name", _("Kanal"), 280), ("key", _("Kanal-ID"), 250), ("at", _("Geblockt am"), 150)):
            self.bl_ch.heading(c, text=t)
            self.bl_ch.column(c, width=w, anchor="w")
        self.bl_ch.pack(fill="both", expand=True)
        ttk.Button(f1, text=_("Ausgewählte Kanäle entsperren"),
                   command=self.unblock_channels).pack(anchor="e", pady=(6, 0))
        nb.add(f1, text=_("Kanäle"))

        f2 = ttk.Frame(nb, padding=6)
        self.bl_vid = ttk.Treeview(f2, columns=("title", "channel", "at"), show="headings",
                                   selectmode="extended")
        for c, t, w in (("title", _("Video"), 380), ("channel", _("Kanal"), 170), ("at", _("Ausgeblendet am"), 150)):
            self.bl_vid.heading(c, text=t)
            self.bl_vid.column(c, width=w, anchor="w")
        self.bl_vid.pack(fill="both", expand=True)
        ttk.Button(f2, text=_("Ausgewählte Videos wieder einblenden"),
                   command=self.unhide_videos).pack(anchor="e", pady=(6, 0))
        nb.add(f2, text=_("Videos"))

        f3 = ttk.Frame(nb, padding=6)
        self.bl_log = tk.Text(f3, wrap="none", state="disabled", height=10)
        lsb = ttk.Scrollbar(f3, orient="vertical", command=self.bl_log.yview)
        self.bl_log.configure(yscrollcommand=lsb.set)
        self.bl_log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        nb.add(f3, text=_("Log"))
        self.bl_win = win
        ttk.Button(win, text=_("Aktualisieren"), command=self.refresh_blocklist).pack(pady=(0, 8))
        self.theme_window(win)
        self.style_text(self.bl_log)
        self.refresh_blocklist()

    def refresh_blocklist(self):
        if not (self.bl_win and self.bl_win.winfo_exists()):
            return
        self.bl_ch.delete(*self.bl_ch.get_children())
        self.bl_ch_keys = sorted(self.blocked, key=lambda k: self.blocked[k].get("at", ""), reverse=True)
        for i, k in enumerate(self.bl_ch_keys):
            b = self.blocked[k]
            self.bl_ch.insert("", "end", iid=str(i), values=(b.get("name", "?"), k, b.get("at", "?")))
        self.bl_vid.delete(*self.bl_vid.get_children())
        self.bl_vid_ids = sorted(self.hidden, key=lambda v: self.hidden[v].get("at", ""), reverse=True)
        for i, v in enumerate(self.bl_vid_ids):
            h = self.hidden[v]
            title = h.get("title", "?")
            if title in ("?", ""):
                title = _("(Titel unbekannt) [{v}]").format(v=v)
            at = h.get("at", "?")
            if at in ("?", ""):
                at = _("vor dem Logging")
            channel = h.get("channel", "?")
            if channel in ("?", ""):
                channel = _("unbekannt")
            self.bl_vid.insert("", "end", iid=str(i), values=(title, channel, at))
        try:
            lines = LOG_FILE.read_text(encoding="utf-8").splitlines()[-1000:]
        except Exception:
            lines = []
        self.bl_log.configure(state="normal")
        self.bl_log.delete("1.0", "end")
        self.bl_log.insert("end", "\n".join(lines))
        self.bl_log.see("end")
        self.bl_log.configure(state="disabled")

    def unblock_channels(self):
        keys = [self.bl_ch_keys[int(i)] for i in self.bl_ch.selection()]
        for k in keys:
            b = self.blocked.pop(k, {})
            log("UNBLOCK channel", f"{k} | {b.get('name', '?')}")
        self.save()
        self.refresh_blocklist()
        self.render()

    def unhide_videos(self):
        ids = [self.bl_vid_ids[int(i)] for i in self.bl_vid.selection()]
        for v in ids:
            h = self.hidden.pop(v, {})
            log("UNHIDE video", f"{v} | {h.get('title', '?')} | {h.get('channel', '?')}")
        self.save()
        self.refresh_blocklist()
        self.render()

    def do_search(self, force=False):
        query = self.q.get().strip()
        if not query:
            return
        self.token += 1
        self.date_abort = False
        self.date_total = self.date_done = self.date_fail = 0
        spec = parse_query(query)
        entry = self.cache["searches"].get(spec["key"])
        if entry and not force and time.time() - entry["at"] < CACHE_TTL:
            self._show(entry["items"], self.token,
                       _("{l} · aus Cache ({a})").format(l=spec["label"], a=age_text(entry["at"])))
            return
        self.status.set(_("{l} … lädt").format(l=spec["label"]))
        threading.Thread(target=self._search, args=(spec, self.token), daemon=True).start()

    def _search(self, spec, token):
        try:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
                    "logger": QuietLogger()}
            if spec["kind"] == "channel":
                opts["playlistend"] = CHANNEL_POOL
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(spec["url"], download=False)
            entries = info.get("entries") or ([info] if info.get("id") else [])
            items = []
            terms = [t for t in spec["term"].lower().split() if t]
            for e in entries:
                if not e or not e.get("id"):
                    continue
                n = normalize(e, info if spec["kind"] == "channel" else None)
                if terms and not all(t in n["title"].lower() for t in terms):
                    continue
                items.append(n)
        except Exception as err:
            log("SEARCH FAIL", f"{spec['key']} | {short_err(err, 200)}")
            self.set_status(_("Fehler bei der Suche: {e}").format(e=short_err(err)))
            return
        self.after(0, lambda: self._finish_search(spec, items, token))

    def _finish_search(self, spec, items, token):
        if items:
            self.cache["searches"][spec["key"]] = {"at": time.time(), "items": items}
            self.save_cache()
        if token == self.token:
            self._show(items, token, _("{l} · frisch geladen").format(l=spec["label"]))

    def _show(self, raw_items, token, note):
        if token != self.token:
            return
        self.items = []
        seen = set()
        for n in raw_items:
            if n["id"] in seen:
                continue
            seen.add(n["id"])
            vid = n["id"]
            h = self.hidden.get(vid)
            if h and h.get("title") in ("?", ""):
                h["title"], h["channel"] = n["title"], n["channel"]
            self.items.append({
                **n,
                "rank": len(self.items) + 1,
                "date": n.get("date") or self.cache["dates"].get(vid) or None,
                "queued": False,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        for vid, p in self.pinned.items():
            if vid not in seen:
                self.items.append({
                    **p,
                    "rank": len(self.items) + 1,
                    "date": p.get("date") or self.cache["dates"].get(vid) or None,
                    "queued": False,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                })
        self.by_id = {it["id"]: it for it in self.items}
        self.save()
        self.refresh_disk()
        self.sort_col, self.sort_rev = "rank", False
        self.update_headings()
        self.render()
        missing = sum(1 for it in self.shown if it["date"] is None)
        self.status.set(_("{note} · {n} sichtbar (Pool {p})").format(note=note, n=len(self.shown), p=len(self.items))
                        + (_(" · Datum fehlt bei {m}").format(m=missing) if missing and self.fetch_dates.get() else ""))

    def ensure_dates(self):
        if not self.fetch_dates.get():
            return
        pending = [it for it in self.shown if it["date"] is None and not it["queued"]]
        for it in pending:
            it["queued"] = True
            self.date_total += 1
            self.dateq.put((self.token, it))

    def _date_worker(self):
        while True:
            token, it = self.dateq.get()
            if token != self.token:
                continue
            d, err_txt = "", ""
            if not self.date_abort:
                time.sleep(0.5)
                try:
                    opts = {**self.ydl_opts(), "skip_download": True, "noplaylist": True,
                            "ignore_no_formats_error": True, "check_formats": False}
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(it["url"], download=False, process=False)
                    d = (info or {}).get("upload_date") or ""
                    if not d and info and info.get("timestamp"):
                        d = datetime.fromtimestamp(info["timestamp"]).strftime("%Y%m%d")
                except Exception as err:
                    err_txt = short_err(err)
                    log("DATE FAIL", f"{it['id']} | {short_err(err, 200)}")
                    if is_bot_error(err):
                        self.date_abort = True
            self.after(0, lambda t=token, i=it, v=d, e=err_txt: self._set_date(t, i, v, e))

    def _set_date(self, token, it, d, err_txt):
        if token != self.token:
            return
        it["date"] = d
        self.date_done += 1
        if d:
            self.cache["dates"][it["id"]] = d
            self.cache_dirty += 1
            if self.cache_dirty >= 10:
                self.save_cache()
        else:
            self.date_fail += 1
            if err_txt:
                self.date_last_err = err_txt
        if self.tree.exists(it["id"]):
            self.tree.set(it["id"], "datum", fmt_date(d))
        if self.date_abort:
            self.status.set(_("YouTube verlangt einen Bot-Check. Wähle unten einen Browser bei "
                              "'Cookies aus Browser' (Datum bleibt bis dahin leer)."))
        elif self.date_done >= self.date_total:
            if self.cache_dirty:
                self.save_cache()
            if self.date_fail:
                self.status.set(_("Datum bei {n} Video(s) nicht ladbar. Grund: {r}").format(
                    n=self.date_fail, r=self.date_last_err or _("unbekannt (siehe Log)")))
            else:
                self.status.set(_("{n} Treffer sichtbar. Datum vollständig geladen.").format(n=len(self.shown)))
            if self.sort_col == "datum":
                self.render()
        else:
            self.status.set(_("Lade Upload-Datum … {d}/{t}").format(d=self.date_done, t=self.date_total))

    def do_download(self):
        picked = self.selected_items()
        if not picked:
            messagebox.showinfo(_("Hinweis"), _("Bitte erst ein oder mehrere Videos auswählen."))
            return
        self.enqueue(picked, dict(self.fmt), self.mode.get())

    def do_download_options(self):
        picked = self.selected_items()
        if not picked:
            messagebox.showinfo(_("Hinweis"), _("Bitte erst ein oder mehrere Videos auswählen."))
            return
        self.open_format_dialog(picked)

    def open_format_dialog(self, picked):
        if self.fmt_win and self.fmt_win.winfo_exists():
            self.fmt_win.destroy()
        win = tk.Toplevel(self)
        win.title(_("Download-Optionen"))
        win.transient(self)
        self.fmt_win = win
        self.theme_window(win)
        f = {**DEFAULT_FMT, **self.fmt}
        v_mode = tk.StringVar(value=self.mode.get())
        v_h = tk.StringVar(value=_("Beste") if not f["height"] else f"{f['height']}p")
        v_subs = tk.BooleanVar(value=bool(f["subs"]))
        v_langs = tk.StringVar(value=f["sub_langs"])
        v_chap = tk.BooleanVar(value=bool(f["chapters"]))
        v_fold = tk.BooleanVar(value=bool(f["channel_folder"]))
        v_def = tk.BooleanVar(value=False)

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        title = picked[0]["title"] if len(picked) == 1 else _("{n} Videos").format(n=len(picked))
        ttk.Label(body, text=title[:70], font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(body, text=_("Format")).grid(row=1, column=0, sticky="w")
        row = ttk.Frame(body)
        row.grid(row=1, column=1, columnspan=2, sticky="w", pady=3)
        for text, val in (("MKV", "mkv"), ("MP4", "mp4"), (_("Nur Audio"), "audio")):
            ttk.Radiobutton(row, text=text, value=val, variable=v_mode).pack(side="left", padx=(0, 8))
        ttk.Label(body, text=_("Max. Auflösung")).grid(row=2, column=0, sticky="w")
        labels = [_("Beste") if h == 0 else f"{h}p" for h in HEIGHTS]
        ttk.Combobox(body, textvariable=v_h, values=labels, state="readonly", width=10).grid(
            row=2, column=1, sticky="w", pady=3)
        ttk.Checkbutton(body, text=_("Untertitel einbetten, Sprachen:"), variable=v_subs).grid(
            row=3, column=0, sticky="w", pady=3)
        ttk.Entry(body, textvariable=v_langs, width=12).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Checkbutton(body, text=_("Kapitel einbetten"), variable=v_chap).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(body, text=_("Eigener Ordner pro Kanal"), variable=v_fold).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(body, text=_("Als Standard speichern"), variable=v_def).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))

        def go():
            label = v_h.get()
            h = 0 if label == _("Beste") else int(label.rstrip("p"))
            fmt = {"height": h, "subs": v_subs.get(), "sub_langs": v_langs.get().strip() or "de,en",
                   "chapters": v_chap.get(), "channel_folder": v_fold.get()}
            if v_def.get():
                self.fmt = dict(fmt)
                self.mode.set(v_mode.get())
                self.save()
            win.destroy()
            self.enqueue(picked, fmt, v_mode.get())

        btns = ttk.Frame(win, padding=(14, 0, 14, 14))
        btns.pack(fill="x")
        ttk.Button(btns, text=_("Herunterladen"), command=go).pack(side="right")
        ttk.Button(btns, text=_("Abbrechen"), command=win.destroy).pack(side="right", padx=6)
        win.bind("<Return>", lambda e: go())
        win.bind("<Escape>", lambda e: win.destroy())

    def enqueue(self, picked, fmt, mode):
        active = {j["item"]["id"] for j in self.jobs if j["status"] in ("queued", "running")}
        base = self.ydl_opts()
        outdir = str(Path(self.outdir.get()).expanduser())
        added = 0
        for it in picked:
            if it["id"] in active:
                continue
            self.job_seq += 1
            self.jobs.append({"n": self.job_seq, "item": it, "mode": mode, "fmt": dict(fmt),
                              "outdir": outdir, "base": base, "status": "queued", "pct": 0.0,
                              "speed": "", "msg": "", "cancel": False})
            added += 1
        if added:
            log("QUEUE", f"{added} Video(s) hinzugefügt")
            self.job_event.set()
        self.open_queue()
        self.update_queue_status()

    def _queue_worker(self):
        while True:
            self.job_event.clear()
            job = next((j for j in self.jobs if j["status"] == "queued"), None)
            if job is None:
                self.job_event.wait()
                continue
            while self.paused and not job["cancel"] and job["status"] == "queued":
                time.sleep(0.3)
            if job["status"] != "queued":
                continue
            self.run_job(job)
            self.after(0, self.update_queue_status)

    def run_job(self, job):
        it = job["item"]
        outdir = Path(job["outdir"])
        job["status"] = "running"
        try:
            outdir.mkdir(parents=True, exist_ok=True)
            opts = download_opts(job["base"], outdir, job["mode"], job["fmt"],
                                 lambda d, j=job: self._hook(j, d))
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(it["url"], download=True)
            good, reason, path = verify_download(info, it["id"], outdir)
            if good:
                job["status"], job["pct"], job["msg"] = "done", 100.0, Path(path).name
                self.history.add(it["id"])
                self.disk_ids.add(it["id"])
                log("DOWNLOAD", f"{it['id']} | {it['title']} | {it['channel']} | {path}")
                self.after(0, self.save)
                self.after(0, self.render)
            else:
                job["status"], job["msg"] = "failed", _("Prüfung fehlgeschlagen: {r}").format(r=reason)
                log("VERIFY FAIL", f"{it['id']} | {reason}")
        except Cancelled:
            job["status"], job["msg"] = "cancelled", ""
            log("CANCEL", f"{it['id']} | {it['title']}")
        except Exception as err:
            if job["cancel"]:
                job["status"], job["msg"] = "cancelled", ""
            else:
                job["status"], job["msg"] = "failed", short_err(err, 160)
                log("DOWNLOAD FAIL", f"{it['id']} | {short_err(err, 200)}")

    def _hook(self, job, d):
        if job["cancel"]:
            raise Cancelled()
        while self.paused:
            if job["cancel"]:
                raise Cancelled()
            time.sleep(0.3)
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                job["pct"] = min(100.0, (d.get("downloaded_bytes") or 0) * 100.0 / total)
            sp = d.get("speed")
            job["speed"] = f"{sp / 1048576:.1f} MB/s" if sp else ""
        elif d.get("status") == "finished":
            job["pct"], job["speed"], job["msg"] = 100.0, "", _("Verarbeite …")

    def update_queue_status(self):
        total = len(self.jobs)
        done = sum(1 for j in self.jobs if j["status"] in ("done", "failed", "cancelled"))
        failed = sum(1 for j in self.jobs if j["status"] == "failed")
        if not total:
            return
        text = _("Warteschlange: {d}/{t} fertig").format(d=done, t=total)
        if failed:
            text += _(", {f} fehlgeschlagen").format(f=failed)
        self.status.set(text)

    def job_state_text(self, j):
        if j["status"] == "running" and self.paused:
            return _("pausiert")
        return {"queued": _("wartet"), "running": _("lädt"), "done": _("fertig"),
                "failed": _("Fehler"), "cancelled": _("abgebrochen")}[j["status"]]

    def open_queue(self):
        if self.q_win and self.q_win.winfo_exists():
            self.q_win.lift()
            self.refresh_queue()
            return
        win = tk.Toplevel(self)
        win.title(_("Warteschlange"))
        win.geometry("760x380")
        win.transient(self)
        self.q_win = win
        self.theme_window(win)
        btns = ttk.Frame(win, padding=8)
        btns.pack(side="bottom", fill="x")
        self.q_bar = ttk.Progressbar(btns, mode="determinate", maximum=100, length=160)
        self.q_bar.pack(side="left")
        self.q_pause = ttk.Button(btns, text=_("Pause"), command=self.toggle_pause)
        self.q_pause.pack(side="right")
        ttk.Button(btns, text=_("Fertige entfernen"), command=self.clear_finished).pack(
            side="right", padx=6)
        ttk.Button(btns, text=_("Alle abbrechen"), command=lambda: self.cancel_jobs(all_jobs=True)).pack(
            side="right")
        ttk.Button(btns, text=_("Auswahl abbrechen"), command=self.cancel_jobs).pack(side="right", padx=6)
        cols = ("titel", "status", "fortschritt", "info")
        tv = ttk.Treeview(win, columns=cols, show="headings", selectmode="extended")
        for key, text, w, a in (("titel", _("Titel"), 300, "w"), ("status", _("Status"), 80, "w"),
                                ("fortschritt", _("Fortschritt"), 150, "w"), ("info", _("Info"), 190, "w")):
            tv.heading(key, text=text)
            tv.column(key, width=w, anchor=a, stretch=(key == "titel"))
        tv.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.q_tree = tv
        self.q_rows = {}
        self.apply_theme()
        self.queue_tick()

    def queue_tick(self):
        win = self.q_win
        if not (win and win.winfo_exists()):
            return
        self.refresh_queue()
        win.after(400, self.queue_tick)

    def refresh_queue(self):
        win = self.q_win
        if not (win and win.winfo_exists()):
            return
        tv = self.q_tree
        live = {str(j["n"]) for j in self.jobs}
        for iid in list(tv.get_children()):
            if iid not in live:
                tv.delete(iid)
        for j in self.jobs:
            iid = str(j["n"])
            filled = int(j["pct"] // 10)
            bar = "█" * filled + "░" * (10 - filled) + f" {j['pct']:.0f} %"
            info = j["speed"] or j["msg"]
            vals = (j["item"]["title"], self.job_state_text(j), bar, info)
            if tv.exists(iid):
                tv.item(iid, values=vals)
            else:
                tv.insert("", "end", iid=iid, values=vals)
        running = next((j for j in self.jobs if j["status"] == "running"), None)
        self.q_bar["value"] = running["pct"] if running else 0
        self.q_pause.configure(text=_("Fortsetzen") if self.paused else _("Pause"))

    def toggle_pause(self):
        self.paused = not self.paused
        log("QUEUE", "pausiert" if self.paused else "fortgesetzt")
        self.refresh_queue_once()

    def refresh_queue_once(self):
        if self.q_win and self.q_win.winfo_exists():
            self.q_pause.configure(text=_("Fortsetzen") if self.paused else _("Pause"))

    def cancel_jobs(self, all_jobs=False):
        if all_jobs:
            targets = list(self.jobs)
        else:
            sel = {int(i) for i in self.q_tree.selection()}
            targets = [j for j in self.jobs if j["n"] in sel]
        for j in targets:
            if j["status"] == "queued":
                j["status"] = "cancelled"
            elif j["status"] == "running":
                j["cancel"] = True
        self.update_queue_status()

    def clear_finished(self):
        self.jobs[:] = [j for j in self.jobs if j["status"] in ("queued", "running")]
        self.refresh_queue_once()
        if self.q_win and self.q_win.winfo_exists():
            for iid in list(self.q_tree.get_children()):
                if iid not in {str(j["n"]) for j in self.jobs}:
                    self.q_tree.delete(iid)

    def watch_selected_channel(self):
        picked = self.selected_items()
        if not picked:
            return
        for it in picked:
            if it.get("channel_id"):
                self.add_watch(f"https://www.youtube.com/channel/{it['channel_id']}/videos", it["channel"])
            else:
                self.status.set(_("Für diesen Kanal fehlt die Kanal-ID. Bitte über @handle hinzufügen."))

    def add_watch(self, url, name=""):
        key = url.lower()
        if key in self.watch:
            self.status.set(_("Kanal wird bereits beobachtet."))
            return
        self.status.set(_("Kanal wird hinzugefügt …"))
        threading.Thread(target=self._add_watch, args=(key, url, name), daemon=True).start()

    def _add_watch(self, key, url, name):
        try:
            info, entries = fetch_flat(url, WATCH_LIMIT, self.ydl_opts())
        except Exception as err:
            log("WATCH FAIL", f"{url} | {short_err(err, 200)}")
            self.set_status(_("Kanal konnte nicht hinzugefügt werden: {e}").format(e=short_err(err)))
            return
        title = clean_text(info.get("channel") or info.get("uploader") or info.get("title")) or name or url
        ids = [e["id"] for e in entries]

        def done():
            self.watch[key] = {"name": title, "url": url, "seen": ids[:WATCH_SEEN_MAX], "new": [],
                               "checked": time.time()}
            log("WATCH", f"{title} | {url}")
            self.save()
            self.refresh_watch()
            self.status.set(_("Kanal beobachtet: {n}").format(n=title))

        self.after(0, done)

    def open_watch(self):
        if self.w_win and self.w_win.winfo_exists():
            self.w_win.lift()
            return
        win = tk.Toplevel(self)
        win.title(_("Beobachtete Kanäle"))
        win.geometry("640x400")
        win.transient(self)
        self.w_win = win
        self.theme_window(win)
        top = ttk.Frame(win, padding=8)
        top.pack(fill="x")
        self.w_entry = ttk.Entry(top)
        self.w_entry.pack(side="left", fill="x", expand=True)
        self.w_entry.bind("<Return>", lambda e: self.add_watch_from_entry())
        ttk.Button(top, text=_("Hinzufügen (@handle oder URL)"), command=self.add_watch_from_entry).pack(
            side="left", padx=(6, 0))
        btns = ttk.Frame(win, padding=8)
        btns.pack(side="bottom", fill="x")
        ttk.Button(btns, text=_("Alle prüfen"), command=self.check_watch).pack(side="left")
        ttk.Button(btns, text=_("Entfernen"), command=self.remove_watch).pack(side="right")
        ttk.Button(btns, text=_("Neue Videos anzeigen"), command=self.show_watch_new).pack(side="right", padx=6)
        cols = ("kanal", "neu", "geprueft")
        tv = ttk.Treeview(win, columns=cols, show="headings", selectmode="extended")
        for key, text, w, a in (("kanal", _("Kanal"), 320, "w"), ("neu", _("Neu"), 70, "e"),
                                ("geprueft", _("Zuletzt geprüft"), 170, "w")):
            tv.heading(key, text=text)
            tv.column(key, width=w, anchor=a, stretch=(key == "kanal"))
        tv.pack(fill="both", expand=True, padx=8)
        self.w_tree = tv
        self.apply_theme()
        self.refresh_watch()

    def add_watch_from_entry(self):
        spec = parse_query(self.w_entry.get())
        if spec["kind"] != "channel":
            self.status.set(_("Bitte @handle oder eine Kanal-URL eingeben."))
            return
        self.w_entry.delete(0, "end")
        self.add_watch(spec["url"])

    def refresh_watch(self):
        if not (self.w_win and self.w_win.winfo_exists()):
            return
        tv = self.w_tree
        tv.delete(*tv.get_children())
        for key, w in self.watch.items():
            checked = datetime.fromtimestamp(w["checked"]).strftime("%d.%m.%Y %H:%M") if w.get("checked") else "–"
            tv.insert("", "end", iid=key, values=(w["name"], len(w.get("new", [])), checked))

    def watch_keys(self, selected_only=False):
        if selected_only:
            return [k for k in self.w_tree.selection() if k in self.watch]
        return list(self.watch)

    def check_watch(self):
        keys = self.watch_keys()
        if not keys:
            self.status.set(_("Keine Kanäle in der Beobachtungsliste."))
            return
        self.status.set(_("Prüfe {n} Kanal/Kanäle …").format(n=len(keys)))
        threading.Thread(target=self._check_watch, args=(keys, self.ydl_opts()), daemon=True).start()

    def _check_watch(self, keys, base):
        total_new, errors = 0, 0
        for n, key in enumerate(keys):
            w = self.watch.get(key)
            if not w:
                continue
            if n:
                time.sleep(1.0)
            try:
                info, entries = fetch_flat(w["url"], WATCH_LIMIT, base)
            except Exception as err:
                errors += 1
                log("WATCH FAIL", f"{w['url']} | {short_err(err, 200)}")
                if is_bot_error(err):
                    break
                continue
            seen = set(w["seen"])
            known_new = {x["id"] for x in w.get("new", [])}
            fresh = []
            for e in entries:
                if e["id"] in seen or e["id"] in known_new:
                    continue
                fresh.append(normalize(e, info))
            w["new"] = (fresh + w.get("new", []))[:WATCH_NEW_MAX]
            w["checked"] = time.time()
            total_new += len(fresh)
        msg = _("Prüfung beendet: {n} neue Videos").format(n=total_new)
        if errors:
            msg += _(", {e} Fehler (siehe Log)").format(e=errors)

        def done():
            self.save()
            self.refresh_watch()
            self.status.set(msg)

        self.after(0, done)

    def remove_watch(self):
        keys = self.watch_keys(selected_only=True)
        for k in keys:
            w = self.watch.pop(k, {})
            log("UNWATCH", f"{w.get('name', '?')} | {k}")
        self.save()
        self.refresh_watch()

    def show_watch_new(self):
        keys = self.watch_keys(selected_only=True) or self.watch_keys()
        items = []
        for k in keys:
            items.extend(self.watch[k].get("new", []))
        if not items:
            self.status.set(_("Keine neuen Videos. Erst „Alle prüfen“ ausführen."))
            return
        for k in keys:
            w = self.watch[k]
            w["seen"] = ([x["id"] for x in w.get("new", [])] + w["seen"])[:WATCH_SEEN_MAX]
            w["new"] = []
        self.save()
        self.refresh_watch()
        self.token += 1
        self.date_abort = False
        self.date_total = self.date_done = self.date_fail = 0
        self._show(items, self.token, _("Neue Videos beobachteter Kanäle"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ytpick",
        description="Search YouTube, pick videos and download them in best quality.",
    )
    parser.add_argument("--version", action="version", version=f"ytpick {__version__}")
    parser.parse_args(argv)
    App().mainloop()


if __name__ == "__main__":
    main()
