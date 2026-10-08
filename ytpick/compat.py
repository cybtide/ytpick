"""Optionale Abhängigkeiten (yt-dlp, Pillow) und PATH-Auffrischung unter Windows."""

import os
import sys


try:
    import yt_dlp
except ImportError:
    raise SystemExit("yt-dlp fehlt. Installieren mit: pip install -U yt-dlp[default]")

try:
    from yt_dlp.version import __version__ as YTDLP_VERSION
except Exception:
    YTDLP_VERSION = "?"

try:
    from PIL import Image, ImageOps, ImageTk
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False


def refresh_windows_path():
    if sys.platform != "win32":
        return
    try:
        import winreg
        parts = []
        for hive, sub in (
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, "Environment"),
        ):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    val, __ = winreg.QueryValueEx(k, "Path")
                    parts.append(os.path.expandvars(val))
            except OSError:
                pass
        cur = os.environ.get("PATH", "")
        known = set(cur.split(";"))
        extra = [p for p in ";".join(parts).split(";") if p and p not in known]
        if extra:
            os.environ["PATH"] = cur + ";" + ";".join(extra)
    except Exception:
        pass


refresh_windows_path()
