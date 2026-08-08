"""The ownership-gated import, and the two silent failures it shipped with.

Both bugs here were invisible: the import printed a success line and a totals
row while doing nothing at all. Neither would have survived a test that looked
at the RESULT rather than the exit code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import import_library


class _Rec(dict):
    pass


def test_import_commlink6_reports_failures_instead_of_swallowing(tmp_path, monkeypatch):
    """The bug: to_item returns THREE values and the caller unpacked two.

    Every record raised ValueError into a bare `except Exception: continue`,
    so a book with 45 Commlink6 records imported 0 of them and still reported
    success. Commlink6 is the authority in this pipeline, so this quietly
    emptied the half of the library that matters most.
    """
    monkeypatch.setattr(import_library, "read_book",
                        lambda b, j: {"a": _Rec(), "b": _Rec(), "c": _Rec()})

    def boom(rec, jar_book):
        raise ValueError("too many values to unpack (expected 2, got 3)")

    monkeypatch.setattr(import_library, "to_item", boom)

    st = import_library.import_commlink6(tmp_path, "astral_ways", "astral_ways",
                                         Path("nope.jar"))
    assert st["jarItems"] == 0
    assert st["read"] == 3
    # the whole point: the failure is COUNTED and named, not discarded
    assert sum(st["failures"].values()) == 3
    assert "too many values to unpack" in "".join(st["failures"])


def test_import_commlink6_files_records_by_domain(tmp_path, monkeypatch):
    """One book's records do not all belong to the same library file."""
    monkeypatch.setattr(import_library, "read_book",
                        lambda b, j: {"1": _Rec(), "2": _Rec(), "3": _Rec()})

    out = iter([("gear", "electronics", {"id": "a", "name": "Commlink"}),
                ("gear", "weapons_firearms", {"id": "b", "name": "Pistol"}),
                ("spells", "combat", {"id": "c", "name": "Manabolt"})])
    monkeypatch.setattr(import_library, "to_item", lambda rec, jb: next(out))

    st = import_library.import_commlink6(tmp_path, "corebook", "core",
                                         Path("nope.jar"))
    assert st["jarItems"] == 3
    assert st["failures"] == {}
    assert st["domains"] == ["gear", "spells"]

    lib = tmp_path / import_library.LIBRARY
    assert json.loads((lib / "gear" / "electronics.json").read_text(
        encoding="utf-8"))["items"][0]["name"] == "Commlink"
    assert json.loads((lib / "spells" / "combat.json").read_text(
        encoding="utf-8"))["items"][0]["name"] == "Manabolt"


def test_commlink6_rows_are_stamped_as_commlink6(tmp_path, monkeypatch):
    """Provenance is what lets the PDF pass fill gaps without overwriting."""
    monkeypatch.setattr(import_library, "read_book", lambda b, j: {"1": _Rec()})
    monkeypatch.setattr(import_library, "to_item",
                        lambda rec, jb: ("gear", "electronics", {"id": "a"}))

    import_library.import_commlink6(tmp_path, "corebook", "core", Path("x.jar"))
    item = json.loads((tmp_path / import_library.LIBRARY / "gear" /
                       "electronics.json").read_text(encoding="utf-8"))["items"][0]
    assert item["meta"]["source"] == "commlink6"
    assert item["meta"]["book"] == "corebook"


def test_reimporting_a_book_replaces_its_rows_rather_than_doubling_them(
        tmp_path, monkeypatch):
    monkeypatch.setattr(import_library, "read_book", lambda b, j: {"1": _Rec()})
    monkeypatch.setattr(import_library, "to_item",
                        lambda rec, jb: ("gear", "electronics", {"id": "a"}))

    for _ in range(3):
        import_library.import_commlink6(tmp_path, "corebook", "core",
                                        Path("x.jar"))
    items = json.loads((tmp_path / import_library.LIBRARY / "gear" /
                        "electronics.json").read_text(encoding="utf-8"))["items"]
    assert len(items) == 1


# ---------- what the installer has to carry ----------

ISS = Path(__file__).resolve().parent.parent / "build" / "installer.iss"


def test_installer_ships_what_the_review_app_needs_to_run():
    """The installed "Review & correct" died on: Cannot find package 'express'.

    site/dist and site/node_modules were both excluded, so the server had no
    dependencies and no front end to serve. server/index.mjs does
    express.static(../dist) — neither is optional.
    """
    iss = ISS.read_text(encoding="utf-8")
    site_line = next(ln for ln in iss.splitlines()
                     if r'Source: "..\site\*"' in ln)
    block = iss[iss.index(site_line):iss.index(site_line) + 400]

    assert r"dist\*" not in block, "the built front end is excluded again"
    assert r"work\site-deps\node_modules\*" in iss, \
        "the review app's runtime packages are not being shipped"


def test_installer_still_excludes_the_dev_tree():
    """Ship production packages, not vite and react's dev tooling."""
    iss = ISS.read_text(encoding="utf-8")
    assert r"node_modules\*,*.log" in iss
    assert "--omit=dev" in (
        Path(__file__).resolve().parent.parent / "build" / "build_release.py"
    ).read_text(encoding="utf-8")



class _FakeProc:
    """Enough of Popen for run_post_phases: a readable stdout and a code."""

    def __init__(self, returncode=0, lines=()):
        self.returncode = returncode
        self.stdout = iter(lines)

    def wait(self):
        return self.returncode


def _capture_popen(monkeypatch, seen, returncode=0, lines=()):
    import subprocess

    def fake(argv, cwd=None, env=None, **kw):
        seen["argv"] = argv
        seen["cwd"] = cwd
        seen["env"] = env or {}
        return _FakeProc(returncode, lines)

    monkeypatch.setattr(subprocess, "Popen", fake)


# ---------- the two rules the pipeline exists to enforce ----------

def test_merge_commlink6_is_never_run_as_a_phase():
    """PDF ownership gates Commlink6 data, so the wholesale merge is banned.

    tools/merge_commlink6.py imports Commlink6 for every book it covers,
    whether or not the PDF is present. That is precisely the rule this
    pipeline exists to enforce — "if you do not have the PDF you do NOT import
    that data from Commlink6" — so the gated per-book import_commlink6() is
    used instead, driven by the ownership plan.
    """
    scripts = [s for _label, s, _args in
               import_library.POST_PHASES + import_library.GRAPHICS_PHASES]
    assert "merge_commlink6.py" not in scripts


def test_corrections_are_not_a_post_phase():
    """They must run AFTER the Commlink6 guard, not inside the guarded block.

    The precedence chain is: your correction > Commlink6 > anything inferred.
    Run inside POST_PHASES, the guard would fire afterwards and restore the
    Commlink6 value straight over a manual edit — defending the authority from
    the one source meant to outrank it.
    """
    scripts = [s for _label, s, _args in import_library.POST_PHASES]
    assert "apply_corrections.py" not in scripts
    assert import_library.CORRECTIONS_PHASE[1] == "apply_corrections.py"


def test_descriptions_run_before_subtype_inference():
    """Subtype inference reads descriptions; reversed, it has nothing to read."""
    scripts = [s for _label, s, _args in import_library.POST_PHASES]
    assert scripts.index("rebuild_descriptions.py") < \
        scripts.index("infer_gear_subtypes.py")


def test_post_phases_pin_both_the_cwd_and_the_data_root(tmp_path, monkeypatch):
    """Some phases resolve data/ against the cwd, others against the repo.

    Pinning only one of them rebuilt the developer's copy instead of the
    user's workspace — silently, because both paths exist on a dev machine.
    """
    seen = {}
    _capture_popen(monkeypatch, seen)

    data = tmp_path / "ws" / "data"
    data.mkdir(parents=True)
    # a phase that exists on disk, so it is not skipped
    import_library.run_post_phases(
        data, [("x", "apply_corrections.py", [])], on_line=lambda _s: None)

    assert seen["env"]["SR6_DATA"] == str(data)
    assert seen["cwd"] == str(data.parent)


def test_a_failing_phase_is_reported_not_swallowed(tmp_path, monkeypatch):
    seen = {}
    _capture_popen(monkeypatch, seen, returncode=2)

    data = tmp_path / "data"
    data.mkdir()
    lines = []
    failed = import_library.run_post_phases(
        data, [("x", "apply_corrections.py", [])], on_line=lines.append)

    assert failed == ["apply_corrections.py"]
    assert any("exited 2" in ln for ln in lines)


def test_the_workspace_owns_a_corrections_folder():
    """Web-app edits land in the workspace, so the folder is part of it."""
    from build.catalog_builder.settings import WORKSPACE_DIRS, ensure_workspace

    assert "_corrections" in WORKSPACE_DIRS

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        ws = ensure_workspace(Path(d) / "ws")
        assert (ws / "_corrections").is_dir()


def test_the_review_app_is_told_where_the_library_is():
    """Installed, the app's own data/ does not exist.

    Without SR6_DATA the review app opened on an empty library and recorded
    every edit into the installation directory, where the import would never
    look for them.
    """
    src = (Path(__file__).resolve().parent.parent
           / "site" / "server" / "index.mjs").read_text(encoding="utf-8")
    assert "process.env.SR6_DATA" in src

    app = (Path(__file__).resolve().parent.parent
           / "build" / "catalog_builder" / "app.py").read_text(encoding="utf-8")
    # passed to the node process that serves the review app
    assert '"SR6_DATA": str(ws / "data")' in app


def test_the_build_resolves_npm_rather_than_calling_it_bare():
    """On Windows npm is npm.cmd and CreateProcess ignores PATHEXT.

    A bare ["npm", ...] raises FileNotFoundError even with npm plainly on the
    PATH, which is how the review-app build step failed the first time it was
    actually run.
    """
    src = (Path(__file__).resolve().parent.parent
           / "build" / "build_release.py").read_text(encoding="utf-8")
    assert 'shutil.which("npm")' in src
    assert '["npm"' not in src and "['npm'" not in src


def test_frozen_builds_never_hand_a_script_path_to_the_exe(tmp_path, monkeypatch):
    """The fork bomb: sys.executable is the GUI exe, not python.

    Handing SR6CatalogBuilder.exe "-u somescript.py" does not run the script.
    The exe does not recognise those arguments, falls through to its entry
    point and opens ANOTHER COPY OF THE WINDOW — sixteen phases meant sixteen
    windows and sixteen phases that silently did nothing. Invisible from the
    repo, where sys.executable really is python.
    """
    seen = {}
    _capture_popen(monkeypatch, seen)
    monkeypatch.setattr(import_library.sys, "frozen", True, raising=False)

    data = tmp_path / "ws" / "data"
    data.mkdir(parents=True)
    import_library.run_post_phases(
        data, [("x", "apply_corrections.py", ["--apply"])],
        on_line=lambda _s: None)

    argv = seen["argv"]
    assert "--run-pipeline" in argv
    assert "tools.apply_corrections" in argv
    assert not any(str(a).endswith(".py") for a in argv), \
        "a frozen build must not be given a script path"
    assert "--apply" in argv


def test_source_runs_still_call_the_script_directly(tmp_path, monkeypatch):
    seen = {}
    _capture_popen(monkeypatch, seen)
    monkeypatch.setattr(import_library.sys, "frozen", False, raising=False)

    data = tmp_path / "ws" / "data"
    data.mkdir(parents=True)
    import_library.run_post_phases(
        data, [("x", "apply_corrections.py", [])], on_line=lambda _s: None)

    assert any(str(a).endswith("apply_corrections.py") for a in seen["argv"])
    assert "--run-pipeline" not in seen["argv"]


def test_a_script_without_main_is_not_reported_as_broken():
    """Most phases do their work at import; no main() is normal, not a failure."""
    src = (Path(__file__).resolve().parent.parent / "build" / "catalog_builder"
           / "__main__.py").read_text(encoding="utf-8")
    assert "has no main()" not in src, \
        "importing a top-level script must count as having run it"


# ---------- the frozen build, exercised for real ----------
#
# The unit tests above assert the COMMAND SHAPE with sys.frozen faked. That is
# the root cause and worth pinning, but the bug itself only ever appeared in a
# real bundle: from the repo sys.executable is python.exe and the old command
# line was perfectly correct. So this runs a phase through an actual frozen exe
# and checks the two things that went wrong — did it do the work, and did it
# open a window.

def _staged_frozen_exe():
    """The exe THIS repo just built, with the pipeline staged beside it.

    Deliberately not the installed copy: that is whatever the user last
    installed, so the test would pass or fail on someone else's build. The
    installer places tools/ and extractor/ next to the exe, and the frozen
    entry point adds its own directory to sys.path, so the layout is
    reproduced here with directory junctions — instant, where copying the
    156 MB bundle per run would not be.

    :returns: ``(exe, [things to remove afterwards])``, or ``(None, [])``.
    """
    import subprocess as sp

    root = Path(__file__).resolve().parent.parent
    base = root / "build" / "dist" / "SR6CatalogBuilder"
    exe = base / "SR6CatalogBuilder.exe"
    if not exe.is_file():
        return None, []

    made = []
    for name in ("tools", "extractor", "schemas"):
        link = base / name
        if link.exists():
            continue
        r = sp.run(["cmd", "/c", "mklink", "/J", str(link), str(root / name)],
                   capture_output=True, text=True)
        if r.returncode != 0:
            for m in made:
                sp.run(["cmd", "/c", "rmdir", str(m)], capture_output=True)
            return None, []
        made.append(link)
    return exe, made


def _sr6_processes():
    import subprocess as sp
    out = sp.run(["powershell", "-NoProfile", "-Command",
                  "@(Get-Process SR6CatalogBuilder -ErrorAction SilentlyContinue).Count"],
                 capture_output=True, text=True)
    try:
        return int((out.stdout or "0").strip())
    except ValueError:
        return 0


def test_a_frozen_phase_runs_its_work_and_opens_no_window(tmp_path):
    """Regression: sixteen phases opened sixteen windows and did nothing.

    sys.executable in a bundle is SR6CatalogBuilder.exe. Handing it
    "-u somescript.py" does not run the script — the exe ignores arguments it
    does not recognise, falls through to its entry point, and shows the GUI.
    """
    exe, staged = _staged_frozen_exe()
    if exe is None:
        pytest.skip("no frozen build in build/dist — run build_release.py first")

    data = tmp_path / "data"
    (data / "corebook" / "gear").mkdir(parents=True)
    (data / "_corrections" / "gear").mkdir(parents=True)
    (data / "corebook" / "gear" / "electronics.json").write_text(json.dumps({
        "book": "corebook", "domain": "gear", "category": "electronics",
        "items": [{"id": "w", "name": "Widget",
                   "system": {"description": "ORIGINAL"},
                   "meta": {"book": "corebook", "source": "pdf",
                            "qaStatus": "extracted"}}]}), encoding="utf-8")
    (data / "_corrections" / "gear" / "w.json").write_text(json.dumps({
        "domain": "gear", "category": "electronics", "id": "w",
        "correctedAt": "2026-08-07T00:00:00Z", "name": "Widget",
        "system": {"description": "CORRECTED"}, "qaStatus": "reviewed"}),
        encoding="utf-8")

    import os
    import subprocess as sp

    before = _sr6_processes()
    try:
        r = sp.run([str(exe), "--run-pipeline", "tools.apply_corrections",
                    "--apply"],
                   cwd=str(tmp_path), capture_output=True, text=True,
                   timeout=180, env={**os.environ, "SR6_DATA": str(data)})
    finally:
        for link in staged:
            sp.run(["cmd", "/c", "rmdir", str(link)], capture_output=True)
    after = _sr6_processes()

    assert r.returncode == 0, r.stdout + r.stderr
    # it did the work
    got = json.loads((data / "corebook" / "gear" / "electronics.json")
                     .read_text(encoding="utf-8"))
    assert got["items"][0]["system"]["description"] == "CORRECTED"
    # and it did not spawn another copy of the app
    assert after <= before, f"a phase spawned {after - before} extra process(es)"


def test_the_description_phase_reports_progress_the_builder_understands():
    """Twenty silent minutes reads as a hang.

    The phase printed "<book> processed N", which the progress parser ignored,
    so the longest step in the import showed nothing at all. It emits the
    "scanned <book>  (k/N)" form the label already knows.
    """
    src = (Path(__file__).resolve().parent.parent
           / "tools" / "rebuild_descriptions.py").read_text(encoding="utf-8")
    assert 'print(f"scanned {r.get(' in src
    assert "processed {len(entries)}" not in src, "the ignored form is back"


def test_the_description_phase_scans_in_parallel_and_is_spawn_safe():
    src = (Path(__file__).resolve().parent.parent
           / "tools" / "rebuild_descriptions.py").read_text(encoding="utf-8")
    assert "map_jobs(scan_book" in src
    # spawn re-imports the main module; without the guard every child restarts
    # the whole phase
    assert 'if __name__ == "__main__":' in src
    assert "freeze_support()" in src


def test_the_worker_target_lives_in_a_module_not_the_script():
    """A target defined in a script makes every spawned child re-run it."""
    from extractor import writeup_scan

    assert callable(writeup_scan.scan_book)
    assert writeup_scan.scan_book.__module__ == "extractor.writeup_scan"


def test_phase_output_reaches_the_log(tmp_path, monkeypatch):
    """Not one line of any phase's output appeared in the window.

    The phases print per book and per domain; the log showed only the headings
    run_post_phases writes itself. A frozen build starts each phase as a fresh
    copy of the exe with no console, so an inherited stdout handle goes
    nowhere — and printing to a dead handle can kill the phase outright.
    """
    seen = {}
    _capture_popen(monkeypatch, seen,
                   lines=["scanned companion  (1/50)\n",
                          "contacts           +114 new, 4 refs\n"])

    data = tmp_path / "ws" / "data"
    data.mkdir(parents=True)
    lines = []
    import_library.run_post_phases(
        data, [("x", "apply_corrections.py", [])], on_line=lines.append)

    assert any("scanned companion" in ln for ln in lines)
    assert any("+114 new" in ln for ln in lines)
