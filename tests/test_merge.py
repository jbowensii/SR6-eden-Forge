from extractor.merge import (
    add_reference,
    better_description,
    merge_book,
    norm_base,
    same_stats,
)

DATES = {"corebook": "2019-08", "firing_squad": "2021-06", "gun_rack": "2022-09"}


def item(id, name, system, book="corebook", page=10):
    return {
        "id": id,
        "name": name,
        "system": system,
        "meta": {
            "book": book,
            "page": page,
            "extractedAt": "2026-07-26",
            "extractorVersion": "0.2.0",
            "qaStatus": "extracted",
        },
    }


def incoming(name, system, page=42, description=None, img=None):
    d = {"name": name, "system": system, "page": page}
    if description:
        d["description"] = description
    if img:
        d["img"] = img
    return d


PISTOL = {"type": "WEAPON_FIREARMS", "dmgDef": "3P", "attackRating": [10, 10, 8, 0, 0], "price": 750, "avail": 2}


def test_norm_base_strips_variant():
    assert norm_base("Ares Predator VI") == norm_base("Ares Predator VI (Variant)")
    assert norm_base("Ares Predator VI") == "arespredatorvi"


def test_same_stats_ignores_formatting():
    a = {**PISTOL, "availDef": "2", "notes": "x"}
    b = {**PISTOL, "availDef": "2", "notes": "y different note"}
    assert same_stats(a, b)  # notes not a key field
    c = {**PISTOL, "price": 800}
    assert not same_stats(a, c)  # price differs


def test_same_stats_formula_pricing():
    a = {"type": "TOOLS", "price": 0, "priceDef": "Rating x 250¥"}
    b = {"type": "TOOLS", "price": 0, "priceDef": "Rating x 500¥"}
    assert not same_stats(a, b)  # different formula prices are different stats


def test_add_reference_seeds_and_dedupes():
    it = item("x", "X", PISTOL)
    assert add_reference(it, "firing_squad", 42) is True
    assert it["meta"]["sources"] == [
        {"book": "corebook", "page": 10},
        {"book": "firing_squad", "page": 42},
    ]
    assert add_reference(it, "firing_squad", 42) is False  # duplicate ref


def test_better_description_longest_then_newest():
    short, long = "a" * 100, "b" * 300
    # much longer wins regardless of book age
    assert better_description(long, "corebook", short, "firing_squad", DATES)[0] == long
    # comparable length -> newer book
    a, b = "x" * 300, "y" * 290
    text, book = better_description(a, "corebook", b, "firing_squad", DATES)
    assert book == "firing_squad" and text == b


def test_merge_duplicate_adds_reference():
    lib = {"weapons_firearms": [item("ares_predator_vi", "Ares Predator VI", PISTOL)]}
    merge_book(lib, {"weapons_firearms": [incoming("Ares Predator VI", dict(PISTOL))]},
               "firing_squad", DATES, "0.2.0", "2026-07-26")
    items = lib["weapons_firearms"]
    assert len(items) == 1  # no new item
    assert {"book": "firing_squad", "page": 42} in items[0]["meta"]["sources"]
    assert {"book": "corebook", "page": 10} in items[0]["meta"]["sources"]


def test_merge_different_stats_creates_variant():
    lib = {"weapons_firearms": [item("ares_predator_vi", "Ares Predator VI", PISTOL)]}
    variant_stats = {**PISTOL, "price": 900, "dmgDef": "4P"}
    _, stats = merge_book(lib, {"weapons_firearms": [incoming("Ares Predator VI", variant_stats)]},
                          "firing_squad", DATES, "0.2.0", "2026-07-26")
    items = lib["weapons_firearms"]
    assert len(items) == 2
    variant = items[1]
    assert variant["name"] == "Ares Predator VI (Variant)"
    assert variant["id"] == "ares_predator_vi_variant"
    assert variant["meta"]["variantOf"] == "ares_predator_vi"
    assert variant["meta"]["book"] == "firing_squad"
    assert stats["variants"] == 1


def test_merge_new_item_appended():
    lib = {"weapons_firearms": [item("ares_predator_vi", "Ares Predator VI", PISTOL)]}
    _, stats = merge_book(lib, {"weapons_firearms": [incoming("Krime Cannon", {"type": "WEAPON_FIREARMS", "dmgDef": "5P", "price": 3000})]},
                          "firing_squad", DATES, "0.2.0", "2026-07-26")
    assert stats["new"] == 1
    assert lib["weapons_firearms"][1]["name"] == "Krime Cannon"
    assert lib["weapons_firearms"][1]["meta"]["book"] == "firing_squad"


def test_reprint_skips_identical():
    lib = {"weapons_firearms": [item("ares_predator_vi", "Ares Predator VI", PISTOL)]}
    _, stats = merge_book(lib, {"weapons_firearms": [incoming("Ares Predator VI", dict(PISTOL))]},
                          "corebook_berlin", DATES, "0.2.0", "2026-07-26", reprint=True)
    assert stats["skipped"] == 1
    assert len(lib["weapons_firearms"]) == 1
    # no berlin reference added for an identical reprint item
    assert all(s["book"] != "corebook_berlin" for s in lib["weapons_firearms"][0]["meta"].get("sources", []))


def test_reprint_dedups_noisy_difference():
    # a reprint's stat "difference" is extraction noise, not new gear: dedup it
    # rather than spawning a false variant.
    lib = {"weapons_firearms": [item("ares_predator_vi", "Ares Predator VI", PISTOL)]}
    _, stats = merge_book(lib, {"weapons_firearms": [incoming("Ares Predator VI", {**PISTOL, "price": 999})]},
                          "corebook_berlin", DATES, "0.2.0", "2026-07-26", reprint=True)
    assert stats["variants"] == 0
    assert stats["skipped"] == 1
    assert len(lib["weapons_firearms"]) == 1


def test_reprint_drops_unmatched_fragments():
    # an item a reprint "adds" that the base library lacks is an extraction
    # fragment (a reprint introduces no new gear) -> dropped, not added.
    lib = {"weapons_firearms": [item("ares_predator_vi", "Ares Predator VI", PISTOL)]}
    _, stats = merge_book(lib, {"weapons_firearms": [incoming("Rating 3", {"type": "CYBERWARE", "price": 100})]},
                          "corebook_berlin", DATES, "0.2.0", "2026-07-26", reprint=True)
    assert stats["new"] == 0 and stats["skipped"] == 1
    assert len(lib["weapons_firearms"]) == 1


def test_merge_attaches_image_when_missing():
    lib = {"weapons_firearms": [item("ares_predator_vi", "Ares Predator VI", PISTOL)]}
    merge_book(lib, {"weapons_firearms": [incoming("Ares Predator VI", dict(PISTOL), img="firing_squad/ares_predator_vi.png")]},
               "firing_squad", DATES, "0.2.0", "2026-07-26")
    assert lib["weapons_firearms"][0]["img"] == "firing_squad/ares_predator_vi.png"


def test_merge_keeps_better_description():
    base = item("ares_predator_vi", "Ares Predator VI", PISTOL)
    base["system"]["description"] = "short one"
    base["meta"]["descriptionFrom"] = "corebook"
    lib = {"weapons_firearms": [base]}
    merge_book(lib, {"weapons_firearms": [incoming("Ares Predator VI", dict(PISTOL), description="a much longer and more complete writeup " * 5)]},
               "firing_squad", DATES, "0.2.0", "2026-07-26")
    kept = lib["weapons_firearms"][0]
    assert "much longer" in kept["system"]["description"]
    assert kept["meta"]["descriptionFrom"] == "firing_squad"


# ---------- Commlink6 display names ----------

def _fake_jar(tmp_path, files):
    """A jar carrying only i18n properties, which is all read_book needs here."""
    import zipfile
    p = tmp_path / "cl6.jar"
    with zipfile.ZipFile(p, "w") as z:
        for book, body in files.items():
            z.writestr(
                f"de/rpgframework/shadowrun6/data/{book}/i18n/{book}.properties", body)
    return p


def test_a_name_is_found_in_another_books_properties(tmp_path):
    """A book's XML routinely names entries defined in another book's file.

    The Dodge Scoot is defined in Double Clutch's data but NAMED in the core
    rulebook's properties. Looking only in <book>.properties left 82 items in
    the library with an empty name.
    """
    from extractor import commlink6

    commlink6._ALL_NAMES.clear()
    jar = _fake_jar(tmp_path, {"core": "item.dodge_scoot=Dodge Scoot\n",
                               "double_clutch": "item.other=Other\n"})
    import zipfile
    with zipfile.ZipFile(jar) as z:
        names = commlink6._all_english_names(z, str(jar))
    assert names["dodge_scoot"] == "Dodge Scoot"


def test_the_books_own_name_beats_the_fallback(tmp_path):
    """A per-book override must survive the cross-book fallback.

    read_book consults `<book>.properties` first and only falls back to the
    rest of the jar, so a book that deliberately renames a shared entry keeps
    its wording.
    """
    import zipfile

    from extractor import commlink6

    commlink6._ALL_NAMES.clear()
    jar = _fake_jar(tmp_path, {"core": "item.widget=Generic Widget\n",
                               "double_clutch": "item.widget=Rigger Widget\n"})
    with zipfile.ZipFile(jar) as z:
        own = commlink6._i18n(z, "double_clutch")
        shared = commlink6._all_english_names(z, str(jar))
    # both know the id; read_book takes the book's own, not the shared one
    assert own["widget"]["name"] == "Rigger Widget"
    assert shared["widget"] in ("Generic Widget", "Rigger Widget")
    assert (own["widget"].get("name") or shared["widget"]) == "Rigger Widget"


def test_german_names_never_reach_the_english_index(tmp_path):
    """Ownership rule: German content stays out unless the German PDF is owned."""
    from extractor import commlink6

    commlink6._ALL_NAMES.clear()
    jar = _fake_jar(tmp_path, {"core": "item.keep=Keep\n",
                               "core_de": "item.drop=Pflock\n"})
    import zipfile
    with zipfile.ZipFile(jar) as z:
        names = commlink6._all_english_names(z, str(jar))
    assert "keep" in names and "drop" not in names
