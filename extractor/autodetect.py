"""Generic gear-table detection by column-header signature.

SR6 books reuse the same column *sets* but abbreviate header tokens
differently (MODES/MODE, AVAILABILITY/AVAIL, CAPACITY/CAP, ACCEL/ACC…) and
reorder them. Rather than hand-tune a header string per book, the row layout
is derived from whatever header a page shows: tokens map to column keys, the
matched sequence becomes the RowSpec, and the column set + the header's
leading label classify the table into a domain/category.

Detection is high-precision by design: only distinctive signatures are
accepted and item names are sanity-checked, so a full-book scan yields clean
gear rather than flooding the review app with table debris. Missed rows are
recovered later by hand, never mis-attributed. No book content lives here.
"""

from __future__ import annotations

import re

from extractor.enrich import parse_col_lines
from extractor.rowengine import RowSpec, parse_block

PHRASES = [
    (("attack", "ratings"), "ar"),
    (("attackr", "atings"), "ar"),
    (("top", "speed"), "int:tspd"),
    (("device", "rating"), "int:rating"),
    (("max", "value"), "note:Max_value"),
]
TOKENS = {
    "dv": "dv", "mode": "modes", "modes": "modes", "ammo": "ammo",
    "avail": "avail", "availability": "avail", "cost": "cost",
    "essence": "essence", "ess": "essence", "capacity": "capacity", "cap": "capacity",
    "defense": "defense", "def": "defense", "rating": "ratingspan",
    "hand": "onoff:handlOn:handlOff", "accel": "int:accOn", "acc": "int:accOn",
    "body": "int:bod", "armor": "int:arm", "arm": "int:arm",
    "pilot": "int:pil", "pil": "int:pil", "sensor": "int:sen", "sens": "int:sen", "sen": "int:sen",
    "seat": "seat", "seats": "seat", "sea": "seat", "speed": "int:tspd",
    "interval": "int:spdiOn", "mount": "mount",
}
GEAR_LABELS = {"gear", "item", "device", "software", "accessory", "accessories",
               "enhancement", "tool", "tools", "sensor", "chemicals", "survival",
               "electronics", "credstick", "tags"}
WORD_RE = re.compile(r"[A-Za-z][A-Za-z]+")


def parse_header(header: str):
    """Header line -> (ordered RowSpec column keys, leading label tokens), or
    None if it isn't a recognizable gear-table header."""
    toks = [t.lower() for t in WORD_RE.findall(header)]
    if len(toks) < 3 or "cost" not in toks:
        return None
    cols: list[str] = []
    label: list[str] = []
    i = 0
    while i < len(toks):
        matched = None
        adv = 1
        for phrase, key in PHRASES:
            if tuple(toks[i:i + len(phrase)]) == phrase:
                matched, adv = key, len(phrase)
                break
        if matched is None and toks[i] in TOKENS:
            matched = TOKENS[toks[i]]
        if matched:
            cols.append(matched)
        elif not cols:
            label.append(toks[i])
        i += adv
    out = []
    for c in cols:
        if not out or out[-1] != c:
            out.append(c)
    if "cost" not in out or len(out) < 2:
        return None
    # 'WEAPON TYPE DV …' has a real per-row category column between name and
    # stats ('Bearded Axe  Blades  3P …') -> capture it as a note column. A
    # bare 'TYPE DV …' is just the name-column header (firearms), so leave it.
    if "type" in label and len(label) > 1:
        out = ["note:Type"] + out
    return out, label


def classify(cols: list[str], label: list[str]):
    """(type, category, skill) for a distinctive signature, else None."""
    s = set(cols)
    if {"onoff:handlOn:handlOff", "int:bod", "int:arm", "int:pil"} <= s:
        return ("VEHICLES", "vehicles", "")
    if "dv" in s and "ar" in s:
        if "modes" in s or "ammo" in s:
            return ("WEAPON_FIREARMS", "weapons_firearms", "firearms")
        return ("WEAPON_CLOSE_COMBAT", "weapons_close_combat", "close_combat")
    if "essence" in s and "capacity" in s:
        return ("CYBERWARE", "cyberware", "")
    if "essence" in s:
        return ("BIOWARE", "bioware", "")
    if "defense" in s:
        return ("ARMOR", "armor", "")
    # generic gear: any priced table with an availability/rating column. The
    # row-validity gate (real name + price) filters out non-gear tables, and
    # the positional reader routes unmapped columns to notes rather than
    # misaligning stats.
    if "avail" in s or "ratingspan" in s:
        return ("ELECTRONICS", "electronics", "")
    return None


VEHICLE_COLS = ["onoff:handlOn:handlOff", "int:accOn", "int:spdiOn", "int:tspd",
                "int:bod", "int:arm", "int:pil", "int:sen", "seat", "avail", "cost"]

SUBTYPE_HINTS = {
    "hold-outs": "HOLDOUTS", "holdouts": "HOLDOUTS", "light pistols": "PISTOLS_LIGHT",
    "heavy pistols": "PISTOLS_HEAVY", "machine pistols": "MACHINE_PISTOLS",
    "submachine guns": "SUBMACHINE_GUNS", "shotguns": "SHOTGUNS", "rifles": "RIFLE_ASSAULT",
    "sniper rifles": "RIFLE_SNIPER", "assault rifles": "RIFLE_ASSAULT",
    "machine guns": "MACHINE_GUNS", "launchers": "LAUNCHERS", "tasers": "TASERS",
    "blades": "BLADES", "clubs": "CLUBS", "bows": "BOWS", "crossbows": "CROSSBOWS",
    "grenades": "GRENADES", "rockets": "ROCKETS", "throwing weapons": "THROWING",
    "armor": "ARMOR_BODY", "clothing": "ARMOR_CLOTHES", "helmets": "ARMOR_HELMET",
    "commlinks": "COMMLINK", "cyberdecks": "CYBERDECK", "software": "SOFTWARE",
    "headware": "CYBER_HEADWARE", "eyeware": "CYBER_EYEWARE", "earware": "CYBER_EARWARE",
    "bodyware": "CYBER_BODYWARE", "cyberlimbs": "CYBER_LIMBS", "bioware": "BIOWARE_STANDARD",
    "cultured bioware": "BIOWARE_CULTURED", "drones": "SMALL_DRONES",
}
_SECTION_RE = re.compile(r"^[a-z][a-z '&/-]{2,38}$")
_STAT_DEBRIS = re.compile(r"[¥|+]|^\d|(?:^|\s)[—-]?\d+/\d|\bx\d|[—-]\d")
# rating-span rows ("Rating 3") and index/label fragments are not item names
_FRAGMENT_RE = re.compile(r"^(rating|force|level|index)\b", re.I)
# bare weapon-category / tier words that are TYPE-column values, not item names
_CATEGORY_WORDS = {
    "blade", "blades", "club", "clubs", "exotic", "heavy", "light", "medium",
    "hold-out", "holdout", "unarmed", "thrown", "throwing", "bow", "standard",
    "pistol", "rifle", "shotgun", "smg", "hmg", "lmg", "mmg", "special",
    "grenade", "rocket", "missile", "melee", "ranged", "firearm", "firearms",
}


_NAME_PARTICLES = {"of", "the", "and", "or", "a", "x", "de", "la", "von", "van", "el"}


def _looks_mangled(name: str) -> bool:
    """Detect broken-font word splits: some SR6 books encode no space glyphs, so
    pdfplumber breaks words at the wrong places -> 'ProstheticCy berlimb,Cr ude',
    'Cleanm etabolism'. The signatures are an interior lowercase->UPPER camelCase
    boundary and a non-leading word fragment that starts lowercase. Genuine
    product names ('Ares Predator', 'Clean Metabolism') never do this."""
    for tok in name.split():
        core = tok.strip(",.()/-")
        if not core:
            continue
        if core[0].islower() and core.casefold() not in _NAME_PARTICLES:
            return True  # 'etabolism', 'berlimb' — a fragment, not a word
        for a, b in zip(core, core[1:]):
            if a.islower() and b.isupper():
                return True  # 'ProstheticCy', 'Wristshie' style camelCase split
    return False


def _valid_name(name: str) -> bool:
    name = name.strip()
    if len(name) < 3 or len(name.split()) > 8:
        return False
    if not (name[0].isupper() or name[0].isdigit()):
        return False  # prose fragments start lowercase
    if "." in name or ":" in name:
        return False  # sentence punctuation
    if name.endswith(",") or "//" in name:
        return False  # dangling column fragment / index divider
    if name.count("(") != name.count(")"):
        return False  # 'Grooming(1' — a split cell, not a name
    if name.isupper() and len(name.split()) >= 4:
        return False  # an all-caps column header leaked as a row
    if name.casefold() in _NAME_PARTICLES:
        return False  # bare 'The'/'A'/'of'
    if _STAT_DEBRIS.search(name):
        return False
    if any(re.fullmatch(r"\d{1,2}[PS]", tok) for tok in name.split()):
        return False  # a bare damage code ('2S') is table debris, not a name
    if _FRAGMENT_RE.match(name):
        return False  # 'Rating 3', 'Force 2' — a span row, not a product
    if name.casefold() in _CATEGORY_WORDS:
        return False
    if _looks_mangled(name):
        return False
    return sum(c.isalpha() for c in name) >= 3


def _detect_stream(lines: list[str], page: int) -> list[dict]:
    """One column's clean line list -> incoming items."""
    items: list[dict] = []
    section = ""
    noise = {page - 1, page, page + 1}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if _SECTION_RE.match(line) and len(line.split()) <= 5:
            section = line.lower()
        parsed = parse_header(line)
        if not parsed:
            i += 1
            continue
        cols, label = parsed
        klass = classify(cols, label)
        if klass is None:
            i += 1
            continue
        wtype, category, skill = klass
        defaults = {"type": wtype}
        if skill:
            defaults["skill"] = skill
        subtype = SUBTYPE_HINTS.get(section, "")
        if subtype:
            defaults["subtype"] = subtype
        spec = RowSpec(columns=(VEHICLE_COLS if wtype == "VEHICLES" else cols),
                       defaults=defaults, allow_tail=True)
        # collect the block: lines until the next header or section title
        block = []
        j = i + 1
        while j < len(lines):
            nxt = lines[j].strip()
            if parse_header(nxt) or (_SECTION_RE.match(nxt) and len(nxt.split()) <= 5):
                break
            block.append(nxt)
            j += 1
        for name, system in parse_block(block, spec, page_numbers=noise):
            if _valid_name(name):
                items.append({"name": name, "system": system, "page": page, "_category": category})
        i = j
    return items


def detect_page_cols(col_text: str, page: int) -> list[dict]:
    """Column-cache page text (frac-prefixed, COLUMN_BREAK) -> items. Each
    column stream is scanned separately so tables don't interleave."""
    parsed = parse_col_lines(col_text.splitlines())
    streams: dict[int, list[str]] = {}
    for _frac, col, text in parsed:
        streams.setdefault(col, []).append(text)
    items = []
    for col in sorted(streams):
        items.extend(_detect_stream(streams[col], page))
    return items


def detect_book(read_cols, book: str, pages) -> dict:
    out: dict[str, list[dict]] = {}
    for page in pages:
        try:
            text = read_cols(book, page)
        except FileNotFoundError:
            continue
        for it in detect_page_cols(text, page):
            out.setdefault(it.pop("_category"), []).append(it)
    return out
