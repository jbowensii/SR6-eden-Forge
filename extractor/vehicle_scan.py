"""Scan one book for stat-block vehicles, in a worker process.

Split out of ``tools/ingest_vehicles.py`` for the same reason as the other
scans: it walks every page of every owned book to find the stat-table header,
and until 0.9.2 the phase never ran at all in an installed build, so nobody had
noticed the cost. Reading is parallel; the merge stays with the caller.

**Why a module and not a function in the script.** Spawn re-imports the module
a worker target came from, so a function defined in a script would make every
child re-execute that script from the top.
"""
from __future__ import annotations

import re

#: The stat-table header that marks a page as carrying vehicles. Defined HERE,
#: not imported from the script: the script defines it inside its __main__
#: guard, and importing a script from a worker is exactly the recursion this
#: module exists to avoid.
_HDR = re.compile(r"HAND\s+ACC(EL)?\b|PILOT\s+SENS")


def scan_book(job: tuple[str, str]) -> dict:
    """``(book, pdf)`` -> ``{"book", "found": [records], "pages": n, "errors"}``."""
    import pdfplumber

    from extractor.autodetect import _valid_name
    from extractor.double_clutch import read_statblock_vehicles
    from extractor.quiet import quiet_pdf_noise

    quiet_pdf_noise()
    book, pdf = job
    try:
        with pdfplumber.open(pdf) as p:
            pages = [i for i, pg in enumerate(p.pages, 1)
                     if _HDR.search(pg.extract_text() or "")]
        if not pages:
            return {"book": book, "found": [], "pages": 0, "errors": []}
        found = [r for r in read_statblock_vehicles(pdf, pages)
                 if _valid_name(r["name"])]
        return {"book": book, "found": found, "pages": len(pages), "errors": []}
    except Exception as e:
        return {"book": book, "found": [], "pages": 0,
                "errors": [f"{book}: {type(e).__name__}: {e}"]}
