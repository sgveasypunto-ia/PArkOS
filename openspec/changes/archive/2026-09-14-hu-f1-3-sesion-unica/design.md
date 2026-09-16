# Design: HU-F1.3 — Constraint sesión única + GET /caja-sesion/sesion/me

> **Change**: `hu-f1-3-sesion-unica`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.3 — DB partial unique index on `prod.sesion` + custom endpoint `GET /caja-sesion/sesion/me`
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a779b79`)
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (D-HU-F1.3-1..8 with KD-1..KD-4) + `exploration.md` +
> `specs/operational/spec.md` (REQ-OPS-026..029 RFC 2119).
> **Cross-references**: `plan.md` (GAP-BE-LS-04 rationale),
> `modelo_datos_er.mmd` `[L-S] prod.sesion` (L715-740, edges L1198-1202), precedent
> `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/design.md`
> (PL/pgSQL migration + custom handler + AST walk pattern, commit `a3d0c39`),
> precedent `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/design.md`
> (helper-pure-pattern + bi-temporal precedent, commit `de4d2fc`),
> `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py`
> (router custom, `_sesion_issuer_dep` line 35, `make_router` mount read-only lines 193-207),
> `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py::open_session` (lines 180-251).

## 1. Context

HU-F1.3 closes two gaps in the cash-session lifecycle `[L-S] prod.sesion` (REQ-40 / REQ-41):

1. **Defense-in-depth at the DB level.** Today, `repo/session_cycle.open_session` only validates
   "no active session" in application code. Two concurrent inserts for the same `uuid_usuario`
   race past the application check and leave an orphan row when the user closes one session
   but not the other, breaking the operational 1:1 between cajero and `sesion` activa. The
   change adds a **partial unique index** `prod.uq_prod_sesion_one_active_per_user
   ON prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL` so the database is the
   authoritative invariant; the partial predicate lets multiple historical closed sessions
   for the same user coexist (a legitimate state).
2. **`GET /api/v1/caja-sesion/sesion/me`.** A dedicated endpoint that lets the admin/operador
   frontend ask "what is my currently active session right now?" via `TenantContext.actor_uuid`
   (HU-F1.2). Reuses `SesionRead` unchanged; returns 404 `sesion_no_active` if the actor has
   no open session.

**Key Decisions confirmed** (proposal §2, all KD-1..KD-4 — no open questions):

- **KD-1** — Map `psycopg2.errors.UniqueViolation` (pgcode `"23505"`) to HTTP 409
  `{"error":"sesion_already_active"}`. The pgcode is an implementation detail of psycopg2;
  leaking it couples the client contract to the driver version.
- **KD-2** — `repo/session_cycle.open_session` catches `UniqueViolation` (by pgcode, not by
  Python `isinstance` — robust to driver wrapping) and re-raises a typed domain exception
  `SesionAlreadyActive(uuid_usuario=...)`. The HTTP handler maps it to 409. The existing
  app-level fast-path check stays as a friendly-message path but is NOT the authoritative
  invariant; the partial unique index is.
- **KD-3** — No pre-check in the repo (`SELECT … WHERE uuid_usuario=:u AND timestamp_cierre
  IS NULL` before `INSERT`). Defense in depth comes from the DB constraint, consistent with
  F1.8's `STABLE/VOLATILE` + AST walk on `calcular_cotizacion`. Pre-check would duplicate
  round-trips and reopen a TOCTOU window.
- **KD-4** — `GET /caja-sesion/sesion/me` accepts both `operador-` and `admin-` issuers. If
  the actor has no active session, return the same 404 `sesion_no_active` — no admin bypass,
  no synthetic payload.

**Sized at ~110 LOC** (70 migration with pre-flight, 25 endpoint, 15 unit tests + the
`UniqueViolation → 409` mapping + KD-1 doc). The migration is `0023_add_sesion_unique_active.py`
(0022 was consumed by F1.8).

## 2. Architecture Overview

```
                     ┌──────────────────────────────────────────────────────────────┐
                     │  MIGRACIÓN Alembic 0023 (defense in depth DB-level)         │
                     │  backend/packages/parkos_core/migrations/versions/0023_…     │
                     │                                                              │
                     │  upgrade():                                                   │
                     │    pre-flight:                                                │
                     │      DO $$ … SELECT count(*)                                  │
                     │        FROM (SELECT uuid_usuario                              │
                     │                FROM prod.sesion                               │
                     │                WHERE timestamp_cierre IS NULL                 │
                     │                GROUP BY uuid_usuario                          │
                     │                HAVING count(*) > 1) t;                       │
                     │      IF n_bad > 0: RAISE EXCEPTION '…huérfanos…';            │
                     │                                                              │
                     │    CREATE UNIQUE INDEX CONCURRENTLY                           │
                     │      IF NOT EXISTS prod.uq_prod_sesion_one_active_per_user    │
                     │      ON prod.sesion (uuid_usuario)                            │
                     │      WHERE timestamp_cierre IS NULL;                          │
                     │                                                              │
                     │  downgrade():                                                 │
                     │    DROP INDEX CONCURRENTLY IF EXISTS                         │
                     │      prod.uq_prod_sesion_one_active_per_user;                │
                     └──────────────────────────────────────────────────────────────┘

   POST /api/v1/caja-sesion/sesiones          (path existente, comportamiento extendido)
        │  _sesion_issuer_dep = requires_issuer("operador-", "admin-")
        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ api/v1/caja_sesion.py :: open_sesion (existente, líneas 70-113)         │
   │                                                                          │
   │   repo/session_cycle.py::open_session(...)   ◄── KD-2 captura           │
   │       INSERT INTO prod.sesion (...)                                       │
   │       │                                                                  │
   │       │  si UniqueViolation (psycopg2 pgcode == "23505") ← RACE:        │
   │       │    raise SesionAlreadyActive(uuid_usuario=…)       ◄── KD-2      │
   │       │                                                                  │
   │       │  cualquier otro IntegrityError:                                  │
   │       │    re-raise  (no swallowing)                                     │
   │       │                                                                  │
   │       └─► en el handler open_sesion:                                    │
   │             except SesionAlreadyActive →                                 │
   │                HTTPException(409, {"error":"sesion_already_active"})     │
   │                                       ◄── KD-1 mapping                  │
   └──────────────────────────────────────────────────────────────────────────┘

   GET /api/v1/caja-sesion/sesion/me          (path NUEVO, registrado ANTES del include_router)
        │  _sesion_issuer_dep = requires_issuer("operador-", "admin-")  ◄── KD-4
        ▼
   ┌──────────────────────────────────────────────────────────────────────────┐
   │ api/v1/caja_sesion.py :: get_my_sesion (NUEVO)                          │
   │   registrado ANTES de router.include_router(make_router(...))           │
   │                                                                          │
   │   repo/sesion_activa.py::get_sesion_activa(                             │
   │       session, *, actor_uuid=ctx.actor_uuid)                             │
   │       │                                                                  │
   │       │  SELECT * FROM prod.sesion                                       │
   │       │  WHERE  uuid_usuario = :actor_uuid                               │
   │       │    AND  timestamp_cierre IS NULL                                 │
   │       │  ORDER BY timestamp_apertura DESC NULLS LAST                     │
   │       │  LIMIT 1                                                         │
   │       │                                                                  │
   │       │  ◄── partial unique index (REQ-OPS-026) garantiza ≤ 1 fila;    │
   │       │      ORDER BY es defensivo por si la BD se erosiona             │
   │       │                                                                  │
   │       └─► SesionRead (model_validate) o None                            │
   │              │                                                           │
   │              └─► None → HTTPException(404,                                │
   │                       {"error":"sesion_no_active"})                      │
   └──────────────────────────────────────────────────────────────────────────┘
```

**Annotations.** The partial unique index is the authoritative invariant (KD-3, NO pre-check).
The handler is registered **before** the `make_router(... sesion, write_enabled=False)` mount
so FastAPI's specificity rule matches `/me` ahead of `/{uuid}`. The handler is read-only;
defense in depth is layered with `tests/static/test_no_write_in_caja_sesion_me.py` (AST walk).

## 3. Components

- **`migrations/versions/0023_add_sesion_unique_active.py`** (NUEVO, 70 LOC) — Alembic
  upgrade() runs pre-flight (DO block with `SELECT count(*) … HAVING count(*) > 1`) then
  `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`. downgrade() runs
  `DROP INDEX CONCURRENTLY IF EXISTS prod.uq_prod_sesion_one_active_per_user`.
  `IF NOT EXISTS` makes the migration idempotent against `alembic upgrade` retries;
  Alembic records no version bump on pre-flight abort (consumed by Alembic
  transaction control).
- **`api/v1/caja_sesion.py::get_my_sesion`** (NUEVO, 25 LOC) — registered with
  `@router.get("/sesion/me")` declared BEFORE `router.include_router(make_router(...))`
  block (líneas 193-207). Injects `session`, `ctx: TenantContext`, `_sesion_issuer_dep`.
  Returns `SesionRead`; raises `HTTPException(404, {"error":"sesion_no_active"})` on miss;
  sets `response.headers["Cache-Control"] = "no-store"` (consistent with F1.8 R8).
- **`api/v1/caja_sesion.py::open_sesion`** (MODIFICAR, +6 LOC) — wrap the `open_session(...)`
  call in `try/except SesionAlreadyActive` → re-raise as `HTTPException(409,
  {"error":"sesion_already_active"})`. Body MUST NOT contain pgcode, raw driver message, or
  log-line diagnostic at `info+`.
- **`repo/session_cycle.py::open_session`** (MODIFICAR, +12 LOC) — wrap `session.add(new_row)`
  + `await session.flush()` in `try/except IntegrityError as exc:`. Detect pgcode via
  `getattr(getattr(exc, "orig", None), "pgcode", None) == "23505"`. Raise the new typed
  domain exception `SesionAlreadyActive(uuid_usuario=...)` defined in
  `exceptions.py`. Re-raise all other `IntegrityError` unchanged.
- **`repo/sesion_activa.py`** (NUEVO, ~20 LOC) — thin async helper
  `get_sesion_activa(session, *, actor_uuid) -> Sesion | None`. Encapsulates the SELECT with
  the four-clause predicate (`uuid_usuario`, `timestamp_cierre IS NULL`, `ORDER BY
  timestamp_apertura DESC NULLS LAST LIMIT 1`). Testable in isolation against a mock or
  real session; no HTTP coupling.
- **`exceptions.py::SesionAlreadyActive`** (NUEVO, ~10 LOC) — domain exception class carrying
  the offending actor UUID for ops triage (`__str__` shows `uuid_usuario` only; no pgcode,
  no driver string). Imported by `session_cycle.py`, raised, caught by handler.
- **`schemas/caja.py::SesionRead`** (REUTILIZADO, sin cambios) — 12 campos incluyendo `uuid`,
  `uuid_sucursal`, `uuid_usuario`, `valor_inicial_*`, `timestamp_apertura`,
  `timestamp_cierre`, `uuid_usuario_cierre`, `created_at`, `created_by`, `sync_status`,
  `sync_timestamp`.
- **`tests/unit/test_caja_sesion_me.py`** (NUEVO) — 4 HTTP-level tests RED-then-GREEN.
- **`tests/unit/test_sesion_already_active_mapping.py`** (NUEVO) — RED-then-GREEN coverage
  that the repo re-raises `SesionAlreadyActive` on pgcode 23505 and the handler maps to 409.
- **`tests/integration/test_caja_sesion_unique_constraint_db.py`** (NUEVO) — 2 DB tests
  contra `parkos-branch-db` con `PARKOS_DOCKER_TEST=1`.
- **`tests/static/test_no_write_in_caja_sesion_me.py`** (NUEVO) — AST walk sobre el handler,
  rechaza `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` en su cuerpo (patrón F1.8,
  `test_no_write_in_calcular_cotizacion.py`).

**Files explicitly NOT touched**:

- `api/v1/router_factory.py::make_router` (HU-F1.1 GAP-BE-02, commit `f7cb37a`,
  estabilizado). `make_router` no soporta filtro `actor_uuid`; un handler dedicado evita
  tocar el factory.
- `models/L_S/sesion.py` (sin cambios de esquema, solo el índice nuevo).
- `schemas/caja.py` (`SesionRead`/`SesionCreate`/`SesionUpdate` se reusan tal cual).
- `repo/session_cycle.py::close_session_with_log` (no relacionado con la unicidad activa).

## 4. Key Decisions (KD)

### Decision KD-1 — `UniqueViolation` map to 409 `sesion_already_active`, pgcode never exposed

**Choice.** When `repo/session_cycle.open_session` raises `IntegrityError` with
`psycopg2.errors.UniqueViolation` (pgcode `"23505"`), the helper re-raises a typed domain
exception `SesionAlreadyActive(uuid_usuario=...)`. The HTTP handler at
`api/v1/caja_sesion.py::open_sesion` catches `SesionAlreadyActive` and emits
`HTTPException(409, detail={"error": "sesion_already_active"})`. The response body, headers,
and any log line at `info` or higher visibility MUST NOT contain the pgcode, the raw
Postgres error message, or any driver-level diagnostic.

**Context.** The partial unique index from REQ-OPS-026 is the authoritative DB-level veto.
On a TOCTOU race past the app-level fast-path (KD-3 says the app check is NOT authoritative),
the second INSERT triggers `UniqueViolation` in psycopg2 — currently a 500 in the codebase
because `open_session` does not catch it. KD-1 turns that 500 into a 409 with a stable
discriminator the client can code against. KD-2 explains the re-emission in the repo.

**Alternatives considered.**

- **Re-raise raw `psycopg2.errors.UniqueViolation`** — rejected: psycopg2 stack is a
  leaky abstraction; the pgcode `"23505"` leaks into FastAPI's default exception handler
  and lands in the body. Coupling the client to psycopg2 versions.
- **Use a custom Postgres `RAISE EXCEPTION` with a stable SQLSTATE** — rejected: the
  constraint is invoked at INSERT time; there is no PL/pgSQL intermediary to format the
  error. Trying to attach `RAISE EXCEPTION` to a check constraint re-routes the design
  through a TRIGGER (out of scope, see R1 in §9) and breaks F1.8's
  `STABLE/VOLATILE`-only-on-functions precedent.
- **Map to 422 (semantic invalid)** — rejected: the request is well-formed; the row is
  rejected because the DB violates the invariant. 409 Conflict matches the HTTP semantics
  better than 422 Unprocessable Entity ("a 422 means the server understands the content
  type and the syntax, but was unable to process the contained instructions", RFC 4918).
- **Single 500 with a generic message** — rejected: leaves the client with no
  discriminator; callers cannot distinguish "ya tienes sesión abierta" from any other DB
  failure.

**Rationale.** 409 + a stable `{"error": "sesion_already_active"}` keeps the discriminator
deterministic and lets the client differentiate from "crear_sesión con datos inválidos"
(422) or "BD caída" (500). The pgcode and raw message move to log lines at `warning` with
`event="sesion_already_active"` and the actor UUID — never to the response surface.

**Trade-off (explicit).** Operations team sees only the typed code in their grafana/PagerDuty
dashboard; diagnosis requires `event="sesion_already_active"` log search. Acceptable: it is a
defensive surface aimed at clients; ops triangulation is a separate, documented act.

### Decision KD-2 — Repo re-emits typed `SesionAlreadyActive`, handler maps to 409

**Choice.** `repo/session_cycle.py::open_session` wraps `session.add(new_row)` followed by
`await session.flush()` in `try/except IntegrityError as exc:`. On
`pgcode == "23505"` it raises `SesionAlreadyActive(uuid_usuario=...)`; on any other
`IntegrityError` it re-raises. The handler at `api/v1/caja_sesion.py::open_sesion` wraps the
`open_session(...)` call in `try/except SesionAlreadyActive` → `HTTPException(409,
detail={"error": "sesion_already_active"})`.

**Context.** Today, the helper in `session_cycle.py` does `session.add(new_row)` and
returns the row; the caller calls `await session.commit()`. The DB exception surfaces from
the implicit commit as a 500 because there is no matching `except IntegrityError`. KD-2
adds an explicit `flush()` BEFORE the implicit commit so the `UniqueViolation` is
inspectable in-process; an explicit `try/except` re-emits as a domain exception.

**Alternatives considered.**

- **Catch `IntegrityError` at the handler** — rejected: the handler has the wrong boundary.
  `IntegrityError` can come from many sources — the foreign key to `usuarios`/`sucursal`,
  NOT NULL on `valor_inicial_*`, etc. — and pgcode discrimination at the handler costs a
  per-handler copy of the discrimination logic. Repo is the natural seam.
- **Detect by `isinstance(exc.orig, psycopg2.errors.UniqueViolation)`** — rejected: driver
  wrapping can sub-class `UniqueViolation` (asyncpg path, future SQLAlchemy 2.x changes);
  pgcode string is robust to wrapping. Precedent: PG-error-handling code throughout
  `repo/` uses `pgcode == "..."` not `isinstance`.
- **Pre-check before INSERT (KD-3)** — covered below; rejected.

**Rationale.** The repo/handler split keeps domain error mapping near the DB (where it
originates) and HTTP status mapping near the wire (where it belongs). Avoiding the
pre-check in the repo means there is no TOCTOU window between check and INSERT.

**Forward compatibility.** The same pattern (catch by pgcode, re-emit typed domain
exception, map at the handler) applies naturally if a future table gains a similar
partial unique index (e.g., `prod.caja` if ever introduced). The exception class is named
`SesionAlreadyActive` to keep that future work self-contained.

### Decision KD-3 — No pre-check, partial unique index is authoritative

**Choice.** The repo does NOT execute `SELECT … WHERE uuid_usuario=:u AND timestamp_cierre
IS NULL` before `INSERT`. The DB partial unique index is the only correctness guarantee;
the existing app-level check (if any) stays as a fast-path friendly-message channel but
is NOT relied upon for correctness.

**Context.** Spec calls this out explicitly: "the contract MUST NOT introduce a pre-check
`SELECT … WHERE uuid_usuario=:u AND timestamp_cierre IS NULL` before the INSERT (KD-3
BD-only)".

**Alternatives considered.**

- **Pre-check + DB constraint** — rejected: two round-trips, doubles latency on the happy
  path, opens a TOCTOU window between check and INSERT. The DB constraint is enough on
  its own; the app-level message is identical either way.
- **Pre-check only** — rejected: weakens defense in depth (single point of failure), drifts
  from the F1.8 precedent (AST walk + `STABLE` + read-only contract), erodes the invariant.
- **DB constraint only (chosen)** — accepted: single source of truth, defense in depth, fast
  on happy path, race-free at the DB.

**Rationale.** Consistent with F1.8 (`STABLE` + AST walk rejecting DML in
`calcular_cotizacion`): the database is the source of truth for "no mutation",
not the application. KD-3 turns that pattern from "mutation veto" to "uniqueness veto".

### Decision KD-4 — `operador-` and `admin-` both accepted on `/sesion/me`, 404 if no session

**Choice.** `GET /api/v1/caja-sesion/sesion/me` accepts both `operador-` and `admin-`
issuers (reuses the existing `_sesion_issuer_dep = requires_issuer("operador-", "admin-")`
at `caja_sesion.py:35`). It resolves `ctx.actor_uuid` from the JWT subject and queries
`prod.sesion WHERE uuid_usuario = ctx.actor_uuid AND timestamp_cierre IS NULL ORDER BY
timestamp_apertura DESC NULLS LAST LIMIT 1`. If the result is `None`, the response is
exactly `404 {"error": "sesion_no_active"}` — the same body the `operador-` issuer would
receive; no admin bypass, no synthetic 200 with `null`.

**Context.** Admins can open a cashier shift in the existing codebase (POST /sesiones
already permits admin-). The `/me` endpoint serves whatever the JWT says the actor is. If
an admin is mid-arqueo and consults `/me`, they get their own sesión activa; if not, they
get 404 — semantic integrity with the operador case.

**Alternatives considered.**

- **`operador-` only** — rejected: rejected by `plan.md` GAP-BE-LS-04 rationale
  ("operadores Y admins deben poder abrir sesión"); the issuer_dep already accepts both.
- **`admin-` gets a synthetic 200 `{session: null}`** — rejected: introduces a different
  response shape per issuer, breaks REST contract uniformity. 404 is canonical REST for
  "no resource found at this URI for this principal".
- **`admin-` gets a 200 with the latest session of any operator** — rejected: security
  hazard; would leak other operators' shift data. Even setting aside the leak, no
  precedent in the codebase for "admin sees all operators' sessions" — out of scope.

**Rationale.** Symmetric response for both issuers is the REST-canonical choice. KD-4
documents the door for a future `GET /caja-sesion/sesion/{uuid_usuario}/active`
(`admin-`-only, explicit query) but explicitly defers it; HU-F1.3 only covers `/me`.

**Forward hook.** A `?actor_uuid=X` form is documented in REQ-OPS-029's "Out of Scope"
section; future HU can build it without reopening this KD.

## 5. Migration 0023

**Path**: `backend/packages/parkos_core/migrations/versions/0023_add_sesion_unique_active.py`.

**SQL skeleton** (the structural shape; the apply phase will produce the literal file):

```python
"""HU-F1.3: partial unique index on prod.sesion(uuid_usuario) WHERE
timestamp_cierre IS NULL — at most ONE active cash session per operator.

The pre-flight block detects orphan data pre-existing the migration and
ABORTS with a typed error if it finds any actor with > 1 active sessions.
If pre-flight passes, we create the partial unique index CONCURRENTLY so
cashier operations do not block on an AccessExclusiveLock.

KEPT IN SYNC WITH: spec/operations/spec.md REQ-OPS-026 (RFC 2119 MUST:
pre-flight abort; CONCURRENTLY; partial predicate).
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0023_sesion_unique_active"
down_revision = "0022_create_calcular_cotizacion"  # F1.8 precedent
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Pre-flight: abort the migration if any (uuid_usuario) already has
    #    > 1 active sesion. CREATE UNIQUE INDEX would fail with a cryptic
    #    "duplicate key value violates unique constraint" message; we
    #    emit a typed error listing the count and the offending UUIDs so
    #    an operator can close them manually before retrying.
    op.execute(
        """
        DO $$
        DECLARE
            n_bad INT;
            offenders TEXT;
        BEGIN
            SELECT count(*) INTO n_bad
            FROM (
                SELECT uuid_usuario
                FROM prod.sesion
                WHERE timestamp_cierre IS NULL
                GROUP BY uuid_usuario
                HAVING count(*) > 1
            ) t;
            IF n_bad > 0 THEN
                SELECT string_agg(uuid_usuario::text, ', ') INTO offenders
                FROM (
                    SELECT uuid_usuario
                    FROM prod.sesion
                    WHERE timestamp_cierre IS NULL
                    GROUP BY uuid_usuario
                    HAVING count(*) > 1
                ) ord;
                RAISE EXCEPTION
                    'unique_active_sesion_preflight_failed: % uuid_usuario(s) '
                    'with >1 active sesion. Close them manually first: %',
                    n_bad, offenders
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
        END $$;
        """
    )

    # 2) Create the partial unique index CONCURRENTLY so we do NOT take an
    #    AccessExclusiveLock against prod.sesion while it's serving the
    #    cashier operations. CONCURRENTLY cannot run inside a transaction;
    #    Alembic supports this via op.execute (autocommit per statement).
    op.execute(
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
            prod.uq_prod_sesion_one_active_per_user
        ON prod.sesion (uuid_usuario)
        WHERE timestamp_cierre IS NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX CONCURRENTLY IF EXISTS
            prod.uq_prod_sesion_one_active_per_user;
        """
    )


__all__ = ["upgrade", "downgrade"]
```

**Notes.**

- `CONCURRENTLY` cannot run inside a transaction block (Postgres rule). Alembic's
  `op.execute` runs each statement in autocommit by default; the `DO $$ … $$` pre-flight
  block IS transactional but does not write any persistent state, so it is safe.
- `IF NOT EXISTS` makes the migration **idempotent**: a retry of `alembic upgrade` after a
  pre-flight abort finds nothing to do and Alembic records the version cleanly. A retry
  after a successful upgrade also no-ops (no error).
- The `down_revision = "0022_create_calcular_cotizacion"` keeps the linear chain
  consistent (0022 was consumed by F1.8).
- `downgrade` uses `DROP INDEX CONCURRENTLY IF EXISTS` (best practice; matches the upgrade
  build mode) per REQ-OPS-026 RFC 2119 SHOULD.

**Idempotency argument.** If the migration is run twice in a row:
- 1st run: pre-flight `n_bad = 0`, CREATE INDEX creates the index.
- 2nd run: pre-flight still `n_bad = 0` (the index does not introduce new active rows);
  CREATE INDEX is a no-op because of `IF NOT EXISTS`.

If pre-flight aborts on the 1st run (`n_bad > 0`), Alembic rolls back the in-progress
transaction (the `DO $$ … RAISE EXCEPTION` raises `IntegrityError`), records no version
bump, and the operator can address the orphans and re-run.

## 6. Endpoint Design

### `GET /api/v1/caja-sesion/sesion/me` (NUEVO)

**Registered**: in `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py`,
with `@router.get("/sesion/me")` declared **BEFORE** the
`router.include_router(make_router(resource="sesion", write_enabled=False, ...))` block at
lines 193-207. FastAPI's path specificity rule (literal `/me` matches before parametric
`/{uuid}`) resolves any collision deterministically.

**Handler signature** (the structural shape; apply phase writes the literal):

```python
@router.get(
    "/sesion/me",
    response_model=SesionRead,
    summary="Get the active session for the authenticated user (REQ-OPS-027, REQ-OPS-029).",
)
async def get_my_sesion(
    response: Response,                                        # for Cache-Control: no-store
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_sesion_issuer_dep),
) -> SesionRead:
    """REQ-OPS-027 + REQ-OPS-029: return the actor's unique active session or 404.

    Reads prod.sesion filtered by ctx.actor_uuid and timestamp_cierre IS NULL.
    The partial unique index (REQ-OPS-026) guarantees at most one such row;
    ORDER BY timestamp_apertura DESC NULLS LAST LIMIT 1 is defensive (e.g.,
    the index was dropped by an operator during an emergency; the read still
    returns the most recent active session deterministically).
    """
    row = await get_sesion_activa(session, actor_uuid=ctx.actor_uuid)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "sesion_no_active"},
        )
    response.headers["Cache-Control"] = "no-store"
    return SesionRead.model_validate(row)
```

**Route order contract** (KD-1 + R3): the `get_my_sesion` decorator MUST be evaluated
(called) **before** the `router.include_router(make_router(...))` line. FastAPI registers
routes in declaration order; if `get_my_sesion` lands after the include_router, FastAPI
matches `/{uuid}` first and returns 422 for `me` as an "invalid UUID". A comment block
in `caja_sesion.py` (just below `router = APIRouter(...)`) documents this contract; a
test verifies the path resolution order.

**Response shapes**:

| HTTP | Body | Headers | Trigger |
|---|---|---|---|
| 200 | `SesionRead` (12 fields) | `Cache-Control: no-store` | Actor has ≥ 1 active sesion |
| 404 | `{"error": "sesion_no_active"}` | (default) | Actor has 0 active sesiones |
| 401/403 | (default) | (default) | Issuer not `operador-/admin-`; JWT invalid |
| 422 | (default) | (default) | Defensive — path `/me` is literal; no body fields |

**Helper** (`repo/sesion_activa.py`):

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.L_S.sesion import Sesion


async def get_sesion_activa(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
) -> Sesion | None:
    """REQ-OPS-027 / KD-1: resolve the actor's unique active sesion.

    Returns the most recently opened active sesion (ORDER BY
    timestamp_apertura DESC NULLS LAST) or None. The partial unique index
    (REQ-OPS-026) makes the LIMIT 1 defensive: at most one row satisfies
    the predicate. SQL is parameterized through SQLAlchemy bind params;
    no string interpolation.
    """
    stmt = (
        select(Sesion)
        .where(Sesion.uuid_usuario == actor_uuid)
        .where(Sesion.timestamp_cierre.is_(None))
        .order_by(Sesion.timestamp_apertura.desc().nulls_last())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
```

**`POST /api/v1/caja-sesion/sesiones`** (MODIFICAR, +6 LOC around the existing
`open_session(...)` call):

```python
try:
    new_row = await open_session(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=payload.uuid_sucursal,
        valor_inicial_efectivo=valor_efectivo,
        valor_inicial_datafono=valor_datafono,
        uuid_usuario=payload.uuid_usuario,
        log_tx=True,
    )
except SesionAlreadyActive:
    # KD-1 mapping: typed body, no pgcode leak.
    raise HTTPException(
        status_code=409,
        detail={"error": "sesion_already_active"},
    )
await session.commit()
await session.refresh(new_row)
return SesionRead.model_validate(new_row)
```

**`repo/session_cycle.py::open_session`** modification (KD-2):

```python
from psycopg2.errors import UniqueViolation  # psycopg2 2.9+
from sqlalchemy.exc import IntegrityError

async def open_session(session, *, actor_uuid, uuid_sucursal, valor_inicial_efectivo,
                       valor_inicial_datafono, uuid_usuario, log_tx=True, uuid=None):
    ...
    session.add(new_row)
    if log_tx:
        log_row = LogTransaccional(...)
        session.add(log_row)
    try:
        # Forces UniqueViolation here (PG partial unique index REQ-OPS-026).
        await session.flush()
    except IntegrityError as exc:
        # Catch by pgcode, not isinstance — robust to asyncpg/SQLAlchemy wrapping.
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        if pgcode == UniqueViolation.sqlstate:  # == "23505"
            raise SesionAlreadyActive(uuid_usuario=uuid_usuario) from exc
        raise
    return new_row
```

## 7. Tests Design

The flow follows F1.8's TDD pattern (RED → GREEN → REFACTOR → VERIFICATION). Total: 13
tasks across 4 phases.

### RED — write tests first (4 HTTP tests + 1 mapping test)

`backend/tests/unit/test_caja_sesion_me.py` (httpx.AsyncClient + ASGITransport + JWT
operador fixture, F1.8 pattern):

| # | Test | Asserts | TDD role |
|---|---|---|---|
| T1 | `test_operador_con_sesion_activa_devuelve_sesion_read` | 200 + body is a `SesionRead` with correct `uuid_usuario`, `timestamp_cierre=None` | RED until handler exists |
| T2 | `test_operador_sin_sesion_activa_devuelve_404_sesion_no_active` | 404 + `body["error"] == "sesion_no_active"`; NO pgcode in body or headers | RED until handler exists |
| T3 | `test_issuer_cliente_rechazado_en_sesion_me` | 401/403 with body UNCHANGED from the rest of caja_sesion (issuer_dep rejection); `get_my_sesion` body never reaches | RED until handler exists |
| T4 | `test_dos_sesiones_cerradas_y_una_abierta_devuelve_la_abierta` | 200 + body matches the open `Sesion` (defense in depth: ORDER BY DESC NULLS LAST) | RED until handler exists |

`backend/tests/unit/test_sesion_already_active_mapping.py` (F1.8 + F1.2 patterns):

| # | Test | Asserts | TDD role |
|---|---|---|---|
| T5 | `test_open_session_re_emite_sesion_already_active_en_unique_violation` | A `MagicMock(exc)` with `orig.pgcode == "23505"` triggers `SesionAlreadyActive(uuid_usuario=…)` | RED until repo is patched |
| T6 | `test_open_sesion_handler_mapea_sesion_already_active_a_409_sin_pgcode` | `POST /sesiones` with a forced 23505 returns 409 + `body["error"] == "sesion_already_active"`; `pgcode` string NEVER in body or headers | RED until handler is patched |

### GREEN — implement minimum to pass

- Land migration 0023 (pre-flight + CREATE INDEX CONCURRENTLY).
- Land `repo/sesion_activa.py::get_sesion_activa`.
- Land `exceptions.py::SesionAlreadyActive`.
- Modify `repo/session_cycle.py::open_session` with the `try/except IntegrityError` block.
- Modify `api/v1/caja_sesion.py::open_sesion` with the `try/except SesionAlreadyActive` block.
- Add `get_my_sesion` handler BEFORE the include_router line.

### REFACTOR — AST guard + OpenAPI tag documentation

- Land `tests/static/test_no_write_in_caja_sesion_me.py` (F1.8 AST pattern, but on the
  Python handler `get_my_sesion` instead of a PL/pgSQL function body). Rejects
  `INSERT|UPDATE|DELETE|TRUNCATE/MERGE` strings inside the `get_my_sesion` source.
- Add OpenAPI `tags=["caja-sesion"]` (already inherited) + `responses={404: {"description":
  "sesion_no_active"}}` for OpenAPI consumers.

### VERIFICATION — DB integration

`backend/tests/integration/test_caja_sesion_unique_constraint_db.py`
(`parkos-branch-db` real, `PARKOS_DOCKER_TEST=1`):

| # | Test | Asserts |
|---|---|---|
| T7 | `test_dos_sesiones_abiertas_mismo_usuario_falla_unique` | Insert session 1 then session 2 for same `uuid_usuario` with `timestamp_cierre=None` → second INSERT raises `UniqueViolation` (pgcode 23505) |
| T8 | `test_segunda_sesion_despues_de_cerrar_primera_pasa` | Close session 1 (`timestamp_cierre = now()`), then insert session 2 → succeeds because partial predicate excludes closed rows |

Both tests confirm the migration's CONCURRENTLY-built index correctly enforces the
invariant AND is partial (lets two historical closed sesiones for the same user coexist).
The pre-flight abort is exercised in the static test as a "second-run returns idempotent"
smoke check.

### Mandatory CI gates (existing)

- `ruff check`, `ruff format --check`, `mypy --strict` on new + modified files (5 new + 1 modified).
- `factory_intact`: `git diff api/v1/router_factory.py` returns empty.

## 8. Threat Matrix

| # | Threat | Attack surface | Mitigation | Residual risk |
|---|---|---|---|---|
| **T1** | Doble apertura concurrente misma UUID (race condition TOCTOU entre dos requests del mismo operador en ms) | `POST /sesiones` simultáneos para mismo `uuid_usuario` | KD-2 + KD-3: la BD rechaza el segundo INSERT vía partial unique index `uq_prod_sesion_one_active_per_user`. El repo captura `IntegrityError` por pgcode `"23505"`, re-emite `SesionAlreadyActive`, handler lo mapea a 409. Defense in depth: la app-level fast-path check sigue ahí como friendly-message channel pero no es la barrera | Log de `event="sesion_already_active"` + `uuid_usuario` para diagnóstico de ops; ningún pgcode ni driver string llega al cliente |
| **T2** | Datos huérfanos pre-existentes (doble sesión activa para misma UUID) hacen fallar `CREATE UNIQUE INDEX` con mensaje críptico | `alembic upgrade` contra BD con legacy data | Pre-flight en migración 0023 con `DO $$ … HAVING count(*) > 1 … RAISE EXCEPTION` lista los UUIDs offending. Alembic registra no version bump on abort (R-Alembic) | Operador debe cerrar manualmente las huérfanas antes de reintentar. Migración no avanza. Housekeeping pre-deploy documentado en `proposal.md §10` |
| **T3** | `actor_uuid` None en JWT (`sub` ausente o preproceso falla) | JWT mal formado | `TenantContext` upstream (HU-F1.2) garantiza `actor_uuid` no-None para claims válidos. Si llegara None, la query `WHERE uuid_usuario = NULL` retorna 0 filas → 404 `sesion_no_active` (consistente con "no hay sesión") | Defensa en profundidad: HU-F1.2 ya filtra este caso aguas arriba. Si llegara None sin pasar por HU-F1.2, la respuesta es 404 (mismo body, no leak) |
| **T4** | `admin-` sin sesión activa — endpoint `me` siempre devuelve 404 para admin (no suelen abrir caja) | Frontend admin consulta `/me` esperando ver caja | KD-4: respuesta 404 `sesion_no_active` igual a la del operador. Cliente debe distinguir 404 (no hay sesión) vs 401 (no auth) | Mensaje 404 puede confundir si el cliente asume 404 ⇒ "auth falló"; documentado en OpenAPI `responses` |
| **T5** | Path collision `/sesion/me` vs `/sesion/{uuid}` — un dev futuro registra el handler DESPUÉS del `include_router`, FastAPI matchea `/{uuid}` y devuelve 422 | PR futuro con orden de registro alterado | KD-1 + KD-4: comentario inline en `caja_sesion.py` (después de `router = APIRouter(...)`) sobre el orden de registro. Test RED T2 verifica que `/me` resuelve ANTES que `/{uuid}`. AST guard `tests/static/test_no_write_in_caja_sesion_me.py` podría extenderse a "verifica que `@router.get('/sesion/me')` está declarado antes del `include_router`" si se requiere más defensa | Comentario + test es la red principal; cobertura AST aún no es contractualmente obligatoria para esta invariante |
| **T6** | Migración CONCURRENTLY falla a mitad (kill -9 en mitad del build) → índice queda INVALID | BD bajo carga durante deploy | `CONCURRENTLY` puede dejar el índice INVALID si falla a mitad. Documentado en `proposal.md §10 Out of Scope`: rebuild vía `DROP INDEX …; CREATE UNIQUE INDEX CONCURRENTLY …` es idempotente. `IF NOT EXISTS` asegura retries seguros | Operador debe verificar `SELECT indisvalid FROM pg_index WHERE indexrelid = 'prod.uq_prod_sesion_one_active_per_user'::regclass` antes de considerar la migración exitosa |
| **T7** | AST walk permite mutaciones accidentales (un dev futuro agrega `INSERT` en `get_my_sesion`) | Modificación del handler `get_my_sesion` | KD-1 + KD-2: AST guard `tests/static/test_no_write_in_caja_sesion_me.py` rechaza `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` en el cuerpo del handler. Patrón de F1.8 (`test_no_write_in_calcular_cotizacion.py`). CI gate | Defense in depth: el test atrapa el caso antes de merge; CI atrapa al dev; el handler ES read-only por contrato (sin JOINs a tablas mutables, sin `session.execute(text("UPDATE …"))`) |
| **T8** | Pgcode leak en response — driver o FastAPI exception handler filtra `pgcode=23505` al cuerpo | PR futuro que importa `IntegrityError` en handler no tipado, sin filtrar | KD-1: `HTTPException(409, detail={"error": "sesion_already_active"})` literal-string body. Test RED T6 verifica que `pgcode` string NO aparece en `body` ni en `headers`. OpenAPI documentation explícita | Defense in depth: aunque un dev futuro cometa el leak, el test RED T6 falla en CI antes del merge |

## 9. Risks

| # | Riesgo | Severidad | Mitigación | Referencia |
|---|---|---|---|---|
| **R1** | Datos huérfanos pre-existentes (dos sesiones activas mismo `uuid_usuario`) hacen fallar `CREATE UNIQUE INDEX` con mensaje críptico | Media | Pre-flight `GROUP BY … HAVING count(*) > 1` antes del CREATE. Aborta con lista explícita de `uuid_usuario`. Operador decide: cerrar manualmente o abortar deploy | §5 SQL skeleton |
| **R2** | Repo `open_session` actual NO captura `UniqueViolation` específicamente — segundo intento crashea con 500 | Media | KD-1 + KD-2: `open_session` captura por pgcode 23505, re-emite `SesionAlreadyActive`. Handler HTTP mapea a 409 | §4 KD-2 + §6 handler |
| **R3** | Handler dedicado registrado después del `include_router` → FastAPI matchea `/{uuid}` y devuelve 422 | Baja | Comentario inline en `caja_sesion.py` líneas 33-36 sobre orden. Test RED T1-T4 verifica path resolution | §4 KD-4 + §6 route order |
| **R4** | `admin-` no suele abrir sesión de caja — endpoint `me` siempre devuelve 404 para admin. ¿Es útil? | Baja | KD-4: 404 coherente con la realidad. Futuro `?actor_uuid=X` (con prefijo `admin-` y audit log) cubre el caso "ver la caja de OTRO" | §4 KD-4 + §10 out of scope |
| **R5** | `CREATE INDEX CONCURRENTLY` puede tardar minutos en tablas grandes | Baja | `prod.sesion` tiene cardinalidad esperada < 100 filas/sede × N sedes = pocos miles. Index trivialmente rápido (< 1s). Documentado en `proposal.md §8 R5` | §5 SQL skeleton |
| **R6** | Race entre `get_sesion_activa` (read) y `close_session_with_log` (write) — el endpoint podría devolver una fila que se cierra milisegundos después | Baja | El endpoint es informativo, no coordina mutaciones. Sin lock. Consistente con REST: "la sesión activa AHORA es esta; si la cierras inmediatamente, una siguiente llamada puede devolver 404" | §6 handler signature |
| **R7** | Dev futuro agrega `INSERT|UPDATE|DELETE` accidental en `get_my_sesion` — rompe read-only | Baja | AST walk `tests/static/test_no_write_in_caja_sesion_me.py` rechaza mutaciones. CI gate | §7 REFACTOR + §8 T7 |
| **R8** | `TenantContext.actor_uuid` puede ser None si el JWT no incluye `sub` → query retorna 0 filas, no error | Baja | Defensa en profundidad: HU-F1.2 garantiza `actor_uuid` no-None. Si llegara None, query retorna 0 filas → 404 `sesion_no_active` (consistente) | §8 T3 |
| **R9** | `make_router` tiene `GET /sesion/{uuid}` registrado — colisión de ruta con `GET /sesion/me` | Baja | FastAPI matchea por especificidad: `/me` literal gana sobre `/{uuid}` paramétrico. Test RED T1-T2 verifica match order | §8 T5 |

## 10. Out of Scope / Future Hooks

### Out of scope (HU-F1.3 NO cubre)

1. **Endpoint `GET /caja-sesion/sesion/{uuid_usuario}/active`** — consultar sesión activa
   de OTRO usuario con `admin-` issuer. Documentado como "future HU" en KD-4 + REQ-OPS-029
   (Open Question: ¿diferenciar admin-de-cualquier-cosa vs admin-de-este-operador? — sale
   de scope, requiere su propio analysis de seguridad). Solo `/me` se aterriza.
2. **Endpoint `POST /caja-sesion/sesion/me/cerrar`** — cierre directo sin pasar por
   `/{uuid}/cerrar`. El endpoint existente cubre el caso con uuid conocido (`PUT
   /sesion/{uuid}/cerrar`, REQ-41). Sale de scope.
3. **Notificación WebSocket cuando un segundo operador intenta abrir sesión con un
   `uuid_usuario` ya activo** — out of MVP backend scope (alinéado con futuras HU de
   observabilidad F1.X).
4. **Lock pesimista sobre la fila activa en `get_sesion_activa` (`FOR SHARE`/`FOR
   UPDATE`)** — el endpoint es informativo, no coordina mutaciones. Replica el patrón de
   F1.8 (KD-1) sin aplicarlo aquí.
5. **Auditoría "quién intentó abrir segunda sesión"** — futuro, requiere tabla de eventos
   de seguridad separada (security event store).
6. **Aplicar el mismo partial unique index pattern a otras tablas `[L-*]` con invariante
   "una fila activa por actor"** — ej. `prod.caja` si existe. Sale de scope.
7. **Migración de limpieza automática** (`DELETE FROM prod.sesion WHERE timestamp_cierre
   IS NULL AND uuid_usuario IN (...)`) cuando el pre-flight detecta huérfanos. Operador
   decide manualmente (KD-1 explícito).
8. **Frontend versioning (Fase 2)** — esta HU aterriza backend solamente.
9. **Métricas / observabilidad (contador de 409, latencia de `/me`)** — alineado con futura
   HU de observabilidad F1.X; este change no agrega counters Prometheus.
10. **Cache-headers en `/me` más allá de `Cache-Control: no-store`** — no se negocia
    `ETag`, `Vary`, ni `Authorization-aware caching`. `no-store` es suficiente para
    privacidad de sesión y consistencia transaccional.

### Future hooks (reusable pattern, no scope)

- **KD-1 reusable**: `IntegrityError → HTTPException` mapping via typed domain exception
  is a pattern. Future constraints on other `[L-*]` tables (e.g., `prod.caja` if it
  exists, `prod.login` open per device) can mirror it.
- **KD-2 reusable**: `repo/*` helper that flushes before commit and re-emits a typed
  domain exception by pgcode is a pattern. Future `repo/login_cycle.py::record_login`
  could apply the same try/except IntegrityError wrapper if `prod.login(uuid_usuario)
  WHERE timestamp_cierre IS NULL` ever gains a partial unique index for "one open device".
- **KD-3 reusable**: "DB constraint is authoritative, no pre-check" is a pattern. Future
  bi-temporal uniqueness invariants can adopt it.
- **AST guard reusable**: `tests/static/test_no_write_in_*.py` is a CI gate. Future
  read-only custom endpoints can re-use the same module, parametrized by handler name.

## 11. References

### This change (hu-f1-3-sesion-unica)

- `openspec/changes/hu-f1-3-sesion-unica/exploration.md` — exploration phase (data
  gathered inline 2026-09-14; KD-1..KD-4 preliminaries).
- `openspec/changes/hu-f1-3-sesion-unica/proposal.md` — proposal phase (D-HU-F1.3-1..8;
  KD-1..KD-4 confirmed; goals/non-goals; architecture overview).
- `openspec/changes/hu-f1-3-sesion-unica/specs/operational/spec.md` — spec RFC 2119
  (REQ-OPS-026 pre-flight + CONCURRENTLY; REQ-OPS-027 `GET /sesion/me`; REQ-OPS-028
  `UniqueViolation → 409`; REQ-OPS-029 `operador- + admin-` issuers accepted).

### Precedents (archive, base-pattern reuse)

- `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/design.md` — PL/pgSQL migration +
  custom handler + AST walk pattern (commit `a3d0c39`); same 11-section structure;
  precedent for `Cache-Control: no-store`, `precedente más reciente: PL/pgSQL + custom
  handler + AST walk`.
- `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/design.md` — helper-pure
  pattern + bi-temporal precedent (commit `de4d2fc`); same 11-section structure;
  precedent for "handler dedicado antes del mount genérico".

### Source files

- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` — router custom
  (`router = APIRouter(prefix="/caja-sesion", tags=["caja-sesion"])`, line 33;
  `_sesion_issuer_dep`, line 35; `open_sesion`, lines 70-113; `cerrar_sesion`,
  lines 116-142; `arqueo_diferencias`, lines 145-190; `include_router(make_router(...))`,
  lines 193-207).
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py::open_session`
  (lines 180-251) — current INSERT helper; KD-2 modification wraps the flush in
  try/except IntegrityError with pgcode 23505 → SesionAlreadyActive.
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py::close_session_with_log`
  (lines 254-333) — precedent for the log-first pattern; not modified by this change.
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py::record_login`
  (lines 39-116) — precedent for co-transactional `log_transaccional`; `open_session`
  already follows the same pattern.
- `backend/packages/parkos_core/src/parkos_core/models/L_S/sesion.py` — ORM model
  (numeric columns, nullable timestamps, nullable FKs).
- `backend/packages/parkos_core/src/parkos_core/api/router_factory.py` — `make_router`
  factory (HU-F1.1 GAP-BE-02, commit `f7cb37a`, **intacto** — verified by
  `factory_intact` CI gate).
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` — `TenantContext`
  (`actor_uuid`, HU-F1.2, used by `get_tenant_ctx`).
- `backend/packages/parkos_core/src/parkos_core/schemas/caja.py` — `SesionRead`,
  `SesionCreate`, `SesionUpdate`, `SesionReadList` (reused **sin cambios**).

### Data model

- `modelo_datos_er.mmd` — tabla `prod.sesion` (lines 715-740, edge definitions
  1198-1202 with `sucursal`/`usuarios`/`factura_pagos`/`arqueo`); **sin cambios de esquema**.

### Plans and cross-references

- `plan.md` — GAP-BE-LS-04 rationale (justifica el partial unique index + el endpoint
  `/me`; this design references it for ground truth on the operational gap).
- `openspec/specs/operations/spec.md` — capability root (last REQ-OPS-NNN vigente was
  REQ-OPS-025 from F1.8; REQ-OPS-026..029 from this change are deltad-in via
  `Modified Capabilities` in the same file post-archive).

### Tests

- `backend/tests/static/test_no_write_in_calcular_cotizacion.py` — AST walk precedent for
  the same pattern adapted to the Python handler `get_my_sesion`
  (`test_no_write_in_caja_sesion_me.py`).
- `backend/tests/unit/test_calcular_cotizacion.py` — `httpx.AsyncClient + ASGITransport +
  JWT operador fixture` precedent (mirrored by `test_caja_sesion_me.py`).
- `backend/tests/unit/test_auth_login_password.py` — auth fixture precedent (bypass JWT
  through `issuer_dep`).
- `backend/tests/integration/test_calcular_cotizacion_db.py` — `parkos-branch-db` DB
  integration precedent (mirrored by `test_caja_sesion_unique_constraint_db.py`).

---

**Design complete.** Ready for `sdd-tasks` with theme: TDD-strict 13 tasks (4 RED + 5
GREEN + 2 REFACTOR + 2 VERIFICATION). Onward to `sdd-apply` after tasks acceptance and
user sign-off on the proposal.
