"""The parallel reading pass.

The pool is not exercised here — spawning real processes in a unit test is
slow and flaky. What matters is the contract around it: that a failing book is
isolated, that the serial path is a true fallback, and that nothing about the
merge order is decided in this module.
"""
from __future__ import annotations

from extractor.bookprep import default_workers, prepare_book, prepare_books


def test_a_missing_pdf_fails_only_that_book():
    """One unreadable book must not lose the other forty-nine."""
    r = prepare_book({"book": "ghost", "pdf": r"C:\nope\missing.pdf",
                      "curated": True, "libText": ""})
    assert r["book"] == "ghost"
    assert r["error"]                      # reported, not raised
    assert r["incoming"] == {} and r["lines"] == []


def test_serial_path_returns_the_same_shape():
    """workers=1 is the fallback, so it must behave identically."""
    jobs = [{"book": "a", "pdf": r"C:\nope\a.pdf", "curated": True, "libText": ""},
            {"book": "b", "pdf": r"C:\nope\b.pdf", "curated": True, "libText": ""}]
    seen = []
    out = prepare_books(jobs, workers=1, on_done=seen.append)
    assert set(out) == {"a", "b"}
    assert len(seen) == 2                  # progress fires per book either way
    assert all(set(r) >= {"book", "pages", "incoming", "hier", "markers",
                          "lines", "error"} for r in out.values())


def test_default_workers_is_sane():
    n = default_workers()
    assert 1 <= n <= 16


def test_prepare_book_takes_and_returns_only_plain_data():
    """Results cross a process boundary, so everything must pickle."""
    import pickle

    r = prepare_book({"book": "ghost", "pdf": r"C:\nope\missing.pdf",
                      "curated": True, "libText": ""})
    assert pickle.loads(pickle.dumps(r)) == r
