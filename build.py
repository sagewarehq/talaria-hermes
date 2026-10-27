"""Build Talaria apps from the workspace: one Vite + React project on this machine, each app a sub-app of it.

    python3 ~/.hermes/plugins/talaria/build.py <name>          build one app
    python3 ~/.hermes/plugins/talaria/build.py --all           build every app in the workspace
    python3 ~/.hermes/plugins/talaria/build.py --new <name> <icon>  start an app from the template, then build it
    python3 ~/.hermes/plugins/talaria/build.py migrate <name>  move an app from before the workspace into it
    python3 ~/.hermes/plugins/talaria/build.py add <pkg>…      npm install packages into the workspace
    python3 ~/.hermes/plugins/talaria/build.py --starters      install the apps Talaria ships with, once each
    python3 ~/.hermes/plugins/talaria/build.py --starter <name>  install one of them now (the Apps marketplace)

An app's source is ``~/.hermes/talaria/workspace/apps/<name>/``; it's built into ``~/.hermes/talaria/apps/<name>/``,
the folder the phone, the preview and Desktop load. A build only replaces what the last build wrote there (listed in
its ``.build.json``), so data that Hermes or a routine writes beside it survives, and a failed build changes nothing.
See docs/apps-vite.md.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "workspace"

# What every app can count on. Added to the workspace's package.json when missing; a version already there is kept,
# so Hermes can upgrade one.
PACKAGES = {
    "vite": "8.3.5", "@vitejs/plugin-react": "6.1.2", "typescript": "7.0.2",
    "react": "19.3.1", "react-dom": "19.3.1", "@types/react": "19.3.0", "@types/react-dom": "19.3.0",
    "tailwindcss": "4.3.3", "@tailwindcss/vite": "4.3.3",
    "motion": "14.6.0", "lucide-react": "1.61.0", "d3": "7.9.0", "@types/d3": "7.4.3",
}
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
# Paths the workspace dev server answers itself (talaria/apps.mjs), so no app can be named after one.
RESERVED = {"apps", "shared", "talaria", "node_modules", "lib", "legacy", "assets"}
# An older app's own code, which its rewrite replaces. Everything else in its folder (data, images, a routine's
# scripts) stays where it is.
CODE = {".html", ".htm", ".js", ".mjs", ".jsx", ".tsx", ".ts", ".css"}


class BuildError(Exception):
    pass


def icons() -> tuple[str, ...]:
    """The icons an app may wear (icons.py), loaded by path: this file runs as a script, outside the package."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("talaria_icons", HERE / "icons.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ICONS


def talaria_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        home = Path(get_hermes_home())
    except Exception:
        home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home / "talaria"


def workspace() -> Path:
    return talaria_home() / "workspace"


def built(name: str) -> Path:
    return talaria_home() / "apps" / name


def node_env() -> dict[str, str]:
    """The environment for node and npm, with node's own folder first on PATH: Hermes' node lives in
    ~/.hermes/node/bin behind a /usr/local/bin symlink, npm only beside it, and npm's and vite's launchers run
    ``#!/usr/bin/env node``, so a routine with a bare PATH would otherwise find neither."""
    env = dict(os.environ)
    dirs = []
    node = shutil.which("node")
    if node:
        dirs.append(str(Path(node).resolve().parent))
    dirs.append(str(Path.home() / ".hermes" / "node" / "bin"))
    env["PATH"] = os.pathsep.join(dirs + [env.get("PATH", "")])
    if not shutil.which("node", path=env["PATH"]) or not shutil.which("npm", path=env["PATH"]):
        raise BuildError("Building apps needs Node.js and npm on this machine. Without them, write a plain HTML app "
                         "in ~/.hermes/talaria/apps/<name>/ instead.")
    return env


@contextmanager
def locked(ws: Path):
    """One build at a time per workspace, so Hermes and a routine don't race npm install or a swap."""
    ws.mkdir(parents=True, exist_ok=True)
    with open(ws / ".lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def seed(ws: Path) -> None:
    """Set up the workspace: Hermes' own files (package.json, tsconfig.json, shared/) only when missing; the
    plugin's talaria/ folder brought in step with the plugin's copy every time (only the files that changed), so a
    plugin update reaches it."""
    for src in TEMPLATE.rglob("*"):
        rel = src.relative_to(TEMPLATE)
        if rel.parts[0] == "talaria" or src.is_dir():
            continue
        dest = ws / rel
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    (ws / "apps").mkdir(exist_ok=True)
    teach_paths(ws)
    # Only what changed: the dev server watches talaria/, and rewriting every file reloaded every open app.
    mine = {p.relative_to(TEMPLATE / "talaria") for p in (TEMPLATE / "talaria").rglob("*") if p.is_file()}
    dest = ws / "talaria"
    for rel in sorted(mine):
        src, out = TEMPLATE / "talaria" / rel, dest / rel
        if not out.is_file() or out.read_bytes() != src.read_bytes():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
    for old in sorted((p for p in dest.rglob("*") if p.is_file()), reverse=True) if dest.is_dir() else ():
        if old.relative_to(dest) not in mine:
            old.unlink()


def teach_paths(ws: Path) -> None:
    """Add the template's tsconfig path aliases a workspace seeded by an older plugin doesn't have (``talaria``)."""
    path = ws / "tsconfig.json"
    try:
        mine, theirs = json.loads(path.read_text()), json.loads((TEMPLATE / "tsconfig.json").read_text())
    except (OSError, ValueError):
        return
    paths = mine.setdefault("compilerOptions", {}).setdefault("paths", {})
    include = mine.setdefault("include", [])
    missing = {k: v for k, v in theirs["compilerOptions"]["paths"].items() if k not in paths}
    extra = [i for i in theirs.get("include", []) if i not in include]
    if missing or extra:
        paths.update(missing)
        include.extend(extra)
        path.write_text(json.dumps(mine, indent=2) + "\n")


def add_packages(ws: Path) -> bool:
    """Add any of PACKAGES missing from the workspace's package.json. True if it changed."""
    path = ws / "package.json"
    pkg = json.loads(path.read_text())
    have = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}
    missing = {k: v for k, v in PACKAGES.items() if k not in have}
    if not missing:
        return False
    pkg["dependencies"] = dict(sorted({**pkg.get("dependencies", {}), **missing}.items()))
    path.write_text(json.dumps(pkg, indent=2) + "\n")
    return True


def run(cmd: list[str], ws: Path, env: dict[str, str], what: str) -> None:
    p = subprocess.run(cmd, cwd=ws, env={**env, "NO_COLOR": "1", "FORCE_COLOR": "0"}, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True)
    if p.returncode:
        # The message without colour codes or node's stack, which only name Vite's own files.
        out = re.sub(r"\x1b\[[0-9;]*m", "", p.stdout + p.stderr)
        out = "\n".join(l for l in out.splitlines() if not re.match(r"\s+at .*(node_modules|node:)", l))
        raise BuildError(f"{what} failed:\n{out.strip()[-6000:]}")


def install(ws: Path, env: dict[str, str]) -> None:
    lock = ws / "node_modules" / ".package-lock.json"
    if add_packages(ws) or not lock.exists() or lock.stat().st_mtime < (ws / "package.json").stat().st_mtime:
        run(["npm", "install", "--no-audit", "--no-fund"], ws, env, "npm install")


def files_in(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}


def swap(staged: Path, dest: Path, retire: set[str] = frozenset()) -> None:
    """Put a build's output in ``dest``: remove what the last build wrote that this one didn't (or, on the first
    build of a migrated app, its old code, ``retire``), copy the new files in, and record them. Files no build
    wrote (data.json, a routine's output) are left alone."""
    record = dest / ".build.json"
    try:
        old = set(json.loads(record.read_text()).get("files", []))
    except (OSError, ValueError):
        old = set(retire)
    new = files_in(staged)
    for rel in sorted(old - new):
        (dest / rel).unlink(missing_ok=True)
    for rel in new:
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged / rel, dest / rel)
    record.write_text(json.dumps({"files": sorted(new)}, indent=1) + "\n")
    for d in sorted((p for p in dest.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()


def build_one(name: str, ws: Path, env: dict[str, str]) -> Path:
    src = ws / "apps" / name
    if not any((src / f).is_file() for f in ("index.html", "App.tsx", "App.jsx")):
        raise BuildError(f"No app source at {src}/ (an App.tsx; start one with --new {name}).")
    staged = ws / ".out" / name
    run(["node", str(ws / "node_modules" / "vite" / "bin" / "vite.js"), "build", "--config", "talaria/vite.config.mjs",
         "--logLevel", "warn"], ws, {**env, "TALARIA_APP": name, "TALARIA_OUT": str(staged)}, f"Building {name}")
    if not (staged / "index.html").is_file():
        raise BuildError(f"Building {name} made no index.html.")
    dest = built(name)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        retire = set(json.loads((ws / "legacy" / name / "legacy.json").read_text())["retire"])
    except (OSError, ValueError, KeyError):
        retire = set()
    swap(staged, dest, retire)
    shutil.rmtree(staged, ignore_errors=True)
    migrate_db(name)
    return dest


def migrate_db(name: str) -> None:
    """Apply the app's migrations/ to its app.db (db.py), so a routine finds its tables before the page first asks."""
    if not (built(name) / "migrations").is_dir():
        return
    import importlib.util
    db = sys.modules.get("talaria_db")
    if db is None:
        spec = importlib.util.spec_from_file_location("talaria_db", HERE / "db.py")
        db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(db)
        db = sys.modules.setdefault("talaria_db", db)
    try:
        db.connect(built(name).parent, name).close()
    except Exception as e:
        raise BuildError(f"Built {name}, but its database: {e}") from None


def older(name: str) -> bool:
    """An app from before the workspace: a built folder with a page but no build record."""
    return (built(name) / "index.html").is_file() and not (built(name) / ".build.json").is_file()


def new_app(name: str, ws: Path, title: str | None = None, glyph: str | None = None) -> None:
    """An app from the template, with its title and its icon (``meta.glyph``; a migrated app may start without)."""
    if name in RESERVED:
        raise BuildError(f"{name} is taken by the workspace itself; pick another name.")
    src = ws / "apps" / name
    if src.exists():
        raise BuildError(f"{src} already exists.")
    shutil.copytree(ws / "talaria" / "new", src)
    title = title or name.replace("-", " ").replace("_", " ").title()
    for f in src.rglob("*"):
        if f.is_file():
            text = f.read_text().replace("__TITLE__", title)
            text = text.replace("__GLYPH__", glyph) if glyph else text.replace(", glyph: '__GLYPH__'", "")
            f.write_text(text)


def migrate(name: str, ws: Path) -> None:
    """Start an older app's rewrite in the workspace, without touching the live app: a copy of its code in
    legacy/<name>/ to work from, a new source folder under its old title, and the list of old code files its
    first build retires. Its data and other files stay in the built folder."""
    dest = built(name)
    if not older(name):
        raise BuildError(f"{dest} isn't an app from before the workspace (no index.html, or it's built here already).")
    legacy = ws / "legacy" / name
    if legacy.exists():
        raise BuildError(f"{legacy} already exists: {name} is being migrated.")
    code = sorted(rel for rel in files_in(dest) if Path(rel).suffix.lower() in CODE
                  and not any(part.startswith(".") or part in ("node_modules", "__pycache__") for part in Path(rel).parts))
    m = re.search(r"<title[^>]*>([^<]*)</title>", (dest / "index.html").read_text(errors="replace"), re.I)
    new_app(name, ws, " ".join(m.group(1).split()) if m and m.group(1).strip() else None)
    for rel in code:
        (legacy / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest / rel, legacy / rel)
    (legacy / "legacy.json").write_text(json.dumps({"retire": code}, indent=1) + "\n")
    kept = sorted(files_in(dest) - set(code))
    print(f"source: {ws / 'apps' / name}/  (the template, to rewrite)\n"
          f"old code: {legacy}/  (a copy to work from: {', '.join(code)})\n"
          f"live: {dest}/ stays as it is until the first build, which replaces the old code with the new build.\n"
          f"kept there: {', '.join(kept) or 'nothing else'}")


STARTERS = HERE / "starters"


def starters_record() -> Path:
    return talaria_home() / "starters.json"


def unchanged_copy(src: Path, dest: Path) -> bool:
    """dest holds nothing but src's files as they ship (or isn't there): the starter's own copy, safe to replace."""
    if not dest.exists():
        return True
    theirs = files_in(dest)
    return theirs <= files_in(src) and all((dest / f).read_bytes() == (src / f).read_bytes() for f in theirs)


def install_starter(name: str, ws: Path, env: dict[str, str], retry: bool = False) -> str:
    """Install a starter app (starters/<name>/) once: its source into the workspace, its shared code, its folder's
    scripts and settings, its Python packages in a venv of its own, then build it. A starter that's already there
    (the user's own app by that name, or this one) is left alone, and so is one the user has deleted since. A retry
    of one that failed picks up where it stopped: its source is the starter's, and nothing was built."""
    src = STARTERS / name
    meta = json.loads((src / "starter.json").read_text())
    if retry and not (built(name) / "index.html").exists() and unchanged_copy(src / "source", ws / "apps" / name):
        shutil.rmtree(ws / "apps" / name, ignore_errors=True)
    elif (ws / "apps" / name).exists() or built(name).exists():
        return "skipped: already there"
    shutil.copytree(src / "source", ws / "apps" / name)
    if meta.get("shared") and not (ws / "shared" / meta["shared"]).exists():
        shutil.copytree(src / "shared", ws / "shared" / meta["shared"])
    shutil.copytree(src / "app", built(name), dirs_exist_ok=True)
    if meta.get("venv") and meta.get("requirements"):
        venv = talaria_home() / "venvs" / meta["venv"]
        try:  # optional: without it, the app does without (Newsroom's reader links to the site instead)
            if not (venv / "bin" / "python").exists():
                subprocess.run([sys.executable, "-m", "venv", str(venv)],
                               check=True, capture_output=True, timeout=120)
            subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "-q", *meta["requirements"]],
                           check=True, capture_output=True, timeout=600)
        except (subprocess.SubprocessError, OSError):
            shutil.rmtree(venv, ignore_errors=True)
    install(ws, env)
    build_one(name, ws, env)
    return "installed"


def install_starters(ws: Path, env: dict[str, str]) -> dict[str, str]:
    """Every starter not yet recorded in talaria/starters.json, each tried once."""
    try:
        done = json.loads(starters_record().read_text())
    except (OSError, ValueError):
        done = {}
    for src in sorted(STARTERS.glob("*/starter.json")) if STARTERS.is_dir() else ():
        name = src.parent.name
        if name in done:
            continue
        try:
            with announced(name):
                done[name] = install_starter(name, ws, env)
        except (BuildError, OSError, ValueError, subprocess.SubprocessError) as e:
            done[name] = f"failed: {e}"[:300]
        starters_record().write_text(json.dumps(done, indent=1) + "\n")
    return done


def installing(name: str) -> Path:
    """While a starter installs from the Apps marketplace: who's installing it and since when (``/talaria catalog``
    reads it; the install removes it when it's done, whatever the outcome)."""
    return talaria_home() / "installing" / f"{name}.json"


@contextmanager
def announced(name: str):
    """The marketplace shows this starter as installing while it does, first run's install included."""
    f = installing(name)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"pid": os.getpid(), "started": time.time()}))
    try:
        yield
    finally:
        f.unlink(missing_ok=True)


def record(name: str, outcome: str) -> None:
    """Note a starter's install outcome in talaria/starters.json, beside the others."""
    try:
        done = json.loads(starters_record().read_text())
    except (OSError, ValueError):
        done = {}
    starters_record().parent.mkdir(parents=True, exist_ok=True)
    starters_record().write_text(json.dumps({**done, name: outcome}, indent=1) + "\n")


def starter_outcome(name: str) -> str:
    """What happened the last time this starter was installed, or "" if it never was."""
    try:
        return str(json.loads(starters_record().read_text()).get(name) or "")
    except (OSError, ValueError, AttributeError):
        return ""


def install_chosen(name: str, ws: Path, env: dict[str, str]) -> str:
    """A starter someone picked in the Apps marketplace: installed even if it was recorded before (one deleted since,
    or a first try that failed), never over an app already there. The outcome is recorded like a first-run one."""
    if starter_outcome(name) == "installed" and (built(name) / "index.html").exists():
        return "installed"  # first run's install finished while this one waited for the lock
    try:
        if not (STARTERS / name / "starter.json").is_file():
            outcome = f"failed: Talaria doesn't ship an app called {name}."
        else:
            with announced(name):
                outcome = install_starter(name, ws, env, retry=starter_outcome(name).startswith("failed"))
    except (BuildError, OSError, ValueError, subprocess.SubprocessError) as e:
        outcome = f"failed: {e}"[:300]
    record(name, outcome)
    return outcome


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    ws = workspace()
    if argv[0] == "--starter":
        return install_starter_main(argv[1:2], ws)
    try:
        env = node_env()
        with locked(ws):
            seed(ws)
            if argv[0] == "--starters":
                for name, outcome in install_starters(ws, env).items():
                    print(f"{name}: {outcome}")
                return 0
            if argv[0] == "add":
                if len(argv) < 2:
                    raise BuildError("add needs a package name.")
                add_packages(ws)
                run(["npm", "install", "--no-audit", "--no-fund", *argv[1:]], ws, env, "npm install")
                print(f"added {' '.join(argv[1:])}")
                return 0
            if argv[0] in ("--new", "migrate"):
                names = argv[1:2]
            elif argv[0] == "--all":
                names = sorted(d.name for d in (ws / "apps").iterdir() if (d / "index.html").is_file())
            else:
                names = argv[:1]
            if not names or not all(NAME.fullmatch(n) for n in names):
                raise BuildError("An app name is short kebab-case: spending, hiring-pipeline, cebu-trip.")
            if argv[0] == "migrate":
                migrate(names[0], ws)
                install(ws, env)
                return 0
            if argv[0] == "--new":
                if older(names[0]):  # the template would replace the live app on the phone
                    raise BuildError(f"{names[0]} is an app from before the workspace: use migrate {names[0]}.")
                glyph = argv[2] if len(argv) > 2 else None
                if glyph not in icons():  # every app starts with its icon in Talaria's lists and sidebars
                    raise BuildError(f"Pick its icon: --new {names[0]} <icon>, the one that fits best of "
                                     f"{', '.join(icons())}." + (f" ({glyph!r} isn't one.)" if glyph else ""))
                new_app(names[0], ws, glyph=glyph)
                print(f"source: {ws / 'apps' / names[0]}/")
            install(ws, env)
            failed = 0
            for name in names:
                try:
                    print(f"built:  {build_one(name, ws, env)}/")
                except BuildError as e:
                    failed += 1
                    print(e, file=sys.stderr)
            return 1 if failed else 0
    except BuildError as e:
        print(e, file=sys.stderr)
        return 1


def install_starter_main(names: list[str], ws: Path) -> int:
    """build.py --starter <name>: the marketplace's install, run detached by /talaria install. Its progress file goes
    whatever happens, so the Apps list never shows an install that stopped as still running."""
    if not names or not NAME.fullmatch(names[0]):
        print("--starter needs the name of an app Talaria ships with.", file=sys.stderr)
        return 2
    name = names[0]
    try:
        try:
            env = node_env()
        except BuildError as e:
            outcome = f"failed: {e}"[:300]
            record(name, outcome)
        else:
            with locked(ws):
                seed(ws)
                outcome = install_chosen(name, ws, env)
    finally:
        installing(name).unlink(missing_ok=True)
    print(f"{name}: {outcome}")
    return 0 if outcome == "installed" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
