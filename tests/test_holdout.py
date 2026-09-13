"""Holdout ciego: logica pura del muestreador (offline)."""

import re

from scripts.holdout_sample import (
    PARSER_FILES,
    parser_fingerprint,
    stratum_of,
    year_bucket,
)


def test_parser_fingerprint_format_and_coverage():
    fingerprint, per_file = parser_fingerprint()
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    assert set(per_file) == set(PARSER_FILES)
    assert all(re.fullmatch(r"[0-9a-f]{64}", v) for v in per_file.values())


def test_parser_fingerprint_stable():
    assert parser_fingerprint()[0] == parser_fingerprint()[0]


def test_year_bucket_boundaries():
    assert year_bucket(None) == "sin_fecha"
    assert year_bucket("2018-12-31") == "<2019"
    assert year_bucket("2019-01-01") == "2019-2021"
    assert year_bucket("2021-12-31") == "2019-2021"
    assert year_bucket("2022-01-01") == "2022-2023"
    assert year_bucket("2023-12-31") == "2022-2023"
    assert year_bucket("2024-01-01") == ">=2024"


def _notice(reg, clone, fecha):
    return {
        "codigo_regulador_raw": reg,
        "fecha": fecha,
        "clone": {"clone_detected": clone},
    }


def test_stratum_of():
    assert stratum_of(_notice("CNMV", False, "2025-01-01")) == \
        "CNMV/noclone/>=2024"
    assert stratum_of(_notice("FCA", True, "2023-05-01")) == \
        "EXTRANJERO/clone/2022-2023"
    assert stratum_of(_notice("BAFIN", False, "2010-01-01")) == \
        "EXTRANJERO/noclone/<2019"
