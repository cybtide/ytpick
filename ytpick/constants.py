"""Dateipfade, Grenzwerte, Spalten und Farbschemata."""

import re
import sys
from pathlib import Path


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
               "channel_folder": False, "embed": False, "cut_start": None, "cut_end": None}
SAVED_FMT_KEYS = ("height", "subs", "sub_langs", "chapters", "channel_folder", "embed")
DEFAULT_WINDOW = ("01:00", "06:00")
FROZEN = bool(getattr(sys, "frozen", False))
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
HISTORY_MAX = 30
SHUTDOWN_SECONDS = 60
DEFAULT_PIN_LIST = "Merkliste"
CLIP_RE = re.compile(r"^https?://(?:(?:www|m|music)\.)?(?:youtube\.com/\S+|youtu\.be/\S+)$")
NAME_PRESETS = {
    "title": "%(title).150B [%(id)s]",
    "channel_title": "%(channel)s - %(title).150B [%(id)s]",
    "rank_title": "{rank} - %(title).150B [%(id)s]",
}
NAME_PRESET_LABELS = {
    "title": "Titel [ID]",
    "channel_title": "Kanal - Titel [ID]",
    "rank_title": "Nr. - Titel [ID]",
}
DONE_ACTIONS = ["none", "sound", "shutdown"]
DONE_ACTION_LABELS = {"none": "Nichts", "sound": "Ton", "shutdown": "Ton und PC herunterfahren"}
DATE_RANGES = [("alle", 0), ("7 Tage", 7), ("30 Tage", 30), ("1 Jahr", 365)]
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
DEFAULT_VISIBLE = ["pin", "titel", "kanal", "datum", "dauer"]

# Dunkles Schema "Kommandozentrale": ruhige, leicht bläuliche Flächen, ein Akzent.
# "bg" ist die Fläche der Tabelle und des Fensters, "bar" die der Leisten,
# Rahmen sind unsichtbar (gleiche Farbe wie die Fläche).
DARK = {"bg": "#14161c", "bar": "#181b22", "panel": "#222733", "field": "#1d212b",
        "header": "#181b22", "fg": "#e6e9f0", "muted": "#9aa2b4", "sel": "#252c40",
        "selfg": "#e6e9f0", "hover": "#2a3040", "accent": "#7aa2ff", "border": "#181b22",
        "dl": "#6f7789", "hid": "#565d6e", "ok": "#5fd37c", "bad": "#ff6b6b"}
LIGHT = {"bg": "#ffffff", "bar": "#f3f3f3", "panel": "#e6e6e6", "field": "#ffffff",
         "header": "#f3f3f3", "fg": "#1b1b1b", "muted": "#666666", "sel": "#dbe7fd",
         "selfg": "#1b1b1b", "hover": "#d6d6d6", "accent": "#2563eb", "border": "#f3f3f3",
         "dl": "#8a8a8a", "hid": "#b5b5b5", "ok": "#1a8f3c", "bad": "#c62828"}
VIDEO_MODES = ("mkv", "mp4")
MUSIC_MODES = ("mp3", "audio")
