# Spec: Append-Only Events

## Capability

Provide a strict **append-only INSERT** API surface for the **12 `[A]` source-of-truth tables** that record immutable business facts. `[A]` tables are the persistence backbone of every audit-first guarantee: `REVOKE UPDATE, DELETE ON <table> FROM rol_app` plus a `BEFORE UPDATE OR DELETE` trigger that `RAISE EXCEPTION '<TABLE>_INMUTABLE'` is enforced at the DB; the API helper layer (`parkos_core/repo/append_only.py`) reinforces this by exposing only `append_event()` and an enumerated set of compensating operations (`mark_dispatched` / `mark_failed` / `schedule_retry` on `sync_queue` only — see Scope-04). Corrections are expressed as **new compensating rows** (`factura_pagos.tipo_movimiento = 'reverso'` pointing at `uuid_pago_revertido`) or via the appropriate `[L-W]` workflow table, NEVER as UPDATE or DELETE. The cloud-edge sync engine replicates every replicated `[A]` row via an `AFTER INSERT` trigger that enqueues in `sync_queue` (filtering `WHEN TG_TABLE_NAME <> 'sync_queue'` to prevent recursion).

## Requirements

### REQ-10-A-INSERCION: Single append, never update, never delete
**Given** a tenant-scoped JWT (operador- for branch-originated, admin- for cloud-only `[A]`s, sync-agent- for sync transport endpoints only)
**When** the client calls `POST /api/v1/<resource>` with the table-specific `Create` Pydantic body and an `Idempotency-Key` header
**Then** the system MUST perform a single INSERT (no UPDATE, no DELETE, no TRUNCATE) with `created_at = NOW()`, `created_by = <jwt_subject_uuid>`; return 201 Created with the projected `Read` payload
And the DB-layer trigger permit MUST NOT fire (success path); attempting `session.execute(update(...))` against any of the 12 `[A]` declarative classes outside `append_only.append_event()` MUST be rejected by static AST test (REQ cross-cutting REQ-X4)

### REQ-11-A-CONSULTA: Current-state list with partition-key awareness
**Given** any of the 8 partitioned `[A]` tables (`salidas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `caja`, `arqueo`, `log_transaccional`)
**When** the client calls `GET /api/v1/<resource>?limit=<N>&cursor=<opaque>` without supplying the partition-key range (date range `fecha_*_desde` / `fecha_*_hasta` for date-partitioned tables)
**Then** the system MUST reject with HTTP 400 `{"error": "partition_key_required", "detail": "this resource is monthly-partitioned; supply fecha_desde and fecha_hasta"}`; the partition pruning EXPLAIN plan MUST remain valid

### REQ-12-A-CONSULTA: Single-row read by uuid
**Given** a tenant-scoped READ caller
**When** the client calls `GET /api/v1/<resource>/{uuid}`
**Then** the system MUST respond 200 OK with the projected `Read` payload (no state derivation; `[A]` is the source of truth) or 404 if no such row exists

### REQ-13-A-NO-DELETE: DELETE endpoint is impossible by design
**Given** any FastAPI router bound to an `[A]` resource
**When** the build-time OpenAPI generator runs (`uv run python -m parkos_core.openapi`)
**Then** the emitted `openapi.json` MUST contain zero `delete:` operations for any `[A]` path; same for any `put:` operation that is not the explicitly carved-out `sync_queue` whitelisted-columns endpoint; the CI test `test_no_delete_or_general_put_on_a_tables.py` enforces this
And attempting a raw `DELETE FROM prod.<table>` on any of the 12 tables via a `rol_app` connection MUST raise `<TABLE>_INMUTABLE` (`backend/tests/migrations/test_a_inmutable.py` — 12 fixtures, one per table)

### REQ-14-A-SYNC-FACADE: POST /sync/* routes are the only sync_queue writes from outside
**Given** a `sync-agent-` JWT scoped to a specific `uuid_sucursal` (REQ-X6)
**When** the client POSTs a sync payload through `POST /api/v1/sync/{pair|push|pull}`
**Then** the system MUST accept only on `api_admin` (cloud-side) and `api_sucursal` (branch-side); the three sync routes MUST use `sync-agent-` tokens only (admin or operador → 401); the `sync_queue` table itself accepts INSERT from `append_only.append_event()` (enqueued as a result of any other `[A]` write via the DB `AFTER INSERT` trigger) AND from the `sync_queue.PUT` whitelisted-columns update paths (`mark_dispatched`, `mark_failed`, `schedule_retry`) which only ever update `estado`, `intentos`, `next_retry_at`, `ultimo_error`

### REQ-15-A-COMPENSATION: Reversal / correction flow
**Given** an existing `factura_pagos` row with `tipo_movimiento = 'pago'` and `uuid_pago = P`
**When** the operator POSTs `POST /api/v1/factura-pagos` with `{"tipo_movimiento": "reverso", "uuid_pago_revertido": P, ...}`
**Then** the system MUST validate via Pydantic that `tipo_movimiento='reverso'` requires a non-null `uuid_pago_revertido` (422 otherwise), that `P` exists (404 otherwise), and that no row already exists with `tipo_movimiento='reverso' AND uuid_pago_revertido=P` (DB partial unique index — Q9); on success INSERT the compensating row and respond 201
And the view `V_FACTURA_PAGOS_NETOS` (materialized at query time) MUST subtract the reverso from the original pago for net reporting

### REQ-16-A-HASH-CHAIN: log_transaccional and revocacion_factura chain integrity
**Given** a new INSERT into `log_transaccional` (or `revocacion_factura`) for `uuid_sucursal = S`
**When** the helper `parkos_core/repo/hash_chain.py.append()` runs
**Then** the system MUST read the `MAX(timestamp_evento)` row for S, take its `hash_actual` as the new row's `hash_anterior`, compute `hash_actual = sha256(canonical_json(payload_new) + hash_anterior)` server-side, write both columns atomically with the payload INSERT, refuse client-supplied `hash_*` values (Pydantic rejects them with 422 — Q1 / defense in depth), and on chain break return 500 `HASH_CHAIN_INTEGRITY_VIOLATION` writing a `sync_conflict` cloud-side and an `alerta tipo_alerta='sync_failure'` row

## Scenarios

### SC-10-A-INMUTABLE-DB: DB-level trigger blocks UPDATE / DELETE
1. A `rol_app` connection issues `INSERT INTO prod.factura_pagos (uuid, uuid_factura, ..., tipo_movimiento='pago') VALUES (...)`. Expect success.
2. The same connection issues `UPDATE prod.factura_pagos SET valor = 0 WHERE uuid = ...`. Expect `psycopg2.errors.RaiseException: FACTURA_PAGOS_INMUTABLE`.
3. Same for `DELETE FROM prod.factura_pagos WHERE uuid = ...`. Expect `FACTURA_PAGOS_INMUTABLE`.
4. Same sequence runs for each of the 12 `[A]` tables — 12 passing fixtures.

### SC-11-A-REVERSO: Compensation via new row, partial unique index
1. Operator posts a pago: `POST /api/v1/factura-pagos` → row R1 with `tipo_movimiento='pago'`, `uuid_pago_revertido = null`.
2. Operator posts a reverso: `POST /api/v1/factura-pagos` with `tipo_movimiento='reverso'`, `uuid_pago_revertido=R1.uuid` → row R2 inserted (201).
3. A second attempt to reverse the same R1 fails: DB partial unique index `WHERE tipo_movimiento='reverso' AND uuid_pago_revertido IS NOT NULL` raises `psycopg2.errors.UniqueViolation`; the API helper maps this to 409 `{"error": "duplicate_reverso"}`.
4. `GET /api/v1/facturas/{F}/pagos-netos` (derived endpoint per AD-4) returns the pago MINUS the reverso.

### SC-12-A-HASH-CHAIN: Cloud preserves branch chain on sync-up
1. A branch inserts 3 `log_transaccional` rows in TX order: hashes h0 (genesis `sha256(b"genesis:" + uuid_sucursal)`), h1, h2.
2. Sync worker bundles them in order (per-branch monotonic `seq` in `datos` JSON).
3. Cloud applies them one TX at a time — `hash_chain.append()` reads `MAX(timestamp_evento)` for the same `uuid_sucursal` and accepts each row's `hash_actual` unchanged because the chain was preserved.
4. A simulated out-of-order attempt fails: corrupted row 2 of 3 breaks at the cloud verifier → 500 `HASH_CHAIN_INTEGRITY_VIOLATION`, `sync_conflict` row created cloud-side with both versions snapshot.

### SC-13-A-SYNC-QUEUE-MARK-DISPATCHED: Whitelisted UPDATE on the only mutable `[A]`
1. Background worker inserts a `sync_queue` row via the `AFTER INSERT` of some replicated `[A]` INSERT.
2. Worker calls `PUT /api/v1/sync/queue/{uuid}/mark-dispatched` with `{"intentos": 1, "next_retry_at": null}`. Expect 200; the PUT only updates `estado`, `intentos`, `next_retry_at`, `ultimo_error` (the four whitelisted columns). A fuzz test asserts any other column name in the body returns 422.

### SC-14-A-DOC-RETENTION: fecha_retencion_hasta is computed, not nullable
1. A `factura_electronica` row is INSERTed with `fecha_retencion_hasta = NOW() + INTERVAL '5 years'` (DIAN compliance).
2. A migration test asserts the column carries a NOT NULL constraint on the 8 `[A]` tables that hold DIAN rows (`factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `factura_electronica` is `[L-E]` but carries the retention column too; `revocacion_factura`, `log_transaccional`, `caja`, `arqueo`, `sync_log`, `sync_conflict`).
3. No DELETE is ever issued on these rows — a pre-flight query against an aged `pg_partman` partition confirm the retention worker only moves partitions (DROP CHILD on partitions older than `fecha_retencion_hasta`), not row-level DELETEs.

## Scope — the 12 `[A]` tables by tenant write authority

| Resource | Tenant write authority | Compliance role |
|---|---|---|
| `salidas` | `operador-` (branch) | operational; monthly-partition |
| `factura-detalle`, `factura-impuestos`, `factura-otros-cobros`, `factura-pagos` | `operador-` (branch at emitir time) | DIAN retention |
| `revocacion-factura` | `admin-` (cloud-only); chain-integrity | DIAN evidence |
| `caja`, `arqueo` | `operador-` (branch at turno cut / audit) | operational; monthly-partition |
| `log-transaccional` | `admin-` + `operador-` + `sync-agent-` (append from helper) | compliance; chain-integrity; monthly-partition |
| `sync-queue`, `sync-conflict`, `sync-log` | local-only infra; not propagated | operational |

## Constraints

- **C-A1**: NO `UPDATE` or `DELETE` SQL statement outside `sync_queue`'s four whitelisted columns. Enforced at three layers (API, ORM via helper, DB REVOKE + trigger). The 12 immutability fixtures in `backend/tests/migrations/test_a_inmutable.py` are the unit-level defense.
- **C-A2**: Every `[A]` row carries `(created_at, created_by, sync_status, sync_timestamp, sync_attempts)` — same 8-column audit block as `[V]`. DIAN rows additionally carry `fecha_retencion_hasta`.
- **C-A3**: `hash_anterior` / `hash_actual` are server-computed (NEVER accepted from clients) for `log_transaccional` and `revocacion_factura` only — the helper rejects any client-supplied value with 422.
- **C-A4**: The `AFTER INSERT` outbox trigger filters `WHEN (TG_TABLE_NAME <> 'sync_queue')`; recursion is impossible by construction (test in PR2).
- **C-A5**: Partition-key filter is REQUIRED for monthly-partitioned `[A]` list queries; missing filter → 400 (REQ-11-A-CONSULTA).
- **C-A6**: Correction flows NEVER touch the original row. `anulaciones`, `revocacion_factura`, `reimpresion_ticket` (L-W) and `factura_pagos.tipo_movimiento='reverso'` (A compensation row) are the four allowed correction channels.

## Out of scope

- HTTP DIAN send/transmission (Factus adapter) — separate change.
- Sync worker internals (`job_sync_cloud`, `job_sync_sucursal` transport / ordering / conflict resolution) — uses the ORM helpers in PR2 only.
- `idempotency_keys` is a 50th `[A]`-class table that lives in this change but is documented in `operational.md` REQ-OP-04.

## Dependencies

- `parkos_core/repo/append_only.py` — `append_event()`, the single allowed writer.
- `parkos_core/repo/hash_chain.py` — `append()` for `log_transaccional` and `revocacion_factura`.
- DB migrations created by `bootstrap-monorepo-foundation` (`0001_initial_schema.py` plus 4 incremental migrations) — must install the `REVOKE` and the `BEFORE UPDATE OR DELETE` trigger in the SAME migration per `openspec/config.yaml` `rules.tasks`.
- `pg_partman` partitions for 8 high-volume `[A]` tables.
- ADR references: AD-1, AD-2, AD-3, AD-4. Q9 (partial unique index) and Q12 (V_RESOLUCION_CONSECUTIVO materialized vs live) are closed here.
- Engram topic: `sdd/create-49-table-apis/spec`.
