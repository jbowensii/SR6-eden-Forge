"""Dump every embedded illustration from every registered book straight to
data/_assets/<book>/_inbox/ so the review app's Book-graphics gallery has full
coverage. Unlike extractor.images_extract (which needs a column cache for
caption pairing and silently skips books without it), this is pairing-free: it
just pulls raster art via PyMuPDF. Full-page images (>90% page area) are skipped
— those are page-scan backgrounds, not discrete art. Dedup by xref. Idempotent:
existing files are left alone. Pass book slugs as argv to limit."""

import json
import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

import fitz

from extractor.ingest import load_registry
from extractor.paths import data_root

# NOT _P("data"). That is the developer's scratch copy; once the builder is
# installed the real library is elsewhere, and extracting into the wrong one
# looks like a successful run that produced nothing.
DATA = data_root()
SKIP = {"gun_rack", "rides"}
MIN_DIM = 150          # px; smaller = decorative rule/icon, skip
MAX_COVER = 0.90       # fraction of page area; larger = full-page background/scan


def _pruned(book):
    """Graphics deleted on purpose, from ``_assets/_pruned.json``.

    Without this, "is the file already there?" is the only skip rule, so
    deleting a useless illustration achieves nothing: the next import extracts
    it again and reports success. An import once put 3,115 discarded images back
    for exactly this reason. tools/record_pruned_art.py writes the ledger.
    """
    try:
        led = json.loads((DATA / "_assets" / "_pruned.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set(led.get(book, ()))


def dump(book, pdf):
    # Straight into <book>/, not <book>/_inbox/. The graphics ARE the book's
    # art; an inbox implies a queue waiting to be filed, and it split the
    # gallery into two piles that had to be reconciled afterwards.
    out = DATA / "_assets" / book
    skip = _pruned(book)
    out.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf))
    seen, saved, skipped_full, skipped_small, failed = set(), 0, 0, 0, 0
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
            # page and object id are the identity; an item name may be prefixed
            # onto it later, so a file already carrying this suffix counts as
            # present however it is now named
            tag = f"p{pno + 1:03d}_x{xref}"
            if tag in skip:
                continue                    # thrown away on purpose; leave it out
            if any(out.glob(f"*{tag}.*")):
                saved += 1
                continue
            dest = out / f"{tag}.png"
            try:
                pix = fitz.Pixmap(doc, xref)
                # PNG carries grayscale and RGB only. `pix.n >= 5` was meant to
                # catch CMYK, but plain DeviceCMYK has n == 4 and alpha 0, so it
                # sailed through and pix.save raised "unsupported colorspace for
                # 'png'" — swallowed by the bare except below. Scotophobia and
                # The Needle's Eye are ENTIRELY CMYK: 468 and 447 illustrations
                # each, every one lost, both books reporting saved=0 as though
                # they simply had no art.
                #
                # Test the colorspace instead of the component count: anything
                # that is not 1-channel gray or 3-channel RGB is converted.
                cs = pix.colorspace
                if cs is None or cs.n not in (1, 3):
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                pix.save(str(dest))
                saved += 1
            except Exception as e:
                # COUNTED, never silent. A bare `pass` here is what let 915
                # images disappear without a single line of output.
                failed += 1
                if failed <= 3:
                    print(f"    {book}: could not extract xref {xref} — "
                          f"{type(e).__name__}: {e}", flush=True)
    return saved, skipped_full, skipped_small, failed


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
            s, f, sm, bad = dump(book, pdf)
            grand += s
            note = f" FAILED={bad}" if bad else ""
            print(f"{book:22} saved={s:>4} (skipped full={f:>4} small={sm:>4})"
                  f"{note}", flush=True)
        except Exception as e:
            print(f"{book:22} ERROR {e}", flush=True)
    print(f"TOTAL illustrations={grand}")
    print("done")
