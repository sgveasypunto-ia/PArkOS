# Design: hu-f1-4-tarifas-vigente

> **Change**: `hu-f1-4-tarifas-vigente`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.4 — Filtro temporal `vigente_en` sobre `GET /empresa/tarifas-sucursal`
> **Source of truth**: `proposal.md` (D-HU-F1.4-1..6) y `exploration.md`.
> **Cross-references**: `openspec/specs/operations/spec.md` (último REQ-OPS-NNN vigente:
    REQ-OPS-016, los nuevos son REQ-OPS-017..020),
    `modelo_datos_er.mmd:406-426`, `backend/.../api/v1/operacion.py:215-277` (precedente).

## 1. Architecture overview

```
Cliente HTTP (admin/operador con config_tarifas)
            │
            │  GET /empresa/tarifas-sucursal?cursor=…&limit=50&vigente_en=…
            ▼
   ┌────────────────────────────────────────────────────────┐
   │  FastAPI router en api/v1/empresa.py                   │
   │                                                        │
   │  ┌──────────────────────────────────────────────────┐  │
   │  │ Handler dedicado (NUEVO) — registrado ANTES de   │  │
   │  │ _mount_empresa("tarifas-sucursal", …)            │  │
   │  │                                                  │  │
   │  │  def list_tarifas_sucursal(                       │  │
   │  │      cursor, limit, vigente_en, session, ctx, …  │  │
   │  │  ):                                              │  │
   │  │      v = vigente_en or datetime.now(UTC)         │  │
   │  │      rows, nxt = await list_tarifas_vigentes(    │  │
   │  │          session, vigente_en=v,                  │  │
   │  │          filter=TarifasSucursalFilter(...),      │  │
   │  │          cursor=cursor, limit=limit,             │  │
   │  │      )                                           │  │
   │  │      return TarifasSucursalReadList(             │  │
   │  │          items=[TarifasSucursalRead.model_validate(r)│
   │  │                 for r in rows],                  │  │
   │  │          next_cursor=nxt,                        │  │
   │  │      )                                           │  │
   │  └─────────────────────────┬────────────────────────┘  │
   │                            │                            │
   │  ┌─────────────────────────▼────────────────────────┐  │
   │  │ repo/tarifas_vigencia.py (NUEVO)                 │  │
   │  │                                                  │  │
   │  │  async def list_tarifas_vigentes(                │  │
   │  │      session, *, vigente_en, filter,             │  │
   │  │      cursor, limit,                              │  │
   │  │  ) -> tuple[list[TarifasSucursal], str | None]:  │  │
   │  │                                                  │  │
   │  │   1. tz→UTC (vigente_en.astimezone(UTC)          │  │
   │  │      if naive: replace tzinfo=UTC)              │  │
   │  │   2. stmt = select(TarifasSucursal).where(       │  │
   │  │        TarifasSucursal.vigente_desde <= v,       │  │
   │  │        or_(vigente_hasta.is_(None),              │  │
   │  │            vigente_hasta > v),                   │  │
   │  │        TarifasSucursal.estado == 'activo',       │  │
   │  │      ).order_by(vigente_desde.desc(), uuid.asc())│  │
   │  │   3. apply remaining filter (uuid_sucursal,      │  │
   │  │      uuid_tipo_vehiculo, uuid_tipo_tarifa,       │  │
   │  │      vigente_desde__gte/lte, estado)             │  │
   │  │   4. cursor compat via _parse_cursor_timestamp   │  │
   │  │   5. .limit(limit + 1) → detect next_cursor      │  │
   │  └─────────────────────────┬────────────────────────┘  │
   │                            │                            │
   │  ┌─────────────────────────▼────────────────────────┐  │
   │  │  SQLAlchemy 2.x async + asyncpg                  │  │
   │  │  prod.tarifas_sucursal (read-only, sin DDL)      │  │
   │  └──────────────────────────────────────────────────┘  │
   │                                                        │
   │  FALLBACK para otros recursos [V]:                    │
   │  ┌──────────────────────────────────────────────────┐  │
   │  │ make_router (HU-F1.1, f7cb37a, INTACTO)          │  │
   │  │ hasattr(model_cls, "vigente_hasta")              │  │
   │  └──────────────────────────────────────────────────┘  │
   └────────────────────────────────────────────────────────┘
```

El cambio es read-only sobre columnas existentes. Cero DDL, cero trigger, cero migración.
El factory `make_router` (estabilizado en `f7cb37a`) NO se modifica. El handler dedicado
se registra antes del mount genérico para `tarifas-sucursal` y gana por especificidad
de path; el resto de recursos `[V]` (`cantidad-vehiculos-sucursal`, `resolucion-facturacion`,
`documentos`, etc.) siguen siendo atendidos por el factory sin cambios.

## 2. Architecture Decisions

### KD-1 — Coexistencia con `make_router`: handler dedicado antes del mount genérico

**Decisión.** El handler dedicado se registra en `empresa.py` con `@router.get("")`
explícitamente **antes** del bloque `_mount_empresa("tarifas-sucursal", …)` (líneas 142-149).
FastAPI resuelve por orden de registro: el primero declarado para un path gana. El factory
genérico queda intacto y sigue atendiendo a todos los demás recursos `[V]`.

**Por qué no se no toca `make_router`.** HU-F1.1 (`f7cb37a`) lo estabilizó con la cláusula
`if hasattr(model_cls, "vigente_hasta"): stmt = stmt.where(model_cls.vigente_hasta.is_(None))`.
Modificarlo para que acepte un `vigente_en` opcional acopla el factory al esquema bi-temporal
canónico, lo expone al riesgo de regresión sobre los 30+ recursos que lo reusan, y vuelve a
romper la estabilización HU-F1.1. El handler dedicado aísla el cambio.

**Por qué no se no se generaliza el patrón bi-temporal al factory.** Sale del scope de
HU-F1.4 (un único recurso). Si en el futuro se replica a otros `[V]`, será otra HU con su
propio analysis de cuáles necesitan punto-en-tiempo y cuáles no.

### KD-2 — Timestamp con conversión tz→UTC

**Decisión.** `vigente_en` se convierte a UTC antes del bind, replicando el patrón de
`_parse_cursor_timestamp` (`router_factory.py:84-113`):

```python
# Vigente_en viene como datetime (con o sin tz) de FastAPI Query.
# El DB column es DateTime(timezone=False); asyncpg no acepta
# timestamptz implícito en WHERE (bug documentado en el comentario
# de _parse_cursor_timestamp). Normalizamos a naive UTC.
if v.tzinfo is None:
    v = v.replace(tzinfo=UTC)
v_utc = v.astimezone(UTC).replace(tzinfo=None)
```

**Por qué.** El DB column `tarifas_sucursal.vigente_desde` y `vigente_hasta` son
`DateTime(timezone=False)` (verificado por la ausencia de tz en el ER, línea 419-420:
`timestamp`). El bind sin normalizar produce el bug ya documentado en `router_factory.py:91`
("operator does not exist: timestamp without time zone < character varying") y en el caso
tz-aware, "asyncpg sends `timestamp with time zone` and Postgres refuses the implicit cast".

**Naive se interpreta como UTC.** Es la convención del proyecto: `_parse_cursor_timestamp`
también lo hace. Documentado en KD-2 del `proposal.md`.

### KD-3 — Default `now(UTC)` dentro del handler dedicado

**Decisión.** `vigente_en = vigente_en or datetime.now(UTC)` se evalúa **dentro** del
handler, no en module load ni en una dependency global. Cada request obtiene su propio
timestamp.

**Por qué.** Race entre requests concurrentes si se cachea en module load. El handler de
FastAPI es por-request; `datetime.now(UTC)` se llama una vez por invocación. Documentado
como riesgo R5 en `proposal.md` y cubierto por un test de monotonicidad.

### KD-4 — Orden de registro en `empresa.py`

**Decisión.** El handler dedicado se registra **antes** del `_mount_empresa` del recurso
para que FastAPI lo prefiera. El factory genérico queda registrado después (líneas 142-149
actuales) y sigue activo para los demás recursos `[V]`.

**Convención de orden** (a documentar en `empresa.py` con un comentario inline):

```python
# Recursos [V] con handler dedicado (registrar ANTES de _mount_empresa
# para que FastAPI los prefiera por orden de declaración).
#   - tarifas-sucursal (HU-F1.4): handler dedicado con vigente_en.
@router.get("/empresa/tarifas-sucursal", response_model=TarifasSucursalReadList)
async def list_tarifas_sucursal(...): ...

# Resto de recursos [V]: factory genérico (HU-F1.1 GAP-BE-02 estabilizado).
_mount_empresa("tarifas-sucursal", …)  # ← esto queda, no se invoca para el GET list
```

**Importante**: `_mount_empresa` todavía se llama para no romper POST/PUT/GET-by-uuid/history.
El override es **sólo sobre el `list_endpoint`** del factory para este recurso. Esto se
logra registrando el handler dedicado con el mismo path `""` (raíz del router del recurso)
y el mismo método (`GET`), por lo que FastAPI lo prefiere por orden.

Si en el futuro se agregan nuevos verbos al recurso, deben respetar el handler dedicado o
reusar el factory. Documentado como riesgo R3.

### KD-5 — Path `vigente_en` opcional en `TarifasSucursalFilter`

**Decisión.** El campo se declara en `schemas/empresa.py::TarifasSucursalFilter` (después de
la línea 309) como `vigente_en: datetime | None = None`. El `Query` se declara en el handler
dedicado (no en el schema) para mantener la separación entre "modelo de validación" y
"parámetro HTTP". El schema sólo transporta el valor validado al helper.

**Por qué en el schema y no como parámetro libre.** El handler construye un
`TarifasSucursalFilter(**campos)` con los filtros vigentes (`uuid_sucursal`, etc.) y el
nuevo `vigente_en`. El helper acepta un solo argumento `filter: TarifasSucursalFilter` para
mantener la firma consistente con futuras extensiones.

**Pydantic con `extra='forbid'`** (heredado de `_Base`). Esto rechaza query params
desconocidos con 422 en lugar de silenciarlos — defensa en profundidad contra typos de
cliente.

## 3. Data Model

`modelo_datos_er.mmd` líneas 406-426 (literal, sin cambios):

| Columna | Línea | Tipo | Rol en HU-F1.4 |
|---|---|---|---|
| `uuid` | 409 | `uuid PK` | Identidad, sin tocar |
| `uuid_sucursal` | 410 | `uuid FK` (UK01) | Filtrable via `filter.uuid_sucursal` |
| `uuid_tipo_vehiculo` | 411 | `uuid FK` (UK01) | Filtrable |
| `uuid_tipo_tarifa` | 412 | `uuid FK` (UK01) | Filtrable |
| `valor` | 413 | `decimal` | Salida |
| `valor_plena` | 414 | `decimal` | Salida |
| `created_at` | 416 | `timestamp` (UTC) | Salida |
| `created_by` | 417 | `uuid` | Salida |
| `vigente_desde` | 419 | `timestamp` | Lado izquierdo del predicado (`<= :v_en`) |
| `vigente_hasta` | 420 | `timestamp NULL` | Lado derecho (`IS NULL OR > :v_en`) |
| `estado` | 421 | `string activo\|inactivo` | Filtro `= 'activo'` |
| `sync_status` | 423 | `string` | Salida |
| `sync_timestamp` | 424 | `timestamp` | Salida |
| `sync_attempts` | 425 | `int` | Salida |

**Por qué ninguna columna se toca.** HU-F1.4 opera exclusivamente sobre `vigente_desde`,
`vigente_hasta` y `estado`, todas presentes en el ER. UK01
(`uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, vigente_desde`) no se altera. Cero
DDL — sólo lectura.

## 4. API Contracts

### `GET /empresa/tarifas-sucursal` (modificado)

**Request signature**:

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

**Issuer / permisos**: `admin-,operador-` con `config_tarifas` (mismo que el factory).

**Response shape** (sin cambios respecto al factory):

```python
class TarifasSucursalReadList(ReadListBase[TarifasSucursalRead]):
    items: list[TarifasSucursalRead]
    next_cursor: str | None
```

Cada `TarifasSucursalRead` (sin cambios) lleva 12 campos:
`uuid, uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, valor, valor_plena,
vigente_desde, vigente_hasta, estado, created_at, created_by, sync_status`.

**Códigos de error** (heredados del factory):
- 400 `invalid_cursor` si el cursor no decodifica.
- 401 si el issuer no es `admin-,operador-`.
- 403 si falta el permiso `config_tarifas`.
- 422 (Pydantic `extra='forbid'`) si el query trae campos no declarados.
- 422 si `vigente_en` no parsea como ISO-8601.

**Comportamiento por valor de `vigente_en`**:

| `vigente_en` | Predicado efectivo | Caso de uso |
|---|---|---|
| omitido | default `datetime.now(UTC)` → mismo conjunto que el factory, pero **excluye `estado='inactivo'`** | Cliente existente — cambio retrocompatible para filas activas; **rompe** el supuesto de que `estado='inactivo'` con `vigente_hasta IS NULL` se devuelve, alineado con `resolve_active_subscription_for_exit` |
| valor pasado | filas vigentes en ese instante | Auditoría retroactiva, disputas |
| valor futuro | filas vigentes + tarifas programadas que entren en vigencia | Vista de tarifas próximas |
| con tz `+05:00` | normalizado a UTC equivalente | Cliente multi-zona |
| con `Z` | normalizado a UTC | Cliente REST estándar |
| naive | interpretado como UTC | Consistente con `_parse_cursor_timestamp` |
| `2026-01-15T25:00:00` (malformed) | 422 Pydantic | Cliente con bug |

### `POST /empresa/tarifas-sucursal`, `PUT /empresa/tarifas-sucursal/{uuid}`, `GET /{uuid}`, `GET /{uuid}/history`

**Sin cambios.** El factory los sigue atendiendo.

## 5. Sequence Diagrams

### Default `now(UTC)`

```
cliente            handler dedicado            helper                DB
   │                     │                       │                    │
   │ GET /empresa/…?limit=50                      │                    │
   │────────────────────▶│                       │                    │
   │                     │ v = datetime.now(UTC) │                    │
   │                     │ (1 call)              │                    │
   │                     │                       │                    │
   │                     │ list_tarifas_vigentes(│                    │
   │                     │   session,            │                    │
   │                     │   vigente_en=v_utc,   │                    │
   │                     │   filter, cursor,     │                    │
   │                     │   limit)              │                    │
   │                     │──────────────────────▶│                    │
   │                     │                       │ SELECT …           │
   │                     │                       │ WHERE vigente_desde<=v
   │                     │                       │   AND (vigente_hasta IS NULL
   │                     │                       │        OR vigente_hasta>v)
   │                     │                       │   AND estado='activo'
   │                     │                       │ ORDER BY vigente_desde DESC, uuid ASC
   │                     │                       │ LIMIT 51           │
   │                     │                       │───────────────────▶│
   │                     │                       │◀──────────────────│
   │                     │                       │ rows              │
   │                     │◀──────────────────────│                    │
   │                     │ items, next_cursor    │                    │
   │◀────────────────────│                       │                    │
   │ 200 + JSON          │                       │                    │
```

### `vigente_en` pasado explícito

```
cliente            handler dedicado            helper                DB
   │                     │                       │                    │
   │ GET …?vigente_en=2026-01-15T00:00:00Z      │                    │
   │────────────────────▶│                       │                    │
   │                     │ v = parse(2026-01-15T00:00:00Z)           │
   │                     │ v_utc = 2026-01-15 00:00:00 (naive UTC)   │
   │                     │                       │                    │
   │                     │ list_tarifas_vigentes(…)                   │
   │                     │──────────────────────▶│                    │
   │                     │                       │ SELECT …           │
   │                     │                       │ WHERE vigente_desde<=2026-01-15
   │                     │                       │   AND (vigente_hasta IS NULL
   │                     │                       │        OR vigente_hasta>2026-01-15)
   │                     │                       │   AND estado='activo'│
   │                     │                       │ …                  │
   │◀────────────────────│                       │                    │
```

### `vigente_en` con tz offset

```
cliente            handler dedicado            helper                DB
   │                     │                       │                    │
   │ GET …?vigente_en=2026-01-15T05:00:00+05:00  │                    │
   │────────────────────▶│                       │                    │
   │                     │ v = parse(…)  # tz-aware                 │
   │                     │ v_utc = v.astimezone(UTC).replace(tz=None)│
   │                     │       = 2026-01-15 00:00:00 (naive UTC)   │
   │                     │ (mismo predicado que el caso pasado)      │
```

### Cursor compat (factory emit / handler dedicado consume)

```
cliente            factory (HU-F1.1)           DB           cliente           handler dedicado (HU-F1.4)
   │                     │                       │                │                     │
   │ GET … (no vigente_en) │                    │                │                     │
   │────────────────────▶│                       │                │                     │
   │                     │ order (vente_desde DESC, uuid ASC)     │                     │
   │                     │ cursor field = 'vigente_desde'         │                     │
   │                     │ SELECT … +1                           │                     │
   │                     │───────────────────────▶│                │                     │
   │                     │◀──────────────────────│                │                     │
   │                     │ next_cursor = encode({                 │                     │
   │                     │   vigente_desde, uuid                  │                     │
   │                     │ })                                     │                     │
   │◀────────────────────│                       │                │                     │
   │ 200 + items + next_cursor                   │                │                     │
                                                                          │
   │ GET …?cursor=<next_cursor>                                            │
   │────────────────────────────────────────────────────────────────────▶│
                                                                          │ _parse_cursor_timestamp(
                                                                          │   "2026-01-15T00:00:00")
                                                                          │   = 2026-01-15 00:00:00
                                                                          │ (naive, listo para bind)
                                                                          │
                                                                          │ list_tarifas_vigentes(…)
                                                                          │──────────────────▶
                                                                          │◀──────────────────
                                                                          │ 200 + items (siguiente página)
```

## 6. Migration Plan

**NO hay migración Alembic.** El helper opera exclusivamente sobre columnas existentes
(`vigente_desde`, `vigente_hasta`, `estado`). El `modelo_datos_er.mmd` queda intacto.

**NO hay DDL.** Cero CREATE/ALTER/DROP. Cero trigger. Cero índice nuevo (los existentes
soportan el predicado: el índice implícito por PK `uuid`, y el índice sobre
`vigente_desde` que el `close_and_insert` del factory ya mantiene vía el módulo `repo`).

**Rollback**: revert del único PR. El helper es un módulo nuevo (`repo/tarifas_vigencia.py`)
no usado fuera del handler dedicado. Al revertir el handler, el factory vuelve a atender el
GET de `tarifas-sucursal` con su comportamiento previo. Sin estado, sin side-effects, sin
tabla de control.

## 7. Testing Strategy

### Tests nuevos

| Test | Tipo | Cubre |
|---|---|---|
| `test_default_now_utc_returns_vigentes` | unit (mock session) | Default `now(UTC)` equivale al filtro vigente actual |
| `test_vigente_en_pasado_devuelve_ventana_cubridora` | unit (mock session) | Pasado con 4 parametrizaciones |
| `test_vigente_en_futuro_incluye_tarifas_programadas` | unit (mock session) | Futuro con `vigente_desde` futuro |
| `test_vigente_en_excluye_inactivos_aunque_vigente_hasta_sea_null` | unit (mock session) | Defensa en profundidad `estado='activo'` |
| `test_vigente_en_tz_offsets_normalizados_a_utc` | unit (mock session) | `+05:00`, `-03:00`, `Z`, naive |
| `test_vigente_en_none_explicito_es_equivalente_a_omitir` | unit | Default aplicado |
| `test_vigente_en_malformed_rechazado_por_pydantic` | unit | 422 sobre handler |
| `test_vigente_en_offset_invalido_rechazado` | unit | 422 sobre `+25:00` |
| `test_cursor_compat_sin_vigente_en` | unit | `_parse_cursor_timestamp` + `_order_key` reusados |
| `test_three_versions_db_backed` | integration (pg_engine) | Pasada, vigente, futura con `estado='activo'` + 1 inactiva |
| `test_handler_dedicated_devuelve_read_list_shape` | integration (TestClient + pg_engine) | Smoke HTTP del path completo |
| `test_coexistencia_factory_sigue_atendiendo_otros_recursos` | integration | `cantidad-vehiculos-sucursal` sigue retornando `vigente_hasta IS NULL` sin filtro `estado` |

### Tests existentes que se preservan

- `tests/unit/test_pagination_cursor.py` — el factory no se toca, sigue verde.
- `tests/unit/test_empresa_router.py` — los demás recursos `[V]` siguen atendidos por el factory.
- `tests/integration/test_router_factory_gap_be_02.py` (si existe) — el factory no se toca.

### Aislamiento

- Tests unit con `MockSession` o `AsyncMock` (sin DB).
- Tests integration con `pg_engine` real (`parkos-postgres:16-pgpartman`) y
  `testcontainers[postgres]` para CI.
- Sin SQLite (regla de la casa).

### Fixtures nuevas

- `seed_tarifa_pasada`, `seed_tarifa_vigente`, `seed_tarifa_futura`,
  `seed_tarifa_inactiva` en `backend/tests/conftest.py` — factories que crean filas en
  `prod.tarifas_sucursal` con `vigente_desde`/`vigente_hasta` parametrizables, sobre un
  `uuid_sucursal` único por test para evitar colisiones de UK01.

### Smoke HTTP

- `curl http://localhost:8000/empresa/tarifas-sucursal?vigente_en=2026-01-15T00:00:00Z` →
  200 con el conjunto esperado.
- Mismo sin `vigente_en` → mismo conjunto que antes, menos inactivas.

## 8. Threat Matrix

| # | Amenaza | Severidad | Mitigación |
|---|---|---|---|
| T1 | Cliente envía `vigente_en` con offset `+25:00` (typo) | Baja | Pydantic + `datetime.fromisoformat` rechaza con 422 antes de llegar al helper |
| T2 | Cliente envía `vigente_en` con año 1900 o 2200 (valores patológicos) | Baja | Sin validación de rango en HU-F1.4; el predicado funciona y devuelve conjunto vacío; documentado en OQ (fuera de scope) |
| T3 | Cliente envía `vigente_en` con tz `+05:00` pero la DB está en otra zona | Baja | DB column es `timestamp` sin tz; bind siempre en UTC; tests cubren tz variants |
| T4 | Concurrencia: dos requests simultáneos con `vigente_en=now()` ligeramente distinto | Baja | Cada request tiene su propio `datetime.now(UTC)`; el predicado es estable sobre la misma fila aunque cambien los bordes; tests de monotonicidad simple |
| T5 | `cursor` emitido antes del deploy con `vigente_en` activo en el siguiente request | Baja | `_parse_cursor_timestamp` no depende de `vigente_en`; el cursor sólo codifica `(vigente_desde, uuid)`; tests de cursor compat |

## 9. Rollback

**Revert del único PR.** El handler dedicado se desregistra al revertir, el factory vuelve a
atender el GET de `tarifas-sucursal` con su comportamiento previo (sólo `vigente_hasta IS NULL`).

**No hay esquema que revertir** (cero DDL).

**No hay estado a limpiar** (helper sin estado, sin tabla de control, sin trigger, sin
background job).

**Si se quisiera hacer un rollback quirúrgico sin esperar el revert del PR** (no
recomendado): eliminar el bloque del handler dedicado en `empresa.py` y el módulo
`repo/tarifas_vigencia.py`. El factory asume automáticamente.

## 10. Open Questions

(vacía — los dos conflictos relevantes, plan.md vs prompt y `estado='activo'` sí/no, están
documentados como RESUELTOS en `proposal.md` §12.)

## 11. Relevant Files

- `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py` — handler dedicado
  (líneas previas al bloque 142-149). Modificado.
- `backend/packages/parkos_core/src/parkos_core/api/router_factory.py` — patrón de cursor y
  orden; **no se modifica** (commit `f7cb37a` HU-F1.1 GAP-BE-02).
- `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py` — `TarifasSucursalFilter`
  (líneas 303-309 → 310). Modificado.
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (NUEVO) — helper
  puro `list_tarifas_vigentes`.
- `backend/tests/unit/test_tarifas_vigente_en.py` (NUEVO) — tests RED-then-GREEN.
- `backend/tests/integration/test_tarifas_vigente_en_db.py` (NUEVO) — DB-backed contra
  `pg_engine` real.
- `backend/tests/conftest.py` — fixtures nuevas (factories parametrizadas).
- `openspec/specs/operations/spec.md` — REQ-OPS-017..020 + Modified Capabilities.
- `modelo_datos_er.mmd` — tabla `tarifas_sucursal` (líneas 406-426), sin cambios.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:215-277` — precedente
  de punto-en-tiempo `resolve_active_subscription_for_exit(as_of=...)`. Sin cambios.