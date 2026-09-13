"""G1-WI evaluator — mecanica del evaluador congelado.

NO fija el veredicto: verifica la mecanica (veredicto, fingerprint,
gates estructurales sobre los artefactos congelados) y documenta los
estados esperados conocidos (domain precision FAIL por holdout-v2,
source limitation FAIL hasta que la salida lo exponga).
"""

import json
from pathlib import Path

import pytest

from alertafin.eval_g1wi import (
    HOLDOUT_V2_COMMIT,
    build_evaluation,
    cnmv_code_matches,
    compute_gates,
    verdict,
)

CNMV_ROWS = [json.loads(l) for l in
             Path("g0/normalized/notices.jsonl").open(
                 encoding="utf-8") if l.strip()]
DGSFP_ROWS = [json.loads(l) for l in
              Path("g1-wi/normalized/notices.jsonl").open(
                  encoding="utf-8") if l.strip()]
HOLDOUT = json.loads(
    Path("g0/holdout-v2/evaluation.json").read_text("utf-8"))
GOLD = json.loads(Path("g1-wi/eval/gold.json").read_text("utf-8"))


def _g(**kw):
    base = {"status": "PASS"}
    base.update(kw)
    return base


def test_verdict_fail_dominates():
    assert verdict({"a": _g(), "b": _g(status="FAIL")}) == "FAIL"
    assert verdict({"a": _g(status="INCONCLUSIVE"),
                    "b": _g(status="FAIL")}) == "FAIL"


def test_verdict_inconclusive_when_no_fail_but_unevaluable():
    assert verdict({"a": _g(), "b": _g(status="INCONCLUSIVE"),
                    "c": _g(status="N/A")}) == "INCONCLUSIVE"


def test_verdict_pass_with_na():
    """N/A != PASS pero no bloquea el veredicto."""
    assert verdict({"a": _g(), "b": _g(status="N/A")}) == "PASS"


def test_verdict_inconclusive_is_not_fail():
    assert verdict({"a": _g(status="INCONCLUSIVE")}) == "INCONCLUSIVE"


def test_cnmv_fingerprint_matches_holdout_v2():
    """Los ficheros del camino CNMV son byte-identicos a los evaluados
    en holdout-v2 -> la evidencia es reutilizable."""
    assert cnmv_code_matches(HOLDOUT_V2_COMMIT)


def test_fingerprint_mismatch_blocks_evidence_reuse():
    """Si el codigo CNMV difiere del evaluado, los gates semanticos CNMV
    quedan INCONCLUSIVE (hace falta evidencia ciega nueva)."""
    assert not cnmv_code_matches(
        HOLDOUT_V2_COMMIT, files=["README.md"])


def test_gates_structural():
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    for g in ["raw_rows_preserved", "provenance_complete",
              "determinism", "stable_idempotent_ids",
              "silent_row_loss", "false_cross_source_merges",
              "source_unavailable_semantics",
              "dgsfp_source_coverage",
              "dgsfp_source_type_preservation"]:
        assert gates[g]["status"] == "PASS", g
    assert gates["valid_source_dates_parsed"]["status"] == "PASS"


def test_domain_precision_known_fail():
    """Holdout-v2 sobre el mismo extractor: 0.9897 < 1.0 -> FAIL
    conocido, no ocultable."""
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    g = gates["domain_precision"]
    assert g["status"] == "FAIL"
    assert g["threshold"] == 1.0
    assert g["numerator"] < g["denominator"]
    assert g["failures"]


def test_domain_recall_per_source():
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    assert gates["domain_recall"]["status"] == "PASS"


def test_clone_gates():
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    assert gates["explicit_clone_precision"]["status"] == "PASS"
    assert gates["explicit_clone_recall"]["status"] == "PASS"
    ft = gates["false_emitted_clone_target"]
    assert ft["status"] == "PASS"
    assert "targets_emitted" in ft


def test_source_limitation_gate_currently_fails():
    """La salida unificada todavia no expone la limitacion DGSFP
    (DECLARED_PAGE_ONLY / population_completeness UNKNOWN)."""
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    assert gates["dgsfp_source_limitation"]["status"] == "FAIL"


def test_no_clone_target_side_door():
    """clone_target_exact / coverage siguen siendo NO GATE."""
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    assert not any(
        gid.startswith("clone_target")
        or ("clone" in gid and "coverage" in gid)
        for gid in gates)


def test_sixteen_mandatory_gates():
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    assert len(gates) == 16


def test_evaluation_schema():
    ev = build_evaluation(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    for k in ["code_under_test_commit", "evidence_fingerprints",
              "gates", "verdict"]:
        assert k in ev
    assert ev["verdict"] in {"PASS", "FAIL", "INCONCLUSIVE"}
    for g in ev["gates"].values():
        assert g["status"] in {"PASS", "FAIL", "N/A", "INCONCLUSIVE"}
        for k in ["threshold", "numerator", "denominator",
                  "evidence_source", "failures"]:
            assert k in g
