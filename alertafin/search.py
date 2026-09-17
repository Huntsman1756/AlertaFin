"""Semantica de busqueda G0 (congelada):

- exact domain match  -> WARNED
- exact normalized name -> un unico sujeto -> WARNED (notices[])
- exact normalized name -> varios sujetos diferentes -> AMBIGUOUS
- partial/fuzzy match -> NUNCA suficiente para WARNED (no se implementa)
- fallo de fuente     -> SOURCE_UNAVAILABLE (nunca NO_WARNING_FOUND)

Sujeto: identidad de sujeto = casefold + colapso de espacios del nombre raw.
El nombre normalizado (diacriticos/puntuacion fuera) es solo clave de
busqueda; dos raw que difieren mas alla de mayusculas/espacios son
sujetos diferentes -> AMBIGUOUS. No hay fusion persistente de entidades.
"""

import re
from dataclasses import dataclass
from dataclasses import field as dc_field

from alertafin.domainex import _HOST_RE, normalize_domain
from alertafin.textnorm import collapse_ws, normalize_name


@dataclass
class CheckResult:
    status: str
    query: str
    notices: list = dc_field(default_factory=list)
    subjects: list = dc_field(default_factory=list)


def _subject_key(entidad_raw: str) -> str:
    return collapse_ws(entidad_raw).casefold()


class SearchIndex:
    def __init__(self, domain_map, name_map, notices):
        self.domain_map = domain_map
        self.name_map = name_map
        self.notices = notices

    @classmethod
    def build(cls, notices):
        domain_map = {}
        name_map = {}
        for n in notices:
            for d in n.get("domains") or []:
                domain_map.setdefault(d["host_normalized"], []).append(n)
            key = normalize_name(n.get("entidad_raw") or "")
            if key:
                name_map.setdefault(key, []).append(n)
        return cls(domain_map, name_map, list(notices))

    def by_notice_id(self, notice_id: str):
        for n in self.notices:
            if n["notice_id"] == notice_id:
                return n
        return None


def _looks_like_domain(query: str) -> bool:
    q = query.strip()
    if re.match(r"^[a-z][a-z0-9+.-]*://", q, re.IGNORECASE):
        return True
    if "." not in q:
        return False
    return bool(_HOST_RE.fullmatch(q))


def check(query: str, index):
    if index is None:
        return CheckResult(status="SOURCE_UNAVAILABLE", query=query)

    query = (query or "").strip()
    if not query:
        return CheckResult(status="NO_WARNING_FOUND", query=query)

    if _looks_like_domain(query):
        host = normalize_domain(query)
        hits = index.domain_map.get(host, []) if host else []
        if hits:
            return CheckResult(
                status="WARNED", query=query, notices=_dedupe(hits)
            )
        return CheckResult(status="NO_WARNING_FOUND", query=query)

    key = normalize_name(query)
    hits = index.name_map.get(key, [])
    if not hits:
        return CheckResult(status="NO_WARNING_FOUND", query=query)

    hits = _dedupe(hits)
    subjects = []
    for n in hits:
        sk = _subject_key(n.get("entidad_raw") or "")
        if sk not in subjects:
            subjects.append(sk)
    if len(subjects) > 1:
        return CheckResult(
            status="AMBIGUOUS", query=query, notices=hits, subjects=subjects
        )
    return CheckResult(status="WARNED", query=query, notices=hits, subjects=subjects)


def _dedupe(notices):
    seen = set()
    out = []
    for n in notices:
        nid = n["notice_id"]
        if nid not in seen:
            seen.add(nid)
            out.append(n)
    return out
