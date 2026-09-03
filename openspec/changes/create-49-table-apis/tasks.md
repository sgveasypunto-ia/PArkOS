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
| Total estimated changed lines | ~7,500–8,500 across PR0–PR11 |
| Total tasks | ~190 across 12 PRs |
| 400-line budget risk | Medium (each PR averages ~650 LOC; PR5, PR6, PR9, PR11 sit at the 800 edge) |
| Chained PRs recommended | Yes — 12 chained PRs to `dev` |
| Suggested split | PR0 → PR1 → PR2 → PR3 → PR4 → PR5 (split at apply-time if >800) → PR6 (split at apply-time if >800) → PR7 → PR8 (split at apply-time if >800) → PR9 (split at apply-time if >800) → PR10 → PR11 (split at apply-time if >800) |
| Delivery strategy | `auto-chain` (cached) |
| Chain strategy | gitflow (feature branches off `dev`, PRs target `dev`, releases to `main` after cert) |
| Conditional splits pre-scoped | PR5a/5b, PR6a/6b, PR8a/8b, PR9a/9b, PR11a/11b (per `design.md` §21 PR slicing delta) |
| `size:exception` required? | **No** — every PR fits in 800 LOC after the conditional splits |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: chained PRs to `dev` in dependency order, each independently revertible (gitflow; `main` is production, `dev` is integration; releases via `release/vX.Y.Z` → `main` after cert)
400-line budget risk: Medium
§21 delta adds: PR8 (env+pairing+sync transport, ~750 LOC), PR9 (sync workers, ~800 LOC), PR10 (admin views+UI, ~600 LOC), PR11 (DIAN dispatcher, ~700 LOC); +2 `[A]` tables (pairing_tokens, revoked_sync_jwts); closes §19 OOS items (DIAN HTTP transport, sync engine implementation, pairing flow, hash chain verifier worker).

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
| PR8 | 2 ([A] pairing_tokens + revoked_sync_jwts, 51st + 52nd) | ~16 | ~750 | **HIGH** | **PR8a** (env + pairing flow + migration, ~400) + **PR8b** (sync transport endpoints + CLI + tests, ~350) |
| PR9 | 0 (orchestration + workers only) | ~14 | ~800 | **HIGH** | **PR9a** (runner + transport + conflict_resolver + jwt_manager, ~450) + **PR9b** (sync_sucursal + sync_cloud + auto_discovery, ~350) |
| PR10 | 0 (multi-sucursal admin views + UI) | ~12 | ~600 | MED | — |
| PR11 | 0 (DIAN dispatcher, cloud-only) | ~10 | ~700 | **HIGH** | **PR11a** (dispatcher + ubl_serializer + Factus provider, ~400) + **PR11b** (atomic_next_consecutivo + integration + Docker verify, ~300) |
| **Total** | **52** | **~158** | **~7,880** | | |

PR5 split trigger: `git diff --stat` post-implementation > 800 LOC → execute PR5a, then PR5b.
PR6 split trigger: same threshold → execute PR6a, then PR6b.
PR8 split trigger: same threshold → execute PR8a, then PR8b.
PR9 split trigger: same threshold → execute PR9a, then PR9b.
PR11 split trigger: same threshold → execute PR11a, then PR11b.

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
| PR8 | `uv run pytest backend/tests/{unit,integration,migrations}/test_{pairing*,sync_transport*,env_validator*,a_inmutable_p2} -q`; smoke `parkos-cli doctor` exit 0; static AST test for sync_router JWT guard | `uv sync --frozen` | `uv run alembic upgrade head` (creates 51st + 52nd tables); `uv run alembic upgrade --sql head` pre-flight; verify `has_table_privilege('rol_app', 'prod.pairing_tokens', 'UPDATE')` returns `f` |
| PR9 | `uv run pytest backend/tests/{unit,integration}/test_{sync_sucursal*,sync_cloud*,conflict_resolver*,jwt_manager*} -q`; mock `httpx.MockTransport` for all endpoints; `--config-test` dry-run smoke | `uv sync --frozen`; `docker build -f infra/docker/Dockerfile.cloud . --build-arg BUILD_TARGET=job_sync_cloud`; same for branch with `BUILD_TARGET=job_sync_sucursal` | testcontainers Postgres; docker image boot test (job_sync_cloud process stays alive > 5s under SIGTERM exits 0) |
| PR10 | `uv run pytest backend/tests/unit/test_{admin_views_scope,dashboard_aggregation,tenancy_admin} -q`; `npx playwright test apps/web_admin/src/components/branch-selector/` | none | testcontainers Postgres; refresh openapi artifact (admin scope filter); negative test: admin whose permitidas excludes X → X not in `/sucursales` response |
| PR11 | `uv run pytest backend/tests/dian/test_{dispatcher,ubl_serializer,factus_provider,boundary} -q`; `httpx.MockTransport` for 3 success + 3 rejection + 2 timeout paths | `uv sync --frozen`; verify `.dockerignore` excludes `**/dian/cloud/**` from branch image (build test in CI) | testcontainers Postgres + mock DIAN provider; verify `from parkos_core.dian.cloud.dispatcher import dispatch_factura_electronica` raises `ImportError` on branch image |

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

## PR8 — Env validator + Pairing flow + Sync transport endpoints

### Branch
`feat/create-49-table-apis-pr8-pairing-sync-api` (off `dev`)

### Dependencies
- PR7 merged to `dev` (uses `log_transaccional` for pairing audit trail + the `sync_queue` whitelisted-columns helpers from PR2).
- `parkos_core.runtime.env` introduced here is the NEW single source of truth for env validation (per `design.md` §21.2). It MUST coexist with bootstrap's existing `entrypoint.sh` env pre-flight — that one stays for the 49 schema tables and Alembic REVOKE/trigger verification; this validator focuses on runtime-required env (`PARKOS_SUCURSAL_UUID`, `PARKOS_DEPLOY`, `PARKOS_DB_URL`, `PARKOS_CLOUD_API_URL`, `PARKOS_SYNC_JWT_PATH`, `PARKOS_PAIRING_TOKEN`).
- DIAN boundary contract honored (REQ-X3, §10 Layer 1): this PR's `parkos_core/api/v1/sync_router.py` is mounted on BOTH `api_admin` and `api_sucursal` (REQ-OP-03). It does NOT mount `factura_electronica` / `revocacion_factura` routes — those stay in `dian/cloud_router.py` from PR6. Three-layer DIAN boundary (image-level `.dockerignore` + module-level import guard + OpenAPI tag filter) is fully verified by PR11 (here only the `sync_router` mount respects it).
- `[A]` canon (REQ-X5, §17 risk #4, `config.yaml rules.tasks`): the migration `0003_add_pairing_tokens_and_revoked_sync_jwts.py` ships BOTH tables + BOTH `REVOKE UPDATE, DELETE` statements + BOTH `BEFORE UPDATE OR DELETE` triggers in the SAME script. Verified by `alembic upgrade --sql head` pre-flight + migration tests.

### Work-unit commit boundaries
~22 commits. The env validator (T-PR8-01) lands FIRST as its own commit so every subsequent consumer can rely on it. The migration (T-PR8-05) is ONE commit (REVOKE + trigger inseparable per `config.yaml rules.tasks`). The pairing endpoints + sync endpoints + rate limiter + CLI + doctor subcommand are each their own commit. `repo/pairing.py` and `repo/revoked_sync_jwt.py` commit separately for review focus.

### Conditional split (apply-time trigger)
If `git diff --stat` post-implementation > 800 LOC → execute **PR8a** (T-PR8-01 through T-PR8-09 + T-PR8-19 + T-PR8-21, env validator + pairing flow + migration, ~400 LOC) + **PR8b** (T-PR8-10 through T-PR8-18 + T-PR8-20 + T-PR8-22, sync transport endpoints + CLI + tests, ~350 LOC). Split triggered at apply time per `chained-pr` skill + AGENTS.md review workflow.

### Tasks

- [ ] **T-PR8-01**: Create `parkos_core/runtime/__init__.py` + `parkos_core/runtime/env.py` — `MissingEnvError`, `load_config()`, `BranchConfig`, `CloudConfig`, `_require_uuid`, `_require_str`, `_require_path`, `_optional_int`. Validates `PARKOS_DEPLOY ∈ {cloud, branch}`, `PARKOS_SUCURSAL_UUID` is UUIDv4 on branch, `PARKOS_DB_URL`, `PARKOS_CLOUD_API_URL`, `PARKOS_JWT_KEY_PATH`, `PARKOS_SYNC_JWT_PATH` (branch), `PARKOS_DIAN_PROVIDER_URL` + `PARKOS_DIAN_PROVIDER_TOKEN_PATH` (cloud). Defaults for the 6 optional ints (`PARKOS_SYNC_POLL_INTERVAL_S=10`, `PARKOS_SYNC_BATCH_SIZE=100`, `PARKOS_SYNC_HEARTBEAT_S=60`, `PARKOS_DIAN_TIMEOUT_S=30`, `PARKOS_DIAN_RETRY_MAX=3`, `PARKOS_SYNC_VERIFY_INTERVAL_S=3600`). Exit code `2` on failure. Cites §21.2 (env validator).
- [ ] **T-PR8-02**: Wire `parkos_core.runtime.env` into `api_admin/src/main.py`, `api_sucursal/src/main.py`, `parkos_core/jobs/runner.py` (added in PR9) — first import on each entrypoint, fail-fast before any DB / network connection. Cites §21.2.
- [ ] **T-PR8-03**: Create `parkos_core/runtime/clock.py` — `server_now() -> datetime`, `clock_skew_seconds(branch_issued_at: datetime) -> int`, `ClockSkewError` (>60s skew raises). Used by `sync_router.py` to validate `issued_at_branch` JWT claim and by `sync_cloud.py` to detect branch clock drift. Cites §21.3 JWT specifics (`issued_at_branch` validation), §21.8 hash chain verifier ordering.
- [ ] **T-PR8-04**: Test `backend/tests/unit/test_env_validator.py` — 12 fixtures: (1) `PARKOS_DEPLOY` unset → `MissingEnvError`; (2) `PARKOS_DEPLOY=cloud` on branch → ok (CloudConfig); (3) `PARKOS_DEPLOY=branch` on cloud binary → `MissingEnvError` exit `2`; (4) `PARKOS_SUCURSAL_UUID` empty → `MissingEnvError`; (5) `PARKOS_SUCURSAL_UUID` malformed → `MissingEnvError`; (6) `PARKOS_SUCURSAL_UUID` is UUIDv3 (not v4) → `MissingEnvError`; (7) `PARKOS_DB_URL` unset on cloud → `MissingEnvError`; (8) `PARKOS_CLOUD_API_URL` unset on branch → `MissingEnvError`; (9) `PARKOS_SYNC_JWT_PATH` missing parent dir → `MissingEnvError`; (10) `PARKOS_DIAN_PROVIDER_URL` unset on cloud → `MissingEnvError`; (11) optional int malformed → falls back to default + warn; (12) `parkos_cli_doctor` happy path. Cites §21.2 acceptance criterion #21-23.
- [ ] **T-PR8-05**: Create `models/A/pairing_tokens.py` + `models/A/revoked_sync_jwts.py` — 2 new `[A]` tables (51st + 52nd overall, beyond the 49-table baseline). Both subclass `AppendOnlyBase`. `pairing_tokens` carries `pairing_token_hash text NOT NULL` (plaintext NEVER persisted), `expires_at`, `used`, `used_at`, `used_by_branch_info jsonb`, `revoked_at`, `revoked_by uuid`, FK to `prod.sucursal(uuid)`. `revoked_sync_jwts` carries `jwt_kid text NOT NULL`, `jwt_uuid text NOT NULL` (jti), `expires_at`, `revoked_by uuid`, `motivo text`, `UNIQUE (jwt_kid, jwt_uuid)`. Both carry `sync_status`, `sync_timestamp`, `sync_attempts` per `SyncMixin`. Cites §21.3 (cloud side tables), REQ-X5 (audit-first canon for `[A]` tables).
- [ ] **T-PR8-06**: Migration `backend/packages/parkos_core/migrations/versions/0003_add_pairing_tokens_and_revoked_sync_jwts.py` — creates BOTH `prod.pairing_tokens` + `prod.revoked_sync_jwts` + 2 partial indexes (one for pending pairing, one for active revocations) + `REVOKE UPDATE, DELETE ON prod.pairing_tokens FROM rol_app` + `REVOKE UPDATE, DELETE ON prod.revoked_sync_jwts FROM rol_app` + `CREATE OR REPLACE FUNCTION prod.fn_pairing_tokens_inmutable() / prod.fn_revoked_sync_jwts_inmutable()` + 2 `BEFORE UPDATE OR DELETE` triggers — ALL in the SAME migration script per `config.yaml rules.tasks` + AGENTS.md risk register row #4. Cites §21.3 (cloud side tables DDL), REQ-X5, `config.yaml rules.tasks`.
- [ ] **T-PR8-07**: Migration pre-flight — `uv run alembic upgrade --sql head` and visually inspect the output: `CREATE TABLE prod.pairing_tokens`, `CREATE TABLE prod.revoked_sync_jwts`, both `REVOKE UPDATE, DELETE ... FROM rol_app`, both `CREATE OR REPLACE FUNCTION prod.fn_*_inmutable()`, both `CREATE TRIGGER *_no_update_delete`. Verify the sequence (per `config.yaml rules.tasks`). Run `alembic upgrade head` against testcontainers Postgres. Cites §21.14 acceptance criterion #2.
- [ ] **T-PR8-08**: Create `schemas/pairing.py` — Pydantic v2 `Read`/`Create`/`Update`/`Filter`/`ReadList` for `pairing_tokens`. `Create` excludes `pairing_token_hash` (server-computed). `Update` for `[A]` tables is read-only (no Update model — closed by `[A]` canon). Cites §21.3 (token shape), REQ-OP-13 (RBAC), `schemas/common.py` `_Base` from PR1.
- [ ] **T-PR8-09**: Create `schemas/revoked_sync_jwt.py` — Pydantic v2 `Read` only (no Create/Update — `[A]` canon). Cites §21.3 (revocation entries are INSERT-only).
- [ ] **T-PR8-10**: Create `repo/pairing.py` — `generate_pairing_token() -> (plaintext, hash)`, `create_pairing_token(session, *, uuid_sucursal, ttl_hours=24, actor_uuid) -> PairingTokenRead`, `consume_pairing_token(session, plaintext: str, *, uuid_sucursal, branch_info) -> PairingTokenRead` (atomic via `SELECT ... FOR UPDATE SKIP LOCKED` per §21.3 "Consume atomicity"), `revoke_pairing_token(session, *, uuid, actor_uuid) -> None` (writes the `revoked_at` + `revoked_by` columns; the row remains `[A]` so UPDATE is the canonical mutation here, per AGENTS.md "sync_queue is `[A]` with operational UPDATE exception" extended to revocation fields). Cites §21.3 (token shape + consume atomicity), §21.14 acceptance criterion #1.
- [ ] **T-PR8-11**: Create `repo/revoked_sync_jwt.py` — `revoke_jwt(session, *, kid, jwt_uuid, motivo, actor_uuid, expires_at) -> None` (INSERT into `prod.revoked_sync_jwts`), `is_revoked(session, kid, jwt_uuid) -> bool` (used by `sync_router.py` middleware to reject 401). The check is `SELECT 1 FROM prod.revoked_sync_jwts WHERE jwt_kid = :k AND jwt_uuid = :j AND expires_at > NOW()`. Cites §21.3 (revocation), §21.10 (`/sync/push` 401 sync_jwt_revoked path).
- [ ] **T-PR8-12**: Create `parkos_core/api/v1/pairing.py` — mounts 4 admin endpoints: (a) `POST /api/v1/admin/pairing-tokens` (issuer `admin-`, `require_permission("gestionar_dian")`); (b) `GET /api/v1/admin/pairing-tokens/{pairing_token_uuid}` (issuer `admin-`, returns `PairingTokenRead` minus `pairing_token_hash`); (c) `DELETE /api/v1/admin/pairing-tokens/{pairing_token_uuid}` (issuer `admin-`, `require_permission("gestionar_dian")`, sets `revoked_at` + `revoked_by`, returns 204); (d) `POST /api/v1/admin/sucursales/{uuid_sucursal}/revoke-sync` (issuer `admin-`, `require_permission("gestionar_dian")`, inserts into `revoked_sync_jwts`, returns 204). Cites §21.3 (cloud-side endpoints table), REQ-X3 (cloud-only via `PARKOS_DEPLOY=cloud` import guard).
- [ ] **T-PR8-13**: Create `parkos_core/api/rate_limit_pairing.py` — token-bucket rate limiter for `POST /api/v1/admin/pairing-tokens`: 5 tokens/hour per `admin_uuid`. In-memory (no Redis dependency on cloud); clock-driven reset. On 6th request in 60 min → 429 `{"error":"pairing_token_rate_limited","detail":"5/hour"}`. Cites §21.3 (Rate limit), §21.14 acceptance criterion #1 (`test_pair_token_rate_limit`).
- [ ] **T-PR8-14**: Create `parkos_core/api/v1/sync_router.py` — mounts 6 sync endpoints per §21.9: (a) `POST /api/v1/sync/pair` (NO auth, single-use token + 24h TTL guard); (b) `POST /api/v1/sync/push` (issuer `sync-agent-`); (c) `POST /api/v1/sync/pull` (issuer `sync-agent-`); (d) `POST /api/v1/sync/heartbeat` (issuer `sync-agent-`); (e) `POST /api/v1/sync/rotate-jwt` (issuer `sync-agent-`, current JWT); (f) `POST /api/v1/sync/events` (issuer `sync-agent-`, cloud → branch push). Mounts BOTH on `api_admin` (cloud-side receiver) AND `api_sucursal` (branch-side receiver) per REQ-OP-03. Cites §21.9 (transport protocol), REQ-OP-03 (mounted on both services).
- [ ] **T-PR8-15**: Create `parkos_core/sync/transport.py` (helpers for sync_router): `SyncIdempotencyCache(maxsize=10_000, ttl=300)` — process-local LRU keyed by `X-Request-Id`, returns cached `(status, body)` on replay within 5 min with `Idempotent-Replay: true` header; `RateLimit(per_(issuer, subject): TokenBucket)` — default `60 req/min` for push, `120 req/min` for pull, `10 req/min` for heartbeat, `1 req/min` for rotate-jwt; 429 includes `Retry-After: <seconds>`. Cites §21.9 (Idempotency + Rate limits), §21.14 acceptance criterion #15-16.
- [ ] **T-PR8-16**: Wire `sync_router` mount in `api/v1/__init__.py` — eager (no `PARKOS_DEPLOY` guard, mounts on BOTH `api_admin` and `api_sucursal`). Document in module docstring: `/sync/*` paths are NOT cloud-only; they're the only `api_sucursal`-mounted paths besides the CRUD routers. Cites REQ-OP-03, REQ-X8.
- [ ] **T-PR8-17**: Create `parkos_core/cli/pair.py` — entrypoint `python -m parkos_core.cli pair`. Detects `PARKOS_PAIRING_TOKEN` in env; on first boot: calls `POST {PARKOS_CLOUD_API_URL}/api/v1/sync/pair` with `{pairing_token, uuid_sucursal, branch_info: {hostname, os, version, endpoint_url}}`; on 200: writes the returned JWT to `PARKOS_SYNC_JWT_PATH` with `os.open(mode=0o600, ...)` (chmod enforced); deletes `PARKOS_PAIRING_TOKEN` from in-process `os.environ` (does NOT touch orchestrator env); writes `log_transaccional` row with `accion='pair_completed'`; exits 0. Subsequent boots (no `PARKOS_PAIRING_TOKEN`): exits 0 silently. Cites §21.3 (branch-side one-shot CLI), §21.14 acceptance criterion #1 (`test_pair_happy_path`).
- [ ] **T-PR8-18**: Create `parkos_core/cli/doctor.py` — `python -m parkos_core.cli doctor` prints structured report `{env_status: "ok"|"missing:<var>", db_connectivity: "ok"|"error:<msg>", jwt_key_path_exists: bool, sync_jwt_path_readable: bool, cloud_api_url_reachable: "ok"|"error:<code>"}` as a JSON object to stdout; exits 0 on all-ok, 1 on any error. Cites §21.12 risk #23 (per-branch misconfiguration diagnostic).
- [ ] **T-PR8-19**: Test `backend/tests/unit/test_pairing_repo.py` — `generate_pairing_token` produces 32-byte base64url; `create_pairing_token` writes sha256 hash only (NEVER plaintext); `consume_pairing_token` happy path; race scenario (two `AsyncSession`s consume simultaneously): second `SELECT FOR UPDATE SKIP LOCKED` returns None → `PairingTokenConsumedError` (mapped to 410). Cites §21.3 (Consume atomicity).
- [ ] **T-PR8-20**: Test `backend/tests/unit/test_pairing_endpoints.py` — 4 endpoints: `POST /admin/pairing-tokens` happy path returns plaintext ONCE + sha256 in DB; `GET /admin/pairing-tokens/{uuid}` does NOT return plaintext; `DELETE /admin/pairing-tokens/{uuid}` sets `revoked_at` and subsequent `consume` returns 410; `POST /admin/sucursales/{uuid}/revoke-sync` writes `revoked_sync_jwts` row + next `/sync/push` with that JWT returns 401. Cites §21.3, §21.14 acceptance #1.
- [ ] **T-PR8-21**: Test `backend/tests/integration/test_pairing_flow.py` — all 9 tests per §21.3 / §21.14: `test_pair_happy_path`, `test_pair_token_reuse_rejected`, `test_pair_token_expired_rejected`, `test_pair_token_revoked_rejected`, `test_pair_revoked_jwt_rejects_subsequent_calls`, `test_pair_wrong_sucursal_rejected`, `test_pair_env_validator_fails_fast`, `test_pair_persisted_jwt_path_0600`, `test_pair_token_rate_limit`. Cites §21.14 acceptance criterion #1.
- [ ] **T-PR8-22**: Test `backend/tests/unit/test_sync_transport.py` — `SyncIdempotencyCache` returns cached response with `Idempotent-Replay: true` header on replay within 5 min; `RateLimit` enforces 60 req/min for push (61st request → 429 with `Retry-After`); `X-Request-Id` replay returns cached response (server-server scenario). Cites §21.9 (Idempotency + Rate limits), §21.14 acceptance criterion #15-16.
- [ ] **T-PR8-23**: Test `backend/tests/migrations/test_pairing_tokens_inmutable.py` — INSERT succeeds; UPDATE raises `PAIRING_TOKENS_INMUTABLE`; DELETE raises same. Same for `revoked_sync_jwts`. `has_table_privilege('rol_app', 'prod.pairing_tokens', 'UPDATE')` returns `f`; `pg_trigger WHERE tgname = 'pairing_tokens_no_update_delete'` returns 1; same for `revoked_sync_jwts`. Cites §21.14 acceptance criterion #3, REQ-X5, AGENTS.md `config.yaml rules.tasks`.
- [ ] **T-PR8-24**: Update `AGENTS.md` Risk Register — close risk #8 "Pairing-token replay" with mitigation `parkos_core/cli/pair.py + repo/pairing.py` per §21.3. Add risk #19 "Pairing-token theft in transit" (HIGH) per §21.12. Add risk #23 "Per-branch misconfig of `PARKOS_SUCURSAL_UUID`" (MED) per §21.12. Cites §21.3, §21.12, AGENTS.md Risk Register convention.
- [ ] **T-PR8-25**: Refresh both OpenAPI artifacts via `uv run python -m parkos_core.openapi --deploy {cloud,branch}`. Verify the new `/admin/pairing-tokens*` + `/admin/sucursales/*/revoke-sync` paths are present in `api_admin/openapi.json` and ABSENT in `api_sucursal/openapi.json`. Verify the 6 `/sync/*` paths are present in BOTH `api_admin/openapi.json` AND `api_sucursal/openapi.json` (REQ-OP-03 boundary). Cites §21.14 acceptance criterion #20 (unchanged from §16 / §10).
- [ ] **T-PR8-26**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): env validator + pairing + sync transport (2 [A] tables + 8 endpoints)`. PR body includes: chain context (📍 PR8 of 12), migration file path, token shape reference, `parkos-cli pair` snippet, link to §21.3 of `design.md`. Add `type:feature` label. Cites AGENTS.md gitflow + `branch-pr` skill.

### Acceptance
- `uv run alembic upgrade --sql head` shows `CREATE TABLE prod.pairing_tokens`, `CREATE TABLE prod.revoked_sync_jwts`, both `REVOKE UPDATE, DELETE ... FROM rol_app`, both `CREATE OR REPLACE FUNCTION prod.fn_*_inmutable()`, both `CREATE TRIGGER *_no_update_delete` in the correct sequence (`config.yaml rules.tasks`).
- `uv run alembic upgrade head` against testcontainers Postgres exits 0; running twice produces no diff (idempotency).
- `uv run pytest backend/tests/migrations/test_pairing_tokens_inmutable.py -q` passes.
- `uv run pytest backend/tests/unit/test_env_validator.py -q` passes (12 fixtures).
- `uv run pytest backend/tests/unit/test_pairing_repo.py -q` passes (race condition verified).
- `uv run pytest backend/tests/unit/test_pairing_endpoints.py -q` passes.
- `uv run pytest backend/tests/integration/test_pairing_flow.py -q` passes (9 tests).
- `uv run pytest backend/tests/unit/test_sync_transport.py -q` passes (idempotency + rate limit).
- `uv run pytest backend/tests/static/test_no_raw_dml_on_a_tables.py -q` passes (extended to cover `pairing_tokens` + `revoked_sync_jwts`).
- `psql -c "SELECT has_table_privilege('rol_app', 'prod.pairing_tokens', 'UPDATE')"` returns `f`; same for `revoked_sync_jwts`.
- `psql -c "SELECT count(*) FROM pg_trigger WHERE tgname = 'pairing_tokens_no_update_delete'"` returns 1; same for `revoked_sync_jwts_no_update_delete`.
- `parkos-cli doctor` prints the structured JSON report `{env_status, db_connectivity, jwt_key_path_exists, sync_jwt_path_readable, cloud_api_url_reachable}` and exits 0 on healthy env.
- `curl -X POST http://localhost:8000/api/v1/admin/pairing-tokens -H "Authorization: Bearer $ADMIN_JWT"` returns the plaintext ONCE + sets `pairing_tokens` row with sha256 hash (plaintext NOT persisted).
- `curl -X DELETE http://localhost:8000/api/v1/admin/pairing-tokens/{uuid} -H "Authorization: Bearer $ADMIN_JWT"` returns 204; subsequent `POST /api/v1/sync/pair` with the same plaintext returns 410.
- `curl -X POST http://localhost:8000/api/v1/admin/pairing-tokens ... ` 6 times in 60 min → 6th request returns 429 `pairing_token_rate_limited`.
- `jq '.paths | keys | map(select(test("/admin/pairing-tokens|/admin/sucursales/.+/revoke-sync"))) | length' backend/packages/api_admin/openapi.json` returns ≥ 3.
- `jq '.paths | keys | map(select(test("/admin/pairing-tokens|/admin/sucursales/.+/revoke-sync"))) | length' backend/packages/api_sucursal/openapi.json` returns 0.
- `jq '.paths | keys | map(select(test("/sync/pair|/sync/push|/sync/pull|/sync/heartbeat|/sync/rotate-jwt|/sync/events"))) | length' backend/packages/api_admin/openapi.json` returns 6.
- `jq '.paths | keys | map(select(test("/sync/pair|/sync/push|/sync/pull|/sync/heartbeat|/sync/rotate-jwt|/sync/events"))) | length' backend/packages/api_sucursal/openapi.json` returns 6 (REQ-OP-03).
- Boot branch image with empty `PARKOS_SUCURSAL_UUID` → exit code `2`, stderr message includes `PARKOS_SUCURSAL_UUID`.
- After successful pair, `os.stat(PARKOS_SYNC_JWT_PATH).st_mode & 0o777 == 0o600` (Unix permission bit check; CI runs in container).

### Estimate
~750 LOC across ~16 files (2 model + 1 migration + 1 env validator + 1 clock + 2 schema + 2 repo + 4 API/router + 1 rate limiter + 1 sync_router + 2 CLI + 6 tests). **Apply-time split trigger: > 800 LOC → PR8a (env + pairing flow + migration) + PR8b (sync transport endpoints + CLI + tests).**

---

## PR9 — Sync workers (`job_sync_sucursal` + `job_sync_cloud`) + conflict resolver + JWT auto-rotation

### Branch
`feat/create-49-table-apis-pr9-sync-workers` (off `dev`)

### Dependencies
- PR8 merged to `dev` (consumes `parkos_core/runtime/env.py`, `parkos_core/cli/pair.py`, the `sync_router` endpoints from §21.9, and the `revoked_sync_jwts` table for the JWT auto-rotation check).
- PR7 merged to `dev` (workers depend on `repo/append_only.py::mark_dispatched / mark_failed / schedule_retry` from PR2; uses `repo/versioned.close_and_insert` for replicated `[V]` rows; uses `repo/hash_chain.append` for `log_transaccional` + `revocacion_factura` chain extension).
- DIAN boundary honored (REQ-X3, §10 Layer 1): the `job_sync_*` workers are NOT mounted on branch API images — they're separate processes invoked via `python -m parkos_core.jobs.sync_*` (per `~/.config/opencode/skills/docker/SKILL.md` step 1). Cloud `job_sync_cloud` writes DIAN cloud-only rows (`factura_electronica`, `envio_dian`); branch `job_sync_sucursal` writes only replicated rows from `sync_queue`. No cross-boundary data flow.

### Work-unit commit boundaries
~18 commits. The generic `runner.py` (T-PR9-01) is its own commit so consumers (`sync_sucursal`, `sync_cloud`) can reuse it cleanly. Each sync worker's main body is its own commit; the conflict resolver and JWT manager commit separately for review focus. The `auto_discovery.py` module commits with the cloud-side verifier (T-PR9-10 + T-PR9-07 are co-dependent).

### Conditional split (apply-time trigger)
If `git diff --stat` post-implementation > 800 LOC → execute **PR9a** (T-PR9-01 + T-PR9-07 + T-PR9-08 + T-PR9-09, generic runner + transport + conflict resolver + JWT manager helpers, ~450 LOC) + **PR9b** (T-PR9-02 through T-PR9-06 + T-PR9-10 + T-PR9-11 through T-PR9-17 + T-PR9-18, `sync_sucursal` + `sync_cloud` + auto-discovery + tests, ~350 LOC). Per `chained-pr` skill.

### Tasks

- [ ] **T-PR9-01**: Create `parkos_core/jobs/__init__.py` + `parkos_core/jobs/runner.py` — generic supervisor: `class WorkerRunner(BaseRunner)` with `run() -> int` (0 = clean shutdown, 1 = unhandled error, 2 = misconfig — matches §21.7 exit codes); SIGTERM handler for graceful shutdown (in-flight cycle finishes, then exit 0); SIGINT same; structured logging via `structlog`; `BACKOFF_4XX = [60, 300, 1800, 7200, 43200, 86400]` and `BACKOFF_5XX = [30, 60, 300]` constants. Cites §21.7 (exit codes), §21.8 (same), `~/.config/opencode/skills/docker/SKILL.md` step 7.
- [ ] **T-PR9-02**: Create `parkos_core/sync/transport.py` (HTTP client helpers — separate from PR8's transport helpers) — `class SyncHttpClient(session_factory, base_url: str, jwt_path: Path)` with `async push(rows) -> PushResponse`, `async pull(since_seq) -> PullResponse`, `async heartbeat(state) -> None`, `async rotate_jwt() -> NewJwt`. Reads the JWT from `PARKOS_SYNC_JWT_PATH` lazily; uses `httpx.AsyncClient` with `timeout=30.0` and `limits=httpx.Limits(max_connections=10)`. Cites §21.7 (push/pull/heartbeat/rotate-jwt), §21.8 (same on cloud side, inverted).
- [ ] **T-PR9-03**: Create `parkos_core/sync/conflict_resolver.py` — `class ConflictResolver` with `apply_pushed_row(session, row: PushedRow) -> ApplyOutcome` where `ApplyOutcome ∈ {APPLIED, CONFLICT_V, CONFLICT_LS, ERROR}`. Implementation per §21.10: `[V]` cloud-wins (writes `sync_conflict` if branch row loses); `[L-E]`/`[L-W]`/`[A]` append-only (no conflict possible); `[L-S]` grace-window (`JWT_OVERLAP_HOURS = 24h`) before cloud-wins. Per-row monotonic `seq` in `datos->>'seq'` verified before apply; mismatch → return `ERROR` (caller retries). Cites §21.10, REQ-X9 (chain tie-break).
- [ ] **T-PR9-04**: Create `parkos_core/sync/jwt_manager.py` — `class JwtManager(jwt_path: Path)` with `async get_current_jwt() -> str`, `async rotate() -> NewJwt` (calls `POST /sync/rotate-jwt`, writes new JWT to `jwt_path` mode `0600`, keeps old JWT valid until `grace_until`). `async on_401_response(response) -> Action` where `Action ∈ {RETRY_NEW_JWT, HALT_REVOKED, HALT_EXPIRED}`. On `401 sync_jwt_revoked`: emit local `alerta tipo_alerta='branch_offline_reauth_required'`, call `sys.exit(1)` so orchestrator restart-loop surfaces the issue (per §21.7). Cites §21.3 (JWT specifics), §21.7 (401 handling), §21.9 (`/sync/rotate-jwt`).
- [ ] **T-PR9-05**: Create `parkos_core/sync/auto_discovery.py` — `async discover_active_branches(session) -> list[BranchEndpoint]` (queries `prod.sucursal WHERE uuid IN (SELECT DISTINCT uuid_sucursal FROM prod.sync_log WHERE created_at > NOW() - INTERVAL '7 days' UNION SELECT DISTINCT uuid_sucursal FROM prod.pairing_tokens WHERE used = true AND used_at > NOW() - INTERVAL '30 days')`), in-memory cache refreshed every `PARKOS_SYNC_VERIFY_INTERVAL_S / 12` (default 5 min). Optional external registry via `PARKOS_REGISTRY_URL` (deferred; default = DB only per §21.5). Cites §21.5 (Auto-discovery).
- [ ] **T-PR9-06**: Create `parkos_core/jobs/sync_sucursal.py` — `class SyncSucursalWorker(WorkerRunner)` with main loop per §21.7 diagram: (1) `poll_sync_queue()` via `repo/append_only.poll_pending()` (whitelisted-columns UPDATE for `mark_dispatched`/`mark_failed`); (2) `push_batch(rows)` via `SyncHttpClient.push`; (3) `handle_response()` (2xx mark_dispatched, 207 partial, 4xx mark_failed + backoff_4xx, 5xx mark_failed + backoff_5xx, 401 → `JwtManager.on_401_response`); (4) `pull_cloud_changes()` via `SyncHttpClient.pull` → `ConflictResolver.apply_pushed_row` per row → `repo/{versioned,append_only,event,workflow,session_cycle}` based on `row.tabla`; (5) `heartbeat()` via `SyncHttpClient.heartbeat`; (6) `sleep(PARKOS_SYNC_POLL_INTERVAL_S - elapsed)`. Cites §21.7 (job_sync_sucursal full flow).
- [ ] **T-PR9-07**: Create `parkos_core/jobs/sync_cloud.py` — `class SyncCloudWorker(WorkerRunner)` with 3 loops per §21.8: (1) `apply_pushed_row()` per incoming push (verified in api_admin `/sync/push` handler — cloud worker maintains side-effects: `sync_log` row per branch per cycle, `sync_conflict` on chain violation, `alerta` chain root); (2) `emit_sync_back_events()` for cloud-originated rows (`factura_electronica` ack, admin updates, catalog refreshes) → `POST {branch_endpoint_url}/api/v1/sync/events` with retry 3x exponential on 5xx; (3) `hash_chain_verifier_loop()` every `PARKOS_SYNC_VERIFY_INTERVAL_S` (default 3600s): walks `log_transaccional` per `uuid_sucursal` in `(timestamp_evento, uuid)` order, asserts `hash_anterior = prev.hash_actual` (or genesis), asserts `hash_actual = sha256(canonical_json(payload) + hash_anterior_bytes)`, on mismatch writes `alerta tipo_alerta='hash_chain_anomaly'` + `sync_conflict`. Cites §21.8 (job_sync_cloud full flow), §21.14 acceptance #14.
- [ ] **T-PR9-08**: Add `Dockerfile.cloud` entrypoint for `job_sync_cloud` — multi-stage `Dockerfile` with `BUILD_TARGET=job_sync_cloud` build-arg (per `~/.config/opencode/skills/docker/SKILL.md` step 2 Pattern A); `SERVICE_NAME=job_sync_cloud` runtime env var; `HEALTHCHECK CMD python -c "import httpx; httpx.get('http://localhost:9999/healthz').raise_for_status()"` (workers expose tiny `httpx`-served `/healthz` for orchestration on port 9999, NOT exposed externally). `deploy.replicas: 1` enforced (single-instance design per §21.12 risk #24). Cites §21.6 (installability), §21.12 risk #24.
- [ ] **T-PR9-09**: Add `Dockerfile.branch` entrypoint for `job_sync_sucursal` — same multi-stage pattern, `BUILD_TARGET=job_sync_sucursal` build-arg, `SERVICE_NAME=job_sync_sucursal` runtime env var, same `/healthz` healthcheck. `deploy.replicas: 1` per branch (paired with `api_sucursal`). Cites §21.6, §21.7.
- [ ] **T-PR9-10**: Add `infra/deploy/docker-compose.{cloud,branch}.yml` — update existing bootstrap compose files to include `job_sync_cloud` / `job_sync_sucursal` services with `depends_on.condition: service_healthy` on the DB + API. Cites §21.6 (installability matrix), `~/.config/opencode/skills/docker/SKILL.md` step 11 (HEALTHCHECK orchestration).
- [ ] **T-PR9-11**: Test `backend/tests/unit/test_sync_sucursal_poll_batch.py` — happy path: insert 3 rows in `prod.sync_queue` (estado='pendiente'), boot worker for 1 cycle, verify all 3 marked 'despachado' via `mark_dispatched`. Cites §21.7 (poll_batch).
- [ ] **T-PR9-12**: Test `backend/tests/unit/test_sync_sucursal_401_rotate.py` — mock `SyncHttpClient.push` to return 401 with `{"error":"sync_jwt_expired"}`; worker calls `JwtManager.rotate` which mocks `POST /sync/rotate-jwt` returning a new JWT; worker retries the push; succeeds. Cites §21.7 (401 sync_jwt_expired → rotate-jwt flow), §21.14 acceptance #12.
- [ ] **T-PR9-13**: Test `backend/tests/unit/test_sync_sucursal_401_halt.py` — mock 401 with `{"error":"sync_jwt_revoked"}`; worker emits local `alerta tipo_alerta='branch_offline_reauth_required'`; worker exits 1 (orchestrator restarts, keeps failing until re-pair). Cites §21.7 (401 sync_jwt_revoked → HALT_REVOKED), §21.14 acceptance #13.
- [ ] **T-PR9-14**: Test `backend/tests/unit/test_sync_sucursal_5xx_backoff.py` — mock 503; worker calls `mark_failed` + `schedule_retry` with `backoff_5xx[0]=30s`; second cycle retries at +30s. Cites §21.7 (5xx backoff).
- [ ] **T-PR9-15**: Test `backend/tests/unit/test_sync_cloud_apply_row.py` — branch pushes `[V]` row; cloud applies via `repo/versioned.close_and_insert`; for `log_transaccional` verifies `hash_anterior = prior row's hash_actual`. Cites §21.8 step 2, REQ-X4 (hash chain integrity).
- [ ] **T-PR9-16**: Test `backend/tests/unit/test_sync_cloud_verifier_catches_break.py` — insert a `log_transaccional` row with `hash_actual` mismatched to `sha256(canonical_json + hash_anterior)`; cloud verifier loop runs (mock the loop trigger); asserts `alerta tipo_alerta='hash_chain_anomaly'` + `sync_conflict` rows written. Cites §21.8 step 5, §21.14 acceptance #14.
- [ ] **T-PR9-17**: Test `backend/tests/integration/test_sync_conflict_resolution.py` — 3 tests per §21.10: `test_v_conflict_writes_sync_conflict_row` (cloud-wins for `[V]`, branch losing row in `sync_conflict`), `test_ls_grace_window_` (two simultaneous `close_session_with_log` calls, one applied, one held in `sync_conflict` until grace window), `test_append_no_conflict_possible` (`[A]` row conflict impossible). Cites §21.10, §21.14 acceptance #17.
- [ ] **T-PR9-18**: Docker build verification — `docker build -f infra/docker/Dockerfile.cloud . --build-arg BUILD_TARGET=job_sync_cloud -t parkos:job-sync-cloud-test` exits 0; `docker run --rm parkos:job-sync-cloud-test python -m parkos_core.jobs.sync_cloud --config-test` exits 0; same for branch with `--build-arg BUILD_TARGET=job_sync_sucursal`. Cites §21.6, §21.14 acceptance #10.
- [ ] **T-PR9-19**: Update `AGENTS.md` Risk Register — add risk #20 "Stale branch registry" (HIGH), #21 "job_sync_sucursal silent death" (MED), #22 "Out-of-order sync arrivals" (MED), #24 "Two parallel job_sync_cloud instances race on hash chain" (MED) per §21.12. Cites §21.12.
- [ ] **T-PR9-20**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): sync workers + conflict resolver + JWT auto-rotation`. PR body includes: chain context (📍 PR9 of 12), worker main-loop ASCII art (from §21.7 / §21.8), link to §21.7-§21.10 of `design.md`. Add `type:feature` label. Cites AGENTS.md gitflow + `branch-pr` skill.

### Acceptance
- `uv run pytest backend/tests/unit/test_sync_sucursal_{poll_batch,401_rotate,401_halt,5xx_backoff}.py -q` all pass.
- `uv run pytest backend/tests/unit/test_sync_cloud_{apply_row,verifier_catches_break}.py -q` passes.
- `uv run pytest backend/tests/integration/test_sync_conflict_resolution.py -q` passes (3 tests).
- `python -m parkos_core.jobs.sync_sucursal --config-test` (dry-run: loads env, prints config, exits 0) succeeds.
- `python -m parkos_core.jobs.sync_sucursal --check-db` succeeds (verifies DB connectivity + JWT key path readable + sync_jwt path readable if present).
- `python -m parkos_core.jobs.sync_cloud --config-test` succeeds; `--check-db` succeeds.
- `docker build -f infra/docker/Dockerfile.cloud . --build-arg BUILD_TARGET=job_sync_cloud` exits 0.
- `docker run --rm parkos:job-sync-cloud-test python -m parkos_core.jobs.sync_cloud --config-test` exits 0; same for branch with `--build-arg BUILD_TARGET=job_sync_sucursal`.
- End-to-end smoke (manual or in CI): pair a branch (via PR8's `parkos-cli pair`) → boot `job_sync_sucursal` → INSERT into `prod.factura_pagos` on branch → wait one poll cycle → verify cloud has the row via `GET /api/v1/admin/sucursales/{uuid}/dashboard` or direct SQL. Cites §21.14 acceptance #11.
- `POST /sync/push` with expired JWT (mocked) → worker calls `POST /sync/rotate-jwt`, gets new JWT, persists, retries — no operator action. Cites §21.14 acceptance #12.
- `POST /sync/push` with revoked JWT (mocked) → worker emits alerta, halts (exit 1). Cites §21.14 acceptance #13.
- Cloud `job_sync_cloud` hash chain verifier catches a deliberately-broken row (test fixture inserts mismatched `hash_actual`); emits alerta + `sync_conflict`. Cites §21.14 acceptance #14.
- `docker compose -f infra/deploy/docker-compose.cloud.yml config` validates without errors; same for `branch.yml` (with `job_sync_*` service included). Cites §21.14 acceptance #9.
- `jq '.paths | keys | map(select(test("/sync/pair|/sync/push|/sync/pull|/sync/heartbeat|/sync/rotate-jwt|/sync/events"))) | length' backend/packages/api_admin/openapi.json` returns 6 (mounted by PR8; PR9 adds no new routes).
- `uv run ruff check backend/packages/parkos_core/jobs/ backend/packages/parkos_core/sync/` passes.

### Estimate
~800 LOC across ~14 files (1 runner + 4 sync helpers + 2 worker bodies + 2 docker entrypoints + 1 compose update + 1 AGENTS.md + 7 tests). **Apply-time split trigger: > 800 LOC → PR9a (runner + transport + conflict_resolver + jwt_manager) + PR9b (sync_sucursal + sync_cloud + auto_discovery + tests + Docker).**

---

## PR10 — Multi-sucursal admin views + branch-selector UI

### Branch
`feat/create-49-table-apis-pr10-admin-views` (off `dev`)

### Dependencies
- PR8 merged to `dev` (consumes `revoked_sync_jwts` writes from `/admin/sucursales/{uuid}/revoke-sync` endpoint for the dashboard's `sync_health` field).
- PR9 merged to `dev` (`sync_log` rows from `job_sync_cloud` feed the dashboard's `last_sync_at` + `queue_depth`; `job_sync_sucursal` writes `sync_log` rows per cycle).
- AGENTS.md gitflow canon (REQ-X2): admin endpoints MUST be cloud-only. Mounted in `api_admin` via `PARKOS_DEPLOY=cloud` import guard (PR6 pattern); branch image raises `ImportError("admin_views_unavailable_on_branch")` if attempted.

### Work-unit commit boundaries
~14 commits. The ORM listener extension (T-PR10-04) is its own commit (defense in depth artifact). The 3 API endpoints commit separately for review focus. The 4 UI sub-tasks (BranchSelector + localStorage + context switcher + SWR mutate) commit together as one work unit per `work-unit-commits` SKILL.md (UI behavior is the unit).

### Tasks

- [ ] **T-PR10-01**: API endpoint `GET /api/v1/sucursales` — issuer `admin-`, returns `{items: [{uuid, nombre, ciudad, uuid_tipo_sucursal, sync_status: {last_sync_at, last_error, last_heartbeat_at}, open_alerts_count, last_pairing_at}], next_cursor}`. Filtered to `uuid IN (claims.sucursales_permitidas)` via the ORM listener (T-PR10-04). Cursor pagination (REQ-OP-01): opaque base64 `{vigente_desde, uuid, resource}`; `limit` 1..200. Cites §21.4 (admin views), REQ-X2, REQ-OP-01.
- [ ] **T-PR10-02**: API endpoint `GET /api/v1/admin/sucursales/{uuid}/dashboard` — issuer `admin-`, requires `X-Sucursal-Context: <uuid>` header matching `sucursales_permitidas` (400 if missing, 403 if mismatched per REQ-X2). Returns `{fecha, ingresos_count, ingresos_monto_total, facturas_emitidas_count, facturas_electronicas_count, open_alertas_count, sync_health: {last_sync_at, lag_seconds, queue_depth}}`. Aggregates via single SQL query per metric (no N+1). Cites §21.4, REQ-X2.
- [ ] **T-PR10-03**: API endpoint `GET /api/v1/admin/me` — issuer `admin-`, returns `{actor_uuid, email, rol, sucursales_permitidas: [uuid, ...], permissions: [...]}`. Full list of `sucursales_permitidas` (used to populate the BranchSelector); `permissions` = `permisos_usuario` with `vigente_hasta IS NULL` joined to `permisos.codigo`. Cites §21.4 (admin views), REQ-OP-13.
- [ ] **T-PR10-04**: Extend `parkos_core/db/tenancy.py` — add `apply_admin_scope` to the existing `do_orm_execute` event listener from PR1 §9. When `issuer = "admin-"`: appends `WHERE uuid = ANY(:permitidas)` predicate (using `claims.sucursales_permitidas`). Defense in depth — even if a route handler forgot to filter, the listener catches it. Cites §21.4 (defense in depth), REQ-X2.
- [ ] **T-PR10-05**: API endpoint `POST /api/v1/admin/sucursales/{uuid}/revoke-sync` — already added in PR8 (T-PR8-12 sub-item d); this task verifies the route is mounted + the OpenAPI tag is `cloud-only`. Cites §21.3.
- [ ] **T-PR10-06**: Test `backend/tests/unit/test_admin_views_scope.py` — admin JWT whose `sucursales_permitidas = [A]`: `GET /sucursales` returns only A; `GET /admin/sucursales/B/dashboard` returns 403; `GET /admin/sucursales/A/dashboard` with `X-Sucursal-Context: A` returns 200. Cites §21.14 acceptance #4-5, REQ-X2.
- [ ] **T-PR10-07**: Test `backend/tests/unit/test_admin_me.py` — `GET /admin/me` returns `{actor_uuid, email, rol, sucursales_permitidas, permissions}`; `permissions` is non-empty for any seeded user (matches PR1's `0003_seed_permisos_canonicos.py`). Cites §21.4, §21.14 acceptance #6.
- [ ] **T-PR10-08**: Test `backend/tests/unit/test_dashboard_aggregation.py` — seed 10 `ingreso` rows + 5 `factura_electronica` rows + 2 `alerta` rows for branch A in the last 24h; `GET /admin/sucursales/A/dashboard` returns `{ingresos_count: 10, facturas_electronicas_count: 5, open_alertas_count: 2, ...}`. Negative test: branch B returns 403. Cites §21.4, §21.14 acceptance #5.
- [ ] **T-PR10-09**: Test `backend/tests/static/test_tenancy_admin_scope.py` — AST scan verifies `parkos_core/api/v1/admin_*.py` route handlers do NOT bypass `apply_admin_scope` listener (i.e. no raw `session.execute(select(...).where())` without the listener applying); the listener is the single source of truth for admin scope filtering. Cites §21.4 (defense in depth).
- [ ] **T-PR10-10**: Create `apps/web_admin/src/components/branch-selector/BranchSelector.tsx` — topbar component (React 18 + shadcn/ui `Select` + Tailwind). Loads `sucursales_permitidas` from `/admin/me` on mount. Default selection: first permitted. UI: per `~/.config/opencode/skills/react/SKILL.md` (PWA + accessibility). Cites §21.4 (UI integration), `shadcn` SKILL.md.
- [ ] **T-PR10-11**: Create `apps/web_admin/src/lib/sucursal-context.tsx` — React context + provider for `X-Sucursal-Context` header injection. Global `fetch` wrapper (in `apps/web_admin/src/lib/fetch.ts`) reads context + sets the header on every admin API call. localStorage key `parkos.lastSelectedSucursal` persists the selection across page reloads. Cites §21.4 (UI integration).
- [ ] **T-PR10-12**: Create `apps/web_admin/src/lib/swr-mutate-on-switch.ts` — SWR `mutate()` invalidates `/admin/sucursales/{uuid}/dashboard` cache on BranchSelector change. Tied to `sucursal-context` via `useEffect`. Cites §21.4 (UI integration).
- [ ] **T-PR10-13**: Playwright tests `apps/web_admin/src/components/branch-selector/branch-selector.spec.ts` — boots `web_admin` (Vite dev server), logs in as admin with 2 permitted branches, asserts BranchSelector renders both, switches between them, asserts `X-Sucursal-Context` header on subsequent `/sucursales/{uuid}/dashboard` calls (via Playwright route interception), asserts localStorage persists selection across page reload. Cites §21.4, `~/.config/opencode/skills/react/SKILL.md`.
- [ ] **T-PR10-14**: Refresh both OpenAPI artifacts. Verify `/sucursales`, `/admin/sucursales/{uuid}/dashboard`, `/admin/me` paths present in `api_admin/openapi.json` and ABSENT in `api_sucursal/openapi.json`. Cites §21.4, REQ-X3, REQ-OP-14.
- [ ] **T-PR10-15**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): multi-sucursal admin views + branch-selector UI`. PR body includes: chain context (📍 PR10 of 12), screen mockup reference, link to §21.4 of `design.md`. Add `type:feature` label. Cites AGENTS.md gitflow + `branch-pr` skill.

### Acceptance
- `uv run pytest backend/tests/unit/test_admin_views_scope.py -q` passes (REQ-X2 scope enforcement).
- `uv run pytest backend/tests/unit/test_admin_me.py -q` passes.
- `uv run pytest backend/tests/unit/test_dashboard_aggregation.py -q` passes.
- `uv run pytest backend/tests/static/test_tenancy_admin_scope.py -q` passes (defense in depth).
- `npx playwright test apps/web_admin/src/components/branch-selector/branch-selector.spec.ts` passes.
- `curl -X GET http://localhost:8000/api/v1/admin/me -H "Authorization: Bearer $ADMIN_JWT"` returns `{actor_uuid, email, rol, sucursales_permitidas: [...], permissions: [...]}`.
- `curl -X GET http://localhost:8000/api/v1/sucursales -H "Authorization: Bearer $ADMIN_JWT"` returns only branches in `sucursales_permitidas`.
- `curl -X GET http://localhost:8000/api/v1/admin/sucursales/<uuid>/dashboard -H "Authorization: Bearer $ADMIN_JWT" -H "X-Sucursal-Context: <uuid>"` returns 200 with dashboard data when `<uuid> ∈ permitidas`; 403 otherwise; 400 if header missing.
- `jq '.paths | keys | map(select(test("/sucursales|/admin/sucursales/.+/dashboard|/admin/me|/admin/sucursales/.+/revoke-sync"))) | length' backend/packages/api_admin/openapi.json` returns 4 (the 4 admin view routes).
- `jq '.paths | keys | map(select(test("/sucursales|/admin/sucursales/.+/dashboard|/admin/me|/admin/sucursales/.+/revoke-sync"))) | length' backend/packages/api_sucursal/openapi.json` returns 0 (cloud-only boundary).

### Estimate
~600 LOC across ~12 files (3 API route additions + 1 tenancy listener extension + 4 unit/static tests + 3 UI files + 1 Playwright spec). No conditional split.

---

## PR11 — DIAN HTTP dispatcher + cloud_router integration + Factus provider

### Branch
`feat/create-49-table-apis-pr11-dian-dispatcher` (off `dev`)

### Dependencies
- PR6 merged to `dev` (`dian/cloud_router.py` mounts the 4 cloud-only routes; this PR wires the actual HTTP calls into those route handlers).
- PR10 merged to `dev` (`GET /admin/sucursales/{uuid}/dashboard` exposes `facturas_electronicas_count` which depends on `envio_dian.estado='aceptado'` rows being present; this PR's dispatcher is the writer of those rows).
- AGENTS.md DIAN boundary canon (REQ-X3, §10 Layer 1): `parkos_core/dian/cloud/**` MUST be excluded from branch image. Verified by 3 layers (image-level `.dockerignore`, module-level `PARKOS_DEPLOY` import guard, OpenAPI tag filter). PR6 ships the `.dockerignore` exclude + the RED import-boundary test; PR11 verifies it and adds the dispatcher's own import guard.
- `[A]` canon (REQ-X5, AGENTS.md config.yaml rules.tasks): `envio_dian` and `factura_electronica` rows are written via the existing `repo/append_only.append_event` helper (PR2) — NO direct `session.execute(insert(...))` calls.

### Work-unit commit boundaries
~16 commits. The dispatcher body (T-PR11-01 + T-PR11-02) commit together as one behavior unit (send + poll + state machine). The ubl_serializer + Factus provider commit separately (provider swap is a future operator concern — adapter pattern). The 5+3+2 mock tests (success / rejection / timeout) commit together as one test suite. Docker verification (T-PR11-14) is its own commit.

### Conditional split (apply-time trigger)
If `git diff --stat` post-implementation > 800 LOC → execute **PR11a** (T-PR11-01 through T-PR11-06 + T-PR11-12 + T-PR11-13, dispatcher + ubl_serializer + Factus provider + cloud_router integration, ~400 LOC) + **PR11b** (T-PR11-07 through T-PR11-11 + T-PR11-14 through T-PR11-16, mock tests + Docker verify + AGENTS.md + commit, ~300 LOC). Per `chained-pr` skill.

### Tasks

- [ ] **T-PR11-01**: Create `parkos_core/dian/cloud/dispatcher.py` — `async dispatch_factura_electronica(session, *, uuid_factura_electronica: UUID, actor_uuid: UUID) -> EnvioDianRead` per §21.11: (1) load `factura_electronica` row + serialize via `ubl_serializer.serialize(row)`; (2) `POST {PARKOS_DIAN_PROVIDER_URL}/api/ubl2.1` with `Authorization: Bearer {PARKOS_DIAN_PROVIDER_TOKEN_PATH contents}`; (3) on trackId returned, poll `GET /api/ubl2.1/{trackId}` every 2s up to `PARKOS_DIAN_TIMEOUT_S` (default 30s); (4) on `aceptado`: INSERT `envio_dian` row (`estado='aceptado'`, `cufe=<returned>`, `reportado_dian=true`, `fecha_retencion_hasta=NOW()+INTERVAL '5 years'`); (5) on `rechazado`: INSERT `envio_dian` row with `motivo_rechazo=<body>` + INSERT `alerta tipo_alerta='dian_rechazada'` chain root; (6) on timeout: `schedule_retry` with `backoff_5xx` (1m, 5m, 15m) up to `PARKOS_DIAN_RETRY_MAX` (default 3); (7) on final timeout: INSERT `envio_dian` row with `estado='timeout'` + INSERT `alerta tipo_alerta='dian_timeout'`. The DB trigger's `AFTER INSERT` on `envio_dian` enqueues `sync_queue` row (PR2 §12). Cites §21.11 (DIAN dispatcher), REQ-X4 (hash chain extension for branch, not cloud).
- [ ] **T-PR11-02**: Add `async dispatch_revocacion(session, *, uuid_revocacion_factura: UUID, actor_uuid: UUID) -> EnvioDianRead` to `dispatcher.py` — same flow but POST to `/api/revocacion`; on `aceptado`: extend `prod.revocacion_factura` hash chain via `repo/hash_chain.append()` (per §21.11 step 2); emit SyncBackEvent to branch. Cites §21.11 (DIAN dispatcher step 2).
- [ ] **T-PR11-03**: Create `parkos_core/dian/cloud/ubl_serializer.py` — `serialize(factura: FacturaElectronica) -> bytes` builds a UBL 2.1 XML from the `factura_electronica` row (vendor + customer + lines + taxes + totals). Uses `lxml` for namespace handling. The XML schema validated against `xsd/UBL-Invoice-2.1.xsd` (bundled in repo, NOT a network fetch). Cites §21.11 (UBL 2.1).
- [ ] **T-PR11-04**: Create `parkos_core/dian/cloud/dian_providers/__init__.py` + `parkos_core/dian/cloud/dian_providers/factus.py` — initial provider adapter implementing `class DianProvider` ABC (`async send_ubl(xml_bytes) -> trackId`, `async poll(trackId) -> PollResult`, `async send_revocacion(xml_bytes) -> trackId`). Factus-specific URL paths: `/api/ubl2.1`, `/api/ubl2.1/{trackId}`, `/api/revocacion`. Auth: Bearer token. Cites §21.11 (configuration env), §21.13 (provider-specific quirks deferred).
- [ ] **T-PR11-05**: Create `parkos_core/dian/cloud/atomic_next_consecutivo.py` — `async next_consecutivo(session, uuid_resolucion_facturacion: UUID) -> int` per REQ-OP-12: `SELECT ... FOR UPDATE` on the `resolucion_facturacion` row + read `V_RESOLUCION_CONSECUTIVO` view + INSERT new `factura_electronica` with the assigned `consecutivo` in the same TX. Replaces bootstrap's stub. Cites REQ-OP-12, REQ-34 (atomic next-consecutivo).
- [ ] **T-PR11-06**: Wire `dispatch_factura_electronica` into `parkos_core/dian/cloud_router.py` — the `POST /api/v1/factura-electronica` handler now calls `dispatcher.dispatch_factura_electronica(...)` after the atomic `next_consecutivo` insert. Same for `POST /api/v1/revocacion-factura-webhook` → `dispatcher.dispatch_revocacion`. Cites §21.11 (DIAN dispatcher wiring).
- [ ] **T-PR11-07**: Module-level import guard in `dispatcher.py` — first statement: `if os.environ.get("PARKOS_DEPLOY") != "cloud": raise ImportError("dian_cloud_unavailable_on_branch")`. Defense in depth (3-layer boundary). Cites §10 (DIAN boundary Layer 2), §21.11 (3 layers).
- [ ] **T-PR11-08**: Test `backend/tests/dian/test_dispatcher.py` — 3 success paths via `httpx.MockTransport`: (a) `test_dispatcher_accepts_and_writes_envio_dian` (trackId returned → poll → aceptado → `envio_dian.estado='aceptado'`, `cufe` set, `reportado_dian=true`); (b) `test_dispatcher_rechazado_writes_envio_dian_and_alerta` (rechazado → `envio_dian.estado='rechazado'`, `motivo_rechazo` set, `alerta tipo_alerta='dian_rechazada'` written); (c) `test_dispatcher_timeout_retries_then_alerts` (timeout → `schedule_retry` then after `PARKOS_DIAN_RETRY_MAX` attempts → `envio_dian.estado='timeout'` + `alerta tipo_alerta='dian_timeout'`). Cites §21.14 acceptance #18, §21.11.
- [ ] **T-PR11-09**: Test `backend/tests/dian/test_dispatcher_3_rejections.py` — 3 rejection paths (provider 4xx, malformed XML, missing auth) each insert `envio_dian.estado='rechazado'` + alerta. Cites §21.11.
- [ ] **T-PR11-10**: Test `backend/tests/dian/test_dispatcher_2_timeouts.py` — 2 timeout paths (initial POST times out, poll times out after trackId) — both produce `envio_dian.estado='timeout'` after retries exhausted. Cites §21.11.
- [ ] **T-PR11-11**: Test `backend/tests/dian/test_dispatcher_boundary.py` — set `PARKOS_DEPLOY=branch`; `from parkos_core.dian.cloud.dispatcher import dispatch_factura_electronica` raises `ImportError("dian_cloud_unavailable_on_branch")`. Cites §21.14 acceptance #19, §10 Layer 2.
- [ ] **T-PR11-12**: Test `backend/tests/dian/test_dispatcher_hash_chain_branch_not_cloud.py` — successful dispatch writes a `log_transaccional` row with `uuid_sucursal = branch.uuid` (NOT `cloud.uuid`); the row's `hash_anterior` = branch's prior `log_transaccional.hash_actual`. Cites §21.11 step 3 (hash chain extension), AGENTS.md `Hash chain` section.
- [ ] **T-PR11-13**: Test `backend/tests/dian/test_ubl_serializer.py` — given a fully-populated `factura_electronica` row, `serialize()` produces a UBL 2.1 XML that validates against the bundled `xsd/UBL-Invoice-2.1.xsd`. Uses `lxml.etree.XMLSchema(etree.parse(xsd))`. Cites §21.11.
- [ ] **T-PR11-14**: Test `backend/tests/dian/test_factus_provider.py` — `FactusProvider.send_ubl(xml_bytes)` makes `POST {url}/api/ubl2.1` with `Authorization: Bearer {token}`; `poll(trackId)` polls `GET {url}/api/ubl2.1/{trackId}` every 2s; mocks via `httpx.MockTransport`. Cites §21.11 (Factus adapter).
- [ ] **T-PR11-15**: Docker verification — `cat backend/.dockerignore | grep -E '^\*\*\/dian\/cloud\/\*\*$'` exits 0 (image-level boundary layer 1 verified in CI); `docker build -f infra/docker/Dockerfile.branch .` does NOT include `parkos_core/dian/cloud/dispatcher.py` (verify via `docker run --rm parkos:branch-test python -c "import parkos_core.dian.cloud.dispatcher"` → `ModuleNotFoundError`). Cites §21.14 acceptance #19, §10 Layer 1.
- [ ] **T-PR11-16**: Update `AGENTS.md` Risk Register — add risk #25 "DIAN provider rate-limit (Factus allows N req/min)" (LOW) per §21.12. Close risk #3 "Hash-chain break on partial sync" with mitigation `job_sync_cloud.hash_chain_verifier_loop` (PR9) + dispatcher hash chain extension (PR11). Cites §21.12, §21.11.
- [ ] **T-PR11-17**: Refresh both OpenAPI artifacts; verify the 4 cloud-only paths (`/factura-electronica`, `/envio-dian`, `/validacion-evento`, `/revocacion-factura-webhook`) are present in `api_admin/openapi.json` and ABSENT in `api_sucursal/openapi.json`. Cites §21.14 acceptance #20 (unchanged from PR6).
- [ ] **T-PR11-18**: Commit + push + open PR → `dev`. PR title: `feat(create-49-table-apis): DIAN HTTP dispatcher + Factus provider + cloud_router wiring`. PR body includes: chain context (📍 PR11 of 12), 3-layer DIAN boundary diagram, link to §21.11 of `design.md`. Add `type:feature` label. Cites AGENTS.md gitflow + `branch-pr` skill.

### Acceptance
- `uv run pytest backend/tests/dian/test_dispatcher.py -q` passes (3 success paths via `httpx.MockTransport`).
- `uv run pytest backend/tests/dian/test_dispatcher_3_rejections.py -q` passes.
- `uv run pytest backend/tests/dian/test_dispatcher_2_timeouts.py -q` passes.
- `uv run pytest backend/tests/dian/test_dispatcher_boundary.py -q` passes (ImportError on branch).
- `uv run pytest backend/tests/dian/test_dispatcher_hash_chain_branch_not_cloud.py -q` passes.
- `uv run pytest backend/tests/dian/test_ubl_serializer.py -q` passes (XSD-validated).
- `uv run pytest backend/tests/dian/test_factus_provider.py -q` passes.
- `cat backend/.dockerignore | grep -E '^\*\*\/dian\/cloud\/\*\*$'` exits 0.
- `docker build -f infra/docker/Dockerfile.branch .` succeeds; `docker run --rm parkos:branch-test python -c "import parkos_core.dian.cloud.dispatcher"` raises `ModuleNotFoundError`.
- `jq '.paths | keys | map(select(test("/factura-electronica|/envio-dian|/validacion-evento|/revocacion-factura"))) | length' backend/packages/api_admin/openapi.json` returns 4 (unchanged from PR6).
- `jq '.paths | keys | map(select(test("/factura-electronica|/envio-dian|/validacion-evento|/revocacion-factura"))) | length' backend/packages/api_sucursal/openapi.json` returns 0 (3-layer boundary).
- `curl -X POST http://localhost:8000/api/v1/factura-electronica` with mock provider returns 201 + `envio_dian.cuid`; branch image import of the route handler raises `ImportError`.

### Estimate
~700 LOC across ~10 files (1 dispatcher + 1 ubl_serializer + 1 Factus provider + 1 atomic_next_consecutivo + 1 cloud_router integration diff + 6 test files). **Apply-time split trigger: > 800 LOC → PR11a (dispatcher + serializer + Factus + cloud_router) + PR11b (tests + Docker verify + AGENTS.md + commit).**

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
| PR8 | 26 | ~750 | 16 | **HIGH** (apply-time split to 8a+8b; migration `0003` ships BOTH `[A]` tables + REVOKE + triggers) |
| PR9 | 20 | ~800 | 14 | **HIGH** (apply-time split to 9a+9b; sync workers) |
| PR10 | 15 | ~600 | 12 | MED (multi-sucursal admin views + branch-selector UI) |
| PR11 | 18 | ~700 | 10 | **HIGH** (apply-time split to 11a+11b; DIAN dispatcher) |
| **Total** | **200** | **~7,880** | **~179** | 5 conditional splits: PR5a/5b, PR6a/6b, PR8a/8b, PR9a/9b, PR11a/11b |

## Risks surfaced

1. **PR5 + PR6 + PR9 + PR11 at 800-LOC edge** — pre-scoped conditional splits (PR5a/5b, PR6a/6b, PR9a/9b, PR11a/11b) per `proposal.md` §PR slicing + `design.md` §21 PR slicing delta. Apply triggers split if `git diff --stat` post-implementation > 800 LOC. PR8 has a split trigger too but only if blown; default is single PR. No `size:exception` required.
2. **`tipo_arqueo` missing from bootstrap** — PR0 reconciles docs; PR3 ships the ORM model only if `preflight_table_counts.sh` exits 0 (verifies `\dt prod.*` includes `tipo_arqueo`). If not, PR3 is blocked until bootstrap backfills.
3. **`resolucion_facturacion`, `envio_dian`, `validacion_evento` missing from bootstrap** — same pre-flight gate covers these. PR4 (for `resolucion_facturacion`) and PR6 (for `envio_dian`, `validacion_evento`) MUST NOT merge until bootstrap ships them.
4. **50th table `idempotency_keys` not in bootstrap** — PR7 ships its own migration `0002_add_idempotency_keys.py` with REVOKE + trigger in the SAME script (per `config.yaml` rules.tasks).
5. **51st + 52nd `[A]` tables (`pairing_tokens`, `revoked_sync_jwts`) not in bootstrap** — PR8 ships migration `0003_add_pairing_tokens_and_revoked_sync_jwts.py` with BOTH tables + BOTH `REVOKE UPDATE, DELETE` statements + BOTH `BEFORE UPDATE OR DELETE` triggers in the SAME script (per `config.yaml rules.tasks` + §21.3).
6. **DIAN boundary** — three-layer defense: (a) `.dockerignore` excludes `**/dian/cloud/**` from branch image (bootstrap ships, PR11 verifies); (b) lazy `PARKOS_DEPLOY` import guard in `api/v1/__init__.py` (PR6 ships, PR11 adds the dispatcher's own guard); (c) RED test `test_dian_boundary_branch.py` (PR6) + OpenAPI tag filter (PR6, verified by PR11).
7. **Hash-chain break on partial sync** — `hash_chain.append()` reads prior `MAX(timestamp_evento)` per `uuid_sucursal` (PR2 ships). Cloud `job_sync_cloud.hash_chain_verifier_loop` catches breaks (PR9 ships). DIAN dispatcher extends hash chain for the BRANCH's `uuid_sucursal`, not cloud (PR11 ships per §21.11 step 3).
8. **REVOKE/trigger drift** — bootstrap's entrypoint verifier covers it on every boot (PR0 + bootstrap). PR8's migration test `test_pairing_tokens_inmutable.py` + PR9's docker boot test add belt-and-suspenders for the 2 new `[A]` tables.
9. **Pairing token replay — CLOSED by §21.3 / PR8** — single-use 24h TTL + sha256-only persistence + 5/hour/admin rate limit + atomic `SELECT ... FOR UPDATE SKIP LOCKED` consume + JWT rotation grace (`JWT_OVERLAP_HOURS=24`). Verified by `test_pairing_flow.py` (9 tests per §21.14 acceptance #1).
10. **Polymorphic FK validator performance** — Redis cache 60s TTL populated by sync worker (PR6 ships consumer; sync worker is PR9 ships).
11. **Subscription vehicle count race** — `pg_advisory_xact_lock(uuid_subscripcion_cliente)` in Pydantic validator (PR5 ships).
12. **Per-branch misconfig of `PARKOS_SUCURSAL_UUID` (operator typo)** — boot-time fail-fast validator `parkos_core/runtime/env.py::load_config()` raises `MissingEnvError` exit `2`; `parkos-core doctor` subcommand prints diagnostic report (PR8 ships per §21.12 risk #23).
13. **Two parallel `job_sync_cloud` instances race on hash chain** — single-instance design enforced via `deploy.replicas: 1` in compose (PR9 ships per §21.12 risk #24); HA with advisory locks deferred to v2.
14. **DIAN provider rate-limit (Factus allows N req/min)** — token bucket per provider, `PARKOS_DIAN_RETRY_MAX=3` defaults; 429 → schedule_retry with `backoff_5xx` (PR11 ships per §21.12 risk #25).

## Out of scope reminders (NOT deliverables of this change)

> §21 closes most of the items the original proposal deferred (DIAN HTTP transport, sync engine, pairing flow, hash chain verifier worker). The following remain deferred:

- Web frontend beyond the branch-selector (`web_admin`/`web_sucursal` PWA surface area outside PR10's `<BranchSelector />`) — bootstrap PR6 owns.
- Operational tooling (rate limiting beyond sync + pairing, OTel, Prometheus exporters, advanced circuit breakers) — separate change.
- RBAC permission matrix population (per-role assignment to permissions) — follow-up change; PR1 ships framework + canonical permission codes only.
- OpenAPI TS client SDK generator wiring (`apps/ui-kit/package.json`) — bootstrap PR6 owns.
- Bulk-CSV import endpoints — separate change per REQ-OP-06.
- `multipart/form-data` for `documentos` — base64 inline accepted in MVP per REQ-OP-05.
- WebSocket sync transport — polling only for v1; deferred to v2 per §21.13.
- TTL worker for `idempotency_keys` nightly cleanup — separate batch.
- DIAN provider-specific quirks beyond the Factus adapter (other providers' rate limits, sandbox vs production endpoints) — operator-supplied via env vars per §21.13.
- `parkos-cli pair --interactive` wizard (operator-friendly) — only the env-var-driven `python -m parkos_core.cli pair` ships per §21.13.
- HA `job_sync_cloud` with Postgres advisory locks per `uuid_sucursal` — single-instance design per §21.12 risk #24; multi-instance deferred to v2.
- `multipart/form-data` upload endpoint at `POST /api/v1/documentos/upload` — base64 inline is enough for v1 per REQ-OP-05.
