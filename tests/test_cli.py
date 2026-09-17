import json

import pytest

from alertafin.cli import main


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
    # Compat: el campo query se conserva tambien en SOURCE_UNAVAILABLE.
    assert out["query"] == "x"


def test_check_invalid_utf8_dataset(tmp_path, capsys):
    bad = tmp_path / "bad-utf8.jsonl"
    bad.write_bytes(b'{"notice_id": "x"}\n\xff\xfe\n')
    code = main(["check", "x", "--dataset", str(bad)])
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


def test_show_unknown_notice_id(dataset, capsys):
    code = main(["show", "noexiste", "--dataset", str(dataset)])
    out = json.loads(capsys.readouterr().out)
    assert code == 2
    assert out["status"] == "NOT_FOUND"


def test_dataset_flag_before_subcommand(dataset, capsys):
    # --dataset a nivel top NO debe ser pisado por el default del subparser
    code = main(["--dataset", str(dataset), "check", "WWW.MELZAPAY.COM"])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "WARNED"


def test_dataset_flag_both_positions_subcommand_wins(dataset, tmp_path, capsys):
    # Si se pasa en ambas posiciones, el valor del subcomando (el ultimo
    # en la linea) gana. El top-level apunta a un dataset inexistente.
    code = main(["--dataset", str(tmp_path / "nope.jsonl"),
                 "check", "WWW.MELZAPAY.COM", "--dataset", str(dataset)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "WARNED"


def test_dataset_flag_only_subcommand(dataset, capsys):
    code = main(["check", "WWW.MELZAPAY.COM", "--dataset", str(dataset)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "WARNED"


def test_default_dataset_missing(monkeypatch, tmp_path, capsys):
    # Sin --dataset: default g0/normalized/notices.jsonl relativo al cwd.
    # En un cwd sin dataset -> SOURCE_UNAVAILABLE, nunca traceback.
    monkeypatch.chdir(tmp_path)
    code = main(["check", "x"])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["status"] == "SOURCE_UNAVAILABLE"


def test_check_corrupt_dataset(tmp_path, capsys):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"notice_id": "ok"}\n{no es json}\n', encoding="utf-8")
    code = main(["check", "x", "--dataset", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["status"] == "SOURCE_UNAVAILABLE"
    assert ":2:" in out["reason"]  # reporta la linea corrupta


def test_check_dataset_non_object_line(tmp_path, capsys):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"notice_id": "ok"}\n42\n', encoding="utf-8")
    code = main(["check", "x", "--dataset", str(bad)])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["status"] == "SOURCE_UNAVAILABLE"
    assert ":2:" in out["reason"]


def test_check_empty_dataset(tmp_path, capsys):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n\n", encoding="utf-8")
    code = main(["check", "x", "--dataset", str(empty)])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["status"] == "SOURCE_UNAVAILABLE"


def test_check_unreadable_dataset(tmp_path, capsys):
    # Un directorio donde se espera un fichero -> DatasetError, no traceback.
    code = main(["check", "x", "--dataset", str(tmp_path)])
    out = json.loads(capsys.readouterr().out)
    assert code == 3
    assert out["status"] == "SOURCE_UNAVAILABLE"


def test_recent_negative_days(dataset, capsys):
    code = main(["recent", "--days", "-1", "--dataset", str(dataset)])
    assert code == 2
    assert "--days" in capsys.readouterr().err


def test_recent_invalid_today(dataset, capsys):
    code = main(["recent", "--today", "no-es-fecha",
                 "--dataset", str(dataset)])
    assert code == 2
    assert "--today" in capsys.readouterr().err


def test_recent_skips_invalid_fecha(dataset, capsys):
    import json as _json
    extra = _json.loads(dataset.read_text("utf-8").splitlines()[0])
    extra["notice_id"] = "cc33"
    extra["fecha"] = "no-es-una-fecha"
    with dataset.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps(extra, ensure_ascii=False) + "\n")
    code = main(["recent", "--days", "30", "--today", "2026-09-05",
                 "--dataset", str(dataset)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["skipped_invalid_fecha"] == 1
