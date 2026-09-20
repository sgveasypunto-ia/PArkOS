# Apply Progress: HU-F8.2 — FacturaDetalle FE status + reintento

> **Change**: `fase-8-2-factura-detalle-fe`
> **Branch**: `feature/hu-f8-2-factura-detalle-fe` (off `dev @ 4c969a5`)
> **Phase**: sdd-apply (in progress) | **Strict TDD**: ACTIVE | **Forecast**: ~300 LOC

## Commit Status

| # | Commit | TDD Phase | Tests Added | Status |
|---|---|---|---|---|
| 1 | `feat(facturacion): useFacturaElectronica terminal-state polling + 3 tests` | RED → GREEN | F4/F5/F6 (computeRefreshInterval) | [x] PASS |
| 2 | `feat(facturacion): useReintentarFE mutation + 3 tests` | RED → GREEN | R1/R2/R3 (201/409/401) | [x] PASS |
| 3 | `feat(facturacion): FacturaDetalle page + 5 component tests` | RED → GREEN | T1..T5 (page + role="alert") | [x] PASS |
| 4 | `feat(facturacion): PagoSheet navigate + App.tsx route + i18n + e2e + apply-progress` | mechanical wiring | (no new tests) | [x] PASS |

## TDD Cycle Evidence

| Commit | RED (pre-fix) | GREEN (post-fix) |
|---|---|---|
| 1 | 3 failed: `computeRefreshInterval is not a function` | 6/6 useFacturaElectronica tests pass |
| 2 | `Failed to resolve import "./useReintentarFE"` | 3/3 useReintentarFE tests pass |
| 3 | `Failed to resolve import "./FacturaDetalle"` | 5/5 FacturaDetalle tests pass |
| 4 | n/a (wiring + i18n + e2e stubs) | n/a |

## File Inventory

### NEW files

- `apps/electron-sucursal/src/features/facturacion/hooks/useReintentarFE.ts` (~165 LOC)
- `apps/electron-sucursal/src/features/facturacion/hooks/useReintentarFE.test.ts` (~170 LOC)
- `apps/electron-sucursal/src/features/facturacion/pages/FacturaDetalle.tsx` (~120 LOC)
- `apps/electron-sucursal/src/features/facturacion/pages/FacturaDetalle.test.tsx` (~200 LOC)
- `apps/electron-sucursal/e2e/fe.spec.ts` (~70 LOC, 3 stubs)

### UPDATED files

- `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` (+30 LOC: `computeRefreshInterval` + `TERMINAL_STATES`)
- `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.test.ts` (+50 LOC: F4/F5/F6 tests)
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (+15 LOC: `useNavigate` + post-201 navigate + defensive typeof narrow)
- `apps/electron-sucursal/src/renderer/App.tsx` (+10 LOC: 1 `<Route>` + import)
- `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` (+10 keys: `fe.estado_dian.{pendiente|enviado|aceptado|rechazado}` + `fe.errors.numeracion_agotada`)

### NOT touched (deliberate)

- `backend/**` — F1.10 owns; **zero backend changes** in F8.2
- `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` — F8.1 owns
- `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` — F8.1 owns
- `apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts` — `factura_electronica: z.unknown()` carry-forward (**ABIERTO-F8.2-01** follow-up for F8.3/F8.x)
- `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` — keeps inline `parkosFetch` for Dashboard mount (panel reuses old path); FacturaDetalle uses `useReintentarFE` directly via the page

## Drift Anchors

- `useReintentarFE` mirrors `useRegistrarSalida.ts:73-101` (F7.2) + `useRegistrarPago.ts:73-101` (F8.1): `useSWRMutation` + `Idempotency-Key` SHA-256 + 401 clear + 409 typed error.
- `computeRefreshInterval` is the only refreshInterval form (no constant `30_000`).
- `useParams<{uuid: string}>()` is the canonical UUID source (no `useRouteMatch` legacy).

## Pre-Merge Gate (post-apply)

- [x] `pnpm test -- --run useFacturaElectronica useReintentarFE FacturaDetalle PagoSheet` passes 19 tests (6+3+5+5)
- [ ] `pnpm typecheck` exits 0 (verified separately)
- [ ] `pnpm lint --max-warnings 0` exits 0
- [ ] `git diff --stat origin/dev` ≤ 800 LOC (forecast ~300)
- [ ] `pnpm test:e2e fe.spec.ts` passes 3 stubs (sandbox F.6 caveat)
- [ ] All 4 phases marked `[x]` in `tasks.md`
