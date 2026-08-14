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


def _domains_holding():
    """id -> the domains that currently contain a row with that id.

    A correction records the domain an item was in when it was made, and the
    lookup only ever searched there. But the phases MOVE things: the sprites
    ended up in critters, and Camera, Folding Stock and Stealth are re-filed out
    of electronics by phases 4 to 7. Once an item crosses a domain its
    correction can never find it again — fourteen deletions silently stopped
    working that way, and the item quietly came back on every import.
    """
    index = {}
    for f in glob.glob(str(DATA / LIBRARY / "*" / "*.json")):
        path = _P(f)
        try:
            doc = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for it in doc.get("items") or []:
            if isinstance(it, dict) and it.get("id"):
                index.setdefault(it["id"], set()).add(path.parent.name)
    return index


applied = deleted = rematched = skipped_absent = 0
_MOVED = _domains_holding()   # id -> domains, so a correction can follow its item
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

        # Not in the domain the record names? Follow it to the domain it is in
        # now. Only when exactly one domain holds that id — Commlink6 reuses ids
        # across books, and applying an edit to the wrong item is worse than not
        # applying it.
        if target is None:
            elsewhere = _MOVED.get(cid, set()) - {domain}
            if len(elsewhere) == 1:
                moved_to = next(iter(elsewhere))
                files = _load_domain(moved_to)
                for stem, (path, payload) in files.items():
                    for it in payload["items"]:
                        if it["id"] == cid:
                            target = (path, payload, it)
                            break
                    if target:
                        break
                if target:
                    rematched += 1

        # The id moved? Fall back to the reference the record carries.
        #
        # An id is derived from the name, so improving a reader changes it:
        # rejoining wrapped vehicle names turned krupp_bentley into
        # cl6_saeder_krupp_bentley_concordat and three corrections lost their
        # target. That matters most for DELETIONS, because the rows worth
        # deleting are junk extractions whose names — and therefore ids — are
        # the least stable in the library.
        #
        # Matched on name AND book, and only when exactly one row answers to
        # that pair. A name alone repeats across books; two candidates mean we
        # cannot tell which was meant, and re-applying an edit to the wrong
        # item is worse than not applying it.
        ref = rec.get("ref") or {}
        if target is None and ref.get("name"):
            want = (ref["name"].strip().casefold(), ref.get("book"))
            hits = [(path, payload, it)
                    for stem, (path, payload) in files.items()
                    for it in payload["items"]
                    if (it.get("name", "").strip().casefold(),
                        (it.get("meta") or {}).get("book")) == want]
            if len(hits) == 1:
                target = hits[0]
                rematched += 1

        if rec.get("deleted"):
            if target:
                path, payload, it = target
                gone = it["id"]
                # ONE row, by identity — not every row answering to this id.
                # Commlink6 reuses ids across books: 43 name-collisions in the
                # library share one, so filtering by id removes the twin the
                # tombstone was never about. Folding Stock lost both copies to
                # exactly that.
                payload["items"] = [i for i in payload["items"] if i is not it]
                path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                deleted += 1
                if gone != cid:
                    print(f"    deleted {gone} (tombstone was {cid}; matched on name)")
            continue
        # A record may say the item belongs in another DOMAIN entirely.
        #
        # Everything else here edits or removes what the extractor produced. A
        # move is the one operation that also has to ADD, and without it a whole
        # class of correction was simply unrecordable: 42 vehicles were filed
        # into gear/vehicles.json, and the only durable answers were to change
        # the reader or to lose them. Delete-then-recreate was not an option —
        # the delete half persisted and the create half did not, so it would
        # have destroyed the row on the next import.
        #
        # `movedTo: {domain, category}` says where the item should end up. The
        # record also carries `item`, the whole body, so the move still works on
        # a run where the extractor did not produce the source row at all.
        moved = rec.get("movedTo") or {}
        if moved.get("domain"):
            to_dom, to_cat = moved["domain"], moved.get("category") or moved["domain"]
            dest_path = DATA / LIBRARY / to_dom / f"{to_cat}.json"
            body = None
            if target:
                spath, spayload, sit = target
                if spath == dest_path:
                    body = None                     # already where it belongs
                else:
                    body = sit
                    spayload["items"] = [i for i in spayload["items"] if i is not sit]
                    spath.write_text(json.dumps(spayload, indent=2, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
            else:
                # NOTHING IS EVER CREATED FROM A CORRECTION.
                #
                # A correction edits or removes what the extractor produced from
                # books the user owns. If the row is not there, the user does not
                # have that source — and a correction that could conjure the item
                # would be shipping someone else's content into an install that
                # has no right to it. So a missing target means skip, always.
                #
                # This is what makes the corrections file safe to distribute: it
                # carries decisions ABOUT data, never the data itself.
                skipped_absent += 1
                continue
            if body is not None:
                if dest_path.is_file():
                    dpayload = json.loads(dest_path.read_text(encoding="utf-8"))
                else:
                    dpayload = {"book": LIBRARY, "domain": to_dom, "category": to_cat, "items": []}
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                if not any(i.get("id") == body.get("id") for i in dpayload.setdefault("items", [])):
                    dpayload["items"].append(body)
                    dest_path.write_text(json.dumps(dpayload, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
                    print(f"    moved {cid} -> {to_dom}/{to_cat}")
                # re-point at the row in its new home so `changed` still applies
                files = _load_domain(to_dom)
                target = None
                for stem, (p2, pay2) in files.items():
                    for i2 in pay2["items"]:
                        if i2.get("id") == cid:
                            target = (p2, pay2, i2)
                            break
                    if target:
                        break

        if not target:
            # The source row is not in this library, so this correction has
            # nothing to act on. Skipped, never invented — see the note above.
            skipped_absent += 1
            continue
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

    note = f", {rematched} re-matched by name after an id change" if rematched else ""
    # Said out loud, always. A correction that found nothing is the safety
    # rule working — this library does not have that book — and a silent
    # skip would look identical to a correction that did its job.
    absent = f", {skipped_absent} skipped (not in this library)" if skipped_absent else ""
    print(f"applied {applied} correction(s), {deleted} deletion(s){note}{absent}")
    if field_changes:
        print("most-corrected fields (extractor-improvement hints):")
        for k, n in field_changes.most_common(12):
            print(f"  {k}: {n}")
print("done")
