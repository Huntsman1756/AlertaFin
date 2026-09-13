# G1-WI.A — DGSFP Source Probe

Read-only. **Cero parser productivo.** Antes de cualquier desarrollo de
ingesta, medir la estructura real de las dos fuentes DGSFP:

- DGSFP «Sujetos no autorizados»
- DGSFP «Paginas web fraudulentas»

## Preguntas que debe responder

```text
acceso reproducible
formato (HTML / PDF / CSV / JSON)
numero de registros
paginacion
historico disponible
fechas
campos
dominios presentes
IDs oficiales presentes
duplicados
cambios temporales
robots.txt / condiciones tecnicas
```

## Reglas

- Read-only sobre la fuente oficial; respeto de robots.txt y condiciones
  tecnicas.
- Todo retrieval queda registrado en provenance (mismo principio que G0:
  `retrieved_at`, `source_sha256`, `http_status`); bytes inmutables por
  SHA-256.
- No se escribe parser productivo ni modelo de datos en esta subfase.

## Salida

- Informe `g1-wi/source-probe-report.md`.
- Snapshot congelado de las respuestas observadas (raw inmutable por
  SHA-256), que pasa a ser el punto de referencia de la fase.

## Criterio de capacidad (por fuente, congelado antes de la primera request)

Para cada una de las dos fuentes DGSFP:

```text
SOURCE_PROBE_CAPABLE(S) iff:

A. official_source = true
B. access_reproducible = true
C. complete_snapshot_enumerable = true
D. record_boundary_identifiable = true
E. raw_bytes_snapshotable = true
F. source_type_preservable = true
G. provenance_reproducible = true
```

## Decision posterior

Con el informe y el snapshot:

```text
BUILD
    ambas fuentes cumplen A-G
    -> G1-WI.B ingestion

DEGRADE
    exactamente una cumple A-G
    -> el scope de v0.2 se reduce explicitamente a esa fuente

STOP
    ninguna cumple A-G
    -> G1-WI = INCONCLUSIVE
```

La existencia de historico, dominios o IDs oficiales es **descriptiva**,
no condicion de BUILD: una fuente perfectamente reproducible sin IDs
sigue siendo valida para un warning index; simplemente no habra
enrichment exacto.

Solo tras el probe se fija el tamano minimo del corpus de evaluacion
DGSFP. Ningun numero artificial a priori.
