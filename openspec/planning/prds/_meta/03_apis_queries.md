# Meta-PRD: API queries (PRD-03)

> **NOT a table PRD.** Documents the exact endpoints and queries that
> `api_admin` and `api_sucursal` expose for each of the 45 tables.

## Required References

### Canonical files outside this folder

- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration-plan.md`](../iteration-plan.md)
- **PRD-00 Scaffold**: [`_meta/00_scaffold.md`](00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **PRD-02 Jobs queries**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)

### Shared PRD references (this folder)

- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md)
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md)
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata

- **Type**: Meta-PRD (API endpoints)
- **Phase**: Phase 1+ (every iteration adds endpoints)
- **Stack**: FastAPI + Pydantic v2 + SQLAlchemy 2.0 async + Depends(get_session)
- **Origin**: per-iteration (IT-1+)
- **PRD status**: Draft
- **PRD version**: 2.0
- **Last updated**: 2026-08-31

## 2. Why this PRD is needed

Per-table PRDs document the table's structure. But API endpoints have cross-cutting concerns (auth, tenancy, audit logging) that apply uniformly. This meta-PRD defines:

- The two-API split (`api_admin` + `api_sucursal`).
- Auth dependency per audience.
- Tenancy middleware.
- Per-table CRUD matrix.
- Audit log middleware that wraps every state-mutating request.

Per-table PRDs override where needed.

## 3. Two APIs

| API | Path | Stack | JWT scope | Tenancy |
|---|---|---|---|---|
| `api_admin` | `/api/v1/admin/...` | FastAPI in cloud | `admin` JWT (long-lived; broad) | `sucursales_permitidas` list (N branches) |
| `api_sucursal` | `/api/v1/sucursal/...` | FastAPI in branch | `operador` JWT (medium-lived; branch-pinned) | Single `uuid_sucursal` enforced |

Plus shared endpoints:

| Endpoint | Path | API | Auth |
|---|---|---|---|
| `POST /auth/login` | `/api/v1/{admin,sucursal}/auth/login` | both | bcrypt + JWT |
| `GET /health` | `/api/v1/{admin,sucursal}/health` | both | none |
| `POST /sync/pair` | `/api/v1/sucursal/sync/pair` | branch → cloud (called by branch entrypoint) | `PAIRING_TOKEN` (one-time) |
| `POST /sync/push` | `/api/v1/admin/sync/push` | branch → cloud | `sync_agent` JWT |
| `POST /sync/pull` | `/api/v1/admin/sync/pull` | branch → cloud | `sync_agent` JWT |
| `GET /sync/dian-numbers` | `/api/v1/admin/sync/dian-numbers` | branch → cloud | `sync_agent` JWT |
| `GET /sync/jwks` | `/api/v1/admin/sync/jwks` | public | none |

## 4. Use Cases enabled by these APIs

### 4.1 Use Case: `uc.api.login-operator`

**Flow**:
1. Branch operator opens `web_sucursal/LoginForm`, enters email + password.
2. Frontend POSTs to `api_sucursal /auth/login`.
3. Backend: SELECT `usuarios` (via `uuid_email` from sync cache OR direct query), bcrypt verify.
4. Verify `usuarios_sucursal.uuid_usuario` exists → `estado='activo'`.
5. SELECT `permisos_usuario` rows → permission list.
6. Issue `operador` JWT with `{sub: uuid_usuario, sucursales_permitidas: [uuid_sucursal], permisos: [...], aud: api_sucursal, ttl: 8h}`.
7. INSERT `login` row (`estado='exitoso'`).
8. INSERT `log_transaccional` row (`accion='login_exitoso'`).
9. Return `{access_token, expires_at, role: operador, permisos: [...]}`.

**Tables touched**: `usuarios` (R), `usuarios_sucursal` (R), `permisos_usuario` (R), `login` (W), `log_transaccional` (W).

### 4.2 Use Case: `uc.api.pairing-branch-first-boot`

**Flow**:
1. Branch operator runs `docker compose up`, gets `PAIRING_TOKEN` from admin.
2. Branch entrypoint POSTs `api_admin /sync/pair` with `{PAIRING_TOKEN, BRANCH_UUID}`.
3. Cloud: SELECT `pairing_tokens` (or `usuarios_sucursal.metadata`) → verify token not used, not expired.
4. Issue `sync_agent` JWT with `{sub: <branch>, uuid_sucursal: BRANCH_UUID, ttl: 90d, aud: [api_admin, api_sucursal]}`.
5. Mark token used.
6. INSERT `login` row (`estado='exitoso'`, action=pairing).
7. INSERT `log_transaccional` row (`accion='pairing_exitoso'`).
8. Return `{access_token, expires_at}`.

**Tables touched**: `usuarios_sucursal` (R), `login` (W), `log_transaccional` (W).

### 4.3 Use Case: `uc.api.event-ingreso-online`

**Flow**:
1. Branch operator scans vehicle plate, enters tipo vehiculo.
2. Frontend POSTs `api_sucursal /ingresos` with `{placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente?}`.
3. Backend: INSERT `ingreso` row.
4. INSERT `log_transaccional` (`accion='ingreso_creado'`).
5. `queue_processor.enqueue('ingres','', uuid, datos)` → INSERT `sync_queue` row.
6. INSERT `sync_log` (will be written by worker later).
7. Return `{uuid, fecha_ingreso}`.

**Tables touched**: `ingreso` (W), `log_transaccional` (W), `sync_queue` (W).

### 4.4 Use Case: `uc.api.factura-online`

**Flow**:
1. Branch operator opens `FacturacionForm`, selects cliente + items + pagos.
2. Frontend POSTs `api_sucursal /facturas` with `{uuid_ingreso, uuid_cliente, items, pagos}`.
3. Backend: SELECT `ingreso` (verify exists, branch-scoped).
4. SELECT `empresa.consecutivo_actual` FOR UPDATE (atomic).
5. SELECT `tarifas_sucursal` for each item (price snapshot).
7. INSERT `facturas` row with `subtotal`, `descuento`, `total`.
8. INSERT `factura_detalle` rows (lines).
9. INSERT `factura_pagos` rows.
10. INSERT `factura_impuestos` rows (snapshot from `impuestos`).
11. INSERT `factura_otros_cobros` rows (snapshot from `otros_cobros`).
12. UPDATE `empresa.consecutivo_actual = consecutivo + 1`.
13. INSERT `factura_electronica` row with `consecutivo=$new_consec, numero_oficial=...`.
14. INSERT `SyncBackEvent` (if pull-mode) or POST to branch with real number.
15. INSERT `log_transaccional` (`accion='factura_creada'`, hash chain).
16. `queue_processor.enqueue('facturas', uuid, datos)` (branch sync).
17. Return `{uuid, uuid_factura_electronica, numero_oficial, total}`.

**Tables touched (cloud-only atomic TX)**: `ingreso` (R), `em` (W), `facturas` (W), `factura_detalle` (W), `factura_pagos` (W), `factura_impuestos` (W), `factura_otros_cobros` (W), `factura_electronica` (W), `log_transaccional` (W), `SyncBackEvent` (W).

### 4.5 Use Case: `uc.api.workflow-anulacion`

**Flow**:
1. Branch operator requests `POST /anulaciones` with `{uuid_ingreso, motivo}`.
2. Backend: INSERT `anulaciones` row with `estado='solicitada', uuid_anulacion_padre=NULL` (chain root).
3. INSERT `log_transaccional` (`accion='anulacion_solicitada'`).
4. INSERT `sync_queue` row for the anulacion event.
5. Cloud admin reviews via `web_admin`, clicks `POST /anulaciones/{uuid}/aprobar`.
6. Backend: SELECT current chain root (SELECT * FROM anulaciones WHERE uuid_ingreso=$1 AND uuid_anulacion_padre IS NULL).
7. INSERT new row `estado='aprobada', uuid_anulacion_padre=$chain_root, timestamp_evento=NOW()`.
8. INSERT `log_transaccional`.
9. INSERT `sync_queue` for the approval event.
10. Cloud admin clicks `POST /anulaciones/{uuid}/ejecutar`.
11. Backend: SELECT latest chain row.
13. INSERT new row `estado='ejecutada', uuid_anulacion_padre=$latest`.
14. UPDATE `ingreso.estado` derived (set flag in `sync_queue.datos` for branch to apply).
15. INSERT `log_transaccional`.

**Tables touched**: `anulaciones` (W x3 for chain), `ingreso` (R, branch-side W via sync), `log_transaccional` (W x3), `sync_queue` (W x3).

### 4.6 Use Case: `uc.api.admin-list-invoices`

**Flow**:
1. Admin opens `web_admin/FacturasList`.
2. Frontend GETs `api_admin /facturas?uuid_sucursal=&desde=&hasta=&cursor=`.
3. Backend: SELECT `facturas` with pagination.
4. JOIN `factura_detalle`, `factura_pagos`, `factura_electronica` (eager load via `selectinload`).
5. Return paginated list with totals.
6. INSERT `log_transaccional` (read audit).

**Tables touched (read-only)**: `facturas`, `factura_detalle`, `factura_pagos`, `factura_electronica`, `revocacion_factura` (for state).

### 4.7 Use Case: `uc.api.admin-create-subscripcion`

**Flow**:
1. Admin opens `web_admin/SubscripcionForm`, selects cliente + tipo_subscripcion + vehiculos.
2. Frontend POSTs `api_admin /subscripciones` with `{uuid_cliente, uuid_sucursal, uuid_tipo_subscripcion, fecha_vencimiento, uuid_vehiculos[]}`.
3. Backend: SELECT `clientes` (verify exists), `tipo_subscripciones` (verify exists).
4. Verify cliente's `cantidad_maxima_vehiculos` from `tipo_subscripciones`.
5. INSERT `subscripciones_cliente`.
6. For each `uuid_vehiculo`: INSERT `subscripcion_vehiculos` linking vehiculo to subscripcion.
7. INSERT `log_transaccional` (`accion='subscripcion_creada'`).
8. `queue_processor.enqueue('subscripciones_cliente', uuid, datos)` for branch sync.
9. INSERT `log_transaccional` (`accion='subscripcion_vehiculos_created'` x N).
10. Return `{uuid, uuid_vehiculos: [...]}`.

**Tables touched**: `clientes` (R), `tipo_subscripciones` (R), `subscripciones_cliente` (W), `vehiculos` (R), `subscripcion_vehiculos` (W x N), `log_transaccional` (W x N), `sync_queue` (W).

### 4.8 Use Case: `uc.api.cash-cierre`

**Flow**:
1. Operator opens `web_sucursal/CierreCajaForm`, enters expected efectivo + datafono counts.
2. Frontend POSTs `api_sucursal /arqueos` with `{uuid_sucursal, valor_efectivo_esperado, valor_datafono_esperado, valor_efectivo_reportado, valor_datafono_reportado, uuid_sesion}`.
3. Backend: SELECT `factura_pagos` SUM by `medio_pago` for the sesion's `timestamp_apertura..NOW()`.
4. Backend computes `diferencia_efectivo`, `diferencia_datafono`.
5. INSERT `arqueo` row.
6. UPDATE `sesion SET estado='cerrada', timestamp_cierre=NOW()` + INSERT `log_transaccional` (`ls_session_update_guard` ensures `log_transaccional` write).
7. UPDATE `caja` (snapshot of final state).
8. If `ABS(diferencia_efectivo) > tolerancia_efectivo OR ABS(diferencia_datafono) > tolerancia_datafono`: INSERT `alerta tipo_alerta='diferencia_arqueo'`.
9. INSERT `log_transaccional` (`accion='arqueo_creado'`).
10. `queue_processor.enqueue('arqueos', uuid, datos)` + `queue_processor.enqueue('alerta', uuid, datos)` if alert.

**Tables touched**: `factura_pagos` (R), `arqueo` (W), `sesion` (W), `caja` (W), `alerta` (W conditional), `log_transaccional` (W x2 or x3), `sync_queue` (W x2 or x3), `configuracion_tolerancias` (R).

### 4.9 Use Case: `uc.api.pydantic-schemas-shared-across-services`

Both `api_admin` and `api_sucursal` import Pydantic v2 schemas from `parkos_core/schemas/`. The schemas are derived from the SQLAlchemy models (via `parkos_core/schemas/generator.py`) but separated per SOLID I (request vs response, segregated). This ensures cross-service consistency: a `Factura` schema is the SAME object in both APIs (admin reads cloud-side, sucursal writes branch-side). Sprint 5 may add per-audience variants if needed (e.g., admin sees more fields than operador).

**Steps**:
1. Developer runs `uv run --package parkos_core python -m parkos_core.schemas.generator --model Factura --output parkos_core/schemas/factura.py`.
2. Generator emits `FacturaRequest` (write schema, excludes server-set fields like `uuid`, `created_at`) + `FacturaResponse` (read schema, includes everything) + `FacturaList` (paginated list response with cursor).
3. Both `api_admin/routers/facturas.py` and `api_sucursal/routers/facturas.py` `from parkos_core.schemas.factura import FacturaRequest, FacturaResponse`.
4. Endpoint signature: `async def create_factura(payload: FacturaRequest, ctx: OperadorContext = Depends(require_operador)) -> FacturaResponse`.
5. Pydantic v2 validates payload against schema BEFORE the endpoint body runs (defense against bad input). Errors return 422 with field-level detail.
6. Response is serialized via `FacturaResponse.model_validate(row)`.

**Tables involved**: any model that has API endpoints (all 45). Generator emits one schema file per model.

**Integrations**: enables the entire API surface; ensures consistency between admin and branch APIs.

### 4.10 Use Case: `uc.api.openapi-generation-feeds-frontend-clients`

FastAPI auto-generates OpenAPI 3.1 schema at `GET /openapi.json` for both `api_admin` and `api_sucursal`. Frontend clients (`web_admin` + `web_sucursal`) consume this schema to generate TypeScript types + React Query hooks (via `openapi-typescript` + `openapi-react-query`). The contract is therefore SINGLE SOURCE OF TRUTH — backend changes propagate to frontend on the next build. Sprint 5 may add API versioning (`/api/v2/...`) for breaking changes.

**Steps**:
1. Backend runs `uv run --package api_admin python -m api_admin` on port 8000.
2. `curl http://localhost:8000/openapi.json` returns the full schema with paths, request/response schemas, auth requirements.
3. Frontend dev runs `npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.ts` — generates TypeScript types.
4. Frontend runs `npx openapi-react-query http://localhost:8000/openapi.json` — generates React Query hooks (`useListFacturas`, `useCreateFactura`, etc.).
5. Frontend uses the generated hooks in components. Type errors caught at compile time if backend contract changes.
6. CI verifies: backend `openapi.json` is committed to `apps/web_admin/openapi.snapshot.json` and `apps/web_sucursal/openapi.snapshot.json`; frontend build fails if generated types differ from snapshot (breaking change detection).

**Tables involved**: any model with endpoints. The OpenAPI schema includes all CRUD endpoints from the matrix in section 5.

**Integrations**: enables the entire frontend stack; provides type-safe contract enforcement.

### 4.11 Use Case: `uc.api.rate-limiting-per-endpoint-and-per-ip`

FastAPI middleware applies rate limiting per endpoint and per IP (default 100 req/min per IP per endpoint). For `/auth/login`, the limit is tighter (default 10 req/min per IP) to mitigate brute force. Rate limit state is stored in Redis (per branch deployment) or in-memory (per cloud instance). Exceeding the limit returns 429 Too Many Requests with `Retry-After` header.

**Steps**:
1. Operator POSTs `/auth/login` with wrong password 11 times in 1 minute from the same IP.
2. Middleware increments counter in Redis: `INCR rate_limit:auth_login:$ip EX 60`.
3. On the 11th request: counter is 11, limit is 10. Return 429 `{"detail":"rate_limited","retry_after":45}` with `Retry-After: 45` header.
4. Sprint 5: may use a token bucket algorithm for smoother rate limiting (vs hard cutoffs).

**Tables involved**: NONE directly. Redis state for rate limit counters (separate from Postgres).
**Integrations**: defense-in-depth on top of `login_lockout_monitor` (which is user-specific); rate limiting is IP-specific.

## 5. Per-table endpoint matrix

The following matrix is the canonical "what API surface each table has". Per-table PRDs reference this matrix and override where needed.

| Table | Level | api_admin endpoints | api_sucursal endpoints |
|---|---|---|---|
| `usuarios` | V | `POST /us`,`, `GET /us`,`, `GET /us`,`/{uuid}`, `PATCH /us`,`/{uuid}` | none (admin-only) |
| `permisos` | V | `POST /permisos`, `GET /permisos` | none |
| `permisos_usuario` | V | `POST /permisos-us`,`, `DELETE /permisos-us`,`/{uuid}` | none |
| `usuarios_sucursal` | V | `POST /us`,`-suc`,`, `DELETE /us`,`-suc`,`/{uuid}` | `GET /us`,`-suc`,` (own branch only) |
| `sucursal` | V | full CRUD | `GET /sucursal/{uuid}` (own only) |
| `tipo_sucursal` | V | full CRUD | none (catalog) |
| `documentos` | V | full CRUD | `GET /documentos` (own only) |
| `tarifas_sucursal` | V | full CRUD | `GET /tarifas` (own only) |
| `cantidad_vehiculos_sucursal` | V | full CRUD | `GET /cantidad-vehiculos` (own only) |
| `clientes` | V | full CRUD | `GET /clientes` (own only) |
| `clientes_b2b` | V | full CRUD | none |
| `subscripciones_cliente` | V | full CRUD | `GET /subscripciones` (own only) |
| `subscripcion_vehiculos` | V | full CRUD | none |
| `vehiculos` | V | full CRUD | `GET /vehiculos` (own only) |
| `empresa` | V | `GET /em`,`, `PATCH /em`,` | `GET /em`,` (read-only projection) |
| `tipo_persona` | V | full CRUD | none (catalog) |
| `tipos_vehiculo` | V | full CRUD | `GET /tipos-vehiculo` (own only) |
| `tipo_subscripciones` | V | full CRUD | none (catalog) |
| `tipo_tarifa` | V | full CRUD | none (catalog) |
| `impuestos` | V | full CRUD | none (catalog) |
| `otros_cobros` | V | full CRUD | none (catalog) |
| `costos_servicios` | V | full CRUD | `GET /costos-servicios` (own only) |
| `configuracion_tolerancias` | V | full CRUD | `GET /configuracion-tolerancias` (own only) |
| `configuracion_seguridad` | V | full CRUD | `GET /configuracion-seguridad` (own only) |
| `ingreso` | L-E | `GET /ingresos?uuid_sucursal=` | `POST /ingresos`, `GET /ingresos`, `GET /ingresos/{uuid}` |
| `facturas` | L-E | `GET /facturas?uuid_sucursal=&desde=&hasta=` | `POST /facturas`, `GET /facturas/{uuid}`, `GET /facturas/{uuid}/numero-oficial` |
| `factura_electronica` | L-E | `POST /facturas/procesar` (cloud-only) | none (cloud-only writes) |
| `reimpresion_ticket` | L-W | `GET /reimpresiones?uuid_sucursal=` | `POST /reimpresion-ticket` (gated on SyncBackEvent) |
| `anulaciones` | L-W | `GET /anulaciones`, `POST /anulaciones/{uuid}/aprobar`, `POST /anulaciones/{uuid}/ejecutar` | `POST /anulaciones` (solicitada only) |
| `reclamos` | L-W | full workflow | `POST /reclamos` (abierto only) |
| `alerta` | L-W | full workflow + `GET /alertas?uuid_sucursal=` | `GET /alertas` (own only, read) |
| `login` | L-S | `GET /logins?uuid_usuario=&desde=&hasta=` (audit) | none (auto-written) |
| `sesion` | L-S | `GET /sesiones?uuid_sucursal=&desde=&hasta=` (audit) | `POST /sesiones` (open), `PATCH /sesiones/{uuid}` (close with `log_transaccional` write) |
| `sync_queue` | A | `GET /sync-queue?uuid_sucursal=&estado=` (audit only) | `GET /sync-queue?estado=` (own only) |
| `sync_log` | A | `GET /sync-log?uuid_sucursal=&desde=&hasta=` | `GET /sync-log?desde=&hasta=` |
| `sync_conflict` | A | full CRUD (admin resolution) | `GET /sync-conflict?uuid_sucursal=` |
| `log_transaccional` | A | `GET /log-transaccional?uuid_sucursal=&tabla_afectada=&uuid_usuario=&desde=&hasta=` (admin-auditor only, BYPASSRLS) | none (branch never reads) |
| `revocacion_factura` | A | full CRUD (cloud-only writes) | none |
| `caja` | A | `GET /caja?uuid_sucursal=&fecha=` | `POST /caja`, `GET /caja/{uuid}` |
| `arqueo` | A | `GET /arqueos?uuid_sucursal=&desde=&hasta=` | `POST /arqueos`, `GET /arqueos/{uuid}` |
| `factura_detalle` | A | `GET /factura-detalle?uuid_factura=` | none (auto-written) |
| `factura_impuestos` | A | `GET /factura-impuestos?uuid_factura=` | none (auto-written) |
| `factura_otros_cobros` | A | `GET /factura-otros-cobros?uuid_factura=` | none (auto-written) |
| `factura_pagos` | A | `GET /factura-pagos?uuid_factura=` | `POST /factura-pagos`, `GET /factura-pagos?uuid_factura=` |
| `salidas` | A | `GET /salidas?uuid_sucursal=&desde=&hasta=` | `POST /salidas`,`, `GET /salidas/{uuid}` |

## 6. CRUD operation rules per enforcement level

| Level | POST (create) | GET (read) | PATCH (update) | DELETE |
|---|---|---|---|---|
| `[V]` projection | YES (new row; version 1) | YES | YES (creates new row; archive old) | NO (archive via PATCH) |
| `[L-E]` event | YES | YES | NO (derived state) | NO |
| `[L-W]` workflow | YES (initial state) | YES | NO (creates new row in chain) | NO |
| `[L-S]` session | YES | YES | YES (only `estado`, `timestamp_cierre`/`timestamp_apertura`) | NO |
| `[A]` source-of-truth | YES | YES | NO (REVOKE) | NO (REVOKE) |
| `[A]` `sync_queue` (operational UPDATE exception) | YES | YES | YES (only `estado`, `intentos`, `next_retry_at`, `ultimo_error`) | NO |

## 7. Cross-cutting middleware

### 7.1 Auth dependency

```python
async def require_admin(token: str = Depends(oauth2_scheme)) -> AdminContext:
    payload = jwt_three_issuers.verify_token(token, audience="api_admin")
    return AdminContext(uuid_usuario=payload["sub"], sucursales_permitidas=payload["sucursales_permitidas"])

async def require_operador(token: str = Depends(oauth2_scheme)) -> OperadorContext:
    payload = jwt_three_issuers.verify_token(token, audience="api_sucursal")
    return OperadorContext(uuid_usuario=payload["sub"], uuid_sucursal=payload["uuid_sucursal"])

async def require_sync_agent(token: str = Depends(oauth2_scheme)) -> SyncAgentContext:
    payload = jwt_three_issuers.verify_token(token, audience=["api_admin", "api_sucursal"])
    return SyncAgentContext(uuid_sucursal=payload["uuid_sucursal"], scope="sync_agent")
```

### 7.2 Tenancy middleware

```python
async def branch_scope_filter(
    request: Request,
    admin_ctx: AdminContext = Depends(require_admin),
) -> UUID:
    """Admin must send X-Sucursal-Context header; enforce it's in sucursales_permitidas."""
    header_uuid = request.headers.get("X-Sucursal-Context")
    if not header_uuid or UUID(header_uuid) not in admin_ctx.sucursales_permitidas:
        raise HTTPException(403, "X-Sucursal-Context must be a permitted branch")
    return UUID(header_uuid)

async def operador_branch_scope(
    operador_ctx: OperadorContext = Depends(require_operador),
) -> UUID:
    """Operador JWT carries single uuid_sucursal — no override possible."""
    return operador_ctx.uuid_sucursal
```

### 7.3 Audit log middleware (writes `log_transaccional`)

For every successful state-mutating request (POST/PATCH that mutates `[A|V|L-S]` tables), `parkos_core.audit.log_transaccional_writer.write_event()` is called BEFORE the response is sent. This is enforced by a FastAPI dependency, not manually per endpoint.

## 8. FK Map

Endpoint FK usage mirrors PRD-01's FK Map (model-level). Endpoints join FKs via SQLAlchemy `selectinload` / `joinedload` to avoid N+1.

## 9. CodeGraph Dependencies

After models + APIs land, `codegraph query --name api_admin --direction both` and `codegraph query --name api_sucursal --direction both` returns the full blast radius per table.

## 10. Layer-by-Layer Impact

| Layer | Impact | Path |
|---|---|---|
| 6. API admin router | YES (this PRD) | `backend/packages/api_admin/.../routers/` |
| 7. API sucursal router | YES (this PRD) | `backend/packages/api_sucursal/.../routers/` |
| 8. Pydantic schemas | YES (one per endpoint) | `backend/packages/parkos_core/schemas/` |
| 9. Auth/tenancy | YES (middleware) | `backend/packages/parkos_core/auth/`, `db/tenancy.py` |
| 28. Docker/compose | YES (image runs them) | `Dockerfile` |

## 11. RED Tests

- (RED) Cross-audience JWT (admin→api_sucursal / operador→api_admin) → 401.
- (RED) Operador JWT to other branch's resource → 403.
- (RED) Branch operator `POST /facturas` online calls `api_admin /facturas/procesar`; offline uses `numero_temporal`.
- (RED) `POST /reimpresion-ticket` blocked before `uuid_factura_electronica` populated.
- (RED) `GET /log-transaccional` requires `rol_admin_auditor` (not just admin JWT).
- (RED) `PATCH /usuarios/{uuid}` creates new row version + archives old (via `vigente_hasta`).

## 12. Implementation Tasks

Per-iteration (IT-1..IT-12) defines which endpoints land in that iteration. Each endpoint:

- [ ] Has a Pydantic v2 request schema (`parkos_core/schemas/<table>.py`).
- [ ] Has a Pydantic v2 response schema (separated from request per `_shared/solid-principles.md` interface segregation).
- [ ] Uses `Depends(get_session)` + `Depends(require_admin)` / `Depends(require_operador)`.
- [ ] Writes a `log_transaccional` event on successful state mutation (via middleware).
- [ ] Has a pytest integration test with `httpx.AsyncClient` against the live container.

## 13. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Cross-audience JWT leak | Low | `audience` check in `jwt_three_issuers.verify_token` |
| Branch operator reads another branch's data | Low | Tenancy middleware enforced on EVERY endpoint |
| `log_transaccional` write fails after API succeeds | Med | Wrap in single TX; rollback API write on log failure |
| `[A]` UPDATE forbidden | Low | REVOKE + trigger + READ-ONLY model in API layer |
| N+1 on list endpoints | Med | Use SQLAlchemy `selectinload` / `joinedload` for FK eager loading |
| Pagination missing on list endpoints | Low | Cursor-based pagination `?limit=&cursor=` |

## 14. Open Questions

- (a) Pagination on GET list endpoints: cursor-based vs offset? Default: default: cursor-based with ` `?limit=&cursor=`.
- (b) Filtering syntax: OData, RSQL, or simple query params? Default: simple query params.
- (c) Bulk endpoints (e.g., bulk INSERT of `factura_detalle` lines)? Not for MVP; clients loop.
- (d) Rate limiting per endpoint? Apply via middleware; default 100 req/min per IP.
- (e) CORS: branch PWA + admin PWA both access from different origins; allow `https://admin.easypunto.example` + `https://*.easypunto.example`.

## 15. Hand-off

After this PRD lands, **per-table PRDs (T01..T45)** can fully document their endpoints by citing this matrix. Each per-table PRD's `## Layer-by-Layer Impact` section lists the relevant endpoints from this matrix.