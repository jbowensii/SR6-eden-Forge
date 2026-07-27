"""Heading-hierarchy reader for subtype assignment.

SR6 gear listings nest by font size: a chapter title, then a subtype section
heading (MELEE / BLADES / LIGHT PISTOLS), then each item's own smaller heading
(COMBAT AXE), then body prose. The subtype of an item is the most recent
section heading above it; the description is the body text under the item
heading until the next heading.

This reader walks a book by font size, tracks the current section, and returns
`{normalized item name -> (section text, description)}`. A separate mapping
turns the section text into an Eden `subtype` code. Item headings that match no
existing library item are prose-only gear (items described without a stat
table). No book content lives here."""

from __future__ import annotations

import re
from collections import Counter

from extractor.demangle import build_vocab  # noqa: F401  (kept for parity/imports)
from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.merge import norm_base
from extractor.normalize import normalize_text

# section-heading text -> Eden subtype code, aligned to the codes already in the
# library. Ambiguous parent sections (Firearms, Rifles, Augmentations, Drones,
# Vehicles) are deliberately left unmapped so they never overwrite a more
# specific subtype an item already carries.
_SECTION_HINTS = {
    "holdouts": "HOLDOUTS", "hold-outs": "HOLDOUTS",
    "light pistols": "PISTOLS_LIGHT", "heavy pistols": "PISTOLS_HEAVY",
    "machine pistols": "MACHINE_PISTOLS", "submachine guns": "SUBMACHINE_GUNS",
    "shotguns": "SHOTGUNS", "sniper rifles": "RIFLE_SNIPER",
    "assault rifles": "RIFLE_ASSAULT", "hunting rifles": "RIFLE_HUNTING",
    "machine guns": "MACHINE_GUNS", "special weapons": "OTHER_SPECIAL", "launchers": "LAUNCHERS",
    "tasers": "TASERS", "blades": "BLADES", "clubs": "CLUBS", "bows": "BOWS",
    "crossbows": "CROSSBOWS", "throwing weapons": "THROWING", "grenades": "GRENADES",
    "rockets and missiles": "ROCKETS", "rockets": "ROCKETS",
    "armor mods": "MODIFICATION", "armor modifications": "MODIFICATION",
    "clothing": "ARMOR_CLOTHES", "helmets": "ARMOR_HELMET", "shields": "ARMOR_SHIELD",
    "commlinks": "COMMLINK", "cyberdecks": "CYBERDECK", "rfid tags": "RFID",
    "sensors": "SENSOR", "security devices": "SECURITY",
    "optical and imaging devices": "OPTICAL", "auditory devices": "AUDIO",
    "tools": "TOOLS", "survival gear": "SURVIVAL_GEAR", "industrial chemicals": "INDUSTRIAL_CHEMICALS",
    "headware": "CYBER_HEADWARE", "eyeware": "CYBER_EYEWARE", "earware": "CYBER_EARWARE",
    "bodyware": "CYBER_BODYWARE", "cyberlimbs": "CYBER_LIMBS",
    "cyber implant weapons": "CYBER_IMPLANT_WEAPON", "cyberlimb accessories": "CYBER_LIMB_ACCESSORY",
    "bioware": "BIOWARE_STANDARD", "cultured bioware": "BIOWARE_CULTURED",
}


# which Eden `type`(s) a subtype legitimately belongs to, so a section marker
# only lands on type-compatible items (generic ELECTRONICS items are allowed to
# receive any subtype since that bucket holds mis-typed gear pending review).
_FIREARM = {"HOLDOUTS", "PISTOLS_LIGHT", "PISTOLS_HEAVY", "MACHINE_PISTOLS",
            "SUBMACHINE_GUNS", "SHOTGUNS", "RIFLE_SNIPER", "RIFLE_ASSAULT",
            "RIFLE_HUNTING", "MACHINE_GUNS", "TASERS", "LAUNCHERS"}
_CLOSE = {"BLADES", "CLUBS", "THROWING"}
_RANGED = {"BOWS", "CROSSBOWS"}
_SPECIAL = {"GRENADES", "ROCKETS", "OTHER_SPECIAL"}
_ARMOR = {"ARMOR_CLOTHES", "ARMOR_HELMET", "ARMOR_SHIELD"}
_CYBER = {"CYBER_HEADWARE", "CYBER_EYEWARE", "CYBER_EARWARE", "CYBER_BODYWARE",
          "CYBER_LIMBS", "CYBER_IMPLANT_WEAPON", "CYBER_LIMB_ACCESSORY", "CYBERDECK"}
_BIO = {"BIOWARE_STANDARD", "BIOWARE_CULTURED"}
_ELEC = {"COMMLINK", "RFID", "SENSOR", "SECURITY", "OPTICAL", "AUDIO"}
_SUBTYPE_TYPE = {
    **{s: {"WEAPON_FIREARMS"} for s in _FIREARM},
    **{s: {"WEAPON_CLOSE_COMBAT"} for s in _CLOSE},
    **{s: {"WEAPON_RANGED"} for s in _RANGED},
    **{s: {"WEAPON_SPECIAL"} for s in _SPECIAL},
    **{s: {"ARMOR"} for s in _ARMOR},
    "MODIFICATION": {"ARMOR", "ARMOR_ADDITION"},
    **{s: {"CYBERWARE"} for s in _CYBER},
    **{s: {"BIOWARE"} for s in _BIO},
    **{s: {"ELECTRONICS", "COMMLINK"} for s in _ELEC},
    "TOOLS": {"TOOLS"}, "SURVIVAL_GEAR": {"SURVIVAL"}, "INDUSTRIAL_CHEMICALS": {"CHEMICALS"},
}


def subtype_compatible(subtype: str, item_type: str) -> bool:
    # the generic ELECTRONICS bucket collects mis-typed gear, so allow any
    # subtype there; otherwise the subtype must belong to the item's type.
    if item_type == "ELECTRONICS":
        return True
    allowed = _SUBTYPE_TYPE.get(subtype)
    return allowed is None or item_type in allowed


def section_to_subtype(section: str) -> str | None:
    key = re.sub(r"\s+", " ", section.strip().lower())
    return _SECTION_HINTS.get(key)


def _heading_sizes(pages_words) -> tuple[float, float]:
    """(body size, item-heading size) inferred from the page sample: the body is
    the commonest size; the item heading is the smallest heading noticeably
    larger than the body that recurs."""
    sizes = Counter(round(w["size"], 1) for ws in pages_words for w in ws)
    if not sizes:
        return 0.0, 0.0
    body = sizes.most_common(1)[0][0]
    heads = sorted(s for s, n in sizes.items() if s > body * 1.12 and n >= 4)
    return body, (heads[0] if heads else body * 1.3)


def _section_name(text: str) -> str | None:
    text = text.strip()
    if 2 <= len(text) and len(text.split()) <= 5 and re.fullmatch(r"[A-Za-z][A-Za-z '&/-]+", text):
        return text
    return None


def extract_sample(pdf_path, pages):
    """`[(page, [words])]` with size/upright attrs — extracted once and shared by
    the hierarchy and section readers so a book is only walked a single time."""
    import pdfplumber

    out = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for p in pages:
            words = [w for w in pdf.pages[p - 1].extract_words(extra_attrs=["size", "upright"])
                     if w.get("upright", True)]
            out.append((p, words))
    return out


def read_sections(pdf_path, pages, sample=None) -> list[tuple[int, float, str]]:
    """`[(page, top, subtype)]` for every section heading that maps to a known
    subtype. Used to subtype table items (whose names aren't headings) by the
    section active where they sit."""
    markers: list[tuple[int, float, str]] = []
    pg_words = sample if sample is not None else extract_sample(pdf_path, pages)
    _body, item_size = _heading_sizes([w for _, w in pg_words])
    if not item_size:
        return markers
    for page_no, words in pg_words:
        for ln in _lines(words):
            sz = max(w["size"] for w in ln)
            if sz < item_size - 0.4:  # section headings sit at/above item level
                continue
            text = normalize_text(" ".join(w["text"] for w in ln)).strip()
            sub = section_to_subtype(text.lower()) if _section_name(text) else None
            if sub:
                markers.append((page_no, ln[0]["top"], sub))
    return markers


def subtype_for_page(markers, page: int) -> str | None:
    """The subtype of the last section heading at or before a given page."""
    best = None
    for mpage, _top, sub in markers:
        if mpage <= page:
            best = sub
        else:
            break
    return best


def read_hierarchy(pdf_path, pages, sample=None) -> dict[str, tuple[str, str]]:
    """`{norm(name): (section, description)}` for every item heading."""
    out: dict[str, tuple[str, str]] = {}
    pg_words = sample if sample is not None else extract_sample(pdf_path, pages)
    _body, item_size = _heading_sizes([w for _, w in pg_words])
    if not item_size:
        return out
    for _page_no, words in pg_words:
        mid = max((w["x1"] for w in words), default=0) / 2
        cols = [[w for w in words if (w["x0"] + w["x1"]) / 2 < mid],
                [w for w in words if (w["x0"] + w["x1"]) / 2 >= mid]]
        for col in cols:
            section = None
            cur_name = None
            buf: list[str] = []

            def flush():
                nonlocal cur_name, buf
                if cur_name and section:
                    desc = _dehyphenate(buf)
                    key = norm_base(cur_name)
                    if key and (key not in out or len(desc) > len(out[key][1])):
                        out[key] = (section, desc)
                cur_name, buf = None, []

            for ln in _lines(col):
                sz = max(w["size"] for w in ln)
                text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                if not text:
                    continue
                if sz >= item_size + 0.8:  # a section heading (above item level)
                    flush()
                    name = _section_name(text)
                    if name:
                        section = name.lower()
                    continue
                if item_size - 0.4 <= sz <= item_size + 0.4:  # an item heading
                    name = _section_name(text) or (text if len(text.split()) <= 6 else None)
                    if name and name[0].isupper():
                        flush()
                        cur_name = name
                        continue
                if cur_name:  # body prose -> description
                    buf.append(text)
            flush()
    return out
