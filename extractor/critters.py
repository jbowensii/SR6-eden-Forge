"""Reader for critter stat blocks (Critters chapter).

Each critter is a name heading, an attribute array (B A R S W L I C [M] ESS —
no Edge; the header sometimes drops out so a bare 9/10-number line is accepted),
then Skills, Powers, Movement, and a description. Critters span the column
break, so a page is read as one left-then-right stream with state persisting
across columns and pages. Only entries inside the Critters section are taken
(contacts earlier in the book have similar blocks). No book content here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_ATTR_HDR = re.compile(r"\bB A R S W L I C (M )?ESS\b")
_VALUES = re.compile(r"^\d{1,2}(?: \d{1,2}(?:\.\d)?){8,9}$")  # 9 or 10 numbers
_KEYS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha", "mag", "ess"]
_LABELS = [(r"Skills:", "skills"), (r"Powers:", "powers"), (r"Movement:", "movement"),
           (r"Weaknesses?:", "weaknesses"), (r"Notes:", "notes")]
_SECTIONS = ("mundane critters", "awakened critters", "dracoforms")
_NOT = {"critters", "mundane critters", "awakened critters", "dracoforms", "powers", "skills"}


def _is_name(text, sz):
    return (12.4 <= sz <= 13.8 and 1 <= len(text.split()) <= 4 and text[0:1].isupper()
            and text.lower() not in _NOT and not text[0].isdigit()
            and not _ATTR_HDR.search(text))


def _attrs(vals_line, has_mag):
    keys = _KEYS if has_mag else [k for k in _KEYS if k != "mag"]
    nums = re.findall(r"\d+(?:\.\d+)?", vals_line)[:len(keys)]
    if len(nums) < len(keys):
        return {}
    return {k: (float(v) if k == "ess" else int(float(v))) for k, v in zip(keys, nums)}


def _page_stream(page):
    words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
    mid = page.width / 2
    out = []
    for lo, hi in ((0, mid), (mid, page.width)):
        for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
            out.append((max(w["size"] for w in ln), normalize_text(" ".join(w["text"] for w in ln)).strip()))
    return out


def read_critters(pdf_path, pages):
    import pdfplumber
    items, cur, want_mag, in_section = [], None, None, False
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            for sz, text in _page_stream(pdf.pages[page_no - 1]):
                if not text:
                    continue
                low = text.lower()
                if sz >= 14 and any(s in low for s in _SECTIONS):
                    in_section = True
                if not in_section:
                    continue
                if _is_name(text, sz):
                    _flush(cur, page_no, items)
                    cur, want_mag = {"name": text, "sys": {}, "buf": []}, None
                    continue
                if cur is None:
                    continue
                h = _ATTR_HDR.search(text)
                if h:
                    want_mag = bool(h.group(1)); continue
                if "attributes" not in cur["sys"]:
                    if want_mag is not None:  # header just seen -> this line is values
                        a = _attrs(text, want_mag)
                        if a:
                            cur["sys"]["attributes"] = a
                        want_mag = None
                        continue
                    if _VALUES.match(text):  # bare values, header dropped
                        n = len(text.split())
                        a = _attrs(text, n == 10)
                        if a:
                            cur["sys"]["attributes"] = a
                        continue
                hit = next((k for pat, k in _LABELS if re.match(pat, text)), None)
                if hit:
                    cur["sys"][hit] = re.sub(r"^\w+:\s*", "", text).strip(); cur["_last"] = hit
                elif cur.get("_last") and text[:1].islower():
                    cur["sys"][cur["_last"]] += " " + text
                else:
                    cur["buf"].append(text); cur.pop("_last", None)
            _flush(cur, page_no, items); cur = None  # entries don't cross page breaks mid-run
    return items


def _flush(cur, page_no, items):
    if not cur or "attributes" not in cur["sys"]:
        return
    system = {"category": "CRITTER", **cur["sys"]}
    desc = _dehyphenate(cur["buf"])
    if len(desc) > 40:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
