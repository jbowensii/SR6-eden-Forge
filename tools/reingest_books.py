"""Re-ingest gear for specific books (idempotent: ingest_book drops the book's
rows first). Use after a book's PDF is replaced with a cleaner file. Pass book
slugs as argv; defaults to the three re-OCR'd/clean-replacement books."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.ingest import ingest_book

DATA = _P("data")
DEFAULT = ["smooth_operations", "body_shop", "deadly_arts"]

if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    for book in (sys.argv[1:] or DEFAULT):
        try:
            st = ingest_book(DATA, book)
            print(f"{book:22} new={st['new']} ref={st['referenced']} var={st['variants']} "
                  f"desc={st['descriptions']} prose={st['prose_only']}")
        except SystemExit as e:
            print(f"{book:22} SKIP: {e}")
    print("done")
