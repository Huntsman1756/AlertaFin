"""CLI de AlertaFin (G0).

Estados: WARNED | NO_WARNING_FOUND | AMBIGUOUS | SOURCE_UNAVAILABLE
Exit codes: 0 ok (cualquier estado resuelto), 2 uso incorrecto,
3 SOURCE_UNAVAILABLE (dataset ausente, vacio, ilegible o corrupto:
un fallo de fuente nunca es NO_WARNING_FOUND).

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

DEFAULT_DATASET = Path("g0/normalized/notices.jsonl")


class DatasetError(Exception):
    """El dataset local existe pero no se puede leer o no es JSONL valido."""


def load_notices(dataset_path: Path):
    """None si el dataset no existe; DatasetError si existe pero falla."""
    dataset_path = Path(dataset_path)
    if not dataset_path.exists():
        return None
    notices = []
    try:
        with dataset_path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    notice = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DatasetError(
                        f"{dataset_path}:{lineno}: JSON invalido: {exc.msg}"
                    ) from exc
                if not isinstance(notice, dict):
                    raise DatasetError(
                        f"{dataset_path}:{lineno}: la linea no es un objeto "
                        "JSON de notice"
                    )
                notices.append(notice)
    except OSError as exc:
        raise DatasetError(f"{dataset_path}: {exc}") from exc
    if not notices:
        # Un indice de advertencias vacio no puede responder con
        # NO_WARNING_FOUND de forma honesta: se reporta como fuente
        # no disponible.
        raise DatasetError(f"dataset vacio: {dataset_path}")
    return notices


def build_index(dataset_path: Path):
    notices = load_notices(dataset_path)
    if notices is None:
        return None
    return SearchIndex.build(notices)


def _emit(payload: dict):
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _load_or_report(args):
    """Devuelve notices o emite SOURCE_UNAVAILABLE y devuelve None."""
    try:
        notices = load_notices(args.dataset)
    except DatasetError as exc:
        _emit({"status": "SOURCE_UNAVAILABLE", "reason": str(exc)})
        return None
    if notices is None:
        _emit({"status": "SOURCE_UNAVAILABLE",
               "reason": f"dataset not found: {args.dataset}"})
        return None
    return notices


def cmd_check(args):
    notices = _load_or_report(args)
    if notices is None:
        return EXIT_SOURCE_UNAVAILABLE
    res = check(args.query, SearchIndex.build(notices))
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
    if args.days < 0:
        print("error: --days debe ser >= 0", file=sys.stderr)
        return EXIT_USAGE
    if args.today:
        try:
            today = date.fromisoformat(args.today)
        except ValueError:
            print(f"error: --today no es fecha ISO: {args.today!r}",
                  file=sys.stderr)
            return EXIT_USAGE
    else:
        today = date.today()
    notices = _load_or_report(args)
    if notices is None:
        return EXIT_SOURCE_UNAVAILABLE
    cutoff = today - timedelta(days=args.days)
    recent = []
    skipped_invalid_fecha = 0
    for n in notices:
        if not n.get("fecha"):
            continue
        try:
            fecha = date.fromisoformat(n["fecha"])
        except (ValueError, TypeError):
            skipped_invalid_fecha += 1
            continue
        if fecha >= cutoff:
            recent.append(n)
    recent.sort(key=lambda n: n["fecha"], reverse=True)
    payload = {"status": "OK", "days": args.days, "from": cutoff.isoformat(),
               "notices": [{"notice_id": n["notice_id"], "fecha": n["fecha"],
                            "entidad_raw": n["entidad_raw"]}
                           for n in recent]}
    if skipped_invalid_fecha:
        payload["skipped_invalid_fecha"] = skipped_invalid_fecha
    _emit(payload)
    return EXIT_OK


def cmd_clones(args):
    notices = _load_or_report(args)
    if notices is None:
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
    notices = _load_or_report(args)
    if notices is None:
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
        default=DEFAULT_DATASET,
        help="Ruta al dataset de notices normalizados (JSONL).",
    )

    def add_dataset(p):
        # SUPPRESS: si el usuario ya paso --dataset antes del subcomando,
        # el default del subparser NO debe pisar el valor (argparse si
        # sobrescribe el namespace con los defaults del subparser).
        p.add_argument("--dataset", type=Path,
                       default=argparse.SUPPRESS,
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
