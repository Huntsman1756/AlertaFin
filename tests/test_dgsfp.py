"""G1-WI.B: ingesta DGSFP sobre el snapshot congelado del probe.

Los tests leen los bytes inmutables de `g1-wi/probe/raw/` — el corpus
congelado en G1-WI.A — y verifican los hechos congelados en
`g1-wi/pre-ingestion-freeze.md`.
"""

import json
from pathlib import Path

import pytest

from alertafin.dgsfp import (
    NS_PAGINAS,
    NS_SUJETOS,
    parse_paginas,
    parse_sujetos,
)

UNAUTH = Path("g1-wi/probe/raw/unauth.html").read_bytes()
WEBS = Path("g1-wi/probe/raw/webs.html").read_bytes()

PROV = {"source_url": "https://dgsfp.mineco.gob.es/x",
        "retrieved_at": "2026-09-13T19:56:33Z", "http_status": 200,
        "source_sha256": "x"}


def test_sujetos_source_coverage_97():
    res = parse_sujetos(UNAUTH, provenance=PROV)
    assert len(res.notices) == 97
    assert not res.row_errors


def test_sujetos_sections_and_duplicates_preserved():
    res = parse_sujetos(UNAUTH, provenance=PROV)
    by_sec = {}
    for n in res.notices:
        by_sec[n["section"]] = by_sec.get(n["section"], 0) + 1
    assert by_sec == {"ANO_2024": 10, "RESTO": 87}
    # duplicados de origen preservados: 2 ocurrencias, misma identidad
    # semantica (notice_id/rvid), ocurrencia fisica distinta
    milton = [n for n in res.notices if n["entidad_raw"] == "MILTON GROUP"]
    assert len(milton) == 2
    assert len({n["notice_id"] for n in milton}) == 1
    assert len({n["record_version_id"] for n in milton}) == 1
    assert len({n["source_occurrence_id"] for n in milton}) == 2
    assert sorted(n["occurrence_index"] for n in milton) == [38, 75]


def test_sujetos_warning_date_absent_and_context_period():
    res = parse_sujetos(UNAUTH, provenance=PROV)
    assert all(n["warning_date"] is None for n in res.notices)
    assert all(n["warning_date_status"] == "ABSENT" for n in res.notices)
    y24 = [n for n in res.notices if n["section"] == "ANO_2024"]
    assert all(n["context_period"]["year"] == 2024
               and n["context_period"]["precision"] == "YEAR"
               for n in y24)
    resto = [n for n in res.notices if n["section"] == "RESTO"]
    assert all(n["context_period"]["raw"] == "Resto de años"
               and n["context_period"]["year"] is None for n in resto)


def test_sujetos_no_relation_disclaimer_is_not_clone():
    """Errata pre-C: 'sin vínculos ni relación con X' no es afirmacion
    explicita de clon bajo la semantica G0. La nota se preserva en
    nota_raw pero no genera evidencia de clon."""
    res = parse_sujetos(UNAUTH, provenance=PROV)
    assert not [n for n in res.notices if n["clone"]["clone_detected"]]
    barkley = next(n for n in res.notices
                   if n["entidad_raw"] == "BARKLEY DEVELOPMENT CORPORATION")
    assert barkley["nota_raw"].startswith("sin vínculos ni relación con")
    assert barkley["clone"] == {
        "clone_detected": False, "clone_markers": [],
        "clone_target_raw": None, "relation_status": None,
    }


def test_notice_id_stable_under_insertion():
    """RED: insertar un <p> ajeno antes de un registro no puede cambiar
    su notice_id (identidad semantica != ocurrencia fisica)."""
    original = parse_sujetos(UNAUTH, provenance=PROV)
    marker = next(n for n in original.notices
                  if n["entidad_raw"] == "MILTON GROUP")
    text = UNAUTH.decode("utf-8")
    i = text.find("MILTON GROUP")
    p_start = text.rfind("<p", 0, i)
    injected = (text[:p_start]
                + "<p><span><strong>ENTIDAD INYECTADA ZZZ</strong></span></p>"
                + text[p_start:])
    modified = parse_sujetos(injected.encode("utf-8"), provenance=PROV)
    assert len(modified.notices) == 98
    after = [n for n in modified.notices
             if n["entidad_raw"] == "MILTON GROUP"]
    assert len(after) == 2
    assert {n["notice_id"] for n in after} == {marker["notice_id"]}


def test_duplicate_rows_share_notice_id_distinct_occurrence():
    """RED: dos filas raw identicas -> mismo notice_id y mismo
    record_version_id, pero dos source_occurrence_id distintos.
    Source coverage sigue siendo 97 ocurrencias."""
    res = parse_sujetos(UNAUTH, provenance=PROV)
    milton = [n for n in res.notices if n["entidad_raw"] == "MILTON GROUP"]
    assert len(milton) == 2
    assert len({n["notice_id"] for n in milton}) == 1
    assert len({n["record_version_id"] for n in milton}) == 1
    assert len({n["source_occurrence_id"] for n in milton}) == 2
    assert len(res.notices) == 97


def test_sujetos_no_domains():
    res = parse_sujetos(UNAUTH, provenance=PROV)
    assert all(n["domains"] == [] for n in res.notices)


def test_paginas_source_coverage_10():
    res = parse_paginas(WEBS, provenance=PROV)
    assert len(res.notices) == 10
    assert not res.row_errors


def test_paginas_domains_exact():
    res = parse_paginas(WEBS, provenance=PROV)
    hosts = {n["domains"][0]["host_normalized"] for n in res.notices}
    # subdominios nunca colapsan (convencion G0): sin-cargos.credito-expres
    # y banque.astral-agency se conservan completos; la denominacion entre
    # parentesis puede ser el dominio padre.
    assert hosts == {
        "rapidegroupe.com", "bp-groupe.com", "europae-s.com",
        "topfservices.com", "bcifinanzial.com", "credito-confiable.com",
        "serviciofinance.com", "sin-cargos.credito-expres.com",
        "astral-bank.com", "banque.astral-agency.com",
    }
    assert all(n["warning_date_status"] == "ABSENT" for n in res.notices)
    assert all(n["clone"]["clone_detected"] is False for n in res.notices)


def test_paginas_entity_denominations():
    res = parse_paginas(WEBS, provenance=PROV)
    by_host = {n["domains"][0]["host_normalized"]: n for n in res.notices}
    assert by_host["rapidegroupe.com"]["entidad_raw"] == "Bankia Finance, S.A."
    assert by_host["europae-s.com"]["entidad_raw"] is None
    assert by_host["topfservices.com"]["entidad_raw"] == "topfservices.com"


def test_determinism_identical_inputs():
    a = parse_sujetos(UNAUTH, provenance=PROV)
    b = parse_sujetos(UNAUTH, provenance=PROV)
    assert [n["notice_id"] for n in a.notices] == \
           [n["notice_id"] for n in b.notices]


def test_source_type_never_collapsed():
    s = parse_sujetos(UNAUTH, provenance=PROV)
    p = parse_paginas(WEBS, provenance=PROV)
    assert {n["source_type"] for n in s.notices} == {"SUJETO_NO_AUTORIZADO"}
    assert {n["source_type"] for n in p.notices} == {"PAGINA_WEB_FRAUDULENTA"}
    assert {n["source_namespace"] for n in s.notices} == {NS_SUJETOS}
    assert {n["source_namespace"] for n in p.notices} == {NS_PAGINAS}
