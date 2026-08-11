

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
