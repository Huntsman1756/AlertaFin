# Aviso sobre los datos

Este repositorio contiene **evidencia regulatoria replicada** de fuentes
oficiales públicas:

- **CNMV** — WebAPI `PaffNoAutorizadas` (entidades no autorizadas).
- **DGSFP** — «Sujetos no autorizados» y «Páginas web fraudulentas».

## Alcance

- La licencia del código (`LICENSE`, MIT) **no relicencia los datos**.
  Los registros, HTML raw, manifests y etiquetas proceden de terceros y
  conservan cualquier condición de reutilización de sus fuentes
  oficiales. Antes de reutilizar los datos, revisa los términos de las
  webs de CNMV y DGSFP.
- La evidencia incluye **datos personales publicados por los propios
  supervisores** (nombres de personas físicas, direcciones de email,
  denominaciones). Se conserva porque es parte de la evidencia oficial
  y de la auditabilidad del índice; su tratamiento ulterior es
  responsabilidad del reutilizador conforme a la normativa aplicable.
- Los artefactos bajo `g0/`, `g0-r/` y `g1-wi/` son **evidencia congelada**: sus
  bytes están fingerprintados (SHA-256) en manifests y evaluaciones.
  No deben modificarse, reformatearse ni regenerarse.

## Lo que este repositorio NO afirma

`NO_WARNING_FOUND` no significa que una entidad esté autorizada ni que
sea segura. Las listas oficiales pueden no ser exhaustivas (la propia
DGSFP lo declara). Este índice solo representa hechos publicados por
los supervisores, con su provenance.
