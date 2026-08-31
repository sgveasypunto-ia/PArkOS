# Database Initial Schema Specification

## Purpose

Defines the single Alembic migration (`0001_initial_schema.py`) that lands the 45-table AUDIT-FIRST schema in `prod` on first boot, honoring DIAN compliance (5+ year retention, SHA256 hash chain) and audit-level enforcement: REVOKE on `[A]` tables, RAISE triggers, `[L-S]` guards, `pg_partman` partitioning, hash-chain genesis, and idempotent seed.

## Requirements

### Requirement: Schema and 45 Tables

The migration MUST `CREATE SCHEMA IF NOT EXISTS prod` and MUST create the 45 tables from `modelo_datos_er.mmd` in dependency order (catalogs → parametrization → operational → `[L]` → `[A]`). Tables MUST use plural snake_case and MUST carry `created_at`, `timestamp_evento`, and `fecha_retencion_hasta` where the model requires them.

#### Scenario: Migration creates the full schema on a fresh DB

- GIVEN `01_roles.sql` and `02_extensions.sql` have applied
- WHEN `alembic upgrade head` runs
- THEN tables-in-prod count returns `45`.

### Requirement: REVOKE on Eleven `[A]` Tables

The migration MUST issue `REVOKE UPDATE, DELETE ON prod.<table> FROM rol_app` for: `sync_log`, `sync_conflict`, `log_transaccional`, `revocacion_factura`, `caja`, `arqueo`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `salidas`. `sync_queue` is excluded because sync workers update its operational fields (`estado`, `intentos`, `next_retry_at`, `ultimo_error`).

#### Scenario: rol_app cannot UPDATE an [A] table

- GIVEN the migration has applied
- WHEN a `rol_app` connection issues an UPDATE on `prod.caja`
- THEN Postgres returns `permission denied for table caja`.

#### Scenario: rol_app CAN update sync_queue operational fields

- GIVEN the same connection
- WHEN it issues an UPDATE on `prod.sync_queue` setting `estado` and `intentos`
- THEN the update succeeds.

### Requirement: `[A]` Immutability Triggers

The migration MUST install `prod.reject_mutation()` and MUST attach a `BEFORE UPDATE OR DELETE` trigger to each of the eleven REVOKEd `[A]` tables:

```sql
CREATE OR REPLACE FUNCTION prod.reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  RAISE EXCEPTION 'AUDIT_FIRST_INMUTABLE'; END; $$;
-- Per [A] table: CREATE TRIGGER <t>_inmutable BEFORE UPDATE OR DELETE ON prod.<t>
--   FOR EACH ROW EXECUTE FUNCTION prod.reject_mutation();
```

#### Scenario: Trigger blocks UPDATE under superuser

- GIVEN a `postgres` connection
- WHEN it issues an UPDATE on `prod.log_transaccional`
- THEN the trigger raises `AUDIT_FIRST_INMUTABLE` and the statement aborts.

### Requirement: `[L-S]` Session Guards

The migration MUST install `prod.ls_session_update_guard()` and MUST attach a `BEFORE UPDATE` trigger to `prod.login` and `prod.sesion`. The guard MUST allow UPDATE only on `estado` and `fecha_cierre` (and `timestamp_apertura`/`timestamp_cierre` for `sesion`) AND MUST verify the same transaction inserted a row into `prod.log_transaccional`.

#### Scenario: Session UPDATE with audit row succeeds

- GIVEN a transaction that first INSERTs into `prod.log_transaccional`
- WHEN it then UPDATEs `prod.login.estado` to `cerrado`
- THEN the guard permits the update.

#### Scenario: Session UPDATE without audit row aborts

- GIVEN a transaction that updates `prod.sesion` without first inserting into `prod.log_transaccional`
- WHEN the trigger fires
- THEN it raises an exception.

### Requirement: Monthly Partitioning on Eight High-Volume Tables

The migration MUST call `SELECT partman.create_parent(p_parent_table := 'prod.<t>', p_control := '<date_col>', p_type := 'range', p_interval := '1 month', p_premake := 3)` for: `factura_detalle`, `factura_pagos`, `log_transaccional`, `sync_log`, `sync_queue`, `caja`, `arqueo`, `salidas`. It MUST set `retention = '24 months'` and `automatic_maintenance = 'on'` in `partman.part_config`.

#### Scenario: Partitioning is active after migration

- GIVEN the migration applied successfully
- WHEN `partman.part_config` is queried
- THEN eight rows appear, all with `automatic_maintenance = 'on'`.

### Requirement: Hash-Chain Genesis Rows

The migration MUST insert one genesis row into `prod.log_transaccional` and one into `prod.revocacion_factura` per `uuid_sucursal`, with `hash_anterior = NULL` and `hash_actual = encode(sha256(concat(uuid_sucursal::text, ts_evento::text, payload::text)), 'hex')`.

#### Scenario: Each branch has one genesis row

- GIVEN the migration has applied
- WHEN genesis rows are grouped by `uuid_sucursal`
- THEN every branch UUID appears with count `1`.

### Requirement: Idempotent Catalog and Singleton Seed

The migration MUST seed `tipo_persona`, `tipos_vehiculo`, `tipo_tarifa`, `tipo_subscripciones`, `tipo_sucursal`, the singletons `configuracion_tolerancias` and `configuracion_seguridad`, and the `consumidor_final_default` UUID, using `INSERT ... ON CONFLICT DO NOTHING`.

#### Scenario: First migration applies the catalog seed

- GIVEN an empty `prod.tipo_persona`
- WHEN `alembic upgrade head` finishes
- THEN rows for `natural`, `juridica`, `final` are present.