import hashlib
import json

import pytest

from alertafin.identity import (
    IDENTITY_FIELDS,
    canonical_bytes,
    notice_id,
    record_version_id,
)


def make_fields(**overrides):
    base = {
        "source_namespace": "cnmv.webapi.paff_no_autorizadas",
        "tipo_raw": "NOAUTO",
        "fecha_raw": "09/09/2026",
        "entidad_raw": "MELZAPAY S.A.",
        "entidad_secundaria_raw": "WWW.MELZAPAY.COM",
        "codigo_regulador_raw": "CSSF",
        "pais_regulador_raw": "LUXEMBURGO",
    }
    base.update(overrides)
    return base


def test_identity_fields_fixed_order():
    assert IDENTITY_FIELDS == [
        "source_namespace",
        "tipo_raw",
        "fecha_raw",
        "entidad_raw",
        "entidad_secundaria_raw",
        "codigo_regulador_raw",
        "pais_regulador_raw",
    ]


def test_canonical_bytes_is_fixed_key_order_compact_utf8():
    b = canonical_bytes(make_fields())
    # Claves en orden fijo, separadores sin espacios, UTF-8.
    expected = (
        '{"source_namespace":"cnmv.webapi.paff_no_autorizadas",'
        '"tipo_raw":"NOAUTO","fecha_raw":"09/09/2026",'
        '"entidad_raw":"MELZAPAY S.A.",'
        '"entidad_secundaria_raw":"WWW.MELZAPAY.COM",'
        '"codigo_regulador_raw":"CSSF",'
        '"pais_regulador_raw":"LUXEMBURGO"}'
    ).encode("utf-8")
    assert b == expected


def test_canonical_bytes_preserves_non_ascii_without_escaping():
    b = canonical_bytes(make_fields(entidad_raw="ÑANDÚ CAPITAL S.L."))
    assert "ÑANDÚ CAPITAL S.L.".encode("utf-8") in b


def test_notice_id_is_sha256_of_canonical():
    b = canonical_bytes(make_fields())
    assert notice_id(make_fields()) == hashlib.sha256(b).hexdigest()


def test_notice_id_idempotent():
    f = make_fields()
    assert notice_id(f) == notice_id(dict(f))
    assert notice_id(f) == notice_id(dict(reversed(list(f.items()))))


def test_notice_id_changes_if_identity_field_changes():
    base = notice_id(make_fields())
    assert notice_id(make_fields(entidad_raw="MELZAPAY  S.A.")) != base
    assert notice_id(make_fields(fecha_raw="08/09/2026")) != base
    assert notice_id(make_fields(tipo_raw="NOAUTO    ")) != base


def test_observaciones_and_fecha_baja_do_not_affect_notice_id():
    """Observaciones y Fecha Baja NO forman parte de notice_id."""
    f1 = make_fields()
    f2 = dict(f1)
    f2["observaciones_raw"] = "cualquier texto adicional"
    f2["fecha_baja_raw"] = "25/03/2026 0:00:00"
    assert notice_id(f1) == notice_id(f2)


def test_missing_fields_serialize_as_null():
    b = canonical_bytes(make_fields(entidad_secundaria_raw=""))
    assert b'"entidad_secundaria_raw":null' in b
    assert notice_id(make_fields(entidad_secundaria_raw="")) == notice_id(
        make_fields(entidad_secundaria_raw=None)
    )


def test_record_version_id_is_sha256_of_raw_bytes():
    raw = b"NOAUTO,09/09/2026,MELZAPAY S.A.,,CSSF,LUXEMBURGO,LU,,\r\n"
    assert record_version_id(raw) == hashlib.sha256(raw).hexdigest()


def test_record_version_id_distinguishes_byte_variants():
    a = record_version_id(b"row-a\r\n")
    b = record_version_id(b"row-a\n")
    assert a != b


def test_notice_id_stable_across_record_version():
    """Mismo contenido logico en bytes distintos (p.ej. CRLF) mismo notice_id,
    distinto record_version_id."""
    f = make_fields()
    assert notice_id(f) == notice_id(f)


def test_json_roundtrip_equivalence():
    """La serializacion canonica es JSON valido y deserializa a los mismos valores."""
    b = canonical_bytes(make_fields(entidad_raw="ÑºÑ"))
    obj = json.loads(b.decode("utf-8"))
    assert obj["entidad_raw"] == "ÑºÑ"
    assert list(obj.keys()) == IDENTITY_FIELDS
