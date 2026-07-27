"""Attribute prose writeups (system.description) to every merged item whose
source book is a supplement. For each book: rebuild per-book payloads from the
merged library, ensure the column-text cache exists, run the heading->next-
heading enrichment, then copy descriptions back into the merged library by id."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import json
import shutil
from pathlib import Path

import fitz

from extractor.cache import cols_path
from extractor.describe import enrich_from_pdf
from extractor.enrich import enrich_descriptions
from extractor.ingest import load_library, load_registry, write_library
from extractor.textcols import dump_columns

DATA = Path("data")
BOOKS = ["corebook", "firing_squad", "body_shop", "hack_slash", "deadly_arts",
         "no_future", "astral_ways", "lethal_harvest", "krime_katalog",
         "shadows_new_orleans", "tarnished_star", "double_clutch", "smooth_operations"]

reg = load_registry(DATA)
library, envelopes = load_library(DATA, "gear")
by_id = {i["id"]: i for cat in library.values() for i in cat}

grand = 0
for book in BOOKS:
    pdf = Path(reg[book]["pdf"])
    npages = fitz.open(str(pdf)).page_count
    pages = range(1, npages + 1)
    if not cols_path(DATA, book, 1).is_file():
        dump_columns(pdf, book, pages, DATA)

    perbook = DATA / book / "gear"
    perbook.mkdir(parents=True, exist_ok=True)
    grouped = {}
    for cat, items in library.items():
        mine = [i for i in items if i["meta"]["book"] == book]
        if mine:
            grouped[cat] = mine
    for cat, items in grouped.items():
        (perbook / f"{cat}.json").write_text(
            json.dumps({"book": book, "domain": "gear", "category": cat, "items": items},
                       indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # font-aware pass first (handles two-column + sidebar-banner pages the text
    # cache scrambles), then the cache-based pass fills any items it missed
    enrich_from_pdf(DATA, book, pdf, "gear", pages, force=False)
    enrich_descriptions(DATA, book, "gear", pages, force=False)

    n = 0
    for cat in grouped:
        payload = json.loads((perbook / f"{cat}.json").read_text(encoding="utf-8"))
        for it in payload["items"]:
            desc = it["system"].get("description", "").strip()
            if desc and it["id"] in by_id:
                by_id[it["id"]]["system"]["description"] = desc
                by_id[it["id"]]["meta"]["descriptionFrom"] = book
                n += 1
    shutil.rmtree(DATA / book)
    grand += n
    total = sum(len(v) for v in grouped.values())
    print(f"{book:20} descriptions {n:>3}/{total}")

write_library(DATA, "gear", library, envelopes)
print(f"\nTOTAL new descriptions: {grand}")
