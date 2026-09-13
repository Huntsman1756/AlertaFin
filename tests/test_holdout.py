"""Holdout ciego: logica pura del muestreador y de la vista de etiquetado."""

import json
import re

from scripts.holdout_labeling import PROV_KEYS, blind_entry, blind_stratum
from scripts.holdout_sample import (
    PARSER_FILES,
    freeze_guard,
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


def test_freeze_guard_missing_manifest(tmp_path):
    assert freeze_guard(tmp_path / "manifest.json", "abc") is None


def test_freeze_guard_allows_same_fingerprint(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"parser_fingerprint": "same"}), encoding="utf-8")
    assert freeze_guard(path, "same") is None


def test_freeze_guard_aborts_on_parser_change(tmp_path, capsys):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"parser_fingerprint": "old"}), encoding="utf-8")
    assert freeze_guard(path, "new") == 2
    assert "ABORTADO" in capsys.readouterr().out


def test_blind_stratum_drops_clone_flag():
    assert blind_stratum("CNMV/clone/2022-2023") == "CNMV/2022-2023"
    assert blind_stratum("EXTRANJERO/noclone/<2019") == "EXTRANJERO/<2019"


def test_blind_entry_removes_inferred_output():
    entry = {
        "notice_id": "n1",
        "record_version_id": "r1",
        "row_number": 7,
        "stratum": "CNMV/clone/>=2024",
        "raw": {"entidad_raw": "X"},
        "fecha": "2024-01-01",
        "fecha_baja": None,
        "domains": ["x.com"],
        "clone": {"clone_detected": True, "relation_status": "UNRESOLVED"},
        "raw_row_bytes_hex": "aa",
        "provenance": {
            "source_url": "u", "query_params": {}, "retrieved_at": "t",
            "source_sha256": "s", "http_status": 200, "parser_version": "p",
            "source_namespace": "ns", "retrieval_id": "zzz",
        },
    }
    blind = blind_entry(entry)
    assert "domains" not in blind
    assert "clone" not in blind
    assert "stratum" not in blind
    assert "raw_row_bytes_hex" not in blind
    assert blind["stratum_blind"] == "CNMV/>=2024"
    assert set(blind["provenance"]) == set(PROV_KEYS)
    assert "retrieval_id" not in blind["provenance"]
