# G1-WI.A — DGSFP Source Probe: informe

Fecha: 2026-09-13 · 8 GET read-only, sin autenticacion, sin robots.txt
(404). Provenance completo en `g1-wi/probe/retrievals.jsonl`; snapshot
congelado en `g1-wi/probe/snapshot.json` + `g1-wi/probe/raw/`.

## Fuentes sondeadas

```text
DGSFP_UNAUTHORISED
  https://dgsfp.mineco.gob.es/es/Consumidor/RegistrosPublicos/Paginas/No-autorizadas.aspx

DGSFP_FRAUDULENT_WEBS
  https://dgsfp.mineco.gob.es/es/Paginas/0-11-Paginas-web-fraudulentas.aspx
```

## Hallazgos a nivel de sitio

- Plataforma: SharePoint (`X-SharePointHealthScore`, `SPRequestGuid`).
- `robots.txt`: **404** (no existe). Sin condiciones tecnicas formales;
  probe realizado con requests espaciados, solo GET.
- `Content-Type: text/html; charset=utf-8` y los bytes son UTF-8 real
  (decode estricto OK).
- `Last-Modified` == `Date` en todas las respuestas: **no hay senal de
  versionado del servidor**; la deteccion de cambios solo es posible por
  diff de content-hash entre snapshots.
- **Volatilidad por request**: dos GET al mismo recurso producen
  SHA-256 distintos del documento completo, pero la diferencia esta
  acotada a 6 lineas de tokens por request (`CssLink` ids,
  `g_correlationId`, timestamp en `_spPageContextInfo`, `SPThemeUtils`,
  `formDigest`). La region de contenido (`ms-rtestate-field`) es
  **byte-identica** entre fetches:
  `unauth content_sha256 = 49c8fee53e4ed6e1f6268479de02fcb487753ed7f643040773a59b0a1e1006f2` (ambos fetches).
  La pagina webs tiene **4 campos** `ms-rtestate-field`, todos
  byte-identicos entre fetches (hashes por campo en
  `probe/snapshot.json`; el que contiene la lista es el campo 3,
  `97c1fea96422c63a…`).
- Consecuencia para provenance: cada retrieval se guarda con su raw
  completo y su sha256 (como en G0); la identidad de contenido se
  define sobre la region de contenido, no sobre el documento entero.

## DGSFP_UNAUTHORISED — estructura observada

- Formato: HTML, lista plana dentro de `ms-rtestate-field` (un `<p>`
  por registro).
- **Registros: 97** (limite de registro = elemento `<p>`; un primer
  recuento por lineas de texto dio 100 porque la nota parentetica de
  BARKLEY salta de linea dentro de su `<p>`) en dos bloques:
  - `Año 2024` — 10 denominaciones.
  - `Resto de años` — 87 denominaciones, **sin fecha ni año por registro**.
- Campos por registro: **solo denominacion**. 5 registros llevan nota
  entre parentesis; una es evidencia explicita de clon:
  `(sin vinculos ni relacion con W.R. BERKLEY INSURANCE (EUROPE) LIMITED
  SUC. EN ESPAÑA, que es entidad aseguradora autorizada)`.
- **Duplicados en la propia fuente: 10 denominaciones aparecen 2 veces**
  (p. ej. `MILTON GROUP`, `TOP CLASS INSURANCE`, `INKORE`).
- Sin IDs oficiales (sin NIF, sin clave administrativa).
- Sin dominios ni URLs en los registros.
- Sin paginacion: la lista completa esta en una unica pagina.
- Enlazada desde la navegacion (Consumidor > Registros publicos):
  es el registro canonico mantenido.
- La propia pagina declara: *«Esta relacion no es exhaustiva…»* —
  encaja con el gate DGSFP-G1.3 (SOURCE LIMITATION).
- Fechas: granularidad anual solo para el bloque del año en curso;
  `warning_date` sera `ABSENT` para ~90% de registros (definicion
  `VALID_SOURCE_DATE`: ausente -> `ABSENT`, nunca se adivina).

## DGSFP_FRAUDULENT_WEBS — estructura observada

- Formato: HTML, **anuncio unico y estatico** (no registro mantenido).
- **Registros: 10**, cada uno = URL/dominio + denominacion de la
  entidad entre parentesis (`rapidegroupe.com (Bankia Finance, S.A.)`,
  `europae-s.com`, …). Fuente **dominio-primaria**.
- **Sin fecha visible en la pagina**: ningun `2020`/`noviembre`/meta de
  publicacion en el HTML; la fecha (nov-2020) solo se infiere del
  prefijo de URL `0-11-` y de prensa externa. `warning_date` sera
  `ABSENT` para todos los registros de esta fuente.
- Sin IDs oficiales.
- Sin paginacion (una pagina).
- **No esta enlazada desde la navegacion del sitio** (Consumidor solo
  enlaza «Sujetos no autorizados» y «Alertas sobre conductas de
  mercado»; Noticias es JS-rendered sin lista estatica). No se encontro
  ningun indice mantenido de advertencias de webs: es la unica pagina
  con ese titulo, pero **no puede verificarse que futuras advertencias
  de webs se consoliden aqui** — podrian publicarse como anuncios
  sueltos sin indice.
- Sin duplicados en la lista.

## Cierre factual A–G por fuente

```text
DGSFP_UNAUTHORISED
A official_source                 true   dgsfp.mineco.gob.es
B access_reproducible             true   200 estable; contenido
                                         byte-identico entre fetches
C complete_snapshot_enumerable    true   pagina unica, lista completa,
                                         sin paginacion
D record_boundary_identifiable    true   un elemento <p> por registro;
                                         headers de seccion anual
E raw_bytes_snapshotable          true   raw guardado; volatilidad
                                         acotada a tokens de request
F source_type_preservable         true   tipo "sujeto no autorizado"
                                         declarado en la propia pagina
G provenance_reproducible         true   url + retrieved_at + sha256 +
                                         http_status registrados
=> CAPABLE true

DGSFP_FRAUDULENT_WEBS
A official_source                 true   mismo dominio oficial
B access_reproducible             true   idem
C complete_snapshot_enumerable    true   la fuente declarada es una
                                         pagina unica -> enumerable
                                         (ver caveat abajo)
D record_boundary_identifiable    true   un item por registro
E raw_bytes_snapshotable          true   idem
F source_type_preservable         true   tipo "pagina web fraudulenta"
                                         distinguible
G provenance_reproducible         true   idem
=> CAPABLE true
```

**Caveat sobre C en FRAUDULENT_WEBS**: enumerable significa «la pagina
declarada se puede snapshotear entera». No garantiza que la pagina cubra
la poblacion real de advertencias de webs DGSFP: es un anuncio de 2020
huerfano de navegacion. Si DGSFP publica nuevas advertencias de webs
fuera de esta pagina, no hay indice para descubrirlas. Esta limitacion
se documenta y aterriza en DGSFP-G1.1 (SOURCE COVERAGE = registros
*observables* de la fuente declarada) y en la documentacion de salida
(DGSFP-G1.3). Si se decide que la fuente «Páginas web fraudulentas» debe
significar *todas* las advertencias de webs publicadas y no esta pagina,
C pasaria a `false` y la decision mecanica seria DEGRADE.

## Decision mecanica

```text
DGSFP_UNAUTHORISED     CAPABLE true
DGSFP_FRAUDULENT_WEBS  CAPABLE true (con caveat documentado)

2 capable -> BUILD
```

## Para congelar antes de G1-WI.B (segun preregistracion)

- Snapshot: este directorio (`g1-wi/probe/`) ya es el snapshot de
  referencia.
- Gramaticas de fecha observadas: ninguna a nivel de registro.
  `Año 2024` como cabecera de bloque (unico patron temporal presente);
  `Resto de años` y webs: `ABSENT`.
- Denominadores minimos propuestos a congelar (recuento observado):
  `DGSFP_SUJETOS` = 97 registros (87 unicas — corregido en
  `pre-ingestion-freeze.md`), `DGSFP_PAGINAS` = 10 registros.
  Suficientes para evaluar; `DGSFP_PAGINAS` con n=10 exige 10/10 para
  cualquier gate >=95%.
- Respuestas a las 12 preguntas del probe: cubiertas arriba
  (acceso/formato/registros/paginacion/historico/fechas/campos/
  dominios/IDs/duplicados/cambios/robots).
