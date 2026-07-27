"""Reader for the Toxins and Drugs section.

A 13pt name heading, then bulleted stats ("Vector:", "Speed:", "Duration:",
"Power:"/"Addiction ...:", "Effect:"), then a prose description. The "Toxins"
and "Drugs" 15pt section headings tag each entry TOXIN vs DRUG. Effect is the
last bullet, so text after it is the description. No book content here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_FIELD = re.compile(r"^[^A-Za-z]*(Vector|Speed|Duration|Power|Effect|Addiction Rating|Addiction Type|Addiction)\b:?\s*(.*)$", re.I)
_KEY = {"vector": "vector", "speed": "speed", "duration": "duration", "power": "power",
        "effect": "effect", "addiction rating": "addictionRating",
        "addiction type": "addictionType", "addiction": "addiction"}
_NOT = {"toxins", "drugs", "concentration", "antidotes", "vector", "speed", "duration",
        "power", "effect", "toxins and drugs", "designer improvements"}


def _is_name(text, sz):
    return (12.4 <= sz <= 13.6 and 1 <= len(text.split()) <= 6 and text[0:1].isupper()
            and text.lower() not in _NOT and not text[0].isdigit()
            and not _FIELD.match(text) and not text.lower().startswith("from "))


def read_toxins_drugs(pdf_path, pages):
    import pdfplumber
    items = []
    section = "TOXIN"
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
            mid = page.width / 2
            for lo, hi in ((0, mid), (mid, page.width)):
                cur, field, phase = None, None, "pre"
                for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
                    sz = max(w["size"] for w in ln)
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    low = text.lower()
                    if sz >= 14.5 and low in ("toxins", "drugs"):
                        _flush(cur, section, page_no, items)
                        cur = None; section = "DRUG" if low == "drugs" else "TOXIN"
                        continue
                    if _is_name(text, sz):
                        _flush(cur, section, page_no, items)
                        cur, field, phase = {"name": text, "sys": {}, "buf": []}, None, "pre"
                        continue
                    if cur is None:
                        continue
                    m = _FIELD.match(text)
                    if m:
                        field = _KEY.get(m.group(1).lower())
                        cur["sys"][field] = m.group(2).strip()
                        phase = "bullets"
                        continue
                    if phase == "bullets" and field and field != "effect":
                        cur["sys"][field] = (cur["sys"][field] + " " + text).strip()
                    else:
                        phase = "desc"; cur["buf"].append(text)
                _flush(cur, section, page_no, items)
    return items


def _flush(cur, section, page_no, items):
    if not cur or "vector" not in cur["sys"]:
        return  # a real entry has at least a Vector bullet
    system = {"category": section, **cur["sys"]}
    desc = _dehyphenate(cur["buf"])
    if len(desc) > 30:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
