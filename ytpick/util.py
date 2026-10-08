"""Kleine Hilfsfunktionen ohne GUI: Formatierung, Zeit, Protokoll, Statistik."""

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from .constants import LOG_FILE, MUSIC_MODES, VIDEO_MODES
from .i18n import _, is_english


def set_titlebar(win, dark):
    if sys.platform != "win32":
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


class QuietLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(action, text):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{now()} | {action:<14} | {text}\n")
    except Exception:
        pass


def clean_text(s):
    return "".join(c for c in (s or "") if ord(c) <= 0xFFFF).strip()


def fmt_dur(sec):
    if not sec:
        return _("live")
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_date(d):
    if d is None:
        return "…"
    if len(d) == 8:
        if is_english():
            return f"{d[0:4]}-{d[4:6]}-{d[6:8]}"
        return f"{d[6:8]}.{d[4:6]}.{d[0:4]}"
    return "?"


def fmt_views(v):
    if not v:
        return "?"
    return f"{v:,}" if is_english() else f"{v:,}".replace(",", ".")


def age_text(ts):
    mins = int((time.time() - ts) / 60)
    if mins < 1:
        return _("gerade eben")
    if mins < 90:
        return _("vor {n} Min").format(n=mins)
    return _("vor {n} Std").format(n=mins // 60)


def is_bot_error(err):
    s = str(err).lower()
    return "sign in to confirm" in s or "not a bot" in s


def short_err(err, n=110):
    s = re.sub(r"\x1b\[[0-9;]*m", "", str(err)).replace("\n", " ").strip()
    s = re.sub(r"^ERROR:\s*", "", s)
    return s[:n]


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def parse_time(text):
    text = (text or "").strip()
    if not text:
        return None
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(text)
    total = 0.0
    for part in parts:
        total = total * 60 + float(part.replace(",", "."))
    if total < 0:
        raise ValueError(text)
    return total


def parse_clock(text):
    h, m = text.strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(text)
    return h * 60 + m


def in_window(now_minutes, start, end):
    if start == end:
        return True
    if start < end:
        return start <= now_minutes < end
    return now_minutes >= start or now_minutes < end


def detect_browsers():
    home = Path.home()
    local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    roaming = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    candidates = {
        "firefox": [roaming / "Mozilla" / "Firefox", home / ".mozilla" / "firefox",
                    home / "Library" / "Application Support" / "Firefox"],
        "chrome": [local / "Google" / "Chrome" / "User Data", home / ".config" / "google-chrome",
                   home / "Library" / "Application Support" / "Google" / "Chrome"],
        "edge": [local / "Microsoft" / "Edge" / "User Data", home / ".config" / "microsoft-edge"],
        "brave": [local / "BraveSoftware" / "Brave-Browser" / "User Data",
                  home / ".config" / "BraveSoftware" / "Brave-Browser"],
    }
    return [name for name, paths in candidates.items() if any(p.exists() for p in paths)]


EGGS = {
    "konami": "↑ ↑ ↓ ↓ ← → ← → B A\nPick wisely.",
    "harry potter": "🪄 Accio Video!\nGleis 9¾ ist frei für deine Downloads.",
    "hsv": "🔷 Nur der HSV.\nRaute im Herzen, Video im Korb.",
    "seahawks": "🦅 Go Hawks!\nDer 12. Mann sucht mit.",
    "hamburg": "⚓ Moin!\nHamburg, das Tor zur Welt, auch für deine Downloads.",
    "seattle": "☕ Regen, Kaffee und Space Needle.\nPerfektes Download-Wetter.",
}


def easter_egg(query):
    key = " ".join(str(query or "").lower().lstrip("@").split())
    return EGGS.get(key)


def fmt_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def fmt_hours(sec):
    sec = int(sec or 0)
    return f"{sec // 3600}:{sec % 3600 // 60:02d} h"


def compute_stats(downloads, history, today=None):
    today = today or datetime.now()
    by_mode, channels, months = Counter(), Counter(), Counter()
    size = duration = day = week = month = 0
    for rec in downloads.values():
        by_mode[rec.get("mode", "?")] += 1
        channels[rec.get("channel") or "?"] += 1
        size += rec.get("size") or 0
        duration += rec.get("duration") or 0
        try:
            at = datetime.strptime(rec.get("at", ""), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        months[at.strftime("%Y-%m")] += 1
        age = (today.date() - at.date()).days
        day += age == 0
        week += 0 <= age < 7
        month += 0 <= age < 30
    last = []
    y, m = today.year, today.month
    for _i in range(12):
        last.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    last.reverse()
    return {
        "total": len(downloads),
        "videos": sum(by_mode[k] for k in VIDEO_MODES),
        "music": sum(by_mode[k] for k in MUSIC_MODES),
        "without_record": len(set(history) - set(downloads)),
        "by_mode": dict(by_mode),
        "size": size,
        "duration": duration,
        "today": day,
        "week": week,
        "month": month,
        "channels": channels.most_common(15),
        "months": [(k, months.get(k, 0)) for k in last],
    }


def shutdown_command():
    if sys.platform == "win32":
        return ["shutdown", "/s", "/t", "0"]
    if sys.platform == "darwin":
        return ["osascript", "-e", 'tell application "System Events" to shut down']
    return ["systemctl", "poweroff"]


def open_path(path, reveal=False):
    path = str(path)
    try:
        if sys.platform == "win32":
            if reveal:
                subprocess.Popen(["explorer", "/select,", path])
            else:
                os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path] if reveal else ["open", path])
        else:
            subprocess.Popen(["xdg-open", str(Path(path).parent) if reveal else path])
    except Exception:
        pass
