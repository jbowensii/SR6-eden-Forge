"""Fill empty descriptions for list-layout domains (spells now; powers next) by
parsing the compact "<Name> / (Category) / RANGE TYPE DURATION... / values /
prose" blocks the prose-writeup extractor can't read. Reads only the domain's own
pages for speed. Fills only empty descriptions, never overwrites; skips manually
corrected items unless empty, in which case it also mirrors the fill into the
correction snapshot. Dry run by default; --apply writes. Run apply_corrections.py
after."""
import sys
import glob
import json
import os
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import pdfplumber
from extractor.enrich import norm
from extractor.ingest import load_registry
from extractor.spell_layout import SPELL_HEADER, parse_list_descriptions
from extractor.writeups import _page_recs

APPLY = "--apply" in sys.argv
DOMAIN = next((a.split("=")[1] for a in sys.argv if a.startswith("--domain=")), "spells")
CORR = {os.path.splitext(os.path.basename(f))[0]: f for f in glob.glob("data/_corrections/*/*.json")}
HEADERS = {"spells": SPELL_HEADER}


def patch_snapshot(item_id, desc):
    f = CORR.get(item_id)
    if not f:
        return
    c = json.load(open(f, encoding="utf-8"))
    (c.get("item", c)).setdefault("system", {})["description"] = desc
    _P(f).write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    header_re = HEADERS.get(DOMAIN, SPELL_HEADER)
    items, pages, known = [], set(), set()
    for f in sorted(glob.glob(f"data/corebook/{DOMAIN}/*.json")):
        payload = json.load(open(f, encoding="utf-8"))
        for it in payload.get("items", []):
            items.append((f, payload, it))
            known.add(norm(it["name"]))
            p = it["meta"].get("page")
            if p:
                pages.update([p - 1, p, p + 1])

    pdf = (load_registry(_P("data")).get("corebook") or {}).get("pdf")
    lines = []
    with pdfplumber.open(pdf) as doc:
        for p in sorted(pages):
            if 1 <= p <= len(doc.pages):
                lines.extend(_page_recs(doc.pages[p - 1], p))

    desc = parse_list_descriptions(lines, known, header_re)

    filled = 0
    dirty = {}
    for f, payload, it in items:
        if (it["system"].get("description") or "").strip():
            continue
        d = desc.get(norm(it["name"]))
        if not d:
            continue
        it["system"]["description"] = d
        dirty[f] = payload
        filled += 1
        if APPLY and it["id"] in CORR:
            patch_snapshot(it["id"], d)
        print(f"  [hit] {it['name'][:34]:34}", flush=True)

    if APPLY:
        for f, payload in dirty.items():
            _P(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    empty = sum(1 for _, _, it in items if not (it["system"].get("description") or "").strip())
    print(f"\n{'APPLY' if APPLY else 'DRY RUN'} — list-layout fill ({DOMAIN})")
    print(f"  parsed descriptions: {len(desc)}   filled: {filled}   still empty: {empty}   of {len(items)}")
    if not APPLY:
        print("(dry run — re-run with --apply, then tools/apply_corrections.py)")


if __name__ == "__main__":
    main()
