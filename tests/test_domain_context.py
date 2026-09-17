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


def test_obs_legit_url_after_legal_suffix_paren_excluded():
    """Regresion G0-R (holdout 98bcfb2b): 'S.L. (https://...)' no debe separar
    la URL de la entidad legitima de su contexto 'no guarda relacion'."""
    n = {
        "entidad_raw": "HTTPS://WWW.EAFI-GESTION.COM  (CLON)",
        "entidad_secundaria_raw": None,
        "observaciones_raw": (
            "No guarda relaci\u00f3n con Expert Timing Systems International "
            "EAF S.L. (https://www.etsfactory.com/), debidamente registrada "
            "en Espa\u00f1a como Empresa de Asesoramiento Financiero con el "
            "n\u00ba 33."
        ),
    }
    hosts = {d["host_normalized"] for d in extract_domains_from_record(n)}
    assert hosts == {"www.eafi-gestion.com"}


def test_obs_legit_url_after_double_legal_suffix_excluded():
    """Regresion G0-R (holdout f557f915): 'A.V., S.A. (<https://...>)'."""
    n = {
        "entidad_raw": "CSPARTNERS-GESTION (CLON)",
        "entidad_secundaria_raw": "CONTACT@INFOS-CSP.COM (CLON)",
        "observaciones_raw": (
            "NO guardan relaci\u00f3n con CAPITAL STRATEGIES PARTNERS, A.V., "
            "S.A. (<https://www.capitalstrategies.com/>) debidamente "
            "registrada en Espa\u00f1a como empresa de servicios de "
            "inversi\u00f3n (agencia de valores) con el n\u00ba 230."
        ),
    }
    hosts = {d["host_normalized"] for d in extract_domains_from_record(n)}
    assert hosts == set()


def test_obs_non_continuation_after_legit_fragment_not_inherited():
    """La herencia de descarte solo aplica a continuaciones parenteticas/URL;
    una frase nueva tras el corte conserva sus dominios."""
    n = {
        "entidad_raw": "ENTIDAD X",
        "entidad_secundaria_raw": None,
        "observaciones_raw": (
            "No guarda relaci\u00f3n con LEGIT S.L. La entidad advertida "
            "opera mediante https://warned-site.example."
        ),
    }
    hosts = {d["host_normalized"] for d in extract_domains_from_record(n)}
    assert hosts == {"warned-site.example"}


def test_entidad_fields_not_context_filtered():
    n = {
        "entidad_raw": "WWW.NO-GUARDA-RELACION.COM",
        "entidad_secundaria_raw": None,
        "observaciones_raw": None,
    }
    hosts = {d["host_normalized"] for d in extract_domains_from_record(n)}
    assert hosts == {"www.no-guarda-relacion.com"}
