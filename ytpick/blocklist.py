"""Ausgeblendete Videos und blockierte Kanäle."""

import tkinter as tk
from tkinter import ttk

from .constants import LOG_FILE
from .i18n import _
from .util import log, now


class BlocklistMixin:
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
