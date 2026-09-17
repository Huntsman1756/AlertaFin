# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto usa [Versionado Semántico](https://semver.org/lang/es/).

Los resultados de evaluación congelados (G0, G0-R, holdout-v2, G1-WI) son
históricos e inmutables: los cambios de código no reescriben esos
veredictos; ver `README.md` y los ADR.

## [Unreleased]

### Corregido

- `--dataset` pasado antes del subcomando ya no se ignora: el default del
  subparser ya no sobrescribe el valor top-level. Si se pasa en ambas
  posiciones, gana el del subcomando.
- Caché de adquisición: ahora implementa lo documentado ("máx. 1
  pull/día"). Antes, un pull OK se reutilizaba indefinidamente sin
  volver a pedir la fuente; el parámetro `today` era código muerto.
- Dataset corrupto, vacío o ilegible: la CLI emite `SOURCE_UNAVAILABLE`
  (exit 3) con mensaje controlado y número de línea, en lugar de un
  traceback de `json.JSONDecodeError`.
- `recent`: `--days` negativo y `--today` no-ISO son errores de uso
  (exit 2); las `fecha` malformadas del dataset se saltan y se contabilizan
  en `skipped_invalid_fecha` en vez de tumbar el comando.
- Payload no decodificable o con cambio de esquema durante la adquisición:
  estado `PARSE_FAILED` (exit 4) registrado en `last_attempt.json`, bytes
  retenidos en el byte store como evidencia y último dataset válido
  preservado. Antes era un traceback no controlado.
- User-Agent honesto (`alertafin/<version> +URL del proyecto`) en lugar de
  suplantar a Chrome. Verificado que la fuente CNMV no lo requiere.

### Añadido

- `python -m alertafin` funciona (nuevo `__main__.py`).
- Dependencia directa declarada: `idna` (se importaba en `domainex.py`
  apoyándose en que era transitiva de `requests`).
- Configuración de `ruff` en `pyproject.toml`, excluyendo los ficheros de
  evaluación congelados por fingerprint.
- `CHANGELOG.md`.
- CI: job de lint (`ruff check`) y smoke test de la CLI sobre el dataset
  congelado.
- `CONTRIBUTING.md`: lista explícita de los evaluadores fingerprinted y
  `ruff check .` en el flujo de verificación.
- Tests: precedencia de `--dataset`, datasets corruptos/vacíos, rollover
  de la caché diaria, `--force`, `--reprocess` sin red, `PARSE_FAILED` y
  preservación del dataset válido.

## [0.1.0] — G0

- CLI `check` / `recent` / `clones` / `show` sobre el índice CNMV.
- Adquisición con byte store inmutable por SHA-256, log append-only de
  retrievals y provenance por notice.
- Parser RFC4180 a nivel de bytes con `notice_id`/`record_version_id`
  deterministas.
- Resultados de evaluación documentados: gates G0 14/14, golden corpus
  154 casos, blind holdout **FAIL** (histórico), G0-R regression **PASS**,
  holdout-v2 **FAIL**, G1-WI **FAIL** (15/16). Ver `README.md`.
