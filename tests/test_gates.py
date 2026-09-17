"""Gates pre-registrados G0 (offline / fixtures).

Los umbrales estan congelados. La evaluacion sobre datos reales la hace
scripts/evaluate_gates.py con el mismo nucleo.
"""

import copy
import json

import tests.fixtures.mini_corpus as mini
from alertafin.identity import IDENTITY_FIELDS, notice_id
from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore
from alertafin.search import SearchIndex, check

PROV = {
    "source_url": "https://www.cnmv.es/WebAPI/datospublicos/PaffNoAutorizadas?format=csv",
    "query_params": {"format": "csv"},
    "retrieved_at": "2026-09-13T00:00:00Z",
    "source_sha256": "0" * 64,
    "http_status": 200,
}


# GATE: Parser determinista -> mismos bytes, misma salida: 3/3
def test_gate_parser_determinism_3_of_3():
    raw = mini.full_csv_bytes()
    runs = []
    for _ in range(3):
        res = enrich(raw, provenance=PROV)
        runs.append(json.dumps(res.notices, sort_keys=True, ensure_ascii=False,
                               default=list))
    assert len(set(runs)) == 1


# GATE: Provenance 100% / raw->normalized provenance 100%
def test_gate_provenance_100_percent():
    res = enrich(mini.full_csv_bytes(), provenance=PROV)
    required = {"source_url", "query_params", "retrieved_at", "source_sha256",
                "parser_version", "source_namespace"}
    assert res.notices
    for n in res.notices:
        assert required <= set(n["provenance"].keys()), n["notice_id"]
        assert n["record_version_id"]
        assert n["raw_row_bytes"]


# GATE: Preservacion de campos raw 100% (golden mini-corpus)
def test_gate_raw_field_preservation_golden():
    res = enrich(mini.full_csv_bytes(), provenance=PROV)
    by_id = {n["notice_id"]: n for n in res.notices}
    for expected in mini.golden_raw_expectations():
        n = by_id[expected["notice_id"]]
        for field, value in expected["fields"].items():
            assert n[field] == value, (expected["notice_id"], field)


# GATE: Parseo de fechas validas 100%
def test_gate_valid_dates_parse_100_percent():
    res = enrich(mini.full_csv_bytes(), provenance=PROV)
    assert res.notices
    for n in res.notices:
        if mini.is_valid_date(n["fecha_raw"]):
            assert n["fecha"], n["notice_id"]


# GATE: notice_id collisions = 0 (fixture amplio determinista)
def test_gate_notice_id_collisions_zero():
    raw = mini.synthetic_csv(1000)
    res = enrich(raw, provenance=PROV)
    ids = [n["notice_id"] for n in res.notices]
    assert len(ids) == len(set(ids))


# GATE: ID idempotence 100%
def test_gate_notice_id_idempotence_100_percent():
    res = enrich(mini.full_csv_bytes(), provenance=PROV)
    assert res.notices
    for n in res.notices:
        identity = {k: n[k] for k in IDENTITY_FIELDS}
        assert notice_id(identity) == n["notice_id"]


# GATE: Automatic false CLONE_OF = 0
def test_gate_no_false_clone_of():
    res = enrich(mini.full_csv_bytes(), provenance=PROV)
    for n in res.notices:
        cl = n["clone"]
        if not cl["clone_detected"]:
            assert cl["relation_status"] is None
            assert cl["clone_target_raw"] is None
        if cl["relation_status"] in ("EXPLICIT_SOURCE", "PARSED_EXPLICIT"):
            assert cl["clone_target_raw"], n["notice_id"]


# GATE: False entity merges = 0
def test_gate_no_entity_merges():
    notices = [
        {"notice_id": "x1", "entidad_raw": "BANCO AZUL SA", "domains": [],
         "entidad_secundaria_raw": None, "observaciones_raw": None, "provenance": {}},
        {"notice_id": "x2", "entidad_raw": "BANCO AZUL, S.A.", "domains": [],
         "entidad_secundaria_raw": None, "observaciones_raw": None, "provenance": {}},
        {"notice_id": "x3", "entidad_raw": "BANCO AZUL S.A. FILIAL", "domains": [],
         "entidad_secundaria_raw": None, "observaciones_raw": None, "provenance": {}},
    ]
    idx = SearchIndex.build(notices)
    res = check("banco azul sa", idx)
    assert res.status == "WARNED"
    assert [n["notice_id"] for n in res.notices] == ["x1"]
    res_cosmetic = check("BANCO AZUL, S.A.", idx)
    assert res_cosmetic.status == "WARNED"
    assert [n["notice_id"] for n in res_cosmetic.notices] == ["x2"]
    res2 = check("banco azul s a filial", idx)
    assert res2.status == "WARNED"         # sigue siendo sujeto distinto
    assert [n["notice_id"] for n in res2.notices] == ["x3"]
    # no se muta ningun notice (no fusion persistente)
    for n in notices:
        assert "merged_into" not in n
        assert "subjects" not in n


# Gate de dominios sobre mini-corpus (precision 100%, recall >=95%)
def test_gate_domain_extraction_mini_corpus():
    res = enrich(mini.full_csv_bytes(), provenance=PROV)
    got = {n["notice_id"]: {d["host_normalized"] for d in n["domains"]}
           for n in res.notices}
    tp = fp = fn = 0
    for notice_id_, expected in mini.golden_domains().items():
        g = got.get(notice_id_, set())
        tp += len(g & expected)
        fp += len(g - expected)
        fn += len(expected - g)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    assert precision == 1.0
    assert recall >= 0.95


# Gate de clones sobre mini-corpus
def test_gate_clone_detection_mini_corpus():
    res = enrich(mini.full_csv_bytes(), provenance=PROV)
    got = {n["notice_id"]: n["clone"] for n in res.notices}
    tp = fp = fn = target_ok = clone_total = 0
    for notice_id_, gold in mini.golden_clones().items():
        g = got[notice_id_]
        if gold["clone"] and g["clone_detected"]:
            tp += 1
            if g["clone_target_raw"]:
                target_ok += 1
        elif gold["clone"] and not g["clone_detected"]:
            fn += 1
        elif not gold["clone"] and g["clone_detected"]:
            fp += 1
        if gold["clone"]:
            clone_total += 1
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    exact = target_ok / tp if tp else 1.0
    assert precision == 1.0
    assert recall >= 0.95
    assert exact >= 0.90


# Gate: fallo de fuente -> SOURCE_UNAVAILABLE (no dataset vacio)
def test_gate_source_failure_is_source_unavailable(tmp_path, monkeypatch, capsys):
    import alertafin.acquire as acquire

    def boom(*a, **k):
        raise ConnectionError("DNS timeout")

    monkeypatch.setattr(acquire, "fetch_bytes", boom)
    store = ByteStore(tmp_path / "raw")
    code = acquire.run_acquisition(
        store=store,
        out_dir=tmp_path,
        today="2026-09-13",
    )
    assert code == 3
    out = json.loads((tmp_path / "acquisition" / "last_attempt.json").read_text("utf-8"))
    assert out["status"] == "SOURCE_UNAVAILABLE"
    assert not (tmp_path / "normalized" / "notices.jsonl").exists()


# Gate: cache agresiva -> segunda corrida no vuelve a pedir la red
def test_gate_cache_avoids_refetch(tmp_path, monkeypatch):
    import alertafin.acquire as acquire

    calls = {"n": 0}

    def fake_fetch(url, params=None, timeout=60):
        calls["n"] += 1
        return 200, mini.full_csv_bytes()

    monkeypatch.setattr(acquire, "fetch_bytes", fake_fetch)
    store = ByteStore(tmp_path / "raw")
    out_dir = tmp_path
    assert acquire.run_acquisition(store=store, out_dir=out_dir, today="2026-09-13") == 0
    assert calls["n"] == 1 + len(acquire.ACTIVE_PROBE_PARAMS)
    assert acquire.run_acquisition(store=store, out_dir=out_dir, today="2026-09-13") == 0
    assert calls["n"] == 1 + len(acquire.ACTIVE_PROBE_PARAMS)  # sin nueva peticion


def test_pipeline_enrich_shape():
    res = enrich(mini.full_csv_bytes(), provenance=PROV)
    n = res.notices[0]
    assert {"domains", "clone"} <= set(n.keys())
    assert copy.deepcopy(n) == n  # datos simples serializables
