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
from extractor.bookprep import env_workers, map_jobs
from extractor.paths import data_root
from extractor.vehicle_scan import FIELDS
from extractor.vehicle_scan import scan_book as vehicle_scan_book
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
# FIELDS is imported from extractor.vehicle_scan, not defined twice: the worker
# builds records with it and this script reads them back, so a column order
# that drifted between the two would mislabel every stat silently.
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


#: A line that is only a number, a price or a wrapped price fragment. These sit
#: between the parts of a name and must not be mistaken for one — the Federated
#: Boeing Commuter has "350,000/" directly above its stat line.
_PRICEISH = re.compile(r"^[\d,./]+[¥�]?$")


def _name_part(line: str) -> bool:
    """Is this line a piece of a vehicle name that wrapped off the stat row?

    Names in the corebook's single-flow tables break across three lines, with
    the stats attached to the middle one:

        Saeder-                          <- prefix
        Krupp-Bentley  3/5 18 30 ...     <- the fragment that carries the stats
        Concordat                        <- suffix

    A part is short, has letters in it, and carries no stats of its own.
    """
    s = line.strip()
    if not s or len(s.split()) > 3:
        return False
    if _PRICEISH.match(s) or "HAND" in s or _CATLINE.match(s):
        return False
    return any(c.isalpha() for c in s)


def _join_name(head: str, tail: str) -> str:
    """Glue two halves of a wrapped name, respecting the break character.

    'Saeder-' + 'Krupp-Bentley' is one word; 'Proteus' + 'Lamprey' is two.
    """
    head = head.strip()
    return head + tail.strip() if head.endswith(("-", "/")) else f"{head} {tail.strip()}"


def _unwrap(lines, i, name, used):
    """Rebuild a wrapped name from the lines either side of the stat row.

    ``used`` holds the line indexes already spent on a name. Without it the
    trailing half of one vehicle becomes the leading half of the next — the
    "Nightrunner" ending Aztechnology's Sunrunner sits directly above the GMC
    Riverine's stat row, and got claimed by both.
    """
    # backwards: skip at most one price fragment, then take a name part
    for back in (1, 2):
        j = i - back
        if j < 0:
            break
        prev = lines[j].strip()
        if _PRICEISH.match(prev):
            continue                    # a wrapped price, keep looking
        if j not in used and _name_part(prev):
            name = _join_name(prev, name)
            used.add(j)
        break
    j = i + 1
    # A line ending in '-' or '/' OPENS the next name; it never closes this one.
    # "Saeder-" sits between Ford Americar's row and Krupp-Bentley's, and was
    # being taken as Americar's tail, leaving the Concordat without its marque.
    if (j < len(lines) and j not in used and _name_part(lines[j])
            and not lines[j].strip().endswith(("-", "/"))):
        name = _join_name(name, lines[j])
        used.add(j)
    return name


#: How much of a name has to match before a suffix counts as the same vehicle.
#: "Patroller" is eight characters and distinctive; anything shorter starts
#: matching things like "Van" or "Bus" to real vehicles.
_SUFFIX_MIN = 8


def _by_suffix(page_key: str, cl6_by_name: dict, claimed: set):
    """The Commlink6 row a page name belongs to when only the maker differs.

    Commlink6 records the full trade name and the books print the model alone:
    "Spinrad Global Street Rocket EX" against a heading of "Street Rocket EX",
    "Nissan Johnny Patroller" against "Patroller". An exact-name fold misses
    every one of those, so the stats stay stranded on a second row while the
    named row shows none.

    Only ever taken when exactly ONE unclaimed Commlink6 row ends with the name.
    "Bazoo Chrome" ends both "Krime Bazoo Chrome" and "Krime Big Bazoo Chrome",
    and guessing between them would attach a vehicle's stats to its larger
    sibling — so an ambiguous suffix is left alone rather than resolved.
    """
    if len(page_key) < _SUFFIX_MIN:
        return page_key, None
    hits = [k for k in cl6_by_name
            if k not in claimed and k != page_key and k.endswith(page_key)]
    if len(hits) != 1:
        return page_key, None
    return hits[0], cl6_by_name[hits[0]]


def fold_into_authority(byname: dict, cl6_by_name: dict):
    """Merge page-read vehicles into the Commlink6 rows that already name them.

    Commlink6 owns the identity; the page owns the stats. Commlink6 carries NO
    vehicle stat line at all — 421 of its vehicles have no handling, accel, top
    speed, body or armour — so the page-read row is the only place those numbers
    exist. Dropping it as "a duplicate" would delete the sole copy of the stats
    and leave a correctly-named, empty vehicle.

    So a page row whose name Commlink6 already owns is folded INTO that row: it
    keeps Commlink6's id, name and every field Commlink6 states, and fills only
    what Commlink6 leaves empty. That is the same asymmetry the authority guard
    applies, decided here where both rows are in hand.

    Returns ``(merged, folded)``; folded is ``[(read_as, kept_as, fields_filled)]``.
    """
    merged, folded = {}, []
    claimed: set[str] = set()
    for key, r in byname.items():
        auth = cl6_by_name.get(key)
        if auth is None:
            key, auth = _by_suffix(key, cl6_by_name, claimed)
        if auth is None:
            merged[key] = r
            continue
        claimed.add(key)
        row = json.loads(json.dumps(auth))          # never mutate the caller's row
        filled = [k for k, v in r["system"].items()
                  if str(row["system"].get(k, "") or "").strip() == ""
                  and str(v or "").strip() != ""]
        for k in filled:
            row["system"][k] = r["system"][k]
        merged[key] = {"name": row["name"], "system": row["system"],
                       "page": (row.get("meta") or {}).get("page") or r.get("page"),
                       "_id": row["id"], "_meta": row.get("meta"),
                       "_book": (row.get("meta") or {}).get("book")}
        folded.append((r["name"], row["name"], len(filled)))

    # Every Commlink6 vehicle the page reader did NOT find has to come through
    # too. This function's result is what gets written over vehicles.json, so
    # leaving them out silently deleted them: 423 of the 485 vehicles vanished
    # the moment this phase ran on its own, because Commlink6 lists hundreds
    # that no stat table in any book we own describes.
    for key, auth in cl6_by_name.items():
        if key in merged:
            continue
        merged[key] = {"name": auth["name"], "system": auth["system"],
                       "page": (auth.get("meta") or {}).get("page"),
                       "_id": auth["id"], "_meta": auth.get("meta"),
                       "_book": (auth.get("meta") or {}).get("book")}
    return merged, folded


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
            # kept as a list, not consumed lazily: a wrapped name needs the
            # lines either side of the one carrying the stats
            page_lines = [l.strip() for l in raw.splitlines() if l.strip()]
            used: set[int] = set()      # line indexes spent on a name
            for idx, line in enumerate(page_lines):
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
                name = _unwrap(page_lines, idx, name, used)
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
    # workers are spawned; without this each child re-runs this script
    import multiprocessing

    multiprocessing.freeze_support()
    reg = load_registry(DATA)
    from extractor.merge import norm_base
    byname = {}
    # corebook tables (broad subtypes) first
    # corebook supplies the ruled vehicle tables; without it the stat-block
    # pass below still runs over whatever books the user does own
    core = (reg.get("corebook") or {}).get("pdf") or ""
    for r in (read_vehicles(core, range(301, 307)) if _P(core).is_file() else []):
        byname[norm_base(r["name"])] = r
    for r in (read_vehicles_text(core, range(301, 307)) if _P(core).is_file() else []):
        byname.setdefault(norm_base(r["name"]), r)
    # Every other book: stat-block vehicles (fine subtypes from parens), read
    # several at a time. Merging stays here, one book at a time, so first-wins
    # order is unchanged.
    jobs = [(b, m.get("pdf", "")) for b, m in reg.items()
            if b not in ("corebook", "gun_rack", "rides")
            and _P(m.get("pdf", "")).is_file()]
    workers = env_workers()
    print(f"scanning {len(jobs)} book(s) with {workers} worker(s)", flush=True)

    seen_n = [0]

    def landed(r):
        seen_n[0] += 1
        for err in r.get("errors", []):
            print(f"  {err}", flush=True)
        print(f"scanned {r.get('book', '?')} ({r.get('pages', 0)} stat pages) "
              f"({seen_n[0]}/{len(jobs)})", flush=True)

    for r in map_jobs(vehicle_scan_book, jobs, workers, on_done=landed):
        # Stamp the book onto each record. The worker knows which book it read
        # but the records do not carry it, and the writer below used to label
        # EVERY vehicle "corebook" — so a Double Clutch drone claimed a corebook
        # page number that points at something else entirely.
        book = (r or {}).get("book") or LIBRARY
        for rec in (r or {}).get("found") or []:
            rec["_book"] = book
            byname.setdefault(norm_base(rec["name"]), rec)
    # Commlink6 owns the identity of any vehicle it names; the page owns the
    # stats. See fold_into_authority — the two are merged, NOT deduplicated,
    # because Commlink6 has no stat line at all and dropping the page row would
    # delete the only copy of the numbers.
    #
    # Read the existing rows BEFORE overwriting the file. On a first install
    # there is nothing to read and nothing is folded, which is correct: there is
    # no authority to defer to yet.
    out_path = DATA / LIBRARY / "vehicles" / "vehicles.json"
    cl6_by_name = {}
    if out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            cl6_by_name = {norm_base(i["name"]): i for i in existing.get("items", [])
                           if (i.get("meta") or {}).get("source") == "commlink6"
                           and (i.get("name") or "").strip()}
        except (OSError, ValueError, KeyError) as e:
            print(f"  (could not read existing vehicles for the Commlink6 check: {e})",
                  flush=True)

    byname, folded = fold_into_authority(byname, cl6_by_name)

    # Stats a PREVIOUS run read, kept for rows this run did not manage to read.
    #
    # The page reader is the only source of vehicle statistics — Commlink6 has
    # none — and its output is rebuilt from scratch every import. So a vehicle
    # whose stat block is read on Monday and missed on Tuesday (a caption that
    # scanned differently, a name that folded elsewhere) silently loses numbers
    # that were correct and are still printed in the book. 22 vehicles lost
    # theirs exactly this way. Re-reading is allowed to IMPROVE a row, never to
    # empty one.
    kept_stats = 0
    if out_path.is_file():
        try:
            prior = json.loads(out_path.read_text(encoding="utf-8")).get("items", [])
        except (OSError, ValueError):
            prior = []
        by_prior = {norm_base(i.get("name", "")): i for i in prior if i.get("name")}
        for key, rec in byname.items():
            was = (by_prior.get(key) or {}).get("system") or {}
            for field in FIELDS:
                if str(rec["system"].get(field) or "").strip():
                    continue                    # this run read it; that wins
                if str(was.get(field) or "").strip():
                    rec["system"][field] = was[field]
                    kept_stats += 1
    if kept_stats:
        print(f"kept {kept_stats} stat value(s) an earlier run had read and this "
              f"one did not", flush=True)

    if folded:
        # Named, not just counted: a silent merge is how a rule like this
        # quietly starts swallowing rows it should not.
        print(f"folded {len(folded)} page-read vehicle(s) into their Commlink6 row "
              f"(Commlink6 keeps every value it states):", flush=True)
        for was, now, n in sorted(folded, key=lambda t: t[1])[:15]:
            note = "" if was == now else f"   (read as {was!r})"
            print(f"    {now:38} +{n} field(s){note}", flush=True)
        if len(folded) > 15:
            print(f"    ... and {len(folded) - 15} more", flush=True)

    recs = sorted(byname.values(), key=lambda r: (r["system"]["subtype"], r["name"]))
    # vehicles are their own site domain (Eden treats them as actors, which are
    # out of scope here — this is browsable reference data, not exported).
    out = out_path                      # resolved above, for the Commlink6 check
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = set()
    items = []
    for r in recs:
        if r.get("_id"):
            # Folded into a Commlink6 row: keep ITS id and meta. A fresh id here
            # would leave the authority guard free to resurrect the original
            # alongside this one, and every manual correction keyed to that id
            # would stop finding its target.
            seen.add(r["_id"])
            items.append({"id": r["_id"], "name": r["name"],
                          "system": r["system"], "meta": r["_meta"]})
            continue
        sid = slugify(r["name"]) or "vehicle"
        k, s = 2, sid
        while s in seen:
            s = f"{sid}_{k}"; k += 1
        seen.add(s)
        # The book this row was actually read from. The corebook table passes
        # above leave _book unset, and LIBRARY is "corebook", so they are still
        # labelled correctly; only the stat-block books change.
        book = r.get("_book", LIBRARY)
        items.append({"id": s, "name": r["name"], "system": r["system"],
                      "meta": {"book": book, "page": r["page"],
                               "sources": [{"book": book, "page": r["page"]}],
                               "extractedAt": date.today().isoformat(),
                               "extractorVersion": extractor.__version__, "qaStatus": "extracted",
                               "descriptionFrom": book}})
    out.write_text(json.dumps({"book": LIBRARY, "domain": "vehicles", "category": "vehicles", "items": items},
                              indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} vehicles/drones")
    for it in items[:8]:
        print(f"  {it['name']:30} {it['system']['type']}/{it['system']['subtype']}")
