# Runbook: HashChainBreak

**Alert rule**: `HashChainBreak` (`infra/grafana/alerts/sync.yaml`)
**Condition**: `sync_chain_anomalies_total > 0 for 5m`
**tipo_alerta**: `hash_chain_anomaly` (`prod.alert_types`, seeded T-PR8-002)
**Severity**: critical
**Req**: REQ-OPS-008 (`openspec/changes/sync-overhaul/specs/operations.md`)

## What this means

The hash-chain verifier (`jobs/sync_cloud.py::_verify_hash_chains_once` /
`_verify_revocacion_factura_chain_once`) detected a broken `log_transaccional`
or `revocacion_factura` hash chain for a `uuid_sucursal`. This is a
**data-integrity** alert, not a transient sync hiccup — the append-only
audit trail no longer verifies.

## Likely causes

- A row was inserted outside the canonical `repo.hash_chain.append` /
  `repo.versioned.close_and_insert` path (bypassing the chain-extension
  logic), most likely through a raw `session.execute(insert(...))` that the
  AST guard (`tests/static/test_no_raw_dml_on_a_tables.py`) should already
  reject in code review.
- A restore/rollback operation reinserted historical rows without
  recomputing the chain.
- Corrupted `hash_anterior`/`hash_actual` values from a manual DB
  intervention.

## Diagnosis

1. The verifier's `_handle_chain_break` already wrote an `alerta` row
   (`tipo_alerta="hash_chain_anomaly"`) and a `sync_conflict` row
   (`politica="chain_break"`, `resolucion="manual"`) for the affected
   `uuid_sucursal`/`tabla` — start there.
2. Walk `log_transaccional` (or `revocacion_factura`) for the affected
   `uuid_sucursal` ordered by `timestamp_evento`, recomputing
   `hash_actual = sha256(hash_anterior || row_payload)` to find exactly
   where the chain diverges.
3. Check for any deploy or migration around the divergence timestamp that
   might have touched the table directly.

## Resolution

This is a **manual-resolution-only** alert (`sync_conflict.resolucion =
"manual"`) — there is no automated remediation. A maintainer must:

- Confirm whether the divergent row is legitimate (and the chain needs a
  documented, signed-off re-genesis) or is evidence of an integrity
  violation requiring incident response.
- Never attempt to "fix" the chain with a raw UPDATE — `log_transaccional`
  and `revocacion_factura` are append-only [A] tables with a
  `BEFORE UPDATE OR DELETE` trigger; any fix goes through a new,
  documented append.

## Escalation

Treat as a security/data-integrity incident. Escalate immediately with the
`uuid_sucursal`, `tabla`, and the exact row range where the chain
diverges.
