from extractor.ingest import fill_blank_fields


def test_fill_adds_missing_string_fields_per_type():
    items = [
        {"system": {"type": "ARMOR", "availDef": "4", "defense": 8}},
        {"system": {"type": "ARMOR", "priceDef": "1000"}},  # missing availDef
    ]
    added = fill_blank_fields(items)
    # the second armor gains the availDef its peer uses, blank
    assert items[1]["system"]["availDef"] == ""
    # the first gains priceDef blank; numeric 'defense' is never blank-added
    assert items[0]["system"]["priceDef"] == ""
    assert "defense" not in items[1]["system"]
    assert added >= 2


def test_fill_respects_base_fields():
    items = [{"system": {"type": "TOOLS", "price": 50}}]
    fill_blank_fields(items, base_fields=("notes", "description"))
    assert items[0]["system"]["notes"] == "" and items[0]["system"]["description"] == ""


def test_type_field_never_blanked():
    items = [{"system": {"type": "ARMOR"}}, {"system": {"category": "COMBAT"}}]
    fill_blank_fields(items)
    assert items[0]["system"]["type"] == "ARMOR"
