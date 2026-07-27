"""Reader for spirit types (Conjuring chapter). Each is a "Spirits of X" name,
the B A R S W L I C M ESS header, a line of Force-based attribute formulas
(F+2, F-3, F, …), then Powers, Optional Powers, and Attacks. Attributes are
kept as formula strings since spirits scale with Force. No book content here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_NAME = re.compile(r"^Spirits? of ", re.I)
_ATTR_HDR = re.compile(r"\bB A R S W L I C M ESS\b")
_FORMULA = re.compile(r"^F\S*(?: +F\S*){9}$")
_KEYS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha", "mag", "ess"]
_LABELS = [(r"Optional Powers:", "optionalPowers"), (r"Powers:", "powers"),
           (r"Attacks:", "attacks"), (r"Defense Rating:", "defenseRating")]


def read_spirits(pdf_path, pages):
    import pdfplumber
    items, cur, want_vals = [], None, False
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            words = [w for w in pdf.pages[page_no - 1].extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
            mid = pdf.pages[page_no - 1].width / 2
            stream = []
            for lo, hi in ((0, mid), (mid, pdf.pages[page_no - 1].width)):
                for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
                    stream.append((max(w["size"] for w in ln), normalize_text(" ".join(w["text"] for w in ln)).strip()))
            for sz, text in stream:
                if not text:
                    continue
                if 12.4 <= sz <= 13.8 and _NAME.match(text) and len(text.split()) <= 6:
                    _flush(cur, page_no, items)
                    cur, want_vals = {"name": text, "sys": {}, "buf": []}, False
                    continue
                if cur is None:
                    continue
                if _ATTR_HDR.search(text):
                    want_vals = True; continue
                if want_vals and _FORMULA.match(text):
                    toks = [re.sub(r"[^A-Za-z0-9]", lambda m: "-" if m.group(0) not in "+" else "+", t) for t in text.split()[:10]]
                    cur["sys"]["attributes"] = {k: v for k, v in zip(_KEYS, toks)}
                    want_vals = False; continue
                want_vals = False
                hit = next((k for pat, k in _LABELS if re.match(pat, text)), None)
                if hit:
                    cur["sys"][hit] = re.sub(r"^[\w ]+:\s*", "", text).strip(); cur["_last"] = hit
                elif cur.get("_last") and text[:1].islower():
                    cur["sys"][cur["_last"]] += " " + text
                else:
                    cur["buf"].append(text); cur.pop("_last", None)
            _flush(cur, page_no, items); cur = None
    return items


def _flush(cur, page_no, items):
    if not cur or "attributes" not in cur["sys"]:
        return
    cur["sys"].pop("_last", None)
    system = {"category": "SPIRIT", **cur["sys"]}
    desc = _dehyphenate(cur["buf"])
    if len(desc) > 40:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
