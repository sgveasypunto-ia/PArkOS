# Design: HU-F6.2 — Tiquete de entrada (CU-15E)

## Technical Approach

F6.2 is a **renderer-side pure** change confined to `apps/electron-sucursal/src/lib/print/` + `renderer/i18n/locales/operacion.json` + `e2e/print.spec.ts` (F6.2-grep slice). It EXTENDS F5.2's `escposTemplates.ts`, `escposBuilder.ts` (no change), `fallbackBrowser.ts`, and reuses F5.2's 9 ESC/POS opcode helpers + 2 named error classes. Composition: caller (F6.1) builds `EntradaPayload` via `buildEntradaPayload(...)` factory → `escposBuilder.build('entrada', payload)` → `Buffer` → `bridge.imprimir({ buffer: Buffer.toString('base64') })` per F5.1's IPC contract. The integration contract is a **documented glue line** (no F6.1 code change in this PR); F6.2 only writes `docs/f6-2-integration.md` so reviewers can grep the call chain end-to-end.

## Architecture Decisions

### Decision: Reuse F5.2's `EntradaPayload` interface verbatim, add only the 2 DEC-SUC-26 fields

**Choice**: F6.2 refines F5.2's `EntradaPayload` to add `qrDataUrl: string` and `logoDataUrl: string` as `readonly` keys (no other changes — the 15 literal fields stay byte-identical to F5.2's declaration per archive-report line 18). The exhaustive `TiqueteEntradaCampos` key set is derived via `keyof EntradaPayload` so the count cannot drift.
**Alternatives considered**: (a) Declare a parallel `TiqueteEntradaPayload` interface — rejected (F5.2 archive-report commits the 17-field spec to ONE interface). (b) Add the 2 fields to F5.2's `EntradaPayload` directly — rejected (out of F6.2 scope; F5.2 is archived; the addition lands as a MODIFIED delta).
**Rationale**: Single source of truth for the tiquete de entrada shape; F7.x (salida) reuses the same pattern. Drift is impossible because F5.2's Zod `entradaPayloadSchema` is the runtime guard.

### Decision: Render-time guard for missing `documentos` row

**Choice**: If `documentos.tipo='logo'` returns no rows (cold cache + ER row absent), the builder emits a placeholder glyph `▢` at the logo position instead of failing the print. The 16 other fields still print; the operator sees the tiquete; the ingreso registration is not blocked.
**Alternatives considered**: (a) Block the print on missing logo — rejected (worse UX, A-05 marks pendiente). (b) Block the ingreso POST on missing logo — rejected (logo is a presentation concern, not a business invariant).
**Rationale**: The tiquete is an operational receipt, not a legal artifact. Per A-01 the póliza RC IS required (text shown on tiquete), but the logo is decorative.

### Decision: QR encoding is the caller's responsibility, builder accepts `qrDataUrl` string

**Choice**: F6.2 declares `qrDataUrl: string` in the payload. The QR rasterizer (a `qrcode` library call at the call site) produces the `data:image/png;base64,...` string. The builder embeds it verbatim. F5.2 R2 constraint honored.
**Alternatives considered**: (a) Builder rasterizes inline — rejected (F5.2 R3 purity: no implicit dependencies, no I/O). (b) Bridge rasterizes — rejected (F5.1 owns bytes, not raster).
**Rationale**: ABIERTO-01 default (`parkos://ingreso/<uuid>?placa=<placa>`) is simple text; the rasterizer is a 5-line caller hook.

## Data Flow

```
                  (F6.1 — Principal.tsx, OUT OF F6.2 SCOPE)
                              │
                              ▼
   POST /operacion/ingresos ─── 200 ───► F6.1 builds EntradaPayload via
                                          buildEntradaPayload(ingreso, sucursal, ...)
                                                │
                                                ▼
                              escposBuilder.build('entrada', payload)   ← F5.2
                                                │
                                                ▼  (Buffer, 17 fields)
                              bridge.imprimir({buffer: bytes.toString('base64')})   ← F5.1
                                                │
                            ┌───────────────────┴───────────────────┐
                            ▼                                       ▼
                       ok:true                              ok:false (printer_offline)
                  (F5.1: emits print_succeeded)         (F5.1: emits print_failed_terminal)
                            │                                       │
                            ▼                                       ▼
                  A-05 hook: backend INSERTs              fallbackBrowser.print('entrada', payload)
                  log_transaccional(accion='impreso',     (F5.2 DOM: 17-field semantic HTML +
                  datos_nuevos={estado:'impresa'})         @page{size:80mm auto;margin:2mm})
                  [DOCUMENTED — separate HU]
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | Modify | Add `qrDataUrl`, `logoDataUrl` to `EntradaPayload`; export `entradaPayloadSchema = entradaBase.refine({...17 keys})`; export `buildEntradaPayload(...)` factory |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | Modify | Extend `renderEntradaTiqueteHtml(payload)` to mirror 17-field layout with `<img src="logoDataUrl">` + QR `<img src="qrDataUrl">` |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` | New | 17 byte-presence scenarios (one per field) + layout composition + Mensualidad tag + missing-key rejection |
| `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` | New | HTML 17-field layout + verbatim `@page` CSS + `window.print` exactly-once |
| `apps/electron-sucursal/e2e/print.spec.ts` | New | Mocked `bridge.imprimir`; F6.2-grep slice only (auto-fire from F6.1 wiring deferred to F6.1's PR) |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Modify | +3 keys: `tiquete_entrada_titulo`, `ingreso_registrado_exitoso`, `ingreso_observaciones_forzado` |
| `openspec/changes/fase-6-2-tiquete-entrada/docs/f6-2-integration.md` | New | 1-page wire contract: F6.1 Principal.tsx → escposBuilder.build → bridge.imprimir → A-05 (doc-only) |

No backend changes. No `modelo_datos_er.mmd` change. No new IPC channel. No new Zod schema beyond the F5.2 base refiner extension.

## Interfaces / Contracts

```typescript
// escposTemplates.ts (extend F5.2)
export interface TiqueteEntradaCampos {
  readonly primero: string;   // Encabezado
  readonly segundo: string;   // Nombre de la empresa
  readonly tercero: string;   // Dirección
  readonly cuarto: string;    // NIT
  readonly quinto: string;    // Régimen
  readonly sexto: string;     // Operario
  readonly septimo: string;   // "TIQUETE DE ENTRADA"
  readonly octavo: string;    // Folio (ingreso.uuid)
  readonly noveno: string;    // Tarifa aplicada
  readonly decimo: string;    // Fecha operación (es-CO short)
  readonly onceavo: string;   // Hora entrada (es-CO short)
  readonly doceavo: string;   // Placa
  readonly treceavo: string;  // Horario atención
  readonly catorceavo: string;// Póliza RC
  readonly quinceavo: string; // Observaciones
  readonly qrDataUrl: string; // DEC-SUC-26 QR (data:image/png;base64,...)
  readonly logoDataUrl: string;// DEC-SUC-26 logo (data:image/png;base64,...)
}

export type TiqueteEntradaPayload = { readonly [K in keyof TiqueteEntradaCampos]: TiqueteEntradaCampos[K] };

export const entradaPayloadSchema = z.object({
  // 15 base fields from F5.2 + 2 DEC-SUC-26 additions
}).refine((p): p is TiqueteEntradaPayload => {
  const keys = Object.keys(TiqueteEntradaCampos);
  return keys.every(k => k in p);
}, { message: 'entrada_payload_missing_field' });
```

The 17-field `TiqueteEntradaCampos` uses Spanish ordinal keys (`primero..quinceavo`) so that the tsc error message on removal is unambiguous (`Property 'tercero' is missing in type 'TiqueteEntradaPayload'`). Names are stable and never drift; the literal CU-15E field NAMES live in `plan.md` (canonical) and the spec file.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit (byte-level) | 17 fields present in the emitted `Buffer` in source order | `escposBuilder.entrada.test.ts` — 17 scenarios using `Buffer.indexOf(campo.toUpperCase())` per field |
| Unit (Zod) | `entradaPayloadSchema.parse` throws `EscposPayloadMissingFieldError` on missing field | Same file, one scenario per field × 17 |
| Unit (mensualidad) | `buildEntradaPayload` emits `MENSUALIDAD` tag when `uuid_subscripcion_cliente IS NOT NULL` | One scenario with mock ingreso |
| Unit (HTML) | `renderEntradaTiqueteHtml` emits 17 `<p>`/`<h1>` tags + `<img>` for QR + logo + verbatim `@page` CSS | `fallbackBrowser.entrada.test.ts` — DOM assertions |
| Unit (fallback) | `fallbackBrowser.print('entrada', payload)` invokes `window.print()` exactly once | `vi.spyOn(window, 'print')` |
| E2E | `bridge.imprimir` is called with `base64` payload + auto-fire from Principal.tsx on 200 | `e2e/print.spec.ts` (F6.2 grep slice) — DEFERRED to CI per sandbox F.6 (F5.1 e2e precedent) |
| tsc | `tsconfig.f6-2-verify.json` extends `tsconfig.json`; includes F6.2 NEW+MODIFIED files only; excludes tests, specs | B-prime scoped tsc per F5.1 archive-report precedent (line 156) |
| eslint | `--max-warnings 0` on F6.2 touched files | Pre-commit |

## Threat Matrix

**N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.** F6.2 is pure renderer composition (F5.2 purity extended). The only I/O surface is the documented F5.1 IPC channel `bridge.imprimir({buffer})` which F6.2 does not modify.

## Migration / Rollout

No migration required. F6.2 ships as a single PR behind no feature flag. The 17-field shape is additive to F5.2's existing `EntradaPayload` — any caller that already passes the 15 literal fields without QR/logo continues to work (the new fields are `readonly string`, empty string is valid). Rollback is a single revert to F5.2's archive head.

## Open Questions

- **None blocking.** Backend `log_transaccional` INSERT endpoint is a separate HU (F6.2 documents only). F5.1 + F5.2 PRs (#3, #4) must merge to `dev` before F6.2 branch creation — orchestrator gates this. QR content ratification is a producto decision (ABIERTO-01 default applies; localized swap if negocio changes its mind).