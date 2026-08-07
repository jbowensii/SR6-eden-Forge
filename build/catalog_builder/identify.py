"""Identify a Shadowrun book by what is INSIDE the PDF, not what it is called.

Matching on the filename was only ever a convention. Rename a book to
``book1.pdf`` and it stopped being recognised, and because a PDF is proof of
ownership that also silently withheld its Commlink6 data. Worse, the weakest
filename rule needed only two distinctive words in common, so an oddly-named
file could bind to the wrong book.

The signals here were chosen by probing all 50 books rather than guessed at:

===========================  ======  ==============================================
signal                       books   notes
===========================  ======  ==============================================
Catalyst code in the text      39    38 of them agree with the registry
``/Title`` PDF metadata        24    clean and canonical when present
neither                         6    fall back to the printed cover title, then
                                     to the filename
===========================  ======  ==============================================

Two findings shaped the scoring, and both would have been missed by assuming:

* **Position matters.** ``body_shop`` carries a DIFFERENT book's code on page
  one — an advert — and its own in the colophon at the back. So a code found at
  the back outweighs one at the front.
* **Frequency matters.** ``30_nights`` shows its own code twice and a stray
  once, which majority alone resolves.

Nothing here trusts one signal blindly: every candidate is scored, the winner
carries a confidence and a human-readable reason, and disagreement between
signals is reported rather than settled quietly.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

#: Front matter and colophon. The code lives at one end or the other, never in
#: the middle, so reading ~13 pages identifies a 300-page book.
FRONT_PAGES = 8
BACK_PAGES = 5

#: "CAT28000", "CAT 28000", "CAT28000S"
CAT_RE = re.compile(r"\bCAT\s*([0-9]{4,6}[A-Z]?)\b", re.I)

#: A code in the colophon is the book's own; one on the cover may be an advert.
BACK_WEIGHT = 3
FRONT_WEIGHT = 1

#: Words too common in Shadowrun titles to identify anything by themselves.
STOPWORDS = {
    "shadowrun", "sixth", "world", "the", "of", "a", "an", "and", "core",
    "rulebook", "sourcebook", "book", "edition", "printing", "current", "6e",
    "sr6", "pdf", "v1", "v2",
}

#: Values seen in the wild that are metadata in name only.
JUNK_TITLES = {"", "about:blank", "untitled", "microsoft word", "document1"}


def norm_words(s: str) -> set[str]:
    """Distinctive words only.

    Single characters are dropped as well as stopwords: "Lofwyr's Legions"
    splits to {lofwyr, s, legions}, and that stray "s" matches essentially any
    page of English, which would have let a title "match" on punctuation.
    """
    return {w for w in re.split(r"[^a-z0-9]+", (s or "").lower())
            if len(w) > 1 and w not in STOPWORDS}


def _norm_cat(code: str) -> str:
    """Comparable form: case-folded, no CAT prefix, no leading zeros."""
    c = (code or "").upper().replace("CAT", "").strip()
    return c.lstrip("0") or c


# --------------------------------------------------------------------------
# reading the file

def read_signals(pdf_path) -> dict:
    """Everything we can learn from the PDF itself.

    :returns: ``{"cat": {code: score}, "title": str, "cover": str,
        "pages": int, "error": str|None}``
    """
    import pdfplumber

    out = {"cat": {}, "title": "", "cover": "", "text": "",
           "pages": 0, "error": None}
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            meta = pdf.metadata or {}
            title = (meta.get("Title") or "").strip()
            if title.lower() not in JUNK_TITLES:
                out["title"] = title

            n = len(pdf.pages)
            out["pages"] = n
            front = set(range(0, min(FRONT_PAGES, n)))
            back = set(range(max(0, n - BACK_PAGES), n))

            cover_bits: list[str] = []
            body_bits: list[str] = []
            for idx in sorted(front | back):
                page = pdf.pages[idx]
                text = page.extract_text() or ""
                weight = BACK_WEIGHT if idx in back and idx not in front else FRONT_WEIGHT
                for m in CAT_RE.finditer(text):
                    code = _norm_cat(m.group(1))
                    out["cat"][code] = out["cat"].get(code, 0) + weight

                # Four of the six books that no code or metadata identified do
                # print their full title in the front matter -- just not as the
                # largest text on the page, which is why looking only at the
                # cover's biggest words missed them.
                if idx in front:
                    body_bits.append(text)

                # the printed title: the biggest text on the opening pages
                if idx in front and idx < 3 and len(cover_bits) < 6:
                    try:
                        words = [w for w in page.extract_words(extra_attrs=["size"])
                                 if w.get("text", "").strip()]
                    except Exception:
                        words = []
                    if words:
                        biggest = max(w["size"] for w in words)
                        cover_bits += [w["text"] for w in words
                                       if w["size"] >= biggest * 0.85]
            out["cover"] = " ".join(cover_bits)[:300]
            out["text"] = " ".join(body_bits)[:20000]
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


# --------------------------------------------------------------------------
# turning signals into a book

def score(signals: dict, registry: dict) -> list[dict]:
    """Rank registry books against one PDF's signals. Best first.

    Each entry is ``{"book", "confidence", "how"}`` with confidence in 0..1.
    """
    by_cat: dict[str, str] = {}
    for book, info in registry.items():
        c = _norm_cat(info.get("cat") or "")
        if c:
            by_cat.setdefault(c, book)

    scores: dict[str, float] = {}
    why: dict[str, list[str]] = {}

    def add(book, points, reason):
        if not book:
            return
        scores[book] = scores.get(book, 0.0) + points
        why.setdefault(book, []).append(reason)

    # 1. the product code, weighted by where it was found
    if signals.get("cat"):
        top = max(signals["cat"].values())
        for code, weight in signals["cat"].items():
            book = by_cat.get(code)
            if not book:
                continue
            # the strongest code is near-certain; a weaker one is a hint
            add(book, 0.90 if weight == top else 0.25,
                f"product code CAT{code} in the book")

    # 2. the PDF's own title metadata
    tw = norm_words(signals.get("title", ""))
    if tw:
        for book, info in registry.items():
            rw = norm_words(info.get("title", ""))
            if rw and rw <= tw:
                add(book, 0.60, "title recorded in the PDF")
                break

    # 3. the title printed on the cover
    cw = norm_words(signals.get("cover", ""))
    if cw:
        for book, info in registry.items():
            rw = norm_words(info.get("title", ""))
            if rw and rw <= cw:
                add(book, 0.35, "title printed on the cover")
                break

    # 4. the full title somewhere in the front matter.
    #
    # Only when EXACTLY ONE registry title matches. A whole page of prose can
    # contain another book's name -- adverts and "also available" lists are
    # common in front matter -- so an ambiguous hit is discarded rather than
    # guessed between.
    if not scores:
        body = norm_words(signals.get("text", ""))
        if body:
            full = [b for b, info in registry.items()
                    if (rw := norm_words(info.get("title", ""))) and rw <= body]
            if len(full) == 1:
                add(full[0], 0.45, "title printed in the front matter")

    ranked = [{"book": b, "confidence": min(1.0, round(v, 2)),
               "how": ", ".join(why[b])}
              for b, v in sorted(scores.items(), key=lambda kv: -kv[1])]
    return ranked


# --------------------------------------------------------------------------
# cache — reading 13 pages of 50 books is slow to repeat for no reason

class SignalCache:
    """Signals keyed by path, size and mtime, so a re-scan is instant.

    Invalidated by the file changing rather than by age: a book that has not
    been touched cannot have become a different book.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict = {}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data = loaded
        except (OSError, ValueError):
            pass

    @staticmethod
    def _stamp(f: Path) -> str:
        st = f.stat()
        return f"{st.st_size}:{int(st.st_mtime)}"

    def get(self, f: Path):
        entry = self.data.get(str(f))
        if entry and entry.get("stamp") == self._stamp(f):
            return entry.get("signals")
        return None

    def put(self, f: Path, signals: dict) -> None:
        self.data[str(f)] = {"stamp": self._stamp(f), "signals": signals}

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass                      # a cache that cannot be written is not fatal


def identify(pdf_path, registry: dict, cache: SignalCache | None = None) -> dict:
    """Identify one PDF. ``{"book", "confidence", "how", "signals", "runnerUp"}``"""
    f = Path(pdf_path)
    signals = cache.get(f) if cache else None
    if signals is None:
        signals = read_signals(f)
        if cache:
            cache.put(f, signals)

    ranked = score(signals, registry)
    best = ranked[0] if ranked else None
    return {
        "file": str(f),
        "book": best["book"] if best else None,
        "confidence": best["confidence"] if best else 0.0,
        "how": best["how"] if best else "nothing inside the file identified it",
        "runnerUp": ranked[1] if len(ranked) > 1 else None,
        "signals": signals,
    }


def default_cache_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or Path.home()
    return Path(base) / "SR6CatalogBuilder" / "pdf-signals.json"


# --------------------------------------------------------------------------
# naming files the way we name books

#: What a recognised book is called once renamed. Mirrors the retail pattern
#: the publisher uses, so a renamed library still matches on the filename alone
#: if it is ever read by something that only looks at names.
NAME_TEMPLATE = "Shadowrun 6e-{title}-CAT{cat}.pdf"
NAME_NO_CAT = "Shadowrun 6e-{title}.pdf"

#: Characters Windows will not accept in a filename.
#: Characters Windows will not accept in a filename, control codes included.
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def canonical_name(book: str, registry: dict) -> str | None:
    """What ``book``'s file should be called, or None if we cannot say."""
    info = registry.get(book) or {}
    title = (info.get("title") or "").strip()
    if not title:
        return None
    title = _ILLEGAL.sub("", title).rstrip(". ")
    cat = _norm_cat(info.get("cat") or "")
    name = (NAME_TEMPLATE.format(title=title, cat=cat) if cat
            else NAME_NO_CAT.format(title=title))
    return name


def plan_renames(matched: list[dict], registry: dict) -> list[dict]:
    """Which recognised files are not named our way, and what to call them.

    :param matched: ``[{"book", "file"}, ...]`` as produced by a scan.
    :returns: ``[{"book", "from", "to", "path", "collision"}]`` -- only files
        that would actually change, with any name clash flagged rather than
        resolved. Renaming one book over another would be the worst possible
        outcome of a convenience feature.
    """
    plan = []
    wanted: dict[str, str] = {}
    for m in matched:
        src = Path(m["file"])
        want = canonical_name(m["book"], registry)
        if not want or src.name == want:
            continue
        target = src.with_name(want)
        clash = ""
        if target.exists():
            clash = "a different file already has that name"
        elif want in wanted:
            clash = f"the same name is wanted by {wanted[want]}"
        wanted[want] = m["book"]
        plan.append({"book": m["book"], "from": src.name, "to": want,
                     "path": str(src), "collision": clash})
    return plan


def apply_renames(plan: list[dict]) -> dict:
    """Carry out a rename plan, skipping anything flagged as a collision.

    :returns: ``{"renamed": [...], "skipped": [...]}``
    """
    renamed, skipped = [], []
    for item in plan:
        if item.get("collision"):
            skipped.append({**item, "why": item["collision"]})
            continue
        src = Path(item["path"])
        dst = src.with_name(item["to"])
        try:
            src.rename(dst)
            renamed.append({**item, "path": str(dst)})
        except OSError as e:
            skipped.append({**item, "why": f"{type(e).__name__}: {e}"})
    return {"renamed": renamed, "skipped": skipped}
