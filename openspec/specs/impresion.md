# Spec: Impresión térmica (HU-F5.1)

## Purpose

Main-process thermal printer service for tiquetes (HU-F5.1, plan.md lines 1446-1474). Enables Fases 6-8 (CU-15E/S/SM + reimpresión con costo) without each reinventing the USB→ESC/POS→error→retry cycle.

## Requirements (6 total, 13 scenarios)

**R1 USB enumeration MUST filter Printer class**: `bridge.usb.list()` returns ONLY devices with `bDeviceClass === 0x07` (Printer, USB-IF standard). 2 scenarios: (a) printer detected with class 0x07; (b) non-printer USB filtered out in <100 ms.

**R2 Print latency P95 <500 ms for 1 KB buffer**: handler entry → `escpos-usb` `print()` callback, measured via `performance.now()`, logged to `electron-log` channel `print.perf`. 2 scenarios: (a) 95 of 100 sequential calls <500 ms; (b) call 100 latency ≤ 2× median of first 10 (no thermal throttling).

**R3 Disconnection at mid-print MUST NOT crash main process**: catch `LIBUSB_ERROR_NO_DEVICE`/`EPERM`/`EBUSY` from `escpos-usb`, log to `electron-log` channel `print.error`, emit `print:status` to renderer, return typed error. 2 scenarios: (a) unplug mid-print → `{ok:false, error:'printer_offline', queueId}` + push event + main process alive; (b) 3 consecutive failures → `bridge.usb.list()` empty, banner "Impresora desconectada".

**R4 IPC payload MUST be Zod-validated BEFORE hardware access**: `printPayloadSchema.parse(payload)` BEFORE any `escpos-usb` call. Validation failure → typed `ZodError`, never reaches hardware. 2 scenarios: (a) missing required fields → ZodError with field paths, no hardware call (verified via spy); (b) invalid `uuidRegistro` (not UUID v4) → ZodError at `uuidRegistro`.

**R5 Retry queue MUST survive app restart**: persisted in `electron-store` key `parkos.print.queue.v1` as JSON `{buffer (base64), vid, pid, ticketId, uuidRegistro?, attempts, nextRetryAt (epoch ms), addedAt}`. On boot, reload + drain if `nextRetryAt <= now`; schedule timer for future. 3 scenarios: (a) app killed mid-backoff → restart resumes queue; (b) backoff schedule = `[5000, 15000, 60000, 60000, 60000][N-1]` ms for attempts 1-5; (c) 5 attempts exhausted → `estado='fallido_permanente'` + push `print_failed_terminal`; item NOT deleted from disk (audit-first; `clearFailed(ticketId)` only changes display).

**R6 `bridge.imprimir` MUST return immediately**: not wait for backoff. 2 scenarios: (a) first attempt fails → renderer gets `{ok:false, error:'printer_offline', queueId}` within 500 ms, shows banner; (b) drain emits `print_succeeded`/`print_failed_terminal` events; banner cleared or escalated to strongest error.

## Error Catalog

`bridge_imprimir_invalid_payload` (ZodError → 422 to renderer, no retry); `printer_offline` (recoverable → banner + poll); `printer_disconnected` (3 consecutive → banner "Impresora desconectada"); `print_failed_terminal` (5 attempts → "Tiquete no impreso — reimprimir manualmente" toast).

## Constraints

(1) F5.1 accepts ONLY `buffer: base64-string`. Rejects `lines: PrintLine[]` — F5.2 composes bytes. (2) No silent deletes on queue items. (3) No DIAN writes — caller (F6.1+) writes `log_transaccional(accion='impreso')` using `uuidRegistro` from payload. (4) Single-instance per DEC-SUC-19. (5) macOS `build/entitlements.mac.plist` `com.apple.security.device.usb = true` REQUIRED for `hardenedRuntime` build.

## Dependencies

`escpos-usb@^3.0.0-alpha.4` (already in deps); `electron-store@^8.2.0` (already); `zod@^3.23.8` (already); `node-usb-mock` (devDep NEW); `@types/escpos-usb` (devDep NEW, conditional — shim local fallback if alpha not on DefinitelyTyped).

## Out of Scope

HU-F5.2 (`escposBuilder` + `fallbackBrowser.print`); CU-15E auto-print (F6.1+); CU-15S/SM (F7+); reimpresión con costo (Fase 8). F5.2/F6+ callers do `bridge.imprimir({ buffer: base64(escposBuilder.build(...)) })`.

## References

plan.md lines 1446-1474 (HU-F5.1 ACs verbatim); line 423 (DEC-SUC-08); line 432 (DEC-SUC-17); line 434 (DEC-SUC-19); lines 456-457 (A-05); `openspec/specs/operations/spec.md` REQ-OPS-112 (forward hook fulfilled); precedent: `openspec/changes/archive/2026-09-17-fase-4-2-tarifas-vigentes/`.


## F5.2 — escposBuilder + browser fallback (2026-09-17)

Fase 5 builds the printing base **before** Fases 6-8 need to emit tiquetes. F5.1 already shipped `bridge.imprimir` accepting `buffer: base64-string`. F5.2 ships the renderer-side **pure** library that *produces* those bytes: `escposBuilder.build(tipo, payload): Buffer` deterministically serializes any of the 4 tiquete tipos (entrada / salida / salida-mensualidad / reimpresion) to the canonical ESC/POS byte sequence required by the thermal printer, and `fallbackBrowser.print(tipo, payload)` falls back to `window.print()` with verbatim DEC-SUC-08 `@page` CSS when the thermal printer is unavailable. Pure renderer lib: no IPC, no USB, no storage, no DOM (except in the explicitly DOM-bound fallback). Caller (F6.2 / F7.3) wires payload → `bridge.imprimir({ buffer: build(tipo, payload).toString('base64') })` per F5.1's contract.

### Requirements (4 total, 13 scenarios)

**R1 Build any of the 4 tiquete tipos to a valid ESC/POS Buffer**: `escposBuilder.build(tipo, payload): Buffer` MUST emit, in order: `0x1B 0x40` (ESC @ init) → UTF-8 body → `0x1B 0x61 0x01` (centered) → `0x1B 0x21 0x30` (text 2x height for sellos) → `0x1B 0x45` / `0x1B 0x46` (bold on/off) → `0x1D 0x56 0x00` (partial cut). `tipo` MUST be `'entrada' | 'salida' | 'salida-mensualidad' | 'reimpresion'`. Invalid `tipo` throws `EscposInvalidTipoError` (code `escpos_invalid_tipo`; message names the offending tipo). Payload missing required field throws `EscposPayloadMissingFieldError` (code `escpos_payload_missing_field`; `error.issues` carries the Zod issue list). Both error classes exported for `instanceof`-check. 6 scenarios: build each of 4 tipos end-to-end; invalid tipo; missing field.

**R2 Browser fallback when thermal printer is unavailable**: `fallbackBrowser.print(tipo, payload)` MUST construct a transient `<div>` with the same semantic content as the ESC/POS body, inject a `<style>` containing the verbatim `@page { size: 80mm auto; margin: 2mm }` rule (DEC-SUC-08), call `window.print()` exactly once, and remove the style from the DOM via `cleanupPageStyle()` once `window.print()` resolves. Each of the 4 tipos MUST have its own HTML renderer that mirrors the corresponding ESC/POS body layout. Caller MUST NOT import any F5.1 dependency from this module. 2 scenarios: `@page` rule injected; per-tipo HTML renderers mirror the buffer body.

**R3 Builder is pure — no side effects, no I/O**: `escposBuilder.build` MUST NOT touch DOM, network, filesystem, USB, IPC, electron-store, `window`, `document`, or any global mutable state. The function MUST be referentially transparent. Time and UUID MUST be supplied by the caller (no implicit `new Date()` / `crypto.randomUUID()`). 2 scenarios: `window.print()` is never invoked; source contains no `from 'electron' | 'escpos-usb' | 'node:'` import.

**R4 Caller-supplied decimals and timestamps avoid hidden coupling**: Builder MUST NOT infer amounts from `ingreso` / `salidas` ER rows at runtime; the caller supplies already-computed money (`subtotal`, `iva`, `total`, `medio_pago`) and timestamps (`fechaEntrada`, `fechaSalida`) in the payload. Isolate F5.2 from ER changes (A-05, DEC-SUC-23) and keep the builder deterministic. Dates formatted via `Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' })` from caller-supplied ISO strings. 1 scenario: build accepts ISO-string timestamps and emits `Fecha: dd/mm/yyyy hh:mm` without calling `new Date()`.

### Error Catalog (F5.2)

`escpos_invalid_tipo` (`EscposInvalidTipoError` thrown by `build` when `tipo` is not in the union — bubble to caller; F6.x / F7.x catches and surfaces as a typed error to the operator); `escpos_payload_missing_field` (`EscposPayloadMissingFieldError` thrown by `build` when Zod validation fails — `error.issues` carries the Zod issue list; caller surfaces field paths in the operator UI). Both errors are exported as named classes; the `readonly code` discriminant enables `instanceof`-free catch blocks.

### escposTemplates.ts (NEW)

Typed payload interfaces (`EntradaPayload`, `SalidaPayload`, `SalidaMensualidadPayload`, `ReimpresionPayload`) + 5 Zod schemas (one per tipo plus a shared base refiner for `uuidRegistro`, `fecha*` ISO strings, optional `qrDataUrl` / `logoDataUrl`) + inline `formatCOP` helper (`Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', minimumFractionDigits: 0, maximumFractionDigits: 0 })`) carrying a `SYNCH NOTE` doc-block referencing F2.x. Exports the `TiqueteTipo` discriminated union. No I/O. Pure module.

### escposBuilder.ts (NEW)

`build(tipo: TiqueteTipo, payload: unknown): Buffer` — validates payload via Zod, dispatches by `tipo` to one of 4 `build*Buffer()` functions (init → body UTF-8 → sello (if any) → cut + LF), returns `Buffer.concat([...])`. 9 ESC/POS opcode helpers exported as `Buffer` constants: `escInit` (`0x1B 0x40`), `cutPartial` (`0x1D 0x56 0x00`), `escCenter` (`0x1B 0x61 0x01`), `escBoldOn` (`0x1B 0x45`), `escBoldOff` (`0x1B 0x46`), `escText2x` (`0x1B 0x21 0x30`), `escTextReset` (`0x1B 0x21 0x00`), plus LF and ASCII line-emit helpers. 2 named error classes: `EscposInvalidTipoError` (code `escpos_invalid_tipo`) and `EscposPayloadMissingFieldError` (code `escpos_payload_missing_field`; carries `issues: ZodIssue[]`). Pure module: imports only `zod` (type-only) and local `./escposTemplates`. Verified by grep — no `from 'electron' | 'escpos-usb' | 'node:'` imports.

### fallbackBrowser.ts (NEW)

`print(tipo: TiqueteTipo, payload: unknown): void` — constructs a transient `<div>` body, injects a `<style>` element containing the verbatim `@page { size: 80mm auto; margin: 2mm }` rule (DEC-SUC-08) plus optional per-tipo CSS, calls `window.print()` exactly once, then removes the injected style from the DOM via `cleanupPageStyle()`. 4 `render*TiqueteHtml()` functions (entrada / salida / salida-mensualidad / reimpresion) mirror the corresponding ESC/POS body layout with semantic `<h1>` / `<p>` tags. The **only** DOM-touching file in `src/lib/print/`.

### Test coverage

| Suite | Exit | Cases |
|---|---|---|
| `npx vitest run src/lib/print` | `0` | **46/46 passing** (escposBuilder.test.ts = 12, escposBuilder.types.test.ts = 17, fallbackBrowser.test.ts = 17) |
| `npx tsc --noEmit -p tsconfig.f5-2-verify.json` (B-prime scoped) | `0` | 0 errors on the 3 production files |
| `npx eslint src/lib/print --max-warnings 0` | `0` | 0 errors / 0 warnings |

Byte-level fixtures verify the canonical ESC/POS opcodes verbatim: `0x1B 0x40` (init), `0x1B 0x61 0x01` (center), `0x1B 0x45` (bold on), `0x1B 0x21 0x30` (text 2x height), `0x1D 0x56 0x00` (partial cut). Purity is enforced at the test layer via `vi.spyOn(window, 'print').toHaveBeenCalledTimes(0)` and at the source layer via `grep -E "from '(electron|escpos-usb|node:)'" src/lib/print/escposBuilder.ts` returning zero matches.

### Carry-forward: formatCOP inline copy (TODO SYNCH WITH F2.x)

`escposTemplates.ts::formatCOP` is an inline copy of the rule from `apps/electron-sucursal/src/features/caja/lib/format.ts` (F3.3 T1). F2.x is committed to ship `src/lib/format/formatCOP.ts` as a shared module. The doc-block carries the `SYNCH NOTE` plus an explicit reference to AGENTS rule 6 (no blockers between phases). Kept as a **warning** in the verify report (not a blocker). When F2.x ships, replace the inline export with `export { formatCOP } from '@/lib/format/formatCOP'` in a 1-line follow-up PR.

## Cross-coupling boundary

F5.2 returns `Buffer`; F5.1 consumes base64-string at `bridge.imprimir({ buffer: build(tipo, payload).toString('base64') })`. F5.2 files are additive and confined to `src/lib/print/{escposTemplates, escposBuilder, fallbackBrowser}.ts` + their `__tests__/`. F5.2 minimally touches the renderer test harness (`src/renderer/{test-setup,global.d}.ts`) for the vitest `Buffer` polyfill + the tsc `Buffer` global declaration. **No** edits to backend/, `modelo_datos_er.mmd`, `apps/ui-kit`, or any F5.1 main-process code (`electron/{main,preload,services,ipc,types,bridge.d}.ts`, `build/entitlements.mac.plist`, `electron-builder.yml`).

## Constraints (F5.2)

(1) `escposBuilder` MUST remain pure — no DOM / IPC / USB / electron-store access. (2) `fallbackBrowser` MUST inject the verbatim DEC-SUC-08 `@page { size: 80mm auto; margin: 2mm }` CSS rule, not a paraphrase. (3) `Buffer` polyfill is **test-runtime only** via `buffer@^6.0.3` in devDependencies; renderer production code never imports `'buffer'` — F5.1's main process owns `Buffer` end-to-end. (4) QR + logo rasterization is the bridge's responsibility (F5.1); F5.2 forwards `qrDataUrl` / `logoDataUrl` strings verbatim. (5) Caller (F6.2 / F7.3) decides CUÁNDO llamar — DEC-SUC-27 (orden impresión auto / after-pago / immediate) is out of F5.2 scope.

## Dependencies (F5.2)

`zod@^3.23.8` (already in deps; type-only import in `escposBuilder.ts`, runtime import in `escposTemplates.ts`); `buffer@^6.0.3` (**devDependency**, test polyfill only); `vitest` + `jsdom` (already configured in `apps/electron-sucursal`).

## Out of Scope (F5.2)

CU-15E auto-print integration (F6.2); CU-15S / CU-15SM (F7.x); reimpresión con costo (Fase 8); `log_transaccional(accion='impreso')` persistence (F6.1+ per A-05); `formatCOP` consolidation with F2.x (carried as warning, not blocker); native-binding shim for `escpos-usb` (F5.1 owns).

## References (F5.2)

plan.md lines 1476-1490 (HU-F5.2 contract); plan.md:412-492 (DEC-SUC-08 `@page{size:80mm auto;margin:2mm}`, DEC-SUC-26 QR + logo as payload strings, DEC-SUC-27 orden impresión — caller-side); F5.1 archive-report (engram id 1763) for the canonical handoff SHA256; `sdd/fase-5-2-escpos-builder-fallback/{proposal, spec, design, tasks, apply-progress, verify-report}` observations (engram ids 1750, 1751, 1753, 1754, 1757, 1760).



## F6.2 — Tiquete de entrada 17 campos + QR + logo (2026-09-17)

Fase 6.2 ships the canonical composition for the **tiquete de entrada** (CU-15E) — the 17-field payload the operador hands the cliente on `POST /operacion/ingresos` HTTP 200. F6.2 is a **renderer-side pure** extension of F5.2's `escposBuilder` + `fallbackBrowser` modules. F6.2 never reimplements: it tightens F5.2's already-declared `EntradaPayload` to the **17-key `TiqueteEntradaCampos`** mapped type (15 literal CU-15E fields + 2 DEC-SUC-26 additions: `qrDataUrl`, `logoDataUrl`), exports the `buildEntradaPayload()` factory + `entradaPayloadSchema` Zod refinement, and mirrors the 17-field layout in `renderEntradaTiqueteHtml`. The end-to-end call chain is F6.1's `Principal.tsx` `onSuccess` → `buildEntradaPayload(...)` → `escposBuilder.build('entrada', payload)` (F5.2) → `bridge.imprimir({ buffer: bytes.toString('base64') })` (F5.1). A-05 (post-print `log_transaccional` row) is **documented** in `ingreso-tiquete-integration.md` and is a separate backend HU — F6.2 does not implement it.

### TiqueteEntradaPayload (17 readonly)

Declared in `apps/electron-sucursal/src/lib/print/escposTemplates.ts` as a **mapped type over `TiqueteEntradaCampos`** so removing or renaming any of the 17 keys fails `tsc --noEmit` with `TS2741: Property '<key>' is missing in type 'TiqueteEntradaPayload'` (compile-time exhaustiveness guard complements the runtime Zod refinement). Spanish ordinal names (`primero..quinceavo`) keep the tsc error messages unambiguous. The 17 keys, in source order per `plan.md` lines 1616-1634:

| # | Key | Source | Type |
|---|---|---|---|
| 1 | `primero` | `sucursal.encabezado` | string (sucursal header) |
| 2 | `segundo` | `empresa.nombre` | string |
| 3 | `tercero` | `empresa.direccion` | string |
| 4 | `cuarto` | `empresa.nit` | string |
| 5 | `quinto` | `empresa.regimen` | string |
| 6 | `sexto` | `usuarios.nombre` (operario) | string |
| 7 | `septimo` | sello `"*** TIQUETE DE ENTRADA ***"` | string |
| 8 | `octavo` | `ingreso.uuid` (folio) | UUID v4 |
| 9 | `noveno` | `tarifas_sucursal` (formateado es-CO) | string |
| 10 | `decimo` | `ingreso.fecha_ingreso` (dateStyle:short) | string |
| 11 | `onceavo` | `ingreso.fecha_ingreso` (timeStyle:short) | string |
| 12 | `doceavo` | `ingreso.placa` | string |
| 13 | `treceavo` | `sucursal.horario_atencion` | string |
| 14 | `catorceavo` | `documentos[tipo='certificado']` (A-01 póliza RC) | string |
| 15 | `quinceavo` | operator-supplied observations | string |
| 16 | `qrDataUrl` | caller-supplied QR rasterizer (DEC-SUC-26, ABIERTO-01) | string (data:image/...;base64,...) |
| 17 | `logoDataUrl` | `documentos[tipo='logo'].documento_b64` (DEC-SUC-26) | string (data:image/...;base64,...) |

The `TiqueteEntradaCampos` interface is exported verbatim; `TiqueteEntradaPayload = { readonly [K in keyof TiqueteEntradaCampos]: TiqueteEntradaCampos[K] }`. Optional `esMensualidad?: boolean` is an additive control flag on `EntradaPayload` (NOT counted in the 17-key conceptual total) — drives the `MENSUALIDAD` tag conditional per DEC-SUC-21 (tipo_entrada NEVER persisted as column).

### buildEntradaPayload factory

`buildEntradaPayload(ingreso, sucursal, empresa, operario, tipoVehiculo, tarifa, documentos, fechaHora): EntradaPayload` — pure function in `escposTemplates.ts` that assembles the 17 fields from 8 caller inputs. Reuses F5.2's Zod base refiner for `uuidRegistro`, ISO `fecha*` strings, optional `qrDataUrl` / `logoDataUrl`. The factory exports `entradaPayloadSchema = entradaBase.refine((p): p is TiqueteEntradaPayload => Object.keys(TiqueteEntradaCampos).every(k => k in p), { message: 'entrada_payload_missing_field' })`. On any missing field, the schema throws `EscposPayloadMissingFieldError` with `code: 'escpos_payload_missing_field'` and `error.issues` carrying the Zod issue path (F5.2 named error class reused). The factory's `qrDataUrl` default is the ABIERTO-01 sentinel `parkos://ingreso/<ingreso.uuid>?placa=<ingreso.placa>`; production callers (F6.1's `Principal.tsx`) MUST overwrite with a real `qrcode`-library rasterized `data:image/png;base64,...` before calling `escposBuilder.build('entrada', payload)` (F5.2 R4 purity preserved — builder never rasterizes).

### fallbackBrowser renderEntradaTiqueteHtml

Extended `fallbackBrowser.ts::renderEntradaTiqueteHtml(payload)` mirrors the 17-field layout with semantic `<h1>` sello + 15 `<p>` literals + `<img src="logoDataUrl">` + `<img src="qrDataUrl">` + conditional `<p class="mensualidad">MENSUALIDAD</p>` when `payload.esMensualidad === true`. The DEC-SUC-08 verbatim `@page { size: 80mm auto; margin: 2mm }` CSS rule is injected via `injectPageStyle()` (F5.2) and removed via `cleanupPageStyle()` after `window.print()` resolves. When `logoDataUrl === ''` (cold cache + ER row absent), the logo position renders the placeholder glyph `▢` — the 16 other fields still print and the ingreso registration is NOT blocked (render-time guard per design decision; A-05 marks `pendiente de impresión` if the backend lands). The `print('entrada', ...)` dispatcher routes through `renderEntradaTiqueteHtml` (F5.2's `renderEntradaHtml` is preserved as an alias for `renderReimpresionHtml` backward compat).

### Test coverage

| Suite | Exit | Cases |
|---|---|---|
| `npx vitest run src/lib/print` | `0` | **122/122 passing** across 5 files (escposBuilder.test.ts = 12 F5.2 baseline, escposBuilder.types.test.ts = 17 F5.2+F6.2 sello rename, escposBuilder.entrada.test.ts = **47 NEW** (17 byte-presence + 17 Zod rejection + Mensualidad + missing-field error class + factory purity + 8 structural), fallbackBrowser.test.ts = 17 F5.2 baseline, fallbackBrowser.entrada.test.ts = **29 NEW** (17 HTML tag layout + Mensualidad conditional + logo placeholder + `window.print()` exactly-once + `@page` CSS injection)) |
| `npx tsc --noEmit -p tsconfig.f6-2-verify.json` (B-prime scoped) | `0` | 0 errors on the 3 F6.2 NEW+MODIFIED production files |
| `npx eslint src/lib/print --max-warnings 0` | `0` | 0 errors / 0 warnings |

**76 new vitest scenarios** vs F5.2's 46 (F6.2 adds 47 byte-level + Zod + Mensualidad scenarios in `escposBuilder.entrada.test.ts` and 29 HTML-layout + Mensualidad + logo-placeholder + `window.print()` exactly-once scenarios in `fallbackBrowser.entrada.test.ts`). E2E (`playwright test e2e/print.spec.ts --grep "F6.2"`) is **DEFERRED** to CI per sandbox F.6 + `node-usb-mock` not installed (same precedent as F5.1/F5.2 e2e deferral). Byte-level fixtures verify the canonical ESC/POS opcodes verbatim and 17-field source order via `Buffer.indexOf(campo) >= 0` per field. Purity is enforced at the source layer via `grep -E "from '(electron|escpos-usb|node:)'" src/lib/print/escposTemplates.ts src/lib/print/escposBuilder.ts` returning zero matches (F5.2 R3 carried forward).

### Carry-forward: backend log_transaccional + QR rasterization

**(1) Backend `log_transaccional` INSERT endpoint (A-05) — separate HU.** F6.2 documents the exact row payload shape (`{tabla_afectada: 'ingreso', uuid_registro_afectado: <ingreso.uuid>, accion: 'impreso', datos_nuevos: {estado: 'impresa'} | {estado: 'pendiente de impresión'}}`) and the wiring site (F6.1 `Principal.tsx` `onSuccess` → after `bridge.imprimir` resolves → backend POST `/log-transaccional/ingreso-impreso`). Retention 5+ años inherits from `log_transaccional.fecha_retencion_hasta`. SHA256 hash chain continues unbroken (per `modelo_datos_er.mmd` lines 386-404) — `hash_anterior` references previous row's `hash_actual` per `uuid_sucursal`. Until the backend ships, the operator UI shows a transient "Impreso (estado local)" banner; the `pendiente de impresión` row is appended when the endpoint lands. No silent drop.

**(2) QR rasterization — caller's responsibility (F5.2 R4 purity preserved).** ESC/POS byte stream has no native QR encoding. F6.2 emits `;QR:<data>` and `;LOGO:<data|▢>` text markers in the buffer; the printer firmware ignores semicolon-prefixed lines, and `bridge.imprimir` (F5.1) can intercept for actual rasterization in a future enhancement. Production callers (F6.1's `Principal.tsx`) MUST invoke a real `qrcode`-library rasterizer and overwrite the ABIERTO-01 sentinel before passing to `escposBuilder.build`. Byte-presence tests assert via `Buffer.indexOf(dataUrl) >= 0`. The deviation is bounded to the print byte stream — the **payload contract** still satisfies the design (caller-supplied string, no implicit rasterizer).

## Cross-coupling boundary (F6.2)

F6.2 EXTENDS F5.2's `escposTemplates.ts`, `escposBuilder.ts` (consumed unchanged), and `fallbackBrowser.ts` — never duplicates. F6.2 produces bytes consumed by F5.1's `bridge.imprimir({ buffer })`. F6.2 does NOT call the engine, the USB, the electron-store, the `documentos` ER, or the backend. F6.1's `Principal.tsx` is the wiring site — F6.2 only writes the **integration contract** at `apps/electron-sucursal/src/features/operacion/docs/ingreso-tiquete-integration.md` (1-page wire contract: F6.1 onSuccess → `buildEntradaPayload(...)` → `escposBuilder.build('entrada', payload)` → `bridge.imprimir({ buffer })` → A-05 backend hook payload shape). The F6.1 PR will install the actual `Principal.tsx` `onSuccess` handler in its own cycle. **`modelo_datos_er.mmd` untouched.** No physical DELETE attempted at any layer (audit-first canon — F6.2 only reads `ingreso`, `sucursal`, `documentos`, `usuarios` for payload assembly).

## Constraints (F6.2)

(1) `TiqueteEntradaPayload` MUST be `readonly` on every key — no mutation after build. (2) The builder MUST NOT add fields beyond the 17 (Mensualidad tag is a conditional line, not a 18th key). (3) `qrDataUrl` and `logoDataUrl` MUST be base64 strings (`data:image/...;base64,...`) or empty strings — the builder never rasterizes (F5.2 R4 purity). (4) ISO date strings MUST be formatted via `Intl.DateTimeFormat('es-CO', {dateStyle:'short', timeStyle:'short'})` from caller-supplied ISO strings per F5.2 R4 — no implicit `new Date()`. (5) No `modelo_datos_er.mmd` change. (6) No physical DELETE attempted at any layer (audit-first canon). (7) No `Co-Authored-By` AI trailer in commits (authored as `Parkos Dev <dev@parkos.local>` per AGENTS.md git identity rule).

## Out of Scope (F6.2)

CU-15S (salida) / CU-15SM (salida-mensualidad) — F7.x per plan, reuses the `TiqueteEntradaCampos` mapped type pattern for `TiqueteSalidaCampos` + `TiqueteSalidaMensualidadCampos`. Backend `log_transaccional` INSERT endpoint — separate HU. PDF generation. Email/SMS delivery of the tiquete. Auto-discovery of `documentos` cache (future enhancement; caller-side `electron-store` key `parkos.documents.v1` with TTL 24 h is documented in `ingreso-tiquete-integration.md`). `formatCOP` consolidation with F2.x (F5.2 carries the warning forward; F6.2 inherits).

## References (F6.2)

`plan.md` lines 1606-1653 (HU-F6.2 contract, 17 fields verbatim); lines 412-492 (DEC-SUC-08 thermal printing, DEC-SUC-26 QR+logo, DEC-SUC-27 orden impresión, ABIERTO-01 QR content); lines 446-462 (A-01 póliza RC, A-05 estado de impresión); `modelo_datos_er.mmd` (`ingreso [L-E]`, `sucursal`, `documentos [V]`, `usuarios` — read-only); `openspec/specs/impresion.md` canonical (F5.1 + F5.2 + F6.2 merged); F5.2 archive-report (`EntradaPayload` declared, F5.2 R3 purity contract); F5.1 archive-report (`bridge.imprimir` contract + B-prime scoped tsc precedent); `apps/electron-sucursal/src/features/operacion/docs/ingreso-tiquete-integration.md` (F6.2 NEW wire contract document).
