# Monorepo Layout Specification

## Purpose

Defines the top-level repository layout for `easypunto_parkos`: a single monorepo that hosts a Python backend (uv workspace) and a React frontend (npm workspace) side-by-side, sharing one multi-target Docker image. Establishes which folders and manifests exist and how they relate, so every later capability can locate its dependencies.

## Requirements

### Requirement: Single-Repo Two-Workspace Layout

The repository MUST be organized as a single root containing a Python `backend/` uv workspace, a JavaScript `apps/` npm workspace, a shared `infra/` tree for Postgres init and Docker helpers, and `docs/` for prose. The repo root MUST NOT host its own `pyproject.toml` or `package.json` workspace declaration.

#### Scenario: Fresh clone reveals both workspace manifests

- GIVEN an operator runs `git clone` of the repository
- WHEN they inspect the top level
- THEN `backend/pyproject.toml` declares `[tool.uv.workspace] members = ["packages/*"]`
- AND `apps/package.json` declares `"workspaces": ["web_admin", "web_sucursal", "ui-kit"]`
- AND `infra/postgres/init/` and `infra/docker/entrypoint.sh` exist alongside them.

#### Scenario: Backend and frontend evolve independently

- GIVEN a developer edits only `apps/web_admin/src/`
- WHEN CI runs `uv sync` at `backend/` and `npm install` at `apps/`
- THEN neither step touches the other tree's lockfile.

### Requirement: Backend uv Workspace Members

The `backend/` workspace MUST contain a shared library `parkos_core` plus four entrypoint packages (`api_admin`, `api_sucursal`, `job_sync_cloud`, `job_sync_sucursal`). Each service `pyproject.toml` MUST list `parkos_core` as an explicit dependency so `uv sync --package <service>` resolves transitive deps correctly.

#### Scenario: parkos_core exports shared domain modules

- GIVEN `backend/packages/parkos_core/src/parkos_core/`
- WHEN the package is imported
- THEN it exposes `models/` (partitioned by audit level: `V/`, `L_E/`, `L_W/`, `L_S/`, `A/`), `schemas/`, `db/`, `auth/`, `sync/`, `dian/`, and `migrations/`.

#### Scenario: Service packages depend only on parkos_core plus their own deps

- GIVEN `backend/packages/api_sucursal/pyproject.toml`
- WHEN resolved
- THEN `dependencies` includes `parkos_core`, `fastapi`, `uvicorn`, `structlog`
- AND it does NOT import models from any sibling service package directly.

### Requirement: Frontend npm Workspace Members

The `apps/` workspace MUST contain `web_admin`, `web_sucursal`, and a shared `ui-kit` package. `web_admin` and `web_sucursal` MUST consume `ui-kit` via `"ui-kit": "workspace:*"`; `ui-kit` MUST NOT depend on either app.

#### Scenario: ui-kit owns the design system

- GIVEN `apps/ui-kit/`
- WHEN imported by `web_admin`
- THEN it provides shadcn-generated components, CSS-variable design tokens, the `cn()` helper, and shared Zod schemas.

#### Scenario: Workspace install resolves ui-kit locally

- GIVEN a developer runs `npm install` at `apps/`
- WHEN the lockfile is created
- THEN `web_admin` and `web_sucursal` resolve `ui-kit` to the in-repo workspace package, never to a public registry copy.