"""Compile the critter powers still lacking a description and do a plain text
search (font-independent) for each name across every book. Reports, per power,
which books/pages mention it — and where a mention is a standalone heading line
followed by prose, captures that as a candidate description and fills it."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import glob
import json
import re
import pdfplumber
from extractor.ingest import LIBRARY, load_registry
from extractor.normalize import dedouble, normalize_text
from extractor.enrich import _dehyphenate

DATA = _P("data")
reg = load_registry(DATA)

# the powers still missing a description
missing = {}
for f in glob.glob(f"data/{LIBRARY}/critter_powers/*.json"):
    for it in json.load(open(f, encoding="utf-8"))["items"]:
        if not it["system"].get("description"):
            missing[it["name"]] = f
print(f"{len(missing)} critter powers lack a description:", ", ".join(sorted(missing)), flush=True)

# per book, extract page lines once; find each power name as a standalone heading
found = {n: [] for n in missing}     # name -> [(book, page)]
desc = {}                             # name -> description (first good heading hit)
for book, meta in reg.items():
    pdf = meta.get("pdf", "")
    if not _P(pdf).is_file() or book in ("gun_rack", "rides"):
        continue
    try:
        with pdfplumber.open(pdf) as p:
            pagelines = [(i, [normalize_text(dedouble(l)).strip() for l in (pg.extract_text() or "").splitlines()])
                         for i, pg in enumerate(p.pages, 1)]
    except Exception as e:
        print(f"  {book}: {e}", flush=True)
        continue
    for name in missing:
        rx = re.compile(rf"\b{re.escape(name)}\b", re.I)
        for pno, lines in pagelines:
            for li, line in enumerate(lines):
                if rx.search(line):
                    found[name].append((book, pno))
                    # heading = short line that IS the name; grab following prose
                    if name.lower() == line.strip(" :.").lower() and name not in desc:
                        prose = _dehyphenate([x for x in lines[li + 1:li + 6] if x])
                        if len(prose) > 60:
                            desc[name] = prose[:600]
                    break
    print(f"scanned {book}", flush=True)

# fill any descriptions we recovered
filled = 0
by_file = {}
for name, text in desc.items():
    f = missing[name]
    by_file.setdefault(f, []).append((name, text))
for f, items in by_file.items():
    payload = json.load(open(f, encoding="utf-8"))
    lut = {it["name"]: it for it in payload["items"]}
    for name, text in items:
        if name in lut and not lut[name]["system"].get("description"):
            lut[name]["system"]["description"] = text
            filled += 1
    _P(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

print("\n=== mentions per power ===", flush=True)
for name in sorted(missing):
    hits = found[name]
    books = sorted({b for b, _ in hits})
    print(f"  {name:24} {len(hits)} mention(s) in {len(books)} book(s): {books[:5]}", flush=True)
print(f"\nfilled {filled} descriptions from heading-style mentions", flush=True)
print("done", flush=True)
