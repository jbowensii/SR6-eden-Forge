from extractor.enrich import build_index, heading_keys, norm, parse_sections


def make_index():
    payloads = {
        "weapons_firearms": {
            "items": [
                {"id": "zapgun_mk1", "name": "Zapgun Mk1"},
                {"id": "zapgun_mk2", "name": "Zapgun Mk2 (cyberware)"},
                {"id": "crossbow_light", "name": "Crossbow, Light"},
            ]
        }
    }
    return build_index(payloads)


def test_heading_keys_variants():
    assert norm("Zapgun Mk1") in heading_keys("Zapgun Mk1")
    assert norm("Zapgun Mk2") in heading_keys("Zapgun Mk2 (cyberware)")
    assert norm("Light Crossbow") in heading_keys("Crossbow, Light")
    assert norm("Yamaha Pulsar") in heading_keys("Yamaha Pulsar I/II")


def test_parse_sections_basic():
    lines = [
        "some intro prose that belongs to nothing in particular",
        "Zapgun Mk1",
        "A fictional pistol beloved by fictional runners every-",
        "where. It has many fictional features and a long fake history.",
        "Wireless bonus: The fictional bonus applies twice.",
        "Zapgun Mk2",
        "The fictional successor, now with extra fictional chrome",
        "and a fictional warranty that voids itself on purpose.",
        "WEAPON DV MODES ATTACK RATINGS AMMO",
        "orphan trailing prose after a table header",
    ]
    sections = parse_sections(lines, make_index())
    d1 = sections[("weapons_firearms", "zapgun_mk1")]
    assert "beloved by fictional runners everywhere" in d1  # de-hyphenated
    assert "Wireless bonus" in d1
    d2 = sections[("weapons_firearms", "zapgun_mk2")]
    assert "fictional warranty" in d2
    assert "orphan trailing" not in d2  # stopped at the table header


def test_parse_sections_skips_stat_junk_and_short():
    lines = [
        "Zapgun Mk1",
        "Real prose line one that is long enough to matter here.",
        "Zapgun Mk1 3P SA 10/10/8 15 2 750¥",
        "251",
        "More real prose that continues the fictional writeup nicely.",
    ]
    sections = parse_sections(lines, make_index())
    text = sections[("weapons_firearms", "zapgun_mk1")]
    assert "750" not in text and "251" not in text
    assert "More real prose" in text


def test_section_title_ends_capture():
    lines = [
        "Zapgun Mk1",
        "A fictional writeup paragraph that is long enough to be kept.",
        "clubs",
        "prose belonging to the next table section, not to the zapgun",
    ]
    sections = parse_sections(lines, make_index())
    assert "next table section" not in sections[("weapons_firearms", "zapgun_mk1")]


def test_colliding_variant_keys_are_dropped():
    payloads = {
        "melee": {"items": [{"id": "combat_axe", "name": "Axe, Combat"}]},
        "tools": {"items": [{"id": "fire_axe", "name": "Axe, Fire"}]},
    }
    index = build_index(payloads)
    assert norm("Axe") not in index          # generic collision dropped
    assert norm("Combat Axe") in index       # unambiguous swap variant kept
    assert norm("Axe, Combat") in index      # full names always kept


def test_same_full_name_keeps_both_targets():
    payloads = {
        "a": {"items": [{"id": "x", "name": "Zapgun Mk1"}]},
        "b": {"items": [{"id": "y", "name": "Zapgun Mk1"}]},
    }
    index = build_index(payloads)
    assert len(index[norm("Zapgun Mk1")]) == 2


def test_writeup_spans_stream_chunks():
    # enrich concatenates all pages before parsing, so a section that starts
    # at the end of one page continues into the next without truncation
    page1 = ["Zapgun Mk1", "The start of a fictional writeup that keeps go-"]
    page2 = ["ing on the following page with more fictional detail to spare."]
    sections = parse_sections(page1 + page2, make_index())
    text = sections[("weapons_firearms", "zapgun_mk1")]
    assert "keeps going on the following page" in text


def test_junk_carveout_keeps_wireless_costs():
    lines = [
        "Zapgun Mk1",
        "A fictional writeup long enough to be kept by the parser here.",
        "Wireless bonus: recharges automatically, costing 50¥ per fictional week.",
    ]
    sections = parse_sections(lines, make_index())
    assert "Wireless bonus" in sections[("weapons_firearms", "zapgun_mk1")]
