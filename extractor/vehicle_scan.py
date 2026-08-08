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
                    heads.append((min(w["top"] for w in ln), text))
            for ln in _L(words):
                text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                pm = _PAREN.match(text)
                if pm:
                    parens.append((min(w["top"] for w in ln), pm.group(1).strip()))
            for tb in page.find_tables():
                x0, top, x1, bottom = tb.bbox
                crop = page.crop((x0 - 2, top - 2, x1 + 2, bottom + 18))
                vals = None
                for line in (crop.extract_text() or "").splitlines():
                    toks = normalize_text(line).strip().split()
                    stat = [t for t in toks if _CELL.match(t)]
                    if len(stat) >= 10:
                        vals = stat[:11]
                        break
                if not vals:
                    continue
                above = [t for t in heads if t[0] < top]
                name = max(above, key=lambda t: t[0])[1] if above else None
                if not name or len(name) < 2:
                    continue
                # drop 'ZZZZZ' sidebar bleed
                name = re.sub(r"^[A-Z]{4,}\s+", "", name).strip()
                sub = [pp for pp in parens if pp[0] < top]
                subtype = max(sub, key=lambda t: t[0])[1] if sub else "vehicle"
                subkey = subtype.upper().replace(" ", "_").replace("/", "_")
                vals = (vals + [""] * 11)[:11]
                system = {"type": "DRONE" if "DRONE" in subkey else "VEHICLE",
                          "subtype": subkey}
                for k, v in zip(FIELDS, vals):
                    system[k] = (v.replace("¥", "").replace("�", "").strip()
                                 if k == "price" else v)
                system["description"] = _DESCRIPTION.format(**system)
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
