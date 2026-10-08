"""Zwischenablage, Hinweise, Update-Leiste, Signalton und Herunterfahren."""

import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import __version__
from .constants import CLIP_RE, SHUTDOWN_SECONDS
from .i18n import _
from .update import RELEASES_URL, fetch_latest_release, is_newer
from .util import log, short_err, shutdown_command


class DesktopMixin:
    def poll_clipboard(self):
        try:
            if self.watch_clipboard and self.focus_displayof() is not None:
                try:
                    text = self.clipboard_get().strip()
                except tk.TclError:
                    text = ""
                if text and text != self.clip_last and len(text) < 300 and CLIP_RE.match(text):
                    self.clip_last = text
                    self.show_clip_bar(text)
        finally:
            self.after(1500, self.poll_clipboard)

    def show_toast(self, text, ms=4500):
        old = getattr(self, "toast", None)
        if old is not None:
            try:
                old.destroy()
            except tk.TclError:
                pass
        p = self.pal
        win = tk.Toplevel(self, bg=p["accent"])
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(win, text=text, justify="left", bg=p["panel"], fg=p["fg"],
                         font=("Segoe UI", 11), padx=18, pady=12)
        label.pack(padx=2, pady=2)
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        x = self.winfo_rootx() + self.winfo_width() - w - 24
        y = self.winfo_rooty() + self.winfo_height() - h - 70
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        win.bind("<Button-1>", lambda e: win.destroy())
        label.bind("<Button-1>", lambda e: win.destroy())
        self.toast = win
        self.after(ms, lambda: win.winfo_exists() and win.destroy())

    def start_update_check(self, manual=False):
        def work():
            try:
                info, err = fetch_latest_release(), None
            except Exception as e:
                info, err = None, short_err(e, 120)
            try:
                self.after(0, lambda: self.on_update_result(info, err, manual))
            except RuntimeError:
                pass
        if manual:
            self.status.set(_("Suche nach Updates …"))
        threading.Thread(target=work, daemon=True).start()

    def on_update_result(self, info, err, manual):
        if info:
            self.update_last = time.time()
            self.save()
            if is_newer(info["version"], __version__):
                if manual or info["version"] != self.update_skip:
                    self.show_update_bar(info)
                return
            if manual:
                messagebox.showinfo(_("Updates"), _("Du hast die neueste Version ({v}).").format(v=__version__))
        elif manual:
            messagebox.showerror(_("Updates"), _("Die Suche nach Updates ist fehlgeschlagen: {e}").format(e=err))

    def show_update_bar(self, info):
        self.update_info = info
        if self.update_bar is None:
            bar = ttk.Frame(self, padding=(8, 4))
            self.update_label = ttk.Label(bar)
            self.update_label.pack(side="left", fill="x", expand=True)
            ttk.Button(bar, text=_("Später"), command=self.hide_update_bar).pack(side="right")
            ttk.Button(bar, text=_("Diese Version überspringen"), command=self.skip_update).pack(
                side="right", padx=6)
            ttk.Button(bar, text=_("Download-Seite öffnen"), command=self.open_update_page).pack(side="right")
            self.update_bar = bar
        self.update_label.configure(text=_("Neue Version {v} verfügbar (installiert: {c}).").format(
            v=info["version"], c=__version__))
        self.update_bar.pack(fill="x", before=self.top_frame)
        self.status.set(_("Neue Version {v} verfügbar.").format(v=info["version"]))

    def hide_update_bar(self):
        if self.update_bar is not None:
            self.update_bar.pack_forget()

    def skip_update(self):
        if self.update_info:
            self.update_skip = self.update_info["version"]
            self.save()
        self.hide_update_bar()

    def open_update_page(self):
        url = (self.update_info or {}).get("url") or RELEASES_URL
        try:
            webbrowser.open(url)
        except Exception:
            pass

    def show_clip_bar(self, url):
        self.clip_url = url
        if self.clip_bar is None:
            bar = ttk.Frame(self, padding=(8, 4))
            self.clip_label = ttk.Label(bar)
            self.clip_label.pack(side="left", fill="x", expand=True)
            ttk.Button(bar, text=_("Ignorieren"), command=self.hide_clip_bar).pack(side="right")
            ttk.Button(bar, text=_("Anzeigen"), command=self.use_clip_url).pack(side="right", padx=6)
            self.clip_bar = bar
        self.clip_label.configure(text=_("YouTube-Link in der Zwischenablage: {u}").format(u=url[:70]))
        self.clip_bar.pack(fill="x", before=self.top_frame)

    def hide_clip_bar(self):
        if self.clip_bar is not None:
            self.clip_bar.pack_forget()

    def use_clip_url(self):
        self.q.delete(0, "end")
        self.q.insert(0, self.clip_url)
        self.hide_clip_bar()
        self.do_search()

    def beep(self):
        try:
            if sys.platform == "win32":
                import winsound
                winsound.MessageBeep()
            else:
                self.bell()
        except Exception:
            pass

    def on_queue_finished(self):
        if any(j["status"] in ("queued", "running") for j in self.jobs):
            return
        fresh = [j for j in self.jobs if j["status"] == "done" and not j.get("notified")]
        if not fresh:
            return
        for j in fresh:
            j["notified"] = True
        failed = any(j["status"] == "failed" for j in self.jobs)
        self.status.set(_("Warteschlange fertig: {n} Download(s)").format(n=len(fresh)))
        if self.done_action in ("sound", "shutdown"):
            self.beep()
        if self.done_action == "shutdown":
            if failed:
                self.status.set(_("Warteschlange fertig, aber es gab Fehler. Der PC wird nicht heruntergefahren."))
            else:
                self.start_shutdown_countdown()

    def start_shutdown_countdown(self):
        if self.shutdown_win and self.shutdown_win.winfo_exists():
            return
        win = tk.Toplevel(self)
        win.title(_("PC herunterfahren"))
        win.transient(self)
        self.shutdown_win = win
        self.theme_window(win)
        self.shutdown_left = SHUTDOWN_SECONDS
        label = ttk.Label(win, padding=20)
        label.pack()
        ttk.Button(win, text=_("Abbrechen"), command=win.destroy).pack(pady=(0, 16))
        self.shutdown_label = label

        def tick():
            if not win.winfo_exists():
                return
            if self.shutdown_left <= 0:
                self.run_shutdown()
                win.destroy()
                return
            label.configure(text=_("Alle Downloads sind fertig. Der PC wird in {s} Sekunden heruntergefahren.").format(
                s=self.shutdown_left))
            self.shutdown_left -= 1
            win.after(1000, tick)

        tick()

    def run_shutdown(self):
        log("SHUTDOWN", "queue finished")
        try:
            subprocess.Popen(shutdown_command())
        except Exception as err:
            self.status.set(_("Herunterfahren fehlgeschlagen: {e}").format(e=short_err(err)))
