"""8 body_shop cyber implant weapons (Crab Claw, Goring Horns, Tesla Coil, ...)
have the subtype value 'CYBER_BODYWARE' stuck in the TYPE field with an empty
subtype — structurally invalid (fails validation, breaks Foundry export). A stale
save froze that broken state into their correction files too, so both the live
data AND the correction snapshot must be fixed or apply_corrections re-breaks it.

This repairs ONLY the type/subtype fields, preserving every other field the user
edited (name, description, icon, qaStatus, price, ...). Dry run by default;
--apply writes."""
import sys
import glob
import json
from pathlib import Path as _P

APPLY = "--apply" in sys.argv
LIVE = _P("data/corebook/gear/cyberware.json")
CORR_DIR = _P("data/_corrections/gear")

# these are offensive cyberlimb mods -> CYBER_IMPLANT_WEAPON; the two accessories
# (a rack and a shield) are CYBER_LIMB_ACCESSORY.
ACCESSORY = {"Drone Rack", "Wrist Shield"}
def target(name):
    return ("CYBERWARE", "CYBER_LIMB_ACCESSORY" if name in ACCESSORY else "CYBER_IMPLANT_WEAPON")

def broken(sys_):
    return sys_.get("type") == "CYBER_BODYWARE" and not sys_.get("subtype")

# absent when the user owns no book with cyberware
if not _P(LIVE).is_file():
    print(f"{LIVE} not present — nothing to repair")
    raise SystemExit(0)
live = json.load(open(LIVE, encoding="utf-8"))
fixed = []
for it in live["items"]:
    if broken(it["system"]):
        t, s = target(it["name"])
        it["system"]["type"], it["system"]["subtype"] = t, s
        fixed.append((it["name"], it["id"], t, s))

# mirror the fix into each item's correction snapshot
corr_fixed = []
for name, _id, t, s in fixed:
    cf = CORR_DIR / f"{_id}.json"
    if cf.exists():
        c = json.load(open(cf, encoding="utf-8"))
        node = c.get("item", c)
        if broken(node["system"]):
            node["system"]["type"], node["system"]["subtype"] = t, s
            corr_fixed.append((name, cf.name))
            if APPLY:
                cf.write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"{'APPLY' if APPLY else 'DRY RUN'} — cyberware CYBER_BODYWARE type repair")
for name, _id, t, s in fixed:
    print(f"    {name:16} -> {t} / {s}")
print(f"correction snapshots also fixed: {len(corr_fixed)}")
if APPLY:
    LIVE.write_text(json.dumps(live, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("written.")
else:
    print("(dry run — re-run with --apply to write)")
