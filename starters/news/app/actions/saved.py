"""Read later: the stories the reader saved, kept here so every device (the phone, Hermes Desktop) has the same list.

    {"op": "add", "article": {...}, "at"?}            save a story
    {"op": "remove", "id": "...", "at"?}              take one off the list
    {"op": "merge", "items": [{"article", "savedAt"}]} what a device saved on its own before the list was shared
    → {"count": n}

The list lives in app.db (reader.py), changed in one transaction so two devices saving at once both land. The app
reads it from read-later.json, which that transaction rewrites (an action's answer is capped at 64 KB): each story's
snapshot, what the app shows without its edition, and when it was saved; for a removed one, when, so a device that
still has it from before doesn't bring it back unless it saved it again later.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reader  # noqa: E402

FIELDS = ("id", "title", "url", "publisher", "topics", "publishedAt", "summary", "discussionUrl", "image", "priority",
          "key", "tags", "why", "evidence")


def snapshot(a) -> dict | None:
    """The story as the app shows it, nothing else; None when it isn't one."""
    if not isinstance(a, dict) or not isinstance(a.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", a["id"]):
        return None
    if not isinstance(a.get("url"), str) or not a["url"].startswith(("https://", "http://")):
        return None
    out = {k: a[k] for k in FIELDS if k in a}
    return out if len(json.dumps(out)) <= 20000 else None


def when(x) -> str:
    return x if isinstance(x, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:.]+(Z|[+-]\d\d:\d\d)", x) else reader.now()


def add(db, article, at: str) -> None:
    a = snapshot(article)
    removed = a and db.execute("SELECT removed_at FROM removed WHERE id = ?", (a["id"],)).fetchone()
    if a and at >= (removed[0] if removed else ""):  # not one removed after this copy was saved
        db.execute("INSERT OR REPLACE INTO saved VALUES (?, ?, ?)", (a["id"], json.dumps(a, ensure_ascii=False), at))
        db.execute("DELETE FROM removed WHERE id = ?", (a["id"],))


req = json.load(sys.stdin) or {}
op = req.get("op")
if op not in ("add", "remove", "merge") or (op == "remove" and not isinstance(req.get("id"), str)):
    sys.exit("Unknown op.")
with reader.changing() as db:
    if op == "add":
        add(db, req.get("article"), when(req.get("at")))
    elif op == "remove":
        db.execute("DELETE FROM saved WHERE id = ?", (req["id"],))
        db.execute("INSERT OR REPLACE INTO removed VALUES (?, ?)", (req["id"], when(req.get("at"))))
    else:
        for item in req.get("items", [])[:reader.MAX] if isinstance(req.get("items"), list) else []:
            if isinstance(item, dict) and isinstance(item.get("article"), dict) and not db.execute(
                    "SELECT 1 FROM saved WHERE id = ?", (item["article"].get("id"),)).fetchone():
                add(db, item["article"], when(item.get("savedAt")))
    count = db.execute("SELECT count(*) FROM saved").fetchone()[0]
print(json.dumps({"count": min(count, reader.MAX)}))
