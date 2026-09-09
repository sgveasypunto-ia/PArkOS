# Tasks: `sync-overhaul`

> **Change**: `sync-overhaul`
> **Phase**: tasks (sdd-tasks) — **rebuilt 2026-09-08** from the amended proposal/specs/design/ADRs
> (ER-alignment correction pass). This is a full regeneration, not a patch: the prior 63-task /
> 1591-line breakdown is **superseded in full** — content changed too much (dropped work,
> new work, renumbered decisions) to patch incrementally.
> **Status**: ready for `sdd-apply` pending the chain-strategy decision (see Review Workload Forecast)
> **Preflight (this session)**: `pace=auto`, `artifact_store=hybrid`, `delivery_strategy=auto-chain`,
> `review_budget_lines=800` (session-authoritative for this run — supersedes `openspec/config.yaml`'s
> stale 400-line figure)
> **Chain strategy**: **not chosen this session** — see Review Workload Forecast. Do not infer one.
> **Inputs read**: `proposal.md` (amended, D1–D22), `specs/{sync-catalog,sync-motor,hooks,
> cutover-migration,operations}.md` (all amended, some twice), `design.md` (amended, 17 §§, 7
> sequence diagrams, §0 amendment log), `adr/{001-parkos-sync-engine-enum,002-50-table-canon,
> 003-dependency-ordering-and-single-escalation}.md`,
> `.agent-generated/2026-09-08-review-sync-overhaul-er/{correccion-brief,addendum-casos-de-uso}.md`,
> the prior `tasks.md` (structure/branch-naming convention only — content superseded)
> **Skills loaded**: `python`, `alembic`, `uv` (paths injected — `skill_resolution: paths-injected`)
> **Chain topology (corrected 2026-09-08 per the org's mandatory `aranda-git-workflow` skill, §2
> `ramas-e-integracion.md`)**: `feature/sync-overhaul` (off `dev`) is the integration branch for the
> whole change — it integrates once to `dev` at the end via squash merge, then is deleted. Each of the
> 14 PRs is an `hu/PR{NN}-{slug}` branch hanging directly off `feature/sync-overhaul` and merging back
> into it (squash) — NOT chained PR-to-PR, NOT targeting `dev` directly. The PR number stands in for
> `{ID-WI}` (no work-item tracker in this repo) — a documented adaptation of the `hu/` pattern, not a
> silent deviation. Only `feature/sync-overhaul` → `dev` is a real integration point.

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~8,000 across 14 chained PRs (per-PR estimates below, from proposal §10 / design §13, each ≤ 800 LOC by design) |
| Total tasks | 149 across 14 PRs (vs. 63 in the superseded breakdown — atomicity requirement, more/smaller not fewer/larger; includes T-PR2-000, a pre-existing `sync_queue.py` bugfix discovered mid-session) |
| Review budget applied | 800 lines/PR (session preflight, authoritative for this run) |
| 400-line budget risk | **High** — PR2 (~750), PR5 (~700), PR8 (~700) sit at 87-94% of the 800-line ceiling before test/migration overhead is counted; real diffs have historically run larger than estimates on this change |
| Chained PRs recommended | Yes — 14 PRs, each independently gated, dependency-ordered |
| Chain strategy | **pending** — not selected this session. Proposal §10 / design §13 suggest feature-branch-chain for the cutover-stage PRs (9-14) and gitflow-to-`dev` for the foundation PRs (1-8); that is a proposal-level suggestion, not a ratified session decision — the orchestrator must collect the actual choice from the user before `sdd-apply` opens PR1 |
| Suggested split | PR1 → PR2 → PR3 → PR4 → PR5 → PR6 → PR7 → PR8 → PR9 → PR10 → PR11 → PR12 → PR13 → PR14 (strict dependency order — matches proposal §10 / design §13 exactly) |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — every PR is designed ≤ 800 LOC |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| PR | Goal | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|
| PR1 | Working-tree cleanup + pytest/TDD scaffold + `PARKOS_SYNC_ENGINE` parser + `role_guard` + `sync_queue` carve-out | `uv run pytest tests/unit/test_engine_flag.py tests/integration/test_role_guard.py -q` | N/A — parser/guard unit tests only, no live DB | Revert branch; no schema touched |
| PR2 | Declare `SYNC_CATALOG` (46) + `LocalOnlyCatalog` (3) + `OutOfCatalog` (5), direction ratified | `uv run pytest tests/unit/test_catalog_counts.py tests/unit/test_catalog_schema.py -q` | `python openspec/scripts/check_catalog_drift.py` against the populated catalog | Revert branch; catalog module unused until PR4 wires the motor |
| PR3 | `depends_on` DAG + `DependencyOrderer` | `uv run pytest tests/unit/test_dependency_graph.py tests/unit/test_dependency_orderer.py -q` | N/A — pure graph algorithm, no DB | Revert branch; orderer unused until PR4 |
| PR4 | `SyncMotor` skeleton + hook lifecycle (`validate_parent → pre_insert → repo → post_insert → chain_extend`) | `uv run pytest tests/unit/test_motor_apply_row.py tests/unit/test_motor_apply_batch.py -q` | testcontainers Postgres, `apply_row` against a seeded `[V]`/`[A]` fixture | Revert branch; motor not yet called by any worker |
| PR5 | D17 identity reconciliation + subscription lifecycle + plate cascade + R22 | `uv run pytest tests/unit/test_identity_reconciler.py tests/integration/test_r22_non_selling_branch.py -q` | testcontainers Postgres, two-branch concurrent-registration scenario | `alembic downgrade -1` twice (0015, 0014); hooks unused until wired |
| PR6 | Hash-chain hooks + `verify_chain` | `uv run pytest tests/unit/test_verify_chain.py -q` | testcontainers Postgres, chain-break injection | Revert branch; verifier not yet scheduled |
| PR7 | `_read_local_seq` materialization + `resolve_conflict` | `uv run pytest tests/unit/test_read_local_seq.py tests/bench/test_read_local_seq_load.py -q` | testcontainers Postgres, 10k-row load test | `alembic downgrade -1` (0013) |
| PR8 | Dependency buffer + `alert_types` + single escalation path | `uv run pytest tests/integration/test_parent_missing_buffer_drain.py tests/integration/test_buffer_ttl_escalation.py -q` | testcontainers Postgres, buffer TTL sweep rehearsal | `alembic downgrade -1` twice (0010, 0009) |
| PR9 | DIAN path: branch-local numbering + `envio_dian` + DIAN backoff | `uv run pytest tests/unit/test_consecutivo_assignment.py tests/integration/test_dian_round_trip.py -q` | testcontainers Postgres + mocked DIAN provider | Revert branch; no legacy return path exists to fall back to (fresh build) |
| PR10 | Migrations 0011/0012 + `modelo_datos_er.mmd` amendment + count scripts | `python openspec/scripts/check_table_counts.py && python openspec/scripts/check_schema_match.py` | `alembic upgrade --sql` dry-run against a staging DSN | `alembic downgrade -1` twice (0012, 0011) |
| PR11 | Cloud worker cutover: catalog-driven `job_sync_cloud` + `/sync/hello` | `uv run pytest tests/integration/test_dual_protocol.py -q` | staging cloud worker with `PARKOS_SYNC_ENGINE=catalog_dian` | `PARKOS_SYNC_ENGINE=legacy` (D12 kill switch) |
| PR12 | Branch cutover: `job_sync_sucursal` + topological backfill + `catalog_backfill_complete` | `uv run pytest tests/integration/test_pairing_flow.py tests/integration/test_branch_offline_flow.py -q` | staging branch worker, cold-pair rehearsal | `PARKOS_SYNC_ENGINE=legacy` on the branch worker |
| PR13 | Observability: metrics + logs + sink-side PII redaction + Grafana alerts | `uv run pytest tests/unit/test_observability_metrics.py tests/unit/test_pii_redaction.py -q` | `GET /metrics` scraped locally | Revert branch; additive only |
| PR14 | Stage-gate runner + reverse migration + `AGENTS.md` correction | `uv run python openspec/scripts/reverse_sync_overhaul.py --dry-run` | full-chain rehearsal against staging | `reverse_sync_overhaul.py` (without `--dry-run`) is itself the rollback path |

## Notes (not tasks)

- **Leave the 4 untracked demo scripts alone.** `backend/scripts/{insert_null_genesis,
  replicate_catalogs_to_branch,verify_branch_catalogs}.py` and `infra/scripts/seed_catalogs.py` are
  manual workarounds for the legacy pipeline with hardcoded local DSNs. No task builds on them.
  `infra/scripts/seed_catalogs.py` is cited once, as an idempotent-seed **pattern reference** for
  the new `infra/scripts/seed_alert_types.py` (T-PR8-003) — nothing else.
- **TDD convention used selectively.** RED-then-GREEN task pairs are used for genuinely new
  decision-bearing logic (motor dispatch, dependency ordering, identity reconciliation, numbering,
  hash chain). Purely declarative work (catalog entry declarations, migrations, docs edits) ships as
  one task with its own inline acceptance check, per the atomicity rule's "migration + its own test"
  cluster allowance.
- **Every migration task carries a pre-flight `alembic upgrade --sql <revision>` check** — the raw
  SQL is reviewed before the migration is applied to any environment (project task rule).
- **All `[A]` migrations ship `REVOKE UPDATE, DELETE` + `BEFORE UPDATE OR DELETE` trigger in the
  same script** as the `CREATE TABLE` (`openspec/config.yaml rules.tasks`, mirrors `prod.bitacora`).

---

## PR1 — Working-tree cleanup + pytest/TDD scaffold + `PARKOS_SYNC_ENGINE` + guards

**Branch**: `hu/PR01-limpieza-arbol-trabajo` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: current `dev` HEAD — already includes `create-49-table-apis`'s ORM/API layer and
`bootstrap-monorepo-foundation`'s `parkos_core/runtime/` scaffolding (confirmed present in the
working tree: `router_factory.py`, `sync_router.py`, `sync_cloud.py`, `dian/cloud/dispatcher.py`,
`repo/hash_chain.py` all already exist and are modified/imported by this change).
**Estimated LOC**: ~280 (proposal §10)
**Gate to next PR**: CI green (`uv sync --frozen`, carve-out check, pytest)
**Status**: Code changes verified present in the working tree — `runtime/engine_flag.py`,
`sync/guards/role_guard.py`, and `repo/sync_queue.py::ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS` all exist;
`sync/table_registry.py` is absent, matching T-PR1-001's cleanup action. Per the mandatory
`hu/`-under-`feature/` topology (`aranda-git-workflow` §2), `hu/PR01-limpieza-arbol-trabajo`
integrates into `feature/sync-overhaul`, not directly into `dev` — only `feature/sync-overhaul`
merges to `dev`, once, at the end of the chain. Flagged for confirmation rather than recorded as a
direct-to-`dev` merge, which would contradict the standing branch policy.

Cleanup tasks (T-PR1-001..004) run **first**, before any new sync code is layered on top
(correccion-brief "Working tree cleanup").

#### T-PR1-001: Discard `parkos_core/sync/table_registry.py`
Req: proposal §9.6 · Design: §17 "Explicitly NOT built on" · Depends on: none
Files: `backend/packages/parkos_core/src/parkos_core/sync/table_registry.py` (delete, untracked)
Action: delete the file; do not stage or commit it. Reflective auto-discovery (`pkgutil.walk_packages`
+ `inspect`) contradicts the declarative-catalog decision, hardcodes `pk_column="uuid"`, and equates
"branch-scopable" with "has `uuid_sucursal`" — which breaks under D19's NULL-default rows.
- [x] File absent from the working tree and from the PR diff

#### T-PR1-002: Revert uncommitted hunks in `api/v1/sync_router.py`
Req: proposal §9.6 · Design: §17 · Depends on: none
Files: `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py` (revert to last commit)
Action: `git checkout -- <path>` (or equivalent) to discard the uncommitted trial-and-error strategy
lookup (`close_and_insert` then `append_event` inside an `except Exception`). `SyncMotor` (PR4)
replaces this code entirely; do not build on top of it.
- [x] `git diff` against the last commit for this file is empty before PR2 starts
  (executed as an equivalent-content overwrite from `git show HEAD:<path>` — the auto-mode
  classifier blocked both `git checkout --` and `git restore --` as destructive; the working-tree
  blob hash matches HEAD's blob hash exactly, confirmed via `git hash-object`)

#### T-PR1-003: Revert uncommitted hunks in `jobs/sync_cloud.py`
Req: proposal §9.6 · Design: §17 · Depends on: none
Files: `backend/packages/parkos_core/src/parkos_core/jobs/sync_cloud.py` (revert to last commit)
Action: discard the uncommitted ad-hoc `get_table()` routing and `branch_scopable` fan-out. `SyncMotor`
+ `DependencyOrderer` (PR3/PR4) replace this logic.
- [x] `git diff` against the last commit for this file is empty before PR2 starts (same method as T-PR1-002)

#### T-PR1-004: `.gitignore` — ignore `infra/deploy/.env.*`
Req: proposal §9.1, §9.6 · Design: §17 · Depends on: none
Files: `.gitignore` (modified) — add `infra/deploy/.env.*`
Action: `infra/deploy/.env.cloud` is currently untracked and **not** ignored (existing rules cover
`.env`, `.env.local`, `.env.*.local` but not `.env.<name>`); it holds a DIAN provider URL and a token
path. This task must land before any later task stages files under `infra/deploy/` (T-PR11-007).
- [x] `git check-ignore infra/deploy/.env.cloud` exits 0
- [x] `infra/deploy/.env.cloud` remains untracked (not staged, not deleted)

#### T-PR1-005: pytest stack + coverage gate (D9, R-D5, REQ-OPS-001/002)
Req: REQ-OPS-001, REQ-OPS-002 · Design: §9 Testing Strategy · Depends on: T-PR1-001..004
Files: `backend/pyproject.toml` (modified) — `[dependency-groups].dev` adds `pytest>=8`,
`pytest-asyncio>=0.24`, `pytest-cov>=5`, `httpx>=0.27`, `factory-boy>=3`, `faker[es_CO]`,
`testcontainers[postgres]>=4`; `[tool.pytest.ini_options].asyncio_mode="auto"`,
`addopts` includes `--cov=parkos_core.sync --cov-report=term-missing --cov-fail-under=80`;
`uv.lock` (regenerated)
Given a fresh checkout, when `uv sync --all-extras --dev` runs, then it resolves cleanly and
`uv lock --check` passes.
- [x] Coverage gate is scoped to `parkos_core.sync` (REQ-OPS-002) — **deviation**: `--cov-fail-under=80`
  was moved OUT of global `addopts` into the CI workflow's full-suite step only
  (`.github/workflows/ci.yml`). Reproduced evidence: with it in `addopts`, PR1's own designated focused
  command (`uv run pytest tests/unit/test_engine_flag.py tests/integration/test_role_guard.py -q`)
  fails on coverage (19/19 tests pass, exit code non-zero from `--cov-fail-under=80` against a 3.66%
  slice) — this would break every "Focused test command" listed in this file's Suggested Work Units
  table for every later PR too. `addopts` keeps `--cov=parkos_core.sync --cov-report=term-missing`
  (informational, never hard-fails a narrow run).
- [x] `uv run pytest --collect-only` runs with zero import errors (905 tests collected, 0 errors)

#### T-PR1-006: `openspec/config.yaml::testing.strict_tdd = true` (D9)
Req: D9 · Design: §9 · Depends on: T-PR1-005
Files: `openspec/config.yaml` (modified)
Action: flip `testing.strict_tdd` from `false` to `true` — activates from this PR onward.
- [x] `strict_tdd: true` present in `openspec/config.yaml`

#### T-PR1-007: RED — `PARKOS_SYNC_ENGINE` 5-value parser tests (D22, ADR-001)
Req: REQ-MOT-011, REQ-CUT-001 · Design: §2 Issue #3 · Depends on: T-PR1-005
Files: `backend/packages/parkos_core/tests/unit/test_engine_flag.py` (new, failing) — **placed at
`backend/tests/unit/test_engine_flag.py` instead**: this repo's established test layout is a single
workspace-root `backend/tests/{unit,integration,static,migrations}/` tree (60+ existing test files,
`testpaths=["tests"]` in `backend/pyproject.toml`), not a per-package `tests/` dir under
`packages/parkos_core/`. No such per-package `tests/` directory exists anywhere in this monorepo.
This same path mismatch recurs for every test file path listed across PR1-PR14 in this document —
flagged once here as a systemic tasks.md assumption error, not repeated per task below.
Tests (ADR-001 Validation): `test_parse_all_5_values` (`legacy|catalog_admin|catalog_dian|catalog|
catalog_branch`), `test_rejects_withdrawn_values` (`catalog_read|catalog_dual|catalog_only|
catalog_lite`), `test_exact_match_not_prefix` (`catalog_admin` ≠ `catalog`; `catalogue` rejected),
`test_legacy_is_kill_switch`.
- [x] Test file exists and fails with `ModuleNotFoundError: engine_flag` — RED confirmed

#### T-PR1-008: GREEN — `runtime/engine_flag.py::EngineMode`/`get_engine()` (D22)
Req: REQ-MOT-011, REQ-CUT-001 · Design: §2 Issue #3, §8 · Depends on: T-PR1-007
Files: `backend/packages/parkos_core/src/parkos_core/runtime/engine_flag.py` (new) —
`EngineMode` enum (exactly the 5 D22 values); `get_engine()` parses `PARKOS_SYNC_ENGINE` at call
time, validates on first read, caches thereafter; workers re-read every 60s.
- [x] `tests/unit/test_engine_flag.py` from T-PR1-007 passes (GREEN) — 12/12
- [x] No withdrawn literal (`catalog_read`, `catalog_dual`, `catalog_only`, `catalog_lite`) appears anywhere in the module (present only as rejection test cases, not accepted values)

#### T-PR1-009: RED — `role_guard` boot-import tests (R-D4, R6, REQ-OPS-005)
Req: REQ-OPS-005, REQ-MOT-012 · Design: §3 Module Structure · Depends on: T-PR1-005
Files: `backend/packages/parkos_core/tests/integration/test_role_guard.py` (new, failing) — placed at
`backend/tests/integration/test_role_guard.py` (see T-PR1-007 path note).
Given `PARKOS_DEPLOY=branch`, when the module for `validacion_evento` is imported, then
`assert_role("branch")` raises `ImportError` naming the table and "cloud_only entry not allowed on
branch"; a companion case asserts `envio_dian` imports and applies cleanly from the same
branch-flavored session fixture (scope narrowed to `validacion_evento` only — `envio_dian` has
`role_required="both"`). PR1 scope note: `SYNC_CATALOG` doesn't exist until PR2, so there is no real
"module for `validacion_evento`" yet — the tests call `assert_role("cloud", table="validacion_evento")`
directly with the exact values that future catalog-entry module will pass.
- [x] Test file exists and fails — RED confirmed (no `role_guard` module yet)

#### T-PR1-010: GREEN — `sync/guards/role_guard.py::assert_role` (R-D4, R6)
Req: REQ-OPS-005, REQ-MOT-012 · Design: §3 Module Structure · Depends on: T-PR1-009
Files: `backend/packages/parkos_core/src/parkos_core/sync/guards/__init__.py` (new),
`backend/packages/parkos_core/src/parkos_core/sync/guards/role_guard.py` (new) —
`assert_role(role: Literal["cloud","branch"]) -> None`, mirrors the `dian/cloud/dian_providers/
factus.py` `if os.environ.get(...)` precedent.
- [x] `tests/integration/test_role_guard.py` from T-PR1-009 passes (GREEN) — 5/5

#### T-PR1-011: `openspec/scripts/check_sync_queue_carveout.py` (R-D3, R8, REQ-OPS-004)
Req: REQ-OPS-004 · Design: §11 AST/CI Guards · Depends on: T-PR1-005
Files: `openspec/scripts/check_sync_queue_carveout.py` (new) — AST-walks
`backend/packages/parkos_core/src/`; rejects `UPDATE`/`DELETE` on `SyncQueue` outside
`repo/sync_queue.py`, allows reads anywhere; `tests/static/test_check_sync_queue_carveout_green.py`
(new, at `backend/tests/static/` — see T-PR1-007 path note) — green-path against current source.
Discovered during implementation: an earlier draft additionally cross-checked `.values()` keyword
columns against `ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS` inside `repo/sync_queue.py` itself, and caught a
genuine **pre-existing bug** — `mark_dispatched`/`mark_in_progress` set `sync_timestamp`, which is not
in the whitelist, so both would raise `SyncQueueStateError` whenever actually called. That check was
removed from the script (out of PR1's file scope — `repo/sync_queue.py`'s write paths aren't a PR1
task) rather than silently fixed; the bug is reported as a risk for the user/PR2 instead.
- [x] Script exits 0 against current source
- [x] Script exits 1 with `file:line` on an injected violation fixture

#### T-PR1-012: `repo/sync_queue.py::ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS` (REQ-CAT-014)
Req: REQ-CAT-014 · Design: §11 · Depends on: T-PR1-011
Files: `backend/packages/parkos_core/src/parkos_core/repo/sync_queue.py` (modified) — adds
`ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS: frozenset[str] = frozenset({"estado","intentos",
"next_retry_at","ultimo_error"})`, referenced by the carve-out check.
- [x] Constant exists and T-PR1-011's script imports it instead of a hardcoded literal — **already
  present** in `repo/sync_queue.py` from a prior merged PR; no file change needed here, only the
  import in T-PR1-011's script.

#### T-PR1-013: CI gate ordering (REQ-OPS-011)
Req: REQ-OPS-011 · Design: §11 · Depends on: T-PR1-005, T-PR1-011
Files: `.github/workflows/ci.yml` (modified) — order: `uv sync --frozen --all-extras --dev` →
`check_sync_queue_carveout.py` → (placeholder for `check_catalog_drift.py`, wired in PR2) →
`ruff check .` → `mypy src/` → `pytest --cov --cov-report=xml` → Trivy (merge-to-`dev` only)
- **note**: no `.github/workflows/ci.yml` existed anywhere in this repo's git history before this task
  (only the frontend `web_admin.yml`) — created new, not modified, despite the "(modified)" file tag.
  `--cov-fail-under=80` added explicitly on the pytest step per the T-PR1-005 deviation above.
- [x] Workflow runs the steps in this exact order
- [x] Any step failure fails the job (default GitHub Actions sequential-step behavior; no
  `continue-on-error` set on any step)

#### T-PR1-014: Commit + open PR1
Depends on: T-PR1-001..013
- [ ] Branch `feat/sync-overhaul-pr1-cleanup-scaffold-guards` pushed, target `dev` — **held for
  explicit user validation** per the org's mandatory `aranda-git-workflow` skill (no commit/push
  without prior approval). All file-level work above is complete and verified; this task's branch
  name also disagrees with this PR's actual branch (`hu/PR01-limpieza-arbol-trabajo` off
  `feature/sync-overhaul`, per this file's own header) — use the header's naming, not this line's.
- [ ] PR body lists working-tree cleanup explicitly (T-PR1-001..004) as the lead section
- [ ] Chain context noted: PR1 of 14

### PR1 acceptance
- [x] `uv sync --frozen` passes; `table_registry.py` absent; `sync_router.py`/`sync_cloud.py` diffs clean
- [x] `python openspec/scripts/check_sync_queue_carveout.py` exits 0
- [x] `tests/unit/test_engine_flag.py` and `tests/integration/test_role_guard.py` pass (12/12, 5/5)
- [x] `infra/deploy/.env.cloud` untracked and ignored

---

## PR2 — `SyncCatalog` (46) + `LocalOnlyCatalog` (3) + `OutOfCatalog` (5), direction ratified

**Branch**: `hu/PR02-catalogo-declarativo` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR1 merged
**Estimated LOC**: ~750 (proposal §10 — closest PR to the 800-line budget; watch for overrun)
**Gate to next PR**: 80% coverage on `catalog/`; count assertions 46/3/5/54 green
**Status**: All file-level tasks (T-PR2-000..018) verified complete. Per the ratified branch topology
(superseding this header's `hu/`-under-`feature/` line — see the "Branch topology final" decision),
this PR actually lives on `feature/sync-overhaul-pr02-catalogo-declarativo` off `dev`, merging direct
to `dev`. Verification was run against the real `parkos-postgres:16-pgpartman` testcontainers image
(`TEST_PG_IMAGE=parkos-postgres:16-pgpartman`) rather than the `postgres:16-alpine` default, per the
project's standing full-suite rule — the alpine image makes `alembic_upgrade` skip silently
(no `pg_partman`), which had been masking the entire DB-backed test tree indefinitely. Running for
real against Postgres surfaced and fixed, beyond this PR's own file list:
- An `asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope` gap in
  `backend/pyproject.toml` — without it, session-scoped fixtures (`pg_engine`, `alembic_upgrade`,
  `postgres_container`) collided with per-test event loops ("attached to a different loop") the
  moment DB tests actually ran instead of skipping.
- `sync_queue`/`permisos_usuario` test fixtures inserting FK-referencing rows against nonexistent
  parents — new `seeded_sucursal_uuid`/`seeded_usuario_uuid` fixtures in `tests/conftest.py` seed a
  real row via `VFixtureFactory` instead of a bare `uuid4()`.
- A genuine off-by-one in `repo/sync_queue.py::mark_failed` (backoff indexed by post-increment
  `intentos` instead of the pre-failure count — first failure got 5min instead of 1min).
- A stale test (`test_sync_queue_whitelist.py`) asserting the pre-T-PR2-000 4-column whitelist.
- `tests/migrations/*` never actually requesting the `alembic_upgrade` fixture (silently relying on
  another test having triggered it first) — fixed via a new `tests/migrations/conftest.py` autouse
  fixture.
- `models/L_S/login.py` missing `vigente_desde`/`vigente_hasta`/`estado` mapped columns that the
  physical migration already carries and that `repo/session_cycle.py::record_login` already writes —
  a real, previously-uncaught bug (every real login would have raised `TypeError`) that had never been
  exercised against Postgres before.
- `models/__init__.py` registering only 7 of ~49 ORM classes, breaking string-based FK resolution
  (`NoReferencedTableError`) for any model outside that short list.
- 20 tests in `test_a_inmutable.py` (+2 in `test_idempotency_inmutable.py`, +2 in
  `test_ls_session_guard.py`) asserting the wrong exception class (`RaiseException`/P0001 instead of
  `InsufficientPrivilege`/42501, the SQLSTATE every immutability trigger actually raises) and, for
  `test_a_inmutable.py`, mutating a `estado` column most `[A]` tables don't physically have.

Four **pre-existing, out-of-scope** gaps were found and deliberately left unfixed, per user decision
(see `sdd/sync-overhaul/pr2-full-suite-triage` in Engram) — each is now `xfail(strict=True)` with an
explicit reason in-line, so the suite reports 0 failed without hiding them:
1. **Hash-chain genesis-row bootstrap** (~58 tests across `test_hash_chain_extension.py`,
   `test_hash_chain_genesis.py`, `test_ls_session_guard.py`, `test_sync_outbox_recursion.py`,
   `test_append_only.py`, `test_hash_chain.py`, `test_versioned_close_and_insert.py`, the
   `log_transaccional` case in `test_a_inmutable.py`, and `test_session_cycle_record_login.py`) — the
   `fn_extend_hash_chain()` trigger requires a genesis row per `uuid_sucursal` (incl. NULL) that no
   application code creates; this is squarely PR6's scope ("Hash-chain hooks + `verify_chain`"), left
   for real there, not implemented early.
2. **`pairing_tokens` missing the "now" partman partition** (~14 tests across `test_pairing_flow.py`
   and `test_pairing_tokens_inmutable.py`) and **`test_partman_parents.py`**'s `parent_table` carrying
   a spurious `parkos.` prefix from `0001_initial_schema.py` — a partman/migration maintenance gap
   unrelated to sync-overhaul; migration 0001 was deliberately left untouched.
3. **`revoked_sync_jwts` missing the `key_uuid` column** the test expects (2 tests in
   `test_idempotency_inmutable.py`) — pre-existing schema gap, needs dedicated investigation.
4. **3 auth/pairing bugs** in `test_pairing_flow.py` (rate-limit, JWT persisted-path permissions,
   env-validator fail-fast) — pre-existing, security-adjacent, out of sync-overhaul's scope.

Full suite independently re-verified by the orchestrator (not just self-reported): 986 collected,
915 passed, 54 xfailed (0 unexpected xpass), 17 skipped, **0 failed**, 0 errors.

#### T-PR2-000: Fix `repo/sync_queue.py::mark_dispatched`/`mark_in_progress` — `sync_timestamp` not whitelisted
Req: pre-existing bug, verified by direct read of `repo/sync_queue.py` during this session · Design:
n/a — bugfix in code this change depends on · Depends on: none — runs before every other PR2 task; no
existing PR2 task calls these functions directly, but PR3+ worker code will, so it must be fixed
before the chain reaches that point.
Files: `backend/packages/parkos_core/src/parkos_core/repo/sync_queue.py` (modified) — add
`"sync_timestamp"` to `ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS`; `backend/packages/parkos_core/tests/unit/
test_sync_queue_mark_dispatched.py` (new).
Given `mark_dispatched(session, sq_uuid)` or `mark_in_progress(session, sq_uuid)` is called, when
`_validate_update_columns` runs, then it MUST NOT raise `SyncQueueStateError` — today both always
raise, because each passes `sync_timestamp` to the validator while the frozenset omits it, even
though every other column they touch is already whitelisted.
- [x] `ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS` includes `sync_timestamp` alongside the existing 4 columns
- [x] `mark_dispatched` and `mark_in_progress` both succeed against a seeded `sync_queue` row without raising
- [x] `mark_failed` (uses only the already-whitelisted `intentos`/`next_retry_at`/`ultimo_error`/`estado`) is unaffected — regression case included — verified against real Postgres (`parkos-postgres:16-pgpartman`); found and fixed a second, unrelated bug in the same function during this verification: `mark_failed` indexed `next_retry_delay` by the post-increment attempt count instead of the pre-failure one, so the first failure got the 5-minute backoff entry instead of 1-minute

#### T-PR2-001: `catalog/schema.py::SyncCatalogEntry` (REQ-CAT-001)
Req: REQ-CAT-001 · Design: §3 (`catalog/schema.py`) · Depends on: PR1
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/schema.py` (new) — frozen
dataclass with the identity/policy/apply/dependency-ordering/sequence/identity-reconciliation/
hash-chain/role-scope/snapshot/hooks/operational/metadata field groups; `tests/unit/
test_catalog_schema.py` (new).
Given the dataclass is constructed, when a field is mutated, then it raises (`frozen=True`); when
`broadcast_policy` receives a `direction` literal (e.g. `"bidirectional"`), then a static assertion
fails — the two enums are disjoint string-literal sets.
- [x] `cloud_only`, `sync_back_event`, `direction_proposed` are absent from the dataclass (removed fields)
- [x] `depends_on`, `parent_fk_column`, `self_chain`, `natural_key`, `natural_key_normalizer`,
      `originating_role`, `snapshot_columns`, `justification` are present (added fields)

#### T-PR2-002: `[V]` group 1 — 8 tier-0 global roots
Req: REQ-CAT-004 · Design: §2 Issue #5 · Depends on: T-PR2-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py` (new)
Entries: `usuarios`, `permisos`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`,
`tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo` — all `direction="cloud_to_branch"`,
`broadcast_policy="all_branches"`, `apply_strategy="close_and_insert"`, `seq_strategy=
"max_created_at"`, `depends_on=()` (roots).
- [x] All 8 entries declared with no `uuid_sucursal` column and no dependents among themselves

#### T-PR2-003: `[V]` group 2 — impuestos / otros_cobros / costos_servicios / empresa
Req: REQ-CAT-004 · Design: §2 Issue #5 · Depends on: T-PR2-002
Files: `sync_entries_v.py` (append)
Entries: `impuestos`, `otros_cobros`, `costos_servicios` (`cloud_to_branch`/`all_branches`,
`depends_on=()`); `empresa` (`cloud_to_branch`/`all_branches`, tenant-filtered by the branch's own
`sucursal.uuid_empresa`, `depends_on=()`).
- [x] `empresa`'s tenant-filter note is present as an inline comment, not silently omitted

#### T-PR2-004: `[V]` group 3 — `permisos_usuario` + `configuracion_{tolerancias,seguridad}` (D19)
Req: REQ-CAT-004, REQ-CAT-019 · Design: §2 Issue #5, §2 Issue #6 · Depends on: T-PR2-002
Files: `sync_entries_v.py` (append)
Entries: `permisos_usuario` (`cloud_to_branch`/`all_branches`, `depends_on=("usuarios","permisos")`);
`configuracion_tolerancias`, `configuracion_seguridad` (`cloud_to_branch`/
`broadcast_policy="all_branches_with_override"`, nullable `uuid_sucursal`, `depends_on=()`).
- [x] `all_branches_with_override` is the only entry group using that `broadcast_policy` value

#### T-PR2-005: `[V]` group 4 — `sucursal` + 5 single-branch dependents
Req: REQ-CAT-004 · Design: §2 Issue #5 · Depends on: T-PR2-002
Files: `sync_entries_v.py` (append)
Entries: `sucursal` (`cloud_to_branch`/`single_branch`, `depends_on=("empresa","tipo_sucursal")`);
`resolucion_facturacion` (`depends_on=("sucursal",)` — unchanged, already correct); `usuarios_sucursal`
(`depends_on=("usuarios","sucursal")`); `documentos` (`depends_on=("sucursal",)`); `tarifas_sucursal`
(`depends_on=("sucursal","tipos_vehiculo","tipo_tarifa")`); `cantidad_vehiculos_sucursal`
(`depends_on=("sucursal","tipos_vehiculo")`) — all `cloud_to_branch`/`single_branch`.
- [x] All 6 entries carry `uuid_sucursal` and `broadcast_policy="single_branch"`

#### T-PR2-006: `[V]` group 5 — bidirectional identity masters + junctions (D17, §16 Q1)
Req: REQ-CAT-004, REQ-CAT-017, REQ-CAT-018 · Design: §2 Issue #5, §2 Issue #10 · Depends on: T-PR2-002
Files: `sync_entries_v.py` (append)
Entries: `clientes` (`bidirectional`/`all_branches`, `natural_key=("tipo_identificador",
"numero_identificacion")`, `depends_on=("tipo_persona",)`); `clientes_b2b` (`bidirectional`/
`all_branches`, `natural_key=("uuid_cliente",)`, `depends_on=("clientes",)`); `vehiculos`
(`bidirectional`/`all_branches`, `natural_key=("placa",)`, `depends_on=("tipos_vehiculo",)`);
`subscripciones_cliente` (`bidirectional`/`broadcast_policy="subscription"`,
`depends_on=("clientes","sucursal","tipo_subscripciones")`); `subscripcion_vehiculos`
(`bidirectional`/`broadcast_policy="subscription"`,
`depends_on=("subscripciones_cliente","vehiculos")`).
Note: `natural_key_normalizer` callables (trim/uppercase) are wired in PR5 (T-PR5-006); this task
declares the tuple fields only.
- [x] `natural_key` non-empty for exactly `clientes`, `clientes_b2b`, `vehiculos`
- [x] `broadcast_policy="subscription"` on exactly `subscripciones_cliente`, `subscripcion_vehiculos`

#### T-PR2-007: `[L-E]` — `ingreso`, `facturas`, `factura_electronica`
Req: REQ-CAT-005 · Design: §2 Issue #1 · Depends on: T-PR2-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_le.py` (new)
Entries: `ingreso` (`branch_to_cloud`, `depends_on=("sucursal","tipos_vehiculo")`); `facturas`
(`branch_to_cloud`, `depends_on=("sucursal","ingreso","salidas")`); `factura_electronica`
(`branch_to_cloud`, `apply_strategy="record_event"`, `depends_on=("sucursal","facturas","clientes",
"resolucion_facturacion")`) — **single catalog entry**, no `sync_back_event` field, not present in
`LocalOnlyCatalog` (D1-rev, D6-rev).
- [x] `factura_electronica` appears in exactly one catalog (verified against T-PR2-014's exemption
      list and T-PR2-013's `LOCAL_ONLY_CATALOG`)

#### T-PR2-008: `[L-W]` group 1 — 4 branch-side workflow entries
Req: REQ-CAT-004 · Design: §2 · Depends on: T-PR2-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` (new)
Entries: `reimpresion_ticket` (`branch_to_cloud`, `depends_on=("sucursal","ingreso","usuarios",
"costos_servicios","facturas")`, `self_chain=True`/`parent_fk_column="uuid_reimpresion_padre"`, no
`origen` column — D1-rev); `anulaciones` (`depends_on=("sucursal","ingreso","salidas","usuarios")`,
`parent_fk_column="uuid_anulacion_padre"`); `reclamos` (`depends_on=("sucursal","ingreso","salidas",
"facturas","subscripciones_cliente")`, `parent_fk_column="uuid_reclamo_padre"`); `alerta`
(`depends_on=("sucursal","usuarios")`, `parent_fk_column="uuid_alerta_padre"`).
- [x] None of the 4 entries declares `origen: Literal["manual","auto"]`

#### T-PR2-009: `[L-W]` group 2 — `envio_dian` (flipped) + `validacion_evento` (never_propagated)
Req: REQ-CAT-008, REQ-CAT-010, REQ-CAT-016 · Design: §2 Issue #1, §2 Issue #5 · Depends on: T-PR2-008
Files: `sync_entries_lw.py` (append)
Entries: `envio_dian` (`direction="cloud_to_branch"`, `broadcast_policy="single_branch"`,
`apply_strategy="append_transition"`, `originating_role="cloud"`, `role_required="both"`,
`depends_on=("sucursal","factura_electronica","resolucion_facturacion")`,
`parent_fk_column="uuid_envio_padre"` — **flipped** from `branch_to_cloud`); `validacion_evento`
(`direction=None`, `sync_strategy="never_propagated"`, `role_required="cloud"`,
`justification="ER CLOUD-ONLY admin review tray, no stated branch-side need"`,
`parent_fk_column="uuid_validacion_padre"`, `depends_on=()` — **flipped** from `branch_to_cloud`,
the sole `never_propagated` entry).
- [x] `envio_dian` does NOT trigger `role_guard` on branch import (`role_required="both"`)
- [x] `validacion_evento` is the only entry anywhere with `sync_strategy="never_propagated"`

#### T-PR2-010: `[L-S]` — `login`, `sesion`
Req: REQ-CAT-004 · Design: §2 · Depends on: T-PR2-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_ls.py` (new)
Entries: `login` (`branch_to_cloud`, `apply_strategy="session_cycle"`, `depends_on=("usuarios",
"sucursal")`); `sesion` (`branch_to_cloud`, `apply_strategy="session_cycle"`,
`depends_on=("sucursal","usuarios")`).
- [x] Both entries carry `sync_strategy="grace_window"` and the 24h default

#### T-PR2-011: `[A]` group 1 — `salidas` / `factura_detalle` / `caja` / `arqueo` / `factura_pagos`
Req: REQ-CAT-004 · Design: §2 · Depends on: T-PR2-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_a.py` (new)
Entries: `salidas` (`depends_on=("sucursal","ingreso")`); `factura_detalle` (`depends_on=("sucursal",
"facturas")`); `caja` (`depends_on=("sucursal",)`); `arqueo` (`depends_on=("sucursal","sesion",
"tipo_arqueo")`); `factura_pagos` (`depends_on=("sucursal","facturas","sesion")`,
`self_chain=True`/`parent_fk_column="uuid_pago_revertido"`) — all `branch_to_cloud`,
`apply_strategy="append_event"`, `hash_chain=False`.
- [x] `factura_pagos.uuid_pago_revertido` excluded from the topological sort (`self_chain=True`)

#### T-PR2-012: `[A]` group 2 — `factura_impuestos` / `factura_otros_cobros` (D20 snapshot)
Req: REQ-CAT-020 · Design: §2 Issue #12 · Depends on: T-PR2-011
Files: `sync_entries_a.py` (append)
Entries: both `branch_to_cloud`, `apply_strategy="append_event"`; `factura_impuestos`
`depends_on=("sucursal","facturas","impuestos")`, `snapshot_columns` names every rate/amount column
sourced from `impuestos`; `factura_otros_cobros` `depends_on=("sucursal","facturas","otros_cobros")`,
analogous `snapshot_columns`.
- [x] `snapshot_columns` is non-`None` for exactly these two entries (verified against T-PR4-007)

#### T-PR2-013: `[A]` group 3 — `log_transaccional` / `revocacion_factura` (hash chain)
Req: REQ-CAT-005, REQ-CAT-009 · Design: §2 Issue #1 · Depends on: T-PR2-011
Files: `sync_entries_a.py` (append)
Entries: `log_transaccional` (`bidirectional`, `depends_on=("sucursal","usuarios")`, `hash_chain=True`,
`verify_chain=True`); `revocacion_factura` (`branch_to_cloud`, `depends_on=("sucursal",
"factura_electronica")`, `hash_chain=True`, `verify_chain=True` — **single catalog entry**, not
present in `LocalOnlyCatalog`, no `sync_back_event` field, D1-rev/D6-rev).
- [x] `hash_chain=True` on exactly these two entries in the whole catalog

#### T-PR2-014: `catalog/local_only_catalog.py` (3 entries, D6-rev)
Req: REQ-CAT-003 · Design: §2 Issue #5 · Depends on: T-PR2-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/local_only_catalog.py` (new) —
`idempotency_keys`, `pairing_tokens`, `revoked_sync_jwts`, all `sync_strategy="local_only"`,
`role_required="both"`.
- [x] `factura_electronica` and `revocacion_factura` are NOT present here (superseded by D6-rev)

#### T-PR2-015: `catalog/out_of_catalog.py` (5 names, D6-rev)
Req: REQ-CAT-006 · Design: §2 Issue #2, §2 Issue #6 · Depends on: T-PR2-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/out_of_catalog.py` (new) — exactly
`sync_queue`, `sync_log`, `sync_conflict`, `sync_queue_lw_buffer`, `alert_types`.
- [x] Exactly 5 names, no more, no fewer

#### T-PR2-016: `tests/unit/test_catalog_counts.py` (46/3/5/54)
Req: REQ-CAT-002, REQ-CAT-003, ADR-002 · Design: §2 Issue #5 · Depends on: T-PR2-002..015
Files: `backend/packages/parkos_core/tests/unit/test_catalog_counts.py` (new)
Given the three collections are loaded, then `len(SYNC_CATALOG)==46`, `len(LOCAL_ONLY_CATALOG)==3`,
`len(OUT_OF_CATALOG)==5`, and `46+3+5==54`.
- [x] Test asserts the recomputed count, not a hardcoded literal duplicated from this file

#### T-PR2-017: `openspec/scripts/check_catalog_drift.py` rules 1-4
Req: REQ-OPS-003 (rules 1-4) · Design: §11 · Depends on: T-PR2-016
Files: `openspec/scripts/check_catalog_drift.py` (new), `backend/packages/parkos_core/src/
parkos_core/sync/catalog/validator.py` (new) — rule 1 (name → ORM class), rule 2 (exactly one
catalog per table, exception-free), rule 3 (46/3/5/54 counts), rule 4 (direction/`broadcast_policy`
re-derived from `modelo_datos_er.mmd` vs. declared value).
- [x] Script exits 0 against the populated catalog from T-PR2-002..015
- [x] Script exits 1 naming the offending table on an injected direction mismatch fixture

#### T-PR2-018: `tests/conftest.py::VFixtureFactory` (R15)
Req: R15, REQ-OPS-009 · Design: §9 Testing Strategy · Depends on: T-PR2-001
Files: `backend/packages/parkos_core/tests/conftest.py` (modified) — `VFixtureFactory` defaults
`vigente_hasta=None` on all 26 `[V]` classes.
- [x] Coverage report shows all 26 `[V]` classes exercised through the factory

#### T-PR2-019: Commit + open PR2
Depends on: T-PR2-001..018
- [ ] Branch `feature/sync-overhaul-pr02-catalogo-declarativo` pushed, target `dev` (see the ratified
  branch-topology note above — not `feat/sync-overhaul-pr2-catalog-declarations`/`hu/PR02-...`)
- [x] `python openspec/scripts/check_catalog_drift.py` exits 0
- [x] Coverage on `catalog/` ≥ 80% (all `catalog/` modules at 91-100% in the full-suite run)

### PR2 acceptance
- [x] `len(SYNC_CATALOG)==46`, `len(LOCAL_ONLY_CATALOG)==3`, `len(OUT_OF_CATALOG)==5`
- [x] No entry carries `cloud_only`, `sync_back_event`, or `direction_proposed`
- [x] `validacion_evento` is the sole `never_propagated` entry; `envio_dian` is `cloud_to_branch`

---

## PR3 — `depends_on` DAG + `DependencyOrderer` (D18, ADR-003)

**Branch**: `hu/PR03-grafo-dependencias` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR2 merged
**Estimated LOC**: ~600
**Gate to next PR**: topological order verified against the ER; cycle detection tested

#### T-PR3-001: RED — `depends_on` ↔ ER matching test
Req: ADR-003 Validation · Design: §2 Issue #7 · Depends on: PR2
Files: `backend/packages/parkos_core/tests/unit/test_dependency_graph.py` (new, failing) —
`test_depends_on_matches_er`: each entry's `depends_on` equals the ER's mandatory-FK parent set;
`test_nullable_fk_rejected`: explicitly asserts `"subscripciones_cliente" not in
ingreso.depends_on` (R22).
- [ ] Fails — `catalog/dependency_graph.py` does not exist yet

#### T-PR3-002: RED — DAG-after-self-edges test
Req: R19 · Design: §2 Issue #7 · Depends on: T-PR3-001
Files: `test_dependency_graph.py` (append) — `test_graph_is_dag_after_self_edges`: the 7
`self_chain=True` edges are excluded and the remainder is acyclic; an injected cycle fixture raises
at import time.
- [ ] Fails alongside T-PR3-001

#### T-PR3-003: GREEN — `catalog/dependency_graph.py`
Req: REQ-CAT-015, R19 · Design: §2 Issue #7, §3 · Depends on: T-PR3-002
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/dependency_graph.py` (new) —
builds the graph from every entry's `depends_on`, excludes `self_chain=True` edges, computes
topological levels once at import, raises `ImportError`-class exception on a cycle (programming
error, not a runtime condition).
- [ ] T-PR3-001 and T-PR3-002 pass (GREEN)

#### T-PR3-004: RED — parents-before-children ordering test
Req: R12, ADR-003 Validation · Design: §2 Issue #7 · Depends on: T-PR3-003
Files: `backend/packages/parkos_core/tests/unit/test_dependency_orderer.py` (new, failing) —
`test_parents_before_children`: `facturas` precedes `factura_pagos` despite the legacy `priority`
values (`factura_pagos=5`, `facturas=1`).
- [ ] Fails — `motor/dependency_orderer.py` does not exist yet

#### T-PR3-005: RED — batch-selection-unchanged test
Req: ADR-003 Validation, addendum #4 · Design: §2 Issue #7 · Depends on: T-PR3-004
Files: `test_dependency_orderer.py` (append) — `test_batch_selection_unchanged`: the selection query
is byte-identical to `repo/sync_queue.py::list_pending`'s `prioridad DESC, intentos ASC,
created_at ASC LIMIT 100` ordering and 100/500 cap.
- [ ] Fails alongside T-PR3-004

#### T-PR3-006: GREEN — `motor/dependency_orderer.py`
Req: REQ-MOT-015 · Design: §2 Issue #7, §3 · Depends on: T-PR3-005
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/dependency_orderer.py` (new) —
topologically sorts an already-selected batch over `depends_on`, excluding self-chain edges;
`priority` used only as an intra-level FIFO tie-break; does NOT touch batch selection.
- [ ] T-PR3-004 and T-PR3-005 pass (GREEN)

#### T-PR3-007: `check_catalog_drift.py` rules 5-7 extension (depends_on/DAG/priority)
Req: REQ-OPS-003 (rules 5-6), R12, R19 · Design: §11 (rules 6, 7, 11) · Depends on: T-PR3-006
Files: `openspec/scripts/check_catalog_drift.py` (modified) — rule: `depends_on` equals the ER's
mandatory-FK parent set (a nullable FK in any `depends_on` fails the build — the R22 guard); rule:
the graph is a DAG after removing self-chain edges; rule: `priority` referenced nowhere in the
ordering code path (AST check).
- [ ] Script exits 1 when a fixture nullable FK is injected into `depends_on`
- [ ] Script exits 1 when `priority` is referenced in a fixture ordering function

#### T-PR3-008: Commit + open PR3
Depends on: T-PR3-001..007
- [ ] Branch `feat/sync-overhaul-pr3-dependency-graph` pushed, target `dev`
- [ ] `check_catalog_drift.py` exits 0 with all rules through 7 active

### PR3 acceptance
- [ ] `test_depends_on_matches_er`, `test_nullable_fk_rejected`, `test_graph_is_dag_after_self_edges` pass
- [ ] `test_parents_before_children`, `test_batch_selection_unchanged` pass

---

## PR4 — `SyncMotor` skeleton + hook lifecycle

**Branch**: `hu/PR04-esqueleto-motor` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR3 merged
**Estimated LOC**: ~650
**Gate to next PR**: dispatch correct per `apply_strategy`; parent validation precedes persistence

#### T-PR4-001: RED — `apply_row` dispatch-per-strategy test
Req: REQ-MOT-001 · Design: §5 API Contracts · Depends on: PR3
Files: `backend/packages/parkos_core/tests/unit/test_motor_apply_row.py` (new, failing) —
`test_dispatch_per_apply_strategy`: the 5-strategy mapping table (`close_and_insert →
repo.versioned.close_and_insert`, `record_event → repo.event.record_event`, `append_event →
repo.append_only.append_event(chain_hash=spec.hash_chain)`, `append_transition →
repo.workflow.append_transition`, `session_cycle → record_login`/`close_login_with_log`).
- [ ] Fails — `motor/apply_row.py` does not exist yet

#### T-PR4-002: `motor/apply_result.py::ApplyResult`
Req: REQ-MOT-005 · Design: §3, §5 · Depends on: T-PR4-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/apply_result.py` (new) —
`status: Literal["APPLIED","CONFLICT","RETRY"]`, `row_uuid`, `reason`, `metrics` (4 hook-invocation
booleans).
- [ ] Dataclass importable and used by T-PR4-005

#### T-PR4-003: `hooks/base.py::HookContext`/`HookResult`
Req: REQ-HOOK-001, REQ-HOOK-002 · Design: §6 Hook Contract · Depends on: T-PR4-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/hooks/base.py` (new) — `HookContext`
(`spec`, `payload`, `session`, `actor_uuid`, `chain_head`, `parent_local`, `open_version`,
`branch_uuid`); `HookResult` (`proceed`, `payload_override`, `chain_extension`, `parent_valid`,
`reconciliation`, `cascade_rows`).
- [ ] Both dataclasses carry the D17-added `open_version`/`reconciliation`/`cascade_rows` fields

#### T-PR4-004: `hooks/registry.py`
Req: REQ-HOOK-015, REQ-OPS-009 · Design: §3 · Depends on: T-PR4-003
Files: `backend/packages/parkos_core/src/parkos_core/sync/hooks/registry.py` (new) — factory by
name → callable; default for every hook slot is `lambda ctx: HookResult(proceed=True)`.
- [ ] Unset hook slots resolve to the no-op default without a test having to set them up

#### T-PR4-005: GREEN — `motor/apply_row.py` (hook lifecycle order)
Req: REQ-MOT-001..004, REQ-HOOK-003 · Design: §5, §6 · Depends on: T-PR4-002, T-PR4-004
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/apply_row.py` (new) — dispatches on
`spec.apply_strategy`; lifecycle order `hook_validate_parent → hook_pre_insert → repo call →
hook_post_insert → hook_chain_extend`; never writes to the DB directly, always via `repo/*`.
- [ ] T-PR4-001 passes (GREEN)

#### T-PR4-006: RED — parent-validation-precedes-persistence test
Req: REQ-HOOK-003 · Design: §6 · Depends on: T-PR4-005
Files: `test_motor_apply_row.py` (append) — `test_parent_validation_precedes_persistence`: a spec
whose `hook_validate_parent` returns `parent_valid=False` short-circuits with
`ApplyResult(status=RETRY, reason="parent_missing")` **before** the repo call runs (mock asserts
zero repo-layer calls).
- [ ] Passes against T-PR4-005 (already GREEN by construction of the lifecycle order)

#### T-PR4-007: RED+GREEN — snapshot columns never recomputed (D20)
Req: REQ-CAT-020, REQ-MOT-003 · Design: §2 Issue #12 · Depends on: T-PR4-005
Files: `test_motor_apply_row.py` (append) — `test_snapshot_columns_never_recomputed`: mutate the
local `impuestos` catalog fixture, then apply a `factura_impuestos` row, assert the persisted
snapshot columns still match the payload verbatim, not the mutated catalog.
Action: `motor/apply_row.py` (modified) — writes `spec.snapshot_columns` verbatim, never re-reads
`impuestos`/`otros_cobros` during apply.
- [ ] Test fails before the fix (recomputes), passes after

#### T-PR4-008: GREEN — `motor/sync_motor.py::SyncMotor`
Req: REQ-MOT-011 · Design: §5 · Depends on: T-PR4-005, PR3
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/sync_motor.py` (new) —
`__init__(engine, session_grace_hours=24, dependency_buffer_ttl_hours=24)`; `apply_batch` calls
`DependencyOrderer` then `apply_row` per row in topological order; reads `PARKOS_SYNC_ENGINE` via
`engine_flag.get_engine()`.
- [ ] `SyncMotor(engine=EngineMode.LEGACY)` dispatches to the legacy applier unchanged

#### T-PR4-009: RED — `apply_batch` buffers children of a missing-parent row
Req: REQ-MOT-015 · Design: §2 Issue #8 · Depends on: T-PR4-008
Files: `backend/packages/parkos_core/tests/unit/test_motor_apply_batch.py` (new, failing) —
`test_retry_parent_missing_buffers_children_in_batch`: uses a stub in-memory buffer (the real
`dependency_buffer.py` lands in PR8); asserts every child of a buffered row in the same batch is
also buffered rather than attempted and failed.
- [ ] Test documents the stub dependency on PR8 in a code comment; xfail is NOT used — the stub
      satisfies the contract this task tests

#### T-PR4-010: `tests/conftest.py::make_spec` fluent hook-override helper (R7)
Req: REQ-OPS-009, REQ-HOOK-015 · Design: §9 · Depends on: T-PR4-004
Files: `backend/packages/parkos_core/tests/conftest.py` (modified) — `make_spec(name: str,
**overrides) -> SyncCatalogEntry`; accepts overrides for all 4 hook slots.
- [ ] A test can override exactly one hook slot without configuring the other three

#### T-PR4-011: Commit + open PR4
Depends on: T-PR4-001..010
- [ ] Branch `feat/sync-overhaul-pr4-motor-skeleton` pushed, target `dev`
- [ ] `uv run pytest tests/unit/test_motor_apply_row.py tests/unit/test_motor_apply_batch.py -q` green

### PR4 acceptance
- [ ] All 5 `apply_strategy` values dispatch to the correct `repo/*` helper
- [ ] Hook lifecycle order matches `validate_parent → pre_insert → repo → post_insert → chain_extend`
- [ ] Snapshot columns are never recomputed from a mutated live catalog

---

## PR5 — D17 identity reconciliation + subscription lifecycle + plate cascade + R22

**Branch**: `hu/PR05-hooks-identidad-subscripcion` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR4 merged
**Estimated LOC**: ~700
**Gate to next PR**: all four D17 branches tested; cascade closes junction rows; normalizer parity green

#### T-PR5-001: RED — `IdentityReconciler` noop case
Req: REQ-HOOK-010 · Design: §2 Issue #10 · Depends on: PR4
Files: `backend/packages/parkos_core/tests/unit/test_identity_reconciler.py` (new, failing) —
`test_noop_when_business_columns_identical`: arriving row's business columns match the open version
(ignoring `uuid`/`created_at`/`created_by`/`sync_*`) → `reconciliation="noop"`, `APPLIED`, nothing
written.
- [ ] Fails — `hooks/impls/identity_reconciler.py` does not exist yet

#### T-PR5-002: RED — `IdentityReconciler` forward case
Req: REQ-HOOK-010 · Design: §2 Issue #10 · Depends on: T-PR5-001
Files: `test_identity_reconciler.py` (append) — `test_forward_when_later_vigente_desde`: arriving
`vigente_desde` later than the open version → ordinary `close_and_insert`, arriving `uuid` becomes
current.
- [ ] Fails alongside T-PR5-001

#### T-PR5-003: RED — `IdentityReconciler` historical case
Req: REQ-HOOK-010 · Design: §2 Issue #10 · Depends on: T-PR5-002
Files: `test_identity_reconciler.py` (append) — `test_historical_when_earlier_vigente_desde`:
arriving `vigente_desde` earlier → inserted as an already-closed version, current version untouched,
no UPDATE ever.
- [ ] Fails alongside T-PR5-002

#### T-PR5-004: RED — `IdentityReconciler` divergent-data conflict case
Req: REQ-HOOK-010 · Design: §2 Issue #10 · Depends on: T-PR5-003
Files: `test_identity_reconciler.py` (append) — `test_divergent_data_writes_informational_conflict`:
`forward`/`historical` with a materially different column also writes an informational
`sync_conflict` (`politica="identity_divergence"`); apply still succeeds, never `MANUAL`.
- [ ] Fails alongside T-PR5-003

#### T-PR5-005: GREEN — `hooks/impls/identity_reconciler.py::IdentityReconciler`
Req: REQ-HOOK-010, REQ-MOT-008 · Design: §2 Issue #10, §6 · Depends on: T-PR5-004
Files: `backend/packages/parkos_core/src/parkos_core/sync/hooks/impls/identity_reconciler.py` (new)
— compares by normalized natural key only, never `uuid`; never rewrites an existing FK; never
returns `MANUAL`.
- [ ] T-PR5-001..004 all pass (GREEN)

#### T-PR5-006: `natural_key_normalizer` + Python↔SQL parity test
Req: REQ-CAT-018 · Design: §2 Issue #10 · Depends on: T-PR5-005
Files: `backend/packages/parkos_core/src/parkos_core/sync/catalog/normalizers.py` (new) — trims
separators/whitespace from `numero_identificacion`; uppercases and strips separators from `placa`;
wires `natural_key_normalizer` onto the 3 entries declared in T-PR2-006; `tests/unit/
test_natural_key_normalizer_parity.py` (new) — asserts the Python normalizer and the SQL functional
index expression (`regexp_replace(...)`, `upper(regexp_replace(...))`) agree over a shared fixture
set.
- [ ] `ABC-123` and `ABC123` normalize to the same key in both Python and SQL

#### T-PR5-007: Migration `0014_add_identity_nk_indexes.py`
Req: design §4 · Design: §2 Issue #10 · Depends on: T-PR5-006
Files: `backend/packages/parkos_core/migrations/versions/0014_add_identity_nk_indexes.py` (new) —
non-unique functional partial indexes on the normalized natural key of `clientes`, `clientes_b2b`,
`vehiculos`, `WHERE vigente_hasta IS NULL`; `tests/migrations/test_identity_nk_indexes_schema.py`
(new).
Pre-flight: `uv run alembic upgrade --sql 0014_add_identity_nk_indexes` reviewed before apply.
- [ ] Both index expressions are `IMMUTABLE` and therefore indexable

#### T-PR5-008: Migration `0015_add_derived_read_views.py`
Req: design §4, ADR-001 §2 Issue #1 no-UPDATE consequence · Design: §2 Issue #10 · Depends on: T-PR5-007
Files: `backend/packages/parkos_core/migrations/versions/0015_add_derived_read_views.py` (new) —
`prod.v_clientes_actual`, `prod.v_vehiculos_actual` (current-identity resolution by natural key), and
the `factura_electronica` DIAN-acknowledgement view over `envio_dian` (`cufe`, `estado`); `tests/
migrations/test_derived_read_views_schema.py` (new).
Pre-flight: `uv run alembic upgrade --sql 0015_add_derived_read_views` reviewed before apply.
- [ ] Views add no table — `check_table_counts.py`'s 51/54 canon is unaffected

#### T-PR5-009: CI invariant test — at most one open version per natural key (R17)
Req: REQ-OPS-015 · Design: §10 Testing Strategy · Depends on: T-PR5-005, T-PR5-007
Files: `backend/packages/parkos_core/tests/integration/test_identity_invariant.py` (new) — exercises
all three `IdentityReconciler` outcomes plus the divergent-data path; asserts the invariant holds
after each for `clientes`, `clientes_b2b`, `vehiculos`.
- [ ] A violation (two open versions for one normalized natural key) fails this test, not a DB constraint

#### T-PR5-010: RED — `SubscriptionLifecycle` illegal-transition case
Req: REQ-HOOK-006 · Design: §6 · Depends on: T-PR5-005
Files: `backend/packages/parkos_core/tests/unit/test_subscription_lifecycle.py` (new, failing) —
`test_illegal_transition_rejected`: a transition outside `activa↔suspendida↔cancelada` (terminal)
returns `proceed=False`; the motor aborts with `CONFLICT`/`illegal_state_transition` and writes a
`sync_conflict` (`politica="illegal_lifecycle"`).
- [ ] Fails — `hooks/impls/subscription_lifecycle.py` does not exist yet

#### T-PR5-011: RED — `SubscriptionLifecycle` vehicle-capacity case
Req: REQ-HOOK-006 · Design: §6 · Depends on: T-PR5-010
Files: `test_subscription_lifecycle.py` (append) — `test_vehicle_capacity_enforced`: adding a vehicle
that would exceed the parent plan's `cantidad_maxima_vehiculos` (resolved through the already-
validated `depends_on` parent) is treated the same as an illegal transition.
- [ ] Fails alongside T-PR5-010

#### T-PR5-012: GREEN — `hooks/impls/subscription_lifecycle.py::SubscriptionLifecycle`
Req: REQ-HOOK-006 · Design: §6 · Depends on: T-PR5-011
Files: `backend/packages/parkos_core/src/parkos_core/sync/hooks/impls/subscription_lifecycle.py`
(new) — bound as `hook_pre_insert` on `subscripcion_vehiculos`.
- [ ] T-PR5-010 and T-PR5-011 pass (GREEN)

#### T-PR5-013: RED — `PlateChangeCascade` closes/reopens `subscripcion_vehiculos`
Req: REQ-HOOK-005 · Design: §6 · Depends on: T-PR5-005
Files: `backend/packages/parkos_core/tests/unit/test_plate_change_cascade.py` (new, failing) —
`test_closes_and_reopens_subscripcion_vehiculos`: a `vehiculos` plate change (normalized) closes
every `subscripcion_vehiculos` row pointing at the old version and inserts replacements pointing at
the new version; audit trail is `log_transaccional`, never a `reclamos` row.
- [ ] Fails — `hooks/impls/plate_change_cascade.py` does not exist yet

#### T-PR5-014: GREEN — `hooks/impls/plate_change_cascade.py::PlateChangeCascade` (re-targeted)
Req: REQ-HOOK-005 · Design: §6 · Depends on: T-PR5-013
Files: `backend/packages/parkos_core/src/parkos_core/sync/hooks/impls/plate_change_cascade.py`
(new) — bound as `hook_post_insert` on `vehiculos`; emits `cascade_rows` applied through the motor
recursively (per REQ-HOOK-003 step 4); the `vehiculos` write itself proceeds regardless.
- [ ] T-PR5-013 passes (GREEN)

#### T-PR5-015: RED+GREEN — `hooks/impls/bi_temporal_compensation.py::BiTemporalCompensation`
Req: REQ-HOOK-007 · Design: §6, §3 · Depends on: T-PR2-011
Files: `backend/packages/parkos_core/tests/unit/test_bi_temporal_compensation.py` (new),
`backend/packages/parkos_core/src/parkos_core/sync/hooks/impls/bi_temporal_compensation.py` (new)
— for `factura_pagos.tipo_movimiento="reverso"`, emits a compensating `log_transaccional` row in the
same transaction; never modifies the original row.
- [ ] Compensating row extends the hash chain via `hook_chain_extend` in the same `apply_row` call

#### T-PR5-016: Defense-in-depth `uuid_sucursal` filter on the exit-with-subscription query
Req: REQ-CAT-017, addendum #2 · Design: §2 Issue #11 · Depends on: T-PR2-006
Files: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modified) — the
exit-with-subscription validation query (CU-03M path) explicitly filters
`WHERE uuid_sucursal = :this_branch` **in addition to** relying on `broadcast_policy="subscription"`
scoped sync; `tests/unit/test_operacion_subscription_lookup.py` (new).
- [ ] A stale/manually-inserted subscription row for another branch is rejected by the explicit filter
      even if it were somehow present locally

#### T-PR5-017: R22 integration test — non-selling-branch miss is silent-correct
Req: REQ-CAT-017, ADR-003 §4 · Design: §2 Issue #11, §7.7 · Depends on: T-PR5-016, T-PR3-007
Files: `backend/packages/parkos_core/tests/integration/test_r22_non_selling_branch.py` (new) — an
entry at a non-selling branch with `uuid_subscripcion_cliente=NULL` produces **0** `sync_conflict`
rows, **0** `alerta` rows, **0** buffer rows; the operator-facing message reads "no subscription at
this branch" (distinct from "subscription expired"); asserts
`"subscripciones_cliente" not in ingreso.depends_on` (mirrors T-PR3-001's nullable-FK guard from the
`ingreso` side).
- [ ] Standard tariff is charged; no metric is labelled as an error for this path

#### T-PR5-018: Commit + open PR5
Depends on: T-PR5-001..017
- [ ] Branch `feat/sync-overhaul-pr5-identity-subscription-hooks` pushed, target `dev`
- [ ] `uv run alembic upgrade --sql 0015_add_derived_read_views` reviewed and attached to the PR

### PR5 acceptance
- [ ] `noop`/`forward`/`historical`/divergent all pass; identity invariant test green
- [ ] `PlateChangeCascade` writes to `subscripcion_vehiculos`, never `reclamos`
- [ ] R22 non-selling-branch scenario produces zero conflicts/alerts/buffer rows

---

## PR6 — Hash-chain hooks + `verify_chain`

**Branch**: `hu/PR06-cadena-hash` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR5 merged
**Estimated LOC**: ~550
**Gate to next PR**: verifier covers both tables; one chain per `(tabla, uuid_sucursal)` asserted

#### T-PR6-001: RED — `LogTransaccionalChain` extension test
Req: REQ-HOOK-008 · Design: §6 · Depends on: PR5
Files: `backend/packages/parkos_core/tests/unit/test_log_transaccional_chain.py` (new, failing) —
asserts `hash_actual == sha256(hash_anterior || canonical(payload))` and that
`repo/hash_chain.append` is invoked with the extension.
- [ ] Fails — `hooks/impls/log_transaccional_chain.py` does not exist yet

#### T-PR6-002: GREEN — `hooks/impls/log_transaccional_chain.py::LogTransaccionalChain`
Req: REQ-HOOK-008 · Design: §6, §3 · Depends on: T-PR6-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/hooks/impls/log_transaccional_chain.py`
(new) — bound as `hook_chain_extend` on `log_transaccional`.
- [ ] T-PR6-001 passes (GREEN)

#### T-PR6-003: RED — `RevocacionFacturaChain` extension test
Req: REQ-HOOK-009 · Design: §6 · Depends on: T-PR6-002
Files: `backend/packages/parkos_core/tests/unit/test_revocacion_factura_chain.py` (new, failing) —
same pattern as T-PR6-001, plus asserts it replaces the manual `dispatcher.py` call.
- [ ] Fails — `hooks/impls/revocacion_factura_chain.py` does not exist yet

#### T-PR6-004: GREEN — `hooks/impls/revocacion_factura_chain.py::RevocacionFacturaChain`
Req: REQ-HOOK-009 · Design: §6, §3 · Depends on: T-PR6-003
Files: `backend/packages/parkos_core/src/parkos_core/sync/hooks/impls/revocacion_factura_chain.py`
(new) — bound as `hook_chain_extend` on `revocacion_factura`.
- [ ] T-PR6-003 passes (GREEN)

#### T-PR6-005: Remove manual chain-append call from `dian/cloud/dispatcher.py`
Req: REQ-HOOK-009 · Design: §17 · Depends on: T-PR6-004
Files: `backend/packages/parkos_core/src/parkos_core/dian/cloud/dispatcher.py` (modified) — deletes
the manual `hash_chain.append(RevocacionFactura, ...)` call at lines 488-493; the hook now performs
the extension via the catalog spec.
- [ ] `git grep -n "hash_chain.append(RevocacionFactura" dispatcher.py` returns nothing

#### T-PR6-006: RED — `verify_chain` walks both chain-bearing tables
Req: REQ-MOT-006 · Design: §5 · Depends on: T-PR6-004
Files: `backend/packages/parkos_core/tests/unit/test_verify_chain.py` (new, failing) —
`test_walks_both_chain_bearing_tables`: walks `log_transaccional` and `revocacion_factura` per
`(timestamp_evento, uuid)` partitioned by `branch_uuid`; a mismatch produces one `ChainAnomaly` and
the walk continues.
- [ ] Fails — `motor/verify_chain.py` does not exist yet

#### T-PR6-007: GREEN — `motor/verify_chain.py::verify_chain`
Req: REQ-MOT-006 · Design: §5, §3 · Depends on: T-PR6-006
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/verify_chain.py` (new)
- [ ] T-PR6-006 passes (GREEN)

#### T-PR6-008: Regression test — exactly one chain per `(tabla, uuid_sucursal)`
Req: REQ-CAT-009, REQ-MOT-004 · Design: §2 Issue #1 · Depends on: T-PR6-007
Files: `test_verify_chain.py` (append) — `test_single_chain_per_tabla_uuid_sucursal`: with
`revocacion_factura` resolving to exactly one catalog entry (D6-rev), the walk never sees two
interleaved chains for the same `(tabla, uuid_sucursal)` — the guard against the double-chain hazard
the superseded dual-catalog design produced.
- [ ] Passes; this is the direct regression guard for the removed hazard

#### T-PR6-009: Commit + open PR6
Depends on: T-PR6-001..008
- [ ] Branch `feat/sync-overhaul-pr6-hash-chain-hooks` pushed, target `dev`

### PR6 acceptance
- [ ] `verify_chain` iterates both `log_transaccional` and `revocacion_factura`
- [ ] Dispatcher no longer calls `hash_chain.append` manually

---

## PR7 — `_read_local_seq` materialization + `resolve_conflict`

**Branch**: `hu/PR07-secuencia-local` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR6 merged
**Estimated LOC**: ~400
**Gate to next PR**: every `[V]` table produces a concrete seq; conflict tests pass; load test green

#### T-PR7-001: RED — `_read_local_seq` 4-strategy dispatch test
Req: REQ-MOT-009 · Design: §2 Issue #4 · Depends on: PR6
Files: `backend/packages/parkos_core/tests/unit/test_read_local_seq.py` (new, failing) — the
4-strategy dispatch table (`seq_via_datos`, `max_timestamp_evento`, `max_created_at`, `none`).
- [ ] Fails — `motor/read_local_seq.py` does not exist yet

#### T-PR7-002: GREEN — `motor/read_local_seq.py::ReadLocalSeq`
Req: REQ-MOT-009 · Design: §2 Issue #4, §3 · Depends on: T-PR7-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/read_local_seq.py` (new) — replaces
the stub at `conflict_resolver.py::_read_local_seq`; 5s TTL cache for `seq_via_datos`, no cache for
the time-based strategies.
- [ ] T-PR7-001 passes (GREEN)

#### T-PR7-003: Migration `0013_add_seq_lookup_indexes.py`
Req: design §4 · Design: §2 Issue #4 · Depends on: T-PR7-002
Files: `backend/packages/parkos_core/migrations/versions/0013_add_seq_lookup_indexes.py` (new) —
`ix_sync_queue_seq_lookup` partial index on `(tabla, uuid_registro, ((datos->>'seq')::bigint))
WHERE estado IN ('exitoso','pendiente')`; `tests/migrations/test_seq_lookup_index_schema.py` (new).
Pre-flight: `uv run alembic upgrade --sql 0013_add_seq_lookup_indexes` reviewed before apply.
- [ ] Index created against `prod.sync_queue`, NOT `0001_initial_schema.py` (which is applied and
      must not be edited)

#### T-PR7-004: Remove `conflict_resolver.py::_read_local_seq` stub; add `ConflictResolver` shim
Req: REQ-MOT-009 · Design: §17 · Depends on: T-PR7-002
Files: `backend/packages/parkos_core/src/parkos_core/sync/conflict_resolver.py` (modified) — removes
the 4 hardcoded `frozenset` constants and the `_read_local_seq` stub; `ConflictResolver` becomes a
thin shim delegating to `SyncMotor.resolve_conflict` so existing callers see no API change.
- [ ] `git grep -n "_read_local_seq" conflict_resolver.py` returns nothing (moved to `motor/`)

#### T-PR7-005: RED — `resolve_conflict` per-audit-class dispatch test
Req: REQ-MOT-007 · Design: §5 · Depends on: T-PR7-002, T-PR5-005 (natural-key path)
Files: `backend/packages/parkos_core/tests/unit/test_resolve_conflict.py` (new, failing) — covers
every branch: `[V]` with `natural_key` → `IdentityReconciler` delegate; `[V]` without → seq
comparison; `[L_E]`/`[L_W]`/`[A]` → `depends_on` parent resolution; `[L_S]` → grace window.
- [ ] Fails — `motor/resolve_conflict.py` does not exist yet

#### T-PR7-006: GREEN — `motor/resolve_conflict.py::resolve_conflict`
Req: REQ-MOT-007..010, REQ-MOT-013 · Design: §5, §3 · Depends on: T-PR7-005
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/resolve_conflict.py` (new)
- [ ] T-PR7-005 passes (GREEN)

#### T-PR7-007: Load test — `_read_local_seq` P95 ≤ 5ms, hit rate ≥ 95%
Req: design §2 Issue #4 load-test scenario · Design: §2 Issue #4 · Depends on: T-PR7-003
Files: `backend/packages/parkos_core/tests/bench/test_read_local_seq_load.py` (new) — testcontainers
Postgres, 10k rows across the 26 `[V]` tables, 1k concurrent lookups for random
`(tabla, uuid_registro)`.
- [ ] P95 ≤ 5ms and cache hit rate ≥ 95% with the 5s TTL

#### T-PR7-008: Commit + open PR7
Depends on: T-PR7-001..007
- [ ] Branch `feat/sync-overhaul-pr7-read-local-seq` pushed, target `dev`

### PR7 acceptance
- [ ] Every `[V]` table produces a concrete seq (no `None` for a non-`never_propagated` entry)
- [ ] Load test asserts P95/hit-rate thresholds

---

## PR8 — Dependency buffer + `alert_types` + single escalation path (D18, ADR-002, ADR-003)

**Branch**: `hu/PR08-buffer-dependencias-alertas` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR7 merged
**Estimated LOC**: ~700
**Gate to next PR**: orphan alerts within TTL; no `sync_queue` re-enqueue for dependency waits

#### T-PR8-001: Migration `0009_add_sync_queue_lw_buffer.py`
Req: REQ-CUT-010 · Design: §2 Issue #2, §4 · Depends on: PR7
Files: `backend/packages/parkos_core/migrations/versions/0009_add_sync_queue_lw_buffer.py` (new) —
`prod.sync_queue_lw_buffer` `[A]` `(uuid, uuid_sucursal, tabla, uuid_registro, tabla_padre,
uuid_padre, datos JSONB, estado, buffered_at, expires_at)` — the `tabla_padre` generalization covers
any declared parent, not only `uuid_padre` — plus `REVOKE UPDATE, DELETE` + `BEFORE UPDATE OR
DELETE` trigger in the same script + partial index `(tabla_padre, uuid_padre) WHERE
estado='pendiente'` + index `(expires_at)` + `pg_partman.create_parent(p_control:='buffered_at',
p_interval:='1 day', p_premake:=3)`; `tests/migrations/test_sync_queue_lw_buffer_schema.py` (new).
Pre-flight: `uv run alembic upgrade --sql 0009_add_sync_queue_lw_buffer` reviewed before apply.
- [ ] Table, REVOKE, trigger, both indexes, and the `pg_partman` parent all verified by the test

#### T-PR8-002: Migration `0010_add_alert_types.py`
Req: REQ-CAT-021 · Design: §2 Issue #6, §4 · Depends on: T-PR8-001
Files: `backend/packages/parkos_core/migrations/versions/0010_add_alert_types.py` (new) —
`prod.alert_types (tipo_alerta TEXT PK, descripcion TEXT, severity TEXT CHECK IN ('info','warning',
'critical'), created_at TIMESTAMPTZ)` + `REVOKE`/trigger in the same script + idempotent seed
(`ON CONFLICT DO NOTHING`) applied on **both** cloud and branch; `tests/migrations/
test_alert_types_schema.py` (new).
Pre-flight: `uv run alembic upgrade --sql 0010_add_alert_types` reviewed before apply.
- [ ] Re-running the seed is a no-op (idempotency test)

#### T-PR8-003: `infra/scripts/seed_alert_types.py` — generic identifiers only
Req: REQ-CAT-021, addendum #5 · Design: §2 Issue #6 · Depends on: T-PR8-002
Files: `infra/scripts/seed_alert_types.py` (new) — 8 rows: `hash_chain_anomaly`, `dian_rechazada`,
`dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`,
`fe_provider_error` (new), `fe_numbering_exhausted` (new); pattern-reference precedent:
`infra/scripts/seed_catalogs.py`'s idempotent `ON CONFLICT DO NOTHING` shape (not its distribution
mechanism, D8-rev).
- [ ] No row uses the literal name of the third-party DIAN provider

#### T-PR8-004: RED — no vendor name in seed data or source (addendum #5)
Req: REQ-OPS-016 · Design: §2 Issue #6 · Depends on: T-PR8-003
Files: `backend/packages/parkos_core/tests/unit/test_alert_types_seed.py` (new) — grep-based
assertion: the third-party DIAN provider's literal name appears in no seed row, source file, log
format string, or `alert_types` row anywhere under `parkos_core/`.
- [ ] Test fails if the vendor name is reintroduced anywhere in scope

#### T-PR8-005: `repo/alert_types.py::validate(tipo_alerta)`
Req: design §2 Issue #6 · Design: §3 · Depends on: T-PR8-002
Files: `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py` (new) —
`validate(tipo_alerta) -> None`, raises `UnknownAlertTypeError` outside the registry; wired into the
alert-writing path; `tests/unit/test_alert_types_validate.py` (new).
- [ ] Unknown identifier raises; a seeded identifier passes

#### T-PR8-006: RED — parent-missing buffer-drain integration test
Req: REQ-HOOK-013, REQ-HOOK-014, ADR-003 Validation · Design: §2 Issue #8, §7.6 · Depends on: T-PR8-001, T-PR4-009
Files: `backend/packages/parkos_core/tests/integration/test_parent_missing_buffer_drain.py` (new,
failing) — a child arriving first is buffered; the sender's row reaches `estado='exitoso'` with
**`intentos` unchanged**; the child applies when the parent lands; the buffer row reaches
`estado='aplicado'`.
- [ ] Fails — `motor/dependency_buffer.py` does not exist yet

#### T-PR8-007: GREEN — `motor/dependency_buffer.py` (insert + bounded drain)
Req: REQ-HOOK-013, ADR-003 Part 2 · Design: §2 Issue #8, §3 · Depends on: T-PR8-006
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/dependency_buffer.py` (new) —
buffer insert keyed `(tabla_padre, uuid_padre)`; `hook_post_insert` drains children as a **bounded
iterative work queue** (not recursion inside the applying transaction), capped per cycle at the
batch size and per row at the DAG depth; row is never re-enqueued into `sync_queue` for this reason.
- [ ] T-PR8-006 passes (GREEN)

#### T-PR8-008: RED — buffer TTL escalation, one alert, no re-enqueue
Req: REQ-HOOK-014, REQ-CUT-011, ADR-003 Validation · Design: §2 Issue #8 · Depends on: T-PR8-007
Files: `backend/packages/parkos_core/tests/integration/test_buffer_ttl_escalation.py` (new, failing)
— an unresolved parent past the 24h TTL emits exactly **one** `alerta
tipo_alerta='orphan_workflow_chain'` and produces **zero** `sync_queue` re-enqueues; the buffered
row is marked `estado='fallido'`, `ultimo_error='parent_missing_timeout'`, never deleted.
- [ ] Fails — the sweep does not exist yet

#### T-PR8-009: GREEN — `motor/dependency_buffer.py` TTL sweep
Req: REQ-CUT-011 · Design: §2 Issue #8, §3 · Depends on: T-PR8-008
Files: `motor/dependency_buffer.py` (modified) — hourly sweep (`_lw_buffer_sweep`) marks
`expires_at < NOW()` rows, emits the alert via `repo/alert_types.py::validate` + the standard alert
writer.
- [ ] T-PR8-008 passes (GREEN)

#### T-PR8-010: Commit + open PR8
Depends on: T-PR8-001..009
- [ ] Branch `feat/sync-overhaul-pr8-dependency-buffer-alert-types` pushed, target `dev`
- [ ] Both migration `--sql` dry-runs attached to the PR

### PR8 acceptance
- [ ] Buffer drains FIFO within a parent; `sync_dependency_wait`-observable via row count
- [ ] `sync_queue` `intentos` never increments for a dependency wait

---

## PR9 — DIAN path: branch-local numbering + `envio_dian` + DIAN backoff (D1-rev)

**Branch**: `hu/PR09-numeracion-dian-sucursal` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR8 merged
**Estimated LOC**: ~600
**Gate to next PR**: branch-emitted document reaches the provider; `cufe`/`estado` returns via
`envio_dian`; zero `sync_back_event` rows or literals anywhere

No task in this PR creates `prod.sync_back_events`, a `SyncBackEventEmitter` hook, or a
`operacion='sync_back_event'` emit loop — D1-rev removed that design before this PR was authored;
T-PR9-007 asserts the absence explicitly.

#### T-PR9-001: RED — sequential no-gap consecutivo assignment test
Req: REQ-CUT-014, addendum #1 · Design: §2 Issue #9 · Depends on: PR8
Files: `backend/packages/parkos_core/tests/unit/test_consecutivo_assignment.py` (new, failing) —
`test_sequential_no_gap_per_branch_resolution`: assignment is transactional and idempotent per
source event; a retry never generates a number, discards it, and generates a new one; if the
persisting transaction fails, no number is considered consumed.
- [ ] Fails — the assignment helper does not exist yet

#### T-PR9-002: GREEN — branch-local `consecutivo` assignment
Req: REQ-CUT-014 · Design: §1 Executive Summary · Depends on: T-PR9-001
Files: `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py` (new or
modified — verify against current repo layout before creating) — `assign_consecutivo(session,
resolucion_uuid, source_event_uuid) -> int`, assigns within `rango_desde`/`rango_hasta`, keyed on
the source event for idempotency.
- [ ] T-PR9-001 passes (GREEN)

#### T-PR9-003: Cloud-side range validation on receipt
Req: REQ-CUT-014, R10 · Design: §7.3 · Depends on: T-PR9-002
Files: `backend/packages/parkos_core/src/parkos_core/dian/cloud/dispatcher.py` (modified) — rejects
any `factura_electronica` whose `consecutivo` falls outside the resolution's authorized range; range
exhaustion raises `alerta tipo_alerta='fe_numbering_exhausted'`; `tests/unit/
test_dian_range_validation.py` (new).
- [ ] Out-of-range document is rejected; exhaustion emits the generic alert type

#### T-PR9-004: `dian/backoff.py::DIAN_BACKOFF_SCHEDULE`
Req: design §2 Issue #9, addendum #3 · Design: §2 Issue #9 · Depends on: PR8
Files: `backend/packages/parkos_core/src/parkos_core/dian/backoff.py` (new) — single declaration,
1m → 5m → 15m → 1h → 6h → 24h, terminal after 6 attempts; `tests/unit/test_dian_backoff.py` (new) —
this is `factura_electronica`'s **own** curve, distinct from the general `sync_queue`
`BACKOFF_SCHEDULE` (1s...300s, `FALLIDO_PERMANENTE` after 24h).
- [ ] Curve values match exactly; test asserts it is imported (not duplicated) by the catalog entries
      and the dispatcher

#### T-PR9-005: Wire `backoff_schedule`/`max_retries`/`on_exhaustion` onto the catalog
Req: design §2 Issue #9 · Design: §2 Issue #9 · Depends on: T-PR9-004, T-PR2-007, T-PR2-013
Files: `sync_entries_le.py` (modified — `factura_electronica`), `sync_entries_a.py` (modified —
`revocacion_factura`) — both get `backoff_schedule=DIAN_BACKOFF_SCHEDULE`, `max_retries=6`,
`on_exhaustion='fe_provider_error'`; `envio_dian` explicitly does NOT (its replication leg uses the
general curve — the provider-facing retry lives in the `envio_dian` transition chain itself).
- [ ] `envio_dian`'s catalog entry has `backoff_schedule=None`

#### T-PR9-006: `repo/sync_queue.py::mark_failed` accepts backoff override
Req: design §2 Issue #9, R8 · Design: §11 · Depends on: T-PR9-005
Files: `backend/packages/parkos_core/src/parkos_core/repo/sync_queue.py` (modified) —
`mark_failed(session, sq_uuid, *, error, backoff_schedule=None, max_retries=None)`; the override is
passed **into** this module, never applied around it, so the R-D3 carve-out AST check still passes.
- [ ] `tests/unit/test_mark_failed_backoff_override.py` (new) asserts the DIAN curve is honored when
      passed, general curve when omitted

#### T-PR9-007: Static test — no `sync_back_event` literals anywhere
Req: R21 (early check; PR14 T-PR14-004 is the full repo-wide gate) · Design: §0 amendment log #1 ·
Depends on: T-PR9-002, T-PR9-003
Files: `backend/packages/parkos_core/tests/static/test_no_sync_back_event_literals.py` (new) —
greps `dian/cloud/dispatcher.py` and `jobs/sync_cloud.py` for `sync_back_event`, `SyncBackEvent`,
`numero_temporal`, `numero_oficial`, `preliminar` — asserts zero hits.
- [ ] Test passes against the PR9 diff

#### T-PR9-008: `envio_dian` provider round trip + backoff
Req: REQ-CUT-014 · Design: §7.3 · Depends on: T-PR9-004, T-PR9-003
Files: `dian/cloud/dispatcher.py` (modified) — forwards a range-validated document to the DIAN
provider; on success `INSERT envio_dian` (cloud-only, chained via `uuid_envio_padre`); on failure
applies `DIAN_BACKOFF_SCHEDULE`, transitions to `ERROR` and raises `alerta
tipo_alerta='fe_provider_error'` after 6 attempts; `tests/integration/test_dian_round_trip.py`
(new).
- [ ] `cufe`/`estado` populated on the `envio_dian` row after a mocked-provider success

#### T-PR9-009: `envio_dian` reaches the branch (`cloud_to_branch`)
Req: REQ-CAT-008 · Design: §2 Issue #1 · Depends on: T-PR9-008, T-PR5-008
Files: `tests/integration/test_envio_dian_reaches_branch.py` (new) — applies at the originating
branch via `repo.workflow.append_transition`; `factura_electronica` is NEVER updated; `cufe`/`estado`
are readable through the derived view (`0015`, T-PR5-008).
- [ ] `factura_electronica` row's own columns are byte-identical before and after the apply

#### T-PR9-010: `revocacion_factura` reuses the DIAN backoff curve
Req: REQ-CUT-014 last clause · Design: §2 Issue #9 · Depends on: T-PR9-005
Files: `tests/unit/test_revocacion_factura_backoff.py` (new) — asserts `revocacion_factura`'s
catalog entry shares `DIAN_BACKOFF_SCHEDULE`/`max_retries=6`/`on_exhaustion='fe_provider_error'`
with `factura_electronica` — same DIAN evidentiary chain, same regulatory deadline.
- [ ] Divergent per-table curve is explicitly rejected (test asserts equality, not just presence)

#### T-PR9-011: Commit + open PR9
Depends on: T-PR9-001..010
- [ ] Branch `feat/sync-overhaul-pr9-dian-branch-numbering` pushed, target `dev`

### PR9 acceptance
- [ ] A branch-emitted document numbers offline and reaches the provider once connected
- [ ] Zero `sync_back_event` rows or literals anywhere in this PR's diff

---

## PR10 — Migrations 0011/0012 + `modelo_datos_er.mmd` amendment + count scripts (ADR-002)

**Branch**: `hu/PR10-triggers-canon-er` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR9 merged
**Estimated LOC**: ~600
**Gate to next PR**: `check_schema_match.py` and `check_table_counts.py` exit 0 at 51/54

#### T-PR10-001: Migration `0011_add_catalog_triggers.py`
Req: REQ-CAT-004 (18-table coverage), REQ-CAT-012 · Design: §4 · Depends on: PR9
Files: `backend/packages/parkos_core/migrations/versions/0011_add_catalog_triggers.py` (new) —
`fn_enqueue_sync_catalog` coverage for the 18 previously-untriggered `[V]` tables (D8-rev); reads
`priority` only as an intra-level tie-break; `tests/migrations/
test_catalog_triggers_schema.py` (new).
Pre-flight: `uv run alembic upgrade --sql 0011_add_catalog_triggers` reviewed before apply.
- [ ] Trigger fires an INSERT into `sync_queue` for all 18 tables named in REQ-CAT-004

#### T-PR10-002: Migration `0012_drop_infra_triggers.py` (D21 guard 1)
Req: REQ-OPS-014 · Design: §4 · Depends on: T-PR10-001
Files: `backend/packages/parkos_core/migrations/versions/0012_drop_infra_triggers.py` (new) — drops
`fn_enqueue_sync` from `prod.sync_log` and `prod.sync_conflict`; `tests/migrations/
test_drop_infra_triggers_schema.py` (new).
Pre-flight: `uv run alembic upgrade --sql 0012_drop_infra_triggers` reviewed before apply.
- [ ] Post-migration INSERT into `sync_log`/`sync_conflict` produces no `sync_queue` row

#### T-PR10-003: Cloud worker skip-not-fail for infra tables (D21 guard 2)
Req: REQ-OPS-014 · Design: §11 · Depends on: T-PR10-002
Files: `backend/packages/parkos_core/src/parkos_core/jobs/sync_cloud.py` (modified) — skips (does
NOT `mark_failed(unknown_table)`) any row whose `tabla` matches one of the 5 out-of-catalog names,
logs `{"event":"sync_skip_infra_table","tabla":...}` at `info`; `tests/unit/
test_sync_cloud_skip_infra_table.py` (new).
- [ ] A `sync_queue` row with `tabla="sync_log"` is skipped cleanly, not marked failed; no failure
      metric increments

#### T-PR10-004: `modelo_datos_er.mmd` — add `sync_queue_lw_buffer` `%% [A]` block
Req: proposal §9.3, ADR-002 · Design: §4 · Depends on: T-PR8-001
Files: `modelo_datos_er.mmd` (modified) — new `%% [A]` entity block for `sync_queue_lw_buffer`
(columns per T-PR8-001's migration) plus its relationship line to `sucursal`.
- [ ] The `.mmd` block's column list matches the `0009` migration's DDL exactly

#### T-PR10-005: `modelo_datos_er.mmd` — add `alert_types` `%% [A]` block
Req: proposal §9.3, ADR-002 · Design: §4 · Depends on: T-PR10-004, T-PR8-002
Files: `modelo_datos_er.mmd` (modified) — new `%% [A]` entity block for `alert_types` (columns per
T-PR8-002's migration) plus its relationship line to `sucursal`.
- [ ] `.mmd` now carries exactly 14 `%% [A]` blocks total (12 existing + these 2)

#### T-PR10-006: `openspec/scripts/check_table_counts.py` — 51/14 canon
Req: ADR-002 Validation · Design: §4 · Depends on: T-PR10-005
Files: `openspec/scripts/check_table_counts.py` (modified) — `CANONICAL` mapping bumped `total: 49 →
51`, `[A]: 12 → 14`; stale-pattern guards so "49 tables" / "12 [A]" cannot reappear as canonical.
- [ ] Script exits 0 against the amended `.mmd`

#### T-PR10-007: `openspec/scripts/check_schema_match.py` — 54 physical tables
Req: ADR-002 Validation · Design: §4 · Depends on: T-PR10-006
Files: `openspec/scripts/check_schema_match.py` (modified) — asserts full match between the amended
`.mmd` (51 ER entities) and 54 physical prod tables (51 ER + 3 non-ER operational).
- [ ] Script exits 0

#### T-PR10-008: Static test — `%% [A]` block count is 14
Req: ADR-002 Validation · Design: §4 · Depends on: T-PR10-005
Files: `backend/packages/parkos_core/tests/static/test_mmd_block_count.py` (new) — equivalent of
`git grep -c "%% \[A\]" modelo_datos_er.mmd` returns 14 (the 3 non-ER operational tables have no
`%% [A]` block by definition).
- [ ] Test passes

#### T-PR10-009: Commit + open PR10
Depends on: T-PR10-001..008
- [ ] Branch `feat/sync-overhaul-pr10-catalog-triggers-er-canon` pushed, target `dev`
- [ ] Both migration `--sql` dry-runs attached to the PR

### PR10 acceptance
- [ ] `check_table_counts.py` and `check_schema_match.py` both exit 0
- [ ] `.mmd` carries 51 entities, 14 `%% [A]` blocks

---

## PR11 — Cloud worker cutover: catalog-driven `job_sync_cloud` + `/sync/hello`

**Branch**: `hu/PR11-corte-nube` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR10 merged
**Estimated LOC**: ~600
**Gate to next PR**: dual protocol active; metrics emit

#### T-PR11-001: `jobs/sync_cloud.py` reads the catalog and calls `SyncMotor`
Req: REQ-MOT-011 · Design: §17 · Depends on: PR10
Files: `backend/packages/parkos_core/src/parkos_core/jobs/sync_cloud.py` (modified) — applier loops
call `SyncMotor.apply_batch`/`verify_chain`; confirms no `_emit_sync_back_events_loop` (loop 2) is
present — it was never built (D1-rev); `tests/integration/test_sync_cloud_catalog_driven.py` (new).
- [ ] Loop applies a `[V]` and an `[A]` fixture row correctly end to end against testcontainers

#### T-PR11-002: `role_guard` regression — cloud process imports cleanly
Req: REQ-OPS-005 · Design: §3 · Depends on: T-PR1-010, T-PR2-009
Files: `backend/packages/parkos_core/tests/integration/test_role_guard.py` (modified) — adds the
cloud-flavored companion case: a cloud process (`PARKOS_DEPLOY=cloud`) imports both `envio_dian` and
`validacion_evento` without raising.
- [ ] Passes alongside the existing branch-side raise case from PR1

#### T-PR11-003: `cutover/dual_protocol.py` + `/sync/hello`
Req: REQ-CUT-003, REQ-CUT-004 · Design: §8 · Depends on: T-PR11-001
Files: `backend/packages/parkos_core/src/parkos_core/sync/cutover/dual_protocol.py` (new),
`backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py::sync_hello` (modified) —
response shape `{protocol_version, min_branch_version, grace_until, catalog_revision}`, 300s branch
cache; `tests/integration/test_dual_protocol.py` (new).
- [ ] Response matches REQ-CUT-004 exactly; `grace_until` is null when `protocol_version=="legacy"`

#### T-PR11-004: `openspec/scripts/check_drain.py`
Req: REQ-OPS-013, REQ-CUT-002 · Design: §11 · Depends on: T-PR11-001
Files: `openspec/scripts/check_drain.py` (new) — queries
`SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente'`; exit 0 if 0, exit 1 with count +
elapsed seconds otherwise; `tests/static/test_check_drain_green.py` (new).
- [ ] Script invoked by the stage-4 gate automation reference in `.github/workflows/ci.yml`'s
      comments (actual CI wiring is a deploy-pipeline concern, out of scope here)

#### T-PR11-005: `check_catalog_drift.py` re-derivation against the populated catalog
Req: REQ-OPS-003 · Design: §11 · Depends on: T-PR2-017, T-PR3-007, T-PR10-005
Files: `backend/packages/parkos_core/tests/static/test_check_catalog_drift_green.py` (modified) —
closes the PR1 placeholder: runs the full 11-rule drift check against the now-populated catalog and
amended `.mmd`, not an empty stub.
- [ ] Script exits 0 with all rules through 11 active

#### T-PR11-006: Cloud-side `/sync/events` wire status `retry_parent_missing` (REQ-CUT-015, cloud leg)
Req: REQ-CUT-015, REQ-MOT-005 · Design: §2 Issue #8 · Depends on: T-PR11-001, T-PR8-007
Files: `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py` (modified) — the cloud's
`/sync/events` receiver reports `retry_parent_missing` for a `branch_to_cloud` row whose declared
parent is not yet present, never a generic failure or a silent drop; `tests/unit/
test_sync_router_wire_status.py` (new).
- [ ] `APPLIED → applied`, `CONFLICT → conflict`, `RETRY(parent_missing) → retry_parent_missing`
      mapping table asserted exactly

#### T-PR11-007: `infra/deploy/docker-compose.{cloud,branch}.yml` — `PARKOS_SYNC_ENGINE` env
Req: REQ-CUT-001 · Design: §17 · Depends on: T-PR1-004
Files: `infra/deploy/docker-compose.cloud.yml` (modified), `infra/deploy/docker-compose.branch.yml`
(modified) — adds `PARKOS_SYNC_ENGINE` (default `legacy` for cloud until stage 3; `catalog_branch`
for branches after stage 4).
- [ ] `.env.cloud` values are NOT inlined into the compose files (T-PR1-004's `.gitignore` still
      applies)

#### T-PR11-008: Commit + open PR11
Depends on: T-PR11-001..007
- [ ] Branch `feat/sync-overhaul-pr11-cloud-cutover` pushed, target `dev`

### PR11 acceptance
- [ ] `job_sync_cloud` applies via the catalog; `/sync/hello` returns the documented shape
- [ ] Full 11-rule `check_catalog_drift.py` green against the real catalog

---

## PR12 — Branch cutover: `job_sync_sucursal` + topological backfill + `catalog_backfill_complete`

**Branch**: `hu/PR12-corte-sucursal` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR11 merged
**Estimated LOC**: ~650
**Gate to next PR**: a freshly paired branch reaches full catalog coverage with zero unresolved parents

#### T-PR12-001: RED — topological backfill reaches `catalog_backfill_complete=1`
Req: R-D8 · Design: §7.1 · Depends on: PR11
Files: `backend/packages/parkos_core/tests/integration/test_pairing_flow.py` (new, failing) — a
freshly paired branch (empty catalog set) backfills every `cloud_to_branch` entry in topological
level order, paginated; `catalog_backfill_complete{uuid_sucursal}` reaches 1 only when every level
applied with zero unresolved parents.
- [ ] Fails — `cutover/backfill.py` does not exist yet

#### T-PR12-002: GREEN — `cutover/backfill.py`
Req: R-D8 · Design: §7.1, §3 · Depends on: T-PR12-001, T-PR3-006
Files: `backend/packages/parkos_core/src/parkos_core/sync/cutover/backfill.py` (new) — walks
`cloud_to_branch` entries by topological level, paginated; `usuarios`/`permisos`/`permisos_usuario`
sit at the root so offline login is available as early as possible (R9).
- [ ] T-PR12-001 passes (GREEN)

#### T-PR12-003: `motor/broadcast_resolver.py` (D5-rev, D19, §16 Q1)
Req: REQ-MOT-014, REQ-MOT-016 · Design: §3 · Depends on: T-PR2-006
Files: `backend/packages/parkos_core/src/parkos_core/sync/motor/broadcast_resolver.py` (new) —
dispatches `broadcast_policy`: `single_branch` (payload's `branch_uuid`), `all_branches` (every
branch), `all_branches_with_override` (NULL row → all + stored; non-NULL → that branch only),
`subscription` (row's own `uuid_sucursal`, or transitively via `subscripciones_cliente.uuid_sucursal`
for `subscripcion_vehiculos` — reusing the already-validated `depends_on` parent, never a second
query); `tests/unit/test_broadcast_resolver.py` (new) — no fallback to `all_branches` for
`subscription`.
- [ ] Transitive resolution for `subscripcion_vehiculos` reuses the validated parent, asserted via a
      mock query-count of 1

#### T-PR12-004: Branch-side `/sync/events` wire status `retry_parent_missing`
Req: REQ-CUT-015 · Design: §2 Issue #8 · Depends on: T-PR11-006
Files: `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py` (modified) — the
branch's `/sync/events` receiver (for `cloud_to_branch` pushes) reports the same wire status
mapping as T-PR11-006; `tests/unit/test_sync_router_wire_status.py` (append case for the branch
direction).
- [ ] Mapping table matches T-PR11-006 exactly (single source of truth, REQ-MOT-005)

#### T-PR12-005: Sender-side `retry_parent_missing` handling (`mark_success`, `intentos` untouched)
Req: REQ-CUT-015, ADR-003 Part 2 · Design: §2 Issue #8 · Depends on: T-PR12-004
Files: `backend/packages/parkos_core/src/parkos_core/jobs/sync_sucursal.py` (modified) — on
`retry_parent_missing`, calls `repo.sync_queue.mark_success`; does NOT increment `intentos` or set
`next_retry_at`; `tests/unit/test_sync_sucursal_retry_parent_missing.py` (new).
- [ ] `intentos` is byte-identical before/after a `retry_parent_missing` response

#### T-PR12-006: `jobs/sync_sucursal.py` 6-step cycle calls `SyncMotor.apply_batch`
Req: REQ-MOT-015 · Design: §17 · Depends on: T-PR12-002
Files: `jobs/sync_sucursal.py` (modified) — every pushed batch goes through
`SyncMotor.apply_batch`; `tests/integration/test_sync_sucursal_apply_batch.py` (new).
- [ ] Batch selection is unchanged (still `list_pending`'s ordering/limit), only in-batch application
      changes

#### T-PR12-007: Branch auto-detect from `/sync/hello`
Req: REQ-CUT-005 · Design: §8 · Depends on: T-PR11-003
Files: `jobs/sync_sucursal.py` (modified) — wires the auto-detect table (legacy vs. catalog applier,
fail-safe to legacy on HTTP error/timeout); `tests/integration/test_branch_autodetect.py` (new).
- [ ] All 4 rows of REQ-CUT-005's condition table are exercised

#### T-PR12-008: `observability/metrics.py::catalog_backfill_complete` gauge
Req: REQ-OPS-006 · Design: §9 · Depends on: T-PR12-002
Files: `backend/packages/parkos_core/src/parkos_core/sync/observability/metrics.py` (new or
modified) — transitions to 1 only after every `cloud_to_branch` entry backfills with zero unresolved
parents for the branch; `tests/unit/test_catalog_backfill_gauge.py` (new).
- [ ] Gauge stays 0 while any level has an unresolved parent

#### T-PR12-009: RED+GREEN — full offline-flow integration test
Req: proposal §13 Success Criteria · Design: §10 Testing Strategy · Depends on: T-PR12-002, PR9, PR5
Files: `backend/packages/parkos_core/tests/integration/test_branch_offline_flow.py` (new) —
authenticate, authorize, classify a vehicle, price a stay, register an identified client, emit and
number an electronic invoice, reprint a ticket — all with the cloud unreachable.
- [ ] Every step succeeds against testcontainers with no cloud connectivity simulated

#### T-PR12-010: Commit + open PR12
Depends on: T-PR12-001..009
- [ ] Branch `feat/sync-overhaul-pr12-branch-cutover` pushed, target `dev`

### PR12 acceptance
- [ ] `catalog_backfill_complete{uuid_sucursal}` reaches 1 with zero unresolved parents
- [ ] Full offline-flow integration test passes end to end

---

## PR13 — Observability: metrics + logs + sink-side PII redaction + Grafana alerts

**Branch**: `hu/PR13-observabilidad` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR12 merged
**Estimated LOC**: ~450
**Gate to next PR**: metrics exposed; alert rules tested

#### T-PR13-001: `observability/metrics.py` — remaining counters/gauges
Req: REQ-OPS-006 · Design: §9 · Depends on: PR12
Files: `sync/observability/metrics.py` (modified/new) — `sync_apply_total{status,tabla,
uuid_sucursal,audit_class}`, `sync_dependency_wait{tabla,tabla_padre}`, `catalog_rows_total{tabla,
uuid_sucursal}`, `sync_deferred_total{tabla,tabla_padre}`; `tests/unit/
test_observability_metrics.py` (new).
- [ ] All labels exclude PII (no payload content) — asserted by the test

#### T-PR13-002: `observability/logs.py` — structlog config
Req: REQ-OPS-007 · Design: §9 · Depends on: T-PR13-001
Files: `sync/observability/logs.py` (new) — required keys `event`, `tabla`, `uuid_sucursal`,
`actor_uuid`, `correlation_id`, `ts`, `level`; `chain_break` logs at `error`; `tests/unit/
test_observability_logs.py` (new).
- [ ] JSON output carries all 7 required keys on a sample `sync_apply` event

#### T-PR13-003: `observability/pii_redaction.py::PIIRedactor` — sink-side only
Req: REQ-HOOK-004, REQ-OPS-007 · Design: §6, §9 · Depends on: T-PR13-002
Files: `sync/observability/pii_redaction.py` (new) — redacts `clientes`
`email`/`telefono`/`direccion`/`nombre`/`apellido` **only** in `sync_log` entries, structured logs,
and `sync_conflict.datos_local`/`datos_remoto`; the replicated payload itself is **never** redacted;
`tests/unit/test_pii_redaction.py` (new).
- [ ] A `clientes` apply payload reaches `repo.versioned.close_and_insert` unredacted; the same
      event's log line has the PII fields masked

#### T-PR13-004: `infra/grafana/alerts/sync.yaml`
Req: REQ-OPS-008 · Design: §9 · Depends on: T-PR13-001
Files: `infra/grafana/alerts/sync.yaml` (new) — 8 rules (`SyncBacklogHigh`,
`SyncConflictRateHigh`, `HashChainBreak`, `OrphanWorkflowChain`, `BranchImportError`,
`CatalogBackfillIncomplete`, `FEProviderError`, `FENumberingExhausted`), each with a `runbook_url`
annotation; every `tipo_alerta` referenced is a generic identifier (addendum #5).
- [ ] YAML validates against the Grafana alert-rule schema

#### T-PR13-005: `docs/runbooks/sync/*.md` — 8 runbook stubs
Req: REQ-OPS-008 · Design: §9 · Depends on: T-PR13-004
Files: `docs/runbooks/sync/{sync_backlog,conflict_rate,chain_break,orphan_workflow,import_error,
dependency_wait,backfill_stalled,client_volume}.md` (8 new files) — one stub per alert rule, using
only generic identifiers.
- [ ] Every `runbook_url` in `sync.yaml` resolves to an existing file in this set

#### T-PR13-006: Commit + open PR13
Depends on: T-PR13-001..005
- [ ] Branch `feat/sync-overhaul-pr13-observability` pushed, target `dev`

### PR13 acceptance
- [ ] `GET /metrics` exposes all counters/gauges with PII-free labels
- [ ] All 8 Grafana alert rules parse and reference an existing runbook

---

## PR14 — Cutover stage gates + reverse migration + `AGENTS.md` correction (D12, R21)

**Branch**: `hu/PR14-cierre-reversion` (off `feature/sync-overhaul`) — PR target: `feature/sync-overhaul`
**Dependencies**: PR13 merged
**Estimated LOC**: ~500
**Gate to next PR**: N/A — final PR of the chain; reverse dry-run OK; repo-wide grep for
`consecutivo_actual`, `numero_temporal`, `numero_oficial`, `sync_back_event`, `SyncBackEvent`
returns nothing outside explicitly-marked superseded-decision text

#### T-PR14-001: `cutover/stage_runner.py` — 6-stage gate evaluator
Req: REQ-CUT-006, REQ-CUT-007 · Design: §8 · Depends on: PR13
Files: `backend/packages/parkos_core/src/parkos_core/sync/cutover/stage_runner.py` (new) — evaluates
stages 0-5 against the 24h-continuous gate criteria table (proposal §11 / design §8), keyed on the
five `PARKOS_SYNC_ENGINE` values; `tests/unit/test_stage_runner.py` (new).
- [ ] Stage 4's gate reads `catalog_backfill_complete{uuid_sucursal}` (R-D8), not a hardcoded pass

#### T-PR14-002: `openspec/scripts/reverse_sync_overhaul.py` (D12)
Req: REQ-CUT-009, REQ-OPS-012 · Design: §12 · Depends on: T-PR8-007
Files: `openspec/scripts/reverse_sync_overhaul.py` (new) — 6 idempotent steps: set `legacy` → wait
for drain → drain `prod.sync_queue_lw_buffer` (buffered rows re-enter the legacy path) → disable new
endpoints → restore legacy paths → verify chain verifier green; `--dry-run` mode records actions
without mutating state; `tests/integration/test_reverse_dry_run.py` (new).
- [ ] `--dry-run` exits 0 on a clean run and non-zero when `check_catalog_drift.py` fails
- [ ] The new `fn_enqueue_sync_catalog` triggers (0011) are asserted **not** removed on rollback

#### T-PR14-003: `AGENTS.md` correction (proposal §9.5, D1-rev) — docs only
Req: proposal §9.5 · Design: §17 (read-only, corrected by this task) · Depends on: none (docs-only,
can run any time in PR14)
Files: `AGENTS.md` (modified) — six exact edits: line 112 (DIAN-only tables claim → branch-emitted
correction), line 113 (`empresa.consecutivo_actual` → branch-local numbering), lines 205-207
(online/offline numbering split → single branch-local rule), line 208 (atomic cloud mutation →
range validation + `envio_dian` forward channel), lines 234-235 (`preliminar` badge / sync-back gate
→ removed, document final at emission), line 255 (risk-register row → resolution-range collision
control). Exact replacement text per proposal §9.5's two tables.
- [ ] All six locations edited exactly as specified in proposal §9.5, no paraphrasing that changes
      the numbering model

#### T-PR14-004: Static test — repo-wide grep for superseded terms (R21)
Req: R21 · Design: §15 · Depends on: T-PR14-003, T-PR9-007
Files: `backend/packages/parkos_core/tests/static/test_agents_md_no_superseded_terms.py` (new) —
repo-wide grep for `consecutivo_actual`, `numero_temporal`, `numero_oficial`, `sync_back_event`,
`SyncBackEvent` returns zero hits outside explicitly-marked superseded-decision blocks (e.g. this
`tasks.md`'s own history references, ADR `<details>` blocks).
- [ ] Test passes against the full repo state after PR14

#### T-PR14-005: Static test — no withdrawn `PARKOS_SYNC_ENGINE` literals (ADR-001)
Req: ADR-001 Validation · Design: §2 Issue #3 · Depends on: T-PR1-008
Files: `openspec/scripts/check_engine_flag_values.py` (new) — asserts the enum literal in
`engine_flag.py` equals exactly the 5 ratified D22 values and that `catalog_read`, `catalog_dual`,
`catalog_only`, `catalog_lite` appear nowhere under `backend/` or `openspec/scripts/`; `tests/static/
test_engine_flag_no_withdrawn_literals.py` (new).
- [ ] Script exits 0

#### T-PR14-006: Full-chain reverse-dry-run rehearsal
Req: REQ-OPS-012 · Design: §12 · Depends on: T-PR14-002, T-PR10-007
Files: N/A — CI job step (documented in `.github/workflows/ci.yml`'s deploy-rehearsal comment, wired
by ops tooling outside this change's file set)
Given the full chain (PR1-PR14) is merged, when `openspec/scripts/reverse_sync_overhaul.py
--dry-run` runs against staging, then it exits 0 and prints every "[DRY-RUN] would ..." action
without touching env or data.
- [ ] Rehearsal recorded in the PR14 description as the final gate before merge

#### T-PR14-007: Commit + open PR14
Depends on: T-PR14-001..006
- [ ] Branch `feat/sync-overhaul-pr14-stage-gates-rollback-agents-md` pushed, target `dev`
- [ ] PR description includes the T-PR14-006 rehearsal output

### PR14 acceptance
- [ ] `stage_runner.py` evaluates all 6 stages against their documented gate criteria
- [ ] `reverse_sync_overhaul.py --dry-run` exits 0
- [ ] Zero hits for any superseded term outside marked history blocks, repo-wide

---

## Cross-PR constraints

- **No task proposes a `DELETE` HTTP endpoint or a raw `delete()` ORM call** on `[V]`/`[A]` tables
  (audit-first canon, unchanged).
- **All `[A]` migrations ship `REVOKE UPDATE, DELETE` + `BEFORE UPDATE OR DELETE` trigger in the
  same script** as the `CREATE TABLE` (0009, 0010).
- **Every migration task carries a pre-flight `alembic upgrade --sql <revision>` review** before
  applying to any environment (0009-0015, seven total).
- **`vigente_hasta=None` default** for all `[V]` factory-created rows (R15, T-PR2-018).
- **`sync_apply_total` and every other metric label excludes PII** — `status`, `tabla`,
  `uuid_sucursal`, `audit_class` only (REQ-OPS-006).
- **Branch process MUST NOT import `role_required="cloud"` entries** (only `validacion_evento`);
  `role_guard.assert_role("branch")` raises `ImportError` (REQ-OPS-005, REQ-MOT-012).
- **`RETRY(parent_missing)` is delivered-and-deferred** — `mark_success` on the sender, `intentos`
  never incremented, `sync_queue` never re-enqueued for a dependency wait. One escalation path only
  (D18, ADR-003).
- **`priority` is a FIFO tie-break within one topological level only** — never a cross-table
  ordering mechanism (R12, CI-asserted).
- **Snapshot columns (`factura_impuestos`, `factura_otros_cobros`) are never recomputed on apply**,
  on either side, at any time (D20).
- **Alert-type identifiers are always generic** — never the third-party DIAN provider's literal name
  (addendum #5, R-OPS-016).
- **A subscribed vehicle missing at a non-selling branch is silent-correct** — zero conflicts,
  alerts, or buffer rows; standard tariff charged (R22).
- **Branch cutover follows cloud stability by 7 days** (D3, REQ-CUT-007), gated on
  `catalog_backfill_complete{uuid_sucursal}=1` (R-D8).
- **No `prod.sync_back_events` table, hook, flag, or vocabulary anywhere** — D1-rev, gated by
  T-PR9-007 (early) and T-PR14-004 (final, repo-wide).
