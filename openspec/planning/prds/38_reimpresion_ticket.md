# PRD: reimpresion_ticket (T38)

> `[L-W]` workflow chain for ticket reprints. Each state transition is a NEW row chained by `uuid_padre`. States: `cobrada` (root) → `anulada` (only if cancelled). **Gated on `facturas.uuid_factura_electronica IS NOT NULL`** — reprint is BLOCKED until cloud SyncBackEvent confirms the official DIAN number (the e-factura is the legal document; reprinting without it would print an invalid number). `costo_aplicado` is a SNAPSHOT of `costos_servicios.costo` at the moment of reprint — preserved across catalog changes.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — **relevant** (chain via `uuid_padre`)
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.reimpresion_ticket`
- **SQL name**: `reimpresion_ticket` (with `prod` schema)
- **Enforcement level**: `[L-W]` workflow chain (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (DIAN compliance — reprints reference the original e-factura)
- **Hash chain**: NO (workflow chain, not source-of-truth for compliance)
- **Origin**: F1 (schema + REVOKE + trigger) + IT-9 (writes per reprint workflow)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_padre` is self-FK for workflow chaining: 0..1 (NULL on root, $previous_uuid on transitions).
- `uuid_costo_servicio` is FK for traceability to the catalog (similar to `factura_impuestos.uuid_impuesto`), but `costo_aplicado` is the SNAPSHOT — independent of catalog changes.
- Travel: branch-origin rows travel to cloud via `sync_queue`. Cloud receives and INSERTs verbatim.
- **Workflow chain naming**: this table uses `uuid_padre` (literal, NOT `uuid_reimpresion_padre` per AGENTS.md comment). Sprint 5 may rename for consistency with `anulaciones` / `reclamos` / `alerta` if naming convention changes.

## 3. SOLID Atomic Breakdown
- **S**: "one ticket reprint event or workflow transition" — INSERT in same TX as the cost `factura_pagos` row + log_transaccional.
- **O**: extensible via migration; new workflow states (`cobrada` → `anulada` only today; sprint 5 may add `duplicado_por_dano` etc.).
- **I**: branch operator API (writer — POST `/reimpresion-ticket`); admin read API (ReimpresionesList, paginated); admin anulación endpoint (POST `/reimpresion-ticket/{uuid}/anular`).
- **D**: `parkos_core/facturacion/reimpresion_writer.py::write_reimpresion(uuid_factura, uuid_costo_servicio, motivo, uuid_usuario, uuid_padre=None)` — the ONLY writer. Validates the gating condition `facturas.uuid_factura_electronica IS NOT NULL` BEFORE INSERT.
- **Atomic**: INSERT only (workflow chain). REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch |
| `uuid_ingreso` | `prod.ingreso.uuid` | exactly one (NOT NULL) | RESTRICT | the original ingreso |
| `uuid_usuario` | `prod.usuarios.uuid` | exactly one (NOT NULL) | RESTRICT | the operator who issued the reprint |
| `uuid_costo_servicio` | `prod.costos_servicios.uuid` | exactly one (NOT NULL) | RESTRICT | the cost catalog (for traceability; `costo_aplicado` is the snapshot) |
| `uuid_factura` | `prod.facturas.uuid` | exactly one (NOT NULL) | RESTRICT | the billed factura (where cost is charged) |
| `uuid_padre` | `prod.reimpresion_ticket.uuid` | 0..1 (nullable, self-ref) | RESTRICT | workflow chain link: `anulada` transitions point to the original `cobrada` row |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| (none direct; the workflow is queried via `uuid_padre` chain + JOIN to `facturas`, `costos_servicios`, `ingreso`, `usuarios`) | | | |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `reimpresion_writer.py::write_reimpresion()` per reprint or per transition |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for DIAN retention |

**Special rules**:
- **Workflow chain**: root has `uuid_padre=NULL, estado='cobrada'`. Transition to `anulada` has `uuid_padre=$root.uuid, estado='anulada'`. State vigente = last row in chain per `uuid_ingreso` (or per root UUID).
- **Snapshot semantic**: `costo_aplicado` is a COPY of `costos_servicios.costo` at the moment of reprint. NOT a live FK cascade.
- **Gating condition**: `facturas.uuid_factura_electronica IS NOT NULL` MUST be true BEFORE INSERT. If NULL (offline mode, SyncBackEvent not yet received): return 409 `reimpresion_requiere_e_factura`. The original `facturas.uuid_factura_electronica` is set by cloud SyncBackEvent after DIAN dispatch (T03).
- **Per .mmd**: "El operador nunca puede dejar la reimpresión gratuita" — every reprint has a non-zero `costo_aplicado` billed via a new `factura_pagos` row.

## 6. CodeGraph Dependencies
- `parkos_core/facturacion/reimpresion_writer.py::write_reimpresion()` (sole writer, validates gating).
- `api_sucursal/routers/reimpresion-ticket.py::POST /reimpresion-ticket` (operator endpoint).
- `api_admin/routers/reimpresion-ticket.py::POST /reimpresion-ticket/{uuid}/anular` (admin anulación).
- `api_admin/routers/reimpresion-ticket.py::GET /reimpresion-ticket` (paginated, filterable).
- `api_admin/routers/reimpresion-ticket.py::GET /reimpresion-ticket/{uuid}/chain` (workflow chain view).
- `web_sucursal/ReimpresionTicketForm` (gated on SyncBackEvent; red banner if not yet received).
- `web_sucursal/ReimpresionesHistory` (own-branch reprint list).
- `web_admin/ReimpresionesList` (cross-branch reprint dashboard).
- `web_admin/ReimpresionesList/{uuid}/Detail` (single reprint detail with workflow chain).

## 7. Use Cases enabled by this table

The `reimpresion_ticket` table is the **L-W workflow** for ticket reprints. Each reprint is a row with `estado='cobrada'`; if the reprint is later annulled, a new row is inserted with `uuid_padre=$original, estado='anulada'`. **Gated on `facturas.uuid_factura_electronica IS NOT NULL`** — reprints are BLOCKED until cloud SyncBackEvent confirms the official DIAN number. `costo_aplicado` is the SNAPSHOT of `costos_servicios.costo` at the moment of reprint. **Manual operator input** for motivo; the reprint cost is from the catalog.

### 7.1 Use Case: `uc.reimpresion-ticket.operator-requests-reprint-blocked-when-no-e-factura`

**Actor**: operator (branch)

**Real-world action**: Customer requests a reprint of their invoice. Operator opens `web_sucursal/ReimpresionTicketForm`, selects the `uuid_factura`, types the motivo. Backend validates the gating condition: `SELECT uuid_factura_electronica FROM facturas WHERE uuid=$uuid_factura`. If NULL (offline mode, SyncBackEvent not yet received): return 409 `reimpresion_requiere_e_factura`. Operator UI shows a red banner: "La factura aún no tiene número DIAN oficial. Espere la confirmación de la nube o contacte al admin."

**Steps**:
1. Operator opens `web_sucursal/ReimpresionTicketForm`. Form lists recent `facturas` rows for the operator's branch with `preliminar` badge if `uuid_factura_electronica IS NULL`.
2. Operator selects `uuid_factura` (a factura from 2 hours ago, offline mode at the time of issue).
3. Operator types `motivo='Cliente perdió el ticket original'`.
4. Frontend POSTs `api_sucursal /reimpresion-ticket` with `{uuid_factura, motivo}`.
5. Backend SELECTs `facturas WHERE uuid=$uuid_factura`. Returns `uuid_factura_electronica=NULL`.
6. Backend returns 409 Conflict `{detail: 'reimpresion_requiere_e_factura', uuid_factura, message: 'La factura no tiene número DIAN oficial aún.'}`.
7. Operator UI shows the red banner; the reprint button is disabled with tooltip "Esperando confirmación DIAN".
8. Operator may escalate to admin via `reclamos` (T40) or wait for the SyncBackEvent to arrive.

**Tables touched (writes)**: NONE (the request is rejected before any INSERT).
**Tables touched (reads)**: `facturas` (gating check), `permisos_usuario` (RBAC for reprint endpoint), `costos_servicios` (vigente for cost preview), `log_transaccional` (chain anchor if INSERT succeeded, but here it doesn't).
**FKs traversed**: `facturas.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (request rejected client-side).
- Cloud → branch: NO (this is branch-internal rejection).
- DIAN trigger: NO.
- Hash chain impact: NO (no INSERT).

**Integration with other tables**:
- Reads from: `facturas` (gating check), `permisos_usuario`, `costos_servicios`.
- Writes to: NONE.
- Cross-cutting: this is the **gating failure** path. The system enforces the .mmd invariant: "El operador nunca puede dejar la reimpresión gratuita" — and by extension, never reprint without the official DIAN number (which would print an invalid number).
- Related: T03 (`factura_electronica`) covers the SyncBackEvent flow that sets `facturas.uuid_factura_electronica`.

### 7.2 Use Case: `uc.reimpresion-ticket.operator-reprint-first-time-after-syncback`

**Actor**: operator (branch)

**Real-world action**: SyncBackEvent has arrived; `facturas.uuid_factura_electronica` is now populated. Operator opens `web_sucursal/ReimpresionTicketForm`, selects the `uuid_factura` (now WITHOUT preliminar badge), types motivo, confirms. Backend validates gating (now PASSES), INSERTs `reimpresion_ticket` root row with `estado='cobrada', uuid_padre=NULL`, INSERTs `factura_pagos` for the cost, INSERTs `log_transaccional`, enqueues for sync.

**Steps**:
1. Operator opens `web_sucursal/ReimpresionTicketForm`. Form now shows the factura WITHOUT preliminar badge (gating passed).
2. Operator selects `uuid_factura`, types `motivo='Cliente perdió el ticket original'`.
3. Frontend POSTs `api_sucursal /reimpresion-ticket` with `{uuid_factura, motivo}`.
4. Backend SELECTs `facturas WHERE uuid=$uuid_factura` — `uuid_factura_electronica IS NOT NULL` ✓.
5. Backend SELECTs vigente `costos_servicios WHERE concepto='reimpresion_ticket' AND vigente_hasta IS NULL` → `costo=$X`.
6. Backend validates RBAC: `permiso='reimprimir_ticket'`.
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
8. Backend SELECTs `ingreso.uuid FROM facturas WHERE uuid=$uuid_factura` → `uuid_ingreso`.
9. INSERT `reimpresion_ticket` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$ingreso_uuid`, `uuid_usuario=$operator`, `uuid_costo_servicio=$costo_servicio_uuid`, `costo_aplicado=$X` (SNAPSHOT), `uuid_factura=$factura_uuid`, `motivo='Cliente perdió el ticket original'`, `uuid_padre=NULL` (root of chain), `timestamp_evento=NOW()`, `estado='cobrada'`, `fecha_retencion_hasta=$created_at + 5_years`).
10. INSERT `factura_pagos` row for the reprint cost: `uuid_factura=$factura_uuid, uuid_sucursal=$branch, medio_pago='efectivo', valor=$X, referencia=NULL, timestamp_evento=NOW()` (per .mmd, the cost is always charged).
11. INSERT `log_transaccional` (`accion='reimpresion_cobrada'`, `tabla_afectada='reimpresion_ticket'`, `uuid_registro_afectado=$reimpresion_uuid`, `uuid_usuario=$operator`, `uuid_sucursal=$branch`, `datos_nuevos={uuid_factura, uuid_costo_servicio, costo_aplicado, motivo, uuid_padre:null}`).
12. `queue_processor.enqueue('reimpresion_ticket', $uuid, $snapshot)` + `enqueue('factura_pagos', $pago_uuid, $snapshot)`.
13. Operator UI shows: "Reimpresión cobrada: $X. Imprimiendo..." → triggers print dialog with the official DIAN number on the reprinted ticket.

**Tables touched (writes)**: `reimpresion_ticket` (1 row, root), `factura_pagos` (1 row, for cost), `log_transaccional` (1 row), `sync_queue` (2 items).
**Tables touched (reads)**: `facturas` (gating + uuid_ingreso), `costos_servicios` (vigente for cost), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `reimpresion_ticket.uuid_sucursal` → `sucursal.uuid`; `reimpresion_ticket.uuid_ingreso` → `ingreso.uuid`; `reimpresion_ticket.uuid_usuario` → `usuarios.uuid`; `reimpresion_ticket.uuid_costo_servicio` → `costos_servicios.uuid` (traceability FK); `reimpresion_ticket.uuid_factura` → `facturas.uuid`; `factura_pagos.uuid_factura` → `facturas.uuid`; `factura_pagos.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `reimpresion_ticket.uuid`.

**Sync behavior**:
- Branch → cloud: YES (reimpresion + factura_pagos propagate).
- Cloud → branch: NO.
- DIAN trigger: NO (reimpresion_ticket is NOT a new e-factura; it reprints an existing one).
- Hash chain impact: YES — branch chain extends by 2 rows (reimpresion + pago); cloud chain extends correspondingly.

**Integration with other tables**:
- Reads from: `facturas` (gating + uuid_ingreso), `costos_servicios` (vigente), `permisos_usuario` (RBAC), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `reimpresion_ticket` (root row), `factura_pagos` (cost), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **reprint first-time** flow. The workflow chain root has `uuid_padre=NULL`. The cost is always charged via `factura_pagos`. The snapshot `costo_aplicado` is preserved even if `costos_servicios.costo` is updated.
- Related: T03 (`factura_electronica`) covers the SyncBackEvent that sets the gating condition; T36 (`factura_pagos`) covers the cost payment.

### 7.3 Use Case: `uc.reimpresion-ticket.operator-reprint-second-time-extends-chain`

**Actor**: operator (branch)

**Real-world action**: Customer comes back ANOTHER time requesting another reprint of the same invoice (e.g., the second reprint was lost too). Operator opens `ReimpresionTicketForm`, selects the SAME `uuid_factura` (or maybe a different one — could be any factura). Backend INSERTs a NEW `reimpresion_ticket` row. The previous reprint is NOT the chain parent — the `uuid_padre` field in this table refers to the **anulación** relationship, not the reprint-of-reprint relationship. Reprints are independent rows unless annulled.

**Steps**:
1. Operator opens `web_sucursal/ReimpresionTicketForm`, selects `uuid_factura=$same_factura`, types motivo.
2. Frontend POSTs `api_sucursal /reimpresion-ticket` with `{uuid_factura, motivo}`.
3. Backend validates gating (same as use case 7.2).
4. Backend SELECTs existing reimpresion count: `SELECT COUNT(*) FROM reimpresion_ticket WHERE uuid_factura=$uuid_factura`. Returns N (e.g., 1 from the first reprint).
5. Backend INSERTs NEW `reimpresion_ticket` row with `uuid_padre=NULL` (this is a SEPARATE reprint, not a workflow transition). The chain only extends if the reprint is annulled.
6. INSERT `factura_pagos` for the cost (independent of the first reprint's payment).
7. INSERT `log_transaccional`.
8. `queue_processor.enqueue`.
9. Operator UI shows: "2da reimpresión cobrada: $X."

**Tables touched (writes)**: `reimpresion_ticket` (new root row), `factura_pagos` (new payment row), `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `facturas` (gating), `costos_servicios` (vigente), `permisos_usuario`, `log_transaccional`.

**Sync behavior**: per use case 7.2.
**Hash chain impact**: YES.

**Integration with other tables**:
- Reads from: per use case 7.2.
- Writes to: `reimpresion_ticket` (new root row — independent chain), `factura_pagos`, `log_transaccional`, `sync_queue`.
- Cross-cutting: **CRITICAL clarification**: this table's `uuid_padre` is for ANULACIÓN workflow transitions ONLY, not for reprint-of-reprint. Multiple reprints of the same factura are independent root rows; only anulación creates a child row. Sprint 5 may add explicit `uuid_reimpresion_anterior` column if the business wants to track reprint history per factura.

### 7.4 Use Case: `uc.reimpresion-ticket.admin-anula-reprint-extends-chain-to-anulada`

**Actor**: admin (cloud)

**Real-world action**: Admin clicks `Anular Reimpresion` in `web_admin/ReimpresionesList/{uuid}/Detail`. Backend SELECTs the latest chain row for the `uuid` (root of the chain, or the most recent transition). INSERTs a NEW `reimpresion_ticket` row with `uuid_padre=$latest.uuid, estado='anulada'`, INSERTs `log_transaccional`, enqueues for sync. The reprint is now annulled: any future query for "is this reprint valid?" returns the latest chain row (`estado='anulada'`).

**Steps**:
1. Admin opens `web_admin/ReimpresionesList/{uuid}` (the ROOT UUID of the reprint chain).
2. Admin clicks `Anular Reimpresion`.
3. Frontend POSTs `api_admin /reimpresion-ticket/{uuid}/anular` with `{motivo}`.
4. Backend SELECTs `reimpresion_ticket` where `uuid=$uuid OR uuid_padre=$uuid` ordered by `created_at DESC LIMIT 1` — this is the latest chain row (root if first time annulling).
5. Backend validates RBAC: `permiso='anular_reimpresion'`.
6. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch_of_reprint`.
7. INSERT new `reimpresion_ticket` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$same_ingreso`, `uuid_usuario=$admin`, `uuid_costo_servicio=$same_costo_servicio`, `costo_aplicado=$same_snapshot`, `uuid_factura=$same_factura`, `motivo='Anulación: $admin_motivo'`, `uuid_padre=$latest.uuid` (CHAIN LINK), `timestamp_evento=NOW()`, `estado='anulada'`, `fecha_retencion_hasta=$created_at + 5_years`).
8. INSERT `log_transaccional` (`accion='reimpresion_anulada'`, `tabla_afectada='reimpresion_ticket'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin`, `uuid_sucursal=$branch`, `datos_anteriores={estado:'cobrada', uuid_padre:$latest_uuid}`, `datos_nuevos={estado:'anulada', uuid_padre:$latest_uuid}`).
9. `queue_processor.enqueue('reimpresion_ticket', $new_uuid, $snapshot)`.
10. Branch receives the parametrization (sprint 5: chain replication pattern); UPSERTs the new row locally. Branch UI updates: "Reimpresión anulada." Red badge.
11. Admin sees the chain in `web_admin/ReimpresionesList/{uuid}/chain` — root `cobrada` → transition `anulada`. The chain has 2 rows now.

**Tables touched (writes)**: `reimpresion_ticket` (1 new chain row, `estado='anulada'`), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `reimpresion_ticket` (previous chain row), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `reimpresion_ticket.uuid_padre` → `reimpresion_ticket.uuid` (workflow self-FK); other FKs per parent row.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — chain replication; branch UPSERTs the new row.
- DIAN trigger: NO (anulación is internal; the original e-factura is still valid).
- Hash chain impact: YES — cloud chain extends by 1 row; branch chain extends by 1 row on parametrization receipt.

**Integration with other tables**:
- Reads from: `reimpresion_ticket` (previous chain row), `permisos_usuario` (RBAC), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `reimpresion_ticket` (new chain row), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **workflow transition**. State vigente is the LAST row in the chain (per `created_at DESC LIMIT 1`). The transition is INSERT-only; the original `cobrada` row is NEVER modified.
- Related: T41 (`alerta`) covers `alerta tipo_alerta='reimpresion_fraudulenta'` if the admin suspects fraud; T40 (`reclamos`) covers customer complaints about reprint charges.

### 7.5 Use Case: `uc.reimpresion-ticket.costo-aplicado-snapshot-survives-catalog-update`

**Actor**: admin (cloud) + system (snapshot semantic invariant)

**Real-world action**: Admin updates `costos_servicios.costo` for `concepto='reimpresion_ticket'` from $2000 to $2500 (effective 2026-07-01). A `reimpresion_ticket` row from 2026-05-15 with `costo_aplicado=$2000` is UNAFFECTED (snapshot semantic). Admin runs an audit query: "Show me all reprints in 2026 that were billed at the OLD $2000 rate" — the answer is the `reimpresion_ticket` rows where `costo_aplicado=$2000`, regardless of the current `costos_servicios.costo`.

**Steps**:
1. Admin opens `web_admin/CostosServiciosDetail/{uuid}`, clicks `Actualizar costo` → types `2000 → 2500`, confirms effective `vigente_desde=2026-07-01`.
2. Frontend PATCHes `api_admin /costos-servicios/{uuid}` with `{costo: 2500, vigente_desde: '2026-07-01'}` (T28 versioning pattern).
3. Backend opens TX; SELECT chain anchor from `log_transaccional`.
4. UPDATE current vigente `costos_servicios` row SET `vigente_hasta='2026-06-30 23:59:59'`.
5. INSERT new `costos_servicios` row with `costo=2500, vigente_desde='2026-07-01', vigente_hasta=NULL`.
6. INSERT `log_transaccional` (`accion='costo_servicio_actualizado'`, `tabla_afectada='costos_servicios'`).
7. `queue_processor.enqueue('costos_servicios', $new_uuid, $new_snapshot)` — parametrization push to all branches.
8. **Existing `reimpresion_ticket` rows are UNAFFECTED**: their `costo_aplicado` snapshot is unchanged. The historical reprint still shows $2000.
9. Admin runs audit query: `SELECT * FROM reimpresion_ticket WHERE uuid_costo_servicio=$costo_uuid AND costo_aplicado=2000 AND created_at < '2026-07-01'` — returns the reprints using the old $2000 rate.
10. The audit confirms: "100 reprints in 2026-Q2 were billed at the old $2000 rate; their `costo_aplicado` snapshots remain at $2000 regardless of the new vigente $2500."

**Tables touched (writes)**: `costos_servicios` (archive old + INSERT new), `log_transaccional` (audit), `sync_queue` (parametrization).
**Tables touched (reads)**: `reimpresion_ticket` (audit query, unchanged), `costos_servicios` (vigente, archived).
**FKs traversed**: `reimpresion_ticket.uuid_costo_servicio` → `costos_servicios.uuid` (traceability); `costos_servicios` (no FKs).

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1-2 rows; branch chain extends on parametrization receipt.

**Integration with other tables**:
- Reads from: `reimpresion_ticket` (audit), `costos_servicios` (vigente, archived).
- Writes to: `costos_servicios` (archive + new), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **snapshot semantic invariant for reprints**. The `costo_aplicado` is FOREVER the value at the moment of reprint. No retroactive re-evaluation, no JOIN cascade. This is the same pattern as `factura_detalle.valor_unitario` (T35) and `factura_impuestos.porcentaje_aplicado` (T37).
- Related: T28 (`costos_servicios`) use case 7.x covers the versioning pattern.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers), 5 (audit constraints — REVOKE), 6 (cloud admin API), 7 (branch API), 8 (Pydantic schemas), 10 (cloud sync worker), 11 (branch sync worker), 12 (sync_queue interop), 13 (web_admin ReimpresionesList), 14 (web_sucursal ReimpresionesHistory + ReimpresionTicketForm), 15 (shadcn UI), 16 (Zustand reprint state), 20 (structlog), 24 (pytest), 28 (docker compose), 33 (DIAN compliance docs).

## 9. RED Tests
- (RED) INSERT `reimpresion_ticket` from `rol_app` → success.
- (RED) UPDATE `prod.reimpresion_ticket` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.reimpresion_ticket` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Gating: POST `/reimpresion-ticket` with `facturas.uuid_factura_electronica IS NULL` → 409 `reimpresion_requiere_e_factura`.
- (RED) Gating passes: POST with `uuid_factura_electronica IS NOT NULL` → 200, INSERT root row.
- (RED) Workflow chain: first row has `uuid_padre=NULL, estado='cobrada'`; transition has `uuid_padre=$root.uuid, estado='anulada'`.
- (RED) State vigente query: `ORDER BY created_at DESC LIMIT 1` returns the latest row.
- (RED) Cost snapshot semantic: update `costos_servicios.costo` after reprint → `reimpresion_ticket.costo_aplicado` is UNCHANGED.
- (RED) Cost always charged: `factura_pagos` row exists for every `reimpresion_ticket` (root or transition).
- (RED) Chain replication: admin anulación cloud-side; branch receives within 30s; chain visible in `web_sucursal`.
- (RED) Multiple reprints of same `uuid_factura` create independent root rows (not chained); only anulación creates child row.
- (RED) `fecha_retencion_hasta = created_at + 5 years`.
- (RED) RBAC: operator without `permiso='reimprimir_ticket'` → 403; admin without `permiso='anular_reimpresion'` → 403.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger.
- [ ] F1.x `reimpresion_writer.py::write_reimpresion()` helper with gating validation.
- [ ] IT-9.x: `api_sucursal/routers/reimpresion-ticket.py::POST /reimpresion-ticket` (operator endpoint).
- [ ] IT-9.x: gating integration with `facturas.uuid_factura_electronica` (set by SyncBackEvent).
- [ ] IT-9.x: automatic `factura_pagos` INSERT for reprint cost.
- [ ] IT-9.x: `api_admin/routers/reimpresion-ticket.py::POST /reimpresion-ticket/{uuid}/anular` (admin endpoint).
- [ ] IT-9.x: `api_admin/routers/reimpresion-ticket.py::GET /reimpresion-ticket` (paginated).
- [ ] IT-9.x: `api_admin/routers/reimpresion-ticket.py::GET /reimpresion-ticket/{uuid}/chain` (workflow chain view).
- [ ] IT-9.x: `web_sucursal/ReimpresionTicketForm` with red banner on gating failure.
- [ ] IT-9.x: `web_sucursal/ReimpresionesHistory` (own-branch reprint list).
- [ ] IT-9.x: `web_admin/ReimpresionesList` (cross-branch reprint dashboard).
- [ ] IT-9.x: `web_admin/ReimpresionesList/{uuid}/Detail` (single reprint detail with workflow chain).
- [ ] Sprint 5: explicit `uuid_reimpresion_anterior` column for reprint-of-reprint history (if business requires).
- [ ] Sprint 5: rename `uuid_padre` to `uuid_reimpresion_padre` for naming consistency (deferred — breaking change).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Operator bypasses gating (UI tampering) | Low | Server validates `facturas.uuid_factura_electronica IS NOT NULL`; UI cannot override |
| Customer loses reprint, requests another → multiple independent root rows | Low | Acceptable per .mmd (each reprint is independent); cost charged each time |
| Admin anulación wrong chain row (e.g., annuls a different reprint by mistake) | Low | UI shows chain visualization; admin must confirm `Anular este` with motivo |
| `costo_aplicado` snapshot diverges from current `costos_servicios.costo` over time | Low | Snapshot semantic is intentional; audit query captures historical state |
| Offline mode extends for days → reprint blocked indefinitely | Low | Admin can manually force `facturas.uuid_factura_electronica` after offline DIAN dispatch via `SyncBackEvent` (T03) |
| Workflow chain grows unbounded (multiple anulaciones of the same reprint) | Low | Each anulación creates ONE chain row; UI shows full chain; typically 2 rows (cobrada → anulada) |
| Cost is always charged — customer disputes | Low | T40 (`reclamos`) covers customer disputes; admin reviews via the workflow chain |

## 12. Open Questions
- (a) Should multiple reprints of the same factura chain via a different mechanism (e.g., `uuid_reimpresion_anterior`)? Sprint 5.
- (b) Should `uuid_padre` be renamed to `uuid_reimpresion_padre` for consistency with `anulaciones` / `reclamos` / `alerta`? Sprint 5 — deferred due to breaking change.
- (c) Refund of reprint cost when annulled: should the `factura_pagos` row be reversed? Currently NO — the anulación is internal; the cost remains charged unless a separate refund flow is triggered (out of MVP).
- (d) Should the admin be able to RE-cobrar an annulled reprint (e.g., customer decides to pay again)? Sprint 5 — would create a new chain transition `anulada → cobrada`.
- (e) Should `motivo` be ENUM or free-text? Currently free-text.
- (f) Should the system auto-detect excessive reprints by same operator (fraud signal) and emit `alerta tipo_alerta='reimpresion_fraudulenta'`? Sprint 5.
- (g) Should the reprint endpoint differentiate between "first reprint" and "second reprint" pricing (e.g., first is free, second is charged)? Currently always charged.
