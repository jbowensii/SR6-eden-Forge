"""The ownership gate: a PDF is what permits an import."""
import json

import pytest

from extractor.ownership import (
    COMMLINK6_ALIAS,
    GERMAN_BOOKS,
    UNGATEABLE,
    plan_book,
    plan_import,
)


def test_no_pdf_means_no_import_even_when_commlink6_has_it():
    """The whole point. The jar carries the entire line; the PDF is the gate."""
    p = plan_book("firing_squad", {"pdf": "C:/nope/missing.pdf"},
                  {"firing_squad": 271})
    assert p["source"] == "skip"
    assert "ownership" in p["reason"]


def test_owned_and_in_commlink6_uses_both(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    p = plan_book("firing_squad", {"pdf": str(pdf)}, {"firing_squad": 271})
    assert p["source"] == "both"
    assert p["jarBook"] == "firing_squad"
    assert p["items"] == 271


def test_owned_with_no_commlink6_data_still_imports(tmp_path):
    """A book newer than Commlink6's coverage must not be locked out."""
    pdf = tmp_path / "brand_new.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    p = plan_book("brand_new", {"pdf": str(pdf)}, {"firing_squad": 271})
    assert p["source"] == "pdf"


def test_no_commlink6_at_all_falls_back_to_pdf(tmp_path):
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert plan_book("corebook", {"pdf": str(pdf)}, None)["source"] == "pdf"


def test_aliases_cover_the_names_that_differ(tmp_path):
    """Four books are filed under a different name by Commlink6. Without the
    alias, corebook alone loses 533 items."""
    pdf = tmp_path / "b.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert COMMLINK6_ALIAS["corebook"] == "core"
    p = plan_book("corebook", {"pdf": str(pdf)}, {"core": 533})
    assert p["source"] == "both" and p["jarBook"] == "core"


def test_german_books_are_not_importable_even_if_owned():
    """Standing rule: English only. Ownership does not override it."""
    assert "lofwyr" in GERMAN_BOOKS
    assert "slip_streams" in GERMAN_BOOKS


def test_grab_bags_are_ungateable():
    """No single PDF can prove ownership of a mixed-source file."""
    assert UNGATEABLE == {"other_us", "de_other"}


def test_plan_processes_corebook_first(tmp_path):
    """corebook is the curated seed whose hierarchy pass the others rely on."""
    (tmp_path / "books.json").write_text(json.dumps({
        "zzz_late": {"date": "2024-01", "pdf": ""},
        "corebook": {"date": "2019-08", "pdf": ""},
    }), encoding="utf-8")
    plan = plan_import(tmp_path, None)
    assert plan[0]["book"] == "corebook"


def test_real_registry_plans_without_error():
    import pathlib
    if not pathlib.Path("data/books.json").exists():
        pytest.skip("no local library")
    plan = plan_import(pathlib.Path("data"), None)
    assert plan and all(p["source"] in {"both", "pdf", "skip"} for p in plan)
