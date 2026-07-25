from pathlib import Path

from extractor.cache import page_path, read_page
from extractor.normalize import normalize_text


def test_normalize_unicode():
    s = "Zapgun’s 8/2*/—/–/− café 500¥ ﬁre"
    out = normalize_text(s)
    assert " " not in out and " 500¥" in out
    assert out.count("—") == 3  # en-dash and minus folded into em-dash
    assert "’" not in out and "'" in out
    assert "fire" in out


def test_soft_hyphen_stripped():
    assert normalize_text("com­bat") == "combat"


def test_page_path_layout(tmp_path):
    p = page_path(tmp_path, "corebook", 245)
    assert p == tmp_path / "_raw" / "corebook" / "pages" / "p245.txt"


def test_read_page_missing_names_dump(tmp_path):
    try:
        read_page(tmp_path, "corebook", 245)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        assert "extractor dump" in str(e)


def test_read_page_roundtrip(tmp_path):
    p = page_path(tmp_path, "corebook", 245)
    p.parent.mkdir(parents=True)
    p.write_text("hello", encoding="utf-8")
    assert read_page(tmp_path, "corebook", 245) == "hello"


def test_both_nbsp_variants_become_space():
    assert normalize_text("a b") == "a b"
    assert normalize_text("a b") == "a b"
