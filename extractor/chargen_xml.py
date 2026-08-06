"""Lossless chargen-data readers for the Commlink6 jar. Unlike the item merge
(extractor/commlink6.py), which flattens stats and skips <modifications>/<choices>,
these parsers preserve the FULL element tree — the chargen rules live exactly in
those skipped blocks (priority values, creation attribute maxima, racial
qualities, skill unlocks, quality costs).

Each section parser returns typed convenience fields PLUS a `raw` deep-tree of
the source element, so nothing is ever unrecoverable. English i18n only."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from extractor.commlink6 import DEFAULT_JAR, _i18n, decode_props

# i18n keys are "<prefix>.<id>[.desc|.page|...]"; ids collide across prefixes
# (skill.firearms=Firearms vs licensetype.firearms=Firearms License), so chargen
# sections must look their labels up under the RIGHT prefix.
_PFX_LINE = re.compile(
    r"^([A-Za-z_]+)\.([A-Za-z0-9_.-]+?)(?:\.(desc|page|wifi|source))?\s*=\s*(.*)$")


def i18n_by_prefix(z: zipfile.ZipFile, book: str) -> dict:
    """{prefix: {id: {name, page, desc, wifi}}} for one book's English bundle."""
    path = f"de/rpgframework/shadowrun6/data/{book}/i18n/{book}.properties"
    out: dict = {}
    if path not in set(z.namelist()):
        return out
    for ln in decode_props(z.read(path)).splitlines():
        m = _PFX_LINE.match(ln)
        if not m:
            continue
        prefix, iid, sub, val = m.groups()
        rec = out.setdefault(prefix, {}).setdefault(iid, {})
        rec[sub or "name"] = val.strip()
    return out


def sub_i18n(byprefix: dict, prefix: str) -> dict:
    """One prefix's id->record map (what the section parsers expect)."""
    return byprefix.get(prefix, {})

# Commlink6 attribute names -> eden attribute codes
ATTR_CODE = {
    "BODY": "bod", "AGILITY": "agi", "REACTION": "rea", "STRENGTH": "str",
    "WILLPOWER": "wil", "LOGIC": "log", "INTUITION": "int", "CHARISMA": "cha",
    "EDGE": "edg", "MAGIC": "mag", "RESONANCE": "res",
}
# human baseline creation maxima (SR6 core: all 6, Edge 7); metatype rows override
HUMAN_MAX = {"bod": 6, "agi": 6, "rea": 6, "str": 6, "wil": 6, "log": 6,
             "int": 6, "cha": 6, "edg": 6}


def deep_tree(el: ET.Element) -> dict:
    """Lossless element -> {'tag', 'attrs', 'text', 'children'} (comments excluded)."""
    return {
        "tag": el.tag if isinstance(el.tag, str) else "!comment",
        "attrs": dict(el.attrib),
        "text": (el.text or "").strip(),
        "children": [deep_tree(c) for c in el if isinstance(c.tag, str)],
    }


def read_category_trees(z: zipfile.ZipFile, book: str, category: str) -> list[dict]:
    """All top-level elements of data/<book>/data/<category>.xml as deep trees."""
    path = f"de/rpgframework/shadowrun6/data/{book}/data/{category}.xml"
    if path not in set(z.namelist()):
        return []
    root = ET.fromstring(z.read(path))
    return [deep_tree(el) for el in root if isinstance(el.tag, str)]


def _mods(tree: dict) -> list[dict]:
    for c in tree["children"]:
        if c["tag"] == "modifications":
            return c["children"]
    return []


def _choices(tree: dict) -> list[dict]:
    for c in tree["children"]:
        if c["tag"] == "choices":
            return c["children"]
    return []


def _int(v, default=0):
    m = re.search(r"-?\d+", str(v or ""))
    return int(m.group()) if m else default


def _num(v, default=0.0):
    try:
        return float(str(v))
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# section parsers
# --------------------------------------------------------------------------- #
def parse_priorities(trees: list[dict]) -> dict:
    """core/priorities.xml -> {letter: {METATYPE:{metatypes{}}, ATTRIBUTE:{attributePoints},
    SKILLS:{skillPoints}, RESOURCES:{nuyen}, MAGIC:{byMor{}}}}"""
    out: dict = {}
    for t in trees:
        if t["tag"] != "priotableentry":
            continue
        letter = t["attrs"].get("prio")
        typ = t["attrs"].get("type")
        row = out.setdefault(letter, {})
        mods = _mods(t)
        if typ == "METATYPE":
            metas = {}
            for m in mods:
                if m["attrs"].get("type") == "METATYPE":
                    metas[m["attrs"]["ref"]] = _int(m["attrs"].get("value"),
                                                    _int(t["attrs"].get("adj")))
            row["METATYPE"] = {"adjustmentDefault": _int(t["attrs"].get("adj")),
                               "metatypes": metas, "raw": t}
        elif typ == "ATTRIBUTE":
            pts = next((_int(m["attrs"].get("value")) for m in mods
                        if m["attrs"].get("ref") == "ATTRIBUTES"), 0)
            row["ATTRIBUTE"] = {"attributePoints": pts}
        elif typ == "SKILLS":
            pts = next((_int(m["attrs"].get("value")) for m in mods
                        if m["attrs"].get("ref") == "SKILLS"), 0)
            row["SKILLS"] = {"skillPoints": pts}
        elif typ == "RESOURCES":
            ny = next((_int(m["attrs"].get("value")) for m in mods
                       if m["attrs"].get("ref") == "NUYEN"), 0)
            row["RESOURCES"] = {"nuyen": ny}
        elif typ == "MAGIC":
            by = {m["attrs"]["ref"]: _int(m["attrs"].get("value")) for m in mods
                  if m["attrs"].get("type") == "MAGIC_RESO"}
            row["MAGIC"] = {"byMor": by}
    return out


def parse_metatypes(trees: list[dict], i18n: dict, book: str) -> dict:
    """metatypes.xml (core or companion) -> {id: {...}}."""
    out: dict = {}
    for t in trees:
        if t["tag"] != "metatype":
            continue
        a = t["attrs"]
        if a.get("lang") not in (None, "", "en"):
            continue                            # German-locale duplicate rows
        mid = a["id"]
        text = i18n.get(mid) or i18n.get(mid.lower()) or {}
        maxima = dict(HUMAN_MAX)
        if mid == "human":
            maxima["edg"] = 7
        racial_q: list = []
        natural: dict = {}
        pricemods: dict = {}
        for m in _mods(t):
            ma = m["attrs"]
            if m["tag"] == "valmod" and ma.get("type") == "ATTRIBUTE" \
                    and ma.get("set") == "MAX":
                code = ATTR_CODE.get(ma.get("ref", ""))
                if code:
                    maxima[code] = _int(ma.get("value"))
            elif m["tag"] == "itemmod" and ma.get("type") == "QUALITY":
                racial_q.append(ma.get("ref"))
            elif m["tag"] == "valmod" and ma.get("type") == "QUALITY" \
                    and ma.get("set") == "NATURAL":
                natural[ma.get("ref")] = _int(ma.get("value"))
            elif m["tag"] == "valmod" and ma.get("type") == "PRICEMOD":
                pricemods[ma.get("ref")] = _num(ma.get("value"))
        out[mid] = {
            "name": text.get("name") or mid.replace("_", " ").title(),
            "book": book, "page": _int(text.get("page")),
            "karma": _int(a.get("karma")),
            "variantOf": a.get("variantof") or ("human" if a.get("human") == "true" else None),
            "size": a.get("size", ""), "weight": a.get("weight", ""),
            "attributeMaxCreation": maxima,
            "racialQualityIds": racial_q,
            "naturalRatings": natural,
            "priceMods": pricemods,
            "raw": t,
        }
    return out


def parse_magicreson(trees: list[dict], i18n: dict) -> dict:
    """magicOrResonance.xml -> {morId: {...}} (ids == eden mortype enum)."""
    out: dict = {}
    for t in trees:
        if t["tag"] != "magicreson":
            continue
        a = t["attrs"]
        mid = a["id"]
        text = i18n.get(mid) or {}
        unlocks = [m["attrs"].get("ref") for m in _mods(t)
                   if m["tag"] == "allowmod" and m["attrs"].get("type") == "SKILL"]
        out[mid] = {
            "name": text.get("name") or mid,
            "magic": a.get("magic") == "true",
            "resonance": a.get("resonance") == "true",
            "spells": a.get("spells") == "true",
            "powers": a.get("powers") == "true",
            "paysPowers": a.get("paysPowers") == "true",
            "aspected": a.get("aspected") == "true",
            "karmaCost": _int(a.get("cost")),
            "skillUnlocks": unlocks,
            "raw": t,
        }
    return out


def parse_skills(trees: list[dict], i18n: dict) -> dict:
    """skills.xml -> {skillId: {name, attr, type, untrained, restricted, specializations{}}}."""
    out: dict = {}
    for t in trees:
        if t["tag"] != "skill":
            continue
        a = t["attrs"]
        sid = a["id"]
        text = i18n.get(sid) or {}
        specs = {}
        for c in t["children"]:
            if c["tag"] != "skillspec":
                continue
            spid = c["attrs"]["id"]
            # "skill.<skill>.skillspec.<spec>" -> our per-prefix map stores the
            # tail as "<skill>.skillspec.<spec>"
            spec_rec = i18n.get(f"{sid}.skillspec.{spid}") or {}
            specs[spid] = {
                "name": spec_rec.get("name") or spid.replace("_", " ").title(),
                "attr": ATTR_CODE.get(c["attrs"].get("attr", ""), None),
                "subtypes": [s for s in c["attrs"].get("subtypes", "").split(",") if s],
            }
        out[sid] = {
            "name": text.get("name") or sid.replace("_", " ").title(),
            "attr": ATTR_CODE.get(a.get("attr", ""), None),
            "type": a.get("type", ""),
            "untrained": a.get("untr") == "y",
            "restricted": a.get("restrict") == "y",
            "freeText": bool(_choices(t)),
            "specializations": specs,
        }
    return out


#: Upstream rule identifiers -> the setting names this project uses.
#:
#: The source data labels its optional rules with SCREAMING_SNAKE constants.
#: Those are the upstream application's identifier namespace, not ours, so they
#: are translated once here, at the import boundary. Everything downstream —
#: chargen-data.json, the engine, the options screen — speaks only the
#: camelCase names on the right, which match Foundry and shadowrun6-eden style.
RULE_SETTING_NAMES = {
    "CHARGEN_MAX_AVAILABILITY": "maxAvailability",
    "CHARGEN_MAX_KARMA_REMAIN": "maxKarmaRemaining",
    "CHARGEN_MAX_NUYEN_REMAIN": "maxNuyenRemaining",
    "CHARGEN_NEGATIVE_NUYEN": "allowNegativeNuyen",
    "CHARGEN_ADJUSTMENT_ON_LOWERED_MAX": "adjustmentOnLoweredMax",
    "CHARGEN_SUM_TO_TEN_ELITE": "sumToTenTarget",
    "CHARGEN_ALLOW_INITIATION": "allowInitiation",
    "CHARGEN_MAX_INITIATION": "maxInitiationGrade",
    "CHARGEN_MAX_SUBMERSION": "maxSubmersionGrade",
    "CHARGEN_MAX_TRANSHUMAN": "maxTranshumanGrade",
    "CHARGEN_MAX_ANIMALISM": "maxAnimalismGrade",
    "CHARGEN_BUY_SPELLS_KARMA": "buySpellsWithKarma",
    "CHARGEN_RAISE_ABOVE_6": "raiseMagicAboveSix",
    "CHARGEN_EXTENDED_CONTACT": "extendedContactRules",
    "CHARGEN_MORE_KNOWLEDGE": "knowledgeFromLogicAndIntuition",
    "CHARGEN_PRIO_ADEPT_PP_PRIO_MAGIC": "powerPointsFromPriorityOnly",
    "CHARGEN_PRIO_ADJUSTED_MAGIC_RESO": "useAdjustedMagicResonance",
    "CHARGEN_ERRATED_POINT_BUY": "erratedPointBuyResources",
    "ALLOW_TRANSHUMANISM": "allowTranshumanism",
    "ALLOW_NEUROMORPHISM": "allowNeuromorphism",
    "ALLOW_ANIMALISM": "allowAnimalism",
    "ALLOW_USED_CULTURED_BIOWARE": "allowUsedCulturedBioware",
    "ADD_STRENGTH_TO_MELEE_AR": "addStrengthToMeleeAttackRating",
    "HIGH_STRENGTH_ADDS_DAMAGE": "strengthAddsMeleeDamage",
    "EXPANDED_SPECIALIZATIONS": "expandedSpecializations",
    "MYSTADEPT_ADVANCE_RAISE_MAGIC_RAISE_PP": "mysticAdeptMagicRaisesPowerPoints",
    "CARGOFACTOR_IS_WITHOUT_SEATS": "seatsOccupyCargoFactor",
}


def setting_name(upstream_id: str) -> str:
    """Translate an upstream rule id; unmapped ids fall back to camelCase."""
    if upstream_id in RULE_SETTING_NAMES:
        return RULE_SETTING_NAMES[upstream_id]
    head, *rest = upstream_id.lower().split("_")
    return head + "".join(w.capitalize() for w in rest)


def parse_rule_labels(z: zipfile.ZipFile) -> dict:
    """Shadowrun6Rules.properties -> {settingName: label} for the optional rules."""
    path = "de/rpgframework/shadowrun6/Shadowrun6Rules.properties"
    if path not in set(z.namelist()):
        return {}
    out = {}
    for ln in decode_props(z.read(path)).splitlines():
        m = re.match(r"^rule\.([a-z0-9_.]+)\s*=\s*(.*)$", ln.strip())
        if m:
            upstream = m.group(1).upper().replace(".", "_")
            out[setting_name(upstream)] = m.group(2).strip()
    return out


def parse_rules(trees: list[dict]) -> dict:
    """rules.xml -> {interpretationId: {restrict[], settings{name: value}}}.

    Rule ids are translated to this project's setting names (see
    ``RULE_SETTING_NAMES``) so no downstream code carries the upstream
    application's identifier namespace.
    """
    def coerce(v: str):
        if v in ("true", "false"):
            return v == "true"
        m = re.fullmatch(r"-?\d+", v or "")
        return int(v) if m else v
    out: dict = {}
    for t in trees:
        if t["tag"] != "interpretation":
            continue
        settings = {}
        for c in t["children"]:
            if c["tag"] == "rules":
                for s in c["children"]:
                    if s["tag"] == "set":
                        name = setting_name(s["attrs"]["rule"])
                        settings[name] = coerce(s["attrs"].get("to", ""))
        out[t["attrs"]["id"]] = {
            "lang": t["attrs"].get("lang", ""),
            "restrict": [r for r in t["attrs"].get("restrict", "").split(",") if r],
            "settings": settings,
        }
    return out


#: (tag, type) -> what the quality hands over. Only entries that create a
#: *thing* are listed; ATTRIBUTE/SKILL/RULE modifiers are handled elsewhere as
#: bonuses, and CHOICE refs are a prompt rather than a fixed grant.
GRANT_KINDS = {
    ("itemmod", "SIN"): "sin",
    ("itemmod", "QUALITY"): "quality",
    ("itemmod", "GEAR"): "gear",
    ("itemmod", "CRITTER_POWER"): "critterPower",
    ("itemmod", "METAECHO"): "echo",
    # NOT allowmod: that is permission to learn something, not a gift of it.
    # `sourceror` allowing the Hyperthreading complex form does not hand it over.
}


def parse_quality_meta(trees: list[dict], book: str) -> dict:
    """qualities*.xml -> {catalog_id: {karma, positive, max, multi, subOptions{}, raw}}."""
    out: dict = {}
    for t in trees:
        if t["tag"] != "quality":
            continue
        a = t["attrs"]
        if a.get("lang") not in (None, "", "en"):
            continue
        sub = {}
        for ch in _choices(t):
            for so in ch.get("children", []):
                if so["tag"] == "subOption":
                    sub[so["attrs"].get("id")] = {"karma": _int(so["attrs"].get("cost"))}
            if ch["tag"] == "subOption":       # some files put subOption directly
                sub[ch["attrs"].get("id")] = {"karma": _int(ch["attrs"].get("cost"))}
        # Things a quality HANDS OVER, as opposed to the modifiers it applies.
        # SINner declares <itemmod type="SIN" ref="REAL_SIN"/>; Shifter hands
        # out four further qualities; the metagenetic ones grant natural
        # weapons as gear. Read the declarations rather than naming qualities
        # in code, so a new book works without a change here.
        grants: dict = {}
        for mods in t.get("children", []):
            if mods["tag"] != "modifications":
                continue
            for m in mods.get("children", []):
                ma = m.get("attrs", {})
                kind = GRANT_KINDS.get((m["tag"], ma.get("type")))
                ref = ma.get("ref")
                if not kind or not ref or ref.startswith("CHOICE"):
                    continue
                grants.setdefault(kind, [])
                if ref not in grants[kind]:
                    grants[kind].append(ref)
        out[a["id"]] = {
            **({"grants": grants} if grants else {}),
            "karma": _int(a.get("karma")),
            "positive": a.get("pos") == "true",
            "type": a.get("type", "NORMAL"),
            "max": _int(a.get("max"), 1),
            "multi": a.get("multi") == "y",
            "book": book,
            "subOptions": sub,
            "hasChoices": bool(_choices(t)),
            "raw": t,
        }
    return out


def parse_lifestyles(trees: list[dict], i18n: dict) -> dict:
    out: dict = {}
    for t in trees:
        if t["tag"] != "lifestyle":
            continue
        a = t["attrs"]
        text = i18n.get(a["id"]) or {}
        out[a["id"]] = {"name": text.get("name") or a["id"].title(),
                        "cost": _int(a.get("cost")), "lp": _int(a.get("lp"))}
    return out


def parse_contacts(trees: list[dict], i18n: dict) -> dict:
    """contacts.xml -> archetypes WITH attribute/skill blocks (previously dropped)."""
    out: dict = {}
    for t in trees:
        if t["tag"] != "npc":
            continue
        a = t["attrs"]
        text = i18n.get(a["id"]) or i18n.get(a["id"].lower()) or {}
        attrs = {}
        skills = {}
        types: list = []
        for c in t["children"]:
            if c["tag"] == "types":
                types = [x for x in c["text"].split(",") if x]
            elif c["tag"] == "attributes":
                for at in c["children"]:
                    code = ATTR_CODE.get(at["attrs"].get("id", ""))
                    if code:
                        attrs[code] = _int(at["attrs"].get("value"))
            elif c["tag"] == "skills":
                for sk in c["children"]:
                    skills[sk["attrs"].get("ref")] = _int(sk["attrs"].get("value"))
        out[a["id"]] = {"name": text.get("name") or a["id"].title(),
                        "rating": _int(a.get("rating"), 1), "types": types,
                        "attributes": attrs, "skills": skills, "raw": t}
    return out


#: <valmod type="CREATION_POINTS" ref="..."> -> chargen budget field
_CREATION_POINT_FIELD = {
    "NUYEN": "nuyen",
    "RESOURCES": "nuyen",
    "CONTACT_POINTS": "contactPoints",
    "KARMA": "karma",
    "ATTRIBUTE_POINTS": "attributePoints",
    "SKILL_POINTS": "skillPoints",
    "ADJUSTMENT_POINTS": "adjustmentPoints",
    "SPECIAL_POINTS": "adjustmentPoints",
}


def lifemod_grants(tree: dict) -> dict:
    """Sum a life module's unconditional budget grants.

    ``<choices>`` declares the player's "choose one" options and ``<selmod>``
    wraps mutually exclusive alternatives — counting either would over-grant, so
    both are skipped and left in ``raw`` for the UI to resolve. A top-level
    ``valmod`` of type ATTRIBUTE or SKILL (typically ``ref="CHOICE"``, pointing
    at one of those choices) is worth one point of the matching pool.
    """
    grants: dict[str, int] = {}

    def add(field: str, raw_value) -> None:
        try:
            grants[field] = grants.get(field, 0) + int(float(raw_value or 0))
        except (TypeError, ValueError):
            pass

    for node in tree.get("children", []):
        if node["tag"] == "choices":
            continue
        stack = [node]
        while stack:
            n = stack.pop()
            if n["tag"] == "selmod":
                continue                        # pick-one, not cumulative
            a = n.get("attrs", {})
            kind = (a.get("type") or "").upper()
            if kind == "CREATION_POINTS":
                field = _CREATION_POINT_FIELD.get((a.get("ref") or "").upper())
                if field:
                    add(field, a.get("value"))
            elif kind == "ATTRIBUTE":
                add("attributePoints", a.get("value"))
            elif kind == "SKILL" and (a.get("ref") or "").lower() not in ("knowledge", "language"):
                add("skillPoints", a.get("value"))
            stack.extend(n.get("children", []))
    return {k: v for k, v in grants.items() if v}


def parse_lifepath(trees: list[dict], i18n: dict, book: str) -> dict:
    """lifepath*.xml -> {id: {name, stage, page, grants, raw}}.

    German-only modules are skipped: Commlink6 ships 84 of them in
    ``lifemods.xml`` with German ids and no English i18n, and this project
    deliberately imports English books only.
    """
    out: dict = {}
    for t in trees:
        if t["tag"] != "lifemod":
            continue
        a = t["attrs"]
        text = i18n.get(a["id"]) or i18n.get(a["id"].lower()) or {}
        if not text.get("name"):
            continue                            # skip German-only modules
        out[a["id"]] = {"name": text["name"], "stage": a.get("type", "ADULT"),
                        "page": text.get("page", ""), "desc": text.get("desc", ""),
                        "grants": lifemod_grants(t), "book": book, "raw": t}
    return out


#: Books whose mentor-spirit lists are English.
MENTOR_BOOKS = ["core", "street_wyrd", "hack_slash", "smooth_operations", "other_us"]


def parse_mentor_spirits(trees: list[dict], book: str, parent: dict) -> dict:
    """mentorspirits.xml -> qualityMeta entries for each individual spirit.

    Commlink6 models a mentor spirit as its own entity, but Shadowrun prices it
    as one quality — core p74: "Mentor Spirit ... Cost: 10 Karma" — with the
    particular spirit as the choice. Our packs flatten the spirits into
    individual quality items, which therefore arrive with no karma of their own
    and (wrongly) categorised as negative. Giving each one the parent quality's
    cost and sign is what stops "Bear" from paying the character 0 karma to take.

    :param parent: the ``mentor_spirit`` / ``paragon`` qualityMeta entry
    """
    karma = parent.get("karma", 10)
    positive = parent.get("positive", True)
    out: dict = {}
    for t in trees:
        if t["tag"] != "mentorspirit":
            continue
        out[t["attrs"]["id"]] = {
            "karma": karma, "positive": positive, "max": 1, "multi": False,
            "book": book, "mentorSpirit": True, "subOptions": {}, "raw": t,
        }
    return out
