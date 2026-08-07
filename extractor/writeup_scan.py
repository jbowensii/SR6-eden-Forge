"""Find each item's writeup in its book, one book per worker process.

``tools/rebuild_descriptions.py`` walked every page of every owned book to
build its line index, then searched that index once per item. The walk is
around 25 seconds on a big book, so fifty books was roughly twenty minutes on a
single core — long enough that the phase was reasonably mistaken for a hang.

The walk depends on nothing but the PDF, so it happens here and several books
can be read at once. Only the SEARCH is done in the worker; deciding what to do
with the result — the notes fallback, which files are dirty, whether to write —
stays with the caller, which is the half that touches the shared library.

**Why a module and not a function in the script.** Workers are started by spawn,
which re-imports the module the target function came from. A function defined
in a script would make every child re-execute that script from the top.
"""
from __future__ import annotations


def scan_book(job: dict) -> dict:
    """``{book, pdf, wanted: [(id, name, page)]}`` -> ``{id: description}``.

    Plain data in and out: a pdfplumber page cannot cross a process boundary,
    and the line index is far too large to want to.
    """
    from extractor.quiet import quiet_pdf_noise
    from extractor.writeups import find_block, read_book_lines

    quiet_pdf_noise()
    book, pdf = job["book"], job["pdf"]
    out: dict[str, str] = {}

    if not pdf:
        return {"book": book, "found": out, "error": None}

    try:
        lines = read_book_lines(pdf)
    except Exception as e:
        return {"book": book, "found": out, "error": f"{type(e).__name__}: {e}"}

    for item_id, name, page in job["wanted"]:
        try:
            block = find_block(name, page or 0, lines)
        except Exception:
            block = None            # one unreadable writeup is not a failure
        if block:
            out[item_id] = block

    return {"book": book, "found": out, "error": None}
