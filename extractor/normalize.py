from __future__ import annotations

import re

_TABLE = {
    chr(0x2019): chr(0x0027),  # right single quote to apostrophe
    chr(0x2014): chr(0x2014),  # em dash
    chr(0x2013): chr(0x2014),  # en dash to em dash
    chr(0x2212): chr(0x2014),  # minus to em dash
    chr(0x00A0): chr(0x0020),  # nbsp to space
    chr(0x202F): chr(0x0020),  # narrow nbsp to space
    chr(0xFB01): "fi",  # fi ligature
    chr(0xFB02): "fl",  # fl ligature
    chr(0x00AD): "",  # soft hyphen
}
_TRANS = str.maketrans(_TABLE)
_WS = re.compile(r"(\s+)")


def _dd_token(t: str) -> str:
    return t[::2] + (t[-1] if len(t) % 2 else "")


def dedouble(s: str) -> str:
    """Undo per-glyph character doubling ('TThhiiss' -> 'This'). Some PDFs carry a
    ToUnicode cmap that emits every glyph twice, so the page LOOKS fine but the
    text layer is doubled. Self-guarding: only fires when the whole string is
    dominantly doubled (>=6 non-space chars, >=75% of adjacent pairs equal), so
    it is safe to call on any text — normal prose passes through untouched."""
    letters = [c for c in s if not c.isspace()]
    pairs = len(letters) // 2
    if pairs < 3:
        return s
    matched = sum(1 for i in range(0, pairs * 2, 2) if letters[i] == letters[i + 1])
    if matched / pairs < 0.75:
        return s
    return "".join(t if t.isspace() else _dd_token(t) for t in _WS.split(s))


def normalize_text(s: str) -> str:
    return dedouble(s.translate(_TRANS))
