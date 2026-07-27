"""Ritual reader for the Magic chapter.

Rituals are 15pt name headings followed by a "(keywords)" line, a
"Threshold: N" line, and a prose description. Rule subsections sit at the same
font size, so a heading only counts as a ritual when a keywords or threshold
line follows it — that signal separates rituals from surrounding rules text.
No book content lives here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_KEYWORDS = re.compile(r"^\(([A-Z][A-Za-z ,/-]+)\)$")
_THRESHOLD = re.compile(r"^Threshold:\s*(.+)$", re.I)
# 15pt headings that are rules subsections, not rituals
_NOT_RITUAL = {"rituals", "ritual failure", "ritual spellcasting", "ritual team",
               "glitches", "step", "magic spells"}


def _is_name(text: str, sz: float) -> bool:
    return (12.4 <= sz and 1 <= len(text.split()) <= 5 and text[0:1].isupper()
            and "(" not in text and text.lower() not in _NOT_RITUAL
            and not text.endswith("Step") and not text[0].isdigit())


def read_rituals(pdf_path, pages) -> list[dict]:
    import pdfplumber

    items: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
            mid = page.width / 2
            for lo, hi in ((0, mid), (mid, page.width)):
                col = [w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]
                cur = None       # {name, keywords, threshold, buf}
                for ln in _lines(col):
                    sz = max(w["size"] for w in ln)
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    if _is_name(text, sz):
                        _flush(cur, page_no, items)
                        cur = {"name": text, "keywords": "", "threshold": "", "buf": []}
                        continue
                    if cur is None:
                        continue
                    m = _KEYWORDS.match(text)
                    if m and not cur["keywords"]:
                        cur["keywords"] = m.group(1).strip()
                        continue
                    t = _THRESHOLD.match(text)
                    if t and not cur["threshold"]:
                        cur["threshold"] = t.group(1).strip()
                        continue
                    cur["buf"].append(text)
                _flush(cur, page_no, items)
    return items


def _flush(cur, page_no, items):
    # a real ritual carries keywords or a threshold; otherwise it's a rules head
    if not cur or not (cur["keywords"] or cur["threshold"]):
        return
    system = {"category": "RITUAL"}
    if cur["keywords"]:
        system["keywords"] = cur["keywords"]
    if cur["threshold"]:
        system["threshold"] = cur["threshold"]
    desc = _dehyphenate(cur["buf"])
    if len(desc) > 40:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
