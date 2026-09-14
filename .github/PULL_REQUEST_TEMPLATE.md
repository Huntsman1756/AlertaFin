## Resumen

<!-- Qué cambia y por qué. -->

## Alcance

<!-- Componentes/archivos afectados. Indica explícitamente lo que queda fuera. -->

## Verificación

<!-- Comandos ejecutados y resultado relevante. -->

```text
pytest
```

## Impacto en evidencia / provenance

<!-- Explica si el cambio afecta a adquisición, identidad, raw bytes, provenance, matching o evaluación. -->

- [ ] Este PR no modifica, reformatea, regenera, mueve ni sustituye evidencia congelada existente bajo `g0/`, `g0-r/` o `g1-wi/`.
- [ ] No cambia retrospectivamente labels, gates, thresholds ni veredictos históricos.

## Checklist

- [ ] El cambio está acotado y el PR explica la motivación.
- [ ] He ejecutado la verificación aplicable y he incluido el resultado arriba.
- [ ] Si cambia comportamiento de código, hay tests que cubren el cambio.
- [ ] La suite sigue sin depender de llamadas live a fuentes regulatorias.
- [ ] No se incluyen secretos, credenciales, cookies, `.env`, rutas locales ni datos privados innecesarios.
- [ ] Si cambia semántica regulatoria/identidad/matching, la decisión está documentada explícitamente.
- [ ] Si se añade una nueva fase experimental, tiene alcance y criterios propios y no reabre un experimento cerrado.
- [ ] Documentación y `DATA_NOTICE.md` siguen siendo coherentes con el cambio.
