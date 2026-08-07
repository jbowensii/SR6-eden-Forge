"""Assign icons from the user's icon sets to every item that has no art.

The icon library was configurable and was recorded correctly, but nothing in
the import ever read it: the matcher existed and was simply never called, so a
fresh library came out with art only on the ~110 items whose illustrations were
lifted out of the PDFs. Choosing a folder appeared to do nothing.

Runs over every book and domain. Idempotent: an item that already has an image
is left alone, so a re-import never overwrites art the user assigned by hand,
and re-running only fills what is still empty.

    python tools/match_icons_all.py                 # uses settings.json
    python tools/match_icons_all.py --library D:\\icons --min-score 4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.icon_match import match_icons          # noqa: E402
from extractor.paths import data_root                 # noqa: E402


def configured_library(data: _P) -> str:
    """The icon folder the builder recorded, if any.

    Same file the review app reads, so the folder chosen in the window and the
    folder used by the import are the same folder by construction.
    """
    try:
        settings = json.loads((data / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    value = settings.get("iconLibrary")
    if isinstance(value, list):                  # the review app allows a list
        value = value[0] if value else ""
    return str(value or "")


def domains_of(data: _P) -> list[tuple[str, str]]:
    """Every ``(book, domain)`` pair present in the library."""
    out = []
    for book in sorted(p for p in data.iterdir()
                       if p.is_dir() and not p.name.startswith("_")):
        for domain in sorted(d for d in book.iterdir() if d.is_dir()):
            out.append((book.name, domain.name))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--library", default="",
                    help="icon sets folder (default: whatever the builder saved)")
    ap.add_argument("--min-score", type=int, default=3)
    args = ap.parse_args()

    data = args.data or data_root()
    library = args.library or configured_library(data)
    if not library:
        print("no icon folder configured — skipping "
              "(set one in the builder, step 5)")
        return 0
    if not _P(library).is_dir():
        print(f"icon folder not found: {library} — skipping")
        return 0

    pairs = domains_of(data)
    print(f"matching icons from {library} over {len(pairs)} book/domain pair(s)")

    total = 0
    for book, domain in pairs:
        try:
            stats = match_icons(_P(library), data, book, domain, args.min_score)
        except Exception as e:            # one domain must not lose the rest
            print(f"  {book}/{domain}: {type(e).__name__}: {e}")
            continue
        n = stats.get("assigned", 0) if isinstance(stats, dict) else 0
        if n:
            total += n
            print(f"  {book}/{domain}: +{n}")

    print(f"assigned {total} icon(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
