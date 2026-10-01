# HU-F15.2 — Empresa: card + página con tabs — specs

> **Change**: `hu-f15-2-empresa`
> **Phase**: specs (sdd-specs)
> **Status**: implemented (merged `9d5a69c` wire-up + `7e2b8a7` placeholder → `08e71a4` real tab)
> **Spec coverage**: 4 ADDED Requirements + 1 MODIFIED for the singleton-table path.

## ADDED Requirements

### Requirement: REQ-OPS-148 — `GET /api/v1/admin/audit/log` accepts `tabla_afectada` as a singleton-table selector

The audit endpoint SHALL accept an optional query parameter `tabla_afectada` that, when provided, restricts the response to rows of `prod.log_transaccional` whose `tabla_afectada` column matches the value. Combined with the existing branch filter `uuid_sucursal`, this enables singleton-table auditing (HU-F15.2 Empresa bitácora, HU-F17 reportería) without requiring a `uuid_sucursal`.

When NEITHER `uuid_sucursal` NOR `tabla_afectada` is provided, the handler SHALL return `422 Unprocessable Entity` with `detail.error="missing_selector"` because the SQL would scan the full partition range (`fecha_retencion_hasta` is the partition key, not `uuid_sucursal`).

#### Scenario: list rows for `tabla_afectada='empresa'`

- **Given** an `admin-` token with `audit_read` permission
- **When** `GET /api/v1/admin/audit/log?tabla_afectada=empresa&limit=20`
- **Then** the response is `200 OK` with `{items: AuditLogItem[], next_cursor: string|null}`
- **And** every `items[*].tabla_afectada` equals `empresa`

#### Scenario: combined `uuid_sucursal` AND `tabla_afectada`

- **Given** the same actor
- **When** `GET /api/v1/admin/audit/log?uuid_sucursal=<X>&tabla_afectada=empresa`
- **Then** the SQL filter applies BOTH predicates with AND

#### Scenario: missing both selectors

- **Given** the same actor
- **When** `GET /api/v1/admin/audit/log?limit=20` (no `uuid_sucursal`, no `tabla_afectada`)
- **Then** the response is `422` with `detail.error="missing_selector"`

### Requirement: REQ-OPS-149 — `<EmpresaBitacoraTab />` wires the singleton filter end-to-end

The Empresa admin bitácora tab SHALL fetch `prod.log_transaccional` rows scoped by `tabla_afectada='empresa'` and render them with the same `<HashChainStatus />` component the cross-branch AuditDashboard uses.

#### Scenario: render the empty state when Empresa has no audit rows yet

- **Given** the singleton Empresa hasn't been edited
- **When** the admin opens `/empresa` and clicks the Bitácora tab
- **Then** the tab shows `data-testid="empresa-bitacora-empty"` with copy "Sin cambios registrados aún"

#### Scenario: render rows with hash-chain badge and before/after JSON

- **Given** two audit rows for Empresa exist (with `hash_anterior`, `hash_actual`, `datos_anteriores`, `datos_nuevos`)
- **When** the admin opens the Bitácora tab
- **Then** both rows render in `<ol data-testid="empresa-bitacora-list">`
- **And** each `<li>` carries `empresa-bitacora-row-{uuid}`, `empresa-bitacora-accion`, `empresa-bitacora-timestamp`, the HashChainStatus, and conditional `empresa-bitacora-antes` / `empresa-bitacora-despues` `<pre>` tags with `JSON.stringify(payload, null, 2)`

#### Scenario: render the error state when the BE rejects the request

- **Given** the `fetchAuditLog` call rejects (network or 5xx)
- **When** the admin opens the Bitácora tab
- **Then** the tab shows `data-testid="empresa-bitacora-error"` with `role="alert"` and the i18n copy "No se pudo cargar la bitácora"

### Requirement: REQ-OPS-150 — The audit repo accepts an optional `tabla_afectada` filter

`repo.log_transaccional.listar_eventos_paginados(session, *, uuid_sucursal, tabla_afectada, cursor, limit)` SHALL accept a new `tabla_afectada: str | None` parameter. When non-None, the WHERE clause adds `prod.log_transaccional.tabla_afectada == :tabla_afectada`. When None, the predicate is omitted (current behavior preserved).

The function's signature change is additive: existing callers that only pass `uuid_sucursal` continue to work — the new parameter has a None default OR callers explicitly pass None. (Implementation note: per `repo/versioned.py` repo convention, the function does not have a default; the schema validator at the route handler enforces "at least one" so callers from the route layer always pass either one or both.)

### Requirement: REQ-OPS-151 — Audit query schema accepts `tabla_afectada` as optional

`schemas/audit.py::auditQuerySchema` (the FE Zod mirror) SHALL make `uuid_sucursal` and `tabla_afectada` BOTH optional. The shared `fetchAuditLog` client SHALL include `tabla_afectada` in the URLSearchParams only when non-empty.

## MODIFIED Capabilities

### Capability: `GET /api/v1/admin/audit/log`

- The query schema (`AuditLogQueryParams`) was strict-`uuid_sucursal` previously. It now accepts `uuid_sucursal: UUID | None` and `tabla_afectada: str | None`. The handler raises `422 missing_selector` when both are None.
- The repo helper (`listar_eventos_paginados`) gained the optional `tabla_afectada` filter.

## Cross-References

- `backend/packages/parkos_core/src/parkos_core/schemas/log_transaccional.py::AuditLogQueryParams`
- `backend/packages/parkos_core/src/parkos_core/repo/log_transaccional.py::listar_eventos_paginados`
- `backend/packages/parkos_core/src/parkos_core/api/v1/audit.py::list_audit_log`
- `apps/web_admin/src/features/audit/api/auditSchema.ts::auditQuerySchema`
- `apps/web_admin/src/features/audit/api/auditApi.ts::fetchAuditLog`
- `apps/web_admin/src/features/empresa/components/EmpresaBitacoraTab.tsx`
- `apps/web_admin/src/features/empresa/components/EmpresaBitacoraTab.test.tsx`

## Test Pinning

- `backend/tests/integration/test_admin_audit.py::test_list_audit_log_by_tabla_afectada` (covers REQ-OPS-148 success case; **pending** — wire-up commit did not add a BE integration test)
- `apps/web_admin/src/features/audit/api/auditSchema.test.ts::auditQuerySchema accepts tabla_afectada` (covers REQ-OPS-151 — present)
- `apps/web_admin/src/features/empresa/components/EmpresaBitacoraTab.test.tsx` (B1, B2, B3 cover REQ-OPS-149 — present)