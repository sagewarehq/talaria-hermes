"""The Apps marketplace: the apps Talaria ships with (starters/, e.g. Newsroom), each with whether it's on this box,
and an install that runs in the background. ``/talaria catalog`` lists them and ``/talaria install <name>`` starts
one; the install itself is ``build.py --starter <name>``, detached, since npm and the build outlast a slash command.

A starter's state, as the iPhone shows it:
  available   not here: never installed, or deleted since
  installing  build.py --starter is on it (its file in talaria/installing/)
  installed   here, installed by Talaria
  failed      the last install stopped; ``error`` says why, and Install tries again
  taken       an app of the user's own has its name, so it can't be installed
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from . import store

HERE = Path(__file__).resolve().parent
STARTERS = HERE / "starters"
STALE = 30 * 60  # an install this old that never cleared its file stopped without saying


def _talaria() -> Path:
    return store.home() / "talaria"


def _record() -> dict[str, str]:
    try:
        done = json.loads((_talaria() / "starters.json").read_text())
        return done if isinstance(done, dict) else {}
    except (OSError, ValueError):
        return {}


def _installing(name: str) -> Path:
    return _talaria() / "installing" / f"{name}.json"  # build.py's installing()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _running(name: str) -> bool:
    """An install of this starter is under way. A file left by one that died (the box restarted mid-install) is
    cleared here, so it can be tried again."""
    f = _installing(name)
    try:
        info = json.loads(f.read_text())
    except (OSError, ValueError):
        return False
    pid, started = info.get("pid"), info.get("started", 0)
    if isinstance(pid, int) and _alive(pid) and time.time() - float(started) < STALE:
        return True
    f.unlink(missing_ok=True)
    return False


def has_node() -> bool:
    return bool(shutil.which("node") or (store.home() / "node" / "bin" / "node").exists())


def starters() -> list[tuple[str, dict[str, Any]]]:
    out = []
    for f in sorted(STARTERS.glob("*/starter.json")) if STARTERS.is_dir() else ():
        try:
            out.append((f.parent.name, json.loads(f.read_text())))
        except (OSError, ValueError):
            continue
    return out


def state(name: str, outcome: str) -> str:
    here = (_talaria() / "apps" / name / "index.html").exists()
    if _running(name):
        return "installing"
    if here:
        return "installed" if outcome == "installed" else "taken"
    if (_talaria() / "workspace" / "apps" / name).exists() or (_talaria() / "apps" / name).exists():
        # source or scripts without a build: a failed install of ours (Install retries it), or the user's own
        return "failed" if outcome.startswith("failed") else "taken"
    return "failed" if outcome.startswith("failed") else "available"


def catalog() -> dict[str, Any]:
    done = _record()
    apps = []
    for name, meta in starters():
        outcome = str(done.get(name) or "")
        row = {"name": name, "title": meta.get("title") or name.replace("-", " ").title(),
               "description": meta.get("description") or "", "glyph": meta.get("glyph"),
               "state": state(name, outcome)}
        if row["state"] == "failed":
            row["error"] = outcome.removeprefix("failed:").strip() or "The install stopped."
        apps.append(row)
    return {"apps": apps, "node": has_node()}


def install(name: str) -> dict[str, Any]:
    """Start installing a starter, in the background; the catalog shows how it's going."""
    meta = dict(starters()).get(name)
    if meta is None:
        return {"error": f"Talaria doesn't ship an app called {name!r}."}
    current = state(name, str(_record().get(name) or ""))
    if current in ("installing", "installed"):
        return {"name": name, "state": current}
    if current == "taken":
        return {"error": f"You already have an app called {name}, so this one can't be installed beside it."}
    if not has_node():
        return {"error": "Installing apps needs Node.js on this machine, which builds them."}
    f = _installing(name)
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.Popen([sys.executable, str(HERE / "build.py"), "--starter", name], start_new_session=True,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return {"error": f"The install couldn't start: {e}"}
    f.write_text(json.dumps({"pid": proc.pid, "started": time.time()}))
    threading.Thread(target=proc.wait, daemon=True).start()  # reaped, so it doesn't linger as a zombie that looks alive
    return {"name": name, "state": "installing"}
