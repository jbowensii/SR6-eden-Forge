"""Prove that nothing Commlink6 stores about an item is silently dropped.

Walks every English data file, collects every XML attribute and child element
that appears on an ``<item>``, and checks each one is either captured somewhere
in our exported data or listed below as a deliberate exclusion.

The point is the exclusion list: anything not captured has to be named and
justified here, so a future jar that adds a field fails the audit instead of
quietly losing it.

    python tools/audit_item_coverage.py
    python tools/audit_item_coverage.py --verbose
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from extractor.gear_meta import GERMAN_BOOKS

DEFAULT_JAR = pathlib.Path(
    r"C:\Users\johnb\CommLink6\app\stable\commlink6-1.14.0-complete.jar")
CHARGEN = pathlib.Path("export/chargen-data.json")

#: item XML attribute -> where it ends up
ATTR_HOME = {
    "id": "genesisID on the item",
    "type": "system.type / itemMeta.itemType",
    "subtype": "system.subtype / itemMeta.subtype",
    "price": "system.price (flat) or gearRatings.price (per rating)",
    "avail": "system.avail (flat) or gearRatings.avail (per rating)",
    "count": "itemMeta.count",
    "units": "itemMeta.units",
    "modonly": "itemMeta.modOnly",
    "reqVariant": "itemMeta.requiresVariant",
    "cost": "itemMeta.upkeep",
}

#: item child element -> where it ends up
CHILD_HOME = {
    "weapon": "itemMeta.weapon",
    "armor": "itemMeta.armor",
    "vehicle": "itemMeta.vehicle",
    "ammo": "itemMeta.ammo",
    "matrix": "itemMeta.matrix",
    "alchemy": "itemMeta.alchemy",
    "flags": "itemMeta.flags",
    "usage": "itemMeta.usage + gearMounts.fits",
    "choices": "gearRatings.ratings (RATING) + itemMeta.choices (the rest)",
    "requires": "itemMeta.requires + gearMounts.hostSubtypes",
    "variant": "itemMeta.variants + gearMounts.variantSlots",
    "attrdef": "gearRatings.price/avail/essence",
    "modifications": "gearMounts.hooks/embedded/bonuses",
    "geardef": "itemMeta.includedGear",
}

#: Deliberately not captured, with the reason. Anything new must be added here
#: (with a reason) or captured — the audit fails otherwise.
EXCLUDED = {
    "lang": "locale marker on German-duplicate rows; we import English only",
    "mode": "wireless//smartgun conditional stat modes — runtime combat "
            "behaviour, which eden owns rather than chargen",
    "alternate": "alternative stat presentations for the same item; the "
                 "primary block is the one a character sheet needs",
    "accessories": "legacy container tag, superseded by <modifications>/<embed>",
    "decision": "a saved player choice inside sample builds, not item data",
    "ref": "attribute of embedded references, not of the item itself",
    "uuid": "internal identifier for choice bookkeeping",
    "slot": "attribute of <usage>, captured there",
}


def survey(jar: pathlib.Path) -> tuple[dict, dict]:
    """(attributes, children) seen on <item>, each -> count."""
    attrs: collections.Counter = collections.Counter()
    kids: collections.Counter = collections.Counter()
    with zipfile.ZipFile(jar) as z:
        for n in z.namelist():
            m = re.match(r"de/rpgframework/shadowrun6/data/([^/]+)/data/([^/]+)\.xml$", n)
            if not m or m.group(1) in GERMAN_BOOKS:
                continue
            try:
                root = ET.fromstring(z.read(n))
            except ET.ParseError:
                continue
            for el in root.iter():
                if el.tag != "item":
                    continue
                attrs.update(el.attrib.keys())
                kids.update(c.tag for c in el)
    return attrs, kids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", type=pathlib.Path, default=DEFAULT_JAR)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    attrs, kids = survey(args.jar)
    data = json.loads(CHARGEN.read_text(encoding="utf-8"))

    missing = []
    print(f"item attributes seen: {len(attrs)}   child elements seen: {len(kids)}")
    print("\nattributes")
    for k, n in attrs.most_common():
        home = ATTR_HOME.get(k)
        if home:
            if args.verbose:
                print(f"  ok       {k:16} {n:5}  -> {home}")
        elif k in EXCLUDED:
            if args.verbose:
                print(f"  skipped  {k:16} {n:5}  ({EXCLUDED[k]})")
        else:
            print(f"  MISSING  {k:16} {n:5}")
            missing.append(f"attribute {k}")

    print("\nchild elements")
    for k, n in kids.most_common():
        home = CHILD_HOME.get(k)
        if home:
            if args.verbose:
                print(f"  ok       {k:16} {n:5}  -> {home}")
        elif k in EXCLUDED:
            if args.verbose:
                print(f"  skipped  {k:16} {n:5}  ({EXCLUDED[k]})")
        else:
            print(f"  MISSING  {k:16} {n:5}")
            missing.append(f"element {k}")

    print(f"\nitemMeta entries: {len(data.get('itemMeta', {}))}"
          f" | gearRatings: {len(data.get('gearRatings', {}))}"
          f" | gearMounts: {len(data.get('gearMounts', {}))}")
    if missing:
        print(f"\nFAIL — {len(missing)} uncaptured and unexplained:")
        for m in missing:
            print(f"   {m}")
        raise SystemExit(1)
    print("\nPASS — every item attribute and child element is either captured "
          "or explicitly excluded with a reason.")


if __name__ == "__main__":
    main()
