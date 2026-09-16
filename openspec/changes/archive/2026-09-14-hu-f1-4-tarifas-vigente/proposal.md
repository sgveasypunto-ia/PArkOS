# Proposal: HU-F1.4 — Filtro vigente_en en tarifas_sucursal

> **Change**: `hu-f1-4-tarifas-vigente`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-spec`
> **Preflight**: `pace=auto`, `artifact=hybrid` (OpenSpec + Engram), `delivery=auto-chain`,
    `review_budget=400 lines/PR` (per `openspec/config.yaml`, vigente)
> **HU ID**: HU-F1.4 (Fase-1 prerequisites — backend)
> **Decisión contractual resuelta**: se **modifica** `GET /empresa/tarifas-sucursal`
    agregando el query param opcional `vigente_en: datetime | None = None`. NO se crea un
    path separado. Ver §12 Open Questions para el conflicto resuelto plan.md vs prompt
    original.
> **Inputs**: `plan.md` (línea 471, patrón bi-temporal canónico), `modelo_datos_er.mmd`
    (líneas 406–426), `openspec/specs/operations/spec.md` (último REQ-OPS-NNN vigente:
    REQ-OPS-016), `openspec/changes/archive/2026-09-09-sync-overhaul/` (forma canónica del
    repo), commit `f7cb37a` (HU-F1.1 GAP-BE-02, no se toca).

## 1. Why

`GET /empresa/tarifas-sucursal` hoy expone únicamente las versiones con `vigente_hasta IS
NULL` (HU-F1.1 GAP-BE-02, commit `f7cb37a`). Esto es correcto para un POS que pregunta
"¿cuánto cobro ahora?" pero insuficiente para tres casos de uso reales:

1. **Auditoría retroactiva**: cuando un arqueo no cuadra, el operador necesita ver
   qué tarifa se aplicaba al egreso, no la actual. Hoy debe pedir el cambio por fuera del
   sistema o revertir manualmente la lectura.
2. **Tarifa programada (futuro)**: `modelo_datos_er.mmd:407` declara que `vigente_desde`
   admite fecha futura ("tarifa programada"). La API no expone cómo consultar esas filas
   sin filtrar `vigente_desde__gte` y razonar a mano sobre el solapamiento.
3. **Resolución de disputas**: un cliente que objeta el cobro de una visita pasada exige
   ver la tarifa efectiva en ese momento exacto.

El patrón bi-temporal canónico ya está ratificado en el plan (línea 471) y replicado en
`resolve_active_subscription_for_exit(as_of=...)` (`operacion.py:215-277`). Sólo falta
exponerlo en este endpoint con la misma forma idiomática (un único query param opcional
con default `now(UTC)`) para preservar retrocompatibilidad al pie de la letra.

## 2. Decision Summary

| # | Decisión | Rationale |
|---|---|---|
| **D-HU-F1.4-1** | Modificar `GET /empresa/tarifas-sucursal` agregando query param opcional `vigente_en: datetime \| None = None` (default `datetime.now(UTC)`) | Cumple los 3 casos de uso sin nuevo endpoint; preserva retrocompatibilidad al pie de la letra; alinea con el precedente de `resolve_active_subscription_for_exit(as_of=...)` |
| **D-HU-F1.4-2** | Handler dedicado registrado ANTES del mount genérico del factory | El factory (HU-F1.1) sigue siendo la opción por defecto para el resto de recursos `[V]`; el dedicado gana sólo para `tarifas-sucursal`. Cero impacto sobre otros paths |
| **D-HU-F1.4-3** | Predicado bi-temporal canónico: `vigente_desde <= :vigente_en AND (vigente_hasta IS NULL OR vigente_hasta > :vigente_en) AND estado = 'activo'` | Texto del plan.md línea 471 + filtro complementario por `estado` (defensa en profundidad) |
| **D-HU-F1.4-4** | Conversión tz→UTC antes del bind (patrón `_parse_cursor_timestamp`); naive se interpreta como UTC | DB column es `DateTime(timezone=False)`; asyncpg no acepta `timestamptz` implícito en `WHERE`; mismo bug documentado en `router_factory.py:84-113` |
| **D-HU-F1.4-5** | Helper puro `repo/tarifas_vigencia.py::list_tarifas_vigentes(session, *, vigente_en, filter, cursor, limit)`; sin tocar `make_router` | Encapsula conversión tz + predicado + cursor + orden; testeable sin HTTP; HU-F1.1 lo estabilizó, no se modifica |
| **D-HU-F1.4-6** | Sin migración Alembic nueva, sin UPDATE/DELETE libre, sin tocar tablas `[A]`/`[L-W]` | El endpoint opera exclusivamente sobre columnas existentes; cero schema, cero triggers, cero hooks del sync motor |

## 3. Goals & Non-Goals

### 3.1 Goals

1. Exponer el patrón bi-temporal canónico del plan sobre `GET /empresa/tarifas-sucursal`
   con un único query param opcional `vigente_en`.
2. Preservar retrocompatibilidad al pie de la letra: cuando `vigente_en` se omite, el
   comportamiento es exactamente el actual (sólo `vigente_hasta IS NULL` + filtro vigente).
3. Permitir auditoría retroactiva, consulta de tarifas programadas y resolución de
   disputas con un único endpoint, sin paths nuevos.
4. Mantener el orden de cursor pagination exactamente igual
   (`vigente_desde DESC, uuid ASC`) para no invalidar cursors ya emitidos.
5. Defensa en profundidad: nunca se devuelve una fila con `estado='inactivo'`, alineado
   con el patrón de `resolve_active_subscription_for_exit`.

### 3.2 Non-Goals

1. NO se crea path nuevo (`GET /tarifas-sucursal/vigentes` u otro). Decisión contractual.
2. NO se modifica `make_router` (HU-F1.1 GAP-BE-02 lo estabilizó en `f7cb37a`).
3. NO se crea migración Alembic nueva (operamos sobre columnas existentes).
4. NO se introducen nuevos endpoints, verbos o sub-rutas sobre el recurso.
5. NO se agrega `vigente_en` al factory genérico — sólo al de `tarifas-sucursal`.
6. NO se toca el sync motor, los hooks, los workers ni el `SyncCatalog`.
7. NO se agrega tenant scoping (es un GET de lectura del mismo recurso ya filtrable por
   `uuid_sucursal`).

## 4. Architecture Overview

```
                                    ┌──────────────────────────────────────────┐
HTTP GET /empresa/tarifas-sucursal  │  FastAPI router (empresa.py:142-149)    │
?cursor=…&limit=50&vigente_en=…     │                                          │
                                    │  ┌────────────────────────────────────┐  │
                                    │  │ Handler dedicado (NUEVO)           │  │
                                    │  │ registrado ANTES de _mount_empresa │  │
                                    │  └─────────────┬──────────────────────┘  │
                                    │                │                         │
                                    │                ▼                         │
                                    │  ┌────────────────────────────────────┐  │
                                    │  │ repo/tarifas_vigencia.py (NUEVO)   │  │
                                    │  │ ::list_tarifas_vigentes(...)       │  │
                                    │  │                                    │  │
                                    │  │  1. tz→UTC (vigente_en)            │  │
                                    │  │  2. vigente_desde <= :vigente_en   │  │
                                    │  │     AND (vigente_hasta IS NULL     │  │
                                    │  │         OR vigente_hasta > :v_en) │  │
                                    │  │     AND estado = 'activo'         │  │
                                    │  │  3. order (vigente_desde DESC,     │  │
                                    │  │          uuid ASC)                 │  │
                                    │  │  4. cursor compat (vigente_desde)  │  │
                                    │  └─────────────┬──────────────────────┘  │
                                    │                │                         │
                                    │                ▼                         │
                                    │  ┌────────────────────────────────────┐  │
                                    │  │  prod.tarifas_sucursal  (read-only)│  │
                                    │  │  (columnas existentes, sin Δ)     │  │
                                    │  └────────────────────────────────────┘  │
                                    │                                          │
                                    │  FALLBACK (otros recursos [V]):          │
                                    │  ┌────────────────────────────────────┐  │
                                    │  │ make_router (HU-F1.1, sin cambios)│  │
                                    │  │ hasattr(model_cls, vigente_hasta)  │  │
                                    │  └────────────────────────────────────┘  │
                                    └──────────────────────────────────────────┘
```

El handler dedicado se registra en `empresa.py` **antes** del `_mount_empresa` del recurso
para que FastAPI lo prefiera por especificidad de path. El factory sigue activo y
proveyendo el resto de recursos `[V]` sin modificación.

## 5. Capabilities

### New

- **`repo/tarifas_vigencia.py::list_tarifas_vigentes`** — helper puro async, sin estado,
  con signature `async def list_tarifas_vigentes(session: AsyncSession, *,
  vigente_en: datetime, filter: TarifasSucursalFilter, cursor: str | None,
  limit: int) -> tuple[list[TarifasSucursal], str | None]`. Encapsula conversión tz, predicado
  bi-temporal, orden, cursor y limit.
- **`Handler dedicado `GET /empresa/tarifas-sucursal` con `vigente_en`** — reemplaza el
  `list_endpoint` del factory para este único recurso. Mantiene la misma response shape
  (`TarifasSucursalReadList` con `items` + `next_cursor`).

### Modified

- **`schemas/empresa.py::TarifasSucursalFilter`** — agregar `vigente_en: datetime | None = None`
  (línea 309 → 310). Pydantic con `extra='forbid'`; el campo acepta ISO-8601 con/sin tz.
- **`api/v1/empresa.py`** — registrar handler dedicado antes del `_mount_empresa` de
  `tarifas-sucursal` (líneas 142-149). El factory queda intacto.
- **`openspec/specs/operations/spec.md`** — agregar REQ-OPS-017..020 + entrada en
  `## Modified Capabilities`.

## 6. Data Model

`modelo_datos_er.mmd` líneas 406-426, **literal**:

```
tarifas_sucursal {
    %% [V] Precio por sede x tipo de vehículo x modalidad; el histórico reconstruye
    %% con qué tarifa se cobró; vigente_desde admite fecha futura (tarifa programada)
    %% Business
    uuid uuid PK "UUIDv4 generado en el nodo que crea la fila (offline-safe, sin colisión entre sedes)"
    uuid uuid_sucursal FK "UK01 (uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, vigente_desde)"
    uuid uuid_tipo_vehiculo FK "UK01"
    uuid uuid_tipo_tarifa FK "UK01 - modalidad tarifada (hora, fracción, plena)"
    decimal valor "precio de la modalidad para la combinación"
    decimal valor_plena "tope/tarifa plena diaria asociada"
    %% Audit
    timestamp created_at "cuándo la DB registró la fila (UTC)"
    uuid created_by "usuario que originó la inserción"
    %% Versioning
    timestamp vigente_desde "inicio de vigencia de esta versión (parte de la UK)"
    timestamp vigente_hasta "fin de vigencia (NULL = vigente); el momento de sistema del cierre queda en log_transaccional"
    string estado "estado de la versión: activo | inactivo (hecho escrito al insertar)"
    %% Sync
    string sync_status "replicación: pendiente | sincronizado | error"
    timestamp sync_timestamp "última sincronización exitosa"
    int sync_attempts "reintentos de sync consumidos"
}
```

**Por qué ninguna columna se toca**: HU-F1.4 opera sobre `vigente_desde`, `vigente_hasta`
y `estado`, todas existentes. UK01 (`uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa,
vigente_desde`) no se altera. No hay DDL — sólo lectura.

## 7. API Surface

| Path | Method | Cambio | Issuer / rol |
|---|---|---|---|
| `/empresa/tarifas-sucursal` | GET | query param opcional `vigente_en: datetime \| None` (default `datetime.now(UTC)`) | `admin-,operador-` con `config_tarifas` |

**Request signature completa**:

```python
async def list_tarifas_sucursal(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    vigente_en: datetime | None = Query(
        None,
        description="Punto en el tiempo para el predicado de vigencia. "
                    "Acepta ISO-8601 con o sin tz (naive = UTC). "
                    "Default: datetime.now(UTC).",
    ),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(issuer_dep),
) -> TarifasSucursalReadList:
```

**Response shape** (sin cambios): `TarifasSucursalReadList(items: list[TarifasSucursalRead],
next_cursor: str | None)`. Cada `TarifasSucursalRead` lleva los mismos 12 campos que hoy
(`uuid, uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, valor, valor_plena,
vigente_desde, vigente_hasta, estado, created_at, created_by, sync_status`).

**Sin cambios sobre**:

- `POST /empresa/tarifas-sucursal` (create)
- `PUT /empresa/tarifas-sucursal` (close + insert via factory)
- `GET /empresa/tarifas-sucursal/{uuid}` (current single)
- `GET /empresa/tarifas-sucursal/{uuid}/history` (full history)

## 8. Risks & Mitigations

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| R1 | Cambio de comportamiento silencioso: clientes existentes que dependan del filtro `vigente_hasta IS NULL` ahora reciben un subconjunto ligeramente distinto (excluye `estado='inactivo'` aunque `vigente_hasta IS NULL`) | Baja | Default `now(UTC)` colapsa al comportamiento actual para todas las filas activas vigentes; las filas inactivas con `vigente_hasta IS NULL` ya no se devuelven sin que el caller lo pida explícitamente — alineado con `resolve_active_subscription_for_exit`. Cubierto por test de retrocompatibilidad |
| R2 | Cursor pagination se invalida si el orden cambia | Baja | Reutiliza exactamente `(vente_desde DESC, uuid ASC)` + el mismo `_parse_cursor_timestamp` del factory. Test de cursor compat con `vigente_en` ausente |
| R3 | Convivencia con el factory — el handler dedicado se registra por path, no por método. Si en el futuro se agregan nuevos verbos al recurso, deben respetar el handler dedicado | Baja | Documentado como KD-4 en `design.md`; el comentario en el handler dedicado explica el orden de registro |
| R4 | `vigente_en` con tz offset no normalizado produce el bug documentado en `_parse_cursor_timestamp` (asyncpg rechaza `timestamptz` implícito en `WHERE`) | Baja | Helper puro normaliza a UTC antes del bind; naive se interpreta como UTC; tests cubren tz-aware, naive, con Z, con offset |
| R5 | Default `datetime.now(UTC)` evaluado una sola vez en FastAPI dependency o en cada request? — race entre requests concurrentes | Baja | Se evalúa dentro del handler dedicado (por request), no en module load. Cubierto por test de monotonicidad simple |

## 9. Success Criteria

1. `GET /empresa/tarifas-sucursal` sin `vigente_en` devuelve exactamente las mismas filas
   que antes (mismo conjunto, mismo orden, mismo cursor).
2. `GET /empresa/tarifas-sucursal?vigente_en=2026-01-15T00:00:00Z` devuelve sólo filas
   vigentes en ese instante, ordenadas por `vigente_desde DESC, uuid ASC`.
3. `vigente_en` con tz offset (`+05:00`, `-03:00`) y con `Z` se normaliza correctamente
   a UTC y produce los mismos resultados que su equivalente UTC.
4. Filas con `estado='inactivo'` y `vigente_hasta IS NULL` **NO** se devuelven ni con
   `vigente_en` omitido ni con `vigente_en` explícito en su ventana.
5. Filas con `vigente_desde` futuro y `vigente_hasta IS NULL` se devuelven cuando
   `vigente_en >= vigente_desde`.
6. El cursor `next_cursor` emitido por el factory antes del deploy sigue funcionando:
   el handler dedicado lo decodifica con `_parse_cursor_timestamp`.
7. `make_router` no se modifica — el commit `f7cb37a` no se toca.
8. Ninguna migración Alembic nueva; `modelo_datos_er.mmd` intacto.

## 10. Out of Scope (deferred)

- Aplicar el mismo patrón bi-temporal al resto de `[V]` del módulo `empresa` (p.ej.
  `cantidad-vehiculos-sucursal`, `resolucion-facturacion`). Sale del scope de HU-F1.4.
- Path dedicado `GET /tarifas-sucursal/vigentes`. Decisión contractual: NO.
- Filtro `vigente_en` en el factory genérico. Sale del scope; mantener el factory estable.
- Versionado de UI cliente (la UI consume `vigente_en` cuando lo necesita; sin breaking).

## 11. Relevant Files

- `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py` — registro del handler
  dedicado antes del mount (líneas 142-149).
- `backend/packages/parkos_core/src/parkos_core/api/router_factory.py` — patrón de cursor y
  orden a reutilizar; **no se modifica** (commit `f7cb37a`).
- `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py` — `TarifasSucursalFilter`
  (líneas 303-309) gana `vigente_en`.
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (NUEVO) — helper
  puro `list_tarifas_vigentes`.
- `backend/tests/unit/test_tarifas_vigente_en.py` (NUEVO) — tests RED-then-GREEN.
- `backend/tests/integration/test_tarifas_vigente_en_db.py` (NUEVO) — DB-backed contra
  `pg_engine` real.
- `openspec/specs/operations/spec.md` — REQ-OPS-017..020 + Modified Capabilities.
- `modelo_datos_er.mmd` — tabla `tarifas_sucursal` (líneas 406-426), sin cambios.
- `openspec/changes/hu-f1-4-tarifas-vigente/{exploration,proposal,tasks,design}.md` +
  `specs/operational/spec.md` — este change (5 archivos).

## 12. Open Questions

- **OQ-1**: ¿path nuevo `GET /tarifas-sucursal/vigentes` o extender el existente? —
  **RESUELTO a favor de extender el existente** (`GET /empresa/tarifas-sucursal` con query
  param `vigente_en`). Decisión contractual ratificada por el usuario en el plan.md. NO se
  crea path nuevo. Conflicto con `prompts/00-ejecutor-fase-1.md` original cerrado a favor
  de plan.md.
- **OQ-2**: ¿incluir `estado='activo'` en el predicado? — **RESUELTO: SÍ**. Defensa en
  profundidad consistente con el patrón de `resolve_active_subscription_for_exit`; el
  factory genérico no lo hace pero HU-F1.4 sí lo hace (el factory lo estabilizó HU-F1.1
  para los demás recursos, no para tarifas). Documentado en D-HU-F1.4-3.