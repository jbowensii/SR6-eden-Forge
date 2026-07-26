from extractor.xtable import assign_row, extract_page, group_lines, header_cells


def W(text, x0, top, w=1.0):
    return {"text": text, "x0": x0, "x1": x0 + w * len(text), "top": top}


def row(words_at):
    """words_at: list of (text, x0). All on one row."""
    return [W(t, x, 100) for t, x in words_at]


def test_group_lines_clusters_by_top():
    words = [W("a", 0, 10), W("b", 20, 10.5), W("c", 5, 40)]
    lines = group_lines(words)
    assert len(lines) == 2
    assert [w["text"] for w in lines[0]] == ["a", "b"]


def test_header_cells_maps_columns():
    # WEAPON  DV  MODES  ATTACK RATINGS  AMMO  AVAILABILITY  COST
    hdr = [W("WEAPON", 10, 5), W("DV", 100, 5), W("MODES", 130, 5),
           W("ATTACK", 170, 5), W("RATINGS", 210, 5), W("AMMO", 280, 5),
           W("AVAILABILITY", 320, 5), W("COST", 400, 5)]
    cells = header_cells(hdr)
    keys = [k for _, k in cells]
    assert keys == [None, "dv", "modes", "ar", "ammo", "avail", "cost"]


def test_header_type_column_distinct_band():
    hdr = [W("WEAPON", 10, 5), W("TYPE", 90, 5), W("DV", 140, 5),
           W("ATTACK", 180, 5), W("RATINGS", 210, 5), W("AVAIL", 280, 5), W("COST", 340, 5)]
    cells = header_cells(hdr)
    keys = [k for _, k in cells]
    # WEAPON=name(None), TYPE=note(None at its own x), DV, ar, avail, cost
    assert keys == [None, None, "dv", "ar", "avail", "cost"]


def test_assign_row_separates_name_type_stats():
    hdr = [W("WEAPON", 10, 5), W("TYPE", 90, 5), W("DV", 140, 5),
           W("ATTACK", 180, 5), W("RATINGS", 210, 5), W("AVAIL", 280, 5), W("COST", 340, 5)]
    cells = header_cells(hdr)
    data = [W("Bearded", 10, 100), W("Axe", 45, 100), W("Blades", 90, 100),
            W("3P", 140, 100), W("11/—/—/—/—", 180, 100), W("3", 280, 100), W("600¥", 340, 100)]
    a = assign_row(data, cells)
    assert a["_name"] == "Bearded Axe"
    assert a["_note"] == "Blades"
    assert a["dv"] == "3P"
    assert a["cost"] == "600¥"


def test_extract_page_firearms_positional():
    hdr = [W("WEAPON", 10, 20), W("DV", 100, 20), W("MODES", 130, 20),
           W("ATTACK", 170, 20), W("RATINGS", 205, 20), W("AMMO", 260, 20),
           W("AVAILABILITY", 300, 20), W("COST", 380, 20)]
    r1 = [W("Zapgun", 10, 40), W("Alpha", 45, 40), W("3P", 100, 40), W("SA", 130, 40),
          W("10/10/8/—/—", 170, 40), W("15(c)", 260, 40), W("2", 300, 40), W("750¥", 380, 40)]
    items = extract_page(hdr + r1, 55)
    assert len(items) == 1
    it = items[0]
    assert it["name"] == "Zapgun Alpha"
    assert it["_category"] == "weapons_firearms"
    assert it["system"]["dmgDef"] == "3P"
    assert it["system"]["price"] == 750
    assert it["system"]["ammocap"] == 15
    assert it["page"] == 55


def test_extract_page_weapon_rack_type_column():
    hdr = [W("WEAPON", 10, 20), W("TYPE", 90, 20), W("DV", 140, 20),
           W("ATTACK", 180, 20), W("RATINGS", 215, 20), W("AVAIL", 280, 20), W("COST", 340, 20)]
    r1 = [W("Bearded", 10, 40), W("Axe", 45, 40), W("Blades", 90, 40),
          W("3P", 140, 40), W("11/—/—/—/—", 180, 40), W("3", 280, 40), W("600¥", 340, 40)]
    items = extract_page(hdr + r1, 17)
    assert items[0]["name"] == "Bearded Axe"
    assert items[0]["system"]["dmgDef"] == "3P"
    assert "Blades" in items[0]["system"].get("notes", "")


def test_cyberware_positional():
    hdr = [W("CYBERWARE", 10, 20), W("ESSENCE", 120, 20), W("CAP", 200, 20),
           W("AVAIL", 250, 20), W("COST", 320, 20)]
    r1 = [W("Fake", 10, 40), W("Eye", 40, 40), W("0.2", 120, 40), W("4", 200, 40),
          W("6", 250, 40), W("2,500¥", 320, 40)]
    items = extract_page(hdr + r1, 51)
    assert items[0]["_category"] == "cyberware"
    assert items[0]["system"]["essence"] == 0.2
    assert items[0]["system"]["price"] == 2500
