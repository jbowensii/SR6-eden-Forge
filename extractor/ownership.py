"""Which books may be imported, and where their data comes from.

A PDF is proof of ownership. Commlink6 ships data for the entire line in one
jar, so importing from it indiscriminately would hand a user content for books
they have never bought. The gate is simple: no PDF on disk, no import — even
when the jar has the book sitting right there.

That leaves three cases per book, and :func:`plan_book` names which one applies:

``both``     PDF present and Commlink6 has it. Import the jar data first, then
             read the PDF to fill what the jar lacks.
``pdf``      PDF present, no Commlink6 counterpart. Read the PDF alone — this
             is the path newer releases take on the day they are published.
``skip``     No PDF. Nothing is imported, whatever the jar holds.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

#: Our registry key -> the directory Commlink6 files it under. Everything not
#: listed matches by name. Verified against commlink6-1.14.0.
COMMLINK6_ALIAS = {
    "corebook": "core",
    "krime_katalog": "krime",
    "shadows_new_orleans": "sif_new_orleans",
    "kechibi_code": "kechibi",
}

#: Commlink6 directories that are not a single publication, so no PDF can prove
#: ownership of them.
UNGATEABLE = {"other_us", "de_other"}

#: German-language books.
#:
#: These are NOT excluded from import. The ownership rule is uniform: own the
#: German PDF and its Commlink6 data imports like any other book; do not own it
#: and nothing imports, exactly as for an English book you lack. The list exists
#: only so tools/curate_english.py can hide items whose *sole* source is a book
#: outside the English line — a post-import curation choice, not a gate.
#:
#: Not derivable from the jar: every book ships a base .properties file, so
#: language is editorial knowledge. Held here once rather than duplicated.
GERMAN_BOOKS = {
    "de_alpen", "de_berlin2080", "de_bundeswehr", "de_feuerlaeufer", "de_other",
    "de_piraten", "de_revierbericht", "de_sota2081", "de_sota2082",
    "de_sota2083", "de_westphalen", "kechibi", "lofwyr", "emerald",
    "power_plays", "shadow_cast", "slip_streams", "collapsing_now",
}

_ITEM_ID = re.compile(rb'<item[^>]*id="')


def commlink6_books(jar: Path) -> dict[str, int]:
    """Commlink6 directory -> how many items it defines.

    Excludes only the grab-bags, which are not a single publication and so
    cannot be matched to any one PDF. Language is irrelevant here: a German
    book imports if — and only if — its PDF is present, like any other.
    """
    out: dict[str, int] = {}
    with zipfile.ZipFile(jar) as z:
        for name in z.namelist():
            m = re.match(r"de/rpgframework/shadowrun6/data/([^/]+)/data/[^/]+\.xml$", name)
            if not m:
                continue
            book = m.group(1)
            # language is not a gate — ownership is. Only the grab-bags,
            # which no single PDF can vouch for, are refused outright.
            if book in UNGATEABLE:
                continue
            out[book] = out.get(book, 0) + len(_ITEM_ID.findall(z.read(name)))
    return out


def owns_pdf(info: dict) -> bool:
    """True when the registry entry points at a PDF that is actually there."""
    pdf = (info or {}).get("pdf")
    return bool(pdf) and Path(pdf).is_file()


def plan_book(book: str, info: dict, jar_books: dict[str, int] | None) -> dict:
    """Decide how one book is imported.

    :returns: ``{book, source, jarBook, items, reason}`` where ``source`` is
        one of ``both`` / ``pdf`` / ``skip``.
    """
    if not owns_pdf(info):
        return {"book": book, "source": "skip", "jarBook": None, "items": 0,
                "reason": "no PDF — ownership not established"}

    jar_book = COMMLINK6_ALIAS.get(book, book)
    if jar_books and jar_book in jar_books:
        return {"book": book, "source": "both", "jarBook": jar_book,
                "items": jar_books[jar_book],
                "reason": "PDF owned and Commlink6 has this book"}
    return {"book": book, "source": "pdf", "jarBook": None, "items": 0,
            "reason": "PDF owned; no Commlink6 data for it"}


def plan_import(data_root: Path, jar: Path | None = None) -> list[dict]:
    """The whole import plan, in the order books should be processed.

    corebook first (it is the curated seed whose hierarchy pass the others
    lean on), then by publication date, reprints last — the order
    ``tools/ingest_all.py`` has always used.
    """
    registry = Path(data_root) / "books.json"
    if not registry.is_file():
        # Reached by running an import before anything has scanned a PDF
        # folder. The bare FileNotFoundError names a path the user never chose
        # and gives them nothing to act on.
        raise SystemExit(
            f"No book registry at {registry}.\n"
            "Choose your PDF folder and let the scan find your books first — "
            "that is what writes this file.")
    reg = json.loads(registry.read_text(encoding="utf-8"))
    jar_books = commlink6_books(jar) if jar and Path(jar).is_file() else None

    order = sorted(
        reg.items(),
        key=lambda kv: (kv[0] != "corebook", bool(kv[1].get("reprint_of")),
                        kv[1].get("date", "")),
    )
    return [plan_book(book, info, jar_books) for book, info in order]
