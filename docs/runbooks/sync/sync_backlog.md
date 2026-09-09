# Runbook: SyncBacklogHigh

**Alert rule**: `SyncBacklogHigh` (`infra/grafana/alerts/sync.yaml`)
**Condition**: `sync_queue_pending_rows > 1000 for 10m`
**Severity**: warning
**Req**: REQ-OPS-008 (`openspec/changes/sync-overhaul/specs/operations.md`)

## What this means

`prod.sync_queue` has more than 1000 pending rows for at least 10 minutes
straight on at least one branch or on cloud. The apply loop (`job_sync_cloud`
or `job_sync_sucursal`) is not draining the queue as fast as new rows are
enqueued.

## Likely causes

- The worker process is down, crash-looping, or stuck (check container/host
  health first).
- A downstream dependency (DB, DIAN provider, JWT issuer) is slow or
  unreachable, so each apply cycle takes far longer than usual.
- A single poison row is failing repeatedly and blocking the batch (check
  `operaciones_fallidas` in the most recent `prod.sync_log` row for the
  affected `uuid_sucursal`).
- Sudden volume spike unrelated to a defect (e.g. bulk import, backfill).

## Diagnosis

1. Confirm the worker is actually running and its last heartbeat log line
   (`event="sync_sucursal.heartbeat_failed"` or `sync_cloud.apply_loop_failed`)
   is not present in the recent logs.
2. `SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente'` per
   `uuid_sucursal` (`openspec/scripts/check_drain.py` runs the cloud-wide
   version of this query).
3. Check `apply_batch_limit` / `sync_batch_size` — an artificially small
   batch size can cause a backlog under normal load.
4. Look for a single row stuck at high `intentos` in `sync_queue`.

## Resolution

- Restart the affected worker if it is unhealthy.
- If a single poison row is blocking the batch, resolve or manually
  mark-failed that row per the existing conflict-resolution runbook, then
  let the batch continue.
- If it is a genuine volume spike, temporarily raise `apply_batch_limit`
  and monitor `sync_apply_total` for recovery.

## Escalation

If the backlog does not recede after worker restart + poison-row removal,
escalate to the on-call engineer with the `uuid_sucursal`, the queue depth
over time, and the worker's recent log lines.
