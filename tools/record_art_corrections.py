"""Put artwork choices into the corrections layer, where a re-import can find them.

The library is rebuilt from the books on every import and the ONLY reason a
manual choice is still there afterwards is a correction record. Anything written
straight into a category file is temporary, however permanent it looks.

Two things got in that way and would not have survived the next import:

* ``meta.render`` backfilled onto the items that already had a book graphic on
  disk, so their render slot would work again, and
* ``meta.icon``, which records the icon a graphic displaced.

This records the current value of those fields for any item whose correction
does not already carry them. It writes the whole item, which is the shape the
correction layer stores and ``tools/apply_corrections.py`` expects.

    python tools/record_art_corrections.py --dry-run
    python tools/record_art_corrections.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                 # noqa: E402

#: What we are protecting. Fields on meta that a rebuild cannot re-derive,
#: because they record a human choice about a picture.
ART_META = ("render", "icon")

#: An `img` that is a shared icon. Those ARE re-derived every import by the icon
#: phases, so recording them would only add noise; a picture from a book is not
#: re-derived and is exactly what gets lost.
SHARED_ICON = ("generic/", "iconsets/")


def book_art(item) -> str:
    """The item's `img`, if it is a picture from a book rather than an icon.

    This was the gap that cost 53 pairings. The ingest phases rewrite a domain's
    whole JSON from the books, and `img` is not something the extractor
    produces — so it is dropped, and the icon phases then fill the empty slot
    with a category icon. Only a correction survives that, and pair_book_art.py
    wrote none.
    """
    img = str(item.get("img") or "")
    if not img or img.startswith(SHARED_ICON) or "/lib/" in img:
        return ""
    return img


def existing(data: _P) -> dict[str, dict]:
    out = {}
    for p in (data / "_corrections").rglob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("id"):
            out[d["id"]] = d
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = args.data or data_root()
    have = existing(data)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    written = 0

    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for domain in sorted(d for d in book.iterdir() if d.is_dir()):
            for path in sorted(domain.glob("*.json")):
                for item in json.loads(path.read_text(encoding="utf-8")).get("items", []):
                    meta = item.get("meta") or {}
                    mine = {k: meta[k] for k in ART_META if meta.get(k)}
                    art = book_art(item)
                    if not mine and not art:
                        continue
                    known = have.get(item["id"]) or {}
                    prior = known.get("meta") or {}
                    if (all(prior.get(k) == v for k, v in mine.items())
                            and (not art or known.get("img") == art)):
                        continue            # already protected
                    record = json.loads(json.dumps(item))
                    record.update(domain=domain.name, category=path.stem,
                                  id=item["id"], correctedAt=stamp)
                    dest = data / "_corrections" / domain.name / f"{item['id']}.json"
                    written += 1
                    if not args.dry_run:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")

    print(f"library: {data}")
    print(f"{written} artwork choice(s) recorded as corrections")
    print("   (book-art img, meta.render and meta.icon — the three a rebuild drops)")
    if args.dry_run:
        print("(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
