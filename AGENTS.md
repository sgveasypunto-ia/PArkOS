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

## Dev Credentials (LOCAL DEV ONLY)

These credentials exist in the local dev database for end-to-end testing.
**Never use them against staging or production environments.**

| Role | Email | Password | Use case |
|------|-------|----------|----------|
| Branch operator | `operador@parkos.local` | `Pass1234word` | Login from `web_sucursal`, post ingresos / salidas / arqueos |

**WARNING**: password is plaintext in this repo. Compromise of this file =
compromise of the dev DB. Rotate by re-running the local seed (`backend/scripts/`).
The email TLD `.local` is intentionally permitted by
`parkos_core/schemas/_email.py::_parkos_email_lenient` (RFC 6762 mDNS reserved)
so the bootstrap login flow works against Pydantic's strict default validator.

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
- `factura_electronica` and `revocacion_factura` are **emitted at the branch** and replicated `branch_to_cloud`; the cloud is the only egress point to the DIAN provider (`envio_dian`), which is cloud-only.
- **Invoice numbering is branch-local**: `consecutivo` is assigned at the branch inside its own `resolucion_facturacion` range (`rango_desde`/`rango_hasta`); uniqueness comes from UK `(uuid_resolucion_facturacion, consecutivo)`. `empresa` has no `consecutivo_actual` column (removed in the 4NF pass).
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
- **Two clocks over the wire (unchanged by design — Carril B fix, obs #18)**:
  - **Valid time** (`vigente_desde`/`vigente_hasta`/`estado` on `[V]` rows): set at the ORIGIN, travels intact, and the receiver applies it verbatim — `identity_reconciler.forward` preserves `vigente_desde`, `close_and_insert` closes the previous row at the SAME boundary the new version opens (no gap/overlap), and `sync_cloud._VERSIONED_ONLY_METADATA_KEYS = {vigente_hasta, estado}` so `vigente_desde` is never stripped on push. Re-stamping the open timestamp with the receiver's `now()` corrupted reconciliation under a backed-up queue (later origin versions wrongly classified `historical`, old version stayed open — inverted/duplicate state downstream).
  - **Transaction time** (`created_at`/`created_by`): NEVER crosses the wire in either direction (stripped by `_QUEUE_METADATA_KEYS` on push and `_PULL_WIRE_METADATA_KEYS` on pull); each node stamps its own receipt time. Naive-UTC convention (`DateTime(timezone=False)`, both nodes), so an observed offset between nodes is queue residence + receiver re-stamp, not clock skew — intentional.
- Hash-chain survival: cloud preserves branch chain verbatim, only extends with cloud-originated rows
- HTTP polling only (MVP); WebSocket deferred to v2

### DIAN

- 100% centralized in cloud admin
- The branch emits and numbers locally, online or offline, with no behavioural difference; the cloud forwards to the provider asynchronously and the outcome returns via `envio_dian`. Reprint is never gated on a cloud round-trip.
- The cloud validates the branch-assigned `consecutivo` against the resolution's authorized range and forwards the document to the DIAN provider (`envio_dian`, cloud-only); `cufe` and `estado` return to the branch through the ordinary `envio_dian` `cloud_to_branch` catalog entry.

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
- The document is final at emission. What may be pending is the DIAN acknowledgement, which is a status indicator on the document, not a gate on reprinting.
- axe-core CI gate must pass for WCAG 2.1 AA

## Workflow (SDD)

1. Preflight collected (current session for `create-49-table-apis`): pace=`auto`, artifact=`hybrid` (OpenSpec+Engram), delivery=`auto-chain`, chain=`gitflow`, budget=`800 lines` per PR
2. Every change follows: explore → propose → spec → design → tasks → apply → verify → archive
3. Each phase persisted to BOTH OpenSpec (`openspec/changes/{name}/`) AND Engram (topic_key `sdd/{name}/{phase}`)
4. In interactive mode: orchestrator shows result + asks before next phase
5. Chained PRs recommended when forecast >800 LOC; `gitflow` model — PRs land on `dev`, releases to `main`

## Operational Timeouts (HARD RULE — applies to every shell command)

Windows PowerShell 5.1 + this repo's toolchain has several processes that
**silently hang and never return** (e.g. `pnpm install` over workspace deps,
`vite` foreground, `docker compose logs -f`, `npm install` with sandbox
limitations). Every bash command MUST have an explicit `timeout` parameter
and an explicit failure handling rule. Default timeout policy:

| Command type | Default timeout | Reasoning |
|---|---|---|
| `Get-ChildItem`, `Get-Process`, `Test-Path`, `Get-Content` (≤1MB) | **15 s** | Filesystem ops; should be instant |
| `git status`, `git log`, `git diff`, `git branch` | **15 s** | Repo ops; should be instant |
| `Invoke-WebRequest`, `curl` to known-good endpoints | **15 s** | HTTP calls; should be instant |
| `npm install`, `pnpm install` in workspace root | **300 s** | First-time install may take 1-5 min |
| `pnpm add`, `pnpm install` in sub-workspace | **120 s** | Sub-install should be quick |
| `vite` foreground / `npm run dev` foreground | **20 s** | Just to verify it boots; abort and use detached for runtime |
| `docker ps`, `docker logs <container>` | **15 s** | Container introspection |
| `docker compose up`, `docker build` | **600 s** | Image build may take minutes |
| `uv run pytest`, `alembic upgrade head` | **300 s** | DB ops may be slow |
| `eslint`, `tsc --noEmit`, `vitest run` | **120 s** | Static analysis should be quick |
| Read, Glob, Grep | **30 s** | Tool calls; if it hangs, narrow the query |
| Sub-agent Task launch | **600 s** | Long-running delegation |

### Rules

1. **Always pass `timeout` explicitly** to the `bash` tool. The shell tool
   defaults to 120000 ms (2 min) which is too long for "verify this works" ops.
2. **Detached / background processes**: NEVER run `vite`, `npm run dev`,
   `docker logs -f`, `pnpm install`, or any server/foreground process with a
   long timeout. Use `Start-Process -WindowStyle Hidden -RedirectStandardOutput
   ...` + `Start-Sleep -Seconds N` + `Test-NetConnection -Port ...` to verify
   boot in <15 s, then return. Use `Get-Process` / `Stop-Process -Id` to
   manage.
3. **Hangs**: If a command times out, the shell tool returns with partial
   output. NEVER retry blindly. Diagnose first: `Get-Process` to see if the
   process is alive, `Test-NetConnection` for ports, read `*.log` files for
   error context. Then choose the next step (kill process, fix config,
   try alternative command).
4. **Cancellation**: A hung `bash` call must NOT block the user-visible
   response. When timeout fires, surface the partial state to the user
   in ≤1 sentence and continue or stop, never silently retry.
5. **Workaround for sandbox F.6 limitations** (npm 11.16.0 + PowerShell 5.1):
   - Use `pnpm` (always available at `C:\Users\mccra\AppData\Roaming\npm\pnpm.ps1`)
     instead of `npm install` when workspaces are involved.
   - Use `cmd /c mklink /J <link> <target>` for directory junctions (no
     admin required) instead of `New-Item -ItemType SymbolicLink`.
   - Use `Start-Process -WindowStyle Hidden` to launch dev servers as
     detached processes; verify with `Test-NetConnection -Port`.
6. **Per-action delegation is allowed** for installs and process launches
   when the orchestration loop would otherwise hang waiting for output.
   Delegate to a fresh `general` sub-agent with a `timeout` budget and
   require structured return.

## Gitflow Estricto (workflow obligatorio)

### Ramas

| Rama | Propósito | Creada desde | Mergea a | Regla |
|---|---|---|---|---|
| `main` | Producción. Solo recibe merges de `release/*`. | `release/*` | nunca mergea hacia atrás | NUNCA commit directo, NUNCA push directo (proteger en GitHub con branch protection: require PR + 1 review + status checks) |
| `dev` | Integración. Recibe PRs/merges de `feature/*` y `fix/*`. | `main` | NUNCA mergea hacia `main` (eso es solo via release) | PRs feature → dev. Fast-forward `--ff-only` cuando sea posible |
| `feature/<HU-id>-<slug>` | Trabajo nuevo (HU del plan). | `dev` | `dev` (vía PR o merge directo con squash) | Borrar después de merge. Nombre: `feature/hu-f4-1-deteccion-tipo-vehiculo` |
| `fix/<HU-id>-<slug>` | Bugfix o cleanup. | `dev` | `dev` | Borrar después de merge |
| `release/<version>` | Candidato a producción. | `dev` | `main` (producción) + `dev` (re-sync) | Tag en main post-merge. Borrar después |

### Naming convention

- **Feature branches**: `feature/<hu-id>-<slug-kebab-case>` — ejemplo: `feature/hu-f4-1-deteccion-tipo-vehiculo`, `feature/fase-3-electron-scaffold`
- **Fix branches**: `fix/<hu-id>-<slug>` — ejemplo: `fix/hu-f3-3-cleanup-ts-strict`
- **Release branches**: `release/vX.Y.Z` — ejemplo: `release/v0.2.0`
- **NO usar prefijos alternativos**: `feat/` → renombrar a `feature/`. Hotfixes → `fix/`.

### Conventional Commits (obligatorio)

Formato: `<type>(<scope>): <description>`

**Types permitidos:**
- `feat` — nueva funcionalidad
- `fix` — bug fix
- `chore` — tooling, deps, refactor no funcional
- `docs` — solo documentación
- `test` — solo tests
- `refactor` — reescritura sin cambio de comportamiento
- `perf` — mejora de performance

**Scopes del proyecto:** `caja`, `operacion`, `facturacion`, `auth`, `suscripciones`, `sync`, `reimpresion`, `apps`, `backend`, `infra`, `sdd`

**Description**: imperativo presente, lowercase, sin punto final, ≤72 caracteres.

**Body**: explicar WHY (no WHAT — el diff ya lo muestra). Wrap a 72 columnas.

**Footer**: `Refs: HU-F4.1` para referenciar historias; `BREAKING CHANGE:` para incompatibilidades.

**PROHIBIDO**:
- `Co-authored-by: AI trailers` (no atribución a IA en commits — canon AGENTS.md)
- Mensajes vagos: `fix`, `update`, `changes`, `wip` (usar `chore:` con descripción específica)
- Mezcla de mayúsculas/minúsculas
- Mezcla de tipos en un commit (un commit = un concern)

### Workflow de feature (paso a paso)

```powershell
# 1. Sync con origin/dev
git fetch origin dev
git checkout dev
git -c user.name='Parkos Dev' -c user.email='dev@parkos.local' merge --ff-only origin/dev

# 2. Crear rama feature
git checkout -b feature/hu-f4-1-deteccion-tipo-vehiculo

# 3. Trabajar — NUNCA commits directos a dev
# 4. Push de la rama (trackearla)
git push -u origin feature/hu-f4-1-deteccion-tipo-vehiculo

# 5. PR via gh (si la rama está en GitHub) — F3.x requiere review de 1 persona
gh pr create --base dev --head feature/hu-f4-1-deteccion-tipo-vehiculo --title "feat(caja): ..." --body "..."

# 6. Después de merge a dev, borrar la rama
git branch -d feature/hu-f4-1-deteccion-tipo-vehiculo
git push origin --delete feature/hu-f4-1-deteccion-tipo-vehiculo
```

### Reglas duras

1. **NUNCA commit directo a `main`**. `main` solo recibe merges desde `release/*` (releases certificados).
2. **NUNCA commit directo a `dev`** sin pasar por una rama feature/fix. Excepción: housekeeping commits materializando REQ-OPS al spec canónico (estos SÍ pueden ir directo a dev porque son artefactos SDD, no código).
3. **SIEMPRE `--ff-only` merge a dev** cuando la rama feature es descendiente directo. Si no es descendiente directo (rebase upstream), usar `--no-ff` para preservar merge commit (preferible para trazabilidad SDD).
4. **SIEMPRE borrar la rama** después de merge a dev (local + remoto).
5. **SIEMPRE configurar author** antes del primer commit: `git -c user.name='Parkos Dev' -c user.email='dev@parkos.local' ...` — nunca usar IA como autor.
6. **NUNCA forzar push** (`--force`, `--force-with-lease`) sin consultar al usuario. Si hay conflictos, resolver localmente o rebase.
7. **SIEMPRE hacer `git fetch --prune origin`** antes de listar ramas remotas (evita mostrar ramas ya borradas en GitHub).
8. **SIEMPRE cerrar la sesión con merge a `dev`** (override usuario 2026-09-17). Cada ajuste de desarrollo — feature, bugfix, refactor, scaffolding, artefacto SDD, incluso housekeeping — debe terminar con el orchestrator ejecutando `git merge --no-ff feature/<hu-id>-<slug>` (o `--ff-only` si la feature es descendiente directo de `dev`) sobre `dev`, resolviendo conflictos en el momento, seguido de `git push origin dev`, **antes de declarar la sesión cerrada**. Los PRs que abrió cada feature siguen siendo artefactos de trazabilidad; GitHub los cierra automáticamente cuando `dev` los alcanza. Esta regla es **no-negociable**: NO dejar trabajo en una feature branch local esperando merge manual via GitHub UI. La excepción pre-existente "housekeeping commits materializando REQ-OPS al spec canónico pueden ir directo a dev" se mantiene solo para micro-cambios de docs/SDD que no justifican una rama; cualquier cambio con código va con rama + merge-to-dev al cierre.

### Git config helper (ejecutar una vez por máquina)

```powershell
git config --global user.name 'Parkos Dev'
git config --global user.email 'dev@parkos.local'
git config --global init.defaultBranch main
git config --global push.autoSetupRemote true   # 'git push' crea upstream automático
git config --global pull.ff only                 # solo pull si es fast-forward
git config --global rerere.enabled true          # reuse recorded resolution en rebase
```

### Branch protection (configurar en GitHub repo settings → Branches)

- **`main`**: Require pull request before merging (1 approval), require status checks (CI), require linear history (no merge commits), restrict push access (solo release branches).
- **`dev`**: Require pull request before merging (1 approval), allow squash/rebase merge, allow delete (rama feature se borra después de merge).

### Post-merge: invalidar Vite cache

Vite pre-bundlea deps en `.vite/`. Después de un merge, ese cache queda stale y errores 500 aleatorios aparecen en imports nuevos. **SIEMPRE** después de un merge:

```powershell
Get-NetTCPConnection -LocalPort 5173 | Stop-Process -Id {$_.OwningProcess} -Force
cd apps\electron-sucursal
Start-Process -FilePath "..\node_modules\.bin\vite.CMD" -ArgumentList "--port","5173","--host","127.0.0.1","--force" -WindowStyle Hidden
```

El flag `--force` limpia `.vite/` deps cache. Esperado ~5s para que Vite vuelva a bootear.

### Comandos rápidos de cleanup

```powershell
# Listar ramas mergeadas a dev (candidatas a borrar)
git branch --merged dev | Where-Object { $_ -notmatch "^\*|main|dev" } | ForEach-Object { $_.Trim().TrimStart('*').Trim() }

# Borrar todas las mergeadas locales
git branch --merged dev | Where-Object { $_ -notmatch "^\*|main|dev" } | ForEach-Object { git branch -d $_.Trim().TrimStart('*').Trim() }

# Borrar una rama mergeada del remoto
git push origin --delete <branch-name>

# Fetch + prune de referencias remotas borradas en GitHub
git fetch --prune origin
```


### Anti-patterns (NEVER DO)

- ❌ `vite` / `npm run dev` / `pnpm install` foreground with 600 s timeout
  hoping it finishes — it WILL hang and burn the budget silently.
- ❌ `pnpm install` with `--no-frozen-lockfile` AND `--force` from the
  workspace root — known to hang indefinitely on this sandbox.
- ❌ Retry a timed-out command without diagnosing WHY it timed out.
- ❌ Use `npm install` directly in a subdir that has `workspace:*` deps —
  npm 11.16.0 throws EUNSUPPORTEDPROTOCOL.

### Example patterns

**Detached Vite dev server:**
```powershell
Start-Process -FilePath "..\node_modules\.bin\vite.CMD" `
  -ArgumentList "--port","5173","--host","127.0.0.1" `
  -RedirectStandardOutput "$env:TEMP\vite-out.log" `
  -RedirectStandardError "$env:TEMP\vite-err.log" `
  -WindowStyle Hidden -PassThru | Select-Object Id
Start-Sleep -Seconds 4
Test-NetConnection -ComputerName "127.0.0.1" -Port 5173 -InformationLevel Quiet
```

**Kill a hung process:**
```powershell
Get-NetTCPConnection -LocalPort 5173 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess | ForEach-Object {
    Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
  }
```

**Diagnose a hang:**
```powershell
Get-Process -Id <pid> | Select-Object Id, ProcessName, StartTime, CPU
Get-Content "$env:TEMP\<process>-err.log" -Tail 50
```

| Risk | Mitigation |
|---|---|
| Hash-chain break on partial sync | per-branch monotonic seq in `datos` JSON; cloud verifier |
| REVOKE/trigger drift on branch boot | entrypoint runs `pg_trigger` check; abort non-zero |
| Outbox bypass on direct `[A]` writes | `AFTER INSERT` trigger into `sync_queue` (PR5 task) |
| Tenant scope leak in admin JWT | `X-Sucursal-Context` enforced against `sucursales_permitidas` on every call |
| Pairing-token replay | single-use, 24h TTL, rate-limited |
| DIAN `consecutivo` collision | one resolution per branch with a disjoint authorized range; UK `(uuid_resolucion_facturacion, consecutivo)`; the cloud rejects a document whose `consecutivo` falls outside the resolution range, and range exhaustion raises an `alerta` |
| **Physical DELETE attempted** at any layer (intentional or feature shortcut) | API has no DELETE endpoint; ORM uses close+insert helpers for `[V]`/`[L]`; `REVOKE DELETE` + `BEFORE UPDATE OR DELETE` trigger on `[A]` tables blocks DB-level — corrections must flow through workflow tables |
| `0001_initial_schema.py` is one big file | MERGED in PR1a (bootstrap-monorepo-foundation #2). Mitigation: `python openspec/scripts/check_schema_match.py` exits 0 verified the 49-table schema matches the ER 100% — tables, columns, UKs, FKs, REVOKE on 11 `[A]`, `_inmutable` triggers, `ls_session*` triggers, and the 8 `pg_partman` parents are all present. Future migrations stay in the <800-LOC budget per `config.yaml rules.tasks`. |
| **Physical DELETE attempted** at any layer (intentional or feature shortcut) | API has no DELETE endpoint; ORM uses close+insert helpers for `[V]`/`[L]`; `REVOKE DELETE` + `BEFORE UPDATE OR DELETE` trigger on `[A]` tables blocks DB-level — corrections must flow through workflow tables. CI gate: `python openspec/scripts/check_schema_match.py` exits 0 with REVOKE + trigger + 8 partman parents verified (per PR1 T-PR1-29). |
| Idempotency table `idempotency_keys` is the 50th table — out of scope for bootstrap. | Mitigation: PR7 ships migration `0002_add_idempotency_keys.py` with REVOKE + trigger in same script (per `config.yaml rules.tasks`). (Note: PR1a's `0001_initial_schema.py` already shipped the table; PR2's `0003_*` shipped the ORM + partial UK on `endpoint`. PR7 adds the application layer: `repo/idempotency.py::guard`/`store_response` + middleware integration.) |
| DIAN provider rate-limit (Factus allows N req/min) (LOW) | The Factus provider caps requests per minute. Mitigation: the dispatcher's `backoff_5xx` schedule (60s/300s/900s) absorbs transient throttling. If sustained 429s become routine, a token-bucket limiter (in `parkos_core/dian/cloud/rate_limiter.py`, follow-up PR) will queue dispatches before they hit the provider. The cloud-side verifier (PR10) flags `envio_dian.estado_dian='rechazado'` with motive prefix `rate:` for observability. |
| `tasks.md` spec drift from `modelo_datos_er.mmd` 4FN canon (HIGH) | ER.mmd is the immutable source of truth (lines 700-702: `cufe` / `reportado_dian` / `lifecycle` are DERIVED, not stored columns — 4FN + insert-only). Spec describes INTENT, ORM uses ER columns. PR11-01 (commit `bbd5bb4`) used `respuesta_proveedor` JSONB for DIAN outcome + dedicated `cufe` column instead of the assumed `motivo_rechazo` / `reportado_dian` columns. `alerta` uses existing `uuid_alerta_padre` (chain) + `uuid_arqueo` (reference) instead of the spec's `uuid_cadena_raiz` / `uuid_referencia`. Follow-up PR11c to migrate `fecha_retencion_hasta` onto the `EnvioDian` ORM (currently raw SQL UPDATE — works but not idiomatic). Rule: when spec and ER disagree, ER wins; update the spec to reflect ER. |
| Pairing-token theft in transit (HIGH) | TLS 1.3 enforced between branch and cloud (container-level `nginx` termination + `PARKOS_TLS=required` runtime gate). `cli/pair.py` consumes `PARKOS_PAIRING_TOKEN` from env, exchanges for the `sync-agent-` JWT, then `os.environ.pop("PARKOS_PAIRING_TOKEN", None)` clears the plaintext from the process env. Only the SHA-256 hex digest (`pairing_token_hash`) is persisted — the plaintext is never written to disk or log. Cited §21.12 risk #19. |
| Per-branch misconfig of `PARKOS_SUCURSAL_UUID` (MED) | `parkos_core/runtime/env.py::load_config()` fail-fast at boot raises `MissingEnvError` (exit code `2` per §21.7 boundary-error contract) when the operator's UUID is missing or malformed. `parkos-core doctor` subcommand (`parkos_core/cli/doctor.py`) prints a structured diagnostic report (env presence + DB reachability + sync-token path writability). Cited §21.12 risk #23. |
| Pairing-token replay — CLOSED by PR8a/b/c per §21.3. Mitigation: `parkos_core/repo/pairing.py::consume_pairing_token` (SELECT ... FOR UPDATE SKIP LOCKED) + `parkos_core/api/rate_limit_pairing.py` (5/hour per admin) + `parkos_core/repo/revoked_sync_jwt.py::revoke_jwt` (admin revokes via `revoked_sync_jwts` INSERT). Verified by `tests/integration/test_pairing_flow.py` (9 scenarios). |
| Stale branch registry (HIGH) | PR9a ships `parkos_core/sync/auto_discovery.py` with `BranchCache(ttl=300s)` defaulting to DB-only source (prod.sync_log last 7d UNION prod.pairing_tokens last 30d). Optional external registry via `PARKOS_REGISTRY_URL` deferred to v2. Operational runbook: invalid cache TTL detected by stale `last_heartbeat_at > 30d` raises `alerta tipo_alerta='stale_branch_registry'` per daily `job_sync_cloud` sweep. |
| `job_sync_sucursal` silent death (MED) | PR9b ships `WorkerRunner` with `BACKOFF_5XX=[30,60,300]` and Docker HEALTHCHECK on `:9999/healthz`. After 3 consecutive failed healthchecks, Docker restarts the container. Worker exits 1 on unhandled exception → orchestrator restart loop. Periodic `journalctl -u job-sync-sucursal` alert via Parkos supervisor (PR10+). |
| Out-of-order sync arrivals (MED) | PR9a ships `ConflictResolver` that verifies per-row monotonic seq in `datos->>'seq'`. Mismatch returns `ApplyOutcome.ERROR` → caller retries. Cloud-side `job_sync_cloud.hash_chain_verifier_loop` (every `PARKOS_SYNC_VERIFY_INTERVAL_S`, default 3600s) catches silent forks and emits `alerta tipo_alerta='hash_chain_anomaly'`. Strict per-uuid_sucursal ordering enforced. Out-of-order writes downstream are caught at the chain verifier before divergence becomes silent. |
| Two parallel `job_sync_cloud` instances race on hash chain (MED) | PR9b ships docker-compose with `deploy.replicas: 1` for `job_sync_cloud`; HA with Postgres advisory locks per `uuid_sucursal` deferred to v2. `infra/deploy/docker-compose.cloud.yml` includes `deploy.replicas: 1` annotation. Verified by `docker compose config` showing single replica constraint. |
| `test_event_record::_make_session()` fragments under hash_chain integration (LOW) | PR11c wired `record_event(log_tx=True)` → `hash_chain.append` → `session.execute(stmt)`. The mock `_make_session()` did not stub `session.execute`, breaking 8 unit tests. Fix: extend mock to return a Result whose `.scalar_one_or_none()` is None (genesis hash path). Pattern documented in PR commits. Future ORM-side changes that add new session calls must update the mock. |

## Closed risks

- Risk #3 (Hash-chain break on partial sync) — CLOSED by PR9 + PR11c. Per-branch monotonic seq in `datos` JSON (PR9a) + cloud `job_sync_cloud.hash_chain_verifier_loop` (PR9b) + DIAN dispatcher extends chain per `uuid_sucursal` for branches (PR11c Bug 2). Test pinning: `backend/tests/unit/test_hash_chain.py::test_record_event_log_tx_extends_hash_chain` (PR11c) + `backend/tests/unit/test_sync_cloud_scenarios.py::test_hash_chain_verifier_catches_break` (PR9b).
- 2026-09-23 hash-chain anomalies (d4c7fc74 GLOBAL, 8e1e0488 branch) — CLOSED by migration `0058_hash_chain_causal_seq` + `fix/hash-chain-causal-seq` (commit `7234731`). `seq BIGINT` is allocated at INSERT time inside `prod.fn_extend_hash_chain()` under a per-chain advisory lock, so chain order is append order regardless of `created_at` (which is per-node, per-statement, and was being backdated/replicated). The trigger's genesis branch is hardened to refuse a genesis row over a live chain, closing the `d4c7fc74` fork. `repo.hash_chain.append` now stamps `seq` for both `log_transaccional` and `revocacion_factura` (the latter has no DB trigger, so Python is the only allocator). Historical damage is three anomaly points (GLOBAL seq 1, branch seq 21/22) at `seq < 50`; the cloud verifier is given `PARKOS_HASH_CHAIN_VERIFY_MIN_SEQ=50` (wired in `docker-compose.cloud.yml` on `job_sync_cloud`) which re-anchors the expected hash on the skipped prefix and validates everything from 50 on. A break planted past the watermark still fires (`test_min_seq_cannot_mask_a_break_after_the_watermark`). The three anomaly rows stay where they are — history is documented, not reshaped. Test pinning: `tests/unit/test_verify_chain.py::test_late_backdated_row_takes_head_seq_not_a_timestamp_slot`, `test_genesis_over_a_live_chain_is_rejected`, `test_min_seq_suppresses_a_known_historical_prefix`, `test_min_seq_cannot_mask_a_break_after_the_watermark`.
- Gap (test mocks) — CLOSED in `fix/close-gaps`. `test_event_record.py::_make_session()` extended to mock `session.execute()` returning a Result-like with `scalar_one_or_none() = None` (genesis path). 8 tests restored. `fix/close-gaps` PR #1 also fixes `jwt_issuer_guard.verify_jwt` → 401 on `JWTValidationError` (was leaking as 500).

## Git identity for sub-agent work

Sub-agent `general` runs set git config to `user.name=gentle-ai-sub-agent, user.email=sub-agent@local`. When `gh pr merge --squash` runs, GitHub auto-formats a `Co-authored-by: gentle-ai-sub-agent <sub-agent@local>` trailer into the squash commit message — violating the no-AI-attribution canon.

To suppress retroactively on a future release branch:
  git rebase -i origin/main --exec 'git commit --amend --no-edit --reset-author'

Or set neutral identity BEFORE merging future PRs:
  git config user.name "Parkos Dev"
  git config user.email "dev@parkos.local"

Cited as follow-up in Engram session #1353. The informational script `infra/scripts/clean_coauthored_trailers.sh` inventories affected commits in a range without rewriting history; the maintainer runs the rebase above on a release branch.

## Active Change

- `create-49-table-apis` (Phases 1-9) — 9 chained PRs (PR0 + PR1a/b/c + PR2-11), feature-branch-chain strategy for PRs 5/6/8/9/11, gitflow for the rest; all PRs merged to `dev`. PR9 (sync workers + Docker) COMPLETE in PR9c. PR11 (DIAN dispatcher) COMPLETE in PR11c. Remaining work documented in tasks.md + Engram backlog.
- `bootstrap-monorepo-foundation` (Phase 1) — 6 chained PRs planned, feature-branch-chain strategy, PR1 ready to launch
- See `openspec/changes/bootstrap-monorepo-foundation/` for proposal/specs/design/tasks
- See `openspec/_meta/roadmap.md` for the full system roadmap across all 9 phases