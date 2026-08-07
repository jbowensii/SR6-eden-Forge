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


def test_language_is_not_a_gate_ownership_is(tmp_path):
    """A German book imports if you own its PDF, exactly like an English one.
    Language decides post-import curation, not whether data may be read."""
    pdf = tmp_path / "lofwyr.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert plan_book("lofwyr", {"pdf": str(pdf)}, {"lofwyr": 12})["source"] == "both"


def test_a_german_book_you_do_not_own_is_still_refused():
    assert plan_book("lofwyr", {"pdf": ""}, {"lofwyr": 12})["source"] == "skip"


def test_german_list_is_kept_for_curation_not_gating():
    assert "lofwyr" in GERMAN_BOOKS and "slip_streams" in GERMAN_BOOKS


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


def test_plan_import_without_a_registry_says_what_to_do(tmp_path):
    """The import must not die on a raw FileNotFoundError.

    Regression: the installed app passed ``--data <workspace>/data`` but never
    wrote the scanned book registry there, so the first Import crashed with a
    traceback naming a path the user had never chosen.
    """
    import pytest

    from extractor.ownership import plan_import

    with pytest.raises(SystemExit) as e:
        plan_import(tmp_path)
    assert "books.json" in str(e.value)
    assert "scan" in str(e.value).lower()


def test_import_writes_the_registry_into_the_workspace(tmp_path):
    """The scan's matches must land where the pipeline actually reads them."""
    from build.catalog_builder import books

    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "data" / "books.json").write_text(
        '{"corebook": {"title": "Sixth World Core Rulebook", "cat": "CAT28000"}}',
        encoding="utf-8")

    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    (pdfs / "Shadowrun 6e-Core Rulebook-CAT28000.pdf").write_bytes(b"%PDF-1.4\n")

    result = books.scan(pdfs, books.load_registry(repo))
    assert len(result["matched"]) == 1

    ws = tmp_path / "workspace"
    out = books.apply_to_registry(repo, result, out=ws / "data" / "books.json")
    assert out.is_file()

    import json
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["corebook"]["pdf"].endswith("CAT28000.pdf")

    # and the plan can now be built from it, which is the thing that crashed
    from extractor.ownership import plan_import
    assert plan_import(ws / "data")
