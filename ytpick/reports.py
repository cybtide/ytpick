"""Statistik und Verlauf."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .i18n import _
from .util import compute_stats, fmt_hours, fmt_size, log, open_path


class ReportsMixin:
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
