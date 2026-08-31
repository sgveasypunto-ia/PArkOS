# PRD: tipo_persona (T22)

> Customer type catalog seeded with `'natural'`, `'juridica'`, `'consumidor_final'`. Read by admin and branch operators on every `clientes` creation. The `'consumidor_final'` row is special: it's the DEFAULT `uuid_cliente` for every `factura_electronica` issued without an identified customer (casual flow / no cedula captured).

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration_plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.tipo_persona`
- **SQL name**: `tipo_persona` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema, seeded 3 types) + IT-10 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 3 use cases covering admin CRUD, branch referencia on cliente creation, and consumidor_final default for casual facturacion)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `tipo` unique string ('natural' / 'juridica' / 'consumidor_final').

## 3. SOLID Atomic Breakdown
- **S**: "one customer type".
- **O**: new column `descripcion`.
- **I**: admin CRUD.
- **D**: `parkos_core/models/V/tipo_persona.py`.
- **Atomic**: INSERT, UPDATE.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `clientes.uuid_tipo_persona` | `\|\|--o{` | clientes classified by type |

## 5. Atomic DB Operations
| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Seed (3 types) in F1 |
| UPDATE | YES | Inside TX + `log_transaccional` |
| DELETE | NO | RESTRICT if any cliente uses |

## 6. CodeGraph Dependencies
- `api_admin/routers/tipo-persona.py`.
- `web_admin/TipoPersonaForm`.

## 7. Use Cases enabled by this table

The `tipo_persona` table is the **3-row catalog that classifies every customer** in the system. While tiny (only 3 rows), it's load-bearing: it gates whether a `clientes` row can have a `clientes_b2b` extension, it determines whether the operator asks for `numero_identificacion` (nit/cedula) at ingreso time, and it provides the canonical `'consumidor_final'` UUID that every e-factura references when the customer is anonymous. Use cases below describe the admin CRUD, the branch reference on `clientes` creation, and the `consumidor_final` default for casual flow. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.tipo-persona.admin-crud-create-or-version`

Cloud admin manages the `tipo_persona` catalog. New types are rare (the seed is 3 types for MVP), but the admin may add `tipo='extranjero'` for foreign customers or `tipo='diplomatico'` for diplomatic corps with special tax treatment. Updates create a new `[V]` version (archive old with `vigente_hasta=NOW()`, INSERT new). Parametrization push delivers the new version to all branches. The `tipo='consumidor_final'` row is SPECIAL — it's seeded with a FIXED UUID and used as default for `factura_electronica.uuid_cliente` (see use case 7.3).

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='administrar_catalogos'`; the catalog has the 3 seed rows; if creating a new `tipo`, the name is unique (DB constraint).

**Steps**:
1. Admin opens `web_admin/Catalogos/TipoPersona`, clicks `New` or selects an existing row to update.
2. For CREATE: Frontend POSTs `api_admin /tipo-persona` (admin- JWT) with `{tipo='extranjero', descripcion='Cliente extranjero sin NIT/cedula colombiana', vigente_desde=NOW()}`. For UPDATE: PATCH `/tipo-persona/{uuid}` with the changes.
3. Backend validates `permisos_usuario` for `permiso='administrar_catalogos'`; rejects 403 if missing.
4. Backend SELECTs current vigente rows: `SELECT * FROM tipo_persona WHERE vigente_hasta IS NULL`. Validates UNIQUE on `tipo` (rejects 409 if duplicate).
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. For UPDATE: UPDATE current vigente row SET `vigente_hasta=NOW()` (archive old). For CREATE: skip this step.
7. INSERT new `tipo_persona` row (`uuid=server-generated`, `tipo`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
8. INSERT `log_transaccional` (`accion='tipo_persona_actualizado'`, `tabla_afectada='tipo_persona'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores=$old_snapshot`, `datos_nuevos=$new_snapshot`).
9. `queue_processor.enqueue('tipo_persona', $new_uuid, $new_snapshot)` → parametrization push for all active branches within 30s.
10. If archiving: also enqueue the archived row (`vigente_hasta=NOW()`).
11. Backend returns `{new_uuid}` to frontend.
12. Branch receives parametrization; UPSERT new row, UPDATE local old row. The local mirror reflects the updated catalog.
13. Next `ClientesForm` (web_admin or web_sucursal) shows the new `tipo` in the dropdown.

**Tables touched (writes)**: `tipo_persona` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipo_persona` (current vigente + uniqueness check), `log_transaccional` (chain anchor), `usuarios` (admin actor), `sucursal` (admin primary branch).
**FKs traversed**: `tipo_persona` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `tipo_persona.uuid`.
**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the new + archived version to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (admin's branch key); each branch chain extends by 1 row when parametrization is received.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `tipo_persona` (current state), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `tipo_persona` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: this is the lightest parametrization catalog — only 3 seed rows. The system design reserves the FIXED UUID for `consumidor_final` because every `factura_electronica` for anonymous customers references it (use case 7.3).
- Related: if admin DELETES a `tipo` that has `clientes` referencing it, the FK RESTRICT blocks. To "remove" a type, admin must create a new version with `estado='inactivo'` and ensure no future `clientes` use it; existing `clientes` keep their FK reference (RESTRICT).

### 7.2 Use Case: `uc.tipo-persona.branch-picks-on-cliente-create`

Admin (cloud or branch) creates a new `clientes` row via `web_admin/ClientesForm` or `web_sucursal/ClientesForm`. Frontend shows a dropdown of `tipo_persona` vigentes; admin picks one. Backend validates the pick is vigente (RESTRICT on FK ensures no archived `tipo` is referenced). The choice cascades into business logic: `natural`/`juridica` customers require `numero_identificacion` (cedula or NIT); `consumidor_final` allows NULL. `juridica` (with `clientes_b2b` extension) unlocks B2B features (corporate contract, fixed monthly fee, multiple vehicles).

**Actor**: admin (cloud or branch)

**Pre-conditions**: branch has parametrization-delivered the vigentes (per use case 7.1); admin has `permiso='crear_clientes'` (or operator has the same perm if branch-level creation is enabled).

**Steps**:
1. Admin opens `ClientesForm`, fills `numero_identificacion` (e.g., `1234567890`), `nombre='Juan Pérez'`, `apellido='García'`, `telefono`, `email`.
2. Frontend GETs `api_admin /tipo-persona?vigente_only=true` (or branch's `/tipo-persona`).
3. Backend returns the vigentes (typically 3 rows: `natural`, `juridica`, `consumidor_final`).
4. Frontend renders dropdown. Admin picks `'natural'`.
5. Frontend POSTs `api_admin /clientes` (admin- JWT) with `{tipo_identificador='cedula', numero_identificacion='1234567890', nombre, apellido, telefono, email, uuid_tipo_persona=$natural_uuid}`.
6. Backend validates: `numero_identificacion` is mandatory when `uuid_tipo_persona != consumidor_final_uuid`. Rejects 400 if missing.
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
8. INSERT `clientes` row (`uuid=server-generated`, `tipo_identificador`, `numero_identificacion`, `nombre`, `apellido`, `telefono`, `email`, `uuid_tipo_persona=$natural_uuid`, `registro={...}`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
9. INSERT `log_transaccional` (`accion='cliente_creado'`, `tabla_afectada='clientes'`, `uuid_registro_afectado=$cliente_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_anteriores=null`, `datos_nuevos=$cliente_snapshot`).
10. `queue_processor.enqueue('clientes', $uuid, $snapshot)` → branch receives the new cliente via parametrization pull within 30s.
11. Backend returns `{uuid, ...}` to frontend.
12. If `uuid_tipo_persona` was `juridica`: the backend additionally offers to create `clientes_b2b` (separate form). If admin skips, the cliente is `juridica` without B2B extension.

**Tables touched (writes)**: `clientes` (1 row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipo_persona` (vigente lookup for dropdown), `clientes` (uniqueness check on `numero_identificacion` per tipo), `log_transaccional` (chain anchor), `usuarios` (admin actor), `sucursal` (branch context).
**FKs traversed**: `clientes.uuid_tipo_persona` → `tipo_persona.uuid` (the FK is RESTRICT, ensuring no archived `tipo` is referenced). `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `clientes.uuid`.
**Sync behavior**:
- Branch → cloud: NO (if admin is cloud; if branch, the cliente is enqueued for cloud receipt within 30s).
- Cloud → branch: YES — parametrization pull delivers the new cliente to all branches within 30s.
- DIAN trigger: NO (cliente creation doesn't trigger DIAN).
- Hash chain impact: YES — chain (cloud or branch) extends by 1 row on creation; each other branch extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `tipo_persona` (vigente for dropdown), `clientes` (uniqueness check), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (branch).
- Writes to: `clientes` (the new customer), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: the FK from `clientes.uuid_tipo_persona` to `tipo_persona.uuid` enforces the catalog reference; RESTRICT on DELETE prevents breaking historical FKs (an old `clientes` row with `uuid_tipo_persona=$old_natural_uuid` keeps pointing to the archived version — this is desired for probatory integrity).
- Related: if admin picks `juridica`, the system MAY also create `clientes_b2b` (separate `[V]` table with `cantidad`, `registro` JSON, `fecha_vencimiento`). The `clientes_b2b` table is the B2B contract extension; not all `juridica` clientes have it.

### 7.3 Use Case: `uc.tipo-persona.consumidor-final-default-casual-flow`

Casual customer (no subscription, doesn't want to provide cedula) arrives, parks, departs. Operator doesn't create a `clientes` row. Branch backend inserts the business `facturas` row with `uuid_cliente=NULL` in the factura (the business row is per-ingreso, not per-customer). Cloud receives, INSERTs `factura_electronica` with `uuid_cliente=$consumidor_final_default_uuid` (the FIXED UUID seeded for the `consumidor_final` row in `tipo_persona`). This is the canonical DIAN flow for anonymous customers: every e-factura references a real `clientes.uuid` (the consumidor_final placeholder), never NULL.

**Actor**: operator (branch) + dian_dispatcher (cloud)

**Pre-conditions**: `tipo_persona` has the seed `consumidor_final` row with its FIXED UUID; `clientes` has a matching row with the SAME FIXED UUID (`uuid=$consumidor_final_default_uuid`, `tipo_identificador='consumidor_final'`, `numero_identificacion='222222222222'`, `nombre='Consumidor Final'`, `uuid_tipo_persona=$consumidor_final_tipo_uuid`). Both are seeded during cloud boot.

**Steps**:
1. Casual customer arrives at the booth. Operator opens `IngresoForm`, types plate, selects `tipo_vehiculo='auto'`. NO `cliente` lookup (anonymous flow).
2. Operator submits ingreso. Branch INSERTs `ingreso` (with `uuid_subscripcion_cliente=NULL`, `observaciones='casual_anonimo'`).
3. Customer returns to vehicle, departs. Operator opens `SalidaForm`, types plate, system finds the ingreso. No subscriber check (anonymous).
4. Operator opens `FacturacionForm`. Branch backend has no `cliente` to attach; the facturacion flow accepts `uuid_cliente=NULL` in the business `facturas` row.
5. Backend computes cost, INSERTs `facturas` (`uuid_cliente=NULL`), `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`. INSERT `log_transaccional`.
6. Branch backend POSTs `api_admin /facturas/procesar` (online) OR queues for sync (offline).
7. Cloud handler receives. SELECTs `clientes WHERE uuid=$consumidor_final_default_uuid` (the FIXED seed UUID) — guaranteed to exist.
8. Cloud SELECT `empresa FOR UPDATE`; atomic increment. INSERT `factura_electronica` with `uuid_cliente=$consumidor_final_default_uuid`, `consecutivo=$new`, `estado='activa'`, `reportado_dian=false`. INSERT `log_transaccional`.
9. Cloud emits `SyncBackEvent` with `numero_oficial`.
10. Branch UPSERTs `facturas.uuid_factura_electronica`, `numero_oficial`. Operator prints the receipt with `Consumidor Final` as titular.
11. `dian_dispatcher` sends the e-factura to DIAN with the `consumidor_final` placeholder. DIAN accepts (Reglamentación DIAN 042 de 2020 allows this for ventas sin identificación).

**Tables touched (writes)**: `ingreso` (1 row), `salidas` (1 row), `facturas` (1 row with NULL cliente), `factura_detalle` (snapshot), `factura_pagos`, `factura_impuestos` (snapshot from `impuestos`), `factura_otros_cobros` (snapshot from `otros_cobros`), `log_transaccional` (multiple rows), `empresa` (atomic UPDATE), `factura_electronica` (1 row with `uuid_cliente=$consumidor_final_default_uuid`), `SyncBackEvent` (concept).
**Tables touched (reads)**: `tipo_persona` (the `consumidor_final` row for the FIXED UUID), `clientes` (the placeholder row), `tarifas_sucursal` (vigente for cost), `impuestos` (vigente for tax), `otros_cobros` (vigente for other charges), `empresa` (atomic lock + consecutive), `log_transaccional` (chain anchors).
**FKs traversed**: `facturas.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid` (the `$consumidor_final_default_uuid` placeholder); `clientes.uuid_tipo_persona` → `tipo_persona.uuid` (the `consumidor_final` row); `empresa` (atomic UPDATE).
**Sync behavior**:
- Branch → cloud: YES — the `facturas` + children + `log_transaccional` push via `sync_queue` within 30s (or synchronous online POST).
- Cloud → branch: YES — `SyncBackEvent` flows back with the real `numero_oficial`.
- DIAN trigger: YES — `dian_dispatcher` sends the e-factura to DIAN with the consumidor_final placeholder.
- Hash chain impact: YES — branch chain extends by N rows (one per business write), cloud chain extends by 2 rows (consecutivo_asignado + factura_electronica_creada).
**Integration**:
- Reads from: `tipo_persona` (the consumidor_final row), `clientes` (the placeholder), `tarifas_sucursal` (vigente), `impuestos` (vigente snapshot), `otros_cobros` (vigente snapshot), `empresa` (atomic lock), `log_transaccional` (chain anchors).
- Writes to: `ingreso`, `salidas`, `facturas` (with NULL cliente), `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `log_transaccional`, `empresa`, `factura_electronica`, `SyncBackEvent`.
- Cross-cutting: this is the **canonical anonymous-customer flow**. The FIXED UUID for `consumidor_final` is the only way to ensure DIAN compliance: NULL `uuid_cliente` would violate DIAN's requirement that every e-factura identify a titular (even if it's a generic placeholder).
- Related: if `consumidor_final` row is accidentally deleted, EVERY facturacion breaks with FK violation. The row must be PROTECTED — `DELETE` blocked at application layer AND FK RESTRICT ensures no cascading delete from `clientes.uuid_tipo_persona` removal.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 13, 31.

## 9. RED Tests
- (RED) `tipo` unique; duplicate → UNIQUE violation.
- (RED) ON DELETE RESTRICT: cannot delete if `clientes` uses it.

## 10. Implementation Tasks
- [x] F1.x Seed (natural/juridica/consumidor_final).
- [ ] IT-10.x: admin CRUD.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| New type added | Low | Migration + seed |

## 12. Open Questions
- (a) Dynamic types vs fixed 3?