# PRD: configuracion_seguridad (T30)

> **SINGLETON** — security policies for auth flow (`dias_expiracion_password`, `max_intentos_login`, `minutos_bloqueo_login`). Seeded with defaults (30 days expiry, 5 attempts, 15 min lockout). Versioned via `vigente_desde`/`vigente_hasta` with UNIQUE partial index enforcing ONE vigente row. Read by `login` flow on every branch authentication attempt.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule S: security policies are config inputs consulted at login time*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.configuracion_seguridad`
- **SQL name**: `configuracion_seguridad` (with `prod` schema)
- **Enforcement level**: `[V]` projection (singleton via UNIQUE partial index on `vigente_hasta IS NULL`)
- **Retention**: indefinite (singleton)
- **Origin**: F1 (schema, singleton seeded with defaults) + IT-2 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; restructured to canonical 12-section format; 4 use cases covering admin policies, branch login enforcement, password expiration, and lockout alerta trigger)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. Singleton: one row only.

## 3. SOLID Atomic Breakdown
- **S**: "one security policy configuration". Security policies are config inputs consulted at `login` time — NOT referenced by FK from `login` (snapshot semantic via `created_at` + vigente lookup).
- **O**: new columns via migration (e.g., adding `requiere_2fa` or `politica_contrasena_regex`).
- **I**: admin CRUD via `api_admin /configuracion-seguridad`; branch reads own vigente at login time.
- **D**: `parkos_core/models/V/configuracion_seguridad.py` (model); `parkos_core/auth/login.py::enforce_security_policy()` (the policy enforcement function).
- **Atomic**: INSERT (initial seed), UPDATE (archive old + create new with vigente_desde=NOW()).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | singleton |

### Incoming FKs (read-only, no FK — snapshot semantic)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | `configuracion_seguridad` is NOT referenced by FK from `login`. The vigente policy at the moment of login attempt is what matters (snapshot via `created_at` + vigente lookup). See use case 7.4 for snapshot semantics. |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Singleton seed (one row only — UNIQUE partial index `(vigente_hasta IS NULL)` enforces) |
| UPDATE | YES (archive only) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted with new UUID. NEVER modify `max_intentos_login` of existing version — compliance. |
| DELETE | NO | Archive via version flow |

**Special rules**:
- Singleton enforced via UNIQUE partial index `(vigente_hasta IS NULL)`.
- Versioning is mandatory for compliance. Every security policy change = new row version + archive old. The `log_transaccional` row records `datos_anteriores` and `datos_nuevos` for probatory integrity.
- The vigente lookup query: `SELECT * FROM configuracion_seguridad WHERE vigente_hasta IS NULL`. Returns 1 row (enforced by UNIQUE partial index).
- Branch reads the singleton at login time and enforces `max_intentos_login`, `dias_expiracion_password`, `minutos_bloqueo_login`.

## 6. CodeGraph Dependencies
- `api_admin/routers/configuracion_seguridad.py::PATCH /configuracion-seguridad` (admin only).
- `api_sucursal/routers/configuracion_seguridad.py::GET /configuracion-seguridad` (own vigente; used at login time).
- `parkos_core/auth/login.py::enforce_security_policy(login_attempt, policy)` (returns `LoginDecision(allow, reason, lockout_until)`).
- `parkos_core/auth/login_attempt_counter.py::count_consecutive_failures(uuid_usuario, within_window)` (reads `login` table).
- `web_admin/ConfiguracionSeguridadForm` (singleton form).
- `web_sucursal/LoginForm` (no direct display — enforcement happens server-side).

## 7. Use Cases enabled by this table

The `configuracion_seguridad` table is the **singleton that defines authentication security policies** (`dias_expiracion_password`, `max_intentos_login`, `minutos_bloqueo_login`) for the `login` flow. With UNIQUE partial index enforcing ONE vigente row at any time, every branch login attempt reads the vigente values. Versioning preserves compliance: admin changes do NOT retroactively affect historical lockouts (snapshot semantic via created_at + vigente lookup). Use cases below describe admin policy updates, branch login enforcement (max attempts), password expiration check, and the lockout `alerta` trigger. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.config-seguridad.admin-sets-policies`

Cloud admin updates security policies via `web_admin/ConfiguracionSeguridadForm`. Fills `dias_expiracion_password=60`, `max_intentos_login=3`, `minutos_bloqueo_login=30`. Backend creates a NEW version (archive old with `vigente_hasta=NOW()`, INSERT new with `vigente_desde=NOW()`). Parametrization push delivers the new version to all branches. The UNIQUE partial index enforces singleton.

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='configurar_seguridad'`; values are positive (`dias_expiracion_password > 0`, `max_intentos_login > 0`, `minutos_bloqueo_login > 0`).

**Steps**:
1. Admin opens `web_admin/ConfiguracionSeguridad`, edits fields.
2. Frontend PATCHes `api_admin /configuracion-seguridad` (admin- JWT) with `{dias_expiracion_password=60, max_intentos_login=3, minutos_bloqueo_login=30, vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario` for `permiso='configurar_seguridad'`; rejects 403 if missing.
4. Backend SELECTs current vigente row with `SELECT FOR UPDATE`.
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. UPDATE current vigente row SET `vigente_hasta=NOW()` (archive old).
7. INSERT new `configuracion_seguridad` row (`uuid=server-generated`, `dias_expiracion_password=60`, `max_intentos_login=3`, `minutos_bloqueo_login=30`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`).
8. INSERT `log_transaccional` (`accion='configuracion_seguridad_actualizada'`, `tabla_afectada='configuracion_seguridad'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores={dias_expiracion_password: $old, max_intentos_login: $old, minutos_bloqueo_login: $old}`, `datos_nuevos={dias_expiracion_password: 60, max_intentos_login: 3, minutos_bloqueo_login: 30}`).
9. `queue_processor.enqueue('configuracion_seguridad', $new_uuid, $new_snapshot)` → parametrization push for all branches within 30s.
10. Also enqueue the archived row.
11. Backend returns `{new_uuid, old_uuid_archived}`.
12. Branch receives parametrization; UPSERT new row, UPDATE local old row.
13. Next login at branch uses the new policies.

**Tables touched (writes)**: `configuracion_seguridad` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `configuracion_seguridad` (current state), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `configuracion_seguridad` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `configuracion_seguridad.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers new + archived version to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row; each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `configuracion_seguridad` (current state), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `configuracion_seguridad` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: the UNIQUE partial index `(vigente_hasta IS NULL)` enforces singleton. Every login attempt across the entire chain reads this row.
- Related: see use cases 7.2, 7.3, 7.4 for the enforcement flows.

### 7.2 Use Case: `uc.config-seguridad.branch-login-enforces-max-attempts`

Operator attempts to log in at branch. Backend bcrypt verifies password. If password is wrong: increment `intentos_login` counter (tracked in `login` table — count of consecutive `estado='fallido'` rows within a window). If `intentos_login >= max_intentos_login`: INSERT `login` with `estado='fallido'`, INSERT `alerta tipo_alerta='login_lockout'`, lock the user for `minutos_bloqueo_login`. Otherwise: just INSERT `login` with `estado='fallido'` (no alert).

**Actor**: operator (branch)

**Pre-conditions**: branch has parametrized vigente `configuracion_seguridad` (use case 7.1); operator exists in `usuarios`; `usuarios.estado='activo'` and `password_hash` is set.

**Steps**:
1. Operator opens `web_sucursal/LoginForm`, enters `cedula` (or email) + `password`.
2. Frontend POSTs `api_sucursal /auth/login` with `{uuid_usuario, password}`.
3. Backend SELECTs `usuarios.password_hash`, `estado`, `uuid_sucursal` for the user.
4. Backend bcrypt verify. If match → proceed to use case 7.3 (password expiration check). If fail:
5. Backend SELECTs vigente `configuracion_seguridad` → `max_intentos_login=3, minutos_bloqueo_login=15`.
6. Backend counts consecutive failed logins: `SELECT COUNT(*) FROM login WHERE uuid_usuario=$user_uuid AND estado='fallido' AND timestamp_evento >= NOW() - INTERVAL '30 minutes'`. (The 30-minute window is a sprint 5 configurable parameter — for MVP, hardcoded.)
7. If `consecutive_failures + 1 >= max_intentos_login` (i.e., this attempt will exceed the limit): trigger lockout.
8. Backend INSERTs `login` row (`uuid=server-generated`, `uuid_usuario`, `uuid_sucursal`, `timestamp_evento=NOW()`, `estado='fallido'`).
9. Backend INSERTs `log_transaccional` (`accion='login_fallido'`, `tabla_afectada='login'`, `uuid_registro_afectado=$login_uuid`, `uuid_usuario=$user_uuid`, `uuid_sucursal=$branch`, `datos_nuevos={intentos: $consecutive_failures+1, max: $max_intentos_login}`).
10. **Lockout alert**: INSERT `alerta` workflow root (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$user_uuid`, `uuid_alerta_padre=NULL`, `tipo_alerta='login_lockout'`, `valor_diferencia_efectivo=0`, `valor_diferencia_datafono=0`, `estado='abierta'`, `timestamp_evento=NOW()`, `observaciones='user_locked_for_${minutos_bloqueo_login}_min_after_${max_intentos_login}_failed_attempts'`).
11. Backend INSERTs `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alert_uuid`, `uuid_usuario=$user_uuid`, `uuid_sucursal=$branch`, `uuid_referencia=$login_uuid`).
12. The user is LOCKED: subsequent login attempts return 401 with `{locked_until: NOW() + minutos_bloqueo_login}`. Admin can manually unlock via PATCH `usuarios.estado` (sprint 5 — for MVP, the lockout expires after `minutos_bloqueo_login` automatically, no DB state needed).
13. `queue_processor.enqueue('login', $uuid, $snapshot)`.
14. Branch UI: red banner "Cuenta bloqueada por N minutos tras M intentos fallidos".

**Tables touched (writes)**: `login` (1 row with `estado='fallido'`), `alerta` (workflow root if lockout), `log_transaccional` (1-2 rows), `sync_queue` (1+ items).
**Tables touched (reads)**: `usuarios` (password_hash + estado), `configuracion_seguridad` (vigente), `login` (consecutive failure count), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`. `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (responsible); `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference for `en_revision → resuelta`). `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `login.uuid` (or `alerta.uuid`); `log_transaccional.uuid_referencia` (polymorphic) → `login.uuid` (for alerta_emitida).
**Sync behavior**:
- Branch → cloud: YES — `login` + `alerta` + `log_transaccional` push via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact for this specific action).
- DIAN trigger: NO (auth events don't trigger DIAN).
- Hash chain impact: YES — branch chain extends by 2-3 rows; cloud chain extends correspondingly.
**Integration**:
- Reads from: `usuarios` (password_hash), `configuracion_seguridad` (vigente), `login` (failure count), `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `login` (the failed attempt), `alerta` (lockout workflow), `log_transaccional` (audits), `sync_queue`.
- Cross-cutting: the `login` table is `[L-S]` (session lifecycle, UPDATE allowed only on `estado` for logout). Failed attempts are `INSERT` only — the state is derived from `estado`. The lockout is enforced by checking `count(estado='fallido' within window) >= max_intentos_login` at each login attempt.
- Related: see T09 (`login`) for the full login lifecycle (exitoso → cerrado for successful, fallido for failed); T41 (`alerta`) for the lockout workflow.

### 7.3 Use Case: `uc.config-seguridad.password-expiration-enforcement`

Operator attempts login (bcrypt passes). Backend checks `usuarios.fecha_cambio_password` against `configuracion_seguridad.dias_expiracion_password`. If `NOW() - fecha_cambio_password > dias_expiracion_password days`: return 401 with `{password_expired: true}`. Operator is forced to reset password before login succeeds. Otherwise: issue JWT.

**Actor**: operator (branch)

**Pre-conditions**: bcrypt password verification succeeded (use case 7.2 step 4); branch has vigente `configuracion_seguridad` (use case 7.1); `usuarios.fecha_cambio_password` is set.

**Steps**:
1. (Continues from use case 7.2 step 4) bcrypt verify passed. Proceed.
2. Backend SELECTs vigente `configuracion_seguridad` → `dias_expiracion_password=30`.
3. Backend SELECTs `usuarios.fecha_cambio_password` for the user.
4. Compute `days_since_change = (NOW() - fecha_cambio_password).days`.
5. If `days_since_change > dias_expiracion_password`: trigger password expiration gate.
6. Backend INSERTs `login` row (`uuid`, `uuid_usuario`, `uuid_sucursal`, `timestamp_evento=NOW()`, `estado='expirado'` — a transient state indicating password expired; not in MVP enum — sprint 5 may add `estado='password_expirado'` to `login` enum).
7. Backend returns 401 with `{detail: 'password_expired', password_updated_at: $fecha_cCamboPassword, days_since: $days_since_change, max_days: $dias_expiracion_password, reset_required: true}`.
8. Branch UI redirects to `ResetPasswordForm`. Operator enters a new password (no current password needed if the existing one is "expired" — though typically requires current for verification).
9. Frontend POSTs `api_sucursal /auth/reset-password` with `{uuid_usuario, new_password}`.
10. Backend bcrypt-hash the new password. UPDATE `usuarios.password_hash`, `fecha_cambio_password=NOW()` (creates a new `[V]` version of `usuarios` per T09 versioning rules). INSERT `log_transaccional` (`accion='password_reset'`, ...).
11. Operator re-attempts login. Now `days_since_change=0 <= dias_expiracion_password`. Login succeeds. INSERT `login` row with `estado='exitoso'`. Issue JWT.
12. If password NOT expired (normal flow): backend INSERTs `login` row with `estado='exitoso'`. Issue JWT. Operator proceeds to `web_sucursal` dashboard.

**Tables touched (writes)**: `login` (1 row, `estado='expirado'` or `'exitoso'`), `usuarios` (UPDATE password_hash + fecha_cambio_password → new `[V]` version per T09), `log_transaccional` (1-2 rows), `sync_queue` (1+ items).
**Tables touched (reads)**: `usuarios` (password_hash verification + fecha_cambio_password), `configuracion_seguridad` (vigente), `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`. `usuarios` is `[V]` — the UPDATE creates a new version (archive old + INSERT new per T09). `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `login.uuid` or `usuarios.uuid` (for password reset).
**Sync behavior**:
- Branch → cloud: YES — `login` + `usuarios` UPDATE + `log_transaccional` push via `sync_queue` within 30s.
- Cloud → branch: NO (the password reset is local to the branch where the user is operating; cloud receives the update via sync).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1-3 rows (login + password reset audit); cloud chain extends correspondingly.
**Integration**:
- Reads from: `usuarios` (password_hash + fecha_cambio_password), `configuracion_seguridad` (vigente), `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `login` (the auth attempt), `usuarios` (password reset, new version), `log_transaccional` (audits), `sync_queue`.
- Cross-cutting: the password expiration check uses the vigente `dias_expiracion_password` at the moment of login. Snapshot semantic applies: if admin changes the policy from 30 to 60 days, users who were "OK" at 30 days remain OK; users who would have been expired under 30 days are now NOT expired.
- Related: see T09 (`usuarios`) for the user versioning on password change; use case 7.4 for the lockout-related flow.

### 7.4 Use Case: `uc.config-seguridad.lockout-window-uses-current-policy-snapshot`

The lockout duration (`minutos_bloqueo_login`) used when a user is locked is the vigente at the moment of lockout — NOT the current one if admin changes the policy. This is the snapshot semantic for compliance. Example: User fails 3 attempts at 14:00, policy vigente says `minutos_bloqueo_login=15` (15-minute lockout). Admin changes to `minutos_bloqueo_login=30` at 14:05. The user is locked until 14:15 (per the 14:00 policy), NOT 14:30. The lockout duration is captured by the lockout's `timestamp_evento` correlation with the vigente policy.

**Actor**: system (no actor — semantic invariant)

**Pre-conditions**: a lockout has been triggered (use case 7.2); admin may have updated the policy since.

**Steps**:
1. User fails 3 login attempts at 14:00. SELECT vigente `configuracion_seguridad` → `minutos_bloqueo_login=15`. Lockout triggered (use case 7.2). `alerta` workflow root INSERTed.
2. Lockout window: user cannot login from 14:00 to 14:15.
3. Admin updates `configuracion_seguridad` at 14:05 → `minutos_bloqueo_login=30`. New version inserted.
4. Subsequent lockouts (e.g., another user fails at 14:10) use the NEW 30-minute duration.
5. The 14:00 lockout is UNAFFECTED — it expires at 14:15 per the policy vigente at that moment.
6. Audit query: "When was user X locked and for how long?" Answer: 14:00 to 14:15 (15 minutes, per the vigente policy at 14:00).
7. The retroactive lookup: `SELECT * FROM configuracion_seguridad WHERE vigente_desde <= '2026-01-15T14:00:00' AND (vigente_hasta IS NULL OR vigente_hasta > '2026-01-15T14:00:00')` — returns the version vigente at 14:00. This query is used for audit reports.

**Tables touched (writes)**: `configuracion_seguridad` (archive + new from admin update), `log_transaccional` (admin update audit).
**Tables touched (reads)**: `login` (lockout attempts), `alerta` (lockout workflow), `configuracion_seguridad` (vigente at lockout timestamp).
**FKs traversed**: `configuracion_seguridad` has NO FKs. `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid`. `login.uuid_usuario` → `usuarios.uuid`; `login.uuid_sucursal` → `sucursal.uuid`.
**Sync behavior**:
- Branch → cloud: NO (this is a semantic invariant).
- Cloud → branch: YES — parametrization push for the admin's policy update.
- DIAN trigger: NO.
- Hash chain impact: YES — each admin update extends the chain; each branch's receipt extends the chain.
**Integration**:
- Reads from: `login` (lockout attempts), `alerta` (lockout workflow), `configuracion_seguridad` (vigente at lockout.created_at).
- Writes to: NONE for this use case (the invariant is observational).
- Cross-cutting: this is the **snapshot semantic for compliance** applied to a singleton auth policy. Just like `tarifas_sucursal` snapshot preserves the historical tariff, the vigente `configuracion_seguridad` at the moment of lockout is the one that governs the lockout duration.
- Related: see use cases 7.2 (lockout trigger), 7.3 (password expiration). The same snapshot semantic applies to `dias_expiracion_password` in use case 7.3.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 31, 36 (auth middleware).

## 9. RED Tests
- (RED) Singleton check: second INSERT with `vigente_hasta=NULL` → UNIQUE violation.
- (RED) Admin PATCH `/configuracion-seguridad` → old row archived, new row vigente.
- (RED) Admin PATCH without `permiso='configurar_seguridad'` → 403.
- (RED) Branch operator JWT to `api_admin /configuracion-seguridad` → 401 (admin-only).
- (RED) Vigente lookup at login: returns exactly 1 row.
- (RED) Failed login counter incremented in `login.estado='fallido'`.
- (RED) 3 consecutive failed logins → INSERT `alerta tipo_alerta='login_lockout'` workflow root.
- (RED) After 4th attempt during lockout window → 401 with `locked_until`.
- (RED) Password expired (NOW() - fecha_cambio_password > dias_expiracion_password) → 401 with `password_expired: true`; operator redirected to `ResetPasswordForm`.
- (RED) Password reset → UPDATE `usuarios.password_hash` + `fecha_cambio_password=NOW()` (creates new `[V]` version per T09).
- (RED) Vigente-at-lockout lookup: SELECT with `vigente_desde <= lockout.created_at AND (vigente_hasta IS NULL OR vigente_hasta > lockout.created_at)` returns the version vigente at that moment.
- (RED) After admin PATCHes the policy (new version), historical lockouts retain their original duration (snapshot preserved via created_at correlation).
- (RED) Hash chain: cloud-side `log_transaccional` written for each policy change; branch chain extends on parametrization receipt.

## 10. Implementation Tasks
- [x] F1.x Schema + UNIQUE partial index on vigentes.
- [x] F1.x Seed (singleton with defaults: dias_expiracion_password=30, max_intentos_login=5, minutos_bloqueo_login=15).
- [ ] IT-2.x: `api_admin /configuracion-seguridad` (PATCH, GET).
- [ ] IT-2.x: parametrization push on security policy change.
- [ ] IT-2.x: `parkos_core/auth/login.py::enforce_security_policy()` with vigente lookup.
- [ ] IT-2.x: `parkos_core/auth/login_attempt_counter.py::count_consecutive_failures()`.
- [ ] IT-2.x: `web_admin/ConfiguracionSeguridadForm`.
- [ ] Sprint 5: add `estado='password_expirado'` to `login` enum (for explicit logging).
- [ ] Sprint 5: add MFA / 2FA support (out of MVP — see Open Question 12.a).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Policy change during active lockout | Low | Snapshot at lockout time (vigente at lockout.created_at governs the duration) |
| Policy set too strict (false lockouts) | Med | Admin reviews alerta workflow; can manually unlock user |
| Brute force attack (many users failing login) | Med | Rate limit at API level (sprint 5); IP-based block (sprint 5) |
| Singleton drift (multiple vigentes from migration bug) | Low | UNIQUE partial index enforces; entrypoint checks on boot |
| Password reset abuse (operator resets password for other users) | Low | Permiso check: `permiso='resetear_password_otros'`; default only allows own password |

## 12. Open Questions
- (a) MFA / 2FA? Out of MVP — sprint 5 may add TOTP.
- (b) Per-branch security policy overrides? Out of MVP — single corporate-wide policy.
- (c) Configurable consecutive-failure window (currently hardcoded 30 minutes)? Sprint 5 — would be a new column `minutos_ventana_intentos`.
- (d) Auto-unlock of `alerta tipo_alerta='login_lockout'` after lockout expires? Sprint 5.
- (e) IP-based blocking (ban IPs with N failures across users)? Sprint 5.
- (f) Explicit `uuid_configuracion_seguridad_vigente` column in `login`? Recommended for sprint 5 (avoids created_at correlation fragility, parallels T29's `uuid_tolerancia_vigente` recommendation).