"""Nothing Commlink6 stores about an item may be silently dropped.

This is the guard for a class of bug that bit repeatedly: a field exists in the
jar, the merge does not read it, and the consequence only shows up much later
as free cyberware or an unfittable accessory. Any attribute or child element
that is neither captured nor explicitly excluded fails here.
"""
import json
import pathlib

import pytest

from tools.audit_item_coverage import ATTR_HOME, CHILD_HOME, EXCLUDED, survey

JAR = pathlib.Path(r"C:\Users\johnb\CommLink6\app\stable\commlink6-1.14.0-complete.jar")
CHARGEN = pathlib.Path("export/chargen-data.json")

pytestmark = pytest.mark.skipif(not JAR.exists(), reason="Commlink6 jar not installed")


@pytest.fixture(scope="module")
def seen():
    return survey(JAR)


def test_every_item_attribute_is_accounted_for(seen):
    attrs, _ = seen
    unexplained = [k for k in attrs if k not in ATTR_HOME and k not in EXCLUDED]
    assert not unexplained, (
        f"item attributes neither captured nor excluded: {unexplained}. "
        "Capture them, or add them to EXCLUDED with a reason.")


def test_every_item_child_element_is_accounted_for(seen):
    _, kids = seen
    unexplained = [k for k in kids if k not in CHILD_HOME and k not in EXCLUDED]
    assert not unexplained, (
        f"item child elements neither captured nor excluded: {unexplained}. "
        "Capture them, or add them to EXCLUDED with a reason.")


@pytest.mark.skipif(not CHARGEN.exists(), reason="chargen-data not built")
def test_the_captured_data_is_actually_populated():
    d = json.loads(CHARGEN.read_text(encoding="utf-8"))
    assert len(d["itemMeta"]) > 2000, "itemMeta looks short"
    assert len(d["gearRatings"]) > 200, "gearRatings looks short"
    assert len(d["gearMounts"]) > 1000, "gearMounts looks short"


@pytest.mark.skipif(not CHARGEN.exists(), reason="chargen-data not built")
def test_stat_blocks_are_populated_not_just_present():
    """Field names were guessed once and produced empty blocks that still
    counted as 'captured' — check the contents, not the key."""
    im = json.loads(CHARGEN.read_text(encoding="utf-8"))["itemMeta"]
    counts = {}
    for rec in im.values():
        for block in ("weapon", "armor", "vehicle", "ammo", "matrix", "alchemy"):
            if rec.get(block):
                counts[block] = counts.get(block, 0) + 1
    for block, minimum in (("weapon", 300), ("vehicle", 300), ("armor", 100),
                           ("alchemy", 90), ("ammo", 50), ("matrix", 40)):
        assert counts.get(block, 0) >= minimum, (
            f"{block} stat block populated on only {counts.get(block, 0)} items")


@pytest.mark.skipif(not CHARGEN.exists(), reason="chargen-data not built")
def test_a_known_item_carries_its_full_stat_line():
    im = json.loads(CHARGEN.read_text(encoding="utf-8"))["itemMeta"]
    pred = im["ares_predator_vi"]["weapon"]
    assert pred["dmg"] == "3P"
    assert pred["mode"] == "SA/BF"
    assert pred["ammo"] == "15(c)"
    assert pred["skill"] == "firearms"
    jacket = im["armor_jacket"]["armor"]
    assert jacket["rating"] == "4"
