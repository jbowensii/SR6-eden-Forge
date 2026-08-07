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
    p.feed("[1/3] corebook done  commlink6 533 items  +pdf new=0 desc=79")
    p.feed("[2/3] companion done  commlink6 783 items  +pdf new=12 desc=40")
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
        p.feed("[1/1] corebook done  commlink6 1 items +pdf new=0")
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


# ---------- the entry point ----------

def test_entry_uses_absolute_imports_only():
    """A frozen entry script has no package context.

    PyInstaller runs __main__.py as `__main__`, so `from .app import ...`
    raises "attempted relative import with no known parent package" — and only
    in the packaged build, which is the worst place to discover it. This is a
    source check because the failure cannot be reproduced from source, where
    the module IS reached as catalog_builder.__main__.
    """
    src = (Path(__file__).resolve().parent.parent
           / "build" / "catalog_builder" / "__main__.py").read_text(encoding="utf-8")
    offenders = [ln.strip() for ln in src.splitlines()
                 if ln.strip().startswith("from .") or ln.strip().startswith("import .")]
    assert not offenders, f"relative import in the frozen entry point: {offenders}"


def test_app_module_avoids_relative_imports_too():
    src = (Path(__file__).resolve().parent.parent
           / "build" / "catalog_builder" / "app.py").read_text(encoding="utf-8")
    offenders = [ln.strip() for ln in src.splitlines()
                 if ln.strip().startswith("from . import")
                 or ln.strip().startswith("from .runner")
                 or ln.strip().startswith("from .settings")]
    assert not offenders, f"relative import in app.py: {offenders}"


def test_entry_can_load_the_window_module():
    from catalog_builder.__main__ import _load_app
    assert _load_app().__name__.endswith("catalog_builder.app")


# ---------- the workspace ----------

def test_workspace_folders_are_created_not_asked_about(tmp_path):
    """icons/ and art/ have exactly one sensible location, so asking would be
    noise. They are made under the workspace with a note saying what each is."""
    ws = tmp_path / "SR6 Catalog"
    settings.ensure_workspace(ws)
    made = {p.name for p in ws.iterdir()}
    assert {"data", "export", "icons", "art", "_ids"} <= made
    assert "icon sets" in (ws / "icons" / "README.txt").read_text(encoding="utf-8")


def test_ensuring_the_workspace_twice_changes_nothing(tmp_path):
    ws = tmp_path / "ws"
    settings.ensure_workspace(ws)
    (ws / "icons" / "mine.svg").write_text("x", encoding="utf-8")
    settings.ensure_workspace(ws)
    assert (ws / "icons" / "mine.svg").exists(), "existing work must be untouched"


# ---------- the books stay where the user put them ----------

def test_the_builder_never_writes_to_the_pdf_folder(tmp_path):
    """Scanning must be strictly read-only. The library is the user's, it is
    large, and it is irreplaceable."""
    pdfs = tmp_path / "books"
    pdfs.mkdir()
    f = _pdf(pdfs, "Sixth World Core Rulebook-CAT28000.pdf")
    before = {p: (p.stat().st_mtime, p.stat().st_size) for p in pdfs.rglob("*")}

    books.scan(pdfs, REG)

    after = {p: (p.stat().st_mtime, p.stat().st_size) for p in pdfs.rglob("*")}
    assert before == after, "scanning modified the PDF folder"
    assert f.exists()


def test_the_build_refuses_to_ship_pdfs(tmp_path):
    """A structural guarantee, not a promise: the release build fails outright
    if a PDF reaches the freeze."""
    import importlib.util as iu
    spec = iu.spec_from_file_location(
        "br", Path(__file__).resolve().parent.parent / "build" / "build_release.py")
    br = iu.module_from_spec(spec)
    spec.loader.exec_module(br)

    clean = tmp_path / "app"
    clean.mkdir()
    br.assert_no_books(clean)                       # nothing there: fine

    (clean / "Some Book.pdf").write_bytes(b"%PDF-1.4")
    with pytest.raises(SystemExit) as e:
        br.assert_no_books(clean)
    assert "REFUSING TO BUILD" in str(e.value)


# ---------- the icon ----------

def test_icon_entries_are_bmp_not_png():
    """Windows only renders a PNG-format icon entry at 256x256.

    Below that the shell needs BMP (DIB). Pillow's default ICO save writes
    every entry PNG-compressed, which produces a file that embeds cleanly,
    reports the right dimensions, and draws as nothing — the exe has an icon
    resource the shell cannot decode. That is exactly how the installer
    shipped twice with no visible icon.
    """
    import struct

    ico = Path(__file__).resolve().parent.parent / "build" / "wizard" / "app.ico"
    if not ico.is_file():
        pytest.skip("icon not built")
    data = ico.read_bytes()
    _, _, count = struct.unpack("<HHH", data[:6])
    assert count >= 5, "too few sizes for the shell to choose from"

    bad = []
    for i in range(count):
        off = 6 + i * 16
        w, h, _, _, _, _, _, doff = struct.unpack("<BBBBHHII", data[off:off + 16])
        w = w or 256
        is_png = data[doff:doff + 8] == b"\x89PNG\r\n\x1a\n"
        if is_png and w < 256:
            bad.append(w)
    assert not bad, f"PNG-format entries the shell cannot draw at: {bad}"


def test_icon_includes_the_sizes_windows_asks_for():
    import struct

    ico = Path(__file__).resolve().parent.parent / "build" / "wizard" / "app.ico"
    if not ico.is_file():
        pytest.skip("icon not built")
    data = ico.read_bytes()
    _, _, count = struct.unpack("<HHH", data[:6])
    sizes = set()
    for i in range(count):
        w = struct.unpack("<B", data[6 + i * 16:7 + i * 16])[0] or 256
        sizes.add(w)
    # 16 for the title bar and Explorer list, 32 for the desktop, 256 for large
    assert {16, 32, 48, 256} <= sizes, f"missing sizes: {sizes}"


# ---------- Commlink6 acquisition ----------

def test_finds_an_installed_commlink6(tmp_path, monkeypatch):
    from catalog_builder import commlink6
    root = tmp_path / "CommLink6" / "app"
    root.mkdir(parents=True)
    jar = root / "commlink6-1.14.0-complete.jar"
    jar.write_bytes(b"PK\x03\x04")
    monkeypatch.setattr(commlink6.Path, "home", staticmethod(lambda: tmp_path))
    assert commlink6.find_local() == jar


def test_prefers_the_newest_jar_when_several_are_installed(tmp_path, monkeypatch):
    import os
    import time
    from catalog_builder import commlink6
    root = tmp_path / "CommLink6" / "app"
    root.mkdir(parents=True)
    old = root / "commlink6-1.12.0-complete.jar"
    new = root / "commlink6-1.14.0-complete.jar"
    for f in (old, new):
        f.write_bytes(b"PK\x03\x04")
    os.utime(old, (time.time() - 9000, time.time() - 9000))
    monkeypatch.setattr(commlink6.Path, "home", staticmethod(lambda: tmp_path))
    assert commlink6.find_local() == new


def test_rejects_a_jar_that_is_not_commlink6(tmp_path):
    """Checked by looking for the data tree, not the filename — so a truncated
    download is caught here rather than halfway through an import."""
    from catalog_builder import commlink6
    import zipfile
    jar = tmp_path / "commlink6-fake.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("hello.txt", "not shadowrun")
    ok, why = commlink6.validate(jar)
    assert not ok and "Commlink6" in why


def test_rejects_a_file_that_is_not_a_zip(tmp_path):
    from catalog_builder import commlink6
    bad = tmp_path / "commlink6-truncated.jar"
    bad.write_bytes(b"not a zip at all")
    ok, why = commlink6.validate(bad)
    assert not ok and "zip" in why.lower()


def test_the_notice_names_the_author_and_says_it_is_optional():
    """It is someone else's software under their terms, and the user should
    know that before we send them to fetch it."""
    from catalog_builder import commlink6
    assert "Stefan Prelle" in commlink6.NOTICE
    assert "optional" in commlink6.NOTICE.lower()
    assert "rpgframework.de" in commlink6.NOTICE


# ---------- the registry must ship ----------

def test_registry_is_bundled_with_the_application():
    """Without it nothing can be recognised and every folder reads as
    "No Shadowrun books found" — which blames the user's folder for a missing
    data file. That is exactly how the first installed build behaved."""
    bundled = (Path(__file__).resolve().parent.parent
               / "build" / "catalog_builder" / "books.json")
    assert bundled.is_file(), "the book registry is not shipped with the app"
    reg = json.loads(bundled.read_text(encoding="utf-8"))
    assert len(reg) >= 40, f"registry looks truncated: {len(reg)} books"
    assert reg["corebook"]["cat"] == "CAT28000"


def test_bundled_registry_carries_no_machine_paths():
    """PDF paths are per-machine and would be meaningless — or misleading — on
    someone else's computer."""
    bundled = (Path(__file__).resolve().parent.parent
               / "build" / "catalog_builder" / "books.json")
    if not bundled.is_file():
        pytest.skip("registry not built")
    reg = json.loads(bundled.read_text(encoding="utf-8"))
    leaked = [k for k, v in reg.items() if v.get("pdf")]
    assert not leaked, f"machine-specific paths in the shipped registry: {leaked[:3]}"


def test_registry_loads_without_a_repo():
    """The installed app has no repo beside it — only the bundled copy."""
    reg = books.load_registry(Path("/definitely/not/a/repo"))
    assert len(reg) >= 40, "fell back to an empty registry"


def test_progress_moves_while_a_book_is_being_read():
    """The label must move on the START marker, not only on the finish.

    Regression: the import printed its per-book line with end="" *before* the
    slow PDF pass, so the terminating newline only arrived once the book was
    done. A line-oriented reader saw nothing for minutes at a time and the
    import looked hung.
    """
    from build.catalog_builder.runner import Progress

    p = Progress(3)

    p.feed("[1/3] corebook reading")
    assert p.current == "corebook"
    assert p.phase == "reading"
    assert p.done == 0                      # started is not finished

    p.feed("[1/3] corebook done  commlink6 533 items  +pdf new=0 desc=79")
    assert p.done == 1
    assert p.fraction == 1 / 3

    p.feed("[2/3] street_grimoire reading")
    assert p.current == "street_grimoire"
    assert p.done == 1                      # bar holds until this one lands

    p.feed("[3/3] firing_squad done  pdf-only  +pdf new=12 desc=3")
    assert p.done == 3
    assert p.fraction == 1.0


def test_progress_defers_to_the_pipeline_total():
    """The scan counts matched books; the pipeline counts what it will read."""
    from build.catalog_builder.runner import Progress

    p = Progress(50)                        # what the folder scan matched
    p.feed("[1/12] corebook reading")       # what is actually importable
    assert p.total == 12


def test_progress_ignores_ordinary_chatter():
    from build.catalog_builder.runner import Progress

    p = Progress(2)
    for noise in ("book                   source  commlink6",
                  "  corebook   both    core", "", "=== importing 2 book(s)",
                  "Could not get FontBBox from font descriptor because None"):
        p.feed(noise)
    assert p.done == 0 and p.current == ""
    assert p.label() == "starting"


def test_pdf_noise_is_silenced():
    """FontBBox warnings are pdfminer telling us about an optional field."""
    import logging

    from extractor.quiet import quiet_pdf_noise

    logging.getLogger("pdfminer.pdffont").setLevel(logging.WARNING)
    quiet_pdf_noise()
    assert logging.getLogger("pdfminer.pdffont").level == logging.ERROR
    assert logging.getLogger("pdfminer").level == logging.ERROR
