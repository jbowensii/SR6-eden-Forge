from __future__ import annotations

import re
from dataclasses import dataclass, field

from extractor.columns import resolve

MAX_WRAP = 3


@dataclass(frozen=True)
class RowSpec:
    columns: list[str]
    defaults: dict = field(default_factory=dict)
    # Tables set in one column of a two-column page get prose from the OTHER
    # column glued after the last cell; allow_tail matches and discards it.
    allow_tail: bool = False

    def regex(self) -> re.Pattern:
        parts = [f"(?P<name>.+?)"]
        for i, key in enumerate(self.columns):
            parts.append(f"(?P<c{i}>{resolve(key).pattern})")
        tail = r"(?:\s+\S.*)?" if self.allow_tail else ""
        return re.compile(r"^\s*" + r"\s+".join(parts) + tail + r"\s*$")


def _strip_page_numbers(line: str, page_numbers: set[int]) -> str:
    if not page_numbers:
        return line
    toks = [t for t in line.split() if not (t.isdigit() and int(t) in page_numbers)]
    return " ".join(toks)


def _plausible_name(name: str) -> bool:
    if len(name.split()) > 8:
        return False
    if ". " in name or name.endswith("."):
        return False
    if "¥" in name or "—" in name:
        return False  # unmatched table data bleeding into the name
    return True


def parse_block(
    lines: list[str], spec: RowSpec, page_numbers: set[int] = frozenset()
) -> list[tuple[str, dict]]:
    rx = spec.regex()
    rows: list[tuple[str, dict]] = []
    buffer: list[str] = []

    def emit(match: re.Match) -> None:
        system = dict(spec.defaults)
        notes: list[str] = []
        if system.get("notes"):
            notes.append(system["notes"])
        for i, key in enumerate(spec.columns):
            converted = resolve(key).convert(match.group(f"c{i}"))
            note = converted.pop("_note", None)
            if note:
                notes.append(note)
            system.update(converted)
        if notes:
            system["notes"] = "; ".join(notes)
        name = re.sub(r"\s+", " ", match.group("name")).strip()
        rows.append((name, system))

    for raw in lines:
        line = _strip_page_numbers(raw.strip(), set(page_numbers))
        if not line:
            continue
        buffer.append(line)
        candidates = [
            (k, m)
            for k in range(1, len(buffer) + 1)
            if (m := rx.match(" ".join(buffer[-k:])))
        ]
        if candidates:
            plausible = [c for c in candidates if _plausible_name(c[1].group("name").strip())]
            # prefer names that start like names (capital/digit) — prose
            # fragments from the page's other column start lowercase
            named = [c for c in plausible if c[1].group("name").strip()[0].isupper() or c[1].group("name").strip()[0].isdigit()]
            if named:
                _, m = max(named, key=lambda c: c[0])
            elif plausible:
                _, m = max(plausible, key=lambda c: c[0])
                m = _trim_leading_junk(m, rx) or m
            else:
                _, m = min(candidates, key=lambda c: c[0])
                m = _trim_leading_junk(m, rx) or m
            emit(m)
            buffer = []
        elif len(buffer) > MAX_WRAP:
            buffer.pop(0)
    return rows


def _trim_leading_junk(match: re.Match, rx: re.Pattern) -> re.Match | None:
    """Prose from the page's other column can precede the item name on the
    same line. Drop leading words until a plausible name remains; table names
    start with a capital or digit, prose fragments don't."""
    tokens = match.string.split()
    fallback = None
    for start in range(1, len(tokens)):
        m = rx.match(" ".join(tokens[start:]))
        if not m:
            continue
        name = m.group("name").strip()
        if not _plausible_name(name):
            continue
        if name[0].isupper():
            return m
        # digit- or lowercase-start names are legal but rarer; keep the first
        # as fallback in case no capitalized candidate appears
        fallback = fallback or m
    return fallback
