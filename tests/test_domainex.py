from alertafin.domainex import extract_domains_from_text, normalize_domain


def test_uppercase_www_host():
    out = extract_domains_from_text("WWW.MELZAPAY.COM")
    assert [d["raw"] for d in out] == ["WWW.MELZAPAY.COM"]
    assert [d["host_normalized"] for d in out] == ["www.melzapay.com"]


def test_clone_suffix_ignored():
    out = extract_domains_from_text("WWW.TOPFORCECOMPANY.NET (CLONE)")
    assert [d["raw"] for d in out] == ["WWW.TOPFORCECOMPANY.NET"]


def test_hyphens_and_digits():
    out = extract_domains_from_text("WWW.LOOM-HELLO-95431323.FIGMA.SITE")
    assert out[0]["host_normalized"] == "www.loom-hello-95431323.figma.site"


def test_url_with_scheme_port_path():
    out = extract_domains_from_text(
        "http://User:Pass@Zona-Inversion.COM:8080/trading/login"
    )
    assert out[0]["host_normalized"] == "zona-inversion.com"
    assert out[0]["raw"] == "http://User:Pass@Zona-Inversion.COM:8080/trading/login"


def test_https_and_www_preserved_as_distinct_fact():
    assert normalize_domain("WWW.Example.com") == "www.example.com"
    assert normalize_domain("example.com") == "example.com"
    assert normalize_domain("www.example.com") != normalize_domain("example.com")


def test_trailing_dot_and_case():
    assert normalize_domain("EXAMPLE.COM.") == "example.com"


def test_unicode_host_idna():
    out = normalize_domain("Espa\u00f1a-Inversiones.com")
    assert out == "xn--espaa-inversiones-ixb.com"


def test_email_domain_excluded():
    # Los dominios tras '@' son proveedores de correo, no dominios del sujeto:
    # decision precision-first congelada para G0.
    assert extract_domains_from_text("correo ifsam@eclipso.eu") == []


def test_non_domain_names_excluded():
    assert extract_domains_from_text("U.MINT") == []
    assert extract_domains_from_text("GLOBAL CAPITAL S.A.") == []
    assert extract_domains_from_text("version 1.2.3") == []
    assert extract_domains_from_text("cuesta 1.234,56 euros") == []


def test_idna_equivalent_forms_match():
    # El host unicode y su forma punycode normalizan al mismo key.
    assert normalize_domain("españa.com") == normalize_domain("xn--espaa-rta.com")


def test_ip_and_single_label_excluded():
    assert normalize_domain("192.168.1.1") is None
    assert normalize_domain("localhost") is None


def test_multiple_domains_in_order_dedup():
    text = "web www.a.com y tambien www.B.com y de nuevo www.a.com"
    hosts = [d["host_normalized"] for d in extract_domains_from_text(text)]
    assert hosts == ["www.a.com", "www.b.com"]


def test_subdomains_not_collapsed():
    text = "cuenta.foo.example.com y foo.example.com"
    hosts = [d["host_normalized"] for d in extract_domains_from_text(text)]
    assert hosts == ["cuenta.foo.example.com", "foo.example.com"]
