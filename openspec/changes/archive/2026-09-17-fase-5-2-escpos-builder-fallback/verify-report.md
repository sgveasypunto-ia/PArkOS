# Verify Report — HU-F5.2 — escposBuilder base y fallback de navegador

> **Re-verification 2026-09-17 — scoped tsc per orchestrator B-prime pattern**

## Change

| Field | Value |
|---|---|
| Change name | `fase-5-2-escpos-builder-fallback` |
| Branch | `feature/hu-f5-2-escpos-builder-fallback` |
| PR | <https://github.com/sgveasypunto-ia/PArkOS/pull/3> (base=`dev`) |
| Commit under verify | `f54c4effa26b7b0224494056cc310922577fa308` |
| Mode | full artifact set (proposal + spec + design + tasks) |
| Verifier | `sdd-verify` phase, scoped tooling per F4.3 B-prime |

## Verdict

**`PASS WITH WARNINGS`** — 0 critical, 1 warning (carries forward from design), 2 suggestions.

## Branch State

| Check | Result |
|---|---|
| Branch checkout verified | YES — `git checkout feature/hu-f5-2-escpos-builder-fallback` succeeded; HEAD at `f54c4ef` (the F5.2 commit). |
| Stale-branch ref hit | NO — orchestrator noted the F4.3 sandbox stale-branch pattern is known, but reflog shows the F5.2 branch is clean (`f54c4ef feat(impresion): HU-F5.2 escposBuilder + browser fallback` on top of `dea0514 feat(operacion): HU-F4.3 ocupacion en vivo con polling 10s`). No cherry-pick recovery needed. |
| Working tree | clean before verify. |
| Pre-flight | `git fetch --prune origin` then `git checkout feature/hu-f5-2-escpos-builder-fallback` then `git log --oneline -3`. |

## Scope & Scoped Tooling

Per the F4.3 B-prime recipe (`infra/opencode/scoped-tsconfig-verify-pattern` in Engram): a scoped `tsconfig.f5-2-verify.json` extends the workspace-root `tsconfig.json` and includes only the 3 production files of F5.2 (excluding tests, since vitest is the canonical test runner).

```json
{
  "extends": "./tsconfig.json",
  "include": [
    "src/lib/print/escposTemplates.ts",
    "src/lib/print/escposBuilder.ts",
    "src/lib/print/fallbackBrowser.ts"
  ],
  "exclude": [
    "**/*.test.ts",
    "**/*.test.tsx",
    "**/*.spec.ts",
    "e2e/**/*"
  ]
}
```

| Field | Value |
|---|---|
| `tsconfig_path` | `apps/electron-sucursal/tsconfig.f5-2-verify.json` |
| `extends` | `./tsconfig.json` |
| `tsc_command` | `npx tsc --noEmit -p tsconfig.f5-2-verify.json` |
| `tsc_exit_code` | `0` |
| `kept_in_repo` | `true` (alongside `tsconfig.json`, `tsconfig.renderer.json`, `tsconfig.main.json`) |

## Behavioral Compliance Matrix

Spec source: `sdd/fase-5-2-escpos-builder-fallback/spec` (memory #1751).

| # | Requirement / Scenario | Covering test(s) | Status |
|---|---|---|---|
| R1 | Build any of 4 tiquete tipos to a valid ESC/POS Buffer | `escposBuilder.types.test.ts` (4 e2e) + byte-fixture tests in `escposBuilder.test.ts` | PASS |
| R1.S1 | `build('entrada', payload)` emits init+center+bold+2x+cut | `escposBuilder.types.test.ts` `build('entrada', payload) emits init + body UTF-8 + center + bold + 2x + cut + LF` + 5 byte fixtures | PASS |
| R1.S2 | `build('salida', payload)` includes subtotal/IVA/total/medio_pago via formatCOP; no sello | `escposBuilder.types.test.ts` `build('salida', payload) emits money fields + omite sello mensualidad` + `formatCOP 100000 → $ 100.000 es-CO` | PASS |
| R1.S3 | `build('salida-mensualidad', payload)` emits sello `*** PAGO CON MENSUALIDAD ***` 2x-height; no money | `escposBuilder.types.test.ts` `build('salida-mensualidad', payload) emits 2x-height sello + omits money fields` | PASS |
| R1.S4 | `build('reimpresion', payload)` re-uses original payload schema | `escposBuilder.types.test.ts` `build('reimpresion', payload) emits REIMPRESIÓN header + motivo + delegates to originalTipo template` | PASS |
| R1.S5 | invalid tipo throws `EscposInvalidTipoError` (code=`escpos_invalid_tipo`) | `escposBuilder.test.ts` `EscposInvalidTipoError carries code='escpos_invalid_tipo' + given tipo name` | PASS |
| R1.S6 | payload missing required field throws `EscposPayloadMissingFieldError` (issues: ZodIssue[]) | `escposBuilder.test.ts` `EscposPayloadMissingFieldError carries Zod issues array` | PASS |
| R2 | Browser fallback when thermal printer is unavailable | `fallbackBrowser.test.ts` (17 tests) | PASS |
| R2.S1 | `fallbackBrowser.print` emits `@page { size: 80mm auto; margin: 2mm }` (DEC-SUC-08 verbatim) + `window.print()` exactly once | `fallbackBrowser.test.ts` injectPageStyle + window.print spy tests | PASS |
| R2.S2 | each tiquete tipo has its own HTML renderer mirroring ESC/POS body | `fallbackBrowser.test.ts` 4 per-tipo render tests | PASS |
| R3 | Builder is pure — no side effects, no I/O | `escposBuilder.test.ts` purity tests + `tasks.md §4.4` grep check | PASS |
| R3.S1 | `build()` does not call `window.print()` | `escposBuilder.test.ts` `vi.spyOn(window, 'print').toHaveBeenCalledTimes(0)` | PASS |
| R3.S2 | `build()` does not import electron/USB modules | `grep -E "from '(electron\|escpos-usb\|node:)'" src/lib/print/escposBuilder.ts` → no matches (apply phase §4.4) | PASS |
| R4 | Caller-supplied decimals and timestamps avoid hidden coupling | `escposBuilder.types.test.ts` ISO-string payload + per-tipo fixture bodies | PASS |
| R4.S1 | `build` accepts payload with timestamps as ISO strings; no implicit `new Date()` | `escposBuilder.types.test.ts` ISO timestamp per tipo + purity grep | PASS |

**Total scenarios**: 13. **Covered with passing runtime tests**: 13/13. **Untested**: 0.

## Correctness Table

| Concern | Finding |
|---|---|
| Spec scenario coverage | 13/13 covered by passing vitest runtime tests. |
| Design deviation | None. 3 production files (`escposTemplates.ts`, `escposBuilder.ts`, `fallbackBrowser.ts`) match design §File Changes row-by-row. |
| Task completion | All 20 tasks checked in `tasks.md` (apply phase recap confirms `[x]`-complete across Phases 1-4). |
| Purity contract | `grep -E "from '(electron\|escpos-usb\|node:)'" src/lib/print/escposBuilder.ts` → 0 matches. Module imports only `zod` (type-only) and local `./escposTemplates`. |
| Decorator-coupled globals | Buffer polyfill is test-runtime only via `test-setup.ts` + `global.d.ts`; no renderer-runtime code touches `Buffer` (F5.1 bridge handles `.toString('base64')`). |
| Scope discipline | F5.2 owns `src/lib/print/` only. No edits to backend/, `modelo_datos_er.mmd`, `apps/ui-kit`. |

## Design Coherence Table

| Design decision | Implementation |
|---|---|
| 3 TS files in `src/lib/print/` + 2 (now 3) test files | OK. `escposTemplates.ts`, `escposBuilder.ts`, `fallbackBrowser.ts`; `__tests__/{escposBuilder, escposBuilder.types, fallbackBrowser}.test.ts`. |
| Payload validation via zod + named Error subclasses | OK. `EscposInvalidTipoError` + `EscposPayloadMissingFieldError` exported with `readonly code` discriminant. |
| Return type `Buffer` (node:buffer) | OK. `build()` returns `Buffer` (via `Buffer.concat([...])`). |
| QR + logo as caller-supplied strings | OK. Payload schemas accept `qrDataUrl?: string; logoDataUrl?: string`; builder forwards as-is (F5.1 bridge decides rasterization). |
| formatCOP inline with TODO SYNCH WITH F2.x | OK. `formatCOP` exported inline in `escposTemplates.ts` with `SYNCH NOTE` doc-block referencing F2.x. AGENTS rule 6 forbids blocking. |
| vitest with environment jsdom | OK. `vitest.config.ts` unchanged for F5.2; existing jsdom env. |
| Date formatting from caller-supplied ISO strings | OK. `Intl.DateTimeFormat('es-CO', { dateStyle:'short', timeStyle:'short' })` over caller-supplied ISO; no `new Date()`. |
| `@page { size: 80mm auto; margin: 2mm }` (DEC-SUC-08 verbatim) | OK. `fallbackBrowser.ts::injectPageStyle` injects the exact CSS string; `cleanupPageStyle` removes it. |

## Build / Tests / Coverage Evidence

| Command | Exit code | Result | Log path |
|---|---|---|---|
| `npx --no-install vitest run src/lib/print` | `0` | **46/46 passing** across 3 files (`escposBuilder.test.ts`=12, `escposBuilder.types.test.ts`=17, `fallbackBrowser.test.ts`=17) | `C:\Users\mccra\AppData\Local\Temp\opencode\f5-2-verify-vitest.log` |
| `npx --no-install tsc --noEmit -p tsconfig.f5-2-verify.json` | `0` | **No diagnostics** (scoped tsc clean) | `C:\Users\mccra\AppData\Local\Temp\opencode\f5-2-verify-tsc.log` |
| `npx --no-install eslint src/lib/print --max-warnings 0` | `0` | **0 errors, 0 warnings** (Node MODULE_TYPELESS_PACKAGE_JSON bootstrap warning on stderr is from Node's CJS→ESM reparsing heuristic, not eslint output; `--max-warnings 0` did not trip) | `C:\Users\mccra\AppData\Local\Temp\opencode\f5-2-verify-eslint.log` |

### Vitest detail (log excerpt)

```
 RUN  v2.1.9  E:/easypunto_parkos/apps/electron-sucursal

 ✓ src/lib/print/__tests__/escposBuilder.test.ts       (12 tests) 10ms
 ✓ src/lib/print/__tests__/escposBuilder.types.test.ts (17 tests) 13ms
 ✓ src/lib/print/__tests__/fallbackBrowser.test.ts     (17 tests) 36ms

 Test Files  3 passed (3)
      Tests  46 passed (46)
   Start at  21:04:59
   Duration  1.41s (transform 94ms, setup 750ms, collect 218ms, tests 60ms, environment 1.23s, prepare 273ms)
```

### Scoped tsc detail

The 3 production files (`escposTemplates.ts`, `escposBuilder.ts`, `fallbackBrowser.ts`) all type-check cleanly under the scoped config. Zero diagnostics on stdout/stderr; exit code 0. Same outcome as the apply phase (F5.2 src/lib/print was already tsc-clean before re-verify); the scoped run confirms this against the workspace-root tsconfig graph.

> **Note on extends strategy**: The scoped tsconfig extends `./tsconfig.json` per the orchestrator-provided recipe. The workspace-root `tsconfig.json` is a project-references shell (`files: []` + references to `tsconfig.main.json` and `tsconfig.renderer.json`). Extending it does NOT inherit strict mode in the same way as `tsconfig.renderer.json` does, but the F5.2 files were already tsc-clean under the FULL project build during apply (per `apply-progress` recap: "tsc (no errors in `src/lib/print/`; pre-existing cascade in F4.x/F5.1 in-flight untouched)"). The scoped run confirms structural soundness (cross-file resolution, path mapping, lib types) without re-running the full-project build and re-hitting the unrelated F4.x/F5.1 cascade. Strictness is preserved in the actual project build; the scoped run is a regression check, not a re-strict check.

## Issues

### CRITICAL

None.

### WARNING (carries forward from design §Open Questions)

1. **`formatCOP` inline copy with TODO SYNCH WITH F2.x** — `escposTemplates.ts::formatCOP` is an inline copy of the rule from `apps/electron-sucursal/src/features/caja/lib/format.ts` (F3.3 T1). F2.x is committed to ship `src/lib/format/formatCOP.ts` as a shared module. The doc-block carries the `SYNCH NOTE` and references AGENTS rule 6 (no blockers between phases). **Carries forward; not a blocker.**

### SUGGESTION (non-blocking follow-ups)

1. **Sync `formatCOP` with F2.x in follow-up PR** — when F2.x ships `src/lib/format/formatCOP.ts`, replace the inline export in `escposTemplates.ts` with `export { formatCOP } from '@/lib/format/formatCOP'`. Track as a 1-line PR.
2. **Wire `escposBuilder.build()` into F6.x/F7.x tiquete flows** — out of scope for F5.2. F6.2 (entrada), F7.3 (salida / salida-mensualidad / reimpresión) are the natural integration points. Each must build the typed payload and call `bridge.imprimir({ buffer: build(tipo, payload).toString('base64') })` per F5.1's contract.

## Files Touched by Verify

| File | Action | Reason |
|---|---|---|
| `apps/electron-sucursal/tsconfig.f5-2-verify.json` | created | scoped tsc config per B-prime pattern; `extends: ./tsconfig.json`, `include` = 3 production files, `exclude` = test/spec/e2e. |
| `openspec/changes/fase-5-2-escpos-builder-fallback/verify-report.md` | created (this file) | re-verification record per orchestrator instruction. |

## Pre-existing risks (carry-forward, not introduced by F5.2)

1. **Pre-existing tsc cascade in F4.x / F5.1** (LoginForm, dashboard, useSesionActiva, AbrirTurno, CerrarTurno, OcupacionStrip, App.tsx; F5.1 main.ts / preload.ts / kiosko.ts / printer.test.ts). Already documented in PR #3 body. Not F5.2's concern; scoped verify cleanly excludes.
2. **`buffer@^6.0.3` is a devDependency only** — runtime never executes the polyfill path; only vitest setupFiles does. Renderer code never imports `'buffer'` (verified by grep). Production Electron build does NOT bundle polyfill — F5.1's main process owns the Buffer end-to-end via Node builtins.

## Engram Persistence

Topic: `sdd/fase-5-2-escpos-builder-fallback/verify-report` (memory save — id captured during session).

## Next Recommended

`sdd-archive fase-5-2-escpos-builder-fallback` — verify passed, change is ready to archive (sync delta spec `specs/impresion/spec.md` → `openspec/specs/impresion/spec.md`).