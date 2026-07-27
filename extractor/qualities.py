"""Reader for the Qualities chapter: a 13pt name heading, a prose description,
then "Cost: N Karma" and "Game Effect: ...". The "Positive Qualities" /
"Negative Qualities" 15pt sections tag each entry. No book content here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_COST = re.compile(r"^[^A-Za-z]*(?:Cost|Bonus):\s*(.+)$", re.I)
_EFFECT = re.compile(r"^[^A-Za-z]*Game Effect:\s*(.*)$", re.I)
_NOT = {"qualities", "positive qualities", "negative qualities", "cost", "bonus", "game effect"}


def _is_name(text, sz):
    return (12.4 <= sz <= 13.6 and 1 <= len(text.split()) <= 6 and text[0:1].isupper()
            and text.lower() not in _NOT and not text[0].isdigit()
            and not _COST.match(text) and not _EFFECT.match(text))


def read_qualities(pdf_path, pages):
    import pdfplumber
    items = []
    section = "POSITIVE"
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
            mid = page.width / 2
            for lo, hi in ((0, mid), (mid, page.width)):
                cur, phase = None, None
                for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
                    sz = max(w["size"] for w in ln)
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    low = text.lower()
                    if sz >= 14.5 and (low.startswith("positive qualities") or low.startswith("negative qualities")):
                        _flush(cur, section, page_no, items)
                        cur = None; section = "NEGATIVE" if low.startswith("negative") else "POSITIVE"
                        continue
                    if _is_name(text, sz):
                        _flush(cur, section, page_no, items)
                        cur, phase = {"name": text, "desc": [], "cost": "", "effect": []}, "desc"
                        continue
                    if cur is None:
                        continue
                    c = _COST.match(text)
                    if c and not cur["cost"]:
                        cur["cost"] = c.group(1).strip(); phase = "cost"; continue
                    e = _EFFECT.match(text)
                    if e:
                        cur["effect"].append(e.group(1).strip()); phase = "effect"; continue
                    if phase == "effect":
                        cur["effect"].append(text)
                    elif phase == "desc":
                        cur["desc"].append(text)
                _flush(cur, section, page_no, items)
    return items


def _flush(cur, section, page_no, items):
    if not cur or not cur["cost"]:
        return
    system = {"category": section, "cost": cur["cost"]}
    eff = _dehyphenate(cur["effect"])
    if eff:
        system["gameEffect"] = eff
    desc = _dehyphenate(cur["desc"])
    if len(desc) > 30:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
