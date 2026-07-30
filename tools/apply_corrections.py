"""Re-apply catalogued manual corrections after a re-import. Every site edit is
saved under data/_corrections/<domain>/<id>.json (by store.mjs); this overlays
them onto the freshly-imported library so a manual edit survives re-extraction
until it is edited again. Deletion tombstones remove re-added items. Runs as the
final step of tools/rebuild_all.py.

Also prints a diff summary (which fields were manually changed) so recurring
corrections can guide extractor improvements."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import glob
import json
from collections import Counter

DATA = _P("data")
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
        for k, v in (rec.get("system") or {}).items():
            if it["system"].get(k) != v:
                field_changes[f"{domain}.{k}"] += 1
            it["system"][k] = v
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
