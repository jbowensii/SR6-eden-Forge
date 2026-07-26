"""Positional table reconstruction.

Header-token guessing can't tell a name column from a TYPE column from a stat
column when books abbreviate and reorder headers. This module reads columns
the way a human does — by their horizontal position on the page. The header
row's word x-positions define the column bands; each data row's words are
assigned to bands by x-coordinate; the first band is always the item name,
mapped bands become stats, and unmapped intermediate bands (e.g. a weapon-type
column) become notes. Each cell's text is fed straight to its column converter
— no ambiguous whole-row regex.

Input is pdfplumber word dicts ({text, x0, x1, top}); output is the same
"incoming item" shape the merge engine consumes. No book content lives here.
"""

from __future__ import annotations

from extractor.autodetect import PHRASES, SUBTYPE_HINTS, TOKENS, _SECTION_RE, _valid_name, classify
from extractor.columns import resolve
from extractor.normalize import normalize_text

LINE_TOL = 3.0       # vertical tolerance grouping words into a line
NAME_MAXGAP = 2.5    # (unused placeholder for future tuning)


def group_lines(words: list[dict]) -> list[list[dict]]:
    """Cluster words into lines by their top coordinate; each line's words are
    sorted left to right."""
    ws = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines: list[list[dict]] = []
    cur: list[dict] = []
    base = None
    for w in ws:
        if cur and w["top"] - base > LINE_TOL:
            lines.append(sorted(cur, key=lambda x: x["x0"]))
            cur = []
            base = None
        if base is None:
            base = w["top"]
        cur.append(w)
    if cur:
        lines.append(sorted(cur, key=lambda x: x["x0"]))
    return lines


def _cell_key(tokens: list[str], i: int):
    """(column key or None, tokens consumed) for the header word(s) at i."""
    for phrase, key in PHRASES:
        if tuple(t.lower() for t in tokens[i:i + len(phrase)]) == phrase:
            return key, len(phrase)
    return TOKENS.get(tokens[i].lower()), 1


def _raw_cells(line: list[dict]):
    texts = [w["text"] for w in line]
    cells: list[tuple[float, str | None]] = []
    i = 0
    while i < len(line):
        key, adv = _cell_key(texts, i)
        cells.append((line[i]["x0"], key))
        i += adv
    return cells


def mapped_count(line: list[dict]) -> int:
    return sum(1 for _, k in _raw_cells(line) if k)


def header_cells(line: list[dict]):
    """A header line -> [(x0, colkey|None)] left to right, with the first cell
    the name column. Returns None if it isn't a gear-table header."""
    cells = _raw_cells(line)
    mapped = [k for _, k in cells if k]
    if "cost" not in mapped or len(mapped) < 2:
        return None
    # ensure a name column exists: if the first cell is already a data column
    # (e.g. vehicle 'HAND ACC …' with no label), prepend one at the left edge
    if cells[0][1] is not None:
        cells = [(0.0, None)] + cells
    return cells


def classify_header(cells) -> tuple[str, str, str] | None:
    keys = [k for _, k in cells if k]
    # the header's leading label words classify generic gear
    return classify(keys, [])


def assign_row(line: list[dict], cells) -> dict:
    """Assign a data row's words to header column bands by x; returns
    {'_name': str, colkey/'_note': text}."""
    bounds = [x0 for x0, _ in cells]
    out: dict[str, list[str]] = {}
    for w in line:
        cx = (w["x0"] + w["x1"]) / 2
        idx = 0
        for j in range(len(bounds)):
            nxt = bounds[j + 1] if j + 1 < len(bounds) else float("inf")
            if bounds[j] - 1 <= cx < nxt - 1:
                idx = j
                break
        key = cells[idx][1] or ("_name" if idx == 0 else "_note")
        out.setdefault(key, []).append(w["text"])
    return {k: normalize_text(" ".join(v)).strip() for k, v in out.items()}


# a real data row must carry a price plus its domain's signature stat; this is
# what separates table rows from the prose that surrounds them on the page.
KEY_STAT = {
    "WEAPON_FIREARMS": "dmgDef", "WEAPON_CLOSE_COMBAT": "dmgDef", "WEAPON_RANGED": "dmgDef",
    "CYBERWARE": "essence", "BIOWARE": "essence", "ARMOR": "defense", "VEHICLES": "bod",
}


def build_item(assigned: dict, wtype: str, skill: str, subtype: str, page: int, cells):
    name = assigned.get("_name", "")
    if not _valid_name(name):
        return None
    system = {"type": wtype}
    if skill:
        system["skill"] = skill
    if subtype:
        system["subtype"] = subtype
    notes = []
    if assigned.get("_note"):
        notes.append(assigned["_note"])
    for _x, key in cells:
        if not key or key not in assigned:
            continue
        text = assigned[key]
        if not text or text in ("—", "-"):
            continue
        try:
            converted = resolve(key).convert(text)
        except Exception:
            continue
        note = converted.pop("_note", None)
        if note:
            notes.append(note)
        system.update(converted)
    # row-validity gate: reject prose masquerading as a row
    if not (system.get("price") or system.get("priceDef")):
        return None
    keystat = KEY_STAT.get(wtype)
    if keystat and keystat not in system:
        return None
    # plausibility gate: an out-of-range avail/price means a column bled into the
    # wrong band (e.g. a price string parsed as avail) -> drop the misaligned row
    if system.get("avail", 0) > 30 or system.get("price", 0) > 10_000_000:
        return None
    if notes:
        system["notes"] = "; ".join(notes)
    return {"name": name, "system": system, "page": page}


def _is_header(line: list[dict]) -> bool:
    return header_cells(line) is not None


def _section_title(line: list[dict]) -> str | None:
    text = normalize_text(" ".join(w["text"] for w in line)).strip()
    if _SECTION_RE.match(text.lower()) and len(text.split()) <= 5:
        return text.lower()
    return None


def extract_page(words: list[dict], page: int) -> list[dict]:
    lines = group_lines(words)
    items: list[dict] = []
    section = ""
    i = 0
    while i < len(lines):
        sec = _section_title(lines[i])
        if sec:
            section = sec
        cells = header_cells(lines[i])
        data_start = i + 1
        if not cells and i + 1 < len(lines) and mapped_count(lines[i]) >= 1:
            # a genuine header fragment (maps some columns but lacks 'cost')
            # wraps onto the next line (vehicles); combine and retry. Section
            # titles / prose map no columns, so they never combine.
            combined = sorted(lines[i] + lines[i + 1], key=lambda w: w["x0"])
            cells = header_cells(combined)
            if cells:
                data_start = i + 2
        if not cells:
            i += 1
            continue
        klass = classify_header(cells)
        if klass is None:
            i += 1
            continue
        wtype, category, skill = klass
        subtype = SUBTYPE_HINTS.get(section, "")
        j = data_start
        while j < len(lines):
            if _is_header(lines[j]) or _section_title(lines[j]):
                break
            assigned = assign_row(lines[j], cells)
            item = build_item(assigned, wtype, skill, subtype, page, cells)
            if item:
                item["_category"] = category
                items.append(item)
            j += 1
        i = j
    return items


def _pdf_words(page):
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False, extra_attrs=["upright"])
    return [w for w in words if w.get("upright", True)]  # drop rotated margin banners


def extract_page_words(words: list[dict], page_no: int) -> list[dict]:
    return extract_page(words, page_no)


def extract_book(pdf_path, pages, word_source=None) -> dict:
    """word_source(page) -> [{text,x0,x1,top}]; defaults to pdfplumber words.
    Broken-glyph books pass OCR words instead."""
    import pdfplumber

    src = word_source or _pdf_words
    out: dict[str, list[dict]] = {}
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            for it in extract_page(src(pdf.pages[page_no - 1]), page_no):
                out.setdefault(it.pop("_category"), []).append(it)
    return out
