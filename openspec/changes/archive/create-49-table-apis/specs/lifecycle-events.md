# Spec: Lifecycle Events

## Capability

Provide an **append-only INSERT** API surface for the **3 `[L-E]` lifecycle event tables**: `ingreso`, `facturas`, `factura_electronica`. These tables record the **immutable business moments** of the parking operation — a vehicle entered, an invoice was issued, an electronic invoice was emitted to DIAN. There is no UPDATE, no compensation row at the lifecycle-event layer; corrections flow through `anulaciones` (for `ingreso` or `salidas`), `revocacion_factura` (for `factura_electronica`), or `factura_pagos.tipo_movimiento='reverso'` (for `facturas`). All derived state (e.g. "is the vehicle still inside?", "is the invoice cancelled?", "what is the DIAN-reported status of the FE?") is computed by live database views (`V_INGRESO_ESTADO`, `V_FACTURA_ESTADO`, `V_FE_ESTADO_DIAN`, `V_FACTURA_PAGOS_NETOS`, `V_ARQUEO_DIFERENCIAS`, `V_RESOLUCION_CONSECUTIVO`) and exposed via nested endpoints under the parent resource per AD-4 — the views are NEVER materialized; performance is acceptable because the affected row sets are small (< 10k rows per `uuid_resolucion_facturacion` and < 50k active `ingreso` per `uuid_sucursal`).

## Requirements

### REQ-30-E-INSERCION: Append-only INSERT with timestamp_evento = NOW()
**Given** a tenant-scoped JWT (operador- for `ingreso` and `facturas`; admin- with cloud-only deploy context for `factura_electronica`)
**When** the client calls `POST /api/v1/<resource>` with the appropriate `Create` Pydantic body and `Idempotency-Key` header
**Then** the system MUST perform a single INSERT with `created_at = NOW()`, `created_by = <jwt_subject>`, `sync_status='pendiente'` (default), and for the DIAN-bound `factura_electronica` additionally enforce the active `resolucion_facturacion` UK check (UUID of resolution is mandatory, `consecutivo` is server-assigned within `[rango_desde, rango_hasta]`); respond 201 with the projected `Read` payload

### REQ-31-E-CONSULTA: Single read by uuid
**Given** a tenant-scoped READ caller
**When** the client calls `GET /api/v1/<resource>/{uuid}`
**Then** the system MUST respond 200 OK with the projected `Read` payload or 404 if no such row exists. State derivation (e.g. "is the ingreso still open?") is NOT a stored column — it lives in views and is exposed via nested endpoints per AD-4

### REQ-32-E-DERIVED-ESTADO: Nested derived state endpoint (AD-4)
**Given** an existing row R on `ingreso`, `facturas`, or `factura_electronica`
**When** the client calls `GET /api/v1/<resource>/{uuid}/estado`
**Then** the system MUST query the corresponding view (`V_INGRESO_ESTADO`, `V_FACTURA_ESTADO`, `V_FE_ESTADO_DIAN`) and return the derived payload (estado string + a list of contributing references: e.g. `salidas` uuid if present, `anulaciones` uuids that affected it, `envio_dian` latest, `revocacion_factura` if any)
And these endpoints live ONLY in derived form — no separate stored `estado` column on the `[L-E]` tables (4FN compliance); the view MUST be a `LIVE VIEW` (not materialized) — Q12 resolution

### REQ-33-E-NO-DELETE: No DELETE operation
**Given** any FastAPI router bound to an `[L-E]` resource
**When** the OpenAPI artifact is generated
**Then** zero `delete:` operations exist for `/api/v1/ingreso*`, `/api/v1/facturas*`, or `/api/v1/factura-electronica*`; static test enforced on every PR

### REQ-34-E-FACTURA-ELECTRONICA-CONSECUTIVO: Atomic `consecutivo_actual` mutation (Q12)
**Given** an active `resolucion_facturacion` R with `vigente_hasta IS NULL` and `rango_desde <= N <= rango_hasta` where N = current `V_RESOLUCION_CONSECUTIVO.consecutivo` + 1 (live view)
**When** an operador- token at a branch with `N = V_RESOLUCION_CONSECUTIVO.consecutivo + 1` posts `POST /api/v1/factura-electronica` (branch online, synchronous request to `api_admin`)
**Then** the system MUST (a) `SELECT ... FOR UPDATE` the row `R`, verify `N <= rango_hasta`, (b) compute the new `consecutivo` server-side from the live view, (c) INSERT with that `consecutivo` within the same TX, (d) handle DIAN send (out of scope for this change), (e) return 201 with the assigned `prefijo + consecutivo` as `numero_oficial`
And on offline mode, the branch inserts a `factura_electronica` preliminary row with `numero_temporal` (a `preliminar` badge in the PWA UI) into `sync_queue`; cloud assigns the real `consecutivo` on sync and emits a `SyncBackEvent` (Q3 cloud→branch callback); `reimpresion_ticket` is disabled until `SyncBackEvent` arrives

### REQ-35-E-FACTURA-ELECTRONICA-CLOUD-ONLY: Branch image cannot write `factura_electronica`
**Given** the FastAPI app boots under the branch deploy context
**When** `parkos_core.api.v1.__init__` runs and attempts `import parkos_core.dian.cloud_router`
**Then** `ImportError: cloud_router_unavailable_on_branch` is raised; the test `test_cloud_router_branch_boundary.py` (PR6 acceptance) imports the module and asserts `ImportError`. OpenAPI for `api_sucursal/openapi.json` MUST NOT contain any path under `/factura-electronica/*`

### REQ-36-E-HASH-CHAIN-CONSUMER: `factura_electronica`'s revocacion path
**Given** a `factura_electronica` row F in any state (its existence triggers the chain indirectly via `revocacion_factura`)
**When** an admin posts a `revocacion_factura` row (Q12 cross-ref; the chain helper lives in `append-only-events.md` REQ-16-A-HASH-CHAIN) referencing F
**Then** the system MUST write a `revocacion_factura` row (per `[A]` rules) keyed by `uuid_sucursal` chain — this chain entry becomes part of the DIAN evidence trail and is reflected in `V_FE_ESTADO_DIAN` (the view aggregates the most recent `revocacion_factura` for the FE)

## Scenarios

### SC-30-E-INGRESO-OPEN-CLOSE-ANULADA: Derived estado changes over time
1. Operator POSTs `POST /api/v1/ingreso {placa: 'ABC123', uuid_tipo_vehiculo: T, fecha_ingreso: T0}`. Row I created.
2. `GET /api/v1/ingreso/{I}/estado` returns `{"estado": "activo", "salida_uuid": null, "anulaciones": []}` (from `V_INGRESO_ESTADO`).
3. Operator posts `POST /api/v1/salidas {uuid_ingreso: I.uuid, fecha_salida: T1}`. Row S created.
4. The same `GET /api/v1/ingreso/{I}/estado` now returns `{"estado": "cerrado", "salida_uuid": S.uuid, "anulaciones": []}`.
5. Admin posts anulación of the salida: `POST /api/v1/anulaciones {uuid_ingreso: I, tipo_anulable:'salida', estado:'ejecutada'}` (full 3-row chain, see `workflow-transitions.md` SC-20). The view updates to `{"estado": "cerrado", "salida_uuid": null, "anulaciones": [<chain>]}` because the salida is annulled.

### SC-31-E-FACTURAS-EMIT: Snapshot totals, no derivation
1. Operator closes an ingreso (S posted). Backend computes totales server-side: e.g. `subtotal = 12000`, `descuento = 0`, `total = 14280` (after `factura_impuestos`).
2. Operator posts `POST /api/v1/facturas {uuid_ingreso: I, uuid_salida: S, subtotal: 12000, descuento: 0, total: 14280, ...}`. Row F created with `fecha_retencion_hasta = NOW() + 5 years` (DIAN).
3. Later, the operator wishes to "correct" the total — but cannot UPDATE. They open an `anulaciones` workflow against F.
4. `GET /api/v1/facturas/{F}/estado` (nested) returns `{"estado": "vigente", "anulaciones": []}`. If anulación ejecutada, returns `{"estado": "anulada", "anulaciones": [<chain>]}`.
5. The TOTAL `14280` column remains as written (snapshot of the legal fact); the anulación is a separate legal act in `anulaciones`.

### SC-32-E-FACTURA-ELECTRONICA-ONLINE: Branch assigns real consecutivo via cloud
1. Branch is online. Operator posts `POST /api/v1/facturas` (internal) and immediately `POST /api/v1/factura-electronica` to `/api/v1/factura-electronica` (routed to cloud).
2. Cloud's helper: `SELECT ... FOR UPDATE` on the active resolucion; computes `consecutivo = V_RESOLUCION_CONSECUTIVO.consecutivo + 1`; INSERTs `factura_electronica` with `prefijo=R.prefijo`, `consecutivo=N`, `uuid_factura=F.uuid`, `fecha_retencion_hasta=NOW()+5y`.
3. Cloud triggers `envio_dian` (out of scope here, but the resulting FK is reflected). `V_FE_ESTADO_DIAN` returns `{"estado": "aceptado", "envio_dian_uuid": E, "cufe": E.cufe}`.
4. The internal `facturas` row F is now bound 1:1 to `factura_electronica` FE.

### SC-33-E-FACTURA-ELECTRONICA-OFFLINE: Preliminary + SyncBackEvent
1. Branch is offline. Operator posts the same flow locally: `POST /api/v1/facturas` (internal) succeeds locally; `POST /api/v1/factura-electronica` queues in `sync_queue` with payload + `numero_temporal = "PRE-<uuid>"`.
2. UI shows `preliminar` badge (per `apps/ui-kit/web_sucursal`). `reimpresion_ticket` button is disabled until `SyncBackEvent`.
3. Network returns. Sync worker picks up `sync_queue` row, POSTs to cloud with `Idempotency-Key` (from branch side). Cloud replies 201 with the real `consecutivo`. Branch receives `SyncBackEvent` callback (`/sync/events`).
4. Local `factura_electronica` row updates `prefijo` / `consecutivo` from the event payload (this UPDATE is allowed by trigger carve-out — event receipt path only); `preliminar` badge clears.

### SC-34-E-REVOCACION-FACTURA: Chain breaks once revoked
1. FE exists, fully `aceptado`. Cloud admin posts `POST /api/v1/revocacion-factura {uuid_factura_electronica: FE, motivo:'error en nit'}`. `revocacion_factura` row R inserted (per `[A]` rules REQ-16-A-HASH-CHAIN); hash chain extends per `uuid_sucursal`.
2. `GET /api/v1/factura-electronica/{FE}/estado-dian` (nested) returns `{"estado": "revocada", "revocacion_uuid": R.uuid, "fecha_evento": ...}`.
3. Net reporting `V_FACTURA_PAGOS_NETOS` continues to subtract the original payments (no automatic refund reversal unless a `factura_pagos.tipo_movimiento='reverso'` row is created).

## Scope — the 3 `[L-E]` tables by tenant write authority

| Resource | Tenant write authority | Compliance role |
|---|---|---|
| `ingreso` | `operador-` (branch at vehicle entry; offline-first) | operational |
| `facturas` | `operador-` (branch at emit) | DIAN retention |
| `factura-electronica` | `operador-` (online: synchronous to cloud via `/api/v1/factura-electronica` → cloud; offline: preliminary row + `sync_queue`) + `admin-` in cloud deploy context | DIAN evidence; cloud-only writes |

## Constraints

- **C-E1**: NO UPDATE, NO DELETE on `[L-E]` tables. Static test (`test_no_raw_dml_on_le_tables.py`) enforces.
- **C-E2**: `ingreso` is `pg_partman` monthly-partitioned on `fecha_ingreso`; queries MUST supply the partition-key range as required filter for list endpoints. Lifted in PR6.
- **C-E3**: `factura_electronica` UK is `(uuid_resolucion_facturacion, consecutivo)` — server assigns `consecutivo` atomically inside `SELECT ... FOR UPDATE` of the resolucion row, never from the client.
- **C-E4**: The 4 derived views (`V_INGRESO_ESTADO`, `V_FACTURA_ESTADO`, `V_FE_ESTADO_DIAN`, `V_RESOLUCION_CONSECUTIVO`, `V_FACTURA_PAGOS_NETOS`, `V_ARQUEO_DIFERENCIAS`) are LIVE views, not materialized — REQ-32 derives correctness from the underlying `[L-E]`/`[A]` rows; EXPLAIN plan acceptable per Q12.
- **C-E5**: `factura_electronica`'s `preliminar` mode is reflected at the API by `sync_status='pendiente'` and a flag in the `Read` payload; never bypasses chain integrity.

## Out of scope

- Factus / other DIAN provider HTTP transport — separate change.
- `reimpresion_ticket` business logic — see `workflow-transitions.md` REQ-27 (it's a `[L-W]` not `[L-E]`).
- Reporting queries beyond what the 4 views expose — domain BI is a separate change.

## Dependencies

- `parkos_core/repo/event.py` — `record_event()` (pure INSERT).
- `parkos_core/repo/hash_chain.py` — `append()` for `revocacion_factura` (lives here as a dep but the row is in `[A]`).
- `parkos_core/dian/cloud_router.py` — routers for `factura_electronica`, `envio_dian`, `validacion_evento`, `revocacion_factura`-webhook.
- ADR references: AD-1, AD-2, AD-3, AD-4. Q12 closed here; Q3 cloud→branch sync also touched.
- Engram topic: `sdd/create-49-table-apis/spec`.
