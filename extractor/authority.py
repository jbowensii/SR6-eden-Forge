"""Commlink6 is the source of truth. Derived passes may enhance it, never replace it.

The post-merge phases — description extractors, type repairs, subtype
inference — were all written when the library came only from PDFs. They edit
items in place and none of them has ever heard of Commlink6. Left alone they
will happily overwrite an authoritative value with a guess:
``rebuild_descriptions`` assigns ``item["system"]["description"] = new``
unconditionally, and when the page yields nothing ``new`` is ``""`` — so a
Commlink6 description is not merely replaced, it is erased.

Rather than patch ten scripts and trust that the eleventh remembers, the rule
is enforced around them. :func:`snapshot` records every non-empty field of
every Commlink6 row before the phases run; :func:`restore` puts back anything
they changed afterwards.

The asymmetry is the whole point:

* a field Commlink6 filled  -> restored, whatever a phase did to it
* a field Commlink6 left empty -> whatever a phase wrote is KEPT

which is exactly "never clobber, only enhance". A phase that fills a gap is
doing its job; a phase that overwrites the authority is not.
"""
from __future__ import annotations

import json
from pathlib import Path

COMMLINK6 = "commlink6"

#: Fields a derived pass has any business touching. Everything else on a
#: Commlink6 row is structural and nothing downstream writes it.
GUARDED = ("description", "type", "subtype", "notes", "category",
           "price", "avail", "rating", "essence", "capacity")


def is_authoritative(item: dict) -> bool:
    """Did this row come from Commlink6?"""
    return ((item or {}).get("meta") or {}).get("source") == COMMLINK6


def _filled(value) -> bool:
    """Did Commlink6 actually say something here?"""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True                      # 0 and False are real values


def _library_files(data_root: Path):
    root = Path(data_root)
    if not root.is_dir():
        return
    for book in sorted(root.iterdir()):
        if not book.is_dir() or book.name.startswith("_"):
            continue
        for domain in sorted(book.iterdir()):
            if not domain.is_dir():
                continue
            yield from sorted(domain.glob("*.json"))


def snapshot(data_root: Path) -> dict[str, dict]:
    """``{item id: {field: value}}`` for every non-empty Commlink6 field."""
    snap: dict[str, dict] = {}
    for f in _library_files(data_root):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in doc.get("items") or []:
            if not is_authoritative(item):
                continue
            sysd = item.get("system") or {}
            kept = {k: sysd[k] for k in GUARDED
                    if k in sysd and _filled(sysd[k])}
            if kept and item.get("id"):
                snap[item["id"]] = kept
    return snap


def restore(data_root: Path, snap: dict[str, dict]) -> dict:
    """Put back anything the phases changed on a Commlink6 row.

    :returns: ``{"restored": n, "items": n, "fields": {field: n}}``
    """
    from collections import Counter

    restored = 0
    touched_items = 0
    per_field: Counter = Counter()

    for f in _library_files(data_root):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = doc.get("items")
        if not isinstance(items, list):
            continue
        dirty = False
        for item in items:
            was = snap.get(item.get("id"))
            if not was:
                continue
            sysd = item.setdefault("system", {})
            hit = False
            for field, value in was.items():
                if sysd.get(field) != value:
                    sysd[field] = value
                    per_field[field] += 1
                    restored += 1
                    hit = True
            if hit:
                touched_items += 1
                dirty = True
        if dirty:
            f.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                         encoding="utf-8")

    return {"restored": restored, "items": touched_items,
            "fields": dict(per_field)}
