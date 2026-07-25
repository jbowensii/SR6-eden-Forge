import json
from types import SimpleNamespace

from validator.cli import main as validate

from extractor.run import parse_book

FAKE_PAGE = """fictional pistols
WEAPON DV MODES ATTACK RATINGS AMMO AVAILABILITY COST
Zapgun Mk1 3P SA 10/10/8/—/— 15(c) 2 750¥
Zapgun Mk2 4P SA/BF 11/11/9/—/— 20(c) 3(L) 1,100¥
"""


def _firearm_spec():
    from extractor.profiles import TableSpec
    from extractor.rowengine import RowSpec

    return TableSpec(
        category="weapons_firearms",
        pages=[10],
        header_regex=r"^fictional pistols$",
        stop_regexes=[],
        row_spec=RowSpec(
            columns=["dv", "modes", "ar", "ammo", "avail", "cost"],
            defaults={"type": "WEAPON_FIREARMS", "subtype": "PISTOLS_LIGHT", "skill": "firearms"},
        ),
    )


def _patch_profile(monkeypatch, module):
    import extractor.profiles as profiles
    import extractor.run as run

    monkeypatch.setattr(profiles, "get_profile", lambda book, domain: module)
    monkeypatch.setattr(run, "get_profile", profiles.get_profile)


def _write_fake_page(tmp_path):
    raw = tmp_path / "_raw" / "testbook" / "pages" / "p10.txt"
    raw.parent.mkdir(parents=True)
    raw.write_text(FAKE_PAGE, encoding="utf-8")


def test_golden_roundtrip(tmp_path, monkeypatch):
    _write_fake_page(tmp_path)
    _patch_profile(monkeypatch, SimpleNamespace(TABLES=[_firearm_spec()]))

    rc = parse_book("testbook", "gear", tmp_path, [])
    assert rc == 0
    out = json.loads((tmp_path / "testbook" / "gear" / "weapons_firearms.json").read_text(encoding="utf-8"))
    assert [i["name"] for i in out["items"]] == ["Zapgun Mk1", "Zapgun Mk2"]
    assert out["items"][1]["system"]["price"] == 1100
    assert validate([str(tmp_path / "testbook")]) == 0


def test_empty_category_fails_loud(tmp_path, monkeypatch, capsys):
    _write_fake_page(tmp_path)

    from extractor.profiles import TableSpec
    from extractor.rowengine import RowSpec

    spec = TableSpec(
        category="weapons_melee",
        pages=[10],
        header_regex=r"^no such header$",
        stop_regexes=[],
        row_spec=RowSpec(columns=["dv", "ar", "avail", "cost"], defaults={"type": "WEAPON_CLOSE_COMBAT"}),
    )
    _patch_profile(monkeypatch, SimpleNamespace(TABLES=[spec]))

    rc = parse_book("testbook", "gear", tmp_path, [])
    assert rc == 1
    out = capsys.readouterr().out
    assert "EMPTY: weapons_melee" in out
    assert (tmp_path / "testbook" / "gear" / "weapons_melee.json").is_file()


def test_profile_hooks_exclude_rename_manual(tmp_path, monkeypatch):
    _write_fake_page(tmp_path)
    module = SimpleNamespace(
        TABLES=[_firearm_spec()],
        EXCLUDE={("weapons_firearms", "zapgun_mk2")},
        RENAMES={("weapons_firearms", "zapgun_mk1"): "Zapgun Mk1 Deluxe"},
        MANUAL_ITEMS=[
            {
                "category": "weapons_firearms",
                "name": "Formula Bow",
                "system": {
                    "type": "WEAPON_RANGED",
                    "skill": "athletics",
                    "dmgDef": "(Rating/2)P",
                    "needsRating": True,
                    "price": 0,
                    "priceDef": "100 + (Rating x 10)¥",
                },
                "page": 10,
            }
        ],
    )
    _patch_profile(monkeypatch, module)

    rc = parse_book("testbook", "gear", tmp_path, [])
    assert rc == 0
    out = json.loads((tmp_path / "testbook" / "gear" / "weapons_firearms.json").read_text(encoding="utf-8"))
    names = [i["name"] for i in out["items"]]
    assert names == ["Zapgun Mk1 Deluxe", "Formula Bow"]
    assert validate([str(tmp_path / "testbook")]) == 0


def test_manual_only_category_created(tmp_path, monkeypatch):
    _write_fake_page(tmp_path)
    module = SimpleNamespace(
        TABLES=[],
        MANUAL_ITEMS=[
            {
                "category": "ammo",
                "name": "Fictional Slug",
                "system": {"type": "AMMUNITION", "avail": 2, "price": 10},
                "page": 10,
            }
        ],
    )
    _patch_profile(monkeypatch, module)

    rc = parse_book("testbook", "gear", tmp_path, [])
    assert rc == 0
    out = json.loads((tmp_path / "testbook" / "gear" / "ammo.json").read_text(encoding="utf-8"))
    assert out["items"][0]["name"] == "Fictional Slug"


def test_overrides_hook(tmp_path, monkeypatch):
    _write_fake_page(tmp_path)
    module = SimpleNamespace(
        TABLES=[_firearm_spec()],
        OVERRIDES={("weapons_firearms", "zapgun_mk2"): {"subtype": "PISTOLS_HEAVY"}},
    )
    _patch_profile(monkeypatch, module)
    assert parse_book("testbook", "gear", tmp_path, []) == 0
    out = json.loads((tmp_path / "testbook" / "gear" / "weapons_firearms.json").read_text(encoding="utf-8"))
    assert out["items"][1]["system"]["subtype"] == "PISTOLS_HEAVY"
    assert out["items"][0]["system"]["subtype"] == "PISTOLS_LIGHT"


def test_stale_hook_key_fails_loud(tmp_path, monkeypatch, capsys):
    _write_fake_page(tmp_path)
    module = SimpleNamespace(
        TABLES=[_firearm_spec()],
        RENAMES={("weapons_firearms", "no_such_slug"): "Ghost"},
    )
    _patch_profile(monkeypatch, module)
    rc = parse_book("testbook", "gear", tmp_path, [])
    assert rc == 1
    assert "STALE HOOK KEY" in capsys.readouterr().out


def test_fixes_sidecar_overlays_profile(tmp_path, monkeypatch):
    _write_fake_page(tmp_path)
    fixes = tmp_path / "_fixes" / "testbook_gear_fixes.py"
    fixes.parent.mkdir(parents=True)
    fixes.write_text(
        'RENAMES = {("weapons_firearms", "zapgun_mk1"): "Zapgun Mk1 Special"}\n',
        encoding="utf-8",
    )
    _patch_profile(monkeypatch, SimpleNamespace(TABLES=[_firearm_spec()]))
    rc = parse_book("testbook", "gear", tmp_path, [])
    assert rc == 0
    out = json.loads((tmp_path / "testbook" / "gear" / "weapons_firearms.json").read_text(encoding="utf-8"))
    assert out["items"][0]["name"] == "Zapgun Mk1 Special"
