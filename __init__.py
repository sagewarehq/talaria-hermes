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

VERSION = "0.2.0"


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
def pre_llm_call(session_id: str = "", turn_id: str = "", platform: str = "", **_: Any) -> None:
    # Once per turn, before the model runs. on_session_start only fires on a session's first turn,
    # so without this a reply to a "needs you" turn left that row up and its end went unclassified.
    # Returns None: no context injected into the turn.
    store.set_state(session_id, "running", turn_id=turn_id or None, platform=platform, new_turn=True)


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
    "You read the last message an AI assistant sent to its principal, Jesse, at the end of a turn. "
    "Decide whether the conversation is now waiting on Jesse to do or decide something: answer a "
    "question, approve or choose, provide information, review or upload a file, make a payment, "
    "confirm with someone, etc. Finished work that still needs his review or go-ahead before it "
    "ships, merges, deploys, or is sent counts as waiting on him (e.g. \"ready to ship\", \"PR is up "
    "for review\", \"draft ready to send\"). Purely informational reports, and work that is already "
    "shipped or complete with nothing left for him, do not wait on him. "
    'Reply with JSON only: {"needs_you": true|false, "next": "<what Jesse should do, imperative, '
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


USAGE = "usage: /talaria version | whoami | inbox [--json] | dismiss <session_id> | classify <session_id>"


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
    if sub == "dismiss" and len(args) == 2:
        return store.to_json({"dismissed": store.dismiss(args[1])})
    if sub == "classify" and len(args) == 2:  # debugging: run the needs-you check on a session now
        try:
            return store.to_json({"verdict": classify(store.last_assistant_text(args[1]))})
        except Exception as e:
            return store.to_json({"error": f"{type(e).__name__}: {e}"[:300]})
    return f"{USAGE} (got {args!r})"


def register(ctx) -> None:
    for name, fn in (("on_session_start", on_session_start), ("pre_llm_call", pre_llm_call),
                     ("on_session_end", on_session_end),
                     ("pre_approval_request", pre_approval_request),
                     ("post_approval_response", post_approval_response),
                     ("on_human_input_request", on_human_input_request),
                     ("on_human_input_resolved", on_human_input_resolved)):
        ctx.register_hook(name, fn)
    # Skills, as /talaria:canvas and /talaria:routine: how to build a canvas Talaria opens, and how to set
    # up a routine that reads well in its Routines list (skills/*/SKILL.md).
    from pathlib import Path
    skills = Path(__file__).parent / "skills"
    ctx.register_skill("canvas", skills / "canvas" / "SKILL.md",
                       description="Build or change a Talaria canvas: a small web app the user opens full screen in Talaria.")
    ctx.register_skill("routine", skills / "routine" / "SKILL.md",
                       description="Set up a routine: a cron job that reads well in Talaria's Routines list.")
    ctx.register_command("talaria", handler=handle_command,
                         description="Talaria attention feed: running / waiting sessions across backends.",
                         args_hint="version | whoami | inbox [--json] | dismiss <id>")
