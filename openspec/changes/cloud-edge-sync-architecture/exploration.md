## Exploration: Cloud-Edge Sync Architecture

### Topic

Pressure-test the user's ratified cloud-edge topology and answer the architectural questions that gate the bootstrap phase: sync trigger, transport, conflict resolution, RBAC scope, sync auth/pairing, offline window, hash-chain survival, and tech-stack assumptions for the sync layer. Output is a set of mutually consistent baseline decisions that the proposal phase can build on without further clarification.

### Current State

**What exists**

- `E:\easypunto_parkos\modelo_datos_er.mmd` (1451 lines, Mermaid ER diagram) — canonical 45-table AUDIT-FIRST model.
- `openspec/PROJECT_CONTEXT.md` — assumptions documented; stack pending design confirmation.
- `openspec/config.yaml` — SDD rules (sync-queue / sync-conflict changes are flagged `risk: high`).
- Ratified topology (Engram #1217): `web_admin <-> api_admin <-> job_sync_cloud <-> many(job_sync_sucursal) <-> many(api_sucursal) <-> web_sucursal`.
- Two distinct web apps: `web_admin` (multi-tenant, 1 admin manages N branches; each branch has exactly 1 admin) and `web_sucursal` (per-branch, operadores do ingresos, salidas, facturación, suscripciones, apertura/cierre de turno y caja).

**What is encoded in the .mmd (sync-relevant)**

- `sync_queue` (A): persistent queue with backoff (estado, intentos, next_retry_at, ultimo_error). Operational UPDATE exception explicitly carved out — the model already accepts that `sync_queue` is mutable on operational fields. UUID FK polimórfica (`tabla` + `uuid_registro` + `datos` JSON snapshot).
- `sync_log` (A): per-cycle metrics (operaciones_enviadas, exitosas, fallidas, conflictos, duracion_ms). Drives the `branch_offline` detection (>24h without row → alerta).
- `sync_conflict` (A): snapshot of both versions + resolution policy (`cloud_wins | local_wins | append | manual`).
- `log_transaccional` (A): SHA256 chain per `uuid_sucursal` (`hash_anterior` → `hash_actual`). Source-of-truth for all audit.
- `revocacion_factura` (A): same SHA256 chain pattern; critical for DIAN probatory evidence.
- `alerta` (L-W): `tipo_alerta` includes `sync_failure` and `branch_offline`; workers close these by inserting a new `resuelta` row when sync resumes.

**What is NOT yet decided**

- Sync trigger model (NOTIFY vs poll vs CDC).
- Cloud ↔ branch transport (HTTP, WebSocket, broker).
- Worker runtime (FastAPI background task vs separate process vs Dramatiq/RQ).
- Hash-chain survival across sync (preserve verbatim vs cloud-extend vs split).
- Conflict policy defaults per table class.
- Sync auth/pairing flow specifics.
- Offline window policy (max days a branch can be offline).
- Tenant scope in JWT (single-branch operador vs multi-branch admin).
- Source-of-truth ownership for parametrization tables (empresa, sucursal, permisos).

### Affected Areas

**Already exists**

- `E:\easypunto_parkos\modelo_datos_er.mmd` — canonical model; no schema changes proposed, only behavior on top of it.

**Will be created by later phases (this exploration just constrains them)**

- `src/{api_admin,api_sucursal,job_sync_cloud,job_sync_sucursal}/` — four Python 3.13 services per the user's ratified topology.
- `migrations/versions/` — Alembic migrations; same DDL MUST apply to cloud AND branch DBs (REVOKE + triggers active on both).
- `apps/web_admin/`, `apps/web_sucursal/` — two PWAs (React 18 + Vite + TypeScript strict + shadcn/ui + Zustand + IndexedDB offline).
- `infra/compose/{cloud,branch}.yaml` — two Docker Compose stacks.
- `openspec/changes/cloud-edge-sync-architecture/specs/` — delta specs (one per subdomain: sync-flow, rbac, conflict, pairing, offline-policy).

### Approaches

#### 1. Sync trigger model

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. Postgres NOTIFY/LISTEN** (push) | Sub-second latency; native to Postgres; no polling overhead. | Fire-and-forget — events missed on worker restart unless backed by durable table; LISTEN holds a connection; payload cap (~8KB arg, large JSON must be hinted-id + read from sync_queue); order NOT guaranteed across channels. | Low |
| **B. Poll `sync_queue` on schedule** (pull) | Durable (queue is the truth); replay-friendly (worker can re-read missed rows); batch-friendly (single SELECT, many rows); idempotency keys in `datos` JSON prevent double-apply. | Latency = poll interval; needs careful indexing (`WHERE estado='pendiente' AND next_retry_at <= NOW()`); poll schedule must be tunable. | Low |
| **C. CDC via logical replication** (pgoutput / Debezium) | Captures all changes without app-side hooks; replay from LSN. | Heavy infra (Debezium + Kafka is overkill for parking-lot scale); requires an outbox table to avoid tx-commit vs replication-slot lag; harder to test locally. | High |

**Decision: B (poll).** The model already has `sync_queue` with explicit backoff state — polling is the natural fit. NOTIFY can be a future optimization for latency-sensitive rows. CDC is overkill for the parking-lot scale (a single branch is hundreds of ops/minute, not millions/sec).

#### 2. Cloud fan-out transport (`job_sync_cloud` ↔ `job_sync_sucursal`)

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. HTTP poll + push** | Stateless on both sides; trivially debuggable with curl; works through any HTTPS LB; simple retry; no broker to operate. | Poll cadence bounds latency; cloud has no push channel (must wait for branch poll); no built-in backpressure. | Low |
| **B. WebSocket / long-lived HTTP/2** | Push from cloud to branch; near-zero latency for parametrization; survives idle. | Stateful (sticky sessions, reconnect logic); harder to load-balance; reverse-proxy buffering can break WS; observability harder. | Medium |
| **C. Message broker** (Redis Pub/Sub or RabbitMQ) | Proper at-least-once delivery; built-in fan-out (RabbitMQ exchange per branch); consumer groups. | Another piece of infra to operate; persistence guarantees vary (Redis Pub/Sub is fire-and-forget; RabbitMQ is durable but adds complexity); broker becomes a single point of failure. | Medium-High |

**Decision: A (HTTP) as baseline.** Reserve B/C as a future scale-out option when branch count exceeds ~50. The 400-line review budget argues for the simplest credible design.

#### 3. Worker runtime (`job_sync_cloud`, `job_sync_sucursal`)

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. FastAPI background `asyncio` task** inside the same process as `api_admin` / `api_sucursal` | Simplest deploy (one container per role); shares SQLAlchemy engine; share tenancy middleware. | Web process lifecycle tied to worker; restart of web restarts worker; scaling web scales worker too (overprovisioned). | Low |
| **B. Separate Python process** (long-running), sharing the same codebase | Independent scaling; clean failure domain; can pause/restart independently; aligns with the user's topology (sync is its own role). | Two containers per side; needs careful share of models/schemas. | Medium |
| **C. Celery / Dramatiq / RQ** (task queue framework) | Retries, scheduling, observability built-in. | Heavyweight; not aligned with the user's topology (sync is its own long-running service, not a queue of short tasks). | Medium-High |

**Decision: B (separate process).** The user explicitly named `job_sync_cloud` and `job_sync_sucursal` as services; modeling them as separate processes matches the topology and avoids coupling worker lifecycle to API lifecycle.

#### 4. Hash-chain survival across sync (`log_transaccional`, `revocacion_factura`)

The .mmd defines hash chains partitioned by `uuid_sucursal`. The branch chain for branch-A is authoritative for events originating at branch-A. Cloud receives the rows via sync.

| Approach | Pros | Cons | Effort |
|----------|------|------|--------|
| **A. Cloud preserves the branch chain verbatim; cloud logs ONLY its own-originated events on the same `uuid_sucursal` chain** | DIAN evidence chain for branch-A events stays intact (same hash sequence as branch); branch and cloud agree on the chain for branch-originated rows; branch remains authoritative for those rows. | Cloud's chain extends the branch chain for admin actions, requiring careful "append-only on receipt, then add cloud-originated rows" ordering; worker must verify chain on receive. | Medium |
| **B. Cloud creates a parallel independent chain keyed by `uuid_sucursal`** | Branch chain never mutated by cloud; simpler invariant. | Two chains to verify; reconciliation between them is fuzzy; probatory evidence requires both; DIAN may not accept a split chain. | Medium-High |
| **C. Cloud is not authoritative on hash chains; only stores the branch-received rows; branch chain is the only chain** | Simple — cloud never inserts into hash-chained tables; branch chain stays the one truth. | Rules out cloud-admin-originated audit OR cloud-originated rows bypass the chain (DIAN risk). | Low |

**Decision: A (preserve branch chain + extend with cloud-originated rows).** Only model that respects DIAN evidence AND supports cloud-admin actions. Worker responsibilities: (1) on receive, verify `hash_anterior == hash_actual` of the previous branch row received; (2) on cloud-originated event, fetch current head of branch chain and append with proper `hash_anterior`.

#### 5. Conflict resolution policy defaults per table class

The model has 4 policies but no per-table default. Recommendation:

| Class | Tables | Default policy |
|-------|--------|----------------|
| `[V]` projection | usuarios, permisos, permisos_usuario, sucursal, tarifas_sucursal, etc. (24) | `manual` for admin-edit rows on operator-edit rows; `cloud_wins` for catalogs (impuestos, tipos_*) when branch has no local modification; `append` for client-side `[V]` like clientes (new version + cloud inserts at head, no overwrite). |
| `[L-E]` event | ingreso, facturas, factura_electronica, factura_pagos, factura_detalle, factura_impuestos, factura_otros_cobros, salidas | `append` — by definition events are append-only. No UPDATE conflict possible; uniqueness conflicts on natural keys resolve as `manual`. |
| `[L-W]` workflow | anulaciones, reclamos, alerta, reimpresion_ticket | `append` — each transition is a new row. Conflict only on UUID collision (impossible if UUIDs are server-side v4). |
| `[A]` source-of-truth | sync_queue, sync_log, sync_conflict, log_transaccional, revocacion_factura, caja, arqueo | `append` always. log_transaccional and revocacion_factura hash chains: `manual` if chain integrity breaks. |
| `[L-S]` session | login, sesion | `manual` — session lifecycle is concurrent on both sides. |

This needs an explicit per-table override config seeded at install. The simpler path is a YAML/JSON file in `infra/sync-policy.yaml`, NOT a new table.

#### 6. Tenant scope in JWT

- `web_admin` admin: JWT carries `tenant_id` and `sucursales_permitidas: [uuid...]` (multi-branch). UI shows branch selector. Each API call includes `X-Sucursal-Context: <uuid>` header (default = first permitted).
- `web_sucursal` operador: JWT carries `sucursal_id` (single). UI is branch-pinned; no selector. API tenancy middleware enforces single-branch scope; cross-branch request returns 403.
- Two distinct `rol` values on `usuarios.rol` (e.g., `admin`, `operador`, `supervisor`) plus `sucursales_permitidas` resolve from `usuarios_sucursal`.
- Single `usuarios` table; admin and operador are NOT separate tables. The .mmd is correct.

#### 7. Sync auth and pairing flow

- Branch `job_sync_sucursal` authenticates to `job_sync_cloud` via a long-lived JWT (`scope: sync_agent`, `uuid_sucursal`, `kid: branch-{N}`).
- Pairing flow:
  1. Admin creates the branch in `web_admin` → generates a one-time pairing token (UUID v4, TTL 24h, single-use).
  2. Branch operator enters the token in `web_sucursal` setup wizard → exchanges it via `POST /api/v1/sync/pair` for the long-lived JWT.
  3. JWT is persisted in branch's local secrets store (env var or mounted secret).
  4. JWT rotation: every 90 days (configurable) via `POST /api/v1/sync/rotate`; old JWT remains valid for 7 days for grace.
- Cloud authenticates `api_admin` and `api_sucursal` users with separate JWT issuers; the admin/operador JWT issuers are DIFFERENT from the sync JWT issuer. **Three key sets.** This is a non-obvious requirement: the admin and operador issuers could be one, but the sync agent issuer MUST be separate because its lifetime and audience differ.

#### 8. Offline window policy

- Default: branches may be offline up to **7 days** (configurable per `sucursal.offline_max_dias`, defaults to env var `EASYPUNTO_BRANCH_OFFLINE_MAX_DIAS`).
- After 24h without `sync_log` row → cloud inserts `alerta tipo_alerta='branch_offline' estado='abierta'`.
- After `offline_max_dias` → cloud escalates `alerta` to `en_revision` and pings admin (out-of-band notification; not in-scope here).
- After reconnection, worker inserts `alerta estado='resuelta'` row (L-W workflow chain).

#### 9. Source-of-truth ownership for parametrization tables

| Table | Owner | Branch behavior |
|-------|-------|-----------------|
| `empresa` (V, singleton) | Cloud only | Read-only sync down to all branches |
| `sucursal` (V) | Cloud | Branches receive inserts/updates; branches cannot mutate (sealed at DB level — only cloud's `rol_app` can UPDATE) |
| `usuarios` (V) | Cloud for admin users; Branch for operadores | Conflict policy: `append` (branch creates operador; cloud propagates new version) |
| `permisos`, `permisos_usuario` (V) | Cloud | Branches receive; branch cannot mutate |
| `clientes` (V) | Branch (created by operador in `web_sucursal`) | Propagated up to cloud (admin sees all clients in `web_admin`) |
| `tarifas_sucursal`, `cantidad_vehiculos_sucursal` (V) | Branch (admin per-branch configures via `web_admin` for that branch) | Cloud stores mirror |
| All `[A]` and `[L]` tables | Branch (originated) | Cloud receives as source-of-truth mirror |

The interesting case is `usuarios`: when a branch operator is created via `web_admin`, the row must arrive at the branch BEFORE the operator can log in via `web_sucursal`. Sync MUST be ordered: parametrization (users, permissions) MUST be applied before any operator authentication.

### Recommendation

Adopt the following baseline (all gates the proposal phase must respect):

1. **Sync trigger**: poll on `sync_queue` (interval default 30s, tunable per branch).
2. **Transport**: HTTP POST/GET between `job_sync_sucursal` and `job_sync_cloud`, both directions, JWT-secured.
3. **Worker runtime**: separate long-running Python processes (`job_sync_cloud` and `job_sync_sucursal`) in the same monorepo, sharing the SQLAlchemy models and Alembic migrations.
4. **Hash chain**: cloud preserves branch chain verbatim and extends with its own-originated rows on the same `uuid_sucursal` chain.
5. **Conflict policy**: per-class defaults as enumerated in §5, with `manual` as a fallback that requires admin resolution. Stored in `infra/sync-policy.yaml`, NOT a new table.
6. **JWT scope**: admin token carries `sucursales_permitidas: []`; operador token carries `sucursal_id`; sync token is a third issuer with `scope: sync_agent`. **Three JWT issuers.**
7. **Pairing**: one-time pairing token → long-lived JWT (90-day rotation, 7-day grace).
8. **Offline window**: default 7 days per branch (configurable); `alerta tipo_alerta='branch_offline'` at 24h without `sync_log`.
9. **Source of truth**: `empresa` (cloud-only), `permisos` (cloud), `sucursal` (cloud), `usuarios` (joint; admin cloud, operadores branch), operational tables (branch).

These nine choices are mutually consistent and answer every sub-question the orchestrator raised. They are deliberately conservative: HTTP polling + durable queue is well-understood; CDC/broker upgrades are future work.

### Risks

- **Hash-chain break on partial sync**: if cloud receives out-of-order `log_transaccional` rows, the chain verification on receive will fail. Mitigation: include a per-branch monotonic sequence in `datos` JSON; cloud worker applies strictly in-order.
- **REVOKE/trigger drift on branch boot**: if `alembic upgrade head` fails on a branch, sync workers may run with un-restricted `rol_app` and bypass append-only. Mitigation: a `alembic check` + REVOKE verification in the worker startup script.
- **Sync_queue recursion illusion**: if anyone tries to sync `sync_queue` rows themselves, infinite loop. Mitigation: the worker treats `tabla='sync_queue'` as a no-op locally and never enqueues it.
- **Outbox bypass**: if `api_sucursal` writes directly to `[A]` tables without inserting into `sync_queue`, the row never reaches cloud. Mitigation: trigger on INSERT of `[A]` tables (`AFTER INSERT FOR EACH ROW`) inserts into `sync_queue` in the same TX; OR a Postgres LISTEN/NOTIFY in addition to polling for low-latency hint.
- **Tenant scope in JWT leak**: admin JWT with `sucursales_permitidas=[A,B]` could be used to access branch-C if the tenancy middleware does not enforce `X-Sucursal-Context ∈ permitidas`. Mitigation: middleware MUST check on every API call.
- **Pairing token replay**: one-time token could be replayed if intercepted. Mitigation: single-use semantics enforced server-side; short TTL; rate-limit `/sync/pair` endpoint.
- **Cloud-admin actions audit**: when admin in `web_admin` approves an anulación on behalf of a branch, the cloud must append to the branch's `log_transaccional` chain with proper `hash_anterior`. Mitigation: explicit "cloud-originated" event flag and chain-extension routine.
- **N branches scaling**: HTTP poll cadence × N branches × 30s interval is fine up to ~100 branches; beyond that, broker/WS becomes mandatory.
- **Empty project**: the proposal phase still depends on the monorepo skeleton (`bootstrap-monorepo-foundation`); if that comes AFTER this exploration, design must defer.

### Ready for Proposal

**Yes** — but the proposal phase should ask the user to ratify the following micro-decisions before locking the proposal:

1. **Sync poll interval**: 30s default vs 60s (lower latency vs load).
2. **JWT TTL**: admin/operador 1h access + 7d refresh; sync 90d rotation + 7d grace.
3. **Offline window default**: 7 days (configurable per branch).
4. **Conflict policy defaults**: confirm the per-class defaults enumerated in §5, especially `manual` for `[V]` cross-tenant edits.
5. **Hash-chain cloud-originated events**: ratify the "extend on receive" model (cloud receives branch chain verbatim, appends cloud-originated rows at head).
6. **Broker introduction**: defer to future (Y/N).
7. **Ordering of changes**: this change is best sequenced AFTER `bootstrap-monorepo-foundation` (which establishes the four-service skeleton + Alembic baseline); alternatively, both can be combined into a single mega-change if the 400-line budget allows.