# PRD: permisos (T08)

> Permission catalog. Versioned projection.

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

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.permisos`
- **SQL name**: `permisos` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema) + IT-1 (writes)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `permiso` is unique string identifier.

## 3. SOLID Atomic Breakdown
- **S**: "one permission in the catalog".
- **O**: new permissions added via INSERT.
- **I**: `POST /permisos`, `GET /permisos` (admin-only).
- **D**: `parkos_core/models/V/permisos.py`.
- **Atomic**: INSERT, UPDATE (rare — rename permission).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | catalog |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `permisos_usuario.uuid_permiso` | \|\|--o{ | permissions assigned to users |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin inserts new permission |
| UPDATE | YES (rare — rename) | Inside TX + `log_transaccional` |
| DELETE | NO | Archive via UPDATE |

## 6. CodeGraph Dependencies
- `api_admin/routers/permisos.py`.
- `api_admin/routers/permisos_usuario.py`.

## 7. Use Cases enabled by this table

The `permisos` table is the **permission catalog**: a small list of granular permissions (`facturar`, `reimprimir`, `aprobar_anulacion`, `ver_arqueo`, `parametrizar`, etc.). Cloud-only writes (admin manages); branches read-only via parametrization pull. Each permission is identified by a unique `permiso` string and referenced by `permisos_usuario` to grant it to users.

### 7.1 Use Case: `uc.permisos.admin-adds-new-permission-to-catalog`

**Actor**: admin

**Real-world action**: Admin needs a new granular permission `facturar_b2b` (only certain operators can issue B2B invoices). Admin opens `web_admin/PermisosList`, adds the new permission. Cloud writes the row and propagates to all branches via parametrization pull.

**Steps**:
1. Admin opens `web_admin/PermisosList` → `PermisoForm`.
2. Admin fills `permiso='facturar_b2b', descripcion='Permite emitir facturas a clientes B2B con NIT', categoria='facturacion'`.
3. Frontend POSTs `api_admin /permisos`.
4. Backend validates `permiso` is unique (`UNIQUE` constraint on `permisos.permiso`).
5. Backend INSERT `permisos` row (`vigente_desde=NOW(), vigente_hasta=NULL, estado='activo'`).
6. INSERT `log_transaccional` (`accion='permiso_creado'`, `tabla_afectada='permisos'`, `uuid_registro_afectado=$new`).
7. `queue_processor.enqueue('permisos', uuid, datos)` (parametrization pull).
8. Cloud → all branches within 30s; branch `permisos` catalog now includes `facturar_b2b`.
9. Admin sees the new permission in the list with active count.

**Tables touched (writes)**: `permisos`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `permisos` (uniqueness check).
**FKs traversed**: `permisos` has NO outgoing FKs (it's a catalog); `log_transaccional.uuid_usuario` → `usuarios.uuid` (the admin).

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator).
- Cloud → branch: YES — parametrization pull pushes the new `permisos` row to all branches within 30s. The branch catalog is now updated.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row on cloud side; all branch chains extend by 1 row each (when parametrization pull propagates).

**Integration with other tables**:
- Reads from: `permisos` (uniqueness check).
- Writes to: `permisos` (new catalog entry), `log_transaccional` (audit), `sync_queue` (deferred propagation).
- Downstream: admins can now GRANT this permission via `permisos_usuario` (T09 use case 7.1).

### 7.2 Use Case: `uc.permisos.api-enforces-permission-on-action`

**Actor**: system

**Real-world action**: An operator tries to issue a B2B invoice at the booth. The API middleware calls `require_permission('facturar_b2b')` which checks the operator's `permisos_usuario` rows. If the operator doesn't have it → 403.

**Steps**:
1. Operator POSTs `api_sucursal /facturas` with `uuid_cliente=$b2b_client_uuid, lines=[...]`.
2. Backend middleware runs `auth.require_permission('facturar_b2b')`.
3. `require_permission` reads JWT claims (`uuid_usuario`), SELECTs `permisos_usuario` rows WHERE `uuid_usuario=$jwt.uuid_usuario AND vigente_hasta IS NULL`.
4. Joins `permisos_usuario` with `permisos` to get the `permiso` strings.
5. Checks if `'facturar_b2b'` is in the set.
6. If YES: proceed with the `facturas` flow (use case T05).
7. If NO: return 403 with `{detail: 'permission_denied', required_permission: 'facturar_b2b'}`.
8. INSERT `log_transaccional` (`accion='permission_denied'`, `datos_nuevos={permiso: 'facturar_b2b', uuid_usuario}`).
9. INSERT `alerta` (`tipo_alerta='permission_denied_repeated', estado='abierta'` if 3+ denials in 1h).

**Tables touched (writes)**: `log_transaccional`, `alerta` (on repeat).
**Tables touched (reads)**: `permisos_usuario`, `permisos` (via JOIN), `log_transaccional` (chain anchor).
**FKs traversed**: `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_permiso` → `permisos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is a branch-local enforcement check).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row per denial (`accion='permission_denied'`).

**Integration with other tables**:
- Reads from: `permisos_usuario` (user's granted permissions), `permisos` (catalog), `log_transaccional` (chain anchor).
- Writes to: `log_transaccional` (audit), `alerta` (on repeat pattern).
- Cross-cutting: this is the canonical example of why the `permisos_usuario` bridge table exists — the actual enforcement always goes through it, never through `usuarios.rol` directly.

### 7.3 Use Case: `uc.permisos.admin-rename-permission`

**Actor**: admin

**Real-world action**: Admin needs to rename a permission from `facturar` to `facturar_b2c` (semantic clarification — split into B2C and B2B variants). Admin opens `web_admin/PermisosList`, clicks the permission, edits the `permiso` string. The `[V]` UPDATE pattern creates a NEW `permisos` row with the new string and archives the OLD row. All `permisos_usuario` rows that referenced the old `permisos.uuid` are NOT auto-rewritten — they remain bound to the OLD UUID, which is now archived. Admin must re-grant `permisos_usuario` with the new UUID if the new permission should is granted.

**Steps**:
1. Admin opens `web_admin/PermisosList`; clicks `facturar`; clicks `Rename`.
2. Frontend PATCHes `api_admin /permisos/{uuid}` with `{permiso: 'facturar_b2c'}`.
3. Backend validates the new string is unique (UNIQUE constraint on `permisos.permiso`).
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch` (use a neutral branch like cloud's own `uuid_sucursal='CLOUD'` for catalog writes).
5. SELECT current `permisos` row (vigente one).
6. INSERT new `permisos` row with `permiso='facturar_b2c'`, `vigente_desde=NOW(), vigente_hasta=NULL`.
7. UPDATE OLD `permisos` row `vigente_hasta=NOW()` (archive).
8. INSERT `log_transaccional` (`accion='permiso_renombrado'`, `tabla_afectada='permisos'`, `datos_anteriores={permiso:'facturar'}, datos_nuevos={permiso:'facturar_b2c', uuid_nuevo: $new_uuid, uuid_viejo: $old_uuid}`).
9. `queue_processor.enqueue('permisos', uuid_new, datos)` (parametrization pull to all branches within 30s).
10. Branch receives parametrization pull: local `permisos` table has both old (archived) and new (vigente) rows.
11. **Important**: `permisos_usuario` rows that referenced the old UUID remain valid (vigente for old UUID). They become inert because no API check looks for `permisos.permiso='facturar'` anymore — the enforcement looks up by the vigente UUID/permiso string. Admin must run a data migration to reassign all existing `permisos_usuario` rows from old UUID to new UUID (application-level script, out of MVP scope; documented in `tasks.md`).
12. Operator's JWT permission claims: cached in JWT at login. If operator was logged in before rename, JWT may still contain `permissions=['facturar']` until logout/refresh. After 12h (JWT TTL), the new claims will reflect the vigente permission set.

**Tables touched (writes)**: `permisos` (new row + UPDATE old), `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `permisos` (uniqueness check), `permisos_usuario` (rows referencing old UUID — informational, NOT modified), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid` (the admin); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (cloud branch context); `permisos_usuario.uuid_permiso` → `permisos.uuid` (READ ONLY on old UUID; not auto-rewritten).

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator).
- Cloud → branch: YES — parametrization pull pushes both new + old (archived) rows to all branches within 30s. Each branch `permisos` table is updated.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (`accion='permiso_renombrado'`); each branch chain extends by 1 row when parametrization pull is received.

**Integration with other tables**:
- Reads from: `permisos` (uniqueness check), `permisos_usuario` (rows referencing old UUID — informational), `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `permisos` (new + UPDATE old), `log_transaccional` (audit), `sync_queue` (parametrization pull).
- Cross-cutting: rename is a `[V]` UPDATE pattern (new version + archive old). DELETE is forbidden. This preserves the audit trail: the rename is a recorded event in `log_transaccional` with both old and new strings. Subsequent `permisos_usuario` migrations can be traced back to this rename event.
- Risk: `permisos_usuario` rows are NOT auto-migrated. If admin does not run the migration, operators retain access via the old permission string (which is now archived but still in JWT claims and in DB). For MVP, document this as a known limitation; admin must re-grant manually.

### 7.4 Use Case: `uc.permisos.permiso-vigente-filter-for-assignment`

**Actor**: admin

**Real-world action**: Admin opens `web_admin/UsuariosDetail/PermisosTab` to grant a permission to an operator. The frontend must show ONLY vigente permissions (not archived/renamed ones). Backend query filters by `vigente_hasta IS NULL AND estado='activo'`. This prevents admin from accidentally assigning an archived permission that wouldn't be enforced.

**Steps**:
1. Admin opens `web_admin/UsuariosDetail/PermisosTab` for operator Juan.
2. Admin clicks `Add Permission` to open the permission selector.
3. Frontend GETs `api_admin /permisos?vigente=true` — filter on `vigente_hasta IS NULL AND estado='activo'`.
4. Backend returns only vigente permissions: e.g., `facturar_b2c`, `reimprimir`, `aprobar_anulacion`, `ver_arqueo`. Archived permissions (e.g., the old `facturar`) are NOT in the list.
5. Admin selects `aprobar_anulacion` from the dropdown (vigente).
6. Admin clicks `Save` → Frontend POSTs `api_admin /permisos-usuario` with `{uuid_usuario=$juan, uuid_permiso=$aprobar_anulacion.uuid, vigente_desde=NOW()}` (continues to T09 use case `admin-grants-permission-to-operator`).
7. The vigente filter ensures only valid permissions can be assigned. If admin somehow POSTs an archived permission UUID: backend rejects with 400 `{detail: 'permission_not_vigente', uuid_permiso: $old_uuid, archived_at: $vigente_hasta}`.

**Tables touched (writes)**: NONE for the filter query itself. If admin proceeds to assign: `permisos_usuario` (W, per T09), `log_transaccional` (W, per T09), `sync_queue` (W).
**Tables touched (reads)**: `permisos` (vigente filter), `log_transaccional` (chain anchor, if downstream writes).
**FKs traversed**: `permisos` has NO outgoing FKs (catalog); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (if downstream writes).

**Sync behavior**:
- Branch → cloud: NO (this is a cloud admin query; the filter result is used immediately in the same session).
- Cloud → branch: NO (read-only filter).
- DIAN trigger: NO.
- Hash chain impact: NO direct impact on `log_transaccional` (the filter is a read; per SOLID I, reads do not extend the chain). Only the downstream grant (T09) extends the chain.

**Integration with other tables**:
- Reads from: `permisos` (vigente filter), `log_transaccional` (chain anchor if downstream).
- Writes to: NONE for the filter; `permisos_usuario` + `log_transaccional` + `sync_queue` (if downstream).
- Cross-cutting: this is the canonical example of the vigente-set-as-application-layer-rule. The `permisos_usuario` rows MUST reference a vigente `permisos` row at INSERT time (FK enforced); the filter at the admin UI is the friendly UX layer that prevents confusing selections. The DB FK `permisos_usuario.uuid_permiso → permisos.uuid` is RESTRICT (no cascade delete), so the archived permission can never be silently removed.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 13, 24, 31.

## 9. RED Tests
- (RED) `permiso` uniqueness enforced at DB level.
- (RED) Admin-only mutations; operador → 403.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-1.x: `POST /permisos` admin-only.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Orphan `permisos_us` if permission renamed | Low | ON DELETE RESTRICT; rename via UPDATE (new version) |

## 12. Open Questions
- (a) Permission categories (UI vs API vs report)? Currently flat string.