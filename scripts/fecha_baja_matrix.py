"""Paso 3: matriz observable de Fecha Baja (FULL vs ACTIVE estado=actu).

SOLO comportamiento observable: si una fila del pull completo aparece en el
pull con estado=actu. Sin atribuir semantica juridica al campo Fecha Baja.

Compara notice_id (estable ante cambios de Fecha Baja/Observaciones por
diseno de la identidad).
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore


def main():
    out_dir = Path("g0")
    summary = json.loads((out_dir / "normalized" / "summary.json").read_text("utf-8"))
    probe = json.loads((out_dir / "acquisition" / "active_probe.json").read_text("utf-8"))
    active = next(
        (p for p in probe if p.get("query_params", {}).get("estado") == "actu"
         and p.get("http_status") == 200),
        None,
    )
    if not active or not summary.get("source_sha256"):
        print("SOURCE_UNAVAILABLE: falta pull full o probe estado=actu valido.")
        return 3

    store = ByteStore(out_dir / "raw")
    full_raw = store.get(summary["source_sha256"])
    active_raw = store.get(active["sha256"])

    full_res = enrich(full_raw)
    active_res = enrich(active_raw)

    active_ids = {n["notice_id"] for n in active_res.notices}

    matrix = Counter()
    diffs = []
    for n in full_res.notices:
        fb_populated = bool(n["fecha_baja"])
        observed = n["notice_id"] in active_ids
        cell = ("fecha_baja_populated" if fb_populated else "fecha_baja_null",
                "yes" if observed else "no")
        matrix[cell] += 1
        if fb_populated and not observed:
            diffs.append({
                "notice_id": n["notice_id"],
                "entidad_raw": n["entidad_raw"],
                "fecha_raw": n["fecha_raw"],
                "fecha_baja_raw": n["fecha_baja_raw"],
            })

    # Cobertura inversa: filas del activo que NO estan en el full
    full_ids = {n["notice_id"] for n in full_res.notices}
    extra_in_active = [n["notice_id"] for n in active_res.notices
                       if n["notice_id"] not in full_ids]

    report = {
        "metric_kind": "observable matrix (NO juridica)",
        "full_pull": {
            "sha256": summary["source_sha256"],
            "rows": len(full_res.notices),
        },
        "active_pull": {
            "query_params": active["query_params"],
            "sha256": active["sha256"],
            "rows": len(active_res.notices),
        },
        "matrix": {
            f"{k[0]} | aparece_en_ACTIVE={k[1]}": v
            for k, v in sorted(matrix.items())
        },
        "fecha_baja_populated_fuera_de_active": diffs,
        "notices_en_active_no_estan_en_full": extra_in_active,
        "observaciones": [
            "observed_in_active_query es un hecho de respuesta HTTP, no un "
            "estado juridico del aviso.",
            "La identidad usa notice_id, estable ante cambios de Fecha Baja/"
            "Observaciones por diseno.",
        ],
    }
    (out_dir / "fecha-baja-matrix-t0.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
