# Branch Install Flow Specification

## Purpose

Defines the operator-facing procedure to stand up a fresh parking-lot branch on a brand-new PC. Covers Docker prerequisites, image acquisition, env-var configuration, the single `docker compose` invocation that brings the branch online, and verification commands. Documents the fallback path for environments where the registry image is unavailable or the network is unreliable.

## Requirements

### Requirement: Operator Prerequisites

The install flow MUST assume Docker Desktop (Windows/macOS) or Docker Engine + Compose v2 (Linux) is pre-installed. The flow MUST NOT require Python, Node, uv, or any source-build toolchain on the operator PC.

#### Scenario: Operator PC has Docker installed

- GIVEN a Windows 11 PC with Docker Desktop 4.x
- WHEN the operator opens PowerShell
- THEN `docker --version` returns a 20.10+ engine
- AND `docker compose version` returns a v2.x plugin.

#### Scenario: Operator PC lacks Docker

- GIVEN a PC with no Docker installed
- WHEN the operator runs the install command
- THEN Docker prints `command not found`
- AND the docs MUST direct the operator to install Docker Desktop before retrying.

### Requirement: Environment Configuration

The operator MUST copy `.env.branch.example` to `.env.branch` and set three required variables: `BRANCH_UUID` (UUID assigned by admin in `web_admin`), `PAIRING_TOKEN` (one-time 24h-TTL token), and `CLOUD_API_URL` (base URL of `api_admin`).

#### Scenario: Required variables set

- GIVEN `.env.branch` contains all three required variables
- WHEN `docker compose -f docker-compose.branch.yml up -d` runs
- THEN the entrypoints read them and proceed.

#### Scenario: Missing required variable — compose refuses to start

- GIVEN `.env.branch` lacks `PAIRING_TOKEN`
- WHEN the entrypoint reads its environment
- THEN it prints `PAIRING_TOKEN not set` and exits non-zero.

### Requirement: Image Acquisition Path

The operator MUST be able to acquire the image via either (a) `docker pull ghcr.io/easypunto/parkos:<tag>` (happy path), or (b) `git clone https://github.com/easypunto/parkos.git` followed by `docker compose -f docker-compose.branch.yml build` (fallback for flaky networks).

#### Scenario: Happy path uses prebuilt image

- GIVEN reliable network access to GHCR
- WHEN the operator runs `docker pull ghcr.io/easypunto/parkos:v0.1.0`
- THEN the image is downloaded once and reused by Compose.

#### Scenario: Fallback path builds locally

- GIVEN the registry is unreachable
- WHEN the operator runs `git clone ... && docker compose -f docker-compose.branch.yml build`
- THEN the build succeeds from local sources and tags the image identically.

### Requirement: Single-Command Stack Bring-up

The full bring-up MUST be one operator-facing command: `docker compose -f docker-compose.branch.yml up -d`. The first-boot entrypoint MUST then run `alembic upgrade head`, the REVOKE/trigger verifier, and pairing exchange before `api_sucursal` accepts traffic.

#### Scenario: First-boot migration succeeds

- GIVEN a fresh Postgres data directory
- WHEN the entrypoint runs `alembic upgrade head`
- THEN 45 tables, REVOKEs, triggers, partitions, seed, and genesis rows are present
- AND `curl http://localhost:8080/health` returns `200`.

#### Scenario: Boot verifier catches drift

- GIVEN an operator pre-attached a Postgres volume without the init scripts
- WHEN the entrypoint's `rol_app` precheck fails
- THEN `docker compose ps` reports `api_sucursal` as unhealthy
- AND logs show the `rol_app role missing` error.

### Requirement: Operator Verification Commands

After `up -d`, the docs MUST instruct the operator to run `curl http://localhost:8080/health` and `docker compose -f docker-compose.branch.yml logs -f api_sucursal`. Successful verification means a `200` from `/health` and `Application startup complete` in the logs.

#### Scenario: Health endpoint responds

- GIVEN the stack is up
- WHEN the operator runs `curl http://localhost:8080/health`
- THEN the response body is `{"status":"ok"}` with HTTP `200`.

### Requirement: Network-Failure Fallback Documented

`docs/branch-setup.md` MUST document the local-build fallback (`git clone` + `docker compose build`) as the canonical answer to flaky networks.

#### Scenario: Flaky network triggers local build

- GIVEN the operator's link times out on `docker pull`
- WHEN they follow the documented fallback
- THEN the build completes locally
- AND the operator proceeds without contacting GHCR again.