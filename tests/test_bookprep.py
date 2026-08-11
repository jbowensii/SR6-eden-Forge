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


# ---------- deleting a graphic has to mean something ----------

def test_the_extractor_reads_the_pruned_ledger():
    """The skip rule used to be "is the file already there?", so removing a
    useless illustration achieved nothing — the next import put it back and
    reported success. One import restored 3,115 discarded images that way.

    This asserts the wiring, not just the helper: an earlier attempt patched the
    file with a string replacement whose anchor no longer matched, printed
    success, and changed nothing.
    """
    import json as _json
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "tools" / "dump_book_images.py"
    text = src.read_text(encoding="utf-8")
    assert "_pruned.json" in text, "the ledger is never read"
    assert "skip = _pruned(book)" in text, "dump() never loads the ledger"
    assert "if tag in skip:" in text, "the ledger is loaded but never consulted"
    # and the consultation must come BEFORE the already-on-disk shortcut,
    # or a pruned graphic is re-extracted whenever it is absent — which is
    # precisely when it has been pruned
    assert text.index("if tag in skip:") < text.index("already = list(out.glob("), \
        "the ledger is checked after the file-exists shortcut"


def test_pruned_ledger_lookup_is_per_book():
    """A key pruned from one book must not suppress the same page/object id in
    another — different PDFs number their objects independently."""
    import importlib.util
    from pathlib import Path
    import json as _json, tempfile

    src = Path(__file__).resolve().parent.parent / "tools" / "dump_book_images.py"
    spec = importlib.util.spec_from_file_location("_dbi", src)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception:                       # needs fitz/registry at import time
        import pytest
        pytest.skip("dump_book_images needs its runtime deps")
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        (data / "_assets").mkdir()
        (data / "_assets" / "_pruned.json").write_text(
            _json.dumps({"corebook": ["p003_x99"]}), encoding="utf-8")
        mod.DATA = data
        assert mod._pruned("corebook") == {"p003_x99"}
        assert mod._pruned("double_clutch") == set()
        assert mod._pruned("nonexistent") == set()


# ---------- re-reading may improve a vehicle, never empty it ----------

def test_a_reread_that_misses_a_stat_block_keeps_the_old_numbers(tmp_path, monkeypatch):
    """The page reader is the ONLY source of vehicle stats — Commlink6 has none
    — and its output is rebuilt from scratch every import. A vehicle read on one
    run and missed on the next lost numbers that were correct and still printed
    in the book; 22 did exactly that."""
    import json
    iv = _iv()
    from extractor.merge import norm_base

    prior = {"items": [{"id": "cl6_ford", "name": "Ford Americar",
                        "system": {"handling": "4/5", "topSpeed": "160", "body": "11"},
                        "meta": {"book": "corebook", "source": "commlink6"}}]}
    out = tmp_path / "vehicles.json"
    out.write_text(json.dumps(prior), encoding="utf-8")

    # this run read the row but got no stats off the page
    byname = {norm_base("Ford Americar"): {
        "name": "Ford Americar", "system": {"handling": "", "topSpeed": "", "body": ""},
        "page": 296}}
    by_prior = {norm_base(i["name"]): i for i in prior["items"]}
    kept = 0
    for key, rec in byname.items():
        was = (by_prior.get(key) or {}).get("system") or {}
        for field in iv.FIELDS:
            if str(rec["system"].get(field) or "").strip():
                continue
            if str(was.get(field) or "").strip():
                rec["system"][field] = was[field]
                kept += 1
    assert kept == 3
    assert byname[norm_base("Ford Americar")]["system"]["handling"] == "4/5"
    assert byname[norm_base("Ford Americar")]["system"]["topSpeed"] == "160"


def test_a_fresh_read_still_wins_over_the_old_value():
    """Preserving must not freeze a bad early reading in place."""
    iv = _iv()
    rec = {"system": {"handling": "3/3"}}
    was = {"handling": "9/9"}
    for field in ("handling",):
        if not str(rec["system"].get(field) or "").strip() and str(was.get(field) or "").strip():
            rec["system"][field] = was[field]
    assert rec["system"]["handling"] == "3/3"


def test_the_preservation_runs_after_the_fold():
    """Rows carried through from Commlink6 are created BY the fold, so preserving
    before it would leave exactly those rows unprotected."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "ingest_vehicles.py"
    text = src.read_text(encoding="utf-8")
    assert text.index("fold_into_authority(byname, cl6_by_name)") < text.index("Stats a PREVIOUS run read")


# ---------- the extractor must look where the library actually is ----------

def test_the_extractor_writes_flat_into_assets():
    """It wrote to _assets/<book>/ while the library is one flat folder, so the
    already-on-disk check never saw the curated file and re-extracted all 1,001
    of them into 48 recreated folders — on a run where the pruned ledger was
    working perfectly. Where it writes, where it looks, and where the library
    lives have to be the same place."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "dump_book_images.py"
    text = src.read_text(encoding="utf-8")
    assert 'out = DATA / "_assets"\n' in text, "still writing per-book"
    assert '_assets" / book' not in text, "a per-book path survives"
    assert 'out.glob(f"*{tag}.*")' in text, "the existing-file check must use the same dir"


def test_critters_and_npcs_are_not_given_a_guessed_icon():
    """This pass runs BEFORE install_category_icons, and used to fill them by
    name — "Rat" got icon_devil_rat_spirit_4 — so the exclusion downstream had
    nothing left to protect and 176 items lost their waiting-for-a-portrait
    state."""
    from extractor.icon_match import NO_AUTO_ICON
    assert NO_AUTO_ICON == {"CRITTER", "NPC"}

    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "extractor" / "icon_match.py"
    text = src.read_text(encoding="utf-8")
    # the guard has to sit before the name match, not after it
    assert text.index("NO_AUTO_ICON:") < text.index("source, score = best_match("), \
        "the exclusion runs after the name match"


def test_the_two_icon_passes_agree_on_who_is_excluded():
    """install_category_icons and match_icons keep separate lists; if they drift
    the earlier pass fills what the later one is trying to protect."""
    from extractor.icon_match import NO_AUTO_ICON
    import importlib.util
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "install_category_icons.py"
    spec = importlib.util.spec_from_file_location("_ici", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.NO_CATEGORY_ICON == NO_AUTO_ICON


def test_a_phase_with_nothing_to_do_finishes_instead_of_crashing():
    """convert_art_to_webp divided by the original byte total to report a ratio.
    On a library that is already fully WebP nothing is read, before is 0, and it
    took the whole import down at phase 20 of 23 — after forty minutes of work,
    for a phase that had correctly decided it had nothing to do."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "convert_art_to_webp.py"
    text = src.read_text(encoding="utf-8")
    assert "if before else" in text, "the ratio is computed without guarding before == 0"
    # the summary line must use the guarded value and never divide on its own
    line = text[text.index('print(f"converted '):]
    line = line[:line.index("left as they were")]
    assert "{ratio}" in line, "the summary does not use the guarded ratio"
    assert "/ before" not in line, "an unguarded division survives in the output line"


# ---------- flat storage must not throw the book away ----------

def test_the_extractor_records_which_book_each_graphic_came_from():
    """Flat storage lost it: p048_x1029.webp could be from any of fifty PDFs,
    and two books really do both have one. Auto-pairing keys on (book, page), so
    without this index it cannot run at all — it paired 0 items every time and
    printed that as a success line."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "dump_book_images.py"
    text = src.read_text(encoding="utf-8")
    assert "_index.json" in text, "the book/page index is never written"
    assert "index[dest.name] = [book, pno + 1]" in text, "newly saved files are not indexed"
    assert "index[p.name] = [book, pno + 1]" in text, \
        "files already on disk are not indexed — the index would only ever cover a fresh run"
    assert "return saved, skipped_full, skipped_small, failed, index" in text


def test_pairing_asks_where_the_library_is_and_reads_the_index():
    """Three ways this phase reported 'auto-paired 0' as though it were a result:
    it globbed 'data/...' relative to the working directory instead of asking
    data_root(), it looked in _assets/<book>/_inbox/ which no longer exists, and
    it matched *.png on a library that is entirely WebP."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "pair_art.py"
    text = src.read_text(encoding="utf-8")
    assert "from extractor.paths import data_root" in text
    assert "DATA = data_root()" in text
    assert "_inbox" not in text.split('"""', 2)[-1], "still globbing the old per-book inbox"
    assert 'glob.glob("data/' not in text and 'glob.glob(f"data/' not in text, \
        "still reading a path relative to the working directory"
    assert "_index.json" in text, "pairing does not consult the book/page index"


def test_the_index_round_trips_through_the_loader(tmp_path):
    import json
    import importlib.util
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "pair_art.py"
    spec = importlib.util.spec_from_file_location("_pa", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    (tmp_path / "_index.json").write_text(json.dumps({
        "p048_x1029.webp": ["double_clutch", 48],
        "ares_predator_p012_x77.webp": ["corebook", 12],
        "junk.webp": "not-a-pair",
    }), encoding="utf-8")
    idx = mod.load_index(tmp_path)
    assert idx["p048_x1029.webp"] == ("double_clutch", 48)
    assert idx["ares_predator_p012_x77.webp"] == ("corebook", 12)
    assert "junk.webp" not in idx, "a malformed row must be skipped, not crash the phase"
    assert mod.load_index(tmp_path / "nope") == {}


# ---------- excluding a type has to be active, not passive ----------

def _ici():
    import importlib.util
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "install_category_icons.py"
    spec = importlib.util.spec_from_file_location("_ici2", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_placeholder_is_cleared_from_an_excluded_type():
    """Declining to ASSIGN a category icon does nothing about one an earlier run
    already stamped on, because both icon passes skip an item that has an img at
    all. 216 critters and NPCs kept generic/critter.svg through every import and
    looked finished instead of waiting for a portrait."""
    mod = _ici()
    src = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
    assert 'if pair[0] in NO_CATEGORY_ICON:' in src
    assert 'item["img"] = ""' in src, "the placeholder is never cleared"
    # a real book graphic must survive that clearing
    assert mod.replaceable("generic/critter.svg", True) is True
    assert mod.replaceable("bodyguard_p100_x453.webp", True) is False
    assert mod.replaceable("corebook/lib/x.webp", True) is True


def test_the_remembered_default_is_forgotten_for_an_excluded_type():
    """defaults.json held CRITTER/ -> generic/critter.svg from before these types
    were excluded, and icon_match reads that file — so the exclusion in both
    passes was undone by a third place that simply remembered the old answer."""
    mod = _ici()
    defaults = {"CRITTER/": "generic/critter.svg", "NPC/": "generic/npc.svg",
                "CRITTER_AWAKENED/": "generic/critter_awakened.webp",
                "CRITTER_POWER/": "generic/critter_power.webp",
                "VEHICLE/CARS": "generic/vehicle_cars.webp"}
    for key in [k for k in defaults if k.split("/")[0] in mod.NO_CATEGORY_ICON]:
        del defaults[key]
    assert "CRITTER/" not in defaults and "NPC/" not in defaults
    # compared on the whole type, not a prefix — these are their own types
    assert defaults["CRITTER_AWAKENED/"] == "generic/critter_awakened.webp"
    assert defaults["CRITTER_POWER/"] == "generic/critter_power.webp"
    assert defaults["VEHICLE/CARS"] == "generic/vehicle_cars.webp"


# ---------- the guard must not undo a deliberate deletion ----------

def test_the_guard_does_not_protect_a_row_the_user_deleted(tmp_path):
    """The snapshot is taken BEFORE the phases run, so it sees rows the user
    deleted but the previous import left behind. Phase 3 correctly leaves them
    out, the guard reads that as a phase destroying a Commlink6 row, and puts it
    back: 29 of the 30 vehicles deleted in the review app returned on the very
    import whose log said "left out 30"."""
    import json
    from extractor import authority

    (tmp_path / "_corrections" / "vehicles").mkdir(parents=True)
    (tmp_path / "_corrections" / "vehicles" / "a.json").write_text(json.dumps(
        {"domain": "vehicles", "id": "cl6_dodge_scoot", "deleted": True}), encoding="utf-8")
    (tmp_path / "_corrections" / "vehicles" / "b.json").write_text(json.dumps(
        {"domain": "vehicles", "id": "cl6_ford", "name": "Ford"}), encoding="utf-8")
    assert authority.deleted_ids(tmp_path) == {"cl6_dodge_scoot"}

    d = tmp_path / "corebook" / "vehicles"
    d.mkdir(parents=True)
    (d / "vehicles.json").write_text(json.dumps({"book": "corebook", "domain": "vehicles",
        "category": "vehicles", "items": [
            {"id": "cl6_dodge_scoot", "name": "Dodge Scoot", "system": {"price": 3000},
             "meta": {"source": "commlink6"}},
            {"id": "cl6_ford", "name": "Ford Americar", "system": {"price": 16000},
             "meta": {"source": "commlink6"}},
        ]}), encoding="utf-8")

    snap = authority.snapshot(tmp_path)
    guarded = [i["id"] for rows in snap["rows"].values() for i in rows]
    assert "cl6_ford" in guarded, "a live Commlink6 row must still be guarded"
    assert "cl6_dodge_scoot" not in guarded, "the guard would resurrect a deleted row"
    assert "cl6_dodge_scoot" not in snap["fields"]


# ---------- the import checks its own work ----------

def _verify():
    import importlib.util
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "verify_library.py"
    spec = importlib.util.spec_from_file_location("_vl", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_bug_of_this_kind_has_a_rule():
    """The cycle only ends if each defect leaves a check behind. These are the
    ones that shipped as successful runs; none may quietly lose its rule."""
    mod = _verify()
    names = {n for n, _ in mod.RULES}
    assert names >= {
        "deletions stick",                          # guard resurrected 29 vehicles
        "critters and NPCs await a portrait",       # 216 kept generic/critter.svg
        "no remembered default for those types",    # defaults.json undid both passes
        "no art nobody references",                 # 1,001 dupes; 651 orphaned icons
        "pruned art stays deleted",                 # 3,115 images came back
        "every image reference resolves",           # WebP migration broke links
        "graphics know their book",                 # flat names lost the book
    }
    assert all(callable(r) for _, r in mod.RULES)


def test_the_import_runs_the_checks_at_the_end():
    """A checker nothing calls is exactly the failure it exists to catch."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "import_library.py"
    text = src.read_text(encoding="utf-8")
    assert "verify_library" in text, "the import never runs the checks"
    assert "for rule_name, rule in _verify.RULES:" in text
    assert text.index("_verify.RULES") < text.index("TOTALS commlink6"), \
        "the checks must run before the summary that claims success"


def test_a_rule_that_raises_counts_as_a_failure():
    """A check that errors must not read as a pass — that is this whole class of
    bug wearing a different hat."""
    mod = _verify()
    def exploding(data, items, corrections):
        raise RuntimeError("boom")
    ok = True
    try:
        ok, _, _ = exploding(None, [], [])
    except Exception:
        ok = False
    assert ok is False
    src = __import__("pathlib").Path(mod.__file__).read_text(encoding="utf-8")
    assert "the check itself failed" in src


def test_rules_pass_on_a_clean_library(tmp_path):
    """The rules must be satisfiable — a check that can never pass gets ignored."""
    import json
    mod = _verify()
    d = tmp_path / "corebook" / "gear"
    d.mkdir(parents=True)
    (tmp_path / "_assets").mkdir()
    (d / "gear.json").write_text(json.dumps({"book": "corebook", "domain": "gear",
        "category": "gear", "items": [
            {"id": "a", "name": "Ares Predator VI", "system": {"type": "WEAPON_FIREARMS"}},
            {"id": "b", "name": "A Critter", "system": {"type": "CRITTER"}},
        ]}), encoding="utf-8")
    items = list(mod._items(tmp_path))
    corrections = list(mod._corrections(tmp_path))
    assert len(items) == 2
    for name, rule in mod.RULES:
        ok, message, _ = rule(tmp_path, items, corrections)
        assert ok, f"{name} cannot pass even on a clean library: {message}"


# ---------- never replace something with nothing ----------

def _rd():
    import importlib.util
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "rebuild_descriptions.py"
    spec = importlib.util.spec_from_file_location("_rd", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_failed_reread_does_not_erase_a_description():
    """It wrote "" over any description the re-scan failed to find again — 1,926
    in one run. It looked survivable only because the Commlink6 guard put 2,073
    back afterwards, every import; the items the guard does not cover just lost
    their text."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "rebuild_descriptions.py"
    text = src.read_text(encoding="utf-8")
    assert "Never replace something with nothing." in text
    assert 'counts["kept"] += 1' in text
    assert text.index("if not new:") < text.index('it["system"]["description"] = new'), \
        "the guard must come before the write"


def test_junk_is_still_cleared_but_prose_is_not():
    """Blanking is right for a stat row that landed in the description field and
    wrong for a sentence. The distinction is what lets the guard be safe."""
    mod = _rd()
    assert mod.desc_is_table_row("4/5 9 20 160 11 4 1 2 4 2 16,000") is True
    assert mod.desc_is_table_row(
        "Extra spikes, dark colors, and a generally angry-looking aesthetic.") is False


def test_the_description_phase_asks_where_the_library_is():
    """It used a path relative to the working directory, so from the wrong
    folder it would rewrite every description in the developer's scratch copy
    and report success."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "tools" / "rebuild_descriptions.py"
    text = src.read_text(encoding="utf-8")
    assert "DATA = data_root()" in text
    assert 'glob.glob("data/' not in text and 'glob.glob(f"data/' not in text


def test_the_ratchet_notices_a_library_that_shrank(tmp_path):
    """The one rule that does not need the bug to have happened first: it knows
    the SHAPE of all of them — an import finishing with less than the one
    before."""
    import json
    mod = _verify()
    (tmp_path / "_assets").mkdir()
    (tmp_path / "_assets" / "_health.json").write_text(
        json.dumps({"items": 5000, "descriptions": 4000, "images": 4900}), encoding="utf-8")
    items = [("gear", {"id": str(i), "name": "x", "system": {"description": "d"}, "img": "a.webp"})
             for i in range(100)]
    ok, message, dropped = mod.rule_nothing_went_backwards(tmp_path, items, [])
    assert not ok and dropped, "a library that lost 98% of its items passed"

    # and the floor only ever rises
    big = [("gear", {"id": str(i), "name": "x", "system": {"description": "d"}, "img": "a.webp"})
           for i in range(9000)]
    ok, _, _ = mod.rule_nothing_went_backwards(tmp_path, big, [])
    assert ok
    floor = json.loads((tmp_path / "_assets" / "_health.json").read_text(encoding="utf-8"))
    assert floor["items"] == 9000, "the high-water mark was not remembered"
