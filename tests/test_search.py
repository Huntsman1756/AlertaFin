import pytest

from alertafin.search import SearchIndex, check


def mk_notice(id_, entidad, entidad_sec=None, domain=None):
    n = {
        "notice_id": id_,
        "entidad_raw": entidad,
        "entidad_secundaria_raw": entidad_sec,
        "observaciones_raw": None,
        "provenance": {},
    }
    if domain:
        n["domains"] = [{"raw": domain, "host_normalized": domain.lower()}]
    return n


@pytest.fixture
def index():
    notices = [
        mk_notice("n1", "MELZAPAY S.A.", domain="www.melzapay.com"),
        mk_notice("n2", "GLOBAL CAPITAL"),
        mk_notice("n3", "Global  Capital"),
        mk_notice("n4", "GLOBAL CAPITAL LTD"),
        mk_notice("n5", "Otra Entidad SL"),
        mk_notice("n6", "GLOBAL CAPITAL"),  # mismo sujeto, segunda advertencia
    ]
    return SearchIndex.build(notices)


def test_exact_domain_match_warned(index):
    res = check("WWW.MELZAPAY.COM", index)
    assert res.status == "WARNED"
    assert [n["notice_id"] for n in res.notices] == ["n1"]


def test_domain_and_host_are_distinct_facts(index):
    res = check("melzapay.com", index)
    assert res.status == "NO_WARNING_FOUND"


def test_exact_normalized_name_single_subject(index):
    res = check("melzapay s.a.", index)
    assert res.status == "WARNED"
    assert res.notices[0]["notice_id"] == "n1"


def test_same_subject_multiple_notices_warned_with_list(index):
    res = check("global capital", index)
    assert res.status == "WARNED"
    assert [n["notice_id"] for n in res.notices] == ["n2", "n3", "n6"]


def test_ambiguous_name_multiple_subjects(index):
    # 'GLOBAL CAPITAL' y 'Global  Capital' colapsan al mismo nombre normalizado
    # pero aqui creamos dos sujetos realmente distintos:
    idx = SearchIndex.build([
        mk_notice("a1", "GLOBAL CAPITAL"),
        mk_notice("a2", "Global-Capital"),  # puntuacion distinta -> otro sujeto
    ])
    res = check("global capital", idx)
    assert res.status == "AMBIGUOUS"
    assert len(res.subjects) == 2


def test_partial_fuzzy_never_warned(index):
    res = check("global", index)
    assert res.status == "NO_WARNING_FOUND"
    res2 = check("melzapay", index)
    assert res2.status == "NO_WARNING_FOUND"


def test_no_warning_found(index):
    res = check("Entidad Inexistente Imaginaria", index)
    assert res.status == "NO_WARNING_FOUND"
    assert res.notices == []


def test_source_unavailable():
    res = check("whatever", None)
    assert res.status == "SOURCE_UNAVAILABLE"


def test_numeric_token_is_name_query_not_domain(index):
    res = check("1.2.3", index)
    assert res.status == "NO_WARNING_FOUND"
