# Proposal: Bootstrap Monorepo Foundation

## Intent

Empty repo: only `modelo_datos_er.mmd` (45 AUDIT-FIRST tables). Ships the working skeleton so engineers code against the ratified layout, the first Alembic migration lands with full DIAN-grade schema, the JWT three-issuer model becomes real, and an operator stands up a fresh branch with one Docker command. AUDIT-FIRST (24 [V] / 9 [L] / 12 [A]) + DIAN 5+ year retention + SHA256 hash chain honored at the migration level.

## Scope

**In**: uv workspace `backend/packages/{parkos_core, api_admin, api_sucursal, job_sync_cloud, job_sync_sucursal}` + npm workspaces `apps/{web_admin, web_sucursal, ui-kit}`; multi-stage `Dockerfile`; `docker-compose.{cloud,branch}.yml`; `infra/postgres/init/{01_roles.sql, 02_extensions.sql}` (roles + extensions ONLY); `0001_initial_schema.py` (45 tables + 11 REVOKE on [A] + 11 [A] triggers + 2 [L-S] session guards + 8 `pg_partman.create_parent` + hash-chain genesis + idempotent seed); `infra/docker/entrypoint.sh` + per-service (`rol_app` precheck, `alembic upgrade head`, REVOKE/trigger verifier); `workers/{hash_chain_verifier, dian_dispatcher}/entrypoint.sh`; `docs/*.md`; six-slice chained PRs (PR2 carries `size:exception`).

**Out**: real e-factura dispatch; real sync worker business logic; CRUD beyond `/health`+`/auth/login`; PWA beyond offline shell; BFF (v2); WebSocket sync; native installer.

## Capabilities

### New

- `monorepo-layout` — uv workspace + npm workspace; root configs
- `postgres-bootstrap-roles-extensions` — `01_roles.sql` (rol_app NOLOGIN, rol_admin_auditor BYPASSRLS) + `02_extensions.sql` (pg_partman, pgcrypto, uuid-ossp)
- `database-initial-schema` — `0001_initial_schema.py`: schema `prod`, 45 tables, 11 REVOKE on [A] (sync_queue excluded), 11 [A] triggers, 2 [L-S] session guards, 8 `pg_partman.create_parent`, hash-chain genesis, idempotent seed
- `container-runtime-and-compose` — multi-stage Dockerfile (`BUILD_TARGET`/`SERVICE_NAME`); `docker-compose.{cloud,branch}.yml`; HEALTHCHECK + `depends_on: service_healthy`
- `container-entrypoint-orchestration` — shared `infra/docker/entrypoint.sh` + per-service; `rol_app` precheck; `alembic upgrade head`; post-migration verifier; abort non-zero on drift
- `branch-install-flow` — `docker pull` + `docker compose -f docker-compose.branch.yml up -d`; env-driven; git-clone fallback; pairing exchange shell
- `pwa-scaffolds` — `apps/{web_admin, web_sucursal, ui-kit}/` React 18 + Vite 5 + TS strict + shadcn/ui + Zustand + react-hook-form + Zod + i18next es-CO + vite-plugin-pwa + axe-core CI gate; offline shell only

### Modified

None — `openspec/specs/` is empty.

## Approach

Two workspaces, one image, one migration. `backend/pyproject.toml` declares `[tool.uv.workspace] members = ["packages/*"]`; `apps/package.json` declares npm workspaces. `infra/postgres/init/` is bootstrap-only; `0001_initial_schema.py` owns schema, REVOKE, triggers, partitions, seed, hash-chain genesis in one coherent migration. Entrypoint runs `alembic upgrade head` per boot (idempotent) then verifies REVOKE + triggers via `pg_trigger` — aborts non-zero on drift.

## Risks

- **Chained-PR size (High)**: 6 slices, 2500-4000+ LOC — PR1 infra skeleton; PR2 `0001_initial_schema.py` with `size:exception`; PR3 `parkos_core`+auth+tenancy+health; PR4 api routers + JWT three issuers; PR5 sync workers + pairing; PR6 PWA + ui-kit
- **REVOKE no-ops (High)**: if `init/01_roles.sql` didn't run — entrypoint `rol_app` precheck BEFORE `alembic upgrade head`; abort non-zero
- **`uv sync --package X` transitive deps (Med)**: each service `pyproject.toml` lists `parkos_core` explicitly in `dependencies`
- **Image size ≈ 450-550MB on flaky links (Med)**: `docker pull` happy path; `git clone + docker compose build` fallback documented
- **TS strict + vite-plugin-pwa + axe-core first-time cost (Med)**: `apps/ui-kit/` absorbs bulk; PR6 is one slice

## Rollback Plan

Each PR independently revertible. PR1: `git revert`, no DB state. PR2: `docker compose exec api_sucursal alembic downgrade base` drops schema `prod` (fresh DB only; non-fresh: targeted `alembic downgrade -1`). PR3-PR6: code-only reverts. Global: `git revert` all six in reverse order; if branches onboarded, manually `alembic downgrade base` on each DB. Registry tags preserved.

## Dependencies

Engram #1217, #1219, #1220, #1221, #1222; `cloud-edge-sync-architecture/exploration.md`; `openspec/config.yaml` rules.proposal (applied); `modelo_datos_er.mmd`; tooling: Docker Desktop, uv 0.4+, Node 20+, PostgreSQL 16 image.

## Success Criteria

- [ ] Both compose stacks boot; `/health` 200 on `api_admin` and `api_sucursal`
- [ ] `0001_initial_schema.py` applied: 45 tables in `prod`; `reject_mutation` + `ls_session_update_guard` exist; REVOKE verified on 11 [A] tables; hash-chain genesis rows present
- [ ] Entrypoint REVOKE verifier exits non-zero on tampering; JWT three issuers reject cross-audience tokens; PWA apps build clean under `tsc --noEmit`; axe-core CI gate passes
- [ ] All six chained PRs merged (PR2 carries `size:exception`); `openspec/specs/{monorepo-layout, postgres-bootstrap-roles-extensions, database-initial-schema, container-runtime-and-compose, container-entrypoint-orchestration, branch-install-flow, pwa-scaffolds}/spec.md` each created by sdd-spec
