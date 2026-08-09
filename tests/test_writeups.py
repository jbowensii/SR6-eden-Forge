import pytest

from extractor.writeups import (
    LineRec,
    clean_block,
    find_block,
    is_stat_line,
    read_book_lines,
)


def _mk(rows):  # rows = (page, col, is_head, text)
    return [LineRec(*r) for r in rows]


# --- is_stat_line ---------------------------------------------------------- #
def test_is_stat_line_flags_stats_and_headers():
    assert is_stat_line("Crossbow, Light 2P Crossbow, Standard 3P")
    assert is_stat_line("HAND ACC SPD INT TOP SPD BODY ARM AVAIL COST")
    assert is_stat_line("11,500¥")
    assert is_stat_line("2/5 35 40 250 3 3 2 1 1 2")
    assert is_stat_line("263")
    assert not is_stat_line("An implanted version of the flare compensation system.")
    assert not is_stat_line("A nice haircut and the right makeup can change everything.")


# --- clean_block ----------------------------------------------------------- #
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


# --- find_block ------------------------------------------------------------ #
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


# --- read_book_lines ------------------------------------------------------- #
class _FakePage:
    width = 600

    def __init__(self, words):
        self._words = words

    def extract_words(self, **kw):
        return self._words


def test_read_book_lines_marks_heading_by_font(monkeypatch):
    import extractor.writeups as W
    # prose must dominate for body-font inference (as on a real page)
    words = [
        {"text": "Synaptic", "size": 16.0, "fontname": "Arial", "upright": True, "top": 10, "x0": 50, "x1": 120},
        {"text": "Booster", "size": 16.0, "fontname": "Arial", "upright": True, "top": 10, "x0": 122, "x1": 180},
        {"text": "A", "size": 10.0, "fontname": "Serif", "upright": True, "top": 30, "x0": 50, "x1": 60},
        {"text": "cyber", "size": 10.0, "fontname": "Serif", "upright": True, "top": 30, "x0": 62, "x1": 100},
        {"text": "upgrade", "size": 10.0, "fontname": "Serif", "upright": True, "top": 44, "x0": 50, "x1": 110},
        {"text": "that", "size": 10.0, "fontname": "Serif", "upright": True, "top": 44, "x0": 112, "x1": 140},
        {"text": "speeds", "size": 10.0, "fontname": "Serif", "upright": True, "top": 58, "x0": 50, "x1": 100},
        {"text": "reflexes", "size": 10.0, "fontname": "Serif", "upright": True, "top": 58, "x0": 102, "x1": 150},
    ]

    class _PDF:
        pages = [_FakePage(words)]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(W.pdfplumber, "open", lambda p: _PDF())
    lines = read_book_lines("dummy.pdf")
    assert lines[0].is_head and lines[0].text == "Synaptic Booster"
    assert not lines[1].is_head and lines[1].text == "A cyber"


# ---------- is a description a sentence, or a table row? ----------

def _rd():
    """Load rebuild_descriptions without running it (work is behind __main__)."""
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location(
        "rd", Path(__file__).resolve().parent.parent / "tools" / "rebuild_descriptions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PROSE = [
    "This costs 200\u00a5 and requires an Engineering test to install correctly.",
    "Troll sized combined fragmentation and flash-bang grenade "
    "(does additional 10S, 8S, 6S in 15m)",
    "A rating 1 PA scores zero hits, rating 2-3 scores 1 hit on any Matrix test.",
]

STAT_ROWS = [
    "3/5 18 30 180 14 8 3 3 4 3 65,000\u00a5",
    "4 10 30 260 22 10 2 3 2/16 2",
    "Rotor 15 25 350 70 Gravtech 20 200 1,000 1,000",
]


@pytest.mark.parametrize("desc", PROSE)
def test_prose_that_quotes_a_price_is_not_a_leak(desc):
    """The old check flagged any nuyen sign and declared a target of zero.

    That target was unreachable, because quoting a price in a sentence is not
    a defect. Every description it flagged at the end of the 0.9.4 import was
    correct English, so the number measured nothing and a real leak would have
    been invisible among the false alarms.
    """
    assert not _rd().desc_is_table_row(desc)


@pytest.mark.parametrize("desc", STAT_ROWS)
def test_a_table_row_in_a_description_is_caught(desc):
    """What actually goes wrong: short, and mostly numbers."""
    assert _rd().desc_is_table_row(desc)


def test_an_empty_description_is_not_a_leak():
    assert not _rd().desc_is_table_row("")
