"""The parallel reading pass.

The pool is not exercised here — spawning real processes in a unit test is
slow and flaky. What matters is the contract around it: that a failing book is
isolated, that the serial path is a true fallback, and that nothing about the
merge order is decided in this module.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

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


# ---------- the worker modules ----------

SCANS = ["content_scan", "newtype_scan", "vehicle_scan", "writeup_scan"]


@pytest.mark.parametrize("name", SCANS)
def test_every_scan_module_imports(name):
    """A worker's imports must resolve, or the phase silently finds nothing.

    vehicle_scan shipped importing ``read_statblock_vehicles`` from a module
    that does not define it. The worker's broad except — there so one bad book
    cannot lose the other forty-nine — turned that ImportError into an empty
    result, per book, and the phase reported success with zero vehicles. The
    top-level import is checked here; nothing else in the suite loads these
    modules, because in production only a spawned child ever does.
    """
    importlib.import_module(f"extractor.{name}")


@pytest.mark.parametrize("name", SCANS)
def test_every_scan_module_exposes_scan_book(name):
    """map_jobs calls this name by convention; a rename would fail at spawn."""
    mod = importlib.import_module(f"extractor.{name}")
    assert callable(getattr(mod, "scan_book", None))


#: ``name -> (job, error-key)``. The three tuple-taking scans and the dict-taking
#: one are listed out rather than normalised: each has one caller, the shapes
#: match what that caller already had, and rewriting a working contract to make
#: this table shorter would be the tail wagging the dog.
SCAN_JOBS = {
    "content_scan": (("ghost", r"C:\nope\missing.pdf"), "errors"),
    "newtype_scan": (("ghost", r"C:\nope\missing.pdf"), "errors"),
    "vehicle_scan": (("ghost", r"C:\nope\missing.pdf"), "errors"),
    "writeup_scan": ({"book": "ghost", "pdf": r"C:\nope\missing.pdf",
                      "wanted": [("x", "Ares Predator", 1)]}, "error"),
}


#: Scripts that do their work against the library at module level. Importing one
#: of these must not run it — see the test below for why this list exists.
#:
#: Tier B (the nine phases import_library dispatches) is deliberately NOT here.
#: Those stayed unguarded until a guard can be proven through the frozen build,
#: because a guard the dispatcher fails to enter is a phase that reports success
#: and does nothing — the exact shape of Gap 2.
LIBRARY_WRITERS = [
    "images_all", "rebuild_all",
    "align_content_eden", "backfill_metatype", "commlink6_report",
    "extract_all_images", "fill_critter_powers", "fill_descriptions",
    "fix_qualities_eden", "gen_newtype_schemas", "ingest_adept_powers",
    "ingest_all", "ingest_critters", "ingest_drugs_toxins", "ingest_lifestyles",
    "ingest_npcs", "ingest_qualities", "ingest_rituals", "ingest_skills",
    "ingest_spells", "ingest_spirits", "merge_chemicals", "merge_commlink6",
    "recover_electronics_names", "reingest_books", "search_critter_powers",
]


@pytest.mark.parametrize("name", LIBRARY_WRITERS)
def test_importing_a_library_writer_does_not_run_it(name):
    """These two guard their work behind ``if __name__ == "__main__"``.

    Most of tools/ executes at import — they are scripts, and that is fine for
    a script you run deliberately. These two are different in kind: one rewrites
    every gear file and re-extracts hundreds of PNGs, the other runs all 21
    phases. Both were started by accident during a review pass, by nothing more
    than an ``import`` to look at the module.

    The guard is the fix; this is the thing that notices if it is ever removed.
    A module-level marker is checked rather than the behaviour itself, because
    a test that got this wrong would run the pipeline to find out.
    """
    src = (Path(__file__).resolve().parent.parent
           / "tools" / f"{name}.py").read_text(encoding="utf-8")
    assert '__name__ == "__main__"' in src, (
        f"tools/{name}.py rewrites the library at import time — restore its "
        f"__main__ guard")


@pytest.mark.parametrize("name", SCANS)
def test_a_scan_worker_reports_a_bad_pdf_rather_than_raising(name):
    """An exception escaping a worker takes the whole pool down with it."""
    mod = importlib.import_module(f"extractor.{name}")
    job, err_key = SCAN_JOBS[name]
    r = mod.scan_book(job)
    assert r["book"] == "ghost"
    assert r[err_key]                      # reported, not raised
    assert not r["found"]


# ---------- the vehicle table crop ----------

class _Page:
    """Just enough of a pdfplumber page for _pad."""
    def __init__(self, bbox):
        self.bbox = bbox


PAGE = _Page((0.0, 0.0, 612.0, 765.0))


def test_padding_a_table_box_stays_on_the_page():
    """pdfplumber raises on a crop that leaves the page.

    The 11-value row sits under the ruled header, so the box is padded out 2pt
    and down 18pt. On a table that touches the edge that padding lands outside
    the page, pdfplumber raises ValueError, and the worker's except reports it
    as "this book has no vehicles". Five books lost their whole vehicle scan to
    one such table; krime_katalog alone was hiding 12.
    """
    from extractor.vehicle_scan import _pad

    x0, top, x1, bottom = _pad((0.0, 48.0, 612.0, 490.0), PAGE)
    assert x0 >= 0.0 and x1 <= 612.0
    assert top >= 0.0 and bottom <= 765.0


def test_a_negative_table_top_is_clamped_not_refused():
    """find_tables() reports a negative top on some rotated pages."""
    from extractor.vehicle_scan import _pad

    box = _pad((-2.2, -941.0, 752.0, 1894.0), _Page((0, 0.0, 750, 938.88)))
    assert box == (0, 0.0, 750, 938.88)


def test_padding_keeps_a_normal_box_intact():
    """Clamping must not disturb a table that was already on the page."""
    from extractor.vehicle_scan import _pad

    assert _pad((100.0, 200.0, 400.0, 300.0), PAGE) == (98.0, 198.0, 402.0, 318.0)


def test_a_degenerate_table_box_is_skipped_not_cropped():
    """A zero-width box off the page edge would crop to nothing."""
    from extractor.vehicle_scan import _pad

    assert _pad((900.0, 100.0, 950.0, 120.0), PAGE) is None


# ---------- vehicle names that wrap across three lines ----------

def _iv():
    """Load ingest_vehicles WITHOUT running it (its work is behind __main__)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "iv", Path(__file__).resolve().parent.parent / "tools" / "ingest_vehicles.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: p302 as pdfplumber reads it: the name breaks around the stat row.
CORE_LINES = [
    "Ford Americar 4/5 9 20 160 11 4 1 2 4 2 16,000",
    "Saeder-",
    "Krupp-Bentley 3/5 18 30 180 14 8 3 3 4 3 65,000",
    "Concordat",
]


def test_a_name_wrapped_around_its_stat_row_is_rejoined():
    iv = _iv()
    used = set()
    assert iv._unwrap(CORE_LINES, 2, "Krupp-Bentley", used) == "Saeder-Krupp-Bentley Concordat"


def test_a_trailing_hyphen_opens_the_next_name_not_the_previous_one():
    """'Saeder-' sits between two stat rows and belongs to the LATER one.

    Taken as Ford Americar's tail it left the Concordat without its marque.
    """
    iv = _iv()
    assert iv._unwrap(CORE_LINES, 0, "Ford Americar", set()) == "Ford Americar"


def test_a_name_part_is_never_spent_twice():
    """'Nightrunner' closes one vehicle and sits above the next one's stat row."""
    iv = _iv()
    lines = ["Aztechnology", "Sunrunner/ 3 20 20 120", "Nightrunner",
             "GMC Riverine 4 10 10 40"]
    used = set()
    first = iv._unwrap(lines, 1, "Sunrunner/", used)
    second = iv._unwrap(lines, 3, "GMC Riverine", used)
    assert first == "Aztechnology Sunrunner/Nightrunner"
    assert second == "GMC Riverine"        # not "Nightrunner GMC Riverine"


def test_a_wrapped_price_is_not_mistaken_for_a_name():
    """The Federated Boeing Commuter has '350,000/' directly above its stats."""
    iv = _iv()
    lines = ["Federated Boeing", "350,000/", "Commuter/ 3 35 60/80 420", "800,000"]
    assert iv._unwrap(lines, 2, "Commuter/", set()) == "Federated Boeing Commuter/"


def test_a_vehicle_keeps_the_book_it_was_read_from():
    """ingest_vehicles labelled every vehicle "corebook", whatever book it came
    from — so a Double Clutch drone carried a corebook page number pointing at
    something else. The writer must read `_book` off the record.

    Checked as source text: the writer lives inside the script's __main__ guard
    and importing it to call it would run the whole phase against the library.
    """
    src = (Path(__file__).resolve().parent.parent
           / "tools" / "ingest_vehicles.py").read_text(encoding="utf-8")
    assert '"book": "corebook"' not in src, (
        "ingest_vehicles is hard-coding the book again — statblock vehicles "
        "will all claim to come from the corebook")
    assert 'r.get("_book", LIBRARY)' in src
    assert 'rec["_book"] = book' in src


# ---------- Commlink6 names the vehicle, the page supplies its stats ----------

def _auth(vid="cl6_krime_dix", name="Krime Dix Prime Mover", **system):
    sysd = {"type": "VEHICLE", "subtype": "TRUCK", "price": 200000,
            "handling": "", "accel": "", "body": ""}
    sysd.update(system)
    return {"id": vid, "name": name, "system": sysd,
            "meta": {"book": "krime_katalog", "page": 37, "source": "commlink6"}}


def _page(name="Krime Dix", **system):
    sysd = {"handling": "2/3", "accel": "4", "body": "15", "price": "200,000"}
    sysd.update(system)
    return {"name": name, "system": sysd, "page": 99}


def test_the_page_fills_the_stats_commlink6_leaves_empty():
    """Commlink6 has NO vehicle stat line — 421 of its vehicles carry none.

    The page-read row is the only place those numbers exist, so folding must
    fill them rather than discard the row as a duplicate.
    """
    iv = _iv()
    merged, folded = iv.fold_into_authority({"k": _page()}, {"k": _auth()})
    row = merged["k"]
    assert row["system"]["handling"] == "2/3"
    assert row["system"]["body"] == "15"
    assert folded == [("Krime Dix", "Krime Dix Prime Mover", 3)]


def test_commlink6_keeps_every_value_it_states():
    """price is 200000 upstream and '200,000' off the page — upstream wins."""
    iv = _iv()
    merged, _ = iv.fold_into_authority({"k": _page()}, {"k": _auth()})
    assert merged["k"]["system"]["price"] == 200000


def test_a_folded_row_keeps_the_commlink6_identity():
    """A fresh id would let the guard resurrect the original beside it, and
    every correction keyed to that id would stop finding its target."""
    iv = _iv()
    merged, _ = iv.fold_into_authority({"k": _page()}, {"k": _auth()})
    assert merged["k"]["_id"] == "cl6_krime_dix"
    assert merged["k"]["name"] == "Krime Dix Prime Mover"
    assert merged["k"]["_meta"]["source"] == "commlink6"


def test_a_vehicle_commlink6_does_not_have_passes_through():
    iv = _iv()
    merged, folded = iv.fold_into_authority({"k": _page(name="Ford Dasher")}, {})
    assert folded == [] and merged["k"]["name"] == "Ford Dasher"
    assert "_id" not in merged["k"]


def test_folding_never_mutates_the_authority_row():
    """The caller's rows are read again later; folding must not scribble on them."""
    iv = _iv()
    auth = _auth()
    iv.fold_into_authority({"k": _page()}, {"k": auth})
    assert auth["system"]["handling"] == ""
