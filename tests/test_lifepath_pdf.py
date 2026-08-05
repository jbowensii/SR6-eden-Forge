"""The English life-module extraction from the Sixth World Companion PDF."""
import json
import pathlib

import pytest

BOOKS = pathlib.Path("data/books.json")
_pdf = None
if BOOKS.exists():
    _pdf = json.loads(BOOKS.read_text(encoding="utf-8")).get("companion", {}).get("pdf")

pytestmark = pytest.mark.skipif(
    not _pdf or not pathlib.Path(_pdf).exists(),
    reason="Sixth World Companion PDF not available",
)


@pytest.fixture(scope="module")
def modules():
    from extractor.lifepath_pdf import extract
    return extract(_pdf)


def test_extracts_the_whole_catalogue(modules):
    assert len(modules) > 75, "the Companion lists ~80 adult and event modules"


def test_every_module_grants_something(modules):
    barren = [k for k, v in modules.items() if not v["grants"]]
    assert not barren, f"modules with no parsed grants: {barren}"


def test_artifact_hunter_matches_the_book(modules):
    """Companion p35 — three 'choose one' bullets, 25,000 nuyen, 2 contact points."""
    m = modules["artifact_hunter"]
    assert m["name"] == "Artifact Hunter"
    assert m["grants"]["nuyen"] == 25000
    assert m["grants"]["contactPoints"] == 2
    assert m["grants"]["attributePoints"] == 2      # two pure-attribute choices
    assert m["grants"]["skillPoints"] == 1
    assert m["knowledgeSkills"] == 1
    assert set(m["contactTypes"]) == {"Magic", "Street"}


def test_module_spanning_a_page_break_is_complete(modules):
    """Office Manager runs from p43 onto p44; its later bullets must survive."""
    m = modules["office_manager"]
    assert m["grants"]["nuyen"] == 50000
    assert m["grants"]["contactPoints"] == 2
    assert m["knowledgeSkills"] == 1


def test_restricted_modules_carry_their_requirement(modules):
    assert modules["alchemist"]["requires"] == "awakened"
    assert modules["adept_training"]["requires"] == "adept"
    assert modules["technomancer"]["requires"] == "emerged"
    assert modules["artist"]["requires"] is None


def test_event_modules_parse_their_unlabelled_bullets(modules):
    """Events write bare '+2 to Agility, ...' lines with no label span."""
    m = modules["event_your_body_was_pushed_to_its_limits"]
    assert m["grants"]["attributePoints"] == 4      # +2, +1, +1
    assert m["grants"]["contactPoints"] == 4


def test_mixed_choices_are_held_back_not_guessed(modules):
    """"+1 to Edge, Resonance, or +25,000 nuyen" cannot be charged to a pool
    until the player says which — Lawyer's mixed bullet must not inflate its
    attribute or skill grant (Companion p41)."""
    m = modules["lawyer"]
    kinds = [c["kind"] for c in m["choices"]]
    assert kinds.count("mixed") == 1
    assert m["grants"]["attributePoints"] == 1      # the one pure-attribute bullet
    assert m["grants"]["skillPoints"] == 1          # the one pure-skill bullet


def test_a_cash_option_keeps_its_thousands_separator(modules):
    """A comma inside 25,000 is not an option separator."""
    choice = next(c for c in modules["lawyer"]["choices"] if c["kind"] == "mixed")
    assert choice["options"] == ["edg", "nuyen:25000"]
