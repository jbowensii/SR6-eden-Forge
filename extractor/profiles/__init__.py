from __future__ import annotations

import importlib
from dataclasses import dataclass

from extractor.rowengine import RowSpec


@dataclass(frozen=True)
class TableSpec:
    category: str
    pages: list[int]
    header_regex: str
    stop_regexes: list[str]
    row_spec: RowSpec
    page_override: int | None = None


def get_profile(book: str, domain: str):
    """Return the profile MODULE for book/domain (attrs: TABLES, and optionally
    EXCLUDE, RENAMES, MANUAL_ITEMS)."""
    name = f"extractor.profiles.{book}_{domain}"
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        raise SystemExit(f"no profile module {name} — create it to extract {book}/{domain}")
    return mod
