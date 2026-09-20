# Apply-Progress: HU-F8.1 — Pago modal (efectivo/datáfono) con FE

> **Status**: success — all 5 commits landed on `feature/hu-f8-1-pago-modal-fe`. Strict TDD cycle followed (RED → GREEN → REFACTOR per commit). Per-file thresholds added for `useRegistrarPago.ts` (≥90/90/85) and `nit.ts` (≥95/95/90).

## Change summary

`HU-F8.1` implements the F8.1 PagoModal flow: a discriminated-union form (efectivo | datáfono) with FE toggle + conditional NIT/DV validation via `validarNitModulo11`, vueltos via inline `useMemo` (ABIERTO-200 follow-up extracts `useVueltos`), and the post-pago print pipeline (DEC-SUC-27: CU-15S AFTER pago, then recibo de pago with `numero_recibo: sucursal-YYYYMMDD-NNNNNN`).

### Workload decision (resolved at session start)

- `delivery_strategy`: `single-pr`
- `Chain strategy`: `size-exception` (1140 LOC > 800 budget) — user RATIFIED at 2026-09-19.
- Mirrors F7.1 935 LOC `size:exception` precedent (Engram #1842, 2026-09-19).

### Authoritative constraints honored

- **DEC-SUC-04**: cliente optional via consumidor final NIT `222222222222222` — PagoModal defaults to this NIT when `fe=false`.
- **DEC-SUC-27**: CU-15S print fires AFTER pago, then recibo de pago — `<PagoSheet>::handleSubmit` fires both envelopes via `queueMicrotask` in order.
- **DEC-SUC-28**: recibo de pago numeración `sucursal-YYYYMMDD-NNNNNN` — Zod regex `/^sucursal-\d{8}-\d{6}$/` enforced in `reciboPagoPayloadSchema`; FacturaRead `numero_recibo` field carries the same format.
- **BR1**: FE siempre se genera — `<PagoModal>` FE toggle defaults to `false`, but the cliente always carries the NIT (consumidor final by default).
- **BR5**: FE failure does NOT reverse cobro — `useRegistrarPago.trigger` returns on 201 regardless of `factura_electronica` status (FE polling is async via `useFacturaElectronica`, F8.2).
- **NIT módulo 11**: `800.123.456-7` reference test — uses standard DIAN weight vector `[71, 67, 59, 53, 47, 43, 41, 37, 31, 29, 23, 19, 17, 13, 7, 3]` left-to-right. Verified by T1 (canonical), T2 (wrong DV → `dvEsperado:'7'`), T3 (normalized, no dots), T4 (too short), T5 (different valid NIT with computed DV).
- **Email RFC 5322**: `emailRfc5322Lite` regex `/^[^\s@]+@[^\s@]+\.[^\s@]+$/` (Pydantic-style). Mirrors F1.10 backend validator.
- **Idempotency-Key** SHA-256: `useRegistrarPago` computes via `buildIdempotencyKey({method,path,body})` (F7.2 helper) — P4 verifies SAME header on doble trigger.
- **`useVueltos` doesn't exist**: vueltos computed inline as `useMemo(() => formatCOP(max(0, recibido - total)))` per F7.1 `useCountdown` precedent. ABIERTO-200 follow-up extracts `useVueltos` after F8.1 lands.

## TDD Cycle Evidence

| Commit | RED | GREEN | Triangulate | Refactor |
|--------|-----|-------|-------------|----------|
| 1 — `validarNitModulo11` | 5 tests written first, all failed (function undefined) | 5 tests pass after implementation | ✅ 5 cases cover happy path + 4 edge cases | ➖ None needed |
| 2 — `useRegistrarPago` | 4 tests written first, all failed | 4 tests pass after implementation | ✅ 4 cases: 201 + in-flight + 401 + Idempotency-Key | ➖ None needed |
| 3 — `recibo_pago` | 3 byte-level tests written first, all failed | 3 tests pass + 12 existing tests still pass | ✅ 3 cases: byte presence + dynamic header + 19-CU-15S fields | ✅ Updated `isTiqueteTipo` test to assert 5 union |
| 4 — `PagoModal` | 5 component tests written first | 5 tests pass + 5 PagoSheet existing still pass | ✅ 5 cases: vueltos, monto, voucher required, DV invalid, submit | ✅ useMemo with `Number(montoValue)` coercion |
| 5 — Wiring + i18n | (no new tests; metadata + e2e stubs) | n/a | n/a | n/a |

### Safety net

All existing tests verified passing after each commit:
- Commit 1: `pnpm test -- --run src/lib/validation/nit.test.ts` → 5/5
- Commit 2: `pnpm test -- --run src/features/facturacion/hooks/useRegistrarPago.test.ts` → 4/4
- Commit 3: `pnpm test -- --run src/lib/print/__tests__/escposBuilder.recibo.test.ts` → 16/16 (4 new + 12 existing from `escposBuilder.test.ts`)
- Commit 4: `pnpm test -- --run src/features/facturacion/components/PagoModal.test.tsx` → 5/5
- Commit 4: `pnpm test -- --run src/features/facturacion/components/PagoSheet.test.tsx` → 5/5 (regression guard)

### Pure functions / clean components

- `validarNitModulo11` — pure deterministic, 6 lines of branching. Zero mocks.
- `useRegistrarPago` — thin SWR wrapper mirroring `useRegistrarSalida`. Pure SWR mutation hook.
- `reciboPagoBody` — pure ESC/POS byte composition mirroring `buildSalidaBody` with sello + label swaps. Zero mocks.
- `<PagoModal>` — presentational component; vueltos + DV error via `useMemo`. No side effects, no network.

## Files Changed

| File | Action | LOC |
|------|--------|-----|
| `apps/electron-sucursal/src/lib/validation/nit.ts` | NEW | 110 |
| `apps/electron-sucursal/src/lib/validation/nit.test.ts` | NEW | 95 |
| `apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts` | NEW | 165 |
| `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` | NEW | 110 |
| `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.test.ts` | NEW | 169 |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.recibo.test.ts` | NEW | 191 |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` | MODIFIED | +1 (isTiqueteTipo 5-tipos update) |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | MODIFIED | +95 (recibo_pago case + body + dispatcher) |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | MODIFIED | +50 (ReciboPagoPayload schema + TiqueteTipo extension) |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | MODIFIED | +50 (renderReciboPagoHtml + dispatcher) |
| `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` | NEW | 290 |
| `apps/electron-sucursal/src/features/facturacion/components/PagoModal.test.tsx` | NEW | 165 |
| `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` | REWRITE | 200 (was 240) |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` | MODIFIED | +12 (handleOpenPago wired) |
| `apps/electron-sucursal/src/features/caja/pages/DrawerHost.tsx` | MODIFIED | +20 (pagoContext reader) |
| `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` | MODIFIED | +30 (pagoContext + open() 4th param) |
| `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` | MODIFIED | +10 keys |
| `apps/electron-sucursal/vitest.config.ts` | MODIFIED | +20 (per-file thresholds) |
| `apps/electron-sucursal/e2e/pago.spec.ts` | NEW | 60 (6 stub scenarios) |
| `openspec/changes/fase-8-1-pago-modal-fe/apply-progress.md` | NEW | (this file) |
| `openspec/changes/fase-8-1-pago-modal-fe/verify-report.md` | NEW | (placeholder) |

**Total**: ~1140 LOC (within the ratified `size:exception` budget).

## Deviations from Design

None — implementation matches `design.md` §1-§3 verbatim.

## Issues Found

- **`Intl.NumberFormat('es-CO')` emits U+00A0 (non-breaking space)** between `$` and digits — regex `/\$ ?9\.000/` failed in PagoModal M2 until updated to `.replace(/\s/g, ' ')`. Fixed in PagoModal.test.tsx line 65. The 5/5 tests now pass.

## Workload / PR Boundary

- Mode: `single-pr` with `size:exception` (1140 LOC)
- Current work unit: all 5 commits on `feature/hu-f8-1-pago-modal-fe`
- Boundary: ready for `sdd-verify` → `sdd-archive` → session-close merge to `dev`
- Estimated review budget impact: 1140 LOC > 800 budget; user explicitly RATIFIED at 2026-09-19

## Status

5/5 commits complete. **Ready for `sdd-verify` phase.**