"""Rebuild every item's system.description from its source book with the
precision-first writeups core. Fallback per item: book writeup -> existing
notes (if real prose) -> empty. Manually-corrected items are never touched.
Dry run by default; --apply writes. Run tools/apply_corrections.py afterwards."""
import sys
import glob
import json
import os
import re
from collections import defaultdict
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from extractor.ingest import LIBRARY, load_registry
from extractor.bookprep import env_workers, map_jobs
from extractor.writeup_scan import scan_book
from extractor.writeups import is_stat_line
from extractor.paths import data_root
from extractor.authority import is_authoritative

# NOT _P("data"). That is the developer's scratch copy; once the builder is
# installed the real library is elsewhere, and rewriting every description in
# the wrong one looks like a successful run that changed nothing.
DATA = data_root()
APPLY = "--apply" in sys.argv
CORR = {p.stem for p in (DATA / "_corrections").rglob("*.json")}  # all domains; ids unique
#: A single stat-looking token: a price, a damage code, a fraction, a bare number.
_STAT_TOKEN = re.compile(r"^(?:[\d,]+¥?|\d+[PS]|\d+/\d+|\d+)$")


def desc_is_table_row(desc: str) -> bool:
    """Does this description look like a TABLE ROW rather than a sentence?

    Deliberately NOT extractor.writeups.is_stat_line, which answers a different
    question: whether a raw PDF *line* should be skipped while reading a page.
    That one treats an empty line as a stat line and any nuyen sign as
    disqualifying — correct there, wrong here, where an empty description is
    merely missing and a quoted price is normal English.

    The old test flagged any description containing a nuyen sign, a damage code
    or a fraction, with a stated target of zero. That target was unreachable
    because it is not a defect: "This costs 200¥ and requires an Engineer" and
    "does additional 10S, 8S, 6S in 15m" are correct, useful sentences. Every
    one of the descriptions it flagged at the end of the 0.9.4 import was
    legitimate prose, so the number it printed measured nothing and a real
    leak would have been invisible in the noise.

    What actually goes wrong is a stat ROW landing in the description field —
    short, and mostly numbers. So: flag a short description in which stat
    tokens outnumber the words. Real prose is long and mostly words, however
    many prices it happens to quote.
    """
    toks = [t.strip("().,;:") for t in (desc or "").split()]
    toks = [t for t in toks if t]
    if not toks or len(toks) > 14:
        return False                      # long enough to be a real sentence
    stats = sum(1 for t in toks if _STAT_TOKEN.match(t))
    return stats >= 4 and stats * 2 >= len(toks)


def name_variants(name: str) -> list[str]:
    """The forms a book might print this item's name in, best first.

    A name carrying two models joined by a slash — "Nissan Samurai/Oni",
    "Aztechnology Sunrunner/ Nightrunner", "BAE Systems Atlantic/Pacific 28" —
    is a shape the library produces and no book ever prints. The page describes
    the Samurai, or the Oni, under its own heading. Searching for the joined
    string finds neither, so the item lands in the library with no description
    at all and nothing says why. Eleven did.

    The manufacturer stays attached to the first model and is dropped from the
    second, because that is how the books set them: "Nissan Samurai/Oni" is one
    write-up headed Samurai and another headed Oni.
    """
    name = (name or "").strip()
    if not name:
        return []
    out = [name]
    if "/" in name:
        head, _, tail = name.partition("/")
        head, tail = head.strip(), tail.strip()
        # the joined form without the stray space pdfplumber leaves behind
        if head and tail:
            out.append(f"{head}/{tail}")
        if head:
            out.append(head)
        if tail:
            out.append(tail)
            # "Nissan Samurai/Oni" -> the Oni write-up may be headed "Nissan Oni"
            maker = head.split()
            if len(maker) > 1:
                out.append(f"{maker[0]} {tail}")
    seen, uniq = set(), []
    for candidate in out:
        if candidate and candidate not in seen:
            seen.add(candidate)
            uniq.append(candidate)
    return uniq


def notes_prose(item):
    n = (item.get("system", {}).get("notes") or "").strip()
    return n if len(n) >= 40 and not is_stat_line(n) else None


def main():
    reg = load_registry(DATA)
    files = sorted(str(p) for p in (DATA / LIBRARY).glob("*/*.json"))
    payloads = {f: json.load(open(f, encoding="utf-8")) for f in files}
    by_book = defaultdict(list)
    for f, p in payloads.items():
        for it in p.get("items", []):
            by_book[it["meta"].get("book")].append((f, it))

    counts = dict(book=0, notes=0, empty=0, skipped=0, commlink6=0)
    dirty = set()

    # ---- search the books, several at a time -------------------------------
    # Building a book's line index is a full pdfplumber walk, ~25s on a big
    # one, and fifty of those in series was twenty silent minutes -- long
    # enough to be reasonably mistaken for a hang. The walk depends on nothing
    # but the PDF, so it runs in workers; applying the results stays here,
    # because that is the half that touches the shared library.
    jobs = []
    for book, entries in sorted(by_book.items()):
        pdf = (reg.get(book) or {}).get("pdf", "")
        jobs.append({
            "book": book,
            "pdf": pdf if pdf and _P(pdf).is_file() else "",
            # One entry per name the book might print. `found` is keyed by id,
            # so the variants cost nothing but the search itself: whichever form
            # the page actually uses is the one that lands.
            "wanted": [(it["id"], variant, it["meta"].get("page") or 0)
                       for _f, it in entries if it["id"] not in CORR
                       and not is_authoritative(it)
                       for variant in name_variants(it["name"])],
        })

    workers = env_workers()
    print(f"searching {len(jobs)} book(s) with {workers} worker(s)", flush=True)

    done = [0]

    def landed(r):
        done[0] += 1
        if r.get("error"):
            print(f"  {r.get('book', '?')}: {r['error']}", flush=True)
        # the form the builder's progress label understands, so a long phase
        # visibly moves instead of looking stopped
        print(f"scanned {r.get('book', '?')}  ({done[0]}/{len(jobs)})", flush=True)

    found = {}
    for r in map_jobs(scan_book, jobs, workers, on_done=landed):
        if r and r.get("book"):
            found[r["book"]] = r.get("found") or {}

    # ---- apply, in order, one library at a time ----------------------------
    for book, entries in sorted(by_book.items()):
        blocks = found.get(book, {})
        for f, it in entries:
            if it["id"] in CORR:
                counts["skipped"] += 1
                continue
            if is_authoritative(it):
                # Commlink6 owns its own text. This phase rewrote it from the
                # books anyway and the guard put 2,073 descriptions back after
                # every single import — the phase and the guard fighting over
                # the same field, one undoing the other, for the whole run.
                # Precedence says Commlink6 outranks anything a reader inferred,
                # so the reader does not get to touch it in the first place.
                counts["commlink6"] += 1
                continue
            new = blocks.get(it["id"])
            src = "book"
            if not new:
                new = notes_prose(it)
                src = "notes" if new else "empty"
            new = new or ""
            if it["system"].get("description", "") != new:
                dirty.add(f)
            it["system"]["description"] = new
            counts[src] += 1

    if APPLY:
        for f in dirty:
            _P(f).write_text(json.dumps(payloads[f], indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")

    smell = sum(1 for p in payloads.values() for it in p.get("items", [])
                if desc_is_table_row(it["system"].get("description", "")))
    print(f"\n{'APPLY' if APPLY else 'DRY RUN'} — "
          f"book={counts['book']} notes={counts['notes']} empty={counts['empty']} "
          f"skipped={counts['skipped']} commlink6-owned={counts['commlink6']}")
    print(f"descriptions that are really a stat row: {smell}  (target 0)")
    if not APPLY:
        print("(dry run — re-run with --apply, then tools/apply_corrections.py)")


if __name__ == "__main__":
    # Workers are started by spawn, which re-imports the main module. Without
    # this guard every child would re-run this script from the top and start a
    # search of its own.
    import multiprocessing

    multiprocessing.freeze_support()
    main()
