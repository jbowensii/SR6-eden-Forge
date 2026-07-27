from extractor.hierarchy import section_to_subtype, subtype_compatible, subtype_for_page


def test_section_to_subtype():
    assert section_to_subtype("Blades") == "BLADES"
    assert section_to_subtype("Heavy Pistols") == "PISTOLS_HEAVY"
    assert section_to_subtype("Headware") == "CYBER_HEADWARE"
    assert section_to_subtype("Cultured Bioware") == "BIOWARE_CULTURED"
    # ambiguous parent sections are intentionally unmapped
    assert section_to_subtype("Firearms") is None
    assert section_to_subtype("Augmentations") is None


def test_subtype_compatible():
    assert subtype_compatible("PISTOLS_HEAVY", "WEAPON_FIREARMS")
    assert not subtype_compatible("PISTOLS_HEAVY", "CYBERWARE")
    assert subtype_compatible("CYBER_HEADWARE", "CYBERWARE")
    # the generic ELECTRONICS bucket accepts any subtype (mis-typed gear)
    assert subtype_compatible("PISTOLS_HEAVY", "ELECTRONICS")


def test_subtype_for_page():
    markers = [(14, 0, "CLUBS"), (18, 0, "PISTOLS_LIGHT"), (20, 0, "MACHINE_PISTOLS")]
    assert subtype_for_page(markers, 12) is None
    assert subtype_for_page(markers, 15) == "CLUBS"
    assert subtype_for_page(markers, 19) == "PISTOLS_LIGHT"
    assert subtype_for_page(markers, 25) == "MACHINE_PISTOLS"
