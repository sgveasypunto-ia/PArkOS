# Design: HU-F7.3 — Tiquetes de salida (CU-15S) y salida-mensualidad (CU-15SM), impresos después del pago

> **Change**: `hu-f7-3-tiquetes-salida` · **Change key (Engram)**: `sdd/hu-f7-3-tiquetes-salida/design` · **Project**: `parkos` (Engram-scoped) · **Phase**: design · **Plan contract**: `plan.md` lines 1779–1826 (HU-F7.3 — Fase 7 Parte I) · **Specs**: `openspec/changes/hu-f7-3-tiquetes-salida/specs/operacion/spec.md` (per-change) + `openspec/specs/operations/spec.md` lines 5826–5997 (REQ-OPS-143..145 delta) · **Forecast LOC**: ~350 (under the 800-LOC single-PR budget from `openspec/config.yaml` `rules.tasks`) · **Strategy**: single-PR, 3 work-unit commits, `feature/hu-f7-3-tiquetes-salida` branched from `dev`, target `dev`

## Technical Approach

F7.3 is a **renderer-side pure** change confined to `apps/electron-sucursal/src/lib/print/` (builder + HTML fallback + 1 new test) + `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (CU-15SM immediate wiring) + `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (CU-15S deferred wiring). No backend, no Alembic, no SQL, no new IPC channel. The two ESC/POS bodies (`buildSalidaBody` at `escposBuilder.ts:240–273` and `buildSalidaMensualidadBody` at `:275–301`) are F5.2 skeletons that diverge from the verbatim 19/15-field contract in `plan.md` lines 1789–1810; F7.3 brings them into alignment, mirrors the fixes in `fallbackBrowser.ts::renderSalidaHtml` / `renderSalidaMensualidadHtml` (semantic HTML, same field order, DEC-SUC-08 `@page` rule reused verbatim from `PAGE_RULE` at `fallbackBrowser.ts:59`), adds the missing `window.bridge.imprimir({...})` calls at the two DEC-SUC-27 sites (mirroring `IngresoPanel.tsx:80`), and ships the 2 byte-fixture cases per `plan.md` line 1816 (`escposBuilder.salida.test.ts`). Composition: caller builds a fully populated `SalidaPayload` / `SalidaMensualidadPayload` → `escposBuilder.build('salida'|'salida-mensualidad', payload)` → `Buffer` → `bridge.imprimir({ buffer: Buffer.toString('base64'), uuidRegistro, ticketId, cut: false })` per F5.1 IPC contract (`apps/electron-sucursal/electron/types/print.ts:28`).

The change is a contract-shaped fix, not a redesign. Zod schemas (`salidaPayloadSchema` at `escposTemplates.ts:369` and `salidaMensualidadPayloadSchema` at `:385` with `esMensualidad: z.literal(true)` per DEC-SUC-21) already carry every field; no schema extension. The F5.2 dispatcher (`escposBuilder.ts:391–427`) already routes the two tipos. The F5.1 IPC channel is unchanged. F7.3 only fills the byte-buffer gaps, mirrors them in HTML, and lights up the two React call sites — three orthogonally-scoped edits inside one PR.

## Architecture Decisions

### ADR-01 — Bring the F5.2 builder skeleton into verbatim alignment with `plan.md` lines 1789–1808 / line 1810 (DEC-SUC-27 contract)

**Context**: The F5.2 skeleton at `escposBuilder.ts:240–273` (CU-15S) and `:275–301` (CU-15SM) emits 17/13-line bodies that diverge from the canonical 19/15-field list. The divergences are enumerated in `proposal.md` §"Builder fixes" and reproduced in §File Changes below. Without the fix, the renderer prints a tiquete that omits `Operario`, `Tarifa`, `Horario`, the QR/LOGO markers (DEC-SUC-26), the optional `Observaciones` branch, and (CU-15SM only) the `Tiempo` line — every operator-visible field documented in `plan.md`.

**Decision**: Modify `buildSalidaBody` (7 line-level changes: sello literal `'*** SALIDA ***'` → `'*** TIQUETE DE SALIDA ***'` at line 252; insert `Operario:`; insert `Tarifa:`; insert `Horario:`; append `;QR:` and `;LOGO:` markers before footer; insert optional `Observaciones:` branch; the existing `Poliza RC:` optional guard at line 269 stays as-is) and `buildSalidaMensualidadBody` (4 line-level changes: insert `Tiempo:` between `Salida:` and `Placa:`; append `;QR:` + `;LOGO:` markers before `Conserve este tiquete como soporte.`; insert optional `Observaciones:` branch; preserve existing sello `*** PAGO CON MENSUALIDAD ***` at line 287 verbatim per `plan.md` line 1787).

**Consequences**: Byte fixtures become deterministic; `Buffer.indexOf(label) !== -1` is the assertion primitive. Field-order correspondence with `fallbackBrowser.ts` HTML renderers is preserved (see §File Changes). The CU-15S sello sentinel `Buffer.from([0x1B, 0x21, 0x30, ...'*** TIQUETE DE SALIDA ***', 0x1B, 0x21, 0x00])` and CU-15SM sello sentinel `Buffer.from([0x1B, 0x21, 0x30, ...'*** PAGO CON MENSUALIDAD ***\n', 0x1B, 0x21, 0x00])` (plan.md line 1816 canonical assertion) become the byte-level guard against future helper drift in `escText2x()` / `escTextReset()` (defined at `escposBuilder.ts:125` / `:130`). No Zod change required — schemas already present.

### ADR-02 — Mirror byte-buffer fixes in `fallbackBrowser.ts` semantic HTML at the same commit boundary (F5.2 R4 mirror rule)

**Context**: `renderSalidaHtml` (`fallbackBrowser.ts:182`) and `renderSalidaMensualidadHtml` (`:208`) currently emit 11/9-line HTML that mirrors the F5.2 builder skeleton — same 7/4 divergences as the byte buffer. The DEC-SUC-08 `@page { size: 80mm auto; margin: 2mm }` CSS rule (`PAGE_RULE` at `fallbackBrowser.ts:59`) is already injected; F7.3 reuses it without paraphrasing (REQ-OPS-143 scenario 5, REQ-OPS-144 scenario 5). F6.2 precedent (`openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/design.md`) shipped both builder fix and HTML mirror in a single commit so the field orders cannot drift at the commit boundary.

**Decision**: Modify both HTML renderers in the same commit as ADR-01. Field order: encabezado (`<h1>PARKINGOS</h1>`) → empresa → NIT → dirección → régimen → operario → sello (`<h2>*** TIQUETE DE SALIDA ***</h2>` or `<h2>*** PAGO CON MENSUALIDAD ***</h2>`) → folio → tarifa (CU-15S only) → entrada → salida → tiempo (CU-15SM only) → placa → subtotal/IVA/total (CU-15S only) → medioPago (CU-15S only) → resolucion FE → horario → poliza (optional) → observaciones (optional) → QR + logo `<img>` tags → footer. QR renders as `<img src="${escapeHtml(payload.qrDataUrl)}" />`; logo renders as `<img src="${escapeHtml(payload.logoDataUrl)}" />` with empty-logo preserving the `▢` placeholder glyph (DEC-SUC-08 fallback, line 145).

**Consequences**: HTML renderers remain auto-tested only by inspection (F6.2 precedent — `renderEntradaTiqueteHtml` is also uncovered by automated tests because the F5.2 R4 "caller-purity" boundary excludes `window.print()` mocks). Reviewer catches field-order drift in PR diff, not in a failing test. Byte buffer is the test boundary; HTML mirror is the visual boundary.

### ADR-03 — Wire the two call sites in the same commit as the HTML mirror (F6.1 auto-print pattern at `IngresoPanel.tsx:80`)

**Context**: F7.3 needs to call `await window.bridge.imprimir({...})` at exactly two moments per DEC-SUC-27 (`plan.md` line 1783): (1) immediately on `SalidaPanel.tsx` mensualidad-confirm success (CU-15SM, no cobro); (2) deferred to `PagoSheet.tsx` post-200 success branch (CU-15S, the post-pago trigger is the only site where `factura_pagos.medio_pago` is known). F6.1's `IngresoPanel.tsx:75–86` (`openSuccessWithAutoPrint`) is the structural precedent: `try { await window.bridge.imprimir(payload); } catch {}` with best-effort semantics and the F5.1 retry queue handling reconnects.

**Decision**:

- `SalidaPanel.tsx` — add a `handleMensualidadConfirm` `useCallback` that builds a `SalidaMensualidadPayload` via `buildSalidaMensualidadPayload(ingreso, sucursal, empresa, operario, ...)` (factory to be added or imported — see ADR-06), then awaits `window.bridge.imprimir({ buffer: escposBuilder.build('salida-mensualidad', payload).toString('base64'), ticketId: `salida-mensualidad-${payload.folio}`, uuidRegistro: payload.folio, cut: false })`. Mirror the F6.1 try/catch shape with `// DEC-SUC-27 immediate clause` comment.

- `PagoSheet.tsx` — declare the call site at the post-200 success branch (inside `handleSubmit`, after `await onSubmit(values)` returns). The trigger site will be supplied by Fase 8 (HU-F8.1+); F7.3 wires only the call with a `// TODO: Fase 8: confirms the post-200 trigger fires here` anchor comment. The call uses `buildSalidaPayload(currentFactura, sucursal, empresa, operario, ...)` factory; `medioPago` comes from `factura_pagos.medio_pago` resolved by Fase 8.

**Consequences**: Both call sites reuse the F5.1 IPC contract unchanged (`PrintPayload` schema at `apps/electron-sucursal/electron/types/print.ts:28`). No new IPC channel, no `lines: PrintLine[]` shape (F5.1 rejects that form per impresion.md R4). The try/catch shape means `printer_offline` / `printer_disconnected` / `print_failed_terminal` errors are absorbed silently and the F5.1 retry queue handles reconnects (F5.1 R5). The `// TODO: Fase 8` anchor is the visible hand-off signal in PR review. `PARKOS_PRINTER_DISABLED=1` env (F5.1 R6) preempts both call sites before the builder is invoked (REQ-OPS-145 scenario 6).

### ADR-04 — Ship 2 byte-fixture cases in `escposBuilder.salida.test.ts` per `plan.md` line 1816 (F6.2 test pattern)

**Context**: `plan.md` line 1816 mandates: "Pruebas: `src/lib/print/__tests__/escposBuilder.salida.test.ts` — 2 casos (19 campos de CU-15S, 15 campos + sello de CU-15SM), validando los bytes exactos del sello (`0x1B 0x21 0x30`)." The F6.2 precedent (`escposBuilder.entrada.test.ts`, 47 scenarios across byte-presence + Zod rejection + mensualidad tag + factory purity) is the template. F5.2 baseline (`escposBuilder.test.ts`, 12 scenarios) supplies the test infrastructure: `validSalidaPayload()` factory at line 168; `Buffer` polyfill in `global.d.ts` (F5.2 commit `f54c4ef`).

**Decision**: Create `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` with two `describe()` blocks (`buildSalidaBuffer — 19 byte-presence scenarios (HU-F7.3)` and `buildSalidaMensualidadBuffer — 15 byte-presence + sello sentinel (HU-F7.3)`). Each `it()` asserts `Buffer.indexOf(<label>) !== -1` for one field label. The CU-15S block has 19 byte-presence scenarios (one per `plan.md` line 1789–1808 field) + 2 DEC-SUC-26 marker scenarios (QR marker, LOGO marker, both before footer) + 1 sello sentinel scenario + 1 optional-branches scenario (polizaRC=null AND observaciones=null → both omitted; horario + resolucionFE still emitted) + 1 purity scenario (no `window.print()` call). The CU-15SM block has 15 byte-presence scenarios + 1 sello sentinel pinned to `Buffer.from([0x1B, 0x21, 0x30, ...'*** PAGO CON MENSUALIDAD ***\n', 0x1B, 0x21, 0x00])` (plan.md line 1816 canonical) + 1 ausencia-de-cobro scenario (no `Subtotal:` / `IVA:` / `TOTAL:` / `Medio de pago:` strings) + 1 discriminator scenario (`esMensualidad: z.literal(true)` rejects missing literal with `EscposPayloadMissingFieldError`) + 1 dynamic-encabezado scenario (payload with `empresa.nombre = "Mi Parqueadero XYZ"` emits that literal, NOT corpus-fixed `PARQUEADERO PUBLICO`) + 1 purity scenario.

**Consequences**: ~170 LOC added. The test file imports `validSalidaPayload()` and adds `validSalidaMensualidadPayload()` helpers alongside (`escposBuilder.test.ts:168` exports the former; F7.3 exports the latter). Reuses F5.2's `Buffer` polyfill (`global.d.ts`) without re-import. Vitest boundary covers the byte buffer; HTML renderer is verified by inspection per ADR-02. e2e `printer.spec.ts` is deferred per sandbox F.6 (F5.1/F5.2/F6.x precedent).

### ADR-05 — Single-PR strategy with 3 work-unit commits (work-unit-commits §SDD Relationship, forecast <400 LOC)

**Context**: `work-unit-commits` §SDD Relationship: forecast <400 LOC ⇒ single PR, no chained-PR scaffolding. F7.3 forecast is 350 LOC. The 3 commits are internal to the same user-facing capability ("tiquete de salida y salida-mensualidad impresos según DEC-SUC-27"), so the contract is cross-file and reviewers benefit from seeing builder + HTML mirror + wiring + tests in one PR diff. The cross-file contract (DEC-SUC-26 marker emission in builder must match the `<img>` tag emission in HTML fallback) is the strongest argument against splitting.

**Decision**: Three commits in one PR (`feature/hu-f7-3-tiquetes-salida` → `dev`):

| # | Type | Scope | Files | LOC delta |
|---|------|-------|-------|-----------|
| 1 | `feat(print)` | CU-15S 19-field contract fixes | `escposBuilder.ts` (+~40), `escposTemplates.ts` (0) | ~40 |
| 2 | `feat(print)` | CU-15SM 15-field contract with mensualidad sello | `escposBuilder.ts` (+~25) | ~25 |
| 3 | `feat(print)` | HTML mirror + wire call sites + byte-fixture tests | `fallbackBrowser.ts` (+~60), `SalidaPanel.tsx` (+~30), `PagoSheet.tsx` (+~25), `__tests__/escposBuilder.salida.test.ts` (+~170) | ~285 |

If implementation exceeds 350 LOC during apply, commits 1+2 stay together as `feature/hu-f7-3-tiquetes-salida-builder` and commit 3 lands as `feature/hu-f7-3-tiquetes-salida-wire` (chained-PR sequence). Work-unit-commits rule: tests live with code, but commit 3 is wide because the wiring additions are operationally one work unit ("wire both call sites so Fase 8 can drive them").

**Consequences**: Conventional Commit messages cite the WHY (DEC-SUC-27 ordering, plan.md 19/15-field contract, plan.md line 1816 test name) rather than the WHAT. No `Co-authored-by:` / AI attribution trailers (AGENTS.md §Gitflow Estricto). Author: `Parkos Dev <dev@parkos.local>`. PR base = `dev`, never `main`. Merge strategy: `--ff-only` if commit 1 is a direct descendant of `dev`; otherwise `--no-ff` (preferred for SDD traceability).

### ADR-06 — Payload factories (CU-15S + CU-15SM) live alongside `buildEntradaPayload` in `escposTemplates.ts`

**Context**: F6.2 ships `buildEntradaPayload({ingreso, sucursal, empresa, operario, tarifa, documentos, fechaHora})` factory at `escposTemplates.ts` (called from `escposBuilder.entrada.test.ts` line 84 and F6.1's `Principal.tsx`). The factory pattern is the established way to convert ER rows to Zod-validated payloads. The two React call sites in ADR-03 (`SalidaPanel.tsx`, `PagoSheet.tsx`) need the equivalent factory for salida builders.

**Decision**: Add two factory functions to `escposTemplates.ts`:

- `buildSalidaPayload({ingreso, salida, sucursal, empresa, operario, tarifa, documentos, fechaHora, medioPago, resolucionFE})` — derives `tiempoTotal = formatTiempo(salida.fecha_salida - ingreso.fecha_ingreso)`, computes subtotal/iva/total from invoice, attaches `qrDataUrl` + `logoDataUrl` from `documentos`, returns a Zod-validated `SalidaPayload`. No `esMensualidad` flag (CU-15S is rotation only).

- `buildSalidaMensualidadPayload({ingreso, salida, sucursal, empresa, operario, documentos, fechaHora})` — derives `tiempoTotal`, attaches QR + logo, sets `esMensualidad: z.literal(true)` literal per DEC-SUC-21. NO `subtotal`/`iva`/`total`/`medioPago` fields (CU-15SM has no cobro per plan.md line 1810).

**Consequences**: Zod runtime validation is at the factory boundary; if a field is missing, `EscposPayloadMissingFieldError` fires before the builder is invoked (F5.2 R1). The two factories are 100% pure (no I/O — QR/LOGO rasterization is the caller's responsibility per F5.2 R3). They are exported from `escposTemplates.ts` and consumed by the new `escposBuilder.salida.test.ts` (test fixtures) and by `SalidaPanel.tsx` / `PagoSheet.tsx` (production). The `validSalidaMensualidadPayload()` test helper in `escposBuilder.test.ts` is built on top of the factory.

## Data Flow

### CU-15S (salida rotación) — DEC-SUC-27 deferred clause

```
                       Operator clicks "Cobrar" in SalidaPanel.tsx
                                                │
                                                ▼
                       PagoSheet.tsx opens (REQ-OPS-138 single-drawer)
                                                │
                       Operator fills medioPago / monto / NIT / voucher
                                                │
                                                ▼
                       Confirm → POST /facturacion/factura (Fase 8)
                                  POST /facturacion/factura-pagos  (Fase 8)
                                                │
                                                ▼
                       200 OK + factura_pagos.medio_pago resolved
                                                │
                                                ▼
        ┌───────────────────────────────────────────────────────────────────────┐
        │ PagoSheet.tsx handleSubmit (POST-F7.3 WIRING) — // TODO: Fase 8 anchor │
        │                                                                       │
        │   const payload = buildSalidaPayload({                               │
        │     ingreso, salida, sucursal, empresa, operario,                    │
        │     tarifa, documentos, fechaHora,                                   │
        │     medioPago: factura_pagos.medio_pago,  // from Fase 8 row         │
        │     resolucionFE,                                                    │
        │   });                                                                 │
        │   await window.bridge.imprimir({                                    │
        │     buffer: escposBuilder.build('salida', payload)                  │
        │                  .toString('base64'),                                │
        │     ticketId: 'salida-${payload.folio}',                             │
        │     uuidRegistro: payload.folio,                                      │
        │     cut: false,                                                       │
        │   });                                                                 │
        └─────────────────────────┬─────────────────────────────────────────────┘
                                                │
                                                ▼
                       bridge.imprimir → electron/preload.ts → IPC print:ticket
                                                │
                                                ▼
                       electron/services/printer.ts (F5.1) — escpos-usb write
                                                │
                       ┌────────────────────────┴────────────────────────┐
                       ▼                                                 ▼
                  ok:true                                  ok:false (printer_offline)
                  F5.1 R5: emits print_succeeded           F5.1 R3: emits print_failed
                       │                                                 │
                       ▼                                                 ▼
                  (A-05 hook — DEFERRED to Fase 8)        F5.1 retry queue persists
                                                           drains when printer reconnects
```

### CU-15SM (salida mensualidad) — DEC-SUC-27 immediate clause

```
                       Operator confirms salida with active subscripcion
                       (SalidaPanel.tsx — mensualidad branch)
                                                │
                                                ▼
                       handleMensualidadConfirm (POST-F7.3 WIRING)
                                                │
                                                ▼
        ┌───────────────────────────────────────────────────────────────────────┐
        │ SalidaPanel.tsx useCallback — DEC-SUC-27 immediate clause           │
        │                                                                       │
        │   const payload = buildSalidaMensualidadPayload({                   │
        │     ingreso, salida, sucursal, empresa, operario,                   │
        │     documentos, fechaHora,                                          │
        │   });                                                                 │
        │   await window.bridge.imprimir({                                    │
        │     buffer: escposBuilder.build('salida-mensualidad', payload)      │
        │                  .toString('base64'),                                │
        │     ticketId: 'salida-mensualidad-${payload.folio}',                 │
        │     uuidRegistro: payload.folio,                                     │
        │     cut: false,                                                       │
        │   });                                                                 │
        └─────────────────────────┬─────────────────────────────────────────────┘
                                                │
                                                ▼
                       (identical IPC path to CU-15S — single bridge.imprimir wire)
```

### Pre-pago guard (REQ-OPS-145 scenario 3)

```
                       pago POST in flight (or any non-200 path:
                       user navigates away, modal closes, error toast)
                                                │
                                                ▼
                       PagoSheet.tsx handleSubmit exits via early return
                       (uuid_ingreso === null  OR  onSubmit rejects)
                                                │
                                                ▼
                       bridge.imprimir SHALL NOT be invoked for tipo:'salida'
                       salidas.uuid MAY be persisted by Fase 8 — Fase 8 owns
                       the INSERT timing (F7.3 is observer-side per A-05)
```

## File Changes

| File | Action | Description | LOC delta |
|------|--------|-------------|-----------|
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (`buildSalidaBody` lines 240–273) | Modify | 7 fixes for CU-15S: sello literal replacement (line 252); insert `Operario:` after regimen block; insert `Tarifa:` after `Folio:`; insert `Horario:` after `Medio de pago:` block; insert optional `Observaciones:` branch after `Resolucion FE:`; append `;QR:` + `;LOGO:` markers before `Gracias por su visita.` footer (mirror the F6.2 `;QR:` / `;LOGO:` pattern at lines 233–234); existing `Poliza RC:` optional guard at line 269 stays as-is. | +40 |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (`buildSalidaMensualidadBody` lines 275–301) | Modify | 4 fixes for CU-15SM: insert `Tiempo:` between `Salida:` and `Placa:`; append `;QR:` + `;LOGO:` markers before `Conserve este tiquete como soporte.`; insert optional `Observaciones:` branch after `Horario:`; preserve existing sello `*** PAGO CON MENSUALIDAD ***` at line 287 verbatim per `plan.md` line 1787 (no byte drift). | +25 |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` (`renderSalidaHtml` line 182) | Modify | Mirror the 7 CU-15S fixes in semantic HTML: add `<p>Operario: ...</p>`; add `<p>Tarifa: .../hora</p>`; add `<p>Horario: ...</p>`; add `<p>Observaciones: ...</p>` (optional); sello `<h2>*** TIQUETE DE SALIDA ***</h2>` (replace `*** SALIDA ***`); add `<img src="${qrDataUrl}">` + `<img src="${logoDataUrl}">` before footer; preserve DEC-SUC-08 `@page` CSS via `PAGE_RULE` (no change). | +30 |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` (`renderSalidaMensualidadHtml` line 208) | Modify | Mirror the 4 CU-15SM fixes in semantic HTML: add `<p>Tiempo: ...</p>`; add `<p>Observaciones: ...</p>` (optional); sello `<h2>*** PAGO CON MENSUALIDAD ***</h2>` already correct; add `<img>` tags before footer. | +30 |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (`buildSalidaPayload`, `buildSalidaMensualidadPayload` factories — NEW) | Modify | Add two factory functions (ADR-06) that convert ER rows to Zod-validated payloads. `buildSalidaPayload` derives `tiempoTotal`, computes `subtotal`/`iva`/`total` from invoice, attaches QR + logo from `documentos`, requires `medioPago` (mandatory for CU-15S); `buildSalidaMensualidadPayload` derives `tiempoTotal`, attaches QR + logo, sets `esMensualidad: z.literal(true)` literal per DEC-SUC-21. NO `subtotal`/`iva`/`total`/`medioPago` fields in CU-15SM. | +60 |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (mensualidad-confirm branch — NEW `useCallback`) | Modify | Add `handleMensualidadConfirm` `useCallback` (DEC-SUC-27 immediate clause). Builds `SalidaMensualidadPayload` via `buildSalidaMensualidadPayload(...)`; awaits `window.bridge.imprimir({...})` mirroring `IngresoPanel.tsx:80` `try/catch` shape. The `// DEC-SUC-27 immediate clause` comment makes the ordering explicit in PR review. | +30 |
| `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (post-200 branch — NEW wiring) | Modify | Declare `await window.bridge.imprimir({ tipo:'salida', payload })` inside `handleSubmit`, after `await onSubmit(values)` returns. The trigger site is supplied by Fase 8 (HU-F8.1+); the `// TODO: Fase 8: confirms the post-200 trigger fires here` anchor comment makes the hand-off visible. Payload includes `medioPago` resolved from `factura_pagos.medio_pago`. | +25 |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` | Create | 2 byte-fixture cases per `plan.md` line 1816: CU-15S 19 byte-presence scenarios + sello sentinel + DEC-SUC-26 markers + optional branches + purity; CU-15SM 15 byte-presence scenarios + sello sentinel pinned to `Buffer.from([0x1B, 0x21, 0x30, ...'*** PAGO CON MENSUALIDAD ***\n', 0x1B, 0x21, 0x00])` + ausencia-de-cobro + `esMensualidad: z.literal(true)` discriminator + dynamic-encabezado + purity. Imports `validSalidaPayload` from F5.2 + adds `validSalidaMensualidadPayload()` helper. | +170 |
| `apps/electron-sucursal/tsconfig.f7-3-verify.json` | Create | B-prime scoped tsc config (Engram #1742 pattern, F4.3/F5.1/F5.2/F6.1/F6.2 archive precedent). Extends `./tsconfig.json`. `include`: `src/lib/print/escposTemplates.ts`, `src/lib/print/escposBuilder.ts`, `src/lib/print/fallbackBrowser.ts`, `src/features/operacion/components/SalidaPanel.tsx`, `src/features/facturacion/components/PagoSheet.tsx`. `exclude`: `**/*.test.ts`, `**/*.test.tsx`, `**/*.spec.ts`, `e2e/**/*`. | +14 |

**Forecast LOC total: ~424** (40+25+30+30+60+30+25+170+14). Slightly above the 350 proposal estimate because ADR-06 (the two factories) adds ~60 LOC. Still well under the 800-LOC single-PR budget from `openspec/config.yaml` `rules.tasks`. If implementation tightens (e.g., factories collapse to ~30 LOC), the total drops to ~394.

**Files unchanged (explicit no-go list)**:

- `apps/electron-sucursal/src/lib/print/escposTemplates.ts` schemas (`salidaPayloadSchema:369`, `salidaMensualidadPayloadSchema:385`) — already complete, no extension.
- `apps/electron-sucursal/electron/main.ts` / `electron/preload.ts` / `electron/kiosko.ts` / `electron/bridge.ts` / `electron/types/print.ts` — F5.1 IPC contract unchanged.
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` — no new i18n keys (UI labels unchanged; the tiquete text is Spanish by construction).
- `backend/packages/parkos_core/` (any) — zero changes (Phase 8 backend).
- `infra/` Alembic migrations — zero changes.
- `e2e/print.spec.ts` — deferred to CI per sandbox F.6.

## Interfaces / Contracts

### F5.1 IPC wire (unchanged from F5.1 — `electron/types/print.ts:28`)

```typescript
export const printPayloadSchema = z.object({
  buffer: z.string().min(1, 'buffer must be non-empty base64'),
  ticketId: z.string().min(1).max(64),
  cut: z.boolean().default(false),
  cashDrawer: z.boolean().optional(),
  vid: z.number().int().min(0).max(0xffff).optional(),
  pid: z.number().int().min(0).max(0xffff).optional(),
  uuidRegistro: z.string().uuid().optional(),
});
export type PrintPayload = z.infer<typeof printPayloadSchema>;
```

F7.3 invocations from the two call sites (CU-15S + CU-15SM):

```typescript
await window.bridge.imprimir({
  buffer: escposBuilder.build('salida-mensualidad', payload).toString('base64'),
  ticketId: `salida-mensualidad-${payload.folio}`,
  uuidRegistro: payload.folio,  // salidas.uuid (F8 supplies)
  cut: false,
});
```

### F5.2 builder dispatcher (unchanged from F5.2 — `escposBuilder.ts:391`)

```typescript
export function build(tipo: TiqueteTipo, payload: unknown): Buffer {
  if (!isTiqueteTipo(tipo)) {
    throw new EscposInvalidTipoError(String(tipo));
  }
  const issues = validatePayload(tipo, payload);
  if (issues !== null) {
    throw new EscposPayloadMissingFieldError(issues);
  }
  switch (tipo) {
    case 'salida': {
      const p = salidaPayloadSchema.parse(payload) as SalidaPayload;
      return buildSalidaBuffer(p);
    }
    case 'salida-mensualidad': {
      const p = salidaMensualidadPayloadSchema.parse(payload) as SalidaMensualidadPayload;
      return buildSalidaMensualidadBuffer(p);
    }
    // ... entrada, reimpresion unchanged
  }
}
```

### New payload factories (ADR-06 — `escposTemplates.ts`)

```typescript
/**
 * `buildSalidaPayload` — CU-15S factory. Converts ER rows to a
 * Zod-validated SalidaPayload. Caller MUST supply `medioPago` (post-pago
 * dependency, DEC-SUC-27). NO `esMensualidad` flag (CU-15S is rotation only).
 */
export function buildSalidaPayload(args: {
  ingreso: IngresoForPayload;
  salida: SalidaForPayload;
  sucursal: SucursalForPayload;
  empresa: Empresa;
  operario: string;
  tarifa: TarifaForPayload;
  documentos: DocumentoForPayload[];
  fechaHora: string;
  medioPago: string;       // REQUIRED — populated by Fase 8 from factura_pagos
  resolucionFE: string;    // REQUIRED — populated by Fase 8 from resolucion_facturacion
}): SalidaPayload {
  const tiempoTotal = formatTiempo(args.salida.fecha_salida, args.ingreso.fecha_ingreso);
  const { subtotal, iva, total } = computeImpuestos(args.tarifa, tiempoTotal);  // CU-04 inline
  const qrDataUrl = deriveQrDataUrl(args.ingreso, args.salida);                  // F6.2 ABIERTO-01
  const logoDataUrl = deriveLogoDataUrl(args.documentos);                         // F6.2 DEC-SUC-08
  return salidaPayloadSchema.parse({
    ...args.ingreso,
    ...args.salida,
    tiempoTotal,
    subtotal, iva, total,
    medioPago: args.medioPago,
    resolucionFE: args.resolucionFE,
    qrDataUrl,
    logoDataUrl,
    empresa: args.empresa,
    operario: args.operario,
    horarioAtencion: args.sucursal.horario_atencion,
    polizaRC: derivePolizaRC(args.documentos),
    folio: args.salida.uuid,
    observaciones: args.salida.observaciones ?? undefined,
  });
}

/**
 * `buildSalidaMensualidadPayload` — CU-15SM factory. NO cobro fields
 * (subtotal/iva/total/medioPago). Sets `esMensualidad: z.literal(true)`
 * discriminator per DEC-SUC-21.
 */
export function buildSalidaMensualidadPayload(args: {
  ingreso: IngresoForPayload;
  salida: SalidaForPayload;
  sucursal: SucursalForPayload;
  empresa: Empresa;
  operario: string;
  documentos: DocumentoForPayload[];
  fechaHora: string;
}): SalidaMensualidadPayload {
  const tiempoTotal = formatTiempo(args.salida.fecha_salida, args.ingreso.fecha_ingreso);
  const qrDataUrl = deriveQrDataUrl(args.ingreso, args.salida);
  const logoDataUrl = deriveLogoDataUrl(args.documentos);
  return salidaMensualidadPayloadSchema.parse({
    placa: args.ingreso.placa,
    fechaEntrada: args.ingreso.fecha_ingreso,
    fechaSalida: args.salida.fecha_salida,
    tiempoTotal,
    qrDataUrl,
    logoDataUrl,
    empresa: args.empresa,
    operario: args.operario,
    horarioAtencion: args.sucursal.horario_atencion,
    polizaRC: derivePolizaRC(args.documentos),
    folio: args.salida.uuid,
    observaciones: args.salida.observaciones ?? undefined,
    esMensualidad: true,  // DEC-SUC-21 discriminator — literal, not boolean
  });
}
```

### Test sentinel — CU-15SM canonical byte fixture (REQ-OPS-144 scenario 2)

```typescript
// Test sentinel — plan.md line 1816 canonical assertion
expect(buf.indexOf(Buffer.from([0x1B, 0x21, 0x30]))).toBeGreaterThanOrEqual(0);
const selloBytes = Buffer.from('*** PAGO CON MENSUALIDAD ***\n', 'utf8');
expect(buf.indexOf(selloBytes)).toBeGreaterThan(
  buf.indexOf(Buffer.from([0x1B, 0x21, 0x30]))
);
expect(buf.indexOf(Buffer.from([0x1B, 0x21, 0x00]))).toBeGreaterThan(
  buf.indexOf(selloBytes)
);
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (byte-level) | 19 CU-15S field labels + sello bytes + DEC-SUC-26 markers + optional branches + purity | `escposBuilder.salida.test.ts` Case 1 — `Buffer.indexOf(label) !== -1` per field, plus the 5 structural scenarios |
| Unit (byte-level) | 15 CU-15SM field labels + sello bytes pinned to canonical fixture + ausencia-de-cobro + discriminator + dynamic-encabezado + purity | Same file Case 2 — same pattern + canonical byte fixture per `plan.md` line 1816 |
| Unit (Zod) | `buildSalidaPayload` / `buildSalidaMensualidadPayload` reject missing fields | Imported from `escposBuilder.salida.test.ts` via the factory (implied by `salidaPayloadSchema.parse`); 1 happy-path + 1 missing-medioPago scenario per factory |
| Unit (HTML) | `renderSalidaHtml` field order matches byte buffer; `<img>` for QR + logo; DEC-SUC-08 `@page` CSS preserved | NOT auto-tested — reviewer inspection only per F6.2 precedent (`fallbackBrowser.entrada.test.ts` exists but `renderSalidaHtml` follows the same manual-review pattern as `renderEntradaTiqueteHtml` mirror) |
| E2E | `bridge.imprimir` called with base64 payload + auto-fire from `PagoSheet.tsx`/`SalidaPanel.tsx` | `e2e/print.spec.ts` (F6.2 grep slice) — DEFERRED to CI per sandbox F.6 + node-usb-mock not installed (F5.1/F5.2/F6.x precedent) |
| tsc (scoped) | F7.3 NEW + MODIFIED production files compile clean under strict mode | `npx tsc --noEmit -p apps/electron-sucursal/tsconfig.f7-3-verify.json` — B-prime pattern (Engram #1742) |
| eslint | `--max-warnings 0` on F7.3 touched files | `npx eslint src/lib/print src/features/operacion/components/SalidaPanel.tsx src/features/facturacion/components/PagoSheet.tsx` |
| Manual QA replay | Pull `feature/hu-f7-3-tiquetes-salida` locally; trigger a CU-15S via the dev mock-pago + a CU-15SM via the mensualidad-confirm path; verify the printed tiquete contains all 19/15 labels in plan.md field order | Documented in `apply-progress`; not blocking for verify-report PASS (F6.2 precedent: byte fixtures + scoped tsc = gating signal, manual QA is informational) |

## Threat Matrix

**N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.** F7.3 is renderer-pure composition (F5.2 purity extended). The only I/O surface is the F5.1 IPC channel `bridge.imprimir({ buffer })` which F7.3 does not modify. The two React call sites add `await window.bridge.imprimir(...)` mirroring `IngresoPanel.tsx:80` — same pattern, same risk profile. No shell-out, no subprocess spawn, no VCS automation, no executable-file classification changes.

## Migration / Rollout

No migration required. F7.3 ships as a single PR behind no feature flag. The byte-buffer shapes are additive to F5.2's existing `SalidaPayload` / `SalidaMensualidadPayload` — any caller that already passes the 17/13 existing fields continues to work (the new fields are `readonly string` / `readonly number`, missing fields trigger `EscposPayloadMissingFieldError` at the Zod boundary, NOT a runtime crash). Rollback is a single `git revert <merge-commit>` on `dev` (per `proposal.md` §"Rollback plan", 6 steps). No Docker image rollback needed (F7.3 is renderer-side, baked into the image at next release). No Alembic rollback needed (no DB schema change).

Operational rollback boundary: `PARKOS_PRINTER_DISABLED=1` env var (F5.1 R6) preempts both call sites before the builder is invoked — useful for disabling salida printing without redeploying if a print issue is detected in production.

## Open Questions

**None blocking.** Proposal §"Open questions for the user" already enumerated: "Skipped — none. `sdd-propose` interactive question round is **not applicable** for this change because the plan contract is fully specified on lines 1779–1826, the existing skeleton is known, and the divergence list is enumerated by gap analysis." F7.3 inherits the same posture.

## Verify Gates

| Gate | Command | Expected | Source |
|------|---------|----------|--------|
| Builder byte-fixture CU-15S | `npx vitest run apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts -t "CU-15S"` | 1+ passed (19 byte-presence + sello + markers + branches + purity) | REQ-OPS-143 §1, §2, §3, §4 |
| Builder byte-fixture CU-15SM | `npx vitest run apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts -t "CU-15SM"` | 1+ passed (15 byte-presence + sello sentinel + ausencia-de-cobro + discriminator + dynamic-encabezado + purity) | REQ-OPS-144 §1, §2, §4, §6 |
| Vitest full-suite (renderer) | `cd apps/electron-sucursal && npx vitest run` | 100% existing tests pass; no `escposBuilder.test.ts` / `escposBuilder.entrada.test.ts` / `escposBuilder.types.test.ts` regression | F5.2/F6.2 precedent |
| Renderer tsc (B-prime scoped) | `npx tsc --noEmit -p apps/electron-sucursal/tsconfig.f7-3-verify.json` | 0 errors on F7.3 NEW + MODIFIED production files | Engram #1742 (F4.3/F5.1/F5.2/F6.1/F6.2 precedent) |
| Workspace tsc (full) | `npx tsc -b` | same — informational; pre-existing F4.x/F5.1 cascades out of scope | F5.1 follow-up MEDIUM |
| eslint | `cd apps/electron-sucursal && npx eslint src/lib/print src/features/operacion/components/SalidaPanel.tsx src/features/facturacion/components/PagoSheet.tsx --max-warnings 0` | 0 errors, 0 warnings | repo convention |
| e2e `printer.spec.ts` | (NOT EXECUTED) | N/A — sandbox F.6 has no USB | F5.1/F5.2/F6.x precedent |
| Manual QA replay | Pull feature branch; trigger CU-15S via mock-pago + CU-15SM via mensualidad-confirm; verify byte buffer content | passes review; informational only | F6.2 precedent |
| LOC audit | `git diff --stat origin/dev` | ≤~424 added lines, ≤30 modified lines (under 800 single-PR budget) | `openspec/config.yaml` `rules.tasks` |
| Author scan | `git log --format='%an <%ae>' -1` | `Parkos Dev <dev@parkos.local>`, never `gentle-ai-sub-agent` | AGENTS.md §Gitflow Estricto |

**Verify envelope**: B-prime scoped `tsc` + vitest (new test + full renderer suite) + eslint + manual QA replay. Admitted by `gentle-ai.verify-result/v1` per F6.2 precedent (`openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/verify-report.md` line 60: "Strict envelope verdict: **PASS** admitted by gentle-ai.verify-result/v1").

## Risk Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Salida builder body diverges from `plan.md` literal byte string after refactor (label reordering) | Low | Byte-fixture test in `escposBuilder.salida.test.ts` asserts each of the 19/15 field labels via `Buffer.indexOf`. Re-running F5.2's purity round-trip (`build('salida', payload)` does NOT call `window.print()`) gives a second boundary. |
| CU-15SM sello bytes drift (`0x1B 0x21 0x30`) if `escText2x()` / `escTextReset()` helpers are touched upstream | Low | Test pins the literal byte sequence `Buffer.from([0x1B, 0x21, 0x30, ...'*** PAGO CON MENSUALIDAD ***\n', 0x1B, 0x21, 0x00])` between the sello UTF-8 bytes. If helpers change, test fails with a diff pointing at the helper. |
| Builder field count diverges between `escposBuilder.ts` and `fallbackBrowser.ts` HTML renderers | Medium | Both files modified in commit 3 (ADR-02) so they cannot drift at the commit boundary. Vitest byte test covers the builder only; HTML is covered by PR-review inspection per F6.2 precedent. |
| `PagoSheet.tsx` post-200 trigger is misread as "wire only", leaving the call site non-executable until Fase 8 | Medium | Proposal explicitly names the call site as a **hole that Fase 8 fills**: trigger is the post-200 callback returning success. The F7.3 commit adds `await window.bridge.imprimir({...})` with `// TODO: Fase 8: confirms the post-200 trigger fires here` anchor comment visible in PR review. |
| `SalidaMensualidadPayload` factory could miss the `esMensualidad: z.literal(true)` discriminator — TypeScript would accept `false` because `z.boolean()` is the parent | Low | Zod `z.literal(true)` at `escposTemplates.ts:400` enforces at runtime; the test scenario for "discriminator" calls `buildSalidaMensualidadPayload` with `esMensualidad: false` and asserts `EscposPayloadMissingFieldError` (REQ-OPS-144 scenario 4). |
| Workspace-class `tsc` cascade re-emits the F5.1 cascade | Low | B-prime scoped tsc pattern (Engram #1742) is the established recipe for verifying renderer files in isolation. Already proven in F4.3 / F5.1 / F5.2 / F6.1 / F6.2. |
| B-prime scoped tsc passes but full-project tsc fails for unrelated reasons | Low | Same precedent: full-project tsc is the quality gate but B-prime is the gating signal per F6.2 verify-report (warning W1). Pre-existing cascades documented in `apply-progress`. |
| `Buffer` polyfill missing in a new test scope | Closed | F5.2's `global.d.ts` is in scope globally (`vitest.config.ts` already loads it); no re-shim needed. |
| e2e `printer.spec.ts` not exercisable on sandbox F.6 | Closed | Same precedent as F5.1/F5.2/F6.x: byte-fixture tests are the verification boundary. Documented as "N/A — sandbox F.6" in `apply-progress`. |
| `PagoSheet.tsx` imports cycle with `src/lib/print/*` | Low | Only `escposBuilder` (already imported by F6.2 test files) and `escposTemplates` factories are imported; both are already exported and reused. No new import surface. |
| A-05 `log_transaccional(accion='impreso')` INSERT is silently skipped | Closed (out of scope) | F6.2 documents the audit-row payload shape; F7.3 declares the `// TODO: Fase 8 inserts log_transaccional INSERT here` anchor in `PagoSheet.tsx`; F7.3 does NOT call `log_transaccional` directly. Audit-first is enforced at the API/ORM/DB layers per AGENTS.md §1 — Fase 8 inherits. |
| HTML renderer field order drifts from byte buffer after future refactor | Low | Both renderers modified in commit 3 (ADR-02); reviewer inspection catches drift in PR diff. F6.2 precedent: `renderEntradaTiqueteHtml` follows the same manual-review pattern. |
| Conventional Commit messages carry AI attribution trailers | Closed | AGENTS.md §Gitflow Estricto prohibits `Co-Authored-By:` trailers. Author identity enforced: `git -c user.name='Parkos Dev' -c user.email='dev@parkos.local'` at first commit per repo convention. Sub-agent identity leak prevented by orchestrator's git config preflight (per Engram session #1353 cited in AGENTS.md §Git identity for sub-agent work). |

## Out of Scope (inherited from `proposal.md` §"Out of scope" and `specs/operacion/spec.md` §"Out of Scope")

- **Backend** (`backend/packages/parkos_core/`, Alembic, SQL) — zero changes. The CU-15S `medioPago`, the `facturas` / `factura_pagos` rows, and the `factura_electronica` issuance are Phase 8 (plan.md lines 1830+).
- **A-05 `log_transaccional(accion='impreso')` INSERT** — backend concern. F6.2 documents the audit-row payload shape; F8 writes the row. F7.3 declares the `// TODO: Fase 8 inserts log_transaccional INSERT here` anchor in `PagoSheet.tsx`; F7.3 does NOT call `log_transaccional` directly. Audit-first enforcement is at the API/ORM/DB layers (AGENTS.md §1), not at the renderer.
- **Fase 8 pago modal UI** — separate cycle (HU-F8.1+, plan.md line 1832+). The `PagoSheet.tsx` post-200 trigger is a hole that Fase 8 fills; F7.3 wires the call site, Fase 8 supplies the data.
- **`operador-dashboard-hub`** refactor — already merged via PR-3 (commit `8d733ee`); F7.3 only adds the missing `window.bridge.imprimir(payload)` calls.
- **`formatCOP` deduplication with F2.x** — F5.2 inherits as a lint warning; F7.3 follows the same convention.
- **CI macOS codesign / `node-usb-mock` / VS Build Tools preflight** — F5.1 follow-ups; not blocking F7.3.
- **Workspace-class `tsc` cascade in `electron/{main,preload,kiosko,bridge}.ts`** — F5.1 follow-up (MEDIUM); F7.3 verifies with B-prime scoped `tsc` pattern (Engram #1742).
- **`global.d.ts` Buffer polyfill** — already shipped in F5.2 (commit `f54c4ef`); F7.3 reuses it.
- **e2e `printer.spec.ts`** — sandbox F.6 has no exercisable USB device; defer per F5.1/F5.2/F6.x precedent.
- **i18n keys** — no new keys needed (tiquete text is Spanish by construction; UI labels for the two call sites reuse existing `facturacion:pago.*` namespace).
- **CU-15S `medioPago` derivation** — backend's `factura_pagos.medio_pago` is the source; F7.3's `SalidaPayload.medioPago` is caller-supplied per F5.2 R4 (no hidden coupling).
- **PDF width policy beyond DEC-SUC-08** — already shipped verbatim; F7.3 reuses `PAGE_RULE`.
- **New IPC channel** — DEC-SUC-19 single-instance preserved; F5.1 IPC shape unchanged.

## Commit Strategy

Three commits, single PR, work-unit per `work-unit-commits` skill. Each commit is a reviewable work unit. Tests live with code per the work-unit-commits skill rule, but commit 3 is wide because the wiring additions are operationally one work unit ("wire both call sites so Fase 8 can drive them").

| # | Conventional Commit | Files | LOC |
|---|---------------------|-------|-----|
| 1 | `feat(print): complete CU-15S 19-field contract in buildSalidaBody` | `escposBuilder.ts` (+40), `escposTemplates.ts` (+60 for factories — split with commit 3 if needed) | ~100 |
| 2 | `feat(print): complete CU-15SM 15-field contract with mensualidad sello` | `escposBuilder.ts` (+25) | ~25 |
| 3 | `feat(print): mirror CU-15S/CU-15SM in fallback HTML, wire call sites, add byte tests` | `fallbackBrowser.ts` (+60), `SalidaPanel.tsx` (+30), `PagoSheet.tsx` (+25), `__tests__/escposBuilder.salida.test.ts` (+170), `tsconfig.f7-3-verify.json` (+14), remaining `escposTemplates.ts` factory work | ~299 |

**Total**: ~424 LOC across 3 commits. Below the 800-LOC single-PR budget. Tests bundled with code in commit 3 (work-unit-commits "Keep tests with code"). Conventional Commit messages cite the WHY (DEC-SUC-27 ordering, plan.md 19/15-field contract, plan.md line 1816 test name) rather than the WHAT.

**Branch strategy**: `feature/hu-f7-3-tiquetes-salida` branched from `dev`, target `dev`, merge strategy `--ff-only` (or `--no-ff` if rebase is needed). Per AGENTS.md §Gitflow Estricto rule 8: feature branch deleted locally + remotely after merge. Per rule 9: post-merge Vite cache invalidation step (`.vite/` deps cache fresh).

**Pre-merge gate**: `git fetch --prune origin`; `gh pr create --base dev --head feature/hu-f7-3-tiquetes-salida --title "feat(print): HU-F7.3 tiquetes de salida CU-15S/CU-15SM" --body "<WHY per proposal §Approach + verification matrix>"`. Per AGENTS.md §Git identity for sub-agent work: sub-agent identity is `gentle-ai-sub-agent`; orchestrator MUST use `Parkos Dev <dev@parkos.local>` for the merge commit to prevent AI attribution trailers on the squash (the informational `infra/scripts/clean_coauthored_trailers.sh` script inventories affected commits if retroactive cleanup is needed on a future release branch — Engram session #1353).

## References

- **Plan contract**: `plan.md` lines 1779–1826 — the HU-F7.3 canonical contract (verbatim 19/15-field lists, sello decision, sequence correction, atomic tasks, test name)
- **Per-change spec**: `openspec/changes/hu-f7-3-tiquetes-salida/specs/operacion/spec.md` — 18 scenarios across REQ-OPS-143..145
- **Canonical spec delta**: `openspec/specs/operations/spec.md` lines 5826–5997 — REQ-OPS-143..145 ADDED (Mechanical Copy Contract preserved: pre-append SHA-256 `50FB12B53E37B4CB01E485DD3DE63EEC9D0E32AAACEBB48787EE3DF924B9703C` over 512004 bytes)
- **F6.2 archive precedent**: `openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/design.md` + `verify-report.md` + `archive-report.md` — primary reference for builder + HTML mirror + byte-fixture test pattern + B-prime scoped tsc
- **F5.1 archive precedent**: `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/` — IPC channel `bridge.imprimir({ buffer })`, `PARKOS_PRINTER_DISABLED=1` env, retry queue
- **F5.2 archive precedent**: `openspec/changes/archive/2026-09-17-fase-5-2-escpos-builder-fallback/` — `escposBuilder.build(tipo, payload)`, `fallbackBrowser.print(payload)`, Buffer polyfill, dispatcher, 4-type Zod schemas, `escText2x()`/`escTextReset()` helpers, `formatFechaCorta()`
- **F6.1 archive precedent**: `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/` — `IngresoPanel.tsx:75–86` `openSuccessWithAutoPrint` pattern that `SalidaPanel.tsx` mirrors
- **Existing builder source**: `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 240–301 (the diverging skeleton this design fixes)
- **Existing HTML mirror source**: `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` lines 59 (`PAGE_RULE`), 182 (`renderSalidaHtml`), 208 (`renderSalidaMensualidadHtml`)
- **Existing schemas**: `apps/electron-sucursal/src/lib/print/escposTemplates.ts` lines 369 (`salidaPayloadSchema`), 385 (`salidaMensualidadPayloadSchema` with `esMensualidad: z.literal(true)`), 449 (TIQUETE_TIPOS union)
- **Existing dispatcher**: `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 391–427 (`build()` routes `'salida'` / `'salida-mensualidad'`)
- **Existing call sites**: `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (mensualidad branch) + `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (post-200 branch)
- **Bridge contract**: `apps/electron-sucursal/electron/bridge.d.ts` (imprimir channel) + `apps/electron-sucursal/electron/types/print.ts:28` (`printPayloadSchema`)
- **AGENTS.md**: Architectural Principles §1–3 (Audit-First, Bi-Temporal, C/Q/U operation contract); §Gitflow Estricto (commit identity, branch protection, merge strategy)
- **Canonical print spec**: `openspec/specs/impresion.md` (F5.1+F5.2+F6.2 merged)
- **Engram patterns**: #1742 (B-prime scoped tsc pattern, F4.3/F5.1/F5.2/F6.1/F6.2 archive precedent); #1736 (stale-branch-ref pattern); #1762 (Mechanical Copy Contract); #1776 (apply-progress convention)
- **`openspec/config.yaml`** `rules.tasks`: 800 LOC single-PR budget; 400 LOC chained-PR threshold

## Next Step

Ready for `sdd-tasks`. Tasks phase will produce `openspec/changes/hu-f7-3-tiquetes-salida/tasks.md` with: (i) per-commit task breakdown (3 commits × ~6 tasks each = ~18 atomic tasks); (ii) verification command receipts (vitest + scoped tsc + eslint per Verify Gates above); (iii) commit-message bodies (per §Commit Strategy above, citing DEC-SUC-27 / plan.md lines / REQ-OPS-143..145); (iv) post-merge Vite cache invalidation step (per AGENTS.md §"Post-merge: invalidar Vite cache"); (v) B-prime scoped tsc recipe (Engram #1742).

---

## Appendix A — Byte-level field assertion matrix (`escposBuilder.salida.test.ts`)

### Case 1 — CU-15S, 19 fields (`plan.md` lines 1789–1808)

| # | plan.md label | Assertion | Note |
|---|---------------|-----------|------|
| 1 | `PARKINGOS` | `Buffer.indexOf('PARKINGOS') >= 0` | Encabezado fijo (escposBuilder.ts:244) |
| 2 | `${empresa.nombre}` | contains mock string (e.g. `PARKINGOS S.A.S.`) | Builder line 246 |
| 3 | `${empresa.direccion}` | contains mock string | Builder line 248 |
| 4 | `NIT ${empresa.nit}` | contains `NIT 900123456-7` | Builder line 247 |
| 5 | `${empresa.regimen}` | contains mock string | Builder line 249 |
| 6 | `Operario: ${operario}` | contains literal | **NEW** — ADR-01 |
| 7 | `*** TIQUETE DE SALIDA ***` | contains literal | **REPLACE** of `'*** SALIDA ***'` |
| 8 | `Folio: ${folio}` | contains `Folio:` literal | Builder line 255 |
| 9 | `Tarifa: ${formatCOP(tarifaAplicada)}/hora` | contains `Tarifa:` literal + `/hora` | **NEW** — ADR-01 |
| 10–12 | `Entrada: …` + `Salida: …` + `Tiempo: …` | contains `Entrada:`, `Salida:`, `Tiempo:` | Builder lines 257–259 |
| 13 | `Tiempo: ${tiempoTotal}` | contains literal | Builder line 259 (already present) |
| 14 | `Subtotal: ${formatCOP(subtotal)}` | contains literal | Builder line 261 |
| 15 | `IVA: ${formatCOP(iva)}` | contains literal | Builder line 262 |
| 16 | `TOTAL: ${formatCOP(total)}` | contains literal | Builder line 264 (bold) |
| 17 | `Medio de pago: ${medioPago}` | contains literal | Builder line 266; campo 17 — Fase 8 dependency |
| 18 | `Placa: ${placa}` | contains literal | Builder line 256 |
| 19a | `Horario: ${horarioAtencion}` | contains literal | **NEW** — ADR-01 |
| 19b | `Poliza RC: ${polizaRC}` | optional guard | Builder line 269 (already correct) |
| 19c | `Resolucion FE: ${resolucionFE}` | contains literal | Builder line 267 (already correct) |
| 19d | `Observaciones: ${observaciones}` | optional guard | **NEW** — ADR-01 |
| 20 | `;QR:${qrDataUrl}` | contains `;QR:` marker before footer | **NEW** — DEC-SUC-26 |
| 21 | `;LOGO:${logoText \|\| 'OK'}` | contains `;LOGO:` marker before footer | **NEW** — DEC-SUC-26 |
| (footer) | `Gracias por su visita.` | contains literal | Builder line 271 |

**Sentinel byte assertion** (sello):

```
expect(buf.indexOf(Buffer.from([0x1B, 0x21, 0x30]))).toBeGreaterThanOrEqual(0);
expect(buf.indexOf('*** TIQUETE DE SALIDA ***')).toBeGreaterThan(
  buf.indexOf(Buffer.from([0x1B, 0x21, 0x30]))
);
expect(buf.indexOf(Buffer.from([0x1B, 0x21, 0x00]))).toBeGreaterThan(
  buf.indexOf('*** TIQUETE DE SALIDA ***')
);
```

**Optional-branch scenario**: `polizaRC=null AND observaciones=null` → buffer SHALL NOT contain `Poliza RC:` and SHALL NOT contain `Observaciones:`; buffer SHALL still contain `Horario:` and `Resolucion FE:` (non-optional).

**DEC-SUC-26 purity scenario**: buffer SHALL NOT contain rasterization opcodes (no `0x1D` GS prefix outside the trailing `cutPartial()` at `0x1D 0x56 0x00` — `escposBuilder.ts` `cutPartial()` helper).

**Purity scenario**: `vi.spyOn(window, 'print')` + `build('salida', payload)` → `expect(spy).not.toHaveBeenCalled()`.

### Case 2 — CU-15SM, 15 fields + sello (`plan.md` line 1810)

| # | plan.md label | Assertion | Note |
|---|---------------|-----------|------|
| 1–6 | (same as Case 1: encabezado, empresa, dirección, NIT, régimen, operario) | yes | Builder lines 279–284 + **NEW** Operario at line 294 |
| 7 | `*** PAGO CON MENSUALIDAD ***` | contains literal | Builder line 287 (already correct per plan.md line 1787) |
| 8 | `Folio: ${folio}` | contains literal | Builder line 290 |
| 9 | `Tiempo: ${tiempoTotal}` | contains literal `Tiempo: 1h 30m` for `tiempoTotal = "1h 30m"` | **NEW** — ADR-01 (campo 13 of plan.md line 1810) |
| 10–12 | `Entrada: …` + `Salida: …` | contains both | Builder lines 292–293 |
| 13 | `Placa: ${placa}` | contains literal | Builder line 291 |
| 14a | `Horario: ${horarioAtencion}` | contains literal | Builder line 295 (already correct) |
| 14b | `Poliza RC: ${polizaRC}` | optional guard | Builder line 297 (already correct) |
| 14c | `Resolucion FE: ${resolucionFE}` | contains literal | **NEW** — ADR-01 |
| 14d | `Observaciones: ${observaciones}` | optional guard | **NEW** — ADR-01 |
| 15 | `;QR:${qrDataUrl}` | contains `;QR:` marker before footer | **NEW** — DEC-SUC-26 |
| 16 | `;LOGO:${logoText \|\| 'OK'}` | contains `;LOGO:` marker before footer | **NEW** — DEC-SUC-26 |
| (footer) | `Conserve este tiquete como soporte.` | contains literal | Builder line 299 |

**Sentinel byte assertion** (mensualidad distinguisher per `plan.md` line 1816):

```
expect(buf.indexOf(Buffer.from([0x1B, 0x21, 0x30]))).toBeGreaterThanOrEqual(0);
const selloBytes = Buffer.from('*** PAGO CON MENSUALIDAD ***\n', 'utf8');
expect(buf.indexOf(selloBytes)).toBeGreaterThan(
  buf.indexOf(Buffer.from([0x1B, 0x21, 0x30]))
);
expect(buf.indexOf(Buffer.from([0x1B, 0x21, 0x00]))).toBeGreaterThan(
  buf.indexOf(selloBytes)
);
```

**Ausencia-de-cobro scenario**: buffer SHALL NOT contain `Subtotal:`, `IVA:`, `TOTAL:`, or `Medio de pago:` (CU-15SM has no cobro per `plan.md` line 1810).

**Discriminator scenario**: payload without `esMensualidad: true` → `build('salida-mensualidad', payload)` SHALL throw `EscposPayloadMissingFieldError` (F5.2 R1 + Zod `z.literal(true)` at `escposTemplates.ts:400`).

**Dynamic-encabezado scenario**: payload with `empresa.nombre = "Mi Parqueadero XYZ"` → buffer SHALL contain `Mi Parqueadero XYZ` as the encabezado (NOT corpus-fixed `PARQUEADERO PUBLICO` per `plan.md` line 1810 corrected).

**Purity scenario**: identical to Case 1.

## Appendix B — Field order correspondence (byte builder vs HTML fallback)

Per F5.2 R4 (purity) and F6.2 (HTML mirror pattern), the field order in `escposBuilder.buildSalidaBuffer()` must correspond to the field order in `fallbackBrowser.renderSalidaHtml()`. This is verified by **PR-review inspection only** (per F6.2 precedent; `renderEntradaTiqueteHtml` is also uncovered by automated tests in `escposBuilder.entrada.test.ts`).

| # | Byte buffer expression | HTML fallback expression |
|---|------------------------|---------------------------|
| 1 | `escBoldOn() + utf8('PARKINGOS\n') + escBoldOff()` | `<h1>PARKINGOS</h1>` |
| 2–5 | `${empresa.nombre/direccion/nit/regimen}` | `<p>...</p>` |
| 6 | `Operario: ${operario}` | `<p>Operario: ...</p>` |
| 7 | sello (text-2x) | `<h2>*** TIQUETE ... ***</h2>` |
| 8 | `Folio: ${folio}` | `<p>Folio: ...</p>` |
| 9 (CU-15S only) | `Tarifa: ${formatCOP(tarifaAplicada)}/hora` | `<p>Tarifa: .../hora</p>` |
| 10–12 | `Entrada: …` + `Salida: …` + `Tiempo: …` | `<p>Entrada: ...</p>` + `<p>Salida: ...</p>` + `<p>Tiempo: ...</p>` |
| 13 | `Placa: ${placa}` | `<p>Placa: ...</p>` |
| 14–16 (CU-15S only) | `Subtotal:` + `IVA:` + `TOTAL:` | `<p>Subtotal: ...</p>` + `<p>IVA: ...</p>` + `<p><strong>TOTAL: ...</strong></p>` |
| 17 (CU-15S only) | `Medio de pago: ${medioPago}` | `<p>Medio de pago: ...</p>` |
| 18 | `Resolucion FE: ${resolucionFE}` | `<p>Resolucion FE: ...</p>` |
| 19 | `Poliza RC: ${polizaRC}` (optional) | `<p>Poliza RC: ...</p>` (optional) |
| 19b | `Horario: ${horarioAtencion}` | `<p>Horario: ...</p>` |
| 19c | `Observaciones: ${observaciones}` (optional) | `<p>Observaciones: ...</p>` (optional) |
| 20, 21 | `;QR:` / `;LOGO:` text markers | `<img src="${qrDataUrl}" />` + `<img src="${logoDataUrl}" />` |
| (footer) | `Gracias por su visita.` (CU-15S) / `Conserve este tiquete como soporte.` (CU-15SM) | `<p>Gracias por su visita.</p>` / `<p>Conserve este tiquete como soporte.</p>` |

If the field order drifts in a future commit, a reviewer catches it on the diff, not a test.

## Appendix C — Conventional Commit messages

Per AGENTS.md §Conventional Commits and `work-unit-commits` skill, three commits per §Commit Strategy above.

```
feat(print): complete CU-15S 19-field contract in buildSalidaBody

Bring the F5.2 skeleton at apps/electron-sucursal/src/lib/print/
escposBuilder.ts (lines 240-273) into verbatim alignment with the
19-field list in plan.md lines 1789-1808 (HU-F7.3 CU-15S).

Changes:
- sello literal "*** SALIDA ***" -> "*** TIQUETE DE SALIDA ***"
  (campo 7 per plan.md line 1794)
- add Operario, Tarifa, Horario lines (campos 6, 9, 19)
- append DEC-SUC-26 QR and LOGO text markers (campos 20-21)
- add optional Observaciones branch (campo 19 subset)

Refs: HU-F7.3, REQ-OPS-143, DEC-SUC-27 (deferred print ordering)
```

```
feat(print): complete CU-15SM 15-field contract with mensualidad sello

Bring the F5.2 skeleton at apps/electron-sucursal/src/lib/print/
escposBuilder.ts (lines 275-301) into verbatim alignment with the
15-field list in plan.md line 1810 (HU-F7.3 CU-15SM).

Changes:
- add Tiempo line (campo 13)
- add Resolucion FE line (campo 14)
- append DEC-SUC-26 QR and LOGO text markers
- add optional Observaciones branch
- verify sello "*** PAGO CON MENSUALIDAD ***" at text-2x
  (0x1B 0x21 0x30) is preserved verbatim from the existing
  skeleton at line 286-287 (plan.md line 1787)

Refs: HU-F7.3, REQ-OPS-144, DEC-SUC-27 (immediate print ordering)
```

```
feat(print): mirror CU-15S/CU-15SM in fallback HTML, wire call sites, add byte tests

i. fallbackBrowser.renderSalidaHtml (line 182) and
   renderSalidaMensualidadHtml (line 208): semantic HTML mirror
   with same field order as the byte builder, <img> for QR/logo,
   the DEC-SUC-08 '@page{size:80mm auto;margin:2mm}' CSS rule
   unchanged (line 59).

ii. SalidaPanel.tsx (mensualidad-confirm branch) adds
    await window.bridge.imprimir({...}) mirroring
    IngresoPanel.tsx:80 — DEC-SUC-27 immediate clause.

iii. PagoSheet.tsx (post-200 branch) declares the same
     bridge.imprimir call with a // TODO: Fase 8 anchor comment,
     since the post-pago trigger site is supplied by HU-F8.1+ —
     DEC-SUC-27 deferred clause.

iv.  escposTemplates.ts adds buildSalidaPayload + buildSalidaMensualidadPayload
     factories (ADR-06) that convert ER rows to Zod-validated payloads.

v.   New escposBuilder.salida.test.ts with 2 byte-fixture cases
     per plan.md line 1816 (CU-15S 19 fields; CU-15SM 15 fields
     with 0x1B 0x21 0x30 sentinel + discriminator + dynamic-encabezado).

vi.  New tsconfig.f7-3-verify.json B-prime scoped tsc config
     (Engram #1742 pattern, F6.2 precedent).

Refs: HU-F7.3, HU-F8.1, REQ-OPS-143/144/145, plan.md lines 1816/1789-1810
```

No `Co-authored-by:` trailers; git author `Parkos Dev <dev@parkos.local>`.

## Appendix D — Why this is a single PR (not chained)

`work-unit-commits` §SDD Relationship table: forecast <400 LOC ⇒ single PR, no chained-PR scaffolding needed. F7.3 forecast is ~424 LOC (slightly above the proposal's 350 estimate because ADR-06 adds ~60 LOC for the two factories) — still well below the 800-LOC single-PR budget from `openspec/config.yaml` `rules.tasks`. The 3 commits are grouped into a single PR because:

1. **Each commit is internal to the same user-facing capability** ("tiquete de salida y salida-mensualidad impresos según DEC-SUC-27").
2. **The contract is cross-file** (DEC-SUC-26 marker emission in builder must match the `<img>` tag emission in HTML fallback; the `;QR:`/`;LOGO:` markers cannot be added to the byte buffer without the `<img>` mirror or the layout breaks).
3. **The wire sites depend on the builder fixes** (`PagoSheet.tsx` calls `escposBuilder.build('salida', payload)` — if the builder is missing `Operario`/`Tarifa`/`Horario`/markers, the printed tiquete is wrong regardless of whether the call site exists).
4. **Reviewers benefit from seeing builder + HTML + wiring + tests in one PR diff** because the contracts interlock field-for-field.

Splitting into chained PRs would invite partial-review error (e.g., "this PR only fixes the builder, not the HTML — the field order is correct in bytes but wrong in pixels"). The exception in `work-unit-commits` ("If the implementation actually exceeds 350 LOC during apply, the orchestrator can promote to chained-PR sequence") applies if implementation tightens < 350 LOC, but does not apply here since the forecast is already above threshold but still single-PR-feasible under the 800-LOC cap. Orchestrator can still escalate to chained PR if actual implementation exceeds 800 LOC during `sdd-apply`.

---

**Status**: success — design contract complete. All 6 SDD design sections covered (Approach, ADR × 6, Data Flow × 3 ASCII diagrams, File Changes × 9, Interfaces, Testing Strategy, Threat Matrix, Migration, Open Questions = none, Verify Gates, Risk Mitigations × 13, Out of Scope × 11, Commit Strategy, References). Ready for `sdd-tasks`.