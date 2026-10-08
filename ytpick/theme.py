"""Fenster-Symbol, Vorschaubilder, Farbschema und Hilfedialoge."""

import shutil
import sys
import threading
import tkinter as tk
from tkinter import ttk
from urllib.request import Request, urlopen

from . import __version__
from .compat import HAVE_PIL, Image, ImageOps, ImageTk, YTDLP_VERSION
from .constants import BASE_DIR, DARK, LIGHT, MAX_THUMBS, THUMB_DIR, THUMB_H, THUMB_W
from .i18n import HELP_TEXT, HELP_TEXT_EN, _, is_english
from .util import log, set_titlebar, short_err
from .ytdl import installed_ytdlp_version, upgrade_ytdlp


class ThemeMixin:
    def set_icon(self):
        assets = BASE_DIR / "assets"
        ico, png = assets / "icon.ico", assets / "icon.png"
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("cybtide.ytpick")
            except Exception:
                pass
        try:
            if sys.platform == "win32" and ico.exists():
                self.iconbitmap(default=str(ico))
            elif png.exists():
                self.app_icon = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self.app_icon)
        except tk.TclError:
            pass

    def row_height(self):
        return THUMB_H + 6 if self.show_thumbs.get() else 22

    def apply_thumbs(self):
        on = self.show_thumbs.get()
        self.tree.configure(show="tree headings" if on else "headings")
        ttk.Style(self).configure("Treeview", rowheight=self.row_height())
        if on:
            self.ensure_thumbs()

    def prune_thumbs(self):
        try:
            files = sorted(THUMB_DIR.glob("*.jpg"), key=lambda f: f.stat().st_mtime)
            for f in files[:max(0, len(files) - MAX_THUMBS)]:
                f.unlink()
        except Exception:
            pass

    def ensure_thumbs(self):
        if not (self.show_thumbs.get() and HAVE_PIL):
            return
        for it in self.shown:
            if it["id"] not in self.thumb_req:
                self.thumb_req.add(it["id"])
                self.thumbq.put(it["id"])

    def _thumb_worker(self):
        while True:
            vid = self.thumbq.get()
            img = None
            try:
                path = THUMB_DIR / f"{vid}.jpg"
                if not path.exists():
                    THUMB_DIR.mkdir(parents=True, exist_ok=True)
                    req = Request(f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                                  headers={"User-Agent": "Mozilla/5.0"})
                    with urlopen(req, timeout=15) as r:
                        data = r.read()
                    path.write_bytes(data)
                with Image.open(path) as im:
                    img = ImageOps.fit(im.convert("RGB"), (THUMB_W, THUMB_H))
            except Exception:
                img = None
            if img is not None:
                self.after(0, lambda v=vid, i=img: self._set_thumb(v, i))

    def _set_thumb(self, vid, img):
        photo = ImageTk.PhotoImage(img)
        self.thumbs[vid] = photo
        if self.show_thumbs.get() and self.tree.exists(vid):
            self.tree.item(vid, image=photo)

    def style_text(self, widget):
        p = self.pal
        widget.configure(bg=p["field"], fg=p["fg"], selectbackground=p["sel"],
                         selectforeground="#ffffff", relief="flat", highlightthickness=0,
                         borderwidth=0)
        if isinstance(widget, tk.Text):
            widget.configure(insertbackground=p["fg"])

    def theme_window(self, win):
        win.configure(bg=self.pal["bg"])
        set_titlebar(win, self.dark.get())

    def apply_theme(self):
        p = DARK if self.dark.get() else LIGHT
        self.pal = p
        st = ttk.Style(self)
        st.theme_use("clam")
        self.configure(bg=p["bg"])
        st.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                     bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"],
                     troughcolor=p["panel"], focuscolor=p["bg"], insertcolor=p["fg"])
        st.configure("TButton", background=p["panel"], foreground=p["fg"],
                     padding=(8, 3), borderwidth=1)
        st.map("TButton", background=[("active", p["sel"]), ("pressed", p["sel"])],
               foreground=[("disabled", p["muted"]), ("active", "#ffffff")])
        for w in ("TCheckbutton", "TRadiobutton"):
            st.configure(w, background=p["bg"], foreground=p["fg"])
            st.map(w, background=[("active", p["bg"])],
                   indicatorcolor=[("selected", p["accent"]), ("!selected", p["field"])])
        st.configure("TEntry", fieldbackground=p["field"], foreground=p["fg"], insertcolor=p["fg"])
        st.configure("TCombobox", fieldbackground=p["field"], background=p["panel"],
                     foreground=p["fg"], arrowcolor=p["fg"],
                     selectbackground=p["field"], selectforeground=p["fg"])
        st.map("TCombobox", fieldbackground=[("readonly", p["field"])],
               foreground=[("readonly", p["fg"])],
               selectbackground=[("readonly", p["field"])],
               selectforeground=[("readonly", p["fg"])])
        self.option_add("*TCombobox*Listbox.background", p["field"])
        self.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", p["sel"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        st.configure("Treeview", background=p["field"], fieldbackground=p["field"],
                     foreground=p["fg"], rowheight=self.row_height(), borderwidth=0)
        st.map("Treeview", background=[("selected", p["sel"])],
               foreground=[("selected", "#ffffff")])
        st.configure("Treeview.Heading", background=p["header"], foreground=p["fg"],
                     relief="flat", padding=(6, 4))
        st.map("Treeview.Heading", background=[("active", p["sel"])])
        st.configure("TNotebook", background=p["bg"], borderwidth=0)
        st.configure("TNotebook.Tab", background=p["panel"], foreground=p["fg"], padding=(12, 5))
        st.map("TNotebook.Tab", background=[("selected", p["sel"])],
               foreground=[("selected", "#ffffff")])
        st.configure("TScrollbar", background=p["header"], troughcolor=p["bg"],
                     arrowcolor=p["fg"], bordercolor=p["bg"])
        st.map("TScrollbar", background=[("active", p["sel"])])

        self.tree.tag_configure("downloaded", foreground=p["dl"])
        self.tree.tag_configure("hidden", foreground=p["hid"])
        self.tree.tag_configure("queued", foreground=p["accent"])
        for menu in (self.ctx, self.tool_menu):
            menu.configure(bg=p["panel"], fg=p["fg"], activebackground=p["sel"],
                           activeforeground="#ffffff", bd=0)
        st.configure("TMenubutton", background=p["panel"], foreground=p["fg"], arrowcolor=p["fg"],
                     padding=(8, 3))
        st.map("TMenubutton", background=[("active", p["sel"])], foreground=[("active", "#ffffff")])
        set_titlebar(self, self.dark.get())
        if self.bl_win and self.bl_win.winfo_exists():
            self.theme_window(self.bl_win)
            if self.bl_log:
                self.style_text(self.bl_log)
        for w in (self.q_win, self.w_win, self.fmt_win, self.h_win, self.s_win):
            if w and w.winfo_exists():
                self.theme_window(w)
        if self.set_win and self.set_win.winfo_exists():
            self.theme_window(self.set_win)
            self.style_text(self.set_list)
        if self.readme_win and self.readme_win.winfo_exists():
            self.theme_window(self.readme_win)
            if self.readme_text:
                self.style_text(self.readme_text)
                self.readme_text.tag_configure("ok", foreground=p["ok"])
                self.readme_text.tag_configure("bad", foreground=p["bad"])

    def on_theme_toggle(self):
        self.apply_theme()
        self.save()

    def system_check(self):
        return [
            ("ffmpeg", shutil.which("ffmpeg") is not None,
             _("gefunden") if shutil.which("ffmpeg") else _("fehlt (nötig zum Zusammenfügen von Video und Ton)")),
            ("deno", shutil.which("deno") is not None,
             _("gefunden") if shutil.which("deno") else _("fehlt (nötig für YouTube-Downloads)")),
            ("ytpick", True, _("Version {v}").format(v=__version__)),
            ("yt-dlp", True, _("Version {v}").format(v=YTDLP_VERSION)),
        ]

    def show_readme_dialog(self):
        if self.readme_win and self.readme_win.winfo_exists():
            self.readme_win.lift()
            return
        win = tk.Toplevel(self)
        win.title(_("Kurzanleitung"))
        win.geometry("700x600")
        win.transient(self)
        self.readme_win = win

        btns = ttk.Frame(win, padding=10)
        btns.pack(side="bottom", fill="x")
        ttk.Checkbutton(btns, text=_("Beim Start anzeigen"), variable=self.show_readme,
                        command=self.save).pack(side="left")
        ttk.Button(btns, text=_("Los geht's"), command=win.destroy).pack(side="right")
        self.upd_btn = ttk.Button(btns, text=_("yt-dlp aktualisieren"), command=self.update_ytdlp)
        self.upd_btn.pack(side="right", padx=8)

        text = tk.Text(win, wrap="word", padx=16, pady=12, font=("Segoe UI", 10), cursor="arrow")
        text.pack(fill="both", expand=True)
        self.readme_text = text
        text.tag_configure("h", font=("Segoe UI", 14, "bold"), spacing3=8)
        text.tag_configure("sub", font=("Segoe UI", 11, "bold"), spacing1=10, spacing3=4)
        text.tag_configure("p", spacing3=10)
        text.tag_configure("ok")
        text.tag_configure("bad")
        for tag, content in (HELP_TEXT_EN if is_english() else HELP_TEXT):
            text.insert("end", content + "\n", tag)
        text.insert("end", _("Systemcheck") + "\n", "sub")
        for name, ok, detail in self.system_check():
            text.insert("end", ("✓ " if ok else "✗ ") + f"{name}: {detail}\n", "ok" if ok else "bad")
        if not all(ok for __, ok, ___ in self.system_check()):
            text.insert("end", "\n" + _("Fehlende Teile installiert setup.bat (im Installer-Ordner).") + "\n", "p")
        text.configure(state="disabled")
        self.apply_theme()

    def update_ytdlp(self):
        self.upd_btn.state(["disabled"])
        self.status.set(_("yt-dlp wird aktualisiert …"))
        threading.Thread(target=self._update_ytdlp, args=(installed_ytdlp_version(),), daemon=True).start()

    def _update_ytdlp(self, before):
        try:
            after = upgrade_ytdlp()
        except Exception as err:
            log("YTDLP UPDATE FAIL", short_err(err, 200))
            self.set_status(_("Aktualisierung fehlgeschlagen: {e}").format(e=short_err(err)))
            self.after(0, self.enable_update_button)
            return
        log("YTDLP UPDATE", f"{before} -> {after}")
        if after == before:
            msg = _("yt-dlp ist aktuell (Version {v}).").format(v=after)
        else:
            msg = _("yt-dlp aktualisiert: {a} → {b}. Bitte ytpick neu starten.").format(a=before, b=after)
        self.set_status(msg)
        self.after(0, self.enable_update_button)

    def enable_update_button(self):
        if self.readme_win and self.readme_win.winfo_exists():
            self.upd_btn.state(["!disabled"])
