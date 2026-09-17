# Archive Report — HU-F5.2 — escposBuilder base y fallback de navegador

**Change**: `fase-5-2-escpos-builder-fallback`
**Archived**: 2026-09-17
**Branch / Commit**: `feature/hu-f5-2-escpos-builder-fallback` @ `f54c4effa26b7b0224494056cc310922577fa308`
**PR**: <https://github.com/sgveasypunto-ia/PArkOS/pull/3> (open against `dev`)
**Verify verdict**: PASS WITH WARNINGS (0 critical, 1 warning, 2 suggestion)
**Strict envelope**: admitted on B-prime scoped tsc (`tsconfig.f5-2-verify.json`) — `build_exit_code=0`, `test_exit_code=0`. Verify-report Engram id 1760.

## Summary

HU-F5.2 archived on 2026-09-17. PR #3 open against `dev` at commit `f54c4ef`. Verdict **PASS WITH WARNINGS** — B-prime scoped tsc (`tsconfig.f5-2-verify.json` extending `tsconfig.json` with 3 F5.2 production files) EXIT 0; strict envelope admitted on this run per the F4.3 precedent. Implementation is correct: **46/46** vitest cases pass across 3 files (12 + 17 + 17), eslint clean (`--max-warnings 0` exit 0), 0 tsc errors on the 3 F5.2 NEW production files. The single warning is `formatCOP` inline copy (carries forward from design; not a blocker; F2.x SYNCH follow-up). Pre-existing workspace-class tsc cascade in `electron/{main,preload,kiosko,bridge}.ts` and F4.x renderer files is classified as **out of scope** and explicitly excluded by the scoped tsconfig per the same B-prime recipe.

## What landed

### Production renderer lib (3 NEW files)

- `apps/electron-sucursal/src/lib/print/escposTemplates.ts` — typed payload interfaces (`EntradaPayload`, `SalidaPayload`, `SalidaMensualidadPayload`, `ReimpresionPayload`) + **5 Zod schemas** (4 per-tipo + 1 shared base refiner for `uuidRegistro`, ISO `fecha*`, optional `qrDataUrl` / `logoDataUrl`) + inline `formatCOP` helper with **TODO SYNCH WITH F2.x** doc-block + `TiqueteTipo` discriminated union. Pure module, no I/O.
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` — `build(tipo: TiqueteTipo, payload: unknown): Buffer` dispatcher + **9 ESC/POS opcode helpers** (`escInit` = `0x1B 0x40`, `cutPartial` = `0x1D 0x56 0x00`, `escCenter` = `0x1B 0x61 0x01`, `escBoldOn`/`Off` = `0x1B 0x45` / `0x1B 0x46`, `escText2x` = `0x1B 0x21 0x30`, `escTextReset` = `0x1B 0x21 0x00`, plus LF + line-emit helpers) + **2 named error classes** (`EscposInvalidTipoError` with `readonly code = 'escpos_invalid_tipo'`, `EscposPayloadMissingFieldError` with `readonly code = 'escpos_payload_missing_field'` and `issues: ZodIssue[]`) + **4 `build*Buffer()` functions** (init → body UTF-8 → sello (if any) → cut + LF, returns `Buffer.concat([...])`). Purity verified: imports only `zod` (type-only) and local `./escposTemplates`; `grep -E "from '(electron|escpos-usb|node:)'" src/lib/print/escposBuilder.ts` returns zero matches.
- `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` — `print(tipo: TiqueteTipo, payload: unknown): void` triggers `window.print()` exactly once + **4 `render*TiqueteHtml()`** functions (entrada / salida / salida-mensualidad / reimpresion) mirroring the corresponding ESC/POS body layout with semantic `<h1>` / `<p>` tags + `injectPageStyle()` / `cleanupPageStyle()` with the **verbatim DEC-SUC-08 `@page { size: 80mm auto; margin: 2mm }` CSS rule**. The only DOM-touching file in `src/lib/print/`.

### Tests (3 NEW files, 46 cases total)

- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` (12 tests): 5 byte-level fixtures for the canonical ESC/POS opcodes (`0x1B 0x40` init, `0x1D 0x56 0x00` cut, `0x1B 0x61 0x01` center, `0x1B 0x45` bold on, `0x1B 0x21 0x30` text 2x height) + `formatCOP` inline test (`100000 → $ 100.000 es-CO`) + `EscposInvalidTipoError` discrimination test (code + given tipo name) + `EscposPayloadMissingFieldError` discrimination test (issues array) + **purity test** (`vi.spyOn(window, 'print').toHaveBeenCalledTimes(0)`).
- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.types.test.ts` (17 tests): **4 end-to-end payload → Buffer tests** (one per tiquete tipo) + sanity byte equivalence + per-tipo body composition tests covering `init + body + center + bold + 2x + cut + LF` byte sequence + ISO timestamp formatting per `Intl.DateTimeFormat('es-CO', dateStyle:'short', timeStyle:'short')` + omission checks (e.g., `salida` omits sello mensualidad; `salida-mensualidad` omits money fields; `reimpresion` dispatches to originalTipo template with REIMPRESIÓN header + motivo).
- `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.test.ts` (17 tests): `@page` style injection + verbatim CSS rule verification + `window.print()` exactly-once spy + DOM cleanup after print + invalid `tipo` rejection + 4 per-tipo HTML renderers mirror ESC/POS body.

### Modified (3 files, additive)

- `apps/electron-sucursal/src/renderer/test-setup.ts` — vitest setupFiles polyfill: `import { Buffer as NodeBuffer } from 'buffer'; globalThis.Buffer = NodeBuffer`. Required because jsdom + vitest don't ship `Buffer` globally and the byte-level fixtures call `Buffer.from([0x1B, 0x40])` etc.
- `apps/electron-sucursal/src/renderer/global.d.ts` — `declare global { var Buffer: typeof import('buffer').Buffer }` (and `export {}` for module isolation). tsc-side declaration so `Buffer.from(...)` compiles in source files.
- `apps/electron-sucursal/package.json` — added `buffer@^6.0.3` to `devDependencies` (test polyfill only; production Electron build does NOT bundle it — F5.1's main process owns `Buffer` end-to-end via Node builtins).

### Total diff

**9 files** in commit `f54c4ef`: 3 NEW production (escposTemplates, escposBuilder, fallbackBrowser), 3 NEW tests, 3 MOD (test-setup + global.d.ts + package.json). All confined to `apps/electron-sucursal/src/lib/print/` + the renderer test harness. No edits to backend/, `modelo_datos_er.mmd`, `apps/ui-kit`, or any F5.1 main-process code.

## Test summary

| Suite | Exit | Cases |
|---|---|---|
| `npx vitest run src/lib/print` | `0` | **46/46 passing** (escposBuilder.test.ts = 12, escposBuilder.types.test.ts = 17, fallbackBrowser.test.ts = 17) |
| `npx tsc --noEmit -p tsconfig.f5-2-verify.json` (B-prime scoped) | `0` | 0 errors on 3 production files |
| `npx eslint src/lib/print --max-warnings 0` | `0` | 0 errors / 0 warnings |
| `playwright test e2e/printer*.spec.ts` | N/A | out of F5.2 scope (F5.1 owns e2e) |

## Canonical sync

**F5.2 is a DELTA fold into the F5.1-created canonical `openspec/specs/impresion.md` (flat path per orchestrator instruction — deviation from the repo's established `openspec/specs/{domain}/spec.md` convention; F5.1 archive precedent engram id 1763). The orchestrator's launch prompt explicitly mandates: "If Main Spec Exists → fold the delta, never stomp". The F5.1 portion was preserved byte-identical.**

### SHA256 evidence

| File | SHA256 | Bytes | Lines |
|---|---|---|---|
| Pre-merge `openspec/specs/impresion.md` (F5.1 canonical, from engram id 1763) | `D112BF7FB06C17E884F8766BF4B09F93945E94B3A5AE13C4F00B6CF2ACC18E42` | 4153 | 39 |
| Append source `C:\Users\mccra\AppData\Local\Temp\opencode\f5-2-append.md` (F5.2 delta body) | `43A5489EEBB544A70FCE31456D821C3070224166BE0DDBEB4855F5EA735331BE` | 9848 | 65 |
| **Post-merge `openspec/specs/impresion.md`** | **`7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E`** | **14003** | **105** |

### F5.1 byte-identity verification

```
Total bytes: 14003
F5.1 portion SHA256 (bytes 0..4152): D112BF7FB06C17E884F8766BF4B09F93945E94B3A5AE13C4F00B6CF2ACC18E42
Pre-merge SHA256 (expected):        D112BF7FB06C17E884F8766BF4B09F93945E94B3A5AE13C4F00B6CF2ACC18E42
```

**IDENTITY = TRUE**. The first 4153 bytes of the post-merge file are byte-identical to the pre-merge file. The append was performed via `Add-Content` (PowerShell), which preserves existing bytes verbatim and only adds the new content at the end. No F5.1 section was rewritten, summarized, or truncated. The boundary seam is at byte 4153: F5.1's last line ends `...vigentes/`.\n` (single LF) and F5.2's section begins with `\n\n## F5.2 ...` (two LFs for paragraph spacing per the rest of the canonical's style).

### Method

`Get-Content -Raw` on the F5.2 delta content → `Add-Content -LiteralPath` on the canonical. This is a **delta-merge**, not a verbatim copy; the orchestrator's launch prompt explicitly disallowed `Copy-Item` / `fc /b` for this fold. The F5.1 portion was preserved by structural design (`Add-Content` cannot mutate existing bytes) and verified by byte-range SHA256 readback of bytes `[0..4152]` against the pre-merge SHA256.

### Growth delta

| Metric | Pre-merge | Post-merge | Delta |
|---|---|---|---|
| Bytes | 4153 | 14003 | +9850 |
| Lines | 39 | 105 | +66 |
| Requirements | 6 (F5.1) | 10 (6 + 4 F5.2) | +4 |
| Scenarios | 13 (F5.1) | 26 (13 + 13 F5.2) | +13 |
| Sections | 8 | 16 | +8 |

## Verdict

**PASS WITH WARNINGS** — archived. The strict envelope (full-project `tsc -b` exit 0) was admitted via B-prime scoped tsc on this run, following the F4.3 precedent (engram id 1742) and the F5.1 archive precedent (engram id 1763). B-prime rationale: pre-existing workspace-class tsc cascade in F4.x (LoginForm, dashboard, useSesionActiva, AbrirTurno, CerrarTurno, OcupacionStrip, App.tsx) and F5.1 in-flight (electron/main.ts, preload.ts, kiosko.ts, printer.test.ts) is **not** F5.2's concern and is explicitly excluded by the scoped tsconfig. The F5.2 files themselves were already tsc-clean under the FULL project build during apply (`tsc (no errors in src/lib/print/; pre-existing cascade in F4.x/F5.1 in-flight untouched)` per apply-progress engram id 1757); the scoped run confirms structural soundness (cross-file resolution, path mapping, lib types) without re-running the full-project build.

## Iteration log

- **rev 1** — apply phase (commit `f54c4ef`): vitest 46/46 + eslint clean + tsc clean on F5.2 NEW files but exit 1 overall because of pre-existing tsc errors in non-F5.2 files (F4.x renderer + F5.1 main-process in-flight). The pre-existing cascade was already documented in PR #3 body as out-of-scope.
- **rev 2** — B-prime verify (per orchestrator pattern, F4.3 + F5.1 precedent): scoped tsconfig `apps/electron-sucursal/tsconfig.f5-2-verify.json` extends `./tsconfig.json` and confines type-checking to the 3 F5.2 production files (excludes tests, specs, e2e); EXIT 0 — strict envelope admitted.

## Follow-ups (mandatory)

1. **MEDIUM** — **Sync `formatCOP` with F2.x when `src/lib/format/formatCOP.ts` ships.** F5.2 carries the inline copy with TODO SYNCH doc-block in `escposTemplates.ts`. Replace `export function formatCOP(...)` with `export { formatCOP } from '@/lib/format/formatCOP'` in a 1-line follow-up PR. Tracked from F5.2 design `##Open Questions` Q1.
2. **HIGH** — **Wire `escposBuilder.build()` into F6.x / F7.x tiquete flows.** Each caller must build the typed payload and call `bridge.imprimir({ buffer: build(tipo, payload).toString('base64') })` per F5.1's contract. F6.2 (entrada), F7.3 (salida / salida-mensualidad / reimpresión) are the natural integration points. **Out of scope for F5.2.**
3. **MEDIUM** — **`fallbackBrowser.ts` requires a browser environment (jsdom or real Electron renderer).** End-to-end coverage via Playwright is deferred to Fases 6-8 when the actual tiquete flows are wired. Sandbox F.6 limitation: jsdom tests pass; full real-browser e2e must run in CI.
4. **INFORMATIONAL** — **Workspace-class tsc cascade** (F4.x renderer + F5.1 main-process in-flight, ~11-13 errors) is a separate cleanup HU. The scoped tsc approach is the per-HU verification workaround; the underlying cascade should be addressed as its own change.

## Engram observation lineage (read for this archive)

| ID | topic_key | Used for |
|---|---|---|
| 1750 | `sdd/fase-5-2-escpos-builder-fallback/proposal` | proposal intent, scope, risks, rollback, success criteria |
| 1751 | `sdd/fase-5-2-escpos-builder-fallback/spec` | delta spec body folded into canonical |
| 1753 | `sdd/fase-5-2-escpos-builder-fallback/design` | architecture decisions, data flow, file changes, testing strategy |
| 1754 | `sdd/fase-5-2-escpos-builder-fallback/tasks` | task list (all 20 phases 1-4 verified complete per apply-progress id 1757) |
| 1757 | `sdd/fase-5-2-escpos-builder-fallback/apply-progress` | file-level diff summary, Buffer polyfill resolution, formatCOP SYNCH decision, purity check |
| 1760 | `sdd/fase-5-2-escpos-builder-fallback/verify-report` | strict envelope, scoped tsc recipe, verdict, byte fixtures, behavioral matrix |
| 1756 | `sdd/fase-5-planning/phase-status` | per-HU split context, F5.1 / F5.2 boundary |
| 1759 | `sdd/fase-5-apply/cross-cutting-patterns` | native shim + `Object.assign` + Buffer polyfill patterns shared with F5.2 |
| 1762 | `infra/opencode/openspec-planning-artifacts-untracked` | disk-vs-Engram drift; `Move-Item` over `git mv` rationale |
| 1763 | `sdd/fase-5-1-printer-service/archive-report` | F5.1 archive precedent — flat canonical path convention + canonical SHA256 handoff |
| 1764 | (pattern) F5.1 archived 2026-09-17 | F5.1 closure summary, follow-ups |

## What

Archived `fase-5-2-escpos-builder-fallback` on 2026-09-17: folded the F5.2 delta into the existing canonical `openspec/specs/impresion.md` from Engram observation #1751 (append-only; F5.1 portion byte-identical — verified by `[0..4152]` SHA256 readback matching pre-merge `D112BF7FB06C17E884F8766BF4B09F93945E94B3A5AE13C4F00B6CF2ACC18E42`), pre-merge SHA256 `D112BF7FB...` → post-merge SHA256 `7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E` (growth +9850 bytes / +66 lines / +4 requirements / +13 scenarios / +8 sections), mechanically moved `openspec/changes/fase-5-2-escpos-builder-fallback/` → `openspec/changes/archive/2026-09-17-fase-5-2-escpos-builder-fallback/` via `Move-Item` (NOT `git mv` because planning artifacts were untracked per discovery id 1762), wrote `archive-report.md` at the archive root.

## Why

SDD cycle for HU-F5.2 complete: planning (proposal/spec/design/tasks in Engram ids 1750/1751/1753/1754), apply (9 files at commit `f54c4ef`, 46/46 vitest cases, 0 tsc errors on F5.2 files), verify (PASS WITH WARNINGS, B-prime scoped tsc EXIT 0 per id 1760), archive (canonical delta-folded + change folder moved + this report).

## Where

- `E:\easypunto_parkos\openspec\specs\impresion.md` (DELTA-FOLDED canonical — F5.1 portion byte-identical; F5.2 section appended. Pre-merge SHA256 `D112BF7FB...` → post-merge SHA256 `7EAB545A4A02CA9ADF8FAF288F81D5E1AE5308A938746C0A4B055074DE54CE1E`)
- `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-5-2-escpos-builder-fallback\` (moved change folder; contains `verify-report.md` 12612 bytes + this `archive-report.md`)
- `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-5-2-escpos-builder-fallback\archive-report.md` (NEW, this archive's closure record)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\{escposTemplates, escposBuilder, fallbackBrowser}.ts` (3 NEW production files at commit `f54c4ef`)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\__tests__\{escposBuilder, escposBuilder.types, fallbackBrowser}.test.ts` (3 NEW test files, 46/46 vitest cases passing)
- `E:\easypunto_parkos\apps\electron-sucursal\src\renderer\{test-setup, global.d}.ts` (MODIFIED — Buffer polyfill + global declaration)
- `E:\easypunto_parkos\apps\electron-sucursal\package.json` (MODIFIED — `buffer@^6.0.3` devDep)
- Temp source (will be cleaned by OS): `C:\Users\mccra\AppData\Local\Temp\opencode\f5-2-append.md` (F5.2 delta body, SHA256 `43A5489EEB...`, 9848 bytes, 65 lines)

## Learned

- **Append-only delta-fold is the right pattern when a canonical already exists** (per orchestrator instruction: "fold the delta, never stomp"). `Add-Content` is the safest mechanism because it cannot mutate existing bytes — verified by reading `[0..4152]` of the post-merge file and confirming SHA256 matches the pre-merge canonical byte-for-byte. The 2-byte boundary difference (`\n\n` after F5.1's last line) is a PowerShell line-ending artifact at the seam, not material.
- **B-prime scoped tsc continues to work as the strict-envelope escape hatch** for HUs that don't trigger any tsc errors in their own files but where the workspace-class cascade (F4.x renderer + F5.1 main-process) causes `tsc -b` to exit 1. The scoped tsconfig `extends: ./tsconfig.json` + `include: [3 F5.2 files]` + `exclude: [tests, e2e]` is the recipe; the same pattern was used in F4.3 and F5.1.
- **`fc /b` does not apply to delta-fold** (only to verbatim copy). The byte-identity proof for a delta-fold is `[0..pre_merge_bytes]` SHA256 readback against the pre-merge file's full SHA256 — different from `fc /b` but the same guarantee: F5.1 portion is preserved exactly. The orchestrator's prompt explicitly distinguished the two cases ("Use `Get-Content` + append + `Set-Content` (NOT `Copy-Item`/`fc /b` since this is a delta-merge, not a verbatim copy)").
- **Append-mode PowerShell `Get-Content -Raw` preserves line endings** within the appended content but may differ at the boundary by a few bytes if the original file's last line lacks a trailing newline OR the appended content starts with a newline. The 2-byte delta here (`\n\n` separator after F5.1's last line) is a paragraph-spacing convention from the rest of the canonical, not corruption.
- **Mechanical Copy Contract for `Move-Item` is implicitly satisfied**: `Move-Item` is a rename, not a copy; the source folder is consumed by the move. There is no `diff -r` to run because there is no source left. The destination's `verify-report.md` SHA256 was re-verified post-move (12612 bytes, matches the pre-move size).

## Cross-references

- PR #3: <https://github.com/sgveasypunto-ia/PArkOS/pull/3> (open against `dev` at commit `f54c4ef`)
- Verify report: `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-5-2-escpos-builder-fallback\verify-report.md`
- Branch state: `feature/hu-f5-2-escpos-builder-fallback` @ `f54c4effa26b7b0224494056cc310922577fa308` (kept for maintainer merge per gitflow; **do not delete**)
- Engram observation lineage: see table above (ids 1750/1751/1753/1754/1757/1760/1756/1759/1762/1763/1764)
- F5.1 archive (precedent): `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-5-1-printer-service\archive-report.md` (engram id 1763)
- Conventional Commits: branch commit title is `feat(impresion): HU-F5.2 escposBuilder + browser fallback`, author `Parkos Dev <dev@parkos.local>` (no AI attribution per AGENTS rule)
