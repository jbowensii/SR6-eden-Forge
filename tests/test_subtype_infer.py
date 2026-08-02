from extractor.subtype_infer import infer_subtype


def test_firearm_specific_before_general():
    assert infer_subtype("WEAPON_FIREARMS", "Ares Light Pistol") == "PISTOLS_LIGHT"
    assert infer_subtype("WEAPON_FIREARMS", "Ingram Machine Pistol") == "MACHINE_PISTOLS"
    assert infer_subtype("WEAPON_FIREARMS", "Ares Alpha", "A modern assault rifle.") == "RIFLE_ASSAULT"
    assert infer_subtype("WEAPON_FIREARMS", "Ares Antioch", "A grenade launcher.") == "LAUNCHERS"


def test_close_combat_from_text():
    assert infer_subtype("WEAPON_CLOSE_COMBAT", "Combat Knife") == "BLADES"
    assert infer_subtype("WEAPON_CLOSE_COMBAT", "Stun Baton", "A telescoping club.") == "CLUBS"


def test_electronics_from_notes():
    assert infer_subtype("ELECTRONICS", "Meta Link", "A budget commlink.") == "COMMLINK"
    assert infer_subtype("ELECTRONICS", "Fairlight Excalibur", "top-end cyberdeck") == "CYBERDECK"


def test_ambiguous_returns_none():
    # bare "pistol" with no light/heavy qualifier must not be guessed
    assert infer_subtype("WEAPON_FIREARMS", "Some Gun", "a weapon") is None
    assert infer_subtype("ELECTRONICS", "Mystery Widget", "a device") is None
    assert infer_subtype("ARMOR", "Anything") is None   # unknown type
