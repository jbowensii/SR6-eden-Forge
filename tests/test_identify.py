"""Identifying a book by what is inside it.

Filename matching was only ever a convention: rename a book to book1.pdf and
it stopped being recognised, and because a PDF is proof of ownership that also
withheld its Commlink6 data. The thresholds and weights here were set from
probing all 50 real books, and the two awkward cases below are real ones.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "build"))

from catalog_builder import books                                # noqa: E402
from catalog_builder.identify import (                           # noqa: E402
    apply_renames, canonical_name, norm_words, plan_renames, score)

REG = {
    "corebook": {"title": "Sixth World Core Rulebook", "cat": "CAT28000"},
    "body_shop": {"title": "Body Shop", "cat": "CAT28007"},
    "astral_ways": {"title": "Astral Ways", "cat": "CAT28101"},
    "gun_rack": {"title": "Gun Rack", "cat": "CAT28504"},
}


def test_the_product_code_identifies_the_book():
    got = score({"cat": {"28000": 3}, "title": "", "cover": "", "text": ""}, REG)
    assert got[0]["book"] == "corebook"
    assert got[0]["confidence"] >= 0.9


def test_an_advert_on_page_one_does_not_beat_the_colophon():
    """Real case: body_shop prints astral_ways' code on its first page.

    Its own code appears in the colophon at the back, which is why a code found
    at the back outweighs one at the front rather than being counted equally.
    """
    signals = {"cat": {"28101": 1, "28007": 3},   # front=1, back=3
               "title": "", "cover": "", "text": ""}
    got = score(signals, REG)
    assert got[0]["book"] == "body_shop"
    assert got[1]["book"] == "astral_ways"       # noted, not discarded
    assert got[0]["confidence"] > got[1]["confidence"]


def test_the_pdf_title_identifies_a_book_with_no_code():
    """Real case: gun_rack carries no product code but clean metadata."""
    got = score({"cat": {}, "title": "Shadowrun: Gun Rack (Weapon Cards)",
                 "cover": "", "text": ""}, REG)
    assert got[0]["book"] == "gun_rack"


def test_junk_metadata_is_ignored():
    """corebook_seattle's /Title really is "about:blank"."""
    got = score({"cat": {}, "title": "", "cover": "", "text": ""}, REG)
    assert got == []


def test_an_ambiguous_front_matter_title_is_refused():
    """Front matter advertises other books, so two matches means no answer."""
    text = "Body Shop and also Gun Rack are available now"
    got = score({"cat": {}, "title": "", "cover": "", "text": text}, REG)
    assert got == [], "two possible titles must not be guessed between"


def test_a_single_front_matter_title_is_accepted():
    got = score({"cat": {}, "title": "", "cover": "",
                 "text": "presenting Body Shop, a sourcebook"}, REG)
    assert got[0]["book"] == "body_shop"


def test_single_characters_never_count_as_a_title_word():
    """"Lofwyr's Legions" splits to {lofwyr, s, legions}; that "s" matches
    any page of English at all."""
    assert "s" not in norm_words("Lofwyr's Legions")
    assert norm_words("Lofwyr's Legions") == {"lofwyr", "legions"}


# ---------- the scan prefers contents over the filename ----------

def _pdf(d: Path, name: str) -> Path:
    p = d / name
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return p


def test_a_meaninglessly_named_file_is_still_identified(tmp_path):
    """The whole point: the filename carries nothing."""
    f = _pdf(tmp_path, "book1.pdf")
    r = books.scan(tmp_path, REG,
                   identify_fn=lambda p: {"book": "corebook", "confidence": 0.9,
                                          "how": "product code CAT28000 in the book"})
    assert [m["book"] for m in r["matched"]] == ["corebook"]
    assert "in the book" in r["matched"][0]["how"]
    assert r["matched"][0]["file"] == str(f)


def test_contents_win_over_a_misleading_filename(tmp_path):
    _pdf(tmp_path, "Sixth World Core Rulebook-CAT28000.pdf")
    r = books.scan(tmp_path, REG,
                   identify_fn=lambda p: {"book": "body_shop", "confidence": 0.9,
                                          "how": "product code CAT28007 in the book"})
    assert [m["book"] for m in r["matched"]] == ["body_shop"]


def test_the_filename_still_rescues_a_file_the_contents_cannot_identify(tmp_path):
    """4 of 50 books are scanned images or render their title as art."""
    _pdf(tmp_path, "Sixth World Core Rulebook-CAT28000.pdf")
    r = books.scan(tmp_path, REG, identify_fn=lambda p: {"book": None})
    assert [m["book"] for m in r["matched"]] == ["corebook"]
    assert "filename" in r["matched"][0]["how"]


def test_an_unreadable_file_does_not_stop_the_scan(tmp_path):
    _pdf(tmp_path, "Sixth World Core Rulebook-CAT28000.pdf")

    def boom(_p):
        raise OSError("damaged")

    r = books.scan(tmp_path, REG, identify_fn=boom)
    assert [m["book"] for m in r["matched"]] == ["corebook"]   # fell back


# ---------- renaming to our convention ----------

def test_canonical_name_matches_the_retail_pattern():
    assert canonical_name("corebook", REG) == \
        "Shadowrun 6e-Sixth World Core Rulebook-CAT28000.pdf"


def test_a_book_with_no_product_code_still_gets_a_name():
    reg = {"krime": {"title": "Krime Katalog", "cat": ""}}
    assert canonical_name("krime", reg) == "Shadowrun 6e-Krime Katalog.pdf"


def test_illegal_filename_characters_are_stripped():
    reg = {"x": {"title": 'A: Book/Name?', "cat": ""}}
    name = canonical_name("x", reg)
    assert not set(name) & set(r'<>:"/\|?*')


def test_a_file_already_named_correctly_is_not_in_the_plan(tmp_path):
    f = _pdf(tmp_path, "Shadowrun 6e-Sixth World Core Rulebook-CAT28000.pdf")
    assert plan_renames([{"book": "corebook", "file": str(f)}], REG) == []


def test_a_rename_that_would_overwrite_is_flagged_not_performed(tmp_path):
    """Renaming one book over another is the worst outcome of a convenience."""
    _pdf(tmp_path, "Shadowrun 6e-Sixth World Core Rulebook-CAT28000.pdf")
    src = _pdf(tmp_path, "book1.pdf")

    plan = plan_renames([{"book": "corebook", "file": str(src)}], REG)
    assert plan and plan[0]["collision"]

    out = apply_renames(plan)
    assert out["renamed"] == []
    assert out["skipped"] and src.exists(), "the source must be left alone"


def test_renaming_actually_renames(tmp_path):
    src = _pdf(tmp_path, "book1.pdf")
    plan = plan_renames([{"book": "corebook", "file": str(src)}], REG)
    out = apply_renames(plan)
    assert len(out["renamed"]) == 1
    assert not src.exists()
    assert (tmp_path / canonical_name("corebook", REG)).is_file()
