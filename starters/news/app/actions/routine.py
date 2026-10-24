"""Newsroom's routine: the scheduled job that collects feeds and has Hermes edit an edition.

    {"op": "status"}                         → {"installed", "id", "frequency", "state", "nextRunAt", "lastRunAt", "lastStatus"}
    {"op": "install", "frequency"}           → the status, after creating the job and queueing a first run
    {"op": "schedule", "frequency"}          → the status, with the job rescheduled
    {"op": "remove"}                         → the status

A frequency is "6h", "12h" or "daily", anchored at 7 AM in the reader's timezone, written as the box's cron hours.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import newsroom  # noqa: E402

HERMES_HOME = Path(os.environ.get("TALARIA_HOME") or newsroom.ROOT.parents[1]).parent
NAME = "Newsroom editor"
SCRIPT = "newsroom-refresh.py"
STEPS = {"6h": 6, "12h": 12, "daily": 24}


def schedule(frequency: str) -> str:
    """The cron expression for a frequency: 7 AM in the reader's timezone, then every step, in the box's hours."""
    step = STEPS[frequency]
    first = dt.datetime.now(newsroom.zone()).replace(hour=7, minute=0, second=0, microsecond=0).astimezone().hour
    return "0 " + ",".join(str(h) for h in sorted((first + k * step) % 24 for k in range(24 // step))) + " * * *"


def jobs() -> dict:
    try:
        data = json.loads((HERMES_HOME / "cron" / "jobs.json").read_text())
    except (OSError, ValueError):
        return {}
    rows = data if isinstance(data, list) else data.get("jobs", [])
    return {j["id"]: j for j in rows if isinstance(j, dict) and j.get("id")}


def status(s: dict) -> dict:
    rid = (s.get("routine") or {}).get("id")
    job = jobs().get(rid) if rid else None
    if not job:
        return {"installed": False}
    return {"installed": True, "id": rid, "frequency": s.get("frequency", "6h"), "state": job.get("state"), "enabled": job.get("enabled", True),
            "nextRunAt": job.get("next_run_at"), "lastRunAt": job.get("last_run_at"), "lastStatus": job.get("last_status")}


def hermes(*args: str) -> str:
    exe = shutil.which("hermes") or "/usr/local/bin/hermes"
    p = subprocess.run([exe, *args], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                       env={**os.environ, "HERMES_HOME": str(HERMES_HOME)})
    if p.returncode:
        sys.exit(((p.stderr or p.stdout).strip().splitlines() or ["hermes failed"])[-1][:300])
    return p.stdout


req = json.load(sys.stdin) or {}
op = req.get("op", "status")
s = newsroom.settings()
frequency = req.get("frequency") or s.get("frequency") or "6h"
if frequency not in STEPS:
    sys.exit(f"Unknown frequency {frequency}.")
if op == "install":
    if status(s)["installed"]:
        print(json.dumps(status(s)))
        sys.exit()
    if not newsroom.configured() or not s["topics"]:
        sys.exit("Choose your topics first.")
    if not s["feeds"]:
        sys.exit("Add at least one source first.")
    script = HERMES_HOME / "scripts" / SCRIPT
    if not script.exists():
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text('#!/usr/bin/env python3\n"""Newsroom\'s collector, run before each editing run."""\nimport runpy\n'
                          f"runpy.run_path({str(newsroom.ROOT / 'refresh.py')!r}, run_name='__main__')\n")
    prompt = (newsroom.ROOT / "routine.md").read_text().replace("{APP}", str(newsroom.ROOT))
    before = set(jobs())
    hermes("cron", "create", schedule(frequency), prompt, "--name", NAME, "--script", SCRIPT, "--workdir", str(newsroom.ROOT), "--deliver", "local")
    new = [i for i in jobs() if i not in before]
    if len(new) != 1:
        sys.exit("The routine wasn't created.")
    s = newsroom.save({**s, "frequency": frequency, "routine": {"id": new[0], "installedAt": dt.datetime.now(dt.timezone.utc).isoformat()}})
    hermes("cron", "run", new[0])  # the first edition, on the scheduler's next tick
elif op == "schedule":
    rid = (s.get("routine") or {}).get("id")
    if rid and rid in jobs():
        hermes("cron", "edit", rid, "--schedule", schedule(frequency))
    s = newsroom.save({**s, "frequency": frequency})
elif op == "remove":
    rid = (s.get("routine") or {}).get("id")
    if rid and rid in jobs():
        hermes("cron", "remove", rid)
    s = newsroom.save({**s, "routine": None})
print(json.dumps(status(s)))
