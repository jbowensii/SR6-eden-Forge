"""Parse a book's table of contents (the 'Section .... printed-page' lists on
the opening pages) into a section->printed-page map, then resolve printed pages
to PDF page indices. Printed page numbers drift from PDF indices by a cover/
front-matter offset, so the offset is estimated by matching a printed page
number found in a page's footer/header text to its PDF index; readers then
search a ±window around the resolved page. This augments signature scanning by
telling us WHERE each kind of content should be, even in books whose stat lines
don't match a signature."""

from __future__ import annotations

import re

import pdfplumber

# "Some Section .......... 214"  (dotted or spaced leaders, page number at end)
_ENTRY = re.compile(r"([A-Za-z][A-Za-z0-9''/&,:\-\(\) ]{2,60}?)\s*[\. ]{2,}\s*(\d{1,4})\b")


def parse_toc(pdf_path, toc_pages=range(1, 8)):
    """Return {normalized_title: printed_page} from the TOC pages. Multi-column
    TOCs interleave, but each 'title ... number' pair is matched independently so
    column order doesn't matter."""
    out = {}
    with pdfplumber.open(str(pdf_path)) as pdf:
        n = len(pdf.pages)
        for pno in toc_pages:
            if pno > n:
                break
            text = pdf.pages[pno - 1].extract_text() or ""
            for m in _ENTRY.finditer(text):
                title = re.sub(r"\s+", " ", m.group(1)).strip(" .")
                page = int(m.group(2))
                if title and 1 <= page <= 2000 and title.lower() not in out:
                    out[title.lower()] = page
    return out


def estimate_offset(pdf_path, probe_pages=range(8, 40)):
    """PDF_index - printed_page. Found by reading each page's own printed folio
    (a bare 1-3 digit number sitting alone on a line, usually the page corner)
    and taking the most common (pdf_index - folio)."""
    from collections import Counter
    votes = Counter()
    with pdfplumber.open(str(pdf_path)) as pdf:
        n = len(pdf.pages)
        for pno in probe_pages:
            if pno > n:
                break
            text = pdf.pages[pno - 1].extract_text() or ""
            for line in text.splitlines():
                s = line.strip()
                if re.fullmatch(r"\d{1,3}", s):
                    votes[pno - int(s)] += 1
    return votes.most_common(1)[0][0] if votes else 0


def find_pages(pdf_path, keywords, toc=None, offset=None, window=10):
    """For each keyword (or synonym list), locate its TOC entry, resolve to a PDF
    page, and return a ±window page range to scan. keywords: {name: [synonyms]}.
    Returns {name: (center_pdf_page, [pages])} for matches found in the TOC."""
    toc = toc if toc is not None else parse_toc(pdf_path)
    offset = offset if offset is not None else estimate_offset(pdf_path)
    with pdfplumber.open(str(pdf_path)) as pdf:
        n = len(pdf.pages)
    hits = {}
    for name, syns in keywords.items():
        printed = None
        for syn in [name, *syns]:
            s = syn.lower()
            if s in toc:
                printed = toc[s]
                break
            for title, pg in toc.items():          # substring fallback
                if s in title:
                    printed = pg
                    break
            if printed is not None:
                break
        if printed is None:
            continue
        center = max(1, min(n, printed + offset))
        lo, hi = max(1, center - window), min(n, center + window)
        hits[name] = (center, list(range(lo, hi + 1)))
    return hits
