from __future__ import annotations

from pathlib import Path

from extractor.cache import page_path
from extractor.normalize import normalize_text


def dump_book(pdf_path: Path, book: str, pages: range, root: Path) -> int:
    import pdfplumber  # lazy: parse stage must not require pdfplumber

    count = 0
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            text = normalize_text(page.extract_text() or "")
            out = page_path(root, book, page_no)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            count += 1
    return count
