"""Ingest a whole book into the canonical gear library: dump column text,
auto-detect gear tables across every page, and merge (dedup / variant /
reference) into the library. The library currently lives under the
``corebook`` namespace (a rename to ``library`` is a tidy follow-up)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import extractor
from extractor.merge import merge_book
from extractor.xtable import extract_book

LIBRARY = "corebook"  # canonical merged-library namespace


def load_registry(data_root: Path) -> dict:
    return json.loads((data_root / "books.json").read_text(encoding="utf-8"))


def _page_count(pdf_path: str) -> int:
    import fitz

    with fitz.open(pdf_path) as doc:
        return doc.page_count


def load_library(data_root: Path, domain: str) -> tuple[dict, dict]:
    """Returns ({category: [items]}, {category: envelope}) for the library."""
    domain_dir = data_root / LIBRARY / domain
    library: dict[str, list] = {}
    envelopes: dict[str, dict] = {}
    for path in sorted(domain_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        library[path.stem] = payload.get("items", [])
        envelopes[path.stem] = payload
    return library, envelopes


def write_library(data_root: Path, domain: str, library: dict, envelopes: dict) -> None:
    domain_dir = data_root / LIBRARY / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    for category, items in library.items():
        env = envelopes.get(category) or {"book": LIBRARY, "domain": domain, "category": category}
        env["items"] = items
        path = domain_dir / f"{category}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(env, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)


def ingest_book(data_root: Path, book: str, domain: str = "gear", redump: bool = False) -> dict:
    reg = load_registry(data_root)
    info = reg.get(book)
    if not info:
        raise SystemExit(f"{book!r} is not in data/books.json")
    pdf = info.get("pdf")
    if not pdf or not Path(pdf).is_file():
        raise SystemExit(f"{book!r} has no readable pdf in data/books.json")

    dates = {k: v.get("date", "") for k, v in reg.items()}
    reprint = bool(info.get("reprint_of"))
    npages = _page_count(pdf)

    incoming = extract_book(Path(pdf), range(1, npages + 1))  # positional table reader
    library, envelopes = load_library(data_root, domain)
    _, stats = merge_book(
        library, incoming, book, dates, extractor.__version__, date.today().isoformat(), reprint=reprint
    )
    write_library(data_root, domain, library, envelopes)
    stats["detected"] = sum(len(v) for v in incoming.values())
    stats["reprint"] = reprint
    return stats
