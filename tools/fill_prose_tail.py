"""Tail description fills that don't fit the stat-header list layout:

  1. notes fallback  — if an item's description is empty but its seeded `notes`
     field holds real prose, use that.
  2. prose-glossary  — for sprite_powers and qualities, the entry is "Name" then a
     prose paragraph (a bare page-number heading may sit between). Capture the
     prose after the name (skipping digit-only headings, stopping at the next
     heading or a Cost:/Game Effect: stat line).

Only fills empty descriptions; never overwrites; skips manually corrected items.
Conservative quality gate (>=40 chars, starts capital, not a bled glossary run).
Dry run by default; --apply writes. Run apply_corrections.py after."""
import sys
import glob
import json
import os
import re
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from extractor.enrich import norm
from extractor.ingest import load_registry
from extractor.writeups import clean_block, is_stat_line, read_book_lines

APPLY = "--apply" in sys.argv
CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/*/*.json")}
GLOSSARY_DOMAINS = ("sprite_powers", "qualities")
_STOP = re.compile(r"^(Cost|Game Effect|Bonus|Requirement|Karma)s?\s*:", re.I)

_reg = None
_book_cache = {}
def _lines(book):
    global _reg
    if _reg is None:
        _reg = load_registry(_P("data"))
    if book not in _book_cache:
        pdf = (_reg.get(book) or {}).get("pdf")
        _book_cache[book] = read_book_lines(pdf) if pdf and _P(pdf).is_file() else []
    return _book_cache[book]


def notes_fallback(item):
    n = (item["system"].get("notes") or "").strip()
    return n if len(n) >= 40 and not is_stat_line(n) else ""


def glossary_prose(item):
    book, pg = item["meta"].get("book"), item["meta"].get("page") or 0
    lines = [r for r in _lines(book) if pg - 1 <= r.page <= pg + 1]
    nn = norm(item["name"])
    i = next((k for k, r in enumerate(lines)
              if norm(r.text).startswith(nn) and abs(r.page - pg) <= 1), None)
    if i is None:
        return ""
    out = []
    for r in lines[i + 1:i + 24]:
        t = r.text.strip()
        if r.is_head and t.isdigit():
            continue
        if r.is_head or _STOP.match(t):
            break
        if is_stat_line(t):
            if out:
                break
            continue
        out.append(t)
    d = clean_block(out)
    if len(d) >= 40 and d[0].isupper() and "is only selected once" not in d:
        return d
    return ""


def main():
    from_notes = from_prose = 0
    for f in sorted(glob.glob("data/corebook/*/*.json")):
        dom = f.replace("\\", "/").split("/")[-2]
        payload = json.load(open(f, encoding="utf-8"))
        changed = False
        for it in payload.get("items", []):
            if (it["system"].get("description") or "").strip() or it["id"] in CORR:
                continue
            d = notes_fallback(it)
            src = "notes"
            if not d and dom in GLOSSARY_DOMAINS:
                d = glossary_prose(it)
                src = "prose"
            if not d:
                continue
            it["system"]["description"] = d
            changed = True
            if src == "notes":
                from_notes += 1
            else:
                from_prose += 1
            print(f"  [{src}] {dom}/{it['name'][:28]}", flush=True)
        if changed and APPLY:
            _P(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n{'APPLY' if APPLY else 'DRY RUN'} — prose-tail fills: "
          f"{from_notes} from notes, {from_prose} from glossary prose")
    if not APPLY:
        print("(dry run — re-run with --apply, then tools/apply_corrections.py)")


if __name__ == "__main__":
    main()
