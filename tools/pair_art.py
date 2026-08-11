"""Auto-pair extracted book graphics to items.

An image is assigned only when its (book, page) has exactly ONE item still
lacking art and exactly ONE image — an unambiguous pairing. Never overwrites
existing art. Runs after the graphics phase.

Three things had this reporting "auto-paired 0" as though it were a result:

* it globbed ``data/...`` relative to the working directory instead of asking
  ``data_root()``, so from the installed app it read a directory that is not the
  library — the same stale-library bug that hit four other tools;
* it looked in ``_assets/<book>/_inbox/``, a layout that no longer exists; and
* it matched ``*.png`` only, on a library that is entirely WebP.

The fourth was not a bug in this file. Flat storage threw the book away —
``p048_x1029.webp`` could be from any of fifty PDFs — so a (book, page) key
cannot be recovered from the filename. dump_book_images now records
``_assets/_index.json`` mapping each file to the book and page it came from,
which is the only reason this phase can work at all.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root          # noqa: E402

DATA = data_root()
LIBRARY = "corebook"


def load_index(assets):
    """filename -> (book, page), written by dump_book_images."""
    try:
        raw = json.loads((assets / "_index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for name, val in raw.items():
        if isinstance(val, (list, tuple)) and len(val) == 2:
            try:
                out[name] = (str(val[0]), int(val[1]))
            except (TypeError, ValueError):
                continue
    return out


def main():
    assets = DATA / "_assets"
    index = load_index(assets)

    # (book, page) -> [(file, item)] for items with no art yet
    by_page = defaultdict(list)
    files = {}
    for path in sorted((DATA / LIBRARY).glob("*/*.json")):
        if path.name.startswith("_") or path.parent.name.startswith("_"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        files[path] = payload
        for it in payload.get("items", []):
            if it.get("img"):
                continue
            meta = it.get("meta") or {}
            book, page = meta.get("book"), meta.get("page")
            if book and page:
                try:
                    by_page[(str(book), int(page))].append((path, it))
                except (TypeError, ValueError):
                    continue

    # (book, page) -> [image filenames]
    imgs = defaultdict(list)
    for name, (book, page) in index.items():
        if (assets / name).is_file():
            imgs[(book, page)].append(name)
    if not index:
        # A missing index is not "nothing to pair" — it means the graphics phase
        # has not recorded anything yet, and pairing silently does nothing.
        for path in assets.glob("*.webp"):
            m = re.search(r"p(\d+)_x\d+", path.name)
            if m:
                imgs[("?", int(m.group(1)))].append(path.name)
        print("  ! no _assets/_index.json — run the Book graphics phase so each "
              "file records the book it came from; pairing needs it")

    paired, dirty = 0, set()
    for key, items in by_page.items():
        pics = imgs.get(key, [])
        if len(items) == 1 and len(pics) == 1:
            path, it = items[0]
            it["img"] = pics[0]
            dirty.add(path)
            paired += 1

    for path in dirty:
        path.write_text(json.dumps(files[path], indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print(f"library: {DATA}")
    print(f"indexed graphics: {len(index)}   pages with art: {len(imgs)}   "
          f"items lacking art: {sum(len(v) for v in by_page.values())}")
    print(f"auto-paired {paired} item(s) to extracted art")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
