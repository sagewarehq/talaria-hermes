"""Newsroom's sources: list them, suggest some for the chosen topics, find a site's feed, add or remove one.

    {"op": "list"}                     → {"feeds": [...with last collection's health]}
    {"op": "suggest", "topics": [...]} → {"suggestions": [...catalog feeds not already added]}
    {"op": "discover", "url"}          → {"url", "title", "headlines": [...3]}  (a site, page or feed URL), or, when the
                                         site has no RSS or Atom feed, {"url": null, "message", "alternatives": [...]}
    {"op": "add", "url", "title", "topic"} / {"op": "remove", "url"} → {"feeds": [...]}
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import newsroom  # noqa: E402

ATOM = "{http://www.w3.org/2005/Atom}"
FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/xml", "text/xml", "application/rss")
GUESSES = ("/feed", "/feed/", "/rss", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml")


def parse_feed(body: bytes):
    """(title, headlines) if ``body`` is an RSS or Atom feed, else None."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    items = root.findall(".//item") or root.findall(f"{ATOM}entry")
    if root.tag.split("}")[-1] not in ("rss", "feed", "RDF") or not items:
        return None
    title = root.findtext("channel/title") or root.findtext(f"{ATOM}title") or ""
    heads = [" ".join((i.findtext("title") or i.findtext(f"{ATOM}title") or "").split()) for i in items[:3]]
    return " ".join(title.split()), [h for h in heads if h]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.feeds = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and "alternate" in (a.get("rel") or "").lower() and (a.get("type") or "").lower() in FEED_TYPES and a.get("href"):
            self.feeds.append(a["href"])


def try_feed(url: str):
    try:
        body, _, final = newsroom.fetch(url, timeout=10, limit=3_000_000)
    except Exception:
        return None
    found = parse_feed(body)
    return (final, *found) if found else None


def discover(url: str) -> dict:
    url = url.strip()
    if not re.match(r"^[a-z]+://", url):
        url = "https://" + url
    url = url.replace("http://", "https://", 1)
    try:
        body, kind, final = newsroom.fetch(url, timeout=10, limit=3_000_000)
    except ValueError:
        sys.exit("Only public https addresses can be added.")
    except Exception:
        found = no_feed(urlsplit(url).hostname or url)
        if not found["alternatives"]:
            sys.exit(f"Couldn't reach {urlsplit(url).hostname or url}.")
        return {**found, "message": f"Couldn't reach {urlsplit(url).hostname}; these feeds cover it."}
    candidates = []
    found = parse_feed(body)
    if found:
        return {"url": final, "title": found[0] or urlsplit(final).hostname, "headlines": found[1]}
    if "html" in kind:
        p = Links()
        p.feed(body.decode("utf-8", "replace")[:500_000])
        candidates = [urljoin(final, h) for h in p.feeds]
    base = f"https://{urlsplit(final).hostname}"
    for c in candidates[:3] + [base + g for g in GUESSES]:
        hit = try_feed(c)
        if hit:
            return {"url": hit[0], "title": hit[1] or urlsplit(hit[0]).hostname, "headlines": hit[2]}
    return no_feed(urlsplit(final).hostname or url)


def no_feed(host: str) -> dict:
    """Feeds that cover a site with none of its own: the catalog's for that publisher, then Google News's feed of
    the site's stories (an RSS feed, checked here before it's offered)."""
    site = host.removeprefix("www.")
    catalog = json.loads((newsroom.ROOT / "catalog.json").read_text())
    same = [dict(f, topic=t) for t, fs in catalog.items() for f in fs if site in (urlsplit(f["url"]).hostname or "")]
    alternatives = same[:3]
    gnews = f"https://news.google.com/rss/search?q=site:{site}&hl=en-US&gl=US&ceid=US:en"
    hit = try_feed(gnews)
    # Google News titles end in " - Publisher"; drop that, and any that are nothing else.
    heads = [h for h in (re.sub(r"\s+-\s+[^-]+$", "", h).strip(" -") for h in (hit[2] if hit else [])) if len(h) > 3]
    if heads:
        alternatives.append({"url": gnews, "title": f"{site} via Google News", "headlines": heads})
    return {"url": None, "message": f"{site} has no RSS or Atom feed.", "alternatives": alternatives}


req = json.load(sys.stdin) or {}
op = req.get("op", "list")
s = newsroom.settings()
feeds = s["feeds"]
if op == "suggest":
    catalog = json.loads((newsroom.ROOT / "catalog.json").read_text())
    have = {f["url"] for f in feeds}
    topics = req.get("topics") or s["topics"] or newsroom.TOPICS
    print(json.dumps({"suggestions": [dict(f, topic=t) for t in topics for f in catalog.get(t, []) if f["url"] not in have]}))
elif op == "discover":
    print(json.dumps(discover(str(req.get("url", "")))))
elif op in ("add", "remove"):
    url = str(req.get("url", ""))
    newsroom.public_url(url)  # raises for anything but a public https address
    feeds = [f for f in feeds if f["url"] != url]
    if op == "add":
        if len(feeds) >= 60:
            sys.exit("That's 60 sources already; remove one first.")
        topic = req.get("topic") if req.get("topic") in newsroom.TOPICS else "Technology"
        feeds.append({"url": url, "title": " ".join(str(req.get("title") or urlsplit(url).hostname).split())[:80], "topic": topic})
    newsroom.save({**s, "feeds": feeds})
    print(json.dumps({"feeds": feeds}))
else:
    try:
        health = {h["url"]: h for h in json.loads((newsroom.ROOT / "status.json").read_text()).get("sources", [])}
    except (OSError, ValueError):
        health = {}
    print(json.dumps({"feeds": [dict(f, ok=health.get(f["url"], {}).get("ok"), count=health.get(f["url"], {}).get("count")) for f in feeds]}))
