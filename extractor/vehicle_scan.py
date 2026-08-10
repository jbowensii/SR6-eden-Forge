"""Proposed replacement for ``extractor/vehicle_scan.py``.

Column-anchored, not table-shaped. The reader locates the *printed caption band*
(HAND / ACC / SPD INT / TOP SPD / BODY / ARM / PILOT / SENS / SEAT / AVAIL /
COST), converts each caption into an x anchor, and then assigns every token on
the rows beneath to the column whose cell it lands in.

Why not ``find_tables()``. The ruled box in these books covers only part of the
stat block, so a crop derived from it has to be nudged left and down by hand-
measured amounts, and the number of tokens recovered then has to be mapped onto
columns by counting. Counting cannot tell a genuine nine-column drone table from
an eleven-column car table that the crop clipped, which is the whole reason
every previous fix traded one set of rows for another. Column identity taken
from the printed caption removes the ambiguity: a table missing SPD INT is
missing it because the book did not print it.

Two page layouts are handled by the same code, because both print the same
captions:

* Double Clutch, Krime Katalog, Rides: a callout block, one vehicle, name in
  9pt Njord on the line(s) ABOVE the caption band with the subtype in
  parentheses on the last of them.
* Core rulebook: a catalogue, one caption band over a dozen rows, the name in a
  leading column on each row and sometimes wrapped onto the line above or below.

Cards (Rides, Tarnished Star) print the band in two halves, one over each half
of the row; halves that share an x-span and sit within 34pt are stitched back
together before the values are assigned.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

FIELDS = ["handling", "accel", "speedInterval", "topSpeed", "body", "armor",
          "pilot", "sensor", "seats", "availability", "price"]

_CAPTION = {
    "HAND": "handling", "HANDL": "handling", "HANDLING": "handling",
    "ACC": "accel", "ACCEL": "accel", "ACCELERATION": "accel",
    "SPDINT": "speedInterval", "SPEEDINTERVAL": "speedInterval",
    "SPDINTERVAL": "speedInterval", "SPEEDINT": "speedInterval",
    "TOPSPD": "topSpeed", "TOPSPEED": "topSpeed",
    "SPEED": "speed", "SPD": "speed",
    "BODY": "body", "BOD": "body",
    "ARM": "armor", "ARMOR": "armor", "ARMOUR": "armor",
    "PILOT": "pilot", "SENS": "sensor", "SENSOR": "sensor",
    "SENSE": "sensor", "SENSORS": "sensor",
    "SEAT": "seats", "SEATS": "seats",
    "AVAIL": "availability", "AVAILABILITY": "availability",
    "COST": "price", "PRICE": "price",
    "NAME": "_name", "VEHICLE": "_name", "MODEL": "_name",
    "DEVICERATING": "deviceRating",
}
#: fragments that are part of a caption but carry no column of their own
_NOISE = ("ONOFFROAD", "ONOFF", "OFFROAD", "ROAD", "ON", "OFF",
          "INTERVAL", "INT", "TOP", "S")
_VOCAB = sorted(set(_CAPTION) | set(_NOISE), key=len, reverse=True)

_DASHES = "\\-—–−"
_VALUE = re.compile(r"^[0-9" + _DASHES + r"]"
                    r"[0-9,./" + _DASHES + r"]*"
                    r"[FRfr]?[*†‡¥�]{0,3}$")
_DASHONLY = re.compile(r"^[" + _DASHES + r"·•]+$")
_WORDY = re.compile(r"^(Special|Spec|Varies|Var|Rating|N/A|NA)\*?$", re.I)
_PAREN = re.compile(r"^\((.{2,45})\)$")

_DESCRIPTION = ("Handling {handling}, Accel {accel}, Speed Interval "
                "{speedInterval}, Top Speed {topSpeed}, Body {body}, "
                "Armor {armor}, Pilot {pilot}, Sensor {sensor}, Seats {seats}, "
                "Avail {availability}, Cost {price}¥")


# --------------------------------------------------------------- primitives
def _norm(s):
    s = unicodedata.normalize("NFKD", s)
    return s.replace("’", "'").replace("�", "")


def _key(txt):
    return re.sub(r"[^A-Za-z]", "", txt).upper()


def _split_caption(key):
    """``'BODYARMPILOT'`` -> ``['BODY','ARM','PILOT']``; ``[]`` if not captions.

    pdfplumber joins captions that are set with no measurable gap, and shatters
    ones that are tightly kerned. Both happen inside the same book.
    """
    out, i, n = [], 0, len(key)
    while i < n:
        for v in _VOCAB:
            if key.startswith(v, i):
                out.append(v)
                i += len(v)
                break
        else:
            return []
    return out


def _is_value(t):
    t = t.replace("¥", "").replace("�", "").strip()
    return bool(t) and bool(_VALUE.match(t) or _DASHONLY.match(t))


def _cell_ok(t):
    return _is_value(t) or bool(_WORDY.match(t))


def _lines(words, tol=2.5):
    out = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        for ln in out:
            if abs(w["top"] - ln[0]["top"]) <= tol:
                ln.append(w)
                break
        else:
            out.append([w])
    for ln in out:
        ln.sort(key=lambda w: w["x0"])
    return sorted(out, key=lambda ln: min(w["top"] for w in ln))


# ------------------------------------------------------------------- bands
def _caption_words(words):
    caps = []
    for w in words:
        if not w.get("upright", True) or w["size"] >= 12:
            continue
        t = w["text"]
        if t != t.upper():
            continue
        k = _key(t)
        if k and len(k) <= 24 and len(k) == len(t.strip(".:()/")):
            caps.append((w, k))
    seeds = [w for w, k in caps if len(k) >= 3 and _split_caption(k)]
    if not seeds:
        return []
    keep = {id(w): w for w in seeds}
    for w, k in caps:
        if id(w) in keep or len(k) > 5:
            continue
        for s in seeds:
            if (abs(w["size"] - s["size"]) < 0.6
                    and abs(w["top"] - s["top"]) <= 9
                    and s["x0"] - 60 <= w["x0"] <= s["x1"] + 60):
                keep[id(w)] = w
                break
    return list(keep.values())


def _columns(band_words):
    ws = sorted(band_words, key=lambda w: w["x0"])
    runs = []
    for w in ws:
        if runs and w["x0"] - runs[-1]["x1"] <= 3.0:
            runs[-1]["x1"] = max(runs[-1]["x1"], w["x1"])
            runs[-1]["ws"].append(w)
        else:
            runs.append({"x0": w["x0"], "x1": w["x1"], "ws": [w]})
    cols = []
    for g in runs:
        parts = sorted(g["ws"], key=lambda w: (round(w["top"], 1), w["x0"]))
        toks = _split_caption("".join(_key(w["text"]) for w in parts))
        fields = [(_CAPTION.get(t), t) for t in toks]
        if not any(f for f, _ in fields):
            for w in parts:                       # a stray fragment joined in
                f = _CAPTION.get(_key(w["text"]))
                if f:
                    cols.append(((w["x0"] + w["x1"]) / 2.0, f, w["x0"], w["x1"]))
            continue
        if sum(1 for f, _ in fields if f) == 1:
            f = next(f for f, _ in fields if f)
            cols.append(((g["x0"] + g["x1"]) / 2.0, f, g["x0"], g["x1"]))
            continue
        # several captions printed with no gap: split the run by glyph count
        total = sum(len(t) for _, t in fields)
        span, cur = g["x1"] - g["x0"], g["x0"]
        for f, t in fields:
            wid = span * len(t) / total
            if f:
                cols.append((cur + wid / 2.0, f, cur, cur + wid))
            cur += wid
    return cols


def find_bands(words, line_gap=5.5):
    caps = _caption_words(words)
    if not caps:
        return []
    # Group captions in TWO dimensions, not by row alone. Two stat blocks in
    # neighbouring columns are routinely set 7pt apart vertically, so their
    # caption rows interleave; grouping by height merges them into one band
    # spanning the page and neither block is read. Captions inside a band are
    # never more than ~30pt apart horizontally, and the gutter is far wider.
    caps = sorted(caps, key=lambda w: (w["top"], w["x0"]))
    parent = list(range(len(caps)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, a in enumerate(caps):
        for j in range(i + 1, len(caps)):
            b = caps[j]
            if b["top"] - a["top"] > line_gap + 3.5:
                break
            if max(a["x0"], b["x0"]) - min(a["x1"], b["x1"]) <= 34:
                ra, rb = find(i), find(j)
                if ra != rb:
                    parent[ra] = rb
    buckets = {}
    for i, w in enumerate(caps):
        buckets.setdefault(find(i), []).append(w)
    groups = list(buckets.values())
    bands = []
    for ws in groups:
        seen, order = set(), []
        for cx, f, cx0, cx1 in sorted(_columns(ws)):
            if f not in seen:
                seen.add(f)
                order.append((cx, f, cx0))
        if len([f for f in seen if not f.startswith("_")]) < 4:
            continue
        bands.append({"captop": min(w["top"] for w in ws),
                      "top": max(w["bottom"] for w in ws),
                      "x0": min(w["x0"] for w in ws),
                      "x1": max(w["x1"] for w in ws),
                      "order": order,
                      "fields": {f for f in seen if not f.startswith("_")}})
    return _pair_halves(bands)


def _pair_halves(bands):
    """Stitch a card's two caption half-bands into one logical table.

    Rides and Tarnished Star print HAND..ARM over one row and PILOT..COST over
    the next. Read separately they yield two half vehicles per card.
    """
    bands.sort(key=lambda b: b["captop"])
    used = set()
    out = []
    for i, b in enumerate(bands):
        if i in used:
            continue
        mate = None
        for j in range(i + 1, len(bands)):
            c = bands[j]
            if j in used or c["captop"] - b["top"] > 34:
                continue
            overlap = min(b["x1"], c["x1"]) - max(b["x0"], c["x0"])
            if overlap < 0.5 * min(b["x1"] - b["x0"], c["x1"] - c["x0"]):
                continue
            if b["fields"] & c["fields"]:
                continue
            if len(b["fields"]) >= 9 or len(c["fields"]) >= 9:
                continue
            mate = j
            break
        b = dict(b)
        b["halves"] = [bands[i]]
        if mate is not None:
            used.add(mate)
            b["halves"].append(bands[mate])
            b["fields"] = b["fields"] | bands[mate]["fields"]
        used.add(i)
        out.append(b)
    # a priced table is a catalogue of vehicles; an unpriced one is a rules
    # table (chassis / powertrain / propulsion), and reading it yields rows
    # like 'Personal Watercraft 4' that are build options, not vehicles
    return [b for b in out if "price" in b["fields"] and len(b["fields"]) >= 6]


def _cells(order, pad=40):
    """Cell x-bounds. The FIRST cell starts at its own caption's left edge, not
    at anchor-minus-a-guess: catalogue names run wide ('Yamaha Growler') and a
    guessed boundary puts the tail of the name in the Handling column, which
    then reads 'Growler 3/3' and takes the whole row down with it."""
    xs = [x for x, _, _ in order]
    fs = [f for _, f, _ in order]
    c0 = [c for _, _, c in order]
    out = []
    for i, x in enumerate(xs):
        lo = (xs[i - 1] + x) / 2 if i else min(c0[0] - 4, x - 4)
        hi = (x + xs[i + 1]) / 2 if i + 1 < len(xs) else x + pad
        out.append((lo, hi, fs[i]))
    return out


# -------------------------------------------------------------------- names
#: fonts the books set vehicle names in (everything else on the page is prose)
_NAMEFONT = ("Njord",)
_SUB_TAIL = re.compile(r"\s*\(p\.\s*\d+.*?\)\s*$", re.I)


def _name_lines(words, band, page_body, above=True, gap=48, floor=None,
                relaxed=False, body_family=None):
    """The display-font lines that name a block, read outward from the band."""
    if above:
        sel = [w for w in words
               if w["bottom"] <= band["captop"] + 0.5
               and band["captop"] - w["bottom"] < gap]
    else:
        base = floor if floor is not None else band["top"]
        sel = [w for w in words if w["top"] >= base - 0.5
               and w["top"] - base < gap]
    sel = [w for w in sel
           if w["x1"] > band["x0"] - 12 and w["x0"] < band["x1"] + 12
           and w.get("upright", True)]
    if not sel:
        return []
    # Drop the page's body face before forming lines. A name is always set in
    # a face the surrounding prose does not use -- Njord over Amplitude in the
    # main books, a bold sans over a serif in the re-typeset ones -- and
    # keeping the prose in means a two-column page hands back the paragraph
    # that happens to share the name's baseline.
    if body_family:
        kept = [w for w in sel if body_family not in w["fontname"]]
        if kept:
            sel = kept
    lns = _lines(sel)
    if above:
        lns = lns[-3:][::-1]
    else:
        lns = lns[:3]
    out = []
    for ln in lns:
        # never mistake a neighbouring block's caption row for a name: it is
        # bold and small, which is exactly the shape a re-typeset book uses
        # for its names
        if sum(1 for w in ln if _split_caption(_key(w["text"]))) > len(ln) / 2:
            continue
        txt = _norm(" ".join(w["text"] for w in ln)).strip()
        fam = Counter(w["fontname"].split("+")[-1] for w in ln).most_common(1)[0][0]
        size = max(w["size"] for w in ln)
        # a name is set apart from the prose around it: a display face, a
        # larger size, or -- in the re-typeset books, where the whole stat
        # block is smaller than the body text -- a bold face at caption size
        display = (any(f in fam for f in _NAMEFONT)
                   or size > page_body + 1.5
                   or (relaxed and "Bold" in fam and size < page_body - 1.5))
        out.append({"text": txt, "display": display, "size": size})
    return out


def _display_name(words, band, page_body, gap=48, floor=None,
                  body_family=None):
    """Name and subtype for a callout block, whichever side the book prints on.

    Double Clutch sets the name in 9pt Njord directly ABOVE the caption band,
    with '(heavy ATV)' under it -- not, as the old reader assumed, in a 15pt
    display face UNDERNEATH. The 15pt lines are the write-up's section headings,
    which is why keying on them named blocks after the wrong vehicle. The Rides
    card deck does print the name below, so both directions are tried.
    """
    for relaxed, side in ((False, True), (False, False),
                          (True, True), (True, False)):
        name, subtype = None, None
        for ln in _name_lines(words, band, page_body, above=side, gap=gap,
                              floor=floor, relaxed=relaxed,
                              body_family=body_family):
            txt = ln["text"]
            m = _PAREN.match(txt)
            if m and subtype is None:
                subtype = m.group(1).strip()
                continue
            if not ln["display"]:
                break
            if txt.islower() and len(txt.split()) == 1:
                continue                       # the 'stats' label on a card
            core = _SUB_TAIL.sub("", txt)
            core = re.sub(r"\s*\(.*$", "", core).strip()
            if 2 <= len(core) <= 60 and not core.isdigit():
                # keep walking outward: a name routinely runs to two lines,
                # 'Yamaha' over 'Kaburaya' on a card, 'Saeder-Krupp' over
                # 'Aerospace Blitz Mk II' in the book
                name = (core + " " + name) if (name and side) else \
                       ((name + " " + core) if name else core)
                continue
        if name:
            if subtype:
                subtype = _SUB_TAIL.sub("", subtype).strip()
                subtype = re.sub(r",\s*(p\.|dc|cr)\b.*$", "", subtype).strip()
            return name, subtype
    return None, None


# ------------------------------------------------------------------- reader
def read_page(page, min_fill=0.6, max_rows=40, gap_stop=26, name_left=70):
    """``page`` is a dict: ``{"no", "words"}`` (word dicts from pdfplumber)."""
    words = [w for w in page["words"] if w.get("upright", True)]
    bands = find_bands(words)
    if not bands:
        return []
    out = []
    for band in bands:
        halves = band.get("halves", [band])
        rows_by_half = []
        for h in halves:
            rows_by_half.append(_rows_under(words, h, bands, min_fill,
                                            max_rows, gap_stop, name_left))
        base = rows_by_half[0]
        for extra in rows_by_half[1:]:
            for k, r in enumerate(extra):
                if k < len(base):
                    base[k]["vals"].update(r["vals"])
                    if r["lead"] and not base[k]["lead"]:
                        base[k]["lead"] = r["lead"]
        bot = max([h["top"] for h in halves]
                  + [r["top"] for rs in rows_by_half for r in rs] + [0])
        for r in base:
            r["band"] = band
            r["blockbot"] = bot + 10
        out.extend(base)
    return out


def _rows_under(words, band, all_bands, min_fill, max_rows, gap_stop, name_left):
    bounds = _cells(band["order"])
    statfs = [f for _, _, f in bounds if not f.startswith("_")]
    first_lo = min(lo for lo, _, f in bounds if not f.startswith("_"))
    below = [b["captop"] for b in all_bands
             if b["captop"] > band["top"] + 2
             and b["x1"] > band["x0"] and b["x0"] < band["x1"]]
    limit = min(below) - 2 if below else 1e9
    cand = [w for w in words
            if band["top"] + 0.5 < w["top"] < limit
            and w["x1"] > band["x0"] - name_left and w["x0"] < band["x1"] + 12]
    rows, orphans, prev_bottom, n = [], [], band["top"], 0
    rowsize = [None]
    for ln in _lines(cand):
        ltop = min(w["top"] for w in ln)
        if ltop - prev_bottom > gap_stop:
            break
        vals, name_ws, stray = {}, [], 0
        for w in ln:
            t = _norm(w["text"]).strip()
            cx = (w["x0"] + w["x1"]) / 2
            if w["x1"] <= first_lo:
                name_ws.append(w)
                continue
            hit = next((f for lo, hi, f in bounds if lo <= cx < hi), None)
            if hit is None or hit.startswith("_"):
                name_ws.append(w)
                continue
            if hit in vals:
                vals[hit] += " " + t
            elif _cell_ok(t):
                vals[hit] = t
            else:
                stray += 1
                vals[hit] = t
        # the vehicle's name is set in the SAME face as its numbers. Anything
        # else to the left of the table is the neighbouring column's prose,
        # which is how 'smart-tires). And' ended up naming a vehicle.
        stat_ws = [w for w in ln if w not in name_ws]
        ref = (sorted(w["size"] for w in stat_ws)[len(stat_ws) // 2]
               if stat_ws else None)
        if ref is not None:
            name_ws = [w for w in name_ws if abs(w["size"] - ref) <= 0.6]
        name_toks = [_norm(w["text"]).strip() for w in
                     sorted(name_ws, key=lambda w: w["x0"])]
        filled = sum(1 for f in statfs if f in vals)
        numeric = sum(1 for f in statfs if f in vals and _is_value(vals[f]))
        ok = (filled >= max(4, int(len(statfs) * min_fill))
              and numeric >= max(3, int(len(statfs) * 0.5))
              and stray <= 2)
        mid = (ltop + max(w["bottom"] for w in ln)) / 2
        if not ok:
            # a name that wrapped off its row: park it and decide later which
            # row it belongs to. Appending it to the NEXT row is wrong half the
            # time -- 'Harley-Davidson / <stats> / Scorpion' brackets its row,
            # so the trailing half would otherwise name the vehicle after it.
            txt = " ".join(name_toks).strip()
            if txt and not vals and 2 < len(txt) < 60 and rowsize[0]:
                if abs(max(w["size"] for w in ln) - rowsize[0]) <= 0.6:
                    orphans.append((mid, txt))
                prev_bottom = max(w["bottom"] for w in ln)
                continue
            if n:
                break
            prev_bottom = max(w["bottom"] for w in ln)
            continue
        if rowsize[0] is None and ref is not None:
            rowsize[0] = ref
        rows.append({"lead": " ".join(name_toks).strip(), "vals": vals,
                     "top": ltop, "mid": mid})
        n += 1
        prev_bottom = max(w["bottom"] for w in ln)
        if n >= max_rows:
            break
    # attach each orphan name line to the nearest value row
    if rows:
        # a wrapped name attaches only to a row that carries no name of its
        # own: in these catalogues a name either sits ON its row or wraps
        # AROUND it, never both, so 'GMC Banshee' cannot also collect the
        # 'Federated Boeing' underneath it
        blank = [r for r in rows if not r["lead"]] or rows
        for mid, txt in orphans:
            r = min(blank, key=lambda r: abs(r["mid"] - mid))
            if abs(r["mid"] - mid) > 30:
                continue
            r.setdefault("wrap", []).append((mid, txt))
        for r in rows:
            if "wrap" not in r:
                continue
            before = [t for m, t in sorted(r["wrap"]) if m < r["mid"]]
            after = [t for m, t in sorted(r["wrap"]) if m >= r["mid"]]
            r["lead"] = " ".join(before + ([r["lead"]] if r["lead"] else [])
                                 + after).strip()
    return rows


# ----------------------------------------------------------------- records
_JUNK = re.compile(r"^(page|table|total|notes?|standard|upgrades?)\b", re.I)


def records_for_page(page):
    words = [w for w in page["words"] if w.get("upright", True)]
    if not words:
        return []
    body = Counter(round(w["size"]) for w in words).most_common(1)[0][0]
    fam = Counter(w["fontname"].split("+")[-1] for w in words
                  if round(w["size"]) == body).most_common(1)[0][0]
    out = []
    rows = read_page(page)
    # for a card layout the name sits under the LAST row, so the search floor
    # is the bottom of the block, not the caption band
    floor = {}
    for r in rows:
        k = id(r["band"])
        floor[k] = max(floor.get(k, 0), r["blockbot"])
    for r in rows:
        band = r["band"]
        name = re.sub(r"^\d+\s+", "", r["lead"]).strip()
        name = re.sub(r"^[A-Z]{4,}\s+", "", name).strip()
        dn, subtype = _display_name(words, band, body, gap=56,
                                    floor=floor.get(id(band)),
                                    body_family=fam)
        if len(name) < 3:
            name = dn
        if not name or len(name) < 3 or _JUNK.match(name):
            continue
        if name == name.upper() and _split_caption(_key(name)):
            continue        # the caption row itself, read as a name
        # a vehicle name is a name, not a sentence. Books whose stat block is
        # set SMALLER than the body text (the re-typeset ones) have no font
        # signal to separate the name from the paragraph beside it, so shape
        # has to do the work: no clause commas, no trailing sentence, and no
        # more than six words.
        if ", " in name or len(name.split()) > 8 or re.search(r"[.;:]\s+[A-Z]",
                                                              name):
            continue
        system = {}
        for k, v in r["vals"].items():
            if k == "price":
                v = v.replace("¥", "").replace("�", "").strip()
            elif v.strip() in ("�", "¥"):
                v = "—"
            system[k] = v
        sub = (subtype or "vehicle").upper().replace(" ", "_").replace("/", "_")
        system["subtype"] = sub
        system["type"] = "DRONE" if "DRONE" in sub else "VEHICLE"
        system["description"] = _DESCRIPTION.format(
            **{f: system.get(f, "—") for f in FIELDS})
        out.append({"name": name, "system": system, "page": page["no"]})
    return out


# ------------------------------------------------------------ plausibility
def implausible(system):
    """Reasons a row cannot be a real vehicle. Empty list == plausible."""
    bad = []

    def num(f):
        v = str(system.get(f, "")).replace(",", "").replace("¥", "")
        v = v.split("/")[0]
        m = re.match(r"^\d+", v)
        return int(m.group()) if m else None

    h = num("handling")
    if h is not None and not 0 <= h <= 12:
        bad.append(f"handling={system['handling']}")
    for f, hi in (("body", 250), ("armor", 60), ("pilot", 12), ("sensor", 12)):
        v = num(f)
        if v is not None and not 0 <= v <= hi:
            bad.append(f"{f}={system[f]}")
    ts = num("topSpeed")
    if ts is not None and not 1 <= ts <= 10000:
        bad.append(f"topSpeed={system['topSpeed']}")
    ac = num("accel")
    if ac is not None and not 0 <= ac <= 500:
        bad.append(f"accel={system['accel']}")
    pr = num("price")
    if pr is not None and not 100 <= pr <= 50_000_000_000:
        bad.append(f"price={system['price']}")
    st = num("seats")
    if st is not None and not 0 <= st <= 1000:
        bad.append(f"seats={system['seats']}")
    return bad


# ------------------------------------------------------- worker entry points
#
# Everything above works on a page as a plain dict of words, so it can be tested
# and profiled without a PDF. The two functions below are the only part that
# touches pdfplumber, and they keep the signatures the pipeline already calls.
#
# `read_statblock_vehicles` lives HERE, not in tools/ingest_vehicles.py: spawn
# re-imports the module a worker target came from, so a function defined in a
# script would make every child re-execute that script from the top. An earlier
# version guessed it into extractor.double_clutch, where there is no such name,
# and the worker's broad except turned the ImportError into "this book has no
# vehicles" fifty times over while the phase reported success.

_WORD_ATTRS = ["fontname", "size", "upright"]


def _page_dict(page, page_no: int) -> dict:
    return {"no": page_no,
            "words": [w for w in page.extract_words(extra_attrs=_WORD_ATTRS)
                      if w.get("upright", True)]}


def read_statblock_vehicles(pdf_path, pages) -> list[dict]:
    """Every stat block on the given 1-based pages of one book."""
    import pdfplumber

    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            items += records_for_page(_page_dict(pdf.pages[page_no - 1], page_no))
    return items


#: A name that is really a stray value or a section label. Deliberately narrow.
#: ``autodetect._valid_name`` is the general-purpose gear-name test and it is far
#: too strict for vehicles: it threw out "Eurocar Northstar 2.0", "Gaz-Niki
#: P-183", "GD/CAS MacArthur" and "Ranger class battlecruiser" -- 40 real
#: vehicles in Double Clutch alone -- for having a decimal point, a hyphenated
#: model code, a slash or a lower-case word. What actually needs rejecting is a
#: price that landed in the name column and the "krime prowler: sr5 stats"
#: captions that head a rules table.
_NOT_A_NAME = re.compile(r"^[\d,.]+\s*[¥�]?$|:")


def _named(record: dict) -> bool:
    name = (record.get("name") or "").strip()
    return bool(name) and len(name) >= 3 and not _NOT_A_NAME.search(name)


def scan_book(job: tuple[str, str]) -> dict:
    """``(book, pdf)`` -> ``{"book", "found": [records], "pages": n, "errors"}``.

    One pass, not two. The old reader ran a regex over every page's text to
    decide where to look and then re-read those pages; finding the caption band
    IS the test for whether a page carries stat blocks, so the words are
    extracted once and used for both. That makes this cheaper than the pass it
    replaces despite reading far more.
    """
    import pdfplumber

    from extractor.quiet import quiet_pdf_noise

    quiet_pdf_noise()
    book, pdf = job
    try:
        found, pages = [], 0
        with pdfplumber.open(pdf) as doc:
            for page_no, page in enumerate(doc.pages, 1):
                data = _page_dict(page, page_no)
                if not data["words"] or not find_bands(data["words"]):
                    continue
                pages += 1
                found += records_for_page(data)
        return {"book": book, "found": [r for r in found if _named(r)],
                "pages": pages, "errors": []}
    except Exception as e:
        # one unreadable book must not take the other forty-nine with it
        return {"book": book, "found": [], "pages": 0,
                "errors": [f"{book}: {type(e).__name__}: {e}"]}
