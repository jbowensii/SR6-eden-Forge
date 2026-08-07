"""Work out which books are in a folder of PDFs.

The user points at a directory; this says what it found. Getting that right is
what makes the first screen feel like the program understands their shelf
rather than demanding they file things a particular way.

Three ways to recognise a book, strongest first:

**Catalyst product code.** Retail PDFs carry it in the filename —
``Shadowrun 6e-Sixth World Core Rulebook-Current Printing-CAT28000.pdf`` — and
the registry stores the same code per book. An exact match on it is certain,
regardless of how the file has been renamed around it.

**Title.** Normalised and compared, so "Sixth World Companion" still matches
``SR6 - Sixth World Companion (2020).pdf``.

**Distinctive words.** A last resort for a heavily renamed file, requiring
enough uncommon words to overlap that a false positive is unlikely.

Anything unmatched is reported rather than ignored: an unrecognised book is
something the user can act on, and silently dropping it looks like a bug.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

CAT_RE = re.compile(r"\bCAT(\d{4,6})\b", re.I)

#: Words too common in Shadowrun titles to identify anything on their own.
_STOPWORDS = {
    "shadowrun", "sixth", "world", "the", "of", "a", "an", "and", "core",
    "rulebook", "sourcebook", "book", "edition", "printing", "current", "6e",
    "sr6", "pdf", "v1", "v2",
}


def _norm(s: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", (s or "").lower())
            if w and w not in _STOPWORDS]


def load_registry(repo: Path) -> dict:
    """The book registry: what titles exist and their Catalyst product codes.

    Shipped WITH the application, not just with the repo. Without it there is
    nothing to match a PDF against, so every folder reads as "no Shadowrun
    books found" — which is exactly how the first installed build behaved, and
    it blames the user's folder for a missing data file.

    Bibliographic metadata only: titles, product codes and dates. No game
    content, and no PDF paths — those are per-machine and the scan fills them.
    """
    here = Path(__file__).resolve().parent
    candidates = [
        repo / "data" / "books.json",     # running from the repo
        repo / "books.json",              # beside the exe
        here / "books.json",              # bundled in the package
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(0, Path(sys.executable).parent / "books.json")
        candidates.insert(1, Path(getattr(sys, "_MEIPASS", "")) / "books.json")
    for candidate in candidates:
        try:
            if candidate.is_file():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def scan(pdf_dir: Path, registry: dict, identify_fn=None) -> dict:
    """Match every PDF in ``pdf_dir`` against the registry.

    :param identify_fn: optional ``path -> {"book", "confidence", "how"}``,
        normally :func:`catalog_builder.identify.identify`. When supplied, what
        is INSIDE the file decides and the filename is only consulted if the
        contents said nothing. A filename is a convention; the Catalyst product
        code printed in the book is a fact.
    :returns: ``{matched: [...], unmatched: [...], missing: [...]}`` where
        *matched* pairs a book id with the file, *unmatched* lists PDFs that
        look like nothing we know, and *missing* names registry books with no
        file present.
    """
    pdf_dir = Path(pdf_dir)
    if not pdf_dir.is_dir():
        return {"matched": [], "unmatched": [], "missing": sorted(registry)}

    by_cat = {}
    for book, info in registry.items():
        cat = (info.get("cat") or "").upper().replace("CAT", "").strip()
        if cat:
            by_cat.setdefault(cat, book)

    files = sorted(p for p in pdf_dir.rglob("*.pdf") if p.is_file())
    matched: list[dict] = []
    unmatched: list[dict] = []
    taken: set[str] = set()

    for f in files:
        stem = f.stem
        book = None
        how = ""

        if identify_fn is not None:
            try:
                found = identify_fn(f) or {}
            except Exception as e:                # a bad file is not fatal
                found = {"book": None, "how": f"could not be read ({type(e).__name__})"}
            if found.get("book"):
                book = found["book"]
                how = found.get("how") or "identified from the file contents"

        if book is None:
            m = CAT_RE.search(stem)
            if m and m.group(1).lstrip("0") in {c.lstrip("0") for c in by_cat}:
                for cat, b in by_cat.items():
                    if cat.lstrip("0") == m.group(1).lstrip("0"):
                        book, how = b, f"product code CAT{m.group(1)} in the filename"
                        break

        if book is None:
            words = set(_norm(stem))
            best, score = None, 0
            for b, info in registry.items():
                title = set(_norm(info.get("title", "")))
                if not title:
                    continue
                overlap = len(words & title)
                # every distinctive word of the title present = a title match
                if overlap and overlap == len(title):
                    best, score = b, 999
                    break
                if overlap >= 2 and overlap > score:
                    best, score = b, overlap
            if best:
                book = best
                how = ("title in the filename" if score == 999
                       else f"{score} distinctive words in the filename")

        if book and book not in taken:
            taken.add(book)
            matched.append({"book": book, "file": str(f),
                            "title": registry[book].get("title", book), "how": how})
        elif book:
            unmatched.append({"file": str(f),
                              "reason": f"duplicate of {book} (already matched)"})
        else:
            unmatched.append({"file": str(f), "reason": "not recognised"})

    missing = sorted(b for b in registry if b not in taken)
    return {"matched": matched, "unmatched": unmatched, "missing": missing}


def apply_to_registry(repo: Path, result: dict, out: Path | None = None) -> Path:
    """Write the matched PDF paths into the registry the pipeline reads.

    The pipeline gates on ``books.json[book].pdf`` existing, so this is what
    turns "I found your books" into "the import will actually read them".
    """
    reg = load_registry(repo)
    for m in result["matched"]:
        reg.setdefault(m["book"], {})["pdf"] = m["file"]
    target = out or (repo / "data" / "books.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(reg, indent=1, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return target


def summary(result: dict) -> str:
    """One human sentence about what the folder contains."""
    n = len(result["matched"])
    if not n:
        return "No Shadowrun books recognised in that folder."
    names = [m["title"] for m in result["matched"]]
    head = ", ".join(names[:3])
    more = f" and {n - 3} more" if n > 3 else ""
    tail = ""
    if result["unmatched"]:
        tail = f"  ({len(result['unmatched'])} file(s) not recognised)"
    return f"Found {n} book{'s' if n != 1 else ''}: {head}{more}.{tail}"
