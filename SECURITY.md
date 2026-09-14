# Política de seguridad

## Versiones soportadas

La versión de producto publicada es la CLI v0.1 (CNMV-only) en la rama `main`. Los artefactos G0/G1-WI son evidencia de investigación congelada y no constituyen una versión de producto soportada.

## Cómo reportar una vulnerabilidad

No publiques secretos, tokens, datos explotables ni detalles sensibles en un issue público.

Usa el canal privado de GitHub para reportar vulnerabilidades cuando esté disponible (`Security` → `Report a vulnerability`). Si ese canal no aparece, abre un issue público mínimo con el título `[security] private contact requested`, sin incluir detalles técnicos sensibles; el intercambio de detalles debe continuar por un canal privado.

Incluye, cuando sea posible:

- versión/commit afectado;
- componente afectado;
- impacto y condiciones necesarias para reproducirlo;
- prueba de concepto mínima y no destructiva;
- mitigación sugerida, si la conoces.

## Alcance

Se consideran problemas de seguridad, entre otros:

- exposición de credenciales, tokens o secretos;
- ejecución de código no prevista;
- dependencias o workflows con riesgo de supply-chain;
- corrupción o sustitución silenciosa de evidencia/provenance;
- fallos que permitan presentar una fuente no disponible como `NO_WARNING_FOUND`;
- vulnerabilidades que afecten a integridad, confidencialidad o disponibilidad del software.

Errores factuales de una fuente oficial, cambios de HTML/CSV o discrepancias regulatorias sin impacto de seguridad deben reportarse mediante la plantilla `Source / regulatory data issue`.

## Datos personales

No añadas al reporte datos personales que no sean imprescindibles. Si necesitas referenciar evidencia oficial pública, incluye solo el fragmento mínimo necesario y su URL/provenance.

## Respuesta

El proyecto se mantiene de forma independiente y no ofrece un SLA formal. Los reportes se evaluarán de buena fe y, si son válidos, se procurará coordinar la corrección y la publicación responsable antes de hacer públicos los detalles sensibles.
