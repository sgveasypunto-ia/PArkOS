# PRD: cantidad_vehiculos_sucursal (T15)

> Capacity / quota per (sucursal, tipo_vehiculo). Defines the **cupo máximo** of vehicles per type that can be inside the branch simultaneously. Consulted at every `ingreso` to enforce capacity; decremented (effectively) at every `salidas`. **Strict mode by default** (admin configurable per branch): exceeding cupo rejects the ingreso with 409 + emits `alerta`.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration_plan.md`](../iteration_plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule I: cupo check at ingreso is segregated from facturacion*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.cantidad_vehiculos_sucursal`
- **SQL name**: `cantidad_vehiculos_sucursal` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema + parametrization seed in `uc.sucursal.admin-onboarding-pairing-flow`) + IT-2 (admin CRUD, capacity updates)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; cupo enforcement + decrement + reporting documented)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `cantidad` is `int` (e.g., `50` for autos in a medium branch, `20` for motos).
- Vigente lookup: `SELECT * FROM cantidad_vehiculos_sucursal WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo AND vigente_hasta IS NULL`. Returns 1 row per triple (enforced by UNIQUE partial index).

## 3. SOLID Atomic Breakdown
- **S**: "one capacity quota for (sucursal, tipo_vehiculo) tuple at a specific time window". Consulted at every ingreso for capacity enforcement; NOT modified at salida time (the count is derived from `ingreso WHERE estado='activo'`).
- **O**: extensible via JSON if needed (e.g., `registro: {strict_mode: true, max_overflow_pct: 10}`) — currently not in model; sprint 5 may add.
- **I**: admin CRUD via `api_admin /cantidad-vehiculos-sucursal`; branch reads own vigentes at ingreso; cloud admin reads cross-branch for reporting.
- **D**: `parkos_core/models/V/cantidad_vehiculos_sucursal.py` (model); `parkos_core/operacion/cupo_validator.py::check(uuid_sucursal, uuid_tipo_vehiculo)` (returns `{cupo_total, cupo_actual, available: cupo_total - cupo_actual, is_full: boolean}`); `workers/cupos/reconciler.py` (cron that verifies count drift).
- **Atomic**: INSERT (admin creates new cupo), UPDATE (creates new version — archive old), DELETE forbidden by FK RESTRICT.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch |
| `uuid_tipo_vehiculo` | `prod.tipos_vehiculo.uuid` | exactly one (NOT NULL) | RESTRICT | the vehicle type |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | capacity is consulted by ingreso via UUID lookup, NOT by FK from `ingreso` |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin via `api_admin /cantidad-vehiculos-sucursal`; inside TX + `log_transaccional` |
| UPDATE | YES (archive only) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted with new UUID. NEVER modify `cantidad` of existing version — preserves audit of capacity changes over time. |
| DELETE | NO | Archive via version flow; FK RESTRICT prevents |

**Special rules**:
- Vigente lookup: 1 row per (sucursal, tipo_vehiculo) triple at a time, enforced by UNIQUE partial index `(uuid_sucursal, uuid_tipo_vehiculo) WHERE vigente_hasta IS NULL`.
- **Strict mode default**: when current count >= cantidad, ingreso is rejected with 409. Configurable per branch via `registro.strict_mode` (sprint 5 JSON extension; current: always strict, no overflow tolerated).
- Count is derived from `ingreso WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo AND estado='activo'` (the `activo` state is derived from `salidas` + `anulaciones` existence — per `uc.ingreso.*`). NOT stored anywhere as a counter; computed at every check.
- The `cupo_reconciler` cron (cloud-side, hourly) recomputes the count and emits `alerta` if it detects drift (e.g., due to a bug that failed to insert `salidas`).

## 6. CodeGraph Dependencies
- `api_admin/routers/cantidad_vehiculos_sucursal.py::POST /cantidad-vehiculos-sucursal`, `PATCH /cantidad-vehiculos-sucursal/{uuid}`, `GET /cantidad-vehiculos-sucursal`, `GET /cantidad-vehiculos-sucursal/cross-branch`.
- `api_sucursal/routers/cantidad_vehiculos_sucursal.py::GET /cantidad-vehiculos-sucursal` (own vigentes).
- `parkos_core/operacion/cupo_validator.py::check()` (used at every ingreso).
- `api_sucursal/routers/ingresos.py::POST /ingresos` (calls `cupo_validator` BEFORE INSERT; rejects with 409 if full).
- `workers/cupos/reconciler.py` (cron, hourly; recomputes counts + emits drift alerts).
- `web_admin/CantidadVehiculosForm`, `CantidadVehiculosGrid` (cross-branch view).

## 7. Use Cases enabled by this table

The `cantidad_vehiculos_sucursal` table is the **capacity gate** for every vehicle entry: the operator cannot create an `ingreso` if the branch's cupo for that vehicle type is full. Use cases below describe the admin CRUD flow, the rejection path at ingreso (with `alerta` workflow), the implicit decrement at salida (via count derivation), the reconciler that catches drift, and the cross-branch reporting.

### 7.1 Use Case: `uc.cupos.admin-sets-or-updates-capacity`

Admin cloud configura el cupo de una branch para un tipo de vehículo (ejemplo: ampliar de 50 autos a 60 autos tras una expansión del lote). Crea una nueva versión `[V]` de `cantidad_vehiculos_sucursal` con `cantidad=60`, archiva la versión anterior con `vigente_hasta=NOW()`, y dispara parametrización push. El flujo toca 6 tablas: `cantidad_vehiculos_sucursal` (W nueva versión + UPDATE archivo), `sucursal` (R tenant), `tipos_vehiculo` (R), `permisos_usuario` (R RBAC), `log_transaccional` (W), `sync_queue` (W).

**Actor**: admin

**Pre-conditions**: branch exists with `estado='activo'`; previous cupo version exists (unless first-time); admin has `permiso='actualizar_cupos'`; `tipos_vehiculo` catalog populated.

**Steps**:
1. Admin opens `web_admin/SucursalDetail/{branch}/CuposTab`, sees current grid: autos=50, motos=20, camionetas=10, bicicletas=15.
2. Admin clicks on autos cell, changes `cantidad` from 50 to 60. Frontend shows confirmation: "Esto aumenta el cupo de autos de 50 a 60. Los ingresos futuros permitirán hasta 60 autos simultáneos. ¿Continuar?"
3. Admin confirms. Frontend PATCHes `api_admin /cantidad-vehiculos-sucursal/{uuid_vigente}` with `{cantidad: 60, vigente_desde: NOW()}`.
4. Backend validates `permisos_usuario` for `permiso='actualizar_cupos'`; rejects 403 if missing.
5. Backend SELECTs current vigente row for (sucursal, tipo_vehiculo='auto'). If none: this is a first-time INSERT.
6. Backend opens TX; SELECT chain anchor from `log_transaccional`.
7. Backend validates no overlap with other versiones vigentes for the same triple.
8. Backend INSERTs new `cantidad_vehiculos_sucursal` row (`vigente_desde=NOW(), vigente_hasta=NULL, cantidad=60`). If updating: also UPDATE old row SET `vigente_hasta=NOW()`.
9. Backend INSERTs `log_transaccional` (`accion='cupo_actualizado'`, `tabla_afectada='cantidad_vehiculos_sucursal'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_anteriores={old_cantidad, old_vigente_hasta: NOW()}`, `datos_nuevos={new_cantidad, new_vigente_hasta: null, reason: 'expansion_lote'}`).
10. `queue_processor.enqueue('cantidad_vehiculos_sucursal', $new_uuid, $snapshot)` + parametrization push for the archive UPDATE. INSERT 1-2 `sync_queue` rows.
11. Backend returns `{new_uuid, old_uuid_archived, vigente_desde}` to frontend.
12. Branch receives parametrization within 30s. UPSERTs new row + UPDATE old row's `vigente_hasta`. Next ingreso lookup sees the new cupo.

**Tables touched (writes)**: `cantidad_vehiculos_sucursal` (1 new + 1 archive UPDATE), `log_transaccional` (1 row), `sync_queue` (1-2 rows).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `sucursal` (tenant), `tipos_vehiculo` (catalog), `cantidad_vehiculos_sucursal` (vigente lookup), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `cantidad_vehiculos_sucursal.uuid_sucursal` → `sucursal.uuid`; `cantidad_vehiculos_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `cantidad_vehiculos_sucursal.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the new version + archive update within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (cupo_actualizado); branch chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `sucursal` (tenant), `tipos_vehiculo` (catalog), `cantidad_vehiculos_sucursal` (vigente lookup), `log_transaccional` (chain anchor), `usuarios` (admin).
- Writes to: `cantidad_vehiculos_sucursal` (new + archive), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: capacity is a **planning artifact** — admin sets it based on physical lot size, expected turnover, business hours. Changes are infrequent (expansion, contraction). The versioning preserves the history of capacity over time, useful for analytics (e.g., "in 2025 we had 50 autos; in 2026 we expanded to 60").
- Related: if admin wants to TEMPORARILY increase cupo for a special event (e.g., holiday market), they could create a short-lived version with `vigente_desde=event_start, vigente_hasta=event_end`. Currently the version flow only handles single-point-in-time replacement; sprint 5 may add scheduled-future versions.

### 7.2 Use Case: `uc.cupos.branch-rejects-ingreso-when-full`

Cuando llega un vehículo casual y el operador registra el ingreso, el sistema valida el cupo disponible: SELECTs `cantidad_vehiculos_sucursal` vigente + cuenta `ingreso WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo AND estado='activo'`. Si `count >= cantidad`, rechaza con 409 + emite `alerta tipo_alerta='cupo_lleno'` para que el admin investigue (¿expandir cupo? ¿redirigir tráfico? ¿hay salidas pendientes?). NO se inserta `ingreso`. El flujo toca 6 tablas: `cantidad_vehiculos_sucursal` (R), `ingreso` (R count), `alerta` (W workflow root), `log_transaccional` (W), `sync_queue` (W), `sucursal` (R tenant).

**Actor**: operator (triggers via IngresoForm POST) + system (rejection logic)

**Pre-conditions**: branch has `cantidad_vehiculos_sucursal` vigente for the tipo_vehiculo; current count is at or above the cupo.

**Steps**:
1. Vehicle arrives at the booth. Operator opens `web_sucursal/IngresoForm`, types plate, selects `uuid_tipo_vehiculo='auto'`.
2. Frontend POSTs `api_sucursal /ingresos` with `{placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente: null}`.
3. Backend opens TX; SELECT chain anchor from `log_transaccional`.
4. Backend calls `cupo_validator.check(uuid_sucursal=$branch, uuid_tipo_vehiculo='auto')`.
5. `cupo_validator` SELECTs `cantidad_vehiculos_sucursal.cantidad` for the vigente row. Then SELECTs COUNT from `ingreso WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo='auto' AND estado='activo'`.
6. Returns `{cupo_total: 50, cupo_actual: 50, available: 0, is_full: true}`.
7. Backend rejects: INSERT `log_transaccional` (`accion='cupo_rechazado'`, `tabla_afectada='cantidad_vehiculos_sucursal'`, `uuid_registro_afectado=$cupo_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_nuevos={placa, tipo, cupo_total, cupo_actual, reason: 'cupo_lleno'}`).
8. Backend INSERTs `alerta` (`tipo_alerta='cupo_lleno'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_alerta_padre=NULL`, `observaciones='cupo_lleno_para_auto_50/50'`).
9. Backend returns `409 Conflict {detail: 'cupo_lleno', tipo_vehiculo: 'auto', cupo_total: 50, cupo_actual: 50, alert_uuid: $alert_uuid}` to frontend.
10. `queue_processor.enqueue('log_transaccional', $uuid, $snapshot)` + enqueue `alerta`.
11. Operator UI shows the rejection with red banner: "Cupo lleno para autos (50/50). El cliente debe ser redirigido a otra branch o esperar."
12. Operator tells the customer the lot is full; may suggest the next branch or escalate to admin.
13. Admin sees the `alerta` in `web_admin/AlertasList`. Admin options: (a) call operator to ask about pending `salidas` (maybe one is overdue and `cupo_actual` count is wrong); (b) expand cupo via PATCH (use case 7.1) — but only if physical lot actually has space; (c) investigate via `cupo_reconciler` if the count is drifting.
14. The `alerta` workflow chain emits 2-3 `log_transaccional` rows total (root + transitions).

**Tables touched (writes)**: `log_transaccional` (1 branch + 1 cloud when received), `alerta` (1 root + 2-3 transitions), `sync_queue` (deferred propagation).
**Tables touched (reads)**: `cantidad_vehiculos_sucursal` (vigente lookup), `ingreso` (count query), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator actor).
**FKs traversed**: `cantidad_vehiculos_sucursal.uuid_sucursal` → `sucursal.uuid`; `cantidad_vehiculos_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `ingreso.uuid_sucursal` → `sucursal.uuid`; `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `ingreso.estado='activo'` is DERIVED from `salidas` + `anulaciones` (no FK needed for the derivation); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `cantidad_vehiculos_sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain).

**Sync behavior**:
- Branch → cloud: YES — the rejection audit + alerta workflow root push via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact; this is a branch-originated operational event).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row (cupo_rechazado); cloud chain extends by 1 row when received. Alerta workflow emits 2-3 additional rows.

**Integration with other tables**:
- Reads from: `cantidad_vehiculos_sucursal` (cupo lookup), `ingreso` (count), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator).
- Writes to: `log_transaccional` (audit), `alerta` (workflow root + transitions), `sync_queue` (deferred propagation).
- Cross-cutting: this is the **capacity enforcement gate**. Without this check, a branch could accept unlimited vehicles, exceeding physical lot capacity and creating safety issues. The strict-mode default reflects business reality.
- Related: subscribers with active subscription may have a "pase especial" that bypasses the cupo check (per `uc.ingreso.subscriber-rotacion-cupo-agotado` — subscriber's own cupo is a separate concept, but their ingreso could bypass branch cupo with admin override). Sprint 5 may formalize this.

### 7.3 Use Case: `uc.cupos.effective-count-decrements-on-salida-and-reconciler-catches-drift`

El cupo efectivo (current count) se DERIVA de `ingreso WHERE estado='activo'`. Cuando se crea una `salidas` row, el estado del ingreso pasa a `cerrado` (derivado), y el `count` efectivo disminuye en 1. **No hay UPDATE explícito en `cantidad_vehiculos_sucursal`** — el cupo total sigue igual; solo el count cambia. El `cupo_reconciler` worker (cron cloud-side, hourly) recalcula el count desde `ingreso` y lo compara contra el último snapshot cacheado. Si hay drift (count difiere del snapshot), emite `alerta tipo_alerta='cupo_count_drift'` para que el admin investigue (posible bug que no insertó `salidas`). El flujo toca 5 tablas en lectura + 1 en escritura opcional (`alerta`).

**Actor**: system (cloud `cupo_reconciler` cron worker)

**Pre-conditions**: branch has been operating for some time; at least one `ingreso` and one `salidas` exist; `cupo_count_cache` (sprint 5) or last computed snapshot exists for comparison.

**Steps**:
1. Vehicle departs. Operator opens `SalidaForm`, types plate. Backend creates `salidas` row (append-only, `[A]`). The corresponding `ingreso`'s derived state changes from `activo` to `cerrado` (because the `salidas` row exists for it).
2. (No explicit UPDATE to `cantidad_vehiculos_sucursal` — the cupo total is unchanged. Only the count query result decreases.)
3. Hourly cron `cupo_reconciler` fires. For each (sucursal, tipo_vehiculo) triple with a vigente cupo:
   a. Computes `current_count = SELECT COUNT(*) FROM ingreso WHERE uuid_sucursal=$branch AND uuid_tipo_vehiculo=$tipo AND estado='activo'`.
   b. Compares to last snapshot (from `cupo_count_cache` table — sprint 5 — or from previous cron run's recorded value in `log_transaccional`).
   c. If `current_count != last_snapshot`: potential drift. INSERTs `alerta tipo_alerta='cupo_count_drift'` with `observaciones='branch:$uuid, tipo:$tipo, snapshot:$last, actual:$current, delta:$X'`.
   d. Records new snapshot.
4. For each `alerta`: INSERT `log_transaccional` (auditoria).
5. Admin sees the alert. Investigates: maybe an `ingreso` was created without the corresponding `salidas` being recorded (e.g., bug, manual override, manual deletion attempt that the REVOKE blocked). Admin may manually file `anulaciones` for the orphan `ingreso` to fix the count.
6. INSERT `sync_log` (cycle metrics).
7. Alerta workflow chain emits 2-3 `log_transaccional` rows total.

**Tables touched (writes)**: optional `alerta` (drift detected) + 1+ `log_transaccional` (audit) + `sync_log` (cycle).
**Tables touched (reads)**: `ingreso` (count query), `cantidad_vehiculos_sucursal` (vigente triples), `salidas` (existence check — does each ingreso have a salida?), `anulaciones` (existence check — was the ingreso anulada?), `log_transaccional` (chain anchor + last snapshot), `sucursal` (tenant).
**FKs traversed**: `ingreso.uuid_sucursal` → `sucursal.uuid`; `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `ingreso.estado='activo'` is DERIVED (via `salidas` + `anulaciones` FKs); `salidas.uuid_ingreso` → `ingreso.uuid` (1:1); `anulaciones.uuid_ingreso` → `ingreso.uuid` (1:N); `cantidad_vehiculos_sucursal.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (reconciler runs cloud-side; the count is computed from `ingreso` rows received via sync from branch).
- Cloud → branch: NO (alerta is cloud-only operational; branch doesn't need to know about count drift).
- DIAN trigger: NO.
- Hash chain impact: **NO** for the routine reconciler run (read-only). YES if drift detected: cloud chain extends by 1 row (cupo_count_drift alert + workflow transitions).

**Integration with other tables**:
- Reads from: `ingreso` (count), `cantidad_vehiculos_sucursal` (vigente triples), `salidas` (existence), `anulaciones` (existence), `log_transaccional` (last snapshot + chain anchor), `sucursal` (tenant).
- Writes to: optional `alerta` (drift) + `log_transaccional` (audit) + `sync_log` (cycle).
- Cross-cutting: this is the **consistency enforcer**. The derived count (`ingreso WHERE estado='activo'`) is the source of truth; if it ever disagrees with reality (e.g., a `salidas` was supposed to be inserted but wasn't due to a bug), the reconciler catches it. The audit trail of `log_transaccional` snapshots makes drift investigation possible.
- Related: the reconciler is **defensive** — in a perfect world, drift never happens because every departure creates exactly one `salidas` row. But defensive engineering requires detection: if the drift is real, admin investigates; if false positive (e.g., timing race), admin dismisses the alerta.

### 7.4 Use Case: `uc.cupos.cloud-cross-branch-occupancy-reporting`

Admin cloud genera un reporte cross-branch de ocupación actual: para cada branch, porcentaje de cupo ocupado por tipo de vehículo. Usa para análisis de capacidad, decisión de expansión, o marketing (identificar branches con cupo disponible para redirigir clientes). Query: SELECTs cada vigente cupo + COUNT de ingresos activos + computa porcentaje. El flujo toca 5 tablas en lectura + 1 en escritura opcional (`log_transaccional` si el admin exporta).

**Actor**: admin

**Pre-conditions**: at least one branch is operational with `cantidad_vehiculos_sucursal` vigentes and `ingreso` activity.

**Steps**:
1. Admin opens `web_admin/Reportes/OcupacionCrossBranch`, selects date range (defaults to "now"), optional filters (ciudad, tipo_sucursal).
2. Frontend GETs `api_admin /cantidad-vehiculos-sucursal/ocupacion?as_of=NOW()` (admin- JWT).
3. Backend validates `permisos_usuario` for `permiso='ver_reportes_ocupacion'`.
4. Backend SELECTs for each (sucursal, tipo_vehiculo):
   ```sql
   SELECT s.uuid AS uuid_sucursal, s.nombre, s.ciudad,
          cvs.uuid_tipo_vehiculo, tv.tipo AS tipo_vehiculo_nombre,
          cvs.cantidad AS cupo_total,
          (SELECT COUNT(*) FROM ingreso i WHERE i.uuid_sucursal=s.uuid AND i.uuid_tipo_vehiculo=cvs.uuid_tipo_vehiculo AND i.estado='activo') AS cupo_actual,
          ROUND(100.0 * cupo_actual / cvs.cantidad, 1) AS ocupacion_pct
   FROM sucursal s
   JOIN cantidad_vehiculos_sucursal cvs ON cvs.uuid_sucursal=s.uuid
   JOIN tipos_vehiculo tv ON cvs.uuid_tipo_vehiculo=tv.uuid
   WHERE s.estado='activo' AND cvs.vigente_hasta IS NULL
   ```
5. Returns `{rows: [...], summary: {branches_count, avg_ocupacion, branches_full_count, branches_almost_full_count (>90%)}}`.
6. Frontend renders the report with color coding: green (<70%), yellow (70-90%), red (>90%).
7. Admin clicks `Export CSV` → backend generates CSV, INSERTs `log_transaccional` (`accion='reporte_ocupacion_exportado'`, `tabla_afectada='cantidad_vehiculos_sucursal'`, `uuid_usuario=$admin_uuid`, `datos_nuevos={filters, row_count}`).
8. Admin downloads CSV.
9. Admin can drill into any branch → opens `SucursalDetail/{uuid}/CuposTab`.

**Tables touched (writes)**: optional `log_transaccional` (1 row on CSV export).
**Tables touched (reads)**: `cantidad_vehiculos_sucursal` (vigente grid), `ingreso` (count), `sucursal` (denormalized JOIN), `tipos_vehiculo` (catalog), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin actor).
**FKs traversed**: `cantidad_vehiculos_sucursal.uuid_sucursal` → `sucursal.uuid`; `cantidad_vehiculos_sucursal.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `ingreso.uuid_sucursal` → `sucursal.uuid`; `ingreso.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `sucursal.uuid_tipo_sucursal` → `tipo_sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read-only on cloud's own data + data received via sync).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: **NO** for the read itself (per SOLID I). YES for the export action (1 row extends the chain).

**Integration with other tables**:
- Reads from: `cantidad_vehiculos_sucursal` (vigente grid), `ingreso` (count), `sucursal` (denormalized), `tipos_vehiculo` (catalog), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin).
- Writes to: optional `log_transaccional` (export audit).
- Cross-cutting: this is the **operational reporting layer** for capacity. The cross-branch view enables strategic decisions (expansion, redirection, marketing).
- Related: the report may surface anomalies — e.g., a branch with 95% ocupacion but low `salidas` rate suggests long stays (potential issue). Admin can drill into `SalidasReport` for that branch.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 28, 31.

## 9. RED Tests
- (RED) F1 schema includes `cantidad_vehiculos_sucursal` with UNIQUE partial index on vigentes.
- (RED) F1 onboarding seed inserts 4 placeholder rows per branch (one per `tipos_vehiculo`).
- (RED) Admin PATCH `/cantidad-vehiculos-sucursal/{uuid}` with new `cantidad` → new version created; old vigente archived.
- (RED) Admin POST with overlap → 409.
- (RED) Operator POST `/ingresos` when `count >= cantidad` → 409 + `alerta tipo_alerta='cupo_lleno'`.
- (RED) Operator POST when `count < cantidad` → 201; `ingreso` inserted.
- (RED) After operator creates `salidas`, next ingreso for same tipo passes (count decreased).
- (RED) Cupo reconciler: simulate drift (manual SQL bug that creates orphan ingreso without salida) → next cron emits `alerta tipo_alerta='cupo_count_drift'`.
- (RED) Cross-branch report: SELECT returns one row per (branch, tipo_vehiculo) triple with vigente cupo + computed count + percentage.
- (RED) CSV export: triggers `log_transaccional accion='reporte_ocupacion_exportado'`.
- (RED) ON DELETE RESTRICT: cannot delete `tipo_vehiculo` while `cantidad_vehiculos_sucursal` references it.

## 10. Implementation Tasks
- [x] F1.x Schema + UNIQUE partial index.
- [x] F1.x Onboarding seed (4 placeholder rows per branch).
- [ ] IT-2.x: `api_admin /cantidad-vehiculos-sucursal` (POST, PATCH, GET list, GET detail, GET cross-branch, GET ocupacion).
- [ ] IT-2.x: parametrization push on cupo change.
- [ ] IT-2.x: `parkos_core/operacion/cupo_validator.py::check()` (used by `api_sucursal /ingresos`).
- [ ] IT-2.x: `workers/cupos/reconciler.py` (cron, hourly; detects drift).
- [ ] Sprint 5: `cupo_count_cache` materialized table for fast snapshot comparison (current: log-based).
- [ ] Sprint 5: `registro` JSON on `cantidad_vehiculos_sucursal` for `strict_mode` and `max_overflow_pct` config.
- [ ] IT-2.x: `web_admin/CantidadVehiculosForm`, `CantidadVehiculosGrid`, `Reportes/OcupacionCrossBranch`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Cupo exhausted frequently (operational reality) | Med | `cupo_lleno` alerts drive admin to investigate; expansion or traffic redirection |
| Count drift due to bugs (orphan ingresos) | Low | `cupo_reconciler` cron detects and alerts; admin can manually fix via `anulaciones` |
| Concurrent ingreso race (two operators POST simultaneously when count is N-1) | Low | `SELECT FOR UPDATE` on the count query OR atomic increment using `pg_advisory_xact_lock` per (sucursal, tipo_vehiculo); both serialize |
| Subscriber rotation policy ambiguity | Med | Documented in `uc.ingreso.subscriber-rotacion-cupo-agotado`; subscriber can enter via rotation even if branch cupo full (special case) |
| Admin reduces cupo below current count | Med | Validation rejects: `new_cantidad >= COUNT(ingreso activos for triple)`; otherwise 422 |
| Branch boot before parametrization pulled | Med | `cupo_validator` returns "cupo unknown" if no vigente row; operator sees warning; admin must push parametrization |

## 12. Open Questions
- (a) Strict mode vs warn-only per branch: currently always strict; sprint 5 may add `registro.strict_mode` boolean to allow overflow with warning.
- (b) Overflow tolerance: e.g., allow 110% of cupo with warning instead of rejection? Sprint 5 candidate.
- (c) Cupo per time-of-day: night vs day quotas? Out of MVP; sprint 5 may add.
- (d) Subscriber bypass of branch cupo: per `uc.ingreso.subscriber-rotacion-cupo-agotado`, subscriber enters via rotation (as casual, charged per visit) when subscription cupo is full. Should branch cupo also be bypassed? Currently NO — subscriber with subscription rotation still gets rejected if branch is full. Sprint 5 may add an override flag.
- (e) Cross-branch shared cupo (e.g., a customer can use cupo at any branch in the same region): out of MVP; sprint 5.
- (f) `cupo_count_cache` materialization: derive from `log_transaccional` snapshot vs explicit table. Sprint 5 decision.
- (g) Reconciler interval: hourly is current default; could be more frequent (every 15 min) for high-traffic branches.
