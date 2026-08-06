"""Convert a Commlink6 record (from extractor.commlink6.read_book) into an
SR6-eden-Forge item. LOSSLESS: the entire Commlink6 payload is stored verbatim
under system._cl6 (id, category, attrs, all nested stat elements, wifi, page);
on top of that we derive the standard Eden fields (type/subtype/price/avail +
per-type weapon/armor/matrix stats) the app and export already use. Nothing from
Commlink6 is dropped."""
from __future__ import annotations

import re
from datetime import date

from extractor.eden_codes import map_code

_TODAY = date.today().isoformat()

# Commlink6 book slug -> our registered book slug (keep cl6 attribution, our slugs)
CL6_TO_OUR_BOOK = {
    "core": "corebook", "sif_new_orleans": "shadows_new_orleans",
    "kechibi": "kechibi_code", "krime": "krime_katalog", "emerald": "emerald_city",
    # direct 1:1 (lofwyr, bestial_nature, deadly_arts, double_clutch, …) keep slug
}

# Commlink6 data category -> (our domain, our category-file stem)
CAT_MAP = {
    "gear_firearms": ("gear", "weapons_firearms"),
    "gear_melee": ("gear", "weapons_close_combat"),
    "gear_weapons": ("gear", "weapons_ranged"),
    "gear_explosives": ("gear", "weapons_special"),
    "gear_armor": ("gear", "armor"),
    "gear_armor_accessories": ("gear", "armor_additions"),
    "gear_clothing": ("gear", "clothing"),
    "gear_electronics": ("gear", "electronics"),
    "gear_electronics_seattle": ("gear", "electronics"),
    "gear_sensors_and_co": ("gear", "electronics"),
    "gear_software": ("gear", "software"),
    "gear_magical": ("gear", "magical"),
    "gear_tools": ("gear", "tools"),
    "gear_bioware": ("gear", "bioware"),
    "gear_cyberware": ("gear", "cyberware"),
    "gear_bodyware": ("gear", "cyberware"),
    "gear_cyberlimbs": ("gear", "cyberware"),
    "gear_biotech": ("gear", "biotech"),
    "gear_ammunition": ("gear", "ammo"),
    "ammunition_types": ("gear", "ammo"),
    "gear_security_survival": ("gear", "survival"),
    "gear_espionage": ("gear", "electronics"),
    "gear_seattle": ("gear", "electronics"),
    "gear_drugs": ("gear", "chemicals"),
    "gear_geneware": ("gear", "bioware"),
    "gear_nanoware": ("gear", "bioware"),
    "gear_revolution_arms": ("gear", "weapons_firearms"),
    "gear_codemods": ("gear", "software"),
    "gear_vehicle_accessories": ("vehicles", "vehicles"),
    "qualities-metagenetic": ("qualities", "qualities"),
    "qualities-infected": ("qualities", "qualities"),
    "qualities_ai": ("qualities", "qualities"),
    "weapon_modifications": ("gear", "weapon_accessories"),
    "gear_firearms_accessories": ("gear", "weapon_accessories"),
    "item_enhancements": ("gear", "electronics"),
    "gear_drones": ("vehicles", "vehicles"),
    "gear_drones_seattle": ("vehicles", "vehicles"),
    "gear_vehicles": ("vehicles", "vehicles"),
    "spells": ("spells", "spells"),
    "rituals": ("rituals", "rituals"),
    "adeptpowers": ("adept_powers", "adept_powers"),
    "qualities": ("qualities", "qualities"),
    "qualities_seattle": ("qualities", "qualities"),
    "qualities_berlin": ("qualities", "qualities"),
    "complexforms": ("complexforms", "complexforms"),
    "echoes": ("echoes", "echoes"),
    "critterpower": ("critter_powers", "critter_powers"),
    "spritepower": ("sprite_powers", "sprite_powers"),
    "metamagics": ("metamagics", "metamagics"),
    "foci": ("foci", "foci"),
    "contacts": ("contacts", "contacts"),
    "lifestyles": ("lifestyles", "lifestyles"),
    "skills": ("skills", "skills"),
    "martialarts": ("martial_techniques", "martial_techniques"),
    "techniques": ("martial_techniques", "martial_techniques"),
    "npcs": ("npcs", "npc"),
    "critters": ("critters", "critter"),
    "critters_awakened": ("critters", "critter"),
    "spirits": ("spirits", "spirit"),
    "mentorspirits": ("qualities", "qualities"),
    "sprites": ("critters", "critter"),
}

_MODES = ("SS", "SA", "BF", "FA")

# Commlink6's own text has a few defects we correct on import:
#  * SR6 capitalises SIN-derived words (SIN = System Identification Number), so
#    "Sinner" must read "SINner"; the source lowercases them.
#  * two entries have literal U+FFFD bytes baked into the jar (upstream data
#    corruption, not an encoding problem on our side).
_NAME_FIXES = {
    "Sinner": "SINner",
    "Sinless": "SINless",
    "Sinners": "SINners",
    "Real World Na�vet�": "Real World Naïveté",
}
# whole-word casing repairs applied inside longer names
_WORD_FIXES = [
    (re.compile(r"\bSinner(s?)\b"), r"SINner\1"),
    (re.compile(r"\bSinless\b"), "SINless"),
    (re.compile(r"\bSin\b(?!\s*[a-z])"), "SIN"),
]


def fix_name(name: str) -> str:
    if not name:
        return name
    if name in _NAME_FIXES:
        return _NAME_FIXES[name]
    for rx, repl in _WORD_FIXES:
        name = rx.sub(repl, name)
    return name

# Commlink6 lumps many enhancements under type=ACCESSORY and distinguishes them by
# subtype; our app groups by type ("Weapon Accessory"), so re-derive the display
# type from the subtype (raw cl6 type preserved in system._cl6). WEAPON_ACCESSORY
# / FIREARMS* / blank stay ACCESSORY (genuine weapon accessories & firearm mods).
_ACCESSORY_RETYPE = {
    "VISION_ENHANCEMENT": "ELECTRONICS", "AUDIO_ENHANCEMENT": "ELECTRONICS",
    "IMAGING": "ELECTRONICS", "ELECTRONIC_ACCESSORIES": "ELECTRONICS",
    "SENSOR": "ELECTRONICS", "OPTICAL": "ELECTRONICS",
    "CYBER_LIMB_ACCESSORY": "CYBERWARE", "CYBER_LIMB_ENHANCEMENT": "CYBERWARE",
    "VEHICLE_ACCESSORY": "VEHICLES", "LAUNCHERS": "WEAPON_FIREARMS",
}


def _retype_accessory(sysd):
    if sysd.get("type") != "ACCESSORY":
        return
    sub = sysd.get("subtype") or ""
    if sub.startswith("ARMOR"):
        sysd["type"] = "ARMOR_ADDITION"
    elif sub in _ACCESSORY_RETYPE:
        sysd["type"] = _ACCESSORY_RETYPE[sub]

# default system.type for cl6 categories that omit a type attr, keyed by target file
_FILE_DEFAULT_TYPE = {
    "ammo": "AMMUNITION", "weapon_accessories": "ACCESSORY", "armor_additions": "ARMOR_ADDITION",
    "weapons_firearms": "WEAPON_FIREARMS", "weapons_close_combat": "WEAPON_CLOSE_COMBAT",
    "weapons_ranged": "WEAPON_RANGED", "weapons_special": "WEAPON_SPECIAL", "armor": "ARMOR",
    "electronics": "ELECTRONICS", "software": "SOFTWARE", "magical": "MAGICAL", "tools": "TOOLS",
    "bioware": "BIOWARE", "cyberware": "CYBERWARE", "chemicals": "CHEMICALS", "clothing": "ARMOR",
    "biotech": "BIOLOGY", "survival": "SURVIVAL", "vehicles": "VEHICLES",
}


def _int(s, default=0):
    m = re.search(r"-?\d+", str(s or ""))
    return int(m.group()) if m else default


def _avail(s):
    s = str(s or "").strip()
    return _int(s), s            # numeric + original string (keeps L/R/F letters)


def _dmg(s):
    s = str(s or "").strip()
    n = _int(s)
    stun = bool(re.search(r"\d+\s*S", s))
    flags = re.findall(r"\(([a-z]+)\)", s)   # (e) electrical, (f) flechette, …
    return n, stun, s, flags


def _attack(s):
    if not s:
        return [0, 0, 0, 0, 0]
    vals = [_int(p) for p in str(s).split(",")]
    return (vals + [0, 0, 0, 0, 0])[:5]        # normalize to exactly 5 ranges


def _modes(s):
    present = set(re.split(r"[\/,]", str(s or "").strip()))
    return {m: (m in present) for m in _MODES}


def _ammo(s):
    s = str(s or "").strip()
    t = re.search(r"\(([a-z]+)\)", s)
    return _int(s), (t.group(1) if t else "")


def _derive_nongear(domain, a, st, sysd):
    """Map cl6 element attributes into our Eden fields for non-gear domains."""
    if domain == "spells":
        sysd.update(category=a.get("cat", ""), range=a.get("range", ""),
                    type=a.get("type", ""), duration=a.get("dur", ""),
                    drain=_int(a.get("drain")), damage=a.get("dmg", ""))
    elif domain == "qualities":
        sysd.update(category=("positive" if a.get("pos") == "true" else "negative"),
                    value=_int(a.get("karma")), subtype=a.get("type", ""))
    elif domain == "rituals":
        feats = [v for k, v in st.items() if k.startswith("ritualfeature")]
        sysd.update(threshold=_int(a.get("thr")), features={f: True for f in feats})
    elif domain == "adept_powers":
        try:
            cost = float(a.get("cost", 0) or 0)
        except ValueError:
            cost = 0
        sysd.update(cost=cost, hasLevel=(a.get("hasLevel") == "true"),
                    activation=a.get("act", ""))
    elif domain in ("critter_powers", "sprite_powers"):
        sysd.update(type=a.get("type", ""), action=a.get("action", ""),
                    range=a.get("range", ""), duration=a.get("dur", ""))
    elif domain == "complexforms":
        sysd.update(duration=a.get("dur", ""), fading=str(a.get("fad", "")),
                    target=a.get("target", ""))


# gear type -> the gear category file it belongs in (used to route items that
# leaked into the vehicles domain via cl6's gear_vehicles/gear_drones categories
# back to gear). Vehicle-mounted weapons keep type WEAPON_VEHICLE and go to gear.
_TYPE_TO_GEAR_FILE = {
    "WEAPON_FIREARMS": "weapons_firearms", "WEAPON_VEHICLE": "weapons_firearms",
    "WEAPON_CLOSE_COMBAT": "weapons_close_combat", "WEAPON_RANGED": "weapons_ranged",
    "WEAPON_SPECIAL": "weapons_special", "AMMUNITION": "ammo", "ACCESSORY": "weapon_accessories",
    "ARMOR": "armor", "ARMOR_ADDITION": "armor_additions", "ELECTRONICS": "electronics",
    "SOFTWARE": "software", "TOOLS": "tools", "CYBERWARE": "cyberware", "BIOWARE": "bioware",
    "CHEMICALS": "chemicals", "MAGICAL": "magical", "SURVIVAL": "survival",
}


def _route_by_type(domain, file, sysd):
    """Route by the item's final type at the gear<->vehicles boundary. Vehicles,
    drones (any size) and vehicle mods (MOD_*) live in the vehicles domain;
    gear/weapon-typed items that arrived via a vehicle category go back to gear."""
    t = sysd.get("type", "") or ""
    if t == "DRONE_MINI":
        sysd["type"] = t = "DRONE"
    is_vehicular = t in ("VEHICLES", "DRONES") or t.startswith("DRONE") or t.startswith("MOD_")
    if is_vehicular:
        return "vehicles", "vehicles"
    if domain == "vehicles" and t in _TYPE_TO_GEAR_FILE:
        return "gear", _TYPE_TO_GEAR_FILE[t]
    return domain, file


def our_book(cl6_book):
    return CL6_TO_OUR_BOOK.get(cl6_book, cl6_book)


def target(category):
    return CAT_MAP.get(category)          # (domain, file) or None


def to_item(rec, cl6_book):
    """rec = record from commlink6.read_book; returns (domain, file, item). Unmapped
    categories go to a lossless catch-all domain so nothing is dropped."""
    tgt = target(rec["category"])
    domain, file = tgt if tgt else ("commlink6_extra", rec["category"])
    st = rec["stats"]
    # some cl6 categories carry no `type` attr (ammo warheads, weapon mods); derive
    # a default from the target file so the schema's required `type` is satisfied.
    if not rec.get("type"):
        rec["type"] = _FILE_DEFAULT_TYPE.get(file, rec.get("type", ""))
    availn, availd = _avail(rec["avail"])
    sysd = {
        "type": rec["type"], "subtype": rec["subtype"],
        "price": _int(rec["price"], 0), "priceDef": str(rec["price"] or ""),
        "avail": availn, "availDef": availd,
        "description": rec["desc"], "notes": "", "wifi": rec["wifi"],
        # ---- LOSSLESS raw Commlink6 payload ----
        "_cl6": {"id": rec["id"], "category": rec["category"], "book": cl6_book,
                 "attrs": rec["attrs"], "stats": st, "page": rec["page"]},
    }
    # derived per-type fields from the nested cl6 stat elements
    if "weapon.dmg" in st or "weapon.attack" in st:
        dn, stun, ddef, flags = _dmg(st.get("weapon.dmg"))
        cap, atype = _ammo(st.get("weapon.ammo"))
        sysd.update(skill=st.get("weapon.skill", ""), spec=st.get("weapon.spec", ""),
                    dmg=dn, stun=stun, dmgDef=ddef, dmgFlags=flags,
                    modes=_modes(st.get("weapon.mode")), attackRating=_attack(st.get("weapon.attack")),
                    ammocap=cap, ammoType=atype)
    if "armor.rating" in st:
        sysd["defense"] = _int(st.get("armor.rating"))
        if "armor.social" in st:
            sysd["social"] = _int(st.get("armor.social"))
    if "matrix.d" in st or "matrix.devrat" in st:
        sysd.update(d=_int(st.get("matrix.d")), f=_int(st.get("matrix.f")),
                    progSlots=_int(st.get("matrix.programs")), rating=_int(st.get("matrix.devrat")))
    _derive_nongear(domain, rec["attrs"], st, sysd)
    _retype_accessory(sysd)
    domain, file = _route_by_type(domain, file, sysd)
    # adopt shadowrun6-eden codes (raw cl6 kept in system._cl6)
    sysd["type"], sysd["subtype"] = map_code(sysd.get("type"), sysd.get("subtype"))
    # eden's catalog field (see EDEN_CATALOG_FIELD in the module config):
    # the RAW upstream id, because eden's own importer matches items on it
    # system.catalog_id, and the chargen engine references qualities the same way.
    sysd["genesisID"] = rec["id"]
    item = {
        "id": f"cl6_{rec['id']}".replace("-", "_").lower(),   # slug: lowercase, no '-'
        "name": fix_name(rec["name"]),
        "system": sysd,
        "meta": {"book": our_book(cl6_book), "page": _int(rec["page"]) or 1,
                 "source": "commlink6", "qaStatus": "extracted",
                 "extractedAt": _TODAY, "extractorVersion": "commlink6-1.14.0"},
    }
    return domain, file, item
