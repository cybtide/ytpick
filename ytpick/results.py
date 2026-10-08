"""Trefferliste: Filter, Sortierung, Tastatur, Darstellung, Kontextmenü."""

import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog

from .constants import CHANNEL_POOL, COLUMNS, DATE_RANGES, RESULTS, THUMB_H, THUMB_W
from .i18n import _
from .util import fmt_date, fmt_dur, fmt_views


class ResultsMixin:
    def reset_filters(self):
        self.f_min.set("")
        self.f_max.set("")
        self.f_verified.set(False)
        self.f_range.set(_(DATE_RANGES[0][0]))

    @staticmethod
    def minutes(var):
        try:
            return float(var.get().replace(",", "."))
        except ValueError:
            return 0.0

    def passes_filters(self, it):
        dur = it.get("duration") or 0
        lo, hi = self.minutes(self.f_min), self.minutes(self.f_max)
        if lo and dur < lo * 60:
            return False
        if hi and dur and dur > hi * 60:
            return False
        if self.f_verified.get() and not it.get("verified"):
            return False
        days = {_(lbl): d for lbl, d in DATE_RANGES}.get(self.f_range.get(), 0)
        date = it.get("date")
        if days and date and len(date) == 8:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
            if date < cutoff:
                return False
        return True

    def remember_anchor(self, event):
        if event.state & 0x0001:
            return
        row = self.tree.identify_row(event.y)
        if row:
            self.sel_anchor = row

    def search_to_list(self, event=None):
        if not self.tree.get_children():
            return None
        self.tree.focus_set()
        return self.key_nav(1, False)

    def focus_search(self, event=None):
        self.q.focus_set()
        self.q.selection_range(0, "end")
        return "break"

    def key_nav(self, delta, extend, absolute=None):
        ids = list(self.tree.get_children())
        if not ids:
            return "break"
        cur = self.tree.focus() if self.tree.focus() in ids else None
        if absolute is not None:
            idx = 0 if absolute == 0 else len(ids) - 1
        elif cur is None:
            idx = 0 if delta > 0 else len(ids) - 1
        else:
            idx = max(0, min(len(ids) - 1, ids.index(cur) + delta))
        target = ids[idx]
        if extend:
            anchor = self.sel_anchor if self.sel_anchor in ids else (cur or target)
            lo, hi = sorted((ids.index(anchor), idx))
            self.tree.selection_set(ids[lo:hi + 1])
            self.sel_anchor = anchor
        else:
            self.tree.selection_set(target)
            self.sel_anchor = target
        self.tree.focus(target)
        self.tree.see(target)
        return "break"

    def select_all(self, event=None):
        self.tree.selection_set(self.tree.get_children())
        return "break"

    def show_more(self):
        if not self.items:
            return
        self.limit += RESULTS
        self.render()
        if self.pool_exhausted() and self.cur_spec and not self.pool_end:
            self.load_more_pool()
            return
        self.status.set(_("{n} sichtbar (Pool {p})").format(n=len(self.shown), p=len(self.items))
                        + self.explain_hidden())

    def pool_exhausted(self):
        return sum(1 for it in self.shown if not self.in_view(it["id"])) < self.limit

    def load_more_pool(self):
        self.pool_size = max(self.pool_size, len(self.items)) + CHANNEL_POOL
        self.pool_prev = len(self.items)
        self.token += 1
        self.status.set(_("{l} … lädt weitere Treffer").format(l=self.cur_spec["label"]))
        threading.Thread(target=self._search, args=(self.cur_spec, self.token, self.pool_size, True),
                         daemon=True).start()

    def explain_hidden(self):
        if self.shown or not self.items:
            return ""
        hidden = dl = filt = 0
        for it in self.items:
            if self.in_view(it["id"]):
                continue
            if (it["id"] in self.hidden or self.chan_key(it) in self.blocked) and not self.show_hidden.get():
                hidden += 1
            elif self.is_downloaded(it["id"]) and self.hide_downloaded.get():
                dl += 1
            elif not self.passes_filters(it):
                filt += 1
        parts = []
        if hidden:
            parts.append(_("{n} ausgeblendet/geblockt").format(n=hidden))
        if dl:
            parts.append(_("{n} bereits geladen (ausgeblendet)").format(n=dl))
        if filt:
            parts.append(_("{n} durch Filter").format(n=filt))
        return (" · " + ", ".join(parts)) if parts else ""

    def filters_active(self):
        return bool(self.minutes(self.f_min) or self.minutes(self.f_max) or self.f_verified.get()
                    or self.f_range.get() != _(DATE_RANGES[0][0]))

    def update_headings(self):
        for key, text, __, ___ in COLUMNS:
            arrow = ""
            if key == self.sort_col:
                arrow = " ▼" if self.sort_rev else " ▲"
            self.tree.heading(key, text=_(text) + arrow)

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
        if c == "pin":
            return 0 if self.in_view(it["id"]) else 1
        if c == "verif":
            return 1 if it.get("verified") else 0
        if c == "datum":
            return it["date"] or ""
        if c == "dauer":
            return it["duration"] or 0
        return it["views"] or 0

    def render(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        pending = {j["item"]["id"]: j["status"] for j in self.jobs if j["status"] in ("queued", "running")}
        rows = []
        kept = []
        for it in self.items:
            hid = it["id"] in self.hidden
            blk = self.chan_key(it) in self.blocked
            dl = self.is_downloaded(it["id"])
            pin = self.in_view(it["id"])
            if not pin:
                if (hid or blk) and not self.show_hidden.get():
                    continue
                if dl and self.hide_downloaded.get():
                    continue
                if not self.passes_filters(it):
                    continue
                if len(rows) - len(kept) >= self.limit:
                    continue
            else:
                kept.append(it["id"])
            rows.append((it, hid, blk, dl))
        rows.sort(key=lambda r: self.sort_key(r[0]), reverse=self.sort_rev)
        rows.sort(key=lambda r: not self.in_view(r[0]["id"]))
        for it, hid, blk, dl in rows:
            tags = []
            state = pending.get(it["id"])
            if hid or blk:
                tags.append("hidden")
            if dl and not state:
                tags.append("downloaded")
            if state:
                tags.append("queued")
            prefix = (("⊘ " if (hid or blk) else "") + ("✓ " if dl else "")
                      + {"queued": "⏳ ", "running": "⬇ "}.get(state, ""))
            extra = {}
            if self.show_thumbs.get():
                extra["image"] = self.thumbs.get(it["id"], self.blank_image())
            self.tree.insert("", "end", iid=it["id"], tags=tags, **extra, values=(
                "★" if it["id"] in self.pinned else "☆", it["rank"], prefix + it["title"],
                it["channel"], _("✔ verifiziert") if it.get("verified") else "",
                fmt_date(it["date"]), fmt_dur(it["duration"]), fmt_views(it["views"]),
            ))
        keep = [i for i in selected if self.tree.exists(i)]
        if keep:
            self.tree.selection_set(keep)
        self.shown = [r[0] for r in rows]
        self.ensure_dates()
        self.ensure_thumbs()

    def blank_image(self):
        if self.blank_thumb is None:
            self.blank_thumb = tk.PhotoImage(width=THUMB_W, height=THUMB_H)
        return self.blank_thumb

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
            self.status.set(_("Für diesen Kanal ist keine Kanal-ID bekannt. Nutze @handle oder die Kanal-URL."))
            return
        self.q.delete(0, "end")
        self.q.insert(0, f"https://www.youtube.com/channel/{it['channel_id']}")
        self.do_search()
