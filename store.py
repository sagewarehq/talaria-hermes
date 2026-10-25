"""Attention store: one row per session, written by every Hermes backend process.

SQLite in WAL mode with a busy timeout, because Desktop's backend, Talaria's backend, the cron
scheduler and the messaging gateway all write concurrently. Rows carry the writer's pid and start
time so a reader can tell a live turn from one whose process died mid-turn.
"""
from __future__ import annotations

import json
import os
try:
    import sqlite3
except ImportError:  # a Python built without it: pysqlite3-binary (db.py --check says how to add it)
    import pysqlite3.dbapi2 as sqlite3
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS attention (
    session_id   TEXT PRIMARY KEY,
    state        TEXT NOT NULL,          -- running | approval | question | needs_you | idle
    reason       TEXT,                   -- approval command / question text / next step
    turn_id      TEXT,
    platform     TEXT,
    updated      REAL NOT NULL,
    writer_pid   INTEGER,
    writer_start REAL,
    dismissed_turn TEXT                  -- turn_id the user dismissed; a new turn raises it again
);
"""

# States a reader treats as "live": only meaningful while the writing process is alive.
LIVE_STATES = {"running", "approval", "question"}


def home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def db_path() -> Path:
    return home() / "talaria" / "attention.db"


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=2.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=2000")
    conn.executescript(SCHEMA)
    return conn


def own_start_time() -> Optional[float]:
    try:
        from hermes_cli.active_sessions import _own_start_time
        return _own_start_time()
    except Exception:
        return None


def writer_alive(pid: Any, start: Any) -> Optional[bool]:
    """True/False when knowable (pid + start time, so a recycled pid reads dead), else None."""
    try:
        from hermes_cli.active_sessions import _pid_liveness
        return _pid_liveness(pid, start)
    except Exception:
        try:
            os.kill(int(pid), 0)
            return True
        except Exception:
            return False


def set_state(session_id: str, state: str, *, reason: Optional[str] = None, turn_id: Optional[str] = None,
              platform: Optional[str] = None, keep_reason: bool = False, new_turn: bool = False,
              conn: Optional[sqlite3.Connection] = None) -> None:
    """Upsert a session's state, stamped with this process as the writer. ``new_turn`` clears a
    dismissal: the next turn raises a dismissed session again."""
    if not session_id:
        return
    own = conn is None
    c = conn or connect()
    try:
        row = c.execute("SELECT reason, turn_id, platform FROM attention WHERE session_id=?", (session_id,)).fetchone()
        prev_reason, prev_turn, prev_platform = row if row else (None, None, None)
        c.execute(
            "INSERT INTO attention (session_id, state, reason, turn_id, platform, updated, writer_pid, writer_start)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(session_id) DO UPDATE SET state=excluded.state, reason=excluded.reason,"
            " turn_id=excluded.turn_id, platform=excluded.platform, updated=excluded.updated,"
            " writer_pid=excluded.writer_pid, writer_start=excluded.writer_start",
            (session_id, state, prev_reason if keep_reason else reason, turn_id or prev_turn,
             platform or prev_platform, time.time(), os.getpid(), own_start_time()))
        if new_turn:
            c.execute("UPDATE attention SET dismissed_turn=NULL WHERE session_id=?", (session_id,))
    finally:
        if own:
            c.close()


def get_state(session_id: str, conn: Optional[sqlite3.Connection] = None) -> Optional[str]:
    own = conn is None
    c = conn or connect()
    try:
        row = c.execute("SELECT state FROM attention WHERE session_id=?", (session_id,)).fetchone()
        return row[0] if row else None
    finally:
        if own:
            c.close()


def dismiss(session_id: str, turn_id: Optional[str] = None, conn: Optional[sqlite3.Connection] = None) -> bool:
    """Hide the session's row until its next turn. ``turn_id`` is the turn the user saw: a dismissal
    that arrives late (a cached row, an Undo that waited, a retry) then hides only that turn, never a
    newer one they haven't seen. A session this store hasn't seen (its turns ran in a backend without
    the plugin) gets a row of its own, dismissed, so the hide holds on every device (the app leaves the
    sessions the store knows to it) instead of only on the one that asked."""
    if not session_id:
        return False
    own = conn is None
    c = conn or connect()
    try:
        cur = c.execute("UPDATE attention SET dismissed_turn=COALESCE(?, turn_id, '') WHERE session_id=?",
                        (turn_id or None, session_id))
        if cur.rowcount == 0:
            cur = c.execute("INSERT INTO attention (session_id, state, updated, dismissed_turn) VALUES (?, 'idle', ?, '')"
                            " ON CONFLICT(session_id) DO NOTHING", (session_id, time.time()))
        return cur.rowcount > 0
    finally:
        if own:
            c.close()


def _session_meta(ids: list[str]) -> dict[str, dict[str, Any]]:
    """Title / cwd / source / parent (a subagent's spawning session) from Hermes's state.db,
    read-only and best-effort."""
    path = home() / "state.db"
    if not ids or not path.exists():
        return {}
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        q = ",".join("?" for _ in ids)
        try:
            rows = c.execute(f"SELECT id, title, cwd, source, parent_session_id FROM sessions WHERE id IN ({q})", ids).fetchall()
        except sqlite3.OperationalError:  # an older state.db without the lineage column
            rows = [r + (None,) for r in c.execute(f"SELECT id, title, cwd, source FROM sessions WHERE id IN ({q})", ids).fetchall()]
        c.close()
        return {r[0]: {"title": r[1], "cwd": r[2], "source": r[3], "parent_session_id": r[4]} for r in rows}
    except Exception:
        return {}


DONE_MAX_AGE_S = 24 * 3600


def inbox(conn: Optional[sqlite3.Connection] = None, *, max_age_s: float = 3 * 86400) -> list[dict[str, Any]]:
    """Rows worth showing: live turns (running / approval / question), turns that died mid-flight
    (stale), finished turns that left the user something to do (needs_you), and other turns that
    finished in the last day (done; not cron runs, which finish all day). Dismissed rows stay
    hidden until their session's next turn."""
    own = conn is None
    c = conn or connect()
    try:
        rows = c.execute(
            "SELECT session_id, state, reason, turn_id, platform, updated, writer_pid, writer_start, dismissed_turn"
            " FROM attention WHERE updated > ? ORDER BY updated DESC", (time.time() - max_age_s,)).fetchall()
    finally:
        if own:
            c.close()
    out = []
    for sid, state, reason, turn_id, platform, updated, pid, start, dismissed in rows:
        if dismissed is not None and dismissed == (turn_id or ""):
            continue
        if state in LIVE_STATES:
            if writer_alive(pid, start) is False:
                state = "stale"   # the process died mid-turn (crash, kill, reboot)
        elif state == "idle":
            if updated < time.time() - DONE_MAX_AGE_S:
                continue
            state = "done"
        elif state != "needs_you":
            continue
        out.append({"session_id": sid, "state": state, "reason": reason, "turn_id": turn_id,
                    "platform": platform, "updated": updated, "writer_pid": pid})
    meta = _session_meta([r["session_id"] for r in out])
    for r in out:
        r.update(meta.get(r["session_id"], {}))
    return [r for r in out if not (r["state"] == "done" and r.get("source") == "cron")]


def known(conn: Optional[sqlite3.Connection] = None, *, max_age_s: float = 3 * 86400) -> list[str]:
    """Sessions this store has a row for in the window: the app checks sessions missing here
    (started before the plugin loaded, or in a backend without it) its own way."""
    own = conn is None
    c = conn or connect()
    try:
        return [r[0] for r in c.execute("SELECT session_id FROM attention WHERE updated > ?", (time.time() - max_age_s,))]
    finally:
        if own:
            c.close()


def last_assistant_text(session_id: str) -> str:
    """The session's latest non-empty assistant message from state.db (flushed before turn end)."""
    path = home() / "state.db"
    try:
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        row = c.execute("SELECT content FROM messages WHERE session_id=? AND role='assistant' AND content IS NOT NULL"
                        " AND trim(content) != '' ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
        c.close()
        return row[0] if row and isinstance(row[0], str) else ""
    except Exception:
        return ""


def to_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
