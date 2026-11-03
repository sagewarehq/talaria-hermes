"""Push notifications to the phones that asked for them, through the Talaria relay.

Opt-in from the phone (Settings › Notifications): it registers with the relay, makes a key, and hands this box
``/talaria push register <relay> <handle> <send_key> <key>``. Nothing is sent for a phone that didn't.

The relay holds Talaria's APNs key, so a box never needs it, and it never sees what a notification says: the box
encrypts it (AES-256-GCM, with the key only this box and the phone have) and pads it to one size, so the relay and
Apple see a handle, a time, and a blob of the same length every time. The phone's notification extension opens it.

Kept in ``$HERMES_HOME/talaria/push.db`` (owner-only), apart from the attention store everyone reads.
"""
from __future__ import annotations

import atexit
import base64
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from . import store

try:
    import sqlite3
except ImportError:
    import pysqlite3.dbapi2 as sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    handle   TEXT PRIMARY KEY,
    relay    TEXT NOT NULL,
    send_key TEXT NOT NULL,
    key      TEXT NOT NULL,          -- base64 AES-256 key, shared with the phone only
    created  REAL NOT NULL,
    seen     REAL                    -- the phone's last Overview poll: it's looking, so don't push
);
CREATE TABLE IF NOT EXISTS sent (
    id TEXT PRIMARY KEY,             -- one push per session, state and turn, across every backend
    at REAL NOT NULL
);
"""

# Every blob is this long before encryption, whatever it says.
PADDED = 512
AAD = b"talaria-push-v1"
# The phone polls Overview every 5 s while it's open.
SEEN_FRESH = 15
TOKEN = re.compile(r"[A-Za-z0-9_-]{16,128}")

_pending: list[threading.Thread] = []


@atexit.register
def _drain() -> None:
    for t in list(_pending):
        t.join(timeout=15)


def _connect() -> sqlite3.Connection:
    p = store.home() / "talaria" / "push.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=2.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=2000")
    conn.executescript(SCHEMA)
    for f in (p, p.with_name(p.name + "-wal"), p.with_name(p.name + "-shm")):
        try:
            os.chmod(f, 0o600)
        except OSError:
            pass
    return conn


def crypto_available() -> bool:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except ImportError:
        return False


def register(relay: str, handle: str, send_key: str, key: str) -> dict[str, Any]:
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?(/[A-Za-z0-9._/-]*)?", relay):
        return {"ok": False, "error": "The relay has to be an https:// address."}
    if not (TOKEN.fullmatch(handle) and TOKEN.fullmatch(send_key)):
        return {"ok": False, "error": "Not a relay handle."}
    try:
        if len(base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))) != 32:
            raise ValueError
    except ValueError:
        return {"ok": False, "error": "Not a 256-bit key."}
    if not crypto_available():
        return {"ok": False, "error": "This Hermes has no `cryptography` module to encrypt with."}
    c = _connect()
    try:
        c.execute("INSERT INTO devices (handle, relay, send_key, key, created, seen) VALUES (?,?,?,?,?,?)"
                  " ON CONFLICT(handle) DO UPDATE SET relay=excluded.relay, send_key=excluded.send_key, key=excluded.key",
                  (handle, relay.rstrip("/"), send_key, key, time.time(), time.time()))
    finally:
        c.close()
    return {"ok": True}


def forget(handle: str) -> dict[str, Any]:
    c = _connect()
    try:
        return {"ok": c.execute("DELETE FROM devices WHERE handle=?", (handle,)).rowcount > 0}
    finally:
        c.close()


def seen(handle: str) -> None:
    """The phone's Overview poll: it's open, so what this box would push it already shows."""
    if not TOKEN.fullmatch(handle or ""):
        return
    try:
        c = _connect()
        try:
            c.execute("UPDATE devices SET seen=? WHERE handle=?", (time.time(), handle))
        finally:
            c.close()
    except Exception:
        pass


def status() -> dict[str, Any]:
    c = _connect()
    try:
        rows = c.execute("SELECT handle, relay, created, seen FROM devices").fetchall()
    finally:
        c.close()
    return {"crypto": crypto_available(),
            "devices": [{"handle": h[:6], "relay": r, "created": cr, "seen": s} for h, r, cr, s in rows]}


def seal(key_b64: str, message: dict[str, Any]) -> str:
    """The message as the relay sees it: base64 of nonce ‖ ciphertext ‖ tag, from a plaintext padded to PADDED."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    msg = dict(message)
    for field, most in (("title", 100), ("p", 40)):  # names stay short, so what it's about gets the room
        if len(msg.get(field) or "") > most:
            msg[field] = msg[field][: most - 1] + "…"
    dump = lambda m: json.dumps(m, ensure_ascii=False, separators=(",", ":")).encode()  # noqa: E731
    raw = dump(msg)
    for field in ("r", "title", "p"):  # long text gives way, so the blob never grows
        while len(raw) > PADDED and msg.get(field):
            cut = len(raw) - PADDED + 3  # a character is at least a byte; "…" is three
            text = msg[field].rstrip("…")
            msg[field] = text[:-cut] + "…" if cut < len(text) else ""
            raw = dump(msg)
    padded = raw + b" " * (PADDED - len(raw))
    key = base64.urlsafe_b64decode(key_b64 + "=" * (-len(key_b64) % 4))
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, padded, AAD)).decode()


def _post(relay: str, handle: str, send_key: str, blob: str) -> int:
    req = urllib.request.Request(f"{relay}/v1/send/{handle}", data=json.dumps({"blob": blob}).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {send_key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def send_to(handle: str, relay: str, send_key: str, key: str, message: dict[str, Any]) -> int:
    code = _post(relay, handle, send_key, seal(key, message))
    if code in (404, 410):  # the phone turned it off (the relay forgot it), or iOS dropped its token
        forget(handle)
    return code


def _badge() -> int:
    return sum(1 for r in store.inbox() if r["state"] in ("approval", "question", "needs_you"))


def notify(session_id: str, kind: str, reason: Optional[str] = None, turn_id: Optional[str] = None) -> None:
    """A session now waits on you (kind: approval | question | needs_you): tell each phone that turned push on,
    once, unless it's open. Off the hook's thread; never raises."""
    if not session_id or not crypto_available():
        return
    t = threading.Thread(target=_notify, args=(session_id, kind, reason, turn_id), daemon=True, name="talaria-push")
    _pending.append(t)
    t.start()


def _notify(session_id: str, kind: str, reason: Optional[str], turn_id: Optional[str]) -> None:
    try:
        c = _connect()
        try:
            devices = c.execute("SELECT handle, relay, send_key, key, seen FROM devices").fetchall()
            if not devices:
                return
            once = hashlib.sha256(f"{session_id}\0{kind}\0{turn_id or ''}\0{reason or ''}".encode()).hexdigest()[:32]
            if c.execute("INSERT OR IGNORE INTO sent (id, at) VALUES (?, ?)", (once, time.time())).rowcount == 0:
                return  # another backend already sent this one
            c.execute("DELETE FROM sent WHERE at < ?", (time.time() - 7 * 86400,))
        finally:
            c.close()
        meta = store._session_meta([session_id]).get(session_id, {})
        message = {"v": 1, "k": kind, "s": session_id, "title": meta.get("title") or "", "r": (reason or "")[:300],
                   "p": os.path.basename((meta.get("cwd") or "").rstrip("/")), "n": _badge()}
        for handle, relay, send_key, key, last in devices:
            if last and time.time() - last < SEEN_FRESH:
                continue
            send_to(handle, relay, send_key, key, message)
    except Exception:
        pass


def test(handle: str) -> dict[str, Any]:
    c = _connect()
    try:
        row = c.execute("SELECT handle, relay, send_key, key FROM devices WHERE handle=?", (handle,)).fetchone()
    finally:
        c.close()
    if not row:
        return {"ok": False, "error": "No phone with that handle here."}
    code = send_to(*row, {"v": 1, "k": "test", "s": "", "title": "", "r": "Notifications from this server work.", "p": "", "n": 0})
    return {"ok": code == 202, "status": code}
