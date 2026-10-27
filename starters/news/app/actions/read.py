"""Read: the stories the reader opened, so a story read on the phone shows Read in Hermes Desktop too.

    {"ids": ["<id>", ...], "at"?}     mark them read (a story keeps when it was first read)
    → {"count": n}

Kept in app.db (reader.py), which rewrites read.json, the file the app reads.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reader  # noqa: E402

req = json.load(sys.stdin) or {}
ids = [i for i in req.get("ids", []) if isinstance(i, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", i)][:reader.MAX] \
    if isinstance(req.get("ids"), list) else []
at = req.get("at") if isinstance(req.get("at"), str) and re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:.]+(Z|[+-]\d\d:\d\d)", req["at"]) else reader.now()
with reader.changing() as db:
    db.executemany("INSERT OR IGNORE INTO read_stories VALUES (?, ?)", [(i, at) for i in ids])
    count = db.execute("SELECT count(*) FROM read_stories").fetchone()[0]
print(json.dumps({"count": min(count, reader.MAX)}))
