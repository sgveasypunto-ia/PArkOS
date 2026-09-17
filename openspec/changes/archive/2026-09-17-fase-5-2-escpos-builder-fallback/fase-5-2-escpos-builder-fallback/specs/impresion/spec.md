# Delta for `impresion` — HU-F5.2 escposBuilder base y fallback

`impresion` is a NEW capability. This is a full spec (not a delta) — there is no prior `openspec/specs/impresion/spec.md` to modify.

## Purpose

The `impresion` capability covers the renderer-side composition of thermal-receipt bytes (ESC/POS) and the DOM fallback when the printer does not respond. It guarantees that any of the 4 tiquete types (entrada, salida, salida-mensualidad, reimpresion) can be serialized deterministically from a typed payload and, failing hardware, redirected to `window.print()` with the canonical 80mm page template declared by DEC-SUC-08. No IPC, no USB, no storage — this layer is **pure**.

## ADDED Requirements

### Requirement: Build Any of the 4 Tiquete Types to a Valid ESC/POS Buffer

The system MUST expose a pure function `escposBuilder.build(tipo, payload)` returning a `Buffer` that contains, in order, the documented ESC/POS sequence:

1. `0x1B 0x40` — ESC `@` (init)
2. ...document body...
3. `0x1B 0x61 0x01` — ESC `a` 1 (centered)
4. `0x1B 0x21 0x30` — ESC `!` 0x30 (text 2x height for sellos)
5. `0x1B 0x45` / `0x1B 0x46` — bold on / bold off
6. ...document body...
7. `0x1D 0x56 0x00` — GS `V` 0 (partial cut)

The `tipo` argument MUST be one of the literal strings `'entrada' | 'salida' | 'salida-mensualidad' | 'reimpresion'`. Any other `tipo` MUST throw `escpos_invalid_tipo` (`Error` subclass with `code: 'escpos_invalid_tipo'`). The `payload` argument MUST be validated against the corresponding Zod schema from `escposTemplates.ts`; a Zod failure MUST throw `escpos_payload_missing_field` (`Error` subclass with `code: 'escpos_payload_missing_field'`, `issues: ZodIssue[]`). Both errors MUST be exported as named classes for the caller to `instanceof`-check. **RFC 2119**: MUST (4 tipos, init-then-body-then-cut sequence, ESC/POS opcodes literal, named error classes with `code` discriminator).

#### Scenario: build('entrada', payload) emits init + center + bold + 2x + cut

- GIVEN a valid `EntradaPayload` from the caller
- WHEN `escposBuilder.build('entrada', payload)` runs
- THEN the returned `Buffer` contains, in order: `0x1B 0x40` (init), the encoded UTF-8 body including QR + logo, `0x1B 0x61 0x01` (centered), `0x1B 0x45` (bold on), `0x1B 0x21 0x30` (text 2x height) for the sello, `0x1B 0x46` (bold off), `0x1B 0x21 0x00` (text 2x off), `0x1D 0x56 0x00` (partial cut), `0x0A` (LF).
- AND the function returns a `Buffer` (not `Uint8Array`).

#### Scenario: build('salida', payload) includes subtotal/IVA/total/medio_pago

- GIVEN a valid `SalidaPayload` containing `subtotal`, `iva`, `total`, `medio_pago`
- WHEN `escposBuilder.build('salida', payload)` runs
- THEN the encoded body contains the UTF-8 form of each money field formatted via `formatCOP` (DEC-SUC-07 canonical `Intl.NumberFormat('es-CO', { style:'currency', currency:'COP', minimumFractionDigits:0 })`).
- AND the sello `*** PAGO CON MENSUALIDAD ***` MUST NOT appear (that's CU-15SM, not CU-15S).

#### Scenario: build('salida-mensualidad', payload) emits the 2x-height sello and no money fields

- GIVEN a valid `SalidaMensualidadPayload`
- WHEN the builder runs
- THEN the body contains the sello `*** PAGO CON MENSUALIDAD ***` rendered with `0x1B 0x21 0x30` (DEC-SUC-27 verbatim) at the title slot.
- AND `subtotal`/`iva`/`total`/`medio_pago` MUST NOT appear in the body.

#### Scenario: build('reimpresion', payload) re-uses the original payload schema

- GIVEN a valid `ReimpresionPayload` whose `originalTipo` is one of `entrada|salida|salida-mensualidad`
- WHEN the builder runs
- THEN it dispatches to the matching template renderer with a "REIMPRESIÓN" header and the same body fields as the original.
- AND a `motivo` string MUST appear under the header.

#### Scenario: invalid tipo throws escpos_invalid_tipo

- GIVEN `escposBuilder.build('foo-bar', payload)` is called
- WHEN the typecheck passes (TS) but `'foo-bar'` is not in the union
- THEN the call throws an `Error` whose `code === 'escpos_invalid_tipo'`.
- AND the message names the offending tipo.

#### Scenario: payload missing required field throws escpos_payload_missing_field

- GIVEN an `EntradaPayload` missing `placa`
- WHEN `escposBuilder.build('entrada', payload)` is called
- THEN the call throws an `Error` whose `code === 'escpos_payload_missing_field'`.
- AND `error.issues` carries the underlying Zod issues.

### Requirement: Browser Fallback When Thermal Printer Is Unavailable

The system MUST expose `fallbackBrowser.print(tipo, payload)` which, when the thermal printer does not respond (caller-driven signal: a downstream service can decide if/when to invoke this — F5.2 only owns the rendering and invocation), constructs a transient `<div>` containing the same semantic content as the ESC/POS body, injects a `<style>` element declaring `@page { size: 80mm auto; margin: 2mm }` (DEC-SUC-08 verbatim), and calls `window.print()`. The injected `<style>` MUST be removed from the DOM after `window.print()` resolves. The caller MUST NOT need to import any F5.1 dependency to use this fallback. **RFC 2119**: MUST (transient div, @page rule, window.print() invocation, style cleanup).

#### Scenario: fallbackBrowser.print emits @page{size:80mm auto;margin:2mm}

- GIVEN a valid `EntradaPayload`
- WHEN `fallbackBrowser.print('entrada', payload)` runs
- THEN the DOM receives a `<style>` whose rule contains `@page { size: 80mm auto; margin: 2mm }`.
- AND `window.print()` is called exactly once.

#### Scenario: each tiquete tipo has its own HTML renderer that mirrors the ESC/POS body

- GIVEN any of the 4 tipos
- WHEN `fallbackBrowser.print(tipo, payload)` runs
- THEN the rendered HTML contains the same fields (text, money, sello) the ESC/POS body would emit, in the same order, with semantic `<h1>`/`<p>` tags.

### Requirement: Builder is Pure — No Side Effects, No I/O

The function `escposBuilder.build(tipo, payload)` MUST NOT touch the DOM, network, filesystem, USB, IPC, electron-store, `window`, `document`, or any global mutable state. The function MUST be referentially transparent: identical inputs produce identical outputs (modulo `vitest` timestamp injection if explicitly opted into via a `now?: () => Date` parameter on the payload). Time- and UUID-bearing fields MUST be supplied by the caller, not generated. **RFC 2119**: MUST (pure, caller-controlled timestamp/uuid).

#### Scenario: build() does not call window.print()

- GIVEN a valid payload
- WHEN `escposBuilder.build('entrada', payload)` runs in jsdom
- THEN `window.print` is NOT invoked (verified by `vi.spyOn(window, 'print')` with `toHaveBeenCalledTimes(0)`).

#### Scenario: build() does not import any electron/USB module

- GIVEN the source `escposBuilder.ts`
- WHEN `grep -E "from '(electron|escpos-usb|node:)'" src/lib/print/escposBuilder.ts` is run
- THEN no matches are found.

### Requirement: Caller-Supplied Decimals and Timestamps Avoid Hidden Coupling

The system MUST NOT infer amounts from `ingreso`/`salidas` ER rows at runtime; the caller MUST supply already-computed money values (`subtotal`, `iva`, `total`, `medio_pago`) and timestamps (`fechaEntrada`, `fechaSalida`) in the payload. This isolates F5.2 from future changes in the ER (A-05 notes; DEC-SUC-23) and keeps the builder deterministic. **RFC 2119**: MUST (caller-supplied, no DB lookup).

#### Scenario: build accepts a payload with timestamps as ISO strings

- GIVEN `EntradaPayload = { ..., fechaEntrada: '2026-09-16T08:30:00Z', placa: 'ABC123' }`
- WHEN `escposBuilder.build('entrada', payload)` runs
- THEN the body emits `Fecha: 16/09/2026 08:30` formatted via `Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' })`.
- AND no call to `new Date()` (i.e., no implicit "now") is made.

## Capability Boundary Summary

| Layer | Owner | Surface |
|---|---|---|
| Hardware + IPC + queue | **F5.1** | `bridge.imprimir(payload)` |
| Byte composition + fallback | **F5.2 (this spec)** | `escposBuilder.build(...)`, `fallbackBrowser.print(...)` |
| Caller wiring (entrada/salida) | F6.2 / F7.3 | builds the payload object, passes to F5.2 |
| Persistence of `impreso` state | F6.1+ (backend) | `log_transaccional` insert (A-05) |
