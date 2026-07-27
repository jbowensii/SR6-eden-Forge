"""Recover gear from books whose compact stat tables encode names without
spaces. The PDF stat numbers are correct; only the names run together, so each
book is re-extracted with a de-mangling name_fixer (Viterbi word segmentation
over a vocabulary built from the library plus the book's own clean prose). The
book's existing partial items are dropped first so the fuller de-mangled set
doesn't collide with them; run tools/enrich_all.py afterwards to (re)attach
descriptions. Recovered items land as qaStatus=extracted for review."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import glob
import json
from datetime import date

import fitz
import pdfplumber

import extractor
from extractor.demangle import build_vocab, demangle_name, make_segmenter
from extractor.ingest import load_library, load_registry, write_library
from extractor.merge import merge_book
from extractor.xtable import extract_book

DATA = _P("data")
BROKEN = ["body_shop", "deadly_arts", "smooth_operations"]

reg = load_registry(DATA)
dates = {k: v.get("date", "") for k, v in reg.items()}
library, envelopes = load_library(DATA, "gear")

# vocabulary shared across books: every clean library name + description
lib_text = " ".join(
    i["name"] + " " + i["system"].get("description", "")
    for f in glob.glob("data/corebook/gear/*.json")
    for i in json.load(open(f, encoding="utf-8"))["items"]
)

for book in BROKEN:
    pdf = reg[book]["pdf"]
    n = fitz.open(pdf).page_count
    prose = ""
    with pdfplumber.open(pdf) as p:
        for pg in p.pages:
            prose += (pg.extract_text() or "") + " "
    seg = make_segmenter(build_vocab(lib_text, prose))
    fixer = lambda nm, seg=seg: demangle_name(nm, seg)

    before = sum(1 for cat in library.values() for i in cat if i["meta"]["book"] == book)
    for cat in list(library):
        library[cat] = [i for i in library[cat] if i["meta"]["book"] != book]

    incoming = extract_book(pdf, range(1, n + 1), name_fixer=fixer)
    _, stats = merge_book(library, incoming, book, dates, extractor.__version__,
                          date.today().isoformat())
    after = sum(1 for cat in library.values() for i in cat if i["meta"]["book"] == book)
    print(f"{book:20} was {before:>3} -> now {after:>3}  (new {stats['new']}, "
          f"ref {stats['referenced']}, var {stats['variants']})")

write_library(DATA, "gear", library, envelopes)
print("\nwrote library; run tools/enrich_all.py to attach descriptions")
