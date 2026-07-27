"""Adept power reader (Magic chapter).

Each power is a 13pt name heading with "Cost: X PP", "Activation: …", and a
prose description. A heading counts as a power only when a Cost/Activation line
follows, separating powers from same-size rules headings. No book content here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_COST = re.compile(r"^Cost:\s*(.+)$", re.I)
_ACT = re.compile(r"^Activation:\s*(.+)$", re.I)
_NOT = {"adepts", "power points", "adept powers", "magic", "spells"}


def _is_name(text, sz):
    return (12.4 <= sz <= 13.6 and 1 <= len(text.split()) <= 5 and text[0:1].isupper()
            and text.lower() not in _NOT and not text[0].isdigit()
            and not text.lower().startswith(("cost", "activation")))


def read_adept_powers(pdf_path, pages):
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
                    if _is_name(text, sz):
                        _flush(cur, page_no, items)
                        cur = {"name": text, "cost": "", "activation": "", "buf": []}
                        continue
                    if cur is None:
                        continue
                    c = _COST.match(text)
                    if c and not cur["cost"]:
                        cur["cost"] = c.group(1).strip(); continue
                    a = _ACT.match(text)
                    if a and not cur["activation"]:
                        cur["activation"] = re.sub(r"\s*\d+$", "", a.group(1)).strip(); continue
                    cur["buf"].append(text)
                _flush(cur, page_no, items)
    return items


def _flush(cur, page_no, items):
    if not cur or not (cur["cost"] or cur["activation"]):
        return
    system = {"category": "ADEPT_POWER"}
    if cur["cost"]:
        system["cost"] = cur["cost"]
    if cur["activation"]:
        system["activation"] = cur["activation"]
    desc = _dehyphenate(cur["buf"])
    if len(desc) > 40:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
