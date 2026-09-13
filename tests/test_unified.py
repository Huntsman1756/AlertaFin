"""G1-WI.C: modelo unificado multifuente.

WarningNotice = notice_id semantico + source_occurrences[1..N].
domains/clone -> domain_assertions[] / clone_evidence[]
provenance-backed. Cobertura sobre ocurrencias.
"""

import json
from pathlib import Path

import pytest

from alertafin.unified import (
    MultiSourceIndex,
    aggregate_status,
    build_notices,
    check_multi,
)

CNMV_ROWS = [json.loads(l) for l in
             Path("g1-wi/normalized/cnmv_rows.jsonl").open(
                 encoding="utf-8") if l.strip()]
DGSFP_ROWS = [json.loads(l) for l in
              Path("g1-wi/normalized/notices.jsonl").open(
                  encoding="utf-8") if l.strip()]
NOTICES = build_notices(CNMV_ROWS + DGSFP_ROWS)


def _by_source(notices, source):
    return [n for n in notices if n["source"] == source]


def test_notice_occurrence_counts():
    assert len(_by_source(NOTICES, "CNMV")) == 10361
    assert len(_by_source(NOTICES, "DGSFP_UNAUTHORISED")) == 87
    assert len(_by_source(NOTICES, "DGSFP_FRAUDULENT_WEBS")) == 10
    total_occ = sum(len(n["source_occurrences"]) for n in NOTICES)
    assert total_occ == 10368 + 97 + 10


def test_cnmv_seven_multi_occurrence_groups():
    multi = [n for n in _by_source(NOTICES, "CNMV")
             if len(n["source_occurrences"]) > 1]
    assert len(multi) == 7
    assert all(len(n["source_occurrences"]) == 2 for n in multi)
    # 5 byte-identicos (mismo rvid), 2 versionados (rvid distinto)
    same_rvid = sum(1 for n in multi if len(
        {o["record_version_id"] for o in n["source_occurrences"]}) == 1)
    assert same_rvid == 5


def test_occurrence_ids_unique_and_raw_preserved():
    all_occ = [o for n in NOTICES for o in n["source_occurrences"]]
    assert len({o["source_occurrence_id"] for o in all_occ}) == 10475
    assert all(o.get("raw_row_bytes_hex") for o in all_occ)
    assert all(o.get("provenance", {}).get("source_sha256")
               for o in all_occ)


def test_tolot_two_clone_targets_preserved():
    tolot = [n for n in _by_source(NOTICES, "CNMV")
             if "TOLOT-EPARGNE" in (n["entidad_raw"] or "")]
    assert len(tolot) == 1
    ev = tolot[0]["clone_evidence"]
    assert len(ev) == 2
    targets = {e["clone_target_raw"] for e in ev}
    assert len(targets) == 2
    assert any("AccorInvest" in t for t in targets)
    assert any("Vontobel" in t for t in targets)
    assert all(e["relation_status"] == "EXPLICIT_SOURCE" for e in ev)
    occ_ids = {o["source_occurrence_id"]
               for o in tolot[0]["source_occurrences"]}
    assert {e["source_occurrence_id"] for e in ev} == occ_ids


def test_dgsfp_milton_one_notice_two_occurrences():
    milton = [n for n in _by_source(NOTICES, "DGSFP_UNAUTHORISED")
              if n["entidad_raw"] == "MILTON GROUP"]
    assert len(milton) == 1
    occs = milton[0]["source_occurrences"]
    assert len(occs) == 2
    assert len({o["source_occurrence_id"] for o in occs}) == 2
    assert len({o["record_version_id"] for o in occs}) == 1


def test_domain_assertions_provenance_backed():
    for n in NOTICES:
        occ_ids = {o["source_occurrence_id"]
                   for o in n["source_occurrences"]}
        for a in n["domain_assertions"]:
            assert a["source_occurrence_id"] in occ_ids
            assert a["host_normalized"]


def test_no_clone_scalar_at_notice_level():
    assert all("clone" not in n and "domains" not in n for n in NOTICES)


def test_determinism_identical_inputs():
    again = build_notices(CNMV_ROWS + DGSFP_ROWS)
    assert json.dumps(NOTICES, ensure_ascii=False, sort_keys=True) == \
           json.dumps(again, ensure_ascii=False, sort_keys=True)


def test_aggregate_status_truth_table():
    assert aggregate_status(
        {"CNMV": "WARNED", "DGSFP_UNAUTHORISED": "NO_WARNING_FOUND",
         "DGSFP_FRAUDULENT_WEBS": "NO_WARNING_FOUND"}) == ("WARNED", True)
    assert aggregate_status(
        {"CNMV": "WARNED", "DGSFP_UNAUTHORISED": "SOURCE_UNAVAILABLE",
         "DGSFP_FRAUDULENT_WEBS": "NO_WARNING_FOUND"}) == ("WARNED", False)
    assert aggregate_status(
        {"CNMV": "NO_WARNING_FOUND",
         "DGSFP_UNAUTHORISED": "SOURCE_UNAVAILABLE",
         "DGSFP_FRAUDULENT_WEBS": "NO_WARNING_FOUND"}
    ) == ("SOURCE_UNAVAILABLE", False)
    assert aggregate_status(
        {"CNMV": "AMBIGUOUS", "DGSFP_UNAUTHORISED": "NO_WARNING_FOUND",
         "DGSFP_FRAUDULENT_WEBS": "NO_WARNING_FOUND"}
    ) == ("AMBIGUOUS", True)
    assert aggregate_status(
        {"CNMV": "NO_WARNING_FOUND",
         "DGSFP_UNAUTHORISED": "NO_WARNING_FOUND",
         "DGSFP_FRAUDULENT_WEBS": "NO_WARNING_FOUND"}
    ) == ("NO_WARNING_FOUND", True)
    # WARNED gana a AMBIGUOUS/SOURCE_UNAVAILABLE
    assert aggregate_status(
        {"CNMV": "AMBIGUOUS", "DGSFP_UNAUTHORISED": "WARNED",
         "DGSFP_FRAUDULENT_WEBS": "SOURCE_UNAVAILABLE"}
    ) == ("WARNED", False)


def test_check_multi_cnmv_domain():
    index = MultiSourceIndex.build(NOTICES)
    res = check_multi("www.melzapay.com", index)
    assert res.status == "WARNED"
    assert res.coverage_complete is True
    assert res.source_status["CNMV"] == "WARNED"
    assert res.source_status["DGSFP_UNAUTHORISED"] == "NO_WARNING_FOUND"
    assert any(n["source"] == "CNMV" for n in res.notices)


def test_check_multi_dgsfp_domain():
    index = MultiSourceIndex.build(NOTICES)
    res = check_multi("sin-cargos.credito-expres.com", index)
    assert res.status == "WARNED"
    assert res.source_status["DGSFP_FRAUDULENT_WEBS"] == "WARNED"
    hit = [n for n in res.notices
           if n["source"] == "DGSFP_FRAUDULENT_WEBS"]
    assert len(hit) == 1


def test_check_multi_no_warning():
    index = MultiSourceIndex.build(NOTICES)
    res = check_multi("dominio-inexistente-xyz.com", index)
    assert res.status == "NO_WARNING_FOUND"
    assert res.coverage_complete is True


def test_check_multi_ambiguous_real_name():
    index = MultiSourceIndex.build(NOTICES)
    res = check_multi("core invest", index)
    assert res.status == "AMBIGUOUS"
    assert res.source_status["CNMV"] == "AMBIGUOUS"


def test_check_multi_source_unavailable():
    index = MultiSourceIndex.build(_by_source(NOTICES, "CNMV"))
    res = check_multi("www.melzapay.com", index)
    assert res.status == "WARNED"
    assert res.coverage_complete is False
    res2 = check_multi("dominio-inexistente-xyz.com", index)
    assert res2.status == "SOURCE_UNAVAILABLE"
    assert res2.source_status["DGSFP_UNAUTHORISED"] == "SOURCE_UNAVAILABLE"


def test_dgsfp_duplicate_dedup_in_search():
    """MILTON GROUP aparece 2 veces en fuente pero es 1 notice."""
    index = MultiSourceIndex.build(NOTICES)
    res = check_multi("milton group", index)
    assert res.status == "WARNED"
    milton = [n for n in res.notices if n["entidad_raw"] == "MILTON GROUP"]
    assert len(milton) == 1
    assert len(milton[0]["source_occurrences"]) == 2


# --- G1-WI-R1.B: limitacion DGSFP en la salida ---

def test_dgsfp_notices_carry_source_limitation():
    for n in NOTICES:
        if not n["source"].startswith("DGSFP"):
            continue
        lim = n.get("source_limitation")
        assert lim, n["notice_id"]
        assert lim["population_scope"] == "DECLARED_PAGE_ONLY"
        assert lim["population_completeness_beyond_page"] == "UNKNOWN"


def test_unauthorised_preserves_official_disclaimer():
    n = next(n for n in NOTICES if n["source"] == "DGSFP_UNAUTHORISED")
    assert "no es exhaustiva" in n["source_limitation"]["declaration_raw"]


def test_check_result_exposes_source_limitations():
    index = MultiSourceIndex.build(NOTICES)
    res = check_multi("dominio-inexistente-xyz.com", index)
    lims = res.source_limitations
    assert "DGSFP_UNAUTHORISED" in lims
    assert "DGSFP_FRAUDULENT_WEBS" in lims
    assert lims["DGSFP_FRAUDULENT_WEBS"]["population_scope"] == \
        "DECLARED_PAGE_ONLY"
