"""Pipeline de normalizacion: CSV bytes -> notices enriquecidos.

Cada notice lleva: identidad (notice_id, record_version_id), campos raw,
fechas ISO, dominios extraidos, analisis de clon y provenance completa.
"""

from alertafin.clones import analyze_clone
from alertafin.domainex import extract_domains_from_record
from alertafin.parser import parse_csv


def enrich(raw: bytes, provenance: dict | None = None):
    """parse_csv + extraccion de dominios + analisis de clones."""
    res = parse_csv(raw, provenance=provenance)
    for n in res.notices:
        n["domains"] = extract_domains_from_record(n)
        n["clone"] = analyze_clone(n)
    return res
