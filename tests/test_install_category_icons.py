"""The category-icon installer: naming rule, and what it refuses to touch."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.install_category_icons import (          # noqa: E402
    icon_key, main, replaceable, slug_for,
)


def test_icon_key_is_the_file_name():
    assert icon_key("WEAPON_FIREARMS", "PISTOLS_LIGHT") == "weapon_firearms-pistols_light"
    assert icon_key("ARMOR", "ARMOR_BODY") == "armor-armor_body"


def test_a_type_with_no_subtype_drops_the_separator():
    # 'air.png', not 'air-.png' — a trailing dash would match nothing
    assert icon_key("AIR", "") == "air"


def test_slug_matches_what_icon_match_writes():
    # both modules must agree on where a default lives, or the importer
    # re-picks its own icon for a pair that already has one
    assert slug_for("WEAPON_FIREARMS", "PISTOLS_LIGHT") == "weapon_firearms_pistols_light"
    assert slug_for("AIR", "") == "air"


def test_only_placeholders_are_replaceable():
    assert replaceable("")                       # never had art
    assert replaceable("generic/armor_body.svg")  # a shared placeholder
    # art belonging to one item — a name match, a hand-picked icon, or a
    # picture lifted out of a PDF — is off limits
    assert not replaceable("corebook/lib/ares_predator.png")
    assert not replaceable("corebook/art/p42_1.png")


def _library(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    domain = data / "corebook" / "gear"
    domain.mkdir(parents=True)
    (domain / "weapons.json").write_text(json.dumps({"items": [
        {"id": "a", "name": "Plain", "system": {"type": "ARMOR", "subtype": "ARMOR_BODY"}},
        {"id": "b", "name": "Placeheld", "img": "generic/armor_body.svg",
         "system": {"type": "ARMOR", "subtype": "ARMOR_BODY"}},
        {"id": "c", "name": "Hand picked", "img": "corebook/lib/c.png",
         "system": {"type": "ARMOR", "subtype": "ARMOR_BODY"}},
        {"id": "d", "name": "No icon for me", "system": {"type": "PACK", "subtype": "PACK_OTHER"}},
    ]}), encoding="utf-8")
    return data


def _png(path: Path, size=(512, 512)) -> None:
    """A real image — a stub of fake bytes would make Pillow fail and silently
    exercise the copy-verbatim fallback instead of the conversion path."""
    from PIL import Image
    Image.new("RGB", size, (40, 90, 160)).save(path, format="PNG")


def _icons(tmp_path: Path) -> Path:
    icons = tmp_path / "Category Icons"
    icons.mkdir()
    _png(icons / "armor-armor_body.png")
    return icons


def _items(data: Path) -> dict:
    payload = json.loads((data / "corebook" / "gear" / "weapons.json").read_text(encoding="utf-8"))
    return {i["id"]: i.get("img") for i in payload["items"]}


def test_install_fills_placeholders_and_spares_specific_art(tmp_path, capsys):
    data, icons = _library(tmp_path), _icons(tmp_path)
    main_argv = ["--data", str(data), "--icons", str(icons)]
    sys.argv = ["install_category_icons.py", *main_argv]
    assert main() == 0

    got = _items(data)
    assert got["a"] == "generic/armor_armor_body.webp"  # was empty; installed as WebP
    assert got["b"] == "generic/armor_armor_body.webp"  # was a placeholder
    assert got["c"] == "corebook/lib/c.png"             # untouched
    assert got["d"] is None                             # no icon supplied for PACK

    # the icon is copied in, and remembered so the next import reuses it
    assert (data / "_assets" / "generic" / "armor_armor_body.webp").is_file()
    defaults = json.loads((data / "_assets" / "generic" / "defaults.json").read_text(encoding="utf-8"))
    assert defaults["ARMOR/ARMOR_BODY"] == "generic/armor_armor_body.webp"
    assert "PACK - PACK_OTHER" in capsys.readouterr().out   # the gap is reported


def test_critters_and_npcs_are_left_out_of_the_shared_icons(tmp_path, capsys):
    data, icons = _library(tmp_path), _icons(tmp_path)
    domain = data / "corebook" / "critters"
    domain.mkdir(parents=True)
    (domain / "critter.json").write_text(json.dumps({"items": [
        {"id": "bear", "name": "Bear", "system": {"type": "CRITTER", "subtype": ""}},
    ]}), encoding="utf-8")
    # an icon file that WOULD match, to prove the exclusion is by type and not
    # merely by the absence of art
    (icons / "critter.png").write_bytes(b"\x89PNG would-be critter icon")

    sys.argv = ["install_category_icons.py", "--data", str(data), "--icons", str(icons)]
    assert main() == 0

    payload = json.loads((domain / "critter.json").read_text(encoding="utf-8"))
    assert payload["items"][0].get("img") is None          # still waiting for its portrait
    defaults = json.loads((data / "_assets" / "generic" / "defaults.json").read_text(encoding="utf-8"))
    assert "CRITTER/" not in defaults
    out = capsys.readouterr().out
    assert "1 items excluded" in out
    assert "CRITTER - " not in out                          # not reported as a gap either


def test_dry_run_writes_nothing(tmp_path):
    data, icons = _library(tmp_path), _icons(tmp_path)
    sys.argv = ["install_category_icons.py", "--data", str(data), "--icons", str(icons), "--dry-run"]
    assert main() == 0
    assert _items(data)["a"] is None
    assert not (data / "_assets" / "generic").exists()
