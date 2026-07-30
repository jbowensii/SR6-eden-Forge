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
from datetime import date
import pdfplumber
import extractor
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

DATA = _P("data")
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


if __name__ == "__main__":
    reg = load_registry(DATA)
    from extractor.merge import norm_base
    recs = read_vehicles(reg["corebook"]["pdf"], range(301, 307))
    byname = {norm_base(r["name"]): r for r in recs}
    for r in read_vehicles_text(reg["corebook"]["pdf"], range(301, 307)):  # union: fill gaps
        byname.setdefault(norm_base(r["name"]), r)
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
