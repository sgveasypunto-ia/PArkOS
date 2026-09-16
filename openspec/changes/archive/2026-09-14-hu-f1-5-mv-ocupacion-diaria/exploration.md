# Exploration: HU-F1.5 — Vista materializada `mv_ocupacion_diaria` + `GET /operacion/ocupacion`

> **Change**: `hu-f1-5-mv-ocupacion-diaria`
> **Phase**: explore (sdd-explore)
> **HU**: HU-F1.5 — Materialized view `prod.mv_ocupacion_diaria` (refresh cada 10s) + custom endpoint `GET /api/v1/operacion/ocupacion?uuid_sucursal=X`
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `b5dd006`)
> **PR target**: `origin/dev`
> **Inputs read**:
> `plan.md` (HU-F1.5 lines 707–731, DEC-SUC-11 línea 426, Ocupación glosario línea 477, dependencia F1.6-T3 línea 792, polling 10s línea 1427, `cantidad_vehiculos_sucursal` SELECT vía vista línea 2619, `mv_ocupacion_diaria` línea 2646),
> `modelo_datos_er.mmd` (`ingreso` 577–596 [L-E], `cantidad_vehiculos_sucursal` 428–446 [V], `tipos_vehiculo` 87–104 [V], `salidas` 761–777 [A]),
> `openspec/specs/operations/spec.md` (formato REQ-OPS-001..029, F1.5 introducirá REQ-OPS-030+),
> `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/exploration.md` (precedente inmediato — formato a replicar),
> `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/exploration.md` (precedente PL/pgSQL + custom handler),
> `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (router custom, `_ingreso_issuer_dep` línea 64, `cotizar_ingreso_handler` línea 219 — patrón custom a replicar),
> `backend/packages/parkos_core/src/parkos_core/jobs/runner.py` (`BaseRunner`, `WorkerRunner` con SIGTERM/SIGINT, exit codes 0/1/2 §21.7),
> `backend/packages/parkos_core/src/parkos_core/jobs/sync_sucursal.py` (`SyncSucursalWorker` con `cycle()` async, `asyncio.sleep` entre ciclos — patrón a replicar),
> `backend/packages/parkos_core/migrations/versions/0022_create_calcular_cotizacion.py` (PL/pgSQL precedent),
> `backend/packages/parkos_core/migrations/versions/0023_unique_active_sesion_per_user.py` (último migration aplicado, **0024 es el próximo disponible**),
> `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` (precedente views plain — NO materialized),
> `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py` (columnas negocio),
> `backend/packages/parkos_core/src/parkos_core/models/V/cantidad_vehiculos_sucursal.py` (`cantidad` Integer, `VersionedBase` con bi-temporal),
> `backend/packages/parkos_core/src/parkos_core/models/V/tipos_vehiculo.py` (`tipo` String),
> `backend/packages/parkos_core/src/parkos_core/models/A/salidas.py` (sin columna `estado`, append-only),
> `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (`CotizarFacturacion`, `CotizarMensualidad`, `CotizarResponse`, `IngresoRead/Create/Filter/ReadList`),
> `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (`TenantContext.actor_uuid` + `sucursal_uuid`, `get_tenant_ctx` con `X-Sucursal-Context`),
> `backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py:143` (`r.include_router(operacion.router)` ya montado, no se toca),
> `backend/packages/parkos_core/src/parkos_core/repo/cotizacion.py` (patrón `CotizacionError` + helpers tipados),
> `backend/packages/parkos_core/src/parkos_core/api/deps.py` (centraliza `get_tenant_ctx` + `requires_issuer`).

## 1. Contexto de la HU

HU-F1.5 implementa la ocupación casi-en-vivo que el operador ve en el strip superior de la pantalla (consumido por F4.3 — `OcupacionStrip` con polling 10s). El cliente nunca calcula "cuántos cupos quedan" sobre la tabla `ingreso`: hace `GET /operacion/ocupacion?uuid_sucursal=X` cada 10s y muestra `Auto: 23/50`. Cierra el prerequisito backend de F6 (`POST /operacion/ingresos` valida cupo contra `mv_ocupacion_diaria` antes de insertar — F1.6-T3 línea 792) y de F4.3 (`OcupacionStrip` lee el mismo endpoint).

**Decisión arquitectónica clave DEC-SUC-11** (plan.md línea 426): la disponibilidad **nunca** se mantiene por trigger sobre una columna mutable `disponible` en `cantidad_vehiculos_sucursal`. La tabla solo guarda el cupo máximo configurado (`cantidad` int); el cálculo siempre compara `cupo_maximo` vs ingresos activos vía la vista materializada. Esto descarta explícitamente el patrón "trigger que decrementa `disponible`" — añadir esa columna violaría la inmutabilidad del ER y el contrato `[V]` bi-temporal. Por la misma razón, el transporte es **polling 10s** desde el cliente (no websocket, no SSE): la vista materializada se refresca server-side cada 10s y el cliente sondea; el lag máximo aceptable de 10s está dentro del SLA operativo y evita mantener conexiones long-lived en `api-sucursal`. F1.5 entrega: (1) la vista `prod.mv_ocupacion_diaria` definida en una migración, (2) un job/scheduler que la refresca cada 10s con `REFRESH MATERIALIZED VIEW CONCURRENTLY`, (3) el endpoint `GET /api/v1/operacion/ocupacion` que hace JOIN de la vista con `cantidad_vehiculos_sucursal` para exponer `cupo_maximo` y `disponible`.

Tamaño estimado: **160 LOC** (plan.md línea 723) — ~80 LOC migración + view definition + UNIQUE INDEX + 30 LOC scheduler/job + 30 LOC endpoint + 20 LOC schemas + tests.

## 2. Migraciones existentes

Listado `backend/packages/parkos_core/migrations/versions/` (verificado vía Glob, 23 archivos):

```
0001_initial_schema.py
0002_seed_permisos_canonicos.py
0003_add_idempotency_keys_and_revoked_sync_jwts.py
0004_add_factura_pagos_reverso_trigger.py
0006_add_pairing_tokens_and_normalized_revoked_sync_jwts.py
0007_add_v_resolucion_consecutivo_view.py
0008_add_identity_nk_indexes.py
0009_add_derived_read_views.py
0010_drop_le_vigente_inicial_triggers.py
0011_add_seq_lookup_indexes.py
0012_add_sync_queue_lw_buffer.py
0013_add_alert_types.py
0014_add_catalog_triggers.py
0015_drop_infra_triggers.py
0016_add_sync_apply_guard.py
0017_fix_hash_chain_prior_row_ordering.py
0018_add_default_partitions_pairing_revoked_jwts.py
0019_deterministic_permisos_uuids.py
0020_deterministic_tipo_persona_empresa_uuids.py
0021_least_privilege_and_immutability_contract.py
0022_create_calcular_cotizacion.py    ← HU-F1.8 (PL/pgSQL precedent)
0023_unique_active_sesion_per_user.py ← HU-F1.3 (última migración aplicada)
```

**Próximo número disponible: `0024`.** El plan.md línea 726 menciona `migrations/versions/2026_09_11_0023_add_mv_ocupacion_diaria.py` pero `0023` ya está consumido por F1.3 (`0023_unique_active_sesion_per_user.py`, commit `ca3f9bf`). El apply de F1.5 usará **`0024_add_mv_ocupacion_diaria.py`** (el prefijo de fecha `2026_09_11` del plan es decorativo — los archivos reales usan `revision = "0024_..."` consistente con el patrón de F1.3).

**Precedentes relevantes para esta migración**:
- `0022_create_calcular_cotizacion.py` — PL/pgSQL con `VOLATILE` para permitir `SELECT … FOR SHARE` (apply-time correction vs `STABLE` original del design). F1.5 NO necesita PL/pgSQL — la vista materializada es DDL puro, sin lógica procedural.
- `0023_unique_active_sesion_per_user.py` — `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` con pre-flight `DO $$ … RAISE EXCEPTION`. F1.5 replicará el patrón `CONCURRENTLY` para el UNIQUE INDEX obligatorio sobre la vista (CRÍTICO para `REFRESH CONCURRENTLY` — ver §7).
- `0009_add_derived_read_views.py` — precedent de views plain (`v_clientes_actual`, `v_vehiculos_actual`, `v_factura_electronica_acuse`). F1.5 introduce la PRIMERA **materialized view** del schema — no hay precedente directo (grep `CREATE MATERIALIZED VIEW` en `migrations/` retorna 0 matches).

**Downgrade** requerido: `DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria` + `DROP INDEX IF EXISTS prod.uq_mv_ocupacion_diaria_*` (verificar nombre exacto en design).

## 3. Modelo `ingreso` + `cantidad_vehiculos_sucursal` + `tipos_vehiculo` + `salidas`

| Tabla | Modelo | Columnas relevantes para F1.5 |
|---|---|---|
| `prod.ingreso` `[L-E]` | `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py` | `uuid` (PK), `uuid_sucursal` (FK nullable), `uuid_tipo_vehiculo` (FK nullable), `placa`, `uuid_subscripcion_cliente`, `fecha_ingreso`, `observaciones`. Insert-only (`LifecycleEventBase`); **NO** hay columna `uuid_salida` ni `estado` — el estado se deriva por LEFT JOIN con `salidas` + `anulaciones`. |
| `prod.salidas` `[A]` | `backend/packages/parkos_core/src/parkos_core/models/A/salidas.py` | `uuid` (composite PK con `fecha_retencion_hasta`), `uuid_sucursal`, `uuid_ingreso` (FK), `fecha_salida`. **NO** tiene columna `estado` (ER línea 765) — la decisión "salida activa vs anulada" la da `anulaciones.tipo_anulable='salida'` + `estado='ejecutada'` (ver `operacion.py:147-168`). Append-only (`AppendOnlyBase` con REVOKE `UPDATE, DELETE`). |
| `prod.anulaciones` `[L-W]` | `models/L_W/anulaciones.py` | `uuid_ingreso` (FK siempre presente), `uuid_salida` (nullable), `estado='ejecutada'`, `tipo_anulable='ingreso'\|'salida'`. Para F1.5: un ingreso con `anulaciones.estado='ejecutada'` Y `tipo_anulable='ingreso'` cuenta como **NO activo** (anulado ⇒ cupo devuelto). |
| `prod.cantidad_vehiculos_sucursal` `[V]` | `models/V/cantidad_vehiculos_sucursal.py` | `uuid`, `uuid_sucursal`, `uuid_tipo_vehiculo`, `cantidad` (int, cupo máximo). **UK01** `(uuid_sucursal, uuid_tipo_vehiculo, vigente_desde)` (línea 39-44 del modelo). Bi-temporal (`VersionedBase`) — la versión vigente es la fila con `estado='activo' AND vigente_hasta IS NULL`. |
| `prod.tipos_vehiculo` `[V]` | `models/V/tipos_vehiculo.py` | `uuid`, `tipo` (string: `Auto`/`Moto`/etc.). UK01 `(tipo, vigente_desde)`. |

**Definición operacional de "ingreso activo"** para `mv_ocupacion_diaria`:
- Existe fila en `prod.ingreso` con `uuid_sucursal = X` AND `uuid_tipo_vehiculo IS NOT NULL`.
- NO existe fila en `prod.salidas` con `uuid_ingreso = ingreso.uuid AND uuid_sucursal = X` (sin salida).
- NO existe fila en `prod.anulaciones` con `uuid_ingreso = ingreso.uuid AND estado='ejecutada' AND tipo_anulable IN ('ingreso','salida')` (no anulada).

**Nota activa vs cerrada** (consistente con `operacion.py:152-168`): actualmente el endpoint `GET /ingresos/{uuid}/estado` ya deriva `abierto | cerrado | anulada` con `LEFT JOIN` ad-hoc en el handler. La vista materializada encapsula la misma lógica para todas las filas a la vez — base del polling 10s.

## 4. Router `operacion.py`

Path: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (388 LOC).

```
router = APIRouter(prefix="/operacion", tags=["operacion"])    # línea 62
_ingreso_issuer_dep = requires_issuer("operador-", "admin-")  # línea 64
```

Endpoints existentes (F1.8 cerró el último):
- `POST /operacion/ingresos` → `create_ingreso` (línea 83) — escritura insert-only
- `GET /operacion/ingresos/{uuid}` → `get_ingreso` (línea 114)
- `GET /operacion/ingresos/{uuid}/estado` → `get_ingreso_estado` (línea 131) — derived state
- `GET /operacion/ingresos` → `list_ingresos` (línea 178) — filtros `uuid_sucursal`, `placa`, `limit`
- `GET /operacion/cotizar` → `cotizar_ingreso_handler` (línea 219) — HU-F1.8

**Patrón para `GET /operacion/ocupacion`**:
- Custom handler `@router.get("/ocupacion", ...)` registrado en `operacion.py`. NO requiere `make_router` (el router es custom, no factory-based).
- Query param `uuid_sucursal: UUID | None = Query(None)`. Si `None`, fallback a `ctx.sucursal_uuid` (operador- siempre tiene una sucursal pinneada; admin- debe enviar header `X-Sucursal-Context` y replicarlo en query para legibilidad).
- Lógica: `SELECT mv.uuid_sucursal, mv.uuid_tipo_vehiculo, tv.tipo, COALESCE(cvs.cantidad, 0) AS cupo_maximo, mv.activos, (COALESCE(cvs.cantidad, 0) - mv.activos) AS disponible FROM prod.mv_ocupacion_diaria mv JOIN prod.tipos_vehiculo tv ON tv.uuid = mv.uuid_tipo_vehiculo AND tv.vigente_hasta IS NULL LEFT JOIN prod.cantidad_vehiculos_sucursal cvs ON cvs.uuid_sucursal = mv.uuid_sucursal AND cvs.uuid_tipo_vehiculo = mv.uuid_tipo_vehiculo AND cvs.vigente_hasta IS NULL WHERE mv.uuid_sucursal = :uuid_sucursal ORDER BY tv.tipo`.
- **Path conflict check**: `/ocupacion` no colisiona con `/ingresos/{uuid}/estado` ni con `/ingresos` ni con `/cotizar`. FastAPI matchea por especificidad de path — no requiere orden de registro especial.

`api/v1/__init__.py:143` ya monta `operacion.router` — F1.5 NO toca el `__init__.py`.

## 5. Auth pattern

`TenantContext` (`backend/packages/parkos_core/src/parkos_core/auth/tenancy.py:28-36`):
- `actor_uuid: UUID` — extraído del JWT claim `sub`.
- `actor_rol: str` — `admin` | `operador` | `sync-agent`.
- `issuer_prefix: str` — `operador-` | `admin-` | `sync-agent-`.
- `sucursal_uuid: UUID | None` — `operador-` lo trae del JWT claim `sucursal`; `admin-` del header `X-Sucursal-Context` validado contra `claims["sucursales_permitidas"]`.

Para `GET /operacion/ocupacion`:
- Aplicar `_ingreso_issuer_dep = requires_issuer("operador-", "admin-")` (mismo que resto de `operacion.py`).
- **Autorización por sucursal** (KD-3 abierto):
  - `operador-`: solo puede consultar `ctx.sucursal_uuid`. Si pasa `?uuid_sucursal=X` con `X != ctx.sucursal_uuid`, devolver `403 tenant_scope_violation` (mismo error tipado que `auth/tenancy.py:38-65` ya define).
  - `admin-`: puede consultar cualquier sucursal presente en `claims["sucursales_permitidas"]`. Validar igual que `auth/tenancy.py:115-131`.
- **Default sucursal**: si el query param `uuid_sucursal` está ausente, usar `ctx.sucursal_uuid` y devolver 400 si es None (admin- sin header).

## 6. Scheduler / Job pattern

Directorio `backend/packages/parkos_core/src/parkos_core/jobs/` (verificado vía Glob):
- `__init__.py`
- `runner.py` — `BaseRunner` (ABC, `cycle()` abstracto) + `WorkerRunner` (signal handlers Unix/Windows, exit codes 0/1/2, `await asyncio.sleep(1)` en error de ciclo, línea 90)
- `sync_cloud.py`
- `sync_sucursal.py` — `SyncSucursalWorker(WorkerRunner)` con ciclo 6-step (`poll→push→handle→pull→heartbeat→sleep`, `asyncio.sleep(self.poll_interval_s)` línea 266). `DEFAULT_POLL_INTERVAL_S = 10` (línea 103) — **mismo intervalo que F1.5 necesita**.

**No hay scheduler dedicado para refresco de vistas materializadas todavía.** F1.5 introduce el primer worker de "branch-local-only" refresh (sin sync cloud). Dos topologías posibles:

| Opción | Ubicación | Pros | Contras |
|---|---|---|---|
| **A. Worker separado** `python -m parkos_core.jobs.refresh_mv_ocupacion` | NSSM service adicional junto a `job_sync_sucursal` | Separación de concerns; ciclo de vida independiente; reinicio no afecta sync | Servicio adicional que mantener; segundo `PARKOS_*` env block |
| **B. asyncio task in-process en `api-sucursal` lifespan** | `main.py` `lifespan` arranca `asyncio.create_task(refresh_loop())` | Cero ops extra; comparte env; NSSM solo maneja api-sucursal | Acopla api-sucursal a MV refresh; un crash de api-sucursal pausa el refresh |

**Recomendación preliminar**: opción **A** (worker separado) — sigue el patrón existente `sync_sucursal.py` y `sync_cloud.py` (cada worker en su proceso), respeta la separación de concerns que el repo ya tiene. El costo operacional (un NSSM más) es bajo y el script CLI `python -m parkos_core.jobs.refresh_mv_ocupacion` es trivialmente testeable.

El worker tendrá:
```python
class RefreshMvOcupacionWorker(WorkerRunner):
    def __init__(self, *, session: AsyncSession, refresh_interval_s: int = 10) -> None:
        super().__init__(name="refresh_mv_ocupacion")
        self._session = session
        self.refresh_interval_s = max(5, int(refresh_interval_s))

    async def cycle(self) -> None:
        # REFRESH MATERIALIZED VIEW CONCURRENTLY requiere UNIQUE INDEX
        # (ver §7). Si falla por falta de índice, log estructurado y
        # fallback a REFRESH plain (sin CONCURRENTLY, toma lock breve).
        try:
            await self._session.execute(
                text("REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria")
            )
            await self._session.commit()
        except Exception as exc:
            self.log.warning("refresh_mv_concurrently_failed_fallback", error=str(exc))
            await self._session.rollback()
            await self._session.execute(
                text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")
            )
            await self._session.commit()
        await asyncio.sleep(self.refresh_interval_s)
```

## 7. View definition pattern

**No existe ningún `CREATE MATERIALIZED VIEW` en las migraciones del repo** (grep `MATERIALIZED` en `migrations/` retorna 0 matches). F1.5 introduce el primero. Las vistas existentes son plain (`CREATE OR REPLACE VIEW`, ver `0009_add_derived_read_views.py:62-95`).

**Decisión técnica crítica**: `REFRESH MATERIALIZED VIEW CONCURRENTLY` requiere UNIQUE INDEX sobre la vista. Sin él, hay que usar `REFRESH MATERIALIZED VIEW` (sin `CONCURRENTLY`), que toma `AccessExclusiveLock` y bloquea lecturas concurrentes — incompatible con el polling 10s de N operadores.

Diseño de la vista (preliminar, a refinar en design):

```sql
CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS
SELECT
    i.uuid_sucursal,
    i.uuid_tipo_vehiculo,
    count(*) AS activos
FROM prod.ingreso i
WHERE
    i.uuid_tipo_vehiculo IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM prod.salidas s
        WHERE s.uuid_ingreso = i.uuid AND s.uuid_sucursal = i.uuid_sucursal
    )
    AND NOT EXISTS (
        SELECT 1 FROM prod.anulaciones a
        WHERE a.uuid_ingreso = i.uuid
          AND a.estado = 'ejecutada'
          AND a.tipo_anulable IN ('ingreso', 'salida')
    )
GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo;

-- UNIQUE INDEX OBLIGATORIO para REFRESH CONCURRENTLY
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    prod.uq_mv_ocupacion_diaria_sucursal_tipo
    ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);
```

**Análisis de unicidad**: la combinación `(uuid_sucursal, uuid_tipo_vehiculo)` ES estrictamente única por construcción — el `GROUP BY` colapsa N filas en una por combinación. No se requiere columna sintética (`row_number() OVER (...)`) — la unicidad es natural.

**Pre-flight check** (migración, análogo a F1.3): si la tabla `prod.ingreso` tiene > 10M filas o `prod.anulaciones` tiene > 1M filas, el primer refresh puede tardar minutos; emitir `RAISE NOTICE` con el conteo y el ETA estimado. Si hay > 50M filas en alguna, abortar con error explícito pidiendo aplicar el índice `(uuid_sucursal, uuid_tipo_vehiculo)` en `ingreso` antes (no es parte de F1.5 — precondición fuera de scope).

**Downgrade**: `DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria` — el `DROP MATERIALIZED VIEW` borra también sus índices.

## 8. Schema

`backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` ya tiene `CotizarFacturacion`, `CotizarMensualidad`, `CotizarResponse`, `IngresoRead/Create/Filter/ReadList`. Agregar (preliminar):

```python
class OcupacionItem(_Base):
    """Una fila del breakdown de ocupación por tipo de vehículo."""
    uuid_tipo_vehiculo: uuid_lib.UUID
    tipo: str                                  # "Auto", "Moto", etc.
    cupo_maximo: int                           # 0 si no hay fila en cvs
    activos: int # desde la vista
    disponible: int                            # cupo_maximo - activos (puede ser negativo si sobrecupo)


class OcupacionResponse(_Base):
    """Respuesta de ``GET /operacion/ocupacion?uuid_sucursal=X``."""
    uuid_sucursal: uuid_lib.UUID
    items: list[OcupacionItem]
    generado_en: datetime                      # NOW() del servidor, para diagnóstico de lag
```

`extra='forbid'` (heredado de `_Base`) rechaza campos no documentados. `disponible` puede ser negativo si `cantidad_vehiculos_sucursal` está mal configurada — el cliente debe interpretar `< 0` como "configuración faltante, contacte al admin" (no como error 500).

## 9. Test patterns

Replicar el patrón F1.8 / F1.3 (4 archivos):

- **`tests/unit/test_operacion_ocupacion.py`** — 4 HTTP-level tests vía `httpx.AsyncClient + ASGITransport + JWT operador fixture`:
  - T1: operador de sucursal X consulta `?uuid_sucursal=X` → `200` con `OcupacionResponse` conteniendo N items.
  - T2: operador de sucursal X consulta `?uuid_sucursal=Y` (otra) → `403 tenant_scope_violation`.
  - T3: admin- con header `X-Sucursal-Context: Y` consulta `?uuid_sucursal=Y` → `200`.
  - T4: operador sin sesión activa (no afecta a este endpoint — el endpoint no requiere caja abierta) → `200` con `OcupacionResponse`. Sin 401.

- **`tests/integration/test_mv_ocupacion_diaria_db.py`** — 2 DB tests con `PARKOS_DOCKER_TEST=1`:
  - T1: insertar un ingreso `(uuid_sucursal=X, uuid_tipo_vehiculo=T)` → ejecutar `REFRESH MATERIALIZED VIEW` → la vista contiene `activos=1` para `(X, T)`.
  - T2: insertar ingreso + insertar `salidas` con `uuid_ingreso=I` → refresh → la vista decrementa `activos`. Verifica que la vista se mantiene sincronizada con la lógica de `estado` derivado de `operacion.py:152-168`.

- **`tests/integration/test_migration_0024_mv.py`** — pre-flight de la migración:
  - Aplicar la migración 0024 sobre un schema con datos sucios (5 ingresos, 2 con salida, 1 anulada) → verificar que la vista se crea, se puebla correctamente, y el UNIQUE INDEX se aplica sin colisiones.

- **`tests/static/test_no_write_in_ocupacion.py`** — AST walk sobre el handler `get_ocupacion` rechazando `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` (defense in depth, mismo patrón que F1.8). El endpoint es read-only por contrato.

- **`tests/integration/test_refresh_mv_job.py`** — 2 tests:
  - T1: el worker `RefreshMvOcupacionWorker` ejecuta un `cycle()` y la vista se refresca (verificar timestamp de la última fila `pg_stat_user_tables.last_analyze` o equivalente).
  - T2: si Postgres devuelve error en `REFRESH CONCURRENTLY`, el worker cae a `REFRESH` plain sin crashear el ciclo (KD-5 mitigation).

## 10. KD preliminares (a refinar en propose/design)

- **KD-1 — Ubicación del refresh job**: opción A (worker separado `parkos_core.jobs.refresh_mv_ocupacion`) vs opción B (asyncio task in-process en `api-sucursal`). Tradeoff: separación de concerns vs ops extra. **Recomendación preliminar**: A — sigue el patrón de `sync_sucursal.py` y `sync_cloud.py` (cada worker en su proceso), testeable con `pytest`, CLI entrypoint trivial. Documentar en design la decisión.

- **KD-2 — UNIQUE INDEX sobre la vista materializada**: la combinación `(uuid_sucursal, uuid_tipo_vehiculo)` es naturalmente única por el `GROUP BY` — sin columna sintética. **Recomendación preliminar**: `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);`. Sin este índice, `REFRESH CONCURRENTLY` falla con error claro.

- **KD-3 — Autorización por sucursal** (KD-BE-OP-02 tentativo):
  - `operador-`: solo `ctx.sucursal_uuid`. Cross-tenant → `403 tenant_scope_violation` (error tipado ya definido en `auth/tenancy.py:60-65`).
  - `admin-`: cualquier sucursal en `claims["sucursales_permitidas"]`. Sin header → `400 missing_sucursal_context`.
  - **Recomendación preliminar**: query param `uuid_sucursal` opcional; default = `ctx.sucursal_uuid`. Validar contra permisos del issuer. Mismo patrón que `auth/tenancy.py:115-131`.

- **KD-4 — Response shape**: ¿agregado por sucursal `{cupo_total, activos_total, disponible_total}` o breakdown por tipo `[{uuid_tipo_vehiculo, tipo, cupo_maximo, activos, disponible}, ...]`? El plan línea 713 explícitamente pide el breakdown: `[{uuid_tipo_vehiculo, tipo, cupo_maximo, activos, disponible}]`. **Recomendación preliminar**: breakdown por tipo (alineado al plan y al consumidor F4.3 `OcupacionStrip` que renderiza "Auto: 23/50" por tipo).

- **KD-5 — Circuit breaker / fallback del refresh**: si Postgres está bajo carga y `REFRESH CONCURRENTLY` tarda > 5s, ¿bloqueamos el siguiente ciclo? **Recomendación preliminar**: NO bloqueamos — aceptamos que un ciclo se "salte" (skip) si el anterior no terminó; el `asyncio.sleep(refresh_interval_s)` se aplica DESPUÉS del refresh (no antes), así un ciclo lento solo atrasa el siguiente. Si el refresh falla por completo, log `refresh_mv_failed` y continuar; el endpoint sirve datos con hasta `2 * refresh_interval_s` de lag. **Aceptable para v1** (RIESGO-SUC-02 del plan línea 2677 documenta el lag máximo).

- **KD-6 — Política ante cupo no configurado**: si no existe fila en `cantidad_vehiculos_sucursal` para `(uuid_sucursal, uuid_tipo_vehiculo)`, la vista puede tener `activos > 0` pero `cupo_maximo = 0` → `disponible = -activos`. **Recomendación preliminar**: `LEFT JOIN` con `COALESCE(cantidad, 0)`; el cliente interpreta `disponible < 0` como "configuración faltante" y muestra "N/A" en el strip. NO devolver 404 — el endpoint siempre devuelve 200 con la breakdown actual, dejando al cliente la decisión de UX.

## 11. Dependencias y bloqueadores

- **Sin dependencia de F1.3** cerrado (F1.3 constraint sesión única es ortogonal — no toca `ingreso` ni `cantidad_vehiculos_sucursal`).
- **Sin dependencia de F1.8** cerrado (F1.8 PL/pgSQL `calcular_cotizacion` es independiente; F1.5 solo lee `ingreso`/`salidas`/`anulaciones`).
- **Sin bloqueo KD-IVA** (F1.5 no toca `impuestos`).
- **Foundation para F1.6** (línea 792): `POST /operacion/ingresos` valida cupo vía `mv_ocupacion_diaria` con `SELECT mv.activos, cvs.cantidad FROM mv_ocupacion_diaria mv LEFT JOIN cantidad_vehiculos_sucursal cvs ...`. F1.6 depende contractualmente de que `mv_ocupacion_diaria` exista y se refresque.
- **Consumido por F4.3** (línea 1422–1442): `OcupacionStrip` con `refreshInterval: 10_000` y `AbortController` explícito en `unmount`. Polling client-side, no websocket.
- **Sin nueva dependencia pip** — `psycopg2`/`asyncpg`/`sqlalchemy[asyncio]` ya presentes.
- **Riesgo vivo RIESGO-SUC-02** (plan línea 2677): "La vista materializada de ocupación (polling 10 s) puede mostrar cupo desactualizado en momentos de alta rotación simultánea". Aceptado por el corpus; mitigación = reducir intervalo en sedes con alta rotación (configuración fuera de scope de F1.5).

## 12. Riesgos

- **R1 (Alto)**: si el refresh job se cae (proceso NSSM `refresh_mv_ocupacion` reinicia), la vista queda stale indefinidamente hasta que el próximo ciclo ejecute. Mitigación: en el `startup` del worker, ejecutar `REFRESH MATERIALIZED VIEW mv_ocupacion_diaria` una vez antes de empezar el `asyncio.sleep` loop (mismo patrón que `sync_sucursal.py:82` `worker_started`). Documentar KD-1 en design.

- **R2 (Medio)**: si hay ingresos concurrentes durante el `REFRESH CONCURRENTLY`, no se pierden — la vista usa MVCC snapshot consistente. Pero la latencia del refresh puede acumularse bajo carga (10s + tiempo de refresh). Aceptable para v1 (KD-5).

- **R3 (Medio)**: el plan menciona `cupo_maximo` desde `cantidad_vehiculos_sucursal.cantidad` — verificar que esa fila existe para cada combinación `(uuid_sucursal, uuid_tipo_vehiculo)`. Si falta, `disponible` puede ser negativo (KD-6). Mitigación: `LEFT JOIN` con `COALESCE(cantidad, 0)` y aceptar `disponible < 0` como estado válido (no es bug, es señal de mala configuración — el operador debe contactar al admin).

- **R4 (Alto)**: `REFRESH MATERIALIZED VIEW CONCURRENTLY` requiere UNIQUE INDEX — si la combinación `(uuid_sucursal, uuid_tipo_vehiculo)` NO fuera estrictamente única por diseño (ej: si en el futuro se particiona la vista por fecha), habría que agregar columna sintética. Hoy es seguro, pero documentar la dependencia en design.

- **R5 (Bajo)**: si la tabla `ingreso` tiene > 10M filas, el primer refresh puede tardar minutos (la vista materializada se inicializa lazy en el `CREATE MATERIALIZED VIEW`). Pre-flight con conteo + `RAISE NOTICE` informativo (sin abortar) — si > 50M, abortar pidiendo precondición.

- **R6 (Bajo)**: el `astwalk` `test_no_write_in_ocupacion.py` puede romperse si un dev futuro agrega `session.execute(text("SELECT … FOR UPDATE"))` (lectura con lock). Aceptable como false positive — el test documenta explícitamente "read-only, sin locks".

- **R7 (Bajo)**: `REFRESH MATERIALIZED VIEW` (sin `CONCURRENTLY`) toma `AccessExclusiveLock` y bloquea lecturas. Si el UNIQUE INDEX llegara a faltar por una migración manual, el worker cae a `REFRESH` plain (KD-5 fallback) — durante ese refresh (típicamente < 100ms), el endpoint `GET /ocupacion` puede devolver 503 o timeout. Mitigación: alerta operativa si el tiempo de refresh supera `refresh_interval_s`.

## 13. Artifacts a crear

```
openspec/changes/hu-f1-5-mv-ocupacion-diaria/exploration.md       ← este archivo
openspec/changes/hu-f1-5-mv-ocupacion-diaria/proposal.md           (sdd-propose)
openspec/changes/hu-f1-5-mv-ocupacion-diaria/specs/operational/spec.md (sdd-spec, introduce REQ-OPS-030+)
openspec/changes/hu-f1-5-mv-ocupacion-diaria/design.md             (sdd-design)
openspec/changes/hu-f1-5-mv-ocupacion-diaria/tasks.md               (sdd-tasks)
openspec/changes/hu-f1-5-mv-ocupacion-diaria/verify-report.md      (sdd-verify)
openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/archive-report.md (sdd-archive)
```

Archivos del backend (a crear o modificar en apply):

| Archivo | Acción | Notas |
|---|---|---|
| `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` | crear | `CREATE MATERIALIZED VIEW` + UNIQUE INDEX CONCURRENTLY + downgrade. **Pre-flight**: conteo de filas en `ingreso` con `RAISE NOTICE` si > 10M. |
| `backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py` | crear | `RefreshMvOcupacionWorker(WorkerRunner)` con `cycle()` que llama `REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria` + `await self._session.commit()` + `asyncio.sleep(refresh_interval_s)`. CLI entrypoint `main()` con `python -m parkos_core.jobs.refresh_mv_ocupacion` + exit codes 0/1/2. |
| `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` | modificar | Agregar `OcupacionResponse` (en schemas) + handler `get_ocupacion` antes/después del `cotizar_ingreso_handler` (orden irrelevante — paths no colisionan). Aplicar `_ingreso_issuer_dep`. |
| `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` | modificar | Agregar `OcupacionItem`, `OcupacionResponse` al final del archivo (post-F1.8). |
| `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` | crear | Helper puro `get_ocupacion(session, *, uuid_sucursal) -> list[OcupacionItemRow]` con la query SQL. Encapsula el JOIN con `cantidad_vehiculos_sucursal` y `tipos_vehiculo`. |
| `backend/tests/unit/test_operacion_ocupacion.py` | crear | 4 HTTP tests con `httpx.AsyncClient + ASGITransport`. |
| `backend/tests/integration/test_mv_ocupacion_diaria_db.py` | crear | 2 DB tests (insert ingreso, refresh; insert salida, refresh). |
| `backend/tests/integration/test_migration_0024_mv.py` | crear | Pre-flight de migración con datos sucios. |
| `backend/tests/static/test_no_write_in_ocupacion.py` | crear | AST walk read-only. |
| `backend/tests/integration/test_refresh_mv_job.py` | crear | 2 tests del worker (cycle normal + fallback a REFRESH plain). |
| `openspec/specs/operations/spec.md` | modificar | Agregar REQ-OPS-030..033 (HU-F1.5) + Modified Capabilities. |

**Archivos NO tocados (deliberado)**: `api/v1/__init__.py` (router ya montado), `models/L_E/ingreso.py`, `models/V/cantidad_vehiculos_sucursal.py`, `models/V/tipos_vehiculo.py`, `models/A/salidas.py`, `repo/cotizacion.py`, `auth/tenancy.py`, `jobs/runner.py` (la base `WorkerRunner` se reusa sin cambios), `jobs/sync_sucursal.py`, `api/deps.py`.

## 14. Open questions para resolver en propose/design

1. **KD-1 ubicación del refresh job**: ¿worker NSSM separado (recomendación) o asyncio task in-process en `api-sucursal`? Argumentos: separación de concerns vs ops extra. Decisión owner.
2. **KD-3 alcance de autorización para `admin-`**: ¿cualquier sucursal global (cross-branch view) o solo las de `claims["sucursales_permitidas"]`? La segunda es coherente con `auth/tenancy.py:122` y mantiene el boundary de visibilidad cross-branch (admin_views cloud-only). Recomendación: segunda.
3. **KD-5 circuit breaker**: ¿agregar circuit breaker que pause el refresh tras N fallos consecutivos, o aceptar lag de hasta `2 * refresh_interval_s` como dice el corpus? Recomendación: aceptar lag; el corpus ya lo documenta como riesgo vivo (RIESGO-SUC-02).
4. **KD-6 UX ante cupo no configurado**: ¿devolver `disponible: -activos` (cliente renderiza "N/A") o devolver 503 con `error: 'cupo_no_configurado'`? Recomendación: la primera — el endpoint es read-only y refleja el estado real; cliente decide UX.
5. **¿Sembrar la vista en el seed inicial (`infra/scripts/seed_catalogs.py`) o esperar al primer ciclo del worker**? Recomendación: NO sembrar — la vista se inicializa en el `CREATE MATERIALIZED VIEW` (DCL implícito); el primer refresh del worker la puebla. Documentar el orden startup: migrate → worker arranca → primer refresh (puede tardar segundos en producción).

---

**Explored by**: sdd-explore (sub-agent executor).
**Engram**: persisted post-write (topic_key `sdd/hu-f1-5-mv-ocupacion-diaria/explore`, project `easypuinto-parkos-software`).
