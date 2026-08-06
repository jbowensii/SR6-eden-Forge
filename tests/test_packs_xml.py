"""Companion gear PACKs — bundle contents, and the traps in reading them."""
import zipfile

import pytest

from extractor.commlink6 import DEFAULT_JAR
from extractor.packs_xml import SIN_LEVELS, parse_packs


@pytest.fixture(scope="module")
def packs():
    if not DEFAULT_JAR.exists():
        pytest.skip("Commlink6 jar not present")
    with zipfile.ZipFile(DEFAULT_JAR) as z:
        return parse_packs(z)


def test_english_only(packs):
    """289 PACKs ship; 112 are lang="de" and this project is English-only."""
    assert len(packs) == 177
    assert "starterpack" in packs


def test_starter_pack_price_and_shape(packs):
    p = packs["starterpack"]
    assert p["price"] == 25000
    assert p["subtype"] == "PACK_COMPLETE"
    kinds = {r["kind"] for r in p["contents"]}
    # not just gear: the Companion's starter kit includes ID and a lifestyle
    assert {"gear", "sin", "license", "lifestyle"} <= kinds


def test_sin_levels_are_not_in_the_obvious_order():
    """Read from Commlink6's own labels, not guessed from the names:
    "superficially plausible" is 4, despite sounding like the weakest."""
    assert SIN_LEVELS["ROUGH_MATCH"] == 2
    assert SIN_LEVELS["SUPERFICIALLY_PLAUSIBLE"] == 4
    assert SIN_LEVELS["SECOND_LIFE"] == 6


def test_nested_packs_are_flattened(packs):
    """pack_hacker_a lists pack_cyberprograms; a buyer wants the programs."""
    refs = [r["ref"] for r in packs["pack_hacker_a"]["contents"]]
    assert "pack_cyberprograms" not in refs
    assert "exploit" in refs


def test_augment_pack_carries_one_essence_cost(packs):
    assert packs["pack_hacker_a"]["essence"] == pytest.approx(3.8)


def test_grades_are_read_as_grades(packs):
    """The grade selector has no <choice> definition, so it is matched by
    value; a regression would leave USED/STANDARD sitting in `text`."""
    rows = packs["pack_hacker_a"]["contents"]
    graded = [r for r in rows if r["grade"]]
    assert graded, "no augmentation grades parsed"
    assert all(r["text"] is None or r["text"] not in {"USED", "STANDARD"} for r in rows)


def test_every_referenced_item_resolves(packs):
    """A pack must not reference gear the local library lacks *for a book that
    has been ingested*.

    Scoped deliberately. PACKs come from the Companion but reference items
    across the whole line, so a pack naming a Firing Squad weapon is not a
    fault when Firing Squad has not been imported — it is just a book the user
    does not own or has not run yet. Asserting zero unresolved refs outright
    made this test fail the moment the library covered fewer books than the
    jar, which says nothing about the parser.
    """
    import json
    import pathlib
    import re
    import zipfile

    from extractor.commlink6 import DEFAULT_JAR

    have = set()
    for f in pathlib.Path("data").rglob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            for it in d["items"]:
                s = it.get("system") or {}
                cid = s.get("genesisID") or s.get("catalogId")
                if cid:
                    have.add(cid)
    if not have:
        pytest.skip("item library not present")

    # which book each id comes from, so a miss can be attributed
    owner: dict[str, str] = {}
    ingested = {d.name for d in pathlib.Path("data").iterdir() if d.is_dir()}
    with zipfile.ZipFile(DEFAULT_JAR) as z:
        for n in z.namelist():
            m = re.match(r"de/rpgframework/shadowrun6/data/([^/]+)/data/[^/]+\.xml$", n)
            if not m:
                continue
            for gid in re.findall(rb'<item[^>]*id="([^"]+)"', z.read(n)):
                owner.setdefault(gid.decode(), m.group(1))

    missing = set()
    for p in packs.values():
        for r in p["contents"]:
            refs = [r["ref"]] + [e["ref"] for e in r["embeds"]]
            for ref in refs:
                if not ref or r["kind"] != "gear" or ref in have:
                    continue
                # only a fault when we claim to have imported that book
                if owner.get(ref, "corebook") in ingested:
                    missing.add(ref)
    assert not missing, (
        f"packs reference {len(missing)} items missing from an INGESTED book: "
        f"{sorted(missing)[:10]}")
