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
- **Authorization model**: `gitflow` (user-ratified) — `main` (producción) + `dev` (integración) + feature branches; **PRs mergean a `dev` (nunca directo a `main`)**; cada rama certificada se mergea a `dev`, y de `dev` a `main` solo via release branch con certificación
- **Data architecture**: Audit-First / Compliance-Driven with Bi-Temporal model and logical deletion only — see [Architectural Principles](#architectural-principles) below
- **API contract**: C/Q/U only — Consulta, Inserción, Actualización (bi-temporal). **No physical DELETE at any layer.**

## Architectural Principles

These principles are project-wide canon. Every sub-agent (and every human
change) MUST honor them. They are non-negotiable.

### 1. Audit-First / Compliance-Driven Data Architecture

The data layer is designed for regulatory auditability from day one:

- Every row carries `created_at`, `created_by`, plus class-specific audit columns
- Compliance tables (`factura_electronica`, `revocacion_factura`,
  `log_transaccional`) carry `fecha_retencion_hasta` (DIAN: 5+ years) and
  SHA256 `hash_anterior` / `hash_actual` chains per `uuid_sucursal`
- `REVOKE UPDATE, DELETE` on 11 `[A]` tables from `rol_app`;
  `rol_admin_auditor` is the only role with `BYPASSRLS`
- `BEFORE UPDATE OR DELETE` triggers on `[A]` tables block any mutation
  outside the allowed paths and force corrections to be expressed as new rows
- The canonical column-level view lives at `modelo_datos_er.mmd` — every
  entity there has `Audit`, `Versioning`, and `Sync` blocks by construction

### 2. Bi-Temporal Model with Logical Deletion (Borrado Lógico)

The model is bi-temporal. Every `[V]` and `[L]` row carries:

- **Valid time** (`vigente_desde`, `vigente_hasta`): when the fact was true in
  the real world. `vigente_hasta IS NULL` means the version is current
- **Transaction time** (`created_at`): when the fact was recorded in the DB

The UK of every `[V]` row includes `vigente_desde`, so the version is part
of identity — multiple versions of the same logical entity coexist as
distinct rows.

**Logical deletion ONLY. No physical DELETE is permitted at any layer**
(API, ORM, SQL, migrations, seed scripts). Closing a version means:

1. Set `vigente_hasta = NOW()` and `estado = 'inactivo'` on the current row
2. `INSERT` a new row with the new state (`vigente_desde = NOW()`,
   `vigente_hasta = NULL`, `estado = 'activo'`)

Both rows remain in the table forever; history is reconstructable at any
point in time. Corrections that look like "deletes" — `anular`, `revertir`,
`reverso`, `corregir salida errónea` — are expressed as new compensating
rows in the corresponding workflow table, never as physical DELETE.

### 3. API Operation Contract — Consulta, Inserción, Actualización (no Delete)

The API exposes exactly three operations per resource:

- **Consulta (Query)**: `SELECT` reads; views and projections are fine
- **Inserción (Insert)**: `INSERT` of a new row (a new version, a new event,
  or an append to an `[A]` table)
- **Actualización (Update)**: bi-temporal — *cambio de estado + nuevo
  registro*. Close the current row (`vigente_hasta = NOW()`,
  `estado = 'inactivo'`) AND insert a new row with the new state

**NO ESTÁ PERMITIDA LA ELIMINACIÓN DE NINGÚN REGISTRO.** The API has no
`DELETE` operation at any layer. Conceptual deletion is modeled as:

- a new row in a workflow table (`anulaciones`, `reimpresion_ticket`,
  `reclamos`, `alerta`)
- a compensating row (`factura_pagos.tipo_movimiento = 'reverso'`,
  pointing at `uuid_pago_revertido`)
- a derived view state (`V_FACTURA_ESTADO`, `V_INGRESO_ESTADO`,
  `V_FE_ESTADO_DIAN`, `V_RESOLUCION_CONSECUTIVO`) — state is *derived*,
  never stored

Enforced at three levels: **API** (no endpoint), **ORM** (close+insert
helpers, no hard delete on `[V]`/`[A]`), **DB** (`REVOKE DELETE` on `[A]` +
`BEFORE UPDATE OR DELETE` trigger). All three are required — defense in
depth.

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
- **Bi-temporal columns** (`vigente_desde` / `vigente_hasta` / `estado` on `[V]` and `[L]`) — every UK includes `vigente_desde`; canonical column-level view at `modelo_datos_er.mmd`
- **No physical DELETE** — `REVOKE DELETE` on `[A]` + `BEFORE UPDATE OR DELETE` trigger; corrections modeled as workflow rows. See [Architectural Principles](#architectural-principles).
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
- Models partitioned by audit level in `parkos_core/models/` (counts track `modelo_datos_er.mmd` — 49 tables total):
  - `models/V/` (26 versioned tables)
  - `models/L_E/` (3 L-E events)
  - `models/L_W/` (6 L-W workflows)
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

### API operation contract

The API exposes **Consulta, Inserción, Actualización** per resource.
Actualización is bi-temporal: close the current row (`vigente_hasta = NOW()`,
`estado = 'inactivo'`) AND insert a new row with the new state.

**NO ESTÁ PERMITIDA LA ELIMINACIÓN DE NINGÚN REGISTRO.** The API has no
`DELETE` operation. Conceptual deletion is modeled as:

- a new row in a workflow table (`anulaciones`, `reimpresion_ticket`,
  `reclamos`, `alerta`)
- a compensating row (`factura_pagos.tipo_movimiento = 'reverso'`)
- a derived view state (`V_FACTURA_ESTADO`, `V_INGRESO_ESTADO`,
  `V_FE_ESTADO_DIAN`)

Enforced at three levels: **API** (no endpoint), **ORM** (close+insert
helpers, no hard delete on `[V]`/`[A]`), **DB** (`REVOKE DELETE` on `[A]` +
`BEFORE UPDATE OR DELETE` trigger). All three are required — defense in
depth. See [Architectural Principles](#3-api-operation-contract--consulta-inserción-actualización-no-delete)
for the full contract and rationale.

### Frontend

- Multi-branch selector in `web_admin`; branch-pinned in `web_sucursal`
- `preliminar` badge on `web_sucursal` until `SyncBackEvent` arrives
- `reimpresion_ticket` disabled until `SyncBackEvent`
- axe-core CI gate must pass for WCAG 2.1 AA

## Workflow (SDD)

1. Preflight collected (current session for `create-49-table-apis`): pace=`auto`, artifact=`hybrid` (OpenSpec+Engram), delivery=`auto-chain`, chain=`gitflow`, budget=`800 lines` per PR
2. Every change follows: explore → propose → spec → design → tasks → apply → verify → archive
3. Each phase persisted to BOTH OpenSpec (`openspec/changes/{name}/`) AND Engram (topic_key `sdd/{name}/{phase}`)
4. In interactive mode: orchestrator shows result + asks before next phase
5. Chained PRs recommended when forecast >800 LOC; `gitflow` model — PRs land on `dev`, releases to `main`

## Risk Registers (project-wide)

| Risk | Mitigation |
|---|---|
| Hash-chain break on partial sync | per-branch monotonic seq in `datos` JSON; cloud verifier |
| REVOKE/trigger drift on branch boot | entrypoint runs `pg_trigger` check; abort non-zero |
| Outbox bypass on direct `[A]` writes | `AFTER INSERT` trigger into `sync_queue` (PR5 task) |
| Tenant scope leak in admin JWT | `X-Sucursal-Context` enforced against `sucursales_permitidas` on every call |
| Pairing-token replay | single-use, 24h TTL, rate-limited |
| DIAN `consecutivo_actual` race | atomic UPDATE in cloud only; branches read via sync |
| **Physical DELETE attempted** at any layer (intentional or feature shortcut) | API has no DELETE endpoint; ORM uses close+insert helpers for `[V]`/`[L]`; `REVOKE DELETE` + `BEFORE UPDATE OR DELETE` trigger on `[A]` tables blocks DB-level — corrections must flow through workflow tables |
| `0001_initial_schema.py` is one big file | MERGED in PR1a (bootstrap-monorepo-foundation #2). Mitigation: `python openspec/scripts/check_schema_match.py` exits 0 verified the 49-table schema matches the ER 100% — tables, columns, UKs, FKs, REVOKE on 11 `[A]`, `_inmutable` triggers, `ls_session*` triggers, and the 8 `pg_partman` parents are all present. Future migrations stay in the <800-LOC budget per `config.yaml rules.tasks`. |
| **Physical DELETE attempted** at any layer (intentional or feature shortcut) | API has no DELETE endpoint; ORM uses close+insert helpers for `[V]`/`[L]`; `REVOKE DELETE` + `BEFORE UPDATE OR DELETE` trigger on `[A]` tables blocks DB-level — corrections must flow through workflow tables. CI gate: `python openspec/scripts/check_schema_match.py` exits 0 with REVOKE + trigger + 8 partman parents verified (per PR1 T-PR1-29). |
| Idempotency table `idempotency_keys` is the 50th table — out of scope for bootstrap. | Mitigation: PR7 ships migration `0002_add_idempotency_keys.py` with REVOKE + trigger in same script (per `config.yaml rules.tasks`). (Note: PR1a's `0001_initial_schema.py` already shipped the table; PR2's `0003_*` shipped the ORM + partial UK on `endpoint`. PR7 adds the application layer: `repo/idempotency.py::guard`/`store_response` + middleware integration.) |
| DIAN provider rate-limit (Factus allows N req/min) (LOW) | The Factus provider caps requests per minute. Mitigation: the dispatcher's `backoff_5xx` schedule (60s/300s/900s) absorbs transient throttling. If sustained 429s become routine, a token-bucket limiter (in `parkos_core/dian/cloud/rate_limiter.py`, follow-up PR) will queue dispatches before they hit the provider. The cloud-side verifier (PR10) flags `envio_dian.estado_dian='rechazado'` with motive prefix `rate:` for observability. |
| `tasks.md` spec drift from `modelo_datos_er.mmd` 4FN canon (HIGH) | ER.mmd is the immutable source of truth (lines 700-702: `cufe` / `reportado_dian` / `lifecycle` are DERIVED, not stored columns — 4FN + insert-only). Spec describes INTENT, ORM uses ER columns. PR11-01 (commit `bbd5bb4`) used `respuesta_proveedor` JSONB for DIAN outcome + dedicated `cufe` column instead of the assumed `motivo_rechazo` / `reportado_dian` columns. `alerta` uses existing `uuid_alerta_padre` (chain) + `uuid_arqueo` (reference) instead of the spec's `uuid_cadena_raiz` / `uuid_referencia`. Follow-up PR11c to migrate `fecha_retencion_hasta` onto the `EnvioDian` ORM (currently raw SQL UPDATE — works but not idiomatic). Rule: when spec and ER disagree, ER wins; update the spec to reflect ER. |

## Active Change

- `bootstrap-monorepo-foundation` (Phase 1) — 6 chained PRs planned, feature-branch-chain strategy, PR1 ready to launch
- See `openspec/changes/bootstrap-monorepo-foundation/` for proposal/specs/design/tasks
- See `openspec/_meta/roadmap.md` for the full system roadmap across all 9 phases