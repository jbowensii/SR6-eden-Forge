"""Reader for the Skills chapter. Each skill is a 13pt name heading with a
"Specializations: ..." line and a description. The specializations line is the
signal that a heading is a skill, not a rules subsection. No book content here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_SPEC = re.compile(r"^Specializations?:\s*(.+)$", re.I)
# canonical linked attribute per SR6 skill (not labelled in the prose)
_ATTR = {
    "astral": "Intuition", "athletics": "Agility", "biotech": "Logic",
    "close combat": "Agility", "con": "Charisma", "conjuring": "Magic",
    "cracking": "Logic", "electronics": "Logic", "enchanting": "Magic",
    "engineering": "Logic", "exotic weapons": "Agility", "firearms": "Agility",
    "influence": "Charisma", "perception": "Intuition", "piloting": "Reaction",
    "sorcery": "Magic", "stealth": "Agility", "tasking": "Resonance",
    "outdoors": "Intuition",
}
# 19 entries — SR6's full active skill list. Perception was listed twice, both
# times as Intuition, so nothing was ever lost; removing the second one only
# stops the count from looking wrong.


def _is_name(text, sz):
    return (14.5 <= sz <= 15.6 and 1 <= len(text.split()) <= 3 and text[0:1].isupper()
            and not text[0].isdigit() and not _SPEC.match(text))


def read_skills(pdf_path, pages):
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
                        cur = {"name": text, "spec": "", "buf": []}
                        continue
                    if cur is None:
                        continue
                    m = _SPEC.match(text)
                    if m and not cur["spec"]:
                        cur["spec"] = m.group(1).strip(); continue
                    cur["buf"].append(text)
                _flush(cur, page_no, items)
    return items


def _flush(cur, page_no, items):
    if not cur or not cur["spec"]:
        return  # a real skill lists specializations
    system = {"category": "ACTIVE", "specializations": cur["spec"]}
    attr = _ATTR.get(cur["name"].lower())
    if attr:
        system["attribute"] = attr
    desc = _dehyphenate(cur["buf"])
    if len(desc) > 30:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
