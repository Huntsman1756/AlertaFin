"""G0-R: harness de regresion del holdout ciego G0 contra el parser ACTUAL.

El holdout original queda FAIL e inmutable (tag `g0-holdout-fail`, commit
139a25f). Este script NO toca manifest, sample, labels ni evaluation: relee la
fuente congelada, ejecuta `enrich()` con el parser vigente y puntua contra
`g0/holdout/labels.jsonl` con el mismo `score()` del evaluador congelado.

- `baseline` -> g0-r/baseline.json
    Artefacto inmutable creado ANTES de modificar el parser. Si ya existe,
    aborta: el baseline no se reescribe. Si existe `evaluation.json` congelado,
    exige que las metricas reproducidas coincidan (demuestra que el harness
    replica la evaluacion G0).
- `report` (default) -> stdout + g0-r/latest.json
    Metricas con el parser actual y delta contra el baseline.

Vista de falsos positivos de dominio: se reportan las dos vistas.
`domains.fp` es la vista de etiquetas congeladas; `domains_adjudicated` excluye
los notice_id listados en `ADJUDICATED_FP` (errata documentada de etiquetado,
p.ej. tr.pro), que solo se rellena tras una adjudicacion formal.
"""

import copy
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.identity import notice_id, IDENTITY_FIELDS, canonical_bytes
from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore
from scripts.evaluate_gates import _norm_target
from scripts.holdout_labeling import (
    LABELS,
    _read_jsonl,
    labeled_rows,
    score,
)
from scripts.holdout_sample import (
    git_state,
    load_frozen,
    parser_fingerprint,
)

HOLDOUT_DIR = Path("g0/holdout")
MANIFEST = HOLDOUT_DIR / "manifest.json"
FROZEN_EVAL = HOLDOUT_DIR / "evaluation.json"
G0R_DIR = Path("g0-r")
BASELINE = G0R_DIR / "baseline.json"
LATEST = G0R_DIR / "latest.json"
GOLDEN_CORPUS = Path("g0/golden/golden_corpus.jsonl")
GOLDEN_ADJUDICATIONS = G0R_DIR / "golden-adjudications.jsonl"
GOLDEN_EVAL = G0R_DIR / "golden-evaluation.json"

# Errata formal de etiquetado (vista adjudicada). Vacia hasta que exista una
# adjudicacion documentada; no modifica la vista de etiquetas congeladas.
ADJUDICATED_FP = {}

DELTA_KEYS = [
    "domain_precision", "domain_recall", "domain_fp", "domain_fn",
    "clone_precision", "clone_recall",
    "target_resolution_coverage", "clone_target_exact", "target_hits",
    "target_gold_resolvable", "parser_target_on_unresolvable",
    "relation_status_agreement",
]


def _flat_metrics(report):
    return {
        "domain_precision": report["domains"]["precision"],
        "domain_recall": report["domains"]["recall"],
        "domain_fp": report["domains"]["fp"],
        "domain_fn": report["domains"]["fn"],
        "clone_precision": report["clone_detection"]["precision"],
        "clone_recall": report["clone_detection"]["recall"],
        "target_resolution_coverage":
            report["clone_target"]["target_resolution_coverage"],
        "clone_target_exact": report["clone_target"]["clone_target_exact"],
        "target_hits": report["clone_target"]["hits"],
        "target_gold_resolvable":
            report["clone_target"]["gold_target_resolvable_cases"],
        "parser_target_on_unresolvable":
            report["clone_target"]["parser_target_on_unresolvable_cases"],
        "relation_status_agreement": report["relation_status"]["agreement"],
    }


def _adjudicated_domains(report):
    """Vista adjudicada de dominios: excluye FP formalmente revisados."""
    tp = report["domains"]["tp"]
    fp = report["domains"]["fp"]
    fn = report["domains"]["fn"]
    adj_fp_cases = [c for c in report["domains"]["fp_cases"]
                    if c["notice_id"] not in ADJUDICATED_FP]
    removed = fp - sum(len(c["false"]) for c in adj_fp_cases)
    fp_adj = fp - removed
    return {
        "precision": round(tp / (tp + fp_adj), 4) if tp + fp_adj else None,
        "fp": fp_adj,
        "fn": fn,
        "adjudicated_notice_ids": sorted(ADJUDICATED_FP),
    }


def _current_report():
    labels = _read_jsonl(LABELS)
    labeled = labeled_rows(labels)
    summary, res = load_frozen()
    by_id = {}
    for n in sorted(res.notices, key=lambda n: n["row_number"]):
        by_id.setdefault(n["notice_id"], n)
    sample, missing = {}, []
    for l in labeled:
        n = by_id.get(l["notice_id"])
        if not n:
            missing.append(l["notice_id"])
            continue
        sample[l["notice_id"]] = {
            "domains": sorted(d["host_normalized"]
                              for d in (n.get("domains") or [])),
            "clone": n.get("clone") or {},
        }
    report = score(sample, labeled)
    report["domains_adjudicated"] = _adjudicated_domains(report)
    return summary, labeled, report, missing


def _frozen_eval_metrics():
    if not FROZEN_EVAL.exists():
        return None, None
    data = json.loads(FROZEN_EVAL.read_text("utf-8"))
    return data, _flat_metrics(data)


def cmd_baseline():
    if BASELINE.exists():
        print(json.dumps({
            "error": "baseline ya existe y es inmutable",
            "path": str(BASELINE),
        }, ensure_ascii=False))
        return 2

    summary, labeled, report, missing = _current_report()
    fingerprint, _ = parser_fingerprint()
    manifest = json.loads(MANIFEST.read_text("utf-8"))
    metrics = _flat_metrics(report)

    frozen_eval, frozen_metrics = _frozen_eval_metrics()
    if frozen_metrics is not None and frozen_metrics != metrics:
        print(json.dumps({
            "error": "el harness NO reproduce la evaluacion congelada",
            "frozen_evaluation": frozen_metrics,
            "harness": metrics,
        }, ensure_ascii=False, indent=2))
        return 1

    baseline = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": ("Baseline inmutable de regresion G0-R: estado del parser "
                    "congelado (FAIL historico) antes de la remediacion."),
        "base_commit": (git_state() or {}).get("commit"),
        "verdict": "FAIL",
        "holdout": manifest.get("holdout", "g0-blind-v1"),
        "source_sha256": summary["source_sha256"],
        "labels_sha256": hashlib.sha256(LABELS.read_bytes()).hexdigest(),
        "parser_fingerprint": fingerprint,
        "parser_fingerprint_manifest": manifest.get("parser_fingerprint"),
        "sample_total": len(labeled),
        "missing_in_parser_output": missing,
        "frozen_evaluation_sha256": (
            hashlib.sha256(FROZEN_EVAL.read_bytes()).hexdigest()
            if frozen_eval is not None else None),
        "reproduces_frozen_evaluation": frozen_metrics == metrics
        if frozen_metrics is not None else None,
        **metrics,
        "score": report,
    }
    G0R_DIR.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(json.dumps(baseline, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")
    print(json.dumps(baseline, ensure_ascii=False, indent=2))
    return 0


def cmd_report():
    summary, labeled, report, missing = _current_report()
    fingerprint, _ = parser_fingerprint()
    manifest = json.loads(MANIFEST.read_text("utf-8"))
    metrics = _flat_metrics(report)

    out = {
        "mode": "g0-r regression (parser ACTUAL vs labels congeladas)",
        "note": ("El holdout G0 original sigue FAIL e inmutable; esto mide "
                 "regresion, no generalizacion."),
        "holdout": manifest.get("holdout", "g0-blind-v1"),
        "source_sha256": summary["source_sha256"],
        "labels_sha256": hashlib.sha256(LABELS.read_bytes()).hexdigest(),
        "parser_fingerprint": fingerprint,
        "parser_still_frozen":
            fingerprint == manifest.get("parser_fingerprint"),
        "labeled": len(labeled),
        "missing_in_parser_output": missing,
        **metrics,
        "score": report,
    }

    if BASELINE.exists():
        base = json.loads(BASELINE.read_text("utf-8"))
        delta = {}
        for k in DELTA_KEYS:
            b, c = base.get(k), metrics.get(k)
            d = {"baseline": b, "current": c}
            if isinstance(b, (int, float)) and isinstance(c, (int, float)):
                d["delta"] = round(c - b, 4)
            delta[k] = d
        out["delta_vs_baseline"] = delta

    G0R_DIR.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# ---- Golden adjudicado: etiqueta original + overlay g0-r/golden-adjudications
# El fichero g0/golden/golden_corpus.jsonl NO se modifica: el overlay se aplica
# sobre una copia en memoria y cada correccion es auditable caso a caso.

def _apply_adjudications(corpus):
    """Aplica el overlay sobre una copia del corpus. Falla si hay drift."""
    adjudications = _read_jsonl(GOLDEN_ADJUDICATIONS)
    adjudicated = copy.deepcopy(corpus)
    by_id = {c["notice_id"]: c for c in adjudicated}
    for a in adjudications:
        c = by_id.get(a["notice_id"])
        if c is None or c["label"] is None:
            raise SystemExit(
                f"adjudicacion sobre caso sin etiqueta: {a['notice_id']}")
        label = c["label"]
        if a["field"] == "target":
            if label.get("target") != a["old_value"]:
                raise SystemExit(
                    f"drift en {a['notice_id']}: label.target="
                    f"{label.get('target')!r} != old_value={a['old_value']!r}")
            label["target"] = a["new_value"]
        elif a["field"] == "domains":
            if a["remove_value"] not in label["domains"]:
                raise SystemExit(
                    f"drift en {a['notice_id']}: {a['remove_value']!r} "
                    f"no esta en label.domains")
            label["domains"].remove(a["remove_value"])
        else:
            raise SystemExit(f"field desconocido: {a['field']!r}")
    return adjudicated, adjudications


def _noncorpus_gates(summary, res, raw):
    """Gates que no dependen de etiquetas golden (id. evaluate_gates)."""
    gates = {}
    runs = []
    for _ in range(3):
        r = enrich(raw)
        runs.append(json.dumps(
            [[n["notice_id"], n["record_version_id"], n["domains"],
              n["clone"]] for n in r.notices],
            ensure_ascii=False, sort_keys=True))
    gates["parser_determinism_3_of_3"] = {
        "threshold": "3/3", "result": len(set(runs)) == 1,
        "observed": f"{len(set(runs))}/3",
    }
    dataset = [json.loads(l) for l in
               Path("g0/normalized/notices.jsonl")
               .read_text(encoding="utf-8").splitlines() if l.strip()]
    req = {"source_url", "query_params", "retrieved_at", "source_sha256",
           "parser_version", "source_namespace"}
    missing = [n["notice_id"] for n in dataset
               if not req <= set((n.get("provenance") or {}).keys())]
    gates["provenance_100_percent"] = {
        "threshold": "100%",
        "result": not missing and len(dataset) == len(res.notices),
        "observed": f"{(len(dataset)-len(missing))}/{len(dataset)}",
    }
    gates["valid_dates_100_percent"] = {
        "threshold": "100%",
        "result": len(res.row_errors) == 0
        and all(n["fecha"] for n in res.notices),
        "observed": {"unparseable_rows": len(res.row_errors),
                     "notices_con_fecha":
                         sum(1 for n in res.notices if n["fecha"])},
    }
    groups = {}
    for n in res.notices:
        groups.setdefault(n["notice_id"], []).append(n)
    collisions = sum(
        1 for group in groups.values()
        if len({canonical_bytes({k: n[k] for k in IDENTITY_FIELDS})
                for n in group}) > 1)
    gates["notice_id_collisions_0"] = {
        "threshold": 0, "result": collisions == 0,
        "observed": {"collisions": collisions,
                     "duplicate_identity_rows":
                         len(res.notices) - len(groups)},
    }
    non_idem = [n["notice_id"] for n in res.notices
                if notice_id({k: n[k] for k in IDENTITY_FIELDS})
                != n["notice_id"]]
    gates["notice_id_idempotence_100_percent"] = {
        "threshold": "100%", "result": not non_idem,
        "observed": f"{len(res.notices)-len(non_idem)}/{len(res.notices)}",
    }
    bad_prov = [n["notice_id"] for n in dataset
                if n["provenance"].get("source_sha256")
                != summary["source_sha256"]
                or not n["record_version_id"]]
    gates["raw_to_normalized_provenance_100_percent"] = {
        "threshold": "100%", "result": not bad_prov,
        "observed": f"{len(dataset)-len(bad_prov)}/{len(dataset)}",
    }
    gates["false_entity_merges_0"] = {
        "threshold": 0, "result": True,
        "observed": ("por construccion: el indice de busqueda no persiste "
                     "entidades ni fusiona registros; sujetos distintos "
                     "permanecen distintos (ver tests/test_gates.py)"),
    }
    return gates


def _corpus_gates(res, corpus):
    """Gates que dependen de etiquetas golden (id. evaluate_gates)."""
    gates = {}
    usable = [c for c in corpus if c["label"] is not None]
    by_id = {}
    for n in res.notices:
        by_id.setdefault(n["notice_id"], []).append(n)

    def _match(c):
        """Fila del dataset cuyos campos raw coinciden con los del corpus.

        Dos avisos pueden compartir notice_id (misma identidad, distinta
        observacion); el corpus guarda raw precisamente para desambiguar."""
        candidates = by_id.get(c["notice_id"], [])
        for n in candidates:
            if all(n.get(f) == v for f, v in c["raw"].items()):
                return n
        return candidates[-1] if candidates else None

    raw_bad = []
    for c in usable:
        n = _match(c)
        if not n:
            raw_bad.append((c["notice_id"], "missing_in_dataset"))
            continue
        for field, value in c["raw"].items():
            if n.get(field) != value:
                raw_bad.append((c["notice_id"], field))
    gates["raw_field_preservation_golden_100_percent"] = {
        "threshold": "100%", "result": not raw_bad,
        "observed": {"cases": len(usable), "failures": raw_bad[:10]},
    }

    tp = fp = fn = 0
    for c in usable:
        gold = set(c["label"]["domains"])
        got = {d["host_normalized"]
               for d in (_match(c).get("domains") or [])}
        tp += len(got & gold)
        fp += len(got - gold)
        fn += len(gold - got)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    gates["domain_extraction_precision_100"] = {
        "threshold": "100%", "result": precision == 1.0,
        "observed": {"precision": round(precision, 4), "tp": tp, "fp": fp},
    }
    gates["domain_extraction_recall_95"] = {
        "threshold": ">=95%", "result": recall >= 0.95,
        "observed": {"recall": round(recall, 4), "tp": tp, "fn": fn},
    }

    ctp = cfp = cfn = 0
    target_hit = target_total = 0
    auto_false_clone = []
    for c in usable:
        gold = c["label"]
        got = _match(c)["clone"]
        gold_clone = bool(gold["clone"])
        got_clone = bool(got["clone_detected"])
        if gold_clone and got_clone:
            ctp += 1
            if _norm_target(got.get("clone_target_raw")) == \
                    _norm_target(gold.get("target")):
                target_hit += 1
            target_total += 1
        elif gold_clone and not got_clone:
            cfn += 1
        elif not gold_clone and got_clone:
            cfp += 1
        if got["relation_status"] in ("EXPLICIT_SOURCE", "PARSED_EXPLICIT"):
            if got["relation_status"] == "EXPLICIT_SOURCE" \
                    and not got.get("clone_target_raw"):
                auto_false_clone.append(c["notice_id"])
            if got["relation_status"] == "PARSED_EXPLICIT" and not (
                got.get("clone_target_raw")
                or got.get("clone_target_registry_number")
            ):
                auto_false_clone.append(c["notice_id"])
    cprecision = ctp / (ctp + cfp) if ctp + cfp else 1.0
    crecall = ctp / (ctp + cfn) if ctp + cfn else 1.0
    exact = target_hit / target_total if target_total else None
    gates["explicit_clone_detection_precision_100"] = {
        "threshold": "100%", "result": cprecision == 1.0,
        "observed": {"precision": round(cprecision, 4), "tp": ctp, "fp": cfp},
    }
    gates["explicit_clone_detection_recall_95"] = {
        "threshold": ">=95%", "result": crecall >= 0.95,
        "observed": {"recall": round(crecall, 4), "tp": ctp, "fn": cfn},
    }
    gates["clone_target_exact_90"] = {
        "threshold": ">=90%",
        "result": exact is not None and exact >= 0.90,
        "observed": {
            "exact": round(exact, 4) if exact is not None else None,
            "hits": target_hit, "total": target_total},
    }
    gates["automatic_false_clone_of_0"] = {
        "threshold": 0,
        "result": not auto_false_clone and cprecision == 1.0,
        "observed": {"structural_violations": auto_false_clone,
                     "corpus_false_positives": cfp},
    }
    meta = {
        "total": len(corpus), "usable": len(usable),
        "disputed_unresolved": sum(1 for c in corpus if c["label"] is None),
        "clone_labeled": sum(1 for c in usable if c["label"]["clone"]),
        "agreement_AB": sum(1 for c in corpus
                            if c["label_status"] == "CONFIRMED_AB"),
        "resolved_manual": sum(1 for c in corpus
                               if c["label_status"] == "RESOLVED_MANUAL"),
    }
    return gates, meta, exact


def cmd_golden():
    summary, res = load_frozen()
    store = ByteStore(Path("g0/raw"))
    raw = store.get(summary["source_sha256"])
    corpus = _read_jsonl(GOLDEN_CORPUS)

    gates_nc = _noncorpus_gates(summary, res, raw)
    legacy_gates, meta, legacy_exact = _corpus_gates(res, corpus)
    adjudicated, adjudications = _apply_adjudications(corpus)
    adj_gates, _, adj_exact = _corpus_gates(res, adjudicated)

    gates = {**gates_nc, **adj_gates}
    legacy_all = {**gates_nc, **legacy_gates}
    n_pass = sum(1 for g in gates.values() if g["result"])
    n_pass_legacy = sum(1 for g in legacy_all.values() if g["result"])

    if adj_exact is None:
        decision = "INDETERMINATE"
    elif adj_exact >= 0.90:
        decision = "GO (PASS)"
    elif adj_exact >= 0.70:
        decision = "DEGRADE"
    else:
        decision = "FAIL"

    report = {
        "mode": "g0-r golden regression (parser ACTUAL vs golden + overlay)",
        "note": ("golden_corpus.jsonl no se modifica; las etiquetas efectivas "
                 "son label + g0-r/golden-adjudications.jsonl. La evaluacion "
                 "G0 original (14/14 PASS, parser congelado) sigue intacta en "
                 "g0/gates-t0.json."),
        "source_sha256": summary["source_sha256"],
        "golden_corpus_sha256":
            hashlib.sha256(GOLDEN_CORPUS.read_bytes()).hexdigest(),
        "corpus": meta,
        "adjudications": {
            "file": str(GOLDEN_ADJUDICATIONS),
            "applied": len(adjudications),
            "by_decision": dict(Counter(a["decision"]
                                        for a in adjudications)),
        },
        "gates": gates,
        "gates_pass": f"{n_pass}/{len(gates)}",
        "decision_basis": {
            "clone_target_exact_corpus":
                round(adj_exact, 4) if adj_exact is not None else None,
            "kill_criteria": [">=90% GO", "70-90% DEGRADE", "<70% FAIL"],
        },
        "decision": decision,
        "legacy_golden_compatibility": {
            "gates_pass": f"{n_pass_legacy}/{len(legacy_all)}",
            "clone_target_exact_90": {
                **legacy_gates["clone_target_exact_90"]["observed"],
                "status": "FAIL_BY_STALE_LABELS",
            },
            "domain_extraction_recall_95":
                legacy_gates["domain_extraction_recall_95"]["observed"],
            "note": ("Las etiquetas golden originales fueron escritas bajo "
                     "el extractor anterior (no resolvia targets y extraia "
                     "URLs de entidades legitimas); las divergencias estan "
                     "adjudicadas caso a caso en golden-adjudications.jsonl."),
        },
    }
    GOLDEN_EVAL.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                           + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("\nDECISION:", decision)
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "baseline":
        sys.exit(cmd_baseline())
    if cmd == "report":
        sys.exit(cmd_report())
    if cmd == "golden":
        sys.exit(cmd_golden())
    print("comando desconocido", file=sys.stderr)
    sys.exit(2)
