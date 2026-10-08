"""Prüfung auf neuere Releases über die GitHub-API."""

import json
import re
import ssl
from urllib.request import Request, urlopen

from . import __version__


REPO = "cybtide/ytpick"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"
UPDATE_INTERVAL = 24 * 3600


def parse_version(text):
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", str(text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(candidate, current):
    a, b = parse_version(candidate), parse_version(current)
    return bool(a and b and a > b)


def fetch_latest_release():
    req = Request(RELEASES_API, headers={"User-Agent": f"ytpick/{__version__}",
                                         "Accept": "application/vnd.github+json"})
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    with urlopen(req, timeout=8, context=ctx) as r:
        data = json.load(r)
    tag = str(data.get("tag_name") or "")
    if not parse_version(tag):
        raise ValueError("tag_name")
    return {"version": tag.lstrip("v"), "url": data.get("html_url") or RELEASES_URL}
