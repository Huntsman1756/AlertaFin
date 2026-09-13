"""Holdout ciego G0: congela el parser y extrae una muestra estratificada
nueva del historico CNMV, excluyendo el golden corpus ya inspeccionado.

Regla de oro: NO se modifica el parser durante la prueba. El manifest guarda
un `parser_fingerprint` (sha256 del contenido de los modulos del parser). Si
`select` se vuelve a ejecutar con un fingerprint distinto al ya registrado,
aborta; `verify` demuestra que el parser no cambio entre muestreo y etiquetado.

Salida:
  g0/holdout/manifest.json   -> congelacion + diseño estratificado
  g0/holdout/sample.jsonl    -> filas seleccionadas + salida del parser
                                (SIN etiquetas; el etiquetado es manual posterior)

Uso:
  python scripts/holdout_sample.py select    # congela y muestrea (seed fija)
  python scripts/holdout_sample.py verify    # re-verifica congelacion e integridad
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
from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore

HOLDOUT_DIR = Path("g0/holdout")
SEED = 20260914
N_TARGET = 200
MIN_PER_STRATUM = 5

PARSER_FILES = [
    "alertafin/__init__.py",
    "alertafin/identity.py",
    "alertafin/parser.py",
    "alertafin/domainex.py",
    "alertafin/clones.py",
    "alertafin/pipeline.py",
    "alertafin/textnorm.py",
]


def parser_fingerprint():
    h = hashlib.sha256()
    per_file = {}
    for rel in PARSER_FILES:
        data = Path(rel).read_bytes()
        per_file[rel] = hashlib.sha256(data).hexdigest()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(data)
        h.update(b"\0")
    return h.hexdigest(), per_file


def git_state():
    def run(*args):
        try:
            proc = subprocess.run(
                ["git", *args], capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                return None
            return proc.stdout.strip()
        except Exception:
            return None
    commit = run("rev-parse", "--verify", "HEAD")
    dirty = run("status", "--porcelain")
    return {"commit": commit or None,
            "dirty": bool(dirty) if commit else None}


def year_bucket(fecha):
    if not fecha:
        return "sin_fecha"
    y = int(fecha[:4])
    if y < 2019:
        return "<2019"
    if y <= 2021:
        return "2019-2021"
    if y <= 2023:
        return "2022-2023"
    return ">=2024"


def stratum_of(n):
    reg = "CNMV" if n["codigo_regulador_raw"] == "CNMV" else "EXTRANJERO"
    clone = "clone" if (n.get("clone") or {}).get("clone_detected") else "noclone"
    return f"{reg}/{clone}/{year_bucket(n['fecha'])}"


def load_frozen():
    summary = json.loads(
        Path("g0/normalized/summary.json").read_text("utf-8"))
    if summary.get("status") != "OK":
        print("SOURCE_UNAVAILABLE: sin pull valido no se muestrea.")
        sys.exit(3)
    store = ByteStore(Path("g0/raw"))
    raw = store.get(summary["source_sha256"])
    prov = {
        "source_url": summary["source_url"],
        "query_params": summary["query_params"],
        "retrieved_at": summary["retrieved_at"],
        "source_sha256": summary["source_sha256"],
        "http_status": 200,
        "parser_version": PARSER_VERSION,
        "source_namespace": SOURCE_NAMESPACE,
    }
    return summary, enrich(raw, provenance=prov)


def golden_notice_ids():
    path = Path("g0/golden/golden_corpus.jsonl")
    if not path.exists():
        return set()
    return {
        json.loads(line)["notice_id"]
        for line in path.read_text("utf-8").splitlines() if line.strip()
    }


def serializable(n, stratum):
    return {
        "notice_id": n["notice_id"],
        "record_version_id": n["record_version_id"],
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
        "domains": sorted(d["host_normalized"] for d in (n.get("domains") or [])),
        "clone": n.get("clone"),
        "raw_row_bytes_hex": n["raw_row_bytes"].hex(),
        "provenance": n["provenance"],
    }


def cmd_select():
    fingerprint, per_file = parser_fingerprint()
    manifest_path = HOLDOUT_DIR / "manifest.json"
    if manifest_path.exists():
        prev = json.loads(manifest_path.read_text("utf-8"))
        if prev.get("parser_fingerprint") != fingerprint:
            print("ABORTADO: el parser cambio respecto al holdout congelado.")
            print("  manifest :", prev.get("parser_fingerprint"))
            print("  actual   :", fingerprint)
            print("Mueve/renombra g0/holdout antes de muestrear de nuevo.")
            return 2

    summary, res = load_frozen()
    golden = golden_notice_ids()

    # Frame = una fila por notice_id (identidad). Se conserva la primera fila
    # (menor row_number). Las filas extra de identidades repetidas se registran.
    by_id = {}
    for n in sorted(res.notices, key=lambda n: n["row_number"]):
        if n["notice_id"] in golden:
            continue
        by_id.setdefault(n["notice_id"], n)
    collapsed = (len(res.notices) - len(golden & {n["notice_id"] for n in res.notices})
                 - len(by_id))

    strata = {}
    for n in by_id.values():
        strata.setdefault(stratum_of(n), []).append(n)

    total = len(by_id)
    rnd = random.Random(SEED)
    sampled = []
    allocation = {}
    for s in sorted(strata):
        rows = sorted(strata[s], key=lambda n: n["notice_id"])
        take = min(len(rows), max(MIN_PER_STRATUM,
                                  round(N_TARGET * len(rows) / total)))
        chosen = rnd.sample(rows, take)
        allocation[s] = {"population": len(rows), "sampled": take}
        sampled.extend(serializable(n, s) for n in chosen)
    sampled.sort(key=lambda e: (e["stratum"], e["notice_id"]))

    ident_counts = Counter(stratum_of(n) for n in by_id.values())
    manifest = {
        "holdout": "g0-blind-v1",
        "purpose": ("Estimacion de generalizacion fuera del golden corpus. "
                    "Parser congelado; etiquetado manual independiente."),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": SEED,
        "n_target": N_TARGET,
        "n_sampled": len(sampled),
        "parser_version": PARSER_VERSION,
        "source_namespace": SOURCE_NAMESPACE,
        "source_sha256": summary["source_sha256"],
        "parser_fingerprint": fingerprint,
        "parser_files": per_file,
        "git": git_state(),
        "population": {
            "rows_total": len(res.notices),
            "notices_unique": len(by_id) + len(golden & {n["notice_id"] for n in res.notices}),
            "golden_excluded": len({n["notice_id"] for n in res.notices} & golden),
            "duplicate_rows_collapsed": collapsed,
            "sampling_frame": total,
        },
        "strata": {
            s: {**allocation[s], "population_total": ident_counts[s]}
            for s in sorted(allocation)
        },
        "sample_notice_ids": [e["notice_id"] for e in sampled],
        "freeze_notice": ("No modificar los modulos listados en `parser_files` "
                          "hasta etiquetar la muestra. "
                          "`holdout_sample.py verify` debe seguir dando OK."),
    }

    HOLDOUT_DIR.mkdir(parents=True, exist_ok=True)
    (HOLDOUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    with (HOLDOUT_DIR / "sample.jsonl").open("w", encoding="utf-8") as fh:
        for e in sampled:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(json.dumps({
        "parser_fingerprint": fingerprint,
        "sampling_frame": total,
        "golden_excluded": manifest["population"]["golden_excluded"],
        "n_sampled": manifest["n_sampled"],
        "strata": {s: a["sampled"] for s, a in sorted(allocation.items())},
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_verify():
    manifest_path = HOLDOUT_DIR / "manifest.json"
    if not manifest_path.exists():
        print("NO HAY HOLDOUT: ejecuta primero `select`.")
        return 3
    manifest = json.loads(manifest_path.read_text("utf-8"))
    fingerprint, _ = parser_fingerprint()
    problems = []
    if fingerprint != manifest["parser_fingerprint"]:
        problems.append("parser_fingerprint MISMATCH")
    summary, res = load_frozen()
    if summary["source_sha256"] != manifest["source_sha256"]:
        problems.append("source_sha256 MISMATCH")
    by_id = {n["notice_id"]: n for n in res.notices}
    sample = [json.loads(line) for line in
              (HOLDOUT_DIR / "sample.jsonl").read_text("utf-8").splitlines()
              if line.strip()]
    for e in sample:
        n = by_id.get(e["notice_id"])
        if not n:
            problems.append(f"{e['notice_id']}: missing_in_parser_output")
            continue
        if n["record_version_id"] != e["record_version_id"]:
            problems.append(f"{e['notice_id']}: record_version_id changed")
        if n["raw_row_bytes"].hex() != e["raw_row_bytes_hex"]:
            problems.append(f"{e['notice_id']}: raw_row_bytes changed")
        got_dom = sorted(d["host_normalized"] for d in (n.get("domains") or []))
        if got_dom != e["domains"]:
            problems.append(f"{e['notice_id']}: domains changed")
        if n.get("clone") != e["clone"]:
            problems.append(f"{e['notice_id']}: clone changed")
    result = {"status": "OK" if not problems else "MISMATCH",
              "checked": len(sample), "problems": problems[:20]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "select"
    if cmd == "select":
        sys.exit(cmd_select())
    if cmd == "verify":
        sys.exit(cmd_verify())
    print("comando desconocido", file=sys.stderr)
    sys.exit(2)
