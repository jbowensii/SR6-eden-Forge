"""Generic glossary reader for description-style content types (complex forms,
echoes, sprite powers, metamagics, critter powers). Each entry is a name heading
sized noticeably larger than the page's body font (sizes differ per book, so the
threshold is body-relative, not fixed), optionally followed by labelled stat
lines (Duration:, Fading:, Type:, Action:, Range:, …), then a prose description.
A page is read left-column-then-right so entries that span the break survive.
No book content is stored here."""

from __future__ import annotations

import re
from collections import Counter

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text


def _name_ok(text, sz, body, ratio, max_words, stop):
    return (sz >= body * ratio and 1 <= len(text.split()) <= max_words
            and text[0:1].isupper() and not text[0].isdigit()
            and "//" not in text and ":" not in text and text.lower() not in stop
            and not text.isupper())


def read_glossary(pdf_path, pages, category, labels=(), *, ratio=1.22,
                  max_words=5, min_desc=40, require_label=False, stop=()):
    """labels: list of (compiled-or-str pattern, key). require_label: only emit
    entries that captured at least one labelled field (filters prose headings)."""
    import pdfplumber
    lab = [(re.compile(p, re.I) if isinstance(p, str) else p, k) for p, k in labels]
    stop = {s.lower() for s in stop}
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
            if not words:
                continue
            body = Counter(round(w["size"], 1) for w in words).most_common(1)[0][0]
            mid = page.width / 2
            cur = None
            for lo, hi in ((0, mid), (mid, page.width)):
                for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
                    sz = max(w["size"] for w in ln)
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    if _name_ok(text, sz, body, ratio, max_words, stop):
                        _flush(cur, page_no, items, category, min_desc, require_label)
                        cur = {"name": text, "sys": {}, "buf": [], "labels": 0}
                        continue
                    if cur is None:
                        continue
                    hit = next(((rx, k) for rx, k in lab if rx.match(text)), None)
                    if hit:
                        rx, k = hit
                        cur["sys"][k] = rx.sub("", text, count=1).strip()
                        cur["_last"] = k
                        cur["labels"] += 1
                    elif cur.get("_last") and text[:1].islower():
                        cur["sys"][cur["_last"]] += " " + text
                    else:
                        cur["buf"].append(text)
                        cur.pop("_last", None)
                _flush(cur, page_no, items, category, min_desc, require_label)
                cur = None
    return items


def _flush(cur, page_no, items, category, min_desc, require_label):
    if not cur:
        return
    if require_label and not cur["labels"]:
        return
    desc = _dehyphenate(cur["buf"])
    if not require_label and len(desc) < min_desc:
        return
    system = {"category": category, **cur["sys"]}
    if len(desc) >= min_desc:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})
