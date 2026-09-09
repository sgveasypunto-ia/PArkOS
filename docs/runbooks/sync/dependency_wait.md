# Runbook: FEProviderError

> **Filename note.** This file is named `dependency_wait.md` per
> `tasks.md` T-PR13-005's literal 8-filename list, but documents the
> `FEProviderError` alert rule per T-PR13-004/REQ-OPS-008's literal
> 8-rule-name list. The two lists do not pair up 1:1 by name for this rule
> (`dependency_wait` matches design.md §9's now-superseded
> `DependencyWaitGrowing` alert name, not `FEProviderError`). See the PR13
> apply report for the recommended follow-up: reconcile the filename (or
> the rule name) so this mismatch does not persist past this PR.

**Alert rule**: `FEProviderError` (`infra/grafana/alerts/sync.yaml`)
**Condition**: `rate(alerta_total{tipo_alerta="fe_provider_error"}[1h]) > 0`
**tipo_alerta**: `fe_provider_error` (`prod.alert_types`, seeded T-PR8-002)
**Severity**: critical
**Req**: REQ-OPS-008 (`openspec/changes/sync-overhaul/specs/operations.md`),
addendum #5 / REQ-OPS-016 (generic identifiers only — never the
third-party provider's name)

## What this means

The electronic-invoicing (FE) provider exchange exhausted its retry
budget for at least one document. This is distinct from a single
`dian_rechazada`/`dian_timeout`/`dian_error` outcome — `fe_provider_error`
fires only once the dispatcher has given up retrying, i.e. the document is
now stuck needing manual intervention.

## Likely causes

- The FE provider is having an extended outage.
- Credentials/certificate for the FE provider integration expired.
- A malformed UBL document is being rejected on every retry attempt
  (a genuine document-content defect, not a transient provider issue).

## Diagnosis

1. Find the `alerta` row(s) with `tipo_alerta='fe_provider_error'` for the
   affected time window and resolve the linked invoice(s).
2. Check the dispatcher's own logs for the terminal poll outcome that
   triggered exhaustion (`dian/cloud/dispatcher.py`).
3. Confirm whether the provider's status page reports an outage, or the
   error is specific to one document (malformed content).

## Resolution

- Provider outage: no action beyond monitoring; the invoice remains
  correctly recorded locally (`factura_electronica` state is unaffected —
  the sync-overhaul canon never marks a document "preliminar" pending a
  sync-back gate).
- Credential/cert issue: rotate and redeploy, then manually re-trigger
  the exhausted document(s).
- Malformed document: fix the UBL serialization defect, then re-trigger.

## Escalation

Critical severity — this blocks invoice legalization. Escalate immediately
if more than one document is affected or the provider outage exceeds its
documented SLA.
