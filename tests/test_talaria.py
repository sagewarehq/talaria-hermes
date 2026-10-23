"""Run on the box with Hermes's interpreter (needs hermes_cli for pid liveness):
    HERMES_HOME=$(mktemp -d) /usr/local/lib/hermes-agent/venv/bin/python -m pytest -q tests/
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


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
        def __init__(self): self.skills, self.hooks, self.commands = {}, [], []
        def register_hook(self, name, fn): self.hooks.append(name)
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


def test_moves_canvases_to_apps(talaria):
    root = talaria.store.home() / "talaria"
    (root / "canvases" / "trips").mkdir(parents=True)
    (root / "canvases" / "trips" / "index.html").write_text("<title>Trips</title>")
    talaria.move_canvases()
    assert (root / "apps" / "trips" / "index.html").read_text() == "<title>Trips</title>"
    assert not (root / "canvases").exists()
    talaria.move_canvases()  # once: nothing left to move
    assert (root / "apps" / "trips").is_dir()
