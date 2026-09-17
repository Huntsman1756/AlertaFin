"""G1-WI evaluator — mecanica del evaluador congelado.

NO fija el veredicto: verifica la mecanica (veredicto, fingerprint,
gates estructurales sobre los artefactos congelados) y documenta los
estados esperados conocidos (domain precision FAIL por holdout-v2,
source limitation FAIL hasta que la salida lo exponga).
"""

import json
from pathlib import Path

from alertafin.eval_g1wi import (
    HOLDOUT_V2_COMMIT,
    build_evaluation,
    cnmv_code_matches,
    compute_gates,
    verdict,
)

CNMV_ROWS = [json.loads(line) for line in
             Path("g1-wi/normalized/cnmv_rows.jsonl")
             .read_text(encoding="utf-8").splitlines() if line.strip()]
DGSFP_ROWS = [json.loads(line) for line in
              Path("g1-wi/normalized/notices.jsonl")
              .read_text(encoding="utf-8").splitlines() if line.strip()]
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


def test_cnmv_fingerprint_no_longer_matches_after_r1():
    """Tras la remediacion R1 de domainex, holdout-v2 ya no puede
    decidir los gates semanticos CNMV: se requiere evidencia ciega
    nueva (sampler G1-WI)."""
    assert not cnmv_code_matches(HOLDOUT_V2_COMMIT)


def test_holdout_reuse_when_fingerprint_matches(monkeypatch):
    """Si el fingerprint coincidiera, la evidencia holdout-v2 si se
    usaria para los gates semanticos CNMV."""
    monkeypatch.setattr(
        "alertafin.eval_g1wi.cnmv_code_matches", lambda *a, **k: True)
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    g = gates["domain_precision"]
    assert g["status"] == "FAIL"          # 0.9897 < 1.0, FP conocidos
    assert g["numerator"] < g["denominator"]
    assert "holdout-v2" in g["evidence_source"]


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


def test_semantic_cnmv_inconclusive_until_new_evidence():
    """Sin fingerprint match los gates semanticos (que cubren CNMV)
    quedan INCONCLUSIVE hasta la nueva evidencia ciega."""
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    for gid in ["domain_precision", "domain_recall",
                "explicit_clone_precision", "explicit_clone_recall",
                "false_emitted_clone_target"]:
        assert gates[gid]["status"] == "INCONCLUSIVE", gid


def test_source_limitation_gate():
    """Tras R1.B la salida expone la limitacion DGSFP
    (DECLARED_PAGE_ONLY / population_completeness UNKNOWN)."""
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD)
    assert gates["dgsfp_source_limitation"]["status"] == "PASS"


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
    for k in ["code_under_test_commit", "evaluator_freeze_commit",
              "evaluator_unchanged", "code_under_test_sha256",
              "evidence_fingerprints", "gates", "verdict"]:
        assert k in ev
    # CUT = HEAD del checkout evaluado; freeze del evaluador es un
    # commit distinto resuelto por tag (None si el tag aun no existe)
    assert ev["code_under_test_commit"]
    assert ev["evaluator_freeze_commit"] != ev["code_under_test_commit"] \
        or ev["evaluator_freeze_commit"] is None
    for f in ["alertafin/dgsfp.py", "alertafin/unified.py",
              "alertafin/domainex.py"]:
        assert f in ev["code_under_test_sha256"]
    assert ev["verdict"] in {"PASS", "FAIL", "INCONCLUSIVE"}
    for g in ev["gates"].values():
        assert g["status"] in {"PASS", "FAIL", "N/A", "INCONCLUSIVE"}
        for k in ["threshold", "numerator", "denominator",
                  "evidence_source", "failures"]:
            assert k in g
