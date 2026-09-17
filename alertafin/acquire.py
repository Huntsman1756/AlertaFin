"""Adquisicion G0 de la fuente CNMV (Paso 1).

- CACHE AGRESIVA: si el ultimo pull OK fue el mismo dia UTC y los bytes
  estan en el ByteStore, no se vuelve a pedir la red (max. 1 pull/dia en
  G0). `--reprocess` re-deriva el dataset desde los bytes cacheados sin
  red; `--force` fuerza un pull nuevo.
- Fallo de fuente (excepcion/HTTP != 200) -> estado SOURCE_UNAVAILABLE
  registrado; NUNCA se produce un dataset vacio.
- Cambio de esquema o payload no decodificable -> estado PARSE_FAILED
  registrado; el ultimo dataset valido se conserva intacto.
- Cada retrieval genera su propio evento de observacion (provenance), aun
  con bytes identicos.
- Se registra un probe del pull 'activo' (estado=actu) solo con hechos
  observables: HTTP status, tamano, sha256, filas fisicas. Sin atribuir
  semantica juridica.
"""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import requests

from alertafin import PARSER_VERSION, SOURCE_NAMESPACE, __version__
from alertafin.parser import ParseError
from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore, RetrievalLog

SOURCE_URL = (
    "https://www.cnmv.es/WebAPI/datospublicos/PaffNoAutorizadas?format=csv"
)
QUERY_PARAMS = {"format": "csv"}

# UA honesto: identifica el cliente y el proyecto. La fuente no exige
# emular un navegador (verificado 2026-09).
USER_AGENT = (
    f"alertafin/{__version__} "
    "(+https://github.com/Huntsman1756/AlertaFin)"
)

# Candidatos de pull activo. SOLO observables: se registra lo que responde
# el endpoint; decidir cual es 'el activo' es experimental, no dogma.
ACTIVE_PROBE_PARAMS = [
    {"format": "csv", "estado": "actu"},
    {"format": "csv", "situacion": "actu"},
    {"format": "csv", "estado": "V"},
    {"format": "csv", "vigentes": "true"},
]

EXIT_OK = 0
EXIT_SOURCE_UNAVAILABLE = 3
EXIT_PARSE_FAILED = 4


def fetch_bytes(url, params=None, timeout=60):
    resp = requests.get(url, params=params, timeout=timeout,
                        headers={"User-Agent": USER_AGENT})
    return resp.status_code, resp.content


def _as_day(value) -> date:
    """`today`: None -> hoy UTC; str ISO o date -> ese dia."""
    if value is None:
        return datetime.now(UTC).date()
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


def _now_iso(today=None):
    """Reloj de la corrida: con `today` fijado (tests) el instante simulado
    es el inicio de ese dia UTC; sin `today` es la hora real UTC."""
    if today is not None:
        return f"{_as_day(today).isoformat()}T00:00:00Z"
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _retrieved_day(iso: str):
    """Dia UTC de un retrieved_at '%Y-%m-%dT%H:%M:%SZ'; None si no parsea."""
    try:
        return datetime.strptime(iso or "", "%Y-%m-%dT%H:%M:%SZ").date()
    except ValueError:
        return None


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _notice_for_jsonl(n: dict) -> dict:
    out = dict(n)
    raw = out.pop("raw_row_bytes")
    out["raw_row_bytes_hex"] = raw.hex()
    return out


def run_acquisition(store: ByteStore, out_dir, today=None, force=False,
                    reprocess=False):
    out_dir = Path(out_dir)
    last_attempt = out_dir / "acquisition" / "last_attempt.json"
    log = RetrievalLog(out_dir / "provenance" / "retrievals.jsonl")

    # --- reprocess: estrictamente offline ---
    # Invariante: con reprocess=True fetch_bytes NO se ejecuta nunca. Si el
    # ultimo intento registro bytes utilizables en el ByteStore se
    # reprocesan; si no hay, error controlado sin tocar la red.
    if reprocess:
        prev = {}
        if last_attempt.exists():
            prev = json.loads(last_attempt.read_text(encoding="utf-8"))
        sha = prev.get("source_sha256")
        if sha and store.has(sha):
            try:
                return _process_bytes(
                    store.get(sha), sha, prev.get("retrieved_at"),
                    prev.get("retrieval_id"), store, log, out_dir,
                )
            except ParseError as exc:
                _write_json(last_attempt, {
                    **prev,
                    "status": "PARSE_FAILED",
                    "reprocess": True,
                    "checked_at": _now_iso(today),
                    "error": f"{type(exc).__name__}: {exc}",
                })
                return EXIT_PARSE_FAILED
        _write_json(last_attempt, {
            **prev,
            "status": "SOURCE_UNAVAILABLE",
            "reprocess": True,
            "checked_at": _now_iso(today),
            "error": "reprocess: no hay bytes cacheados utilizables",
        })
        return EXIT_SOURCE_UNAVAILABLE

    # --- cache agresiva ---
    if last_attempt.exists() and not force:
        prev = json.loads(last_attempt.read_text(encoding="utf-8"))
        # Max. 1 pull/dia: solo se reutiliza si el ultimo pull OK fue
        # hoy (UTC). retrieved_at no parseable -> fail-safe: nuevo pull.
        if (
            prev.get("status") == "OK"
            and prev.get("source_sha256")
            and store.has(prev["source_sha256"])
            and _retrieved_day(prev.get("retrieved_at")) == _as_day(today)
        ):
            _write_json(last_attempt, {**prev, "reused_cache": True,
                                       "checked_at": _now_iso(today)})
            return EXIT_OK

    # --- adquisicion full pull ---
    try:
        status, body = fetch_bytes(SOURCE_URL, params=QUERY_PARAMS)
    except Exception as exc:  # DNS, timeout, TLS, red...
        _write_json(last_attempt, {
            "status": "SOURCE_UNAVAILABLE",
            "source_url": SOURCE_URL,
            "query_params": QUERY_PARAMS,
            "retrieved_at": _now_iso(today),
            "error": f"{type(exc).__name__}: {exc}",
        })
        return EXIT_SOURCE_UNAVAILABLE

    retrieved_at = _now_iso(today)
    if status != 200:
        _write_json(last_attempt, {
            "status": "SOURCE_UNAVAILABLE",
            "source_url": SOURCE_URL,
            "query_params": QUERY_PARAMS,
            "retrieved_at": retrieved_at,
            "http_status": status,
        })
        return EXIT_SOURCE_UNAVAILABLE

    source_sha256 = store.put(body)
    event = log.append(
        source_url=SOURCE_URL,
        query_params=QUERY_PARAMS,
        retrieved_at=retrieved_at,
        http_status=status,
        source_sha256=source_sha256,
        size=len(body),
        note="full pull",
        source_namespace=SOURCE_NAMESPACE,
    )
    try:
        code = _process_bytes(body, source_sha256, retrieved_at,
                              event["retrieval_id"], store, log, out_dir)
    except ParseError as exc:
        # La fuente respondio pero cambio de formato: los bytes quedan
        # guardados como evidencia; el ultimo dataset valido se conserva.
        _write_json(last_attempt, {
            "status": "PARSE_FAILED",
            "source_url": SOURCE_URL,
            "query_params": QUERY_PARAMS,
            "retrieved_at": retrieved_at,
            "source_sha256": source_sha256,
            "retrieval_id": event["retrieval_id"],
            "error": f"{type(exc).__name__}: {exc}",
        })
        return EXIT_PARSE_FAILED
    _run_active_probe(store, log, out_dir, source_sha256, today=today)
    _write_json(last_attempt, {
        "status": "OK",
        "source_url": SOURCE_URL,
        "query_params": QUERY_PARAMS,
        "retrieved_at": retrieved_at,
        "source_sha256": source_sha256,
        "retrieval_id": event["retrieval_id"],
    })
    return code


def _process_bytes(body, source_sha256, retrieved_at, retrieval_id,
                   store, log, out_dir):
    """Parsea, enriquece y escribe el dataset a partir de bytes ya
    almacenados. Estrictamente offline y determinista: NUNCA ejecuta
    fetch_bytes; el probe del pull activo vive aparte."""
    out_dir = Path(out_dir)
    prov = {
        "source_url": SOURCE_URL,
        "query_params": QUERY_PARAMS,
        "retrieved_at": retrieved_at,
        "source_sha256": source_sha256,
        "http_status": 200,
        "retrieval_id": retrieval_id,
        "parser_version": PARSER_VERSION,
        "source_namespace": SOURCE_NAMESPACE,
    }
    res = enrich(body, provenance=prov)

    notices_path = out_dir / "normalized" / "notices.jsonl"
    notices_path.parent.mkdir(parents=True, exist_ok=True)
    with notices_path.open("w", encoding="utf-8") as fh:
        for n in res.notices:
            fh.write(json.dumps(_notice_for_jsonl(n), ensure_ascii=False) + "\n")

    _write_json(out_dir / "normalized" / "row_errors.json", res.row_errors)
    summary = {
        "status": "OK",
        "source_url": SOURCE_URL,
        "query_params": QUERY_PARAMS,
        "retrieved_at": retrieved_at,
        "source_sha256": source_sha256,
        "size": len(body),
        "encoding": res.encoding,
        "header": res.header,
        "parser_version": PARSER_VERSION,
        "total_rows": len(res.notices) + len(res.row_errors),
        "normalized_notices": len(res.notices),
        "unparseable_rows": len(res.row_errors),
        "notice_ids_unique": len({n["notice_id"] for n in res.notices}),
    }
    _write_json(out_dir / "normalized" / "summary.json", summary)
    return EXIT_OK


def _run_active_probe(store, log, out_dir, source_sha256, today=None):
    """Observaciones live del pull 'activo'. SOLO se invoca tras un full
    pull real; jamas desde el camino --reprocess."""
    out_dir = Path(out_dir)
    probe = []
    for params in ACTIVE_PROBE_PARAMS:
        try:
            p_status, p_body = fetch_bytes(SOURCE_URL, params=params)
            entry = {
                "query_params": params,
                "http_status": p_status,
                "size": len(p_body) if p_status == 200 else None,
                "sha256": None,
                "physical_lines": None,
                "equals_full_pull": False,
            }
            if p_status == 200:
                p_sha = store.put(p_body)
                entry["sha256"] = p_sha
                entry["physical_lines"] = p_body.count(b"\n")
                entry["equals_full_pull"] = p_sha == source_sha256
            log.append(
                source_url=SOURCE_URL,
                query_params=params,
                retrieved_at=_now_iso(today),
                http_status=p_status,
                source_sha256=entry["sha256"] or "",
                size=len(p_body),
                note="active pull probe",
            )
        except Exception as exc:
            entry = {"query_params": params, "error": f"{type(exc).__name__}: {exc}"}
        probe.append(entry)
    _write_json(out_dir / "acquisition" / "active_probe.json", probe)


if __name__ == "__main__":
    import sys
    code = run_acquisition(
        store=ByteStore(Path("g0/raw")),
        out_dir=Path("g0"),
        force="--force" in sys.argv,
        reprocess="--reprocess" in sys.argv,
    )
    sys.exit(code)
