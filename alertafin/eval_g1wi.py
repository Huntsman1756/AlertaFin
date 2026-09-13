"""G1-WI evaluator — gates congelados de `g1-wi/preregistration.md`.

Dos capas:

A. STRUCTURAL / CENSUS — medidos mecanicamente sobre los artefactos
   congelados (rows normalizadas + vista unificada).
B. SEMANTIC QUALITY — CNMV reutiliza la evidencia inmutable de
   holdout-v2 SOLO si el fingerprint del camino CNMV (parser, domainex,
   clones, identity, textnorm, search) sigue siendo el del commit
   evaluado; si difiere -> INCONCLUSIVE (hace falta evidencia ciega
   nueva). DGSFP se evalua contra el censo gold congelado en
   `g1-wi/eval/gold.json`.

Estados: PASS | FAIL | N/A | INCONCLUSIVE.
N/A != PASS. INCONCLUSIVE != FAIL.
verdict: FAIL > INCONCLUSIVE > PASS.

`clone_target_exact` y coverage de target siguen siendo NO GATE.
"""

import hashlib
import json
import subprocess
from pathlib import Path

from alertafin.identity import notice_id as cnmv_notice_id
from alertafin.dgsfp import _notice_id as dgsfp_notice_id
from alertafin.unified import (
    SOURCE_ORDER,
    MultiSourceIndex,
    build_notices,
    check_multi,
)

HOLDOUT_V2_COMMIT = "ab07001b0919ac5694e034fe686f87ac27df732e"

# El evaluador se congela por TAG (un commit no puede contener su propio
# SHA). `g1-wi-evaluator-v1` apunta al commit que congela esta mecanica;
# si el evaluador cambia despues, el flag evaluator_unchanged lo delata.
EVALUATOR_TAG = "g1-wi-evaluator-v1"
EVALUATOR_FILES = ["alertafin/eval_g1wi.py", "scripts/g1wi_evaluate.py"]

CNMV_CODE_FILES = [
    "alertafin/parser.py",
    "alertafin/domainex.py",
    "alertafin/clones.py",
    "alertafin/identity.py",
    "alertafin/textnorm.py",
    "alertafin/search.py",
]

CODE_UNDER_TEST_FILES = CNMV_CODE_FILES + [
    "alertafin/dgsfp.py",
    "alertafin/unified.py",
]

_PROV_KEYS = ["source_url", "retrieved_at", "http_status",
              "source_sha256"]


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(path: str) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _sha256_at_commit(commit: str, path: str) -> str | None:
    out = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        capture_output=True,
    )
    if out.returncode != 0:
        return None
    return _sha256_bytes(out.stdout)


def cnmv_code_matches(commit: str, files: list | None = None) -> bool:
    """True si el camino CNMV actual es byte-identico al evaluado."""
    for f in (files or CNMV_CODE_FILES):
        if _sha256_at_commit(commit, f) != _sha256_file(f):
            return False
    return True


def verdict(gates: dict) -> str:
    statuses = {g["status"] for g in gates.values()}
    if "FAIL" in statuses:
        return "FAIL"
    if "INCONCLUSIVE" in statuses:
        return "INCONCLUSIVE"
    return "PASS"


def _gate(status, threshold, numerator=None, denominator=None,
          evidence_source=None, failures=None, **extra):
    g = {
        "status": status,
        "threshold": threshold,
        "numerator": numerator,
        "denominator": denominator,
        "evidence_source": evidence_source,
        "failures": failures or [],
    }
    g.update(extra)
    return g


def _s(n: float) -> str:
    return f"{n:.4f}"


def compute_gates(cnmv_rows, dgsfp_rows, holdout, gold) -> dict:
    """Los 16 gates obligatorios sobre los artefactos congelados."""
    gates = {}
    rows = list(cnmv_rows) + list(dgsfp_rows)
    notices = build_notices(rows)
    all_occ = [o for n in notices for o in n["source_occurrences"]]

    # ---------- A. STRUCTURAL / CENSUS ----------

    n_occ = len(all_occ)
    gates["raw_rows_preserved"] = _gate(
        "PASS" if n_occ == len(rows) else "FAIL",
        f"{len(rows)} ocurrencias", n_occ, len(rows),
        "census: warning_notices vs rows",
        [] if n_occ == len(rows) else
        [f"ocurrencias {n_occ} != filas {len(rows)}"])

    prov_ok = sum(1 for o in all_occ
                  if all(o.get("provenance", {}).get(k)
                         for k in _PROV_KEYS))
    gates["provenance_complete"] = _gate(
        "PASS" if prov_ok == n_occ else "FAIL",
        "100%", prov_ok, n_occ,
        "census: provenance por ocurrencia",
        [] if prov_ok == n_occ else
        [f"{n_occ - prov_ok} ocurrencias sin provenance completa"])

    valid = sum(1 for r in cnmv_rows if r.get("fecha"))
    with_fecha_raw = sum(1 for r in cnmv_rows if r.get("fecha_raw"))
    gates["valid_source_dates_parsed"] = _gate(
        "PASS" if valid == with_fecha_raw else "FAIL",
        "100% donde aplica (DGSFP: N/A estructural)",
        valid, with_fecha_raw,
        "CNMV census; DGSFP sin fechas por registro",
        [] if valid == with_fecha_raw else
        [f"{with_fecha_raw - valid} fecha_raw no parseadas"])

    canon = lambda ns: json.dumps(ns, ensure_ascii=False,
                                  sort_keys=True)
    det = canon(notices) == canon(build_notices(rows))
    gates["determinism"] = _gate(
        "PASS" if det else "FAIL", "identical inputs -> identical output",
        1 if det else 0, 1, "build_notices x2 byte-identico")

    recompute_ok = 0
    for r in rows:
        if r["source_namespace"].startswith("cnmv."):
            ok = cnmv_notice_id(r) == r["notice_id"]
        else:
            ok = dgsfp_notice_id(r) == r["notice_id"]
        recompute_ok += ok
    gates["stable_idempotent_ids"] = _gate(
        "PASS" if recompute_ok == len(rows) else "FAIL",
        "100% notice_id recomputable",
        recompute_ok, len(rows), "re-hash de identity_fields")

    lost = len(rows) - n_occ
    gates["silent_row_loss"] = _gate(
        "PASS" if lost == 0 else "FAIL", "0",
        lost, 0, "rows vs ocurrencias",
        [] if lost == 0 else [f"{lost} filas sin ocurrencia"])

    merged = [n["notice_id"] for n in notices
              if len({o["source_namespace"]
                      for o in n["source_occurrences"]}) > 1]
    gates["false_cross_source_merges"] = _gate(
        "PASS" if not merged else "FAIL", "0",
        len(merged), 0, "namespaces por notice",
        merged)

    idx_partial = MultiSourceIndex.build(
        [n for n in notices if n["source"] == "CNMV"])
    r_un = check_multi("dominio-inexistente-zzzz.com", idx_partial)
    su_ok = (r_un.status == "SOURCE_UNAVAILABLE"
             and r_un.source_status.get("DGSFP_UNAUTHORISED")
             == "SOURCE_UNAVAILABLE"
             and r_un.source_status.get("DGSFP_FRAUDULENT_WEBS")
             == "SOURCE_UNAVAILABLE")
    gates["source_unavailable_semantics"] = _gate(
        "PASS" if su_ok else "FAIL", "100%",
        1 if su_ok else 0, 1,
        "check_multi con fuentes ausentes -> SOURCE_UNAVAILABLE",
        [] if su_ok else ["SOURCE_UNAVAILABLE no propagado"])

    # ---------- B. SEMANTIC QUALITY ----------

    evidence_ok = cnmv_code_matches(HOLDOUT_V2_COMMIT)
    cnmv_ev = ("holdout-v2 evaluation.json "
               f"(code {HOLDOUT_V2_COMMIT[:7]}, fingerprint match)"
               if evidence_ok else
               "code drift vs holdout-v2: evidencia no reutilizable")

    d_hold = holdout["domains"]
    c_hold = holdout["clone_detection"]
    t_hold = holdout["clone_target"]

    gold_pag = gold["sources"]["dgsfp.paginas_web_fraudulentas"]
    gold_suj = gold["sources"]["dgsfp.sujetos_no_autorizados"]
    pag_notices = [n for n in notices
                   if n["source"] == "DGSFP_FRAUDULENT_WEBS"]
    emitted_pag = [a["host_normalized"] for n in pag_notices
                   for a in n["domain_assertions"]]
    gold_set = set(gold_pag["gold_domains"])
    emitted_set = set(emitted_pag)
    dgsfp_fp = sorted(emitted_set - gold_set)
    dgsfp_fn = sorted(gold_set - emitted_set)

    dgsfp_emitted_targets = sum(
        len(n["clone_evidence"]) for n in notices
        if n["source"].startswith("DGSFP"))

    if evidence_ok:
        dom_tp = d_hold["tp"] + len(emitted_set & gold_set)
        dom_denom = (d_hold["tp"] + d_hold["fp"]) + len(emitted_set)
        dom_prec = dom_tp / dom_denom if dom_denom else 1.0
        gates["domain_precision"] = _gate(
            "PASS" if dom_prec >= 1.0 else "FAIL",
            1.0, dom_tp, dom_denom, cnmv_ev + " + censo DGSFP",
            [f"CNMV holdout-v2 fp: {[c['false'] for c in d_hold['fp_cases']]}"]
            + [f"DGSFP fp: {dgsfp_fp}"] if (d_hold["fp"] or dgsfp_fp)
            else [],
            observed=_s(dom_prec))
    else:
        gates["domain_precision"] = _gate(
            "INCONCLUSIVE", 1.0, None, None, cnmv_ev,
            ["evidencia CNMV no reutilizable: se requiere nueva "
             "auditoria ciega"])

    if evidence_ok:
        cnmv_rec = d_hold["recall"]
        pag_rec = (len(emitted_set & gold_set) / len(gold_set)
                   if gold_set else None)
        ok = cnmv_rec >= 0.95 and (pag_rec is None or pag_rec >= 0.95)
        gates["domain_recall"] = _gate(
            "PASS" if ok else "FAIL", ">=0.95 por fuente",
            d_hold["tp"] + (len(emitted_set & gold_set)),
            d_hold["tp"] + d_hold["fn"] + len(gold_set),
            cnmv_ev + " + censo DGSFP",
            [f"CNMV recall {_s(cnmv_rec)}",
             f"DGSFP_PAGINAS recall {_s(pag_rec)}" if pag_rec is not None
             else "DGSFP_PAGINAS N/A",
             "DGSFP_SUJETOS N/A (0 dominios gold)"])
    else:
        gates["domain_recall"] = _gate(
            "INCONCLUSIVE", ">=0.95 por fuente", None, None, cnmv_ev)

    if evidence_ok:
        gates["explicit_clone_precision"] = _gate(
            "PASS" if c_hold["precision"] >= 1.0 else "FAIL",
            1.0, c_hold["tp"], c_hold["tp"] + c_hold["fp"],
            cnmv_ev + "; DGSFP 0 emitidos (N/A)",
            [f"precision {_s(c_hold['precision'])}"])
        gates["explicit_clone_recall"] = _gate(
            "PASS" if c_hold["recall"] >= 0.95 else "FAIL",
            ">=0.95 por fuente", c_hold["tp"],
            c_hold["tp"] + c_hold["fn"],
            cnmv_ev + "; DGSFP N/A (0 positivos gold, errata)",
            [f"CNMV recall {_s(c_hold['recall'])}",
             "DGSFP_SUJETOS N/A", "DGSFP_PAGINAS N/A"])
        gates["false_emitted_clone_target"] = _gate(
            "PASS" if (t_hold["parser_target_on_unresolvable_cases"] == 0
                       and dgsfp_emitted_targets == 0) else "FAIL",
            0, t_hold["parser_target_on_unresolvable_cases"]
            + dgsfp_emitted_targets, 0,
            cnmv_ev + " + censo DGSFP (safety gate)",
            [],
            targets_emitted=t_hold["parser_target_resolved_cases"]
            + dgsfp_emitted_targets)
    else:
        for gid in ["explicit_clone_precision", "explicit_clone_recall",
                    "false_emitted_clone_target"]:
            gates[gid] = _gate("INCONCLUSIVE", None, None, None, cnmv_ev)

    # ---------- DGSFP-specific ----------

    suj_notices = [n for n in notices if n["source"] ==
                   "DGSFP_UNAUTHORISED"]
    suj_occ = sum(len(n["source_occurrences"]) for n in suj_notices)
    pag_occ = sum(len(n["source_occurrences"]) for n in pag_notices)
    cov_ok = (suj_occ == gold_suj["occurrences"]
              and pag_occ == gold_pag["occurrences"])
    gates["dgsfp_source_coverage"] = _gate(
        "PASS" if cov_ok else "FAIL",
        f"{gold_suj['occurrences']}+{gold_pag['occurrences']}",
        suj_occ + pag_occ,
        gold_suj["occurrences"] + gold_pag["occurrences"],
        "censo gold vs ocurrencias",
        [] if cov_ok else
        [f"sujetos {suj_occ}/{gold_suj['occurrences']}, "
         f"paginas {pag_occ}/{gold_pag['occurrences']}"])

    types = {}
    for n in notices:
        types.setdefault(n["source_namespace"], set()).add(
            n["source_type"])
    st_ok = (len(types.get("dgsfp.sujetos_no_autorizados", set())) == 1
             and len(types.get("dgsfp.paginas_web_fraudulentas",
                              set())) == 1
             and types["dgsfp.sujetos_no_autorizados"]
             != types["dgsfp.paginas_web_fraudulentas"])
    gates["dgsfp_source_type_preservation"] = _gate(
        "PASS" if st_ok else "FAIL", "tipos distintos por fuente",
        1 if st_ok else 0, 1, "source_type por namespace",
        [] if st_ok else ["source_type colapsado entre fuentes"])

    lim_fields = all(
        n.get("source_limitation") for n in notices
        if n["source"].startswith("DGSFP"))
    lim_result = hasattr(
        check_multi("x", MultiSourceIndex.build(notices)),
        "source_limitations")
    lim_ok = lim_fields and lim_result
    gates["dgsfp_source_limitation"] = _gate(
        "PASS" if lim_ok else "FAIL",
        "salida + docs preservan no-exhaustividad",
        int(lim_fields) + int(lim_result), 2,
        "contrato DGSFP-G1.3",
        [] if lim_ok else [
            "notices DGSFP sin source_limitation"
            if not lim_fields else None,
            "MultiCheckResult no expone limitacion "
            "(DECLARED_PAGE_ONLY / population_completeness UNKNOWN)"
            if not lim_result else None])

    return gates


def _git(*args) -> str:
    return subprocess.run(["git", *args],
                          capture_output=True, text=True).stdout.strip()


def build_evaluation(cnmv_rows, dgsfp_rows, holdout, gold) -> dict:
    head = _git("rev-parse", "HEAD")
    eval_commit = _git("rev-parse", f"{EVALUATOR_TAG}^{{commit}}") or None
    gates = compute_gates(cnmv_rows, dgsfp_rows, holdout, gold)
    return {
        "evaluation": "g1-wi",
        # codigo evaluado = checkout sobre el que corre esta evaluacion
        "code_under_test_commit": head,
        # mecanica del evaluador, congelada por tag — distinto de CUT
        "evaluator_freeze_commit": eval_commit,
        "evaluator_unchanged": (
            eval_commit is not None and all(
                _sha256_at_commit(eval_commit, f) == _sha256_file(f)
                for f in EVALUATOR_FILES)),
        "code_under_test_sha256": {
            f: _sha256_file(f) for f in CODE_UNDER_TEST_FILES},
        "evidence_fingerprints": {
            "cnmv_holdout_v2_evaluation_sha256":
                _sha256_file("g0/holdout-v2/evaluation.json"),
            "cnmv_code_commit_evaluated": HOLDOUT_V2_COMMIT,
            "cnmv_code_matches_current":
                cnmv_code_matches(HOLDOUT_V2_COMMIT),
            "dgsfp_gold_sha256": _sha256_file("g1-wi/eval/gold.json"),
            "dgsfp_snapshot_sha256":
                _sha256_file("g1-wi/probe/snapshot.json"),
        },
        "gates": gates,
        "verdict": verdict(gates),
    }


__all__ = [
    "HOLDOUT_V2_COMMIT", "CNMV_CODE_FILES",
    "cnmv_code_matches", "compute_gates", "build_evaluation",
    "verdict",
]
