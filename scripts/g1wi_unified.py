"""G1-WI.C: construye la vista unificada multifuente (WarningNotice).

Las filas DGSFP vienen del snapshot congelado:
- `g1-wi/normalized/notices.jsonl` (DGSFP, 97 + 10 filas)

Las filas CNMV se **regeneran**: `pipeline.enrich` sobre los raw bytes
inmutables de `g0/raw/` (ByteStore) con la provenance original. Los
artefactos `g0/` no se modifican; la vista v0.2 no hereda los dominios
del extractor historico.

Escribe:
- `g1-wi/normalized/cnmv_rows.jsonl`   (CNMV re-normalizado, CUT actual)
- `g1-wi/normalized/warning_notices.jsonl`
- `g1-wi/normalized/unified_summary.json`

Modelo: `alertafin/unified.py`. Vista derivada v0.2.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore
from alertafin.unified import (
    SOURCE_ORDER,
    build_notices,
    notice_for_jsonl,
)

G0 = Path("g0")
DGSFP = Path("g1-wi/normalized/notices.jsonl")
OUT = Path("g1-wi/normalized")


def _load(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _cnmv_rows():
    """Re-parsea el raw CNMV congelado con el extractor actual."""
    legacy = _load(G0 / "normalized" / "notices.jsonl")
    prov = legacy[0]["provenance"]
    raw = ByteStore(G0 / "raw").get(prov["source_sha256"])
    res = enrich(raw, provenance=prov)
    rows = []
    for n in res.notices:
        out = dict(n)
        out["raw_row_bytes_hex"] = out.pop("raw_row_bytes").hex()
        rows.append(out)
    return rows


def main() -> int:
    cnmv_rows = _cnmv_rows()
    dgsfp_rows = _load(DGSFP)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "cnmv_rows.jsonl").open(
            "w", encoding="utf-8", newline="\n") as fh:
        for r in cnmv_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    rows = cnmv_rows + dgsfp_rows
    notices = build_notices(rows)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "warning_notices.jsonl").open(
            "w", encoding="utf-8", newline="\n") as fh:
        for n in notices:
            fh.write(json.dumps(notice_for_jsonl(n), ensure_ascii=False)
                     + "\n")

    per_source = {}
    for n in notices:
        s = per_source.setdefault(n["source"], {
            "notices": 0, "occurrences": 0, "domain_assertions": 0,
            "clone_evidence": 0})
        s["notices"] += 1
        s["occurrences"] += len(n["source_occurrences"])
        s["domain_assertions"] += len(n["domain_assertions"])
        s["clone_evidence"] += len(n["clone_evidence"])

    summary = {
        "status": "OK",
        "model": "g1wi-unified-1.0.0",
        "sources": {k: per_source.get(k, {"notices": 0, "occurrences": 0,
                                          "domain_assertions": 0,
                                          "clone_evidence": 0})
                    for k in SOURCE_ORDER},
        "total_notices": len(notices),
        "total_occurrences": sum(len(n["source_occurrences"])
                                 for n in notices),
        "notices_multi_occurrence": sum(
            1 for n in notices if len(n["source_occurrences"]) > 1),
    }
    (OUT / "unified_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
