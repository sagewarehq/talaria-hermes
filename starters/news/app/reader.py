"""Newsroom's reader state in app.db (migrations/001-reader.sql): the shared reading list and every device's votes.

The actions change it in one transaction, which also rewrites read-later.json and reader-feedback.json from it: the
page and the editor read those files, as they did before the database (a file has no size cap on the way to the
page), and two devices writing at once no longer lose one another's change. The first change adopts the files the
app kept before.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX = 1000  # stories on the list, and removals remembered
MAX_DEVICES = 20


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@contextmanager
def changing():
    """The database inside one write transaction (other writers wait for it), with the files rewritten at its end."""
    db = sqlite3.connect(os.environ.get("TALARIA_DB") or ROOT / "app.db", timeout=15, isolation_level=None)
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("BEGIN IMMEDIATE")
    try:
        adopt(db)
        yield db
        export(db)
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    finally:
        db.close()


def adopt(db: sqlite3.Connection) -> None:
    """Once: the reading list and votes from the files the app kept before it had a database."""
    if db.execute("SELECT 1 FROM meta WHERE key = 'adopted'").fetchone():
        return
    try:
        old = json.loads((ROOT / "read-later.json").read_text())
        for id, item in (old.get("items") or {}).items():
            db.execute("INSERT OR IGNORE INTO saved VALUES (?, ?, ?)", (id, json.dumps(item["article"], ensure_ascii=False), item["savedAt"]))
        for id, at in (old.get("removed") or {}).items():
            db.execute("INSERT OR IGNORE INTO removed VALUES (?, ?)", (id, at))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    try:
        old = json.loads((ROOT / "reader-feedback.json").read_text())
        devices = old.get("devices") if isinstance(old.get("devices"), dict) else {}
        if not devices and isinstance(old.get("votes"), list):  # a file from before devices: its votes as one
            devices = {"earlier": {"syncedAt": old.get("syncedAt", ""), "votes": old["votes"]}}
        for device, d in devices.items():
            set_votes(db, device, d.get("votes") or [], d.get("syncedAt") or "")
    except (OSError, ValueError, AttributeError):
        pass
    db.execute("INSERT INTO meta VALUES ('adopted', ?)", (now(),))


def set_votes(db: sqlite3.Connection, device: str, votes: list[dict], at: str) -> None:
    """A device's whole set of votes, replacing what it sent before; only the latest MAX_DEVICES devices are kept."""
    db.execute("INSERT INTO devices VALUES (?, ?) ON CONFLICT(device) DO UPDATE SET synced_at = excluded.synced_at", (device, at))
    db.execute("DELETE FROM votes WHERE device = ?", (device,))
    db.executemany("INSERT OR REPLACE INTO votes VALUES (?, ?, ?, ?, ?)",
                   [(device, v["id"], v["value"], str(v.get("at", "")), json.dumps(v, ensure_ascii=False))
                    for v in votes if isinstance(v, dict) and isinstance(v.get("id"), str) and v.get("value") in (1, -1)])
    db.execute("DELETE FROM devices WHERE device NOT IN (SELECT device FROM devices ORDER BY synced_at DESC LIMIT ?)", (MAX_DEVICES,))


def write(name: str, data) -> None:
    tmp = ROOT / (name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    tmp.replace(ROOT / name)


def export(db: sqlite3.Connection) -> None:
    """read-later.json and reader-feedback.json as the page and the editor read them, after trimming to the limits."""
    db.execute("DELETE FROM saved WHERE id NOT IN (SELECT id FROM saved ORDER BY saved_at DESC LIMIT ?)", (MAX,))
    db.execute("DELETE FROM removed WHERE id NOT IN (SELECT id FROM removed ORDER BY removed_at DESC LIMIT ?)", (MAX,))
    write("read-later.json", {
        "items": {id: {"article": json.loads(a), "savedAt": at}
                  for id, a, at in db.execute("SELECT id, article, saved_at FROM saved ORDER BY saved_at DESC")},
        "removed": dict(db.execute("SELECT id, removed_at FROM removed ORDER BY removed_at")),
    })
    devices = {d: {"syncedAt": at, "votes": [json.loads(v) for (v,) in db.execute(
                   "SELECT vote FROM votes WHERE device = ? ORDER BY at, id", (d,))]}
               for d, at in db.execute("SELECT device, synced_at FROM devices ORDER BY synced_at").fetchall()}
    write("reader-feedback.json", {
        "syncedAt": now(),
        "votes": [json.loads(v) for (v,) in db.execute("SELECT vote FROM latest_votes ORDER BY at, id")],
        "devices": devices,
    })
