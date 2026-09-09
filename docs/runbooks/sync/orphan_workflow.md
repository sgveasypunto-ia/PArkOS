# Runbook: OrphanWorkflowChain

**Alert rule**: `OrphanWorkflowChain` (`infra/grafana/alerts/sync.yaml`)
**Condition**: `rate(orphan_workflow_chain_alerts_total[1h]) > 0`
**tipo_alerta**: `orphan_workflow_chain` (`prod.alert_types`, seeded T-PR8-002)
**Severity**: warning
**Req**: REQ-OPS-008 (`openspec/changes/sync-overhaul/specs/operations.md`)

## What this means

The dependency-buffer TTL sweep (`sync/motor/dependency_buffer.py`) found a
row in `prod.sync_queue_lw_buffer` whose declared parent
(`tabla_padre`/`uuid_padre`) never arrived before the buffer entry's
`expires_at`. The row is a `RETRY(parent_missing)` outcome (D18) that aged
out — it is buffered-and-delivered on the sender side, so no data was
lost, but the dependent row is stuck waiting indefinitely.

## Likely causes

- The parent row's replication direction/`broadcast_policy` genuinely never
  sends it to this branch (a catalog drift bug — should be caught by
  `check_catalog_drift.py` before reaching this alert).
- The parent row failed to apply on this branch for an unrelated reason
  (e.g. a prior conflict or worker outage) and was never retried.
  is the parent row itself stuck in `sync_queue` for the same branch?
- Clock/ordering issue: the child arrived and was buffered before the
  parent's batch was even sent.

## Diagnosis

1. Query `prod.sync_queue_lw_buffer` for rows with `estado='pendiente'`
   and `expires_at < now()` for the affected branch.
2. For each, look up whether the declared parent (`tabla_padre`,
   `uuid_padre`) exists at all for that `uuid_sucursal`.
3. If the parent never arrived, check the parent's own `sync_queue`/
   `sync_conflict` history for that branch to see why.

## Resolution

- If the parent simply hasn't synced yet, force a re-sync of the parent
  table for the affected branch, then re-drive the buffer sweep
  (`fn_enqueue_sync_catalog` picks it up automatically once the parent
  lands).
- If the parent genuinely will never arrive (catalog/direction bug), file
  it as a catalog-drift defect — do not manually delete or "resolve" the
  buffered row; `sync_queue_lw_buffer` is append-only ([A]).

## Escalation

Escalate to the sync-catalog owner if the root cause is a
direction/`broadcast_policy` mismatch rather than a transient outage.
