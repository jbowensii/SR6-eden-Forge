from extractor.rowengine import RowSpec, parse_block

ARMOR = RowSpec(columns=["defense", "capacity", "avail", "cost"], defaults={"type": "ARMOR"})
MOD = RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "ARMOR_ADDITION"})
ACCESSORY = RowSpec(columns=["mount", "avail", "cost"], defaults={"type": "ACCESSORY"})
BE_GEAR = RowSpec(columns=["ratingspan", "avail", "cost"], defaults={"type": "TOOLS"})
CREDSTICK = RowSpec(columns=["note:Max_value", "avail", "cost"], defaults={"type": "ELECTRONICS"})
LIMB = RowSpec(
    columns=["essence", "avail", "pricecapnote:Synthetic", "pricecap"],
    defaults={"type": "CYBERWARE"},
)
BIOWARE = RowSpec(columns=["ratingspan", "essence", "avail", "cost"], defaults={"type": "BIOWARE"})


def one(lines, spec):
    rows = parse_block(lines, spec)
    assert len(rows) == 1, rows
    return rows[0]


def test_armor_row_with_plus_defense():
    name, system = one(["Fictional Jacket +4 8 2 1,000¥"], ARMOR)
    assert name == "Fictional Jacket"
    assert system["defense"] == 4 and system["capacity"] == 8 and system["price"] == 1000


def test_dash_avail_allowed():
    name, system = one(["w/helmet +2 6 — 500¥"], ARMOR)
    assert system["avail"] == 0 and system["availDef"] == "—"


def test_rating_capacity_and_formula_cost():
    name, system = one(["Fictional Protection [Rating] 3 Rating x 250¥"], MOD)
    assert system["needsRating"] is True
    assert system["capacity"] == 0
    assert system["price"] == 0 and system["priceDef"] == "Rating x 250¥"


def test_plus_prefixed_cost():
    name, system = one(["Fictional Smartlink — 1(L) +500¥"], ACCESSORY)
    assert system["price"] == 500


def test_mount_becomes_note():
    name, system = one(["Fictional Sight Top or Under 1 125¥"], ACCESSORY)
    assert name == "Fictional Sight"
    assert system["notes"] == "Mount: Top or Under"


def test_mount_dash_no_note():
    name, system = one(["Fictional Holster — 1 150¥"], ACCESSORY)
    assert "notes" not in system


def test_ratingspan_na_and_span_and_int():
    _, na = one(["Fictional Picker n/a 4(L) 500¥"], BE_GEAR)
    assert "rating" not in na and "needsRating" not in na
    _, span = one(["Fictional Molder 1—4 6(I) Rating x 500¥"], BE_GEAR)
    assert span["needsRating"] is True
    _, fixed = one(["Fictional Gadget 3 2 100¥"], BE_GEAR)
    assert fixed["rating"] == 3


def test_note_column():
    name, system = one(["Standard 5,000¥ 1 5¥"], CREDSTICK)
    assert system["notes"] == "Max value: 5,000¥"
    assert system["price"] == 5


def test_pricecap_pair():
    name, system = one(["Fictional Arm 1 4 20,000¥(8) 15,000¥(15)"], LIMB)
    assert system["essence"] == 1.0
    assert system["price"] == 15000 and system["capacity"] == 15
    assert system["notes"] == "Synthetic: 20,000¥(8)"


def test_bioware_formula_essence():
    name, system = one(["Fictional Pump 1—3 Rating x 0.75 5(I) Rating x 55,000¥"], BIOWARE)
    assert system["needsRating"] is True
    assert system["essence"] == 0
    assert system["priceDef"] == "Rating x 55,000¥"
    assert "Essence: Rating x 0.75" in system["notes"]


def test_defaults_notes_are_prepended():
    spec = RowSpec(columns=["mount", "avail", "cost"], defaults={"type": "ACCESSORY", "notes": "Base note"})
    name, system = one(["Fictional Rail Under 2 300¥"], spec)
    assert system["notes"] == "Base note; Mount: Under"


def test_belt_fed_ammo_and_special_dv():
    from extractor.rowengine import RowSpec

    spec = RowSpec(columns=["dv", "modes", "ar", "ammo", "avail", "cost"], defaults={"type": "WEAPON_FIREARMS"})
    _, mg = one(["Fictional LMG 4P SA/BF/FA 2/11/12/7/3 50(c) or 100(belt) 4(L) 4,175¥"], spec)
    assert mg["ammocap"] == 50 and "Ammo: 50(c) or 100(belt)" in mg["notes"]
    _, squirt = one(["Fictional Squirter Special SS 8/12/9/—/— 20(c) 3(L) 560¥"], spec)
    assert squirt["dmgDef"] == "Special" and squirt["dmg"] == 0
    _, dart = one(["Fictional Dart Gun 1P + special SS 9/10/8/—/— 5(c) 2 510¥"], spec)
    assert dart["dmgDef"] == "1P + special" and dart["dmg"] == 1


def test_allow_tail_discards_interleaved_prose():
    spec = RowSpec(columns=["avail", "cost"], defaults={"type": "SECURITY"}, allow_tail=True)
    name, system = one(["Fictional Maglock 3 Rating x 100¥ to melt metals, either to cut through"], spec)
    assert name == "Fictional Maglock"
    assert system["priceDef"] == "Rating x 100¥"


def test_capacity_rating_word_and_bracket_int():
    spec = RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "ELECTRONICS"})
    _, arr = one(["Fictional Array Rating 3 Rating x 1,000¥"], spec)
    assert arr["needsRating"] is True
    _, single = one(["Fictional Sensor [1] 2 Capacity x 100¥"], spec)
    assert single["capacity"] == 1 and single["priceDef"] == "Capacity x 100¥"


def test_attack_rating_capped_at_five():
    from extractor.columns import resolve
    assert resolve("ar").convert("8/10/6/0/0/0")["attackRating"] == [8, 10, 6, 0, 0]
    assert resolve("ar").convert("9")["attackRating"] == [9, 0, 0, 0, 0]
