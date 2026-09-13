"""G1-WI.C: construye la vista unificada multifuente (WarningNotice).

Lee las filas normalizadas congeladas:
- `g0/normalized/notices.jsonl`   (CNMV, 10.368 filas)
- `g1-wi/normalized/notices.jsonl` (DGSFP, 97 + 10 filas)

y escribe:
- `g1-wi/normalized/warning_notices.jsonl`
- `g1-wi/normalized/unified_summary.json`

Modelo: `alertafin/unified.py`. Vista derivada v0.2 — no modifica los
artefactos G0.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.unified import (
    SOURCE_ORDER,
    build_notices,
    notice_for_jsonl,
)

CNMV = Path("g0/normalized/notices.jsonl")
DGSFP = Path("g1-wi/normalized/notices.jsonl")
OUT = Path("g1-wi/normalized")


def _load(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main() -> int:
    rows = _load(CNMV) + _load(DGSFP)
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
