# HU-F15.2 — Empresa: card + página con tabs — design

> **Change**: `hu-f15-2-empresa`
> **Phase**: design (sdd-design)
> **Status**: applied (this branch `fix/hu-f15-2-empresa`).

## Architectural Choice

HU-F15.2 Empresa is a singleton tenant-global with no `uuid_sucursal`. The branch-scoped `/admin/audit/log` endpoint required a `uuid_sucursal` filter that no Empresa-related entry carries. The clean fix is **additive, not breaking**: extend `AuditLogQueryParams` with an optional `tabla_afectada` filter that the repo's SQL composes with `uuid_sucursal` via AND. Both filters are optional individually; the handler raises `422 missing_selector` when both are absent (the table is partitioned by `fecha_retencion_hasta`, not by `uuid_sucursal`, so a missing selector would scan the full partition range — that's the same safety class the schema validator was meant to enforce).

The reason we did NOT introduce a brand-new endpoint (`/admin/audit/log-by-table`) is that `log_transaccional` already supports the SQL filter natively; a new endpoint would duplicate the cursor/limit/permission-gate machinery and create two ways to query the same data. One endpoint with two optional selectors keeps the API surface small and the SQL composable.

## Data Flow

```
admin opens /empresa → Bitácora tab
  ↓
<EmpresaBitacoraTab /> (apps/web_admin/.../EmpresaBitacoraTab.tsx)
  ↓
useSWR('/admin/audit/log?tabla_afectada=empresa&limit=20&_=<testSalt>')
  ↓
fetchAuditLog({tabla_afectada:'empresa', limit:20})  (auditApi.ts)
  ↓
parkosFetchRaw('/api/v1/admin/audit/log?tabla_afectada=empresa&limit=20')
  ↓
audit.py::list_audit_log (api/v1/audit.py)
  ├── Step 4: SELECT via listar_eventos_paginados(...)
  │   ├── WHERE uuid_sucursal IS NULL OR = :u  (composable)
  │   └── WHERE tabla_afectada IS NULL OR = :t  (composable)
  ├── Step 5: next_cursor via encode_audit_cursor
  └── Step 6: Cache-Control: no-store header
  ↓
AuditLogListResponse{items, next_cursor}
  ↓
EmpresaBitacoraTab renders the rows with <HashChainStatus> per row
```

## Schema Decisions

### Decision: Pydantic v2 `model_validator` does NOT produce 422 inside FastAPI Depends()

We initially used `model_validator(mode="after")` to enforce the "at least one selector" rule. The validator raises `ValueError` → wrapped in `pydantic_core.ValidationError` → BUT FastAPI's default `RequestValidationError` handler does not translate `model_validator`-raised errors on optional query params into 422 — they propagate as a 500 because the validator runs AFTER the field-construction phase FastAPI already validated.

The fix: drop the model_validator and enforce the same rule explicitly in the route handler with `HTTPException(422)`. This is documented inline at `api/v1/audit.py` step 3.

### Decision: `tabla_afectada` is additive on the FE

`auditQuerySchema` makes both `uuid_sucursal` and `tabla_afectada` `.optional()`. `fetchAuditLog` only includes `tabla_afectada` in the URLSearchParams when non-empty, preserving the existing branch-scoped call site (AuditDashboard) with zero changes. The branch-scoped call continues to work — the BE treats `tabla_afectada=None` as "no table filter" and applies only `uuid_sucursal`.

### Decision: SWR cache key embeds `swrKeySuffix`

The `<EmpresaBitacoraTab />` accepts an optional `swrKeySuffix` prop that, when set, gets appended to the SWR key (`&_=<suffix>`). Unit tests use `Date.now()` per case to keep cache slots separate. In production the prop is not passed → key stays stable → SWR dedupes across navigations.

The reason a prop exists (rather than a non-deterministic key in the component itself): production should always use the same key for the same data — adding a random suffix in production would defeat SWR's deduping.

## Composition

- `listar_eventos_paginados(session, *, uuid_sucursal, tabla_afectada, cursor, limit)` adds the `tabla_afectada` filter as an OPTIONAL `WHERE` predicate. Both selectors compose with AND — if the row matches the branch AND the table, it's included.
- The existing AuditDashboard call site still passes only `uuid_sucursal` (the BE handler accepts that — `tabla_afectada` defaults to None and the predicate is omitted).
- EmpresaBitacoraTab passes only `tabla_afectada='empresa'` (the BE accepts that — `uuid_sucursal` defaults to None).
- A future "branch + singleton" audit view (e.g. "show me only admin_usuarios events for this branch") would pass both — handled natively by the repo's composable WHERE clause.

## Threading Through Endpoints (composition matrix)

| Caller | `uuid_sucursal` | `tabla_afectada` | Result |
|---|---|---|---|
| `AuditDashboard` (admin) | ✅ active branch from `<BranchSelector />` | not passed | rows for the selected branch, all tables |
| `EmpresaBitacoraTab` (admin) | not passed | `'empresa'` | rows for Empresa singleton, all branches |
| Future "branch + table" combo | ✅ branch | e.g. `'admin_usuarios'` | rows matching both |
| Empty call | not passed | not passed | `422 missing_selector` |

## Decisions Affected / Not Affected

- **Branch-scoped AuditDashboard**: ZERO changes required. The new `tabla_afectada` is additive and the existing `uuid_sucursal` is preserved.
- **HU-F15.2 EmpresaDatosTab**: unchanged.
- **HU-F15.2 EmpresaMensajesTab**: unchanged (no audit integration).
- **HU-F19.5 / F19.1 etc.**: unchanged; they will adopt `tabla_afectada` when they need to query the audit by table.

## Risk

- **Wire regression**: existing `uuid_sucursal`-only callers now also accept the new optional `tabla_afectada` parameter at the route, which is a non-breaking change. The schema validator's "at least one selector" rule never fires for those callers because `uuid_sucursal` is always set.
- **Orphan schema validator**: the model_validator that produces 500 instead of 422 is removed; the handler-level check raises `HTTPException(422)` directly. Same operator-visible shape as the validator would have produced.

## Files Touched

- `backend/packages/parkos_core/src/parkos_core/schemas/log_transaccional.py`
- `backend/packages/parkos_core/src/parkos_core/repo/log_transaccional.py`
- `backend/packages/parkos_core/src/parkos_core/api/v1/audit.py`
- `apps/web_admin/src/features/audit/api/auditSchema.ts`
- `apps/web_admin/src/features/audit/api/auditApi.ts`
- `apps/web_admin/src/features/empresa/components/EmpresaBitacoraTab.tsx`
- `apps/web_admin/src/features/empresa/components/EmpresaBitacoraTab.test.tsx` (new)
- `apps/web_admin/src/features/empresa/components/EmpresaMensajesTab.test.tsx` (new)
- `apps/web_admin/src/i18n/locales/es-CO.json` (`empresa.bitacora.*` cleanup)

## Future Hooks

- BE integration test `tests/integration/test_admin_audit.py::test_list_audit_log_by_tabla_afectada` — pending, manual smoke verified (curl 200 with 2 items, curl 422 with the typed error body).
- HU-F19.5 admin bandeja de alertas will benefit from the same pattern (events for the admin, scoped by `uuid_sucursal` + `tabla_afectada='alerta'`).
- HU-F20.4 bitácora global del admin (`log_transaccional` search) can add `uuid_usuario` as a third optional selector without touching this endpoint's signature — the repo would gain one more optional WHERE.