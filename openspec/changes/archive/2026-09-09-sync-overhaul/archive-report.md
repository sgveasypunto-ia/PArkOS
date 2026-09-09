# Archive Report: `sync-overhaul`

> Phase: archive (sdd-archive)
> Date: 2026-09-09
> Archived to: `openspec/changes/archive/2026-09-09-sync-overhaul/`
> Artifact store mode for this closure: hybrid (filesystem move/merge per `openspec/config.yaml` "Artifact store: hybrid (Engram + openspec/)", plus this report persisted to Engram under `sdd/sync-overhaul/archive-report`)
> Verdict carried forward from verify: PASS WITH WARNINGS (no CRITICAL findings; all open items WARNING/SUGGESTION severity, documentation/spec-text only)

## 1. SDD cycle closed

`propose` → `spec` (5 domain specs) → `design` → `tasks` (14 PRs, ~200 atomic tasks) → `apply` (14 PRs implemented and merged) → `verify` (PASS WITH WARNINGS) → **`archive` (this report)**. All required artifacts were present and read in full before this closure: `proposal.md` (1342 lines, D1-D22, ER-alignment amendment), `design.md` (1231 lines, 17 sections + 3 ADRs), the 5 delta specs under `specs/` (83 REQ-* total), `tasks.md` (3374 lines, 14 PRs + 2 post-PR14 E2E closure sections), `verify-report.md` (76 lines).

## 2. Native Review Receipt Gate

Not queried in this closure. This archive run was launched directly as a documentary closure step (no code changes, no test execution, no review-lifecycle invocation performed or requested). No `reviewGate` evidence was collected; per the gate's own default, an absent/unqueried gate in an ordinary-policy repository does not block archive. If receipt-driven development is active for this repository and a receipt exists for this candidate, it was not consulted here — flagged for completeness, not as an open risk, since the user's explicit instructions scoped this run to artifact consolidation only.

## 3. Task Completion Gate — 20 unchecked checkboxes reviewed, none block archive

`tasks.md` (as archived) contains 195 checked (`[x]`) and 20 unchecked (`[ ]`) items. All 20 were inspected individually; none is an unfinished implementation task:

- 14 are the "Branch `...` pushed, target `dev`" / "PR opened" delivery-step checkboxes at the end of each PR section (T-PR1..PR14 "Commit + open PR" tasks), each carrying an explicit `Status:` note stating commit/push was deliberately left to the maintainer/orchestrator during the apply session (no `git commit`/`push` performed by that executor, per that session's own instructions).
- 4 are PR-description/attachment checkboxes tied to those same delivery steps (`--sql` dry-run attachments, PR14 rehearsal-output attachment, PR13 rehearsal note) — same category, not code.
- 1 is `GET /metrics exposes all counters/gauges with PII-free labels` (PR13 acceptance) — explicitly and permanently out of this change's scope (documented gap, mirrors the PR12 `catalog_backfill_complete` exposition carve-out); the 4 underlying counters/gauges themselves are real, tested, and PII-free.
- 1 is the PR1 "held for [orchestrator]" branch/PR-body checklist, same delivery-step category.

**Final-state reconciliation (per Final-State Authority):** `tasks.md`'s own checkboxes and its closing prose ("Working tree carries 4 real fixes (uncommitted, for review)") are intermediate-snapshot claims, current only at the moment each section was written. The actual final state — corroborated independently by `git log` on `dev` in this repository, not merely asserted — shows all 14 PR branches merged in sequence (`9f8f20b` → `73492e4`), followed by the testcontainers E2E closure fix commit (`5ee5bca`), a compose config commit (`971ec21`), and the real-Docker-deployment fix commit (`5b41fdf`, HEAD of `dev` at archive time). The "uncommitted, for review" fixes `tasks.md` describes (workers' missing `session.commit()`, `/sync/events` dependency-ordering fix, migration `0016_add_sync_apply_guard.py` + `sync/motor/apply_guard.py`) are present on disk and match exactly the content of commit `5b41fdf`; nothing from that description remains uncommitted. No unchecked box represents unfinished implementation work. No reconciliation edit was made to the archived `tasks.md` checkboxes themselves — the file is archived byte-identical to its state at verify time (see diff evidence in §7); this section documents why that is safe to do, not a repair.

No CRITICAL issues exist in `verify-report.md` (verdict: PASS WITH WARNINGS, 0 CRITICAL). Archive proceeds without any override.

## 4. Delivery: 14 PRs merged to `dev`

| PR | Commit on `dev` | Scope |
|---|---|---|
| PR1 | `9f8f20b` | Working-tree cleanup, pytest/TDD scaffold, `PARKOS_SYNC_ENGINE` parser, role guard, `sync_queue` carve-out check |
| PR2 | `8e6b855` | Declarative `SyncCatalog` (46) + `LocalOnlyCatalog` (3) + `OutOfCatalog` (5), direction ratified from the ER |
| PR3 | `7e0913e` | `depends_on` DAG + `DependencyOrderer` (D18, ADR-003); fixed 3 ER-misaligned `depends_on` entries |
| PR4 | `2bef349` | `SyncMotor` skeleton + hook lifecycle |
| PR5 | `7058e17` | D17 identity reconciliation + subscription lifecycle + plate cascade + R22 |
| PR6 | `b0ff5e0` | Hash-chain hooks + `verify_chain`; real genesis-row bootstrap |
| PR7 | `e98cc37` | `_read_local_seq` materialization + `resolve_conflict`; `ConflictResolver` becomes a shim |
| PR8 | `df5b742` | Dependency buffer + `alert_types` + single escalation path (D18, ADR-002/003) |
| PR9 | `3266301` | DIAN path: branch-local numbering + `envio_dian` + dedicated backoff (D1-rev) |
| PR10 | `29c4b14` | Migrations 0014/0015 + `modelo_datos_er.mmd` amendment + count scripts; 18 `[V]` tables gain triggers, canon reaches 51/54 |
| PR11 | `0e4a989` | Cloud worker cutover: catalog-driven `job_sync_cloud` + `/sync/hello` + dual protocol |
| PR12 | `66dcb36` | Branch cutover: `job_sync_sucursal` + topological backfill + `catalog_backfill_complete` |
| PR13 | `abdc5cd` | Observability: metrics + structured logs + sink-side PII redaction + Grafana alerts |
| PR14 | `73492e4` | Cutover stage gates + reverse-migration script + `AGENTS.md` correction (D12, R21) |

Followed by two closing fix commits outside the numbered PR chain, both requested as explicit closing exercises (see §5): `5ee5bca` (testcontainers 46/46 catalog E2E, 6 bugs + 1 pre-existing JWT flake) and `5b41fdf` (real Docker deployment, 3 additional critical bugs, migration `0016_add_sync_apply_guard`).

## 5. Two E2E closure exercises, run against the full 46-entry `SYNC_CATALOG`

### 5.1 Testcontainers exercise (commit `5ee5bca`)

New test `backend/tests/integration/test_e2e_full_catalog_sync.py`: for every one of the 46 catalog entries, created one record through the real service/repo layer, let the real DB trigger enqueue it, ran the real job/motor code, and verified it landed at the destination. Harness used two independent, module-scoped real Postgres `testcontainers` (cloud + branch), each with the full `0001..0015` Alembic chain applied. Result: **46/46 accounted for** — 45 synced correctly end to end, `validacion_evento` confirmed to correctly never propagate (its documented `never_propagated` strategy).

**6 real bugs found and fixed** (motor/repo/catalog layer only — no schema, no API):
1. `sesion` silently misrouted into `prod.login` — motor dispatch keyed on `apply_strategy`, not `spec.name`, for the two tables sharing `session_cycle`.
2. Wire payload date/datetime strings never coerced before an asyncpg bind, raising `DataError` the first time a payload crossed an actual JSON wire boundary.
3. `revocacion_factura`/`log_transaccional` double-inserted on every sync — `hook_chain_extend` re-ran hash-chain extension already handled by the `append_event` apply strategy.
4. `factura_electronica` ORM/DB mapping drift — `fecha_retencion_hasta` column existed physically but was never declared on the ORM class.
5. Hash-chain canonical JSON serializer rejected a bare `date` value (only handled `datetime`/`uuid.UUID`).
6. pg_partman child-partition names never resolved against the catalog — 8 partitioned tables silently failed sync forever (`unknown_table`) because triggers fire with the partition's physical name, not the logical parent name.

Plus **1 pre-existing flake reproduced and triaged**, not fixed as part of this change: `test_jwt_issuer_guard.py`, confirmed order-dependent and unrelated to sync-overhaul (passes standalone and in every other full-suite run).

3 issues were found and explicitly left unfixed as out of this exercise's scope (documented, not silently dropped): a blanket `uuid`-strip helper that would break referential identity once a real multi-level `[V]` backfill chain exists; the trigger "echo" amplification risk on cross-side apply (later confirmed for real — see §5.2); and an `append_transition` parent-key mismatch that bypasses state-machine validation for non-root `[L-W]` rows (currently inert, since every row this exercise creates is a root transition).

### 5.2 Real Docker deployment exercise (commit `5b41fdf`, follow-up to 5.1)

Repeated the same 46-entry closing exercise against the actual `docker-compose.cloud.yml` + `docker-compose.local.yml` stack — 6 real containers (`cloud-db`, `api-admin`, `job-sync-cloud`, `branch-db`, `api-sucursal`, `job-sync-sucursal`), real HTTP between two independently networked Postgres databases, not testcontainers. Images rebuilt from current `dev`; migrations `0008`→`0016` applied to both databases; existing branch pairing/JWT confirmed valid throughout (zero 401/403). Result: **46/46 accounted for** again, same `validacion_evento` non-propagation confirmed.

**3 additional real bugs found and fixed**, none of which the testcontainers exercise's more artificial one-row-at-a-time calling convention could surface:
1. `SyncCloudWorker`/`SyncSucursalWorker` never called `session.commit()` for the life of the process — every applied row and status transition sat in one never-committed transaction; confirmed fatal (blocked a real `alembic upgrade` with `LockNotAvailable` against the worker's own idle-in-transaction backend). Fixed by committing at each unit-of-work boundary in both `jobs/sync_cloud.py` and `jobs/sync_sucursal.py`.
2. `POST /sync/events` applied a received batch in wire order, not dependency order, and one FK violation aborted the entire batch. Reproduced deterministically with a real parent+child pair (`facturas`+`factura_electronica`) created moments apart by a real polling worker. Fixed by routing through the same `dependency_orderer.order_batch` every other real call site already uses, preserving response-index correspondence.
3. **Real defect #3 — echo-amplification / hash-chain double extension.** This is the same gap the testcontainers exercise had already discovered and explicitly left unfixed (§5.1, item b): the `AFTER INSERT` trigger fires unconditionally, including when the sync motor itself is writing an already-incoming row, so an "echo" enqueue amplifies without bound on every real drain cycle. It was CONFIRMED to manifest for real once a genuine long-running worker (made durable by bug #1's fix) exercised it end to end — `motor.verify_chain` found dozens of genuine `ChainAnomaly` breaks on `log_transaccional`/`revocacion_factura`. It was then **RESOLVED in a follow-up session on the same Docker stack**: migration `0016_add_sync_apply_guard.py` adds a session-local Postgres GUC check (`parkos.sync_apply_in_progress`) as the first statement in both trigger functions; `sync/motor/apply_guard.py::enable_echo_suppression` sets that GUC transactionally at every real call site where the motor applies an already-synced row (`sync_router.py::sync_events`, both worker `_apply_pending_batch_once`/`_pull_and_apply*` paths). Regression-covered by a new `tests/integration/test_sync_apply_echo_guard.py`; re-verified against the real running stack with zero new `ChainAnomaly` entries post-fix.

One additional pre-existing, unrelated behavior was observed and explicitly not investigated further (out of scope, "leave other PRs' gaps alone" discipline already established): `POST /api/v1/sync/heartbeat` returns `422` throughout, fire-and-forget, does not affect the sync cycle.

### 5.3 Combined bug count across the whole change

**9 real bugs found and fixed** across the two E2E closure exercises (6 in the testcontainers pass + 3 in the real-Docker pass, the third of which is the same underlying gap discovered-but-deferred in the testcontainers pass and only confirmed/resolved once a real long-running deployment exercised it) — matching the closing count communicated for this archive. Plus 1 pre-existing JWT test flake triaged as unrelated. No schema or API-contract change was required by any of the 9 fixes except the deliberate, additive migration `0016_add_sync_apply_guard.py` (function bodies only — no table recreated, no trigger dropped/recreated).

## 6. Final test suite state

`tasks.md` documents an incremental progression across checkpoints: 1260 passed/28 xfailed/14 skipped/0 failed at the PR14 baseline (per `verify-report.md`), then 1263 passed after the testcontainers E2E closure (+1 new E2E test, +2 regression unit tests for the `sesion`-dispatch fix). Per the explicit final-state statement for this closure — corroborated by commit `5b41fdf` being the current `dev` HEAD and by the new `test_sync_apply_echo_guard.py` regression coverage it adds — the true final suite state at archive time is:

**1266 passed, 28 xfailed, 14 skipped, 0 failed.**

The 28 xfailed are unchanged from the PR14 baseline throughout (documented, pre-existing, out-of-scope gaps: pg_partman "now"-partition gap for `pairing_tokens`, `revoked_sync_jwts.key_uuid` missing column, plus pre-existing auth/pairing bugs — rate-limit, JWT persisted-path permissions, env-validator fail-fast — all recorded in the user-approved triage referenced by `verify-report.md`). 0 failed at every checkpoint from PR14 onward.

## 7. Deliverable: real Docker stack deployed and running

Per the explicit final-state statement for this closure, the 6-container real deployment (`cloud-db`, `branch-db`, `api-admin`, `api-sucursal`, `job-sync-cloud`, `job-sync-sucursal`) is left running and healthy, both databases migrated to Alembic head `0016_add_sync_apply_guard`, as a live artifact of the change's own closing verification — not merely a test-time construct. This is recorded here as a fact about the environment at closure; this archive operation itself performed no Docker action.

## 8. Open follow-ups (non-blocking, carried from `verify-report.md`, all WARNING/SUGGESTION)

None of the following blocks this archive; none is a functional defect. Recommended as one small housekeeping change if/when convenient:
1. `AGENTS.md` line 204 — stale "100% centralized in cloud admin" bullet, not caught by the T-PR14-004 literal-term grep gate, contradicts the immediately following D1-rev text.
2. `operations.md` REQ-OPS-006 lists `sync_dependency_wait` labels as `tabla`/`uuid_sucursal`; shipped code (and `design.md` §9) uses `tabla`/`tabla_padre` — code is the semantically correct choice; spec text was never reconciled.
3. `0012_add_sync_queue_lw_buffer.py`'s `REVOKE` scope diverges from `cutover-migration.md` REQ-CUT-010's literal blanket-`REVOKE UPDATE, DELETE` text (a disclosed, functionally justified carve-out mirroring the pre-existing `sync_queue` pattern); spec text not yet amended to match.
4. Two runbook filenames (`dependency_wait.md`, `client_volume.md`) document `FEProviderError`/`FENumberingExhausted` but are named after superseded alert rules; each file carries an explicit top-of-file note explaining the mismatch.
5. `tasks.md`'s own Cross-PR constraints section (now archived) cites stale migration numbers (0009, 0010) instead of the real, renumbered 0012/0013 for the `[A]`-migration REVOKE-and-trigger invariant.
6. `MOT-010`/`HOOK-012`/`HOOK-013` (`ValidateParentChain`) is dispatchable via `hooks.registry.resolve()` but no catalog entry currently sets that hook slot — pre-approved out-of-scope gap, not new.
7. `GET /metrics` HTTP exposition endpoint (REQ-OPS-006) does not exist; the 4 underlying counters/gauges are real and PII-free, only the scrape endpoint and 4 additionally-named metrics remain a follow-up (mirrors the PR12 `catalog_backfill_complete` exposition carve-out).
8. `/sync/pull` backfill transport remains a literal stub; the only wired backfill mechanism is `sync/cutover/backfill.py::run_backfill`, invoked directly by both E2E exercises' own harnesses, not yet by any production job.
9. The blanket `uuid`-strip in `_business_payload_for_apply` would break referential identity once a real multi-level `[V]` backfill chain exists; inert today because `/sync/pull` is a stub.
10. `append_transition`'s `parent_uuid` key lookup bypasses state-machine validation for a synced non-root `[L-W]` transition; inert today because every `[L-W]` row created by the closing exercises is a root transition.

## 9. Specs synced to `openspec/specs/` (source of truth)

No main specs directory existed prior to this change (`openspec/specs/` was absent). Each of the 5 domain specs delivered by this change is therefore a full spec, not a delta against pre-existing text, and was copied mechanically (shell `cp`, verified with an empty `diff -r`, never Read→Write) rather than merged:

| Domain | Action | Path |
|---|---|---|
| sync-catalog | Created | `openspec/specs/sync-catalog/spec.md` (CAT-001..021, 21 requirements) |
| sync-motor | Created | `openspec/specs/sync-motor/spec.md` (MOT-001..016, 16 requirements) |
| hooks | Created | `openspec/specs/hooks/spec.md` (HOOK-001..015, 15 requirements) |
| cutover-migration | Created | `openspec/specs/cutover-migration/spec.md` (CUT-001..015, 15 requirements) |
| operations | Created | `openspec/specs/operations/spec.md` (OPS-001..016, 16 requirements) |

83 REQ-* requirements total now live as the project's canonical source of truth for the sync engine.

## 10. Mechanical copy/move verification (mandatory, verbatim)

Spec copy to `openspec/specs/{domain}/spec.md` (5 domains), each verified with `diff -r` between the change's delta spec file and the newly written main spec file — all empty:
```
== cutover-migration == / exit=0
== hooks == / exit=0
== operations == / exit=0
== sync-catalog == / exit=0
== sync-motor == / exit=0
```

Change-folder move via `git mv openspec/changes/sync-overhaul openspec/changes/archive/2026-09-09-sync-overhaul`, verified with `diff -r` between a pre-move recursive snapshot (taken to the session scratchpad directory) and the archived destination — empty, exit code 0:
```
diff -r <pre-move-snapshot>/source openspec/changes/archive/2026-09-09-sync-overhaul
diff exit code: 0
```
This report file itself is additive to the archived folder and was excluded from that comparison, per the mechanical copy contract (it did not exist in the source folder being compared).

## 11. Artifacts

- `openspec/changes/archive/2026-09-09-sync-overhaul/` — full archived change folder (proposal.md, design.md, exploration.md, adr/, specs/, tasks.md, verify-report.md, this archive-report.md)
- `openspec/specs/{sync-catalog,sync-motor,hooks,cutover-migration,operations}/spec.md` — new canonical project specs
- Engram `sdd/sync-overhaul/archive-report` — this report, persisted for cross-session traceability

## 12. SDD Cycle Complete

The `sync-overhaul` change is fully planned, implemented (14 PRs merged to `dev`), independently verified (PASS WITH WARNINGS, 0 CRITICAL), closed with two escalating real-world E2E exercises (testcontainers, then real Docker deployment) that together found and fixed 9 real bugs beyond what unit/integration testing alone had caught, and is now archived. The real 6-container Docker deployment remains running and healthy as a live artifact of this closure. Ready for the next change.
