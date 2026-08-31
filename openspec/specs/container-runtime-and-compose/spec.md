# Container Runtime and Compose Specification

## Purpose

Defines the Docker image, the build-time and runtime selection mechanism, and the two Docker Compose stacks (`cloud`, `branch`) that deploy the same image artifact under different roles. Establishes how the image is built once, how its runtime entrypoint is chosen, how container health is verified, and how Compose wires the cloud and branch topologies.

## Requirements

### Requirement: Single Multi-Stage Image with BUILD_TARGET

The repository MUST contain exactly one `Dockerfile` at the repo root. It MUST be multi-stage (builder + runtime), MUST accept a `BUILD_TARGET` build-arg whose value is one of `api_admin | api_sucursal | job_sync_cloud | job_sync_sucursal`, and MUST build only the runtime dependencies for that service via `uv sync --frozen --no-dev --package ${BUILD_TARGET}`. The runtime stage MUST run as non-root UID 1000.

#### Scenario: Building api_sucursal resolves only its deps

- GIVEN `Dockerfile` and `backend/` with all four service pyprojects
- WHEN an operator runs `docker build --build-arg BUILD_TARGET=api_sucursal -t parkos:api-sucursal .`
- THEN the resulting image's `.venv` contains `parkos_core`, `api_sucursal`, `fastapi`, `uvicorn`.

#### Scenario: Image runs as non-root

- GIVEN the built image
- WHEN the container starts
- THEN `whoami` inside returns `app` (UID 1000), never `root`.

### Requirement: Runtime Service Selection via SERVICE_NAME

Each container MUST select its runtime role via the `SERVICE_NAME` env var (not the build arg). The shared entrypoint MUST dispatch to uvicorn for `api_*` or to the poll loop for `job_sync_*`. The image MUST be deployable under any of the four roles without rebuilding.

#### Scenario: Same image runs as api_admin or job_sync_cloud

- GIVEN a single image `parkos:v0.1.0`
- WHEN the cloud compose brings it up once with `SERVICE_NAME=api_admin` and once with `SERVICE_NAME=job_sync_cloud`
- THEN the first runs uvicorn and the second runs the sync poll loop, both without rebuilding.

### Requirement: Mandatory HEALTHCHECK Directive

Every image MUST declare a `HEALTHCHECK` directive probing `http://localhost:${HEALTHCHECK_PORT}/health` via `curl -fsS`. Interval `30s`, timeout `5s`, retries `3`, start-period `60s`. Compose MUST consume this signal via `condition: service_healthy`.

#### Scenario: HEALTHCHECK passes once /health returns 200

- GIVEN the API is fully booted and `/health` returns `200`
- WHEN the next probe runs
- THEN `docker inspect --format '{{.State.Health.Status}}' <container>` reports `healthy`.

### Requirement: Cloud Compose Stack

`docker-compose.cloud.yml` MUST define `api_admin`, `web_admin`, `job_sync_cloud`, `workers/hash_chain_verifier`, `workers/dian_dispatcher`, and `postgres-cloud`. Every non-DB service MUST declare `depends_on: postgres-cloud: condition: service_healthy`. Workers MUST each have their own `entrypoint.sh` and run on different cadences.

#### Scenario: Cloud stack boots end-to-end

- GIVEN a fresh host with Docker installed
- WHEN the operator runs `docker compose -f docker-compose.cloud.yml up -d`
- THEN `postgres-cloud` reports healthy first, then `api_admin`, `web_admin`, and `job_sync_cloud` start
- AND `curl http://localhost:<api_admin_port>/health` returns `200`.

#### Scenario: Worker failure does not block the API

- GIVEN the same stack
- WHEN a worker fails its probe
- THEN `api_admin` and `web_admin` continue serving traffic (workers are independent failure domains).

### Requirement: Branch Compose Stack

`docker-compose.branch.yml` MUST define `api_sucursal`, `web_sucursal`, `job_sync_sucursal`, and `postgres-branch`. Every non-DB service MUST declare `depends_on: postgres-branch: condition: service_healthy`. The branch stack MUST NOT contain cloud-only services.

#### Scenario: Branch stack boots on a fresh PC

- GIVEN a fresh operator PC with `.env.branch` configured
- WHEN they run `docker compose -f docker-compose.branch.yml up -d`
- THEN `postgres-branch` initializes via `infra/postgres/init/*.sql`, runs `alembic upgrade head`, and `api_sucursal` becomes healthy.

#### Scenario: Branch stack rejects cloud-only services

- GIVEN `docker-compose.branch.yml`
- WHEN inspected
- THEN it contains no reference to `api_admin`, `web_admin`, `hash_chain_verifier`, or `dian_dispatcher`.