"""Assign subtypes from each book's heading hierarchy. For every book, the
gear-listing headings nest as section (subtype) over item; this reads that
structure and sets each matching library item's subtype from the section above
it. Also fills a missing description from the same writeup. Items whose subtype
the hierarchy can't determine are listed at the end for manual review."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import fitz

from extractor.hierarchy import (
    extract_sample, read_hierarchy, read_sections, section_to_subtype, subtype_compatible, subtype_for_page,
)
from extractor.ingest import load_library, load_registry, write_library
from extractor.merge import norm_base

DATA = _P("data")
reg = load_registry(DATA)
library, envelopes = load_library(DATA, "gear")

# every source book that contributed items
books = sorted({i["meta"]["book"] for cat in library.values() for i in cat if reg.get(i["meta"]["book"], {}).get("pdf")})

filled = changed = desc_filled = 0
for book in books:
    pdf = reg[book]["pdf"]
    n = fitz.open(pdf).page_count
    try:
        sample = extract_sample(pdf, range(1, n + 1))  # walk the book once
        hier = read_hierarchy(pdf, range(1, n + 1), sample=sample)
        markers = read_sections(pdf, range(1, n + 1), sample=sample)
    except Exception as e:
        print(f"{book}: skip ({e})")
        continue
    # pages where a section heading appears are ambiguous for page-level lookup
    # (two subtypes can share a page), so table items there are left for review
    boundary = {p for p, _, _ in markers}
    for cat in library.values():
        for item in cat:
            if item["meta"]["book"] != book:
                continue
            itype = item["system"].get("type", "")
            page = item["meta"].get("page", 0)
            # 1) per-item writeup heading (corebook-style prose gear listing):
            #    accurate, so it may correct a wrong subtype too
            hit = hier.get(norm_base(item["name"]))
            sub = section_to_subtype(hit[0]) if hit else None
            correcting = bool(sub)
            # 2) else the section active on the item's page, but only on
            #    non-boundary pages and only to FILL a missing subtype
            if not sub and page not in boundary:
                cand = subtype_for_page(markers, page)
                if cand and subtype_compatible(cand, itype):
                    sub = cand
                    correcting = False
            if sub:
                cur = item["system"].get("subtype")
                if not cur:
                    item["system"]["subtype"] = sub
                    filled += 1
                elif cur != sub and correcting:  # only the accurate path overrides
                    item["system"]["subtype"] = sub
                    changed += 1
            if hit and hit[1] and len(hit[1]) > 40 and not item["system"].get("description"):
                item["system"]["description"] = hit[1]
                item["meta"]["descriptionFrom"] = book
                desc_filled += 1

write_library(DATA, "gear", library, envelopes)

still = [(i["system"].get("type"), i["name"], i["meta"]["book"])
         for cat in library.values() for i in cat
         if not i["system"].get("subtype")]
print(f"subtypes filled: {filled}, corrected: {changed}, descriptions filled: {desc_filled}")
print(f"still missing subtype: {len(still)}")
from collections import Counter
for t, n in Counter(t for t, _, _ in still).most_common():
    print(f"  {t}: {n}")
