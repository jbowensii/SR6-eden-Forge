from extractor.enrich import norm
from extractor.spell_layout import CRITTER_POWER_HEADER, parse_list_descriptions
from extractor.writeups import LineRec


def _mk(rows):  # (page, col, is_head, text)
    return [LineRec(*r) for r in rows]


def test_grouped_spells_share_following_description():
    lines = _mk([
        (134, 0, False, "Clout"),
        (134, 0, False, "(Indirect Combat)"),
        (134, 0, False, "RANGE TYPE DURATION DV DAMAGE"),
        (134, 0, False, "LOS S"),
        (134, 0, False, "Blast"),
        (134, 0, False, "(Indirect Combat, Area)"),
        (134, 0, False, "RANGE TYPE DURATION DV DAMAGE"),
        (134, 0, False, "LOS (A) S"),
        (134, 0, False, "A tricky little spell shapes the air to strike."),
        (134, 0, False, "Clout targets individuals, Blast is area effect."),
        (134, 0, False, "Flamestrike"),
        (134, 0, False, "(Indirect Combat)"),
        (134, 0, False, "RANGE TYPE DURATION DV DAMAGE"),
        (134, 0, False, "LOS P, Special"),
        (134, 0, False, "A classic fire spell that explodes in faces."),
    ])
    known = {norm(n) for n in ["Clout", "Blast", "Flamestrike"]}
    out = parse_list_descriptions(lines, known)
    assert out[norm("Clout")] == "A tricky little spell shapes the air to strike. Clout targets individuals, Blast is area effect."
    assert out[norm("Blast")] == out[norm("Clout")]        # shared
    assert out[norm("Flamestrike")] == "A classic fire spell that explodes in faces."


def test_name_resolved_past_column_bleed_stray():
    # a stray bleed word ("the") sits between the name and the (category) line
    lines = _mk([
        (134, 0, False, "Ice Spear"),
        (134, 0, False, "the"),
        (134, 0, False, "(Indirect Combat)"),
        (134, 0, False, "RANGE TYPE DURATION DV DAMAGE"),
        (134, 0, False, "LOS P, Special"),
        (134, 0, False, "A shard of ice hurled at the target for damage."),
    ])
    known = {norm("Ice Spear")}
    out = parse_list_descriptions(lines, known)
    assert out[norm("Ice Spear")] == "A shard of ice hurled at the target for damage."


def test_prose_cuts_header_merged_mid_line_by_bleed():
    # column bleed merges a prose tail with the next entry's header on one row
    lines = _mk([
        (141, 0, False, "Light"),
        (141, 0, False, "(Manipulation)"),
        (141, 0, False, "RANGE TYPE DURATION DV"),
        (141, 0, False, "LOS(A) S"),
        (141, 0, False, "Creates light or darkness in an area. Darkness"),
        (141, 0, False, "reduces vision as needed by the caster. RANGE TYPE DURATION DV LOS(A)"),
    ])
    known = {norm("Light")}
    out = parse_list_descriptions(lines, known)
    assert out[norm("Light")] == "Creates light or darkness in an area. Darkness reduces vision as needed by the caster."
    assert "RANGE TYPE" not in out[norm("Light")]


def test_critter_power_header_variant():
    # same list structure, different stat header column order
    lines = _mk([
        (222, 1, True, "Accident"),
        (222, 1, False, "TYPE ACTION RANGE DURATION"),
        (222, 1, False, "P Major LOS Instant"),
        (222, 1, False, "Critters with this power can cause seemingly normal accidents."),
        (222, 1, True, "Animal Control"),
        (222, 1, False, "TYPE ACTION RANGE DURATION"),
        (222, 1, False, "M Complex LOS Sustained"),
        (222, 1, False, "The critter can control the actions of a mundane animal."),
    ])
    known = {norm("Accident"), norm("Animal Control")}
    out = parse_list_descriptions(lines, known, CRITTER_POWER_HEADER)
    assert out[norm("Accident")] == "Critters with this power can cause seemingly normal accidents."
    assert out[norm("Animal Control")] == "The critter can control the actions of a mundane animal."


def test_prose_stops_at_column_boundary():
    lines = _mk([
        (134, 0, False, "Heal"),
        (134, 0, False, "(Health)"),
        (134, 0, False, "RANGE TYPE DURATION DV DAMAGE"),
        (134, 0, False, "Touch P"),
        (134, 0, False, "Restores health to a living target over time."),
        (134, 1, False, "Unrelated second-column text that must not leak in."),
    ])
    known = {norm("Heal")}
    out = parse_list_descriptions(lines, known)
    assert out[norm("Heal")] == "Restores health to a living target over time."
