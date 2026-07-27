from extractor.double_clutch import _is_stat_header, _norm_subtype, _parse_stat_row


def test_stat_header_detection():
    assert _is_stat_header("HAND ACC BODY ARM PILOT SENS SEAT AVAIL COST")
    assert not _is_stat_header("This classic road beast made a comeback")


def test_parse_stat_row():
    s = _parse_stat_row("4/3 15 20 160 5 4 1 1 2 2 7,000¥")
    assert s["type"] == "VEHICLES"
    assert s["handlOn"] == 4 and s["handlOff"] == 3
    assert s["bod"] == 5 and s["tspd"] == 160 and s["price"] == 7000
    assert "_note" not in s  # notes folded, never left in the system block


def test_parse_rejects_short_row():
    assert _parse_stat_row("4/3 15 20") is None


def test_norm_subtype():
    assert _norm_subtype("combat motorcycle") == "BIKE"
    assert _norm_subtype("heavy ATV") == "BIKE"
    assert _norm_subtype("luxury SUV") == "TRUCK_VAN"
    assert _norm_subtype("sedan") == "CAR"
    assert _norm_subtype("submarine") == "SUBMARINE"
    assert _norm_subtype("Weird New Thing") == "Weird_New_Thing"
