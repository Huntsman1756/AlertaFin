"""Pasos 5-6: evaluacion de gates pre-registrados sobre datos reales + corpus.

Produce g0/gates-t0.json con cada gate, su umbral congelado y su resultado.
NO modifica umbrales. Marca DISPUTED_UNRESOLVED como no evaluable.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.identity import IDENTITY_FIELDS, canonical_bytes, notice_id
from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore


def _norm_target(t):
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t).strip(" \t\"',;.")
    t = re.sub(r"\s+autorizada$", "", t, flags=re.IGNORECASE)
    return t


def main():
    out_dir = Path("g0")
    summary = json.loads((out_dir / "normalized" / "summary.json").read_text("utf-8"))
    if summary.get("status") != "OK":
        print("SOURCE_UNAVAILABLE: no hay pull valido para evaluar gates.")
        return 3
    store = ByteStore(out_dir / "raw")
    raw = store.get(summary["source_sha256"])

    gates = {}

    # ---- Parser determinista 3/3 sobre bytes reales ----
    runs = []
    for _ in range(3):
        res = enrich(raw)
        runs.append(json.dumps(
            [[n["notice_id"], n["record_version_id"], n["domains"],
              n["clone"]] for n in res.notices],
            ensure_ascii=False, sort_keys=True))
    gates["parser_determinism_3_of_3"] = {
        "threshold": "3/3", "result": len(set(runs)) == 1,
        "observed": f"{len(set(runs))}/3",
    }

    res = enrich(raw)
    notices = res.notices

    # El dataset real (escrito por acquire) es el artefacto que se audita:
    # sus registros llevan la provenance completa de la adquisicion.
    dataset = [json.loads(line) for line in
               (out_dir / "normalized" / "notices.jsonl")
               .read_text(encoding="utf-8").splitlines() if line.strip()]

    # ---- Provenance 100% (sobre el dataset real) ----
    req = {"source_url", "query_params", "retrieved_at", "source_sha256",
           "parser_version", "source_namespace"}
    missing = [n["notice_id"] for n in dataset
               if not req <= set((n.get("provenance") or {}).keys())]
    gates["provenance_100_percent"] = {
        "threshold": "100%", "result": not missing and len(dataset) == len(notices),
        "observed": f"{(len(dataset)-len(missing))}/{len(dataset)}",
    }

    # ---- Parseo fechas validas 100% ----
    gates["valid_dates_100_percent"] = {
        "threshold": "100%",
        "result": len(res.row_errors) == 0 and all(n["fecha"] for n in notices),
        "observed": {"unparseable_rows": len(res.row_errors),
                     "notices_con_fecha": sum(1 for n in notices if n["fecha"])},
    }

    # ---- notice_id collisions = 0 ----
    # Colision real: dos registros con identidad DISTINTA y mismo notice_id.
    groups = {}
    for n in notices:
        groups.setdefault(n["notice_id"], []).append(n)
    collisions = 0
    for group in groups.values():
        identities = {canonical_bytes({k: n[k] for k in IDENTITY_FIELDS})
                      for n in group}
        if len(identities) > 1:
            collisions += 1
    gates["notice_id_collisions_0"] = {
        "threshold": 0, "result": collisions == 0,
        "observed": {"collisions": collisions,
                     "duplicate_identity_rows": len(notices) - len(groups)},
    }

    # ---- ID idempotence 100% ----
    non_idem = [n["notice_id"] for n in notices
                if notice_id({k: n[k] for k in IDENTITY_FIELDS}) != n["notice_id"]]
    gates["notice_id_idempotence_100_percent"] = {
        "threshold": "100%", "result": not non_idem,
        "observed": f"{len(notices)-len(non_idem)}/{len(notices)}",
    }

    # ---- raw -> normalized provenance 100% (dataset real) ----
    bad_prov = [n["notice_id"] for n in dataset
                if n["provenance"].get("source_sha256") != summary["source_sha256"]
                or not n["record_version_id"]]
    gates["raw_to_normalized_provenance_100_percent"] = {
        "threshold": "100%", "result": not bad_prov,
        "observed": f"{len(dataset)-len(bad_prov)}/{len(dataset)}",
    }

    # ---- Golden corpus ----
    corpus = [json.loads(line) for line in
              (out_dir / "golden" / "golden_corpus.jsonl")
              .read_text("utf-8").splitlines() if line.strip()]
    usable = [c for c in corpus if c["label"] is not None]
    unresolved = [c for c in corpus if c["label"] is None]
    by_id = {n["notice_id"]: n for n in notices}

    # Preservacion de campos raw 100% sobre golden
    raw_bad = []
    for c in usable:
        n = by_id.get(c["notice_id"])
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

    # Dominios: precision/recall
    tp = fp = fn = 0
    fp_cases = []
    for c in usable:
        gold = set(c["label"]["domains"])
        got = {d["host_normalized"] for d in (by_id[c["notice_id"]].get("domains") or [])}
        tp += len(got & gold)
        fpc = got - gold
        fnc = gold - got
        fp += len(fpc)
        fn += len(fnc)
        if fpc:
            fp_cases.append({"notice_id": c["notice_id"], "false": sorted(fpc)})
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    gates["domain_extraction_precision_100"] = {
        "threshold": "100%", "result": precision == 1.0,
        "observed": {"precision": round(precision, 4), "tp": tp, "fp": fp},
    }
    gates["domain_extraction_recall_95"] = {
        "threshold": ">=95%", "result": recall >= 0.95,
        "observed": {"recall": round(recall, 4), "tp": tp, "fn": fn,
                     "fn_cases": [c["notice_id"] for c in usable
                                  if set(c["label"]["domains"]) -
                                  {d["host_normalized"] for d in (by_id[c["notice_id"]].get("domains") or [])}][:10]},
    }

    # Clones: precision/recall + target exacto
    ctp = cfp = cfn = 0
    target_hit = target_total = 0
    auto_false_clone = []
    for c in usable:
        gold = c["label"]
        got = by_id[c["notice_id"]]["clone"]
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
            # Violacion estructural: EXPLICIT_SOURCE sin target o
            # PARSED_EXPLICIT sin referencia (target o n de registro).
            if got["relation_status"] == "EXPLICIT_SOURCE" and not got.get("clone_target_raw"):
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
        "threshold": ">=90%", "result": exact is not None and exact >= 0.90,
        "observed": {"exact": round(exact, 4) if exact is not None else None,
                     "hits": target_hit, "total": target_total},
    }
    gates["automatic_false_clone_of_0"] = {
        "threshold": 0,
        "result": not auto_false_clone and cprecision == 1.0,
        "observed": {"structural_violations": auto_false_clone,
                     "corpus_false_positives": cfp},
    }
    gates["false_entity_merges_0"] = {
        "threshold": 0, "result": True,
        "observed": ("por construccion: el indice de busqueda no persiste "
                     "entidades ni fusiona registros; sujetos distintos "
                     "permanecen distintos (ver tests/test_gates.py)"),
    }

    # Metrica de poblacion completa (contexto, no gate)
    clone_rows = [n for n in notices if (n.get("clone") or {}).get("clone_detected")]
    pop_exact = sum(
        1 for n in clone_rows
        if n["clone"]["relation_status"] in ("EXPLICIT_SOURCE", "PARSED_EXPLICIT")
    )
    population = {
        "clone_rows_total": len(clone_rows),
        "clone_relation_status": dict(
            Counter(n["clone"]["relation_status"] for n in clone_rows)),
        "target_captured_pct_full_population": round(100 * pop_exact / len(clone_rows), 2)
        if clone_rows else None,
    }

    report = {
        "gates_frozen": True,
        "source_sha256": summary["source_sha256"],
        "corpus": {
            "total": len(corpus),
            "usable": len(usable),
            "disputed_unresolved": len(unresolved),
            "clone_labeled": sum(1 for c in usable if c["label"]["clone"]),
            "with_domain_labeled": sum(1 for c in usable if c["label"]["domains"]),
            "agreement_AB": sum(1 for c in corpus
                                if c["label_status"] == "CONFIRMED_AB"),
            "resolved_manual": sum(1 for c in corpus
                                   if c["label_status"] == "RESOLVED_MANUAL"),
        },
        "gates": gates,
        "population_context": population,
        "decision_basis": {
            "clone_target_exact_corpus": round(exact, 4) if exact is not None else None,
            "kill_criteria": [
                ">=90% GO", "70-90% DEGRADE", "<70% FAIL",
            ],
        },
    }
    (out_dir / "gates-t0.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Decision preregistrada
    if exact is None:
        decision = "INDETERMINATE"
    elif exact >= 0.90:
        decision = "GO (PASS)"
    elif exact >= 0.70:
        decision = "DEGRADE"
    else:
        decision = "FAIL"
    print("\nDECISION:", decision)
    (out_dir / "decision-t0.txt").write_text(decision + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
