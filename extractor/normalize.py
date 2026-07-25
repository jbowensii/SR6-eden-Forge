from __future__ import annotations

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


def normalize_text(s: str) -> str:
    return s.translate(_TRANS)
