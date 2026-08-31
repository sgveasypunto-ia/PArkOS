# PRD: usuarios (T07)

> System users (admin, operador, supervisor). Versioned projection.

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
- **Table name**: `prod.usuarios`
- **SQL name**: `usuarios` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite (until archive)
- **Versioning**: YES
- **Origin**: F1 (schema) + IT-1 (writes)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `cedula` is unique natural key. `email` is unique login identifier. `password_hash` is bcrypt.

## 3. SOLID Atomic Breakdown
- **S**: "one system user".
- **O**: new columns via migration.
- **I**: `POST /us`,`, `GET /us`,`, `GET /us`,`/{uuid}`, `PATCH /us`,`/{uuid}`.
- **D**: API depends on `parkos_core.models.V.usuarios.Usuarios`; bcrypt via `parkos_core.auth.passwords`.
- **Atomic**: INSERT, UPDATE creates new row + archive old.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | usuarios is FK source for many |

### Incoming FKs (heavy FK target)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `permisos_usuario.uuid_usuario` | \|\|--o{ | permissions assigned to user |
| `usuarios_sucursal.uuid_usuario` | \|\|--o{ | user assigned to branches |
| `login.uuid_usuario` | \|\|--o{ | login attempts |
| `reimpresion_ticket.uuid_usuario` | \|\|--o{ | operator who issued reprint |
| `anulaciones.uuid_usuario` | \|\|--o{ | admin who authorized |
| `sesion.uuid_usuario` | \|\|--o{ | operator who opened sesion |
| `alerta.uuid_usuario` | \|\|--o{ | current responsible user |
| `log_transaccional.uuid_usuario` | \|\|--o{ | actor of every event |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Server-generated UUID |
| UPDATE | YES (creates new version; archive old) | Inside TX + `log_transaccional` write |
| DELETE | NO | Archive via UPDATE |

## 6. CodeGraph Dependencies
- `api_admin/routers/usuarios.py`.
- `api_sucursal/routers/auth.py` (uses `usuarios` for login lookup).
- `parkos_core/auth/passwords.py` (bcrypt).
- `job_sync_cloud::poll_usuarios` (IT-1).
- `web_admin/UsuariosList`, `web_sucursal/LoginForm`.

## 7. Use Cases enabled by this table

The `usuarios` table is the **system users catalog** (admin, operador, supervisor). Versioned projection: every change creates a NEW row with `vigente_desde=NOW()` and archives the old (`vigente_hasta=NOW()`). The `password_hash` is bcrypt (factor 12); the `cedula` is the unique legal identifier; the `email` is the login identifier. Cloud admin writes; branches receive via parametrization pull.

### 7.1 Use Case: `uc.usuarios.admin-onboards-branch-operator`

**Actor**: admin

**Real-world action**: Admin creates a new branch operator for the Bogotá branch: fills the form with `cedula`, `email`, `password`, `rol='operador'`, `sucursales_permitidas=[Bogotá.uuid]`. Backend bcrypts the password, INSERTs the row, INSERTs the `usuarios_sucursal` bridge, and queues parametrization pull so the branch receives the new operator.

**Steps**:
1. Admin opens `web_admin/UsuariosList` → `UsuariosForm`.
2. Admin fills `nombre='Juan', apellido='Pérez', cedula='1234567890', email='juan@bogota.parkos.co', password='temp123', rol='operador', sucursales_permitidas=[Bogotá.uuid]`.
3. Frontend POSTs `api_admin /usuarios` with payload.
4. Backend bcrypt-hashes password (factor 12).
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=Bogotá.uuid`.
6. INSERT `usuarios` row (`vigente_desde=NOW(), vigente_hasta=NULL, fecha_creacion=NOW()`).
7. For each `uuid_sucursal` in payload: INSERT `usuarios_sucursal` row (`uuid_usuario=$new, uuid_sucursal=Bogotá.uuid, vigente_desde=NOW()`).
8. INSERT `permisos_usuario` rows (one per default permission for `rol='operador'`: e.g., `facturar`, `reimprimir`, `ver_arqueo`).
9. INSERT `log_transaccional` (`accion='usuario_creado'`, `tabla_afectada='usuarios'`, `uuid_registro_afectado=$new`).
10. `queue_processor.enqueue('usuarios', uuid, datos)` + enqueue `usuarios_sucursal` + `permisos_usuario` (3 separate queue items).
11. Cloud → branch parametrization pull pushes all 3 to the Bogotá branch within 30s.

**Tables touched (writes)**: `usuarios`, `usuarios_sucursal`, `permisos_usuario`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `sucursal` (the assigned branch), `permisos` (catalog for default permissions), `log_transaccional` (chain anchor).
**FKs traversed**: `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_permiso` → `permisos.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (the admin who created); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is cloud→branch direction).
- Cloud → branch: YES — parametrization pull pushes `usuarios` + `usuarios_sucursal` + `permisos_usuario` to the assigned branch within 30s. Branch DB now has the operator's row + branch assignment + permissions; ready for login.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row on cloud side (`accion='usuario_creado'`); branch chain extends by 1 row on branch side when it receives the parametrization pull.

**Integration with other tables**:
- Reads from: `sucursal` (the branch to assign to), `permisos` (default permissions for the rol), `log_transaccional` (chain anchor).
- Writes to: `usuarios` (new row), `usuarios_sucursal` (bridge), `permisos_usuario` (bridge), `log_transaccional` (audit), `sync_queue` (deferred parametrization).
- Downstream: when the operator logs in at the branch, `usuarios_sucursal` is read to populate the JWT's `sucursales_permitidas` claim.

### 7.2 Use Case: `uc.usuarios.operator-login-at-branch-booth`

**Actor**: operator

**Real-world action**: At the start of shift, the operator arrives at the booth and types their `email` + `password` into `web_sucursal/LoginForm`. The system bcrypt-verifies, looks up `usuarios_sucursal` for the JWT's `sucursales_permitidas` claim, and issues an `operador-` JWT scoped to the single branch.

**Steps**:
1. Operator arrives at the booth, opens `web_sucursal/LoginForm` (auto-loaded on cold start).
2. Operator **types `email='juan@bogota.parkos.co'`** and **`password='temp123'`**.
3. Frontend POSTs `api_sucursal /auth/login`.
4. Backend SELECTs `usuarios WHERE email=$email AND vigente_hasta IS NULL AND estado='activo'` — finds the operator's row.
5. `bcrypt.verify(password, row.password_hash)` — success.
6. Backend SELECTs `usuarios_sucursal` rows WHERE `uuid_usuario=$uuid AND vigente_hasta IS NULL` — for `rol='operador'`, returns exactly 1 row (Bogotá.uuid).
7. Backend issues `operador-` JWT (`kid=operador-...`, `ttl=12h`, `claims={uuid_usuario, rol='operador', sucursales_permitidas=[Bogotá.uuid]}`).
8. INSERT `login` row (`estado='exitoso'`, `uuid_usuario, uuid_sucursal=Bogotá.uuid`).
9. INSERT `log_transaccional` (`accion='login_exitoso'`, `tabla_afectada='usuarios'`).
10. Return `{jwt, uuid_usuario, sucursales_permitidas}` to frontend.
11. Frontend stores JWT in IndexedDB; PWA loads `IngresoForm` (default screen at start of shift).
12. INSERT `login` attempt audit row (`estado='fallido'`) if bcrypt verify fails — separate use case (use case 7.3).

**Tables touched (writes)**: `login`, `log_transaccional`.
**Tables touched (reads)**: `usuarios` (lookup), `usuarios_sucursal` (branch assignment), `log_transaccional` (chain anchor).
**FKs traversed**: `usuarios.uuid` (lookup); `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid` (for JWT claim); `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (login is a branch-local event; the `login` row is NOT enqueued — `login` is `[L-S]`, locally scoped).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row per successful login (`accion='login_exitoso'`).

**Integration with other tables**:
- Reads from: `usuarios` (the operator), `usuarios_sucursal` (branch assignment for JWT claim), `log_transaccional` (chain anchor).
- Writes to: `login` (audit), `log_transaccional` (audit).
- Downstream: every subsequent API call from this session includes the JWT; the API enforces `X-Sucursal-Context` against `sucursales_permitidas`.

### 7.3 Use Case: `uc.usuarios.failed-login-attempt-locks-account`

**Actor**: system

**Real-world action**: Someone tries to log in with a wrong password 5 times in a row. The system records each failed attempt in `login` (separate row each time), emits an `alerta tipo_alerta='repeated_failed_login'` at threshold 5, and after threshold 10 the account is temporarily locked (`usuarios.estado='bloqueado'`).

**Steps**:
1. Unknown person (or operator forgetting password) POSTs `api_sucursal /auth/login` with `email='juan@...'`, `password='wrong_guess_1'`.
2. Backend SELECTs `usuarios WHERE email=$email AND vigente_hasta IS NULL` — finds the row.
3. `bcrypt.verify('wrong_guess_1', row.password_hash)` — FAILS.
4. INSERT `login` row (`estado='fallido'`, `motivo='wrong_password', uuid_usuario=$uuid`).
5. INSERT `log_transaccional` (`accion='login_fallido'`, `datos_nuevos={intento:1}`).
6. Returns 401 to frontend.
7. (Repeat 4 more times → after intento #5): INSERT `alerta` (`tipo_alerta='repeated_failed_login', estado='abierta', uuid_usuario=$uuid, observaciones='5 intentos fallidos'`).
8. (Repeat 5 more times → after intento #10): backend creates new `usuarios` row version with `estado='bloqueado', vigente_hasta=NULL` (the bloqueo row), archives old row.
9. INSERT `log_transaccional` (`accion='usuario_bloqueado'`, `datos_anteriores={estado:'activo'}, datos_nuevos={estado:'bloqueado'}`).
10. `queue_processor.enqueue('usuarios', uuid_new, datos)` → parametrization pull to the branch + sync to cloud's `usuarios` master.

**Tables touched (writes)**: `login` (N rows), `log_transaccional` (N+1 rows), `alerta` (at threshold 5), `usuarios` (new version + archive old at threshold 10), `sync_queue`.
**Tables touched (reads)**: `usuarios` (lookup), `login` (rate counting), `log_transaccional` (chain anchor).
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — `login` rows are local-only `[L-S]`, but `usuarios` (the bloqueo row) propagates to cloud via parametrization pull (cloud→branch is actually the master; branch→cloud carries the new version).
- Cloud → branch: YES — when admin unlocks (use case 7.4), cloud pushes the new active row to branch.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by N+1 rows (one per failed attempt + one for bloqueo at threshold 10).

**Integration with other tables**:
- Reads from: `usuarios` (lookup + rate counting), `login` (count), `log_transaccional` (chain anchor).
- Writes to: `login` (audit), `log_transaccional` (audit), `alerta` (threshold 5), `usuarios` (threshold 10), `sync_queue` (deferred).
- Cross-cutting: the rate-limit counter lives in `login` rows (separate per attempt) or in `log_transaccional` for cloud aggregation; admin can unlock via `web_admin/UsuariosDetail/Unlock`.

### 7.4 Use Case: `uc.usuarios.admin-resets-password-and-archives-old`

**Actor**: admin

**Real-world action**: An operator forgot their password. Admin clicks `Reset Password`, the backend creates a NEW `usuarios` row version (new `password_hash`), archives the OLD row (`vigente_hasta=NOW()`), AND emits a `log_transaccional` row. The branch receives the new row via parametrization pull and the old row is no longer valid for login.

**Steps**:
1. Admin opens `web_admin/UsuariosDetail`; clicks `Reset Password`.
2. Frontend PATCHes `api_admin /usuarios/{uuid}` with `{password: 'new_temp_pwd'}` (admin chooses temp password; operator must change on first login).
3. Backend bcrypt-hashes new password (factor 12).
4. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
5. Backend SELECTs the current `usuarios` row (the vigente one).
6. Backend INSERT new `usuarios` row with `vigente_desde=NOW(), vigente_hasta=NULL, password_hash=$new_hash, fecha_cambio_password=NOW()`.
7. Backend UPDATE old row `vigente_hasta=NOW()` (archive).
8. INSERT `log_transaccional` (`accion='password_reset'`, `datos_anteriores={password_hash: '<old>'}, datos_nuevos={password_hash: '<new>'}`).
9. `queue_processor.enqueue('usuarios', uuid_new, datos)`.
10. Cloud → branch parametrization pull pushes the new row; operator can now log in with the new password.

**Tables touched (writes)**: `usuarios` (new row + UPDATE old), `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `usuarios` (the vigente row to archive), `log_transaccional` (chain anchor).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid` (the admin who did it); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator — admin action).
- Cloud → branch: YES — parametrization pull pushes the new row within 30s. Branch DB now has the new `vigente` row; old row remains archived locally for audit.
- DIAN trigger: NO.
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row on cloud side (`accion='password_reset'`); branch chain extends by 1 row on branch side when it receives.

**Integration with other tables**:
- Reads from: `usuarios` (the vigente row), `log_transaccional` (chain anchor).
- Writes to: `usuarios` (new + UPDATE old), `log_transaccional` (audit), `sync_queue`.
- Cross-cutting: the OLD `password_hash` is in `datos_anteriores` of the log row — for forensic purposes, NEVER store the new password in `datos_nuevos` (only the new bcrypt digest).

### 7.5 Use Case: `uc.usuarios.admin-user-deactivation`

**Actor**: admin

**Real-world action**: An operator (Juan) left the company or transferred permanently. Admin opens `web_admin/UsuariosDetail`, clicks `Deactivate User`. The `[V]` UPDATE pattern creates a NEW `usuarios` row version with `estado='inactivo', vigente_desde=NOW()` and archives the OLD row with `vigente_hasta=NOW()`. Both operations are in the same TX with the chain-extending `log_transaccional` write. **Critically: this cascades to all `permisos_usuario` vigente rows + all `usuarios_sucursal` vigente rows + all active `login` / `sesion` rows for this user — none are revoked individually; they remain "vigente" in the DB but are inert because the user can't log in (`estado='inactivo'` blocks authentication).**

**Steps**:
1. Admin opens `web_admin/UsuariosDetail` for Juan; clicks `Deactivate User`.
2. Frontend PATCHes `api_admin /usuarios/{uuid}` with `{estado: 'inactivo', motivo: 'employee_left_company'}`.
3. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch_of_juan` (the user's primary branch, derived from `usuarios_sucursal`).
4. SELECT the current `usuarios` row (vigente one) for archiving.
5. INSERT new `usuarios` row with `vigente_desde=NOW(), vigente_hasta=NULL, estado='inactivo'`, all other fields copied (or selectively cleared per policy; e.g., `password_hash=NULL` to fully invalidate credentials).
6. UPDATE OLD `usuarios` row `vigente_hasta=NOW()` (archive).
7. INSERT `log_transaccional` (`accion='usuario_desactivado'`, `tabla_afectada='usuarios'`, `datos_anteriores={estado:'activo'}, datos_nuevos={estado:'inactivo', motivo, fecha_desactivacion}`).
8. `queue_processor.enqueue('usuarios', uuid_new, datos)` (parametrization pull to assigned branches within 30s).
9. Cascade check (read-only): SELECT count of `permisos_usuario` vigente rows for this user (still vigente; no auto-revoke); SELECT count of `usuarios_sucursal` vigente rows for this user; SELECT count of active `sesion` rows for this user.
10. For each active `sesion` row (`estado='abierta'`): INSERT `log_transaccional` (`accion='sesion_invalidada_por_usuario_desactivado'`) and notify the branch admin (alerta chain root `tipo_alerta='user_deactivation_force_logout'`). The `sesion` row itself is NOT closed via UPDATE — that's an `[L-S]` operation that would require its own TX with log row; instead, the user simply can't authenticate new requests, and active sessions are marked for forced logout on next JWT validation.
11. Branch receives parametrization pull: local `usuarios` table now has the new inactive row; old row archived. Login attempts for this user return 401 even with correct password (state='inactivo' blocks).

**Tables touched (writes)**: `usuarios` (new row + UPDATE old), `log_transaccional`, `sync_queue`, `alerta` (for active sessions).
**Tables touched (reads)**: `usuarios` (vigente row), `permisos_usuario` (cascade check), `usuarios_sucursal` (cascade check), `sesion` (active session check), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `log_transaccional.uuid_usuario` → `usuarios.uuid` (the admin); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` (read-only check); `usuarios_sucursal.uuid_usuario` → `usuarios.uuid` (read-only check); `sesion.uuid_usuario` → `usuarios.uuid` (read-only check); `sesion.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain).

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator — admin action).
- Cloud → branch: YES — parametrization pull pushes the new inactive `usuarios` row + the archived old row to the assigned branch within 30s. Branch `usuarios` table now reflects the deactivated state.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (`accion='usuario_desactivado'`); branch chain extends by 1 row when received. If active `sesion` rows existed, additional `log_transaccional` rows are written for each (chain extends per session).

**Integration with other tables**:
- Reads from: `usuarios` (vigente row), `permisos_usuario` (cascade check), `usuarios_sucursal` (cascade check), `sesion` (active sessions), `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `usuarios` (new + UPDATE old), `log_transaccional` (audit), `sync_queue` (parametrization pull), `alerta` (active-session forced-logout notifications).
- Cross-cutting: this is the canonical "off-boarding" pattern. Pair with T10 use case `admin-unassigns-operator-from-branch` for full termination: deactivate user → unassign from branch → optionally archive `usuarios.estado='archivado'` (new version).
- **Important note**: `permisos_usuario` and `usuarios_sucursal` rows are NOT auto-revoked (their `vigente_hasta` remains NULL). They become inert because the user can't authenticate. This preserves the audit trail: if the user is reactivated later, the same permissions and branch assignments come back without manual re-creation. The `vigente` set is interpreted per the user state: `estado='activo' AND vigente_hasta IS NULL`.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 8, 10, 11, 12, 13, 14, 15, 16, 17, 20, 24, 25, 26, 28, 31, 36, 37, 38.

## 9. RED Tests
- (RED) PATCH creates new row + archive old.
- (RED) Cross-audience: operador JWT to `api_admin /usuarios` → 401.
- (RED) bcrypt verify on login; wrong password → 401.
- (RED) `cedula` unique; duplicate → UNIQUE violation.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-1.x: `api_admin/routers/usuarios.py::POST /usuarios` + bcrypt hash.
- [ ] IT-1.x: `api_sucursal/routers/auth.py::POST /auth/login` with bcrypt verify.
- [ ] IT-1.x: `job_sync_cloud::poll_usuarios` pushes us to assigned branches.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| bcrypt too slow | Low | Factor 12 |
| Password reset leak | Low | Reset creates new row version; old invalidated |
| User assigned to wrong branch | Low | `usuarios_sucursal` audit + admin UI |

## 12. Open Questions
- (a) MFA required for admin? Out of MVP scope.