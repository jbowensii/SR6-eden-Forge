"""Restore adept powers the item merge dropped to a catalog_id collision.

`merge_commlink6.py` keys items by catalog_id across the whole library, so when
the same id exists in two domains only one survives. Shadowrun has several of
these by design — Mystic Armor, Combat Sense and Starlight Sight are each both
a spell and an adept power — and in every case the spell won and the power
vanished from the compendium.

chargen-data already carries the full power list (name, PP cost per level,
whether it is leveled), so the missing entries are rebuilt from that plus the
jar's English description.

    python tools/backfill_adept_powers.py            # report only
    python tools/backfill_adept_powers.py --apply
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import zipfile

DEFAULT_JAR = pathlib.Path(
    r"C:\Users\johnb\CommLink6\app\stable\commlink6-1.14.0-complete.jar")
TARGET = pathlib.Path("data/corebook/adept_powers/adept_powers.json")
CHARGEN = pathlib.Path("export/chargen-data.json")

_I18N = re.compile(r"^([A-Za-z_]+)\.([A-Za-z0-9_.\-]+?)(\.desc)?\s*=\s*(.*)$")
GERMAN = re.compile(r"_de\.properties$")


def english_descriptions(jar: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with zipfile.ZipFile(jar) as z:
        for n in z.namelist():
            if not n.endswith(".properties") or GERMAN.search(n):
                continue
            raw = z.read(n)
            try:
                txt = raw.decode("utf-8")
            except UnicodeDecodeError:
                txt = raw.decode("cp1252", "replace")
            for ln in txt.splitlines():
                m = _I18N.match(ln.strip())
                if m and m.group(3) and m.group(1) == "power":
                    out.setdefault(m.group(2), m.group(4).strip())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", type=pathlib.Path, default=DEFAULT_JAR)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    powers = json.loads(CHARGEN.read_text(encoding="utf-8"))["adeptPowers"]
    doc = json.loads(TARGET.read_text(encoding="utf-8"))
    have = {(r.get("system") or {}).get("genesisID") for r in doc["items"]}
    missing = [pid for pid in powers if pid not in have]
    if not missing:
        print("no adept powers missing from the item pack")
        return

    descs = english_descriptions(args.jar)
    added = []
    for pid in missing:
        p = powers[pid]
        # match the shape the exporter expects: a top-level `id` (it dedupes on
        # it, and a missing one fails the whole pack), name, system, meta
        doc["items"].append({
            "id": f"cl6_{pid}".replace("-", "_").lower(),
            "name": p["name"],
            "system": {
                "genesisID": pid,
                "type": "", "subtype": "",
                "description": descs.get(pid, ""),
                # PP per level — the wizard multiplies by the chosen level
                "cost": p["cost"],
                "hasLevel": p["hasLevel"],
                "activation": p.get("action", ""),
                "price": 0, "priceDef": "", "avail": 0, "availDef": "",
                "notes": "", "wifi": "",
            },
            "meta": {
                "book": p.get("book", "core"),
                "page": p.get("page", ""),
                "source": "commlink6",
                "qaStatus": "extracted",
                "extractorVersion": "commlink6-1.14.0",
                "restoredBy": "backfill_adept_powers",
                "reason": "dropped by a cross-domain catalog_id collision",
            },
        })
        added.append(f"{p['name']} ({pid}, {p['cost']} PP"
                     f"{'/level' if p['hasLevel'] else ''})")

    print(f"{'added' if args.apply else 'would add'} {len(added)} adept powers:")
    for a in added:
        print(f"    {a}")
    if args.apply:
        doc["items"].sort(key=lambda r: r.get("name") or "")
        TARGET.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        print(f"wrote {TARGET}")
    else:
        print("\n(dry run — pass --apply to write)")


if __name__ == "__main__":
    main()
