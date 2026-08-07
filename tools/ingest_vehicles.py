"""Extract the corebook vehicle + drone catalog (p302-303 tables) into gear as
type=VEHICLE / DRONE. Rows are either single-line ("Name  h a s ts b a p s seat
avail cost") or split around the stat line (the name wraps above/below it); both
are handled. Stats map to HAND/ACCEL/SPEED INTERVAL/TOP SPEED/BODY/ARMOR/PILOT/
SENSOR/SEAT/AVAIL/COST. Writes into the gear domain via domain_lib."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import json
import re
from collections import Counter
from datetime import date
import pdfplumber
import extractor
from extractor.paths import data_root, positional
from extractor.emit import slugify
from extractor.ingest import LIBRARY, load_registry
from extractor.normalize import normalize_text
from extractor.describe import _lines


def _column_lines(page):
    """Vehicle tables sit in a two-column page layout; extract_text reads them in
    the wrong order. Reconstruct lines per column (left then right) by x-position."""
    words = [w for w in page.extract_words(extra_attrs=["size", "upright"]) if w.get("upright", True)]
    mid = page.width / 2
    out = []
    for lo, hi in ((0, mid), (mid, page.width)):
        for ln in _lines([w for w in words if lo <= (w["x0"] + w["x1"]) / 2 < hi]):
            out.append(normalize_text(" ".join(w["text"] for w in ln)).strip())
    return out

DATA = data_root()
FIELDS = ["handling", "accel", "speedInterval", "topSpeed", "body", "armor",
          "pilot", "sensor", "seats", "availability", "price"]
CATS = {  # section header -> (subtype, is_drone)
    "BIKES": ("BIKE", False), "CARS": ("CAR", False), "TRUCKS AND VANS": ("TRUCK", False),
    "BOATS": ("BOAT", False), "SUBMARINES": ("SUBMARINE", False),
    "FIXED-WING AIRCRAFT": ("FIXED_WING", False), "ROTORCRAFT": ("ROTORCRAFT", False),
    "VTOL/VSTOL": ("VTOL", False), "MICRODRONES": ("MICRODRONE", True),
    "MINIDRONES": ("MINIDRONE", True), "SMALL DRONES": ("SMALL_DRONE", True),
    "MEDIUM DRONES": ("MEDIUM_DRONE", True), "LARGE DRONES": ("LARGE_DRONE", True),
}
_CATLINE = re.compile(r"^(" + "|".join(re.escape(c) for c in CATS) + r")\b")
_STAT = re.compile(r"^([\d,]+[¥�]?|\d+/\d+|\d+|[–\-�])$")  # stat/cost/fraction/dash


def _is_stat(tok):
    return bool(_STAT.match(tok))


def _split_row(line):
    """Return (name, [stats]) if the line ends in >=10 stat tokens, else None."""
    toks = line.split()
    i = len(toks)
    while i > 0 and _is_stat(toks[i - 1]):
        i -= 1
    stats = toks[i:]
    if len(stats) < 10:
        return None
    return " ".join(toks[:i]).strip(), stats


def _cat_of(cell):
    key = re.sub(r"\s+", " ", normalize_text(str(cell or "")).replace("\n", " ")).strip().upper()
    return key if key in CATS else None


def read_vehicles(pdf_path, pages):
    """Use ruled-table extraction: each vehicle/drone is a row whose columns line
    up under HAND/ACCEL/…/COST. Category header rows (col1 == 'HAND') switch the
    current section; data rows carry the name in col0 and 11 stats after."""
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            cat = None
            for tbl in pdf.pages[page_no - 1].extract_tables():
                for row in tbl:
                    if not row or not row[0]:
                        continue
                    c0 = normalize_text(str(row[0]).replace("\n", " ")).strip()
                    if len(row) > 1 and str(row[1]).strip().upper().startswith("HAND"):
                        cat = _cat_of(c0) or cat          # header row -> switch section
                        continue
                    if cat is None:
                        continue
                    stats = [normalize_text(str(c)).replace("\n", " ").strip() if c else "" for c in row[1:]]
                    if sum(1 for s in stats if re.search(r"\d", s)) < 8:
                        continue                           # not a real data row
                    name = re.sub(r"^\d+\s+", "", c0).strip()
                    if len(name) < 2:
                        continue
                    subtype, is_drone = CATS[cat]
                    stats = (stats + [""] * 11)[:11]
                    system = {"type": "DRONE" if is_drone else "VEHICLE", "subtype": subtype}
                    for k, v in zip(FIELDS, stats):
                        system[k] = v.replace("¥", "").strip() if k == "price" else v
                    system["description"] = ("Handling {handling}, Accel {accel}, Speed Interval {speedInterval}, "
                                             "Top Speed {topSpeed}, Body {body}, Armor {armor}, Pilot {pilot}, "
                                             "Sensor {sensor}, Seats {seats}, Avail {availability}, Cost {price}¥").format(**system)
                    items.append({"name": name, "system": system, "page": page_no})
    return items


def read_vehicles_text(pdf_path, pages):
    """Token pass over raw text — deep on the single-flow ground/water tables
    (p302) that ruled-table extraction under-reads. Unioned with read_vehicles."""
    _CATTEXT = re.compile(r"^(BIKES|CARS|TRUCKS AND VANS|BOATS|SUBMARINES|FIXED-WING|"
                          r"ROTORCRAFT|VTOL/VSTOL|MICRODRONES|MINIDRONES|SMALL DRONES|"
                          r"MEDIUM DRONES|LARGE DRONES)\b")
    ALIAS = {"FIXED-WING": "FIXED-WING AIRCRAFT"}
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            raw = normalize_text(pdf.pages[page_no - 1].extract_text() or "")
            cat = None
            for line in [l.strip() for l in raw.splitlines() if l.strip()]:
                cm = _CATTEXT.match(line)
                if cm:
                    cat = ALIAS.get(cm.group(1), cm.group(1))
                    cat = cat if cat in CATS else None
                    continue
                if "HAND" in line:
                    continue
                r = _split_row(line)
                if not r or cat is None or not r[0]:
                    continue
                name = re.sub(r"^\d+\s+", "", r[0]).strip()
                if len(name) < 2:
                    continue
                subtype, is_drone = CATS[cat]
                stats = (r[1][:11] + [""] * 11)[:11]
                system = {"type": "DRONE" if is_drone else "VEHICLE", "subtype": subtype}
                for k, v in zip(FIELDS, stats):
                    system[k] = v.replace("¥", "").strip() if k == "price" else v
                system["description"] = ("Handling {handling}, Accel {accel}, Speed Interval {speedInterval}, "
                                         "Top Speed {topSpeed}, Body {body}, Armor {armor}, Pilot {pilot}, "
                                         "Sensor {sensor}, Seats {seats}, Avail {availability}, Cost {price}¥").format(**system)
                items.append({"name": name, "system": system, "page": page_no})
    return items


_PAREN = re.compile(r"^\(([^)]{2,40})\)\s*$")
_VALUES = re.compile(r"^[\d]+(?:/\d+)?(?:\s+[\d,]+(?:/\d+)?){9,10}[¥�]?$")


def read_statblock_vehicles(pdf_path, pages):
    """Splatbook stat blocks (Double Clutch etc.): the HAND ACC …/COST table is a
    ruled table interleaved with prose, so find_tables() locates it and a crop
    just below the header isolates the 11-value row (no prose bleed). The vehicle
    name is the nearest 15pt display-font (Njord) heading above the table; the
    subtype is a '(racing motorcycle)'-style line near it."""
    from extractor.describe import _lines as _L
    items = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            words = [w for w in page.extract_words(extra_attrs=["fontname", "size", "upright"])
                     if w.get("upright", True)]
            if not words:
                continue
            body = Counter(round(w["size"]) for w in words).most_common(1)[0][0]
            # names are display-font (Njord) words ~1.3x body; filter to those
            # first, then group into heading lines (prose shares the y-row otherwise)
            heads, parens = [], []
            njord = [w for w in words if "Njord" in w["fontname"] and w["size"] >= body * 1.3]
            for ln in _L(njord):
                text = normalize_text(" ".join(w["text"] for w in ln)).strip()
                text = re.sub(r"\s*\(.*$", "", text).strip()
                if 1 <= len(text.split()) <= 6 and text[0:1].isupper() and "HAND" not in text and not text.isdigit():
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
                    stat = [t for t in toks if re.match(r"^[\d,]+(?:/\d+)?[¥�]?$", t)]
                    if len(stat) >= 10:
                        vals = stat[:11]
                        break
                if not vals:
                    continue
                above = [t for t in heads if t[0] < top]
                name = max(above, key=lambda t: t[0])[1] if above else None
                if not name or len(name) < 2:
                    continue
                name = re.sub(r"^[A-Z]{4,}\s+", "", name).strip()   # drop 'ZZZZZ' sidebar bleed
                sub = [pp for pp in parens if pp[0] < top]
                subtype = max(sub, key=lambda t: t[0])[1] if sub else "vehicle"
                subkey = subtype.upper().replace(" ", "_").replace("/", "_")
                vals = (vals + [""] * 11)[:11]
                system = {"type": "DRONE" if "DRONE" in subkey else "VEHICLE", "subtype": subkey}
                for k, v in zip(FIELDS, vals):
                    system[k] = v.replace("¥", "").replace("�", "").strip() if k == "price" else v
                system["description"] = ("Handling {handling}, Accel {accel}, Speed Interval {speedInterval}, "
                                         "Top Speed {topSpeed}, Body {body}, Armor {armor}, Pilot {pilot}, "
                                         "Sensor {sensor}, Seats {seats}, Avail {availability}, Cost {price}¥").format(**system)
                items.append({"name": name, "system": system, "page": page_no})
    return items


if __name__ == "__main__":
    reg = load_registry(DATA)
    from extractor.merge import norm_base
    from extractor.autodetect import _valid_name
    _HDR = re.compile(r"HAND\s+ACC(EL)?\b|PILOT\s+SENS")
    byname = {}
    # corebook tables (broad subtypes) first
    for r in read_vehicles(reg["corebook"]["pdf"], range(301, 307)):
        byname[norm_base(r["name"])] = r
    for r in read_vehicles_text(reg["corebook"]["pdf"], range(301, 307)):
        byname.setdefault(norm_base(r["name"]), r)
    # every other book: stat-block vehicles (fine subtypes from parens)
    import pdfplumber as _pp
    for book, meta in reg.items():
        pdf = meta.get("pdf", "")
        if book in ("corebook", "gun_rack", "rides") or not _P(pdf).is_file():
            continue
        try:
            with _pp.open(pdf) as p:
                pages = [i for i, pg in enumerate(p.pages, 1) if _HDR.search(pg.extract_text() or "")]
            if not pages:
                continue
            for r in read_statblock_vehicles(pdf, pages):
                if _valid_name(r["name"]):
                    byname.setdefault(norm_base(r["name"]), r)
            print(f"scanned {book} ({len(pages)} stat pages)", flush=True)
        except Exception as e:
            print(f"  {book}: {e}", flush=True)
    recs = sorted(byname.values(), key=lambda r: (r["system"]["subtype"], r["name"]))
    # vehicles are their own site domain (Eden treats them as actors, which are
    # out of scope here — this is browsable reference data, not exported).
    out = DATA / LIBRARY / "vehicles" / "vehicles.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    items = []
    for r in recs:
        sid = slugify(r["name"]) or "vehicle"
        k, s = 2, sid
        while s in seen:
            s = f"{sid}_{k}"; k += 1
        seen.add(s)
        items.append({"id": s, "name": r["name"], "system": r["system"],
                      "meta": {"book": "corebook", "page": r["page"],
                               "sources": [{"book": "corebook", "page": r["page"]}],
                               "extractedAt": date.today().isoformat(),
                               "extractorVersion": extractor.__version__, "qaStatus": "extracted",
                               "descriptionFrom": "corebook"}})
    out.write_text(json.dumps({"book": LIBRARY, "domain": "vehicles", "category": "vehicles", "items": items},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} vehicles/drones")
    for it in items[:8]:
        print(f"  {it['name']:30} {it['system']['type']}/{it['system']['subtype']}")
