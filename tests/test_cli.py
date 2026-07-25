import json

from validator.cli import main


def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_clean_tree_exits_zero(tmp_path, gear_file, capsys):
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    assert main([str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "OK: 1 file(s), 1 item(s) validated" in out


def test_schema_violation_exits_one(tmp_path, gear_file, capsys):
    gear_file["items"][0]["system"]["type"] = "WEAPON_LASER"
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    assert main([str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "schema" in out and "FAILED" in out


def test_sanity_violation_exits_one(tmp_path, gear_file, capsys):
    gear_file["items"][0]["system"]["dmgDef"] = "3X"
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    assert main([str(tmp_path)]) == 1
    assert "damage-format" in capsys.readouterr().out


def test_missing_path_exits_two(tmp_path, capsys):
    assert main([str(tmp_path / "nope")]) == 2


def test_schema_invalid_file_skips_sanity(tmp_path, gear_file, capsys):
    gear_file["items"][0]["system"]["dmgg"] = 1
    gear_file["items"][0]["system"]["dmgDef"] = "3X"
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    main([str(tmp_path)])
    out = capsys.readouterr().out
    assert "schema" in out and "damage-format" not in out
