# Extractor + Core Rulebook Gear Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A standalone `python -m extractor` CLI (dump + parse subcommands) plus corebook parser profiles that produce the full Core Rulebook gear dataset in `data/corebook/gear/`, passing the validator.

**Architecture:** Two-stage pipeline. `dump` opens the PDF with pdfplumber once and caches normalized per-page text under `data/_raw/<book>/pages/` (gitignored — contains book text). `parse` never touches the PDF: it reads the cache, segments each configured page range into table blocks, parses rows with a declarative column-spec engine (one generic row parser driven by typed column fragments), maps rows to Eden `system` fields via per-table specs, and writes schema-valid category JSON. Correctness is enforced by (a) synthetic golden tests using invented rows in the same layout, and (b) a controller-driven QA diff against a reference extraction, per docs/design.md §3.

**Tech Stack:** Python 3.12+, pdfplumber (dump stage only), existing validator package for output checking.

## Global Constraints

- Runtime deps become: `jsonschema`, `referencing`, `pdfplumber` (dump only — parse must work without it installed if the cache exists; import pdfplumber lazily inside the dump command).
- **No copyrighted content committed**: raw page cache lives in `data/_raw/` (already covered by `data/**` gitignore); test fixtures use invented item rows only.
- Output items must validate against `schemas/gear.schema.json` — `python -m validator data/corebook` exits 0 when parsing succeeds.
- Item `meta`: `book: "corebook"`, `page` = the PDF-printed page the table appears on, `extractedAt` = run date, `extractorVersion` = `extractor.__version__` (start `"0.1.0"`), `qaStatus: "extracted"`.
- Item `id`: slugified name (lowercase, `[a-z0-9_]`, non-alphanumerics → `_`, collapse repeats, strip edge `_`); on collision within a category append `_2`, `_3`, ….
- Unicode normalization for all cached text: `’`→`'`, `—`/`–`/`−`→`—` (keep em-dash — it means "column empty"), ` `→space, `ﬁ`→`fi`, `ﬂ`→`fl`, strip `­`. Keep `¥` as-is.
- Eden field mapping (fixed): DV `3P`→`dmg:3, stun:false, dmgDef:"3P"`; `2S`→`dmg:2, stun:true`; suffix like `(e)` stays in `dmgDef`. Attack rating `10/6/2/—/—` → `attackRating:[10,6,2,0,0]` (strip `*`, `—`→0). Modes `SA/BF` → `modes:{SS:false,SA:true,BF:true,FA:false}`. Ammo `15(c)` → `ammocap:15` (feed letter dropped). Avail `4(L)` → `avail:4, availDef:"4(L)"` (plain `4` → `avail:4, availDef:"4"`). Cost `2,100¥` → `price:2100`. Essence `0.2` → `essence:0.2`. Vehicles: HANDL `4/2`→`handlOn:4, handlOff:2` (single value → both), ACCEL→`accOn`, TOP SPEED→`tspd`, BODY→`bod`, ARMOR→`arm`, PILOT→`pil`, SENSOR→`sen`, SEATS→`sea`; `vtype` = subtype slug lowercased.
- Commit trailer: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Working directory: `C:\Users\johnb\Documents\Projects\SR6-eden-Forge`; test runner `./.venv/Scripts/python -m pytest`.

## File Structure

```
extractor/__init__.py             ← __version__ = "0.1.0"
extractor/__main__.py             ← argparse: dump | parse subcommands
extractor/normalize.py            ← normalize_text(s) -> str
extractor/dump.py                 ← dump_book(pdf_path, book, pages, out_root)
extractor/cache.py                ← read_page(book, page, root) -> str; page_path()
extractor/columns.py              ← typed column regex fragments + converters
extractor/rowengine.py            ← RowSpec, parse_block(lines, spec) -> list[dict]
extractor/segment.py              ← extract_blocks(page_text, header_regex) -> list[list[str]]
extractor/emit.py                 ← build_item(), write_category(), slugify()
extractor/profiles/__init__.py    ← get_profile(book, domain)
extractor/profiles/corebook_gear.py  ← TableSpec list for every corebook gear table
extractor/run.py                  ← parse_book(book, domain, data_root): orchestrates
tests/test_normalize.py
tests/test_rowengine.py
tests/test_segment.py
tests/test_emit.py
tests/test_extractor_golden.py    ← synthetic raw pages -> expected JSON end-to-end
```

Tasks 5–7 (profiles + QA) iterate on `corebook_gear.py` only. The engine (Tasks 1–4) is book-agnostic.

---

### Task 1: Normalization + dump + cache

**Files:**
- Create: `extractor/__init__.py`, `extractor/normalize.py`, `extractor/dump.py`, `extractor/cache.py`, `extractor/__main__.py`
- Modify: `requirements.txt` (add `pdfplumber>=0.11`)
- Test: `tests/test_normalize.py`

**Interfaces:**
- Produces:
  - `extractor.normalize.normalize_text(s: str) -> str` — applies the Global Constraints unicode table.
  - `extractor.cache.page_path(root: Path, book: str, page: int) -> Path` — `root/_raw/<book>/pages/p<page>.txt` (root is the `data/` dir).
  - `extractor.cache.read_page(root: Path, book: str, page: int) -> str` — reads cached page, `FileNotFoundError` with message naming the dump command if missing.
  - `extractor.dump.dump_book(pdf_path: Path, book: str, pages: range, root: Path) -> int` — writes normalized text per page (1-based page numbers), returns count. Imports pdfplumber lazily.
  - CLI: `python -m extractor dump --pdf <path> --book corebook --pages 245-304 [--data data]` and `python -m extractor parse --book corebook --domain gear [--data data]` (parse wired fully in Task 4; until then it exits 2 with "parse not implemented").

- [ ] **Step 1: Failing tests** — `tests/test_normalize.py`:

```python
from pathlib import Path

from extractor.cache import page_path, read_page
from extractor.normalize import normalize_text


def test_normalize_unicode():
    s = "Zapgun’s 8/2*/—/–/− café 500¥ ﬁre"
    out = normalize_text(s)
    assert "’" not in out and "'" in out
    assert out.count("—") == 3  # en-dash and minus folded into em-dash
    assert " " not in out and " 500¥" in out
    assert "fire" in out


def test_soft_hyphen_stripped():
    assert normalize_text("com­bat") == "combat"


def test_page_path_layout(tmp_path):
    p = page_path(tmp_path, "corebook", 245)
    assert p == tmp_path / "_raw" / "corebook" / "pages" / "p245.txt"


def test_read_page_missing_names_dump(tmp_path):
    try:
        read_page(tmp_path, "corebook", 245)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        assert "extractor dump" in str(e)


def test_read_page_roundtrip(tmp_path):
    p = page_path(tmp_path, "corebook", 245)
    p.parent.mkdir(parents=True)
    p.write_text("hello", encoding="utf-8")
    assert read_page(tmp_path, "corebook", 245) == "hello"
```

- [ ] **Step 2: Run to verify FAIL** — `./.venv/Scripts/python -m pytest tests/test_normalize.py -v` → ModuleNotFoundError.

- [ ] **Step 3: Implement.**

`extractor/__init__.py`:

```python
__version__ = "0.1.0"
```

`extractor/normalize.py`:

```python
from __future__ import annotations

_TABLE = {
    "’": "'",
    "—": "—",
    "–": "—",
    "−": "—",
    " ": " ",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "­": "",
}
_TRANS = str.maketrans(_TABLE)


def normalize_text(s: str) -> str:
    return s.translate(_TRANS)
```

`extractor/cache.py`:

```python
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
```

`extractor/dump.py`:

```python
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
```

`extractor/__main__.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _pages(spec: str) -> range:
    start, _, end = spec.partition("-")
    return range(int(start), int(end or start) + 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="extractor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("dump", help="cache normalized page text from a PDF")
    d.add_argument("--pdf", required=True)
    d.add_argument("--book", required=True)
    d.add_argument("--pages", required=True, help="e.g. 245-304")
    d.add_argument("--data", default="data")

    p = sub.add_parser("parse", help="parse cached pages into data files")
    p.add_argument("--book", required=True)
    p.add_argument("--domain", required=True)
    p.add_argument("--data", default="data")
    p.add_argument("--categories", default="", help="comma-separated filter")

    args = parser.parse_args(argv)
    if args.cmd == "dump":
        from extractor.dump import dump_book

        n = dump_book(Path(args.pdf), args.book, _pages(args.pages), Path(args.data))
        print(f"dumped {n} page(s)")
        return 0
    from extractor.run import parse_book  # Task 4

    return parse_book(
        args.book,
        args.domain,
        Path(args.data),
        [c for c in args.categories.split(",") if c],
    )


if __name__ == "__main__":
    sys.exit(main())
```

Until Task 4 exists, create a stub `extractor/run.py`:

```python
from __future__ import annotations

from pathlib import Path


def parse_book(book: str, domain: str, data_root: Path, categories: list[str]) -> int:
    print("parse not implemented")
    return 2
```

Add `pdfplumber>=0.11` to `requirements.txt`. Run `./.venv/Scripts/pip install pdfplumber` (already installed in this venv — verify).

- [ ] **Step 4: Run to verify PASS** — `./.venv/Scripts/python -m pytest tests/test_normalize.py -v` → 5 passed. Full suite → 33 passed.

- [ ] **Step 5: Commit** — `feat: extractor dump/cache/normalize + CLI skeleton` (+ trailer).

---

### Task 2: Column engine (typed fragments + row parsing)

**Files:**
- Create: `extractor/columns.py`, `extractor/rowengine.py`
- Test: `tests/test_rowengine.py`

**Interfaces:**
- Produces:
  - `extractor.columns.COLUMNS: dict[str, Column]` — `Column(pattern: str, convert: Callable[[str], dict])`; each `convert` returns a dict of Eden system fields. Keys and behavior:
    - `dv`: `(?P<dv>\d{1,2}[PS](?:\([a-z]+\))?)` → dmg/stun/dmgDef per Global Constraints.
    - `modes`: `(?P<modes>(?:SS|SA|BF|FA)(?:/(?:SS|SA|BF|FA))*)` → modes dict.
    - `ar`: `(?P<ar>[0-9*]+(?:/[0-9*—]+){4})` → attackRating (strip `*`, `—`→0). Also accepts a 1-element variant? No — exactly 5 slots.
    - `ammo`: `(?P<ammo>\d+(?:\([a-z]+\))?)` → ammocap int.
    - `avail`: `(?P<avail>\d{1,2}(?:\([A-Z]\))?)` → avail int + availDef raw.
    - `cost`: `(?P<cost>[\d,]+¥)` → price int (strip commas and ¥).
    - `essence`: `(?P<essence>\d(?:\.\d{1,2})?)` → essence float.
    - `rating_txt`: `(?P<rating_txt>[\dA-Za-z—/+\-]+)` → `{}` (consumed, informational only).
    - `capacity`: `(?P<capacity>[\d—]+)` → capacity int (`—`→0).
    - `int:<field>`: `(?P<f_<field>>[\d—]+)` → that Eden int field (`—`→0). e.g. `int:bod`.
    - `onoff:<on>:<off>`: `(?P<x_<on>>\d+(?:/\d+)?)` → on/off pair fields (single → both).
    - `text:<field>`: `(?P<t_<field>>\S+)` → string field.
  - `extractor.rowengine.RowSpec(columns: list[str], defaults: dict)` — `columns` are keys above, matched left-to-right after the name; name = everything before the first column match.
  - `extractor.rowengine.parse_block(lines: list[str], spec: RowSpec, page_numbers: set[int] = frozenset()) -> list[ParsedRow]` where `ParsedRow = (name: str, system: dict)`:
    - Joins wrapped rows: buffer up to 3 consecutive lines until the assembled string matches the spec's full regex; on match, emit and reset. Non-matching leftovers are dropped when the buffer exceeds 3 lines (drop the first buffered line and retry).
    - Strips stray page-number tokens: any standalone token in `page_numbers` is removed before matching.
    - `system` = merge of spec.defaults + every column converter's output. Name is title-stripped (collapse spaces).

- [ ] **Step 1: Failing tests** — `tests/test_rowengine.py` (invented items only):

```python
from extractor.rowengine import RowSpec, parse_block

FIREARM = RowSpec(
    columns=["dv", "modes", "ar", "ammo", "avail", "cost"],
    defaults={"type": "WEAPON_FIREARMS", "skill": "firearms"},
)
MELEE = RowSpec(
    columns=["dv", "ar", "avail", "cost"],
    defaults={"type": "WEAPON_CLOSE_COMBAT", "skill": "close_combat"},
)
CYBER = RowSpec(
    columns=["essence", "capacity", "avail", "cost"],
    defaults={"type": "CYBERWARE"},
)


def test_simple_firearm_row():
    rows = parse_block(["Zapgun Mk1 3P SA/BF 10/10/8/—/— 15(c) 2(L) 750¥"], FIREARM)
    assert len(rows) == 1
    name, system = rows[0]
    assert name == "Zapgun Mk1"
    assert system["dmg"] == 3 and system["stun"] is False and system["dmgDef"] == "3P"
    assert system["modes"] == {"SS": False, "SA": True, "BF": True, "FA": False}
    assert system["attackRating"] == [10, 10, 8, 0, 0]
    assert system["ammocap"] == 15
    assert system["avail"] == 2 and system["availDef"] == "2(L)"
    assert system["price"] == 750
    assert system["type"] == "WEAPON_FIREARMS" and system["skill"] == "firearms"


def test_wrapped_row_reassembled():
    lines = ["Very Long Fictional Gun Name", "4P SS 8/6/—/—/— 6(c) 3 1,200¥"]
    rows = parse_block(lines, FIREARM)
    assert rows[0][0] == "Very Long Fictional Gun Name"
    assert rows[0][1]["price"] == 1200


def test_stray_page_number_stripped():
    lines = ["Fictional Pistol 253 2P SS 9/8/—/—/— 10(c) 2 300¥"]
    rows = parse_block(lines, FIREARM, page_numbers={253})
    assert rows[0][0] == "Fictional Pistol"


def test_melee_with_asterisk_and_stun():
    rows = parse_block(["Practice Club 2S 8/2*/—/—/— 1 20¥"], MELEE)
    name, system = rows[0]
    assert system["stun"] is True and system["dmg"] == 2
    assert system["attackRating"] == [8, 2, 0, 0, 0]


def test_cyberware_essence():
    rows = parse_block(["Fake Eye Mk2 0.2 4 6 2,500¥"], CYBER)
    _, system = rows[0]
    assert system["essence"] == 0.2 and system["capacity"] == 4
    assert system["avail"] == 6 and system["price"] == 2500


def test_prose_lines_ignored():
    lines = [
        "This paragraph explains why the gun is popular on the streets.",
        "Zapgun Mk1 3P SA 10/10/8/—/— 15(c) 2 750¥",
    ]
    rows = parse_block(lines, FIREARM)
    assert len(rows) == 1


def test_dv_with_element_suffix():
    rows = parse_block(["Shock Rod 4S(e) 6/—/—/—/— 3 400¥"], MELEE)
    assert rows[0][1]["dmgDef"] == "4S(e)" and rows[0][1]["stun"] is True
```

- [ ] **Step 2: Run to verify FAIL.**

- [ ] **Step 3: Implement** `extractor/columns.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Column:
    pattern: str
    convert: Callable[[str], dict]


def _dv(v: str) -> dict:
    m = re.match(r"(\d{1,2})([PS])", v)
    return {"dmg": int(m.group(1)), "stun": m.group(2) == "S", "dmgDef": v}


def _modes(v: str) -> dict:
    parts = set(v.split("/"))
    return {"modes": {m: m in parts for m in ("SS", "SA", "BF", "FA")}}


def _ar(v: str) -> dict:
    slots = []
    for tok in v.split("/"):
        tok = tok.replace("*", "")
        slots.append(0 if tok in ("", "—") else int(tok))
    return {"attackRating": slots}


def _ammo(v: str) -> dict:
    return {"ammocap": int(re.match(r"\d+", v).group())}


def _avail(v: str) -> dict:
    return {"avail": int(re.match(r"\d+", v).group()), "availDef": v}


def _cost(v: str) -> dict:
    return {"price": int(v.rstrip("¥").replace(",", ""))}


def _essence(v: str) -> dict:
    return {"essence": float(v)}


def _capacity(v: str) -> dict:
    return {"capacity": 0 if v == "—" else int(v)}


COLUMNS: dict[str, Column] = {
    "dv": Column(r"\d{1,2}[PS](?:\([a-z]+\))?", _dv),
    "modes": Column(r"(?:SS|SA|BF|FA)(?:/(?:SS|SA|BF|FA))*", _modes),
    "ar": Column(r"[0-9*—]+(?:/[0-9*—]+){4}", _ar),
    "ammo": Column(r"\d+(?:\([a-z]+\))?", _ammo),
    "avail": Column(r"\d{1,2}(?:\([A-Z]\))?", _avail),
    "cost": Column(r"[\d,]+¥", _cost),
    "essence": Column(r"\d(?:\.\d{1,2})?", _essence),
    "capacity": Column(r"[\d—]+", _capacity),
}


def make_int_column(field: str) -> Column:
    return Column(r"[\d—]+", lambda v, f=field: {f: 0 if v == "—" else int(v)})


def make_onoff_column(on: str, off: str) -> Column:
    def conv(v: str, on=on, off=off) -> dict:
        if "/" in v:
            a, b = v.split("/", 1)
            return {on: int(a), off: int(b)}
        return {on: int(v), off: int(v)}

    return Column(r"\d+(?:/\d+)?", conv)


def make_text_column(field: str) -> Column:
    return Column(r"\S+", lambda v, f=field: {f: v})


def resolve(key: str) -> Column:
    if key in COLUMNS:
        return COLUMNS[key]
    if key.startswith("int:"):
        return make_int_column(key[4:])
    if key.startswith("onoff:"):
        _, on, off = key.split(":")
        return make_onoff_column(on, off)
    if key.startswith("text:"):
        return make_text_column(key[5:])
    raise KeyError(f"unknown column type {key!r}")
```

`extractor/rowengine.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field

from extractor.columns import resolve

MAX_WRAP = 3


@dataclass(frozen=True)
class RowSpec:
    columns: list[str]
    defaults: dict = field(default_factory=dict)

    def regex(self) -> re.Pattern:
        parts = [f"(?P<name>.+?)"]
        for i, key in enumerate(self.columns):
            parts.append(f"(?P<c{i}>{resolve(key).pattern})")
        return re.compile(r"^\s*" + r"\s+".join(parts) + r"\s*$")


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
    return True


def parse_block(
    lines: list[str], spec: RowSpec, page_numbers: set[int] = frozenset()
) -> list[tuple[str, dict]]:
    rx = spec.regex()
    rows: list[tuple[str, dict]] = []
    buffer: list[str] = []

    def emit(match: re.Match) -> None:
        system = dict(spec.defaults)
        for i, key in enumerate(spec.columns):
            system.update(resolve(key).convert(match.group(f"c{i}")))
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
            _, m = max(plausible, key=lambda c: c[0]) if plausible else min(candidates, key=lambda c: c[0])
            emit(m)
            buffer = []
        elif len(buffer) > MAX_WRAP:
            buffer.pop(0)
    return rows
```

- [ ] **Step 4: Run to verify PASS** — 8 new tests; full suite 41.
- [ ] **Step 5: Commit** — `feat: declarative column engine for table row parsing` (+ trailer).

---

### Task 3: Segmenter (page text → table blocks)

**Files:**
- Create: `extractor/segment.py`
- Test: `tests/test_segment.py`

**Interfaces:**
- Produces: `extractor.segment.block_after_header(page_text: str, header_regex: str, stop_regexes: list[str]) -> list[str]` — returns the lines strictly after the first line matching `header_regex` (case-sensitive regex, searched with `re.search`), stopping at (excluding) the first subsequent line that matches any of `stop_regexes` OR a second occurrence of an all-caps table-header-looking line (`^[A-Z][A-Z /()]+$` with length > 12). Returns `[]` if header not found. Multiple tables per page are handled by callers passing distinct header regexes.

- [ ] **Step 1: Failing tests** — `tests/test_segment.py`:

```python
from extractor.segment import block_after_header

PAGE = """intro prose about fictional guns
zap pistols
WEAPON DV MODES ATTACK RATINGS AMMO AVAILABILITY COST
Zapgun Mk1 3P SA 10/10/8/—/— 15(c) 2 750¥
Zapgun Mk2 4P SA/BF 11/11/9/—/— 20(c) 3 1,100¥
zap rifles
WEAPON DV MODES ATTACK RATINGS AMMO AVAILABILITY COST
Zapri fle Alpha 5P SA/BF/FA 4/11/9/7/1 38(c) 2 2,000¥
closing prose paragraph
"""


def test_block_between_header_and_next_header():
    lines = block_after_header(PAGE, r"^zap pistols$", [])
    assert lines[0].startswith("Zapgun Mk1")
    assert lines[1].startswith("Zapgun Mk2")
    assert len([l for l in lines if "Zapri" in l]) == 0


def test_block_with_stop_regex():
    lines = block_after_header(PAGE, r"^zap rifles$", [r"^closing prose"])
    assert any("Zapri" in l for l in lines)
    assert not any("closing prose" in l for l in lines)


def test_missing_header_returns_empty():
    assert block_after_header(PAGE, r"^no such section$", []) == []


def test_column_header_line_is_skipped():
    lines = block_after_header(PAGE, r"^zap pistols$", [])
    assert not any(l.startswith("WEAPON DV") for l in lines)
```

- [ ] **Step 2: Run to verify FAIL.**
- [ ] **Step 3: Implement** `extractor/segment.py`:

```python
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
```

- [ ] **Step 4: Run to verify PASS** — full suite 45.
- [ ] **Step 5: Commit** — `feat: page segmenter for table blocks` (+ trailer).

---

### Task 4: Emit + orchestration + golden end-to-end test

**Files:**
- Create: `extractor/emit.py`, `extractor/profiles/__init__.py`
- Rewrite: `extractor/run.py` (replace Task 1 stub)
- Test: `tests/test_emit.py`, `tests/test_extractor_golden.py`

**Interfaces:**
- Consumes: cache, segment, rowengine, profiles.
- Produces:
  - `extractor.emit.slugify(name: str) -> str` per Global Constraints.
  - `extractor.emit.build_item(name, system, book, page, version) -> dict` — full item with meta (`extractedAt` = `date.today().isoformat()`, `qaStatus:"extracted"`).
  - `extractor.emit.write_category(data_root, book, domain, category, items) -> Path` — writes envelope JSON (2-space indent, `ensure_ascii=False`, trailing newline), dedups ids with `_2` suffixes.
  - `TableSpec` dataclass in `extractor/profiles/__init__.py`: `(category: str, pages: list[int], header_regex: str, stop_regexes: list[str], row_spec: RowSpec, page_override: int | None = None)` — `category` names the output file; multiple TableSpecs may share a category (rows concatenate in spec order).
  - `extractor.profiles.get_profile(book: str, domain: str) -> list[TableSpec]` — imports `extractor.profiles.<book>_<domain>` and returns its `TABLES` list; raises `SystemExit` with clear message for unknown combos.
  - `extractor.run.parse_book(book, domain, data_root, categories) -> int` — for each TableSpec (filtered by categories if given): read each page from cache, `block_after_header`, `parse_block` with `page_numbers={page-1, page, page+1}`, build items (meta.page = page_override or the page the row came from), group by category, `write_category`, print per-category counts, return 0 (or 1 if any category produced zero items — loud failure for layout drift).

- [ ] **Step 1: Failing tests** — `tests/test_emit.py`:

```python
from extractor.emit import build_item, slugify, write_category


def test_slugify():
    assert slugify("Zapgun Predator VI") == "zapgun_predator_vi"
    assert slugify("Combat/survival knife") == "combat_survival_knife"
    assert slugify("  Bull's-eye!  ") == "bull_s_eye"


def test_build_item_meta(monkeypatch):
    item = build_item("Zapgun Mk1", {"type": "WEAPON_FIREARMS"}, "corebook", 253, "0.1.0")
    assert item["id"] == "zapgun_mk1"
    assert item["meta"]["book"] == "corebook" and item["meta"]["page"] == 253
    assert item["meta"]["qaStatus"] == "extracted"
    assert item["meta"]["extractorVersion"] == "0.1.0"


def test_write_category_dedups_ids(tmp_path):
    items = [
        build_item("Same Name", {"type": "TOOLS"}, "corebook", 1, "0.1.0"),
        build_item("Same Name", {"type": "TOOLS"}, "corebook", 2, "0.1.0"),
    ]
    p = write_category(tmp_path, "corebook", "gear", "tools", items)
    import json

    data = json.loads(p.read_text(encoding="utf-8"))
    ids = [i["id"] for i in data["items"]]
    assert ids == ["same_name", "same_name_2"]
    assert data["book"] == "corebook" and data["domain"] == "gear" and data["category"] == "tools"
```

`tests/test_extractor_golden.py` — end-to-end on a synthetic cached page, then validator must pass:

```python
import json

from validator.cli import main as validate

from extractor.run import parse_book

FAKE_PAGE = """fictional pistols
WEAPON DV MODES ATTACK RATINGS AMMO AVAILABILITY COST
Zapgun Mk1 3P SA 10/10/8/—/— 15(c) 2 750¥
Zapgun Mk2 4P SA/BF 11/11/9/—/— 20(c) 3(L) 1,100¥
"""


def test_golden_roundtrip(tmp_path, monkeypatch):
    raw = tmp_path / "_raw" / "testbook" / "pages" / "p10.txt"
    raw.parent.mkdir(parents=True)
    raw.write_text(FAKE_PAGE, encoding="utf-8")

    import extractor.profiles as profiles
    from extractor.profiles import TableSpec
    from extractor.rowengine import RowSpec

    monkeypatch.setattr(
        profiles,
        "get_profile",
        lambda book, domain: [
            TableSpec(
                category="weapons_firearms",
                pages=[10],
                header_regex=r"^fictional pistols$",
                stop_regexes=[],
                row_spec=RowSpec(
                    columns=["dv", "modes", "ar", "ammo", "avail", "cost"],
                    defaults={"type": "WEAPON_FIREARMS", "subtype": "PISTOLS_LIGHT", "skill": "firearms"},
                ),
            )
        ],
    )
    import extractor.run as run
    monkeypatch.setattr(run, "get_profile", profiles.get_profile)

    rc = parse_book("testbook", "gear", tmp_path, [])
    assert rc == 0
    out = json.loads((tmp_path / "testbook" / "gear" / "weapons_firearms.json").read_text(encoding="utf-8"))
    assert [i["name"] for i in out["items"]] == ["Zapgun Mk1", "Zapgun Mk2"]
    assert out["items"][1]["system"]["price"] == 1100
    assert validate([str(tmp_path / "testbook")]) == 0
```

- [ ] **Step 2: Run to verify FAIL.**
- [ ] **Step 3: Implement.**

`extractor/emit.py`:

```python
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower())
    return s.strip("_")


def build_item(name: str, system: dict, book: str, page: int, version: str) -> dict:
    return {
        "id": slugify(name),
        "name": name,
        "system": system,
        "meta": {
            "book": book,
            "page": page,
            "extractedAt": date.today().isoformat(),
            "extractorVersion": version,
            "qaStatus": "extracted",
        },
    }


def write_category(data_root: Path, book: str, domain: str, category: str, items: list[dict]) -> Path:
    seen: dict[str, int] = {}
    for item in items:
        base = item["id"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            item["id"] = f"{base}_{seen[base]}"
    payload = {"book": book, "domain": domain, "category": category, "items": items}
    out = data_root / book / domain / f"{category}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
```

`extractor/profiles/__init__.py`:

```python
from __future__ import annotations

import importlib
from dataclasses import dataclass, field

from extractor.rowengine import RowSpec


@dataclass(frozen=True)
class TableSpec:
    category: str
    pages: list[int]
    header_regex: str
    stop_regexes: list[str]
    row_spec: RowSpec
    page_override: int | None = None


def get_profile(book: str, domain: str) -> list[TableSpec]:
    name = f"extractor.profiles.{book}_{domain}"
    try:
        mod = importlib.import_module(name)
    except ModuleNotFoundError:
        raise SystemExit(f"no profile module {name} — create it to extract {book}/{domain}")
    return mod.TABLES
```

`extractor/run.py` (replace stub):

```python
from __future__ import annotations

from pathlib import Path

import extractor
from extractor.cache import read_page
from extractor.emit import build_item, write_category
from extractor.profiles import get_profile
from extractor.rowengine import parse_block
from extractor.segment import block_after_header


def parse_book(book: str, domain: str, data_root: Path, categories: list[str]) -> int:
    specs = get_profile(book, domain)
    if categories:
        specs = [s for s in specs if s.category in categories]
    if not specs:
        print("no categories matched")
        return 1
    by_category: dict[str, list[dict]] = {s.category: [] for s in specs}
    for spec in specs:
        for page in spec.pages:
            text = read_page(data_root, book, page)
            lines = block_after_header(text, spec.header_regex, spec.stop_regexes)
            noise = {page - 1, page, page + 1}
            for name, system in parse_block(lines, spec.row_spec, page_numbers=noise):
                meta_page = spec.page_override or page
                by_category[spec.category].append(
                    build_item(name, system, book, meta_page, extractor.__version__)
                )
    empty = []
    for category, items in sorted(by_category.items()):
        write_category(data_root, book, domain, category, items)
        print(f"{category}: {len(items)} item(s)")
        if not items:
            empty.append(category)
    if empty:
        print(f"EMPTY: {', '.join(empty)}")
        return 1
    return 0
```

- [ ] **Step 4: Run to verify PASS** — full suite 49.
- [ ] **Step 5: Commit** — `feat: emit + profile-driven parse orchestration with golden test` (+ trailer).

---

### Task 5: Corebook profile — weapons (controller QA loop)

**Files:**
- Create: `extractor/profiles/corebook_gear.py` (weapons portion)

This task is executed by the controller (Claude session) directly with PDF access, NOT by a code subagent, because it requires reading the real cached pages and iterating on header regexes until counts and spot-checks match a reference reading of the book. Process:

- [ ] Dump the gear chapter: `python -m extractor dump --pdf "<corebook pdf>" --book corebook --pages 245-304`
- [ ] Add TableSpecs for: taser/holdouts/light/machine/heavy pistols, SMGs, shotguns, rifles, machine guns, launchers (WEAPON_FIREARMS, per-table subtype, skill firearms); bows/crossbows/throwing (WEAPON_RANGED, skill athletics for throwing / exotic per book); blades/clubs/other melee (WEAPON_CLOSE_COMBAT, skill close_combat); weapon accessories (ACCESSORY/FIREARMS_ACCESSORY — columns mount(text)/avail/cost); grenades+rockets+missiles (WEAPON_SPECIAL — DV/blast columns via int fields where parseable).
- [ ] Run parse for these categories; eyeball every output file against the cached raw text; adjust regexes until item counts match the tables in the book and spot-checked rows are exact.
- [ ] `python -m validator data/corebook` → exit 0.
- [ ] Commit profile: `feat: corebook weapons parser profiles` (+ trailer). Data is NOT committed.

### Task 6: Corebook profile — armor, electronics, tools, survival, biotech

- [ ] Same controller QA loop for: armor + helmets/shields (ARMOR / ARMOR_ADDITION — defense int column, capacity); commlinks/cyberdecks/rigger consoles/comm devices (ELECTRONICS subtypes; cyberdecks map A/S columns to `a`/`s` int fields); software (SOFTWARE); credsticks (ELECTRONICS/ID_CREDIT); RFID (ELECTRONICS/RFID); tools (TOOLS); visual/audio enhancements + sensors (ELECTRONICS subtypes); B&E gear (TOOLS/BREAKING); industrial chemicals (CHEMICALS); survival gear (SURVIVAL); biotech (BIOLOGY/BIOTECH).
- [ ] Validator exit 0; commit `feat: corebook armor/electronics/tools profiles` (+ trailer).

### Task 7: Corebook profile — augmentation, magical, vehicles, drones

- [ ] Same loop for: cyberjacks/headware/eyeware/earware/bodyware (CYBERWARE subtypes, essence+capacity columns); cyberlimbs (special dual-cost table — parse synthetic/obvious costs into price=obvious cost, note synthetic in `notes`); implant weapons (CYBER_IMPLANT_WEAPON); bioware + cultured (BIOWARE, rating column consumed, essence); magical goods (MAGICAL subtypes); vehicles (VEHICLES subtypes — onoff handling, int columns bod/arm/pil/sen/sea, tspd); drones (DRONES subtypes).
- [ ] Validator exit 0 across ALL of data/corebook; commit `feat: corebook augmentation/magical/vehicle profiles` (+ trailer).

### Task 8: Docs + wrap-up

- [ ] README: extractor usage section (dump + parse commands, profile-writing guide pointer); Status checklist: extractor + corebook dataset checked.
- [ ] `docs/extraction-notes-corebook.md`: page map (245-304 categories), quirks found (wrapped rows, stray page numbers, footnote asterisks), item counts per category as extracted.
- [ ] Full suite green; commit `docs: extractor usage + corebook extraction notes` (+ trailer); push.

## Self-Review Notes

- Engine tasks (1–4) contain complete code and synthetic tests; profile tasks (5–7) are deliberately controller-run QA loops per docs/design.md §3 ("Claude's role is in the build phase") — a code subagent cannot iterate against copyrighted page text it cannot see in fixtures.
- Type consistency: `RowSpec(columns, defaults)` used identically in Tasks 2/4/5; `TableSpec` fields match between profiles/__init__ and run.py; `parse_book` signature matches the Task 1 CLI stub call.
- The zero-items-is-failure rule in run.py guards against silent layout drift when Eden or the PDF printing changes.
