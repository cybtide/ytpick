"""Warteschlange, Formatdialog und Download-Ausführung."""

import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .compat import yt_dlp
from .constants import DEFAULT_FMT, HEIGHTS, SAVED_FMT_KEYS
from .i18n import _
from .util import (
    detect_browsers, in_window, is_bot_error, log, now, parse_clock, parse_time, short_err,
)
from .ytdl import Cancelled, download_opts, verify_download


class DownloadMixin:
    def do_download(self):
        picked = self.selected_items()
        if not picked:
            messagebox.showinfo(_("Hinweis"), _("Bitte erst ein oder mehrere Videos auswählen."))
            return
        self.enqueue(picked, dict(self.fmt), self.mode.get())

    def do_download_options(self):
        picked = self.selected_items()
        if not picked:
            messagebox.showinfo(_("Hinweis"), _("Bitte erst ein oder mehrere Videos auswählen."))
            return
        self.open_format_dialog(picked)

    def open_format_dialog(self, picked):
        if self.fmt_win and self.fmt_win.winfo_exists():
            self.fmt_win.destroy()
        win = tk.Toplevel(self)
        win.title(_("Download-Optionen"))
        win.transient(self)
        self.fmt_win = win
        self.theme_window(win)
        f = {**DEFAULT_FMT, **self.fmt}
        v_mode = tk.StringVar(value=self.mode.get())
        v_h = tk.StringVar(value=_("Beste") if not f["height"] else f"{f['height']}p")
        v_subs = tk.BooleanVar(value=bool(f["subs"]))
        v_langs = tk.StringVar(value=f["sub_langs"])
        v_chap = tk.BooleanVar(value=bool(f["chapters"]))
        v_fold = tk.BooleanVar(value=bool(f["channel_folder"]))
        v_def = tk.BooleanVar(value=False)
        v_embed = tk.BooleanVar(value=bool(f["embed"]))
        v_cut_a = tk.StringVar(value="")
        v_cut_b = tk.StringVar(value="")

        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        title = picked[0]["title"] if len(picked) == 1 else _("{n} Videos").format(n=len(picked))
        ttk.Label(body, text=title[:70], font=("Segoe UI", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Label(body, text=_("Format")).grid(row=1, column=0, sticky="w")
        row = ttk.Frame(body)
        row.grid(row=1, column=1, columnspan=2, sticky="w", pady=3)
        for text, val in (("MKV", "mkv"), ("MP4", "mp4"), (_("Nur Audio"), "audio"), ("MP3", "mp3")):
            ttk.Radiobutton(row, text=text, value=val, variable=v_mode).pack(side="left", padx=(0, 8))
        ttk.Label(body, text=_("Max. Auflösung")).grid(row=2, column=0, sticky="w")
        labels = [_("Beste") if h == 0 else f"{h}p" for h in HEIGHTS]
        ttk.Combobox(body, textvariable=v_h, values=labels, state="readonly", width=10).grid(
            row=2, column=1, sticky="w", pady=3)
        ttk.Checkbutton(body, text=_("Untertitel einbetten, Sprachen:"), variable=v_subs).grid(
            row=3, column=0, sticky="w", pady=3)
        ttk.Entry(body, textvariable=v_langs, width=12).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Checkbutton(body, text=_("Kapitel einbetten"), variable=v_chap).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(body, text=_("Eigener Ordner pro Kanal"), variable=v_fold).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Checkbutton(body, text=_("Cover und Metadaten einbetten"), variable=v_embed).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Label(body, text=_("Ausschnitt (Start – Ende, z.B. 1:20 – 3:45)")).grid(
            row=7, column=0, columnspan=3, sticky="w", pady=(8, 0))
        cut = ttk.Frame(body)
        cut.grid(row=8, column=0, columnspan=3, sticky="w", pady=3)
        ttk.Entry(cut, textvariable=v_cut_a, width=9).pack(side="left")
        ttk.Label(cut, text="–").pack(side="left", padx=6)
        ttk.Entry(cut, textvariable=v_cut_b, width=9).pack(side="left")
        ttk.Checkbutton(body, text=_("Als Standard speichern"), variable=v_def).grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(10, 0))

        def go():
            label = v_h.get()
            h = 0 if label == _("Beste") else int(label.rstrip("p"))
            try:
                a, b = parse_time(v_cut_a.get()), parse_time(v_cut_b.get())
                if a is not None and b is not None and b <= a:
                    raise ValueError("range")
            except ValueError:
                messagebox.showerror(_("Ausschnitt"), _("Ungültiger Ausschnitt. Beispiel: 1:20 und 3:45."),
                                     parent=win)
                return
            fmt = {"height": h, "subs": v_subs.get(), "sub_langs": v_langs.get().strip() or "de,en",
                   "chapters": v_chap.get(), "channel_folder": v_fold.get(), "embed": v_embed.get(),
                   "cut_start": a, "cut_end": b}
            if v_def.get():
                self.fmt = {**DEFAULT_FMT, **{k: fmt[k] for k in SAVED_FMT_KEYS}}
                self.mode.set(v_mode.get())
                self.save()
            win.destroy()
            self.enqueue(picked, fmt, v_mode.get())

        btns = ttk.Frame(win, padding=(14, 0, 14, 14))
        btns.pack(fill="x")
        ttk.Button(btns, text=_("Herunterladen"), command=go).pack(side="right")
        ttk.Button(btns, text=_("Abbrechen"), command=win.destroy).pack(side="right", padx=6)
        win.bind("<Return>", lambda e: go())
        win.bind("<Escape>", lambda e: win.destroy())

    def mode_label(self, mode):
        return {"mkv": "MKV", "mp4": "MP4", "audio": _("Audio"), "mp3": "MP3"}.get(mode, mode)

    def describe_download(self, vid):
        rec = self.downloads.get(vid)
        if not rec:
            return _("unbekannt")
        h = rec.get("height") or 0
        return self.mode_label(rec.get("mode", "?")) + (f" ≤{h}p" if h else "")

    def enqueue_all(self):
        items = list(self.shown)
        if not items:
            return
        if len(items) > 20 and not messagebox.askyesno(
                _("Alle sichtbaren laden"), _("{n} Videos in die Warteschlange legen?").format(n=len(items))):
            return
        self.enqueue(items, dict(self.fmt), self.mode.get())

    def enqueue(self, picked, fmt, mode, ask=True):
        active = {j["item"]["id"] for j in self.jobs if j["status"] in ("queued", "running")}
        picked = [it for it in picked if it["id"] not in active]
        dups = [it for it in picked if self.is_downloaded(it["id"])]
        if dups and ask:
            names = ", ".join(f"{d['title'][:30]} ({self.describe_download(d['id'])})" for d in dups[:3])
            answer = messagebox.askyesnocancel(
                _("Bereits geladen"),
                _("{n} Video(s) wurden schon geladen: {names}\n\nJa = trotzdem laden, Nein = überspringen, "
                  "Abbrechen = nichts tun.").format(n=len(dups), names=names))
            if answer is None:
                return
            if answer is False:
                skip = {d["id"] for d in dups}
                picked = [it for it in picked if it["id"] not in skip]
        base = self.ydl_opts()
        if self.rate_mb > 0:
            base["ratelimit"] = int(self.rate_mb * 1048576)
        outdir = str(Path(self.outdir.get()).expanduser())
        for it in picked:
            self.job_seq += 1
            self.jobs.append({"n": self.job_seq, "item": it, "mode": mode,
                              "fmt": {**fmt, "name": self.name_preset},
                              "outdir": outdir, "base": base, "status": "queued", "pct": 0.0,
                              "speed": "", "msg": "", "cancel": False})
        if picked:
            log("QUEUE", f"{len(picked)} Video(s) hinzugefügt")
            self.job_event.set()
        if self.open_queue_on_add:
            self.open_queue()
        self.render()
        self.update_queue_status()

    def in_schedule(self):
        try:
            start, end = parse_clock(self.window_start), parse_clock(self.window_end)
        except ValueError:
            return True
        n = datetime.now()
        return in_window(n.hour * 60 + n.minute, start, end)

    def _queue_worker(self):
        while True:
            self.job_event.clear()
            job = next((j for j in self.jobs if j["status"] == "queued"), None)
            if job is None:
                self.job_event.wait()
                continue
            while self.paused and not job["cancel"] and job["status"] == "queued":
                time.sleep(0.3)
            while (self.window_on and not self.in_schedule() and not job["cancel"]
                   and job["status"] == "queued"):
                job["msg"] = _("wartet auf Zeitfenster {a}–{b}").format(a=self.window_start, b=self.window_end)
                time.sleep(5)
            job["msg"] = ""
            if job["status"] != "queued" or job["cancel"]:
                continue
            self.run_job(job)
            self.after(0, self.render)
            self.after(0, self.update_queue_status)
            self.after(0, self.on_queue_finished)

    def run_job(self, job):
        it = job["item"]
        outdir = Path(job["outdir"])
        job["status"] = "running"
        self.after(0, self.render)
        try:
            outdir.mkdir(parents=True, exist_ok=True)
            opts = download_opts(job["base"], outdir, job["mode"], job["fmt"],
                                 lambda d, j=job: self._hook(j, d), it.get("rank"))
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(it["url"], download=True)
            good, reason, path = verify_download(info, it["id"], outdir)
            if good:
                job["status"], job["pct"], job["msg"] = "done", 100.0, Path(path).name
                self.history.add(it["id"])
                self.disk_ids.add(it["id"])
                try:
                    file_size = Path(path).stat().st_size
                except OSError:
                    file_size = 0
                self.downloads[it["id"]] = {
                    "title": it["title"], "channel": it["channel"], "mode": job["mode"],
                    "height": job["fmt"].get("height", 0), "at": now(), "file": path,
                    "size": file_size, "duration": it.get("duration") or 0}
                log("DOWNLOAD", f"{it['id']} | {it['title']} | {it['channel']} | {path}")
                self.after(0, self.save)
                self.after(0, self.render)
            else:
                job["status"], job["msg"] = "failed", _("Prüfung fehlgeschlagen: {r}").format(r=reason)
                log("VERIFY FAIL", f"{it['id']} | {reason}")
        except Cancelled:
            job["status"], job["msg"] = "cancelled", ""
            log("CANCEL", f"{it['id']} | {it['title']}")
        except Exception as err:
            if job["cancel"]:
                job["status"], job["msg"] = "cancelled", ""
            else:
                job["status"], job["msg"] = "failed", short_err(err, 160)
                log("DOWNLOAD FAIL", f"{it['id']} | {short_err(err, 200)}")
                if is_bot_error(err):
                    self.after(0, self.offer_cookies)

    def _hook(self, job, d):
        if job["cancel"]:
            raise Cancelled()
        while self.paused:
            if job["cancel"]:
                raise Cancelled()
            time.sleep(0.3)
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                job["pct"] = min(100.0, (d.get("downloaded_bytes") or 0) * 100.0 / total)
            sp = d.get("speed")
            job["speed"] = f"{sp / 1048576:.1f} MB/s" if sp else ""
        elif d.get("status") == "finished":
            job["pct"], job["speed"], job["msg"] = 100.0, "", _("Verarbeite …")

    def update_queue_status(self):
        total = len(self.jobs)
        done = sum(1 for j in self.jobs if j["status"] in ("done", "failed", "cancelled"))
        failed = sum(1 for j in self.jobs if j["status"] == "failed")
        if not total:
            return
        text = _("Warteschlange: {d}/{t} fertig").format(d=done, t=total)
        if failed:
            text += _(", {f} fehlgeschlagen").format(f=failed)
        self.status.set(text)

    def job_state_text(self, j):
        if j["status"] == "running" and self.paused:
            return _("pausiert")
        return {"queued": _("wartet"), "running": _("lädt"), "done": _("fertig"),
                "failed": _("Fehler"), "cancelled": _("abgebrochen")}[j["status"]]

    def open_queue(self):
        if self.q_win and self.q_win.winfo_exists():
            self.q_win.lift()
            self.refresh_queue()
            return
        win = tk.Toplevel(self)
        win.title(_("Warteschlange"))
        win.geometry("760x380")
        win.transient(self)
        self.q_win = win
        self.theme_window(win)
        btns = ttk.Frame(win, padding=8)
        btns.pack(side="bottom", fill="x")
        self.q_bar = ttk.Progressbar(btns, mode="determinate", maximum=100, length=160)
        self.q_bar.pack(side="left")
        self.q_pause = ttk.Button(btns, text=_("Pause"), command=self.toggle_pause)
        self.q_pause.pack(side="right")
        ttk.Button(btns, text=_("Fertige entfernen"), command=self.clear_finished).pack(
            side="right", padx=6)
        ttk.Button(btns, text=_("Alle abbrechen"), command=lambda: self.cancel_jobs(all_jobs=True)).pack(
            side="right")
        ttk.Button(btns, text=_("Auswahl abbrechen"), command=self.cancel_jobs).pack(side="right", padx=6)
        cols = ("titel", "status", "fortschritt", "info")
        tv = ttk.Treeview(win, columns=cols, show="headings", selectmode="extended")
        for key, text, w, a in (("titel", _("Titel"), 300, "w"), ("status", _("Status"), 80, "w"),
                                ("fortschritt", _("Fortschritt"), 150, "w"), ("info", _("Info"), 190, "w")):
            tv.heading(key, text=text)
            tv.column(key, width=w, anchor=a, stretch=(key == "titel"))
        tv.pack(fill="both", expand=True, padx=8, pady=(8, 0))
        self.q_tree = tv
        self.q_rows = {}
        self.apply_theme()
        self.queue_tick()

    def queue_tick(self):
        win = self.q_win
        if not (win and win.winfo_exists()):
            return
        self.refresh_queue()
        win.after(400, self.queue_tick)

    def refresh_queue(self):
        win = self.q_win
        if not (win and win.winfo_exists()):
            return
        tv = self.q_tree
        live = {str(j["n"]) for j in self.jobs}
        for iid in list(tv.get_children()):
            if iid not in live:
                tv.delete(iid)
        for j in self.jobs:
            iid = str(j["n"])
            filled = int(j["pct"] // 10)
            bar = "█" * filled + "░" * (10 - filled) + f" {j['pct']:.0f} %"
            info = j["speed"] or j["msg"]
            vals = (j["item"]["title"], self.job_state_text(j), bar, info)
            if tv.exists(iid):
                tv.item(iid, values=vals)
            else:
                tv.insert("", "end", iid=iid, values=vals)
        running = next((j for j in self.jobs if j["status"] == "running"), None)
        self.q_bar["value"] = running["pct"] if running else 0
        self.q_pause.configure(text=_("Fortsetzen") if self.paused else _("Pause"))

    def toggle_pause(self):
        self.paused = not self.paused
        log("QUEUE", "pausiert" if self.paused else "fortgesetzt")
        self.refresh_queue_once()

    def refresh_queue_once(self):
        if self.q_win and self.q_win.winfo_exists():
            self.q_pause.configure(text=_("Fortsetzen") if self.paused else _("Pause"))

    def cancel_jobs(self, all_jobs=False):
        if all_jobs:
            targets = list(self.jobs)
        else:
            sel = {int(i) for i in self.q_tree.selection()}
            targets = [j for j in self.jobs if j["n"] in sel]
        for j in targets:
            if j["status"] == "queued":
                j["status"] = "cancelled"
            elif j["status"] == "running":
                j["cancel"] = True
        self.render()
        self.update_queue_status()

    def clear_finished(self):
        self.jobs[:] = [j for j in self.jobs if j["status"] in ("queued", "running")]
        self.refresh_queue_once()
        if self.q_win and self.q_win.winfo_exists():
            for iid in list(self.q_tree.get_children()):
                if iid not in {str(j["n"]) for j in self.jobs}:
                    self.q_tree.delete(iid)

    def offer_cookies(self):
        if self.cookie_offered or self.cookies.get() != "keine":
            return
        found = detect_browsers()
        if not found:
            return
        self.cookie_offered = True
        name = found[0]
        if messagebox.askyesno(
                _("YouTube verlangt eine Anmeldung"),
                _("YouTube verlangt einen Bot-Check. {b} ist auf diesem Computer installiert.\n\n"
                  "Cookies aus {b} verwenden? Du musst dort bei YouTube angemeldet sein.").format(b=name)):
            self.cookies.set(name)
            self.on_cookies_changed()
