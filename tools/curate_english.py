"""Keep the item library English-only, and backfill missing descriptions.

Two passes, both reversible and neither of which touches an item's name:

1. **Hide German-sourced items.** The Commlink6 merge pulled in entries whose
   catalog_id appears *only* in a German-language sourcebook (Lofwyr, the SOTA
   series, Kechibi, ...). This project imports English books only, so those are
   flagged ``meta.hidden`` — the same mechanism the exporter already honours —
   rather than deleted, so nothing is lost if they are ever wanted.

2. **Backfill descriptions.** Where an item has no description and Commlink6's
   *English* bundle has one for its catalog_id, copy it in.

Names are deliberately left alone. The jar's English names are sometimes worse
than ours — it has "Sinner" for SINner, a mojibake "Real World Na?vet?", and a
"Hermeticsm" typo — and the good ones here are manual corrections.

    python tools/curate_english.py            # report only
    python tools/curate_english.py --apply
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import zipfile

DEFAULT_JAR = pathlib.Path(
    r"C:\Users\johnb\CommLink6\app\stable\commlink6-1.14.0-complete.jar")

#: Books published in German. Defined once in extractor.ownership, which is
#: also where the Commlink6 import gate reads it.
from extractor.ownership import GERMAN_BOOKS  # noqa: E402

HIDDEN_REASON = "german-only source book"

_ID = re.compile(rb'\bid="([^"]+)"')
_I18N = re.compile(r"^([A-Za-z_]+)\.([A-Za-z0-9_.\-]+?)(\.desc)?\s*=\s*(.*)$")


def catalog_owners(z: zipfile.ZipFile) -> dict[str, set[str]]:
    """catalog_id -> the set of books whose data files define it."""
    owner: dict[str, set[str]] = collections.defaultdict(set)
    for n in z.namelist():
        m = re.match(r"de/rpgframework/shadowrun6/data/([^/]+)/data/([^/]+)\.xml$", n)
        if not m:
            continue
        for gid in _ID.findall(z.read(n)):
            owner[gid.decode("utf-8", "replace")].add(m.group(1))
    return owner


def english_descriptions(z: zipfile.ZipFile) -> dict[str, str]:
    """catalog_id -> English description, from the non-German i18n bundles."""
    out: dict[str, str] = {}
    for n in z.namelist():
        m = re.match(r"de/rpgframework/shadowrun6/data/([^/]+)/i18n/\1\.properties$", n)
        if not m or m.group(1) in GERMAN_BOOKS:
            continue
        raw = z.read(n)
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            txt = raw.decode("cp1252", "replace")
        for ln in txt.splitlines():
            mm = _I18N.match(ln.strip())
            if mm and mm.group(3):
                out.setdefault(mm.group(2), mm.group(4).strip())
    return out


def data_files(root: pathlib.Path):
    for f in sorted(root.rglob("*.json")):
        if "_corrections" in str(f) or "_fixes" in str(f) or "_raw" in str(f):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            yield f, d


def curate(jar: pathlib.Path, root: pathlib.Path, apply: bool) -> dict:
    with zipfile.ZipFile(jar) as z:
        owner = catalog_owners(z)
        descs = english_descriptions(z)

    stats = collections.Counter()
    hidden_sample, desc_sample = [], []

    for path, doc in data_files(root):
        dirty = False
        for item in doc["items"]:
            sysd = item.get("system") or {}
            gid = sysd.get("genesisID")
            if not gid:
                continue
            books = owner.get(gid)

            # 1. German-only source -> hide (idempotent, and never un-hides
            #    something a human hid for another reason)
            if books and books <= GERMAN_BOOKS:
                meta = item.setdefault("meta", {})
                if not meta.get("hidden"):
                    meta["hidden"] = True
                    meta["hiddenReason"] = HIDDEN_REASON
                    stats["hidden"] += 1
                    if len(hidden_sample) < 8:
                        hidden_sample.append(f"{item.get('name')} <- {sorted(books)}")
                    dirty = True
                continue

            # 2. backfill a missing description from the English bundle
            if not (sysd.get("description") or "").strip() and descs.get(gid):
                sysd["description"] = descs[gid]
                item["system"] = sysd
                stats["described"] += 1
                if len(desc_sample) < 8:
                    desc_sample.append(item.get("name"))
                dirty = True

        if dirty and apply:
            path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            stats["files"] += 1

    return {"stats": stats, "hidden_sample": hidden_sample, "desc_sample": desc_sample}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jar", type=pathlib.Path, default=DEFAULT_JAR)
    ap.add_argument("--data", type=pathlib.Path, default=pathlib.Path("data"))
    ap.add_argument("--apply", action="store_true", help="write changes")
    args = ap.parse_args()

    r = curate(args.jar, args.data, args.apply)
    s = r["stats"]
    verb = "hid" if args.apply else "would hide"
    print(f"{verb} {s['hidden']} German-only items")
    for x in r["hidden_sample"]:
        print(f"    {x}")
    verb = "added" if args.apply else "would add"
    print(f"{verb} {s['described']} descriptions from the English bundles")
    for x in r["desc_sample"]:
        print(f"    {x}")
    if args.apply:
        print(f"rewrote {s['files']} files")
    else:
        print("\n(dry run — pass --apply to write)")


if __name__ == "__main__":
    main()
