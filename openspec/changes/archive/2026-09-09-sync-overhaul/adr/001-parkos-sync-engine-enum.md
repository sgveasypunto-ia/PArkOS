# ADR 001 — `PARKOS_SYNC_ENGINE` enum values

> **Status**: Accepted — **decision reversed by amendment 2026-09-08 (ER-alignment correction pass)**
> **Deciders**: sdd-tasks for `sync-overhaul` (original); sdd-design for `sync-overhaul` (amendment)
> **Date**: 2026-09-08 (original) · amended 2026-09-08
> **Spec ref**: `specs/sync-motor.md` REQ-MOT-011 + `specs/cutover-migration.md` REQ-CUT-001
> **Design ref**: `design.md` §2 Issue #3, §8 Cutover Mechanics, §13 Delivery Plan
> **Proposal ref**: `proposal.md` **D22** — the ratifying decision

## Amendment note (2026-09-08)

The original decision picked the **design's** behaviour-flavoured enum
(`legacy | catalog_read | catalog_dual | catalog_only | catalog_lite`) and instructed the two spec
files to be amended to match. **That decision is reversed.**

The amended proposal ratifies the **service-flavoured** enum in **D22**:

```
legacy | catalog_admin | catalog_dian | catalog | catalog_branch
```

This ADR is amended in place. The original Context, Decision, Rationale, and Consequences are kept
below inside `Superseded` blocks so the reversal is auditable; the live Decision, Consequences,
Tasks, and Validation sections are rewritten. The ambiguity between the two candidate enums is
closed: there is exactly one enum, and the behaviour-flavoured variant is **withdrawn**.

## Context

`PARKOS_SYNC_ENGINE` is the single feature flag governing the cutover. It is read by Python workers
at the top of every 60 s loop tick (`parkos_core/runtime/engine_flag.py::get_engine()`), validated
against the enum on first read, and cached thereafter. `infra/docker/entrypoint.sh` only forwards it.
Setting it to `legacy` is the kill switch (D12).

The cutover it governs is staged **by service**, not by engine behaviour (D13, and the stage table in
`design.md` §8):

| Stage | Service | Value |
|---|---|---|
| 0 | all | `legacy` |
| 1 | `api_admin` | `catalog_admin` |
| 2 | `dian/cloud/dispatcher` | `catalog_dian` |
| 3 | `jobs/sync_cloud` | `catalog` |
| 4-5 | branch workers | `catalog_branch` |

Two candidate enums existed across this change's artifacts. `specs/sync-motor.md` REQ-MOT-011 and
`specs/cutover-migration.md` REQ-CUT-001 carried the service-flavoured values; `design.md` §2 and
this ADR carried a behaviour-flavoured set. The split was recorded as finding A5 of the ER-conformance
review and is what this amendment closes.

<details>
<summary><b>Superseded — original Context (kept for history)</b></summary>

> `sync-motor.md` REQ-MOT-011 enumerated `PARKOS_SYNC_ENGINE` as five values:
>
> | Spec value | Spec behavior |
> |---|---|
> | `legacy` | Dispatch to legacy applier; kill switch. |
> | `catalog_admin` | Catalog-driven, `api_admin` only. |
> | `catalog_dian` | Catalog-driven, DIAN dispatcher only. |
> | `catalog` | Catalog-driven, all 47 entries. |
> | `catalog_branch` | Catalog-driven, branch-side workers. |
>
> The same values appeared in `cutover-migration.md` REQ-CUT-001 (identical table).
>
> `design.md` §2 Issue #3 replaced these five values with **behavior-based** names:
>
> | Design value | Behavior | Stage |
> |---|---|---|
> | `legacy` | Legacy applier; kill switch. | 0 (pre-cutover) |
> | `catalog_read` | `api_admin` reads catalog to validate row metadata; writes via legacy applier. | 1 |
> | `catalog_dual` | Both legacy and catalog appliers run; disagreements log a structured alert and prefer legacy. | 2 |
> | `catalog_only` | Catalog-driven only. Legacy paths stubbed to `NotImplementedError`. | 3-4 |
> | `catalog_lite` | Branch-side mode: catalog drives `sync_queue` + hash chain only; PII redaction + dependency buffer active; deep features off. | 5 (branch) |
>
> The two enums were judged not isomorphic: spec values were **service-flavored**, design values
> **stage-flavored**. Note also that the `catalog` row above cites "all 47 entries" — a stale count;
> the ratified catalog size is **46** (proposal §6.5).

</details>

## Decision

**`PARKOS_SYNC_ENGINE` accepts exactly five values:**

```
legacy | catalog_admin | catalog_dian | catalog | catalog_branch
```

| Value | Stage | Service | Behaviour |
|---|---|---|---|
| `legacy` | 0 | all | No catalog consulted; legacy applier. **Kill switch** (D12). |
| `catalog_admin` | 1 | `api_admin` | Reads `SYNC_CATALOG` for row metadata; writes via the legacy applier. Read-side observability only. |
| `catalog_dian` | 2 | `dian/cloud/dispatcher` | Catalog-driven on the DIAN path: range validation on receipt, `envio_dian` emitted `cloud_to_branch`. |
| `catalog` | 3 | `jobs/sync_cloud` | Catalog-driven cloud-side; legacy paths stubbed to `NotImplementedError`. |
| `catalog_branch` | 4-5 | branch workers | Catalog-driven branch-side, gated on `catalog_backfill_complete{uuid_sucursal}` = 1 (R-D8). |

**No spec amendment is required.** The specs already carry these values, so this ADR removes an
artifact split rather than propagating one. `design.md` §2 Issue #3 and §8 are amended to match, and
the behaviour-flavoured variant (`catalog_read`, `catalog_dual`, `catalog_only`, `catalog_lite`) is
withdrawn — it must not appear in any artifact, module, runbook, or test.

<details>
<summary><b>Superseded — original Decision (kept for history)</b></summary>

> The **design enum wins**: `PARKOS_SYNC_ENGINE` accepts
> `legacy | catalog_read | catalog_dual | catalog_only | catalog_lite`. The spec text in REQ-MOT-011
> and REQ-CUT-001 is amended by this ADR.
>
> | Spec (role-flavored) | Design (stage-flavored) | Where it runs |
> |---|---|---|
> | `legacy` | `legacy` | All services (kill switch). |
> | `catalog_admin` | `catalog_read` | `api_admin` only (stage 1). |
> | `catalog_dian` | `catalog_dual` | `dian/cloud/dispatcher` (stage 2). |
> | `catalog` | `catalog_only` | `job_sync_cloud` (stages 3-4). |
> | `catalog_branch` | `catalog_lite` | Branch workers (stage 5). |

</details>

## Rationale

1. **The flag value must name the stage, and the stages are named by service.** D13 stages the
   cutover by service. With the service-flavoured enum the flag value alone answers the only question
   an operator asks during a stage incident — "which stage is live?" The behaviour-flavoured enum
   requires a second mapping table to answer it, and a mapping table maintained in an ADR is exactly
   the artifact you cannot trust at 03:00. The original rationale optimized for describing the
   observable; it overlooked that the *stage* is the observable an operator acts on.
2. **The mapping table was itself the evidence.** The original decision shipped a 1:1 mapping between
   the two enums. A 1:1 mapping means the two sets carry identical information, so the split bought
   nothing and cost two spec amendments plus a translation step in every runbook.
3. **The motor still never imports service identity.** This was the original rationale's strongest
   point and it survives intact: `SyncMotor.__init__(engine=…)` receives the mode as a constructor
   argument and dispatches on it. A value *named* after a service does not make the motor aware of
   its service — the worker that constructs the motor already knows which service it is. The
   anti-pattern the original ADR feared does not occur.
4. **`catalog_branch` does not need splitting.** The original ADR split branch behaviour into
   `catalog_only` (cloud) and `catalog_lite` (branch) because "branch workers must disable deep
   features (auto-reprint, realtime DIAN ack) per D16 even after cutover". **D1-rev removes that
   requirement.** Reprint is never gated on a cloud round-trip, and the branch emits and numbers
   locally, online or offline, with no behavioural difference. What degrades under a partition is
   DIAN *acknowledgement visibility* only — a status indicator, not a feature toggle. The distinction
   the split existed to encode no longer exists.
5. **`catalog_dian` names the DIAN path, which is a real stage with a real gate.** Stage 2's gate is
   specific and service-shaped: zero `operacion='sync_back_event'` rows anywhere, a branch-emitted
   `factura_electronica` range-validated and forwarded, `envio_dian` (`cufe`, `estado`) applying at
   the originating branch, and reprint available throughout including with the cloud unreachable. The
   original ADR called `catalog_dian` a conflation of stage with service; under D13 they are the same
   axis.

<details>
<summary><b>Superseded — original Rationale (kept for history)</b></summary>

> 1. **Operational clarity.** Operators tuning the flag in a stage 2 incident need the behavior
>    ("dual-write, log disagreements"), not the surface ("DIAN dispatcher").
> 2. **Stateless motor.** The spec's `catalog_admin` / `catalog_branch` names require the motor to
>    import service-level config (anti-pattern).
> 3. **Branch cutover shape.** The split into `catalog_only` / `catalog_lite` is required because
>    branch workers must disable deep features (auto-reprint, realtime DIAN ack) per D16 even after
>    cutover.
> 4. **Dual-write visibility.** `catalog_dual` is the only value that names the dual-write stage
>    explicitly.
>
> Points 1, 2, and 4 are answered above. **Point 3 is void**: its premise (a branch feature set
> reduced by D16) was removed by D1-rev.

</details>

## Alternatives considered

| Option | Tradeoff | Decision |
|---|---|---|
| Service-flavoured enum (`catalog_admin`, `catalog_dian`, `catalog`, `catalog_branch`) | Flag value = stage identity; no mapping table; already in both spec files | **CHOSEN** (D22) |
| Behaviour-flavoured enum (`catalog_read`, `catalog_dual`, `catalog_only`, `catalog_lite`) | Names the observable behaviour, but needs a second mapping table to locate the stage, and its `catalog_lite` split is void after D1-rev | rejected — withdrawn |
| Two orthogonal flags (one for stage, one for behaviour) | Expressive, but doubles the rollback surface: the kill switch stops being a single env flip, which breaks D12 | rejected |
| A numeric stage flag (`PARKOS_SYNC_STAGE=0..5`) | Unambiguous ordering, but loses the kill-switch semantics of a literal `legacy` and reads as opaque in logs and alerts | rejected |

## Consequences

### Positive

- **Zero spec drift.** `specs/sync-motor.md` REQ-MOT-011 and `specs/cutover-migration.md`
  REQ-CUT-001 are already correct and are **not** edited. Finding A5 closes without touching the
  spec layer.
- **The flag value locates the stage directly**, so `design.md` §8's stage table, the D13 stage list,
  and the ops runbooks all key on the same literal.
- The 60 s re-read operates on a single enum; transitions such as `catalog_dian → catalog` are
  observable in logs by value.
- Rollback stays a single env flip to `legacy` (D12), unchanged.

### Negative

- **Design and this ADR carried the withdrawn values** and needed the amendment recorded here. That
  is the cost being paid now.
- **Any artifact, module, runbook, or test written against the withdrawn names must be corrected.**
  Mitigation: the AST guard below fails the build on any withdrawn literal, so the correction cannot
  be forgotten silently.
- The value `catalog` is a prefix of `catalog_admin`, `catalog_dian`, and `catalog_branch`.
  Mitigation: parsing is exact-match against the enum, never a prefix or `startswith` test, and the
  parser test asserts that explicitly.

## Tasks affected

- **PR1** — `parkos_core/runtime/engine_flag.py` parses exactly these five values and rejects every
  withdrawn name.
- **PR11** — `/sync/hello` `protocol_version` stays `legacy | catalog` (the *protocol* enum, which is
  deliberately distinct from the *engine* enum — a two-value wire contract, not a five-value stage
  flag).
- **PR14** — `reverse_sync_overhaul.py` resets to `legacy`; `cutover/stage_runner.py` evaluates gates
  keyed on these five values.
- **PR14** — the repo-wide grep gate (R21) additionally returns zero hits for `catalog_read`,
  `catalog_dual`, `catalog_only`, and `catalog_lite` outside this ADR's superseded blocks.

## Validation

- `tests/unit/test_engine_flag.py::test_parse_all_5_values` — accepts `legacy`, `catalog_admin`,
  `catalog_dian`, `catalog`, `catalog_branch`.
- `tests/unit/test_engine_flag.py::test_rejects_withdrawn_values` — rejects `catalog_read`,
  `catalog_dual`, `catalog_only`, `catalog_lite`.
- `tests/unit/test_engine_flag.py::test_exact_match_not_prefix` — `catalog_admin` does not parse as
  `catalog`, and an unknown value such as `catalogue` is rejected.
- `tests/unit/test_engine_flag.py::test_legacy_is_kill_switch` — `apply_row` returns the legacy
  outcome under `legacy`.
- AST guard `check_engine_flag_values.py` (PR11, alongside `check_catalog_drift.py`) asserts the enum
  literal in `engine_flag.py` equals the five ratified values and that no withdrawn literal appears
  anywhere under `backend/` or `openspec/scripts/`.

## References

- `proposal.md` **D22** — the ratifying decision, with the D13 stage-order rationale.
- `proposal.md` D1-rev — removes the premise behind the withdrawn `catalog_lite` split.
- `proposal.md` §11 — the six-stage cutover table these values key on.
- `design.md` §2 Issue #3, §8 — amended to these values.
- Engram #1408 — D1-D16 decisions (D1 superseded).
- AGENTS.md §"Workflow (SDD)" — when spec and design disagree, the ER-derived decision wins and the
  losing artifact is corrected. Here the ER-derived decision is the spec's, so the design was
  corrected.
