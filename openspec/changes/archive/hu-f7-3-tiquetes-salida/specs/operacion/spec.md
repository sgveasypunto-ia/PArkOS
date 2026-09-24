# Delta Spec: HU-F7.3 — Tiquetes de salida CU-15S / CU-15SM y wiring post-pago

> **Change**: `hu-f7-3-tiquetes-salida` · **Change key (Engram)**: `sdd/hu-f7-3-tiquetes-salida/spec` · **Domain folder**: `operacion` (matches project convention; root-level `openspec/specs/operacion.md` holds F6.1 entry-side, this delta folder covers F7.3 salida-side) · **Phase**: spec (sdd-spec) · **Plan contract**: `plan.md` lines 1779–1826 (HU-F7.3) + line 1783 (DEC-SUC-27) + lines 412–492 (DEC-SUC-08/26) · **Canonical REQ-OPS series file**: `openspec/specs/operations/spec.md` (delta-appended here — the prompt's reference to `operacion.md` is a typo; REQ-OPS-001..142 live in `operations/spec.md`, the only canonical file carrying the series) · **Allocated REQ-OPS**: `REQ-OPS-143`, `REQ-OPS-144`, `REQ-OPS-145` (next free after REQ-OPS-141..142 from `2026-09-17-orphan-req-f1-1-f1-2-coverage`; the prompt's "likely REQ-OPS-141..143" is stale by one change)

## ADDED Requirements

### Requirement: REQ-OPS-143 — CU-15S tiquete de salida (19 campos + QR + logo)

The renderer SHALL emit a `Buffer` from `escposBuilder.build('salida', payload)` whose UTF-8 byte sequence contains, in order, the 19 literal fields of `plan.md` lines 1789–1808 (encabezado `PARKINGOS`, empresa, dirección, NIT, régimen, operario, sello `*** TIQUETE DE SALIDA ***`, folio from `salidas.uuid`, tarifa aplicada in `COP/hora`, fecha operación from `salidas.fecha_salida`, hora entrada from `ingreso.fecha_ingreso`, hora salida, tiempo total, subtotal, IVA, total a pagar, medio de pago from `factura_pagos.medio_pago`, placa from `ingreso.placa`, plus the multi-line `Horario`/`Poliza RC` (optional)/`Resolucion FE`/`Observaciones` (optional) block from `sucursal`/`documentos`/`resolucion_facturacion`) AND SHALL append the DEC-SUC-26 text markers `;QR:${qrDataUrl}` and `;LOGO:${logoText || 'OK'}` before the final `Gracias por su visita.` line (plan.md lines 1807–1808; DEC-SUC-26 verbatim — builder emits markers, NOT raster, per F5.2 R3 purity). The sello SHALL be wrapped by `0x1B 0x21 0x30` (text-2x opener) … `0x1B 0x21 0x00` (reset) from `escText2x()` / `escTextReset()`. `fallbackBrowser.renderSalidaHtml` SHALL produce semantic HTML whose visible field order matches the byte buffer field-for-field under the verbatim DEC-SUC-08 `@page { size: 80mm auto; margin: 2mm }` CSS rule (`PAGE_RULE` at `fallbackBrowser.ts:59`, not paraphrased). QR + logo SHALL render as `<img src="${qrDataUrl}" />` / `<img src="${logoDataUrl || ''}" />`; empty-logo case preserves the `▢` glyph placeholder (DEC-SUC-08 fallback, line 145).

#### Scenario: 19 CU-15S field labels discoverable in byte buffer

- **GIVEN** a fully-populated `SalidaPayload` (campos 1–19 set; `qrDataUrl` set; `logoText="OK"`; `polizaRC` truthy; `observaciones` set; `medioPago="EFECTIVO"`)
- **WHEN** `build('salida', payload)` is invoked
- **THEN** the buffer SHALL contain each of the 19 literal labels at least once (`Buffer.indexOf(label) !== -1` per plan.md line 1816): `PARKINGOS`, `${empresa.nombre}`, `${empresa.direccion}`, `NIT ${empresa.nit}`, `${empresa.regimen}`, `Operario: ${operario}`, `*** TIQUETE DE SALIDA ***`, `Folio: ${folio}`, `Tarifa: ${formatCOP(tarifaAplicada)}/hora`, `Entrada: …`, `Salida:  …`, `Tiempo: ${tiempoTotal}`, `Subtotal: ${formatCOP(subtotal)}`, `IVA: ${formatCOP(iva)}`, `TOTAL: ${formatCOP(total)}`, `Medio de pago: ${medioPago}`, `Placa: ${placa}`, `Horario: ${horarioAtencion}`, `Poliza RC: ${polizaRC}`, `Observaciones: ${observaciones}`, `Resolucion FE: ${resolucionFE}`.

#### Scenario: DEC-SUC-26 QR + logo markers emitted before footer

- **GIVEN** the same payload with `qrDataUrl="data:image/png;base64,FAKEQR"` and `logoText="OK"`
- **WHEN** `build('salida', payload)` is invoked
- **THEN** the buffer SHALL contain `;QR:data:image/png;base64,FAKEQR` and `;LOGO:OK` BEFORE the `Gracias por su visita.` footer
- **AND** the buffer SHALL NOT contain rasterization opcodes (no `0x1D` GS prefix outside the trailing `cutPartial` at `0x1D 0x56 0x00`) — DEC-SUC-26 purity: caller rasterizes, builder emits markers only.

#### Scenario: Sello bytes pinned between text-2x opener and reset

- **GIVEN** any `SalidaPayload`
- **WHEN** `build('salida', payload)` is invoked
- **THEN** the buffer SHALL contain `Buffer.from([0x1B, 0x21, 0x30])` immediately before the sello UTF-8 bytes
- **AND** `Buffer.from([0x1B, 0x21, 0x00])` SHALL appear immediately after the sello UTF-8 bytes
- **AND** the sello UTF-8 bytes SHALL be exactly `*** TIQUETE DE SALIDA ***` (plan.md line 1794 literal, campo 7) — NOT `'*** SALIDA ***'` (the F5.2 skeleton typo at escposBuilder.ts:252 is replaced).

#### Scenario: `observaciones` + `polizaRC` optional branches respected

- **GIVEN** a `SalidaPayload` with `polizaRC=null` AND `observaciones=null`
- **WHEN** `build('salida', payload)` is invoked
- **THEN** the buffer SHALL NOT contain `Poliza RC:` (the `if (payload.polizaRC)` guard is required)
- **AND** the buffer SHALL NOT contain `Observaciones:` (the missing optional branch is inserted by this change, per plan.md campo 19 subset)
- **AND** `Horario:` and `Resolucion FE:` SHALL still be emitted (non-optional mandatory fields of campo 19).

#### Scenario: HTML fallback mirrors byte buffer field order

- **GIVEN** the same fully-populated `SalidaPayload`
- **WHEN** `fallbackBrowser.renderSalidaHtml(payload)` is invoked
- **THEN** the returned HTML SHALL contain every label in the same sequence as the byte buffer (encabezado → empresa → dirección → NIT → régimen → operario → sello → folio → tarifa → entrada → salida → tiempo → subtotal → IVA → total → medio de pago → placa → horario → poliza (optional) → resolucion FE → observaciones (optional) → QR + logo `<img>` tags → footer)
- **AND** the `<style>` block SHALL include the verbatim `@page { size: 80mm auto; margin: 2mm }` rule (DEC-SUC-08).

#### Scenario: Printer offline — ingreso persisted, banner shown

- **GIVEN** `build('salida', payload)` returned a valid `Buffer` AND the F5.1 `bridge.imprimir` IPC returns `printer_offline`
- **WHEN** the renderer awaits `bridge.imprimir(...)` from `PagoSheet.tsx`
- **THEN** a banner SHALL read "Impresora no disponible, reintentando…" (F5.1 R3)
- **AND** the `salidas` INSERT that Fase 8 issued MUST remain committed (Fase 8 owns the source-of-truth row; print is observer-side per A-05)
- **AND** the F5.1 retry queue SHALL drain when the printer reconnects (F5.1 R5).

**Source**: `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 240–273 (skeleton with 7 divergences); `fallbackBrowser.ts` lines 182–208 (HTML mirror skeleton); `escposTemplates.ts` lines 369–385 (`salidaPayloadSchema = entradaPayloadSchema.extend(...)` already carries every field — no schema extension); `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` (NEW per plan.md line 1816); `openspec/specs/impresion.md` F5.2 R1 (dispatcher), R3 (purity), R4 (caller-supplied decimals), Constraints §5 (DEC-SUC-27 ordering is F7.3 scope, not F5.2); `plan.md` lines 1789–1808 (19-field list); plan.md line 1816 (test name + 2-case scope); plan.md lines 412–492 (DEC-SUC-08 + DEC-SUC-26 verbatim). A-05 `log_transaccional(accion='impreso')` INSERT is **out of scope** for F7.3 — Fase 8 inherits per F6.2 documentation.

---

### Requirement: REQ-OPS-144 — CU-15SM tiquete de salida-mensualidad (15 campos + sello text-2x)

The renderer SHALL emit a `Buffer` from `escposBuilder.build('salida-mensualidad', payload)` whose UTF-8 byte sequence contains, in order, the 15 literal fields of plan.md line 1810 (encabezado `PARKINGOS`, empresa, dirección, NIT, régimen, operario, sello `*** PAGO CON MENSUALIDAD ***`, folio from `salidas.uuid`, fecha operación, hora entrada, hora salida, tiempo total, placa, plus the multi-line `Horario`/`Poliza RC` (optional)/`Resolucion FE`/`Observaciones` (optional) block) — **without** subtotal/IVA/total (no cobro) — AND SHALL append DEC-SUC-26 markers `;QR:${qrDataUrl}` + `;LOGO:${logoText || 'OK'}` before the `Conserve este tiquete como soporte.` footer. The sello SHALL be wrapped by `0x1B 0x21 0x30` … `0x1B 0x21 0x00` (text-2x opener + reset, per plan.md line 1787 + line 1816 byte sentinel). `fallbackBrowser.renderSalidaMensualidadHtml` SHALL mirror byte-buffer field-for-field under the same DEC-SUC-08 `@page` rule. The encabezado MUST be the dynamic `${empresa.nombre}` value (plan.md line 1810 corrected: NOT the corpus-original fixed literal `"PARQUEADERO PUBLICO"` — that was a corpus copy defect).

#### Scenario: 15 CU-15SM field labels discoverable in byte buffer

- **GIVEN** a fully-populated `SalidaMensualidadPayload` (campos 1–15 set; `qrDataUrl` set; `logoText` set; `polizaRC` truthy; `observaciones` set; `tiempoTotal` set; `esMensualidad: z.literal(true)` per escposTemplates.ts:400 DEC-SUC-21)
- **WHEN** `build('salida-mensualidad', payload)` is invoked
- **THEN** the buffer SHALL contain each of the 15 literal labels: `PARKINGOS`, `${empresa.nombre}`, `${empresa.direccion}`, `NIT ${empresa.nit}`, `${empresa.regimen}`, `Operario: ${operario}`, `*** PAGO CON MENSUALIDAD ***`, `Folio: ${folio}`, `Tiempo: ${tiempoTotal}`, `Entrada: …`, `Salida:  …`, `Placa: ${placa}`, `Horario: ${horarioAtencion}`, `Poliza RC: ${polizaRC}` (optional), `Resolucion FE: ${resolucionFE}`, `Observaciones: ${observaciones}` (optional), `;QR:${qrDataUrl}`, `;LOGO:${logoText || 'OK'}`, `Conserve este tiquete como soporte.`
- **AND** the buffer SHALL NOT contain `Subtotal:`, `IVA:`, `TOTAL:`, or `Medio de pago:` (CU-15SM has no cobro per plan.md line 1810).

#### Scenario: Sello byte sentinel pinned (plan.md line 1816 canonical assertion)

- **GIVEN** any `SalidaMensualidadPayload`
- **WHEN** `build('salida-mensualidad', payload)` is invoked
- **THEN** the buffer SHALL contain `Buffer.from([0x1B, 0x21, 0x30])` (text-2x opener) immediately before the sello UTF-8 bytes
- **AND** the sello UTF-8 bytes SHALL be exactly `*** PAGO CON MENSUALIDAD ***\n`
- **AND** `Buffer.from([0x1B, 0x21, 0x00])` (text-2x reset) SHALL appear immediately after the sello UTF-8 bytes
- **AND** the byte fixture `Buffer.from([0x1B, 0x21, 0x30, ...'*** PAGO CON MENSUALIDAD ***\n', 0x1B, 0x21, 0x00])` SHALL be present verbatim — the canonical "mensualidad distinguisher" sentinel per plan.md line 1816.

#### Scenario: `Tiempo` field added (current skeleton is missing it)

- **GIVEN** the current `escposBuilder.ts:275–301` skeleton (line 287 has the sello, line 290 has `Folio`, line 291 has `Placa`, lines 292–293 have `Entrada`/`Salida` — but NO `Tiempo:` line)
- **WHEN** F7.3 is applied
- **THEN** `buildSalidaMensualidadBody` SHALL insert `utf8('Tiempo: ${payload.tiempoTotal}\n')` between the `Salida:` line and the `Placa:` line (campo 13 of plan.md line 1810)
- **AND** the byte-fixture test SHALL assert `Buffer.indexOf('Tiempo: 1h 30m') !== -1` for `tiempoTotal = "1h 30m"`.

#### Scenario: Discriminator `esMensualidad: z.literal(true)` separates flows

- **GIVEN** a `SalidaMensualidadPayload` with `esMensualidad: true`
- **WHEN** `build('salida-mensualidad', payload)` is invoked
- **THEN** the build SHALL dispatch to `buildSalidaMensualidadBody` (NOT `buildSalidaBody`) — DEC-SUC-21 discriminator
- **AND** the build SHALL reject any payload missing the `esMensualidad: true` literal with `EscposPayloadMissingFieldError` (F5.2 R1 + Zod `literal(true)`).

#### Scenario: HTML fallback mirrors byte buffer field order

- **GIVEN** the same fully-populated `SalidaMensualidadPayload`
- **WHEN** `fallbackBrowser.renderSalidaMensualidadHtml(payload)` is invoked
- **THEN** the returned HTML SHALL contain every label in the same sequence as the byte buffer (encabezado → empresa → dirección → NIT → régimen → operario → sello → folio → tiempo → entrada → salida → placa → horario → poliza (optional) → resolucion FE → observaciones (optional) → QR + logo `<img>` tags → footer)
- **AND** the `<style>` block SHALL include the verbatim `@page { size: 80mm auto; margin: 2mm }` rule (DEC-SUC-08).

#### Scenario: Encabezado is dynamic, not corpus-fixed

- **GIVEN** a `SalidaMensualidadPayload` with `empresa.nombre = "Mi Parqueadero XYZ"`
- **WHEN** `build('salida-mensualidad', payload)` is invoked
- **THEN** the buffer SHALL contain `Mi Parqueadero XYZ` as the encabezado (NOT the corpus-original fixed literal `PARQUEADERO PUBLICO`)
- **AND** the same payload with a different `empresa.nombre` SHALL emit a different encabezado (one-to-one mapping, F5.2 R4 caller-supplied).

**Source**: `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 275–301 (sello already correct at line 287, but `Tiempo` missing at campo 13 — confirmed via read); `fallbackBrowser.ts` lines 208–228 (`renderSalidaMensualidadHtml` skeleton); `escposTemplates.ts` lines 385–403 (`salidaMensualidadPayloadSchema` + `esMensualidad: z.literal(true)` per DEC-SUC-21, no schema extension); `plan.md` line 1810 (15-field list verbatim); plan.md line 1816 (test name + byte sentinel); plan.md line 1787 (sello decision + dynamic `encabezado` correction).

---

### Requirement: REQ-OPS-145 — Wiring DEC-SUC-27 (inmediato CU-15SM, diferido CU-15S)

The renderer SHALL call `await window.bridge.imprimir({ tipo, payload })` at exactly **two** moments, mirroring the F6.1 auto-print pattern at `IngresoPanel.tsx:80` (DEC-SUC-27 verbatim from plan.md line 1783):

1. **Immediate clause (CU-15SM)** — in `SalidaPanel.tsx` (mensualidad-confirm success branch), the renderer SHALL invoke `bridge.imprimir({ tipo: 'salida-mensualidad', payload: <fully populated SalidaMensualidadPayload> })` immediately after the mensualidad-confirm step returns success. The `medioPago` field is NOT required (no cobro).

2. **Deferred clause (CU-15S)** — in `PagoSheet.tsx` (post-200 success branch that Fase 8 will populate), the renderer SHALL declare the `await window.bridge.imprimir({ tipo: 'salida', payload: <fully populated SalidaPayload> })` call site with a `// TODO: Fase 8` anchor comment explaining that the post-pago trigger site is supplied by HU-F8.1+. The `medioPago` field MUST be present in the payload (campo 17 of plan.md line 1804) — this is the data dependency that mandates DEC-SUC-27's deferred ordering.

The IPC wire signature `bridge.imprimir({ buffer })` SHALL be unchanged from F5.1 (no new IPC shape); payload shape for `salida` and `salida-mensualidad` slots is inherited from `escposTemplates.ts:369/385` via the F5.2 dispatcher.

#### Scenario: CU-15SM prints immediately on mensualidad-confirm success

- **GIVEN** the operator confirms a salida with an active `subscripciones_cliente` row
- **WHEN** the mensualidad-confirm step returns `success === true`
- **THEN** `SalidaPanel.tsx` SHALL build a `SalidaMensualidadPayload` whose `esMensualidad === true` AND SHALL call `await window.bridge.imprimir({ tipo: 'salida-mensualidad', payload })` exactly once
- **AND** the printer SHALL receive the byte buffer whose sello bytes match the REQ-OPS-144 sentinel
- **AND** the call site SHALL mirror `IngresoPanel.tsx:80` structurally (same `try/catch` shape, same `printer_offline` banner handling per F5.1 R3).

#### Scenario: CU-15S print is deferred until post-200 (the `medioPago` dependency)

- **GIVEN** the operator triggered a salida rotación (no mensualidad) AND the operator is in `PagoSheet.tsx`
- **WHEN** the Fase 8 pago POST returns `200 OK` with `factura_pagos.medio_pago` resolved
- **THEN** `PagoSheet.tsx` SHALL build a `SalidaPayload` whose `medioPago === <factura_pagos.medio_pago>` AND SHALL call `await window.bridge.imprimir({ tipo: 'salida', payload })` exactly once
- **AND** the call site SHALL carry a `// TODO: Fase 8: confirms the post-200 trigger fires here` comment visible in the PR diff
- **AND** the build SHALL NOT fire before pago-200 — invoking `escposBuilder.build('salida', ...)` with `medioPago = null` is a contract violation (campo 17).

#### Scenario: Pre-pago state — no print fires

- **GIVEN** the operator triggered a salida rotación AND pago has NOT yet returned 200 (e.g. user still in medio-pago selector)
- **WHEN** any non-pago-200 event fires (user navigates away, modal closes, error toast appears)
- **THEN** `bridge.imprimir` SHALL NOT be invoked for `tipo: 'salida'`
- **AND** `salidas.uuid` MAY be persisted (Fase 8 owns the INSERT timing — F7.3 is observer-side per A-05).

#### Scenario: `bridge.imprimir` wire signature unchanged

- **GIVEN** the F5.1 IPC contract (`bridge.imprimir({ buffer: base64-string })` per impresion.md F5.1 R4 + R6)
- **WHEN** F7.3 wires the two call sites
- **THEN** the IPC channel SHALL accept the same `{ buffer }` shape
- **AND** the renderer SHALL call `bridge.imprimir({ buffer: escposBuilder.build(tipo, payload).toString('base64') })` (F5.2 Constraint §2 verbatim, no `lines: PrintLine[]` shape — F5.1 rejects that form)
- **AND** the call site SHALL NOT introduce a new IPC channel or shape (DEC-SUC-19 single-instance preserved).

#### Scenario: Caller-supplied `medioPago` from `factura_pagos` row

- **GIVEN** the Fase 8 pago handler resolved `factura_pagos.medio_pago = "TARJETA_DEBITO"`
- **WHEN** `PagoSheet.tsx` builds the `SalidaPayload` for the deferred print
- **THEN** the payload's `medioPago` field SHALL equal `"TARJETA_DEBITO"` (F5.2 R4 — caller-supplied decimal/string, no hidden coupling, no inference from `ingreso`/`salidas` rows)
- **AND** invoking `escposBuilder.build('salida', payload)` with this payload SHALL emit `Medio de pago: TARJETA_DEBITO` in the byte buffer (REQ-OPS-143 scenario 1).

#### Scenario: `PARKOS_PRINTER_DISABLED=1` env disables both call sites

- **GIVEN** `PARKOS_PRINTER_DISABLED=1` (F5.1 operational rollback boundary)
- **WHEN** either call site invokes `bridge.imprimir`
- **THEN** the IPC SHALL return `503` BEFORE the builder is invoked (F5.1 R6 — caller-side rollback)
- **AND** no byte buffer is generated (the disable preempts the build call).

**Source**: `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (mensualidad-confirm branch); `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (post-200 branch — supplied by Fase 8); `apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx:80` (F6.1 auto-print precedent the wiring mirrors); `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 391–427 (F5.2 dispatcher already routes `'salida'` and `'salida-mensualidad'`); `apps/electron-sucursal/src/lib/print/escposTemplates.ts` lines 369–403 (Zod schemas — no extension); `plan.md` line 1783 (DEC-SUC-27 verbatim ordering); `openspec/specs/impresion.md` F5.1 R4 + R6 (wire signature) + F5.2 Constraints §2 (caller shape) + Constraints §5 (DEC-SUC-27 is F7.3 scope, not F5.2).

---

## Mechanical Copy Contract — pre-existing REQ-OPS are NOT modified

This change ADDs new REQ-OPS-143..145 to `openspec/specs/operations/spec.md`. The following pre-existing requirement IDs are **reused as-is**, not modified:

- **`tiquete-entrada-cu15e` (F6.2)** — its byte contract for `build('entrada', …)` is independent of the salida builders (separate Zod schemas: `entradaPayloadSchema` at escposTemplates.ts vs `salidaPayloadSchema` / `salidaMensualidadPayloadSchema` via `entradaPayloadSchema.extend(...)`); F7.3 only references the F6.2 mirror pattern, does not alter its byte sequence.
- **`puente-impresion-bridge-f5-1` (F5.1, impresion.md R1..R6)** — wire signature `{ buffer: base64-string }` is unchanged; payload shape for the two new tipos is exercised in the new byte tests but the IPC contract is not modified.
- **`req-ops-131..140` (operador-dashboard-hub, REQ-OPS-131..140)** — pre-existing dashboard IA + composable-section + drawer + lazy-mount requirements; F7.3 only adds the missing `window.bridge.imprimir(payload)` calls into the React call sites, never touches the dashboard's IA structure or the composable-section contract.
- **`req-ops-141..142` (2026-09-17-orphan-req-f1-1-f1-2-coverage)** — `router_factory` guard + `/auth/me` cookie — backend concerns, out of F7.3 scope; pre-existing REQ-OPS series `req-ops-001..142` in `operations/spec.md` retains byte-identity in the unappended portion.

**SHA-256 of `operations/spec.md` BEFORE the append (recorded by sdd-spec)**: `50FB12B53E37B4CB01E485DD3DE63EEC9D0E32AAACEBB48787EE3DF924B9703C` · **Pre-append length**: `512004 bytes`. The append-only edit guarantees that this hash of bytes 0..512003 is preserved after the append. Post-append verification: re-hash the file and confirm the byte prefix of the unchanged portion still matches the pre-append hash (a SHA-256 over the first 512004 bytes of the post-append file MUST equal `50FB12B53E37B4CB01E485DD3DE63EEC9D0E32AAACEBB48787EE3DF924B9703C`).

## Out of Scope (explicit, inherited from proposal.md §Scope)

- **Backend changes** — `backend/packages/parkos_core/`, Alembic migrations, SQL — zero changes. The `medioPago` data dependency comes from `factura_pagos` rows that Fase 8 writes; F7.3 only reads the value through the `SalidaPayload.medioPago` field that the caller (PagoSheet.tsx) supplies.
- **A-05 `log_transaccional(accion='impreso')` INSERT** — backend concern. F6.2 documents the audit-row payload shape; Fase 8 writes the row. F7.3 declares the `// TODO: Fase 8` anchor in `PagoSheet.tsx` and does NOT call `log_transaccional` directly (audit-first enforcement is at API/ORM/DB per AGENTS.md §1).
- **Fase 8 pago modal UI** — separate cycle (HU-F8.1+). The `PagoSheet.tsx` post-200 trigger is a hole that Fase 8 fills; F7.3 wires the call site, Fase 8 supplies the data.
- **CU-15S `medioPago` derivation** — backend's `factura_pagos.medio_pago` is the source; F7.3's `SalidaPayload.medioPago` is caller-supplied per F5.2 R4 (caller-supplied decimals — no hidden coupling).
- **PDF width policy beyond DEC-SUC-08** — already shipped verbatim; F7.3 reuses `PAGE_RULE`.
- **CI macOS codesign / node-usb-mock / VS Build Tools preflight** — F5.1 follow-ups; not blocking F7.3.
- **Workspace-class `tsc` cascade** — F5.1 follow-up MEDIUM; F7.3 verifies with B-prime scoped tsc pattern (engram id 1742).
- **e2e `printer.spec.ts`** — sandbox F.6 has no exercisable USB device; byte-fixture tests are the verification boundary.

## Coverage matrix

| Area | Happy path | Edge case | Error state |
|---|---|---|---|
| CU-15S byte buffer | REQ-OPS-143 §1 (19 labels discoverable) | REQ-OPS-143 §4 (optional branches respected) | REQ-OPS-143 §6 (printer offline → banner, persisted) |
| CU-15S DEC-SUC-26 markers | REQ-OPS-143 §2 (markers emitted, no raster) | — | — |
| CU-15S sello bytes | REQ-OPS-143 §3 (text-2x opener/reset wrapping sello) | — | — |
| CU-15S HTML fallback | REQ-OPS-143 §5 (field order mirror + DEC-SUC-08) | — | — |
| CU-15SM byte buffer | REQ-OPS-144 §1 (15 labels discoverable) | REQ-OPS-144 §3 (`Tiempo` field added) | — |
| CU-15SM sello bytes | REQ-OPS-144 §2 (0x1B 0x21 0x30 sentinel pinned) | — | — |
| CU-15SM discriminator | REQ-OPS-144 §4 (`esMensualidad: z.literal(true)`) | — | — |
| CU-15SM HTML fallback | REQ-OPS-144 §5 (field order mirror + DEC-SUC-08) | — | — |
| CU-15SM encabezado dynamic | REQ-OPS-144 §6 (not corpus-fixed) | — | — |
| Salida wiring immediate | REQ-OPS-145 §1 (CU-15SM prints immediately on confirm) | — | REQ-OPS-145 §6 (`PARKOS_PRINTER_DISABLED=1` rollback) |
| Salida wiring deferred | REQ-OPS-145 §2 (CU-15S deferred until post-200 with `medioPago`) | REQ-OPS-145 §3 (pre-pago: no print fires) | — |
| Caller-supplied medioPago | REQ-OPS-145 §5 (`factura_pagos.medio_pago` → payload.medioPago) | — | — |
| Wire signature | REQ-OPS-145 §4 (no new IPC; `{ buffer: base64 }` preserved) | — | — |

## Per-field enumeration (plan.md line-numbered trace)

### CU-15S (19 campos, plan.md lines 1793–1808)

| Campo | Source column / ER row | Builder line (post-F7.3) | Required? |
|---|---|---|---|
| 1 Encabezado `PARKINGOS` | fixed string (escposBuilder.ts:244) | line 244 | yes |
| 2 Empresa nombre | `empresa.nombre` | line 246 | yes |
| 3 Dirección | `empresa.direccion` | line 248 | yes |
| 4 NIT | `empresa.nit` | line 247 | yes |
| 5 Régimen | `empresa.regimen` | line 249 | yes |
| 6 Operario | session (plan.md line 1793) | line 250 (NEW, replaces current F5.2 skeleton) | yes |
| 7 Sello `*** TIQUETE DE SALIDA ***` | fixed string (plan.md line 1794) | line 252 (REPLACES current `'*** SALIDA ***'`) | yes |
| 8 Folio | `salidas.uuid` | line 255 | yes |
| 9 Tarifa aplicada | `tarifas_sucursal` (plan.md line 1796) | NEW line (insert) | yes |
| 10 Fecha operación | `salidas.fecha_salida` (date) | line 257 (split from `formatFechaCorta` join) | yes |
| 11 Hora entrada | `ingreso.fecha_ingreso` (time) | line 257 (concatenated with date) | yes |
| 12 Hora salida | `salidas.fecha_salida` (time) | line 258 | yes |
| 13 Tiempo total | `fecha_salida - fecha_ingreso` | line 259 (already present) | yes |
| 14 Subtotal | from invoice (CU-02/CU-04) | line 261 | yes |
| 15 IVA | from invoice | line 262 | yes |
| 16 Total a pagar | from invoice | line 264 (bold) | yes |
| 17 Medio de pago | `factura_pagos.medio_pago` (plan.md line 1804) | line 266 (data dependent on Fase 8) | yes (post-pago) |
| 18 Placa | `ingreso.placa` | line 256 | yes |
| 19 Horario | `sucursal.horario_atencion` | NEW line (insert) | yes |
| 19 Poliza RC | `documentos` (`tipo='poliza_rc'`) | line 269 (already optional) | optional |
| 19 Resolucion FE | `resolucion_facturacion.numero` | line 267 (already present) | yes |
| 19 Observaciones | operator-typed text | NEW line (insert, optional) | optional |
| 20 QR (DEC-SUC-26) | `qrDataUrl` (folio+placa) | NEW marker before footer | yes |
| 21 Logo (DEC-SUC-26) | `documentos` (`tipo='logo'`) | NEW marker before footer | yes |
| Footer | "Gracias por su visita." | line 271 | yes |

### CU-15SM (15 campos, plan.md line 1810)

| Campo | Source column / ER row | Builder line (post-F7.3) | Required? |
|---|---|---|---|
| 1-6 | (same as CU-15S 1-6) | lines 279-284 + 294 (Operario already present at 294) | yes |
| 7 Sello `*** PAGO CON MENSUALIDAD ***` | fixed string (plan.md line 1787) | line 287 (already correct) | yes |
| 8 Folio | `salidas.uuid` | line 290 | yes |
| 9 Tiempo total | `fecha_salida - fecha_ingreso` | NEW line (insert — current skeleton missing) | yes |
| 10 Fecha operación | `salidas.fecha_salida` (date) | line 292 | yes |
| 11 Hora entrada | `ingreso.fecha_ingreso` (time) | line 292 (concatenated) | yes |
| 12 Hora salida | `salidas.fecha_salida` (time) | line 293 | yes |
| 13 Placa | `ingreso.placa` | line 291 | yes |
| 14 Horario | `sucursal.horario_atencion` | line 295 (already present) | yes |
| 14 Poliza RC | `documentos` (`tipo='poliza_rc'`) | line 297 (already optional) | optional |
| 14 Resolucion FE | `resolucion_facturacion.numero` | NEW line (insert — current skeleton missing) | yes |
| 14 Observaciones | operator-typed text | NEW line (insert, optional) | optional |
| 15 QR (DEC-SUC-26) | `qrDataUrl` (folio+placa) | NEW marker before footer | yes |
| 16 Logo (DEC-SUC-26) | `documentos` (`tipo='logo'`) | NEW marker before footer | yes |
| Footer | "Conserve este tiquete como soporte." | line 299 | yes |

## Next step

Ready for `sdd-design`. Design phase will produce `openspec/changes/hu-f7-3-tiquetes-salida/design.md` with: (i) byte-level field assertion matrix for the 19 + 15 fields (already partially specified in proposal.md Appendix A); (ii) HTML field-order correspondence matrix (Appendix B); (iii) commit sequence (3 commits, 350 LOC forecast, single-PR strategy per `work-unit-commits`); (iv) verification matrix (Appendix C — Vitest byte tests + B-prime scoped tsc + ESLint); (v) post-merge Vite cache invalidation step (per AGENTS.md Operational Timeouts §"Post-merge: invalidar Vite cache").

## Engram handoff

- **topic_key**: `sdd/hu-f7-3-tiquetes-salida/spec`
- **capture_prompt**: `false` (SDD artifact, automated)
- **type**: `architecture`
- **artifact keys**: `openspec/changes/hu-f7-3-tiquetes-salida/specs/operacion/spec.md` + `openspec/specs/operations/spec.md` (delta-appended REQ-OPS-143..145) + `engram://sdd/hu-f7-3-tiquetes-salida/spec`