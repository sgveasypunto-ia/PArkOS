# Runbook: SyncConflictRateHigh

**Alert rule**: `SyncConflictRateHigh` (`infra/grafana/alerts/sync.yaml`)
**Condition**: `rate(sync_apply_total{status="CONFLICT"}[1h]) / rate(sync_apply_total[1h]) > 0.005`
**Severity**: warning
**Req**: REQ-OPS-008 (`openspec/changes/sync-overhaul/specs/operations.md`)

## What this means

More than 0.5% of applied rows over the last hour resolved as `CONFLICT`
(`ApplyResult.status`, `motor/apply_result.py`) instead of `APPLIED`. Most
conflicts are informational (`IdentityReconciler`'s `divergent` case emits
one, never blocks) — a sustained high rate signals either a genuine
concurrent-edit hotspot or a misbehaving client repeatedly resubmitting
stale data.

## Likely causes

- Two branches (or a branch and cloud) are editing the same natural-key
  entity concurrently (e.g. the same `clientes` row) faster than
  replication settles.
- A client integration is resubmitting an outdated snapshot in a loop.
- A clock-skew issue is making `vigente_desde` comparisons behave
  unexpectedly across branches.

## Diagnosis

1. Query `prod.sync_conflict` for the affected time window, grouped by
   `tabla` and `politica`, to find the dominant table/policy combination.
2. Cross-reference `uuid_registro` values that appear more than once — a
   repeating `uuid_registro` strongly suggests a retry loop rather than
   organic concurrent edits.
3. Check whether the spike correlates with a specific `uuid_sucursal`
   (client-side bug) or is spread across branches (systemic issue).

## Resolution

- If it is a retry loop, identify and fix (or block) the offending client.
- If it is organic concurrent editing, review `IdentityReconciler`'s
  classification for the affected table and confirm the auto-resolution
  (`noop`/`forward`/`historical`) is landing correctly; escalate any
  `divergent` case that looks wrong.
- No manual DB conflict rows should ever be updated or deleted directly —
  `sync_conflict` is append-only ([A] contract).

## Escalation

If the rate stays elevated after ruling out a retry loop, escalate with the
`tabla`/`politica` breakdown and a sample of the affected
`sync_conflict.uuid_registro` values.
