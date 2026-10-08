# Changelog

Alle nennenswerten Änderungen werden in dieser Datei festgehalten.
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), die Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unveröffentlicht]

### Hinzugefügt

- Programmsymbol für Fenster, Windows-Verknüpfung und README
- Einstellungsdialog zum Ein- und Ausblenden sowie Umsortieren der Spalten
- Spalte „Status“ mit Hinweis auf verifizierte Kanäle, sofern YouTube die Angabe liefert
- Merken von Videos: gemerkte Videos stehen oben und bleiben bei neuen Suchen erhalten
- Prüfung nach dem Download, dass die fertige Datei zur gewählten Video-ID passt
- Download-Warteschlange mit Fortschritt, Pause und Abbrechen
- Download-Optionen pro Video: maximale Auflösung, Untertitel, Kapitel, Ordner pro Kanal
- Beobachtete Kanäle mit Anzeige neuer Videos seit der letzten Prüfung
- Optionale Vorschaubilder in der Trefferliste (Pillow)
- Englische Oberfläche, Spracheinstellung in den Einstellungen
- Englisches README mit Screenshot, deutsche Fassung in `README.de.md`
- Automatische Tests und Testlauf im CI
- Schaltfläche „yt-dlp aktualisieren“ in der Kurzanleitung
- Download als MP3
- Playlists laden und komplett in die Warteschlange legen („Alle sichtbaren laden“)
- Ausschnitt-Download (Start und Ende) und Einbetten von Cover und Metadaten in den Download-Optionen
- Filter nach Dauer, Zeitraum und verifizierten Kanälen
- Warnung vor erneutem Download bereits geladener Videos
- Verlauf der geladenen Dateien mit Datei öffnen und Ordner zeigen
- Statistik-Fenster mit Anzahl von Videos und Musik, Zeiträumen, Top-Kanälen, Monaten, Größe und Laufzeit
- Geschwindigkeitslimit und Zeitfenster für die Warteschlange in den Einstellungen
- Vorschlag der Cookies eines installierten Browsers, wenn YouTube einen Bot-Check verlangt

### Geändert

- Die Download-Historie erkennt Dateien auch in Kanal-Unterordnern

## [0.1.0] - 2026-10-08

### Hinzugefügt

- Videosuche mit bis zu 50 sichtbaren Treffern aus einem Pool von 150, sortierbar nach jeder Spalte
- Kanalsuche per `@handle` oder Kanal-URL, optional mit Titelfilter
- Ausblenden von Videos und Blockieren von Kanälen mit Blockliste, Zeitstempeln und Protokoll
- Markierung bereits geladener Videos
- Cache für Suchergebnisse und Upload-Daten
- Download als MKV (beste Qualität), MP4 oder nur Audio
- Anmeldung über Browser-Cookies
- Dark Mode, Kurzanleitung und Systemcheck beim Start
- Windows-Installer (`setup.bat`) und Kommandozeilenversion (`ytpick_cli.py`)
- Installation über pipx
