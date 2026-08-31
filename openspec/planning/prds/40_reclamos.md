# PRD: reclamos (T40)

> `[L-W]` workflow chain for customer complaints with **polymorphic FK**: `tipo_reclamable ∈ {ingreso, salida, factura, subscripcion}`. Each state transition is a NEW row chained by `uuid_reclamo_padre` (named FK). States: `abierto` (root) → `en_revision` (admin/branch takes) → `resuelto` (admin) | `rechazado` (admin). The `uuid_reclamable` is the FK to the target entity based on `tipo_reclamable` — branch/cliente relationship derived via JOIN through the target.

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
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — **relevant** (chain via `uuid_reclamo_padre`)
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.reclamos`
- **SQL name**: `reclamos` (with `prod` schema)
- **Enforcement level**: `[L-W]` workflow chain (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (customer relationship + audit; not DIAN-critical but legally required in Colombia for consumer complaints)
- **Hash chain**: NO (workflow chain, not source-of-truth for compliance)
- **Polymorphic FK**: `tipo_reclamable ENUM('ingreso', 'salida', 'factura', 'subscripcion')` + `uuid_reclamable` (FK to one of those tables based on tipo_reclamable)
- **Origin**: F1 (schema + REVOKE + trigger + polymorphic FK validation) + IT-10 (writes per reclamo workflow)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_reclamo_padre` is self-FK for workflow chaining: 0..1 (NULL on root, $previous_uuid on transitions).
- `uuid_reclamable` + `tipo_reclamable` form a **polymorphic FK**: the FK target depends on `tipo_reclamable`. DB-level constraint: NOT a single FK to one table; instead, a CHECK constraint validates `tipo_reclamable IN ('ingreso', 'salida', 'factura', 'subscripcion')` AND a per-row application-level validation that `uuid_reclamable` exists in the corresponding table.
- Travel: branch-origin rows (abierto) travel to cloud via `sync_queue`. Cloud-origin rows (en_revision, resuelto, rechazado) flow back to branch via parametrization push.
- **Workflow chain naming**: this table uses `uuid_reclamo_padre` (named FK per AGENTS.md), distinct from `reimpresion_ticket.uuid_padre`. All chain rows of the same reclamo share the same `uuid_reclamable` (the target entity).

## 3. SOLID Atomic Breakdown
- **S**: "one customer complaint event or workflow transition" — INSERT in same TX as log_transaccional.
- **O**: extensible via migration; new `tipo_reclamable` enum values added as new tables become reclamable.
- **I**: branch operator API (writer — POST `/reclamos` for `abierto`); cloud admin API (writer — POST `/reclamos/{uuid}/revisar`, `/resolver`, `/rechazar`); admin read API (ReclamosPanel paginated, filterable by estado + tipo_reclamable).
- **D**: `parkos_core/reclamos/reclamo_writer.py::write_reclamo(tipo_reclamable, uuid_reclamable, motivo, estado, uuid_reclamo_padre=None)` — the ONLY writer. Validates the polymorphic FK (tipo_reclamable in enum; uuid_reclamable exists in the corresponding table) BEFORE INSERT.
- **Atomic**: INSERT only (workflow chain). REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch where the reclamo originated |
| `uuid_reclamable` | polymorphic (no DB FK) | exactly one (NOT NULL) | n/a | FK to the target entity based on `tipo_reclamable`; validated at INSERT time |
| `uuid_reclamo_padre` | `prod.reclamos.uuid` | 0..1 (nullable, self-ref) | RESTRICT | workflow chain link: NULL on root, $previous_uuid on transitions |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| (none direct — `reclamos` is leaf for complaint records) | | | |

**Polymorphic FK detail**:
- DB-level: `CHECK (tipo_reclamable IN ('ingreso', 'salida', 'factura', 'subscripcion'))`.
- Application-level (at INSERT time): validates `uuid_reclamable` exists in the table corresponding to `tipo_reclamable`. E.g., if `tipo_reclamable='factura'`, `SELECT uuid FROM facturas WHERE uuid=$uuid_reclamable` must return a row.
- Branch/cliente relationship is derived via JOIN: `JOIN facturas f ON r.uuid_reclamable=f.uuid JOIN clientes c ON f.uuid_cliente=c.uuid` (where applicable; `facturas` may not have direct cliente FK — needs JOIN through the ingreso/salida). The polymorphic FK requires the application to do the right JOIN based on `tipo_reclamable`.

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `reclamo_writer.py::write_reclamo()` per reclamo or per transition |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for legal retention |

**Special rules**:
- **Workflow chain**: root has `uuid_reclamo_padre=NULL, estado='abierto'`. Transition to `en_revision` has `uuid_reclamo_padre=$root.uuid, estado='en_revision'`. Terminal transition to `resuelto` OR `rechazado` has `uuid_reclamo_padre=$revision.uuid, estado='resuelto'|'rechazado'`. State vigente = last row in chain.
- **All chain rows share `uuid_reclamable` AND `tipo_reclamable`**: per .mmd, the same target entity is the subject of all transitions.
- **Polymorphic FK validation**: at INSERT time, application validates the FK target. Rejects any `tipo_reclamable` not in the enum. Rejects any `uuid_reclamable` not found in the corresponding table.
- **Terminal states**: `resuelto` and `rechazado` are terminal. No further transitions allowed. The chain ends with one of these.

## 6. CodeGraph Dependencies
- `parkos_core/reclamos/reclamo_writer.py::write_reclamo()` (sole writer, validates polymorphic FK).
- `api_sucursal/routers/reclamos.py::POST /reclamos` (operator endpoint for `abierto`).
- `api_admin/routers/reclamos.py::POST /reclamos/{uuid}/revisar` (admin/branch endpoint for `en_revision`).
- `api_admin/routers/reclamos.py::POST /reclamos/{uuid}/resolver` (admin endpoint for `resuelto`).
- `api_admin/routers/reclamos.py::POST /reclamos/{uuid}/rechazar` (admin endpoint for `rechazado`).
- `api_admin/routers/reclamos.py::GET /reclamos` (paginated, filterable by estado, tipo_reclamable, uuid_sucursal).
- `api_admin/routers/reclamos.py::GET /reclamos/{uuid}/chain` (workflow chain view).
- `api_admin/routers/reclamos.py::GET /reclamos/{uuid}/target` (polymorphic FK resolution — returns the target entity detail).
- `web_sucursal/ReclamoAbrirForm` (operator form for `abiento`).
- `web_admin/ReclamosPanel` (cloud admin panel).
- `web_admin/ReclamosPanel/{uuid}/Detail` (single reclamo detail with chain + target).

## 7. Use Cases enabled by this table

The `reclamos` table is the **L-W workflow** for customer complaints with **polymorphic FK**. Workflow: `abierto` (operator) → `en_revision` (admin/branch takes) → `resuelto` (admin) | `rechazado` (admin). The polymorphic FK `tipo_reclamable + uuid_reclamable` allows targeting any of {ingreso, salida, factura, subscripcion}. State vigente is the LAST row in the chain. **Manual operator input** for `abierto` (motivo); **admin input** for `en_revision`/`resuelto`/`rechazado` (resolucion_text or motivo_rechazo).

### 7.1 Use Case: `uc.reclamos.operator-abre-reclamo-sobre-factura`

**Actor**: operator (branch)

**Real-world action**: Customer complains about a factura (e.g., double charge for parking). Operator opens `web_sucursal/ReclamoAbrirForm`, selects `tipo_reclamable='factura'`, enters the `uuid_factura` (or selects from a list of recent facturas), types motivo. Backend validates the polymorphic FK (factura exists), INSERTs `reclamos` root row with `estado='abierto', uuid_reclamo_padre=NULL`, INSERTs `log_transaccional`, enqueues for sync.

**Steps**:
1. Operator opens `web_sucursal/ReclamoAbrirForm`. Form has a `tipo_reclamable` dropdown: {ingreso, salida, factura, subscripcion}.
2. Operator selects `tipo_reclamable='factura'`. Form dynamically loads a `uuid_factura` picker (recent facturas for the branch).
3. Operator selects `uuid_factura=$uuid_xyz`. Form auto-populates the factura detail (cliente, total, fecha).
4. Operator types `motivo='Cliente reclama cobro doble. Factura muestra $17000 pero cliente pagó $34000.'`.
5. Frontend POSTs `api_sucursal /reclamos` with `{tipo_reclamable:'factura', uuid_reclamable:$uuid_xyz, motivo}`.
6. Backend validates RBAC: `permiso='abrir_reclamo'`.
7. Backend validates polymorphic FK: `tipo_reclamable='factura' IN ('ingreso', 'salida', 'factura', 'subscripcion')` ✓; `SELECT uuid FROM facturas WHERE uuid=$uuid_xyz` → returns row ✓.
8. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
9. INSERT `reclamos` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `tipo_reclamable='factura'`, `uuid_reclamable=$uuid_xyz`, `motivo='Cliente reclama cobro doble...'`, `uuid_reclamo_padre=NULL` (ROOT of chain), `timestamp_evento=NOW()`, `estado='abierto'`).
10. INSERT `log_transaccional` (`accion='reclamo_abierto'`, `tabla_afectada='reclamos'`, `uuid_registro_afectado=$reclamo_uuid`, `uuid_usuario=$operator`, `uuid_sucursal=$branch`, `datos_nuevos={tipo_reclamable, uuid_reclamable, motivo, uuid_reclamo_padre:null}`).
11. `queue_processor.enqueue('reclamos', $uuid, $snapshot)`.
12. Operator UI shows: "Reclamo abierto. Esperando revisión del admin."

**Tables touched (writes)**: `reclamos` (1 root row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `facturas` (polymorphic FK validation), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `reclamos.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `reclamos.uuid`. **Polymorphic FK**: `reclamos.uuid_reclamable → facturas.uuid` (validated at INSERT time, no DB FK).

**Sync behavior**:
- Branch → cloud: YES (abierto propagates).
- Cloud → branch: NO (this is the initial request).
- DIAN trigger: NO (reclamo opening doesn't trigger DIAN; only `factura_electronica` creation does).
- Hash chain impact: YES — branch chain extends by 1 row; cloud chain extends on receipt.

**Integration with other tables**:
- Reads from: `facturas` (polymorphic FK validation), `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `reclamos` (root row), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **abierto** flow. The polymorphic FK is validated at INSERT time. The target entity (factura) is NOT modified; only the workflow chain root is created.
- Related: T05 (`facturas`) covers the target factura detail.

### 7.2 Use Case: `uc.reclamos.admin-toma-reclamo-en-revision-extends-chain`

**Actor**: admin (cloud) or supervisor (branch)

**Real-world action**: Admin opens `web_admin/ReclamosPanel`, filter `estado='abierto'`. Clicks a reclamo to review: views the chain (just the root), the target entity detail (factura, via polymorphic FK resolution), the motivo. Admin decides to TAKE (claim ownership). Backend SELECTs the latest chain row (`abierto`), INSERTs new `reclamos` row with `uuid_reclamo_padre=$root.uuid, estado='en_revision', uuid_usuario=$admin`, INSERTs `log_transaccional`, enqueues for parametrization push.

**Steps**:
1. Admin opens `web_admin/ReclamosPanel`, filter `estado='abierto'`.
2. Frontend GETs `api_admin /reclamos?estado=abierto` (paginated, with polymorphic target preview via JOIN).
3. Admin clicks a reclamo → opens `ReclamoDetail` with chain visualization (1 row `abierto`), target entity detail (`/reclamos/{uuid}/target` resolves the polymorphic FK to fetch the target), operator name (JOIN `usuarios`), branch name (JOIN `sucursal`).
4. Admin decides to take. Admin clicks `Tomar`. Frontend POSTs `api_admin /reclamos/{uuid}/revisar` with `{observaciones_admin}`.
5. Backend validates RBAC: `permiso='revisar_reclamo'`.
6. Backend SELECTs latest chain row: `SELECT * FROM reclamos WHERE uuid=$uuid OR uuid_reclamo_padre=$uuid ORDER BY created_at DESC LIMIT 1` — returns the `abierto` row.
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch_of_reclamo`.
8. INSERT `reclamos` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `tipo_reclamable` (same), `uuid_reclamable` (same target), `motivo='Revisión: $observaciones_admin'`, `uuid_reclamo_padre=$latest.uuid` (CHAIN LINK), `timestamp_evento=NOW()`, `estado='en_revision'`).
9. INSERT `log_transaccional` (`accion='reclamo_en_revision'`, `tabla_afectada='reclamos'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin`, `uuid_sucursal=$branch`, `datos_anteriores={estado:'abierto', uuid_reclamo_padre:$root_uuid}`, `datos_nuevos={estado:'en_revision', uuid_reclamo_padre:$root_uuid, observaciones_admin}`).
10. `queue_processor.enqueue('reclamos', $new_uuid, $snapshot)` — parametrization push to branch.
11. Branch receives within 30s; UPSERTs the new row in the chain. Branch UI updates: "Reclamo EN REVISIÓN por admin."
12. Admin UI now shows the chain: root `abierto` → transition `en_revision`. 2 rows. Filter `estado='en_revision'` shows this and other pending resolution.

**Tables touched (writes)**: `reclamos` (1 new chain row, `estado='en_revision'`), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `reclamos` (previous chain row), target entity (polymorphic FK, e.g., `facturas`), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `reclamos.uuid_reclamo_padre` → `reclamos.uuid` (workflow self-FK); per use case 7.1.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud; sprint 5: supervisor branch-side take also possible).
- Cloud → branch: YES — parametrization push.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; branch chain extends on parametrization receipt.

**Integration with other tables**:
- Reads from: `reclamos` (previous chain row), target entity (polymorphic FK), `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `reclamos` (new chain row), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **take/claim** transition. The chain extends; the target entity (factura) is NOT modified yet.

### 7.3 Use Case: `uc.reclamos.admin-resuelve-reclamo-terminal-state`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/ReclamosPanel`, filter `estado='en_revision'`. Investigates the reclamo (views the target factura detail, the operator's name, all `factura_pagos` and `factura_detalle` for the factura). Concludes: customer was correct, the factura has a duplicate charge. Admin clicks `Resolver`. Backend SELECTs the latest chain row (`en_revision`), INSERTs new `reclamos` row with `uuid_reclamo_padre=$revision.uuid, estado='resuelto'` (TERMINAL state), INSERTs `log_transaccional`, enqueues for parametrization push. Optionally, admin triggers downstream actions (e.g., `anulaciones` to annulate the duplicate factura, or refund flow).

**Steps**:
1. Admin opens `web_admin/ReclamosPanel`, filter `estado='en_revision'`.
2. Admin clicks a reclamo → opens `ReclamoDetail` with full chain, target detail, related log_transaccional history.
3. Admin investigates: views `factura_pagos` for the target factura (SUMs by medio_pago), views `factura_detalle` (line items), views the operator's audit history (via `log_transaccional WHERE uuid_usuario=$operator AND uuid_registro_afectado=$factura_uuid`).
4. Admin concludes: customer was correct. Decision: ANNULL the duplicate pago and issue a refund.
5. Admin clicks `Resolver`. Frontend POSTs `api_admin /reclamos/{uuid}/resolver` with `{resolucion_text: 'Cliente correcto. Cobro doble confirmado. Se anula el pago duplicado y se emite nota crédito.', accion_correctiva: 'anular_pago_duplicado'}`.
6. Backend validates RBAC: `permiso='resolver_reclamo'`.
7. Backend SELECTs latest chain row: returns `en_revision`.
8. Backend opens TX; SELECT chain anchor from `log_transaccional`.
9. INSERT `reclamos` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `tipo_reclamable` (same), `uuid_reclamable` (same target), `motivo='Resolución: $resolucion_text. Acción correctiva: $accion_correctiva'`, `uuid_reclamo_padre=$revision.uuid`, `timestamp_evento=NOW()`, `estado='resuelto'` — **TERMINAL STATE**).
10. INSERT `log_transaccional` (`accion='reclamo_resuelto'`, `tabla_afectada='reclamos'`, `uuid_registro_afectado=$new_uuid`, `datos_nuevos={estado:'resuelto', uuid_reclamo_padre:$revision_uuid, resolucion_text, accion_correctiva}`).
11. (Optional) If `accion_correctiva='anular_pago_duplicado'`: backend INSERTs `factura_pagos` row with `valor<0` (refund) for the duplicate pago. This is a separate TX.
12. (Optional) If `accion_correctiva='anular_factura'`: backend INSERTs `anulaciones` workflow root (T39 use case 7.1) referencing the same `uuid_ingreso` of the factura. This is a separate TX (cross-table cascade).
13. `queue_processor.enqueue('reclamos', $new_uuid, $snapshot)`.
14. Branch receives within 30s; UPSERTs the new row in the chain. Branch UI updates: "Reclamo RESUELTO. Acción correctiva aplicada."
15. Admin UI shows the chain: root `abierto` → `en_revision` → `resuelto`. 3 rows. TERMINAL — no further transitions allowed.

**Tables touched (writes)**: `reclamos` (1 terminal chain row), `log_transaccional` (1 row), optional `factura_pagos` (refund row) or `anulaciones` (workflow root for invoice annulment), `sync_queue` (1+ items).
**Tables touched (reads)**: `reclamos` (previous chain row), target entity (polymorphic FK), related tables for investigation (`factura_pagos`, `factura_detalle`, `log_transaccional` audit history), `permisos_usuario` (RBAC), `usuarios`, `sucursal`.
**FKs traversed**: `reclamos.uuid_reclamo_padre` → `reclamos.uuid`; polymorphic FK per tipo_reclamable; optional downstream FKs.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push + optional downstream cascade.
- DIAN trigger: NO (resolucion doesn't directly trigger DIAN; only the downstream `anulaciones.ejecutada` does, if applicable).
- Hash chain impact: YES — cloud chain extends by 1+ rows.

**Integration with other tables**:
- Reads from: `reclamos`, target entity, related tables, `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `reclamos` (terminal row), `log_transaccional`, optional downstream (`factura_pagos` refund or `anulaciones` workflow root), `sync_queue`.
- Cross-cutting: this is the canonical **resolution** transition. The chain TERMINATES. Optional downstream actions are explicit and tracked separately.

### 7.4 Use Case: `uc.reclamos.admin-rechaza-reclamo-terminal-state`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/ReclamosPanel`, filter `estado='en_revision'`. Investigates the reclamo (different customer claim, e.g., "I was overcharged by $1000"). Views the target factura detail and `factura_pagos` SUMs. Concludes: factura is correct, customer is mistaken about the amount. Admin clicks `Rechazar`. Backend SELECTs the latest chain row (`en_revision`), INSERTs new `reclamos` row with `uuid_reclamo_padre=$revision.uuid, estado='rechazado'` (TERMINAL state), INSERTs `log_transaccional` with `motivo_rechazo`, enqueues for parametrization push. NO downstream action (the target entity is unchanged).

**Steps**:
1. Admin opens `web_admin/ReclamosPanel`, filter `estado='en_revision'`.
2. Admin clicks a reclamo → opens `ReclamoDetail` with full chain, target detail.
3. Admin investigates: views `factura_pagos` and confirms the amount is correct. Customer's claim is unfounded.
4. Admin clicks `Rechazar`. Frontend POSTs `api_admin /reclamos/{uuid}/rechazar` with `{motivo_rechazo: 'Factura correcta. Cliente confundió el cobro con otro servicio.'}`.
5. Backend validates RBAC: `permiso='rechazar_reclamo'`.
6. Backend SELECTs latest chain row: returns `en_revision`.
7. Backend opens TX; SELECT chain anchor from `log_transaccional`.
8. INSERT `reclamos` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `tipo_reclamable` (same), `uuid_reclamable` (same target), `motivo='Rechazo: $motivo_rechazo'`, `uuid_reclamo_padre=$revision.uuid`, `timestamp_evento=NOW()`, `estado='rechazado'` — TERMINAL STATE).
9. INSERT `log_transaccional` (`accion='reclamo_rechazado'`, `tabla_afectada='reclamos'`, `uuid_registro_afectado=$new_uuid`, `datos_nuevos={estado:'rechazado', uuid_reclamo_padre:$revision_uuid, motivo_rechazo}`).
10. `queue_processor.enqueue('reclamos', $new_uuid, $snapshot)`.
11. Branch receives within 30s; UPSERTs the new row in the chain. Branch UI updates: "Reclamo RECHAZADO. Motivo: $motivo_rechazo."
12. The customer may escalate via another `reclamos` workflow (operator can open a NEW reclamo with `uuid_reclamable` pointing to the same target — separate chain).

**Tables touched (writes)**: `reclamos` (1 terminal chain row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `reclamos` (previous chain row), target entity (polymorphic FK), related tables for investigation, `permisos_usuario` (RBAC), `usuarios`, `sucursal`.
**FKs traversed**: `reclamos.uuid_reclamo_padre` → `reclamos.uuid`; polymorphic FK per tipo_reclamable.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push.
- DIAN trigger: NO.
- Hash chain impact: YES.

**Integration with other tables**:
- Reads from: `reclamos`, target entity, related tables, `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `reclamos` (terminal row), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **rejection** transition. The chain TERMINATES. NO downstream action. The target entity is confirmed unchanged.
- Related: customer may open a NEW reclamo if dissatisfied (separate chain).

### 7.5 Use Case: `uc.reclamos.polymorphic-fk-validation-rejects-invalid-tipo-or-uuid`

**Actor**: system (at INSERT time) + developer (when implementing client)

**Real-world action**: When the operator (or any caller) attempts to INSERT a `reclamos` row with an invalid `tipo_reclamable` (e.g., `'otro'`) or a `uuid_reclamable` that doesn't exist in the corresponding table, the system rejects the INSERT. The polymorphic FK constraint is enforced at TWO levels: (1) DB CHECK constraint on `tipo_reclamable` enum; (2) application-level validation that `uuid_reclamable` exists in the corresponding table.

**Steps**:
1. Frontend POSTs `api_sucursal /reclamos` with `{tipo_reclamable:'otro', uuid_reclamable:$some_uuid, motivo}` — invalid `tipo_reclamable`.
2. Backend validates RBAC.
3. Backend validates polymorphic FK: `tipo_reclamable='otro' NOT IN ('ingreso', 'salida', 'factura', 'subscripcion')` → REJECT with 422 `{detail: 'tipo_reclamable_invalido', allowed_values: ['ingreso', 'salida', 'factura', 'subscripcion']}`.
4. (Alternative) Frontend POSTs with `tipo_reclamable='factura', uuid_reclamable=$nonexistent_uuid`.
5. Backend validates polymorphic FK: `tipo_reclamable='factura'` ✓; `SELECT uuid FROM facturas WHERE uuid=$nonexistent_uuid` → returns 0 rows.
6. Backend REJECTS with 422 `{detail: 'uuid_reclamable_no_existe', tipo_reclamable: 'factura', uuid_reclamable: $nonexistent_uuid}`.
7. NO INSERT performed. NO log_transaccional row written (the validation happens BEFORE the TX).
8. Frontend displays the error to the user.
9. (Optional) Sprint 5: trigger-level polymorphic FK validation as a safety net (in case application bypasses validation).

**Tables touched (writes)**: NONE (rejected before INSERT).
**Tables touched (reads)**: `facturas` (or corresponding table for validation), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor for the would-be INSERT, but not used).
**FKs traversed**: none (no INSERT).

**Sync behavior**:
- Branch → cloud: NO (rejected client-side).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: target entity table (validation), `permisos_usuario`.
- Writes to: NONE.
- Cross-cutting: this is the **polymorphic FK enforcement**. Two layers: (1) DB CHECK on enum; (2) application validation on UUID existence. Sprint 5: trigger-level safety net.
- Related: the .mmd explicitly documents `tipo_reclamable IN ('ingreso', 'salida', 'factura', 'subscripcion')` — this is the canonical enum.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger + polymorphic FK validation), 2 (DB triggers — polymorphic FK safety net, sprint 5), 5 (audit constraints — REVOKE), 6 (cloud admin API), 7 (branch API), 8 (Pydantic schemas with polymorphic discriminator), 10 (cloud sync worker), 11 (branch sync worker), 12 (sync_queue interop), 13 (web_admin ReclamosPanel), 14 (web_sucursal ReclamoAbrirForm), 15 (shadcn UI), 16 (Zustand reclamos state), 17 (i18n — motivo text), 20 (structlog), 24 (pytest), 28 (docker compose), 38 (multi-tenant boundaries — admin JWT scope).

## 9. RED Tests
- (RED) INSERT `reclamos` from `rol_app` → success.
- (RED) UPDATE `prod.reclamos` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.reclamos` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Workflow chain: root `uuid_reclamo_padre=NULL, estado='abierto'`; transition `uuid_reclamo_padre=$root.uuid, estado='en_revision'`; terminal `uuid_reclamo_padre=$revision.uuid, estado='resuelto'|'rechazado'`.
- (RED) All chain rows share the same `tipo_reclamable` AND `uuid_reclamable`.
- (RED) State vigente query: `ORDER BY created_at DESC LIMIT 1` returns the latest row.
- (RED) Polymorphic FK: `tipo_reclamable='factura', uuid_reclamable=$valid_factura_uuid` → INSERT success.
- (RED) Polymorphic FK: `tipo_reclamable='otro'` (invalid enum) → 422 `tipo_reclamable_invalido`.
- (RED) Polymorphic FK: `tipo_reclamable='factura', uuid_reclamable=$nonexistent_uuid` → 422 `uuid_reclamable_no_existe`.
- (RED) Polymorphic FK: `tipo_reclamable='ingreso', uuid_reclamable=$valid_factura_uuid` (mismatch) → 422 `uuid_reclamable_no_existe` (because the UUID isn't in `ingreso` table).
- (RED) Target resolution endpoint: `GET /reclamos/{uuid}/target` returns the target entity (factura, ingreso, salida, or subscripcion) with proper polymorphic JOIN.
- (RED) Terminal states: `resuelto` and `rechazado` reject further transitions (POST `/resolver` on `resuelto` chain → 409 `reclamo_terminal`).
- (RED) Chain replication: cloud-origin chain rows propagate to branch within 30s.
- (RED) Cross-table cascade: `accion_correctiva='anular_factura'` in resolution triggers `anulaciones` workflow root (separate TX, separate audit).
- (RED) `motivo` is required (NOT NULL constraint enforced at INSERT).
- (RED) RBAC: operator without `permiso='abrir_reclamo'` → 403; admin without `permiso='revisar_reclamo'` → 403; admin without `permiso='resolver_reclamo'` → 403; admin without `permiso='rechazar_reclamo'` → 403.
- (RED) Customer escalation: a NEW reclamo for the same target after `rechazado` → creates a NEW chain (not extending the rejected one).

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + CHECK constraint on `tipo_reclamable` enum.
- [ ] F1.x `reclamo_writer.py::write_reclamo()` helper with polymorphic FK validation.
- [ ] F1.x Recursive CTE query helper for chain resolution.
- [ ] F1.x Polymorphic FK resolution helper (`resolve_target(uuid_reclamo, tipo_reclamable)`).
- [ ] IT-10.x: `api_sucursal/routers/reclamos.py::POST /reclamos` (operator endpoint for `abierto`).
- [ ] IT-10.x: polymorphic FK validation at INSERT time.
- [ ] IT-10.x: `api_admin/routers/reclamos.py::POST /reclamos/{uuid}/revisar`.
- [ ] IT-10.x: `api_admin/routers/reclamos.py::POST /reclamos/{uuid}/resolver` (with optional downstream cascade).
- [ ] IT-10.x: `api_admin/routers/reclamos.py::POST /reclamos/{uuid}/rechazar`.
- [ ] IT-10.x: `api_admin/routers/reclamos.py::GET /reclamos` (paginated, filterable).
- [ ] IT-10.x: `api_admin/routers/reclamos.py::GET /reclamos/{uuid}/chain`.
- [ ] IT-10.x: `api_admin/routers/reclamos.py::GET /reclamos/{uuid}/target` (polymorphic FK resolution).
- [ ] IT-10.x: chain replication via parametrization push.
- [ ] IT-10.x: `web_sucursal/ReclamoAbrirForm` with polymorphic target picker.
- [ ] IT-10.x: `web_admin/ReclamosPanel` (filter + list + revise/resolve/reject).
- [ ] IT-10.x: `web_admin/ReclamosPanel/{uuid}/Detail` with chain + target detail.
- [ ] Sprint 5: trigger-level polymorphic FK validation as safety net.
- [ ] Sprint 5: dashboard widget "Reclamos abiertos por sucursal" (cross-branch view).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Polymorphic FK bypassed (application bug) | Low | Sprint 5: trigger-level validation as safety net; immediate RED test coverage |
| Admin delays review (reclamo stuck in `abierto`) | Med | `alerta` reminder after 24h (T41); sprint 5: SLA monitoring |
| Operator opens duplicate reclamos for same target | Low | UI warns if `EXISTS(reclamos WHERE uuid_reclamable=$X AND uuid_reclamo_padre IS NULL AND estado IN ('abierto', 'en_revision'))`; sprint 5: enforce uniqueness |
| Customer escalates after `rechazado` — chain confusion | Low | New chain is independent (not extending rejected); admin sees both chains in detail |
| Resolucion triggers downstream cascade (e.g., `anular_factura`) which fails | Low | TX wraps cascade; failure rolls back the chain row + cascade; admin retries |
| Terminal state transition attempted (POST `/resolver` on `resuelto` chain) → 409 | Low | UI disables action buttons for terminal states; server-side validation |
| Branch/cliente relationship derivation fails (polymorphic JOIN ambiguous) | Low | Each `tipo_reclamable` has a well-defined JOIN path; document in `resolve_target` helper |
| Chain replication delays → branch sees outdated chain | Low | Replication is best-effort within 30s; admin can force re-push |
| Motivo text exposes sensitive info (PII) | Low | Motivo is operator-typed; encryption-at-rest is sprint 5+ |

## 12. Open Questions
- (a) Should the polymorphic FK validation be at the DB level (e.g., per-tipo trigger) for stronger guarantees? Sprint 5.
- (b) Should `resolucion_text` and `motivo_rechazo` be separate columns or merged into `motivo` with a prefix? Currently separate for clarity.
- (c) Should there be a `reapertura` transition (admin reopens a `resuelto` or `rechazado` reclamo after customer escalation)? Sprint 5.
- (d) Customer-facing portal: should customers see their own reclamos? Sprint 5 (customer portal feature).
- (e) Should `reclamos` support bulk operations (admin resolves 50 reclamos in one click)? Sprint 5.
- (f) SLA monitoring: should admin be alerted if a `reclamos` chain is stuck in `en_revision` for > 7 days? Currently NOT; sprint 5.
- (g) Refund flow integration: should `resuelto` with `accion_correctiva='refund'` automatically INSERT negative `factura_pagos` rows? Sprint 5 — currently manual via separate flow.
- (h) Cross-tenant scope: admin from chain A reviewing a reclamo for branch B — requires `permisos_usuario` for both branches + `sucursales_permitidas` in admin JWT.
