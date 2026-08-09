"""Re-applying manual corrections after a re-import.

The interesting case is not the happy path — it is what happens when the
extractor improves and an item's id moves out from under a correction that was
keyed to it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "apply_corrections.py"


def _library(root: Path, items: list[dict], domain="vehicles", category="vehicles"):
    d = root / "corebook" / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{category}.json").write_text(json.dumps(
        {"book": "corebook", "domain": domain, "category": category, "items": items},
        indent=2), encoding="utf-8")


def _correction(root: Path, rec: dict, domain="vehicles"):
    d = root / "_corrections" / domain
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rec['id']}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")


def _item(iid, name, **system):
    return {"id": iid, "name": name, "system": {"type": "VEHICLE", **system},
            "meta": {"book": "corebook", "page": 1, "qaStatus": "extracted"}}


def _run(root: Path):
    """Run the tool against a temp library, never the real one."""
    r = subprocess.run([sys.executable, "-u", str(TOOL), "--apply"],
                       capture_output=True, text=True, cwd=str(REPO),
                       env=dict(os.environ, SR6_DATA=str(root)))
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _items(root: Path, domain="vehicles", category="vehicles"):
    return json.loads((root / "corebook" / domain / f"{category}.json")
                      .read_text(encoding="utf-8"))["items"]


def test_a_tombstone_still_deletes_after_the_id_changed(tmp_path):
    """The exact failure seen on 2026-08-08.

    Rejoining wrapped vehicle names turned krupp_bentley into
    cl6_saeder_krupp_bentley_concordat. A deletion keyed to the old id would
    silently stop working, and a row deleted months ago would come back.
    """
    _library(tmp_path, [_item("cl6_saeder_krupp_bentley_concordat",
                              "Saeder-Krupp-Bentley Concordat")])
    _correction(tmp_path, {"domain": "vehicles", "category": "vehicles",
                           "id": "krupp_bentley", "deleted": True,
                           "ref": {"name": "Saeder-Krupp-Bentley Concordat",
                                   "book": "corebook"}})
    out = _run(tmp_path)
    assert _items(tmp_path) == []
    assert "matched on name" in out


def test_a_tombstone_matched_by_id_still_works(tmp_path):
    """Records written before ref existed must keep functioning."""
    _library(tmp_path, [_item("junk_row", "Junk Row"), _item("keep_me", "Keep Me")])
    _correction(tmp_path, {"domain": "vehicles", "category": "vehicles",
                           "id": "junk_row", "deleted": True})
    _run(tmp_path)
    assert [i["id"] for i in _items(tmp_path)] == ["keep_me"]


def test_an_ambiguous_name_is_left_alone(tmp_path):
    """Two rows answer to the name — deleting the wrong one is unrecoverable.

    Commlink6 reuses ids and names repeat across books, so 'the only row with
    this name' is the only safe re-match.
    """
    _library(tmp_path, [_item("twin_a", "Ares Roadmaster"),
                        _item("twin_b", "Ares Roadmaster")])
    _correction(tmp_path, {"domain": "vehicles", "category": "vehicles",
                           "id": "gone_id", "deleted": True,
                           "ref": {"name": "Ares Roadmaster", "book": "corebook"}})
    _run(tmp_path)
    assert len(_items(tmp_path)) == 2          # nothing removed


def test_an_edit_also_re_finds_its_item_by_name(tmp_path):
    """The fallback is not delete-only; a re-keyed edit lands too."""
    _library(tmp_path, [_item("cl6_new_id", "Proteus Lamprey/Sea Snake")])
    _correction(tmp_path, {"domain": "vehicles", "category": "vehicles",
                           "id": "lamprey_sea",
                           "ref": {"name": "Proteus Lamprey/Sea Snake", "book": "corebook"},
                           "changed": {"system": {"handling": "3"}}})
    _run(tmp_path)
    assert _items(tmp_path)[0]["system"]["handling"] == "3"
