from alertafin.clones import analyze_clone


def notice(entidad, entidad_sec="", observaciones="", tipo="NOAUTO"):
    return {
        "tipo_raw": tipo,
        "entidad_raw": entidad,
        "entidad_secundaria_raw": entidad_sec or None,
        "observaciones_raw": observaciones or None,
    }


def test_clone_suffix_in_entidad_with_target_in_observaciones():
    n = notice(
        "WWW.BVFCAPITAL.COM (CLONE)",
        observaciones=(
            "LA web advertida se hace pasar de manera fraudulenta por la entidad "
            "BVF CAPITAL S.A. r.l., con la que no guarda relaci\u00f3n."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["relation_status"] == "EXPLICIT_SOURCE"
    assert res["clone_target_raw"] == "BVF CAPITAL S.A. r.l."
    assert res["clone_markers"]


def test_clone_entidad_secundaria_multiple_domains():
    n = notice(
        "WWW.TOPFORCECOMPANY.COM (CLONE)",
        entidad_sec="WWW.TOPFORCECOMPANY.NET (CLONE)",
        observaciones=(
            "Las p\u00e1ginas web advertidas se hacen pasar de manera fraudulenta "
            "por la entidad FORCE MANAGEMENT, con la que no guardan relaci\u00f3n."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] == "FORCE MANAGEMENT"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_suplanta_marker():
    n = notice(
        "ALPHA-TRADE.NET",
        observaciones="Entidad que suplanta a la autorizada BETA INVEST S.A.",
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] == "BETA INVEST S.A."


def test_no_clone_marker_no_relation():
    n = notice("MELZAPAY S.A.", entidad_sec="WWW.MELZAPAY.COM")
    res = analyze_clone(n)
    assert res["clone_detected"] is False
    assert res["relation_status"] is None
    assert res["clone_target_raw"] is None


def test_clone_marker_without_target_is_unresolved():
    n = notice("INTERNATIONAL FUND SERVICES & ASSET MANAGEMENT S.A. (CLONE)")
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] is None
    assert res["relation_status"] == "UNRESOLVED"


def test_precise_word_clon_not_substring():
    # 'clonico' / 'clonacion' no deben activar el marcador
    n = notice("ENTIDAD X", observaciones="Estudio clonacion de tarjetas.")
    res = analyze_clone(n)
    assert res["clone_detected"] is False


def test_clon_de_pattern():
    n = notice("WWW.FAKE-BANK.ES", observaciones="Web clon de la entidad BANCO REAL S.A.")
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] == "BANCO REAL S.A."


def test_utiliza_el_nombre_de_pattern():
    n = notice("FAKE CO", observaciones="utiliza el nombre de GAMA CAPITAL, S.A.")
    res = analyze_clone(n)
    assert res["clone_target_raw"] == "GAMA CAPITAL, S.A."
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_registry_number_boosts_resolution():
    n = notice(
        "WWW.CLON-SITE.COM",
        observaciones=(
            "Se hace pasar por la entidad autorizada BANCO DEL NORTE S.A. "
            "(n\u00ba registro 12345)."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == "BANCO DEL NORTE S.A."
    assert res["clone_target_registry_number"] == "12345"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_target_never_fuzzy_merged():
    """Si hay marcador pero el objetivo no es extraible con patron exacto,
    relation_status es UNRESOLVED y no se genera ningun CLONE_OF."""
    n = notice(
        "WWW.X.COM (CLONE)",
        observaciones="Sitio web con apariencia similar a otras entidades del sector.",
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] is None
    assert res["relation_status"] == "UNRESOLVED"


def test_similar_alone_is_not_clone_marker():
    n = notice("ENTIDAD Y", observaciones="Nombre similar a la entidad ZETA S.A.")
    res = analyze_clone(n)
    assert res["clone_detected"] is False
    assert res["relation_status"] is None
