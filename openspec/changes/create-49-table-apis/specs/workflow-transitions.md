# Spec: Workflow Transitions

## Capability

Provide an **append-only state-machine** API surface for the **6 `[L-W]` workflow tables**: `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `envio_dian`, `validacion_evento`. Each row carries a `uuid_*_padre` FK (e.g. `uuid_anulacion_padre`, `uuid_reclamo_padre`, `uuid_alerta_padre`, `uuid_reimpresion_padre`, `uuid_envio_padre`, `uuid_validacion_padre`) that chains transitions into a tree rooted at a NULL-parent row. Transition legality is enforced server-side by the helper `parkos_core/repo/workflow.py::append_transition()` which reads the parent row's `estado`, validates the transition against the per-table state machine (Q10 adds `descartada` to `alerta`), inserts a new row, and refuses cross-chain transitions. **NO UPDATE, NO DELETE** — corrections are expressed as a new row in the same chain (new `uuid_*_padre`, new `estado`, new `timestamp_evento`). State of the workflow as a whole is derived by chaining from each root, picking the longest chain on tie (deterministic tie-break rule — same algorithm per table, documented in `cross-cutting.md`).

## Requirements

### REQ-20-W-CONSULTA: Current chain tip
**Given** a workflow root row `R` (parent_uuid column NULL) for any of the 6 `[L-W]` tables
**When** the client calls `GET /api/v1/<resource>/{uuid}/estado`
**Then** the system MUST walk the chain recursively following `uuid_*_padre` FKs from R, compute the chain tip as the row whose `uuid_*_padre` FK is NULL OR whose referenced row no longer has any row referencing it back (i.e. leaf in the directed graph), and return `{"uuid_root": ..., "uuid_actual": ..., "estado": ..., "timestamp_evento": ...}`; ties are broken by (a) most recent `timestamp_evento` then (b) longest chain length (deterministic per table)

### REQ-21-W-TRANSITION: Validated append-only state transition
**Given** a parent row `P` in `estado=E1` belonging to one of the 6 `[L-W]` tables, and a JWT permitted to perform the transition (admin- for `anulaciones.aprobar|ejecutar`, operador- for branch-initiated transitions, admin- + cloud context for `envio_dian` and `validacion_evento`)
**When** the client POSTs `POST /api/v1/<resource>` with body `{"uuid_*_padre": P.uuid, "estado": "E2", "motivo": "...", ...}`
**Then** the system MUST validate `E2` is a legal next state from `E1` (per the per-table state machine below); if valid, INSERT a new row with `uuid_*_padre = P.uuid`, `timestamp_evento = NOW()`, `estado = E2`, `created_by = <jwt_subject>` and return 201
And on commit, enqueue a `log_transaccional` row with `accion='actualizar'`, `tabla_afectada=<table>`, `uuid_registro_afectado=P.uuid_root` (the root, not the new row)

### REQ-22-W-INITIAL: Initial row when chain root is missing
**Given** no existing root row (parent_uuid NULL) for the new chain's scope (per the workflow root invariant — e.g. `anulaciones` roots are uniquely bound to `(uuid_sucursal, uuid_ingreso, tipo_anulable)`)
**When** the client POSTs `POST /api/v1/<resource>` with `uuid_*_padre = NULL`, `estado="<initial>"` (e.g. `solicitada` for `anulaciones`, `abierto` for `reclamos`, `abierta` for `alerta`, `cobrada` for `reimpresion_ticket`, `pendiente` for `envio_dian`, `recibido` for `validacion_evento`)
**Then** the system MUST INSERT the new row as the chain root and return 201; subsequent reads (`GET /<resource>/<root>/estado`) return this row as the tip

### REQ-23-W-POLYMORPHIC-FK: `reclamos.tipo_reclamable` + `reclamos.uuid_reclamable` validator (Q8)
**Given** an incoming `POST /api/v1/reclamos` body with `tipo_reclamable IN {'ingreso', 'salida', 'factura', 'subscripcion'}` and `uuid_reclamable = X`
**When** the Pydantic validator runs (`parkos_core/schemas/reclamos.py::ReclamoCreate.model_validate`)
**Then** the system MUST verify that a row exists in the named table with `uuid = X` via Pydantic `model_validator(mode='after')`; missing row → 422 `{"error": "polymorphic_fk_not_found", "detail": "no row in <table> with uuid X"}`. Cloud-side, the same validator consults a Redis cache populated by the sync worker (max 60s TTL) to avoid cross-network synchronous DB calls during validation; on cache miss, falls back to direct read
And the original physical schema is unaltered (polymorphic FK by design — `uuid_reclamable` is a plain UUID with no FK)

### REQ-24-W-ADMIN-ONLY: `anulaciones.aprobar` and `anulaciones.ejecutar` require admin- token
**Given** a `POST /api/v1/anulaciones` with `estado='aprobada'` or `estado='ejecutada'`
**When** the JWT scope guard runs (`parkos_core/auth/permissions.py`)
**Then** the request MUST carry an `admin-` token whose `sucursales_permitidas` includes the target `uuid_sucursal`; an `operador-` token attempting `aprobada` or `ejecutada` returns 403 `{"error": "admin_scope_required", "detail": "transition <estado> requires admin-"}`. Initial `solicitada` from a branch is allowed with `operador-` (REQ-21-W-TRANSITION)

### REQ-25-W-CLOUD-ONLY: `envio_dian` and `validacion_evento` boundaries
**Given** the `[L-W]` rows for `envio_dian` and `validacion_evento`
**When** the FastAPI app boots under either deploy context (cloud or branch)
**Then** the routers for these 2 tables MUST be mountable only on the cloud context via `parkos_core/dian/cloud_router.py`; the branch image's import attempt raises `ImportError` (RED test in PR6 acceptance) and the OpenAPI emitted for `api_sucursal/openapi.json` MUST contain zero paths under `/envio-dian` or `/validacion-evento`

### REQ-26-W-ALERTA-DESCARTADA: `alerta` accepts `descartada` transition (Q10)
**Given** an `alerta` chain tip in state `en_revision`
**When** an `admin-` token holder posts `POST /api/v1/alerta` with `uuid_alerta_padre = tip.uuid`, `estado='descartada'`, `motivo='<text>'` — AND the requester is NOT the current `uuid_usuario` assigned to the alerta
**Then** the system MUST INSERT the new row, transition to `descartada`, and enqueue a `log_transaccional` row (`accion='rechazar'`)
And only `admin-` tokens may transition to `descartada` — the operador assigned to the alerta receives 403 `{"error": "self_discard_forbidden"}` even if they hold `permisos` granular permission

### REQ-27-W-REIMPRESION-ANULADA: Original stays, new row points via `uuid_reimpresion_padre`
**Given** a `reimpresion_ticket` row R1 in `estado='cobrada'`
**When** an admin posts `POST /api/v1/reimpresion-ticket` with `uuid_reimpresion_padre = R1.uuid`, `estado='anulada'`, `motivo='<text>'`
**Then** the system MUST INSERT a new row R2 leaving R1 untouched in `estado='cobrada'` (the original never changes — chain shows the anulación); `GET /api/v1/reimpresion-ticket/{R1.uuid}/estado` returns R1's original estado AND a `anulada_por` hint that points to R2

## Scenarios

### SC-20-W-ANULACIONES-CHAIN: 3-row minimal cancel chain
1. Operator posts initial `POST /api/v1/anulaciones {uuid_anulacion_padre: null, estado:'solicitada', uuid_ingreso: I, tipo_anulable:'ingreso'}`. Row A1 created (root).
2. Admin posts `POST /api/v1/anulaciones {uuid_anulacion_padre: A1.uuid, estado:'aprobada', motivo:'...'}`. Row A2 created, A1 unchanged.
3. Admin posts `POST /api/v1/anulaciones {uuid_anulacion_padre: A2.uuid, estado:'ejecutada', motivo:'...'}`. Row A3 created.
4. `GET /api/v1/anulaciones/{A1.uuid}/estado` returns `{"uuid_actual": A3.uuid, "estado": "ejecutada", "timestamp_evento": ..., "chain_length": 3}`.
5. `GET /api/v1/ingresos/{I}/estado` (per AD-4 nested endpoint) returns `anulada` (from `V_INGRESO_ESTADO` view).

### SC-21-W-RECLAMOS-POLYMORPHIC: `tipo_reclamable` validator
1. Operator posts `POST /api/v1/reclamos {tipo_reclamable:'ingreso', uuid_reclamable: X, motivo:'perdía objeto'}`. Pydantic validator queries `ingreso` table (Redis-cache hit); 201 with chain root R1.
2. Same operator posts `POST /api/v1/reclamos {tipo_reclamable:'ingreso', uuid_reclamable: '00000000-...-nonexistent'}`. Validator finds no row → 422 `{"error": "polymorphic_fk_not_found"}`.
3. Admin transitions R1: `POST /api/v1/reclamos {uuid_reclamo_padre: R1.uuid, estado:'en_revision'}`. Row R2 created.
4. Admin resolves: `POST /api/v1/reclamos {uuid_reclamo_padre: R2.uuid, estado:'resuelto', motivo:'objeto devuelto'}`. Row R3 created; tip = R3.

### SC-22-W-ALERTA-DESCARTADA: Admin-only reject
1. Alert A1 created automatically by arqueo with `estado='abierta'`, `uuid_usuario=U1`.
2. U1 transitions to `en_revision`: `POST /api/v1/alerta {uuid_alerta_padre: A1.uuid, estado:'en_revision'}`. Allowed (operador-/admin-).
3. U1 attempts self-discard: `POST /api/v1/alerta {uuid_alerta_padre: A1.uuid, estado:'descartada', motivo:'falsa alarma'}`. 403 `self_discard_forbidden`.
4. Admin A2 transitions: `POST /api/v1/alerta {uuid_alerta_padre: A1.uuid, estado:'descartada', motivo:'verified by supervisor'}`. Row A3 created; tip = A3.

### SC-23-W-ENVIO-DIAN-RETRY: pending → enviado loop, then terminal
1. Cloud insert initial `POST /api/v1/envio-dian {estado:'pendiente', uuid_factura_electronica: FE, payload: {...}}`. Row E1.
2. Cloud transitions to `enviado`: `POST /api/v1/envio-dian {uuid_envio_padre: E1.uuid, estado:'enviado', respuesta_proveedor: {...}}`. Row E2.
3. Provider returns rejection → new row E3 with `estado='rechazado'`. Tie-break keeps the longest chain tip at E3.
4. Operator re-sends through correct data → new row E4 with `uuid_envio_padre=E3.uuid`, `estado='pendiente'`. Branch continues; E4 is new root of new chain from `uuid_envio_padre IS NOT NULL` is allowed but treated as re-opening; the read endpoint with explicit `uuid_factura_electronica` returns the chain with E4 as the current tip (most-recent wins per REQ-20-W-CONSULTA).

### SC-24-W-VALIDACION-EVENTO: Admin-driven validation loop
1. Branch emits `ingreso` I; cloud sync creates `validacion_evento` row V1 with `estado='recibido'`, `tabla_origen='ingreso'`, `uuid_registro=I.uuid`, `hash_evento=...`.
2. Admin transitions V1 → V2 (`estado='validado'`, `observaciones='ok'`).
3. If admin observes discrepancy → V3 (`estado='observado'`, `observaciones='revisar hash'`).
4. Final resolution → V4 (`estado='rechazado'` or `validado`) by separate admin; chain ends.

## Per-table state machines

| Table | Initial → … → terminal | Self-discard mechanic |
|---|---|---|
| `anulaciones` | `solicitada` → `aprobada` → `ejecutada` (initial by operador; `aprobada`/`ejecutada` by admin) | n/a |
| `reclamos` | `abierto` → `en_revision` → `resuelto` \| `rechazado` | n/a |
| `alerta` | `abierta` → `en_revision` → `resuelta` \| `descartada` (Q10) | `descartada` admin-only, not self |
| `reimpresion-ticket` | `cobrada` → `anulada` (original stays `cobrada`; new row via `uuid_reimpresion_padre`) | n/a |
| `envio_dian` | `pendiente` → `enviado` → `aceptado` \| `rechazado` (cloud-only; may re-loop `pendiente` from any non-terminal) | n/a |
| `validacion_evento` | `recibido` → `validado` \| `observado` \| `rechazado` (cloud-only; admin-driven; `observado` may chain back to `recibido`) | n/a |

## Constraints

- **C-W1**: NO UPDATE, NO DELETE on `[L-W]` tables. Static test (`test_no_raw_dml_on_lw_tables.py`) rejects `session.execute(update/delete)` against the 6 declarative classes outside `append_transition()`.
- **C-W2**: Each transition writes a `log_transaccional` row in the SAME TX. The helper enforces atomicity; partial write is impossible.
- **C-W3**: The chain-tip algorithm is deterministic — see `cross-cutting.md` REQ-X7 (tie-break rule).
- **C-W4**: `envio_dian` and `validacion_evento` schemas/routers live in `parkos_core/dian/cloud_router.py` and the branch image cannot import them.

## Out of scope

- Notification dispatch (email/push) on state transitions — separate change.
- SLA timers (`alerta` overdue escalation) — separate change.

## Dependencies

- `parkos_core/repo/workflow.py` — `append_transition()` and `read_chain_tip()`.
- `parkos_core/api/v1/workflows.py` — FastAPI routers for the 6 tables (with `dian/cloud_router.py` carve-out).
- ADR references: AD-2, AD-4. Q8, Q10 closed here. Q3 (sync endpoints) cross-references.
- Engram topic: `sdd/create-49-table-apis/spec`.
