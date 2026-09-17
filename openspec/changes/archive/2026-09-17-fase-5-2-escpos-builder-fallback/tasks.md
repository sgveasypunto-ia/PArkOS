# Tasks: HU-F5.2 — `escposBuilder` base y fallback de navegador

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~220 (additions only — pure additive lib + tests + small vitest/setupFile edit) |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (single PR is sufficient) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Pure lib + tests + Buffer polyfill | PR 1 (single) | `cd apps/electron-sucursal && npx vitest run src/lib/print` | N/A — pure functions + jsdom | Delete `src/lib/print/` + revert vitest.config.ts/global.d.ts/test-setup.ts diffs |

## Phase 1: Foundation (Pure-Lib Scaffold)

- [ ] 1.1 Create `apps/electron-sucursal/src/lib/print/` directory.
- [ ] 1.2 Add `buffer@^6.0.3` to `apps/electron-sucursal/package.json` dependencies (npm); run `pnpm install` to lock it.
- [ ] 1.3 Extend `apps/electron-sucursal/src/renderer/test-setup.ts` with `import { Buffer } from 'buffer'; (globalThis as { Buffer: typeof Buffer }).Buffer = Buffer;` (additive — keeps existing F4.x tests passing).
- [ ] 1.4 Modify `apps/electron-sucursal/src/renderer/global.d.ts` to declare `global { var Buffer: typeof import('buffer').Buffer }`.
- [ ] 1.5 Verify `npx vitest run src/lib/validation/placa.test.ts` still passes (regression safety before adding new test file).

## Phase 2: Core Implementation (Templates + Builder + Fallback)

- [ ] 2.1 Create `apps/electron-sucursal/src/lib/print/escposTemplates.ts` with the 4 typed payload interfaces (`EntradaPayload`, `SalidaPayload`, `SalidaMensualidadPayload`, `ReimpresionPayload`) and matching Zod schemas.
- [ ] 2.2 Add inline `formatCOP` helper to `escposTemplates.ts` (with TODO header `SYNCH WITH F2.x`); export it. Resolution path: when F2.x ships `src/lib/format/formatCOP.ts`, switch to re-export from there and remove the inline copy.
- [ ] 2.3 Create `apps/electron-sucursal/src/lib/print/escposBuilder.ts` exporting `build(tipo, payload): Buffer`, the 6 ESC/POS helper constants (`ESC_INIT = Buffer.from([0x1B, 0x40])` etc.), and the two named error classes (`EscposInvalidTipoError`, `EscposPayloadMissingFieldError`).
- [ ] 2.4 Implement the 4 `build*Buffer()` functions in `escposBuilder.ts` (one per `TiqueteTipo`), each composing body + sello via the helper constants and ending with `0x1D 0x56 0x00` partial cut + `0x0A` LF.
- [ ] 2.5 Implement the `TiqueteTipo` discriminated union + `validatePayload(tipo, payload)` dispatcher that runs the Zod schema and throws the right named error class on failure.
- [ ] 2.6 Create `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` exporting `print(tipo, payload)` + the 4 `render*TiqueteHtml(payload)` functions mirroring the buffer layout using semantic `<h1>`/`<p>`.
- [ ] 2.7 Implement `injectPageStyle()` injecting `@page { size: 80mm auto; margin: 2mm }` (DEC-SUC-08 verbatim), call `window.print()` once, and `cleanupPageStyle()` removes the injected `<style>` from `document.head` afterward.

## Phase 3: Tests (Byte Fixtures + End-to-End)

- [ ] 3.1 Create `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` with 5 byte-level fixtures: `esc_init`, `cut_partial`, `esc_center`, `esc_bold_on`, `esc_text_2x`. Each test `expect(buf).toEqual(Buffer.from([...]))`.
- [ ] 3.2 Add `EscposInvalidTipoError` unit test asserting `err.code === 'escpos_invalid_tipo'` and `err.given` carries the bad value.
- [ ] 3.3 Add payload-missing-field test: calling `build('entrada', { foo: 1 })` throws `EscposPayloadMissingFieldError` and `err.issues` is non-empty.
- [ ] 3.4 Add purity test: `vi.spyOn(window, 'print')`; after `build('entrada', validPayload)`, spy never called.
- [ ] 3.5 Add `formatCOP` inline unit test (e.g., `100000` → `$ 100.000` es-CO).
- [ ] 3.6 Create `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.types.test.ts` with 4 end-to-end tests (one per tipo) — each asserts the returned `Buffer` includes init + body + sello (where applicable) + cut, AND that `Buffer.from('ABC123').toString()` is contained in the body for an entrada test.
- [ ] 3.7 Add fallback test for `fallbackBrowser.print('entrada', payload)`: spy on `document.head.appendChild` and `window.print`; assert the `<style>` injection and exactly-one `window.print()` call.

## Phase 4: Static Analysis & Local Verify

- [ ] 4.1 Run `cd apps/electron-sucursal && npx tsc -b` — must exit 0.
- [ ] 4.2 Run `cd apps/electron-sucursal && npx eslint src/lib/print --max-warnings 0` — must exit 0.
- [ ] 4.3 Run `cd apps/electron-sucursal && npx vitest run src/lib/print` — must exit 0 with all 10+ tests passing.
- [ ] 4.4 Run `grep -E "from '(electron|escpos-usb|node:)'" apps/electron-sucursal/src/lib/print/escposBuilder.ts` — must produce NO matches (purity assertion). Doc as a simple shell script in the PR description (not as a CI gate, since gating is out of F5.2 scope).
- [ ] 4.5 Add comment in `escposTemplates.ts` header noting: "formatCOP inline copy — replace with `import { formatCOP } from '@/lib/format/formatCOP'` once F2.x ships that module."

## Implementation Order

T1 → T2 → T3 → T4 (single PR, linearly ordered): foundation (polyfill + scaffold) unblocks the implementation; implementation enables tests; tests gate static analysis. Tasks 2.2 (formatCOP) and 2.4 (sello bytes for salida-mensualidad) are the two design-critical points where reviewers should focus.

## Stretch / Non-Goals

- No CI workflow YAML changes (out of F5.2; gates already covered by F3.x CI).
- No `bridge.imprimir` wire-up — that's F6.x calling F5.2.
- No raster-bit-image of QR/logo — F5.1's bridge decides.
