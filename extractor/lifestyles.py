"""Reader for the six Lifestyles (Street, Squatter, Low, Middle, High, Luxury):
a 15pt name heading, "Cost: ...", and a description. No book content here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_NAMES = {"street", "squatter", "low", "middle", "high", "luxury"}
_COST = re.compile(r"^[^A-Za-z]*Cost:\s*(.+)$", re.I)


def read_lifestyles(pdf_path, pages):
    import pdfplumber
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
            mid = page.width / 2
            for lo, hi in ((0, mid), (mid, page.width)):
                cur = None
                for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
                    sz = max(w["size"] for w in ln)
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    if sz >= 14.5 and text.lower() in _NAMES:
                        _flush(cur, page_no, items)
                        cur = {"name": text, "cost": "", "buf": []}
                        continue
                    if cur is None:
                        continue
                    c = _COST.match(text)
                    if c and not cur["cost"]:
                        cur["cost"] = c.group(1).strip(); continue
                    cur["buf"].append(text)
                _flush(cur, page_no, items)
    return items


def _flush(cur, page_no, items):
    if not cur or not cur["cost"]:
        return
    system = {"category": "LIFESTYLE", "cost": cur["cost"]}
    desc = _dehyphenate(cur["buf"])
    if len(desc) > 30:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
