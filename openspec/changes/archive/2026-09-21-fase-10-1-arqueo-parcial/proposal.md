# Proposal: fase-10-1-arqueo-parcial — Arqueo parcial (auditoria, sin cierre)

## Intent

Operator counts the cash drawer mid-shift, no session close. Live `esperado` vs `reportado`, warning (NOT block) on difference, `alerta descuadre_critico` when `|diferencia|` > `configuracion_tolerancias.tolerancia_efectivo`/`tolerancia_datafono` (absolute, NEVER percentage).

## Phase / Preflight

Fase 10 / HU-F10.1 (first of 3). pace=`auto`, artifact=`hybrid`, `gitflow`, review 800 LOC (HU ≈ 260). Strict-TDD ACTIVE. Branch `feature/hu-f10-1-arqueo-parcial`. Author `Parkos Dev <dev@parkos.local>`. No AI attribution.

## Scope

**In**: Frontend-only delta extending `operations` (backend `POST /caja/arqueo` + `GET /caja/arqueo/resumen` shipped F1.13 / REQ-OPS-091..097). Routed page `/caja/arqueo-parcial` wrapping shipped `<ArqueoSheet>` drawer. Live `esperado = base_vigente + Σ factura_pagos.valor` grouped by `medio_pago`. UI shows `diferencia_cop` (DECISIVE) + `descuadre_pct` (informational). Zod refinement: `observaciones` required client-side when `|diferencia|>0` (backend REQ-OPS-096 accepts `auditoria` without — UI enforces, backend permits). `bridge.imprimir(escposBuilder.build('arqueo', payload))` — T3 adds dispatcher key. e2e `e2e/arqueo.spec.ts` (3 scenarios).
**Out**: Backend (F1.13). Close-session (F10.2). Full-day cierre (F10.3). Cross-branch admin UI.

## Capabilities

**New**: None. **Modified**: `operations` — extend REQ-OPS-091..097 with REQ-OPS-F10.1:1..5 delta (page+Sheet wiring, live diff+alerta, `observaciones` UI refinement, `'arqueo'` ESC/POS, e2e specs).

## Approach

Wrap shipped `<ArqueoSheet>` + `useArqueo` SWR with routed `<ArqueoParcial>` page. Fetch live `esperado` from `GET /caja/arqueo/resumen` (REUSE). `useWatch`+`useMemo` compute `diferencia_cop`/`descuadre_pct`; render shadcn `<Alert variant='warning'>` when touched. Zod refines `observaciones` required when `|diferencia|>0`. On submit, dispatch `bridge.imprimir(escposBuilder.build('arqueo', {...}))`.

## Affected Areas

| Path | LOC | Change |
|---|---|---|
| `apps/electron-sucursal/src/features/caja/pages/ArqueoParcial.tsx` | ~120 (new) | Routed page, live diff, Zod refinement |
| `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx` | ~40 | Live diferencia block + refinement |
| `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts` | ~30 | Field-name align REQ-OPS-091 + ticket helper |
| `apps/electron-sucursal/src/renderer/App.tsx` | ~5 | `/caja/arqueo-parcial` route |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | ~60 | `TiqueteArqueoCampos` + `'arqueo'` key |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | ~30 | `case 'arqueo'` |
| `apps/electron-sucursal/e2e/arqueo.spec.ts` | ~90 (new) | 3 scenarios per AC |
| `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` | small | Keys `diferencia`, `descuadre_pct`, `requiereObservaciones` |

## Risks (ABIERTO drift anchors — carry forward to sdd-spec)

| # | Drift anchor | L | Mitigation |
|---|---|---|---|
| 1 | `useArqueo.submit` uses `efectivo_contado_cop`; REQ-OPS-091.Scenario1 uses `valor_efectivo_reportado`. Silent 422 risk. | H | Spec reconciles field names with `ArqueoCreateV2`; e2e hits real endpoint shape. |
| 2 | AC routed `/caja/arqueo-parcial`; current UX is Sheet drawer from Dashboard F4. | M | Spec decides: route WRAPS drawer (preserves F4 hotkey). |
| 3 | BR1 base configurable al momento del arqueo. `GET /caja/arqueo/resumen` reads `sesion.valor_inicial_efectivo` — vigente base or snapshot? | H | Spec/design calls out: REQ-OPS-097 §3919 formula is `valor_inicial_efectivo + Σ factura_pagos`. If column is vigente base, fine; if snapshot, expose `configuracion_caja.base_efectivo_vigente`. |
| 4 | Justification asymmetry: AC optional in CU; UI refines required on `|diferencia|>0`; backend REQ-OPS-096 accepts `auditoria` without it. | M | UI enforces; backend permits. No divergence in success path. |
| 5 | `'arqueo'` dispatcher key NOT yet in `escposTemplates` union (only `entrada`/`salida`/`recibo_pago`/`reimpresion`). | H | T3 adds dispatcher entry + happy-path byte fixture. |
| 6 | `factura_pagos` immutability: `fn_factura_pagos_inmutable` trigger fires on any UPDATE. | L | Renderer forbids UPDATE; backend single-commit per REQ-OPS-091 §3700. |
| 7 | Hash chain extension: every `arqueo` [A] extends `prod.log_transaccional` per `uuid_sucursal`. Out-of-order e2e could fork. | L | Cloud `hash_chain_verifier_loop` catches forks; e2e is single-shot. |

## Rollback Plan

Revert branch → removes routed page, live-diff Zod refinement, `'arqueo'` dispatcher entry, e2e specs. Backend (F1.13) untouched. No migration. `<ArqueoSheet>` + `useArqueo.submit` remain (MODIFY, not REPLACE).

## Dependencies

HU-F1.13 backend (REQ-OPS-091..097 shipped). `@parkos/ui-kit` `parkosFetch` + `useAuthStore`; shadcn `<Sheet>`/`<Form>`/`<Alert>` (Fase 3). `escposBuilder` + `bridge.imprimir` IPC (F5.1/F5.2 shipped). i18n `caja` namespace (`arqueo` + `arqueoParcial` already exist).

## Atomic Tasks (sdd-tasks; RED→GREEN pairs per strict-TDD)

- **T1**: `<ArqueoParcial>` routed page + live `diferencia`/`descuadre_pct` + `observaciones` refinement.
- **T2**: `useArqueo.submit` field-name alignment with REQ-OPS-091.
- **T3**: `escposTemplates.TiqueteArqueoCampos` + `escposBuilder.case 'arqueo'` + `bridge.imprimir`.
- **T4**: `e2e/arqueo.spec.ts` (3 scenarios) — test-only, after T1+T2+T3 merged.

## Success Criteria

- [ ] `vitest` green: `ArqueoParcial.test.tsx` + `useArqueo.test.ts` (NEW) + `escposBuilder.arqueo.test.ts` (NEW).
- [ ] `pnpm playwright test e2e/arqueo.spec.ts` green (3 scenarios).
- [ ] `pnpm typecheck` + `pnpm lint` green; axe-core zero WCAG 2.1 AA violations.
- [ ] `git merge --no-ff feature/hu-f10-1-arqueo-parcial` → `dev` + `git push origin dev` before session close.

## Next Recommended

`sdd-spec` — extend `openspec/specs/operations/spec.md` with REQ-OPS-F10.1:1..5 delta; resolve drift anchors #1, #3, #5 BEFORE authoring spec text.
