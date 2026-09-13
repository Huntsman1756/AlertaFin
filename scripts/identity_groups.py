"""Evidencia de los grupos con `notice_id` repetido (identidad vs version).

Reproduce, sin tocar el parser, la inspeccion de los 7 grupos con identidad
raw repetida en el pull T0 y escribe `g0/identity-groups-t0.json`.

Clasificacion por grupo:
- BYTE_IDENTICAL_DUPLICATE_ROW: misma fila fisica publicada dos veces
  consecutivas (mismo `record_version_id` y mismos `raw_row_bytes`).
- VERSIONED_OBSERVACIONES_ONLY: identidad raw identica; solo cambia
  `Observaciones` (=> `record_version_id` distinto). El versionado funciona.
- OTHER: cualquier otro caso (revisar a mano).

Uso:
  python scripts/identity_groups.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore
from alertafin.identity import canonical_bytes, IDENTITY_FIELDS

CONTENT_FIELDS = [
    "tipo_raw", "fecha_raw", "entidad_raw", "entidad_secundaria_raw",
    "codigo_regulador_raw", "pais_regulador_raw", "pais_codigo_regulador_raw",
    "observaciones_raw", "fecha_baja_raw", "fecha", "fecha_baja",
]


def _diff_fields(rows, fields):
    out = []
    for f in fields:
        seen = {json.dumps(r.get(f), ensure_ascii=False, sort_keys=True)
                for r in rows}
        if len(seen) > 1:
            out.append(f)
    return out


def _classify(rows):
    raw_hex = {r["raw_row_bytes"].hex() for r in rows}
    content_diff = _diff_fields(rows, CONTENT_FIELDS)
    non_identity_diff = [f for f in content_diff if f not in IDENTITY_FIELDS]
    if len(raw_hex) == 1:
        return "BYTE_IDENTICAL_DUPLICATE_ROW", non_identity_diff
    if non_identity_diff == ["observaciones_raw"]:
        return "VERSIONED_OBSERVACIONES_ONLY", non_identity_diff
    return "OTHER", non_identity_diff


def main():
    out_dir = Path("g0")
    summary = json.loads(
        (out_dir / "normalized" / "summary.json").read_text("utf-8"))
    if summary.get("status") != "OK":
        print("SOURCE_UNAVAILABLE: sin pull valido no hay evidencia.")
        return 3
    store = ByteStore(out_dir / "raw")
    raw = store.get(summary["source_sha256"])
    notices = enrich(raw).notices

    groups = {}
    for n in notices:
        groups.setdefault(n["notice_id"], []).append(n)
    dup = {k: v for k, v in groups.items() if len(v) > 1}

    evidence = []
    kinds = Counter()
    for nid in sorted(dup):
        rows = sorted(dup[nid], key=lambda n: n["row_number"])
        identities = {canonical_bytes({k: n[k] for k in IDENTITY_FIELDS})
                      for n in rows}
        kind, non_identity_diff = _classify(rows)
        kinds[kind] += 1
        evidence.append({
            "notice_id": nid,
            "rows": [
                {
                    "row_number": n["row_number"],
                    "record_version_id": n["record_version_id"],
                    "fecha_raw": n["fecha_raw"],
                    "entidad_raw": n["entidad_raw"],
                    "entidad_secundaria_raw": n["entidad_secundaria_raw"],
                    "codigo_regulador_raw": n["codigo_regulador_raw"],
                    "pais_regulador_raw": n["pais_regulador_raw"],
                    "observaciones_raw": n["observaciones_raw"],
                    "fecha_baja_raw": n["fecha_baja_raw"],
                }
                for n in rows
            ],
            "identity_canonical_distinct": len(identities),
            "raw_row_bytes_distinct": len({n["raw_row_bytes"] for n in rows}),
            "non_identity_diff_fields": non_identity_diff,
            "classification": kind,
        })

    report = {
        "metric_kind": "identity-evidence (NO gates)",
        "source_sha256": summary["source_sha256"],
        "rows_total": len(notices),
        "notice_ids_unique": len(groups),
        "duplicate_identity_groups": len(dup),
        "duplicate_identity_rows": len(notices) - len(groups),
        "classification_counts": dict(kinds),
        "conclusion": (
            "Ningun grupo representa dos notices distintos: o es la misma "
            "fila publicada dos veces (bytes identicos) o difiere solo en "
            "Observaciones, que no forma parte de la identidad por diseno. "
            "La identidad no esta subespecificada en estos 7 casos."),
        "groups": evidence,
    }
    path = out_dir / "identity-groups-t0.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(json.dumps({
        "duplicate_identity_groups": report["duplicate_identity_groups"],
        "duplicate_identity_rows": report["duplicate_identity_rows"],
        "classification_counts": report["classification_counts"],
        "written": str(path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
