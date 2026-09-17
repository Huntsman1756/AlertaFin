"""Parser determinista del CSV CNMV PaffNoAutorizadas.

- RFC4180 a nivel de bytes: captura raw_row_bytes exactos por fila,
  incluyendo newlines embebidos en campos entrecomillados.
- Conserva TODOS los campos raw (incluidos espacios internos y padding).
- Fechas: Fecha=dd/mm/yyyy; Fecha Baja=dd/mm/yyyy H:MM:SS. Invalidas ->
  row_error (nunca silencio).
- Filas con numero de columnas incorrecto -> row_error, no se descartan.
"""

import hashlib
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import datetime

from alertafin import PARSER_VERSION, SOURCE_NAMESPACE
from alertafin.identity import notice_id

EXPECTED_HEADER = [
    "Tipo",
    "Fecha",
    "Entidad",
    "Entidad Secundaria",
    "C\u00f3digo regulador",
    "Pa\u00eds regulador",
    "C\u00f3digo pa\u00eds regulador",
    "Observaciones",
    "Fecha Baja",
]

_COLUMN_MAP = [
    ("tipo_raw", "Tipo"),
    ("fecha_raw", "Fecha"),
    ("entidad_raw", "Entidad"),
    ("entidad_secundaria_raw", "Entidad Secundaria"),
    ("codigo_regulador_raw", "C\u00f3digo regulador"),
    ("pais_regulador_raw", "Pa\u00eds regulador"),
    ("pais_codigo_regulador_raw", "C\u00f3digo pa\u00eds regulador"),
    ("observaciones_raw", "Observaciones"),
    ("fecha_baja_raw", "Fecha Baja"),
]


class ParseError(Exception):
    pass


@dataclass
class ParseResult:
    encoding: str
    header: list
    notices: list = dc_field(default_factory=list)
    row_errors: list = dc_field(default_factory=list)


# ---------------------------------------------------------------------------
# Lectura fisica de filas (framing exacto por fila)
# ---------------------------------------------------------------------------

def _split_records(raw: bytes):
    """Divide el CSV en registros fisicos RFC4180.

    Devuelve lista de (campos_valores_decodificados, raw_bytes_sin_terminador).
    Los valores no incluyen las comillas envolventes; raw_bytes conserva la
    fila byte a byte (comillas y terminador excluidos de raw_row_bytes).
    """
    records = []
    buf = bytearray()
    fields = []
    cur = bytearray()
    in_quotes = False
    i = 0
    n = len(raw)

    while i < n:
        ch = raw[i:i + 1]
        buf.extend(ch)
        if in_quotes:
            if ch == b'"':
                if raw[i + 1:i + 2] == b'"':
                    cur.extend(b'"')
                    buf.extend(b'"')
                    i += 1
                else:
                    in_quotes = False
            else:
                cur.extend(ch)
        else:
            if ch == b',':
                fields.append(bytes(cur))
                cur = bytearray()
            elif ch == b'\r' and raw[i + 1:i + 2] == b'\n':
                pass  # terminador CRLF: el \n procesa el fin de registro
            elif ch == b'\n':
                end = len(buf) - 2 if buf.endswith(b'\r\n') else len(buf) - 1
                fields.append(bytes(cur))
                records.append((fields, bytes(buf[:end])))
                fields = []
                cur = bytearray()
                buf = bytearray()
            elif ch == b'"' and not cur:
                in_quotes = True
            else:
                cur.extend(ch)
        i += 1

    if buf or fields or cur:
        end = len(buf)
        while end > 0 and buf[end - 1:end] in (b'\n', b'\r'):
            end -= 1
        fields.append(bytes(cur))
        records.append((fields, bytes(buf[:end])))
    return records


def _decode(raw: bytes):
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:], "utf-8-sig"
    return raw, "utf-8"


def _parse_date(value):
    """dd/mm/yyyy -> ISO date string. None para vacio. ValueError si invalido."""
    v = (value or "").strip()
    if not v:
        return None
    return datetime.strptime(v, "%d/%m/%Y").date().isoformat()


def _parse_datetime(value):
    """dd/mm/yyyy H:MM:SS (hora opcional) -> ISO datetime. ValueError si invalido."""
    v = (value or "").strip()
    if not v:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(v, fmt).isoformat()
        except ValueError:
            continue
    raise ValueError(f"unsupported datetime format: {v!r}")


def parse_csv(raw: bytes, provenance: dict | None = None) -> ParseResult:
    body, encoding = _decode(raw)
    try:
        # Fail-fast: valida la decodificabilidad antes de procesar filas;
        # los decodes por campo mas abajo quedan garantizados.
        body.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ParseError(f"payload no decodificable como {encoding}: {exc}") \
            from exc

    records = _split_records(body)
    if not records:
        raise ParseError("empty source")

    header_fields, _header_raw = records[0]
    header = [h.decode(encoding) for h in header_fields]
    if [h.strip() for h in header] != EXPECTED_HEADER:
        raise ParseError(
            f"schema change: header {header!r} != expected {EXPECTED_HEADER!r}"
        )

    prov = dict(provenance or {})
    prov.setdefault("parser_version", PARSER_VERSION)
    prov.setdefault("source_namespace", SOURCE_NAMESPACE)

    result = ParseResult(encoding=encoding, header=header)
    for row_number, (fields, raw_bytes) in enumerate(records[1:], start=1):
        decoded = [f.decode(encoding) for f in fields]
        base_err = {
            "row_number": row_number,
            "raw_row_bytes": raw_bytes,
            "record_version_id": hashlib.sha256(raw_bytes).hexdigest(),
        }
        if len(decoded) != len(EXPECTED_HEADER):
            result.row_errors.append({**base_err, "error": "COLUMN_COUNT",
                                      "got_columns": len(decoded)})
            continue
        record = dict(zip([name for name, _ in _COLUMN_MAP], decoded,
                          strict=True))
        # Convencion: campo vacio -> None. Los valores no vacios se conservan
        # byte a byte (incluido padding como 'NOAUTO    ').
        record = {k: (v if v != "" else None) for k, v in record.items()}
        try:
            record["fecha"] = _parse_date(record["fecha_raw"])
            record["fecha_baja"] = _parse_datetime(record["fecha_baja_raw"])
        except ValueError as exc:
            result.row_errors.append({**base_err, "error": "INVALID_DATE",
                                      "detail": str(exc)})
            continue

        identity = {
            "source_namespace": SOURCE_NAMESPACE,
            "tipo_raw": record["tipo_raw"],
            "fecha_raw": record["fecha_raw"],
            "entidad_raw": record["entidad_raw"],
            "entidad_secundaria_raw": record["entidad_secundaria_raw"],
            "codigo_regulador_raw": record["codigo_regulador_raw"],
            "pais_regulador_raw": record["pais_regulador_raw"],
        }
        n = {
            "notice_id": notice_id(identity),
            "record_version_id": base_err["record_version_id"],
            "row_number": row_number,
            "raw_row_bytes": raw_bytes,
            **record,
            **identity,
            "provenance": prov,
        }
        result.notices.append(n)
    return result
