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

## Decision posterior

Con el informe y el snapshot:

```text
BUILD    estructura suficiente y reproducible -> G1-WI.B ingestion
DEGRADE  alcance reducido (p. ej. solo una de las dos fuentes)
STOP     la fuente no permite corpus evaluable -> INCONCLUSIVE
```

Solo tras el probe se fija el tamano minimo del corpus de evaluacion
DGSFP. Ningun numero artificial a priori.
