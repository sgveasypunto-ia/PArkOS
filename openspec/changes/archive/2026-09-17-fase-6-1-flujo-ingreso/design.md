# Design: Fase 6.1 — Flujo de ingreso vehicular (CU-01 + CU-15E)

> **Change**: `fase-6-1-flujo-ingreso`
> **Phase**: design (sdd-design)
> **Inputs read**: `proposal.md` §Approach §Dependencies; `specs/operacion-ingreso.md` §ADDED Requirements §Error Catalog §Open question; `modelo_datos_er.mmd` lines 577-596 (`ingreso` table + bi-temporal); `plan.md` lines 1496-1604 (F6.1 + sequence mermaid) + 412-492 (DEC-SUC-* + A-04); `apps/electron-sucursal/src/lib/validation/placa.ts` (F4.1 strict detector — `detectarTipoVehiculo(placa): 'Auto'|'Moto'|null`); `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (F6.2 — `EntradaPayload` + `buildEntradaPayload()`); `apps/electron-sucursal/src/features/operacion/docs/ingreso-tiquete-integration.md` (F6.2 contract); existing `useOcupacion` + `ocupacionApi` (F4.3 archived hooks); `apps/ui-kit/src/fetch/parkosFetch.ts` (DEC-FETCH-02..05).

## Technical Approach

RHF + Zod at the form boundary; SWR for the read of `/operacion/ingresos?placa=X`; `parkosFetch` POST with `Idempotency-Key = SHA-256('POST:/operacion/ingresos:' + canonicalJSON(body))` per DEC-SUC-04; on `201` the success handler runs the F6.2 call chain (`buildEntradaPayload()` → `escposBuilder.build('entrada', payload)` → `bridge.imprimir({ buffer: base64, ticketId })`); `TiqueteModal` (shadcn Dialog, `role="dialog"`) shows success + always-on "Imprimir" (E3 exemption); `ForzarIngresoModal` is independent, Zod `min(10)` motivo, payload prepended with `[FORZADO: <motivo>]`. Path 1 client-side filter resolves the missing `GET /operacion/ingresos?placa=X&activo=true` endpoint with zero backend change.

## Architecture Decisions

### Decision: Path 1 — composition with existing endpoint

**Choice**: `GET /operacion/ingresos?placa=X` returns 0..N historical rows; `useIngresoActivo` SWR hook filters client-side to **most-recent UUID** and exposes `hasActive`. No backend change in F6.1.
**Alternatives considered**: (1) companion backend PR adding `?activo=true` (~15 LOC: `WHERE NOT EXISTS salidas` + `WHERE NOT EXISTS anulaciones` join in `repo/ingreso.py`); (2) N+1 calls to `/ingresos/{uuid}/estado` per result row.
**Rationale**: zero backend dependency keeps F6.1 a pure renderer change; placa cardinality is typically 0-3 rows so most-recent approximation is MVP-acceptable; the doble-ingreso edge case is operator-handled via `ForzarIngresoModal`. Backend path 2 deferred as a separate companion PR (T0b, ~15 LOC, optional follow-up).

### Decision: Reuse existing `useOcupacion` for inline cupo display

**Choice**: import `useOcupacion(uuid_sucursal)` from `features/operacion/hooks/useOcupacion.ts` (F4.3 hook already shipped, see `OPERACION_REFRESH_INTERVAL_MS` in `constants.ts`) and render a lightweight inline cup strip in `Principal.tsx`. No new SWR key, no second polling.
**Alternatives**: write a fresh inline `useSWR('/operacion/ocupacion?uuid_sucursal=X', ...)` inside `Principal.tsx` (duplicates F4.3 deduping + retries).
**Rationale**: the F4.3 hook is the verified pattern (DEC-SUC-11 verbatim — 10s refresh + 5s deduping); reuse keeps a single SWR key for occupancy across F4.3/F4.4/F6.1/F7.x.

### Decision: Bridge buffer extension (prerequisite)

**Choice**: assume `bridge.imprimir({ buffer: base64, ticketId: string })` becomes available. F6.1 ships a T0a bridge extension (`electron/bridge.d.ts` adds `buffer?: string` to `PrintPayload`; preload handler dispatches to escpos-usb). The `features/operacion/docs/ingreso-tiquete-integration.md` (F6.2 doc, archived) already describes this exact contract.
**Open question**: the current `bridge.d.ts` declares `PrintPayload = { ticketId, lines, cut, cashDrawer? }`. Without T0a, the auto-print path cannot be honored. T0a is a 5-LOC patch to the bridge contract + preload whitelist — treated as a Phase 0 prerequisite and verified before T6.

### Decision: Idempotency-Key body canonicalization

**Choice**: `Idempotency-Key = SHA-256('POST:/operacion/ingresos:' + canonicalJSON(body))` where `canonicalJSON` recurses with sorted-object-keys and primitive stripping. POST + retries (network 5xx via DEC-FETCH-02, operator double-press) carry the same hash → server returns the same `uuid_ingreso`. A small `lib/canonicalJson.ts` module (15 LOC) lives next to `ingresoApi.ts` for unit testing.

### Decision: Decoupled `ENTRADA_PAYLOAD_LOCAL` interface

**Choice**: `Principal.tsx` declares `interface EntradaPayloadLocal = EntradaPayload` re-exported from `lib/print/escposTemplates.ts` while F6.2 may still be in active branch. When F6.2 merges, the import resolves directly. If F6.2 has not merged at apply time, the design ships a local 1:1 mirror that document-straddles; both paths converge in F6.2 merge PR.

## Data Flow

```
Operator types "ABC123" + Enter
    │
    ├─ PlacaInput.normalize() ──► detectarTipoVehiculo('ABC123') → 'Auto'
    │     │
    │     └─ invalid → inline error, no API call  [Zod, client-side]
    │
    └─ useIngresoActivo('ABC123').refetch()
          │
          └─ parkosFetch('/operacion/ingresos?placa=ABC123') ──► Array<Ingreso>
                │
                └─ client filter: latest = arr.sort(by created_at desc)[0]
                      └─ hasActive = latest !== undefined  [Path 1 simplification]

Principal banner re-renders with tipo_entrada = 'ROTACION' (or 'MENSUALIDAD')

Operator clicks "Confirmar"
    │
    └─ postIngreso(placa, motivo?) [parkosFetch w/ Idempotency-Key]
          │
          ├─ 201 + uuid_ingreso ──► Promise.all([logo, certificado])
          │     └─ buildEntradaPayload() ──► escposBuilder.build('entrada', payload): Buffer
          │           └─ bridge.imprimir({ buffer: Buffer.toString('base64'), ticketId })
          │                 ├─ ok:true    → TiqueteModal opens
          │                 └─ printer_offline → banner + F5.1 retry queue
          │
          ├─ 409 ingreso_activo_existente → router.push('SalidaFlow placeholder URL')
          ├─ 422 motivo_forzado_requerido → ForzarIngresoModal opens
          └─ 422 motivo_forzado_insuficiente → inline modal error
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `apps/electron-sucursal/electron/bridge.d.ts` | Modify (T0a) | Add `buffer?: string` to `PrintPayload`; union discriminated by `lines?: PrintLine[] \| buffer?: string` |
| `apps/electron-sucursal/electron/preload.ts` | Modify (T0a) | Whitelist new `imprimir({ buffer, ticketId })` call; route to escpos-usb consumer |
| `apps/electron-sucursal/src/features/operacion/lib/canonicalJson.ts` | Create (T8) | 15-LOC `canonicalJSON(value)` helper + unit tests |
| `apps/electron-sucursal/src/features/operacion/api/ingresoActivoApi.ts` | Create (T1) | `parkosFetch('/operacion/ingresos?placa=X')` returning `Ingreso[]` |
| `apps/electron-sucursal/src/features/operacion/hooks/useIngresoActivo.ts` | Create (T2) | SWR hook: `{ hasActive, latestIngreso, isLoading, error }` |
| `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts` | Create (T3) | `postIngreso(payload)` with canonical Idempotency-Key |
| `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.test.ts` | Create (T3) | Idempotency-Key derivation tests (3 scenarios from spec) |
| `apps/electron-sucursal/src/features/operacion/components/PlacaInput.tsx` | Create (T4) | RHF+Zod (`REGEX_AUTO\|REGEX_MOTO`), auto-focus via `useRef`, Enter-submit, Zod regex via F4.1 detector |
| `apps/electron-sucursal/src/features/operacion/components/ForzarIngresoModal.tsx` | Create (T5) | shadcn Dialog; `motivoSchema = z.string().min(10)`; payload `[FORZADO: <motivo>]` |
| `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx` | Create (T6) | shadcn Dialog (`role="dialog"`); Imprimir + Siguiente buttons |
| `apps/electron-sucursal/src/features/operacion/pages/Principal.tsx` | Create (T7) | Page container; orchestrates banner + active-check + auto-print + redirect |
| `apps/electron-sucursal/src/features/operacion/pages/Principal.test.tsx` | Create (T7) | RTL render + smoke |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Modify (T8) | Add 8 keys; reuse existing `placa_formato_invalido`, `ingreso_registrado_exitoso`, `tiquete_entrada_titulo`, `ingreso_observaciones_forzado` |
| `apps/electron-sucursal/e2e/operacion/ingreso.spec.ts` | Create (T9) | 5 e2e scenarios (rotación, mensualidad, redirect, forzado, fallback térmico) + 1 redirect test |

## Interfaces / Contracts

```ts
// hooks/useIngresoActivo.ts
export interface Ingreso {
  uuid: string;
  uuid_sucursal: string;
  placa: string;
  fecha_ingreso: string;
  uuid_subscripcion_cliente: string | null;
  tipo_entrada: 'MENSUALIDAD' | 'ROTACION'; // server-derived, never persisted client-side
}

export interface IngresoActivoState {
  hasActive: boolean;
  latestIngreso: Ingreso | null;
  isLoading: boolean;
  error: Error | undefined;
}

export function useIngresoActivo(placa: string | null): IngresoActivoState;

// lib/ingresoApi.ts
export interface PostIngresoPayload { placa: string; uuid_tipo_vehiculo: string; observaciones?: string; forzado?: boolean; }
export interface PostIngresoResponse { uuid_ingreso: string; tipo_entrada: 'MENSUALIDAD' | 'ROTACION'; uuid_subscripcion_cliente: string | null; }
export async function postIngreso(payload: PostIngresoPayload): Promise<PostIngresoResponse>;

// bridge extension
export interface PrintPayload {
  ticketId: string;
  lines?: PrintLine[];     // existing — kept for legacy consumers
  buffer?: string;          // F6.1 — base64-encoded escpos bytes
  cut?: boolean;
  cashDrawer?: boolean;
}
```

## Testing Strategy

| Layer | What | How |
|-------|------|-----|
| Unit | `useIngresoActivo` SWR shape (mock `parkosFetch`), `getKey` for null placa, error propagation | `vitest run src/features/operacion/hooks/useIngresoActivo.test.ts` (RTL + MSW) |
| Unit | `postIngreso` Idempotency-Key derivation (3 scenarios from spec) | `vitest run src/features/operacion/lib/ingresoApi.test.ts` |
| Unit | `canonicalJSON` sorted-key stability | `vitest run src/features/operacion/lib/canonicalJson.test.ts` |
| Unit | `PlacaInput` auto-focus + uppercase + Enter-submit | RTL render with `fireEvent.submit` |
| E2E | 5 plan.md F6.1 scenarios + 1 transparent redirect | `apps/electron-sucursal/e2e/operacion/ingreso.spec.ts` (Playwright + axe-core) |
| A11y | axe-core WCAG 2.1 AA snapshot mode on `Principal.tsx` + 2 modals | per e2e spec |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The escpos/escpos-usb layer is F5.1/F6.2's domain; F6.1 only invokes it through the typed bridge contract.

## Migration / Rollout

No migration required. Renderer-only change. Revert the PR; INSERTed `ingreso` rows persisted during the rolled-back window remain in the DB (insert-only per ER canon). Operators must correct via `anulaciones` workflow (Fase 7) — out of F6.1 scope. The new `src/features/operacion/{pages,components,hooks,api,lib}/` additions and `electron/bridge.d.ts` + `electron/preload.ts` modifications are fully removable in one revert commit.

## Open Questions

- [ ] **bridge.d.ts buffer field** (T0a) — verify F5.1 owner OK with extending `PrintPayload` to accept `buffer: base64`; the F6.2 integration doc (archived) implies this contract. If F5.1 owner rejects the buffer shape, F6.1 builds `PrintPayload.lines: PrintLine[]` client-side (different design — escalate before apply).
- [ ] **F6.2 merge timing** (T8 mirror) — if F6.2 has not merged when F6.1 apply starts, mirror `EntradaPayload` shape inline in `lib/print/escposTemplates.ts` mirror file. Synchronize on F6.2 merge PR.
- [ ] **Path 1 false-negative** — client "most-recent" approximation may miss the case where the latest ingreso was already exited; operator catches via `ForzarIngresoModal` or `SalidaFlow`. Backend `?activo=true` companion PR (T0b) recommended.
