"""Each app's icon, its color and whether it's pinned, kept on the box so every device shows the same: the iPhone app's drawer
and Desktop's sidebar list pinned apps beside their own sections.

An icon is one of icons.py's ICONS, Hermes Desktop's codicons; Desktop shows the name as is and the iPhone maps it to an
SF Symbol. The icon someone picks wins over the app's own ``meta.glyph`` (App.tsx); with neither, clients show their
generic app glyph. IMAGE is the app's own image as its icon, a fully custom one (appserver.image), when it has one.
A color is one of COLORS, Desktop's project swatches by name; with none, clients draw it in their
own ink. Pins keep the order they were made in.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from . import store
from .icons import COLORS, ICONS

IMAGE = "image"

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def valid(app: str) -> bool:
    """A name that can be an app's folder: no paths."""
    return bool(_NAME.match(app))


def _path() -> Path:
    return store.home() / "talaria" / "app-prefs.json"


def load() -> dict[str, Any]:
    try:
        prefs = json.loads(_path().read_text())
    except (OSError, ValueError):
        prefs = {}
    icons = prefs.get("icons") if isinstance(prefs.get("icons"), dict) else {}
    colors = prefs.get("colors") if isinstance(prefs.get("colors"), dict) else {}
    pinned = prefs.get("pinned") if isinstance(prefs.get("pinned"), list) else []
    return {"icons": {k: v for k, v in icons.items() if v in ICONS or v == IMAGE},
            "colors": {k: v for k, v in colors.items() if v in COLORS},
            "pinned": [p for p in pinned if isinstance(p, str)]}


def _save(prefs: dict[str, Any]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}")
    tmp.write_text(json.dumps(prefs, indent=1))
    os.replace(tmp, p)  # every backend loads the plugin: a reader never sees half a file


def set_icon(app: str, icon: str, image=lambda name: None) -> dict[str, Any]:
    """Pick ``app``'s icon, or ``image`` for its own; ``none`` goes back to its own (``meta.glyph``) or the generic
    one."""
    if not _NAME.match(app):
        return {"error": f"No app called {app!r}."}
    if icon == IMAGE and not image(app):
        return {"error": f"{app} has no image of its own: give it one in meta.icon (an SVG or PNG in its folder)."}
    if icon not in ("none", IMAGE) and icon not in ICONS:
        return {"error": f"{icon!r} isn't one of the icons: {', '.join(ICONS)}."}
    prefs = load()
    if icon == "none":
        prefs["icons"].pop(app, None)
    else:
        prefs["icons"][app] = icon
    _save(prefs)
    return {"name": app, "icon": prefs["icons"].get(app)}


def set_color(app: str, color: str) -> dict[str, Any]:
    """Pick ``app``'s color; ``none`` goes back to the clients' own ink."""
    if not _NAME.match(app):
        return {"error": f"No app called {app!r}."}
    if color != "none" and color not in COLORS:
        return {"error": f"{color!r} isn't one of the colors: {', '.join(COLORS)}."}
    prefs = load()
    if color == "none":
        prefs["colors"].pop(app, None)
    else:
        prefs["colors"][app] = color
    _save(prefs)
    return {"name": app, "color": prefs["colors"].get(app)}


def set_pinned(app: str, pinned: bool) -> dict[str, Any]:
    if not _NAME.match(app):
        return {"error": f"No app called {app!r}."}
    prefs = load()
    prefs["pinned"] = [p for p in prefs["pinned"] if p != app] + ([app] if pinned else [])
    _save(prefs)
    return {"pinned": prefs["pinned"]}


def decorate(apps: list[dict[str, Any]], glyph=lambda name: None, image=lambda name: None) -> list[dict[str, Any]]:
    """Each app with its ``icon`` (picked, else its own ``meta.glyph`` if that's in the kit, else null; ``image`` is its
    own image, only while it has one), ``image`` (a stamp of that image, which changes with it, for /talaria app-image;
    null without one), ``color`` (picked, or null) and ``pinned`` (its place among the pins, from 0, or null)."""
    prefs = load()
    for a in apps:
        path = image(a["name"])
        try:
            a["image"] = hashlib.sha1(path.read_bytes()).hexdigest()[:12] if path else None
        except OSError:
            a["image"] = None
        kit = ICONS + ((IMAGE,) if a["image"] else ())
        own = glyph(a["name"])
        picked = prefs["icons"].get(a["name"])
        a["icon"] = (picked if picked in kit else None) or (own if own in kit else None)
        a["color"] = prefs["colors"].get(a["name"])
        a["pinned"] = prefs["pinned"].index(a["name"]) if a["name"] in prefs["pinned"] else None
    return apps
