"""Deteccion de clonado EXPLICITO y resolucion de objetivo.

Precision sobre recall:
- CLONE solo si la fuente lo afirma explicitamente: token '(CLONE)' o
  marcadores verbales: clon*/clone, suplanta*, imita* (G0-R), 'se hace(n)
  pasar', 'utiliza(n) el nombre de', 'falsa identidad'.
- 'similar a' NO es marcador de clon.
- clone_target_raw SOLO por patrones exactos sobre el propio registro; nunca
  por fuzzy matching ni conocimiento externo.

Resolucion de objetivo candidate-first (G0-R):
- Cada familia de patrones aporta candidatos; se validan y se deduplican
  (casefold + espacios colapsados).
- 0 candidatos validos -> UNRESOLVED; 1 -> EXPLICIT_SOURCE; >1 -> UNRESOLVED.
  Nunca se elige el primero arbitrariamente (p.ej. 'dos entidades X e Y').
- 'la entidad autorizada del mismo nombre' resuelve contra entidad_raw sin
  marcador (CLON)/(CLONE), solo si entidad_raw no es URL/dominio.
- PARSED_EXPLICIT queda reservado para casos con referencia estructurada
  (n de registro) sin nombre.
"""

import re
import unicodedata

CLONE_MARKERS = [
    (r"\(?\s*CLONE\s*\)?", "token_clone"),
    (r"\bclon(?:a|an|ado|ados|as|es|e|ar)?\b", "clon"),
    (r"\bsuplant\w*", "suplantacion"),
    (r"\bimit\w*", "imitacion"),
    (r"\bhac(?:e|en|emos)\s+pasar\b", "hace_pasar"),
    (r"\butiliz(?:a|an)\s+el\s+nombre\b", "utiliza_nombre"),
    (r"\bfals\w+\s+identidad\b", "falsa_identidad"),
]

# Prefijos opcionales de citacion de la entidad legitima en Observaciones.
# El lead-in completo exige articulo ('la entidad X', 'la firma autorizada');
# sin articulo no se salta nada para no comerse nombres propios ('ENTIDAD
# LEGIT S.A.' conserva 'ENTIDAD').
_LEAD_IN = (
    r"(?:(?:la|el|los|las)\s+"
    r"(?:(?:entidad|empresa|firma|sociedad)\s+)?"
    r"(?:autorizada\s+)?"
    r"(?:de\s+nombre\s+)?)?"
)

# Cada patron aporta candidatos en el grupo 't'. La captura es amplia y los
# cortes finos (debidamente, 'y su web', 'con quien', parentesis con URL...)
# se aplican de forma central en _clean_target. Los textos CNMV traen
# mojibake (U+FFFD): 'relaci\S*', 'inversi\S*' toleran 'relacin'.
_TARGET_PATTERNS = [
    # 'no guarda(n) relacion con [la entidad] [de nombre] X' (familia CNMV
    # dominante). El nombre puede llevar comas internas.
    r"no\s+guard\w*\s+relaci\S*\s+con\s+" + _LEAD_IN + r"(?P<t>[^;]+)",
    # Invertida: 'La entidad registrada|autorizada en <pais> X no guarda
    #  relacion ...'
    r"la\s+entidad\s+(?:registrada|autorizada)\s+en\s+\w+\s+"
    r"(?P<t>.+?)\s+no\s+guard\w*\s+relaci",
    # 'suplantar ... la identidad de [la] entidad|sociedad [legitima]
    #  [autorizada] [registrada en <pais>] X'
    r"suplant\w*[^;.]*?identidad\s+de\s+(?:la\s+|el\s+)?"
    r"(?:entidad|empresa|sociedad|firma)\s+"
    r"(?:(?:autorizada|leg\S*tima)\s+)?"
    r"(?:registrada\s+en\s+\w+\s+)?(?P<t>[^;]+)",
    # 'suplantado|tomado los detalles|datos de una entidad autorizada por
    #  <autoridad>, X' — exige la coma que introduce el nombre propio; sin
    #  ella ('...por el Banco Central.') no hay candidato.
    r"(?:datos|detalles)\s+de\s+una?\s+"
    r"(?:entidad|empresa|firma|sociedad)\s+autorizada\s+por\s+[^,;.]+"
    r"\s*,\s*(?P<t>[A-Z0-9][^;]*)",
    # 'se hacen pasar por trabajadores de la propia X para ...'
    r"por\s+trabajadores\s+de\s+la\s+propia\s+(?P<t>.+?)\s+para\s+",
    # 'imita(n) a la empresa|entidad X' (G0-R: tambien marcador de clon)
    r"\bimit\w*\s+a\s+(?:la\s+|el\s+)?"
    r"(?:entidad|empresa|sociedad|firma)\s+(?P<t>[^;]+)",
    # 'ha tomado los datos de una entidad autorizada a prestar servicios de
    #  inversion en <lugar> X, para enganar'
    r"datos\s+de\s+una\s+entidad\s+autorizada\s+a\s+prestar\s+servicios\s+de\s+"
    r"inversi\S*\s+en\s+\w+\s+(?P<t>.+?)[\s,]+para\s+enga",
    # Formas originales G0
    r"por\s+la\s+entidad(?:\s+autorizada)?\s+(?P<t>[^;]+)",
    # 'suplanta a [la] [entidad] [autorizada] X' — suprimido cuando la frase
    # es 'suplantar ... la identidad de ...' (la cubre el patron anterior).
    r"suplant\w*\s+(?![^;.]*?identidad\s+de\s)"
    r"(?:a\s+)?(?:la\s+|el\s+)?(?:entidad\s+)?(?:autorizada\s+)?"
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

# Cortes del candidato: se aplica el de menor posicion. Ninguno corta dentro
# de un nombre propio: '(EU)' no es URL, 'B.V.'/'S.A.' son abreviaturas, y
# los stops son coletillas CNMV siempre posteriores al nombre.
_CUT_PATTERNS = [
    _SENTENCE_PERIOD,
    # parentesis/corchete/angulo que abre URL o host: '(https://x)',
    # '(<https://x>)', '(www.x.com)'. '(EU)' u '(n 33)' no se cortan.
    re.compile(r"[(\[<]\s*<?\s*(?:(?:https?|ftp)://|www\.|"
               r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}\b)", re.IGNORECASE),
    re.compile(r"(?:https?|ftp)://|www\.", re.IGNORECASE),
    re.compile(r"[\s,]+con\s+(?:la\s+que|quien)\b", re.IGNORECASE),
    re.compile(r"[\s,]+debidamente\b", re.IGNORECASE),
    re.compile(r"[\s,]+y\s+su\s+web\b", re.IGNORECASE),
    re.compile(r"[\s,]+que\s+(?:estuvo|est\u00e1|esta|estaba)\s+registrad",
               re.IGNORECASE),
    re.compile(r"[\s,]+para\s+enga", re.IGNORECASE),
]

# Palabras funcionales al inicio del candidato: indican que el patron capturo
# una descripcion ('ninguna firma autorizada por el CBI', 'en Dubai'), no un
# nombre propio de entidad.
_FUNC_WORDS = {
    "ningun", "ninguna", "ninguno", "ningunas", "ningunos",
    "la", "el", "los", "las", "un", "una", "unos", "unas",
    "en", "de", "del", "con", "por", "para", "que", "su", "sus",
    "y", "o", "a", "se", "es", "son", "the", "of",
    # auto-referencias CNMV: 'la entidad advertida', 'la pagina web advertida'
    "advertida", "advertido", "advertidas", "advertidos",
    "pagina", "paginas", "web",
    # genericos descriptivos, no nombres propios: 'entidades legitimas, en
    # este caso ...', 'personas desconocidas'. OJO: 'banco', 'grupo' NO van
    # aqui: pueden abrir un nombre propio real ('BANCO REAL S.A.').
    "entidad", "entidades", "empresa", "empresas", "sociedad",
    "sociedades", "firma", "firmas", "persona", "personas",
}

# 'X y Y' con Y en mayuscula dentro del candidato: probable enumeracion de
# dos entidades (criterio conservador del etiquetado -> UNRESOLVED).
_MULTI_ENTITY = re.compile(r"\s+y\s+[A-Z\u00c0-\u00de]")

_SAME_NAME_RE = re.compile(
    r"(?:entidad|empresa|firma|sociedad)\s+autorizada\s+del\s+mismo\s+nombre",
    re.IGNORECASE)
_CLONE_TAG_RE = re.compile(r"\s*\(\s*CLONE?\s*\)", re.IGNORECASE)


def _clean_target(t: str) -> str:
    t = t.strip(_STRIP_EDGES)
    t = re.sub(r"\s+", " ", t)
    cut = len(t)
    for pat in _CUT_PATTERNS:
        m = pat.search(t)
        if m:
            cut = min(cut, m.start())
    t = t[:cut]
    t = _REG_PAREN_TAIL.sub("", t)
    t = re.sub(r"\s+autorizada$", "", t, flags=re.IGNORECASE)
    t = t.strip(_STRIP_EDGES)
    if t.endswith(".") and not _ABBREV_TAIL.search(t):
        t = t[:-1].rstrip(_STRIP_EDGES)
    return t


def _looks_like_target(candidate: str) -> bool:
    if len(candidate) < 2:
        return False
    first = candidate.split(" ", 1)[0].strip(_STRIP_EDGES + ";:()").lower()
    # insensible a acentos: 'pagina' cubre 'p\u00e1gina'
    first = "".join(
        ch for ch in unicodedata.normalize("NFD", first)
        if unicodedata.category(ch) != "Mn")
    if first in _FUNC_WORDS:
        return False
    if _MULTI_ENTITY.search(candidate):
        return False
    return True


def _is_urlish(name: str) -> bool:
    if re.match(r"^[a-z][a-z0-9+.-]*://", name, re.IGNORECASE):
        return True
    if re.match(r"^www\.", name, re.IGNORECASE):
        return True
    # dominio desnudo sin espacios: FOO.COM, WWW.FOO.COM, FOO.COM/
    return bool(re.fullmatch(r"[\w\-]+(?:\.[\w\-]+)+/?", name))


def _same_name_candidate(notice):
    """'entidad autorizada del mismo nombre': el target es entidad_raw sin el
    marcador (CLON)/(CLONE), solo si entidad_raw es un nombre propio."""
    entidad = notice.get("entidad_raw") or ""
    name = _CLONE_TAG_RE.sub("", entidad).strip(_STRIP_EDGES)
    if not name or _is_urlish(name):
        return None
    return name


def _target_candidates(notice):
    """Candidatos validos a clone_target, deduplicados (casefold+espacios)."""
    obs = notice.get("observaciones_raw") or ""
    cands = []
    for pat in _TARGET_PATTERNS:
        for m in re.finditer(pat, obs, flags=re.IGNORECASE):
            c = _clean_target(m.group("t"))
            if c and _looks_like_target(c):
                cands.append(c)
    if _SAME_NAME_RE.search(obs):
        c = _same_name_candidate(notice)
        if c:
            cands.append(c)
    seen, uniq = set(), []
    for c in cands:
        key = re.sub(r"\s+", " ", c).strip().casefold()
        if key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


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
    target = None
    reg_num = None
    if clone_detected:
        candidates = _target_candidates(notice)
        # 0 -> UNRESOLVED, 1 -> EXPLICIT_SOURCE, >1 -> UNRESOLVED.
        if len(candidates) == 1:
            target = candidates[0]
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
