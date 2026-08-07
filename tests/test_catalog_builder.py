"""The catalog builder's non-UI logic.

The window itself is not tested — Tk needs a display and the interesting parts
are all underneath it: does it recognise a book, does it settle on a stable
config, does it refuse to publish over a running Foundry.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "build"))

from catalog_builder import books, publish, runner, settings  # noqa: E402

REG = {
    "corebook": {"title": "Sixth World Core Rulebook", "cat": "CAT28000"},
    "companion": {"title": "Sixth World Companion", "cat": "CAT28005"},
    "firing_squad": {"title": "Firing Squad", "cat": "CAT28002"},
}


def _pdf(d: Path, name: str) -> Path:
    p = d / name
    p.write_bytes(b"%PDF-1.4\n%%EOF\n")
    return p


# ---------- recognising books ----------

def test_matches_on_the_catalyst_product_code(tmp_path):
    """The strongest signal: retail PDFs carry it and the registry stores it."""
    _pdf(tmp_path, "Shadowrun 6e-Sixth World Core Rulebook-Current Printing-CAT28000.pdf")
    r = books.scan(tmp_path, REG)
    assert [m["book"] for m in r["matched"]] == ["corebook"]
    assert "CAT28000" in r["matched"][0]["how"]


def test_matches_a_renamed_file_on_its_title(tmp_path):
    _pdf(tmp_path, "SR6 - Sixth World Companion (2020).pdf")
    r = books.scan(tmp_path, REG)
    assert [m["book"] for m in r["matched"]] == ["companion"]


def test_searches_subfolders(tmp_path):
    sub = tmp_path / "Sourcebooks"
    sub.mkdir()
    _pdf(sub, "Firing Squad-CAT28002.pdf")
    assert len(books.scan(tmp_path, REG)["matched"]) == 1


def test_unrecognised_files_are_reported_not_swallowed(tmp_path):
    """A book we do not know is something the user can act on."""
    _pdf(tmp_path, "Some Other Game - Player Handbook.pdf")
    r = books.scan(tmp_path, REG)
    assert not r["matched"]
    assert len(r["unmatched"]) == 1
    assert "not recognised" in r["unmatched"][0]["reason"]


def test_does_not_match_two_files_to_one_book(tmp_path):
    _pdf(tmp_path, "Sixth World Core Rulebook-CAT28000.pdf")
    _pdf(tmp_path, "Sixth World Core Rulebook copy-CAT28000.pdf")
    r = books.scan(tmp_path, REG)
    assert len(r["matched"]) == 1
    assert "duplicate" in r["unmatched"][0]["reason"]


def test_books_you_do_not_own_are_listed_as_missing(tmp_path):
    _pdf(tmp_path, "Firing Squad-CAT28002.pdf")
    r = books.scan(tmp_path, REG)
    assert set(r["missing"]) == {"corebook", "companion"}


def test_empty_folder_is_not_an_error(tmp_path):
    r = books.scan(tmp_path, REG)
    assert r["matched"] == [] and len(r["missing"]) == 3


def test_summary_reads_like_a_sentence(tmp_path):
    _pdf(tmp_path, "Sixth World Core Rulebook-CAT28000.pdf")
    s = books.summary(books.scan(tmp_path, REG))
    assert s.startswith("Found 1 book:")
    assert "Sixth World Core Rulebook" in s


def test_scanning_writes_the_paths_the_pipeline_gates_on(tmp_path):
    """The pipeline only reads a book whose books.json entry points at a file."""
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    f = _pdf(pdfs, "Sixth World Core Rulebook-CAT28000.pdf")
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "data" / "books.json").write_text(json.dumps(REG), encoding="utf-8")

    out = books.apply_to_registry(repo, books.scan(pdfs, REG))
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["corebook"]["pdf"] == str(f)


# ---------- settings ----------

def test_settings_round_trip(tmp_path):
    s = settings.Settings(tmp_path / "settings.json")
    s["pdfFolder"] = r"D:\Books"
    s.save()
    assert settings.Settings(tmp_path / "settings.json")["pdfFolder"] == r"D:\Books"


def test_unreadable_settings_fall_back_to_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert settings.Settings(p)["pdfFolder"] == ""


def test_unknown_keys_survive_a_round_trip(tmp_path):
    """An older build must not discard a newer build's settings."""
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"pdfFolder": "x", "somethingNewer": 42}), encoding="utf-8")
    s = settings.Settings(p)
    s.save()
    assert json.loads(p.read_text(encoding="utf-8"))["somethingNewer"] == 42


def test_save_is_atomic(tmp_path):
    """A crash mid-save must not leave a truncated config."""
    p = tmp_path / "settings.json"
    s = settings.Settings(p)
    s["pdfFolder"] = "x" * 5000
    s.save()
    assert json.loads(p.read_text(encoding="utf-8"))["pdfFolder"] == "x" * 5000
    assert not p.with_suffix(".tmp").exists()


# ---------- publishing ----------

def test_refuses_a_folder_that_is_not_foundry(tmp_path):
    ok, why = publish.check(tmp_path)
    assert not ok and "does not look like" in why


def test_accepts_a_real_looking_data_folder(tmp_path, monkeypatch):
    (tmp_path / "modules").mkdir()
    (tmp_path / "worlds").mkdir()
    monkeypatch.setattr(publish, "foundry_running", lambda: False)
    ok, why = publish.check(tmp_path)
    assert ok, why


def test_refuses_while_foundry_is_running(tmp_path, monkeypatch):
    """Packs are LevelDB and Foundry holds them open; writing over that lock
    can leave a pack unreadable."""
    (tmp_path / "modules").mkdir()
    monkeypatch.setattr(publish, "foundry_running", lambda: True)
    ok, why = publish.check(tmp_path)
    assert not ok and "Close it first" in why


def test_install_keeps_the_previous_catalog_if_the_copy_fails(tmp_path, monkeypatch):
    """A failed publish must leave the working catalog, not nothing."""
    built = tmp_path / "built"
    built.mkdir()
    (built / "module.json").write_text('{"id":"m","version":"2"}', encoding="utf-8")
    data = tmp_path / "Data"
    (data / "modules" / "m").mkdir(parents=True)
    (data / "modules" / "m" / "module.json").write_text('{"id":"m","version":"1"}',
                                                        encoding="utf-8")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(publish.shutil, "copytree", boom)
    with pytest.raises(OSError):
        publish.install(built, data, "m")
    still = json.loads((data / "modules" / "m" / "module.json").read_text(encoding="utf-8"))
    assert still["version"] == "1"


def test_install_replaces_the_module(tmp_path, monkeypatch):
    built = tmp_path / "built"
    built.mkdir()
    (built / "module.json").write_text('{"id":"m","version":"2"}', encoding="utf-8")
    data = tmp_path / "Data"
    (data / "modules").mkdir(parents=True)
    dest = publish.install(built, data, "m")
    assert json.loads((dest / "module.json").read_text(encoding="utf-8"))["version"] == "2"


# ---------- the runner ----------

def test_progress_counts_books_not_invented_percentages():
    p = runner.Progress(total_books=3)
    assert p.fraction == 0
    p.feed("  corebook   commlink6  533 items  +pdf new=0 desc=79")
    p.feed("  companion  commlink6  783 items  +pdf new=12 desc=40")
    assert p.done == 2
    assert 0.6 < p.fraction < 0.7
    assert "companion" in p.label()


def test_progress_ignores_banners_and_totals():
    p = runner.Progress(total_books=2)
    for noise in ("=== importing", "TOTAL items=5", "", "-----"):
        p.feed(noise)
    assert p.done == 0


def test_progress_never_exceeds_the_total():
    p = runner.Progress(total_books=1)
    for _ in range(5):
        p.feed("  corebook  commlink6 1 items +pdf new=0")
    assert p.fraction == 1.0


def test_pipeline_command_from_source_uses_the_interpreter():
    argv = runner.pipeline_command("tools.import_library", ["--apply"])
    assert argv[0] == sys.executable
    assert argv[1:] == ["-m", "tools.import_library", "--apply"]


def test_pipeline_command_frozen_reinvokes_the_exe(monkeypatch):
    """A frozen bundle has no python.exe and no tools/ on disk."""
    monkeypatch.setattr(runner, "is_frozen", lambda: True)
    argv = runner.pipeline_command("tools.import_library", ["--apply"])
    assert argv[1] == runner.WORKER_FLAG
    assert argv[2] == "tools.import_library"


def test_a_job_streams_output_and_reports_its_exit_code():
    job = runner.Job([sys.executable, "-c",
                      "print('one'); print('two')"]).start()
    seen, done = [], False
    for _ in range(400):
        lines, done = job.drain()
        seen += lines
        if done:
            break
        import time
        time.sleep(0.01)
    assert done, "job never finished"
    assert "one" in seen and "two" in seen
    assert job.returncode == 0


def test_a_job_that_cannot_start_reports_it_rather_than_raising():
    job = runner.Job(["this-command-does-not-exist-xyz"]).start()
    for _ in range(200):
        lines, done = job.drain()
        if done:
            break
        import time
        time.sleep(0.01)
    assert job.returncode == 127
