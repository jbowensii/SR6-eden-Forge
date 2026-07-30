"""Readers for the Eden item types beyond the first content wave: complex forms
(FADE/DURATION mini-table), echoes (bulleted Name: desc list), contacts
(Connection/Loyalty examples), martial-art styles and techniques (heading +
labelled lines), plus a harvester that mines distinct critter/sprite powers out
of already-extracted actor blocks. All name detection is body-relative so it
survives per-book font differences. No book content is stored here."""

from __future__ import annotations

import re
from collections import Counter

from extractor.describe import _lines
from extractor.enrich import _dehyphenate
from extractor.normalize import normalize_text

_DUR = {"I": "instantaneous", "S": "sustained", "P": "permanent"}


def _cols(page):
    words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
    if not words:
        return 10.0, []
    body = Counter(round(w["size"], 1) for w in words).most_common(1)[0][0]
    mid = page.width / 2
    streams = []
    for lo, hi in ((0, mid), (mid, page.width)):
        col = []
        for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
            col.append((max(w["size"] for w in ln), normalize_text(" ".join(w["text"] for w in ln)).strip()))
        streams.append(col)
    return body, streams


def _heading(text, sz, body, *, ratio=1.22, max_words=5, stop=()):
    return (sz >= body * ratio and 1 <= len(text.split()) <= max_words
            and text[0:1].isupper() and not text[0].isdigit()
            and "//" not in text and ":" not in text and text.lower() not in stop
            and not text.isupper())


# ── complex forms ────────────────────────────────────────────────────────────
_CF_HDR = re.compile(r"^FADE\s+VALUE\s+DURATION", re.I)
_CF_VALS = re.compile(r"^([–—\-\d]+)\s+([ISP])\b", re.I)
_CF_STOP = {"complex forms", "sprites", "matrix", "technomancers", "registering a sprite"}


def read_complexforms(pdf_path, pages):
    import pdfplumber
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            body, streams = _cols(pdf.pages[page_no - 1])
            for col in streams:
                cur, want = None, False
                for sz, text in col:
                    if not text:
                        continue
                    if _heading(text, sz, body, stop=_CF_STOP):
                        _cf_flush(cur, page_no, items)
                        cur, want = {"name": re.sub(r"\s*\(.*\)$", "", text), "sys": {}, "buf": []}, False
                        continue
                    if cur is None:
                        continue
                    if _CF_HDR.match(text):
                        want = True
                        continue
                    if want:
                        m = _CF_VALS.match(text)
                        if m:
                            fv = re.sub(r"[–—]", "-", m.group(1))
                            cur["sys"]["fading"] = fv
                            cur["sys"]["duration"] = _DUR.get(m.group(2).upper(), "")
                        want = False
                        continue
                    cur["buf"].append(text)
                _cf_flush(cur, page_no, items)
    return items


def _cf_flush(cur, page_no, items):
    if not cur or "fading" not in cur["sys"]:
        return
    desc = _dehyphenate(cur["buf"])
    system = {"category": "COMPLEX_FORM", **cur["sys"]}
    if len(desc) >= 30:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})


# ── echoes (bulleted "• Name: description" list) ─────────────────────────────
_BULLET = re.compile(r"^[•●▪∙·\-\*]\s*(.+)$")
_ECHO_ITEM = re.compile(r"^([A-Z][A-Za-z0-9 /'\-]{1,38}?):\s+(.*\S)$")


def read_echoes(pdf_path, pages):
    """Echoes are a bullet list; also accept 'Increased Maximum Resonance'-style
    heading echoes. Bullets can wrap, so lowercase continuations append."""
    import pdfplumber
    items, cur = [], None

    def flush():
        nonlocal cur
        if cur and len(cur["desc"]) >= 20:
            items.append({"name": cur["name"],
                          "system": {"category": "ECHO", "description": _dehyphenate([cur["desc"]])},
                          "page": cur["page"]})
        cur = None

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            body, streams = _cols(pdf.pages[page_no - 1])
            for col in streams:
                for sz, text in col:
                    if not text:
                        continue
                    b = _BULLET.match(text)
                    payload = b.group(1) if b else None
                    m = _ECHO_ITEM.match(payload) if payload else None
                    if m:
                        flush()
                        cur = {"name": m.group(1).strip(), "desc": m.group(2).strip(), "page": page_no}
                    elif cur and text[:1].islower():
                        cur["desc"] += " " + text
                    elif b:
                        flush()  # a bullet with no Name: pattern ends the current one
    flush()
    return items


# ── contacts (examples: heading + Connection/Loyalty) ────────────────────────
_CON = re.compile(r"Connection\s*(?:Rating)?\s*[:=]?\s*(\d+)", re.I)
_LOY = re.compile(r"Loyalty\s*(?:Rating)?\s*[:=]?\s*(\d+)", re.I)
_CONTACT_STOP = {"contacts", "connection", "loyalty", "making contact", "using contacts"}


def read_contacts(pdf_path, pages):
    import pdfplumber
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            body, streams = _cols(pdf.pages[page_no - 1])
            for col in streams:
                cur = None
                for sz, text in col:
                    if not text:
                        continue
                    if _heading(text, sz, body, max_words=4, stop=_CONTACT_STOP):
                        _con_flush(cur, page_no, items)
                        cur = {"name": text, "sys": {}, "buf": []}
                        continue
                    if cur is None:
                        continue
                    c, l = _CON.search(text), _LOY.search(text)
                    if c:
                        cur["sys"]["connection"] = int(c.group(1))
                    if l:
                        cur["sys"]["loyalty"] = int(l.group(1))
                    if not (c or l):
                        cur["buf"].append(text)
                _con_flush(cur, page_no, items)
    return items


def _con_flush(cur, page_no, items):
    # only real contact examples: those carrying a Connection or Loyalty rating
    if not cur or not ("connection" in cur["sys"] or "loyalty" in cur["sys"]):
        return
    desc = _dehyphenate(cur["buf"])
    system = {"category": "CONTACT", **cur["sys"]}
    if len(desc) >= 20:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})


# ── martial arts (styles carry a Techniques: list; techniques are headings) ──
_MA_STOP = {"martial arts", "martial art", "styles", "techniques", "the basics"}


def read_martial_styles(pdf_path, pages):
    from extractor.glossary import read_glossary
    return read_glossary(pdf_path, pages, "MARTIAL_ART_STYLE",
                         [("Techniques?:", "techniques")], require_label=True,
                         max_words=5, stop=_MA_STOP)


_MT_HDR = re.compile(r"^AVAIL\s+SLOTS\s+COST", re.I)
_MT_VALS = re.compile(r"^(\d+[A-Z]?)\s+(\d+)\s+([\d,]+)")
_MT_EDGE = re.compile(r"Cost:\s*(\d+)\s*Edge", re.I)


_MT_ACTIVATION = {"any attack", "any strike", "grapple", "any melee", "any action",
                  "any test", "any combat", "any ranged"}


def _read_martial_font(pdf_path, pages, category, name_lo=12.5, name_hi=14.5):
    """Deadly Arts sets martial STYLE and TECHNIQUE names in a display font (Njord)
    at ~13pt over 10pt Sabon body; 15-21pt are section titles. Detect entry names
    by 'display font + ~13pt', take following body lines as the description. Called
    on TOC-bounded page ranges so the cyberweapon/gear chapter is excluded."""
    import pdfplumber
    from collections import Counter as _C
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["fontname", "size", "upright"])
                     if w.get("upright", True)]
            if not words:
                continue
            body_font = _C((w["fontname"], round(w["size"])) for w in words).most_common(1)[0][0]
            mid = page.width / 2
            for lo, hi in ((0, mid), (mid, page.width)):
                cur = None
                for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
                    sz = max(w["size"] for w in ln)
                    font = _C(w["fontname"] for w in ln).most_common(1)[0][0]
                    text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                    if not text:
                        continue
                    is_name = (font != body_font[0] and name_lo <= sz <= name_hi
                               and 1 <= len(text.split()) <= 5 and text[0:1].isupper()
                               and text.lower() not in _MA_STOP)
                    if is_name:
                        _ma_flush(cur, page_no, items, category)
                        cur = {"name": text, "buf": []}
                    elif cur is not None and font == body_font[0]:
                        cur["buf"].append(text)
                _ma_flush(cur, page_no, items, category)
    return items


def _ma_flush(cur, page_no, items, category):
    if not cur:
        return
    desc = _dehyphenate(cur["buf"])
    if len(desc) < 40:
        return
    items.append({"name": cur["name"], "page": page_no,
                  "system": {"category": category, "description": desc}})


def read_martial_techs(pdf_path, pages):
    """Deadly Arts martial techniques/edge-actions are 13pt display-font (Njord)
    name headings over 10pt body. BEST-EFFORT: the chapter interleaves cyberweapon
    gear and polearm-weapon writeups in the same font, and SR6 has no clean style
    catalog, so extracted entries mix in some gear/weapon names and need a human
    review pass. Activation labels and prose section titles are dropped; dedup
    keeps the first instance."""
    recs = _read_martial_font(pdf_path, pages, "MARTIAL_ART_TECH")
    out, seen = [], set()
    for r in recs:
        name = r["name"].strip()
        key = name.lower()
        if key in _MT_ACTIVATION or key in seen:
            continue
        if "?" in name or "," in name or "/" in name:
            continue                                   # weapon list / prose fragment
        if re.search(r"\b(your|through|versus|when to|part of|installing|weapon details|specialization)\b", name, re.I):
            continue                                   # prose section title, not a technique
        if re.match(r"^(An|A) [A-Z]", name):
            continue                                   # bad parse ("An The Original Claw")
        seen.add(key)
        out.append(r)
    return out


# ── critter powers glossary (Name / TYPE ACTION RANGE DURATION / P Major LOS …)
_CP_HDR = re.compile(r"^TYPE\s+ACTION\s+RANGE\s+DURATION", re.I)
_CP_VALS = re.compile(r"^([PM])\s+(\S+)\s+(\S+(?:\s*\([^)]*\))?)\s+"
                      r"(Instant(?:aneous)?|Always|Sustained|Permanent|Special|Varies|Never)\b")
_CP_STOP = {"powers", "critters", "critter powers", "the awakened world",
            "mundane critters", "awakened critters", "dracoforms", "optional powers"}


def read_critter_powers(pdf_path, pages):
    """Each power: a name heading, a TYPE ACTION RANGE DURATION table header, a
    'P Major LOS Instant' value line, then a description. Maps to the Eden
    critterpower shape (type physical/mana, action, range, duration)."""
    import pdfplumber
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            body, streams = _cols(pdf.pages[page_no - 1])
            for col in streams:
                cur, want = None, False
                for sz, text in col:
                    if not text:
                        continue
                    if _heading(text, sz, body, max_words=4, stop=_CP_STOP):
                        _cp_flush(cur, page_no, items)
                        cur, want = {"name": text, "sys": {}, "buf": []}, False
                        continue
                    if cur is None:
                        continue
                    if _CP_HDR.match(text):
                        want = True
                        continue
                    if want:
                        m = _CP_VALS.match(text)
                        if m:
                            cur["sys"]["type"] = "physical" if m.group(1) == "P" else "mana"
                            cur["sys"]["action"] = m.group(2)
                            cur["sys"]["range"] = m.group(3).strip()
                            cur["sys"]["duration"] = m.group(4).strip()
                        want = False
                        continue
                    cur["buf"].append(text)
                _cp_flush(cur, page_no, items)
    return items


def _cp_flush(cur, page_no, items):
    if not cur or "type" not in cur["sys"]:      # only entries with the stat table
        return
    cur["name"] = re.sub(r"\s+(of|the|a|and|to|with)$", "", cur["name"], flags=re.I).strip()
    desc = _dehyphenate(cur["buf"])
    system = {"category": "CRITTER_POWER", **cur["sys"]}
    if len(desc) >= 30:
        system["description"] = desc
    items.append({"name": cur["name"], "system": system, "page": page_no})


# ── foci (magical-goods table: TYPE | BONDING | AVAILABILITY | COST) ──────────
_FOCUS_ROW = re.compile(
    r"^(.+?\bfocus)\s+Force\s*[x×]\s*(\d+)\s*\(([^)]*)\)\s+(\S+)\s+Force\s*[x×]\s*([\d,]+)", re.I)


def read_foci(pdf_path, pages):
    """Foci scale with Force, so bonding/cost are stored as Force expressions and
    rating defaults to 1 (the Eden focus template's only own field)."""
    import pdfplumber
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            text = pdf.pages[page_no - 1].extract_text() or ""
            for ln in text.splitlines():
                m = _FOCUS_ROW.match(ln.strip())
                if not m:
                    continue
                name = normalize_text(m.group(1)).strip().title()
                items.append({"name": name, "page": page_no, "system": {
                    "category": "FOCUS", "rating": 1,
                    "force": f"Force × {m.group(2)}",
                    "availability": m.group(4),
                    "price": f"Force × {m.group(5)}¥",
                    "description": f"Bonding karma: Force × {m.group(2)} "
                                   f"({m.group(3)}). Availability {m.group(4)}.",
                }})
    return items
