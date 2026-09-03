# Tasks: create-49-table-apis

> **Change**: `create-49-table-apis`
> **Phase**: tasks (sdd-tasks)
> **Status**: ready for `sdd-apply`
> **Preflight cached** (this session): `pace=auto`, `artifact=hybrid` (OpenSpec + Engram), `delivery=auto-chain`, `chain=gitflow`, `review_budget=800 lines/PR`
> **Inputs read**: `proposal.md` (644 lines, memory #1265), `design.md` (2170 lines, memory #1267), `specs/{bi-temporal-crud,append-only-events,workflow-transitions,lifecycle-events,session-cycles,cross-cutting,operational}.md` (39 REQs + 26 SCs, memory #1266), `exploration.md` (345 lines, memory #1264), `AGENTS.md` (project canon), `modelo_datos_er.mmd` (49 tables), `bootstrap-monorepo-foundation/{proposal,design,tasks}.md` (stays on legacy `feature-branch-chain` per user decision this session — NOT migrated to gitflow; schema migration file `0001_initial_schema.py` must be reachable on disk for PR2)
> **Gitflow ratified this session**: branches off `dev`, PRs merge to `dev`, NEVER `main` directly; release branches to `main` after cert.

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~5,000–5,500 across PR0–PR7 |
| Total tasks | 121 across 8 PRs |
| 400-line budget risk | Medium (each PR averages ~700 LOC; PR5 and PR6 sit at the 800 edge) |
| Chained PRs recommended | Yes — 8 chained PRs to `dev` |
| Suggested split | PR0 → PR1 → PR2 → PR3 → PR4 → PR5 (split at apply-time if >800) → PR6 (split at apply-time if >800) → PR7 |
| Delivery strategy | `auto-chain` (cached) |
| Chain strategy | gitflow (feature branches off `dev`, PRs target `dev`, releases to `main` after cert) |
| Conditional splits pre-scoped | PR5a/5b, PR6a/6b (per `proposal.md` §PR slicing) |
| `size:exception` required? | **No** — every PR fits in 800 LOC after the conditional splits |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: chained PRs to `dev` in dependency order, each independently revertible (gitflow; `main` is production, `dev` is integration; releases via `release/vX.Y.Z` → `main` after cert)
400-line budget risk: Medium

## Work-unit commit conventions

- **One task = one work-unit commit.** Each commit tells a story: behavior + tests + docs for the unit.
- **Conventional Commits only** (`feat(scope): description`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`). NO `Co-Authored-By` / NO AI attribution trailers (per `AGENTS.md`).
- **Tests ship with code in the same commit.** When a task has a test artifact, both land together.
- **Migrations carry the REVOKE + trigger in the SAME migration script** when the table is `[A]`-class (per `openspec/config.yaml` `rules.tasks`).
- **Pre-flight `alembic upgrade --sql` check** BEFORE applying any migration; printed DDL inspected visually (per `config.yaml`).
- Reference: `~/.config/opencode/skills/work-unit-commits/SKILL.md` and `~/.config/opencode/skills/chained-pr/SKILL.md`.

## Pre-apply setup

> **Manual, one-time, executed ONCE before PR0.** Operator (or orchestrator) runs these git commands locally. PR1's T-PR1-01 verifies they ran. This MUST happen before PR0's branch is cut — otherwise PR0 has no `dev` to branch off and no `dev` to merge to.

```bash
# Pre-apply: one-time gitflow bootstrap (manual, before PR0)
git checkout master
git branch -m master main
git push -u origin main
git checkout -b dev main
git push -u origin dev
```

After pre-apply, all feature branches are cut from `dev` and all PRs target `dev`. The `master` branch no longer exists; `main` is production; `dev` is integration.

**Why this is manual and not a task in PR1**: the `master` → `main` rename + `dev` creation is git topology that mutates the default branch and remote tracking. It must be executed by the operator who owns the GitHub repo (and who can flip the default-branch setting on github.com). A PR cannot rename the canonical branch it lives on. So this work is done OUTSIDE the chained-PR flow, with PR1's T-PR1-01 acting as a gatekeeper (`verify only`, no mutations).

## Branch and merge strategy (gitflow, per `AGENTS.md`)

- `master` is renamed to `main` and `dev` is cut from `main` in the **Pre-apply setup** (see Pre-apply section above). This is a one-time manual git operation; PR1's T-PR1-01 verifies it.
- `dev` is the integration branch for ALL subsequent work.
- Feature branches: `feat/create-49-table-apis-prN-<slug>` (PR1–PR7) or `docs/create-49-table-apis-pr0-doc-reconcile` (PR0).
- Each PR targets `dev` (NEVER `main` directly).
- Each PR is reviewed and merged to `dev` BEFORE the next starts.
- Release branches (`release/vX.Y.Z`) cut from `dev` only after the full chain is verified; merge into `main` after certification.

## Per-PR workload forecast and split triggers

| PR | Tables | New files | LOC forecast | LOC risk | Conditional split |
|---|---|---|---|---|---|
| PR0 | 0 | 2 | ~80 | LOW | — |
| PR1 | 5 (4 [V] auth + 1 [L-S] login) | ~22 | ~700 | MED | — |
| PR2 | 7 ([A] infra: sync + log) | ~12 | ~700 | MED | — |
| PR3 | 9 ([V] catalogs) | ~11 | ~600 | LOW | — |
| PR4 | 8 ([V] empresa+sucursal+config) | ~12 | ~750 | MED | — |
| PR5 | 6 ([V] commercial + 1 [L-E] ingreso) | ~10 | ~800 | **HIGH** | **PR5a** ([V] 5 commercial, ~500) + **PR5b** ([L-E] ingreso, ~300) |
| PR6 | 12 (2 [L-E] + 6 [L-W] + 4 [A] billing) | ~22 | ~800 | **HIGH** | **PR6a** (5 billing/facturas, ~600) + **PR6b** (6 workflows, ~500) |
| PR7 | 4 (1 [L-S] sesion + 2 [A] + 1 idempotency 50th) | ~13 | ~600 | LOW | — |
| **Total** | **50** | **~104** | **~5,030** | | |

PR5 split trigger: `git diff --stat` post-implementation > 800 LOC → execute PR5a, then PR5b.
PR6 split trigger: same threshold → execute PR6a, then PR6b.

## Per-action forecast (orchestrator cost/side-effect before long-running work)

| PR | Test actions | Build/install actions | Runtime side-effects |
|---|---|---|---|
| PR0 | `bash openspec/scripts/check_table_counts.py`; static drift check | none | none (docs only) |
| PR1 | `uv run pytest backend/tests/migrations/test_{a_inmutable,ls_session_guard,revokes_active,partman_parents}.py -q`; `uv run pytest backend/tests/{unit,static} -q`; `uv run ruff check backend/packages/parkos_core/` | `uv sync --frozen` (workspace lock) | `uv run alembic upgrade head` against testcontainers Postgres; `alembic upgrade --sql head` pre-flight |
| PR2 | `uv run pytest backend/tests/{migrations,unit}/test_hash_chain* tests/migrations/test_sync_outbox_recursion.py -q` | `uv sync --frozen` | testcontainers Postgres; `uv run alembic upgrade head` idempotency check |
| PR3 | `uv run pytest backend/tests/unit/test_catalogos_* -q`; smoke `curl /api/v1/tipo-persona?limit=10` | none | testcontainers Postgres; refresh openapi artifact |
| PR4 | `uv run pytest backend/tests/unit/test_config_override_resolution.py -q` | none | testcontainers Postgres; refresh openapi artifact |
| PR5 | `uv run pytest backend/tests/unit/test_event_record.py tests/integration/test_crud_happy_path.py -q` | none | testcontainers Postgres; refresh openapi artifact |
| PR6 | `uv run pytest backend/tests/{migrations,static,unit}/ -q`; `uv run python -m parkos_core.openapi --deploy {cloud,branch}` | none | testcontainers Postgres + Redis (cache for polymorphic FK); refresh openapi artifact; smoke import-boundary test |
| PR7 | `uv run pytest backend/tests/{migrations,unit}/ -q` | `uv sync --frozen` | testcontainers Postgres; `uv run alembic upgrade head` (creates 50th table); refresh openapi artifact |

## Constraints honored

- NO task proposes a `DELETE` HTTP endpoint or a raw `delete()` ORM call. Exceptions are explicitly scoped: TTL prune of `idempotency_keys` (PR7, owner-only SQL, NOT an API endpoint) and `pg_partman` partition drops (operational only, NOT business).
- Tasks for `parkos_core/sync_queue.py` writes do NOT trigger a recursive `sync_queue` insert (REQ-X6 + SC-X5: `WHEN (TG_TABLE_NAME <> 'sync_queue')` filter is in the DB trigger).
- `parkos_core/repo/sync_outbox.py` is a no-op facade that raises `RuntimeError` on any call (REQ-X6).
- Every Pydantic `Create` for `[V]` rejects `vigente_desde` / `vigente_hasta` / `estado` from the client (C-6).
- Every migration that touches `[A]` includes REVOKE + trigger in the SAME script (config.yaml rules.tasks).

---

## PR0 — Doc drift reconciliation

### Branch
`docs/create-49-table-apis-pr0-doc-reconcile` (off `dev`, after pre-apply setup)

### Dependencies
- **None.** PR0 is the first PR to land. It MUST merge BEFORE bootstrap PR2 lands; otherwise bootstrap ships against stale docs (risk #1 in `proposal.md`).

### Work-unit commit boundaries
All edits land in ONE commit (single docs reconciliation unit). The two new scripts (T-PR0-05, T-PR0-06) MAY split into two commits if the reviewer prefers; otherwise one.

### Tasks

- [ ] **T-PR0-01**: Update `openspec/PROJECT_CONTEXT.md` line 55 header from "45 tables" to "49 tables (26 [V] / 3 [L-E] / 6 [L-W] / 2 [L-S] / 12 [A])"; update the table at lines 60–67 to the new counts; update the risk note on line 110. Implements REQ: project context stays authoritative.
- [ ] **T-PR0-02**: Update `openspec/_meta/roadmap.md` lines 29 and 80–84 (F1 description + Model Coverage Map) — replace "24 [V]" with "26 [V]", "4 [L-W]" with "6 [L-W]", and add `envio_dian`, `validacion_evento`, `tipo_arqueo`, `resolucion_facturacion` to the appropriate lists.
- [ ] **T-PR0-03**: Update `openspec/_meta/iteration-plan.md` line 21 (F1 description: "45 tables" → "49 tables") and line 44 (F1.6 reference: "45 tables + 11 REVOKE + 11 triggers" → "49 tables + 11 REVOKE + 11 triggers").
- [ ] **T-PR0-04**: Update `openspec/config.yaml` line 14 `context:` — rewrite the data-model line to "AUDIT-FIRST (49 tables, 26 [V] / 3 [L-E] / 6 [L-W] / 2 [L-S] / 12 [A])"; update `rules.proposal` line 20 to reference the 49-table model.
- [ ] **T-PR0-05**: Add `openspec/scripts/check_table_counts.py` — Python helper that scans the four reconciled docs and exits non-zero if any "45 / 24 / 9 / 12" stale token appears; prints the canonical counts.
- [ ] **T-PR0-06**: Add `openspec/scripts/preflight_table_counts.sh` — bash wrapper that calls the Python helper, then queries `\dt prod.*` via `psql $DATABASE_URL` and asserts count ≥ 49, asserts ≥ 11 `_inmutable` triggers, and asserts ≥ 2 `ls_session%` triggers. Exits non-zero on any miss. Refs SC-X4 (REQ-cross-cutting).
- [ ] **T-PR0-07**: Add `AGENTS.md` Risk Register row: "bootstrap PR2 schema completeness" — mitigation: `preflight_table_counts.sh` exit 0. (User instructed T-PR1-18 for this in the prompt; shipped here as PR0 alongside the script.)
- [ ] **T-PR0-08**: Commit + push + open PR. PR title: `docs(create-49-table-apis): reconcile 45→49 table count drift`. PR body includes the diff-stat and links to the script. PR target: `dev` (per `AGENTS.md` gitflow).

### Acceptance
- `python openspec/scripts/check_table_counts.py` exits 0 against the four docs.
- `bash openspec/scripts/preflight_table_counts.sh` exits 0 against the migrated DB after bootstrap PR2 lands.
- All 4 stale docs read "49 tables / 26 [V] / 3 [L-E] / 6 [L-W] / 2 [L-S] / 12 [A]".
- `AGENTS.md` Risk Register references the new preflight check.

### Estimate
~80 changed lines across 6 files (4 edits + 2 new scripts + 1 AGENTS.md row).

---

## PR1 — ORM foundation + auth + JWT three-issuer + master→dev rename

### Branch
`feat/create-49-table-apis-pr1-orm-auth` (off `dev`)

### Dependencies
- Pre-apply gitflow setup completed (`master` → `main`, `dev` created). Verified by T-PR1-01.
- PR0 merged to `dev` (post pre-apply; PR0 is the first PR of `create-49-table-apis`).
- `bootstrap-monorepo-foundation` PR1–PR4 (uv workspace, `parkos_core` package layout, `db/{base,engine,tenancy}.py`, `models/{V,L_E,L_W,L_S,A}/` stubs with `__tablename__` + PK, JWT three issuers in `auth/jwt_three_issuers.py` stub, `/health` routers) reachable from `create-49-table-apis` PR1's branch — operator copies/fetches those files from the bootstrap branch (bootstrap stays on legacy `feature-branch-chain` and is NOT merged to `dev`, per the user's gitflow decision this session).
- `bootstrap-monorepo-foundation` PR2 (`size:exception`) migration file `0001_initial_schema.py` reachable on disk (from bootstrap's branch); operator applies it to the test DB before running `create-49-table-apis` PR2 tests. See PR2 Dependencies note below.

### Work-unit commit boundaries
~12–14 commits (one per task that introduces code or tests; doc updates may co-commit with their related code). T-PR1-01 (pre-apply verification) lands as its own commit so a failed verification block is visible in isolation; it has NO branch-topology side effect (that work was done manually in Pre-apply setup, not in this PR).

### Tasks

- [ ] **T-PR1-01**: **Verify pre-apply gitflow setup is complete.** Check: `git rev-parse --verify main` exits 0 (master was renamed); `git rev-parse --verify dev` exits 0 (dev was cut from main); `git config --get init.defaultBranch` returns `main` (or `master` is absent from `git branch -a`). If any check fails, abort this PR and request the operator to run the Pre-apply setup commands (see Pre-apply setup section above). DO NOT attempt the renames inside this PR — they cannot be done in a PR against `dev`. This is a verification gate, not a mutation. (Risk #9 in `proposal.md`.)
- [ ] **T-PR1-02**: `backend/pyproject.toml` workspace extension + `backend/packages/parkos_core/pyproject.toml` deps (`sqlalchemy[asyncio]>=2.0`, `asyncpg`, `pydantic>=2`, `pydantic-settings`, `python-jose[cryptography]`, `bcrypt`, `passlib[bcrypt]`, `structlog`, `alembic`). Run `uv lock`.
- [ ] **T-PR1-03**: `backend/packages/parkos_core/src/parkos_core/models/{__init__.py, base.py}` — five abstract bases per `design.md` §3.2 (`VersionedBase`, `LifecycleEventBase`, `WorkflowBase`, `SessionBase`, `AppendOnlyBase`) with mixins (`IdMixin`, `AuditMixin`, `SyncMixin`, `VersionedMixin`, `RetentionMixin`, `HashChainMixin`) and the `__write_only__` / `__close_and_insert_only__` / `__record_only__` / `__workflow_only__` / `__session_only__` markers consumed by AST tests.
- [ ] **T-PR1-04**: 6 ORM model files: `models/V/{usuarios,permisos,permisos_usuario,usuarios_sucursal}.py` (4 `[V]` auth, REQ-01 + REQ-OP-13); `models/L_S/login.py` (REQ-42, REQ-46); `models/A/log_transaccional.py` (REQ-16, REQ-X4 with `HashChainMixin` columns).
- [ ] **T-PR1-05**: `schemas/{__init__.py, auth.py, common.py}` — Pydantic v2 `Read`/`Create`/`Update`/`Filter`/`ReadList` for the 5 auth tables; `common.py` carries `_Base` (`ConfigDict(from_attributes=True, extra='forbid')`); field names mirror ORM columns (C-3).
- [ ] **T-PR1-06**: `repo/{__init__.py, versioned.py, session_cycle.py (skeleton), pagination.py}` — `close_and_insert/current_version/history/list_with_cursor` (REQ-04, REQ-05); `record_login` + `close_login_with_log` skeleton (REQ-42, REQ-45); `Cursor` encode/decode (REQ-OP-01).
- [ ] **T-PR1-07**: `auth/{jwt_issuer_guard.py, permissions.py, tenancy.py, tokens.py}` — `verify_jwt`/`requires_issuer` (REQ-X7); `require_permission(codigo)` dep (REQ-OP-13); `TenantContext` + `X-Sucursal-Context` enforcement (REQ-X1, REQ-X2, SC-X1); `issue_token`/`verify_token` with grace rotation (`JWT_OVERLAP_HOURS=24`).
- [ ] **T-PR1-08**: `api/{__init__.py, router_factory.py, deps.py, middleware.py}` — `make_router(*, resource, model_cls, schema_module, repo_kind, derived_view=None, issuer_required, permission_required=None, write_enabled=True, transition_states=None)` per `design.md` §5 (uniform C+Q+U, NO DELETE); dependency re-exports; `IdempotencyKeyMiddleware` (REQ-OP-04).
- [ ] **T-PR1-09**: `api/v1/{__init__.py, auth.py, catalogos.py}` — `POST /auth/login` + `POST /auth/refresh` + `POST /auth/logout` (login uses `record_login` success path; failure path lands in PR7); `catalogos.py` smoke-mounts `tipo-persona` only (full mount in PR3); `__init__.py` adds lazy DIAN-router import guard per `design.md` §10 Layer 2.
- [ ] **T-PR1-10**: Wire `backend/packages/api_admin/src/api_admin_main/app.py` + `api_sucursal_main/app.py` to mount the router factory output under `/api/v1`; both apps lazy-import `dian.cloud_router` only when `PARKOS_DEPLOY=cloud`.
- [ ] **T-PR1-11**: Migration `backend/packages/parkos_core/migrations/versions/0003_seed_permisos_canonicos.py` — INSERT ~15 canonical permission codes (REQ-OP-13: `config_catalogo`, `config_sistema`, `config_sucursal`, `gestionar_clientes`, `emitir_factura`, `emitir_factura_electronica`, `revocar_factura`, `gestionar_dian`, `audit_read`, `admin_usuarios`, `aprobar_anulacion`, `ejecutar_anulacion`, `crear_arqueo`, `solicitar_reverso`, `cerrar_sesion`, `descartar_alerta`). Idempotent (`ON CONFLICT DO NOTHING`).
- [ ] **T-PR1-12**: Migration pre-flight — `uv run alembic upgrade --sql head`; inspect for the 16 `INSERT INTO prod.permisos …` lines. Apply via `alembic upgrade head`.
- [ ] **T-PR1-13**: `backend/tests/conftest.py` — testcontainers Postgres + Redis fixtures + JWT mint helpers (`mint_admin_jwt`, `mint_operador_jwt`, `mint_sync_agent_jwt`) per `design.md` §15.
- [ ] **T-PR1-14**: Migration tests — `tests/migrations/test_a_inmutable.py` (12 fixtures, SC-10-A-INMUTABLE-DB), `test_ls_session_guard.py` (2 fixtures, SC-42), `test_revokes_active.py` (REQ-X5), `test_partman_parents.py` (8 partman parents, REQ-X6).
- [ ] **T-PR1-15**: Static AST tests — `tests/static/test_no_delete_routes.py` (SC-04), `test_no_raw_upsert_on_v_tables.py` (C-2), `test_no_raw_dml_on_a_tables.py` (REQ-13), `test_no_raw_dml_on_ls_tables.py` (REQ-46), `test_openapi_branch_excludes_cloud.py` smoke (REQ-X3), `test_openapi_no_delete_operations.py` (SC-04).
- [ ] **T-PR1-16**: Unit tests — `test_versioned_close_and_insert.py` (REQ-04, REQ-05, 409 on collision), `test_jwt_issuer_guard.py` (REQ-X7, REQ-X8 cross-audience → 401), `test_permissions_dependency.py` (REQ-OP-13, SC-OP-04), `test_tenancy_operador.py` + `test_tenancy_admin.py` (REQ-X1, REQ-X2, SC-X1), `test_pagination_cursor.py` (REQ-OP-01, SC-OP-01), `test_session_cycle_record_login.py` (REQ-42, REQ-43).
- [ ] **T-PR1-17**: Add `pyproject.toml` ruff rules — `select = ["E","F","I","UP","B","ASYNC","SIM","PT","RUF"]`; per-file ignores for `tests/**` (`B`, `PT011`, `S101`) and `migrations/**` (`E501`); AST rule file for `session.execute(update/delete)` rejection.
- [ ] **T-PR1-18**: `apps/ui-kit/src/api/{admin,branch}/generated/.gitkeep` placeholders + update `AGENTS.md` Risk Register to mark "bootstrap PR2 schema completeness" as mitigated (now that PR0 + preflight landed).
- [ ] **T-PR1-19**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): ORM foundation + auth + JWT three-issuer`. PR body includes the test summary and chain context (📍 PR1 of 8). Add `type:feature` label.

### Acceptance
- `uv run pytest backend/tests/migrations/test_a_inmutable.py -q` passes (12 fixtures).
- `uv run pytest backend/tests/migrations/test_ls_session_guard.py -q` passes (2 fixtures).
- `uv run pytest backend/tests/migrations/test_revokes_active.py -q` passes.
- `uv run pytest backend/tests/migrations/test_partman_parents.py -q` passes.
- `uv run pytest backend/tests/repo/test_versioned.py -q` passes.
- `uv run pytest backend/tests/api/test_no_delete_routes.py -q` passes.
- `uv run pytest backend/tests/{unit,static} -q` all pass.
- `uv run ruff check backend/packages/parkos_core/` passes (no AST rule violations).
- Login flow: `curl -X POST http://localhost:8000/api/v1/auth/login -d '{"email":"...","password":"..."}' -H 'Content-Type: application/json'` returns JWT with correct `iss`, `aud`, `kid`; `curl /api/v1/tipo-persona` with cross-issuer token returns 401.

### Estimate
~700 LOC across ~30 files (5 model + 7 schema + 6 repo + 4 auth + 4 api + 2 main + 13 tests + 1 migration + 1 ruff config).

---

## PR2 — `[A]` infrastructure: sync_queue + log_transaccional + hash-chain genesis + append_only helper

### Branch
`feat/create-49-table-apis-pr2-a-infra` (off `dev`)

### Dependencies
- PR1 merged to `dev`.
- `bootstrap-monorepo-foundation` PR2 (`size:exception`) migration file `0001_initial_schema.py` reachable on disk (operator fetches it from bootstrap's branch — bootstrap stays on legacy `feature-branch-chain`). **Operator MUST apply this migration to the test DB BEFORE running PR2 tests.** Without it, the migration tests (T-PR2-08/09/10/19) cannot run because the 49 schema tables won't exist. If the operator cannot or will not do this, PR2 MUST ship its own schema baseline migration in the same PR (which duplicates bootstrap's work but is acceptable for `create-49-table-apis` to land independently). Document the chosen path in the PR description.

### Work-unit commit boundaries
~8–10 commits. The DB-side `AFTER INSERT` trigger is bootstrap-owned; this PR verifies the trigger via tests and wires the helpers. `repo/append_only.py` and `repo/hash_chain.py` may commit separately for atomic review.

### Tasks

- [ ] **T-PR2-01**: Create `models/A/sync_queue.py`, `sync_log.py`, `sync_conflict.py` — 3 `[A]` sync infra tables; subclass `AppendOnlyBase`; `sync_queue` carries `ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS` documentation. REQ-14-A-SYNC-FACADE.
- [ ] **T-PR2-02**: Create `models/A/caja.py`, `arqueo.py`, `revocacion_factura.py` — 3 `[A]` tables; `revocacion_factura` adds `HashChainMixin`. REQ-16-A-HASH-CHAIN.
- [ ] **T-PR2-03**: Create `models/A/__init__.py` — re-exports for Alembic discovery.
- [ ] **T-PR2-04**: Create `repo/append_only.py` — `append_event()` (REQ-10-A-INSERCION) + `mark_dispatched()` + `mark_failed()` + `schedule_retry()` (REQ-14 + SC-13). The four whitelisted `sync_queue` columns enforced both client-side (frozenset) and via `tests/migrations/test_sync_queue_whitelist.py`.
- [ ] **T-PR2-05**: Create `repo/hash_chain.py` — `_canonical_json()`, `append(session, model_cls, payload, actor_uuid)` per `design.md` §4.6. Reads prior `MAX(timestamp_evento)` row per `uuid_sucursal`; raises `HashChainIntegrityViolation` on mismatch. REQ-16, REQ-X4.
- [ ] **T-PR2-06**: Create `repo/sync_outbox.py` — `enqueue_sync_row()` raises `RuntimeError` no-op facade per `design.md` §12. Refs REQ-X6, SC-X5.
- [ ] **T-PR2-07**: Create `schemas/sync_infra.py` — Pydantic `Read`/`Create` for `sync_queue`, `sync_log`, `sync_conflict`, `log_transaccional`, `caja`, `arqueo`, `revocacion_factura`. `Read` excludes `hash_anterior`/`hash_actual` from `Create` (server-computed only). SC-X2.
- [ ] **T-PR2-08**: Test `backend/tests/migrations/test_sync_queue_whitelist.py` — fuzz test: `mark_dispatched`/`mark_failed`/`schedule_retry` accept only the 4 whitelisted columns; any other column name in helper input raises `ValueError`. SC-13-A-SYNC-QUEUE-MARK-DISPATCHED.
- [ ] **T-PR2-09**: Test `backend/tests/migrations/test_sync_outbox_recursion.py` — `INSERT INTO prod.sync_queue …` does NOT create a second `sync_queue` row (DB trigger's `WHEN (TG_TABLE_NAME <> 'sync_queue')` filter). REQ-X6, SC-X5.
- [ ] **T-PR2-10**: Test `backend/tests/migrations/test_hash_chain_genesis.py` — first `log_transaccional` row per `uuid_sucursal` has `hash_anterior = sha256(b'genesis:' + uuid_sucursal_bytes).hexdigest()`. REQ-16, REQ-X4, SC-12-A-HASH-CHAIN.
- [ ] **T-PR2-11**: Test `backend/tests/unit/test_append_only.py` — `append_event` succeeds; `session.execute(update(...))` against any of the 13 `[A]` classes raises `AppendOnlyError`. REQ-10, REQ-13.
- [ ] **T-PR2-12**: Test `backend/tests/unit/test_hash_chain_append.py` — second row's `hash_anterior` = prior row's `hash_actual`; canonical JSON deterministic across dict insertion order; out-of-order payload raises `HashChainIntegrityViolation`. SC-X2, SC-X3.
- [ ] **T-PR2-13**: Test `backend/tests/unit/test_sync_outbox.py` — `repo.sync_outbox.enqueue_sync_row()` always raises `RuntimeError`; documents that the DB trigger owns enqueue.
- [ ] **T-PR2-14**: Migration pre-flight check (no new migration; verify `alembic upgrade head` is idempotent — running twice produces no change). REQ-cross-cutting.
- [ ] **T-PR2-15**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): [A] infrastructure + sync outbox + hash-chain genesis helper`. Add `type:feature` label.

### Acceptance
- `uv run pytest backend/tests/migrations/test_sync_queue_whitelist.py -q` passes (fuzz inputs verified).
- `uv run pytest backend/tests/migrations/test_sync_outbox_recursion.py -q` passes.
- `uv run pytest backend/tests/migrations/test_hash_chain_genesis.py -q` passes.
- `uv run pytest backend/tests/unit/test_append_only.py -q` passes.
- `uv run pytest backend/tests/unit/test_hash_chain_append.py -q` passes.
- `uv run pytest backend/tests/unit/test_sync_outbox.py -q` passes.
- `uv run alembic upgrade head` twice in a row produces no diff (idempotency).

### Estimate
~700 LOC across ~17 files (8 model + 3 repo + 1 schema + 6 tests).

---

## PR3 — Catalog domain (8 `[V]` catalogs + `tipo_arqueo`)

### Branch
`feat/create-49-table-apis-pr3-catalogs` (off `dev`)

### Dependencies
- PR1 + PR2 merged to `dev`.

### Work-unit commit boundaries
~7 commits. The 9 catalog model files may commit in one batch (mechanical pattern); the schema file and the router file commit together (model + schema + router = one feature unit per REQ-OP-13).

### Tasks

- [ ] **T-PR3-01**: Create `models/V/{tipo_persona,tipos_vehiculo,tipo_subscripciones,tipo_tarifa,tipo_sucursal,tipo_arqueo,impuestos,otros_cobros,costos_servicios}.py` — 9 `[V]` catalog tables, subclass `VersionedBase`. `tipo_arqueo` is the 4th missing table reconciled from PR0. REQ-01-V-CONSULTA, REQ-OP-13.
- [ ] **T-PR3-02**: Create `schemas/catalogos.py` — 9 Pydantic `Read`/`Create`/`Update`/`Filter`/`ReadList` quadruples per catalog. All inherit `_Base` from `schemas/common.py`. Field names mirror ORM columns (C-3).
- [ ] **T-PR3-03**: Create `api/v1/catalogos.py` (full — replace PR1's smoke mount) — 9 `make_router(...)` calls, each with `issuer_required="admin-,operador-"`, `permission_required="config_catalogo"`. SC-01-V-CATALOG-CRUD.
- [ ] **T-PR3-04**: Wire `api/v1/__init__.py` to include `catalogos_router`. Verify mount via `app.openapi()` smoke test.
- [ ] **T-PR3-05**: Test `backend/tests/unit/test_catalogos_crud.py` — for each catalog: admin POST creates a new row with `vigente_desde=NOW()` (REQ-03); admin PUT closes current + inserts new (REQ-04); GET `/<r>/{uuid}/historial` returns versions in DESC order (REQ-05); operador GET works (catalogs replicated). SC-01.
- [ ] **T-PR3-06**: Test `backend/tests/unit/test_catalogos_filter.py` — `?vigente_desde__gte=...`, `?estado=activo`, `?vigente_hasta__isnull=true` filters; extra fields rejected via `extra='forbid'`. REQ-06-V-FILTRO.
- [ ] **T-PR3-07**: Test `backend/tests/integration/test_crud_happy_path.py` — end-to-end catalog flow: POST → GET single → PUT → GET history → GET list (current version only). Implements SC-01.
- [ ] **T-PR3-08**: Refresh `backend/packages/api_{admin,sucursal}/openapi.json` artifacts via `uv run python -m parkos_core.openapi --deploy {cloud,branch}`.
- [ ] **T-PR3-09**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): catalog domain (9 [V] tables)`. Add `type:feature` label.

### Acceptance
- `uv run pytest backend/tests/unit/test_catalogos_crud.py -q` passes (9 catalogs × 4 ops = 36 assertions).
- `uv run pytest backend/tests/unit/test_catalogos_filter.py -q` passes.
- `uv run pytest backend/tests/integration/test_crud_happy_path.py -q` passes.
- `jq '.paths | keys | map(select(test("/tipo-persona|/tipos-vehiculo|/tipo-subscripciones|/tipo-tarifa|/tipo-sucursal|/tipo-arqueo|/impuestos|/otros-cobros|/costos-servicios"))) | length' backend/packages/api_admin/openapi.json` returns 9.
- `jq '.paths | keys | map(select(test("/tipo-arqueo")))' backend/packages/api_sucursal/openapi.json` returns 1 (read-only replicated).

### Estimate
~600 LOC across ~13 files (9 model + 1 schema + 1 router + 3 tests).

---

## PR4 — Empresa + Sucursal + per-branch config (8 `[V]` tables)

### Branch
`feat/create-49-table-apis-pr4-empresa-sucursal` (off `dev`)

### Dependencies
- PR1 + PR3 merged to `dev` (`sucursal` FKs `tipo_sucursal`, `empresa`).

### Work-unit commit boundaries
~8 commits. `resolucion_facturacion` deserves its own commit (DIAN-coupling). The config override pattern (REQ-OP-12 + SC-OP-06) commits separately for review focus.

### Tasks

- [ ] **T-PR4-01**: Create `models/V/{empresa,sucursal,documentos,resolucion_facturacion,tarifas_sucursal,cantidad_vehiculos_sucursal,configuracion_tolerancias,configuracion_seguridad}.py` — 8 `[V]` tables. `documentos` carries `documento_b64 String(1_400_000)` for 1MB cap. `resolucion_facturacion` is the 4th missing table reconciled from PR0 (DIAN root, cloud-only writes). REQ-01.
- [ ] **T-PR4-02**: Create `schemas/{empresa.py, configuracion.py}` — Pydantic `Read`/`Create`/`Update`/`Filter`/`ReadList` for the 8 tables; `DocumentosCreate` rejects `documento_b64` > 1MB; `ResolucionFacturacionCreate` server-assigns `prefijo` and `rango_desde`/`rango_hasta` ranges.
- [ ] **T-PR4-03**: Create `api/v1/empresa.py` — `make_router(...)` for `empresa`, `sucursal`, `documentos`, `resolucion-facturacion`, `tarifas-sucursal`, `cantidad-vehiculos-sucursal`. Cloud-only writes via `issuer_required="admin-"` + `X-Sucursal-Context` enforcement; branch reads via `issuer_required="admin-,operador-"` for replicated tables only.
- [ ] **T-PR4-04**: Create `api/v1/configuracion.py` — `make_router(...)` for `configuracion-tolerancias`, `configuracion-seguridad`. Adds the custom `GET /configuracion-seguridad/efectiva?uuid_sucursal=<uuid>` route that resolves the per-branch override OR falls back to the global default (`vigente_hasta IS NULL AND uuid_sucursal IS NULL`). REQ-OP-12, SC-OP-06.
- [ ] **T-PR4-05**: Create `api/v1/sucursal.py` — minimal: a `GET /sucursal/{uuid}/pairing-token` endpoint that returns a 24h single-use pairing token (REQ-OP-15). Cloud-only. Token mint via `auth/tokens.py` extension (already shipped in PR1).
- [ ] **T-PR4-06**: Wire `api/v1/__init__.py` to include `empresa_router`, `configuracion_router`, `sucursal_router`.
- [ ] **T-PR4-07**: Test `backend/tests/unit/test_config_override_resolution.py` — write global default; write per-branch override; resolve for override branch → override value; resolve for non-override branch → global value. SC-OP-06, SC-03-V-CONFIG-OVERRIDE.
- [ ] **T-PR4-08**: Test `backend/tests/unit/test_resolucion_facturacion_crud.py` — admin POST + GET works on cloud; branch token attempts to write `resolucion_facturacion` → 403 (issuer guard). REQ-01, REQ-X3.
- [ ] **T-PR4-09**: Test `backend/tests/unit/test_documentos_b64_cap.py` — Pydantic rejects `documento_b64` > 1MB with 422; accepts ≤ 1MB. REQ-OP-05.
- [ ] **T-PR4-10**: Test `backend/tests/unit/test_pairing_token_endpoint.py` — admin issues token; consuming token is 24h-TTL single-use. REQ-OP-15.
- [ ] **T-PR4-11**: Refresh both OpenAPI artifacts; verify `resolucion-facturacion` paths present in `api_admin/openapi.json` and ABSENT in `api_sucursal/openapi.json`. REQ-X3.
- [ ] **T-PR4-12**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): empresa + sucursal + per-branch config (8 [V] tables)`. Add `type:feature` label.

### Acceptance
- `uv run pytest backend/tests/unit/test_config_override_resolution.py -q` passes (SC-OP-06).
- `uv run pytest backend/tests/unit/test_resolucion_facturacion_crud.py -q` passes (REQ-X3 boundary enforced).
- `uv run pytest backend/tests/unit/test_documentos_b64_cap.py -q` passes.
- `uv run pytest backend/tests/unit/test_pairing_token_endpoint.py -q` passes.
- `curl -X POST http://localhost:8000/api/v1/resolucion-facturacion -H "Authorization: Bearer $ADMIN_JWT"` returns 201; same call with `$OPERADOR_JWT` returns 403.

### Estimate
~750 LOC across ~12 files (8 model + 2 schema + 3 router + 4 tests).

---

## PR5 — Commercial domain + `[L-E] ingreso`

### Branch (PR5)
`feat/create-49-table-apis-pr5-commercial-ingreso` (off `dev`)

### Dependencies
- PR3 + PR4 merged to `dev` (FKs: `clientes.uuid_tipo_persona`, `vehiculos.uuid_tipo_vehiculo`, `ingreso.uuid_subscripcion_cliente`).

### Conditional split (apply-time trigger)
If `git diff --stat` post-implementation > 800 LOC → execute **PR5a** (`[V]` commercial, 5 tables, ~500 LOC) + **PR5b** (`[L-E] ingreso`, 1 table, ~300 LOC).

### Work-unit commit boundaries (PR5)
~9 commits. Each `[V]` commercial model file in its own commit (mechanical but reviewable). The `subscripcion_vehiculos` validator (REQ-OP-08 + SC-OP-08) is its own commit.

### Tasks

- [ ] **T-PR5-01**: Create `models/V/{clientes,clientes_b2b,subscripciones_cliente,vehiculos,subscripcion_vehiculos}.py` — 5 `[V]` commercial tables, subclass `VersionedBase`. REQ-01.
- [ ] **T-PR5-02**: Create `models/L_E/ingreso.py` — `[L-E]` lifecycle event for vehicle entry, subclass `LifecycleEventBase`. Carries `timestamp_evento`, `uuid_subscripcion_cliente` (nullable), `uuid_cliente`, `uuid_vehiculo`. REQ-30-E-INSERCION.
- [ ] **T-PR5-03**: Create `repo/event.py` (full) — `record_event()` per `design.md` §4.5. Pure INSERT; refuses UPDATE/DELETE; raises `LifecycleEventWriteError`. REQ-30.
- [ ] **T-PR5-04**: Create `schemas/clientes.py` — Pydantic for `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`. `SubscripcionVehiculosCreate` validator (`model_validator(mode='after')`) asserts `count(active vehiculos for this subscripcion) <= cantidad_maxima_vehiculos of the plan` via `pg_advisory_xact_lock(uuid_subscripcion_cliente)` to prevent concurrent overflow. REQ-OP-08 + risk #18.
- [ ] **T-PR5-05**: Create `schemas/operacion.py` — Pydantic for `ingreso` (`Read`/`Create`). `IngresoCreate` requires `Idempotency-Key` header.
- [ ] **T-PR5-06**: Create `api/v1/clientes.py` — `make_router(...)` for the 5 commercial tables. `issuer_required="operador-,admin-"` (operator writes locally, admin reads cross-branch).
- [ ] **T-PR5-07**: Create `api/v1/operacion.py` — `make_router(...)` for `ingreso`. Adds nested derived `GET /ingresos/{uuid}/estado` reading `V_INGRESO_ESTADO`. REQ-32-E-DERIVED-ESTADO, SC-30.
- [ ] **T-PR5-08**: Wire `api/v1/__init__.py` to include `clientes_router`, `operacion_router`.
- [ ] **T-PR5-09**: Test `backend/tests/unit/test_event_record.py` — `record_event` happy path; concurrent insert via two `AsyncSession`s race on partition key; rejects UPDATE/DELETE. REQ-30, REQ-33.
- [ ] **T-PR5-10**: Test `backend/tests/unit/test_subscripcion_vehiculos_validator.py` — count overflow → 422; concurrent inserts serialized via advisory lock; legitimate insert succeeds. REQ-OP-08.
- [ ] **T-PR5-11**: Test `backend/tests/unit/test_clientes_crud.py` — admin cross-branch read; operador branch write; PUT close+insert. REQ-01–04.
- [ ] **T-PR5-12**: Test `backend/tests/unit/test_ingreso_estado.py` — derived `V_INGRESO_ESTADO` returns `abierto` initially, transitions to `cerrado` after `salidas` row (PR6 mounts), transitions to `anulada` after `anulaciones` chain (PR6). SC-30.
- [ ] **T-PR5-13**: Test `backend/tests/static/test_no_raw_dml_on_le_tables.py` — AST scan rejects `session.execute(update/delete)` against `ingreso` outside `repo/event.py`. REQ-33.
- [ ] **T-PR5-14**: Refresh both OpenAPI artifacts.
- [ ] **T-PR5-15**: Migration pre-flight (no new migration; verify `alembic check` exits 0).
- [ ] **T-PR5-16**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): commercial + ingreso (5 [V] + 1 [L-E])`. Add `type:feature` label.

### Acceptance
- `uv run pytest backend/tests/unit/test_event_record.py -q` passes (REQ-30, REQ-33).
- `uv run pytest backend/tests/unit/test_subscripcion_vehiculos_validator.py -q` passes (REQ-OP-08).
- `uv run pytest backend/tests/unit/test_clientes_crud.py -q` passes.
- `uv run pytest backend/tests/unit/test_ingreso_estado.py -q` passes (SC-30 partial — full state machine requires PR6).
- `uv run pytest backend/tests/static/test_no_raw_dml_on_le_tables.py -q` passes.
- `jq '.paths | keys | map(select(test("/ingresos")))' backend/packages/api_admin/openapi.json` shows `ingresos` + `ingresos/{uuid}/estado`.

### Estimate
~800 LOC across ~14 files (6 model + 2 schema + 2 router + 1 repo + 6 tests). **Apply-time split trigger: > 800 LOC → PR5a (commercial) + PR5b (ingreso).**

---

## PR6 — Operations + `[L-W]` workflows + `[A]` billing + DIAN boundary

### Branch (PR6)
`feat/create-49-table-apis-pr6-operations-workflows` (off `dev`)

### Dependencies
- PR5 merged to `dev` (`facturas` FKs `ingreso` / `salidas`).

### Conditional split (apply-time trigger)
If `git diff --stat` post-implementation > 800 LOC → execute **PR6a** (`[L-E] facturas + [A] factura_detalle/impuestos/otros_cobros/pagos`, 6 tables, ~600 LOC) + **PR6b** (`[L-W]` workflows + `[L-E] factura_electronica` + `[A] revocacion_factura`, 6 tables, ~500 LOC).

### Work-unit commit boundaries (PR6)
~12 commits. The DIAN boundary test (T-PR6-13) is its own commit (defense in depth artifact). The polymorphic validator (T-PR6-04) and the partial unique index migration (T-PR6-05) commit separately for review focus.

### Tasks

- [ ] **T-PR6-01**: Create `models/L_E/facturas.py`, `factura_electronica.py` — 2 `[L-E]` tables; `factura_electronica` is cloud-only. REQ-30, REQ-34.
- [ ] **T-PR6-02**: Create `models/A/{factura_detalle,factura_impuestos,factura_otros_cobros,factura_pagos}.py` — 4 `[A]` billing tables, subclass `AppendOnlyBase`. REQ-10, REQ-15.
- [ ] **T-PR6-03**: Create `models/L_W/{anulaciones,reclamos,alerta,reimpresion_ticket,envio_dian,validacion_evento}.py` — 6 `[L-W]` workflow tables, subclass `WorkflowBase`. `envio_dian`, `validacion_evento` are the 3rd/4th missing tables reconciled from PR0 (cloud-only). REQ-21, REQ-22.
- [ ] **T-PR6-04**: Create `repo/workflow.py` (full) — `append_transition()`, `read_chain_tip()`, `STATE_MACHINES` per `design.md` §4.2. Deterministic tie-break: `(max(timestamp_evento), count_of_rows, lex(uuid))` per REQ-X9. Includes `polymorphic_row_exists()` for `reclamos` (REQ-OP-08, REQ-23-W-POLYMORPHIC-FK).
- [ ] **T-PR6-05**: Create `repo/factura_pagos.py` — `reverse_payment()` with Pydantic `tipo_movimiento` discriminator validator + partial unique index test (REQ-OP-09, SC-11).
- [ ] **T-PR6-06**: Migration `backend/packages/parkos_core/migrations/versions/0004_add_factura_pagos_reverso_index.py` — `CREATE UNIQUE INDEX uq_factura_pagos_reverso ON prod.factura_pagos (uuid_pago_revertido) WHERE tipo_movimiento = 'reverso' AND uuid_pago_revertido IS NOT NULL;`. Per `config.yaml` rules.tasks (index-only — no `[A]` mutation, but REVOKE re-asserted defensively).
- [ ] **T-PR6-07**: Migration pre-flight — `uv run alembic upgrade --sql head`; inspect the partial unique index. Apply.
- [ ] **T-PR6-08**: Create `schemas/{facturacion.py, workflows.py, dian.py}` — Pydantic for the 12 tables. `ReclamoCreate` polymorphic validator (REQ-23-W-POLYMORPHIC-FK). `AlertaCreate` admin-only reject when `estado='descartada'` is attempted by the alert's user (REQ-26-W-ALERTA-DESCARTADA). `FacturaElectronicaCreate` server-assigns `prefijo + consecutivo` (REQ-34).
- [ ] **T-PR6-09**: Create `dian/cloud_router.py` — cloud-only module that mounts the 4 cloud-only routes:
  - `POST /api/v1/factura-electronica` (REQ-34, REQ-35) — atomic `SELECT FOR UPDATE` on `resolucion_facturacion` row + `consecutivo_actual++` + `INSERT factura_electronica` with `fecha_retencion_hasta = NOW() + INTERVAL '5 years'`. Cloud-only via `issuer_required="admin-,operador-"` + `PARKOS_DEPLOY=cloud` import-guard.
  - `POST /api/v1/envio-dian` (REQ-25-W-CLOUD-ONLY) — workflow transition for DIAN send/ack.
  - `POST /api/v1/validacion-evento` (REQ-25) — admin validation of received events.
  - `POST /api/v1/revocacion-factura-webhook` (REQ-X3) — receives DIAN revocation, inserts `revocacion_factura` row extending the hash chain.
- [ ] **T-PR6-10**: Create `api/v1/{facturacion.py, workflows.py}` — `make_router(...)` calls. `facturacion` mounts the 5 non-cloud `[L-E]` + `[A]` billing tables; `workflows` mounts the 4 branch-originated `[L-W]` tables (`anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`). Cloud-only `[L-W]` (`envio_dian`, `validacion_evento`) live only in `dian/cloud_router.py`.
- [ ] **T-PR6-11**: Wire `api/v1/__init__.py` to lazy-import `dian.cloud_router` ONLY when `PARKOS_DEPLOY=cloud`. On branch: raise `ImportError("cloud_router_unavailable_on_branch")`. Per `design.md` §10 Layer 2.
- [ ] **T-PR6-12**: Add `parkos_core/cache/poly_cache.py` — Redis-backed cache (60s TTL) for `polymorphic_row_exists()` lookups; populated by sync worker (out of scope here, only consumer ships). REQ-OP-08 + risk #17.
- [ ] **T-PR6-13**: Test `backend/tests/static/test_dian_boundary_branch.py` — set `PARKOS_DEPLOY=branch` and assert `from parkos_core.dian.cloud_router import router` raises `ImportError`. REQ-X3, SC-X6.
- [ ] **T-PR6-14**: Test `backend/tests/static/test_no_raw_dml_on_lw_tables.py` — AST scan rejects `session.execute(update/delete)` against the 6 `[L-W]` classes outside `repo/workflow.py`. REQ-21.
- [ ] **T-PR6-15**: Test `backend/tests/unit/test_workflow_append_transition.py` — happy path for each state machine; illegal transition → 422; `append_transition` writes co-transactional `log_transaccional` row. REQ-21, SC-20.
- [ ] **T-PR6-16**: Test `backend/tests/unit/test_workflow_read_chain_tip.py` — N chains; tie-break deterministic (REQ-X9); returns `{uuid_root, uuid_actual, estado, timestamp_evento, chain_length}`.
- [ ] **T-PR6-17**: Test `backend/tests/unit/test_factura_pagos_reverse.py` — `reverse_payment` happy path; second reversal attempt raises `DuplicateReversoError` (409) via partial unique index. REQ-OP-09, SC-11.
- [ ] **T-PR6-18**: Test `backend/tests/unit/test_reclamos_polymorphic_validator.py` — unknown `tipo_reclamable` → 422; valid + non-existent `uuid_reclamable` → 422; valid + existing → 201. REQ-OP-08, REQ-23.
- [ ] **T-PR6-19**: Test `backend/tests/migrations/test_factura_pagos_reverso_index.py` — second reversal of same `uuid_pago_revertido` fails with `UniqueViolation`. SC-11.
- [ ] **T-PR6-20`: Test `backend/tests/integration/test_branch_offline_flow.py` — branch emits `factura` with `numero_temporal`; cloud `SyncBackEvent` flows back (mock); `reimpresion_ticket` enabled after sync-back. SC-33, SC-34.
- [ ] **T-PR6-21**: Refresh both OpenAPI artifacts. Verify cloud-only paths (`/factura-electronica`, `/envio-dian`, `/validacion-evento`, `/revocacion-factura-webhook`) are present in `api_admin/openapi.json` and ABSENT in `api_sucursal/openapi.json`. REQ-X3.
- [ ] **T-PR6-22**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): operations + workflows + DIAN boundary (12 tables)`. Add `type:feature` label.

### Acceptance
- `uv run pytest backend/tests/static/test_dian_boundary_branch.py -q` passes (REQ-X3).
- `uv run pytest backend/tests/static/test_no_raw_dml_on_lw_tables.py -q` passes (REQ-21).
- `uv run pytest backend/tests/unit/test_workflow_append_transition.py -q` passes.
- `uv run pytest backend/tests/unit/test_workflow_read_chain_tip.py -q` passes (REQ-X9).
- `uv run pytest backend/tests/unit/test_factura_pagos_reverse.py -q` passes (REQ-OP-09).
- `uv run pytest backend/tests/unit/test_reclamos_polymorphic_validator.py -q` passes (REQ-OP-08).
- `uv run pytest backend/tests/migrations/test_factura_pagos_reverso_index.py -q` passes (SC-11).
- `uv run pytest backend/tests/integration/test_branch_offline_flow.py -q` passes (SC-33, SC-34).
- `jq '.paths | keys | map(select(test("/factura-electronica|/envio-dian|/validacion-evento|/revocacion-factura"))) | length' backend/packages/api_admin/openapi.json` returns 4 (the 4 cloud-only paths).
- `jq '.paths | keys | map(select(test("/factura-electronica|/envio-dian|/validacion-evento|/revocacion-factura"))) | length' backend/packages/api_sucursal/openapi.json` returns 0.
- `curl -X POST http://localhost:8000/api/v1/factura-electronica` with branch image → process never reaches the route (ImportError at import time).

### Estimate
~800 LOC across ~22 files (12 model + 3 schema + 1 cloud router + 2 router + 1 cache + 3 static tests + 6 unit/integration tests + 1 migration). **Apply-time split trigger: > 800 LOC → PR6a (5 billing/facturas) + PR6b (6 workflows).**

---

## PR7 — Caja + `[L-S]` sesion + sync infra + idempotency_keys (50th `[A]`)

### Branch
`feat/create-49-table-apis-pr7-caja-sesion` (off `dev`)

### Dependencies
- PR6 merged to `dev` (`sesion` FKs `factura_pagos`; `arqueo` FKs `sesion`; `alerta` FKs `arqueo`).

### Work-unit commit boundaries
~10 commits. The `0002_add_idempotency_keys.py` migration (REVOKE + trigger in same script per `config.yaml` rules.tasks) commits separately. The login-failure lockout (REQ-OP-11 + REQ-43) commits separately.

### Tasks

- [ ] **T-PR7-01**: Create `models/L_S/sesion.py` — `[L-S]` cash session table, subclass `SessionBase`. REQ-40-S-OPEN, REQ-41-S-CLOSE.
- [ ] **T-PR7-02**: Create `models/A/{caja,arqueo}.py` — already partly in PR2; finalize schemas here (any extra columns). REQ-10-A-INSERCION.
- [ ] **T-PR7-03**: Create `models/A/idempotency_keys.py` — 50th `[A]` table; subclass `AppendOnlyBase`; carries `endpoint`, `key_hash`, `request_payload_hash`, `response_status`, `response_body`, `expires_at`. REQ-OP-04.
- [ ] **T-PR7-04**: Migration `backend/packages/parkos_core/migrations/versions/0002_add_idempotency_keys.py` — `CREATE TABLE prod.idempotency_keys ...` + `CREATE UNIQUE INDEX uq_idempotency_keys_key_hash_endpoint ON prod.idempotency_keys (key_hash, endpoint) WHERE expires_at > NOW();` + `REVOKE UPDATE, DELETE ON prod.idempotency_keys FROM rol_app` + `CREATE TRIGGER idempotency_keys_inmutable BEFORE UPDATE OR DELETE ... EXECUTE FUNCTION prod.fn_idempotency_keys_inmutable();` — ALL in the SAME migration per `config.yaml` rules.tasks.
- [ ] **T-PR7-05`: Migration pre-flight — `uv run alembic upgrade --sql head`; inspect the CREATE TABLE + REVOKE + TRIGGER appear in sequence. Apply.
- [ ] **T-PR7-06`: Create `repo/session_cycle.py` (full) — `open_session()`, `close_session_with_log()` (REQ-41), `record_login()` already in PR1; add lockout counter (`close_and_insert()` on `usuarios` if `intentos_fallo` >= 3 in last 15 min, lockout 30 min) per REQ-OP-11, REQ-43.
- [ ] **T-PR7-07`: Create `repo/idempotency.py` — `guard(session, endpoint, idempotency_key, request_body, actor_uuid)` (returns `(status, body, is_replay)` or `None`; raises `IdempotencyKeyRequiredError` on missing key, `IdempotencyConflictError` on key reuse with different body), `store_response(...)` per `design.md` §4.7. REQ-OP-04, SC-OP-02.
- [ ] **T-PR7-08`: Create `schemas/{caja.py, idempotency.py}` — Pydantic for `caja`, `arqueo`, `sesion`, `idempotency_keys` (Read-only for the latter; written by middleware).
- [ ] **T-PR7-09`: Create `api/v1/caja.py` — `make_router(...)` for `caja`, `arqueo`; `sesion` lives under `api/v1/caja_sesion.py` (created here) with `PUT /sesion/{uuid}/cerrar` calling `close_session_with_log()`. Also adds derived `GET /arqueos/{uuid}/diferencias` reading `V_ARQUEO_DIFERENCIAS`. SC-40-S-FULL-SHIFT.
- [ ] **T-PR7-10`: Wire `api/v1/__init__.py` to include `caja_router`. Update `api/router_factory.py` to call `idempotency_guard()` on every POST handler (the per-route hook).
- [ ] **T-PR7-11`: Test `backend/tests/migrations/test_idempotency_keys_inmutable.py` — INSERT succeeds; UPDATE raises `IDEMPOTENCY_KEYS_INMUTABLE`; DELETE raises same. SC-13.
- [ ] **T-PR7-12`: Test `backend/tests/unit/test_idempotency_guard.py` — missing `Idempotency-Key` header on POST → 400 `IdempotencyKeyRequiredError`; replay with same key + same body → cached response with `Idempotent-Replay: true` header; replay with same key + different body → 409 `IdempotencyConflictError`. REQ-OP-04, SC-OP-02.
- [ ] **T-PR7-13`: Test `backend/tests/unit/test_idempotency_ttl.py` — entry past `expires_at` is treated as fresh (not cached); new POST inserts a new `idempotency_keys` row.
- [ ] **T-PR7-14`: Test `backend/tests/unit/test_session_cycle_open_close.py` — open session writes `log_transaccional` first; close_session_with_log writes log FIRST, then UPDATE in same TX; DB trigger's `LOG_TRANSACCIONAL_REQUIRED` fires if log is missing. SC-40, SC-42.
- [ ] **T-PR7-15`: Test `backend/tests/unit/test_session_cycle_login_failure_lockout.py` — 3 failures within 15 min lock the user out for 30 min; success after lockout clears counter via `close_and_insert()`. REQ-OP-11, REQ-43, SC-41.
- [ ] **T-PR7-16`: Test `backend/tests/unit/test_session_cycle_logout.py` — `close_login_with_log` writes log + UPDATE login row in same TX. REQ-45.
- [ ] **T-PR7-17`: Test `backend/tests/integration/test_crud_happy_path.py` (extended) — full shift: login → open sesion → pay (factura_pagos) → close sesion → logout. SC-40.
- [ ] **T-PR7-18`: Refresh both OpenAPI artifacts.
- [ ] **T-PR7-19`: Update `AGENTS.md` Risk Register — add row: "Idempotency table `idempotency_keys` is the 50th table — out of scope for bootstrap. Mitigation: PR7 ships migration `0002_add_idempotency_keys.py` with REVOKE + trigger in same script."
- [ ] **T-PR7-20`: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): caja + sesion + idempotency (4 tables + 50th [A])`. Add `type:feature` label.

### Acceptance
- `uv run alembic upgrade --sql head` shows `CREATE TABLE prod.idempotency_keys`, `REVOKE UPDATE, DELETE ON prod.idempotency_keys FROM rol_app`, `CREATE TRIGGER idempotency_keys_inmutable ...` in sequence (config.yaml rules.tasks).
- `uv run pytest backend/tests/migrations/test_idempotency_keys_inmutable.py -q` passes.
- `uv run pytest backend/tests/unit/test_idempotency_guard.py -q` passes (REQ-OP-04, SC-OP-02).
- `uv run pytest backend/tests/unit/test_idempotency_ttl.py -q` passes.
- `uv run pytest backend/tests/unit/test_session_cycle_open_close.py -q` passes (REQ-41, SC-42).
- `uv run pytest backend/tests/unit/test_session_cycle_login_failure_lockout.py -q` passes (REQ-OP-11, SC-41).
- `uv run pytest backend/tests/unit/test_session_cycle_logout.py -q` passes (REQ-45).
- `uv run pytest backend/tests/integration/test_crud_happy_path.py -q` passes (SC-40 full shift).
- `curl -X POST http://localhost:8000/api/v1/auth/login` without `Idempotency-Key` header → 400 `IdempotencyKeyRequiredError`.
- `curl -X POST http://localhost:8000/api/v1/auth/login` with key `abc123` twice (same body) → second call returns cached response with `Idempotent-Replay: true`.
- `psql -c "SELECT count(*) FROM pg_trigger WHERE tgname = 'idempotency_keys_inmutable'"` returns 1.
- `psql -c "SELECT has_table_privilege('rol_app', 'prod.idempotency_keys', 'UPDATE')"` returns `f`.

### Estimate
~600 LOC across ~13 files (3 model + 1 migration + 2 repo + 2 schema + 1 router + 1 factory hook + 7 tests).

---

## Total summary

| PR | Tasks | LOC | Files | Risk |
|---|---|---|---|---|
| PR0 | 8 | ~80 | 6 | LOW |
| PR1 | 19 | ~700 | 30 | MED |
| PR2 | 15 | ~700 | 17 | MED |
| PR3 | 9 | ~600 | 13 | LOW |
| PR4 | 12 | ~750 | 12 | MED |
| PR5 | 16 | ~800 | 14 | **HIGH** (apply-time split to 5a+5b) |
| PR6 | 22 | ~800 | 22 | **HIGH** (apply-time split to 6a+6b) |
| PR7 | 20 | ~600 | 13 | LOW |
| **Total** | **121** | **~5,030** | **~127** | |

## Risks surfaced

1. **PR5 + PR6 at 800-LOC edge** — pre-scoped conditional splits (PR5a/5b, PR6a/6b) in `proposal.md` §PR slicing. Apply triggers split if `git diff --stat` post-implementation > 800 LOC. No `size:exception` required.
2. **`tipo_arqueo` missing from bootstrap** — PR0 reconciles docs; PR3 ships the ORM model only if `preflight_table_counts.sh` exits 0 (verifies `\dt prod.*` includes `tipo_arqueo`). If not, PR3 is blocked until bootstrap backfills.
3. **`resolucion_facturacion`, `envio_dian`, `validacion_evento` missing from bootstrap** — same pre-flight gate covers these. PR4 (for `resolucion_facturacion`) and PR6 (for `envio_dian`, `validacion_evento`) MUST NOT merge until bootstrap ships them.
4. **50th table `idempotency_keys` not in bootstrap** — PR7 ships its own migration `0002_add_idempotency_keys.py` with REVOKE + trigger in the SAME script (per `config.yaml` rules.tasks).
5. **DIAN boundary** — three-layer defense: (a) `.dockerignore` excludes `**/dian/cloud/**` from branch image (bootstrap ships); (b) lazy `PARKOS_DEPLOY` import guard in `api/v1/__init__.py` (PR6 ships); (c) RED test `test_dian_boundary_branch.py` (PR6) + OpenAPI tag filter (PR6).
6. **Hash-chain break on partial sync** — `hash_chain.append()` reads prior `MAX(timestamp_evento)` per `uuid_sucursal` (PR2 ships). Cloud verifier is out of scope here (bootstrap PR5 owns).
7. **REVOKE/trigger drift** — bootstrap's entrypoint verifier covers it on every boot (PR0 + bootstrap).
8. **Pairing token replay** — single-use 24h TTL enforced in `auth/tokens.py` (PR4 ships the endpoint; token consumption handled by bootstrap's `entrypoint.sh`).
9. **Polymorphic FK validator performance** — Redis cache 60s TTL populated by sync worker (PR6 ships consumer; sync worker is bootstrap's responsibility).
10. **Subscription vehicle count race** — `pg_advisory_xact_lock(uuid_subscripcion_cliente)` in Pydantic validator (PR5 ships).

## Out of scope reminders (NOT deliverables of this change)

- DIAN HTTP transport (Factus adapter, `dian_dispatcher`) — bootstrap PR5 owns.
- Sync engine (`job_sync_cloud`, `job_sync_sucursal`, transport, ordering) — bootstrap PR5 owns.
- Web frontend (`web_admin`, `web_sucursal` PWA) — bootstrap PR6 owns.
- Operational tooling (rate limiting, OTel, Prometheus, circuit breakers) — separate change.
- RBAC permission matrix population (per-role assignment) — follow-up change; PR1 ships framework + canonical codes only.
- OpenAPI TS client SDK generator wiring (`apps/ui-kit/package.json`) — bootstrap PR6 owns.
- Bulk-CSV import endpoints — separate change per REQ-OP-06.
- `multipart/form-data` for `documentos` — base64 inline accepted in MVP per REQ-OP-05.
- WebSocket sync transport — deferred to v2.
- Hash chain verifier worker (`workers/hash_chain_verifier`) — bootstrap PR5 owns.
- TTL worker for `idempotency_keys` nightly cleanup — separate batch.
