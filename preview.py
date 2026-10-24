"""Preview Talaria apps on this machine, the way the phone shows them, so Hermes can look before handing one back.

    python3 ~/.hermes/plugins/talaria/preview.py [name]

Starts the preview server in the background (or finds it already running) and prints where to look:

- ``http://<name>.localhost:8797/__phone/`` the app in a phone-sized frame (402×874), between a drawn status bar
  and home indicator, under Talaria's floating Back and ⋯ buttons, where they sit on the phone. Look at this one;
  ``/__phone/<page>`` frames a subpage.
- ``http://<name>.localhost:8797/`` the app on its own, for its console and for clicking through its pages.

Each app gets its own origin, as on the phone (``/`` is the app's folder), with Talaria's built-in libraries at
``/lib/`` and the same import map injected into every page. A folder is its ``index.html``; a route that isn't a
file serves the root ``index.html``. A ``.jsx``, ``.tsx`` or ``.ts`` file is compiled to plain JS as it's served,
by the same ``lib/compile.js`` the phone runs (here through node).
"""
from __future__ import annotations

import hashlib
import http.server
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

PORT = int(os.environ.get("TALARIA_PREVIEW_PORT", "8797"))
HERE = Path(__file__).resolve().parent
LIB = HERE / "lib"
# This copy of the preview and its compiler. A server that answers with another (one started before a plugin
# update) is replaced, since it would go on serving the old code.
STAMP = hashlib.sha256(Path(__file__).read_bytes() + ((LIB / "compile.js").read_bytes()
                                                    if (LIB / "compile.js").is_file() else b"")).hexdigest()[:12]

# What a page imports by name. Keep in step with CanvasSchemeHandler.importMap in the app.
IMPORT_MAP = ('<script type="importmap">{"imports":{"react":"/lib/react.js","react/jsx-runtime":"/lib/jsx-runtime.js",'
              '"react-dom":"/lib/react-dom.js","react-dom/client":"/lib/react-dom-client.js","html":"/lib/html.js",'
              '"htm":"/lib/html.js","viz":"/lib/viz.js","motion":"/lib/motion.js","motion/react":"/lib/motion.js",'
              '"framer-motion":"/lib/motion.js","lucide-react":"/lib/icons.js","icons":"/lib/icons.js","d3":"/lib/d3.js"}}'
              '</script>')

TYPES = {".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8", ".js": "text/javascript",
         ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml",
         ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
         ".woff2": "font/woff2", ".woff": "font/woff", ".txt": "text/plain; charset=utf-8", ".csv": "text/csv",
         ".jsx": "text/javascript", ".tsx": "text/javascript", ".ts": "text/javascript"}
COMPILED = {".jsx", ".tsx", ".ts"}

# The phone: an iPhone's 402×874 points. A browser has no notch, so the page sits between a drawn status bar (62)
# and home indicator (34), where env(safe-area-inset-*) would put it, painted in the page's own background, with
# Talaria's floating Back and ⋯ buttons over it. Scaled down to fit a short window.
PHONE = """<!doctype html><html><head><meta charset="utf-8"><title>{name} · phone preview</title>
<style>
  html,body{{margin:0;height:100%;background:#d9d9d6;display:grid;place-items:center;font:13px -apple-system,system-ui,sans-serif}}
  .phone{{position:relative;width:402px;height:874px;border-radius:48px;overflow:hidden;background:#fff;
          box-shadow:0 0 0 10px #111,0 20px 60px rgba(0,0,0,.35)}}
  iframe{{position:absolute;top:62px;left:0;width:402px;height:778px;border:0;background:transparent}}
  .status{{position:absolute;top:0;left:0;right:0;height:62px;display:flex;align-items:center;justify-content:space-between;
           padding:0 34px;font-weight:600;font-size:16px}}
  .island{{position:absolute;top:11px;left:50%;width:124px;height:36px;margin-left:-62px;border-radius:20px;background:#000}}
  .home{{position:absolute;bottom:0;left:0;right:0;height:34px}}
  .home::after{{content:"";position:absolute;bottom:8px;left:50%;width:134px;height:5px;margin-left:-67px;border-radius:3px;background:currentColor}}
  .btn{{position:absolute;top:62px;width:44px;height:44px;border-radius:22px;background:rgba(245,245,242,.88);
        box-shadow:0 1px 4px rgba(0,0,0,.2);display:grid;place-items:center;font-size:22px;color:#111;pointer-events:none}}
</style></head><body>
<div class="phone" id="phone">
  <div class="status" id="status"><span>9:41</span><span>●●● ▮</span></div><div class="island"></div>
  <iframe id="page" src="/{page}"></iframe>
  <div class="home" id="home"></div>
  <div class="btn" style="left:16px">‹</div><div class="btn" style="right:16px">⋯</div>
</div>
<script>
  const phone = document.getElementById('phone'), frame = document.getElementById('page')
  const fit = () => phone.style.zoom = Math.min(1, (innerHeight - 40) / 894)
  addEventListener('resize', fit); fit()
  // The bars take the page's background, as the page runs under them on the phone.
  frame.addEventListener('load', () => {{
    const d = frame.contentDocument, pick = el => el && getComputedStyle(el).backgroundColor
    let bg = [d.body, d.documentElement].map(pick).find(c => c && c !== 'transparent' && !/,\\s*0\\)$/.test(c)) || '#fff'
    phone.style.background = bg
    const [r, g, b] = (bg.match(/[\\d.]+/g) || [255, 255, 255]).map(Number)
    const ink = (0.299 * r + 0.587 * g + 0.114 * b) < 128 ? '#fff' : '#000'
    document.getElementById('status').style.color = ink
    document.getElementById('home').style.color = ink
  }})
</script></body></html>"""


def phone_url(name: str, page: str = "") -> str:
    return f"http://{name}.localhost:{PORT}/__phone/{page}"


def apps_root() -> Path:
    try:
        from hermes_constants import get_hermes_home
        home = Path(get_hermes_home())
    except Exception:
        home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home / "talaria" / "apps"


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def do_GET(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        path = self.path.split("?")[0].split("#")[0]
        if path == "/__talaria":
            return self.send(200, f"talaria-preview {STAMP} {os.getpid()}".encode(), "text/plain")
        if host.endswith(".localhost"):
            name = host[: -len(".localhost")]
            if path == "/__phone" or path.startswith("/__phone/"):
                # On the app's own origin, so the frame can read the page's background.
                page = path[len("/__phone/"):] if path.startswith("/__phone/") else ""
                return self.send(200, PHONE.format(name=name, page=page).encode(), "text/html; charset=utf-8")
            return self.app(name, path)
        names = sorted(p.name for p in apps_root().glob("*") if (p / "index.html").exists())
        body = "".join(f'<li><a href="{phone_url(n)}">{n}</a> · <a href="http://{n}.localhost:{PORT}/">alone</a></li>' for n in names)
        return self.send(200, f"<!doctype html><h1>Talaria apps</h1><ul>{body}</ul>".encode(), "text/html; charset=utf-8")

    def do_POST(self):
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if not host.endswith(".localhost"):
            return self.send(404, b"Not found", "text/plain")
        return self.action(host[: -len(".localhost")], self.path.split("?")[0])

    def action(self, app: str, path: str):
        """POST /__action/<name>: run one of the app's actions. Only the app's own page can: the SDK's custom header
        forces a CORS preflight (never answered here), so another site's page can't send it, and a foreign Origin
        is refused outright."""
        actions = actions_module()
        if not path.startswith("/__action/"):
            return self.send(404, b"Not found", "text/plain")
        origin = self.headers.get("Origin")
        if self.headers.get("X-Talaria-Action") != "1" or (origin and not local_origin(origin)):
            return self.send(403, actions.failed("Not from this app's page.").encode(), "application/json")
        size = int(self.headers.get("Content-Length") or 0)
        if size > actions.MAX_REQUEST:
            return self.send(413, actions.failed("The request is too large.").encode(), "application/json")
        body = actions.run(apps_root(), app, path[len("/__action/"):], self.rfile.read(size))
        return self.send(200, body.encode(), "application/json")

    def app(self, name: str, path: str):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
            return self.send(404, b"Not an app name", "text/plain")
        if path.startswith("/lib/"):
            return self.file(LIB / path[len("/lib/"):], LIB)
        root = (apps_root() / name).resolve()
        if not root.is_dir():
            return self.send(404, f"No app named {name} in {apps_root()}".encode(), "text/plain")
        rel = urllib.request.url2pathname(path.lstrip("/"))
        target = root / rel
        if path.endswith("/") or target.is_dir():
            target = target / "index.html"
        if not target.exists() and not Path(rel).suffix:
            target = root / "index.html"  # a route of a one-page app
        return self.file(target, root)

    def file(self, target: Path, within: Path):
        try:
            target = target.resolve()
            target.relative_to(within.resolve())  # never climb out of the folder
            data = target.read_bytes()
        except (ValueError, OSError):
            return self.send(404, b"Not found", "text/plain")
        kind = TYPES.get(target.suffix.lower(), "application/octet-stream")
        if kind.startswith("text/html"):
            data = inject(data)
        elif target.suffix.lower() in COMPILED:
            data = compiled(target, "/" + target.relative_to(within.resolve()).as_posix(), data)
        return self.send(200, data, kind)

    def send(self, code: int, body: bytes, kind: str):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def actions_module():
    """actions.py from beside this file, loaded by path: preview.py runs both as a script and inside the backend,
    where putting the plugin's folder on sys.path could shadow other modules."""
    import importlib.util
    mod = sys.modules.get("talaria_actions")
    if mod is None:
        spec = importlib.util.spec_from_file_location("talaria_actions", HERE / "actions.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        sys.modules["talaria_actions"] = mod
    return mod


def local_origin(origin: str) -> bool:
    """An Origin from this machine's own pages: the preview's *.localhost origins and Desktop's loopback ports."""
    host = urllib.parse.urlsplit(origin).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")


def inject(data: bytes) -> bytes:
    html = data.decode("utf-8", "replace")
    if "importmap" in html:
        return data
    lower = html.lower()
    i = lower.find("<head")
    if i >= 0:
        j = html.find(">", i) + 1
        html = html[:j] + IMPORT_MAP + html[j:]
    else:
        html = IMPORT_MAP + html
    return html.encode()


# One node process compiles every file, a line of JSON in ([source, path]) and out (the module), with
# lib/compile.js loaded once. It starts on the first .jsx/.tsx/.ts asked for, and again if it dies.
NODE_COMPILER = ("const vm = require('vm'), fs = require('fs');"
                 "vm.runInThisContext(fs.readFileSync(process.argv[1], 'utf8'));"
                 "require('readline').createInterface({ input: process.stdin }).on('line', (l) => {"
                 "  const [source, path] = JSON.parse(l);"
                 "  process.stdout.write(JSON.stringify(talariaCompile(source, path)) + '\\n') })")
_compiler: subprocess.Popen | None = None
_compiler_lock = threading.Lock()
_compiled: dict[tuple, bytes] = {}  # by (file, mtime, size)


def throwing(message: str) -> bytes:
    """A module that fails with ``message``, so it shows in the page's console."""
    return f"throw new Error({json.dumps(message)})\n".encode()


def compiled(target: Path, path: str, data: bytes) -> bytes:
    """The file at ``target`` (``path`` within its app) as plain JS, the way the phone compiles it."""
    stat = target.stat()
    key = (str(target), stat.st_mtime_ns, stat.st_size)
    code = _compiled.get(key)
    if code is None:
        if len(_compiled) > 256:
            _compiled.clear()
        code = _compiled[key] = compile_module(data.decode("utf-8", "replace"), path)
    return code


def compile_module(source: str, path: str) -> bytes:
    global _compiler
    with _compiler_lock:
        for _ in range(2):
            if _compiler is None or _compiler.poll() is not None:
                node = shutil.which("node")
                if not node:
                    return throwing(f"Can't compile {path}: JSX and TypeScript need Node.js on the Hermes machine. "
                                    "Write plain .js instead.")
                if not (LIB / "compile.js").is_file():
                    return throwing(f"Can't compile {path}: lib/compile.js is missing; reinstall the plugin.")
                _compiler = subprocess.Popen([node, "-e", NODE_COMPILER, str(LIB / "compile.js")], stdin=subprocess.PIPE,
                                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                             encoding="utf-8")
            try:
                _compiler.stdin.write(json.dumps([source, path]) + "\n")
                _compiler.stdin.flush()
                line = _compiler.stdout.readline()
                if line:
                    return json.loads(line).encode()
            except (OSError, ValueError):
                pass
            _compiler.kill()
            _compiler = None
    return throwing(f"Talaria couldn't compile {path}.")


def ping() -> str:
    """What answers on the port: ``talaria-preview <stamp> <pid>`` from a preview server (just ``talaria-preview``
    from one before plugin 0.2.7), something else, or "" for nothing."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/__talaria", timeout=1) as r:
            return r.read().decode("utf-8", "replace")
    except OSError:
        return ""


def running() -> bool:
    return ping().split()[:2] == ["talaria-preview", STAMP]


def stop_stale() -> None:
    """Stop a preview server that an older copy of this file started."""
    words = ping().split()
    if words[:1] != ["talaria-preview"] or words[1:2] == [STAMP]:
        return
    try:
        if len(words) == 3 and words[2].isdigit():
            os.kill(int(words[2]), signal.SIGTERM)
        else:
            subprocess.run(["pkill", "-f", "preview.py --serve"], check=False)
    except OSError:
        pass
    for _ in range(50):
        if not ping():
            return
        time.sleep(0.1)


def serve() -> None:
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


# Hermes Desktop shows an app through its SSH forward to one loopback port, which rewrites the host to 127.0.0.1,
# so `<name>.localhost` can't pick the app there: each app gets a port of its own instead, served from the
# process that asked (the backend Desktop talks to) for as long as it runs.
_app_ports: dict[str, int] = {}
_app_lock = threading.Lock()


def serve_app(name: str) -> int:
    """The loopback port serving app ``name`` at its root, starting it on first ask."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name) or not (apps_root() / name / "index.html").is_file():
        raise LookupError(f"No app named {name}")
    with _app_lock:
        if name not in _app_ports:
            class AppHandler(Handler):
                def do_GET(self):
                    return self.app(name, self.path.split("?")[0].split("#")[0])

                def do_POST(self):
                    return self.action(name, self.path.split("?")[0])
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), AppHandler)
            threading.Thread(target=server.serve_forever, daemon=True, name=f"talaria-app-{name}").start()
            _app_ports[name] = server.server_address[1]
        return _app_ports[name]


def main(argv: list[str]) -> int:
    if argv[:1] == ["--serve"]:
        serve()
        return 0
    if not LIB.is_dir():
        print(f"Talaria's libraries are missing ({LIB}); reinstall the plugin.", file=sys.stderr)
        return 1
    stop_stale()
    if not running():
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", PORT)) == 0:
                print(f"Port {PORT} is taken by something else; set TALARIA_PREVIEW_PORT.", file=sys.stderr)
                return 1
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--serve"], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            if running():
                break
            time.sleep(0.1)
        else:
            print("The preview server didn't start.", file=sys.stderr)
            return 1
    name = argv[0] if argv else None
    if name:
        if not (apps_root() / name / "index.html").exists():
            print(f"No app at {apps_root() / name}/index.html", file=sys.stderr)
            return 1
        print(f"phone:  {phone_url(name)}")
        print(f"alone:  http://{name}.localhost:{PORT}/")
    else:
        print(f"apps:   http://localhost:{PORT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
