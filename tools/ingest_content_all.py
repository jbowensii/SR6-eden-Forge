"""Run every content reader over every book — efficiently. Each book's page text
is extracted ONCE to find which pages carry each content type's signature; each
reader then runs only on its signature pages. Results merge into the library:
dedup by name (reprints add a source reference), garbage names rejected,
blank-filled. corebook stays the canonical seed."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import glob
import json
import re
from datetime import date

import fitz
import pdfplumber

import extractor
from extractor.autodetect import _valid_name
from extractor.emit import slugify
from extractor.ingest import LIBRARY, fill_blank_fields, load_registry
from extractor.merge import norm_base
from extractor.normalize import dedouble
from extractor.eden_align import ALIGNERS

_RAW_FIELDS = ("cost", "gameEffect", "keywords", "descriptor", "spellType", "damage")


def _align(domain, system):
    """Convert a reader's raw system block to the Eden shape at ingest, so the
    library never carries un-aligned content (spells/qualities/adept_powers/
    rituals). Non-raw extras are preserved; corebook seed is untouched (skipped)."""
    if domain not in ALIGNERS:
        return system
    keep = {k: v for k, v in system.items() if k not in _RAW_FIELDS}
    return {**keep, **ALIGNERS[domain](system)}
from extractor.spells import read_spells
from extractor.rituals import read_rituals
from extractor.adept_powers import read_adept_powers
from extractor.toxins_drugs import read_toxins_drugs
from extractor.qualities import read_qualities
from extractor.actors import read_actors, read_npc_blocks
from extractor.critters import read_critters
from extractor.spirits import read_spirits

DATA = _P(__file__).resolve().parent.parent / "data"
S = re.compile
# domain -> (reader, signature, base_fields, group_by, extra_filter)
DOMAINS = {
    # base_fields for aligner-backed domains are the EDEN string fields (the raw
    # reader fields cost/gameEffect/descriptor/… are converted by eden_align at
    # ingest, below, so they must NOT be blank-filled back in).
    "spells": (read_spells, S(r"RANGE\s+TYPE\s+DURATION\s+DV"),
               ("description",), "category", None),
    "rituals": (read_rituals, S(r"Threshold:\s*\d"),
                ("description",), "category", None),
    "adept_powers": (read_adept_powers, S(r"Cost:\s*[\d.]+\s*PP"),
                     ("activation", "description"), "category", None),
    "qualities": (read_qualities, S(r"(?:Cost|Bonus):\s*\d+\s*Karma"),
                  ("explain", "description"), "category", None),
    "npcs": (read_npc_blocks, re.compile(r"Metatype:|B\s+A\s+R\s+S\s+W\s+L\s+I\s+C\s+EDG", re.I),
             ("metatype", "activeSkills", "knowledgeSkills", "qualities", "gear",
              "weapons", "augmentations", "description"), "category", None),
    "critters": (read_critters, S(r"\bB A R S W L I C (?:M )?ESS\b"),
                 ("skills", "powers", "movement", "description"), "category", None),
    "spirits": (read_spirits, S(r"Optional Powers:"),
                ("powers", "optionalPowers", "attacks", "description"), "category", None),
    # toxins/drugs are folded into gear as type=CHEMICALS (subtype TOXIN/DRUG),
    # not their own domains — see tools/merge_chemicals.py. Do not re-add here.
}
SKIP = {"gun_rack", "rides", "corebook"}

reg = load_registry(DATA)
books = [(k, v["pdf"]) for k, v in reg.items() if k not in SKIP and _P(v.get("pdf", "")).is_file()]

# collect new records per domain across all books
collected = {d: [] for d in DOMAINS}
for book, pdf in books:
    with pdfplumber.open(pdf) as p:
        texts = [(i, dedouble(page.extract_text() or "")) for i, page in enumerate(p.pages, 1)]
    npages = len(texts)
    for domain, (reader, sig, *_rest) in DOMAINS.items():
        pages = set()
        for i, t in texts:
            if sig.search(t):
                pages.update((i - 1, i, i + 1))
        pages = sorted(x for x in pages if 1 <= x <= npages)
        if not pages:
            continue
        try:
            for rec in reader(pdf, pages):
                rec["_book"] = book
                collected[domain].append(rec)
        except Exception as e:
            print(f"  {book}/{domain}: {e}")
    print(f"scanned {book}")

# merge each domain into the library
for domain, (_r, _s, base, group_by, extra) in DOMAINS.items():
    files = {_P(f).stem: json.load(open(f, encoding="utf-8"))["items"] for f in glob.glob(f"data/{LIBRARY}/{domain}/*.json")}
    existing = {norm_base(it["name"]): it for items in files.values() for it in items}
    seen_ids = {it["id"] for items in files.values() for it in items}
    added = refs = 0
    for rec in collected[domain]:
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
        base_id = slugify(name) or "item"
        sid, k = base_id, 2
        while sid in seen_ids:
            sid = f"{base_id}_{k}"; k += 1
        seen_ids.add(sid)
        item = {"id": sid, "name": name, "system": _align(domain, rec["system"]),
                "meta": {"book": book, "page": rec["page"], "sources": [{"book": book, "page": rec["page"]}],
                         "extractedAt": date.today().isoformat(), "extractorVersion": extractor.__version__,
                         "qaStatus": "extracted",
                         **({"descriptionFrom": book} if rec["system"].get("description") else {})}}
        cat = str(item["system"].get(group_by, "item")).lower()
        files.setdefault(cat, []).append(item)
        existing[key] = item
        added += 1
    fill_blank_fields([i for v in files.values() for i in v], base, group_by)
    out_dir = DATA / LIBRARY / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    for cat, items in files.items():
        (out_dir / f"{cat}.json").write_text(
            json.dumps({"book": LIBRARY, "domain": domain, "category": cat, "items": items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{domain:14} +{added} new, {refs} reprint-refs")
print("done")
