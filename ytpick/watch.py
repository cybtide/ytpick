"""Beobachtete Kanäle."""

import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk

from .constants import WATCH_LIMIT, WATCH_NEW_MAX, WATCH_SEEN_MAX
from .i18n import _
from .util import clean_text, is_bot_error, log, short_err
from .ytdl import fetch_flat, normalize, parse_query


class WatchMixin:
    def watch_selected_channel(self):
        picked = self.selected_items()
        if not picked:
            return
        for it in picked:
            if it.get("channel_id"):
                self.add_watch(f"https://www.youtube.com/channel/{it['channel_id']}/videos", it["channel"])
            else:
                self.status.set(_("Für diesen Kanal fehlt die Kanal-ID. Bitte über @handle hinzufügen."))

    def add_watch(self, url, name=""):
        key = url.lower()
        if key in self.watch:
            self.status.set(_("Kanal wird bereits beobachtet."))
            return
        self.status.set(_("Kanal wird hinzugefügt …"))
        threading.Thread(target=self._add_watch, args=(key, url, name), daemon=True).start()

    def _add_watch(self, key, url, name):
        try:
            info, entries = fetch_flat(url, WATCH_LIMIT, self.ydl_opts())
        except Exception as err:
            log("WATCH FAIL", f"{url} | {short_err(err, 200)}")
            self.set_status(_("Kanal konnte nicht hinzugefügt werden: {e}").format(e=short_err(err)))
            return
        title = clean_text(info.get("channel") or info.get("uploader") or info.get("title")) or name or url
        ids = [e["id"] for e in entries]

        def done():
            self.watch[key] = {"name": title, "url": url, "seen": ids[:WATCH_SEEN_MAX], "new": [],
                               "checked": time.time()}
            log("WATCH", f"{title} | {url}")
            self.save()
            self.refresh_watch()
            self.status.set(_("Kanal beobachtet: {n}").format(n=title))

        self.after(0, done)

    def open_watch(self):
        if self.w_win and self.w_win.winfo_exists():
            self.w_win.lift()
            return
        win = tk.Toplevel(self)
        win.title(_("Beobachtete Kanäle"))
        win.geometry("640x400")
        win.transient(self)
        self.w_win = win
        self.theme_window(win)
        top = ttk.Frame(win, padding=8)
        top.pack(fill="x")
        self.w_entry = ttk.Entry(top)
        self.w_entry.pack(side="left", fill="x", expand=True)
        self.w_entry.bind("<Return>", lambda e: self.add_watch_from_entry())
        ttk.Button(top, text=_("Hinzufügen (@handle oder URL)"), command=self.add_watch_from_entry).pack(
            side="left", padx=(6, 0))
        btns = ttk.Frame(win, padding=8)
        btns.pack(side="bottom", fill="x")
        ttk.Button(btns, text=_("Alle prüfen"), command=self.check_watch).pack(side="left")
        ttk.Button(btns, text=_("Entfernen"), command=self.remove_watch).pack(side="right")
        ttk.Button(btns, text=_("Neue Videos anzeigen"), command=self.show_watch_new).pack(side="right", padx=6)
        cols = ("kanal", "neu", "geprueft")
        tv = ttk.Treeview(win, columns=cols, show="headings", selectmode="extended")
        for key, text, w, a in (("kanal", _("Kanal"), 320, "w"), ("neu", _("Neu"), 70, "e"),
                                ("geprueft", _("Zuletzt geprüft"), 170, "w")):
            tv.heading(key, text=text)
            tv.column(key, width=w, anchor=a, stretch=(key == "kanal"))
        tv.pack(fill="both", expand=True, padx=8)
        self.w_tree = tv
        self.apply_theme()
        self.refresh_watch()

    def add_watch_from_entry(self):
        spec = parse_query(self.w_entry.get())
        if spec["kind"] != "channel":
            self.status.set(_("Bitte @handle oder eine Kanal-URL eingeben."))
            return
        self.w_entry.delete(0, "end")
        self.add_watch(spec["url"])

    def refresh_watch(self):
        if not (self.w_win and self.w_win.winfo_exists()):
            return
        tv = self.w_tree
        tv.delete(*tv.get_children())
        for key, w in self.watch.items():
            checked = datetime.fromtimestamp(w["checked"]).strftime("%d.%m.%Y %H:%M") if w.get("checked") else "–"
            tv.insert("", "end", iid=key, values=(w["name"], len(w.get("new", [])), checked))

    def watch_keys(self, selected_only=False):
        if selected_only:
            return [k for k in self.w_tree.selection() if k in self.watch]
        return list(self.watch)

    def check_watch(self):
        keys = self.watch_keys()
        if not keys:
            self.status.set(_("Keine Kanäle in der Beobachtungsliste."))
            return
        self.status.set(_("Prüfe {n} Kanal/Kanäle …").format(n=len(keys)))
        threading.Thread(target=self._check_watch, args=(keys, self.ydl_opts()), daemon=True).start()

    def _check_watch(self, keys, base):
        total_new, errors, bot_seen = 0, 0, False
        for n, key in enumerate(keys):
            w = self.watch.get(key)
            if not w:
                continue
            if n:
                time.sleep(1.0)
            try:
                info, entries = fetch_flat(w["url"], WATCH_LIMIT, base)
            except Exception as err:
                errors += 1
                log("WATCH FAIL", f"{w['url']} | {short_err(err, 200)}")
                if is_bot_error(err):
                    bot_seen = True
                    break
                continue
            seen = set(w["seen"])
            known_new = {x["id"] for x in w.get("new", [])}
            fresh = []
            for e in entries:
                if e["id"] in seen or e["id"] in known_new:
                    continue
                fresh.append(normalize(e, info))
            w["new"] = (fresh + w.get("new", []))[:WATCH_NEW_MAX]
            w["checked"] = time.time()
            total_new += len(fresh)
        msg = _("Prüfung beendet: {n} neue Videos").format(n=total_new)
        if errors:
            msg += _(", {e} Fehler (siehe Log)").format(e=errors)

        def done():
            self.save()
            self.refresh_watch()
            self.status.set(msg)
            if bot_seen:
                self.offer_cookies()

        self.after(0, done)

    def remove_watch(self):
        keys = self.watch_keys(selected_only=True)
        for k in keys:
            w = self.watch.pop(k, {})
            log("UNWATCH", f"{w.get('name', '?')} | {k}")
        self.save()
        self.refresh_watch()

    def show_watch_new(self):
        keys = self.watch_keys(selected_only=True) or self.watch_keys()
        items = []
        for k in keys:
            items.extend(self.watch[k].get("new", []))
        if not items:
            self.status.set(_("Keine neuen Videos. Erst „Alle prüfen“ ausführen."))
            return
        for k in keys:
            w = self.watch[k]
            w["seen"] = ([x["id"] for x in w.get("new", [])] + w["seen"])[:WATCH_SEEN_MAX]
            w["new"] = []
        self.save()
        self.refresh_watch()
        self.token += 1
        self.date_abort = False
        self.date_total = self.date_done = self.date_fail = 0
