"""The phone's votes, for the editor: writes reader-feedback.json, which the routine reads each run.

    {"votes": [{"id", "title", "publisher", "topics", "tags", "value": 1|-1, "at"}, ...]} → {"saved": n}
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
req = json.load(sys.stdin) or {}
keep = ("id", "title", "url", "publisher", "topics", "tags", "value", "at")
votes = [{k: v[k] for k in keep if k in v} for v in req.get("votes", []) if isinstance(v, dict) and v.get("value") in (1, -1)][-2000:]
tmp = ROOT / "reader-feedback.tmp"
tmp.write_text(json.dumps({"syncedAt": dt.datetime.now(dt.timezone.utc).isoformat(), "votes": votes}, ensure_ascii=False))
tmp.replace(ROOT / "reader-feedback.json")
print(json.dumps({"saved": len(votes)}))
