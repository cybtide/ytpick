<p align="center">
  <img src="assets/icon.png" alt="ytpick" width="112">
</p>

<h1 align="center">ytpick</h1>

<p align="center">
  Desktop-Anwendung zum Suchen, Auswählen und Herunterladen von YouTube-Videos in bester Qualität.<br>
  Grafische Oberfläche für <a href="https://github.com/yt-dlp/yt-dlp">yt-dlp</a>.
</p>

## Funktionen

- Suche mit bis zu 50 sichtbaren Treffern aus einem Pool von 150, sortierbar nach jeder Spalte
- Kanalsuche per `@handle` oder Kanal-URL, optional mit Titelfilter
- Videos ausblenden, Kanäle blockieren; Blockliste mit Zeitstempel, Entsperren und Protokoll
- Bereits geladene Videos werden erkannt und markiert
- Cache für Suchergebnisse und Upload-Daten, schont die Abfragelimits von YouTube
- Download als MKV (beste Qualität), MP4 oder nur Audio
- Dark Mode, Kurzanleitung und Systemcheck beim Start
- Anmeldung über die Cookies eines installierten Browsers

## Voraussetzungen

| Komponente | Zweck |
| --- | --- |
| Python 3.10 oder neuer mit tkinter | Programm (Linux: Paket `python3-tk`) |
| [ffmpeg](https://ffmpeg.org) | Video und Ton zusammenführen |
| [Deno](https://deno.com) | JavaScript-Laufzeit, die yt-dlp für YouTube benötigt |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Suche und Download, wird per pip installiert |

## Installation

### Windows

1. ZIP-Datei aus dem Bereich *Releases* herunterladen und entpacken.
2. `setup.bat` ausführen.

Das Skript installiert fehlende Komponenten über winget, aktualisiert yt-dlp und legt Verknüpfungen auf dem Desktop und im Startmenü an.

### pipx

```
pipx install git+https://github.com/cybtide/ytpick
ytpick
```

ffmpeg und Deno müssen separat installiert sein.

### Manuell

```
pip install -r requirements.txt
python ytpick.py
```

## Bedienung

| Eingabe | Ergebnis |
| --- | --- |
| `suchbegriff` | Videosuche |
| `@kanalname` | Neueste Videos des Kanals |
| `@kanalname begriff` | Videos des Kanals mit dem Begriff im Titel |
| Kanal-URL | Videos des Kanals |

| Aktion | Bedienung |
| --- | --- |
| Suche aus dem Cache | Enter |
| Suche ohne Cache | Umschalt + Enter oder Schaltfläche *Ohne Cache* |
| Mehrere Videos wählen | Strg- oder Umschalttaste |
| Video ausblenden | Entf |
| Kontextmenü | Rechtsklick |
| Herunterladen | Doppelklick oder Schaltfläche *Auswahl herunterladen* |
| Sortieren | Klick auf eine Spaltenüberschrift |

## Bot-Prüfung von YouTube

Meldet YouTube `Sign in to confirm you're not a bot`, wähle unten bei *Cookies aus Browser* einen Browser, in dem du bei YouTube angemeldet bist. Firefox funktioniert am zuverlässigsten. Chrome und Edge müssen unter Windows teilweise vollständig geschlossen sein.

## Gespeicherte Daten

Alle Dateien liegen im Benutzerverzeichnis.

| Datei | Inhalt |
| --- | --- |
| `.ytdl_gui.json` | Einstellungen, Download-Historie, ausgeblendete Videos, blockierte Kanäle |
| `.ytdl_gui_cache.json` | Zwischengespeicherte Suchergebnisse und Upload-Daten |
| `.ytdl_gui.log` | Protokoll mit Zeitstempeln |

## Kommandozeile

```
python ytpick_cli.py "suchbegriff"
python ytpick_cli.py "suchbegriff" -n 20 --mp4
python ytpick_cli.py "https://www.youtube.com/watch?v=..."
python ytpick_cli.py --help
```

## Hinweise zur Nutzung

ytpick ist ein unabhängiges Projekt und steht in keiner Verbindung zu YouTube oder Google. Lade nur Inhalte herunter, zu deren Vervielfältigung du berechtigt bist, und beachte die Nutzungsbedingungen von YouTube sowie das in deinem Land geltende Recht.

yt-dlp, ffmpeg und Deno sind eigenständige Projekte mit eigenen Lizenzen. Sie sind nicht Bestandteil dieses Repositorys.

## Versionierung und Releases

ytpick folgt [Semantic Versioning](https://semver.org/lang/de/). Die installierte Version zeigt `ytpick --version` sowie die Kurzanleitung im Programm. Änderungen stehen im [Changelog](CHANGELOG.md).

Ein Release entsteht so:

1. `__version__` in `ytpick.py` erhöhen.
2. In `CHANGELOG.md` einen Abschnitt `## [x.y.z] - JJJJ-MM-TT` ergänzen.
3. Änderungen committen, Tag `vx.y.z` setzen und pushen.

Der Release-Workflow prüft, ob Tag, Version und Changelog zusammenpassen, und veröffentlicht das Windows-Paket mit den Release-Notizen aus dem Changelog.

## Lizenz

[MIT](LICENSE)
