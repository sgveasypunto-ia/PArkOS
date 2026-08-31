# PRD: costos_servicios (T28)

> **SNAPSHOT SOURCE** — service cost catalog (`reimpresion_ticket`, `segunda_via_factura`, `certificados`, etc.). Every service's `costo` is COPIED into `reimpresion_ticket.costo_aplicado` at the moment the service is requested. The catalog row can be versioned, expired, or deleted later; the snapshot row is IMMUTABLE. Distinct from `facturas` snapshots: this is for ancillary services charged separately from the main parking fee.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration_plan.md)
- **Meta-PRD-00 Scaffold**: `_meta/00_scaffold.md`
- **Meta-PRD-01 Models**: `_meta/01_models.md`
- **Meta-PRD-02 Jobs**: `_meta/02_jobs_queries.md`
- **Meta-PRD-03 APIs**: `_meta/03_apis_queries.md`

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: `_shared/uuid-v4-strategy.md`
- **SOLID Principles**: `_shared/solid-principles.md`
- **CodeGraph Usage**: `_shared/codegraph-usage.md`
- **Layer Impact Map**: `_shared/layer-impact-map.md`
- **FK Naming Convention**: `_shared/fk-naming-convention.md`
- **Workflow Chains**: `_shared/workflow-chains.md` — *n/a for this `[V]` non-workflow table*
- **References Index**: `_shared/references.md`

## 1. Metadata
- **Table name**: `prod.costos_servicios`
- **SQL name**: `costos_servicios` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema, seeded) + IT-2 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 4 use cases covering admin CRUD, snapshot into reimpresion_ticket, retroactive update rule, and branch display current cost)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `concepto` unique.

## 3. SOLID Atomic Breakdown
- **S**: "one service cost definition".
- **O**: new columns via migration.
- **I**: admin CRUD.
- **D**: `parkos_core/models/V/costos_servicios.py`.
- **Atomic**: INSERT, UPDATE.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `reimpresion_ticket.uuid_costo_servicio` | `\|\|--o{` | snapshot per reimpresion |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Seed |
| UPDATE | YES (archive old) | Inside TX + `log_transaccional` |
| DELETE | NO | RESTRICT |

## 6. CodeGraph Dependencies
- `api_admin/routers/costos-servicios.py`.

## 7. Use Cases enabled by this table

The `costos_servicios` table is the **catalog of ancillary service costs** (`reimpresion_ticket`, `segunda_via_factura`, `certificados`, etc.). Distinct from `tarifas_sucursal` (the main parking fee) and `impuestos`/`otros_cobros` (charges that go on the main factura). These are services charged SEPARATELY, typically via a dedicated `reimpresion_ticket` workflow. Like the other snapshot sources, the `costo` is COPIED into `reimpresion_ticket.costo_aplicado` at the moment of the service — the catalog row can change later; the snapshot row is immutable. Use cases below describe admin CRUD, the snapshot into `reimpresion_ticket`, the retroactive update rule (admin changes a cost — does it affect past reimpresiones? NO), and the branch display. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.costos-servicios.admin-crud-create-or-version`

Cloud admin manages the `costos_servicios` catalog. New services are added as the business evolves — e.g., adding `segunda_via_factura` for duplicate invoice request or `certificado_no_adeudo` for proof of no-debt certificate. Updates create a new `[V]` version (archive old with `vigente_hasta=NOW()`, INSERT new). Parametrization push delivers the new version to all branches.

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='administrar_catalogos'`; the `concepto` is unique (DB constraint); `costo >= 0` (free reimpresion is allowed — sprint 5 nuance).

**Steps**:
1. Admin opens `web_admin/Catalogos/CostosServicios`, clicks `New`.
2. Frontend POSTs `api_admin /costos-servicios` with `{concepto='segunda_via_factura', costo=5000, tipo_calculo='fijo', vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario`; rejects 403 if missing.
4. Backend SELECTs current vigentes; validates UNIQUE on `concepto` (rejects 409 if duplicate).
5. Backend validates business consistency: `costo >= 0`; `tipo_calculo='fijo'` (only fixed fees for MVP; percentage-based service fees are sprint 5).
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
7. INSERT `costos_servicios` row (`uuid=server-generated`, `concepto`, `costo`, `tipo_calculo`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
8. INSERT `log_transaccional` (`accion='costo_servicio_creado'`, `tabla_afectada='costos_servicios'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=null`, `datos_nuevos=$service_snapshot`).
9. `queue_processor.enqueue('costos_servicios', $new_uuid, $snapshot)` → parametrization push.
10. Backend returns `{new_uuid}`.
11. Branch receives parametrization; UPSERT new row. New service appears in `web_sucursal/ReimpresionForm` service list.

**Tables touched (writes)**: `costos_servicios` (1 row), `log_transaccional` (1 row), `sync_queue` (1 parametrization item).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `costos_servicios` (uniqueness), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `costos_servicios` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `costos_servicios.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers the new service to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `costos_servicios` (uniqueness), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `costos_servicios` (the new service), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: the FK from `reimpresion_ticket.uuid_costo_servicio` to `costos_servicios.uuid` is the SNAPSHOT REFERENCE — it points to the service DEFINITION (which is versioned), while the snapshot row carries `costo_aplicado` (the value at the moment of the service).
- Related: see T38 (`reimpresion_ticket`) for the snapshot use case 7.2 below.

### 7.2 Use Case: `uc.costos-servicios.snapshot-into-reimpresion-ticket`

Customer loses their ticket and asks for a reprint. Operator opens `FacturaDetail` in `web_sucursal`, clicks `Reimprimir`. Backend SELECTs `costos_servicios` vigente for `concepto='reimpresion_ticket'`, INSERTs `reimpresion_ticket` with `costo_aplicado=$current_costo` (the **SNAPSHOT** value), INSERTs `factura_pagos` for the cost (or waives if `costo=0`), INSERTs `log_transaccional`.

**Actor**: operator (branch)

**Pre-conditions**: branch has parametrized vigentes `costos_servicios`; `facturas` row exists with `uuid_factura_electronica` populated (gate per T05 use case 7.5 — `reimpresion_ticket` disabled before sync-back); `costos_servicios` for `concepto='reimpresion_ticket'` is vigente.

**Steps**:
1. Customer asks for a reprint. Operator opens `FacturaDetail`, clicks `Reimprimir`.
2. Frontend checks the gate: `factura.uuid_factura_electronica IS NOT NULL AND factura.dian_response_at IS NOT NULL`. If NOT ready → button is disabled with tooltip "Esperando SyncBackEvent de DIAN".
3. If ready: Frontend POSTs `api_sucursal /reimpresion-ticket` with `{uuid_factura, motivo='cliente_perdio_ticket', uuid_usuario=$operator}`.
4. Backend SELECTs vigente `costos_servicios` WHERE `concepto='reimpresion_ticket' AND vigente_hasta IS NULL`. Returns 1 row with `costo=2000`.
5. Backend opens TX; SELECT chain anchor from `log_transaccional`.
6. INSERT `reimpresion_ticket` workflow chain root (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$ingreso_uuid`, `uuid_usuario=$operator_uuid`, `uuid_costo_servicio=$service.uuid`, `costo_aplicado=$service.costo` ← **SNAPSHOT VALUE**, `uuid_factura=$factura_uuid`, `motivo='cliente_perdio_ticket'`, `uuid_padre=NULL`, `estado='cobrada'`).
7. If `costo > 0`: INSERT `factura_pagos` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_factura=$factura_uuid`, `medio_pago='efectivo'` (default; operator may override to `datafono`), `valor=$service.costo`, `referencia=null`, `timestamp_evento=NOW()`).
8. INSERT `log_transaccional` (`accion='reimpresion_cobrada'`, `tabla_afectada='reimpresion_ticket'`, `uuid_registro_afectado=$reimpresion_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_nuevos={costo_aplicado: $snapshot, factura_uuid, motivo}`).
9. `queue_processor.enqueue('reimpresion_ticket', $uuid, $snapshot)`.
10. Operator prints duplicate receipt.
11. If a subsequent cancel of the the invoice is needed (e.g., wrong client): INSERT new `reimpresion_ticket` row with `uuid_padre=$root, estado='anulada'`. INSERT `log_transaccional`. The state vigente becomes `anulada`.

**Tables touched (writes)**: `reimpresion_ticket` (workflow chain root, 1 or 2 rows), `factura_pagos` (1 row, only if `costo > 0`), `log_transaccional` (1 row), `sync_queue` (1+ items).
**Tables touched (reads)**: `costos_servicios` (vigente for SNAPSHOT), `facturas` (gate check), `factura_electronica` (DIAN status), `reimpresion_ticket` (dedup check for existing chain root), `log_transaccional` (chain anchor), `usuarios` (operator), `sucursal` (tenant).
**FKs traversed**: `reimpresion_ticket.uuid_costo_servicio` → `costos_servicios.uuid` (FK to SPECIFIC version); `reimpresion_ticket.uuid_factura` → `facturas.uuid`; `reimpresion_ticket.uuid_ingreso` → `ingreso.uuid`; `reimpresion_ticket.uuid_usuario` → `usuarios.uuid`; `reimpresion_ticket.uuid_sucursal` → `sucursal.uuid`; `reimpresion_ticket.uuid_padre` → `reimpresion_ticket.uuid` (self-reference, workflow chain for `anulada` transition). `factura_pagos.uuid_factura` → `facturas.uuid`; `factura_pagos.uuid_sucursal` → `sucursal.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `reimpresion_ticket.uuid`.
**Sync behavior**:
- Branch → cloud: YES — `reimpresion_ticket` + `factura_pagos` + `log_transaccional` push via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact for this specific action).
- DIAN trigger: NO (reimpresion is a local-only event — it doesn't generate a new e-factura).
- Hash chain impact: YES — branch chain extends by 1-2 rows; cloud chain extends correspondingly on receipt.
**Integration**:
- Reads from: `costos_servicios` (vigente for SNAPSHOT), `facturas` (gate), `factura_electronica` (DIAN status), `reimpresion_ticket` (dedup), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
- Writes to: `reimpresion_ticket` (workflow chain), `factura_pagos` (charge), `log_transaccional`, `sync_queue`.
- Cross-cutting: same canonical snapshot semantic as T26/T27/T14. The `reimpresion_ticket` row carries TWO fields: `uuid_costo_servicio` (FK to version) AND `costo_aplicado` (snapshot value). Both are needed for probatory integrity.
- Related: see T38 (`reimpresion_ticket`) for the full workflow chain lifecycle (`cobrada` → `anulada` transitions); T05 use case 7.5 for the `reimpresion_ticket` gate on sync-back.

### 7.3 Use Case: `uc.costos-servicios.retroactive-update-no-effect-on-past-reimpresiones`

Cloud admin updates a service cost — e.g., `reimpresion_ticket` from $2000 to $3000 effective next month. Admin creates a NEW version (`vigente_desde=$effective_date`) and EXPIRES the current version. **Existing `reimpresion_ticket` rows are UNAFFECTED** — they still FK to the OLD version's UUID and carry `costo_aplicado=$2000` (the snapshot). New reimpresiones after $effective_date use the new $3000 cost.

**Actor**: admin (cloud)

**Pre-conditions**: service exists and is vigente; admin has `permiso='administrar_catalogos'`; the change is a cost update (concepto stays the same); historical `reimpresion_ticket` rows exist referencing the current version.

**Steps**:
1. Admin opens `web_admin/Catalogos/CostosServicios/{uuid}`, edits `costo` from 2000 to 3000. Sets `vigente_desde=$effective_date`.
2. Frontend PATCHes `api_admin /costos-servicios/{uuid}` with `{costo=3000, vigente_desde=$effective_date}`.
3. Backend validates `permisos_usuario`; rejects 403 if missing.
4. Backend SELECTs current vigente service with `SELECT FOR UPDATE`.
5. Backend opens TX; SELECT chain anchor from `log_transaccional`.
6. UPDATE current vigente row SET `vigente_hasta=$effective_date` (archive old).
7. INSERT new `costos_servicios` row (`uuid`, same `concepto='reimpresion_ticket'`, `costo=3000`, `vigente_desde=$effective_date`).
8. INSERT `log_transaccional` (`accion='costo_servicio_actualizado'`, ..., `datos_anteriores={costo: 2000, ...}`, `datos_nuevos={costo: 3000, ...}`).
10. `queue_processor.enqueue` parametrization push.
11. Branch receives parametrization; UPSERT new row, UPDATE local old row.
12. **Historical `reimpresion_ticket` rows are UNAFFECTED**: they still FK to the OLD version's UUID and carry `costo_aplicado=2000`. This is the **retroactive update rule**: catalog changes do NOT retroactively affect historical snapshots. DIAN compliance preserved.
13. **New reimpresiones** (use case 7.2) use the vigente service at the moment of the service: before $effective_date → 2000; on/after → 3000.

**Tables touched (writes)**: `costos_servicios` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `costos_servicios` (current state), `reimpresion_ticket` (count of existing snapshots — informational), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `costos_servicios` has NO outgoing FKs. `reimpresion_ticket.uuid_costo_servicio` → `costos_servicios.uuid` (REFERENCES the version vigente at the service moment). `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `costos_servicios.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers new + archived version to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `costos_servicios` (current state), `reimpresion_ticket` (existing snapshots), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `costos_servicios` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **canonical retroactive update rule** for snapshot sources. The same pattern applies to T26 (impuestos), T27 (otros_cobros), and T14 (tarifas_sucursal) — admin changes do NOT retroactively affect historical snapshots. This is critical for DIAN compliance: a customer who paid $2000 for a reimpresion yesterday should NOT be retroactively charged an extra $1000 because admin updated the cost today.
- Related: see T26 use case 7.2 (impuestos versioning), T27 use case 7.2 (otros_cobros versioning), T14 use case 7.1 (tarifas_sucursal versioning) for the parallel patterns.

### 7.4 Use Case: `uc.costos-servicios.branch-displays-current-cost-before-charging`

Operator at the booth is about to issue a reimpresion. Before confirming, the system displays the **current** `costo` for the service (e.g., "Costo actual de reimpresion: $3,000. ¿Confirma?"). This is a READ against `costos_servicios` vigente — does NOT extend the hash chain per SOLID I. The operator sees the LIVE cost, not the snapshot cost (the snapshot is created when the reimpresion is confirmed in use case 7.2).

**Actor**: operator (branch)

**Pre-conditions**: branch has parametrized vigentes `costos_servicios`; operator is about to issue a reimpresion.

**Steps**:
1. Operator opens `web_sucursal/FacturaDetail`, clicks `Reimprimir`. Frontend fires `GET api_sucursal /costos-servicios?vigente_only=true&concepto=reimpresion_ticket` (or all vigentes if multi-service preview).
2. Backend SELECTs `costos_servicios` WHERE `concepto='reimpresion_ticket' AND vigente_hasta IS NULL`. Returns the row with `costo=$current`.
3. Frontend displays preview modal: "Servicio: reimpresion_ticket. Costo actual: $X. ¿Confirma?". Operator clicks `Confirm` or `Cancel`.
4. If `Confirm`: backend proceeds with use case 7.2 (snapshot + chain extension).
5. If `Cancel`: nothing happens. No writes.

**Tables touched (writes)**: NONE for the preview itself.
**Tables touched (reads)**: `costos_servicios` (vigente lookup).
**FKs traversed**: `costos_servicios` has NO FKs.
**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO (no parametrization impact for the preview).
- DIAN trigger: NO.
- Hash chain impact: **NO** — per SOLID I, reads do not extend the chain. The chain extends ONLY when the operator confirms (use case 7.2).

**Integration**:
- Reads from: `costos_servicios` (vigente for display).
- Writes to: NONE.
- Cross-cutting: this is the canonical READ path for the catalog — display current values without extending the chain. The WRITE path (snapshot) is use case 7.2.
- Related: see T14 use case 7.2 for the parallel `tarifas_sucursal` vigente lookup at ingreso preview (same pattern, same SOLID I reasoning).

## 8. Layer-by-Layer Impact
Layers: 1, 6, 13, 24, 31.

## 9. RED Tests
- (RED) `concepto` unique.
- (RED) Snapshot takes costo at reimpresion time.

## 10. Implementation Tasks
- [x] F1.x Seed.
- [ ] IT-2.x: admin CRUD.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Cost change | Low | Snapshot at reimpresion time |

## 12. Open Questions
- (a) Dynamic cost per branch? Currently global.