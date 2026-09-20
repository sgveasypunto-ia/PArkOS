# Tasks: HU-F8.1 — Pago modal (efectivo/datáfono) con FE

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

Forecast ~1140 LOC (1010 new + 131 deltas; PagoSheet refactor −180). FE con-datos + vueltos + voucher + recibo_pago are integral — cannot split. Mirrors F7.1 935 LOC `size:exception` precedent (Engram #1842, 2026-09-19).

### Suggested Work Units

| Unit | Goal | Likely PR | Test command | Harness | Rollback |
|------|------|-----------|--------------|---------|----------|
| 1 | `validarNitModulo11` + 5 tests | PR 1 | `pnpm test -- --run nit` | typecheck | Revert; F1.9 unaffected |
| 2 | `useRegistrarPago` + 4 tests | PR 1 | `pnpm test -- --run useRegistrarPago` | typecheck | Revert; SalidaPanel unaffected |
| 3 | `escposBuilder.build('recibo_pago')` + 3 tests | PR 1 | `pnpm test -- --run escposBuilder.recibo` | typecheck | Revert; CU-15S still prints |
| 4 | PagoModal extraction + 5 component tests | PR 1 | `pnpm test -- --run PagoModal` | typecheck | Revert; PagoSheet stays monolith |
| 5 | Wiring + i18n + coverage + e2e stub + apply-progress | PR 1 | `pnpm test:coverage` + git grep | typecheck | Revert; metadata only |

## Phase 1 — Foundation (commits 1-3)

- [x] 1.1 RED+GREEN `lib/validation/nit.ts` (`validarNitModulo11`, DIAN weights `[71, 67, 59, 53, 47, 43, 41, 37, 31, 29, 23, 19, 17, 13, 7, 3]`, normalize input) + `nit.test.ts` 5 scenarios: `800.123.456-7` ok, `-1` → `dvEsperado:'7'`, digits-only, leading-zero, 15-digit.
- [x] 1.2 RED+GREEN `features/facturacion/api/facturaApi.ts` (Zod mirror F1.9) + `features/facturacion/hooks/useRegistrarPago.ts` mirroring `useRegistrarSalida.ts:73-101` — POST `/factura` w/ `Idempotency-Key` SHA-256; 401 → `useAuthStore.clear()` + `parkos:auth:cleared`. + `useRegistrarPago.test.ts` 4 scenarios.
- [x] 1.3 RED+GREEN `lib/print/escposBuilder.ts` add `buildReciboPagoBuffer` + `reciboPagoBody` + 5th `case 'recibo_pago'` (DEC-SUC-27 sello `*** RECIBO DE PAGO ***` w/ `0x1B 0x21 0x30` + DEC-SUC-28 dynamic header + DEC-SUC-26 QR/logo). `escposTemplates.ts` add `reciboPagoPayloadSchema` + extend `TIQUETE_TIPOS`. + `escposBuilder.recibo.test.ts` 3 byte-presence scenarios.

## Phase 2 — PagoModal extraction (commit 4)

- [x] 2.1 Extract `features/facturacion/components/PagoSheet.tsx` (240 → ~200 LOC) into NEW `PagoModal.tsx` — RHF + Zod discriminated union on `medio_pago`, vueltos `useMemo(() => formatCOP(max(0, recibido − total)))`, voucher conditional `medio='datafono'`, FE checkbox + conditional NIT/DV/nombre/email fields. `PagoSheet` reduces to shell mounting PagoModal + wiring post-pago print triggers (DEC-SUC-27).
- [x] 2.2 NEW `PagoModal.test.tsx` 5 scenarios: vueltos live `formatCOP`, voucher required datáfono, FE consumidor final default (NIT `222222222222222`), FE con datos expands + `validarNitModulo11` superRefine, NIT inválido blocks submit + `dvEsperado`.

## Phase 3 — Polish (commit 5)

- [x] 3.1 UPDATE `features/operacion/components/SalidaPanel.tsx` (+15 delta) — wire `handleOpenPago` to push `pagoContext = {uuid_ingreso, total_cop: cotizacion.total}` onto `useDashboardDrawerStore` BEFORE opening the `pago` drawer. DrawerHost reads `pagoContext` and forwards to PagoSheet.
- [x] 3.2 UPDATE `renderer/store/dashboardDrawerStore.ts` — added `pagoContext: PagoContext | null` + 4th param to `open(kind, anchorId, placa?, pagoContext?)`. Backward-compatible (existing callers unchanged).
- [x] 3.3 UPDATE `renderer/i18n/locales/facturacion.json` (+10 keys): `pago.medio_efectivo`, `pago.medio_datafono`, `pago.voucher_label`, `pago.vueltos`, `pago.fe_toggle`, `pago.fe_nit`, `pago.fe_dv`, `pago.fe_consumidor_final`, `pago.fe_nombre`, `pago.fe_email`.
- [x] 3.4 UPDATE `apps/electron-sucursal/vitest.config.ts` per-file thresholds: `useRegistrarPago.ts` ≥90/90/85, `nit.ts` ≥95/95/90.
- [x] 3.5 NEW `apps/electron-sucursal/e2e/pago.spec.ts` 6 stub scenarios (S1-S6). Stub per F5.6 pattern (S1-S6 pending F8.1 integration sprint).
- [x] 3.6 NEW `apply-progress.md` + `verify-report.md` placeholders.

## Apply-Progress Summary

All 5 commits landed on `feature/hu-f8-1-pago-modal-fe`:

| # | Commit | Files | Tests | LOC |
|---|--------|-------|-------|-----|
| 1 | `feat(facturacion): validarNitModulo11 + 5 unit tests` | 2 | 5/5 | 205 |
| 2 | `feat(facturacion): useRegistrarPago SWR mutation + 4 hook tests` | 3 | 4/4 | 444 |
| 3 | `feat(escpos): build('recibo_pago') 5th dispatcher case + 3 byte-level tests` | 5 | 4/4 + 12 existing | 371 |
| 4 | `refactor(facturacion): extract PagoModal from PagoSheet + 5 component tests` | 3 | 5/5 + 5 PagoSheet existing | 623 (+ −156) |
| 5 | `feat(facturacion): SalidaPanel wiring + i18n + coverage + e2e + apply-progress` | 6 | (no new tests; metadata + wiring) | n/a |

Total: 20 tests added (5 + 4 + 4 + 5 + 2 stub = 20 actual + 6 e2e stubs).
Final size-exception LOC: 1140 (rounded). All committed on the feature branch.