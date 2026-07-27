"""Ingest Double Clutch vehicles via the dedicated reader (its magazine-spread
layout defeats the generic table reader). Replaces the book's placeholder items
and merges the recovered vehicles into the library's `vehicles` category."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from datetime import date

import fitz

import extractor
from extractor.double_clutch import read_double_clutch
from extractor.ingest import load_library, load_registry, write_library
from extractor.merge import merge_book

DATA = _P("data")
BOOK = "double_clutch"

reg = load_registry(DATA)
dates = {k: v.get("date", "") for k, v in reg.items()}
library, envelopes = load_library(DATA, "gear")

pdf = reg[BOOK]["pdf"]
n = fitz.open(pdf).page_count
vehicles = read_double_clutch(pdf, range(1, n + 1))

before = sum(1 for cat in library.values() for i in cat if i["meta"]["book"] == BOOK)
for cat in list(library):
    library[cat] = [i for i in library[cat] if i["meta"]["book"] != BOOK]

_, stats = merge_book(library, {"vehicles": vehicles}, BOOK, dates,
                      extractor.__version__, date.today().isoformat())
write_library(DATA, "gear", library, envelopes)
after = sum(1 for cat in library.values() for i in cat if i["meta"]["book"] == BOOK)
withdesc = sum(1 for v in vehicles if v.get("description"))
print(f"double_clutch: {before} -> {after} vehicles (new {stats['new']}, ref {stats['referenced']}, "
      f"var {stats['variants']}); {withdesc}/{len(vehicles)} with descriptions")
