"""Holdout ciego v2: seleccion, vistas de etiquetado y evaluacion.

Implementa lo preregistrado en `g0/holdout-v2/preregistration.md` (commit
`0b4ee63`, enmienda docs-only sobre `c01cae3`). Diferencias frente a v1:

- `case_key = (notice_id, record_version_id)`; exclusion por notice_id
  completo del seen set; maximo una version por notice_id en la muestra
  (record_version_id lexicograficamente menor).
- Estratos `regulator_group x temporal_bucket` SIN estrato de clon.
- Seed derivada del commit de preregistracion (sin eleccion manual).
- Asignacion cerrada: min(5, pop) + largest remainder/Hamilton sobre
  capacidad restante, empates lexicograficos, total exacto n=300.
- Freeze ampliado: parser + evaluator + este script + contrato de
  anotacion + seen set, todo con sha256 en el manifest.
- El codigo bajo prueba es el parser de `ab07001` (tag
  `g0-r-regression-pass`): `select` aborta si el fingerprint del parser
  o el ultimo commit que toco los ficheros del parser difieren.

Uso:
  python scripts/holdout_v2.py select     # congela y muestrea UNA vez
  python scripts/holdout_v2.py verify     # re-verifica la congelacion
  python scripts/holdout_v2.py blind      # vista ciega para etiquetar
  python scripts/holdout_v2.py scaffold   # plantilla labels.jsonl
  python scripts/holdout_v2.py evaluate   # join + gates + veredicto
"""

import hashlib
import json
import random
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin import PARSER_VERSION, SOURCE_NAMESPACE
from scripts.holdout_sample import (
    git_state,
    load_frozen,
    parser_fingerprint,
    year_bucket,
)

HOLDOUT_DIR = Path("g0/holdout-v2")
MANIFEST = HOLDOUT_DIR / "manifest.json"
SEEN_SET = HOLDOUT_DIR / "seen-set.json"
SAMPLE = HOLDOUT_DIR / "sample.jsonl"
BLIND = HOLDOUT_DIR / "labeling-blind.jsonl"
LABELS = HOLDOUT_DIR / "labels.jsonl"
EVAL = HOLDOUT_DIR / "evaluation.json"
CONTRACT = HOLDOUT_DIR / "annotation-contract-v2.md"
PREREG = HOLDOUT_DIR / "preregistration.md"

# ---- Preregistrado (no editable tras el freeze) ----
SEED_MATERIAL = ("AlertaFin-holdout-v2|"
                 "c01cae34ffd29019d7d124cc7aeaba4907230006|sample")
SEED = int.from_bytes(
    hashlib.sha256(SEED_MATERIAL.encode("utf-8")).digest()[:8], "big")
N_TOTAL = 300
MIN_PER_NONEMPTY_STRATUM = 5

PREREGISTRATION_COMMIT = "c01cae34ffd29019d7d124cc7aeaba4907230006"
CODE_UNDER_TEST_COMMIT = "ab07001b0919ac5694e034fe686f87ac27df732e"
EXPECTED_PARSER_FINGERPRINT = (
    "a200675e896c27bf559ed328b26afafc4b7aca54f723c9a552e78876e0437c70")

# Evaluator = este script + la infra compartida de holdout_sample que se
# reutiliza (load_frozen, fingerprint, git_state, year_bucket).
EVALUATOR_FILES = [
    "scripts/holdout_v2.py",
    "scripts/holdout_sample.py",
]

SEEN_SOURCES = {
    "golden": "g0/golden/golden_corpus.jsonl",
    "holdout_v1": "g0/holdout/labels.jsonl",
    "identity_groups": "g0/identity-groups-t0.json",
    "g0r_adjudications": "g0-r/golden-adjudications.jsonl",
}

PROV_KEYS = [
    "source_url", "query_params", "retrieved_at", "source_sha256",
    "http_status", "parser_version", "source_namespace",
]
LABEL_FIELDS = [
    "expected_domains", "expected_clone_detected", "expected_clone_target",
    "expected_relation_status", "unclear", "notes",
]

DENOMINATOR_MINIMUMS = {
    "gold_domain_instances": 100,
    "gold_clone_cases": 20,
    "gold_target_resolvable_cases": 15,
    "gold_target_unresolvable_cases": 3,
}

PARSER_FILES = [  # para localizar el ultimo commit que toco el parser
    "alertafin/__init__.py", "alertafin/identity.py", "alertafin/parser.py",
    "alertafin/domainex.py", "alertafin/clones.py", "alertafin/pipeline.py",
    "alertafin/textnorm.py",
]


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_lines(items):
    h = hashlib.sha256()
    for it in items:
        h.update(str(it).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def evaluator_fingerprint():
    h = hashlib.sha256()
    per_file = {}
    for rel in EVALUATOR_FILES:
        data = Path(rel).read_bytes()
        per_file[rel] = hashlib.sha256(data).hexdigest()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\0")
    return h.hexdigest(), per_file


def _git(*args):
    proc = subprocess.run(["git", *args], capture_output=True, text=True,
                          check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def last_parser_commit():
    return _git("log", "-1", "--format=%H", "--", *PARSER_FILES)


def case_key(n):
    return {"notice_id": n["notice_id"],
            "record_version_id": n["record_version_id"]}


def regulator_group(n):
    return "CNMV" if n["codigo_regulador_raw"] == "CNMV" else "EXTRANJERO"


def stratum_of(n):
    return f"{regulator_group(n)}/{year_bucket(n['fecha'])}"


# ---- Seen set (fail-closed) ----

def _seen_from_file(name, path):
    p = Path(path)
    if not p.exists():
        raise SystemExit(
            f"seen-set FAIL-CLOSED: falta la fuente {name} ({path})")
    data = p.read_bytes()
    if name == "identity_groups":
        doc = json.loads(data)
        ids = {g["notice_id"] for g in doc["groups"]}
    else:
        ids = {json.loads(l)["notice_id"]
               for l in data.decode("utf-8").splitlines() if l.strip()}
    return {"path": path, "sha256": hashlib.sha256(data).hexdigest(),
            "count": len(ids), "notice_ids": ids}


def build_seen_set(sources=None):
    sources = sources or SEEN_SOURCES
    report, union = {}, set()
    for name, path in sources.items():
        info = _seen_from_file(name, path)
        union |= info.pop("notice_ids")
        report[name] = info
    return union, {
        "sources": report,
        "union_count": len(union),
        "union_sha256": _sha256_lines(sorted(union)),
        "notice_ids": sorted(union),
    }


# ---- Asignacion cerrada ----

def allocate(populations, n_total=N_TOTAL,
             min_per=MIN_PER_NONEMPTY_STRATUM):
    """min(min_per, pop) por estrato + Hamilton sobre capacidad restante."""
    base = {s: min(min_per, p) for s, p in populations.items()}
    if sum(base.values()) > n_total:
        raise SystemExit("asignacion imposible: minimos superan n_total")
    remaining = n_total - sum(base.values())
    capacity = {s: populations[s] - base[s] for s in populations}
    total_cap = sum(capacity.values())
    if total_cap < remaining:
        raise SystemExit(
            f"poblacion elegible insuficiente: {sum(populations.values())}"
            f" < {n_total}")
    quotas = {s: remaining * capacity[s] / total_cap for s in capacity}
    take = dict(base)
    for s in quotas:
        take[s] += int(quotas[s])
    leftover = n_total - sum(take.values())
    by_remainder = sorted(
        capacity, key=lambda s: (-(quotas[s] - int(quotas[s])), s))
    for s in by_remainder:
        if leftover <= 0:
            break
        if take[s] < populations[s]:
            take[s] += 1
            leftover -= 1
    if leftover:
        for s in sorted(capacity):
            if leftover <= 0:
                break
            room = populations[s] - take[s]
            add = min(room, leftover)
            take[s] += add
            leftover -= add
    if leftover:
        raise SystemExit("asignacion imposible: capacidad agotada")
    return take


def pick_version(notices):
    """Una version por notice_id: record_version_id lexicografico menor."""
    best = {}
    for n in notices:
        cur = best.get(n["notice_id"])
        if cur is None or n["record_version_id"] < cur["record_version_id"]:
            best[n["notice_id"]] = n
    return best


def serializable(n, stratum):
    e = case_key(n)
    e.update({
        "case_key": f"{n['notice_id']}:{n['record_version_id']}",
        "row_number": n["row_number"],
        "stratum": stratum,
        "raw": {
            "tipo_raw": n["tipo_raw"],
            "fecha_raw": n["fecha_raw"],
            "entidad_raw": n["entidad_raw"],
            "entidad_secundaria_raw": n["entidad_secundaria_raw"],
            "codigo_regulador_raw": n["codigo_regulador_raw"],
            "pais_regulador_raw": n["pais_regulador_raw"],
            "pais_codigo_regulador_raw": n["pais_codigo_regulador_raw"],
            "observaciones_raw": n["observaciones_raw"],
            "fecha_baja_raw": n["fecha_baja_raw"],
        },
        "fecha": n["fecha"],
        "fecha_baja": n["fecha_baja"],
        "domains": sorted(d["host_normalized"]
                          for d in (n.get("domains") or [])),
        "clone": n.get("clone"),
        "raw_row_bytes_hex": n["raw_row_bytes"].hex(),
        "provenance": n["provenance"],
    })
    return e


def _write_jsonl(path, rows):
    with Path(path).open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _read_jsonl(path):
    return [json.loads(l) for l in
            Path(path).read_text("utf-8").splitlines() if l.strip()]


def blind_entry(entry):
    """Vista sin ningun output inferido por el sistema."""
    return {
        "case_key": entry["case_key"],
        "notice_id": entry["notice_id"],
        "record_version_id": entry["record_version_id"],
        "row_number": entry["row_number"],
        "stratum_blind": entry["stratum"],
        "raw": entry["raw"],
        "fecha": entry["fecha"],
        "fecha_baja": entry["fecha_baja"],
        "provenance": {k: entry["provenance"].get(k) for k in PROV_KEYS},
    }


# ---- Comandos ----

def cmd_select():
    if MANIFEST.exists():
        print("ABORTADO: el holdout v2 ya esta congelado. "
              "No se vuelve a muestrear.")
        return 2
    state = git_state()
    if state.get("dirty"):
        print("ABORTADO: arbol git sucio; el freeze exige commit limpio.")
        return 2
    for p in (PREREG, CONTRACT):
        if not p.exists():
            print(f"ABORTADO: falta la preregistracion ({p}).")
            return 2
    fingerprint, per_file = parser_fingerprint()
    if fingerprint != EXPECTED_PARSER_FINGERPRINT:
        print("ABORTADO: el parser ya no es el de ab07001.")
        print("  esperado:", EXPECTED_PARSER_FINGERPRINT)
        print("  actual  :", fingerprint)
        return 2
    lpc = last_parser_commit()
    if lpc != CODE_UNDER_TEST_COMMIT:
        print("ABORTADO: el ultimo commit que toco el parser no es ab07001.")
        print("  esperado:", CODE_UNDER_TEST_COMMIT)
        print("  actual  :", lpc)
        return 2

    summary, res = load_frozen()
    seen, seen_report = build_seen_set()

    eligible = [n for n in res.notices if n["notice_id"] not in seen]
    frame = pick_version(eligible)

    populations = Counter(stratum_of(n) for n in frame.values())
    take = allocate(dict(populations))

    rnd = random.Random(SEED)
    sampled = []
    for s in sorted(populations):
        rows = sorted((n for n in frame.values() if stratum_of(n) == s),
                      key=lambda n: (n["notice_id"], n["record_version_id"]))
        chosen = rnd.sample(rows, take[s])
        sampled.extend(serializable(n, s) for n in chosen)
    sampled.sort(key=lambda e: (e["stratum"], e["notice_id"]))

    HOLDOUT_DIR.mkdir(parents=True, exist_ok=True)
    seen_out = {k: v for k, v in seen_report.items()}
    SEEN_SET.write_text(json.dumps(seen_out, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")
    _write_jsonl(SAMPLE, sampled)
    _write_jsonl(BLIND, [blind_entry(e) for e in sampled])

    manifest = {
        "holdout": "g0-blind-v2",
        "purpose": ("Generalizacion del parser ab07001 sobre casos nunca "
                    "inspeccionados en G0/holdout-v1/G0-R."),
        "created_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "preregistration_commit": PREREGISTRATION_COMMIT,
        "code_under_test_commit": CODE_UNDER_TEST_COMMIT,
        "experiment_freeze_commit": state.get("commit"),
        "seed": SEED,
        "seed_material": SEED_MATERIAL,
        "n_target": N_TOTAL,
        "n_sampled": len(sampled),
        "parser_version": PARSER_VERSION,
        "source_namespace": SOURCE_NAMESPACE,
        "source_sha256": summary["source_sha256"],
        "parser_fingerprint": fingerprint,
        "parser_files": per_file,
        "evaluator_fingerprint": evaluator_fingerprint()[0],
        "evaluator_files": evaluator_fingerprint()[1],
        "selection_script_sha256": _sha256_file("scripts/holdout_v2.py"),
        "annotation_contract_sha256": _sha256_file(CONTRACT),
        "preregistration_sha256": _sha256_file(PREREG),
        "sample_sha256": _sha256_file(SAMPLE),
        "labeling_blind_sha256": _sha256_file(BLIND),
        "seen_set": {k: v for k, v in seen_report.items()
                     if k != "notice_ids"},
        "seen_set_sha256": seen_report["union_sha256"],
        "population": {
            "rows_total": len(res.notices),
            "seen_excluded_notices": len(seen
                                         & {n["notice_id"]
                                            for n in res.notices}),
            "eligible_rows": len(eligible),
            "sampling_frame": len(frame),
        },
        "strata": {s: {"population": populations[s], "sampled": take[s]}
                   for s in sorted(take)},
        "allocation_rule": {
            "min_per_nonempty_stratum": MIN_PER_NONEMPTY_STRATUM,
            "remainder": "largest remainder/Hamilton sobre capacidad "
                         "restante; empates lexicograficos; n exacto",
        },
        "denominator_minimums": DENOMINATOR_MINIMUMS,
        "sample_case_keys": [e["case_key"] for e in sampled],
        "freeze_notice": ("No modificar parser, evaluator, selector, "
                          "contrato ni thresholds hasta publicar "
                          "PASS/FAIL/INCONCLUSIVE."),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)
                        + "\n", encoding="utf-8")

    print(json.dumps({
        "status": "FROZEN",
        "seed": SEED,
        "sampling_frame": len(frame),
        "seen_union": len(seen),
        "n_sampled": len(sampled),
        "strata": {s: take[s] for s in sorted(take)},
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_verify():
    if not MANIFEST.exists():
        print("NO HAY HOLDOUT v2: ejecuta primero `select`.")
        return 3
    manifest = json.loads(MANIFEST.read_text("utf-8"))
    problems = []
    fingerprint, _ = parser_fingerprint()
    if fingerprint != manifest["parser_fingerprint"]:
        problems.append("parser_fingerprint MISMATCH")
    ev_fp, _ = evaluator_fingerprint()
    if ev_fp != manifest["evaluator_fingerprint"]:
        problems.append("evaluator_fingerprint MISMATCH")
    if _sha256_file(CONTRACT) != manifest["annotation_contract_sha256"]:
        problems.append("annotation_contract MISMATCH")
    if _sha256_file(SAMPLE) != manifest["sample_sha256"]:
        problems.append("sample.jsonl MISMATCH")
    if _sha256_file(BLIND) != manifest["labeling_blind_sha256"]:
        problems.append("labeling-blind.jsonl MISMATCH")
    seen, _ = build_seen_set()
    if _sha256_lines(sorted(seen)) != manifest["seen_set_sha256"]:
        problems.append("seen-set MISMATCH")

    summary, res = load_frozen()
    if summary["source_sha256"] != manifest["source_sha256"]:
        problems.append("source_sha256 MISMATCH")
    by_key = {(n["notice_id"], n["record_version_id"]): n
              for n in res.notices}
    for e in _read_jsonl(SAMPLE):
        n = by_key.get((e["notice_id"], e["record_version_id"]))
        if not n:
            problems.append(f"{e['case_key']}: missing_in_parser_output")
            continue
        if n["raw_row_bytes"].hex() != e["raw_row_bytes_hex"]:
            problems.append(f"{e['case_key']}: raw_row_bytes changed")
        if sorted(d["host_normalized"] for d in (n.get("domains") or [])) \
                != e["domains"]:
            problems.append(f"{e['case_key']}: domains changed")
        if n.get("clone") != e["clone"]:
            problems.append(f"{e['case_key']}: clone changed")
    result = {"status": "OK" if not problems else "MISMATCH",
              "checked": len(_read_jsonl(SAMPLE)),
              "problems": problems[:20]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


def cmd_blind():
    sample = _read_jsonl(SAMPLE)
    _write_jsonl(BLIND, [blind_entry(e) for e in sample])
    print(json.dumps({
        "written": str(BLIND), "cases": len(sample),
        "removed_inferred": ["domains", "clone", "raw_row_bytes_hex"],
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_scaffold(force=False):
    if LABELS.exists() and not force:
        print(json.dumps({"skipped": str(LABELS),
                          "reason": "ya existe; usa --force"},
                         ensure_ascii=False))
        return 0
    sample = _read_jsonl(SAMPLE)
    with LABELS.open("w", encoding="utf-8") as fh:
        for e in sample:
            row = {"case_key": e["case_key"], "notice_id": e["notice_id"],
                   "record_version_id": e["record_version_id"],
                   "stratum_blind": e["stratum"], "labeled": False}
            row.update({f: None for f in LABEL_FIELDS})
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"written": str(LABELS), "cases": len(sample),
                      "fields": ["labeled", *LABEL_FIELDS]},
                     ensure_ascii=False, indent=2))
    return 0


# ---- Evaluacion ----

def _norm_target(t):
    import re
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t).strip(" \t\"',;.")
    t = re.sub(r"\s+autorizada$", "", t, flags=re.IGNORECASE)
    return t


def _ratio(num, den):
    return round(num / den, 4) if den else None


def validate_label(l):
    errs = []
    domains = l.get("expected_domains")
    if not isinstance(domains, list) or not all(
            isinstance(d, str) for d in domains):
        errs.append("expected_domains debe ser lista de strings")
    if not isinstance(l.get("expected_clone_detected"), bool):
        errs.append("expected_clone_detected debe ser bool")
    if l.get("expected_clone_target") is not None and not isinstance(
            l["expected_clone_target"], str):
        errs.append("expected_clone_target debe ser str o null")
    if l.get("expected_relation_status") is not None and not isinstance(
            l["expected_relation_status"], str):
        errs.append("expected_relation_status debe ser str o null")
    if l.get("unclear") is not None and not isinstance(l["unclear"], bool):
        errs.append("unclear debe ser bool o null")
    return errs


def score(sample_by_key, labeled):
    """Mismas metricas que v1 pero con join por case_key."""
    dtp = dfp = dfn = 0
    fp_cases, fn_cases = [], []
    ctp = cfp = cfn = 0
    clone_mismatch = []
    rel_agree = rel_total = 0
    rel_mismatch = []
    gold_clone = gold_res = gold_unres = 0
    parser_resolved = parser_on_unres = 0
    hit = miss = 0
    miss_cases = []
    gold_domain_instances = 0
    unclear_cases = []

    for l in labeled:
        e = sample_by_key[l["case_key"]]
        if l.get("unclear"):
            unclear_cases.append(l["case_key"])
        gold = set(l["expected_domains"])
        got = set(e["domains"])
        gold_domain_instances += len(gold)
        dtp += len(gold & got)
        dfp += len(got - gold)
        dfn += len(gold - got)
        if got - gold:
            fp_cases.append({"case_key": l["case_key"],
                             "false": sorted(got - gold)})
        if gold - got:
            fn_cases.append({"case_key": l["case_key"],
                             "missed": sorted(gold - got)})

        g_clone = l["expected_clone_detected"]
        p_clone = bool(e["clone"]["clone_detected"])
        if g_clone and p_clone:
            ctp += 1
        elif g_clone and not p_clone:
            cfn += 1
        elif not g_clone and p_clone:
            cfp += 1
        if g_clone != p_clone:
            clone_mismatch.append({"case_key": l["case_key"],
                                   "expected": g_clone, "got": p_clone})

        if g_clone:
            gold_clone += 1
            g_t = _norm_target(l.get("expected_clone_target"))
            p_t = _norm_target(e["clone"].get("clone_target_raw"))
            if g_t:
                gold_res += 1
                if p_t:
                    parser_resolved += 1
                    if g_t == p_t:
                        hit += 1
                    else:
                        miss += 1
                        miss_cases.append({
                            "case_key": l["case_key"],
                            "expected": l.get("expected_clone_target"),
                            "got": e["clone"].get("clone_target_raw")})
                else:
                    miss += 1
                    miss_cases.append({"case_key": l["case_key"],
                                       "expected":
                                           l.get("expected_clone_target"),
                                       "got": None})
            else:
                gold_unres += 1
                if p_t:
                    parser_on_unres += 1

        if l.get("expected_relation_status") is not None:
            rel_total += 1
            if l["expected_relation_status"] == \
                    e["clone"]["relation_status"]:
                rel_agree += 1
            else:
                rel_mismatch.append({
                    "case_key": l["case_key"],
                    "expected": l["expected_relation_status"],
                    "got": e["clone"]["relation_status"]})

    dprec = _ratio(dtp, dtp + dfp)
    drec = _ratio(dtp, dtp + dfn)
    cprec = _ratio(ctp, ctp + cfp)
    crec = _ratio(ctp, ctp + cfn)
    texact = _ratio(hit, gold_res)
    rel = _ratio(rel_agree, rel_total)

    gates = {
        "domain_precision_100":
            dprec == 1.0 if dprec is not None else None,
        "domain_recall_95":
            drec >= 0.95 if drec is not None else None,
        "clone_precision_100":
            cprec == 1.0 if cprec is not None else None,
        "clone_recall_95":
            crec >= 0.95 if crec is not None else None,
        "clone_target_exact_90":
            texact >= 0.90 if texact is not None else None,
        "automatic_false_target_0": parser_on_unres == 0,
    }
    denominators = {
        "gold_domain_instances": gold_domain_instances,
        "gold_clone_cases": gold_clone,
        "gold_target_resolvable_cases": gold_res,
        "gold_target_unresolvable_cases": gold_unres,
    }
    denom_ok = {k: denominators[k] >= v
                for k, v in DENOMINATOR_MINIMUMS.items()}

    if any(g is False for g in gates.values()):
        verdict = "FAIL"
    elif not all(denom_ok.values()):
        verdict = "INCONCLUSIVE"
    elif any(g is None for g in gates.values()):
        verdict = "INCONCLUSIVE"
    else:
        verdict = "PASS"

    return {
        "domains": {"precision": dprec, "recall": drec,
                    "tp": dtp, "fp": dfp, "fn": dfn,
                    "fp_cases": fp_cases[:20], "fn_cases": fn_cases[:20]},
        "clone_detection": {"precision": cprec, "recall": crec,
                            "tp": ctp, "fp": cfp, "fn": cfn,
                            "mismatches": clone_mismatch[:20]},
        "clone_target": {
            "gold_clone_cases": gold_clone,
            "gold_target_resolvable_cases": gold_res,
            "gold_target_unresolvable_cases": gold_unres,
            "parser_target_resolved_cases": parser_resolved,
            "parser_target_on_unresolvable_cases": parser_on_unres,
            "target_resolution_coverage": _ratio(parser_resolved, gold_res),
            "clone_target_exact": texact,
            "hits": hit, "misses": miss,
            "miss_cases": miss_cases[:20]},
        "relation_status": {"agreement": rel, "total": rel_total,
                            "mismatches": rel_mismatch[:20]},
        "gate_status": gates,
        "denominators": {**denominators,
                         "minimums": DENOMINATOR_MINIMUMS,
                         "sufficient": denom_ok},
        "unclear_cases": unclear_cases,
        "verdict": verdict,
    }


def cmd_evaluate():
    if not LABELS.exists():
        print("NO HAY ETIQUETAS: ejecuta primero `scaffold` y etiqueta.")
        return 3
    sample = {e["case_key"]: e for e in _read_jsonl(SAMPLE)}
    labels = _read_jsonl(LABELS)

    unknown = sorted({l["case_key"] for l in labels} - set(sample))
    if unknown:
        print(json.dumps({"error": "case_key fuera de la muestra",
                          "unknown": unknown[:10]}, ensure_ascii=False))
        return 2
    counts = Counter(l["case_key"] for l in labels)
    dup = sorted(k for k, v in counts.items() if v > 1)
    if dup:
        print(json.dumps({"error": "case_key duplicado en labels",
                          "duplicates": dup[:10]}, ensure_ascii=False))
        return 2

    labeled = [l for l in labels if l.get("labeled") is True]
    errors = {l["case_key"]: errs for l in labeled
              if (errs := validate_label(l))}
    if errors:
        print(json.dumps({"error": "etiquetas invalidas",
                          "details": errors}, ensure_ascii=False, indent=2))
        return 2

    manifest = json.loads(MANIFEST.read_text("utf-8"))
    fingerprint, _ = parser_fingerprint()
    ev_fp, _ = evaluator_fingerprint()

    report = {
        "holdout": manifest.get("holdout", "g0-blind-v2"),
        "source_sha256": manifest.get("source_sha256"),
        "code_under_test_commit": manifest.get("code_under_test_commit"),
        "experiment_freeze_commit":
            manifest.get("experiment_freeze_commit"),
        "parser_still_frozen":
            manifest.get("parser_fingerprint") == fingerprint,
        "evaluator_still_frozen":
            manifest.get("evaluator_fingerprint") == ev_fp,
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
    cmd = sys.argv[1] if len(sys.argv) > 1 else "select"
    if cmd == "select":
        sys.exit(cmd_select())
    if cmd == "verify":
        sys.exit(cmd_verify())
    if cmd == "blind":
        sys.exit(cmd_blind())
    if cmd == "scaffold":
        sys.exit(cmd_scaffold(force="--force" in sys.argv))
    if cmd == "evaluate":
        sys.exit(cmd_evaluate())
    print("comando desconocido", file=sys.stderr)
    sys.exit(2)
