# PRD: facturas (T05)

> Business invoice (non-fiscal). Cloud receives via sync; assigns DIAN number asynchronously.

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
- **Table name**: `prod.facturas`
- **SQL name**: `facturas` (with `prod` schema)
- **Enforcement level**: `[L-E]` event (branch writes business; cloud assigns e-factura)
- **Retention**: 5+ years (DIAN)
- **Origin**: F1 (schema) + IT-5 (writes)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. `numero_temporal` is `PRE-<8-char-uuid>` (offline mode only). `uuid_factura_electronica` populated by cloud after SyncBackEvent.

## 3. SOLID Atomic Breakdown
- **S**: "one business invoice" — sale record with items + payments.
- **O**: `descuento` column extensible.
- **I**: branch operator API (creates with `numero_temporal`); admin read API; cloud `/facturas/procesar` assigns e-factura.
- **D**: `parkos_core/facturacion/factura_business_writer.py`.
- **Atomic**: INSERT only (state derived from `anulaciones``).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | mandatory |
| `uuid_ingreso` | `prod.ingreso.uuid` | exactly one (NOT NULL) | RESTRICT | the cycle origin |
| `uuid_salida` | `prod.salidas.uuid` | exactly one (NOT NULL) | RESTRICT | the cycle end |
| `uuid_factura_electronica` | `prod.factura_electronica.uuid` | 0..1 (nullable) | RESTRICT | populated by sync-back |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `prod.factura_detalle.uuid_factura` | 1:N | lines |
| `prod.factura_pagos.uuid_factura` | 1:N | payments |
| `prod.factura_impuestos.uuid_factura` | 1:N | tax snapshots |
| `prod.factura_otros_cobros.uuid_factura` | 1:N | other charges |
| `prod.factura_electronica.uuid_factura` | 1:1 | the DIAN doc |
| `prod.reimpresion_ticket.uuid_factura` | 1:N | reimpresiones |
| `prod.reclamos` (polymorphic) | — | FK polimórfica `tipo_reclamable='factura'` |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Branch writes locally first; cloud receives via sync |
| UPDATE | NO | Derived state |
| DELETE | NO | Append-only |

## 6. CodeGraph Dependencies
- `api_sucursal/routers/facturas.py`.
- `api_admin/routers/facturas.py`.
- `parkos_core/dian/cloud/factura_electronica_builder.py`.

## 7. Use Cases enabled by this table

The `facturas` table is the **business invoice** (non-fiscal). Branch writes locally first; cloud receives via sync and asynchronously assigns the DIAN `factura_electronica`. Offline-first: branch can issue a factura with `numero_temporal = PRE-<8-char-uuid>` when cloud is unreachable. The `estado` is DERIVED from `anulaciones` existence — no UPDATE.

### 7.1 Use Case: `uc.facturas.online-mode-cloud-assigns-dian-number`

**Actor**: operator

**Real-world action**: Branch is online; operator completes a sale with items + payments. Branch backend synchronously calls cloud `/facturas/procesar` and receives the real DIAN `numero_oficial` to print immediately. No `preliminar` badge, no SyncBackEvent wait.

**Steps**:
1. Operator opens `web_sucursal/FacturacionForm`; selects cliente, items, pagos (efectivo/datafono mixto allowed).
2. Frontend POSTs `api_sucursal /facturas` with `{uuid_ingreso, uuid_salida, uuid_cliente, lines, pagos}`.
3. Branch backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
4. INSERT `facturas` row (without `numero_oficial`).
5. INSERT `factura_detalle` lines (snapshot of items), `factura_pagos` rows (payment methods + amounts), `factura_impuestos` (snapshot from `impuestos`), `factura_otros_cobros` (snapshot from `otros_cobros`) — all in same TX.
6. INSERT `log_transaccional` (`accion='factura_creada'`).
7. Branch backend calls `api_admin /facturas/procesar` (cross-service call with admin sync_agent JWT) with the local `facturas.uuid`.
8. Cloud `procesar` opens TX; `SELECT empresa FOR UPDATE`; `consecutivo_new = consecutivo_actual + 1`; UPDATE `empresa`.
9. Cloud INSERTs `factura_electronica` with `consecucion=$new`, `numero_oficial=FAC-$prefijo-$consecutivo_new`, `reportado_dian=false`.
10. Cloud INSERTs `log_transaccional` (`accion='factura_electronica_creada'`).
11. Cloud INSERTs `SyncBackEvent` (`uuid_factura, numero_oficial, dian_response_at=NULL`) for defense-in-depth.
12. Cloud returns `{uuid_factura_electronica, numero_oficial, consecutivo}` synchronously to branch.
13. Branch UPSERTs `facturas.uuid_factura_electronica=$uuid, numero_oficial=$numero_oficial`; clears preliminar badge.
14. Operator prints the receipt with the real number.

**Tables touched (writes)**: `facturas`, `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `log_transaccional` (branch), `empresa`, `factura_electronica`, `log_transaccional` (cloud), `SyncBackEvent`.
**Tables touched (reads)**: `ingreso`, `salidas`, `clientes`, `tarifas_sucursal`, `impuestos`, `otros_cobros`, `log_transaccional` (chain anchor), `empresa`.
**FKs traversed**: `facturas.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`; `facturas.uuid_factura_electronica` → `factura_electronica.uuid` (after sync-back); `factura_electronica.uuid_cliente` → `clientes.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the originating `facturas` row plus its children are all queued and pushed via `sync_queue`. In the online case the cloud already processed them synchronously; the queue ensures idempotency on retry.
- Cloud → branch: YES — `SyncBackEvent` flows back; branch UPSERTs `numero_oficial`.
- DIAN trigger: YES — after cloud INSERTs `factura_electronica`, it's enqueued for `dian_dispatcher`.
- Hash chain impact: YES — `log_transaccional` chain extends by 2 rows (1 on branch side `accion='factura_creada'`, 1 on cloud side `accion='factura_electronica_creada'`). Branch chain and cloud chain share `uuid_sucursal` partition key.

**Integration with other tables**:
- Reads from: `ingreso`, `salidas` (the cycle), `clientes` (titular), `tarifas_sucursal` (pricing), `impuestos`, `otros_cobros` (tax/charge snapshots), `empresa` (atomic `consecutivo_actual`), `log_transaccional` (chain anchor).
- Writes to: `empresa`, `factura_electronica`, `log_transaccional` (audit), `SyncBackEvent`, `facturas` + children (branch side).
- Downstream: `reimpresion_ticket` is now enabled because `uuid_factura_electronica` is populated; `dian_dispatcher` will extend the chain again when DIAN responds.

### 7.2 Use Case: `uc.facturas.offline-mode-uses-numero-temporal`

**Actor**: operator

**Real-world action**: Branch is offline (no internet). Operator still completes the sale; the system prints a `PRE-XXXXXXXX` number on the receipt with a red `preliminar` badge. When connectivity returns, the queue pushes to cloud and `SyncBackEvent` fills the real `numero_oficial`.

**Steps**:
1. Operator completes sale with items + payments at `FacturacionForm`. Internet is down.
2. Frontend POSTs `api_sucursal /facturas` (online call fails with timeout).
3. Branch backend detects cloud unreachable (timeout > 5s); falls back to offline mode.
4. Backend opens TX; SELECT chain anchor from `log_transaccional`.
5. INSERT `facturas` row with `numero_temporal='PRE-' + uuid[:8].upper()`, `observaciones='offline_sale_<timestamp>'`.
6. INSERT `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros` (same as online).
7. INSERT `log_transaccional` (`accion='factura_creada_offline'`).
8. `queue_processor.enqueue('facturas', uuid, datos)` → INSERT `sync_queue` row (accumulates in branch DB).
9. Print receipt with `PRE-XXXXXXXX` number + red `preliminar` badge; `reimpresion_ticket` disabled.
10. When internet returns, `job_sync_sucursal/drain_outbox` flushes the queue to cloud within 30s.
11. Cloud processes: `SELECT empresa FOR UPDATE`; INSERT `factura_electronica`; INSERT `log_transaccional`.
12. Cloud emits `SyncBackEvent` (`uuid_factura, numero_oficial, dian_response_at`).
13. Branch polls; UPSERTs `facturas.uuid_factura_electronica`, `numero_oficial`; clears preliminar badge.
14. Operator can now `reimpresion_ticket` with real number.

**Tables touched (writes)**: `facturas`, `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `log_transaccional` (branch), `sync_queue` (branch), `empresa`, `factura_electronica`, `log_transaccional` (cloud), `SyncBackEvent`.
**Tables touched (reads)**: `ingreso`, `salidas`, `clientes`, `tarifas_sucursal`, `impuestos`, `otros_cobros`, `log_transaccional` (chain anchor), `empresa`.
**FKs traversed**: `facturas.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_salida` → `salidas.uuid`; `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_cliente` → `clientes.uuid`.

**Sync behavior**:
- Branch → cloud: YES, but delayed. `sync_queue.depth` grows during offline; alert emitted at depth > 1000.
- Cloud → branch: YES — `SyncBackEvent` flows back once cloud processes.
- DIAN trigger: YES — same as online, just delayed.
- Hash chain impact: YES — branch chain advances locally during offline; cloud chain advances when sync completes. Idempotency by UUID ensures no duplicates.

**Integration with other tables**:
- Reads from: same as online.
- Writes to: same as online + `sync_queue` for deferred propagation.
- Related: if the cloud processes the row but DIAN rejects (e.g., expired `rango_hasta`), the `factura_electronica` is revoked via `revocacion_factura` (T02) and the branch shows a red badge permanently (not just preliminar).

### 7.3 Use Case: `uc.facturas.subscriber-departure-without-bill`

**Actor**: operator

**Real-world action**: A subscriber (with active subscription) departs. The system reads `ingreso.uuid_subscripcion_cliente` and DOES NOT create a business factura — the subscription is consumed instead. This is the critical "subscriber doesn't pay per visit" rule.

**Steps**:
1. Subscriber arrives at the booth with their vehicle. Operator creates ingreso with `uuid_subscripcion_cliente` linked (T04 use case 7.2).
2. Time passes; subscriber returns to their vehicle to leave.
3. Operator opens `SalidaForm`, **types the plate** (manual, no scanners).
4. Frontend GETs `api_sucursal /ingresos?placa=$plate&estado='activo'` — finds the ingreso.
5. Backend reads `ingreso.uuid_subscripcion_cliente`; checks `subscripciones_cliente.estado='activa' AND vigente_desde<=NOW() AND (vigente_hasta IS NULL OR vigente_hasta>NOW())`.
6. **Branch rule**: if `uuid_subscripcion_cliente IS NOT NULL AND active` → no factura is created.
7. Backend INSERTs `salidas` row (`estado='activo'`, `fecha_salida=NOW()`) — 1:1 with the ingreso.
9. INSERT `log_transaccional` (`accion='salida_por_subscripcion'`).
10. INSERT `sync_queue` row for the salida.
11. Operator opens the barrier; subscriber drives out without paying anything at the booth.
12. The subscription is "consumed" — counted in the periodic `subscripcion_vehiculos` consumption metric.

**Tables touched (writes)**: `salidas`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `ingreso`, `subscripciones_cliente`, `subscripcion_vehiculos`, `vehiculos`, `clientes`, `log_transaccional` (chain anchor).
**FKs traversed**: `ingreso.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `salidas.uuid_ingreso` → `ingreso.uuid`; `salidas.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `salidas` row + `log_transaccional` row push via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO (no invoice = no DIAN).
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row on each side.

**Integration with other tables**:
- Reads from: `ingreso` (the originating entry), `subscripciones_cliente` (active check), `subscripcion_vehiculos` (consumption tracking), `clientes`, `log_transaccional` (chain anchor).
- Writes to: `salidas`, `log_transaccional`, `sync_queue`.
- Note: this is the ONLY departure path where `facturas` is NOT written. Critical for billing integrity — if the rule is broken, the subscriber gets billed per visit AND consumes subscription quota.

### 7.4 Use Case: `uc.facturas.operator-requests-annulment-with-cloud-revocacion`

**Actor**: operator (branch) + admin (cloud) + dian_dispatcher (cloud)

**Real-world action**: Operator realizes the factura has an error (wrong items, wrong client) and clicks `Anular`. The request goes into the `anulaciones` workflow chain (`solicitada → aprobada → ejecutada`); admin approves AND executes. The execution triggers a cloud-only `revocacion_factura` INSERT (with hash chain), the `dian_dispatcher` notifies DIAN, a `SyncBackEvent` flows back, and the branch updates its local `facturas.estado='anulada'` (operational derivation from `revocacion_factura` existence — branch never writes to `revocacion_factura`). This is the end-to-end cross-table cascade (gap #1 made explicit).

**Steps**:
1. Operator opens `FacturacionForm` (or `FacturaDetail` view); clicks `Anular`.
2. Frontend POSTs `api_sucursal /anulaciones` with `{uuid_ingreso, motivo='factura_anulada', observaciones='wrong client'}`.
3. Backend: SELECT the `facturas` for the ingreso; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
4. INSERT `anulaciones` chain root row (`estado='solicitada'`, `uuid_anulacion_padre=NULL`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `uuid_ingreso=$ingreso_uuid`) — workflow chain root.
5. INSERT `log_transaccional` (`accion='anulacion_solicitada'`, `tabla_afectada='anulaciones'`, `uuid_registro_afectado=$anulacion_uuid`, `uuid_referencia=$ingreso_uuid`, `datos_anteriores=null`, `datos_nuevos={motivo, uuid_ingreso, observaciones}`) — extends branch chain by 1 row.
6. `queue_processor.enqueue('anulaciones', uuid, datos)`.
7. Cloud receives; admin opens `web_admin/AnulacionesList`, sees the request, reviews the factura.
8. Admin clicks `Aprobar` → INSERT new `anulaciones` row (`uuid_anulacion_padre=$root, estado='aprobada'`, `uuid_usuario=$admin_uuid`) — workflow chain extends by 1 row. INSERT `log_transaccional` (`accion='anulacion_aprobada'`) — cloud chain extends by 1 row.
9. Admin clicks `Ejecutar`. Backend opens TX; SELECT chain anchors for BOTH `revocacion_factura` and `log_transaccional`.
10. (If `factura_electronica` exists for this ingreso cycle — i.e., DIAN numbering was assigned): INSERT `revocacion_factura` row (`uuid_factura_electronica=$original, uuid_factura_electronica_reemplazo=NULL_OR_$credit_note, motivo='anulacion_ejecutada', hash_anterior=$last_rev.hash_actual, hash_actual=SHA256(...)`) — extends the `revocacion_factura` chain by 1 row.
11. INSERT new `anulaciones` row (`uuid_anulacion_padre=$aprobada, estado='ejecutada'`, `uuid_usuario=$admin_uuid`) — workflow chain extends by 1 row.
12. INSERT `log_transaccional` (`accion='anulacion_ejecutada'`, `tabla_afectada='anulaciones'`, `uuid_registro_afectado=$anulacion_ejecutada_uuid`, `uuid_referencia=$anulacion_root_uuid`) — cloud chain extends by 1 row.
13. `dian_dispatcher` worker dequeues the new `revocacion_factura` row and notifies DIAN provider of the revocation.
14. Cloud INSERT `SyncBackEvent` (concepto sprint 5; payload `{uuid_operacion, tabla_origen='facturas', uuid_registro=$factura_uuid, datos_nuevos={estado:'anulada', uuid_revocacion=$revocacion_uuid, anulacion_root=$anulacion_root_uuid}, timestamp}`).
15. Branch worker polls for SyncBackEvent; UPSERT `facturas.estado='anulada'` derived cache update (NOT a row mutation — `facturas` is `[L-E]` append-only; `estado='anulada'` is derived from `revocacion_factura` existence + `anulaciones.estado='ejecutada'`).
16. Branch UI shows the factura as annulled (permanent red badge).
17. `reimpresion_ticket` for that factura becomes impossible (gated on `uuid_factura_electronica` being valid AND derived `estado='activa'`).

**Tables touched (writes)**: `anulaciones` (chain: solicitada + aprobada + ejecutada = 3 rows), `log_transaccional` (3 audit rows on branch + cloud sides combined; breakdown: 1 branch + 2 cloud), `revocacion_factura` (1 row, cloud-only, if e-factura existed), `SyncBackEvent`, `facturas` (operational derived cache update from SyncBackEvent; not a row mutation).
**Tables touched (reads)**: `facturas` (the cycle), `factura_electronica` (does it exist?), `empresa` (consecutivo context if creating credit note), `anulaciones` (latest chain row), `log_transaccional` (chain anchor for log), `revocacion_factura` (chain anchor for revocation chain), `sucursal` (chain key).
**FKs traversed**: `anulaciones.uuid_ingreso` → `ingreso.uuid`; `anulaciones.uuid_usuario` → `usuarios.uuid` (admin who authorized each transition); `anulaciones.uuid_anulacion_padre` → `anulaciones.uuid` (self-reference, workflow chain); `anulaciones.uuid_sucursal` → `sucursal.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid`; `revocacion_factura.uuid_factura_electronica_reemplazo` → `factura_electronica.uuid` (optional, if credit note); `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_factura_electronica` → `factura_electronica.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `anulaciones.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `anulaciones` chain root (`solicitada`) + `log_transaccional` audit rows pushed from branch.
- Cloud → branch: YES — `SyncBackEvent` flows back once cloud executes the anulacion. Branch receives and updates local `facturas` derived state (operational cache; the row itself is not modified).
- DIAN trigger: YES — the executed anulation triggers `revocacion_factura` (T02 itself) which extends BOTH hash chains, and DIAN provider notification happens via `dian_dispatcher`.
- Hash chain impact: YES — `log_transaccional` chain extends by 3 rows total: 1 branch (solicitada) + 2 cloud (aprobada, ejecutada). `revocacion_factura` chain extends by 1 row on cloud side (the revocation link, if e-factura existed). `anulaciones` chain extends by 3 rows: 1 branch (solicitada root) + 2 cloud (aprobada + ejecutada).

**Integration with other tables**:
- Reads from: `facturas` (the cycle), `factura_electronica` (does it exist?), `empresa` (consecutivo context), `anulaciones` (latest chain row), `revocacion_factura` (chain anchor), `log_transaccional` (chain anchor for log), `sucursal` (chain key).
- Writes to: `anulaciones` (chain rows: 3), `log_transaccional` (audits: 3), `revocacion_factura` (1, cloud-only), `SyncBackEvent`, `facturas` (derived cache).
- Cross-cutting: this is the canonical end-to-end cross-table cascade — operator triggers at branch → workflow chain on cloud → revocacion chain extends → DIAN notified → SyncBackEvent → branch UI updates. Total tables touched: 5 (`anulaciones`, `log_transaccional`, `revocacion_factura`, `facturas`, `SyncBackEvent` concept). Note: `facturas` is NOT modified at the DB level (it's `[L-E]` append-only); only the local cache reflects the derived state.
- Downstream: `reimpresion_ticket` is disabled for the annulled factura; `reclamos` may be opened against the anulation (if customer disputes — polymorphic FK on `reclamos.tipo_reclamable='factura'`).

### 7.5 Use Case: `uc.facturas.reimpresion-gated-on-sync-back`

**Actor**: operator

**Real-world action**: Customer loses their receipt and asks for a reprint. Operator clicks `Reimprimir`. The system checks whether `uuid_factura_electronica` is populated (sync-back completed) — if NOT, the button is disabled (gate). Once sync-back is done, the reprint proceeds via the `reimpresion_ticket` workflow.

**Steps**:
1. Customer asks for a reprint. Operator opens `FacturaDetail` in `web_sucursal`.
2. Operator clicks `Reimprimir`.
3. Frontend checks `factura.uuid_factura_electronica IS NOT NULL AND factura.dian_response_at IS NOT NULL` (gate).
4. If NOT ready: frontend displays disabled button with tooltip "Esperando SyncBackEvent de DIAN (preliminar)".
5. If ready: Frontend POSTs `api_sucursal /reimpresion-ticket` with `{uuid_factura, uuid_usuario, costo=0}` (reprint of an existing ticket is free; only NEW tickets cost).
6. Backend: SELECT `facturas` (verify DIAN status), SELECT chain anchor.
7. INSERT `reimpresion_ticket` chain root (`estado='cobrada'`, `uuid_padre=NULL`, `costo=0`).
8. INSERT `log_transaccional` (`accion='reimpresion_solicitada'`).
9. `queue_processor.enqueue('reimpresion_ticket', uuid, datos)`.
10. Print duplicate receipt with the real `numero_oficial`, `cufe`, `qr_code`.
11. If a subsequent cancel of the reprint is needed (e.g., wrong client): INSERT new `reimpresion_ticket` row with `uuid_padre=$root, estado='anulada'`.

**Tables touched (writes)**: `reimpresion_ticket` (1 or 2 rows), `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `facturas` (the original), `factura_electronica` (DIAN status), `log_transaccional` (chain anchor).
**FKs traversed**: `reimpresion_ticket.uuid_factura` → `facturas.uuid`; `reimpresion_ticket.uuid_ingreso` → `ingreso.uuid`; `reimpresion_ticket.uuid_usuario` → `usuarios.uuid`; `reimpresion_ticket.uuid_padre` → `reimpresion_ticket.uuid` (self-reference, chain).

**Sync behavior**:
- Branch → cloud: YES — the `reimpresion_ticket` row + `log_transaccional` push via `sync_queue`.
- Cloud → branch: NO (cloud may pull-verify but no parametrization impact).
- DIAN trigger: NO (reprint is a local-only event).
- Hash chain impact: YES — `log_transaccional` chain extends by 1 row on each side.

**Integration with other tables**:
- Reads from: `facturas` (gate check on DIAN status), `log_transaccional` (chain anchor).
- Writes to: `reimpresion_ticket` (workflow chain), `log_transaccional`, `sync_queue`.
- Cross-cutting: this use case is the canonical example of why the gate on `uuid_factura_electronica` matters — reprinting with a `numero_temporal` would print `PRE-XXXXXXXX` which is invalid for DIAN compliance.

### 7.6 Use Case: `uc.facturas.pago-mixto-efectivo-datafono`

**Actor**: operator (branch)

**Real-world action**: Customer wants to split the payment: $30,000 in efectivo (cash) + $15,000 in datafono (card). Operator records both as separate `factura_pagos` rows under the same `facturas.uuid`. The sum must equal `facturas.total` (validated before INSERT). This exercises the `[A]` append-only `factura_pagos` table with 2 rows per factura in the mixto case.

**Steps**:
1. Operator completes `FacturacionForm`; total is $45,000. Customer says "30k efectivo + 15k datafono".
2. Operator selects `medio_pago='efectivo'`, fills `valor=30000`, `referencia=null`. Then adds another payment row: `medio_pago='datafono'`, `valor=15000`, `referencia='VISA-XXXX-1234'` (manual entry from the dataphone terminal; no automated capture).
3. Frontend POSTs `api_sucursal /facturas` with `{lines, pagos: [{medio_pago:'efectivo', valor:30000}, {medio_pago:'datafono', valor:15000, referencia:'VISA-XXXX-1234'}]}`.
4. Branch backend opens TX; SELECT chain anchor from `log_transaccional`.
5. Backend validates `sum(pagos.valor) == total` (rejects with 400 if not).
6. INSERT `facturas` row (`subtotal`, `descuento`, `total=45000`).
7. INSERT `factura_detalle` lines.
8. INSERT 2 `factura_pagos` rows (same `uuid_factura`, different `medio_pago`, different `valor`, different `referencia`); both rows reference the same `facturas.uuid`.
9. INSERT `factura_impuestos` (snapshot), `factura_otros_cobros` (snapshot).
10. INSERT `log_transaccional` (`accion='factura_creada'`, `tabla_afectada='facturas'`, `datos_nuevos={total, pagos_count: 2, mixto: true}`).
11. Continue to cloud `/facturas/procesar` (online) or fallback to offline (per use case 7.1 / 7.2).
12. At `arqueo` (T34) end-of-shift: the sum of `factura_pagos.valor WHERE medio_pago='efectivo'` must match `caja.valor_efectivo`; sum of `factura_pagos.valor WHERE medio_pago='datafono'` must match `caja.valor_datafono` — both per `uuid_sucursal` and `sesion.uuid`. Tolerance check uses `configuracion_tolerancias`.

**Tables touched (writes)**: `facturas`, `factura_detalle`, `factura_pagos` (2 rows), `factura_impuestos`, `factura_otros_cobros`, `log_transaccional`, `sync_queue`.
**Tables touched (reads)**: `facturas` (validation: pagos sum == total), `tarifas_sucursal` (pricing), `impuestos`, `otros_cobros`, `log_transaccional` (chain anchor), `sucursal`.
**FKs traversed**: `factura_pagos.uuid_factura` → `facturas.uuid` (both rows reference the same `facturas` row); `factura_pagos.uuid_sucursal` → `sucursal.uuid`; `factura_detalle.uuid_factura` → `facturas.uuid`; `factura_impuestos.uuid_impuesto` → `impuestos.uuid`; `factura_otros_cobros.uuid_otro_cobro` → `otros_cobros.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the 2 `factura_pagos` rows travel together with `facturas` + children via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: YES (same as online flow; the mixto nature doesn't affect DIAN).
- Hash chain impact: YES — branch chain extends by 1 row (single `log_transaccional` for the factura creation, regardless of pago count); cloud chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `facturas` (validation), `tarifas_sucursal` (pricing), `impuestos`, `otros_cobros`, `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `facturas`, `factura_detalle`, `factura_pagos` (2 rows), `factura_impuestos`, `factura_otros_cobros`, `log_transaccional`, `sync_queue`.
- Cross-cutting: the `[A]` constraint on `factura_pagos` means corrections are NOT deletes — if the operator typed the wrong value, they annul the entire `facturas` (use case 7.4) and re-create. The mixto scenario is explicitly modeled as N rows in `factura_pagos`, all referencing the same `facturas.uuid`.
- Related: `arqueo` end-of-shift cross-checks `factura_pagos.valor` aggregated by `medio_pago` vs `caja.valor_efectivo` + `caja.valor_datafono` snapshots. Mismatch triggers `alerta tipo_alerta='diferencia_arqueo'`.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 15, 16, 17, 20, 24, 28, 31.

## 9. RED Tests
- (RED) Online branch: POST inserts locally, calls cloud `/facturas/procesar`, gets `numero_oficial`.
- (RED) Offline branch: POST inserts with `numero_temporal`, enqueues.
- (RED) `numero_temporal` shown as preliminar badge until sync-back.
- (RED) `reimpresion_ticket` disabled before `uuid_factura_electronica` populated.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-5.x: dual-mode POST (`numero_temporal` fallback on cloud unreachable).
- [ ] IT-5.x: bidirectional sync for `facturas`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Branch offline indefinitely | Med | Alert after 7 days; queue grows |
| Cloud `/facturas/procesar` race | Low | Atomic `consecutivo_actual` |
| DIAN rejection | Med | Revocation via `revocacion_factura` |

## 12. Open Questions
- (a) Multiple `pagos` per factura (mixto)?
- (b) Credit notes — separate table or via `revocacion_factura`?