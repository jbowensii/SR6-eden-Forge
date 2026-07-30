"""Comprehensive gear type/subtype repair. The bulk-merge of several books left
whole clusters mis-filed: an entire book (body_shop) blanket-tagged
ELECTRONICS/BIOWARE_CULTURED though the items are drugs, toxins, medkits and
climbing gear; weapons (launchers, grenades, an SMG) dumped into electronics; a
cyberware cluster with the type in the subtype slot; vehicle subtypes in mixed
case. This moves each item to the right file with the right type+subtype.

Classification is by (current subtype) and, for body_shop, by (book, page)
cluster verified against the item text. Items you have manually corrected
(data/_corrections/gear/<id>.json) are never touched. Dry run by default;
--apply writes. Run tools/apply_corrections.py afterwards."""
import sys
import glob
import json
import os
import re
from pathlib import Path as _P

DATA = _P("data/corebook/gear")
CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/gear/*.json")}
APPLY = "--apply" in sys.argv

_files = {}
def F(name):
    if name not in _files:
        _files[name] = json.load(open(DATA / f"{name}.json", encoding="utf-8"))
    return _files[name]

# body_shop drugs that are really TOXINS (damage-dealing), everything else = DRUG
TOXINS = {"arsenic", "cyanide", "blight", "burn", "zombie dust"}

def classify(it):
    """Return (dest_file, type, subtype) for a mis-filed item, or None to leave."""
    s = it["system"]
    sub = s.get("subtype")
    book = it["meta"].get("book")
    page = it["meta"].get("page") or 0
    name = it["name"].lower()

    # --- weapons wrongly living in electronics ---
    if sub == "LAUNCHERS":
        return ("weapons_firearms", "WEAPON_FIREARMS", "LAUNCHERS")
    if sub == "SUBMACHINE_GUNS":
        return ("weapons_firearms", "WEAPON_FIREARMS", "SUBMACHINE_GUNS")
    if sub == "GRENADES" and s.get("type") == "ELECTRONICS":
        return ("weapons_special", "WEAPON_SPECIAL", "GRENADES")
    if sub == "ARMOR_CLOTHES" and s.get("type") == "ELECTRONICS":
        return ("clothing", "ARMOR", "ARMOR_CLOTHES")

    # --- body_shop blanket ELECTRONICS/BIOWARE_CULTURED cluster ---
    if sub == "BIOWARE_CULTURED":
        if book == "body_shop" and page == 90:
            return ("biotech", "BIOLOGY", "BIOTECH")            # medkits, sealants, spray kits
        if book == "body_shop" and page == 149:
            return ("survival", "SURVIVAL", "SURVIVAL_GEAR")    # gecko pads (climbing)
        if book == "body_shop" and page in (120, 124, 126, 130):
            st = "TOXIN" if name in TOXINS else "DRUG"
            return ("chemicals", "CHEMICALS", st)
        # any other stray BIOWARE_CULTURED: it's not electronics — send to chemicals/DRUG
        return ("chemicals", "CHEMICALS", "DRUG")
    return None


# --- fixes that stay in place (type/subtype correction, no move) ---
def inplace_fixes():
    log = []
    cw = F("cyberware")
    for it in cw["items"]:
        if it["id"] in CORR:
            continue
        s = it["system"]
        if s.get("type") == "CYBER_BODYWARE" and not s.get("subtype"):
            s["type"], s["subtype"] = "CYBERWARE", "CYBER_BODYWARE"
            log.append(("cyberware", it["name"], "CYBER_BODYWARE type->subtype"))
    veh = F("vehicles")
    CASE = {"Main_Battle_Tank": "MAIN_BATTLE_TANK", "Jet-Board": "JET_BOARD"}
    for it in veh["items"]:
        if it["id"] in CORR:
            continue
        s = it["system"]
        if s.get("subtype") in CASE:
            old = s["subtype"]; s["subtype"] = CASE[old]
            log.append(("vehicles", it["name"], f"{old}->{s['subtype']}"))
    return log


elec = F("electronics")
moves = []
keep = []
for it in elec["items"]:
    if it["id"] in CORR:
        keep.append(it); continue
    plan = classify(it)
    if not plan:
        keep.append(it); continue
    dest, typ, sub = plan
    it["system"]["type"], it["system"]["subtype"] = typ, sub
    F(dest)["items"].append(it)
    moves.append((it["name"], dest, typ, sub))
elec["items"] = keep

inplace = inplace_fixes()

print(f"{'APPLY' if APPLY else 'DRY RUN'} — comprehensive gear type/subtype repair\n")
from collections import Counter
by_dest = Counter((d, t, s) for _, d, t, s in moves)
print(f"MOVED out of electronics ({len(moves)}):")
for (d, t, s), n in sorted(by_dest.items()):
    print(f"    {n:3}  -> {d}.json   ({t} / {s})")
print(f"\nIN-PLACE type fixes ({len(inplace)}):")
for f, n, what in inplace:
    print(f"    [{f}] {n[:34]:34} {what}")
print(f"\nelectronics: {len(keep)} remain")

if APPLY:
    dirty = {"electronics"} | {d for _, d, _, _ in moves} | {f for f, _, _ in inplace}
    for name in dirty:
        (DATA / f"{name}.json").write_text(
            json.dumps(F(name), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nwritten:", ", ".join(sorted(dirty)))
else:
    print("\n(dry run — re-run with --apply to write)")
