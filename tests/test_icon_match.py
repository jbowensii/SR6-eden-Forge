from pathlib import Path

from extractor.icon_match import best_match, index_library, tokens


def make_lib(tmp_path):
    for rel in [
        "cyberpunk/pistols/heavy_pistol_black.png",
        "cyberpunk/rifles/assault_rifle_worn.webp",
        "fantasy/axes/battle_axe_iron.png",
        "fantasy/book/spell_tome_red.png",
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake")
    return index_library(tmp_path)


def test_tokens_drop_noise():
    assert tokens("Heavy_Pistol-icons FINAL 03.png") == {"heavy", "pistol", "03"} - {"03"}


def test_best_match_prefers_name_and_context(tmp_path):
    lib = make_lib(tmp_path)
    item = {"name": "Zap Heavy Pistol", "system": {"type": "WEAPON_FIREARMS", "subtype": "PISTOLS_HEAVY"}}
    path, score = best_match(item, lib)
    assert path is not None and path.name == "heavy_pistol_black.png"


def test_best_match_requires_name_token(tmp_path):
    lib = make_lib(tmp_path)
    item = {"name": "Chemsuit", "system": {"type": "SURVIVAL", "subtype": "SURVIVAL_GEAR"}}
    path, score = best_match(item, lib)
    assert path is None


def test_axe_matches_axe(tmp_path):
    lib = make_lib(tmp_path)
    item = {"name": "Battle Axe", "system": {"type": "WEAPON_CLOSE_COMBAT", "subtype": "BLADES"}}
    path, _ = best_match(item, lib)
    assert path.name == "battle_axe_iron.png"
