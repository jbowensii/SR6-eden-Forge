"""Adopt shadowrun6-eden type/subtype codes post-import. The canonical map lives
in site/shared/eden_codes.json (shared with the web UI). `map_code` remaps a
(type, subtype) pair to Eden's vocabulary; anything not in the remap is identity.
The original Commlink6 codes remain untouched under item.system._cl6."""
from __future__ import annotations

import json
from pathlib import Path

_PATH = Path("site/shared/eden_codes.json")
_DATA = None


def _load():
    global _DATA
    if _DATA is None:
        try:
            _DATA = json.loads(_PATH.read_text(encoding="utf-8"))
        except Exception:
            _DATA = {"remap": {}, "vocab": {"subtypes": []}}
    return _DATA


def map_code(type_: str, subtype: str):
    """Return the Eden (type, subtype) for our (type, subtype)."""
    remap = _load().get("remap", {})
    hit = remap.get(f"{type_ or ''}/{subtype or ''}")
    if hit:
        return hit[0], hit[1]
    return type_, subtype


def eden_subtypes() -> set:
    return set(_load().get("vocab", {}).get("subtypes", []))
