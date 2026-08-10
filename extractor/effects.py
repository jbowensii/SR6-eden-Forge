"""Turn Commlink6 ``<modifications>`` into Foundry ActiveEffects for Eden.

Commlink6 records what an item DOES — "+1 Body", "-1 to Con checks", "+2 attack
rating" — as structured XML. We read that XML for stats and threw the
modifications away, so every item exported to Foundry carried an empty effects
array and modified nothing when equipped.

**What maps, and what does not.** Of 9,631 modification elements in the jar:

    814   name a specific target and become a live effect
    418   say "a skill of your choice" and cannot name one
  6,639   are not effects at all — embedded items, modification slots,
          permission rules — and belong to systems we do not model
  1,760   are chargen budgets, ammo grants and mounting hooks

So this produces roughly 814 working effects, not 9,631. The rest are left
alone deliberately; a mounting hook is not a modifier and pretending otherwise
would put nonsense on the item sheet.

**Key format.** Eden lists its 104 targets with underscores
(``system_attributes_bod_mod``) and its own dropdown converts them to a dotted
path when it writes one. Then a second table migrates the older short names to
the ones the current data model actually reads — ``attributes.body``, not
``attributes.bod``. Both steps are already applied in
``eden_effect_targets.json``, so the values there are what Foundry consumes.
Writing the dropdown's un-migrated form would produce effects that look right
on screen and move nothing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

#: Foundry ActiveEffect change modes. ADD is the only one a stat modifier wants:
#: OVERRIDE would make two sources of "+1 Body" disagree instead of stacking.
MODE_ADD = 2

_TARGETS: dict[str, str] | None = None


def targets() -> dict[str, str]:
    """Eden's 104 effect targets, as ``option key -> dotted path``.

    Generated from the installed system rather than typed out, so a future Eden
    release can be re-read instead of re-guessed.
    """
    global _TARGETS
    if _TARGETS is None:
        p = Path(__file__).with_name("eden_effect_targets.json")
        _TARGETS = json.loads(p.read_text(encoding="utf-8"))["targets"]
    return _TARGETS


#: Commlink6 attribute code -> Eden's option key.
_ATTR = {
    "BODY": "system_attributes_bod_mod", "AGILITY": "system_attributes_agi_mod",
    "REACTION": "system_attributes_rea_mod", "STRENGTH": "system_attributes_str_mod",
    "WILLPOWER": "system_attributes_wil_mod", "LOGIC": "system_attributes_log_mod",
    "INTUITION": "system_attributes_int_mod", "CHARISMA": "system_attributes_cha_mod",
    "MAGIC": "system_attributes_mag_mod", "RESONANCE": "system_attributes_res_mod",
    "ESSENCE": "system_attributes_essence_mod", "EDGE": "system_edge_max",
}

#: Derived stats. Matched by reading Eden's list against Commlink6's refs, one
#: by one — NOT by fuzzy string match, which cheerfully paired Commlink6's
#: weapon DAMAGE with Eden's defensepool.damage_physical. They are unrelated,
#: and that effect would have quietly subtracted from the wrong number.
_DERIVED = {
    "DEFENSE_POOL_PHYSICAL": "system_defensepool_physical_mod",
    "DEFENSE_POOL_ASTRAL": "system_defensepool_astral_mod",
    "DEFENSE_POOL_SPELLS_DIRECT": "system_defensepool_spells__direct_mod",
    "DEFENSE_POOL_SPELLS_INDIRECT": "system_defensepool_spells__indirect_mod",
    "DEFENSE_POOL_DRAIN": "system_defensepool_drain_mod",
    "DEFENSE_POOL_FADING": "system_defensepool_fading_mod",
    "DEFENSE_POOL_TOXIN": "system_defensepool_toxin_mod",
    "DEFENSE_RATING_PHYSICAL": "system_defenserating_physical_mod",
    "DEFENSE_RATING_ASTRAL": "system_defenserating_astral_mod",
    "DEFENSE_RATING_MATRIX": "system_defenserating_matrix_mod",
    "ATTACK_RATING_PHYSICAL": "system_attackrating_physical_mod",
    "ATTACK_RATING_ASTRAL": "system_attackrating_astral_mod",
    "ATTACK_RATING_MATRIX": "system_attackrating_matrix_mod",
    "COMPOSURE": "system_derived_composure_mod",
    "JUDGE_INTENTIONS": "system_derived_judge__intentions_mod",
    "LIFT_CARRY": "system_derived_lift__carry_mod",
    "MEMORY": "system_derived_memory_mod",
    "MATRIX_PERCEPTION": "system_derived_matrix__perception_mod",
    "INITIATIVE_DICE_PHYSICAL": "system_initiative_physical_diceMod",
    "INITIATIVE_DICE_ASTRAL": "system_initiative_astral_diceMod",
    "INITIATIVE_DICE_MATRIX": "system_initiative_matrix_diceMod",
    "INITIATIVE_PHYSICAL": "system_initiative_physical_mod",
    "INITIATIVE_ASTRAL": "system_initiative_astral_mod",
    "INITIATIVE_MATRIX": "system_initiative_matrix_mod",
    "PAIN_TOLERANCE": "system_painTolerance",
}

#: Item stats Commlink6 modifies that Eden also exposes. Deliberately short:
#: Eden has no target for CONCEALABILITY, HANDLING or TOPSPEED, so those stay
#: on the item's own fields where they already live.
_ITEM_ATTR = {"ATTACK_RATING": "system_attackRating_0"}

#: A ref of CHOICE means the player picks the target when they take the item.
#: Foundry needs a concrete path, so these are recorded and left switched off.
CHOICE = "CHOICE"


def _skill_key(ref: str) -> str:
    """``close combat`` -> ``system_skills_close__combat_modifier``.

    Eden DOUBLES the separator inside a skill name so its own converter can
    tell a word break from a path break: a single underscore becomes a dot, a
    doubled one becomes a literal underscore. Both spaces and underscores in
    the source name collapse to one doubled separator — done in a single pass,
    because replacing spaces first and underscores second would then double the
    underscores just inserted.
    """
    stem = re.sub(r"[\s_]+", "__", ref.strip().lower())
    return f"system_skills_{stem}_modifier"


def _num(raw):
    """Commlink6 values are strings; Foundry wants a number where it is one."""
    s = "" if raw is None else str(raw).strip()
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return s


def _change(option_key: str, value) -> dict | None:
    path = targets().get(option_key)
    if not path:
        return None
    return {"key": path, "mode": MODE_ADD, "value": _num(value), "priority": None}


def modification_to_change(mod: dict) -> tuple[dict | None, str | None]:
    """One ``<modifications>`` child -> ``(change, why_not)``.

    Returns ``(None, reason)`` for anything that is not a stat modifier, so the
    caller can count what was skipped instead of losing it silently.
    """
    tag = mod.get("tag")
    if tag not in ("valmod", "checkmod"):
        return None, f"not a modifier ({tag})"

    mtype = (mod.get("type") or "").upper()
    ref = (mod.get("ref") or "").strip()
    value = mod.get("value", mod.get("val"))

    if ref == CHOICE:
        return None, "player chooses the target"

    if mtype == "ATTRIBUTE":
        # Commlink6 files real attributes and derived pools under one type.
        key = _ATTR.get(ref.upper()) or _DERIVED.get(ref.upper())
        return (_change(key, value), None) if key else (None, f"unmapped attribute {ref}")
    if mtype == "SKILL":
        ch = _change(_skill_key(ref), value)
        return (ch, None) if ch else (None, f"unknown skill {ref}")
    if mtype == "ITEM_ATTRIBUTE":
        key = _ITEM_ATTR.get(ref.upper())
        return (_change(key, value), None) if key else (None, f"item stat {ref}")
    return None, f"{mtype or 'untyped'} is not a character modifier"


def build_effects(name: str, mods: list[dict], img: str | None = None) -> list[dict]:
    """All of an item's modifications as at most two ActiveEffects.

    One effect holds every change that names a target and is enabled. A second
    holds the "of your choice" ones — recorded so the information travels with
    the item, disabled so it cannot silently apply the wrong bonus. A GM picks
    the target and switches it on.

    Grouped rather than one effect per change: an item with four modifiers
    should read as one thing on the sheet, not four.
    """
    changes, choices = [], []
    for m in mods or []:
        change, why = modification_to_change(m)
        if change:
            changes.append(change)
        elif why == "player chooses the target":
            choices.append(m)

    out = []
    if changes:
        out.append({
            "name": name, "img": img or None, "disabled": False, "transfer": True,
            "changes": changes,
            "description": "",
        })
    if choices:
        what = ", ".join(sorted({(m.get("type") or "?").lower() for m in choices}))
        out.append({
            "name": f"{name} — choose {what}", "img": img or None,
            "disabled": True, "transfer": True, "changes": [],
            "description": ("This item modifies a "
                            f"{what} the player chooses. Set the target and enable "
                            "this effect."),
        })
    return out
