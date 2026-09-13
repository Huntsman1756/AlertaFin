"""Adquisicion G0 de la fuente CNMV (Paso 1).

- CACHE AGRESIVA: si el ultimo intento fue OK y los bytes ya estan en el
  ByteStore, no se vuelve a pedir la red (max. 1 pull/dia en G0).
- Fallo de fuente (excepcion/HTTP != 200) -> estado SOURCE_UNAVAILABLE
  registrado; NUNCA se produce un dataset vacio.
- Cada retrieval genera su propio evento de observacion (provenance), aun
  con bytes identicos.
- Se registra un probe del pull 'activo' (estado=actu) solo con hechos
  observables: HTTP status, tamano, sha256, filas fisicas. Sin atribuir
  semantica juridica.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import requests

from alertafin import SOURCE_NAMESPACE, PARSER_VERSION
from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore, RetrievalLog

SOURCE_URL = (
    "https://www.cnmv.es/WebAPI/datospublicos/PaffNoAutorizadas?format=csv"
)
QUERY_PARAMS = {"format": "csv"}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
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


def fetch_bytes(url, params=None, timeout=60):
    resp = requests.get(url, params=params, timeout=timeout,
                        headers={"User-Agent": USER_AGENT})
    return resp.status_code, resp.content


def _now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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

    # --- cache agresiva ---
    if last_attempt.exists() and (not force or reprocess):
        prev = json.loads(last_attempt.read_text(encoding="utf-8"))
        if (
            prev.get("status") == "OK"
            and prev.get("source_sha256")
            and store.has(prev["source_sha256"])
        ):
            if reprocess:
                return _process_bytes(
                    store.get(prev["source_sha256"]),
                    prev["source_sha256"], prev["retrieved_at"],
                    prev.get("retrieval_id"), store, log, out_dir,
                )
            _write_json(last_attempt, {**prev, "reused_cache": True,
                                       "checked_at": _now_iso()})
            return EXIT_OK

    # --- adquisicion full pull ---
    try:
        status, body = fetch_bytes(SOURCE_URL, params=QUERY_PARAMS)
    except Exception as exc:  # DNS, timeout, TLS, red...
        _write_json(last_attempt, {
            "status": "SOURCE_UNAVAILABLE",
            "source_url": SOURCE_URL,
            "query_params": QUERY_PARAMS,
            "retrieved_at": _now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
        })
        return EXIT_SOURCE_UNAVAILABLE

    retrieved_at = _now_iso()
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
    code = _process_bytes(body, source_sha256, retrieved_at,
                          event["retrieval_id"], store, log, out_dir)
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
    """Parsea, enriquece y escribe el dataset a partir de bytes ya almacenados."""
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

    # --- probe del pull activo (solo observables) ---
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
                retrieved_at=_now_iso(),
                http_status=p_status,
                source_sha256=entry["sha256"] or "",
                size=len(p_body),
                note="active pull probe",
            )
        except Exception as exc:
            entry = {"query_params": params, "error": f"{type(exc).__name__}: {exc}"}
        probe.append(entry)
    _write_json(out_dir / "acquisition" / "active_probe.json", probe)
    return EXIT_OK


if __name__ == "__main__":
    import sys
    code = run_acquisition(
        store=ByteStore(Path("g0/raw")),
        out_dir=Path("g0"),
        force="--force" in sys.argv,
        reprocess="--reprocess" in sys.argv,
    )
    sys.exit(code)
