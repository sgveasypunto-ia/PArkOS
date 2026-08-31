# PRD: login (T42)

> `[L-S]` audit trail of every login attempt (exitoso → cerrado, or fallido). `timestamp_evento` (when the attempt happened at the operator's device) diverges from `created_at` (when the DB registered the row) in offline mode. UPDATE permitted ONLY on `estado='cerrado'` via `ls_session_update_guard` trigger, with `log_transaccional` INSERT mandatory in the same TX. The three issuers (`admin-`, `operador-`, `sync-agent-`) validate `iss + aud + kid` per AGENTS.md. Failed attempts trigger `alerta tipo_alerta='login_lockout'` after N consecutive failures (T30/T41). First operator login after branch boot triggers parametrization pull verification.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule S: login is the single audit point for auth events*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[L-S]` table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.login`
- **SQL name**: `login` (with `prod` schema)
- **Enforcement level**: `[L-S]` session/cycle (UPDATE permitted only on `estado='cerrado'` via `ls_session_update_guard`)
- **Retention**: 5+ years (security audit + DIAN compliance — login is the audit point for all user actions)
- **Hash chain**: NO (operational audit, not source-of-truth for compliance)
- **Origin**: F1 (schema + REVOKE + `ls_session_update_guard` trigger) + IT-1 (writes from auth flow)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; 5 use cases covering successful/failed/offline/logout/lockout + the 3-JWT-issuer validation pattern)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `timestamp_evento` is the moment the attempt happened at the operator's device (NOT NULL); `created_at` is when the DB registered the row (server default NOW()). In offline mode, the gap = time in `sync_queue` queue.
- Travel: branch-origin rows travel to cloud via `sync_queue` within 30s. Cloud-origin rows (admin logins) do NOT travel back to branches.
- **UPDATE constraint**: only `estado='cerrado'` transition (logout) is permitted. Trigger `ls_session_update_guard` enforces (a) the only column being UPDATEd is `estado`, and (b) an INSERT into `log_transaccional` occurs in the SAME TX. Any other UPDATE (e.g., changing `uuid_usuario`, `timestamp_evento`) is rejected with `LS_SESSION_FORBIDDEN_COLUMN`.

## 3. SOLID Atomic Breakdown
- **S**: "one login attempt (success, failure, or logout closure)" — INSERT in same TX as bcrypt verify + JWT issue.
- **O**: extensible via migration; new columns (e.g., `ip_origen`, `user_agent`) for forensic detail.
- **I**: branch operator API (writer — `POST /auth/login`); cloud admin API (writer — `POST /admin/auth/login`); branch sync_agent (writer — `POST /sync/pair`); admin read API (`LoginAuditPanel` paginated, filterable by `uuid_usuario`, `estado`, `fecha`).
- **D**: `parkos_core/auth/login.py::attempt_login(email, password, uuid_sucursal, ip=None, user_agent=None)` (the ONLY writer for `exitoso`/`fallido`); `parkos_core/auth/logout.py::close_session(uuid)` (the ONLY writer for `cerrado` via the `[L-S]` UPDATE exception).
- **Atomic**: INSERT for new login attempts; UPDATE (only `estado='cerrado'`) for logout, gated by `ls_session_update_guard` + concurrent `log_transaccional` write in same TX. REVOKE UPDATE/DELETE on other columns / on non-logout transitions.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_usuario` | `prod.usuarios.uuid` | exactly one (NOT NULL) | RESTRICT | the user attempting login |
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch where the attempt occurred |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| (none — `login` is leaf for auth audit; the `alerta tipo_alerta='login_lockout'` is emitted via cross-table query, not FK) | | | |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `login.py::attempt_login()` per attempt |
| UPDATE `estado='cerrado'` | YES (only via `ls_session_update_guard` + concurrent `log_transaccional`) | Inside TX, by `logout.py::close_session()` |
| UPDATE other columns / other transitions | NO | `ls_session_update_guard` trigger raises `LS_SESSION_FORBIDDEN_COLUMN` |
| DELETE | NO | Append-only |

**Special rules**:
- **`ls_session_update_guard` trigger** (per AGENTS.md): validates (a) only `estado` is being modified (NEW.estado='cerrado' AND OLD.estado IN ('exitoso', 'cerrado')), (b) the TX includes a `log_transaccional` INSERT for the same `uuid_sucursal` with `accion='logout'`. On violation: RAISE EXCEPTION.
- **`timestamp_evento` vs `created_at` divergence**: in offline mode, `created_at` may be hours/days after `timestamp_evento`. Admin queries that need "when did the user actually try to login" MUST use `timestamp_evento`, not `created_at`.
- **No UPDATE on failed login**: a `fallido` row stays `fallido` forever — it cannot be retroactively changed to `exitoso`. If the user then succeeds, a NEW row is INSERTed with `estado='exitoso'`.
- **Three JWT issuers validated per token**: `kid` prefix identifies the issuer (`admin-`, `operador-`, `sync-agent-`). `iss` + `aud` must match: admin JWT can ONLY be used for `api_admin` endpoints; operador JWT can ONLY be used for `api_sucursal`; sync-agent JWT can be used for both `api_admin` and `api_sucursal` sync endpoints.
- **`operador-` issuer carries `uuid_sucursal`**: the JWT payload includes `uuid_sucursal` (the branch the operator works at). Cross-branch access is impossible without re-login at the target branch.
- **`sync-agent-` issuer is long-lived (90d)**: issued during pairing (T11 use case 7.2 — meta-PRD-03); used by `job_sync_*` workers.

## 6. CodeGraph Dependencies
- `parkos_core/auth/login.py::attempt_login()` (sole writer for `exitoso`/`fallido`).
- `parkos_core/auth/logout.py::close_session()` (sole writer for `cerrado` UPDATE).
- `parkos_core/auth/jwt_three_issuers.py::verify_token()` (RS256 + iss/aud/kid validation).
- `parkos_core/auth/login_lockout_monitor.py` (counts failed attempts, emits `alerta tipo_alerta='login_lockout'`).
- `api_sucursal/routers/auth.py::POST /auth/login` (operator endpoint).
- `api_sucursal/routers/auth.py::POST /auth/logout` (operator endpoint, triggers `cerrado` UPDATE).
- `api_admin/routers/auth.py::POST /admin/auth/login` (cloud admin endpoint).
- `api_admin/routers/auth.py::POST /admin/auth/logout` (cloud admin endpoint).
- `api_admin/routers/login.py::GET /login` (audit view, paginated, filterable).
- `web_sucursal/LoginForm` (operator login UI; supports offline cached credentials).
- `web_admin/LoginForm` (cloud admin login UI).
- `web_admin/LoginAuditPanel` (cross-branch login history).

## 7. Use Cases enabled by this table

The `login` table is the **canonical audit point for every authentication event** across all three JWT issuers. Every successful login, every failed attempt, every logout is a row. The `[L-S]` UPDATE constraint on `estado='cerrado'` ensures that a logout is the ONLY mutation after the initial INSERT, and that mutation MUST be accompanied by a `log_transaccional` row in the same TX. The 5 use cases below cover the full auth lifecycle: successful login (with the 3-issuer validation), failed login (with the lockout alert trigger), offline login (with the timestamp divergence), logout (with the UPDATE constraint), and lockout emission (with the cross-table alert flow). **No cámaras, no OCR, no QR**: login is email + password typed manually.

### 7.1 Use Case: `uc.login.operator-successful-online-jwt-issued`

**Actor**: operator (branch)

**Real-world action**: Operator opens `web_sucursal/LoginForm`, types email and password, submits. Backend SELECTs `usuarios` row by email (branch-scoped — the operator's `usuarios_sucursal` must include the branch), bcrypt verifies password hash, SELECTs `permisos_usuario` for permissions, issues `operador-` JWT (medium-lived, 8h TTL, branch-pinned via `uuid_sucursal`). INSERTs `login` row with `estado='exitoso'`, INSERTs `log_transaccional`, enqueues for sync.

**Steps**:
1. Operator opens `web_sucursal/LoginForm` (PWA, loaded from IndexedDB cache). Form pre-fills the operator's branch UUID (from JWT cookie or local storage).
2. Operator types email `operador1@easypunto.example` and password.
3. Frontend POSTs `api_sucursal /auth/login` with `{email, password, uuid_sucursal}`.
4. Backend: SELECT `usuarios` (via email + `usuarios_sucursal.uuid_sucursal=$branch` JOIN to verify the operator works at this branch). Returns the `usuarios` row + `password_hash`.
5. bcrypt.verify(password, usuarios.password_hash) → success.
6. Verify `usuarios.estado='activo'` (if `bloqueado` from `login_lockout`: 423 Locked).
7. SELECT `permisos_usuario` rows WHERE `uuid_usuario=$user AND vigente_hasta IS NULL` → permission list.
8. Issue `operador-` JWT via `jwt_three_issuers.sign(issuer='operador-', kid='operador-2026-01', claims={sub: $user_uuid, uuid_sucursal: $branch, permisos: [...], aud: 'api_sucursal', iat: NOW(), exp: NOW() + 8h})`.
9. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
10. INSERT `login` row (`uuid=server-generated`, `uuid_usuario=$user`, `uuid_sucursal=$branch`, `timestamp_evento=$client_timestamp` (from JWT issuer's clock), `estado='exitoso'`, `created_at=NOW()`).
11. INSERT `log_transaccional` (`accion='login_exitoso'`, `tabla_afectada='login'`, `uuid_registro_afectado=$login_uuid`, `uuid_usuario=$user`, `uuid_sucursal=$branch`, `datos_nuevos={email, permisos_count, jwt_ttl: 8h, jwt_issuer:'operador-'}`).
12. `queue_processor.enqueue('login', $uuid, $snapshot)` — propagates to cloud within 30s.
13. INSERT `sync_log` (cycle metric — successful login counted as 1 cycle event).
14. Backend returns `{access_token: <jwt>, expires_at, role: 'operador', permisos: [...]}`.
15. Frontend stores JWT in HttpOnly cookie + IndexedDB (for offline fallback).

**Tables touched (writes)**: `login` (1 row), `log_transaccional` (1 row), `sync_queue` (1 item), `sync_log` (1 row).
**Tables touched (reads)**: `usuarios` (email lookup + password_hash), `usuarios_sucursal` (branch scoping), `permisos_usuario` (permissions), `configuracion_seguridad` (vigente — for lockout thresholds, NOT applied here), `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `permisos_usuario.uuid_permiso` → `permisos.uuid`; `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `login.uuid`.

**Sync behavior**:
- Branch → cloud: YES (the login row propagates with hash chain verification).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row (the `log_transaccional`).

**Integration with other tables**:
- Reads from: `usuarios`, `usuarios_sucursal`, `permisos_usuario`, `configuracion_seguridad`, `log_transaccional`, `sucursal`.
- Writes to: `login`, `log_transaccional`, `sync_queue`, `sync_log`.
- Cross-cutting: this is the canonical **operator login** flow. The `operador-` JWT carries `uuid_sucursal` in its payload — cross-branch access requires re-login. The `permisos` list is embedded in the JWT (not re-queried per request); sprint 5 may move to permission re-query for finer-grained revocation.
- Related: T07 (`usuarios`) covers the version flow for the `estado` lifecycle; T30 (`configuracion_seguridad`) covers the thresholds consulted by `login_lockout_monitor`.

### 7.2 Use Case: `uc.login.operator-failed-bcrypt-mismatch-emits-lockout-after-N`

**Actor**: operator (branch) + system (`login_lockout_monitor`)

**Real-world action**: Operator types wrong password. Backend bcrypt verify fails. INSERT `login` row with `estado='fallido'`. The `login_lockout_monitor` (called inline OR via 60s cron) SELECTs failed login count for the user within the lockout window. If count >= `configuracion_seguridad.max_intentos_login` (default 5), emits `alerta tipo_alerta='login_lockout'` (T41 use case 7.5). The user account is marked `estado='bloqueado'` (new `usuarios` version with `vigente_hasta=NOW()` on the active version).

**Steps**:
1. Operator POSTs `api_sucursal /auth/login` with wrong password.
2. Backend: SELECT `usuarios` by email — returns the row.
3. bcrypt.verify(password, usuarios.password_hash) → FAIL.
4. Backend opens TX; SELECT chain anchor from `log_transaccional`.
5. INSERT `login` row (`uuid=server-generated`, `uuid_usuario=$user`, `uuid_sucursal=$branch`, `timestamp_evento=$client_timestamp`, `estado='fallido'`, `created_at=NOW()`). The row is FALLIDO — no UPDATE will ever change it.
6. INSERT `log_transaccional` (`accion='login_fallido'`, `tabla_afectada='login'`, `uuid_registro_afectado=$login_uuid`, `datos_nuevos={email, motivo:'password_mismatch'}`).
7. `queue_processor.enqueue('login', $uuid, $snapshot)`.
8. Return 401 Unauthorized `{detail: 'invalid_credentials'}`. NO information about whether email exists (security: avoid user enumeration).
9. `login_lockout_monitor` (inline call OR cron every 60s) runs SELECT: `SELECT COUNT(*) FROM login WHERE uuid_usuario=$user AND estado='fallido' AND created_at > NOW() - INTERVAL '15 minutes'`.
10. If count >= 5 AND no open `alerta tipo_alerta='login_lockout'` for this user: `alerta_writer.write_alerta(uuid_sucursal=$branch, tipo_alerta='login_lockout', uuid_usuario=$user, observaciones='failed_attempts=$count, window_min=15, max_intentos=5')`.
11. INSERT `alerta` workflow root (T41 use case 7.5).
12. UPDATE `usuarios`: archive current version (`vigente_hasta=NOW()`); INSERT new version with `estado='bloqueado', vigente_desde=NOW()`. INSERT `log_transaccional` (`accion='usuario_bloqueado'`).
13. Subsequent login attempts with same email: backend SELECTs `usuarios` → finds `estado='bloqueado'` → returns 423 Locked (no bcrypt attempt).
14. Admin sees the alert in `web_admin/AlertasList` filter `tipo_alerta='login_lockout'`. Admin clicks → `AlertaDetail` → drills into the user → clicks `Unlock` → INSERT new `usuarios` version with `estado='activo'`; INSERT new `alerta` chain row with `estado='resuelta', uuid_alerta_padre=$root.uuid`.

**Tables touched (writes)**: `login` (1 row fallido), `log_transaccional` (1-2 rows), `sync_queue` (1 item), `alerta` (1 root row), `usuarios` (2 versions: archive + new bloqueado).
**Tables touched (reads)**: `usuarios`, `usuarios_sucursal`, `configuracion_seguridad` (vigente for thresholds), `login` (failed count), `alerta` (open check), `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (the LOCKED user, not the SYSTEM actor); `alerta.uuid_sucursal` → `sucursal.uuid`; `usuarios` (no outgoing FKs); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `login.uuid` or `alerta.uuid` or `usuarios.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the fallido login row + the alerta + the usuarios version change all propagate.
- Cloud → branch: NO (lockout is branch-side enforcement).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 2-3 rows.

**Integration with other tables**:
- Reads from: `usuarios`, `usuarios_sucursal`, `configuracion_seguridad`, `login`, `alerta`, `log_transaccional`, `sucursal`.
- Writes to: `login` (fallido), `log_transaccional`, `sync_queue`, `alerta` (login_lockout root), `usuarios` (version: bloqueado).
- Cross-cutting: the `[L-S]` constraint is critical here — the fallido row NEVER changes. Each subsequent failed attempt is a NEW row. The lockout counter is computed by `COUNT(*)` over the time window, not by mutating an existing row.
- Related: T41 (`alerta`) use case 7.5 covers the lockout emission in detail; T30 (`configuracion_seguridad`) covers the thresholds (default 5 attempts, 15 min window, configurable).

### 7.3 Use Case: `uc.login.operator-offline-timestamp-evento-vs-created-at-divergence`

**Actor**: operator (branch, offline mode)

**Real-world action**: Branch lost internet connectivity. Operator still needs to login to continue operations. The PWA's IndexedDB has cached credentials (hashed email + bcrypt verification is local-only). Operator types email + password. Frontend validates locally (bcrypt verify against cached hash), issues a SHORT-LIVED local JWT (4h TTL instead of 8h, marked `iat_offline=true`). Backend INSERTs `login` row with `timestamp_evento=$client_time (which is the time the operator actually tried — could be hours before reconnect)` and `created_at=NOW() (the time the DB registered the row — at reconnect)`. The divergence = time in offline mode.

**Steps**:
1. Branch offline (no internet). Operator opens `web_sucursal/LoginForm` (loaded from PWA cache, all UI elements from IndexedDB).
2. Frontend: bcrypt verify against cached `usuarios.password_hash` in IndexedDB (loaded during last parametrization pull). Success.
3. Frontend issues local `operador-` JWT via `jwt_three_issuers.sign(issuer='operador-', kid='operador-2026-01', claims={sub, uuid_sucursal, permisos, aud, iat: NOW(), exp: NOW() + 4h, iat_offline: true})`. TTL is shorter because the JWT cannot be validated against cloud's JWKS until reconnect.
4. Frontend POSTs to local `api_sucursal /auth/login` with `{email, password, uuid_sucursal, timestamp_evento=$client_time}` — but the request stays LOCAL (the API is on the same container/branch network). Backend INSERTs the row locally.
5. Backend: bcrypt verify (defense in depth — the cached hash could be stale), INSERT `login` with `timestamp_evento=$client_time (passed from frontend), created_at=NOW() (DB time)`. The divergence between these two timestamps = offline duration.
6. INSERT `log_transaccional` (`accion='login_exitoso_offline'`, `datos_nuevos={offline_duration_seconds: EXTRACT(EPOCH FROM (created_at - timestamp_evento))}`).
7. `queue_processor.enqueue('login', $uuid, $snapshot)` — accumulates in local `sync_queue` (no push possible while offline).
8. When internet returns: `job_sync_sucursal/drain_outbox` pushes all queued login rows to cloud. Cloud receives and INSERTs verbatim.
9. Cloud admin querying `LoginAuditPanel`: filter `accion='login_exitoso_offline'` → sees all logins that happened during offline windows. The `timestamp_evento` column tells the real login time; the `created_at` tells when cloud received the row.

**Tables touched (writes)**: `login` (1 row offline), `log_transaccional` (1 row), `sync_queue` (1 item, accumulated).
**Tables touched (reads)**: `usuarios` (cached hash + permissions), `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `login.uuid`.

**Sync behavior**:
- Branch → cloud: YES (delayed by offline duration).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends immediately (the log row is written locally even offline); cloud chain extends on receipt.

**Integration with other tables**:
- Reads from: `usuarios` (cached hash), `log_transaccional`, `sucursal`.
- Writes to: `login` (with `timestamp_evento` divergence), `log_transaccional` (with `offline_duration_seconds`), `sync_queue`.
- Cross-cutting: this is the **offline-first** auth pattern. The frontend + backend + DB all work locally during offline; sync is best-effort when connectivity returns. The `timestamp_evento` divergence is the auditable proof of when the operator actually attempted login — critical for compliance audits (e.g., DIAN may ask "show me all logins between 2pm and 4pm on date X"; the answer requires `timestamp_evento`, not `created_at`).
- Special rule: local JWT has `iat_offline=true` flag; cloud API endpoints reject this flag when the branch is online (the local JWT cannot be used to access cloud APIs).

### 7.4 Use Case: `uc.login.operator-logout-estado-cerrado-with-log-transaccional-same-tx`

**Actor**: operator (branch)

**Real-world action**: Operator clicks "Logout" in `web_sucursal/TopBar`. Backend SELECTs the latest `login` row with `estado='exitoso'` for this user (per JWT's `sub`). UPDATE that row to `estado='cerrado'` — this is the ONLY permitted UPDATE on `login`, gated by `ls_session_update_guard` trigger that validates (a) only `estado` column is changing and (b) a `log_transaccional` INSERT occurs in the SAME TX. The trigger raises `LS_SESSION_FORBIDDEN_COLUMN` on any other column change or missing log row.

**Steps**:
1. Operator clicks `Logout`. Frontend POSTs `api_sucursal /auth/logout` with the JWT in the Authorization header.
2. Backend validates JWT (still valid, not expired). SELECTs the latest `login` row: `SELECT * FROM login WHERE uuid_usuario=$sub AND uuid_sucursal=$branch AND estado='exitoso' ORDER BY created_at DESC LIMIT 1`. Returns the `exitoso` row.
3. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
4. UPDATE `login SET estado='cerrado' WHERE uuid=$login_uuid`. The `ls_session_update_guard` trigger fires:
   - Validates NEW.estado='cerrado' AND OLD.estado='exitoso'.
   - Validates the TX includes an INSERT into `log_transaccional` for the same `uuid_sucursal` with `accion='logout'`. If missing → RAISE EXCEPTION `LS_SESSION_LOG_MISSING`.
   - Validates NO other column is being modified (NEW.uuid_usuario = OLD.uuid_usuario, etc.). If violated → RAISE EXCEPTION `LS_SESSION_FORBIDDEN_COLUMN`.
5. INSERT `log_transaccional` (`accion='logout'`, `tabla_afectada='login'`, `uuid_registro_afectado=$login_uuid`, `uuid_usuario=$operator`, `uuid_sucursal=$branch`, `datos_anteriores={estado:'exitoso'}`, `datos_nuevos={estado:'cerrado'}`).
6. `queue_processor.enqueue('login', $uuid, $snapshot)` — propagates the UPDATED row (with `estado='cerrado'`) to cloud within 30s.
7. Backend returns 204 No Content.
8. Frontend clears JWT from HttpOnly cookie + IndexedDB; redirects to LoginForm.

**Tables touched (writes)**: `login` (1 UPDATE — `[L-S]` exception), `log_transaccional` (1 INSERT — required by trigger), `sync_queue` (1 item).
**Tables touched (reads)**: `login` (the exitoso row, FOR UPDATE), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `login.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the UPDATED row (`estado='cerrado'`) propagates with the [L-S] UPDATE replicated as an UPDATE on cloud (same `ls_session_update_guard` validates).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row (the log_transaccional); cloud chain extends on receipt.

**Integration with other tables**:
- Reads from: `login` (the exitoso row), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `login` (UPDATE), `log_transaccional` (mandatory same TX), `sync_queue`.
- Cross-cutting: the `[L-S]` UPDATE constraint is the cornerstone — without the `ls_session_update_guard` trigger, this would be a regular UPDATE without audit trail. The trigger enforces "every state mutation has a log row in the same TX" — the audit-first contract. The same pattern is used in `sesion` (T43) for the cierre transition.
- Alternative: JWT expiry (no explicit logout). In this case, the `login` row stays `estado='exitoso'` until the operator explicitly logs out or a new login creates a new row. The `cerrado` state is only set on explicit logout. This is intentional — admin can distinguish "user is actively using the app" (exitoso) from "user has logged out" (cerrado).
- Related: T43 (`sesion`) use case 7.3 applies the same `[L-S]` UPDATE pattern for sesion cierre.

### 7.5 Use Case: `uc.login.cloud-admin-jwt-issuer-admin-validation-aud-iss-kid`

**Actor**: admin (cloud)

**Real-world action**: Cloud admin opens `web_admin/LoginForm`, types email + password. Backend validates JWT issuer is `admin-` (NOT `operador-` or `sync-agent-`). bcrypt verify, SELECTs `permisos_usuario`, issues `admin-` JWT (long-lived, 24h TTL, broad scope, `sucursales_permitidas` list per `usuarios_sucursal`). The JWT's `aud` claim is `api_admin`; cross-audience requests (admin JWT → `api_sucursal` endpoint) return 401. INSERTs `login` row with `estado='exitoso'`, INSERTs `log_transaccional` (with `aud='api_admin'` claim recorded in `datos_nuevos`).

**Steps**:
1. Admin opens `web_admin/LoginForm` (cloud PWA). Types email `admin1@easypunto.example` and password.
2. Frontend POSTs `api_admin /admin/auth/login` with `{email, password}`.
3. Backend: SELECT `usuarios` by email. bcrypt verify. Success.
4. SELECT `usuarios_sucursal` rows WHERE `uuid_usuario=$admin_uuid AND vigente_hasta IS NULL` → returns the list of branches the admin can access (`sucursales_permitidas`).
5. SELECT `permisos_usuario` rows → permission list (admin typically has all permissions).
6. Issue `admin-` JWT via `jwt_three_issuers.sign(issuer='admin-', kid='admin-2026-01', claims={sub, sucursales_permitidas: [...], permisos: [...], aud: 'api_admin', iat, exp: NOW() + 24h})`.
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for the admin's primary branch (or `CLOUD_ROOT` sentinel per T01 use case 7.3).
8. INSERT `login` row (`uuid=server-generated`, `uuid_usuario=$admin`, `uuid_sucursal=$admin_primary_branch`, `timestamp_evento=$client_time`, `estado='exitoso'`).
9. INSERT `log_transaccional` (`accion='login_admin_exitoso'`, `datos_nuevos={email, sucursales_permitidas_count: N, permisos_count, jwt_issuer:'admin-', jwt_aud:'api_admin', jwt_ttl: 24h}`).
10. INSERT `sync_log`.
11. Return `{access_token, expires_at, role: 'admin', sucursales_permitidas: [...]}`.
12. Frontend stores JWT; subsequent admin requests include the JWT in Authorization header. Each request's `jwt_three_issuers.verify_token(token, audience='api_admin')` validates `iss='admin-' AND aud='api_admin' AND kid='admin-2026-01'`. Any cross-audience request → 401.

**Tables touched (writes)**: `login` (1 row), `log_transaccional` (1 row), `sync_log` (1 row).
**Tables touched (reads)**: `usuarios` (email + bcrypt), `usuarios_sucursal` (sucursales_permitidas), `permisos_usuario` (permisos), `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid` (the admin's primary branch, not the cloud global — admin is "in" one branch contextually); `usuarios_sucursal.uuid_usuario` → `usuarios.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `login.uuid`.

**Sync behavior**:
- Branch → cloud: NO (this is cloud-origin).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row.

**Integration with other tables**:
- Reads from: `usuarios`, `usuarios_sucursal`, `permisos_usuario`, `log_transaccional`, `sucursal`.
- Writes to: `login`, `log_transaccional`, `sync_log`.
- Cross-cutting: this is the canonical **admin login** flow. The `admin-` JWT has `sucursales_permitidas` (N branches) and `aud='api_admin'`. Every API endpoint enforces `aud + iss + kid` validation. Cross-audience is impossible — admin JWT cannot call `api_sucursal` endpoints, and vice versa. The `sync-agent-` JWT is the only one that can call both (for sync workers).
- Three JWT issuers, three audiences: `admin-` → `api_admin`, `operador-` → `api_sucursal`, `sync-agent-` → `[api_admin, api_sucursal]`. Validation per AGENTS.md: `iss + aud + kid` must match.
- Related: T07 (`usuarios`) covers the admin user model; T30 (`configuracion_seguridad`) covers the password expiration (default 30 days, configurable).

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + `ls_session_update_guard` trigger), 5 (audit constraints — REVOKE + trigger for [L-S]), 6 (cloud admin API for login/logout), 7 (branch API for login/logout), 8 (Pydantic schemas), 9 (auth middleware with three JWT issuers), 13 (web_admin LoginForm + LoginAuditPanel), 14 (web_sucursal LoginForm with offline cache), 20 (structlog), 24 (pytest), 28 (docker compose), 31 (security audit + lockout monitoring), 35 (operational dashboards — login volume per branch per day).

## 9. RED Tests
- (RED) INSERT `login` from `rol_app` with `estado='exitoso'` → success.
- (RED) INSERT `login` with `estado='fallido'` → success.
- (RED) UPDATE `login SET estado='cerrado'` AND concurrent `log_transaccional` INSERT in same TX → success.
- (RED) UPDATE `login SET estado='cerrado'` WITHOUT concurrent `log_transaccional` → `LS_SESSION_LOG_MISSING` exception.
- (RED) UPDATE `login SET timestamp_evento=$X` (any column other than `estado`) → `LS_SESSION_FORBIDDEN_COLUMN` exception.
- (RED) UPDATE `login SET estado='exitoso'` (already exitoso) → trigger raises (only `cerrado` allowed).
- (RED) DELETE `prod.login` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Three-issuer JWT validation: admin JWT to `api_sucursal` endpoint → 401.
- (RED) Operador JWT to `api_admin` endpoint → 401.
- (RED) sync-agent JWT to `api_admin/sync/push` → 200; to `api_sucursal` endpoint requiring operador scope → 401.
- (RED) `timestamp_evento` divergence in offline mode: simulated 4h offline, then sync → `created_at - timestamp_evento = 4h`. Admin query by `timestamp_evento` correct.
- (RED) Lockout emission: 5 failed logins in 15 min window → `alerta tipo_alerta='login_lockout'` row created + `usuarios` new version with `estado='bloqueado'`. Subsequent login → 423 Locked.
- (RED) Admin unlock: POST `/alertas/{uuid}/resolver` with motivo → `usuarios` new version with `estado='activo'`.
- (RED) First operator login after branch boot: parametrization pull verification — login succeeds but UI shows "branch bootstrapping, please wait" until parametrization pull completes.
- (RED) FK RESTRICT: deleting `usuarios` with login rows → error.
- (RED) Cross-branch operador: operador JWT with `uuid_sucursal=A` calling endpoint scoped to branch B → 403.
- (RED) JWT expiry: token with `exp` in the past → 401. Refresh flow (sprint 5).

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + `ls_session_update_guard` trigger.
- [ ] F1.x `parkos_core/auth/login.py::attempt_login()` (exitoso + fallido writer).
- [ ] F1.x `parkos_core/auth/logout.py::close_session()` (cerrado UPDATE via [L-S]).
- [ ] F1.x `parkos_core/auth/jwt_three_issuers.py` (RS256 + iss/aud/kid validation).
- [ ] F1.x `parkos_core/auth/login_lockout_monitor.py` (failed count + alerta emission).
- [ ] IT-1.x: `api_sucursal/routers/auth.py::POST /auth/login` (operator).
- [ ] IT-1.x: `api_sucursal/routers/auth.py::POST /auth/logout` (operator, triggers UPDATE).
- [ ] IT-1.x: `api_admin/routers/auth.py::POST /admin/auth/login` (admin).
- [ ] IT-1.x: `api_admin/routers/auth.py::POST /admin/auth/logout` (admin).
- [ ] IT-1.x: `api_admin/routers/login.py::GET /login` (audit view, paginated).
- [ ] IT-1.x: bcrypt password verification (12 rounds).
- [ ] IT-1.x: offline cached credentials in IndexedDB + local JWT with `iat_offline=true`.
- [ ] IT-1.x: parametrization pull verification on first operator login.
- [ ] IT-1.x: `web_sucursal/LoginForm` with offline fallback.
- [ ] IT-1.x: `web_admin/LoginForm` (cloud).
- [ ] IT-1.x: `web_admin/LoginAuditPanel` (cross-branch history).
- [ ] IT-1.x: lockout monitor integration with `alerta tipo_alerta='login_lockout'`.
- [ ] Sprint 5: JWT refresh token rotation.
- [ ] Sprint 5: per-IP rate limiting on `/auth/login` (default 10 attempts per IP per minute).
- [ ] Sprint 5: password expiration enforcement per `configuracion_seguridad.dias_expiracion_password`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Brute force on `/auth/login` | Med | `configuracion_seguridad.max_intentos_login` enforced via `login_lockout_monitor` |
| Stolen JWT used cross-branch | Low | `uuid_sucursal` embedded in JWT; cross-branch returns 403 |
| Stolen JWT used cross-audience (admin → operador endpoints) | Low | `aud + iss + kid` validation enforced per request |
| Offline cached credentials stale (admin changed password while operator offline) | Med | Local JWT is short-lived (4h); on reconnect, cloud rejects JWT issued offline if user has been deactivated. Parametrization pull refreshes the cached hash. |
| `[L-S]` trigger bypassed by direct DB connection | Low | Trigger is on the table itself; even `rol_admin_auditor` (BYPASSRLS) cannot bypass the trigger without DROP TRIGGER (which is logged in `log_transaccional`) |
| `login` row volume explodes (high-traffic branch, many failed attempts) | Med | Partition by month on `created_at`; retention 5 years per compliance; pg_partman purges > 5 years |
| Admin views login audit reveals password hashes via timing attack | Low | Backend never returns `password_hash` in API responses; audit view shows only metadata |
| `timestamp_evento` clock skew between operator device and DB | Low | Operator device syncs time via NTP on every online login; offline mode accepts skew up to 5 min |
| Failed login due to user typo (not brute force) triggers lockout | Low | Lockout window is 15 min; admin can unlock with motivo |
| Operator deletes PWA cache (loses offline credentials) | Med | PWA cache is automatic; if cleared, operator must login online once to re-cache |

## 12. Open Questions
- (a) JWT TTL: 8h for operador online, 4h for operador offline — too long or too short? Currently 8h/4h.
- (b) Should the `cerrado` UPDATE be optional (auto-close on JWT expiry)? Currently requires explicit logout.
- (c) Should `login` partition by month or by quarter? Compliance retention is 5 years; partitioning is for performance.
- (d) Should `login` rows for system actors (`uuid_usuario=SYSTEM`) be flagged distinctly? Currently indistinguishable from human logins.
- (e) Should `login_lockout` apply to admin too (cloud)? Currently only branch operators; cloud admin lockout is admin-controlled via `usuarios.estado`.
- (f) Per-IP rate limiting beyond `login_lockout`: should `/auth/login` have its own rate limiter (e.g., 10 attempts per IP per minute)? Sprint 5.
- (g) Should the operator login UI support biometric (fingerprint, face) on mobile? Sprint 5+ (WebAuthn).
- (h) Multi-factor authentication (TOTP): out of MVP scope; sprint 5+.
- (i) Should `login` rows survive `usuarios` version archive? Currently RESTRICT FK prevents `usuarios` deletion but allows version archive; old login rows point to the version-active UUID at INSERT time.
- (j) Login audit export for DIAN compliance: should the system generate a monthly report of all logins? Sprint 5.
