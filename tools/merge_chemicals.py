"""Finish the toxins/drugs → gear/chemicals move. Corebook drugs and toxins were
copied into gear as type=CHEMICALS, but the parallel cross-book toxins/drugs
domains were left behind (orphan dirs with no schema). Drugs are already fully in
gear; the only unique content is a handful of cross-book venoms. Fold the real
ones into gear/chemicals (composing the gear description from their structured
toxin fields), then remove the orphan domains. Idempotent by name."""

import glob
import json
from datetime import date
from pathlib import Path

GEAR = Path("data/corebook/gear/chemicals.json")


def slug(name):
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def compose_desc(s):
    parts = []
    for label, key in [("Vector", "vector"), ("Speed", "speed"), ("Duration", "duration"),
                       ("Power", "power"), ("Effect", "effect")]:
        v = s.get(key)
        if v:
            parts.append(f"{label}: {v}")
    body = s.get("description") or ""
    return "\n".join(parts) + (("\n\n" + body) if body else "")


if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    payload = json.load(open(GEAR, encoding="utf-8"))
    have = {it["name"].lower() for it in payload["items"]}
    ids = {it["id"] for it in payload["items"]}
    added = 0

    for orphan_domain, subtype in [("toxins", "TOXIN"), ("drugs", "DRUG")]:
        for f in glob.glob(f"data/corebook/{orphan_domain}/*.json"):
            for it in json.load(open(f, encoding="utf-8"))["items"]:
                s = it["system"]
                name = it["name"]
                if name.lower() in have:
                    continue
                # keep only real chemicals: must carry the defining structured fields
                if not (s.get("vector") and s.get("power")):
                    continue
                sid, k = slug(name), 2
                while sid in ids:
                    sid = f"{slug(name)}_{k}"; k += 1
                ids.add(sid); have.add(name.lower())
                payload["items"].append({
                    "id": sid, "name": name,
                    "system": {"type": "CHEMICALS", "subtype": subtype, "description": compose_desc(s)},
                    "meta": {**it["meta"]},
                })
                added += 1

    payload["items"].sort(key=lambda x: x["name"])
    GEAR.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"folded {added} venoms/chemicals into gear/chemicals ({len(payload['items'])} total)")
