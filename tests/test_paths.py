"""Which library the tools resolve to, and in what order.

Getting this wrong is quiet and expensive: a tool pointed at the developer's
scratch ``<repo>/data`` reports perfectly plausible numbers, writes nothing the
user can see, and — in the case of the backup tool — announces success while
protecting the wrong tree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from extractor import paths                       # noqa: E402
from extractor.paths import REPO, data_root       # noqa: E402


def _recorded(tmp_path, monkeypatch, workspace: Path | str) -> Path:
    """Stand up an APPDATA holding the builder's settings.json."""
    appdata = tmp_path / "AppData"
    config = appdata / "SR6CatalogBuilder"
    config.mkdir(parents=True)
    (config / "settings.json").write_text(
        json.dumps({"workspace": str(workspace)}), encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("SR6_DATA", raising=False)
    return appdata


def test_explicit_data_wins_over_everything(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "data").mkdir(parents=True)
    _recorded(tmp_path, monkeypatch, ws)
    monkeypatch.setenv("SR6_DATA", str(tmp_path / "from-env"))
    assert data_root(["--data", str(tmp_path / "explicit")]) == tmp_path / "explicit"
    assert data_root([f"--data={tmp_path / 'explicit'}"]) == tmp_path / "explicit"


def test_env_wins_over_the_recorded_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / "data").mkdir(parents=True)
    _recorded(tmp_path, monkeypatch, ws)
    monkeypatch.setenv("SR6_DATA", str(tmp_path / "from-env"))
    assert data_root([]) == tmp_path / "from-env"


def test_the_builders_workspace_beats_the_repo_scratch_copy(tmp_path, monkeypatch):
    # the whole point: with the builder installed, its library is THE library
    ws = tmp_path / "SR6 Catalog"
    (ws / "data").mkdir(parents=True)
    _recorded(tmp_path, monkeypatch, ws)
    assert data_root([]) == ws / "data"


def test_a_recorded_workspace_that_is_not_there_is_ignored(tmp_path, monkeypatch):
    # an uninstalled or moved workspace must not send tools somewhere that
    # does not exist — fall through to the developer default instead
    _recorded(tmp_path, monkeypatch, tmp_path / "gone")
    assert data_root([]) == REPO / "data"


def test_no_builder_settings_falls_back_to_the_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "empty"))
    monkeypatch.delenv("SR6_DATA", raising=False)
    assert data_root([]) == REPO / "data"


def test_unreadable_builder_settings_is_not_fatal(tmp_path, monkeypatch):
    appdata = tmp_path / "AppData"
    config = appdata / "SR6CatalogBuilder"
    config.mkdir(parents=True)
    (config / "settings.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("SR6_DATA", raising=False)
    assert paths.builder_workspace() is None
    assert data_root([]) == REPO / "data"
