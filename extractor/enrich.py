"""Attribute per-item prose writeups from the column-ordered page cache to
items in the local dataset (system.description). Runs entirely against the
user's local page cache and local data files.

Matching model: item names generate normalized heading keys (full name plus
variants for parenthetical/slash/comma forms and plurals). A heading line on
page P matches an item only when the item's own table page is within
PAGE_WINDOW of P — that is what disambiguates identically-named gear in
different chapters (e.g. an external device and its cyberware twin). Group
headings ("Cyberjacks") attach to every family member via prefix matching.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from extractor.cache import read_cols
from extractor.textcols import COLUMN_BREAK

MAX_SECTION_LINES = 120
MAX_DESC_CHARS = 3500
PAGE_WINDOW = 8       # heading may sit several pages before the item's table
PREFIX_MIN = 6        # min normalized-key length for group-prefix matching
# lines that end a writeup section even if no new heading was seen
_STOPPERS = re.compile(r"^[A-Z][A-Z /()&'’]{11,}$")  # table/column headers
_JUNK = re.compile(r"¥|\d/\d.*\d/\d|^\d{1,3}$")  # stat rows, bare page numbers


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


def _plural_forms(key: str) -> set[str]:
    forms = {key}
    if key.endswith("s"):
        forms.add(key[:-1])
    else:
        forms.add(key + "s")
    return forms


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
    out: set[str] = set()
    for k in keys:
        if k:
            out |= _plural_forms(k)
    return out


@dataclass(frozen=True)
class Target:
    category: str
    item_id: str
    page: int
    name: str


class HeadingIndex:
    def __init__(self, payloads: dict[str, dict]):
        self.by_key: dict[str, list[Target]] = {}
        self.full_keys: dict[str, list[Target]] = {}
        self.subtype_keys: dict[str, list[Target]] = {}
        for category, payload in payloads.items():
            for item in payload.get("items", []):
                target = Target(category, item["id"], item.get("meta", {}).get("page", 0), item["name"])
                for key in _plural_forms(norm(item["name"])):
                    self.full_keys.setdefault(key, []).append(target)
                for key in heading_keys(item["name"]):
                    self.by_key.setdefault(key, []).append(target)
                subtype = str(item.get("system", {}).get("subtype", "")).replace("_", " ")
                if subtype:
                    for key in _plural_forms(norm(subtype)):
                        self.subtype_keys.setdefault(key, []).append(target)
        self._prefix_pool = sorted(
            (key, targets) for key, targets in self.full_keys.items() if len(key) >= PREFIX_MIN
        )

    def match(self, line: str, page: int | None) -> list[Target]:
        """Targets whose writeup heading this line plausibly is."""
        if len(line.split()) > 6:
            return []
        key = norm(line)
        if not key:
            return []
        candidates = list(self.by_key.get(key, []))
        if not candidates:
            words = line.split()
            for k in (2, 1):
                if len(words) > k:
                    tail_key = norm(" ".join(words[-k:]))
                    if tail_key in self.by_key:
                        key = tail_key
                        candidates = list(self.by_key[key])
                        break
        if len(key) >= PREFIX_MIN:
            for full_key, targets in self._prefix_pool:
                if full_key.startswith(key) and full_key != key:
                    candidates.extend(targets)  # group heading: 'Cyberjacks' -> rating family
        if not candidates:
            group = self.subtype_keys.get(key, [])
            if page is not None:
                group = [t for t in group if t.page and abs(t.page - page) <= PAGE_WINDOW]
            if group:
                return _dedupe(group)
            return []
        if page is not None:
            candidates = [t for t in candidates if t.page and abs(t.page - page) <= PAGE_WINDOW]
        if not candidates:
            return []
        # a non-full-name key shared by several DIFFERENT item names is only
        # trustworthy when it narrowed to one family of names
        names = {t.name for t in candidates}
        if len(names) > 1 and key not in self.full_keys and not _all_same_family(names):
            return []
        return _dedupe(candidates)


def _dedupe(targets):
    seen = set()
    out = []
    for t in targets:
        if (t.category, t.item_id) not in seen:
            seen.add((t.category, t.item_id))
            out.append(t)
    return out


def _all_same_family(names: set[str]) -> bool:
    """'Cyberjack (Rating 1..6)' / 'Wired Reflexes 1..4' style families
    share the same base name once parens and trailing numbers drop."""
    bases = set()
    for n in names:
        base = re.sub(r"\s*\(.*?\)$", "", n).strip().casefold()
        bases.add(re.sub(r"\s+\d+$", "", base))
    return len(bases) == 1


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


def _stat_like(line: str) -> bool:
    """True for table-row debris (mostly numeric/symbol tokens); False for a
    prose sentence that happens to mention a price."""
    tokens = line.split()
    if not tokens:
        return True
    numeric = sum(1 for t in tokens if re.search(r"[\d¥]", t) or t == "—")
    return numeric / len(tokens) > 0.4 or len(tokens) <= 3


def parse_sections(lines, index) -> dict[tuple[str, str], str]:
    """lines: iterable of str or (page|None, str). A line matching a known
    item name opens a section captured until the next heading/stopper."""
    sections: dict[tuple[str, str], str] = {}
    current: list[Target] | None = None
    buffer: list[str] = []

    def flush():
        nonlocal current, buffer
        if current and buffer:
            text = _dehyphenate(buffer)[:MAX_DESC_CHARS]
            if len(text) > 40:  # ignore stray one-liners
                for t in current:
                    key = (t.category, t.item_id)
                    if len(text) > len(sections.get(key, "")):
                        sections[key] = text
        current, buffer = None, []

    for entry in lines:
        page, raw = entry if isinstance(entry, tuple) else (None, entry)
        line = raw.strip()
        if not line:
            continue
        targets = index.match(line, page)
        if targets:
            flush()
            current = targets
            continue
        if current is None:
            continue
        if _STOPPERS.match(line):
            continue
        if _JUNK.search(line) and "Wireless" not in line and _stat_like(line):
            continue
        buffer.append(line)
        if len(buffer) >= MAX_SECTION_LINES:
            flush()
    flush()
    return sections


def build_index(payloads: dict[str, dict]) -> HeadingIndex:
    return HeadingIndex(payloads)


def enrich_descriptions(data_root: Path, book: str, domain: str, pages, force: bool = False) -> dict:
    domain_dir = data_root / book / domain
    payloads = {
        p.stem: json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(domain_dir.glob("*.json"))
    }
    index = build_index(payloads)

    lines: list[tuple[int, str]] = []
    for page in pages:
        for _, _, text in parse_col_lines(read_cols(data_root, book, page).splitlines()):
            lines.append((page, text))
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
