# Exploration: sync-overhaul

> **Change**: `sync-overhaul`
> **Phase**: explore (sdd-explore)
> **Date**: 2026-09-08
> **Inputs read**: `AGENTS.md`, `openspec/config.yaml`, `openspec/PROJECT_CONTEXT.md`,
> `openspec/changes/create-49-table-apis/tasks.md` (49 tables canon, PR8-9-11),
> `modelo_datos_er.mmd`, all sync + jobs + repo + models + migrations source,
> `backend/tests/unit/test_conflict_resolver.py`, `tests/unit/test_hash_chain.py`.
> **Approach (user-ratified)**: Option C — declarative `SyncCatalog` +
> reusable `SyncMotor` + per-table HOOKS for special cases.

## 1. Current sync surface (what we have today)

### 1.1 Inventory of sync-bearing files

| Path | Role | Lines |
|---|---|---|
| `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` | Creates 49 tables + 3 ops tables + 30 `fn_enqueue_sync` triggers + `fn_extend_hash_chain` + REVOKE on 11 [A] + `fn_<table>_inmutable` triggers | ~3,569 |
| `backend/packages/parkos_core/src/parkos_core/sync/conflict_resolver.py` | Per-class conflict policy + `ApplyOutcome` enum + 4 hardcoded `frozenset` table lists | 227 |
| `backend/packages/parkos_core/src/parkos_core/sync/table_registry.py` | NEW, uncommitted — auto-walks `models/*` and registers every ORM class with PK + `has_uuid_sucursal` | 126 |
| `backend/packages/parkos_core/src/parkos_core/sync/transport.py` | `SyncHttpClient` (push / pull / heartbeat / rotate-jwt) — single httpx session, JWT from disk | 168 |
| `backend/packages/parkos_core/src/parkos_core/sync/auto_discovery.py` | Branch list from `sync_log ∪ pairing_tokens` (last 7d/30d); `BranchCache(ttl=300s)` | 277 |
| `backend/packages/parkos_core/src/parkos_core/sync/jwt_manager.py` | 401-driven JWT lifecycle (RETRY_NEW_JWT, HALT_REVOKED, HALT_EXPIRED) | (per file) |
| `backend/packages/parkos_core/src/parkos_core/sync/router_helpers.py` | `RateLimit`, `SyncIdempotencyCache`, clock-skew check, JWT kid decode | (per file) |
| `backend/packages/parkos_core/src/parkos_core/jobs/sync_cloud.py` | `SyncCloudWorker`: 3 loops (apply_pushed, emit_sync_back, hash_chain_verifier) | 521 |
| `backend/packages/parkos_core/src/parkos_core/jobs/sync_sucursal.py` | `SyncSucursalWorker`: 6-step cycle (poll/push/handle/pull/heartbeat/sleep) | 486 |
| `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py` | 6 endpoints: `/sync/{pair,push,pull,heartbeat,rotate-jwt,events}` + per-endpoint rate limit + idempotency cache | 923 (modified, uncommitted) |
| `backend/packages/parkos_core/src/parkos_core/repo/sync_queue.py` | Worker-side CRUD on `prod.sync_queue` (carved-out [A]); 4 whitelisted columns + backoff schedule | 318 |
| `backend/packages/parkos_core/src/parkos_core/repo/sync_outbox.py` | No-op facade (the only fence that documents `fn_enqueue_sync` is the canonical path) | 48 |
| `backend/packages/parkos_core/src/parkos_core/repo/append_only.py` | `append_event(chain_hash=False)` + `compensate()` for [A] | 227 |
| `backend/packages/parkos_core/src/parkos_core/repo/hash_chain.py` | `append(session, model, payload, actor)` — SHA-256 chain per `uuid_sucursal` + `_genesis_hash` | 220 |
| `backend/packages/parkos_core/src/parkos_core/repo/event.py` | `record_event(...)` for [L-E] — extends hash chain via `hash_chain.append` for `log_transaccional` | 131 |
| `backend/packages/parkos_core/src/parkos_core/repo/versioned.py` | `close_and_insert()` — bi-temporal close+insert for [V] | 143 |
| `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` | `append_transition()` for [L-W] | (per file) |
| `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py` | `record_login` / `close_login_with_log` for [L-S] | (per file) |
| `backend/packages/parkos_core/src/parkos_core/dian/cloud/dispatcher.py` | DIAN dispatcher — extends `revocacion_factura` chain on `aceptado` AND enqueues `operacion='sync_back_event'` row into `sync_queue` | 531 |

### 1.2 The 49-table canon (and 3 operational siblings)

Per `AGENTS.md` §"Architectural Principles" and `modelo_datos_er.mmd`. Counts in
AGENTS.md say 49, but the repo today carries 52 tables in `prod.*`:

| Audit class | Count | ORM dir | ER marker |
|---|---|---|---|
| [V] versioned projection | 26 | `models/V/` | yes |
| [L-E] lifecycle event | 3 | `models/L_E/` | yes |
| [L-W] workflow | 6 | `models/L_W/` | yes |
| [L-S] session/cycle | 2 | `models/L_S/` | yes |
| [A] source-of-truth (canon) | 12 | `models/A/` | yes |
| **Sub-total** | **49** | | |
| [A] operational carve-outs | +3 | `models/A/` | n/a (added PR7/PR8) |
| - `idempotency_keys` | +1 | — | 50th, PR7 |
| - `pairing_tokens` | +1 | — | 51st, PR8 |
| - `revoked_sync_jwts` | +1 | — | 52nd, PR8 |
| **TOTAL in DB** | **52** | | |

The 3 operational tables are NOT in the ER diagram (added during
`create-49-table-apis` PR7/PR8) but live in `prod.*` and carry the same
audit-first invariants as the [A] canon. The catalog needs to enumerate them
explicitly so the sync policy is unambiguous.

### 1.3 The 30 `fn_enqueue_sync` triggers actually installed

Per `0001_initial_schema.py` lines 2728-2906 (CREATE statements) + lines
3360-3389 (DROP statements for downgrade). The header comment at line 32
claims "48 `fn_<table>_enqueue_sync()` triggers" but the actual install is
30. Cross-referenced against the 52-table inventory:

| Table | Audit class | Trigger installed? | Reason |
|---|---|---|---|
| `usuarios_sucursal` | [V] | YES | replicated auth junction |
| `documentos` | [V] | YES | replicated admin assets |
| `tarifas_sucursal` | [V] | YES | replicated per-branch tariff |
| `cantidad_vehiculos_sucursal` | [V] | YES | replicated per-branch cap |
| `configuracion_tolerancias` | [V] | YES | replicated per-branch |
| `configuracion_seguridad` | [V] | YES | replicated per-branch |
| `resolucion_facturacion` | [V] | YES | replicated per-branch DIAN resolution |
| `subscripciones_cliente` | [V] | YES | replicated commercial |
| `permisos`, `permisos_usuario` | [V] | NO | catalog (admin-cfg only?) |
| `empresa`, `usuarios` | [V] | NO | catalog (admin-cfg only?) |
| `clientes`, `clientes_b2b`, `vehiculos`, `subscripcion_vehiculos` | [V] | NO | commercial master |
| `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo` | [V] | NO | catalog |
| `impuestos`, `otros_cobros`, `costos_servicios` | [V] | NO | catalog |
| `sucursal` | [V] | NO | branch master (admin-cfg) |
| `login`, `sesion` | [L-S] | YES | replicated per-operator session |
| `ingreso` | [L-E] | YES | replicated parking event |
| `salidas` | [A] | YES | replicated parking exit |
| `caja` | [A] | YES | replicated cash session |
| `facturas` | [L-E] | YES | replicated invoice |
| `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos` | [A] | YES | replicated billing |
| `arqueo` | [A] | YES | replicated cash count |
| `revocacion_factura` | [A] (chain) | YES | replicated DIAN revocation |
| `sync_log`, `sync_conflict` | [A] op | YES | operational (recurses to itself) |
| `log_transaccional` | [A] (chain) | YES | replicated audit log |
| `factura_electronica` | [L-E] | YES | replicated DIAN ack |
| `reimpresion_ticket`, `anulaciones`, `reclamos`, `alerta`, `envio_dian`, `validacion_evento` | [L-W] | YES | replicated workflows |
| `sync_queue` | [A] op | EXCLUDED (recursion guard) | DB function: `IF TG_TABLE_NAME = 'sync_queue' RETURN NULL` |
| `idempotency_keys` | [A] op | NO | local-only idempotency cache |
| `pairing_tokens` | [A] op | NO | pairing flow (pre-issuance, never replicated) |
| `revoked_sync_jwts` | [A] op | NO | local-only JWT revocation list |

**Gap summary**: 18 [V] tables + 3 operational [A] tables have NO
`fn_enqueue_sync` trigger = 21 tables where the proposed catalog MUST
declare `sync_strategy: 'never_propagated'` (or a follow-up migration
adds the missing triggers in PR-OVERHAUL-2).

### 1.4 The `fn_enqueue_sync` payload shape (the opaque JSONB)

```sql
-- 0001_initial_schema.py lines 1947-1985
CREATE OR REPLACE FUNCTION prod.fn_enqueue_sync()
RETURNS trigger AS $$
DECLARE
    next_seq bigint;
    payload jsonb;
BEGIN
    IF TG_TABLE_NAME = 'sync_queue' THEN
        RETURN NEW;                                  -- recursion guard
    END IF;
    SELECT COALESCE(MAX((datos->>'seq')::bigint), 0) + 1 INTO next_seq
      FROM prod.sync_queue
     WHERE uuid_sucursal IS NOT DISTINCT FROM NEW.uuid_sucursal;
    payload := to_jsonb(NEW);                       -- WHOLE ROW → JSONB
    payload := jsonb_set(payload, '{seq}', to_jsonb(next_seq));
    INSERT INTO prod.sync_queue (
        uuid, uuid_sucursal, operacion, tabla, uuid_registro,
        datos, prioridad, estado, intentos,
        created_at, created_by, sync_status, sync_attempts)
    VALUES (
        gen_random_uuid(),
        NEW.uuid_sucursal,
        TG_OP,                                       -- 'INSERT' / 'UPDATE' / 'DELETE'
        TG_TABLE_NAME,
        NEW.uuid,
        payload,
        CASE TG_TABLE_NAME
            WHEN 'factura_electronica' THEN 10
            WHEN 'revocacion_factura'  THEN 10
            WHEN 'ingreso'             THEN 5
            WHEN 'salidas'             THEN 5
            WHEN 'factura_pagos'       THEN 5
            ELSE 1
        END,
        'pendiente', 0,
        NOW(), NEW.created_by, 'pendiente', 0);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

Three opaque-by-design properties:

1. **Whole-row `to_jsonb(NEW)`** — the payload carries every column, including
   server-controlled ones (`created_at`, `created_by`, `vigente_hasta`,
   `sync_status`). When the branch-side applier reads it back, it has to
   filter server-controlled columns out (see `sync_router.py` lines 836-857).
2. **`seq` keyed in `datos->>'seq'`** — the per-row monotonic seq lives
   inside the payload JSONB, not as a first-class column. Every consumer
   (`ConflictResolver._coerce_seq`) re-parses JSON on every row.
3. **Per-table priority is hardcoded in the trigger function** — adding a new
   "high priority" table requires editing the trigger.

### 1.5 `ConflictResolver` — the 4 hardcoded frozensets

From `sync/conflict_resolver.py`:

```python
APPEND_ONLY_TABLES: frozenset[str] = frozenset({
    "sync_queue", "sync_log", "sync_conflict", "log_transaccional",
    "factura_detalle", "factura_impuestos", "factura_otros_cobros",
    "factura_pagos", "revocacion_factura", "caja", "arqueo",
    "pairing_tokens", "revoked_sync_jwts", "idempotency_keys", "salidas",
})
LIFECYCLE_EVENT_TABLES: frozenset[str] = frozenset({"ingreso", "facturas", "factura_electronica"})
WORKFLOW_TABLES: frozenset[str] = frozenset({
    "anulaciones", "reclamos", "alerta", "reimpresion_ticket",
    "envio_dian", "validacion_evento",
})
SESSION_TABLES: frozenset[str] = frozenset({"login", "sesion"})
```

Plus a stub `_read_local_seq` that returns `None` (lines 203-217):

```python
async def _read_local_seq(self, session, tabla, uuid_registro) -> int | None:
    """Return the highest locally-known seq for (tabla, uuid_registro).
    Default returns None — the per-row monotonic seq lives in the
    destination table itself (varies by table). PR9b wires the
    concrete lookup per [V] destination table.
    """
    return None
```

This means: every [V] conflict currently resolves to `APPLIED` because
`existing is None`. There is no concrete conflict detection for [V] today.

### 1.6 Hash chain integration (only 2 tables carry the chain)

From `repo/hash_chain.py` + `models/base.py::HashChainMixin`:

- `log_transaccional` and `revocacion_factura` are the ONLY tables that
  carry the chain columns (`hash_anterior` CHAR(64), `hash_actual` CHAR(64)).
- Detection happens via mixin introspection:
  `_has_hash_chain(model_cls)` returns `HashChainMixin in model_cls.__mro__`.
- `repo/append_only.append_event(..., chain_hash=True)` switches to
  `repo/hash_chain.append(...)` when the mixin is present.
- `repo/event.record_event(...)` always extends the chain via
  `hash_chain.append(LogTransaccional, ...)` (PR11c — Bug 2).
- DIAN dispatcher calls `hash_chain.append(RevocacionFactura, ...)`
  explicitly on `_finalize_revocacion(estado='aceptado')`
  (`dian/cloud/dispatcher.py` lines 488-493).
- DB trigger `prod.fn_extend_hash_chain()` on `prod.log_transaccional`
  (BEFORE INSERT) re-verifies the chain server-side — Python + DB agree
  on every insert.

### 1.7 Cloud-side worker — 3 loops (`jobs/sync_cloud.py`)

1. **Cycle pulse (heartbeat)**: 5s sleep, lazily starts 2 heavy loops.
2. **`_emit_sync_back_events_loop` (5s)**: reads `prod.sync_queue` pending
   rows via `repo/sync_queue.list_pending`, looks up the table in
   `sync.table_registry.get_table(tabla)` to determine `branch_scopable`,
   POSTs to each branch's `/api/v1/sync/events`. Broadcasts to ALL branches
   when `branch_scopable=False` (catalogs). Marks `estado='exitoso'` /
   `estado='fallido'` per branch response.
3. **`_hash_chain_verifier_loop` (3600s)**: walks `prod.log_transaccional`
   per `uuid_sucursal` in `(timestamp_evento, uuid)` order. On mismatch
   raises `HashChainBreak` → writes `alerta tipo_alerta='hash_chain_anomaly'`
   + `sync_conflict tabla='log_transaccional' politica='chain_break'`.

NOTE: today the verifier ONLY walks `log_transaccional`. When the catalog
formalizes `revocacion_factura` as chain-bearing, the verifier must also
walk that table.

### 1.8 Branch-side worker — 6 steps (`jobs/sync_sucursal.py`)

1. Poll `prod.sync_queue` (`list_pending(limit=batch_size)`).
2. Push batch via `SyncHttpClient.push` → 207 / 2xx / 401 / 4xx / 5xx.
3. Handle response: 207 → partial via `success_uuids`,
   401 → `JwtManager.on_401_response` (RETRY_NEW_JWT or HALT),
   4xx → `mark_failed` (no retry),
   5xx → `mark_failed` + backoff schedule.
4. Pull cloud changes (`SyncHttpClient.pull(since_seq=0)`).
5. For each pulled row → `ConflictResolver.apply_pushed_row`.
6. Heartbeat (fire-and-forget) + sleep `poll_interval_s`.

The cloud-side `/sync/push` and `/sync/pull` handlers in
`api/v1/sync_router.py` are auth-only stubs (lines 480-487 and 553-559):
every row returns `status="applied"` for push and empty for pull. The
real applier (line 740-920 `/sync/events`) DOES wire the per-table
strategy but does it by trial: try `close_and_insert` first, fall back to
`append_event` on failure. This trial pattern is exactly what the catalog
replaces.

### 1.9 Sync queue — the carved-out [A] table

`prod.sync_queue` carries UPDATE/DELETE grants (the only [A] table that
does), gated to 4 whitelisted columns in `repo/sync_queue.py`:

```python
ALLOWED_SYNC_QUEUE_UPDATE_COLUMNS: frozenset[str] = frozenset(
    {"estado", "intentos", "next_retry_at", "ultimo_error"}
)
BACKOFF_SCHEDULE: tuple[timedelta, ...] = (
    timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30),
    timedelta(hours=2), timedelta(hours=12), timedelta(hours=24),
)
```

Monthly partitioned by `fecha_retencion_hasta` (pg_partman). The catalog
should declare `sync_queue` as `is_sync_outbox=True` so the motor knows
not to enqueue it again on push (recursion guard) and respects the 4
whitelisted columns when mutating state.

### 1.10 Pairing flow + JWT (`api/v1/sync_router.py::sync_pair`)

- `POST /sync/pair` consumes an admin-issued `pairing_token` (single-use,
  24h TTL) and mints a 30-day `sync-agent-cloud` JWT.
- `POST /sync/rotate-jwt` rotates the current JWT with a unique
  `sync-agent-cloud-r-{uuid}` issuer and 24h grace window.
- Auth chain on every protected endpoint: (1) `verify_jwt` issuer prefix,
  (2) `is_revoked` lookup, (3) `iat_branch` clock-skew check,
  (4) `X-Request-Id` idempotency cache, (5) per-(issuer, subject) rate limit.
- 6 endpoints + 4 rate-limit budgets (push=60/min, pull=120/min,
  heartbeat=10/min, rotate=1/min). No coupling to the sync payload shape
  — the catalog refactor must not change the auth chain.

## 2. The 52 tables → per-table catalog mapping

The proposed `SyncCatalog` needs one entry per table. Below is the working
mapping (49 ER tables + 3 operational carve-outs) with the fields the
catalog should carry.

### 2.1 [V] versioned (26 tables)

Per-table strategy: `manual_conflict_resolution` (the seq-based tie-break
on the destination table). Apply via `repo/versioned.close_and_insert`.
Hash chain: no (no row reaches the chain via this path — `log_transaccional`
extends via `repo/event.record_event` separately).

| Table | `uuid_sucursal` | Trigger today | Catalog `sync_strategy` | `seq_strategy` | Broadcast | DIAN? |
|---|---|---|---|---|---|---|
| `permisos` | NO | NO | `never_propagated` (admin-cfg only) | n/a | n/a | no |
| `permisos_usuario` | NO | NO | `never_propagated` | n/a | n/a | no |
| `empresa` | NO | NO | `never_propagated` | n/a | n/a | no |
| `tipo_persona` | NO | NO | `never_propagated` (catalog master) | n/a | n/a | no |
| `tipos_vehiculo` | NO | NO | `never_propagated` | n/a | n/a | no |
| `tipo_subscripciones` | NO | NO | `never_propagated` | n/a | n/a | no |
| `tipo_tarifa` | NO | NO | `never_propagated` | n/a | n/a | no |
| `tipo_sucursal` | NO | NO | `never_propagated` | n/a | n/a | no |
| `tipo_arqueo` | NO | NO | `never_propagated` | n/a | n/a | no |
| `impuestos` | NO | NO | `never_propagated` | n/a | n/a | no |
| `otros_cobros` | NO | NO | `never_propagated` | n/a | n/a | no |
| `costos_servicios` | NO | NO | `never_propagated` | n/a | n/a | no |
| `sucursal` | NO | NO | `never_propagated` | n/a | n/a | no |
| `clientes` | NO | NO | `never_propagated` | n/a | n/a | no |
| `clientes_b2b` | NO | NO | `never_propagated` | n/a | n/a | no |
| `vehiculos` | NO | NO | `never_propagated` | n/a | n/a | no |
| `subscripcion_vehiculos` | NO | NO | `never_propagated` | n/a | n/a | no |
| `usuarios` | NO | NO | `manual` (cross-tenant admin-cfg, special-case TBD) | per-table-clock | `all_branches` (single-tenant tables need per-uuid_usuario policy) | no |
| `usuarios_sucursal` | YES | YES | `manual` | `seq_via_datos` | `single_branch` (uuid_sucursal) | no |
| `documentos` | YES | YES | `manual` | `seq_via_datos` | `single_branch` | no |
| `tarifas_sucursal` | YES | YES | `manual` | `seq_via_datos` | `single_branch` | no |
| `cantidad_vehiculos_sucursal` | YES | YES | `manual` | `seq_via_datos` | `single_branch` | no |
| `configuracion_tolerancias` | YES | YES | `manual` | `seq_via_datos` | `single_branch` | no |
| `configuracion_seguridad` | YES | YES | `manual` | `seq_via_datos` | `single_branch` | no |
| `resolucion_facturacion` | YES | YES | `manual` (DIAN, see §2.5) | `seq_via_datos` | `single_branch` | YES (DIAN) |
| `subscripciones_cliente` | YES | YES | `manual` | `seq_via_datos` | `single_branch` | no |

NOTE: 18 of 26 [V] tables have NO trigger today. The proposal MUST decide
either (a) keep `never_propagated` and add explicit justification per
table, or (b) ship a follow-up migration that adds the missing 18
triggers. Option (b) requires per-table justification — e.g. do branches
need local `permisos` for offline login? — before triggering it.

### 2.2 [L-E] lifecycle events (3 tables)

Per-table strategy: `append` (no conflict possible; events are immutable
facts). Apply via `repo/event.record_event`. Hash chain: `log_transaccional`
is extended by `record_event` automatically.

| Table | `uuid_sucursal` | Trigger | Catalog `sync_strategy` | Hash chain | DIAN? |
|---|---|---|---|---|---|
| `ingreso` | YES | YES | `append` (L-E) | via `record_event` → `log_transaccional` | no |
| `facturas` | YES | YES | `append` (L-E) | via `record_event` → `log_transaccional` | no |
| `factura_electronica` | YES | YES | `append` (L-E) + `sync_back_event=True` | via `record_event` | YES (DIAN ack) |

### 2.3 [L-W] workflows (6 tables)

Per-table strategy: `append` (workflow chain = `uuid_padre` FK, last row
is current state). Apply via `repo/workflow.append_transition`.

| Table | `uuid_sucursal` | Trigger | Catalog `sync_strategy` | Hash chain | DIAN? |
|---|---|---|---|---|---|
| `reimpresion_ticket` | YES | YES | `append` (L-W) | via `log_transaccional` | no |
| `anulaciones` | YES | YES | `append` (L-W) | via `log_transaccional` | no |
| `reclamos` | YES | YES | `append` (L-W) | via `log_transaccional` | no |
| `alerta` | YES | YES | `append` (L-W) | via `log_transaccional` | no |
| `envio_dian` | YES | YES | `append` (L-W) + `cloud_only=True` | via `log_transaccional` | YES (cloud-only writes) |
| `validacion_evento` | YES | YES | `append` (L-W) + `cloud_only=True` | via `log_transaccional` | YES (cloud-only writes) |

`envio_dian` + `validacion_evento` are cloud-only today (AGENTS.md
explicit: "DIAN-only tables ... live ONLY in cloud; branches have schema
parity but never write"). Catalog must enforce this with a
`deployment_scope: cloud` flag and a build-time import guard (the
`dian/cloud/dian_providers/factus.py` line 31-35 already uses this pattern
for the Factus adapter).

### 2.4 [L-S] sessions (2 tables)

Per-table strategy: `grace_window` (the JWT overlap window). Apply via
`repo/session_cycle.record_login` / `close_login_with_log`. Hash chain:
via `log_transaccional` (the `fn_login_ls_session_guard` trigger ensures
a co-transactional log row is written).

| Table | `uuid_sucursal` | Trigger | Catalog `sync_strategy` | Hash chain | DIAN? |
|---|---|---|---|---|---|
| `login` | YES | YES | `grace_window` (24h overlap, configurable) | via `log_transaccional` | no |
| `sesion` | YES | YES | `grace_window` | via `log_transaccional` | no |

### 2.5 [A] source-of-truth (12 tables)

Per-table strategy: `append` (events only). Apply via
`repo/append_only.append_event(chain_hash=True|False)`. Hash chain column
on `log_transaccional` + `revocacion_factura` only.

| Table | `uuid_sucursal` | Trigger | Catalog `sync_strategy` | Hash chain | DIAN? |
|---|---|---|---|---|---|
| `salidas` | YES | YES | `append` (A) | no | no |
| `factura_detalle` | YES | YES | `append` (A) | no | no |
| `factura_impuestos` | YES | YES | `append` (A) | no | no |
| `factura_otros_cobros` | YES | YES | `append` (A) | no | no |
| `factura_pagos` | YES | YES | `append` (A) + reverso compensation pattern | no | no |
| `caja` | YES | YES | `append` (A) | no | no |
| `arqueo` | YES | YES | `append` (A) | no | no |
| `log_transaccional` | YES | YES | `append` (A) + **`hash_chain=True`** | YES (carries chain) | no |
| `revocacion_factura` | YES | YES | `append` (A) + **`hash_chain=True`** + DIAN | YES | YES |
| `sync_log` | YES (op) | YES | `local_only` | no | no |
| `sync_conflict` | YES (op) | YES | `local_only` | no | no |
| `sync_queue` | YES (op) | EXCLUDED | `is_sync_outbox=True` (carved-out [A]) | no | no |

### 2.6 [A] operational carve-outs (3 tables, NOT in canon)

| Table | `uuid_sucursal` | Trigger | Catalog `sync_strategy` | Notes |
|---|---|---|---|---|
| `idempotency_keys` | YES | NO | `local_only` (TTL-pruned; never replicated) | added PR7 |
| `pairing_tokens` | NO | NO | `local_only` (pre-issuance; never replicated) | added PR8 |
| `revoked_sync_jwts` | YES | NO | `local_only` (JWT revocation list; never replicated) | added PR8 |

### 2.7 Sync-only meta-tables (NOT in `prod.*`)

`pairing_tokens` carries `used_by_branch_info` JSONB used by
`sync/auto_discovery.py` to discover the branch list. `revoked_sync_jwts`
is read by `api/v1/sync_router.py::_sync_agent_claims`. `idempotency_keys`
is read by the `IdempotencyKeyMiddleware`. None of them should appear in
the catalog — they are infra tables, not data tables.

## 3. Gaps between current surface and Option C

Numbered for traceability. Each gap is concrete + actionable.

### Gap 1 — 21 tables have NO `fn_enqueue_sync` trigger
18 [V] tables + 3 operational [A] tables. Today the worker's emit loop
silently skips them. The catalog MUST declare `sync_strategy: never_propagated`
for each one OR a follow-up migration MUST add the missing triggers.
**Action**: per-table decision in the proposal.

### Gap 2 — `ConflictResolver`'s class lists duplicate ORM metadata
4 hardcoded `frozenset` (15+3+6+2 = 26 entries) reproduce information that
already lives in `models.base` (`VersionedBase`, `LifecycleEventBase`,
`WorkflowBase`, `SessionBase`, `AppendOnlyBase`). The catalog should
derive these via `issubclass(model_cls, Base)` once and remove the
hardcoded sets.

### Gap 3 — `_read_local_seq` is a stub returning None
Every [V] conflict currently resolves to `APPLIED` because the resolver
returns None. 26 [V] tables need concrete seq lookups. 12 of them carry
`created_at` only (no `timestamp_evento`); the lookup is
`MAX(created_at) WHERE uuid = :uuid`. The motor must call the
catalog-declared `seq_strategy` (`MAX(timestamp_evento)` vs
`MAX(created_at)` vs UUID-7 timestamp extraction).

### Gap 4 — DIAN SyncBackEvent path leaks into `sync_queue`
`dispatcher._finalize_revocacion` writes
`operacion='sync_back_event'` rows into `sync_queue`. The catalog should
declare `sync_back_event=True` for `factura_electronica` +
`revocacion_factura` + `envio_dian` and route through a dedicated
`sync_back_events` table (or `sync_queue`-internal flag) so the
append-only outbox stays clean.

### Gap 5 — Hash chain integration is via mixin introspection
`_has_hash_chain` checks `HashChainMixin in cls.__mro__`. The catalog
should expose `hash_chain: bool` and the motor should route accordingly.
For `revocacion_factura` on DIAN `aceptado`, the dispatcher already calls
`hash_chain.append` explicitly — that's the per-table hook callable
pattern.

### Gap 6 — Branch-side `/sync/events` applier picks strategy by trial
`sync_router.py` lines 869-903 try `close_and_insert` first, fall back to
`append_event`. The catalog replaces the trial with a declared
`apply_strategy` per table.

### Gap 7 — `sync_queue` carve-out is special
The catalog must NOT extend sync_queue — it stays as the operational
outbox. Declare `is_sync_outbox=True` with `state_mutable_columns` set
(`{estado, intentos, next_retry_at, ultimo_error}`).

### Gap 8 — Broadcast policy is implicit
Cloud-side emitter sends ANY catalog update to ALL branches when
`branch_scopable=False`. With 18 [V] catalogs newly reachable (if Gap 1 is
closed), broadcast traffic multiplies. Catalog needs
`broadcast_policy: 'all_branches' | 'single_branch' | 'subscription'` per
table — defaults from `has_uuid_sucursal` but overridable.

### Gap 9 — Hash chain verifier only walks `log_transaccional`
`sync_cloud._verify_one_tenant_chain` line 393 only queries
`prod.log_transaccional`. When `revocacion_factura` chain extension is
formalized via the catalog hook, the verifier must also walk that table.
Catalog exposes `verify_chain=True` so the verifier iterates all
chain-bearing tables.

### Gap 10 — Per-uuid_sucursal seq for cloud-global tables
Tables without `uuid_sucursal` (catalogs, [A] op carve-outs) share the
NULL tenant. `fn_enqueue_sync` filters `uuid_sucursal IS NOT DISTINCT FROM
NEW.uuid_sucursal` (line 1958) which handles NULL. The catalog must
preserve this — declare `seq_tenant_scope: 'uuid_sucursal'` even when the
column is nullable.

### Gap 11 — Cutover order
Branches first (so cloud → branch push runs on the new catalog), cloud
last (so the verifier + SyncBackEvent emitter + revocation checker all
consume the new catalog at once). Migration in-flight: `sync_queue` rows
during cutover must drain under both code paths. Strategy: feature flag
`PARKOS_SYNC_ENGINE=legacy|catalog` on the worker entrypoint; legacy =
current behavior, catalog = new motor. Both paths must run during the
overlap window; the motor must read the flag and dispatch.

## 4. What the proposed `SyncCatalog` / `SyncMotor` / `HookSpec` needs

This is the proposal-shape handoff. Not yet a design — just the surface.

### 4.1 `SyncCatalog` (one entry per table, declarative)

```python
@dataclass(frozen=True)
class SyncCatalogEntry:
    name: str                                   # __tablename__
    model_cls: type[DeclarativeBase]
    audit_class: Literal["V", "L_E", "L_W", "L_S", "A"]
    sync_strategy: Literal["append", "manual", "grace_window",
                            "never_propagated", "local_only",
                            "is_sync_outbox"]
    has_uuid_sucursal: bool                     # derived from columns
    seq_strategy: Literal["seq_via_datos",
                          "max_timestamp_evento",
                          "max_created_at",
                          "none"] | None
    hash_chain: bool = False
    cloud_only: bool = False                    # envio_dian, validacion_evento
    sync_back_event: bool = False               # DIAN ack tables
    broadcast_policy: Literal["single_branch",
                               "all_branches",
                               "subscription"] = "single_branch"
    apply_strategy: Literal["close_and_insert",
                            "record_event",
                            "append_event",
                            "append_transition",
                            "session_cycle"]   # how the motor calls the repo
    hook_pre_insert: Callable | None = None     # DIAN, hash chain, bi-temporal
    hook_post_insert: Callable | None = None
    hook_chain_extend: Callable | None = None  # hash chain extension
    verify_chain: bool = False                  # sync_cloud verifier iterates
    state_mutable_columns: frozenset[str] | None = None  # for sync_queue
```

Construction: declarative list (one file or per-table decorators) —
NOT auto-discovery (the catalog is a policy decision, not metadata).

### 4.2 `SyncMotor` (reusable, per-direction)

Three methods, each taking a `SyncCatalogEntry` + payload:

```python
class SyncMotor:
    async def apply_row(self, spec: SyncCatalogEntry, payload: dict,
                        *, actor_uuid, log_tx=True) -> ApplyResult
    async def verify_chain(self, spec: SyncCatalogEntry, branch_uuid) -> list[Anomaly]
    async def resolve_conflict(self, spec: SyncCatalogEntry,
                                local: dict, remote: dict) -> ConflictResolution
```

The motor must:
- Look up `spec.apply_strategy` → dispatch to the corresponding `repo.*`
  helper (`close_and_insert`, `record_event`, `append_event`,
  `append_transition`, `session_cycle`).
- Call `spec.hook_pre_insert` before the repo call.
- Call `spec.hook_post_insert` after the repo call.
- For `spec.hash_chain=True` rows, route through `repo/hash_chain.append`
  instead of `repo/append_only.append_event`.
- For `spec.verify_chain=True` rows, expose the chain head to the verifier.
- For `spec.cloud_only=True` rows, raise `ImportError` on branch process
  (build-time guard like `dian/cloud/dian_providers/factus.py` line 31-35).

### 4.3 Hooks (per-table callable signatures)

- `DIANCloudExtension(spec=RevocacionFactura)` — called when the
  DIAN dispatcher confirms `aceptado`. Reads `sync_queue.datos`,
  recomputes hash, extends chain.
- `LogTransaccionalChainExtension(spec=LogTransaccional)` — called by
  every `repo/event.record_event` + `repo/append_only.append_event`
  + `repo/versioned.close_and_insert(log_tx=True)` + the [L-W] and [L-S]
  writers.
- `BiTemporalCompensation(spec=FacturaPagos)` — for `tipo_movimiento='reverso'`
  compensation rows (`repo/factura_pagos.reverse_payment`).
- `SyncBackEvent(spec=FacturaElectronica | RevocacionFactura | EnvioDian)` —
  pushes a `SyncBackEvent` into `sync_queue` (or `sync_back_events`)
  with `operacion='sync_back_event'` after the cloud write commits.

### 4.4 Migration path

Feature flag `PARKOS_SYNC_ENGINE=legacy|catalog` on
`parkos_core.jobs.sync_cloud` + `parkos_core.jobs.sync_sucursal` +
`parkos_core.api.v1.sync_router` entrypoints. Both paths run during the
overlap window. The motor must read the flag and dispatch. Drain is
verified by `SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente'`
returning 0 within 2× `poll_interval_s` after the catalog cutover.

### 4.5 Cutover order (recap)

1. Branches first: `job_sync_sucursal` + branch `/sync/events` applier
   switch to motor (lowest risk — they only consume).
2. Cloud second: `job_sync_cloud` (3 loops) + cloud `/sync/push` +
   `/sync/pull` handlers switch to motor. The hash chain verifier and
   SyncBackEvent emitter live here — single coordinated switchover.
3. Triggers (`fn_enqueue_sync`) stay in place (or get a parallel
   `fn_enqueue_sync_catalog` path that does the same thing); the worker
   can read from either. Migration: drop legacy triggers AFTER the
   catalog path has been observed stable for 24h+ with 0 dropped rows.

## 5. Risks surfaced

| # | Risk | Severity | Mitigation in proposal |
|---|---|---|---|
| R1 | Catalog drift from `modelo_datos_er.mmd` (PR1a canon) | HIGH | CI gate: every catalog entry must reference an existing ORM class; reject unknown names; fail build on missing entries. |
| R2 | In-flight `sync_queue` rows during cutover lose their seq interpretation | HIGH | Feature flag + drain check; both paths read `datos->>'seq'` JSONB identically during overlap. |
| R3 | New 18 [V] tables (Gap 1) suddenly replicate and overwhelm branches | MEDIUM | Per-table decision in the proposal — `never_propagated` requires explicit justification. If a trigger is added, broadcast policy + tenant scope must be ratified first. |
| R4 | Hash chain verifier dual-walks (`log_transaccional` + `revocacion_factura`) doubles DB load | LOW | Single transaction per tenant; walker order = `log_transaccional` first, then `revocacion_factura`. Cache the per-tenant chain head for the duration of the sweep. |
| R5 | DIAN dispatcher still writes `operacion='sync_back_event'` into `sync_queue` after catalog cutover | MEDIUM | Catalog entry declares `sync_back_event=True`; the dispatcher's hook (`SyncBackEvent(spec)`) replaces the manual insert + the worker routes SyncBackEvent rows through a dedicated path. |
| R6 | Branch process imports a cloud-only catalog entry (e.g. `envio_dian`) at boot | HIGH | Build-time import guard (`if os.environ.get("PARKOS_DEPLOY") == "branch": raise ImportError`), matching the Factus adapter pattern (`dian/cloud/dian_providers/factus.py` line 31-35). |
| R7 | Test mocks don't see new hook callables | MEDIUM | Hooks are pure callables — tests inject `spec.hook_post_insert=lambda x: None`. The `test_event_record.py::_make_session()` extension from PR11c is a precedent. |
| R8 | `sync_queue` carve-out enforcement regresses during the refactor | MEDIUM | Catalog entry declares `is_sync_outbox=True`; AST test rejects `update/delete` on `SyncQueue` outside `repo/sync_queue.py` — already in place today. |
| R9 | `_read_local_seq` materialization introduces a per-table DB query on every conflict | LOW | The seq lookup is per-`uuid_registro` per-table — bounded by 1 SELECT per row, covered by the existing `(uuid, fecha_retencion_hasta)` partial index on `[A]` and the `vigente_hasta IS NULL` partial index on `[V]`. |
| R10 | Per-table priority hardcoded in `fn_enqueue_sync` (Gap 1 has 18 [V] all at priority=1) | LOW | Move priority out of the trigger into `SyncCatalogEntry.priority`; the worker reads it from the catalog (or from `sync_queue.prioridad` if the row was already enqueued with the old trigger). |

## 6. Outputs handed to `sdd-propose`

The proposal phase needs:

- **Catalog entry list (52 tables)** — drafted in §2 above, ready for
  per-table ratification.
- **Apply strategy per audit class** — drafted in §4.1, derived from the
  existing repo helpers (no new repo layer needed).
- **Hook signatures** — drafted in §4.3.
- **Cutover order** — §4.5 + Risk R2/R6.
- **Feature flag name** — `PARKOS_SYNC_ENGINE=legacy|catalog`.

## 7. What is NOT in scope for the proposal (explicit)

- New repo helpers — the existing `repo/{append_only,hash_chain,event,
  versioned,workflow,session_cycle}` cover all 52 tables. The motor
  dispatches to them.
- New DB migrations for the 18 missing `fn_enqueue_sync` triggers — this
  is a separate decision (Gap 1). Either close in the proposal OR punt
  to a follow-up.
- Changes to the auth chain (sync-router, JWT issuers, revocation list)
  — out of scope for sync-overhaul.
- DIAN provider swap (`DianProvider` ABC + Factus adapter) — already
  shipped in PR11. The catalog hook for `revocacion_factura` is the only
  DIAN touch-point.
- WebSocket transport — deferred per `AGENTS.md` §"Sync" (HTTP polling
  only on v1).

## 8. Relevant Files

- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py`
- `backend/packages/parkos_core/src/parkos_core/sync/conflict_resolver.py`
- `backend/packages/parkos_core/src/parkos_core/sync/table_registry.py` (new)
- `backend/packages/parkos_core/src/parkos_core/sync/transport.py`
- `backend/packages/parkos_core/src/parkos_core/sync/auto_discovery.py`
- `backend/packages/parkos_core/src/parkos_core/sync/jwt_manager.py`
- `backend/packages/parkos_core/src/parkos_core/sync/router_helpers.py`
- `backend/packages/parkos_core/src/parkos_core/jobs/sync_cloud.py`
- `backend/packages/parkos_core/src/parkos_core/jobs/sync_sucursal.py`
- `backend/packages/parkos_core/src/parkos_core/jobs/runner.py`
- `backend/packages/parkos_core/src/parkos_core/api/v1/sync_router.py`
- `backend/packages/parkos_core/src/parkos_core/api/router_factory.py`
- `backend/packages/parkos_core/src/parkos_core/repo/sync_queue.py`
- `backend/packages/parkos_core/src/parkos_core/repo/sync_outbox.py`
- `backend/packages/parkos_core/src/parkos_core/repo/append_only.py`
- `backend/packages/parkos_core/src/parkos_core/repo/hash_chain.py`
- `backend/packages/parkos_core/src/parkos_core/repo/event.py`
- `backend/packages/parkos_core/src/parkos_core/repo/versioned.py`
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py`
- `backend/packages/parkos_core/src/parkos_core/repo/session_cycle.py`
- `backend/packages/parkos_core/src/parkos_core/repo/factura_pagos.py`
- `backend/packages/parkos_core/src/parkos_core/repo/pairing.py`
- `backend/packages/parkos_core/src/parkos_core/repo/revoked_sync_jwt.py`
- `backend/packages/parkos_core/src/parkos_core/dian/cloud/dispatcher.py`
- `backend/packages/parkos_core/src/parkos_core/dian/cloud/dian_providers/factus.py`
- `backend/packages/parkos_core/src/parkos_core/dian/cloud_router.py`
- `backend/packages/parkos_core/src/parkos_core/models/base.py`
- `backend/packages/parkos_core/src/parkos_core/models/{V,L_E,L_W,L_S,A}/*.py`
- `openspec/changes/create-49-table-apis/{proposal,design,tasks}.md`
- `openspec/config.yaml`
- `AGENTS.md`
- `modelo_datos_er.mmd`

## 9. Open questions for the user (one at a time)

Q1 (most important): **Gap 1 decision** — for the 18 [V] tables with no
`fn_enqueue_sync` trigger today, do we declare them
`sync_strategy: never_propagated` (status quo + explicit justification per
table) OR ship a follow-up migration that adds the missing triggers (need
per-table replication policy ratification first)?

The other questions (R3 broadcast, R4 chain verifier scope, R5 SyncBackEvent
table) are derivable from the Q1 decision and don't need separate asks.