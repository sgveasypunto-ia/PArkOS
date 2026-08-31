# PRD: usuarios_sucursal (T10)

> Bridge table: usuario ↔ sucursal. Defines which branches a user can access.

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
- **Table name**: `prod.usuarios_sucursal`
- **SQL name**: `usuarios_sucursal` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema) + IT-1 (writes)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.

## 3. SOLID Atomic Breakdown
- **S**: "one user assignment to one branch".
- **O**: new columns via migration.
- **I**: `POST /usuarios-sucursal`, `DELETE /usuarios-sucursal/{uuid}` (admin-only); `GET /usuarios-sucursal` (branch reads own).
- **D**: `parkos_core/models/V/usuarios_sucursal.py`.
- **Atomic**: INSERT, UPDATE (revoke).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch |
| `uuid_usuario` | `prod.usuarios.uuid` | exactly one (NOT NULL) | RESTRICT | the user |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | bridge |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin assigns user to branch |
| UPDATE | YES | Inside TX + `log_transaccional` |
| DELETE | NO | Archive |

## 6. CodeGraph Dependencies
- `api_admin/routers/us_sucursal.py`.
- `api_sucursal/routers/us_sucursal.py` (read own).
- `job_sync_cloud::poll_usuarios_sucursal` (IT-1).

## 7. Use Cases enabled by this table

The `usuarios_sucursal` table is the **N:M bridge** between users and branches. Defines which branches a user can access (operator → 1 branch; supervisor → many; admin → all via separate `admin-` JWT path). Versioned projection: unassigning a user from a branch creates a NEW row version with `vigente_hasta=NOW()`. Cloud-only writes (admin manages); branches receive via parametrization pull. **Critical for `X-Sucursal-Context` enforcement on every API call**.

### 7.1 Use Case: `uc.usuarios-sucursal.admin-assigns-supervisor-across-three-branches`

**Actor**: admin.

**Real-world action**: Admin needs to assign a supervisor to 3 branches (Bogotá, Medellín, Cali) so she can review arqueos at any of them. Admin creates the user, then adds 3 `usuarios_sucursal` rows.

**Steps**:
1. Admin opens `web_admin/UsuariosDetail/SucursalesTab` for the supervisor (already created with `rol='supervisor'`).
2. Admin clicks `Add Sucursal`, selects Bogotá from the `sucursal` dropdown.
3. Frontend POSTs `api_admin /usuarios-sucursal` with `{uuid_usuario=$supervisor, uuid_sucursal=Bogotá.uuid, rol_principal='supervisor'}`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=Bogotá.uuid`.
5. INSERT `usuarios_sucursal` row (`vigente_desde=NOW(), vigente_hasta=NULL`).
6. INSERT `log_transaccional` (`accion='usuario_asignado_a_sucursal'`, `datos_anteriores=null, datos_nuevos={user_uuid, sucursal_uuid, rol}`).
7. `queue_processor.enqueue('usuarios_sucursal', uuid, datos)` (parametrization pull).
8. Admin repeats for Medellín and Cali (3 separate POSTs, 3 separate rows).
9. Cloud → each branch within 30s; all 3 branches now have the supervisor in their `usuarios_sucursal` table.

**Tables touched (writes)**: `usuarios_sucursal` (3 rows), `log_transaccional` (3 rows, one per branch), `sync_queue`.
**Tables touched (reads)**: `usuarios` (FK validation), `sucursal` (FK validation), `log_transaccional` (chain anchor per branch).
**FKs traversed**: `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (the admin); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (the branch being assigned to).

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator).
- Cloud → branch: YES — parametrization pull pushes one row to each of the 3 branches (Bogotá, Medellín, Cali) within 30s each.
- DIAN trigger: NO.
- Hash chain impact: YES — each branch's `log_transaccional` chain extends by 1 row (one per assignment, on each respective branch). The cloud chain for each branch also extends by 1 row.

**Integration with other tables**:
- Reads from: `usuarios` (FK validation), `sucursal` (FK validation), `log_transaccional` (chain anchor).
- Writes to: `usuarios_sucursal` (bridge row), `log_transaccional` (audit per branch), `sync_queue` (deferred propagation).
- Downstream: when the supervisor logs in at any of the 3 branches, her JWT will have `sucursales_permitidas = [Bogotá.uuid, Medellín.uuid, Cali.uuid]`.

### 7.2 Use Case: `uc.usuarios-sucursal.operator-login-jwt-scope`

**Actor**: system (api_sucursal on login).

**Real-world action**: When an operator logs in at the booth, the JWT must be scoped to the SINGLE branch they belong to. This is critical for tenancy: an operador JWT from Bogotá cannot read or write data from Medellín.

**Steps**:
1. Operator POSTs `api_sucursal /auth/login` with `email`, `password`.
2. Backend bcrypt-verifies (T07 use case 7.2).
3. Backend SELECTs `usuarios_sucursal` rows WHERE `uuid_usuario=$juan AND vigente_hasta IS NULL`.
4. For `rol='operador'`: expect exactly 1 row → `sucursales_permitidas = [that_single_uuid]`.
5. For `rol='supervisor'`: expect 1..N rows → `sucursales_permitidas = [uuid_1, uuid_2, ...]`.
6. For `rol='admin'`: skip this table (admin uses `admin-` JWT via cloud login, separate path).
7. Backend issues `operador-` JWT with `claims.sucursales_permitidas = [...]`.
8. INSERT `login` row (`estado='exitoso', uuid_usuario, uuid_sucursal=$first_assigned`).
9. INSERT `log_transaccional` (`accion='login_exitoso'`, `datos_nuevos={sucursales_permitidas}`).
10. Every subsequent API call from this session includes the JWT; the API middleware enforces `X-Sucursal-Context` against `sucursales_permitidas`.

**Tables touched (writes)**: `login`, `log_transaccional`.
**Tables touched (reads)**: `usuarios`, `usuarios_sucursal`, `permisos_usuario`, `permisos`, `log_transaccional` (chain anchor).
**FKs traversed**: `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`; `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (login is local).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row per login (`accion='login_exitoso'`).

**Integration with other tables**:
- Reads from: `usuarios`, `usuarios_sucursal` (the bridge — single source of truth for branch scope), `permisos_usuario` (for permission JWT claims), `log_transaccional` (chain anchor).
- Writes to: `login` (audit), `log_transaccional` (audit).
- Cross-cutting: this is THE enforcement point for tenancy. If an operador tries to call `/clientes` with `X-Sucursal-Context: Medellín.uuid` but JWT has `sucursales_permitidas=[Bogotá.uuid]` → 403. The same table is read on every API call via the auth middleware.

### 7.3 Use Case: `uc.usuarios-sucursal.admin-unassigns-operator-from-branch`

**Actor**: admin.

**Real-world action**: An operator (Juan) transferred to another city; admin needs to remove his `usuarios_sucursal` for the old branch so he can no longer log in there. The bridge row is archived via `vigente_hasta=NOW()` (NOT deleted).

**Steps**:
1. Admin opens `web_admin/UsuariosDetail/SucursalesTab` for Juan.
2. Admin clicks `Unassign` on the Bogotá row.
3. Frontend PATCHes `api_admin /usuarios-sucursal/{uuid}` with `{vigente_hasta=NOW()}`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=Bogotá.uuid`.
5. Backend SELECTs the current `usuarios_sucursal` row (the vigente one).
6. Backend INSERT new `usuarios_sucursal` row with `vigente_desde=NOW(), vigente_hasta=NOW()` (unassigned).
7. Backend UPDATE old row `vigente_hasta=NOW()` (archive).
8. INSERT `log_transaccional` (`accion='usuario_designado_de_sucursal'`, `datos_anteriores={vigente: true, user: Juan, branch: Bogotá}, datos_nuevos={vigente: false}`).
9. `queue_processor.enqueue('usuarios_sucursal', uuid_new, datos)` (parametrization pull).
10. Cloud → Bogotá branch within 30s; the branch `usuarios_sucursal` table no longer has the vigente row for Juan.
11. Next time Juan tries to log in at Bogotá → 403 (no vigente `usuarios_sucursal` for his user + branch).
12. If Juan has a `usuarios_sucursal` row for another branch (e.g., Medellín), he can still log in there.

**Tables touched (writes)**: `usuarios_sucursal` (new row + UPDATE old), `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `usuarios_sucursal` (the vigente row to archive), `log_transaccional` (chain anchor).
**FKs traversed**: same as use case 7.1.

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator).
- Cloud → branch: YES — parametrization pull pushes the new row + UPDATE on the old within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row on each side (`accion='usuario_designado_de_sucursal'`).

**Integration with other tables**:
- Reads from: `usuarios_sucursal` (the vigente row to archive), `log_transaccional` (chain anchor).
- Writes to: `usuarios_sucursal` (new + UPDATE old), `log_transaccional` (audit), `sync_queue`.
- Cross-cutting: this is the canonical "off-boarding" pattern. Pair it with `usuarios.estado='archivado'` (T07) for full termination. Just unassigning leaves the user valid in the system but with zero branch access (can't log in anywhere).

### 7.4 Use Case: `uc.usuarios-sucursal.admin-audit-cross-branch-access`

**Actor**: admin

**Real-world action**: Compliance audit: admin needs to know which users currently have access to each branch, identify orphaned assignments (user deactivated but assignment vigente), and prepare a report for SOX-style access review. Admin opens `web_admin/AuditUsuariosSucursal`, filters by `uuid_sucursal` + status. This is a READ-ONLY audit query; per SOLID I (T01 use case `rol-admin-auditor-bypass-rls-reads-no-chain`), the audit query does NOT extend the hash chain.

**Steps**:
1. Admin opens `web_admin/AuditUsuariosSucursal` (separate UI module for access audits).
2. Admin filters: `uuid_sucursal=Bogotá.uuid, vigente=true, usuario_estado='activo'` — get list of active operators with vigente access to Bogotá.
3. Frontend GETs `api_admin /usuarios-sucursal?uuid_sucursal=Bogotá&vigente=true&join=usuarios,permisos_usuario,permisos` (eager load).
4. Backend paginates with cursor; returns rows with JOIN: `{uuid_asignacion, uuid_usuario, usuario.nombre, usuario.estado, usuario.email, usuario.rol, permissions: [...vigente permission strings]}`.
5. Admin drills into specific user; sees `permisos_usuario` history (revoked + vigente).
6. Admin exports the report (no DB write; just file generation).
7. If admin finds an orphaned assignment — user `estado='inactivo'` but `usuarios_sucursal` still vigente — admin clicks `Cleanup` which triggers the deactivation cascade documented in T07 use case `admin-user-deactivation`. The cleanup itself IS a mutation and writes a `log_transaccional` row (`accion='cleanup_orphaned_assignment'`).

**Tables touched (writes)**: NONE for the audit query itself (read-only). If admin clicks `Cleanup`: `log_transaccional` (W, per the cascade), `alerta` (W, for the cleanup event).
**Tables touched (reads)**: `usuarios_sucursal` (vigente set), `usuarios` (user state + name + email JOIN), `permisos_usuario` (permission set JOIN), `permisos` (permission strings JOIN), `sucursal` (the branch context).
**FKs traversed**: `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_permiso` → `permisos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is a cloud admin audit query).
- Cloud → branch: NO (read-only query).
- DIAN trigger: NO.
- Hash chain impact: NO direct impact from the audit query (read-only). Only the downstream `Cleanup` action (if invoked) extends the chain.

**Integration with other tables**:
- Reads from: `usuarios_sucursal`, `usuarios`, `permisos_usuario`, `permisos`, `sucursal`.
- Writes to: NONE for the audit query; `log_transaccional` + `alerta` for cleanup.
- Cross-cutting: this is the canonical cross-table audit join — `usuarios_sucursal` is the bridge that lets admin see WHICH USERS have access to WHICH BRANCHES. Combined with `permisos_usuario` JOIN, admin can produce a full access matrix per branch. The audit is read-only per SOLID I (T01 use case 7.7); any downstream mutation is its own documented use case (e.g., T07 use case `admin-user-deactivation` for the cascade).
- Note: the `vigente_hasta IS NULL` filter is critical — it returns the CURRENT assignment set, not the historical. For historical audit (who had access on date X), use a bi-temporal query with `vigente_desde <= X AND (vigente_hasta IS NULL OR vigente_hasta > X)`.
Layers: 1, 6, 7, 10, 13, 14, 38.

## 9. RED Tests
- (RED) Admin assigns user to 3 branches; `sucursales_permitidas` in JWT contains all 3.
- (RED) Branch reads users from another branch → 403 (tenancy).
- (RED) Cross-audience: admin JWT to branch → 401.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-1.x: `POST /usuarios-sucursal` admin-only.
- [ ] IT-1.x: `job_sync_cloud::poll_usuarios_sucursal` pushes assignments.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| User assigned to too many branches | Low | UI shows count; admin audit |
| Branch decommissioned with users assigned | Low | ON DELETE RESTRICT; manual archive first |

## 12. Open Questions
- (a) Default branch on user creation? Currently admin assigns explicitly.