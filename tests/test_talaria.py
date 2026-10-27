"""Run on the box with Hermes's interpreter (needs hermes_cli for pid liveness):
    HERMES_HOME=$(mktemp -d) /usr/local/lib/hermes-agent/venv/bin/python -m pytest -q tests/
"""
import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("TALARIA_NO_STARTERS", "1")  # loading the plugin mustn't install Newsroom in a test


@pytest.fixture()
def talaria(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    # Import the plugin package from its directory regardless of the folder name.
    import importlib.util
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("talaria_plugin", root / "__init__.py",
                                                  submodule_search_locations=[str(root)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["talaria_plugin"] = mod
    spec.loader.exec_module(mod)
    mod.store.home = lambda: tmp_path  # never touch the real ~/.hermes
    return mod


def inbox(t):
    return json.loads(t.handle_command("inbox --json"))["rows"]


def test_turn_lifecycle(talaria):
    talaria.on_session_start(session_id="s1", platform="desktop")
    assert [r["state"] for r in inbox(talaria)] == ["running"]
    talaria.pre_approval_request(session_id="s1", command="rm -rf build", description="Delete build output")
    row = inbox(talaria)[0]
    assert row["state"] == "approval" and row["reason"] == "Delete build output"
    talaria.post_approval_response(session_id="s1", choice="once")
    assert inbox(talaria)[0]["state"] == "running"
    talaria.on_session_end(session_id="s1", turn_id="t1", completed=True)
    assert [r["state"] for r in inbox(talaria)] == ["done"]  # finished in the last day
    talaria.handle_command("dismiss s1")
    assert inbox(talaria) == []


def test_reply_to_needs_you_starts_a_new_turn(talaria, monkeypatch):
    # Only a session's first turn fires on_session_start; later turns start with pre_llm_call.
    monkeypatch.setenv("TALARIA_ATTENTION_CLASSIFY", "0")
    talaria.on_session_start(session_id="s5")
    talaria.on_session_end(session_id="s5", turn_id="t1", completed=True)
    talaria.store.set_state("s5", "needs_you", reason="Approve the archive", turn_id="t1")
    assert inbox(talaria)[0]["state"] == "needs_you"
    talaria.pre_llm_call(session_id="s5", turn_id="t2")
    assert inbox(talaria)[0]["state"] == "running"
    talaria.on_session_end(session_id="s5", turn_id="t2", completed=True)
    assert [r["state"] for r in inbox(talaria)] == ["done"]  # the old "needs you" is gone


def test_known_lists_tracked_sessions(talaria):
    talaria.on_session_start(session_id="s6")
    feed = json.loads(talaria.handle_command("inbox --json"))
    assert "s6" in feed["known"]


def test_question_hides_secret_prompts(talaria):
    talaria.on_human_input_request(session_id="s2", kind="clarify", prompt="Which month?")
    assert inbox(talaria)[0]["reason"] == "Which month?"
    talaria.on_human_input_request(session_id="s3", kind="secret", prompt="Paste the API key")
    assert [r for r in inbox(talaria) if r["session_id"] == "s3"][0]["reason"] == "secret"
    talaria.on_human_input_resolved(session_id="s2", outcome="answered")
    assert [r for r in inbox(talaria) if r["session_id"] == "s2"][0]["state"] == "running"


def test_dead_writer_reads_stale(talaria):
    talaria.on_session_start(session_id="s4")
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    c = talaria.store.connect()
    c.execute("UPDATE attention SET writer_pid=?, writer_start=NULL WHERE session_id='s4'", (child.pid,))
    c.close()
    assert inbox(talaria)[0]["state"] == "stale"


def test_dismiss_until_next_turn(talaria):
    talaria.pre_approval_request(session_id="s5", command="x", turn_id="t1")
    assert json.loads(talaria.handle_command("dismiss s5"))["dismissed"] is True
    assert inbox(talaria) == []
    talaria.on_session_end(session_id="s5", turn_id="t1")
    talaria.on_session_start(session_id="s5")
    assert inbox(talaria)[0]["state"] == "running"  # a new turn raises it again


def test_late_dismiss_spares_a_newer_turn(talaria, monkeypatch):
    # The user cleared turn t1, but the dismissal reached the box after t2 had started (a cached row,
    # an Undo that waited, a retry): t2 still shows.
    monkeypatch.setenv("TALARIA_ATTENTION_CLASSIFY", "0")
    talaria.pre_llm_call(session_id="s10", turn_id="t1")
    talaria.on_session_end(session_id="s10", turn_id="t1", completed=True)
    talaria.pre_llm_call(session_id="s10", turn_id="t2")
    talaria.on_session_end(session_id="s10", turn_id="t2", completed=True)
    assert json.loads(talaria.handle_command("dismiss s10 t1"))["dismissed"] is True
    assert [r["state"] for r in inbox(talaria)] == ["done"]
    talaria.handle_command("dismiss s10 t2")
    assert inbox(talaria) == []


def test_dismiss_an_untracked_session_with_a_turn(talaria):
    assert json.loads(talaria.handle_command("dismiss s11 t1"))["dismissed"] is True
    assert inbox(talaria) == []


def test_hooks_never_raise(talaria, monkeypatch):
    monkeypatch.setattr(talaria.store, "set_state", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    assert talaria.pre_approval_request(session_id="s6", command="x") is None
    assert talaria.on_session_start(session_id="s6") is None


def test_command_surface(talaria):
    assert json.loads(talaria.handle_command("version"))["plugin"] == "talaria"
    assert json.loads(talaria.handle_command("whoami"))["pid"] == os.getpid()
    assert talaria.handle_command("bogus").startswith("usage")


class _Msg:
    def __init__(self, content): self.content = content
class _Choice:
    def __init__(self, content): self.message = _Msg(content)
class _Resp:
    def __init__(self, content): self.choices = [_Choice(content)]


def test_needs_you_after_turn(talaria, monkeypatch):
    monkeypatch.setattr(talaria.store, "last_assistant_text",
                        lambda sid: "I prepared the Wise bulk CSV in Finance/Payables. Upload it to Wise when ready.")
    monkeypatch.setattr(talaria, "classify", lambda text: (True, "Upload the Wise CSV"))
    talaria.on_session_start(session_id="s7")
    talaria.on_session_end(session_id="s7", turn_id="t1", completed=True)
    for th in __import__("threading").enumerate():
        if th.name == "talaria-classify":
            th.join(5)
    row = inbox(talaria)[0]
    assert row["state"] == "needs_you" and row["reason"] == "Upload the Wise CSV"
    talaria.handle_command("dismiss s7")
    assert inbox(talaria) == []


def test_new_turn_beats_late_classification(talaria, monkeypatch):
    monkeypatch.setattr(talaria.store, "last_assistant_text", lambda sid: "Want me to process these three requests?")
    talaria.on_session_start(session_id="s8")
    talaria.store.set_state("s8", "idle")
    talaria.on_session_start(session_id="s8")          # the user already replied: a new turn is running
    monkeypatch.setattr(talaria, "classify", lambda text: (True, "Reply"))
    talaria._classify_turn("s8", "t1")
    assert inbox(talaria)[0]["state"] == "running"


def test_parse_verdict(talaria):
    assert talaria.parse_verdict('{"needs_you": true, "next": "Approve  the transfer"}') == (True, "Approve the transfer")
    assert talaria.parse_verdict('```json\n{"needs_you": false, "next": ""}\n```') == (False, "")
    assert talaria.parse_verdict("no idea") is None
    assert talaria.parse_verdict('{"needs_you": "yes"}') is None


def test_dismiss_an_untracked_session(talaria):
    # Its turns ran in a backend without the plugin: the dismissal still lands here, hidden, and the
    # session is known, so every device leaves it to the store (and a new turn raises it again).
    assert json.loads(talaria.handle_command("dismiss s9"))["dismissed"] is True
    assert inbox(talaria) == []
    assert "s9" in json.loads(talaria.handle_command("inbox --json"))["known"]
    talaria.pre_llm_call(session_id="s9", turn_id="t1")
    assert inbox(talaria)[0]["state"] == "running"


def test_registers_the_app_skill(talaria):
    class Ctx:
        def __init__(self): self.skills, self.hooks, self.commands, self.tools = {}, [], [], {}
        def register_hook(self, name, fn): self.hooks.append(name)
        def register_tool(self, name, toolset, schema, handler, **kw): self.tools[name] = (toolset, schema, handler)
        def register_command(self, name, **kw): self.commands.append(name)
        def register_skill(self, name, path, description=""): self.skills[name] = (Path(path), description)
    ctx = Ctx()
    talaria.register(ctx)
    path, description = ctx.skills["app"]
    text = path.read_text()
    assert text.startswith("---\nname: app\n") and description
    assert "MEDIA:/root/.hermes/talaria/apps/" in text  # how Talaria knows to show the app card
    path, _ = ctx.skills["routine"]
    assert path.read_text().startswith("---\nname: routine\n")
    toolset, schema, handler = ctx.tools["app_snapshot"]
    assert toolset == "talaria" and schema["name"] == "app_snapshot"
    assert json.loads(handler({})) == {"error": "No app page is shared with Hermes."}  # no apps server running


def test_moves_canvases_to_apps(talaria):
    root = talaria.store.home() / "talaria"
    (root / "canvases" / "trips").mkdir(parents=True)
    (root / "canvases" / "trips" / "index.html").write_text("<title>Trips</title>")
    talaria.move_canvases()
    assert (root / "apps" / "trips" / "index.html").read_text() == "<title>Trips</title>"
    assert not (root / "canvases").exists()
    talaria.move_canvases()  # once: nothing left to move
    assert (root / "apps" / "trips").is_dir()


def test_lists_apps_newest_first(talaria):
    root = talaria.store.home() / "talaria" / "apps"
    for name, title, mtime in (("trips", "<title> Trip\n planner </title>", 100), ("budget", "<h1>no title</h1>", 200)):
        (root / name).mkdir(parents=True)
        (root / name / "index.html").write_text(title)
        os.utime(root / name / "index.html", (mtime, mtime))
    (root / "half-built").mkdir()  # no index page: not an app yet
    apps = json.loads(talaria.handle_command("apps"))["apps"]
    assert [(a["name"], a["title"], a["updated"]) for a in apps] == [("budget", None, 200), ("trips", "Trip planner", 100)]


def test_an_apps_stamp_changes_with_its_code_but_not_its_data(talaria):
    app = talaria.store.home() / "talaria" / "apps" / "trips"
    app.mkdir(parents=True)
    (app / "index.html").write_text("<title>Trips</title>")
    stamp = lambda: json.loads(talaria.handle_command("apps"))["apps"][0]["stamp"]
    first = stamp()
    for name in ("app.db", "app.db-wal", "app.db-shm", "data.json"):
        (app / name).write_bytes(b"rows")
    assert stamp() == first
    (app / "app.jsx").write_text("export default () => null")
    assert stamp() != first


def test_app_icons_and_pins_are_kept_for_every_device(talaria, monkeypatch):
    """An app's icon is the one picked, else its own meta.glyph if that's in the kit; pins keep their order."""
    from talaria_plugin import appserver
    root = talaria.store.home() / "talaria" / "apps"
    for name in ("trips", "budget"):
        (root / name).mkdir(parents=True)
        (root / name / "index.html").write_text("<title>x</title>")
    ws = talaria.store.home() / "talaria" / "workspace" / "apps" / "notes"
    ws.mkdir(parents=True)
    (ws / "App.tsx").write_text("export const meta = { title: 'Notes', glyph: 'book' }\nexport default () => null")
    monkeypatch.setattr(appserver, "runs", lambda name: name == "notes")
    apps = lambda: {a["name"]: (a["icon"], a["pinned"]) for a in json.loads(talaria.handle_command("apps"))["apps"]}
    assert apps() == {"trips": (None, None), "budget": (None, None), "notes": ("book", None)}

    assert json.loads(talaria.handle_command("app-icon trips rocket")) == {"name": "trips", "icon": "rocket"}
    assert "error" in json.loads(talaria.handle_command("app-icon trips wallet"))  # not in the kit
    assert "error" in json.loads(talaria.handle_command("app-icon ../x rocket"))
    talaria.handle_command("app-icon notes heart")
    assert json.loads(talaria.handle_command("pin budget")) == {"pinned": ["budget"]}
    assert json.loads(talaria.handle_command("pin trips")) == {"pinned": ["budget", "trips"]}
    assert apps() == {"trips": ("rocket", 1), "budget": (None, 0), "notes": ("heart", None)}

    talaria.handle_command("app-icon notes none")  # back to its own
    assert json.loads(talaria.handle_command("unpin budget")) == {"pinned": ["trips"]}
    assert apps() == {"trips": ("rocket", 0), "budget": (None, None), "notes": ("book", None)}
    assert "rocket" in json.loads(talaria.handle_command("apps"))["icons"]


def test_open_serves_an_app_on_its_own_port(talaria):
    import urllib.request
    app = talaria.store.home() / "talaria" / "apps" / "trips"
    app.mkdir(parents=True)
    (app / "index.html").write_text("<html><head><title>Trips</title></head><body>home</body></html>")
    (app / "data.json").write_text('{"ok": true}')
    port = json.loads(talaria.handle_command("open trips"))["port"]
    get = lambda path: urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5).read().decode()
    assert "importmap" in get("/") and "home" in get("/trips/42")  # the root is the app, routes fall back to it
    assert get("/data.json") == '{"ok": true}'
    assert json.loads(talaria.handle_command("open trips"))["port"] == port  # one server per app, reused
    assert "error" in json.loads(talaria.handle_command("open nope"))
    assert "error" in json.loads(talaria.handle_command("open ../trips"))


def test_apps_that_are_only_an_app_tsx_open_from_the_dev_server(talaria, monkeypatch):
    """A workspace app that's only an App.tsx is listed (built or not, titled from its meta) and opens at /<app>/ on
    the dev server; an older app with its own index.html keeps its own port; --via asks for the gate."""
    from talaria_plugin import appserver
    ws = talaria.store.home() / "talaria" / "workspace" / "apps"
    (ws / "notes").mkdir(parents=True)
    (ws / "notes" / "App.tsx").write_text("export const meta = { title: 'My notes' }\nexport default () => null\n")
    (ws / "old").mkdir()
    (ws / "old" / "App.tsx").write_text("export default () => null\n")
    (ws / "old" / "index.html").write_text("<title>Old</title>")
    (ws / "lib").mkdir()
    (ws / "lib" / "App.tsx").write_text("export default () => null\n")  # a name the server keeps for itself
    built = talaria.store.home() / "talaria" / "apps" / "old"
    built.mkdir(parents=True)
    (built / "index.html").write_text("<title>Old</title>")
    assert appserver.runs("notes") and not appserver.runs("old") and not appserver.runs("lib")
    listed = {a["name"]: a["title"] for a in json.loads(talaria.handle_command("apps"))["apps"]}
    assert listed == {"notes": "My notes", "old": "Old"}
    monkeypatch.setattr(appserver, "ensure", lambda: {"state": "ready", "port": 8798})
    monkeypatch.setattr(appserver, "gate", lambda host: {"port": 8798, "ticket": f"t-{host}"})
    assert json.loads(talaria.handle_command("open notes")) == {"state": "ready", "port": 8798, "path": "/notes/"}
    gated = json.loads(talaria.handle_command("open notes --via 100.64.0.3"))
    assert gated["ticket"] == "t-100.64.0.3" and gated["path"] == "/notes/"
    monkeypatch.setattr(appserver, "ensure", lambda: {"state": "starting"})
    assert json.loads(talaria.handle_command("open notes --via 100.64.0.3")) == {"state": "starting", "path": "/notes/"}


@pytest.mark.skipif(not os.environ.get("TALARIA_TEST_BUILD"), reason="set TALARIA_TEST_BUILD=1 (npm installs, ~30 s)")
def test_dev_server_end_to_end(talaria):
    """The real dev server: an App.tsx app's page, its data folder, its server.ts, an action, its server code kept
    from the browser, and the gate letting a device in only with a ticket."""
    import time, urllib.error, urllib.request
    from talaria_plugin import appserver
    home = talaria.store.home() / "talaria"
    src, data = home / "workspace" / "apps" / "notes", home / "apps" / "notes"
    src.mkdir(parents=True)
    (data / "actions").mkdir(parents=True)
    (src / "App.tsx").write_text("export const meta = { title: 'Notes' }\nexport default function App() { return <p>notes</p> }\n")
    (src / "server.ts").write_text(
        "export default async (req: Request, ctx: any) => {\n"
        "  if (new URL(req.url).pathname.endsWith('/notes')) return Response.json((await ctx.db()).prepare('SELECT body FROM notes').all())\n"
        "  return new Response(`hi ${ctx.app} ${new URL(req.url).pathname}`)\n}\n")
    (data / "migrations").mkdir(parents=True)
    (data / "migrations" / "001-notes.sql").write_text("CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT);\n")
    (data / "data.json").write_text('{"n": 1}')
    (data / "actions" / "echo.py").write_text("import json, sys\nprint(json.dumps(json.load(sys.stdin)))\n")
    try:
        while (state := appserver.ensure())["state"] == "starting":
            time.sleep(1)
        assert state["state"] == "ready", state
        base = f"http://127.0.0.1:{state['port']}"

        def get(path, **kw):
            req = urllib.request.Request(base + path, **kw)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode()

        status, page = get("/notes/")
        assert status == 200 and "<title>Notes</title>" in page and "/@talaria/entry/notes" in page
        assert get("/notes/data.json") == (200, '{"n": 1}')
        assert get("/notes/api/x") == (200, "hi notes /notes/api/x")
        assert get("/apps/notes/server.ts")[0] == 404
        assert get("/notes/actions/echo.py")[0] == 404
        assert get("/notes/__action/echo", method="POST", data=b'{"a": 1}', headers={"X-Talaria-Action": "1"}) == \
            (200, '{"ok": true, "result": {"a": 1}}')
        assert get("/notes/__action/echo", method="POST", data=b"1")[0] == 403  # no SDK header: not the app's page
        # the page's db call and server.ts's node:sqlite reach the same database
        status, out = get("/notes/__action/talaria-db", method="POST", headers={"X-Talaria-Action": "1"},
                          data=b'{"sql": "INSERT INTO notes (body) VALUES (?)", "params": ["hello"]}')
        assert status == 200 and json.loads(out)["result"]["changes"] == 1, out
        assert json.loads(get("/notes/api/notes")[1]) == [{"body": "hello"}]
        gate = appserver.gate("127.0.0.1")
        assert appserver.gate("0.0.0.0").get("error")
        gated = f"http://127.0.0.1:{gate['port']}"
        assert gate["port"] != state["port"]

        def through(path):
            try:
                with urllib.request.urlopen(urllib.request.Request(gated + path), timeout=30) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code
        assert through("/notes/") == 403
        assert through(f"/notes/?talaria-ticket={gate['ticket']}") == 200  # unlocked, then redirected to /notes/
        assert through("/notes/") == 200
        assert through("/__talaria/gate") == 404
        # The page channel: nothing shared yet; then a page watches, and the plugin's ask reaches it and comes back
        # with what it answered (its app the one it watched), only with the page's header
        import http.client, threading
        assert appserver.snapshot() == {"error": "No app page is shared with Hermes."}
        conn = http.client.HTTPConnection("127.0.0.1", state["port"], timeout=30)
        conn.request("GET", "/notes/__page/watch")
        stream = conn.getresponse()
        assert stream.status == 200
        answered = []

        def page():
            event = {}
            while not event:
                line = stream.fp.readline().decode()
                if line.startswith("data: "):
                    event = json.loads(line[6:])
            reply = lambda shot: json.dumps({"id": event["id"], "snapshot": shot}).encode()
            answered.append(get("/notes/__page/answer", method="POST", data=reply({}))[0])
            answered.append(get("/notes/__page/answer", method="POST", headers={"X-Talaria-Page": "1"},
                                data=reply({"title": "Notes", "visible": "hello", "app": "other"}))[0])
        reader = threading.Thread(target=page)
        reader.start()
        assert appserver.snapshot() == {"title": "Notes", "visible": "hello", "app": "notes"}
        reader.join(10)
        assert answered == [403, 204]
        assert appserver.snapshot("other") == {"error": "No app page is shared with Hermes."}
        assert json.loads(talaria.app_snapshot({"app": "other"}))["error"]
        conn.close()
    finally:
        pid = json.loads((home / "apps-server.json").read_text()).get("pid") if (home / "apps-server.json").exists() else None
        if pid:
            os.killpg(pid, 15)


def test_preview_serves_an_app_like_the_phone(tmp_path, monkeypatch):
    """preview.py: each app on its own origin, the import map injected, folders and routes resolved, nothing
    outside the app's folder."""
    import importlib.util, threading, urllib.request
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("talaria_preview", root / "preview.py")
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    app = tmp_path / "talaria" / "apps" / "trips"
    (app / "cebu").mkdir(parents=True)
    (app / "index.html").write_text("<html><head><title>Trips</title></head><body>home</body></html>")
    (app / "cebu" / "index.html").write_text("<html><head></head><body>cebu</body></html>")
    (app / "data.json").write_text('{"ok": true}')
    (tmp_path / "talaria" / "attention.db").write_text("secret")
    monkeypatch.setattr(preview, "apps_root", lambda: tmp_path / "talaria" / "apps")
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "viz.js").write_text("export const x = 1")
    monkeypatch.setattr(preview, "LIB", lib)
    server = preview.http.server.ThreadingHTTPServer(("127.0.0.1", 0), preview.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def get(path, host="trips.localhost"):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": f"{host}:{port}"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.headers["Content-Type"], r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.headers["Content-Type"], ""

    try:
        status, kind, body = get("/")
        assert status == 200 and kind.startswith("text/html") and '<script type="importmap">' in body and "home" in body
        assert "cebu" in get("/cebu/")[2]
        assert get("/data.json")[1] == "application/json"
        assert "home" in get("/settings/42")[2]  # a route that isn't a file: the app's first page
        assert get("/lib/viz.js")[2] == "export const x = 1"
        assert get("/__talaria")[2] == f"talaria-preview {preview.STAMP} {os.getpid()}"
        assert get("/../attention.db")[0] == 404
        assert get("/x", host="..localhost")[0] == 404
        status, _, frame = get("/__phone/")
        assert status == 200 and 'src="/"' in frame and "402px" in frame
        assert 'src="/cebu/"' in get("/__phone/cebu/")[2]
    finally:
        server.shutdown()


def test_preview_compiles_jsx_and_tsx_like_the_phone(tmp_path, monkeypatch):
    """preview.py: .jsx, .tsx and .ts come back as JavaScript, compiled by the same lib/compile.js the app runs; a
    file that doesn't compile comes back as a module that throws, naming the line; no node says so."""
    import importlib.util, shutil, threading, urllib.request
    root = Path(__file__).resolve().parents[1]
    lib = next((d for d in (root / "lib", root.parents[1] / "Talaria" / "Canvas" / "lib") if (d / "compile.js").is_file()), None)
    if lib is None or not shutil.which("node"):
        pytest.skip("needs node and lib/compile.js")
    spec = importlib.util.spec_from_file_location("talaria_preview_jsx", root / "preview.py")
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    app = tmp_path / "apps" / "trips"
    app.mkdir(parents=True)
    (app / "index.html").write_text("<html><head></head><body></body></html>")
    (app / "App.tsx").write_text("type P = { n: number }\nexport default function App({ n }: P) { return <p>{n}</p> }\n")
    (app / "main.jsx").write_text("export default function A() { return <div>\n  <b>\n</div> }\nexport const x = 1\n")
    (app / "util.ts").write_text("export const twice = (x: number): number => x * 2\n")
    monkeypatch.setattr(preview, "apps_root", lambda: tmp_path / "apps")
    monkeypatch.setattr(preview, "LIB", lib)
    server = preview.http.server.ThreadingHTTPServer(("127.0.0.1", 0), preview.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def get(path):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"Host": f"trips.localhost:{port}"})
        with urllib.request.urlopen(req) as r:
            return r.headers["Content-Type"], r.read().decode()

    try:
        kind, body = get("/App.tsx")
        assert kind == "text/javascript" and 'from "react/jsx-runtime"' in body and ": P" not in body
        assert get("/util.ts") == ("text/javascript", "export const twice = (x) => x * 2\n")
        broken = get("/main.jsx")[1]  # throws, but still links for a page that imports its exports
        assert broken.startswith('throw new SyntaxError("/main.jsx:3:')
        assert "export default undefined" in broken and "export const x = undefined" in broken
        (app / "main.jsx").write_text("export default <i>fixed</i>\n")  # an edit is compiled again
        assert "fixed" in get("/main.jsx")[1] and "throw" not in get("/main.jsx")[1]
        preview._compiler.kill()
        preview._compiler = None
        monkeypatch.setattr(preview.shutil, "which", lambda _: None)
        (app / "util.ts").write_text("export const one = 1\n")
        assert "need Node.js" in get("/util.ts")[1]
    finally:
        server.shutdown()
        if preview._compiler:
            preview._compiler.kill()


def test_preview_replaces_a_server_from_an_older_copy(monkeypatch):
    """preview.py: a server that answers with another stamp (started before a plugin update) is stopped, so the
    new code serves; one with the same stamp is left alone."""
    import importlib.util, socket, textwrap
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("talaria_preview_stale", root / "preview.py")
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(preview, "PORT", port)

    def fake(stamp):
        code = textwrap.dedent(f"""
            import http.server, os
            class H(http.server.BaseHTTPRequestHandler):
                def log_message(self, *a): pass
                def do_GET(self):
                    body = f"talaria-preview {stamp} {{os.getpid()}}".encode()
                    self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
                    self.wfile.write(body)
            http.server.HTTPServer(("127.0.0.1", {port}), H).serve_forever()""")
        proc = subprocess.Popen([sys.executable, "-c", code])
        for _ in range(50):
            if preview.ping():
                return proc
            time.sleep(0.1)
        proc.kill()
        raise AssertionError("fake server didn't start")

    current = fake(preview.STAMP)
    try:
        preview.stop_stale()
        assert preview.running() and current.poll() is None
    finally:
        current.kill()
        current.wait()
    old = fake("0ld")
    try:
        assert not preview.running()
        preview.stop_stale()
        assert old.wait(timeout=5) is not None and preview.ping() == ""
    finally:
        old.kill()


def load_build(tmp_path, monkeypatch):
    import importlib.util
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    spec = importlib.util.spec_from_file_location("talaria_build", Path(__file__).resolve().parents[1] / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    monkeypatch.setattr(build, "talaria_home", lambda: tmp_path / "talaria")
    return build


def test_seed_keeps_the_workspace_and_refreshes_talaria(tmp_path, monkeypatch):
    """build.py: package.json, tsconfig.json and shared/ are Hermes' once seeded; talaria/ is the plugin's."""
    build = load_build(tmp_path, monkeypatch)
    ws = build.workspace()
    build.seed(ws)
    assert (ws / "talaria" / "vite.config.mjs").is_file() and (ws / "talaria" / "viz" / "entry.ts").is_file()
    assert (ws / "shared" / "Screen.tsx").is_file() and (ws / "apps").is_dir()
    (ws / "package.json").write_text('{"dependencies": {"react": "18.0.0"}}')
    (ws / "shared" / "Screen.tsx").write_text("mine")
    (ws / "talaria" / "stale.js").write_text("gone after the next seed")
    build.seed(ws)
    assert json.loads((ws / "package.json").read_text()) == {"dependencies": {"react": "18.0.0"}}
    assert (ws / "shared" / "Screen.tsx").read_text() == "mine"
    assert not (ws / "talaria" / "stale.js").exists()

    assert build.add_packages(ws)  # the missing ones, at their pins; react stays where Hermes put it
    deps = json.loads((ws / "package.json").read_text())["dependencies"]
    assert deps["react"] == "18.0.0" and deps["vite"] == build.PACKAGES["vite"] and set(build.PACKAGES) <= set(deps)
    assert not build.add_packages(ws)


def test_swap_replaces_the_last_build_and_keeps_data(tmp_path, monkeypatch):
    build = load_build(tmp_path, monkeypatch)
    dest, staged = tmp_path / "apps" / "trips", tmp_path / "out"

    def stage(files):
        import shutil
        shutil.rmtree(staged, ignore_errors=True)
        for rel in files:
            (staged / rel).parent.mkdir(parents=True, exist_ok=True)
            (staged / rel).write_text(rel)

    dest.mkdir(parents=True)
    (dest / "data.json").write_text("live")
    stage(["index.html", "assets/a1.js", "cebu/index.html"])
    build.swap(staged, dest)
    stage(["index.html", "assets/a2.js"])
    build.swap(staged, dest)
    assert build.files_in(dest) == {"index.html", "assets/a2.js", "data.json", ".build.json"}
    assert (dest / "data.json").read_text() == "live" and not (dest / "cebu").exists()
    assert json.loads((dest / ".build.json").read_text())["files"] == ["assets/a2.js", "index.html"]


def test_a_failed_build_changes_nothing(tmp_path, monkeypatch):
    build = load_build(tmp_path, monkeypatch)
    ws = build.workspace()
    build.seed(ws)
    (ws / "apps" / "trips").mkdir()
    (ws / "apps" / "trips" / "index.html").write_text("<title>Trips</title>")
    dest = build.built("trips")
    dest.mkdir(parents=True)
    (dest / "index.html").write_text("the last good build")

    def fail(*a, **k):
        raise build.BuildError("Building trips failed:\nApp.tsx:1:32 Expected `}`")
    monkeypatch.setattr(build, "run", fail)
    with pytest.raises(build.BuildError, match="App.tsx:1:32"):
        build.build_one("trips", ws, {})
    assert (dest / "index.html").read_text() == "the last good build"
    with pytest.raises(build.BuildError, match="--new nope"):
        build.build_one("nope", ws, {})


@pytest.mark.skipif(not os.environ.get("TALARIA_TEST_BUILD"), reason="set TALARIA_TEST_BUILD=1 (npm installs, ~30 s)")
def test_builds_a_new_app_end_to_end(tmp_path, monkeypatch):
    """The template app through a real npm install and vite build: pages, Tailwind classes from shared/, and data
    that survives a rebuild."""
    build = load_build(tmp_path, monkeypatch)
    assert build.main(["--new", "demo", "rocket"]) == 0
    assert "glyph: 'rocket'" in (build.workspace() / "apps" / "demo" / "App.tsx").read_text()
    dest = build.built("demo")
    html = (dest / "index.html").read_text()
    assert "<title>Demo</title>" in html and 'src="/assets/' in html
    css = "".join(p.read_text() for p in (dest / "assets").glob("*.css"))
    assert "max-w-xl" in css  # a class only shared/Screen.tsx uses
    (dest / "data.json").write_text("[]")
    assert build.main(["demo"]) == 0
    assert (dest / "data.json").read_text() == "[]"


def test_a_new_app_starts_with_its_icon(tmp_path, monkeypatch, capsys):
    """--new needs an icon from the kit, and writes it into the app's meta."""
    build = load_build(tmp_path, monkeypatch)
    monkeypatch.setattr(build, "node_env", lambda: {})
    monkeypatch.setattr(build, "install", lambda ws, env: None)
    monkeypatch.setattr(build, "build_one", lambda name, ws, env: build.built(name))
    assert build.main(["--new", "trips"]) == 1
    assert "Pick its icon" in capsys.readouterr().err
    assert build.main(["--new", "trips", "wallet"]) == 1  # not in the kit
    assert not (build.workspace() / "apps" / "trips").exists()
    assert build.main(["--new", "trips", "globe"]) == 0
    assert "export const meta = { title: 'Trips', glyph: 'globe' }" in (build.workspace() / "apps" / "trips" / "App.tsx").read_text()


def test_migrate_an_older_app(tmp_path, monkeypatch):
    """migrate: the live app stays until the first build, which retires its old code and keeps everything else."""
    build = load_build(tmp_path, monkeypatch)
    monkeypatch.setattr(build, "node_env", lambda: {})
    monkeypatch.setattr(build, "install", lambda ws, env: None)
    old = build.built("spending")
    (old / "images").mkdir(parents=True)
    for rel, text in (("index.html", "<title> Spending\n</title>"), ("app.js", "old"), ("style.css", "old"),
                      ("data.json", "live"), ("refresh.py", "routine"), ("images/a.jpg", "img")):
        (old / rel).write_text(text)
    assert build.main(["--new", "spending", "dashboard"]) == 1  # would replace the live app
    assert build.main(["migrate", "spending"]) == 0
    ws = build.workspace()
    assert "title: 'Spending'" in (ws / "apps" / "spending" / "App.tsx").read_text()
    assert (ws / "legacy" / "spending" / "app.js").read_text() == "old"
    assert (old / "app.js").read_text() == "old"  # still live
    assert build.main(["migrate", "spending"]) == 1

    def vite(cmd, ws_, env, what):
        out = Path(env["TALARIA_OUT"])
        (out / "assets").mkdir(parents=True)
        (out / "index.html").write_text("new")
        (out / "assets" / "index-1.js").write_text("new")
    monkeypatch.setattr(build, "run", vite)
    build.build_one("spending", ws, {})
    assert build.files_in(old) == {"index.html", "assets/index-1.js", "data.json", "refresh.py", "images/a.jpg",
                                   ".build.json"}
    assert (old / "index.html").read_text() == "new" and (old / "data.json").read_text() == "live"


def make_action(app: Path, name: str, code: str) -> None:
    (app / "actions").mkdir(parents=True, exist_ok=True)
    (app / "actions" / f"{name}.py").write_text(code)


ECHO = "import json, os, sys\nreq = json.load(sys.stdin)\nprint(json.dumps({'got': req, 'app': os.environ['TALARIA_APP'], 'cwd': os.getcwd()}))\n"


def test_actions_run_only_declared_scripts(talaria, tmp_path):
    """actions.run: a declared script gets the request on stdin and answers JSON; nothing else runs."""
    import base64
    from talaria_plugin import actions
    apps = tmp_path / "talaria" / "apps"
    make_action(apps / "news", "echo", ECHO)
    make_action(apps / "news", "broken", "import sys\nprint('half', end='')\nsys.exit('it broke')\n")
    make_action(apps / "news", "chatty", "print('not json')\n")
    out = json.loads(actions.run(apps, "news", "echo", b'{"op": "list"}'))
    assert out["ok"] and out["result"]["got"] == {"op": "list"} and out["result"]["app"] == "news"
    assert Path(out["result"]["cwd"]).resolve() == (apps / "news").resolve()
    for app, name, err in (("news", "missing", "no action"), ("news", "../news/actions/echo", "Not an app"),
                           ("../x", "echo", "Not an app"), ("news", "broken", "it broke"), ("news", "chatty", "JSON")):
        res = json.loads(actions.run(apps, app, name, b"{}"))
        assert not res["ok"] and err in res["error"], (name, res)
    assert "over" in json.loads(actions.run(apps, "news", "echo", b"1" * (actions.MAX_REQUEST + 1)))["error"]
    # the same through /talaria action, as the phone sends it
    b64 = base64.b64encode(b'{"op": "list"}').decode()
    assert json.loads(talaria.handle_command(f"action news echo {b64}"))["result"]["got"] == {"op": "list"}
    assert not json.loads(talaria.handle_command("action news echo not-base64!"))["ok"]


def test_preview_runs_actions_only_from_the_apps_page(tmp_path, monkeypatch):
    """POST /__action/<name> needs the SDK's header and a local Origin, so another site's page can't trigger it."""
    import importlib.util, threading, urllib.request, urllib.error
    spec = importlib.util.spec_from_file_location("talaria_preview_actions", Path(__file__).resolve().parents[1] / "preview.py")
    preview = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preview)
    apps = tmp_path / "apps"
    make_action(apps / "news", "echo", ECHO)
    (apps / "news" / "index.html").write_text("<title>News</title>")
    monkeypatch.setattr(preview, "apps_root", lambda: apps)
    server = preview.http.server.ThreadingHTTPServer(("127.0.0.1", 0), preview.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def post(headers):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/__action/echo", data=b'{"n": 1}', method="POST",
                                     headers={"Host": "news.localhost", **headers})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    try:
        code, body = post({"X-Talaria-Action": "1", "Origin": f"http://news.localhost:{port}"})
        assert code == 200 and body["result"]["got"] == {"n": 1}
        assert post({"Origin": f"http://news.localhost:{port}"})[0] == 403          # no SDK header
        assert post({"X-Talaria-Action": "1", "Origin": "https://evil.example"})[0] == 403
        # and on Desktop's per-app port
        port2 = preview.serve_app("news")
        req = urllib.request.Request(f"http://127.0.0.1:{port2}/__action/echo", data=b"{}", method="POST",
                                     headers={"X-Talaria-Action": "1", "Origin": f"http://localhost:{port2}"})
        with urllib.request.urlopen(req) as r:
            assert json.loads(r.read())["ok"]
    finally:
        server.shutdown()


def test_seed_teaches_an_older_workspace_new_aliases(tmp_path, monkeypatch):
    build = load_build(tmp_path, monkeypatch)
    ws = build.workspace()
    ws.mkdir(parents=True)
    (ws / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"paths": {"viz": ["./talaria/viz/entry.ts"], "mine": ["./x"]}}, "include": ["apps"]}))
    build.seed(ws)
    cfg = json.loads((ws / "tsconfig.json").read_text())
    assert cfg["compilerOptions"]["paths"]["talaria"] == ["./talaria/sdk.ts"] and cfg["compilerOptions"]["paths"]["mine"] == ["./x"]
    assert "talaria/sdk.ts" in cfg["include"] and (ws / "talaria" / "sdk.ts").is_file()


STARTER = Path(__file__).resolve().parents[1] / "starters" / "news"


def test_newsroom_starter_has_nothing_personal():
    """Every install gets this: no one's name, home, company or timezone in it."""
    import re
    hits = [f"{p.relative_to(STARTER)}: {m.group(0)}" for p in STARTER.rglob("*") if p.is_file() and p.suffix in (".py", ".ts", ".tsx", ".md", ".json", ".html", ".css")
            for m in re.finditer(r"Jesse|Mara\b|Sageware|Erudifi|Manila|/root", p.read_text())]
    assert not hits, hits


def newsroom_app(tmp_path) -> Path:
    """The starter's app folder, with its database migrated, as the plugin leaves it after a build."""
    import importlib.util, shutil
    app = tmp_path / "talaria" / "apps" / "news"
    shutil.copytree(STARTER / "app", app)
    spec = importlib.util.spec_from_file_location("talaria_db_newsroom", STARTER.parents[1] / "db.py")
    db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(db)
    db.connect(app.parent, "news").close()
    return app


def act(app: Path, name: str, req) -> tuple[int, object]:
    p = subprocess.run([sys.executable, str(app / "actions" / f"{name}.py")], input=json.dumps(req), capture_output=True, text=True,
                       cwd=app, env={**os.environ, "TALARIA_HOME": str(app.parents[1])}, timeout=120)
    return p.returncode, (json.loads(p.stdout) if p.returncode == 0 else (p.stderr.strip().splitlines() or [""])[-1])


def test_newsroom_settings_sources_and_feedback(tmp_path):
    app = newsroom_app(tmp_path)
    assert act(app, "settings", {"op": "get"})[1]["configured"] is False
    assert act(app, "settings", {"op": "save", "topics": []})[0] != 0
    assert act(app, "settings", {"op": "save", "topics": ["Cybersecurity"], "timezone": "Mars/Base"})[0] != 0
    code, out = act(app, "settings", {"op": "save", "topics": ["Cybersecurity", "Nope"], "interests": "  web   security ", "timezone": "Asia/Tokyo"})
    assert code == 0 and out["configured"] and out["settings"]["topics"] == ["Cybersecurity"] and out["settings"]["interests"] == "web security"
    sugg = act(app, "sources", {"op": "suggest", "topics": ["Cybersecurity"]})[1]["suggestions"]
    assert sugg and all(s["topic"] == "Cybersecurity" and s["url"].startswith("https://") for s in sugg)
    code, out = act(app, "sources", {"op": "add", "url": sugg[0]["url"], "title": sugg[0]["title"], "topic": "Cybersecurity"})
    assert code == 0 and [f["url"] for f in out["feeds"]] == [sugg[0]["url"]]
    assert sugg[0]["url"] not in [s["url"] for s in act(app, "sources", {"op": "suggest", "topics": ["Cybersecurity"]})[1]["suggestions"]]
    for bad in ("https://127.0.0.1/feed", "http://example.com/feed", "https://10.0.0.1/rss"):
        assert act(app, "sources", {"op": "add", "url": bad})[0] != 0, bad
        if "127.0.0.1" in bad or "10.0.0.1" in bad:  # discover upgrades a typed http:// to https://, so only these must fail
            assert act(app, "sources", {"op": "discover", "url": bad})[0] != 0, bad
    assert act(app, "sources", {"op": "remove", "url": sugg[0]["url"]})[1]["feeds"] == []
    code, out = act(app, "feedback", {"votes": [{"id": "a" * 16, "title": "T", "value": 1, "at": "2026-10-24T00:00:00Z", "junk": 1}, {"id": "b", "value": 5}]})
    assert code == 0 and out["saved"] == 1
    assert json.loads((app / "reader-feedback.json").read_text())["votes"] == [{"id": "a" * 16, "title": "T", "value": 1, "at": "2026-10-24T00:00:00Z"}]
    # A 👎 says why: a known reason and the reader's note are kept; anything else isn't.
    at = "2026-10-24T00:00:00Z"
    act(app, "feedback", {"votes": [{"id": "c", "value": -1, "at": at, "reason": "source", "note": "  Press release.  "},
                                    {"id": "d", "value": -1, "at": at, "reason": "whatever", "note": "   "}]})
    assert json.loads((app / "reader-feedback.json").read_text())["votes"] == [
        {"id": "c", "value": -1, "at": at, "reason": "source", "note": "Press release."}, {"id": "d", "value": -1, "at": at}]
    # Two devices (the phone, Desktop): one's sync never wipes the other's votes; the latest vote on a story wins.
    later = "2026-10-25T00:00:00Z"
    act(app, "feedback", {"device": "phone-0001", "votes": [{"id": "p", "value": 1, "at": at}, {"id": "q", "value": 1, "at": at}]})
    act(app, "feedback", {"device": "desktop-0001", "votes": [{"id": "q", "value": -1, "at": later, "reason": "seen"}]})
    merged = {v["id"]: v for v in json.loads((app / "reader-feedback.json").read_text())["votes"]}
    assert merged["p"]["value"] == 1 and merged["q"] == {"id": "q", "value": -1, "at": later, "reason": "seen"}
    assert {"c", "d"} <= set(merged)  # the earlier, device-less sync is kept too
    # A vote taken back on another device (0, later) wins and leaves the editor's votes; the page still gets it.
    act(app, "feedback", {"device": "desktop-0001", "votes": [{"id": "p", "value": 0, "at": later}]})
    data = json.loads((app / "reader-feedback.json").read_text())
    assert "p" not in {v["id"] for v in data["votes"]} and {"id": "p", "value": 0, "at": later} in data["devices"]["desktop-0001"]["votes"]
    # A device with no votes (a new Desktop origin) isn't recorded, so it never pushes out one that has them.
    for i in range(25):
        act(app, "feedback", {"device": f"empty-{i:04}", "votes": []})
    assert set(json.loads((app / "reader-feedback.json").read_text())["devices"]) == {"unknown", "phone-0001", "desktop-0001"}


def test_newsroom_read_marks_are_shared(tmp_path):
    """actions/read.py: a story opened on one device shows Read on the others, keeping when it was first read."""
    app = newsroom_app(tmp_path)
    assert act(app, "read", {"ids": ["a1", "../x", 5], "at": "2026-10-24T01:00:00Z"}) == (0, {"count": 1})
    assert act(app, "read", {"ids": ["a1", "b2"], "at": "2026-10-25T01:00:00Z"}) == (0, {"count": 2})
    assert json.loads((app / "read.json").read_text())["read"] == {"a1": "2026-10-24T01:00:00Z", "b2": "2026-10-25T01:00:00Z"}


def test_newsroom_read_later_is_shared_by_devices(tmp_path):
    """actions/saved.py: one reading list for the phone and Desktop. A save lands in read-later.json; a removal
    sticks, so a device that saved it earlier doesn't bring it back, unless it saved it again after."""
    import subprocess
    app = newsroom_app(tmp_path)

    def act(req):
        p = subprocess.run([sys.executable, str(app / "actions" / "saved.py")], input=json.dumps(req).encode(),
                           capture_output=True)
        return p.returncode, json.loads(p.stdout or b"null")
    story = {"id": "a1", "title": "T", "url": "https://example.com/t", "publisher": "P", "why": "W", "junk": "x"}
    assert act({"op": "add", "article": story, "at": "2026-10-24T01:00:00Z"}) == (0, {"count": 1})
    data = json.loads((app / "read-later.json").read_text())
    assert data["items"]["a1"] == {"article": {k: story[k] for k in ("id", "title", "url", "publisher", "why")},
                                   "savedAt": "2026-10-24T01:00:00Z"}
    act({"op": "remove", "id": "a1", "at": "2026-10-24T02:00:00Z"})
    old = {"article": story, "savedAt": "2026-10-24T00:30:00Z"}
    assert act({"op": "merge", "items": [old]})[1] == {"count": 0}  # removed after this copy was saved
    assert act({"op": "merge", "items": [{**old, "savedAt": "2026-10-24T03:00:00Z"}]})[1] == {"count": 1}
    assert act({"op": "add", "article": {"id": "../x", "url": "https://e.com"}})[1] == {"count": 1}  # not a story
    assert act({"op": "add", "article": {"id": "b", "url": "javascript:alert(1)"}})[1] == {"count": 1}
    assert act({"op": "nope"})[0] != 0


def test_newsroom_keeps_reader_state_in_its_database(tmp_path):
    """reader.py: the files the app kept before are adopted once; saves from two devices at once both land; the files
    the page and the editor read are rewritten from the database."""
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor
    app = newsroom_app(tmp_path)
    (app / "read-later.json").write_text(json.dumps({"items": {"old": {"article": {"id": "old", "url": "https://e.com/o"},
                                                                         "savedAt": "2026-10-20T00:00:00Z"}},
                                                     "removed": {"gone": "2026-10-21T00:00:00Z"}}))
    (app / "reader-feedback.json").write_text(json.dumps({"votes": [{"id": "v", "value": 1, "at": "2026-10-20T00:00:00Z"}]}))

    def save(i):
        return act(app, "saved", {"op": "add", "article": {"id": f"s{i}", "url": f"https://e.com/{i}"}, "at": f"2026-10-24T00:00:{i:02d}Z"})
    with ThreadPoolExecutor(8) as pool:
        assert all(code == 0 for code, _ in pool.map(save, range(16)))
    items = json.loads((app / "read-later.json").read_text())["items"]
    assert set(items) == {"old"} | {f"s{i}" for i in range(16)}
    assert json.loads((app / "read-later.json").read_text())["removed"] == {"gone": "2026-10-21T00:00:00Z"}
    act(app, "feedback", {"device": "phone-0001", "votes": [{"id": "w", "value": -1, "at": "2026-10-24T00:00:00Z"}]})
    feedback = json.loads((app / "reader-feedback.json").read_text())
    assert [v["id"] for v in feedback["votes"]] == ["v", "w"] and set(feedback["devices"]) == {"earlier", "phone-0001"}
    db = sqlite3.connect(app / "app.db")
    assert db.execute("SELECT count(*) FROM saved").fetchone()[0] == 17
    assert db.execute("SELECT count(*) FROM latest_votes").fetchone()[0] == 2


def test_newsroom_routine_schedules_in_the_readers_morning(tmp_path):
    import datetime as dt
    from zoneinfo import ZoneInfo
    app = newsroom_app(tmp_path)
    (app / "newsroom.json").write_text(json.dumps({"timezone": "Asia/Tokyo", "topics": ["Fintech"], "feeds": []}))
    src = (app / "actions" / "routine.py").read_text().split("req = json.load")[0]
    ns = {"__name__": "check", "__file__": str(app / "actions" / "routine.py")}
    exec(compile(src, "routine", "exec"), ns)
    seven = dt.datetime.now(ZoneInfo("Asia/Tokyo")).replace(hour=7, minute=0, second=0, microsecond=0).astimezone().hour
    assert ns["schedule"]("daily") == f"0 {seven} * * *"
    assert ns["schedule"]("12h") == "0 " + ",".join(map(str, sorted({seven, (seven + 12) % 24}))) + " * * *"
    assert len(ns["schedule"]("6h").split()[1].split(",")) == 4
    assert act(app, "routine", {"op": "status"})[1] == {"installed": False}
    assert act(app, "routine", {"op": "install"})[0] != 0  # no sources yet: nothing is created
    assert act(app, "routine", {"op": "install", "frequency": "hourly"})[0] != 0


def test_newsroom_publishes_in_the_readers_timezone(tmp_path):
    """publish_edition: dates come from newsroom.json's timezone, and a missing reader venv doesn't fail it."""
    import datetime as dt
    app = newsroom_app(tmp_path)
    (app / "newsroom.json").write_text(json.dumps({"timezone": "Pacific/Auckland", "topics": ["Fintech"], "feeds": []}))
    arts = [{"id": f"{i:016x}", "title": f"Story {i}", "url": f"https://example.com/{i}", "publisher": "Ex", "topics": ["Fintech"],
             "publishedAt": "2026-10-24T00:00:00+00:00", "summary": ""} for i in range(3)]
    (app / "data.json").write_text(json.dumps({"updatedAt": "2026-10-24T11:00:00+00:00", "articles": arts}))
    stage = tmp_path / "stage.json"
    stage.write_text(json.dumps({"version": 1, "editedAt": "2026-10-24T11:30:00+00:00", "basisUpdatedAt": "2026-10-24T11:00:00+00:00",
                                 "summary": "Test.", "items": [{"id": a["id"], "priority": 50, "key": False, "tags": ["a", "b"],
                                 "why": "Because it matters to this reader.", "evidence": {"status": "feed-only", "url": a["url"], "note": "Feed only."}} for a in arts]}))
    p = subprocess.run([sys.executable, str(app / "publish_edition.py"), str(stage)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    index = json.loads((app / "editions.json").read_text())
    assert index["editions"][0]["date"] == "2026-10-25"  # 11:30 UTC is the next day in Auckland


def test_newsroom_editions_carry_only_whats_new(tmp_path):
    """publish_edition: a story that ran in the last 72 hours (by id, or the same URL from another feed) is left out
    unless it's marked an update with what changed; when nothing new is left, nothing is published."""
    import datetime as dt
    app = newsroom_app(tmp_path)
    (app / "newsroom.json").write_text(json.dumps({"timezone": "UTC", "topics": ["Fintech"], "feeds": []}))
    now = dt.datetime.now(dt.timezone.utc)
    stamp = lambda h: (now - dt.timedelta(hours=h)).isoformat()
    arts = [{"id": f"{i:016x}", "title": f"Story {i}", "url": f"https://example.com/{i}", "publisher": "Ex", "topics": ["Fintech"],
             "publishedAt": stamp(5), "summary": ""} for i in range(4)]
    arts.append({**arts[0], "id": f"{9:016x}", "url": "http://www.example.com/0/?utm=x", "publisher": "Other"})  # same story, other feed

    def publish(ids, edited, **extra):
        (app / "data.json").write_text(json.dumps({"updatedAt": edited, "articles": arts}))
        items = [{"id": i, "priority": 50, "key": False, "tags": ["a", "b"], "why": "Because it matters to this reader.",
                  "evidence": {"status": "feed-only", "url": "https://example.com/e", "note": "Feed only."}, **extra.get(i, {})} for i in ids]
        stage = tmp_path / "stage.json"
        stage.write_text(json.dumps({"version": 1, "editedAt": edited, "basisUpdatedAt": edited, "summary": "Test.", "items": items}))
        p = subprocess.run([sys.executable, str(app / "publish_edition.py"), str(stage)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout.strip().splitlines()[-1])
    a, b, c, d, again = [x["id"] for x in arts]
    assert publish([a, b], stamp(3))["selected"] == 2
    out = publish([again, b, c, d], stamp(2), **{b: {"update": True, "updateNote": "A patch shipped since this first ran."}})
    assert out["selected"] == 3 and out["repeatsLeftOut"] == 1  # the same story as a, from another feed
    latest = json.loads((app / "editorial.json").read_text())
    assert [i["id"] for i in latest["items"]] == [b, c, d] and latest["repeatsLeftOut"] == 1
    assert publish([c, d], stamp(1)) == {"published": False, "reason": "Every selected story already ran in the last 72 hours; nothing new to publish.", "repeatsLeftOut": 2}
    assert json.loads((app / "editorial.json").read_text())["editedAt"] == stamp(2)  # the last edition stays
    rec = json.loads((app / "editorial.json").read_text())
    assert len(json.loads((app / "editions.json").read_text())["editions"]) == 2 and rec["items"][0]["update"] is True


def test_newsroom_discovery_widens_taste_a_little(tmp_path):
    """Discovery feeds near the reader's topics (not ones they follow, none when turned off); an edition may carry up
    to three of their stories, one comic, never key, and never as the whole edition."""
    import datetime as dt
    app = newsroom_app(tmp_path)
    settings = {"timezone": "UTC", "topics": ["Cybersecurity"], "feeds": [{"url": "https://www.eff.org/rss/updates.xml"}]}
    (app / "newsroom.json").write_text(json.dumps(settings))
    sys.path.insert(0, str(app))
    try:
        import newsroom
        importlib.reload(newsroom)
        feeds = newsroom.discovery_feeds()
        assert {a for a, _, _ in feeds} == {"Privacy & Policy", "Comics"}  # what's near security, and comics
        assert "https://www.eff.org/rss/updates.xml" not in [u for _, _, u in feeds]  # theirs already
        assert newsroom.discovery_feeds({**newsroom.settings(), "discovery": False}) == []
        import refresh
        importlib.reload(refresh)
    finally:
        sys.path.remove(str(app))
    assert refresh.caption('<img src="https://imgs.xkcd.com/c.png" title="The light is bremsstrahlung." />') == "The light is bremsstrahlung."
    assert refresh.caption('<a><img src="x.png" /></a><p>Hovertext:<br/>Hope this ruins you.</p>') == "Hope this ruins you."

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    arts = [{"id": f"{i:016x}", "title": f"Story {i}", "url": f"https://example.com/{i}", "publisher": "Ex", "topics": ["Cybersecurity"],
             "publishedAt": now, "summary": ""} for i in range(2)]
    arts += [{**arts[0], "id": f"{i:016x}", "url": f"https://example.org/{i}", "topics": [area], "discovery": area}
             for i, area in [(10, "Privacy & Policy"), (11, "Privacy & Policy"), (12, "Comics"), (13, "Comics"), (14, "Privacy & Policy")]]
    (app / "data.json").write_text(json.dumps({"updatedAt": now, "articles": arts}))

    def publish(ids, key=(), topics={}):
        items = [{"id": i, "priority": 50, "key": i in key, "tags": ["a", "b"], "topics": topics.get(i, []), "why": "Because it matters to this reader.",
                  "evidence": {"status": "feed-only", "url": "https://example.com/e", "note": "Feed only."}} for i in ids]
        stage = tmp_path / "stage.json"
        stage.write_text(json.dumps({"version": 1, "editedAt": now, "basisUpdatedAt": now, "summary": "Test.", "items": items}))
        p = subprocess.run([sys.executable, str(app / "publish_edition.py"), str(stage)], capture_output=True, text=True, timeout=60)
        return p.returncode, (p.stdout.strip().splitlines() or [""])[-1] + p.stderr
    ids = [a["id"] for a in arts]
    assert "No more than 3 discovery picks" in publish(ids[:2] + [ids[2], ids[3], ids[4], ids[6]])[1]
    assert "No more than one comic" in publish(ids[:2] + [ids[4], ids[5]])[1]
    assert "never a key" in publish(ids[:2] + [ids[2]], key={ids[2]})[1]
    assert json.loads(publish([ids[2], ids[4]])[1])["reason"].startswith("Only discovery picks")  # not an edition alone
    code, out = publish(ids[:2] + [ids[2], ids[4]], topics={ids[4]: ["Comics"]})  # its area is its topic
    assert code == 0 and json.loads(out)["discovery"] == 2


def test_starters_install_once_and_leave_existing_apps(tmp_path, monkeypatch):
    build = load_build(tmp_path, monkeypatch)
    ws = build.workspace()
    build.seed(ws)
    calls = []
    monkeypatch.setattr(build, "install", lambda ws, env: None)
    monkeypatch.setattr(build, "build_one", lambda name, ws, env: calls.append(name))
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(build.subprocess.SubprocessError("no venv here")))
    assert build.install_starters(ws, {}) == {"news": "installed"}
    assert (ws / "apps" / "news" / "Setup.tsx").is_file() and (ws / "shared" / "newsroom" / "useNewsroom.ts").is_file()
    assert (build.built("news") / "actions" / "routine.py").is_file() and not (build.built("news") / "newsroom.json").exists()
    assert calls == ["news"]
    assert build.install_starters(ws, {}) == {"news": "installed"} and calls == ["news"]  # recorded: never again
    # a box that already has its own news app keeps it
    build.starters_record().unlink()
    (ws / "apps" / "news" / "App.tsx").write_text("mine")
    assert build.install_starters(ws, {})["news"].startswith("skipped")
    assert (ws / "apps" / "news" / "App.tsx").read_text() == "mine"


def test_marketplace_install_brings_back_a_deleted_starter_and_retries_a_failed_one(tmp_path, monkeypatch):
    """build.py --starter: the Apps marketplace's install. Unlike first run, it installs a starter recorded before
    (deleted since, or failed), picks up a failed try's own copy, and never replaces an app of the user's."""
    build = load_build(tmp_path, monkeypatch)
    ws = build.workspace()
    build.seed(ws)
    monkeypatch.setattr(build, "install", lambda ws, env: None)
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(build.subprocess.SubprocessError("no venv here")))

    def fail(name, ws, env):
        raise build.BuildError("vite: out of memory")
    monkeypatch.setattr(build, "build_one", fail)
    assert build.install_chosen("news", ws, {}) == "failed: vite: out of memory"
    assert build.starter_outcome("news").startswith("failed") and (ws / "apps" / "news").is_dir()

    def ok(name, ws, env):
        (build.built(name) / "index.html").write_text("<title>Newsroom</title>")
    monkeypatch.setattr(build, "build_one", ok)
    assert build.install_chosen("news", ws, {}) == "installed"  # its own leftover copy didn't stand in the way
    # deleted since: the marketplace brings it back, where first run would leave it gone
    shutil.rmtree(ws / "apps" / "news")
    shutil.rmtree(build.built("news"))
    assert build.install_starters(ws, {}) == {"news": "installed"} and not (ws / "apps" / "news").exists()
    assert build.install_chosen("news", ws, {}) == "installed" and (build.built("news") / "index.html").is_file()
    assert build.install_chosen("news", ws, {}) == "installed"  # one that waited on first run's: still installed
    # a failed try the user has since made their own is theirs: never replaced
    build.record("news", "failed: earlier")
    shutil.rmtree(build.built("news"))
    (ws / "apps" / "news" / "App.tsx").write_text("mine")
    assert build.install_chosen("news", ws, {}).startswith("skipped")
    assert (ws / "apps" / "news" / "App.tsx").read_text() == "mine"
    assert build.install_chosen("nope", ws, {}).startswith("failed: Talaria doesn't ship")


def test_catalog_lists_the_starters_with_their_state(talaria, tmp_path, monkeypatch):
    """/talaria catalog and install: what the iPhone's Marketplace tab shows, and its Install."""
    from talaria_plugin import market
    home = tmp_path / "talaria"
    started = []

    class Proc:
        pid = os.getpid()  # alive, as a running install would be
        def wait(self):
            return 0
    monkeypatch.setattr(market.subprocess, "Popen", lambda cmd, **k: started.append(cmd) or Proc())
    monkeypatch.setattr(market, "has_node", lambda: True)

    def news():
        out = json.loads(talaria.handle_command("catalog"))
        return next(a for a in out["apps"] if a["name"] == "news")
    row = news()
    assert row["state"] == "available" and row["title"] == "Newsroom" and row["glyph"] == "broadcast" and row["description"]
    assert json.loads(talaria.handle_command("install news")) == {"name": "news", "state": "installing"}
    assert started[0][-2:] == ["--starter", "news"] and news()["state"] == "installing"
    assert json.loads(talaria.handle_command("install news"))["state"] == "installing"  # not started twice
    assert len(started) == 1
    # an install that died without clearing its file doesn't show as running forever
    (home / "installing" / "news.json").write_text(json.dumps({"pid": 2 ** 22 + 12345, "started": time.time()}))
    (home / "starters.json").write_text(json.dumps({"news": "failed: npm install: network down"}))
    row = news()
    assert row["state"] == "failed" and row["error"] == "npm install: network down"
    assert not (home / "installing" / "news.json").exists()
    # installed by Talaria, or an app of the user's own with the name
    (home / "apps" / "news").mkdir(parents=True)
    (home / "apps" / "news" / "index.html").write_text("<title>Newsroom</title>")
    (home / "starters.json").write_text(json.dumps({"news": "installed"}))
    assert news()["state"] == "installed"
    (home / "starters.json").write_text(json.dumps({"news": "skipped: already there"}))
    assert news()["state"] == "taken" and "already have" in json.loads(talaria.handle_command("install news"))["error"]
    assert "doesn't ship" in json.loads(talaria.handle_command("install nope"))["error"]
    assert json.loads(talaria.handle_command("version"))["api"] == 2


def test_app_db_migrates_and_answers_the_page(talaria, tmp_path):
    """db.py: an app's migrations applied once, in order; the page's statements (the reserved action talaria-db, as
    the phone sends it) kept inside its own database; a failed batch changes nothing."""
    import base64
    from talaria_plugin import actions
    apps = tmp_path / "talaria" / "apps"
    (apps / "trips" / "migrations").mkdir(parents=True)
    (apps / "trips" / "migrations" / "001-trips.sql").write_text(
        "CREATE TABLE trips (id INTEGER PRIMARY KEY, name TEXT NOT NULL, meta TEXT);\n"
        "CREATE TRIGGER named AFTER INSERT ON trips BEGIN UPDATE trips SET meta = coalesce(meta, '{}') WHERE id = new.id; END;\n")

    def db(req):
        b64 = base64.b64encode(json.dumps(req).encode()).decode()
        return json.loads(talaria.handle_command(f"action trips talaria-db {b64}"))

    assert db({"sql": "INSERT INTO trips (name, meta) VALUES (?, ?)", "params": ["Kyoto", {"days": 5}]})["result"] == \
        {"rows": [], "changes": 1, "lastId": 1}
    db({"sql": "INSERT INTO trips (name) VALUES (:name)", "params": {"name": "Cebu"}})
    rows = db({"sql": "SELECT name, meta FROM trips ORDER BY id"})["result"]["rows"]
    assert rows == [{"name": "Kyoto", "meta": '{"days": 5}'}, {"name": "Cebu", "meta": "{}"}]
    failed = db({"batch": [{"sql": "INSERT INTO trips (name) VALUES ('Bohol')"}, {"sql": "INSERT INTO nope VALUES (1)"}]})
    assert not failed["ok"] and "nope" in failed["error"]
    assert db({"sql": "SELECT count(*) AS n FROM trips"})["result"]["rows"] == [{"n": 2}]
    assert db({"sql": "PRAGMA table_info(trips)"})["ok"]
    for sql in (f"ATTACH '{tmp_path / 'x.db'}' AS x", f"VACUUM INTO '{tmp_path / 'y.db'}'", "PRAGMA user_version = 0",
                "PRAGMA journal_mode = DELETE", "SELECT 1; SELECT 2"):
        assert not db({"sql": sql})["ok"], sql
    assert not (tmp_path / "x.db").exists() and not (tmp_path / "y.db").exists()

    # a new migration applies once, before an action runs, which finds the database in TALARIA_DB
    (apps / "trips" / "migrations" / "002-done.sql").write_text("ALTER TABLE trips ADD COLUMN done INTEGER DEFAULT 0;\n")
    make_action(apps / "trips", "count", "import json, os, sqlite3\n"
                "print(json.dumps(sqlite3.connect(os.environ['TALARIA_DB']).execute('SELECT count(*) FROM trips WHERE done = 0').fetchone()[0]))\n")
    assert json.loads(actions.run(apps, "trips", "count", b"null")) == {"ok": True, "result": 2}
    assert db({"sql": "PRAGMA user_version"})["result"]["rows"] == [{"user_version": 2}]

    # a gap in the numbering is refused, and nothing else is applied
    (apps / "trips" / "migrations" / "004-gap.sql").write_text("CREATE TABLE gap (x);\n")
    assert "numbered" in db({"sql": "SELECT 1"})["error"]
    assert not db({"sql": "SELECT 1", "params": 5})["ok"] and not db({"batch": "no"})["ok"]
    assert "No app" in json.loads(actions.run(apps, "nope", "talaria-db", b'{"sql": "SELECT 1"}'))["error"]


def test_a_failed_migration_applies_none_of_itself(talaria, tmp_path):
    from talaria_plugin import actions
    apps = tmp_path / "talaria" / "apps"
    (apps / "log" / "migrations").mkdir(parents=True)
    (apps / "log" / "migrations" / "001-log.sql").write_text("CREATE TABLE log (x);\nCREATE TABLE log (x);\n")
    out = json.loads(actions.run(apps, "log", "talaria-db", b'{"sql": "SELECT name FROM sqlite_master"}'))
    assert not out["ok"] and "001-log.sql" in out["error"]
    (apps / "log" / "migrations" / "001-log.sql").write_text("CREATE TABLE log (x);\n")
    out = json.loads(actions.run(apps, "log", "talaria-db", b'{"sql": "SELECT name FROM sqlite_master"}'))
    assert out["result"]["rows"] == [{"name": "log"}]


def test_db_check_says_how_to_add_a_missing_sqlite(talaria, monkeypatch):
    """db.py --check: what each runtime has, and steps an agent can follow on any platform when one lacks SQLite."""
    from talaria_plugin import actions
    db = actions.db_module()
    report = json.loads(talaria.handle_command("db-check"))
    assert report["python"]["ok"] and report["python"]["sqlite"] and report["system"]["os"]
    monkeypatch.setattr(db, "sqlite3", None)
    report = db.check()
    assert not report["ok"] and not report["python"]["ok"]
    step = next(f for f in report["fix"] if f["for"] == "python")
    assert any("pysqlite3-binary" in t for t in step["try"])
    assert "no SQLite" in json.loads(db.query(Path("/nonexistent"), "x", b'{"sql": "SELECT 1"}'))["error"]
    monkeypatch.setattr("shutil.which", lambda name, *a, **k: None)
    monkeypatch.setattr(Path, "home", lambda: Path("/nonexistent"))
    node = next(f for f in db.check()["fix"] if f["for"] == "node")
    assert any("22.13" in t for t in node["try"])


def test_a_shared_app_page_rides_along_in_desktop_turns_only(talaria, monkeypatch):
    """pre_llm_call adds the shared page to a Desktop turn (title, page, the text in view); nothing on other
    platforms, when nothing is shared, or when the page doesn't answer."""
    from talaria_plugin import appserver
    assert talaria.pre_llm_call(session_id="d1", turn_id="t1", platform="desktop") is None  # no apps server
    asked = []
    shot = {"app": "news", "title": "Newsroom", "page": "story/42", "visible": "Bbtree: Fastest Ordered Map",
            "text": "everything", "scroll": 30}
    monkeypatch.setattr(appserver, "snapshot", lambda app=None, wait=8: asked.append(wait) or shot)
    context = talaria.pre_llm_call(session_id="d1", turn_id="t2", platform="desktop")["context"]
    assert '"news"' in context and "Newsroom · story/42" in context and "Bbtree: Fastest Ordered Map" in context
    assert "everything" not in context and "30% down" in context and asked == [2]
    assert talaria.pre_llm_call(session_id="t1", turn_id="t1", platform="telegram") is None
    assert inbox(talaria)[0]["state"] == "running"  # the turn is still recorded
    monkeypatch.setattr(appserver, "snapshot", lambda app=None, wait=8: {"error": "The page didn’t answer."})
    assert talaria.pre_llm_call(session_id="d1", turn_id="t3", platform="desktop") is None


def test_a_page_the_phone_hands_over_goes_with_that_sessions_next_turn(talaria, monkeypatch):
    """/talaria page keeps what the phone's page shows for one session; its next turn carries it (ahead of a page
    shared from Desktop), once; another session's turn doesn't; a stale or malformed one is dropped."""
    import base64
    from talaria_plugin import appserver
    monkeypatch.setattr(appserver, "snapshot", lambda app=None, wait=8: {"app": "kanban", "visible": "Desktop's board"})
    shot = {"app": "news", "title": "Newsroom", "page": "", "visible": "Woman, 65, becomes second patient"}
    b64 = base64.b64encode(json.dumps(shot).encode()).decode()
    assert json.loads(talaria.handle_command(f"page 20261025_1 {b64}")) == {"ok": True}
    assert "Desktop's board" in talaria.pre_llm_call(session_id="other", turn_id="t", platform="desktop")["context"]
    context = talaria.pre_llm_call(session_id="20261025_1", turn_id="t1", platform="desktop")["context"]
    assert '"news"' in context and "second patient" in context and "Desktop's board" not in context
    assert "talaria:app" not in context  # no such app on this box: nothing to point at
    (talaria.store.home() / "talaria" / "workspace" / "apps" / "news").mkdir(parents=True)
    talaria.keep_page("20261025_1", {**shot, "from": "phone", "scroll": 10})
    context = talaria.pre_llm_call(session_id="20261025_1", turn_id="t1", platform="desktop")["context"]
    assert "workspace/apps/news" in context and "talaria:app skill" in context and "app_snapshot" not in context
    assert "Desktop's board" in talaria.pre_llm_call(session_id="20261025_1", turn_id="t2", platform="desktop")["context"]
    talaria.keep_page("20261025_1", {**shot})
    talaria._page_file("20261025_1").write_text(json.dumps({**shot, "at": 0}))  # handed over long ago
    assert talaria.take_page("20261025_1") is None
    assert json.loads(talaria.handle_command("page ../x " + b64)) == {"ok": False}
    assert json.loads(talaria.handle_command("page s1 not-base64!"))["ok"] is False


def test_voice_chat_asks_for_a_spoken_answer(talaria):
    # Nothing extra until the phone says it's in voice chat on this session; then every turn until it's off.
    assert talaria.pre_llm_call(session_id="v1", turn_id="t1", platform="tui") is None
    assert json.loads(talaria.handle_command("voice v1 on"))["ok"] is True
    context = talaria.pre_llm_call(session_id="v1", turn_id="t2", platform="tui")["context"]
    assert "Speak first" in context and "word for word" in context
    assert talaria.pre_llm_call(session_id="other", turn_id="t1", platform="tui") is None
    talaria.handle_command("voice v1 off")
    assert talaria.pre_llm_call(session_id="v1", turn_id="t3", platform="tui") is None
    assert json.loads(talaria.handle_command("voice ../x on"))["ok"] is False
