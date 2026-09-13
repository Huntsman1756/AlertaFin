"""CLI de AlertaFin (G0).

Estados: WARNED | NO_WARNING_FOUND | AMBIGUOUS | SOURCE_UNAVAILABLE
Exit codes: 0 ok (cualquier estado resuelto), 2 uso incorrecto,
3 SOURCE_UNAVAILABLE.

Salida: JSON en stdout. Sin colores, auditable.
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from alertafin import __version__
from alertafin.search import SearchIndex, check

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_SOURCE_UNAVAILABLE = 3


def load_notices(dataset_path: Path):
    if not dataset_path.exists():
        return None
    notices = []
    with dataset_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                notices.append(json.loads(line))
    return notices


def build_index(dataset_path: Path):
    notices = load_notices(dataset_path)
    if notices is None:
        return None
    return SearchIndex.build(notices)


def _emit(payload: dict):
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def cmd_check(args):
    index = build_index(args.dataset)
    if index is None:
        _emit({"status": "SOURCE_UNAVAILABLE", "query": args.query,
               "reason": f"dataset not found: {args.dataset}"})
        return EXIT_SOURCE_UNAVAILABLE
    res = check(args.query, index)
    payload = {"status": res.status, "query": res.query}
    if res.status == "WARNED":
        payload["notices"] = [
            {
                "notice_id": n["notice_id"],
                "entidad_raw": n["entidad_raw"],
                "fecha": n.get("fecha"),
                "domains": [
                    d["host_normalized"] for d in n.get("domains") or []
                ],
            }
            for n in res.notices
        ]
    elif res.status == "AMBIGUOUS":
        payload["subjects"] = res.subjects
        payload["notices"] = [
            {"notice_id": n["notice_id"], "entidad_raw": n["entidad_raw"]}
            for n in res.notices
        ]
    _emit(payload)
    return EXIT_OK


def cmd_recent(args):
    notices = load_notices(args.dataset)
    if notices is None:
        _emit({"status": "SOURCE_UNAVAILABLE",
               "reason": f"dataset not found: {args.dataset}"})
        return EXIT_SOURCE_UNAVAILABLE
    today = date.fromisoformat(args.today) if args.today else date.today()
    cutoff = today - timedelta(days=args.days)
    recent = [n for n in notices if n.get("fecha") and date.fromisoformat(n["fecha"]) >= cutoff]
    recent.sort(key=lambda n: n["fecha"], reverse=True)
    _emit({"status": "OK", "days": args.days, "from": cutoff.isoformat(),
           "notices": [{"notice_id": n["notice_id"], "fecha": n["fecha"],
                        "entidad_raw": n["entidad_raw"]} for n in recent]})
    return EXIT_OK


def cmd_clones(args):
    notices = load_notices(args.dataset)
    if notices is None:
        _emit({"status": "SOURCE_UNAVAILABLE",
               "reason": f"dataset not found: {args.dataset}"})
        return EXIT_SOURCE_UNAVAILABLE
    clones = [
        {
            "notice_id": n["notice_id"],
            "entidad_raw": n["entidad_raw"],
            "relation_status": (n.get("clone") or {}).get("relation_status"),
            "clone_target_raw": (n.get("clone") or {}).get("clone_target_raw"),
            "clone_target_registry_number": (n.get("clone") or {}).get(
                "clone_target_registry_number"
            ),
        }
        for n in notices
        if (n.get("clone") or {}).get("clone_detected")
        and (n.get("clone") or {}).get("relation_status") in (
            "EXPLICIT_SOURCE", "PARSED_EXPLICIT"
        )
    ]
    _emit({"status": "OK", "clones": clones})
    return EXIT_OK


def cmd_show(args):
    notices = load_notices(args.dataset)
    if notices is None:
        _emit({"status": "SOURCE_UNAVAILABLE",
               "reason": f"dataset not found: {args.dataset}"})
        return EXIT_SOURCE_UNAVAILABLE
    index = SearchIndex.build(notices)
    n = index.by_notice_id(args.notice_id)
    if n is None:
        _emit({"status": "NOT_FOUND", "notice_id": args.notice_id})
        return EXIT_USAGE
    _emit({"status": "OK", "notice": n})
    return EXIT_OK


def build_parser():
    parser = argparse.ArgumentParser(
        prog="alertafin",
        description=(
            "Indice auditable de advertencias financieras oficiales (G0: CNMV)."
        ),
    )
    parser.add_argument("--version", action="version",
                        version=f"alertafin {__version__}")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("g0/normalized/notices.jsonl"),
        help="Ruta al dataset de notices normalizados (JSONL).",
    )

    def add_dataset(p):
        p.add_argument("--dataset", type=Path,
                       default=Path("g0/normalized/notices.jsonl"),
                       help="Ruta al dataset de notices (JSONL).")
        return p

    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Consulta un nombre/dominio/marca.")
    p_check.add_argument("query")
    add_dataset(p_check)
    p_check.set_defaults(func=cmd_check)

    p_recent = sub.add_parser("recent", help="Avisos de los ultimos N dias.")
    p_recent.add_argument("--days", type=int, default=30)
    p_recent.add_argument("--today", default=None,
                          help="Fecha de referencia ISO (para tests).")
    add_dataset(p_recent)
    p_recent.set_defaults(func=cmd_recent)

    p_clones = sub.add_parser("clones", help="Relaciones CLONE_OF explicitas.")
    add_dataset(p_clones)
    p_clones.set_defaults(func=cmd_clones)

    p_show = sub.add_parser("show", help="Detalle completo de un notice-id.")
    p_show.add_argument("notice_id")
    add_dataset(p_show)
    p_show.set_defaults(func=cmd_show)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
