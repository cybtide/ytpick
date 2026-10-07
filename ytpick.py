import argparse
import json
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

try:
    import yt_dlp
except ImportError:
    raise SystemExit("yt-dlp fehlt. Installieren mit: pip install -U yt-dlp[default]")

try:
    from yt_dlp.version import __version__ as YTDLP_VERSION
except Exception:
    YTDLP_VERSION = "?"


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
                    val, _ = winreg.QueryValueEx(k, "Path")
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
RESULTS = 50
POOL = 150
CHANNEL_POOL = 300
CACHE_TTL = 12 * 3600
MAX_CACHED_SEARCHES = 40
DATE_WORKERS = 2
BROWSERS = ["keine", "firefox", "chrome", "edge", "brave", "vivaldi", "opera", "safari"]

COLUMNS = [
    ("rank", "#", 40, "e"),
    ("titel", "Titel", 410, "w"),
    ("kanal", "Kanal", 150, "w"),
    ("datum", "Upload", 90, "w"),
    ("dauer", "Dauer", 65, "e"),
    ("aufrufe", "Aufrufe", 100, "e"),
]

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
    ("p", "4. Blockliste\n"
          "   Zeigt geblockte Kanäle und ausgeblendete Videos mit Zeitpunkt, Entsperren und Log."),
    ("p", "5. Bot-Check von YouTube?\n"
          "   Unten bei \"Cookies aus Browser\" einen Browser wählen, in dem du bei YouTube eingeloggt bist."),
    ("p", "Nur Inhalte herunterladen, die du herunterladen darfst."),
]


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
        return "live"
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
        return "gerade eben"
    if mins < 90:
        return f"vor {mins} Min"
    return f"vor {mins // 60} Std"


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
                "term": "", "label": f"Suche „{q}“"}
    target, term = m.group(1), m.group(2).strip()
    if target.startswith("@"):
        url = f"https://www.youtube.com/{target}/videos"
    else:
        url = target.rstrip("/")
        if (not re.search(r"/(videos|streams|shorts|playlists|search|featured)(/|\?|$)", url)
                and "/watch" not in url and "/playlist" not in url):
            url += "/videos"
    label = f"Kanal {target}" + (f" · Filter „{term}“" if term else "")
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
    }


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"ytpick {__version__}")
        self.geometry("1050x700")

        st = load_json(STATE_FILE, {})
        hidden = st.get("hidden", {})
        if isinstance(hidden, list):
            hidden = {v: {"title": "?", "channel": "?", "at": "?"} for v in hidden}
        self.hidden = hidden
        self.blocked = st.get("blocked_channels", {})
        self.history = set(st.get("downloaded", []))
        s = st.get("settings", {})

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
        self.show_hidden = tk.BooleanVar(value=False)
        self.hide_downloaded = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Suchbegriff, @Kanal oder Kanal-URL eingeben und Enter drücken.")

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.q = ttk.Entry(top)
        self.q.pack(side="left", fill="x", expand=True)
        self.q.bind("<Return>", lambda e: self.do_search())
        self.q.bind("<Shift-Return>", lambda e: self.do_search(force=True))
        self.q.focus()
        ttk.Button(top, text="Suchen", command=self.do_search).pack(side="left", padx=(6, 0))
        ttk.Button(top, text="Ohne Cache", command=lambda: self.do_search(force=True)).pack(
            side="left", padx=(6, 0))

        filt = ttk.Frame(self, padding=(8, 0))
        filt.pack(fill="x")
        ttk.Checkbutton(filt, text="Ausgeblendete/Geblockte anzeigen", variable=self.show_hidden,
                        command=self.render).pack(side="left")
        ttk.Checkbutton(filt, text="Bereits geladene ausblenden", variable=self.hide_downloaded,
                        command=self.render).pack(side="left", padx=12)
        ttk.Button(filt, text="Blockliste…", command=self.open_blocklist).pack(side="right")
        ttk.Button(filt, text="Kanal blockieren", command=self.block_channels).pack(side="right", padx=6)
        ttk.Button(filt, text="Video ausblenden/einblenden (Entf)",
                   command=self.toggle_hide).pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=6)
        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS],
                                 show="headings", selectmode="extended")
        for key, text, width, anchor in COLUMNS:
            self.tree.heading(key, text=text, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "titel"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.do_download())
        self.tree.bind("<Delete>", lambda e: self.toggle_hide())
        self.tree.bind("<Button-3>", self.on_context)
        self.tree.bind("<Button-2>", self.on_context)
        self.ctx = tk.Menu(self, tearoff=0)
        self.ctx.add_command(label="Herunterladen", command=self.do_download)
        self.ctx.add_command(label="Mehr von diesem Kanal", command=self.more_from_channel)
        self.ctx.add_separator()
        self.ctx.add_command(label="Video ausblenden/einblenden", command=self.toggle_hide)
        self.ctx.add_command(label="Kanal blockieren", command=self.block_channels)
        self.update_headings()

        opt = ttk.Frame(self, padding=(8, 4))
        opt.pack(fill="x")
        for text, val in (("Video MKV (beste Qualität)", "mkv"),
                          ("Video MP4", "mp4"), ("Nur Audio", "audio")):
            ttk.Radiobutton(opt, text=text, value=val, variable=self.mode).pack(side="left", padx=4)
        ttk.Button(opt, text="Ordner…", command=self.pick_dir).pack(side="right")
        ttk.Entry(opt, textvariable=self.outdir, width=40).pack(side="right", padx=6)

        opt2 = ttk.Frame(self, padding=(8, 0))
        opt2.pack(fill="x")
        ttk.Label(opt2, text="Cookies aus Browser:").pack(side="left")
        cb = ttk.Combobox(opt2, textvariable=self.cookies, values=BROWSERS,
                          state="readonly", width=10)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.on_cookies_changed())
        ttk.Checkbutton(opt2, text="Upload-Datum nachladen", variable=self.fetch_dates,
                        command=self.on_fetch_dates_toggle).pack(side="left", padx=12)
        ttk.Button(opt2, text="Datum erneut versuchen", command=self.retry_dates).pack(side="left")
        ttk.Button(opt2, text="Hilfe", command=self.show_readme_dialog).pack(side="right")
        ttk.Checkbutton(opt2, text="Dark Mode", variable=self.dark,
                        command=self.on_theme_toggle).pack(side="right", padx=10)

        bot = ttk.Frame(self, padding=8)
        bot.pack(fill="x")
        ttk.Label(bot, textvariable=self.status).pack(side="left")
        ttk.Button(bot, text="Auswahl herunterladen", command=self.do_download).pack(side="right")

        self.apply_theme()
        for _ in range(DATE_WORKERS):
            threading.Thread(target=self._date_worker, daemon=True).start()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_disk()
        if self.show_readme.get():
            self.after(400, self.show_readme_dialog)

    def style_text(self, widget):
        p = self.pal
        widget.configure(bg=p["field"], fg=p["fg"], insertbackground=p["fg"],
                         selectbackground=p["sel"], selectforeground="#ffffff",
                         relief="flat", highlightthickness=0, borderwidth=0)

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
                     foreground=p["fg"], rowheight=22, borderwidth=0)
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
             "gefunden" if shutil.which("ffmpeg") else "fehlt (nötig zum Zusammenfügen von Video und Ton)"),
            ("deno", shutil.which("deno") is not None,
             "gefunden" if shutil.which("deno") else "fehlt (nötig für YouTube-Downloads)"),
            ("ytpick", True, f"Version {__version__}"),
            ("yt-dlp", True, f"Version {YTDLP_VERSION}"),
        ]

    def show_readme_dialog(self):
        if self.readme_win and self.readme_win.winfo_exists():
            self.readme_win.lift()
            return
        win = tk.Toplevel(self)
        win.title("Kurzanleitung")
        win.geometry("700x600")
        win.transient(self)
        self.readme_win = win

        btns = ttk.Frame(win, padding=10)
        btns.pack(side="bottom", fill="x")
        ttk.Checkbutton(btns, text="Beim Start anzeigen", variable=self.show_readme,
                        command=self.save).pack(side="left")
        ttk.Button(btns, text="Los geht's", command=win.destroy).pack(side="right")

        text = tk.Text(win, wrap="word", padx=16, pady=12, font=("Segoe UI", 10), cursor="arrow")
        text.pack(fill="both", expand=True)
        self.readme_text = text
        text.tag_configure("h", font=("Segoe UI", 14, "bold"), spacing3=8)
        text.tag_configure("sub", font=("Segoe UI", 11, "bold"), spacing1=10, spacing3=4)
        text.tag_configure("p", spacing3=10)
        text.tag_configure("ok")
        text.tag_configure("bad")
        for tag, content in HELP_TEXT:
            text.insert("end", content + "\n", tag)
        text.insert("end", "Systemcheck\n", "sub")
        for name, ok, detail in self.system_check():
            text.insert("end", ("✓ " if ok else "✗ ") + f"{name}: {detail}\n", "ok" if ok else "bad")
        if not all(ok for _, ok, _ in self.system_check()):
            text.insert("end", "\nFehlende Teile installiert setup.bat (im Installer-Ordner).\n", "p")
        text.configure(state="disabled")
        self.apply_theme()

    def save(self):
        data = {
            "hidden": self.hidden,
            "blocked_channels": self.blocked,
            "downloaded": sorted(self.history),
            "settings": {
                "outdir": self.outdir.get(),
                "mode": self.mode.get(),
                "cookies": self.cookies.get(),
                "fetch_dates": self.fetch_dates.get(),
                "dark": self.dark.get(),
                "show_readme": self.show_readme.get(),
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
        try:
            for f in Path(self.outdir.get()).expanduser().iterdir():
                m = re.search(r"\[([A-Za-z0-9_-]{11})\]", f.name)
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
        self.status.set(f"Cookies: {self.cookies.get()}. Gilt für Datum-Abruf und Downloads.")
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

    def update_headings(self):
        for key, text, _, _ in COLUMNS:
            arrow = ""
            if key == self.sort_col:
                arrow = " ▼" if self.sort_rev else " ▲"
            self.tree.heading(key, text=text + arrow)

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
        if c == "datum":
            return it["date"] or ""
        if c == "dauer":
            return it["duration"] or 0
        return it["views"] or 0

    def render(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        rows = []
        for it in self.items:
            hid = it["id"] in self.hidden
            blk = self.chan_key(it) in self.blocked
            dl = self.is_downloaded(it["id"])
            if (hid or blk) and not self.show_hidden.get():
                continue
            if dl and self.hide_downloaded.get():
                continue
            rows.append((it, hid, blk, dl))
            if len(rows) >= RESULTS:
                break
        rows.sort(key=lambda r: self.sort_key(r[0]), reverse=self.sort_rev)
        for it, hid, blk, dl in rows:
            tags = []
            if hid or blk:
                tags.append("hidden")
            if dl:
                tags.append("downloaded")
            prefix = ("⊘ " if (hid or blk) else "") + ("✓ " if dl else "")
            self.tree.insert("", "end", iid=it["id"], tags=tags, values=(
                it["rank"], prefix + it["title"], it["channel"], fmt_date(it["date"]),
                fmt_dur(it["duration"]), fmt_views(it["views"]),
            ))
        keep = [i for i in selected if self.tree.exists(i)]
        if keep:
            self.tree.selection_set(keep)
        self.shown = [r[0] for r in rows]
        self.ensure_dates()

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
            self.status.set("Für diesen Kanal ist keine Kanal-ID bekannt. Nutze @handle oder die Kanal-URL.")
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
            self.status.set(f"{len(sel)} Video(s) wieder eingeblendet.")
        else:
            n = 0
            for it in sel:
                if it["id"] not in self.hidden:
                    self.hidden[it["id"]] = {"title": it["title"], "channel": it["channel"], "at": now()}
                    log("HIDE video", f"{it['id']} | {it['title']} | {it['channel']}")
                    n += 1
            self.status.set(f"{n} Video(s) ausgeblendet, neue Treffer rücken nach.")
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
            self.status.set("Kanal blockiert: " + ", ".join(dict.fromkeys(names)))

    def open_blocklist(self):
        if self.bl_win and self.bl_win.winfo_exists():
            self.bl_win.lift()
            self.refresh_blocklist()
            return
        win = tk.Toplevel(self)
        win.title("Blockliste")
        win.geometry("820x500")
        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        f1 = ttk.Frame(nb, padding=6)
        self.bl_ch = ttk.Treeview(f1, columns=("name", "key", "at"), show="headings",
                                  selectmode="extended")
        for c, t, w in (("name", "Kanal", 280), ("key", "Kanal-ID", 250), ("at", "Geblockt am", 150)):
            self.bl_ch.heading(c, text=t)
            self.bl_ch.column(c, width=w, anchor="w")
        self.bl_ch.pack(fill="both", expand=True)
        ttk.Button(f1, text="Ausgewählte Kanäle entsperren",
                   command=self.unblock_channels).pack(anchor="e", pady=(6, 0))
        nb.add(f1, text="Kanäle")

        f2 = ttk.Frame(nb, padding=6)
        self.bl_vid = ttk.Treeview(f2, columns=("title", "channel", "at"), show="headings",
                                   selectmode="extended")
        for c, t, w in (("title", "Video", 380), ("channel", "Kanal", 170), ("at", "Ausgeblendet am", 150)):
            self.bl_vid.heading(c, text=t)
            self.bl_vid.column(c, width=w, anchor="w")
        self.bl_vid.pack(fill="both", expand=True)
        ttk.Button(f2, text="Ausgewählte Videos wieder einblenden",
                   command=self.unhide_videos).pack(anchor="e", pady=(6, 0))
        nb.add(f2, text="Videos")

        f3 = ttk.Frame(nb, padding=6)
        self.bl_log = tk.Text(f3, wrap="none", state="disabled", height=10)
        lsb = ttk.Scrollbar(f3, orient="vertical", command=self.bl_log.yview)
        self.bl_log.configure(yscrollcommand=lsb.set)
        self.bl_log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        nb.add(f3, text="Log")
        self.bl_win = win
        ttk.Button(win, text="Aktualisieren", command=self.refresh_blocklist).pack(pady=(0, 8))
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
                title = f"(Titel unbekannt) [{v}]"
            at = h.get("at", "?")
            if at in ("?", ""):
                at = "vor dem Logging"
            channel = h.get("channel", "?")
            if channel in ("?", ""):
                channel = "unbekannt"
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
            self._show(entry["items"], self.token, f"{spec['label']} · aus Cache ({age_text(entry['at'])})")
            return
        self.status.set(f"{spec['label']} … lädt")
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
            self.set_status(f"Fehler bei der Suche: {short_err(err)}")
            return
        self.after(0, lambda: self._finish_search(spec, items, token))

    def _finish_search(self, spec, items, token):
        if items:
            self.cache["searches"][spec["key"]] = {"at": time.time(), "items": items}
            self.save_cache()
        if token == self.token:
            self._show(items, token, f"{spec['label']} · frisch geladen")

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
        self.by_id = {it["id"]: it for it in self.items}
        self.save()
        self.refresh_disk()
        self.sort_col, self.sort_rev = "rank", False
        self.update_headings()
        self.render()
        missing = sum(1 for it in self.shown if it["date"] is None)
        self.status.set(f"{note} · {len(self.shown)} sichtbar (Pool {len(self.items)})"
                        + (f" · Datum fehlt bei {missing}" if missing and self.fetch_dates.get() else ""))

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
            self.status.set("YouTube verlangt einen Bot-Check. Wähle unten einen Browser bei "
                            "'Cookies aus Browser' (Datum bleibt bis dahin leer).")
        elif self.date_done >= self.date_total:
            if self.cache_dirty:
                self.save_cache()
            if self.date_fail:
                self.status.set(f"Datum bei {self.date_fail} Video(s) nicht ladbar. Grund: "
                                f"{self.date_last_err or 'unbekannt (siehe Log)'}")
            else:
                self.status.set(f"{len(self.shown)} Treffer sichtbar. Datum vollständig geladen.")
            if self.sort_col == "datum":
                self.render()
        else:
            self.status.set(f"Lade Upload-Datum … {self.date_done}/{self.date_total}")

    def do_download(self):
        picked = self.selected_items()
        if not picked:
            messagebox.showinfo("Hinweis", "Bitte erst ein oder mehrere Videos auswählen.")
            return
        threading.Thread(target=self._download, args=(picked,), daemon=True).start()

    def _download(self, picked):
        outdir = Path(self.outdir.get()).expanduser()
        outdir.mkdir(parents=True, exist_ok=True)
        mode = self.mode.get()
        opts = self.ydl_opts()
        opts.update({
            "outtmpl": str(outdir / "%(title).150B [%(id)s].%(ext)s"),
            "noplaylist": True,
            "windowsfilenames": True,
            "retries": 10,
            "fragment_retries": 10,
            "concurrent_fragment_downloads": 4,
            "progress_hooks": [self._hook],
        })
        if mode == "audio":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "best"}]
        elif mode == "mp4":
            opts.update(format="bv*+ba/b", format_sort=["res", "ext:mp4:m4a"],
                        merge_output_format="mp4")
        else:
            opts.update(format="bv*+ba/b", merge_output_format="mkv")

        ok, failed, last_err = 0, 0, ""
        with yt_dlp.YoutubeDL(opts) as ydl:
            for n, it in enumerate(picked, 1):
                self.set_status(f"Lade {n}/{len(picked)}: {it['title'][:60]} …")
                try:
                    if ydl.download([it["url"]]) == 0:
                        ok += 1
                        self.history.add(it["id"])
                        self.disk_ids.add(it["id"])
                        log("DOWNLOAD", f"{it['id']} | {it['title']} | {it['channel']}")
                        self.after(0, self.save)
                        self.after(0, self.render)
                    else:
                        failed += 1
                except Exception as err:
                    failed += 1
                    last_err = short_err(err, 200)
                    log("DOWNLOAD FAIL", f"{it['id']} | {last_err}")
        msg = f"Fertig: {ok} geladen"
        if failed:
            msg += f", {failed} fehlgeschlagen"
            if is_bot_error(last_err):
                msg += " (Bot-Check: bitte Browser bei 'Cookies' wählen)"
            elif last_err:
                msg += f" ({last_err[:100]})"
        self.set_status(f"{msg}. Ordner: {outdir}")

    def _hook(self, d):
        if d.get("status") == "downloading":
            self.set_status(f"Lädt … {d.get('_percent_str', '').strip()} "
                            f"({d.get('_speed_str', '').strip()})")
        elif d.get("status") == "finished":
            self.set_status("Verarbeite (zusammenfügen) …")


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
