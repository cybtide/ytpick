"""Sprache, Übersetzungen und Hilfetexte."""

import locale
import os


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


HELP_TEXT = [
    ("h", "Kurzanleitung"),
    ("p", "1. Suchen\n"
          "   Suchbegriff eingeben und Enter drücken. Für einen Kanal: @handle oder Kanal-URL, "
          "optional mit Filterwort (z.B. @channelname training).\n"
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
          "verifizierten Kanälen stehen hinter dem Knopf \"Filter\". Unter \"Optionen…\" lädst du auch nur einen "
          "Ausschnitt, bettest Cover und Metadaten ein oder wählst MP3."),
    ("p", "4. Blockliste\n"
          "   Zeigt geblockte Kanäle und ausgeblendete Videos mit Zeitpunkt, Entsperren und Log."),
    ("p", "5. Bot-Check von YouTube?\n"
          "   Unter \"Einstellungen\" bei \"Cookies aus Browser\" einen Browser wählen, in dem du bei YouTube eingeloggt bist."),
    ("p", "6. Suche oder Download geht nicht mehr?\n"
          "   YouTube ändert sich oft. \"yt-dlp aktualisieren\" (unten in diesem Fenster) lädt die neueste Version, "
          "danach ytpick neu starten."),
    ("p", "Nur Inhalte herunterladen, die du herunterladen darfst."),
]


HELP_TEXT_EN = [
    ("h", "Quick guide"),
    ("p", "1. Search\n"
          "   Type a search term and press Enter. For a channel use @handle or the channel URL, "
          "optionally followed by a filter word (e.g. @channelname training).\n"
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
          "channels are behind the \"Filters\" button. \"Options…\" lets you download just a clip, embed cover and "
          "metadata or choose MP3."),
    ("p", "4. Blocklist\n"
          "   Shows blocked channels and hidden videos with timestamps, unblocking and the log."),
    ("p", "5. YouTube bot check?\n"
          "   In \"Settings\" choose a browser at \"Cookies from browser\" in which you are signed in to YouTube."),
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
    "YouTube verlangt einen Bot-Check. Wähle in den Einstellungen einen Browser bei 'Cookies aus Browser' (Datum bleibt bis dahin leer).":
        "YouTube asks for a bot check. Choose a browser at 'Cookies from browser' in the settings (dates stay empty until then).",
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
    "🪄 Accio Video!\nGleis 9¾ ist frei für deine Downloads.": "🪄 Accio Video!\nPlatform 9¾ is clear for your downloads.",
    "🔷 Nur der HSV.\nRaute im Herzen, Video im Korb.": "🔷 Nur der HSV.\nDiamond in the heart, video in the basket.",
    "🦅 Go Hawks!\nDer 12. Mann sucht mit.": "🦅 Go Hawks!\nThe 12th Man is searching along.",
    "⚓ Moin!\nHamburg, das Tor zur Welt, auch für deine Downloads.": "⚓ Moin!\nHamburg, gateway to the world, and to your downloads.",
    "☕ Regen, Kaffee und Space Needle.\nPerfektes Download-Wetter.": "☕ Rain, coffee and the Space Needle.\nPerfect download weather.",
    "Nach Updates suchen": "Check for updates",
    "Suche nach Updates …": "Checking for updates …",
    "Updates": "Updates",
    "Du hast die neueste Version ({v}).": "You have the latest version ({v}).",
    "Die Suche nach Updates ist fehlgeschlagen: {e}": "Checking for updates failed: {e}",
    "Später": "Later",
    "Diese Version überspringen": "Skip this version",
    "Download-Seite öffnen": "Open download page",
    "Neue Version {v} verfügbar (installiert: {c}).": "New version {v} available (installed: {c}).",
    "Neue Version {v} verfügbar.": "New version {v} available.",
    "Beim Start nach neuer Version suchen (GitHub)": "Check for a new version at startup (GitHub)",
    " · keine weiteren Treffer": " · no more results",
    "{l} … lädt weitere Treffer": "{l} … loading more results",
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


def is_english():
    return LANG == "en"


def set_language(lang):
    global LANG
    LANG = lang
