# Spec: Bi-Temporal CRUD

## Capability

Provide a uniform Consulta + Inserción + Actualización surface for the **26 `[V]` bi-temporal projection tables** defined in `modelo_datos_er.mmd`. Every `[V]` row carries `vigente_desde`, `vigente_hasta`, and `estado`, where the natural-key UK includes `vigente_desde` so multiple versions of the same logical entity coexist as distinct rows. The API enforces the audit-first contract via a single shared helper (`parkos_core/repo/versioned.py`), a Pydantic v2 schema set per table, and a FastAPI router per domain group — exposed on `api_admin` for cloud-authored catalogs and replicated down to `api_sucursal` for read; branches never insert their own `[V]` rows except for branch-originated customer/operator records (see Scope table below). **No `DELETE` operation exists at any layer** (AD-2 defense in depth); concept closure is expressed as `vigente_hasta = NOW()` + a new INSERT in the same SQLAlchemy transaction (close + insert).

## Requirements

### REQ-01-V-CONSULTA: Current-version READ by natural key
**Given** a JWT bearing one of the three ratified issuers (`admin-`, `operador-`, `sync-agent-`) and tenant scope resolved (see `cross-cutting.md` REQ-X1)
**When** a client calls `GET /api/v1/<resource>/{uuid}` where `<resource>` is the snake_case name of any of the 26 `[V]` tables
**Then** the system MUST return the row whose `uuid` matches and `vigente_hasta IS NULL`, projected through the table's `Read` Pydantic schema (200 OK), or 404 if no such row exists; an additional `?vigente_desde=<timestamp>` query param selects a historical version and the response carries the active/inactive `estado` snapshot

### REQ-02-V-CONSULTA: List endpoint with cursor pagination
**Given** a tenant-scoped caller (per `cross-cutting.md` REQ-X1) on any `[V]` resource
**When** the client calls `GET /api/v1/<resource>?limit=<N>&cursor=<opaque>` with `limit` between 1 and 200 and `cursor` previously returned in a prior response
**Then** the system MUST respond with `{"items": [...], "next_cursor": "<opaque-or-null>"}` ordered by `(vigente_desde DESC, uuid ASC)` filtered to `vigente_hasta IS NULL`, and the `next_cursor` MUST be an opaque base64-encoded `{"vigente_desde": "...", "uuid": "..."}` tuple; an empty `next_cursor` (or `null`) signals end of result set (Q1 resolution); RFC 5988 `Link: <url>; rel="next"` header MUST also be emitted as a non-normative convenience
And `X-Total-Estimate` MUST NOT be present (count would force a full scan)

### REQ-03-V-INSERCION: Create inserts a new version with `vigente_desde = NOW()`
**Given** an `admin-` or `operador-` JWT (per the resource's tenant scope table in Scope below) and a validated `Create` Pydantic body
**When** the client calls `POST /api/v1/<resource>` with an `Idempotency-Key` header (per `operational.md` REQ-OP-04) and a business-natural-key payload whose UK (business key + `vigente_desde`) does not collide with an existing row
**Then** the system MUST INSERT exactly one new row with `vigente_desde = NOW()`, `vigente_hasta = NULL`, `estado = 'activo'`, `created_at = NOW()`, `created_by = <jwt_subject_uuid>`, and return 201 Created with the projected `Read` payload

### REQ-04-V-ACTUALIZACION: Update = close current version + insert new version (bi-temporal)
**Given** an existing active row `R` (i.e. `R.vigente_hasta IS NULL`) on a `[V]` resource where the operation is permitted (per Scope)
**When** the client calls `PUT /api/v1/<resource>/{uuid}` with a modified `Create` payload and an `Idempotency-Key` header
**Then** the system MUST (a) `UPDATE` `R` SET `vigente_hasta = NOW()`, `estado = 'inactivo'`, then (b) `INSERT` a new row with the new payload, `vigente_desde = NOW()`, `vigente_hasta = NULL`, `estado = 'activo'`, `created_by = <jwt_subject_uuid>` — both in the SAME `AsyncSession` transaction committed once — and return 200 OK with the new row's `Read` payload
And a `log_transaccional` row with `accion='actualizar'`, `datos_anteriores = json(R_old)`, `datos_nuevos = json(R_new)` MUST be written (enforced by `versioned.close_and_insert()` helper, not by the API caller) — see `cross-cutting.md` REQ-X4

### REQ-05-V-HISTORY: History endpoint surfaces the full version chain
**Given** a tenant-scoped caller with READ permission on the resource
**When** the client calls `GET /api/v1/<resource>/{uuid}/historial`
**Then** the system MUST respond with `{"uuid_business_key": "...", "versiones": [Read, ...]}` ordered by `vigente_desde DESC`, including both active and inactive versions, paginated with the same cursor scheme as REQ-02-V-CONSULTA; the response enables audit reconstruction at any point in time

### REQ-06-V-FILTRO: Filter and search shape
**Given** a tenant-scoped READ caller
**When** the client calls `GET /api/v1/<resource>` with any combination of `uuid_sucursal`, `estado`, `vigente_desde__gte`, `vigente_desde__lte`, `vigente_hasta__isnull`, `created_by`, plus table-specific filter fields declared in each `Filter` Pydantic schema
**Then** the system MUST apply all filters as a WHERE clause applied to the canonical table before pagination, reject filters that reference non-declared fields via Pydantic `extra='forbid'`, and apply the partition-key-aware filter requirement where applicable (not relevant for `[V]` tables — they are not partitioned; the requirement applies only to `[A]`s in `append-only-events.md`)

## Scenarios

### SC-01-V-CATALOG-CRUD: Admin creates → operator reads → admin updates → second version visible in history
1. An `admin-` token holder calls `POST /api/v1/tipo-persona` with body `{"tipo": "natural"}` and `Idempotency-Key: 11111111-1111-1111-1111-111111111111`. Expect HTTP 201 with a row whose `vigente_desde = T0` and `vigente_hasta = null`.
2. An `operador-` token (pinned to `sucursal_id=A`) calls `GET /api/v1/tipo-persona/{uuid}`. Expect HTTP 200 with the same row (catalogs are replicated to all branches).
3. An `admin-` token holder calls `PUT /api/v1/tipo-persona/{uuid}` with `{"tipo": "natural", "updated_reason": "rename to persona_natural"}`. Expect HTTP 200; the response contains the new row at `vigente_desde = T1`; the original row now has `vigente_hasta = T1` and `estado = 'inactivo'`.
4. A subsequent `GET /api/v1/tipo-persona/{uuid}/historial` returns 2 rows; `GET /api/v1/tipo-persona?limit=10` returns only the current version (`vigente_hasta IS NULL`).

### SC-02-V-PERMISOS-USUARIO-REVOKE: Bi-temporal revoke (Q7 resolution)
1. An `admin-` token holder grants permission: `POST /api/v1/permisos-usuario` with `{"uuid_usuario": "...", "uuid_permiso": "..."}`. Expect 201.
2. Later, the admin revokes via `PUT /api/v1/permisos-usuario/{uuid}` with `{"vigente_hasta": "NOW", "motivo": "rol_changed"}`. The helper performs close + insert; the new row carries `estado='inactivo'`, the prior row's `vigente_hasta` is set. No `revocado` boolean flag exists.

### SC-03-V-CONFIG-OVERRIDE: Default global + per-branch override read resolution
1. Cloud-admin writes `POST /api/v1/configuracion-seguridad` with `{"uuid_sucursal": null, "max_intentos_login": 5}`. Expect 201 (global default).
2. Cloud-admin writes `POST /api/v1/configuracion-seguridad` with `{"uuid_sucursal": "BRANCH-A-UUID", "max_intentos_login": 3}`. Expect 201 (override).
3. Operator at `BRANCH-A-UUID` calls `GET /api/v1/configuracion-seguridad/efectiva`. Service resolves to the per-branch override (`max_intentos_login=3`). Operator at `BRANCH-B-UUID` gets the global default (`5`).

### SC-04-V-NO-DELETE: API contract forbids DELETE
1. A static-analysis test (`backend/tests/static/test_no_delete_routes.py`) greps every FastAPI router under `parkos_core/api/v1/` for a route whose `methods` set contains `"DELETE"` — fails on the first match. CI enforces this on every PR.
2. Equivalent OpenAPI check: `jq '.paths | to_entries[] | select(.value.delete != null)' openapi.json` returns zero matches for both `api_admin/openapi.json` and `api_sucursal/openapi.json`.

## Scope — the 26 `[V]` tables by tenant write authority

| Resource | Tenant write authority | Domain group |
|---|---|---|
| `usuarios` | `admin-` (cloud-authored for admin users) + `operador-` (branch-pinned for self-registration with admin pre-approval; see `operational.md` REQ-OP-12) | auth |
| `permisos`, `permisos_usuario`, `usuarios_sucursal` | `admin-` only | auth |
| `tipo-persona`, `tipos-vehiculo`, `tipo-subscripciones`, `tipo-tarifa`, `tipo-sucursal`, `tipo-arqueo`, `impuestos`, `otros-cobros`, `costos-servicios` | `admin-` only (catalogs; read-replicated down) | catalogos |
| `configuracion-tolerancias`, `configuracion-seguridad` | `admin-` only (global + per-branch override) | configuracion |
| `empresa` | `admin-` only (cloud-only writes; branches read) | empresa |
| `resolucion-facturacion` | `admin-` + cloud-only deploy context (DIAN root) | dian-cloud |
| `sucursal`, `documentos` | `admin-` only (cloud-admin) | empresa |
| `tarifas-sucursal`, `cantidad-vehiculos-sucursal` | `admin-` only (per-branch override) | configuracion |
| `clientes`, `clientes-b2b`, `subscripciones-cliente`, `vehiculos`, `subscripcion-vehiculos` | `operador-` (branch-originated, replicated up); `admin-` for read across branches | clientes |

## Constraints

- **C-1**: NO `DELETE` HTTP route exists for any `[V]` resource. Closure is modeled as close + insert in the same TX. Enforced by static test (SC-04).
- **C-2**: Every ORM write MUST flow through `parkos_core/repo/versioned.py`. Static AST test (`test_no_raw_upsert_on_v_tables.py`) rejects direct `session.execute(update(...))` against any of the 26 `[V]` declarative classes outside the `close_and_insert()` helper.
- **C-3**: Pydantic field names MUST match ORM column names exactly (`model_config = ConfigDict(from_attributes=True)`); CI validates one sample row per table.
- **C-4**: Every `[V]` row carries `(vigente_desde, vigente_hasta, estado, created_at, created_by, sync_status, sync_timestamp, sync_attempts)` — see `modelo_datos_er.mmd` column comments. No `[V]` table is exempt from this 8-column block.
- **C-5**: The natural-key UK (e.g. `cedula` for `usuarios`, `(prefijo_nombre, vigente_desde)` for `sucursal`) is enforced by the DB and asserted by Pydantic; INSERTing a duplicate with `vigente_desde` differing by microseconds is allowed (different version), INSERTing a duplicate at the same `vigente_desde` raises 409.
- **C-6**: `vigente_desde` is always the TX `NOW()` — clients MUST NOT supply it in the body; supplying it returns 422.
- **C-7**: Every list endpoint MUST be server-time-ordered by `(vigente_desde DESC, uuid ASC)` to guarantee cursor stability across concurrent inserts (last-write-wins on PK only when `vigente_desde` differs).

## Out of scope

- Bulk-CSV import endpoints (`POST /catalogos/<x>:batch`) — deferred per exploration §Open Q#10 and `operational.md` REQ-OP-10.
- Derived state projections for any `[V]` table — none of the 26 `[V]` tables expose state derivation; derived state belongs to `[L-E]` and `[L-W]` views (see `lifecycle-events.md` and `workflow-transitions.md`).
- WebSocket push of version updates — polling only for v1.
- Multi-currency per-empresa — not in ER.

## Dependencies

- `bootstrap-monorepo-foundation` MUST be merged to `dev` first — all 26 `[V]` tables exist at the DB layer (verified by `preflight_table_counts.sh` returning `>= 49`).
- `parkos_core/repo/versioned.py` — implements `close_and_insert()`, `current_version()`, `history()`, `list_with_cursor()`.
- `parkos_core/schemas/<domain>.py` — one `Read`/`Create`/`Update`/`Filter` quadruple per table; field names mirror ORM.
- `parkos_core/api/v1/<domain>.py` — one FastAPI router per domain group, mounted under `/api/v1` with the JWT scope guard described in `cross-cutting.md` REQ-X6.
- ADR references: AD-1 (list coverage), AD-2 (defense in depth), AD-3 (idempotency), AD-4 (nested derived state — not applicable to `[V]`).
- Engram topic: `sdd/create-49-table-apis/spec` (this spec).
