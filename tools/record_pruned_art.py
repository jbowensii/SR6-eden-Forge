"""Record which extracted graphics were thrown away, so a re-import leaves them out.

``dump_book_images.py`` decides what to skip by asking whether the file is
already on disk. That makes deletion meaningless: an illustration judged useless
and removed comes straight back on the next import, and an afternoon spent
pruning is undone in a phase that reports success.

The ledger is the missing memory. It lists the graphics that WERE extracted and
are no longer here, keyed by page and PDF object id — ``p003_x4714`` — because
that key survives everything we do to the file afterwards: flattening the
folders, prefixing the item name, converting to WebP.

Run it after pruning by hand. It compares what the PDFs offer against what is
still in ``_assets`` and writes the difference to ``_assets/_pruned.json``.
Anything currently on disk is, by definition, not pruned — so a graphic restored
later simply drops out of the ledger on the next run.

    python tools/record_pruned_art.py --dry-run
    python tools/record_pruned_art.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                 # noqa: E402

LEDGER = "_pruned.json"

#: the page/object key inside a filename, wherever it sits: "p003_x4714.webp"
#: and "ares_predator_vi_p254_x4595.webp" both yield the key.
KEY = re.compile(r"p(\d{2,4})_x(\d+)")

#: Same thresholds dump_book_images.py applies, so the two agree on what counts
#: as an extractable graphic. Out of step, the ledger would list images that were
#: never extracted in the first place.
MIN_DIM = 150
MAX_COVER = 0.90
SKIP_BOOKS = {"gun_rack", "rides"}


def present(assets: _P) -> set[str]:
    """Keys for every graphic still on disk, wherever it now lives."""
    out = set()
    for p in assets.rglob("*"):
        if not p.is_file() or "generic" in p.parts or "iconsets" in p.parts:
            continue
        m = KEY.search(p.stem)
        if m:
            out.add(f"p{int(m.group(1)):03d}_x{m.group(2)}")
    return out


def offered(pdf_path: str) -> set[str]:
    """Keys for every graphic this PDF would yield."""
    import fitz

    out = set()
    with fitz.open(pdf_path) as doc:
        for pno in range(doc.page_count):
            page = doc[pno]
            parea = abs(page.rect) or 1.0
            for img in page.get_images(full=True):
                xref, w, h = img[0], img[2], img[3]
                if w < MIN_DIM or h < MIN_DIM:
                    continue
                rects = page.get_image_rects(xref)
                if rects and (abs(rects[0]) / parea) > MAX_COVER:
                    continue
                out.add(f"p{pno + 1:03d}_x{xref}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = args.data or data_root()
    assets = data / "_assets"
    books = json.loads((data / "books.json").read_text(encoding="utf-8"))
    here = present(assets)

    ledger: dict[str, list[str]] = {}
    for slug in sorted(books):
        pdf = books[slug].get("pdf")
        if slug in SKIP_BOOKS or not pdf or not _P(pdf).is_file():
            continue
        try:
            gone = sorted(offered(pdf) - here)
        except Exception as e:                          # noqa: BLE001
            print(f"  {slug:24} skipped — {type(e).__name__}: {e}")
            continue
        if gone:
            ledger[slug] = gone
            print(f"  {slug:24} {len(gone):4} pruned")

    total = sum(len(v) for v in ledger.values())
    print(f"\n{total} pruned graphic(s) across {len(ledger)} book(s); {len(here)} still present")
    if args.dry_run:
        print("(dry run — nothing written)")
        return 0
    path = assets / LEDGER
    path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
