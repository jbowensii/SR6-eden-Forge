"""Commlink6 is the source of truth: enhance it, never overwrite it.

The post-merge phases were written when the library came only from PDFs and
none of them checks a row's provenance. rebuild_descriptions in particular does

    item["system"]["description"] = new        # new may be ""

so a Commlink6 description is not just replaced when the page yields nothing —
it is erased. These tests pin the guard that surrounds those phases.
"""
from __future__ import annotations

import json

from extractor.authority import is_authoritative, restore, snapshot


def _lib(root, items, domain="gear", cat="electronics"):
    d = root / "corebook" / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{cat}.json").write_text(
        json.dumps({"book": "corebook", "domain": domain,
                    "category": cat, "items": items}),
        encoding="utf-8")
    return d / f"{cat}.json"


def _cl6(id_, **system):
    return {"id": id_, "name": id_, "system": system,
            "meta": {"book": "corebook", "source": "commlink6"}}


def _pdf(id_, **system):
    return {"id": id_, "name": id_, "system": system,
            "meta": {"book": "corebook", "source": "pdf"}}


def test_an_erased_commlink6_description_is_put_back(tmp_path):
    """The exact failure: a phase blanks it because the page had nothing."""
    f = _lib(tmp_path, [_cl6("a", description="From Commlink6.", type="ELECTRONICS")])
    snap = snapshot(tmp_path)

    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["items"][0]["system"]["description"] = ""        # rebuild_descriptions
    f.write_text(json.dumps(doc), encoding="utf-8")

    stats = restore(tmp_path, snap)
    assert stats["restored"] == 1
    back = json.loads(f.read_text(encoding="utf-8"))["items"][0]
    assert back["system"]["description"] == "From Commlink6."


def test_an_overwritten_commlink6_type_is_put_back(tmp_path):
    f = _lib(tmp_path, [_cl6("a", type="CYBERWARE", subtype="HEADWARE")])
    snap = snapshot(tmp_path)

    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["items"][0]["system"]["type"] = "ELECTRONICS"    # fix_gear_types
    doc["items"][0]["system"]["subtype"] = "OTHER"
    f.write_text(json.dumps(doc), encoding="utf-8")

    restore(tmp_path, snap)
    got = json.loads(f.read_text(encoding="utf-8"))["items"][0]["system"]
    assert got["type"] == "CYBERWARE"
    assert got["subtype"] == "HEADWARE"


def test_a_gap_commlink6_left_empty_is_KEPT(tmp_path):
    """The other half of the rule: filling a gap is enhancement, and stands."""
    f = _lib(tmp_path, [_cl6("a", description="", type="ELECTRONICS")])
    snap = snapshot(tmp_path)

    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["items"][0]["system"]["description"] = "Read from the page."
    f.write_text(json.dumps(doc), encoding="utf-8")

    stats = restore(tmp_path, snap)
    assert stats["restored"] == 0
    kept = json.loads(f.read_text(encoding="utf-8"))["items"][0]
    assert kept["system"]["description"] == "Read from the page."


def test_pdf_rows_are_left_entirely_alone(tmp_path):
    """The guard protects the authority, not everything."""
    f = _lib(tmp_path, [_pdf("a", description="From the page.")])
    snap = snapshot(tmp_path)
    assert snap["fields"] == {} and snap["rows"] == {}

    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["items"][0]["system"]["description"] = "Rewritten by a later phase."
    f.write_text(json.dumps(doc), encoding="utf-8")

    assert restore(tmp_path, snap)["restored"] == 0
    got = json.loads(f.read_text(encoding="utf-8"))["items"][0]
    assert got["system"]["description"] == "Rewritten by a later phase."


def test_zero_and_false_count_as_real_values(tmp_path):
    """A price of 0 is something Commlink6 said, not an empty field."""
    f = _lib(tmp_path, [_cl6("a", price=0, rating=False)])
    snap = snapshot(tmp_path)
    assert snap["fields"]["a"]["price"] == 0

    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["items"][0]["system"]["price"] = 9999
    f.write_text(json.dumps(doc), encoding="utf-8")

    restore(tmp_path, snap)
    assert json.loads(f.read_text(encoding="utf-8"))["items"][0]["system"]["price"] == 0


def test_the_guard_spans_every_domain_not_just_gear(tmp_path):
    _lib(tmp_path, [_cl6("s1", description="Commlink6 spell text.")],
         domain="spells", cat="combat")
    _lib(tmp_path, [_cl6("q1", description="Commlink6 quality text.")],
         domain="qualities", cat="positive")
    snap = snapshot(tmp_path)
    assert set(snap["fields"]) == {"s1", "q1"}


def test_is_authoritative_reads_the_provenance_stamp():
    assert is_authoritative({"meta": {"source": "commlink6"}})
    assert not is_authoritative({"meta": {"source": "pdf"}})
    assert not is_authoritative({"meta": {}})
    assert not is_authoritative({})


def test_a_deleted_commlink6_row_is_brought_back(tmp_path):
    """Deleting is the most complete form of clobbering there is.

    ingest_vehicles rewrites vehicles.json wholesale from its own reading of
    the books, which dropped 366 Commlink6 vehicles outright. Restoring fields
    cannot help a row that is no longer there, so the row itself is recovered.
    """
    f = _lib(tmp_path, [_cl6("v1", description="Commlink6 vehicle."),
                        _cl6("v2", description="Another.")],
             domain="vehicles", cat="vehicles")
    snap = snapshot(tmp_path)

    # the phase replaces the whole file with what it read from the page
    f.write_text(json.dumps({"book": "corebook", "domain": "vehicles",
                             "category": "vehicles",
                             "items": [_pdf("p1", description="From the page.")]}),
                 encoding="utf-8")

    stats = restore(tmp_path, snap)
    assert stats["resurrected"] == 2

    items = {i["id"]: i for i in
             json.loads(f.read_text(encoding="utf-8"))["items"]}
    assert set(items) == {"p1", "v1", "v2"}          # the PDF row is kept too
    assert items["v1"]["system"]["description"] == "Commlink6 vehicle."
    assert items["v1"]["meta"]["source"] == "commlink6"


def test_a_deleted_row_is_restored_even_if_the_file_went_with_it(tmp_path):
    f = _lib(tmp_path, [_cl6("v1", description="Commlink6 vehicle.")],
             domain="vehicles", cat="vehicles")
    snap = snapshot(tmp_path)
    f.unlink()

    assert restore(tmp_path, snap)["resurrected"] == 1
    doc = json.loads(f.read_text(encoding="utf-8"))
    assert doc["domain"] == "vehicles"
    assert doc["items"][0]["id"] == "v1"


def test_resurrection_does_not_duplicate_a_row_that_survived(tmp_path):
    f = _lib(tmp_path, [_cl6("a", description="Kept.")])
    snap = snapshot(tmp_path)
    stats = restore(tmp_path, snap)
    assert stats["resurrected"] == 0
    assert len(json.loads(f.read_text(encoding="utf-8"))["items"]) == 1


def test_rows_sharing_an_id_are_all_recovered(tmp_path):
    """Commlink6 reuses ids: 385 vehicle rows share only 356 of them.

    Keyed by id, the snapshot kept one row of each colliding pair, so 29
    vehicles stayed dead after the guard reported "restored". Rows are counted
    per id now, not matched as a set.
    """
    f = _lib(tmp_path, [_cl6("dup", description="First."),
                        _cl6("dup", description="Second."),
                        _cl6("solo", description="Third.")],
             domain="vehicles", cat="vehicles")
    snap = snapshot(tmp_path)

    # a phase rewrites the file from its own reading
    f.write_text(json.dumps({"book": "corebook", "domain": "vehicles",
                             "category": "vehicles", "items": []}),
                 encoding="utf-8")

    stats = restore(tmp_path, snap)
    assert stats["resurrected"] == 3          # not 2

    items = json.loads(f.read_text(encoding="utf-8"))["items"]
    assert len(items) == 3
    assert sorted(i["system"]["description"] for i in items) == \
        ["First.", "Second.", "Third."]


def test_a_partial_deletion_of_duplicate_ids_restores_only_the_gap(tmp_path):
    """Two rows shared an id, one survived — bring back one, not two."""
    f = _lib(tmp_path, [_cl6("dup", description="First."),
                        _cl6("dup", description="Second.")],
             domain="vehicles", cat="vehicles")
    snap = snapshot(tmp_path)

    doc = json.loads(f.read_text(encoding="utf-8"))
    doc["items"] = [doc["items"][0]]
    f.write_text(json.dumps(doc), encoding="utf-8")

    assert restore(tmp_path, snap)["resurrected"] == 1
    assert len(json.loads(f.read_text(encoding="utf-8"))["items"]) == 2
