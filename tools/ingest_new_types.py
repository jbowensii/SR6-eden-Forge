"""Extract the 10 further Eden item types across all registered books.

Two families:
  • PDF-scan domains — a reader runs on each book's signature pages
    (complex forms, echoes, metamagics, contacts, martial styles/techniques,
    sprite powers, foci).
  • Harvest domains — distinct powers mined out of already-extracted actor
    blocks (critter powers ← critters, sprite powers ← spirits) plus the
    constructed SIN catalog.

Merges into the corebook library namespace: dedup by normalized name (a second
book becomes a source reference), garbage names rejected, string fields
blank-filled. corebook stays the canonical seed. Pass book slugs as argv to
limit the scan (default: all). No book content lives here."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import glob
import json
import re
from datetime import date

import pdfplumber

import extractor
from extractor.bookprep import env_workers, map_jobs
from extractor.newtype_scan import (MARTIAL, MARTIAL_BOOKS,
                                    MARTIAL_RANGES, SKIP, XBOOK,
                                    scan_book)
from extractor.paths import data_root, positional
from extractor.autodetect import _valid_name
from extractor.emit import slugify
from extractor.ingest import LIBRARY, fill_blank_fields, load_registry
from extractor.merge import norm_base
from extractor.normalize import dedouble
from extractor.glossary import read_glossary
from extractor.newtypes import (
    read_complexforms, read_echoes, read_contacts,
    read_martial_styles, read_martial_techs, read_foci, read_critter_powers,
)

DATA = data_root()          # --data / SR6_DATA / <repo>/data
def S(pattern: str):
    """Case-insensitive signature pattern — used once per domain below."""
    return re.compile(pattern, re.I)

META_STOP = {"metamagic", "metamagics", "initiation", "initiate grade", "magic",
             "mentor spirits", "the awakened world", "adept powers", "astral perception",
             "focus types", "enchanting foci", "metamagic foci", "power foci",
             "spell foci", "spirit foci", "weapon foci", "qi foci"}
SPRITE_STOP = {"sprites", "sprite powers", "matrix", "registering a sprite",
               "types of sprites", "sprite characteristics", "registered sprite tasks",
               "the basics", "matrix history", "submersion", "echoes",
               "sprite-technomancer link", "sprite example", "courier sprite",
               "crack sprite", "data sprite", "fault sprite", "machine sprite"}

# str-only base fields per domain (for blank-filling the editor's slots)
BASE = {
    "complexforms": ("fading", "duration", "skill", "target", "description"),
    "echoes": ("description",),
    "metamagics": ("description",),
    "sprite_powers": ("duration", "skill", "description"),
    "foci": ("force", "availability", "price", "description"),
    "martial_arts": ("techniques", "description"),
    "martial_techniques": ("style", "choice", "description"),
    "contacts": ("type", "pronouns", "description"),
    "critter_powers": ("duration", "action", "type", "range", "description"),
    "sins": ("quality", "description"),
}

# corebook is the canonical seed: extract its new-type content from KNOWN page
# ranges (precise, no signature noise). reader -> pages.
COREBOOK = {
    "complexforms": (read_complexforms, range(190, 193)),
    "echoes": (read_echoes, range(195, 197)),
    "metamagics": (lambda p, pg: read_glossary(p, pg, "METAMAGIC", stop=META_STOP, max_words=4),
                   [168, 169, 170]),
    "sprite_powers": (lambda p, pg: read_glossary(p, pg, "SPRITE_POWER", stop=SPRITE_STOP, max_words=4),
                      [194, 195]),
    "foci": (read_foci, [295]),
    "critter_powers": (read_critter_powers, range(222, 228)),  # glossary w/ stats+desc
}

# other books: only domains whose per-entry signature is reliable enough to scan
# blind. (Adventure/plot books mostly have none of this, so yields are small.)
# Martial arts (Deadly Arts): BEST-EFFORT import over the technique chapter by
# range (font+size detection isolates 13pt display-font entry names). The chapter
# interleaves cyberweapon/polearm gear in the same font and SR6 has no clean style
# catalog, so martial_techniques carries some gear names that need a human review
# pass. Styles stay empty (the "styles" chapter is motivation essays, not a catalog).


def merge_write(domain, collected, base_fields, group_by):
    files = {_P(f).stem: json.load(open(f, encoding="utf-8"))["items"]
             for f in glob.glob(str(DATA / LIBRARY / domain / "*.json"))}
    existing = {norm_base(it["name"]): it for items in files.values() for it in items}
    seen_ids = {it["id"] for items in files.values() for it in items}
    added = refs = 0
    for rec in collected:
        name, book = rec["name"], rec["_book"]
        if not _valid_name(name):
            continue
        key = norm_base(name)
        if key in existing:
            e = existing[key]
            srcs = e["meta"].setdefault("sources", [{"book": e["meta"]["book"], "page": e["meta"]["page"]}])
            if not any(s["book"] == book for s in srcs):
                srcs.append({"book": book, "page": rec["page"]}); refs += 1
            continue
        base_id, k = slugify(name) or "item", 2
        sid = base_id
        while sid in seen_ids:
            sid = f"{base_id}_{k}"; k += 1
        seen_ids.add(sid)
        item = {"id": sid, "name": name, "system": rec["system"],
                "meta": {"book": book, "page": rec["page"],
                         "sources": [{"book": book, "page": rec["page"]}],
                         "extractedAt": date.today().isoformat(),
                         "extractorVersion": extractor.__version__, "qaStatus": "extracted",
                         **({"descriptionFrom": book} if rec["system"].get("description") else {})}}
        cat = str(item["system"].get(group_by, "item")).lower()
        files.setdefault(cat, []).append(item)
        existing[key] = item
        added += 1
    fill_blank_fields([i for v in files.values() for i in v], base_fields, group_by)
    out_dir = DATA / LIBRARY / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    for cat, items in files.items():
        (out_dir / f"{cat}.json").write_text(
            json.dumps({"book": LIBRARY, "domain": domain, "category": cat, "items": items},
                       indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(v) for v in files.values())
    print(f"{domain:18} +{added} new, {refs} refs  (total {total})")


def harvest_powers(actor_domain, out_domain, category):
    """Mine distinct power names out of extracted actor blocks' powers fields."""
    names = {}
    for f in glob.glob(str(DATA / LIBRARY / actor_domain / "*.json")):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            for field in ("powers", "optionalPowers"):
                blob = it["system"].get(field) or ""
                for raw in re.split(r"[,;]", blob):
                    nm = re.sub(r"\s*\([^)]*\)", "", raw).strip()          # drop "(rating)" notes
                    nm = re.sub(r"\s+\d+$", "", nm).strip(" .")            # drop trailing rating
                    if nm.endswith("-") or len(nm) < 3:
                        continue                                            # dehyphenation fragment
                    if not (3 <= len(nm) <= 40) or not _valid_name(nm) or nm[0].isdigit():
                        continue
                    names.setdefault(norm_base(nm), (nm, it["meta"]["book"], it["meta"]["page"]))
    recs = [{"name": nm, "system": {"category": category}, "page": pg, "_book": bk}
            for nm, bk, pg in names.values()]
    return recs


def constructed_sins():
    recs = [{"name": "Real SIN", "page": 246, "_book": LIBRARY,
             "system": {"category": "SIN", "quality": "REAL_SIN", "rating": 6,
                        "description": "A legitimate System Identification Number issued by a "
                                       "government or megacorporation."}}]
    for r in range(1, 7):
        recs.append({"name": f"Fake SIN (Rating {r})", "page": 246, "_book": LIBRARY,
                     "system": {"category": "SIN", "quality": "FAKE_SIN", "rating": r,
                                "description": f"A forged SIN of Rating {r}. Detected on a check that "
                                               f"beats its rating; higher rating resists better."}})
    return recs


if __name__ == "__main__":
    only = set(sys.argv[1:])
    reg = load_registry(DATA)
    books = [(k, v["pdf"]) for k, v in reg.items()
             if k not in SKIP and (not only or k in only) and _P(v.get("pdf", "")).is_file()]

    collected = {d: [] for d in set(COREBOOK) | set(XBOOK) | set(MARTIAL)}

    # corebook: precise page ranges
    if any(b == "corebook" for b, _ in books):
        core_pdf = reg["corebook"]["pdf"]
        for domain, (reader, pages) in COREBOOK.items():
            try:
                for rec in reader(core_pdf, list(pages)):
                    rec["_book"] = "corebook"
                    collected[domain].append(rec)
            except Exception as e:
                print(f"  corebook/{domain}: {e}")
        print("scanned corebook (curated ranges)")

    # Other books: reliable-signature scan, several at a time.
    #
    # This phase only began doing any work in 0.9.2 -- the frozen dispatcher
    # never ran it before, so it looked instant because it did nothing. Reading
    # every page of every owned book on one core is twenty minutes that nobody
    # had budgeted for. The scan depends on nothing but the PDF; the merge
    # below still happens once, here.
    jobs = [(b, pdf) for b, pdf in books if b != "corebook"]
    workers = env_workers()
    print(f"scanning {len(jobs)} book(s) with {workers} worker(s)", flush=True)

    seen = [0]

    def landed(r):
        seen[0] += 1
        for err in r.get("errors", []):
            print(f"  {err}", flush=True)
        print(f"scanned {r.get('book', '?')}  ({seen[0]}/{len(jobs)})", flush=True)

    for r in map_jobs(scan_book, jobs, workers, on_done=landed):
        for domain, recs in ((r or {}).get("found") or {}).items():
            collected.setdefault(domain, []).extend(recs)

    for domain in sorted(collected):
        merge_write(domain, collected[domain], BASE.get(domain, ("description",)), "category")

    # harvest domains (no PDF) — mine powers out of the extracted actor blocks.
    # Spirits use the same power glossary as critters (Eden files both under
    # critterpower), so both feed critter_powers. Matrix sprite powers stay the
    # glossary-only set above.
    crit_pwr = (harvest_powers("critters", "critter_powers", "CRITTER_POWER")
                + harvest_powers("spirits", "critter_powers", "CRITTER_POWER"))
    merge_write("critter_powers", crit_pwr, BASE["critter_powers"], "category")
    merge_write("sins", constructed_sins(), BASE["sins"], "category")
    print("done")
