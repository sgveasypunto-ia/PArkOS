# HU-F15.2 — Empresa: card + página con tabs — tasks

> **Change**: `hu-f15-2-empresa`
> **Phase**: tasks (sdd-tasks)
> **Status**: applied (closed for F15.2 via commits `f223e60` already + this branch's wire-up)
> **Work-unit commits**: 4 (one per file group, per `work-unit-commits` skill).

## Review Workload Forecast

| Field | Value |
|---|---|
| Total changed lines | ~600 across BE schema+repo+route + FE query schema+api+component+tests |
| Work-unit commits | 4 (table_afectada, login shift, must-change routing already done in f223e60; this branch adds table_afectada wire-up + EmpresaBitacoraTab real impl + tests) |
| 400-line budget risk | Low (~250 in this branch; rest is in f223e60) |
| Chained PRs recommended | No (single branch `fix/hu-f15-2-empresa` covers theEmpresa bitácora wire-up) |
| Delivery strategy | single merge to `dev` |

## Work-unit commits

### Commit 1 — `feat(backend): audit endpoint accepts tabla_afectada singleton filter`

- `backend/packages/parkos_core/src/parkos_core/schemas/log_transaccional.py`: `AuditLogQueryParams` makes `uuid_sucursal` optional + adds `tabla_afectada: str | None`.
- `backend/packages/parkos_core/src/parkos_core/repo/log_transaccional.py::listar_eventos_paginados` accepts `tabla_afectada: str | None` and applies the SQL filter conditionally.
- `backend/packages/parkos_core/src/parkos_core/api/v1/audit.py::list_audit_log` raises `422 missing_selector` when neither selector is present.
- Migration: **none** (no schema change; only parameter acceptance).

### Commit 2 — `feat(web_admin): EmpresaBitacoraTab queries by tabla_afectada=empresa`

- `apps/web_admin/src/features/audit/api/auditSchema.ts`: `auditQuerySchema` mirrors the new BE shape.
- `apps/web_admin/src/features/audit/api/auditApi.ts::fetchAuditLog` includes `tabla_afectada` in the URL only when non-empty.
- `apps/web_admin/src/features/empresa/components/EmpresaBitacoraTab.tsx` rewrites the prior placeholder with a real SWR-backed component that:
  - queries `?tabla_afectada=empresa&limit=20`
  - renders the empty state `empresa-bitacora-empty` when the BE returns no rows
  - renders rows with `empresa-bitacora-row-{uuid}` + `HashChainStatus` + `empresa-bitacora-antes` / `empresa-bitacora-despues` JSON pre tags
  - renders the error state `empresa-bitacora-error` with `role="alert"`

### Commit 3 — `feat(test): EmpresaBitacoraTab unit tests`

- `apps/web_admin/src/features/empresa/components/EmpresaBitacoraTab.test.tsx` — three tests (B1 empty, B2 loaded with two rows + JSON payloads, B3 error).
- Mocks `fetchAuditLog` directly to keep cache isolation per test via the `swrKeySuffix` prop.

### Commit 4 — `feat(test): EmpresaMensajesTab unit tests`

- `apps/web_admin/src/features/empresa/components/EmpresaMensajesTab.test.tsx` — four tests (M1 empty, M2 pre-fill, M3 empty values accepted, M4 submit with trimmed payloads).
- Mocks `useEmpresa` directly (the form does NOT call `getEmpresa` directly — it goes through the SWR hook).
- i18n: cleans up obsolete `pendingTitle / pendingBody / sampleCaption / col` keys from the prior placeholder; adds `title / subtitle / empty / errorLoading` for the real implementation.

## Validation

- `cd apps/web_admin && npx tsc --noEmit -p tsconfig.app.json` → 0 errors.
- `cd apps/web_admin && npx vitest run` → 341/341 tests pass (53 test files, 0 failures).
- `docker exec -w /app/backend parkos-api-admin /app/backend/.venv/bin/python /tmp/check_schema.py ... --database-url postgresql://...` → (h1)/(h2)/(h3) green; the 2 pre-existing FAILs (`sync_catalog` not in ER, `tarifas_sucursal` partial UK) predate this commit.

## Pending For F15.2 To Be Fully Closing (not in this branch)

- **BE integration test** `test_admin_audit.py::test_list_audit_log_by_tabla_afectada` — covers the 422 + 200 paths. **To add** in a follow-up; the manual smoke (curl) verified this works end-to-end against the live cloud DB (status 200 with 2 items; status 422 with the correct error body when both selectors omitted).
- **HU-F15.2 Backlog** (kept open): "Cerrar el placeholder de ingresos_monto_total" (F17.1), Resoluciones DIAN (F15.3), Documentos (F15.4), Caja admin (F15.5).