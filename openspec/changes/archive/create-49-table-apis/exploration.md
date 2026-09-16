# Exploration: create-49-table-apis

## Goal

Expose every table in `modelo_datos_er.mmd` (canonical 49-table AUDIT-FIRST
model) through the API surface — one consistent Pydantic-v2 schema + FastAPI
router per enforcement class (`[V]` projection, `[L-E]` event, `[L-W]`
workflow, `[L-S]` session, `[A]` append-only) — honoring the three
architectural principles ratified this session (Audit-First / Bi-Temporal /
C/Q/U-no-D), the multi-tenant cloud-edge topology, the JWT three-issuer
model, and the DIAN-only boundary (cloud owns `factura_electronica`,
`revocacion_factura`, `envio_dian`, `validacion_evento`). Schema is
established by `bootstrap-monorepo-foundation` (active change); this change
layers API endpoints and ORM helpers on top, in ~7-8 chained PRs to `dev`
(gitflow), each ≤800 LOC.

## Scope

**In scope**:

- One Pydantic-v2 schema file per table (`parkos_core/schemas/<table>.py`):
  `Read`, `Create`, `Update` (only when the operation exists), `Filter` for
  list endpoints.
- One ORM helper module per enforcement class with the patterns enumerated
  below (`current_version`, `history`, `close_and_insert`,
  `append_workflow_transition`, `close_session_with_log`, `append_event`).
- One FastAPI router per domain group, mounted under `/api/v1` with the
  correct JWT scope guard (`admin-`, `operador-`, `sync-agent-`).
- Tenant scoping middleware that enforces `X-Sucursal-Context` against the
  JWT's `sucursales_permitidas` (admin) or `sucursal_id` (operador) on
  every read/write.
- Hash-chain helpers for `log_transaccional` and `revocacion_factura`
  (compute `hash_anterior` / `hash_actual` server-side; never accept
  client-supplied chain values).
- Sync-queue enqueue helper invoked from any API endpoint that mutates a
  replicated table (post-DB-commit; mirrors the `AFTER INSERT` trigger
  proposed in the cloud-edge sync exploration).
- Idempotency-key support on every POST (UUID v4, 24h TTL in
  `sync_queue`/`log_transaccional`).
- OpenAPI artifact committed for client codegen (PWA side may consume).

**Out of scope**:

- Schema changes (DDL) — owned by `bootstrap-monorepo-foundation`
  (`0001_initial_schema.py`).
- Sync workers (`job_sync_*`) — owned by bootstrap PR5.
- DIAN dispatcher / provider integration — separate change.
- PWA UI changes — owned by future per-iteration changes.
- BFF (deferred to v2).
- WebSocket sync (deferred to v2).
- Bulk-CSV import endpoints — separate change (catalog seeding).
- File-upload multipart for `documentos` (base64 inline is enough for MVP).

## Entity inventory

### By domain

| # | Domain | Tables | Count | Owner (cloud / branch / shared) |
|---|---|---|---:|---|
| 1 | **Auth & RBAC** | `usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal`, `login` | 5 | Shared (usuarios/permisos cloud-authored, replicated down; login branch-originated) |
| 2 | **Empresa & Sucursal** | `empresa`, `sucursal`, `tipo_sucursal`, `documentos`, `resolucion_facturacion` | 5 | Cloud-owned (branches read-only) |
| 3 | **Catalogs** (global) | `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios` | 8 | Cloud-authored, replicated down |
| 4 | **Per-branch config** | `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `configuracion_tolerancias`, `configuracion_seguridad` | 4 | Cloud-admin writes per-branch override; branch reads |
| 5 | **Customer** | `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos` | 5 | Branch-originated, replicated up |
| 6 | **Operación** | `ingreso`, `salidas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `facturas`, `factura_electronica`, `revocacion_factura` | 9 | Branch-originated (factura_electronica + revocacion_factura cloud-written) |
| 7 | **Caja & Arqueo** | `sesion`, `caja`, `arqueo` | 3 | Branch-originated |
| 8 | **Workflows** | `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `envio_dian`, `validacion_evento` | 6 | Branch-originated except envio_dian + validacion_evento (cloud-only) |
| 9 | **Sync & Audit** | `sync_queue`, `sync_conflict`, `sync_log`, `log_transaccional` | 4 | Local-only (sync_queue / sync_log / sync_conflict); log_transaccional cloud-mirrored |
| | **TOTAL** | | **49** | |

### By enforcement class

| Class | Count | Tables |
|---|---:|---|
| `[V]` bi-temporal projection | **26** | `usuarios`, `permisos`, `permisos_usuario`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios`, `configuracion_tolerancias`, `configuracion_seguridad`, `empresa`, `resolucion_facturacion`, `sucursal`, `usuarios_sucursal`, `documentos`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos` |
| `[L-E]` lifecycle event | **3** | `ingreso`, `facturas`, `factura_electronica` |
| `[L-W]` workflow | **6** | `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `envio_dian`, `validacion_evento` |
| `[L-S]` session/cycle | **2** | `login`, `sesion` |
| `[A]` source-of-truth | **12** | `salidas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `revocacion_factura`, `caja`, `arqueo`, `sync_queue`, `sync_conflict`, `sync_log`, `log_transaccional` |
| **TOTAL** | **49** | |

### By tenant scope

| Scope | Tables |
|---|---|
| **Cloud-only** (DIAN compliance; branches NEVER write, read-only mirror if any) | `factura_electronica`, `revocacion_factura`, `envio_dian`, `validacion_evento`, `empresa` (logical — only cloud-admin mutates; branches read) |
| **Branch-originated** (replicated up to cloud) | `ingreso`, `salidas`, `facturas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `caja`, `arqueo`, `sesion`, `login`, `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `configuracion_tolerancias`, `configuracion_seguridad`, `documentos`, `log_transaccional` |
| **Global / catalog** (cloud-authored, replicated down, no branch mutation) | `permisos`, `permisos_usuario`, `usuarios_sucursal`, `usuarios`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios`, `resolucion_facturacion`, `sucursal` |
| **Local-only infra** (no propagation) | `sync_queue`, `sync_conflict`, `sync_log` |

> Note: `usuarios` straddles the catalog/branch-originated boundary — admin
> users are cloud-authored; operadores are branch-created. The API must
> enforce this at the JWT level (admin token required for admin-create;
> operador token may self-register with admin pre-approval flow — open
> question).

## Shared patterns identified

### `[V]` bi-temporal CRUD helper — `parkos_core/repo/versioned.py`

For every `[V]` table the API surface is:

- **Create** (INSERT): new row with `vigente_desde = NOW()`, `vigente_hasta = NULL`, `estado = 'activo'`. The UK includes `vigente_desde`, so an existing key with `vigente_hasta IS NULL` may NOT exist for the same business key; the operation is a pure INSERT.
- **Update** (close + insert): the C/Q/U contract forbids `UPDATE` on `[V]` business state. The helper `close_and_insert(session, table, business_key, new_state, created_by)` performs:
  1. `UPDATE ... SET vigente_hasta = NOW(), estado = 'inactivo' WHERE UK = :bk AND vigente_hasta IS NULL` (this UPDATE is allowed because it's part of the close+insert pattern, NOT a state mutation in the audit sense — but the `[A]` REVOKE on `[V]` is NOT enforced; only on `[A]` tables).
  2. `INSERT INTO ... VALUES (..., vigente_desde = NOW(), vigente_hasta = NULL, estado = 'activo', created_by = :user)`.
  3. Both in the same SQLAlchemy 2.0 transaction with `await session.commit()` only after both succeed.
  4. On commit: enqueue a `log_transaccional` row with `accion='actualizar'`, `datos_anteriores` snapshot, `datos_nuevos` snapshot.
  5. The helper does NOT exist for `[A]` tables (REVOKE blocks both UPDATE and DELETE).
- **Read current**: `SELECT ... WHERE UK = :bk AND vigente_hasta IS NULL ORDER BY vigente_desde DESC LIMIT 1`.
- **Read history**: `SELECT ... WHERE UK = :bk ORDER BY vigente_desde DESC`.
- **Filter** (list endpoint): `WHERE estado = 'activo'` is the default; query params allow `vigente_desde >=`, `vigente_hasta <=`, `uuid_sucursal =` (only if the table has `uuid_sucursal`).
- **Pagination**: cursor-based on `(vigente_desde, uuid)` tuple (stable across inserts).

The helper takes the SQLAlchemy declarative class and the business-key
field list as parameters — one helper instance is registered per table at
module-load time via a decorator:

```python
@register_versioned(usuarios, business_keys=["cedula"])
class UsuariosRepo: ...
```

### `[L-W]` workflow transition helper — `parkos_core/repo/workflow.py`

Each workflow row carries `uuid_*_padre` (FK to the previous row in the
chain). The pattern is **append-only** — there is no UPDATE. The helper
`append_transition(session, table, parent_uuid, new_state, actor_uuid,
motivo)` performs:

1. If `parent_uuid IS NULL`: this is the **initial** row (e.g., `anulaciones` `estado='solicitada'`).
2. Otherwise: read the parent row and verify state-machine legality
   (`solicitada → aprobada → ejecutada` for `anulaciones`;
   `abierto → en_revision → resuelto | rechazado` for `reclamos`;
   `abierta → en_revision → resuelta` for `alerta`;
   `pendiente | enviado → aceptado | rechazado` for `envio_dian`;
   `cobrada → anulada` for `reimpresion_ticket`;
   `recibido → validado | observado | rechazado` for `validacion_evento`).
3. Insert new row with `uuid_*_padre = parent_uuid`, new `estado`, `timestamp_evento = NOW()`, `created_by = actor_uuid`.
4. On commit: enqueue `log_transaccional` (`accion='actualizar'`).
5. Read-current is `SELECT ... WHERE uuid_reclamo_inicial = ANY(chain) ORDER BY timestamp_evento DESC LIMIT 1` — but since the chain may branch on retries (`envio_dian` reintentos), the convention is "last row of the longest chain from any root" (open question on tie-break).

State machines per table (derived from the model comments; verify in
specs phase):

- `anulaciones`: `solicitada → aprobada → ejecutada` (3 rows minimum per successful cancel)
- `reclamos`: `abierto → en_revision → {resuelto | rechazado}` (rejected may branch from any state)
- `alerta`: `abierta → en_revision → resuelta` (rechazo may be modeled differently — open)
- `reimpresion_ticket`: `cobrada → anulada` (anulación is a new row pointing to the original via `uuid_reimpresion_padre`)
- `envio_dian`: `pendiente → enviado → {aceptado | rechazado}` (cloud-only; may loop pendiente → enviado on retries)
- `validacion_evento`: `recibido → {validado | observado | rechazado}` (cloud-only; admin-driven)

### `[L-S]` session lifecycle helper — `parkos_core/repo/session_cycle.py`

`login` and `sesion` are the only tables with an allowed UPDATE (state
close). The DB has a `BEFORE UPDATE` trigger that permits updates only on
`estado`, `timestamp_cierre`, `timestamp_evento`, `uuid_usuario_cierre`,
AND requires a `log_transaccional` row to exist in the same TX (enforced
via `RAISE EXCEPTION` if missing). The API helper wraps this:

- **Open session** (`sesion`): INSERT with `estado='abierta'`, `timestamp_apertura = NOW()`. Mirror in `login` with `estado='exitoso'`.
- **Close session** (`UPDATE` allowed): set `estado='cerrada'`, `timestamp_cierre = NOW()`, `uuid_usuario_cierre = :user`; same TX inserts the MANDATORY `log_transaccional` row. If the trigger detects no log row → 500 (defense in depth).
- **Failed login**: INSERT in `login` with `estado='fallido'`. Counter on `usuarios` is read from `login` history; bootstrap change exposes it.
- **Logout**: UPDATE `login` row setting `estado='cerrado'`, `timestamp_cierre = NOW()`; log row written in same TX.

### `[A]` append-only insert helper — `parkos_core/repo/append_only.py`

`[A]` tables have REVOKE UPDATE, DELETE from `rol_app` and a `BEFORE
UPDATE OR DELETE` trigger that RAISE EXCEPTIONs. The only operation is
INSERT. The helper `append_event(session, table, payload, created_by)`
performs:

1. `INSERT INTO ... VALUES (...)` (must NOT be `UPDATE` or `DELETE`).
2. On commit: enqueue `log_transaccional` if the table is part of the sync replication set (12 of 12 `[A]` are; `sync_queue` is local-only and excluded from the enqueue).
3. **Compensation pattern** (`factura_pagos.tipo_movimiento='reverso'`): insert a new row with `tipo_movimiento='reverso'`, `uuid_pago_revertido` pointing at the original. NEVER update the original. The view `V_FACTURA_PAGOS_NETOS` subtracts reversos.
4. For `sync_queue`: the operational UPDATE exception is honored — the helper exposes `mark_dispatched`, `mark_failed`, `schedule_retry` that perform UPDATE on `estado`, `intentos`, `next_retry_at`, `ultimo_error` only (the trigger permits these by trigger-function carve-out, but the API MUST NOT touch any other column).

### `[L-E]` immutable event helper — `parkos_core/repo/event.py`

`ingreso`, `facturas`, `factura_electronica` are append-only facts. No
UPDATE, no compensation row — corrections flow through `anulaciones` or
`revocacion_factura`. The helper `record_event(session, table, payload,
created_by)` performs:

1. INSERT (the business event).
2. On commit: enqueue `log_transaccional`.
3. **Derived state lives in views**: `V_INGRESO_ESTADO` (combines `ingreso` + `salidas NOT anulada` + `anulaciones ejecutadas`), `V_FACTURA_ESTADO` (combines `facturas` + `anulaciones ejecutadas`), `V_FE_ESTADO_DIAN` (combines `factura_electronica` + `envio_dian` + `revocacion_factura`), `V_RESOLUCION_CONSECUTIVO` (max `consecutivo` per `resolucion_facturacion`), `V_ARQUEO_DIFERENCIAS` (`esperado - reportado`).
4. For `factura_electronica`: cloud-only INSERT. Branches INSERT into `facturas` (internal) and the cloud-side helper (triggered by sync) mirrors into `factura_electronica` with the assigned `consecutivo`.

## Cross-cutting concerns

### Tenant scoping

- **Operador JWT** (`kid: operador-*`): single `sucursal_id`. Middleware enforces every query touches `uuid_sucursal = :sucursal_id`. Cross-branch requests → 403 `tenant_scope_violation`.
- **Admin JWT** (`kid: admin-*`): `sucursales_permitidas: [uuid, ...]`. Each request must include `X-Sucursal-Context: <uuid>` header; middleware validates `uuid ∈ sucursales_permitidas`. Missing header → 400 `missing_sucursal_context`. Mismatched → 403.
- **Sync JWT** (`kid: sync-agent-*`): `uuid_sucursal` and `scope: sync_agent`. ONLY the sync router is mounted for this scope. Operators and admins cannot use a sync-agent token and vice-versa — three issuers, hard separation.
- **Bypass**: `rol_admin_auditor` is the only role with `BYPASSRLS` for SELECT (audit reads). No write bypass.

### DIAN-only tables

`factura_electronica`, `revocacion_factura`, `envio_dian`, `validacion_evento`
exist ONLY in cloud DB. Branches have schema parity (DDL applied) but
NEVER write. Enforcement layers:

1. **API layer**: the routers for these tables are mounted in `api_admin` only; branch image cannot import them — bootstrap design asserts `branch import of dian.cloud.dian_dispatcher` raises `ImportError`; same boundary applies to the API routers.
2. **ORM layer**: branch's `parkos_core` exports `dian/cloud_router.py` only behind `try: import dian.cloud_router except ImportError: ...`. Branch process never reaches it.
3. **DB layer**: `revocacion_factura` and `factura_electronica` carry `hash_anterior`/`hash_actual`; the chain is cloud-owned and the API helper rejects writes from any actor other than `cloud_service_account`.

### Hash chain (`log_transaccional`, `revocacion_factura`)

- Server computes `hash_actual = sha256(json_canonical(payload) + hash_anterior)`. Client NEVER sends `hash_anterior` or `hash_actual`.
- Per-`uuid_sucursal` chain: helper reads `MAX(timestamp_evento)` row for the `uuid_sucursal`, takes its `hash_actual` as the new `hash_anterior`, computes the new `hash_actual`. Insert + UPDATE chain head in same TX.
- Cloud preserves branch chain verbatim; cloud-originated rows append at head of the same `uuid_sucursal` chain (per cloud-edge-sync-architecture decision §4).
- Chain break → 500 `hash_chain_integrity_violation`; the worker that triggered it logs a `sync_conflict` row (cloud-side) and surfaces an `alerta tipo_alerta='sync_failure'`.

### Audit triggers

The bootstrap change owns the DB-level triggers. The API must NOT bypass them; the helpers above assume they exist. Specifically:

- 12 `[A]` tables: `BEFORE UPDATE OR DELETE` → `RAISE EXCEPTION '<TABLE>_INMUTABLE'`. The API's append-only helper only INSERTs; any accidental UPDATE triggers the exception (defense in depth).
- 2 `[L-S]` tables: `BEFORE UPDATE` permits columns (`estado`, `timestamp_cierre`, `timestamp_evento`, `uuid_usuario_cierre`) ONLY if a `log_transaccional` row exists in the same TX (trigger reads `pg_stat_activity` or a CTE). The session helper satisfies this by inserting the log row first, then performing the UPDATE.
- 4 `[A]` DIAN tables (`factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`): REVOKE + trigger same as the other `[A]`.

### Sync triggers

Every write to a replicated `[A]` table triggers an `AFTER INSERT` that
enqueues in `sync_queue` (cloud-edge-sync §4 mitigation). The API does
NOT enqueue manually — the DB trigger does it. Exception: `sync_queue`
itself is local-only; the trigger explicitly filters `WHEN (TG_TABLE_NAME <> 'sync_queue')`.

For `[V]` and `[L-W]` writes, the API helper enqueues a `log_transaccional`
row in the same TX (which itself triggers a `sync_queue` insert via the
same DB trigger).

### JWT scope per endpoint class

| Endpoint class | JWT scope | Examples |
|---|---|---|
| Auth (`POST /auth/login`, `/auth/refresh`) | none (pre-auth) | `POST /api/v1/auth/login` |
| Admin parametrization (`POST /api/v1/usuarios`, `PUT /api/v1/sucursal/{uuid}/tarifas`) | `admin-*` | All `[V]` catalog and branch-config writes |
| Branch read (`GET /api/v1/ingresos?uuid_sucursal=X`) | `operador-*` (pinned) or `admin-*` + `X-Sucursal-Context` | All `[V]`/`[L-E]`/`[L-W]`/`[L-S]` reads scoped to a branch |
| Branch write (`POST /api/v1/ingresos`) | `operador-*` (pinned) | All branch-originated inserts |
| Workflow transition approval (`POST /api/v1/anulaciones/{uuid}/aprobar`) | `admin-*` only | `anulaciones.aprobar`, `anulaciones.ejecutar`; admin-only because they cross branch boundary |
| Cloud-only DIAN (`POST /api/v1/factura-electronica`, `/api/v1/envio-dian`) | `admin-*` + cloud-only deploy | `factura_electronica`, `revocacion_factura`, `envio_dian`, `validacion_evento` |
| Sync push/pull (`POST /api/v1/sync/push`, `/sync/pull`) | `sync-agent-*` only | Mounted on `api_admin` AND `api_sucursal` but only accepts sync-agent tokens; admin/operador → 401 |

## Dependency ordering

**Precondition**: `bootstrap-monorepo-foundation` MUST be merged first
(the schema, Alembic, JWT three-issuers, REVOKE/triggers, pg_partman
partitions, hash-chain genesis). This change layers on top.

8 chained PRs (each to `dev`, then release → `main`):

| PR | Slice | Tables | LOC est. | Notes |
|---|---|---|---:|---|
| **PR1** | Auth & Users | `usuarios`, `permisos`, `permisos_usuario`, `usuarios_sucursal`, `login` (5) | 600 | Touches `[V]` (4) + `[L-S]` (1); establishes JWT-issuer wiring in `parkos_core/auth/`; tenant middleware smoke-tested here |
| **PR2** | Empresa & Sucursal | `empresa`, `sucursal`, `tipo_sucursal`, `documentos`, `resolucion_facturacion` (5) | 700 | Cloud-admin writes; `documentos` carries base64 binary (open question on size cap); `resolucion_facturacion` is the DIAN root |
| **PR3** | Catalogs | `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios` (8) | 600 | All cloud-admin CRUD; smallest per-table LOC because they are pure catalog reads/writes; `tipos_vehiculo` is referenced by many downstream PRs |
| **PR4** | Per-branch config | `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `configuracion_tolerancias`, `configuracion_seguridad` (4) | 500 | Per-branch override pattern (default NULL + specific `uuid_sucursal`); admin writes per-branch |
| **PR5** | Customer | `clientes`, `clientes_b2b`, `subscripciones_cliente`, `vehiculos`, `subscripcion_vehiculos` (5) | 700 | Branch-originated; admin-read; subscription purchase = operator flow; `clientes_b2b` is 1:1 extension |
| **PR6** | Operación (Ingreso/Salida + Facturación) | `ingreso`, `salidas`, `facturas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos` (7) | 800 | High-volume: pg_partman partition queries must be partition-key aware; `factura_pagos` compensation pattern (`tipo_movimiento='reverso'`); `V_FACTURA_ESTADO` view surfaced as derived endpoint |
| **PR7** | DIAN compliance | `factura_electronica`, `revocacion_factura`, `envio_dian`, `validacion_evento` (4) | 800 | Cloud-only routers; branch import boundary tested via RED; `hash_chain` helper for `revocacion_factura`; `consecutivo_actual` atomic via `SELECT ... FOR UPDATE` |
| **PR8** | Workflows + Caja + Sync infra | `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `sesion`, `caja`, `arqueo`, `sync_queue`, `sync_conflict`, `sync_log`, `log_transaccional` (11) | 800 | Heaviest PR by table count, but workflows are short state machines; `sesion` is `[L-S]` with the strict UPDATE-with-log pattern; `sync_queue` is the only `[A]` with UPDATE exception |

> PR8 is borderline — 11 tables. If the LOC budget blows, split into
> PR8a (Workflows + Sesion: 5 tables) + PR8b (Caja + Sync: 6 tables).

Total estimated LOC: ~5,500 across 8 PRs (~690 LOC avg, all under 800).

**Dependency graph (must precede)**:

```
PR1 (Auth) ───────┐
                  ├─► PR2 (Tenant) ─► PR3 (Catalogs) ─► PR4 (Branch config) ─► PR5 (Customer)
                  │                                                                       │
                  └─────────────────────────────────────────────────────────────────► PR6 (Operación) ─► PR7 (DIAN) ─► PR8 (Workflows + Caja + Sync)
```

PR2 must follow PR1 (sucursal needs `usuarios_sucursal` for tenant
binding). PR3 may parallelize with PR4 (no FK between them). PR5 may
follow PR4. PR6 depends on PR5 (clientes + subscripciones referenced by
`ingreso.uuid_subscripcion_cliente`). PR7 depends on PR6 (factura_electronica FKs to facturas). PR8 depends on PR6 (sync_queue writes from operación).

## Open questions for sdd-propose

The proposal phase MUST resolve these before locking the spec:

1. **Pagination strategy**: cursor-based on `(vigente_desde, uuid)` for `[V]`; offset/page for `[L-E]` reads where insertion order is the natural sort. Confirm vs `Link` headers (RFC 5988) vs simple `{items, next_cursor}`.
2. **List endpoints**: expose a `GET /<resource>` list for every table, or only the ones with operational UI (e.g., `GET /facturas` yes, `GET /tipo_persona` only via `GET /catalogos/tipos`)?
3. **OpenAPI client SDK**: generate TS client (preferred for the PWA side) or hand-write the Zod schemas? If generated, which generator (`openapi-typescript-codegen`, `orval`, `openapi-fetch`)?
4. **RBAC at API vs DB**: enforce role checks in FastAPI dependency + DB REVOKE, OR rely on DB REVOKE only and trust JWT scope? (Defence-in-depth argues for both, but it doubles the auth code surface.)
5. **Idempotency keys**: standard `Idempotency-Key` HTTP header (Stripe-style) on all POST, with a 24h TTL `idempotency_keys` table? Or rely on UUID v4 PKs being globally unique (no second insert possible) and skip the header?
6. **DIAN endpoints**: separate `dian/cloud_router.py` mounted only in `api_admin`, OR a single `factura_electronica_router.py` with a runtime guard that rejects on branch?
7. **Sync endpoints on api_sucursal**: `POST /api/v1/sync/pair`, `POST /api/v1/sync/push`, `POST /api/v1/sync/pull` — mounted on both `api_admin` and `api_sucursal`? Or a separate `api_sync` service?
8. **Tenant context**: `X-Sucursal-Context` header (current model) vs path parameter (`/api/v1/sucursales/{uuid}/ingresos`) vs subdomain (`{uuid}.parkos.local`)? Header is simplest; path is most explicit; subdomain is most REST-y.
9. **`documentos.documento_b64`**: cap size at 1MB inline (model accepts text), or stream via `multipart/form-data` (requires separate endpoint, breaks base64 simplicity)?
10. **Bulk operations**: any use case for `POST /catalogos/tipos-vehiculo:batch` (CSV upload)? If yes, separate change.
11. **Open questions on table semantics surfaced from ER comments**:
    - `permisos_usuario`: revoke = close vigencia (per ER comment). Are we OK with that, or is there an explicit `revocado` flag?
    - `reclamos.tipo_reclamable` (polymorphic): how do we enforce type-safe writes? Application-level validation only (the FK is polymorphic by design).
    - `factura_pagos.uuid_pago_revertido`: enforce 1:1 reverso via partial unique index?
    - `alerta` workflow: do we support `rechazada` (rejected = closed) or only `resuelta`? ER comment says `abierta | en_revision | resuelta` — but rejection may exist in the workflow chain.
    - `reimpresion_ticket.estado`: `cobrada | anulada` — does the anulada state need a chain back to the original (yes, via `uuid_reimpresion_padre`), but the original row stays `cobrada`. Verify.
12. **Audit log noise**: do we log every `GET` in `log_transaccional`? Or only writes? (Current model says `crear | actualizar | eliminar | revocar | archivar` — all writes.)
13. **`login` failure lockout**: `configuracion_seguridad.max_intentos_login` is a config; how does the API enforce it? On insert of `login estado='fallido'`, query the last N rows for the user and reject if count >= max. Open: window (sliding 15 min? since last success?).
14. **DIAN online path**: when branch is online and calls `POST /api/v1/facturas/procesar` on `api_admin` synchronously, what's the timeout? 5s default? 30s? Bootstrap design mentions 5s but cloud roundtrip may need more.
15. **`V_RESOLUCION_CONSECUTIVO` derivation**: materialized view or live view? DIAN numeration needs atomic `consecutivo_actual`; live view + `SELECT ... FOR UPDATE` on `factura_electronica` ordering by `consecutivo DESC LIMIT 1`.

## Risks

| Severity | Risk | Mitigation |
|---|---|---|
| **High** | **Stale docs at 45 tables** — `openspec/PROJECT_CONTEXT.md` and `openspec/_meta/roadmap.md` (and `bootstrap-monorepo-foundation/proposal.md` and `design.md`) say 45 tables / 24 [V] / 4 [L-W]. The canonical ER has 49 / 26 [V] / 6 [L-W]. Drift between docs and the source of truth. | Reconcile during proposal phase: update PROJECT_CONTEXT.md and roadmap.md to reflect the +4 (tipo_arqueo, resolucion_facturacion, envio_dian, validacion_evento). Bootstrap proposal's PR2 (`0001_initial_schema.py`) MUST cover all 49, not 45 — verify before merge. |
| **High** | **Bootstrap schema must include all 49 tables** — if PR2 of bootstrap shipped with only 45 tables, `create-49-table-apis` cannot add the missing 4 via API alone. The `resolucion_facturacion`, `envio_dian`, `validacion_evento`, `tipo_arqueo` tables need DB-level FKs, REVOKE statements, trigger function names, partition calls. | Add a pre-flight check in PR1 of this change: `psql -c "\dt prod.*" \| wc -l` returns 49; `pg_trigger` count covers 11 [A] + 2 [L-S]; if not, block PR1 and require a follow-up Alembic migration from bootstrap. |
| **High** | **`[A]` REVOKE + trigger must be in place** — every API write to a `[A]` table fails if the trigger is missing (or, worse, silently succeeds). Defense in depth requires ALL THREE layers (API no UPDATE, ORM no UPDATE, DB REVOKE + trigger). | Add a smoke test in PR1: `INSERT INTO prod.factura_pagos ... ; UPDATE ... SET valor=0 WHERE uuid=:uuid` — expect 500 with `FACTURA_PAGOS_INMUTABLE`. Repeat for each of the 12 `[A]` tables. |
| **High** | **Hash-chain break on partial sync** — if `log_transaccional` rows arrive at cloud out-of-order, `hash_anterior` mismatches. The API helper computes chain server-side, but the sync worker must apply rows in order. | Cloud-edge-sync §4 already mandates per-branch monotonic seq in `datos` JSON. The API helper stamps the seq on every `log_transaccional` insert. Open question: who maintains the seq counter — DB sequence per `uuid_sucursal`, or app-side counter in `sync_queue`? |
| **High** | **DIAN-only boundary breach** — a bug in the branch image that imports `dian/cloud_router` would let a branch insert into `factura_electronica`. Bootstrap asserts this fails at import time; the API change must preserve that. | Add a RED test in PR7: `from parkos_core.dian import cloud_router` on the branch image raises `ImportError`. CI runs the same import in both build contexts. |
| **High** | **`[L-S]` trigger accepts UPDATE without log row** — if the trigger is misconfigured, a session-close UPDATE without a log row silently succeeds, breaking audit. | The session helper writes the log row BEFORE the UPDATE in the same TX. Add a smoke test: `UPDATE sesion SET estado='cerrada' WHERE uuid=:u` without a prior log insert in the TX → expect `LOG_TRANSACCIONAL_REQUIRED` exception. |
| **Med** | **Gitflow not initialized** — the repo is currently on `master` (not `main`). The preflight says chain=gitflow but no `dev` branch exists. PRs need to merge to `dev`. | Bootstrap change should establish the gitflow in PR1 (rename `master` to `main`, create `dev`). If not, this change's first PR creates them. |
| **Med** | **pg_partman partition-key indexes** — high-volume tables (`factura_detalle`, `factura_pagos`, `log_transaccional`, `sync_log`, `sync_queue`, `caja`, `arqueo`, `salidas`) are partitioned by month. The API queries MUST include the partition key in WHERE clauses to avoid sequential scan across all partitions. | ORM helper accepts `partition_key` as a required filter parameter for these tables (date range mandatory). Add a CI check: any ORM query missing the partition key on a partitioned table → lint warning. |
| **Med** | **`sync_queue` recursion** — if anyone accidentally enqueues a `sync_queue` row, infinite loop. The DB trigger explicitly filters `WHEN (TG_TABLE_NAME <> 'sync_queue')`; the API helper must mirror that. | Add a unit test: enqueueing any operation whose `tabla='sync_queue'` raises `SYNC_QUEUE_NO_RECURSION`. |
| **Med** | **`[L-W]` chain tie-break** — `reclamos` and `envio_dian` may have multiple chains if rejected and re-opened. The read-current query must pick the "longest chain" or "most recent root". | Spec must define: prefer the chain whose last row has the most recent `timestamp_evento`; on tie, prefer the chain with the most rows. Open question for proposal. |
| **Med** | **Idempotency-Key table** — the proposal question #5 proposes a 24h TTL idempotency table. This is itself an `[A]`-style table that needs REVOKE + trigger. Adds a 50th table to manage. | Decision: if we adopt it, register `idempotency_keys` as a sibling of `sync_queue` (local-only, no sync, REVOKE + trigger). Otherwise rely on UUID v4 PKs. |
| **Low** | **OpenAPI spec bloat** — 49 tables × ~5 endpoints each = ~245 paths. OpenAPI doc will be large. | Split OpenAPI by audience (admin vs operador) using FastAPI's `openapi_tags` + separate apps. Each PWA only ships its audience's doc. |
| **Low** | **Pydantic v2 schema drift from ORM** — if a Pydantic field name diverges from the ORM column name, mapping gets verbose. | Adopt `model_config = ConfigDict(from_attributes=True)` and align Pydantic field names with ORM column names exactly. Document any aliasing. |

## Next phase

`/sdd-propose create-49-table-apis` — produce the proposal that locks the
PR slicing above, ratifies the open questions, and references this
exploration. The proposal should also include the doc-reconciliation
patch (PROJECT_CONTEXT.md, roadmap.md, bootstrap proposal/design) to
close the 45→49 table-count drift before any PR lands.

## Relevant files

- `E:\easypunto_parkos\modelo_datos_er.mmd` (1178 lines, canonical ER)
- `E:\easypunto_parkos\AGENTS.md` (project canon — tech stack, audit-first principles, branching)
- `E:\easypunto_parkos\openspec\config.yaml` (SDD rules — REVOKE/trigger in same migration as `[A]` table create)
- `E:\easypunto_parkos\openspec\PROJECT_CONTEXT.md` (STALE at 45 tables — reconcile in proposal phase)
- `E:\easypunto_parkos\openspec\_meta\roadmap.md` (STALE at 45 tables — reconcile in proposal phase)
- `E:\easypunto_parkos\openspec\changes\cloud-edge-sync-architecture\exploration.md` (baseline sync decisions)
- `E:\easypunto_parkos\openspec\changes\bootstrap-monorepo-foundation\{exploration,proposal,design,tasks}.md` (active change; pre-flight gate)
- Engram topic key `sdd/create-49-table-apis/explore` (this exploration persisted as project memory)
