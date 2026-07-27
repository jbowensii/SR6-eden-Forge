"""Process a content domain across many books: find the pages that actually
carry that content type's stat signature, run its reader on only those pages,
then merge into the library — dedup by name (reprints add a source reference),
reject garbage names, and blank-fill. Reused by ingest_content_all."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import glob
import json
import re
from datetime import date

import fitz
import pdfplumber

import extractor
from extractor.autodetect import _valid_name
from extractor.emit import slugify
from extractor.ingest import LIBRARY, fill_blank_fields
from extractor.merge import norm_base

DATA = _P(__file__).resolve().parent.parent / "data"


def _content_pages(pdf_path, signature: re.Pattern):
    """Pages whose text matches a content-type signature (± a 1-page margin)."""
    hits = set()
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            if signature.search(page.extract_text() or ""):
                hits.update((i - 1, i, i + 1))
    n = fitz.open(pdf_path).page_count
    return sorted(p for p in hits if 1 <= p <= n)


def _existing_by_name(domain):
    out = {}
    for f in glob.glob(f"data/{LIBRARY}/{domain}/*.json"):
        for it in json.load(open(f, encoding="utf-8"))["items"]:
            out[norm_base(it["name"])] = it
    return out


def process_domain(domain, reader, signature, base_fields, books, category_of=None,
                   group_by="category", extra_filter=None):
    """reader(pdf, pages)->records; signature finds the pages; books = [(slug,pdf)]."""
    existing = _existing_by_name(domain)
    new_by_cat = {}
    referenced = added = 0
    seen_ids = {it["id"] for it in existing.values()}
    for book, pdf in books:
        pages = _content_pages(pdf, signature)
        if not pages:
            continue
        for rec in reader(pdf, pages):
            name = rec["name"]
            if not _valid_name(name) or (extra_filter and not extra_filter(rec)):
                continue
            key = norm_base(name)
            if key in existing:  # reprint -> add a source reference to the canonical item
                srcs = existing[key]["meta"].setdefault("sources", [{"book": existing[key]["meta"]["book"], "page": existing[key]["meta"]["page"]}])
                if not any(s["book"] == book for s in srcs):
                    srcs.append({"book": book, "page": rec["page"]})
                    referenced += 1
                continue
            base = slugify(name) or "item"
            sid, k = base, 2
            while sid in seen_ids:
                sid = f"{base}_{k}"; k += 1
            seen_ids.add(sid)
            item = {"id": sid, "name": name, "system": rec["system"],
                    "meta": {"book": book, "page": rec["page"],
                             "sources": [{"book": book, "page": rec["page"]}],
                             "extractedAt": date.today().isoformat(),
                             "extractorVersion": extractor.__version__, "qaStatus": "extracted",
                             **({"descriptionFrom": book} if rec["system"].get("description") else {})}}
            cat = (category_of(item) if category_of else str(item["system"].get(group_by, "item"))).lower()
            new_by_cat.setdefault(cat, []).append(item)
            existing[key] = item
            added += 1
    # append new items to existing category files (blank-fill the whole domain)
    out_dir = DATA / LIBRARY / domain
    out_dir.mkdir(parents=True, exist_ok=True)
    all_by_cat = {}
    for f in glob.glob(f"data/{LIBRARY}/{domain}/*.json"):
        cat = _P(f).stem
        all_by_cat[cat] = json.load(open(f, encoding="utf-8"))["items"]
    for cat, items in new_by_cat.items():
        all_by_cat.setdefault(cat, []).extend(items)
    fill_blank_fields([i for v in all_by_cat.values() for i in v], base_fields, group_by)
    for cat, items in all_by_cat.items():
        payload = {"book": LIBRARY, "domain": domain, "category": cat, "items": items}
        (out_dir / f"{cat}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{domain:14} +{added} new, {referenced} reprint-refs")
    return added, referenced
