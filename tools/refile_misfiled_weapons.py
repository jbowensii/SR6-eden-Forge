"""Re-file the weapons that were wrongly dropped into weapons_firearms. Verified
from the deadly_arts / firing_squad source tables:

  Autocannons (Dauntless, Super Rapid 75)      -> firearms / ASSAULT_CANNON (stay)
  Aztechnology Vehicle Railguns                -> weapons_special / OTHER_SPECIAL
  Ares Vehicle Lasers                          -> weapons_special / OTHER_SPECIAL
  Linear Kinetics (exotic)                     -> weapons_special / OTHER_SPECIAL
  Light Bow                                    -> weapons_ranged / BOWS

Vehicle/exotic heavy weapons have no standard Eden firearm subtype, so they move
to weapons_special/OTHER_SPECIAL. Matches by exact name; skips corrected items.
Dry run by default; --apply writes. Run apply_corrections.py after."""
import sys
import glob
import json
import os
from pathlib import Path as _P

DATA = _P("data/corebook/gear")
APPLY = "--apply" in sys.argv
CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/*/*.json")}

# name -> (dest_file, type, subtype)  (dest_file == "weapons_firearms" => stay, subtype only)
REFILE = {
    "Dauntless": ("weapons_firearms", "WEAPON_FIREARMS", "ASSAULT_CANNON"),
    "Super Rapid 75": ("weapons_firearms", "WEAPON_FIREARMS", "ASSAULT_CANNON"),
    "Estolica": ("weapons_special", "WEAPON_SPECIAL", "OTHER_SPECIAL"),
    "Xicohtencatl": ("weapons_special", "WEAPON_SPECIAL", "OTHER_SPECIAL"),
    "Mixcoatl": ("weapons_special", "WEAPON_SPECIAL", "OTHER_SPECIAL"),
    "Firelance II": ("weapons_special", "WEAPON_SPECIAL", "OTHER_SPECIAL"),
    "Fire Serpent": ("weapons_special", "WEAPON_SPECIAL", "OTHER_SPECIAL"),
    "Dornenwerfer": ("weapons_special", "WEAPON_SPECIAL", "OTHER_SPECIAL"),
    "Vaporizer": ("weapons_special", "WEAPON_SPECIAL", "OTHER_SPECIAL"),
    "Tetsu No Yari": ("weapons_special", "WEAPON_SPECIAL", "OTHER_SPECIAL"),
    "Light Bow": ("weapons_ranged", "WEAPON_RANGED", "BOWS"),
}

_files = {}
def F(name):
    if name not in _files:
        _files[name] = json.load(open(DATA / f"{name}.json", encoding="utf-8"))
    return _files[name]

src = F("weapons_firearms")
keep, moved = [], []
for it in src["items"]:
    plan = REFILE.get(it["name"])
    if not plan or it["id"] in CORR:
        keep.append(it)
        continue
    dest, typ, sub = plan
    it["system"]["type"], it["system"]["subtype"] = typ, sub
    if dest == "weapons_firearms":
        keep.append(it)
        moved.append((it["name"], "firearms (stay)", sub))
    else:
        F(dest)["items"].append(it)
        moved.append((it["name"], f"-> {dest}", sub))
src["items"] = keep

print(f"{'APPLY' if APPLY else 'DRY RUN'} — re-file mis-filed weapons")
for name, where, sub in moved:
    print(f"  {name[:18]:18} {where:22} {sub}")
print(f"  total: {len(moved)}")

if APPLY:
    dirty = {"weapons_firearms"} | {p[0] for p in REFILE.values() if p[0] != "weapons_firearms"}
    for name in dirty:
        (DATA / f"{name}.json").write_text(
            json.dumps(F(name), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("written:", ", ".join(sorted(dirty)))
else:
    print("(dry run — re-run with --apply, then tools/apply_corrections.py)")
