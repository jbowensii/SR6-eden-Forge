"""One-pass ingest: read a book and formulate all of its gear in a single
method. For each book the pipeline —

  1. extracts stat tables with the positional reader, repairing mangled names
     inline (no-space-glyph books) via a de-mangling name_fixer;
  2. runs any dedicated per-book reader (e.g. Double Clutch's magazine-spread
     vehicles);
  3. merges the rows into the library (dedup / variant / reference);
  4. reads the book's heading hierarchy once and, from that single read,
     assigns subtypes, attaches writeup descriptions, and adds prose-only gear
     (items described without a stat table).

Curated books (the hand-built corebook seed) skip extraction but still get the
hierarchy pass. Re-ingesting a book first drops its previous rows, so the whole
thing is idempotent. No book content lives in this module."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import extractor
from extractor.autodetect import _looks_mangled, _valid_name
from extractor.demangle import build_vocab, demangle_name, make_segmenter
from extractor.describe import extract_book_descriptions
from extractor.double_clutch import read_double_clutch
from extractor.enrich import build_index
from extractor.hierarchy import (
    _SUBTYPE_TYPE, extract_sample, read_hierarchy, read_sections,
    section_to_subtype, subtype_compatible, subtype_for_page,
)
from extractor.merge import merge_book, norm_base
from extractor.xtable import extract_book

LIBRARY = "corebook"          # canonical merged-library namespace
CURATED = {"corebook"}        # seed books kept as-is (not re-extracted)
# books whose layout defeats the generic table reader get a dedicated reader
SPECIAL_READERS = {"double_clutch": ("vehicles", read_double_clutch)}
# where a prose-only item of a given type is filed
TYPE_CATEGORY = {
    "WEAPON_FIREARMS": "weapons_firearms", "WEAPON_CLOSE_COMBAT": "weapons_close_combat",
    "WEAPON_RANGED": "weapons_ranged", "WEAPON_SPECIAL": "weapons_special",
    "ARMOR": "armor", "ARMOR_ADDITION": "armor_additions", "AMMUNITION": "ammo",
    "CYBERWARE": "cyberware", "BIOWARE": "bioware", "BIOLOGY": "biotech",
    "ELECTRONICS": "electronics", "SOFTWARE": "software", "MAGICAL": "magical",
    "VEHICLES": "vehicles", "DRONES": "drones", "SURVIVAL": "survival",
    "TOOLS": "tools", "CHEMICALS": "chemicals",
}
_WEAPON_SKILL = {
    "WEAPON_FIREARMS": "firearms", "WEAPON_CLOSE_COMBAT": "close_combat",
    "WEAPON_RANGED": "exotic", "WEAPON_SPECIAL": "exotic",
}
# last-resort subtype from the item name, used only when the heading hierarchy
# gave nothing. Conservative on purpose: high-signal keywords only, so it fills
# gaps without the mislabels the section-marker path is careful to avoid.
_BLADE_KW = ("axe", "sword", "blade", "knife", "gladius", "claymore", "labrys",
             "katar", "chakram", "macuahuitl", "dagger", "glaive", "naginata",
             "chainsaw", "tomahawk", "bear axe", "war fan")
_CLUB_KW = ("club", "chain", "tonfa", "staff", "mace", "hammer", "baton",
            "shillelagh", "warclub", "nunchaku", "taiaha", "shockglove", "knuckle")


def _fallback_subtype(name: str, itype: str) -> str | None:
    n = name.lower()
    if itype == "BIOWARE":
        return "BIOWARE_STANDARD"  # bioware default; reviewer re-tags the cultured few
    if itype == "WEAPON_CLOSE_COMBAT":
        if any(k in n for k in _BLADE_KW):
            return "BLADES"
        if any(k in n for k in _CLUB_KW):
            return "CLUBS"
    if itype == "CYBERWARE":
        if "cyberlimb" in n or "exoframe" in n:
            return "CYBER_LIMBS" if "cyberlimb" in n else "CYBER_BODYWARE"
    return None


def load_registry(data_root: Path) -> dict:
    return json.loads((data_root / "books.json").read_text(encoding="utf-8"))


def _page_count(pdf_path: str) -> int:
    import fitz

    with fitz.open(pdf_path) as doc:
        return doc.page_count


def load_library(data_root: Path, domain: str) -> tuple[dict, dict]:
    """Returns ({category: [items]}, {category: envelope}) for the library."""
    domain_dir = data_root / LIBRARY / domain
    library: dict[str, list] = {}
    envelopes: dict[str, dict] = {}
    for path in sorted(domain_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        library[path.stem] = payload.get("items", [])
        envelopes[path.stem] = payload
    return library, envelopes


def write_library(data_root: Path, domain: str, library: dict, envelopes: dict) -> None:
    domain_dir = data_root / LIBRARY / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    for category, items in library.items():
        env = envelopes.get(category) or {"book": LIBRARY, "domain": domain, "category": category}
        env["items"] = items
        path = domain_dir / f"{category}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(env, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)


def _name_fixer(pdf: str, pages, library: dict):
    """A name repair function that re-spaces only mangled names (no-space-glyph
    tables), leaving clean names untouched — safe to apply to every book."""
    import pdfplumber

    lib_text = " ".join(i["name"] + " " + i["system"].get("description", "")
                        for cat in library.values() for i in cat)
    prose = []
    with pdfplumber.open(pdf) as p:
        for pg in p.pages:
            prose.append(pg.extract_text() or "")
    seg = make_segmenter(build_vocab(lib_text, " ".join(prose)))
    return lambda n: demangle_name(n, seg) if _looks_mangled(n) else n


def _apply_descriptions(library: dict, book: str, pdf: str, pages) -> int:
    """Attach writeup descriptions to this book's items via font-aware matching."""
    payloads: dict[str, dict] = {}
    for cat, items in library.items():
        mine = [i for i in items if i["meta"]["book"] == book]
        if mine:
            payloads[cat] = {"items": mine}
    if not payloads:
        return 0
    index = build_index(payloads)
    sections = extract_book_descriptions(pdf, index, pages)
    by_id = {i["id"]: i for cat in library.values() for i in cat}
    n = 0
    for (_cat, item_id), text in sections.items():
        item = by_id.get(item_id)
        if item and text and not item["system"].get("description"):
            item["system"]["description"] = text
            item["meta"]["descriptionFrom"] = book
            n += 1
    return n


def _apply_subtypes(library: dict, book: str, hier: dict, markers: list) -> tuple[int, int]:
    boundary = {p for p, _, _ in markers}
    filled = changed = 0
    for cat in library.values():
        for item in cat:
            if item["meta"]["book"] != book:
                continue
            itype = item["system"].get("type", "")
            page = item["meta"].get("page", 0)
            hit = hier.get(norm_base(item["name"]))
            sub = section_to_subtype(hit[1]) if hit else None  # accurate: may correct
            correcting = bool(sub)
            if not sub and page not in boundary:  # section active on a stable page
                cand = subtype_for_page(markers, page)
                if cand and subtype_compatible(cand, itype):
                    sub, correcting = cand, False
            if not sub:  # last resort: high-signal name keyword
                sub = _fallback_subtype(item["name"], itype)
                correcting = False
            if sub:
                cur = item["system"].get("subtype")
                if not cur:
                    item["system"]["subtype"] = sub
                    filled += 1
                elif cur != sub and correcting:
                    item["system"]["subtype"] = sub
                    changed += 1
    return filled, changed


def _prose_only_items(library: dict, hier: dict) -> dict:
    """Gear headings with a description but no matching stat-table item -> new
    items (type/subtype from their section, no stats), grouped by category."""
    existing = {norm_base(i["name"]) for cat in library.values() for i in cat}
    out: dict[str, list] = {}
    for key, (name, section, desc, page) in hier.items():
        if key in existing:
            continue
        sub = section_to_subtype(section)
        if not sub:
            continue  # only real gear sections
        types = _SUBTYPE_TYPE.get(sub)
        if not types or len(types) != 1:
            continue  # need an unambiguous type
        if not _valid_name(name):
            continue
        typ = next(iter(types))
        system = {"type": typ, "subtype": sub}
        skill = _WEAPON_SKILL.get(typ)
        if skill:
            system["skill"] = skill
        item = {"name": name, "system": system, "page": page}
        if desc and len(desc) > 40:
            item["description"] = desc
        out.setdefault(TYPE_CATEGORY.get(typ, "electronics"), []).append(item)
    return out


def ingest_book(data_root: Path, book: str, domain: str = "gear", redump: bool = False) -> dict:
    reg = load_registry(data_root)
    info = reg.get(book)
    if not info:
        raise SystemExit(f"{book!r} is not in data/books.json")
    pdf = info.get("pdf")
    if not pdf or not Path(pdf).is_file():
        raise SystemExit(f"{book!r} has no readable pdf in data/books.json")

    dates = {k: v.get("date", "") for k, v in reg.items()}
    reprint = bool(info.get("reprint_of"))
    version = extractor.__version__
    today = date.today().isoformat()
    npages = _page_count(pdf)
    pages = range(1, npages + 1)
    library, envelopes = load_library(data_root, domain)
    stats = {"new": 0, "referenced": 0, "variants": 0, "skipped": 0, "images": 0}

    if book not in CURATED:
        # idempotent: drop this book's prior rows before re-reading it
        for cat in list(library):
            library[cat] = [i for i in library[cat] if i["meta"]["book"] != book]
        name_fixer = _name_fixer(pdf, pages, library)
        incoming = extract_book(Path(pdf), pages, name_fixer=name_fixer)  # tables + de-mangle
        if book in SPECIAL_READERS:  # dedicated layout readers
            catname, reader = SPECIAL_READERS[book]
            incoming.setdefault(catname, []).extend(reader(pdf, pages))
        _, stats = merge_book(library, incoming, book, dates, version, today, reprint=reprint)

    # single heading-hierarchy read -> subtypes, descriptions, prose-only gear
    sample = extract_sample(pdf, pages)
    hier = read_hierarchy(pdf, pages, sample=sample)
    markers = read_sections(pdf, pages, sample=sample)
    filled, changed = _apply_subtypes(library, book, hier, markers)
    desc_n = _apply_descriptions(library, book, pdf, pages)
    prose = 0
    if not reprint:
        prose_items = _prose_only_items(library, hier)
        if prose_items:
            _, pstats = merge_book(library, prose_items, book, dates, version, today)
            prose = pstats["new"]
    write_library(data_root, domain, library, envelopes)

    stats.update(detected=sum(len(v) for v in library.values()), reprint=reprint,
                 subtypes_filled=filled, subtypes_corrected=changed,
                 descriptions=desc_n, prose_only=prose)
    return stats
