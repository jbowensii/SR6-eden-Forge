"""Shared helpers for ingesting a simple (item-like) domain into the library:
turn extractor records into schema-conformant items, blank-fill the group's
string fields, and write per-category files. Reused by every non-gear domain."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import json
from datetime import date

import extractor
from extractor.emit import slugify
from extractor.ingest import LIBRARY, fill_blank_fields

DATA = _P("data")


def build_item(rec, book):
    return {
        "id": None, "name": rec["name"], "system": rec["system"],
        "meta": {
            "book": book, "page": rec["page"],
            "sources": [{"book": book, "page": rec["page"]}],
            "extractedAt": date.today().isoformat(),
            "extractorVersion": extractor.__version__, "qaStatus": "extracted",
            **({"descriptionFrom": book} if rec["system"].get("description") else {}),
        },
    }


def write_domain(domain, records, book, base_fields, group_by="category", category_of=None):
    """category_of(item)->str picks the file; default groups by system[group_by]."""
    by_cat, seen = {}, set()
    for rec in records:
        item = build_item(rec, book)
        base = slugify(item["name"]) or "item"
        sid, n = base, 2
        while sid in seen:
            sid = f"{base}_{n}"; n += 1
        seen.add(sid)
        item["id"] = sid
        cat = (category_of(item) if category_of else str(item["system"].get(group_by, "item"))).lower()
        by_cat.setdefault(cat, []).append(item)

    fill_blank_fields([i for v in by_cat.values() for i in v], base_fields, group_by)

    out_dir = DATA / LIBRARY / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    for cat, items in by_cat.items():
        payload = {"book": LIBRARY, "domain": domain, "category": cat, "items": items}
        (out_dir / f"{cat}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(v) for v in by_cat.values())
    print(f"{domain}: wrote {total} items ({', '.join(f'{c}:{len(v)}' for c, v in sorted(by_cat.items()))})")
    return total
