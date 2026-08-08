"""Re-apply catalogued manual corrections after a re-import.

Every site edit is saved under ``data/_corrections/<domain>/<id>.json`` by
store.mjs; this overlays them onto the freshly-imported library so a manual
edit survives re-extraction until it is edited again. Deletion tombstones
remove re-added items.

**When this runs.** Last, after every extraction phase AND after the Commlink6
guard has restored its rows. That order is the whole point: the guard undoes
what the derived phases overwrote, and a manual correction is the one thing
allowed to sit on top of Commlink6, because a human put it there deliberately.
Running before the guard would see the correction wiped by the restore.

**Two record shapes, both honoured.**

``{"system": {...}, "name": ...}``
    The original shape: the whole edited object. Records written before
    2026-08-08 look like this and are still applied field by field.

``{"changed": {"system": {...}}, "ref": {"name", "book"}, "gapsOnly": bool}``
    The current shape from store.mjs: only the fields that actually differ from
    what was on screen, plus enough reference data to recognise the item if its
    id changes. Storing the whole object meant a correction to one field
    carried a snapshot of every other field with it, and re-applying that
    snapshot silently reverted later extractor improvements.

``gapsOnly`` fills a field only where the imported item has nothing there, so a
correction that existed to supply a missing value stops fighting an extractor
that has since learned to read it.

Also prints a diff summary (which fields were manually changed) so recurring
corrections can guide extractor improvements."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import glob
import json
from collections import Counter

from extractor.paths import data_root, positional
from extractor.eden_codes import map_code

DATA = data_root()
LIBRARY = "corebook"
CORR = DATA / "_corrections"


def _load_domain(domain):
    """category -> (path, payload) for a domain."""
    out = {}
    for f in glob.glob(str(DATA / LIBRARY / domain / "*.json")):
        out[_P(f).stem] = (_P(f), json.load(open(f, encoding="utf-8")))
    return out


applied = deleted = 0
field_changes = Counter()
if not CORR.is_dir():
    print("no corrections to apply")
else:
    for cf in sorted(glob.glob(str(CORR / "*" / "*.json"))):
        rec = json.load(open(cf, encoding="utf-8"))
        domain, cat, cid = rec["domain"], rec.get("category"), rec["id"]
        files = _load_domain(domain)
        # locate the item across the domain's category files
        target = None
        for stem, (path, payload) in files.items():
            for it in payload["items"]:
                if it["id"] == cid:
                    target = (path, payload, it)
                    break
            if target:
                break
        if rec.get("deleted"):
            if target:
                path, payload, it = target
                payload["items"] = [i for i in payload["items"] if i["id"] != cid]
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                deleted += 1
            continue
        if not target:
            continue  # item no longer produced by extraction; skip (tombstone would remove anyway)
        path, payload, it = target

        # Two shapes. New corrections store only what CHANGED under "changed",
        # plus a "ref" for finding the item again if its id moves. Older ones
        # stored the whole item at the top level, which made every edit a
        # wholesale replacement — re-applying one overwrote fields the user had
        # never touched, including Commlink6's. Both are honoured so the
        # corrections already on disk keep working.
        edit = rec.get("changed") if isinstance(rec.get("changed"), dict) else rec
        gaps_only = bool(rec.get("gapsOnly"))

        for k, v in (edit.get("system") or {}).items():
            # gapsOnly: an old PDF-era edit re-keyed onto a Commlink6 row fills
            # what Commlink6 left empty and never overwrites what it stated
            if gaps_only and (it["system"].get(k) not in (None, "", [], {})):
                continue
            if it["system"].get(k) != v:
                field_changes[f"{domain}.{k}"] += 1
            it["system"][k] = v
        rec = {**rec, **{k: v for k, v in edit.items() if k != "system"}}
        if it["system"].get("type"):     # keep type/subtype on the Eden vocabulary
            it["system"]["type"], it["system"]["subtype"] = map_code(
                it["system"].get("type") or "", it["system"].get("subtype") or "")
        if rec.get("name"):
            it["name"] = rec["name"]
        if rec.get("img"):
            it["img"] = rec["img"]
        if rec.get("qaStatus"):
            it["meta"]["qaStatus"] = rec["qaStatus"]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        applied += 1

    print(f"applied {applied} correction(s), {deleted} deletion(s)")
    if field_changes:
        print("most-corrected fields (extractor-improvement hints):")
        for k, n in field_changes.most_common(12):
            print(f"  {k}: {n}")
print("done")
