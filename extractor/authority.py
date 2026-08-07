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
    """Everything needed to put a Commlink6 row back exactly as it was.

    ``{id: {"fields": {...}, "item": <whole row>, "file": <relative path>}}``

    The whole row is kept, not just its fields, because a phase can DELETE a
    Commlink6 record rather than merely edit it — ``ingest_vehicles`` rewrites
    the vehicles file wholesale from its own reading, which silently dropped
    366 Commlink6 vehicles. Restoring fields cannot help an item that is no
    longer there, and deleting is the most complete form of clobbering there
    is, so the row itself has to be recoverable.
    """
    import copy

    snap: dict[str, dict] = {}
    root = Path(data_root)
    for f in _library_files(root):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for item in doc.get("items") or []:
            if not is_authoritative(item) or not item.get("id"):
                continue
            sysd = item.get("system") or {}
            kept = {k: sysd[k] for k in GUARDED
                    if k in sysd and _filled(sysd[k])}
            snap[item["id"]] = {
                "fields": kept,
                "item": copy.deepcopy(item),
                "file": f.relative_to(root).as_posix(),
            }
    return snap


def restore(data_root: Path, snap: dict[str, dict]) -> dict:
    """Put back anything the phases changed on a Commlink6 row.

    :returns: ``{"restored": n, "items": n, "fields": {field: n}}``
    """
    from collections import Counter

    root = Path(data_root)
    restored = 0
    touched_items = 0
    per_field: Counter = Counter()
    survived: set[str] = set()

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
            was = snap.get(item.get("id"))
            if not was:
                continue
            survived.add(item["id"])
            sysd = item.setdefault("system", {})
            hit = False
            for field, value in was["fields"].items():
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

    # pass 2 — bring back rows a phase deleted outright, to the file they came
    # from. Grouped so each file is rewritten once however many rows it lost.
    gone = [i for i in snap if i not in survived]
    by_file: dict[str, list] = {}
    for item_id in gone:
        by_file.setdefault(snap[item_id]["file"], []).append(snap[item_id]["item"])

    resurrected = 0
    for rel, rows in by_file.items():
        path = root / rel
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # the phase removed the file as well; rebuild its envelope
            parts = Path(rel).parts
            doc = {"book": parts[0] if parts else "corebook",
                   "domain": parts[1] if len(parts) > 1 else "gear",
                   "category": Path(rel).stem, "items": []}
        if not isinstance(doc.get("items"), list):
            doc["items"] = []
        have = {i.get("id") for i in doc["items"]}
        for row in rows:
            if row.get("id") not in have:
                doc["items"].append(row)
                resurrected += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    return {"restored": restored, "items": touched_items,
            "fields": dict(per_field), "resurrected": resurrected}
