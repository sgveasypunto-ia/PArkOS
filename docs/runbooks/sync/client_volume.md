# Runbook: FENumberingExhausted

> **Filename note.** This file is named `client_volume.md` per
> `tasks.md` T-PR13-005's literal 8-filename list, but documents the
> `FENumberingExhausted` alert rule per T-PR13-004/REQ-OPS-008's literal
> 8-rule-name list. The two lists do not pair up 1:1 by name for this rule
> (`client_volume` matches design.md §9's now-superseded
> `ClientMasterVolumeHigh` alert name, not `FENumberingExhausted`). See the
> PR13 apply report for the recommended follow-up: reconcile the filename
> (or the rule name) so this mismatch does not persist past this PR.

**Alert rule**: `FENumberingExhausted` (`infra/grafana/alerts/sync.yaml`)
**Condition**: `rate(alerta_total{tipo_alerta="fe_numbering_exhausted"}[1h]) > 0`
**tipo_alerta**: `fe_numbering_exhausted` (`prod.alert_types`, seeded T-PR8-002)
**Severity**: critical
**Req**: REQ-OPS-008 (`openspec/changes/sync-overhaul/specs/operations.md`),
addendum #5 / REQ-OPS-016 (generic identifiers only — never the
third-party provider's name)

## What this means

A branch's authorized invoice numbering range (`resolucion_facturacion`)
has been exhausted — the branch-local numbering rule (AGENTS.md §9.5
correction, PR14) can no longer mint a new consecutive number in that
range. Every subsequent invoice attempt on that branch will fail until a
new range is authorized.

## Likely causes

- Genuine high invoice volume consumed the authorized range faster than
  expected (a capacity-planning gap, not a defect).
- A resolution-range collision was mis-provisioned (two branches or two
  ranges overlapping), exhausting the range early.
- A bug generating duplicate/skipped consecutive numbers within the range
  (should be caught by the range-validation control, risk-register item).

## Diagnosis

1. Confirm the exhausted range's `numero_desde`/`numero_hasta` (or
   equivalent) against how many invoices were actually issued in that
   range for the affected branch.
2. Check for a resolution-range collision with another branch's active
   range.
3. Rule out a numbering-generation defect (duplicate/skip) before assuming
   pure volume exhaustion.

## Resolution

- Pure volume exhaustion: request and provision a new authorized
  numbering range for the branch as soon as possible — this blocks
  invoicing entirely until resolved.
- Collision: correct the provisioned ranges so they no longer overlap.
- Generation defect: fix the numbering bug, then re-provision a clean
  range.

## Escalation

Critical severity — a branch cannot legally emit invoices while its range
is exhausted. Escalate immediately to whoever owns numbering-range
provisioning.
