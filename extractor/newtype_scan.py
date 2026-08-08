"""Scan one book for the smaller content types, in a worker process.

Split out of ``tools/ingest_new_types.py`` so several books can be read at
once. This phase only started doing any work in 0.9.2 — before that the frozen
dispatcher never ran it, so it appeared instant because it did nothing. Now
that it runs it walks every page of every owned book on one core, which is
twenty minutes nobody had budgeted for.

The scan depends on nothing but the PDF. The merge into the library still
happens once, serially, in the caller.

**Why a module and not a function in the script.** Workers are started by
spawn, which re-imports the module a target came from. A function defined in a
script would make every child re-execute that script from the top.
"""
from __future__ import annotations

import re

from extractor.newtypes import (read_complexforms, read_contacts,
                                read_martial_techs)
from extractor.normalize import dedouble


def S(pattern: str):
    return re.compile(pattern, re.I)


#: Domains whose per-entry signature is reliable enough to scan a book blind.
#: Adventure and plot books mostly have none of this, so yields are small and
#: that is correct rather than a bug.
XBOOK = {
    "complexforms": (read_complexforms, S(r"FADE\s+VALUE\s+DURATION")),
    "contacts": (read_contacts, S(r"(?:Connection|Loyalty)\s*(?:Rating)?\s*[:=]?\s*\d")),
}

#: Martial arts, best effort. The Deadly Arts technique chapter interleaves
#: cyberweapon and polearm gear in the same font and SR6 has no clean style
#: catalog, so these need a human review pass.
MARTIAL_BOOKS = {"deadly_arts"}
MARTIAL = {"martial_techniques": (read_martial_techs, None)}
MARTIAL_RANGES = {
    "deadly_arts": {"martial_techniques": list(range(33, 48)) + list(range(49, 52))},
}

#: Card decks, not sourcebooks.
SKIP = {"gun_rack", "rides"}


def scan_book(job: tuple[str, str]) -> dict:
    """``(book, pdf)`` -> ``{"book", "found": {domain: [records]}, "errors"}``.

    Plain data in and out: nothing here may hold a pdfplumber object, which
    cannot cross a process boundary.
    """
    import pdfplumber

    from extractor.quiet import quiet_pdf_noise

    quiet_pdf_noise()
    book, pdf = job
    found: dict[str, list] = {}
    errors: list[str] = []

    try:
        with pdfplumber.open(pdf) as p:
            texts = [(i, dedouble(page.extract_text() or ""))
                     for i, page in enumerate(p.pages, 1)]
    except Exception as e:
        return {"book": book, "found": {}, "errors": [f"{type(e).__name__}: {e}"]}

    npages = len(texts)
    active = dict(XBOOK)
    if book in MARTIAL_BOOKS:
        active.update(MARTIAL)

    for domain, (reader, sig) in active.items():
        override = MARTIAL_RANGES.get(book, {}).get(domain)
        if override:
            pages = [x for x in override if 1 <= x <= npages]
        else:
            hits = set()
            for i, t in texts:
                if sig.search(t):
                    hits.update((i - 1, i, i + 1))
            pages = sorted(x for x in hits if 1 <= x <= npages)
        if not pages:
            continue
        try:
            recs = []
            for rec in reader(pdf, pages):
                rec["_book"] = book
                recs.append(rec)
            if recs:
                found[domain] = recs
        except Exception as e:
            errors.append(f"{book}/{domain}: {e}")

    return {"book": book, "found": found, "errors": errors}
