"""Restoring artwork the library points at but does not have."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.repair_missing_art import find, main, missing_art   # noqa: E402


def _library(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    domain = data / "corebook" / "critters"
    domain.mkdir(parents=True)
    (domain / "critter.json").write_text(json.dumps({"items": [
        {"id": "a", "name": "Bear", "img": "body_shop/bear.jpg"},
        {"id": "b", "name": "Wolf", "img": "body_shop/wolf.jpg"},
        {"id": "c", "name": "Present", "img": "here/ok.png"},
        {"id": "d", "name": "No art at all"},
    ]}), encoding="utf-8")
    present = data / "_assets" / "here"
    present.mkdir(parents=True)
    (present / "ok.png").write_bytes(b"already here")
    return data


def test_missing_art_finds_only_dangling_paths(tmp_path):
    data = _library(tmp_path)
    assert set(missing_art(data)) == {"body_shop/bear.jpg", "body_shop/wolf.jpg"}


def test_restores_from_another_assets_tree(tmp_path, capsys):
    data = _library(tmp_path)
    other = tmp_path / "other_assets" / "body_shop"
    other.mkdir(parents=True)
    (other / "bear.jpg").write_bytes(b"a bear")

    sys.argv = ["repair_missing_art.py", "--data", str(data), "--only-from",
                "--from", str(tmp_path / "other_assets")]
    assert main() == 0

    assert (data / "_assets" / "body_shop" / "bear.jpg").read_bytes() == b"a bear"
    # the recorded path is left exactly as it was — the file was missing, not wrong
    items = json.loads((data / "corebook" / "critters" / "critter.json").read_text(encoding="utf-8"))["items"]
    assert items[0]["img"] == "body_shop/bear.jpg"
    assert "1 could not be found" in capsys.readouterr().out   # the wolf


def test_a_name_that_matches_two_files_is_not_guessed(tmp_path):
    root = tmp_path / "assets"
    for sub in ("one", "two"):
        (root / sub).mkdir(parents=True)
        (root / sub / "bear.jpg").write_bytes(sub.encode())
    # same name in two places and no exact relative path -> refuse to choose
    assert find("body_shop/bear.jpg", [root],
                {root: {"bear.jpg": [root / "one" / "bear.jpg", root / "two" / "bear.jpg"]}}) is None


def test_exact_relative_path_beats_a_name_match(tmp_path):
    root = tmp_path / "assets"
    (root / "body_shop").mkdir(parents=True)
    exact = root / "body_shop" / "bear.jpg"
    exact.write_bytes(b"right one")
    (root / "elsewhere").mkdir()
    (root / "elsewhere" / "bear.jpg").write_bytes(b"wrong one")
    assert find("body_shop/bear.jpg", [root], {root: {"bear.jpg": [root / "elsewhere" / "bear.jpg"]}}) == exact


def test_clear_unfound_drops_the_broken_reference(tmp_path):
    data = _library(tmp_path)
    # --only-from with no roots: nothing is searched, so both are unfindable
    sys.argv = ["repair_missing_art.py", "--data", str(data), "--only-from", "--clear-unfound"]
    assert main() == 0
    items = {i["id"]: i for i in json.loads(
        (data / "corebook" / "critters" / "critter.json").read_text(encoding="utf-8"))["items"]}
    assert "img" not in items["a"] and "img" not in items["b"]
    assert items["c"]["img"] == "here/ok.png"        # the one that was fine is untouched
