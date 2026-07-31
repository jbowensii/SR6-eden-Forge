"""Precision-first item-writeup extraction. Pure core over a flat LineRec list
so it is unit-testable without a PDF. Anchors on text search, ranks candidates
with font/position, captures a variable-length prose block, cleans it. No book
content is stored here."""
from __future__ import annotations

import re
from collections import Counter, namedtuple

import pdfplumber

from extractor.describe import _lines, HEAD_RATIO, MIN_COL_GAP
from extractor.enrich import heading_keys, norm

MAX_DESC = 3500
PAGE_WINDOW = 3

LineRec = namedtuple("LineRec", "page col is_head text")

_DICE = re.compile(r"\b\d+[PS]\b|\b\d/\d\b|\b\d{1,2}[PS]\s+\d")
_CAPS_HEADER = re.compile(r"^[A-Z][A-Z /()&'’]{11,}$")
_BARE_NUM = re.compile(r"^\d{1,3}$")
_NUMERIC_ROW = re.compile(r"^[\d/.,\s]+$")
_SENT_END = re.compile(r"[.!?][\"'”’)]?\s")


# --------------------------------------------------------------------------- #
# boundary / stat-row detection
# --------------------------------------------------------------------------- #
def is_stat_line(text: str) -> bool:
    """True when a line is a stat/table row, ALL-CAPS column header, price row,
    or bare page number — never prose."""
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


# --------------------------------------------------------------------------- #
# prose cleaning
# --------------------------------------------------------------------------- #
def _join(texts: list[str]) -> str:
    out = ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if out.endswith("-"):
            out = out[:-1] + t            # dehyphenate a line-break hyphen
        elif out:
            out += " " + t
        else:
            out = t
    return re.sub(r"\s+", " ", out).strip()


def _strip_leading_fragment(text: str) -> str:
    # drop a leading lowercase run (tail of a heading line) up to the first
    # capitalized word that begins a sentence
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
    if text and text[-1] not in ".!?\"'”’)":
        ends = [m.end() for m in _SENT_END.finditer(text + " ")]
        if ends:
            text = text[:ends[-1]].strip()
    return text.strip()


def clean_block(texts: list[str]) -> str:
    """Join captured lines into clean prose: dehyphenate line breaks, single-space
    join, drop a stray leading lowercase fragment, trim a trailing partial
    sentence, cap at MAX_DESC on a sentence boundary."""
    return _sentence_trim(_strip_leading_fragment(_join(texts)))


# --------------------------------------------------------------------------- #
# anchor -> rank -> capture -> validate
# --------------------------------------------------------------------------- #
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
    out: list[str] = []
    for ln in lines[start + 1:]:
        if ln.col != anchor.col or ln.page - anchor.page > 1:
            break
        if ln.is_head or is_stat_line(ln.text):
            break
        out.append(ln.text)
    return out


def find_block(name: str, meta_page: int, lines: list[LineRec]) -> str | None:
    """Best cleaned prose block for `name` in `lines`, or None when nothing
    confident is found (precision over recall)."""
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


# --------------------------------------------------------------------------- #
# PDF -> LineRec list (font/column aware)
# --------------------------------------------------------------------------- #
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
    recs: list[LineRec] = []
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
    """Every page's lines as LineRec, is_head by font size, col by x-position."""
    recs: list[LineRec] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            recs.extend(_page_recs(page, i))
    return recs
