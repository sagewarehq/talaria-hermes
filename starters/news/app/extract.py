#!/usr/bin/env python3
"""Extract readable article text for every story in Newsroom's editions, for the in-app reader.

    extract.py <app folder>

Writes articles/<id>.json beside the editions: the article as plain blocks (paragraphs, headings, list items, quotes),
never HTML, so the app renders text only. Skips stories already extracted, and records a failure (paywall, block,
too little text) so the reader falls back to the publisher's page instead of retrying every run.
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
import sys
from pathlib import Path

import trafilatura

sys.path.insert(0, str(Path(__file__).resolve().parent))
from newsroom import fetch  # noqa: E402  (https and public addresses only, as for every fetch)

MIN_WORDS = 120


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


def blocks(markdown: str) -> list[dict]:
    out = []
    for line in markdown.splitlines():
        line = line.strip()
        if not line or line.startswith("|") or line.startswith("!["):
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
    return out


def extract(a: dict) -> dict:
    record = {"id": a["id"], "url": a["url"], "extractedAt": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        body, kind, _ = fetch(a["url"], timeout=20, limit=5_000_000)
    except Exception:
        return {**record, "ok": False, "reason": "unreachable"}
    if kind not in ("text/html", "application/xhtml+xml"):
        return {**record, "ok": False, "reason": f"not a page ({kind})"}
    html = body.decode("utf-8", "replace")
    md = trafilatura.extract(html, output_format="markdown", include_comments=False, include_tables=False,
                             include_images=False, favor_precision=True, url=a["url"])
    meta = trafilatura.extract_metadata(html, default_url=a["url"])
    body = blocks(md or "")
    words = sum(len(b["text"].split()) for b in body)
    if words < MIN_WORDS:
        return {**record, "ok": False, "reason": "too little text (paywall or blocked)", "words": words}
    return {**record, "ok": True, "title": meta.title if meta else None, "byline": meta.author if meta else None,
            "site": meta.sitename if meta else None, "words": words, "blocks": body[:400]}


def main(app: Path) -> int:
    out = app / "articles"
    out.mkdir(exist_ok=True)
    todo = {i: a for i, a in stories(app).items() if not (out / f"{i}.json").exists()}
    with cf.ThreadPoolExecutor(6) as pool:
        for a, rec in zip(todo.values(), pool.map(lambda a: _safe(a), todo.values())):
            tmp = out / f".{a['id']}.json"
            tmp.write_text(json.dumps(rec, ensure_ascii=False))
            tmp.replace(out / f"{a['id']}.json")
            print(f"{'ok ' if rec['ok'] else 'no '} {rec.get('words', 0):>5}  {a['title'][:70]}")
    return 0


def _safe(a):
    try:
        return extract(a)
    except Exception as e:
        return {"id": a["id"], "url": a["url"], "ok": False, "reason": f"{type(e).__name__}"}


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
