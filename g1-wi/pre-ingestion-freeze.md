# G1-WI — Freeze pre-ingesta (post-probe, pre-parser)

Docs/data-derived only. Congela lo observado en G1-WI.A **antes** de
G1-WI.B (parser productivo). Tras este commit: ningun cambio de gates,
denominadores ni contrato.

## 1. Aritmetica de denominaciones (DGSFP_UNAUTHORISED)

Counter determinista sobre las 100 lineas del snapshot
(`g1-wi/probe/unauth-name-counts.json`):

```text
rows_total            100    (AÑO_2024: 10, RESTO: 90)
unique_raw_names       90
duplicate_groups       10    (cada una x2)
duplicate_extra_rows   10
cross_section_dups      0    (todos los duplicados dentro de RESTO)
```

Corrige el informe del probe: 90 unicas, no 95.

## 2. Matriz de denominadores (congelada)

| Fuente        | Metrica                   | Denominador |
| ------------- | ------------------------- | ----------: |
| DGSFP_SUJETOS | source coverage           |    100 filas raw |
| DGSFP_SUJETOS | domain recall             |    N/A — 0 dominios gold |
| DGSFP_SUJETOS | clone recall              |    1 positivo explicito |
| DGSFP_SUJETOS | valid source date parsing |    N/A — 0 fechas completas por registro |
| DGSFP_PAGINAS | source coverage           |    10 registros |
| DGSFP_PAGINAS | domain recall             |    10 dominios gold -> exige 10/10 |
| DGSFP_PAGINAS | clone recall              |    N/A si el corpus confirma 0 clones explicitos |
| DGSFP_PAGINAS | valid source date parsing |    N/A — 0 fechas visibles |

`clone recall` con n=1 se acepta porque se evalua un **censo exhaustivo
del snapshot declarado**, no una muestra. Se informa `1/1`; no es
evidencia estadistica fuerte y no se presenta como tal.

## 3. Semantica temporal

`Año 2024` es **cabecera contextual de periodo**, no fecha de
advertencia:

```text
record-level VALID_SOURCE_DATE:  ninguna

context_period:
    "Año 2024" -> year = 2024, precision = YEAR
                  (o preservar raw si el modelo no admite partial dates)

warning_date:
    ABSENT en los 100 sujetos
    ABSENT en las 10 paginas
```

No se convierte a `2024-01-01`, `2024-12-31` ni fecha sintetica. La
fecha nov-2020 de la pagina de webs (inferible solo del slug `0-11-` o
de prensa externa) permanece **fuera del dato**.

## 4. Alcance de cobertura de DGSFP_FRAUDULENT_WEBS

```text
population_scope                      = DECLARED_PAGE_ONLY
snapshot_completeness                 = COMPLETE_FOR_DECLARED_PAGE
population_completeness_beyond_page   = UNKNOWN
```

No se afirma «todas las paginas fraudulentas advertidas por DGSFP».
Si se afirma: «todos los registros observables de la pagina oficial
declarada en el snapshot». Coherente con DGSFP-G1.1 (cobertura sobre lo
observable) y DGSFP-G1.3 (limitacion de exhaustividad documentada).

## 5. Preservacion de duplicados raw

No se deduplican las 100 filas durante la ingesta: `raw rows preserved
= 100%` exige que las duplicaciones de origen permanezcan como registros
de origen distintos. La identidad estable distingue ocurrencias
identicas por **seccion + indice de ocurrencia** (p. ej.
`RESTO:37`, `RESTO:81`). Vistas agrupadas posteriores son opcionales y
derivadas; el canonical raw layer conserva las 100 ocurrencias.

## 6. OpenDGSFP — estructuralmente N/A en este snapshot

El probe observo **0 identificadores oficiales** en ambas fuentes. Por
la regla exact-ID-only:

```text
official identifiers observed      = 0
OpenDGSFP exact joins attempted    = 0
related_authorised_entity added    = 0
```

No se compensa con nombre por muy evidente que parezca un caso. Es el
comportamiento querido del contrato.

Nota: no se anade un gate 17 de name retrieval — el contrato esta
congelado. Que los nombres ingeridos sean consultables por el
normalizador exacto se prueba como **invariante funcional** del core
product, sin reetiquetarlo retrospectivamente como gate experimental.

## Estado

```text
G1-WI.A probe                    PASS
DGSFP_UNAUTHORISED CAPABLE       true
DGSFP_FRAUDULENT_WEBS CAPABLE    true (DECLARED_PAGE_ONLY)
decision                         BUILD
G1-WI.B ingestion                AUTHORIZED tras este commit
```
