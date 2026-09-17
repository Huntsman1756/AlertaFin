import pytest

from alertafin.parser import ParseError, parse_csv

BOM = b"\xef\xbb\xbf"
HEADER = (
    "Tipo,Fecha,Entidad,Entidad Secundaria,"
    "C\u00f3digo regulador,Pa\u00eds regulador,"
    "C\u00f3digo pa\u00eds regulador,Observaciones,Fecha Baja"
).encode("utf-8")


def make_csv(rows: bytes) -> bytes:
    return BOM + HEADER + b"\r\n" + rows


ROW1 = (
    b"NOAUTO,09/09/2026,\"MELZAPAY S.A.\",\"WWW.MELZAPAY.COM\","
    b"CSSF,LUXEMBURGO,LU,\"\","
    b"\r\n"
)

ROW2 = (
    b"OTRADV,01/03/2021,ALPHA INVEST,\"\",FCA,REINO UNIDO,GB,"
    b"\"Se hace pasar por la entidad BETA S.A.\","
    b"\r\n"
)

ROW3 = b"NOAUTO    ,02/02/2019,GAMMA,,CONSOB,ITALIA,IT,,25/03/2026 0:00:00\r\n"


def test_parses_all_rows_with_raw_fields():
    res = parse_csv(make_csv(ROW1 + ROW2 + ROW3))
    assert len(res.notices) == 3
    n1 = res.notices[0]
    assert n1["tipo_raw"] == "NOAUTO"
    assert n1["entidad_raw"] == "MELZAPAY S.A."
    assert n1["entidad_secundaria_raw"] == "WWW.MELZAPAY.COM"
    assert n1["fecha_raw"] == "09/09/2026"
    assert n1["fecha"] == "2026-09-09"
    n3 = res.notices[2]
    assert n3["tipo_raw"] == "NOAUTO    "  # espacios preservados
    assert n3["fecha_baja_raw"] == "25/03/2026 0:00:00"
    assert n3["fecha_baja"] == "2026-03-25T00:00:00"


def test_empty_optional_fields_are_none():
    res = parse_csv(make_csv(ROW1))
    n = res.notices[0]
    assert n["observaciones_raw"] is None
    assert n["fecha_baja_raw"] is None
    assert n["fecha_baja"] is None


def test_raw_row_bytes_preserved_without_terminator():
    res = parse_csv(make_csv(ROW1 + ROW3))
    assert res.notices[0]["raw_row_bytes"] == ROW1[:-2]
    assert res.notices[1]["raw_row_bytes"] == ROW3[:-2]


def test_raw_row_bytes_hex_matches_record_version_input():
    from alertafin.identity import record_version_id
    res = parse_csv(make_csv(ROW1))
    assert res.notices[0]["record_version_id"] == record_version_id(ROW1[:-2])


def test_quoted_field_with_comma_and_newline():
    row = b"NOAUTO,05/05/2025,\"DIEZ, S.L.\",\"MULTI\r\nLINE\",FCA,REINO UNIDO,GB,\"\",\"\"\r\n"
    res = parse_csv(make_csv(row))
    assert len(res.notices) == 1
    assert res.notices[0]["entidad_raw"] == "DIEZ, S.L."
    assert res.notices[0]["entidad_secundaria_raw"] == "MULTI\r\nLINE"


def test_determinist_same_bytes_same_output():
    data = make_csv(ROW1 + ROW2 + ROW3)
    r1 = parse_csv(data)
    r2 = parse_csv(data)
    r3 = parse_csv(data)
    ids1 = [n["notice_id"] for n in r1.notices]
    for other in (r2, r3):
        assert [n["notice_id"] for n in other.notices] == ids1


def test_header_mismatch_raises_schema_change():
    bad = BOM + b"Tipo,Fecha,Entidad\r\nNOAUTO,01/01/2024,X\r\n"
    with pytest.raises(ParseError):
        parse_csv(bad)


def test_wrong_column_count_is_captured_not_dropped():
    bad_row = b"NOAUTO,01/01/2024,SOLO-TRES\r\n"
    res = parse_csv(make_csv(ROW1 + bad_row))
    assert len(res.notices) == 1
    assert len(res.row_errors) == 1
    assert res.row_errors[0]["error"] == "COLUMN_COUNT"


def test_invalid_date_is_row_error_with_raw_kept():
    bad_date = b"NOAUTO,31/02/2024,X,,CNMV,ESPANA,ES,,\r\n"
    res = parse_csv(make_csv(bad_date))
    assert len(res.notices) == 0
    assert len(res.row_errors) == 1
    assert res.row_errors[0]["error"] == "INVALID_DATE"
    assert res.row_errors[0]["raw_row_bytes"] == bad_date[:-2]


def test_notice_id_and_provenance_attached():
    prov = {
        "source_url": "https://www.cnmv.es/WebAPI/datospublicos/PaffNoAutorizadas?format=csv",
        "query_params": {"format": "csv"},
        "retrieved_at": "2026-09-13T10:00:00Z",
        "source_sha256": "abc123",
    }
    res = parse_csv(make_csv(ROW1), provenance=prov)
    n = res.notices[0]
    assert n["provenance"]["source_sha256"] == "abc123"
    assert n["provenance"]["parser_version"]
    assert n["notice_id"]


def test_bom_stripped_and_encoding_recorded():
    res = parse_csv(make_csv(ROW1))
    assert res.encoding == "utf-8-sig"
    res2 = parse_csv(HEADER + b"\r\n" + ROW1)
    assert res2.encoding == "utf-8"


def test_all_identity_fields_present_in_output():
    from alertafin.identity import IDENTITY_FIELDS
    res = parse_csv(make_csv(ROW1))
    for f in IDENTITY_FIELDS:
        assert f in res.notices[0]
