"""One-time cleanup: cross-book quality import left raw reader fields (cost,
gameEffect) on items instead of the Eden shape (value, explain). value/explain
are already populated by eden_align for most; this backfills any that aren't
from the leftover fields, then drops cost/gameEffect entirely so the data
matches the Eden quality template."""

import glob
import json
import re
from pathlib import Path


def _num(s):
    m = re.search(r"-?\d+", str(s or ""))
    return int(m.group()) if m else 0


changed = 0
for f in glob.glob("data/corebook/qualities/*.json"):
    payload = json.load(open(f, encoding="utf-8"))
    dirty = False
    for it in payload["items"]:
        s = it["system"]
        if "cost" in s or "gameEffect" in s:
            if s.get("value") in (None, "") and s.get("cost") not in (None, ""):
                v = _num(s["cost"])
                s["value"] = -abs(v) if s.get("category") == "negative" else v
            if s.get("explain") in (None, "") and s.get("gameEffect") not in (None, ""):
                s["explain"] = s["gameEffect"]
            s.pop("cost", None)
            s.pop("gameEffect", None)
            dirty = True
    if dirty:
        Path(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed += 1
        print("fixed", Path(f).name)
print(f"done — {changed} file(s)")
