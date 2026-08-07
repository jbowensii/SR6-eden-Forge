"""Read one book for every content type, in a worker process.

Split out of ``tools/ingest_content_all.py`` so the per-book scan can run for
several books at once. That scan was the slowest thing in an import after the
initial read — it walks every page of every owned book to find each content
type's signature pages, then runs the readers over them — and it ran on a
single core while the other fifteen sat idle.

**Why a module and not a function in the script.** Worker processes are started
by *spawn* on Windows, which re-imports the module the target function lives
in. A function defined in a script would make each worker re-execute that
script from the top — registry load, scan loop and all — recursively. Living
here, the worker imports a module with no side effects.

The scan depends on nothing but the PDF, so parallelising it changes no
result: the merge into the library still happens once, serially, in the
caller.
"""
from __future__ import annotations

import re
from typing import NamedTuple

from extractor.actors import read_npc_blocks
from extractor.adept_powers import read_adept_powers
from extractor.critters import read_critters
from extractor.normalize import dedouble
from extractor.qualities import read_qualities
from extractor.rituals import read_rituals
from extractor.spells import read_spells
from extractor.spirits import read_spirits

S = re.compile


class Content(NamedTuple):
    """How one content type is found and filed.

    A NamedTuple rather than a bare 5-tuple: callers used to unpack it as
    ``(reader, sig, *_rest)``, which said nothing about what the rest was and
    left static analysis unable to tell that ``sig`` is a compiled pattern.
    It still unpacks positionally, so nothing downstream changed.
    """

    reader: object          #: (pdf, pages) -> records
    sig: re.Pattern         #: marks a page as carrying this content
    base_fields: tuple      #: blank-filled after the merge
    group_by: str           #: which system field becomes the category file
    extra: object = None    #: optional per-domain filter


#: domain -> how to find it
#:
#: base_fields for aligner-backed domains are the EDEN string fields: the raw
#: reader fields (cost/gameEffect/descriptor/...) are converted by eden_align at
#: ingest, so they must NOT be blank-filled back in.
DOMAINS = {
    "spells": Content(read_spells, S(r"RANGE\s+TYPE\s+DURATION\s+DV"),
                      ("description",), "category"),
    "rituals": Content(read_rituals, S(r"Threshold:\s*\d"),
                       ("description",), "category"),
    "adept_powers": Content(read_adept_powers, S(r"Cost:\s*[\d.]+\s*PP"),
                            ("activation", "description"), "category"),
    "qualities": Content(read_qualities, S(r"(?:Cost|Bonus):\s*\d+\s*Karma"),
                         ("explain", "description"), "category"),
    "npcs": Content(
        read_npc_blocks,
        re.compile(r"Metatype:|B\s+A\s+R\s+S\s+W\s+L\s+I\s+C\s+EDG", re.I),
        ("metatype", "activeSkills", "knowledgeSkills", "qualities", "gear",
         "weapons", "augmentations", "description"), "category"),
    "critters": Content(read_critters, S(r"\bB A R S W L I C (?:M )?ESS\b"),
                        ("skills", "powers", "movement", "description"),
                        "category"),
    "spirits": Content(read_spirits, S(r"Optional Powers:"),
                       ("powers", "optionalPowers", "attacks", "description"),
                       "category"),
    # toxins/drugs are folded into gear as type=CHEMICALS (subtype TOXIN/DRUG),
    # see tools/merge_chemicals.py. Do not re-add them here.
}

#: Books with no prose content worth scanning.
SKIP = {"gun_rack", "rides", "corebook"}


def scan_book(job: tuple[str, str]) -> dict:
    """``(book, pdf)`` -> ``{"book", "found": {domain: [records]}, "errors"}``.

    Returns plain data: records cross a process boundary, so nothing here may
    hold a pdfplumber object.
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
    for domain, spec in DOMAINS.items():
        pages = set()
        for i, t in texts:
            if spec.sig.search(t):
                pages.update((i - 1, i, i + 1))
        pages = sorted(x for x in pages if 1 <= x <= npages)
        if not pages:
            continue
        try:
            recs = []
            for rec in spec.reader(pdf, pages):
                rec["_book"] = book
                recs.append(rec)
            if recs:
                found[domain] = recs
        except Exception as e:
            errors.append(f"{book}/{domain}: {e}")

    return {"book": book, "found": found, "errors": errors}
