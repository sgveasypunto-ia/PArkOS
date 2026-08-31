# easypunto_parkos — Iteration Plan (Vertical Slicing)

> Each iteration is **atomic**: smallest possible end-to-end case that crosses
> ALL components (web_admin UI, web_sucursal UI, api_admin, api_sucursal,
> job_sync_cloud, job_sync_sucursal, DIAN dispatcher, DB). After IT-N, the
> system has a working feature in production, not a half-built layer.

## Why this beats the layer-based plan

| | Layer-based (rejected) | Vertical slicing (this plan) |
|---|---|---|
| Time-to-first-feature | After PR6 (all 6 layers done) | After IT-1 (first iteration) |
| Risk surface per PR | Wide (DB or API or sync alone) | Narrow (one feature, all components) |
| Review focus | "How does this layer fit with the others?" | "Does this case work end-to-end?" |
| Feedback loop | 6-PR cycle | 1-iteration cycle |
| Rollback granularity | Layer-level | Feature-level |
| DIAN/AUDIT exposure | Schema lands before any business logic (idle risk) | Schema lands, then immediate first use (real validation) |

## Constraints

- **Schema is foundational** — `0001_initial_schema.py` (45 tables + 11 REVOKE + 11 triggers + 8 `pg_partman` + hash-chain genesis + seed) lands in one PR with `size:exception`. Cannot split (single `alembic head` invariant).
- **JWT three issuers** must exist before IT-1 — the bootstrap builds the auth skeleton with `admin`, `operador`, `sync-agent` keys. IT-1 wires login endpoints + UI.
- **DIAN dispatcher** is cloud-only — branch imports of `parkos_core.dian.cloud` MUST fail (RED test enforces the boundary from the first iteration).
- **Hash-chain survival** — every iteration that writes to `log_transaccional` or `revocacion_factura` MUST verify `hash_anterior == prev.hash_actual` per `uuid_sucursal`.
- **AUDIT-FIRST DDL** — every iteration that touches `[A]` tables MUST ship REVOKE + trigger DDL in the same migration (`config.yaml` `rules.tasks`).

## Phases

### Phase 0 — Foundation Walking Skeleton

Two PRs that establish everything the iterations need without delivering any business feature.

#### PR1 — Foundation Skeleton (`size:exception`, ~800–1500 LOC)

Schema + infra + Docker + minimal parkos_core. After this PR the system boots end-to-end (cloud + branch + DB + Alembic), serves `/health`, and applies the full schema.

Tasks:

- [ ] F1.1 `backend/pyproject.toml` workspace + 5 service `pyproject.toml` stubs.
- [ ] F1.2 `Dockerfile` multi-stage (`BUILD_TARGET` + `SERVICE_NAME`).
- [ ] F1.3 `docker-compose.cloud.yml` + `docker-compose.branch.yml` + `.env.*.example`.
- [ ] F1.4 `infra/postgres/init/{01_roles,02_extensions}.sql`.
- [ ] F1.5 `infra/docker/entrypoint.sh` skeleton (wait-for-postgres + `${VAR:?}` precheck + `alembic upgrade head` + REVOKE verifier + `exec "$@"`).
- [ ] F1.6 `backend/packages/parkos_core/migrations/{env.py,script.py.mako,versions/0001_initial_schema.py}` — **45 tables + 11 REVOKE + 11 triggers + 2 session guards + 8 `pg_partman.create_parent` + hash-chain genesis + idempotent seed**. Pre-flight `alembic upgrade --sql` per `config.yaml` `rules.tasks`.
- [ ] F1.7 RED test for entrypoint (shell commands + executable-file classification from threat matrix).
- [ ] F1.8 RED test for `0001_initial_schema.py`: drop a trigger → restart container → entrypoint exits non-zero.
- [ ] F1.9 `parkos_core` skeleton: `db/{base,engine,tenancy}.py`, `auth/{passwords.py, jwt_three_issuers.py stub}`, `models/{V,L_E,L_W,L_S,A}/` stubs (one class per table with `__tablename__` + PK so Alembic sees `target_metadata`).
- [ ] F1.10 `parkos_core/api_admin/routers/health.py` + `parkos_core/api_sucursal/routers/health.py` (`GET /health`).
- [ ] F1.11 `api_admin_main/__main__.py` + `api_sucursal_main/__main__.py` (uvicorn wiring).
- [ ] F1.12 Verify: `docker compose -f docker-compose.branch.yml up -d` boots; `curl /health` returns 200; `\dt prod.*` count = 45; `pg_trigger` check passes.

#### PR2 — Building Blocks (~400 LOC)

DIAN stubs + sync stubs + JWT three issuers production-ready + conflict policy shell + apps/ui-kit.

- [ ] F2.1 `parkos_core/dian/common/{numeration.py, provisional.py, sync_back.py}` — types only, no behavior yet.
- [ ] F2.2 `parkos_core/dian/cloud/{builder.py, dispatcher.py stub, atomic_next_consecutivo.py}` — `atomic_next_consecutivo` works (real `SELECT FOR UPDATE`); `dispatcher` is a stub returning `numero_oficial=None`.
- [ ] F2.3 `parkos_core/dian/branch/__init__.py` — thin wrapper calling `provisional_number("PRE", uuid)`. RED test: `from parkos_core.dian.cloud.dian_dispatcher import dispatch` from a branch code path MUST raise `ImportError`.
- [ ] F2.4 `parkos_core/sync/{queue_processor.py stub, conflict_policy.py stub, pairing.py, sync_back.py}` — function signatures only.
- [ ] F2.5 `parkos_core/auth/jwt_three_issuers.py` — production: three RS256 keypairs, `issue_token(scope, claims, ttl)`, `verify_token(token, audience)` enforcing audience matches scope. Cross-audience → 401.
- [ ] F2.6 `infra/sync_policy.yaml` — per-class defaults skeleton (manual/append/cloud_wins/local_wins per table class).
- [ ] F2.7 `apps/{package.json, tsconfig.base.json, ui-kit/}` — npm workspaces + ui-kit with shadcn config + tokens.css.
- [ ] F2.8 RED test JWT three-issuers: admin→api_sucursal/login → 401; operador→api_admin/login → 401; sync_agent→any→401.
- [ ] F2.9 Verify: `pytest tests/integration/test_jwt_cross_audience.py` passes; `uv sync --package api_admin` resolves clean.

### Phase 1 — Authentication & Tenancy (vertical)

#### IT-1 — Login end-to-end (atomic, ~400 LOC)

After IT-1: an admin user can log in to `web_admin`; a branch operator can log in to `web_sucursal`; both use real JWT; tokens are scoped correctly; branch users were synced from cloud via `job_sync_cloud`.

Components touched:

- **DB**: `usuarios`, `usuarios_sucursal`, `permisos_usuario`, `login` `[L-S]`.
- **API admin**: `POST /auth/login` issues `admin` JWT; `POST /usuarios` creates; `GET /usuarios` lists; `POST /usuarios/{uuid}/sucursales` assigns branch.
- **API sucursal**: `POST /auth/login` issues `operador` JWT; `GET /usuarios-sucursal` lists assigned users (read-only projection of synced data).
- **Sync cloud**: `job_sync_cloud` polls `prod.usuarios` + `prod.usuarios_sucursal` for changed rows, pushes to each assigned branch via `sync_queue` → POST `/sync/push`.
- **Sync sucursal**: `job_sync_sucursal` polls the cloud inbox endpoint, upserts `usuarios` + `usuarios_sucursal` locally; updates `sync_status='synced'`.
- **web_admin**: `LoginForm` (shadcn `form` + `input` + `button`); `useAuth` zustand store; route guard `RequireAdmin`; redirects to `/dashboard` on success.
- **web_sucursal**: `LoginForm` (same ui-kit component); `useAuth` zustand store; route guard `RequireOperador`; redirects to `/pos` on success.

Tasks:

- [ ] IT-1.1 RED test login end-to-end (admin): create user via direct DB seed; `POST /auth/login` returns admin JWT; `useAuth.login()` succeeds; `/dashboard` renders.
- [ ] IT-1.2 `api_admin/routers/auth.py` `POST /auth/login` — bcrypt verify + `issue_token(scope='admin', claims, ttl=8h)`. Returns `{access_token, expires_at, role}`.
- [ ] IT-1.3 `api_sucursal/routers/auth.py` `POST /auth/login` — same shape, scope=`operador`, claims include `sucursales_permitidas=[uuid_sucursal]` (single branch).
- [ ] IT-1.4 `api_admin/routers/usuarios.py` `POST /usuarios` + `GET /usuarios` — admin-only; bcrypt hash via `parkos_core.auth.passwords`. Required fields: `nombre, apellido, cedula, email, rol, password`.
- [ ] IT-1.5 `api_admin/routers/usuarios_sucursal.py` `POST /usuarios/{uuid}/sucursales` + `DELETE /usuarios/{uuid}/sucursales/{sucursal_uuid}` — admin-only.
- [ ] IT-1.6 `parkos_core/sync/queue_processor.py::enqueue_user_for_branch(user_uuid, sucursal_uuid)` — INSERT into local `prod.sync_queue` with `datos={user_payload}` + `tabla='usuarios'`. Idempotency key = `f"{user_uuid}:{sucursal_uuid}"`.
- [ ] IT-1.7 `job_sync_cloud/__main__.py::poll_usuarios` — every N seconds: SELECT users whose `sync_status='pending'` AND have at least one `usuarios_sucursal` row; for each, POST to branch `/sync/push` (JWT = sync_agent); on success update `sync_status='synced'`.
- [ ] IT-1.8 `api_admin/routers/sync.py::POST /sync/push` — sync_agent-auth; validates `hash_anterior == last.log_transaccional.hash_actual`; INSERT `usuarios` + `usuarios_sucursal` in branch DB (called cloud→branch). Returns `200 {accepted: <count>}`.
- [ ] IT-1.9 `job_sync_sucursal/__main__.py::drain_inbox` — every N seconds: GET `/sync/pull?since=<last_sync_ts>` from cloud; for each batch, INSERT `log_transaccional` row + UPSERT `usuarios` locally.
- [ ] IT-1.10 `apps/web_admin/src/routes/login.tsx` + `LoginForm.tsx` (shadcn form) + `useAuth.ts` zustand + `RequireAdmin.tsx` route guard.
- [ ] IT-1.11 `apps/web_sucursal/src/routes/login.tsx` + same form (shared from ui-kit) + `useAuth.ts` + `RequireOperador.tsx`.
- [ ] IT-1.12 RED test sync roundtrip: create user in cloud; after N seconds user appears in branch `prod.usuarios`; `login` from `web_sucursal` works with that user.
- [ ] IT-1.13 RED test cross-audience: admin token used at `api_sucursal /auth/login` → 401.
- [ ] IT-1.14 Verify: `npm run -ws build` passes; `tsc --noEmit` clean; axe-core smoke test of both login pages passes WCAG AA.

#### IT-2 — Sucursales CRUD + pairing branch (atomic, ~350 LOC)

After IT-2: admin creates a new branch in `web_admin`; admin issues a one-time pairing token; the branch operator enters it in `web_sucursal` setup; the branch receives a long-lived `sync_agent` JWT.

Components touched:

- **DB**: `sucursal`, `tipo_sucursal`, `documentos`, `login` `[L-S]` (pairing event), `usuarios_sucursal`.
- **API admin**: `POST /sucursales`, `GET /sucursales`, `POST /sucursales/{uuid}/pairing-token`, `GET /sucursales/{uuid}/documentos`.
- **API sucursal**: `POST /sync/pair` (consumes token; returns long-lived sync_agent JWT).
- **Sync cloud**: parametrization push of new `sucursal` to all branches (so admin can see cross-branch).
- **Sync sucursal**: parametrization pull — branch receives the new `sucursal` record AND stores the long-lived JWT locally.
- **web_admin**: `SucursalesList`, `SucursalForm`, `PairingTokenDialog` (shows token + copy button + expiry).
- **web_sucursal**: `PairingWizard` (first-boot flow: enter token → receive JWT → persist).

Tasks:

- [ ] IT-2.1 RED test: admin `POST /sucursales` creates branch; `POST /sync/pair` with the returned token + branch UUID returns sync_agent JWT; `parkos_core.dian.cloud.dian_dispatcher` is NOT importable from branch.
- [ ] IT-2.2 `api_admin/routers/sucursales.py` CRUD.
- [ ] IT-2.3 `api_admin/routers/sucursales.py::POST /{uuid}/pairing-token` — generates 24h-TTL single-use token, stores hashed in `prod.usuarios_sucursal.metadata` or a new `prod.pairing_tokens` table; returns plaintext once.
- [ ] IT-2.4 `api_sucursal/routers/sync.py::POST /sync/pair` — validates token (not expired, not used), issues `sync_agent` JWT with `claims.uuid_sucursal=<branch>`, `ttl=90 days`. Persists JWT to `/var/secrets/parkos-sync-jwt` mode 0600.
- [ ] IT-2.5 `job_sync_cloud::poll_sucursales_parametrization` — every N seconds: SELECT changed `sucursal` rows; push to ALL branches.
- [ ] IT-2.6 `job_sync_sucursal::persist_sucursal_parametrization` — receives and UPSERTs locally.
- [ ] IT-2.7 `web_admin` `SucursalesList` + `SucursalForm` + `PairingTokenDialog`.
- [ ] IT-2.8 `web_sucursal` `PairingWizard` — first-boot only; checks for persisted JWT; if absent, shows wizard.
- [ ] IT-2.9 RED test pairing-token replay: after first use, second `POST /sync/pair` with same token → 410 Gone.
- [ ] IT-2.10 Verify: e2e `docker compose up` of cloud + branch; admin creates branch; `web_sucursal` PairingWizard accepts token; `job_sync_*` logs show first parametrization pull.

### Phase 2 — Core Operations (vertical)

#### IT-3 — Ingreso de vehículo (atomic, ~300 LOC)

After IT-3: branch operator records a vehicle entry; the `ingreso` event propagates to cloud; admin can see all entries for the branch.

Components touched:

- **DB**: `ingreso` `[L-E]`, `vehiculos` `[V]`, `tipos_vehiculo` (catalog sync), `subscripciones_cliente` (lookup).
- **API sucursal**: `POST /ingresos` (operator), `GET /ingresos?estado=activo`.
- **API admin**: `GET /ingresos?uuid_sucursal=<uuid>`.
- **Sync cloud**: receives `ingreso` events; appends to `prod.ingreso`; writes `log_transaccional` with hash chain.
- **Sync sucursal**: parametrization pull for `tipos_vehiculo` + `subscripciones_cliente` (so operator can pick from dropdown).
- **web_sucursal**: `IngresoForm` (placa input + tipo vehiculo select + subscripcion optional select).
- **web_admin**: `IngresosList` filtered by `uuid_sucursal`.

Tasks:

- [ ] IT-3.1 RED test ingreso end-to-end: operator submits `POST /ingresos`; row in `prod.ingreso` (branch); after sync, row in `prod.ingreso` (cloud); admin GET sees it.
- [ ] IT-3.2 `api_sucursal/routers/ingresos.py::POST /ingresos` — operator JWT required; INSERT into `prod.ingreso`; enqueue in `sync_queue`.
- [ ] IT-3.3 `api_sucursal/routers/ingresos.py::GET /ingresos?estado=activo` — operator scoped to branch.
- [ ] IT-3.4 `api_admin/routers/ingresos.py::GET /ingresos?uuid_sucursal=<uuid>` — admin scope; multi-branch.
- [ ] IT-3.5 `job_sync_sucursal::drain_outbox_ingresos` — push `prod.ingreso` rows where `sync_status='pending'`.
- [ ] IT-3.6 `api_admin/routers/sync.py::POST /sync/push` (extended) — handles `tabla='ingreso'`; validates hash chain; INSERTs into `prod.ingreso`; INSERTs `log_transaccional` with `hash_anterior=last.hash_actual`.
- [ ] IT-3.7 `job_sync_cloud::drain_inbox_ingresos` — receives and applies.
- [ ] IT-3.8 Parametrization pull: `tipos_vehiculo` + `subscripciones_cliente` (catalog sync).
- [ ] IT-3.9 `web_sucursal` `IngresoForm` (shadcn form + react-hook-form + Zod validation).
- [ ] IT-3.10 `web_admin` `IngresosList` (filter by `uuid_sucursal`).
- [ ] IT-3.11 RED test hash-chain integrity: ingest 100 ingresos; cloud verifier (cron) confirms chain unbroken.
- [ ] IT-3.12 Verify: full flow e2e in `docker compose`.

#### IT-4 — Salida de vehículo (atomic, ~250 LOC)

After IT-4: branch operator records a vehicle exit; the `salidas` `[A]` row propagates to cloud; `ingreso.estado` derives `cerrado` from the existence of the matching `salidas` row.

Components:

- **DB**: `salidas` `[A]` (REVOKE-enforced), `ingreso` (state derived).
- **API sucursal**: `POST /salidas` — operator; references `uuid_ingreso`.
- **API admin**: `GET /salidas?uuid_sucursal=<uuid>`.
- **Sync**: bidirectional, same shape as IT-3 but for `salidas`.
- **web_sucursal**: `SalidaForm` (lookup by placa or ingreso UUID).
- **web_admin**: `SalidasList`.

Tasks:

- [ ] IT-4.1 RED test salida end-to-end.
- [ ] IT-4.2 `api_sucursal/routers/salidas.py::POST /salidas` — INSERT into `prod.salidas`; enqueue.
- [ ] IT-4.3 Sync both directions for `salidas` (same pattern as IT-3.5/3.6/3.7).
- [ ] IT-4.4 `api_admin/routers/salidas.py::GET /salidas`.
- [ ] IT-4.5 `web_sucursal` `SalidaForm` + placa/UUID lookup.
- [ ] IT-4.6 `web_admin` `SalidasList`.
- [ ] IT-4.7 RED test AUDIT-FIRST: branch app attempts `UPDATE prod.salidas` → raises AUDIT_FIRST_INMUTABLE (REVOKE enforcement).
- [ ] IT-4.8 Verify: e2e in `docker compose`.

#### IT-5 — Facturación (cloud-first + sync back, atomic, ~600 LOC)

After IT-5: branch operator charges a customer; online mode prints with real DIAN number, offline mode prints with `numero_temporal` and sync-back updates the UI.

Components:

- **DB**: `facturas` `[L-E]`, `factura_detalle` `[A]`, `factura_pagos` `[A]`, `factura_electronica` `[L-E]` (cloud-only writes), `empresa.consecutivo_actual` (atomic, cloud-only).
- **API admin**: `POST /facturas/procesar` — cloud-first; consumes `consecutivo_actual`, creates `factura_electronica`, queues for DIAN.
- **API sucursal**: `POST /facturas` (online → calls cloud /facturas/procesar; offline → writes business factura with `numero_temporal` + enqueues); `GET /facturas/{uuid}/numero-oficial` (returns real number once SyncBackEvent arrives).
- **Sync cloud**: receives business facturas from branches; processes them; emits SyncBackEvent.
- **dian_dispatcher**: cloud-only worker; pulls queued e-facturas; sends to DIAN provider; updates `factura_electronica.estado`; emits SyncBackEvent.
- **Sync sucursal**: pull mode for SyncBackEvent (per design `dian_numbers.mode: pull`).
- **web_sucursal**: `FacturacionForm` (cliente, items, pagos); `preliminar` badge component; reimpresion button (disabled until sync-back).
- **web_admin**: `FacturasList` (cross-branch view); `FacturaDetail` (shows e-factura + DIAN response).

Tasks:

- [ ] IT-5.1 RED test online facturación: operator submits; cloud `/facturas/procesar` returns real number; branch prints with real.
- [ ] IT-5.2 RED test offline facturación: cloud mocked to 500; operator still completes sale with `numero_temporal`; sync-back later updates the UI.
- [ ] IT-5.3 `api_sucursal/routers/facturas.py::POST /facturas` — try cloud first (online mode); on failure or timeout, fallback to `numero_temporal` + enqueue.
- [ ] IT-5.4 `api_admin/routers/facturas.py::POST /facturas/procesar` — `atomic_next_consecutivo(empresa_id)` + INSERT `factura_electronica` + enqueue for `dian_dispatcher`.
- [ ] IT-5.5 `job_sync_sucursal::drain_outbox_facturas` — push `prod.facturas` (business) where `sync_status='pending'`.
- [ ] IT-5.6 `api_admin/routers/sync.py::POST /sync/push` — handles `tabla='facturas'`; creates cloud `prod.facturas` + `prod.factura_detalle` + `prod.factura_pagos`; emits SyncBackEvent placeholder.
- [ ] IT-5.7 `parkos_core/dian/cloud/dispatcher.py::process_pending_invoices` — pulls queued e-facturas, sends to DIAN provider stub (real provider in future change), updates `factura_electronica.estado`.
- [ ] IT-5.8 `parkos_core/sync/sync_back.py::emit_sync_back_event(factura_uuid, numero_oficial)` — writes `prod.sync_back_events` (new table) with timestamp.
- [ ] IT-5.9 `api_admin/routers/sync.py::GET /sync/dian-numbers?since=<ts>` — pull mode; returns pending SyncBackEvent for the calling branch.
- [ ] IT-5.10 `job_sync_sucursal::poll_dian_numbers` — every 30s; receives real numbers; UPSERTs `prod.facturas.uuid_factura_electronica` + `numero_oficial`.
- [ ] IT-5.11 `api_sucursal/routers/facturas.py::GET /facturas/{uuid}/numero-oficial`.
- [ ] IT-5.12 `workers/dian_dispatcher/entrypoint.sh` — shell out to `infra/docker/entrypoint.sh` then `exec python -m parkos_core.workers.dian_dispatcher`.
- [ ] IT-5.13 `docker-compose.cloud.yml` adds `workers-dian_dispatcher` service. RED test (already in F2): `docker compose -f docker-compose.branch.yml config | grep -c dian_dispatcher` = 0.
- [ ] IT-5.14 `web_sucursal` `FacturacionForm` (react-hook-form + Zod; cliente, items dynamic list, pagos split by medio_pago).
- [ ] IT-5.15 `web_sucursal` `PreliminarBadge` (display `numero_temporal`; flip to real when sync-back arrives — re-poll every 30s or via WebSocket placeholder).
- [ ] IT-5.16 `web_sucursal` `ReimpresionButton` (disabled until sync-back).
- [ ] IT-5.17 `web_admin` `FacturasList` + `FacturaDetail` (cross-branch filter).
- [ ] IT-5.18 Verify: e2e online + offline flows.

### Phase 3 — Workflows (vertical)

#### IT-6 — Anulación de ingreso (workflow chain, ~250 LOC)

Components: `anulaciones` `[L-W]`, `ingreso` (state derivation), `login` `[L-S]`.

- [ ] IT-6.1 RED test workflow chain: operator requests anulación → admin approves → admin executes → 3 rows in `prod.anulaciones` chained by `uuid_anulacion_padre`.
- [ ] IT-6.2 `api_sucursal/routers/anulaciones.py::POST /anulaciones` (estado='solicitada').
- [ ] IT-6.3 `api_admin/routers/anulaciones.py::POST /anulaciones/{uuid}/aprobar` (creates new row chained to original, estado='aprobada').
- [ ] IT-6.4 `api_admin/routers/anulaciones.py::POST /anulaciones/{uuid}/ejecutar` (creates new row chained, estado='ejecutada').
- [ ] IT-6.5 Sync: bidirectional for `anulaciones`.
- [ ] IT-6.6 `web_sucursal` `AnularIngresoButton` + `AnulacionDialog`.
- [ ] IT-6.7 `web_admin` `AnulacionesPendientesList` + `AprobarDialog` + `EjecutarDialog`.

#### IT-7 — Alertas operacionales (workflow + sync_failure detection, ~300 LOC)

Components: `alerta` `[L-W]`, `arqueo`, `sync_log`, `caja`.

- [ ] IT-7.1 RED test: arqueo with diferencia > tolerancia → alerta `diferencia_arqueo` created.
- [ ] IT-7.2 RED test: cloud detects no `sync_log` from branch in 24h → alerta `branch_offline`.
- [ ] IT-7.3 `api_sucursal/routers/arqueos.py::POST /arqueos` — operator; computes diferencia; if > tolerancia, INSERTs `prod.alerta` chain `abierta`.
- [ ] IT-7.4 `parkos_core/sync/sync_monitor.py::detect_offline_branches` — cron in cloud; queries `sync_log` for branches with no entry in 24h; INSERTs `alerta tipo_alerta='branch_offline'`.
- [ ] IT-7.5 Sync: bidirectional for `alerta`.
- [ ] IT-7.6 `web_admin` `AlertasList` + workflow dialogs (`en_revision`, `resuelta`).
- [ ] IT-7.7 `web_sucursal` (operator-visible) `MisAlertasList` (only for their branch).

#### IT-8 — Reclamos (workflow chain, ~200 LOC)

Components: `reclamos` `[L-W]`, FK polimórfica.

- [ ] IT-8.1 RED test: operator presents claim on `ingreso`; admin marks `en_revision`; admin marks `resuelto`; 3 rows chained.
- [ ] IT-8.2 CRUD endpoints (admin + branch) for `reclamos` with FK polimórfica (`tipo_reclamable` + `uuid_reclamable`).
- [ ] IT-8.3 Sync: bidirectional.
- [ ] IT-8.4 `web_sucursal` `PresentarReclamoDialog`.
- [ ] IT-8.5 `web_admin` `ReclamosList` + workflow dialogs.

#### IT-9 — Reimpresión de ticket (workflow, ~200 LOC)

Components: `reimpresion_ticket` `[L-W]`, `factura` (gate via SyncBackEvent).

- [ ] IT-9.1 RED test: reimpresion blocked before SyncBackEvent; enabled after.
- [ ] IT-9.2 `api_sucursal/routers/reimpresion.py::POST /reimpresion-ticket` — guards SyncBackEvent.
- [ ] IT-9.3 Sync: bidirectional.
- [ ] IT-9.4 `web_sucursal` `ReimpresionButton` (gate via `GET /facturas/{uuid}/numero-oficial`).
- [ ] IT-9.5 `web_admin` `ReimpresionesList`.

### Phase 4 — Customer Features (vertical)

#### IT-10 — Subscripciones + vehículos (atomic, ~400 LOC)

Components: `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`.

- [ ] IT-10.1 RED test: admin creates subscripcion + 2 vehículos for B2C cliente; branch operator sees them after sync; operator assigns vehicles on ingreso.
- [ ] IT-10.2 Admin CRUD: `clientes`, `subscripciones_cliente`, `vehiculos`.
- [ ] IT-10.3 Sync: parametrization pull for branches.
- [ ] IT-10.4 `web_admin` `ClientesList` + `SubscripcionForm` + `VehiculoForm`.
- [ ] IT-10.5 `web_sucursal` `ClientesList` (read-only) + lookup on `IngresoForm` (already in IT-3).

### Phase 5 — Admin Ops (vertical)

#### IT-11 — Reportes admin (cross-branch aggregations, ~350 LOC)

Components: read-only aggregations over `facturas`, `arqueo`, `alerta`, `log_transaccional`.

- [ ] IT-11.1 RED test: admin GETs `/reportes/facturacion-diaria?fecha=2026-08-30` returns aggregated totals per branch.
- [ ] IT-11.2 `api_admin/routers/reportes.py` — endpoints for daily/weekly/monthly aggregations.
- [ ] IT-11.3 `web_admin` `ReportesDashboard` with charts (recharts).
- [ ] IT-11.4 Verify: queries use indexed scan; performance within budget.

### Phase 6 — Audit Hardening (vertical)

#### IT-12 — Hash-chain verifier + audit reports (atomic, ~300 LOC)

Components: `log_transaccional`, `revocacion_factura` (both with hash chains), `workers/hash_chain_verifier`.

- [ ] IT-12.1 RED test: tamper one `log_transaccional` row's `hash_actual` → verifier emits alert.
- [ ] IT-12.2 `workers/hash_chain_verifier/entrypoint.sh` + Python verifier.
- [ ] IT-12.3 Nightly cron-style verification.
- [ ] IT-12.4 `web_admin` `AuditDashboard` (read-only view of `log_transaccional` filterable by sucursal/tabla/usuario).

## Iteration Sizing Guidelines

- **Atomic** = one PR. Revertible in isolation.
- **<400 LOC** preferred (per review budget). Exceptions require `size:exception` ratification at plan time.
- **All components touched** in every iteration: at minimum one component in each of {UI admin, UI sucursal, API admin, API sucursal, sync, DB}.
- **RED test first, GREEN, REFACTOR** for each task that touches `[A]` tables or security boundaries.
- **No `Co-Authored-By` or AI attribution** in commit messages.

## Cross-cutting Refactors (after each phase)

- After Phase 0: extract ui-kit primitives used twice or more.
- After Phase 1: extract sync error recovery patterns.
- After Phase 2: consolidate hash-chain verification across all writes.
- After Phase 3: extract workflow state machine from `anulaciones` to `parkos_core.workflow`.
- After Phase 4: consolidate read-only aggregations behind a single SQL helper.

## Open Questions Surfaced

These get ratified at the first iteration that needs them; default values shown:

- (a) **Preliminar-number UX format** → `PRE-<8-char-uuid>`. Ratify in IT-5.15.
- (b) **Sync-back transport (DIAN numbers)** → pull mode every 30s. Ratify in IT-5.9.
- (c) **`reimpresion_ticket` blocking (API + PWA)** → both layers gate on `GET /facturas/{uuid}/numero-oficial`. Ratify in IT-9.
- (d) **WebSocket vs polling** → polling for all MVP iterations. WS in v2.
- (e) **DIAN provider** → stub in MVP; real adapter (Factus or another provider) is a separate change.
- (f) **Multi-country support** → deferred; model supports it parametrically but not implemented.