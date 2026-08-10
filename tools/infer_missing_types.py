"""Give a type and subtype to the items that have neither.

Gear arrives classified; most of the rest does not. Contacts, adept powers,
martial techniques, traditions, the Commlink6 reference tables — roughly a
thousand items — carry an empty ``type``/``subtype``, which means they group
under nothing in the review app and can never be given a category icon.

Nothing here is authoritative, and it is not pretending to be. The type comes
from the domain the item was read out of, which is reliable; the subtype is a
best guess, taken from an explicit "Category:"/"Type:"/"Activation:" line in the
item's own text when there is one, and from keywords in its name and description
when there is not. Where the guess would be noise, the subtype is left empty and
the type alone carries the grouping.

Only items with BOTH fields empty are touched, so a real classification — from
Commlink6, from a source table, or from your own hand — is never overwritten.

Critters and NPCs are typed like everything else so they group properly, but
with no subtype: a bear and a street samurai are not two kinds of one thing. They
are deliberately excluded from the shared category icons (see
``install_category_icons.NO_CATEGORY_ICON``) because each one gets its own
portrait by hand.

    python tools/infer_missing_types.py --dry-run
    python tools/infer_missing_types.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path as _P

sys.path.insert(0, str(_P(__file__).resolve().parent.parent))

from extractor.paths import data_root                 # noqa: E402



def _text(item: dict) -> str:
    system = item.get("system") or {}
    return f"{item.get('name') or ''}\n{system.get('description') or ''}\n{system.get('notes') or ''}"


def _stated(item: dict, label: str) -> str:
    """A "Category: Weapon" style declaration in the item's own text.

    The books print it for some entries and not others, so this is a strong
    signal where present and simply absent elsewhere — hence the keyword
    fallbacks below rather than a single rule.
    """
    m = re.search(rf"{label}:\s*([A-Za-z][A-Za-z /&-]{{2,24}})", _text(item))
    if not m:
        return ""
    # the line often runs straight into the prose that follows it, so keep only
    # the leading words that still look like a label
    words = re.split(r"\s+", m.group(1).strip())
    kept = []
    for w in words[:2]:
        if w.isupper() or w[:1].isupper() or len(kept) == 0:
            kept.append(w)
        else:
            break
    return "_".join(kept).upper().strip("_")


def _keyword(item: dict, table: list[tuple[str, tuple[str, ...]]], default: str) -> str:
    """First subtype whose keywords appear in the item's text."""
    text = _text(item).casefold()
    for subtype, words in table:
        if any(w in text for w in words):
            return subtype
    return default


CONTACT_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("MEDICAL", ("street doc", "doctor", "medic", "nurse", "surgeon", "paramedic", "hospital")),
    ("MAGIC", ("talismonger", "shaman", "mage", "magician", "awakened", "spirit", "occult",
               "alchemist", "adept", "hermetic", "witch", "lorekeeper", "artificer")),
    ("MATRIX", ("decker", "hacker", "deckmeister", "technomancer", "matrix", "sysop", "netcat",
                "programmer", "data broker")),
    ("ENGINEERING", ("mechanic", "rigger", "engineer", "armorer", "chemist", "technician",
                     "gunsmith", "machinist", "drone")),
    ("CORPORATE", ("corporate", "wageslave", "executive", "exec ", "megacorp", "board member",
                   "manager", "accountant", "store owner", "merchant")),
    ("GOVERNMENT", ("government", "official", "politician", "bureaucrat", "customs", "soldier",
                    "police", "officer", "detective", "agent", "military", "lawyer", "judge")),
    ("ACADEMIC", ("professor", "scholar", "researcher", "scientist", "academic", "historian",
                  "archaeologist", "librarian", "teacher")),
    ("MEDIA", ("reporter", "journalist", "media", "broadcaster", "producer", "trid", "blogger")),
    ("CRIMINAL", ("mafia", "yakuza", "triad", "gang", "ganger", "smuggler", "fence", "fencing",
                  "thief", "pickpocket", "bounty hunter", "cleaner", "fixer", "syndicate",
                  "id manufacturer", "forger", "assassin", "organized crim")),
]

#: Order matters — the specific manoeuvre categories are tested before WEAPON,
#: which is last because the word "weapon" turns up in the prose of half the
#: techniques and would otherwise claim them all.
MARTIAL_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("GRAPPLING", ("grapple", "grappling", "clinch", "chokehold", "joint lock", "takedown", "pin ")),
    ("STRIKING", ("strike", "striking", "punch", "kick", "elbow", "knee", "unarmed")),
    ("MOBILITY", ("mobility", "dodge", "evade", "footwork", "sprint", "leap", "reposition")),
    ("RANGED", ("ranged", "firearm", "pistol", "rifle", "throwing", "thrown")),
    ("WEAPON", ("blade", "bladed", "sword", "staff", "club", "weapon")),
]

FOCUS_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("FOCI_WEAPON", ("weapon focus", "athame", "blood focus")),
    ("FOCI_QI", ("qi focus",)),
    ("FOCI_POWER", ("power focus",)),
    ("FOCI_METAMAGIC", ("centering", "masking", "flexible signature", "spell shaping",
                        "disenchant", "metamagic")),
    ("FOCI_ENCHANTING", ("alchemical", "enchanting")),
    ("FOCI_SPIRIT", ("summoning", "banishing", "spirit")),
]


def contact_subtype(item: dict) -> str:
    stated = _stated(item, "Type")
    canon = {"FREE_SPIRIT", "ACADEMIC", "CORPORATE", "CRIMINAL", "ENGINEERING", "GOVERNMENT",
             "MAGIC", "MATRIX", "MEDIA", "MEDICAL", "STREET"}
    if stated in canon:
        return stated
    if stated == "MAGICAL":
        return "MAGIC"
    return _keyword(item, CONTACT_WORDS, "STREET")


def martial_subtype(item: dict) -> str:
    stated = _stated(item, "Category")
    if stated in {"WEAPON", "STRIKING", "MOBILITY", "GRAPPLING", "GENERAL", "RANGED"}:
        return stated
    return _keyword(item, MARTIAL_WORDS, "GENERAL")


def adept_subtype(item: dict) -> str:
    """Passive unless the power costs an action to use.

    "Activation: Passive" vs "Activation: Major Action" is the one distinction
    the books make consistently. Roughly a third of the entries state neither,
    and passive is both the commoner case and the safer default — calling an
    always-on power "active" misleads in a way the reverse does not.
    """
    stated = _stated(item, "Activation").casefold()
    if "passive" in stated:
        return "PASSIVE"
    if "action" in stated or re.search(r"\b(major|minor)\s+action\b", _text(item), re.I):
        return "ACTIVE"
    return "PASSIVE"


def focus_subtype(item: dict) -> str:
    return _keyword(item, FOCUS_WORDS, "FOCI_SPELL")


#: domain/category  ->  (type, subtype)   where subtype is a constant or a rule.
#: The type is the domain's own identity and is safe; the subtype is the guess.
RULES: dict[str, tuple[str, object]] = {
    "contacts/contact":                       ("CONTACT", contact_subtype),
    "adept_powers/adept_powers":              ("ADEPT_POWER", adept_subtype),
    "adept_powers/adept_power":               ("ADEPT_POWER", adept_subtype),
    "martial_techniques/martial_techniques":  ("MARTIAL_TECHNIQUE", martial_subtype),
    "martial_techniques/martial_art_tech":    ("MARTIAL_TECHNIQUE", martial_subtype),
    "complexforms/complexforms":              ("COMPLEX_FORM", ""),
    "critter_powers/critter_power":           ("CRITTER_POWER", ""),
    "rituals/ritual":                         ("RITUAL", ""),
    "rituals/rituals":                        ("RITUAL", ""),
    "metamagics/metamagic":                   ("METAMAGIC", ""),
    "echoes/echo":                            ("ECHO", ""),
    "spirits/spirit":                         ("SPIRIT", ""),
    "sins/sin":                               ("SIN", ""),
    "lifestyles/lifestyles":                  ("LIFESTYLE", ""),
    # foci reuse the gear taxonomy on purpose: MAGICAL/FOCI_* already exists and
    # already has icons, so these join a group instead of inventing a new one
    "foci/foci":                              ("MAGICAL", focus_subtype),
    "foci/focus":                             ("MAGICAL", focus_subtype),
    "qualities/qualities":                    ("QUALITY", "MENTOR_SPIRIT"),
    "qualities/positive":                     ("QUALITY", "POSITIVE"),
    "qualities/negative":                     ("QUALITY", "NEGATIVE"),
    "commlink6_extra/quality_paths":          ("QUALITY", "PATH"),
    "commlink6_extra/metatypes":              ("METATYPE", ""),
    "commlink6_extra/traditions":             ("TRADITION", ""),
    "commlink6_extra/datastructures":         ("DATA_STRUCTURE", ""),
    "commlink6_extra/contact_types":          ("CONTACT", "ARCHETYPE"),
    "commlink6_extra/licensetypes":           ("LICENSE", ""),
    "commlink6_extra/magicOrResonance":       ("MAGIC_TYPE", ""),
    "commlink6_extra/senses":                 ("SENSE", ""),
    "commlink6_extra/spellfeatures":          ("SPELL_FEATURE", ""),
    "commlink6_extra/ritualfeatures":         ("RITUAL_FEATURE", ""),
    "commlink6_extra/rules":                  ("RULESET", ""),
    "commlink6_extra/consoleTypes":           ("CONSOLE_TYPE", ""),
    "commlink6_extra/draketypes":             ("DRAKE_TYPE", ""),
    "commlink6_extra/qualityFactors":         ("VEHICLE_DESIGN", "FACTOR"),
    "commlink6_extra/designMods":             ("VEHICLE_DESIGN", "MOD"),
    "commlink6_extra/designOptions":          ("VEHICLE_DESIGN", "OPTION"),
    "commlink6_extra/modifications_easycome": ("GEAR_MODIFICATION", ""),
    "commlink6_extra/cyberware_enhancements": ("CYBERWARE", "ENHANCEMENT"),
    "commlink6_extra/true_element_attributes": ("ELEMENT_ATTRIBUTE", ""),
    # Typed so they group, but never subtyped: these are individuals, and each
    # gets its own portrait rather than a shared category icon.
    "critters/critter":                       ("CRITTER", ""),
    "npcs/npc":                               ("NPC", ""),
}


def classify(group: str, item: dict) -> tuple[str, str] | None:
    rule = RULES.get(group)
    if rule is None:
        return None
    itype, sub = rule
    return itype, (sub(item) if callable(sub) else sub)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=_P, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    data = args.data or data_root()
    assigned: Counter[tuple[str, str]] = Counter()
    skipped_groups: Counter[str] = Counter()
    changed = 0

    for book in sorted(p for p in data.iterdir() if p.is_dir() and not p.name.startswith("_")):
        for domain in sorted(d for d in book.iterdir() if d.is_dir()):
            for path in sorted(domain.glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                group = f"{domain.name}/{path.stem}"
                dirty = False
                for item in payload.get("items", []):
                    system = item.setdefault("system", {})
                    if str(system.get("type") or "") or str(system.get("subtype") or ""):
                        continue                       # already classified: leave it
                    guess = classify(group, item)
                    if guess is None:
                        skipped_groups[group] += 1
                        continue
                    system["type"], system["subtype"] = guess
                    assigned[guess] += 1
                    changed += 1
                    dirty = True
                if dirty and not args.dry_run:
                    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8")

    print(f"library: {data}")
    print(f"classified {changed} items into {len(assigned)} type/subtype pairs\n")
    for (t, s), n in sorted(assigned.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {n:5}  {t} - {s or '(no subtype)'}")
    if skipped_groups:
        print(f"\nno rule for {sum(skipped_groups.values())} items:")
        for g, n in skipped_groups.most_common(10):
            print(f"  {n:5}  {g}")
    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
