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
from extractor.bookprep import env_workers, map_jobs
from extractor.content_scan import DOMAINS, SKIP, scan_book
from extractor.paths import data_root, positional
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
# DOMAINS / SKIP / scan_book live in extractor.content_scan so a worker
# process can import them WITHOUT re-executing this script.
DATA = data_root()          # --data / SR6_DATA / <repo>/data

def _main() -> None:
    """Everything that actually does work.

    Guarded because the book scan runs in worker processes: spawn
    re-imports the module a target came from, and for a script that means
    re-executing it top to bottom — so an unguarded pool here would start
    another scan in every child, and another in every grandchild.
    """
    reg = load_registry(DATA)
    _only = set(positional())          # optional: restrict to specific book slugs (scoped run)
    books = [(k, v["pdf"]) for k, v in reg.items()
             if k not in SKIP and _P(v.get("pdf", "")).is_file() and (not _only or k in _only)]

    # Collect new records per domain across all books — several books at a time.
    # This walks every page of every owned book, depends on nothing but the PDFs,
    # and used to run on one core: the single slowest step of the whole import.
    collected = {d: [] for d in DOMAINS}
    _workers = env_workers()
    print(f"scanning {len(books)} book(s) with {_workers} worker(s)", flush=True)

    _seen = [0]


    def _landed(r):
        _seen[0] += 1
        for err in r.get("errors", []):
            print(f"  {err}", flush=True)
        # the phase's only sign of life; the builder shows it beside the bar
        print(f"scanned {r.get('book', '?')}  ({_seen[0]}/{len(books)})", flush=True)


    for r in map_jobs(scan_book, books, _workers, on_done=_landed):
        for domain, recs in (r.get("found") or {}).items():
            collected.setdefault(domain, []).extend(recs)

    # merge each domain into the library
    for domain, (_r, _s, base, group_by, extra) in DOMAINS.items():
        files = {_P(f).stem: json.load(open(f, encoding="utf-8"))["items"] for f in glob.glob(str(DATA / LIBRARY / domain / "*.json"))}
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


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    _main()
