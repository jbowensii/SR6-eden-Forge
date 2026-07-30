"""Backfill Eden alignment on cross-book content items written with the reader's
raw fields instead of the Eden shape. The all-books content import merges rows
without running eden_align (only the curated corebook seed was aligned), so
supplement spells/qualities/adept_powers/rituals carry raw reader fields
('descriptor'/'spellType', 'cost' strings, 'gameEffect', 'keywords', a stray
'category'). Re-align just those (items still holding a raw marker field), leaving
already-aligned seed items untouched. Idempotent. Run after any content import."""

import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from extractor.eden_align import spell, quality, adeptpower, ritual

RAW = ("cost", "gameEffect", "keywords", "descriptor", "spellType", "damage")

# domain -> (aligner, needs-alignment marker). `quality`/`lifestyle` take (s,name)
JOBS = {
    "spells": (spell, lambda s: "descriptor" in s or "spellType" in s),
    "qualities": (lambda s: quality(s), lambda s: "gameEffect" in s or isinstance(s.get("cost"), str)),
    "adept_powers": (adeptpower, lambda s: isinstance(s.get("cost"), str) or "category" in s),
    "rituals": (ritual, lambda s: "keywords" in s or "category" in s or isinstance(s.get("threshold"), str)),
}


def _keep(s):
    return {k: v for k, v in s.items() if k not in RAW}


for domain, (align, needs) in JOBS.items():
    fixed = 0
    for f in glob.glob(f"data/corebook/{domain}/*.json"):
        payload = json.load(open(f, encoding="utf-8"))
        dirty = False
        for it in payload["items"]:
            s = it["system"]
            if not needs(s):
                continue
            # qualities/adept keep category via aligner output; spells set it too
            it["system"] = {**_keep(s), **align(s)}
            dirty = True
            fixed += 1
        if dirty:
            Path(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{domain:14} aligned {fixed} item(s)")
print("done")
