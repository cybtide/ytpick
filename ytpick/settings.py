"""Einstellungsdialog, Spaltenwahl und Filterleiste."""

import tkinter as tk
from tkinter import messagebox, ttk

from .compat import HAVE_PIL
from .constants import (
    BROWSERS, COLUMN_KEYS, COLUMN_LABELS, DATE_RANGES, DEFAULT_VISIBLE, DONE_ACTION_LABELS,
    LOCKED_COLUMNS, NAME_PRESET_LABELS,
)
from .i18n import _
from .util import parse_clock


class SettingsMixin:
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
        win.geometry("640x870")
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
        self.set_upd = tk.BooleanVar(value=self.check_updates)
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
        ttk.Checkbutton(extra, text=_("Beim Start nach neuer Version suchen (GitHub)"),
                        variable=self.set_upd).grid(row=11, column=0, columnspan=2, sticky="w", pady=(8, 0))
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
        self.check_updates = self.set_upd.get()
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
