# ADR-002: Aceptar el FAIL final de G1-WI — warning index no certificado en v0.2

**Estado:** aceptado — 2026-09-14
**Tag del experimento:** `g1-wi-final-fail` (commit de este ADR)
**Artefacto de veredicto:** `g1-wi/evaluation.json` en commit `6deb5f0`,
SHA-256 `66d38260a15bf4e51a947e67071a490d77c779c762f17a37abfa8e7b334ae2dc`

## Contexto

G1-WI evaluó el warning index multifuente (CNMV + DGSFP) bajo el
contrato congelado de `g1-wi/preregistration.md` (tag
`g1-wi-prereg-v1`), con la cadena:

```text
G1-WI.A   source probe DGSFP              PASS / BUILD
G1-WI.B   ingestion DGSFP                 COMPLETE (errata incorporada:
                                          BARKLEY no-clon, identidad
                                          vs ocurrencia)
G1-WI.C   modelo unificado + busqueda     COMPLETE (WarningNotice con
          multifuente                     source_occurrences[1..N],
                                          domain_assertions[] /
                                          clone_evidence[]
                                          provenance-backed)
evaluator v1                              FROZEN 28c18c3 (+erratum
                                          ff447d5: separa
                                          evaluator_freeze_commit de
                                          code_under_test_commit)
G1-WI-R1  remediacion scope cerrado       COMPLETE (prereg 8af629c;
          pre-evaluacion                  domainex causa general:
                                          ext. fichero + version
                                          numerica; source_limitation
                                          en salida)
CUT                                       FROZEN 4edcce5
evaluator v2                              FROZEN 6844e83 (tag
                                          g1-wi-evaluator-v2: consume
                                          evidencia ciega nueva con
                                          precedencia sobre holdout-v2)
blind sample n=300                        FROZEN c2d60f5 (seed desde
                                          prereg, 0 seen-collisions,
                                          sin predicciones)
blind labels 300/300                      FROZEN 59e5028 (sha256
                                          0191ed4f..., antes de evaluar)
final run                                 UNICO — 6844e83 -> 6deb5f0
```

## Resultado

```text
15/16 gates PASS

structural (11/11)   PASS — ocurrencias preservadas, provenance,
                     determinismo, IDs estables, sin merges entre
                     fuentes, SOURCE_UNAVAILABLE, coverage DGSFP,
                     tipos, limitacion de fuente
domain recall        PASS   311/311
domain precision     FAIL   311/312 = 0.9968   (gate 1.0)
clone precision      PASS   21/21
clone recall         PASS   21/21
target safety        PASS   0 targets emitidos sobre oro irresoluble
DGSFP gates          PASS
```

**Veredicto: FAIL.** Unico FP CNMV: `www.inexxspain.com`.

## Failure mode

```text
RELATED_WARNED_DOMAIN_MISATTRIBUTED_AS_SUBJECT_DOMAIN
```

El raw del caso advierte a `D. MANUEL VILAR PERAIRE` y sus
Observaciones lo vinculan con `www.inexxspain.com`, «ya advertida por
esta CNMV» — dominio de **otro sujeto/aviso relacionado**, no del
sujeto de la fila. El parser lo extrajo desde Observaciones y lo
atribuyo al WarningNotice; el gold, conforme al contrato congelado
(dominios positivos solo desde Entidad/Entidad Secundaria), no lo
atribuye. Es un FP de **atribucion/provenance de la relacion
dominio-sujeto**, no un FP de extraccion («¿esto parece un dominio?»)
ni un error de etiquetado. Ninguna correccion retrospectiva es
legitima.

## Decision

*Aclaración añadida el 2026-09-14 como enmienda documental posterior al
resultado. El umbral estaba preregistrado en `g1-wi/preregistration.md`
(tag `g1-wi-prereg-v1`) antes de la evaluación; esta adición no altera
resultados, thresholds ni evidencia congelada.*

El umbral de `domain precision = 1.0` responde a una asimetría de riesgo
definida por el producto. Un fallo de cobertura degrada a abstención —
el dominio no se emite como aserción y la búsqueda sobre él devuelve
`NO_WARNING_FOUND` —, que sigue siendo una salida explícita y auditable.
Una atribución positiva falsa no tiene degradación equivalente: afirmar
que un dominio pertenece al sujeto advertido cambia el significado del
hecho regulatorio publicado y atribuye al supervisor una relación que
la fuente no afirmó. Por ello, el FAIL de `www.inexxspain.com` no invalida
el umbral; evidencia que el modelo de relación dominio-sujeto era
insuficiente para sostenerlo.

Se acepta el FAIL definitivo para G1-WI:

```text
G1-WI FINAL                FAIL
AlertaFin v0.2 contract    NOT MET
R2                         PROHIBITED dentro de G1-WI
```

El FAIL publicado es el resultado correcto del contrato: un criterio
de precision del 100% falla por 1 atribucion contextual entre 312
emisiones, con la clase de error exactamente aislada.

## Consecuencias

1. **No hay R2 ni remediacion dentro de G1-WI.** El experimento queda
   cerrado tal cual; `evaluation.json` es el veredicto inmutable.
2. **La capacidad sustentada por evidencia** es la de los 15 gates
   PASS: indice multifuente auditable, busqueda exacta con
   SOURCE_UNAVAILABLE/limitaciones explicitas, deteccion de clon
   explicita (21/21) y abstencion segura de targets. La tesis
   «precision de dominio 100% por sujeto» queda **rechazada** por
   atribucion.
3. **La hipotesis siguiente es fase nueva**, no continuacion:
   distinguir dominios directamente atribuibles al sujeto advertido de
   dominios mencionados como evidencia/aviso relacionado — modelo de
   `DomainAssertion` con `relation` tipada (SUBJECT_DOMAIN,
   RELATED_WARNED_DOMAIN, LEGITIMATE_ENTITY_DOMAIN, EMAIL_ONLY_DOMAIN,
   OTHER_REFERENCE), donde solo `SUBJECT_DOMAIN` alimenta la busqueda
   directa. Se abriria con preregistracion propia, no como R2.
4. Artefactos congelados intocables: muestra, etiquetas, CUT
   `4edcce5`, evaluador `g1-wi-evaluator-v2`, `evaluation.json` en
   `6deb5f0`.

## Referencias

- `g1-wi/preregistration.md` — contrato y gates (tag `g1-wi-prereg-v1`)
- `g1-wi/r1-preregistration.md` — scope cerrado de remediacion
- `g1-wi/evaluation.json` @ `6deb5f0` — veredicto inmutable
- `g1-wi/blind/{sample,labels}.jsonl` — evidencia ciega congelada
- Tags: `g1-wi-prereg-v1`, `g1-wi-evaluator-v2`, `g1-wi-final-fail`
- `ADR-001-clone-graph-rejected.md` — precedente de aceptacion de FAIL
