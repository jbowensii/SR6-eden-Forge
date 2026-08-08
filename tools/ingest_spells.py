"""Ingest the Magic chapter's spells into data/<library>/spells/<category>.json.
Uses the font-aware spell reader (name -> descriptor -> stat line -> description),
groups by spell category, and writes schema-conformant spell items."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import json
from datetime import date

import extractor
from extractor.emit import slugify
from extractor.ingest import LIBRARY, fill_blank_fields, load_registry
from extractor.spells import read_spells

SPELL_BASE_FIELDS = ("descriptor", "range", "drain", "damage", "description")

DATA = _P("data")
BOOK = "corebook"
PAGES = range(133, 144)  # corebook Magic chapter spell list

if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    reg = load_registry(DATA)
    spells = read_spells(reg[BOOK]["pdf"], PAGES)

    by_cat: dict[str, list] = {}
    seen: set[str] = set()
    for sp in spells:
        cat = sp["system"]["category"].lower()
        base = slugify(sp["name"])
        sid = base
        n = 2
        while sid in seen:
            sid = f"{base}_{n}"
            n += 1
        seen.add(sid)
        item = {
            "id": sid,
            "name": sp["name"],
            "system": sp["system"],
            "meta": {
                "book": BOOK,
                "page": sp["page"],
                "sources": [{"book": BOOK, "page": sp["page"]}],
                "extractedAt": date.today().isoformat(),
                "extractorVersion": extractor.__version__,
                "qaStatus": "extracted",
            },
        }
        if sp["system"].get("description"):
            item["meta"]["descriptionFrom"] = BOOK
        by_cat.setdefault(cat, []).append(item)

    # every spell exposes its category's full string-field set (blank where missing)
    fill_blank_fields([i for items in by_cat.values() for i in items],
                      SPELL_BASE_FIELDS, group_by="category")

    out_dir = DATA / LIBRARY / "spells"
    out_dir.mkdir(parents=True, exist_ok=True)
    for cat, items in by_cat.items():
        payload = {"book": LIBRARY, "domain": "spells", "category": cat, "items": items}
        (out_dir / f"{cat}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"wrote {sum(len(v) for v in by_cat.values())} spells to {out_dir}")
    for cat, items in sorted(by_cat.items()):
        print(f"  {cat}: {len(items)}")
