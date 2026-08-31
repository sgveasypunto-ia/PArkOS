# PRD: clientes_b2b (T17)

> B2B contract extension for `clientes` (corporate contracts). 1:1 optional relationship with the parent `clientes` row. Defines `cantidad` (max vehicles authorized under the corporate contract), `fecha_vencimiento` (contract expiry), and `registro` JSON (contract-specific terms: billing address, payment conditions, commercial contact, observations). The B2B nature of a `clientes` row is determined by the **presence** of a row in `clientes_b2b`.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration_plan.md`](../iteration_plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule I: B2B extension is segregated from cliente CRUD*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.clientes_b2b`
- **SQL name**: `clientes_b2b` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite (legal contract record)
- **Origin**: F1 (schema) + IT-10 (admin CRUD, contract renewal)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; contract attach + renewal + nullification-on-parent-archive documented)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `uuid_cliente` is **UNIQUE** — enforces 1:1 relationship with the parent `clientes` row. Composite UNIQUE constraint prevents two B2B contracts per cliente.
- `cantidad` is `int` — the maximum number of vehicles authorized under the corporate contract (distinct from `tipo_subscripciones.cantidad_maxima_vehiculos` which is per-subscription).
- `fecha_vencimiento` is `date` — when the contract expires; `workers/clientes/expiry_monitor` (T16) watches this and triggers lifecycle enforcement.

## 3. SOLID Atomic Breakdown
- **S**: "one B2B contract for one cliente". The 1:1 extension is the **canonical subtype pattern** in the model — adding the B2B nature to a cliente without forcing all clientes to carry nullable B2B columns.
- **O**: `registro` JSON is the extension point for contract-specific terms (billing address, payment conditions, contact info). New contract attributes don't require schema migration.
- **I**: admin CRUD via `api_admin /clientes-b2b`; branch reads own via `api_sucursal /clientes/{uuid}/b2b` (for operator display at facturacion); `expiry_monitor` cron writes the lifecycle enforcement.
- **D**: `parkos_core/models/V/clientes_b2b.py` (model); `parkos_core/clientes/b2b_contract_service.py` (attach/renew/detach operations).
- **Atomic**: INSERT (admin attaches contract), UPDATE (creates new version on renewal — archive old, new with new `fecha_vencimiento`), DELETE forbidden by FK RESTRICT (parent `clientes` protects via UNIQUE on `uuid_cliente`).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_cliente` | `prod.clientes.uuid` | exactly one (NOT NULL, UNIQUE) | RESTRICT | the B2B cliente (1:1 enforced) |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | bridge — extensions are referenced via `clientes.uuid` JOIN, not directly FK'd |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin attaches contract to existing cliente (parent must have `uuid_tipo_persona='juridica'`) or in same TX as `clientes` INSERT (per `uc.clientes.admin-creates-b2b-with-extension`) |
| UPDATE | YES (archive only) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted with new UUID + new `fecha_vencimiento` / `cantidad` / `registro` |
| DELETE | NO | Archive via version flow; FK RESTRICT prevents; UNIQUE on `uuid_cliente` prevents second contract |

**Special rules**:
- **1:1 enforced** via UNIQUE on `uuid_cliente`. Two contracts per cliente is impossible at DB level.
- The parent `clientes` row MUST have `uuid_tipo_persona='juridica'` (validation enforced at INSERT). B2C natural personas should NOT have a `clientes_b2b` row — it's business-rule inconsistent (a natural person doesn't have a corporate contract).
- On parent `clientes` archive (via PATCH `estado='archivado'` with new version), the extension is also archived via application-level cascade: the next `clientes_b2b` version flow sets `vigente_hasta=NOW()` on the extension row. The DB does NOT cascade automatically (FK RESTRICT prevents delete); application orchestrates the synchronous archive.
- Renewal = new `clientes_b2b` version with extended `fecha_vencimiento` and possibly updated `cantidad` / `registro`. The old version is archived with `vigente_hasta=NOW()`. The expiry monitor (T16 use case 7.4) reads the vigente version to determine which subscriptions are tied to an expired contract.

## 6. CodeGraph Dependencies
- `api_admin/routers/clientes_b2b.py::POST /clientes-b2b` (attach contract), `PATCH /clientes-b2b/{uuid}` (renew or modify), `GET /clientes-b2b`.
- `api_sucursal/routers/clientes.py::GET /clientes/{uuid}/b2b` (operator reads contract details for B2B cliente at facturacion).
- `parkos_core/clientes/b2b_contract_service.py::attach(uuid_cliente, contract_data)`, `renew(uuid_extension, new_fecha_vencimiento)`, `detach_on_cliente_archive(uuid_cliente)`.
- `workers/clientes/expiry_monitor.py` (T16 cron — watches `clientes_b2b.fecha_vencimiento`, enforces subscription lifecycle).
- `web_admin/ClientesDetail/B2BContractTab` (cloud admin manages contract).

## 7. Use Cases enabled by this table

The `clientes_b2b` table is the **B2B subtype discriminator**: a `clientes` row becomes B2B by acquiring a `clientes_b2b` extension row. The extension carries the corporate contract terms (vehicle quota, expiry, billing conditions) that drive subscription pricing and lifecycle enforcement. Use cases below describe the contract attach flow, the renewal version flow, the B2C-to-B2B conversion (via new cliente row + extension), the parent-archive cascade, and the operator display at facturacion.

### 7.1 Use Case: `uc.clientes-b2b.admin-attaches-contract-to-existing-juridica-cliente`

Admin cloud tiene un cliente `juridica` ya creado (per `uc.clientes.admin-creates-b2c-natural` o similar) y quiere attachar el contrato B2B ahora (separado del momento de creación del cliente — útil cuando se firma el contrato después del alta comercial). Crea la fila `clientes_b2b` con `cantidad`, `fecha_vencimiento`, `registro` JSON. Backend valida que el parent `clientes` tiene `uuid_tipo_persona='juridica'` y que NO existe ya otra extension (UNIQUE en `uuid_cliente`). El flujo toca 6 tablas: `clientes_b2b` (W), `clientes` (R para validar tipo_persona + UNIQUE check), `permisos_usuario` (R RBAC), `usuarios` (R admin), `log_transaccional` (W), `sync_queue` (W).

**Actor**: admin

**Pre-conditions**: parent `clientes` row exists with `uuid_tipo_persona='juridica'`; no existing `clientes_b2b` row for this cliente (UNIQUE enforced); admin has `permiso='crear_contratos_b2b'`.

**Steps**:
1. Admin opens `web_admin/ClientesDetail/{uuid_cliente}/B2BContractTab`, clicks `Attach Contract`.
2. Frontend shows `B2BContractForm`: `cantidad=50` (max vehicles), `fecha_vencimiento='2027-12-31'`, `registro={direccion_facturacion:'Cra 7 #123-45', condiciones_pago:'30_dias', contacto_comercial:'comercial@empresa.com', observaciones:'Contrato corporativo anual renovacion automatica'}`.
3. Frontend POSTs `api_admin /clientes-b2b` (admin- JWT) with `{uuid_cliente, cantidad, fecha_vencimiento, registro}`.
4. Backend validates `permisos_usuario` for `permiso='crear_contratos_b2b'`.
5. Backend SELECTs `clientes` WHERE `uuid=$uuid_cliente`. Validates `uuid_tipo_persona=(SELECT uuid FROM tipo_persona WHERE tipo='juridica')`. If not juridica: 422 (business rule violation).
6. Backend SELECTs `clientes_b2b` WHERE `uuid_cliente=$uuid_cliente`. If exists: 409 (UNIQUE violation — only one contract per cliente).
7. Backend opens TX; SELECT chain anchor from `log_transaccional`.
8. Backend INSERTs `clientes_b2b` row (`vigente_desde=NOW(), vigente_hasta=NULL, estado='activo'`).
9. Backend INSERTs `log_transaccional` (`accion='cliente_b2b_creado'`, `tabla_afectada='clientes_b2b'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_branch_or_cloud_anchor`, `datos_anteriores=null`, `datos_nuevos={...snapshot, uuid_cliente, cantidad, fecha_vencimiento}`).
10. `queue_processor.enqueue('clientes_b2b', $new_uuid, $snapshot)` → parametrization push.
11. Backend returns `{uuid, uuid_cliente, vigente_desde}` to frontend.
12. Branches receive parametrization within 30s. UPSERTs locally. Operator in `web_sucursal/ClientesDetail/{uuid}/B2BContractTab` sees the contract terms.

**Tables touched (writes)**: `clientes_b2b` (1 row), `log_transaccional` (1 row), `sync_queue` (1 row).
**Tables touched (reads)**: `clientes` (tipo_persona validation), `clientes_b2b` (UNIQUE check), `tipo_persona` (catalog), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `clientes_b2b.uuid_cliente` → `clientes.uuid` (UNIQUE); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `clientes_b2b.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (cliente_b2b_creado); branch chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `clientes` (tipo validation), `clientes_b2b` (UNIQUE check), `tipo_persona` (catalog), `permisos_usuario`, `log_transaccional`, `usuarios`.
- Writes to: `clientes_b2b` (new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **B2B subtype attachment** flow — distinguishes a juridica cliente WITH corporate contract from one WITHOUT (e.g., a juridica that pays casually per visit). The presence of `clientes_b2b` row is the discriminator.
- Related: after attaching, the admin typically creates `subscripciones_cliente` rows for the corporate cliente's vehicles (per `uc.subscripciones.admin-create`), referencing the `clientes_b2b.uuid` indirectly via `clientes.uuid` JOIN. The B2B contract terms (e.g., bulk discount) are applied via `registro` of the subscription (custom pricing logic).

### 7.2 Use Case: `uc.clientes-b2b.admin-renews-or-modifies-contract-via-version-flow`

Admin cloud renueva el contrato B2B de un cliente existente (ejemplo: el contrato venció o se va a vencer, admin negocia nuevos términos). Crea una nueva versión `[V]` con `fecha_vencimiento` extendida y posiblemente `cantidad` / `registro` modificados. La versión anterior se archiva con `vigente_hasta=NOW()`. Esto es crítico para auditoría: si las condiciones cambiaron (precio, cupo), se preserva el histórico. El flujo toca 6 tablas: `clientes_b2b` (W nueva versión + UPDATE archivo), `clientes` (R), `subscripciones_cliente` (R para identificar cuáles se reactivan — si el contrato venció, las subs están en `estado='vencida'`; renovación puede reactivar), `permisos_usuario` (R), `log_transaccional` (W), `sync_queue` (W).

**Actor**: admin

**Pre-conditions**: existing `clientes_b2b` row vigente; admin has `permiso='actualizar_contratos_b2b'`; new contract terms negotiated.

**Steps**:
1. Admin opens `web_admin/ClientesDetail/{uuid_cliente}/B2BContractTab`, sees current contract: `cantidad=50, fecha_vencimiento=2027-12-31`. Clicks `Renew`.
2. Frontend shows `B2BContractForm` pre-filled with current values; admin edits `cantidad=75` (increased vehicle quota), `fecha_vencimiento='2028-12-31'` (1-year extension), `registro.condiciones_pago='45_dias'` (updated terms).
3. Admin confirms. Frontend PATCHes `api_admin /clientes-b2b/{uuid_vigente}` with `{cantidad: 75, fecha_vencimiento: '2028-12-31', registro: {...new}}`.
4. Backend validates `permisos_usuario` for `permiso='actualizar_contratos_b2b'`.
5. Backend SELECTs current vigente row for archival.
6. Backend opens TX; SELECT chain anchor.
7. Backend UPDATEs old `clientes_b2b` row: SET `vigente_hasta=NOW()`. Capture old data for `datos_anteriores`.
8. Backend INSERTs new `clientes_b2b` row with `vigente_desde=NOW(), vigente_hasta=NULL, estado='activo', cantidad=75, fecha_vencimiento='2028-12-31', registro={...new}`.
9. Backend INSERTs `log_transaccional` (`accion='cliente_b2b_renovado'`, `tabla_afectada='clientes_b2b'`, `uuid_registro_afectado=$new_uuid`, `datos_anteriores={old_cantidad: 50, old_fecha_vencimiento: '2027-12-31', old_registro: {...}}`, `datos_nuevos={new_cantidad: 75, new_fecha_vencimiento: '2028-12-31', new_registro: {...}}`, `uuid_referencia=$old_uuid`).
10. (Optional admin action, separate call) Admin reactivates subscriptions that were marked `vencida` due to the previous expiry: `PATCH /subscripciones-cliente/{uuid}/reactivar`. This creates a new `subscripciones_cliente` version with `estado='activa'`. Per `uc.subscripciones.*`.
11. `queue_processor.enqueue('clientes_b2b', $new_uuid, $snapshot)` + parametrization for the archive update. INSERT 1-2 `sync_queue` rows.
12. Backend returns `{new_uuid, old_uuid_archived, vigente_desde}`.
13. Branches receive parametrization within 30s. UPSERTs locally. Operator sees the new contract terms.
14. `expiry_monitor` next run sees the new vigente version with extended `fecha_vencimiento` → does NOT emit alerts.

**Tables touched (writes)**: `clientes_b2b` (1 new + 1 archive UPDATE), `log_transaccional` (1 row), `sync_queue` (1-2 rows). Optional: `subscripciones_cliente` (new version per reactivated sub).
**Tables touched (reads)**: `clientes_b2b` (vigente lookup), `clientes` (validate parent), `permisos_usuario` (RBAC), `subscripciones_cliente` (optional reactivation check), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `clientes_b2b.uuid_cliente` → `clientes.uuid` (stable across versions); `subscripciones_cliente.uuid_cliente` → `clientes.uuid` (reactivation reads); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `clientes_b2b.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `clientes_b2b.uuid` (old); `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push delivers new version + archive update.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (cliente_b2b_renovado). Branch chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `clientes_b2b` (vigente lookup), `clientes` (validate), `subscripciones_cliente` (optional reactivation), `permisos_usuario`, `log_transaccional`, `usuarios`.
- Writes to: `clientes_b2b` (new + archive), `log_transaccional` (audit), `sync_queue` (parametrization), optional `subscripciones_cliente` (reactivation).
- Cross-cutting: the **version flow on `clientes_b2b` is the canonical renewal pattern**. Every contract change is a new row; old rows are preserved forever for audit. The `datos_anteriores` snapshot in `log_transaccional` is the legal evidence of "what were the terms on date X".
- Related: subscription reactivation is intentionally NOT automatic — admin must explicitly reactivate after renewal, in case the renewal included changed terms that require subscription adjustment (e.g., new pricing tier, new vehicle types).

### 7.3 Use Case: `uc.clientes-b2b.parent-cliente-archive-cascades-extension-via-application`

Admin cloud archiva un cliente `juridica` (per `uc.clientes.*` archive flow — uses `[V]` versioning with `vigente_hasta=NOW()`). Como el cliente archivado ya no debe tener contratos B2B vigentes, la extension `clientes_b2b` también se archiva en la misma TX (aplicación orquesta, NO hay cascade automático en DB porque FK RESTRICT). El flujo toca 5 tablas: `clientes` (W nueva versión archivada), `clientes_b2b` (W nueva versión archivada con `vigente_hasta=NOW()`), `subscripciones_cliente` (W se marcan como inactivas via T16/T18 cascade), `log_transaccional` (W x 2 — uno por `clientes`, uno por `clientes_b2b`), `sync_queue` (W parametrización).

**Actor**: admin

**Pre-conditions**: `clientes` row exists with `estado='activo'`; `clientes_b2b` row exists with `vigente_hasta IS NULL` for this cliente; admin has `permisos='archivar_clientes' AND 'archivar_contratos_b2b'`.

**Steps**:
1. Admin opens `web_admin/ClientesDetail/{uuid_cliente}`, clicks `Archive`.
2. Frontend shows confirmation: "Archivar cliente + su contrato B2B? Las subscripciones serán marcadas inactivas. Esta acción no se puede deshacer."
3. Admin confirms. Frontend PATCHes `api_admin /clientes/{uuid}` with `{estado: 'archivado', archive_reason: 'cliente_desvinculado_2026'}`.
4. Backend opens TX; SELECT chain anchor.
5. Backend SELECTs current vigente `clientes` row. INSERTs new row: `vigente_desde=NOW(), vigente_hasta=NOW(), estado='archivado'`. (Same `vigente_desde` and `vigente_hasta` since the archive is immediate; preserves audit.)
6. Backend SELECTs `clientes_b2b` WHERE `uuid_cliente=$cliente_uuid AND vigente_hasta IS NULL`. If found: INSERTs new row `vigente_desde=NOW(), vigente_hasta=NOW(), estado='inactivo'` (the extension is archived in the same TX).
7. Backend SELECTs `subscripciones_cliente` WHERE `uuid_cliente=$cliente_uuid AND estado='activa'`. For each: INSERTs new version with `vigente_hasta=NOW(), estado='inactiva'` (per `uc.subscripciones.*` archive flow).
8. Backend INSERTs `log_transaccional` for `clientes` archive (`accion='cliente_archivado'`, `datos_anteriores={...}, datos_nuevos={archivado, extension_archived: true, subscriptions_affected: $count}`).
9. Backend INSERTs `log_transaccional` for `clientes_b2b` archive (`accion='cliente_b2b_archivado'`, `uuid_referencia=$cliente_uuid`).
10. (Optional) Backend INSERTs additional `log_transaccional` rows per subscription archive (per `uc.subscripciones.*`).
11. `queue_processor.enqueue` for all archived rows → INSERT multiple `sync_queue` rows.
12. Backend returns `{cliente_uuid, extension_uuid_archived, subscriptions_affected}` to frontend.
13. Branches receive parametrization. UPSERTs archived versions locally. Operator UI for the cliente shows "Archivado" badge; the B2B contract tab shows "Inactive since $date"; subscriptions show "Inactive".

**Tables touched (writes)**: `clientes` (1 archived version), `clientes_b2b` (1 archived version, if exists), `subscripciones_cliente` (1 archived version per active sub), `log_transaccional` (2+ rows), `sync_queue` (multiple).
**Tables touched (reads)**: `clientes` (vigente lookup), `clientes_b2b` (vigente lookup), `subscripciones_cliente` (active filter), `permisos_usuario` (RBAC), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `clientes_b2b.uuid_cliente` → `clientes.uuid` (stable across versions); `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `clientes.uuid` + `clientes_b2b.uuid` (separate rows); `log_transaccional.uuid_referencia` (polymorphic) → `clientes.uuid` (cross-reference); `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push delivers all archived versions within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 2+ rows (cliente_archivado + cliente_b2b_archivado + subscription archives). Each branch chain extends when received.

**Integration with other tables**:
- Reads from: `clientes`, `clientes_b2b`, `subscripciones_cliente`, `permisos_usuario`, `log_transaccional`, `usuarios`.
- Writes to: `clientes` (archived), `clientes_b2b` (archived), `subscripciones_cliente` (archived), `log_transaccional` (2+ rows), `sync_queue` (multiple).
- Cross-cutting: this is the **archive cascade via application** pattern — the DB does NOT cascade-delete or cascade-archive; the application orchestrates the synchronous archive of related rows in the same TX. This is by design (FK RESTRICT prevents cascade-delete, and version flow requires explicit INSERT for the new archived row).
- Related: if a cliente was previously archived and admin wants to "reactivate", admin creates a NEW `clientes` row (different UUID? or same UUID? — current model: same UUID since version flow keeps the UUID stable). The historical archived version stays; the new active version has `vigente_desde=NOW(), vigente_hasta=NULL`. The `clientes_b2b` extension also needs a new version (since the old one was archived). This is the "resurrection" flow — out of MVP, sprint 5 may formalize.

### 7.4 Use Case: `uc.clientes-b2b.branch-operator-displays-contract-on-facturacion`

Operator en la branch está facturando a un cliente B2B y necesita ver los términos del contrato corporativo (cupo disponible, fecha de vencimiento, condiciones de pago) para aplicar correctamente el cobro. Frontend hace GET al endpoint, backend retorna la extension. El operador ve un panel de "Contrato B2B" arriba del form de facturación. **NO genera escrituras** — es READ puro (no extiende la hash chain).

**Actor**: operator (display only)

**Pre-conditions**: B2B cliente has `clientes_b2b` vigente; operator is creating a `factura_electronica` for this cliente.

**Steps**:
1. Operator opens `FacturacionForm`, selects a B2B cliente via `ClienteLookup` (NIT search).
2. Frontend GETs `api_sucursal /clientes/{uuid_cliente}/b2b`.
3. Backend SELECTs `clientes_b2b` WHERE `uuid_cliente=$cliente_uuid AND vigente_hasta IS NULL`. Returns the vigente contract row.
4. Backend also SELECTs COUNT of `subscripciones_cliente` WHERE `uuid_cliente=$cliente_uuid AND estado='activa'`. Returns the active sub count (to display against the `cantidad` quota).
5. Backend returns `{uuid_extension, cantidad, fecha_vencimiento, registro, active_subscriptions_count, available_quota: cantidad - active_subscriptions_count}`.
6. Frontend displays a panel: "Contrato B2B — Cantidad autorizada: 50, Subscripciones activas: 35, Cupo disponible: 15. Vence: 2027-12-31. Condiciones de pago: 30 días. Contacto comercial: comercial@empresa.com".
7. Operator completes the facturacion with awareness of the B2B context.
8. (No writes; no `log_transaccional`; no `sync_queue`. Per SOLID I, reads don't extend the chain.)

**Tables touched (writes)**: NONE.
**Tables touched (reads)**: `clientes_b2b` (vigente lookup), `subscripciones_cliente` (active count), `clientes` (validate), `usuarios_sucursal` (tenant scope), `sucursal` (tenant).
**FKs traversed**: `clientes_b2b.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (read-only).
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO.
- Hash chain impact: **NO** (read-only).

**Integration with other tables**:
- Reads from: `clientes_b2b`, `subscripciones_cliente`, `clientes`, `usuarios_sucursal`, `sucursal`.
- Writes to: NONE.
- Cross-cutting: this is the **operator context display pattern** — operator sees B2B context at the moment of facturacion, enabling informed decisions (e.g., "should I charge this corporate visit per-tariff or per the B2B contract terms?"). The `registro.condiciones_pago` informs whether to apply late-payment fees.
- Related: if the B2B `fecha_vencimiento` is within 7 days, the operator sees a yellow banner "Contrato vence pronto — contacte al cliente para renovar". If expired, red banner "Contrato vencido — el cliente debe renovar antes de facturar como B2B". Operator may proceed as casual if needed (with admin approval).

## 8. Layer-by-Layer Impact
Layers: 1, 6, 13, 24, 28, 31.

## 9. RED Tests
- (RED) F1 schema includes `clientes_b2b` with UNIQUE on `uuid_cliente`.
- (RED) Admin POST `/clientes-b2b` to existing juridica cliente → 201; row persisted.
- (RED) Admin POST to cliente with `uuid_tipo_persona='natural'` → 422 (business rule).
- (RED) Admin POST to cliente with existing `clientes_b2b` → 409 (UNIQUE violation).
- (RED) Admin PATCH `/clientes-b2b/{uuid}` with renewal terms → new version created; old `vigente_hasta=NOW()`.
- (RED) Subscription reactivation after B2B renewal: PATCH `/subscripciones-cliente/{uuid}/reactivar` → new version with `estado='activa'`.
- (RED) Parent `clientes` archive: in same TX, `clientes_b2b` archive version created.
- (RED) Operator GET `/clientes/{uuid}/b2b` → 200 with vigente contract.
- (RED) Operator GET for cliente without B2B → 404.
- (RED) Cross-audience: operador from branch A to `/clientes/{uuid_b}/b2b` (cliente belongs to another branch) → 403.
- (RED) ON DELETE RESTRICT: cannot delete `clientes` while `clientes_b2b` references it (DB-level enforcement + application archive flow).

## 10. Implementation Tasks
- [x] F1.x Schema with UNIQUE on `uuid_cliente`.
- [ ] IT-10.x: `api_admin /clientes-b2b` (POST, PATCH, GET list, GET detail).
- [ ] IT-10.x: `api_sucursal /clientes/{uuid}/b2b` (operator display).
- [ ] IT-10.x: `parkos_core/clientes/b2b_contract_service.py` (attach, renew, detach_on_archive).
- [ ] IT-10.x: `workers/clientes/expiry_monitor.py` integration (T16 cron watches `clientes_b2b.fecha_vencimiento`).
- [ ] IT-10.x: parametrization push for `clientes_b2b` updates.
- [ ] IT-10.x: `web_admin/ClientesDetail/B2BContractTab` (admin UI).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Two contracts per cliente | Low | UNIQUE on `uuid_cliente` prevents at DB level; admin must consolidate before re-attaching |
| B2B attached to natural persona | Low | Validation rejects; admin must fix `clientes.uuid_tipo_persona` first (rare — typically the cliente is correctly typed from creation) |
| Renewal auto-applied to expired subscriptions | Low | NOT automatic; admin must explicitly reactivate subs after renewal (allows term adjustment) |
| Archive cascade partial (some rows archived, others not) | Low | Single TX ensures atomicity; rollback if any INSERT fails |
| Cross-branch B2B contract confusion | Med | Documented: B2B contract is GLOBAL to the cliente, but subscriptions are branch-pinned. Operator may see a B2B contract at one branch but the cliente's active subs may be at another. UI clearly shows scope. |
| Subscription quota mismatch with B2B `cantidad` | Med | `cantidad` is the contract cap; subscriptions may use up to that cap across branches. UI shows per-branch subscription count and global cap. |

## 12. Open Questions
- (a) Multiple `clientes_b2b` per cliente over time (renewals): current model uses version flow (1 vigente row + N archived). Acceptable for MVP; sprint 5 may consider time-range partition for clarity.
- (b) B2B sub-quota per branch: e.g., a B2B cliente with `cantidad=50` may want 20 at Branch A, 30 at Branch B. Current model: subscription count per branch must sum to <= `cantidad`. Application enforces; sprint 5 may formalize as `clientes_b2b_sucursal_cuota` table.
- (c) Cross-corporate hierarchies (parent empresa with subsidiary empresas): out of MVP; sprint 5 may add `clientes_b2b.uuid_cliente_padre` FK.
- (d) Auto-renewal: `registro.auto_renew=true` + `registro.renovacion_dias=365` → cron auto-extends `fecha_vencimiento`. Sprint 5.
- (e) `clientes_b2b` permissions: who can attach/detach contracts? Currently `permiso='crear_contratos_b2b'`. Sprint 5 may split into attach / renew / archive roles.
- (f) Resurrection flow (unarchive a previously archived cliente): create new `clientes` row with same UUID? Or different UUID with cross-reference? Sprint 5.
- (g) Cancellation mid-contract: if admin wants to cancel before `fecha_vencimiento` (e.g., cliente breaches terms), how is the contract ended? Archive with `motivo='cancelacion_anticipada'`. Sprint 5 formalization.
