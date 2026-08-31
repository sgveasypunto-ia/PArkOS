# PRD: permisos_usuario (T09)

> Bridge table: usuario ↔ permiso. Versioned projection.

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
- **Table name**: `prod.permisos_usuario`
- **SQL name**: `permisos_usuario` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite
- **Origin**: F1 (schema) + IT-1 (writes)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.

## 3. SOLID Atomic Breakdown
- **S**: "one permission assignment to one user".
- **O**: new columns via migration.
- **I**: `POST /permisos-us`, `DELETE /permisos-us/{uuid}` (admin-only).
- **D**: `parkos_core/models/V/permisos_usuario.py`.
- **Atomic**: INSERT, UPDATE (revoke via `vigente_hasta`).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_usuario` | `prod.usuarios.uuid` | exactly one (NOT NULL) | RESTRICT | the user |
| `uuid_permiso` | `prod.permisos.uuid` | exactly one (NOT NULL) | RESTRICT | the permission |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | bridge table |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin assigns permission |
| UPDATE | YES (revoke via vigente_hasta) | Inside TX + `log_transaccional` |
| DELETE | NO | Archive |

## 6. CodeGraph Dependencies
- `api_admin/routers/permisos_usuario.py`.
- `parkos_core/auth/require_permission.py`.

## 7. Use Cases enabled by this table

The `permisos_usuario` table is the **N:M bridge** between users and permissions. Versioned projection: revocation doesn't DELETE — it creates a NEW row version with `vigente_hasta=NOW()` (the vigente set is the one with `vigente_hasta IS NULL`). Cloud-only writes (admin manages); branches read-only via parametrization pull.

### 7.1 Use Case: `uc.permisos-usuario.admin-grants-permission-to-operator`

**Actor**: admin

**Real-world action**: Admin needs to grant `aprobar_anulacion` to an operator at the Medellín branch. Admin opens the user's permission tab, selects the permission, and saves. The backend INSERTs the bridge row and propagates to the branch via parametrization pull so the operator can approve anulaciones at the booth.

**Steps**:
1. Admin opens `web_admin/UsuariosDetail/PermisosTab` for operator Juan Pérez (Medellín).
2. Admin clicks `Add Permission`, selects `aprobar_anulacion` from the `permisos` catalog dropdown.
3. Frontend POSTs `api_admin /permisos-usuario` with `{uuid_usuario=$juan, uuid_permiso=$aprobar_anulacion, vigente_desde=NOW()}`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=Medellín.uuid`.
5. Backend validates FKs: `usuarios.estado='activo' AND vigente_hasta IS NULL`, `permisos.estado='activo'`.
6. INSERT `permisos_usuario` row (`vigente_desde=NOW(), vigente_hasta=NULL`).
7. INSERT `log_transaccional` (`accion='permiso_asignado'`, `datos_anteriores=null, datos_nuevos={permiso_uuid, user_uuid, vigente_desde}`).
8. `queue_processor.enqueue('permisos_usuario', uuid, datos)` (parametrization pull).
9. Cloud → Medellín branch within 30s; branch `permisos_usuario` table now has the new row.
10. Next time Juan logs in and calls `require_permission('aprobar_anulacion')`, it returns success.

**Tables touched (writes)**: `permisos_usuario`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `usuarios` (FK validation), `permisos` (FK validation), `usuarios_sucursal` (find the branch to enqueue to), `log_transaccional` (chain anchor).
**FKs traversed**: `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_permiso` → `permisos.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (the admin); `log_transaccional.uuid_sucursal` → `sucursal.uuid` (the operator's branch).

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator — admin action).
- Cloud → branch: YES — parametrization pull pushes the new row to the operator's branch (Medellín) within 30s. The operator's login session on next refresh has the new permission.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row on cloud side (`accion='permiso_asignado'`); branch chain extends by 1 row on branch side when it receives.

**Integration with other tables**:
- Reads from: `usuarios` (FK validation), `permisos` (FK validation), `usuarios_sucursal` (target branch), `log_transaccional` (chain anchor).
- Writes to: `permisos_usuario` (bridge row), `log_transaccional` (audit), `sync_queue` (deferred propagation).
- Downstream: enforcement via `require_permission` (T08 use case 7.2).

### 7.2 Use Case: `uc.permisos-usuario.admin-revokes-permission-from-operator`

**Actor**: admin

**Real-world action**: Operator Juan's role changed — he's no longer allowed to approve anulaciones. Admin clicks `Revoke` on the `aprobar_anulacion` row. Backend creates a NEW row version with `vigente_hasta=NOW()` (the vigente set no longer includes this permission), archives the old, and propagates.

**Steps**:
1. Admin opens `web_admin/UsuariosDetail/PermisosTab` for Juan.
2. Admin clicks `Revoke` on `aprobar_anulacion`.
3. Frontend PATCHes `api_admin /permisos-usuario/{uuid}` with `{vigente_hasta=NOW()}`.
4. Backend opens TX; SELECT chain anchor from `log_transaccional`.
5. Backend SELECTs the current `permisos_usuario` row (the vigente one for this user+permission).
6. Backend INSERT new `permisos_usuario` row with `vigente_desde=NOW(), vigente_hasta=NOW()` (revoked).
7. Backend UPDATE the OLD row's `vigente_hasta=NOW()` (archive; old row no longer vigente).
8. INSERT `log_transaccional` (`accion='permiso_revocado'`, `datos_anteriores={vigente: true}, datos_nuevos={vigente: false}`).
9. `queue_processor.enqueue('permisos_usuario', uuid_new, datos)` (parametrization pull).
10. Cloud → branch within 30s; the branch `permisos_usuario` table now reflects the revoke.
11. Next time Juan calls `require_permission('aprobar_anulacion')`, the vigente set doesn't include it → 403.

**Tables touched (writes)**: `permisos_usuario` (new row + UPDATE old), `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `permisos_usuario` (the vigente row to archive), `log_transaccional` (chain anchor).
**FKs traversed**: same as use case 7.1.

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator).
- Cloud → branch: YES — parametrization pull pushes both the new (revoked) row + the UPDATE on the old within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row per side.

**Integration with other tables**:
- Reads from: `permisos_usuario` (the vigente row), `log_transaccional` (chain anchor).
- Writes to: `permisos_usuario` (new + UPDATE old), `log_transaccional` (audit), `sync_queue`.
- Note: revocation is NEVER a DELETE — both rows remain in the table for audit. The vigente set is the one with `vigente_hasta IS NULL`.

### 7.3 Use Case: `uc.permisos-usuario.operator-login-inherits-permissions`

**Actor**: system

**Real-world action**: When Juan logs in at the booth, the JWT must carry the vigente permission set so the API can enforce it. The login handler reads the vigente `permisos_usuario` rows for the user and packs the permission list into the JWT claims.

**Steps**:
1. Operator Juan POSTs `api_sucursal /auth/login` (T07 use case 7.2).
2. Backend SELECTs `permisos_usuario` rows WHERE `uuid_usuario=$juan AND vigente_hasta IS NULL`.
3. Joins with `permisos` to get the `permiso` strings.
4. Backend issues `operador-` JWT with `claims.permissions = ['facturar', 'reimprimir', 'ver_arqueo']` (whatever is vigente).
5. INSERT `log_transaccional` (`accion='login_con_permisos'`, `datos_nuevos={permissions: [...]}`).
6. Juan uses the JWT on subsequent calls; each `require_permission` middleware call compares the JWT claims vs the requested action.

**Tables touched (writes)**: `login`, `log_transaccional`.
**Tables touched (reads)**: `permisos_usuario`, `permisos` (via JOIN), `usuarios`, `usuarios_sucursal` (for `sucursales_permitidas`), `log_transaccional` (chain anchor).
**FKs traversed**: `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_permiso` → `permisos.uuid`; `login.uuid_usuario` → `usuarios.uuid`.

**Sync behavior**:
- Branch → cloud: NO (login is local to the branch).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row per login (`accion='login_con_permisos'`).

**Integration with other tables**:
- Reads from: `usuarios` (the user), `permisos_usuario` (vigente set), `permisos` (catalog), `usuarios_sucursal` (branch assignment), `log_transaccional` (chain anchor).
- Writes to: `login` (audit), `log_transaccional` (audit).
- Cross-cutting: JWT claims may become stale if admin revokes a permission while operator is logged in. Mitigation: JWT `ttl=12h` (operators re-login daily); plus critical permission revocations may invalidate active JWTs (out of MVP scope).

### 7.4 Use Case: `uc.permisos-usuario.cascade-on-user-deactivation`

**Actor**: admin (in conjunction with T07 use case `admin-user-deactivation`)

**Real-world action**: When admin deactivates an operator (`usuarios.estado='inactivo'` via T07 use case 7.5), the operator's `permisos_usuario` rows are NOT auto-revoked. They remain vigente in the DB but become inert because the user can't authenticate (estado='inactivo' blocks login). If admin REACTIVATES the user later (new `usuarios` version with `estado='activo'`), the same `permisos_usuario` rows are immediately effective again — no manual re-grant needed. This use case documents the cascade relationships explicitly so future maintainers don't break them.

**Steps**:
1. Admin deactivates operator Juan: T07 use case `admin-user-deactivation` runs. New `usuarios` row with `estado='inactivo'`; old row archived.
2. Cascade check (read-only, NOT modification):
   - SELECT `permisos_usuario` rows WHERE `uuid_usuario=$juan AND vigente_hasta IS NULL` → N rows remain vigente (e.g., `facturar`, `reimprimir`, `aprobar_anulacion`).
   - SELECT `usuarios_sucursal` rows WHERE `uuid_usuario=$juan AND vigente_hasta IS NULL` → 1 row remains vigente (Bogotá).
   - SELECT `sesion` rows WHERE `uuid_usuario=$juan AND estado='abierta'` → 0 rows (no active sessions at this moment).
3. Juan tries to log in: API returns 401 (state='inactivo' blocks bcrypt verification flow). No new `login` row written (the failure happens at the auth pre-check, before any DB write).
4. Juan's JWT (if he had an active session before deactivation): cached claims contain `permissions=['facturar', 'reimprimir', 'aprobar_anulacion']`. API middleware doesn't re-check `usuarios.estado` on every request (out of scope for MVP); JWT signature validity is the only check. The session will naturally expire at JWT TTL (12h) or be force-killed on next admin intervention.
5. Admin reactivates Juan: T07 analog of use case 7.5 with `estado='activo'` new version.
6. Juan logs in: bcrypt passes, `usuarios_sucursal` vigente rows provide `sucursales_permitidas=[Bogotá.uuid]`, `permisos_usuario` vigente rows provide `permissions=['facturar', 'reimprimir', 'aprobar_anulacion']`. The same permission set is effective immediately — no manual re-grant.
7. INSERT `login` row (`estado='exitoso'`) + `log_transaccional` (`accion='login_exitoso_post_reactivation'`).

**Tables touched (writes)**: NONE from this use case directly. (The deactivation/reactivation writes happen in T07, the login writes happen in T07 case 7.2.)
**Tables touched (reads)**: `permisos_usuario` (cascade check), `usuarios_sucursal` (cascade check), `usuarios` (state check), `sesion` (active session check), `permisos` (catalog JOIN for permission strings).
**FKs traversed**: `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_permiso` → `permisos.uuid`; `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_usuario` → `usuarios.uuid`; `login.uuid_usuario` → `usuarios.uuid` (when re-logging in).

**Sync behavior**:
- Branch → cloud: NO (cascade check is local to the transaction context).
- Cloud → branch: NO (read-only check).
- DIAN trigger: NO.
- Hash chain impact: NO direct impact (this use case is read-only); the writes from T07 deactivation and the T07 reactivation (when applicable) do extend the chain, but those are documented in T07.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `usuarios_sucursal`, `usuarios`, `sesion`, `permisos`, `log_transaccional` (chain anchor).
- Writes to: NONE.
- Cross-cutting: this is the canonical documentation of the **inert-but-vigente pattern** for permissions and branch assignments. The user state (`usuarios.estado`) is the switch; the permission/assignment tables remain unchanged. This is by design: reactivating a user restores their previous access without manual intervention.
- Risk: if admin DELETES the `permisos_usuario` rows while the user is deactivated (out of pattern; not the recommended path), the user will not regain permissions on reactivation. This is documented as a known anti-pattern in `tasks.md`.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 13, 31, 37.

## 9. RED Tests
- (RED) Admin assigns permission; operador → 403.
- (RED) Revoke sets `vigente_hasta`; FK remains.
- (RED) Cascade check on `usuarios` or `permisos` delete → RESTRICT prevents.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-1.x: `POST /permisos-usuario` admin-only.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Admin grants too many permissions | Low | UI shows count; audit log |

## 12. Open Questions
- (a) Time-bound permissions (e.g., seasonal)? Out of MVP.