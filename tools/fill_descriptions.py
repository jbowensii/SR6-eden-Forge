"""Fill missing item descriptions by searching every book's text. Optimized:
each book's PDF is text-extracted ONCE, then every domain's item names are
matched against those shared lines (name -> heading -> following prose). Only
fills items whose description is still empty; never overwrites. Much faster than
re-opening the PDF per domain."""
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
import glob
import json
import pdfplumber
from extractor.describe import page_lines
from extractor.enrich import build_index, parse_sections
from extractor.ingest import LIBRARY, load_registry

DATA = _P("data")
reg = load_registry(DATA)
DOMAINS = sorted({_P(f).parent.name for f in glob.glob(f"data/{LIBRARY}/*/*.json") if not _P(f).parent.name.startswith("_")})

# preload payloads + indexes per domain once
domain_payloads = {}
for domain in DOMAINS:
    payloads = {_P(f).stem: json.load(open(f, encoding="utf-8"))
                for f in sorted(glob.glob(f"data/{LIBRARY}/{domain}/*.json"))}
    if any(any(not it["system"].get("description") for it in p.get("items", [])) for p in payloads.values()):
        domain_payloads[domain] = (payloads, build_index(payloads))

grand = 0
for book, meta in reg.items():
    pdf = meta.get("pdf", "")
    if not _P(pdf).is_file() or book in ("gun_rack", "rides"):
        continue
    try:
        lines = []
        with pdfplumber.open(pdf) as p:
            for pno in range(1, len(p.pages) + 1):
                lines.extend(page_lines(p.pages[pno - 1], pno))
    except Exception as e:
        print(f"{book}: {e}", flush=True)
        continue
    book_total = 0
    for domain, (payloads, index) in domain_payloads.items():
        sections = parse_sections(lines, index)
        for category, payload in payloads.items():
            changed = False
            for item in payload["items"]:
                if item["system"].get("description"):
                    continue
                text = sections.get((category, item["id"]))
                if text:
                    item["system"]["description"] = text
                    book_total += 1
                    changed = True
            if changed:
                _P(f"data/{LIBRARY}/{domain}/{category}.json").write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    grand += book_total
    print(f"{book:22} filled {book_total}", flush=True)

print(f"TOTAL descriptions filled: {grand}", flush=True)
print("done", flush=True)
