"""Genera g0-r/golden-adjudications.jsonl a partir de g0-r/_divergent_dump.json.

Los notice_id se leen del dump (procedente del corpus), no se transcriben.
Las decisiones/new_value son la adjudicacion manual caso a caso contra raw.
"""
import json
import sys
from pathlib import Path

DUMP = Path("g0-r/_divergent_dump.json")
OUT = Path("g0-r/golden-adjudications.jsonl")
SCOPE = "G0-R regression only"

# prefix -> (decision, new_value, reason)
T = {
    "bac12ac9": ("CORRECT_LABEL", "SOLVENTIS, SV, SA",
                 "Raw: 'No guarda relacion con SOLVENTIS, SV, SA, (https://solventis.es/) debidamente registrada'. Target explicito unico."),
    "5bdfce7b": ("CORRECT_LABEL", "SOLVENTIS, SV, SA",
                 "Mismo raw: 'No guarda relacion con SOLVENTIS, SV, SA, ...'. Target explicito unico."),
    "35b2197e": ("CORRECT_LABEL", "SOLVENTIS, SV, SA",
                 "Mismo raw: 'No guarda relacion con SOLVENTIS, SV, SA, ...'. Target explicito unico."),
    "af3e3b9f": ("CORRECT_LABEL", "OLYMPUS EQUITY EUROPE, FI",
                 "Raw: 'No guarda relacion con OLYMPUS EQUITY EUROPE, FI, debidamente registrado'. Target explicito unico."),
    "a3b8fc7c": ("CORRECT_LABEL", "OLYMPUS EQUITY EUROPE, FI",
                 "Mismo raw: 'No guarda relacion con OLYMPUS EQUITY EUROPE, FI'. Target explicito unico."),
    "682a85dc": ("CORRECT_LABEL", "AXON WEALTH ADVISORY DIGITAL, A.V., S.A.U.",
                 "Raw: 'No guarda relacion con AXON WEALTH ADVISORY DIGITAL, A.V., S.A.U. (https://finizens.com)'. Target explicito unico."),
    "339e4ea0": ("CORRECT_LABEL", "GPB FINANCIAL SERVICES LTD",
                 "Raw: 'No guarda relacion con la entidad GPB FINANCIAL SERVICES LTD, debidamente autorizada y registrada'. Target explicito unico."),
    "22d4bdbf": ("CORRECT_LABEL", "IBROKER GLOBAL MARKETS, S.V., S.A",
                 "Raw: 'No guarda relacion con IBROKER GLOBAL MARKETS, S.V., S.A (https://www.ibroker.es)'. Target explicito unico."),
    "220c7fd2": ("CORRECT_LABEL", "ASEVIA TECHNOLOGY VENTURES, FCRE, SA",
                 "Raw: 'No guarda relacion con ASEVIA TECHNOLOGY VENTURES, FCRE, SA debidamente registrada'. Target explicito unico."),
    "1355d297": ("CORRECT_LABEL", "ASEVIA TECHNOLOGY VENTURES, FCRE, SA",
                 "Mismo raw: 'No guarda relacion con ASEVIA TECHNOLOGY VENTURES, FCRE, SA'. Target explicito unico."),
    "ea54f69b": ("CORRECT_LABEL", "Banque Internationale à Luxembourg (BIL)",
                 "Raw: 'La entidad autorizada en Luxemburgo Banque Internationale a Luxembourg (BIL) no guarda relacion con la pagina web advertida.' Target explicito unico (sujeto gramatical)."),
    "dd747199": ("CORRECT_LABEL", "IBS ASSET MANAGEMENT, B.V.",
                 "Raw: 'No guarda relacion con IBS ASSET MANAGEMENT, B.V. debidamente registrada'. Target explicito unico."),
    "3aa62698": ("CORRECT_LABEL", "TRADITION FINANCIAL SERVICES ESPAÑA, SOCIEDAD DE VALORES, S.A.U.",
                 "Raw: 'no guarda relacion con TRADITION FINANCIAL SERVICES ESPANA, SOCIEDAD DE VALORES, S.A.U., debidamente registrada'. Target explicito unico."),
    "dedbb9e7": ("CORRECT_LABEL", "ALANTRA EQUITIES SOCIEDAD DE VALORES, S.A.",
                 "Raw: 'No guarda relacion con ALANTRA EQUITIES SOCIEDAD DE VALORES, S.A. (https://www.alantra.com)'. Target explicito unico."),
    "1ba42f7f": ("CORRECT_LABEL", "ALANTRA CAPITAL MARKETS, SV, S.A.",
                 "Raw: 'No guarda relacion con ALANTRA CAPITAL MARKETS, SV, S.A. (https://www.alantra.com)'. Target explicito unico."),
    "22426176": ("CORRECT_LABEL", "XTB S.A., SUCURSAL EN ESPAÑA",
                 "Raw: 'No guarda relacion con XTB S.A., SUCURSAL EN ESPANA, y su web https://www.xtb.com/es'. Target explicito unico."),
    "9d286f16": ("CORRECT_LABEL", "INNAT INVERSIONES SICAV S.A. (antes denominada PROFIT INVERSIONES SICAV, S.A.)",
                 "Raw: 'No guarda relacion con INNAT INVERSIONES SICAV S.A. (antes denominada PROFIT INVERSIONES SICAV, S.A.), debidamente registrada'. El parentesis forma parte del nombre citado."),
    "d32c14a8": ("CORRECT_LABEL", "Waystone Asset Management (IE) Limited (C39544)",
                 "Raw: 'ha tomado los datos de una entidad autorizada por el CBI, Waystone Asset Management (IE) Limited (C39544), para enganar'. Target explicito unico."),
    "a3198c63": ("CORRECT_LABEL", "EVER CAPITAL INVESTMENTS, S.V., S.A.",
                 "Raw: 'no guardan relacion con EVER CAPITAL INVESTMENTS, S.V., S.A., y su web https://evercapitalsv.com'. Target explicito unico."),
    "e15f657d": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'no guardan relacion con la entidad de nombre VIE FINANCE AEPEY'. Target explicito unico."),
    "fcc9bf6f": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'NO GUARDAN RELACION CON LA ENTIDAD DE NOMBRE VIE FINANCE AEPEY.' Target explicito unico."),
    "00182cab": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'NO GUARDAN RELACION CON LA ENTIDAD DE NOMBRE VIE FINANCE AEPEY.' Target explicito unico."),
    "00678443": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'NO GUARDAN RELACION CON LA ENTIDAD DE NOMBRE VIE FINANCE AEPEY.' Target explicito unico."),
    "a6967424": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'La entidad registrada en Grecia VIE FINANCE AEPEY no guarda relacion con ninguna de las paginas web advertidas.' Target explicito unico."),
    "d9722e7a": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'La entidad registrada en Grecia VIE FINANCE AEPEY no guarda relacion...'. Target explicito unico."),
    "1abc1bf1": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'La entidad registrada en Grecia VIE FINANCE AEPEY no guarda relacion...'. Target explicito unico."),
    "950b3cc8": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'La entidad registrada en Grecia VIE FINANCE AEPEY no guarda relacion...'. Target explicito unico."),
    "439567f1": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'La entidad registrada en Grecia VIE FINANCE AEPEY no guarda relacion...'. Target explicito unico."),
    "75a1c4c0": ("CORRECT_LABEL", "VIE FINANCE AEPEY",
                 "Raw: 'La entidad registrada en Grecia VIE FINANCE AEPEY no guarda relacion...'. Target explicito unico."),
    "5879af6d": ("NORMALIZE_LABEL", "Vontobel Asset Management S.A.",
                 "El gold contiene el nombre correcto pero con basura copiada del raw ('de manera fraudulenta la identidad de la sociedad registrada en Luxemburgo', ', con quien...'). Se normaliza al nombre propio. NOTA: este notice_id tiene dos filas en el dataset (AccorInvest y Vontobel); el raw del corpus corresponde a la fila Vontobel."),
    "5877c672": ("NORMALIZE_LABEL", "Incentive Investment Funds plc (CBI00134801)",
                 "El gold contiene el nombre correcto pero con basura copiada del raw ('IDENTIDAD DE LA ENTIDAD legitima', ', CON QUIEN...'). Se normaliza al nombre propio."),
    "fc88be0b": ("NORMALIZE_LABEL", "Macquarie Bank Europe Designated Activity Company",
                 "El gold contiene el nombre correcto pero con prefijo no nominal ('LOS DETALLES DE UNA ENTIDAD AUTORIZADA POR EL BANCO CENTRAL DE IRLANDA,')."),
    "62fe5512": ("SET_UNRESOLVED", None,
                 "El texto nombra DOS targets (Bolero (KBC Bank NV) y GuardCap Asset Management Limited). El esquema admite uno: UNRESOLVED en vez de eleccion arbitraria."),
    "37d3a3c7": ("SET_UNRESOLVED", None,
                 "El texto dice 'suplantan la identidad de bancos': generico plural, sin nombre singular defendible."),
}

# URLs de entidad legitima citada en el raw: se retiran de label.domains
# (mismo criterio que el holdout ciego: no son dominios del advertido).
DOM_REMOVE = {
    "682a85dc": "finizens.com",
    "dedbb9e7": "www.alantra.com",
    "1ba42f7f": "www.alantra.com",
}


def main():
    dump = json.loads(DUMP.read_text(encoding="utf-8"))
    rows = []
    seen = set()
    for d in dump:
        nid = d["notice_id"]
        dec, new, reason = T[nid[:8]]
        seen.add(nid[:8])
        rows.append({
            "notice_id": nid, "field": "target",
            "old_value": d["gold_target"], "new_value": new,
            "decision": dec, "reason": reason,
            "adjudication_scope": SCOPE,
        })
        host = DOM_REMOVE.get(nid[:8])
        if host:
            rows.append({
                "notice_id": nid, "field": "domains",
                "remove_value": host, "decision": "CORRECT_LABEL",
                "reason": (f"{host} es la web de la entidad legitima citada "
                           "en el raw, no del advertido. Mismo criterio que "
                           "el holdout ciego."),
                "adjudication_scope": SCOPE,
            })
    missing = set(T) - seen
    if missing:
        sys.exit(f"prefijos sin caso en dump: {sorted(missing)}")
    with open(OUT, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(len(rows), "adjudications ->", OUT)


if __name__ == "__main__":
    main()
