# Contribuir a AlertaFin

Gracias por contribuir. AlertaFin combina una CLI pública v0.1 (CNMV) con artefactos de investigación reproducible sobre advertencias regulatorias. La prioridad del repositorio es conservar trazabilidad, provenance e integridad experimental.

## Antes de empezar

- Lee `README.md`, `DATA_NOTICE.md` y los ADR relevantes.
- La CLI publicada v0.1 es **CNMV-only**. La investigación G1-WI (CNMV + DGSFP) está cerrada y no alcanzó release.
- `g0/`, `g0-r/` y `g1-wi/` contienen evidencia congelada. **No modifiques, reformatees, regeneres, muevas ni sustituyas archivos existentes en esas rutas.**
- Una nueva hipótesis, fuente o experimento debe abrir una fase nueva con alcance y criterios propios; no se corrigen retrospectivamente gates, labels, thresholds ni veredictos históricos.

## Flujo de trabajo

1. Crea una rama desde `main`.
2. Mantén el cambio acotado y separa cambios de producto, documentación y evidencia.
3. Ejecuta la suite localmente:

   ```bash
   pip install -e ".[test]"
   pytest
   ```

   La suite no debe depender de llamadas live a CNMV/DGSFP.
4. Abre un pull request contra `main` y completa la plantilla.
5. Espera a que el check requerido `ci` esté verde. `main` bloquea force-push, borrado y cambios sin el check requerido.

No se aceptan pushes directos como mecanismo normal de trabajo.

## Evidencia y reproducibilidad

La evidencia histórica se trata como material inmutable. Si detectas un error en un artefacto congelado:

- no reescribas el archivo histórico;
- documenta el hallazgo en un issue o ADR nuevo;
- usa overlays, erratas o artefactos posteriores explícitamente no canónicos cuando corresponda;
- conserva los hashes y la cadena de procedencia original.

No presentes datos de regresión o corpus ya inspeccionados como evidencia de generalización.

## Cambios en fuentes regulatorias

Para cambios de CNMV/DGSFP o de otra fuente oficial, documenta como mínimo:

- URL oficial y fecha/hora de observación;
- método de adquisición;
- boundary de registro;
- limitaciones de cobertura;
- tratamiento de fallos de fuente;
- provenance suficiente para reproducir el snapshot.

Usa la plantilla `Source / regulatory data issue` para discrepancias de fuente o provenance.

## Privacidad y secretos

Nunca incluyas:

- API keys, tokens, cookies, credenciales o ficheros `.env`;
- rutas locales, datos privados del colaborador o secretos de terceros;
- datos personales que no formen parte de una fuente oficial pública necesaria para la evidencia.

Los datos regulatorios replicados no quedan relicenciados por MIT. Consulta `DATA_NOTICE.md`.

## Pull requests

Un PR debe explicar qué cambia, por qué, cómo se verificó y si afecta a provenance/evidencia. Para código, añade o actualiza tests cuando cambie comportamiento. Para documentación/configuración, verifica sintaxis y coherencia sin introducir tests artificiales.

Los cambios que alteren semántica regulatoria, identidad, matching o criterios de evaluación requieren documentación explícita de la decisión antes de presentarse como nueva evidencia.

## Licencia

Al contribuir código aceptas que tu contribución se publique bajo la licencia MIT del repositorio. Los datos y evidencias de terceros conservan sus propias condiciones de reutilización; consulta `DATA_NOTICE.md`.
