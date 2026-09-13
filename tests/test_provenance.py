import json
import pytest

from alertafin.provenance import ByteStore, RetrievalLog


def test_byte_store_roundtrip(tmp_path):
    store = ByteStore(tmp_path / "raw")
    sha = store.put(b"hola mundo")
    assert store.get(sha) == b"hola mundo"
    assert (tmp_path / "raw" / sha[:2] / f"{sha}.bin").exists()


def test_byte_store_idempotent_same_bytes(tmp_path):
    store = ByteStore(tmp_path / "raw")
    sha1 = store.put(b"mismos bytes")
    n_before = len(list((tmp_path / "raw").rglob("*.bin")))
    sha2 = store.put(b"mismos bytes")
    assert sha1 == sha2
    assert len(list((tmp_path / "raw").rglob("*.bin"))) == n_before


def test_byte_store_refuses_corruption(tmp_path):
    store = ByteStore(tmp_path / "raw")
    sha = store.put(b"contenido original")
    path = tmp_path / "raw" / sha[:2] / f"{sha}.bin"
    path.write_bytes(b"contenido corrompido")
    with pytest.raises(RuntimeError):
        store.put(b"contenido original")


def test_retrieval_log_unique_events_for_same_bytes(tmp_path):
    log = RetrievalLog(tmp_path / "events.jsonl")
    e1 = log.append(source_url="https://x", query_params={"format": "csv"},
                    retrieved_at="2026-09-13T00:00:00Z", http_status=200,
                    source_sha256="abc", size=10)
    e2 = log.append(source_url="https://x", query_params={"format": "csv"},
                    retrieved_at="2026-09-13T00:00:00Z", http_status=200,
                    source_sha256="abc", size=10)
    assert e1["retrieval_id"] != e2["retrieval_id"]
    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2  # no se sobrescribe metadata historica


def test_retrieval_log_preserves_fields(tmp_path):
    log = RetrievalLog(tmp_path / "events.jsonl")
    ev = log.append(source_url="https://x?f=csv", query_params={"f": "csv"},
                    retrieved_at="2026-09-13T01:02:03Z", http_status=200,
                    source_sha256="deadbeef", size=42, note="full pull")
    assert ev["source_sha256"] == "deadbeef"
    assert ev["note"] == "full pull"
    rec = json.loads((tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert rec["retrieval_id"] == ev["retrieval_id"]
    assert rec["query_params"] == {"f": "csv"}
