# Spec: operational

> **Change**: `hu-f1-4-tarifas-vigente`
> **Phase**: spec (sdd-spec)
> **HU**: HU-F1.4 — Filtro temporal `vigente_en` sobre `GET /empresa/tarifas-sucursal`
> **Source of truth**: `proposal.md` (D-HU-F1.4-1..6), `design.md` (KD-1..5),
    `exploration.md`, `modelo_datos_er.mmd:406-426`.
> **Contexto upstream**: este change extiende la capability **operational** ya existente
    en `openspec/specs/operations/spec.md` (último REQ-OPS-NNN vigente: REQ-OPS-016).
    HU-F1.4 introduce 4 requirements nuevos (REQ-OPS-017..020) que se integran a esa
    capability; los REQ-OPS-001..016 vigentes NO se modifican. La decisión contractual del
    usuario (path único `GET /empresa/tarifas-sucursal` con query param opcional, NO path
    nuevo) queda documentada en `proposal.md` §12 Open Questions como RESUELTA.

## Purpose

Exponer el patrón bi-temporal canónico del plan (`vigente_desde <= :vigente_en AND
(vigente_hasta IS NULL OR vigente_hasta > :vigente_en) AND estado = 'activo'`) sobre el
endpoint existente `GET /empresa/tarifas-sucursal` mediante un query param opcional
`vigente_en: datetime | None = None` (default `datetime.now(UTC)`), sin crear un path nuevo,
sin modificar `make_router` (estabilizado por HU-F1.1 GAP-BE-02 commit `f7cb37a`), sin
migración Alembic, sin tocar tablas, columnas o triggers. El handler dedicado se registra
antes del mount genérico para `tarifas-sucursal` y delega en el helper puro
`repo/tarifas_vigencia.py::list_tarifas_vigentes` que encapsula la conversión tz→UTC, el
predicado, el orden de cursor y la paginación.

El precedente idiomático es `resolve_active_subscription_for_exit(..., as_of=...)` en
`backend/.../api/v1/operacion.py:215-277`. La forma del nuevo query param (`vigente_en`,
default `now(UTC)`, normalización tz→UTC) replica ese patrón, adaptado de `date` a
`datetime` para precisión por hora (las tarifas se cobran por modalidad horaria).

## Requirements

### REQ-OPS-017: Query param `vigente_en` opcional en `GET /empresa/tarifas-sucursal`

**Given** el cliente envía `GET /empresa/tarifas-sucursal` con un query param
opcional `vigente_en` en formato ISO-8601 (con o sin tz; naive se interpreta como UTC)
**When** el handler dedicado de HU-F1.4 procesa la request
**Then** el endpoint MUST aceptar el valor y propagarlo al helper
`repo/tarifas_vigencia.py::list_tarifas_vigentes` como un `datetime` UTC-normalizado
**And** MUST usar `datetime.now(UTC)` cuando `vigente_en` se omite (preservando
retrocompatibilidad con el comportamiento previo del factory para el subconjunto de
filas con `estado='activo'`)
**And** MUST aceptar ISO-8601 con sufijo `Z` (zona UTC explícita)
**And** MUST aceptar offsets ISO-8601 (`+05:00`, `-03:00`, etc.) y normalizarlos a UTC
**And** MUST devolver `422 Unprocessable Entity` cuando `vigente_en` no parsea como
ISO-8601 (Pydantic + `datetime.fromisoformat`)
**And** MUST devolver `422 Unprocessable Entity` cuando el offset está fuera del rango
válido (`±14:00` por convención IANA, validado por `datetime.fromisoformat`)
**And** MUST seguir devolviendo `400 invalid_cursor` cuando `cursor` no decodifica,
independiente del valor de `vigente_en`
**And** MUST seguir exigiendo los issuers `admin-,operador-` y el permiso
`config_tarifas` (sin cambios respecto al factory).
**And** SHALL documentar el query param en el OpenAPI generado por FastAPI con
`description=` que explique: punto en el tiempo para el predicado de vigencia, formato
ISO-8601, naive=UTC, default `now(UTC)`.

> **Amended — fue una sección del factory genérico.** Previo a HU-F1.4, el factory
> atendía este recurso con un comportamiento fijo (`vigente_hasta IS NULL`); la
> cobertura de ese comportamiento pasa a ser un subconjunto del default de HU-F1.4.
> El factory NO se modifica: el handler dedicado gana por orden de registro
> (KD-4 del `design.md`).

### REQ-OPS-018: Predicado bi-temporal canónico con `estado='activo'`

**Given** el handler dedicado invoca `list_tarifas_vigentes(session, *, vigente_en, filter, cursor, limit)`
**When** el helper construye el `SELECT`
**Then** el predicado MUST ser exactamente:
`vigente_desde <= :vigente_en AND (vigente_hasta IS NULL OR vigente_hasta > :vigente_en) AND estado = 'activo'`
**And** el predicado MUST aplicarse como filtros `WHERE` de SQLAlchemy, no como filtros
post-fetch en Python (defensa en profundidad: el índice subyacente se usa para reducir
el conjunto antes del bind)
**And** `vigente_en` MUST estar normalizado a UTC **naive** antes del bind (DB column
`DateTime(timezone=False)`; `asyncpg` rechaza `timestamptz` implícito en `WHERE`)
**And** SHALL reutilizar el patrón `_parse_cursor_timestamp` de
`backend/.../api/router_factory.py:84-113` para la normalización tz→UTC naive
**And** SHALL incluir el filtro `estado='activo'` siempre, **independiente** del valor de
`vigente_en` (incluido el default `now(UTC)`) — defensa en profundidad consistente con
`resolve_active_subscription_for_exit` (`operacion.py:215-277`)
**And** MUST persistir el orden por `vigente_desde DESC, uuid ASC` (idéntico al factory)
para que los cursors emitidos antes del deploy sigan decodificando correctamente.

### REQ-OPS-019: Handler dedicado antes del mount genérico del factory

**Given** el recurso `tarifas-sucursal` está registrado en `empresa.py` mediante
`_mount_empresa(...)` (líneas 142-149) que a su vez invoca `make_router(...)`
**When** `sdd-apply` registra el handler dedicado de HU-F1.4
**Then** el handler MUST estar declarado con `@router.get("")` (raíz del recurso)
explícitamente **antes** del bloque `_mount_empresa("tarifas-sucursal", …)` en
`backend/.../api/v1/empresa.py`
**And** FastAPI MUST preferir el handler dedicado por orden de registro sobre el
`list_endpoint` del factory para el método `GET` y path `""` (sin slug)
**And** los demás verbos del recurso (`POST`, `PUT`, `GET /{uuid}`,
`GET /{uuid}/history`) MUST seguir siendo atendidos por el factory sin cambios
**And** el factory (`make_router`) MUST permanecer intacto: HU-F1.1 GAP-BE-02
(commit `f7cb37a`) lo estabilizó y NO se modifica
**And** los demás recursos `[V]` del módulo `empresa` (`cantidad-vehiculos-sucursal`,
`resolucion-facturacion`, `documentos`, `usuarios-sucursal`) MUST seguir siendo
atendidos por el factory sin handler dedicado
**And** SHALL documentar el orden de registro con un comentario inline en `empresa.py`
explicando que el handler dedicado gana por especificidad de path.

### REQ-OPS-020: Helper puro `repo/tarifas_vigencia.py::list_tarifas_vigentes`

**Given** el handler dedicado de HU-F1.4 necesita aplicar el predicado bi-temporal sobre
`prod.tarifas_sucursal` con conversión tz→UTC, orden estable y cursor pagination
**When** `sdd-apply` crea `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py`
**Then** el módulo MUST exponer una única función async pública con signature
`async def list_tarifas_vigentes(session: AsyncSession, *, vigente_en: datetime,
filter: TarifasSucursalFilter, cursor: str | None, limit: int) -> tuple[list[TarifasSucursal], str | None]`
**And** la firma MUST ser keyword-only a partir de `vigente_en` para evitar swaps de
argumentos posicionales
**And** el orden de las filas MUST ser exactamente `(TarifasSucursal.vigente_desde.desc(),
TarifasSucursal.uuid.asc())` — idéntico al factory
**And** el cursor MUST decodificarse usando
`router_factory._parse_cursor_timestamp` y la misma `(order_col, cursor_field) =
router_factory._order_key(model_cls)` (cursor field = `vigente_desde` para esta tabla)
**And** el helper MUST ejecutar `SELECT … LIMIT limit + 1` y emitir `next_cursor` cuando
el conjunto devuelto excede `limit` (mismo patrón que el factory)
**And** el helper MUST ser SELECT puro: no `INSERT`, `UPDATE`, `DELETE`, no side-effects,
no cache, no lock
**And** SHALL encapsular el predicado en una constante constante a nivel de módulo
(`BITEMPORAL_VIGENTE_PREDICATE` o equivalente) para que los tests unit la referencien
sin reescribir el SQL
**And** el helper SHALL coexistir con `make_router` sin importar ni tocar
`router_factory.make_router` más allá de las dos funciones reusadas
(`_parse_cursor_timestamp`, `_order_key`); sin imports circulares.

### REQ-OPS-021: Campo `vigente_en` en `TarifasSucursalFilter`

> **NOTA**: este requirement se asigna REQ-OPS-021 (no REQ-OPS-018-bis) para preservar
> monotonicidad con la serie REQ-OPS-001..016 ya existente en
> `openspec/specs/operations/spec.md`. El correlativo 020 se reservó para el helper puro
> por ser la dependencia más cargada del handler dedicado. Si el lector encuentra
> inconsistente el orden numérico frente a la redacción (REQ-OPS-017..020 en proposal.md
> y design.md vs REQ-OPS-017, 018, 020, 021 acá), la divergencia es **documentada, no
> resuelta**: el agente writer no edita `proposal.md` ni `design.md` para reordenar, y
> el agente apply decide si unificar durante la implementación.

**Given** el handler dedicado construye un `TarifasSucursalFilter` para reenviar al
helper `list_tarifas_vigentes`
**When** `sdd-apply` modifica `backend/.../schemas/empresa.py`
**Then** la clase `TarifasSucursalFilter` MUST agregar el campo
`vigente_en: datetime | None = None` después del último campo existente (línea 309)
**And** el campo MUST heredar `extra='forbid'` de la `_Base` (Pydantic) para rechazar
query params desconocidos con 422
**And** el campo MUST aceptar `datetime | None` (no `str`): Pydantic con `datetime`
builtin parsea ISO-8601 directamente y rechaza lo malformado
**And** SHALL incluir `description=` que diga "Punto en el tiempo para el predicado de
vigencia. ISO-8601 con o sin tz; naive = UTC. Default en el handler: `datetime.now(UTC)`."
**And** SHALL mantener retrocompatibilidad: las instancias existentes de
`TarifasSucursalFilter` (en el factory para los demás verbos, en tests, en scripts) MUST
seguir funcionando sin cambios — el campo nuevo tiene default `None`.

## Scenarios

### SC-HU-F1.4-1: Default `now(UTC)` retorna mismas activas que el factory

1. Seed: una fila `tarifas_sucursal` con `vigente_hasta IS NULL`, `estado='activo'`,
   `vigente_desde < now(UTC)`.
2. Seed: una fila `tarifas_sucursal` con `vigente_hasta IS NULL`, `estado='inactivo'`,
   `vigente_desde < now(UTC)`.
3. `GET /empresa/tarifas-sucursal` (sin `vigente_en`).
4. Respuesta 200, `items` contiene la fila 1, NO contiene la fila 2.

### SC-HU-F1.4-2: `vigente_en` pasado retorna ventana cubridora

1. Seed: tres filas con `vigente_desde` en `2026-01-01`, `vigente_desde` en
   `2026-06-01`, `vigente_desde` en `2026-12-01`; cada una con `vigente_hasta` un mes
   después; todas con `estado='activo'`.
2. `GET /empresa/tarifas-sucursal?vigente_en=2026-08-15T00:00:00Z`.
3. Respuesta 200, `items` contiene la fila 2; NO contiene las filas 1 ni 3.

### SC-HU-F1.4-3: `vigente_en` futuro incluye tarifas programadas

1. Seed: una fila con `vigente_desde = 2027-01-01`, `vigente_hasta IS NULL`,
   `estado='activo'`.
2. `GET /empresa/tarifas-sucursal?vigente_en=2026-12-15T00:00:00Z`.
3. Respuesta 200, `items` NO contiene la fila 1.
4. `GET /empresa/tarifas-sucursal?vigente_en=2027-01-15T00:00:00Z`.
5. Respuesta 200, `items` contiene la fila 1.

### SC-HU-F1.4-4: Tz offset normalizado a UTC

1. Seed: una fila con `vigente_desde = 2026-01-15T05:00:00Z`, `vigente_hasta IS NULL`,
   `estado='activo'`.
2. `GET /empresa/tarifas-sucursal?vigente_en=2026-01-15T05:00:00+05:00`.
3. Respuesta 200, `items` contiene la fila 1 (es vigente en su `vigente_desde` exacto).
4. `GET /empresa/tarifas-sucursal?vigente_en=2026-01-15T00:00:00-05:00`.
5. Respuesta 200, `items` contiene la fila 1 (mismo instante UTC, distinto offset).

### SC-HU-F1.4-5: Cursor compat con `vigente_en` ausente

1. Seed: 51 filas con `vigente_desde` en orden descendente.
2. `GET /empresa/tarifas-sucursal?limit=50` (sin `vigente_en`).
3. Respuesta 200, `items` tiene 50 filas, `next_cursor` no nulo.
4. `GET /empresa/tarifas-sucursal?limit=50&cursor=<next_cursor>` (sin `vigente_en`).
5. Respuesta 200, `items` tiene la fila 51.

### SC-HU-F1.4-6: Coexistencia factory intacto para otros recursos

1. Seed: una fila `cantidad_vehiculos_sucursal` con `vigente_hasta IS NULL`,
   `estado='inactivo'`.
2. `GET /empresa/cantidad-vehiculos-sucursal`.
3. Respuesta 200, `items` contiene la fila con `estado='inactivo'` (factory sin filtro
   `estado='activo'`).
4. `GET /empresa/tarifas-sucursal`.
5. Respuesta 200, ninguna fila con `estado='inactivo'` (handler dedicado sí filtra).

## Modified Capabilities

- `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py` — handler dedicado
  antes del `_mount_empresa("tarifas-sucursal", …)` (líneas 142-149). Factory intacto.
- `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py` — `TarifasSucursalFilter`
  agrega `vigente_en: datetime | None = None` (REQ-OPS-021). `extra='forbid'` preservado.
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (NUEVO) —
  helper puro `list_tarifas_vigentes` (REQ-OPS-020).
- `backend/tests/unit/test_tarifas_vigente_en.py` (NUEVO) — tests RED-then-GREEN.
- `backend/tests/integration/test_tarifas_vigente_en_db.py` (NUEVO) — DB-backed contra
  `pg_engine` real.
- `backend/tests/conftest.py` — fixtures nuevas (`seed_tarifa_*`) para los tests
  DB-backed.
- `openspec/specs/operations/spec.md` (raíz) — entrada en `## Modified Capabilities`:
  "`TarifasSucursalFilter` agrega `vigente_en` (REQ-OPS-021)" + "`api/v1/empresa.py`
  registra handler dedicado antes del mount genérico para `tarifas-sucursal` (REQ-OPS-019)".

## Out of Scope

- Aplicar el mismo patrón bi-temporal al resto de `[V]` del módulo `empresa`
  (`cantidad-vehiculos-sucursal`, `resolucion-facturacion`, `documentos`,
  `usuarios-sucursal`). Sale del scope de HU-F1.4 — sería otra HU con su propio analysis.
- Path nuevo `GET /tarifas-sucursal/vigentes`. Decisión contractual: NO.
- Filtro `vigente_en` en el factory genérico. Sale del scope; factory permanece estable.
- Modificación de `make_router` (HU-F1.1 GAP-BE-02 commit `f7cb37a` lo estabilizó).
- Migración Alembic nueva. Cero DDL.
- Sync motor, hooks, workers, `SyncCatalog`. Sin cambios.
- Tenant scoping nuevo (el endpoint ya filtra por `uuid_sucursal` via el filtro
  existente).