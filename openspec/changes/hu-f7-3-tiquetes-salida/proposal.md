# Proposal: HU-F7.3 — Tiquetes de salida (CU-15S) y salida-mensualidad (CU-15SM), impresos después del pago

> Change key: `hu-f7-3-tiquetes-salida`
> Plan contract: `plan.md` lines 1779–1826 (HU-F7.3 — Fase 7 Parte I)
> Project: `parkos` (Engram-scoped)
> Phase: `propose` (this artifact)
> Forecast LOC: 350 (under the 800-LOC single-PR budget from `openspec/config.yaml` `rules.tasks`)

## Intent

`plan.md` line 1783 records an obligatory sequence correction: the original CU-03 corpus calls for the salida tiquete to be printed at its own step 8, **before** any payment exists. CU-15S, however, requires the `medio de pago` field (campo 17 of the 19-field list, `plan.md` line 1804) — a value that only materializes **after** CU-04 confirms payment. The corpus cited the wrong CU for that field; plan.md treats that citation error as a silent correction. The product-correct behavior is therefore:

- **CU-15S** (rotation salida) — print **only after** the Fase 8 cobro returns HTTP 200. This is the `DEC-SUC-27` reordering decision stated on `plan.md` line 1783.
- **CU-15SM** (mensualidad salida) — print **immediately** when the salida is recorded, because no cobro is involved (DEC-SUC-27 second clause, same line).

This proposal closes the renderer-side gap that makes that contract executable. The output buffers (`buildSalidaBuffer`, `buildSalidaMensualidadBuffer`) and the `build()` dispatcher were scaffolded in F5.2 (`buildSalidaBody` lines 240–273 of `apps/electron-sucursal/src/lib/print/escposBuilder.ts`, `buildSalidaMensualidadBody` lines 275–301), but both bodies diverge from the 19/15-field literal contract in `plan.md` lines 1786/1787/1789–1810. Likewise the `fallbackBrowser` HTML renderers (`renderSalidaHtml` line 182, `renderSalidaMensualidadHtml` line 208 of `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts`) ship only as entry-point skeletons with the same divergences. The two React call sites that will invoke the builders — `SalidaPanel.tsx` (mensualidad flow) and `PagoSheet.tsx` (post-pago flow) — were merged without the `window.bridge.imprimir(payload)` wiring that `IngresoPanel.tsx:80` and `TiqueteModal.tsx:69` already carry. A builder test exists for entrada (`escposBuilder.entrada.test.ts`) but not for salida (`plan.md` line 1816 calls for `escposBuilder.salida.test.ts`; confirmed missing).

The intent of this change is therefore narrow and contract-shaped: bring the two builders and the two HTML renderers into verbatim alignment with the 19/15-field plan.md contract, mirror the F6.2 call-site pattern into the two missing call sites per the DEC-SUC-27 ordering, and add the byte-fixture test plan.md line 1816 requires. Nothing else.

## Scope

### In scope (renderer-only, all on `apps/electron-sucursal/`)

| # | File | Change |
|---|------|--------|
| 1 | `src/lib/print/escposBuilder.ts` (`buildSalidaBody`, lines 240–273) | **Modify** — apply 7 field-level fixes (septo literal, operario, tarifaAplicada, horarioAtencion, polizaRC confirmation, qr+logo markers, observaciones) to satisfy the 19-field list in `plan.md` lines 1789–1808 |
| 2 | `src/lib/print/escposBuilder.ts` (`buildSalidaMensualidadBody`, lines 275–301) | **Modify** — apply 4 field-level fixes (tiempo, fecha+hora split, qr+logo markers, observaciones) to satisfy the 15-field list in `plan.md` line 1810 |
| 3 | `src/lib/print/fallbackBrowser.ts` (`renderSalidaHtml` line 182, `renderSalidaMensualidadHtml` line 208) | **Modify** — mirror the builder fixes in semantic HTML so `@page{size:80mm auto;margin:2mm}` (DEC-SUC-08, verbatim) fallback prints the same fields in the same order |
| 4 | `src/features/operacion/components/SalidaPanel.tsx` (mensualidad-confirm branch) | **Modify** — add the `await window.bridge.imprimir(payload)` call mirroring `IngresoPanel.tsx:80` for the **immediate** CU-15SM print (DEC-SUC-27 second clause) |
| 5 | `src/features/facturacion/components/PagoSheet.tsx` (post-200 branch) | **Modify** — add the `await window.bridge.imprimir(payload)` call mirroring `IngresoPanel.tsx:80` for the **deferred** CU-15S print (DEC-SUC-27 first clause); the field for `medioPago` becomes available here, not earlier |
| 6 | `src/lib/print/__tests__/escposBuilder.salida.test.ts` | **Create** — 2 byte-fixture cases exactly as `plan.md` line 1816 describes: 19-field CU-15S + 15-field CU-15SM with the `0x1B 0x21 0x30` text-2x sentinel asserted by literal byte sequence |

### Out of scope (explicit non-goals)

- **Backend** (`backend/packages/parkos_core/`, Alembic, SQL) — zero changes. The CU-15S `medioPago`, the `facturas`/`factura_pagos` rows, and the `factura_electronica` issuance are Phase 8 (plan.md lines 1830+).
- **A-05 `log_transaccional` INSERT endpoint** — backend concern. F6.2 documents the audit-row shape; the actual wiring of `accion='impreso'` rows after a successful print is **inherited by F8**, not introduced here. Documented in plan.md's audit-first principle.
- **Fase 8 pago modal UI** — separate cycle (`HU-F8.1` onwards, plan.md line 1832+). The `PagoSheet.tsx` call site is being **prepared**, not driven: the trigger is a hole that Fase 8 will fill. F7.3 wires the call, Fase 8 supplies the data.
- **`operador-dashboard-hub`** refactor — already merged via PR-3 (commit `8d733ee`); F7.3 only adds the missing `window.bridge.imprimir(payload)` calls.
- **`formatCOP` deduplication with F2.x** — F5.2 inherits as a lint warning; F7.3 follows the same convention.
- **CI macOS codesign / `node-usb-mock` / VS Build Tools preflight** — F5.1 follow-ups; not blocking F7.3.
- **Workspace-class `tsc` cascade in `electron/{main,preload,kiosko,bridge}.ts`** — F5.1 follow-up (MEDIUM); F7.3 verifies with the B-prime scoped `tsc` pattern (engram id 1742) the same way F5.x/F6.x already do.
- **`global.d.ts` Buffer polyfill** — already shipped in F5.2 (commit `f54c4ef`); F7.3 reuses it.
- **e2e `printer.spec.ts`** — sandbox F.6 has no exercisable USB device; defer per the F5.1/F5.2/F6.x precedent (byte fixtures are the verification boundary).

## Capabilities

> Section is the contract with `sdd-spec`. Each entry names the file the spec phase will create or the delta spec the spec phase will write.

### New capabilities

- `tiquete-salida-cu15s`: render the CU-15S tiquete (19 literal fields + QR + logo) as both an ESC/POS byte buffer and an HTML fallback that prints at `80mm auto / 2mm` margins.
- `tiquete-salida-mensualidad-cu15sm`: render the CU-15SM tiquete (15 literal fields + sello `*** PAGO CON MENSUALIDAD ***` at text-2x `0x1B 0x21 0x30`) as both an ESC/POS byte buffer and an HTML fallback.
- `salida-print-wiring`: trigger the `build('salida', payload)` and `build('salida-mensualidad', payload)` paths from the React renderer at the **two** correct moments (immediate on mensualidad-confirm, deferred on pago-200), passing `SalidaPayload` / `SalidaMensualidadPayload` whose fields are already populated per Fase 4 / Fase 8.

### Modified capabilities

- `tiquete-entrada-cu15e` (F6.2): no requirement change; the existing tests (`escposBuilder.test.ts`, `escposBuilder.entrada.test.ts`) stay as-is and the existing `escposBuilder.ts` / `fallbackBrowser.ts` skeleton is not removed. F7.3 adds fields, never subtracts.
- `puente-impresion-bridge-f5-1` (F5.1): no behavior change to the IPC channel (`bridge.imprimir({ buffer })`); payload shape for `salida` and `salida-mensualidad` slots is exercised in the new byte tests but the wire signature is unchanged.

## Approach

### Builder fixes (`escposBuilder.ts`)

`buildSalidaBody(payload)` currently emits the 17-line body at `apps/electron-sucursal/src/lib/print/escposBuilder.ts:240–273`. The seven divergences from the 19-field contract in `plan.md` lines 1789–1808 are:

| Field # | Plan.md requirement | Current implementation | Action |
|--------:|---|---|---|
| 7 (septo) | Literal `*** TIQUETE DE SALIDA ***` | Line 252: `'*** SALIDA ***'` | **Replace** the literal |
| 6 (sexto) | `Operario: ${payload.operario}` | **Missing** | **Insert** — `payload.operario` is inherited from `entradaPayloadSchema.extend(...)` at `escposTemplates.ts:369` |
| 9 (noveno) | `Tarifa: ${formatCOP(payload.tarifaAplicada)}/hora` | **Missing** | **Insert** — `payload.tarifaAplicada` is inherited from `entradaPayloadSchema.extend(...)` |
| 19 (diecinueveavo) | `Horario: ${payload.horarioAtencion}` | **Missing** | **Insert** — inherited |
| 19 (catorceavo subset) | `Poliza RC:` is already guarded by `payload.polizaRC` truthy (line 269) | Already correct | **Keep as-is** |
| 19 (quinceavo subset) | `Observaciones: ${payload.observaciones}` (when set) | **Missing optional branch** | **Insert** optional `if (payload.observaciones) ...` |
| 20, 21 (QR / logo) | DEC-SUC-26 markers `;QR:${qrDataUrl}` and `;LOGO:${logoDataUrl or 'OK'}` | **Missing** | **Append** before final `Gracias por su visita.` newline, mirroring the F6.2 entrance pattern exactly |

`buildSalidaMensualidadBody(payload)` at `apps/electron-sucursal/src/lib/print/escposBuilder.ts:275–301` has the four divergences from the 15-field contract in `plan.md` line 1810:

| Action | Justification |
|---|---|
| **Insert** `Tiempo: ${payload.tiempoTotal}` between salida+poliza blocks | Field 13 in `plan.md` line 1810 |
| **Split** `formatFechaCorta(payload.fechaEntrada)` into `Entrada: dd/MM/yyyy HH:mm` rendered as two separate lines (today the format joins them) | Per plan.md line 1810 spec, fecha entrada (date) and hora entrada (time) are field 10+11 of entrada but kept concatenated here for compactness; the test will assert the joined form |
| **Insert** QR + logo markers before soporte line | DEC-SUC-26 applicability, same as F6.2 |
| **Insert** optional `Observaciones:` block | Field 15 of plan.md line 1810 |

Field 7's sello `'*** PAGO CON MENSUALIDAD ***'` is already correct at line 287 (matches plan.md line 1787). The `0x1B 0x21 0x30` text-2x ESC/POS opener (`escText2x()`) is already wired before it on line 286. **The byte fixture for the sello is therefore the canonical assertion**: `Buffer.from([0x1B, 0x21, 0x30, ...'*** PAGO CON MENSUALIDAD ***\n', 0x1B, 0x21, 0x00])` must appear verbatim in the test's expected buffer.

### Fallback HTML mirror (`fallbackBrowser.ts`)

`renderSalidaHtml` (line 182) and `renderSalidaMensualidadHtml` (line 208) in `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` must mirror the builder fixes in semantic HTML. The DEC-SUC-08 `@page{size:80mm auto;margin:2mm}` CSS rule is already injected by `PAGE_RULE` (line 59). The renderers must produce the same field ORDER as the byte buffer (encabezado → empresa → NIT → dirección → régimen → operario → sello → folio → tarifa → ...) so the printed-on-fallback layout matches the printer-buffer layout field-for-field, even though one is a stream of bytes and the other is markup. QR/logo render as `<img>` with their data URLs verbatim (line 168 already demonstrates this for entrada). Empty `logoDataUrl` keeps the `▢` glyph (DEC-SUC-08 placeholder, line 145).

### Wiring

Two call sites, mirroring `IngresoPanel.tsx:80`:

```typescript
// SalidaPanel.tsx — DEC-SUC-27 immediate clause
// After the mensualidad-confirm step returns success, build the payload
// in the existing format (already populated by Fase 4) and call:
const buffer = await window.bridge.imprimir({
  tipo: 'salida-mensualidad',
  payload: buildSalidaMensualidadPayloadFromCurrentIngreso(...),
});
```

```typescript
// PagoSheet.tsx — DEC-SUC-27 deferred clause
// Inside the post-200 success branch that Fase 8 will populate,
// after `factura_pagos.medio_pago` and `factura_electronica.cufe`
// become available, call:
const buffer = await window.bridge.imprimir({
  tipo: 'salida',
  payload: buildSalidaPayloadFromFactura(currentFactura, ...),
});
```

The `bridge.imprimir({ buffer })` IPC channel comes from F5.1 (PR #4, commit `b987cf29`). The auto-print precedent is `IngresoPanel.tsx:80` (F6.1, PR #6, commit `2026-09-17T04:06:41Z`). The fallback `print()` from `fallbackBrowser.ts` ships for cases where the printer does not respond; `bridge.imprimir({ buffer })` calls `print(tipo, payload)` when the printer handshake fails (caller-driven signal, per F5.1 bridge). No new IPC shape is needed.

### Test (`escposBuilder.salida.test.ts`)

Two cases, exactly as `plan.md` line 1816 describes:

1. **CU-15S, 19 fields** — construct a fully-populated `SalidaPayload`, call `buildSalidaBuffer(payload)`, assert each of the 19 literal labels appears at least once in the buffer (`Buffer.indexOf(label) !== -1`), and assert the byte sequence `0x1B 0x21 0x30` (the text-2x ESC/POS opener preceding the sello at line 244 of the builder's `escText2x()` helper) appears with the `'*** TIQUETE DE SALIDA ***'` literal between two text-2x sentinels.

2. **CU-15SM, 15 fields + sello** — same shape, assert the sello bytes are `'*** PAGO CON MENSUALIDAD ***'` between the text-2x opener `0x1B 0x21 0x30` and the text-2x reseter `0x1B 0x21 0x00`, and that all 15 fields appear.

Test boundary uses the same Vitest patterns as F5.2 (`escposBuilder.test.ts`) and F6.2 (`escposBuilder.entrada.test.ts`). The Buffer polyfill from F5.2's `global.d.ts` is in scope without re-import.

### Work unit commits

Forecast 350 LOC against the 800-LOC single-PR budget. **Single PR to `dev`**, 3 commits, each a reviewable work unit per `work-unit-commits`:

| Commit | Type | Scope | Files touched | LOC delta |
|---|------|-------|---------------|-----------|
| 1 | `feat(print): complete CU-15S 19-field contract` | All 7 builder fixes for salida + schema unchanged | `escposBuilder.ts` (+40), `escposTemplates.ts` (0) | ~40 |
| 2 | `feat(print): complete CU-15SM 15-field contract with mensualidad sello` | All 4 builder fixes for salida-mensualidad | `escposBuilder.ts` (+25) | ~25 |
| 3 | `feat(print): mirror CU-15S/CU-15SM fixes in fallback HTML` + `+ wire call sites` + `+tests` | Renderer + test additions | `fallbackBrowser.ts` (+60), `SalidaPanel.tsx` (+30), `PagoSheet.tsx` (+25), `__tests__/escposBuilder.salida.test.ts` (+170) | ~285 |

Total forecast: 350 LOC. Total commits: 3 (fits the chained-PR "low risk / 1 PR" track from `work-unit-commits`). Tests live with code per the work-unit-commits skill rule, but commit 3 is a wide commit because the wiring additions are operationally one work unit ("wire both call sites so Fase 8 can drive them"). If the line count exceeds 350 during implementation, commits 1+2 stay together as a chained `feature/hu-f7-3-tiquetes-salida-builder` PR and commit 3 lands as a chained `feature/hu-f7-3-tiquetes-salida-wire` PR.

## Affected areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 240–301 | Modified | 7 builder fixes for salida + 4 builder fixes for salida-mensualidad to honor the 19/15-field contract (`plan.md` lines 1789–1810) |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` lines 182–228 | Modified | Mirror builder fixes in semantic HTML so the `@page{size:80mm auto;margin:2mm}` fallback matches field-for-field |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (mensualidad branch) | Modified | Add `await window.bridge.imprimir(payload)` mirroring `IngresoPanel.tsx:80` — DEC-SUC-27 immediate clause |
| `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (post-pago branch) | Modified | Add `await window.bridge.imprimir(payload)` mirroring `IngresoPanel.tsx:80` — DEC-SUC-27 deferred clause; the call is wired but the post-200 trigger site is supplied by Fase 8 |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` | New | 2 byte-fixture cases exactly per `plan.md` line 1816 |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | **No change** | `salidaPayloadSchema` (line 369) and `salidaMensualidadPayloadSchema` (line 385) already have every field needed; no schema extension required |
| `apps/electron-sucursal/electron/main.ts` / `electron/preload.ts` / `electron/kiosko.ts` / `electron/bridge.ts` | **No change** | F5.1 IPC contract unchanged; `bridge.imprimir({ buffer })` is the wire shape |
| `backend/packages/parkos_core/` (any) | **No change** | Out of scope; backend is Phase 8 |
| `infra/` Alembic migrations | **No change** | Out of scope; no DB change |

## Risks

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Salida builder body diverges from plan.md literal byte string after refactor (e.g., label ordering) | Low | Byte-fixture test in `escposBuilder.salida.test.ts` asserts each of the 19 field labels appears; `Buffer.indexOf` is exact, not fuzzy. Re-running F5.2's purity round-trip (input → buffer → parse) gives a second boundary. |
| `PagoSheet.tsx` post-200 trigger is misread as "wire only", leaving the call site non-executable until Fase 8 | Medium | Proposal explicitly names the call site as a **hole that Fase 8 fills**: trigger is the post-200 callback returning success. The F7.3 commit adds the `await window.bridge.imprimir(...)` line commented as `// DEC-SUC-27: print after pago-200`. `// TODO: Fase 8` anchors the hand-off in code, visible in PR review. |
| Mensualidad sello bytes drift (`0x1B 0x21 0x30`) if `escText2x()` helper is touched upstream | Low | Test pins the literal byte sequence `Buffer.from([0x1B, 0x21, 0x30, ...0x1B, 0x21, 0x00])` between the sello literal. If `escText2x` ever changes, the test fails with a diff pointing at the helper. |
| Builder field count diverges between `escposBuilder.ts` and `fallbackBrowser.ts` HTML renderers | Medium | Both files modified in the same commit (per the work-unit-commits grouping) so they cannot drift at the commit boundary. Vitest byte test only covers the builder; HTML is covered by inspection (per F6.2 precedent, where `renderEntradaTiqueteHtml` is also uncovered by automated tests). |
| e2e `printer.spec.ts` not exercisable on sandbox F.6 | **Closed** (precedent) | Same precedent as F5.1/F5.2/F6.x: byte-fixture tests are the verification boundary. Documented as "N/A — sandbox F.6" in the apply-progress receipt. |
| PDF width policy ambiguity — does the 80mm `@page` translate to the local PDF printer driver? | Low | F6.2 already shipped this rule verbatim (`PAGE_RULE` in `fallbackBrowser.ts:59`) and `apps/electron-sucursal/package.json` printer config inherits it. |
| `PagoSheet.tsx` already imports things from `src/lib/print/*` and a circular import or test double leak appears | Low | Only `buildSalidaBuffer` / `buildSalidaMensualidadBuffer` are imported; both are already exported from `escposBuilder.ts` lines 350/359. No new import surface. |
| Workspace-class `tsc` cascade re-emits the F5.1 cascade | Low | B-prime scoped tsc pattern (engram id 1742) is the established recipe for verifying renderer files in isolation. Already proven in F5.x/F6.x. |
| B-prime scoped tsc passes but full-project tsc fails for unrelated reasons | Low | Same precedent: per `apply-progress`, full-project tsc is the quality gate but B-prime is the gating signal. Document any pre-existing cascades. |
| Buffer polyfill missing in a new test scope | **Closed** | F5.2's `global.d.ts` is in scope globally (`vitest.config.ts` already loads it); no re-shim needed. |

## Rollback plan

1. **`git revert <merge-commit>`** on `dev` removes all 5 modifications + 1 new test in a single operation.
2. `escposBuilder.ts` returns to its F5.2 scaffold state: `buildSalidaBuffer` and `buildSalidaMensualidadBuffer` still exist and produce a 17-/13-line body that validates against the Zod schemas, just without the 19/15-field contract fields. The `build()` dispatcher (lines 391–427) still routes `'salida'` and `'salida-mensualidad'` to their respective buffer functions. No consumers outside of `PagoSheet.tsx` and `SalidaPanel.tsx` would break.
3. `SalidaPanel.tsx` (mensualidad branch) and `PagoSheet.tsx` (post-pago branch) revert to their PR-3 (`8d733ee`) state — same behavior they had before the F7.3 wiring merge. Operators can still register entradas (F6.1/F6.2) and re-print them (`TiqueteModal.tsx:69`), because neither of those code paths touches the salida routing.
4. `escposBuilder.salida.test.ts` reverts with the revert commit; existing test suites (`escposBuilder.test.ts`, `escposBuilder.entrada.test.ts`, `escposBuilder.types.test.ts`, `escposBuilder.entrada.test.ts`) still pass because they cover independent `tipo` strings.
5. No data migration is required, no schema migration reverts needed (since no Alembic changes), no Docker image rollbacks needed (F7.3 is renderer-side, baked into the image at next release). Next release cycle picks up the rollback automatically.
6. **Operational rollback boundary**: any operator can disable salida-and-salida-mensualidad printing by setting `PARKOS_PRINTER_DISABLED=1` env var (already shipped in F5.1); the bridge returns 503 from `bridge.imprimir` before the builder is invoked, so the wiring does not block exit-entry flows.

Rollback does not require frontend redeploy because the rollback is a git revert on `dev`, picked up by the next image build. Rollback does not require schema replay because there is no schema change.

## Dependencies

**All merged to `dev` before F7.3 starts (per Engram backlog and PR close-events):**

- **F5.1** — PR #4, commit `b987cf29`, merged 2026-09-17T02:02:20Z. Provides the `bridge.imprimir({ buffer })` IPC channel on `window.bridge`.
- **F5.2** — PR #3, commit `f54c4ef`, merged 2026-09-17T04:26:31Z. Provides `escposBuilder.build(tipo, payload): Buffer`, `fallbackBrowser.print(payload)`, the Buffer polyfill in `global.d.ts`, the dispatcher, and the 4-type Zod schemas.
- **F6.1** — PR #6, commit `2026-09-17T04:06:41Z`. Provides `IngresoPanel.tsx:80` (the auto-print pattern F7.3 mirrors) and the A-05 `log_transaccional` `accion='impreso'` row-payload documentation.
- **F6.2** — PR #5, commit `2026-09-17T03:31:41Z`. Provides `EntradaPayload` and the `qrDataUrl` / `logoDataUrl` pattern that `salidaPayloadSchema` inherits via `extend(...)`, plus the F6.2 byte-fixture test pattern F7.3's `escposBuilder.salida.test.ts` follows.
- **`operador-dashboard-hub` PR-3** — commit `8d733ee`. Provides `SalidaPanel.tsx` (with the mensualidad branch) and `PagoSheet.tsx` ready to receive the `await window.bridge.imprimir(payload)` wiring.

**External requirement (already in dependencies tree):**

- The Phase 8 pago modal UI provides the post-200 trigger for `PagoSheet.tsx`'s `await window.bridge.imprimir(...)` call. F7.3 wires the call; Fase 8 supplies the trigger.

**Out-of-tree (not a dependency for F7.3 to land):**

- `log_transaccional` write path for `accion='impreso'`. F6.2 documented it; F8 will write the row. The `PagoSheet.tsx` site carries a `// TODO: Fase 8 inserts log_transaccional INSERT here` comment to make the inheritance visible.

## Success criteria

- [ ] `escposBuilder.salida.test.ts` passes locally and in CI for **both** byte-fixture cases (CU-15S 19 fields; CU-15SM 15 fields + `0x1B 0x21 0x30` sello bytes).
- [ ] All 19 field labels of CU-15S are discoverable in the `buildSalidaBuffer(payload)` output via `Buffer.indexOf`. All 15 field labels of CU-15SM are discoverable in the `buildSalidaMensualidadBuffer(payload)` output.
- [ ] `fallbackBrowser.renderSalidaTiqueteHtml` and `renderSalidaMensualidadTiqueteHtml` produce HTML whose visible field order matches the byte buffer field order (visible in PR review diff).
- [ ] `SalidaPanel.tsx` (mensualidad branch) calls `await window.bridge.imprimir({...})` with a fully populated `SalidaMensualidadPayload` immediately after the mensualidad-confirm step returns success. Compiles, does not regress the existing Vitest snapshot.
- [ ] `PagoSheet.tsx` (post-pago branch) declares the `await window.bridge.imprimir({...})` site at the post-200 callback position with a `// TODO: Fase 8` anchor comment explaining the Fase 8 hand-off. Compiles, does not regress the existing Vitest snapshot.
- [ ] No `backend/packages/parkos_core/` files are touched. No Alembic migrations are added. No SQL changes anywhere.
- [ ] `git diff --stat` against `origin/dev` shows ≤350 added lines and ≤30 modified lines (under the 800-line single-PR budget from `openspec/config.yaml` `rules.tasks`).
- [ ] Conventional Commit messages carry no `Co-Authored-By:` / AI attribution trailers. Git author is `Parkos Dev <dev@parkos.local>`. PR targets `dev`, never `main`.
- [ ] `git log --oneline -3` on the feature branch shows commits of the form `feat(print): ...` with bodies explaining the WHY (DEC-SUC-27 ordering, plan.md 19/15-field contract) rather than the WHAT (file rename, function extract).
- [ ] Branch is merged into `dev` before session close per `AGENTS.md` rule 8. Feature branch `feature/hu-f7-3-tiquetes-salida` is deleted locally and remotely post-merge.

## Architectural decisions cited

- **DEC-SUC-27** — sequence correction (`plan.md` line 1783). CU-15S prints after pago (deferred); CU-15SM prints immediately (immediate). Both decisions are honored verbatim by the wiring in `PagoSheet.tsx` (deferred) and `SalidaPanel.tsx` (immediate).
- **DEC-SUC-26** — QR + logo rasterization is the **caller's** responsibility (F5.1 bridge); builder emits text markers `;QR:${qrDataUrl}` and `;LOGO:${logoDataUrl or 'OK'}`. F7.3 follows the F5.2 R3 purity rule: no QR rendering in the builder.
- **DEC-SUC-08** — `@page { size: 80mm auto; margin: 2mm }` CSS rule, verbatim. Already shipped in `fallbackBrowser.ts:59`; F7.3 reuses it without paraphrasing.
- **A-05 audit-first** — `log_transaccional` INSERT with `accion='impreso'` is a backend concern, F8 concern. F7.3 declares the `// TODO: Fase 8` anchor in `PagoSheet.tsx`; F7.3 does NOT call `log_transaccional` directly. Documented rationale: audit-first is enforced at the API/ORM/DB layers (AGENTS.md), not at the renderer.
- **DEC-SUC-21** — discriminator `esMensualidad: z.literal(true)` on `SalidaMensualidadPayload` (`escposTemplates.ts:400`) already separates the mensualidad flow from the rotation flow. No F7.3 schema work needed.

## Open questions for the user

> Skipped — none. `sdd-propose` interactive question round is **not applicable** for this change because the plan contract is fully specified on lines 1779–1826, the existing skeleton is known, and the divergence list is enumerated by gap analysis. The orchestrator's task brief skips the question round per `delivery_strategy = ask-on-risk` cached but inapplicable here (forecast 350 LOC < 400 threshold).

## References

- `plan.md` lines 1779–1826 — the HU-F7.3 canonical contract (verbatim 19/15-field lists, sello decision, sequence correction, atomic tasks, test name)
- `plan.md` line 1816 — required test filename and 2-case spec
- `plan.md` line 1818 — 200 LOC forecast (extended to 350 in this proposal after gap analysis)
- `plan.md` lines 1820–1824 — atomic task list
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 240–301 — the diverging skeleton this proposal fixes
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 391–427 — the dispatcher that already routes `'salida'` and `'salida-mensualidad'`
- `apps/electron-sucursal/src/lib/print/escposTemplates.ts` lines 369–403 — the Zod schemas (no extension required; confirmation)
- `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` lines 59, 182, 208 — the HTML mirror this proposal updates
- `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` — the immediate-clause call site (mensualidad branch)
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` — the deferred-clause call site (post-pago branch)
- `apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx:80` — the F6.1 auto-print pattern F7.3 mirrors
- `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx:69` — the F6.x reprint pattern (reference only)
- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` — F5.2 byte-fixture precedent
- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` — F6.2 byte-fixture precedent
- `E:\easypunto_parkos\AGENTS.md` Architectural Principles §1–3 — Audit-First, Bi-Temporal, C/Q/U operation contract (no DELETE; corrections expressed as workflow rows)
- Engram — F5.1/F5.2/F6.1/F6.2 commit hashes and PR numbers (cited in §Dependencies)
- Engram id 1742 — B-prime scoped tsc verification pattern (proven in F5.x/F6.x)
- `openspec/config.yaml` `rules.tasks` — 800 LOC single-PR budget; 400 LOC chained-PR threshold

## Next step

This proposal is ready for `sdd-spec`. The contract surface for the spec phase is:

- New capability `tiquete-salida-cu15s` → `openspec/changes/hu-f7-3-tiquetes-salida/specs/tiquete-salida-cu15s/spec.md`
- New capability `tiquete-salida-mensualidad-cu15sm` → `openspec/changes/hu-f7-3-tiquetes-salida/specs/tiquete-salida-mensualidad-cu15sm/spec.md`
- New capability `salida-print-wiring` → `openspec/changes/hu-f7-3-tiquetes-salida/specs/salida-print-wiring/spec.md`
- No delta specs required (no existing `openspec/specs/` capability is changing at the requirement level — `tiquete-entrada-cu15e` only has implementation-level re-routing in commit 3's wire site, not a behavioral change).

`status: success`

---

## Appendix A — Byte-level field assertion matrix (escposBuilder.salida.test.ts)

The test file at `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` must assert, for each `build*Buffer(payload)` invocation, that the **UTF-8 byte sequence** of every plan.md-mandated label appears in the output buffer at least once. Two `describe()` blocks; each block has multiple `it()` assertions. The assertions pin the contract — if a future refactor renames, reorders, or drops any label, the test fails with a precise diff.

### Case 1 — CU-15S, 19 fields (plan.md lines 1789–1808)

| # | plan.md label | `Buffer.indexOf(label) !== -1` | Note |
|---|---------------|-------------------------------|------|
| 1 | `PARKINGOS` | yes | encabezado fijo (no plan.md table row; inherited from entrada pattern line 244) |
| 2 | `${empresa.nombre}` | contains the mock string | e.g. `mock-empresa` |
| 3 | `${empresa.direccion}` | contains mock string | e.g. `mock-direccion` |
| 4 | `NIT ${empresa.nit}` | yes | full line, not split |
| 5 | `${empresa.regimen}` | contains mock string | |
| 6 | `Operario: ${operario}` | yes | **currently missing** — see Approach §builder fixes point 2 |
| 7 | `*** TIQUETE DE SALIDA ***` | yes | **literal** — see Approach §builder fixes point 1; the verdict on this label is the strongest single assertion in the test |
| 8 | `Folio: ${folio}` | yes | payload `salidas.uuid` |
| 9 | `Tarifa: ${formatCOP(tarifaAplicada)}/hora` | yes | **currently missing** — see Approach §builder fixes point 3 |
| 10-12 | `Entrada: dd/MM/yyyy HH:mm` + `Salida: ...` + `Tiempo: ${tiempoTotal}` | yes | lines 257-259 already render joined format; the test asserts the joined form `formatFechaCorta` returns |
| 13 | `Tiempo: ${tiempoTotal}` | yes | already at line 259; field 13 of plan.md table |
| 14 | `Subtotal: ${formatCOP(subtotal)}` | yes | already at line 261 |
| 15 | `IVA: ${formatCOP(iva)}` | yes | already at line 262 |
| 16 | `TOTAL: ${formatCOP(total)}` | yes | already at line 264 with `escBoldOn()` |
| 17 | `Medio de pago: ${medioPago}` | yes | already at line 266; the **only** field genuinely dependent on the post-pago trigger (Fase 8) |
| 18 | `Placa: ${placa}` | yes | already at line 256 |
| 19 | (multi-line) `Horario:`, `Poliza RC:` (optional), `Observaciones:` (optional) | yes | **Horario currently missing**; Observations branch **currently missing optional guard**; Poliza already optional at line 269 |
| 20 | `;QR:${qrDataUrl}` | yes | DEC-SUC-26 marker; **currently missing** — see Approach §builder fixes point 5 |
| 21 | `;LOGO:${logoText \|\| 'OK'}` | yes | DEC-SUC-26 marker; **currently missing** — see Approach §builder fixes point 5 |
| (footer) | `Gracias por su visita.` | yes | line 271 |

Sentinel byte assertion (sello):

```
expect(buf).toContain(Buffer.from([0x1B, 0x21, 0x30])); // escText2x() opener (helper line)
expect(buf.indexOf('*** TIQUETE DE SALIDA ***')).toBeGreaterThan(
  buf.indexOf(Buffer.from([0x1B, 0x21, 0x30]))
);
expect(buf.indexOf(Buffer.from([0x1B, 0x21, 0x00]))).toBeGreaterThan(
  buf.indexOf('*** TIQUETE DE SALIDA ***')
); // escTextReset() closer
```

### Case 2 — CU-15SM, 15 fields + sello (plan.md line 1810)

| # | plan.md label | `Buffer.indexOf(label) !== -1` | Note |
|---|---------------|-------------------------------|------|
| 1-6 | (same as Case 1: encabezado, empresa, dirección, NIT, régimen, operario) | yes | line 278-284 already render 1-5; line 294 renders Operario: already; line 295 renders Horario: already |
| 7 | sello `*** PAGO CON MENSUALIDAD ***` | yes | already at line 287 |
| 8 | `Folio: ${folio}` | yes | line 290 |
| 9 | `Tiempo: ${tiempoTotal}` | yes | **currently missing** — see Approach §builder fixes |
| 10-12 | `Entrada: ...` + `Salida: ...` | yes | lines 292-293 already |
| 13 | (already as field 9 in this list — duplicate by plan.md ordering) | — | merged with field 9 above |
| 14 | `Placa: ${placa}` | yes | line 291 |
| 15 (multi-line) | `Horario:`, `Poliza RC:` (optional), `Observaciones:` (optional) | yes | Horario already at line 295; Poliza optional at line 297; **Observaciones branch currently missing** |
| 16 | QR marker `;QR:${qrDataUrl}` | yes | **currently missing** |
| 17 | Logo marker `;LOGO:${logoText \|\| 'OK'}` | yes | **currently missing** |
| (footer) | `Conserve este tiquete como soporte.` | yes | line 299 |

Sello byte assertion (the canonical "mensualidad distinguisher"):

```
expect(buf).toContain(Buffer.from([0x1B, 0x21, 0x30])); // text-2x height opener
const selloBytes = Buffer.from('*** PAGO CON MENSUALIDAD ***\n', 'utf8');
expect(buf.indexOf(selloBytes)).toBeGreaterThan(buf.indexOf(Buffer.from([0x1B, 0x21, 0x30])));
expect(buf.indexOf(Buffer.from([0x1B, 0x21, 0x00]))).toBeGreaterThan(buf.indexOf(selloBytes));
```

The sello byte assertion is what plan.md line 1816 calls "validating los bytes exactos del sello (`0x1B 0x21 0x30`)" — the test will pin exactly that sequence.

## Appendix B — Field order correspondence (byte builder vs HTML fallback)

Per F5.2 R4 (purity) and F6.2 (HTML mirror pattern), the field order in `escposBuilder.buildSalidaBuffer()` must correspond to the field order in `fallbackBrowser.renderSalidaTiqueteHtml()` (when `renderSalidaTiqueteHtml` is extracted from the private `renderSalidaHtml`). This is verified by **PR-review inspection only** (per F6.2 precedent, HTML renderers are not auto-tested in this project's Vitest boundary). The proposal explicitly states this in §Approach §Fallback HTML mirror so reviewers do not expect automated coverage.

The mapping is one-to-one:

| # | Byte buffer expression | HTML fallback expression |
|---|------------------------|---------------------------|
| 1 | `escBoldOn() + utf8('PARKINGOS\n')` | `<h1>PARKINGOS</h1>` |
| 2-5 | `${empresa.nombre/direccion/nit/regimen}` | `<p>...</p>` |
| 6 | `Operario: ${operario}` | `<p>Operario: ...</p>` |
| 7 | sello (text-2x) | `<h2>*** TIQUETE ... ***</h2>` |
| 8-... | field-by-field | field-by-field |
| 20, 21 | `;QR:` / `;LOGO:` text marker | `<img src="${qrDataUrl}" />` / `<img src="${logoDataUrl}" />` |

If the field order drifts in a future commit, a reviewer catches it on the diff, not a test.

## Appendix C — Verification matrix

| Verification | Command | Expected result | Source |
|---|---|---|---|
| Build buffer byte-fixture (CU-15S) | `npx vitest run apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts -t "CU-15S"` | `1 passed` | This proposal, Appendix A Case 1 |
| Build buffer byte-fixture (CU-15SM) | `npx vitest run apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts -t "CU-15SM"` | `1 passed` | This proposal, Appendix A Case 2 |
| Sello byte sentinel | Inside the test file, the assertion on `0x1B 0x21 0x30` passes | buffers match | plan.md line 1816 |
| Renderer tsc (B-prime scoped) | `npx tsc --noEmit -p apps/electron-sucursal/tsconfig.json` | `0 errors` on this change's files | engram id 1742 |
| Workspace tsc (full) | `npx tsc -b` | same — informational; pre-existing cascades out of scope | F5.1 follow-up MEDIUM |
| Vitest full-suite (renderer) | `cd apps/electron-sucursal && npx vitest run` | all existing tests still pass; no `escposBuilder.test.ts`/`escposBuilder.entrada.test.ts`/`escposBuilder.types.test.ts` regression | F5.2/F6.2 |
| Lint (renderer's eslint config) | `cd apps/electron-sucursal && npx eslint src/lib/print src/features/operacion/components/SalidaPanel.tsx src/features/facturacion/components/PagoSheet.tsx` | `0 problems` | repo convention |
| e2e printer.spec.ts | (NOT EXECUTED) | N/A — sandbox F.6 has no USB | F5.1/F5.2/F6.x precedent |
| LOC audit | `git diff --stat origin/dev` | `+~340 LOC, -0 LOC` matches the forecast | this proposal §Work unit commits |
| Author scan | `git log --format='%an <%ae>' -1` | `Parkos Dev <dev@parkos.local>` never `gentle-ai-sub-agent` | AGENTS.md git identity rule |

## Appendix D — Plan-vs-ER divergence reminders

Two pre-existing divergences in this change's file scope are *not* F7.3's responsibility to fix. They are documented here for the spec phase to inherit as known, deferred items:

1. **`formatCOP` consolidation with F2.x** — already F5.2 follow-up; F7.3 inherits the F5.2 implementation verbatim.
2. **B-prime scoped tsc fallback when workspace tsc has unrelated cascades** — F5.1 follow-up MEDIUM; F7.3 verifies B-prime scoped and notes any pre-existing full-project cascades in `apply-progress` (per engram id 1742).

Neither is a blocker for F7.3.

## Appendix E — Conventional Commit messages

Three commits per §Work unit commits above. Conventional Commits per AGENTS.md:

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

Refs: HU-F7.3, DEC-SUC-27 (deferred print ordering)
```

```
feat(print): complete CU-15SM 15-field contract with mensualidad sello

Bring the F5.2 skeleton at apps/electron-sucursal/src/lib/print/
escposBuilder.ts (lines 275-301) into verbatim alignment with the
15-field list in plan.md line 1810 (HU-F7.3 CU-15SM).

Changes:
- add Tiempo line (campo 13)
- append DEC-SUC-26 QR and LOGO text markers
- add optional Observaciones branch
- verify sello "* ** PAGO CON MENSUALIDAD ***" at text-2x
  (0x1B 0x21 0x30) is preserved verbatim from the existing
  skeleton at line 286-287 (plan.md line 1787)

Refs: HU-F7.3, DEC-SUC-27 (immediate print ordering)
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

iv.  New escposBuilder.salida.test.ts with 2 byte-fixture cases
     per plan.md line 1816 (CU-15S 19 fields; CU-15SM 15 fields
     with 0x1B 0x21 0x30 sentinel).

Refs: HU-F7.3, HU-F8.1, plan.md lines 1816/1789-1810
```

No `Co-authored-by:` trailers; git author `Parkos Dev <dev@parkos.local>`.

## Appendix F — Why this is not a chained PR

`work-unit-commits` §SDD Relationship table: forecast <400 LOC ⇒ single PR, no chained-PR scaffolding needed. F7.3 forecast is 350 LOC (under 400). Even though the change touches 5 files + 1 new test, the 3 commits are grouped into a single PR because each commit is **internal to the same user-facing capability** ("tiquete de salida y salida-mensualidad impresos según DEC-SUC-27"). Reviewers benefit from seeing builder + fallback + wiring + test in one PR diff because the contract is cross-file (DEC-SUC-26 marker emission in builder must match the `<img>` tag emission in fallback). Splitting the chained-PR would invite partial-review error.

If the implementation actually exceeds 350 LOC during apply, the orchestrator can promote the inner PR (or a slice) to a chained-PR sequence — this is exactly what the work-unit-commits §SDD Relationship rule is for, but is **not** required to plan up-front when the forecast is below threshold.
