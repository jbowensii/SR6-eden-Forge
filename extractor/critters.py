"""Reader for critter stat blocks (p215+). Each critter is a name heading, an
attribute array (B A R S W L I C [M] ESS — no Edge), then Skills, Powers,
Movement, and a description. No book content lives here."""

from __future__ import annotations

import re

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_ATTR = re.compile(r"^B A R S W L I C (M )?ESS\b")
_KEYS = ["bod", "agi", "rea", "str", "wil", "log", "int", "cha", "mag", "ess"]
_LABELS = [(r"Skills:", "skills"), (r"Powers:", "powers"), (r"Movement:", "movement"),
           (r"Weaknesses:", "weaknesses"), (r"Notes:", "notes")]
_NOT = {"critters", "mundane critters", "awakened critters", "dracoforms", "powers",
        "skills", "the majority of the earth's animal"}


def _is_name(text, sz):
    return (12.4 <= sz <= 13.6 and 1 <= len(text.split()) <= 4 and text[0:1].isupper()
            and text.lower() not in _NOT and not text[0].isdigit())


def _attrs(vals_line, has_mag):
    keys = _KEYS if has_mag else [k for k in _KEYS if k != "mag"]
    nums = re.findall(r"\d+(?:\.\d+)?", vals_line)[:len(keys)]
    if len(nums) < len(keys):
        return {}
    return {k: (float(v) if k == "ess" else int(float(v))) for k, v in zip(keys, nums)}


def read_critters(pdf_path, pages):
    import pdfplumber
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
            mid = page.width / 2
            for lo, hi in ((0, mid), (mid, page.width)):
                cur, want_vals = None, None
                for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
                    sz = max(w["size"] for w in ln)
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    if _is_name(text, sz):
                        _flush(cur, page_no, items)
                        cur, want_vals = {"name": text, "sys": {}, "buf": []}, None
                        continue
                    if cur is None:
                        continue
                    m = _ATTR.match(text)
                    if m:
                        want_vals = bool(m.group(1)); continue
                    if want_vals is not None:
                        a = _attrs(text, want_vals)
                        if a:
                            cur["sys"]["attributes"] = a
                        want_vals = None
                        continue
                    hit = next((k for pat, k in _LABELS if re.match(pat, text)), None)
                    if hit:
                        cur["sys"][hit] = re.sub(r"^\w+:\s*", "", text).strip(); cur["_last"] = hit
                    elif cur["sys"].get("_last") and text[0].islower():
                        cur["sys"][cur["sys"]["_last"]] += " " + text
                    else:
                        cur["buf"].append(text); cur["sys"].pop("_last", None)
                _flush(cur, page_no, items)
    return items


def _flush(cur, page_no, items):
    if not cur or "attributes" not in cur["sys"]:
        return
    cur["sys"].pop("_last", None)
    system = {"category": "CRITTER", **cur["sys"]}
    desc = _dehyphenate(cur["buf"])
    if len(desc) > 40:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
