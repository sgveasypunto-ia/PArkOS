# ADR 003 — `depends_on` dependency ordering and a single escalation path

> **Status**: Accepted
> **Deciders**: sdd-design for `sync-overhaul`
> **Date**: 2026-09-08
> **Proposal ref**: `proposal.md` **D18** (generalizes D7 + D15), §6.4 (the dependency graph),
> §12 R12 / R13 / R19 / R22
> **Design ref**: `design.md` §2 Issue #7, §2 Issue #8, §5 `apply_batch`, §7.6, §11 rules 6-7 and 11
> **Supersedes in part**: D7 (`[L-W]` `validate_parent_chain`) and D15 (`uuid_padre` buffer) — both
> survive as the special case of a general rule, not as separate mechanisms

## Why this needs its own ADR

The two decisions recorded here are the ones most likely to be silently reverted by a future change,
because each looks like a defect to a reader who has not seen the reasoning:

1. `priority` exists on every catalog entry, is populated, and is **forbidden** from ordering rows
   across tables. A maintainer optimizing the drain will reach for it.
2. A `RETRY(parent_missing)` outcome causes the sender to call `repo.sync_queue.mark_success`.
   Marking a row that was *not applied* as a success reads like a bug on first contact.

ADR-001 and ADR-002 exist for an enum and a table count. A mechanism whose correct behaviour is
counter-intuitive deserves at least the same durability.

## Context

The ER-conformance review's finding **C4** was that the change had **no FK application order** for
`branch_to_cloud` traffic. Concretely, at the time of the review:

- The only wait mechanism was a buffer keyed on the `[L-W]` self-chain column `uuid_padre`, covering
  6 tables.
- Nine parent/child FK pairs on the invoicing path had no protection at all: `salidas → ingreso`;
  `facturas → ingreso`, `salidas`; `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`,
  `factura_pagos → facturas`; `factura_pagos → sesion`; `arqueo → sesion`;
  `revocacion_factura → factura_electronica`.
- The `[L-E]` and `[A]` apply policy was "always APPLIED", which has **no** `RETRY(parent_missing)`
  path — so a child arriving before its parent produced a raw FK violation, not a resolvable
  condition. This is the DIAN critical path, and it is where children arrive first most often.
- `priority` actively ordered children **ahead of** parents: its legacy values (inherited from
  trigger insertion order) gave `factura_pagos` 5 and `facturas` 1, and the drain is
  `prioridad DESC`.
- Two escalation paths coexisted without reconciliation: re-enqueue into `sync_queue` at
  `intentos >= 6`, and the buffer's TTL sweep.

Dependency order is not a `branch_to_cloud`-only concern. After D8-rev a freshly paired branch starts
with an empty catalog set, so the initial `cloud_to_branch` backfill must apply parents first or
every child fails — which is the failure class that motivated the whole amendment.

## Decision

### Part 1 — `depends_on` is the only cross-table ordering mechanism

Each `SyncCatalogEntry` declares `depends_on: tuple[str, ...]` — every table it holds a **mandatory**
(NOT NULL) FK to that is itself a `SyncCatalog` entry. Batches are applied in **topological order
over `depends_on`**, and any missing declared parent yields `RETRY(parent_missing)`.

Four properties make this a mechanism rather than a list:

- **`depends_on` is CI-derived, not hand-maintained.** `check_catalog_drift.py` computes the expected
  set from the ER relationship block and fails the build on drift. A hand-edited value cannot rot the
  way the direction values did.
- **Mandatory FKs only.** Optional (nullable) FKs are structurally excluded, and a nullable FK
  appearing in any `depends_on` **fails the build**.
- **Self-chains are excluded from the sort.** The seven self-referential FKs are marked
  `self_chain=True` and resolved by `ValidateParentChain` through the per-table
  `parent_fk_column`. CI asserts the remaining graph is a **DAG**; a cycle raises at import time.
- **`priority` is demoted to a FIFO tie-break within one topological level.** Using it for
  cross-table ordering is forbidden, and CI asserts it is referenced nowhere in the ordering path.

**Batch selection is not touched.** The mechanism composes with the existing selection in this exact
order: (1) select via `repo/sync_queue.py::list_pending` — `prioridad DESC, intentos ASC,
created_at ASC LIMIT 100` — unchanged, not one line; (2) topologically order *within* the selected
batch; (3) buffer any row whose parent is neither local nor earlier in the same batch.

**Parent validation runs before persistence.** The hook lifecycle becomes
`validate_parent → pre_insert → repo call → post_insert → chain_extend`. Previously it ran after the
repo call, which cannot prevent an FK violation — only observe one.

### Part 2 — `RETRY(parent_missing)` is delivered-and-deferred; one escalation path

The **receiving** side buffers, because it is the only side that can see whether the parent exists.
`RETRY(parent_missing)` is an *accepted* outcome on the wire, not a failure:

| `ApplyResult.status` | `/sync/events` per-row status | Sender action |
|---|---|---|
| `APPLIED` | `applied` | `mark_success` |
| `CONFLICT` | `conflict` | `mark_success` (delivered; a `sync_conflict` row exists at the receiver) |
| `RETRY` (`parent_missing`) | `retry_parent_missing` | **`mark_success`** — delivered; the wait now belongs to the receiver's buffer |
| transport / HTTP failure | — | `mark_failed` → `next_retry_delay(intentos)` |

Consequently: the buffer owns the wait, its TTL sweep owns the timeout, `sync_queue` is **never**
re-enqueued for a dependency wait, and `intentos` is **never** incremented for one. The sweep is the
single escalation, emitting `alerta tipo_alerta='orphan_workflow_chain'`, with the
`sync_dependency_wait` gauge alerting before the TTL.

Draining is a **bounded iterative work queue**, not recursion inside the applying transaction: when a
parent applies, `hook_post_insert` drains children keyed on `(tabla_padre, uuid_padre)`, capped per
cycle at the batch size and per row at the DAG depth.

## Rationale

1. **`intentos` and `next_retry_at` carry transport-failure semantics.** A row deferred for a missing
   parent was *delivered successfully*; nothing about the transport failed, and the sender cannot
   influence the outcome by resending. Counting it as a transport failure is the same defect class as
   D21's `unknown_table → mark_failed`: it inflates the failure-rate metric and buries real failures
   underneath it. That metric is a stage-3 cutover gate (conflict rate < 0.5 %, backlog < 1000), so
   polluting it does not merely mislead an operator — it can block or falsely pass a gate.
2. **Two clocks on one row is a correctness problem, not just untidiness.** With both paths live, a
   delivered row waiting on a parent would also be counting down `sync_queue` retries, and could
   exhaust its transport retry budget and reach `FALLIDO_PERMANENTE` while the buffer still holds it
   legitimately. The same wait would then alert twice, from two subsystems, with two different
   timeouts.
3. **Topological order beats a hand-tuned priority because it is derivable.** The legacy `priority`
   values were not arbitrary — they were a faithful encoding of *trigger insertion order*, which has
   no relationship to FK dependency. Any value hand-assigned to express dependency has the same
   fragility: it is a claim about the FK graph stored somewhere the FK graph is not. `depends_on`
   derived from the ER and asserted in CI is a claim the build can check.
4. **Mandatory-only is what makes R22 correct by construction.** A subscribed vehicle presenting at a
   non-selling branch legitimately finds no subscription row, because
   `broadcast_policy=subscription` sends it only to the selling branch. Since
   `ingreso.uuid_subscripcion_cliente` is optional, it can never enter `ingreso`'s `depends_on`, so
   the miss can never produce `RETRY(parent_missing)`. Had the rule been "all declared FKs", every
   occasional entry at a non-selling branch would buffer against a parent that will never arrive, and
   the TTL sweep would raise a false `orphan_workflow_chain` for ordinary business traffic. The
   correct behaviour falls out of the rule instead of needing a special case.
5. **A cycle is a programming error, not a runtime condition.** Raising at import time turns a
   would-be production deadlock into a failed build. Best-effort application of a cyclic graph would
   silently violate FK order, which is the defect being fixed.
6. **Direction-agnostic by design.** The same mechanism orders the first-pairing backfill, where
   `usuarios` / `permisos` / `permisos_usuario` sit at the root so offline login becomes available as
   early as possible (R9), and `catalog_backfill_complete{uuid_sucursal}` cannot reach 1 while any
   parent is unresolved (R-D8).

## Alternatives considered

| Option | Tradeoff | Decision |
|---|---|---|
| `depends_on` + topological sort within the selected batch, reusing the one existing buffer | One ordering mechanism, one wait mechanism, one escalation path; CI-derivable from the ER | **CHOSEN** |
| Keep `priority` as the cross-table ordering mechanism | Free, and demonstrably wrong: it currently orders `factura_pagos` (5) ahead of `facturas` (1) | Rejected |
| Replace batch selection with a global topological drain | Would discard the ratified `prioridad DESC, intentos ASC, created_at ASC LIMIT 100` selection, unbound the batch, and starve high-priority rows behind a deep dependency chain | Rejected |
| A second buffer table for non-`[L-W]` waits | Two tables, two TTLs, two sweeps, two escalation paths — the exact defect this ADR removes | Rejected |
| Keep `RETRY(parent_missing)` as a `sync_queue` failure with re-enqueue at `intentos >= 6` | Requires no wire-contract change, but keeps two clocks on one row and pollutes the gate metric | Rejected |
| Let the FK violation happen and retry the raw error | Zero new mechanism, but an FK violation aborts the applying transaction, so an unrelated sibling row in the same batch is lost, and the error is indistinguishable from real corruption | Rejected |
| Order by an explicit integer `apply_level` per entry | Simpler than a sort, but it is a second hand-maintained encoding of the FK graph — the `priority` mistake with a new name | Rejected |

## Consequences

### Positive

- The nine unprotected parent/child pairs on the invoicing path are covered by the same mechanism as
  the 6 `[L-W]` self-chains; D7 and D15 become special cases of one rule.
- The transport failure rate becomes an honest signal again, so the stage-3 gate measures what it
  claims to.
- `sync_deferred_total{tabla, tabla_padre}` and `sync_dependency_wait{tabla, tabla_padre}` give an
  operator the dependency picture directly, instead of inferring it from retry counts.
- The first-pairing backfill and steady-state replication share one ordering implementation.
- A `depends_on` value that drifts from the ER fails the build, so this fix cannot rot the way the
  direction values did.

### Negative

- **The wire contract gains a per-row status.** `/sync/events` responses must carry
  `retry_parent_missing`, and both protocol versions must agree on it during the 14-day dual-protocol
  grace window.
- **`mark_success` on a non-applied row reads like a bug.** This is the specific hazard this ADR
  exists to guard. Mitigation: the status name is explicit at the call site, `sync_deferred_total`
  counts these separately from `applied`, and `test_parent_missing_buffer_drain` asserts `intentos`
  is unchanged after a deferral.
- **`priority` remains a live field with a narrow legal use**, which invites misuse. Mitigation:
  drift-check rule 11 asserts it is absent from the ordering path.
- **Topological sorting adds per-batch CPU cost.** Bounded and small: the graph is static (computed
  once at import from `depends_on`), the sort runs over at most 100 rows across ~46 nodes, and levels
  are precomputed rather than re-derived per batch.
- **A deep chain can require several cycles to fully drain.** Accepted: the alternative is an
  unbounded drain inside one transaction, and the `sync_dependency_wait` gauge makes the progress
  observable.

## Tasks affected

PR mapping per `design.md` §13; task IDs are owned by `sdd-tasks`.

- **PR3** — `catalog/dependency_graph.py` (graph build, precomputed topological levels, DAG assertion
  at import) + `motor/dependency_orderer.py` + the `check_catalog_drift.py` rules for
  `depends_on` ↔ ER, nullable-FK rejection, DAG, and the `priority` absence check.
- **PR4** — `hooks/impls/validate_parent_chain.py` bound to every entry with non-empty `depends_on`,
  using `spec.parent_fk_column` for self-chains; lifecycle reordered so it precedes persistence.
- **PR8** — `motor/dependency_buffer.py`: insert, bounded iterative drain, TTL sweep, single
  escalation to `orphan_workflow_chain`; `0009` provides the generic `tabla_padre` / `uuid_padre`
  columns and the partial index.
- **PR11 / PR12** — the `retry_parent_missing` per-row wire status on both sides, and the sender's
  `mark_success` handling.
- **PR12** — `cutover/backfill.py` applies `cloud_to_branch` entries in topological level order and
  drives `catalog_backfill_complete`.
- **PR13** — `sync_deferred_total` counter, `sync_dependency_wait` gauge, `DependencyWaitGrowing`
  alert rule.

## Validation

- `tests/unit/test_dependency_graph.py::test_depends_on_matches_er` — each entry's `depends_on`
  equals the ER's mandatory-FK parent set for that entity.
- `tests/unit/test_dependency_graph.py::test_nullable_fk_rejected` — a nullable FK in any
  `depends_on` fails; explicitly asserts `"subscripciones_cliente" not in ingreso.depends_on` (R22).
- `tests/unit/test_dependency_graph.py::test_graph_is_dag_after_self_edges` — the seven `self_chain`
  edges are excluded and the remainder is acyclic; an injected cycle raises at import.
- `tests/unit/test_dependency_orderer.py::test_parents_before_children` — `facturas` precedes
  `factura_pagos` despite the legacy `priority` values (R12).
- `tests/unit/test_dependency_orderer.py::test_batch_selection_unchanged` — the selection query is
  byte-identical to `repo/sync_queue.py::list_pending`'s ordering and limit.
- `tests/integration/test_parent_missing_buffer_drain.py` — a child arriving first is buffered, the
  sender's row is `exitoso` with **`intentos` unchanged**, the child applies when the parent lands,
  and the buffer row reaches `estado='aplicado'`.
- `tests/integration/test_r22_non_selling_branch.py` — an entry at a non-selling branch produces 0
  `sync_conflict` rows, 0 alerts, and 0 buffer rows.
- `tests/integration/test_buffer_ttl_escalation.py` — an unresolved parent past TTL emits exactly
  **one** `orphan_workflow_chain` alert and no `sync_queue` re-enqueue.
- `python openspec/scripts/check_catalog_drift.py` exits 0 with rules 6, 7, and 11 active.

## References

- `proposal.md` D18 (with D7 / D15 as its special cases), §6.4, §7 `apply_batch` and
  `resolve_conflict`, §12 R12 / R13 / R19 / R22.
- `design.md` §2 Issue #7 and Issue #8, §5, §7.2, §7.6, §7.7, §11.
- ER-conformance review finding **C4** — no FK application order for `branch_to_cloud`; and **A6** —
  `parent_fk_column` missing from the entry while the six `[L-W]` tables use differently named parent
  columns.
- `repo/sync_queue.py` — `BACKOFF_SCHEDULE`, `next_retry_delay`, `list_pending`, and the
  4-column update whitelist this ADR deliberately does not touch.
