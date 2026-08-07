"""Fix the over-classified ELECTRONICS bucket: many items the extractor dumped
there are really clothing, melee weapons, armor/suits, chemicals, magic supplies,
or are electronics that just lack a subtype. Reclassify by name keyword — set the
correct type+subtype and MOVE the item to the right gear category file.

SAFETY: items you have manually corrected (data/_corrections/gear/<id>.json) are
NEVER touched. Run with --apply to write; default is a dry run. Run
tools/apply_corrections.py afterwards as a final overlay."""
import sys
import glob
import json
import os
import re
from pathlib import Path as _P

DATA = _P("data/corebook/gear")
CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/gear/*.json")}
APPLY = "--apply" in sys.argv

# (regex on name) -> (target category file, system.type, system.subtype)
RULES = [
    (r"\btrench\s?coat\b|\btrilby\b|\bhomburg\b|krime rave|\bslacks\b|\bshirt\b|\bvest\b|"
     r"\bjacket\b|\bcane\b|\bboots\b|\bgrooming\b|eau de|parfum|purple reign|dragon.?s gaze|"
     r"le tigre|of the pack|essence of|de d.?guise|\bglasses\b|\bvisor\b",
     "clothing", "ARMOR", "ARMOR_CLOTHES"),
    (r"hirschf|hagami|neko-tegami|\bpitchfork\b|\bhercules\b|\bkatana\b|\bknife\b|\bsword\b",
     "weapons_close_combat", "WEAPON_CLOSE_COMBAT", "BLADES"),
    (r"encounter suit|exploration suit|suit helmet|ceramic plate",
     "armor", "ARMOR", "ARMOR_BODY"),
    (r"^dmso$|\bscourge\b", "chemicals", "CHEMICALS", "INDUSTRIAL_CHEMICALS"),
    (r"\bfetish\b|orichalcum|divination|\breagent", "magical", "MAGICAL", "MAGIC_SUPPLIES"),
    (r"graffiti kit|uv ?f?\s?(flashlight|loodlight)|black ink|\bpaper\b", "tools", "TOOLS", "GENERAL_TOOLS"),
    # real electronics that just lack a subtype
    (r"\bmodule\b|program carrier|reality filter|hardening", None, "ELECTRONICS", "CYBERDECK"),
    (r"commlink \(variant\)|\bbriefcase\b", None, "ELECTRONICS", "COMMLINK"),
]


def load(name):
    # A category file only exists if the user owns a book that fills it.
    # Crashing here meant a smaller library — anyone who owns a subset of
    # the books — could not finish an import at all.
    p = DATA / f"{name}.json"
    if not p.is_file():
        return p, {"items": []}          # same shape, so callers need no branch
    return p, json.load(open(p, encoding="utf-8"))


files = {}
def get(name):
    if name not in files:
        files[name] = load(name)
    return files[name]


ep, elec = get("electronics")
moved = {}
keep = []
for it in elec["items"]:
    if it["system"].get("subtype") or it["id"] in CORR:
        keep.append(it)
        continue
    name = it["name"].lower()
    rule = next((r for r in RULES if re.search(r[0], name)), None)
    if not rule:
        keep.append(it)
        continue
    _rx, targetfile, typ, sub = rule
    it["system"]["type"] = typ
    it["system"]["subtype"] = sub
    dest = targetfile or "electronics"
    moved.setdefault(dest, []).append(it["name"])
    if targetfile:
        get(targetfile)[1]["items"].append(it)   # moved out of electronics
    else:
        keep.append(it)                            # stays, now with a subtype

elec["items"] = keep   # electronics = everything not moved to another file

print(f"{'APPLY' if APPLY else 'DRY RUN'} — reclassify uncorrected no-subtype electronics")
for dest, names in sorted(moved.items()):
    where = f"-> {dest}.json" if dest != "electronics" else "(stay, +subtype)"
    print(f"\n{where}  ({len(names)})")
    for n in names[:30]:
        print(f"    {n}")

if APPLY:
    for name, (p, payload) in files.items():
        p.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nwritten.")
else:
    print("\n(dry run — re-run with --apply to write)")
