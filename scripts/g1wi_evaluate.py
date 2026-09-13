"""G1-WI: evaluador congelado. Escribe `g1-wi/evaluation.json`.

NO EJECUTAR para fijar el veredicto hasta que se autorice el run final:
el commit de este script congela la mecanica; `evaluation.json` se
genera/publica como paso separado y auditable.

Entradas (todas congeladas):
- `g0/normalized/notices.jsonl`      CNMV rows
- `g1-wi/normalized/notices.jsonl`   DGSFP rows
- `g0/holdout-v2/evaluation.json`    evidencia CNMV (si fingerprint match)
- `g1-wi/eval/gold.json`             censo gold DGSFP
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.eval_g1wi import build_evaluation


def _load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def main() -> int:
    cnmv_rows = _load_jsonl(Path("g0/normalized/notices.jsonl"))
    dgsfp_rows = _load_jsonl(Path("g1-wi/normalized/notices.jsonl"))
    holdout = json.loads(
        Path("g0/holdout-v2/evaluation.json").read_text("utf-8"))
    gold = json.loads(Path("g1-wi/eval/gold.json").read_text("utf-8"))

    ev = build_evaluation(cnmv_rows, dgsfp_rows, holdout, gold)
    out = Path("g1-wi/evaluation.json")
    out.write_text(json.dumps(ev, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps({"verdict": ev["verdict"],
                      "gates": {k: v["status"]
                                for k, v in ev["gates"].items()}},
                     ensure_ascii=False, indent=2))
    return 0 if ev["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
