"""App actions: scripts an app declares in its built folder, which its page can run (docs/app-actions.md).

    ~/.hermes/talaria/apps/<app>/actions/<name>.py

A script gets the request as JSON on stdin, runs in the app's folder with ``TALARIA_APP`` and ``TALARIA_HOME`` set,
and answers with one JSON value on stdout. The page gets ``{"ok": true, "result": …}`` or ``{"ok": false, "error": …}``.
Only scripts already in that app's ``actions/`` folder run: no paths, no other app's, no commands.

``talaria-db`` is reserved: it's the SDK's ``db`` calls (db.py), answered here without a script, so they travel every
way an action does. Before a script runs, the app's migrations are applied and ``TALARIA_DB`` names its database.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
MAX_REQUEST = 64 * 1024
MAX_RESULT = 64 * 1024
TIMEOUT = 120


def failed(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


def db_module():
    """db.py from beside this file, loaded by path: this file is imported as the plugin's, by serve.mjs from the
    plugin's folder, and by preview.py by path."""
    import importlib.util
    mod = sys.modules.get("talaria_db")
    if mod is None:
        spec = importlib.util.spec_from_file_location("talaria_db", Path(__file__).resolve().parent / "db.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Only once it's whole: the preview answers on threads, and a second request mustn't get a half-run module.
        mod = sys.modules.setdefault("talaria_db", mod)
    return mod


def run(apps_root: Path, app: str, name: str, request: bytes) -> str:
    """Run action ``name`` of ``app`` with ``request`` (JSON bytes); the envelope as JSON text."""
    if not NAME.fullmatch(app or "") or not NAME.fullmatch(name or ""):
        return failed("Not an app or action name.")
    if len(request) > MAX_REQUEST:
        return failed(f"The request is over {MAX_REQUEST // 1024} KB.")
    try:
        json.loads(request or b"null")
    except ValueError:
        return failed("The request isn't JSON.")
    db = db_module()
    if name == db.RESERVED:
        return db.query(apps_root, app, request)
    folder = (apps_root / app).resolve()
    script = (folder / "actions" / f"{name}.py").resolve()
    if script.parent != folder / "actions" or not script.is_file():
        return failed(f"{app} has no action named {name}.")
    if (folder / "migrations").is_dir():
        try:
            db.connect(apps_root, app).close()
        except Exception as e:
            return failed(f"{app}'s database: {e}")
    env = {**os.environ, "TALARIA_APP": app, "TALARIA_HOME": str(apps_root.parent), "TALARIA_DB": str(db.path(apps_root, app)),
           "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        p = subprocess.run([sys.executable, str(script)], input=request or b"null", cwd=folder, env=env,
                           capture_output=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return failed(f"{name} took longer than {TIMEOUT} seconds.")
    except OSError as e:
        return failed(f"{name} couldn't start: {e}")
    if p.returncode:
        detail = (p.stderr or p.stdout).decode("utf-8", "replace").strip().splitlines()
        return failed(detail[-1][:500] if detail else f"{name} failed ({p.returncode}).")
    out = p.stdout.strip()
    if len(out) > MAX_RESULT:
        return failed(f"{name} answered with more than {MAX_RESULT // 1024} KB.")
    try:
        result = json.loads(out or b"null")
    except ValueError:
        return failed(f"{name} didn't answer with JSON.")
    return json.dumps({"ok": True, "result": result})
