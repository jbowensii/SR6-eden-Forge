"""Merge Commlink6 (source of truth) into SR6-eden-Forge.

Strategy (user-confirmed):
  * COVERED books  -> import ALL Commlink6 English items (lossless convert),
                      HIDE our previously-imported items from those books,
                      carry our art/img (+ corrections) onto the matching cl6
                      item by name so nothing visual is lost.
  * GAP books      -> keep our items, mark them converted (kept visible).
  * apply_corrections runs LAST (unchanged).

Dry run by default (reports the full plan + sample converted items, no writes);
--apply performs the merge. Idempotent-ish: re-running re-imports cl6 fresh."""
import sys
import glob
import json
import os
from collections import defaultdict
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
from extractor.commlink6 import BOOK_ALIAS, english_books, norm, read_book
from extractor.commlink6_convert import CL6_TO_OUR_BOOK, target, to_item

APPLY = "--apply" in sys.argv
DATA = _P("data/corebook")
CORR = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob("data/_corrections/*/*.json")}

cl6_books = english_books()
covered_our = {b for b in BOOK_ALIAS if BOOK_ALIAS[b] in cl6_books}
# our books whose slug IS a cl6 book directly (deadly_arts, double_clutch, …)
for f in glob.glob("data/corebook/*/*.json"):
    for it in json.load(open(f, encoding="utf-8")).get("items", []):
        b = it["meta"].get("book")
        if b in cl6_books:
            covered_our.add(b)

# ---- load our current data, split covered vs gap, index art/corrections ----
our_files = defaultdict(list)           # (domain,file) -> [item]  (rebuilt)
hide_count = defaultdict(int)
gap_count = 0
art_index = {}                          # (domain, norm_name) -> {img, id}
for f in sorted(glob.glob("data/corebook/*/*.json")):
    dom = f.replace("\\", "/").split("/")[-2]
    file = f.replace("\\", "/").split("/")[-1][:-5]
    payload = json.load(open(f, encoding="utf-8"))
    for it in payload.get("items", []):
        if it.get("meta", {}).get("source") == "commlink6":
            continue                      # prior cl6 import — rebuilt fresh below (idempotent)
        b = it["meta"].get("book")
        if b in covered_our:
            it.setdefault("meta", {})["hidden"] = True
            hide_count[b] += 1
            if it.get("img") or it["id"] in CORR:
                art_index[(dom, norm(it["name"]))] = {"img": it.get("img", ""), "id": it["id"]}
        else:
            gap_count += 1
        our_files[(dom, file)].append(it)

# ---- convert Commlink6 items ----
cl6_by_target = defaultdict(list)
catchall = defaultdict(int)
carried = 0
seen_ids = set()                       # a cl6 id can appear in several books; first wins
for cb in sorted(cl6_books):
    for rec in read_book(cb).values():
        if not rec["name"] or rec["id"] in seen_ids:
            continue
        seen_ids.add(rec["id"])
        if not target(rec["category"]):
            catchall[rec["category"]] += 1     # retained losslessly in commlink6_extra
        conv = to_item(rec, cb)
        if not conv:
            continue
        domain, file, item = conv
        art = art_index.get((domain, norm(item["name"])))
        if art and art["img"]:
            item["img"] = art["img"]          # carry our artwork onto the cl6 item
            carried += 1
        cl6_by_target[(domain, file)].append(item)

cl6_total = sum(len(v) for v in cl6_by_target.values())

if not APPLY:
    print("=" * 66)
    print("COMMLINK6 MERGE — DRY RUN (no writes)")
    print("=" * 66)
    print(f"covered books (import cl6 + hide ours): {len(covered_our)}")
    print(f"  {', '.join(sorted(covered_our))}")
    print(f"\ncl6 items to import (lossless): {cl6_total}")
    dom_tot = defaultdict(int)
    for (d, f), items in cl6_by_target.items():
        dom_tot[d] += len(items)
    for d, n in sorted(dom_tot.items(), key=lambda x: -x[1]):
        print(f"    {d:16} +{n}")
    print(f"\nour items to HIDE (covered books): {sum(hide_count.values())}")
    print(f"our GAP-book items kept+converted: {gap_count}")
    print(f"art/icons carried onto cl6 items: {carried}")
    if catchall:
        print(f"\ncatch-all -> commlink6_extra (retained losslessly): {sum(catchall.values())} items")
        for c, n in sorted(catchall.items(), key=lambda x: -x[1])[:20]:
            print(f"    {c:28} {n}")
    # sample converted items (structure only)
    print("\n--- sample converted items (structure; desc lengths, not text) ---")
    shown = 0
    for (d, f), items in cl6_by_target.items():
        for it in items:
            s = it["system"]
            derived = [k for k in s if k not in ("_cl6", "description", "notes", "wifi")]
            print(f"  [{d}/{f}] {it['name'][:26]:26} id={it['id']}")
            print(f"     type={s['type']}/{s.get('subtype')}  derived={derived}")
            print(f"     _cl6.stats keys={list(s['_cl6']['stats'].keys())}  desc={len(s['description'])}c wifi={len(s['wifi'])}c")
            shown += 1
            if shown >= 4:
                break
        if shown >= 4:
            break
    print("\n(dry run — re-run with --apply to write, then tools/apply_corrections.py)")
else:
    # rebuild each file: cl6 items (visible) + our items (gap kept / covered hidden)
    changed = set()
    for key in set(our_files) | set(cl6_by_target):
        dom, file = key
        items = list(cl6_by_target.get(key, [])) + list(our_files.get(key, []))
        path = DATA / dom / f"{file}.json"
        if path.exists():
            payload = json.load(open(path, encoding="utf-8"))
        else:
            payload = {"book": "corebook", "domain": dom, "category": file, "items": []}
        payload["items"] = items
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed.add(str(path))
    print(f"APPLY — wrote {len(changed)} files; imported {cl6_total} cl6 items, "
          f"hid {sum(hide_count.values())}, carried {carried} art. "
          f"Run tools/apply_corrections.py next.")
