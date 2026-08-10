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

# Mechanically-defining stats compared for variant detection. `type` is
# deliberately excluded: the curated corebook uses specific types
# (COMMLINK/TOOLS/…) while the generic classifier tags re-listed gear as
# ELECTRONICS, so including type would make every cross-book duplicate look
# different. Economic identity is price (formula pricing captured via priceDef).
KEY_FIELDS = [
    "dmgDef", "stun", "attackRating", "modes", "ammocap",
    "essence", "defense", "rating", "capacity", "a", "s", "d", "f",
    "handlOn", "handlOff", "accOn", "spdiOn", "tspd", "bod", "arm", "pil", "sen", "sea",
]
_EMPTY = (None, 0, [], "", {})


def norm_base(name: str) -> str:
    """Normalized identity key: drop a trailing '(Variant…)'/parenthetical
    and non-alphanumerics."""
    base = re.sub(r"\s*\((?:variant|[^)]*variant[^)]*)\)\s*$", "", name, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "", base.casefold())


def _key_view(system: dict) -> dict:
    """Defining stats that carry a real value (empties dropped so an extraction
    that missed a field doesn't read as a difference)."""
    view = {f: system.get(f) for f in KEY_FIELDS if system.get(f) not in _EMPTY}
    view["_price"] = system.get("price") or system.get("priceDef")
    return view


def same_stats(a: dict, b: dict) -> bool:
    """Two same-named items are the same product when their prices match and
    every defining stat present on BOTH sides agrees. Stats present on only one
    side are extraction gaps, not differences — this keeps reprints and
    cross-book duplicates from spawning false variants, while genuine stat
    changes (price, damage, rating) still split into a (Variant)."""
    va, vb = _key_view(a), _key_view(b)
    if va["_price"] != vb["_price"]:
        return False
    return all(va[k] == vb[k] for k in (set(va) & set(vb)) - {"_price"})


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
            # dedup across the WHOLE library, not just the detected category: the
            # generic classifier files re-listed gear under 'electronics' even
            # when the corebook curated it under software/tools/drones/etc., so a
            # same-category-only search would miss the original and duplicate it.
            matches = [i for cat in library.values() for i in cat
                       if norm_base(i["name"]) == base]
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

            if matches and reprint:
                # a city-edition reprint reprints corebook's gear verbatim; a
                # stat "difference" here is an extraction artifact (mis-read
                # column), never genuinely new gear, so dedup rather than fork.
                stats["skipped"] += 1
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

            if reprint:
                # nothing in a reprint that isn't already in the base library is
                # real new gear — it's an extraction fragment. Drop it.
                stats["skipped"] += 1
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
    # What the item DOES, as Foundry ActiveEffects. Carried like img: this
    # function rebuilds the item from named fields rather than copying it, so
    # anything not listed here is dropped on the way into the library. Without
    # this line every effect the Commlink6 reader builds is discarded before it
    # is ever written, and the export ships empty effect arrays exactly as it
    # did before the feature existed.
    if inc.get("effects"):
        item["effects"] = inc["effects"]
    return item
