"""G1-WI blind evidence — harness de join y wiring en el evaluador.

Tests sobre fixtures sinteticos: NO computan las etiquetas reales de
`g1-wi/blind/labels.jsonl` (eso es el run final autorizado)."""

import json
from pathlib import Path

from alertafin.blind_eval import DENOMINATOR_MINIMUMS, score_blind
from alertafin.eval_g1wi import build_evaluation, compute_gates

CNMV_ROWS = [json.loads(line) for line in
             Path("g1-wi/normalized/cnmv_rows.jsonl")
             .read_text(encoding="utf-8").splitlines() if line.strip()]
DGSFP_ROWS = [json.loads(line) for line in
              Path("g1-wi/normalized/notices.jsonl")
              .read_text(encoding="utf-8").splitlines() if line.strip()]
HOLDOUT = json.loads(
    Path("g0/holdout-v2/evaluation.json").read_text("utf-8"))
GOLD = json.loads(Path("g1-wi/eval/gold.json").read_text("utf-8"))


def _row(domains=None, clone=False, target=None):
    return {
        "domains": [{"host_normalized": d} for d in (domains or [])],
        "clone": {"clone_detected": clone, "clone_target_raw": target},
    }


def _label(key, domains=None, clone=False, target=None,
           status="EXPLICIT_SOURCE", unclear=False, labeled=True):
    return {
        "case_key": key, "labeled": labeled, "unclear": unclear,
        "expected_domains": domains or [],
        "expected_clone_detected": clone,
        "expected_clone_target": target,
        "expected_relation_status": status if clone else None,
    }


def test_score_blind_domain_arithmetic():
    rows = {
        "k1": _row(["a.com", "b.com"]),      # gold a.com -> fp b.com
        "k2": _row(["c.com"]),               # gold c.com d.com -> fn
        "k3": _row([]),                      # gold [] -> limpio
    }
    labels = [
        _label("k1", ["a.com"]),
        _label("k2", ["c.com", "d.com"]),
        _label("k3"),
    ]
    m = score_blind(rows, labels)
    assert (m["domains"]["tp"], m["domains"]["fp"],
            m["domains"]["fn"]) == (2, 1, 1)
    assert m["domains"]["fp_cases"][0]["false"] == ["b.com"]
    assert m["domains"]["fn_cases"][0]["missed"] == ["d.com"]
    assert m["denominators"]["gold_domain_instances"] == 3


def test_score_blind_clone_and_safety():
    rows = {
        "k1": _row(clone=True, target="ACME S.A."),   # gold clone, hit
        "k2": _row(clone=False),                      # gold clone -> fn
        "k3": _row(clone=True, target="X"),           # gold none -> fp
        "k4": _row(clone=True, target="X"),           # UNRESOLVED + target
    }
    labels = [
        _label("k1", clone=True, target="ACME S.A."),
        _label("k2", clone=True, target="BANK S.A."),
        _label("k3"),
        _label("k4", clone=True, status="UNRESOLVED"),
    ]
    m = score_blind(rows, labels)
    assert (m["clone_detection"]["tp"], m["clone_detection"]["fp"],
            m["clone_detection"]["fn"]) == (2, 1, 1)
    t = m["clone_target"]
    assert t["gold_clone_cases"] == 3
    assert t["gold_target_resolvable_cases"] == 2
    assert t["gold_target_unresolvable_cases"] == 1
    assert t["parser_target_on_unresolvable_cases"] == 1  # safety hit
    assert t["hits"] == 1 and t["misses"] == 1


def test_score_blind_unclear_excluded():
    rows = {"k1": _row(["a.com"]), "k2": _row(["b.com"])}
    labels = [_label("k1", ["a.com"]),
              _label("k2", ["b.com"], unclear=True)]
    m = score_blind(rows, labels)
    assert m["unclear_cases"] == ["k2"]
    assert m["domains"]["tp"] == 1  # k2 fuera de numerador/denominador
    assert m["denominators"]["gold_domain_instances"] == 1


def test_score_blind_denominator_flags():
    assert DENOMINATOR_MINIMUMS["gold_domain_instances"] == 100
    m = score_blind({"k1": _row(["a.com"])}, [_label("k1", ["a.com"])])
    assert m["denominators"]["sufficient"]["gold_domain_instances"] \
        is False


def _blind_metrics(**over):
    base = {
        "sample_total": 300, "labeled": 300, "unclear_cases": [],
        "domains": {"precision": 1.0, "recall": 1.0, "tp": 300,
                    "fp": 0, "fn": 0, "fp_cases": [], "fn_cases": []},
        "clone_detection": {"precision": 1.0, "recall": 1.0,
                            "tp": 20, "fp": 0, "fn": 0,
                            "mismatches": []},
        "clone_target": {"gold_clone_cases": 20,
                         "gold_target_resolvable_cases": 17,
                         "gold_target_unresolvable_cases": 3,
                         "parser_target_resolved_cases": 17,
                         "parser_target_on_unresolvable_cases": 0,
                         "hits": 17, "misses": 0},
        "denominators": {
            "gold_domain_instances": 300, "gold_clone_cases": 20,
            "gold_target_resolvable_cases": 17,
            "gold_target_unresolvable_cases": 3,
            "minimums": DENOMINATOR_MINIMUMS,
            "sufficient": {"gold_domain_instances": True,
                           "gold_clone_cases": True,
                           "gold_target_resolvable_cases": True,
                           "gold_target_unresolvable_cases": True}},
    }
    base.update(over)
    return base


def test_blind_evidence_feeds_semantic_gates():
    """Con evidencia ciega nueva los gates semanticos CNMV se evaluan
    (ya no INCONCLUSIVE), con evidence_source documentado."""
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD,
                          cnmv_blind=_blind_metrics())
    for gid in ["domain_precision", "domain_recall",
                "explicit_clone_precision", "explicit_clone_recall",
                "false_emitted_clone_target"]:
        assert gates[gid]["status"] == "PASS", gid
        assert "blind" in gates[gid]["evidence_source"]


def test_blind_fp_fails_domain_precision():
    blind = _blind_metrics()
    blind["domains"] = {**blind["domains"], "fp": 2,
                        "precision": 300 / 302,
                        "fp_cases": [{"case_key": "x",
                                      "false": ["y.com"]}]}
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD,
                          cnmv_blind=blind)
    assert gates["domain_precision"]["status"] == "FAIL"


def test_blind_insufficient_clone_denominator_inconclusive():
    blind = _blind_metrics()
    blind["denominators"]["sufficient"]["gold_clone_cases"] = False
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD,
                          cnmv_blind=blind)
    assert gates["explicit_clone_precision"]["status"] == "INCONCLUSIVE"
    assert gates["explicit_clone_recall"]["status"] == "INCONCLUSIVE"
    # dominios siguen evaluados: la insuficiencia es por gate
    assert gates["domain_precision"]["status"] == "PASS"


def test_blind_target_on_unresolvable_fails_safety():
    blind = _blind_metrics()
    blind["clone_target"]["parser_target_on_unresolvable_cases"] = 1
    gates = compute_gates(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD,
                          cnmv_blind=blind)
    assert gates["false_emitted_clone_target"]["status"] == "FAIL"


def test_blind_fingerprints_in_evaluation():
    ev = build_evaluation(CNMV_ROWS, DGSFP_ROWS, HOLDOUT, GOLD,
                          cnmv_blind=_blind_metrics())
    fp = ev["evidence_fingerprints"]
    assert fp["cnmv_blind_evidence_used"] is True
    assert fp["cnmv_blind_sample_sha256"]
    assert fp["cnmv_blind_labels_sha256"] == (
        "0191ed4fe9161210daf3a0a6668baf31f92e0ac90828302fa85f818e90169d3b")
