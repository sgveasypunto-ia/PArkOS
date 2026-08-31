# PRD: documentos (T13)

> Documents associated with branches (business licenses, B2B signed contracts, municipal permits, operational damage photos). Stored as base64-encoded content (`documento_b64`); per-version `[V]` rows preserve upload history for audit. Used by both admin (regulatory upload) and operator (operational upload with permission gate).

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule O: `registro` JSON as extension point (sprint 5 schema addition for expiry)*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.documentos`
- **SQL name**: `documentos` (with `prod` schema)
- **Enforcement level**: `[V]` projection (every upload creates a new version; old version archived with `vigente_hasta=NOW()`)
- **Retention**: indefinite (regulatory requirement for licenses/contracts; 5+ years for operational)
- **Origin**: F1 (schema + placeholder seed in `uc.sucursal.admin-onboarding-pairing-flow`) + IT-2 (writes from admin + operator)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; version-flow + expiry-alert + cloud audit retrieval documented)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `documento_b64` is `text` (base64-encoded PDF/JPG content). Max size per row: 10 MB (enforced application-side; larger files would need S3-compatible storage — sprint 5 deferred).
- `tipo` is free-form string with business-level enum: `'licencia_comercial'`, `'permiso_municipal'`, `'contrato_b2b'`, `'foto_dano'`, `'foto_evidencia'`, `'certificado'`, `'otro'`. Application validates against known set at INSERT/PATCH time.
- `formato` indicates encoding: `'pdf'`, `'jpg'`, `'png'`. New formats added via migration if needed (per SOLID O).
- **Schema extension note**: `registro` JSON column (`{fecha_vencimiento, numero_resolucion, observaciones_admin}`) is required for the expiry alert use case (7.3). Sprint 5 migration adds the column; current schema does not include it. The use case documents the design assuming the column exists.

## 3. SOLID Atomic Breakdown
- **S**: "one document attached to one branch" — a regulatory artifact (license, permit) or operational artifact (damage photo, B2B signed contract).
- **O**: `registro` JSON (sprint 5) is the extension point for per-document metadata (expiry dates, resolution numbers, admin notes). Adding new metadata doesn't require schema migration.
- **I**: segregated audiences — admin upload via `api_admin /documentos` (regulatory); operator upload via `api_sucursal /documentos/{uuid}/upload` with `permiso='subir_documentos_operativos'` (operational); branch reads own; cloud admin reads all for audit.
- **D**: `parkos_core/models/V/documentos.py` (model); `parkos_core/documentos/version_service.py` (versioning logic); `parkos_core/documentos/expiry_monitor.py` (cron worker that scans for expiring docs); `parkos_core/documentos/storage.py` (base64 ↔ binary conversion, SHA256 integrity check).
- **Atomic**: INSERT (new version), UPDATE forbidden directly (the version flow uses INSERT + UPDATE old with `vigente_hasta=NOW()`); DELETE forbidden (archive via UPDATE). Cloud admin can read any version via bi-temporal query.

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_sucursal` | `prod.sucursal.uuid` | exactly one (NOT NULL) | RESTRICT | the branch that owns the document |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | documents are leaf data; no FK references INTO this table |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin (regulatory) or operator with permission (operational); inside TX + `log_transaccional` |
| UPDATE | YES (archive only) | UPDATE old row sets `vigente_hasta=NOW()`; NEVER modify content of an existing version (preserves audit) |
| DELETE | NO | Archive via UPDATE; FK RESTRICT also prevents |

**Special rules**:
- Versioning is mandatory: every "upload" creates a NEW row with new UUID. The old row is archived (`vigente_hasta=NOW()`). Content is immutable once inserted.
- SHA256 hash of `documento_b64` content is stored in `registro.sha256` (sprint 5 JSON extension) for integrity verification. Any read computes the hash and compares; mismatch → `HASH_MISMATCH` exception.
- Max file size: 10 MB encoded (≈ 7.5 MB binary). Larger files need S3 — deferred.
- The `documentos` placeholder row seeded in `uc.sucursal.admin-onboarding-pairing-flow` step 5 (`tipo='licencia_comercial', documento_b64=NULL`) is the "empty version" until the operator uploads the real content. Until then, the placeholder is the vigente row with empty content.

## 6. CodeGraph Dependencies
- `api_admin/routers/documentos.py::POST /documentos` (admin regulatory upload).
- `api_admin/routers/documentos.py::PATCH /documentos/{uuid}` (admin replaces — creates new version, archives old).
- `api_sucursal/routers/documentos.py::POST /documentos/{uuid_placeholder}/upload` (operator fills placeholder — same version flow).
- `api_sucursal/routers/documentos.py::GET /documentos` (own branch scoped).
- `api_admin/routers/documentos.py::GET /documentos/{uuid}/audit` (cloud audit retrieval — bi-temporal query of all versions).
- `workers/documentos/expiry_monitor.py` (cron — scans for expiring docs, emits `alerta tipo_alerta='documento_por_vencer'` / `'documento_vencido'`).
- `web_admin/DocumentosList`, `DocumentosForm`, `DocumentosDetail/VersionHistory` (cloud audit UI).
- `web_sucursal/DocumentosTab`, `DocumentUploadForm`.

## 7. Use Cases enabled by this table

The `documentos` table is the **regulatory and operational artifact store**: business licenses uploaded by admin at branch onboarding (or renewal), municipal permits, B2B signed contracts, and operational damage photos uploaded by branch operators. The `[V]` versioning is critical — every upload creates a new immutable row, preserving the upload history for legal audit. Use cases below describe the upload flows (admin vs operator), the bi-temporal audit retrieval, and the expiry monitoring that drives compliance alerts.

### 7.1 Use Case: `uc.documentos.admin-regulatory-upload-replaces-expired-license`

Admin cloud sube una nueva versión de la licencia comercial de una branch (la anterior venció o se renueva). Crea una nueva fila `[V]` con el contenido actualizado, archiva la versión anterior con `vigente_hasta=NOW()`, y la parametrización push propaga el cambio a la branch para que el operador local vea la versión vigente. Si la licencia tiene `registro.fecha_vencimiento`, el `expiry_monitor` worker la vigila y emite alertas cuando se aproxima el vencimiento. El flujo toca 6 tablas: `documentos` (W nueva versión + UPDATE archivo de la anterior), `sucursal` (R tenant), `usuarios` (R admin actor), `permisos_usuario` (R RBAC), `log_transaccional` (W), `sync_queue` (W).

**Actor**: admin

**Pre-conditions**: branch exists with `estado='activo'`; previous license version exists (or first-time upload, where only the placeholder exists); admin has `permiso='subir_documentos_regulatorios'`; PDF file ready (≤10 MB encoded).

**Steps**:
1. Admin opens `web_admin/SucursalDetail/{branch_uuid}/DocumentosTab`, clicks `Upload License`. (Or: `web_admin/DocumentosList → New → select branch + tipo='licencia_comercial'`.)
2. Frontend shows `DocumentUploadForm`: branch selector (auto-filled if accessed from SucursalDetail), `tipo` dropdown (`licencia_comercial` selected by default), file input (PDF), optional fields for `registro: {fecha_vencimiento: '2027-12-31', numero_resolucion: 'RES-2026-12345', observaciones_admin: 'Renovación anual'}`.
3. Admin selects the PDF file. Frontend reads as base64 client-side, computes SHA256, displays preview.
4. Frontend POSTs `api_admin /documentos` (admin- JWT) with `{uuid_sucursal, tipo:'licencia_comercial', formato:'pdf', documento_b64:<b64>, registro:{fecha_vencimiento:'2027-12-31', numero_resolucion:'...', sha256:<hash>, file_size_bytes: $X, mime_type:'application/pdf'}}`.
5. Backend validates: `permisos_usuario` lookup for `permiso='subir_documentos_regulatorios'`; rejects 403 if missing.
6. Backend validates file: size ≤ 10 MB encoded, MIME type matches `formato`, SHA256 matches recomputed.
7. Backend SELECTs current `documentos` row WHERE `uuid_sucursal=$branch AND tipo='licencia_comercial' AND vigente_hasta IS NULL` (the vigente version, possibly the placeholder).
8. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$branch`.
9. Backend INSERTs new `documentos` row: new UUID, `vigente_desde=NOW(), vigente_hasta=NULL, documento_b64=$b64, registro=$json`. The "version" is implicit (always new UUID); ordering is by `created_at`.
10. Backend UPDATEs the previous vigente row: SET `vigente_hasta=NOW()` (archive). The old row is preserved forever for audit.
11. Backend INSERTs `log_transaccional` (`accion='documento_subido_admin'`, `tabla_afectada='documentos'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$branch`, `datos_anteriores={old_version_summary: {uuid, sha256, file_size, created_at}}`, `datos_nuevos={new_version_summary: {uuid, sha256, file_size, created_at, registro}}`, `uuid_referencia=$old_uuid`).
12. `queue_processor.enqueue('documentos', $new_uuid, $snapshot)` → INSERT `sync_queue` row (parametrization push to branch).
13. Backend returns `{uuid, sha256, file_size, uploaded_at, old_version_archived: true}` to frontend.
14. Branch receives parametrization within 30s. `job_sync_sucursal::drain_outbox_parametrizacion` UPSERTs the new `documentos` row locally (idempotent by UUID); UPDATE local old row to `vigente_hasta=NOW()` (matches cloud).
15. Operator in `web_sucursal/DocumentosTab` sees the new vigente version badge with green check; old version appears in the "Versions" history view but marked archived.

**Tables touched (writes)**: `documentos` (1 new + 1 archive UPDATE), `log_transaccional` (1 row), `sync_queue` (1 row).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `usuarios` (admin actor), `documentos` (vigente version lookup), `log_transaccional` (chain anchor), `sucursal` (tenant).
**FKs traversed**: `documentos.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `documentos.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `documentos.uuid` (old version); `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the new `documentos` row within 30s. Branch UPSERTs; UPDATE old row's `vigente_hasta` matches cloud.
- DIAN trigger: NO (documentos are regulatory, not fiscal).
- Hash chain impact: YES — cloud chain extends by 1 row (documento_subido_admin); branch chain extends by 1 row when parametrization received.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `usuarios` (admin actor), `documentos` (vigente version lookup), `log_transaccional` (chain anchor), `sucursal` (tenant).
- Writes to: `documentos` (new version + archive old), `log_transaccional` (audit), `sync_queue` (parametrization push).
- Cross-cutting: the `[V]` versioning is the legal guarantee — the license that was active on 2026-03-15 can be retrieved via bi-temporal query even after the 2027 renewal overwrites it. This is essential for audit when a regulatory body asks "show me the license that was in force when the parking lot received customer X".
- Related: if `registro.fecha_vencimiento` is set, the `expiry_monitor` worker (use case 7.3) starts watching the document for expiry alerts 30 days before the date.

### 7.2 Use Case: `uc.documentos.operator-uploads-damage-photo-with-permission`

Operator en la branch sube una foto de daño a un vehículo del cliente (rayón, golpe en barrera, daño por intento de robo). El operador NO es admin — usa su permiso `subir_documentos_operativos`. La foto se almacena como una nueva versión `[V]` con `tipo='foto_dano', formato='jpg'`, asociada al ingreso del vehículo dañado via `registro.uuid_ingreso_referencia`. La branch la mantiene localmente; cloud la recibe via sync para auditoría (admin puede revisar luego en caso de reclamo del cliente). El flujo toca 7 tablas: `documentos` (W), `ingreso` (R referencia), `permisos_usuario` (R RBAC), `usuarios_sucursal` (R tenant scope), `log_transaccional` (W), `sync_queue` (W), `clientes` (R opcional si se vincula el cliente).

**Actor**: operator

**Pre-conditions**: branch is paired and operational; operator's `permisos_usuario` includes `permiso='subir_documentos_operativos'`; an `ingreso` row exists for the vehicle in question (the operator references it from the IngresoForm detail view); JPG file ready (≤10 MB).

**Steps**:
1. Operator opens `web_sucursal/IngresoDetail/{uuid_ingreso}`, clicks `Upload Damage Photo`.
2. Frontend shows `DocumentUploadForm` pre-filled: `uuid_sucursal` from JWT (not editable), `tipo='foto_dano'` selected, file input (JPG/PNG).
3. Operator selects JPG file. Frontend reads as base64, computes SHA256.
4. Operator optionally selects the related `cliente` from a dropdown (if known) — this goes into `registro.uuid_cliente_referencia` for later cross-reference.
5. Frontend POSTs `api_sucursal /documentos/{uuid_placeholder_optional}/upload` with `{tipo:'foto_dano', formato:'jpg', documento_b64:<b64>, registro:{uuid_ingreso_referencia:$ingreso_uuid, uuid_cliente_referencia:$cliente_uuid_or_null, fecha_evento:NOW(), sha256:<hash>, file_size_bytes:$X, observaciones:'golpe_lateral_izquierdo'}}`.
6. Backend verifies operator JWT: SELECTs `permisos_usuario` for `permiso='subir_documentos_operativos'`; rejects 403 if missing.
7. Backend validates tenant scope: `permisos_usuario` AND `usuarios_sucursal` rows confirm operator belongs to `uuid_sucursal=$JWT_branch`.
8. Backend validates file: size ≤ 10 MB, MIME matches `formato='jpg'`, SHA256 recomputed matches.
9. Backend SELECTs `ingreso` WHERE `uuid=$ingreso_uuid AND uuid_sucursal=$JWT_branch` (cross-tenant protection). Rejects 404 if not found in own branch.
10. Backend opens TX; SELECT chain anchor from `log_transaccional`.
11. Backend INSERTs `documentos` row (new version, since this is the first damage photo for this ingreso — `tipo='foto_dano' AND uuid_sucursal=$branch AND registro->>'uuid_ingreso_referencia'=$ingreso_uuid` would be the query to find existing; if found, archives old version).
12. Backend INSERTs `log_transaccional` (`accion='documento_subido_operativo'`, `tabla_afectada='documentos'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_anteriores=null`, `datos_nuevos={...snapshot, uuid_ingreso_referencia, uuid_cliente_referencia, observaciones}`, `uuid_referencia=$ingreso_uuid`).
13. `queue_processor.enqueue('documentos', $new_uuid, $snapshot)` → INSERT `sync_queue` row.
14. Backend returns `{uuid, sha256, file_size, uploaded_at}` to frontend.
15. Operator UI shows the photo thumbnail on the IngresoDetail view; `IngresoDetail` now shows "1 damage photo" badge.
16. When branch syncs, the row + log push to cloud. Cloud receives; INSERTs both rows (idempotent by UUID); cloud chain extends by 1 row.
17. Cloud admin in `web_admin/IngresoDetail/{uuid}` (cross-branch view) sees the damage photo with a "View" button — read-only.

**Tables touched (writes)**: `documentos` (1 row), `log_transaccional` (1 branch + 1 cloud when received), `sync_queue` (1 row).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `usuarios_sucursal` (tenant scope), `ingreso` (cross-reference validation), `clientes` (optional linkage), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator actor).
**FKs traversed**: `documentos.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `ingreso.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`; `usuarios_sucursal.uuid_usuario` → `usuarios.uuid` + `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `documentos` row + `log_transaccional` row push via `sync_queue` within 30s of upload.
- Cloud → branch: NO (no parametrization impact; cloud only receives the operator's upload).
- DIAN trigger: NO (operational document, not fiscal).
- Hash chain impact: YES — branch chain extends by 1 row on upload; cloud chain extends by 1 row when received via sync.

**Integration with other tables**:
- Reads from: `permisos_usuario` (RBAC), `usuarios_sucursal` (tenant scope), `ingreso` (cross-reference), `clientes` (optional linkage), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator).
- Writes to: `documentos` (new version with ingreso cross-ref), `log_transaccional` (audit), `sync_queue` (deferred propagation).
- Cross-cutting: the `registro.uuid_ingreso_referencia` enables a future flow where, if the cliente files a `reclamos tipo_reclamable='ingreso'`, the admin can pull up the damage photo evidence in `web_admin/ReclamoDetail/Evidencia`. This is the link between operational documents and the customer claims workflow.
- Related: if multiple damage photos are uploaded for the same `ingreso`, each is a separate `documentos` row (new version), all referencing the same `registro.uuid_ingreso_referencia`. The vigentes set shows the latest per upload moment.

### 7.3 Use Case: `uc.documentos.expiry-monitor-emits-alert-30-days-before`

Worker cron `expiry_monitor` corre diariamente en cloud. Escanea todos los `documentos` vigentes con `registro.fecha_vencimiento` populated. Para cada documento con `fecha_vencimiento - NOW() <= 30 days AND > 7 days`: emite `alerta tipo_alerta='documento_por_vencer'` (warning, amarillo). Para cada documento con `fecha_vencimiento <= NOW() + 7 days AND > NOW()`: emite `alerta tipo_alerta='documento_por_vencer_critico'` (critical, naranja). Para cada documento con `fecha_vencimiento < NOW()`: emite `alerta tipo_alerta='documento_vencido'` (red, blocks operations). El admin ve las alertas en `web_admin/AlertasList` y debe subir la versión renovada (use case 7.1). El flujo toca 5 tablas: `documentos` (R scan), `alerta` (W workflow root), `log_transaccional` (W), `sync_log` (W ciclo del monitor), `sucursal` (R tenant).

**Actor**: system (cloud `expiry_monitor` cron worker)

**Pre-conditions**: cloud has at least one `documentos` row with `registro.fecha_vencimiento` populated (set during admin upload in 7.1 or operator upload in 7.2); cron is enabled (daily at 02:00 cloud time); `alerta` workflow chain is functional.

**Steps**:
1. `expiry_monitor` cron fires daily at 02:00 cloud time. SELECTs `documentos` WHERE `vigente_hasta IS NULL AND estado='activo' AND registro->>'fecha_vencimiento' IS NOT NULL`.
2. For each row, computes `days_until_expiry = (registro.fecha_vencimiento::date - CURRENT_DATE)`.
3. Three buckets:
   - **Critical (≤7 days)**: `days_until_expiry <= 7 AND > 0` → INSERTs `alerta` `tipo_alerta='documento_por_vencer_critico'`, `estado='abierta'`, `uuid_sucursal=$branch`, `observaciones='vencimiento_en_${days_until_expiry}_dias, tipo:${tipo}, uuid_doc:${uuid}'`.
   - **Warning (≤30 days, >7 days)**: `days_until_expiry <= 30 AND > 7` → INSERTs `alerta` `tipo_alerta='documento_por_vencer'`, `estado='abierta'`, similar observations.
   - **Expired (<0 days)**: `days_until_expiry < 0` → INSERTs `alerta` `tipo_alerta='documento_vencido'`, `estado='abierta'`, `observaciones='vencido_hace_${-days}_dias'`. CRITICAL: branches with `documento_vencido` for `tipo='licencia_comercial'` are flagged as "regulatory_non_compliant" — may block `ingreso` operations via config gate (sprint 5 feature, not MVP).
4. Before INSERTing `alerta`, the worker checks for existing open `alerta` of the same `tipo_alerta` for the same `documentos.uuid` to avoid duplicate alerts (deduplication). Only INSERTs if no open alerta exists.
5. For each `alerta` INSERTed: INSERT `log_transaccional` (`accion='expiry_alert_emitted'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alert.uuid`, `uuid_usuario=SYSTEM`, `uuid_sucursal=$branch`, `datos_nuevos={documento_uuid, days_until_expiry, alert_type}`).
6. After all alerts: INSERT `sync_log` (`operaciones_enviadas=$alert_count, exitosas=$alert_count, fallidas=0, duracion_ms=$X`).
7. Admin sees the alerts in `web_admin/AlertasList` (red for expired, orange for critical, yellow for warning).
8. Admin clicks on a `documento_por_vencer` alerta → opens `DocumentosDetail/{uuid}` → reviews current version → uploads new version (per use case 7.1).
9. After upload, the new `documentos` version has `vigente_desde=NOW(), vigente_hasta=NULL`; the old version is archived. The `expiry_monitor` next run will see the new vigente version with its own (later) `fecha_vencimiento`.
10. Admin may also resolve the alert manually: workflow chain transition `en_revision → resuelta` with `observaciones='documento_renovado_<uuid>'`.
11. The `alerta` workflow chain emits 1-3 `log_transaccional` rows total (root + transitions).

**Tables touched (writes)**: `alerta` (1 root per affected documento + 2-3 transitions), `log_transaccional` (1 per alert + 2-3 per transitions), `sync_log` (1 monitor cycle).
**Tables touched (reads)**: `documentos` (scan vigente with expiry), `alerta` (dedup check), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (SYSTEM lookup).
**FKs traversed**: `documentos.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` (assigned during en_revision) → `usuarios.uuid`; `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference); `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_referencia` (polymorphic) → `documentos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (the monitor runs cloud-side).
- Cloud → branch: NO (alerts are operational; branch sees the renewal notification only when the new `documentos` version arrives via parametrization push).
- DIAN trigger: NO (operational alert, not fiscal).
- Hash chain impact: YES — cloud chain extends by 1 row per alert (expiry_alert_emitted) plus 1-3 rows per alert workflow transitions.

**Integration with other tables**:
- Reads from: `documentos` (scan + vigente filter), `alerta` (dedup check), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (SYSTEM).
- Writes to: `alerta` (workflow root + transitions), `log_transaccional` (audit + per-transition), `sync_log` (monitor cycle).
- Cross-cutting: this is the **regulatory compliance enforcer**. The `expiry_monitor` ensures that licenses and permits don't silently expire — a missing renewal would result in `documento_vencido` alerts that flag the branch as non-compliant. The admin is responsible for uploading renewed documents in time.
- Related: `documento_vencido` alerts could integrate with `configuracion_seguridad` for "regulatory_compliance_required" — branches with expired commercial licenses could have `ingreso` operations blocked at the application level (deferred to sprint 5).
- Dedup strategy: only one open `alerta` per `(tipo_alerta, uuid_documento)` pair. If admin manually closes one and the condition persists (e.g., doesn't upload the renewal), the next monitor run will create a new `alerta` with `uuid_alerta_padre` pointing to the previous closed one.

### 7.4 Use Case: `uc.documentos.cloud-admin-bi-temporal-audit-retrieval`

Admin cloud (con `permiso='auditar_documentos'` o `rol_admin_auditor` con BYPASSRLS) investiga un reclamo de un cliente o una auditoría regulatoria. Necesita ver TODAS las versiones históricas de un documento (cuál era la licencia vigente en la fecha X, cuándo se renovó, qué decía la versión anterior). Usa la query bi-temporal: SELECTs todas las filas de `documentos` WHERE `uuid_sucursal=$branch AND tipo=$tipo AND vigente_desde <= $as_of_date AND (vigente_hasta IS NULL OR vigente_hasta > $as_of_date)`. El resultado muestra la versión que estaba activa en esa fecha, no la actual. El flujo toca 4 tablas en lectura + 1 en escritura opcional (`alerta` si la auditoría revela problemas).

**Actor**: admin (or admin_auditor)

**Pre-conditions**: cloud has the `documentos` rows (received via parametrization or written by admin); the admin has appropriate permissions; a regulatory or customer audit is in progress.

**Steps**:
1. Admin opens `web_admin/AuditDashboard/DocumentosAudit`, fills filters: `uuid_sucursal=$branch (optional, blank = all)`, `tipo=$tipo_doc`, `as_of_date=$target_date` (the date to reconstruct state for).
2. Frontend GETs `api_admin /documentos/audit?tipo=$tipo_doc&uuid_sucursal=$branch&as_of_date=$target_date` (admin- JWT).
3. Backend validates: `permisos_usuario` for `permiso='auditar_documentos'` OR rol_admin_auditor.
4. Backend SELECTs `documentos` WHERE `tipo=$tipo_doc AND ($uuid_sucursal IS NULL OR uuid_sucursal=$uuid_sucursal) AND vigente_desde <= $as_of_date AND (vigente_hasta IS NULL OR vigente_hasta > $as_of_date)`. Returns the vigentes set at `$as_of_date`.
5. Backend also SELECTs `log_transaccional` rows WHERE `tabla_afectada='documentos' AND uuid_registro_afectado IN ($vigente_uuids) AND timestamp_evento <= $as_of_date`. Returns the full audit trail for those documents up to the as-of date.
6. Backend returns `{documentos_vigentes: [...], log_transaccional_audit: [...]}` to frontend.
7. Admin UI shows: the document(s) active at that date with their SHA256 hashes and metadata; the upload history showing who uploaded what when. Admin can download the base64 content via `GET /documentos/{uuid}/download`.
8. If the admin finds a regulatory issue (e.g., the license was expired at the audit date but no `alerta` was emitted — gap in monitoring): admin can manually file an `alerta tipo_alerta='audit_finding'` with the relevant `uuid_referencia=$documento_uuid` and `observaciones=$finding_text`.
9. The `alerta` workflow chain emits 1+ `log_transaccional` rows.
10. The audit findings may also trigger retroactive updates to `expiry_monitor` configuration (e.g., shorten the warning window from 30 to 60 days if past alerts were too late).

**Tables touched (writes)**: optional `alerta` (if audit finds issues) + 1+ `log_transaccional`.
**Tables touched (reads)**: `documentos` (bi-temporal query), `log_transaccional` (audit trail), `permisos_usuario` (RBAC), `sucursal` (tenant), `usuarios` (admin actor).
**FKs traversed**: `documentos.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_referencia` (polymorphic) → `documentos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (the audit is a cloud-side read).
- Cloud → branch: NO (audit is read-only; no parametrization impact).
- DIAN trigger: NO (audit query is operational, not fiscal).
- Hash chain impact: NO for the read itself (per SOLID I, reads don't extend the chain). If the audit triggers an `alerta`, that DOES extend the chain.

**Integration with other tables**:
- Reads from: `documentos` (bi-temporal vigente query), `log_transaccional` (audit trail), `permisos_usuario` (RBAC), `sucursal` (tenant), `usuarios` (admin).
- Writes to: optional `alerta` (audit findings), `log_transaccional` (audit action audit if alert is filed).
- Cross-cutting: this is the **bi-temporal audit pattern** — the `[V]` versioning is meaningless without a way to query historical state. The audit retrieval is the read-side counterpart to the version-flow write-side. Together they form the "complete audit" capability required by regulatory compliance.
- Related: if `rol_admin_auditor` (BYPASSRLS) is used, the SELECT bypasses RLS but still respects the REVOKE on `rol_app` (so the auditor cannot UPDATE/DELETE `documentos` — only SELECT). The audit row in `log_transaccional` records the auditor's actions only when they mutate state (filing an `alerta`).

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 17, 24, 28, 31.

## 9. RED Tests
- (RED) F1 schema includes `documentos` table; F1 onboarding seed inserts placeholder row (`tipo='licencia_comercial', documento_b64=NULL`).
- (RED) Admin POST `/documentos` with valid PDF → 201; new row inserted; old vigente row updated to `vigente_hasta=NOW()`.
- (RED) Admin POST with file >10 MB → 413 Payload Too Large.
- (RED) Admin POST with mismatched SHA256 → 422 with `HASH_MISMATCH`.
- (RED) Admin POST without `permiso='subir_documentos_regulatorios'` → 403.
- (RED) Operator POST `/documentos/{uuid_placeholder}/upload` with `permiso='subir_documentos_operativos'` → 201; new version inserted.
- (RED) Operator without permission → 403.
- (RED) Operator from branch A uploading to branch B's placeholder → 403 (tenant scope enforced via `usuarios_sucursal`).
- (RED) Bi-temporal audit query: `GET /documentos/audit?tipo=licencia_comercial&as_of_date=2026-06-01` returns the vigente row at that date, NOT the current row.
- (RED) Expiry monitor: insert `documentos` with `registro.fecha_vencimiento=NOW() + 5 days` → next cron run emits `alerta tipo_alerta='documento_por_vencer_critico'`.
- (RED) Expiry monitor: insert with `fecha_vencimiento=NOW() - 1 day` → emits `documento_vencido` (red).
- (RED) Expiry monitor dedup: existing open alerta for same `(tipo_alerta, uuid_documento)` → no duplicate emitted.
- (RED) Version history preserved: after 3 uploads of the same `tipo` to the same branch, `GET /documentos/{uuid}/versions` returns all 3 rows.
- (RED) ON DELETE RESTRICT: cannot `DELETE FROM documentos WHERE uuid=?` (REVOKE on rol_app + trigger raises AUDIT_FIRST_INMUTABLE).
- (RED) FK RESTRICT: cannot `DELETE FROM sucursal WHERE uuid=?` while `documentos` references it.

## 10. Implementation Tasks
- [x] F1.x Schema.
- [ ] IT-2.x: `api_admin /documentos` (POST, PATCH, GET list, GET detail, GET audit, GET versions).
- [ ] IT-2.x: `api_sucursal /documentos/{uuid}/upload` (operator with permission).
- [ ] IT-2.x: `parkos_core/documentos/version_service.py` (versioning logic).
- [ ] IT-2.x: `parkos_core/documentos/expiry_monitor.py` (cron worker, daily 02:00 cloud).
- [ ] Sprint 5: add `registro` JSON column to `documentos` for expiry/resolution metadata (current: documented in use case 7.3, schema extension required).
- [ ] IT-2.x: parametrization push for `documentos` updates to branches.
- [ ] IT-2.x: `web_admin/DocumentosList`, `DocumentosForm`, `DocumentosDetail/VersionHistory`, `AuditDashboard/DocumentosAudit`.
- [ ] IT-2.x: `web_sucursal/DocumentosTab`, `DocumentUploadForm`.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Large file storage | Med | 10 MB cap; >10 MB → S3-compatible storage (sprint 5 deferred) |
| Binary corruption | Low | SHA256 verified at upload; mismatch → 422; integrity check at read |
| Version explosion (upload spam) | Low | UI confirms "Replace existing version?"; old version archived but visible in history |
| Expiry alert missed (cron failure) | Low | Cron monitored by `workers/cron_health`; missed run → alert; dedup prevents re-emission |
| Operator uploads wrong document type | Med | UI dropdown for `tipo`; rejection if mis-categorized; admin can re-categorize later |
| `registro` JSON schema drift | Low | `config_validator` for `registro` (sprint 5); required keys per `tipo` |
| Tenant scope leak (operator sees other branch docs) | Low | `usuarios_sucursal` enforcement + JWT scope; cross-tenant upload rejected |
| Auditor with BYPASSRLS modifies state | Low | REVOKE on `rol_app` still applies; BYPASSRLS bypasses RLS not REVOKE |

## 12. Open Questions
- (a) `registro` JSON column for `documentos`: sprint 5 migration to add; current model lacks it. Use case 7.3 documents the design assuming the column exists.
- (b) S3-compatible storage for files >10 MB: deferred; need to decide S3 vs MinIO vs local file system.
- (c) `documento_vencido` enforcement: should expired licenses BLOCK `ingreso` operations? Currently alert-only; sprint 5 may add hard block via `configuracion_seguridad` flag.
- (d) Expiry warning window: 30 days is current default; configurable per `tipo` (e.g., `licencia_comercial` may need 90 days warning)?
- (e) Auto-resolve `alerta` when new version uploaded: should the workflow chain auto-transition to `resuelta` on parametrization push? Currently manual; sprint 5 may automate.
- (f) Operator upload audit trail visibility: should operators see WHO uploaded a damage photo, or is it admin-only? Currently both can see; may want to hide operator PII from cross-branch views.
- (g) Bi-temporal query indexing: `vigente_desde..vigente_hasta` range query on `documentos` may be slow for large datasets; consider GiST index or materialized view.
