"""Cross-book merge: fold a book's extracted items into the canonical gear
library, deduplicating and creating variants per these rules —

  same normalized name + same key stats  -> one item; add {book,page} to its
                                            references (reprints: skip instead)
  same normalized name + different stats -> new "(Variant)" item
  new name                               -> new item

Descriptions: keep the longest; when two are comparably long, prefer the one
from the newer book. Images from a book attach to the item (and its variants
via the generic mechanism) when the item has no specific render yet.

Everything here is pure data manipulation over dicts; no PDF or book content
lives in this module.
"""

from __future__ import annotations

import re

from extractor.emit import slugify

# system fields that define item identity for variant detection. Economic
# fields are compared through _price/_avail so formula pricing (price=0 +
# priceDef) is captured; formatting-only *Def strings are otherwise ignored.
KEY_FIELDS = [
    "type", "dmgDef", "stun", "attackRating", "modes", "ammocap",
    "essence", "defense", "rating", "capacity", "a", "s", "d", "f",
    "handlOn", "handlOff", "accOn", "spdiOn", "tspd", "bod", "arm", "pil", "sen", "sea",
]


def norm_base(name: str) -> str:
    """Normalized identity key: drop a trailing '(Variant…)'/parenthetical
    and non-alphanumerics."""
    base = re.sub(r"\s*\((?:variant|[^)]*variant[^)]*)\)\s*$", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", base.casefold())


def _key_view(system: dict) -> dict:
    view = {f: system.get(f) for f in KEY_FIELDS if f in system}
    view["_price"] = system.get("price") or system.get("priceDef")
    view["_avail"] = system.get("avail") or system.get("availDef")
    return view


def same_stats(a: dict, b: dict) -> bool:
    return _key_view(a) == _key_view(b)


def _seed_sources(item: dict) -> list:
    return item["meta"].setdefault(
        "sources", [{"book": item["meta"]["book"], "page": item["meta"]["page"]}]
    )


def add_reference(item: dict, book: str, page: int) -> bool:
    """Append {book,page} to an item's references if not already present."""
    sources = _seed_sources(item)
    if any(s["book"] == book and s["page"] == page for s in sources):
        return False
    sources.append({"book": book, "page": page})
    return True


def better_description(cur: str, cur_book: str, inc: str, inc_book: str, dates: dict):
    """Return (text, book) to keep: longest wins; comparable lengths -> newer."""
    cur = cur or ""
    inc = inc or ""
    if not inc:
        return cur, cur_book
    if not cur:
        return inc, inc_book
    lc, li = len(cur), len(inc)
    if min(lc, li) / max(lc, li) >= 0.85:  # comparably complete -> newer book wins
        return (inc, inc_book) if dates.get(inc_book, "") >= dates.get(cur_book, "") else (cur, cur_book)
    return (inc, inc_book) if li > lc else (cur, cur_book)


def _unique_id(base_id: str, existing_ids: set) -> str:
    if base_id not in existing_ids:
        return base_id
    n = 2
    while f"{base_id}_{n}" in existing_ids:
        n += 1
    return f"{base_id}_{n}"


def _apply_description(item: dict, inc_desc: str, book: str, dates: dict) -> None:
    cur = item["system"].get("description", "")
    cur_book = item["meta"].get("descriptionFrom", item["meta"]["book"])
    text, from_book = better_description(cur, cur_book, inc_desc, book, dates)
    if text:
        item["system"]["description"] = text
        item["meta"]["descriptionFrom"] = from_book


def merge_book(library, incoming, book, dates, version, extracted_at, reprint=False):
    """Fold `incoming` ({category: [ {name, system, page, description?, img?} ]})
    into `library` ({category: [item]}). Mutates and returns library plus a
    stats dict."""
    stats = {"new": 0, "referenced": 0, "variants": 0, "skipped": 0, "images": 0}

    for category, items in incoming.items():
        lib = library.setdefault(category, [])
        all_ids = {i["id"] for cat in library.values() for i in cat}

        for inc in items:
            page = inc["page"]
            base = norm_base(inc["name"])
            matches = [i for i in lib if norm_base(i["name"]) == base]
            same = next((i for i in matches if same_stats(i["system"], inc["system"])), None)

            if same is not None:
                if reprint:
                    stats["skipped"] += 1
                    continue
                add_reference(same, book, page)
                if inc.get("description"):
                    _apply_description(same, inc["description"], book, dates)
                if inc.get("img") and not same.get("img"):
                    same["img"] = inc["img"]
                    stats["images"] += 1
                stats["referenced"] += 1
                continue

            if matches:  # same name, different stats -> variant
                name = f"{inc['name']} (Variant)"
                new_id = _unique_id(slugify(name), all_ids)
                item = _build(new_id, name, inc, book, page, version, extracted_at)
                item["meta"]["variantOf"] = matches[0]["id"]
                lib.append(item)
                all_ids.add(new_id)
                stats["variants"] += 1
                if inc.get("img"):
                    stats["images"] += 1
                continue

            new_id = _unique_id(slugify(inc["name"]), all_ids)  # brand new
            item = _build(new_id, inc["name"], inc, book, page, version, extracted_at)
            lib.append(item)
            all_ids.add(new_id)
            stats["new"] += 1
            if inc.get("img"):
                stats["images"] += 1

    return library, stats


def _build(item_id, name, inc, book, page, version, extracted_at) -> dict:
    system = dict(inc["system"])
    if inc.get("description"):
        system["description"] = inc["description"]
    item = {
        "id": item_id,
        "name": name,
        "system": system,
        "meta": {
            "book": book,
            "page": page,
            "sources": [{"book": book, "page": page}],
            "extractedAt": extracted_at,
            "extractorVersion": version,
            "qaStatus": "extracted",
        },
    }
    if inc.get("description"):
        item["meta"]["descriptionFrom"] = book
    if inc.get("img"):
        item["img"] = inc["img"]
    return item
