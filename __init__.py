"""talaria: server-side companion for the Talaria iPhone app.

Every Hermes backend (Desktop's, Talaria's, the cron scheduler, the messaging gateway) loads this
plugin, so its hooks see turns, approvals and questions in all of them and record each session's
state in one shared store (``store.py``). The app reads it with ``/talaria inbox --json`` over
``slash.exec``, which works in SSH and gateway mode alike.

Hooks sit on safety paths (approvals, human prompts): each one is wrapped, returns fast, and never
raises.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shlex
import threading
from typing import Any

from . import store

logger = logging.getLogger(__name__)

VERSION = "0.7.0"


def _safe(fn):
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            fn(*args, **kwargs)
        except Exception:  # observability must never break a turn, an approval, or a prompt
            logger.debug("talaria hook %s failed", fn.__name__, exc_info=True)
        return None
    wrapper.__name__ = fn.__name__
    return wrapper


@_safe
def on_session_start(session_id: str = "", platform: str = "", **_: Any) -> None:
    store.set_state(session_id, "running", platform=platform, new_turn=True)


@_safe
def _turn_starts(session_id: str, turn_id: str, platform: str) -> None:
    # on_session_start only fires on a session's first turn, so without this a reply to a "needs you"
    # turn left that row up and its end went unclassified.
    store.set_state(session_id, "running", turn_id=turn_id or None, platform=platform, new_turn=True)


def pre_llm_call(session_id: str = "", turn_id: str = "", platform: str = "", **_: Any) -> dict | None:
    """Once per turn, before the model runs. In a Desktop chat while you share an app page with Hermes (the eye
    beside an app, or Chat about this page), what it shows rides along with your message: Hermes then answers
    about the page without having to think of app_snapshot. Nothing otherwise, and never on other platforms."""
    _turn_starts(session_id, turn_id, platform)
    if platform != "desktop":
        return None
    try:
        context = shared_page_context()
    except Exception:
        logger.debug("talaria: reading the shared page failed", exc_info=True)
        return None
    return {"context": context} if context else None


PAGE_CONTEXT_TEXT = 6_000


def shared_page_context() -> str | None:
    """The shared app page as a note for the turn: which app and page, and the text in view. Quick: a page that
    doesn't answer in a couple of seconds is left out rather than holding up the reply."""
    from . import appserver
    shot = appserver.snapshot(wait=2)
    if not shot or shot.get("error"):
        return None
    where = " · ".join(x for x in (shot.get("title") or shot.get("app"), shot.get("page")) if x)
    lines = [f"[Talaria: the user has the app \"{shot.get('app')}\" open beside this chat and shared with you"
             f" ({where}). \"This\", \"here\" or \"on screen\" most likely mean it. What it shows now:]"]
    if shot.get("selection"):
        lines.append(f"Selected: {shot['selection'][:1500]}")
    seen = (shot.get("visible") or shot.get("text") or "")[:PAGE_CONTEXT_TEXT]
    lines.append(seen or "(no readable text)")
    if shot.get("scroll") is not None:
        lines.append(f"[Scrolled {shot['scroll']}% down. app_snapshot reads the whole page, fresh.]")
    return "\n".join(lines)


@_safe
def on_session_end(session_id: str = "", turn_id: str = "", platform: str = "", completed: bool = True,
                   failed: bool = False, interrupted: bool = False, **_: Any) -> None:
    if store.get_state(session_id) not in store.LIVE_STATES:
        return
    store.set_state(session_id, "idle", turn_id=turn_id, platform=platform)
    if completed and not failed and not interrupted and classify_enabled():
        t = threading.Thread(target=_classify_turn, args=(session_id, turn_id), daemon=True, name="talaria-classify")
        _pending.append(t)
        t.start()


# MARK: needs-you classification

CLASSIFY_PROMPT = (
    "You read the last message an AI assistant sent to the user it works for, at the end of a turn. "
    "Decide whether the conversation is now waiting on the user to do or decide something: answer a "
    "question, approve or choose, provide information, review or upload a file, make a payment, "
    "confirm with someone, etc. Finished work that still needs their review or go-ahead before it "
    "ships, merges, deploys, or is sent counts as waiting on them (e.g. \"ready to ship\", \"PR is up "
    "for review\", \"draft ready to send\"). Purely informational reports, and work that is already "
    "shipped or complete with nothing left for them, do not wait on them. "
    'Reply with JSON only: {"needs_you": true|false, "next": "<what the user should do, imperative, '
    'at most 10 words, empty if needs_you is false>"}'
)


# Short-lived processes (``hermes chat --oneshot``, a CLI that exits) would kill a daemon thread
# mid-call; give in-flight classifications a bounded grace period at exit.
_pending: list[threading.Thread] = []


@atexit.register
def _drain() -> None:
    for t in list(_pending):
        t.join(timeout=25)


def classify_enabled() -> bool:
    return os.environ.get("TALARIA_ATTENTION_CLASSIFY", "1") not in ("0", "false", "no")


def _note(msg: str) -> None:
    """One line in $HERMES_HOME/talaria/classify.log: the background path is otherwise silent."""
    try:
        import time
        p = store.home() / "talaria" / "classify.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} pid={os.getpid()} {msg}\n")
    except Exception:
        pass


def _classify_turn(session_id: str, turn_id: str) -> None:
    try:
        text = store.last_assistant_text(session_id).strip()
        if len(text) < 20:
            _note(f"{session_id[:16]} skip: short or missing final message ({len(text)} chars)")
            return
        verdict = classify(text)
        if verdict is None:
            _note(f"{session_id[:16]} no verdict")
            return
        # Only if nothing newer happened meanwhile (a new turn, an approval, a dismissal's next turn).
        state = store.get_state(session_id)
        if state != "idle":
            _note(f"{session_id[:16]} superseded (state {state})")
            return
        needs, nxt = verdict
        _note(f"{session_id[:16]} needs_you={needs}")
        if needs:
            store.set_state(session_id, "needs_you", reason=nxt or "Reply to Hermes", turn_id=turn_id or None)
    except Exception as e:
        _note(f"{session_id[:16]} error {type(e).__name__}: {str(e)[:200]}")


def classify(text: str) -> tuple[bool, str] | None:
    """(needs_you, next step) from the auxiliary model, or None when it can't tell."""
    from agent.auxiliary_client import call_llm
    response = call_llm(
        task=None, messages=[{"role": "system", "content": CLASSIFY_PROMPT},
                             {"role": "user", "content": text[-4000:]}],
        max_tokens=200, temperature=None, timeout=30,
        extra_body={"response_format": {"type": "json_object"}})
    return parse_verdict(response.choices[0].message.content or "")


def parse_verdict(raw: str) -> tuple[bool, str] | None:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("needs_you"), bool):
        return None
    nxt = data.get("next") if isinstance(data.get("next"), str) else ""
    return data["needs_you"], " ".join(nxt.split())[:120]


@_safe
def pre_approval_request(session_id: str = "", command: str = "", description: str = "", turn_id: str = "", **_: Any) -> None:
    what = (description or command or "an action").strip()
    store.set_state(session_id, "approval", reason=what[:300], turn_id=turn_id or None)


@_safe
def post_approval_response(session_id: str = "", **_: Any) -> None:
    if store.get_state(session_id) == "approval":
        store.set_state(session_id, "running")


@_safe
def on_human_input_request(session_id: str = "", kind: str = "", prompt: str = "", **_: Any) -> None:
    # Secrets and sudo passwords also come through here; never record their prompt text.
    reason = (prompt or "").strip()[:300] if kind in ("clarify", "question") else kind or "input"
    store.set_state(session_id, "question", reason=reason)


@_safe
def on_human_input_resolved(session_id: str = "", **_: Any) -> None:
    if store.get_state(session_id) == "question":
        store.set_state(session_id, "running")


USAGE = ("usage: /talaria version | whoami | inbox [--json] | apps | open <app> [--via <host>] | action <app> <name> [base64 json]"
         " | db-check"
         " | dismiss <session_id> [turn_id] | classify <session_id>")


def list_apps() -> list[dict[str, Any]]:
    """Every app, newest first: its folder name, its title, when it last changed. For the Desktop plugin, which can't
    list folders on the box itself. The workspace's apps that are only an App.tsx (the dev server runs them, built or
    not), then the built ones in ``talaria/apps/`` with an index page."""
    from . import appserver
    root = store.home() / "talaria" / "apps"
    apps, seen = [], set()
    source = store.home() / "talaria" / "workspace" / "apps"
    for d in source.iterdir() if source.is_dir() else ():
        if not appserver.runs(d.name):
            continue
        files = [f for f in d.rglob("*") if f.is_file()] + [f for f in (root / d.name).rglob("*") if f.is_file()]
        updated = max((f.stat().st_mtime for f in files), default=d.stat().st_mtime)
        apps.append({"name": d.name, "title": appserver.title(d.name), "folder": str(root / d.name), "updated": updated})
        seen.add(d.name)
    for d in root.iterdir() if root.is_dir() else ():
        index = d / "index.html"
        if d.name in seen or not index.is_file():
            continue
        title = None
        try:
            m = re.search(r"<title[^>]*>([^<]*)</title>", index.read_text(encoding="utf-8", errors="replace")[:20000], re.I)
            title = " ".join(m.group(1).split()) or None if m else None
        except OSError:
            pass
        updated = max((f.stat().st_mtime for f in d.rglob("*") if f.is_file()), default=index.stat().st_mtime)
        apps.append({"name": d.name, "title": title, "folder": str(d), "updated": updated})
    return sorted(apps, key=lambda a: a["updated"], reverse=True)


def handle_command(raw_args: str = "") -> str:
    try:
        args = shlex.split(raw_args or "")
    except ValueError:
        return USAGE
    sub = args[0] if args else "inbox"
    if sub == "version":
        return store.to_json({"plugin": "talaria", "version": VERSION, "api": 1})
    if sub == "whoami":
        return store.to_json({"pid": os.getpid(), "start": store.own_start_time()})
    if sub == "inbox":
        rows = store.inbox()
        if "--json" in args:
            return store.to_json({"rows": rows, "pid": os.getpid(), "known": store.known()})
        if not rows:
            return "Nothing running or waiting."
        return "\n".join(f"{r['state']:<9} {r.get('title') or r['session_id']}  {r.get('reason') or ''}".rstrip() for r in rows)
    if sub == "apps":
        return store.to_json({"apps": list_apps()})
    if sub == "open" and len(args) in (2, 4) and (len(args) == 2 or args[2] == "--via"):
        # Desktop forwards the port over its SSH connection; on a direct one it passes --via <the gateway's host>,
        # and gets the gate there and a ticket for this device (appserver.gate).
        from . import appserver, preview
        if appserver.runs(args[1]):  # the workspace dev server: every app on one port, at /<app>/
            ready = {**appserver.ensure(), "path": f"/{args[1]}/"}
            if len(args) == 4 and ready["state"] == "ready":
                return store.to_json({**ready, **appserver.gate(args[3]), "host": args[3]})
            return store.to_json(ready)
        try:
            return store.to_json({"state": "ready", "port": preview.serve_app(args[1]), "path": "/"})
        except (LookupError, OSError) as e:
            return store.to_json({"error": str(e)})
    if sub == "action" and len(args) in (3, 4):  # an app's page running one of its declared scripts
        import base64
        from . import actions
        try:
            request = base64.b64decode(args[3], validate=True) if len(args) == 4 else b"null"
        except ValueError:
            return actions.failed("The request isn't base64.")
        return actions.run(store.home() / "talaria" / "apps", args[1], args[2], request)
    if sub == "db-check":  # is SQLite here for apps' databases, and how to add what's missing (db.py --check)
        from . import actions
        return store.to_json(actions.db_module().check())
    if sub == "dismiss" and len(args) in (2, 3):
        return store.to_json({"dismissed": store.dismiss(args[1], args[2] if len(args) == 3 else None)})
    if sub == "classify" and len(args) == 2:  # debugging: run the needs-you check on a session now
        try:
            return store.to_json({"verdict": classify(store.last_assistant_text(args[1]))})
        except Exception as e:
            return store.to_json({"error": f"{type(e).__name__}: {e}"[:300]})
    return f"{USAGE} (got {args!r})"


def start_starters() -> None:
    """Install the apps Talaria ships with (starters/, e.g. Newsroom) once, in the background: build.py --starters,
    detached, since a CLI one-shot that loaded the plugin may exit long before npm finishes. Cheap when there's
    nothing to do: one file read."""
    from pathlib import Path
    import shutil
    import subprocess
    import sys
    here = Path(__file__).resolve().parent
    names = {p.parent.name for p in (here / "starters").glob("*/starter.json")}
    try:
        done = set(json.loads((store.home() / "talaria" / "starters.json").read_text()))
    except (OSError, ValueError):
        done = set()
    if not names - done or os.environ.get("TALARIA_NO_STARTERS"):
        return
    if not (shutil.which("node") or (store.home() / "node" / "bin" / "node").exists()):
        return  # build.py would only say it needs Node.js
    try:
        subprocess.Popen([sys.executable, str(here / "build.py"), "--starters"], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def move_canvases() -> None:
    """Apps were "canvases" before 0.2.3: move their folder to its new name, once."""
    old, new = store.home() / "talaria" / "canvases", store.home() / "talaria" / "apps"
    try:
        if old.is_dir() and not new.exists():
            old.rename(new)
    except OSError:
        pass


APP_SNAPSHOT = {
    "name": "app_snapshot",
    "description": (
        "Read the Talaria app page the user has open and shared with you (Hermes Desktop's eye toggle beside an app): "
        "which app and page, its title, `visible` (the text in view right now), `text` (all of the page's readable "
        "text), `selection` if any, and `scroll` (percent down). Use it when the user refers to what they're looking "
        "at ('this', 'here', 'on screen'). It's read fresh on each call. The app's code and data are in its workspace "
        "and data folders as usual; this is only what the page shows."),
    "parameters": {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "Only this app's page (its folder name). Omit for the newest shared page."},
        },
    },
}


def app_snapshot(args: dict | None = None, **_: Any) -> str:
    from . import appserver
    app = str((args or {}).get("app") or "").strip()
    return store.to_json(appserver.snapshot(app or None))


def register(ctx) -> None:
    for name, fn in (("on_session_start", on_session_start), ("pre_llm_call", pre_llm_call),
                     ("on_session_end", on_session_end),
                     ("pre_approval_request", pre_approval_request),
                     ("post_approval_response", post_approval_response),
                     ("on_human_input_request", on_human_input_request),
                     ("on_human_input_resolved", on_human_input_resolved)):
        ctx.register_hook(name, fn)
    # Skills, as /talaria:app and /talaria:routine: how to build an app Talaria opens, and how to set
    # up a routine that reads well in its Routines list (skills/*/SKILL.md).
    from pathlib import Path
    skills = Path(__file__).parent / "skills"
    move_canvases()
    start_starters()
    ctx.register_skill("app", skills / "app" / "SKILL.md",
                       description="Build or change a Talaria app: a small web app the user opens full screen in Talaria.")
    ctx.register_skill("routine", skills / "routine" / "SKILL.md",
                       description="Set up a routine: a cron job that reads well in Talaria's Routines list.")
    if hasattr(ctx, "register_tool"):  # what the shared app page shows (older Hermes: no plugin tools)
        ctx.register_tool(name="app_snapshot", toolset="talaria", schema=APP_SNAPSHOT, handler=app_snapshot,
                          description=APP_SNAPSHOT["description"], emoji="👁")
    ctx.register_command("talaria", handler=handle_command,
                         description="Talaria attention feed: running / waiting sessions across backends.",
                         args_hint="version | whoami | inbox [--json] | apps | open <app> | action <app> <name> | dismiss <id> [turn]")
