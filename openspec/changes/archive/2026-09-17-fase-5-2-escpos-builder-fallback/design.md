# Design: HU-F5.2 — `escposBuilder` base y fallback de navegador

## Technical Approach

Three pure modules in `apps/electron-sucursal/src/lib/print/`. The composition is **deterministic byte assembly** with no I/O, no DOM access (except in the explicitly DOM-bound `fallbackBrowser`), and no dependencies on F5.1 hardware/IPC surfaces. The contract is: `escposBuilder.build(tipo, payload) → Buffer`; `fallbackBrowser.print(tipo, payload) → void` (DOM-target). A `Buffer` shape (not `Uint8Array`) is required by F5.1's `bridge.imprimir` contract (`payload.buffer` base64 → `escpos-usb` `Device.print(Buffer)`) per `openspec/changes/fase-5-1-printer-service/proposal.md` §Risk 7.

## Architecture Decisions

| Decision | Choice | Alternatives | Rationale |
|---|---|---|---|
| Module layout | 3 TS files in `src/lib/print/` + 2 test files | 1 monolith file; sub-folder per tipo | Per plan:1483, 3 named files (`escposBuilder.ts`, `escposTemplates.ts`, `fallbackBrowser.ts`); keeps the entrypoint (`escposBuilder`) thin and pushes typed payload definitions into a separate spec-like file. |
| Payload validation | `zod` parse, throw named `Error` subclasses | hand-written type guards; yup | zod already in `dependencies` (v3.23.8 line 51 of `package.json`); precedent in F4.3 (`PostOcupacionResponse` schema). Named subclasses (`escpos_invalid_tipo`, `escpos_payload_missing_field`) give callers a stable `instanceof` and `err.code` discriminator. |
| Return type | `Buffer` (node:buffer) | `Uint8Array` | F5.1 expects `Buffer` end-to-end (see `F5.1/proposal.md`); staying `Buffer` avoids re-packing inside `bridge.imprimir`. jsdom + vitest require a polyfill (see Threats). |
| QR + logo in payload | Caller passes `qrDataUrl: string` (base64) and `logoDataUrl: string` (base64); F5.2 embeds them as `GS ( L` raster-bit-image bytes IF the renderer is in a "graphics-capable" mode, ELSE forwards as ISO-8859-1 placeholder and the bridge decides | Serialize raster at build time; embed inline as text only; pre-rasterize in F6.2 | Plan A keeps the build **opaque to graphics**: same byte stream regardless of whether the printer supports raster — the bridge can later transform if needed. Plan B (rasterize at build) introduces a graphics-capability flag that doesn't belong in renderer-side pure lib. **Decision**: forward URL strings, not bytes. |
| `formatCOP` | If F2.x ships before F5.2 apply: import `src/lib/format/formatCOP.ts`. If not: **declare F5.2 inline** with TODO header "SYNCH WITH F2.x — replace with F2.x module when shipped" | Block on F2.x | F5.2 is **architecturally independent** of F2.x; the only shared concern is the `Intl.NumberFormat` rule. Per `AGENTS.md` rule 6 ("SF2 FORBIDS BLOCKERS BETWEEN FASES BY DEFAULT") the inline-with-TODO path is approved; we acknowledge a follow-up PR to drop the inline once F2.x ships. |
| Pure-function validation | `vitest` in `environment: 'jsdom'` (already configured) | Add a new env like 'happy-dom'; node env | Existing config handles Buffer polyfill via `setupFiles`. Avoid touching env config — minimal blast radius per Rule of minimal changes. |
| Date formatting | `Intl.DateTimeFormat('es-CO', ...)` from caller-supplied ISO strings | `new Date().toLocaleString()` (implicit "now") | Spec §Caller-Supplied Timestamps forbids implicit now. |

## Data Flow

```
caller (F6.1/F6.2/F7.3)
  │
  │ const payload: EntradaPayload = { placa, fechaEntrada, qrDataUrl, logoDataUrl, ... };
  │
  ▼
escposBuilder.build('entrada', payload)
  │
  │ 1. validatePayload(tipo, payload)
  │    ├── zodSchema.parse(payload)            ← escposTemplates.ts
  │    │   ↳ throws escpos_payload_missing_field
  │    └── tipo ∈ TIPOS_VALIDOS                 ← escposBuilder.ts
  │        ↳ throws escpos_invalid_tipo
  │
  │ 2. dispatch por tipo
  │    ├── buildEntradaBuffer(payload)           ← escposBuilder.ts
  │    ├── buildSalidaBuffer(payload)
  │    ├── buildSalidaMensualidadBuffer(payload)
  │    └── buildReimpresionBuffer(payload)
  │        each calls shared helpers:
  │        esc_init()  ─[Buffer.from([0x1B,0x40])]─▶ prefix
  │        esc_center()  ─[Buffer.from([0x1B,0x61,0x01])]─▶ center
  │        esc_bold_on()  ─[Buffer.from([0x1B,0x45])]─▶ bold on
  │        esc_text_2x()  ─[Buffer.from([0x1B,0x21,0x30])]─▶ text 2x
  │        cut_partial()  ─[Buffer.from([0x1D,0x56,0x00])]─▶ cut
  │
  ▼
Buffer  ─── Buffer.toString('base64') ───▶ bridge.imprimir({ buffer, ... })
                                                │  (F5.1)
                                                ▼
                                            escpos-usb → printer
```

## File Changes

| File | Action | Description |
|---|---|---|
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | New | TS interfaces (`EntradaPayload`, `SalidaPayload`, `SalidaMensualidadPayload`, `ReimpresionPayload`); zod schemas with required fields per tipo; `formatCOP` (inline-or-import per Risk decision); Zod inferred types re-exported. |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | New | `build(tipo, payload)` (entrypoint, dispatcher); 4 `build*Buffer()` (one per tipo); 6 esc-pos helper functions returning `Buffer`; 2 named error classes. |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | New | `print(tipo, payload)` (DOM-targeted); 4 `render*TiqueteHtml()` mirroring the buffer layout; `injectPageStyle()` adds the `@page { size: 80mm auto; margin: 2mm }` rule; `cleanupPageStyle()` removes it post-`window.print()`. |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` | New | Byte-level fixtures for the 5 ESC/POS opcodes (init/cut/center/bold/2x); uses `Buffer.from()` to assert exact byte sequences. |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.types.test.ts` | New | 4 end-to-end payload→`Buffer` tests (one per tipo); asserts sello bytes, money fields, and required fields. |
| `apps/electron-sucursal/vitest.config.ts` | Modified | Add `'./src/lib/print/__tests__/setup-buffer.ts'` to `setupFiles` (polyfills `Buffer` global from `buffer` package). |
| `apps/electron-sucursal/src/renderer/global.d.ts` | Modified | `declare global { var Buffer: typeof import('buffer').Buffer }` so TS sees the global. |
| `apps/electron-sucursal/src/renderer/test-setup.ts` | Modified (additive, non-breaking) | `import { Buffer } from 'buffer'; (globalThis as { Buffer: typeof Buffer }).Buffer = Buffer;` — applies app-wide; existing F4.x tests continue to pass. |

## Interfaces / Contracts

```ts
// escposTemplates.ts
import { z } from 'zod';

export const entradaPayloadSchema = z.object({
  placa: z.string().regex(/^[A-Z]{3}[0-9]{3}$|^[A-Z]{3}[0-9]{2}[A-Z]$/),
  fechaEntrada: z.string().datetime(),                       // ISO
  qrDataUrl: z.string().url().optional(),                    // base64 data URL
  logoDataUrl: z.string().url().optional(),
  empresa: z.object({ nombre: z.string(), nit: z.string(), direccion: z.string(), regimen: z.string() }),
  operario: z.string(),
  tarifaAplicada: z.number().positive(),
  horarioAtencion: z.string(),
  polizaRC: z.string().optional(),
  folio: z.string().uuid(),
  observaciones: z.string().optional(),
});

export type EntradaPayload = z.infer<typeof entradaPayloadSchema>;
// + SalidaPayload (adds subtotal, iva, total, medio_pago, fechaSalida, tiempoTotal, resolucionFE)
// + SalidaMensualidadPayload (drop money fields; add selloPagoMensualidad: literal(true))
// + ReimpresionPayload (discriminated union: originalTipo + motivo + variant fields)

// escposBuilder.ts
export type TiqueteTipo = 'entrada' | 'salida' | 'salida-mensualidad' | 'reimpresion';

export class EscposInvalidTipoError extends Error {
  readonly code = 'escpos_invalid_tipo' as const;
  constructor(public readonly given: string) { super(`Invalid tiquete tipo: '${given}'`); }
}
export class EscposPayloadMissingFieldError extends Error {
  readonly code = 'escpos_payload_missing_field' as const;
  constructor(public readonly issues: z.ZodIssue[]) { super('Payload failed Zod validation'); }
}

export function build(tipo: TiqueteTipo, payload: unknown): Buffer;
// + buildEntradaBuffer(payload: EntradaPayload): Buffer
// + buildSalidaBuffer(payload: SalidaPayload): Buffer
// + buildSalidaMensualidadBuffer(payload: SalidaMensualidadPayload): Buffer
// + buildReimpresionBuffer(payload: ReimpresionPayload): Buffer

// fallbackBrowser.ts
export function print(tipo: TiqueteTipo, payload: unknown): void;
```

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit — byte helpers | `esc_init`/`esc_center`/`esc_bold_on`/`esc_text_2x`/`cut_partial` produce the exact byte sequences | `escposBuilder.test.ts`: 5 tests, each `expect(buf).toEqual(Buffer.from([0x1B, 0x40]))`. |
| Unit — error classes | `EscposInvalidTipoError` carries `code` and the offending tipo | 1 test: `expect(new EscposInvalidTipoError('foo').code).toBe('escpos_invalid_tipo')`. |
| Unit — Zod fail | Payload missing `placa` throws `EscposPayloadMissingFieldError` with `issues` populated | 1 test: `expect(() => build('entrada', { foo: 1 })).toThrow(EscposPayloadMissingFieldError)`. |
| Unit — end-to-end by tipo | Each `build*(payload)` produces a Buffer containing the required opcodes | `escposBuilder.types.test.ts`: 4 tests (entrada/salida/salida-mensualidad/reimpresion) with `expect(buf.subarray(...)).toEqual(Buffer.from([0x1B, 0x40]))` and `expect(buf.includes(Buffer.from('ABC123'))).toBe(true)`. |
| Unit — purity | `build()` does not call `window.print()` or access `document` | `escposBuilder.test.ts`: `const spy = vi.spyOn(window, 'print'); build(...); expect(spy).toHaveBeenCalledTimes(0)`. |
| Unit — purity 2 | `escposBuilder.ts` imports nothing from `electron`/`escpos-usb`/`node:*` | shell `grep -E "from '(electron|escpos-usb|node:)'" src/lib/print/escposBuilder.ts` exits 1 in CI. |
| Unit — formatCOP inline | `100000` → `$ 100.000` (es-CO) | 1 test against the inline helper. |

### Local verify (no CI gate shipped yet because sdd-init refresh was skipped)

```powershell
cd apps\electron-sucursal
npx vitest run src/lib/print
npx tsc -b
npx eslint src/lib/print --max-warnings 0
```

> **NOTE on Strict TDD**: the orchestrator's preflight flagged `strict_tdd: false` (sdd-init refresh was skipped). The plan above is **RED-then-GREEN-by-coincidence** — tests are written first, then the implementation, but no strict gate enforces the order. Apply is encouraged to honor TDD discipline regardless of the cache.

## Threat Matrix

**N/A** — F5.2 does not route, does not invoke shell, does not spawn subprocesses, does not classify executable files, does not integrate with VCS or PR automation, does not bridge processes. Pure functions + DOM-target utilities only. No applicable rows.

## Migration / Rollout

No data migration. No feature flag. No phased rollout. The library is fully additive — `src/lib/print/` is created from scratch; nothing in the existing app references it.

**Rollout guard**: the F5.1 caller (`bridge.imprimir`) is the only downstream consumer, and it already shipped (F5.1 proposal complete). Once F5.2 ships, F6.x can wire it; until then nothing breaks.

## Open Questions

- **Q1** — Does `formatCOP` from F2.x ship before F5.2 enters apply? Resolution path: F5.2 carries the inline `formatCOP` with `TODO: SYNCH WITH F2.x` until F2.x is merged. **Decision pending apply** (does NOT block proposal/spec/design; only blocks the import-vs-inline choice at apply time).
- **Q2** — Will F5.2 embed QR as raster bytes or pass `qrDataUrl` strings? **Decided** in this design (§Architecture Decisions): pass `qrDataUrl` (string). F5.1's bridge decides whether to rasterize.

## Data Architecture Compliance

- **No DB writes** — F5.2 is renderer-side only; A-05 (`log_transaccional` insert) lives in the caller (F6.x backend).
- **No new tables / columns / ER changes** — backend ER (`modelo_datos_er.mmd`) is canonical and untouched.
- **DEC-SUC-08 fallback honored** — `window.print()` with `@page { size: 80mm auto; margin: 2mm }` declared verbatim.
- **DEC-SUC-26** (QR + logo) — payload schema accepts `qrDataUrl`/`logoDataUrl`.
- **DEC-SUC-27** (orden impresión) — fuera de F5.2; el caller (F6.1 entrada auto, F7.3 salida after pago, salida-mensualidad immediate) decide CUÁNDO llamar `escposBuilder.build(...)`. F5.2 es agnóstico al orden.
