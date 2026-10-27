"""Newsroom's settings (newsroom.json) and its one way of reaching the internet, shared by the collector, the
publisher, the extractor and the app's actions.

Every fetch goes through fetch(): https only, public addresses only, checked again on every redirect, with a size
limit. Feeds and pages come from URLs the user pastes, so nothing here may reach the box itself or its network.
"""
from __future__ import annotations

import ipaddress
import json
import socket
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "newsroom.json"
TOPICS = ["Artificial Intelligence", "Technology", "Cybersecurity", "Developer & Engineering", "Fintech", "Startups",
          "World Affairs", "Philippines", "Business & Economy", "Science & Space", "Health", "Climate & Energy",
          "Culture & Entertainment", "Sports"]
USER_AGENT = "TalariaNewsroom/1.0 (RSS reader; personal reading)"


def configured() -> bool:
    return SETTINGS.is_file()


def settings() -> dict:
    try:
        s = json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        s = {}
    return {"version": 1, "timezone": "UTC", "topics": [], "interests": "", "feeds": [], "discovery": True, **s}


COMICS = "Comics"
MAX_DISCOVERY = 3


def discovery_feeds(s: dict | None = None) -> list[tuple[str, str, str]]:
    """(area, title, url) of each feed in discovery.json near the reader's topics, unless they turned discovery off:
    the few stories each edition may carry from outside their topics, to widen their taste (EDITORIAL.md). Feeds the
    reader already follows are theirs, not discovery."""
    s = s or settings()
    if not s.get("discovery", True):
        return []
    try:
        areas = json.loads((ROOT / "discovery.json").read_text())["areas"]
    except (OSError, ValueError, KeyError):
        return []
    mine = {f.get("url") for f in s["feeds"]}
    return [(a["name"], f["title"], f["url"]) for a in areas if set(a.get("near", [])) & set(s["topics"])
            for f in a["feeds"] if f["url"] not in mine]


def save(s: dict) -> dict:
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2))
    tmp.replace(SETTINGS)
    return s


def zone() -> ZoneInfo:
    try:
        return ZoneInfo(settings()["timezone"])
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def public_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443) or not parts.hostname:
        raise ValueError("Only public https addresses")
    for info in socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ValueError("Only public https addresses")
    return url


class _PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_PublicRedirect())


def open_public(url: str, timeout: float = 18):
    """A response for a public https URL (a context manager), following only public redirects."""
    return _OPENER.open(urllib.request.Request(public_url(url), headers={"User-Agent": USER_AGENT}), timeout=timeout)


def fetch(url: str, timeout: float = 18, limit: int = 4_000_000) -> tuple[bytes, str, str]:
    """(body, content type, final URL) of a public https URL, at most ``limit`` bytes."""
    with open_public(url, timeout) as r:
        return r.read(limit), r.headers.get_content_type(), r.geturl()


REPEAT_HOURS = 72


def story_url(url: str) -> str:
    """A story's URL without what makes the same story look different: scheme, www, query, fragment, trailing slash."""
    parts = urlsplit((url or "").strip())
    host = (parts.hostname or "").lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}" if host else ""


def recently_published(root: Path = ROOT, hours: int = REPEAT_HOURS, now=None) -> dict[str, str]:
    """Every story in an edition from the last `hours`: its id and its URL (story_url), each mapped to the newest
    edition's editedAt it ran in. An edition carries what's new; these already ran."""
    import datetime as dt
    now = now or dt.datetime.now(dt.timezone.utc)
    seen: dict[str, str] = {}
    for path in [root / "editorial.json", *sorted((root / "editions").glob("*.json"))]:
        try:
            ed = json.loads(path.read_text())
            when = dt.datetime.fromisoformat(ed["editedAt"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if when.tzinfo is None or now - when > dt.timedelta(hours=hours):
            continue
        urls = {a.get("id"): a.get("url", "") for a in ed.get("snapshots", [])}
        for item in ed.get("items", []):
            for key in (f"id:{item.get('id')}", f"url:{story_url(urls.get(item.get('id'), ''))}"):
                if key not in ("id:None", "url:") and ed["editedAt"] > seen.get(key, ""):
                    seen[key] = ed["editedAt"]
    return seen


def ran(article: dict, recent: dict[str, str]) -> str | None:
    """When this story last ran in a recent edition, or None."""
    return recent.get(f"id:{article.get('id')}") or recent.get(f"url:{story_url(article.get('url', ''))}") or None
