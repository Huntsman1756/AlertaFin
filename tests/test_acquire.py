"""Tests de adquisicion: cache diaria, --force, --reprocess y PARSE_FAILED."""

import json

import alertafin.acquire as acquire
from alertafin.parser import ParseError
from alertafin.provenance import ByteStore
from tests.fixtures import mini_corpus as mini

PROBE_N = len(acquire.ACTIVE_PROBE_PARAMS)


def _fake_fetch_ok(calls):
    def fake_fetch(url, params=None, timeout=60):
        calls["n"] += 1
        return 200, mini.full_csv_bytes()
    return fake_fetch


def _last_attempt(out_dir):
    return json.loads(
        (out_dir / "acquisition" / "last_attempt.json").read_text("utf-8"))


def _notices(out_dir):
    return (out_dir / "normalized" / "notices.jsonl").read_text("utf-8")


def test_cache_refetches_next_day(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(acquire, "fetch_bytes", _fake_fetch_ok(calls))
    store = ByteStore(tmp_path / "raw")
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13") == 0
    n_day1 = calls["n"]
    # Otro dia UTC -> pull nuevo (max. 1 pull/dia, no cache eterna)
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-14") == 0
    assert calls["n"] == 2 * n_day1


def test_force_bypasses_cache(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(acquire, "fetch_bytes", _fake_fetch_ok(calls))
    store = ByteStore(tmp_path / "raw")
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13") == 0
    n_day1 = calls["n"]
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13", force=True) == 0
    assert calls["n"] == 2 * n_day1


def test_reprocess_uses_cached_bytes_without_network(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(acquire, "fetch_bytes", _fake_fetch_ok(calls))
    store = ByteStore(tmp_path / "raw")
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13") == 0

    def boom(*a, **k):
        raise AssertionError("la red no debe tocarse en --reprocess")

    monkeypatch.setattr(acquire, "fetch_bytes", boom)
    # Aunque sea otro dia, reprocess re-deriva desde los bytes guardados.
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-14",
        reprocess=True) == 0
    assert (tmp_path / "normalized" / "notices.jsonl").exists()


def test_parse_failed_preserves_last_valid_dataset(tmp_path, monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(acquire, "fetch_bytes", _fake_fetch_ok(calls))
    store = ByteStore(tmp_path / "raw")
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13") == 0
    valid_notices = _notices(tmp_path)

    # Al dia siguiente la fuente devuelve bytes no decodificables.
    def fake_fetch_bad(url, params=None, timeout=60):
        calls["n"] += 1
        return 200, b"\xff\xfe no es utf-8 \x9c"

    monkeypatch.setattr(acquire, "fetch_bytes", fake_fetch_bad)
    code = acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-14")
    assert code == acquire.EXIT_PARSE_FAILED

    attempt = _last_attempt(tmp_path)
    assert attempt["status"] == "PARSE_FAILED"
    assert "error" in attempt
    # Los bytes malos quedan en el byte store como evidencia...
    assert store.has(attempt["source_sha256"])
    # ...y el ultimo dataset valido se conserva intacto.
    assert _notices(tmp_path) == valid_notices


def test_reprocess_parse_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(acquire, "fetch_bytes", _fake_fetch_ok({"n": 0}))
    store = ByteStore(tmp_path / "raw")
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13") == 0
    valid_notices = _notices(tmp_path)

    real_enrich = acquire.enrich

    def broken(*a, **k):
        raise ParseError("esquema cambiado")

    monkeypatch.setattr(acquire, "enrich", broken)
    code = acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13", reprocess=True)
    assert code == acquire.EXIT_PARSE_FAILED
    attempt = _last_attempt(tmp_path)
    assert attempt["status"] == "PARSE_FAILED"
    assert attempt.get("reprocess") is True
    assert _notices(tmp_path) == valid_notices
    monkeypatch.setattr(acquire, "enrich", real_enrich)


def test_reprocess_never_touches_network_after_failed_attempt(
        tmp_path, monkeypatch):
    """Invariante: reprocess=True jamas llama a fetch_bytes, en ningun
    estado de last_attempt (OK, SOURCE_UNAVAILABLE, PARSE_FAILED o
    inexistente)."""
    monkeypatch.setattr(acquire, "fetch_bytes", _fake_fetch_ok({"n": 0}))
    store = ByteStore(tmp_path / "raw")
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13") == 0

    # Intento de red fallido: last_attempt queda SOURCE_UNAVAILABLE sin sha.
    def boom(*a, **k):
        raise ConnectionError("DNS timeout")

    monkeypatch.setattr(acquire, "fetch_bytes", boom)
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-14") == 3
    assert _last_attempt(tmp_path)["status"] == "SOURCE_UNAVAILABLE"

    def explode(*a, **k):
        raise AssertionError("reprocess toco la red")

    monkeypatch.setattr(acquire, "fetch_bytes", explode)
    # El ultimo intento no apunta a bytes utilizables -> error controlado,
    # pero la red jamas se ejecuta.
    code = acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-14", reprocess=True)
    assert code == acquire.EXIT_SOURCE_UNAVAILABLE
    attempt = _last_attempt(tmp_path)
    assert attempt["status"] == "SOURCE_UNAVAILABLE"
    assert attempt.get("reprocess") is True


def test_reprocess_without_any_attempt_is_offline_error(
        tmp_path, monkeypatch):
    def explode(*a, **k):
        raise AssertionError("reprocess toco la red")

    monkeypatch.setattr(acquire, "fetch_bytes", explode)
    store = ByteStore(tmp_path / "raw")
    code = acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13", reprocess=True)
    assert code == acquire.EXIT_SOURCE_UNAVAILABLE


def test_source_failure_preserves_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr(acquire, "fetch_bytes", _fake_fetch_ok({"n": 0}))
    store = ByteStore(tmp_path / "raw")
    assert acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-13") == 0
    valid_notices = _notices(tmp_path)

    def boom(*a, **k):
        raise ConnectionError("DNS timeout")

    monkeypatch.setattr(acquire, "fetch_bytes", boom)
    code = acquire.run_acquisition(
        store=store, out_dir=tmp_path, today="2026-09-14")
    assert code == acquire.EXIT_SOURCE_UNAVAILABLE
    assert _last_attempt(tmp_path)["status"] == "SOURCE_UNAVAILABLE"
    assert _notices(tmp_path) == valid_notices
