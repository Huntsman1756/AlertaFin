
from alertafin.textnorm import collapse_ws, normalize_name


def test_casefold_and_accents():
    assert normalize_name("MELZAPAY S.A.") == "melzapay s a"
    assert normalize_name("ÑANDÚ CAPITAL") == "nandu capital"


def test_punctuation_becomes_space_and_collapses():
    assert normalize_name("  Global   Capital,  Ltd.") == "global capital ltd"
    assert normalize_name("A&B-FINANCE") == "a b finance"


def test_idempotent():
    x = "INVERSIÓN  ONLINE, S.L."
    assert normalize_name(x) == normalize_name(normalize_name(x))


def test_collapse_ws_keeps_case():
    assert collapse_ws("  Foo   Bar  ") == "Foo Bar"
