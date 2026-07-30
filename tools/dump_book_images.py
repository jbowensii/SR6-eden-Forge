"""Dump every embedded illustration from every registered book straight to
data/_assets/<book>/_inbox/ so the review app's Book-graphics gallery has full
coverage. Unlike extractor.images_extract (which needs a column cache for
caption pairing and silently skips books without it), this is pairing-free: it
just pulls raster art via PyMuPDF. Full-page images (>90% page area) are skipped
— those are page-scan backgrounds, not discrete art. Dedup by xref. Idempotent:
existing files are left alone. Pass book slugs as argv to limit."""

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import fitz

from extractor.ingest import load_registry

DATA = _P("data")
SKIP = {"gun_rack", "rides"}
MIN_DIM = 150          # px; smaller = decorative rule/icon, skip
MAX_COVER = 0.90       # fraction of page area; larger = full-page background/scan


def dump(book, pdf):
    out = DATA / "_assets" / book / "_inbox"
    out.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf))
    seen, saved, skipped_full, skipped_small = set(), 0, 0, 0
    for pno in range(doc.page_count):
        page = doc[pno]
        parea = abs(page.rect) or 1.0
        for img in page.get_images(full=True):
            xref, w, h = img[0], img[2], img[3]
            if xref in seen:
                continue
            if w < MIN_DIM or h < MIN_DIM:
                skipped_small += 1
                continue
            rects = page.get_image_rects(xref)
            if rects and (abs(rects[0]) / parea) > MAX_COVER:
                skipped_full += 1
                continue
            seen.add(xref)
            dest = out / f"p{pno + 1:03d}_x{xref}.png"
            if dest.exists():
                saved += 1
                continue
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n >= 5:                 # CMYK / with alpha -> RGB(A)
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                pix.save(str(dest))
                saved += 1
            except Exception:
                pass
    return saved, skipped_full, skipped_small


if __name__ == "__main__":
    reg = load_registry(DATA)
    only = set(sys.argv[1:])
    grand = 0
    for book, meta in reg.items():
        if book in SKIP or (only and book not in only):
            continue
        pdf = _P(meta.get("pdf", ""))
        if not pdf.is_file():
            continue
        try:
            s, f, sm = dump(book, pdf)
            grand += s
            print(f"{book:22} saved={s:>4} (skipped full={f:>4} small={sm:>4})", flush=True)
        except Exception as e:
            print(f"{book:22} ERROR {e}", flush=True)
    print(f"TOTAL illustrations={grand}")
    print("done")
