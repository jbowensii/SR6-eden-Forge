"""Dedicated reader for Double Clutch (the rigger book).

Its vehicles don't sit in a normal table: each one is a magazine spread with a
15pt name heading + prose description, and — elsewhere on the page, wrapped in
forum commentary — a compact stat block:

    Honda Rough Rider (heavy ATV)      <- 9pt label: name + subtype-in-parens
    SPD TOP
    HAND ACC BODY ARM PILOT SENS SEAT AVAIL COST
    INT SPD
    4/3 15 20 160 5 4 1 1 2 2 7,000    <- 11 values == the standard VEHICLE_COLS

So the block is found by its stat header, the label just above it gives the
name and subtype, the numeric line just below gives the stats, and the matching
15pt heading's prose gives the description. No book content lives here."""

from __future__ import annotations

import re

from extractor.columns import resolve
from extractor.describe import _lines
from extractor.normalize import normalize_text

VEHICLE_COLS = ["onoff:handlOn:handlOff", "int:accOn", "int:spdiOn", "int:tspd",
                "int:bod", "int:arm", "int:pil", "int:sen", "seat", "avail", "cost"]
_HEADER_TOKENS = {"hand", "acc", "body", "arm", "pilot", "sens", "seat", "avail", "cost"}
_STAT_ROW = re.compile(r"^\d+/\d+(?:\s+[\d,]+[¥�]?){8,}")  # 4/3 then 8+ numbers
_LABEL = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")  # 'Honda Rough Rider (heavy ATV)'
# normalize the parenthetical descriptor to the book's vehicle categories by
# substring (checked most-specific first); unmatched descriptors are kept as a
# Title-cased subtype so nothing is lost.
_SUBTYPE_RULES = [
    ("submarine", "SUBMARINE"), ("boat", "BOAT"), ("watercraft", "BOAT"), ("ship", "BOAT"),
    ("rotorcraft", "ROTORCRAFT"), ("helicopter", "ROTORCRAFT"), ("vtol", "VTOL"),
    ("aircraft", "AIRCRAFT"), ("plane", "AIRCRAFT"), ("airship", "AIRCRAFT"),
    ("drone", "DRONE"),
    ("motorcycle", "BIKE"), ("bike", "BIKE"), ("atv", "BIKE"), ("hover", "BIKE"),
    ("van", "TRUCK_VAN"), ("truck", "TRUCK_VAN"), ("pickup", "TRUCK_VAN"),
    ("suv", "TRUCK_VAN"), ("cargo", "TRUCK_VAN"), ("bus", "TRUCK_VAN"),
    ("limo", "CAR"), ("coupe", "CAR"), ("sedan", "CAR"), ("car", "CAR"),
    ("utv", "CAR"), ("vehicle", "CAR"),
]


def _norm_subtype(desc: str) -> str:
    d = desc.lower()
    for needle, code in _SUBTYPE_RULES:
        if needle in d:
            return code
    return desc.strip().title().replace(" ", "_")


def _is_stat_header(text: str) -> bool:
    toks = {t.lower() for t in re.findall(r"[A-Za-z]+", text)}
    return "hand" in toks and len(toks & _HEADER_TOKENS) >= 5


def _parse_stat_row(text: str) -> dict | None:
    toks = normalize_text(text).replace("�", "¥").split()
    if len(toks) < 11:
        return None
    toks = toks[:11]
    system = {"type": "VEHICLES"}
    notes = []
    for key, tok in zip(VEHICLE_COLS, toks):
        try:
            converted = resolve(key).convert(tok)
        except Exception:
            return None
        note = converted.pop("_note", None)
        if note:
            notes.append(note)
        system.update(converted)
    if not (system.get("price") and system.get("bod")):
        return None
    if notes:
        system["notes"] = "; ".join(notes)
    return system


def _plausible_name(name: str) -> bool:
    name = name.strip()
    return (3 <= len(name) <= 40 and name[0].isupper()
            and ":" not in name and not name.startswith(">")
            and 1 <= len(name.split()) <= 6)


def _label_above(lines, i):
    """Vehicle 'Name (subtype)' just above a stat header. The name and the
    parenthetical subtype are often on separate lines
    ('Harley-Davidson Centaur' / '(combat motorcycle)')."""
    window = [(k, normalize_text(" ".join(w["text"] for w in lines[k])).strip())
              for k in range(max(0, i - 6), i)]
    for idx in range(len(window) - 1, -1, -1):  # single-line 'Name (subtype)'
        _, text = window[idx]
        m = _LABEL.match(text)
        if m and _plausible_name(m.group(1)):
            return m.group(1).strip(), m.group(2).strip().lower()
    for idx in range(len(window) - 1, 0, -1):  # split: '(subtype)' with name above
        _, text = window[idx]
        m = re.match(r"^\(([^)]+)\)$", text)
        if m:
            name = window[idx - 1][1]
            if _plausible_name(name):
                return name, m.group(1).strip().lower()
    return None, None


def _column_lines(page):
    words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
    mid = page.width / 2
    out = []
    for lo, hi in ((0, mid), (mid, page.width)):
        col = [w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]
        out.append(_lines(col))
    return out


def _descriptions(col_lines) -> dict[str, str]:
    """Map vehicle name -> description prose that follows its 15pt heading."""
    out: dict[str, list[str]] = {}
    cur = None
    for ln in col_lines:
        sz = max(w["size"] for w in ln)
        text = normalize_text(" ".join(w["text"] for w in ln)).strip()
        if not text:
            continue
        if sz >= 13 and 2 <= len(text.split()) <= 7 and text[0].isupper() and "//" not in text:
            cur = text
            out.setdefault(cur, [])
        elif cur and sz >= 10 and not text.startswith(">"):
            out[cur].append(text)
        elif text.startswith(">"):
            cur = None  # forum commentary ends the description
    from extractor.enrich import _dehyphenate
    return {k: _dehyphenate(v) for k, v in out.items() if v}


def read_double_clutch(pdf_path, pages) -> list[dict]:
    import pdfplumber

    vehicles: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            cols = _column_lines(page)
            descs: dict[str, str] = {}
            for col in cols:
                descs.update(_descriptions(col))
            for lines in cols:
                for i, ln in enumerate(lines):
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not _is_stat_header(text):
                        continue
                    name, subtype = _label_above(lines, i)
                    if not name:
                        continue
                    system = None
                    for k in range(i + 1, min(i + 4, len(lines))):
                        row = normalize_text(" ".join(w["text"] for w in lines[k])).strip()
                        if _STAT_ROW.match(row):
                            system = _parse_stat_row(row)
                            break
                    if not system:
                        continue
                    if subtype:
                        system["subtype"] = _norm_subtype(subtype)
                    item = {"name": name, "system": system, "page": page_no}
                    desc = descs.get(name)
                    if desc and len(desc) > 40:
                        item["description"] = desc
                    vehicles.append(item)
    return vehicles
