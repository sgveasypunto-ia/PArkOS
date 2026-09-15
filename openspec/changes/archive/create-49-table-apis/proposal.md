# Proposal: create-49-table-apis

> **Change**: `create-49-table-apis`
> **Phase**: propose (sdd-propose)
> **Status**: draft, awaiting user ratification
> **Preflight**: `pace=auto`, `artifact=hybrid` (OpenSpec + Engram), `delivery=auto-chain`,
> `chain=gitflow` (`main` + `dev` + feature branches; PRs merge to `dev` only),
> `review_budget=800 lines/PR`.
> **Inputs read**: `modelo_datos_er.mmd` (1178 lines, 49 tables), Engram #1264, exploration.md (345 lines), AGENTS.md, `openspec/config.yaml`, drifted docs listed in [Pre-existing Doc Drift Reconciliation](#pre-existing-doc-drift-reconciliation).

## Why

The parking-lot business runs on three engines: multi-tenant cloud-edge
topology (cloud admin over central Postgres, each branch over its own local
Postgres with bidirectional HTTP-polling sync), strict audit-first /
bi-temporal / no-physical-DELETE data discipline (DIAN Colombia: 5+ year
retention + SHA256 hash chain on `log_transaccional` and `revocacion_factura`
per `uuid_sucursal`), and a 49-table relational model that today exists ONLY
as a Mermaid ER diagram and a single Alembic bootstrap migration. Nothing
above the data layer exists yet — there is no ORM, no Pydantic v2 surface, no
FastAPI router, no shared helper that enforces the audit-first contract at
the API boundary, no PWA-consumable OpenAPI document.

Without this change, every future feature starts from raw SQL and `cur.execute()`
— an audit-first architecture that depends on three layers of defense
(see [Architectural Principles in AGENTS.md](../../AGENTS.md#architectural-principles))
gets hand-waved at layer 1 (API), leaving only layers 2 (ORM) and 3 (DB
REVOKE + triggers) to carry compliance. That is exactly the failure mode the
project's canon is designed to prevent.

`bootstrap-monorepo-foundation` (active change, six chained PRs in flight)
stands up the monorepo skeleton and the initial schema migration. It DOES
NOT ship application code. This change layers on top of it and converts the
49 entities into a typed, tenant-scoped, DIAN-aware API surface with
mechanical three-layer enforcement: no DELETE endpoint, no ORM `UPDATE` on
`[V]/[A]`, DB REVOKE + `BEFORE UPDATE OR DELETE` triggers on every `[A]`
table. Every future iteration (login, ingreso, factura electrónica, etc.)
will compose these helpers — they cannot be re-implemented per feature.

The cloud-edge topology, the JWT three-issuer model, the DIAN-only boundary,
and the gitflow branching policy were all ratified in earlier sessions and
fix this change's inputs; this proposal does not re-open them.

## What changes

One concrete, vertical-yet-data-centric deliverable per enforcement class:

**ORM layer** (`backend/packages/parkos_core/models/`)

- `V/` — 26 SQLAlchemy 2.0 async ORM classes for the 26 `[V]` tables
- `L_E/` — 3 ORM classes for `ingreso`, `facturas`, `factura_electronica` (insert-only)
- `L_W/` — 6 ORM classes for the 6 `[L-W]` workflow chains (insert-only)
- `L_S/` — 2 ORM classes for `login`, `sesion` (UPDATE permitted only on the
  documented close columns, with mandatory co-transactional `log_transaccional`
  insert)
- `A/` — 12 ORM classes for the 12 `[A]` append-only tables; mapping enforces
  `INSERT`-only via the helper layer (no `session.execute(update(...))` on
  these classes; static analysis test)
- Every model carries `created_at`, `created_by`, `vigente_desde`,
  `vigente_hasta` (where applicable), `estado` (where applicable),
  `sync_status`, `sync_timestamp`, `sync_attempts`
- Partition-key columns on high-volume `[A]` tables (`ingreso`-implied,
  `salidas`, `factura_detalle`, `factura_pagos`, `log_transaccional`,
  `sync_log`, `sync_queue`, `caja`, `arqueo`) are documented as
  mandatory filter inputs on every ORM helper call (the bootstrap migration
  installs `pg_partman` partitions)

**Pydantic v2 schemas** (`backend/packages/parkos_core/schemas/`)

- One schema module per domain group: `auth.py`, `empresa.py`,
  `catalogos.py`, `clientes.py`, `operacion.py`, `caja.py`,
  `workflows.py`, `dian.py` (cloud-only), `sync_infra.py` (local-only)
- Per table: `Read` (response), `Create` (POST body when applicable),
  `Update` (PUT body — only where `[V]` or `[L-S]` allows a state change),
  `Filter` (list query params — version range, tenant scope, pagination cursor)
- `model_config = ConfigDict(from_attributes=True)` and Pydantic field names
  equal to ORM column names so `model_validate(row)` is the only mapping
- Strict UUIDv4 / DIAN number formats rejected by Pydantic regex at the edge

**Shared helpers** (`backend/packages/parkos_core/repo/`)

- `versioned.py` — `close_and_insert()` for `[V]` (UPDATE only on
  `vigente_hasta` + INSERT in the same TX + enqueue `log_transaccional`),
  `current_version()`, `history()`
- `event.py` — `record_event()` for `[L-E]` (pure INSERT; refuses DELETE/UPDATE)
- `workflow.py` — `append_transition()` for `[L-W]` (validates state-machine
  legality against the chain's last row, inserts new row with
  `uuid_*_padre` FK, no UPDATE)
- `session_cycle.py` — `open_session()`, `close_session_with_log()` for `[L-S]`
  (inserts the MANDATORY `log_transaccional` row BEFORE the UPDATE, per the DB
  trigger's contract)
- `append_only.py` — `append_event()` for `[A]` (pure INSERT; refunds via
  compensating rows; `sync_queue` exposes `mark_dispatched` / `mark_failed` /
  `schedule_retry` confined to the four whitelisted columns)
- `hash_chain.py` — server-side `hash_actual = sha256(payload_canonical +
  hash_anterior)` per `uuid_sucursal`; never accepts client-supplied chain
  values; cloud preserves branch chain verbatim
- `tenancy.py` — tenant scope guard (`X-Sucursal-Context` enforcement for
  `admin-*`, `uuid_sucursal` FK for `operador-*`, `sync-agent-*` only on
  sync endpoints)
- `sync_outbox.py` — public no-op facade that confirms the DB
  `AFTER INSERT` trigger is doing the enqueue (not the API); tested in CI

**FastAPI routers** (`backend/packages/api_admin/api/v1/` and `api_sucursal/api/v1/`)

- One router per domain group; mounted under `/api/v1` with the JWT scope
  guard described in exploration §"JWT scope per endpoint class" (see
  `exploration.md` lines 235-246)
- Endpoints are **Consulta + Inserción + Actualización**. NO `DELETE` route
  exists at any URL — recorded in the OpenAPI schema's `delete` operation
  count = 0 enforced by static test
- Each router imports ORM helpers, NOT the raw `session.execute()` SQL; a
  `ruff` + custom AST test rejects direct UPDATE/DELETE against
  `[V]/[L-E]/[L-W]/[A]` classes
- `DIAN-only` routers (`factura_electronica`, `revocacion_factura`,
  `envio_dian`, `validacion_evento`) live in `parkos_core/dian/cloud_router.py`
  with an `import dian.cloud_router` boundary that raises
  `ImportError` on the branch image — RED test in PR7

**Alembic migration test harness** (`backend/tests/migrations/`)

- One pytest fixture per `[A]` table: insert a row, attempt UPDATE, expect
  `RAISE EXCEPTION '<TABLE>_INMUTABLE'` (12 fixtures)
- One pytest fixture per `[L-S]` table: open a session, close without log row
  in TX, expect `RAISE EXCEPTION 'LOG_TRANSACCIONAL_REQUIRED'` (2 fixtures)
- Smoke for `pg_partman` partitions: 8 parents configured, `partman.run_maintenance()`
  creates a future partition without error
- Smoke for hash-chain genesis: per `uuid_sucursal`, the helper inserts the
  first row with `hash_anterior = sha256(b'genesis:uuid_sucursal')`
- Smoke for the 11 REVOKE statements from `rol_app` (`sync_queue` excluded)
- Idempotency: `alembic upgrade head` twice = no change

**OpenAPI contract** (`backend/packages/api_admin/openapi.json`,
`api_sucursal/openapi.json`)

- Generated from the FastAPI app at build time; emitted as committed artifact
  (not generated in CI runtime) so the frontend can pin a version
- 3.1 (FastAPI supports it via JSON Schema 2020-12); `info.version` is the
  git SHA of the change that shipped the contract, for traceability
- Tagged by audience (`admin`, `operador`, `sync`) so each PWA only loads
  the tags it consumes

## Pre-existing Doc Drift Reconciliation

The canonical model is `modelo_datos_er.mmd` (49 tables: 26 `[V]`,
3 `[L-E]`, 6 `[L-W]`, 2 `[L-S]`, 12 `[A]`). Seven documents still report
45 / 24 / 4 / 12 from an earlier scan and must be reconciled BEFORE
bootstrap PR2 lands — otherwise bootstrap ships a 45-table schema and
`create-49-table-apis` cannot expose 4 tables through the API alone
(`resolucion_facturacion`, `envio_dian`, `validacion_evento`, `tipo_arqueo`
each require DB-level FKs, REVOKE statements, trigger function names, and
pg_partman partition calls).

### Drift inventory

| # | File | Lines | Stale claim |
|---|---|---|---|
| 1 | `openspec/PROJECT_CONTEXT.md` | 55, 110 (and contextual references on 64-67) | "45 tables" header |
| 2 | `openspec/_meta/roadmap.md` | 29, 80, 81, 82, 84 (Model Coverage Map) | "24 [V]", "4 [L-W]"; F1 PR description says "45 tables" |
| 3 | `openspec/_meta/iteration-plan.md` | 21, 44 (and F1 references) | F1.6 calls for "45 tables + 11 REVOKE + 11 triggers" |
| 4 | `openspec/changes/bootstrap-monorepo-foundation/exploration.md` | 5, 11, 110, 163, 165, 342, 363 | "24 [V]", "4 [L-W]", counts in dir tree |
| 5 | `openspec/changes/bootstrap-monorepo-foundation/proposal.md` | 5, 9, 19, 52 | "45 AUDIT-FIRST tables", "24 [V] / 9 [L] / 12 [A]" |
| 6 | `openspec/changes/bootstrap-monorepo-foundation/design.md` | (search hits line 165 area, layout tree) | tree shows "24 [V]" and "4 [L-W]"; success criterion |
| 7 | `openspec/changes/bootstrap-monorepo-foundation/tasks.md` | 29, 53 (and F1.6 description) | F1 acceptance "45 tables in `prod`" |
| 8 | `openspec/changes/cloud-edge-sync-architecture/exploration.md` | 11 | "canonical 45-table" — earlier baseline, also stale |

### Reconciliation strategy

Two coordinated PRs, one in each change:

**PR0 — Doc reconciliation PR (THIS change, docs-only)**

- **Branch**: `docs/create-49-table-apis-pr0-doc-reconcile` from `dev`
- **Target**: `dev` (gitflow)
- **Files patched** (all under `E:\easypunto_parkos\`):
  - `openspec/PROJECT_CONTEXT.md` — line 55 → "49 tables"; lines 60-67 →
    26/3/6/2/12 counts; line 110 risk note updated
  - `openspec/_meta/roadmap.md` — line 29 description updated to 49 tables;
    Model Coverage Map (lines 78-84) rebuilt with new counts
  - `openspec/_meta/iteration-plan.md` — line 21 phrase updated; F1.6
    description (line 44) updated to 49 tables
  - `openspec/config.yaml` — line 14 `context` rewritten to 49 / 26 / 3 / 6
    / 2 / 12 counts; `rules.proposal` line 20 references "49-table model"
- **Excluded from PR0**: bootstrap change artifacts (#4-#7) belong to a
  different active change with its own branching model per user direction.
  The patch for those is delivered as PR0b (next entry).
- **Acceptance**: a CI static check `openspec/scripts/check_table_counts.py`
  scans the four docs above, fails if any other count appears, and
  prints the canonical counts for reviewer verification
- **Estimated LOC**: ~40 lines (4 files, surgical edits). Trivial PR.
- **DEPENDENCY GATE**: PR0 MUST land and merge to `dev` BEFORE
  bootstrap PR2 lands; otherwise bootstrap ships against stale docs

**PR0b — Bootstrap artifact patch (FOLLOW-UP hotfix on bootstrap's branch)**

- **Branch**: out of scope for THIS change's PR chain; filed by the user or
  bootstrap maintainer
- **Target**: `bootstrap-monorepo-foundation`'s parent branch (per its
  existing model: F1 PR's branch, also `dev` under gitflow)
- **Files patched**:
  - `openspec/changes/bootstrap-monorepo-foundation/{exploration,proposal,design,tasks}.md`
    — replace "45 tables" and "24 / 9 / 12" with "49 tables" and "26 / 9 / 12"
- **Estimated LOC**: ~25 lines across 4 files. Trivial PR.
- **Note**: This proposal SPECIFIES the patch contents; the user can apply
  them in one commit or split into bootstrap PR2.5 if F2 has already landed

**Pre-flight before bootstrap PR2 merges** (executed locally before
bootstrap PR2 review approval):

- `psql -c "\dt prod.*"` against the migrated DB → expected row count = 49
- `psql -c "SELECT count(*) FROM pg_trigger WHERE tgname LIKE '%_inmutable'"`
  → expected ≥ 11 `[A]` triggers (12 minus `sync_queue`)
- `psql -c "SELECT count(*) FROM pg_trigger WHERE tgname LIKE 'ls_session%'"`
  → expected 2 `[L-S]` session guards
- If any count is short, bootstrap PR2 is BLOCKED until the missing 4 tables
  (`resolucion_facturacion`, `tipo_arqueo`, `envio_dian`, `validacion_evento`)
  are added in a follow-up Alembic revision on top of `0001_initial_schema.py`

This pre-flight is the single most important item in this proposal — it
prevents the 45→49 drift from poisoning the database while the docs lie.

## Scope

### In scope

- ORM models for all 49 tables with audit / versioning / sync columns
- Pydantic v2 schemas (`Read`, `Create`, `Update`, `Filter`) per table
- FastAPI routers under `/api/v1`: Consulta + Inserción + Actualización
  bi-temporal — **NO `DELETE` endpoint at any layer**; static test enforces
- 5 helper families (versioned, workflow, session_cycle, append_only, event)
  + 3 cross-cutting helpers (tenancy, hash_chain, sync_outbox facade)
- JWT scope enforcement per router (admin-, operador-, sync-agent-only)
- Tenant scoping via `X-Sucursal-Context` against `sucursales_permitidas`
- OpenAPI 3.1 contract per service (admin, branch), committed artifact
- Alembic migration test harness (12 `[A]` immutability, 2 `[L-S]`
  log-with-UPDATE, 8 `pg_partman` parents, hash-chain genesis, 11 REVOKE,
  `alembic upgrade head` idempotency)
- DIAN-only boundary: `parkos_core/dian/cloud_router.py` raises
  `ImportError` on branch image — RED test in PR7
- Doc drift reconciliation: PR0 (4 docs in this change) + PR0b (4
  bootstrap artifacts) — exactly the patches listed in
  [Pre-existing Doc Drift Reconciliation](#pre-existing-doc-drift-reconciliation)
- Pre-flight check script before bootstrap PR2 merges (`check_table_counts.py`
  + schema-count probe)
- Gitflow: feature branches off `dev`, PRs merge to `dev` only; release
  branches to `main` after certification
- Establish `dev` from `master` (current branch) before PR1 lands — see
  Risks below

### Out of scope (deferred to later changes)

- DIAN external provider integration (`dian_dispatcher` HTTP client and
  Factus / provider adapter). The DIAN-only routers expose the 4 cloud-only
  endpoints; the wire-level call to DIAN is owned elsewhere
- Web frontend (`web_admin`, `web_sucursal`). PWAs consume the OpenAPI
  contract artifact only — UI work is in separate change streams
- Sync engine implementation (`job_sync_cloud`, `job_sync_sucursal`). The
  sync router endpoints exist (`/sync/pair`, `/sync/push`, `/sync/pull`)
  and the ORM is sync-aware (carries `sync_status` / `sync_timestamp`), but
  the transport and ordering logic are out of scope here
- Operational tooling (rate limiting, metrics, OpenTelemetry tracing,
  Prometheus exporters, health-check expansion beyond `/health`,
  circuit-breaker policies). Separate change
- RBAC permission matrix (per-endpoint fine-grained `permisos_usuario`
  lookups). Propose the FRAMEWORK (FastAPI dependency that resolves
  `permisos_usuario` and returns 403), defer the matrix population
- OpenAPI client SDK generation (TypeScript via `openapi-typescript-codegen`
  or `orval`). Propose the STRATEGY (committed JSON, frontend pinned),
  defer the generator wiring
- Bulk-CSV import endpoints for catalog seeding. Separate change
- `multipart/form-data` for `documentos.documento_b64` (open question #9
  from exploration). Base64 inline is enough for MVP
- WebSocket sync transport (deferred to v2 — polling only for now)

## Architectural decisions to ratify

The exploration surfaced 15 open questions. Four (chosen for highest impact
on the audit-first contract) are resolved here; the remaining 11 are
explicitly deferred to the spec or design phase where they are local to a
single helper or router.

### AD-1: List-endpoint coverage — ALL 49 tables get a list endpoint

**Recommendation**: Yes. Every table exposes `GET /api/v1/<resource>`
(list, paginated, current-version-only by default).

**Alternatives considered**:

- (a) List endpoints only for tables with operational UI → smaller surface
  area; rejected because it forces ad-hoc additions during each iteration
  and bypasses the "API as the typed source of truth" principle
- (b) List endpoints exposed under `GET /api/v1/catalogos/*` (catalog
  namespace) and `GET /api/v1/<table>` for the rest → split UX; rejected
  for both cognitive cost and because it conflates "catalog" with
  "[V]-no-branch-writes", which is not always true

**Rationale**: The audit-first promise is "every fact is queryable, every
mutation is logged". A list endpoint is the queryability half. The cost is
~50 lines per table (router + Filter schema + cursor pagination), spread
across 8 PRs — well under the 800-LOC budget per PR. The contract surface
being uniform simplifies the PWA client (one fetch pattern, one cursor
iterator) and the future sync worker (it needs to enumerate `[V]` rows
replicated to a branch).

### AD-2: RBAC layering — BOTH API and DB (defense in depth)

**Recommendation**: Enforce permissions at BOTH the FastAPI dependency
layer (early reject, 403 with structured error) and the DB REVOKE / trigger
layer (last line of defense). The RBAC matrix itself is `[V] permisos` +
`[V] permisos_usuario`, populated by admin tooling later — this change
ships only the FRAMEWORK (a `require_permission("...")` FastAPI dependency
that resolves the JWT subject → `permisos_usuario` join → boolean), not
the matrix.

**Alternatives considered**:

- (a) DB REVOKE only (rely on REVOKE to deny everything not explicitly
  granted at the DB; no FastAPI dependency) → rejected because it hides
  the authorization rule from the API contract and forces every error to
  be a 500 instead of a 403
- (b) API dependency only → rejected because it leaves the DB accessible to
  any session that bypasses the API (sync workers, `psql`, future
  microservices). The whole audit-first rationale for `[A]` REVOKE
  evaporates

**Rationale**: AGENTS.md is explicit that defense in depth is non-negotiable
(see [Architectural Principles §1](../../AGENTS.md#1-audit-first--compliance-driven-data-architecture))
— "REVOKE UPDATE, DELETE on 11 `[A]` tables from `rol_app`;
`rol_admin_auditor` is the only role with `BYPASSRLS`". That stance only
makes sense if the API boundary ALSO enforces. The double-check is
redundant in the happy path and catches security regressions in either
layer. The framework cost is one FastAPI dependency class (≈ 30 LOC)
plus an `auth/permissions.py` module that joins `permisos_usuario` (≈ 60
LOC) — negligible.

### AD-3: Idempotency keys — REQUIRED for ALL write endpoints

**Recommendation**: `Idempotency-Key` HTTP header on all POST endpoints,
stored in a 50th table `[A] idempotency_keys` (24h TTL, same REVOKE +
trigger pattern as the other 12 `[A]` tables). Re-submission of the same
key within the window returns the original response. Branch image
opportunistically flushes entries > 24h via a nightly worker.

**Alternatives considered**:

- (a) No idempotency at the HTTP layer — rely on UUID v4 PKs being
  globally unique → simpler, but DOES NOT help against retries from the
  PWA after `preliminar` → `oficial` flow (same POST fired twice with
  different UUIDs would create two `facturas` rows); rejected
- (b) Idempotency only for DIAN writes (`factura_*`) → narrower blast
  radius; rejected because login (POST `/auth/login`) ALSO benefits
  (network blip on first login attempt, PWA retries), and the cost of the
  helper is amortized across all writes

**Rationale**: The branch is offline-first. The PWA caches POSTs in a
service-worker queue, retries them on reconnect, and may double-submit on
a flaky network. Idempotency keys are the standard defense (RFC 7234
draft, Stripe, Square). A 50th `[A]` table is one more Alembic
migration — small marginal cost. The 24h TTL matches Stripe's default
and is long enough to absorb every realistic retry window.

### AD-4: Derived state endpoints — nested under the parent resource

**Recommendation**: Expose derived views (`V_FACTURA_ESTADO`,
`V_INGRESO_ESTADO`, `V_FE_ESTADO_DIAN`, `V_RESOLUCION_CONSECUTIVO`,
`V_ARQUEO_DIFERENCIAS`, `V_FACTURA_PAGOS_NETOS`) as nested sub-resources
of the parent. Example: `GET /api/v1/facturas/{uuid}/estado`,
`GET /api/v1/ingresos/{uuid}/estado`,
`GET /api/v1/factura-electronica/{uuid}/estado-dian`,
`GET /api/v1/resoluciones/{uuid}/consecutivo`,
`GET /api/v1/arqueos/{uuid}/diferencias`.

**Alternatives considered**:

- (a) Flat `/derived/{view_name}` → simpler routing layer, but the URL
  loses the parent context and the PWA has to maintain a parallel
  naming convention. Rejected.
- (b) No derived endpoint at all — PWA computes from fact tables →
  leaks domain semantics into the frontend, breaks the "API is the typed
  contract" principle. Rejected.

**Rationale**: The canonical model deliberately stores state as DERIVED
(see the ER comments on `ingreso`/`facturas`/`factura_electronica` —
4NF-compliance means `estado` and `consecutivo` live in views, not
columns). The PWA shouldn't re-implement those derivations; it should
GET them. Nesting under the parent makes the data dependency obvious in
the URL and lets FastAPI's `response_model` document both the table
schema and the derived schema side-by-side.

### BONUS: Gitflow model — ratified, applies to this change

Per AGENTS.md and the user's direction in this session:

- Branch from `dev`. Feature branches use `feat/create-49-table-apis-prN-*`
  (matching `branch-pr` skill convention)
- PRs merge INTO `dev` (never `main` directly)
- Release branches (`release/vX.Y.Z`) cut from `dev` only after the full
  PR chain is merged and verified, then merge into `main` after
  certification
- The repo currently sits on `master` with no `dev`; PR1 includes the
  one-time `dev` branch creation (see Risks)

## PR slicing (8 chained PRs to `dev` via gitflow)

All eight PRs live behind the gate: bootstrap is merged to `dev` first. Each
PR targets `dev` and uses gitflow branch naming. Every PR is independently
revertible. The first PR that lands (PR0) is docs-only and the gate for the
pre-flight check on bootstrap PR2.

### PR0 — Doc drift reconciliation

| Field | Value |
|---|---|
| **Branch** | `docs/create-49-table-apis-pr0-doc-reconcile` |
| **Target** | `dev` |
| **Depends on** | none |
| **Tables touched** | none — docs only |
| **Files modified** | `openspec/PROJECT_CONTEXT.md`, `openspec/_meta/roadmap.md`, `openspec/_meta/iteration-plan.md`, `openspec/config.yaml`, plus `openspec/scripts/check_table_counts.py` (new) |
| **Estimated LOC** | ~40 |
| **Acceptance** | `python openspec/scripts/check_table_counts.py` exits 0; CI runs it on every PR to keep counts from drifting again; PR0b PR exists or has been filed separately by the maintainer for the bootstrap artifacts |
| **Rollback** | revert the single commit; no data impact |

### PR1 — ORM foundation + auth + JWT three-issuer wiring

| Field | Value |
|---|---|
| **Branch** | `feat/create-49-table-apis-pr1-orm-auth` |
| **Target** | `dev` |
| **Depends on** | bootstrap fully merged to `dev` (PR0's docs land before bootstrap PR2 is approved) |
| **Tables touched** | `usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal` (4 `[V]`), `login` (1 `[L-S]`) |
| **New files** | `parkos_core/models/{V,L_S}/<table>.py` × 5; `parkos_core/schemas/auth.py`; `parkos_core/repo/{versioned,session_cycle,append_only,event,workflow}.py` (stubs); `parkos_core/auth/{jwt_issuer_guard,permissions.py}`; `backend/tests/migrations/test_a_inmutable.py` (12 fixtures), `test_ls_session_guard.py` (2 fixtures); `openspec/scripts/preflight_table_counts.sh` |
| **Estimated LOC** | ~700 |
| **Acceptance** | (a) `alembic upgrade head` against fresh DB returns 49 tables in `prod.*`; (b) `INSERT INTO prod.factura_pagos ... ; UPDATE ... SET valor=0` raises `FACTURA_PAGOS_INMUTABLE` (and same for the other 11 `[A]`); (c) `UPDATE prod.sesion SET estado='cerrada' WHERE uuid=:u` without prior `log_transaccional` insert raises `LOG_TRANSACCIONAL_REQUIRED`; (d) `usuarios` CRUD works through the helpers (insert, close+insert, history); (e) JWT three-issuer guard rejects cross-audience tokens with 401; (f) `preflight_table_counts.sh` passes |
| **Rollback** | revert the PR; helpers and ORM models can be removed; the 12 `[A]` trigger tests stay (they document the contract) |

### PR2 — `[A]` infrastructure + sync_queue + audit triggers + hash-chain genesis helper

| Field | Value |
|---|---|
| **Branch** | `feat/create-49-table-apis-pr2-a-infra` |
| **Target** | `dev` |
| **Depends on** | PR1 |
| **Tables touched** | `sync_queue`, `sync_log`, `sync_conflict`, `log_transaccional`, `caja`, `arqueo`, `revocacion_factura` (7 `[A]` — leaves the 4 DIAN-row ones for PR6) |
| **New files** | `parkos_core/models/A/{sync_queue,sync_log,sync_conflict,log_transaccional,caja,arqueo,revocacion_factura}.py`; `parkos_core/repo/append_only.py` (full); `parkos_core/repo/hash_chain.py` (covers `log_transaccional`); `parkos_core/schemas/sync_infra.py` |
| **Estimated LOC** | ~700 |
| **Acceptance** | (a) `sync_queue` PUT for `mark_dispatched / mark_failed / schedule_retry` updates only the 4 whitelisted columns (CI test fuzzes other columns); (b) `log_transaccional` insert computes `hash_actual` from prior row's `hash_actual` per `uuid_sucursal`; (c) `revocacion_factura` insert computes same chain, cloud-only on cloud image; (d) sync outbox trigger fires on every `[A]` insert EXCEPT `sync_queue` (test asserts `WHEN (TG_TABLE_NAME <> 'sync_queue')`); (e) CI test: `INSERT INTO prod.sync_queue` does NOT create another `sync_queue` row (no recursion) |
| **Rollback** | revert; `log_transaccional` and `revocacion_factura` chain init is the only cross-PR state |

### PR3 — Catalog domain (8 `[V]` catalogs + 1 partial admin config)

| Field | Value |
|---|---|
| **Branch** | `feat/create-49-table-apis-pr3-catalogs` |
| **Target** | `dev` |
| **Depends on** | PR1 |
| **Tables touched** | `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios` (9 — one more than the exploration's PR3 because `tipo_arqueo` is added per the 49-table count) |
| **New files** | `parkos_core/models/V/<table>.py` × 9; `parkos_core/schemas/catalogos.py`; `parkos_core/api/v1/catalogos.py` |
| **Estimated LOC** | ~600 |
| **Acceptance** | (a) `tipo_arqueo` is in the API surface even though it doesn't appear in `_meta/roadmap.md` (drift reconciled); (b) cloud-admin POST on each catalog creates a new version with the catalog versionable UK + `vigente_desde`; (c) PUT closes + inserts (verified via history endpoint); (d) branch operator GET works for replicated catalogs; (e) tests cover happy path + bi-temporal close+insert + pagination cursor |
| **Rollback** | revert; no data state survives (catalogs have no business references yet) |

### PR4 — Empresa + Sucursal + per-branch config

| Field | Value |
|---|---|
| **Branch** | `feat/create-49-table-apis-pr4-empresa-sucursal` |
| **Target** | `dev` |
| **Depends on** | PR1 + PR3 (`sucursal` FKs `tipo_sucursal`, `empresa`) |
| **Tables touched** | `empresa`, `sucursal`, `documentos`, `resolucion_facturacion`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `configuracion_tolerancias`, `configuracion_seguridad` (8 `[V]`) |
| **New files** | `parkos_core/models/V/<table>.py` × 8; `parkos_core/schemas/empresa.py`; `parkos_core/api/v1/{empresa,sucursal,configuracion}.py` |
| **Estimated LOC** | ~750 |
| **Acceptance** | (a) `resolucion_facturacion` POST/GET works (this table was MISSING from bootstrap docs); (b) `documentos` carries base64 with a 1MB cap (Pydantic `String(max_length=1_400_000)`); (c) per-branch config override pattern: GET for `uuid_sucursal` falls back to global if no override; (d) branch image CRUD denied on `resolucion_facturacion` (cloud-only via `X-Sucursal-Context = cloud`) |
| **Rollback** | revert |

### PR5 — Commercial domain + `[L-E] ingreso` (entry event)

| Field | Value |
|---|---|
| **Branch** | `feat/create-49-table-apis-pr5-commercial-ingreso` |
| **Target** | `dev` |
| **Depends on** | PR3 + PR4 (FKs: `clientes.uuid_tipo_persona`, `vehiculos.uuid_tipo_vehiculo`, `ingreso.uuid_subscripcion_cliente`) |
| **Tables touched** | `[V]`: `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`. `[L-E]`: `ingreso` |
| **New files** | `parkos_core/models/{V,L_E}/<table>.py` × 6; `parkos_core/schemas/clientes.py`, `parkos_core/schemas/operacion.py`; `parkos_core/repo/event.py` (full); `parkos_core/api/v1/{clientes,operacion}.py` |
| **Estimated LOC** | ~800 (at budget — watch the PR line counter) |
| **Acceptance** | (a) ingreso insert is partition-key-aware (date filter); (b) `V_INGRESO_ESTADO` exposed at `GET /api/v1/ingresos/{uuid}/estado`; (c) `subscripcion_vehiculos` UK check via Pydantic validator (count vs `cantidad_maxima_vehiculos`); (d) `reclamos.tipo_reclamable` polymorphic write validator rejects unknown `tabla` values (test asserts 422) |
| **Rollback** | revert |

If PR5 exceeds 800 LOC at apply-time, split into PR5a (`[V]` commercial, 5
tables, ~500 LOC) + PR5b (`[L-E]` ingreso, 1 table, ~300 LOC).

### PR6 — Operations + `[L-W]` workflows + `[A]` billing

| Field | Value |
|---|---|
| **Branch** | `feat/create-49-table-apis-pr6-operations-workflows` |
| **Target** | `dev` |
| **Depends on** | PR5 (`facturas` FKs `ingreso` / `salidas`) |
| **Tables touched** | `[L-E]`: `salidas` (`[A]`, sorry — reclassify as `[A]`). `[L-E]`: `facturas`, `factura_electronica`. `[L-W]`: `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `envio_dian`, `validacion_evento`. `[A]`: `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`. Total = 12 tables |
| **New files** | `parkos_core/models/{L_E,L_W,A}/<table>.py` × 12; `parkos_core/schemas/{facturacion,workflows,sync_infra}.py`; `parkos_core/repo/{workflow,event,append_only}.py` (full); `parkos_core/api/v1/{facturacion,workflows}.py` |
| **Estimated LOC** | ~800 (heaviest PR — split trigger at 750 applied-LOC) |
| **Acceptance** | (a) `anulaciones` workflow chain 3-row minimum (solicitada → aprobada → ejecutada); (b) `reclamos` polymorphic FK validated; (c) `factura_pagos.tipo_movimiento='reverso'` validates 1:1 reversal (partial unique index tested via ORM); (d) `V_FACTURA_ESTADO`, `V_FE_ESTADO_DIAN` derived endpoints live; (e) `envio_dian`, `validacion_evento` import boundary enforced (`from parkos_core.dian.cloud_router` raises `ImportError` on branch image — RED test in CI) |
| **Rollback** | revert |

If PR6 exceeds 800 LOC at apply-time, split into PR6a (`[L-E] facturas +
[A] factura_detalle/impuestos/otros_cobros/pagos`, 5 tables, ~600 LOC)
+ PR6b (`[L-W]` workflows, 6 tables, ~500 LOC).

### PR7 — Caja + `[L-S]` sesion + sync infra

| Field | Value |
|---|---|
| **Branch** | `feat/create-49-table-apis-pr7-caja-sesion` |
| **Target** | `dev` |
| **Depends on** | PR6 (`sesion` FKs `factura_pagos`; `arqueo` FKs `sesion`; `alerta` FKs `arqueo`) |
| **Tables touched** | `[L-S]`: `sesion`. `[A]`: `caja`, `arqueo`. **Adds idempotency_keys** (50th `[A]` table) for AD-3. Total = 4 tables |
| **New files** | `parkos_core/models/{L_S,A}/<table>.py` × 3; `parkos_core/models/A/idempotency_keys.py` (new); `parkos_core/schemas/caja.py`; `parkos_core/repo/session_cycle.py` (full — incl. log-before-update); `parkos_core/api/v1/caja.py`; `infra/migrations/0002_add_idempotency_keys.py` |
| **Estimated LOC** | ~600 |
| **Acceptance** | (a) `sesion` close always inserts a `log_transaccional` row BEFORE the UPDATE (verified by migration test firing UPDATE without prior log → `LOG_TRANSACCIONAL_REQUIRED`); (b) `V_ARQUEO_DIFERENCIAS` derived endpoint live; (c) `idempotency_keys` table created with REVOKE + trigger; (d) POST endpoints without `Idempotency-Key` header return 400 |
| **Rollback** | revert; `idempotency_keys` table drop is reversible |

### Dependency graph

```
       bootstrap → dev
            │
            ▼
         PR0 ──────► (also: pre-flight on bootstrap PR2 gate)
            │
            ▼
   PR1 (ORM + auth)  ────►  PR3 (catalogs)         ───►  PR5 (commercial + ingreso)
            │                                                │
            ├──►  PR2 ([A] infra)  ──────────────────────────┤
            │                                                │
            └──►  PR4 (empresa + sucursal + config)  ─────────┤
                                                             │
                                                             ▼
                                              PR6 (operations + workflows + billing)
                                                             │
                                                             ▼
                                                     PR7 (caja + sesion + idempotency)
```

Total LOC across PR1–PR7: ~5,000 (avg ~720 / PR). All under the 800 budget
with two conditional splits (PR5, PR6) ready if budgets blow at apply time.

## Risks

Carry-forward from exploration, plus three new ones. Severity unchanged
except where noted. Mitigation is explicit per row.

| Severity | Risk | Mitigation |
|---|---|---|
| **HIGH** | **Doc drift poisons bootstrap PR2** — `0001_initial_schema.py` ships with 45 tables, API surface missing for `tipo_arqueo`, `resolucion_facturacion`, `envio_dian`, `validacion_evento` | PR0 lands BEFORE bootstrap PR2; PR0b (bootstrap maintainer-owned) lands before bootstrap PR2 reviews; pre-flight `preflight_table_counts.sh` aborts if `\dt prod.*` returns fewer than 49 or if trigger counts are short |
| **HIGH** | **DIAN-only boundary breach** — branch image accidentally imports `dian.cloud_router` and writes to `factura_electronica` | RED test in PR6 (`from parkos_core.dian.cloud_router import router` on branch image raises `ImportError`); CI runs the import in both build contexts (`cloud`, `branch`); OpenAPI contract check verifies DIAN-only routes absent from `api_sucursal/openapi.json` |
| **HIGH** | **Hash-chain break on partial sync** — out-of-order `log_transaccional` rows from a branch break chain on cloud | `hash_chain.append()` reads prior `MAX(timestamp_evento)` row per `uuid_sucursal`; rejects if `hash_anterior` doesn't match (raises `HASH_CHAIN_INTEGRITY_VIOLATION`); the bootstrap sync worker orders rows by per-branch monotonic seq stamped in `datos` JSON; cloud verifier tests in PR7 catch breaks the same way; an `alerta tipo_alerta='sync_failure'` row is the fallback |
| **HIGH** | **`[A]` REVOKE + trigger not enforced** — API accidentally writes UPDATE/DELETE via raw `session.execute()` bypassing the helper | Ruff rule + AST test (`test_no_raw_dml_on_a_tables.py`) scans `parkos_core/api/` and `parkos_core/workers/` for `session.execute(update(...)` against `[A]` class names and fails CI; the 12 immutability tests in PR1 are the unit-level defense |
| **HIGH** | **`[L-S]` UPDATE-without-log passes** — trigger misconfigured, session-close UPDATE slips through without audit row | Migration test `test_ls_session_guard.py` in PR1 fires UPDATE without prior log → expects exception; PR7's `close_session_with_log()` inserts log FIRST, then UPDATE in same TX; CI verifies by trace inspection |
| **MED** | **PR6 at the budget edge (12 tables, ~800 LOC)** — risk of being split at apply time and stalling the chain | Mitigation: PR6 is pre-scoped to split into PR6a + PR6b if `git diff --stat` post-implementation shows >800 LOC; the design-phase task list spells out the split point so apply does not lose context |
| **MED** | **`sync_queue` recursion** — INSERT into `sync_queue` re-triggers the outbox trigger | Bootstrap migration's `AFTER INSERT` trigger filters `WHEN (TG_TABLE_NAME <> 'sync_queue')`; PR2 test asserts `INSERT INTO prod.sync_queue` does NOT create another row; AST test rejects `append_event(session, sync_queue, ...)` calls |
| **MED** | **pg_partman partition pruning** — `[A]` queries on `salidas`/`factura_pagos`/`log_transaccional`/etc. miss the partition key and full-scan | ORM helpers accept `partition_key_from` / `partition_key_to` as required kwargs; lint warning fires when missing; a focused ORM unit test verifies EXPLAIN plan contains the partition |
| **MED** | **Gitflow not initialized** — current branch is `master`, no `dev` | PR1 establishes `dev` from `master` (one-time); subsequent PRs target `dev`; release branches to `main` per AGENTS.md |
| **MED** | **`[L-W]` chain tie-break for retries** — workflows like `envio_dian` and `reclamos` have multiple chains from re-opening | Helper `read_current_*()` orders chains by `(max(timestamp_evento), count_of_rows)` and returns last row; spec phase documents the algorithm; tests pin determinism |
| **MED** | **Bootstrap artifacts still say 45 tables after PR0 lands** — drift persists in the bootstrap change | PR0b listed as out-of-scope deliverable but specs the exact patches; user/maintainer owns the PR0b merge; this proposal cannot force bootstrap to accept the patch but makes the patch trivial (~25 lines) |
| **LOW** | **OpenAPI doc bloat** — ~245 paths, ~2 MB JSON | Per-audience split via `openapi_tags`; each PWA only consumes its tag set; artifact compressed in CI |
| **LOW** | **Pydantic v2 ↔ ORM field drift** — renaming during refactors breaks `from_attributes=True` mapping | CI test loads each Pydantic schema, validates a row-instance via `model_validate(row)`, catches missing fields; same test runs against generated OpenAPI |
| **NEW — HIGH** | **`revocacion_factura` not in cloud-only router list at PR6** — accidentally mounted on branch | The router file `parkos_core/dian/cloud_router.py` is the SINGLE mount point for these 4 tables; CI test asserts only this file contains their imports; the RED import-boundary test covers all four |
| **NEW — MED** | **`tipo_arqueo` FK `arqueo` requires cloud migration in PR3's window** — circular PR risk if bootstrap hasn't shipped `tipo_arqueo` | The pre-flight check covers this; if `tipo_arqueo` is missing from `\dt prod.*`, PR3 cannot proceed |
| **NEW — MED** | **Idempotency table `idempotency_keys` is the 50th table** — out of scope for bootstrap | PR7 includes a new Alembic migration `0002_add_idempotency_keys.py`; if bootstrap is still active, this migration depends on its PR-chain landing first |

## Acceptance criteria

The change is "done" when:

1. All 49 tables have ORM models, Pydantic v2 schemas (Read/Create/Update/Filter), FastAPI routers, and Alembic migration test fixtures
2. Three-layer audit-first enforcement is verified by automated test:
   - **API**: zero `DELETE` routes in any OpenAPI artifact (CI grep)
   - **ORM**: `parkos_core/repo/{versioned,event,workflow,append_only,session_cycle}.py` are the ONLY writers; AST test rejects raw `session.execute(update/delete)` against `[V]/[L-E]/[L-W]/[A]` classes outside these helpers
   - **DB**: 11 REVOKE statements active on `[A]` tables (excluding `sync_queue`); 11 `BEFORE UPDATE OR DELETE` triggers RAISE EXCEPTION; 2 `[L-S]` UPDATE guards require `log_transaccional` in TX; 8 `pg_partman` partitions configured; `log_transaccional` and `revocacion_factura` hash chain genesis verified
3. All 8 chained PRs land on `dev` (PR0 docs + PR1–PR7 code), each independently revertible, each < 800 LOC (PR5 and PR6 may split if budgets blow)
4. OpenAPI 3.1 contracts emitted as committed artifacts for both `api_admin` and `api_sucursal`; PWA clients pin a specific git-SHA version
5. Alembic migration test harness covers: 12 `[A]` immutability fixtures, 2 `[L-S]` log-with-UPDATE guards, 8 `pg_partman` partition parents, `hash_chain.append()` genesis, 11 REVOKE statements, idempotent `alembic upgrade head` (twice)
6. Doc drift is reconciled: PR0 merged and PR0b has been filed (or merged) so that every project doc references the canonical 49 / 26 / 3 / 6 / 2 / 12 counts
7. Pre-flight schema check (`preflight_table_counts.sh`) exits 0 against the migrated DB immediately before bootstrap PR2 reviews approval
8. `gitflow` initialization: `master` → `dev` rename done; release branch strategy documented; AGENTS.md cross-checked
9. All existing tests pass (`alembic check`, `ruff check`, `mypy --strict`, `pytest -q`, `preflight_table_counts.sh`)
10. The 50th table `idempotency_keys` exists with REVOKE + trigger and supports the `Idempotency-Key` header on all POSTs

## Non-goals

Explicitly NOT in this change:

- DIAN HTTP transport (Factus / other provider adapter) — separate change
- Sync engine implementation (`job_sync_cloud` / `job_sync_sucursal`
  transport, ordering, conflict resolution policy enforcement) — uses
  the ORM but is out of scope
- Web frontend (`web_admin`, `web_sucursal` PWA) — consumes the OpenAPI
  contract; UI work is separate
- Operational tooling (rate limiting, metrics, tracing, circuit breakers,
  Prometheus exporters)
- RBAC permission matrix population (per-endpoint per-permission rules).
  The framework ships; matrix authoring is a follow-up change
- OpenAPI TS client SDK generator wiring
- Bulk-CSV import endpoints
- `multipart/form-data` for `documentos.documento_b64` (base64 inline is enough)
- WebSocket sync transport (deferred to v2; polling only)

## Next phase

After this proposal is approved: `/sdd-spec create-49-table-apis`

The spec phase will:

1. Lock the four `Architectural decisions` from this proposal as
   GIVEN/WHEN/THEN scenarios in `openspec/changes/create-49-table-apis/specs/`
2. Produce one spec file per PR (8 specs total: `pr0_doc_reconcile.spec.md`
   through `pr7_caja_sesion.spec.md`) keyed to `acceptance criteria`
3. Resolve the 11 deferred exploration questions (pagination shape, OpenAPI
   generator choice, sync endpoint mounting, tenant context header vs
   path vs subdomain, login lockout window, DIAN online timeout,
   `V_RESOLUCION_CONSECUTIVO` materialization, etc.) as local scenarios
4. Verify the `sdd-qa` skill's per-file coverage threshold is satisfiable
   within the 800-LOC budget per PR; split and re-spec if not

## Relevant files

Inputs read for this proposal:

- `E:\easypunto_parkos\modelo_datos_er.mmd` — canonical 49-table ER
- `E:\easypunto_parkos\openspec\changes\create-49-table-apis\exploration.md` — 345 lines, prior phase
- `E:\easypunto_parkos\AGENTS.md` — project canon
- `E:\easypunto_parkos\openspec\config.yaml` — SDD rules
- `E:\easypunto_parkos\openspec\_meta\roadmap.md` — STALE, reconciled in PR0
- `E:\easypunto_parkos\openspec\_meta\iteration-plan.md` — STALE, reconciled in PR0
- `E:\easypunto_parkos\openspec\PROJECT_CONTEXT.md` — STALE, reconciled in PR0
- `E:\easypunto_parkos\openspec\changes\bootstrap-monorepo-foundation\{exploration,proposal,design,tasks}.md` — STALE, patched in PR0b (out-of-scope)
- `E:\easypunto_parkos\openspec\changes\cloud-edge-sync-architecture\exploration.md` — baseline sync decisions
- Engram #1264 — exploration memory snapshot

Files this proposal will modify (none — this proposal is a single
deliverable; PR0 modifies the docs above and the new script; PR1–PR7
introduce backend code):

- `openspec/changes/create-49-table-apis/proposal.md` (this file)
- Engram `sdd/create-49-table-apis/propose` (saved after this turn)
