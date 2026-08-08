"""Extract embedded artwork from EVERY registered book into
data/_assets/<book>/_inbox (unpaired) so the review app's Book-graphics gallery
shows all of it. Pairing to items happens separately for gear books; here the
goal is coverage across the whole library, including the plot/adventure books
image extraction never ran on. rembg is skipped for speed. Idempotent: images
are keyed by xref hash, so re-running only adds new ones."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import fitz

from extractor.images_extract import extract_images
from extractor.ingest import load_registry

DATA = _P("data")
SKIP = {"gun_rack", "rides"}

if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    reg = load_registry(DATA)
    only = set(sys.argv[1:])
    grand = {"saved": 0, "assigned": 0, "inbox": 0}
    for book, meta in reg.items():
        if book in SKIP or (only and book not in only):
            continue
        pdf = _P(meta.get("pdf", ""))
        if not pdf.is_file():
            continue
        try:
            npages = fitz.open(str(pdf)).page_count
            stats = extract_images(pdf, DATA, book, "gear", range(1, npages + 1), rembg=False)
            for k in grand:
                grand[k] += stats.get(k, 0)
            print(f"{book:22} saved={stats['saved']:>4} assigned={stats['assigned']:>3} inbox={stats['inbox']:>4}", flush=True)
        except Exception as e:
            print(f"{book:22} ERROR {e}", flush=True)
    print(f"TOTAL saved={grand['saved']} assigned={grand['assigned']} inbox={grand['inbox']}")
    print("done")
