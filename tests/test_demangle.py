from collections import Counter

from extractor.demangle import build_vocab, demangle_name, make_segmenter

# a small domain vocabulary standing in for library + book prose
VOCAB = build_vocab(
    "prosthetic cyberlimb crude generic custom clean metabolism adapsin therapy "
    "radiation tolerance neurochemical regulator high altitude adaptation matrix "
    "defense suite aluminum titanium exoframe exhalation spray strength increase "
    "enhanced movement good times chill btl toxin resistance specific " * 3
)
SEG = make_segmenter(VOCAB)


def dm(s):
    return demangle_name(s, SEG)


def test_respaces_runtogether_words():
    assert dm("Cleanm etabolism") == "Clean Metabolism"
    assert dm("AdapsinTh erapy") == "Adapsin Therapy"
    assert dm("RadiationTo lerance") == "Radiation Tolerance"
    assert dm("EnhancedMo vement") == "Enhanced Movement"


def test_preserves_punctuation_and_case():
    assert dm("ProstheticCy berlimb,Cr ude") == "Prosthetic Cyberlimb, Crude"
    assert dm("ToxinRe sistance(s pecific)") == "Toxin Resistance (Specific)"


def test_keeps_acronyms_uppercase():
    assert dm("ChillB TL") == "Chill BTL"


def test_titlecases_recovered_words():
    # mangling drops capitals; recovered names follow item-name Title Case
    out = dm("StrengthIn crease")
    assert out == "Strength Increase"
    assert out[0].isupper()


def test_clean_name_unchanged():
    assert dm("Matrix Defense Suite") == "Matrix Defense Suite"
