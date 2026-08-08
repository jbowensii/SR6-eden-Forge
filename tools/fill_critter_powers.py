"""Fill descriptions (and TYPE/ACTION/RANGE/DURATION) on critter powers that were
harvested as names only. Runs the critter-power glossary reader across every book
that has the 'TYPE ACTION RANGE DURATION' signature, collects all glossary
entries, and fills matching undescribed powers by normalized name."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import glob
import json
import re
import pdfplumber
from extractor.ingest import load_registry
from extractor.normalize import dedouble
from extractor.newtypes import read_critter_powers
from extractor.merge import norm_base

DATA = _P("data")
if __name__ == "__main__":
    # Guarded: everything below runs against the library, so an import
    # of this module to inspect it must not start the job.
    reg = load_registry(DATA)
    SIG = re.compile(r"TYPE\s+ACTION\s+RANGE\s+DURATION", re.I)

    glossary = {}   # norm_name -> system
    for book, meta in reg.items():
        pdf = meta.get("pdf", "")
        if not _P(pdf).is_file() or book in ("gun_rack", "rides"):
            continue
        try:
            with pdfplumber.open(pdf) as p:
                texts = [(i, dedouble(pg.extract_text() or "")) for i, pg in enumerate(p.pages, 1)]
            n = len(texts)
            pages = sorted({x for i, t in texts if SIG.search(t) for x in (i - 1, i, i + 1) if 1 <= x <= n})
            if not pages:
                print(f"scanned {book} (no glossary)", flush=True)
                continue
            for r in read_critter_powers(pdf, pages):
                k = norm_base(r["name"])
                if k not in glossary or r["system"].get("description"):
                    glossary[k] = r["system"]
        except Exception as e:
            print(f"  {book}: {e}", flush=True)
        print(f"scanned {book} (glossary now {len(glossary)})", flush=True)

    filled = 0
    for f in glob.glob("data/corebook/critter_powers/*.json"):
        payload = json.load(open(f, encoding="utf-8"))
        dirty = False
        for it in payload["items"]:
            if it["system"].get("description"):
                continue
            g = glossary.get(norm_base(it["name"]))
            if g and g.get("description"):
                for key in ("type", "action", "range", "duration", "description"):
                    if g.get(key):
                        it["system"][key] = g[key]
                dirty = True
                filled += 1
        if dirty:
            _P(f).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"filled {filled} critter-power descriptions", flush=True)
    print("done", flush=True)
