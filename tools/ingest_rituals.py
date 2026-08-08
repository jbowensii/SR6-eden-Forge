"""Ingest the Magic chapter's rituals into data/<library>/rituals/ritual.json."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import json
from datetime import date

import extractor
from extractor.emit import slugify
from extractor.ingest import LIBRARY, fill_blank_fields, load_registry
from extractor.rituals import read_rituals

DATA = _P("data")
BOOK = "corebook"
PAGES = range(144, 147)

if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    reg = load_registry(DATA)
    rituals = read_rituals(reg[BOOK]["pdf"], PAGES)

    items, seen = [], set()
    for r in rituals:
        base = slugify(r["name"])
        sid, n = base, 2
        while sid in seen:
            sid = f"{base}_{n}"; n += 1
        seen.add(sid)
        item = {
            "id": sid, "name": r["name"], "system": r["system"],
            "meta": {
                "book": BOOK, "page": r["page"],
                "sources": [{"book": BOOK, "page": r["page"]}],
                "extractedAt": date.today().isoformat(),
                "extractorVersion": extractor.__version__, "qaStatus": "extracted",
            },
        }
        if r["system"].get("description"):
            item["meta"]["descriptionFrom"] = BOOK
        items.append(item)

    fill_blank_fields(items, ("keywords", "threshold", "description"), group_by="category")

    out_dir = DATA / LIBRARY / "rituals"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"book": LIBRARY, "domain": "rituals", "category": "ritual", "items": items}
    (out_dir / "ritual.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} rituals to {out_dir}")
