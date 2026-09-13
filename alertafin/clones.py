"""Deteccion de clonado EXPLICITO y resolucion de objetivo.

Congelado G0 (precision sobre recall):
- CLONE solo si la fuente lo afirma explicitamente: token '(CLONE)' o
  marcadores verbales: clon*/clone, suplanta*, 'se hace(n) pasar',
  'utiliza(n) el nombre de', 'falsa identidad'.
- 'similar a' NO es marcador de clon.
- clone_target_raw SOLO por patrones exactos sobre el propio registro; nunca
  por fuzzy matching ni conocimiento externo.
- Sin objetivo extraible -> relation_status = UNRESOLVED (no se genera CLONE_OF).
- Con objetivo explicito -> EXPLICIT_SOURCE. PARSED_EXPLICIT queda reservado
  para casos con referencia estructurada (n de registro) sin nombre.
"""

import re

CLONE_MARKERS = [
    (r"\(?\s*CLONE\s*\)?", "token_clone"),
    (r"\bclon(?:a|an|ado|ados|as|es|e|ar)?\b", "clon"),
    (r"\bsuplant\w*", "suplantacion"),
    (r"\bhac(?:e|en|emos)\s+pasar\b", "hace_pasar"),
    (r"\butiliz(?:a|an)\s+el\s+nombre\b", "utiliza_nombre"),
    (r"\bfals\w+\s+identidad\b", "falsa_identidad"),
]

# El objetivo se captura de forma amplia y se trunca solo en frontera de
# frase (punto seguido de mayuscula) o en ';'; se limpia la coletilla
# ', con la que no guarda(n) relacion' tipica de CNMV. Los puntos de
# abreviatura (S.A., S.L.) se conservan.
_TARGET_PATTERNS = [
    r"por\s+la\s+entidad(?:\s+autorizada)?\s+(?P<t>[^;]+)",
    r"suplant\w*\s+(?:a\s+)?(?:la\s+|el\s+)?(?:entidad\s+)?(?:autorizada\s+)?"
    r"(?P<t>[A-Z0-9][^;]+)",
    r"clon\w*\s+de\s+la\s+entidad\s+(?P<t>[^;]+)",
    r"clon\w*\s+de\s+(?P<t>[A-Z0-9][^;]+)",
    r"utiliz\w*\s+el\s+nombre\s+de\s+(?:la\s+|el\s+)?(?:entidad\s+)?"
    r"(?:autorizada\s+)?(?P<t>[^;]+)",
]

_REG_NUMBER_RE = re.compile(
    r"\bn(?:\u00ba|\u00b0|\u00famero|ro)?\.?\s*(?:(?:de\s+)?registro\s*)?"
    r"(?:\u00ba|\u00b0)?\s*[:#]?\s*(\d{3,8})",
    re.IGNORECASE,
)
_REG_NUM_FALLBACK = re.compile(
    r"registro\w*\D{0,20}(\d{3,8})", re.IGNORECASE
)

_REG_PAREN_TAIL = re.compile(
    r"\s*\(\s*(?:n[\u00ba\u00b0]|registro|n\u00famero)[^)]*\)\s*\.?\s*$",
    re.IGNORECASE,
)
_STRIP_EDGES = " \t\"'\u201c\u201d,"
_ABBREV_TAIL = re.compile(r"(?:^|\s)(?:[A-Za-z]\.){1,4}[A-Za-z]?\.?$")

_SENTENCE_PERIOD = re.compile(r"\.\s+(?=[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1])|;")


def _clean_target(t: str) -> str:
    t = t.strip(_STRIP_EDGES)
    t = re.sub(r"\s+", " ", t)
    m = _SENTENCE_PERIOD.search(t)
    if m:
        t = t[: m.start()]
    t = re.sub(r",?\s+con\s+la\s+que\s+.*$", "", t, flags=re.IGNORECASE)
    t = _REG_PAREN_TAIL.sub("", t)
    t = re.sub(r"\s+autorizada$", "", t, flags=re.IGNORECASE)
    t = t.strip(_STRIP_EDGES)
    if t.endswith(".") and not _ABBREV_TAIL.search(t):
        t = t[:-1].rstrip(_STRIP_EDGES)
    return t


def _find_target(text: str):
    for pat in _TARGET_PATTERNS:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            cleaned = _clean_target(m.group("t"))
            if cleaned:
                return cleaned
    return None


def analyze_clone(notice: dict) -> dict:
    """clone_detected, markers, target raw, n de registro y relation_status."""
    haystacks = " || ".join(
        str(notice.get(f) or "")
        for f in (
            "tipo_raw",
            "entidad_raw",
            "entidad_secundaria_raw",
            "observaciones_raw",
        )
    )
    markers = []
    for pat, name in CLONE_MARKERS:
        if re.search(pat, haystacks, flags=re.IGNORECASE):
            markers.append(name)
    clone_detected = bool(markers)

    obs = notice.get("observaciones_raw") or ""
    target = _find_target(obs) if clone_detected else None
    reg_num = None
    if clone_detected:
        m = _REG_NUMBER_RE.search(obs) or _REG_NUM_FALLBACK.search(obs)
        if m:
            reg_num = m.group(1)

    if not clone_detected:
        relation_status = None
    elif target:
        relation_status = "EXPLICIT_SOURCE"
    elif reg_num:
        relation_status = "PARSED_EXPLICIT"
    else:
        relation_status = "UNRESOLVED"

    return {
        "clone_detected": clone_detected,
        "clone_markers": markers,
        "clone_target_raw": target,
        "clone_target_registry_number": reg_num,
        "relation_status": relation_status,
    }
