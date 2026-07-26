"""Ingest every gear-bearing book into the live library in publication-date
order (earliest first so it becomes the variant base), city editions last as
reprints. corebook and firing_squad are already merged; skipped here."""
from pathlib import Path
from extractor.ingest import ingest_book, load_registry

DATA = Path("data")
reg = load_registry(DATA)

# already merged into the live library
ALREADY = {"corebook", "firing_squad"}
# zero-yield or non-gear (measured); skip to save time but list for the report
ZERO = {"companion", "street_wyrd", "gun_rack", "rides"}

books = [(k, v.get("date", ""), bool(v.get("reprint_of")))
         for k, v in reg.items() if k not in ALREADY and k not in ZERO]
# non-reprints first (date asc), then reprints (date asc)
books.sort(key=lambda t: (t[2], t[1]))

print(f"{'book':22} {'new':>4} {'ref':>4} {'var':>4} {'skip':>5} {'detected':>8}")
totals = {"new": 0, "referenced": 0, "variants": 0, "skipped": 0}
for book, date, reprint in books:
    try:
        st = ingest_book(DATA, book)
    except SystemExit as e:
        print(f"{book:22} SKIP: {e}")
        continue
    for k in totals:
        totals[k] += st.get(k, 0)
    tag = "(reprint)" if reprint else ""
    print(f"{book:22} {st['new']:>4} {st['referenced']:>4} {st['variants']:>4} "
          f"{st['skipped']:>5} {st['detected']:>8}  {tag}")

print(f"\nTOTALS  new={totals['new']} referenced={totals['referenced']} "
      f"variants={totals['variants']} skipped={totals['skipped']}")
