# easypunto_parkos — AGENTS.md

> Living project agent guide. Mirrors the cross-cutting conventions and stack
> decisions. Read this before launching any sub-agent in this project.

## Project

- **Name**: easypunto_parkos (parking-lot management system)
- **Workspace root**: `E:\easypunto_parkos`
- **Platform**: Windows (PowerShell 5.1)
- **Architecture**: multi-tenant cloud-edge with bidirectional sync
  - Cloud admin (central Postgres) + each branch (own Postgres local)
  - Topology: `web_admin <-> api_admin <-> job_sync_cloud <-> many(job_sync_sucursal) <-> many(api_sucursal) <-> web_sucursal`
  - Two distinct web apps (admin multi-tenant, branch single-tenant)
- **Deployment**: Docker Compose for both cloud and branch (same image, two compose files)
- **Compliance**: DIAN Colombia (electronic invoicing, 5+ year retention, SHA256 hash chain on `log_transaccional` and `revocacion_factura` per `uuid_sucursal`)
- **Authorization model**: `feature-branch-chain` (user-ratified for compliance-heavy schemas)

## Tech Stack (assumed, to be ratified in `bootstrap-monorepo-foundation/design`)

### Backend

- **Python 3.13** + **uv** workspace (monorepo)
- **FastAPI** + **SQLAlchemy 2.0 (async)** + **Pydantic v2**
- **Alembic** for migrations; co-located at `backend/packages/parkos_core/migrations/`
- **bcrypt** for password hashing; **JWT** (RS256) with three issuers: `admin-`, `operador-`, `sync-agent-`
- **httpx** for sync transport (HTTP polling); WebSocket deferred to v2
- **structlog** for logging
- **pytest** + **testcontainers** (deferred to first feature change; `config.yaml` reconfigure trigger)

### Database

- **PostgreSQL 16+** in cloud and on each branch
- **AUDIT-FIRST** schema with 3 enforcement levels: `[V]` projection, `[L]` lifecycle, `[A]` source-of-truth
- **REVOKE UPDATE, DELETE** on 11 `[A]` tables from `rol_app`; `rol_admin_auditor` has BYPASSRLS
- **`pg_partman`** for monthly partitioning of high-volume tables
- **DIAN-only tables** (`factura_electronica`, `revocacion_factura`) live ONLY in cloud; branches have schema parity but never write
- **`empresa.consecutivo_actual`** is atomic in cloud; branches read via sync
- **Hash chain**: `hash_anterior` references previous row's `hash_actual` per `uuid_sucursal`

### Frontend

- **React 18 PWA** + **Vite 5** + **TypeScript strict**
- **shadcn/ui** + **Tailwind** + **CSS variables** (white-label tokens)
- **Zustand** + **react-hook-form** + **Zod** + **i18next** (`es-CO` default)
- **vite-plugin-pwa** + **IndexedDB** for offline shell
- **@axe-core/playwright** in CI for WCAG 2.1 AA
- **Two apps**: `web_admin` (multi-tenant, branch selector), `web_sucursal` (branch-pinned)

### DevOps

- **Docker** multi-stage Dockerfile with `BUILD_TARGET` build-arg + `SERVICE_NAME` runtime env var
- **Docker Compose v2**: `docker-compose.cloud.yml`, `docker-compose.branch.yml`
- **ghcr.io/easypunto/parkos:vX.Y.Z** for image registry
- **uv** workspace at `backend/`; npm workspaces at `apps/`
- **Conventional Commits** (no Co-Authored-By / AI attribution)

## Sub-Agents Available (from `~/.config/opencode/agents/`)

| Agent | When to use | Reads | Writes |
|---|---|---|---|
| `sdd-init` | Bootstrap SDD context for a new project | project files | `openspec/`, `.atl/skill-registry.md` |
| `sdd-explore` | Investigate before committing to a change | codebase, prior artifacts | `openspec/changes/{name}/exploration.md` + Engram |
| `sdd-propose` | Formal proposal for a change | proposal inputs | `openspec/changes/{name}/proposal.md` + Engram |
| `sdd-spec` | Write delta/full specs | proposal, prior specs | `openspec/changes/{name}/specs/`, `openspec/specs/` + Engram |
| `sdd-design` | Technical design | proposal, specs, codebase | `openspec/changes/{name}/design.md` + Engram |
| `sdd-tasks` | Break design into implementation tasks | proposal, specs, design | `openspec/changes/{name}/tasks.md` + Engram |
| `sdd-apply` | Implement tasks in batches (chained PRs supported) | tasks, design, specs | `apply-progress` + Engram + git/PRs |
| `sdd-verify` | Validate implementation against specs | tasks, design, specs, apply-progress | `verify-report` + Engram |
| `sdd-archive` | Close a change with delta spec sync | all artifacts | `archive-report` + Engram |
| `explore` | Freeform read-only mapping | repo | nothing |
| `general` | Unstructured queries, fallback | anything | anything |

## Cross-Cutting Conventions

### Python (`backend/`)

- All async (SQLAlchemy 2.0 `AsyncSession`)
- Models partitioned by audit level in `parkos_core/models/`:
  - `models/V/` (24 versioned tables)
  - `models/L_E/` (3 L-E events)
  - `models/L_W/` (4 L-W workflows)
  - `models/L_S/` (2 L-S sessions)
  - `models/A/` (12 append-only tables)
- Every model has `created_at`, `created_by`, `vigente_desde`/`vigente_hasta` (for `[V]`), `sync_status`/`sync_timestamp`/`sync_attempts`
- Hash chain columns (`hash_anterior`, `hash_actual`) live on `log_transaccional` and `revocacion_factura` ONLY
- DIAN retention column `fecha_retencion_hasta` per row

### Alembic migrations

- Co-located at `backend/packages/parkos_core/migrations/versions/`
- `env.py` does `from parkos_core.models import *` plain (no `sys.path` hacks)
- `include_schemas=True` for the `prod.*` schema
- Every migration that touches `[A]` tables MUST include the REVOKE statement AND the BEFORE UPDATE OR DELETE trigger in the SAME migration (`config.yaml` `rules.tasks`)
- Pre-flight `alembic upgrade --sql` check before applying any migration

### Docker

- One multi-stage `Dockerfile`; `BUILD_TARGET` build-arg selects one of four entrypoints
- `SERVICE_NAME` runtime env var selects at boot
- Shared `infra/docker/entrypoint.sh` orchestrates: `wait-postgres → rol_app precheck → alembic upgrade head → REVOKE/trigger verifier → exec CMD`
- Branch entrypoint additionally POSTs `/sync/pair` and persists the long-lived JWT
- Compose files: `docker-compose.cloud.yml` (admin + jobs + workers + cloud DB), `docker-compose.branch.yml` (branch API + sync + branch DB)

### JWT (three issuers)

- Three key sets, one per issuer:
  - `admin-` (admin users; long-lived; broad scope)
  - `operador-` (branch operators; medium-lived; branch-pinned via `uuid_sucursal`)
  - `sync-agent-` (sync workers; long-lived; sync scope)
- `kid` prefix identifies the issuer; cross-issuer tokens rejected by `iss + aud`
- Grace rotation: `JWT_OVERLAP_HOURS=24` (both keys in JWKS during rotation)

### Sync

- `sync_queue` is `[A]` with operational UPDATE exception (estado, intentos, next_retry_at, ultimo_error); local-only, never propagated
- `sync_log` and `sync_conflict` also local-only, no propagation
- Conflict policy defaults per class:
  - `[V]` = manual
  - `[L-E]` = append
  - `[L-W]` = append
  - `[A]` = append
  - `[L-S]` = manual
- Hash-chain survival: cloud preserves branch chain verbatim, only extends with cloud-originated rows
- HTTP polling only (MVP); WebSocket deferred to v2

### DIAN

- 100% centralized in cloud admin
- `factura_electronica` and `revocacion_factura` written ONLY in cloud
- Branch online mode: synchronous POST to `/facturas/procesar` returns real `numero_oficial`
- Branch offline mode: prints `numero_temporal` (preliminar), enqueues `factura` in `sync_queue`; cloud assigns real and sends `SyncBackEvent` back; `reimpresion_ticket` enabled only after sync-back
- Atomic `empresa.consecutivo_actual` mutated only in cloud

### Frontend

- Multi-branch selector in `web_admin`; branch-pinned in `web_sucursal`
- `preliminar` badge on `web_sucursal` until `SyncBackEvent` arrives
- `reimpresion_ticket` disabled until `SyncBackEvent`
- axe-core CI gate must pass for WCAG 2.1 AA

## Workflow (SDD)

1. Preflight collected: pace=`interactive`, artifact=`hybrid`, delivery=`ask-on-risk`, chain=`feature-branch-chain`, budget=`400 lines` per PR
2. Every change follows: explore → propose → spec → design → tasks → apply → verify → archive
3. Each phase persisted to BOTH OpenSpec (`openspec/changes/{name}/`) AND Engram (topic_key `sdd/{name}/{phase}`)
4. In interactive mode: orchestrator shows result + asks before next phase
5. Chained PRs recommended when forecast >400 LOC; `feature-branch-chain` for compliance-heavy changes

## Risk Registers (project-wide)

| Risk | Mitigation |
|---|---|
| Hash-chain break on partial sync | per-branch monotonic seq in `datos` JSON; cloud verifier |
| REVOKE/trigger drift on branch boot | entrypoint runs `pg_trigger` check; abort non-zero |
| Outbox bypass on direct `[A]` writes | `AFTER INSERT` trigger into `sync_queue` (PR5 task) |
| Tenant scope leak in admin JWT | `X-Sucursal-Context` enforced against `sucursales_permitidas` on every call |
| Pairing-token replay | single-use, 24h TTL, rate-limited |
| DIAN `consecutivo_actual` race | atomic UPDATE in cloud only; branches read via sync |
| `0001_initial_schema.py` is one big file | PR2 carries explicit `size:exception`; not split (would break single-head invariant) |

## Active Change

- `bootstrap-monorepo-foundation` (Phase 1) — 6 chained PRs planned, feature-branch-chain strategy, PR1 ready to launch
- See `openspec/changes/bootstrap-monorepo-foundation/` for proposal/specs/design/tasks
- See `openspec/_meta/roadmap.md` for the full system roadmap across all 9 phases