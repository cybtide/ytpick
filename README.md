<p align="center">
  <img src="assets/icon.png" alt="ytpick" width="112">
</p>

<h1 align="center">ytpick</h1>

<p align="center">
  Desktop application to search YouTube, pick videos and download them in best quality.<br>
  Graphical front end for <a href="https://github.com/yt-dlp/yt-dlp">yt-dlp</a>.<br>
  <a href="README.de.md">Deutsch</a>
</p>

<p align="center">
  <img src="docs/screenshot.png" alt="ytpick with demo data" width="820"><br>
  <sub>Screenshot with demo data</sub>
</p>

## Features

- Search with up to 50 visible results from a pool of 150, sortable by any column
- Channel search by `@handle` or channel URL, optionally with a title filter
- Download queue with progress, pause and cancel
- Per-download options: maximum resolution, embedded subtitles and chapters, folder per channel
- Playlists: paste a playlist URL and queue the whole list
- Clip download: only a time range of a video
- Embed cover art and metadata (MP3, MP4, MKV)
- Filters for duration, period and verified channels
- Warning before downloading a video again, with the format used last time
- History of downloaded files with open file / show folder
- Statistics: downloads in total, videos vs. music, per period, per channel and per month, total size and duration
- Speed limit and an optional time window (for example nights only) for the queue
- Offers the cookies of an installed browser when YouTube asks for a bot check
- Watch channels and list new videos since your last check
- Pin videos into named pin lists; pinned videos stay on top and survive new searches
- Search history in the search box, YouTube links from the clipboard are offered automatically
- Choose the file name pattern (title, channel and title, or number and title)
- Sound when the queue is finished, optionally shut down the PC afterwards
- Optional thumbnails in the result list
- Choose and reorder the visible columns in the settings
- Verified-channel indicator, shown only when YouTube provides it
- Hide videos and block channels; blocklist with timestamps, unblocking and log
- Already downloaded videos are recognised and marked; each finished file is checked against the selected video ID
- Cache for search results and upload dates to stay within YouTube's rate limits
- Download as MKV (best quality), MP4, MP3 or audio only
- Sign-in through the cookies of an installed browser
- Dark mode, quick guide and system check at startup
- English and German interface
- One-click yt-dlp update from the quick guide
- Terminal version `ytpick-cli` for Linux, macOS and Windows

## Requirements

| Component | Purpose |
| --- | --- |
| Python 3.10 or newer with tkinter | The program (Linux: package `python3-tk`) |
| [ffmpeg](https://ffmpeg.org) | Merging video and audio |
| [Deno](https://deno.com) | JavaScript runtime that yt-dlp needs for YouTube |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Search and download, installed with pip |
| [Pillow](https://python-pillow.org) (optional) | Thumbnails |

## Installation

### Windows

**Option A: executable.** Download `ytpick-x.y.z-windows.exe` from the *Releases* section and start it. No Python needed. ffmpeg and Deno still have to be installed:

```
winget install Gyan.FFmpeg DenoLand.Deno
```

The executable is not code-signed, so Windows SmartScreen may warn on the first start. yt-dlp is built into the executable; update it by downloading the latest release.

**Option B: installer.**

1. Download the ZIP file from the *Releases* section and extract it.
2. Run `setup.bat`.

The script installs missing components through winget, updates yt-dlp and creates shortcuts on the desktop and in the start menu.

### Linux

**Option A: binary.** Download `ytpick-x.y.z-linux-x86_64.tar.gz` from the *Releases* section, extract it and start `./ytpick` (graphical) or `./ytpick-cli` (terminal). No Python needed. ffmpeg and Deno still have to be installed, for example `sudo apt install ffmpeg` and the [Deno install script](https://deno.com). The binaries are built on Ubuntu 22.04 and need a similarly recent glibc.

**Option B: pipx.** See below. The graphical version needs the package `python3-tk`.

### pipx

```
pipx install "ytpick[thumbnails] @ git+https://github.com/cybtide/ytpick"
ytpick
ytpick-cli --help
```

ffmpeg and Deno have to be installed separately. Leave out `[thumbnails]` if you do not want thumbnails.

### Manual

```
pip install -r requirements.txt
python ytpick.py
```

## Usage

| Input | Result |
| --- | --- |
| `search term` | Video search |
| `@channelname` | Latest videos of the channel |
| `@channelname term` | Videos of the channel with the term in the title |
| Channel URL | Videos of the channel |
| Video link (`youtu.be/...`, `watch?v=...`) | That video |
| Playlist URL (`youtube.com/playlist?list=...`) | All videos of the playlist, up to 300 |

| Action | How |
| --- | --- |
| Search from cache | Enter |
| Search without cache | Shift + Enter or the *No cache* button |
| Select several videos | Ctrl or Shift |
| Hide a video | Del |
| Pin a video | Space or click on the star |
| Context menu | Right click |
| Download | Double click or *Download selection* |
| Download with options | *Options…* or context menu |
| Sort | Click a column header |

## YouTube bot check

If YouTube reports `Sign in to confirm you're not a bot`, choose a browser in which you are signed in to YouTube at *Cookies from browser* in the settings. Firefox works most reliably. On Windows, Chrome and Edge sometimes have to be closed completely.

## Stored data

All files are located in the user directory.

| File | Content |
| --- | --- |
| `.ytdl_gui.json` | Settings, download history, pinned and hidden videos, blocked and watched channels, downloaded files |
| `.ytdl_gui_cache.json` | Cached search results and upload dates |
| `.ytdl_gui_thumbs/` | Cached thumbnails |
| `.ytdl_gui.log` | Log with timestamps |

## Command line

`ytpick-cli` is the terminal version without a window and without tkinter. After `pipx install` it is available as a command, otherwise start `python ytpick_cli.py`.

```
ytpick-cli "search term"
ytpick-cli "search term" -n 20 --mp4
ytpick-cli @channelname tutorial --mp3 --embed
ytpick-cli "https://www.youtube.com/playlist?list=..." --all -o ~/Music
ytpick-cli "https://www.youtube.com/watch?v=..." --cut 1:20-3:45
ytpick-cli "search term" --list
ytpick-cli --help
```

It understands the same input as the window (search term, `@channel` with filter word, channel, playlist and video URLs). Results are numbered; choose with `1,3`, `2-4` or `all`, type `m` for more results. `--pick 1,3`, `--all` and `--list` work without questions, so it can run in scripts; the exit code is 1 if a download failed. Further options: `--mp4`, `--mp3`, `--audio`, `--max-height`, `--cut`, `--embed`, `--chapters`, `--subs`, `--name`, `--channel-folder`, `--cookies`, `--rate`.

## Development

```
pip install -e ".[thumbnails]"
python -m unittest discover -s tests -v
```

The tests that open the window need a display (on Linux for example `xvfb-run`).

## Notes on use

ytpick is an independent project and not affiliated with YouTube or Google. Only download content you are entitled to copy, and observe YouTube's terms of service and the law of your country.

yt-dlp, ffmpeg and Deno are independent projects with their own licenses. They are not part of this repository.

## Versioning and releases

ytpick follows [Semantic Versioning](https://semver.org). The installed version is shown by `ytpick --version` and in the quick guide. Changes are listed in the [changelog](CHANGELOG.md).

A release is created like this:

1. Raise `__version__` in `ytpick.py`.
2. Add a section `## [x.y.z] - YYYY-MM-DD` to `CHANGELOG.md`.
3. Commit, tag `vx.y.z` and push.

The release workflow checks that tag, version and changelog match and publishes the Windows package with the release notes taken from the changelog.

## License

[MIT](LICENSE)
