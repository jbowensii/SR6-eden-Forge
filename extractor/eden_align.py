"""Map a reader's raw system block to the shadowrun6-eden Foundry template
field shapes (from the system's template.json), so the local data store mirrors
the Eden document types and exports cleanly. One aligner per item domain; call
after extraction (or as a migration over existing data)."""

from __future__ import annotations

import re

_DUR = {"I": "instantaneous", "S": "sustained", "P": "permanent"}


def _num(s, default=0):
    m = re.search(r"-?\d+(?:\.\d+)?", "" if s is None else str(s))
    if not m:
        return default
    return float(m.group()) if "." in m.group() else int(m.group())


def _base(s):
    # "genesisID" is eden's own field name, kept verbatim on the wire;
    # everything in our code calls this the catalog id
    return {"genesisID": s.get("genesisID", ""), "description": s.get("description", ""),
            "product": s.get("product", ""), "page": s.get("page", 0)}


def spell(s):
    n = _base(s)
    n["category"] = (s.get("category") or "").lower()
    n["type"] = "mana" if s.get("spellType") == "M" else "physical"
    n["duration"] = _DUR.get(s.get("duration"), "instantaneous")
    n["range"] = re.sub(r"[^a-z]", "", (s.get("range") or "").lower()) or "los"
    n["drain"] = _num(s.get("drain"), 1)
    dmg = (s.get("damage") or "").upper()
    n["damage"] = "stun" if dmg.startswith("S") else ("physical" if dmg.startswith("P") else "")
    desc = (s.get("descriptor") or "").lower()
    n["combatSpellType"] = ("spells_direct" if ("direct" in desc and "indirect" not in desc)
                            else ("spells_indirect" if "indirect" in desc else ""))
    n["isSustained"] = n["duration"] == "sustained"
    for b in ("alchemic", "multiSense", "isOpposed", "withEssence", "wildDie"):
        n[b] = False
    return n


def ritual(s):
    kw = (s.get("keywords") or "").lower()
    n = _base(s)
    n["threshold"] = _num(s.get("threshold"), 0)
    n["features"] = {"anchored": "anchor" in kw, "material_link": "material" in kw,
                     "minion": "minion" in kw, "spell": "spell" in kw, "spotter": "spotter" in kw}
    return n


def adeptpower(s):
    cost = s.get("cost") or ""
    n = _base(s)
    n.update(hasLevel="per level" in cost.lower(), level=0, choice="",
             cost=float(_num(cost, 0)), activation=s.get("activation", ""))
    return n


def quality(s):
    n = _base(s)
    val = _num(s.get("cost"), 0)
    if "bonus" in (s.get("cost") or "").lower() or s.get("category") == "NEGATIVE":
        val = -abs(val)
    n.update(category=(s.get("category") or "").lower(), value=val,
             explain=s.get("gameEffect", ""), modifier=0, level=False)
    return n


def lifestyle(s, name=""):
    n = _base(s)
    n.update(type=re.sub(r"[^a-z]", "", name.lower()), cost=_num(s.get("cost"), 0), paid=1, sin="")
    return n


ALIGNERS = {"spells": spell, "rituals": ritual, "adept_powers": adeptpower,
            "qualities": quality, "lifestyles": lifestyle}
