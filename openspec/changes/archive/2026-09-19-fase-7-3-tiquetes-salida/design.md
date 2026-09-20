# Design: HU-F7.3 — Tiquetes de salida (CU-15S) + salida-mensualidad (CU-15SM)

> **Change**: `fase-7-3-tiquetes-salida` · **Phase**: sdd-design · **Forecast**: ~360 LOC < 800 budget

## Technical Approach

F7.3 tightens the F5.2+F6.2 stubs already merged at `d157195`. The 4-tipo
`build(tipo, payload)` dispatcher stays untouched. Work is the body
emission of `buildSalidaBody` (T1) and `buildSalidaMensualidadBody` (T2)
plus the payload schemas (T3) and the `SalidaMensualidad` wiring (I1).
The builder remains pure — no IPC, no DOM, no `new Date()` (F5.2 R4
invariant). SalidaMensualidad does the `bridge.imprimir` call deferred
via `queueMicrotask` to avoid blocking the React render commit
(DEC-SUC-08 + DEC-SUC-27). Backend zero changes.

## Architecture Decisions

| # | Decision | Tradeoff | Verdict |
|---|---|---|---|
| AD-1 | Tighten existing stubs (no new dispatcher cases). The 4-tipo dispatcher already shipped. | Adding new cases would duplicate work and break purity. | **Tighten**. |
| AD-2 | Atomic header swap across all 3 payloads (`entrada`, `salida`, `salida-mensualidad`) in the SAME migration step. | Partial swap yields inconsistent brand identity. | **Atomic**. `sucursal.encabezado` added to all 3 schemas; drift guard `grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` returns 0. |
| AD-3 | Sello wrap `escText2x() → literal → escTextReset()` for both `*** SALIDA ***` (CU-15S) and `*** PAGO CON MENSUALIDAD ***` (CU-15SM). | Per-line bold instead would lose the 2x height signal. | **escText2x/escTextReset wrap** (DEC-SUC-27 + `plan.md:1787`). Bytes `0x1B 0x21 0x30` + `0x1B 0x21 0x00`. |
| AD-4 | Print trigger via `queueMicrotask(() => bridge.imprimir(...))` wrapped in try/catch. | Synchronous call blocks render commit; `setTimeout(..., 0)` is slower than microtask. | **`queueMicrotask` + try/catch**. Errors log to `console.warn`; salida is already persisted so failure is non-blocking. |
| AD-5 | Mapped-type exhaustiveness: `TiqueteSalidaCampos` (21 keys = 19 CU-15S + 2 DEC-SUC-26) + `TiqueteSalidaMensualidadCampos` (17 keys = 15 CU-15SM + 2 DEC-SUC-26). Mirror F6.2 `TiqueteEntradaCampos` pattern. | Hand-counted enum risks drift. | **Mapped type** (F6.2 precedent). `tsc --noEmit` fails on rename/remove. |
| AD-6 | Payload schemas tighten `qrDataUrl` + `logoDataUrl` to REQUIRED on `salidaPayloadSchema` (currently `.optional()`). DEC-SUC-26 transversal. | Backward-compat would let callers omit QR/logo. | **Tighten to required**. Empty `logoDataUrl` renders placeholder glyph `▢`. |

## Data Flow

```
SalidaMensualidad.tsx (F7.2)
   │
   ├─ handleConfirmar()
   │     └─ useRegistrarSalida.trigger({ uuid_ingreso })
   │           └─ POST /api/v1/operacion/salidas → 201 { uuid, tipo_salida: 'MENSUALIDAD' }
   │
   ├─ result.tipo_salida === 'MENSUALIDAD'
   │     └─ queueMicrotask(() => {
   │           try {
   │             payload = useSalidaMensualidadPayload(result.uuid)
   │                  ├─ GET /operacion/salidas/:uuid        (F1.7)
   │                  └─ GET /documentos?...&tipo=logo      (F1.7, electron-store cache 24h)
   │             window.bridge.imprimir('salida_mensualidad', payload)
   │                  └─ escposBuilder.build('salida_mensualidad', payload)
   │                        └─ escInit() + buildSalidaMensualidadBody(payload) + cutPartial() + lf()
   │                              └─ Buffer → escpos-usb (F5.1)
   │           } catch (e) { console.warn(...) }      ← non-blocking
   │        })
   ▼
React render commit proceeds, operator UI is responsive
```

## File Changes (~360 LOC)

| File | Action | LOC | Notes |
|---|---|---|---|
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | UPDATE | +90 | Tighten `buildSalidaBody` (T1: tarifa/horario/observaciones + QR + logo + dynamic header) + `buildSalidaMensualidadBody` (T2: sello wrap verified + QR + logo + header) + all 3 bodies header swap (DEC-SUC-28). |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | UPDATE | +40 | Add `sucursal.encabezado` to all 3 schemas; add `tarifaAplicada`/`horarioAtencion`/`observaciones` to `salidaPayloadSchema`; tighten `qrDataUrl`/`logoDataUrl` required on salida. Declare `TiqueteSalidaCampos` (21) + `TiqueteSalidaMensualidadCampos` (17). |
| `apps/electron-sucursal/src/features/operacion/components/SalidaMensualidad.tsx` | UPDATE | +20 | Wire `useSalidaMensualidadPayload`; replace `{ uuid_salida }` envelope with full payload; `queueMicrotask` + try/catch. |
| `apps/electron-sucursal/src/features/operacion/hooks/useSalidaMensualidadPayload.ts` | NEW | 60 | SWR hook composing F1.7 endpoints + electron-store cache `parkos.documents.v1` (F6.2 design). |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` | NEW | 90 | 21 byte-presence scenarios + sello `*** SALIDA ***` + dynamic header. |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida_mensualidad.test.ts` | NEW | 80 | 17 byte-presence scenarios + sello opcode assertion `[0x1b, 0x21, 0x30]` precedes literal, `[0x1b, 0x21, 0x00]` follows. |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | UPDATE | +5 keys | `salida.tiquete_sello`, `salida_mensualidad.tiquete_sello`, `salida.tiquete_qr`, `salida.tiquete_logo_missing`, `salida.errors.sucursal_encabezado_missing`. |

## Interfaces / Contracts

```ts
// escposTemplates.ts — additions to SalidaPayload (CU-15S, 21 fields = 19 + 2)
export interface SalidaPayload {
  // existing 11 keys + dynamic header source (DEC-SUC-28)
  sucursal: { encabezado: string; ... };
  // + tarifaAplicada, horarioAtencion, observaciones
  // + qrDataUrl: REQUIRED, logoDataUrl: REQUIRED (DEC-SUC-26)
}

// CU-15SM, 17 fields = 15 + 2 (mirror)
export interface SalidaMensualidadPayload {
  sucursal: { encabezado: string };
  qrDataUrl: string;   // REQUIRED (DEC-SUC-26)
  logoDataUrl: string; // REQUIRED
  // + 15 conceptual fields per plan.md:1810
}

// escposBuilder.ts — unchanged signatures
export function build('salida' | 'salida-mensualidad', payload: unknown): Buffer;
```

Sello invariant (CU-15SM): `Buffer.indexOf([0x1b, 0x21, 0x30])` followed
by `'*** PAGO CON MENSUALIDAD ***'` then `Buffer.indexOf([0x1b, 0x21, 0x00])`.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (byte) | CU-15S 21-field presence | `Buffer.indexOf(<value>) >= 0` per scenario (mirror `escposBuilder.entrada.test.ts:100+`). |
| Unit (byte) | CU-15SM sello opcode invariant | `[0x1b, 0x21, 0x30]` precedes literal, `[0x1b, 0x21, 0x00]` follows. |
| Unit (byte) | CU-15SM no monetary fields | `indexOf('Subtotal:') === -1`, etc. |
| Component | SalidaMensualidad `bridge.imprimir` invocation | Spy on `window.bridge.imprimir`; assert full payload shape + `queueMicrotask` deferral. |
| Hook | useSalidaMensualidadPayload | SWR cache hit/miss/404 scenarios (4 tests, mirror F6.1 `useIngresoActivo.test.ts`). |
| E2E (optional) | Rotación → mocked F8.1 trigger; mensualidad → immediate envelope | Playwright `salida-tiquete.spec.ts` (deferred to F8.1 PR — F7.3 unit gate is sufficient). |

## Threat Matrix

N/A — renderer-only pure-function tightening + SWR hook. No routing, no
shell, no subprocess, no VCS/PR automation, no executable-file
classification, no process-integration boundary. `bridge.imprimir` is
already F5.1-owned.

## Migration / Rollout

No migration. No backend changes. No DB migration. Single PR to `dev`.

## Open Questions

None. OD-1 + OD-2 ratified by user at proposal time (NO sello
crossover; SÍ logo en CU-15SM).

## Review Workload Forecast

`Decision needed before apply: No` · `Chained PRs recommended: No` · `400-line budget risk: Low` (~360 LOC).
