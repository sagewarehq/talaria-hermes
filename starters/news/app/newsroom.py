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
TOPICS = ["Artificial Intelligence", "Technology", "Cybersecurity", "Developer & Engineering", "Fintech", "Startups"]
USER_AGENT = "TalariaNewsroom/1.0 (RSS reader; personal reading)"


def configured() -> bool:
    return SETTINGS.is_file()


def settings() -> dict:
    try:
        s = json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        s = {}
    return {"version": 1, "timezone": "UTC", "topics": [], "interests": "", "feeds": [], **s}


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
