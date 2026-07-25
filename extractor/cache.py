from __future__ import annotations

from pathlib import Path


def page_path(root: Path, book: str, page: int) -> Path:
    return root / "_raw" / book / "pages" / f"p{page}.txt"


def read_page(root: Path, book: str, page: int) -> str:
    p = page_path(root, book, page)
    if not p.is_file():
        raise FileNotFoundError(
            f"{p} missing — run: python -m extractor dump --pdf <book.pdf> --book {book}"
        )
    return p.read_text(encoding="utf-8")
