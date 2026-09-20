# Design: HU-F8.3 — Reimpresión de tiquete con costo (FE)

> **Change**: `fase-8-3-reimpresion-tiquete-costo`
> **Phase**: design (sdd-design)
> **Branch**: `feature/hu-f8-3-reimpresion-tiquete-costo` off `dev` at `3d0e2e8`
> **Forecast**: ~325 LOC · 400-line budget risk: **Low** · Chained PRs: **No** (`size:exception` not needed)

---

## 1. Technical Approach

F8.3 ships the renderer half of the reimpresión con costo flow on top of F1.11's merged backend (`POST /api/v1/workflows/reimpresion-ticket` + `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular`). The page mounts at `/facturacion/reimprimir` (mirrors F8.2 `FacturaDetalle` page pattern), validates `motivo: z.string().min(10)` client-side via RHF + Zod, then fires `useReimprimir` (SWR mutation + Idempotency-Key SHA-256 + 401 → `useAuthStore.clear()`). The escposBuilder reimpresion case is tightened with `0x1B 0x45`/`0x1B 0x46` (bold on/off) wrapping the inner body — the `*** REIMPRESION ***` sello (F1.11/F7.3) is upgraded to `*** REIMPRESIÓN ***` (with accent) per `plan.md:2006` verbatim. Two new mutation hooks (`useReimprimir`, `useAnularReimpresion`) reuse the F7.2 `buildIdempotencyKey` + F8.1 `useRegistrarPago` SWR mutation pattern. The `useAnularReimpresion` hook preserves the F1.11 `[L-W]` insert-only invariant by POSTing (never UPDATE).

## 2. Architecture Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Page vs drawer for reimpresion | **Page** at `/facturacion/reimprimir` | Long-running 4-step wizard (placa → motivo → alertdialog → success card) too cramped for drawer; mirrors F8.2 `FacturaDetalle` page pattern; success card requires URL-addressable back-navigation |
| D2 | escposBuilder dispatcher key | **`'reimpresion'`** (NOT `'reimprimir'`) | F1.11 + F7.3 already use `'reimpresion'`; `plan.md:2006` is a corpus typo. Drift anchor REQ-OPS-175 enforces |
| D3 | Hook composition | **SWR mutation + Idempotency-Key** (mirror F8.1 `useRegistrarPago`) | F3.1 401 invariant preserved; doble-click dedup via F7.2 SHA-256 closure |
| D4 | Anulación chain | **INSERT new row** (F1.11 DEC-TKT-03 `[L-W]` invariant) | Mirrors F1.11 backend contract; `uuid_reimpresion_padre` FK chain reconstructs history |
| D5 | Sello accent | **`*** REIMPRESIÓN ***`** (with accent) | `plan.md:2006` verbatim copy; semantic distinction vs original tiquete |

## 3. Data Flow

```
Operator (placa search)
        │
        ▼
  <ReimprimirTiquete />  (page, role="alertdialog")
        │  Zod: motivo.min(10)
        ▼
  useReimprimir().trigger({uuid_ingreso, motivo, tipo})
        │  buildIdempotencyKey(SHA-256)
        ▼
  POST /api/v1/workflows/reimpresion-ticket/{uuid_ingreso}/reimprimir
  body: {motivo, tipo}
  header: Idempotency-Key: <hex>
        │
        ▼
  201 → ReimpresionTicketRead{uuid_reimpresion, uuid_factura?, estado: 'autorizada'}
        │
        ├─► success card renders uuid_reimpresion + motivo
        └─► queueMicrotask(() => bridge.imprimir('reimpresion', payload))

  ──────── ANULAR FLOW ────────

  Operator clicks "Anular" → alertdialog confirms motivo_anulacion.min(10)
        │
        ▼
  useAnularReimpresion().trigger({uuid_reimpresion, motivo_anulacion})
        │  buildIdempotencyKey(SHA-256)
        ▼
  POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular
  body: {motivo_anulacion}
        │
        ▼
  201 → new row INSERTed with uuid_reimpresion_padre=<original>
  (NEVER UPDATE on original — F1.11 DEC-TKT-03 invariant)
```

## 4. File Changes

| File | Action | LOC | Description |
|---|---|---|---|
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | UPDATE | +10 | Wrap `buildReimpresionBody` inner body with `escBoldOn()`/`escBoldOff()`; sello `'*** REIMPRESIÓN ***'` + subline `'--- COPIA AUTORIZADA ---'` |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.reimpresion.test.ts` | NEW | 60 | 3 byte-presence tests (REQ-OPS-172) |
| `apps/electron-sucursal/src/features/facturacion/api/reimpresionApi.ts` | NEW | 40 | Zod mirror of F1.11 `ReimpresionTicketRead` + `ReimpresionTicketCreateEndpoint` + `ReimpresionTicketAnular` shapes |
| `apps/electron-sucursal/src/features/facturacion/hooks/useReimprimir.ts` | NEW | 50 | SWR mutation hook (REQ-OPS-173) |
| `apps/electron-sucursal/src/features/facturacion/hooks/useReimprimir.test.ts` | NEW | 60 | 3 hook tests |
| `apps/electron-sucursal/src/features/facturacion/hooks/useAnularReimpresion.ts` | NEW | 50 | SWR mutation hook (REQ-OPS-174) INSERT-only |
| `apps/electron-sucursal/src/features/facturacion/hooks/useAnularReimpresion.test.ts` | NEW | 40 | 2 hook tests |
| `apps/electron-sucursal/src/features/facturacion/pages/ReimprimirTiquete.tsx` | NEW | 100 | Page with placa search + motivo textarea + alertdialog + success card anular (REQ-OPS-171) |
| `apps/electron-sucursal/src/features/facturacion/pages/ReimprimirTiquete.test.tsx` | NEW | 80 | 5 component tests |
| `apps/electron-sucursal/src/renderer/App.tsx` | UPDATE | +8 | Add `/facturacion/reimprimir` route under `<ProtectedRoute>` (mirror F8.2 line 65-72) |
| `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` | UPDATE | +13 | Extend `reimprimir.*` keys (tipo/alertdialog/errors/success/anular/placa) |
| `apps/electron-sucursal/e2e/reimpresion.spec.ts` | NEW | 50 | 3 Playwright scenarios |
| **Total** | | **~561** | Under 800 budget |

## 5. Interfaces / Contracts

```typescript
// reimpresionApi.ts — Zod mirror of F1.11
export const ReimpresionTicketCreateSchema = z.object({
  motivo: z.string().min(10),
  tipo: z.enum(['entrada', 'salida']),
});
export type ReimpresionTicketCreate = z.infer<typeof ReimpresionTicketCreateSchema>;

export const ReimpresionTicketReadSchema = z.object({
  uuid: z.string().uuid(),
  workflow_estado: z.literal('autorizada'),
  uuid_reimpresion_padre: z.string().uuid().nullable(),
  uuid_ingreso: z.string().uuid(),
  uuid_factura: z.string().uuid().nullable(),
  motivo: z.string(),
  created_at: z.string(),
});
export type ReimpresionTicketRead = z.infer<typeof ReimpresionTicketReadSchema>;

export const ReimpresionTicketAnularSchema = z.object({
  motivo_anulacion: z.string().min(10),
});

// useReimprimir.ts
export interface UseReimprimirReturn {
  trigger: (input: { uuidIngreso: string; motivo: string; tipo: 'entrada' | 'salida' }) => Promise<ReimpresionTicketRead>;
  isMutating: boolean;
  error: ParkosHttpError | undefined;
  data: ReimpresionTicketRead | undefined;
}

// useAnularReimpresion.ts
export interface UseAnularReimpresionReturn {
  trigger: (input: { uuidReimpresion: string; motivoAnulacion: string }) => Promise<ReimpresionTicketRead>;
  isMutating: boolean;
  error: ParkosHttpError | undefined;
  data: ReimpresionTicketRead | undefined;
}
```

## 6. Testing Strategy

| Layer | What to Test | Approach | Count |
|---|---|---|---|
| Unit | `escposBuilder.build('reimpresion')` bold marca + sello + subline | Byte-level `Buffer.indexOf()` assertions | 3 |
| Unit | `useReimprimir` hook (201 + motivo Zod + 401) | Vitest + renderHook + `parkosFetch` mock | 3 |
| Unit | `useAnularReimpresion` hook (INSERT-only + motivo_anulacion Zod) | Vitest + renderHook + mock | 2 |
| Unit | `<ReimprimirTiquete />` (placa → motivo → alertdialog → success → anular) | RTL + axe-core | 5 |
| E2E | Reimpresion spec (entrada + salida + motivo corto blocked) | Playwright + axe-core | 3 |
| **Total** | | | **16** |

## 7. Threat Matrix

`N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The escposBuilder change is pure renderer-side byte composition (F5.2 R4 purity contract preserved). Hooks reuse F8.1 + F7.2 pattern mirrors (no new auth/transport code).`

## 8. Migration

None. F1.11 backend is already merged (MIGRATION 0029 Op 1 + 2 + 3 shipped). F8.3 reads only.

## 9. Open Questions

- **OD-1 (RATIFIED)**: Single page with `tipo: 'entrada' | 'salida'` selector vs split pages — single page ratified per `plan.md:2005` (`pages/ReimprimirTiquete.tsx`) and F7.3 precedent (single `'salida' | 'salida-mensualidad'` discriminator in the same builder). No block on implementation.

## 10. Review Workload Forecast

325 LOC under 800 → **Low risk**, **no `size:exception`**, **single PR topology** (commits 1-5 per work-unit-commits skill, each independently revertible).

---

**End of design — HU-F8.3.**
