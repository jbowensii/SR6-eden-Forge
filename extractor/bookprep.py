"""Read many books at once, so the machine's other fifteen cores do something.

An import spent almost all of its time in pdfplumber, walking every page of
every book -- and doing it FIVE times per book, once each for the table reader,
the name fixer's prose scan, the heading sample, and the description reader. On
a 322-page core rulebook that was roughly 25 seconds a pass. Fifty books of
that is hours, on one core, while the rest of the machine idles.

None of that page-walking depends on the library. So it happens here, for as
many books at a time as the user allows, and each worker hands back a small
picklable result instead of a PDF.

**What stays serial, and why.** Every book merges into the one ``corebook``
library, so two books merged at once would race on the same files. More
importantly Commlink6 rows must keep their precedence over anything read from
a page -- Commlink6 is the authority, the PDF fills its gaps -- and that
ordering is only meaningful if books are merged one at a time, in plan order,
corebook first. So the merge is untouched: this module only makes the reading
parallel, never the writing.

**The one behavioural difference.** The name fixer builds its vocabulary from
the library plus the book's own prose. Run serially, a book sees the items
every earlier book added; run in parallel, every book sees the library as it
was when the run started. It only ever affects de-mangling of names in
no-space-glyph tables, and ``--workers 1`` restores the old behaviour exactly.
"""
from __future__ import annotations

import concurrent.futures as cf
import multiprocessing
import os
from pathlib import Path

from extractor.describe import book_lines
from extractor.hierarchy import extract_sample, read_hierarchy, read_sections
from extractor.quiet import quiet_pdf_noise
from extractor.demangle import build_vocab, demangle_name, make_segmenter
from extractor.xtable import extract_book


def default_workers() -> int:
    """One per physical-ish core, minus a couple so the machine stays usable."""
    n = os.cpu_count() or 4
    return max(1, min(16, n - 2))


def _page_count(pdf: str) -> int:
    import pdfplumber

    with pdfplumber.open(str(pdf)) as p:
        return len(p.pages)


def prepare_book(job: dict) -> dict:
    """All the PDF reading for one book. Runs in a worker process.

    Takes and returns plain data only -- a pdfplumber page cannot be pickled,
    and sending one back would defeat the point anyway.
    """
    quiet_pdf_noise()

    book, pdf = job["book"], job["pdf"]
    try:
        npages = _page_count(pdf)
        pages = range(1, npages + 1)

        incoming: dict = {}
        if not job["curated"]:
            # the name fixer's vocabulary: the library as it stood when the run
            # started, plus this book's own prose
            import pdfplumber

            prose = []
            with pdfplumber.open(pdf) as p:
                for pg in p.pages:
                    prose.append(pg.extract_text() or "")
            seg = make_segmenter(build_vocab(job["libText"], " ".join(prose)))
            from extractor.autodetect import _looks_mangled

            def fixer(n, _seg=seg):
                return demangle_name(n, _seg) if _looks_mangled(n) else n

            incoming = extract_book(Path(pdf), pages, name_fixer=fixer)

        sample = extract_sample(pdf, pages)
        return {
            "book": book,
            "pages": npages,
            "incoming": incoming,
            "hier": read_hierarchy(pdf, pages, sample=sample),
            "markers": read_sections(pdf, pages, sample=sample),
            "lines": book_lines(pdf, pages),
            "error": None,
        }
    except Exception as e:                      # one bad book must not stop the rest
        return {"book": book, "pages": 0, "incoming": {}, "hier": {},
                "markers": [], "lines": [], "error": f"{type(e).__name__}: {e}"}


def prepare_books(jobs: list[dict], workers: int, on_done=None) -> dict[str, dict]:
    """Run :func:`prepare_book` over ``jobs``, up to ``workers`` at a time.

    :param on_done: called with each result as it lands, for progress.
    :returns: ``{book: result}``

    ``workers <= 1`` runs in-process: no pool, no spawn cost, and the exact
    serial behaviour for anyone who wants it.
    """
    out: dict[str, dict] = {}
    if workers <= 1:
        for j in jobs:
            r = prepare_book(j)
            out[r["book"]] = r
            if on_done:
                on_done(r)
        return out

    # spawn, not fork: Windows has no fork, and a frozen build must re-exec
    # itself cleanly (see freeze_support in the entry points)
    ctx = multiprocessing.get_context("spawn")
    with cf.ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        futures = {pool.submit(prepare_book, j): j["book"] for j in jobs}
        for fut in cf.as_completed(futures):
            try:
                r = fut.result()
            except Exception as e:              # worker died outright
                r = {"book": futures[fut], "pages": 0, "incoming": {}, "hier": {},
                     "markers": [], "lines": [], "error": f"worker lost: {e}"}
            out[r["book"]] = r
            if on_done:
                on_done(r)
    return out
