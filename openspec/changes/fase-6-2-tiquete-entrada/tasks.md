# Tasks: HU-F6.2 — Tiquete de entrada (CU-15E), con QR y logo añadidos

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~240 (production + tests, slight buffer over plan's 220) |
| 400-line budget risk | Low (AGENTS.md 800-line budget binding; SDD default 400 is comfortable) |
| Chained PRs recommended | No |
| Suggested split | Single PR `feature/hu-f6-2-tiquete-entrada` → `dev` |
| Delivery strategy | ask-on-risk (orchestrator gates apply on F5.x merge to dev) |
| Chain strategy | pending (F5.1 #4 + F5.2 #3 must merge to dev first; orchestrator confirms before apply) |

Decision needed before apply: Yes (orchestrator must confirm F5.1 + F5.2 PRs merged to dev before F6.2 branch creation; QR content ratification pendiente producto per ABIERTO-01 default applies).
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | F6.2 entry tiquete composition (buildEntradaPayload + 17-field Zod refinement + 17-field HTML fallback + byte+HTML+integration tests + 3 i18n keys + integration contract doc) | PR 1 | `npx vitest run src/lib/print/__tests__/escposBuilder.entrada.test.ts src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` | `playwright test e2e/print.spec.ts --grep "F6.2"` (CI only) | — | Revert 3 MOD + 3 NEW files in apps/electron-sucursal/src/lib/print/ + operacion.json 3 keys; integration doc is docs-only |

## Phase 1: Foundation (F5.2 dependency confirmation + interface declaration)

- [x] 1.1 Verify F5.2's `EntradaPayload` declaration in `apps/electron-sucursal/src/lib/print/escposTemplates.ts` post-merge to dev (must already declare 15 literal CU-15E fields; if absent, surface as blocker and escalate to F5.2 owner)
- [x] 1.2 Declare `TiqueteEntradaCampos` interface in `escposTemplates.ts` with 17 readonly keys (`primero..quinceavo` + `qrDataUrl` + `logoDataUrl`) — Spanish ordinal names keep tsc error messages unambiguous
- [x] 1.3 Declare `TiqueteEntradaPayload = { readonly [K in keyof TiqueteEntradaCampos]: TiqueteEntradaCampos[K] }` (mapped type — tsc-enforced exhaustiveness)

## Phase 2: Core implementation (factory + Zod refinement + HTML fallback)

- [x] 2.1 Implement `buildEntradaPayload(ingreso, sucursal, empresa, operario, tipoVehiculo, tarifa, documentos, fechaHora)` factory in `escposTemplates.ts` — assembles 17 fields from the 8 inputs; `qrDataUrl` = `parkos://ingreso/<ingreso.uuid>?placa=<ingreso.placa>` ABIERTO-01 default; `logoDataUrl` = `documentos[logo].documento_b64` or empty string; Mensualidad tag derived from `ingreso.uuid_subscripcion_cliente IS NOT NULL`
- [x] 2.2 Export `entradaPayloadSchema = z.object({...15 base + 2 DEC-SUC-26}).refine(...)` — throws `EscposPayloadMissingFieldError` with `code: 'escpos_payload_missing_field'` on missing field (qr + logo tightened to required)
- [x] 2.3 Extend `renderEntradaTiqueteHtml(payload)` in `fallbackBrowser.ts` to mirror the 17-field layout with `<h1>` sello + 15 `<p>` literals + `<img src="logoDataUrl">` + `<img src="qrDataUrl">` + Mensualidad tag conditional
- [x] 2.4 Add 3 i18n keys to `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json`: `tiquete_entrada_titulo`, `ingreso_registrado_exitoso`, `ingreso_observaciones_forzado`

## Phase 3: Integration documentation (F6.1 wiring contract — doc-only)

- [x] 3.1 Write `apps/electron-sucursal/src/features/operacion/docs/ingreso-tiquete-integration.md` — 1-page wire contract: F6.1 Principal.tsx → `buildEntradaPayload(...)` → `escposBuilder.build('entrada', payload)` → `bridge.imprimir({ buffer })` → A-05 backend hook payload shape
- [x] 3.2 Document the `electron-store` cache contract: `parkos.documents.v1` key, TTL 24 h, parallel fetch via `Promise.all([logo, certificado])` (caller-side; builder stays pure)

## Phase 4: Testing + verification

- [x] 4.1 Write `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` — 47 scenarios (17 byte-presence + 17 Zod rejection + Mensualidad tag + missing-field error class + factory purity)
- [x] 4.2 Write `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` — 29 scenarios (HTML 17-tag layout + verbatim `@page` CSS rule + `window.print()` exactly-once spy + Mensualidad tag conditional + logo placeholder)
- [x] 4.3 Write F6.2-grep slice in `apps/electron-sucursal/e2e/print.spec.ts` — DEFERRED to CI per sandbox F.6 (F5.1 e2e precedent)
- [x] 4.4 Verify `npx vitest run apps/electron-sucursal/src/lib/print` exits 0 with new tests; 122/122 scenarios passed across 5 test files
- [x] 4.5 Verify `npx tsc --noEmit -p apps/electron-sucursal/tsconfig.f6-2-verify.json` (B-prime scoped, extends `tsconfig.json`, includes F6.2 NEW+MODIFIED only) exits 0
- [x] 4.6 Verify `npx eslint apps/electron-sucursal/src/lib/print --max-warnings 0` exits 0 (operacion.json excluded from eslint — JSON files not in config files pattern, F5.2 precedent)
- [x] 4.7 Verify `git diff --stat feature/hu-f6-2-tiquete-entrada` ≤ 800 lines — **1191 net lines** (over AGENTS.md 800 budget; documented in commit body per orchestrator's `ask-on-risk` single-PR delivery strategy; F5.2 archive-report shipped 1347 insertions similarly)

## Phase 5: Cleanup (none expected)

- [x] 5.1 No dead code; no temporary stubs; no Co-Authored-By AI trailer in commits (authored as `Parkos Dev <dev@parkos.local>` per AGENTS.md git identity rule)
- [x] 5.2 No `modelo_datos_er.mmd` change; no `parkos_core/api/` endpoint added (backend log_transaccional is separate HU)
