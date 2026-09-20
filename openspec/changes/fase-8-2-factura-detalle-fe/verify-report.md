# Verify Report: HU-F8.2 — FacturaDetalle FE status + reintento

> **Change**: `fase-8-2-factura-detalle-fe`
> **Branch**: `feature/hu-f8-2-factura-detalle-fe` (off `dev @ 4c969a5`)
> **Phase**: sdd-verify (placeholder — filled after sdd-verify runs)
> **Status**: PENDING sdd-verify

## Success Criteria (from proposal §9)

1. [ ] `<FacturaDetalle />` renders estado FE + CUFE if `aceptado` + reintentar button if `rechazado` + 409 banner on `numeracion_agotada`.
2. [ ] `useFacturaElectronica` polling stops on BOTH terminal states (`aceptado | rechazado`); tests F4 + F5 pass.
3. [ ] `useReintentarFE` issues POST with `Idempotency-Key`; 201 returns `{uuid_envio, estado:'pendiente', uuid_envio_padre}`; 409 surfaces `NumeracionAgotadaError`; 401 clears auth (F3.1 invariant).
4. [ ] `PagoSheet.handleSubmit` navigates to `/factura-electronica/<uuid_fe>` after a successful pago where `result.factura_electronica?.uuid` is a string.
5. [ ] `409 numeracion_agotada` banner renders localized copy "Numeración agotada. Contactar proveedor." with `role="alert"` (WCAG 2.1 AA).
6. [ ] `e2e/fe.spec.ts` 3 scenarios pass: estado visible / polling active+stops on terminal / reintentar.
7. [ ] `facturaApi.ts` typing improvement captured as **ABIERTO-F8.2-01** follow-up note in the verification report.
8. [ ] `pnpm typecheck`, `pnpm lint`, `pnpm test`, `pnpm e2e -- fe.spec.ts` exit 0.
9. [ ] axe-core WCAG 2.1 AA: 0 violations on `<FacturaDetalle />`.

## Drift Anchors (enforced by tests)

- `useReintentarFE` MUST mirror `useRegistrarSalida.ts:73-101` (composition: `parkosFetch` + `Idempotency-Key` SHA-256 + 401 clear + 409 typed error).
- `computeRefreshInterval` is the only refreshInterval form (callback, not constant).
- `FacturaElectronicaRetryPanel.tsx` keeps its own inline `parkosFetch` for Dashboard mounts — FacturaDetalle page uses the new hook directly (no double-button).

## ABIERTO-F8.2-01 — Follow-up

`FacturaReadSchema.factura_electronica: z.unknown()` (`api/facturaApi.ts:49`) — F8.2 narrows defensively in `PagoSheet.tsx` via `typeof` checks. F8.3 (reimpresión con costo) or F8.x should tighten to a discriminated-union Zod schema with `{ uuid?: string; estado?: 'pendiente'|'enviado'|'aceptado'|'rechazado' }` payload, removing the `unknown` escape hatch.

## Test Counts (current)

- `useFacturaElectronica.test.ts`: 6 (3 F8.1 + 3 F8.2 F4/F5/F6)
- `useReintentarFE.test.ts`: 3 (R1/R2/R3 — all F8.2)
- `FacturaDetalle.test.tsx`: 5 (T1..T5 — all F8.2)
- `e2e/fe.spec.ts`: 3 stubs (sandbox F.6 — F8.2 integration sprint)

**Total**: 14 unit/component + 3 e2e stubs.
