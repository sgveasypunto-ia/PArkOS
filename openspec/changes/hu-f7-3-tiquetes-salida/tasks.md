# Tasks: HU-F7.3 — Tiquetes de salida (CU-15S) y salida-mensualidad (CU-15SM), impresos después del pago

> **Change**: `hu-f7-3-tiquetes-salida` · **Project**: `parkos` (Engram-scoped) · **Phase**: tasks (sdd-tasks) · **Plan contract**: `plan.md` lines 1779–1826 · **Specs**: `openspec/changes/hu-f7-3-tiquetes-salida/specs/operacion/spec.md` (per-change) + `openspec/specs/operations/spec.md` lines 5826–5997 (REQ-OPS-143..145) · **Design**: `openspec/changes/hu-f7-3-tiquetes-salida/design.md` (6 ADRs, 9 file changes, ~424 LOC forecast) · **Renderer-only**: zero backend, zero Alembic, zero SQL.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines (production) | ~254 LOC across 7 files (escposBuilder.ts +40/+25, fallbackBrowser.ts +30/+30, escposTemplates.ts +60 factories, SalidaPanel.tsx +30, PagoSheet.tsx +25, tsconfig.f7-3-verify.json +14) |
| Estimated changed lines (incl. tests) | ~424 LOC (production 254 + tests 170 — `escposBuilder.salida.test.ts`) |
| 400-line budget risk | High (424 > 400 chained-PR threshold; well under 800 per-PR hard cap from `openspec/config.yaml` `rules.tasks`) |
| 800-line PR budget | Under (~424 < 800) |
| Chained PRs recommended | **Yes** (forecast crosses the 400 LOC chained-PR review-budget threshold) — user must choose between **chained-PR split** OR **size:exception single-PR** |
| Suggested split | Option A — single PR `feature/hu-f7-3-tiquetes-salida` with 3 work-unit commits (design default; cross-file contract protects the byte↔HTML field-order coupling). Option B — chained-PR `feature/hu-f7-3-tiquetes-salida-builder` (commits 1+2, ~125 LOC) → `feature/hu-f7-3-tiquetes-salida-wire` (commit 3, ~299 LOC). |
| Delivery strategy | `ask-on-risk` (cached) — orchestrator gates apply on user decision |
| Chain strategy | `gitflow` (cached) — feature-branch-chain available if Option B is chosen |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | CU-15S 19-field contract + factories (ADR-01 + ADR-06 partial) | PR 1 (single-PR track) OR PR 1 (chained track, base = `feature/hu-f7-3-tiquetes-salida-builder`) | `npx vitest run apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts -t "CU-15S"` | N/A — renderer change; byte fixtures + scoped tsc are the gating signal (F5.1/F5.2/F6.x precedent; sandbox F.6 has no USB) | Revert commit 1: `escposBuilder.ts` returns to F5.2 skeleton (`buildSalidaBody` 17-line body), `escposTemplates.ts` removes `buildSalidaPayload` factory. CU-15S byte fixture test from commit 3 still imports factory — would break (mitigated by keeping factory in commit 1). |
| 2 | CU-15SM 15-field contract + `esMensualidad` factory (ADR-01 + ADR-06 partial) | PR 1 (single-PR track) OR PR 1 (chained track, same PR) | `npx vitest run apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts -t "CU-15SM"` | N/A — same rationale as Unit 1 | Revert commit 2: `buildSalidaMensualidadBody` returns to F5.2 13-line body (sello preserved at line 287), `escposTemplates.ts` removes `buildSalidaMensualidadPayload` factory. |
| 3 | HTML mirror + React call-site wiring + byte-fixture tests + B-prime tsconfig (ADR-02 + ADR-03 + ADR-04 + ADR-05 verify gate) | PR 1 (single-PR track) OR PR 2 (chained track, base = Unit-1+Unit-2 branch) | `npx vitest run apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` (full file, both cases) | N/A — same rationale; `bridge.imprimir` call sites are unit-tested via byte fixtures, no runtime harness required | Revert commit 3: `fallbackBrowser.ts` HTML renderers return to F5.2 skeleton, `SalidaPanel.tsx` / `PagoSheet.tsx` revert to PR-3 (`8d733ee`) state, `escposBuilder.salida.test.ts` reverts, `tsconfig.f7-3-verify.json` reverts. Builder and factory (commits 1+2) remain in place — Fase 8 trigger site still missing until F8 lands. |

> **Note on chaining base branch** — under `feature-branch-chain` strategy, PR #1 (`feature/hu-f7-3-tiquetes-salida-builder`) targets the tracker branch `feature/hu-f7-3-tiquetes-salida`. PR #2 (`feature/hu-f7-3-tiquetes-salida-wire`) targets PR #1's branch. Only the tracker merges to `dev`. Under `size:exception` (single PR), the branch `feature/hu-f7-3-tiquetes-salida` carries all 3 commits and merges directly to `dev`.

## Phase 1: Foundation — pre-flight + scoped verification scaffold (no production code)

- [ ] 1.1 Verify F5.1 + F5.2 + F6.1 + F6.2 + `operador-dashboard-hub` are merged to `dev` (commit hashes: `b987cf29`, `f54c4ef`, `2026-09-17T04:06:41Z`, `2026-09-17T03:31:41Z`, `8d733ee`). Surface as blocker if any is missing.
- [ ] 1.2 Sync `dev` and create feature branch: `git fetch --prune origin && git checkout dev && git -c user.name='Parkos Dev' -c user.email='dev@parkos.local' merge --ff-only origin/dev && git checkout -b feature/hu-f7-3-tiquetes-salida` (single-PR) — OR create the tracker + first PR branch under `feature-branch-chain` if user picks that.
- [ ] 1.3 Create `apps/electron-sucursal/tsconfig.f7-3-verify.json` (B-prime scoped tsc per Engram #1742; extends `tsconfig.json`; `include` lists the 5 NEW+MODIFIED production files only; `exclude` masks `**/*.test.ts`, `**/*.test.tsx`, `**/*.spec.ts`, `e2e/**/*`).
- [ ] 1.4 Verify B-prime scaffold compiles against the **pre-change** `dev` baseline: `npx tsc --noEmit -p apps/electron-sucursal/tsconfig.f7-3-verify.json` exits 0 (gating signal before any production code lands).

## Phase 2: Core implementation — builder contracts (CU-15S + CU-15SM)

- [ ] 2.1 Modify `apps/electron-sucursal/src/lib/print/escposBuilder.ts` `buildSalidaBody` (lines 240–273) — apply 7 field-level fixes (ADR-01):
  - Replace `'*** SALIDA ***'` → `'*** TIQUETE DE SALIDA ***'` at line 252 (campo 7 per plan.md line 1794).
  - Insert `utf8('Operario: ' + payload.operario + '\n')` after the régimen block (campo 6).
  - Insert `utf8('Tarifa: ' + formatCOP(payload.tarifaAplicada) + '/hora\n')` after `Folio:` line (campo 9).
  - Insert `utf8('Horario: ' + payload.horarioAtencion + '\n')` after the optional `Poliza RC:` block (campo 19).
  - Insert optional `if (payload.observaciones) lines.push(utf8('Observaciones: ' + payload.observaciones + '\n'))` after `Horario:` (campo 19 subset).
  - Append `utf8(';QR:' + payload.qrDataUrl + '\n')` and `utf8(';LOGO:' + (payload.logoText || 'OK') + '\n')` before `Gracias por su visita.` (campos 20–21, DEC-SUC-26).
- [ ] 2.2 Modify `apps/electron-sucursal/src/lib/print/escposBuilder.ts` `buildSalidaMensualidadBody` (lines 275–301) — apply 4 field-level fixes (ADR-01):
  - Insert `utf8('Tiempo: ' + payload.tiempoTotal + '\n')` between `Salida:` and `Placa:` (campo 13 per plan.md line 1810).
  - Append `utf8(';QR:...')` + `utf8(';LOGO:...')` markers before `Conserve este tiquete como soporte.` (DEC-SUC-26).
  - Insert optional `if (payload.observaciones) lines.push(...)` after `Horario:` (campo 15).
  - Preserve the existing sello `'*** PAGO CON MENSUALIDAD ***'` at line 287 verbatim — **no byte drift**.
- [ ] 2.3 Add factory `buildSalidaPayload(args)` to `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (ADR-06) — derives `tiempoTotal`, computes `subtotal`/`iva`/`total` from invoice, attaches `qrDataUrl` + `logoDataUrl` from `documentos`, requires `medioPago` (post-pago dependency), returns `salidaPayloadSchema.parse(...)`. NO `esMensualidad` flag.
- [ ] 2.4 Add factory `buildSalidaMensualidadPayload(args)` to `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (ADR-06) — derives `tiempoTotal`, attaches QR + logo, sets `esMensualidad: z.literal(true)` discriminator (DEC-SUC-21). NO `subtotal`/`iva`/`total`/`medioPago` fields (CU-15SM has no cobro).
- [ ] 2.5 Run scoped tsc after builder edits: `npx tsc --noEmit -p apps/electron-sucursal/tsconfig.f7-3-verify.json` exits 0; full workspace tsc (`npx tsc -b`) is informational only (pre-existing F5.1 cascade tolerated per F5.x/F6.x precedent).

## Phase 3: Integration — HTML mirror + React call-site wiring

- [ ] 3.1 Modify `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` `renderSalidaHtml` (line 182) — mirror 7 CU-15S fixes in semantic HTML: add `<p>Operario: ...</p>`, `<p>Tarifa: .../hora</p>`, `<p>Horario: ...</p>`, optional `<p>Observaciones: ...</p>`; replace `<h2>*** SALIDA ***</h2>` with `<h2>*** TIQUETE DE SALIDA ***</h2>`; add `<img src="${qrDataUrl}">` + `<img src="${logoDataUrl}">` before footer; `PAGE_RULE` (line 59) reused verbatim.
- [ ] 3.2 Modify `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` `renderSalidaMensualidadHtml` (line 208) — mirror 4 CU-15SM fixes in semantic HTML: add `<p>Tiempo: ...</p>`, optional `<p>Observaciones: ...</p>`; sello `<h2>*** PAGO CON MENSUALIDAD ***</h2>` already correct; add `<img>` tags before footer; preserve `PAGE_RULE`.
- [ ] 3.3 Modify `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (mensualidad-confirm branch) — add `handleMensualidadConfirm` `useCallback` that builds a `SalidaMensualidadPayload` via `buildSalidaMensualidadPayload(...)` and awaits `window.bridge.imprimir({ buffer: escposBuilder.build('salida-mensualidad', payload).toString('base64'), ticketId, uuidRegistro: payload.folio, cut: false })` mirroring `IngresoPanel.tsx:80` try/catch shape. Add `// DEC-SUC-27 immediate clause` anchor comment.
- [ ] 3.4 Modify `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (post-200 branch) — declare `await window.bridge.imprimir({ tipo: 'salida', payload: buildSalidaPayload(...) })` inside `handleSubmit` after `await onSubmit(values)` returns. The post-200 trigger is supplied by Fase 8 (HU-F8.1+); add `// TODO: Fase 8: confirms the post-200 trigger fires here` anchor comment + `// TODO: Fase 8 inserts log_transaccional INSERT here` audit-row anchor per A-05. Payload `medioPago` is caller-supplied from `factura_pagos.medio_pago`.

## Phase 4: Testing — byte-fixture test suite + verification receipts

- [ ] 4.1 Create `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` (~170 LOC per plan.md line 1816, F6.2 `escposBuilder.entrada.test.ts` template):
  - `describe('buildSalidaBuffer — 19 byte-presence scenarios (HU-F7.3)')` with 19 `it()` blocks, one per field label from plan.md lines 1789–1808 (Appendix A Case 1 matrix).
  - `it('emits DEC-SUC-26 QR marker before footer')` + `it('emits DEC-SUC-26 LOGO marker before footer')` — verify `;QR:...` and `;LOGO:...` appear before `Gracias por su visita.`.
  - `it('sello bytes pinned between text-2x opener and reset')` — `Buffer.from([0x1B, 0x21, 0x30])` immediately before `'*** TIQUETE DE SALIDA ***'` UTF-8 bytes; `Buffer.from([0x1B, 0x21, 0x00])` immediately after (REQ-OPS-143 scenario 3).
  - `it('omits Poliza RC: and Observaciones: when both are null')` + `it('still emits Horario: and Resolucion FE:')` — optional-branch guard test.
  - `it('contains no rasterization opcodes outside cutPartial()')` — DEC-SUC-26 purity: no `0x1D` GS prefix outside the trailing `cutPartial` helper.
  - `it('does not call window.print()')` — purity spy.
  - `describe('buildSalidaMensualidadBuffer — 15 byte-presence scenarios (HU-F7.3)')` with 15 `it()` blocks per plan.md line 1810 (Appendix A Case 2 matrix).
  - `it('sello byte sentinel pinned to canonical fixture')` — `Buffer.from([0x1B, 0x21, 0x30, ...'*** PAGO CON MENSUALIDAD ***\n', 0x1B, 0x21, 0x00])` verbatim (plan.md line 1816 canonical assertion).
  - `it('omits Subtotal:, IVA:, TOTAL:, Medio de pago:')` — ausencia-de-cobro test.
  - `it('rejects payload missing esMensualidad: true')` — `EscposPayloadMissingFieldError` (F5.2 R1 + Zod `z.literal(true)`).
  - `it('emits dynamic empresa.nombre as encabezado')` — `payload.empresa.nombre = "Mi Parqueadero XYZ"` → buffer contains literal; NOT corpus-fixed `PARQUEADERO PUBLICO`.
- [ ] 4.2 Verify vitest full-suite passes: `cd apps/electron-sucursal && npx vitest run` — 100% of pre-existing scenarios pass (F5.2 `escposBuilder.test.ts`, F6.2 `escposBuilder.entrada.test.ts`, `escposBuilder.types.test.ts`, `fallbackBrowser.entrada.test.ts`, `fallbackBrowser.test.ts`); new file passes 30+ scenarios.
- [ ] 4.3 Verify scoped tsc: `npx tsc --noEmit -p apps/electron-sucursal/tsconfig.f7-3-verify.json` exits 0 on F7.3 NEW+MODIFIED production files only (B-prime pattern; pre-existing F5.1 cascades tolerated).
- [ ] 4.4 Verify eslint: `cd apps/electron-sucursal && npx eslint src/lib/print src/features/operacion/components/SalidaPanel.tsx src/features/facturacion/components/PagoSheet.tsx --max-warnings 0` exits 0.
- [ ] 4.5 Verify LOC budget: `git diff --stat origin/dev` shows ≤424 added lines, ≤30 modified lines (under 800 single-PR cap).
- [ ] 4.6 Verify author identity: `git log --format='%an <%ae>' -1` returns `Parkos Dev <dev@parkos.local>` (NEVER `gentle-ai-sub-agent`); no `Co-authored-by:` AI trailers in commit messages.
- [ ] 4.7 Capture manual QA replay evidence (informational, per F6.2 precedent): trigger CU-15S via the dev mock-pago + CU-15SM via the mensualidad-confirm path; verify the printed tiquete contains all 19/15 labels in plan.md field order; document in `apply-progress` if the post-200 wiring fires end-to-end.

## Phase 5: Cleanup + branch hygiene

- [ ] 5.1 No dead code, no temporary stubs, no `Co-Authored-By:` AI attribution trailers in commit messages.
- [ ] 5.2 No backend, no Alembic, no SQL, no new IPC channel changes. No `modelo_datos_er.mmd` modification. No `electron/{main,preload,kiosko,bridge}.ts` changes (F5.1 IPC contract preserved verbatim).
- [ ] 5.3 Post-merge Vite cache invalidation (per AGENTS.md §Operational Timeouts §"Post-merge: invalidar Vite cache"): `Get-NetTCPConnection -LocalPort 5173 | Stop-Process -Id {$_.OwningProcess} -Force`; restart vite with `--force` flag.
- [ ] 5.4 Delete feature branch (per AGENTS.md §Gitflow Estricto rule 4): `git branch -d feature/hu-f7-3-tiquetes-salida && git push origin --delete feature/hu-f7-3-tiquetes-salida` (and the chained-PR sibling if Option B is chosen).
- [ ] 5.5 Confirm session-close merge to `dev` (AGENTS.md §Gitflow Estricto rule 8): `git merge --no-ff feature/hu-f7-3-tiquetes-salida dev` (or `--ff-only` if direct descendant) + `git push origin dev`.

## Acceptance Criteria (REQ-OPS-143 / 144 / 145 scenario coverage)

| REQ | Scenarios covered | Verification |
|-----|-------------------|--------------|
| **REQ-OPS-143** (CU-15S) | §1 (19 labels discoverable), §2 (DEC-SUC-26 markers), §3 (sello bytes pinned), §4 (optional branches), §5 (HTML fallback field order — inspection only), §6 (printer offline → banner — requires runtime, deferred to F8) | Vitest `escposBuilder.salida.test.ts` CU-15S describe block + PR-review field-order inspection of `renderSalidaHtml` |
| **REQ-OPS-144** (CU-15SM) | §1 (15 labels), §2 (sello byte sentinel pinned to canonical fixture), §3 (Tiempo field added), §4 (`esMensualidad: z.literal(true)` discriminator), §5 (HTML fallback field order — inspection), §6 (dynamic encabezado) | Vitest CU-15SM describe block + PR-review field-order inspection of `renderSalidaMensualidadHtml` |
| **REQ-OPS-145** (Wiring DEC-SUC-27) | §1 (CU-15SM immediate on mensualidad-confirm), §2 (CU-15S deferred until post-200 with medioPago), §3 (pre-pago: no print fires), §4 (`bridge.imprimir` wire signature unchanged), §5 (caller-supplied medioPago), §6 (`PARKOS_PRINTER_DISABLED=1` rollback boundary) | PR-review inspection of `SalidaPanel.tsx` + `PagoSheet.tsx` call sites; `bridge.imprimir` signature preserved per F5.1 R4 + R6; `// TODO: Fase 8` anchor comment visible in diff |

## Verify Gates per Task

| Task ID | Vitest | Scoped tsc | ESLint | Manual QA | LOC audit |
|---------|--------|------------|--------|-----------|-----------|
| 1.1–1.4 (pre-flight + scaffold) | n/a | **GATE** (1.4) | n/a | n/a | n/a |
| 2.1–2.5 (builder + factories) | GATE on 4.2 (re-run) | GATE on 2.5 | GATE on 4.4 | n/a | n/a |
| 3.1–3.4 (HTML + wiring) | n/a (HTML inspection only) | GATE on 4.3 (re-run) | GATE on 4.4 | INFO on 4.7 | n/a |
| 4.1–4.7 (tests + verify) | **GATE** on 4.2 | **GATE** on 4.3 | **GATE** on 4.4 | INFO on 4.7 | **GATE** on 4.5 (≤424 LOC) |
| 5.1–5.5 (cleanup) | n/a | n/a | n/a | n/a | n/a |

## Risk Register

| # | Risk | Source | Mitigation | Phase/task |
|---|------|--------|------------|-----------|
| R1 | Salida builder body diverges from `plan.md` literal byte string after refactor (label reordering) | design.md §Risk Mitigations row 1 | Byte-fixture test pins each of the 19/15 field labels via `Buffer.indexOf` | Phase 2 + 4.1 |
| R2 | CU-15SM sello bytes drift (`0x1B 0x21 0x30`) if `escText2x()` / `escTextReset()` helpers are touched upstream | design.md §Risk Mitigations row 2 | Test pins the literal byte sequence verbatim | Phase 2 + 4.1 |
| R3 | Builder field count diverges between `escposBuilder.ts` and `fallbackBrowser.ts` HTML renderers | design.md §Risk Mitigations row 3 | Both files modified in commit 3 (single-PR track) OR chained-PR Unit 3 (chained track); reviewer inspection catches drift | Phase 3.1 + 3.2 |
| R4 | `PagoSheet.tsx` post-200 trigger is misread as "wire only", leaving the call site non-executable until Fase 8 | design.md §Risk Mitigations row 4 | Anchor comment `// TODO: Fase 8: confirms the post-200 trigger fires here` is visible in PR diff | Phase 3.4 |
| R5 | `SalidaMensualidadPayload` factory could miss `esMensualidad: z.literal(true)` discriminator | design.md §Risk Mitigations row 5 | Zod `z.literal(true)` at `escposTemplates.ts:400` enforces at runtime; test scenario for "discriminator" asserts `EscposPayloadMissingFieldError` on `esMensualidad: false` | Phase 2.4 + 4.1 |
| R6 | Workspace-class `tsc` cascade re-emits the F5.1 cascade | design.md §Risk Mitigations row 6 | B-prime scoped tsc pattern (Engram #1742) is the established recipe | Phase 1.3 + 1.4 + 4.3 |
| R7 | B-prime scoped tsc passes but full-project tsc fails for unrelated reasons | design.md §Risk Mitigations row 7 | Full-project tsc is informational; B-prime is the gating signal per F6.2 verify-report | Phase 4.3 |
| R8 | `Buffer` polyfill missing in a new test scope | design.md §Risk Mitigations row 8 (closed) | F5.2's `global.d.ts` is in scope globally; no re-shim needed | Phase 4.1 |
| R9 | e2e `printer.spec.ts` not exercisable on sandbox F.6 | design.md §Risk Mitigations row 9 (closed) | Byte-fixture tests are the verification boundary; documented as "N/A — sandbox F.6" in `apply-progress` | Phase 4.7 |
| R10 | `PagoSheet.tsx` imports cycle with `src/lib/print/*` | design.md §Risk Mitigations row 10 | Only `escposBuilder` and `escposTemplates` factories are imported; both already exported and reused | Phase 3.4 |
| R11 | A-05 `log_transaccional(accion='impreso')` INSERT silently skipped | design.md §Risk Mitigations row 11 (closed) | `// TODO: Fase 8 inserts log_transaccional INSERT here` anchor in `PagoSheet.tsx`; audit-first enforced at API/ORM/DB per AGENTS.md §1 | Phase 3.4 |
| R12 | HTML renderer field order drifts from byte buffer after future refactor | design.md §Risk Mitigations row 12 | Both renderers modified in same commit; reviewer inspection catches drift in PR diff (F6.2 precedent) | Phase 3.1 + 3.2 |
| R13 | Conventional Commit messages carry AI attribution trailers | design.md §Risk Mitigations row 13 (closed) | AGENTS.md §Gitflow Estricto prohibits `Co-Authored-By:` trailers; author identity enforced via `git -c user.name='Parkos Dev' -c user.email='dev@parkos.local'` | Phase 4.6 + 5.1 |
| R14 | Single-PR track rejected by reviewer for being >400 LOC | this tasks.md | Chained-PR Option B proposed as alternative; user selects at apply gate | Phase 0 (orchestrator ask) |
| R15 | Chained-PR track rejected by reviewer for partial-review error (builder without HTML mirror = byte-correct, pixel-broken) | this tasks.md | Chained-PR Unit 3 explicitly bundles HTML mirror + wiring + tests because cross-file coupling makes partial review dangerous | Phase 3 + 4 (under Option B) |

## Commit Strategy

### Option A (design default) — single PR with 3 work-unit commits

Branch: `feature/hu-f7-3-tiquetes-salida` from `dev`, target `dev`.

| # | Conventional Commit | Files | LOC |
|---|---------------------|-------|-----|
| 1 | `feat(print): complete CU-15S 19-field contract in buildSalidaBody` | `escposBuilder.ts` (+40), `escposTemplates.ts` (+60 — `buildSalidaPayload` factory) | ~100 |
| 2 | `feat(print): complete CU-15SM 15-field contract with mensualidad sello` | `escposBuilder.ts` (+25), `escposTemplates.ts` (residual factory work if split) | ~25 |
| 3 | `feat(print): mirror CU-15S/CU-15SM in fallback HTML, wire call sites, add byte tests` | `fallbackBrowser.ts` (+60), `SalidaPanel.tsx` (+30), `PagoSheet.tsx` (+25), `__tests__/escposBuilder.salida.test.ts` (+170), `tsconfig.f7-3-verify.json` (+14), residual factory work | ~299 |

**Total**: ~424 LOC across 3 commits. Tests bundled with code per `work-unit-commits` rule. Commit 3 is wide because the wiring additions are operationally one work unit ("wire both call sites so Fase 8 can drive them"). Conventional Commit messages cite the WHY (DEC-SUC-27 ordering, plan.md 19/15-field contract, plan.md line 1816 test name) rather than the WHAT. No `Co-authored-by:` trailers; author `Parkos Dev <dev@parkos.local>`. PR base = `dev`, never `main`. Merge strategy: `--ff-only` if direct descendant of `dev`, else `--no-ff` (preferred for SDD traceability).

### Option B (alternative if user picks chained-PR) — `feature-branch-chain` per `work-unit-commits`

Branch topology:
- Tracker: `feature/hu-f7-3-tiquetes-salida` (accumulates the final integration; targets `dev`).
- PR #1: `feature/hu-f7-3-tiquetes-salida-builder` (base = tracker) — commits 1+2 (CU-15S builder + CU-15SM builder + both factories).
- PR #2: `feature/hu-f7-3-tiquetes-salida-wire` (base = PR #1 branch) — commit 3 (HTML mirror + call sites + tests + tsconfig).

**Reviewer benefit**: each PR diff stays focused (~125 LOC + ~299 LOC). **Trade-off**: PR #2's diff is the wider one and the cross-file contract (byte ↔ HTML ↔ wiring ↔ tests) splits at the commit boundary, so partial-review error on PR #1 (builder without HTML mirror) is possible. PR #2 must include a PR description that explicitly references the byte-buffer ↔ HTML field-order coupling so reviewers don't ship builder fixes that don't match the fallback mirror.

**Selection criterion**: prefer Option A unless reviewer burden on a 424-LOC PR is judged unsustainable; prefer Option B if the team wants per-PR review focus and accepts the partial-review trade-off documented in R15.

## References

- **Proposal**: `openspec/changes/hu-f7-3-tiquetes-salida/proposal.md` — intent, scope, approach, rollback, dependencies, success criteria.
- **Spec (per-change)**: `openspec/changes/hu-f7-3-tiquetes-salida/specs/operacion/spec.md` — 18 scenarios across REQ-OPS-143..145.
- **Spec (canonical delta)**: `openspec/specs/operations/spec.md` lines 5826–5997 — REQ-OPS-143..145 ADDED (Mechanical Copy Contract: pre-append SHA-256 `50FB12B53E37B4CB01E485DD3DE63EEC9D0E32AAACEBB48787EE3DF924B9703C` over 512004 bytes).
- **Design**: `openspec/changes/hu-f7-3-tiquetes-salida/design.md` — 6 ADRs, 9 file changes, 3 data-flow diagrams, verify matrix, threat matrix.
- **Plan contract**: `plan.md` lines 1779–1826 — HU-F7.3 canonical contract (verbatim 19/15-field lists, sello decision, DEC-SUC-27 sequence correction, test name + 2-case scope).
- **F6.2 archive precedent**: `openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/{tasks.md,design.md,verify-report.md}` — primary reference for builder + HTML mirror + byte-fixture test pattern + B-prime scoped tsc.
- **F5.1 archive precedent**: `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/` — IPC channel `bridge.imprimir({ buffer })`, `PARKOS_PRINTER_DISABLED=1` env, retry queue.
- **F5.2 archive precedent**: `openspec/changes/archive/2026-09-17-fase-5-2-escpos-builder-fallback/` — `escposBuilder.build(tipo, payload)`, `fallbackBrowser.print(payload)`, Buffer polyfill, dispatcher, 4-type Zod schemas, `escText2x()` / `escTextReset()` helpers, `formatFechaCorta()`.
- **F6.1 archive precedent**: `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/` — `IngresoPanel.tsx:75–86` `openSuccessWithAutoPrint` pattern that `SalidaPanel.tsx` mirrors.
- **Existing builder source**: `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 240–301 — the diverging skeleton this change fixes.
- **Existing HTML mirror source**: `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` lines 59 (`PAGE_RULE`), 182 (`renderSalidaHtml`), 208 (`renderSalidaMensualidadHtml`).
- **Existing schemas**: `apps/electron-sucursal/src/lib/print/escposTemplates.ts` lines 369 (`salidaPayloadSchema`), 385 (`salidaMensualidadPayloadSchema` with `esMensualidad: z.literal(true)`), 449 (TIQUETE_TIPOS union).
- **Existing dispatcher**: `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 391–427 — `build()` routes `'salida'` / `'salida-mensualidad'`.
- **Bridge contract**: `apps/electron-sucursal/electron/bridge.d.ts` + `apps/electron-sucursal/electron/types/print.ts:28` (`printPayloadSchema`).
- **AGENTS.md**: Architectural Principles §1–3 (Audit-First, Bi-Temporal, C/Q/U operation contract); §Gitflow Estricto (commit identity, branch protection, merge strategy, post-merge Vite cache invalidation).
- **Canonical print spec**: `openspec/specs/impresion.md` (F5.1 + F5.2 + F6.2 merged).
- **Engram patterns**: #1742 (B-prime scoped tsc pattern, F4.3/F5.1/F5.2/F6.1/F6.2 archive precedent); #1762 (Mechanical Copy Contract); #1776 (apply-progress convention); session #1353 (git identity leak prevention).
- **`openspec/config.yaml`** `rules.tasks`: 800 LOC single-PR budget; 400 LOC chained-PR threshold.

## Next Step

Hand back to the orchestrator. The orchestrator must:
1. **Gatekeeper-check**: verify all pre-flight dependencies from §Dependencies of `proposal.md` are merged to `dev`.
2. **Apply `delivery_strategy = ask-on-risk`** (cached): the 424 LOC forecast crosses the 400 chained-PR threshold but stays under the 800 per-PR cap. The user must choose between **Option A — size:exception single-PR with 3 work-unit commits** (design default; cross-file contract) OR **Option B — feature-branch-chain with 2 PRs** (split builder from wiring+tests).
3. **On user choice**: launch `sdd-apply` with the selected commit strategy. Apply-phase will produce `apply-progress` with per-task receipts (vitest, scoped tsc, eslint, LOC audit, author scan) for verify-report consumption.

**Status**: success — task list complete with 5 phases, 18 atomic tasks, 3-work-unit commit strategy, 15-risk register, full REQ-OPS-143/144/145 coverage, Review Workload Forecast at the top.
