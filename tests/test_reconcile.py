"""Reconciling the jar's reading and the book's reading of the same record."""
from extractor.reconcile import JAR_WINS, PDF_WINS, reconcile_item, reconcile_library


def jar(name="Ares Predator VI", **sys):
    return {"name": name, "system": sys, "meta": {"source": "commlink6"}}


def pdf(name="Ares Predator VI", **sys):
    return {"name": name, "system": sys, "meta": {"source": "pdf", "page": 251}}


def test_only_one_source_has_it_so_no_conflict():
    merged, c = reconcile_item(jar(price=725), pdf(description="A heavy pistol."))
    assert merged["system"]["price"] == 725
    assert merged["system"]["description"] == "A heavy pistol."
    assert c == []


def test_agreement_is_not_a_conflict():
    _, c = reconcile_item(jar(price=725), pdf(price=725))
    assert c == []


def test_the_book_wins_on_prose():
    merged, c = reconcile_item(jar(description="short"), pdf(description="the full paragraph"))
    assert merged["system"]["description"] == "the full paragraph"
    assert c and "-> pdf" in c[0]


def test_the_jar_wins_on_declared_mechanisms():
    """Mounts and ratings are declarations in the jar; the page barely says them."""
    merged, c = reconcile_item(jar(rating=6), pdf(rating=4))
    assert merged["system"]["rating"] == 6
    assert "-> commlink6" in c[0]


def test_a_disagreement_is_recorded_not_swallowed():
    merged, c = reconcile_item(jar(price=725), pdf(price=750))
    assert merged["meta"]["conflicts"] == ["price: commlink6=725 pdf=750 -> commlink6"]
    assert len(c) == 1


def test_a_conflict_pulls_an_approved_item_back_for_review():
    """Two sources disagreeing is exactly when a human should look again."""
    j = jar(price=725)
    j["meta"]["qaStatus"] = "approved"
    merged, _ = reconcile_item(j, pdf(price=750))
    assert merged["meta"]["qaStatus"] == "review"


def test_bookkeeping_fields_are_never_compared():
    merged, c = reconcile_item(jar(genesisID="a", img="x.png"),
                               pdf(genesisID="b", img="y.png"))
    assert c == []


def test_library_merge_keeps_records_unique_to_either_side():
    items, stats = reconcile_library(
        [jar("Ares Predator VI", price=725), jar("Jar Only Item", price=10)],
        [pdf("Ares Predator VI", price=750), pdf("Book Only Item", price=20)],
    )
    names = sorted(i["name"] for i in items)
    assert names == ["Ares Predator VI", "Book Only Item", "Jar Only Item"]
    assert stats == {"matched": 1, "conflicts": 1, "jarOnly": 1, "pdfOnly": 1}


def test_precedence_tables_do_not_overlap():
    assert not (JAR_WINS & PDF_WINS)
