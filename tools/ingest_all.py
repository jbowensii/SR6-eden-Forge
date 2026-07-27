"""Rebuild the whole library with the unified one-pass ingest. corebook (the
curated seed) is processed first for its hierarchy pass; every other gear book
is then read in publication-date order by the single ingest_book pipeline
(extraction + de-mangle + special readers + subtypes + descriptions +
prose-only), city editions last as reprints."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.ingest import ingest_book, load_registry

DATA = _P("data")
reg = load_registry(DATA)
ZERO = {"companion", "street_wyrd", "gun_rack", "rides"}  # measured 0 gear

order = [(k, v.get("date", ""), bool(v.get("reprint_of")))
         for k, v in reg.items() if k not in ZERO]
order.sort(key=lambda t: (t[0] != "corebook", t[2], t[1]))  # corebook, then date, reprints last

print(f"{'book':22} {'new':>4} {'ref':>4} {'var':>4} {'sub+':>5} {'sub~':>5} {'desc':>5} {'prose':>6}")
tot = {"new": 0, "referenced": 0, "variants": 0, "subtypes_filled": 0,
       "subtypes_corrected": 0, "descriptions": 0, "prose_only": 0}
for book, _date, reprint in order:
    try:
        st = ingest_book(DATA, book)
    except SystemExit as e:
        print(f"{book:22} SKIP: {e}")
        continue
    for k in tot:
        tot[k] += st.get(k, 0)
    tag = "(reprint)" if reprint else ""
    print(f"{book:22} {st['new']:>4} {st['referenced']:>4} {st['variants']:>4} "
          f"{st['subtypes_filled']:>5} {st['subtypes_corrected']:>5} {st['descriptions']:>5} "
          f"{st['prose_only']:>6}  {tag}")

print(f"\nTOTALS new={tot['new']} ref={tot['referenced']} var={tot['variants']} "
      f"subtypes(filled={tot['subtypes_filled']} corrected={tot['subtypes_corrected']}) "
      f"descriptions={tot['descriptions']} prose-only={tot['prose_only']}")
