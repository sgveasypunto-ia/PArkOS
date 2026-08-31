# Container Entrypoint Orchestration Specification

## Purpose

Defines the shared `infra/docker/entrypoint.sh` plus per-service variants that run before the main process on every container boot. The entrypoint enforces "REVOKE + triggers must exist before traffic flows" by waiting for Postgres, verifying roles, running Alembic, and post-migration verifying that audit-first protections survived migration.

## Requirements

### Requirement: Wait-for-Postgres Loop

The entrypoint MUST poll the database (`SELECT 1`) on a fixed interval until the DB becomes reachable or a retry budget elapses. It MUST abort non-zero if Postgres never becomes reachable. This MUST run before any other check.

#### Scenario: Postgres is unreachable past the retry budget

- GIVEN the DB container is stopped
- WHEN the entrypoint retries until its budget elapses
- THEN it prints a clear error and exits non-zero.

### Requirement: `rol_app` Precheck

Before invoking Alembic, the entrypoint MUST execute `SELECT 1 FROM pg_roles WHERE rolname='rol_app'`. If the row is missing, the entrypoint MUST abort non-zero with an error instructing the operator to wipe the Postgres data directory so `01_roles.sql` re-runs.

#### Scenario: rol_app exists

- GIVEN the bootstrap init scripts have applied
- WHEN the precheck runs
- THEN it returns one row and the entrypoint proceeds.

#### Scenario: rol_app missing — entrypoint aborts

- GIVEN a pre-existing Postgres data directory that never ran the init scripts
- WHEN the precheck finds zero rows
- THEN the entrypoint prints `rol_app role missing — wipe pg_data and restart` and exits non-zero
- AND Docker marks the container unhealthy.

### Requirement: Idempotent Alembic Migration on Boot

The entrypoint MUST invoke `alembic upgrade head` on every container start. Alembic's own versioning MUST make the call a no-op when the DB is already at head.

#### Scenario: First boot runs all migrations

- GIVEN a freshly initialized database
- WHEN `alembic upgrade head` runs
- THEN `0001_initial_schema.py` applies and `alembic_version` advances.

### Requirement: Post-Migration REVOKE and Trigger Verifier

After `alembic upgrade head`, the entrypoint MUST verify:
1. For each of the eleven `[A]` tables, `has_table_privilege('rol_app', 'prod.<t>', 'UPDATE')` and `has_table_privilege('rol_app', 'prod.<t>', 'DELETE')` are both `false`.
2. A `BEFORE UPDATE OR DELETE` trigger exists in `pg_trigger` and is enabled for each.

The entrypoint MUST abort non-zero if any REVOKE or trigger is missing, with a message naming the table.

#### Scenario: All REVOKEs and triggers present

- GIVEN a clean migration
- WHEN the verifier queries `pg_trigger` and `has_table_privilege`
- THEN the script prints `OK` and proceeds.

#### Scenario: REVOKE missing — verifier aborts

- GIVEN an operator manually granted `UPDATE` on `prod.caja` to `rol_app`
- WHEN the verifier runs
- THEN it prints `drift: rol_app retains UPDATE on prod.caja` and exits non-zero.

#### Scenario: Trigger dropped — verifier aborts

- GIVEN an operator `DROP TRIGGER caja_inmutable ON prod.caja`
- WHEN the verifier queries `pg_trigger`
- THEN it prints `drift: trigger caja_inmutable missing` and exits non-zero.

### Requirement: Pairing Token Exchange (Branch Entrypoints Only)

The branch entrypoint MUST read `PAIRING_TOKEN` and `CLOUD_API_URL`. After the verifier succeeds, it MUST `POST` to `${CLOUD_API_URL}/api/v1/sync/pair` with the token and `BRANCH_UUID`. On `200`, it MUST persist the returned JWT to `/var/secrets/parkos-sync-jwt` (mode `0600`, owner `app`).

#### Scenario: Pairing succeeds and JWT is persisted

- GIVEN a valid `PAIRING_TOKEN` (24h TTL) and matching `BRANCH_UUID`
- WHEN the entrypoint POSTs to `/sync/pair`
- THEN the response carries a JWT with `scope: sync_agent`
- AND `/var/secrets/parkos-sync-jwt` exists with permissions `-rw-------`.

### Requirement: Exec Final CMD After All Checks

Once every prior requirement has succeeded, the entrypoint MUST `exec "$@"` so the runtime process (uvicorn or worker loop) becomes PID 1 and inherits signals correctly.

#### Scenario: API container hands off to uvicorn

- GIVEN all checks pass and `CMD ["uvicorn", "api_admin_main:app", "--port", "8000"]`
- WHEN the entrypoint reaches its last line
- THEN uvicorn replaces the shell as PID 1.