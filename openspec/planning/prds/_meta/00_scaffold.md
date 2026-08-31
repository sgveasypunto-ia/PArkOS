# Meta-PRD: Scaffold + uv workspace (PRD-00)

> **NOT a table PRD.** Guides the creation of the Python monorepo scaffold
> (`pyproject.toml` workspace, package structure, tooling). All 45 table
> PRDs depend on the scaffold being in place. See `_shared/references.md`.

## Required References

### Canonical files outside this folder

- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd) — informs the models created later
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md) — strict TDD off until F1 lands
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md) — Python 3.13 + FastAPI + SQLAlchemy 2.0 async + Alembic + uv
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md) — Phase 0 F1
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **Bootstrap Tasks (F1+F2)**: [`openspec/changes/bootstrap-monorepo-foundation/tasks.md`](../../changes/bootstrap-monorepo-foundation/tasks.md)

### Shared PRD references (this folder)

- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for scaffold*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata

- **Type**: Meta-PRD (not a table)
- **Phase**: Phase 0 (Foundation Walking Skeleton) — F1 of the iteration plan
- **Scope**: backend workspace + 5 service packages + tooling
- **Stack**: Python 3.13 + uv 0.4+ workspace
- **Origin**: `bootstrap-monorepo-foundation/F1`
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. Use Cases enabled by this PRD

This scaffold enables EVERY use case in the system. The 45 table PRDs each define specific use cases; this PRD establishes the foundation they all share.

### 2.1 Use Case: `uc.setup.dev-env`

A developer clones the repo and runs `uv sync` from `backend/`. All 5 service packages are installed in a single virtualenv. `uv run --package <svc> python -c "import <svc>_main"` works for any service. `pytest` discovers tests across all packages.

**Steps**:
1. `git clone https://github.com/easypunto/parkos.git && cd parkos/backend`
2. `uv sync` (resolves all 5 workspace members, generates `uv.lock`)
3. `uv run pytest` (runs tests across all packages)

**Tables involved**: NONE (scaffold only).
**Integrations**: enables `uc.setup.run-service` (next).

### 2.2 Use Case: `uc.setup.run-service`

A developer or CI runs any of the 4 entrypoints (`api_admin`, `api_sucursal`, `job_sync_cloud`, `job_sync_sucursal`). The scaffold's `__main__.py` pattern + uvicorn wiring is consistent across services.

**Steps**:
1. `uv run --package api_admin python -m api_admin_main` (starts uvicorn on :8000)
2. Same for other services on different ports.
3. `curl http://localhost:8000/health` returns 200.

**Tables involved**: NONE (scaffold).
**Integrations**: feeds into all 12 iterations (IT-1..IT-12) once schemas land in F1.

### 2.3 Use Case: `uc.setup.docker-build`

Docker multi-stage build uses `[tool.uv] package = true` markers to know which services to install in the runtime image.

**Steps**:
1. `docker build --build-arg BUILD_TARGET=api_admin -t parkos:test .`
2. Container runs `infra/docker/entrypoint.sh` which calls `alembic upgrade head`.
3. Service starts on configured port.

**Tables involved**: NONE (scaffold).
**Integrations**: enables F1 schema + F2 building blocks + every iteration.

### 2.4 Use Case: `uc.setup.entrypoint-orchestrates-multi-stage-init`

The shared `infra/docker/entrypoint.sh` orchestrates the multi-stage container initialization sequence: `wait-postgres → rol_app precheck → alembic upgrade head → REVOKE/trigger verifier → JWT keys load → service start`. This is the SAME script for both cloud and branch images — only the `SERVICE_NAME` runtime env var differs. The script gates the service start on critical integrity checks (hash chain genesis row, REVOKE/triggers present, JWT keys valid) — boot fails non-zero if any check fails. This is the boot-blocking invariant that protects the AUDIT-FIRST contract.

**Steps**:
1. `docker compose up` (cloud or branch) starts the container.
2. `entrypoint.sh` runs as the container's PID 1.
3. `wait-postgres`: `pg_isready` polling until Postgres is reachable (max 60s).
4. `rol_app precheck`: `psql -c "SELECT 1 FROM pg_roles WHERE rolname='rol_app'"` — if missing, bootstrap creates the role from `infra/postgres/init_roles.sql`.
5. `alembic upgrade head`: runs all migrations. If `0001_initial_schema.py` is the only migration, this creates all 45 tables + REVOKE statements + `reject_mutation` triggers + hash-chain genesis row per `uuid_sucursal`.
6. `REVOKE/trigger verifier`: `psql -c "SELECT count(*) FROM information_schema.triggers WHERE trigger_name='reject_mutation' AND event_object_table NOT IN ('sync_queue')"` — must return 11 (the 11 `[A]` tables excluding sync_queue). If any missing, abort non-zero with `BOOT_VERIFIER_FAILED`.
7. `JWT keys load`: validates `JWT_KEYS_PATH` env var points to a valid RS256 keypair; if missing, generates a new keypair (per `infra/auth/jwt_keygen.sh`).
8. `service start`: `exec CMD` — runs the service selected by `SERVICE_NAME` (`api_admin` | `api_sucursal` | `job_sync_cloud` | `job_sync_sucursal`).
9. For branch images: AFTER service start, the branch-specific post-init runs `POST /sync/pair` with `PAIRING_TOKEN` to receive the long-lived `sync-agent-` JWT, which is persisted to `/etc/parkos/sync_agent_jwt`.
10. Service is now operational. Subsequent boots skip the migration step (idempotent) but ALWAYS re-run the verifier checks (defense against drift).

**Tables involved**: NONE directly (scaffold); the verifier checks that 45 tables + 11 reject_mutation triggers + 1 hash-chain genesis row per `uuid_sucursal` are present (read-only validation).
**Integrations**: every iteration depends on this boot sequence. F1's `0001_initial_schema.py` is the first migration. Subsequent migrations (sprint 2+) append to the chain.

## 3. Why this PRD is needed

The 45 table PRDs each reference `parkos_core.models.<table>` — but those modules don't exist until the scaffold lands. This PRD defines exactly what files, what dependencies, what tooling, what version pinning, and what directory structure must be in place BEFORE any model file can be created.

## 4. UUIDv4 Handling

- See `_shared/uuid-v4-strategy.md`.
- This meta-PRD does NOT create model classes directly; the UUIDv4 strategy applies to PRD-01 (models) and PRD-02 (jobs queries).
- Scaffold itself generates UUIDs only in two places: (1) `pyproject.toml` project URLs (cosmetic); (2) `Dockerfile` image tag (CI generates via git SHA).
- `parkos_core` package version uses `0.1.0` semver, not UUID.

## 5. SOLID Atomic Breakdown

- See `_shared/solid-principles.md`.
- **S**: scaffold has a single responsibility: establish the workspace skeleton. No business logic, no models, no DB.
- **O**: open for extension — new service packages can be added via `backend/packages/<name>/pyproject.toml` without touching the workspace manifest.
- **L**: each service package is substitutable; `uv sync --package <service>` works for any member.
- **I**: scaffold interfaces are minimal — `uv sync`, `uv run`, `uv add` are the only entry points.
- **D**: scaffold depends on `uv` (binary), Python 3.13 (interpreter); not on any application code.
- **Atomic operations**: N/A — scaffold is configuration, not state.

## 6. FK Map

- N/A — no models in this PRD. The next meta-PRD (`PRD-01`) creates the 45 models with all FKs.

## 7. Atomic DB Operations

- N/A — scaffold does not touch the database directly. The migration is `0001_initial_schema.py` and is created by a separate path (F1 task F1.7).

## 8. CodeGraph Dependencies

After scaffold lands, `codegraph init` indexes:

- `backend/pyproject.toml` (workspace manifest).
- `backend/packages/<each>/pyproject.toml` (5 deps declarations).
- `backend/packages/parkos_core/src/parkos_core/__init__.py` (package init).
- `backend/packages/parkos_core/src/parkos_core/models/__init__.py` (initially empty; populated by PRD-01).
- Empty `__init__.py` files in each `models/{V,L_E,L_W,L_S,A}/` directory.
- `backend/.python-version` (3.13.5).

Blast radius: 5 service packages × (pyproject.toml + `__init__.__.py`) = 10 files.

## 9. Layer-by-Layer Impact

| Layer | Impact | Path |
|---|---|---|
| 1. DB schema | NO (scaffold only; Alembic migration lands separately) | — |
| 24. CI/test | YES (pytest configured) | `backend/pyproject.toml` `[tool.pytest.ini_options]` |
| 25. CI/lint | YES (ruff configured) | `backend/pyproject.toml` `[tool.ruff]` |
| 26. CI/typecheck | YES (mypy configured) | `backend/pyproject.toml` `[tool.mypy]` |
| 28. Docker/compose | YES (Dockerfile references the workspace structure) | `Dockerfile` |

## 10. Deliverables (full specification)

### 10.1 Root `pyproject.toml` (uv workspace marker)

```toml
# /pyproject.toml — empty project marker; workspace lives at /backend
[project]
name = "easypunto-parkos-root"
version = "0.1.0"
requires-python = ">=3.13"
```

### 10.2 `backend/pyproject.toml` (uv workspace root)

```toml
[project]
name = "easypunto-backend"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = = []

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv]
dev-dependencies = [
    "pytest>=8",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "mypy>=1.10",
    "bats",          # shell tests for entrypoint.sh
    "alembic>=1.13",
    "testcontainers[postgres]>=4",
]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "N", "ASYNC", "S", "RUF"]
ignore = ["S101", "B008"]

[tool.mypy]
python_version = "3.13"
strict = true
disallow_untyped_defs = true
no_implicit_optional = true
warn_unused_ignores = true
warn_return_any = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### 10.3 `backend/.python-version`

```
3.13.5
```

### 10.4 Per-service `pyproject.toml` stubs

Five service packages under `backend/packages/`, each with its own
`pyproject.toml` declaring `parkos_core` as an explicit dependency:

- `backend/packages/parkos_core/pyproject.toml` — shared library; no FastAPI dep yet.
- `backend/packages/api_admin/pyproject.toml` — deps: `parkos_core`, `fastapi`, `uvicorn[standard]`, `structlog`.
- `backend/packages/api_sucursal/pyproject.toml` — same shape.
- `backend/packages/job_sync_cloud/pyproject.toml` — deps: `parkos_core`, `httpx`, `structlog`, `apscheduler`.
- `backend/packages/job_sync_sucursal/pyproject.toml` — same shape.

Each service's `pyproject.toml`:

```toml
[project]
name = "<service>"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "parkos_core",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "structlog>=24",
]

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### 10.5 Directory tree (the canonical layout)

```
backend/
├── pyproject.toml
├── uv.lock
├── .python-version
├── packages/
│   ├── parkos_core/
│   │   ├── pyproject.toml
│   │   └── src/parkos_core/
│   │       ├── __init__.py
│   │       ├── models/
│   │       │   ├── __init__.py
│   │       │   ├── V/             # 24 [V] projection tables (usuarios, permisos, clientes, sucursal, ...)
│   │       │   ├── L_E/           # 3  [L-E] event tables (ingreso, facturas, factura_electronica)
│   │       │   ├── L_W/           # 4  [L-W] workflow tables (anulaciones, reclamos, alerta, reimpresion_ticket)
│   │       │   ├── L_S/           # 2  [L-S] session tables (login, sesion)
│   │       │   └── A/             # 12 [A] source-of-truth tables (log_transaccional, revocacion_factura, sync_queue, ...)
│   │       ├── schemas/
│   │       ├── db/
│   │       ├── auth/
│   │       ├── dian/
│   │       │   ├── common/
│   │       │   ├── cloud/
│   │       │   └── branch/
│   │       ├── sync/
│   │       ├── api_admin/
│   │       ├── api_sucursal/
│   │       ├── audit/
│   │       └── migrations/
│   │           ├── env.py
│   │           ├── script.py.mako
│   │           └── versions/
│   │               └── 0001_initial_schema.py  (lands in F1)
│   ├── api_admin/...
│   ├── api_sucursal/...
│   ├── job_sync_cloud/...
│   └── job_sync_sucursal/...
└── tests/
    ├── unit/
    ├── integration/
    └── shell/    # bats tests for entrypoint.sh
```

### 10.6 Tooling config

- `pyproject.toml` `[tool.ruff]` — line-length 100, target Python 3.13.
- `pyproject.toml` `[tool.mypy]` — strict, `disallow_untyped_defs = true`, `no_implicit_optional = true`.
- `.gitignore` — `.venv`, `__pycache__`, `.pytest_cache`, `*.egg-info`, `dist`, `build`, `.mypy_cache`, `.ruff_cache`.
- `openspec/config.yaml` `rules.apply.guidelines` honored.

## 11. Use Case Integration Matrix

This scaffold is the foundation. Every other PRD inherits from it.

| Downstream PRD | Depends on scaffold for | Integration |
|---|---|---|
| `PRD-01_models` | `parkos_core` package + workspace structure | Models live in `parkos_core/models/{V,L_E,L_W,L_S,A}/` |
| `PRD-02_jobs_queries` | `parkos_core` + `job_sync_*` service packages | Workers import from `parkos_core` |
| `PRD-03_apis_queries` | `parkos_core` + `api_*` service packages | Routers import from `parkos_core` |
| T01-T45 per-table PRDs | `parkos_core` package structure + tools (pytest, ruff, mypy) | Each table's model + tests live in their respective locations |

## 12. RED Tests (must fail BEFORE production tasks)

- (RED) `uv sync` from `backend/` resolves all 5 packages without error.
- (RED) `uv run --package parkos_core python -c "import parkos_core"` → success.
- (RED) `uv run --package api_admin python -c "import api_admin_main"` → success (after F1's `__main__.py`).
- (RED) `ruff check backend/` → exit 0.
- (RED) `mypy --strict backend/packages/parkos_core/src/parkos_core/` → exit 0.
- (RED) Workspace glob `["packages/*"]` picks up all 5 service packages.
- (RED) `parkos_core` listed as explicit dep in each service pyproject.toml.

## 13. Implementation Tasks

- [ ] PRD-00.1 Create `/pyproject.toml` (root marker).
- [ ] PRD-00.2 Create `backend/pyproject.toml` workspace root with `[tool.uv.workspace] members = ["packages/*"]`.
- [ ] PRD-00.3 Create `backend/.python-version` = `3.13.5`.
- [ ] PRD-00.4 Create `backend/packages/parkos_core/pyproject.toml` (no FastAPI dep).
- [ ] PRD-00.5 Create `backend/packages/api_admin/pyproject.toml`.
- [ ] PRD-00.6 Create `backend/packages/api_sucursal/pyproject.toml`.
- [ ] PRD-00.7 Create `backend/packages/job_sync_cloud/pyproject.toml`.
- [ ] PRD-00.8 Create `backend/packages/job_sync_sucursal/pyproject.toml`.
- [ ] PRD-00.9 Run `uv sync` from `backend/`; verify `uv.lock` is generated.
- [ ] PRD-00.10 Create the canonical directory tree (with empty `__init__.py` files).
- [ ] PRD-00.11 Add ruff + mypy + pytest config to `backend/pyproject.toml`.
- [ ] PRD-00.12 Add `.gitignore` for `backend/` (extend repo-level).
- [ ] PRD-00.13 Verify: `uv run --package parkos_core python -c "import parkos_core"` exits 0.

## 14. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Workspace member glob `["packages/*"]` doesn't pick up all 5 | Low | Each package must have `[tool.uv] package = true` in its `pyproject.toml` |
| `uv sync --package <service>` doesn't resolve transitive `parkos_core` | Low | Each service explicitly lists `parkos_core` in `dependencies` |
| Python version drift (CI vs local) | Med | Pin `backend/.python-version` to 3.13.5; CI uses `actions/setup-python@v5` with the same version |
| MyPy strict too aggressive for stubs | Med | Allow `# type: ignore[no-untyped-def]` in `__init__.py` only |
| Hatchling backend fails on services without `[tool.hatch.build.targets]` | Low | Add `[tool.hatch.build.targets.wheel] packages = ["src/<service>"]` per service |
| CI fails on missing test runner | Med | `testing.strict_tdd: false` per config.yaml; sdd-qa re-runs sdd-init after PR1 lands |

## 15. Open Questions

- (a) Should `parkos_core` depend on `fastapi` (for type hints) or stay FastAPI-free? Currently NO; FastAPI types imported via TYPE_CHECKING in routers.
- (b) `apscheduler` vs plain `asyncio` for `job_sync_*` workers? Default: asyncio (matches "long-running process" architecture).
- (c) Should the workspace include apps/ (frontend)? Currently NO — apps/ is npm-managed.
- (d) `pydantic-settings` for env vars in services? Default: yes for `api_admin` + `api_sucursal` (need config); no for jobs (config injected from compose env).

## 16. Hand-off

After this PRD lands, **PRD-01 (45 models)** can start writing SQLAlchemy model classes against `parkos_core.models.{V,L_E,L_W,L_S,A}.<table>`.