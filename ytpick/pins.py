"""Merklisten und angeheftete Videos."""

from tkinter import simpledialog

from .constants import DEFAULT_PIN_LIST
from .i18n import _
from .util import log


class PinsMixin:
    def on_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        cols = self.tree.cget("displaycolumns")
        idx = int(self.tree.identify_column(event.x)[1:]) - 1
        if 0 <= idx < len(cols) and cols[idx] == "pin":
            row = self.tree.identify_row(event.y)
            if row in self.by_id:
                self.set_pin([row])
                return "break"

    def pin_list_names(self):
        names = {p.get("list") or DEFAULT_PIN_LIST for p in self.pinned.values()}
        return sorted(names | self.pin_lists | {DEFAULT_PIN_LIST})

    def refresh_pin_lists(self):
        values = [_("Alle")] + self.pin_list_names()
        self.pin_box.configure(values=values)
        if self.pin_view.get() not in values:
            self.pin_view.set(_("Alle"))

    def in_view(self, vid):
        p = self.pinned.get(vid)
        if p is None:
            return False
        view = self.pin_view.get()
        return view == _("Alle") or (p.get("list") or DEFAULT_PIN_LIST) == view

    def target_list(self):
        view = self.pin_view.get()
        return DEFAULT_PIN_LIST if view == _("Alle") else view

    def new_pin_list(self):
        name = simpledialog.askstring(_("Neue Merkliste"), _("Name der Merkliste:"), parent=self)
        name = (name or "").strip()
        if name:
            self.pin_lists.add(name)
            self.refresh_pin_lists()
            self.pin_view.set(name)
            self.save()
            self.sync_pins()

    def move_to_list(self):
        picked = self.selected_items()
        if not picked:
            return
        name = simpledialog.askstring(_("In Merkliste verschieben"), _("Name der Merkliste:"),
                                      initialvalue=self.target_list(), parent=self)
        name = (name or "").strip()
        if not name:
            return
        self.pin_lists.add(name)
        for it in picked:
            self.pinned[it["id"]] = {**self.snapshot(it), "list": name}
        self.refresh_pin_lists()
        self.save()
        self.sync_pins()

    @staticmethod
    def snapshot(it):
        return {k: it.get(k) for k in ("id", "title", "channel", "channel_id", "duration",
                                       "views", "date", "verified")}

    def pinned_item(self, vid, p):
        return {
            **{k: v for k, v in p.items() if k != "list"},
            "rank": len(self.items) + 1,
            "date": p.get("date") or self.cache["dates"].get(vid) or None,
            "queued": False,
            "from_pin": True,
            "url": f"https://www.youtube.com/watch?v={vid}",
        }

    def sync_pins(self):
        self.items = [it for it in self.items if not it.get("from_pin")]
        have = {it["id"] for it in self.items}
        for vid, p in self.pinned.items():
            if vid not in have and self.in_view(vid):
                self.items.append(self.pinned_item(vid, p))
        self.by_id = {it["id"]: it for it in self.items}
        self.render()

    def toggle_pin(self):
        ids = [it["id"] for it in self.selected_items()]
        if ids:
            self.set_pin(ids)

    def set_pin(self, ids):
        mark = not all(i in self.pinned for i in ids)
        for i in ids:
            it = self.by_id[i]
            if mark:
                self.pinned[i] = {**self.snapshot(it), "list": self.target_list()}
                log("PIN", f"{i} | {it['title']} | {it['channel']}")
            else:
                self.pinned.pop(i, None)
                log("UNPIN", f"{i} | {it['title']} | {it['channel']}")
        self.refresh_pin_lists()
        self.save()
        self.render()
