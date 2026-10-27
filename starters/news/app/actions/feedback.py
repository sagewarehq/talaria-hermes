"""The reader's votes, for the editor: kept in app.db (reader.py), which rewrites reader-feedback.json, the file the
routine reads each run.

    {"device": "<id>", "votes": [{"id", "title", "publisher", "topics", "tags", "value": 1|-1, "at", "reason"?, "note"?}, ...]}
    → {"saved": n}

Each device (the phone, Hermes Desktop) keeps its own votes and sends all of them; the file keeps every device's set
under "devices" and, in "votes", one vote per story, the latest of them, so one device's sync never wipes another's.
A 👎 can carry why: "reason" (topic, seen, source, quality, misleading, other) and the reader's "note". A vote of 0
is one taken back: it stays in the device's set, so it outlasts the older vote other devices still send, and is left
out of "votes".
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reader  # noqa: E402

KEEP = ("id", "title", "url", "publisher", "topics", "tags", "value", "at", "reason", "note")
REASONS = {"topic", "seen", "source", "quality", "misleading", "other"}


def clean(raw) -> list[dict]:
    votes = [{k: v[k] for k in KEEP if k in v} for v in raw if isinstance(v, dict) and v.get("value") in (1, -1, 0)][-2000:]
    for v in votes:
        if v.get("reason") not in REASONS:
            v.pop("reason", None)
        if not isinstance(v.get("note"), str) or not v["note"].strip():
            v.pop("note", None)
        else:
            v["note"] = v["note"].strip()[:500]
    return votes


req = json.load(sys.stdin) or {}
device = req.get("device") if isinstance(req.get("device"), str) and re.fullmatch(r"[A-Za-z0-9-]{8,64}", req["device"]) else "unknown"
votes = clean(req.get("votes", []))
with reader.changing() as db:
    reader.set_votes(db, device, votes, reader.now())
print(json.dumps({"saved": len(votes)}))
