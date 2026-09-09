# Runbook: BranchImportError

**Alert rule**: `BranchImportError` (`infra/grafana/alerts/sync.yaml`)
**Condition**: `rate(sync_import_errors_total[5m]) > 0`
**Severity**: critical
**Req**: REQ-OPS-008 (`openspec/changes/sync-overhaul/specs/operations.md`)

## What this means

The branch worker (`job_sync_sucursal`) is failing to import (apply) rows
pulled from cloud. Unlike a routine `CONFLICT` outcome, this counts a real
apply-time error — the row could not be persisted at all.

## Likely causes

- JWT expiry/rotation failure preventing authenticated pulls — often
  correlates with `branch_offline_reauth_required` (`prod.alert_types`)
  when the branch has been offline long enough that its short-lived JWT
  needs re-issuance.
- A schema mismatch between the pulled payload and the branch's applied
  migrations (branch running behind on `alembic upgrade`).
- A hook raising an unexpected exception (`hook_validate_parent`,
  `hook_pre_insert`) instead of returning a structured `HookResult`.
- Local DB connectivity or disk-space issue on the branch.

## Diagnosis

1. Check the branch's own log stream for `sync_sucursal.pull_apply_batch_failed`
   and the attached `error` field — this names the underlying exception.
2. Confirm the branch's JWT is valid and not stuck in a rotation failure
   loop (`sync_sucursal.rotating_jwt_after_401`).
3. Confirm `alembic current` on the branch matches the expected revision
   for the deployed `parkos-core` version.

## Resolution

- If it's a JWT/auth issue, follow the branch re-pairing procedure
  (`branch_offline_reauth_required`'s resolution path).
- If it's a schema drift, apply the missing migration(s) on the branch.
- If it's a hook exception, treat as a code defect — file it, do not
  silently retry indefinitely (`sync_import_errors_total` should stop
  incrementing once the underlying defect is fixed).

## Escalation

Critical severity — escalate immediately if the branch cannot apply ANY
rows (full import failure), since that blocks the branch's whole
replication stream, not just one row.
