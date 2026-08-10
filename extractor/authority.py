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

import copy
import json
from pathlib import Path

COMMLINK6 = "commlink6"

#: book folder used when a phase deleted a file and its envelope with it
LIBRARY_FALLBACK = "corebook"

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
    """Everything needed to put a Commlink6 row back exactly as it was.

    ``{"fields": {id: {field: value}}, "rows": {file: [whole row, ...]}}``

    Whole rows are kept, not just fields, because a phase can DELETE a record
    rather than merely edit it — ``ingest_vehicles`` rewrites the vehicles file
    wholesale from its own reading, destroying every Commlink6 vehicle in it.
    Restoring fields cannot help a row that is no longer there.

    They are keyed by FILE and kept as a list, not keyed by id, because
    Commlink6 reuses ids: 385 vehicle rows share only 356 of them. An id-keyed
    store drops one of each colliding pair, which is how 29 vehicles stayed
    dead after the guard reported them restored.
    """

    fields: dict[str, dict] = {}
    rows: dict[str, list] = {}
    root = Path(data_root)
    for f in _library_files(root):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rel = f.relative_to(root).as_posix()
        for item in doc.get("items") or []:
            if not is_authoritative(item) or not item.get("id"):
                continue
            sysd = item.get("system") or {}
            kept = {k: sysd[k] for k in GUARDED
                    if k in sysd and _filled(sysd[k])}
            # Effects live at the TOP level, not under system, so the loop above
            # cannot see them. They are Commlink6's statement of what an item
            # does; a phase that rewrites an item without them would silently
            # revert every modifier to nothing.
            if item.get("effects"):
                kept["__effects"] = copy.deepcopy(item["effects"])
            fields.setdefault(item["id"], kept)
            # EVERY row, not one per id. Commlink6 reuses an id across rows —
            # 385 vehicle rows share only 356 ids — so an id-keyed store
            # silently discards one of each colliding pair, and 29 vehicles
            # stayed dead after the guard "restored" them.
            rows.setdefault(rel, []).append(copy.deepcopy(item))
    return {"fields": fields, "rows": rows}


def restore(data_root: Path, snap: dict[str, dict]) -> dict:
    """Put back anything the phases changed on a Commlink6 row.

    :returns: ``{"restored": n, "items": n, "fields": {field: n}}``
    """
    from collections import Counter

    root = Path(data_root)
    want_fields = snap.get("fields") or {}
    want_rows = snap.get("rows") or {}
    restored = 0
    touched_items = 0
    per_field: Counter = Counter()

    # pass 1 — put back any field a phase changed on a row that still exists
    for f in _library_files(root):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = doc.get("items")
        if not isinstance(items, list):
            continue
        dirty = False
        for item in items:
            if not is_authoritative(item):
                continue
            was = want_fields.get(item.get("id"))
            if not was:
                continue
            sysd = item.setdefault("system", {})
            hit = False
            for field, value in was.items():
                if field == "__effects":                 # top level, not system
                    if item.get("effects") != value:
                        item["effects"] = copy.deepcopy(value)
                        per_field["effects"] += 1
                        restored += 1
                        hit = True
                    continue
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

    # pass 2 — bring back rows a phase removed.
    #
    # Counted per id, not matched as a set: Commlink6 reuses ids, so "is this
    # id present?" is the wrong question. The right one is "did this file hold
    # THREE rows with this id before and only one now?"
    resurrected = 0
    for rel, before in want_rows.items():
        path = root / rel
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # the phase deleted the file too; rebuild its envelope
            parts = Path(rel).parts
            doc = {"book": parts[0] if parts else LIBRARY_FALLBACK,
                   "domain": parts[1] if len(parts) > 1 else "gear",
                   "category": Path(rel).stem, "items": []}
        if not isinstance(doc.get("items"), list):
            doc["items"] = []

        now = Counter(i.get("id") for i in doc["items"]
                      if is_authoritative(i))
        need = Counter(i.get("id") for i in before)
        missing = need - now                     # multiset difference
        if not missing:
            continue

        for row in before:
            rid = row.get("id")
            if missing.get(rid, 0) > 0:
                doc["items"].append(row)
                missing[rid] -= 1
                resurrected += 1

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    return {"restored": restored, "items": touched_items,
            "fields": dict(per_field), "resurrected": resurrected}
