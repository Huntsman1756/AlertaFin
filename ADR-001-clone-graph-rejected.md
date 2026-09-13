# ADR-001: Aceptar el kill criterion del holdout-v2 — grafo automático de clones rechazado

**Estado:** aceptado — 2026-09-13
**Tag del experimento:** `g0-holdout-v2-fail` (commit `a939da7`)

## Contexto

AlertaFin G0 se evaluó con dos holdouts ciegos consecutivos sobre datos
nunca inspeccionados durante el desarrollo:

```text
G0 CNMV engineering          PASS
blind holdout v1             FAIL    (histórico)
G0-R regression              PASS    (remediación sobre corpus conocido)
blind holdout v2             FAIL    (300 casos, etiquetado ciego,
                                      labels congeladas en 283ab6f
                                      ANTES de evaluar)
```

Resultados del holdout-v2 (`g0/holdout-v2/evaluation.json`):

```text
domain precision      0.9897   (3 FP: ver.pdf ×2, 5.3.ai)   gate 1.00   FAIL
domain recall         1.0000   (0 FN / 289 gold)            gate ≥0.95  PASS
clone precision       1.0000                                 gate 1.00   PASS
clone recall          1.0000   (25/25)                      gate ≥0.95  PASS
clone target exact    0.5909   (13/22; 8 sin resolver,
                                1 sobre-captura)            gate ≥0.90  FAIL
false target          0        (0/3 irresolubles)           gate 0      PASS
```

Denominadores preregistrados: todos suficientes. El FAIL no es
INCONCLUSIVE.

## Decisión

El criterio preregistrado era, en esencia:

```text
clone_target_exact >= 90%   GO clone graph
70%–<90%                    DEGRADE
< 70%                       FAIL clone-graph thesis / warning-index-only
```

Con `clone_target_exact = 13/22 = 59.09%`, **la tesis del grafo
automático de clones queda rechazada según su propio kill criterion**.

Se acepta el resultado y se adopta el siguiente alcance de producto:

```text
WARNING INDEX THESIS          SUPPORTED BY CURRENT EVALUATION
CLONE DETECTION THESIS        SUPPORTED BY CURRENT EVALUATION
AUTOMATIC CLONE GRAPH THESIS  REJECTED
```

("Supported" = soportado por la evaluación actual; no es una garantía
universal.)

El producto queda definido como:

```text
type = CLONE
relation_status = EXPLICIT_SOURCE / PARSED_EXPLICIT / UNRESOLVED
clone_target = X solo cuando el resolver tiene evidencia determinista

UNRESOLVED no es error de producto.
No se intenta completar automáticamente el grafo.
```

Que el parser abstenga (`null`) en 8 de los 9 fallos de target es un
comportamiento defendible para un producto regulatorio: abstención
conservadora antes que invención.

## Consecuencias

1. **No se abre un tercer ciclo arreglo→holdout para rehabilitar G0.**
   Tras dos holdouts ciegos, iterar hasta verde sería optimizar contra el
   benchmark.
2. Los FP de dominio (`ver.pdf`, `5.3.ai`) se corrigen como bugs
   ordinarios del extractor — sus causas son claras — sin holdout-v3
   asociado.
3. `G1 DGSFP` permanece **BLOCKED** bajo su preregistración original; no
   se desbloquea retrospectivamente. Si el producto pivota a
   warning-index + evidencia de clon explícita, se define una **nueva
   fase con nuevo contrato de éxito** y DGSFP se incorpora bajo ese
   alcance.
4. G0 se cierra con este veredicto. Los artefactos congelados
   (`manifest.json`, `sample.jsonl`, `labels.jsonl`, `evaluation.json`)
   no se modifican.

## Referencias

- `g0/holdout-v2/preregistration.md` — gates y denominadores
- `g0/holdout-v2/annotation-contract-v2.md` — reglas de etiquetado
- `g0/holdout-v2/evaluation.json` — métricas completas del FAIL
- Tag `g0-holdout-v2-fail`; tags previos `g0-holdout-fail`,
  `g0-r-regression-pass`
