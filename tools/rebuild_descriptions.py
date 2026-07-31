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
from extractor.writeups import find_block, is_stat_line, read_book_lines

DATA = _P("data")
APPLY = "--apply" in sys.argv
CORR = {os.path.splitext(os.path.basename(f))[0]
        for f in glob.glob("data/_corrections/*/*.json")}  # all domains; ids unique
_SMELL = re.compile(r"¥|\b\d+[PS]\b|\b\d/\d\b")


def notes_prose(item):
    n = (item.get("system", {}).get("notes") or "").strip()
    return n if len(n) >= 40 and not is_stat_line(n) else None


def main():
    reg = load_registry(DATA)
    files = sorted(glob.glob(f"data/{LIBRARY}/*/*.json"))
    payloads = {f: json.load(open(f, encoding="utf-8")) for f in files}
    by_book = defaultdict(list)
    for f, p in payloads.items():
        for it in p.get("items", []):
            by_book[it["meta"].get("book")].append((f, it))

    counts = dict(book=0, notes=0, empty=0, skipped=0)
    dirty = set()
    for book, entries in sorted(by_book.items()):
        meta = reg.get(book) or {}
        pdf = meta.get("pdf", "")
        lines = read_book_lines(pdf) if pdf and _P(pdf).is_file() else []
        for f, it in entries:
            if it["id"] in CORR:
                counts["skipped"] += 1
                continue
            new = find_block(it["name"], it["meta"].get("page") or 0, lines) if lines else None
            src = "book"
            if not new:
                new = notes_prose(it)
                src = "notes" if new else "empty"
            new = new or ""
            if it["system"].get("description", "") != new:
                dirty.add(f)
            it["system"]["description"] = new
            counts[src] += 1
        print(f"{book:22} processed {len(entries)}", flush=True)

    if APPLY:
        for f in dirty:
            _P(f).write_text(json.dumps(payloads[f], indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")

    smell = sum(1 for p in payloads.values() for it in p.get("items", [])
                if _SMELL.search(it["system"].get("description", "")))
    print(f"\n{'APPLY' if APPLY else 'DRY RUN'} — "
          f"book={counts['book']} notes={counts['notes']} empty={counts['empty']} "
          f"skipped={counts['skipped']}")
    print(f"smell-check (desc containing nuyen/dice): {smell}  (target 0)")
    if not APPLY:
        print("(dry run — re-run with --apply, then tools/apply_corrections.py)")


if __name__ == "__main__":
    main()
