from extractor.rowengine import RowSpec, parse_block

FIREARM = RowSpec(
    columns=["dv", "modes", "ar", "ammo", "avail", "cost"],
    defaults={"type": "WEAPON_FIREARMS", "skill": "firearms"},
)
MELEE = RowSpec(
    columns=["dv", "ar", "avail", "cost"],
    defaults={"type": "WEAPON_CLOSE_COMBAT", "skill": "close_combat"},
)
CYBER = RowSpec(
    columns=["essence", "capacity", "avail", "cost"],
    defaults={"type": "CYBERWARE"},
)


def test_simple_firearm_row():
    rows = parse_block(["Zapgun Mk1 3P SA/BF 10/10/8/—/— 15(c) 2(L) 750¥"], FIREARM)
    assert len(rows) == 1
    name, system = rows[0]
    assert name == "Zapgun Mk1"
    assert system["dmg"] == 3 and system["stun"] is False and system["dmgDef"] == "3P"
    assert system["modes"] == {"SS": False, "SA": True, "BF": True, "FA": False}
    assert system["attackRating"] == [10, 10, 8, 0, 0]
    assert system["ammocap"] == 15
    assert system["avail"] == 2 and system["availDef"] == "2(L)"
    assert system["price"] == 750
    assert system["type"] == "WEAPON_FIREARMS" and system["skill"] == "firearms"


def test_wrapped_row_reassembled():
    lines = ["Very Long Fictional Gun Name", "4P SS 8/6/—/—/— 6(c) 3 1,200¥"]
    rows = parse_block(lines, FIREARM)
    assert rows[0][0] == "Very Long Fictional Gun Name"
    assert rows[0][1]["price"] == 1200


def test_stray_page_number_stripped():
    lines = ["Fictional Pistol 253 2P SS 9/8/—/—/— 10(c) 2 300¥"]
    rows = parse_block(lines, FIREARM, page_numbers={253})
    assert rows[0][0] == "Fictional Pistol"


def test_melee_with_asterisk_and_stun():
    rows = parse_block(["Practice Club 2S 8/2*/—/—/— 1 20¥"], MELEE)
    name, system = rows[0]
    assert system["stun"] is True and system["dmg"] == 2
    assert system["attackRating"] == [8, 2, 0, 0, 0]


def test_cyberware_essence():
    rows = parse_block(["Fake Eye Mk2 0.2 4 6 2,500¥"], CYBER)
    _, system = rows[0]
    assert system["essence"] == 0.2 and system["capacity"] == 4
    assert system["avail"] == 6 and system["price"] == 2500


def test_prose_lines_ignored():
    lines = [
        "This paragraph explains why the gun is popular on the streets.",
        "Zapgun Mk1 3P SA 10/10/8/—/— 15(c) 2 750¥",
    ]
    rows = parse_block(lines, FIREARM)
    assert len(rows) == 1
    assert rows[0][0] == "Zapgun Mk1"


def test_wrapped_row_after_prose():
    lines = [
        "Some marketing prose about the fictional gun line.",
        "Very Long Fictional Gun Name",
        "4P SS 8/6/—/—/— 6(c) 3 1,200¥",
    ]
    rows = parse_block(lines, FIREARM)
    assert len(rows) == 1
    assert rows[0][0] == "Very Long Fictional Gun Name"


def test_dv_with_element_suffix():
    rows = parse_block(["Shock Rod 4S(e) 6/—/—/—/— 3 400¥"], MELEE)
    assert rows[0][1]["dmgDef"] == "4S(e)" and rows[0][1]["stun"] is True


def test_wrapped_name_fragment_on_data_line():
    lines = ["Fictional Predator", "V 4P SS 8/7/6/—/— 15(c) 4 350¥"]
    rows = parse_block(lines, FIREARM)
    assert len(rows) == 1
    assert rows[0][0] == "Fictional Predator V"


def test_long_prose_run_evicted_then_row_parses():
    lines = [
        "First prose sentence describing the fictional catalog.",
        "Second prose sentence with more flavor text.",
        "Third prose sentence that keeps going.",
        "Fourth prose sentence beyond the wrap window.",
        "Zapgun Mk1 3P SA 10/10/8/—/— 15(c) 2 750¥",
    ]
    rows = parse_block(lines, FIREARM)
    assert len(rows) == 1
    assert rows[0][0] == "Zapgun Mk1"


def test_unmatched_data_fragments_rejected_in_names():
    lines = [
        "Injection bolt — — 4 50¥",
        "Throwing knives",
        "2P 10/9/3/—/— 2 155¥",
    ]
    rows = parse_block(lines, MELEE)
    assert len(rows) == 1
    assert rows[0][0] == "Throwing knives"


def test_leading_prose_trimmed_from_name():
    spec = RowSpec(columns=["avail", "cost"], defaults={"type": "CHEMICALS"}, allow_tail=True)
    lines = ["cutting through trees, doors, and other immovable Glue solvent 1 90¥"]
    rows = parse_block(lines, spec)
    assert len(rows) == 1
    assert rows[0][0] == "Glue solvent"


def test_capacity_span_means_rated(gear_file=None):
    spec = RowSpec(columns=["capacity", "avail", "cost"], defaults={"type": "ELECTRONICS"})
    rows = parse_block(["Fictional Camera 1—6 1 Capacity x 100¥"], spec)
    assert rows[0][1]["needsRating"] is True


def test_capitalized_name_preferred_over_prose_prefix():
    lines = ["popular with street samurai", "Zapgun Prime VI", "4P SA 10/10/8/—/— 15(c) 2 750¥"]
    rows = parse_block(lines, FIREARM)
    assert rows[0][0] == "Zapgun Prime VI"


def test_single_line_prose_prefix_trimmed_when_plausible():
    spec = RowSpec(columns=["avail", "cost"], defaults={"type": "TOOLS"}, allow_tail=True)
    rows = parse_block(["per 10 rounds Fictional Widget 2 100¥"], spec)
    assert rows[0][0] == "Fictional Widget"
