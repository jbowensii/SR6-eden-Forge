"""Repair mangled gear names from books whose compact stat tables encode words
without reliable spaces ("ProstheticCy berlimb,Cr ude" -> "Prosthetic Cyberlimb,
Crude"). The stat *numbers* in these rows are correct; only the name text runs
together, so the names are re-spaced by Viterbi word segmentation over a
unigram model. The vocabulary is built from clean text — the library's own item
names/descriptions plus the source book's prose (which extracts normally) — so
every domain term (Adapsin, Cyberlimb, Deltaware) is known. No book content is
stored in this module; the vocabulary is built at runtime from local data."""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"[a-z]+")
# separators kept as boundaries so "limb,Crude" splits cleanly around the comma
_SPLIT = re.compile(r"([,/()\[\]]|\s*[-–]\s*)")


def build_vocab(*texts: str) -> Counter:
    vocab: Counter = Counter()
    for text in texts:
        vocab.update(_WORD.findall(text.lower()))
    return vocab


def make_segmenter(vocab: Counter):
    total = sum(vocab.values()) or 1
    log_total = math.log(total)
    maxlen = max((len(w) for w in vocab), default=18)

    def wordcost(w: str) -> float:
        c = vocab.get(w)
        if c:
            return log_total - math.log(c)
        # unknown run: cheap enough to accept a real out-of-vocab token but
        # costly per char so the search still prefers known words; a lone
        # unknown letter (not 'a'/'i') is very expensive to avoid junk splits.
        if len(w) == 1:
            return 4.0 if w in "ai" else 30.0
        return 11.0 + 2.2 * len(w)

    def segment(s: str) -> list[str]:
        s = s.lower()
        n = len(s)
        if n == 0:
            return []
        cost = [0.0] + [1e18] * n
        back = [0] * (n + 1)
        for i in range(1, n + 1):
            lo = max(0, i - maxlen)
            best_c, best_j = 1e18, i - 1
            for j in range(lo, i):
                c = cost[j] + wordcost(s[j:i])
                if c < best_c:
                    best_c, best_j = c, j
            cost[i], back[i] = best_c, best_j
        words, i = [], n
        while i > 0:
            j = back[i]
            words.append((j, i))
            i = j
        return words[::-1]

    return segment


_PARTICLE = {"of", "the", "and", "or", "a", "per", "with", "for", "to", "in"}


def _case_word(w: str) -> str:
    if w.isupper() and len(w) > 1:
        return w  # keep acronyms like BTL / DNI / RFID
    if w.lower() in _PARTICLE:
        return w.lower()
    return w[:1].upper() + w[1:].lower()


def _respace_chunk(chunk: str, segment) -> str:
    """Re-space one all-letters run; mangling drops capitals, so Title-case the
    recovered words (item-name convention) while keeping all-caps acronyms."""
    spans = segment(chunk)
    words = [_case_word(chunk[a:b]) for a, b in spans]
    if words:
        words[0] = words[0][:1].upper() + words[0][1:]  # never start lowercase
    return " ".join(words)


def demangle_name(raw: str, segment) -> str:
    """Re-space a mangled name, preserving punctuation and original letter case."""
    out_parts = []
    for piece in _SPLIT.split(raw):
        if piece is None:
            continue
        stripped = piece.strip()
        if not stripped:
            continue
        if _SPLIT.fullmatch(piece) or not re.search(r"[A-Za-z]", piece):
            out_parts.append(("sep", stripped))
            continue
        # a text piece may still hold stray spaces from the bad kerning; drop
        # them, re-segment the letter run, keep any trailing digits/marks
        m = re.match(r"([A-Za-z][A-Za-z ]*)(.*)$", piece.strip())
        if not m:
            out_parts.append(("word", piece.strip()))
            continue
        letters = m.group(1).replace(" ", "")
        tail = m.group(2).strip()
        respaced = _respace_chunk(letters, segment)
        out_parts.append(("word", respaced + (f" {tail}" if tail else "")))

    # join: no space before ,)] and no space after ([ ; single space otherwise
    text = ""
    glue = True  # no leading space for the next token
    for kind, val in out_parts:
        if kind == "sep" and val in ",)]":
            text += val
            glue = False
        elif kind == "sep" and val in "([":
            text += ("" if glue else " ") + val
            glue = True
        else:
            text += ("" if glue else " ") + val
            glue = False
    return re.sub(r"\s+", " ", text).strip()
