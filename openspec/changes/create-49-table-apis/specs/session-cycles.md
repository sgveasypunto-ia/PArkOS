# Spec: Session Cycles

## Capability

Provide the **session lifecycle** API surface for the **2 `[L-S]` tables** (`login`, `sesion`) — the only enforcement class with a permitted UPDATE on a state column. UPDATE is allowed ONLY on the canonical close-columns (`estado`, `timestamp_cierre`, `timestamp_evento`, `uuid_usuario_cierre`) AND ONLY IF a `log_transaccional` row has been written in the SAME transaction. This mandatory co-transactional pattern is enforced at three layers (API helper, ORM `session_cycle.py`, DB `BEFORE UPDATE` trigger). Branch-side login and sesion flows feed the lockout machinery (`configuracion_seguridad.max_intentos_login` is the threshold; `minutos_bloqueo_login` the lockout duration; the sliding 15-minute window is the counter reset window — see `operational.md` REQ-OP-11). On successful login the failure counter is reset as part of the same TX that inserts the `exitoso` `login` row.

## Requirements

### REQ-40-S-OPEN: `sesion` open = single INSERT
**Given** an `operador-` JWT subject (the user opening the turno) and `uuid_sucursal = X`
**When** the operator calls `POST /api/v1/sesion {valor_inicial_efectivo: V_e, valor_inicial_datafono: V_d, uuid_sucursal: X}` with `Idempotency-Key`
**Then** the system MUST INSERT a new `sesion` row with `timestamp_apertura = NOW()`, `estado='abierta'`, `uuid_usuario = <jwt_subject>`, `created_by = <jwt_subject>`, return 201 with the projected `Read` payload; a mirror `login` row with `estado='exitoso'` is also written in the SAME TX for audit (login here = the opening act of the shift at the device, not authentication)
And on commit, a `log_transaccional` row with `accion='crear'` is enqueued by the helper

### REQ-41-S-CLOSE: `sesion` close = `log_transaccional` BEFORE `UPDATE` (same TX)
**Given** an existing `sesion` row S with `estado='abierta'` and `timestamp_cierre IS NULL`
**When** the operator (or a supervisor) calls `PUT /api/v1/sesion/{S.uuid}/cerrar` with body `{"valor_final_efectivo": V_fe, "valor_final_datafono": V_fd, "uuid_usuario_cierre": <subject>}`
**Then** `close_session_with_log()` helper MUST (a) INSERT a `log_transaccional` row with `accion='actualizar'`, `tabla_afectada='sesion'`, `uuid_registro_afectado=S.uuid`, `datos_anteriores=json(S)`, `datos_nuevos=json(S+changes)`; (b) then `UPDATE` S SET `estado='cerrada'`, `timestamp_cierre=NOW()`, `uuid_usuario_cierre=<subject>` — both in the SAME `AsyncSession` transaction; respond 200 with the updated Read
And a trigger-level migration test (`test_ls_session_guard.py`) verifies that attempting `UPDATE sesion SET estado='cerrada' WHERE uuid=:u` WITHOUT a prior `log_transaccional` row in the same TX raises `psycopg2.errors.RaiseException: LOG_TRANSACCIONAL_REQUIRED` — 2 fixtures, one per `[L-S]` table

### REQ-42-S-LOGIN: Authentication flow
**Given** a `POST /api/v1/auth/login` body with `{"email": "...", "password": "...", "totp_code": "..."}` (TOTP optional depending on user config)
**When** the auth service runs
**Then** the system MUST (a) resolve `usuarios.email` (active row only), (b) verify `bcrypt.verify(password, password_hash)` AND `pyotp.verify(totp_code)` if TOTP enabled, (c) on success INSERT a `login` row with `estado='exitoso'`, `uuid_usuario = U`, `uuid_sucursal = <from request context>`; (d) reset `usuarios.intentos_fallo` counter — bi-temporally via close + insert (REQ-04-V-ACTUALIZACION on `usuarios`); (e) issue an `operador-` JWT (RS256) bound to `uuid_sucursal` and `permisos_usuario` snapshot; respond 200 with `{"access_token": ..., "refresh_token": ..., "expires_in": ..., "requires_totp": false}`; reply with 401 `{"error": "invalid_credentials"}` on any failure (no enumeration)

### REQ-43-S-LOGIN-FAILURE: Failed attempt and lockout (Q11)
**Given** a login attempt with valid email and WRONG password (or invalid TOTP)
**When** the auth service increments the failure counter
**Then** the system MUST (a) INSERT a `login` row with `estado='fallido'` (no UPDATE to `usuarios` on failure — counter is read from `login` history by the next failure check); (b) check the sliding-window: count of `login` rows with `uuid_usuario = U AND estado='fallido' AND timestamp_evento > NOW() - INTERVAL '15 minutes'` (the value from `configuracion_seguridad.minutos_ventana_login` once populated; defaults to 15 for now) — if `count >= config.max_intentos_login` (default 3), then (c) INSERT a `login` row with `estado='fallido'` AND `motivo='lockout'` for the audit trail, AND reject with 423 `{"error": "locked", "retry_after_seconds": 1800}` (config.minutos_bloqueo_login * 60); (d) on exceeding attempts, suspend the user record by inserting `usuarios` close + insert with `estado='inactivo'` and a `motivo='lockout'` snapshot in `datos_nuevos` (this re-activation is admin-restored — `usuarios.estado` is bi-temporal, so a `suspendida` row followed by a new `activa` row preserves history)

### REQ-44-S-LOGIN-REFRESH: Token refresh
**Given** a valid `refresh_token` from a previous successful login (≤ 7 days old)
**When** the client POSTs `POST /api/v1/auth/refresh` with the refresh token
**Then** the system MUST validate the `refresh_token` signature against the `operador-*` JWKS, check `iss` and `aud` claims, rotate to a new pair (revoke old access, issue new access; old refresh becomes single-use per RFC 6749 §6), and respond 200 with `{"access_token": ..., "refresh_token": ..., "expires_in": ...}`; on invalid signature, 401 `{"error": "invalid_refresh"}`

### REQ-45-S-LOGOUT: Session close
**Given** a valid `operador-` access token
**When** the client calls `POST /api/v1/auth/logout` with `Idempotency-Key`
**Then** the system MUST (a) read the latest `login` row for the user with `estado='exitoso'` AND `timestamp_cierre IS NULL`; (b) INSERT a `log_transaccional` row (`accion='actualizar'`); (c) UPDATE that `login` row SET `estado='cerrado'`, `timestamp_cierre=NOW()` — in the same TX; (d) optionally close any open `sesion` rows for the same `uuid_usuario` (if `cerrar_sesion=true` query param) following REQ-41-S-CLOSE; respond 204 No Content

### REQ-46-S-LOGIN-NO-UPDATE-ESTADO-LOGIN-ALONE: `login`'s UPDATE is bounded
**Given** any FastAPI path code path that updates the `login` table
**When** the migration test runs (`backend/tests/migrations/test_ls_session_guard.py::test_login_update_requires_log`)
**Then** an `UPDATE login SET estado='cerrado' WHERE uuid=:u` without a prior `log_transaccional` INSERT in the SAME TX MUST raise `psycopg2.errors.RaiseException: LOG_TRANSACCIONAL_REQUIRED`. The DB trigger is the third-layer defense; API and ORM are the first and second

## Scenarios

### SC-40-S-FULL-SHIFT: Open → pay → close → lockout cleared on success
1. Operator U opens shift: `POST /api/v1/sesion {valor_inicial_efectivo: 50000}`. Row S1 created with `estado='abierta'`, S1.timestamp_apertura = T0.
2. Operator U logs in (already done in SC-41), `login` row L1 with `estado='exitoso'`.
3. Time passes; multiple pago rows accumulated under `factura_pagos.uuid_sesion = S1.uuid`.
4. Operator U closes: `PUT /api/v1/sesion/{S1.uuid}/cerrar {valor_final_efectivo: 185000, ...}`. Helper writes `log_transaccional` first, then UPDATE S1 SET `estado='cerrada'`. Returns 200.
5. U retries login from a different device: success → `login` row L2 with `estado='exitoso'`; if U had prior 3 fails in last 15min, the success resets the counter bi-temporally (no field on `usuarios` is overwritten — a new `usuarios` row is appended via REQ-04-V-ACTUALIZACION with `intentos_fallo=0`, prior row closed).

### SC-41-S-LOCKOUT: Three wrong passwords in 15 minutes
1. U tries `POST /api/v1/auth/login` with wrong password. `login` row L1 with `estado='fallido'`.
2. U tries again wrong (T+5min). `login` row L2 with `estado='fallido'`. Counter (read from `login` history): 2.
3. U tries third time wrong (T+10min). `login` row L3 with `estado='fallido'`. Counter: 3 → matches `max_intentos_login`. Auth helper inserts an additional `login` row L4 with `estado='fallido'`, `motivo='lockout'`. Suspends user via close+insert on `usuarios`. Returns 423 `{"error": "locked", "retry_after_seconds": 1800}`.
4. Correct password during lockout window: 423 still.
5. After `minutos_bloqueo_login` elapses, correct password succeeds → new `usuarios` row activated (admin-driven restore or auto via this path); `login` row L5 with `estado='exitoso'`.

### SC-42-S-DB-TRIGGER-GUARD: Migration test
1. Migration test fixture opens a TX.
2. It tries `UPDATE sesion SET estado='cerrada' WHERE uuid=:u` with NO prior log_insert in the TX.
3. Expects `psycopg2.errors.RaiseException: LOG_TRANSACCIONAL_REQUIRED`.
4. Same fixture inserts a log row first (`INSERT INTO log_transaccional ...`), then retry the same UPDATE — now succeeds.
5. Same for `login` table (second fixture).

## Constraints

- **C-S1**: The `[L-S]` UPDATE-with-log enforcement is the single allowed exception to the no-UPDATE principle. The DB trigger is mandatory in the same migration that creates the table; `openspec/config.yaml` `rules.tasks`.
- **C-S2**: `login` rows are append + close-only. Even successful logins accumulate as rows; bi-temporal close on `usuarios` for `intentos_fallo` counter reset preserves the full history.
- **C-S3**: `bcrypt 12+` factor required (skill `easy-punto-python` hard rule). TOTP (`pyotp`) mandatory on production builds (deferred config: `requiere_totp bool` on `usuarios`).
- **C-S4**: All three JWT issuers are mutually exclusive — `kid` prefix + `iss` + `aud` enforced; cross-issuer use rejected with 401.
- **C-S5**: Lockout timer uses `configuracion_seguridad.minutos_bloqueo_login` (default 30 minutes) and window uses `minutos_ventana_login` (default 15, Q11 resolution).

## Out of scope

- BFF (HTTP-to-BFF proxy) — separate change.
- WebAuthn / passkeys — separate change (deferred to v2).
- Admin impersonation — separate change; mentioned in `bitacora` document at `actor_impersonado_id`.

## Dependencies

- `parkos_core/repo/session_cycle.py` — `open_session()`, `close_session_with_log()`.
- `parkos_core/auth/{jwt_issuer_guard,permissions}.py` — three-issuer validation, RBAC framework.
- `parkos_core/api/v1/auth.py` — `/auth/login`, `/auth/refresh`, `/auth/logout`.
- DB trigger functions `ls_session_update_guard()`, `ls_login_update_guard()` — bootstrap migration (`0001_initial_schema.py`).
- ADR references: AD-2, AD-3. Q11 closed here.
- Engram topic: `sdd/create-49-table-apis/spec`.
