

# ---------- the corebook gets the same reader as every other book ----------

def _ingest_src():
    from pathlib import Path
    return (Path(__file__).resolve().parent.parent / "tools" / "ingest_vehicles.py"
            ).read_text(encoding="utf-8")


def test_the_corebook_is_not_scanned_a_third_time():
    """Adding it looks like a clear win from inside the corebook — the anchored
    reader finds 45 names on pp. 301-306 against the 37 the two corebook readers
    find, seemingly 27 nobody has. Across the whole library it adds exactly zero:
    Double Clutch already carries all 27. Measured both ways: 316 names, nothing
    lost. Re-adding it costs scan time and makes shared names depend on worker
    completion order."""
    text = _ingest_src()
    assert 'if b not in ("corebook", "gun_rack", "rides")' in text


def test_the_corebook_text_readers_still_run_first():
    """They are unioned, not replaced. The ruled tables carry the broad printed
    subtypes and the token pass covers the single-flow page the tables
    under-read; the anchored scan only fills names neither of them found, so it
    must merge with setdefault AFTER both."""
    text = _ingest_src()
    assert text.index("read_vehicles_text(core") < text.index("jobs = ["), \
        "the anchored scan now runs before the corebook readers"
    tail = text[text.index("for r in map_jobs(vehicle_scan_book"):]
    assert "byname.setdefault(" in tail, "scanned rows must not overwrite the table rows"


# ---------- a deleted vehicle must not come back on the next import ----------

def test_deleted_vehicles_are_read_from_the_corrections_layer(tmp_path):
    import importlib.util, json
    src = __import__("pathlib").Path(__file__).resolve().parent.parent / "tools" / "ingest_vehicles.py"
    spec = importlib.util.spec_from_file_location("_iv_del", src)
    iv = importlib.util.module_from_spec(spec); spec.loader.exec_module(iv)

    d = tmp_path / "_corrections" / "vehicles"
    d.mkdir(parents=True)
    (d / "a.json").write_text(json.dumps(
        {"domain": "vehicles", "id": "cl6_gmc_bulldog", "deleted": True,
         "ref": {"name": "GMC Bulldog"}}), encoding="utf-8")
    (d / "b.json").write_text(json.dumps(
        {"domain": "vehicles", "id": "cl6_keep_me", "name": "Keeper"}), encoding="utf-8")
    (d / "c.json").write_text(json.dumps(
        {"domain": "gear", "id": "g1", "deleted": True}), encoding="utf-8")

    ids, names = iv.deleted_vehicles(tmp_path)
    assert ids == {"cl6_gmc_bulldog"}, "a live correction or another domain leaked in"
    assert "gmcbulldog" in names, "the name is needed too — a fold moves the id"


def test_the_ingest_drops_deleted_rows_before_writing():
    """fold_into_authority carries through every Commlink6 row, so a vehicle
    deleted in the review app is rebuilt by the next import. Thirty were back in
    the library that way; the count only looked right because apply_corrections
    had not run since. The deletion has to be applied by the thing that rebuilds
    the domain, not by a later phase that may or may not follow it."""
    text = _ingest_src()
    assert "dead_ids, dead_names = deleted_vehicles(DATA)" in text
    assert text.index("deleted_vehicles(DATA)") < text.index("recs = sorted(byname.values()"), \
        "the drop must happen before the rows are written"
