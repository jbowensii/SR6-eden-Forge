import copy
from pathlib import Path

from validator.model import DataFile
from validator.sanity import check_gear


def df(payload, path="data/corebook/gear/weapons_firearms.json"):
    return DataFile(path=Path(path), payload=payload)


def rules(issues):
    return sorted({i.rule for i in issues})


def test_clean_file_no_issues(gear_file):
    assert check_gear([df(gear_file)]) == []


def test_duplicate_id_across_files(gear_file):
    other = copy.deepcopy(gear_file)
    other["category"] = "armor"
    issues = check_gear(
        [df(gear_file), df(other, "data/corebook/gear/armor.json")]
    )
    assert rules(issues) == ["duplicate-id"]


def test_same_id_different_books_ok(gear_file):
    other = copy.deepcopy(gear_file)
    other["book"] = "firing_squad"
    other["items"][0]["meta"]["book"] = "firing_squad"
    issues = check_gear(
        [df(gear_file), df(other, "data/firing_squad/gear/weapons_firearms.json")]
    )
    assert issues == []


def test_bad_damage_code(gear_file):
    gear_file["items"][0]["system"]["dmgDef"] = "3X"
    assert rules(check_gear([df(gear_file)])) == ["damage-format"]


def test_special_damage_ok(gear_file):
    gear_file["items"][0]["system"]["dmgDef"] = "Special"
    assert check_gear([df(gear_file)]) == []


def test_weapon_missing_skill(gear_file):
    gear_file["items"][0]["system"]["skill"] = ""
    assert rules(check_gear([df(gear_file)])) == ["weapon-fields"]


def test_nonweapon_needs_no_skill(gear_file):
    item = gear_file["items"][0]
    item["system"] = {"type": "ELECTRONICS", "avail": 2, "price": 100}
    assert check_gear([df(gear_file)]) == []


def test_implausible_price_and_avail(gear_file):
    gear_file["items"][0]["system"]["price"] = 99_000_000
    gear_file["items"][0]["system"]["avail"] = 99
    assert rules(check_gear([df(gear_file)])) == ["plausibility"]


def test_path_mismatch(gear_file):
    issues = check_gear([df(gear_file, "data/corebook/gear/armor.json")])
    assert rules(issues) == ["path-mismatch"]


def test_path_not_in_convention_is_ignored(gear_file):
    assert check_gear([df(gear_file, "somefile.json")]) == []
