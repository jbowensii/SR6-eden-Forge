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


# ---------- the caption band replaces the ruled table ----------
#
# The crop-and-pad tests that used to live here went with `_pad`. They asserted
# that a box derived from find_tables() was nudged left and down without leaving
# the page — machinery the reader no longer has, because for 35% of Double
# Clutch's stat blocks find_tables() returns no box to nudge.


def test_captions_printed_with_no_gap_are_split_apart():
    """pdfplumber joins captions set without a measurable gap."""
    from extractor.vehicle_scan import _split_caption

    assert _split_caption("BODYARMPILOT") == ["BODY", "ARM", "PILOT"]
    assert _split_caption("HANDACC") == ["HAND", "ACC"]
    assert _split_caption("PILOT") == ["PILOT"]
    # a word that merely starts like a caption is not one
    assert _split_caption("SEATBELTFACTORY") == []


def test_a_column_is_identified_by_its_printed_caption():
    """The 9-vs-11 column ambiguity that broke every count-based attempt cannot
    arise: a table missing SPD INT is missing it because the book did not print
    it, and the caption says so."""
    from extractor.vehicle_scan import _CAPTION

    assert _CAPTION["SPDINT"] == "speedInterval"
    assert _CAPTION["TOPSPD"] == "topSpeed"
    # SR5 books (Krime Katalog) print SPEED, which is NOT Speed Interval and
    # must not be merged into it downstream
    assert _CAPTION["SPEED"] == "speed"
    assert _CAPTION["SPD"] == "speed"


def test_dashes_and_broken_glyphs_count_as_values():
    """Both the em dash and the nuyen sign arrive as U+FFFD in these PDFs, and a
    missing stat still occupies its column."""
    from extractor.vehicle_scan import _is_value

    assert _is_value("4/6")
    assert _is_value("2/4*")
    assert _is_value("—")
    assert _is_value("16,000�")
    assert not _is_value("Growler")


def test_a_price_or_a_section_label_is_not_a_vehicle_name():
    """What actually needs rejecting is a price that landed in the name column
    and the 'krime prowler: sr5 stats' caption over a rules table."""
    from extractor.vehicle_scan import _named

    assert not _named({"name": "58,000¥"})
    assert not _named({"name": "1,000"})
    assert not _named({"name": "krime prowler: sr5 stats"})
    assert not _named({"name": ""})
    # ...and NOT these, which the general-purpose gear-name test threw out
    for real in ("Eurocar Northstar 2.0", "Gaz-Niki P-183", "GD/CAS MacArthur",
                 "Ranger class battlecruiser", "Honda Rough Rider"):
        assert _named({"name": real}), real


def test_implausible_flags_a_scrambled_row_but_allows_a_capital_ship():
    """Double Clutch stats out capital ships: Body 200 and 7,000,000,000¥ are
    printed values, not parse failures."""
    from extractor.vehicle_scan import implausible

    assert implausible({"handling": "25"})              # a car cannot handle 25
    assert not implausible({"handling": "4/5", "body": "200",
                            "price": "7,000,000,000", "seats": "535"})


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


# ---------- vehicles Commlink6 names but no book describes ----------

def test_unmatched_commlink6_vehicles_are_carried_through():
    """The fold's result is written over vehicles.json, so anything left out of
    it is deleted. Commlink6 lists hundreds of vehicles no stat table we own
    describes; dropping them cost 423 of 485 rows the first time this phase ran
    on its own."""
    iv = _iv()
    page = {"ford": {"name": "Ford Americar", "system": {"handling": "4/5"}, "page": 296}}
    cl6 = {
        "ford": {"id": "cl6_ford", "name": "Ford Americar", "system": {"price": "16000"},
                 "meta": {"book": "corebook", "page": 296, "source": "commlink6"}},
        "obscure": {"id": "cl6_obscure", "name": "Obscure Hovercraft", "system": {"price": "9000"},
                    "meta": {"book": "corebook", "page": 300, "source": "commlink6"}},
    }
    merged, folded = iv.fold_into_authority(page, cl6)

    assert set(merged) == {"ford", "obscure"}          # nothing dropped
    assert merged["ford"]["system"]["handling"] == "4/5"   # page filled the gap
    assert merged["ford"]["system"]["price"] == "16000"    # Commlink6 kept its own
    assert merged["ford"]["_id"] == "cl6_ford"
    # the untouched one keeps its identity so corrections still find it
    assert merged["obscure"]["_id"] == "cl6_obscure"
    assert merged["obscure"]["system"]["price"] == "9000"
    assert [f[1] for f in folded] == ["Ford Americar"]     # only the match is a fold


# ---------- Commlink6 names the maker, the book names the model ----------

def test_a_distinctive_suffix_folds_onto_the_commlink6_row():
    """Commlink6 records the full trade name and the books print the model
    alone, so an exact-name fold strands the stats on a second row."""
    iv = _iv()
    page = {"streetrocketex": {"name": "Street Rocket EX",
                               "system": {"handling": "1/1"}, "page": 44}}
    cl6 = {"spinradglobalstreetrocketex": {
        "id": "cl6_srex", "name": "Spinrad Global Street Rocket EX",
        "system": {"price": "1500000"},
        "meta": {"book": "double_clutch", "page": 44, "source": "commlink6"}}}
    merged, folded = iv.fold_into_authority(page, cl6)

    assert set(merged) == {"spinradglobalstreetrocketex"}      # one row, not two
    row = merged["spinradglobalstreetrocketex"]
    assert row["name"] == "Spinrad Global Street Rocket EX"     # Commlink6 owns the name
    assert row["system"]["handling"] == "1/1"                   # the page brought the stats
    assert row["_id"] == "cl6_srex"
    assert folded == [("Street Rocket EX", "Spinrad Global Street Rocket EX", 1)]


def test_an_ambiguous_suffix_is_left_alone():
    """'Bazoo Chrome' ends both 'Krime Bazoo Chrome' and 'Krime Big Bazoo
    Chrome'. Guessing would hand one vehicle's stats to its larger sibling."""
    iv = _iv()
    page = {"bazoochrome": {"name": "Bazoo Chrome", "system": {"handling": "2/4"}, "page": 31}}
    cl6 = {
        "krimebazoochrome": {"id": "a", "name": "Krime Bazoo Chrome", "system": {},
                             "meta": {"book": "krime_katalog", "source": "commlink6"}},
        "krimebigbazoochrome": {"id": "b", "name": "Krime Big Bazoo Chrome", "system": {},
                                "meta": {"book": "krime_katalog", "source": "commlink6"}},
    }
    merged, folded = iv.fold_into_authority(page, cl6)
    assert folded == []                                   # nothing guessed
    assert "bazoochrome" in merged                        # the page row survives on its own
    assert {"krimebazoochrome", "krimebigbazoochrome"} <= set(merged)   # both kept


def test_a_short_name_never_matches_by_suffix():
    """'Van' ending 'Ford Van' would attach stats to the wrong thing."""
    iv = _iv()
    page = {"van": {"name": "Van", "system": {"handling": "3"}, "page": 1}}
    cl6 = {"fordvan": {"id": "c", "name": "Ford Van", "system": {},
                       "meta": {"book": "corebook", "source": "commlink6"}}}
    merged, folded = iv.fold_into_authority(page, cl6)
    assert folded == []
    assert set(merged) == {"van", "fordvan"}
