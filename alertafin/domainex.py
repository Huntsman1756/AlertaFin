"""Extraccion y normalizacion determinista de dominios.

Decisiones congeladas (G0, precision-first):
- Los dominios tras '@' (correos) NO se extraen: suelen ser proveedores de
  correo, no dominios publicados como usados por el sujeto advertido.
- foo.example.com != example.com: los subdominios NUNCA se colapsan.
- www. NO se elimina: CNMV publica hosts concretos.
- Se conserva siempre el valor raw y se genera host_normalized
  (minusculas, sin esquema/credenciales/puerto/path, sin punto final, IDNA).
- Denylist de tokens observados que no son dominios (p.ej. 'U.MINT', nombre
  de producto): lista explicita, documentada y congelada por evidencia.
"""

import re
from urllib.parse import urlsplit

import idna

# Tokens exactos (en minusculas) que parecen dominios pero no lo son.
HOST_DENYLIST = {
    "u.mint",
}

_URL_RE = re.compile(
    r"\b(?:https?|ftp)://[^\s\"'<>()\[\]]+", re.IGNORECASE
)

# Contexto de ENTIDAD LEGITIMA en Observaciones: los dominios que aparecen
# en estos fragmentos pertenecen a la entidad suplantada citada por CNMV,
# no al sujeto advertido. Se excluyen de USES_DOMAIN (precision-first).
_LEGIT_CONTEXT_RE = re.compile(
    r"no\s+guard\w+\s+relaci|web\s+oficial|sitio\s+oficial|p[a\u00e1]gina\s+oficial"
    r"|\bsu\s+web\b|p[a\u00e1]gina(?:s)?\s+web\s+de\s+la\s+entidad"
    r"|p[a\u00e1]gina(?:s)?\s+de\s+la\s+entidad",
    re.IGNORECASE,
)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+|\n")


def _obs_fragments(text: str):
    for fragment in _SENTENCE_SPLIT_RE.split(text):
        if fragment and not _LEGIT_CONTEXT_RE.search(fragment):
            yield fragment
_HOST_BODY = r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?"
_HOST_RE = re.compile(
    r"(?<![\w@.\-])"                     # no letra, '@' (email), punto o guion antes
    r"(?P<host>"
    + _HOST_BODY
    + r"(?:\."
    + _HOST_BODY
    + r")+)"
    r"(?![\w@.\-])",                     # no continua como host/email
    re.IGNORECASE,
)


def _tld_of(host: str):
    return host.rsplit(".", 1)[-1]


def _valid_host(host: str) -> bool:
    if host in HOST_DENYLIST:
        return False
    labels = host.split(".")
    if len(labels) < 2:
        return False
    if any(not lbl for lbl in labels):
        return False
    tld = labels[-1]
    if len(tld) < 2 or not tld.isalpha():
        return False
    return True


def _normalize_host(host: str):
    host = host.strip().strip(".").lower()
    if not host or not _valid_host(host):
        return None
    try:
        return idna.encode(host, uts46=True).decode("ascii").lower()
    except (idna.IDNAError, UnicodeError):
        return host


def normalize_domain(raw: str):
    """Dominio o URL cruda -> host normalizado. None si no es un host valido."""
    if not raw:
        return None
    candidate = raw.strip()
    if re.match(r"^[a-z][a-z0-9+.-]*://", candidate, re.IGNORECASE):
        try:
            parts = urlsplit(candidate)
            hostname = parts.hostname or ""
        except ValueError:
            return None
        return _normalize_host(hostname)
    return _normalize_host(candidate)


def extract_domains_from_text(text):
    """Devuelve [{raw, host_normalized}] en orden de aparicion, deduplicado."""
    if not text:
        return []
    findings = []
    seen = set()

    def add(raw_value, host):
        if host and host not in seen:
            seen.add(host)
            findings.append({"raw": raw_value, "host_normalized": host})

    remainder = text
    for m in _URL_RE.finditer(text):
        raw_url = m.group(0)
        host = normalize_domain(raw_url)
        if host:
            add(raw_url, host)
        remainder = remainder.replace(raw_url, " ")

    for m in _HOST_RE.finditer(remainder):
        token = m.group("host")
        host = _normalize_host(token)
        if host:
            add(token, host)
    return findings


def extract_domains_from_record(notice):
    """Extrae dominios de los campos de un notice ya normalizado.

    Devuelve [{raw, host_normalized, source_field}] sin duplicar hosts entre
    campos: el primer campo en el orden fijo donde aparece gana el raw.
    """
    out = []
    seen = set()
    for field_name in ("entidad_raw", "entidad_secundaria_raw", "observaciones_raw"):
        if field_name == "observaciones_raw":
            # En Observaciones se excluyen los fragmentos con contexto de
            # entidad legitima (su web, web oficial, no guarda relacion...).
            texts = _obs_fragments(notice.get(field_name) or "")
        else:
            texts = [notice.get(field_name) or ""]
        for text in texts:
            for item in extract_domains_from_text(text):
                if item["host_normalized"] in seen:
                    continue
                seen.add(item["host_normalized"])
                out.append({**item, "source_field": field_name})
    return out
