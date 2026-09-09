# Runbook: CatalogBackfillIncomplete

**Alert rule**: `CatalogBackfillIncomplete` (`infra/grafana/alerts/sync.yaml`)
**Condition**: `catalog_backfill_complete{uuid_sucursal} == 0 for 48h after pairing`
**Severity**: warning
**Req**: REQ-OPS-008 (`openspec/changes/sync-overhaul/specs/operations.md`), R-D8

## What this means

`catalog_backfill_complete{uuid_sucursal}`
(`sync/observability/metrics.py`, T-PR12-008) has stayed `0` for 48 hours
after a branch was paired. This gauge only reaches `1` once EVERY
`cloud_to_branch`/`bidirectional` catalog entry has completed its initial
topological backfill with zero unresolved parents for that branch — this
is the SAME gauge the R-D8 stage-4 cutover gate reads
(`cutover-migration.md` REQ-CUT-006). A stalled backfill blocks that
branch's cutover progression.

## Likely causes

- One or more catalog entries never finished their initial backfill
  (buffered on a missing parent that itself never backfilled).
- The backfill job crashed partway through and was never resumed.
- The branch went offline mid-backfill and has not reconnected.

## Diagnosis

1. Identify which catalog entries are still incomplete for the affected
   `uuid_sucursal` (the backfill runner tracks per-entry topological-level
   completion — see `sync/cutover/backfill.py`).
2. For each incomplete entry, check whether it is itself blocked on a
   `RETRY(parent_missing)` — cross-reference with `OrphanWorkflowChain`.
3. Confirm the branch is online and its pull loop is actually running.

## Resolution

- If blocked on a parent, resolve the parent's backfill first (topological
  order matters — do not attempt to force a child entry's completion
  bypassing its declared parent).
- If the backfill job crashed, re-run it for the affected branch; it is
  designed to resume from the last completed topological level.
- Do NOT manually flip `catalog_backfill_complete` — it must reflect the
  real backfill state, since the R-D8 stage-4 gate trusts it directly.

## Escalation

Escalate before advancing this branch through any cutover stage while this
alert is firing — R-D8 explicitly requires this gauge, not a hardcoded
pass, to gate stage 4.
