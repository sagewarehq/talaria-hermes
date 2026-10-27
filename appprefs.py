"""Each app's icon and whether it's pinned, kept on the box so every device shows the same: the iPhone app's drawer
and Desktop's sidebar list pinned apps beside their own sections.

An icon is one of ICONS, Hermes Desktop's codicons for a project glyph (its PROJECT_ICONS); Desktop shows the name as
is and the iPhone maps it to an SF Symbol. The icon someone picks wins over the app's own ``meta.glyph`` (App.tsx);
with neither, clients show their generic app glyph. Pins keep the order they were made in.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from . import store
from .icons import ICONS

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _path() -> Path:
    return store.home() / "talaria" / "app-prefs.json"


def load() -> dict[str, Any]:
    try:
        prefs = json.loads(_path().read_text())
    except (OSError, ValueError):
        prefs = {}
    icons = prefs.get("icons") if isinstance(prefs.get("icons"), dict) else {}
    pinned = prefs.get("pinned") if isinstance(prefs.get("pinned"), list) else []
    return {"icons": {k: v for k, v in icons.items() if v in ICONS}, "pinned": [p for p in pinned if isinstance(p, str)]}


def _save(prefs: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}")
    tmp.write_text(json.dumps(prefs, indent=1))
    os.replace(tmp, p)  # every backend loads the plugin: a reader never sees half a file


def set_icon(app: str, icon: str) -> dict[str, Any]:
    """Pick ``app``'s icon; ``none`` goes back to its own (``meta.glyph``) or the generic one."""
    if not _NAME.match(app):
        return {"error": f"No app called {app!r}."}
    if icon != "none" and icon not in ICONS:
        return {"error": f"{icon!r} isn't one of the icons: {', '.join(ICONS)}."}
    prefs = load()
    if icon == "none":
        prefs["icons"].pop(app, None)
    else:
        prefs["icons"][app] = icon
    _save(prefs)
    return {"name": app, "icon": prefs["icons"].get(app)}


def set_pinned(app: str, pinned: bool) -> dict[str, Any]:
    if not _NAME.match(app):
        return {"error": f"No app called {app!r}."}
    prefs = load()
    prefs["pinned"] = [p for p in prefs["pinned"] if p != app] + ([app] if pinned else [])
    _save(prefs)
    return {"pinned": prefs["pinned"]}


def decorate(apps: list[dict[str, Any]], glyph=lambda name: None) -> list[dict[str, Any]]:
    """Each app with its ``icon`` (picked, else its own ``meta.glyph`` if that's in the kit, else null) and ``pinned``
    (its place among the pins, from 0, or null)."""
    prefs = load()
    for a in apps:
        own = glyph(a["name"])
        a["icon"] = prefs["icons"].get(a["name"]) or (own if own in ICONS else None)
        a["pinned"] = prefs["pinned"].index(a["name"]) if a["name"] in prefs["pinned"] else None
    return apps
