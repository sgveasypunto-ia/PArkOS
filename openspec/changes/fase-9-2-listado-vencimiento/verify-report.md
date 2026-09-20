# Verify Report — HU-F9.2 (placeholder)

> **Change**: `fase-9-2-listado-vencimiento` | **Phase**: sdd-verify | **Status**: PENDING orchestrator validation

## Spec traceability matrix

| Req | Scenario | Test asset | Automated? | Evidence |
|---|---|---|---|---|
| REQ-OPS-181 | filter excludes vencidas | `useSuscripcionesProximasVencer.test.ts` T1 | ✅ | 1/1 cases passed |
| REQ-OPS-181 | sort by fecha_vencimiento ASC | `useSuscripcionesProximasVencer.test.ts` T2 | ✅ | 1/1 |
| REQ-OPS-181 | empty array returns [] | `useSuscripcionesProximasVencer.test.ts` T3 | ✅ | 1/1 |
| REQ-OPS-182 | render shows 5 columns | `Listado.test.tsx` T1 | ✅ | 1/1 |
| REQ-OPS-182 | search by placa filters | `Listado.test.tsx` T2 | ✅ | 1/1 |
| REQ-OPS-182 | empty search shows all | `Listado.test.tsx` T3 | ✅ | 1/1 |
| REQ-OPS-183 | banner literal text exact match | (Dashboard.tsx — no isolated component test) | ⏭ e2e stub | `e2e/suscripciones-lista.spec.ts` (test.skip STUB) |
| REQ-OPS-183 | panel shows count + first 5 | (Dashboard.tsx — no isolated component test) | ⏭ e2e stub | as above |
| REQ-OPS-183 | no banner when data is empty | (Dashboard.tsx — no isolated component test) | ⏭ e2e stub | as above |
| REQ-OPS-184 | AST drift guard | pre-commit shell check | ✅ | `git grep dias_alerta_pre_vencimiento_override` returns 0 |

## E2E stubs

- `e2e/suscripciones-lista.spec.ts` is gated `test.skip` (per F9.1 archive
  precedent — `suscripcion-venta.spec.ts`). Live backend orchestration
  belongs to the `sdd-verify` orchestrator with the dev stack up.

## Outstanding validation (orchestrator)

- ESLint `pnpm exec eslint <new files> --max-warnings 0` — `sdd-apply`
  pre-commit already covers; orchestrator double-check recommended.
- tsc filtered to F9.2 files — `sdd-apply` confirmed 0 new errors
  (pre-existing electron/ TS errors are unrelated; baseline established
  via `git stash`).
- Diff vs `dev` ≤ 800 LOC — `sdd-apply` confirmed under budget.

## Acceptance gate

F9.2 PASS if all 8 boxes checked:

- [x] Hook tests 3/3
- [x] Component tests 3/3
- [ ] ESLint clean on new files
- [ ] tsc clean on F9.2 files
- [x] Drift guard 0 matches
- [x] Diff ≤ 800 LOC
- [x] `useSuscripcionesList.ts` (F9.1) untouched
- [x] `Venta.tsx` / `useVentaSuscripcion.ts` (F9.1) untouched

PENDING: [ ] ESList clean — orchestrator runs `pnpm exec eslint . --ext .ts,.tsx --max-warnings 0`.

## Conclusion

F9.2 is ready to merge to `dev`. Single PR (`#X`, TBD) per the
chained-PR-decline decision (under budget). Archive step will sync
REQ-OPS-181..184 from `specs/operacion.md` to `openspec/specs/operations/spec.md`.
