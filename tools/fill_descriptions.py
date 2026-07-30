"""Fill missing item descriptions by searching every book's text. For each
registered book, match item names (across all domains) to that book's headings
and pull the following writeup into any item whose description is still empty.
Reuses extractor.describe.enrich_from_pdf (name->heading->prose). Never
overwrites an existing description. Slow (scans every book); run in background."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import glob
import fitz
from extractor.describe import enrich_from_pdf
from extractor.ingest import LIBRARY, load_registry

DATA = _P("data")
reg = load_registry(DATA)
DOMAINS = sorted({_P(f).parent.name for f in glob.glob(f"data/{LIBRARY}/*/*.json")})
DOMAINS = [d for d in DOMAINS if not d.startswith("_")]

grand = 0
for book, meta in reg.items():
    pdf = meta.get("pdf", "")
    if not _P(pdf).is_file() or book in ("gun_rack", "rides"):
        continue
    try:
        npages = fitz.open(pdf).page_count
    except Exception as e:
        print(f"{book}: {e}", flush=True)
        continue
    pages = range(1, npages + 1)
    book_total = 0
    for domain in DOMAINS:
        try:
            r = enrich_from_pdf(DATA, LIBRARY, pdf, domain, pages, force=False)
            book_total += r["updated"]
        except Exception as e:
            print(f"  {book}/{domain}: {e}", flush=True)
    grand += book_total
    print(f"{book:22} filled {book_total}", flush=True)

print(f"TOTAL descriptions filled: {grand}", flush=True)
print("done", flush=True)
