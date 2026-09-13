"""Ingesta DGSFP (G1-WI.B): parser determinista de las dos fuentes.

Fuentes congeladas en `g1-wi/probe/` (snapshot G1-WI.A):

- `dgsfp.sujetos_no_autorizados`: lista plana en un campo
  `ms-rtestate-field`; un `<p>` por registro bajo cabeceras
  `Año YYYY` / `Resto de años`.
- `dgsfp.paginas_web_fraudulentas`: anuncio estatico; un `<p><a>` por
  registro (URL + denominacion de entidad entre parentesis).

Reglas congeladas (`g1-wi/pre-ingestion-freeze.md`):

- `warning_date` = ABSENT en ambas fuentes; `Año YYYY` es
  `context_period` con precision YEAR, nunca fecha sintetica.
- Duplicados de origen preservados: la identidad distingue ocurrencias
  por seccion + indice de ocurrencia; `record_version_id` =
  sha256(raw `<p>` bytes).
- Evidencia de clon solo cuando la fuente la afirma: la nota
  `(sin vínculos ni relación con X, que es entidad aseguradora
  autorizada)` marca confusion con entidad autorizada -> clone_detected
  + EXPLICIT_SOURCE con target determinista. Nunca se inventa.
"""

import hashlib
import html as _html
import json
import re
from dataclasses import dataclass, field as dc_field

from alertafin.domainex import normalize_domain

NS_SUJETOS = "dgsfp.sujetos_no_autorizados"
NS_PAGINAS = "dgsfp.paginas_web_fraudulentas"

PARSER_VERSION_DGSFP = "g1wi-dgsfp-1.0.0"

SOURCE_TYPE_SUJETOS = "SUJETO_NO_AUTORIZADO"
SOURCE_TYPE_PAGINAS = "PAGINA_WEB_FRAUDULENTA"

SECTION_RE = re.compile(r"^(Año\s+\d{4}|Resto de años)$", re.IGNORECASE)
SECTION_YEAR_RE = re.compile(r"^Año\s+(\d{4})$", re.IGNORECASE)
LIST_END_RE = re.compile(r"^SUJETOS AUTORIZADOS\b", re.IGNORECASE)

# Nota parentetica al final del registro que declara confusion con una
# entidad autorizada ('sin vínculos ni relación con X, que es entidad
# aseguradora autorizada'). El contenido puede llevar parentesis internos
# (p.ej. '(EUROPE)'), por eso se ancla al cierre final del registro.
_NOTA_RE = re.compile(
    r"\(\s*(sin\s+v[íi]nculos\s+ni\s+relaci[oó]n\s+con\s+.+?)\s*\)\s*$",
    re.IGNORECASE | re.DOTALL,
)
# Dentro de la nota: 'con X, que es entidad aseguradora autorizada'.
_NOTA_TARGET_RE = re.compile(
    r"relaci[oó]n\s+con\s+(?P<t>.+?)\s*,?\s*que\s+es\s+entidad\s+"
    r"[a-záéíóú\s]*autorizad", re.IGNORECASE | re.DOTALL,
)


class ParseError(Exception):
    pass


@dataclass
class DgsfpResult:
    source_namespace: str
    notices: list = dc_field(default_factory=list)
    row_errors: list = dc_field(default_factory=list)


def content_fields(text: str) -> list:
    """Todos los div `ms-rtestate-field` (conteo de <div> anidados)."""
    out = []
    for m in re.finditer(r'<div[^>]*class="ms-rtestate-field"', text):
        start = m.start()
        depth = 0
        end = len(text)
        for t in re.finditer(r"<div\b|</div>", text[start:]):
            depth += 1 if t.group(0) == "<div" else -1
            if depth == 0:
                end = start + t.end()
                break
        out.append(text[start:end])
    return out


def _inner_text(fragment: str) -> str:
    """Texto visible de un fragmento HTML: sin tags, entidades decodificadas,
    espacios colapsados."""
    txt = re.sub(r"<[^>]+>", " ", fragment)
    txt = _html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _p_elements(region: str):
    """(inner_html, raw_element) de cada <p>...</p> en orden de documento."""
    return [
        (m.group(1), m.group(0))
        for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", region,
                             re.DOTALL | re.IGNORECASE)
    ]


def _notice_id(fields: dict) -> str:
    keys = ["source_namespace", "source_type", "entidad_raw", "url_raw",
            "section", "occurrence_index"]
    payload = {k: (fields.get(k) or None) for k in keys}
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _section_code(section_raw: str) -> str:
    if SECTION_YEAR_RE.match(section_raw):
        return "ANO_" + SECTION_YEAR_RE.match(section_raw).group(1)
    return "RESTO"


def _context_period(section_raw: str) -> dict:
    m = SECTION_YEAR_RE.match(section_raw)
    if m:
        return {"raw": section_raw, "year": int(m.group(1)),
                "precision": "YEAR"}
    return {"raw": section_raw, "year": None, "precision": None}


def _split_nota(text: str):
    """Separa nota parentetica final si es disclaimer de relacion."""
    m = _NOTA_RE.search(text)
    if not m:
        return text, None
    return text[:m.start()].strip(), m.group(1).strip()


def _clone_sujetos(nota_raw):
    """Evidencia explicita de confusion con entidad autorizada (DGSFP)."""
    if not nota_raw:
        return {"clone_detected": False, "clone_markers": [],
                "clone_target_raw": None, "relation_status": None}
    m = _NOTA_TARGET_RE.search(nota_raw)
    target = m.group("t").strip(" .,") if m else None
    return {
        "clone_detected": True,
        "clone_markers": ["sin_vinculos_relacion"],
        "clone_target_raw": target,
        "relation_status": "EXPLICIT_SOURCE" if target else "UNRESOLVED",
    }


def _clone_paginas():
    return {"clone_detected": False, "clone_markers": [],
            "clone_target_raw": None, "relation_status": None}


def parse_sujetos(raw: bytes, provenance: dict | None = None) -> DgsfpResult:
    """Lista «Sujetos no autorizados»: un <p> por registro por seccion."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError(f"encoding no utf-8: {exc}") from exc
    fields = content_fields(text)
    if not fields:
        raise ParseError("sin campo ms-rtestate-field")

    prov = dict(provenance or {})
    prov.setdefault("parser_version", PARSER_VERSION_DGSFP)
    prov.setdefault("source_namespace", NS_SUJETOS)

    res = DgsfpResult(source_namespace=NS_SUJETOS)
    section_raw = None
    occ = 0
    records = 0
    for inner_html, raw_el in _p_elements(fields[0]):
        t = _inner_text(inner_html)
        if not t:
            continue
        if SECTION_RE.match(t):
            section_raw = t
            occ = 0
            continue
        if LIST_END_RE.match(t):
            section_raw = None
            break
        if section_raw is None:
            continue
        entidad_raw, nota_raw = _split_nota(t)
        rec = {
            "notice_id": None,
            "record_version_id": hashlib.sha256(
                raw_el.encode("utf-8")).hexdigest(),
            "row_number": records + 1,
            "source_namespace": NS_SUJETOS,
            "source_type": SOURCE_TYPE_SUJETOS,
            "authority": "DGSFP",
            "entidad_raw": entidad_raw,
            "nota_raw": nota_raw,
            "url_raw": None,
            "section_raw": section_raw,
            "section": _section_code(section_raw),
            "occurrence_index": occ,
            "context_period": _context_period(section_raw),
            "warning_date": None,
            "warning_date_status": "ABSENT",
            "domains": [],
            "clone": _clone_sujetos(nota_raw),
            "raw_row_bytes": raw_el.encode("utf-8"),
            "provenance": prov,
        }
        rec["notice_id"] = _notice_id(rec)
        res.notices.append(rec)
        occ += 1
        records += 1
    if records == 0:
        raise ParseError("estructura cambiada: 0 registros en sujetos")
    return res


def parse_paginas(raw: bytes, provenance: dict | None = None) -> DgsfpResult:
    """Anuncio «Páginas web fraudulentas»: un <p><a href> por registro."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError(f"encoding no utf-8: {exc}") from exc
    fields = content_fields(text)
    if len(fields) < 2:
        raise ParseError("estructura cambiada: campos insuficientes")

    prov = dict(provenance or {})
    prov.setdefault("parser_version", PARSER_VERSION_DGSFP)
    prov.setdefault("source_namespace", NS_PAGINAS)

    res = DgsfpResult(source_namespace=NS_PAGINAS)
    occ = 0
    for region in fields:
        for inner_html, raw_el in _p_elements(region):
            a = re.search(r'href="([^"]+)"', inner_html)
            if not a:
                continue
            url_raw = _html.unescape(a.group(1))
            host = normalize_domain(url_raw)
            t = _inner_text(inner_html)
            m = re.search(r"\(\s*[\"'“”]?(?P<t>.+?)[\"'“”]?\s*\)\s*$", t)
            entidad_raw = m.group("t") if m else None
            domains = ([{"raw": url_raw, "host_normalized": host,
                         "source_field": "url_raw"}] if host else [])
            rec = {
                "notice_id": None,
                "record_version_id": hashlib.sha256(
                    raw_el.encode("utf-8")).hexdigest(),
                "row_number": occ + 1,
                "source_namespace": NS_PAGINAS,
                "source_type": SOURCE_TYPE_PAGINAS,
                "authority": "DGSFP",
                "entidad_raw": entidad_raw,
                "nota_raw": None,
                "url_raw": url_raw,
                "section_raw": None,
                "section": None,
                "occurrence_index": occ,
                "context_period": {"raw": None, "year": None,
                                   "precision": None},
                "warning_date": None,
                "warning_date_status": "ABSENT",
                "domains": domains,
                "clone": _clone_paginas(),
                "raw_row_bytes": raw_el.encode("utf-8"),
                "provenance": prov,
            }
            rec["notice_id"] = _notice_id(rec)
            res.notices.append(rec)
            occ += 1
    if occ == 0:
        raise ParseError("estructura cambiada: 0 registros en paginas")
    return res


def _notice_for_jsonl(n: dict) -> dict:
    out = dict(n)
    out["raw_row_bytes_hex"] = out.pop("raw_row_bytes").hex()
    return out


__all__ = [
    "NS_SUJETOS",
    "NS_PAGINAS",
    "PARSER_VERSION_DGSFP",
    "SOURCE_TYPE_SUJETOS",
    "SOURCE_TYPE_PAGINAS",
    "DgsfpResult",
    "ParseError",
    "content_fields",
    "parse_sujetos",
    "parse_paginas",
]
