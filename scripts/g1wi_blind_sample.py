"""G1-WI: muestreo ciego CNMV (evidencia nueva post-remediacion R1).

NO es holdout-v3 ni rehabilita G0. Reglas congeladas en
`g1-wi/r1-preregistration.md`:

- Excluye todo notice_id ya visto en: golden G0, holdout-v1,
  holdout-v2, identity-groups y G0-R adjudications.
- Selector sin predicciones del parser: la muestra lleva solo campos
  raw + ids; nada de domains/clone.
- Seed derivada mecanicamente del commit de preregistracion R1:
  seed = sha256("g1-wi-blind-v1:" + <commit>).digest()[:8] big-endian.
- n=300, estratificado proporcional por (autoridad CNMV/EXTRANJERO) x
  (bucket de anno), misma convencion que holdout-v2.
- Denominadores minimos se comprueban tras etiquetar; si no alcanzan
  -> INCONCLUSIVE, sin remuestreo.
"""

import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PREREG_COMMIT = "8af629cb98c31fc6baa821d1d3dabf81de8f8a90"
N = 300
SEED = int.from_bytes(
    hashlib.sha256(f"g1-wi-blind-v1:{PREREG_COMMIT}".encode()).digest()[:8],
    "big")

CNMV_ROWS = Path("g1-wi/normalized/cnmv_rows.jsonl")
SEEN_SET = Path("g0/holdout-v2/seen-set.json")
HOLDOUT_V2_SAMPLE = Path("g0/holdout-v2/sample.jsonl")
OUT = Path("g1-wi/blind")

_RAW_FIELDS = ["tipo_raw", "fecha_raw", "entidad_raw",
               "entidad_secundaria_raw", "codigo_regulador_raw",
               "pais_regulador_raw", "pais_codigo_regulador_raw",
               "observaciones_raw", "fecha_baja_raw"]


def _load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _stratum(row: dict) -> str:
    auth = ("CNMV" if (row.get("codigo_regulador_raw") or "").strip()
            == "CNMV" else "EXTRANJERO")
    try:
        year = int((row.get("fecha_raw") or "").rsplit("/", 1)[-1])
    except (ValueError, IndexError):
        year = 0
    bucket = ("<2019" if year < 2019 else
              "2019-2021" if year < 2022 else
              "2022-2023" if year < 2024 else ">=2024")
    return f"{auth}/{bucket}"


def main() -> int:
    rows = _load_jsonl(CNMV_ROWS)
    seen = set(json.loads(SEEN_SET.read_text("utf-8"))["notice_ids"])
    seen |= {r["notice_id"] for r in _load_jsonl(HOLDOUT_V2_SAMPLE)}

    eligible = [r for r in rows if r["notice_id"] not in seen]
    by_stratum = {}
    for r in eligible:
        by_stratum.setdefault(_stratum(r), []).append(r)

    # Asignacion proporcional (largest remainder), deterministico.
    total = len(eligible)
    quotas = {k: len(v) * N / total for k, v in by_stratum.items()}
    alloc = {k: int(q) for k, q in quotas.items()}
    for k in sorted(by_stratum,
                    key=lambda k: quotas[k] - alloc[k],
                    reverse=True)[: N - sum(alloc.values())]:
        alloc[k] += 1

    rng = random.Random(SEED)
    sample = []
    for stratum in sorted(by_stratum):
        pool = sorted(by_stratum[stratum], key=lambda r: r["row_number"])
        for r in rng.sample(pool, min(alloc[stratum], len(pool))):
            sample.append({  # noqa: PERF401  (cuerpo multi-linea, legibilidad)
                "notice_id": r["notice_id"],
                "record_version_id": r["record_version_id"],
                "case_key": f"{r['notice_id']}:{r['record_version_id']}",
                "row_number": r["row_number"],
                "stratum": stratum,
                "raw": {f: r.get(f) for f in _RAW_FIELDS},
            })
    rng.shuffle(sample)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "sample.jsonl").open("w", encoding="utf-8",
                                     newline="\n") as fh:
        for c in sample:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    manifest = {
        "experiment": "g1-wi-blind-cnmv-v1",
        "preregistration_commit": PREREG_COMMIT,
        "seed": SEED,
        "seed_derivation":
            "sha256('g1-wi-blind-v1:' + prereg_commit)[0:8] big-endian",
        "n": len(sample),
        "corpus": {
            "path": CNMV_ROWS.as_posix(),
            "rows": len(rows),
            "excluded_seen_notice_ids": len(seen),
            "eligible": total,
        },
        "strata": dict(Counter(c["stratum"] for c in sample)),
        "labels": "PENDING — etiquetado ciego externo; congelar antes "
                  "de evaluar. Si denominadores insuficientes -> "
                  "INCONCLUSIVE, sin remuestreo.",
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
