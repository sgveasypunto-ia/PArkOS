# Delta Spec: orphan REQ-OPS materialization (F1.1 + F1.2)

> **Change**: `2026-09-17-orphan-req-f1-1-f1-2-coverage`
> **Capability**: operations
> **Type**: ADDED Requirements (delta)
> **Date**: 2026-09-17

## ADDED Requirements

The following 2 requirements are ADDED to `openspec/specs/operations/spec.md`, appended after REQ-OPS-140.

### Requirement: REQ-OPS-141 — `router_factory` guard for tables without `vigente_desde`

`make_router(model_cls)` MUST NOT apply `ORDER BY vigente_desde DESC, uuid ASC` or cursor pagination on `vigente_desde` when the model lacks that column. Tables mounted with `make_router` that only have `created_at` / `timestamp_evento` (workflow tables `alerta`, `anulaciones`, `reclamos`, `reimpresion_ticket`) MUST list correctly without `AttributeError` or SQL syntax error.

The fix relies on a single `_order_key(model_cls) -> tuple[ColumnElement, str]` helper that returns `(order_col, cursor_field)` shared by the order-by clause AND the cursor parsing. If `hasattr(model_cls, "vigente_desde")`, the helper returns `(model_cls.vigente_desde, "vigente_desde")`; otherwise it returns a fallback pair (the model's `uuid` plus a workflow-appropriate timestamp, e.g. `timestamp_evento`). The pagination guard mirrors: `if hasattr(model_cls, "vigente_hasta")` for the `vigente_hasta IS NULL` predicate and `if hasattr(model_cls, "vigente_desde")` for the order-by.

#### Scenario: GET on workflow table without `vigente_desde`

- **Given** `alerta` (workflow `[L-W]` table) lacks `vigente_desde` and `vigente_hasta` columns in the ER
- **When** `GET /workflows/alerta` is invoked against any `make_router(alerta)`-mounted collection
- **Then** the handler MUST NOT raise `AttributeError` or SQL error
- **And** the response MUST be ordered by `(timestamp_evento DESC, uuid ASC)` per the workflow default
- **And** cursor pagination MUST function with the same envelope `{items, next_cursor}` per `router_factory.py:227`.

#### Scenario: GET on `[V]` table with `vigente_desde` (no regression)

- **Given** `tarifas_sucursal` (`[V]` table) has `vigente_desde` and `vigente_hasta` columns
- **When** `GET /empresa/tarifas-sucursal` is invoked
- **Then** the response MUST preserve `ORDER BY vigente_desde DESC, uuid ASC` behavior (no regression vs the pre-fix contract)
- **And** the `vigente_hasta IS NULL` predicate MUST continue to be applied.

#### Scenario: `_order_key` helper centralizes the guard

- **Given** the helper at `api/router_factory.py:52` named `_order_key(model_cls: type) -> tuple[ColumnElement, str]`
- **When** any caller invokes it with a model
- **Then** it MUST return a 2-tuple `(order_column, cursor_field_name)` where the column matches the model's available sort key
- **And** the order-by clause and the cursor parsing MUST both consume this helper (no inline re-implementation).

**Source**: `backend/packages/parkos_core/src/parkos_core/api/router_factory.py` lines 17, 22, 52 (`_order_key` helper signature), 76 (`hasattr(model_cls, "vigente_desde")` guard for order-by), 84 (`_parse_cursor_timestamp` shared helper), 178 (`order_col, cursor_field = _order_key(model_cls)` shared between order + cursor), 182, 193, 246 (additional `hasattr` guards for cursor and list filtering). Commit `f7cb37a` is the original fix; `openspec/scripts/check_schema_match.py` `factory_intact` CI gate pins the behavior.

---

### Requirement: REQ-OPS-142 — `GET /auth/me`, cookie `httpOnly`, and real lockout

`POST /auth/login` MUST set `parkos_session` cookie with `httponly=True, secure=True, samesite="lax"` AND return `access_token` Bearer in the JSON body. `GET /auth/me` MUST return `{user, permisos, uuid_sucursal, sucursales_permitidas, expires_at}` per `AuthMeResponse`. The lockout window MUST come from `prod.configuracion_seguridad.minutos_bloqueo_login`: when an actor accumulates `max_intentos_login` failed attempts in the rolling window, `POST /auth/login` MUST respond `429 account_locked` with header `Retry-After: minutos_bloqueo_login * 60`.

The counter is per-`uuid_usuario`; the policy (`max_intentos_login`, `minutos_bloqueo_login`) is per-`uuid_sucursal`. The default fallback when `prod.configuracion_seguridad` row is missing is `DEFAULT_MINUTOS_BLOQUEO = 15` minutes. Lockout respects the `_resolve_lockout_params` resolver that SELECTs both columns from `prod.configuracion_seguridad` filtered by `uuid_sucursal` and falls back to defaults only when the row is absent (NOT when the columns are `NULL`).

#### Scenario: `POST /auth/login` success sets cookie + returns Bearer

- **Given** valid `email` + `password`
- **When** `POST /auth/login` is invoked
- **Then** response MUST be `200 OK` with body `{access_token, refresh_token, token_type: "bearer", expires_in, expires_at}`
- **And** `Set-Cookie: parkos_session=<JWT>; HttpOnly; Secure; SameSite=Lax` MUST be present on the response.

#### Scenario: 5th failed attempt returns `429 account_locked` with `Retry-After`

- **Given** `prod.configuracion_seguridad.max_intentos_login = 5` AND `minutos_bloqueo_login = 15` for the actor's `uuid_sucursal`
- **When** an actor accumulates 5 consecutive failed attempts within the lockout window
- **Then** the 5th failed attempt MUST respond `429 Too Many Requests` with body `{"error": "account_locked"}`
- **And** the response MUST include `Retry-After: 900` (15 * 60 seconds)
- **And** subsequent attempts within the window MUST also respond `429 account_locked` regardless of credential correctness.

#### Scenario: Lockout window expiry resets the counter

- **Given** an actor is locked out at time `T`
- **When** `T + minutos_bloqueo_login * 60` seconds elapse AND a correct `POST /auth/login` arrives at `T + minutos_bloqueo_login * 60 + 1`
- **Then** the response MUST be `200 OK` (counter reset by window expiry)
- **And** the failed-attempt counter MUST be re-initialized to 0.

#### Scenario: `GET /auth/me` returns `AuthMeResponse`

- **Given** a valid session cookie OR `Authorization: Bearer <access_token>`
- **When** `GET /auth/me` is invoked
- **Then** response MUST be `200 OK` with body `{user: {uuid, email, uuid_sucursal}, permisos: [...], uuid_sucursal, sucursales_permitidas: [...], expires_at}`
- **And** response MUST include `Cache-Control: no-store` (anti-enumeration + prevents stale permission cache).

#### Scenario: `GET /auth/me` unauthenticated returns `401`

- **Given** no session cookie AND no `Authorization` header
- **When** `GET /auth/me` is invoked
- **Then** response MUST be `401 Unauthorized` with body `{"error": "not_authenticated"}`
- **And** the handler MUST NOT leak any actor information (anti-enumeration).

**Source**: `backend/packages/parkos_core/src/parkos_core/api/v1/auth.py` lines 12-15 (lockout rationale), 81 (`DEFAULT_MINUTOS_BLOQUEO = 15`), 84-99 (`_resolve_lockout_params` resolver), 148 (`@router.post("/login")`), 175 (cookie `httponly=True, secure=True, samesite="lax"` comment), 291-294 (`response.set_cookie(..., httponly=True, ...)`), 310 (POST /refresh), 352 (POST /logout), 419 (`@router.get("/me", response_model=AuthMeResponse)`). `backend/packages/parkos_core/src/parkos_core/models/V/configuracion_seguridad.py:39` `minutos_bloqueo_login: Mapped[int | None]` column seeded by MIGRATION 0001. The frontend F3.1 login UI consumes REQ-OPS-106..112 (separate from this backend contract).

## Modified Capabilities

None. This change adds new requirements; it does not modify or remove any existing requirement.

## Out of Scope

- Frontend login UI (F3.1 REQ-OPS-106..112 — already materialized).
- Frontend lockout countdown (F3.2 — separate change).
- `parkos_session` cookie max-age or rotation policy (deferred to follow-up; current implementation aligns JWT expires_at with cookie expires).
- Refresh token rotation policy (Fase 3 Parte II follow-up).