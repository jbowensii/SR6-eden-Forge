"""Work out how far each book's printed page numbers sit from its PDF pages.

An item records the page PRINTED on the page it came from, which is what you
want in a citation and is not what a PDF viewer counts. Covers, credits and a
table of contents push the two apart, so "Open PDF - p. 58" opened page 58 of
the file and showed printed page 57, or 54, depending on the book.

The offset is measured, not assumed: for a sample of pages the printed folio is
read off the page itself, and the difference from the physical index is taken.
A book only gets an offset if the sample agrees with itself, so a book whose
folios cannot be read is left alone rather than shifted by a guess.

Writes ``pageOffset`` into books.json next to each book's pdf path. The review
app adds it when building the link; nothing else reads it.

    python tools/detect_page_offsets.py --dry-run
    python tools/detect_page_offsets.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                 # noqa: E402

#: Pages to sample. Early pages are front matter with no folio; late ones are
#: indexes and adverts. The middle of a book is where the numbering is honest.
_FRACTIONS = (0.25, 0.35, 0.45, 0.55, 0.65, 0.75)

#: A folio is a small number alone on its line, at the top or bottom of the page.
_FOLIO = re.compile(r"^\s*(\d{1,3})\s*$")


def _folios(page) -> list[int]:
    """Every number standing alone on a line — candidates for the printed folio.

    Looking only at the first and last couple of lines missed it on most books:
    the folio is its own text line but not reliably the first or last one, so
    Double Clutch and the core rulebook both came back "no page numbers found"
    when their offset is plainly +1. Every candidate is returned instead and the
    ambiguity is settled by voting across pages — the real offset repeats on
    every sample, a stray number does not.
    """
    out = []
    for line in (page.extract_text() or "").splitlines():
        m = _FOLIO.match(line)
        if m:
            out.append(int(m.group(1)))
    return out


def offset_for(pdf_path: str) -> tuple[int | None, str]:
    """``(offset, why)`` — physical page = printed page + offset."""
    import pdfplumber

    try:
        with pdfplumber.open(pdf_path) as pdf:
            n = len(pdf.pages)
            votes = Counter()
            for f in _FRACTIONS:
                idx = max(1, min(n, round(n * f)))
                for folio in _folios(pdf.pages[idx - 1]):
                    if abs(idx - folio) <= 30:
                        votes[idx - folio] += 1
    except Exception as e:                              # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"
    if not votes:
        return None, "no page numbers found"
    off, hits = votes.most_common(1)[0]
    # two independent samples must agree, or we are reading something that is
    # not a folio and would shift every citation in the book
    # the true offset shows up on nearly every sampled page; a stray number that
    # happened to sit alone on a line does not. Require a clear majority, not
    # just a plurality, or a book with two candidates gets shifted on a coin toss
    if hits < 3 or hits < 2 * (sum(votes.values()) - hits):
        return None, f"inconsistent ({dict(votes.most_common(4))})"
    return off, f"{hits}/{sum(votes.values())} samples agree"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = args.data or data_root()
    path = data / "books.json"
    books = json.loads(path.read_text(encoding="utf-8"))

    changed = 0
    for slug in sorted(books):
        entry = books[slug]
        pdf = entry.get("pdf")
        if not pdf or not _P(pdf).is_file():
            continue
        off, why = offset_for(pdf)
        if off is None:
            print(f"  {slug:24} —      {why}")
            continue
        print(f"  {slug:24} {off:+3}    {why}")
        if entry.get("pageOffset") != off:
            entry["pageOffset"] = off
            changed += 1

    print(f"\n{changed} book(s) updated")
    if changed and not args.dry_run:
        path.write_text(json.dumps(books, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path}")
    elif args.dry_run:
        print("(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
