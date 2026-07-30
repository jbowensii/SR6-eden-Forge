"""Backfill metatype on already-extracted NPCs that lack it, using the improved
read_npc_blocks (which now infers metatype from 'Male human'/'Human' demographics
lines). Re-runs the reader per source book, matches by normalized name, and only
fills blanks — never overwrites. Fast alternative to a full re-extraction."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import glob
import json
import re
from collections import defaultdict

import pdfplumber

from extractor.actors import read_npc_blocks
from extractor.ingest import load_registry
from extractor.merge import norm_base

DATA = _P("data")
reg = load_registry(DATA)
EDG = re.compile(r"B\s+A\s+R\s+S\s+W\s+L\s+I\s+C\s+EDG")
MT = re.compile(r"Metatype:", re.I)

# which books have NPCs missing metatype
need = defaultdict(list)
files = {}
for f in glob.glob("data/corebook/npcs/*.json"):
    payload = json.load(open(f, encoding="utf-8"))
    files[f] = payload
    for it in payload["items"]:
        if not it["system"].get("metatype"):
            need[it["meta"]["book"]].append(it)

filled = 0
for book, items in need.items():
    pdf = reg.get(book, {}).get("pdf")
    if not pdf or not _P(pdf).is_file():
        continue
    with pdfplumber.open(pdf) as p:
        texts = [(i, page.extract_text() or "") for i, page in enumerate(p.pages, 1)]
    npages = len(texts)
    pages = sorted({x for i, t in texts if EDG.search(t) or MT.search(t)
                    for x in (i - 1, i, i + 1) if 1 <= x <= npages})
    meta_by_name = {norm_base(r["name"]): r["system"].get("metatype")
                    for r in read_npc_blocks(pdf, pages) if r["system"].get("metatype")}
    for it in items:
        mt = meta_by_name.get(norm_base(it["name"]))
        if mt:
            it["system"]["metatype"] = mt
            filled += 1

for f, payload in files.items():
    _P(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"backfilled metatype on {filled} NPC(s)")
