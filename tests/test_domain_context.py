import pytest
from alertafin.domainex import extract_domains_from_record


def test_obs_legit_entity_context_excluded():
    """La web de la entidad legitima citada en Observaciones NO es un dominio
    del sujeto advertido (precision-first, congelado G0)."""
    n = {
        "entidad_raw": "EVER-SALES.COM (CLON)",
        "entidad_secundaria_raw": None,
        "observaciones_raw": (
            "que opera a traves de la direccion de correo electronico "
            "nombre.apellidos@ever-sales.com, no guardan relacion con EVER "
            "CAPITAL INVESTMENTS, S.V., S.A., y su web https://evercapitalsv.com, "
            "debidamente registrada en Espana como empresa de servicios de "
            "inversion con el n 259"
        ),
    }
    hosts = {d["host_normalized"] for d in extract_domains_from_record(n)}
    assert hosts == {"ever-sales.com"}


def test_obs_subject_web_still_extracted():
    n = {
        "entidad_raw": "FAKE BROKER LTD",
        "entidad_secundaria_raw": None,
        "observaciones_raw": (
            "La entidad opera mediante la web https://fake-broker.example/trading "
            "sin autorizacion."
        ),
    }
    hosts = {d["host_normalized"] for d in extract_domains_from_record(n)}
    assert hosts == {"fake-broker.example"}


def test_entidad_fields_not_context_filtered():
    n = {
        "entidad_raw": "WWW.NO-GUARDA-RELACION.COM",
        "entidad_secundaria_raw": None,
        "observaciones_raw": None,
    }
    hosts = {d["host_normalized"] for d in extract_domains_from_record(n)}
    assert hosts == {"www.no-guarda-relacion.com"}
