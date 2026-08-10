"""Pair each extracted graphic to the item it illustrates, and name it after it.

The extractor names a graphic for where it came from — ``p254_x4595.png`` is
page 254, PDF object 4595. That is provenance, not a name, and a gallery of them
is a wall of identical-looking files.

Pairing is by page and deliberately conservative: a graphic is claimed only when
its (book, page) has exactly ONE item still lacking art. Two candidates on a
page means we cannot tell which the picture shows, and a wrong picture attached
confidently is worse than an unpaired one. Most graphics stay unpaired for that
reason, and that is the honest outcome — a book page carries far more art than
it carries items.

A paired file is renamed ``<item>_p<page>_x<object>.png``: the item's name in
front, the original name kept whole behind it. The page and object id are the
only thread back to where the picture came from, and they keep two pictures of
one subject from colliding.

Supersedes ``tools/pair_art.py``, which assumed the graphics sat in ``_inbox``
and read ``data/`` directly — the developer's scratch copy, not the library the
installed builder manages.

    python tools/name_book_art.py --dry-run
    python tools/name_book_art.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                 # noqa: E402

NOT_BOOKS = {"generic", "iconsets"}
#: "p254_x4595" — the page and PDF object id the extractor stamps on every file.
TAG = re.compile(r"(?:^|_)p(\d{2,4})_x(\d+)$")


def slug(name: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (name or "").casefold())).strip("_")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = args.data or data_root()
    assets = data / "_assets"

    # every graphic, keyed by the (book, page) it was lifted from
    graphics: dict[tuple[str, int], list[_P]] = defaultdict(list)
    total = 0
    for book in sorted(d for d in assets.iterdir() if d.is_dir() and d.name not in NOT_BOOKS):
        for p in sorted(book.glob("*")):
            if not p.is_file():
                continue
            m = TAG.search(p.stem)
            if m:
                graphics[(book.name, int(m.group(1)))].append(p)
                total += 1

    # every item still without a picture, keyed the same way
    wanting: dict[tuple[str, int], list[tuple[_P, dict]]] = defaultdict(list)
    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for path in book.rglob("*.json"):
            for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
                meta = item.get("meta") or {}
                if item.get("img") or not meta.get("book") or not meta.get("page"):
                    continue
                wanting[(meta["book"], int(meta["page"]))].append((path, item))

    paired = {}
    for key, files in graphics.items():
        items = wanting.get(key, [])
        # one picture, one item wanting one: an unambiguous pairing
        if len(files) == 1 and len(items) == 1:
            paired[files[0]] = items[0]

    print(f"library: {data}")
    print(f"{total} graphics across {len({k[0] for k in graphics})} books")
    print(f"{len(paired)} paired to an item unambiguously "
          f"({total - len(paired)} left with their page name)")

    renames: dict[str, str] = {}
    for src, (_, item) in sorted(paired.items(), key=lambda kv: str(kv[0])):
        s = slug(item.get("name"))
        if not s:
            continue
        dest = src.with_name(f"{s}_{src.stem.split('_p')[-1] if '_p' in src.stem else src.stem}{src.suffix}")
        dest = src.with_name(f"{s}_{src.stem}{src.suffix}") if not src.stem.startswith(s) else src
        if dest == src or dest.exists():
            continue
        renames[src.relative_to(assets).as_posix()] = dest.relative_to(assets).as_posix()
        if not args.dry_run:
            src.rename(dest)

    if args.dry_run:
        for a, b in list(renames.items())[:8]:
            print(f"    {a}  ->  {b}")
        print("\n(dry run — nothing written)")
        return 0

    # point the items at their picture
    assigned = 0
    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for path in book.rglob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            dirty = False
            for item in payload.get("items", []):
                meta = item.get("meta") or {}
                if item.get("img") or not meta.get("book") or not meta.get("page"):
                    continue
                for src, (_, want) in paired.items():
                    if want.get("id") != item.get("id"):
                        continue
                    rel = src.relative_to(assets).as_posix()
                    item["img"] = renames.get(rel, rel)
                    assigned += 1
                    dirty = True
                    break
            if dirty:
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                encoding="utf-8")
    print(f"renamed {len(renames)} file(s); {assigned} item(s) now show their book art")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
