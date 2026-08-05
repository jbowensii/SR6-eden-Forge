"""Chargen-data extraction tests. Skipped wholesale when the Commlink6 jar is
not installed (the dataset is an external dependency, not repo content)."""
import json

import pytest

from extractor.commlink6 import DEFAULT_JAR, read_book

jar_missing = not DEFAULT_JAR.exists()
pytestmark = pytest.mark.skipif(jar_missing, reason="Commlink6 jar not installed")


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    from tools.build_chargen_data import build
    out = tmp_path_factory.mktemp("chargen") / "chargen-data.json"
    return build(DEFAULT_JAR, out)


# --- i18n regex fix ---------------------------------------------------------- #
def test_core_metatype_names_resolve():
    recs = read_book("core")
    for mid, name in [("human", "Human"), ("elf", "Elf"), ("dwarf", "Dwarf"),
                      ("ork", "Ork"), ("troll", "Troll")]:
        assert recs[mid]["name"] == name


def test_hyphenated_ids_resolve():
    recs = read_book("core")
    assert recs["human-looking"]["name"] == "Human-Looking"
    assert recs["low-light_vision"]["name"] == "Low-Light Vision"


def test_case_insensitive_i18n_fallback():
    recs = read_book("core")
    assert recs["mrJohnson"]["name"] == "Mr. Johnson"


# --- builder output ----------------------------------------------------------- #
def test_priority_table(data):
    P = data["priorities"]
    assert set(P) == {"A", "B", "C", "D", "E"}
    assert P["A"]["ATTRIBUTE"]["attributePoints"] == 24
    assert P["E"]["ATTRIBUTE"]["attributePoints"] == 2
    assert P["A"]["SKILLS"]["skillPoints"] == 32
    assert P["E"]["RESOURCES"]["nuyen"] == 8000
    assert P["A"]["RESOURCES"]["nuyen"] == 450000
    assert P["B"]["MAGIC"]["byMor"]["magician"] == 3
    assert P["B"]["MAGIC"]["byMor"]["aspectedmagician"] == 4
    assert P["E"]["MAGIC"]["byMor"] == {"mundane": 0}
    assert P["A"]["METATYPE"]["metatypes"]["dwarf"] == 13


def test_metatypes(data):
    mt = data["metatypes"]
    for mid in ("human", "elf", "dwarf", "ork", "troll"):
        assert mt[mid]["book"] == "core"
    assert mt["human"]["attributeMaxCreation"]["edg"] == 7
    assert mt["troll"]["attributeMaxCreation"]["bod"] == 9
    assert mt["troll"]["attributeMaxCreation"]["agi"] == 5
    assert mt["troll"]["priceMods"].get("EVERYTHING") == 0.1
    assert "thermographic_vision" in mt["troll"]["racialQualityIds"]
    # English rows win over lang=de duplicates
    assert mt["gnome"]["weight"] == "37"
    assert mt["gnome"]["variantOf"] == "dwarf"


def test_mor_types_match_eden_enum(data):
    assert set(data["morTypes"]) == {"mundane", "magician", "mysticadept",
                                     "technomancer", "adept", "aspectedmagician"}
    mag = data["morTypes"]["magician"]
    assert mag["magic"] and mag["spells"] and not mag["powers"]
    assert "sorcery" in mag["skillUnlocks"]
    assert data["morTypes"]["mysticadept"]["paysPowers"] is True
    assert data["morTypes"]["technomancer"]["resonance"] is True


def test_skills_and_specs(data):
    sk = data["skills"]
    assert len(sk) == 21
    assert sum(len(s["specializations"]) for s in sk.values()) >= 107
    assert sk["firearms"]["attr"] == "agi"
    assert sk["sorcery"]["restricted"] is True
    assert sk["knowledge"]["freeText"] and sk["language"]["freeText"]
    assert sk["athletics"]["specializations"]["climbing"]["attr"] == "str"


def test_rules_interpretations(data):
    srm = data["rules"]["srm"]["settings"]
    assert srm["maxAvailability"] == 7
    assert srm["maxKarmaRemaining"] == 5
    assert srm["adjustmentOnLoweredMax"] is False
    assert srm["expandedSpecializations"] is True


def test_upstream_rule_ids_never_reach_the_shipped_data(data):
    """The source data's SCREAMING_SNAKE rule ids are the upstream application's
    identifier namespace. They are translated once at the import boundary, so
    nothing downstream should ever see one."""
    for ruleset in data["rules"].values():
        for key in ruleset["settings"]:
            assert not key.isupper(), f"untranslated rule id in settings: {key}"
    for key in data["ruleLabels"]:
        assert not key.isupper(), f"untranslated rule id in ruleLabels: {key}"


def test_rule_setting_names_are_camel_case(data):
    from extractor.chargen_xml import RULE_SETTING_NAMES, setting_name

    assert setting_name("CHARGEN_MAX_AVAILABILITY") == "maxAvailability"
    # an id we have not mapped still comes out camelCase, never SCREAMING_SNAKE
    assert setting_name("SOME_FUTURE_RULE") == "someFutureRule"
    for name in RULE_SETTING_NAMES.values():
        assert name[0].islower() and "_" not in name


def test_quality_meta(data):
    q = data["qualityMeta"]
    bt = q["built_tough"]
    assert bt["karma"] == 4 and bt["positive"] and bt["max"] == 4


def test_lifestyles_and_contacts(data):
    assert data["lifestyles"]["low"]["cost"] == 2000
    fx = data["contactArchetypes"]["fixer"]
    assert fx["attributes"] and fx["skills"]         # stat blocks preserved now
    assert "FIXER" in fx["types"]


def test_lifepath_english_only(data):
    assert set(data["lifepathModules"]) >= {"ganger", "it_support",
                                            "teen_diva", "15_min_fame"}
