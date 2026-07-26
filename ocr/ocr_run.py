"""Multi-engine OCR runner (runs in the .venv-ocr Python 3.12 environment with
GPU torch). Renders each page, runs one or more OCR engines, votes on the text
where engines overlap, and writes word-box JSON the main extractor consumes at
data/_raw/<book>/ocr/p<N>.json — a list of {text, x0, x1, top, conf}.

Consensus: boxes from different engines are matched by centre proximity; the
reading with the higher confidence wins, and agreement between engines boosts
confidence. Run standalone:

  .venv-ocr/Scripts/python ocr/ocr_run.py --pdf "<book.pdf>" --book <slug> \
      --data data --dpi 250
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import fitz
import numpy as np


def render(page, dpi):
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    return img[:, :, :3] if pix.n == 4 else img


def easyocr_words(reader, img, scale):
    out = []
    for bbox, text, conf in reader.readtext(img, detail=1, paragraph=False):
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        out.append({"text": text.strip(), "x0": min(xs) * scale, "x1": max(xs) * scale,
                    "top": min(ys) * scale, "conf": float(conf)})
    return [w for w in out if w["text"]]


def paddle_words(reader, img, scale):
    out = []
    try:
        res = reader.ocr(img, cls=False)
    except Exception:
        return out
    for page in res or []:
        for box, (text, conf) in page or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append({"text": str(text).strip(), "x0": min(xs) * scale, "x1": max(xs) * scale,
                        "top": min(ys) * scale, "conf": float(conf)})
    return [w for w in out if w["text"]]


def _norm(t):
    return "".join(c for c in t.lower() if c.isalnum())


def consensus(engine_outputs):
    """Merge word lists from N engines. Base = the engine with the most boxes;
    each base box is matched to the nearest box (by centre) in every other
    engine; agreement raises confidence, and the highest-confidence reading of
    the matched set is kept."""
    if not engine_outputs:
        return []
    engine_outputs = sorted(engine_outputs, key=len, reverse=True)
    base = engine_outputs[0]
    others = engine_outputs[1:]
    merged = []
    for w in base:
        cx, cy = (w["x0"] + w["x1"]) / 2, w["top"]
        candidates = [w]
        for eng in others:
            best, bestd = None, 40.0  # points
            for o in eng:
                ox, oy = (o["x0"] + o["x1"]) / 2, o["top"]
                d = ((cx - ox) ** 2 + (cy - oy) ** 2) ** 0.5
                if d < bestd:
                    best, bestd = o, d
            if best is not None:
                candidates.append(best)
        agree = sum(1 for c in candidates if _norm(c["text"]) == _norm(w["text"]))
        pick = max(candidates, key=lambda c: c["conf"])
        conf = min(1.0, pick["conf"] + 0.05 * (agree - 1))
        merged.append({"text": pick["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"],
                       "conf": round(conf, 3), "engines": len(candidates), "agree": agree})
    return merged


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--book", required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--pages", default="")  # "1-30"; empty = whole book
    ap.add_argument("--dpi", type=int, default=250)
    ap.add_argument("--engines", default="easyocr")  # paddle conflicts with torch in-process; run as a separate pass for consensus
    args = ap.parse_args(argv)

    engines = args.engines.split(",")
    readers = {}
    if "easyocr" in engines:
        import easyocr
        readers["easyocr"] = easyocr.Reader(["en"], gpu=True)
    if "paddleocr" in engines:
        try:
            from paddleocr import PaddleOCR
            readers["paddleocr"] = PaddleOCR(use_angle_cls=False, lang="en", show_log=False, use_gpu=True)
        except Exception as e:
            print(f"paddleocr unavailable ({e}); continuing without it", file=sys.stderr)

    out_dir = Path(args.data) / "_raw" / args.book / "ocr"
    out_dir.mkdir(parents=True, exist_ok=True)
    scale = 72.0 / args.dpi

    doc = fitz.open(args.pdf)
    if args.pages:
        a, _, b = args.pages.partition("-")
        pages = range(int(a), int(b or a) + 1)
    else:
        pages = range(1, doc.page_count + 1)

    for pno in pages:
        img = render(doc[pno - 1], args.dpi)
        outs = []
        if "easyocr" in readers:
            outs.append(easyocr_words(readers["easyocr"], img, scale))
        if "paddleocr" in readers:
            outs.append(paddle_words(readers["paddleocr"], img, scale))
        words = consensus(outs)
        (out_dir / f"p{pno}.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        print(f"p{pno}: {len(words)} words ({'+'.join(readers)})")
    print(f"done: {len(list(pages))} pages -> {out_dir}")


if __name__ == "__main__":
    main()
