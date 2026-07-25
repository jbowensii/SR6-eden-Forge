from __future__ import annotations

import re

_TABLE_HEADER = re.compile(r"^[A-Z][A-Z /()]{12,}$")


def block_after_header(page_text: str, header_regex: str, stop_regexes: list[str]) -> list[str]:
    lines = page_text.splitlines()
    rx = re.compile(header_regex)
    stops = [re.compile(s) for s in stop_regexes]
    out: list[str] = []
    seen_header = False
    seen_col_header = False
    for line in lines:
        stripped = line.strip()
        if not seen_header:
            if rx.search(stripped):
                seen_header = True
            continue
        if any(s.search(stripped) for s in stops):
            break
        if _TABLE_HEADER.match(stripped):
            if seen_col_header:
                break  # a second table's column header ends this block
            seen_col_header = True
            continue
        out.append(stripped)
    return out
