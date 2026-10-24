"""Newsroom's settings: get them, or save the topics, interests and timezone (the first-run flow and Preferences).

    {"op": "get"}                                   → {"configured", "settings", "topics"}
    {"op": "save", "topics", "interests", "timezone"} → the saved settings
"""
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import newsroom  # noqa: E402

req = json.load(sys.stdin) or {}
s = newsroom.settings()
if req.get("op") == "save":
    topics = [t for t in req.get("topics", s["topics"]) if t in newsroom.TOPICS]
    if not topics:
        sys.exit("Pick at least one topic.")
    interests = " ".join(str(req.get("interests", s["interests"])).split())[:1000]
    tz = req.get("timezone") or s["timezone"]
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        sys.exit(f"Unknown timezone {tz}.")
    s = newsroom.save({**s, "topics": topics, "interests": interests, "timezone": tz})
print(json.dumps({"configured": newsroom.configured(), "settings": s, "topics": newsroom.TOPICS}))
