"""Auto-pair extracted book graphics to items. Every _inbox image is named
p<page>_x<xref>.png, so it can be matched to items on that page. Conservative:
an image is assigned only when its (book, page) has exactly ONE item still
lacking art — an unambiguous pairing. Sets item.img to the _inbox path (served
at /assets/…). Never overwrites existing art. Run after import + graphics."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import glob
import json
import re
from collections import defaultdict

DATA = _P("data")
LIBRARY = "corebook"

# (book, page) -> list of (path, payload, item) lacking art
by_page = defaultdict(list)
files = {}
for f in glob.glob(f"data/{LIBRARY}/*/*.json"):
    if "/_" in f.replace("\\", "/"):
        continue
    payload = json.load(open(f, encoding="utf-8"))
    files[f] = payload
    for it in payload["items"]:
        if it.get("img"):
            continue
        book = it["meta"].get("book")
        page = it["meta"].get("page")
        if book and page:
            by_page[(book, int(page))].append((f, it))

# (book, page) -> list of _inbox image relpaths
imgs = defaultdict(list)
for f in glob.glob("data/_assets/*/_inbox/*.png"):
    rel = f.replace("\\", "/").split("_assets/")[-1]
    book = rel.split("/")[0]
    m = re.search(r"/p(\d+)_", rel)
    if m:
        imgs[(book, int(m.group(1)))].append(rel)

paired = 0
dirty = set()
for key, items in by_page.items():
    pics = imgs.get(key, [])
    if len(items) == 1 and len(pics) == 1:      # unambiguous: one item, one image
        f, it = items[0]
        it["img"] = pics[0]
        dirty.add(f)
        paired += 1

for f in dirty:
    _P(f).write_text(json.dumps(files[f], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"auto-paired {paired} item(s) to extracted art")
print("done")
