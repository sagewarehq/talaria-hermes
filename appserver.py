"""The workspace dev server (workspace/talaria/serve.mjs): every app in the workspace live on one loopback port, with
no build step.

    python3 ~/.hermes/plugins/talaria/appserver.py [name]

starts it (or finds it running) and prints where it is: ``http://127.0.0.1:<port>/<name>/``. That's what Hermes
looks at to see an app as Hermes Desktop shows it. ``/talaria open`` starts it on first ask and hands back its port; Desktop forwards that port as it
does the per-app ones.

One per Talaria home, whichever backend asked first: its port and pid are in ``talaria/apps-server.json``, and a lock
keeps two backends from starting it at once. A server started from an older copy of the plugin is replaced. Starting
can take a while (npm install, Vite's first dependency scan), so it happens in the background and ``ensure`` says
"starting" until the server answers.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "workspace" / "talaria"
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
RESERVED = {"apps", "shared", "talaria", "node_modules", "lib", "legacy", "assets"}  # as in talaria/apps.mjs
DEFAULT_PORT = 8798
READY_WAIT = 90  # seconds for a fresh server to answer

def stamp() -> str:
    """This copy of the server's code, read now (not when the plugin loaded: a long-running gateway would otherwise
    keep an old stamp after a deploy). One that answers with another is replaced, since it runs the old code."""
    return hashlib.sha256(b"".join(p.read_bytes() for p in sorted(TEMPLATE.glob("*")) if p.is_file())).hexdigest()[:12]

_thread: threading.Thread | None = None
_error: str | None = None


def _build():
    import importlib.util
    mod = sys.modules.get("talaria_build")
    if mod is None:  # build.py from beside this file, by path, as preview.py loads actions.py
        spec = importlib.util.spec_from_file_location("talaria_build", HERE / "build.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["talaria_build"] = mod
    return mod


def home() -> Path:
    return _build().talaria_home()


def runs(name: str) -> bool:
    """Whether ``name`` opens from the dev server: a workspace app that's only an App.tsx (no index.html of its own).
    Older apps, with their own index.html, keep opening from their build on a port of their own."""
    src = home() / "workspace" / "apps" / name
    return (bool(NAME.fullmatch(name)) and name not in RESERVED and not (src / "index.html").exists()
            and any((src / f).is_file() for f in ("App.tsx", "App.jsx")))


def _state_path() -> Path:
    return home() / "apps-server.json"


def _state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def ping(port: int) -> list[str]:
    """What answers on ``port``: ``["talaria-apps", stamp, pid]`` from a dev server, else something else or []."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/__talaria/ping", timeout=2) as r:
            return r.read().decode("utf-8", "replace").split()
    except OSError:
        return []


def _current(port: int | None) -> bool:
    return bool(port) and ping(port)[:2] == ["talaria-apps", stamp()]


def _free(port: int) -> bool:
    with socket.socket() as s:
        # As node binds: connections the last server left in TIME_WAIT don't keep the port.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def ensure() -> dict:
    """``{"state": "ready", "port": n}`` when the server is up and current; else start it in the background and
    say ``{"state": "starting"}`` (or ``"failed"`` with the reason, after a start that didn't take)."""
    global _thread, _error
    port = _state().get("port")
    if _current(port):
        return {"state": "ready", "port": port}
    if _thread and _thread.is_alive():
        return {"state": "starting"}
    if _error:
        error, _error = _error, None
        return {"state": "failed", "error": error}
    _thread = threading.Thread(target=_start_logged, daemon=True, name="talaria-apps-start")
    _thread.start()
    return {"state": "starting"}


def _start_logged() -> None:
    global _error
    try:
        start()
    except Exception as e:  # reported on the next ensure()
        _error = f"{type(e).__name__}: {e}"[:2000]


def start() -> int:
    """Start the server (or find it started by another backend meanwhile) and wait until it answers. Its port."""
    build = _build()
    home().mkdir(parents=True, exist_ok=True)
    with open(home() / "apps-server.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _state()
        if _current(state.get("port")):
            return state["port"]
        _stop(state)
        ws = build.workspace()
        env = build.node_env()
        with build.locked(ws):
            build.seed(ws)
            build.install(ws, env)
        port = state.get("port") or DEFAULT_PORT
        for _ in range(20):  # the server just stopped can take a moment to let go of its port
            if _free(port):
                break
            time.sleep(0.25)
        else:
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
        admin = secrets.token_urlsafe(24)
        log = open(home() / "apps-server.log", "ab")
        child = subprocess.Popen(
            [shutil_which_node(env), str(ws / "talaria" / "serve.mjs")], cwd=ws, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            env={**env, "TALARIA_PORT": str(port), "TALARIA_HOME": str(home()), "TALARIA_PYTHON": sys.executable,
                 "TALARIA_PLUGIN": str(HERE), "TALARIA_STAMP": stamp(), "TALARIA_ADMIN": admin, "NO_COLOR": "1"})
        _state_path().write_text(json.dumps({"port": port, "pid": child.pid, "stamp": stamp(), "admin": admin}) + "\n")
        os.chmod(_state_path(), 0o600)  # the admin secret
        deadline = time.time() + READY_WAIT
        while time.time() < deadline:
            if _current(port):
                return port
            if child.poll() is not None:
                break
            time.sleep(0.5)
        child.kill()
        raise RuntimeError("The apps server didn't start:\n" + _tail(home() / "apps-server.log"))


def gate(host: str) -> dict:
    """Open the gate on ``host`` (the address Desktop reaches the gateway at) and mint a ticket for one device:
    ``{"port": n, "ticket": "…"}``, or ``{"error": "…"}``. The server must be ready."""
    state = _state()
    req = urllib.request.Request(f"http://127.0.0.1:{state.get('port')}/__talaria/gate", method="POST",
                                 data=json.dumps({"host": host}).encode(),
                                 headers={"X-Talaria-Admin": state.get("admin", ""), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except ValueError:
            return {"error": f"The gate said {e.code}."}
    except (OSError, ValueError) as e:
        return {"error": f"Couldn’t open the gate: {e}"}


def snapshot(app: str | None = None, wait: float = 8) -> dict:
    """What the app page you share with Hermes shows (the newest one, or ``app``'s): its app, title, page, the text in
    view, all its readable text and any selection, read now. ``{"error": "…"}`` when none is shared or it doesn't
    answer within ``wait`` seconds. Never starts the server: a page can only be shared from one that's running."""
    state = _state()
    if not _current(state.get("port")):
        return {"error": "No app page is shared with Hermes."}
    req = urllib.request.Request(f"http://127.0.0.1:{state['port']}/__talaria/snapshot", method="POST",
                                 data=json.dumps({"app": app or "", "wait": int(wait * 1000)}).encode(),
                                 headers={"X-Talaria-Admin": state.get("admin", ""), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=wait + 5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except ValueError:
            return {"error": f"The apps server said {e.code}."}
    except (OSError, ValueError) as e:
        return {"error": f"Couldn’t reach the apps server: {e}"}


def shutil_which_node(env: dict[str, str]) -> str:
    import shutil
    return shutil.which("node", path=env.get("PATH")) or "node"


def _stop(state: dict) -> None:
    """Stop a server this file's older copy started, if it's still the one on its port."""
    pid, port = state.get("pid"), state.get("port")
    if not pid or not port or ping(port)[:1] != ["talaria-apps"]:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(40):
        if not ping(port):
            return
        time.sleep(0.25)


def _tail(path: Path, lines: int = 30) -> str:
    try:
        text = re.sub(r"\x1b\[[0-9;]*m", "", path.read_text(errors="replace"))
        return "\n".join(text.splitlines()[-lines:])
    except OSError:
        return ""


def title(name: str) -> str | None:
    """The app's ``meta.title``, read from its App.tsx without running it (as talaria/apps.mjs does)."""
    return meta(name, "title")


def meta(name: str, key: str) -> str | None:
    """A string in the app's ``export const meta = { … }``: ``title``, or ``glyph`` (its icon, appprefs.ICONS)."""
    src = home() / "workspace" / "apps" / name
    for f in ("App.tsx", "App.jsx"):
        try:
            text = (src / f).read_text(errors="replace")
        except OSError:
            continue
        m = re.search(r"export\s+const\s+meta\s*(?::[^=]+)?=\s*\{[^}]*?\b" + key + r"\s*:\s*(['\"`])(.*?)\1", text, re.S)
        return m.group(2) if m else None
    return None

if __name__ == "__main__":
    try:
        port = start()
    except Exception as e:
        sys.exit(f"{type(e).__name__}: {e}")
    print(f"http://127.0.0.1:{port}/{sys.argv[1]}/" if len(sys.argv) > 1 else f"http://127.0.0.1:{port}/")
