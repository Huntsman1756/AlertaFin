"""Mini-corpus golden para gates offline.

Filas sinteticas pero calcadas de los patrones REALES observados en
PaffNoAutorizadas (2026-09-13): (CLONE) en Entidad/Entidad Secundaria,
'se hace pasar por la entidad X, con la que no guarda relacion',
'U.MINT' (no-dominio), padding en Tipo, Fecha Baja con hora, emails en
Observaciones, URL con esquema, nombres con acentos y comas entrecomilladas.
"""

import csv
import io
from datetime import datetime, timedelta

from alertafin.identity import notice_id
from alertafin import SOURCE_NAMESPACE

ROWS = [
    # tipo, fecha, entidad, entidad_sec, cod_reg, pais, cpais, observaciones, fecha_baja
    ("NOAUTO", "09/09/2026", "MELZAPAY S.A.", "WWW.MELZAPAY.COM", "CSSF",
     "LUXEMBURGO", "LU", "", ""),
    ("NOAUTO", "09/09/2026",
     "INTERNATIONAL FUND SERVICES & ASSET MANAGEMENT S.A. (CLONE)", "", "CSSF",
     "LUXEMBURGO", "LU",
     "Personas desconocidas, que utilizan el correo electronico ifsam@eclipso.eu "
     "se hacen pasar de manera fraudulenta por la entidad autorizada "
     "INTERNATIONAL FUND SERVICES & ASSET MANAGEMENT S.A., con la que no guarda "
     "relacion.", ""),
    ("NOAUTO", "02/09/2026", "WWW.TOPFORCECOMPANY.COM (CLONE)",
     "WWW.TOPFORCECOMPANY.NET (CLONE)", "FSMA", "BELGICA", "BE",
     "Las paginas web advertidas se hacen pasar de manera fraudulenta por la "
     "entidad FORCE MANAGEMENT, con la que no guardan relacion.", ""),
    ("NOAUTO", "15/08/2026", "URBANMINT LTD", "U.MINT", "FCA", "REINO UNIDO", "GB",
     "", ""),
    ("NOAUTO    ", "02/02/2019", "GAMMA TRADING LTD", "", "CONSOB", "ITALIA", "IT",
     "", "25/03/2026 0:00:00"),
    ("OTRADV", "01/03/2021", "ALPHA INVEST", "", "FCA", "REINO UNIDO", "GB",
     "", ""),
    ("NOAUTO", "10/07/2026", "WWW.ZONA-INVERSION.ES", "",
     "CNMV", "ESPANA", "ES",
     "La web https://Zona-Inversion.es/trading ofrece servicios sin autorizacion.",
     ""),
    ("NOAUTO", "05/06/2026", "ENTIDAD SIMILAR SL", "", "CNMV", "ESPANA", "ES",
     "Nombre similar a la entidad ZETA CAPITAL S.A. No se afirma clonacion.", ""),
    ("NOAUTO", "20/05/2026", "WWW.CLON-BANCO.INFO", "", "CNMV", "ESPANA", "ES",
     "Se hace pasar por la entidad autorizada BANCO DEL NORTE S.A. "
     "(numero de registro 12345).", ""),
    ("NOAUTO", "11/11/2025", "\u00d1ANDU CAPITAL S.L.", "WWW.NANDU-CAPITAL.ES",
     "CNMV", "ESPANA", "ES", "", ""),
    ("OTRADV", "30/12/2024", "DIEZ & HIJOS, S.L.", "", "AMF", "FRANCIA", "FR",
     "", ""),
    # misma identidad que la fila 1, Observaciones distinto -> mismo notice_id,
    # distinto record_version_id (Observaciones NO forma parte de la identidad)
    ("NOAUTO", "09/09/2026", "MELZAPAY S.A.", "WWW.MELZAPAY.COM", "CSSF",
     "LUXEMBURGO", "LU",
     "Observacion ampliada posteriormente por el supervisor.", ""),
]

_HEADER = [
    "Tipo", "Fecha", "Entidad", "Entidad Secundaria",
    "C\u00f3digo regulador", "Pa\u00eds regulador",
    "C\u00f3digo pa\u00eds regulador", "Observaciones", "Fecha Baja",
]


def _csv_bytes(rows):
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(_HEADER)
    for row in rows:
        writer.writerow(row)
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def full_csv_bytes():
    return _csv_bytes(ROWS)


def notice_ids():
    """notice_id por posicion de fila, calculado con el modulo de identidad."""
    ids = []
    for row in ROWS:
        identity = {
            "source_namespace": SOURCE_NAMESPACE,
            "tipo_raw": row[0],
            "fecha_raw": row[1],
            "entidad_raw": row[2],
            "entidad_secundaria_raw": row[3] or None,
            "codigo_regulador_raw": row[4],
            "pais_regulador_raw": row[5],
        }
        ids.append(notice_id(identity))
    return ids


def golden_raw_expectations():
    ids = notice_ids()
    return [
        {"notice_id": ids[0], "fields": {"entidad_raw": "MELZAPAY S.A.",
                                         "entidad_secundaria_raw": "WWW.MELZAPAY.COM",
                                         "tipo_raw": "NOAUTO"}},
        {"notice_id": ids[3], "fields": {"entidad_secundaria_raw": "U.MINT"}},
        {"notice_id": ids[4], "fields": {"tipo_raw": "NOAUTO    ",
                                         "fecha_baja_raw": "25/03/2026 0:00:00",
                                         "fecha_baja": "2026-03-25T00:00:00"}},
        {"notice_id": ids[9], "fields": {"entidad_raw": "\u00d1ANDU CAPITAL S.L."}},
        {"notice_id": ids[10], "fields": {"entidad_raw": "DIEZ & HIJOS, S.L."}},
    ]


def is_valid_date(fecha_raw):
    if not fecha_raw:
        return False
    try:
        datetime.strptime(fecha_raw.strip(), "%d/%m/%Y")
        return True
    except ValueError:
        return False


def golden_domains():
    """{notice_id: hosts esperados} etiquetados a mano."""
    ids = notice_ids()
    return {
        ids[0]: {"www.melzapay.com"},
        ids[1]: set(),                      # solo un email: dominio excluido
        ids[2]: {"www.topforcecompany.com", "www.topforcecompany.net"},
        ids[3]: set(),                      # 'U.MINT' no es dominio
        ids[6]: {"www.zona-inversion.es",
                 "zona-inversion.es"},  # ambos literales: entidad y URL en obs
        ids[9]: {"www.nandu-capital.es"},
    }


def golden_clones():
    ids = notice_ids()
    return {
        ids[0]: {"clone": False},
        ids[1]: {"clone": True, "target": "INTERNATIONAL FUND SERVICES & ASSET MANAGEMENT S.A."},
        ids[2]: {"clone": True, "target": "FORCE MANAGEMENT"},
        ids[3]: {"clone": False},
        ids[4]: {"clone": False},
        ids[5]: {"clone": False},
        ids[6]: {"clone": False},
        ids[7]: {"clone": False},           # 'similar a' NO es clon
        ids[8]: {"clone": True, "target": "BANCO DEL NORTE S.A."},
        ids[9]: {"clone": False},
        ids[10]: {"clone": False},
        ids[11]: {"clone": False},
    }


def synthetic_csv(n):
    """n filas deterministas con identidades unicas (para gate de colisiones)."""
    rows = []
    base = datetime(2024, 1, 1)
    regs = [("CNMV", "ESPANA", "ES"), ("FSMA", "BELGICA", "BE"),
            ("CONSOB", "ITALIA", "IT"), ("FCA", "REINO UNIDO", "GB")]
    for i in range(n):
        fecha = (base + timedelta(days=i % 900)).strftime("%d/%m/%Y")
        cod, pais, cpais = regs[i % len(regs)]
        rows.append((
            "NOAUTO" if i % 3 else "OTRADV",
            fecha,
            f"ENTIDAD SINTETICA {i} S.A.",
            f"WWW.ENTIDAD-{i}.COM" if i % 2 else "",
            cod, pais, cpais,
            f"Fila sintetica numero {i} para gates." if i % 5 == 0 else "",
            "",
        ))
    return _csv_bytes(rows)
