"""Subtype the remaining no-subtype firearms from their source weapon tables.

Reality check from reading deadly_arts: these pages mix weapon classes (e.g.
railguns and bomb-launchers on one page) and the category headers are not in a
heading font, so a keyword scan mislabels rows (it tagged railguns as LAUNCHERS
from an adjacent bomb cluster). So automated inference is NOT reliable on this
book. Instead we assign only pages verified by eye to be a single standard-
firearm class, via PAGE_CLASS. Every other target is a heavy/vehicle/exotic
weapon mis-filed in weapons_firearms (railguns, energy weapons, thrown weapons)
that has no standard Eden firearm subtype — left blank and reported for the
mis-classification worklist. Skips corrected items. --apply writes."""
import sys
import glob
import json
import os
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

APPLY = "--apply" in sys.argv
CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/*/*.json")}

# (book, page) verified by reading the source table to be a single standard
# firearm class. deadly_arts p141 = "Automatic Assault Cannons" (prose: "Automatic
# assault cannons, also known as chain guns").
PAGE_CLASS = {
    ("deadly_arts", 141): "ASSAULT_CANNON",
}

assigned, unmapped = 0, []
for f in sorted(glob.glob("data/corebook/gear/weapons_firearms.json")):
    payload = json.load(open(f, encoding="utf-8"))
    changed = False
    for it in payload.get("items", []):
        s = it["system"]
        if s.get("subtype") or it["id"] in CORR:
            continue
        key = (it["meta"].get("book"), it["meta"].get("page"))
        sub = PAGE_CLASS.get(key)
        if sub:
            s["subtype"] = sub
            changed = True
            assigned += 1
            print(f"  {it['name'][:24]:24} [{key[0]} p{key[1]}] -> {sub}", flush=True)
        else:
            unmapped.append((it["name"], key[0], key[1]))
    if changed and APPLY:
        _P(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"\n{'APPLY' if APPLY else 'DRY RUN'} — firearm subtype from verified source pages")
print(f"  assigned: {assigned}")
print(f"  mis-filed / no standard firearm class — left blank ({len(unmapped)}):")
for n, b, p in unmapped:
    print(f"    {n[:24]:24} [{b} p{p}]")
if not APPLY:
    print("\n(dry run — re-run with --apply, then tools/apply_corrections.py)")
