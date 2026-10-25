#!/usr/bin/env python3
"""Extract readable article text for every story in Newsroom's editions, for the in-app reader.

    extract.py <app folder>

Writes articles/<id>.json beside the editions: the article as plain blocks (paragraphs, headings, list items, quotes,
and its media), never HTML, so the app renders text only. Media is where the story has it: a photo or chart as its
https address on the publisher's site (shown from there, never downloaded), and a video or chart embed from a known
player, rebuilt from its id. Skips stories already extracted, and records a failure (paywall, block, too little
text) so the reader falls back to the publisher's page instead of retrying every run.
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import lxml.html
import trafilatura

sys.path.insert(0, str(Path(__file__).resolve().parent))
from newsroom import fetch  # noqa: E402  (https and public addresses only, as for every fetch)

MIN_WORDS = 120
# What a reader never sees as the article: dialogs (a privacy notice behind a footer link), cookie and consent
# banners. Trafilatura reads them as text all the same.
_lower = "translate(concat(@id,' ',@class),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')"
PRUNE = ["//dialog", "//template", "//*[@role='dialog' or @role='alertdialog' or @aria-modal='true']",
         f"//*[contains({_lower},'cookie') or contains({_lower},'consent') or contains({_lower},'gdpr')]"]
# A page's legal text, which an extraction that went wrong starts with instead of the story.
# Bumped when what's extracted changes, so stored articles are extracted again (2: media).
VERSION = 2
MAX_IMAGES = 12
# An image that's the site's furniture, not the story's: by its address or its alt text.
FURNITURE = re.compile(r"logo|/icons?/|favicon|avatar|sprite|badge|banner|navigation|newsletter|promo|advert|placeholder|"
                       r"pixel|spacer|\.svg(\?|$)", re.I)
FURNITURE_ALT = re.compile(r"\b(logo|icon|avatar|banner|newsletter|advert(isement)?|sponsored)\b", re.I)
# Players an embed may come from, by the id in their address; the embed is rebuilt from the id, never kept as given.
PLAYERS = [
    (re.compile(r"^https?://(?:www\.)?youtube(?:-nocookie)?\.com/embed/([\w-]{6,20})"), "video",
     "https://www.youtube-nocookie.com/embed/{}"),
    (re.compile(r"^https?://player\.vimeo\.com/video/(\d{4,12})"), "video", "https://player.vimeo.com/video/{}"),
    (re.compile(r"^https?://flo\.uri\.sh/(visualisation|story)/(\d{3,12})/embed"), "chart", "https://flo.uri.sh/{}/{}/embed"),
    (re.compile(r"^https?://datawrapper\.dwcdn\.net/(\w{5})/(\d{1,3})/"), "chart", "https://datawrapper.dwcdn.net/{}/{}/"),
]
# An embed's place in the page, kept through trafilatura as an image it will keep: replaced by the embed afterwards.
MARK = "https://embed.talaria.invalid/"
LEGAL = re.compile(r"^(privacy (notice|policy|statement)|cookie (notice|policy|settings|preferences)|"
                   r"terms (of (service|use)|and conditions)|your privacy choices)\b", re.I)


def stories(app: Path) -> dict[str, dict]:
    out = {}
    for f in [app / "editorial.json", *sorted((app / "editions").glob("*.json"))]:
        try:
            ed = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        snaps = {a["id"]: a for a in ed.get("snapshots", [])}
        for item in ed.get("items", []):
            a = snaps.get(item["id"])
            if a and a.get("url", "").startswith("https://"):
                out[a["id"]] = a
    return out


def embeds(html: str, url: str) -> tuple[str, list[dict]]:
    """The page with each embed from a known player marked where it sits, and the embeds, by mark."""
    try:
        doc = lxml.html.fromstring(html)
    except (ValueError, lxml.etree.ParserError):
        return html, []
    found = []
    for frame in list(doc.iter("iframe")):
        src = urljoin(url, (frame.get("src") or frame.get("data-src") or "").strip())
        for pattern, kind, rebuilt in PLAYERS:
            if m := pattern.match(src):
                embed = {"t": "embed", "kind": kind, "src": rebuilt.format(*m.groups())}
                w, h = (re.match(r"\d+", frame.get(k) or "") for k in ("width", "height"))
                if w and h and int(w.group()) >= 100 and int(h.group()) >= 100:
                    embed["ratio"] = round(int(w.group()) / int(h.group()), 3)
                mark = lxml.html.Element("img", src=f"{MARK}{len(found)}.png", alt="embed")
                if frame.getparent() is None:
                    break
                frame.getparent().replace(frame, mark)
                found.append(embed)
                break
    return (lxml.html.tostring(doc, encoding="unicode"), found) if found else (html, [])


IMAGE = re.compile(r"!\[([^\]]*)\]\((\S+?)(?:\s+\"[^\"]*\")?\)")


def media(alt: str, src: str, url: str, found: list[dict]) -> dict | None:
    if src.startswith(MARK):
        n = re.match(r"\d+", src[len(MARK):])
        return found[int(n.group())] if n and int(n.group()) < len(found) else None
    src = urljoin(url, src)
    if not src.startswith("https://") or len(src) > 2000 or FURNITURE.search(src) or FURNITURE_ALT.search(alt):
        return None
    return {"t": "img", "src": src, "alt": alt.strip()[:300]}


def blocks(markdown: str, url: str = "", found: list[dict] | None = None) -> list[dict]:
    out = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line or line.startswith("|"):
            continue
        # Images (and the embeds marked as images) on the line, after its text; linked images too.
        pictures = [m for alt, src in IMAGE.findall(line) if (m := media(alt, src, url, found or []))]
        line = IMAGE.sub("", line).strip()
        line = re.sub(r"\[\s*\]\([^)]+\)", "", line).strip()  # what's left of a linked image
        if not re.sub(r"^([-*+]|\d+\.)\s*", "", line):
            out.extend(pictures)
            continue
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)  # links to their text
        line = re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", line)
        line = re.sub(r"\*{2,}|_{2,}|`", "", line).strip()  # any emphasis left unbalanced
        if not line:
            continue
        if line.startswith("#"):
            out.append({"t": "h", "text": line.lstrip("# ")})
        elif re.match(r"^[-*+] ", line) or re.match(r"^\d+\. ", line):
            out.append({"t": "li", "text": re.sub(r"^([-*+]|\d+\.) ", "", line)})
        elif line.startswith(">"):
            out.append({"t": "q", "text": line.lstrip("> ")})
        else:
            out.append({"t": "p", "text": line})
        out.extend(pictures)
    return tidy(out)


def tidy(body: list[dict]) -> list[dict]:
    """Each picture once, a dozen at most, and none after the story's last paragraph: those are other stories'
    promos (a site's "Latest" and "Trending" lists can come after it too)."""
    last = max((i for i, b in enumerate(body) if b["t"] == "p" and len(b["text"].split()) >= 8), default=len(body))
    seen, images, out = set(), 0, []
    for i, b in enumerate(body):
        if b["t"] == "img" and i > last:
            continue
        if b["t"] in ("img", "embed"):
            if b["src"] in seen or (b["t"] == "img" and images >= MAX_IMAGES):
                continue
            seen.add(b["src"])
            images += b["t"] == "img"
        out.append(b)
    return out


def text(body: list[dict]) -> list[dict]:
    return [b for b in body if "text" in b]


def count(body: list[dict]) -> int:
    return sum(len(b["text"].split()) for b in text(body))


def legal(body: list[dict]) -> bool:
    """The extraction starts with a privacy notice, cookie policy or terms, not a story."""
    return any(LEGAL.match(b["text"]) for b in text(body)[:3])


def relevance(body: list[dict], a: dict) -> int:
    """How many of the story's title words the first few hundred words mention: a story's text names its subject."""
    title = {w for w in re.findall(r"[a-z0-9]{4,}", a.get("title", "").lower())}
    lead = " ".join(b["text"] for b in text(body)[:12]).lower()
    return sum(1 for w in title if w in lead)


def candidates(html: str, url: str):
    """Trafilatura's readings of the page, most precise first, with what a reader never sees pruned."""
    marked, found = embeds(html, url)
    for kw in ({"favor_precision": True}, {"favor_recall": True}):
        try:
            md = trafilatura.extract(marked, output_format="markdown", include_comments=False, include_tables=False,
                                     include_images=True, url=url, prune_xpath=PRUNE, **kw)
        except Exception:
            continue
        yield blocks(md or "", url, found)


def extract(a: dict) -> dict:
    record = {"id": a["id"], "url": a["url"], "v": VERSION, "extractedAt": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        body, kind, _ = fetch(a["url"], timeout=20, limit=5_000_000)
    except Exception:
        return {**record, "ok": False, "reason": "unreachable"}
    if kind not in ("text/html", "application/xhtml+xml"):
        return {**record, "ok": False, "reason": f"not a page ({kind})"}
    html = body.decode("utf-8", "replace")
    meta = trafilatura.extract_metadata(html, default_url=a["url"])
    # The first reading that's long enough, not legal text, and about the story; else the most relevant of them.
    readings = [b for b in candidates(html, a["url"]) if count(b) >= MIN_WORDS and not legal(b)]
    body = next((b for b in readings if relevance(b, a) > 0), max(readings, key=lambda b: relevance(b, a), default=[]))
    words = count(body)
    if words < MIN_WORDS:
        return {**record, "ok": False, "reason": "too little text (paywall or blocked)", "words": words}
    return {**record, "ok": True, "title": meta.title if meta else None, "byline": meta.author if meta else None,
            "site": meta.sitename if meta else None, "words": words, "blocks": body[:400]}


def main(app: Path) -> int:
    out = app / "articles"
    out.mkdir(exist_ok=True)
    todo = {i: a for i, a in stories(app).items() if not (out / f"{i}.json").exists() or wrong(out / f"{i}.json")}
    with cf.ThreadPoolExecutor(6) as pool:
        for a, rec in zip(todo.values(), pool.map(lambda a: _safe(a), todo.values())):
            tmp = out / f".{a['id']}.json"
            tmp.write_text(json.dumps(rec, ensure_ascii=False))
            tmp.replace(out / f"{a['id']}.json")
            print(f"{'ok ' if rec['ok'] else 'no '} {rec.get('words', 0):>5}  {a['title'][:70]}")
    return 0


def wrong(path: Path) -> bool:
    """A stored extraction that caught a page's legal text instead of the story, or one from before what's extracted
    now (its media): extracted again."""
    try:
        rec = json.loads(path.read_text())
    except (OSError, ValueError):
        return True
    return bool(rec.get("ok")) and (rec.get("v", 1) < VERSION or legal(rec.get("blocks") or []))


def _safe(a):
    try:
        return extract(a)
    except Exception as e:
        return {"id": a["id"], "url": a["url"], "ok": False, "reason": f"{type(e).__name__}"}


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
