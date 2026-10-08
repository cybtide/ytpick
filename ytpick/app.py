"""Hauptfenster: setzt die Teile zusammen und startet das Programm."""

import argparse
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import __version__
from .blocklist import BlocklistMixin
from .compat import HAVE_PIL
from .constants import (
    CACHE_FILE, COLUMNS, COLUMN_KEYS, DARK, DATE_RANGES, DATE_WORKERS, DEFAULT_FMT,
    DEFAULT_VISIBLE, DEFAULT_WINDOW, DONE_ACTIONS, HISTORY_MAX, LOCKED_COLUMNS,
    MAX_CACHED_SEARCHES, NAME_PRESETS, RESULTS, SAVED_FMT_KEYS, STATE_FILE, THUMB_W,
    THUMB_WORKERS,
)
from .desktop import DesktopMixin
from .downloads import DownloadMixin
from .i18n import _, detect_language, set_language
from .pins import PinsMixin
from .reports import ReportsMixin
from .results import ResultsMixin
from .search import SearchMixin
from .settings import SettingsMixin
from .theme import ThemeMixin
from .update import UPDATE_INTERVAL
from .util import QuietLogger, load_json
from .watch import WatchMixin


class App(
    ThemeMixin, SettingsMixin, PinsMixin, ResultsMixin, BlocklistMixin,
    SearchMixin, DownloadMixin, DesktopMixin, ReportsMixin, WatchMixin, tk.Tk,
):
    def __init__(self):
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
        self.cur_spec = None
        self.pool_size = 0
        self.pool_end = False
        self.pool_prev = 0
        self.h_win = None
        self.s_win = None
        self.pin_view = None
        self.search_hist = [q for q in st.get("search_history", []) if isinstance(q, str)][:HISTORY_MAX]
        self.pin_lists = set(st.get("pin_lists", []))
        self.name_preset = s.get("name_preset", "title") if s.get("name_preset") in NAME_PRESETS else "title"
        self.done_action = s.get("done_action", "sound") if s.get("done_action") in DONE_ACTIONS else "sound"
        self.watch_clipboard = bool(s.get("watch_clipboard", True))
        self.check_updates = bool(s.get("check_updates", True))
        self.update_last = float(s.get("update_last", 0) or 0)
        self.update_skip = str(s.get("update_skip", ""))
        self.update_bar = None
        self.update_info = None
        self.open_queue_on_add = bool(s.get("open_queue_on_add", False))
        self.clip_last = ""
        self.clip_bar = None
        self.shutdown_win = None
        self.lang_choice = s.get("lang", "auto")
        set_language(detect_language(self.lang_choice))
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
                           (_("Nach Updates suchen"), lambda: self.start_update_check(True)),
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
        for seq in ("<Control-a>", "<Control-A>", "<Command-a>"):
            self.tree.bind(seq, self.select_all)
        self.sel_anchor = None
        for key, delta in (("Up", -1), ("Down", 1), ("Prior", -10), ("Next", 10)):
            self.tree.bind(f"<{key}>", lambda e, d=delta: self.key_nav(d, False))
            self.tree.bind(f"<Shift-{key}>", lambda e, d=delta: self.key_nav(d, True))
        for key, pos in (("Home", 0), ("End", -1)):
            self.tree.bind(f"<{key}>", lambda e, p=pos: self.key_nav(0, False, p))
            self.tree.bind(f"<Shift-{key}>", lambda e, p=pos: self.key_nav(0, True, p))
        self.tree.bind("<ButtonPress-1>", self.remember_anchor, add="+")
        self.q.bind("<Down>", self.search_to_list)
        self.bind("<Control-f>", self.focus_search)
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
        if self.check_updates and time.time() - self.update_last >= UPDATE_INTERVAL:
            self.after(3000, self.start_update_check)
        if self.pinned:
            self.token += 1
            self._show([], self.token, _("Gemerkte Videos"))
        if self.show_readme.get():
            self.after(400, self.show_readme_dialog)


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
                "check_updates": self.check_updates,
                "update_last": self.update_last,
                "update_skip": self.update_skip,
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="ytpick",
        description="Search YouTube, pick videos and download them in best quality.",
    )
    parser.add_argument("--version", action="version", version=f"ytpick {__version__}")
    parser.parse_args(argv)
    App().mainloop()
