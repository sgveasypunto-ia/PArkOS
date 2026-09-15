# Proposal: HU-F1.5 — Vista materializada `mv_ocupacion_diaria` + `GET /operacion/ocupacion`

> **Change**: `hu-f1-5-mv-ocupacion-diaria`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.5 (Fase-1 prerequisites — backend)
> **Inputs**: `openspec/changes/hu-f1-5-mv-ocupacion-diaria/exploration.md`
> (this change, 14 secciones), `plan.md` (HU-F1.5 lines 707–731, DEC-SUC-11 línea 426,
> polling 10s línea 1427, dependencia F1.6-T3 línea 792, RIESGO-SUC-02 línea 2677),
> `modelo_datos_er.mmd` (`ingreso` 577–596 [L-E], `cantidad_vehiculos_sucursal` 428–446
> [V], `tipos_vehiculo` 87–104 [V], `salidas` 761–777 [A], `anulaciones` [L-W]),
> `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/` (precedente inmediato:
> `CREATE UNIQUE INDEX CONCURRENTLY` + pre-flight + custom handler antes de factory +
> AST walk, commit `ca3f9bf`),
> `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/` (precedente PL/pgSQL +
> `WorkerRunner` y `SyncSucursalWorker` ciclo async — patron de job a replicar, commit
> `de4d2fc`), `backend/packages/parkos_core/migrations/versions/0023_unique_active_sesion_per_user.py`
> (última migración aplicada — **0024 es el próximo slot disponible**),
> `backend/packages/parkos_core/src/parkos_core/jobs/sync_sucursal.py` (precedente
> `WorkerRunner` con `asyncio.sleep(self.poll_interval_s)` post-cycle),
> `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (router custom,
> `_ingreso_issuer_dep` línea 64, `cotizar_ingreso_handler` línea 219 — patron a
> replicar).

## 1. Why

La pantalla del operador muestra en su strip superior "Auto: 23/50" — cuántos cupos
quedan por tipo de vehículo. Hoy esa cuenta no existe en backend: el cliente tendría que
replicar la fórmula de "ingresos activos vs cupo configurado" sobre `prod.ingreso` +
`prod.salidas` + `prod.anulaciones`, manteniendo sincronía manual con cada INSERT/UPDATE
del catálogo. Además, **`plan.md` línea 426 (DEC-SUC-11)** veta explícitamente mantener
una columna mutable `disponible` en `cantidad_vehiculos_sucursal` vía trigger: la tabla
solo guarda el cupo máximo configurado (`cantidad` int), y el cálculo siempre compara
`cupo_maximo` contra ingresos activos vía vista materializada. Esto descarta el patrón
"trigger que decrementa `disponible`" — añadir esa columna violaría la inmutabilidad del
ER y el contrato `[V]` bi-temporal (versionado por `vigente_desde/hasta`, no por mutación
in-place).

F1.5 cierra **dos dependencias contractuales** declaradas en el plan:

- **F1.6-T3 (línea 792)**: `POST /operacion/ingresos` valida cupo antes de insertar
  consultando `mv_ocupacion_diaria` con JOIN sobre `cantidad_vehiculos_sucursal`. Sin
  F1.5, F1.6 no puede implementar la regla "rechazar ingreso si no hay cupo".
- **F4.3** (`OcupacionStrip` cliente, polling 10s): consume `GET /operacion/ocupacion`
  cada 10s. Sin F1.5, el strip no puede renderizar contra datos del backend.

La elección de **vista materializada refrescada server-side cada 10s + polling cliente**
(no websocket, no SSE) está alineada con RIESGO-SUC-02 (plan línea 2677): el lag máximo
aceptable de 10s está dentro del SLA operativo y evita mantener conexiones long-lived en
`api-sucursal`. La vista encapsula la lógica de "ingreso activo" (sin salida, sin
anulación) que hoy `operacion.py:152-168` deriva ad-hoc para una fila — F1.5 la
materializa para todas las filas a la vez, base del polling.

Tamaño estimado: **160 LOC** (plan línea 723) — ~80 LOC migración + view definition +
UNIQUE INDEX + 30 LOC scheduler/job + 30 LOC endpoint + 20 LOC schemas + tests.

## 2. Decision Summary

| # | Decisión | Rationale |
|---|---|---|
| **D-HU-F1.5-1 (KD-1)** | Refresh vía worker NSSM separado `python -m parkos_core.jobs.refresh_mv_ocupacion`, NO asyncio task in-process en `api-sucursal` lifespan | Sigue patrón existente `sync_sucursal.py` / `sync_cloud.py` (cada worker en su proceso); separación de concerns; reinicio del worker no afecta api-sucursal; CLI entrypoint trivialmente testeable con pytest |
| **D-HU-F1.5-2 (KD-2)** | `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)` — sin columna sintética | La combinación `(uuid_sucursal, uuid_tipo_vehiculo)` es naturalmente única por el `GROUP BY` de la vista; el UNIQUE INDEX es **obligatorio** para `REFRESH MATERIALIZED VIEW CONCURRENTLY` (sin él, `CONCURRENTLY` falla con error explícito de Postgres) |
| **D-HU-F1.5-3 (KD-3)** | Autorización por sucursal: `operador-` solo `ctx.sucursal_uuid` (cross-tenant → `403 tenant_scope_violation`); `admin-` solo sucursales en `claims["sucursales_permitidas"]` (sin header → `400 missing_sucursal_context`) | Coherente con `auth/tenancy.py:115-131` y el boundary de visibilidad cross-branch (admin_views cloud-only); NO se permite a `admin-` consultar cualquier sucursal global |
| **D-HU-F1.5-4 (KD-4)** | Response shape = **breakdown por tipo de vehículo** `[{uuid_tipo_vehiculo, tipo, cupo_maximo, activos, disponible}, ...]`, NO agregado por sucursal | `plan.md:713` lo pide explícitamente; `OcupacionStrip` (F4.3) renderiza "Auto: 23/50" por tipo; cliente necesita granularidad por `tipo` |
| **D-HU-F1.5-5 (KD-5)** | Si `REFRESH MATERIALIZED VIEW CONCURRENTLY` falla (típicamente porque falta UNIQUE INDEX o porque Postgres está bajo carga), worker cae a `REFRESH MATERIALIZED VIEW` plain sin `CONCURRENTLY` (toma `AccessExclusiveLock` brevemente); lag máximo aceptable `2 * refresh_interval_s` | Defense in depth: el endpoint sigue sirviendo datos aunque el refresh sea subóptimo; RIESGO-SUC-02 del corpus ya documenta el lag como riesgo vivo aceptado |
| **D-HU-F1.5-6** | Pre-flight en migración: `DO $$ … count(*) FROM prod.ingreso … RAISE NOTICE si > 10M; RAISE EXCEPTION si > 50M` | Primer refresh sobre tabla grande puede tardar minutos; abortar con mensaje claro si supera umbral pidiendo precondición de indexación en `ingreso` |
| **D-HU-F1.5-7** | Helper puro `repo/ocupacion.py::get_ocupacion(session, *, uuid_sucursal) -> list[OcupacionItemRow]` con la query SQL del JOIN (`mv` × `tipos_vehiculo` × LEFT JOIN `cantidad_vehiculos_sucursal`) | Encapsula el SQL; testeable sin HTTP; consistente con `repo/cotizacion.py` (F1.8) |
| **D-HU-F1.5-8** | Excepción de dominio `OcupacionMaterializadaError` para envolver fallos del refresh job; handler HTTP mapea a `503 service_unavailable` con `Retry-After: 10` | Defense in depth: si la vista no responde al refresh (catástrofe DB), el endpoint degrada a 503 con backpressure claro en lugar de 500 genérico |
| **D-HU-F1.5-9** | AST walk `tests/static/test_no_write_in_ocupacion.py` rechaza `INSERT\|UPDATE\|DELETE\|TRUNCATE\|MERGE` dentro del handler `get_ocupacion` | Mismo patrón que F1.8 / F1.3; endpoint es read-only por contrato; CI gate contra dev futuro que agregue side-effects |
| **D-HU-F1.5-10 (KD-6 omitido)** | Si no existe fila en `cantidad_vehiculos_sucursal` para `(uuid_sucursal, uuid_tipo_vehiculo)`, devolver `disponible = -activos` con `cupo_maximo = 0`; el cliente interpreta `disponible < 0` como "configuración faltante, contacte al admin" | El endpoint siempre devuelve 200 con la breakdown actual; NO devuelve 404 — refleja estado real; cliente decide UX. Sale del scope de REQ contractuales (KD-6 omitido por acuerdo) |

## 3. Goals & Non-Goals

### 3.1 Goals

1. Crear la vista materializada `prod.mv_ocupacion_diaria` vía migración Alembic `0024`
   con UNIQUE INDEX obligatorio para `REFRESH CONCURRENTLY`.
2. Refrescar la vista cada 10s vía worker NSSM separado
   `python -m parkos_core.jobs.refresh_mv_ocupacion` (`RefreshMvOcupacionWorker`).
3. Exponer `GET /api/v1/operacion/ocupacion?uuid_sucursal=X` que devuelve breakdown por
   tipo de vehículo con `cupo_maximo`, `activos`, `disponible`.
4. Aplicar autorización por sucursal: `operador-` solo su sucursal pinneada, `admin-`
   solo sucursales de `claims["sucursales_permitidas"]`.
5. Defense in depth: pre-flight en migración (DO block cuenta filas + aborta si > 50M)
   + UNIQUE INDEX `CONCURRENTLY` + fallback KD-5 a `REFRESH` plain + typed exception
   `OcupacionMaterializadaError`.
6. Mantener `api/v1/__init__.py` intacto (`r.include_router(operacion.router)` ya está
   montado, no se toca).
7. AST walk read-only gate sobre el handler.
8. Cubrir con tests: 4 HTTP unit + 2 DB integration + 1 migration pre-flight + 1 AST
   walk + 2 worker cycle = **10 tests**.

### 3.2 Non-Goals

1. NO se crea path nuevo con sub-recurso (`/ocupacion/{uuid_tipo_vehiculo}`) — solo el
   listado por sucursal completa. Sale del scope.
2. NO se siembra el refresh job vía systemd / cron — la operación NSSM es responsabilidad
   de `infra/` y se documenta en `design.md`, no se automatiza desde este change.
3. NO se introduce websocket ni SSE para push de ocupación — el cliente hace polling
   10s. Sale del scope (alineado con `plan.md:1422-1442`).
4. NO se modifica `WorkerRunner` base (`jobs/runner.py`) — la subclase
   `RefreshMvOcupacionWorker` reusa la base tal cual.
5. NO se crea handler `POST /operacion/ocupacion` — solo GET (idempotente, read-only).
6. NO se agrega tenant scoping para `admin-` con visibilidad cross-branch (admin_views
   cloud-only) — KD-3 acota el scope a `claims["sucursales_permitidas"]`.
7. NO se cambia `make_router` (`api/v1/router_factory.py`) — `/operacion` no lo usa; el
   endpoint se monta directamente sobre el `APIRouter` custom.
8. NO se introduce lock sobre `prod.ingreso` / `prod.salidas` / `prod.anulaciones` —
   la vista materializada usa snapshot MVCC consistente; la atomicidad la garantiza el
   `REFRESH CONCURRENTLY` con UNIQUE INDEX.
9. NO se siembra catálogo adicional (`unidad_minutos`, `categoria_vehiculo`, etc.) — la
   vista opera exclusivamente sobre tablas existentes.
10. NO se crea endpoint `GET /operacion/ocupacion/{uuid_tipo_vehiculo}` filtrado por
    tipo — el breakdown completo cabe en una sola respuesta JSON.

## 4. Architecture Overview

```
HTTPS GET /api/v1/operacion/ocupacion?uuid_sucursal=X
        │
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        ▼
┌────────────────────────────────────────────────────────────────────────┐
│ api/v1/operacion.py  (APIRouter custom, línea 52)                     │
│ @router.get("/ocupacion")  (NUEVO handler get_ocupacion)               │
│                                                                        │
│ 1. resolver uuid_sucursal:                                             │
│      - query param → ctx.sucursal_uuid → 400 si None                  │
│      - KD-3 authz: validar contra ctx (operador) o                     │
│                    claims["sucursales_permitidas"] (admin)             │
│ 2. repo/ocupacion.py::get_ocupacion(session, uuid_sucursal)            │
│      │                                                                 │
│      │  SELECT mv.uuid_sucursal, mv.uuid_tipo_vehiculo, tv.tipo,      │
│      │         COALESCE(cvs.cantidad, 0) AS cupo_maximo,              │
│      │         mv.activos,                                            │
│      │         (COALESCE(cvs.cantidad,0) - mv.activos) AS disponible  │
│      │  FROM   prod.mv_ocupacion_diaria mv                            │
│      │    JOIN prod.tipos_vehiculo tv                                 │
│      │      ON tv.uuid = mv.uuid_tipo_vehiculo AND tv.vigente_hasta IS NULL│
│      │    LEFT JOIN prod.cantidad_vehiculos_sucursal cvs               │
│      │      ON cvs.uuid_sucursal = mv.uuid_sucursal                   │
│      │         AND cvs.uuid_tipo_vehiculo = mv.uuid_tipo_vehiculo     │
│      │         AND cvs.vigente_hasta IS NULL                          │
│      │  WHERE mv.uuid_sucursal = :uuid_sucursal                       │
│      │  ORDER BY tv.tipo                                              │
│      │                                                                 │
│      └─► list[OcupacionItemRow]                                        │
│ 3. wrap en OcupacionResponse {uuid_sucursal, items, generado_en}       │
│      └─► 200 OK con Cache-Control: no-store                            │
└────────────────────────────────────────────────────────────────────────┘
        ▲
        │ lectura read-only (sin locks)
        │
┌────────────────────────────────────────────────────────────────────────┐
│ prod.mv_ocupacion_diaria  (MATERIALIZED VIEW)                          │
│   SELECT i.uuid_sucursal, i.uuid_tipo_vehiculo, count(*) AS activos   │
│   FROM prod.ingreso i                                                 │
│   WHERE i.uuid_tipo_vehiculo IS NOT NULL                              │
│     AND NOT EXISTS (SELECT 1 FROM prod.salidas s                      │
│                     WHERE s.uuid_ingreso=i.uuid                       │
│                       AND s.uuid_sucursal=i.uuid_sucursal)             │
│     AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a                  │
│                     WHERE a.uuid_ingreso=i.uuid                      │
│                       AND a.estado='ejecutada'                        │
│                       AND a.tipo_anulable IN ('ingreso','salida'))    │
│   GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo;                     │
│                                                                        │
│   UNIQUE INDEX prod.uq_mv_ocupacion_diaria_sucursal_tipo              │
│     ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);  │
│                                                                        │
│   ◄── refrescada cada 10s por:                                         │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────┐       │
│   │ jobs/refresh_mv_ocupacion.py  (NUEVO)                      │       │
│   │ RefreshMvOcupacionWorker(WorkerRunner)                     │       │
│   │                                                            │       │
│   │ async def cycle(self):                                     │       │
│   │   try:                                                     │       │
│   │     await REFRESH MATERIALIZED VIEW CONCURRENTLY           │       │
│   │          prod.mv_ocupacion_diaria                          │       │
│   │     await self._session.commit()                           │       │
│   │   except Exception:                                        │       │
│   │     # KD-5 fallback a REFRESH plain sin CONCURRENTLY       │       │
│   │     await REFRESH MATERIALIZED VIEW                        │       │
│   │          prod.mv_ocupacion_diaria                          │       │
│   │     await self._session.commit()                           │       │
│   │   await asyncio.sleep(self.refresh_interval_s)  # = 10    │       │
│   └────────────────────────────────────────────────────────────┘       │
│         ▲                                                              │
│         │ proceso NSSM separado (cli: python -m parkos_core.jobs.refresh_mv_ocupacion)│
└────────────────────────────────────────────────────────────────────────┘
```

Toda la lógica de "ingreso activo" vive en la vista (server-side, reutilizable); el
handler HTTP es thin: resuelve authz, llama `repo/ocupacion.py::get_ocupacion`, envuelve
en `OcupacionResponse`. El worker de refresh es independiente de api-sucursal (KD-1).

## 5. Capabilities

### New

- **`operacion-ocupacion`** — cubre el endpoint `GET /operacion/ocupacion` con
  autorización KD-3, el schema `OcupacionResponse` con breakdown por tipo, y la
  autorización tipada (`403 tenant_scope_violation`, `400 missing_sucursal_context`).
  Spec en `openspec/changes/hu-f1-5-mv-ocupacion-diaria/specs/operational/spec.md`,
  archivada en `openspec/specs/operations/spec.md` como REQ-OPS-030, REQ-OPS-031.
- **`mv-ocupacion-diaria-refresh`** — cubre la vista materializada
  `prod.mv_ocupacion_diaria` con UNIQUE INDEX `CONCURRENTLY` y el worker
  `RefreshMvOcupacionWorker` con `cycle()` que ejecuta `REFRESH MATERIALIZED VIEW
  CONCURRENTLY` + fallback KD-5 a `REFRESH` plain. Spec REQ-OPS-032, REQ-OPS-033.

### Modified

- **`operations`** — la skill canónica agrega la regla "ocupación derivada de
  `ingreso - salidas - anulaciones` vía vista materializada refrescada server-side cada
  10s, expuesta por endpoint read-only con autorización por sucursal". Sin cambio
  contractual sobre REQ-OPS-001..029; sólo delta. Spec deltada en
  `openspec/changes/hu-f1-5-mv-ocupacion-diaria/specs/operations/spec.md`.

## 6. Data Model

`modelo_datos_er.mmd` tablas `prod.ingreso` (577-596, `[L-E]`), `prod.salidas`
(761-777, `[A]`), `prod.anulaciones` (`[L-W]`), `prod.cantidad_vehiculos_sucursal`
(428-446, `[V]`), `prod.tipos_vehiculo` (87-104, `[V]`) — **sin cambios de esquema**.
La migración `0024` sólo crea la vista materializada + UNIQUE INDEX.

**Columnas leídas** (todas existentes):

| Tabla | Columna | Lectura |
|---|---|---|
| `prod.ingreso` | `uuid`, `uuid_sucursal`, `uuid_tipo_vehiculo` | fuente de `count(*)` |
| `prod.salidas` | `uuid_ingreso`, `uuid_sucursal` | `NOT EXISTS` |
| `prod.anulaciones` | `uuid_ingreso`, `estado`, `tipo_anulable` | `NOT EXISTS` |
| `prod.cantidad_vehiculos_sucursal` | `uuid_sucursal`, `uuid_tipo_vehiculo`, `cantidad` | LEFT JOIN; `cupo_maximo` |
| `prod.tipos_vehiculo` | `uuid`, `tipo` | JOIN; nombre legible |

**DDL nuevo** (migración `0024_add_mv_ocupacion_diaria.py`):

```sql
-- Pre-flight (dentro de upgrade(), antes del CREATE MATERIALIZED VIEW):
DO $$
DECLARE
    _n_ingreso bigint;
    _n_anul    bigint;
BEGIN
    SELECT count(*) INTO _n_ingreso FROM prod.ingreso;
    SELECT count(*) INTO _n_anul    FROM prod.anulaciones;
    IF _n_ingreso > 10_000_000 THEN
        RAISE NOTICE 'mv_ocupacion_diaria_preflight: prod.ingreso tiene % filas, '
                     'el primer refresh puede tardar minutos', _n_ingreso;
    END IF;
    IF _n_ingreso > 50_000_000 THEN
        RAISE EXCEPTION 'mv_ocupacion_diaria_preflight_abort: prod.ingreso tiene % filas '
                        '(umbral 50M). Aplique índice (uuid_sucursal, uuid_tipo_vehiculo) '
                        'en prod.ingreso antes de continuar.', _n_ingreso;
    END IF;
END $$;

-- View:
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

-- UNIQUE INDEX OBLIGATORIO para REFRESH CONCURRENTLY:
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    prod.uq_mv_ocupacion_diaria_sucursal_tipo
    ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo);
```

**Downgrade** (`downgrade()`):

```sql
DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria;
-- (DROP MATERIALIZED VIEW borra también sus índices)
```

`CONCURRENTLY` permite crear/borrar el UNIQUE INDEX sin tomar `AccessExclusiveLock`
sobre la vista — crítico porque el polling 10s de N operadores lee concurrentemente.

**Grant**:

```sql
GRANT SELECT ON prod.mv_ocupacion_diaria TO parkos_app;
```

(La función `calcular_cotizacion` ya tiene `GRANT EXECUTE TO parkos_app`; el worker y
el endpoint usan el rol `parkos_app` que ya tiene `SELECT` sobre `ingreso`, `salidas`,
`anulaciones`, `cantidad_vehiculos_sucursal`, `tipos_vehiculo` — no se otorgan
privilegios adicionales para el JOIN.)

## 7. API Surface

| Path | Method | Cambio | Issuer / rol |
|---|---|---|---|
| `/api/v1/operacion/ocupacion` | GET | NUEVO endpoint con query param `uuid_sucursal: UUID4 \| None` | `operador-`, `admin-` |

**Request signature**:

```python
async def get_ocupacion(
    uuid_sucursal: UUID4 | None = Query(
        None,
        description="UUIDv4 de la sucursal. Default = ctx.sucursal_uuid. "
                    "Operador- solo su sucursal pinneada; admin- solo sucursales "
                    "de claims['sucursales_permitidas'].",
    ),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),
) -> OcupacionResponse:
```

**Response shape** (`OcupacionResponse`):

```python
class OcupacionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uuid_tipo_vehiculo: UUID
    tipo: str                                 # "Auto", "Moto", etc.
    cupo_maximo: int                          # 0 si no hay fila en cvs (KD-6 omitido)
    activos: int                              # count(*) de la vista materializada
    disponible: int                           # cupo_maximo - activos (puede ser <0)


class OcupacionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uuid_sucursal: UUID
    items: list[OcupacionItem]
    generado_en: datetime                     # NOW() del servidor, diagnóstico de lag
```

**Ejemplo**:

```json
// 200 OK
{
  "uuid_sucursal": "11111111-...",
  "items": [
    {"uuid_tipo_vehiculo": "aaaa...", "tipo": "Auto", "cupo_maximo": 50, "activos": 23, "disponible": 27},
    {"uuid_tipo_vehiculo": "bbbb...", "tipo": "Moto", "cupo_maximo": 20, "activos": 12, "disponible": 8}
  ],
  "generado_en": "2026-09-14T18:25:32.123456Z"
}
```

**Errores tipados**:

| HTTP | Body | Cuándo |
|---|---|---|
| 400 | `{"error":"missing_sucursal_context"}` | `uuid_sucursal` ausente y `ctx.sucursal_uuid is None` (admin- sin header `X-Sucursal-Context`) |
| 403 | `{"error":"tenant_scope_violation"}` | `operador-` con `uuid_sucursal != ctx.sucursal_uuid` (KD-3) |
| 403 | `{"error":"sucursal_not_permitted"}` | `admin-` con `uuid_sucursal` fuera de `claims["sucursales_permitidas"]` (KD-3) |
| 503 | `{"error":"ocupacion_materializada_error"}` | Vista materializada no responde al refresh (catástrofe DB) — header `Retry-After: 10` (D-HU-F1.5-8) |
| 401/403 | sin cambios | issuer inválido / falta token (precedente) |

**Headers**: `Cache-Control: no-store` (alineado con F1.8 R8).

**Sin cambios sobre**:

- `POST /operacion/ingresos`, `GET /operacion/ingresos/{uuid}`,
  `GET /operacion/ingresos/{uuid}/estado`, `GET /operacion/ingresos`,
  `GET /operacion/cotizar` (precedentes F1.8 / F1.6 / F1.1).

**Requirements planificados** (escritos en spec.md por `sdd-spec`):

- `REQ-OPS-030` — endpoint `GET /operacion/ocupacion?uuid_sucursal=X` con respuesta
  `OcupacionResponse` (breakdown por tipo) y header `Cache-Control: no-store`.
- `REQ-OPS-031` — autorización KD-3 (operador pinneado, admin acotado a
  `sucursales_permitidas`) + errores tipados (`403 tenant_scope_violation`,
  `400 missing_sucursal_context`).
- `REQ-OPS-032` — vista materializada `prod.mv_ocupacion_diaria` + UNIQUE INDEX
  `CONCURRENTLY` + pre-flight `DO $$` con umbrales 10M/50M.
- `REQ-OPS-033` — worker `RefreshMvOcupacionWorker` con `cycle()` que ejecuta
  `REFRESH MATERIALIZED VIEW CONCURRENTLY` + fallback KD-5 a `REFRESH` plain +
  `asyncio.sleep(refresh_interval_s=10)`.

## 8. Risks & Mitigations

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | Si el refresh job NSSM `refresh_mv_ocupacion` reinicia (crash, OOM, deploy), la vista queda stale indefinidamente hasta el próximo ciclo | Alta | En `startup` del worker, ejecutar `REFRESH MATERIALIZED VIEW mv_ocupacion_diaria` una vez antes de empezar el `asyncio.sleep` loop (mismo patrón que `sync_sucursal.py:82` `worker_started`). Documentar KD-1 en design |
| **R2** | Si hay ingresos concurrentes durante `REFRESH CONCURRENTLY`, no se pierden (MVCC snapshot consistente), pero la latencia puede acumularse bajo carga (10s + tiempo de refresh) | Media | Aceptable para v1 (KD-5); RIESGO-SUC-02 del corpus ya lo documenta como riesgo vivo; configurar alerta operativa si `refresh_duration_s > refresh_interval_s` |
| **R3** | Si falta fila en `cantidad_vehiculos_sucursal` para `(uuid_sucursal, uuid_tipo_vehiculo)`, `disponible` puede ser negativo (KD-6 omitido) | Media | `LEFT JOIN` con `COALESCE(cantidad, 0)` y aceptar `disponible < 0` como estado válido (no es bug, es señal de mala configuración). Cliente renderiza "N/A" en el strip. Documentado en design |
| **R4** | `REFRESH MATERIALIZED VIEW CONCURRENTLY` requiere UNIQUE INDEX — si la combinación `(uuid_sucursal, uuid_tipo_vehiculo)` NO fuera estrictamente única por diseño (futuro particionado por fecha), habría que agregar columna sintética | Alta | Hoy es seguro por el `GROUP BY`; documentar la dependencia en design; test de unicidad sobre `mv_ocupacion_diaria` valida invariante |
| **R5** | Si `prod.ingreso` tiene > 10M filas, el primer refresh puede tardar minutos (la vista materializada se inicializa lazy en el `CREATE MATERIALIZED VIEW`) | Baja | Pre-flight `DO $$` con `RAISE NOTICE` informativo si > 10M (sin abortar); `RAISE EXCEPTION` si > 50M pidiendo precondición de indexación en `ingreso` |
| **R6** | El `astwalk` `test_no_write_in_ocupacion.py` puede romperse si un dev futuro agrega `session.execute(text("SELECT … FOR UPDATE"))` (lectura con lock) | Baja | Aceptable como false positive — el test documenta explícitamente "read-only, sin locks". CI gate contra mutaciones accidentales |
| **R7** | `REFRESH MATERIALIZED VIEW` (sin `CONCURRENTLY`) toma `AccessExclusiveLock` y bloquea lecturas. Si UNIQUE INDEX llegara a faltar por migración manual, worker cae a `REFRESH` plain (KD-5 fallback) — durante ese refresh (típicamente < 100ms), el endpoint `GET /ocupacion` puede devolver 503 o timeout | Baja | KD-5 fallback a `REFRESH` plain documentado; alerta operativa si tiempo de refresh supera `refresh_interval_s`; `Retry-After: 10` en 503 |

## 9. Success Criteria

1. `pytest backend/tests/unit/test_operacion_ocupacion.py` verde — 4 HTTP-level tests:
   - T1: operador de sucursal X consulta `?uuid_sucursal=X` → `200` con `OcupacionResponse`
     conteniendo N items (breakdown por tipo).
   - T2: operador de sucursal X consulta `?uuid_sucursal=Y` (otra) → `403
     tenant_scope_violation` (KD-3).
   - T3: admin- con header `X-Sucursal-Context: Y` consulta `?uuid_sucursal=Y` →
     `200` (KD-3).
   - T4: admin- sin header `X-Sucursal-Context` y sin query param → `400
     missing_sucursal_context` (KD-3).
2. `pytest backend/tests/integration/test_mv_ocupacion_diaria_db.py` verde — 2 DB tests:
   - T1: insertar un ingreso `(uuid_sucursal=X, uuid_tipo_vehiculo=T)` → ejecutar
     `REFRESH MATERIALIZED VIEW` → la vista contiene `activos=1` para `(X, T)`.
   - T2: insertar ingreso + insertar `salidas` con `uuid_ingreso=I` → refresh → la
     vista decrementa `activos`. Verifica que la vista se mantiene sincronizada con
     `operacion.py:152-168`.
3. `pytest backend/tests/integration/test_migration_0024_mv.py` verde — pre-flight de
   la migración:
   - Aplicar la migración 0024 sobre un schema con datos sucios (5 ingresos, 2 con
     salida, 1 anulada) → la vista se crea, se puebla correctamente, UNIQUE INDEX se
     aplica sin colisiones.
4. `pytest backend/tests/static/test_no_write_in_ocupacion.py` verde — AST walk rechaza
   `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` en el cuerpo del handler `get_ocupacion`.
5. `pytest backend/tests/integration/test_refresh_mv_job.py` verde — 2 tests del worker:
   - T1: `RefreshMvOcupacionWorker.cycle()` ejecuta `REFRESH CONCURRENTLY` y la vista se
     refresca (verificar timestamp de la última fila).
   - T2: si Postgres devuelve error en `REFRESH CONCURRENTLY`, worker cae a `REFRESH`
     plain sin crashear el ciclo (KD-5 fallback).
6. Migración `0024_add_mv_ocupacion_diaria.py` aplica limpia en BD de tests; downgrade
   sin errores.
7. `ruff check`, `ruff format --check`, `mypy --strict` verde sobre los 7 archivos
   nuevos/modificados (3 nuevos + 2 modificados en backend + 5 test files).
8. Header `Cache-Control: no-store` presente en toda respuesta 2xx/4xx/5xx del endpoint.
9. Defense in depth gate: pre-flight `DO $$` se ejecuta dentro de la TX Alembic;
   verifica con test que sobre schema con > 50M filas simuladas la migración aborta con
   `RAISE EXCEPTION` explícito (sin dejar la vista a medias).
10. Fallthrough to KD-5 fallback: test que simula Postgres sin UNIQUE INDEX verifica que
    el worker cicla sin crashear y la vista eventualmente se refresca con `REFRESH`
    plain (KD-5 mitigation).
11. AST walk read-only gate: test verifica que el handler `get_ocupacion` no contiene
    `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` ni `session.execute(text("SELECT … FOR
    UPDATE/SHARE"))` en su cuerpo.
12. `make_router` intacto: `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py`
    retorna vacío.
13. `WorkerRunner` base intacto: `git diff backend/packages/parkos_core/src/parkos_core/jobs/runner.py`
    retorna vacío (la subclase `RefreshMvOcupacionWorker` reusa la base tal cual).
14. Ningún cambio en `openspec/specs/operations/spec.md`破坏 REQ-OPS-001..029; sólo
    delta en REQ-OPS-030..033.

## 10. Out of Scope (deferred)

1. Visibilidad cross-branch para `admin-` (consultar cualquier `uuid_sucursal` global,
   no solo `claims["sucursales_permitidas"]`). Sale del scope: admin_views cloud-only
   es un producto separado. KD-3 acota explícitamente.
2. Push de ocupación vía websocket / SSE. Sale del scope: el cliente hace polling 10s
   (`plan.md:1422-1442`); mantener conexiones long-lived en `api-sucursal` queda fuera
   del SLA.
3. Mitigación de RIESGO-SUC-02 (lag máximo 10s en momentos de alta rotación). Sale del
   scope: el corpus ya lo documenta como riesgo vivo aceptado; mitigación
   (configuración de intervalo por sede) es operacional, no de HU.
4. Endpoint `GET /operacion/ocupacion/{uuid_tipo_vehiculo}` filtrado por tipo. Sale del
   scope: el breakdown completo cabe en una sola respuesta JSON; no hay caso de uso para
   filtro server-side.
5. Lock pesimista `SELECT … FOR SHARE` sobre `ingreso` / `salidas` / `anulaciones`
   desde el endpoint. Sale del scope: la vista materializada usa snapshot MVCC
   consistente; la atomicidad la garantiza `REFRESH CONCURRENTLY` con UNIQUE INDEX.
6. Indexación `(uuid_sucursal, uuid_tipo_vehiculo)` sobre `prod.ingreso` para acelerar
   el primer refresh. Precondición documentada en pre-flight (> 50M filas); no se
   agrega en este change.
7. Siembra operativa del refresh job vía systemd / cron / k8s CronJob. La operación
   NSSM es responsabilidad de `infra/`; este change solo entrega el script
   `python -m parkos_core.jobs.refresh_mv_ocupacion`.
8. Versionado de UI cliente (Fase 2 frontend — `OcupacionStrip` consumirá el endpoint).
9. Métricas / observabilidad del refresh (contador de cycles, latencia p99 del
   `REFRESH`, alertas si `refresh_duration_s > refresh_interval_s`). Sale del scope;
   alineado con HU-F1.X de observabilidad (futuro).
10. Tabla `categorias_vehiculo` para agrupar tipos (Auto/Moto/Camioneta). No existe en
    el ER; no se crea.
11. Endpoint `GET /operacion/ocupacion/resumen` (agregado `{cupo_total, activos_total,
    disponible_total}` sin breakdown). Sale del scope: KD-4 eligió breakdown por tipo.

## 11. Relevant Files

**Nuevos** (7 archivos backend):

- `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` —
  Alembic: pre-flight `DO $$` + `CREATE MATERIALIZED VIEW` + UNIQUE INDEX `CONCURRENTLY`
  + `GRANT SELECT` + downgrade `DROP MATERIALIZED VIEW`.
- `backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py` —
  `RefreshMvOcupacionWorker(WorkerRunner)` con `cycle()` async + KD-5 fallback +
  CLI `main()` con exit codes 0/1/2.
- `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` — helper puro
  `get_ocupacion(session, *, uuid_sucursal) -> list[OcupacionItemRow]` con SQL del JOIN.
- `backend/tests/unit/test_operacion_ocupacion.py` — 4 HTTP-level tests vía
  `httpx.AsyncClient + ASGITransport`.
- `backend/tests/integration/test_mv_ocupacion_diaria_db.py` — 2 DB-backed tests con
  `PARKOS_DOCKER_TEST=1`.
- `backend/tests/integration/test_migration_0024_mv.py` — pre-flight de migración con
  datos sucios + defense in depth gate (> 50M abort).
- `backend/tests/static/test_no_write_in_ocupacion.py` — AST walk read-only.
- `backend/tests/integration/test_refresh_mv_job.py` — 2 tests del worker (cycle normal
  + KD-5 fallback).

**Modificados** (2 archivos backend):

- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` — agregar handler
  `get_ocupacion` antes/después del `cotizar_ingreso_handler` (orden irrelevante — paths
  no colisionan). Aplicar `_ingreso_issuer_dep` (línea 64).
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` — agregar
  `OcupacionItem`, `OcupacionResponse` al final del archivo (post-F1.8).
- `openspec/specs/operations/spec.md` — agregar REQ-OPS-030..033 + entrada en
  `## Modified Capabilities`.

**Archivos NO tocados (deliberado)**:

- `api/v1/__init__.py` (router ya montado en línea 143, no se toca).
- `api/v1/router_factory.py` (factory F1.1, no se usa en `/operacion`).
- `api/deps.py` (centraliza `get_tenant_ctx` + `requires_issuer`, se reusa tal cual).
- `models/L_E/ingreso.py`, `models/V/cantidad_vehiculos_sucursal.py`,
  `models/V/tipos_vehiculo.py`, `models/A/salidas.py`, `models/L_W/anulaciones.py`
  (sin cambios de esquema, solo lectura).
- `repo/cotizacion.py` (helper F1.8, semánticamente reusable pero el patrón se replica
  en `repo/ocupacion.py` con SQL distinto — JOIN sobre vista en lugar de PL/pgSQL).
- `auth/tenancy.py` (KD-3 reusa los errores tipados ya definidos en líneas 60-65 y
  115-131).
- `jobs/runner.py` (la base `WorkerRunner` se reusa sin cambios — D-HU-F1.5-1,
  D-HU-F1.5-2).

## 12. Open Questions

**Ninguna abierta**. Las 5 KD (KD-1 worker separado, KD-2 UNIQUE INDEX natural, KD-3
autorización por sucursal, KD-4 breakdown por tipo, KD-5 aceptar lag / fallback
plain) están recomendadas en la exploration con fecha 2026-09-14 y se adoptan sin
disputa. KD-6 (cupo no configurado → `disponible < 0`) se omite por acuerdo — sale del
scope contractual (D-HU-F1.5-10). Las 5 preguntas abiertas de `exploration.md §14`
quedan resueltas en design vía adopción de KD:

- **OQ-1 (KD-1 ubicación del refresh job)** — RESUELTO a favor de worker NSSM separado
  (`RefreshMvOcupacionWorker` en `parkos_core.jobs.refresh_mv_ocupacion`). Decisión
  D-HU-F1.5-1. Justificación: separación de concerns vs ops extra — el costo operacional
  (un NSSM más) es bajo y el script CLI es trivialmente testeable con pytest.
- **OQ-2 (KD-3 alcance de autorización para `admin-`)** — RESUELTO a favor de acotar a
  `claims["sucursales_permitidas"]`. Decisión D-HU-F1.5-3. Coherente con
  `auth/tenancy.py:122`; cross-branch view (admin_views cloud-only) queda fuera del
  scope.
- **OQ-3 (KD-5 circuit breaker)** — RESUELTO a favor de aceptar lag de hasta `2 *
  refresh_interval_s` y NO agregar circuit breaker. Decisión D-HU-F1.5-5. El corpus ya
  documenta RIESGO-SUC-02 como riesgo vivo aceptado.
- **OQ-4 (KD-6 UX ante cupo no configurado)** — RESUELTO a favor de devolver
  `disponible: -activos` con `cupo_maximo: 0` (cliente renderiza "N/A"). Decisión
  D-HU-F1.5-10 (KD-6 omitido). El endpoint siempre devuelve 200 con la breakdown
  actual.
- **OQ-5 (¿Sembrar la vista en el seed inicial o esperar al primer ciclo del
  worker?)** — RESUELTO a favor de NO sembrar — la vista se inicializa en el `CREATE
  MATERIALIZED VIEW` (DDL implícito); el primer refresh del worker la puebla. Decisión
  documentada en design; orden startup = migrate → worker arranca → primer refresh
  (puede tardar segundos en producción).

Si durante `sdd-design` surge evidencia técnica fuerte para revisar alguna KD (ej: el
pre-flight de cardinalidad revela > X filas esperadas en producción), se reabre en
`design.md` con evidencia. Caso base: el plan original está completo y es ejecutable
tal cual.