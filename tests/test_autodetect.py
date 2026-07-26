from extractor.autodetect import classify, detect_page_cols, parse_header


def test_parse_header_corebook_firearms():
    cols, _ = parse_header("WEAPON DV MODES ATTACK RATINGS AMMO AVAILABILITY COST")
    assert cols == ["dv", "modes", "ar", "ammo", "avail", "cost"]


def test_parse_header_firing_squad_abbreviated():
    cols, _ = parse_header("TYPE DV MODE ATTACK RATINGS AMMO AVAIL COST")
    assert cols == ["dv", "modes", "ar", "ammo", "avail", "cost"]


def test_parse_header_melee_no_modes():
    cols, _ = parse_header("TYPE DV ATTACK RATINGS AVAIL COST")
    assert cols == ["dv", "ar", "avail", "cost"]


def test_parse_header_cyberware_abbrev():
    cols, label = parse_header("CYBERWARE ESSENCE CAP AVAIL COST")
    assert cols == ["essence", "capacity", "avail", "cost"]
    assert "cyberware" in label


def test_parse_header_armor():
    cols, _ = parse_header("TYPE DEFENSE RATING CAPACITY AVAIL COST")
    # DEFENSE then (RATING->ratingspan) then capacity/avail/cost
    assert cols[0] == "defense" and cols[-1] == "cost" and "capacity" in cols


def test_parse_header_rejects_prose():
    assert parse_header("This is just a sentence about guns and their cost") is None
    assert parse_header("weapon accessories") is None


def test_classify_domains():
    assert classify(["dv", "modes", "ar", "ammo", "avail", "cost"], [])[1] == "weapons_firearms"
    assert classify(["dv", "ar", "avail", "cost"], [])[1] == "weapons_close_combat"
    assert classify(["essence", "capacity", "avail", "cost"], [])[1] == "cyberware"
    assert classify(["essence", "avail", "cost"], [])[1] == "bioware"
    assert classify(["defense", "capacity", "avail", "cost"], [])[1] == "armor"
    veh = ["onoff:handlOn:handlOff", "int:accOn", "int:tspd", "int:bod", "int:arm", "int:pil", "int:sen", "seat", "avail", "cost"]
    assert classify(veh, [])[1] == "vehicles"


def test_detect_page_cols_extracts_rows_with_subtype():
    # column-cache format: frac-prefixed lines, one column stream
    page = "\n".join([
        "0.100|heavy pistols",
        "0.120|WEAPON DV MODES ATTACK RATINGS AMMO AVAILABILITY COST",
        "0.140|Zapgun Alpha 3P SA 10/10/8/—/— 15(c) 2 750¥",
        "0.160|Zapgun Beta 4P SA/BF 11/11/9/—/— 20(c) 3(L) 1,100¥",
    ])
    items = detect_page_cols(page, 42)
    assert [i["name"] for i in items] == ["Zapgun Alpha", "Zapgun Beta"]
    assert all(i["_category"] == "weapons_firearms" for i in items)
    assert items[0]["system"]["subtype"] == "PISTOLS_HEAVY"
    assert items[0]["system"]["price"] == 750
    assert items[1]["system"]["price"] == 1100


def test_generic_gear_needs_gear_label():
    # AVAIL+COST alone is not enough; needs a gear-ish label
    assert classify(["avail", "cost"], ["skill"]) is None
    assert classify(["avail", "cost"], ["gear"])[1] == "electronics"


def test_stat_debris_names_rejected():
    from extractor.autodetect import _valid_name
    assert not _valid_name("8(m)")
    assert not _valid_name("0.220|+8 —10")
    assert not _valid_name("n/a")
    assert _valid_name("Ares Predator VI")


def test_type_column_captured_as_note():
    cols, _ = parse_header("WEAPON TYPE DV ATTACK RATINGS AVAIL COST")
    assert cols[0] == "note:Type" and "dv" in cols and cols[-1] == "cost"


def test_def_abbreviation():
    cols, _ = parse_header("ITEM DEF CAPACITY AVAIL COST")
    assert "defense" in cols


def test_category_words_rejected_as_names():
    from extractor.autodetect import _valid_name
    assert not _valid_name("Blade")
    assert not _valid_name("Exotic")
    assert not _valid_name("Hold-Out")
    assert _valid_name("Bearded Axe")
