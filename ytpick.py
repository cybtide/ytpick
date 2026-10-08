import argparse
import json
import locale
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
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

__version__ = "0.3.0"

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
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
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
          "Die Spalte Status zeigt ein Häkchen bei von YouTube verifizierten Kanälen.\n"
          "   Mit der Merkliste oben sortierst du gemerkte Videos in eigene Listen. Kopierte YouTube-Links "
          "bietet ytpick oben im Fenster an, das Suchfeld merkt sich deine letzten Suchen."),
    ("p", "Playlists, Filter, Ausschnitt\n"
          "   Eine Playlist-URL (youtube.com/playlist?list=...) lädt die ganze Playlist in die Liste, "
          "\"Alle sichtbaren laden\" legt sie in die Warteschlange. Filter nach Dauer, Zeitraum und "
          "verifizierten Kanälen stehen über der Liste. Unter \"Optionen…\" lädst du auch nur einen "
          "Ausschnitt, bettest Cover und Metadaten ein oder wählst MP3."),
    ("p", "4. Blockliste\n"
          "   Zeigt geblockte Kanäle und ausgeblendete Videos mit Zeitpunkt, Entsperren und Log."),
    ("p", "5. Bot-Check von YouTube?\n"
          "   Unten bei \"Cookies aus Browser\" einen Browser wählen, in dem du bei YouTube eingeloggt bist."),
    ("p", "6. Suche oder Download geht nicht mehr?\n"
          "   YouTube ändert sich oft. \"yt-dlp aktualisieren\" (unten in diesem Fenster) lädt die neueste Version, "
          "danach ytpick neu starten."),
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
          "The Status column shows a check mark for channels verified by YouTube.\n"
          "   The pin list at the top sorts pinned videos into your own lists. Copied YouTube links "
          "are offered at the top of the window, and the search box remembers your latest searches."),
    ("p", "Playlists, filters, clips\n"
          "   A playlist URL (youtube.com/playlist?list=...) loads the whole playlist into the list, "
          "\"Download all visible\" puts it in the queue. Filters for duration, period and verified "
          "channels sit above the list. \"Options…\" lets you download just a clip, embed cover and "
          "metadata or choose MP3."),
    ("p", "4. Blocklist\n"
          "   Shows blocked channels and hidden videos with timestamps, unblocking and the log."),
    ("p", "5. YouTube bot check?\n"
          "   Choose a browser at \"Cookies from browser\" in which you are signed in to YouTube."),
    ("p", "6. Search or download stopped working?\n"
          "   YouTube changes often. \"Update yt-dlp\" (at the bottom of this window) fetches the latest version; "
          "restart ytpick afterwards."),
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
    "Werkzeuge": "Tools",
    "Mehr anzeigen (+{n})": "Show more (+{n})",
    "{n} sichtbar (Pool {p})": "{n} visible (pool {p})",
    "{n} ausgeblendet/geblockt": "{n} hidden/blocked",
    "{n} bereits geladen (ausgeblendet)": "{n} already downloaded (hidden)",
    "{n} durch Filter": "{n} filtered out",
    "Warteschlange beim Start eines Downloads öffnen": "Open queue window when a download starts",
    "Filter": "Filters",
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
    "YouTube verlangt eine Anmeldung": "YouTube requires sign-in",
    "Verlauf": "History",
    "Verlauf…": "History…",
    "Bereits geladen": "Already downloaded",
    "Zeitpunkt": "Time",
    "Ungültiger Wert bei Geschwindigkeit oder Zeitfenster (Format hh:mm).":
        "Invalid value for speed or time window (format hh:mm).",
    "Audio": "Audio",
    "Alle sichtbaren laden": "Download all visible",
    "YouTube verlangt einen Bot-Check. {b} ist auf diesem Computer installiert.\n\nCookies aus {b} verwenden? Du musst dort bei YouTube angemeldet sein.":
        "YouTube asks for a bot check. {b} is installed on this computer.\n\nUse cookies from {b}? You have to be signed in to YouTube there.",
    "Playlist {t}": "Playlist {t}",
    "Dauer (Min.) von": "Duration (min) from",
    "bis": "to",
    "Zeitraum": "Period",
    "Nur verifizierte Kanäle": "Verified channels only",
    "Filter zurücksetzen": "Reset filters",
    "Max. Geschwindigkeit (MB/s, 0 = unbegrenzt)": "Max. speed (MB/s, 0 = unlimited)",
    "Downloads nur im Zeitfenster starten (hh:mm)": "Start downloads only within time window (hh:mm)",
    "Cover und Metadaten einbetten": "Embed cover and metadata",
    "Ausschnitt (Start – Ende, z.B. 1:20 – 3:45)": "Clip (start – end, e.g. 1:20 – 3:45)",
    "Ausschnitt": "Clip",
    "Ungültiger Ausschnitt. Beispiel: 1:20 und 3:45.": "Invalid clip. Example: 1:20 and 3:45.",
    "{n} Video(s) wurden schon geladen: {names}\n\nJa = trotzdem laden, Nein = überspringen, Abbrechen = nichts tun.":
        "{n} video(s) were already downloaded: {names}\n\nYes = download anyway, No = skip, Cancel = do nothing.",
    "wartet auf Zeitfenster {a}–{b}": "waiting for time window {a}–{b}",
    "Datei öffnen": "Open file",
    "Ordner zeigen": "Show folder",
    "Aus Verlauf entfernen": "Remove from history",
    "{n} Videos in die Warteschlange legen?": "Add {n} videos to the queue?",
    "Datei nicht mehr vorhanden: {f}": "File no longer exists: {f}",
    "alle": "all",
    "7 Tage": "7 days",
    "30 Tage": "30 days",
    "1 Jahr": "1 year",
    "Statistik…": "Statistics…",
    "Statistik": "Statistics",
    "Übersicht": "Overview",
    "Kennzahl": "Metric",
    "Wert": "Value",
    "Downloads": "Downloads",
    "Monat": "Month",
    "Downloads gesamt": "Total downloads",
    "Videos (MKV/MP4)": "Videos (MKV/MP4)",
    "Musik und Audio (MP3/Audio)": "Music and audio (MP3/audio)",
    "Heute": "Today",
    "Letzte 7 Tage": "Last 7 days",
    "Letzte 30 Tage": "Last 30 days",
    "Gesamtgröße": "Total size",
    "Gesamtlaufzeit": "Total duration",
    "Erkannte Dateien ohne Verlaufseintrag": "Detected files without history entry",
    "Blockierte Kanäle": "Blocked channels",
    "Ausgeblendete Videos": "Hidden videos",
    "Monate": "Months",
    "Merkliste:": "Pin list:",
    "Alle": "All",
    "In Merkliste verschieben…": "Move to pin list…",
    "In Merkliste verschieben": "Move to pin list",
    "Neue Merkliste": "New pin list",
    "Name der Merkliste:": "Name of the pin list:",
    "Ignorieren": "Dismiss",
    "Anzeigen": "Show",
    "YouTube-Link in der Zwischenablage: {u}": "YouTube link in clipboard: {u}",
    "Warteschlange fertig: {n} Download(s)": "Queue finished: {n} download(s)",
    "Warteschlange fertig, aber es gab Fehler. Der PC wird nicht heruntergefahren.":
        "Queue finished, but there were errors. The PC will not be shut down.",
    "PC herunterfahren": "Shut down PC",
    "Alle Downloads sind fertig. Der PC wird in {s} Sekunden heruntergefahren.":
        "All downloads are finished. The PC will shut down in {s} seconds.",
    "Herunterfahren fehlgeschlagen: {e}": "Shutdown failed: {e}",
    "Dateiname": "File name",
    "Titel [ID]": "Title [ID]",
    "Kanal - Titel [ID]": "Channel - Title [ID]",
    "Nr. - Titel [ID]": "No. - Title [ID]",
    "Nach der Warteschlange": "After the queue",
    "Nichts": "Nothing",
    "Ton": "Sound",
    "Ton und PC herunterfahren": "Sound and shut down PC",
    "Zwischenablage auf YouTube-Links prüfen": "Check clipboard for YouTube links",
    "Video {t}": "Video {t}",
    "In der .exe ist yt-dlp fest eingebaut. Lade die neueste ytpick-Version von GitHub.":
        "yt-dlp is built into the .exe. Download the latest ytpick version from GitHub.",
    "yt-dlp aktualisieren": "Update yt-dlp",
    "yt-dlp wird aktualisiert …": "Updating yt-dlp …",
    "Aktualisierung fehlgeschlagen: {e}": "Update failed: {e}",
    "yt-dlp ist aktuell (Version {v}).": "yt-dlp is up to date (version {v}).",
    "yt-dlp aktualisiert: {a} → {b}. Bitte ytpick neu starten.": "yt-dlp updated: {a} → {b}. Please restart ytpick.",
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
        if LANG == "en":
            return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
        return f"{d[6:8]}.{d[4:6]}.{d[0:4]}"
    return "?"


def fmt_views(v):
    if not v:
        return "?"
    return f"{v:,}" if LANG == "en" else f"{v:,}".replace(",", ".")


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


def parse_clock(text):
    h, m = text.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(text)
    return h * 60 + m


def in_window(now_minutes, start, end):
    if start == end:
        return True
    if start < end:
        return start <= now_minutes < end
    return now_minutes >= start or now_minutes < end


def detect_browsers():
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    candidates = {
        "firefox": [roaming / "Mozilla" / "Firefox", home / ".mozilla" / "firefox",
                    home / "Library" / "Application Support" / "Firefox"],
        "chrome": [local / "Google" / "Chrome" / "User Data", home / ".config" / "google-chrome",
                   home / "Library" / "Application Support" / "Google" / "Chrome"],
        "edge": [local / "Microsoft" / "Edge" / "User Data", home / ".config" / "microsoft-edge"],
        "brave": [local / "BraveSoftware" / "Brave-Browser" / "User Data",
                  home / ".config" / "BraveSoftware" / "Brave-Browser"],
    }
    return [name for name, paths in candidates.items() if any(p.exists() for p in paths)]


VIDEO_MODES = ("mkv", "mp4")
MUSIC_MODES = ("mp3", "audio")


def fmt_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def fmt_hours(sec):
    sec = int(sec or 0)
    return f"{sec // 3600}:{sec % 3600 // 60:02d} h"


def compute_stats(downloads, history, today=None):
    today = today or datetime.now()
    by_mode, channels, months = Counter(), Counter(), Counter()
    size = duration = day = week = month = 0
    for rec in downloads.values():
        by_mode[rec.get("mode", "?")] += 1
        channels[rec.get("channel") or "?"] += 1
        size += rec.get("size") or 0
        duration += rec.get("duration") or 0
        try:
            at = datetime.strptime(rec.get("at", ""), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        months[at.strftime("%Y-%m")] += 1
        age = (today.date() - at.date()).days
        day += age == 0
        week += 0 <= age < 7
        month += 0 <= age < 30
    last = []
    y, m = today.year, today.month
    for _i in range(12):
        last.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    last.reverse()
    return {
        "total": len(downloads),
        "videos": sum(by_mode[k] for k in VIDEO_MODES),
        "music": sum(by_mode[k] for k in MUSIC_MODES),
        "without_record": len(set(history) - set(downloads)),
        "by_mode": dict(by_mode),
        "size": size,
        "duration": duration,
        "today": day,
        "week": week,
        "month": month,
        "channels": channels.most_common(15),
        "months": [(k, months.get(k, 0)) for k in last],
    }


def shutdown_command():
    if sys.platform == "win32":
        return ["shutdown", "/s", "/t", "0"]
    if sys.platform == "darwin":
        return ["osascript", "-e", 'tell application "System Events" to shut down']
    return ["systemctl", "poweroff"]


def open_path(path, reveal=False):
    path = str(path)
    try:
        if sys.platform == "win32":
            if reveal:
                subprocess.Popen(["explorer", "/select,", path])
            else:
                os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if reveal else ["open", path])
        else:
            subprocess.Popen(["xdg-open", str(Path(path).parent) if reveal else path])
    except Exception:
        pass


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
        self.fmt = {**DEFAULT_FMT, **{k: v for k, v in s.get("fmt", {}).items() if k in SAVED_FMT_KEYS}}
        self.downloads = st.get("downloads", {})
        self.rate_mb = float(s.get("rate_limit", 0) or 0)
        self.window_on = bool(s.get("window_on", False))
        self.window_start = s.get("window_start", DEFAULT_WINDOW[0])
        self.window_end = s.get("window_end", DEFAULT_WINDOW[1])
        self.cookie_offered = False
        self.limit = RESULTS
        self.h_win = None
        self.s_win = None
        self.pin_view = None
        self.search_hist = [q for q in st.get("search_history", []) if isinstance(q, str)][:HISTORY_MAX]
        self.pin_lists = set(st.get("pin_lists", []))
        self.name_preset = s.get("name_preset", "title") if s.get("name_preset") in NAME_PRESETS else "title"
        self.done_action = s.get("done_action", "sound") if s.get("done_action") in DONE_ACTIONS else "sound"
        self.watch_clipboard = bool(s.get("watch_clipboard", True))
        self.open_queue_on_add = bool(s.get("open_queue_on_add", False))
        self.clip_last = ""
        self.clip_bar = None
        self.shutdown_win = None
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
        self.f_min = tk.StringVar(value="")
        self.f_max = tk.StringVar(value="")
        self.f_verified = tk.BooleanVar(value=False)
        self.f_range = tk.StringVar(value=_(DATE_RANGES[0][0]))
        self.pin_view = tk.StringVar(value=_("Alle"))
        self.show_hidden = tk.BooleanVar(value=False)
        self.hide_downloaded = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value=_("Suchbegriff, @Kanal oder Kanal-URL eingeben und Enter drücken."))

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.top_frame = top
        self.q = ttk.Combobox(top, values=self.search_hist)
        self.q.pack(side="left", fill="x", expand=True)
        self.q.bind("<Return>", lambda e: self.do_search())
        self.q.bind("<Shift-Return>", lambda e: self.do_search(force=True))
        self.q.focus()
        ttk.Button(top, text=_("Suchen"), command=self.do_search).pack(side="left", padx=(6, 0))
        ttk.Button(top, text=_("Ohne Cache"), command=lambda: self.do_search(force=True)).pack(
            side="left", padx=(6, 0))

        tools = ttk.Frame(self, padding=(8, 4, 8, 0))
        tools.pack(fill="x")
        self.tools_frame = tools
        self.filter_btn = ttk.Button(tools, command=self.toggle_filters)
        self.filter_btn.pack(side="left")
        wz = ttk.Menubutton(tools, text=_("Werkzeuge") + " ▾")
        wz.pack(side="left", padx=6)
        self.tool_menu = tk.Menu(wz, tearoff=0)
        wz["menu"] = self.tool_menu
        for label, cmd in ((_("Beobachtete Kanäle…"), self.open_watch), (_("Verlauf…"), self.open_history),
                           (_("Statistik…"), self.open_stats), (_("Blockliste…"), self.open_blocklist),
                           (None, None), (_("Datum erneut versuchen"), self.retry_dates),
                           (_("Hilfe"), self.show_readme_dialog)):
            if label is None:
                self.tool_menu.add_separator()
            else:
                self.tool_menu.add_command(label=label, command=cmd)
        ttk.Button(tools, text=_("Warteschlange…"), command=self.open_queue).pack(side="left")
        ttk.Button(tools, text=_("Einstellungen…"), command=self.open_settings).pack(side="right")
        self.pin_box = ttk.Combobox(tools, textvariable=self.pin_view, state="readonly", width=14)
        self.pin_box.pack(side="right", padx=(0, 12))
        self.pin_box.bind("<<ComboboxSelected>>", lambda e: self.sync_pins())
        ttk.Button(tools, text="+", width=3, command=self.new_pin_list).pack(side="right", padx=(0, 4))
        ttk.Label(tools, text=_("Merkliste:")).pack(side="right", padx=(12, 4))

        fl = ttk.Frame(self, padding=(8, 4, 8, 0))
        self.filter_frame = fl
        self.filters_open = False
        ttk.Label(fl, text=_("Dauer (Min.) von")).pack(side="left")
        ttk.Entry(fl, textvariable=self.f_min, width=5).pack(side="left", padx=4)
        ttk.Label(fl, text=_("bis")).pack(side="left")
        ttk.Entry(fl, textvariable=self.f_max, width=5).pack(side="left", padx=4)
        ttk.Label(fl, text=_("Zeitraum")).pack(side="left", padx=(12, 4))
        ttk.Combobox(fl, textvariable=self.f_range, values=[_(lbl) for lbl, days in DATE_RANGES],
                     state="readonly", width=9).pack(side="left")
        ttk.Checkbutton(fl, text=_("Nur verifizierte Kanäle"), variable=self.f_verified).pack(
            side="left", padx=12)
        ttk.Checkbutton(fl, text=_("Ausgeblendete/Geblockte anzeigen"), variable=self.show_hidden,
                        command=self.render).pack(side="left")
        ttk.Checkbutton(fl, text=_("Bereits geladene ausblenden"), variable=self.hide_downloaded,
                        command=self.render).pack(side="left", padx=12)
        ttk.Button(fl, text=_("Filter zurücksetzen"), command=self.reset_filters).pack(side="left")
        for v in (self.f_min, self.f_max, self.f_verified, self.f_range):
            v.trace_add("write", lambda *a: self.render())
        for v in (self.f_min, self.f_max, self.f_verified, self.f_range, self.show_hidden, self.hide_downloaded):
            v.trace_add("write", lambda *a: self.update_filter_label())
        self.update_filter_label()

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
        self.ctx.add_command(label=_("In Merkliste verschieben…"), command=self.move_to_list)
        self.ctx.add_command(label=_("Mehr von diesem Kanal"), command=self.more_from_channel)
        self.ctx.add_separator()
        self.ctx.add_command(label=_("Video ausblenden/einblenden"), command=self.toggle_hide)
        self.ctx.add_command(label=_("Kanal blockieren"), command=self.block_channels)
        self.update_headings()
        self.refresh_pin_lists()

        opt = ttk.Frame(self, padding=(8, 4))
        opt.pack(fill="x")
        for text, val in ((_("Video MKV (beste Qualität)"), "mkv"),
                          (_("Video MP4"), "mp4"), (_("Nur Audio"), "audio"), ("MP3", "mp3")):
            ttk.Radiobutton(opt, text=text, value=val, variable=self.mode).pack(side="left", padx=4)
        ttk.Button(opt, text=_("Ordner…"), command=self.pick_dir).pack(side="right")
        ttk.Entry(opt, textvariable=self.outdir, width=40).pack(side="right", padx=6)

        bot = ttk.Frame(self, padding=8)
        bot.pack(fill="x")
        ttk.Label(bot, textvariable=self.status).pack(side="left")
        ttk.Button(bot, text=_("Auswahl herunterladen"), command=self.do_download).pack(side="right")
        ttk.Button(bot, text=_("Optionen…"), command=self.do_download_options).pack(side="right", padx=6)
        ttk.Button(bot, text=_("Alle sichtbaren laden"), command=self.enqueue_all).pack(side="right")
        ttk.Button(bot, text=_("Mehr anzeigen (+{n})").format(n=RESULTS), command=self.show_more).pack(
            side="right", padx=(0, 6))

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
        try:
            self.clip_last = self.clipboard_get().strip()
        except tk.TclError:
            self.clip_last = ""
        self.after(1500, self.poll_clipboard)
        if self.pinned:
            self.token += 1
            self._show([], self.token, _("Gemerkte Videos"))
        if self.show_readme.get():
            self.after(400, self.show_readme_dialog)

    def set_icon(self):
        assets = BASE_DIR / "assets"
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
        for menu in (self.ctx, self.tool_menu):
            menu.configure(bg=p["panel"], fg=p["fg"], activebackground=p["sel"],
                           activeforeground="#ffffff", bd=0)
        st.configure("TMenubutton", background=p["panel"], foreground=p["fg"], arrowcolor=p["fg"],
                     padding=(8, 3))
        st.map("TMenubutton", background=[("active", p["sel"])], foreground=[("active", "#ffffff")])
        set_titlebar(self, self.dark.get())
        if self.bl_win and self.bl_win.winfo_exists():
            self.theme_window(self.bl_win)
            if self.bl_log:
                self.style_text(self.bl_log)
        for w in (self.q_win, self.w_win, self.fmt_win, self.h_win, self.s_win):
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
        self.upd_btn = ttk.Button(btns, text=_("yt-dlp aktualisieren"), command=self.update_ytdlp)
        self.upd_btn.pack(side="right", padx=8)

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

    def update_ytdlp(self):
        self.upd_btn.state(["disabled"])
        self.status.set(_("yt-dlp wird aktualisiert …"))
        threading.Thread(target=self._update_ytdlp, args=(installed_ytdlp_version(),), daemon=True).start()

    def _update_ytdlp(self, before):
        try:
            after = upgrade_ytdlp()
        except Exception as err:
            log("YTDLP UPDATE FAIL", short_err(err, 200))
            self.set_status(_("Aktualisierung fehlgeschlagen: {e}").format(e=short_err(err)))
            self.after(0, self.enable_update_button)
            return
        log("YTDLP UPDATE", f"{before} -> {after}")
        if after == before:
            msg = _("yt-dlp ist aktuell (Version {v}).").format(v=after)
        else:
            msg = _("yt-dlp aktualisiert: {a} → {b}. Bitte ytpick neu starten.").format(a=before, b=after)
        self.set_status(msg)
        self.after(0, self.enable_update_button)

    def enable_update_button(self):
        if self.readme_win and self.readme_win.winfo_exists():
            self.upd_btn.state(["!disabled"])

    def save(self):
        data = {
            "hidden": self.hidden,
            "blocked_channels": self.blocked,
            "downloaded": sorted(self.history),
            "pinned": self.pinned,
            "watch": self.watch,
            "downloads": self.downloads,
            "search_history": self.search_hist,
            "pin_lists": sorted(self.pin_lists),
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
                "fmt": {k: self.fmt.get(k) for k in SAVED_FMT_KEYS},
                "rate_limit": self.rate_mb,
                "window_on": self.window_on,
                "window_start": self.window_start,
                "window_end": self.window_end,
                "name_preset": self.name_preset,
                "done_action": self.done_action,
                "watch_clipboard": self.watch_clipboard,
                "open_queue_on_add": self.open_queue_on_add,
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

    def toggle_filters(self):
        self.filters_open = not self.filters_open
        if self.filters_open:
            self.filter_frame.pack(fill="x", after=self.tools_frame)
        else:
            self.filter_frame.pack_forget()
        self.update_filter_label()

    def update_filter_label(self):
        active = bool(self.f_min.get().strip() or self.f_max.get().strip() or self.f_verified.get()
                      or self.f_range.get() != _(DATE_RANGES[0][0]) or self.show_hidden.get()
                      or self.hide_downloaded.get())
        arrow = "▴" if self.filters_open else "▾"
        self.filter_btn.configure(text=_("Filter") + (" •" if active else "") + " " + arrow)

    def apply_columns(self):
        show = [k for k in self.col_order if k in self.col_visible]
        self.tree.configure(displaycolumns=show)

    def open_settings(self):
        if self.set_win and self.set_win.winfo_exists():
            self.set_win.lift()
            return
        win = tk.Toplevel(self)
        win.title(_("Einstellungen"))
        win.geometry("620x830")
        win.transient(self)
        self.set_win = win
        self.set_order = list(self.col_order)
        self.set_vis = set(self.col_visible)
        self.set_thumbs = tk.BooleanVar(value=self.show_thumbs.get())
        self.set_rate = tk.StringVar(value=f"{self.rate_mb:g}")
        self.set_win_on = tk.BooleanVar(value=self.window_on)
        self.set_win_a = tk.StringVar(value=self.window_start)
        self.set_win_b = tk.StringVar(value=self.window_end)
        self.set_name = tk.StringVar(value=_(NAME_PRESET_LABELS[self.name_preset]))
        self.set_done = tk.StringVar(value=_(DONE_ACTION_LABELS[self.done_action]))
        self.set_clip = tk.BooleanVar(value=self.watch_clipboard)
        self.set_open_q = tk.BooleanVar(value=self.open_queue_on_add)
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
        ttk.Label(extra, text=_("Max. Geschwindigkeit (MB/s, 0 = unbegrenzt)")).grid(
            row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(extra, textvariable=self.set_rate, width=6).grid(row=2, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Checkbutton(extra, text=_("Downloads nur im Zeitfenster starten (hh:mm)"),
                        variable=self.set_win_on).grid(row=3, column=0, sticky="w", pady=(8, 0))
        win_row = ttk.Frame(extra)
        win_row.grid(row=3, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Entry(win_row, textvariable=self.set_win_a, width=6).pack(side="left")
        ttk.Label(win_row, text="–").pack(side="left", padx=4)
        ttk.Entry(win_row, textvariable=self.set_win_b, width=6).pack(side="left")
        ttk.Label(extra, text=_("Dateiname")).grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(extra, textvariable=self.set_name, values=[_(v) for v in NAME_PRESET_LABELS.values()],
                     state="readonly", width=22).grid(row=4, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Label(extra, text=_("Nach der Warteschlange")).grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(extra, textvariable=self.set_done, values=[_(v) for v in DONE_ACTION_LABELS.values()],
                     state="readonly", width=22).grid(row=5, column=1, sticky="w", padx=6, pady=(8, 0))
        ttk.Checkbutton(extra, text=_("Zwischenablage auf YouTube-Links prüfen"), variable=self.set_clip).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(extra, text=_("Cookies aus Browser:")).grid(row=7, column=0, sticky="w", pady=(8, 0))
        cb = ttk.Combobox(extra, textvariable=self.cookies, values=BROWSERS, state="readonly", width=10)
        cb.grid(row=7, column=1, sticky="w", padx=6, pady=(8, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_cookies_changed())
        ttk.Checkbutton(extra, text=_("Upload-Datum nachladen"), variable=self.fetch_dates,
                        command=self.on_fetch_dates_toggle).grid(row=8, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(extra, text=_("Dark Mode"), variable=self.dark,
                        command=self.on_theme_toggle).grid(row=9, column=0, sticky="w", pady=(8, 0))
        ttk.Checkbutton(extra, text=_("Warteschlange beim Start eines Downloads öffnen"),
                        variable=self.set_open_q).grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))
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
        try:
            rate = float(self.set_rate.get().replace(",", ".") or 0)
            if rate < 0:
                raise ValueError("rate")
            parse_clock(self.set_win_a.get())
            parse_clock(self.set_win_b.get())
        except ValueError:
            messagebox.showerror(_("Einstellungen"),
                                 _("Ungültiger Wert bei Geschwindigkeit oder Zeitfenster (Format hh:mm)."),
                                 parent=self.set_win)
            return
        name_by_label = {_(v): k for k, v in NAME_PRESET_LABELS.items()}
        done_by_label = {_(v): k for k, v in DONE_ACTION_LABELS.items()}
        self.name_preset = name_by_label.get(self.set_name.get(), "title")
        self.done_action = done_by_label.get(self.set_done.get(), "sound")
        self.watch_clipboard = self.set_clip.get()
        self.open_queue_on_add = self.set_open_q.get()
        self.rate_mb = rate
        self.window_on = self.set_win_on.get()
        self.window_start = self.set_win_a.get().strip()
        self.window_end = self.set_win_b.get().strip()
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

    def pin_list_names(self):
        names = {p.get("list") or DEFAULT_PIN_LIST for p in self.pinned.values()}
        return sorted(names | self.pin_lists | {DEFAULT_PIN_LIST})

    def refresh_pin_lists(self):
        values = [_("Alle")] + self.pin_list_names()
        self.pin_box.configure(values=values)
        if self.pin_view.get() not in values:
            self.pin_view.set(_("Alle"))

    def in_view(self, vid):
        p = self.pinned.get(vid)
        if p is None:
            return False
        view = self.pin_view.get()
        return view == _("Alle") or (p.get("list") or DEFAULT_PIN_LIST) == view

    def target_list(self):
        view = self.pin_view.get()
        return DEFAULT_PIN_LIST if view == _("Alle") else view

    def new_pin_list(self):
        name = simpledialog.askstring(_("Neue Merkliste"), _("Name der Merkliste:"), parent=self)
        name = (name or "").strip()
        if name:
            self.pin_lists.add(name)
            self.refresh_pin_lists()
            self.pin_view.set(name)
            self.save()
            self.sync_pins()

    def move_to_list(self):
        picked = self.selected_items()
        if not picked:
            return
        name = simpledialog.askstring(_("In Merkliste verschieben"), _("Name der Merkliste:"),
                                      initialvalue=self.target_list(), parent=self)
        name = (name or "").strip()
        if not name:
            return
        self.pin_lists.add(name)
        for it in picked:
            self.pinned[it["id"]] = {**self.snapshot(it), "list": name}
        self.refresh_pin_lists()
        self.save()
        self.sync_pins()

    @staticmethod
    def snapshot(it):
        return {k: it.get(k) for k in ("id", "title", "channel", "channel_id", "duration",
                                       "views", "date", "verified")}

    def pinned_item(self, vid, p):
        return {
            **{k: v for k, v in p.items() if k != "list"},
            "rank": len(self.items) + 1,
            "date": p.get("date") or self.cache["dates"].get(vid) or None,
            "queued": False,
            "from_pin": True,
            "url": f"https://www.youtube.com/watch?v={vid}",
        }

    def sync_pins(self):
        self.items = [it for it in self.items if not it.get("from_pin")]
        have = {it["id"] for it in self.items}
        for vid, p in self.pinned.items():
            if vid not in have and self.in_view(vid):
                self.items.append(self.pinned_item(vid, p))
        self.by_id = {it["id"]: it for it in self.items}
        self.render()

    def toggle_pin(self):
        ids = [it["id"] for it in self.selected_items()]
        if ids:
            self.set_pin(ids)

    def set_pin(self, ids):
        mark = not all(i in self.pinned for i in ids)
        for i in ids:
            it = self.by_id[i]
            if mark:
                self.pinned[i] = {**self.snapshot(it), "list": self.target_list()}
                log("PIN", f"{i} | {it['title']} | {it['channel']}")
            else:
                self.pinned.pop(i, None)
                log("UNPIN", f"{i} | {it['title']} | {it['channel']}")
        self.refresh_pin_lists()
        self.save()
        self.render()

    def reset_filters(self):
        self.f_min.set("")
        self.f_max.set("")
        self.f_verified.set(False)
        self.f_range.set(_(DATE_RANGES[0][0]))

    @staticmethod
    def minutes(var):
        try:
            return float(var.get().replace(",", "."))
        except ValueError:
            return 0.0

    def passes_filters(self, it):
        dur = it.get("duration") or 0
        lo, hi = self.minutes(self.f_min), self.minutes(self.f_max)
        if lo and dur < lo * 60:
            return False
        if hi and dur and dur > hi * 60:
            return False
        if self.f_verified.get() and not it.get("verified"):
            return False
        days = {_(lbl): d for lbl, d in DATE_RANGES}.get(self.f_range.get(), 0)
        date = it.get("date")
        if days and date and len(date) == 8:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            if date < cutoff:
                return False
        return True

    def show_more(self):
        if not self.items:
            return
        self.limit += RESULTS
        self.render()
        self.status.set(_("{n} sichtbar (Pool {p})").format(n=len(self.shown), p=len(self.items))
                        + self.explain_hidden())

    def explain_hidden(self):
        if self.shown or not self.items:
            return ""
        hidden = dl = filt = 0
        for it in self.items:
            if self.in_view(it["id"]):
                continue
            if (it["id"] in self.hidden or self.chan_key(it) in self.blocked) and not self.show_hidden.get():
                hidden += 1
            elif self.is_downloaded(it["id"]) and self.hide_downloaded.get():
                dl += 1
            elif not self.passes_filters(it):
                filt += 1
        parts = []
        if hidden:
            parts.append(_("{n} ausgeblendet/geblockt").format(n=hidden))
        if dl:
            parts.append(_("{n} bereits geladen (ausgeblendet)").format(n=dl))
        if filt:
            parts.append(_("{n} durch Filter").format(n=filt))
        return (" · " + ", ".join(parts)) if parts else ""

    def filters_active(self):
        return bool(self.minutes(self.f_min) or self.minutes(self.f_max) or self.f_verified.get()
                    or self.f_range.get() != _(DATE_RANGES[0][0]))

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
            return 0 if self.in_view(it["id"]) else 1
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
            pin = self.in_view(it["id"])
            if not pin:
                if (hid or blk) and not self.show_hidden.get():
                    continue
                if dl and self.hide_downloaded.get():
                    continue
                if not self.passes_filters(it):
                    continue
                if len(rows) - len(kept) >= self.limit:
                    continue
            else:
                kept.append(it["id"])
            rows.append((it, hid, blk, dl))
        rows.sort(key=lambda r: self.sort_key(r[0]), reverse=self.sort_rev)
        rows.sort(key=lambda r: not self.in_view(r[0]["id"]))
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

    def remember_query(self, query):
        self.search_hist = ([query] + [x for x in self.search_hist if x != query])[:HISTORY_MAX]
        self.q.configure(values=self.search_hist)

    def do_search(self, force=False):
        query = self.q.get().strip()
        if not query:
            return
        self.token += 1
        self.date_abort = False
        self.date_total = self.date_done = self.date_fail = 0
        spec = parse_query(query)
        self.remember_query(query)
        entry = self.cache["searches"].get(spec["key"])
        if entry and not force and time.time() - entry["at"] < CACHE_TTL:
            self._show(entry["items"], self.token,
                       _("{l} · aus Cache ({a})").format(l=spec["label"], a=age_text(entry["at"])),
                       CHANNEL_POOL if spec["kind"] == "playlist" else RESULTS)
            return
        self.status.set(_("{l} … lädt").format(l=spec["label"]))
        threading.Thread(target=self._search, args=(spec, self.token), daemon=True).start()

    def _search(self, spec, token):
        try:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
                    "logger": QuietLogger()}
            if spec["kind"] in ("channel", "playlist"):
                opts["playlistend"] = CHANNEL_POOL
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(spec["url"], download=False)
            entries = info.get("entries") or ([info] if info.get("id") else [])
            items = []
            terms = [t for t in spec["term"].lower().split() if t]
            for e in entries:
                if not e or not e.get("id"):
                    continue
                n = normalize(e, info if spec["kind"] in ("channel", "playlist") else None)
                if terms and not all(t in n["title"].lower() for t in terms):
                    continue
                items.append(n)
        except Exception as err:
            log("SEARCH FAIL", f"{spec['key']} | {short_err(err, 200)}")
            self.set_status(_("Fehler bei der Suche: {e}").format(e=short_err(err)))
            if is_bot_error(err):
                self.after(0, self.offer_cookies)
            return
        self.after(0, lambda: self._finish_search(spec, items, token))

    def _finish_search(self, spec, items, token):
        if items:
            self.cache["searches"][spec["key"]] = {"at": time.time(), "items": items}
            self.save_cache()
        if token == self.token:
            self._show(items, token, _("{l} · frisch geladen").format(l=spec["label"]),
                       CHANNEL_POOL if spec["kind"] == "playlist" else RESULTS)

    def _show(self, raw_items, token, note, limit=RESULTS):
        if token != self.token:
            return
        self.limit = limit
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
            if vid not in seen and self.in_view(vid):
                self.items.append(self.pinned_item(vid, p))
        self.by_id = {it["id"]: it for it in self.items}
        self.save()
        self.refresh_disk()
        self.sort_col, self.sort_rev = "rank", False
        self.update_headings()
        self.render()
        missing = sum(1 for it in self.shown if it["date"] is None)
        self.status.set(_("{note} · {n} sichtbar (Pool {p})").format(note=note, n=len(self.shown), p=len(self.items))
                        + self.explain_hidden()
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
            self.offer_cookies()
        elif self.date_done >= self.date_total:
            if self.cache_dirty:
                self.save_cache()
            if self.date_fail:
                self.status.set(_("Datum bei {n} Video(s) nicht ladbar. Grund: {r}").format(
                    n=self.date_fail, r=self.date_last_err or _("unbekannt (siehe Log)")))
            else:
                self.status.set(_("{n} Treffer sichtbar. Datum vollständig geladen.").format(n=len(self.shown)))
            if self.sort_col == "datum" or self.filters_active():
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
        v_embed = tk.BooleanVar(value=bool(f["embed"]))
        v_cut_a = tk.StringVar(value="")
        v_cut_b = tk.StringVar(value="")

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        title = picked[0]["title"] if len(picked) == 1 else _("{n} Videos").format(n=len(picked))
        ttk.Label(body, text=title[:70], font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(body, text=_("Format")).grid(row=1, column=0, sticky="w")
        row = ttk.Frame(body)
        row.grid(row=1, column=1, columnspan=2, sticky="w", pady=3)
        for text, val in (("MKV", "mkv"), ("MP4", "mp4"), (_("Nur Audio"), "audio"), ("MP3", "mp3")):
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
        ttk.Checkbutton(body, text=_("Cover und Metadaten einbetten"), variable=v_embed).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Label(body, text=_("Ausschnitt (Start – Ende, z.B. 1:20 – 3:45)")).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))
        cut = ttk.Frame(body)
        cut.grid(row=8, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Entry(cut, textvariable=v_cut_a, width=9).pack(side="left")
        ttk.Label(cut, text="–").pack(side="left", padx=6)
        ttk.Entry(cut, textvariable=v_cut_b, width=9).pack(side="left")
        ttk.Checkbutton(body, text=_("Als Standard speichern"), variable=v_def).grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(10, 0))

        def go():
            label = v_h.get()
            h = 0 if label == _("Beste") else int(label.rstrip("p"))
            try:
                a, b = parse_time(v_cut_a.get()), parse_time(v_cut_b.get())
                if a is not None and b is not None and b <= a:
                    raise ValueError("range")
            except ValueError:
                messagebox.showerror(_("Ausschnitt"), _("Ungültiger Ausschnitt. Beispiel: 1:20 und 3:45."),
                                     parent=win)
                return
            fmt = {"height": h, "subs": v_subs.get(), "sub_langs": v_langs.get().strip() or "de,en",
                   "chapters": v_chap.get(), "channel_folder": v_fold.get(), "embed": v_embed.get(),
                   "cut_start": a, "cut_end": b}
            if v_def.get():
                self.fmt = {**DEFAULT_FMT, **{k: fmt[k] for k in SAVED_FMT_KEYS}}
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

    def mode_label(self, mode):
        return {"mkv": "MKV", "mp4": "MP4", "audio": _("Audio"), "mp3": "MP3"}.get(mode, mode)

    def describe_download(self, vid):
        rec = self.downloads.get(vid)
        if not rec:
            return _("unbekannt")
        h = rec.get("height") or 0
        return self.mode_label(rec.get("mode", "?")) + (f" ≤{h}p" if h else "")

    def enqueue_all(self):
        items = list(self.shown)
        if not items:
            return
        if len(items) > 20 and not messagebox.askyesno(
                _("Alle sichtbaren laden"), _("{n} Videos in die Warteschlange legen?").format(n=len(items))):
            return
        self.enqueue(items, dict(self.fmt), self.mode.get())

    def enqueue(self, picked, fmt, mode, ask=True):
        active = {j["item"]["id"] for j in self.jobs if j["status"] in ("queued", "running")}
        picked = [it for it in picked if it["id"] not in active]
        dups = [it for it in picked if self.is_downloaded(it["id"])]
        if dups and ask:
            names = ", ".join(f"{d['title'][:30]} ({self.describe_download(d['id'])})" for d in dups[:3])
            answer = messagebox.askyesnocancel(
                _("Bereits geladen"),
                _("{n} Video(s) wurden schon geladen: {names}\n\nJa = trotzdem laden, Nein = überspringen, "
                  "Abbrechen = nichts tun.").format(n=len(dups), names=names))
            if answer is None:
                return
            if answer is False:
                skip = {d["id"] for d in dups}
                picked = [it for it in picked if it["id"] not in skip]
        base = self.ydl_opts()
        if self.rate_mb > 0:
            base["ratelimit"] = int(self.rate_mb * 1048576)
        outdir = str(Path(self.outdir.get()).expanduser())
        for it in picked:
            self.job_seq += 1
            self.jobs.append({"n": self.job_seq, "item": it, "mode": mode,
                              "fmt": {**fmt, "name": self.name_preset},
                              "outdir": outdir, "base": base, "status": "queued", "pct": 0.0,
                              "speed": "", "msg": "", "cancel": False})
        if picked:
            log("QUEUE", f"{len(picked)} Video(s) hinzugefügt")
            self.job_event.set()
        if self.open_queue_on_add:
            self.open_queue()
        self.update_queue_status()

    def in_schedule(self):
        try:
            start, end = parse_clock(self.window_start), parse_clock(self.window_end)
        except ValueError:
            return True
        n = datetime.now()
        return in_window(n.hour * 60 + n.minute, start, end)

    def _queue_worker(self):
        while True:
            self.job_event.clear()
            job = next((j for j in self.jobs if j["status"] == "queued"), None)
            if job is None:
                self.job_event.wait()
                continue
            while self.paused and not job["cancel"] and job["status"] == "queued":
                time.sleep(0.3)
            while (self.window_on and not self.in_schedule() and not job["cancel"]
                   and job["status"] == "queued"):
                job["msg"] = _("wartet auf Zeitfenster {a}–{b}").format(a=self.window_start, b=self.window_end)
                time.sleep(5)
            job["msg"] = ""
            if job["status"] != "queued" or job["cancel"]:
                continue
            self.run_job(job)
            self.after(0, self.update_queue_status)
            self.after(0, self.on_queue_finished)

    def run_job(self, job):
        it = job["item"]
        outdir = Path(job["outdir"])
        job["status"] = "running"
        try:
            outdir.mkdir(parents=True, exist_ok=True)
            opts = download_opts(job["base"], outdir, job["mode"], job["fmt"],
                                 lambda d, j=job: self._hook(j, d), it.get("rank"))
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(it["url"], download=True)
            good, reason, path = verify_download(info, it["id"], outdir)
            if good:
                job["status"], job["pct"], job["msg"] = "done", 100.0, Path(path).name
                self.history.add(it["id"])
                self.disk_ids.add(it["id"])
                try:
                    file_size = Path(path).stat().st_size
                except OSError:
                    file_size = 0
                self.downloads[it["id"]] = {
                    "title": it["title"], "channel": it["channel"], "mode": job["mode"],
                    "height": job["fmt"].get("height", 0), "at": now(), "file": path,
                    "size": file_size, "duration": it.get("duration") or 0}
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
                if is_bot_error(err):
                    self.after(0, self.offer_cookies)

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

    def offer_cookies(self):
        if self.cookie_offered or self.cookies.get() != "keine":
            return
        found = detect_browsers()
        if not found:
            return
        self.cookie_offered = True
        name = found[0]
        if messagebox.askyesno(
                _("YouTube verlangt eine Anmeldung"),
                _("YouTube verlangt einen Bot-Check. {b} ist auf diesem Computer installiert.\n\n"
                  "Cookies aus {b} verwenden? Du musst dort bei YouTube angemeldet sein.").format(b=name)):
            self.cookies.set(name)
            self.on_cookies_changed()

    def poll_clipboard(self):
        try:
            if self.watch_clipboard and self.focus_displayof() is not None:
                try:
                    text = self.clipboard_get().strip()
                except tk.TclError:
                    text = ""
                if text and text != self.clip_last and len(text) < 300 and CLIP_RE.match(text):
                    self.clip_last = text
                    self.show_clip_bar(text)
        finally:
            self.after(1500, self.poll_clipboard)

    def show_clip_bar(self, url):
        self.clip_url = url
        if self.clip_bar is None:
            bar = ttk.Frame(self, padding=(8, 4))
            self.clip_label = ttk.Label(bar)
            self.clip_label.pack(side="left", fill="x", expand=True)
            ttk.Button(bar, text=_("Ignorieren"), command=self.hide_clip_bar).pack(side="right")
            ttk.Button(bar, text=_("Anzeigen"), command=self.use_clip_url).pack(side="right", padx=6)
            self.clip_bar = bar
        self.clip_label.configure(text=_("YouTube-Link in der Zwischenablage: {u}").format(u=url[:70]))
        self.clip_bar.pack(fill="x", before=self.top_frame)

    def hide_clip_bar(self):
        if self.clip_bar is not None:
            self.clip_bar.pack_forget()

    def use_clip_url(self):
        self.q.delete(0, "end")
        self.q.insert(0, self.clip_url)
        self.hide_clip_bar()
        self.do_search()

    def beep(self):
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep()
            else:
                self.bell()
        except Exception:
            pass

    def on_queue_finished(self):
        if any(j["status"] in ("queued", "running") for j in self.jobs):
            return
        fresh = [j for j in self.jobs if j["status"] == "done" and not j.get("notified")]
        if not fresh:
            return
        for j in fresh:
            j["notified"] = True
        failed = any(j["status"] == "failed" for j in self.jobs)
        self.status.set(_("Warteschlange fertig: {n} Download(s)").format(n=len(fresh)))
        if self.done_action in ("sound", "shutdown"):
            self.beep()
        if self.done_action == "shutdown":
            if failed:
                self.status.set(_("Warteschlange fertig, aber es gab Fehler. Der PC wird nicht heruntergefahren."))
            else:
                self.start_shutdown_countdown()

    def start_shutdown_countdown(self):
        if self.shutdown_win and self.shutdown_win.winfo_exists():
            return
        win = tk.Toplevel(self)
        win.title(_("PC herunterfahren"))
        win.transient(self)
        self.shutdown_win = win
        self.theme_window(win)
        self.shutdown_left = SHUTDOWN_SECONDS
        label = ttk.Label(win, padding=20)
        label.pack()
        ttk.Button(win, text=_("Abbrechen"), command=win.destroy).pack(pady=(0, 16))
        self.shutdown_label = label

        def tick():
            if not win.winfo_exists():
                return
            if self.shutdown_left <= 0:
                self.run_shutdown()
                win.destroy()
                return
            label.configure(text=_("Alle Downloads sind fertig. Der PC wird in {s} Sekunden heruntergefahren.").format(
                s=self.shutdown_left))
            self.shutdown_left -= 1
            win.after(1000, tick)

        tick()

    def run_shutdown(self):
        log("SHUTDOWN", "queue finished")
        try:
            subprocess.Popen(shutdown_command())
        except Exception as err:
            self.status.set(_("Herunterfahren fehlgeschlagen: {e}").format(e=short_err(err)))

    def open_stats(self):
        if self.s_win and self.s_win.winfo_exists():
            self.s_win.lift()
            self.refresh_stats()
            return
        win = tk.Toplevel(self)
        win.title(_("Statistik"))
        win.geometry("560x520")
        win.transient(self)
        self.s_win = win
        self.theme_window(win)
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.s_trees = {}
        for key, title, cols in (
                ("sum", _("Übersicht"), (("name", _("Kennzahl"), 320), ("value", _("Wert"), 180))),
                ("chan", _("Kanäle"), (("name", _("Kanal"), 320), ("value", _("Downloads"), 100))),
                ("month", _("Monate"), (("name", _("Monat"), 120), ("value", _("Downloads"), 100),
                                        ("bar", "", 260)))):
            frame = ttk.Frame(nb, padding=6)
            tv = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", selectmode="browse")
            for c, t, w in cols:
                tv.heading(c, text=t)
                tv.column(c, width=w, anchor="e" if c == "value" else "w", stretch=(c == "name"))
            tv.pack(fill="both", expand=True)
            nb.add(frame, text=title)
            self.s_trees[key] = tv
        ttk.Button(win, text=_("Aktualisieren"), command=self.refresh_stats).pack(pady=(0, 8))
        self.apply_theme()
        self.refresh_stats()

    def refresh_stats(self):
        if not (self.s_win and self.s_win.winfo_exists()):
            return
        st = compute_stats(self.downloads, self.history)
        for tv in self.s_trees.values():
            tv.delete(*tv.get_children())
        rows = [
            (_("Downloads gesamt"), st["total"]),
            (_("Videos (MKV/MP4)"), st["videos"]),
            (_("Musik und Audio (MP3/Audio)"), st["music"]),
        ]
        for mode in ("mkv", "mp4", "mp3", "audio"):
            if st["by_mode"].get(mode):
                rows.append(("   " + self.mode_label(mode), st["by_mode"][mode]))
        rows += [
            (_("Heute"), st["today"]),
            (_("Letzte 7 Tage"), st["week"]),
            (_("Letzte 30 Tage"), st["month"]),
            (_("Gesamtgröße"), fmt_size(st["size"])),
            (_("Gesamtlaufzeit"), fmt_hours(st["duration"])),
            (_("Erkannte Dateien ohne Verlaufseintrag"), st["without_record"]),
            (_("Blockierte Kanäle"), len(self.blocked)),
            (_("Ausgeblendete Videos"), len(self.hidden)),
            (_("Gemerkte Videos"), len(self.pinned)),
            (_("Beobachtete Kanäle"), len(self.watch)),
        ]
        for i, (name, value) in enumerate(rows):
            self.s_trees["sum"].insert("", "end", iid=str(i), values=(name, value))
        for i, (name, count) in enumerate(st["channels"]):
            self.s_trees["chan"].insert("", "end", iid=str(i), values=(name, count))
        peak = max([c for _m, c in st["months"]] + [1])
        for i, (name, count) in enumerate(st["months"]):
            bar = "█" * round(count * 24 / peak)
            self.s_trees["month"].insert("", "end", iid=str(i), values=(name, count, bar))

    def open_history(self):
        if self.h_win and self.h_win.winfo_exists():
            self.h_win.lift()
            self.refresh_history()
            return
        win = tk.Toplevel(self)
        win.title(_("Verlauf"))
        win.geometry("820x420")
        win.transient(self)
        self.h_win = win
        self.theme_window(win)
        btns = ttk.Frame(win, padding=8)
        btns.pack(side="bottom", fill="x")
        ttk.Button(btns, text=_("Datei öffnen"), command=lambda: self.open_history_file(False)).pack(side="left")
        ttk.Button(btns, text=_("Ordner zeigen"), command=lambda: self.open_history_file(True)).pack(
            side="left", padx=6)
        ttk.Button(btns, text=_("Aus Verlauf entfernen"), command=self.remove_history).pack(side="right")
        cols = ("at", "titel", "kanal", "format")
        tv = ttk.Treeview(win, columns=cols, show="headings", selectmode="extended")
        for key, text, w, a in (("at", _("Zeitpunkt"), 140, "w"), ("titel", _("Titel"), 330, "w"),
                                ("kanal", _("Kanal"), 150, "w"), ("format", _("Format"), 100, "w")):
            tv.heading(key, text=text)
            tv.column(key, width=w, anchor=a, stretch=(key == "titel"))
        tv.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        tv.bind("<Double-1>", lambda e: self.open_history_file(False))
        self.h_tree = tv
        self.apply_theme()
        self.refresh_history()

    def refresh_history(self):
        if not (self.h_win and self.h_win.winfo_exists()):
            return
        tv = self.h_tree
        tv.delete(*tv.get_children())
        for vid, rec in sorted(self.downloads.items(), key=lambda kv: kv[1].get("at", ""), reverse=True):
            tv.insert("", "end", iid=vid, values=(rec.get("at", "?"), rec.get("title", "?"),
                                                  rec.get("channel", "?"), self.describe_download(vid)))

    def open_history_file(self, reveal):
        for vid in self.h_tree.selection()[:1]:
            f = Path(self.downloads.get(vid, {}).get("file", ""))
            if f.exists():
                open_path(f, reveal)
            else:
                self.status.set(_("Datei nicht mehr vorhanden: {f}").format(f=f.name))

    def remove_history(self):
        for vid in self.h_tree.selection():
            self.downloads.pop(vid, None)
            self.history.discard(vid)
            log("UNHISTORY", vid)
        self.save()
        self.refresh_history()
        self.render()

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
        total_new, errors, bot_seen = 0, 0, False
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
                    bot_seen = True
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
            if bot_seen:
                self.offer_cookies()

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
