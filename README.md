# AlertaFin

[![CI](https://github.com/Huntsman1756/AlertaFin/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/Huntsman1756/AlertaFin/actions/workflows/tests.yml)

[Contribuir](CONTRIBUTING.md) · [Seguridad](SECURITY.md) · [Aviso de datos](DATA_NOTICE.md) · [Licencia MIT](LICENSE)

CLI v0.1: índice auditable de advertencias financieras oficiales de la
**CNMV** (WebAPI `PaffNoAutorizadas`), con provenance byte-exacta. No
determina si una entidad es segura ni si está autorizada; solo
representa hechos regulatorios publicados. Ver `DATA_NOTICE.md` para el
aviso de datos.

> La CLI publicada es **CNMV-only**. El repositorio contiene además la
> investigación multifuente **G1-WI** (CNMV + DGSFP), que no alcanzó
> release: su contrato v0.2 falló en evaluación — ver
> [la sección G1-WI](#v02--multi-source-warning-index-g1-wi-fail--cerrado)
> y `ADR-002-g1-wi-final-fail.md`.

```bash
alertafin check nextinversion.com
alertafin check "Global Capital"
alertafin recent --days 30
alertafin clones
alertafin show <notice-id>
```

Estados: `WARNED` | `NO_WARNING_FOUND` | `AMBIGUOUS` | `SOURCE_UNAVAILABLE`.
`NO_WARNING_FOUND` significa únicamente que no hubo coincidencia en las
fuentes consultadas. Un fallo de fuente nunca es `NO_WARNING_FOUND`.

## Decisiones congeladas (G0)

1. **Identidad**: `notice_id = sha256(canonical_json)` de
   `{source_namespace, tipo_raw, fecha_raw, entidad_raw,
   entidad_secundaria_raw, codigo_regulador_raw, pais_regulador_raw}`
   (UTF-8, `ensure_ascii=False`, separadores `(',',':')`, claves en orden
   fijo, vacío→`null`). `Observaciones` y `Fecha Baja` NO forman parte de la
   identidad. `record_version_id = sha256(raw_row_bytes)` por separado.
   Sin contadores, índices ni orden del CSV.
2. **Serialización canónica**: JSON como arriba; no hay concatenación de
   strings de longitud variable sin framing.
3. **Provenance**: cada retrieval genera su propio evento
   (`g0/provenance/retrievals.jsonl`) aunque los bytes sean idénticos; los
   bytes se almacenan inmutables por SHA-256 (`g0/raw/aa/…bin`). Caché
   agresiva: no se re-pide la fuente si el último intento fue OK (≤1
   pull/día en G0).
4. **Parser**: RFC4180 a nivel de bytes; conserva `raw_row_bytes` exactos
   (incluye newlines embebidos entrecomillados); campos vacíos→`None`,
   padding conservado (`'NOAUTO    '`); fechas `dd/mm/yyyy`
   (`Fecha Baja` con hora opcional); filas inválidas→`row_errors`, nunca
   silencio; cabecera distinta→`ParseError` (schema change).
5. **Dominios** (`domainex.py`): extracción determinista de
   `entidad_raw`, `entidad_secundaria_raw` y `observaciones_raw`;
   normalización técnica (minúsculas, sin esquema/credenciales/puerto/path,
   sin punto final, IDNA punycode) conservando SIEMPRE el raw.
   - `foo.example.com != example.com`; `www.` NO se elimina.
   - Dominios tras `@` (correos) NO se extraen (precision-first).
   - En `Observaciones` se excluyen fragmentos con contexto de **entidad
     legítima** (`no guarda relación con…`, `su web`, `web oficial`, …):
     esos dominios pertenecen al suplantado, no al sujeto advertido.
   - Denylist explícita: `u.mint` (nombre de producto, no dominio).
6. **Clones** (`clones.py`): solo si la fuente lo afirma explícitamente
   (token `CLONE`/`CLON`, `clon*`, `suplanta*`, `hace(n) pasar`,
   `utiliza(n) el nombre de`, `falsa identidad`). `similar a` NO es clon.
   - `clone_target_raw` solo por patrones exactos sobre el propio registro.
   - `EXPLICIT_SOURCE` (con objetivo) | `PARSED_EXPLICIT` (solo nº de
     registro) | `UNRESOLVED` (sin objetivo → NO se emite `CLONE_OF`).
   - Nunca fuzzy matching para construir relaciones. Precision > recall.
7. **Búsqueda** (`search.py`): dominio exacto o nombre normalizado exacto;
   un sujeto→`WARNED`+notices[]; varios sujetos→`AMBIGUOUS`; parcial/fuzzy
   nunca advierte. Sujeto = casefold+colapso de espacios del raw; no hay
   fusión persistente de entidades.
8. **`Fecha Baja`**: no se le atribuye semántica jurídica. Solo se documenta
   el hecho observable (ver `g0/fecha-baja-matrix-t0.json`): con el pull
   `estado=actu`, las 10.338 filas con `Fecha Baja` NULL aparecen y las 30
   con `Fecha Baja` poblada no aparecen (10.368 full).

## Reproducir G0

```bash
pip install -e .[test]
pytest                                     # suite completa
python -m alertafin.acquire                # Paso 1 (cache; --force fuerza red)
python scripts/census.py                   # Paso 2
python scripts/fecha_baja_matrix.py        # Paso 3
python scripts/golden_corpus.py select|label|finalize   # Paso 4
python scripts/identity_groups.py          # Evidencia de los 7 grupos de identidad
python scripts/holdout_sample.py select    # Holdout ciego (parser congelado)
python scripts/holdout_sample.py verify    # Verifica que el parser no cambio
python scripts/holdout_labeling.py blind       # Vista ciega para etiquetar
python scripts/holdout_labeling.py scaffold    # Plantilla de etiquetas humanas
python scripts/holdout_labeling.py evaluate    # Join + precision/recall
python scripts/evaluate_gates.py           # Pasos 5-6 -> g0/gates-t0.json
```

## Gates congelados (14, en `g0/gates-t0.json`)

El acta de G0 evalua **14 gates pre-registrados**: determinismo del parser,
provenance, fechas, colisiones de identidad, idempotencia, provenance
raw->normalized, preservacion de campos raw, dominios (precision/recall),
clones (precision/recall, target exacto), falso `CLONE_OF` y falsos merges.
Resultado: **14/14 PASS**.

Las cifras de `g0/census-t0.json` (incluida la cobertura de clones 28,18%)
son **metricas de techo del producto**, marcadas `"metric_kind":
"product-ceiling (NO gates)"`, y no se suman a la tabla de umbrales. Si un
informe muestra 15 filas, la decimoquinta es contexto de poblacion/decision
(`decision_basis`), no un gate.

## Golden corpus (g0/golden/)

154 casos (100 recientes, 25 clones, 20 con dominio, 11 difíciles;
los buckets se solapan por diseño). Protocolo de doble pasada: etiquetador
A (`alertafin.pipeline`) vs etiquetador B (implementación independiente en
`scripts/golden_corpus.py`); coincidencia→`CONFIRMED_AB`; discrepancia→
`DISPUTED` + arbitraje manual documentado en `resolutions.json`→
`RESOLVED_MANUAL`. 0 disputas sin resolver.

## Límites conocidos (documentados, no racionalizados)

- **Identidad vs version (7 grupos).** En el pull T0 hay 7 `notice_id` con mas
  de una fila. Inspeccionados uno a uno (`scripts/identity_groups.py` ->
  `g0/identity-groups-t0.json`): **5** son la misma fila fisica publicada dos
  veces consecutivas (`record_version_id` y `raw_row_bytes` identicos) y **2**
  difieren **solo** en `Observaciones`, con los 7 campos de identidad
  identicos (`record_version_id` distinto). Ninguno son dos notices distintos;
  el versionado funciona como se diseño y la identidad no queda
  subespecificada en estos casos.

  | notice_id (12) | filas | clasificacion |
  |---|---|---|
  | `471c6716385b` | 4541-4542 | fila duplicada (bytes identicos) |
  | `47e0bd7aa57a` | 6270-6271 | fila duplicada (bytes identicos) |
  | `48dbcd0d59a8` | 4855-4856 | fila duplicada (bytes identicos) |
  | `4da7eaa0b14a` | 3844-3845 | fila duplicada (bytes identicos) |
  | `6334d313088d` | 8813-8814 | fila duplicada (bytes identicos) |
  | `5879af6de6d1` | 2766-2767 | version: solo `Observaciones` |
  | `a88ca5244ebf` | 2637-2638 | version: solo `Observaciones` |

- Cobertura de resolución de clones en población completa: 28,18% de las
  1.015 filas marcadas como clon obtienen referencia explícita (157
  `EXPLICIT_SOURCE` + 129 `PARSED_EXPLICIT`); 729 quedan `UNRESOLVED`
  porque CNMV no nombra al objetivo de forma estructurada. No se inventan.
- El golden corpus etiquetado por A/B/arbitraje no es un benchmark externo
  independiente; su acuerdo bruto A=B fue 110/154 (71,4%) y las 44
  discrepancias se resolvieron contra el texto raw (2 familias de error de
  B, documentadas en `resolutions.json`). Es un corpus de
  **regresion/desarrollo**, no un holdout ciego: las reglas del extractor se
  derivaron de sus propias discrepancias. Para generalizacion se usa el
  holdout de abajo.

## Holdout ciego (`g0/holdout/`)

`scripts/holdout_sample.py select` congela el parser (sha256 del contenido de
`parser.py`, `domainex.py`, `clones.py`, `pipeline.py`, `identity.py`,
`textnorm.py`, `__init__.py`), excluye los 154 casos del golden ya
inspeccionados y extrae del resto una muestra estratificada determinista
(regulador x clon x tramo temporal, seed fija). `sample.jsonl` guarda la salida
congelada del parser **sin etiquetas**; `verify` demuestra que el parser no
cambio entre muestreo y etiquetado. Regla: no tocar el parser mientras la
muestra siga sin etiquetar.

`sample.jsonl` guarda ademas la salida del parser (`domains`, `clone`), asi que
**no es la vista para etiquetar**: anclaria al humano. El etiquetado se hace
sobre `labeling-blind.jsonl` (`scripts/holdout_labeling.py blind`), derivada de
los mismos 210 IDs pero sin ningun output inferido. `stratum_blind` conserva
solo regulador/tramo porque el estrato original codificaba la prediccion de
clon. `scaffold` crea la plantilla `labels.jsonl` con campos vacios y
`evaluate` hace el join por `notice_id` contra `sample.jsonl` y calcula
precision/recall (con `pending` mientras falten etiquetas). Solo puntua filas
con `labeled: true`, valida los tipos obligatorios y separa dos preguntas:
deteccion de clon (todos los casos etiquetados) y target exacto (solo ground
truth con target explicitamente resoluble; un `null`/`null` no cuenta como
acierto). Reporta ademas `gold_target_resolvable_cases`,
`parser_target_resolved_cases`, `parser_target_on_unresolvable_cases` y
`target_resolution_coverage`.

## G0 blind holdout: FAIL — resultado historico inmutable

Etiquetado ciego completo (210/210, commit `139a25f`, tag `g0-holdout-fail`)
con el parser congelado (`parser_still_frozen: true`):

| Metrica | Resultado | Gate |
|---|---|---|
| domain precision | 0.985 (3 FP) | FAIL (<100%) |
| domain recall | 1.0 | PASS |
| clone precision | 1.0 | PASS |
| clone recall | 0.9677 (30/31) | PASS |
| clone target exact | 0/25 | FAIL (<90%) |

Dos gates preregistrados fallan -> **G0 HOLDOUT VERDICT = FAIL**. La tesis
"indice de advertencias y dominios" continua; la tesis "grafo CLONE_OF con
targets deterministas" falla en G0. Este resultado no se rescribe.

## G0-R: remediacion sobre corpus de regresion

`G0-R: remediation evaluated on known regression data; not evidence of
generalization.` Los 210 casos etiquetados dejan de ser holdout de
generalizacion (se conocen y se usaron para corregir el parser): pasan a ser
corpus de regresion medido por `scripts/holdout_regression.py`.

- `g0-r/baseline.json`: baseline inmutable creado antes de tocar el parser
  (reproduce el FAIL congelado; `reproduces_frozen_evaluation: true`).
- `g0-r/latest.json`: metricas del parser actual + delta vs baseline.
- `g0-r/golden-adjudications.jsonl` + `g0-r/golden-evaluation.json`
  (`holdout_regression.py golden`): re-evaluacion de los 14 gates sobre
  `golden_corpus.jsonl` **sin modificarlo**; cada correccion de etiqueta es
  una linea auditable (`CORRECT_LABEL`/`NORMALIZE_LABEL`/`SET_UNRESOLVED`)
  con razon y alcance `G0-R regression only`. Vista legacy sin overlay:
  `13/14` (`clone_target_exact_90: FAIL_BY_STALE_LABELS`, etiquetas escritas
  bajo el extractor anterior). Vista adjudicada: 14/14.
- `holdout_sample.py verify` reporta MISMATCH a proposito: el fingerprint del
  parser cambio (es el freeze guard funcionando, no un error).

Resultado G0-R sobre las 210 etiquetas congeladas: domain precision 0.9949
(1 FP: `tr.pro`, adjudicacion de etiqueta **PENDIENTE** — no se usa para
fabricar 100%), recall 1.0; clones 31/31, precision 1.0; target 25/25,
cobertura 100%, 0 targets sobre casos no resolubles.

```text
G0 blind holdout       FAIL   # historico, inmutable (tag g0-holdout-fail)
G0-R regression        PASS   # datos conocidos; no es generalizacion
holdout-v2             FAIL   # 300 casos ciegos; tag g0-holdout-v2-fail
G1 DGSFP               BLOCKED
```

El holdout ciego v2 (300 casos, etiquetas congeladas en `283ab6f` antes de
evaluar) dio **FAIL**: domain precision 0.9897 (3 FP) y
`clone_target_exact` 0.5909 (13/22) contra gates 1.00 y >=0.90. Por su
propio kill criterion (<70%), la tesis del **grafo automatico de clones
queda RECHAZADA** (`ADR-001-clone-graph-rejected.md`): AlertaFin queda
como indice auditable de advertencias y detector de clones explicitos;
`UNRESOLVED` es un estado de producto legitimo y no se completan
relaciones automaticamente.

## v0.2 — Multi-source Warning Index (G1-WI): FAIL — cerrado

Fase preregistrada en `g1-wi/preregistration.md` (tag `g1-wi-prereg-v1`):
índice multifuente CNMV + DGSFP con `WarningNotice` semántico que agrupa
`source_occurrences[1..N]` y assertions provenance-backed
(`domain_assertions[]`, `clone_evidence[]`). Sin gate de
`clone_target` (tesis rechazada en ADR-001); `UNRESOLVED` permanece.

Resultado del run final único (`g1-wi/evaluation.json` @ `6deb5f0`,
etiquetas ciegas n=300 congeladas en `59e5028` antes de evaluar):

```text
15/16 gates PASS
domain precision     FAIL   311/312 = 0.9968   (gate 1.0)
domain recall        PASS   311/311
clone precision      PASS   21/21
clone recall         PASS   21/21
structural (11)      PASS   — incl. coverage, tipos, limitación DGSFP,
                              SOURCE_UNAVAILABLE, 0 merges
```

Unico FP: `www.inexxspain.com`, extraído de `Observaciones` — dominio de
**otro sujeto ya advertido**, atribuido al notice equivocado
(`RELATED_WARNED_DOMAIN_MISATTRIBUTED_AS_SUBJECT_DOMAIN`,
`ADR-002-g1-wi-final-fail.md`). **El contrato v0.2 no se cumplió** y no
hay R2 dentro de G1-WI. Lo que sí queda sustentado por evidencia: índice
multifuente auditable, búsqueda exacta con `SOURCE_UNAVAILABLE` y
limitaciones de fuente explícitas, y detección de clon explícita 21/21
con abstención segura de targets.
