from pathlib import Path

from validator.model import DataFile
from validator.schema_check import check_file


def df(payload):
    return DataFile(path=Path("data/corebook/gear/weapons_firearms.json"), payload=payload)


def test_valid_file_passes(gear_file):
    assert check_file(df(gear_file)) == []


def test_bad_gear_type_fails(gear_file):
    gear_file["items"][0]["system"]["type"] = "WEAPON_LASER"
    issues = check_file(df(gear_file))
    assert len(issues) == 1
    assert issues[0].rule == "schema"
    assert issues[0].item_id == "example_autopistol"


def test_unknown_item_field_fails(gear_file):
    # system now accepts lossless Commlink6 extras, but the item shell stays strict
    gear_file["items"][0]["bogus"] = 3
    assert any(i.rule == "schema" for i in check_file(df(gear_file)))


def test_unknown_system_field_allowed(gear_file):
    # lossless: unknown system fields (Commlink6 passthrough) no longer fail schema
    gear_file["items"][0]["system"]["dmgg"] = 3
    assert not any(i.rule == "schema" for i in check_file(df(gear_file)))


def test_attack_rating_wrong_length_fails(gear_file):
    gear_file["items"][0]["system"]["attackRating"] = [10, 10, 8]
    assert any(i.rule == "schema" for i in check_file(df(gear_file)))


def test_missing_meta_field_fails(gear_file):
    del gear_file["items"][0]["meta"]["qaStatus"]
    assert any(i.rule == "schema" for i in check_file(df(gear_file)))


def test_unknown_domain_reports_no_schema(gear_file):
    gear_file["domain"] = "nonexistent_domain"
    issues = check_file(df(gear_file))
    assert len(issues) == 1
    assert issues[0].rule == "no-schema"


def test_item_img_field_allowed(gear_file):
    gear_file["items"][0]["img"] = "corebook/example_autopistol.webp"
    assert check_file(df(gear_file)) == []
