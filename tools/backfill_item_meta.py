"""Push the extracted item metadata onto the items themselves.

chargen-data carries the full picture, but only the character-creator module
reads it. The compendium packs and the review site read ``data/**.json``, which
is why Wired Reflexes still showed a price of 0 in the compendium even after
the wizard priced it correctly.

Two destinations, deliberately kept apart:

* **eden's own fields** where eden has one — ``price``, ``avail``, ``essence``,
  ``rating``, ``needsRating``, ``count``, ``countable``. A rated item is
  written at its LOWEST rating, which is the honest single value for a field
  that cannot express a range, and matches what the shop quotes.

* **``system.sr6forge``** for everything eden has no field for: the rating
  range and per-rating tables, mount slots, flags, prerequisites, variants.
  Namespaced on purpose — it is one obviously-ours key rather than a dozen
  loose ones, so it is easy to preserve (or drop) if eden ever activates its
  gear DataModel, and it can never collide with an eden field.

Existing non-empty values are never overwritten: manual corrections win.

    python tools/backfill_item_meta.py            # report only
    python tools/backfill_item_meta.py --apply
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CHARGEN = pathlib.Path("export/chargen-data.json")
DATA = pathlib.Path("data")


def resolve(spec: dict | None, rating: int, fallback=0):
    """A price/avail/essence spec at one rating (see gear_meta.parse_item_ratings)."""
    if not spec:
        return fallback
    if "table" in spec:
        raw = spec["table"][min(max(rating, 1), len(spec["table"])) - 1]
        try:
            return float(str(raw).rstrip("LIRlir") or 0)
        except ValueError:
            return fallback
    if spec.get("perRating") is not None:
        return spec["perRating"] * rating
    if spec.get("flat") is not None:
        return spec["flat"]
    return fallback


def num(v):
    """Ints stay ints so the packs do not fill up with 40000.0."""
    f = float(v)
    return int(f) if f == int(f) else round(f, 3)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    cg = json.loads(CHARGEN.read_text(encoding="utf-8"))
    ratings, mounts, meta = cg["gearRatings"], cg["gearMounts"], cg["itemMeta"]

    stats = collections.Counter()
    priced_samples: list[str] = []

    for path in sorted(DATA.rglob("*.json")):
        if any(x in str(path) for x in ("_corrections", "_fixes", "_raw")):
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
            continue

        dirty = False
        for item in doc["items"]:
            sysd = item.setdefault("system", {})
            gid = sysd.get("genesisID")
            if not gid:
                continue

            rm, mm, im = ratings.get(gid), mounts.get(gid), meta.get(gid)
            if not (rm or mm or im):
                continue

            extra: dict = {}

            # ---- rated gear: eden holds one rating, we keep the whole range --
            if rm:
                low = rm["ratings"][0]
                extra["ratings"] = rm["ratings"]
                extra["maxRating"] = rm["maxRating"]
                for key, field in (("price", "price"), ("avail", "avail"),
                                   ("essence", "essence")):
                    if key in rm:
                        extra[f"{key}ByRating"] = [
                            num(resolve(rm[key], r, 0)) for r in rm["ratings"]]
                # only fill an eden field that is empty — never clobber a fix
                if not sysd.get("price") and "price" in rm:
                    sysd["price"] = num(resolve(rm["price"], low, 0))
                    stats["price filled"] += 1
                    if len(priced_samples) < 6:
                        priced_samples.append(f"{item.get('name')} -> {sysd['price']}")
                if not sysd.get("avail") and "avail" in rm:
                    sysd["avail"] = num(resolve(rm["avail"], low, 0))
                    stats["avail filled"] += 1
                if not sysd.get("essence") and "essence" in rm:
                    sysd["essence"] = num(resolve(rm["essence"], low, 0))
                    stats["essence filled"] += 1
                if not sysd.get("rating"):
                    sysd["rating"] = low
                    sysd["needsRating"] = True
                    stats["rating set"] += 1

            # ---- accessory mounting -------------------------------------
            if mm:
                for k in ("hooks", "fits", "hostSubtypes", "embedded", "bonuses"):
                    if mm.get(k):
                        extra[k] = mm[k]

            # ---- everything else Commlink6 stores -----------------------
            if im:
                for k in ("flags", "usage", "requires", "variants", "choices",
                          "includedGear", "modOnly", "requiresVariant", "units",
                          "upkeep", "weapon", "armor", "vehicle", "ammo",
                          "matrix", "alchemy"):
                    if im.get(k):
                        extra[k] = im[k]
                # count/countable are eden's own
                if im.get("count") and not sysd.get("count"):
                    sysd["count"] = im["count"]
                    sysd["countable"] = True
                    stats["count filled"] += 1

            if extra:
                if sysd.get("sr6forge") != extra:
                    sysd["sr6forge"] = extra
                    stats["sr6forge written"] += 1
                    dirty = True

        if dirty and args.apply:
            path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            stats["files"] += 1

    verb = "" if args.apply else "would be "
    for k, v in stats.most_common():
        if k != "files":
            print(f"  {k:20} {verb}{v}")
    if priced_samples:
        print("\n  newly priced, e.g.:")
        for s in priced_samples:
            print(f"    {s}")
    if args.apply:
        print(f"\nrewrote {stats['files']} files")
    else:
        print("\n(dry run — pass --apply to write)")


if __name__ == "__main__":
    main()
