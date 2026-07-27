"""Spell reader for the Magic chapter.

Spells nest by font like gear listings: a 15pt category heading ("Combat
Spells", "Detection Spells", …), then each spell as a 13pt name heading, a
"(descriptor)" line, a small stat line under a RANGE/TYPE/DURATION/DV[/DAMAGE]
header, and a 10.5pt prose description. This reads that structure into spell
items. No book content lives here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

CATEGORIES = ("COMBAT", "DETECTION", "HEALTH", "ILLUSION", "MANIPULATION")
_CAT_HEADING = re.compile(r"^(Combat|Detection|Health|Illusion|Manipulation)\s+Spells\b", re.I)
_STAT_HEADER = re.compile(r"RANGE\s+TYPE\s+DURATION\s+DV", re.I)
_DESCRIPTOR = re.compile(r"^\(([^)]+)\)$")
# value row: RANGE (LOS / LOS (A) / T / Touch) then P|M, then I|S|P, then DV#, then damage
_VALUE = re.compile(r"^(LOS(?:\s*\(A\))?|Touch|T|Self)\s+([PM])\s+([ISP])\s+(\d+)\s*(.*)$", re.I)


def _category_of(descriptor: str, section: str) -> str | None:
    text = f"{descriptor} {section}".upper()
    for c in CATEGORIES:
        if c in text:
            return c
    return None


def _column_lines(page):
    words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
    mid = page.width / 2
    out = []
    for lo, hi in ((0, mid), (mid, page.width)):
        col = [w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]
        out.append(_lines(col))
    return out


def _flush(cur, buf, section, page_no, items):
    if not cur:
        return
    name, descriptor, stat = cur
    category = _category_of(descriptor, section)
    if not category:
        return
    system = {"category": category}
    if descriptor:
        system["descriptor"] = descriptor
    if stat:
        system.update(stat)
    desc = _dehyphenate(buf)
    if len(desc) > 40:
        system["description"] = desc
    items.append({"name": name, "system": system, "page": page_no})


def read_spells(pdf_path, pages) -> list[dict]:
    import pdfplumber

    items: list[dict] = []
    section = ""  # persists across columns/pages: the last category heading seen
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            for lines in _column_lines(page):
                cur = None       # (name, descriptor, stat|None)
                buf: list[str] = []
                expect_header = False
                for ln in lines:
                    sz = max(w["size"] for w in ln)
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    if _CAT_HEADING.match(text):
                        _flush(cur, buf, section, page_no, items)
                        cur, buf = None, []
                        section = text
                        continue
                    if 12.4 <= sz <= 13.6 and 1 <= len(text.split()) <= 5 and text[0].isupper() and "(" not in text:
                        _flush(cur, buf, section, page_no, items)
                        cur, buf, expect_header = (text, "", None), [], False
                        continue
                    if cur:
                        m = _DESCRIPTOR.match(text)
                        if m and not cur[1]:
                            cur = (cur[0], m.group(1).strip(), cur[2])
                            continue
                        if _STAT_HEADER.search(text):
                            expect_header = True
                            continue
                        if expect_header:
                            v = _VALUE.match(text)
                            if v:
                                stat = {"range": v.group(1).upper().replace(" ", ""),
                                        "spellType": v.group(2).upper(),
                                        "duration": v.group(3).upper(),
                                        "drain": v.group(4)}
                                dmg = v.group(5).strip().rstrip(".")
                                if dmg:
                                    stat["damage"] = dmg
                                cur = (cur[0], cur[1], stat)
                            expect_header = False
                            continue
                        buf.append(text)
                _flush(cur, buf, section, page_no, items)
    return items
