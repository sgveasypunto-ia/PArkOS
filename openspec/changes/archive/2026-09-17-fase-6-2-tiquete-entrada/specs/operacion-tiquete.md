# Delta for operacion-tiquete (F6.2 — Tiquete de entrada CU-15E)

> Disambiguator from F6.1 (`operacion-ingreso`). Delta folds into the flat canonical `openspec/specs/impresion.md` at archive time per F5.1 archive-report precedent (line 99). 17-field tiquete per `plan.md` lines 1606-1653. DEC-SUC-26 adds QR + logo to the 15 literal CU-15E fields. DEC-SUC-21 forbids persisting `tipo_entrada`. ABIERTO-01 fixes QR content = `parkos://ingreso/<uuid>?placa=<placa>`.

## ADDED Requirements

### Requirement: Tiquete de entrada MUST emit exactly 17 fields

The system MUST emit a tiquete de entrada containing the **15 literal CU-15E fields** in the source order specified by `plan.md` (Encabezado, Nombre de la empresa, Dirección, NIT, Régimen, Operario, "TIQUETE DE ENTRADA" tipo documento, Folio, Tarifa aplicada, Fecha, Hora de entrada, Placa, Horario de atención, Póliza RC, Observaciones) plus the **2 añadidos per DEC-SUC-26** (QR, Logo), in that order, with no extra or missing fields.

#### Scenario: All 17 fields present and sourced from the documented ER row

- GIVEN an ingreso confirmed (HTTP 200 from `POST /operacion/ingresos`) with `uuid_sucursal`, `uuid_usuario`, `ingreso.uuid` (folio), `ingreso.placa`, `ingreso.fecha_ingreso` (date + hour), `ingreso.uuid_tarifa_sucursal`, and `uuid_empresa`
- WHEN the entry tiquete builder runs
- THEN the buffer MUST contain, in order, the 15 literal CU-15E strings sourced from `sucursal`, `empresa`, `ingreso`, `tarifas_sucursal` and `usuarios` (one field per plan.md table line 1616-1634) PLUS the QR + logo bitmaps

#### Scenario: Mensualidad tag derived without persisting `tipo_entrada`

- GIVEN an ingreso whose `uuid_subscripcion_cliente IS NOT NULL`
- WHEN the tiquete is built
- THEN the buffer MUST include a `MENSUALIDAD` tag line under the "TIQUETE DE ENTRADA" sello
- AND the `ingreso` row MUST NOT receive any `tipo_entrada` column write (DEC-SUC-21)

#### Scenario: Browser fallback when the thermal printer is offline

- GIVEN `bridge.imprimir` returns `{ok: false, error: 'printer_offline'}` (F5.1 R3, R6) within 500 ms
- WHEN the F6.2 fallback handler runs
- THEN `fallbackBrowser.print('entrada', payload)` MUST construct a transient `<div>` containing the same 17 fields as semantic HTML and invoke `window.print()` exactly once
- AND the injected `<style>` MUST contain the verbatim DEC-SUC-08 `@page { size: 80mm auto; margin: 2mm }` rule

### Requirement: TypeScript MUST enforce exhaustiveness at build time

The system MUST declare `TiqueteEntradaPayload` as a `readonly` mapped type over the 17-key `TiqueteEntradaCampos` so that removing or renaming any key fails `tsc --noEmit` (compile-time guard, complements the runtime Zod check).

#### Scenario: Removing a key breaks the build

- GIVEN the 17-key `TiqueteEntradaCampos` interface
- WHEN a developer removes `{campo:'cuarto'; fuente:'sucursal.nit'}` (one of the 17)
- THEN `tsc` MUST exit non-zero with `TS2741: Property 'cuarto' is missing in type 'TiqueteEntradaPayload'`

#### Scenario: Zod runtime check agrees with tsc

- GIVEN a payload with all 17 fields
- WHEN `entradaPayloadSchema.parse(payload)` runs
- THEN it MUST succeed (no throw)
- AND given a payload with any field removed
- WHEN the same parse runs
- THEN it MUST throw `EscposPayloadMissingFieldError` with `code === 'escpos_payload_missing_field'` and `error.issues` carrying the missing path

### Requirement: QR content MUST be ABIERTO-01 default

The system MUST encode the QR with the static string `parkos://ingreso/<ingreso.uuid>?placa=<ingreso.placa>` per ABIERTO-01 (no dynamic URL, no extra fields). The QR rasterization is the caller's responsibility; the builder accepts the resulting `qrDataUrl` string verbatim per F5.2 R4.

#### Scenario: QR encodes folio + placa only

- GIVEN `ingreso.uuid = "11111111-..."` and `ingreso.placa = "ABC123"`
- WHEN the QR rasterizer produces the data URL
- THEN the encoded string MUST equal `parkos://ingreso/11111111-...?placa=ABC123`
- AND MUST NOT contain additional query parameters

### Requirement: Logo + Póliza RC MUST come from `documentos` (A-01)

The system MUST fetch the logo from `GET /documentos?uuid_sucursal=X&tipo=logo` (returns `documento_b64`) and the póliza RC from `GET /documentos?uuid_sucursal=X&tipo=certificado`. The cache is the caller's responsibility (`electron-store` key `parkos.documents.v1`, TTL 24 h); the builder never hits the ER directly per F5.2 R3 purity.

#### Scenario: Logo missing does not block ingreso registration

- GIVEN the logo row in `documentos` does not exist (cold cache + ER row absent)
- WHEN the builder runs
- THEN the tiquete MUST emit the 16 other fields
- AND the logo position MUST render a placeholder glyph (e.g., `▢`) without blocking the print or the ingreso registration

### Requirement: A-05 hook MUST be the backend concern (F6.2 documents, does not implement)

F6.2 MUST document the exact `log_transaccional` payload shape the backend must INSERT after `bridge.imprimir` resolves; F6.2 MUST NOT implement the backend endpoint. Payload shape: `{tabla_afectada: 'ingreso', uuid_registro_afectado: <ingreso.uuid>, accion: 'impreso', datos_nuevos: {estado: 'impresa'} | {estado: 'pendiente de impresión'}}`. Retention 5+ años inherits from `log_transaccional.fecha_retencion_hasta`.

#### Scenario: F6.2 ships documentation only

- GIVEN F6.2 is the renderer-side change
- WHEN the change lands
- THEN the F6.2 PR MUST include `docs/f6-2-integration.md` describing the row payload shape and the `Principal.tsx` wiring site
- AND MUST NOT add any `parkos_core/api/` endpoint (that is a separate HU)

## Error Catalog (F6.2)

| Code | Class | When | Caller action |
|------|-------|------|--------------|
| `escpos_payload_missing_field` | `EscposPayloadMissingFieldError` | Any of the 17 fields absent at parse time | Bubble to operator UI; surface the field path from `error.issues` |
| `escpos_invalid_tipo` | `EscposInvalidTipoError` | F5.2 reused (caller passes non-union `tipo`) | Bubble to caller; F6.2 inherits |
| `bridge_imprimir_failure` | Typed result `{ok:false, error:'printer_offline' \| 'printer_disconnected' \| 'invalid_payload', queueId?}` | F5.1 IPC returns non-ok | Fallback to `fallbackBrowser.print('entrada', payload)`; UI shows transient banner; A-05 row records `pendiente de impresión` once the backend lands |

## Cross-coupling boundary

F6.2 consumes F5.2's `EntradaPayload` (extends, never duplicates). F6.2 produces bytes consumed by F5.1's `bridge.imprimir({ buffer })`. F6.2 does **not** call the engine, the USB, the electron-store, the `documentos` ER, or the backend. F6.1's `Principal.tsx` is the wiring site (NOT modified by F6.2; F6.2 only writes the integration contract document).

## Constraints (F6.2)

(1) `TiqueteEntradaPayload` MUST be `readonly` on every key — no mutation after build. (2) The builder MUST NOT add fields beyond the 17. (3) `qrDataUrl` and `logoDataUrl` MUST be base64 strings (`data:image/...;base64,...`) or empty strings — the builder never rasterizes. (4) ISO date strings MUST be formatted via `Intl.DateTimeFormat('es-CO', {dateStyle:'short', timeStyle:'short'})` from caller-supplied ISO strings per F5.2 R4 — no implicit `new Date()`. (5) No `modelo_datos_er.mmd` change. (6) No physical DELETE attempted at any layer (audit-first canon).

## Out of Scope (F6.2)

CU-15S (salida) / CU-15SM (salida-mensualidad) — F7.x per plan. Backend `log_transaccional` INSERT endpoint — separate HU. PDF generation. Email/SMS delivery of the tiquete. Auto-discovery of `documentos` cache (future enhancement). `formatCOP` consolidation with F2.x (F5.2 carries the warning forward).

## References (F6.2)

`plan.md` lines 1606-1653 (HU-F6.2 contract); lines 412-492 (DEC-SUC-08 `@page` rule, DEC-SUC-26 QR+logo, DEC-SUC-27 orden impresión, ABIERTO-01 QR content); lines 446-462 (A-01 póliza RC, A-05 estado de impresión); `modelo_datos_er.mmd` (`ingreso` `[L-E]`, `sucursal`, `documentos` `[V]`, `usuarios` — read-only); `openspec/specs/impresion.md` canonical (F5.1 + F5.2 merged); F5.2 archive-report (entrada payload declared); F5.1 archive-report (`bridge.imprimir` contract + B-prime scoped tsc precedent).