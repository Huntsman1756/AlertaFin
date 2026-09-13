import json
import pytest

from alertafin.cli import main, build_index


@pytest.fixture
def dataset(tmp_path):
    n1 = {
        "notice_id": "aa11",
        "entidad_raw": "MELZAPAY S.A.",
        "fecha": "2026-09-01",
        "entidad_secundaria_raw": "WWW.MELZAPAY.COM",
        "observaciones_raw": None,
        "provenance": {"source_sha256": "x"},
        "domains": [{"raw": "WWW.MELZAPAY.COM", "host_normalized": "www.melzapay.com",
                     "source_field": "entidad_secundaria_raw"}],
        "clone": {"clone_detected": False, "relation_status": None,
                  "clone_target_raw": None, "clone_markers": [],
                  "clone_target_registry_number": None},
    }
    n2 = {
        "notice_id": "bb22",
        "entidad_raw": "FAKE WEB (CLONE)",
        "fecha": "2026-08-20",
        "entidad_secundaria_raw": None,
        "observaciones_raw": "se hace pasar por la entidad BANCO REAL S.A.",
        "provenance": {"source_sha256": "x"},
        "domains": [],
        "clone": {"clone_detected": True, "relation_status": "EXPLICIT_SOURCE",
                  "clone_target_raw": "BANCO REAL S.A.", "clone_markers": ["token_clone"],
                  "clone_target_registry_number": None},
    }
    path = tmp_path / "notices.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for n in (n1, n2):
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    return path


def test_check_warned_by_domain(dataset, capsys):
    code = main(["check", "WWW.MELZAPAY.COM", "--dataset", str(dataset)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "WARNED"


def test_check_no_warning(dataset, capsys):
    code = main(["check", "inexistente total", "--dataset", str(dataset)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "NO_WARNING_FOUND"


def test_check_source_unavailable(tmp_path, capsys):
    code = main(["check", "x", "--dataset", str(tmp_path / "nope.jsonl")])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["status"] == "SOURCE_UNAVAILABLE"


def test_recent_filters_by_days(dataset, capsys):
    code = main(["recent", "--days", "7", "--dataset", str(dataset), "--today", "2026-09-05"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert [n["notice_id"] for n in out["notices"]] == ["aa11"]


def test_clones_lists_explicit_only(dataset, capsys):
    code = main(["clones", "--dataset", str(dataset)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(out["clones"]) == 1
    assert out["clones"][0]["relation_status"] == "EXPLICIT_SOURCE"
    assert out["clones"][0]["clone_target_raw"] == "BANCO REAL S.A."


def test_show_notice_by_id(dataset, capsys):
    code = main(["show", "bb22", "--dataset", str(dataset)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["notice"]["entidad_raw"] == "FAKE WEB (CLONE)"
    assert out["notice"]["clone"]["clone_target_raw"] == "BANCO REAL S.A."
    assert out["notice"]["provenance"]["source_sha256"] == "x"
