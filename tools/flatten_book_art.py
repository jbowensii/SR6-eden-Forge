"""Bring a book's extracted graphics up out of ``_inbox`` and name the ones we can.

The extractor drops every image it lifts off a page into ``<book>/_inbox/`` and
names it after where it came from — ``p254_x4595.webp`` is page 254, PDF object
4595. That is a provenance record, not a name, and it made the graphics browser
a wall of identical-looking filenames.

Two things happen here:

* every file moves up one level, into ``<book>/``, and the emptied ``_inbox``
  is removed. Since the downloaded art that used to live at that level is gone,
  a book directory now holds exactly what came out of that book.
* a file that an item actually points at gets the item's name put in front of
  the one it already has — ``ares_predator_vi_p254_x4595.webp``. The original
  name is kept whole: it is the only thread back to the page the picture came
  from, and it keeps two pictures of one subject from colliding.

Most files cannot be renamed. Of 1,867 graphics only 26 have an item pointing at
them; the rest are unpaired, and inventing a name for a picture nobody has
identified would be worse than leaving the honest one.

Every reference moves with the file — item ``img``, ``meta.render``, and the
correction records, which are re-applied after each import and would otherwise
point at the old path forever.

    python tools/flatten_book_art.py --dry-run
    python tools/flatten_book_art.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                 # noqa: E402

#: Not books — the shared icon pools.
NOT_BOOKS = {"generic", "iconsets"}

def slug(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (name or "").casefold())).strip("_")


def item_names(data: _P) -> dict[str, str]:
    """asset path -> the name of an item that points at it."""
    out: dict[str, str] = {}
    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for path in book.rglob("*.json"):
            for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
                for ref in (item.get("img"), (item.get("meta") or {}).get("render")):
                    if ref and ref not in out and item.get("name"):
                        out[ref] = item["name"]
    return out


def repoint(data: _P, moved: dict[str, str]) -> tuple[int, int]:
    items = corrections = 0
    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for path in book.rglob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            dirty = False
            for item in payload.get("items", []):
                meta = item.setdefault("meta", {})
                for field, obj in (("img", item), ("render", meta)):
                    if obj.get(field) in moved:
                        obj[field] = moved[obj[field]]
                        items += 1
                        dirty = True
            if dirty:
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
    for path in (data / "_corrections").rglob("*.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        dirty = False
        for field, obj in (("img", doc), ("render", doc.get("meta") or {})):
            if obj.get(field) in moved:
                obj[field] = moved[obj[field]]
                dirty = True
        if dirty:
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            corrections += 1
    return items, corrections


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = args.data or data_root()
    assets = data / "_assets"
    names = item_names(data)

    moved: dict[str, str] = {}
    renamed = 0
    for book in sorted(d for d in assets.iterdir() if d.is_dir() and d.name not in NOT_BOOKS):
        inbox = book / "_inbox"
        if not inbox.is_dir():
            continue
        taken = {p.name for p in book.iterdir() if p.is_file()}
        for src in sorted(p for p in inbox.iterdir() if p.is_file()):
            rel = src.relative_to(assets).as_posix()
            stem, ext = src.stem, src.suffix
            title = names.get(rel)
            if title and slug(title):
                # the item's name in FRONT, the original name kept whole behind
                # it: "ares_predator_vi_p254_x4595". The page and object id are
                # the only thread back to where the picture came from, and two
                # pictures of one subject would collide without them.
                stem = f"{slug(title)}_{stem}"
                renamed += 1
            candidate, n = f"{stem}{ext}", 2
            while candidate in taken:
                candidate, n = f"{stem}_{n}{ext}", n + 1
            taken.add(candidate)
            moved[rel] = f"{book.name}/{candidate}"
            if not args.dry_run:
                src.rename(book / candidate)
        if not args.dry_run:
            try:
                inbox.rmdir()
            except OSError as e:
                print(f"  ! {inbox} not empty: {e}")

    print(f"library: {data}")
    print(f"{len(moved)} graphic(s) moved up out of _inbox, {renamed} renamed after their item")
    if args.dry_run:
        for rel, new in list(moved.items())[:8]:
            if rel.split("/")[-1] != new.split("/")[-1]:
                print(f"    {rel}  ->  {new}")
        print("\n(dry run — nothing written)")
        return 0

    items, corrections = repoint(data, moved)
    print(f"repointed {items} item reference(s) and {corrections} correction(s)")
    left = [d / "_inbox" for d in assets.iterdir()
            if d.is_dir() and (d / "_inbox").is_dir()]
    print(f"_inbox directories remaining: {len(left)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
