# PRD: revocacion_factura (T02)

> Second-most complex: hash chain + cloud-only writes (branches never write).

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
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[A]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.revocacion_factura`
- **SQL name**: `revocacion_factura` (with `prod` schema)
- **Enforcement level**: `[A]` source-of-truth (cloud-only writes)
- **Retention**: 5+ years (DIAN)
- **Hash chain**: YES (per `uuid_sucursal`)
- **Origin**: F1 (schema) + IT-5 (writes from `dian_dispatcher`)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. Cross-system: cloud-only.

## 3. SOLID Atomic Breakdown
- **S**: "one DIAN revocation event".
- **O**: new columns (e.g., `motivo_codigo` for DIAN error codes) added via migration.
- **I**: `POST /revocacion-factura` is admin-auditor or `dian_dispatcher`-auth only.
- **D**: cloud-only writer `parkos_core/dian/cloud/revocacion_writer.py`.
- **Atomic**: INSERT only.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | mandatory; chain partitioning key |
| `uuid_factura_electronica` | `prod.factura_electronica.uuid` | exactly one (NOT NULL) | RESTRICT | the revoked invoice |
| `uuid_factura_electronica_reemplazo` | `prod.factura_electronica.uuid` | exactly one (NOT NULL) | RESTRICT | the replacement |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | No FKs to this table |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES (cloud only) | From `dian_dispatcher` after DIAN confirms revocation |
| UPDATE | NO | REVOKE + trigger |
| DELETE | NO | REVOKE + trigger |

## 6. CodeGraph Dependencies
- `parkos_core/dian/cloud/revocacion_writer.py` (cloud-only).
- `workers/hash_chain_verifier` (includes this table in nightly run).
- `web_admin/RevocacionesList` (read-only view).

## 7. Use Cases enabled by this table

The `revocacion_factura` table is the **probatory trail of DIAN fiscal-document revocations**. Cloud-only writes (branches NEVER write here). Every revocation extends the per-`uuid_sucursal` SHA256 hash chain in `revocacion_factura` (parallel to the `log_transaccional` chain). DIAN replacements are NOT deletes — the original `factura_electronica` stays in the chain and a new row points forward via `uuid_factura_electronica_reemplazo`. The chain is 2-hop in the sense that BOTH `log_transaccional` and `revocacion_factura` grow per `uuid_sucursal`, and every cloud-side revocation writes to BOTH chains.

### 7.1 Use Case: `uc.revocacion-factura.dian-rejects-creates-revocation`

**Actor**: dian_dispatcher

**Real-world action**: The DIAN provider rejects a freshly-sent e-factura (e.g., malformed NIT, expired `rango_hasta`, CUFE mismatch). The cloud `dian_dispatcher` records the rejection as a revocation row, extends BOTH hash chains, and notifies the admin and branch.

**Steps**:
1. Cloud `dian_dispatcher` finishes sending the e-factura to the DIAN provider and receives the rejection response (`{estado='rechazada', motivo_codigo, motivo_texto}`).
2. Cloud opens a TX; `SELECT last.revocacion_factura.hash_actual FROM revocacion_factura WHERE uuid_sucursal = $1 ORDER BY created_at DESC LIMIT 1` (chain anchor for this branch's `revocacion_factura` chain).
3. SELECT the `factura_electronica` (the rejected one) to capture `consecutivo`, `numero_oficial`, `uuid_factura`, `uuid_cliente`.
4. INSERT `revocacion_factura` row with `motivo='dian_error', uuid_factura_electronica=rejected.uuid, uuid_factura_electronica_reemplazo=NULL, motivo_codigo=$codigo, motivo_texto=$texto`, `hash_anterior=$last.hash_actual, hash_actual=SHA256(uuid || timestamp_registro || hash_anterior || uuid_sucursal || uuid_factura_electronica || uuid_factura_electronica_reemplazo || motivo)`.
5. `SELECT last.log_transaccional.hash_actual FROM log_transaccional WHERE uuid_sucursal = $1` (chain anchor for the OTHER chain).
6. INSERT `log_transaccional` (`accion='dian_rechazada'`, `tabla_afectada='revocacion_factura'`, `uuid_referencia=$factura_uuid`, `uuid_registro_afectado=$revocacion_uuid`) — extends the `log_transaccional` chain for the same `uuid_sucursal`.
7. INSERT `alerta` (`tipo_alerta='dian_rechazada'`, `estado='abierta'`, `uuid_sucursal=$branch`, `uuid_alerta_padre=NULL`, `observaciones=$motivo_texto`) — admin must investigate via the `alerta` workflow chain (`abierta → en_revision → resuelta`).
8. INSERT `SyncBackEvent` (concepto a modelar en sprint 5; payload `{uuid_operacion, tabla_origen='facturas', uuid_registro=$factura_uuid, datos_nuevos={dian_rechazada=true, motivo_codigo, motivo_texto, uuid_revocacion=$revocacion_uuid}, timestamp}`) — branch sees the red badge on the invoice in `FacturaDetail` and disables `reimpresion_ticket`.
9. Admin sees the red badge in `web_admin/FacturaDetail` and `web_admin/AlertasList`.

**Tables touched (writes)**: `revocacion_factura`, `log_transaccional`, `alerta`, `SyncBackEvent` (concept).
**Tables touched (reads)**: `factura_electronica` (the rejected invoice), `log_transaccional` (chain anchor for log chain), `revocacion_factura` (chain anchor for revocation chain), `sucursal` (chain key).
**FKs traversed**: `revocacion_factura.uuid_sucursal` → `sucursal.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `facturas.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference for subsequent transitions).

**Sync behavior**:
- Branch → cloud: NO (cloud is the originator — branches NEVER write to `revocacion_factura`).
- Cloud → branch: YES — `SyncBackEvent` flows back so the branch UI shows the red badge and disables `reimpresion_ticket`.
- DIAN trigger: NO (this is a response to a previous DIAN dispatch, not a new dispatch).
- Hash chain impact: YES — BOTH chains extend on the cloud side. The `revocacion_factura` chain grows by 1 row (this revocation); the `log_transaccional` chain grows by 1 row (the audit). The branch-side chains are NOT extended — branch receives the SyncBackEvent but doesn't write `revocacion_factura` rows (and doesn't write `log_transaccional` for the cloud-only revocation event).

**Integration with other tables**:
- Reads from: `factura_electronica` (the rejected invoice), `revocacion_factura` (chain anchor), `log_transaccional` (chain anchor for the log audit), `sucursal` (chain key).
- Writes to: `revocacion_factura` (this row), `log_transaccional` (audit), `alerta` (admin notification; workflow chain root), `SyncBackEvent` (branch UI signal).
- Downstream: admin may follow up by creating a `factura_electronica` replacement (use case 7.2 below). Branch UI shows `facturas.estado='anulada'` derived from `revocacion_factura` existence.

### 7.2 Use Case: `uc.revocacion-factura.admin-credit-note-with-replacement`

**Actor**: admin

**Real-world action**: A customer asks for a refund on yesterday's parking invoice. The admin opens the e-factura in `web_admin`, clicks `Revoke + Replace`, the system creates a new e-factura with **negative amounts** (credit note), and links both via a `revocacion_factura` row. The original invoice stays in the audit chain.

**Steps**:
1. Admin opens `web_admin/FacturaDetail` (the rejected one from use case 7.1, or any refund request).
2. Clicks `Revoke + Replace`.
3. Frontend POSTs `api_admin /revocacion-factura` with `{uuid_factura_electronica: $original, motivo: 'customer_refund', uuid_factura_electronica_reemplazo: $new_negative_invoice, observaciones: 'devolución solicitada por cliente X'}`.
4. Backend opens a TX; SELECT chain anchor for `uuid_sucursal=$branch` in BOTH `revocacion_factura` and `log_transaccional`.
5. Verify the new `factura_electronica` already exists (it was created with `monto_total < 0`, `tipo='credit_note'`, atomic `consecutivo_actual` increment in a previous step — see T03 use case `cloud-assigns-consecutivo-online-branch` for the assignment flow).
6. INSERT `revocacion_factura` row with `hash_anterior=$last_rev.hash_actual, hash_actual=SHA256(...)` (extends the `revocacion_factura` chain).
7. INSERT `log_transaccional` (`accion='factura_revocada_con_reemplazo'`, `tabla_afectada='revocacion_factura'`, `uuid_referencia=$original_invoice_uuid`) (extends the `log_transaccional` chain).
8. INSERT `SyncBackEvent` (`uuid_factura, revocada=true, uuid_factura_electronica_reemplazo=$new_negative_invoice`) — branch UI shows the credit-note link.
9. Admin sees the chain link in `web_admin/RevocacionesList`.

**Tables touched (writes)**: `revocacion_factura`, `log_transaccional`, `SyncBackEvent`.
**Tables touched (reads)**: `factura_electronica` (the original AND the replacement — both must already exist), `empresa` (chain anchor context), `log_transaccional`, `revocacion_factura`, `sucursal` (chain key).
**FKs traversed**: `revocacion_factura.uuid_sucursal` → `sucursal.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid` (original); `revocacion_factura.uuid_factura_electronica_reemplazo` → `factura_electronica.uuid` (replacement); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `facturas.uuid`.

**Sync behavior**:
- Branch → cloud: NO (cloud-only operation).
- Cloud → branch: YES — `SyncBackEvent` flows back. Branch updates local `facturas` row with the replacement reference; `reimpresion_ticket` remains gated (the replacement is a new invoice, branch operator may need to issue a new ticket on customer request).
- DIAN trigger: NO (the replacement invoice was already dispatched to DIAN in its own flow).
- Hash chain impact: YES — both cloud chains extend by 1 row each (`revocacion_factura` chain + `log_transaccional` chain). The replacement e-factura, when it was originally created, ALSO extended the `log_transaccional` chain with `accion='factura_electronica_creada'`. So the total chain growth for this refund scenario is 2 cloud rows on `log_transaccional` (replacement creation + revocation link) + 1 cloud row on `revocacion_factura` (the link).

**Integration with other tables**:
- Reads from: `factura_electronica` (both old and new), `empresa` (consecutivo context for the replacement), `revocacion_factura` (chain anchor), `log_transaccional` (chain anchor).
- Writes to: `revocacion_factura` (the chain row), `log_transaccional` (the audit), `SyncBackEvent` (branch signal).
- Related: the operator at the branch may need to issue a `reimpresion_ticket` for the customer to hand them the credit note — the existing `reimpresion_ticket` workflow handles this, gated on the new `uuid_factura_electronica_reemplazo` being populated.

### 7.3 Use Case: `uc.revocacion-factura.cloud-revocacion-cascade-syncback`

**Actor**: admin (cloud) + sync worker (branch)

**Real-world action**: Anularion in `web_admin` (after operator-requested flow at the branch) reaches the `ejecutada` state. Cloud emits a `revocacion_factura` row (cloud-only, with hash chain), the `dian_dispatcher` notifies DIAN, a `SyncBackEvent` flows back to the branch, and the branch updates its local `facturas.estado='anulada'` (operational derivation from `revocacion_factura` existence — the branch never writes to `revocacion_factura`). This is the **end-to-end cross-table cascade** that makes the gap explicit.

**Steps**:
1. (Prior) Operator at branch requested `anulacion`: branch INSERT `anulaciones` row (`estado='solicitada'`, `uuid_anulacion_padre=NULL` — chain root). See T05 use case `operator-requests-annulment-with-cloud-revocacion`.
2. Branch pushed `anulaciones` row + `log_transaccional` audit via `sync_queue`. Cloud receives.
3. Admin opens `web_admin/AnulacionesList`, clicks `Aprobar` on the root solicitud.
4. Backend INSERT new `anulaciones` row (`uuid_anulacion_padre=$root, estado='aprobada'`) — chain extends.
5. INSERT `log_transaccional` (`accion='anulacion_aprobada'`) — log chain extends.
6. Admin clicks `Ejecutar`.
7. Backend opens a TX; SELECT chain anchors for BOTH `revocacion_factura` and `log_transaccional`.
9. (If e-factura exists for the ingreso cycle — i.e., `factura_electronica` was assigned): INSERT `revocacion_factura` row (`uuid_factura_electronica=$original, uuid_factura_electronica_reemplazo=NULL_OR_$credit_note, motivo='anulacion_ejecutada', hash_anterior=$last_rev.hash_actual, hash_actual=SHA256(...)`) — extends the `revocacion_factura` chain.
10. INSERT new `anulaciones` row (`uuid_anulacion_padre=$aprobada, estado='ejecutada'`) — chain extends.
11. INSERT `log_transaccional` (`accion='anulacion_ejecutada'`, `tabla_afectada='anulaciones'`, `uuid_referencia=$anulacion_root_uuid`) — log chain extends.
12. `dian_dispatcher` worker dequeues the new `revocacion_factura` row and notifies DIAN provider of the revocation (per the use case 7.1 above).
13. Cloud INSERT `SyncBackEvent` (concepto a modelar sprint 5; payload `{uuid_operacion, tabla_origen='facturas', uuid_registro=$factura_uuid, datos_nuevos={estado:'anulada', uuid_revocacion=$revocacion_uuid, anulacion_root=$anulacion_root_uuid}, timestamp}`).
14. Branch worker polls for SyncBackEvent; UPSERT `facturas.estado='anulada'` (derived update — the row itself isn't modified, but the local cache reflects the derivation). Branch UI shows the factura as annulled.
15. `reimpresion_ticket` for that factura becomes impossible (gated on `uuid_factura_electronica` being valid AND `estado='activa'`).

**Tables touched (writes)**: `anulaciones` (chain root + aprobada + ejecutada = 3 rows), `log_transaccional` (3 audit rows), `revocacion_factura` (1 row, if e-factura existed), `SyncBackEvent`, `facturas` (operational cache update from SyncBackEvent, NOT a row mutation — `facturas` itself is `[L-E]` append-only; the `estado='anulada'` is a derived cache value).
**Tables touched (reads)**: `anulaciones` (latest chain row), `facturas` (the cycle), `factura_electronica` (does it exist?), `empresa` (consecutivo context if creating credit note), `revocacion_factura` (chain anchor), `log_transaccional` (chain anchor for log), `sucursal` (chain key).
**FKs traversed**: `anulaciones.uuid_ingreso` → `ingreso.uuid`; `anulaciones.uuid_usuario` → `usuarios.uuid` (admin who authorized each transition); `anulaciones.uuid_anulacion_padre` → `anulaciones.uuid` (workflow chain self-reference); `anulaciones.uuid_sucursal` → `sucursal.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid`; `revocacion_factura.uuid_factura_electronica_reemplazo` → `factura_electronica.uuid` (optional, if credit note); `facturas.uuid_ingreso` → `ingreso.uuid`; `facturas.uuid_factura_electronica` → `factura_electronica.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the original `anulaciones` chain root + `log_transaccional` audit rows pushed from branch.
- Cloud → branch: YES — `SyncBackEvent` flows back once cloud executes the anulacion. Branch receives and updates local `facturas` derived state.
- DIAN trigger: YES — the executed anulacion triggers `revocacion_factura` (T02 itself) which extends BOTH hash chains, and DIAN provider notification happens via `dian_dispatcher`.
- Hash chain impact: YES — `log_transaccional` chain extends by 3 rows (one per transition: solicitada on branch; aprobada + ejecutada on cloud). `revocacion_factura` chain extends by 1 row on cloud side (the revocation link). `anulaciones` chain extends by 2 new rows on cloud side (aprobada + ejecutada, plus the root from branch).

**Integration with other tables**:
- Reads from: `anulaciones` (latest chain row), `facturas`, `factura_electronica`, `empresa`, `revocacion_factura` (chain anchor), `log_transaccional` (chain anchor), `sucursal`.
- Writes to: `anulaciones` (chain rows), `log_transaccional` (audits), `revocacion_factura` (cloud-only chain row), `SyncBackEvent`, `facturas` (derived cache).
- Cross-cutting: this is the canonical end-to-end cross-table cascade — operator triggers at branch → workflow chains on cloud → revocacion chain extends → DIAN notified → SyncBackEvent → branch UI updates. Total tables touched in one business operation: 5 (anulaciones, log_transaccional, revocacion_factura, facturas, SyncBackEvent concept).

### 7.4 Use Case: `uc.revocacion-factura.nightly-hash-chain-verifier`

**Actor**: verifier

**Real-world action**: The same nightly worker that verifies `log_transaccional` chains (see T01 use case 7.4) ALSO walks the `revocacion_factura` chains. If a revocation row has been tampered with, the verifier emits an `alerta tipo_alerta='hash_chain_break_revocation'`.

**Steps**:
1. `workers/hash_chain_verifier/__main__.py` runs at 02:00 cloud time (after `log_transaccional` chain check).
2. SELECT DISTINCT `uuid_sucursal` from `revocacion_factura` (branches that have at least one revocation — most branches will have many).
3. For each `uuid_sucursal`: walk the chain from genesis (first row with `hash_anterior IS NULL`) to tip (highest `created_at`).
4. For each row: recompute `hash_actual_expected = SHA256(uuid + timestamp_registro + hash_anterior + uuid_sucursal + uuid_factura_electronica + uuid_factura_electronica_reemplazo + motivo)`.
5. Compare to stored `hash_actual`. If mismatch: collect the offending row UUID + the discrepancy.
6. After walking all branches: for each broken chain, INSERT `alerta` row (`tipo_alerta='hash_chain_break_revocation', estado='abierta', uuid_sucursal=$branch, uuid_alerta_padre=NULL, observaciones=$summary`) — root of the `alerta` workflow chain for admin triage.
7. INSERT `log_transaccional` (`accion='chain_verification_failed_revocation'`, `tabla_afectada='revocacion_factura'`, `datos_nuevos={broken_uuids: [...]}`) using skip-broken mode (last known-good row as `hash_anterior`, not the broken row).
8. INSERT `sync_log` row with cycle metrics.
9. Alert appears in `web_admin/AlertasList` (red badge); admin triages manually via the `alerta` workflow chain (`abierta → en_revision → resuelta`).

**Tables touched (writes)**: `alerta`, `log_transaccional`, `sync_log`.
**Tables touched (reads)**: `revocacion_factura` (every chain), `sucursal` (active branches), `factura_electronica` (join for display), `log_transaccional` (last known-good anchor for verifier insert).
**FKs traversed**: `revocacion_factura.uuid_sucursal` → `sucursal.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` (responsible) → `usuarios.uuid` (NULL until claimed); `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain); `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (verifier runs in cloud only).
- Cloud → branch: NO (alerts are cloud-only; branches don't need to know about cloud chain integrity unless the broken row was branch-originated — but `revocacion_factura` is cloud-only by definition, so the broken row is always cloud-side).
- DIAN trigger: NO.
- Hash chain impact: NO direct impact on the verified `revocacion_factura` chains (verifier is read-only). However, the verifier's own `log_transaccional` audit row DOES extend the `log_transaccional` chain by 1 row using skip-broken mode (see T01 use case 7.4 for skip-broken semantics).

**Integration with other tables**:
- Reads from: `revocacion_factura` (every chain), `factura_electronica` (display JOIN), `sucursal` (active branches), `log_transaccional` (last known-good anchor).
- Writes to: `alerta` (on break; workflow chain root), `log_transaccional` (verifier audit, skip-broken), `sync_log` (cycle metrics).
- Cross-cutting: this worker is the SAME `hash_chain_verifier` that handles `log_transaccional` (T01 use case 7.4). The two chain tables share a verifier because they share the partition key (`uuid_sucursal`) and the same nightly cadence.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema), 2 (trigger), 4 (hash-chain), 6 (cloud API), 11 (sync parametrization pull to branch for display), 13 (web_admin), 30 (workers), 33 (DIAN compliance docs).

## 9. RED Tests
- (RED) INSERT from cloud `rol_app` → success.
- (RED) INSERT from branch `rol_app` → `AUDIT_FIRST_INMUTABLE`.
- (RED) UPDATE/DELETE → `AUDIT_FIRST_INMUTABLE`.
- (RED) Hash chain break → `HASH_CHAIN_BREAK`.
- (RED) SyncBackEvent emitted on cloud INSERT.
- (RED) Verifier detects tampering.

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger + hash-chain genesis per `uuid_sucursal`.
- [ ] IT-5.7 GREEN: `parkos_core/dian/cloud/revocacion_writer.py::write_revocation()`.
- [ ] IT-12.x: verifier includes `revocacion_factura` chain.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Branch operator accidentally gains write access | Low | REVOKE + trigger + DIAN credentials only in cloud secrets |
| Hash chain break on revocation of already-revoked invoice | Low | Application-level check before write |
| DIAN provider slowness → branch waits | Med | Async pattern: `dian_dispatcher` queue + webhook back to branch |

## 12. Open Questions
- (a) DIAN replacement rule (always replace vs sometimes cancel without replacement)?
- (b) Retention beyond 5 years for compliance disputes?