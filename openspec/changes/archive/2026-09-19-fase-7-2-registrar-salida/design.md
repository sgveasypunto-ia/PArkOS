# Design: HU-F7.2 — Registrar salida (rotación + mensualidad) — UI integration

> **Change**: `fase-7-2-registrar-salida` | **Phase**: sdd-design | **Forecast**: ~410 LOC | **Budget**: <800
> **Base**: `openspec/changes/fase-7-2-registrar-salida/{proposal.md,specs/operacion.md}` + `openspec/specs/operations/spec.md` (REQ-OPS-042..052)
> **Drift anchor**: F1.7 DEC-MONO-01 — ONE endpoint `POST /operacion/salidas`; server-side `tipo_salida` derivation. F7.2 honors the merged reality (R-DRIFT).

## 1. Technical Approach

F7.2 wires F7.1's `<CotizacionPanel onConfirmar />` callback to F1.7's canonical `POST /api/v1/operacion/salidas` (REQ-OPS-042..052, already shipped on `dev`). A new `useRegistrarSalida()` SWR mutation hook composes `parkosFetch` + `useAuthStore` + a pure `buildIdempotencyKey` helper that hashes `method|path|canonicalJSON(body)` via Web Crypto SHA-256 (DEC-SUC-04 + DEC-IDEM-01 reuse from F1.6). The hook returns `SalidaReadForzado` discriminated on `tipo_salida`: `ROTACION` routes to `useDashboardDrawerStore.open('pago', pagoAnchorId)` (REQ-OPS-138 invariant); `MENSUALIDAD` fires the typed `bridge.imprimir('salida_mensualidad', payload)` event envelope (F7.3 owns payload shape + `escposBuilder`). DEC-SUC-23 verbatim: F7.2 is INSERT-only at `prod.salidas`; the `estado='PAGADO'` UPDATE is F8.1 territory.

## 2. Architecture Decisions

| # | Choice | Alternatives | Rationale |
|---|---|---|---|
| D1 | `useSWRMutation` for `useRegistrarSalida` | raw `fetch` + `useState`; thin wrapper around `parkosFetch` | SWR first-class mutation hook exposes `{ trigger, isMutating, error, data }`; reuses `parkosFetch` auth/retry/error pipeline; `isMutating` enables UI in-flight disable (REQ-OPS-152). Mirrors `useCotizacion.ts:170` `mutate()` precedent. |
| D2 | `SalidaFlow`/`SalidaMensualidad` inline composition in `SalidaPanel`, not a route page | separate `/salida/:uuid` route; new sheet | F7.1 R2 precedent at `SalidaPanel.tsx:179-191`: `<CotizacionPanel onConfirmar={fn} />` is the composition point. Adding a route breaks the F7.1 inline UX and bypasses `<SalidaSheet />`. |
| D3 | `Idempotency-Key` via `canonicalJson.ts` + SHA-256 (RFC 8785) | hash of `JSON.stringify(body)`; UUID v4 per request | RFC 8785 canonical form guarantees property-order independence. Mirrors `ingresoApi.ts:66-76` `deriveIdempotencyKey` precedent verbatim. |
| D4 | F7.2 INSERT-only; F8.1 owns the `salidas.estado='PAGADO'` UPDATE | F7.2 owns both INSERT + UPDATE | DEC-SUC-23: `salidas` has NO `valor` column; the `estado='PAGADO'` flip requires F8.1 pago data. Splitting phases keeps blast radius tight (R1). |
| D5 | 6 atomic REQ-OPS-152..157 (not split per endpoint) | 6 reqs split rotación / mensualidad / shared | DEC-MONO-01 collapsed 2 endpoints into 1; specs MUST mirror the runtime (R-DRIFT). Splitting would re-introduce the drift at the spec layer. |
| D6 | Single `POST /operacion/salidas` endpoint (no `…/mensualidad`) | add a new endpoint per `plan.md` text | F1.7 DEC-MONO-01 + 0 grep matches for `salidas/mensualidad` in `backend/`. AST drift guard (REQ-OPS-155) blocks future regression. |

## 3. Data Flow

```
operator click "Confirmar"
   │
   ▼
SalidaPanel.onConfirmar (rotation|mensualidad branch)
   │  uuid_ingreso, uuid_cotizacion_ref?
   ▼
useRegistrarSalida().trigger({uuid_ingreso})
   │  const key = buildIdempotencyKey({
   │     method:'POST', path:'/api/v1/operacion/salidas',
   │     body })
   │     // SHA-256 hex of canonicalJson(body)
   ▼
parkosFetch POST /api/v1/operacion/salidas
   │   Idempotency-Key: <hex>
   │   Body: {uuid_ingreso, uuid_cotizacion_ref?}
   ▼
F1.7 handler (operacion.py:322)
   │   V1..V5 validations + INSERT prod.salidas
   │   server-side tipo_salida derivation (DEC-MONO-01)
   ▼
201 SalidaReadForzado {uuid_salida, tipo_salida, estado}
   │
   ├─ tipo_salida='ROTACION'    → open('pago', pagoAnchorId)            (REQ-OPS-138)
   └─ tipo_salida='MENSUALIDAD' → bridge.imprimir('salida_mensualidad',payload) (F7.3 owner)
   │
   ▼
onConfirmado(uuid_salida) callback
```

## 4. File Changes

| File | Action | LOC | Notes |
|---|---|---|---|
| `apps/electron-sucursal/src/features/operacion/hooks/useRegistrarSalida.ts` | NEW | 70 | SWR mutation hook; calls `parkosFetch` with `Idempotency-Key`; auto-detects `modo` from input; 401 → `useAuthStore.clear()` + `parkos:auth:cleared` (mirrors `useCotizacion.ts:155-159`). |
| `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` | NEW | 25 | `buildIdempotencyKey({method,path,body})` pure fn; SHA-256 hex via Web Crypto. |
| `apps/electron-sucursal/src/features/operacion/api/salidaApi.ts` | NEW | 40 | Zod mirror of `SalidaCreateForzado`/`SalidaReadForzado`; composes `parkosFetch`. |
| `apps/electron-sucursal/src/features/operacion/pages/SalidaFlow.tsx` | NEW | 90 | Composition layer (rotation branch) — NOT a visual component; wires `<CotizacionPanel onConfirmar>` to hook + drawer. |
| `apps/electron-sucursal/src/features/operacion/pages/SalidaMensualidad.tsx` | NEW | 50 | 1-screen page; mensualidad branch; fires print envelope post-201. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` | UPDATE | +20 | Replace `handleOpenPago` (lines 115-117) with `handleRegistrarSalida` + post-201 routing by `response.tipo_salida`. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaSheet.tsx` | UPDATE | +5 | Pass `uuid_ingreso` from `useDashboardDrawerStore`. |
| `apps/electron-sucursal/e2e/salida.spec.ts` | NEW | 100 | 3 scenarios per `plan.md:1729`: rotation, mensualidad, doble-click idempotente. |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | UPDATE | +6 keys | es-CO strings: `salida.confirmar_rotacion`, `salida.confirmar_mensualidad`, `salida.errors.salida_duplicada`, `salida.errors.network`, `salida.errors.cotizacion_expirada`, `salida.success.uuid`. |
| **Total** | | **~400** | Under 800 LOC budget; no `size:exception` needed. |

## 5. Interfaces / Contracts

```ts
// Backend response — SalidaReadForzado (F1.7 schemas/operacion.py:392-422)
export const SalidaReadForzadoSchema = z.object({
  uuid_salida: z.string().uuid(),
  uuid_ingreso: z.string().uuid(),
  tipo_salida: z.enum(['ROTACION', 'MENSUALIDAD']), // server-derived (DEC-SUC-21)
  estado: z.enum(['PENDIENTE_PAGO', 'MENSUALIDAD_PAGO']), // F8.1 flips to 'PAGADO'
  uuid_sucursal: z.string().uuid(),
  uuid_usuario: z.string().uuid(),
  created_at: z.string(), // ISO-8601
});
export type SalidaReadForzado = z.infer<typeof SalidaReadForzadoSchema>;

// Mutation input
export interface RegistrarSalidaInput {
  uuid_ingreso: string;
  uuid_cotizacion_ref?: string; // optional; from useCotizacion
}

// Hook signature — useSWRMutation (mutation-only, no polling)
export function useRegistrarSalida(): {
  trigger: (input: RegistrarSalidaInput) => Promise<SalidaReadForzado>;
  isMutating: boolean;
  error: ParkosHttpError | SalidaDuplicadaError | undefined;
  data: SalidaReadForzado | undefined;
};

// Pure helper — sync, side-effect free, called from inside trigger()
export function buildIdempotencyKey(args: {
  method: string;       // e.g. 'POST'
  path: string;         // e.g. '/api/v1/operacion/salidas'
  body: unknown;        // canonicalized via canonicalJSON (RFC 8785)
}): string;
// Returns: SHA-256 hex of '<METHOD>|<path>|<canonicalJSON(body)>'
// Reuses canonicalJSON from ./canonicalJson (F7.1 shipped, RFC 8785)

// 409 typed error (partial unique index `one_exit_per_ingreso` violation, migration 0026)
export class SalidaDuplicadaError extends Error {
  readonly status = 409;
  constructor(public readonly uuid_salida_existente: string) {
    super('salida_duplicada');
  }
}
```

## 6. Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | `buildIdempotencyKey` property-order independence (RFC 8785) | 4 vitest cases — same body shuffled keys → same hex; nested objects; array order preserved; primitives pass-through |
| Unit | `useRegistrarSalida` 4 scenarios | 4 vitest + MSW: rotación 201 (`tipo_salida='ROTACION'`, `estado='PENDIENTE_PAGO'`); mensualidad 201 (`tipo_salida='MENSUALIDAD'`, `estado='MENSUALIDAD_PAGO'`); 409 → `SalidaDuplicadaError`; 401 → `useAuthStore.clear()` + `parkos:auth:cleared` |
| Unit | `salidaApi.ts` Zod parse + DEC-SUC-21 guard | 3 vitest: canonical `SalidaReadForzado` accepted; input rejects injected `tipo_salida`; discriminated-union narrows |
| E2E | rotación confirm → 201 → PagoModal drawer opens | Playwright `e2e/salida.spec.ts` S1 |
| E2E | mensualidad confirm → 201 → print envelope fired | Playwright S2 with `bridge.imprimir` spy |
| E2E | doble-click in <500ms → 1 row in `prod.salidas` | Playwright S3 with server-side dedup verification (cached 201) |

## 7. Threat Matrix

N/A — renderer-only change. No routing, no shell, no subprocess, no VCS/PR automation, no executable-file classification, no process-integration boundary. F7.2 composes existing infrastructure: `parkosFetch` (F2.2), `useAuthStore` (F3.1), `useDashboardDrawerStore` (REQ-OPS-138), `IdempotencyKeyMiddleware` (F1.6 PR2). Backend zero-changes.

## 8. Migration / Rollout

None required. F7.2 ships ZERO backend changes; F1.7 already ships `POST /operacion/salidas` + `SalidaReadForzado` on `dev`. `useRegistrarSalida` is the sole caller — no migration, no feature flag, no phased rollout. Post-merge: Vite cache invalidation per AGENTS.md (`--force`); delete `feature/hu-f7-2-registrar-salida` branch after merge to `dev`.

## 9. Open Questions

None. Both ODs (OD-1 inspection-in-consumer; OD-2 `useSWRMutation`) are ratified in proposal §7. Drift reconciliation (DEC-MONO-01 vs `plan.md`) is captured in proposal §3.4 + REQ-OPS-152/REQ-OPS-155.

## 10. Review Workload Forecast

**LOC**: ~410 (forecast) | **Budget**: 800 LOC per PR (AGENTS.md)
**Decision needed before apply**: No
**Chained PRs recommended**: No
**400-line budget risk**: Low