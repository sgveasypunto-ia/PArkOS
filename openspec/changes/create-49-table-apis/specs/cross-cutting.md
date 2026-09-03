# Spec: Cross-Cutting Concerns

## Capability

Define the cross-cutting invariants that ALL resource specs in this change must honor. These six concerns — **tenant scoping** (REQ-X1, REQ-X2), **DIAN-only cloud boundary** (REQ-X3), **hash chain integrity** (REQ-X4), **audit triggers** (REQ-X5), **sync triggers** (REQ-X6), and **JWT scope per resource class** (REQ-X7, REQ-X8, REQ-X9) — are infrastructural; they are implemented once in `parkos_core/auth/`, `parkos_core/repo/`, `parkos_core/db/` and are referenced by every router and helper. They correspond directly to the three enforcement pillars of the project's canon (API → ORM → DB), with the table-counts and trigger-counts verified by the `preflight_table_counts.sh` script before bootstrap PR2 can be approved.

## Requirements

### REQ-X1-TENANCY-OPERADOR: Branch JWT pins `uuid_sucursal`
**Given** a `POST/GET/PUT/DELETE` (the last of which is impossible by design — see each per-class spec) request to any resource mounted on `api_sucursal`
**When** the request hits the tenant scope guard middleware (`parkos_core/auth/tenancy.py::enforce_operador_scope`)
**Then** the system MUST (a) extract `uuid_sucursal` from the verified `operador-` JWT's `sucursal` claim; (b) rewrite / scope the SQLAlchemy query `WHERE uuid_sucursal = :claim` for every operation touching a column that has `uuid_sucursal`; (c) reject with 403 `{"error": "tenant_scope_violation"}` if the JWT's `sucursal` does not match the row's `uuid_sucursal`; (d) skip scoping for tables without `uuid_sucursal` (catalogs). The `X-Sucursal-Context` header is OPTIONAL on `operador-` requests (defaults to the JWT claim). Static test enforces that no query against an operation-bearing table leaves the operator middleware without scope injection

### REQ-X2-TENANCY-ADMIN: Admin JWT requires `X-Sucursal-Context` header
**Given** an `admin-` JWT containing `sucursales_permitidas: [uuid_A, uuid_B, ...]`
**When** any request under `/api/v1/*` (except `/auth/*` and `/health/*`) arrives with the admin token
**Then** the system MUST (a) require `X-Sucursal-Context: <uuid>` header (Q4 resolution), missing → 400 `missing_sucursal_context`; (b) require `X-Sucursal-Context ∈ sucursales_permitidas`, mismatched → 403 `unauthorized_sucursal_context`; (c) apply the same query-level scoping as operador (REQ-X1). The header is the operational handle — branch pin is implicit via JWT for operador-, explicit via header for admin-. The `'admin-'` global scope (no `X-Sucursal-Context`, used by auditor role only) is rejected by default; a future `rol_admin_auditor` flow uses `BYPASSRLS` SELECT-only bypass separately.

### REQ-X3-DIAN-CLOUD-ONLY: `factura_electronica`, `revocacion_factura`, `envio_dian`, `validacion_evento` are cloud-only
**Given** the four tables in the DIAN-only set per AGENTS.md canon and `modelo_datos_er.mmd` row comments
**When** the FastAPI app boots under either context (cloud or branch)
**Then** `parkos_core/dian/cloud_router.py` MUST be importable only on the cloud image. The branch image's `Dockerfile` does NOT include `parkos_core/dian/cloud_router.py`. A RED import test (`test_cloud_router_branch_boundary.py`) at PR6 acceptance imports the module from the branch context and asserts `ImportError`. The OpenAPI emitted for `api_sucursal/openapi.json` MUST contain zero paths under `/factura-electronica/*`, `/revocacion-factura/*`, `/envio-dian/*`, `/validacion-evento/*`. CI runs `jq` against both `openapi.json` files and fails on any cloud-only path in the branch file

### REQ-X4-HASH-CHAIN: `log_transaccional` and `revocacion_factura` SHA-256 chain per `uuid_sucursal`
**Given** an INSERT into `log_transaccional` (any writing helper does this — `close_and_insert`, `append_event`, `append_transition`, `close_session_with_log`) or `revocacion_factura`
**When** the helper `parkos_core/repo/hash_chain.py::append()` runs
**Then** the system MUST (a) read the prior row via `SELECT uuid, hash_actual FROM <table> WHERE uuid_sucursal = :S ORDER BY timestamp_evento DESC LIMIT 1`; (b) compute `hash_actual = sha256(canonical_json(payload + audit_columns) + hash_anterior_or_genesis)`; (c) for the FIRST row per `uuid_sucursal`, the genesis value is `sha256(b"genesis:" + uuid_sucursal_bytes)` (deterministic); (d) insert with the chain values in the SAME TX as the payload. Client-supplied `hash_anterior`/`hash_actual` are rejected with 422. On chain mismatch (the read chain and the supplied `hash_anterior` don't agree, or external sync delivered out of order), the helper raises `HashChainIntegrityViolation` → 500; the cloud-side verifier writes a `sync_conflict` row with both `datos_local` / `datos_cloud` snapshots, and the cloud-side `alerta tipo_alerta='sync_failure'` workflow opens a chain (see `workflow-transitions.md` REQ-21 on `alerta`)

### REQ-X5-AUDIT-TRIGGERS: All `[A]` REVOKE + `BEFORE UPDATE OR DELETE` triggers active in same migration
**Given** the bootstrap migration (`0001_initial_schema.py` plus 4 incremental migrations for the 49-table drift) creates any of the 12 `[A]` tables
**When** the migration runs
**Then** the migration MUST include in the SAME script (per `openspec/config.yaml` `rules.tasks`): (a) `REVOKE UPDATE, DELETE ON prod.<table> FROM rol_app` for ALL 12 `[A]` tables EXCEPT `sync_queue`; (b) `CREATE OR REPLACE FUNCTION prod.fn_<table>_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION '<TABLE>_INMUTABLE' USING ERRCODE = '42501'; END; $$` + `CREATE TRIGGER <table>_no_update_delete BEFORE UPDATE OR DELETE ON prod.<table> FOR EACH ROW EXECUTE FUNCTION prod.fn_<table>_inmutable()`; (c) the `sync_queue` table gets an ALTER trigger carve-out: `CREATE OR REPLACE FUNCTION prod.fn_sync_queue_mark_dispatched() ...` that permits UPDATE only on `(estado, intentos, next_retry_at, ultimo_error)` columns. The `preflight_table_counts.sh` script asserts `\dt prod.*` returns 49, `pg_trigger WHERE tgname LIKE '%_inmutable'` returns >= 11, `pg_trigger WHERE tgname LIKE 'ls_session%'` returns 2, and the REVOKE statements are present (`has_table_privilege('rol_app', '<table>', 'UPDATE')` returns false on the 11 `[A]`s excluding `sync_queue`)

### REQ-X6-SYNC-TRIGGERS: `AFTER INSERT` enqueues to `sync_queue` for replicated `[A]` rows
**Given** an INSERT into any of the 12 `[A]` tables whose rows are part of the sync replication set (all 12 — `sync_queue` is the local-only exception; `sync_conflict` and `sync_log` are also local-only; the other 9 are cloud-mirrored)
**When** the row commits
**Then** the DB-side `AFTER INSERT` trigger `prod.fn_enqueue_sync` MUST fire and INSERT a row into `prod.sync_queue` with `tabla = TG_TABLE_NAME`, `uuid_registro = NEW.uuid`, `datos = json(NEW)`, `estado = 'pendiente'`, `prioridad = <per-table default>`, EXCEPT when `TG_TABLE_NAME = 'sync_queue'` (recursion guard) — `WHEN (TG_TABLE_NAME <> 'sync_queue')`. The API does NOT enqueue manually; the DB does. A migration test inserts an arbitrary `[A]` row (`factura_pagos`) and asserts that exactly one `sync_queue` row exists afterwards. A second test inserts a `sync_queue` row directly and asserts NO new `sync_queue` row is created (recursion guard works)

### REQ-X7-JWT-SCOPE: Three issuers, hard separation
**Given** any request to `/api/v1/*`
**When** the JWT verification middleware runs (`parkos_core/auth/jwt_issuer_guard.py`)
**Then** the system MUST (a) verify `iss` against the expected issuer for the route: `iss=admin-*` ⇒ admin routes, `iss=operador-*` ⇒ branch + admin routes, `iss=sync-agent-*` ⇒ sync routes only; (b) verify signature against the issuer's JWKS (`/.well-known/jwks.json` per issuer) with grace rotation window `JWT_OVERLAP_HOURS=24` (both keys in JWKS during rotation); (c) verify `aud` claim (`aud=parkos-admin` or `aud=parkos-branch`); (d) reject cross-issuer tokens (operador attempting admin route, or any non-sync token hitting `/sync/*`) with 401. The three issuers each have their own private/public keypair stored in the deployment secrets (`/var/secrets/jwt_admin_*.pem`, etc.). Audit log entries (`actor_real_id` vs `actor_impersonado_id`) capture impersonation when an admin acts on behalf of an operador; admin-as-actor with `actor_impersonado_id = <operador_uuid>` is permitted only for documented `impersonation_scope` claims

### REQ-X8-JWT-SYNC-AGENT: `sync-agent-` tokens only on sync endpoints
**Given** a request hits `/api/v1/sync/{pair, push, pull, events}` (per Q3, mounted on both `api_admin` and `api_sucursal`)
**When** the JWT issuer guard runs
**Then** the request MUST carry a `sync-agent-` token scoped to `uuid_sucursal` (a branch-specific sync agent) or to `cloud_admin`; any other token (`admin-`, `operador-`) returns 401. The 4 sync endpoints are the ONLY mount points for `sync-agent-` tokens; no other API mount accepts them

### REQ-X9-CHAIN-TIE-BREAK: Workflow chain-tip deterministic ordering
**Given** a workflow chain (or branch) on any `[L-W]` table
**When** the helper `parkos_core/repo/workflow.py::read_chain_tip()` resolves "current state" given potentially multiple chains (rejections + re-opens)
**Then** the algorithm MUST (a) collect all root rows (`uuid_*_padre IS NULL`) for the chain's scope filter (e.g. for `anulaciones`: same `uuid_sucursal` + same `uuid_ingreso` + same `tipo_anulable`); (b) for each root, walk forward through `uuid_*_padre` FKs to the leaf (a row not referenced as anyone's parent); (c) select the leaf with the most recent `timestamp_evento`; (d) on `timestamp_evento` tie, select the leaf of the longer chain (more rows from root to leaf); (e) on further tie, select by lexicographic `uuid` ASC. Returns `{uuid_root, uuid_actual, estado, timestamp_evento, chain_length}`. The algorithm is identical per table — no per-table variation

## Scenarios

### SC-X1-TENANT-SCOPE: Cross-branch access denied
1. Operador O1 (pinned to `sucursal_id=A`) calls `GET /api/v1/ingreso/{uuid_X}` where `uuid_X.uuid_sucursal = B`.
2. Tenant middleware checks: `O1.sucursal != uuid_X.uuid_sucursal`. 403 `tenant_scope_violation`.
3. Admin A1 (with `sucursales_permitidas=[A, B, C]`) calls same with `X-Sucursal-Context: A`. Same 403 (header not in `B`).
4. Admin A1 retries with `X-Sucursal-Context: B`. 200 OK.
5. Admin A1 retries with `X-Sucursal-Context: D` (not in list). 403 `unauthorized_sucursal_context`.

### SC-X2-HASH-CHAIN-VERIFY: Cloud verifier accepts intact chain
1. Branch inserts 5 `log_transaccional` rows in TX order with hashes `h0, h1, h2, h3, h4`.
2. Branch syncs them up; cloud applies them in TX order.
3. Cloud verifier queries `SELECT uuid, hash_anterior, hash_actual FROM log_transaccional WHERE uuid_sucursal=B ORDER BY timestamp_evento` — each row's `hash_anterior` equals the previous row's `hash_actual`; each `hash_actual` matches `sha256(payload + previous_hash_actual)`. Pass.

### SC-X3-HASH-CHAIN-BREAK: Out-of-order sync triggers violation
1. Branch inserts 3 rows (h0, h1, h2). Network reorders: cloud receives row 3 first.
2. Cloud applies row 3 as if it were next in the chain. `hash_anterior=h2` but the previous max-row hash is `h0`. Helper raises `HashChainIntegrityViolation`.
3. Cloud writes a `sync_conflict` row with both versions (the cloud's chain-head attempt and the buffered branch `datos_local`). Returns 500 to the sync worker.
4. Cloud admin `validacion_evento` chain opens on the affected `uuid_sucursal`.
5. Sync worker retries after manual reconciliation; the worker re-applies in correct order; chain extends.

### SC-X4-PREFLIGHT: bootstrap PR2 gate
1. CI runs `preflight_table_counts.sh` against the migrated dev DB.
2. Asserts `psql -tA -c "\dt prod.*" | wc -l` = 49 (or `>=` for future expansion).
3. Asserts the 11 `[A]` REVOKE statements are active (SQL `has_table_privilege` check).
4. Asserts the 2 `[L-S]` UPDATE-guard triggers exist.
5. Asserts `pg_partman.part_config` lists 8 parents (`factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `log_transaccional`, `caja`, `arqueo`, `salidas`).
6. Any failure → exit non-zero; bootstrap PR2 reviews blocked until fixed.

### SC-X5-SYNC-QUEUE-INSERT: Recursion guard
1. Direct INSERT into `prod.sync_queue` (test fixture). After commit, no new `sync_queue` row appears (the `WHEN TG_TABLE_NAME <> 'sync_queue'` filter holds).
2. INSERT into `prod.factura_pagos` (test fixture). After commit, exactly one `sync_queue` row appears with `tabla='factura_pagos'`.

### SC-X6-DIAN-BOUNDARY: Branch image import attempt
1. Branch image boots. CLI: `python -c "from parkos_core.dian import cloud_router"`. Expect `ImportError`.
2. CI test `test_cloud_router_branch_boundary.py` reproduces and asserts the same.
3. OpenAPI emitted by branch process: `jq '.paths | keys | map(select(.|test("/factura-electronica|/revocacion-factura|/envio-dian|/validacion-evento")))' api_sucursal/openapi.json` returns `[]`.

## Constraints

- **C-X1**: The three enforcement layers (API / ORM / DB) MUST each reject independently — defense in depth per AGENTS.md canon. A test gap at any layer is a regression.
- **C-X2**: Every migration that touches an `[A]` table MUST include both REVOKE statement and `BEFORE UPDATE OR DELETE` trigger in the SAME migration. `openspec/config.yaml` `rules.tasks` enforced.
- **C-X3**: Hash-chain helpers never accept client-supplied `hash_anterior`/`hash_actual`. Pydantic rejects with 422.
- **C-X4**: JWT three issuers are mutually exclusive; grace rotation is implemented via dual-key JWKS during `JWT_OVERLAP_HOURS=24` windows.
- **C-X5**: Tenant scope is enforced via middleware, not via FK constraints alone — operators must not be able to enumerate other branches' rows.

## Out of scope

- DIAN HTTP transport (handled by separate change for the DIAN provider adapter).
- BFF (deferred to v2).
- WebSocket sync (deferred to v2 — polling only).
- RBAC permission matrix population (framework ships here; matrix is per-permission lookup in `permisos_usuario` — population is a follow-up change. See `operational.md` REQ-OP-08).

## Dependencies

- `bootstrap-monorepo-foundation` MUST ship: 49-table schema, REVOKE + triggers (11+2), `pg_partman` partitions (8), JWT three keypairs, `app_user` and `rol_app` roles, `configuracion_seguridad` default row.
- `parkos_core/auth/{tenancy, jwt_issuer_guard, permissions}.py` — cross-cutting modules.
- `parkos_core/db/triggers.py` — Alembic migration helpers (`create_a_table_with_trigger` factory).
- `openspec/scripts/preflight_table_counts.sh` — schema-count probe (PR0 deliverable).
- ADR references: AD-1, AD-2, AD-3, AD-4. Q4 (tenant context header), Q3 (sync endpoints), Q11 (login lockout), Q12 (live views) cross-reference here.
- Engram topic: `sdd/create-49-table-apis/spec`.
