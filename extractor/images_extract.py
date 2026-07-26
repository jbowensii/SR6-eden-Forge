"""Extract item artwork from the source PDF as alpha-preserving PNGs and
auto-assign unambiguous ones to items (data/_assets/<book>/<item_id>.png).

Everything lands in the local gitignored data tree. Images the pairing pass
cannot attribute confidently stay in data/_assets/<book>/_inbox/ for manual
assignment through the review app's Image field."""

from __future__ import annotations

import json
import re
from pathlib import Path

from extractor.cache import read_cols
from extractor.enrich import build_index, norm, parse_col_lines

MIN_DIM = 60          # ignore decorations
BG_AREA_RATIO = 0.6   # placements covering this much of the page are backgrounds
PAIR_MAX_DIST = 0.30  # max heading distance as a fraction of page height


def _load_payloads(domain_dir: Path) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(domain_dir.glob("*.json"))}


def _page_headings(data_root: Path, book: str, page: int, index) -> list[tuple[float, int, tuple[str, str]]]:
    """(top-fraction, column, (category, item_id)) for item-name lines."""
    out = []
    for frac, col, text in parse_col_lines(read_cols(data_root, book, page).splitlines()):
        line = text.strip()
        key = norm(line)
        if key in index and len(line.split()) <= 6 and frac is not None:
            out.append((frac, col, index[key][0]))
    return out


def extract_images(pdf_path: Path, data_root: Path, book: str, domain: str, pages) -> dict:
    import fitz  # PyMuPDF; lazy so parse/enrich don't require it

    domain_dir = data_root / book / domain
    payloads = _load_payloads(domain_dir)
    index = build_index(payloads)
    items_by_key = {(c, i["id"]): i for c, p in payloads.items() for i in p.get("items", [])}

    assets = data_root / "_assets" / book
    inbox = assets / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    seen_xrefs: set[int] = set()
    saved = assigned = 0
    changed_categories: set[str] = set()

    for page_no in pages:
        page = doc[page_no - 1]
        page_area = abs(page.rect)
        candidates = []  # (y_fraction, column, xref, smask)
        for img in page.get_images(full=True):
            xref, smask, w, h = img[0], img[1], img[2], img[3]
            if w < MIN_DIM or h < MIN_DIM or xref in seen_xrefs:
                continue
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            rect = rects[0]
            if abs(rect) / page_area > BG_AREA_RATIO:
                continue  # page background / texture
            seen_xrefs.add(xref)
            y_frac = (rect.y0 + rect.y1) / 2 / page.rect.height
            column = 0 if (rect.x0 + rect.x1) / 2 < page.rect.width / 2 else 1
            candidates.append((y_frac, column, xref, smask))

        if not candidates:
            continue
        headings = _page_headings(data_root, book, page_no, index)

        for y_frac, column, xref, smask in candidates:
            pix = fitz.Pixmap(doc, xref)
            if smask:
                mask = fitz.Pixmap(doc, smask)
                try:
                    pix = fitz.Pixmap(pix, mask)  # graft alpha channel
                except Exception:
                    pass
            if pix.colorspace and pix.colorspace.n > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            target = _nearest_free_heading(y_frac, column, headings, items_by_key)
            if target:
                category, item_id = target
                rel = f"{book}/{item_id}.png"
                pix.save(str(assets / f"{item_id}.png"))
                item = items_by_key[(category, item_id)]
                item["img"] = rel
                changed_categories.add(category)
                assigned += 1
            else:
                pix.save(str(inbox / f"p{page_no}_{xref}.png"))
            saved += 1

    for category in changed_categories:
        path = domain_dir / f"{category}.json"
        path.write_text(json.dumps(payloads[category], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"saved": saved, "assigned": assigned, "inbox": saved - assigned}


def _nearest_free_heading(y_frac, column, headings, items_by_key):
    """Closest same-column, same-page item heading whose item has no image."""
    best = None
    best_dist = PAIR_MAX_DIST
    for h_frac, h_col, target in headings:
        if h_col != column:
            continue
        item = items_by_key.get(target)
        if item is None or item.get("img"):
            continue
        dist = abs(h_frac - y_frac)
        if dist < best_dist:
            best, best_dist = target, dist
    return best
