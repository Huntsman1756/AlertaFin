"""Identidad estable de WarningNotice.

notice_id = sha256(serializacion canonica de los campos de identidad).
record_version_id = sha256(bytes crudos de la fila).

Convenciones congeladas (G0):
- Serializacion canonica: JSON UTF-8, ensure_ascii=False, separadores (',',':'),
  claves en orden fijo IDENTITY_FIELDS, valores ausentes/vacios -> null.
- Observaciones y Fecha Baja NO forman parte de notice_id.
- No se usan contadores, indices de fila ni orden del CSV.
"""

import hashlib
import json

IDENTITY_FIELDS = [
    "source_namespace",
    "tipo_raw",
    "fecha_raw",
    "entidad_raw",
    "entidad_secundaria_raw",
    "codigo_regulador_raw",
    "pais_regulador_raw",
]

_FIELDS_SET = set(IDENTITY_FIELDS)


def canonical_bytes(fields: dict) -> bytes:
    """Serializa los campos de identidad de forma canonica.

    Los campos no pertenecientes a IDENTITY_FIELDS se ignoran (p.ej.
    observaciones_raw, fecha_baja_raw) para que no puedan afectar al hash.
    """
    payload = {
        key: (fields.get(key) or None)
        for key in IDENTITY_FIELDS
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def notice_id(fields: dict) -> str:
    """Identificador estable e idempotente del aviso."""
    return hashlib.sha256(canonical_bytes(fields)).hexdigest()


def record_version_id(raw_row_bytes: bytes) -> str:
    """Version exacta de la fila cruda (framing incluido, terminador excluido)."""
    return hashlib.sha256(raw_row_bytes).hexdigest()


def identity_view(fields: dict) -> dict:
    """Devuelve solo los campos de identidad, en orden fijo."""
    return {key: (fields.get(key) or None) for key in IDENTITY_FIELDS}


__all__ = [
    "IDENTITY_FIELDS",
    "canonical_bytes",
    "identity_view",
    "notice_id",
    "record_version_id",
]
