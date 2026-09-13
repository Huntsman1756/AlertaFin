"""Paso 2: caracterizacion descriptiva del historico (product-ceiling metrics).

NO son gates: dependen de como publica CNMV. Lee el pull FULL desde el
ByteStore (bytes identificados por sha256) y produce g0/census-t0.json.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore
from alertafin.textnorm import normalize_name


def main():
    out_dir = Path("g0")
    summary = json.loads((out_dir / "normalized" / "summary.json").read_text("utf-8"))
    if summary.get("status") != "OK":
        print("SOURCE_UNAVAILABLE: no hay pull valido; no se produce censo vacio.")
        return 3
    store = ByteStore(out_dir / "raw")
    raw = store.get(summary["source_sha256"])
    res = enrich(raw, provenance=summary.get("provenance", {}))
    notices = res.notices

    total = len(notices)
    por_anio = Counter()
    por_regulador = Counter()
    por_pais = Counter()
    por_tipo = Counter()
    con_dominio = 0
    multi_dominio = 0
    marcados_clon = 0
    clones_con_registro = 0
    con_entidad_sec = 0
    con_fecha_baja = 0
    nombres = Counter()

    for n in notices:
        if n["fecha"]:
            por_anio[n["fecha"][:4]] += 1
        por_regulador[n["codigo_regulador_raw"]] += 1
        por_pais[n["pais_regulador_raw"]] += 1
        por_tipo[n["tipo_raw"]] += 1
        doms = n.get("domains") or []
        if doms:
            con_dominio += 1
        if len(doms) > 1:
            multi_dominio += 1
        cl = n.get("clone") or {}
        if cl.get("clone_detected"):
            marcados_clon += 1
            if cl.get("clone_target_registry_number"):
                clones_con_registro += 1
        if n["entidad_secundaria_raw"]:
            con_entidad_sec += 1
        if n["fecha_baja"]:
            con_fecha_baja += 1
        key = normalize_name(n["entidad_raw"])
        if key:
            nombres[key] += 1

    repetidos = {k: v for k, v in nombres.items() if v > 1}
    notice_id_counts = Counter(n["notice_id"] for n in notices)

    report = {
        "metric_kind": "product-ceiling (NO gates)",
        "total_warnings": total,
        "unparseable_rows": len(res.row_errors),
        "warnings_por_anio": dict(sorted(por_anio.items())),
        "warnings_por_regulador": dict(por_regulador.most_common()),
        "warnings_por_pais_regulador": dict(por_pais.most_common()),
        "warnings_por_tipo": dict(por_tipo.most_common()),
        "pct_con_dominio_explicito": round(100 * con_dominio / total, 2),
        "pct_multiples_dominios": round(100 * multi_dominio / total, 2),
        "pct_marcados_clon_explicito": round(100 * marcados_clon / total, 2),
        "pct_con_entidad_secundaria": round(100 * con_entidad_sec / total, 2),
        "pct_con_fecha_baja": round(100 * con_fecha_baja / total, 2),
        "pct_clones_con_n_registro": (
            round(100 * clones_con_registro / marcados_clon, 2)
            if marcados_clon else None
        ),
        "nombres_repetidos_distintos": len(repetidos),
        "nombres_repetidos_top10": dict(
            Counter(repetidos).most_common(10)
        ),
        "pct_nombres_repetidos_filas": round(
            100 * sum(repetidos.values()) / total, 2
        ),
        "notice_ids_unicos": len(notice_id_counts),
        "filas_por_notice_id_repetido": sum(
            c - 1 for c in notice_id_counts.values() if c > 1
        ),
    }
    (out_dir / "census-t0.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
