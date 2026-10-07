import argparse
import re
import sys
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp fehlt. Installieren mit: pip install -U yt-dlp")


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
    for unit, div in (("Mrd", 1e9), ("Mio", 1e6), ("Tsd", 1e3)):
        if v >= div:
            return f"{v / div:.1f} {unit}"
    return str(v)


def search(query, n):
    opts = {"quiet": True, "extract_flat": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{n}:{query}", download=False)
    return [e for e in (info.get("entries") or []) if e]


def show_results(entries):
    print()
    for i, e in enumerate(entries, 1):
        print(f"{i:>2}. {e.get('title', '?')}")
        print(
            f"    {e.get('channel') or e.get('uploader') or '?'}"
            f"  |  {fmt_duration(e.get('duration'))}"
            f"  |  {fmt_views(e.get('view_count'))} Aufrufe"
        )
    print()


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
            raise ValueError(f"Ungültige Eingabe: {part}")
    bad = [p for p in picked if not 1 <= p <= maximum]
    if bad:
        raise ValueError(f"Außerhalb des Bereichs 1-{maximum}: {bad}")
    return list(dict.fromkeys(picked))


def build_opts(outdir, audio_only, mp4):
    opts = {
        "outtmpl": str(outdir / "%(title).150B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "windowsfilenames": True,
        "restrictfilenames": False,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 4,
        "writethumbnail": False,
        "ignoreerrors": True,
    }
    if audio_only:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "best"},
            {"key": "FFmpegMetadata"},
        ]
    elif mp4:
        opts["format"] = "bv*+ba/b"
        opts["format_sort"] = ["res", "ext:mp4:m4a"]
        opts["merge_output_format"] = "mp4"
        opts["postprocessors"] = [{"key": "FFmpegMetadata"}]
    else:
        opts["format"] = "bv*+ba/b"
        opts["merge_output_format"] = "mkv"
        opts["postprocessors"] = [{"key": "FFmpegMetadata"}]
    return opts


def download(urls, outdir, audio_only, mp4):
    outdir.mkdir(parents=True, exist_ok=True)
    with yt_dlp.YoutubeDL(build_opts(outdir, audio_only, mp4)) as ydl:
        ydl.download(urls)
    print(f"\nFertig. Dateien liegen in: {outdir}")


def entry_url(e):
    return e.get("url") or f"https://www.youtube.com/watch?v={e['id']}"


def main():
    p = argparse.ArgumentParser(description="YouTube suchen & in bester Qualität laden")
    p.add_argument("query", nargs="?", help="Suchbegriff oder URL")
    p.add_argument("-n", type=int, default=10, help="Anzahl Suchergebnisse (Standard 10)")
    p.add_argument("-o", "--output", default=str(Path.home() / "Downloads" / "YouTube"),
                   help="Zielordner")
    p.add_argument("--audio", action="store_true", help="Nur Audio")
    p.add_argument("--mp4", action="store_true", help="MP4 statt MKV")
    args = p.parse_args()

    outdir = Path(args.output).expanduser()
    query = args.query or input("Suchbegriff oder URL: ").strip()

    while query:
        if re.match(r"https?://", query):
            download([query], outdir, args.audio, args.mp4)
        else:
            print(f"Suche nach: {query} …")
            entries = search(query, args.n)
            if not entries:
                print("Keine Treffer.")
            else:
                show_results(entries)
                while True:
                    sel = input("Auswahl (z.B. 1,3 | 2-4 | all | Enter = neue Suche): ").strip()
                    if not sel:
                        break
                    if sel.lower() == "q":
                        return
                    try:
                        idx = parse_selection(sel, len(entries))
                    except ValueError as err:
                        print(err)
                        continue
                    download([entry_url(entries[i - 1]) for i in idx],
                             outdir, args.audio, args.mp4)
                    break
        query = input("\nNeue Suche / URL (leer = Ende): ").strip()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
