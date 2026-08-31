## Exploration: Bootstrap Monorepo Foundation

### Topic

Translate the already-ratified cloud-edge topology (Engram #1217, #1219–#1222) and the sync baseline decisions (OpenSpec `cloud-edge-sync-architecture/exploration.md`, Engram #1218) into a concrete monorepo skeleton for `E:\easypunto_parkos`. Resolve the bootstrap-specific unknowns that the sync exploration deliberately deferred: Python + React layout strategy, full directory tree, single-image Dockerfile strategy, the structure of `0001_initial_schema.py` (45 tables + triggers + REVOKE + seed + partitions), branch install UX, and three open scope questions (BFF, isolated workers, WebSocket sync). Output is a baseline that `sdd-propose` can lock without re-exploring topology.

### Current State

**What exists (files on disk)**

- `E:\easypunto_parkos\modelo_datos_er.mmd` — canonical 45-table AUDIT-FIRST schema. Three enforcement levels: 24 `[V]` projection, 3 `[L-E]` event, 4 `[L-W]` workflow, 2 `[L-S]` session/cycle, 12 `[A]` source-of-truth. Hash-chain tables: `log_transaccional`, `revocacion_factura` (per `uuid_sucursal`). DIAN retention columns: `fecha_retencion_hasta` = `created_at + dias_retencion_*`.
- `openspec/PROJECT_CONTEXT.md` — assumes Python 3.13 + FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + Alembic + uv; React 18 + Vite 5 + TS strict + shadcn/ui + Zustand; PostgreSQL 16+; Docker Compose v2.
- `openspec/config.yaml` — has the `design` rule: "For backend module layout, partition models/ by audit level (`models/[V]/`, `models/[L]/`, `models/[A]/`)" — must be honored by `parkos_core/`.
- `openspec/changes/cloud-edge-sync-architecture/exploration.md` — 9 ratified baseline decisions (poll queue, HTTP+JWT, separate worker processes, hash-chain preservation, per-class conflict policy, JWT three issuers, pairing flow, offline window default 7d, source-of-truth ownership).
- `.atl/skill-registry.md`, `.gitignore`, `openspec/specs/.gitkeep`, `openspec/changes/.gitkeep`, `openspec/changes/archive/.gitkeep` — SDD scaffolding only.
- **NO** `pyproject.toml`, `package.json`, `Dockerfile`, `docker-compose.yml`, `.env.example`, migrations directory, source code, or git repo.

**What is encoded in the .mmd that this exploration must respect**

- Schema is `prod.*` plural snake_case (per `openspec/PROJECT_CONTEXT.md` and the `alembic` skill rule for easyPunto).
- `sync_queue` is `[A]` BUT carries an explicit operational UPDATE exception (estado, intentos, next_retry_at, ultimo_error). Engram #1221: `sync_queue` is local-only, never propagated — sync workers filter `tabla='sync_queue'` as no-op.
- `sync_log` and `sync_conflict` are also `[A]` but locally scoped (per-cycle metrics, conflict snapshot). Same no-propagation rule.
- 12 `[A]` tables that need REVOKE UPDATE, DELETE from `rol_app` + triggers RAISE EXCEPTION: `sync_queue`, `sync_log`, `sync_conflict`, `log_transaccional`, `revocacion_factura`, `caja`, `arqueo`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `salidas` — minus the operational exceptions.
- 2 `[L-S]` tables needing partial-UPDATE triggers: `login`, `sesion` — UPDATE allowed only on `estado`, `fecha_cierre` (and `timestamp_apertura`/`timestamp_cierre` for `sesion`), with MANDATORY `log_transaccional` row in same TX.
- DIAN retention 5+ years + SHA256 hash chain on `log_transaccional` and `revocacion_factura` partitioned per `uuid_sucursal`.
- High-volume tables (200k–500k events/day per parking lot): `factura_detalle`, `factura_pagos`, `log_transaccional`, `sync_log`, `sync_queue`, `caja`, `arqueo`, `salidas` — partition by month via `pg_partman`.

**What is NOT yet decided (this exploration resolves these)**

- Monorepo layout strategy (uv workspace vs single `--app` flag vs polyrepo).
- Exact directory tree (parkos_core placement, Alembic location, BFF inclusion, workers placement).
- Dockerfile strategy (single multi-target image vs per-service images).
- `infra/postgres/init/` vs Alembic-migration split for roles / triggers / partitions.
- Branch install UX (image pull vs git clone; entrypoint sequencing).
- BFF, isolated workers, WebSocket — open scope questions.

**Already-decided Engram topics this exploration MUST align with**

- `architecture/cloud-edge-topology` — `web_admin <-> api_admin <-> job_sync_cloud <-> many(job_sync_sucursal) <-> many(api_sucursal) <-> web_sucursal`.
- `architecture/deployment-topology` — both cloud and branch via Docker Compose; same monorepo, two different compose files; branch reads pairing config from env vars.
- `architecture/sync-hash-chain` — cloud preserves branch chain verbatim, only extends with cloud-originated rows on the SAME `uuid_sucursal` chain.
- `architecture/jwt-three-issuers` — three JWT key sets (`admin`, `operador`, `sync-agent`).
- `architecture/sync-queue-local-only` — `sync_queue` rows never propagate.

### Affected Areas

**Already on disk** (no changes to these)

- `E:\easypunto_parkos\modelo_datos_er.mmd` — canonical model; bootstrap must read it, not regenerate.
- `openspec/PROJECT_CONTEXT.md`, `openspec/config.yaml`, `openspec/SPECS/` — referenced but not modified.

**Will be created by later phases (this exploration just defines the shape)**

- `pyproject.toml` (root — uv workspace manifest).
- `Dockerfile` (multi-stage, `BUILD_TARGET` build arg selects one of four Python entrypoints).
- `docker-compose.cloud.yml`, `docker-compose.branch.yml`, `.env.cloud.example`, `.env.branch.example`.
- `backend/packages/parkos_core/` (shared library — models, schemas, db, auth, sync, dian).
- `backend/packages/{api_admin,api_sucursal,job_sync_cloud,job_sync_sucursal}/` (entrypoints).
- `apps/{web_admin,web_sucursal}/` (React 18 PWA scaffolds).
- `apps/ui-kit/` (shared shadcn/ui + design tokens).
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (THE critical migration).
- `infra/postgres/init/01_roles.sql`, `02_extensions.sql` (pre-Alembic).
- `infra/sync_policy.yaml` (per-class conflict policy defaults).
- `infra/docker/entrypoint.sh` (alembic upgrade head + REVOKE verifier).
- `docs/{architecture,sync-flow,dian-compliance,branch-setup}.md`.
- `openspec/changes/bootstrap-monorepo-foundation/proposal.md`, `design.md`, `tasks.md`, `verify-report.md`.

### Approaches

#### 1. Python layout (3 options compared)

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. uv workspace** — `pyproject.toml` at `backend/` root with `[tool.uv.workspace] members = ["packages/*"]`; `parkos_core` plus four service packages each with own `pyproject.toml` depending on `parkos_core`. | Clean separation; one `uv.lock` coordinates all members; shared transitive deps resolved once; new service = `uv init --package packages/<name>` + 2-line addition to workspace manifest; matches `uv` skill convention exactly (`[tool.uv.workspace]`). | Two layers of `pyproject.toml` (root + 5 members); workspace member resolution can surprise CI on first run. | Low |
| **B. Single `pyproject.toml` + `--app` flag** — one package, multiple `main_*.py` entrypoints selected via `APP` env var. | Simplest possible layout; no workspace concept. | Couples the four services at packaging level; can't run unit tests for one service without pulling all; dirty when a service needs an extra dep; `entrypoints` table in `pyproject.toml` becomes a key–value bag. | Low (start), but bloats fast. |
| **C. Polyrepo** — four separate repos sharing via git subtree or submodule. | Strong service boundary. | Slow painful merges; cross-cutting refactors are nightmares; CD pipelines multiply; the four services share the SAME schema and MUST stay aligned — polyrepo fights this requirement. | High |

**Decision: A (uv workspace).** Matches the `uv` skill exactly (`[tool.uv.workspace]` members = `["packages/*"]` is the documented pattern). Clean service boundaries without polyrepo pain. The model is shared, so the four services MUST share a lockfile — uv workspace makes that mandatory and trivial.

#### 2. Alembic location — co-locate vs `infra/alembic/`

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. `backend/packages/parkos_core/migrations/`** (co-located with models) | `env.py` does `from parkos_core.models import …` directly; `prepend_sys_path = ../src`; `alembic check` works without sys.path hacks; matches the `alembic` skill convention; migrations travel with the package that owns the schema. | Path is `backend/packages/parkos_core/migrations/versions/` — slightly deeper than a flat `migrations/`. | Low |
| **B. `infra/alembic/`** (separate infra tree) | Migrations are discoverable in a single ops-focused dir. | `env.py` must hack `sys.path` to reach `backend/packages/parkos_core/src/`; less idiomatic; harder to evolve (services that grow schema still need `infra/alembic/`). | Medium |

**Decision: A (co-locate).** The alembic skill's canonical pattern is `migrations/env.py` next to the models that define `target_metadata`. Co-location honors that and removes a layer of indirection. `infra/` keeps only pre-Alembic SQL init scripts (roles, extensions) which Alembic should NOT manage.

#### 3. Dockerfile strategy (single multi-target vs per-service)

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. Single multi-stage Dockerfile with `BUILD_TARGET` build arg** — one image artifact; runtime service selected via `SERVICE_NAME` env var; entrypoint.sh dispatches. | Single security baseline; one CI build matrix entry; simpler registry; layer caching shared across all four services; mirrors the monorepo's "same code, different roles" intent (Engram #1222). | Slightly larger image (carries all four main entrypoints); changing any one service requires a new image tag (mitigated by `docker compose build` rebuilding the same Dockerfile with same tag). | Low |
| **B. Per-service Dockerfile** in each `packages/<service>/`. | Smallest possible per-service image. | Four Dockerfiles to maintain; four buildx entries; four security audits; divergence pressure over time. | Medium-High |
| **C. Monorepo build tool** (Bazel, Nx, Earthly). | Reproducible, cached, hermetic. | Steep learning curve; not aligned with the easyPunto tooling budget. | High |

**Decision: A (single multi-stage).** The bootstrap must stay under the 400-line review budget and a single Dockerfile is one file. ENTRYPOINT dispatches by `SERVICE_NAME`. Same image is pushed once per build, deployed to cloud OR to any branch — Engram #1222 explicitly says "same image artifacts can deploy to cloud OR to a branch."

#### 4. `infra/postgres/init/` vs Alembic-managed DDL

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. Init scripts: roles + extensions ONLY. Everything else in Alembic.** | Roles (`rol_app`, `rol_admin_auditor`) and `pg_partman` extension must exist before Alembic can REVOKE or `partman.create_parent` — `infra/postgres/init/` is the right home. Trigger functions, triggers, REVOKE statements, table DDL, partitions, seed data all live in `0001_initial_schema.py` and are versioned with code. | The split is non-obvious; needs to be documented in the entrypoint and the migration's docstring. | Low |
| **B. All SQL in init/ (no Alembic).** | One-shot, easy to read. | No version control; drift between cloud and branch possible; no `alembic check`; no rollback story. | High risk. |
| **C. All in Alembic (no init/).** | Single source of DDL. | Alembic can't create roles idempotently across rebuilds; can't load extensions before table DDL; can't `GRANT BYPASSRLS` until the role exists. | High risk. |

**Decision: A (split).** Specifically:
- `infra/postgres/init/01_roles.sql` — `rol_app` (NOLOGIN), `rol_admin_auditor` (BYPASSRLS), GRANTs. Idempotent via DO block (`CREATE ROLE` has no `IF NOT EXISTS` pre-PG16).
- `infra/postgres/init/02_extensions.sql` — `pg_partman`, `pgcrypto`, `uuid-ossp` (`CREATE EXTENSION IF NOT EXISTS`).
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` — ALL 45 tables, ALL triggers, ALL REVOKEs, ALL `pg_partman.create_parent` calls, ALL seed data, hash-chain seed.

#### 5. Frontend layout (React)

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. Three npm workspaces** — `apps/web_admin`, `apps/web_sucursal`, `apps/ui-kit`. `apps/package.json` declares workspaces. | Shared `ui-kit` (shadcn components + design tokens) is the only DRY mechanism that scales; tailwind preset + CSS vars defined once; i18n shared. | Two workspace systems in one repo (uv + npm); need to keep them in sync via CI. | Low |
| **B. Two independent Vite projects, shared via git subtree.** | No npm workspace concept. | Drift between the two apps; ui-kit becomes a copy-paste land. | High risk. |

**Decision: A.** Already the standard. `apps/ui-kit/` is a workspace package exporting components, design tokens, and shared Zod schemas (per the `react` skill — "idealmente en `libs/schemas/` con backend" — `ui-kit` is the closest equivalent for frontend-only shared code).

#### 6. Branch install UX

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. Pull pre-built image from GHCR** — `docker compose -f docker-compose.branch.yml up -d` after editing `.env.branch`. | Fast (no build); one command; matches the operator's "fresh PC" mental model (Engram #1222: "1 command from a fresh PC"). | Operator needs Docker Desktop pre-installed; GHCR auth token required; image is largeish (≈400MB). | Low |
| **B. `git clone` the repo + `docker compose up`.** | No registry dependency; devs can patch. | Operator needs git + docker + buildx; slow first boot (compile deps); diverges from prod image. | Medium |
| **C. Native installer** (.exe / .msi) wrapping docker-compose. | Friendly UX; auto-update. | Big upfront cost; out-of-scope for MVP. | High |

**Decision: A for MVP, with B as fallback when the image is unavailable (e.g., dev machines).** Both compose files use the same image (`ghcr.io/easypunto/parkos:<tag>`). Entry script ensures `alembic upgrade head` runs BEFORE the service starts accepting traffic, so a fresh branch is fully migrated on first boot.

#### 7. Open scope questions

| Question | Options | Decision |
|----------|---------|----------|
| **BFF layer** (`bff/`) | (i) Add now — Node/TS aggregator per PWA. (ii) Skip for MVP, add later if needed. | **(ii) Skip.** Two SPAs, two direct APIs. The CORS surface is tiny; a BFF adds deployment complexity without solving a concrete problem at MVP. Revisit when the first multi-call aggregation pattern appears (estimated: 50+ branches OR when `web_admin` needs to fan-out reads across multiple branch APIs). |
| **`workers/`** (hash_chain_verifier, dian_dispatcher) | (i) Separate Docker services. (ii) Tasks inside `job_sync_cloud`. | **(i) Separate services.** Sync is real-time polling (seconds); verifier is nightly cron; DIAN dispatcher is hourly retry queue. Three different scaling profiles. Co-locating them inside `job_sync_cloud` creates a fat process. `infra/docker/entrypoint.sh` on each worker runs the same REVOKE/trigger verifier. |
| **WebSockets for sync** | (i) HTTP polling only. (ii) Add WS now for cloud→branch push. | **(i) HTTP polling only.** Sync exploration already decided HTTP polling is baseline; WebSocket adds sticky-session + reverse-proxy buffering complexity that we don't need at <100 branches. Add WS only when parametrization latency becomes a UX problem (estimated: v2). |

### Recommendation

The monorepo skeleton is **one backend uv workspace + one frontend npm workspace, sharing a single multi-target Docker image**. Concretely:

```
E:\easypunto_parkos\
├── pyproject.toml                      # root — empty project marker, no [tool.uv.workspace]
├── uv.lock                             # backend only (NOT in monorepo root; lives at backend/)
├── docker-compose.cloud.yml
├── docker-compose.branch.yml
├── .env.cloud.example
├── .env.branch.example
├── .dockerignore                       # root-level; aligned with the docker skill
├── Dockerfile                          # multi-stage, BUILD_TARGET build arg
├── backend/
│   ├── pyproject.toml                  # uv workspace root: [tool.uv.workspace] members = ["packages/*"]
│   ├── uv.lock                         # workspace lockfile
│   ├── .python-version                 # 3.13
│   ├── .dockerignore
│   ├── packages/
│   │   ├── parkos_core/                # SHARED library — everything depends on this
│   │   │   ├── pyproject.toml
│   │   │   └── src/parkos_core/
│   │   │       ├── models/
│   │   │       │   ├── V/              # 24 [V] tables (per audit-level partitioning rule)
│   │   │       │   ├── L_E/            # 3 [L-E] events (facturas, factura_electronica, ingreso)
│   │   │       │   ├── L_W/            # 4 [L-W] workflow (anulaciones, reclamos, alerta, reimpresion_ticket)
│   │   │       │   ├── L_S/            # 2 [L-S] session (login, sesion)
│   │   │       │   └── A/              # 12 [A] append-only (sync_queue, sync_log, sync_conflict, log_transaccional, revocacion_factura, caja, arqueo, factura_detalle, factura_impuestos, factura_otros_cobros, factura_pagos, salidas)
│   │   │       ├── schemas/            # Pydantic v2 (request/response DTOs)
│   │   │       ├── db/                 # SQLAlchemy 2.0 async engine, session, base, tenancy middleware
│   │   │       ├── auth/               # JWT three-issuers (admin/operador/sync-agent), bcrypt, RBAC
│   │   │       ├── api_admin/          # FastAPI routers — admin surface
│   │   │       ├── api_sucursal/       # FastAPI routers — branch surface
│   │   │       ├── sync/               # shared sync logic — queue processor, conflict policy, hash-chain, pairing
│   │   │       ├── dian/               # e-factura builder, hash chain, dispatcher interface
│   │   │       └── migrations/         # Alembic lives here
│   │   │           ├── env.py
│   │   │           ├── script.py.mako
│   │   │           └── versions/
│   │   │               └── 0001_initial_schema.py   # THE critical migration
│   │   ├── api_admin/                  # entrypoint for cloud admin API
│   │   │   ├── pyproject.toml          # deps: parkos_core, fastapi, uvicorn, structlog
│   │   │   ├── src/api_admin_main/
│   │   │   │   └── __main__.py         # uvicorn entrypoint
│   │   │   └── entrypoint.sh           # runs alembic upgrade head + REVOKE verifier + exec uvicorn
│   │   ├── api_sucursal/               # entrypoint for branch API
│   │   ├── job_sync_cloud/             # entrypoint for cloud sync worker
│   │   │   ├── pyproject.toml          # deps: parkos_core, httpx, structlog
│   │   │   ├── src/job_sync_cloud_main/
│   │   │   │   └── __main__.py         # long-running poll loop
│   │   │   └── entrypoint.sh           # waits for DB healthy, alembic upgrade head, REVOKE verifier, exec __main__
│   │   └── job_sync_sucursal/          # entrypoint for branch sync worker
│   ├── tests/                          # integration tests live here (testcontainers)
│   └── pyproject.toml                  # workspace root
├── apps/
│   ├── package.json                    # npm workspace root
│   ├── pnpm-workspace.yaml             # OR npm workspaces in package.json
│   ├── tsconfig.base.json
│   ├── ui-kit/                         # shared shadcn components + design tokens
│   │   ├── package.json                # "@easypunto/ui-kit"
│   │   ├── components.json             # shadcn config
│   │   └── src/
│   │       ├── components/ui/          # generated by `npx shadcn add`
│   │       ├── styles/tokens.css       # CSS variables for white-label
│   │       └── lib/cn.ts
│   ├── web_admin/                      # React 18 PWA — admin UI
│   │   ├── package.json                # "@easypunto/web-admin"; deps: ui-kit (workspace:*)
│   │   ├── vite.config.ts
│   │   ├── tsconfig.json
│   │   ├── components.json
│   │   ├── index.html
│   │   └── src/{routes,components,stores,services,lib,hooks,locales,styles}/
│   └── web_sucursal/                   # React 18 PWA — branch UI (kiosko + cajero)
│       └── ... (same shape)
├── workers/                            # ONLY for the docker compose references; the code lives elsewhere
│   ├── hash_chain_verifier/            # nightly job (separate cloud container)
│   │   └── entrypoint.sh               # cron-style loop in container
│   └── dian_dispatcher/                # hourly retry queue (separate cloud container)
│       └── entrypoint.sh
├── infra/
│   ├── postgres/
│   │   ├── init/                       # runs once at DB first init via /docker-entrypoint-initdb.d/
│   │   │   ├── 01_roles.sql            # rol_app, rol_admin_auditor, BYPASSRLS GRANT
│   │   │   └── 02_extensions.sql       # pg_partman, pgcrypto, uuid-ossp
│   │   └── conf.d/                     # postgres tuning (postgresql.conf overrides)
│   ├── sync_policy.yaml                # per-class conflict policy defaults
│   └── docker/
│       └── entrypoint.sh               # shared helper: alembic upgrade head + REVOKE verifier + exec CMD
├── docs/
│   ├── architecture.md                 # the topology as built
│   ├── sync-flow.md                    # sync worker lifecycle, pairing, hash-chain rules
│   ├── dian-compliance.md              # retention + hash chain explanation
│   └── branch-setup.md                 # operator-facing: fresh-PC install
├── .atl/skill-registry.md              # already exists
├── openspec/
│   ├── config.yaml
│   ├── PROJECT_CONTEXT.md
│   ├── TESTING_CAPABILITIES.md
│   ├── specs/                          # main specs (populated by sdd-spec)
│   └── changes/
│       ├── cloud-edge-sync-architecture/{exploration.md, …}
│       └── bootstrap-monorepo-foundation/
│           ├── exploration.md          # this file
│           ├── proposal.md             # sdd-propose
│           ├── design.md               # sdd-design
│           ├── tasks.md                # sdd-tasks
│           └── verify-report.md        # sdd-verify
└── modelo_datos_er.mmd                 # canonical data model
```

**Why this layout**

1. **Two workspace managers, one per language** — `uv` at `backend/`, npm/pnpm at `apps/`. Each is idiomatic for its ecosystem. Monorepo root is intentionally package-manager-free except for `Dockerfile`, compose files, `.env.example`, `.dockerignore`.
2. **Parkos core is the only package every other backend service depends on.** Models live there, schemas live there, auth lives there, sync logic lives there. This is what `uv workspace` is built for.
3. **Migrations co-locate with models** (`backend/packages/parkos_core/migrations/`) — `env.py` does plain `from parkos_core.models import *` with no `sys.path` hack. `infra/postgres/init/` keeps ONLY roles + extensions, which Alembic shouldn't manage.
4. **One Dockerfile, four runtime entrypoints** selected via `SERVICE_NAME` env var. `infra/docker/entrypoint.sh` is the canonical orchestrator: wait for DB healthy → `alembic upgrade head` → verify REVOKE/triggers present → `exec CMD`.
5. **`workers/` only contains `entrypoint.sh`** for the cloud-only nightly/hourly jobs; the Python code for those workers lives in `parkos_core/workers/`. The directory exists because `docker-compose.cloud.yml` references them as separate services with their own `entrypoint.sh`.

**Dockerfile shape (recommended)**

```dockerfile
# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.13.5
ARG BUILD_TARGET=api_admin   # api_admin | api_sucursal | job_sync_cloud | job_sync_sucursal

# === BUILDER ===
FROM python:${PYTHON_VERSION}-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install uv
WORKDIR /app

# Workspace root first — better cache
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/packages/ ./packages/

# Build all workspace members; install only the requested service's runtime deps
ARG BUILD_TARGET
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package ${BUILD_TARGET} --no-install-project

# Bring in source code (last; cache-friendly)
COPY backend/packages/ ./packages/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# === RUNTIME ===
FROM python:${PYTHON_VERSION}-slim AS runtime
ARG BUILD_TARGET
ENV SERVICE_NAME=${BUILD_TARGET}
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl tini ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home --shell /bin/bash app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv .venv
COPY --from=builder --chown=app:app /app/packages ./packages
COPY infra/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
USER app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:${HEALTHCHECK_PORT:-8000}/health || exit 1
ENTRYPOINT ["tini", "--", "/usr/local/bin/entrypoint.sh"]
```

**`infra/docker/entrypoint.sh` (sketch)** — shared by all four services: wait-for-postgres → `alembic upgrade head` → verify REVOKE + triggers on `[A]` tables (raises if missing) → `exec "$@"`.

**`0001_initial_schema.py` (the critical migration) — must contain, in order**

1. `op.execute("CREATE SCHEMA IF NOT EXISTS prod")` — alembic skill hard rule for `include_schemas=True`.
2. Tables created in dependency order: catalogs (tipo_*, configuracion_*) → empresa → sucursal → usuarios → permisos → permission_usuario → clientes → vehicles → tarifas → operational tables → `[L]` events → `[A]` append-only.
3. `op.execute("CREATE OR REPLACE FUNCTION prod.reject_mutation() RETURNS trigger …")` — RAISE EXCEPTION 'AUDIT_FIRST_INMUTABLE'.
4. `op.execute("CREATE OR REPLACE FUNCTION prod.ls_session_update_guard() …")` — allows UPDATE only on `estado`/`timestamp_cierre`/`timestamp_apertura` AND verifies `log_transaccional` was inserted in same TX (via `pg_temp.xact_log_inserted` flag table).
5. Per-`[A]`-table `BEFORE UPDATE OR DELETE` triggers (except `sync_queue`): `CREATE TRIGGER {table}_inmutable BEFORE UPDATE OR DELETE ON prod.{table} FOR EACH ROW EXECUTE FUNCTION prod.reject_mutation();`
6. Per-`[L-S]`-table triggers on `login`, `sesion` that call the session guard.
7. `op.execute("REVOKE UPDATE, DELETE ON prod.{table} FROM rol_app")` × 11 (all `[A]` except `sync_queue`).
8. `op.execute("GRANT BYPASSRLS TO rol_admin_auditor")` (idempotent).
9. `pg_partman.create_parent(...)` for the 8 partitioned tables with `p_premake := 3`, `p_interval := '1 month'`, `retention := '24 months'`.
10. Seed data via `op.execute("INSERT INTO prod.{table} … VALUES …")` — idempotent (`ON CONFLICT DO NOTHING`).
11. Hash-chain seed: insert first `log_transaccional` and first `revocacion_factura` rows per `uuid_sucursal` with `hash_anterior = NULL` and `hash_actual = SHA256('{uuid_sucursal}||{created_at}||{payload}')` (the genesis row).

**Branch install UX (operator-facing, exact command sequence)**

```bash
# Fresh Windows PC with Docker Desktop pre-installed:
git clone https://github.com/easypunto/parkos.git C:\parkos            # or: docker pull ghcr.io/easypunto/parkos:v0.1.0
cd C:\parkos
cp .env.branch.example .env.branch
# Edit .env.branch:
#   BRANCH_UUID=<uuid from admin's pairing email>
#   PAIRING_TOKEN=<one-time 24h token>
#   CLOUD_API_URL=https://api.easypunto.example
docker compose -f docker-compose.branch.yml up -d
# Logs:
docker compose -f docker-compose.branch.yml logs -f api_sucursal
# Health:
curl http://localhost:8080/health
# Done. First-run entrypoint:
#   1. waits for Postgres healthy (depends_on: condition: service_healthy)
#   2. runs alembic upgrade head (45 tables + triggers + REVOKE + seed)
#   3. verifies REVOKE on [A] tables via SELECT has_table_privilege('rol_app', …)
#   4. POST /sync/pair with PAIRING_TOKEN → exchanges for long-lived JWT (scope=sync_agent, kid=branch-{N})
#   5. JWT persisted to /var/secrets/parkos-sync-jwt
#   6. Initial parametrization pull: catalogs, empresa, sucursal config
#   7. Service starts accepting traffic (uvicorn for APIs, loop for job_sync_*)
```

The entrypoint runs `alembic upgrade head` **once per boot, idempotently** (Alembic checks `alembic_version`; no-op when up-to-date). On schema mismatch, the verifier checks that `pg_trigger` entries exist for every `[A]` table — if any are missing, the entrypoint exits non-zero so Compose marks the container unhealthy and Docker auto-restart loops it until an operator intervenes. This is the defense against "REVOKE/trigger drift on branch boot" from the sync exploration's risk register.

**Frontend stack** (per `react` and `shadcn` skills)

- `apps/web_admin/` and `apps/web_sucursal/` are independent Vite 5 + TS strict + React 18 projects.
- `apps/ui-kit/` is a workspace package exporting: shadcn-generated components, CSS-variable design tokens, shared Zod schemas, the `cn()` helper.
- `vite-plugin-pwa` for service worker; `idb` + `crypto.randomUUID()` for IndexedDB sync queue (per the `react` skill's D-019 rule).
- `i18next` with `es-CO` default (Colombia-first, per D-063).
- WCAG 2.1 AA via `@axe-core/playwright` (per the `react` skill's RNF-022 rule).

### Risks

- **Chained-PR risk is HIGH.** The bootstrap delivers: 1 `pyproject.toml` workspace + 1 `Dockerfile` + 2 `docker-compose.*.yml` + 4 service `pyproject.toml` + 4 `entrypoint.sh` + 2 Vite scaffolds + 1 `ui-kit` workspace + 1 `entrypoint.sh` + 1 `0001_initial_schema.py` (estimated 800–1500 lines for the migration alone). Total: 2500–4000+ authored lines. **The 400-line review budget will be exceeded by 5× to 10×.** `sdd-tasks` MUST propose chained PRs. Recommended slice: PR1 monorepo + uv workspace + Dockerfile + compose skeletons (infra only, no schema); PR2 `0001_initial_schema.py` + init/ SQL; PR3 `parkos_core` models + auth + tenancy + health endpoint; PR4 `api_admin` and `api_sucursal` routers + JWT three issuers; PR5 sync workers + pairing; PR6 PWA scaffolds + ui-kit.
- **Alembic migration size.** Even if the monorepo skeleton ships in chained PRs, `0001_initial_schema.py` is one file with 45 tables + 12 triggers + 11 REVOKE statements + 8 `partman.create_parent` calls + seed data. Splitting this migration is undesirable (a single `head` must represent a coherent initial state). Recommend: `0001_initial_schema.py` lives in its own PR; review budget MUST be exceeded with `size:exception` (the orchestrator preflight says `delivery_strategy: ask-on-risk`, so this triggers a user decision at apply time).
- **Roles-must-exist-before-migration trap.** `0001_initial_schema.py` issues `REVOKE UPDATE, DELETE … FROM rol_app`. If `init/01_roles.sql` didn't run first (e.g., branch operator brought up Postgres from a pre-existing data dir), the REVOKE silently no-ops. Mitigation: `infra/docker/entrypoint.sh` runs a precheck `SELECT 1 FROM pg_roles WHERE rolname='rol_app'` BEFORE `alembic upgrade head`; if missing, it aborts with a clear error directing the operator to wipe `pg_data`.
- **`build_target` / `uv sync --package X` matrix risk.** A uv workspace sync with `--package X` installs only X's runtime deps; if `parkos_core` is referenced by a service but not in its explicit `dependencies`, the resolved lock may not include `parkos_core`'s transitive deps. Mitigation: each service `pyproject.toml` lists `parkos_core` as an explicit dependency (`dependencies = ["parkos_core"]`); `uv sync --frozen --package <service>` then pulls `parkos_core` transitively.
- **Pre-built image size.** A multi-target image carrying four entrypoints + `parkos_core` + all transitive deps lands around 450–550MB compressed. For branch offices on flaky links, that's an operational concern. Mitigation: documented `docker pull` is the happy path; `docker compose build` from `git clone` is the fallback that trades time for bandwidth.
- **TS strict + vite-plugin-pwa + axe-core first-time cost.** First Vite scaffold + shadcn init + axe-core wired into CI is ~250 LOC of config and a 2–3-hour bootstrap. Mitigation: `apps/ui-kit/` exists to absorb the bulk of this in ONE place, and PR6 should include the ui-kit + scaffold in one chained slice.
- **DIAN retention default = 5 years is not in scope.** The migration sets `fecha_retencion_hasta` per row, but the default value comes from `empresa.dias_retencion_*` which is seeded. If a tenant edits `empresa` mid-flight, old rows keep their original retention deadline — verify that's the desired semantic in `sdd-propose`.
- **`build_target` build-arg vs `SERVICE_NAME` env confusion.** `BUILD_TARGET` is the build-time selection (which service image to produce); `SERVICE_NAME` is the runtime selection (which entrypoint the same image runs). Both are needed because the same image artifact deploys to all four roles. Document explicitly in `docs/branch-setup.md` and `docs/architecture.md`.

### Ready for Proposal

**Yes** — with the following micro-decisions to ratify at the proposal phase:

1. **`uv workspace` over single-package or polyrepo** — locked in this exploration. Confirm the user is OK with two workspace managers (uv + npm).
2. **Alembic co-located at `backend/packages/parkos_core/migrations/`** (NOT `infra/alembic/`). Confirm.
3. **`infra/postgres/init/` is roles + extensions ONLY** (NOT triggers / REVOKE / partitions). Confirm.
4. **Single multi-stage Dockerfile with `BUILD_TARGET` + `SERVICE_NAME`** (NOT per-service Dockerfiles). Confirm.
5. **Skip BFF for MVP** (revisit at v2 or 50+ branches). Confirm.
6. **Isolated `workers/hash_chain_verifier` and `workers/dian_dispatcher`** as separate cloud services (NOT inside `job_sync_cloud`). Confirm.
7. **HTTP polling sync for MVP** (no WebSocket). Confirm.
8. **Branch install = `docker pull` + `docker compose -f docker-compose.branch.yml up -d`** (git-clone fallback for dev). Confirm.
9. **Chained PRs are mandatory** for the bootstrap. `sdd-tasks` should forecast this and propose the six-slice chain enumerated in Risks.
10. **`0001_initial_schema.py` requires `size:exception`** against the 400-line budget — must be a deliberate user decision at apply time, not an accident.

If the user ratifies all ten, `sdd-propose` can proceed without re-opening any architectural question. If any answer diverges, surface the divergence here so the proposal re-scopes.