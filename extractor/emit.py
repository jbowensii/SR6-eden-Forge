from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return s.strip("_")


def build_item(name: str, system: dict, book: str, page: int, version: str) -> dict:
    return {
        "id": slugify(name),
        "name": name,
        "system": system,
        "meta": {
            "book": book,
            "page": page,
            "extractedAt": date.today().isoformat(),
            "extractorVersion": version,
            "qaStatus": "extracted",
        },
    }


def write_category(data_root: Path, book: str, domain: str, category: str, items: list[dict]) -> Path:
    """Write a category envelope; deduplicates ids on copies without mutating the caller's items."""
    items = [dict(item) for item in items]
    seen: dict[str, int] = {}
    for item in items:
        base = item["id"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            item["id"] = f"{base}_{seen[base]}"
    payload = {"book": book, "domain": domain, "category": category, "items": items}
    out = data_root / book / domain / f"{category}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
