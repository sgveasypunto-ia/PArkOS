# Postgres Bootstrap Roles and Extensions Specification

## Purpose

Defines the pre-Alembic SQL scripts that prepare a fresh Postgres data directory for the easypunto_parkos backend. These scripts run exactly once, before any Alembic migration, to install the two database roles that enforce audit-first permissions and the three extensions that the schema migration depends on.

## Requirements

### Requirement: Roles Bootstrap (`01_roles.sql`)

`infra/postgres/init/01_roles.sql` MUST create the role `rol_app` with `NOLOGIN` and the role `rol_admin_auditor` with `BYPASSRLS`. Both `CREATE ROLE` statements MUST be idempotent because Postgres 15 has no `CREATE ROLE IF NOT EXISTS`. The script MUST run automatically via Postgres's `/docker-entrypoint-initdb.d/` mechanism on first DB initialization.

#### Scenario: Fresh database initializes both roles

- GIVEN an empty Postgres data directory
- WHEN the container first starts and runs `01_roles.sql`
- THEN `pg_roles` contains a row with `rolname = 'rol_app'` and `rolcanlogin = false`
- AND `pg_roles` contains a row with `rolname = 'rol_admin_auditor'` and `rolbypassrls = true`.

#### Scenario: Re-running init on existing data is idempotent

- GIVEN a database that already ran `01_roles.sql` once
- WHEN the container is restarted (no new data dir)
- THEN the script executes the `DO $$ ... EXCEPTION WHEN duplicate_object THEN NULL $$` guard
- AND the container starts without error.

### Requirement: Extensions Bootstrap (`02_extensions.sql`)

`infra/postgres/init/02_extensions.sql` MUST install `pg_partman`, `pgcrypto`, and `uuid-ossp` using `CREATE EXTENSION IF NOT EXISTS` for each. The script MUST execute after `01_roles.sql` so the extensions exist when Alembic later calls `pg_partman.create_parent(...)`.

#### Scenario: All three extensions are present after init

- GIVEN a fresh database has just finished initializing
- WHEN an operator runs `SELECT extname FROM pg_extension`
- THEN the result includes rows for `pg_partman`, `pgcrypto`, and `uuid-ossp`.

#### Scenario: Idempotent re-run

- GIVEN a database where `02_extensions.sql` already executed
- WHEN the script runs again on a container restart
- THEN each `CREATE EXTENSION IF NOT EXISTS` is a no-op
- AND no error is raised.

### Requirement: Execution Order and Naming

The init scripts MUST be prefixed with a numeric ordering prefix so Postgres runs them deterministically (`01_roles.sql` before `02_extensions.sql`). Filenames MUST be lowercase snake_case. The scripts MUST live exclusively under `infra/postgres/init/`; Alembic migrations MUST NOT recreate roles or extensions because pre-Alembic SQL is the single source for them.

#### Scenario: Filename ordering is honored

- GIVEN two files `01_roles.sql` and `02_extensions.sql` mounted in `/docker-entrypoint-initdb.d/`
- WHEN Postgres initializes the cluster
- THEN `01_roles.sql` completes before `02_extensions.sql` starts.

#### Scenario: Alembic never creates roles or extensions

- GIVEN any migration under `backend/packages/parkos_core/migrations/versions/`
- WHEN inspected
- THEN it MUST NOT contain `CREATE ROLE` or `CREATE EXTENSION` statements.