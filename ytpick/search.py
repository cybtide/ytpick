"""Suche, Nachladen und Veröffentlichungsdaten."""

import threading
import time
from datetime import datetime

from .compat import yt_dlp
from .constants import CACHE_TTL, CHANNEL_POOL, HISTORY_MAX, POOL, RESULTS
from .i18n import _
from .util import QuietLogger, age_text, easter_egg, fmt_date, is_bot_error, log, short_err
from .ytdl import normalize, parse_query


class SearchMixin:
    def remember_query(self, query):
        self.search_hist = ([query] + [x for x in self.search_hist if x != query])[:HISTORY_MAX]
        self.q.configure(values=self.search_hist)

    def do_search(self, force=False):
        query = self.q.get().strip()
        if not query:
            return
        self.token += 1
        self.date_abort = False
        self.date_total = self.date_done = self.date_fail = 0
        egg = easter_egg(query)
        if egg:
            self.show_toast(_(egg))
        spec = parse_query(query)
        self.remember_query(query)
        self.cur_spec = spec if spec["kind"] in ("search", "channel", "playlist") else None
        self.pool_size = POOL if spec["kind"] == "search" else CHANNEL_POOL
        self.pool_end = False
        entry = self.cache["searches"].get(spec["key"])
        if entry and not force and time.time() - entry["at"] < CACHE_TTL:
            self.pool_size = max(self.pool_size, len(entry["items"]))
            self._show(entry["items"], self.token,
                       _("{l} · aus Cache ({a})").format(l=spec["label"], a=age_text(entry["at"])),
                       CHANNEL_POOL if spec["kind"] == "playlist" else RESULTS)
            return
        self.status.set(_("{l} … lädt").format(l=spec["label"]))
        threading.Thread(target=self._search, args=(spec, self.token), daemon=True).start()

    def _search(self, spec, token, pool=None, keep_limit=False):
        try:
            opts = {"quiet": True, "no_warnings": True, "extract_flat": True,
                    "logger": QuietLogger()}
            url = spec["url"]
            if spec["kind"] in ("channel", "playlist"):
                opts["playlistend"] = pool or CHANNEL_POOL
            elif pool:
                url = f"ytsearch{pool}:" + url.split(":", 1)[1]
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            entries = info.get("entries") or ([info] if info.get("id") else [])
            items = []
            terms = [t for t in spec["term"].lower().split() if t]
            for e in entries:
                if not e or not e.get("id"):
                    continue
                n = normalize(e, info if spec["kind"] in ("channel", "playlist") else None)
                if terms and not all(t in n["title"].lower() for t in terms):
                    continue
                items.append(n)
        except Exception as err:
            log("SEARCH FAIL", f"{spec['key']} | {short_err(err, 200)}")
            self.set_status(_("Fehler bei der Suche: {e}").format(e=short_err(err)))
            if is_bot_error(err):
                self.after(0, self.offer_cookies)
            return
        self.after(0, lambda: self._finish_search(spec, items, token, keep_limit))

    def _finish_search(self, spec, items, token, keep_limit=False):
        if items:
            self.cache["searches"][spec["key"]] = {"at": time.time(), "items": items}
            self.save_cache()
        if token == self.token:
            limit = self.limit if keep_limit else (CHANNEL_POOL if spec["kind"] == "playlist" else RESULTS)
            self._show(items, token, _("{l} · frisch geladen").format(l=spec["label"]), limit)
            if keep_limit and len(items) <= self.pool_prev:
                self.pool_end = True
                self.status.set(self.status.get() + _(" · keine weiteren Treffer"))

    def _show(self, raw_items, token, note, limit=RESULTS):
        if token != self.token:
            return
        self.limit = limit
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
        for vid, p in self.pinned.items():
            if vid not in seen and self.in_view(vid):
                self.items.append(self.pinned_item(vid, p))
        self.by_id = {it["id"]: it for it in self.items}
        self.save()
        self.refresh_disk()
        self.sort_col, self.sort_rev = "rank", False
        self.update_headings()
        self.render()
        missing = sum(1 for it in self.shown if it["date"] is None)
        self.status.set(_("{note} · {n} sichtbar (Pool {p})").format(note=note, n=len(self.shown), p=len(self.items))
                        + self.explain_hidden()
                        + (_(" · Datum fehlt bei {m}").format(m=missing) if missing and self.fetch_dates.get() else ""))

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
            self.status.set(_("YouTube verlangt einen Bot-Check. Wähle in den Einstellungen einen Browser bei "
                              "'Cookies aus Browser' (Datum bleibt bis dahin leer)."))
            self.offer_cookies()
        elif self.date_done >= self.date_total:
            if self.cache_dirty:
                self.save_cache()
            if self.date_fail:
                self.status.set(_("Datum bei {n} Video(s) nicht ladbar. Grund: {r}").format(
                    n=self.date_fail, r=self.date_last_err or _("unbekannt (siehe Log)")))
            else:
                self.status.set(_("{n} Treffer sichtbar. Datum vollständig geladen.").format(n=len(self.shown)))
            if self.sort_col == "datum" or self.filters_active():
                self.render()
        else:
            self.status.set(_("Lade Upload-Datum … {d}/{t}").format(d=self.date_done, t=self.date_total))
