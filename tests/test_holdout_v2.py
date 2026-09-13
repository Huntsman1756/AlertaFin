"""Tests del harness del holdout ciego v2 (select/verify/blind/scaffold/
evaluate) segun g0/holdout-v2/preregistration.md."""
import hashlib
import json

import pytest

from scripts.holdout_v2 import (
    MIN_PER_NONEMPTY_STRATUM,
    N_TOTAL,
    SEED,
    SEED_MATERIAL,
    allocate,
    blind_entry,
    build_seen_set,
    case_key,
    pick_version,
    regulator_group,
    score,
    stratum_of,
    validate_label,
)


def _notice(notice_id="n1", rvid="a" * 64, reg="CNMV", fecha="2020-01-01"):
    return {"notice_id": notice_id, "record_version_id": rvid,
            "codigo_regulador_raw": reg, "fecha": fecha}


def _sample_entry(key, domains=(), detected=False, target=None,
                  rel="UNRESOLVED"):
    return {"case_key": key, "domains": list(domains),
            "clone": {"clone_detected": detected,
                      "clone_target_raw": target,
                      "clone_target_registry_number": None,
                      "relation_status": rel}}


def _label(key, domains=(), clone=False, target=None, rel=None,
           unclear=None):
    return {"case_key": key, "labeled": True, "expected_domains":
            list(domains), "expected_clone_detected": clone,
            "expected_clone_target": target,
            "expected_relation_status": rel, "unclear": unclear}


# ---- seed preregistrada ----

def test_seed_derivada_del_commit_de_preregistracion():
    digest = hashlib.sha256(SEED_MATERIAL.encode("utf-8")).digest()
    assert SEED == int.from_bytes(digest[:8], "big") == 305345613011385107
    assert "c01cae34ffd29019d7d124cc7aeaba4907230006" in SEED_MATERIAL


# ---- unidad de evaluacion y estratos ----

def test_case_key_es_notice_id_mas_record_version():
    n = _notice("nid", "rvid")
    assert case_key(n) == {"notice_id": "nid", "record_version_id": "rvid"}


def test_pick_version_elige_record_version_id_lexicograficamente_menor():
    a = _notice("x", "b" * 64)
    b = _notice("x", "a" * 64)
    c = _notice("y", "z" * 64)
    best = pick_version([a, b, c])
    assert best["x"]["record_version_id"] == "a" * 64
    assert best["y"]["record_version_id"] == "z" * 64


def test_stratum_es_regulador_por_tramo_sin_clon():
    assert stratum_of(_notice(reg="CNMV", fecha="2018-05-01")) == \
        "CNMV/<2019"
    assert stratum_of(_notice(reg="FCA", fecha="2020-01-01")) == \
        "EXTRANJERO/2019-2021"
    assert stratum_of(_notice(reg="CNMV", fecha="2023-06-01")) == \
        "CNMV/2022-2023"
    assert stratum_of(_notice(reg="AMF", fecha="2025-01-01")) == \
        "EXTRANJERO/>=2024"
    assert "/" in stratum_of(_notice()) and "clone" not in \
        stratum_of(_notice())


def test_regulator_group():
    assert regulator_group(_notice(reg="CNMV")) == "CNMV"
    assert regulator_group(_notice(reg="FCA")) == "EXTRANJERO"
    assert regulator_group(_notice(reg=None)) == "EXTRANJERO"


# ---- asignacion cerrada ----

def test_allocate_total_exacto():
    pops = {"CNMV/<2019": 4000, "CNMV/2019-2021": 3000,
            "CNMV/2022-2023": 2000, "CNMV/>=2024": 1500,
            "EXTRANJERO/<2019": 100, "EXTRANJERO/2019-2021": 500,
            "EXTRANJERO/2022-2023": 800, "EXTRANJERO/>=2024": 300}
    take = allocate(pops)
    assert sum(take.values()) == N_TOTAL
    assert all(take[s] >= MIN_PER_NONEMPTY_STRATUM for s in take)
    assert all(take[s] <= pops[s] for s in take)


def test_allocate_minimos_en_estratos_pequenos():
    pops = {"a": 3, "b": 1000, "c": 7}
    take = allocate(pops, n_total=50)
    assert take["a"] == 3          # min(5, pop)
    assert take["c"] >= 5
    assert sum(take.values()) == 50


def test_allocate_empates_de_resto_lexicograficos():
    # Dos estratos con mismo resto: la plaza extra va al nombre menor.
    pops = {"b": 10, "a": 10}
    take = allocate(pops, n_total=11, min_per=5)
    assert take["a"] == 6 and take["b"] == 5


def test_allocate_aborta_si_poblacion_insuficiente():
    with pytest.raises(SystemExit):
        allocate({"a": 4, "b": 4}, n_total=300)


def test_allocate_aborta_si_minimos_superan_total():
    with pytest.raises(SystemExit):
        allocate({f"s{i}": 10 for i in range(100)},
                 n_total=50, min_per=5)


# ---- seen set fail-closed ----

def test_seen_set_falla_si_falta_fuente(tmp_path):
    missing = tmp_path / "nope.jsonl"
    with pytest.raises(SystemExit):
        build_seen_set({"golden": str(missing)})


def test_seen_set_une_fuentes_y_reporta(tmp_path):
    g = tmp_path / "golden.jsonl"
    g.write_text('\n'.join(json.dumps({"notice_id": n})
                          for n in ["a", "b"]), encoding="utf-8")
    h = tmp_path / "h1.jsonl"
    h.write_text(json.dumps({"notice_id": "b"}) + "\n" +
                 json.dumps({"notice_id": "c"}), encoding="utf-8")
    ig = tmp_path / "ig.json"
    ig.write_text(json.dumps({"groups": [{"notice_id": "d"}]}),
                  encoding="utf-8")
    seen, report = build_seen_set(
        {"golden": str(g), "holdout_v1": str(h), "identity_groups": str(ig)})
    assert seen == {"a", "b", "c", "d"}
    assert report["union_count"] == 4
    assert report["sources"]["golden"]["count"] == 2
    assert report["sources"]["identity_groups"]["count"] == 1
    assert len(report["union_sha256"]) == 64


# ---- vista ciega ----

def test_blind_entry_no_expone_output_inferido():
    entry = {"case_key": "n:r", "notice_id": "n", "record_version_id": "r",
             "row_number": 7, "stratum": "CNMV/2022-2023",
             "raw": {"entidad_raw": "X"}, "fecha": "2022-01-01",
             "fecha_baja": None,
             "domains": ["x.com"], "clone": {"clone_detected": True},
             "raw_row_bytes_hex": "aa",
             "provenance": {"source_url": "u", "query_params": {},
                            "retrieved_at": "t", "source_sha256": "s",
                            "http_status": 200, "parser_version": "p",
                            "source_namespace": "ns", "extra": 1}}
    b = blind_entry(entry)
    assert "domains" not in b and "clone" not in b
    assert "raw_row_bytes_hex" not in b
    assert b["case_key"] == "n:r" and b["raw"]["entidad_raw"] == "X"
    assert "extra" not in b["provenance"]


# ---- labels ----

def test_validate_label():
    ok = _label("k", domains=["a.com"], clone=True, target="T",
                unclear=False)
    assert validate_label(ok) == []
    bad = {"case_key": "k", "labeled": True, "expected_domains": "a.com",
           "expected_clone_detected": "si", "expected_clone_target": 3,
           "expected_relation_status": None, "unclear": "quizas"}
    errs = validate_label(bad)
    assert len(errs) == 4


# ---- score: gates + denominadores + precedencia ----

def _big_gold_domains(key, n):
    return _label(key, domains=[f"d{i}.com" for i in range(n)])


def test_score_pass_con_denominadores_suficientes():
    keys = [f"k{i}" for i in range(24)]
    sample = {}
    labels = []
    for i, k in enumerate(keys):
        doms = [f"d{i}-{j}.com" for j in range(5)]  # 5 gold por caso
        if i < 20:   # 20 clones: 16 resolubles, 4 unresolvable
            tgt = f"TARGET {i}" if i < 16 else None
            e = _sample_entry(k, doms, True, tgt,
                              "EXPLICIT_SOURCE" if tgt else "UNRESOLVED")
            labels.append(_label(k, doms, True, tgt))
        else:
            e = _sample_entry(k, doms)
            labels.append(_label(k, doms))
        sample[k] = e
    r = score(sample, labels)
    assert r["verdict"] == "PASS"
    assert all(v is True for v in r["gate_status"].values())
    assert r["denominators"]["gold_domain_instances"] == 120
    assert r["denominators"]["gold_clone_cases"] == 20
    assert r["denominators"]["gold_target_resolvable_cases"] == 16
    assert r["denominators"]["gold_target_unresolvable_cases"] == 4


def test_score_fail_si_gate_falla_aunque_denominadores_sobren():
    k = "k1"
    sample = {k: _sample_entry(k, ["real.com"], True, "T",
                               "EXPLICIT_SOURCE")}
    labels = [_label(k, domains=["real.com", "falso.com"] * 60,
                     clone=True, target="OTRO")]
    r = score(sample, labels)
    assert r["gate_status"]["domain_recall_95"] is False
    assert r["gate_status"]["clone_target_exact_90"] is False
    assert r["verdict"] == "FAIL"


def test_score_inconclusive_si_denominador_insuficiente_sin_fallo():
    k = "k1"
    sample = {k: _sample_entry(k, ["a.com"])}
    labels = [_label(k, domains=["a.com"])]
    r = score(sample, labels)
    assert r["verdict"] == "INCONCLUSIVE"
    assert r["denominators"]["sufficient"]["gold_domain_instances"] is False


def test_score_false_target_gate():
    k = "k1"
    sample = {k: _sample_entry(k, [], True, "INVENTADO",
                               "EXPLICIT_SOURCE")}
    labels = [_label(k, clone=True, target=None)]
    r = score(sample, labels)
    assert r["gate_status"]["automatic_false_target_0"] is False
    assert r["verdict"] == "FAIL"
