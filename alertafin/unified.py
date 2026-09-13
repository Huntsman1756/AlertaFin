"""G1-WI.C: modelo unificado multifuente (vista derivada v0.2).

`notice_id` = WarningNotice semantico. Las filas raw de cada fuente se
agrupan por `notice_id` en `source_occurrences[1..N]`:

- CNMV: 10.368 filas -> 10.361 notices (7 grupos x2: 5 byte-identicos,
  2 versionados con Observaciones distintas — mismo notice_id porque
  Observaciones no forma parte de la identidad, `identity.py`).
- DGSFP: 97 + 10 filas -> 87 + 10 notices (10 grupos duplicados).

`domains`/`clone` NO son escalares a nivel notice: dos versiones del
mismo aviso pueden afirmar cosas distintas (p.ej. TOLOT-EPARGNE.FR tiene
dos targets legitimos distintos). Se exponen como colecciones
provenance-backed:

- `domain_assertions[]`: una por dominio x ocurrencia.
- `clone_evidence[]`: una por afirmacion explicita de clon x ocurrencia.

Nunca se elige arbitrariamente entre versiones: la evidencia distinta
coexiste y cada pieza referencia su `source_occurrence_id`.

La cobertura de fuente se mide sobre ocurrencias, no notices.

Semantica de consulta (`warning_status` agregado, congelada en
`g1-wi/preregistration.md`):

    cualquier fuente WARNED            -> WARNED
        (+ coverage_complete=false si otra fuente no respondio)
    ninguna WARNED y alguna
        SOURCE_UNAVAILABLE             -> SOURCE_UNAVAILABLE
    todas disponibles y alguna
        AMBIGUOUS                      -> AMBIGUOUS
    todas disponibles, ninguna warned
        ni ambiguous                   -> NO_WARNING_FOUND
"""

import hashlib
import json

from alertafin.identity import identity_view
from alertafin.search import SearchIndex, check

NS_CNMV = "cnmv.webapi.paff_no_autorizadas"
NS_SUJETOS = "dgsfp.sujetos_no_autorizados"
NS_PAGINAS = "dgsfp.paginas_web_fraudulentas"

SOURCE_ORDER = ["CNMV", "DGSFP_UNAUTHORISED", "DGSFP_FRAUDULENT_WEBS"]

SOURCE_BY_NAMESPACE = {
    NS_CNMV: "CNMV",
    NS_SUJETOS: "DGSFP_UNAUTHORISED",
    NS_PAGINAS: "DGSFP_FRAUDULENT_WEBS",
}
AUTHORITY_BY_NAMESPACE = {
    NS_CNMV: "CNMV",
    NS_SUJETOS: "DGSFP",
    NS_PAGINAS: "DGSFP",
}
SOURCE_TYPE_BY_NAMESPACE = {
    NS_CNMV: "ENTIDAD_NO_AUTORIZADA",
    NS_SUJETOS: "SUJETO_NO_AUTORIZADO",
    NS_PAGINAS: "PAGINA_WEB_FRAUDULENTA",
}

_DGSFP_IDENTITY_KEYS = [
    "source_namespace", "source_type", "entidad_raw", "url_raw",
    "section",
]

# Campos que ascienden al nivel notice; el resto de la fila queda en la
# ocurrencia como evidencia raw versionable.
_LIFTED = {"notice_id", "domains", "clone"}


def _canon_sha256(payload: dict) -> str:
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _occurrence_id_cnmv(row: dict) -> str:
    """Identidad determinista de la ocurrencia fisica CNMV: fila raw +
    posicion fisica en la fuente (row_number). CNMV no tiene secciones."""
    return _canon_sha256({
        "record_version_id": row["record_version_id"],
        "section": None,
        "occurrence_index": row["row_number"],
    })


def _to_occurrence(row: dict) -> dict:
    occ = {k: v for k, v in row.items() if k not in _LIFTED}
    raw = occ.pop("raw_row_bytes", None)
    if raw is not None:
        occ["raw_row_bytes_hex"] = (
            raw.hex() if isinstance(raw, (bytes, bytearray)) else raw)
    if not occ.get("source_occurrence_id"):
        occ["source_occurrence_id"] = _occurrence_id_cnmv(row)
    return occ


def _identity_fields(row: dict) -> dict:
    if row["source_namespace"] == NS_CNMV:
        return identity_view(row)
    return {k: (row.get(k) or None) for k in _DGSFP_IDENTITY_KEYS}


def _warning_date(row: dict):
    if row["source_namespace"] == NS_CNMV:
        if row.get("fecha"):
            return row["fecha"], "PARSED"
        return None, "UNPARSEABLE" if row.get("fecha_raw") else "ABSENT"
    return row.get("warning_date"), row.get("warning_date_status") or "ABSENT"


def build_notices(rows) -> list:
    """Agrupa filas raw-level (CNMV o DGSFP) en WarningNotice semantico.

    rows: iterable de dicts tal como salen de `pipeline.enrich` /
    `dgsfp.parse_*` / los JSONL normalizados. Orden de salida =
    orden de primera aparicion; ocurrencias en orden de fila.
    """
    groups = {}
    for row in rows:
        groups.setdefault(row["notice_id"], []).append(row)

    notices = []
    for nid, group in groups.items():
        first = group[0]
        ns = first["source_namespace"]
        occs = [_to_occurrence(r) for r in group]

        domain_assertions = []
        clone_evidence = []
        for r, occ in zip(group, occs):
            for d in r.get("domains") or []:
                domain_assertions.append({
                    "host_normalized": d["host_normalized"],
                    "raw": d.get("raw"),
                    "source_field": d.get("source_field"),
                    "source_occurrence_id": occ["source_occurrence_id"],
                })
            c = r.get("clone") or {}
            if c.get("clone_detected"):
                clone_evidence.append({
                    "clone_target_raw": c.get("clone_target_raw"),
                    "clone_target_registry_number":
                        c.get("clone_target_registry_number"),
                    "clone_markers": c.get("clone_markers") or [],
                    "relation_status": c.get("relation_status"),
                    "source_occurrence_id": occ["source_occurrence_id"],
                })

        warning_date, warning_date_status = _warning_date(first)
        notices.append({
            "notice_id": nid,
            "source": SOURCE_BY_NAMESPACE[ns],
            "source_namespace": ns,
            "source_type": SOURCE_TYPE_BY_NAMESPACE[ns],
            "authority": AUTHORITY_BY_NAMESPACE[ns],
            "identity_fields": _identity_fields(first),
            "entidad_raw": first.get("entidad_raw"),
            "section": first.get("section"),
            "warning_date": warning_date,
            "warning_date_status": warning_date_status,
            "domain_assertions": domain_assertions,
            "clone_evidence": clone_evidence,
            "source_occurrences": occs,
        })
    return notices


def _search_view(notice: dict) -> dict:
    return {
        "notice_id": notice["notice_id"],
        "entidad_raw": notice.get("entidad_raw"),
        "domains": [{"host_normalized": a["host_normalized"]}
                    for a in notice["domain_assertions"]],
        "_notice": notice,
    }


class MultiSourceIndex:
    """Un SearchIndex por fuente; `None` = fuente no respondio."""

    def __init__(self, per_source: dict):
        self.per_source = per_source

    @classmethod
    def build(cls, notices) -> "MultiSourceIndex":
        by_source = {}
        for n in notices:
            by_source.setdefault(n["source"], []).append(_search_view(n))
        return cls({key: (SearchIndex.build(by_source[key])
                          if key in by_source else None)
                    for key in SOURCE_ORDER})


def aggregate_status(source_status: dict):
    """Precedencia congelada. Devuelve (status, coverage_complete)."""
    statuses = list(source_status.values())
    coverage_complete = "SOURCE_UNAVAILABLE" not in statuses
    if "WARNED" in statuses:
        return "WARNED", coverage_complete
    if not coverage_complete:
        return "SOURCE_UNAVAILABLE", False
    if "AMBIGUOUS" in statuses:
        return "AMBIGUOUS", True
    return "NO_WARNING_FOUND", True


class MultiCheckResult:
    def __init__(self, status, query, source_status, notices,
                 coverage_complete):
        self.status = status
        self.query = query
        self.source_status = source_status
        self.notices = notices
        self.coverage_complete = coverage_complete


def check_multi(query: str, index: MultiSourceIndex) -> MultiCheckResult:
    source_status = {}
    hits = []
    for key in SOURCE_ORDER:
        idx = index.per_source.get(key)
        if idx is None:
            source_status[key] = "SOURCE_UNAVAILABLE"
            continue
        res = check(query, idx)
        source_status[key] = res.status
        hits.extend(r["_notice"] for r in res.notices)

    status, coverage_complete = aggregate_status(source_status)
    return MultiCheckResult(
        status=status, query=query, source_status=source_status,
        notices=hits, coverage_complete=coverage_complete)


def notice_for_jsonl(notice: dict) -> dict:
    return notice


__all__ = [
    "NS_CNMV", "NS_SUJETOS", "NS_PAGINAS",
    "SOURCE_ORDER", "SOURCE_BY_NAMESPACE",
    "MultiSourceIndex", "MultiCheckResult",
    "aggregate_status", "build_notices", "check_multi",
    "notice_for_jsonl",
]
