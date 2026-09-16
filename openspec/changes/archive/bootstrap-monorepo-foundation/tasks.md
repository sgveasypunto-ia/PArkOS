# Tasks: Bootstrap Monorepo Foundation

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 1,200–1,900 across 2 PRs (F1 + F2) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes (only 2 PRs: F1 → F2) |
| Suggested split | F1 infra+schema (size:exception) → F2 building blocks |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |
| F1 carries `size:exception` | true (user-ratified for `0001_initial_schema.py`) |
| Decision needed before apply | Yes |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

This change is now the **Foundation walking skeleton** (Phase 0 of the iteration plan). It establishes everything the per-feature iterations (IT-1..IT-12) need without delivering any business feature. After F1+F2 land, every iteration (IT-1 onward) ships a working end-to-end case.

`0001_initial_schema.py` lands in F1 as one coherent migration (~800–1500 LOC, `size:exception` user-ratified). Splitting that file would break the "one `alembic head` = one complete baseline" property.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Empty monorepo boots an API container that answers `/health` 200, applies 45-table schema on first boot, REVOKE + triggers verified by entrypoint | F1 | `docker compose -f docker-compose.branch.yml up -d --wait && curl -fsS http://localhost:8080/health && docker compose exec postgres-branch psql -U postgres -d parkos -c "\dt prod.*" \| wc -l` → 45 | Real `docker compose up` against the built image; Alembic upgrade against fresh Postgres data dir | Revert F1 deletes `Dockerfile`, `docker-compose.*.yml`, `backend/pyproject.toml`, migration; on non-fresh DB, `alembic downgrade base` drops `prod.*` |
| 2 | JWT three issuers production-ready, DIAN/sync/PAIRING stubs, ui-kit shell, apps/web_admin + apps/web_sucursal empty shells, cross-audience guard active | F2 | `pytest tests/integration/test_jwt_cross_audience.py` + `bash -c 'from parkos_core.dian.cloud.dian_dispatcher import dispatch' && echo OK` from branch code path must fail + `npm run -ws typecheck` | Real `docker compose up`; pytest with `httpx.AsyncClient` against live containers | Revert F2 deletes `parkos_core/{auth,dian,sync}/` implementations + `apps/ui-kit/`; F1 `/health` still works |

### RED tests per threat-matrix (applied)

- **Shell commands** (entrypoint.sh) → RED test in F1 task: `bash -c 'set -euo pipefail; : "${PAIRING_TOKEN:?PAIRING_TOKEN not set}"'` exits 1 when `PAIRING_TOKEN` is unset.
- **Executable-file classification** → RED test in F1 task: `file infra/docker/entrypoint.sh` returns `POSIX shell script, ASCII text executable`; `shellcheck infra/docker/entrypoint.sh` exits 0.
- **Routing (DIAN boundary)** → RED test in F2 task: `from parkos_core.dian.cloud.dian_dispatcher import dispatch` inside a `job_sync_sucursal` import graph MUST raise `ImportError`.
- **JWT cross-audience** → RED test in F2 task: admin→api_sucursal/auth/login → 401; operador→api_admin/auth/login → 401; sync_agent→any/api/auth/login → 401.

---

## Phase 0 / F1 — Foundation Walking Skeleton (`size:exception`, ~800–1500 LOC)

> Per `openspec/config.yaml` `rules.tasks`: every migration task below carries a **pre-flight `alembic upgrade --sql` check** BEFORE applying. Pre-flight prints the raw SQL; the agent reviews it, THEN applies.

- [ ] F1.1 Create `backend/pyproject.toml` with `[tool.uv.workspace] members = ["packages/*"]`, `[project]` marker, `requires-python = ">=3.13"`. Add `backend/.python-version` pinned to `3.13.5`.
- [ ] F1.2 Create stub `pyproject.toml` per service at `backend/packages/{api_admin,api_sucursal,job_sync_cloud,job_sync_sucursal}/` each declaring `dependencies = ["parkos_core", "fastapi", "uvicorn", "structlog"]` and `[tool.uv] package = true`.
- [ ] F1.3 Create `infra/postgres/init/01_roles.sql` — `DO $$ BEGIN CREATE ROLE rol_app NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL END $$;` and same for `rol_admin_auditor BYPASSRLS`.
- [ ] F1.4 Create `infra/postgres/init/02_extensions.sql` — `CREATE EXTENSION IF NOT EXISTS pg_partman; CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS uuid-ossp;`.
- [ ] F1.5 Generate Alembic scaffold under `backend/packages/parkos_core/migrations/` via `uv run --project parkos_core alembic init -t generic migrations`. Customize `env.py` to import `parkos_core.config` + `parkos_core.db.base`, set `include_schemas=True`, `render_as_batch=False`.
- [ ] F1.6 Create `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` skeleton — `revision = "0001_initial_schema"`, `down_revision = None`, `op.execute("CREATE SCHEMA IF NOT EXISTS prod")` first line.
- [ ] F1.7 Fill `0001_initial_schema.py` body (PRE-FLIGHT REQUIRED per `config.yaml` `rules.tasks`):
  1. `op.execute("CREATE SCHEMA IF NOT EXISTS prod")`.
  2. 45 tables created in dependency order: catalogs → parametrization → operational → `[L-W]` → `[L-S]` → `[A]` (per the canonical order in `iteration-plan.md` Phase 2 references).
  3. `op.execute("CREATE OR REPLACE FUNCTION prod.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'AUDIT_FIRST_INMUTABLE'; END; $$;")`.
  4. `op.execute("CREATE OR REPLACE FUNCTION prod.ls_session_update_guard() RETURNS trigger …")` — checks `pg_temp.xact_log_inserted` flag; allows UPDATE only on `estado`, `fecha_cierre`, `timestamp_apertura`, `timestamp_cierre`.
  5. Per-`[A]`-table triggers (11 except `sync_queue`): `CREATE TRIGGER <t>_inmutable BEFORE UPDATE OR DELETE ON prod.<t> FOR EACH ROW EXECUTE FUNCTION prod.reject_mutation();`.
  6. Per-`[L-S]`-table triggers: `CREATE TRIGGER <t>_ls_guard BEFORE UPDATE ON prod.<t> FOR EACH ROW EXECUTE FUNCTION prod.ls_session_update_guard();`.
  7. `op.execute("REVOKE UPDATE, DELETE ON prod.<table> FROM rol_app")` × 11 (all `[A]` except `sync_queue`).
  8. `op.execute("GRANT BYPASSRLS TO rol_admin_auditor")` (idempotent).
  9. Eight `op.execute("SELECT partman.create_parent(p_parent_table := 'prod.<t>', p_control := '<date_col>', p_type := 'range', p_interval := '1 month', p_premake := 3)")` calls for the partitioned tables.
  10. Idempotent seed: catalogs via `INSERT … ON CONFLICT DO NOTHING`; `consumidor_final_default` UUID.
  11. Hash-chain genesis rows: per `uuid_sucursal`, `INSERT INTO prod.log_transaccional … ON CONFLICT DO NOTHING;` and same for `prod.revocacion_factura`.
- [ ] F1.8 Production REVOKE + trigger verifier (called from entrypoint F1.10): SQL block iterating the 11 `[A]` tables, asserting `has_table_privilege('rol_app', 'prod.<t>', 'UPDATE') IS FALSE` and `has_table_privilege('rol_app', 'prod.<t>', 'DELETE') IS FALSE`, plus `EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = 'prod.<t>'::regclass AND tgname = '<t>_inmutable' AND tgenabled = 'O')`. On any failure print `drift: <table> missing REVOKE|trigger` and `exit 1`.
- [ ] F1.9 Pre-flight `alembic upgrade --sql head` against a fresh `postgres:16` container (per config.yaml `rules.tasks`). Inspect generated DDL for: 45 `CREATE TABLE prod.<t>` lines, `CREATE SCHEMA prod`, both trigger functions, 11 REVOKEs, 11 `[A]` triggers, 2 `[L-S]` triggers, 8 `partman.create_parent` calls, hash-chain genesis rows.
- [ ] F1.10 Create `infra/docker/entrypoint.sh` body — `set -euo pipefail` → wait-for-postgres loop → `${PAIRING_TOKEN:?PAIRING_TOKEN not set}` and `${CLOUD_API_URL:?CLOUD_API_URL not set}` for branch images → `${DATABASE_URL:?DATABASE_URL not set}` always → `SELECT 1 FROM pg_roles WHERE rolname='rol_app'` precheck → `alembic upgrade head` → REVOKE + trigger verifier (F1.8) → pairing exchange for branch → `exec "$@"`.
- [ ] F1.11 RED test for entrypoint (threat-matrix: shell commands + executable-file classification): `file infra/docker/entrypoint.sh` returns POSIX; `bash -c 'PAIRING_TOKEN="" CLOUD_API_URL="http://x" /usr/local/bin/entrypoint.sh echo'` exits non-zero printing `PAIRING_TOKEN not set`.
- [ ] F1.12 Create root `Dockerfile` (multi-stage `builder` + `runtime`) with `ARG BUILD_TARGET=api_admin`, `ARG PYTHON_VERSION=3.13.5`, `RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --package ${BUILD_TARGET}` in builder; runtime stage copies `.venv` and `packages/`, `ENV SERVICE_NAME=${BUILD_TARGET}`, non-root `app` UID 1000, `HEALTHCHECK`, `ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]`.
- [ ] F1.13 Create root `.dockerignore` (excludes `.git`, `node_modules`, `apps/dist`, `apps/node_modules`, `.env.*`, `openspec/`, `docs/`, `__pycache__`, `.venv`).
- [ ] F1.14 Create `docker-compose.cloud.yml` — services `postgres-cloud`, `api_admin`, `job_sync_cloud`, with `depends_on: postgres-cloud: { condition: service_healthy }`. `SERVICE_NAME` env per service.
- [ ] F1.15 Create `docker-compose.branch.yml` — services `postgres-branch`, `api_sucursal`, `job_sync_sucursal`. Same healthcheck gate.
- [ ] F1.16 Create `.env.cloud.example` and `.env.branch.example` with required vars.
- [ ] F1.17 Create `parkos_core/db/{base,engine,tenancy}.py` — `DeclarativeBase`, async engine + `async_sessionmaker`, FastAPI dependency injecting `sucursal_id`.
- [ ] F1.18 Create `parkos_core/models/{V,L_E,L_W,L_S,A}/` stubs — one class per table with `__tablename__` + PK so Alembic sees `target_metadata`. Real columns land with feature iterations.
- [ ] F1.19 Create `parkos_core/auth/{passwords.py (bcrypt via passlib[bcrypt] factor 12), jwt_three_issuers.py stub (Scope enum + IssueTokenRequest Pydantic model only)}`.
- [ ] F1.20 Create `parkos_core/api_admin/routers/health.py` + `parkos_core/api_sucursal/routers/health.py` (`GET /health` returning `HealthResponse(status="ok")`).
- [ ] F1.21 Wire `backend/packages/api_admin/src/api_admin_main/__main__.py` + `api_sucursal_main/__main__.py` (uvicorn).
- [ ] F1.22 Apply migration: `uv run --project parkos_core alembic upgrade head`. Verify `\dt prod.*` count = 45; `pg_trigger` check passes; `has_table_privilege('rol_app', 'prod.caja', 'UPDATE')` = `f`.
- [ ] F1.23 DRIFT test (RED for F1.8 verifier): `DROP TRIGGER log_transaccional_inmutable ON prod.log_transaccional;` then restart the API container → entrypoint MUST exit non-zero with `drift: trigger log_transaccional_inmutable missing`.
- [ ] F1.24 Verify: `docker compose -f docker-compose.branch.yml up -d` boots `api_sucursal` + `job_sync_sucursal`; `curl /health` returns 200; `docker compose -f docker-compose.cloud.yml up -d` boots `api_admin` + `job_sync_cloud`.

## Phase 0 / F2 — Building Blocks (~400 LOC)

> After F2, the system is ready for IT-1 (login end-to-end) and onward. Each iteration from IT-1 ships a working end-to-end case.

- [ ] F2.1 Create `parkos_core/dian/common/{numeration.py, provisional.py, sync_back.py}` — `NumerationMode = Literal["online", "offline-preliminar", "sync-back-pending"]`; `provisional_number(prefix, uuid)` deterministic; `SyncBackEvent` Pydantic v2 model.
- [ ] F2.2 Create `parkos_core/dian/cloud/{builder.py, dispatcher.py stub, atomic_next_consecutivo.py}` — `atomic_next_consecutivo(empresa_id, session)` uses `SELECT … FOR UPDATE`. `dispatcher` returns `numero_oficial=None` (real provider in a future change).
- [ ] F2.3 Create `parkos_core/dian/branch/__init__.py` — `ProvisionalNumberConsumer` calling `provisional_number("PRE", uuid)`. RED test (threat-matrix: routing DIAN): `from parkos_core.dian.cloud.dian_dispatcher import dispatch` inside a branch code path MUST raise `ImportError`.
- [ ] F2.4 Create `parkos_core/sync/{queue_processor.py stub, conflict_policy.py stub, pairing.py, sync_back.py}` — function signatures only.
- [ ] F2.5 Production `parkos_core/auth/jwt_three_issuers.py` — three RS256 key pairs (`admin-`, `operador-`, `sync-agent-` prefixes in `kid`); `issue_token(scope, claims, ttl_seconds)`; `verify_token(token, audience)` enforcing `audience == scope`. Cross-audience → 401.
- [ ] F2.6 Create `infra/sync_policy.yaml` — per-class defaults skeleton (manual/append/cloud_wins/local_wins per table class).
- [ ] F2.7 RED test JWT cross-audience: admin token used at `api_sucursal /auth/login` → 401; operador token at `api_admin /auth/login` → 401; sync_agent token at any `/api/auth/login` → 401.
- [ ] F2.8 Create `apps/{package.json (npm workspaces), tsconfig.base.json (strict, noUncheckedIndexedAccess, exactOptionalPropertyTypes)}`.
- [ ] F2.9 Create `apps/ui-kit/{package.json, components.json, src/{components/ui, styles/tokens.css, lib/cn.ts, schemas/}}` — exports `cn`, design tokens, Zod schemas.
- [ ] F2.10 Create `apps/web_admin/{package.json, vite.config.ts, tsconfig.json, index.html, src/{routes,components,stores,services,lib,hooks,locales,styles}/}` empty shell (no features yet — IT-1 fills it).
- [ ] F2.11 Create `apps/web_sucursal/` same shape.
- [ ] F2.12 Verify: `npm install` resolves all three workspaces; `npm run -ws typecheck` clean; `docker compose up` (cloud + branch) boots; `curl /health` returns 200; `pytest tests/integration/test_jwt_cross_audience.py` passes.

---

## Cross-cutting Constraints (apply to every task above)

- **`openspec/config.yaml` `rules.tasks`**: hierarchical numbering used; F1.7 carries pre-flight `alembic upgrade --sql` check before apply; tasks completable in one session.
- **`openspec/config.yaml` `rules.apply`**: never edit schema in ORM only — `0001_initial_schema.py` is the source of truth for DDL in F1.
- **Language contract**: code, identifiers, comments, UI copy default to English. Generated task artifacts (this file) in English.
- **Forbidden in commits**: `Co-Authored-By` and AI attribution. Conventional commits only.
- **Tests deferred until F1 lands** `pyproject.toml` — `openspec/config.yaml` `testing.strict_tdd: false`. After F1: `sdd-qa` re-runs `sdd-init` to flip the runner.
- **Threat-matrix rows omitted** per spec: subprocesses, VCS/PR automation, process integration — not applicable to F1+F2.

## Out of scope (explicit, do NOT create tasks here)

- Real e-factura dispatch (Factus provider integration) — interface shape in F2.2, real call in a future change.
- Real sync worker business logic beyond polling + queue drain — only the boundary lands in F2.4.
- CRUD beyond `/health` — login, /auth/login, /facturas*, /sync/* all live in iterations IT-1..IT-12.
- PWA features beyond auth + health + placeholder routes + preliminar badge + reimpresion gate (all in iterations).
- BFF layer (deferred to v2).
- WebSocket sync (deferred to v2).
- Native installer (deferred to v2).

## Hand-off to IT-1

After F1 + F2 land, **IT-1 (Login end-to-end)** is the first deliverable feature. See `openspec/_meta/iteration-plan.md` for the per-task breakdown of IT-1 (UI admin + UI sucursal + API admin + API sucursal + job_sync_cloud + job_sync_sucursal + DB, ~400 LOC, ~12 RED-tested tasks).