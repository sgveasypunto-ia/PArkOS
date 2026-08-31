# PRD: factura_electronica (T03)

> Cloud-only DIAN fiscal document. State derived from `revocacion_factura` existence.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[L-E]` table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.factura_electronica`
- **SQL name**: `factura_electronica` (with `prod` schema)
- **Enforcement level**: `[L-E]` event (cloud-only writes)
- **Retention**: 5+ years (DIAN)
- **Origin**: F1 (schema) + IT-5 (writes from `/facturas/procesar`)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `consecutivo` is atomic BigInteger from `em`.consecutivo_actual`.

## 3. SOLID Atomic Breakdown
- **S**: "one DIAN-registered electronic invoice".
- **O**: new columns (e.g., `qr_code`, `cufe`) added via migration.
- **I**: `POST /facturas/procesar` is cloud-only; branches NEVER write.
- **D**: cloud-only writer `parkos_core/dian/cloud/factura_electronica_builder.py`.
- **Atomic**: INSERT only (state derived from `revocacion_factura`).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | mandatory |
| `uuid_factura` | `prod.facturas.uuid` | exactly one (NOT NULL) | RESTRICT | the business invoice |
| `uuid_cliente` | `prod.clientes.uuid` | exactly one (NOT NULL) | RESTRICT | the titular |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `prod.revocacion_factura.uuid_factura_electronica` | (chain) | — | revoked chain |
| `prod.revocacion_factura.uuid_factura_electronica_reemplazo` | (chain) | — | replacement chain |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES (cloud only) | In `api_admin POST /facturas/procesar` + same TX as `atomic_next_consecutivo()` |
| UPDATE | NO | Derived state |
| DELETE | NO | Append-only |

## 6. CodeGraph Dependencies
- `parkos_core/dian/cloud/factura_electronica_builder.py`.
- `parkos_core/dian/cloud/atomic_next_consecutivo.py`.
- `parkos_core/dian/cloud/dispatcher.py`.
- `web_sucursal/FacturacionForm` (reads `numero_oficial` after sync-back).

## 7. Use Cases enabled by this table

The `factura_electronica` table is the **DIAN fiscal representation** of a business `facturas` row. Cloud-only writes (branches NEVER write here). The `consecutivo` is assigned atomically from `empresa.consecutivo_actual` in the same TX that INSERTs the row, and the `estado` is DERIVED from the existence of a `revocacion_factura` row (no DB-level state mutation). Every write extends the `log_transaccional` chain. Branch-side, `facturas` carries a `preliminar` badge until the SyncBackEvent brings back the real `numero_oficial` — a UI gate that prevents `reimpresion_ticket` from firing with an invalid DIAN number.

### 7.1 Use Case: `uc.factura-electronica.cloud-assigns-consecutivo-online-branch`

**Actor**: dian_dispatcher

**Real-world action**: Branch operator is online when customer departs; the operator POSTs `/facturas` with items + payments. The branch backend calls cloud `/facturas/procesar` synchronously; cloud atomically assigns the DIAN `consecutivo`, INSERTs `factura_electronica`, and returns the real `numero_oficial` to the branch so the operator can print immediately.

**Steps**:
1. Branch operator opens `web_sucursal/FacturacionForm`; selects cliente, items, pagos (efectivo/datafono mixto allowed — see T05 use case `pago-mixto-efectivo-datafono`).
2. Frontend POSTs `api_sucursal /facturas` with the full payload (`uuid_ingreso, uuid_salida, uuid_cliente, lines, pagos`).
3. Branch backend opens a TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`; INSERTs `facturas` (without `numero_oficial`, with `numero_temporal=NULL` because online), `factura_detalle` lines, `factura_pagos` rows, `factura_impuestos` (snapshot from `impuestos`), `factura_otros_cobros` (snapshot from `otros_cobros`), and `log_transaccional` (`accion='factura_creada'`, `uuid_registro_afectado=$factura_uuid`) — all in same TX; the chain extends locally by 1 row.
4. Branch backend calls `api_admin /facturas/procesar` (cross-service call with admin sync_agent JWT) with the local `facturas.uuid`.
5. Cloud `procesar` opens a TX; `SELECT empresa FOR UPDATE` (atomic lock); `consecutivo_new = consecutivo_actual + 1`.
6. `UPDATE empresa SET consecutivo_actual = consecutivo_new` (the ONLY mutable business field on `empresa`).
7. SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
8. INSERT `factura_electronica` row (`uuid`, `consecutivo=$consecutivo_new`, `numero_oficial=empresa.prefijo_factura || '-' || lpad(consecutivo_new,8,'0')`, `reportado_dian=false`, `estado='activa'` derived).
9. INSERT `log_transaccional` (`accion='factura_electronica_creada'`, `tabla_afectada='factura_electronica'`, `uuid_referencia=$facturas.uuid`, `uuid_registro_afectado=$factura_electronica_uuid`) — extends the cloud chain by 1 row.
10. INSERT `SyncBackEvent` (concepto sprint 5; payload `{uuid_operacion, tabla_origen='facturas', uuid_registro=$factura_uuid, datos_nuevos={uuid_factura_electronica, numero_oficial, consecutivo, reportado_dian=false}, timestamp}`) for branch polling.
12. Cloud returns `{uuid_factura_electronica, numero_oficial, consecutivo}` synchronously to branch.
13. Branch UPSERTs `facturas.uuid_factura_electronica=$uuid, numero_oficial=$numero_oficial`; clears preliminar badge (which was never set in online case).
14. Operator prints the receipt with the real number.

**Tables touched (writes)**: `facturas`, `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `log_transaccional` (branch side), `empresa`, `factura_electronica`, `log_transaccional` (cloud side), `SyncBackEvent`.
**Tables touched (reads)**: `ingreso`, `salidas` (the cycle), `clientes` (titular), `tarifas_sucursal` (pricing snapshot), `impuestos`, `otros_cobros` (tax/charge snapshots), `empresa` (atomic `consecutivo_actual`), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `factura_electronica.uuid_sucursal` → `sucursal.uuid`; `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid`; `empresa` (atomic lock); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `facturas.uuid`; `factura_pagos.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_impuesto` → `impuestos.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the originating `facturas` row plus its `factura_detalle`/`pagos`/`impuestos`/`otros_cobros` children are all queued and pushed via `sync_queue` (but in the online case, cloud already processed them synchronously; the queue just ensures idempotency).
- Cloud → branch: YES — `SyncBackEvent` flows back with the `numero_oficial`. Branch may also receive it via the parametrization pull (defense in depth).
- DIAN trigger: YES — after INSERT, cloud enqueues for `dian_dispatcher` to actually send to the DIAN provider (use case 7.2 below).
- Hash chain impact: YES — `log_transaccional` chain extends by 2 rows: 1 on the branch side (`accion='factura_creada'`) and 1 on the cloud side (`accion='factura_electronica_creada'`). The branch chain and cloud chain are separate but share `uuid_sucursal` as the partition key.

**Integration with other tables**:
- Reads from: `ingreso`, `salidas` (the cycle), `clientes` (titular), `tarifas_sucursal` (pricing snapshot), `impuestos`, `otros_cobros` (tax/charge snapshots), `empresa` (atomic `consecutivo_actual`), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: `empresa` (atomic increment), `factura_electronica` (the DIAN doc), `log_transaccional` (audit, both sides), `SyncBackEvent` (branch signal).
- Downstream: `reimpresion_ticket` is now enabled because `uuid_factura_electronica` is populated; `dian_dispatcher` will extend the chain again when DIAN responds (use case 7.2).

### 7.2 Use Case: `uc.factura-electronica.dian-accepts-publishes-cufe`

**Actor**: dian_dispatcher

**Real-world action**: The DIAN provider (Factus or similar) accepts the e-factura and returns the CUFE, QR code, and official timestamp. The `dian_dispatcher` records the acceptance and emits the `SyncBackEvent` so the branch clears the `preliminar` badge (if any) and stores the official CUFE/QR for printing.

**Steps**:
1. `dian_dispatcher` dequeues a `factura_electronica` row with `reportado_dian=false` (every 30s).
2. Calls DIAN provider API with the e-factura payload (`uuid`, `consecutivo`, `numero_oficial`, lines, pagos, cliente).
3. DIAN responds with `{cufe, qr_code, dian_response_at, estado='aceptada'}`.
4. Cloud opens a TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
5. UPDATE `factura_electronica SET reportado_dian=true, cufe=..., qr_code=..., dian_response_at=NOW()` (operational UPDATE on derived-state fields; allowed per the AUDIT-FIRST cloud-only exception).
6. INSERT `log_transaccional` (`accion='dian_aceptada'`, `tabla_afectada='factura_electronica'`, `uuid_registro_afectado=$uuid`) — extends the cloud chain by 1 row.
7. INSERT `SyncBackEvent` (`uuid_factura, numero_oficial, cufe, qr_code, dian_response_at`) — branch polls and updates local cache.
8. Branch UPSERTs `facturas.cufe`, `facturas.qr_code`, `facturas.dian_response_at`; UI flips the badge from `preliminar` to `oficial` (or just `oficial` if it was already that for an online branch).

**Tables touched (writes)**: `factura_electronica` (operational UPDATE), `log_transaccional` (cloud side), `SyncBackEvent`.
**Tables touched (reads)**: `factura_electronica` (the one being dispatched), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `factura_electronica.uuid_sucursal` → `sucursal.uuid`; `factura_electronica.uuid_factura` → `facturas.uuid` (for SyncBackEvent linking); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator — this is the cloud-side DIAN dispatch).
- Cloud → branch: YES — `SyncBackEvent` flows back with `cufe` + `qr_code` + `dian_response_at`. Branch updates `facturas` cache.
- DIAN trigger: YES — this IS the DIAN dispatch (DIAN provider responded; we record the response).
- Hash chain impact: YES — `log_transaccional` chain extends by 1 cloud-side row (`accion='dian_aceptada'`). The branch-side chain is NOT extended (this is a cloud-only event).

**Integration with other tables**:
- Reads from: `factura_electronica` (the one being dispatched), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: `factura_electronica` (operational UPDATE — cloud-only derived state exception), `log_transaccional` (audit), `SyncBackEvent` (branch signal).
- Note: `UPDATE` here is the operational exception for `[L-E]` derived state; the `estado` field is computed from `reportado_dian` + `cufe IS NOT NULL` + existence of `revocacion_factura` row. Application-level enforcement only. The `reportado_dian=true` transition triggers the UPDATE; the `estado` field is computed at read time.

### 7.3 Use Case: `uc.factura-electronica.dian-rejects-creates-revocation`

**Actor**: dian_dispatcher

**Real-world action**: DIAN provider rejects the e-factura (wrong NIT, expired `rango_hasta`, CUFE pre-validation failure). The cloud worker records the rejection by creating a `revocacion_factura` row (NOT by setting `estado='rechazada'` directly — `estado` is DERIVED from `revocacion_factura` existence per the model). This extends BOTH hash chains and emits an alert.

**Steps**:
1. `dian_dispatcher` calls DIAN provider API with the e-factura payload.
2. DIAN responds with `{estado='rechazada', motivo_codigo, motivo_texto}`.
3. Cloud opens a TX; SELECT chain anchor from `revocacion_factura` for `uuid_sucursal=$branch`.
4. INSERT `revocacion_factura` row (`motivo='dian_error'`, `uuid_factura_electronica=rejected.uuid`, `uuid_factura_electronica_reemplazo=NULL`, `motivo_codigo=...`, `motivo_texto=...`, `hash_anterior=$last_rev.hash_actual, hash_actual=SHA256(...)`) — extends the `revocacion_factura` chain.
5. SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`; INSERT `log_transaccional` (`accion='dian_rechazada'`, `tabla_afectada='revocacion_factura'`, `uuid_registro_afectado=$revocacion_uuid`, `uuid_referencia=$factura_uuid`) — extends the `log_transaccional` chain by 1 row.
6. INSERT `alerta` (`tipo_alerta='dian_rechazada'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_alerta_padre=NULL`, `observaciones=$motivo_texto`) — root of the `alerta` workflow chain (`abierta → en_revision → resuelta`).
7. INSERT `SyncBackEvent` (`uuid_factura, dian_rechazada=true, motivo_codigo=..., motivo_texto=...`) — branch UI shows red badge permanently (NOT just preliminar); `reimpresion_ticket` permanently disabled for this factura.
8. Admin sees the alert in `web_admin/AlertasList`; follows up via `web_admin/FacturaDetail` (may decide to issue a credit-note replacement per T02 use case 7.2).

**Tables touched (writes)**: `revocacion_factura` (extends that chain), `log_transaccional` (extends that chain), `alerta` (workflow root), `SyncBackEvent`.
**Tables touched (reads)**: `factura_electronica` (the rejected one), `log_transaccional` (chain anchor), `revocacion_factura` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `revocacion_factura.uuid_sucursal` → `sucursal.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `facturas.uuid`.

**Sync behavior**:
- Branch → cloud: NO (cloud-only event).
- Cloud → branch: YES — `SyncBackEvent` flows back so the branch disables `reimpresion_ticket` and shows the red badge permanently (the e-factura is now fiscally invalid).
- DIAN trigger: NO (this is the RESPONSE to a previous DIAN dispatch, not a new one).
- Hash chain impact: YES — both cloud chains extend. The `revocacion_factura` chain grows by 1 row (the revocation). The `log_transaccional` chain grows by 1 row (the audit). Branch chains are NOT extended (branches don't write to `revocacion_factura`).

**Integration with other tables**:
- Reads from: `factura_electronica` (the rejected one), `revocacion_factura` (chain anchor), `log_transaccional` (chain anchor), `sucursal` (chain key).
- Writes to: `revocacion_factura` (chain extension), `log_transaccional` (audit), `alerta` (admin notification; workflow chain root), `SyncBackEvent` (branch signal).
- Downstream: T02 use case 7.1 covers the same scenario in detail from the `revocacion_factura` perspective; this use case is the parallel PRD write for `factura_electronica` side.

### 7.4 Use Case: `uc.factura-electronica.branch-offline-preliminar-badge-syncback`

**Actor**: operator (offline) + dian_dispatcher (online later) + sync worker

**Real-world action**: Branch is offline when customer departs. Operator completes the sale with `numero_temporal = PRE-<8-char-uuid>` printed on the receipt + a red `preliminar` badge. Cloud is unreachable; the receipt prints with the temporary number. When connectivity returns, `job_sync_sucursal/drain_outbox` flushes to cloud, cloud assigns the real `consecutivo` via `/facturas/procesar`, inserts `factura_electronica`, and emits `SyncBackEvent` with the real `numero_oficial`. Branch UPSERTs and clears the badge.

**Steps**:
1. Operator completes sale at `FacturacionForm`; internet is down (detected by `api_sucursal` health check or timeout > 5s).
2. Frontend POSTs `api_sucursal /facturas`; the call to `api_admin /facturas/procesar` times out.
3. Branch backend falls back to offline mode: opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
4. INSERT `facturas` row with `numero_temporal='PRE-' || substr(uuid::text,1,8)`, `observaciones='offline_sale_<timestamp>'`, `numero_oficial=NULL`.
5. INSERT `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros` (snapshots, same as online).
6. INSERT `log_transaccional` (`accion='factura_creada_offline'`, `tabla_afectada='facturas'`, `uuid_registro_afectado=$factura_uuid`) — extends branch chain by 1 row.
7. `queue_processor.enqueue('facturas', uuid, datos)` → INSERT `sync_queue` row (accumulates in branch DB; `job_sync_sucursal/drain_outbox` flushes within 30s of reconnect).
8. Print receipt with `PRE-XXXXXXXX` number + red `preliminar` badge; `reimpresion_ticket` UI button is disabled with tooltip "Esperando SyncBackEvent de DIAN".
9. When internet returns: `job_sync_sucursal/drain_outbox` flushes the queue.
10. Cloud receives `facturas` row; opens TX; `SELECT empresa FOR UPDATE`; assigns `consecutivo_new = consecutivo_actual + 1`.
11. INSERT `factura_electronica` (`numero_oficial=prefijo||'-'||lpad(consecutivo_new,8,'0')`, `reportado_dian=false`).
12. INSERT `log_transaccional` (`accion='factura_electronica_creada_offline'`, cloud side, extends cloud chain).
13. INSERT `SyncBackEvent` (payload `{uuid_operacion, tabla_origen='facturas', uuid_registro=$factura_uuid, datos_nuevos={uuid_factura_electronica, numero_oficial, numero_temporal_anterior='PRE-XXXXXXXX'}, timestamp}`).
14. Branch worker polls (or receives via parametrization pull) the SyncBackEvent; UPSERTs `facturas.uuid_factura_electronica=$uuid, numero_oficial=$numero_oficial, numero_temporal=NULL`; UI flips badge from `preliminar` to `oficial`; `reimpresion_ticket` button becomes enabled.
15. Operator can now click `Reimprimir` with real number + (later) CUFE/QR once `dian_dispatcher` confirms.

**Tables touched (writes)**: `facturas` (with `numero_temporal`), `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `log_transaccional` (branch side), `sync_queue` (branch), `empresa` (cloud), `factura_electronica` (cloud), `log_transaccional` (cloud side), `SyncBackEvent`.
**Tables touched (reads)**: `ingreso`, `salidas`, `clientes`, `tarifas_sucursal`, `impuestos`, `otros_cobros`, `empresa` (atomic lock), `log_transaccional` (chain anchor), `sucursal` (chain key).
**FKs traversed**: `facturas.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`; `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `facturas.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES, but **delayed**. `sync_queue.depth` grows during offline; alert emitted at depth > 1000.
- Cloud → branch: YES — `SyncBackEvent` flows back once cloud processes; branch UPSERTs `numero_oficial` and clears the preliminar badge.
- DIAN trigger: YES — same as online, just delayed. Once `factura_electronica` is INSERTed, `dian_dispatcher` picks it up.
- Hash chain impact: YES — branch chain advances locally during offline; cloud chain advances when sync completes. Idempotency by UUID ensures no duplicates. Total: branch chain +1 row (offline INSERT) + cloud chain +1 row (cloud INSERT).

**Integration with other tables**:
- Reads from: `ingreso`, `salidas`, `clientes`, `tarifas_sucursal`, `impuestos`, `otros_cobros`, `empresa`, `log_transaccional`, `sucursal`.
- Writes to: `facturas` (with `numero_temporal`), `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `log_transaccional` (branch side), `sync_queue` (deferred), `empresa` (cloud atomic increment), `factura_electronica` (cloud), `log_transaccional` (cloud side), `SyncBackEvent`.
- Cross-cutting: the `preliminar` badge is a **UI gate** on `reimpresion_ticket` (T05 use case `reimpresion-gated-on-sync-back`) — reprinting with `PRE-XXXXXXXX` would print an invalid DIAN number, which is a compliance violation. The badge clears ONLY when `numero_oficial IS NOT NULL` (SyncBackEvent received).
- Related: if the cloud processes the row but DIAN rejects (use case 7.3 above), the `factura_electronica` is revoked via `revocacion_factura` and the branch shows a **permanent red badge** (not just preliminar).

## 8. Layer-by-Layer Impact
Layers: 1 (DB), 5 (REVOKE for branches), 6 (cloud API), 11 (sync back via pull), 13 (web_admin), 14 (web_sucursal preliminar badge), 29 (DIAN provider), 33 (DIAN compliance docs).

## 9. RED Tests
- (RED) Atomic `consecutivo_actual` increment: two concurrent POSTs return different numbers.
- (RED) Branch INSERT → `AUDIT_FIRST_INMUTABLE`.
- (RED) SyncBackEvent not emitted on cloud INSERT.
- (RED) `reimpresion_ticket` disabled before sync-back.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE.
- [ ] IT-5.x: `atomic_next_consecutivo(em`)` with `SELECT FOR UPDATE`.
- [ ] IT-5.x: `FacturaElectronicaBuilder.build()` constructs the e-factura.
- [ ] IT-5.x: SyncBackEvent emitted on cloud INSERT.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| `consecutivo_actual` race | Low | `SELECT FOR UPDATE` in same TX |
| `rango_hasta` exhausted | Low | Endpoint returns 409 `rango_agotado` |
| DIAN provider offline | Med | Branch falls back to `numero_temporal`; `dian_dispatcher` queue persists |
| Sync-back delay → operator reimprime with wrong number | Low | `reimpresion_ticket` gate on `SyncBackEvent` |

## 12. Open Questions
- (a) DIAN provider adapter (Factus, etc.) — out of scope for bootstrap.
- (b) CUFE generation — library or DIAN-side?