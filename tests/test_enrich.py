from extractor.enrich import build_index, heading_keys, norm, parse_sections


def make_index():
    payloads = {
        "weapons_firearms": {
            "items": [
                {"id": "zapgun_mk1", "name": "Zapgun Mk1", "meta": {"page": 10}},
                {"id": "zapgun_mk2", "name": "Zapgun Mk2 (cyberware)", "meta": {"page": 10}},
                {"id": "crossbow_light", "name": "Crossbow, Light", "meta": {"page": 11}},
            ]
        }
    }
    return build_index(payloads)


def test_heading_keys_variants():
    assert norm("Zapgun Mk1") in heading_keys("Zapgun Mk1")
    assert norm("Zapgun Mk2") in heading_keys("Zapgun Mk2 (cyberware)")
    assert norm("Light Crossbow") in heading_keys("Crossbow, Light")
    assert norm("Yamaha Pulsar") in heading_keys("Yamaha Pulsar I/II")
    assert norm("Zapgun Mk1s") in heading_keys("Zapgun Mk1")  # plural form


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
    # interleaved table headers are skipped, not terminators — the block
    # continues to the next item heading
    assert "WEAPON DV MODES" not in d2
    assert "orphan trailing" in d2


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


def test_lowercase_fragments_do_not_kill_capture():
    # column splitting produces stray lowercase fragment lines; they are
    # prose, not section boundaries
    lines = [
        "Zapgun Mk1",
        "keep",
        "A fictional writeup that must survive the stray fragment above.",
    ]
    sections = parse_sections(lines, make_index())
    assert "survive the stray fragment" in sections[("weapons_firearms", "zapgun_mk1")]


def test_merged_header_row_matches_trailing_words():
    sections = parse_sections(
        [
            "Chapterware Zapgun Mk1",  # chapter header merged with item heading
            "A fictional writeup attributed despite the merged header row.",
        ],
        make_index(),
    )
    assert ("weapons_firearms", "zapgun_mk1") in sections


def test_writeup_spans_stream_chunks():
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


def test_group_heading_reaches_rating_family():
    payloads = {
        "cyberware": {
            "items": [
                {"id": f"zapjack_rating_{n}", "name": f"Zapjack (Rating {n})", "meta": {"page": 20}}
                for n in range(1, 4)
            ]
        }
    }
    index = build_index(payloads)
    lines = [
        (20, "Zapjacks"),
        (20, "A fictional family writeup that applies to every rating tier sold."),
    ]
    sections = parse_sections(lines, index)
    for n in range(1, 4):
        assert "fictional family writeup" in sections[("cyberware", f"zapjack_rating_{n}")]


def test_page_window_disambiguates_same_name():
    payloads = {
        "electronics": {"items": [{"id": "zap_filter", "name": "Zap Filter", "meta": {"page": 30}}]},
        "cyberware": {"items": [{"id": "zap_filter", "name": "Zap Filter", "meta": {"page": 80}}]},
    }
    index = build_index(payloads)
    lines = [
        (30, "Zap Filter"),
        (30, "The external fictional filter writeup, long enough to keep here."),
        (80, "Zap Filter"),
        (80, "The implanted fictional filter writeup, also long enough to keep."),
    ]
    sections = parse_sections(lines, index)
    assert "external" in sections[("electronics", "zap_filter")]
    assert "implanted" in sections[("cyberware", "zap_filter")]


def test_ambiguous_variant_without_page_is_skipped():
    payloads = {
        "melee": {"items": [{"id": "combat_zaxe", "name": "Zaxe, Combat", "meta": {"page": 5}}]},
        "tools": {"items": [{"id": "fire_zaxe", "name": "Zaxe, Fire", "meta": {"page": 90}}]},
    }
    index = build_index(payloads)
    # bare 'Zaxe' with no page info matches two different names -> no section
    sections = parse_sections(["Zaxe", "Some fictional prose that would otherwise be captured here."], index)
    assert sections == {}


def test_subtype_group_heading():
    payloads = {
        "electronics": {
            "items": [
                {"id": "zapa_link", "name": "Zapa Link", "meta": {"page": 40}, "system": {"subtype": "ZAPLINK"}},
                {"id": "zapb_elite", "name": "Zapb Elite", "meta": {"page": 40}, "system": {"subtype": "ZAPLINK"}},
            ]
        }
    }
    index = build_index(payloads)
    sections = parse_sections(
        [(40, "Zaplinks"), (40, "A fictional group writeup shared by every model in the family here.")],
        index,
    )
    assert "fictional group writeup" in sections[("electronics", "zapa_link")]
    assert "fictional group writeup" in sections[("electronics", "zapb_elite")]


def test_numbered_family_heading():
    payloads = {
        "cyberware": {
            "items": [
                {"id": f"zap_reflexes_{n}", "name": f"Zap Reflexes {n}", "meta": {"page": 50}}
                for n in (1, 2)
            ]
        }
    }
    index = build_index(payloads)
    sections = parse_sections(
        [(50, "Zap Reflexes"), (50, "A fictional writeup covering every grade of the fictional implant.")],
        index,
    )
    assert ("cyberware", "zap_reflexes_1") in sections
    assert ("cyberware", "zap_reflexes_2") in sections


def test_longest_writeup_wins_over_caption_fragment():
    lines = [
        "Zapgun Mk1",  # art caption opens a short premature section
        "A short caption-adjacent fragment of fictional text here.",
        "Zapgun Mk2",
        "filler writeup for the other fictional gun, long enough to keep.",
        "Zapgun Mk1",  # the real writeup, longer
        "The real fictional writeup which is much longer and should win the",
        "assignment because it contains the full description of the zapgun",
        "including all of its fictional features and quirks in detail.",
    ]
    sections = parse_sections(lines, make_index())
    assert "real fictional writeup" in sections[("weapons_firearms", "zapgun_mk1")]


def test_prose_prices_survive_junk_filter():
    lines = [
        "Zapgun Mk1",
        "This fictional gun sells on fictional streets for around 750¥ despite the ban.",
    ]
    sections = parse_sections(lines, make_index())
    assert "750¥ despite the ban" in sections[("weapons_firearms", "zapgun_mk1")]
