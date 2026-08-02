"""Backfill blank gear subtypes with extractor.subtype_infer: match each item's
name, then its description + notes, against per-type keyword/synonym rules. Only
touches items with no subtype; skips manually corrected items. Conservative — an
item with no specific keyword match is left blank. Dry run by default; --apply
writes. Run tools/apply_corrections.py after."""
import sys
import glob
import json
import os
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from extractor.subtype_infer import infer_subtype

APPLY = "--apply" in sys.argv
CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/*/*.json")}

# --apply-text also writes the lower-confidence description/notes matches
APPLY_TEXT = "--apply-text" in sys.argv

assigned, skipped, left = 0, 0, 0
by_sub = {}
suggestions = []
for f in sorted(glob.glob("data/corebook/gear/*.json")):
    payload = json.load(open(f, encoding="utf-8"))
    changed = False
    for it in payload.get("items", []):
        s = it["system"]
        if s.get("subtype"):
            continue
        if it["id"] in CORR:
            skipped += 1
            continue
        # pass 1: name only (high confidence). pass 2: description + notes (lower).
        name_sub = infer_subtype(s.get("type"), it["name"], "", "")
        text_sub = None if name_sub else infer_subtype(s.get("type"), "", s.get("description", ""), s.get("notes", ""))
        sub = name_sub or (text_sub if APPLY_TEXT else None)
        if not sub:
            if text_sub:
                suggestions.append((it["name"], s.get("type"), text_sub))
            else:
                left += 1
            continue
        s["subtype"] = sub
        changed = True
        assigned += 1
        by_sub[sub] = by_sub.get(sub, 0) + 1
        src = "name" if name_sub else "text"
        print(f"  {it['name'][:32]:32} [{s.get('type')}] -> {sub}  ({src})", flush=True)
    if changed and APPLY:
        _P(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"\n{'APPLY' if APPLY else 'DRY RUN'} — gear subtype inference")
print(f"  assigned: {assigned}   left blank: {left}   skipped (corrected): {skipped}")
print(f"  by subtype: {by_sub}")
if suggestions and not APPLY_TEXT:
    print(f"\n  {len(suggestions)} lower-confidence description/notes suggestions (NOT applied; "
          f"use --apply-text to accept):")
    for name, typ, sub in suggestions:
        print(f"    {name[:32]:32} [{typ}] ~ {sub}")
if not APPLY:
    print("\n(dry run — re-run with --apply for name matches, then tools/apply_corrections.py)")
