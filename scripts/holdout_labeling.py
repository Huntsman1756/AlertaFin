"""Holdout ciego G0: vistas de etiquetado y evaluacion independiente.

No modifica el parser, la muestra, el seed ni el manifest. Solo deriva vistas
de `g0/holdout/sample.jsonl`:

- `blind`    -> g0/holdout/labeling-blind.jsonl
                Misma muestra (210 IDs) SIN ningun output inferido por
                AlertaFin (`domains`, `clone`, `raw_row_bytes_hex`) para que
                el etiquetado humano no quede anclado. `stratum` se sustituye
                por `stratum_blind` (regulador/tramo), porque el estrato
                original codifica la prediccion de clon.
- `scaffold` -> g0/holdout/labels.jsonl
                Plantilla de etiquetas humanas (vacia). No sobreescribe si ya
                existe, salvo --force.
- `evaluate` -> g0/holdout/evaluation.json
                Join por `notice_id` entre etiquetas humanas y las
                predicciones congeladas del sample; calcula precision/recall.

Uso:
  python scripts/holdout_labeling.py blind
  python scripts/holdout_labeling.py scaffold
  python scripts/holdout_labeling.py evaluate
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.holdout_sample import parser_fingerprint

HOLDOUT_DIR = Path("g0/holdout")
SAMPLE = HOLDOUT_DIR / "sample.jsonl"
MANIFEST = HOLDOUT_DIR / "manifest.json"
BLIND = HOLDOUT_DIR / "labeling-blind.jsonl"
LABELS = HOLDOUT_DIR / "labels.jsonl"
EVAL = HOLDOUT_DIR / "evaluation.json"

PROV_KEYS = [
    "source_url", "query_params", "retrieved_at", "source_sha256",
    "http_status", "parser_version", "source_namespace",
]
LABEL_FIELDS = [
    "expected_domains", "expected_clone_detected", "expected_clone_target",
    "expected_relation_status", "notes",
]


def _read_jsonl(path):
    return [json.loads(line) for line in
            Path(path).read_text("utf-8").splitlines() if line.strip()]


def blind_stratum(stratum):
    """Quita el token de clon del estrato (REG/clone|noclone/TRAMO)."""
    parts = stratum.split("/")
    if len(parts) == 3:
        return f"{parts[0]}/{parts[2]}"
    return stratum


def blind_entry(entry):
    """Vista de una fila sin ningun output inferido por el sistema."""
    return {
        "notice_id": entry["notice_id"],
        "record_version_id": entry["record_version_id"],
        "row_number": entry["row_number"],
        "stratum_blind": blind_stratum(entry["stratum"]),
        "raw": entry["raw"],
        "fecha": entry["fecha"],
        "fecha_baja": entry["fecha_baja"],
        "provenance": {k: entry["provenance"].get(k) for k in PROV_KEYS},
    }


def cmd_blind():
    sample = _read_jsonl(SAMPLE)
    with BLIND.open("w", encoding="utf-8") as fh:
        for entry in sample:
            fh.write(json.dumps(blind_entry(entry), ensure_ascii=False) + "\n")
    keys = sorted({k for e in sample for k in e})
    print(json.dumps({
        "written": str(BLIND),
        "cases": len(sample),
        "removed_inferred": ["domains", "clone", "raw_row_bytes_hex"],
        "stratum_blind": "REG/tramo (sin flag de clon)",
        "sample_keys": keys,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_scaffold(force=False):
    if LABELS.exists() and not force:
        print(json.dumps({
            "skipped": str(LABELS),
            "reason": "ya existe; usa --force para sobreescribir",
        }, ensure_ascii=False))
        return 0
    sample = _read_jsonl(SAMPLE)
    with LABELS.open("w", encoding="utf-8") as fh:
        for entry in sample:
            row = {"notice_id": entry["notice_id"],
                   "stratum_blind": blind_stratum(entry["stratum"]),
                   "labeled": False}
            row.update({f: None for f in LABEL_FIELDS})
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"written": str(LABELS), "cases": len(sample),
                      "fields": ["labeled", *LABEL_FIELDS]},
                     ensure_ascii=False, indent=2))
    return 0


def _norm_target(t):
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t).strip(" \t\"',;.")
    t = re.sub(r"\s+autorizada$", "", t, flags=re.IGNORECASE)
    return t


def _ratio(num, den):
    return round(num / den, 4) if den else None


def labeled_rows(labels):
    """Solo las filas marcadas explicitamente `labeled: true`."""
    return [l for l in labels if l.get("labeled") is True]


def validate_label(l):
    """Tipos obligatorios de una fila etiquetada. Lista de errores (vacia = OK)."""
    errs = []
    domains = l.get("expected_domains")
    if not isinstance(domains, list) or not all(isinstance(d, str) for d in domains):
        errs.append("expected_domains debe ser lista de strings")
    if not isinstance(l.get("expected_clone_detected"), bool):
        errs.append("expected_clone_detected debe ser bool")
    target = l.get("expected_clone_target")
    if target is not None and not isinstance(target, str):
        errs.append("expected_clone_target debe ser str o null")
    rel = l.get("expected_relation_status")
    if rel is not None and not isinstance(rel, str):
        errs.append("expected_relation_status debe ser str o null")
    return errs


def score(sample, labeled):
    """Metricas del holdout. La seleccion de filas la hace `cmd_evaluate`.

    Dos preguntas separadas:
    - deteccion de clon: sobre todos los casos etiquetados.
    - target exacto: solo sobre ground truth con target explicitamente
      resoluble. Si el ground truth no fija target, el caso queda FUERA del
      denominador (no se cuenta un null/null como acierto).
    """
    dtp = dfp = dfn = 0
    fp_cases, fn_cases = [], []
    ctp = cfp = cfn = 0
    clone_mismatch = []
    rel_agree = rel_total = 0
    rel_mismatch = []
    gold_clone_cases = 0
    gold_resolvable = 0
    parser_resolved = 0
    parser_on_unresolvable = 0
    target_hit = target_miss = 0
    target_miss_cases = []

    for l in labeled:
        e = sample[l["notice_id"]]
        gold = set(l["expected_domains"])
        got = set(e["domains"])
        dtp += len(gold & got)
        dfp += len(got - gold)
        dfn += len(gold - got)
        if got - gold:
            fp_cases.append({"notice_id": l["notice_id"],
                             "false": sorted(got - gold)})
        if gold - got:
            fn_cases.append({"notice_id": l["notice_id"],
                             "missed": sorted(gold - got)})

        gold_clone = l["expected_clone_detected"]
        got_clone = bool(e["clone"]["clone_detected"])
        if gold_clone and got_clone:
            ctp += 1
        elif gold_clone and not got_clone:
            cfn += 1
        elif not gold_clone and got_clone:
            cfp += 1
        if gold_clone != got_clone:
            clone_mismatch.append({"notice_id": l["notice_id"],
                                   "expected": gold_clone, "got": got_clone})

        if gold_clone:
            gold_clone_cases += 1
            gold_t = _norm_target(l.get("expected_clone_target"))
            got_t = _norm_target(e["clone"].get("clone_target_raw"))
            if gold_t:
                gold_resolvable += 1
                if got_t:
                    parser_resolved += 1
                    if gold_t == got_t:
                        target_hit += 1
                    else:
                        target_miss += 1
                        target_miss_cases.append({
                            "notice_id": l["notice_id"],
                            "expected": l.get("expected_clone_target"),
                            "got": e["clone"].get("clone_target_raw")})
                else:
                    target_miss += 1
                    target_miss_cases.append({
                        "notice_id": l["notice_id"],
                        "expected": l.get("expected_clone_target"),
                        "got": None})
            elif got_t:
                parser_on_unresolvable += 1

        if l.get("expected_relation_status") is not None:
            rel_total += 1
            if l["expected_relation_status"] == e["clone"]["relation_status"]:
                rel_agree += 1
            else:
                rel_mismatch.append({
                    "notice_id": l["notice_id"],
                    "expected": l["expected_relation_status"],
                    "got": e["clone"]["relation_status"]})

    dprec = _ratio(dtp, dtp + dfp)
    drec = _ratio(dtp, dtp + dfn)
    cprec = _ratio(ctp, ctp + cfp)
    crec = _ratio(ctp, ctp + cfn)
    texact = _ratio(target_hit, gold_resolvable)
    rel = _ratio(rel_agree, rel_total)

    return {
        "domains": {
            "precision": dprec, "recall": drec,
            "tp": dtp, "fp": dfp, "fn": dfn,
            "fp_cases": fp_cases[:20], "fn_cases": fn_cases[:20],
        },
        "clone_detection": {
            "precision": cprec, "recall": crec,
            "tp": ctp, "fp": cfp, "fn": cfn,
            "mismatches": clone_mismatch[:20],
        },
        "clone_target": {
            "gold_clone_cases": gold_clone_cases,
            "gold_target_resolvable_cases": gold_resolvable,
            "parser_target_resolved_cases": parser_resolved,
            "parser_target_on_unresolvable_cases": parser_on_unresolvable,
            "target_resolution_coverage": _ratio(parser_resolved, gold_resolvable),
            "clone_target_exact": texact,
            "hits": target_hit, "misses": target_miss,
            "miss_cases": target_miss_cases[:20],
        },
        "relation_status": {
            "agreement": rel, "total": rel_total,
            "mismatches": rel_mismatch[:20],
        },
        "gate_status": {
            "domain_precision_100": dprec == 1.0 if dprec is not None else None,
            "domain_recall_95": drec >= 0.95 if drec is not None else None,
            "clone_precision_100": cprec == 1.0 if cprec is not None else None,
            "clone_recall_95": crec >= 0.95 if crec is not None else None,
            "clone_target_exact_90": (None if texact is None
                                      else texact >= 0.90),
        },
    }


def cmd_evaluate():
    if not LABELS.exists():
        print("NO HAY ETIQUETAS: ejecuta primero `scaffold` y etiqueta.")
        return 3
    sample = {e["notice_id"]: e for e in _read_jsonl(SAMPLE)}
    labels = _read_jsonl(LABELS)

    unknown = sorted({l["notice_id"] for l in labels} - set(sample))
    if unknown:
        print(json.dumps({"error": "notice_id fuera de la muestra",
                          "unknown": unknown[:10]}, ensure_ascii=False))
        return 2

    counts = Counter(l["notice_id"] for l in labels)
    duplicates = sorted(k for k, v in counts.items() if v > 1)
    if duplicates:
        print(json.dumps({"error": "notice_id duplicado en labels",
                          "duplicates": duplicates[:10]}, ensure_ascii=False))
        return 2

    labeled = labeled_rows(labels)
    errors = {l["notice_id"]: errs for l in labeled
              if (errs := validate_label(l))}
    if errors:
        print(json.dumps({"error": "etiquetas invalidas",
                          "details": errors}, ensure_ascii=False, indent=2))
        return 2

    current_fp, _ = parser_fingerprint()
    manifest = json.loads(MANIFEST.read_text("utf-8")) if MANIFEST.exists() else {}

    report = {
        "holdout": manifest.get("holdout", "g0-blind-v1"),
        "source_sha256": manifest.get("source_sha256"),
        "parser_fingerprint_manifest": manifest.get("parser_fingerprint"),
        "parser_fingerprint_now": current_fp,
        "parser_still_frozen":
            manifest.get("parser_fingerprint") == current_fp,
        "sample_total": len(sample),
        "labeled": len(labeled),
        "pending": len(sample) - len(labeled),
        "invalid": len(errors),
    }
    report.update(score(sample, labeled))
    EVAL.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "blind"
    if cmd == "blind":
        sys.exit(cmd_blind())
    if cmd == "scaffold":
        sys.exit(cmd_scaffold(force="--force" in sys.argv))
    if cmd == "evaluate":
        sys.exit(cmd_evaluate())
    print("comando desconocido", file=sys.stderr)
    sys.exit(2)
