"""G1-WI: scoring de evidencia ciega CNMV (harness de join).

Une `g1-wi/blind/sample.jsonl` + `g1-wi/blind/labels.jsonl` con las
predicciones del code-under-test (`cnmv_rows.jsonl`) por `case_key`
(notice_id:record_version_id) y produce las metricas que alimentan los
gates semanticos CNMV.

Convenciones identicas a holdout-v2:
- dominios: tp/fp/fn sobre host_normalized por caso; gold =
  expected_domains (Entidad/Entidad Secundaria; emails y dominios de
  entidad legitima en Observaciones excluidos por el etiquetador).
- clones: tp/fp/fn sobre clone_detected por caso.
- safety: parser NO debe emitir target cuando el oro es irresoluble
  (expected_relation_status == "UNRESOLVED").
- `unclear` se excluye de numerador y denominador, y se reporta.
- clone_target_exact: metrica descriptiva, NO gate.
"""

DENOMINATOR_MINIMUMS = {
    "gold_domain_instances": 100,
    "gold_clone_cases": 20,
    "gold_target_resolvable_cases": 15,
    "gold_target_unresolvable_cases": 3,
}


def score_blind(rows_by_key, labels) -> dict:
    """rows_by_key: {case_key: row con domains+clone del CUT}.
    labels: lista de dicts con expected_*. Devuelve metricas."""
    labeled = [l for l in labels if l.get("labeled")]
    unclear = [l["case_key"] for l in labeled if l.get("unclear")]
    scored = [l for l in labeled if not l.get("unclear")]

    dom_tp = dom_fp = dom_fn = 0
    fp_cases, fn_cases = [], []
    cl_tp = cl_fp = cl_fn = 0
    mismatches = []

    gold_clone = resolvable = unresolvable = 0
    parser_resolved = parser_on_unresolvable = 0
    tgt_hits = tgt_misses = 0

    for l in scored:
        row = rows_by_key.get(l["case_key"])
        pred_hosts = {d["host_normalized"]
                      for d in (row.get("domains") or [])}
        gold_hosts = set(l.get("expected_domains") or [])

        tp = len(pred_hosts & gold_hosts)
        fp = pred_hosts - gold_hosts
        fn = gold_hosts - pred_hosts
        dom_tp += tp
        dom_fp += len(fp)
        dom_fn += len(fn)
        if fp:
            fp_cases.append({"case_key": l["case_key"],
                             "false": sorted(fp)})
        if fn:
            fn_cases.append({"case_key": l["case_key"],
                             "missed": sorted(fn)})

        gold_cd = bool(l.get("expected_clone_detected"))
        pred_cd = bool((row.get("clone") or {}).get("clone_detected"))
        if gold_cd and pred_cd:
            cl_tp += 1
        elif pred_cd and not gold_cd:
            cl_fp += 1
            mismatches.append({"case_key": l["case_key"], "kind": "fp"})
        elif gold_cd and not pred_cd:
            cl_fn += 1
            mismatches.append({"case_key": l["case_key"], "kind": "fn"})

        if gold_cd:
            gold_clone += 1
            if l.get("expected_relation_status") == "UNRESOLVED":
                unresolvable += 1
                if (row.get("clone") or {}).get("clone_target_raw"):
                    parser_on_unresolvable += 1
            else:
                resolvable += 1
                pred_t = (row.get("clone") or {}).get("clone_target_raw")
                if pred_t:
                    parser_resolved += 1
                    if pred_t == l.get("expected_clone_target"):
                        tgt_hits += 1
                    else:
                        tgt_misses += 1
                else:
                    tgt_misses += 1

    dom_p = dom_tp / (dom_tp + dom_fp) if dom_tp + dom_fp else 1.0
    dom_r = dom_tp / (dom_tp + dom_fn) if dom_tp + dom_fn else 1.0
    cl_p = cl_tp / (cl_tp + cl_fp) if cl_tp + cl_fp else 1.0
    cl_r = cl_tp / (cl_tp + cl_fn) if cl_tp + cl_fn else 1.0

    denominators = {
        "gold_domain_instances": dom_tp + dom_fn,
        "gold_clone_cases": gold_clone,
        "gold_target_resolvable_cases": resolvable,
        "gold_target_unresolvable_cases": unresolvable,
    }
    sufficient = {k: denominators[k] >= v
                  for k, v in DENOMINATOR_MINIMUMS.items()}

    return {
        "sample_total": len(labels),
        "labeled": len(labeled),
        "unclear_cases": unclear,
        "domains": {"precision": dom_p, "recall": dom_r,
                    "tp": dom_tp, "fp": dom_fp, "fn": dom_fn,
                    "fp_cases": fp_cases, "fn_cases": fn_cases},
        "clone_detection": {"precision": cl_p, "recall": cl_r,
                            "tp": cl_tp, "fp": cl_fp, "fn": cl_fn,
                            "mismatches": mismatches},
        "clone_target": {
            "gold_clone_cases": gold_clone,
            "gold_target_resolvable_cases": resolvable,
            "gold_target_unresolvable_cases": unresolvable,
            "parser_target_resolved_cases": parser_resolved,
            "parser_target_on_unresolvable_cases":
                parser_on_unresolvable,
            "hits": tgt_hits, "misses": tgt_misses,
        },
        "denominators": {**denominators,
                         "minimums": DENOMINATOR_MINIMUMS,
                         "sufficient": sufficient},
    }


__all__ = ["DENOMINATOR_MINIMUMS", "score_blind"]
