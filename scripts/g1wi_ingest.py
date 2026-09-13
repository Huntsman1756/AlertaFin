"""G1-WI.B: ingesta DGSFP desde el snapshot congelado del probe.

Lee `g1-wi/probe/raw/{unauth,webs}.html`, verifica su sha256 contra
`g1-wi/probe/snapshot.json` (fuente congelada; aborta si difiere), parsea
con `alertafin.dgsfp` y escribe:

- `g1-wi/normalized/notices.jsonl`
- `g1-wi/normalized/summary.json`

Sin requests de red: la fuente es el snapshot inmutable del probe.
"""

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.dgsfp import (
    NS_PAGINAS,
    NS_SUJETOS,
    PARSER_VERSION_DGSFP,
    _notice_for_jsonl,
    parse_paginas,
    parse_sujetos,
)

PROBE = Path("g1-wi/probe")
SNAPSHOT = PROBE / "snapshot.json"
RETRIEVALS = PROBE / "retrievals.jsonl"
OUT = Path("g1-wi/normalized")

SOURCES = [
    ("raw/unauth.html", NS_SUJETOS, parse_sujetos,
     "https://dgsfp.mineco.gob.es/es/Consumidor/RegistrosPublicos/Paginas/No-autorizadas.aspx"),
    ("raw/webs.html", NS_PAGINAS, parse_paginas,
     "https://dgsfp.mineco.gob.es/es/Paginas/0-11-Paginas-web-fraudulentas.aspx"),
]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _retrieval_for(url: str) -> dict:
    for line in RETRIEVALS.read_text("utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("url") == url and "fetch 1" in ev.get("purpose", ""):
            return ev
    raise SystemExit(f"FALTA provenance del snapshot para {url}")


def main() -> int:
    snapshot = json.loads(SNAPSHOT.read_text("utf-8"))
    notices = []
    per_source = {}
    for rel, ns, parser, url in SOURCES:
        raw = (PROBE / rel).read_bytes()
        sha = _sha256_file(PROBE / rel)
        expected = snapshot["files"][rel]["sha256"]
        if sha != expected:
            print(f"ABORTADO: {rel} sha256 != snapshot congelado")
            print(f"  esperado: {expected}")
            print(f"  actual  : {sha}")
            return 2
        ev = _retrieval_for(url)
        prov = {
            "source_url": url,
            "retrieved_at": ev["retrieved_at"],
            "http_status": ev["http_status"],
            "source_sha256": sha,
            "retrieval_id": None,
            "parser_version": PARSER_VERSION_DGSFP,
            "source_namespace": ns,
        }
        res = parser(raw, provenance=prov)
        per_source[ns] = {
            "records": len(res.notices),
            "row_errors": len(res.row_errors),
            "notice_ids_unique": len({n["notice_id"] for n in res.notices}),
        }
        notices.extend(res.notices)

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "notices.jsonl").open("w", encoding="utf-8") as fh:
        for n in notices:
            fh.write(json.dumps(_notice_for_jsonl(n), ensure_ascii=False)
                     + "\n")

    summary = {
        "status": "OK",
        "parser_version": PARSER_VERSION_DGSFP,
        "sources": per_source,
        "total_notices": len(notices),
        "notice_ids_unique": len({n["notice_id"] for n in notices}),
        "clone_detected": sum(1 for n in notices
                              if n["clone"]["clone_detected"]),
        "domains_total": sum(len(n["domains"]) for n in notices),
        "warning_dates_present": sum(1 for n in notices
                                     if n["warning_date"] is not None),
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
