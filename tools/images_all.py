"""Extract item artwork from each newly-merged book into per-book directories
(data/_assets/<book>/) as alpha PNGs, pairing confident art to items and
applying offline rembg to opaque paired art. Assigned images are copied back
into the merged library by item id. Unpaired art lands in _assets/<book>/_inbox."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import json
import shutil
from pathlib import Path

import fitz

from extractor.cache import cols_path
from extractor.images_extract import extract_images
from extractor.textcols import dump_columns
from extractor.ingest import load_library, load_registry, write_library

DATA = Path("data")
NEW_BOOKS = ["body_shop", "hack_slash", "deadly_arts", "no_future", "astral_ways",
             "lethal_harvest", "krime_katalog", "shadows_new_orleans",
             "tarnished_star", "double_clutch", "smooth_operations"]

reg = load_registry(DATA)
library, envelopes = load_library(DATA, "gear")   # merged library {cat: [items]}
by_id = {i["id"]: i for cat in library.values() for i in cat}

grand = {"saved": 0, "assigned": 0, "inbox": 0}
for book in NEW_BOOKS:
    pdf = Path(reg[book]["pdf"])
    npages = fitz.open(str(pdf)).page_count
    pages = range(1, npages + 1)

    # 1. column-text cache (needed for caption/heading pairing)
    if not cols_path(DATA, book, 1).is_file():
        dump_columns(pdf, book, pages, DATA)

    # 2. per-book payloads from the merged items sourced to this book
    perbook = DATA / book / "gear"
    perbook.mkdir(parents=True, exist_ok=True)
    grouped = {}
    for cat, items in library.items():
        mine = [i for i in items if i["meta"]["book"] == book]
        if mine:
            grouped.setdefault(cat, []).extend(mine)
    for cat, items in grouped.items():
        (perbook / f"{cat}.json").write_text(
            json.dumps({"book": book, "domain": "gear", "category": cat, "items": items},
                       indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 3. paired extraction + rembg on assigned opaque art
    stats = extract_images(pdf, DATA, book, "gear", pages, rembg=True)
    for k in grand:
        grand[k] += stats[k]
    print(f"{book:20} saved={stats['saved']:>4} assigned={stats['assigned']:>3} inbox={stats['inbox']:>4}")

    # 4. copy assigned img paths back into the merged library, then drop scratch payloads
    for cat in grouped:
        payload = json.loads((perbook / f"{cat}.json").read_text(encoding="utf-8"))
        for it in payload["items"]:
            if it.get("img") and it["id"] in by_id:
                by_id[it["id"]]["img"] = it["img"]
    shutil.rmtree(DATA / book)

write_library(DATA, "gear", library, envelopes)
print(f"\nTOTAL saved={grand['saved']} assigned={grand['assigned']} inbox={grand['inbox']}")
print("artwork per book under data/_assets/<book>/ ; unpaired in _assets/<book>/_inbox/")
