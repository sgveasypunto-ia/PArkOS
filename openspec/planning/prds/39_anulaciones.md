# PRD: anulaciones (T39)

> `[L-W]` workflow chain for the annulment of an `ingreso` (and its associated `factura`). Each state transition is a NEW row chained by `uuid_anulacion_padre` (named FK for consistency with workflow convention). States: `solicitada` (root) → `aprobada` (cloud admin) → `ejecutada` (cloud admin). Cross-table to `revocacion_factura` (cloud-only) when the anulación targets a facturada ingreso. Cross-table to `ingreso.placa` correction when the anulación targets a non-facturada ingreso (correction of typo via `[L-E]` derived cache, NOT row mutation).

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
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — **relevant** (chain via `uuid_anulacion_padre`)
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.anulaciones`
- **SQL name**: `anulaciones` (with `prod` schema)
- **Enforcement level**: `[L-W]` workflow chain (append-only, REVOKE UPDATE/DELETE)
- **Retention**: 5+ years (DIAN compliance — anulaciones may affect e-facturas)
- **Hash chain**: NO (workflow chain, not source-of-truth for compliance)
- **Origin**: F1 (schema + REVOKE + trigger) + IT-9 (writes per anulación workflow)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated (`gen_random_uuid()` from `pgcrypto`).
- `uuid_anulacion_padre` is self-FK for workflow chaining: 0..1 (NULL on root, $previous_uuid on transitions).
- Travel: branch-origin rows (solicitada) travel to cloud via `sync_queue`. Cloud-origin rows (aprobada, ejecutada) flow back to branch via parametrization push.
- **Workflow chain naming**: this table uses `uuid_anulacion_padre` (named FK per AGENTS.md comment), distinct from `reimpresion_ticket.uuid_padre`. All chain rows of the same anulación point to the same `uuid_ingreso`.

## 3. SOLID Atomic Breakdown
- **S**: "one anulación event or workflow transition" — INSERT in same TX as the originating action + log_transaccional.
- **O**: extensible via migration; new workflow states added as business needs evolve (currently 3: solicitada, aprobada, ejecutada).
- **I**: branch operator API (writer — POST `/anulaciones` for `solicitada`); cloud admin API (writer — POST `/anulaciones/{uuid}/aprobar` for `aprobada`, POST `/anulaciones/{uuid}/ejecutar` for `ejecutada`); admin read API (AnulacionesPanel paginated).
- **D**: `parkos_core/anulaciones/anulacion_writer.py::write_anulacion(uuid_ingreso, uuid_usuario, motivo, estado, uuid_anulacion_padre=None)` — the ONLY writer.
- **Atomic**: INSERT only (workflow chain). REVOKE UPDATE/DELETE on `rol_app`. `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE`.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch |
| `uuid_ingreso` | `prod.ingreso.uuid` | exactly one (NOT NULL) | RESTRICT | the affected ingreso (all chain rows point to the same ingreso) |
| `uuid_usuario` | `prod.usuarios.uuid` | exactly one (NOT NULL) | RESTRICT | the user who executed this transition (operator for solicitada, admin for aprobada/ejecutada) |
| `uuid_anulacion_padre` | `prod.anulaciones.uuid` | 0..1 (nullable, self-ref) | RESTRICT | workflow chain link: NULL on root (solicitada), $previous_uuid on transitions |

### Incoming FKs (cross-table references)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `ingreso.estado` (T04) | (derived) | 0..1 | `ingreso.estado='anulado'` is derived from the existence of an `anulaciones` row with `estado='ejecutada'` pointing to the same `uuid_ingreso` (per .mmd) |
| `facturas.estado` (T05) | (derived) | 0..1 | `facturas.estado='anulada'` is derived from the existence of an `anulaciones` row with `estado='ejecutada'` AND a `factura` linked to the same `uuid_ingreso` |
| `revocacion_factura` (T02) | (FK — see T02) | 0..1 | when anulación targets a facturada ingreso, `ejecutada` triggers `revocacion_factura` insert (cloud-only, hash chain) |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | From `anulacion_writer.py::write_anulacion()` per transition |
| UPDATE | NO | REVOKE + `BEFORE UPDATE OR DELETE` trigger raises `AUDIT_FIRST_INMUTABLE` |
| DELETE | NO | Same trigger; rows preserved for DIAN retention |

**Special rules**:
- **Workflow chain**: root has `uuid_anulacion_padre=NULL, estado='solicitada'`. Transition to `aprobada` has `uuid_anulacion_padre=$root.uuid, estado='aprobada'`. Transition to `ejecutada` has `uuid_anulacion_padre=$approved.uuid, estado='ejecutada'`. State vigente = last row in chain per `uuid_ingreso` (or per root UUID).
- **All chain rows share `uuid_ingreso`**: per .mmd, "todas las filas de la cadena apuntan al mismo ingreso".
- **`uuid_usuario` per transition**: operator for `solicitada`, admin (cloud) for `aprobada` and `ejecutada`. Records WHO executed each transition.
- **Cross-table effects of `ejecutada`**: per .mmd, the `ejecutada` row triggers downstream effects:
  - If the ingreso is facturada: INSERT `revocacion_factura` (cloud-only) + SyncBackEvent to branch + `facturas.estado='anulada'` (derived).
  - If the ingreso is NOT facturada: `ingreso.placa` correction (e.g., for typo) via `[L-E]` derived cache (NOT row mutation); ingresos chain effectively closed.
- **Sprint 5: chain replication**: cloud-origin rows (`aprobada`, `ejecutada`) propagate to branch via parametrization push; branch UPSERTs the new rows in the chain.

## 6. CodeGraph Dependencies
- `parkos_core/anulaciones/anulacion_writer.py::write_anulacion()` (sole writer).
- `api_sucursal/routers/anulaciones.py::POST /anulaciones` (operator solicitud endpoint).
- `api_admin/routers/anulaciones.py::POST /anulaciones/{uuid}/aprobar` (cloud admin approve).
- `api_admin/routers/anulaciones.py::POST /anulaciones/{uuid}/ejecutar` (cloud admin execute — triggers downstream).
- `api_admin/routers/anulaciones.py::GET /anulaciones` (paginated, filterable by estado).
- `api_admin/routers/anulaciones.py::GET /anulaciones/{uuid}/chain` (workflow chain view).
- `parkos_core/dian/cloud/dispatcher.py` (cloud-only — handles `revocacion_factura` insert on ejecutada for facturada ingreso).
- `web_sucursal/AnulacionSolicitarForm` (operator solicitud form).
- `web_admin/AnulacionesPanel` (cloud admin panel for approve/execute).
- `web_admin/AnulacionesPanel/{uuid}/Chain` (workflow chain visualization).

## 7. Use Cases enabled by this table

The `anulaciones` table is the **L-W workflow** for annulment of an `ingreso` (and its associated `factura`). Workflow: `solicitada` (operator) → `aprobada` (cloud admin) → `ejecutada` (cloud admin). The `ejecutada` transition is the critical one — it triggers downstream effects (DIAN revocation for facturada, plate correction for non-facturada). State vigente is the LAST row in the chain. **Manual operator input** for solicitud (motivo); **admin approval** for aprobacion and ejecucion.

### 7.1 Use Case: `uc.anulaciones.operator-solicita-anulacion-placa-typo`

**Actor**: operator (branch)

**Real-world action**: Operator in `web_sucursal` notices a plate typo on an `ingreso` from 5 minutes ago (`placa='ABC123'` should be `placa='ABC132'`). Operator opens `AnulacionSolicitarForm`, selects the `uuid_ingreso`, types motivo. Backend INSERTs `anulaciones` root row with `estado='solicitada', uuid_anulacion_padre=NULL`, INSERTs `log_transaccional`, enqueues for sync.

**Steps**:
1. Operator opens `web_sucursal/AnulacionSolicitarForm`. Form lists active `ingreso` rows (estado='activo' derived).
2. Operator selects `uuid_ingreso=$uuid_ingreso_xyz`, types `motivo='Error de digitación en placa: ABC123 debería ser ABC132'`.
3. Frontend POSTs `api_sucursal /anulaciones` with `{uuid_ingreso, motivo}`.
4. Backend validates RBAC: `permiso='solicitar_anulacion'`.
5. Backend SELECTs `ingreso WHERE uuid=$uuid_ingreso` — confirms `estado='activo'` (derived: no `salidas` row, no `anulaciones` with `estado='ejecutada'`).
6. Backend SELECTs existing anulación check: `SELECT uuid FROM anulaciones WHERE uuid_ingreso=$uuid_ingreso`. If exists with `estado IN ('solicitada', 'aprobada')` → return 409 `anulacion_ya_en_curso`.
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
8. INSERT `anulaciones` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$uuid_ingreso_xyz`, `uuid_usuario=$operator`, `motivo='Error de digitación...'`, `uuid_anulacion_padre=NULL` (ROOT of chain), `timestamp_evento=NOW()`, `estado='solicitada'`).
9. INSERT `log_transaccional` (`accion='anulacion_solicitada'`, `tabla_afectada='anulaciones'`, `uuid_registro_afectado=$anulacion_uuid`, `uuid_usuario=$operator`, `uuid_sucursal=$branch`, `datos_nuevos={uuid_ingreso, motivo, uuid_anulacion_padre:null}`).
10. `queue_processor.enqueue('anulaciones', $uuid, $snapshot)`.
11. Operator UI shows: "Solicitud de anulación enviada. Esperando aprobación del admin."

**Tables touched (writes)**: `anulaciones` (1 root row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `ingreso` (active check), `anulaciones` (existing check), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `anulaciones.uuid_sucursal` → `sucursal.uuid`; `anulaciones.uuid_ingreso` → `ingreso.uuid`; `anulaciones.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `anulaciones.uuid`.

**Sync behavior**:
- Branch → cloud: YES (solicitada propagates).
- Cloud → branch: NO (this is the initial request).
- DIAN trigger: NO (solicitada alone doesn't trigger DIAN; only `ejecutada` for facturada does).
- Hash chain impact: YES — branch chain extends by 2 rows; cloud chain extends on receipt.

**Integration with other tables**:
- Reads from: `ingreso`, `anulaciones` (existing check), `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `anulaciones` (root row), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **solicitud** flow. The ingreso is NOT modified yet — only the workflow chain root is created. The downstream effects happen on `ejecutada`.
- Related: T04 (`ingreso`) covers the active/closed/anulado derivation.

### 7.2 Use Case: `uc.anulaciones.cloud-admin-aprueba-solicitud-extends-chain`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/AnulacionesPanel`, sees pending solicitudes. Clicks one to review: views the chain (just the root for now), the `ingreso` detail, the `motivo`. Admin decides to APPROVE. Backend SELECTs the latest chain row (root `solicitada`), INSERTs a new `anulaciones` row with `uuid_anulacion_padre=$root.uuid, estado='aprobada', uuid_usuario=$admin`, INSERTs `log_transaccional`, enqueues for parametrization push to branch.

**Steps**:
1. Admin opens `web_admin/AnulacionesPanel`, filter `estado='solicitada'`.
2. Frontend GETs `api_admin /anulaciones?estado=solicitada` (paginated).
3. Admin clicks a solicitud → opens `AnulacionDetail` with chain visualization: 1 row `solicitada`, JOIN `ingreso`, JOIN `usuarios` (the operator).
4. Admin reviews motivo, the operator's identity, the ingreso detail. Decides to approve.
5. Admin clicks `Aprobar`. Frontend POSTs `api_admin /anulaciones/{uuid}/aprobar` with `{observaciones_admin}`.
6. Backend validates RBAC: `permiso='aprobar_anulacion'`.
7. Backend SELECTs latest chain row: `SELECT * FROM anulaciones WHERE uuid=$uuid OR uuid_anulacion_padre=$uuid ORDER BY created_at DESC LIMIT 1` — returns the `solicitada` row.
8. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch_of_ingreso`.
9. INSERT `anulaciones` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$same_ingreso`, `uuid_usuario=$admin`, `motivo='Aprobación: $observaciones_admin'`, `uuid_anulacion_padre=$latest.uuid` (CHAIN LINK to root), `timestamp_evento=NOW()`, `estado='aprobada'`).
10. INSERT `log_transaccional` (`accion='anulacion_aprobada'`, `tabla_afectada='anulaciones'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin`, `uuid_sucursal=$branch`, `datos_anteriores={estado:'solicitada', uuid_anulacion_padre:$root_uuid}`, `datos_nuevos={estado:'aprobada', uuid_anulacion_padre:$root_uuid, observaciones_admin}`).
11. `queue_processor.enqueue('anulaciones', $new_uuid, $snapshot)` — parametrization push to branch.
12. Branch receives within 30s; UPSERTs the new row in the chain. Branch UI updates: "Solicitud APROBADA por admin. Pendiente de ejecución."
13. Admin UI now shows the chain: root `solicitada` → transition `aprobada`. 2 rows. Filter `estado='aprobada'` shows this and other pending ejecucion.

**Tables touched (writes)**: `anulaciones` (1 new chain row, `estado='aprobada'`), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `anulaciones` (previous chain row), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `anulaciones.uuid_anulacion_padre` → `anulaciones.uuid` (workflow self-FK); other FKs per parent row.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push.
- DIAN trigger: NO (aprobada alone doesn't trigger DIAN).
- Hash chain impact: YES — cloud chain extends by 1 row; branch chain extends on parametrization receipt.

**Integration with other tables**:
- Reads from: `anulaciones` (previous chain row), `permisos_usuario`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `anulaciones` (new chain row), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the canonical **approval** transition. State vigente is the LAST row in the chain. The aprobado ingreso is still `activo` (no `ejecutada` yet); the anulación is approved but pending execution.
- Related: T41 (`alerta`) may surface an alerta if admin delays execution > N hours.

### 7.3 Use Case: `uc.anulaciones.cloud-admin-ejecuta-facturada-triggers-revocacion-dian`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/AnulacionesPanel`, filter `estado='aprobada'`. Clicks the anulación for a facturada ingreso (the ingreso already has a `factura_electronica` issued). Admin clicks `Ejecutar`. Backend SELECTs the latest chain row (`aprobada`), INSERTs new `anulaciones` row with `estado='ejecutada'`, INSERTs `revocacion_factura` (cloud-only, hash chain), INSERTs `SyncBackEvent` for branch, INSERTs `log_transaccional`. The `facturas.estado` is now 'anulada' (derived from the existence of an `anulaciones` row with `estado='ejecutada'`).

**Steps**:
1. Admin opens `web_admin/AnulacionesPanel`, filter `estado='aprobada'`.
2. Admin clicks anulación with `uuid_ingreso=$uuid_xyz`. UI shows: "Este ingreso tiene una factura emitida con DIAN número FAC-12345. La ejecución generará una revocación DIAN."
3. Admin confirms. Frontend POSTs `api_admin /anulaciones/{uuid}/ejecutar` with `{observaciones_ejecucion}`.
4. Backend validates RBAC: `permiso='ejecutar_anulacion'`.
5. Backend SELECTs latest chain row: returns `aprobada`.
6. Backend SELECTs `facturas WHERE uuid_ingreso=$uuid_ingreso`. Returns the factura (with `uuid_factura_electronica` populated).
7. Backend SELECTs `factura_electronica WHERE uuid_factura=$factura_uuid` — returns the e-factura with `estado='activa'` derived.
8. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
9. INSERT `anulaciones` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$same_ingreso`, `uuid_usuario=$admin`, `motivo='Ejecución: $observaciones_ejecucion'`, `uuid_anulacion_padre=$approved.uuid` (CHAIN LINK), `timestamp_evento=NOW()`, `estado='ejecutada'`).
10. Backend INSERTs `revocacion_factura` row (T02): `uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_factura_electronica=$e_factura_uuid`, `uuid_factura_electronica_reemplazo=NULL` (anulada directa, sin reemplazo per .mmd "anulada directamente (sin reemplazo)"), `motivo='Anulación de ingreso por $motivo'`, `timestamp=NOW()`, `hash_anterior=$last_rev.hash_actual`, `hash_actual=SHA256(...)`. Cloud-only hash chain extends.
11. INSERT `log_transaccional` (`accion='anulacion_ejecutada'`, `tabla_afectada='anulaciones'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin`, `uuid_sucursal=$branch`, `datos_nuevos={estado:'ejecutada', uuid_anulacion_padre:$approved_uuid}`).
12. INSERT `log_transaccional` (`accion='revocacion_factura_creada'`, `tabla_afectada='revocacion_factura'`, `uuid_registro_afectado=$revocacion_uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_nuevos={uuid_factura_electronica, motivo, hash_anterior, hash_actual}`).
13. INSERT `SyncBackEvent` (concept) for branch: `{tabla_origen='facturas', uuid_registro:$factura_uuid, datos_nuevos:{estado:'anulada'}, timestamp}`.
14. `queue_processor.enqueue('anulaciones', $new_uuid, $snapshot)` for branch propagation.
15. Branch receives within 30s; UPSERTs the chain row + processes the SyncBackEvent → updates `facturas.estado` derived cache (or just relies on the derived query). Branch UI shows: "Factura anulada. Reimpresión deshabilitada."
16. The `factura_electronica.estado` is now `'revocada'` derived (existence of `revocacion_factura` row pointing to it).

**Tables touched (writes)**: `anulaciones` (1 new chain row, `estado='ejecutada'`), `revocacion_factura` (1 row, cloud-only, hash chain), `log_transaccional` (2 rows), `SyncBackEvent` (1 concept), `sync_queue` (2 items: anulaciones + parametrization push).
**Tables touched (reads)**: `anulaciones` (previous chain row), `facturas` (factura lookup), `factura_electronica` (e-factura lookup), `log_transaccional` (chain anchor + last hash for revocacion_factura chain), `usuarios`, `sucursal`.
**FKs traversed**: `anulaciones.uuid_anulacion_padre` → `anulaciones.uuid`; `revocacion_factura.uuid_sucursal` → `sucursal.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `factura_electronica.uuid_factura` → `facturas.uuid`; `factura_electronica.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `anulaciones.uuid` or `revocacion_factura.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — chain replication + SyncBackEvent.
- DIAN trigger: YES (this IS the DIAN revocation flow).
- Hash chain impact: YES — cloud chain extends by 1 row for `anulaciones.ejecutada` + 1 row for `revocacion_factura` (which extends the revocacion_factura hash chain). Branch chain extends on parametrization receipt.

**Integration with other tables**:
- Reads from: `anulaciones`, `facturas`, `factura_electronica`, `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `anulaciones` (ejecutada), `revocacion_factura` (cloud-only hash chain), `log_transaccional`, `SyncBackEvent`, `sync_queue`.
- Cross-cutting: this is the **DIAN-integrated execution** path. The ejecutada triggers the legal DIAN revocation via `revocacion_factura`. The `facturas.estado` and `factura_electronica.estado` are DERIVED from the existence of these records; never mutated.
- Related: T02 (`revocacion_factura`) covers the hash chain in detail; T03 (`factura_electronica`) covers the estado derivation.

### 7.4 Use Case: `uc.anulaciones.cloud-admin-ejecuta-no-facturada-correccion-placa`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/AnulacionesPanel`, filter `estado='aprobada'`. Clicks an anulación for a NON-facturada ingreso (the ingreso was still active, no factura yet — e.g., the customer left without paying). Admin clicks `Ejecutar`. Backend SELECTs the latest chain row (`aprobada`), confirms NO factura exists for the ingreso, INSERTs new `anulaciones` row with `estado='ejecutada'`, INSERTs `log_transaccional`. The `ingreso.placa` correction is recorded via `[L-E]` derived cache (the ingreso row is NOT mutated; the corrected placa is logged in `anulaciones.motivo`). The ingresos chain is effectively closed.

**Steps**:
1. Admin opens `web_admin/AnulacionesPanel`, filter `estado='aprobada'`. Sees anulación with `uuid_ingreso=$uuid_xyz`.
2. UI shows: "Este ingreso NO tiene factura emitida. La ejecución cerrará el ingreso como anulado (no se requiere revocación DIAN). La placa corregida es ABC132."
3. Admin confirms. Frontend POSTs `api_admin /anulaciones/{uuid}/ejecutar` with `{observaciones_ejecucion, placa_corregida: 'ABC132'}`.
4. Backend validates RBAC: `permiso='ejecutar_anulacion'`.
5. Backend SELECTs latest chain row: returns `aprobada`.
6. Backend SELECTs `facturas WHERE uuid_ingreso=$uuid_ingreso` — returns NO rows (no factura).
7. Backend opens TX; SELECT chain anchor from `log_transaccional`.
8. INSERT `anulaciones` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_ingreso=$same_ingreso`, `uuid_usuario=$admin`, `motivo='Ejecución: $observaciones_ejecucion. Placa corregida: $placa_corregida'`, `uuid_anulacion_padre=$approved.uuid`, `timestamp_evento=NOW()`, `estado='ejecutada'`).
9. INSERT `log_transaccional` (`accion='anulacion_ejecutada'`, `tabla_afectada='anulaciones'`, `uuid_registro_afectado=$new_uuid`, `datos_nuevos={estado:'ejecutada', uuid_anulacion_padre:$approved_uuid, placa_corregida}`).
10. (Optional) Sprint 5: INSERT `ingreso_correcciones` row (separate `[A]` table) with `uuid_ingreso=$uuid, campo='placa', valor_anterior='ABC123', valor_nuevo='ABC132'`. For now, the correction is captured in `anulaciones.motivo` + log_transaccional `datos_nuevos.placa_corregida`.
11. `queue_processor.enqueue('anulaciones', $new_uuid, $snapshot)`.
12. Branch receives within 30s; UPSERTs the chain row. Branch UI updates: "Ingreso anulado. Placa corregida a ABC132."
13. The `ingreso.estado` is now `'anulado'` derived (existence of `anulaciones` with `estado='ejecutada'`).

**Tables touched (writes)**: `anulaciones` (1 new chain row), `log_transaccional` (1 row), `sync_queue` (1 item).
**Tables touched (reads)**: `anulaciones` (previous chain row), `facturas` (confirm no factura), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
**FKs traversed**: `anulaciones.uuid_anulacion_padre` → `anulaciones.uuid`; `ingreso.uuid_sucursal` → `sucursal.uuid` (derived state check); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `anulaciones.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — chain replication.
- DIAN trigger: NO (no e-factura to revoke).
- Hash chain impact: YES — cloud chain extends by 1 row; branch chain extends on parametrization receipt.

**Integration with other tables**:
- Reads from: `anulaciones`, `facturas` (none), `log_transaccional`, `usuarios`, `sucursal`.
- Writes to: `anulaciones` (ejecutada), `log_transaccional`, `sync_queue`.
- Cross-cutting: this is the **non-facturada execution** path. NO `revocacion_factura` (no e-factura). The ingreso closes via derived state. The placa correction is logged but NOT a row mutation on `ingreso` (per `[L-E]` append-only semantics; corrections live in `anulaciones.motivo` or sprint 5 `ingreso_correcciones`).
- Related: T04 (`ingreso`) covers the estado='anulado' derivation.

### 7.5 Use Case: `uc.anulaciones.admin-queries-pending-and-resolved-with-chain-view`

**Actor**: admin (cloud)

**Real-world action**: Admin opens `web_admin/AnulacionesPanel`. Sees filterable list: `estado` ∈ {solicitada, aprobada, ejecutada}, `uuid_sucursal`, `uuid_ingreso`, date range. Admin clicks any anulación → opens `AnulacionDetail` with the FULL workflow chain (root + all transitions), JOIN to `ingreso` (with derived estado), JOIN to `facturas` (if facturada), JOIN to `revocacion_factura` (if ejecutada + facturada).

**Steps**:
1. Admin opens `web_admin/AnulacionesPanel`. Default filter: `estado='solicitada'` (pending requests).
2. Frontend GETs `api_admin /anulaciones?estado=solicitada&uuid_sucursal=&desde=&hasta=&limit=` (paginated).
3. Backend runs: `SELECT a.*, u.nombre AS operador_nombre, i.placa, i.uuid_tipo_vehiculo FROM anulaciones a JOIN usuarios u ON a.uuid_usuario=u.uuid JOIN ingreso i ON a.uuid_ingreso=i.uuid WHERE a.estado='solicitada' [AND a.uuid_sucursal=$branch] ORDER BY a.created_at DESC LIMIT 50`.
4. Admin clicks a row → opens `AnulacionDetail`.
5. Frontend GETs `api_admin /anulaciones/{uuid}/chain` — returns the FULL chain (root + all transitions) with JOINs.
6. UI renders the chain as a timeline: solicitud (operator name, motivo, timestamp) → aprobación (admin name, observaciones, timestamp) → ejecución (admin name, observaciones, timestamp, downstream effects).
7. If facturada: UI shows the `revocacion_factura` link (with hash chain status). If non-facturada: UI shows the placa correction in the chain.
8. (Optional) Admin exports the chain to PDF for audit.
9. (Optional) Admin filters by `tipo_ejecucion='facturada'` vs `'no_facturada'` (sprint 5: add this filter to the chain query).

**Tables touched (writes)**: NONE for the read.
**Tables touched (reads)**: `anulaciones` (full chain via recursive CTE or self-join), `usuarios` (operator + admin names), `ingreso` (placa, tipo_vehiculo), `facturas` (if facturada), `factura_electronica` (if applicable), `revocacion_factura` (if executed + facturada), `sucursal` (display).
**FKs traversed**: `anulaciones.uuid_anulacion_padre` → `anulaciones.uuid` (chain self-FK); `anulaciones.uuid_ingreso` → `ingreso.uuid`; `anulaciones.uuid_usuario` → `usuarios.uuid`; `anulaciones.uuid_sucursal` → `sucursal.uuid`; `facturas.uuid_ingreso` → `ingreso.uuid`; `factura_electronica.uuid_factura` → `facturas.uuid`; `revocacion_factura.uuid_factura_electronica` → `factura_electronica.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read of historical data).
- Cloud → branch: NO.
- DIAN trigger: NO.
- Hash chain impact: NO.

**Integration with other tables**:
- Reads from: `anulaciones` (chain), `usuarios`, `ingreso`, `facturas`, `factura_electronica`, `revocacion_factura`, `sucursal`.
- Writes to: NONE.
- Cross-cutting: this is the **chain visualization** view. The recursive CTE `WITH RECURSIVE chain AS (SELECT * FROM anulaciones WHERE uuid=$1 UNION ALL SELECT next.* FROM anulaciones next JOIN chain c ON next.uuid_anulacion_padre=c.uuid) SELECT * FROM chain ORDER BY created_at` returns the full chain.
- Related: `_shared/workflow-chains.md` documents the chain resolution query pattern.

## 8. Layer-by-Layer Impact
Layers impacted: 1 (DB schema + REVOKE + trigger), 2 (DB triggers), 5 (audit constraints — REVOKE), 6 (cloud admin API), 7 (branch API), 8 (Pydantic schemas), 10 (cloud sync worker), 11 (branch sync worker), 12 (sync_queue interop), 13 (web_admin AnulacionesPanel), 14 (web_sucursal AnulacionSolicitarForm), 15 (shadcn UI), 16 (Zustand anulaciones state), 20 (structlog), 24 (pytest), 28 (docker compose), 29 (DIAN provider — revocacion_factura cloud-only), 33 (DIAN compliance docs).

## 9. RED Tests
- (RED) INSERT `anulaciones` from `rol_app` → success.
- (RED) UPDATE `prod.anulaciones` → `AUDIT_FIRST_INMUTABLE`.
- (RED) DELETE `prod.anulaciones` → `AUDIT_FIRST_INMUTABLE`.
- (RED) Workflow chain: root `uuid_anulacion_padre=NULL, estado='solicitada'`; transition `uuid_anulacion_padre=$root.uuid, estado='aprobada'`.
- (RED) All chain rows share the same `uuid_ingreso`.
- (RED) State vigente query: `ORDER BY created_at DESC LIMIT 1` returns the latest row.
- (RED) Solicitud for non-active ingreso (already `cerrado` or `anulado`) → 422.
- (RED) Duplicate solicitud (existing chain with `estado IN ('solicitada', 'aprobada')`) → 409 `anulacion_ya_en_curso`.
- (RED) Aprobada before solicitud: POST `/aprobar` with no chain root → 422.
- (RED) Ejecutada for facturada: triggers `revocacion_factura` insert (cloud-only, hash chain extends).
- (RED) Ejecutada for non-facturada: NO `revocacion_factura` insert; `ingreso.estado` derived `'anulado'`.
- (RED) `ingreso.estado` derived query: `EXISTS(SELECT 1 FROM anulaciones WHERE uuid_ingreso=$X AND estado='ejecutada')` → `anulado`.
- (RED) `facturas.estado` derived query (for ingreso's factura): same derivation.
- (RED) Chain replication: cloud-origin chain rows (aprobada, ejecutada) propagate to branch within 30s.
- (RED) RBAC: operator without `permiso='solicitar_anulacion'` → 403; admin without `permiso='aprobar_anulacion'` → 403; admin without `permiso='ejecutar_anulacion'` → 403.
- (RED) Motivo is required (NOT NULL constraint enforced at INSERT).
- (RED) `costos_servicios.costo` snapshot NOT applicable here (no cost in anulación flow).

## 10. Implementation Tasks
- [x] F1.x Schema + REVOKE + trigger.
- [ ] F1.x `anulacion_writer.py::write_anulacion()` helper.
- [ ] F1.x Recursive CTE query helper for chain resolution.
- [ ] IT-9.x: `api_sucursal/routers/anulaciones.py::POST /anulaciones` (operator solicitud).
- [ ] IT-9.x: existing anulación check (no duplicate pending).
- [ ] IT-9.x: `api_admin/routers/anulaciones.py::POST /anulaciones/{uuid}/aprobar`.
- [ ] IT-9.x: `api_admin/routers/anulaciones.py::POST /anulaciones/{uuid}/ejecutar` (with facturada check + revocacion_factura trigger).
- [ ] IT-9.x: `api_admin/routers/anulaciones.py::GET /anulaciones` (paginated, filterable).
- [ ] IT-9.x: `api_admin/routers/anulaciones.py::GET /anulaciones/{uuid}/chain`.
- [ ] IT-9.x: chain replication via parametrization push (cloud-origin rows propagate).
- [ ] IT-9.x: SyncBackEvent on ejecutada for facturada (T03 interop).
- [ ] IT-9.x: `web_sucursal/AnulacionSolicitarForm` (operator solicitud).
- [ ] IT-9.x: `web_admin/AnulacionesPanel` (filter + list + approve/execute).
- [ ] IT-9.x: `web_admin/AnulacionesPanel/{uuid}/Chain` (workflow chain visualization).
- [ ] Sprint 5: `ingreso_correcciones` table for explicit `[L-E]` correction chain (vs current `anulaciones.motivo` text).
- [ ] Sprint 5: filter `tipo_ejecucion='facturada' | 'no_facturada'` in admin queries.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Admin ejecuta for non-facturada but factura is issued between check and INSERT | Low | TX wraps check + INSERTs; if factura appears mid-TX, abort |
| Admin aprueba but delays ejecucion indefinitely → ingreso stuck in limbo | Med | `alerta` reminder after 24h post-aprobada (T41); sprint 5: auto-expiration policy |
| Operator requests anulación for typo but actual intent is fraud (delete evidencia) | Low | Approval workflow requires admin review with motivo; audit chain captures everything |
| Placa correction NOT applied to ingreso row (only in anulaciones.motivo) — operational confusion | Med | Sprint 5: explicit `ingreso_correcciones` table; until then, branch UI shows "placa corregida" with reference to anulacion UUID |
| Ejecutada for facturada triggers revocation but customer's e-factura was already downloaded | Low | DIAN accepts revocation regardless; customer is notified via email (sprint 5: notification integration) |
| Chain replication delays → branch sees outdated chain | Low | Replication is best-effort within 30s; admin can force re-push via `POST /anulaciones/{uuid}/replicate` |
| `factura_electronica.estado='revocada'` derived but cross-reference to other tables broken (e.g., `reimpresion_ticket` still tries to reprint) | Low | Sprint 5: gating on `factura_electronica.estado` for reprint (already implemented in T38) |
| Motivo is sensitive (PII) but stored in plain text | Low | Motivo is operator-typed; encryption-at-rest for the column is sprint 5+ |

## 12. Open Questions
- (a) Should anulación approval be a single-step (aprobada → ejecutada in one action) or always two-step? Currently two-step for audit clarity.
- (b) Should `ejecutada` for non-facturada also insert a `salidas` row (with `fecha_salida=NULL`) to formally close the ingreso via the `[L-E]` derived state? Sprint 5.
- (c) Refund flow: if the ingreso was paid but not yet exited, does anulación trigger automatic refund of `factura_pagos`? Currently NO — separate flow.
- (d) Should the chain include a `rechazada` state (admin rejects the solicitud without ejecuting)? Currently no such state; admin simply doesn't transition; the solicitud stays pending until expiration.
- (e) Should `anulaciones` support bulk anulacion (multiple ingresos in one request)? Sprint 5.
- (f) Should `motivo` be ENUM or free-text? Currently free-text; may constrain to common values.
- (g) Cross-tenant scope: admin from chain A approving for branch B — requires `permisos_usuario` for both branches + `sucursales_permitidas` in admin JWT.
- (h) Notification to customer when anulación is ejecutada: should the system email/SMS? Sprint 5 (notification integration).
