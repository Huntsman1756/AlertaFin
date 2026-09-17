"""Paso 4: golden corpus con protocolo de doble revision independiente.

- LITERAL A: usa alertafin.pipeline (domainex + clones).
- LITERAL B: segunda implementacion independiente (algoritmos distintos,
  escrita desde cero, no importa domainex/clones).
- Coincidencia A==B -> CONFIRMED. Diferencia -> DISPUTED, se lista para
  arbitraje manual (g0/golden/disputes.json); las resoluciones manuales se
  registran en g0/golden/resolutions.json con su razon y pasan a RESOLVED.
- Un caso DISPUTED sin resolver NO entra al calculo final de gates.

Uso:
  python scripts/golden_corpus.py select   # seleccion determinista (seed fija)
  python scripts/golden_corpus.py label    # doble pasada + reconcile
  python scripts/golden_corpus.py finalize # aplica resoluciones -> corpus final
"""

import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alertafin.pipeline import enrich
from alertafin.provenance import ByteStore
from alertafin.textnorm import normalize_name

GOLD_DIR = Path("g0/golden")
SEED = 20260913


# ---------------------------------------------------------------------------
# Literales de dominios: implementacion B independiente
# ---------------------------------------------------------------------------

_B_URL_PREFIXES = ("http://", "https://", "ftp://")


def _domains_b(text):
    if not text:
        return []
    out = []
    seen = set()
    for token in text.replace(";", " ").replace(",", " ").split():
        t = token.strip("()[]\"'<>,.;:")
        if "@" in t:
            continue
        low = t.lower()
        for pre in _B_URL_PREFIXES:
            if low.startswith(pre):
                t = t[len(pre):]
                break
        t = t.split("/")[0].split("?")[0].split(":")[0].strip(".")
        if not t or t.lower() == "u.mint":
            continue
        labels = t.lower().split(".")
        if len(labels) < 2 or any(not lbl for lbl in labels):
            continue
        tld = labels[-1]
        if len(tld) < 2 or not tld.isalpha():
            continue
        if not all(all(c.isalnum() or c == "-" for c in lbl) for lbl in labels):
            continue
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t.lower())
    return out


def domains_b(notice):
    got = []
    for f in ("entidad_raw", "entidad_secundaria_raw", "observaciones_raw"):
        for d in _domains_b(notice.get(f) or ""):
            if d not in got:
                got.append(d)
    return got


# ---------------------------------------------------------------------------
# Literales de clones: implementacion B independiente
# ---------------------------------------------------------------------------

_B_MARKERS = re.compile(
    r"clon|(?:\(\s*clone\s*\))|suplant|pasar por|utiliza(?:n)? el nombre|"
    r"fals\w+ identidad",
    re.IGNORECASE,
)
_B_TARGET = re.compile(
    r"(?:pasar por la entidad(?: autorizada)?|suplanta\w*\s+(?:a\s+)?(?:la\s+)?"
    r"(?:entidad\s+)?(?:autorizada\s+)?|clon\w*\s+de\s+(?:la\s+)?(?:entidad\s+)?|"
    r"utiliz\w*\s+el\s+nombre\s+de\s+(?:la\s+)?(?:entidad\s+)?)"
    r"(?P<t>[^;]+)",
    re.IGNORECASE,
)


def _norm_target_b(t):
    t = re.sub(r"\s+", " ", t).strip(" \t\"',;")
    t = re.split(r"\.\s+[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1]", t)[0]
    t = re.sub(r",?\s+con\s+la\s+que\s+.*$", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\([^)]*\d{3,8}[^)]*\)\s*\.?\s*$", "", t)
    return t.strip(" \t\"',;.")


def clone_b(notice):
    text = " | ".join(
        str(notice.get(f) or "")
        for f in ("entidad_raw", "entidad_secundaria_raw", "observaciones_raw")
    )
    if "(clone)" not in text.lower() and not _B_MARKERS.search(text):
        return {"clone": False, "target": None}
    if "similar" in text.lower() and not _B_MARKERS.search(
        re.sub(r"similar", "", text, flags=re.IGNORECASE)
    ):
        pass
    obs = notice.get("observaciones_raw") or ""
    m = _B_TARGET.search(obs)
    target = _norm_target_b(m.group("t")) if m else None
    if "(clone)" in text.lower() or "clon" in text.lower() \
            or "suplant" in text.lower() or "pasar por" in text.lower() \
            or "el nombre" in text.lower():
        return {"clone": True, "target": target}
    return {"clone": False, "target": None}


# ---------------------------------------------------------------------------
# Seleccion determinista
# ---------------------------------------------------------------------------

def load_notices():
    summary = json.loads(Path("g0/normalized/summary.json").read_text("utf-8"))
    if summary.get("status") != "OK":
        print("SOURCE_UNAVAILABLE: sin pull valido no se construye corpus.")
        sys.exit(3)
    store = ByteStore(Path("g0/raw"))
    raw = store.get(summary["source_sha256"])
    return enrich(raw).notices


def select(notices):
    rnd = random.Random(SEED)
    by_date = sorted(notices, key=lambda n: (n["fecha"] or "", n["notice_id"]),
                     reverse=True)
    recent = by_date[:100]

    clone_pool = [n for n in notices if (n.get("clone") or {}).get("clone_detected")]
    clones_sample = rnd.sample(clone_pool, 25)

    dom_pool = [n for n in notices if (n.get("domains") or [])
                and n not in clones_sample and n not in recent]
    dom_sample = rnd.sample(dom_pool, 20)

    # casos dificiles
    names = {}
    for n in notices:
        key = normalize_name(n["entidad_raw"])
        if key:
            names.setdefault(key, []).append(n)
    repeated = [g for g in names.values() if len(g) > 1]
    repeated.sort(key=lambda g: (-len(g), g[0]["entidad_raw"] or ""))
    hard = []
    hard += repeated[0][:3]                    # grupo de nombres mas repetido
    hard += repeated[1][:2]                    # segundo grupo
    hard += repeated[2][:2]                    # tercer grupo
    unresolved = [n for n in clone_pool
                  if (n["clone"] or {}).get("relation_status") == "UNRESOLVED"]
    unresolved.sort(key=lambda n: n["notice_id"])
    hard += unresolved[:2]                     # clones sin target (aliases)
    # negativos: 'similar a' sin marcador de clon + no-dominios tipo U.MINT
    negatives = [n for n in notices
                 if n["observaciones_raw"]
                 and re.search(r"similar", n["observaciones_raw"], re.IGNORECASE)
                 and not (n.get("clone") or {}).get("clone_detected")]
    hard += negatives[:1]
    umint = [n for n in notices
             if n["entidad_secundaria_raw"]
             and re.fullmatch(r"[A-Z]\.[A-Z]{3,}", n["entidad_secundaria_raw"].strip())]
    hard += umint[:2]
    hard = list({n["notice_id"]: n for n in hard}.values())[:14]

    sel = {}
    for bucket, rows in (("recent_100", recent), ("clones_25", clones_sample),
                         ("domains_20", dom_sample), ("difficult_14", hard)):
        for n in rows:
            sel.setdefault(n["notice_id"], {
                "notice": n, "buckets": [], "selection_reason": bucket,
            })["buckets"].append(bucket)
    return list(sel.values())


# ---------------------------------------------------------------------------
# Doble pasada + reconcile
# ---------------------------------------------------------------------------

def _target_comparable(t):
    return normalize_name(t or "")


def label_all(selected):
    out = []
    for entry in selected:
        n = entry["notice"]
        a_dom = {d["host_normalized"] for d in (n.get("domains") or [])}
        b_dom = set(domains_b(n))
        a_cl = n.get("clone") or {}
        b_cl = clone_b(n)

        disputes = []
        if a_dom != b_dom:
            disputes.append({
                "field": "domains",
                "A": sorted(a_dom), "B": sorted(b_dom),
            })
        a_clone = bool(a_cl.get("clone_detected"))
        if a_clone != b_cl["clone"]:
            disputes.append({"field": "clone", "A": a_clone, "B": b_cl["clone"]})
        elif a_clone and _target_comparable(a_cl.get("clone_target_raw")) != \
                _target_comparable(b_cl.get("target")):
            disputes.append({
                "field": "clone_target",
                "A": a_cl.get("clone_target_raw"),
                "B": b_cl.get("target"),
            })

        out.append({
            "notice_id": n["notice_id"],
            "raw": {
                "tipo_raw": n["tipo_raw"], "fecha_raw": n["fecha_raw"],
                "entidad_raw": n["entidad_raw"],
                "entidad_secundaria_raw": n["entidad_secundaria_raw"],
                "observaciones_raw": n["observaciones_raw"],
                "fecha_baja_raw": n["fecha_baja_raw"],
            },
            "buckets": entry["buckets"],
            "passes": {
                "A": {"domains": sorted(a_dom), "clone": a_clone,
                      "target": a_cl.get("clone_target_raw"),
                      "relation_status": a_cl.get("relation_status"),
                      "registry_number": a_cl.get("clone_target_registry_number")},
                "B": {"domains": sorted(b_dom), "clone": b_cl["clone"],
                      "target": b_cl.get("target")},
            },
            "disputes": disputes,
            "label_status": "DISPUTED" if disputes else "CONFIRMED",
            "label": None,
        })
    return out


def cmd_select(notices):
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    sel = select(notices)
    serializable = []
    for e in sel:
        n = dict(e["notice"])
        n["raw_row_bytes_hex"] = n.pop("raw_row_bytes").hex()
        serializable.append({"notice": n, "buckets": e["buckets"],
                             "selection_reason": e["selection_reason"]})
    counts = {}
    for e in sel:
        for b in e["buckets"]:
            counts[b] = counts.get(b, 0) + 1
    (GOLD_DIR / "selection.json").write_text(
        json.dumps(serializable, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"selected": len(sel), "buckets": counts}, indent=2,
                     ensure_ascii=False))


def cmd_label():
    entries = json.loads((GOLD_DIR / "selection.json").read_text("utf-8"))
    labeled = label_all(entries)
    confirmed = sum(1 for e in labeled if e["label_status"] == "CONFIRMED")
    with (GOLD_DIR / "labeled.json").open("w", encoding="utf-8") as fh:
        json.dump(labeled, fh, ensure_ascii=False, indent=2)
    disputes = [e for e in labeled if e["label_status"] == "DISPUTED"]
    with (GOLD_DIR / "disputes.json").open("w", encoding="utf-8") as fh:
        json.dump(disputes, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"total": len(labeled), "confirmed": confirmed,
                      "disputed": len(disputes)}, indent=2))


def cmd_finalize():
    labeled = json.loads((GOLD_DIR / "labeled.json").read_text("utf-8"))
    res_path = GOLD_DIR / "resolutions.json"
    resolutions = {}
    if res_path.exists():
        resolutions = {
            r["notice_id"]: r
            for r in json.loads(res_path.read_text("utf-8"))
        }
    final = []
    unresolved_disputes = 0
    for e in labeled:
        if e["label_status"] == "CONFIRMED":
            a = e["passes"]["A"]
            e["label"] = {
                "domains": a["domains"], "clone": a["clone"],
                "target": a["target"],
                "registry_number": a["registry_number"],
            }
            e["label_status"] = "CONFIRMED_AB"
        else:
            r = resolutions.get(e["notice_id"])
            if not r:
                unresolved_disputes += 1
                e["label_status"] = "DISPUTED_UNRESOLVED"
                e["label"] = None
            else:
                e["label"] = r["label"]
                e["label_status"] = "RESOLVED_MANUAL"
                e["resolution_rationale"] = r["rationale"]
        final.append(e)

    with (GOLD_DIR / "golden_corpus.jsonl").open("w", encoding="utf-8") as fh:
        for e in final:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    usable = [e for e in final if e["label"] is not None]
    print(json.dumps({
        "total": len(final),
        "confirmed_ab": sum(1 for e in final if e["label_status"] == "CONFIRMED_AB"),
        "resolved_manual": sum(1 for e in final if e["label_status"] == "RESOLVED_MANUAL"),
        "disputed_unresolved": unresolved_disputes,
        "usable_for_gates": len(usable),
    }, indent=2))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "select"
    if cmd == "select":
        cmd_select(load_notices())
    elif cmd == "label":
        cmd_label()
    elif cmd == "finalize":
        cmd_finalize()
    else:
        print("comando desconocido", file=sys.stderr)
        sys.exit(2)
