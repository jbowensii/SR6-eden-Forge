"""Rebuild the item library under the ownership-gated workflow.

    python tools/import_library.py                 # plan only, writes nothing
    python tools/import_library.py --apply         # do it
    python tools/import_library.py --apply --book firing_squad

The rule: a PDF is proof of ownership, and nothing imports without one.

For each book, in publication order, :mod:`extractor.ownership` decides:

``both``  the PDF is present and Commlink6 has the book. The jar data goes in
          first — it is already structured and typed — then the PDF is read to
          fill what the jar does not carry.
``pdf``   the PDF is present with no Commlink6 counterpart. Read the PDF alone.
          This is how a new release works on the day it is published.
``skip``  no PDF. Nothing is imported, whatever the jar holds.

Where both sources give a value for the same field and they disagree, the
disagreement is recorded on the item as ``meta.conflicts`` rather than settled
silently. Two independent transcriptions of one book are a QA asset, and the
places they differ are exactly where a human should look.

Dry run by default. This rewrites the library, so it asks to be asked twice.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.commlink6 import DEFAULT_JAR, read_book
from extractor.commlink6_convert import to_item
from extractor.identity import IdLock, stamp_catalog_ids
from extractor.ingest import (CURATED, LIBRARY, ingest_book, load_library,
                              load_registry, write_library)
from extractor.bookprep import default_workers, prepare_books
from extractor.ownership import plan_import
from extractor.quiet import quiet_pdf_noise
from extractor.reconcile import reconcile_library

def import_commlink6(data_root: _P, book: str, jar_book: str, jar: _P) -> dict:
    """Load one book's Commlink6 items into the library, replacing prior rows.

    ``to_item`` returns THREE values -- ``(domain, file, item)``. This unpacked
    two of them, so every single record raised ValueError straight into a bare
    ``except Exception: continue`` and the import landed zero Commlink6 rows
    while cheerfully reporting success. Commlink6 is the authority here, so
    that quietly emptied the half of the library that matters most.

    Two lessons are baked in below: the records are grouped by DOMAIN, because
    one book's records do not all belong to the same library file; and a record
    that cannot be converted is counted and reported rather than dropped on the
    floor.
    """
    recs = read_book(jar_book, jar)

    by_domain: dict[str, dict[str, list]] = {}
    failures: dict[str, int] = {}
    for rec in recs.values():
        try:
            dom, file_, item = to_item(rec, jar_book)
        except Exception as e:                  # counted, never silent
            failures[f"{type(e).__name__}: {e}"] = (
                failures.get(f"{type(e).__name__}: {e}", 0) + 1)
            continue
        if not dom or not file_ or not item:
            failures["converter returned nothing"] = (
                failures.get("converter returned nothing", 0) + 1)
            continue
        item.setdefault("meta", {})
        item["meta"].update(book=book, source="commlink6")
        by_domain.setdefault(dom, {}).setdefault(file_, []).append(item)

    # Idempotent across EVERY domain already on disk, not just the ones this
    # run produces — otherwise a book that stops yielding, say, spells leaves
    # its old spell rows behind forever.
    existing = set()
    lib_dir = data_root / LIBRARY
    if lib_dir.is_dir():
        existing = {d.name for d in lib_dir.iterdir() if d.is_dir()}

    added = 0
    for dom in sorted(existing | set(by_domain)):
        library, envelopes = load_library(data_root, dom)
        for cat in list(library):
            library[cat] = [
                i for i in library[cat]
                if not (i.get("meta", {}).get("book") == book
                        and i.get("meta", {}).get("source") == "commlink6")
            ]
        for cat, items in by_domain.get(dom, {}).items():
            library.setdefault(cat, []).extend(items)
            added += len(items)
        write_library(data_root, dom, library, envelopes)

    return {"jarItems": added, "read": len(recs), "failures": failures,
            "domains": sorted(by_domain)}


def _snapshot(data_root: _P, book: str, domain: str = "gear") -> dict:
    """This book's Commlink6 rows, keyed by name, before the PDF pass runs."""
    library, _ = load_library(data_root, domain)
    out: dict[str, list[dict]] = {}
    for cat, items in library.items():
        rows = [i for i in items
                if (i.get("meta") or {}).get("book") == book
                and (i.get("meta") or {}).get("source") == "commlink6"]
        if rows:
            out[cat] = [json.loads(json.dumps(r)) for r in rows]
    return out


def _reconcile_book(data_root: _P, book: str, before: dict,
                    domain: str = "gear") -> dict:
    """Fold the pre-PDF jar rows back over what the PDF pass produced.

    ingest_book rewrites this book's rows from the page. Anything the jar
    declared that the page does not carry would be lost, so the two readings
    are reconciled here and disagreements recorded on the item.
    """
    if not before:
        return {"conflicts": 0}
    library, envelopes = load_library(data_root, domain)
    total = 0
    for cat, jar_rows in before.items():
        pdf_rows = [i for i in library.get(cat, [])
                    if (i.get("meta") or {}).get("book") == book]
        others = [i for i in library.get(cat, [])
                  if (i.get("meta") or {}).get("book") != book]
        merged, stats = reconcile_library(jar_rows, pdf_rows)
        library[cat] = others + merged
        total += stats["conflicts"]
    write_library(data_root, domain, library, envelopes)
    return {"conflicts": total}


#: Everything that has to happen AFTER the per-book merge to reach the state
#: the curated library is in. Same order as tools/rebuild_all.py, which is the
#: order that reproduces it — descriptions before subtypes because the subtype
#: inference reads descriptions, and corrections dead last so a manual fix
#: always wins.
#:
#: merge_commlink6.py is deliberately NOT here. It imports Commlink6 wholesale
#: for every book it covers, regardless of whether the PDF is present, which is
#: exactly the ownership rule this pipeline exists to enforce. The gated
#: equivalent is import_commlink6() above, run per book from the plan.
POST_PHASES: list[tuple[str, str, list[str]]] = [
    # more of the book: domains the gear pass does not produce
    ("Content: spells, qualities, NPCs, critters, spirits",
     "ingest_content_all.py", []),
    ("New types: complex forms, foci, contacts, SINs",
     "ingest_new_types.py", []),
    ("Vehicles and drones", "ingest_vehicles.py", []),
    # repair systematic mis-filing before anything reads the types
    ("Reclassify over-typed electronics", "reclassify_electronics.py", ["--apply"]),
    ("Repair gear type/subtype", "fix_gear_types.py", ["--apply"]),
    ("Fix cyberware CYBER_BODYWARE type", "fix_cyberware_bodyware.py", ["--apply"]),
    ("Re-file mis-filed weapons", "refile_misfiled_weapons.py", ["--apply"]),
    # descriptions
    ("Descriptions: writeup extractor", "rebuild_descriptions.py", ["--apply"]),
    ("Descriptions: spell layout", "fill_list_descriptions.py",
     ["--domain=spells", "--apply"]),
    ("Descriptions: complex-form layout", "fill_list_descriptions.py",
     ["--domain=complexforms", "--apply"]),
    ("Descriptions: critter-power layout", "fill_list_descriptions.py",
     ["--domain=critter_powers", "--apply"]),
    ("Descriptions: ritual layout", "fill_list_descriptions.py",
     ["--domain=rituals", "--apply"]),
    ("Descriptions: notes and prose tail", "fill_prose_tail.py", ["--apply"]),
    ("Descriptions: recover malformed entries",
     "fix_corrected_descriptions.py", ["--apply"]),
    # subtypes read descriptions, so they come after
    ("Subtypes: firearms from source tables",
     "subtype_firearms_from_book.py", ["--apply"]),
    ("Subtypes: infer blank gear subtypes", "infer_gear_subtypes.py", ["--apply"]),
    # LAST, always: a manual correction outranks anything a reader inferred
    ("Re-apply manual corrections", "apply_corrections.py", ["--apply"]),
]

#: Slow, and it changes artwork rather than item counts, so it is opt-in.
GRAPHICS_PHASES: list[tuple[str, str, list[str]]] = [
    ("Book graphics", "dump_book_images.py", []),
    ("Auto-pair artwork", "pair_art.py", []),
]


def run_post_phases(data_root: _P, phases, on_line=print) -> list[str]:
    """Run the post-merge phases against ``data_root``.

    Several of these tools resolve ``data/`` relative to the working directory
    and others relative to the repo, so BOTH are pinned: cwd is the folder that
    contains the library, and SR6_DATA names it outright. Without that they
    quietly rebuilt the developer's copy instead of the user's workspace.
    """
    import os
    import subprocess

    here = _P(__file__).resolve().parent
    env = {**os.environ, "SR6_DATA": str(data_root), "PYTHONUNBUFFERED": "1"}
    failed: list[str] = []

    for n, (label, script, args) in enumerate(phases, 1):
        path = here / script
        if not path.is_file():
            on_line(f"[{n}/{len(phases)}] {script} missing — skipped")
            continue
        on_line(f"[{n}/{len(phases)}] {label}")
        r = subprocess.run([sys.executable, "-u", str(path), *args],
                           cwd=str(data_root.parent), env=env)
        if r.returncode:
            # one bad phase must not lose the rest, but it must be VISIBLE
            on_line(f"    !! {script} exited {r.returncode}")
            failed.append(script)
    return failed


def run(data_root: _P, jar: _P | None, only: str | None, apply: bool,
        workers: int = 1, post: bool = True, graphics: bool = False) -> int:
    quiet_pdf_noise()          # or the log is all FontBBox and nothing else
    plan = plan_import(data_root, jar)
    if only:
        plan = [p for p in plan if p["book"] == only]
        if not plan:
            print(f"no such book: {only}")
            return 1

    counts = collections.Counter(p["source"] for p in plan)
    print(f"{'book':22} {'source':7} {'commlink6':18} {'items':>6}")
    for p in plan:
        print(f"  {p['book']:20} {p['source']:7} {str(p['jarBook'] or '-'):18} {p['items']:>6}")
    print(f"\n{counts['both']} both · {counts['pdf']} pdf-only · {counts['skip']} skipped")

    skipped = [p["book"] for p in plan if p["source"] == "skip"]
    if skipped:
        print(f"\nnot imported (no PDF, so ownership is not established):")
        for b in skipped:
            print(f"    {b}")

    if not apply:
        print("\n(dry run — nothing written. Re-run with --apply)")
        return 0

    reg = load_registry(data_root)
    totals = collections.Counter()
    todo = [p for p in plan if p["source"] != "skip"]

    # ---- read every book's pages, several books at a time -------------------
    # This is the part that took hours: pdfplumber walking every page, and
    # nothing in it depends on the library. The merge below stays strictly
    # serial and in plan order, so Commlink6 keeps precedence over the page.
    library, _ = load_library(data_root, "gear")
    lib_text = " ".join(i["name"] + " " + i["system"].get("description", "")
                        for cat in library.values() for i in cat)
    jobs = [{"book": p["book"], "pdf": reg[p["book"]]["pdf"],
             "curated": p["book"] in CURATED, "libText": lib_text}
            for p in todo]

    n_read = [0]

    def _read(r):
        n_read[0] += 1
        note = f"ERROR: {r['error']}" if r["error"] else f"{r['pages']} pages"
        print(f"[{n_read[0]}/{len(jobs)}] {r['book']} read  {note}", flush=True)

    print(f"\nreading {len(jobs)} book(s) with {workers} worker(s)", flush=True)
    prepared = prepare_books(jobs, workers, on_done=_read)

    # ---- merge, one book at a time, in plan order ---------------------------
    print(f"\nmerging {len(todo)} book(s)", flush=True)
    for n, p in enumerate(todo, 1):
        book = p["book"]
        # A COMPLETE line BEFORE the work, not a partial one after it. This was
        # printed with end="" ahead of the slow pass, so the newline that ends
        # it only arrived once the book had finished -- and anything reading
        # this stream a line at a time saw nothing at all in between.
        print(f"[{n}/{len(todo)}] {book} merging", flush=True)
        try:
            if p["source"] == "both":
                st = import_commlink6(data_root, book, p["jarBook"], jar)
                totals["jarItems"] += st["jarItems"]
                head = f"commlink6 {st['jarItems']:>5} items"
                if st["failures"]:
                    worst = max(st["failures"].items(), key=lambda kv: kv[1])
                    totals["jarFailed"] += sum(st["failures"].values())
                    print(f"    !! {sum(st['failures'].values())} of {st['read']} "
                          f"Commlink6 records did not convert — {worst[0]}",
                          flush=True)
            else:
                head = "pdf-only"
            # the PDF pass fills what the jar lacks and always supplies prose.
            # ingest_book merges into the same library, so reconciliation
            # happens against rows already carrying meta.source == "commlink6".
            before = _snapshot(data_root, book)
            st = ingest_book(data_root, book, prepared=prepared.get(book))
            rec = _reconcile_book(data_root, book, before)
            totals["new"] += st.get("new", 0)
            totals["descriptions"] += st.get("descriptions", 0)
            totals["conflicts"] += rec["conflicts"]
            print(f"[{n}/{len(todo)}] {book} done  {head}"
                  f"  +pdf new={st.get('new', 0)} desc={st.get('descriptions', 0)}"
                  f" conflicts={rec['conflicts']}", flush=True)
        except SystemExit as e:
            print(f"[{n}/{len(todo)}] {book} done  SKIP: {e}", flush=True)
        except Exception as e:  # one bad book must not lose the whole run
            print(f"[{n}/{len(todo)}] {book} done  "
                  f"ERROR: {type(e).__name__}: {e}", flush=True)

    # ---- the rest of the book -----------------------------------------------
    # The gear pass and Commlink6 between them do not produce spells, critters,
    # NPCs, contacts, vehicles or any of the smaller domains, and nothing so far
    # has filled a description. Running only the merge left a library about a
    # fifth the size of the curated one, which is what "the import does not look
    # like the backup" came down to. These phases run BEFORE ids are minted, so
    # everything they add is stamped too.
    phase_failures: list[str] = []
    if post:
        phases = list(POST_PHASES) + (list(GRAPHICS_PHASES) if graphics else [])
        print(f"\nfinishing the library — {len(phases)} phase(s)", flush=True)
        phase_failures = run_post_phases(
            data_root, phases, on_line=lambda s: print(s, flush=True))

    # every record leaves with a stable catalog id
    minted = 0
    for domain in sorted({d.name for b in data_root.iterdir() if b.is_dir()
                          and not b.name.startswith("_")
                          for d in b.iterdir() if d.is_dir()}):
        for bookdir in sorted(p for p in data_root.iterdir()
                              if p.is_dir() and not p.name.startswith("_")):
            dom = bookdir / domain
            if not dom.is_dir():
                continue
            cat = reg.get(bookdir.name, {}).get("cat", bookdir.name)
            lock = IdLock(data_root, bookdir.name)
            for f in sorted(dom.glob("*.json")):
                doc = json.loads(f.read_text(encoding="utf-8"))
                if not isinstance(doc.get("items"), list):
                    continue
                n = stamp_catalog_ids(doc["items"], bookdir.name, domain, cat, lock)
                if n:
                    f.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
                    minted += n
            lock.save()

    # a count of what is actually THERE, not of what we did to it — the old
    # totals line could report success over a library a fifth the expected size
    total_items = 0
    for bookdir in data_root.iterdir():
        if not bookdir.is_dir() or bookdir.name.startswith("_"):
            continue
        for dom in bookdir.iterdir():
            if not dom.is_dir():
                continue
            for f in dom.glob("*.json"):
                try:
                    doc = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if isinstance(doc.get("items"), list):
                    total_items += len(doc["items"])

    print(f"\nTOTALS commlink6={totals['jarItems']} pdf-new={totals['new']} "
          f"descriptions={totals['descriptions']} ids-minted={minted}")
    print(f"LIBRARY {total_items} items in {data_root}")
    if phase_failures:
        print(f"\n!! these phases failed: {', '.join(phase_failures)}")
        print("   the library is usable but incomplete — see the log above")
        return 1
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=_P("data"))
    ap.add_argument("--jar", type=_P, default=DEFAULT_JAR)
    ap.add_argument("--book", help="just this one book")
    ap.add_argument("--apply", action="store_true", help="write changes")
    ap.add_argument(
        "--workers", type=int, default=default_workers(),
        help="how many books to READ at once (default: %(default)s). The merge "
             "is always one book at a time, in plan order. 1 disables the pool.")
    ap.add_argument("--no-post", action="store_true",
                    help="stop after the merge; skip the phases that add the "
                         "other domains, the descriptions and your corrections")
    ap.add_argument("--graphics", action="store_true",
                    help="also extract book artwork and auto-pair it (slow)")
    args = ap.parse_args()
    jar = args.jar if args.jar and _P(args.jar).is_file() else None
    if not jar:
        print("Commlink6 jar not found — every owned PDF will be read on its own.\n")
    raise SystemExit(run(args.data, jar, args.book, args.apply, args.workers,
                         post=not args.no_post, graphics=args.graphics))


if __name__ == "__main__":
    # Books are read in worker processes, and Windows starts a worker by
    # re-executing this program. Without this the worker would fall through to
    # main() and start an import of its own.
    import multiprocessing

    multiprocessing.freeze_support()
    main()
