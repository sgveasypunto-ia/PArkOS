# Proposal: HU-F6.2 — Tiquete de entrada (CU-15E), con QR y logo añadidos

## Intent

HU-F6.2 (`plan.md` lines 1606-1653) defines the entry tiquete as a **17-field payload** (15 fields from the literal CU-15E list, plus QR and logo added per DEC-SUC-26). It composes on top of F5.2's renderer-side pure library (`escposBuilder.build('entrada', payload)`) which F5.2 ships ready (file `apps/electron-sucursal/src/lib/print/escposTemplates.ts`, `EntradaPayload` typed interface already declared per F5.2 archive-report line 18 — F6.2 extends, never reimplements). It integrates with F5.1's `bridge.imprimir({ buffer })` IPC channel for ESC/POS dispatch (auto-fired by F6.1's `Principal.tsx` on HTTP 200 of `POST /operacion/ingresos`, per DEC-SUC-27). It adopts `log_transaccional` for the post-print state row per A-05 (backend concern; F6.2 documents the row payload shape and the WIRING site). It is the canonical composition entry point for any "entry tiquete" emitted during the operador flow at the sucursal.

## Scope

### In Scope

- **Typed `EntradaPayload` refinement** (where F5.2's `EntradaPayload` is already declared, F6.2 tightens only the missing 2 fields per DEC-SUC-26: `qrDataUrl: string` and `logoDataUrl: string`; if F5.2's declared shape omits them, F6.2 adds them and re-emits the 17-field `TiqueteEntradaCampos` key set). The exhaustive `readonly` interface guarantees at tsc that **no field is missing** — if any of the 17 is dropped, `tsc` fails before `vitest` runs.
- **`buildEntradaPayload()` factory** in `escposTemplates.ts` — pure function that takes `(ingreso, sucursal, empresa, operario, tipoVehiculo, tarifa, documentos, fechaHora)` and assembles the 17-field `EntradaPayload`. Reuses F5.2's Zod base refiner for `uuidRegistro`, ISO `fecha*`, optional `qrDataUrl` / `logoDataUrl`. Already-present 4 dispatch schema in F5.2 — F6.2 only adds the `entradaPayloadSchema = entradaBase.refine(17 keys present)` variant.
- **A-01 integration: fetch `documentos` for logo + póliza RC** — `GET /documentos?uuid_sucursal=X&tipo=certificado` returns the RC text; `GET /documentos?uuid_sucursal=X&tipo=logo` returns the base64 logo. Both are read-only and consumed in the caller-supplied payload (F5.2 R4 constraint — builder never hits ER).
- **ABIERTO-01 QR content**: `qrDataUrl` = SHA256-prefixed concatenation of `folio+placa` formatted as `parkos://ingreso/<uuid>?placa=<placa>` (text encoded by the caller's QR rasterizer — the builder accepts the resulting data-URL string verbatim per F5.2 R2 constraint). No new column or table.
- **A-05 backend hook (DOCUMENTATION ONLY)**: F6.2 documents the exact `log_transaccional` payload the backend must INSERT after `bridge.imprimir` resolves: `{tabla_afectada: 'ingreso', uuid_registro_afectado: <ingreso.uuid>, accion: 'impreso', datos_nuevos: {estado: 'impresa'} | {estado: 'pendiente de impresión'}}`. **F6.2 does not implement the backend endpoint** (that's a separate HU per the user's prompt and the plan's F6.x split).
- **Wiring documentation** of the F6.1 → F6.2 → F5.1 call site: F6.1's `Principal.tsx` on POST 200 calls `escposBuilder.build('entrada', payload)` then `bridge.imprimir({ buffer: build(...).toString('base64') })`. The integration is a **typed glue line**, not new code — F6.2 documents the contract that F6.1 must satisfy.

### Out of Scope

- No PDF generation (only ESC/POS thermal + browser fallback per DEC-SUC-08).
- No email / SMS delivery of the tiquete (out of Fase 21 installer scope per plan).
- No QR with dynamic URLs — only ABIERTO-01's static `parkos://ingreso/<uuid>?placa=<placa>` payload.
- No new column, no new table, no `modelo_datos_er.mmd` change. `tipo_entrada` is **derived** from `ingreso.uuid_subscripcion_cliente IS NOT NULL` (DEC-SUC-21); the tiquete displays `MENSUALIDAD` tag without persisting.
- No backend endpoint for `log_transaccional` INSERT (separate HU — F6.2 documents the shape only).
- No auto-discovery of the `documents` cache (a future enhancement may live in the F6.x sync catalog; out of F6.2).
- No tests for CU-15S (salida) / CU-15SM (salida-mensualidad) — those are F7.x per plan.

## Capabilities

### Modified Capabilities

- `impresion` — appends a 4th capability block at `openspec/specs/impresion.md` (the flat canonical per F5.1 archive-report precedent, line 99). The block adds the entry tiquete as a 17-field typed payload wired through F5.2's `escposBuilder.build('entrada', payload)` and F5.1's `bridge.imprimir`.

No **New Capabilities** — `impresion` already exists and F6.2 extends it. (F5.1+F5.2 are merged into the canonical spec; F6.2 folds into the same canonical per the F5.1/F5.2 archive-report precedent.)

## Approach

Three pure modules in `apps/electron-sucursal/src/lib/print/`. F5.2 already ships `escposTemplates.ts`, `escposBuilder.ts`, `fallbackBrowser.ts` with the 4-tipo dispatcher + the 9 ESC/POS opcodes + the 2 named error classes. F6.2 only **extends** these files — never duplicates.

- `escposTemplates.ts` (MODIFY) — tighten `EntradaPayload` to the 17 `TiqueteEntradaCampos` keys (already declared by F5.2 with the 15 literal fields; F6.2 adds the 2 DEC-SUC-26 fields `qrDataUrl: string`, `logoDataUrl: string` and exposes `entradaPayloadSchema = base.refine({...17 keys})`). Add `buildEntradaPayload(ingreso, sucursal, empresa, operario, tipoVehiculo, tarifa, documentos, fechaHora)` factory. Reuses the existing `formatCOP` helper and `Intl.DateTimeFormat('es-CO', ...)` per F5.2 R4.
- `escposBuilder.ts` (NO CHANGE) — F5.2's `build('entrada', payload)` dispatcher already routes to `buildEntradaBuffer()`; F6.2 only updates the body emitted by `buildEntradaBuffer()` if the 17-field layout requires additional opcodes (e.g., `escText2x` for "TIQUETE DE ENTRADA" sello, `escCenter` for the header). The 9 opcode helpers are already exported.
- `fallbackBrowser.ts` (MODIFY) — extend `renderEntradaTiqueteHtml(payload)` to mirror the 17-field layout with semantic `<h1>` / `<p>` / `<img>` tags (QR + logo). The `@page{size:80mm auto;margin:2mm}` CSS is already injected by F5.2 R2.
- `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` (MODIFY) — append 3 keys: `tiquete_entrada_titulo`, `ingreso_registrado_exitoso`, `ingreso_observaciones_forzado` (for the operator UI messages that wrap the auto-print flow).
- **Wiring documentation** — the F6.1 `Principal.tsx` integration is **NOT** new code; F6.2 only writes a 1-page `docs/f6-2-integration.md` in the same change folder (NOT in the repo wiki) so reviewers can grep for the contract: `on POST 200 → escposBuilder.build('entrada', payload) → bridge.imprimir({buffer}) → on success/failure backend INSERTs log_transaccional`. F6.1 implements the actual `onSuccess` handler in its own PR.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | Modified | Add 2 DEC-SUC-26 fields + `buildEntradaPayload()` factory + `entradaPayloadSchema` |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | Modified | Extend `renderEntradaTiqueteHtml()` to mirror 17-field layout |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` | New | Byte-level 17-field presence (T1, T2, T4) |
| `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` | New | HTML layout for the 17-field tiquete |
| `apps/electron-sucursal/e2e/print.spec.ts` | New | Mocked `bridge.imprimir` + auto-fire from F6.1 wiring |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Modified | +3 keys for the operator UI |
| `openspec/changes/fase-6-2-tiquete-entrada/docs/f6-2-integration.md` | New | Wire contract for F6.1's `Principal.tsx` `onSuccess` |
| `openspec/specs/impresion.md` | Modified | Append `## F6.2 — tiquete de entrada` section (delta-fold) |

No backend changes. No `modelo_datos_er.mmd` change. No new tables / columns.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| F5.2 PR #3 not yet merged to `dev` (still open against dev per F5.2 archive-report line 6) | Med | F6.2 ships after F5.1 + F5.2 PRs merge. Branch from `dev` post-merge; F6.1's `feature/hu-f6-1-...` branch is already on `dev` per `git log --all`. Coordination: block F6.2 branch creation on F5.x merge. |
| QR content (`parkos://ingreso/<uuid>?placa=<placa>`) not yet ratified by producto | Low | ABIERTO-01 default applies; if negocio wants another content, swap is localized to the caller's QR rasterizer (F5.2 builder accepts any data-URL string). |
| `documentos` cache cold — first ingreso POST blocks on `GET /documentos?uuid_sucursal=X&tipo=logo` | Med | Caller-side cache: `electron-store` key `parkos.documents.v1` with TTL 24 h; on miss, fetch both (logo + RC) in parallel via `Promise.all`. Documented in `f6-2-integration.md`. |
| Backend `log_transaccional(accion='impreso')` endpoint not yet shipped | High | F6.2 documents the row payload shape only; the backend INSERT is a separate HU (out of F6.2). Until backend ships, the operator UI shows a transient "Impreso (estado local)" banner — the row is appended when the endpoint lands. No silent drop. |
| `window.print()` blocks the renderer thread for >2 s on slow printers (real-browser fallback path) | Low | Same mitigation as F5.2 R2: `window.print()` is async-isolated in a transient `<div>`; the operator can navigate away; the print completion is observed via `window.matchMedia('print')` listener. Out of F6.2 strict scope. |

## Rollback Plan

F6.2 is renderer-side pure (no DB, no migration, no IPC contract change). Rollback is a single revert:
1. Revert commits in `feature/hu-f6-2-tiquete-entrada` to the F5.2 archive head (`f54c4ef`).
2. The F6.2 build factory `buildEntradaPayload()` is the **only** new public surface in `escposTemplates.ts`. Reverting it restores F5.2's behavior (4-tipo dispatcher with the 4 original payloads — entrada is back to its F5.2 placeholder if any).
3. The 3 i18n keys are additive — reverting `operacion.json` removes them with no fallback string required (the operator UI texts revert to the F4.x literal keys).
4. The `log_transaccional` INSERT is **NOT** shipped by F6.2 (backend concern) — no rollback step required.
5. Canonical spec `openspec/specs/impresion.md` retains the F5.1 + F5.2 sections; the F6.2 section is appended at archive time only — during the F6.2 cycle the delta spec lives in `openspec/changes/fase-6-2-tiquete-entrada/specs/operacion-tiquete/spec.md` and is folded only on archive.

## Dependencies

- **F5.1 PR #4** (open against dev, head `b987cf2`) — `bridge.imprimir({ buffer })` IPC + `print:status` events + backoff queue.
- **F5.2 PR #3** (open against dev, head `f54c4ef`) — `escposBuilder.build('entrada', payload)` + `fallbackBrowser.print('entrada', payload)` + `EntradaPayload` interface.
- **F6.1** (`feature/hu-f6-1-...`, in-flight per `git log --all`) — provides the `Principal.tsx` `onSuccess` handler that consumes F6.2's payload. F6.2 documents the contract; F6.1 implements the call site. **Independent SDD cycle** per user's instruction.
- **Backend `log_transaccional` INSERT endpoint** — NOT shipped by F6.2; flagged as a separate HU.

## Success Criteria

- [ ] `npx vitest run apps/electron-sucursal/src/lib/print` exits `0` and the new `escposBuilder.entrada.test.ts` reports ≥17 byte-presence scenarios (one per field, plus layout composition).
- [ ] `npx tsc --noEmit -p apps/electron-sucursal/tsconfig.f6-2-verify.json` exits `0` on the F6.2 NEW + MODIFIED files (B-prime scoped per F5.2 precedent).
- [ ] `npx eslint apps/electron-sucursal/src/lib/print apps/electron-sucursal/src/renderer/i18n/locales/operacion.json --max-warnings 0` exits `0`.
- [ ] `playwright test e2e/print.spec.ts --grep "F6.2"` exits `0` on CI (deferred locally per sandbox F.6 — same precedent as F5.1 e2e deferral).
- [ ] `apps/electron-sucursal/src/lib/print/escposTemplates.ts::entradaPayloadSchema.parse(entradaPayload)` throws `EscposPayloadMissingFieldError` (code `escpos_payload_missing_field`) when any of the 17 keys is absent; passing all 17 succeeds.
- [ ] `git diff --stat feature/hu-f6-2-tiquete-entrada` ≤ 800 lines (single PR under the AGENTS.md review budget).
- [ ] Zero physical DELETE attempts (audit-first canon: the F6.2 change does not touch `[A]` tables; it only reads `ingreso`, `sucursal`, `documentos`, `usuarios` for payload assembly).
- [ ] No `Co-Authored-By:` AI trailer in any commit (authored as `Parkos Dev <dev@parkos.local>`).

## References

- `plan.md` lines 1606-1653 (HU-F6.2 contract, the 17 fields verbatim)
- `plan.md` lines 412-492 (DEC-SUC-08 thermal printing; DEC-SUC-26 QR + logo; DEC-SUC-27 orden impresión; ABIERTO-01 QR content)
- `plan.md` lines 446-462 (A-01 póliza RC; A-05 estado de impresión)
- `modelo_datos_er.mmd` — `ingreso`, `sucursal`, `documentos`, `usuarios` (read-only for payload assembly)
- `openspec/specs/impresion.md` — canonical printer domain spec (F5.1 + F5.2 merged)
- `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/archive-report.md` — F5.1 closure, B-prime scoped tsc precedent
- `openspec/changes/archive/2026-09-17-fase-5-2-escpos-builder-fallback/archive-report.md` — F5.2 closure, `EntradaPayload` declared
- Engram: `sdd/fase-5-2-escpos-builder-fallback/spec` (id 1751), `sdd/fase-5-1-printer-service/spec` (id 1749)

## Regulatory Impact (DIAN audit-first)

The tiquete de entrada is **not** an electronic invoice — it is an operational receipt that the cliente uses to claim the vehículo. DIAN retention (5+ años) applies to the **factura electrónica** emitted at salida (CU-15S, F7.x scope), not to the tiquete de entrada. F6.2 nevertheless conforms to audit-first via the **log_transaccional hook** (A-05): the `accion='impreso'` row carries `datos_nuevos.estado ∈ {impresa, pendiente de impresión}` and the SHA256 hash chain continues unbroken (per `modelo_datos_er.mmd` lines 386-404). The hook is **backend concern** (not F6.2); F6.2 documents the row payload. Retention 5+ años inherits from the existing `log_transaccional.fecha_retencion_hasta` column.