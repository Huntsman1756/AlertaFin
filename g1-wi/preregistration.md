# G1-WI — AlertaFin v0.2 · Multi-source Warning Index

Preregistracion del contrato de exito. **Docs-only.**

`preregistration_commit = 5b1434879d65ec042ee7423fd4cb1253c5154af7`
— el commit que introdujo este fichero —, fijado por el tag anotado
`g1-wi-prereg-v1`. Un commit no puede contener su propio SHA: la
referencia es al commit anterior, no una autorreferencia.

- Fase: **AlertaFin v0.2 — Multi-source Warning Index**
- Gate: **G1-WI** (DGSFP warning-source integration)
- Fecha: 2026-09-13
- Sustituye: nada. El antiguo G1 (DGSFP) permanece **BLOCKED** bajo su
  preregistracion original (ver `ADR-001-clone-graph-rejected.md`). Esta
  fase es un contrato nuevo, no un desbloqueo retrospectivo.
- Precedente: G0 cerrado con veredicto **FAIL** metodologicamente limpio
  (tag `g0-holdout-v2-fail`, commit `a939da7`, ADR-001). La tesis del
  grafo automatico de clones quedo **RECHAZADA** por su propio kill
  criterion (`clone_target_exact = 13/22 = 59.09% < 70%`) y **no se
  reintroduce** en esta fase bajo ningun nombre.

## Tesis

> Dada una denominacion o dominio, AlertaFin puede localizar de forma
> reproducible las advertencias oficiales disponibles, preservando
> exactamente que supervisor dijo que, cuando y sobre que sujeto, y
> detectar evidencia explicita de clon sin inventar relaciones.

## Arquitectura

```text
DGSFP warning pages
        |
        v
AlertaFin warning ingestion
        |
        |-- WarningNotice
        |-- domains / aliases
        |-- clone evidence
        `-- provenance
               |
               | enrichment opcional,
               | NUNCA requisito para warning lookup
               v
        OpenDGSFP export (pinned, exact IDs only)
```

OpenDGSFP (`Huntsman1756/OpenDGSFP`) se consume como **export
determinista pinneado a commit/tag** (pin del SHA-256 del export), como
proveedor opcional de identidad legitima. No se importa como dependencia
estrecha ni se duplica su crawler/modelo. Si una advertencia no contiene
un identificador oficial que permita el enlace exacto, queda
`UNRESOLVED`.

## Scope

Incluido:

- Corpus de advertencias CNMV existente (sin cambios de alcance).
- DGSFP «Sujetos no autorizados».
- DGSFP «Paginas web fraudulentas».

Excluido:

- Banco de Espana.
- Fuzzy entity merging.
- Automatic clone-graph completion.
- WHOIS / reputation / social enrichment.
- Frontend.
- LLMs.

## Core product

```text
warning_status:
    WARNED | NO_WARNING_FOUND | AMBIGUOUS | SOURCE_UNAVAILABLE

query:
    exact normalized domain
    exact normalized name

output (por coincidencia):
    all matching notices
    authority
    warning date
    source type
    source URL
    retrieved_at
    source SHA-256
    clone evidence when explicit
```

## Semantica multifuente de `warning_status`

Cada fuente produce su propio estado por consulta:

```text
source_status[CNMV]
source_status[DGSFP_UNAUTHORISED]
source_status[DGSFP_FRAUDULENT_WEBS]
```

Agregado (precedencia):

```text
si cualquier fuente = WARNED
    => WARNED
       + coverage_complete=false si otra fuente no respondio

si ninguna WARNED y alguna SOURCE_UNAVAILABLE
    => SOURCE_UNAVAILABLE

si todas disponibles y alguna AMBIGUOUS
    => AMBIGUOUS

si todas disponibles, ninguna warned ni ambiguous
    => NO_WARNING_FOUND
```

Regla heredada de G0, inalterada: varias notices para el mismo dominio
exacto siguen siendo `WARNED`, no `AMBIGUOUS`; `AMBIGUOUS` es para un
nombre normalizado exacto que no permite identificar univocamente al
sujeto.

## Identity

- Identidad de notice determinista por fuente (mismo principio que G0).
- `record_version` determinista.
- **NO** merge canonico cross-authority por nombre.
- Enlaces canonicos solo por identificador oficial exacto.
- Unresolved permanece unresolved.

## OpenDGSFP

- Enrichment opcional unicamente.
- Export pinneado (SHA-256 / commit).
- Ninguna advertencia depende de que OpenDGSFP este disponible.
- Sin join canonico por nombre.
- OpenDGSFP nunca puede cambiar `warning_status`, `notice_id`, autoridad
  ni texto de la advertencia. Solo puede anadir
  `related_authorised_entity`.
- Si un identificador exacto lleva a conflicto o a multiples candidatos
  en OpenDGSFP => `CONFLICT/UNRESOLVED`; nunca elegir uno
  arbitrariamente.

## Gates (obligatorios)

| Area | Gate |
|---|---|
| Raw rows preserved | **100%** |
| Provenance complete | **100%** |
| Valid source dates parsed | **100%** |
| Determinism identical inputs | **100%** |
| Stable/idempotent IDs | **100%** |
| Silent row loss | **0** |
| False cross-source canonical merges | **0** |
| Domain precision | **100%** |
| Domain recall | **>=95%** |
| Explicit clone precision | **100%** |
| Explicit clone recall | **>=95%** |
| False emitted clone target | **0** |
| Source failure represented as `SOURCE_UNAVAILABLE` | **100%** |

`False emitted clone target = 0` es deliberadamente un **safety gate**:
cero targets emitidos puede dar PASS. Siempre se reporta
`targets_emitted`; ese PASS no es evidencia de cobertura — coverage y
exact recall estan expresamente fuera de gates.

### Recall por fuente/tipo (no solo micro-average global)

Un recall global >=95% podria esconder un parser mediocre en una fuente
minoritaria. Los gates de recall se evaluan por clase:

```text
domain recall >=95%:   CNMV · DGSFP_SUJETOS · DGSFP_PAGINAS
                       cuando el denominador de esa clase sea suficiente

clone recall >=95%:    idem por fuente cuando existan positivos;
                       fuente con cero clones explicitos => N/A,
                       nunca PASS 100%
```

Los denominadores minimos por clase se fijan tras el probe y se congelan
**antes de implementar el parser productivo y antes de etiquetar** la
evaluacion.

### Fechas de fuente (definicion independiente del parser)

`Valid source dates parsed = 100%` no puede depender de lo que el propio
parser considere «valido» — seria circular. Se define asi:

```text
VALID_SOURCE_DATE =
    valor no vacio
    + conforme a una gramatica observada/documentada
    + fecha calendario valida

valid source date -> parse obligatorio
ausente           -> ABSENT
presente pero no interpretable bajo el contrato
                  -> UNPARSEABLE + raw preservado

Nunca adivinar/corregir una fecha.
```

El probe descubre las gramaticas reales de cada fuente; se congelan
antes de G1-WI.B.

Explicitamente **SIN gate**:

```text
clone_target coverage        NO GATE
clone_target exact recall    NO GATE
```

La tesis fue rechazada; no se recola bajo otro nombre.

Regla de abstencion (permanece):

```text
si AlertaFin emite clone_target:
    debe estar sustentado deterministicamente
si no:
    UNRESOLVED
```

Abstencion permitida; invencion no.

## Gates especificos DGSFP-G1

1. **SOURCE COVERAGE** — 100% de los registros observables de las dos
   fuentes representados, o explicacion explicita de cada exclusion.
2. **SOURCE-TYPE PRESERVATION** — «sujeto no autorizado» y «pagina
   fraudulenta» nunca se colapsan semanticamente entre si.
3. **SOURCE LIMITATION** — la salida y la documentacion preservan que la
   lista DGSFP puede no ser exhaustiva. Nunca:
   `NO_WARNING_FOUND => autorizado/seguro`.

## Veredicto

```text
MANDATORY_GATES = 16    (13 core + 3 DGSFP-specific)

FAIL
    cualquier mandatory applicable gate falla.

INCONCLUSIVE
    ningun gate evaluable falla, pero la fuente/corpus impide
    evaluar uno o mas gates obligatorios con denominador
    suficiente.

PASS
    los 16 gates son PASS o, cuando este explicitamente permitido,
    N/A por ausencia estructural de la clase.
```

Sin minimo artificial de registros DGSFP a priori: el tamano del corpus
de evaluacion se fija tras el Source Probe (G1-WI.A), a partir de la
estructura real observada.

## Secuencia de la fase

```text
1. feat/v0.2-warning-index-contract   docs only — este contrato
2. G1-WI.A  DGSFP source probe        cero parser productivo
3. decision BUILD / DEGRADE / STOP    segun la fuente real
4. G1-WI.B  ingestion DGSFP
5. G1-WI.C  modelo unificado CNMV + DGSFP
6. G1-WI.D  integracion opcional OpenDGSFP (solo exact-ID)
7. evaluacion ciega propia del corpus DGSFP/multifuente
8. si PASS -> AlertaFin v0.2
```

## Freeze

Congelado en `5b1434879d65ec042ee7423fd4cb1253c5154af7`, fijado por el
tag anotado `g1-wi-prereg-v1`. Enmiendas solo docs-only, en commits
aparte, y antes del primer request a DGSFP. Tras el freeze del snapshot
del probe, ningun cambio de gates, denominadores ni contrato.
