# Proposal: HU-X.8 — bugfixes + UX del módulo Facturación admin

> **Change**: `hu-x-8-bugfixes` (follow-up de `hu-x-facturacion-admin`)
> **Phase**: propose (sdd-propose)
> **Date**: 2026-10-13
> **Status**: ready for sdd-spec + sdd-design + sdd-tasks

## Why

`hu-x-facturacion-admin` cerró formalmente con ssd-archive (commit `40663ed2`). Durante el verify de ese change + un walkthrough en browser, se detectaron 4 issues de UX/data que la change no abordó (los 7 PRs de X.1..X.7 cubrieron la superficie funcional, no el pulido visual ni los 404 de DevTools). El usuario los enumeró explícitamente y aprobó el plan de arreglos.

## 4 issues

1. **404 de `GET /facturacion/factura-electronica/{uuid}` en DevTools**: el SWR pasa el `uuid` de la FACTURA al endpoint, pero el endpoint espera el uuid de la FE row → 404 siempre. La página renderiza "FE no generada" correctamente (no es bug funcional), pero el ruido en Network es confuso.
2. **`/reporteria/financiera` sin branch selector con search** y sin indicador de qué sucursal está mostrando. El usuario quiere un picker inline (similar al `SucursalPicker` que ya existe) con buscador y la sucursal activa visible.
3. **Diseño del componente "Facturas" distinto al de los demás** (e.g. `Reporteria` operacional sí muestra `({branchName})` en el subtítulo; `ReporteriaFinanciera` no).
4. **Dashboard `/dashboard` con sucursal seleccionada**: la card "Facturas" no muestra ninguna factura activa ni tiene link al módulo de facturas. Las otras cards (Usuarios, Cupos, Tarifas, Reportería) SÍ tienen `to` + `linkHint`.

## What changes

### BE (1 commit)

- `backend/.../api/v1/facturacion.py` `get_factura_electronica`: aceptar query param `?uuid_factura=`. Si está presente, llamar `repo_factura_electronica.buscar_factura_electronica_por_factura(session, uuid_factura=X)` (helper ya existe, repo line 164). Path param (`/{uuid}`) se mantiene para no romper consumidores existentes.

### FE (3 commits)

- `apps/web_admin/src/features/facturacion/api/facturacionAdminApi.ts`: añadir `fetchFacturaElectronicaByFacturaUuid(uuid_factura)`. `useFacturaDetalle.ts` usa la nueva función.
- `apps/web_admin/src/components/branch-selector/BranchPickerInline.tsx` (NEW): dropdown Radix con Input search encima. Reutiliza `BranchOption` (uuid, nombre). Patrón visual: `SucursalPicker` (cards) + `BranchSelector` (dropdown) → Popover. Expone `value` + `onChange`.
- `apps/web_admin/src/features/reporteria/pages/ReporteriaFinanciera.tsx`: usar `BranchPickerInline` con `selected` de `useSucursal()`. Agregar `({branchName})` en el subtítulo (mismo patrón que `Reporteria.tsx:173-177`).
- `apps/web_admin/src/features/dashboard/pages/Dashboard.tsx`: agregar `to="/reporteria/financiera"` + `linkHint` + `body` (mensaje "Ninguna factura activa" cuando `value === 0`) a la card "Facturas".

### i18n

- `apps/web_admin/src/i18n/locales/es-CO.json`: agregar `dashboard.verFacturas`, `dashboard.facturasEmpty`, `branchPickerInline.searchPlaceholder`.

## Non-Goals

- No se modifica el BE schema de `FacturasRead` (el approach del query param es más liviano que agregar un `uuid_factura_electronica` computed field).
- No se reemplaza `BranchSelector` (topbar); se agrega `BranchPickerInline` (uso en la página).
- No se modifica el `KpiCard` (el prop `to` ya existe; el `body` se pasa inline).

## Risks

| # | Riesgo | Mitigación |
|---|---|---|
| 1 | El query param del BE introduce un cambio de contrato (ahora acepta `?uuid_factura=`) | Path param se mantiene funcional; el query param es opt-in; 4 tests RED+GREEN del factory regression + 1 test del nuevo path |
| 2 | `BranchPickerInline` no matchea el patrón visual de los demás (cards vs dropdown) | Reutilizar `SucursalPicker` envuelto en `<Popover>` — el contenido es el mismo (cards + search), solo cambia el shell. Si no, dropdown Radix simple (similar al `BranchSelector` actual) con search input encima |
| 3 | El KpiCard podría no aceptar `body` | Revisar KpiCard: `KpiCard` ya acepta `value` (string | number) → pasamos un string descriptivo en lugar de `value`. Si el `linkHint` requiere children, lo agregamos. Revisar en la implementación. |
| 4 | ReporteriaFinanciera.test.tsx match exacto del subtítulo | Test: actualizar el selector a un regex parcial o agregar `data-testid="reporteria-financiera-branch-name"` |

## Decision needed

- (Recomendado) `BranchPickerInline` = Popover wrapping `SucursalPicker` (mismo look que la page de selección inicial, con search). O dropdown Radix simple.

Decision taken: Popover wrapping `SucursalPicker` (mismo look, más coherencia con el chrome).
