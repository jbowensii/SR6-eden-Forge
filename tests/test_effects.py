"""Commlink6 modifications -> Foundry ActiveEffects.

The failure this guards against is silent: an effect with a key Eden does not
read looks perfectly correct on the item sheet and moves no number at all.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from extractor.effects import (MODE_ADD, build_effects, modification_to_change,
                               targets)

EDEN = Path(r"C:\Users\johnb\AppData\Local\FoundryVTT\Data\systems\shadowrun6-eden")


def mod(tag="valmod", **kw):
    return {"tag": tag, **kw}


# ---------- key format ----------

def test_attribute_uses_the_name_the_data_model_reads():
    """Eden's dropdown writes system.attributes.bod.mod and migrates it on edit.

    The current data model reads `attributes.body`, so a freshly imported item
    must carry the migrated name — otherwise it applies nothing until someone
    opens and re-saves the effect by hand.
    """
    change, _ = modification_to_change(mod(type="ATTRIBUTE", ref="BODY", value="1"))
    assert change["key"] == "system.attributes.body.mod"
    assert change["mode"] == MODE_ADD
    assert change["value"] == 1


def test_a_two_word_skill_keeps_its_underscore():
    """Eden doubles the separator so its converter can tell a word break from a
    path break: close__combat -> close_combat, not close.combat."""
    change, _ = modification_to_change(mod("checkmod", type="SKILL", ref="close combat", value="2"))
    assert change["key"] == "system.skills.close_combat.mod"


def test_every_target_we_emit_exists_in_edens_list():
    for path in targets().values():
        assert path.startswith(("system.", "traits.")), path


# ---------- what maps, and what deliberately does not ----------

def test_a_derived_pool_maps():
    change, _ = modification_to_change(mod(type="ATTRIBUTE", ref="DEFENSE_POOL_PHYSICAL", value="1"))
    assert change["key"] == "system.defensepool.physical.mod"


def test_weapon_damage_is_not_a_defence_pool():
    """A fuzzy name match paired Commlink6's weapon DAMAGE with Eden's
    defensepool.damage_physical. They are unrelated, and that effect would have
    quietly altered the wrong number on every character carrying the weapon."""
    change, why = modification_to_change(mod(type="ITEM_ATTRIBUTE", ref="DAMAGE", value="2"))
    assert change is None
    assert "DAMAGE" in why


@pytest.mark.parametrize("mtype", ["GEAR", "HOOK", "CREATION_POINTS", "METATYPE", "PRICEMOD"])
def test_non_modifiers_are_skipped_with_a_reason(mtype):
    change, why = modification_to_change(mod(type=mtype, ref="whatever", value="1"))
    assert change is None and why


@pytest.mark.parametrize("tag", ["embed", "itemmod", "allowmod", "selmod", "relevancemod"])
def test_structural_tags_are_not_effects(tag):
    change, why = modification_to_change(mod(tag, type="ATTRIBUTE", ref="BODY", value="1"))
    assert change is None
    assert "not a modifier" in why


# ---------- grouping ----------

def test_one_item_makes_one_effect_holding_every_change():
    eff = build_effects("Muscle Toner", [
        mod(type="ATTRIBUTE", ref="AGILITY", value="2"),
        mod(type="ATTRIBUTE", ref="REACTION", value="1"),
    ])
    assert len(eff) == 1
    assert eff[0]["disabled"] is False
    assert [c["key"] for c in eff[0]["changes"]] == [
        "system.attributes.agility.mod", "system.attributes.reaction.mod"]


def test_a_choice_is_recorded_but_left_switched_off():
    """"+1 to a skill of your choice" cannot name a target, and Foundry needs
    one. Recorded so the information travels with the item, disabled so it
    cannot apply the wrong bonus."""
    eff = build_effects("Aptitude", [mod("checkmod", type="SKILL", ref="CHOICE", value="1")])
    assert len(eff) == 1
    assert eff[0]["disabled"] is True
    assert eff[0]["changes"] == []
    assert "choose" in eff[0]["name"].lower()


def test_an_item_with_both_gets_one_of_each():
    eff = build_effects("Mixed", [
        mod(type="ATTRIBUTE", ref="BODY", value="1"),
        mod("checkmod", type="SKILL", ref="CHOICE", value="1"),
    ])
    assert [e["disabled"] for e in eff] == [False, True]


def test_an_item_with_nothing_mappable_gets_no_effect():
    """No empty effects: a blank one on the sheet reads as a bug."""
    assert build_effects("Plain", [mod("embed", intoType="ARMOR")]) == []
    assert build_effects("Plain", []) == []


# ---------- the table is generated, not typed ----------

@pytest.mark.skipif(not EDEN.is_dir(), reason="shadowrun6-eden not installed")
def test_the_target_table_still_matches_the_installed_system():
    """Regenerate rather than re-guess when Eden updates."""
    import re
    src = (EDEN / "module" / "config.js").read_text(encoding="utf-8", errors="replace")
    i = src.index("ACTIVE_EFFECT_OPTIONS = {")
    depth, j = 0, i + 24
    while True:
        if src[j] == "{": depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0: break
        j += 1
    live = set(re.findall(r"^\s{8}([A-Za-z0-9_]+)\s*:", src[i:j], re.M))
    assert live == set(targets()), "Eden's effect list changed — regenerate eden_effect_targets.json"
