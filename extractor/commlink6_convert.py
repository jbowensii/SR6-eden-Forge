"""Convert a Commlink6 record (from extractor.commlink6.read_book) into an
SR6-eden-Forge item. LOSSLESS: the entire Commlink6 payload is stored verbatim
under system._cl6 (id, category, attrs, all nested stat elements, wifi, page);
on top of that we derive the standard Eden fields (type/subtype/price/avail +
per-type weapon/armor/matrix stats) the app and export already use. Nothing from
Commlink6 is dropped."""
from __future__ import annotations

import re
from datetime import date

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
    item = {
        "id": f"cl6_{rec['id']}",
        "name": rec["name"],
        "system": sysd,
        "meta": {"book": our_book(cl6_book), "page": _int(rec["page"]) or 1,
                 "source": "commlink6", "qaStatus": "extracted",
                 "extractedAt": _TODAY, "extractorVersion": "commlink6-1.14.0"},
    }
    return domain, file, item
