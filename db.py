"""An app's own SQLite database, for state that outgrows JSON files (docs/app-db.md).

    ~/.hermes/talaria/apps/<app>/app.db              the database, beside the app's other data
    ~/.hermes/talaria/apps/<app>/migrations/*.sql    its schema, applied in name order (001-trips.sql, 002-…)

There's no server: the page (through ``query``, as the reserved action ``talaria-db``), actions, routines and an
app's ``server.ts`` each open the file, and WAL with a busy timeout lets them write at once. ``PRAGMA user_version``
counts the migrations applied; ``migrate`` runs the rest before anything else opens it from here.

A page may run any one statement on its own app's database, or a batch in one transaction, but never reach past it:
no ATTACH, no PRAGMA that sets anything, no VACUUM INTO.

    python db.py <app>            apply its migrations
    python db.py <app> "<sql>"    run one statement and print what the page would get
    python db.py --check          is SQLite here for Python and for server.ts's Node, and if not, how to add it
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import sqlite3
except ImportError:  # a Python built without it; pysqlite3-binary is the same module, from pip
    try:
        import pysqlite3.dbapi2 as sqlite3
    except ImportError:
        sqlite3 = None

RESERVED = "talaria-db"  # the action name the SDK's db calls ride on
MIGRATION = re.compile(r"(\d+)[-_].*\.sql")
TIMEOUT = 10  # seconds a page's statement may run
MAX_RESULT = 64 * 1024


class Failed(Exception):
    pass


def path(apps_root: Path, app: str) -> Path:
    return apps_root / app / "app.db"


def migrations(apps_root: Path, app: str) -> list[Path]:
    folder = apps_root / app / "migrations"
    found = sorted((int(m.group(1)), p) for p in folder.glob("*.sql") if (m := MIGRATION.fullmatch(p.name)))
    numbers = [n for n, _ in found]
    if numbers != list(range(1, len(numbers) + 1)):
        raise Failed(f"{app}'s migrations must be numbered 1, 2, 3… with none missing or repeated (got {numbers}).")
    return [p for _, p in found]


def connect(apps_root: Path, app: str) -> sqlite3.Connection:
    """The app's database, migrated. Autocommit: a batch opens its own transaction."""
    steps = migrations(apps_root, app)
    conn = sqlite3.connect(str(path(apps_root, app)), timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    if conn.execute("PRAGMA user_version").fetchone()[0] < len(steps):
        migrate(conn, app, steps)
    return conn


def migrate(conn: sqlite3.Connection, app: str, steps: list[Path]) -> None:
    conn.execute("BEGIN IMMEDIATE")  # one process migrates; the rest wait, then find it done
    try:
        done = conn.execute("PRAGMA user_version").fetchone()[0]
        if done > len(steps):
            raise Failed(f"{app}'s database has {done} migrations applied but only {len(steps)} files.")
        for n, step in enumerate(steps[done:], done + 1):
            for statement in statements(step.read_text(encoding="utf-8")):
                try:
                    conn.execute(statement)
                except sqlite3.Error as e:
                    raise Failed(f"{step.name}: {e}") from None
            conn.execute(f"PRAGMA user_version = {n}")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def statements(script: str) -> list[str]:
    """A migration's statements, one by one, so they share the caller's transaction (executescript commits)."""
    out, current = [], ""
    for line in script.splitlines(keepends=True):
        current += line
        if sqlite3.complete_statement(current):
            if current.strip().rstrip(";").strip():
                out.append(current.strip())
            current = ""
    if current.strip():
        raise Failed(f"An unfinished statement: {current.strip()[:80]}")
    return out


LOOKUPS = {"table_info", "table_xinfo", "table_list", "index_list", "index_info", "index_xinfo", "foreign_key_list"}


def guard(action: int, arg1, arg2, db_name, trigger) -> int:
    """A page's statement stays inside its own database: no other files, no settings changed."""
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_PRAGMA and arg2 is not None and arg1.lower() not in LOOKUPS:  # reading, not setting
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def value(v):
    """A JSON value as a parameter: objects and arrays are stored as JSON text."""
    return json.dumps(v) if isinstance(v, (dict, list)) else v


def plain(v):
    return base64.b64encode(v).decode() if isinstance(v, bytes) else v


def execute(conn: sqlite3.Connection, stmt) -> dict:
    if not isinstance(stmt, dict) or not isinstance(stmt.get("sql"), str):
        raise Failed("Each statement is {sql, params}.")
    params = stmt.get("params") or []
    if isinstance(params, list):
        params = [value(p) for p in params]
    elif isinstance(params, dict):
        params = {k: value(p) for k, p in params.items()}
    else:
        raise Failed("params is a list or an object.")
    cur = conn.execute(stmt["sql"], params)
    cols = [d[0] for d in cur.description or ()]
    rows = [dict(zip(cols, map(plain, r))) for r in cur.fetchall()] if cols else []
    return {"rows": rows, "changes": cur.rowcount if cur.rowcount >= 0 else 0, "lastId": cur.lastrowid}


def run(conn: sqlite3.Connection, request) -> dict | list:
    """``{sql, params}`` → ``{rows, changes, lastId}``; ``{batch: [...]}`` → a list of those, all or nothing."""
    deadline = time.monotonic() + TIMEOUT
    conn.set_progress_handler(lambda: time.monotonic() > deadline, 10_000)
    conn.set_authorizer(guard)
    try:
        if isinstance(request, dict) and "batch" in request:
            batch = request["batch"]
            if not isinstance(batch, list):
                raise Failed("batch is a list of {sql, params}.")
            conn.execute("BEGIN IMMEDIATE")
            try:
                out = [execute(conn, s) for s in batch]
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            return out
        return execute(conn, request)
    except sqlite3.OperationalError as e:
        raise Failed(f"Took longer than {TIMEOUT} seconds." if "interrupted" in str(e) else str(e)) from None
    except sqlite3.Error as e:
        raise Failed(str(e)) from None
    finally:
        conn.set_authorizer(None)
        conn.set_progress_handler(None, 0)


def query(apps_root: Path, app: str, request: bytes) -> str:
    """What the page gets for a db call: the actions envelope, ``{"ok": true, "result": …}`` or an error."""
    if sqlite3 is None:
        return json.dumps({"ok": False, "error": "Hermes' Python has no SQLite. Ask Hermes to run db.py --check and fix it."})
    try:
        req = json.loads(request or b"null")
        if not (apps_root / app).is_dir():
            raise Failed(f"No app named {app}.")
        conn = connect(apps_root, app)
        try:
            result = json.dumps({"ok": True, "result": run(conn, req)})
        finally:
            conn.close()
    except ValueError:
        return json.dumps({"ok": False, "error": "The request isn't JSON."})
    except (Failed, sqlite3.Error) as e:
        return json.dumps({"ok": False, "error": str(e)[:500]})
    if len(result) > MAX_RESULT:
        return json.dumps({"ok": False, "error": f"The answer is over {MAX_RESULT // 1024} KB: ask for fewer rows (LIMIT)."})
    return result


def check() -> dict:
    """Whether each runtime has SQLite, what this machine is, and the steps that would add what's missing, in words
    an agent can act on whatever the platform: Hermes runs this and installs what it says."""
    import platform
    import shutil
    import subprocess
    here = Path(__file__).resolve().parent
    home = Path(os.environ.get("TALARIA_HOME") or Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "talaria")
    system = {"os": platform.system(), "machine": platform.machine(), "release": platform.release()}
    try:
        fields = dict(l.split("=", 1) for l in Path("/etc/os-release").read_text().splitlines() if "=" in l)
        system["distro"] = " ".join(fields.get(k, "").strip('"') for k in ("ID", "VERSION_ID")).strip() or None
    except OSError:
        pass
    py = {"ok": sqlite3 is not None, "python": sys.executable, "version": platform.python_version(),
          "module": sqlite3.__name__ if sqlite3 else None, "sqlite": sqlite3.sqlite_version if sqlite3 else None}
    fix = []
    if not py["ok"]:
        fix.append({"for": "python", "why": "The page's db calls, actions and the plugin's inbox need SQLite in Hermes' Python.",
                    "try": [f"{sys.executable} -m pip install pysqlite3-binary",
                            f"uv pip install --python {sys.executable} pysqlite3-binary",
                            "No wheel for this platform (pysqlite3-binary has Linux ones): give Hermes a Python built with "
                            "sqlite3 (uv python install, the OS's python3 package, or python.org), then restart Hermes."]})
    hermes_node = Path.home() / ".hermes" / "node" / "bin" / "node"
    node_bin = shutil.which("node") or (str(hermes_node) if hermes_node.exists() else None)
    node: dict = {"ok": False, "node": node_bin}
    if node_bin:
        probe = ("const r = { version: process.version }\n"
                 "try { require('node:sqlite'); r.builtin = true } catch { r.builtin = false }\n"
                 "try { const D = require(require.resolve('better-sqlite3', { paths: [process.argv[1]] })); new D(':memory:').close(); r.package = true }"
                 " catch { r.package = false }\n"
                 "console.log(JSON.stringify(r))")
        try:
            p = subprocess.run([node_bin, "-e", probe, str(home / "workspace")], capture_output=True, text=True, timeout=30)
            node.update(json.loads(p.stdout.strip().splitlines()[-1]))
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
            node["error"] = "node didn't answer"
        node["ok"] = bool(node.get("builtin") or node.get("package"))
    if not node["ok"]:
        fix.append({"for": "node", "why": "Only an app's server.ts (ctx.db(), on Desktop) needs it; the page's db calls don't.",
                    "try": ([f"{sys.executable} {here / 'build.py'} add better-sqlite3"] if node_bin else [])
                    + ["Install Node.js 22.13 or later, which has node:sqlite built in (Hermes' own lives in ~/.hermes/node)."]})
    cli = shutil.which("sqlite3")
    return {"ok": py["ok"] and node["ok"], "system": system, "python": py, "node": node,
            "cli": {"ok": bool(cli), "path": cli, "note": f"optional: {sys.executable} {here / 'db.py'} <app> \"<sql>\" does the same"},
            "fix": fix}


def main(argv: list[str]) -> int:
    if argv == ["--check"]:
        report = check()
        print(json.dumps(report, indent=1))
        return 0 if report["ok"] else 1
    if sqlite3 is None:
        print("This Python has no SQLite: run db.py --check.", file=sys.stderr)
        return 1
    if not argv or len(argv) > 2:
        print(__doc__.strip().split("\n\n")[-1], file=sys.stderr)
        return 2
    home = Path(os.environ.get("TALARIA_HOME") or Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes") / "talaria")
    root = home / "apps"
    if len(argv) == 2:
        print(query(root, argv[0], json.dumps({"sql": argv[1]}).encode()))
        return 0
    try:
        connect(root, argv[0]).close()
    except (Failed, sqlite3.Error) as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{path(root, argv[0])}: {len(migrations(root, argv[0]))} migrations applied")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
