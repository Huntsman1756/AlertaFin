"""Normalizacion tecnica de texto para matching.

normalize_name: NFKD -> sin diacriticos -> casefold -> puntuacion a espacio ->
colapso de espacios. Es una clave de BUSQUEDA, nunca reescritura de datos:
el valor raw de la fuente se conserva siempre.
"""

import unicodedata

_PUNCT_CATS = {"P", "S"}  # punctuation, symbols


def normalize_name(value: str) -> str:
    if value is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    no_marks = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    lowered = no_marks.casefold()
    out = []
    for ch in lowered:
        if ch.isspace() or ch in "-_" or unicodedata.category(ch)[0] in _PUNCT_CATS:
            out.append(" ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())


def collapse_ws(value: str) -> str:
    if value is None:
        return ""
    return " ".join(value.split())
