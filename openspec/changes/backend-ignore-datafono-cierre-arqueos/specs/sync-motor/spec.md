# Delta for `sync-motor` — `backend-ignore-datafono-cierre-arqueos`

## Header

| Field | Value |
|---|---|
| Change | `backend-ignore-datafono-cierre-arqueos` |
| Phase | spec (sdd-spec) |
| Base spec | `openspec/specs/sync-motor/spec.md` (last entry REQ-MOT-001..015) |
| Gap | `apply_row` close path on `session_cycle` strategy passes `valor_final_datafono` from the wire; the datafono dimension is no longer part of the close contract per the operations spec (REQ-OPS-198) |
| Decision ref | D2 default — pass `None` explicitly at the sync boundary |

## MODIFIED Requirements

### Requirement: REQ-MOT-001 — `apply_row` dispatches by `apply_strategy` (close path drops datafono)

**Previously**: `session_cycle` strategy close path forwarded `valor_final_datafono` from the wire payload to `close_session_with_log`. **Now**: the close path MUST pass `valor_final_datafono=None` explicitly, regardless of whether the wire payload contains the key.

The `SyncMotor.apply_row` dispatch table for `apply_strategy='session_cycle'` close leg MUST invoke `repo.session_cycle.close_session_with_log(..., valor_final_datafono=None)` (NOT `payload.get('valor_final_datafono')`). The open leg (`record_login`) is unchanged — `valor_inicial_datafono` is still passed through (the apertura contract is unaffected; see operations spec REQ-OPS-191 for the rationale that only the cierre side reduces). The open leg's behavior preserves the existing `valor_inicial_datafono: 0` default that the UI sends.

#### Scenario: replicated close payload with `valor_final_datafono` key → `None` at dispatch

- **Given** a sync queue entry for `session_cycle` close with `estado` indicator + payload `{"valor_final_datafono": 50000, ...}`
- **When** `apply_row` dispatches
- **Then** the motor MUST call `close_session_with_log(..., valor_final_datafono=None)` (the wire value is dropped, NOT propagated)
- **And** the persisted `prod.sesion.valor_final_datafono` MUST be the column default (the wire value is not reflected).

#### Scenario: open leg unaffected

- **Given** a sync queue entry for `session_cycle` open with `valor_inicial_datafono=0`
- **When** `apply_row` dispatches to `record_login`
- **Then** the motor MUST continue to pass `valor_inicial_datafono=0` through (no change to the open path; the apertura contract is preserved).

## ADDED Requirements

### Requirement: REQ-MOT-016 — Sync layer strips `valor_final_datafono` at the close boundary

The sync motor MUST treat the `valor_final_datafono` key on `session_cycle` close payloads as wire-dead: the value is parsed but never forwarded to the session close helper. This contract is enforced at the dispatch site (`sync/motor/apply_row.py` line 300, close branch) and the persisted `prod.sesion.valor_final_datafono` column MUST NOT reflect the wire value. The hash chain on `prod.log_transaccional` and `prod.revocacion_factura` is unaffected — `valor_final_datafono` is not part of the chain (per AGENTS.md §Sync hash-chain contract).

#### Scenario: wire `valor_final_datafono` value mismatch with persisted column

- **Given** a `prod.sesion` row X closed via sync with wire `valor_final_datafono=50000`
- **When** the close commits
- **Then** `prod.sesion[X].valor_final_datafono` MUST be the column default (`0` or `NULL`)
- **And** `prod.log_transaccional` MUST NOT contain a `valor_final_datafono` key in `datos_nuevos` (the datafono dimension is excluded from the log row's payload too)
- **And** the SHA256 hash chain MUST continue unbroken (the datafono field is not part of `datos_nuevos` schema).

## Cross-References

- `backend/packages/parkos_core/src/parkos_core/sync/motor/apply_row.py` (line 300, close branch — `valor_final_datafono=None` explicit)
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py::close_session_with_log` (signature accepts `valor_final_datafono=None`)
- `openspec/changes/backend-ignore-datafono-cierre-arqueos/specs/operations/spec.md` REQ-OPS-198 (the operations spec mirrors this intent at the API handler level)

## Compliance

- **Hash chain safety**: confirmed via the same `datos->>'seq'` per-row monotonic check used by the existing branch/cloud chain verifier (`job_sync_cloud.hash_chain_verifier_loop`); `valor_final_datafono` is not a chain-bearing field.
- **Forward-only**: no historical payload is migrated; pre-change payloads in `sync_queue` (replayed after the merge) follow the new contract on apply.
- **Cross-tier consistency**: the close contract is identical at the API handler (REQ-OPS-191 / 192), the session close repo (REQ-OPS-198), and the sync motor (REQ-MOT-016). All three layers drop the datafono dimension at the close boundary.

## Test Pinning

- `backend/tests/integration/test_sync_apply_row.py::test_session_cycle_close_passes_datafono_none` (mirrors REQ-OPS-198 pinning)
- `backend/tests/integration/test_sync_apply_row.py::test_session_cycle_open_passes_datafono_through` (regression guard for the open path)
- `backend/tests/integration/test_sync_apply_row.py::test_session_cycle_close_persisted_column_is_default` (covers REQ-MOT-016 Scenario 1)
- `backend/tests/integration/test_sync_apply_row.py::test_session_cycle_close_datos_nuevos_omits_datafono` (covers REQ-MOT-016 Scenario 2)
- `backend/tests/integration/test_sync_chain.py::test_chain_unaffected_by_datafono_drop` (regression for hash-chain safety)
