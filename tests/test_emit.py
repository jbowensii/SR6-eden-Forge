from extractor.emit import build_item, slugify, write_category


def test_slugify():
    assert slugify("Zapgun Predator VI") == "zapgun_predator_vi"
    assert slugify("Combat/survival knife") == "combat_survival_knife"
    assert slugify("  Bull's-eye!  ") == "bull_s_eye"


def test_build_item_meta(monkeypatch):
    item = build_item("Zapgun Mk1", {"type": "WEAPON_FIREARMS"}, "corebook", 253, "0.1.0")
    assert item["id"] == "zapgun_mk1"
    assert item["meta"]["book"] == "corebook" and item["meta"]["page"] == 253
    assert item["meta"]["qaStatus"] == "extracted"
    assert item["meta"]["extractorVersion"] == "0.1.0"


def test_write_category_dedups_ids(tmp_path):
    items = [
        build_item("Same Name", {"type": "TOOLS"}, "corebook", 1, "0.1.0"),
        build_item("Same Name", {"type": "TOOLS"}, "corebook", 2, "0.1.0"),
    ]
    p = write_category(tmp_path, "corebook", "gear", "tools", items)
    import json

    data = json.loads(p.read_text(encoding="utf-8"))
    ids = [i["id"] for i in data["items"]]
    assert ids == ["same_name", "same_name_2"]
    assert data["book"] == "corebook" and data["domain"] == "gear" and data["category"] == "tools"


def test_write_category_does_not_mutate_input(tmp_path):
    items = [
        build_item("Same Name", {"type": "TOOLS"}, "corebook", 1, "0.1.0"),
        build_item("Same Name", {"type": "TOOLS"}, "corebook", 2, "0.1.0"),
    ]
    write_category(tmp_path, "corebook", "gear", "tools", items)
    assert [i["id"] for i in items] == ["same_name", "same_name"]
