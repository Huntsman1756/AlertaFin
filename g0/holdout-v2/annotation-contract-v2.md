# Contrato de anotacion v2 — holdout ciego

Reglas deterministas para el anotador. Si un caso no encaja en ninguna
regla, se marca `unclear: true` con nota libre; no se improvisa.

## Dominios

```text
Un token presente en Entidad o Entidad Secundaria que sea
sintacticamente un hostname valido se etiqueta como dominio.
No se intenta inferir si comercialmente se usa como marca.
```

Esta regla resuelve sin discrecionalidad casos tipo `TR.PRO` (token en
`Entidad Secundaria` con forma de hostname -> dominio, sea o no una marca).

```text
URLs/dominios de la entidad legitima citada en Observaciones
-> se excluyen (pertenecen al suplantado, no al advertido).

Dominios presentes exclusivamente dentro de una direccion de email
-> se excluyen.

Subdominios se conservan completos (www incluido);
foo.example.com != example.com.
```

## Clones

```text
afirmacion explicita de clon/suplantacion/imitacion -> clone = true
("similar a" solo, sin afirmacion de suplantacion -> clone = false)

0 targets nominales unicos  -> target = null (UNRESOLVED)
1 target nominal unico      -> target = nombre citado
>1 targets                  -> UNRESOLVED (nunca elegir el primero)

"entidad autorizada del mismo nombre"
-> solo usar entidad_raw como target si la fuente lo afirma
   explicitamente Y entidad_raw es una denominacion nominal utilizable
   (no una URL/dominio).
```

## General

- Solo cuenta lo que el raw afirma; no se infiere por conocimiento externo
  ni por apariencia del dominio.
- Se etiqueta la FILA indicada por `case_key = (notice_id,
  record_version_id)`; un mismo `notice_id` puede tener observaciones
  distintas en otra fila y no se usa.
