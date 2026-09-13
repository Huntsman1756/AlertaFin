# G1-WI-R1 — preregistracion de remediacion previa al run final

Estado: congelada por commit. Una unica remediacion permitida; despues,
evidencia ciega nueva y un unico run final.

## Por que existe

El evaluador G1-WI (`g1-wi-evaluator-v1` -> `ff447d5`) confirma dos FAIL
conocidos sobre el build `9f1a15d` antes del run final:

1. `domain_precision` = 0.9897 (holdout-v2, mismo extractor) — FP
   `ver.pdf` x2 y `5.3.ai`.
2. `dgsfp_source_limitation` — la salida unificada no expone la
   limitacion de no-exhaustividad que el contrato exige.

Ambos defectos estaban identificados **antes** de esta remediacion (uno
clasificado en ADR-001 como bug ordinario). Esto no es iterar hasta
verde: es arreglar defectos de producto conocidos antes del unico
disparo.

## Scope permitido — exactamente dos cambios

### A. `domainex.py` — causa general de los FP conocidos

- `ver.pdf`: ruta/nombre de fichero confundido con hostname.
- `5.3.ai`: numeracion de seccion confundida con hostname.

Reglas:

- Corregir la **causa general** con tests RED que demuestren el mecanismo.
- PROHIBIDO denylist de los casos concretos (`HOST_DENYLIST += {...}`).
- Los tres casos conocidos pasan a regresion; no son el diseno.

### B. `unified.py` — limitacion DGSFP en la salida

- Cada WarningNotice DGSFP expone `source_limitation`.
- `MultiCheckResult` expone `source_limitations`.
- `DGSFP_FRAUDULENT_WEBS`: `population_scope = DECLARED_PAGE_ONLY`,
  `population_completeness_beyond_page = UNKNOWN`.
- `DGSFP_UNAUTHORISED`: preservar la declaracion oficial de
  no exhaustividad de la fuente.

## Prohibido

- Tocar thresholds ni gates.
- Tocar clones/targets (`clones.py`).
- Cambiar identidad (`identity.py`, `notice_id`, `source_occurrence_id`).
- Nuevas heuristicas no relacionadas.
- Usar el nuevo blind sample para desarrollar.
- Modificar artefactos/gates G0 ni el parser CNMV congelado salvo el
  punto A.

## Secuencia congelada

```text
1. Remediacion TDD (A + B)
2. Freeze del nuevo code-under-test: commit + fingerprints + suite
3. Nuevo blind CNMV G1-WI (NO es holdout-v3; no rehabilita G0):
   - excluye todo notice_id visto en golden G0, holdout-v1,
     holdout-v2 y G0-R (adjudicaciones/triage)
   - selector sin predicciones del parser
   - seed derivada mecanicamente del commit de esta preregistracion
   - n=300; minimos: gold domains >=100, gold clone >=20,
     gold target-unresolvable suficiente para safety
   - si denominadores insuficientes -> INCONCLUSIVE; sin remuestreo
4. Etiquetas ciegas congeladas y publicadas ANTES de evaluar
5. Run final unico: DGSFP censo + CNMV blind + estructurales
6. Cierre: PASS -> v0.2; FAIL -> FAIL; INCONCLUSIVE -> INCONCLUSIVE.
   Sin R2 dentro de G1-WI.
```

Consecuencia aceptada: tras tocar `domainex`, holdout-v2 deja de decidir
los gates CNMV (fingerprint ya lo implementa) — pasa a evidencia
historica; los tres FP quedan como regresion.
