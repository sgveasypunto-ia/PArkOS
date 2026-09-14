# Spec: operational (delta for hu-f1-3-sesion-unica)

## Capability: operational
## Change: hu-f1-3-sesion-unica
## Date: 2026-09-14

> **Source of truth**: `openspec/changes/hu-f1-3-sesion-unica/proposal.md`
> (D-HU-F1.3-1..8), `exploration.md` (KD-1 error mapping, KD-2 capture and re-emit,
> KD-3 BD-only no pre-check, KD-4 admin issuer 404), `plan.md` GAP-BE-LS-04
> rationale, `modelo_datos_er.mmd` `[L-S] prod.sesion` columns
> (`timestamp_cierre`, `uuid_usuario`, `timestamp_apertura`),
> `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (router
> custom, `_sesion_issuer_dep` line 35, `make_router` mount read-only lines
> 193–207).
>
> **Precedente upstream**: este change extiende la capability **operational** ya
> consolidada en `openspec/specs/operations/spec.md` (último REQ-OPS-NNN vigente:
> REQ-OPS-025 tras el merge de HU-F1.8, reconciliado 2026-09-14 a aceptar
> `VOLATILE`). HU-F1.3 introduce 4 requirements nuevos (REQ-OPS-026..029)
> sobre esa misma capability; los REQ-OPS-001..025 NO se modifican.

## Purpose

HU-F1.3 closes two gaps in the session lifecycle `[L-S]` model:

1. **Defense in depth at the DB level** — guarantee that a single `uuid_usuario`
   cannot hold two rows in `prod.sesion` with `timestamp_cierre IS NULL` at
   the same time, via a partial unique index. Today the application-level
   check in `repo/session_cycle.open_session` is the only guard: two
   concurrent inserts from the same `uuid_usuario` can race past the app
   check and leave an orphan row when the user eventually closes one
   session but not the other. The partial index is the authoritative
   invariant; the app check remains as a fast-path friendly-message.
2. **`GET /api/v1/caja-sesion/sesion/me`** — a dedicated endpoint that lets
   the admin/operador frontend ask "what is my currently active session
   right now?" without filtering `GET /sesion` (a paginated list without an
   actor filter, useful for audit but noisy for the operator's own shift).
   Returns either a single `SesionRead` or 404 `sesion_no_active`.

The migration `0023_add_sesion_unique_active.py` adds the partial unique
index; the pre-flight query detects orphan data pre-existing in the table
and aborts the migration with a typed error before `CREATE UNIQUE INDEX`
would fail with a cryptic message. The custom handler `get_my_sesion` is
registered in `caja_sesion.py` **before** the read-only `make_router` mount
so FastAPI matches the literal path `/sesion/me` ahead of the parametric
`/sesion/{uuid}` route.

## Requirements

### REQ-OPS-026: Partial unique index on `prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL` with pre-flight abort

**Given** an Alembic migration `0023_add_sesion_unique_active.py` is
applied against a Postgres database where `prod.sesion` already exists
and may contain legacy data
**When** the migration's `upgrade()` executes
**Then** the migration MUST first run a pre-flight query of the form
`SELECT uuid_usuario, count(*) FROM prod.sesion WHERE timestamp_cierre IS
NULL GROUP BY uuid_usuario HAVING count(*) > 1`
**And** if the pre-flight returns one or more rows, the migration MUST
abort with an explicit error that names each affected `uuid_usuario` and
the orphan count, MUST NOT proceed to `CREATE INDEX`, and MUST NOT leave
the migration half-applied (Alembic records no version bump on abort)
**And** the migration MUST then execute
`CREATE UNIQUE INDEX CONCURRENTLY uq_prod_sesion_one_active_per_user
ON prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL`
**And** the index MUST be a **partial** index (the `WHERE timestamp_cierre
IS NULL` predicate is mandatory — a full unique index would forbid two
historical closed sessions for the same user, which is legitimate)
**And** the index MUST be created with `CONCURRENTLY` so the build does
not take an `AccessExclusiveLock` against `prod.sesion` while the table
is serving cashier operations
**And** the `downgrade()` MUST execute `DROP INDEX CONCURRENTLY IF EXISTS
prod.uq_prod_sesion_one_active_per_user`
**RFC 2119**: MUST (pre-flight abort, `CONCURRENTLY`, partial predicate);
SHOULD (downgrade uses `CONCURRENTLY` to match the upgrade build mode).

### REQ-OPS-027: `GET /api/v1/caja-sesion/sesion/me` returns the actor's unique active session or 404

**Given** a JWT request reaches the FastAPI router for
`GET /api/v1/caja-sesion/sesion/me` with a valid `TenantContext` carrying
`ctx.actor_uuid` (extracted from the token subject by HU-F1.2)
**When** the dedicated handler `get_my_sesion` invokes
`repo/sesion_activa.py::get_sesion_activa(session, *, actor_uuid)`
**Then** the helper MUST execute a SQLAlchemy `SELECT` against `prod.sesion`
with the predicate `Sesion.uuid_usuario == :actor_uuid AND
Sesion.timestamp_cierre.is_(None)`
**And** the helper MUST order the result by
`Sesion.timestamp_apertura.desc().nulls_last()` and MUST apply `LIMIT 1`
**And** the helper MUST return exactly one `Sesion` ORM instance if a
match exists, or `None` otherwise (the partial unique index REQ-OPS-026
guarantees at most one row satisfies the predicate)
**And** the handler MUST return `200 OK` with the `SesionRead` payload
when the helper returns a row
**And** the handler MUST raise `HTTPException(status_code=404, detail=
{"error": "sesion_no_active"})` when the helper returns `None`
**And** the handler MUST be declared with `@router.get("/sesion/me")` and
MUST be registered **before** the `include_router(make_router(resource=
"sesion", ...))` block in `caja_sesion.py` so FastAPI matches the
literal path `/me` ahead of the parametric `/sesion/{uuid}`
**And** the `make_router` (HU-F1.1 GAP-BE-02 commit `f7cb37a`) MUST
remain unmodified
**RFC 2119**: MUST (literal path, ordering, `LIMIT 1`, 404 body shape);
SHOULD (return 404 with `Cache-Control: no-store` if applicable to keep
behaviour consistent with other read endpoints, but the contract does not
require it).

### REQ-OPS-028: `UniqueViolation` from partial unique index maps to 409 `sesion_already_active`, pgcode never exposed

**Given** `repo/session_cycle.py::open_session` is invoked with a
`uuid_usuario` that already has an active row in `prod.sesion`
(`timestamp_cierre IS NULL`) — either via a TOCTOU race past the app-level
fast-path check, or because the fast-path check returned a stale view
**When** the underlying `INSERT INTO prod.sesion (...)` reaches Postgres
**Then** Postgres MUST raise a unique-constraint violation because the
partial unique index from REQ-OPS-026 forbids the row; the
`psycopg2.errors.UniqueViolation` exception is surfaced with `pgcode ==
"23505"`
**And** `repo/session_cycle.open_session` MUST catch
`psycopg2.errors.UniqueViolation` (identified by `pgcode == "23505"`, not
by Python `isinstance` alone to remain robust to driver wrapping) and
MUST re-raise a domain exception `SesionAlreadyActive(uuid_usuario=...)`
**And** the HTTP handler `POST /api/v1/caja-sesion/sesiones` MUST catch
`SesionAlreadyActive` and MUST raise `HTTPException(status_code=409,
detail={"error": "sesion_already_active"})`
**And** the response body MUST contain **only** `{"error":
"sesion_already_active"}`; the pgcode `"23505"`, the raw Postgres error
message, and any driver-level diagnostic strings MUST NOT appear in the
response body, the response headers, or any log line emitted at `info` or
higher visibility to client users
**And** the contract MUST NOT introduce a pre-check `SELECT … WHERE
uuid_usuario=:u AND timestamp_cierre IS NULL` before the `INSERT` (KD-3
BD-only): the partial index is the authoritative invariant and a
pre-check would duplicate round-trips and reopen a TOCTOU window
**RFC 2119**: MUST (catch by pgcode, re-raise typed domain exception,
409 mapping, no pgcode in body, no pre-check); SHOULD (log the
occurrence at `warning` level with `event="sesion_already_active"` and
the `uuid_usuario` for ops triage, but without the pgcode).

### REQ-OPS-029: Both `operador-` and `admin-` issuers accepted on `GET /api/v1/caja-sesion/sesion/me`

**Given** a JWT request reaches `GET /api/v1/caja-sesion/sesion/me` with
either an `operador-` prefixed issuer or an `admin-` prefixed issuer
**When** the dedicated handler `get_my_sesion` resolves its dependencies
**Then** the dependency `_sesion_issuer_dep` (defined in `caja_sesion.py`
line 35 with `requires_issuer("operador-", "admin-")`) MUST accept both
issuer prefixes and MUST reject any other issuer with 401/403 (consistent
with the rest of `caja_sesion.py`)
**And** the handler MUST follow REQ-OPS-027 for both issuer classes: it
MUST resolve `ctx.actor_uuid` from the JWT subject and MUST query
`prod.sesion WHERE uuid_usuario = ctx.actor_uuid AND timestamp_cierre
IS NULL ORDER BY timestamp_apertura DESC NULLS LAST LIMIT 1`
**And** if an `admin-` issuer has no active session (the common case —
admins rarely open a cashier shift), the response MUST be exactly the
same 404 with body `{"error": "sesion_no_active"}` as for an `operador-`
issuer; there is no special admin bypass, no synthetic "view any session"
behaviour, and no 200 with `null` payload
**And** if a future need arises to query "the active session of an
arbitrary `uuid_usuario` from an `admin-` issuer", that is a separate
endpoint with an explicit query parameter and is OUT OF SCOPE for HU-F1.3
**RFC 2119**: MUST (accept both issuers, 404 same body, no admin bypass,
no synthetic payload); SHOULD (document the issuer list in the FastAPI
OpenAPI `tags` annotation alongside the rest of `caja_sesion.py`).

## Modified Capabilities

- `operational`: HU-F1.4 vigente filter (REQ-OPS-017..021) and HU-F1.8
  cotización surface (REQ-OPS-022..025) are preserved unchanged; this
  delta adds the uniqueness invariant on `prod.sesion` and the
  `/sesion/me` endpoint (REQ-OPS-026..029). The merged main spec
  (`openspec/specs/operations/spec.md`) gains four requirements and no
  existing requirement is modified.
- `backend/packages/parkos_core/migrations/versions/0023_add_sesion_unique_active.py`
  (NUEVO) — pre-flight `SELECT uuid_usuario, count(*) … HAVING count(*) >
  1` + `CREATE UNIQUE INDEX CONCURRENTLY
  uq_prod_sesion_one_active_per_user ON prod.sesion(uuid_usuario) WHERE
  timestamp_cierre IS NULL`. No table or column changes; `modelo_datos_er.mmd`
  intact.
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py`
  (MODIFICAR) — new `@router.get("/sesion/me")` handler `get_my_sesion`
  registered **before** the `include_router(make_router(resource="sesion",
  write_enabled=False, ...))` block (lines 193–207), plus the mapping
  `SesionAlreadyActive → HTTPException(409, {"error":
  "sesion_already_active"})` in the existing `open_sesion` handler.
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py`
  (MODIFICAR) — `open_session` catches `psycopg2.errors.UniqueViolation`
  by pgcode `"23505"` and re-raises `SesionAlreadyActive`. The fast-path
  application-level check (the pre-INSERT count) MAY remain as a
  friendly-message path but MUST NOT be relied upon for correctness; the
  partial unique index is the authoritative invariant (KD-3).
- `backend/packages/parkos_core/src/parkos_core/repo/sesion_activa.py`
  (NUEVO) — thin async helper `get_sesion_activa(session, *, actor_uuid)
  -> Sesion | None` with the `SELECT … WHERE uuid_usuario = :actor_uuid
  AND timestamp_cierre IS NULL ORDER BY timestamp_apertura DESC NULLS
  LAST LIMIT 1` query. Testable in isolation, no HTTP coupling.
- `backend/packages/parkos_core/src/parkos_core/exceptions.py`
  (MODIFICAR) — new domain exception `SesionAlreadyActive(uuid_usuario:
  UUID)` carrying the offending actor for ops triage but no pgcode, no
  raw driver message.
- `backend/tests/unit/test_caja_sesion_me.py` (NUEVO) — 4 HTTP-level
  tests (operador with active session, operador without, cliente issuer
  rejected, multiple closed sessions + one active).
- `backend/tests/integration/test_caja_sesion_unique_constraint_db.py`
  (NUEVO) — 2 DB-backed tests against `parkos-branch-db` (two open
  sessions for same `uuid_usuario` → `UniqueViolation`; second open after
  first close → no violation).
- `backend/tests/static/test_no_write_in_caja_sesion_me.py` (NUEVO) —
  AST walk rejecting `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` inside the
  `get_my_sesion` handler body, same pattern as F1.8.
- `backend/tests/unit/test_sesion_already_active_mapping.py` (NUEVO) —
  RED-then-GREEN coverage that `repo/session_cycle.open_session`
  re-raises `SesionAlreadyActive` on `pgcode == "23505"` and that the
  handler maps it to 409 with the typed body.
- `openspec/specs/operations/spec.md` (raíz) — entry in `## Modified
  Capabilities`: "Partial unique index on `prod.sesion(uuid_usuario)
  WHERE timestamp_cierre IS NULL` + pre-flight abort
  (REQ-OPS-026)" + "`GET /api/v1/caja-sesion/sesion/me` returns actor's
  active session or 404 (REQ-OPS-027)" + "`UniqueViolation` → 409
  `sesion_already_active`, pgcode never exposed (REQ-OPS-028)" + "`operador-`
  and `admin-` issuers both accepted on `/sesion/me` (REQ-OPS-029)".

## Out of Scope

- Endpoint `GET /caja-sesion/sesion/{uuid_usuario}/active` (consult any
  user's active session with `admin-` issuer) — deferred to a future HU
  per KD-4. This change only covers `/me`.
- Endpoint `POST /caja-sesion/sesion/me/cerrar` (close my own session
  without going through `/{uuid}/cerrar`) — deferred; the existing
  `PUT /sesion/{uuid}/cerrar` covers the case once the UUID is known.
- Notifying via WebSocket when a second operator tries to open a session
  for an already-active `uuid_usuario` — out of MVP backend scope.
- Pessimistic lock (`SELECT … FOR SHARE`) on the active session row in
  `get_sesion_activa` — the endpoint is informational and does not
  coordinate mutations.
- Audit table "who attempted to open a second session" — deferred; would
  require a separate security event table.
- Applying the same partial unique index pattern to other `[L-*]` tables
  with an "at most one active row per actor" invariant (e.g. `prod.caja`
  if it ever exists) — out of scope.
- Automatic cleanup of orphan data (`DELETE FROM prod.sesion WHERE
  timestamp_cierre IS NULL AND uuid_usuario IN (...)`) when the
  pre-flight detects it — the operator decides manually per KD-1 in the
  proposal.
- Frontend versioning (Fase 2) — this HU lands the backend surface only.
- Metrics / observability (counter of 409s, latency of `/me`) — aligned
  with the future F1.X observability HU; this change does not add
  Prometheus counters for `/me`.
