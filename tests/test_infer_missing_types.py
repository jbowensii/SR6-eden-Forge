"""Classifying the items that arrive with no type or subtype."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.infer_missing_types import (      # noqa: E402
    adept_subtype, classify, contact_subtype, focus_subtype, main, martial_subtype,
)


def _item(name="", desc="", notes=""):
    return {"name": name, "system": {"description": desc, "notes": notes}}


def test_a_stated_category_beats_the_keywords():
    # the books print "Category: Striking" for some techniques; when they do,
    # that wins over whatever words happen to appear in the prose
    it = _item("Ballestra", "Category: Striking may only be used with bladed weapons")
    assert martial_subtype(it) == "STRIKING"


def test_keywords_carry_the_entries_that_state_nothing():
    assert martial_subtype(_item("Baton Lock", "apply a joint lock to trap the arm")) == "GRAPPLING"
    assert martial_subtype(_item("Quickdraw", "a thrown blade at close range")) == "RANGED"


def test_weapon_is_the_last_resort_not_the_first():
    # "weapon" shows up in half the technique prose; a technique that is clearly
    # a strike must not be filed under WEAPON just because the word is present
    it = _item("Hammer Fist", "a punch delivered with the weapon of the closed fist")
    assert martial_subtype(it) == "STRIKING"


def test_martial_falls_back_to_general():
    assert martial_subtype(_item("Signature Style", "a distinctive personal flourish")) == "GENERAL"


def test_adept_powers_are_passive_unless_they_cost_an_action():
    assert adept_subtype(_item("Combat Sense", "Activation: Passive heightened awareness")) == "PASSIVE"
    assert adept_subtype(_item("Smashing Blow", "Activation: Major Action shatter a wall")) == "ACTIVE"
    # states neither: passive is both commoner and the safer wrong answer
    assert adept_subtype(_item("Astral Perception", "the adept perceives the astral")) == "PASSIVE"


def test_contacts_prefer_a_stated_type():
    assert contact_subtype(_item("Mafia Consigliere", "Type: Criminal an organized criminal")) == "CRIMINAL"
    # 'Magical' in the text maps onto the canonical 'MAGIC' contact type
    assert contact_subtype(_item("Talismonger", "Type: Magical sells reagents")) == "MAGIC"


def test_contacts_fall_back_to_keywords_then_to_street():
    assert contact_subtype(_item("Street Doc", "patches up runners")) == "MEDICAL"
    assert contact_subtype(_item("Deckmeister", "builds cyberdecks")) == "MATRIX"
    assert contact_subtype(_item("Felix Gagnon", "a person you know")) == "STREET"


def test_foci_join_the_existing_gear_taxonomy():
    # MAGICAL/FOCI_* already exists for gear, so foci group with it rather than
    # inventing a parallel set of categories
    assert classify("foci/foci", _item("Weapon focus")) == ("MAGICAL", "FOCI_WEAPON")
    assert focus_subtype(_item("Centering focus")) == "FOCI_METAMAGIC"
    assert focus_subtype(_item("Sustaining focus")) == "FOCI_SPELL"


def test_an_unknown_group_is_left_alone():
    assert classify("something/unknown", _item("Thing")) is None


def _library(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    for domain, cat, items in [
        ("contacts", "contact", [{"id": "a", "name": "Street Doc", "system": {"description": "medic"}}]),
        # already classified, and a critter: neither may be touched
        ("gear", "weapons", [{"id": "b", "name": "Pistol",
                              "system": {"type": "WEAPON_FIREARMS", "subtype": "PISTOLS_LIGHT"}}]),
        ("critters", "critter", [{"id": "c", "name": "Bear", "system": {}}]),
    ]:
        d = data / "corebook" / domain
        d.mkdir(parents=True)
        (d / f"{cat}.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    return data


def _system(data: Path, domain: str, cat: str, idx: int = 0) -> dict:
    payload = json.loads((data / "corebook" / domain / f"{cat}.json").read_text(encoding="utf-8"))
    return payload["items"][idx]["system"]


def test_only_unclassified_items_change(tmp_path):
    data = _library(tmp_path)
    sys.argv = ["infer_missing_types.py", "--data", str(data)]
    assert main() == 0
    assert _system(data, "contacts", "contact") == {"description": "medic",
                                                    "type": "CONTACT", "subtype": "MEDICAL"}
    # an existing classification is authority and is never overwritten
    assert _system(data, "gear", "weapons")["subtype"] == "PISTOLS_LIGHT"


def test_critters_are_typed_but_never_subtyped(tmp_path):
    # they group under one type, but a bear and a devil rat are not two kinds of
    # the same thing — and each gets its own portrait, not a shared icon
    data = _library(tmp_path)
    sys.argv = ["infer_missing_types.py", "--data", str(data)]
    assert main() == 0
    assert _system(data, "critters", "critter") == {"type": "CRITTER", "subtype": ""}
    assert classify("npcs/npc", _item("Street Samurai")) == ("NPC", "")


def test_running_twice_changes_nothing_more(tmp_path):
    data = _library(tmp_path)
    sys.argv = ["infer_missing_types.py", "--data", str(data)]
    assert main() == 0
    before = (data / "corebook" / "contacts" / "contact.json").read_text(encoding="utf-8")
    assert main() == 0
    assert (data / "corebook" / "contacts" / "contact.json").read_text(encoding="utf-8") == before


def test_dry_run_writes_nothing(tmp_path):
    data = _library(tmp_path)
    sys.argv = ["infer_missing_types.py", "--data", str(data), "--dry-run"]
    assert main() == 0
    assert _system(data, "contacts", "contact") == {"description": "medic"}
