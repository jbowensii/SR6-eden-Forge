"""Reconstruct words from individual glyph positions.

Some SR6 books have broken space-glyph metrics inside table cells, so
pdfplumber's extract_words mis-splits them ("Clean metabolism" -> "Cleanm
etabolism"). Clustering the actual glyph boxes by x-gap — with a space
threshold adaptive to each line's font size — sidesteps the bad space glyphs
and recovers correct words. Returns {text, x0, x1, top} dicts, the shape the
positional table reader consumes.
"""

from __future__ import annotations

from statistics import median

from extractor.normalize import normalize_text

LINE_TOL = 3.0


def cluster_words(chars: list[dict]) -> list[dict]:
    lines: dict[int, list[dict]] = {}
    for c in chars:
        lines.setdefault(round(c["top"] / LINE_TOL), []).append(c)
    words: list[dict] = []
    for key in sorted(lines):
        row = sorted(lines[key], key=lambda c: c["x0"])
        fs = median([c["bottom"] - c["top"] for c in row]) or 10.0
        space_thr = max(0.22 * fs, 1.2)
        cur = ""
        x0 = x1 = top = None
        for c in row:
            if cur and (c["x0"] - x1) > space_thr:
                words.append({"text": normalize_text(cur), "x0": x0, "x1": x1, "top": top})
                cur = ""
            if not cur:
                x0, top = c["x0"], c["top"]
            cur += c["text"]
            x1 = c["x1"]
        if cur.strip():
            words.append({"text": normalize_text(cur), "x0": x0, "x1": x1, "top": top})
    return [w for w in words if w["text"].strip()]


def page_words(page) -> list[dict]:
    """pdfplumber page -> reconstructed words (upright glyphs only)."""
    chars = [c for c in page.chars if c.get("upright", True)]
    return cluster_words(chars)
