"""Font-aware writeup extraction.

The column-text cache scrambles two-column pages with a vertical sidebar banner
(the SR6 supplements), so heading lines get split across columns and the
cache-based enricher misses them. This module reads each page straight from the
PDF instead: item writeups are set in a larger sans-serif heading font over a
serif body, so headings are found by font size, columns by x-position, and the
body between one heading and the next (in the same column) becomes the writeup —
exactly the "text between the item heading and the next heading" pattern.

Output is the (page, line) stream the existing enrich.parse_sections/HeadingIndex
consume, so all name-matching/dehyphenation logic is reused. No book content
lives here."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from extractor.enrich import HEAD_SENTINEL, build_index, parse_sections

LINE_TOL = 3.0          # group words into a visual line within this many points
HEAD_RATIO = 1.25       # a line this much larger than the body font is a heading
MIN_COL_GAP = 0.15      # ignore a 2nd column unless it holds a real share of text


def _lines(words):
    """Cluster words into visual lines by top; each line sorted left to right."""
    ws = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
    out, cur, base = [], [], None
    for w in ws:
        if cur and w["top"] - base > LINE_TOL:
            out.append(sorted(cur, key=lambda x: x["x0"]))
            cur, base = [], None
        if base is None:
            base = w["top"]
        cur.append(w)
    if cur:
        out.append(sorted(cur, key=lambda x: x["x0"]))
    return out


def page_lines(page, page_no: int) -> list[tuple[int, str]]:
    words = [w for w in page.extract_words(extra_attrs=["size", "fontname", "upright"])
             if w.get("upright", True) and w["text"].strip()]
    if not words:
        return []
    # a vertical sidebar banner ("SHADOWRUN BODY SHOP") is a stack of single
    # glyphs at a near-constant x; drop those columns so they don't append to
    # prose lines ("...it didn't take D") or split them. Real 1-char words
    # (a/I/A) are scattered, never stacked, so they survive.
    banner_x = {x for x, n in Counter(round(w["x0"]) for w in words
                                      if len(w["text"]) == 1).items() if n >= 5}
    words = [w for w in words if not (len(w["text"]) == 1 and round(w["x0"]) in banner_x)]
    if not words:
        return []

    body = Counter(round(w["size"], 1) for w in words).most_common(1)[0][0]
    head_min = body * HEAD_RATIO
    mid = page.width / 2

    # a page is two-column only if both halves carry a real share of the words.
    # Words MUST be split into columns before lines are grouped, or left- and
    # right-column text sharing a vertical position merges into one line
    # ("...Each exter- Tesla Coil").
    left = sum(1 for w in words if (w["x0"] + w["x1"]) / 2 < mid)
    two_col = min(left, len(words) - left) / len(words) >= MIN_COL_GAP
    columns = {0: [], 1: []}
    for w in words:
        col = 1 if (two_col and (w["x0"] + w["x1"]) / 2 >= mid) else 0
        columns[col].append(w)

    out: list[tuple[int, str]] = []
    for col in (0, 1):
        if not columns[col]:
            continue
        for ln in _lines(columns[col]):
            real = ln if len(ln) > 1 else [w for w in ln if len(w["text"]) > 1]
            if not real:
                continue  # a lone single glyph is stray banner/decoration
            text = " ".join(w["text"] for w in real)
            is_head = sum(1 for w in real if w["size"] >= head_min) * 2 >= len(real)
            if is_head:
                out.append((page_no, HEAD_SENTINEL))  # force a section break
            out.append((page_no, text))
    return out


def extract_book_descriptions(pdf_path, index, pages) -> dict:
    import pdfplumber

    lines: list[tuple[int, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for pno in pages:
            lines.extend(page_lines(pdf.pages[pno - 1], pno))
    return parse_sections(lines, index)


def enrich_from_pdf(data_root: Path, book: str, pdf_path, domain: str, pages, force: bool = False) -> dict:
    import json

    domain_dir = data_root / book / domain
    payloads = {p.stem: json.loads(p.read_text(encoding="utf-8"))
                for p in sorted(domain_dir.glob("*.json"))}
    index = build_index(payloads)
    sections = extract_book_descriptions(pdf_path, index, pages)

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
            (domain_dir / f"{category}.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    total = sum(len(p.get("items", [])) for p in payloads.values())
    return {"matched": len(sections), "updated": updated, "items": total}
