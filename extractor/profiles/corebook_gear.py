"""Parser profile: SR6 Core Rulebook (CAT28000), gear chapter (pages 245-304).

Weapons portion. Tables the layout makes unparseable (formula stats, names
wrapped around their data line, matrix tables) are covered by MANUAL_ITEMS;
partially-parsed artifacts of those rows are dropped via EXCLUDE; names split
by the two-column layout are corrected via RENAMES.
"""

from __future__ import annotations

from extractor.profiles import TableSpec
from extractor.rowengine import RowSpec

FIREARM = ["dv", "modes", "ar", "ammo", "avail", "cost"]
MELEE = ["dv", "ar", "avail", "cost"]
MELEE_TYPED = ["note:Type", "dv", "ar", "avail", "cost"]
LAUNCHER = ["text:dmgDef", "modes", "ar", "ammo", "avail", "cost"]
ACCESSORY_ROW = ["mount", "avail", "cost"]


def firearm(subtype: str) -> RowSpec:
    return RowSpec(columns=FIREARM, defaults={"type": "WEAPON_FIREARMS", "subtype": subtype, "skill": "firearms"})


# MELEE is shared across calls, and deliberately: RowSpec only ever reads
# `columns` (regex() builds a pattern from it), so there is nothing to mutate
# and a per-call copy of four strings would be noise.
def melee(subtype: str, columns=MELEE) -> RowSpec:  # pylint: disable=dangerous-default-value
    return RowSpec(columns=columns, defaults={"type": "WEAPON_CLOSE_COMBAT", "subtype": subtype, "skill": "close_combat"})


TABLES = [
    # ── close combat ────────────────────────────────────────────
    TableSpec("weapons_close_combat", [250], r"^blades$", [r"^clubs$"], melee("BLADES")),
    TableSpec("weapons_close_combat", [250], r"^clubs$", [], melee("CLUBS")),
    TableSpec("weapons_close_combat", [251], r"^other melee weapons$", [r"^throwing weapons/projectiles$"], melee("OTHER_CLOSE", MELEE_TYPED)),
    # ── ranged (throwing + crossbows share one table) ───────────
    TableSpec(
        "weapons_ranged",
        [251],
        r"^throwing weapons/projectiles$",
        [r"^tasers$"],
        RowSpec(columns=MELEE, defaults={"type": "WEAPON_RANGED", "subtype": "THROWING", "skill": "athletics"}),
    ),
    # ── firearms ────────────────────────────────────────────────
    TableSpec("weapons_firearms", [251, 252], r"^tasers$", [r"^Wireless bonus"], firearm("TASERS")),
    TableSpec("weapons_firearms", [254], r"^hold-outs$", [r"^light pistols$"], firearm("HOLDOUTS")),
    TableSpec("weapons_firearms", [254], r"^light pistols$", [], firearm("PISTOLS_LIGHT")),
    TableSpec("weapons_firearms", [255], r"^machine pistols$", [], firearm("MACHINE_PISTOLS")),
    TableSpec("weapons_firearms", [256], r"^heavy pistols$", [r"^submachine guns$"], firearm("PISTOLS_HEAVY")),
    TableSpec("weapons_firearms", [256], r"^submachine guns$", [], firearm("SUBMACHINE_GUNS")),
    TableSpec("weapons_firearms", [257], r"^shotguns$", [], firearm("SHOTGUNS")),
    TableSpec("weapons_firearms", [259], r"^rifles$", [r"^machine guns$"], firearm("RIFLE_ASSAULT")),
    TableSpec("weapons_firearms", [259], r"^machine guns$", [r"^special weapons"], firearm("MACHINE_GUNS")),
    TableSpec(
        "weapons_special",
        [259, 260],
        r"^special weapons \(Exotic\)$",
        [r"^launchers$"],
        RowSpec(columns=FIREARM, defaults={"type": "WEAPON_SPECIAL", "subtype": "OTHER_SPECIAL", "skill": "exotic_weapons"}),
    ),
    TableSpec(
        "weapons_firearms",
        [260],
        r"^launchers$",
        [r"^Wireless bonus"],
        RowSpec(columns=LAUNCHER, defaults={"type": "WEAPON_FIREARMS", "subtype": "LAUNCHERS", "skill": "firearms"}),
    ),
    # ── accessories ─────────────────────────────────────────────
    TableSpec(
        "weapon_accessories",
        [262],
        r"^weapon accessories$",
        [r"^tion and"],
        RowSpec(columns=ACCESSORY_ROW, defaults={"type": "ACCESSORY", "subtype": "FIREARMS_ACCESSORY"}),
    ),
    # ── clothing & armor (p266-268) ─────────────────────────────
    TableSpec(
        "clothing",
        [266],
        r"^clothes$",
        [r"^Armor\b"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "ARMOR", "subtype": "ARMOR_CLOTHES"}, allow_tail=True),
    ),
    TableSpec(
        "armor",
        [267],
        r"^armor$",
        [r"^armor modifications$"],
        RowSpec(columns=["defense", "capacity", "avail", "cost"], defaults={"type": "ARMOR", "subtype": "ARMOR_BODY"}),
    ),
    TableSpec(
        "armor_additions",
        [267],
        r"^armor modifications$",
        [],
        RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "ARMOR_ADDITION", "subtype": "MODIFICATION"}, allow_tail=True),
    ),
    TableSpec(
        "armor_additions",
        [268],
        r"^helmets and shields$",
        [],
        RowSpec(columns=["defense", "capacity", "avail", "cost"], defaults={"type": "ARMOR_ADDITION", "subtype": "ARMOR_HELMET"}),
    ),
    # ── electronics (p268-274) ──────────────────────────────────
    TableSpec(
        "electronics",
        [268],
        r"^ITEM DEVICE RATING ATTRIBUTES \(D/F\) AVAIL COST$",
        [],
        RowSpec(columns=["int:rating", "onoff:d:f", "int:progSlots", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "COMMLINK"}),
    ),
    TableSpec(
        "electronics",
        [268],
        r"^ITEM DEVICE RATING ATTRIBUTES \(A/S\) AVAIL COST$",
        [],
        RowSpec(columns=["int:rating", "onoff:a:s", "int:progSlots", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "CYBERDECK"}),
    ),
    TableSpec(
        "electronics",
        [269],
        r"^accessories$",
        [],
        RowSpec(columns=["int:rating", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "ELECTRONIC_ACCESSORIES"}, allow_tail=True),
    ),
    TableSpec(
        "electronics",
        [270],
        r"^rfid tags$",
        [],
        RowSpec(columns=["int:rating", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "RFID", "notes": "Price per 10 tags"}, allow_tail=True),
    ),
    TableSpec(
        "electronics",
        [272],
        r"^Communications and Countermeasures$",
        [],
        RowSpec(columns=["avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "COMMUNICATION"}, allow_tail=True),
    ),
    TableSpec(
        "software",
        [273],
        r"^software$",
        [r"^credsticks$"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "SOFTWARE", "subtype": "SOFTWARE"}, allow_tail=True),
    ),
    TableSpec(
        "electronics",
        [274],
        r"^credsticks$",
        [r"^identification$"],
        RowSpec(columns=["note:Max_value", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "ID_CREDIT"}),
    ),
    TableSpec(
        "electronics",
        [274],
        r"^identification$",
        [],
        RowSpec(columns=["avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "ID_CREDIT"}, allow_tail=True),
    ),
    # ── tools, optics, sensors (p275-279) ───────────────────────
    TableSpec(
        "tools",
        [275],
        r"^tools$",
        [r"^optical and$", r"^Optical and$"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "TOOLS", "subtype": "TOOLS"}, allow_tail=True),
    ),
    TableSpec(
        "electronics",
        [275, 276],
        r"^optical and imaging devices$|^DEVICE CAPACITY AVAIL COST$",
        [r"^visual enhancements$"],
        RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "OPTICAL"}, allow_tail=True),
    ),
    TableSpec(
        "electronics",
        [276],
        r"^visual enhancements$",
        [],
        RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "VISION_ENHANCEMENT"}, allow_tail=True),
    ),
    TableSpec(
        "electronics",
        [277],
        r"^audio enhancements$",
        [],
        RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "AUDIO_ENHANCEMENT"}, allow_tail=True),
    ),
    TableSpec(
        "electronics",
        [278],
        r"^sensors$",
        [r"^sensor functions$"],
        RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "SENSOR"}, allow_tail=True),
    ),
    TableSpec(
        "security",
        [279],
        r"^security and restraints$",
        [r"^breaking and$", r"^Breaking and$"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "ELECTRONICS", "subtype": "SECURITY"}, allow_tail=True),
    ),
    # ── B&E, chemicals, survival, biotech (p280-283) ────────────
    TableSpec(
        "tools",
        [280],
        r"^breaking and entering gear$",
        [r"^industrial chemicals$"],
        RowSpec(columns=["ratingspan", "avail", "cost"], defaults={"type": "TOOLS", "subtype": "BREAKING"}, allow_tail=True),
    ),
    TableSpec(
        "chemicals",
        [280],
        r"^industrial chemicals$",
        [r"^Survival Gear$"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "CHEMICALS", "subtype": "INDUSTRIAL_CHEMICALS"}, allow_tail=True),
    ),
    TableSpec(
        "survival",
        [281, 282],
        r"^survival gear$|^GEAR AVAIL COST\b",
        [r"^biotech$", r"^Medkit\b"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "SURVIVAL", "subtype": "SURVIVAL_GEAR"}, allow_tail=True),
    ),
    TableSpec(
        "biotech",
        [283],
        r"^biotech$",
        [r"^implant grades$"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "BIOLOGY", "subtype": "BIOTECH"}, allow_tail=True),
    ),
    # ── cyberware (p285-291) ────────────────────────────────────
    TableSpec(
        "cyberware",
        [285],
        r"^cyberjacks$",
        [r"^headware$"],
        RowSpec(columns=["onoff:d:f", "plusint:modifier", "avail", "essence", "cost"], defaults={"type": "CYBERWARE", "subtype": "CYBERJACK"}, allow_tail=True),
    ),
    TableSpec(
        "cyberware",
        [285],
        r"^headware$",
        [],
        RowSpec(columns=["essence", "capacity", "avail", "cost"], defaults={"type": "CYBERWARE", "subtype": "CYBER_HEADWARE"}, allow_tail=True),
    ),
    TableSpec(
        "cyberware",
        [286],
        r"^eyeware$",
        [],
        RowSpec(columns=["essence", "capacity", "avail", "cost"], defaults={"type": "CYBERWARE", "subtype": "CYBER_EYEWARE"}, allow_tail=True),
    ),
    TableSpec(
        "cyberware",
        [287],
        r"^earware$",
        [r"^bone lacing$"],
        RowSpec(columns=["essence", "capacity", "avail", "cost"], defaults={"type": "CYBERWARE", "subtype": "CYBER_EARWARE"}, allow_tail=True),
    ),
    TableSpec(
        "cyberware",
        [289],
        r"^bodyware$",
        [],
        RowSpec(columns=["essence", "capacity", "avail", "cost"], defaults={"type": "CYBERWARE", "subtype": "CYBER_BODYWARE"}, allow_tail=True),
    ),
    TableSpec(
        "cyberware",
        [290],
        r"^cyberlimb cost and capacity$",
        [r"^cyberlimb accessories$"],
        RowSpec(columns=["essence", "avail", "pricecapnote:Synthetic_(cost/capacity)", "pricecap"], defaults={"type": "CYBERWARE", "subtype": "CYBER_LIMBS", "notes": "Obvious limb price/capacity; see notes for synthetic"}, allow_tail=True),
    ),
    TableSpec(
        "cyberware",
        [290],
        r"^cyberlimb accessories$",
        [r"^cyberlimbs$"],
        RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "CYBERWARE", "subtype": "CYBER_LIMB_ACCESSORY"}, allow_tail=True),
    ),
    TableSpec(
        "cyberware",
        [291],
        r"^cyber implant weapons$",
        [r"^implant weapons stats$"],
        RowSpec(columns=["essence", "capacity", "avail", "cost"], defaults={"type": "CYBERWARE", "subtype": "CYBER_IMPLANT_WEAPON"}, allow_tail=True),
    ),
    # ── bioware (p294-295) ──────────────────────────────────────
    TableSpec(
        "bioware",
        [294],
        r"^bioware$",
        [r"^cultured bioware$"],
        RowSpec(columns=["ratingspan", "essence", "avail", "cost"], defaults={"type": "BIOWARE", "subtype": "BIOWARE_STANDARD"}, allow_tail=True),
    ),
    TableSpec(
        "bioware",
        [295],
        r"^cultured bioware$",
        [r"^magical goods table$"],
        RowSpec(columns=["ratingspan", "essence", "avail", "cost"], defaults={"type": "BIOWARE", "subtype": "BIOWARE_CULTURED"}, allow_tail=True),
    ),
    # ── magical goods (p295-296) ────────────────────────────────
    TableSpec(
        "magical",
        [295],
        r"^FORMULAE AVAILABILITY COST$",
        [r"^MAGICAL SUPPLIES"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "MAGICAL", "subtype": "MAGICAL_FORMULA"}, allow_tail=True),
    ),
    TableSpec(
        "magical",
        [295],
        r"^MAGICAL SUPPLIES AVAILABILITY COST$",
        [r"^Magical Goods$"],
        RowSpec(columns=["avail", "cost"], defaults={"type": "MAGICAL", "subtype": "MAGIC_SUPPLIES"}, allow_tail=True),
    ),
    # ── vehicles (p302-303) ─────────────────────────────────────
]

VEHICLE_COLS = ["onoff:handlOn:handlOff", "int:accOn", "int:spdiOn", "int:tspd", "int:bod", "int:arm", "int:pil", "int:sen", "seat", "avail", "cost"]


def _vehicle_table(page, header, subtype, vtype, kind="VEHICLES", stops=()):
    return TableSpec(
        "drones" if kind == "DRONES" else "vehicles",
        [page],
        header,
        list(stops),
        RowSpec(columns=VEHICLE_COLS, defaults={"type": kind, "subtype": subtype, "vtype": vtype}, allow_tail=True),
    )


TABLES += [
    _vehicle_table(302, r"^BIKES ACCEL TOP SPEED", "BIKES", "ground"),
    _vehicle_table(302, r"^CARS ACCEL TOP SPEED", "CARS", "ground"),
    _vehicle_table(302, r"^VANS OFF ROAD\) INTERVAL$", "TRUCKS", "ground"),
    _vehicle_table(302, r"^BOATS ACCEL TOP SPEED", "BOATS", "water"),
    _vehicle_table(302, r"^SUBMARINES HAND ACCEL", "SUBMARINES", "water"),
    _vehicle_table(303, r"^HAND ACCEL TOP SPEED BODY ARMOR PILOT SENSOR SEAT AVAIL COST$", "FIXED_WING", "air"),
    _vehicle_table(303, r"^ROTORCRAFT HAND ACCEL", "ROTORCRAFT", "air", stops=(r"^VTOL/VSTOL",)),
    _vehicle_table(303, r"^VTOL/VSTOL HAND ACCEL", "VTOL", "air"),
    _vehicle_table(303, r"^MICRODRONES ACCEL", "MICRODRONES", "ground", kind="DRONES"),
    _vehicle_table(303, r"^MINIDRONES ACCEL", "MINIDRONES", "ground", kind="DRONES"),
    _vehicle_table(303, r"^SMALL DRONES ACCEL", "SMALL_DRONES", "ground", kind="DRONES"),
    _vehicle_table(303, r"^MEDIUM DRONES ACCEL", "MEDIUM_DRONES", "ground", kind="DRONES"),
    _vehicle_table(303, r"^LARGE DRONES ACCEL", "LARGE_DRONES", "ground", kind="DRONES"),
]

# Correction hooks (RENAMES/OVERRIDES/EXCLUDE/MANUAL_ITEMS) load from
# data/_fixes/corebook_gear_fixes.py — they reference real book content and
# are never committed. See extractor/run.py:_load_fixes.
