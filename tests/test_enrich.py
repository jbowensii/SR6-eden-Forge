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
