# Description Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all item `system.description` values with a precision-first extractor that anchors on text search, ranks candidates with font/position, captures a variable-length prose block, and falls back writeup → notes → empty.

**Architecture:** A pure, unit-tested core `extractor/writeups.py` operating on a flat list of `LineRec(page, col, is_head, text)` so tests need no PDF. A thin PDF reader turns a book into that list. A driver `tools/rebuild_descriptions.py` walks the dataset, opens each source book once, applies the fallback chain, skips manually-corrected items, and runs dry-run/apply plus a smell-check.

**Tech Stack:** Python 3.14, pdfplumber (already a dep), pytest. Reuse `extractor.enrich.norm` and `extractor.enrich.heading_keys` for name normalization.

## Global Constraints

- Library namespace is `corebook`; data lives at `data/corebook/<domain>/*.json`. Edit in place.
- `data/` is gitignored — commit only tooling/tests, never data.
- Never touch items with a correction file at `data/_corrections/<domain>/<id>.json`.
- Precision over recall: return `None`/empty rather than wrong text.
- `notes` is read-only — never written.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- Char cap for a description: `MAX_DESC = 3500`, trimmed only at a sentence boundary.
- Page window for ranking: `PAGE_WINDOW = 3`.

---

### Task 1: `is_stat_line` — boundary/stat-row detector

**Files:**
- Create: `extractor/writeups.py`
- Test: `tests/test_writeups.py`

**Interfaces:**
- Produces: `is_stat_line(text: str) -> bool` — True when a line is a stat/table row,
  ALL-CAPS column header, price row, or bare page number (never enters prose).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_writeups.py
from extractor.writeups import is_stat_line


def test_is_stat_line_flags_stats_and_headers():
    assert is_stat_line("Crossbow, Light 2P Crossbow, Standard 3P")   # damage codes
    assert is_stat_line("HAND ACC SPD INT TOP SPD BODY ARM AVAIL COST")  # table header
    assert is_stat_line("11,500¥")                                     # nuyen
    assert is_stat_line("2/5 35 40 250 3 3 2 1 1 2")                    # numeric stat row
    assert is_stat_line("263")                                         # bare page number
    assert not is_stat_line("An implanted version of the flare compensation system.")
    assert not is_stat_line("A nice haircut and the right makeup can change everything.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_writeups.py::test_is_stat_line_flags_stats_and_headers -v`
Expected: FAIL (`ModuleNotFoundError: extractor.writeups`)

- [ ] **Step 3: Write minimal implementation**

```python
# extractor/writeups.py
"""Precision-first item-writeup extraction. Pure core over a flat LineRec list
so it is unit-testable without a PDF. Anchors on text search, ranks candidates
with font/position, captures a variable-length prose block, cleans it. No book
content is stored here."""
from __future__ import annotations

import re
from collections import namedtuple

from extractor.enrich import heading_keys, norm

MAX_DESC = 3500
PAGE_WINDOW = 3

LineRec = namedtuple("LineRec", "page col is_head text")

_DICE = re.compile(r"\b\d+[PS]\b|\b\d/\d\b|\b\d{1,2}[PS]\s+\d")
_CAPS_HEADER = re.compile(r"^[A-Z][A-Z /()&'’]{11,}$")
_BARE_NUM = re.compile(r"^\d{1,3}$")
_NUMERIC_ROW = re.compile(r"^[\d/.,\s]+$")


def is_stat_line(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if "¥" in t:
        return True
    if _CAPS_HEADER.match(t):
        return True
    if _BARE_NUM.match(t):
        return True
    if len(t) >= 5 and _NUMERIC_ROW.match(t):
        return True
    if _DICE.search(t):
        return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_writeups.py::test_is_stat_line_flags_stats_and_headers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add extractor/writeups.py tests/test_writeups.py
git commit -m "feat: is_stat_line boundary detector for writeup extraction

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `clean_block` — dehyphenate, join, strip leading fragment, sentence-trim

**Files:**
- Modify: `extractor/writeups.py`
- Test: `tests/test_writeups.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `clean_block(texts: list[str]) -> str` — joins captured lines into clean
  prose: merges hyphenated line breaks, joins with single spaces, drops a stray
  leading lowercase fragment, trims a trailing partial sentence, caps at `MAX_DESC`
  on a sentence boundary, collapses whitespace.

- [ ] **Step 1: Write the failing test**

```python
from extractor.writeups import clean_block


def test_clean_block_dehyphenates_and_joins():
    out = clean_block(["An implanted version of the flare compensa-",
                       "tion system that shields the user's eyes."])
    assert out == "An implanted version of the flare compensation system that shields the user's eyes."


def test_clean_block_strips_leading_lowercase_fragment():
    out = clean_block(["enhancement An implanted version of the system works well."])
    assert out.startswith("An implanted version")


def test_clean_block_trims_trailing_partial_sentence():
    out = clean_block(["This is a complete sentence. And this one trails off with any fo"])
    assert out == "This is a complete sentence."


def test_clean_block_keeps_multiple_sentences():
    out = clean_block(["First paragraph text here.", "Second sentence continues the idea."])
    assert out == "First paragraph text here. Second sentence continues the idea."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_writeups.py -k clean_block -v`
Expected: FAIL (`clean_block` not defined)

- [ ] **Step 3: Write minimal implementation**

```python
# add to extractor/writeups.py
_SENT_END = re.compile(r"[.!?][\"'”’)]?\s")


def _join(texts: list[str]) -> str:
    out = ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if out.endswith("-"):
            out = out[:-1] + t            # dehyphenate line break
        elif out:
            out += " " + t
        else:
            out = t
    return re.sub(r"\s+", " ", out).strip()


def _strip_leading_fragment(text: str) -> str:
    # drop a leading lowercase run (tail of a heading line) up to the first
    # capitalized word that starts a sentence
    if text and text[0].islower():
        m = re.search(r"\b[A-Z]", text)
        if m:
            return text[m.start():]
    return text


def _sentence_trim(text: str) -> str:
    if len(text) > MAX_DESC:
        cut = text.rfind(". ", 0, MAX_DESC)
        if cut > 0:
            text = text[:cut + 1]
    # if it doesn't end on a terminator, cut back to the last complete sentence
    if text and text[-1] not in ".!?\"'”’)":
        ends = [m.end() for m in _SENT_END.finditer(text + " ")]
        if ends:
            text = text[:ends[-1]].strip()
    return text.strip()


def clean_block(texts: list[str]) -> str:
    return _sentence_trim(_strip_leading_fragment(_join(texts)))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_writeups.py -k clean_block -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add extractor/writeups.py tests/test_writeups.py
git commit -m "feat: clean_block prose normalization (dehyphenate/join/trim)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `find_block` — anchor, rank, capture, validate

**Files:**
- Modify: `extractor/writeups.py`
- Test: `tests/test_writeups.py`

**Interfaces:**
- Consumes: `LineRec`, `is_stat_line`, `clean_block`, `heading_keys`, `norm`, `PAGE_WINDOW`.
- Produces: `find_block(name: str, meta_page: int, lines: list[LineRec]) -> str | None` —
  best cleaned prose block for `name`, or `None` when nothing confident is found.

- [ ] **Step 1: Write the failing test**

```python
from extractor.writeups import find_block, LineRec


def _mk(rows):  # rows = (page, col, is_head, text)
    return [LineRec(*r) for r in rows]


def test_find_block_prefers_heading_near_page_and_captures_paragraphs():
    lines = _mk([
        (10, 0, False, "Some unrelated table row 2P 3P"),
        (12, 0, True, "Synaptic Booster"),
        (12, 0, False, "A cybernetic upgrade that speeds reflexes."),
        (12, 0, False, "It grants bonus initiative dice to the user."),
        (12, 0, True, "Next Item"),
        (12, 0, False, "Different unrelated prose."),
    ])
    out = find_block("Synaptic Booster", 12, lines)
    assert out == "A cybernetic upgrade that speeds reflexes. It grants bonus initiative dice to the user."


def test_find_block_rejects_table_only_mention():
    lines = _mk([
        (251, 0, False, "Injection Arrow"),
        (251, 0, False, "Crossbow, Light 2P Crossbow, Standard 3P Crossbow, Heavy 4P"),
    ])
    assert find_block("Injection Arrow", 251, lines) is None


def test_find_block_ignores_far_away_same_name():
    lines = _mk([
        (12, 0, True, "Regular Ammo"),
        (12, 0, False, "Standard rounds for common firearms, nothing special."),
        (263, 0, True, "Regular Ammo"),
        (263, 0, False, "or display text images or patterns for fashion."),
    ])
    out = find_block("Regular Ammo", 12, lines)
    assert out.startswith("Standard rounds")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_writeups.py -k find_block -v`
Expected: FAIL (`find_block` not defined)

- [ ] **Step 3: Write minimal implementation**

```python
# add to extractor/writeups.py
def _anchor_score(line: LineRec, keys: set[str], meta_page: int) -> float | None:
    nt = norm(line.text)
    key = next((k for k in keys if nt == k or nt.startswith(k)), None)
    if key is None:
        return None
    dist = abs(line.page - meta_page)
    if dist > PAGE_WINDOW:
        return None
    score = -dist * 5.0
    if line.is_head:
        score += 100
    if nt == key:                      # whole line is exactly the name
        score += 40
    return score


def _capture(lines: list[LineRec], start: int) -> list[str]:
    anchor = lines[start]
    out = []
    for ln in lines[start + 1:]:
        if ln.col != anchor.col or ln.page - anchor.page > 1:
            break
        if ln.is_head or is_stat_line(ln.text):
            break
        out.append(ln.text)
    return out


def find_block(name: str, meta_page: int, lines: list[LineRec]) -> str | None:
    keys = heading_keys(name)
    best_i, best_s = None, None
    for i, ln in enumerate(lines):
        s = _anchor_score(ln, keys, meta_page)
        if s is None:
            continue
        if best_s is None or s > best_s:
            best_i, best_s = i, s
    if best_i is None:
        return None
    captured = _capture(lines, best_i)
    if not captured:
        return None
    text = clean_block(captured)
    if len(text) < 40 or is_stat_line(text):
        return None
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_writeups.py -k find_block -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add extractor/writeups.py tests/test_writeups.py
git commit -m "feat: find_block anchor/rank/capture for writeup extraction

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `read_book_lines` — font/column-aware PDF → LineRec list

**Files:**
- Modify: `extractor/writeups.py`
- Test: `tests/test_writeups.py`

**Interfaces:**
- Consumes: `LineRec`, and the column/line/heading logic from `extractor.describe`.
- Produces: `read_book_lines(pdf_path) -> list[LineRec]` — every page's lines with
  `is_head` set by font size and `col` by x-position, in reading order.

- [ ] **Step 1: Write the failing test** (structure test with a fake page object)

```python
from extractor.writeups import read_book_lines, LineRec


class _FakeWord(dict):
    pass


class _FakePage:
    width = 600

    def __init__(self, words):
        self._words = words

    def extract_words(self, **kw):
        return self._words


def test_read_book_lines_marks_heading_by_font(monkeypatch):
    import extractor.writeups as W
    words = [
        {"text": "Synaptic", "size": 16.0, "fontname": "Arial", "upright": True, "top": 10, "x0": 50, "x1": 120},
        {"text": "Booster", "size": 16.0, "fontname": "Arial", "upright": True, "top": 10, "x0": 122, "x1": 180},
        {"text": "A", "size": 10.0, "fontname": "Serif", "upright": True, "top": 30, "x0": 50, "x1": 60},
        {"text": "cyber", "size": 10.0, "fontname": "Serif", "upright": True, "top": 30, "x0": 62, "x1": 100},
    ]

    class _PDF:
        pages = [_FakePage(words)]
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(W.pdfplumber, "open", lambda p: _PDF())
    lines = read_book_lines("dummy.pdf")
    assert lines[0].is_head and lines[0].text == "Synaptic Booster"
    assert not lines[1].is_head and lines[1].text == "A cyber"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_writeups.py -k read_book_lines -v`
Expected: FAIL (`read_book_lines` not defined)

- [ ] **Step 3: Write minimal implementation** (reuse describe's column/line grouping)

```python
# add to extractor/writeups.py
import pdfplumber
from collections import Counter
from extractor.describe import _lines, HEAD_RATIO, MIN_COL_GAP


def _page_recs(page, page_no: int) -> list[LineRec]:
    words = [w for w in page.extract_words(extra_attrs=["size", "fontname", "upright"])
             if w.get("upright", True) and w["text"].strip()]
    if not words:
        return []
    banner_x = {x for x, n in Counter(round(w["x0"]) for w in words
                                      if len(w["text"]) == 1).items() if n >= 5}
    words = [w for w in words if not (len(w["text"]) == 1 and round(w["x0"]) in banner_x)]
    if not words:
        return []
    body = Counter(round(w["size"], 1) for w in words).most_common(1)[0][0]
    head_min = body * HEAD_RATIO
    mid = page.width / 2
    left = sum(1 for w in words if (w["x0"] + w["x1"]) / 2 < mid)
    two_col = min(left, len(words) - left) / len(words) >= MIN_COL_GAP
    cols = {0: [], 1: []}
    for w in words:
        c = 1 if (two_col and (w["x0"] + w["x1"]) / 2 >= mid) else 0
        cols[c].append(w)
    recs = []
    for c in (0, 1):
        for ln in _lines(cols[c]):
            real = ln if len(ln) > 1 else [w for w in ln if len(w["text"]) > 1]
            if not real:
                continue
            text = " ".join(w["text"] for w in real)
            is_head = sum(1 for w in real if w["size"] >= head_min) * 2 >= len(real)
            recs.append(LineRec(page_no, c, is_head, text))
    return recs


def read_book_lines(pdf_path) -> list[LineRec]:
    recs = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            recs.extend(_page_recs(page, i))
    return recs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_writeups.py -k read_book_lines -v`
Expected: PASS. Then run the whole file: `python -m pytest tests/test_writeups.py -v` — all green.

- [ ] **Step 5: Commit**

```bash
git add extractor/writeups.py tests/test_writeups.py
git commit -m "feat: read_book_lines font/column-aware PDF reader

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `tools/rebuild_descriptions.py` — driver with fallback, skip-corrected, dry-run/apply, smell-check

**Files:**
- Create: `tools/rebuild_descriptions.py`

**Interfaces:**
- Consumes: `read_book_lines`, `find_block` from `extractor.writeups`;
  `load_registry`, `LIBRARY` from `extractor.ingest`.
- Produces: CLI. Default dry-run; `--apply` writes. Prints per-book counts and a
  final summary: `book / notes / empty / skipped` plus a smell-check (descriptions
  still containing `¥` or a dice code — target 0).

- [ ] **Step 1: Write the driver**

```python
# tools/rebuild_descriptions.py
"""Rebuild every item's system.description from its source book with the
precision-first writeups core. Fallback per item: book writeup -> existing
notes (if real prose) -> empty. Manually-corrected items are never touched.
Dry run by default; --apply writes. Run tools/apply_corrections.py afterwards."""
import sys
import glob
import json
import os
import re
from collections import defaultdict
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))
from extractor.ingest import LIBRARY, load_registry
from extractor.writeups import find_block, read_book_lines, is_stat_line

DATA = _P("data")
APPLY = "--apply" in sys.argv
CORR = {os.path.splitext(os.path.basename(f))[0]
        for f in glob.glob("data/_corrections/*/*.json")}  # all domains; ids unique
_SMELL = re.compile(r"¥|\b\d+[PS]\b|\b\d/\d\b")


def notes_prose(item):
    n = (item.get("system", {}).get("notes") or "").strip()
    return n if len(n) >= 40 and not is_stat_line(n) else None


def main():
    reg = load_registry(DATA)
    files = sorted(glob.glob(f"data/{LIBRARY}/*/*.json"))
    # group items by source book so each PDF is read once
    payloads = {f: json.load(open(f, encoding="utf-8")) for f in files}
    by_book = defaultdict(list)
    for f, p in payloads.items():
        for it in p.get("items", []):
            by_book[it["meta"].get("book")].append((f, it))

    counts = dict(book=0, notes=0, empty=0, skipped=0)
    dirty = set()
    for book, entries in sorted(by_book.items()):
        meta = reg.get(book) or {}
        pdf = meta.get("pdf", "")
        lines = read_book_lines(pdf) if _P(pdf).is_file() else []
        for f, it in entries:
            if it["id"] in CORR:
                counts["skipped"] += 1
                continue
            new = find_block(it["name"], it["meta"].get("page") or 0, lines) if lines else None
            src = "book"
            if not new:
                new = notes_prose(it)
                src = "notes" if new else "empty"
            new = new or ""
            if it["system"].get("description", "") != new:
                dirty.add(f)
            it["system"]["description"] = new
            counts[src] += 1
        print(f"{book:22} processed {len(entries)}", flush=True)

    if APPLY:
        for f in dirty:
            _P(f).write_text(json.dumps(payloads[f], indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")

    # smell-check across the (in-memory) result
    smell = sum(1 for p in payloads.values() for it in p.get("items", [])
                if _SMELL.search(it["system"].get("description", "")))
    print(f"\n{'APPLY' if APPLY else 'DRY RUN'} — "
          f"book={counts['book']} notes={counts['notes']} empty={counts['empty']} "
          f"skipped={counts['skipped']}")
    print(f"smell-check (desc containing ¥/dice): {smell}  (target 0)")
    if not APPLY:
        print("(dry run — re-run with --apply, then tools/apply_corrections.py)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run on real data**

Run: `python tools/rebuild_descriptions.py`
Expected: per-book lines, a summary, and a smell-check number. Note the smell count.

- [ ] **Step 3: Spot-check the failure cases from the spec**

Run:
```bash
python -c "import sys; sys.path.insert(0,'.'); from extractor.writeups import read_book_lines, find_block; from extractor.ingest import load_registry; from pathlib import Path; reg=load_registry(Path('data')); L=read_book_lines(reg['corebook']['pdf']); print(repr(find_block('Regular Ammo (Rifles)',263,L))); print(repr(find_block('Synaptic booster',295,L)))"
```
Expected: the ammo item is `None` or real ammo prose (NOT electrochromic-clothing text); the booster is real prose or `None`. If a known bad case still returns wrong text, tighten `find_block` ranking before applying.

- [ ] **Step 4: Commit the driver (data not yet written)**

```bash
git add tools/rebuild_descriptions.py
git commit -m "feat: rebuild_descriptions driver (book->notes->empty, smell-check)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Apply, re-overlay corrections, verify

**Files:** none (data only — gitignored)

- [ ] **Step 1: Apply the rebuild**

Run: `python tools/rebuild_descriptions.py --apply`
Expected: summary printed; `smell-check ... : 0` (or near-0 — investigate any residue).

- [ ] **Step 2: Re-overlay manual corrections**

Run: `python tools/apply_corrections.py`
Expected: `applied 173 correction(s)` — manual description/icon edits restored on top.

- [ ] **Step 3: Full test + dataset smell-check**

Run: `python -m pytest -q`
Expected: all pass (154 existing + new writeups tests).

Run:
```bash
python -c "import json,glob,re; s=re.compile(r'¥|\b\d+[PS]\b|\b\d/\d\b'); n=sum(1 for f in glob.glob('data/corebook/*/*.json') for it in json.load(open(f,encoding='utf-8')).get('items',[]) if s.search(it.get('system',{}).get('description',''))); print('smell:',n)"
```
Expected: `smell: 0` (target). Any residue → inspect those items, tighten rules, re-run Tasks 5–6.

- [ ] **Step 4: Rebuild frontend so the app serves refreshed data views**

Run: `cd site && npm run build && cd ..`
Expected: build succeeds.

- [ ] **Step 5: Final commit (tooling/tests only)**

```bash
git add -A
git commit -m "chore: description rebuild applied (data regenerated, corrections re-overlaid)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** anchor=text search (Task 3 `_anchor_score` over all lines) ✓;
  font/position ranking (Task 3 heading bonus + page distance) ✓; variable-length
  block (Task 3 `_capture` to boundary, no sentence cap on capture) ✓; stat-row
  rejection (Task 1 + capture break) ✓; cleaning: dehyphenate/join/strip-leading/
  sentence-trim (Task 2) ✓; fallback writeup→notes→empty (Task 5) ✓; skip corrected
  (Task 5 `CORR`) ✓; apply_corrections last (Task 6) ✓; dry-run/apply + smell-check
  (Task 5/6) ✓; column-aware read (Task 4) ✓.
- **Corrected-item scope:** `CORR` currently globs `data/_corrections/gear/*.json`.
  If other domains (critters/npcs/spirits) have corrections, widen the glob to
  `data/_corrections/*/*.json` keyed by id — ids are unique across domains, so a flat
  id set is safe. (Adjust in Task 5 if those domains carry description corrections.)
- **Placeholder scan:** none.
- **Type consistency:** `LineRec(page, col, is_head, text)` used identically in Tasks
  1/3/4; `find_block(name, meta_page, lines)` and `read_book_lines(pdf_path)`
  signatures match between core and driver.
