"""Phase 1 of the description recovery for CORRECTED items (the ones the bulk
rebuild deliberately skipped). Their frozen descriptions are malformed: good
prose with a running-header bleed ("WILD LIFE // CRITTERS") mid-sentence and/or
a stat-block dump appended ("... I/ID AC CM MOVE 6/1 ..."), or a pure stat line
with no prose at all (mundane animals, vehicle stat rows).

Recover from the item's OWN text: strip the header bleed, cut at the first
stat-block boundary, sentence-trim. If real prose remains, keep it; otherwise set
empty (Phase 2 fills those from the Shadowrun wiki). Per user decision, the fix is
written to BOTH the live data and the correction snapshot, touching only the
`description` field — every other corrected field (icon, name, subtype, qa) is
preserved. Dry run by default; --apply writes. Run apply_corrections.py after."""
import sys
import glob
import json
import os
import re
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from extractor.writeups import _sentence_trim, is_stat_line

APPLY = "--apply" in sys.argv
CORR_DIR = _P("data/_corrections")
CORR = {os.path.splitext(os.path.basename(f))[0]: f for f in glob.glob("data/_corrections/*/*.json")}

# first stat-block marker — everything from here on is stats, not flavor
_CUT = re.compile(
    r"\b(I/ID|ID AC|AC CM|CM MOVE|MOVE \d|Defense Rating:|Attacks?:|Powers?:|"
    r"Skills?:|Handling \d|Accel \d|Speed Interval|Top Speed \d|Body \d+,? Armor)\b")
# running-header / sidebar bleed: 2+ ALL-CAPS words (optionally // joined) inside prose
_BLEED = re.compile(r"\s+[A-Z]{3,}(?:\s+(?:/+\s+)?[A-Z]{3,})+\s+")
# malformed test (same as the audit)
_STATHDR = re.compile(r"^(I/ID|AC CM|[A-Z]{1,3}/[A-Z]{1,3}\b)|Defense Rating:|MOVE \d|"
                      r"^Handling \d|^Hand(ling)? ")


def _numfrac(s):
    toks = s.split()
    return sum(1 for t in toks if re.search(r"\d", t)) / len(toks) if toks else 0


def is_malformed(d):
    return bool(d.strip()) and (bool(_STATHDR.search(d)) or _numfrac(d) > 0.25)


def recover(d):
    d = _BLEED.sub(" ", d)                 # drop header bleed
    m = _CUT.search(d)
    if m:
        d = d[:m.start()]                  # cut the stat-block tail
    d = re.sub(r"\s+", " ", d).strip()
    d = _sentence_trim(d)
    if len(d) < 40 or is_stat_line(d) or _numfrac(d) > 0.25:
        return ""                          # nothing usable -> empty (Phase 2)
    return d


def patch_snapshot(item_id, new_desc):
    f = CORR.get(item_id)
    if not f:
        return False
    c = json.load(open(f, encoding="utf-8"))
    node = c.get("item", c)
    node.setdefault("system", {})["description"] = new_desc
    if APPLY:
        _P(f).write_text(json.dumps(c, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True


kept, emptied, snaps = 0, 0, 0
by_dom = {}
for path in glob.glob("data/corebook/*/*.json"):
    dom = path.replace("\\", "/").split("/")[-2]
    payload = json.load(open(path, encoding="utf-8"))
    changed = False
    for it in payload.get("items", []):
        if it["id"] not in CORR:
            continue
        d = it["system"].get("description", "")
        if not is_malformed(d):
            continue
        new = recover(d)
        it["system"]["description"] = new
        changed = True
        if patch_snapshot(it["id"], new):
            snaps += 1
        if new:
            kept += 1
        else:
            emptied += 1
        by_dom[dom] = by_dom.get(dom, 0) + 1
    if changed and APPLY:
        _P(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print(f"{'APPLY' if APPLY else 'DRY RUN'} — fix malformed corrected descriptions")
print(f"  recovered prose (kept): {kept}")
print(f"  set empty (Phase 2 wiki candidates): {emptied}")
print(f"  correction snapshots patched: {snaps}")
print(f"  by domain: {by_dom}")
if not APPLY:
    print("\n(dry run — re-run with --apply, then tools/apply_corrections.py)")
