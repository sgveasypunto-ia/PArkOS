# PRD: clientes (T16)

> Customers of the parking system: **B2C natural** (individuals with subscriptions), **B2B juridica** (corporate clients with contracts), and **consumidor_final** (anonymous cash sales default). The `clientes` row is the FK anchor for `subscripciones_cliente`, `factura_electronica` (as titular), and `clientes_b2b` (1:1 extension for B2B contracts). The subscriber arrival lookup by `numero_identificacion` (cedula) is **the heart of the operation flow**.

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
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule I: lookup-by-cedula API is segregated from admin CRUD*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.clientes`
- **SQL name**: `clientes` (with `prod` schema)
- **Enforcement level**: `[V]` projection
- **Retention**: indefinite (legal customer record)
- **Origin**: F1 (schema + seed `consumidor_final_default` UUID) + IT-10 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 3.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; the operation-heart lookup-by-cedula flow documented end-to-end)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated.
- `numero_identificacion` is natural key (cedula for natural, NIT for juridica) — UNIQUE per `uuid_tipo_persona` (enforced via composite UNIQUE constraint `(numero_identificacion, uuid_tipo_persona)`).
- `tipo_identificador` is a free-form string with business-level enum: `'cedula'`, `'nit'`, `'pasaporte'`, `'consumidor_final'` (for the seed default).
- `registro` is JSON — extensible per-client metadata (e.g., direccion, contacto_emergencia, observaciones).
- **F1 seed**: a fixed UUID `consumidor_final_default` row is inserted with `uuid_tipo_persona='consumidor_final'`, `numero_identificacion='222222222222'` (placeholder). All `factura_electronica` rows for cash sales without a registered cliente reference this seed.

## 3. SOLID Atomic Breakdown
- **S**: "one customer" (natural persona, juridica empresa, or consumidor final). The B2B nature is determined by the presence of a row in `clientes_b2b` (1:1 extension).
- **O**: `registro` JSON is the extension point for per-customer metadata. New columns (e.g., `direccion_facturacion`) don't require schema migration.
- **I**: admin CRUD via `api_admin /clientes`; branch reads own + cross-branch lookup via `api_sucursal /clientes?numero_identificacion=...` (the operation lookup); auditor reads via `rol_admin_auditor`.
- **D**: `parkos_core/models/V/clientes.py` (model); `parkos_core/clientes/lookup_service.py` (cedula-based lookup with subscription JOIN); `workers/clientes/expiry_monitor.py` (cron — flags subscriptions with expired B2B `fecha_vencimiento`).
- **Atomic**: INSERT (admin creates), UPDATE (creates new version, archive old — every change emits `log_transaccional`), DELETE forbidden by FK RESTRICT (subscripciones_cliente references).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| `uuid_tipo_persona` | `prod.tipo_persona.uuid` | exactly one (NOT NULL) | RESTRICT | 'natural' / 'juridica' / 'consumidor_final' |

### Incoming FKs
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| `clientes_b2b.uuid_cliente` | `\|\|--o\|` | 0..1 (B2B extension optional) |
| `subscripciones_cliente.uuid_cliente` | `\|\|--o{` | customer subscriptions (per branch) |
| `factura_electronica.uuid_cliente` | `\|\|--o{` | titular of e-factura (cloud-side; via SyncBackEvent on receipt) |
| `reclamos` (polymorphic, future) | — | FK polimórfica `tipo_reclamable` is currently limited to `{ingreso, salida, factura, subscripcion}` per the model — `cliente` is NOT a valid `tipo_reclamable`. Reclamos against the customer as a whole use `tipo_reclamable='subscripcion'` referencing their subscription. See open question (f). |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Admin via `api_admin /clientes` (B2C natural + B2B juridica); seed consumidor_final_default in F1 |
| UPDATE | YES (archive only) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted. NEVER modify `numero_identificacion` of existing version — preserves audit of identity changes |
| DELETE | NO | Archive; FK RESTRICT (subscripciones reference this) |

**Special rules**:
- **F1 seed**: `consumidor_final_default` UUID is fixed (deterministic, documented in F1 migration). Used as FK target for all cash sales without a registered cliente.
- **Composite UNIQUE**: `(numero_identificacion, uuid_tipo_persona)` — same cedula can exist for natural and juridica (different tipo_persona = different row). But same NIT for two juridicas is rejected.
- The lookup-by-cedula query is the **most-frequent** read in the system (every subscriber arrival). Indexed on `(numero_identificacion, uuid_tipo_persona)` for fast lookup.
- GDPR-like deletion: per `registro.pseudonymize=true` (sprint 5 JSON flag), admin can update `nombre='PSEUDONYMIZED_$uuid_short'` and `email=null` while preserving `numero_identificacion` and FK integrity. Out of MVP; sprint 5.

## 6. CodeGraph Dependencies
- `api_admin/routers/clientes.py::POST /clientes`, `PATCH /clientes/{uuid}`, `GET /clientes`, `GET /clientes/{uuid}`.
- `api_sucursal/routers/clientes.py::GET /clientes?numero_identificacion=...` (the lookup-by-cedula — heart of operation flow).
- `api_sucursal/routers/clientes.py::GET /clientes/{uuid}/subscripciones` (joined: cliente + active subscriptions + vehicles).
- `parkos_core/clientes/lookup_service.py::find_by_cedula(cedula)` (returns cliente + active subs + vehiculos).
- `workers/clientes/expiry_monitor.py` (cron, daily 03:00 cloud; flags subscriptions tied to expired B2B contracts).
- `web_admin/ClientesList`, `ClienteForm`, `ClientesDetail/SubscripcionesTab`.
- `web_sucursal/ClienteLookup` (the lookup-by-cedula UI component, embedded in `IngresoForm`).

## 7. Use Cases enabled by this table

The `clientes` table is the **anchor for the subscriber operation flow**: when a customer arrives with a subscription, the operator types the cedula, the system finds the cliente + active subscription + vehicles, and the operator picks the right vehicle for the ingreso. Use cases below describe this canonical lookup, the B2C/B2B creation flows, the B2B lifecycle enforcement, the consumidor_final default, and the polymorphic-FK constraint in `reclamos`.

### 7.1 Use Case: `uc.clientes.subscriber-arrival-lookup-by-cedula`

Llega un suscriptor al parqueadero. El operador NO escanea QR (el sistema no tiene scanner) — pregunta la cédula, la tipea, y el sistema le muestra el cliente + subscripciones activas + vehículos para que el operador elija el correcto. El flujo toca 6 tablas: `clientes` (R), `subscripciones_cliente` (R activas), `subscripcion_vehiculos` (R JOIN), `vehiculos` (R), `tipos_vehiculo` (R JOIN), `usuarios_sucursal` (R JWT scope). **Es el heart del operation flow** — el use case más frecuente del sistema.

**Actor**: operator

**Pre-conditions**: subscriber is registered in `clientes`; has at least one active `subscripciones_cliente` at the current branch; has at least one `vehiculos` linked via `subscripcion_vehiculos`; branch is paired and operational.

**Steps**:
1. Vehicle arrives at the booth. Subscriber says "Tengo suscripción". Operator opens `web_sucursal/IngresoForm`, clicks `Cliente con subscripción`.
2. Frontend shows `ClienteLookup` component (cedula input).
3. Operator **types the cedula** of the customer (e.g., `1234567890`) — manual input, no scanner.
4. Frontend GETs `api_sucursal /clientes?numero_identificacion=1234567890&uuid_tipo_persona=natural` (own branch scoped via JWT).
5. Backend SELECTs `clientes` WHERE `numero_identificacion='1234567890' AND uuid_tipo_persona=(SELECT uuid FROM tipo_persona WHERE tipo='natural')`. Returns 1 row: `{uuid, nombre, apellido, telefono, email, uuid_tipo_persona}`.
6. If no match: frontend shows "Cliente no encontrado — verifique la cédula o cree nuevo cliente (admin only)". Operator may ask the customer to confirm cedula, or escalate to admin.
7. If match found: Frontend GETs `api_sucursal /clientes/{uuid}/subscripciones?estado=activa&uuid_sucursal=$JWT_branch`.
8. Backend SELECTs `subscripciones_cliente` WHERE `uuid_cliente=$cliente_uuid AND uuid_sucursal=$branch AND estado='activa' AND vigente_desde<=NOW() AND (vigente_hasta IS NULL OR vigente_hasta>NOW()) AND fecha_vencimiento>=CURRENT_DATE`. Returns 1+ rows (subscriber may have multiple subscriptions at different branches or plans).
9. Frontend GETs `api_sucursal /subscripciones-cliente/{uuid}/vehiculos` for each active subscription.
10. Backend SELECTs `subscripcion_vehiculos sv JOIN vehiculos v ON sv.uuid_vehiculo=v.uuid JOIN tipos_vehiculo tv ON v.uuid_tipo_vehiculo=tv.uuid WHERE sv.uuid_subscripcion_cliente=$sub_uuid AND sv.vigente_hasta IS NULL`. Returns the vehicles in the subscription.
11. Frontend shows: "Cliente: Juan Pérez. Subscripciones activas: 1. Vehículos: ABC123 (auto), DEF456 (auto). Seleccione el vehículo que llega:".
12. Operator **selects** the vehicle that just arrived (e.g., `ABC123`).
13. Frontend POSTs `api_sucursal /ingresos` with `{placa: 'ABC123', uuid_tipo_vehiculo: $auto_uuid, uuid_subscripcion_cliente: $sub_uuid}`. Backend creates `ingreso` linked to the subscription.
14. (No `log_transaccional` write for the lookup itself — per SOLID I, reads don't extend the chain. The ingreso creation writes the log row.)

**Tables touched (writes)**: NONE for the lookup. The subsequent `ingreso` creation writes `ingreso + log_transaccional + sync_queue` (per `uc.ingreso.subscriber-lookup-by-cedula`).
**Tables touched (reads)**: `clientes` (lookup), `subscripciones_cliente` (active filter), `subscripcion_vehiculos` (JOIN), `vehiculos` (JOIN), `tipos_vehiculo` (catalog JOIN), `tipo_persona` (catalog for natural lookup), `usuarios_sucursal` (JWT scope), `sucursal` (tenant).
**FKs traversed**: `clientes.uuid_tipo_persona` → `tipo_persona.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `subscripcion_vehiculos.uuid_subscripcion_cliente` → `subscripciones_cliente.uuid`; `subscripcion_vehiculos.uuid_vehiculo` → `vehiculos.uuid`; `vehiculos.uuid_tipo_vehiculo` → `tipos_vehiculo.uuid`; `usuarios_sucursal.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (the lookup is read-only; the subsequent ingreso is per `uc.ingreso.*`).
- Cloud → branch: YES — parametrization push delivers any updates to `clientes` (e.g., new email, new phone) within 30s.
- DIAN trigger: NO (lookup is operational).
- Hash chain impact: **NO** for the lookup itself (per SOLID I, reads don't extend the chain). The subsequent ingreso creation does extend the chain.

**Integration with other tables**:
- Reads from: `clientes` (lookup), `subscripciones_cliente` (active filter), `subscripcion_vehiculos` (JOIN), `vehiculos`, `tipos_vehiculo`, `tipo_persona`, `usuarios_sucursal`, `sucursal`.
- Writes to: NONE for the lookup.
- Cross-cutting: this is the **canonical subscriber arrival pattern**. The 3-step GET chain (cliente → subscripcion → vehiculos) is the most-frequent read in the system. Performance optimization: cache `lookup_service.find_by_cedula(cedula)` result in Redis for 5 minutes (sprint 5 — current is direct DB query, ~50ms per lookup which is acceptable for operator UI).
- Related: if the subscriber has no active subscription at the current branch (but has one at another branch), the lookup returns 0 subs. Operator must proceed as casual. The system does NOT auto-create cross-branch subscription (subscription is branch-pinned per business model).

### 7.2 Use Case: `uc.clientes.admin-creates-b2c-natural`

Admin cloud crea un cliente B2C (persona natural con cédula). El cliente se inserta con `uuid_tipo_persona='natural'`, `numero_identificacion=cedula`, datos básicos, y parametrización push lo entrega a las branches. El flujo toca 6 tablas: `clientes` (W), `tipo_persona` (R catalog), `permisos_usuario` (R RBAC), `usuarios` (R admin actor), `log_transaccional` (W), `sync_queue` (W parametrización).

**Actor**: admin

**Pre-conditions**: admin has `permiso='crear_clientes'`; `tipo_persona='natural'` exists in catalog (seeded in F1); no existing `clientes` row with same `(numero_identificacion, uuid_tipo_persona='natural')`.

**Steps**:
1. Admin opens `web_admin/ClientesList → ClientesForm`, selects `tipo_persona='natural'`.
2. Fills `tipo_identificador='cedula'`, `numero_identificacion='1234567890'`, `nombre='Juan'`, `apellido='Pérez'`, `telefono='+57-301-555-1234'`, `email='juan.perez@example.com'`, `registro={direccion:'Calle 123 #45-67', contacto_emergencia:'Maria Pérez +57-301-555-5678'}`.
3. Frontend POSTs `api_admin /clientes` (admin- JWT).
4. Backend validates `permisos_usuario` for `permiso='crear_clientes'`. Rejects 403 if missing.
5. Backend SELECTs `tipo_persona` WHERE `tipo='natural'`. Returns UUID.
6. Backend SELECTs `clientes` WHERE `numero_identificacion='1234567890' AND uuid_tipo_persona=$natural_uuid`. If exists: 409 conflict.
7. Backend opens TX; SELECT chain anchor from `log_transaccional` for the admin's branch (or cloud sentinel — see open question).
8. Backend INSERTs `clientes` row (`vigente_desde=NOW(), vigente_hasta=NULL, estado='activo'`).
9. Backend INSERTs `log_transaccional` (`accion='cliente_creado'`, `tabla_afectada='clientes'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `datos_anteriores=null`, `datos_nuevos={...snapshot, tipo_persona: 'natural'}`).
10. `queue_processor.enqueue('clientes', $new_uuid, $snapshot)` → INSERT `sync_queue` row.
11. Backend returns `{uuid, vigente_desde}` to frontend.
12. All branches receive parametrization within 30s. UPSERTs the new `clientes` row locally (idempotent by UUID).
13. Branch operator in `web_sucursal/ClienteLookup` can now find this customer by cedula.

**Tables touched (writes)**: `clientes` (1 row), `log_transaccional` (1 row), `sync_queue` (1 row).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `tipo_persona` (catalog), `clientes` (UNIQUE check), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `clientes.uuid_tipo_persona` → `tipo_persona.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `clientes.uuid`; `sync_queue.uuid_sucursal` → `sucursal.uuid`; `permisos_usuario.uuid_usuario` → `usuarios.uuid` + `permisos_usuario.uuid_permiso` → `permisos.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write happens in cloud).
- Cloud → branch: YES — parametrization push delivers the new cliente to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (cliente_creado); each branch chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `tipo_persona` (catalog), `clientes` (UNIQUE check), `log_transaccional`, `usuarios`.
- Writes to: `clientes` (new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: this is the **customer onboarding flow**. Each new B2C cliente is a potential subscription holder; the admin typically also creates a `subscripciones_cliente` for them in the same workflow (per `uc.subscripciones.admin-create`).
- Related: if admin tries to UPDATE `numero_identificacion` (e.g., correction from `1234567890` to `1234567891` due to data entry error), the version flow preserves the OLD cedula as a previous row. Future lookups by OLD cedula return the cliente with a note that the current `numero_identificacion` is different (the UI may show "Cliente Juan Pérez — cedula updated from 1234567890 to 1234567891 on $date").

### 7.3 Use Case: `uc.clientes.admin-creates-b2b-with-extension`

Admin cloud crea un cliente B2B (persona jurídica con NIT) + la extensión `clientes_b2b` con `cantidad` (cupo de vehículos en el contrato corporativo), `fecha_vencimiento` (vencimiento del contrato), y `registro` (condiciones contractuales). Las dos escrituras van en la misma TX para garantizar atomicidad. El flujo toca 7 tablas: `clientes` (W), `clientes_b2b` (W extension), `tipo_persona` (R), `permisos_usuario` (R), `usuarios` (R), `log_transaccional` (W x 2), `sync_queue` (W parametrización).

**Actor**: admin

**Pre-conditions**: admin has `permiso='crear_clientes'` AND `permiso='crear_contratos_b2b'`; `tipo_persona='juridica'` exists; no existing cliente with same `(numero_identificacion=NIT, uuid_tipo_persona='juridica')`.

**Steps**:
1. Admin opens `web_admin/ClientesForm`, selects `tipo_persona='juridica'`.
2. Fills B2C-like fields: `tipo_identificador='nit'`, `numero_identificacion='900123456-7'`, `nombre='Empresa XYZ S.A.S.'`, `telefono='+57-1-555-1234'`, `email='facturacion@xyz.com'`, `registro={direccion:'Cra 7 #123-45', ciudad:'Bogotá'}`.
3. Fills B2B extension fields: `cantidad=50` (vehículos autorizados en el contrato), `fecha_vencimiento='2027-12-31'`, `registro_b2b={direccion_facturacion:'...', condiciones_pago:'30_dias', contacto_comercial:'...', observaciones:'Contrato corporativo anual'}`.
4. Frontend POSTs `api_admin /clientes` with `{...cliente_fields, extension: {cantidad: 50, fecha_vencimiento: '2027-12-31', registro: {...}}}`.
5. Backend validates `permisos_usuario` for both permissions.
6. Backend SELECTs `tipo_persona='juridica'` UUID.
7. Backend SELECTs `clientes` WHERE `numero_identificacion='900123456-7' AND uuid_tipo_persona=$juridica_uuid`. If exists: 409. Also SELECTs `clientes_b2b` WHERE `uuid_cliente IN (existing cliente with same NIT)` — if exists, error (1:1 enforced).
8. Backend opens TX; SELECT chain anchor from `log_transaccional`.
9. Backend INSERTs `clientes` row.
10. Backend INSERTs `clientes_b2b` row with `uuid_cliente=$new_cliente_uuid, cantidad=50, fecha_vencimiento='2027-12-31', registro={...}`. UNIQUE on `uuid_cliente` enforces 1:1.
11. Backend INSERTs 2 `log_transaccional` rows: (a) `accion='cliente_creado'` for the `clientes` row; (b) `accion='cliente_b2b_creado'` for the extension.
12. `queue_processor.enqueue` for both tables → INSERT 2 `sync_queue` rows.
13. Backend returns `{uuid, uuid_extension, vigente_desde}` to frontend.
14. Branches receive parametrization. UPSERTs both rows locally. Now operators can find Empresa XYZ by NIT and see the B2B contract details (cantidad, fecha_vencimiento).

**Tables touched (writes)**: `clientes` (1 row), `clientes_b2b` (1 row), `log_transaccional` (2 rows), `sync_queue` (2 rows).
**Tables touched (reads)**: `permisos_usuario` (RBAC x 2), `tipo_persona` (catalog), `clientes` (UNIQUE check), `clientes_b2b` (UNIQUE check), `log_transaccional` (chain anchor), `usuarios` (admin).
**FKs traversed**: `clientes.uuid_tipo_persona` → `tipo_persona.uuid`; `clientes_b2b.uuid_cliente` → `clientes.uuid` (UNIQUE); `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `clientes.uuid` (one row) and `clientes_b2b.uuid` (other row); `sync_queue.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: NO (admin write).
- Cloud → branch: YES — parametrization push delivers both rows.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 2 rows (cliente_creado + cliente_b2b_creado). Each branch chain extends by 2 rows when received.

**Integration with other tables**:
- Reads from: `permisos_usuario`, `tipo_persona`, `clientes`, `clientes_b2b`, `log_transaccional`, `usuarios`.
- Writes to: `clientes`, `clientes_b2b`, `log_transaccional` (2 rows), `sync_queue` (2 rows).
- Cross-cutting: the B2B creation is the **canonical atomic TX** for this domain — the `clientes` parent and `clientes_b2b` 1:1 extension MUST be created together (FK RESTRICT on the extension means you can't create the extension without the parent, but the application enforces both in same TX for consistency). If the TX rolls back (e.g., admin network drop between the two INSERTs), neither row exists — clean state.
- Related: the `clientes_b2b.cantidad` is the **maximum vehicles allowed under this B2B contract**. When admin creates `subscripciones_cliente` for Empresa XYZ (per `uc.subscripciones.admin-create`), they may reference the B2B contract for bulk conditions (e.g., 50 vehicles at a discounted rate).

### 7.4 Use Case: `uc.clientes.b2b-fecha-vencimiento-enforces-subscription-lifecycle`

Worker cron `clientes/expiry_monitor` corre diariamente en cloud. Para cada `clientes_b2b` con `fecha_vencimiento < NOW()`, marca todas las `subscripciones_cliente` asociadas como `estado='vencida'` (UPDATE version flow) y emite `alerta tipo_alerta='b2b_vencido'` para que el admin renueve el contrato. Si la fecha ya pasó por >30 días, emite `alerta tipo_alerta='b2b_vencido_critico'` (red). El flujo toca 7 tablas: `clientes_b2b` (R scan), `subscripciones_cliente` (W UPDATE para marcar vencida), `alerta` (W workflow root), `log_transaccional` (W), `sync_queue` (W), `clientes` (R JOIN), `sucursal` (R tenant).

**Actor**: system (cloud `clientes/expiry_monitor` cron worker)

**Pre-conditions**: at least one `clientes_b2b` row with `fecha_vencimiento` past; cron is enabled (daily 03:00 cloud).

**Steps**:
1. `expiry_monitor` cron fires daily. SELECTs `clientes_b2b cb JOIN clientes c ON cb.uuid_cliente=c.uuid` WHERE `cb.fecha_vencimiento < CURRENT_DATE AND cb.vigente_hasta IS NULL`.
2. For each expired B2B contract, SELECTs `subscripciones_cliente` WHERE `uuid_cliente=c.uuid AND estado='activa'`.
3. For each active subscription tied to the expired B2B cliente:
   a. UPDATE old version: `vigente_hasta=NOW()` (archive the active version).
   b. INSERT new version: `vigente_desde=NOW(), vigente_hasta=NULL, estado='vencida'`. The subscription is now flagged as expired — operator lookup returns 0 active subs for this cliente at this branch.
   c. INSERT `log_transaccional` (`accion='subscripcion_marcada_vencida'`, `tabla_afectada='subscripciones_cliente'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=SYSTEM`, `datos_anteriores={old_estado: 'activa', old_vigente_hasta: NOW()}`, `datos_nuevos={new_estado: 'vencida', b2b_fecha_vencimiento: $expired_date}`).
   d. `queue_processor.enqueue('subscripciones_cliente', $new_uuid, $snapshot)` → parametrization push.
4. INSERT `alerta tipo_alerta='b2b_vencido'` per expired contract: `uuid_sucursal=$branch_of_first_subscription, observaciones='cliente:$nit, fecha_vencimiento:$date, subscriptions_affected:$count'`.
5. If `fecha_vencimiento < NOW() - 30 days`: escalates to `b2b_vencido_critico` instead.
6. Dedupe check: if open alerta for same `(tipo_alerta, uuid_cliente)` exists, skip.
7. INSERT `log_transaccional` for each alerta emission.
8. INSERT `sync_log` (cycle metrics).
9. Admin sees alerta → contacts the B2B cliente to renew. Admin creates a new `clientes_b2b` version (extending the contract) → next cron run sees the new vigente and emits a workflow transition `resuelta` on the alert.

**Tables touched (writes)**: `subscripciones_cliente` (1 new version per affected sub + 1 archive UPDATE), `alerta` (1 root per expired B2B + 2-3 transitions), `log_transaccional` (multiple: per subscription update + per alerta + workflow transitions), `sync_queue` (1 per subscription update + parametrization), `sync_log` (1 cycle).
**Tables touched (reads)**: `clientes_b2b` (scan), `clientes` (JOIN), `subscripciones_cliente` (filter active), `alerta` (dedup), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (SYSTEM).
**FKs traversed**: `clientes_b2b.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `subscripciones_cliente.uuid_tipo_subscripcion` → `tipo_subscripciones.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid` (SYSTEM); `log_transaccional.uuid_referencia` (polymorphic) → `clientes_b2b.uuid`; `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_referencia` (polymorphic) → `clientes_b2b.uuid`.

**Sync behavior**:
- Branch → cloud: NO (monitor runs cloud-side).
- Cloud → branch: YES — parametrization push delivers the updated `subscripciones_cliente` versions to all affected branches within 30s. Branch UPSERTs; operator lookup reflects the new `estado='vencida'`.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by N rows (one per affected subscription + alerta root + transitions). Branch chains extend by N rows when received.

**Integration with other tables**:
- Reads from: `clientes_b2b` (scan), `clientes`, `subscripciones_cliente` (active filter), `alerta` (dedup), `log_transaccional`, `sucursal`, `usuarios` (SYSTEM).
- Writes to: `subscripciones_cliente` (version flow), `alerta` (workflow root + transitions), `log_transaccional` (multiple), `sync_queue` (parametrization), `sync_log` (cycle).
- Cross-cutting: this is the **B2B lifecycle enforcer**. Without this cron, an expired B2B contract would still allow subscriber ingresos at the contracted price, costing the company money. The cron ensures revenue protection.
- Related: when admin renews the B2B contract (creates a new `clientes_b2b` version extending `fecha_vencimiento`), the cron next run sees the new vigente and DOES NOT auto-reactivate subscriptions. Admin must manually reactivate each subscription via PATCH (per `uc.subscripciones.*`) — this is intentional, as contract renewal may include changed terms (e.g., different `cantidad`).

### 7.5 Use Case: `uc.clientes.consumidor-final-default-facturacion`

Operator emite una factura para un cliente casual que NO quiere dar sus datos (venta rápida de efectivo, sin registro). El operador selecciona `Consumidor Final` en el dropdown de `FacturacionForm`. Frontend usa el UUID seed `consumidor_final_default` para `factura_electronica.uuid_cliente`. NO se crea ningún `clientes` row nuevo — el seed ya existe. El flujo toca 4 tablas: `clientes` (R seed lookup), `factura_electronica` (W), `facturas` (W), `log_transaccional` (W).

**Actor**: operator

**Pre-conditions**: F1 seeded `consumidor_final_default` row; operator is creating a `factura_electronica` via `FacturacionForm`.

**Steps**:
1. Operator completes a sale. In `FacturacionForm/ClienteLookup`, operator clicks `Consumidor Final` (special button next to the search field).
2. Frontend uses the cached `consumidor_final_default` UUID (loaded at app startup from F1 seed). NO backend lookup needed for this UUID.
3. Frontend POSTs `api_sucursal /facturas` with `{..., uuid_cliente: consumidor_final_default, ...}`.
4. Backend SELECTs `clientes` WHERE `uuid=consumidor_final_default` (sanity check). If missing: 500 (seed broken — should never happen post-F1).
5. Backend proceeds with factura creation. The `factura_electronica.uuid_cliente` references the seed.
6. Cloud receives via sync; `factura_electronica.uuid_cliente` is preserved (idempotent by UUID).
7. DIAN receives the factura with `cliente='Consumidor Final'`, `identificacion='222222222222'` (the placeholder).

**Tables touched (writes)**: `facturas`, `factura_detalle`, `factura_pagos`, `factura_impuestos`, `factura_otros_cobros`, `log_transaccional` (per `uc.facturas.*`), `factura_electronica` (cloud-side), `sync_queue`.
**Tables touched (reads)**: `clientes` (seed sanity check), `facturas` + `factura_electronica` + `log_transaccional` + `sucursal` (per the factura flow).
**FKs traversed**: `clientes` (no FK from `clientes` table for this read — just PK lookup); `factura_electronica.uuid_cliente` → `clientes.uuid` (consumidor_final_default); `facturas.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`.

**Sync behavior**:
- Branch → cloud: YES (per the factura flow).
- Cloud → branch: YES (SyncBackEvent with `numero_oficial`).
- DIAN trigger: YES.
- Hash chain impact: YES (per the factura flow).

**Integration with other tables**:
- Reads from: `clientes` (seed sanity check), `facturas` + `factura_electronica` + `log_transaccional` + `sucursal` (per factura flow).
- Writes to: `facturas` + `factura_detalle` + `factura_pagos` + `factura_impuestos` + `factura_otros_cobros` + `log_transaccional` + `factura_electronica` (cloud) + `sync_queue`.
- Cross-cutting: the `consumidor_final_default` is the **designated anonymous customer** for DIAN compliance. Per DIAN rules, every electronic invoice must have a cliente — `consumidor_final` is the catch-all when the real customer doesn't identify.
- Related: if operator wants to register the cliente retroactively (e.g., customer says "actually, here is my cedula"), admin can create a new `clientes` row AND a new `factura_electronica` via `revocacion_factura` (T02) pointing to the new doc with the real cliente. The old factura with `consumidor_final_default` is preserved (audit) but revoked for DIAN.

### 7.6 Use Case: `uc.clientes.polymorphic-fk-constraint-in-reclamos`

Operator o admin crea un `reclamos` referring to a customer complaint. La `reclamos.uuid_reclamable + tipo_reclamable` es una FK polimórfica. **Constraint del modelo actual**: `tipo_reclamable ∈ {ingreso, salida, factura, subscripcion}`. NO incluye `cliente` directamente. Esto significa que un reclamo sobre el comportamiento general del cliente (no atado a un evento específico) debe usar `tipo_reclamable='subscripcion'` referenciando una subscripción del cliente. Este use case documenta el constraint y el workaround. El flujo toca 5 tablas: `clientes` (R), `subscripciones_cliente` (R para seleccionar la sub a reclamar), `reclamos` (W workflow root), `log_transaccional` (W), `sucursal` (R tenant).

**Actor**: operator (creates the reclamo)

**Pre-conditions**: cliente exists; cliente has at least one `subscripciones_cliente` (since the reclamo must reference one); operator has permission to file reclamos.

**Steps**:
1. Customer files a complaint (e.g., "I've been overcharged for 3 months"). Operator opens `web_sucursal/ReclamosForm`.
2. Frontend shows `ReclamoLookup` with cliente lookup (per `uc.clientes.subscriber-arrival-lookup-by-cedula`).
3. Operator looks up cliente by cedula. Frontend GETs `api_sucursal /clientes/{uuid}/subscripciones`.
4. Backend returns the active (or historical) subscripciones for the cliente. Frontend shows: "Seleccione la subscripción a reclamar: Plan Mensual Auto (since 2025-06-01)".
5. Operator selects the subscription.
6. Frontend POSTs `api_sucursal /reclamos` with `{uuid_sucursal: $branch, tipo_reclamable: 'subscripcion', uuid_reclamable: $sub_uuid, motivo: 'cobro_excesivo_3_meses'}`.
7. Backend validates: `tipo_reclamable` is in the allowed enum `{ingreso, salida, factura, subscripcion}`. `'cliente'` would be rejected with 422 (not in enum).
8. Backend SELECTs `subscripciones_cliente` WHERE `uuid=$uuid_reclamable AND uuid_sucursal=$branch`. (Cross-tenant protection: if subscription belongs to another branch, reject.)
9. Backend opens TX; SELECT chain anchor.
10. Backend INSERTs `reclamos` workflow root (`estado='abierto', uuid_reclamo_padre=NULL`).
11. Backend INSERTs `log_transaccional` (`accion='reclamo_abierto'`, `tabla_afectada='reclamos'`, `uuid_registro_afectado=$reclamo_uuid`, `uuid_referencia=$sub_uuid`).
12. `queue_processor.enqueue('reclamos', $uuid, $snapshot)` → parametrization push.
13. Cloud receives; admin reviews in `web_admin/ReclamosList`.

**Tables touched (writes)**: `reclamos` (1 workflow root), `log_transaccional` (1 row), `sync_queue` (1 row).
**Tables touched (reads)**: `clientes` (lookup), `subscripciones_cliente` (subscription lookup for cross-tenant check + selection), `reclamos` (enum constraint check), `log_transaccional` (chain anchor), `sucursal` (tenant), `usuarios` (operator).
**FKs traversed**: `reclamos.uuid_sucursal` → `sucursal.uuid`; `reclamos.uuid_reclamable` (polymorphic) → `subscripciones_cliente.uuid` (when `tipo_reclamable='subscripcion'`); `reclamos.uuid_reclamo_padre` → `reclamos.uuid` (workflow chain self-reference for subsequent transitions); `subscripciones_cliente.uuid_cliente` → `clientes.uuid`; `subscripciones_cliente.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `subscripciones_cliente.uuid`.

**Sync behavior**:
- Branch → cloud: YES — the `reclamos` workflow root + log push via `sync_queue` within 30s.
- Cloud → branch: NO (reclamos is cloud-admin-routed; branch sees the workflow transitions when parametrization pull delivers them).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1 row (reclamo_abierto); cloud chain extends by 1 row when received.

**Integration with other tables**:
- Reads from: `clientes` (lookup), `subscripciones_cliente` (subscription for cross-tenant + selection), `reclamos` (enum constraint), `log_transaccional`, `sucursal`, `usuarios`.
- Writes to: `reclamos` (workflow root), `log_transaccional` (audit), `sync_queue` (deferred propagation).
- Cross-cutting: this is the **polymorphic FK constraint enforcement**. The model explicitly limits `tipo_reclamable` to specific event types (ingreso, salida, factura, subscripcion), NOT generic entities like `cliente`. This forces every reclamo to be anchored to a specific event, which has audit value (the reclamo can be traced back to the exact thing that went wrong).
- Related: if a customer wants to complain about a service quality issue that doesn't fit any of the 4 types (e.g., "el operador fue grosero"), there's no clean way to file it in the current model. Options: (a) file it against the most recent ingreso of that cliente (proxy); (b) extend the model with `tipo_reclamable='cliente'` (sprint 5); (c) file as a `reclamos tipo_reclamable='subscripcion'` with detailed motivo. Current recommendation: (c) — least schema change.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 28, 31, 33, 38.

## 9. RED Tests
- (RED) F1 schema includes `clientes` table; F1 seed inserts `consumidor_final_default` with deterministic UUID.
- (RED) Admin POST `/clientes` with `tipo_persona='natural'` → 201; row persisted; parametrization pushed.
- (RED) Admin POST with duplicate `(numero_identificacion, uuid_tipo_persona='natural')` → 409.
- (RED) Admin POST with same `numero_identificacion` but different `tipo_persona='juridica'` → 201 (composite UNIQUE allows it).
- (RED) Operator GET `/clientes?numero_identificacion=$cedula` → 200 with matching cliente + active subscriptions + vehicles.
- (RED) Operator GET with non-existent cedula → 404.
- (RED) B2B create: `clientes` + `clientes_b2b` created in same TX (rollback if either fails).
- (RED) UNIQUE on `clientes_b2b.uuid_cliente` — second B2B for same cliente → UNIQUE violation.
- (RED) Expiry monitor: B2B `fecha_vencimiento < NOW()` → all active subscriptions for that cliente marked `estado='vencida'`.
- (RED) Expiry monitor: `fecha_vencimiento < NOW() - 30 days` → emits `b2b_vencido_critico`.
- (RED) Expiry monitor dedup: existing open alerta → no duplicate.
- (RED) Consumidor final: operator selects seed UUID; `factura_electronica.uuid_cliente` references seed.
- (RED) Reclamo with `tipo_reclamable='cliente'` → 422 (not in enum).
- (RED) Reclamo with `tipo_reclamable='subscripcion'` and `uuid_reclamable` referencing sub from another branch → 403 (cross-tenant).
- (RED) Cross-audience: operador from branch A to `/clientes/{uuid_cliente_B}` → 403 (or scoped view).
- (RED) PATCH `numero_identificacion` on existing cliente → new version created, old archived.

## 10. Implementation Tasks
- [x] F1.x Schema + `consumidor_final_default` seed.
- [ ] IT-10.x: `api_admin /clientes` (POST, PATCH, GET list, GET detail).
- [ ] IT-10.x: `api_sucursal /clientes` (lookup-by-cedula, GET detail, GET subscripciones).
- [ ] IT-10.x: parametrization push for clientes updates.
- [ ] IT-10.x: `parkos_core/clientes/lookup_service.py::find_by_cedula()` with subscription + vehicle JOIN.
- [ ] IT-10.x: `workers/clientes/expiry_monitor.py` (cron, daily 03:00 cloud).
- [ ] IT-10.x: `web_admin/ClientesList`, `ClienteForm`, `ClientesDetail/SubscripcionesTab`.
- [ ] IT-10.x: `web_sucursal/ClienteLookup` (the lookup-by-cedula UI embedded in `IngresoForm`).

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Same cedula typo → duplicate cliente | Low | Composite UNIQUE constraint per `tipo_persona`; admin must merge manually if discovered |
| GDPR-style deletion request | Low | Sprint 5: pseudonymize via `registro.pseudonymize=true` flag + UPDATE nombre to `PSEUDONYMIZED_$uuid_short`; preserve UUID for FK |
| Lookup-by-cedula performance | Low | Indexed on `(numero_identificacion, uuid_tipo_persona)`; ~50ms per lookup acceptable for operator UI; sprint 5 may add Redis cache |
| B2B contract overlap (multiple `clientes_b2b` per cliente) | Low | UNIQUE on `uuid_cliente` prevents; renewal = PATCH (new version) |
| Subscriber with no active sub at current branch | Med | Documented: lookup returns 0 subs → operator proceeds as casual; cross-branch subscriptions do NOT auto-apply |
| Operador types wrong cedula (typo) | Med | Lookup returns "no encontrado" — operator asks customer to confirm; no false matches |
| Reclamo against cliente without subscripcion | Low | Workaround: file against their most recent subscripcion (even if expired); sprint 5 may extend `tipo_reclamable` enum |

## 12. Open Questions
- (a) `log_transaccional.uuid_sucursal` for cloud-only cliente writes: use cloud sentinel or first-active-branch UUID? Same issue as `tipo_sucursal` PRDs.
- (b) GDPR deletion: how to handle FK integrity when a cliente is "deleted"? Current: archive only (preserve FK). Sprint 5: pseudonymize.
- (c) Lookup-by-cedula caching: Redis 5-min cache acceptable? Or per-request DB query?
- (d) Composite UNIQUE `(numero_identificacion, uuid_tipo_persona)`: should the same NIT be allowed for natural AND juridica? Currently allowed by composite; some regulators may want stricter (NIT must be unique globally). Sprint 5 decision.
- (e) B2B contract auto-renewal: should `clientes_b2b` auto-extend on expiry if `registro.auto_renew=true`? Sprint 5.
- (f) `reclamos.tipo_reclamable` extension to include `'cliente'`: enables claims against customer behavior in general (not anchored to a specific event). Sprint 5 model extension.
- (g) Multi-branch cliente (cliente has subscripciones at multiple branches): current model supports it (`subscripciones_cliente` rows per branch). UI: should `web_admin/ClientesDetail` show ALL branches' subscriptions, or just one branch at a time? Currently scoped to selected branch via `X-Sucursal-Context` header.
- (h) Cliente with mixed B2C + B2B (e.g., a natural person who is also a representative of a juridica): two separate `clientes` rows (different `uuid_tipo_persona`). Cross-references via `registro.representante_legal_uuid` JSON field.
