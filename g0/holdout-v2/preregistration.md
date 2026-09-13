# Holdout ciego v2 — preregistracion

Commit de preregistracion: este documento y `annotation-contract-v2.md` se
congelan **antes** de seleccionar un solo caso. Nada de lo que sigue puede
cambiarse una vez generada la muestra.

## Proposito

Comprobar si el parser del commit `ab07001` (tag `g0-r-regression-pass`)
generaliza a casos nunca inspeccionados durante G0, el holdout v1 ni G0-R.

Fuente: el mismo snapshot CNMV congelado de G0
(`source_sha256 = 1816cd621f96fcbe6a2d138ea6fa52befd27babcb5dfb2c5e8f50a086ecb7049`).
Quedan miles de observaciones no vistas; un holdout temporal futuro sera aun
mas fuerte, pero no hace falta esperar para validar ahora.

## Unidad de evaluacion

```text
case_key = (notice_id, record_version_id)
```

No solo `notice_id`: G0-R demostro que un mismo `notice_id` puede cubrir
filas con `Observaciones` distintas (p.ej. `5879af6d`: AccorInvest/Vontobel).

## Exclusion por contaminacion (seen set)

Si cualquier version de `notice_id` X aparecio en golden / holdout-v1 /
adjudicaciones / inspeccion manual, se excluyen **todas** las versiones de X.

El seen set une como minimo:

```text
154 casos golden (g0/golden/golden_corpus.jsonl)
210 casos holdout-v1 (g0/holdout/labels.jsonl)
7 identity groups inspeccionados (g0/identity-groups-t0.json)
notices usados como fixture o triage manual en G0-R
```

El manifest registra la lista, su sha256 y el recuento.

En el universo restante, si un `notice_id` aun tiene varias versiones, se
elige como maximo una version de forma determinista (orden por
`record_version_id`), de modo que los casos muestreados sean
estadisticamente mas independientes.

## Muestreo

- **Sin estrato `clone/noclone`**, ni internamente para la seleccion
  principal: estratificar por la prediccion del sistema puede sesgar que
  errores aparecen.
- Estratos: `regulator_group x temporal_bucket`

```text
CNMV / EXTRANJERO
x
<2019 / 2019-2021 / 2022-2023 / >=2024
```

- Seleccion proporcional con minimos por estrato, seed fija registrada en
  el manifest.
- **Tamano: 300 casos.** Con ~10% de clones historicos se esperan del orden
  de 30 positivos sin seleccionar expresamente clones.
- No hay challenge set dentro del veredicto. Pruebas especificas de
  `imita`, `mismo nombre`, multi-target, etc. serian un corpus de robustez
  separado y claramente no-ciego.

## Freeze

Esta vez no se congela solo el parser. El manifest fija:

```text
source_sha256
base_commit                 # commit del codigo evaluado
parser_fingerprint          # PARSER_FILES, mismo metodo que v1
evaluator_fingerprint       # scripts de scoring/evaluacion
selection_script_sha256
annotation_contract_sha256  # annotation-contract-v2.md

sample.jsonl sha256
labeling-blind.jsonl sha256

seen-set sha256
sample case_keys            # (notice_id, record_version_id) por caso
seed
allocation                  # recuento por estrato
```

El `evaluator_fingerprint` se incluye porque en v1 se encontraron bugs
metodologicos en el scoring antes de etiquetar: el evaluador tambien forma
parte del experimento.

## Etiquetado

- Ciego: el anotador solo ve la vista raw (`labeling-blind`); nunca
  `sample.jsonl`, outputs del parser, estratos ni evaluacion.
- Revision independiente de una submuestra aleatoria del 20% antes de abrir
  las predicciones: permite publicar acuerdo inter-anotador. No es
  imprescindible para el gate.

## Gates (inalterados respecto a v1)

```text
domain precision       = 100%
domain recall          >= 95%

clone precision        = 100%
clone recall           >= 95%

clone target exact     >= 90%
automatic false target = 0
```

`target_resolution_coverage` y `relation_status agreement` se reportan como
metricas descriptivas, sin umbral.

## Veredicto

Tres estados posibles:

```text
todos los gates                          -> PASS
algun gate falla                         -> FAIL
denominador insuficiente para un gate
critico                                -> INCONCLUSIVE
```

No hay remediacion antes de publicar el resultado.

## Consecuencias

```text
PASS -> la tesis CLONE_OF determinista queda rehabilitada y G1 DGSFP
        puede desbloquearse.
FAIL / INCONCLUSIVE -> G1 DGSFP sigue bloqueado.
```
