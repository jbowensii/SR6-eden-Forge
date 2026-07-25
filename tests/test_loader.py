import json

from validator.loader import discover


def write(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj), encoding="utf-8")


def test_discovers_nested_json(tmp_path, gear_file):
    write(tmp_path / "corebook" / "gear" / "weapons_firearms.json", gear_file)
    write(tmp_path / "corebook" / "gear" / "armor.json", {**gear_file, "category": "armor"})
    files, issues = discover(tmp_path)
    assert issues == []
    assert [f.category for f in files] == ["armor", "weapons_firearms"]
    assert all(f.domain == "gear" for f in files)


def test_bad_json_reports_parse_issue(tmp_path):
    p = tmp_path / "corebook" / "gear" / "broken.json"
    p.parent.mkdir(parents=True)
    p.write_text("{not json", encoding="utf-8")
    files, issues = discover(tmp_path)
    assert files == []
    assert len(issues) == 1
    assert issues[0].rule == "parse"


def test_non_object_root_reports_parse_issue(tmp_path):
    write(tmp_path / "corebook" / "gear" / "list.json", [1, 2, 3])
    files, issues = discover(tmp_path)
    assert files == []
    assert issues[0].rule == "parse"


def test_empty_root_ok(tmp_path):
    files, issues = discover(tmp_path)
    assert files == [] and issues == []


def test_non_utf8_file_reports_parse_issue(tmp_path):
    p = tmp_path / "corebook" / "gear" / "bad_encoding.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(b'{"x": "\xe9"}')
    files, issues = discover(tmp_path)
    assert files == []
    assert len(issues) == 1
    assert issues[0].rule == "parse"
