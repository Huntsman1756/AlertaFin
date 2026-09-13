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


# ---------------------------------------------------------------------------
# G0-R: familias reales del holdout ciego (candidate-first)
# ---------------------------------------------------------------------------

def test_no_guarda_relacion_con_target_nombre_con_coma():
    """Holdout 09cfd68f: el nombre del target puede llevar comas internas."""
    n = notice(
        "CMX MARKET (CLON)", entidad_sec="HTTPS://WWW.CMXMARKET.COM/",
        observaciones=(
            "No guarda relaci\u00f3n con CMC MARKETS GERMANY GMBH, SUCURSAL "
            "EN ESPA\u00d1A, debidamente registrada en Espa\u00f1a como Empresa "
            "de Servicios de Inversi\u00f3n del Espacio Econ\u00f3mico Europeo "
            "con Sucursal con el n\u00ba 134."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == \
        "CMC MARKETS GERMANY GMBH, SUCURSAL EN ESPA\u00d1A"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_no_guarda_relacion_con_entidad_y_su_web():
    """Holdout ab1b2557: 'la entidad X y su web ...' trunca en 'y su web'."""
    n = notice(
        "THETA INVESTMENTS (CLON)",
        entidad_sec="HTTPS://WWW.SECTORTHETA.COM/ (CLON)",
        observaciones=(
            "No guarda relaci\u00f3n con la entidad SECTOR THETA AS y su web "
            "www.sector.no ,que estuvo registrada en la CNMV como Empresa de "
            "Servicios de Inversi\u00f3n del Espacio Econ\u00f3mico Europeo en "
            "Libre Prestaci\u00f3n con el n\u00ba 1.531."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == "SECTOR THETA AS"


def test_no_guarda_relacion_con_entidad_de_nombre():
    """Holdout c41e069a: 'NO GUARDAN RELACION CON LA ENTIDAD DE NOMBRE X'."""
    n = notice(
        "GROXBITLY.COM (CLONE)", entidad_sec="ELECTSBIT.COM (CLONE)",
        observaciones=(
            "LOS DOMINIOS QUE APARECEN EN EL LISTADO NO GUARDAN RELACI\u00d3N "
            "CON LA ENTIDAD DE NOMBRE VIE FINANCE AEPEY."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == "VIE FINANCE AEPEY"


def test_inverted_entidad_registrada_no_guarda_relacion():
    """Holdout 14ed93b1: el target es el sujeto gramatical, no lo que sigue
    a 'con' (aqui 'con ninguna de las paginas' no es candidato)."""
    n = notice(
        "TITANCFD.COM (CLONE)", entidad_sec="BITWAYNE.COM (CLONE)",
        observaciones=(
            "La entidad registrada en Grecia VIE FINANCE AEPEY no guarda "
            "relaci\u00f3n con ninguna de las p\u00e1ginas web advertidas."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == "VIE FINANCE AEPEY"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_suplantar_identidad_de_la_entidad():
    """Holdout (Wells Fargo): 'SUPLANTAR LA IDENTIDAD DE la ENTIDAD X' no debe
    capturar basura 'IDENTIDAD DE...'."""
    n = notice(
        "WELLS FARGO INTERNATIONAL BANK UNLIMITED COMPANY (CLONE)",
        observaciones=(
            "La entidad advertida, que ha usado las direcciones de correo "
            "electr\u00f3nico info@irelandfixedincometeam.com y "
            "james.martin@fixedincomedivision.com, HA INTENTADO SUPLANTAR LA "
            "IDENTIDAD DE la ENTIDAD Wells Fargo International Bank Unlimited "
            "Company, CON QUIEN no guarda ninguna relaci\u00f3n."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == \
        "Wells Fargo International Bank Unlimited Company"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_suplantando_identidad_sociedad_registrada_en_pais():
    """Holdout (BLI): 'suplantando de manera fraudulenta la identidad de la
    sociedad registrada en Luxemburgo X con quien no guardan'."""
    n = notice(
        "WWW.BANQUEDELUXEMBOURGINVESTMENTS.DE (CLONE)",
        observaciones=(
            "Personas desconocidas est\u00e1n suplantando de manera fraudulenta "
            "la identidad de la sociedad registrada en Luxemburgo BLI - "
            "Banque de Luxembourg Investments con quien no guardan ninguna "
            "relaci\u00f3n."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == "BLI - Banque de Luxembourg Investments"


def test_hacen_pasar_por_trabajadores_de_la_propia():
    """Holdout 22475062 (AMF): target = la propia autoridad suplantada."""
    n = notice(
        "VARIOS FRANCIA", tipo="OTRADV",
        observaciones=(
            "LA AMF ADVIERTE AL P\u00daBLICO SOBRE PERSONAS QUE SE HACEN PASAR "
            "POR TRABAJADORES DE LA PROPIA AMF PARA RECUPERAR LAS P\u00c9RDIDAS "
            "DE LOS INVERSORES"
        ),
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] == "AMF"


def test_imita_a_la_empresa_marker_and_target():
    """Holdout 4405b685 (FN unico de deteccion): 'imita a la empresa X'."""
    n = notice(
        "WEBTRADER.AXIONCAPITAL.CCS",
        observaciones=(
            "La p\u00e1gina web advertida, que utiliza la direcci\u00f3n de "
            "correo support@axioncapital.info  imita a la empresa Axion "
            "Capital S.\u00e0 r.l.\u00a0, con quien no guarda relaci\u00f3n"
        ),
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] == "Axion Capital S.\u00e0 r.l."
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_tomado_datos_entidad_autorizada_en_lugar():
    """Holdout (Bemo): 'ha tomado los datos de una entidad autorizada a
    prestar servicios de inversion en Dubai X, para enganar'. La coletilla
    'no guarda relacion con la firma autorizada en Dubai' NO aporta
    candidato (no hay nombre propio)."""
    n = notice(
        "BEMO INVESTMENT FIRM LTD (CLONE)",
        entidad_sec="WWW.BEMOINVESTMENTFIRMLTD.VIP (CLONE)",
        observaciones=(
            "La entidad advertida, que utiliza la direcci\u00f3n de correo "
            "electr\u00f3nico support@bemoinvestment.com, ha tomado los datos "
            "de una entidad autorizada a prestar servicios de inversi\u00f3n "
            "en Dubai Bemo Investment Firm Limited, para enga\u00f1ar a los "
            "inversores. La entidad advertida no guarda relaci\u00f3n con la "
            "firma autorizada en Dubai."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == "Bemo Investment Firm Limited"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_entidad_autorizada_del_mismo_nombre():
    """Holdout (OCM): 'del mismo nombre' resuelve contra entidad_raw sin el
    marcador (CLONE), solo si entidad_raw no es una URL/dominio."""
    n = notice(
        "OCM EMRU DEBTCO DESIGNATED ACTIVITY COMPANY (CLONE)",
        entidad_sec="HTTPS://OCMEMRUDEBTCODESIGNATEDACTIVITYCOMPANY.COM/ (CLONE)",
        observaciones=(
            "La entidad, que opera utilizando las direcciones de correo "
            "electr\u00f3nico info@OcmEmRuDebtcoDesignatedActivityCompany.com e "
            "info@ocmemrudebtcodac.com, ha tomado los datos de la entidad "
            "autorizada del mismo nombre, con quien no guarda relaci\u00f3n"
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == \
        "OCM EMRU DEBTCO DESIGNATED ACTIVITY COMPANY"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_mismo_nombre_rechaza_entidad_url():
    """Guard del 'mismo nombre': entidad_raw que es solo URL -> UNRESOLVED."""
    n = notice(
        "HTTPS://BELTONACCOUNTING.COM/ (CLONE)",
        observaciones=(
            "La entidad advertida ha tomado los datos de la entidad "
            "autorizada del mismo nombre, con quien no guarda relaci\u00f3n"
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] is None
    assert res["relation_status"] == "UNRESOLVED"


def test_multi_entidad_no_resuelve_target():
    """Holdout (PEOPLE FINANCE): 'dos entidades autorizadas ... X e Y' ->
    UNRESOLVED; nunca se elige una arbitrariamente."""
    n = notice(
        "PEOPLE FINANCE GROUP (CLONE)",
        entidad_sec="WWW.PEOPLEFINANCEGROUP.COM (CLONE)",
        observaciones=(
            "La entidad advertida, que utiliza la direcci\u00f3n de correo "
            "electr\u00f3nico info@peoplefinancegroup.com, ha tomado los datos "
            "de dos entidades autorizadas por el CBI, E & L Credit Ltd y "
            "Optal Financial Europe Limited, para enga\u00f1ar a los "
            "inversores. La entidad advertida no guarda relaci\u00f3n con "
            "ninguna firma autorizada por el CBI."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] is None
    assert res["relation_status"] == "UNRESOLVED"


def test_no_guarda_relacion_mojibake():
    """Tolerancia a caracter de reemplazo (U+FFFD) en 'relaci\\ufffdn'."""
    n = notice(
        "X (CLON)",
        observaciones=(
            "No guarda relaci\ufffdn con LEGIT CAPITAL S.A., debidamente "
            "registrada en Espa\ufffda."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == "LEGIT CAPITAL S.A."


def test_detalles_de_entidad_autorizada_por_autoridad():
    """Golden fc88be0b: 'SUPLANTADO LOS DETALLES DE UNA ENTIDAD AUTORIZADA POR
    <autoridad>, X'. La coletilla 'con la advertida' no aporta candidato."""
    n = notice(
        "MACQUARIE (CLONE)",
        observaciones=(
            "LA ENTIDAD ADVERTIDA, QUE UTILIZA LA DIRECCI\u00d3N DE CORREO "
            "ELECTR\u00d3NICO HA SUPLANTADO LOS DETALLES DE UNA ENTIDAD "
            "AUTORIZADA POR EL BANCO CENTRAL DE IRLANDA, Macquarie Bank "
            "Europe Designated Activity Company. LA ENTIDAD AUTORIZADA NO "
            "GUARDA RELACI\u00d3N CON LA ADVERTIDA."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == \
        "Macquarie Bank Europe Designated Activity Company"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_inverted_entidad_autorizada_en_pais():
    """Golden ea54f69b (BIL): 'La entidad autorizada en <pais> X no guarda
    relacion con la pagina web advertida' — 'pagina web advertida' no es
    candidato."""
    n = notice(
        "BANQUE INTERNATIONALE \u00e0 LUXEMBOURG (BIL) (CLONE)",
        observaciones=(
            "La entidad autorizada en Luxemburgo Banque Internationale "
            "\u00e0 Luxembourg (BIL) no guarda relaci\u00f3n con la p\u00e1gina "
            "web advertida."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == \
        "Banque Internationale \u00e0 Luxembourg (BIL)"
    assert res["relation_status"] == "EXPLICIT_SOURCE"


def test_identidad_de_la_entidad_legitima_adjetivo():
    """Golden 5877c672: 'LA ENTIDAD legitima X' — 'legitima' es adjetivo,
    no parte del nombre."""
    n = notice(
        "INCENTIVE INVESTMENT FUNDS PLC (CLONE)",
        observaciones=(
            "La entidad advertida, que ha usado direcciones de correo "
            "electr\u00f3nico con la estructura cargo.nombre@incentiveinvest.com "
            "HA SUPLANTADO LA IDENTIDAD DE LA ENTIDAD leg\u00edtima Incentive "
            "Investment Funds plc (CBI00134801), CON QUIEN no guarda ninguna "
            "relaci\u00f3n"
        ),
    )
    res = analyze_clone(n)
    assert res["clone_target_raw"] == \
        "Incentive Investment Funds plc (CBI00134801)"


def test_identidad_de_generico_plural_unresolved():
    """Golden 37d3a3c7: 'suplantan la identidad de bancos' — generico plural
    sin nombre propio -> UNRESOLVED."""
    n = notice(
        "DEUTSCHE BANK  (CLONE)",
        observaciones=(
            "La FSMA ha recibido informes de entidades que suplantan la "
            "identidad de bancos"
        ),
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] is None
    assert res["relation_status"] == "UNRESOLVED"


def test_identidad_dos_entidades_en_este_caso_unresolved():
    """Golden 62fe5512: 'la identidad de entidades legitimas, en este caso
    X e Y' -> multi-entidad -> UNRESOLVED."""
    n = notice(
        "GTI APP",
        observaciones=(
            "La FSMA advierte sobre grupos fraudulentos de WhatsApp que "
            "suplantan la identidad de entidades leg\u00edtimas, en este caso "
            "Bolero (KBC Bank NV) y GuardCap Asset Management Limited. Bolero "
            "y GuardCap no guardan ninguna relaci\u00f3n con dichos grupos."
        ),
    )
    res = analyze_clone(n)
    assert res["clone_detected"] is True
    assert res["clone_target_raw"] is None
    assert res["relation_status"] == "UNRESOLVED"
