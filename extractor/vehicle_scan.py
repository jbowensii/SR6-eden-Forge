"""Scan one book for stat-block vehicles, in a worker process.

Split out of ``tools/ingest_vehicles.py`` for the same reason as the other
scans: it walks every page of every owned book to find the stat-table header,
and until 0.9.2 the phase never ran at all in an installed build, so nobody had
noticed the cost. Reading is parallel; the merge stays with the caller.

**Why a module and not a function in the script.** Spawn re-imports the module
a worker target came from, so a function defined in a script would make every
child re-execute that script from the top.

``read_statblock_vehicles`` lives here, not in the script, for exactly that
reason — it used to be defined in ``ingest_vehicles.py`` and the first version
of this module guessed it into ``extractor.double_clutch``, where there is no
such name. The worker's broad except turned that ImportError into "this book
has no vehicles", fifty times over, and the phase reported success. One
definition, in a module both callers can import, is the fix.
"""
from __future__ import annotations

import re
from collections import Counter

#: The stat-table header that marks a page as carrying vehicles. Defined HERE,
#: not imported from the script: the script defines it inside its __main__
#: guard, and importing a script from a worker is exactly the recursion this
#: module exists to avoid.
_HDR = re.compile(r"HAND\s+ACC(EL)?\b|PILOT\s+SENS")

#: The eleven stat columns, in the order the books print them.
FIELDS = ["handling", "accel", "speedInterval", "topSpeed", "body", "armor",
          "pilot", "sensor", "seats", "availability", "price"]

#: A subtype line on its own: '(racing motorcycle)'.
_PAREN = re.compile(r"^\(([^)]{2,40})\)\s*$")

#: One stat cell: a number, a fraction, or a price with the nuyen sign.
_CELL = re.compile(r"^[\d,]+(?:/\d+)?[¥�]?$")

_DESCRIPTION = ("Handling {handling}, Accel {accel}, Speed Interval "
                "{speedInterval}, Top Speed {topSpeed}, Body {body}, "
                "Armor {armor}, Pilot {pilot}, Sensor {sensor}, Seats {seats}, "
                "Avail {availability}, Cost {price}¥")


#: How far LEFT of the detected table to crop. The ruled box covers only the
#: right-hand columns — find_tables() returns a bbox starting at BODY, so the
#: crop read "BODY ARM PILOT SENS SEAT AVAIL COST" and a seven-value row while
#: Handling, Accel, Speed Interval and Top Speed sat just outside it. That is
#: why 118 of Double Clutch's 178 stat tables produced nothing readable: not a
#: parsing fault, a framing one. 90pt reaches the start of the row; 160pt starts
#: dragging in the prose of the neighbouring column.
_PAD_LEFT = 90


def _pad(bbox, page):
    """Widen a table's box to the whole stat row, without leaving the page.

    The row sits just under the ruled header, so the crop is padded down 18pt,
    and out to the LEFT far enough to reach the first column (see _PAD_LEFT).
    pdfplumber REFUSES a crop that is not fully inside the page and raises
    ValueError, which the worker's except turns into "this book has no
    vehicles" — five books lost their entire scan to one bad table that way,
    three of them because find_tables() reported a NEGATIVE top on a rotated
    page.

    Clamping is the whole fix: a table cannot extend past the page it is on, so
    a box that claims to is wrong at the edges and right in the middle.
    """
    px0, ptop, px1, pbottom = page.bbox
    x0 = max(px0, min(bbox[0] - _PAD_LEFT, px1))
    top = max(ptop, min(bbox[1] - 2, pbottom))
    x1 = max(px0, min(bbox[2] + 4, px1))
    bottom = max(ptop, min(bbox[3] + 18, pbottom))
    if x1 - x0 < 1 or bottom - top < 1:
        return None
    return (x0, top, x1, bottom)


#: How far under a stat block its name may sit. Measured on Double Clutch's
#: callout boxes, where the gap runs about 40-65pt. Beyond that the "heading
#: below" is the next section, not this vehicle's name.
_LABEL_GAP = 90


def _label(candidates, bbox):
    """The heading that names the table at ``bbox``.

    Two layouts, and only one of them was ever handled. Double Clutch prints the
    stat block first with the vehicle's name UNDER it, so taking the nearest
    heading above labelled each block with the PREVIOUS vehicle's name, and
    discarded the block entirely when nothing was above. The core rulebook does
    the opposite — one heading over a long table — so a below-only rule names
    every corebook vehicle after the section that follows it.

    So: a heading close underneath wins, otherwise fall back to the one above.
    Both tests are confined to the table's own column, because on a two-column
    page the nearest heading by height alone is routinely in the other column,
    which is a different vehicle entirely.
    """
    x0, top, x1, _ = bbox
    left = x0 - _PAD_LEFT - 20          # the stat row starts left of the ruled box
    column = [c for c in candidates if left <= c[1] <= x1]
    below = [c for c in column if top < c[0] <= top + _LABEL_GAP]
    if below:
        return min(below, key=lambda c: c[0])[2]
    above = [c for c in column if c[0] < top]
    if above:
        return max(above, key=lambda c: c[0])[2]
    # nothing in this column: fall back to anything above, which is what the
    # single-column books need
    any_above = [c for c in candidates if c[0] < top]
    return max(any_above, key=lambda c: c[0])[2] if any_above else None


def read_statblock_vehicles(pdf_path, pages) -> list[dict]:
    """Splatbook stat blocks (Double Clutch etc.).

    The HAND ACC …/COST table is a ruled table interleaved with prose, so
    find_tables() locates it and a crop just below the header isolates the
    11-value row (no prose bleed). The vehicle name is the nearest 15pt
    display-font (Njord) heading above the table; the subtype is a
    '(racing motorcycle)'-style line near it.
    """
    import pdfplumber

    from extractor.describe import _lines as _L
    from extractor.normalize import normalize_text

    items = []
    # Adjacent tables' crops overlap, so the same printed row is read more than
    # once. Keyed on what identifies a vehicle in print — its name, its page and
    # its price — so a genuine variant listed at a different cost still counts.
    seen: set[tuple] = set()
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(
                         extra_attrs=["fontname", "size", "upright"])
                     if w.get("upright", True)]
            if not words:
                continue
            body = Counter(round(w["size"]) for w in words).most_common(1)[0][0]
            # names are display-font (Njord) words ~1.3x body; filter to those
            # first, then group into heading lines (prose shares the y-row
            # otherwise)
            heads, parens = [], []
            njord = [w for w in words
                     if "Njord" in w["fontname"] and w["size"] >= body * 1.3]
            for ln in _L(njord):
                text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                text = re.sub(r"\s*\(.*$", "", text).strip()
                if (1 <= len(text.split()) <= 6 and text[0:1].isupper()
                        and "HAND" not in text and not text.isdigit()):
                    heads.append((min(w["top"] for w in ln),
                                  min(w["x0"] for w in ln), text))
            for ln in _L(words):
                text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                pm = _PAREN.match(text)
                if pm:
                    parens.append((min(w["top"] for w in ln),
                                   min(w["x0"] for w in ln), pm.group(1).strip()))
            for tb in page.find_tables():
                # the table's own top, NOT the clamped one: it is what decides
                # which headings count as "above the table", and clamping that
                # would drag the cutoff onto the page edge
                top = tb.bbox[1]
                box = _pad(tb.bbox, page)
                if box is None:
                    continue        # degenerate table box — nothing to read
                crop = page.crop(box)
                # EVERY row in the crop, not just the first. The core rulebook
                # prints a catalogue: one table, a dozen vehicles, one per line.
                # Breaking at the first match read one of them and discarded the
                # rest, which is most of what that book has.
                for line in (crop.extract_text() or "").splitlines():
                    toks = normalize_text(line).strip().split()
                    # walk back from the end collecting stat cells; whatever is
                    # left in front is the vehicle's name, which is how the
                    # catalogue rows carry it
                    vals, i = [], len(toks)
                    while i > 0 and len(vals) < len(FIELDS) and _CELL.match(toks[i - 1]):
                        i -= 1
                        vals.insert(0, toks[i])
                    if len(vals) < len(FIELDS):
                        continue
                    lead = " ".join(toks[:i]).strip()
                    lead = re.sub(r"^\d+\s+", "", lead)      # a page number ran in
                    name = lead if len(lead) >= 3 else _label(heads, tb.bbox)
                    if not name or len(name) < 2:
                        continue
                    # drop 'ZZZZZ' sidebar bleed
                    name = re.sub(r"^[A-Z]{4,}\s+", "", name).strip()
                    if not name:
                        continue
                    subtype = _label(parens, tb.bbox) or "vehicle"
                    subkey = subtype.upper().replace(" ", "_").replace("/", "_")
                    system = {"type": "DRONE" if "DRONE" in subkey else "VEHICLE",
                              "subtype": subkey}
                    for k, v in zip(FIELDS, vals):
                        system[k] = (v.replace("¥", "").replace("�", "").strip()
                                     if k == "price" else v)
                    system["description"] = _DESCRIPTION.format(**system)
                    key = (name.casefold(), page_no, system["price"])
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append({"name": name, "system": system, "page": page_no})
    return items


def scan_book(job: tuple[str, str]) -> dict:
    """``(book, pdf)`` -> ``{"book", "found": [records], "pages": n, "errors"}``."""
    import pdfplumber

    from extractor.autodetect import _valid_name
    from extractor.quiet import quiet_pdf_noise

    quiet_pdf_noise()
    book, pdf = job
    try:
        with pdfplumber.open(pdf) as p:
            pages = [i for i, pg in enumerate(p.pages, 1)
                     if _HDR.search(pg.extract_text() or "")]
        if not pages:
            return {"book": book, "found": [], "pages": 0, "errors": []}
        found = [r for r in read_statblock_vehicles(pdf, pages)
                 if _valid_name(r["name"])]
        return {"book": book, "found": found, "pages": len(pages), "errors": []}
    except Exception as e:
        return {"book": book, "found": [], "pages": 0,
                "errors": [f"{book}: {type(e).__name__}: {e}"]}
