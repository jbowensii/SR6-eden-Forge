from extractor.segment import block_after_header

PAGE = """intro prose about fictional guns
zap pistols
WEAPON DV MODES ATTACK RATINGS AMMO AVAILABILITY COST
Zapgun Mk1 3P SA 10/10/8/—/— 15(c) 2 750¥
Zapgun Mk2 4P SA/BF 11/11/9/—/— 20(c) 3 1,100¥
zap rifles
WEAPON DV MODES ATTACK RATINGS AMMO AVAILABILITY COST
Zapri fle Alpha 5P SA/BF/FA 4/11/9/7/1 38(c) 2 2,000¥
closing prose paragraph
"""


def test_block_between_header_and_next_header():
    lines = block_after_header(PAGE, r"^zap pistols$", [])
    assert lines[0].startswith("Zapgun Mk1")
    assert lines[1].startswith("Zapgun Mk2")
    assert len([l for l in lines if "Zapri" in l]) == 0


def test_block_with_stop_regex():
    lines = block_after_header(PAGE, r"^zap rifles$", [r"^closing prose"])
    assert any("Zapri" in l for l in lines)
    assert not any("closing prose" in l for l in lines)


def test_missing_header_returns_empty():
    assert block_after_header(PAGE, r"^no such section$", []) == []


def test_column_header_line_is_skipped():
    lines = block_after_header(PAGE, r"^zap pistols$", [])
    assert not any(l.startswith("WEAPON DV") for l in lines)
