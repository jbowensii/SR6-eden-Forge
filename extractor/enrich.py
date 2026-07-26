"""Attribute per-item prose writeups from the column-ordered page cache to
items in the local dataset (system.description). Runs entirely against the
user's local page cache and local data files."""

from __future__ import annotations

import json
import re
from pathlib import Path

from extractor.cache import read_cols
from extractor.textcols import COLUMN_BREAK

MAX_SECTION_LINES = 18
MAX_DESC_CHARS = 1400
# lines that end a writeup section even if no new heading was seen
_STOPPERS = re.compile(r"^[A-Z][A-Z /()&'’]{11,}$")  # table/column headers
_JUNK = re.compile(r"¥|\d/\d.*\d/\d|^\d{1,3}$")  # stat rows, bare page numbers
_SECTION = re.compile(r"^[a-z][a-z /&'’-]{2,40}$")  # lowercase table section titles


def parse_col_lines(raw_lines):
    """Cols-cache lines -> [(top_fraction|None, column, text)]; strips the
    position prefix and the column marker."""
    col = 0
    out = []
    for raw in raw_lines:
        if raw.strip() == COLUMN_BREAK:
            col = 1
            continue
        frac, text = None, raw
        m = re.match(r"^(\d\.\d{3})\|(.*)$", raw)
        if m:
            frac, text = float(m.group(1)), m.group(2)
        out.append((frac, col, text))
    return out


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.casefold())


def heading_keys(name: str) -> set[str]:
    """Normalized variants under which an item's writeup heading may appear."""
    keys = {norm(name)}
    base = re.sub(r"\s*\(.*?\)$", "", name)  # 'Smartlink (cyberware)' -> 'Smartlink'
    keys.add(norm(base))
    if "/" in base:  # 'Yamaha Pulsar I/II' -> 'Yamaha Pulsar I' etc.
        head = base.split("/")[0].strip()
        keys.add(norm(head))
        keys.add(norm(re.sub(r"\s+\S+$", "", head)))  # drop trailing model token
    if "," in base:  # 'Crossbow, Light' -> 'Light Crossbow' + 'Crossbow'
        first, _, rest = base.partition(",")
        keys.add(norm(f"{rest} {first}"))
        keys.add(norm(first))
    keys.discard("")
    return keys


def build_index(payloads: dict[str, dict]) -> dict[str, list[tuple[str, str]]]:
    """key -> [(category, item_id)]. Full-name keys may map to several items
    (intentionally same-named across categories); looser variant keys that
    collide across DIFFERENT items are ambiguous and dropped."""
    index: dict[str, list[tuple[str, str]]] = {}
    full_keys: dict[str, set[str]] = {}
    variant_of: dict[str, set[str]] = {}
    for category, payload in payloads.items():
        for item in payload.get("items", []):
            full = norm(item["name"])
            full_keys.setdefault(full, set()).add(item["name"])
            for key in heading_keys(item["name"]):
                index.setdefault(key, []).append((category, item["id"]))
                variant_of.setdefault(key, set()).add(item["name"])
    for key in list(index):
        names = variant_of[key]
        if len(names) > 1 and key not in full_keys:
            del index[key]  # generic variant shared by different items
    return index


def _dehyphenate(lines: list[str]) -> str:
    text = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if text.endswith("-"):
            text = text[:-1] + line
        else:
            text = f"{text} {line}" if text else line
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s+\S*-$", "", text)  # drop a mid-word tail cut off at a section boundary


def parse_sections(lines: list[str], index: dict[str, list[tuple[str, str]]]) -> dict[tuple[str, str], str]:
    """Scan column-ordered lines; a line matching a known item name opens a
    section captured until the next heading/stopper."""
    sections: dict[tuple[str, str], str] = {}
    current: list[tuple[str, str]] | None = None
    buffer: list[str] = []

    def flush():
        nonlocal current, buffer
        if current and buffer:
            text = _dehyphenate(buffer)[:MAX_DESC_CHARS]
            if len(text) > 40:  # ignore stray one-liners
                for target in current:
                    sections.setdefault(target, text)
        current, buffer = None, []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        key = norm(line)
        if key in index and len(line.split()) <= 6:
            flush()
            current = index[key]
            continue
        if _STOPPERS.match(line) or _SECTION.match(line):
            flush()
            continue
        if current is None:
            continue
        if _JUNK.search(line) and "Wireless" not in line:
            continue
        buffer.append(line)
        if len(buffer) >= MAX_SECTION_LINES:
            flush()
    flush()
    return sections


def enrich_descriptions(data_root: Path, book: str, domain: str, pages, force: bool = False) -> dict:
    domain_dir = data_root / book / domain
    payloads = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(domain_dir.glob("*.json"))
    }
    index = build_index(payloads)

    lines: list[str] = []
    for page in pages:
        lines.extend(t for _, _, t in parse_col_lines(read_cols(data_root, book, page).splitlines()))
    sections = parse_sections(lines, index)

    updated = 0
    for category, payload in payloads.items():
        changed = False
        for item in payload.get("items", []):
            text = sections.get((category, item["id"]))
            if not text:
                continue
            if item["system"].get("description") and not force:
                continue
            item["system"]["description"] = text
            updated += 1
            changed = True
        if changed:
            path = domain_dir / f"{category}.json"
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(p.get("items", [])) for p in payloads.values())
    return {"matched": len(sections), "updated": updated, "items": total}
