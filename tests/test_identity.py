"""Catalog ids: minted once, and never moved again."""
from extractor.identity import IdLock, slugify, stamp_catalog_ids


def test_commlink6_ids_are_never_regenerated(tmp_path):
    """They are the cross-reference eden matches on."""
    lock = IdLock(tmp_path, "corebook")
    items = [{"name": "Ares Predator VI",
              "system": {"genesisID": "ares_predator_vi"},
              "meta": {"source": "commlink6"}}]
    stamp_catalog_ids(items, "corebook", "gear", "CAT28000", lock)
    assert items[0]["system"]["genesisID"] == "ares_predator_vi"


def test_pdf_only_items_are_minted_from_the_product_code(tmp_path):
    lock = IdLock(tmp_path, "corebook")
    items = [{"name": "Ares Predator VI", "system": {}, "meta": {"page": 251}}]
    stamp_catalog_ids(items, "corebook", "gear", "CAT28000", lock)
    assert items[0]["system"]["genesisID"] == "cat28000_gear_ares_predator_vi"


def test_an_id_survives_the_name_being_corrected(tmp_path):
    """The reason the lockfile exists. Fixing a typo in the review app must not
    move the id, or every character linked to that item is orphaned."""
    items = [{"name": "Ares Predatar VI", "system": {}, "meta": {"page": 251}}]
    lock = IdLock(tmp_path, "corebook")
    stamp_catalog_ids(items, "corebook", "gear", "CAT28000", lock)
    first = items[0]["system"]["genesisID"]
    lock.save()

    # a human fixes the spelling, and the library is re-imported
    corrected = [{"name": "Ares Predator VI", "system": {},
                  "meta": {"page": 251, "originalName": "Ares Predatar VI"}}]
    lock2 = IdLock(tmp_path, "corebook")
    stamp_catalog_ids(corrected, "corebook", "gear", "CAT28000", lock2)
    assert corrected[0]["system"]["genesisID"] == first


def test_reimport_is_stable(tmp_path):
    """Same input twice must give the same ids, or every rebuild churns."""
    make = lambda: [{"name": f"Item {i}", "system": {}, "meta": {"page": i}}
                    for i in range(5)]
    a, b = make(), make()
    lock = IdLock(tmp_path, "corebook")
    stamp_catalog_ids(a, "corebook", "gear", "CAT28000", lock)
    lock.save()
    stamp_catalog_ids(b, "corebook", "gear", "CAT28000", IdLock(tmp_path, "corebook"))
    assert [x["system"]["genesisID"] for x in a] == [x["system"]["genesisID"] for x in b]


def test_collisions_get_a_suffix_and_keep_it(tmp_path):
    """Two records that slug the same must not swap ids on a later run."""
    items = [{"name": "Grenade", "system": {}, "meta": {"page": 10}},
             {"name": "Grenade", "system": {}, "meta": {"page": 44}}]
    lock = IdLock(tmp_path, "corebook")
    stamp_catalog_ids(items, "corebook", "gear", "CAT28000", lock)
    ids = [i["system"]["genesisID"] for i in items]
    assert len(set(ids)) == 2
    assert ids[1].endswith("_2")
    lock.save()

    again = [{"name": "Grenade", "system": {}, "meta": {"page": 44}}]
    stamp_catalog_ids(again, "corebook", "gear", "CAT28000", IdLock(tmp_path, "corebook"))
    assert again[0]["system"]["genesisID"] == ids[1]


def test_page_is_not_part_of_the_id():
    """Pages move between printings; an id built on them breaks on reprint."""
    assert "251" not in slugify("Ares Predator VI")


def test_slug_handles_the_punctuation_extraction_produces():
    assert slugify("Ares Predator VI") == "ares_predator_vi"
    assert slugify("Renraku Sensei’s Kit") == "renraku_senseis_kit"
    assert slugify("  ") == "unnamed"
