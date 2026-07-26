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


def test_pick_generic_prefers_terms(tmp_path):
    from extractor.icon_match import pick_generic

    extra = tmp_path / "fantasy" / "swords" / "steel_sword_plain.png"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"fake")
    from extractor.icon_match import index_library as idx

    lib = idx(tmp_path)
    pick = pick_generic("BLADES", lib)  # terms: sword/knife/blade
    assert pick is not None and pick.name == "steel_sword_plain.png"


def test_pick_generic_none_when_no_terms_hit(tmp_path):
    from extractor.icon_match import pick_generic

    lib = make_lib(tmp_path)  # no sword/knife/blade or crate/box/bag/gear tokens
    assert pick_generic("BLADES", lib) is None


def test_match_icons_honors_remembered_default(tmp_path):
    import json

    from extractor.icon_match import match_icons

    lib = tmp_path / "lib"
    (lib / "cyberpunk").mkdir(parents=True)
    (lib / "cyberpunk" / "nothing_relevant.png").write_bytes(b"x")
    data = tmp_path / "data"
    (data / "testbook" / "gear").mkdir(parents=True)
    (data / "_assets" / "generic").mkdir(parents=True)
    (data / "_assets" / "generic" / "weapon_firearms_zapguns.png").write_bytes(b"icon")
    (data / "_assets" / "generic" / "defaults.json").write_text(
        json.dumps({"WEAPON_FIREARMS/ZAPGUNS": "generic/weapon_firearms_zapguns.png"}), encoding="utf-8"
    )
    (data / "testbook" / "gear" / "weapons.json").write_text(
        json.dumps({
            "book": "testbook", "domain": "gear", "category": "weapons",
            "items": [{
                "id": "zapgun_x", "name": "Unmatchable Zapgun X",
                "system": {"type": "WEAPON_FIREARMS", "subtype": "ZAPGUNS"},
                "meta": {"book": "testbook", "page": 1, "extractedAt": "2026-07-26", "extractorVersion": "0.1.0", "qaStatus": "extracted"},
            }],
        }), encoding="utf-8")
    stats = match_icons(lib, data, "testbook", "gear")
    payload = json.loads((data / "testbook" / "gear" / "weapons.json").read_text(encoding="utf-8"))
    assert payload["items"][0]["img"] == "generic/weapon_firearms_zapguns.png"
    assert stats["generic"] == 1
