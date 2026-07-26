"""Column-aware page text: reconstruct left/right column line streams from
word positions, so prose paragraphs read contiguously instead of interleaving
across the two-column layout."""

from __future__ import annotations

from extractor.normalize import normalize_text

LINE_BUCKET = 3.0  # vertical tolerance when grouping words into lines
COLUMN_BREAK = "␟ COLUMN ␟"  # separator between left and right streams


def split_columns(words: list[dict], page_width: float, page_height: float = 0.0) -> list[str]:
    """words: pdfplumber extract_words() dicts (text, x0, top). Returns the
    page's lines: left column top-to-bottom, COLUMN_BREAK, right column.
    When page_height is given, each line is prefixed with its top fraction
    ("0.42|text") so downstream passes know true vertical position."""
    mid = page_width / 2
    out: list[str] = []
    for idx, side in enumerate((lambda w: w["x0"] < mid, lambda w: w["x0"] >= mid)):
        if idx == 1:
            out.append(COLUMN_BREAK)
        rows: dict[float, list[dict]] = {}
        for w in filter(side, words):
            key = round(w["top"] / LINE_BUCKET)
            rows.setdefault(key, []).append(w)
        for key in sorted(rows):
            ws = sorted(rows[key], key=lambda w: w["x0"])
            line = " ".join(w["text"] for w in ws)
            if page_height:
                frac = min(ws[0]["top"] / page_height, 0.999)
                line = f"{frac:.3f}|{line}"
            out.append(normalize_text(line))
    return out


def dump_columns(pdf_path, book: str, pages, root) -> int:
    """Cache column-ordered lines to data/_raw/<book>/cols/p<N>.txt."""
    import pdfplumber  # lazy: parse/enrich must not require it

    from extractor.cache import cols_path

    count = 0
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            lines = split_columns(page.extract_words(), page.width, page.height)
            out = cols_path(root, book, page_no)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("\n".join(lines) + "\n", encoding="utf-8")
            count += 1
    return count
