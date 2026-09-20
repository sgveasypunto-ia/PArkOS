# Design: HU-F8.2 — FacturaDetalle FE status + reintento

> **Change**: `fase-8-2-factura-detalle-fe` | **Phase**: design | **HU**: HU-F8.2 (CU-04 cierre DIAN)
> **Base**: `dev @ 4c969a5` (F8.1 merged) | **Forecast**: ~300 LOC | **No `size:exception`** (under 800 budget)
> **Inputs**: `proposal.md` §1..§13; `specs/operacion.md` REQ-OPS-166..170
> **Drift anchor**: F8.1 `useRegistrarPago.ts:73-101` + F7.2 `useRegistrarSalida.ts:73-101` (SWR mutation + 401/409/Idempotency-Key invariants); F1.10 `prod.envio_dian` retry chain (DEC-FE-02 + REQ-OPS-070 — NEVER UPDATE on `envio_dian`)

## 1. Technical Approach

Renderer-only. Tighten the existing `useFacturaElectronica` SWR hook from constant 30 s polling to a callback `refreshInterval: (latest) => isTerminal(latest?.estado_dian) ? 0 : 30_000` — SWR treats `0` as "do not poll" so both terminal states (`aceptado | rechazado`) halt polling on the same commit the new state lands. Introduce a `useReintentarFE` `useSWRMutation` hook (mirror of `useRegistrarPago` / `useRegistrarSalida`) that POSTs `…/{uuid}/reintentar` with `Idempotency-Key` SHA-256, maps `409 numeracion_agotada` to a typed `NumeracionAgotadaError`, and triggers `mutate('/facturacion/factura-electronica/{uuid}')` on `201` so the cache re-engages 30 s polling when the new chain tip is `pendiente`. Mount a new routed `<FacturaDetalle />` page at `/factura-electronica/:uuid` (inside `<ProtectedRoute>`) that consumes `useFacturaElectronica(uuid)` + `useReintentarFE`, renders localized `estado` (`fe.estado.pendiente|enviado|aceptado|rechazado`), shows CUFE when `aceptado`, exposes a "Reintentar" button ONLY on `rechazado` (disabled while `isMutating`), and surfaces a `role="alert"` banner pointing at the seeded `fe_numbering_exhausted` alerta on `NumeracionAgotadaError`. Wire `<PagoSheet />` to call `navigate('/factura-electronica/<uuid_fe>')` after pago `201` — closes F8.1 §3.5 handoff.

## 2. Architecture Decisions

| # | Decision | Rationale |
|---|---|---|
| AD1 | `refreshInterval` callback form (vs disable + restart) | Single SWR instance; `latestData` is the closure; no race between unmount + remount on reintentar. |
| AD2 | `useSWRMutation` for reintentar (vs inline `parkosFetch`) | Mirrors F7.2/F8.1 invariants: `isMutating` button-disable + Idempotency-Key SHA-256 + 401 clear + 409 typed error. Single source of cache invalidation. |
| AD3 | `<FacturaDetalle />` page wraps existing `<FacturaElectronicaRetryPanel />` (vs replaces) | F8.1 already shipped the panel inside Dashboard; F8.2 lifts it to a route without rewriting presentational logic. No double-fetching (SWR key is shared). |
| AD4 | `typeof` narrow on `result.factura_electronica` in PagoSheet (vs strict Zod schema) | `FacturaReadSchema.factura_electronica: z.unknown()` (ABIERTO-F8.2-01 follow-up). Defensive narrowing avoids forcing a schema change in F8.2. |
| AD5 | `NumeracionAgotadaError` as typed class (vs raw `ParkosHttpError` 409) | Mirrors F7.2 `SalidaDuplicadaError` precedent — page catches the typed error and renders the localized banner; no string-match on body. |
| AD6 | `mutate(key)` inside `useReintentarFE.trigger()` after 201 (vs consumer-driven) | Mirrors F7.2 `useRegistrarSalida` precedent (hook owns the cache); one source of truth; avoids stale `aceptado` flash (R1). |

## 3. Data Flow

```
<PagoSheet handleSubmit>
  └─ useRegistrarPago().trigger(post) ──POST /facturacion/factura──> 201 {uuid, factura_electronica}
       └─ PagoSheet: const fe = result.factura_electronica as {uuid?:string}|null
            └─ if (fe?.uuid) navigate(`/factura-electronica/${fe.uuid}`)

<Route path="/factura-electronica/:uuid" ProtectedRoute>
  └─ <FacturaDetalle uuid={useParams().uuid}>
       ├─ useFacturaElectronica(uuid) ──GET /facturacion/factura-electronica/{uuid}──> {estado_dian, cufe?}
       │   refreshInterval: (latest) => TERMINAL.has(latest?.estado_dian) ? 0 : 30_000
       │   ├─ estado='pendiente|enviado' (non-terminal) → poll every 30 s
       │   └─ estado='aceptado|rechazado' (terminal)   → polling stops (refreshInterval=0)
       ├─ useReintentarFE().trigger(uuid) ──POST /facturacion/factura-electronica/{uuid}/reintentar──> 201 {uuid_envio, estado:'pendiente', uuid_envio_padre}
       │   ├─ Idempotency-Key: buildIdempotencyKey({POST, path, body})
       │   ├─ 409 numeracion_agotada → throw NumeracionAgotadaError → page catches → banner role="alert"
       │   ├─ 401 → useAuthStore.clear() + parkos:auth:cleared [F3.1 invariant]
       │   └─ 201 → mutate('/facturacion/factura-electronica/{uuid}') → polling re-engages (new chain tip is pendiente)
       └─ Render:
            ├─ estado visible (testid fe-estado, data-estado={estado_dian})
            ├─ cufe visible ONLY when aceptado (testid fe-cufe)
            ├─ "Reintentar" button ONLY when rechazado (testid fe-reintentar, disabled while isMutating)
            └─ banner role="alert" ONLY when NumeracionAgotadaError caught
```

## 4. File Changes (8 files, ~300 LOC)

NEW: `features/facturacion/pages/FacturaDetalle.tsx` (~80) + `.test.tsx` (~60); `features/facturacion/hooks/useReintentarFE.ts` (~50) + `.test.ts` (~70); `e2e/fe.spec.ts` (~40).
UPDATE: `features/facturacion/hooks/useFacturaElectronica.ts` (+15) + `.test.ts` (+40 — add F4/F5 terminal-gating); `features/facturacion/components/PagoSheet.tsx` (+10 — `useNavigate` + post-pago navigate); `renderer/App.tsx` (+7 — 1 `<Route>` + import); `renderer/i18n/locales/facturacion.json` (+5 keys: `fe.estado.pendiente|enviado|aceptado|rechazado` split, `fe.errors.numeracion_agotada`).

## 5. Interfaces / Contracts

```ts
// useFacturaElectronica.ts — UPDATE (terminal-gating)
const TERMINAL_STATES = new Set(['aceptado', 'rechazado'] as const);
refreshInterval: (latest) => (latest && TERMINAL_STATES.has(latest.estado_dian as 'aceptado'|'rechazado')) ? 0 : FE_REFRESH_INTERVAL_MS,
// 0 → SWR treats as "do not poll". Reintentar's mutate() re-engages polling with the new chain tip.

// useReintentarFE.ts — NEW (mirrors useRegistrarSalida.ts:73-101)
export class NumeracionAgotadaError extends Error { readonly status=409; readonly code='numeracion_agotada'; constructor() { super('numeracion_agotada'); this.name='NumeracionAgotadaError'; } }
export function useReintentarFE(): { trigger(uuid:string): Promise<{uuid_envio:string; estado:'pendiente'; uuid_envio_padre:string}>; isMutating:boolean; error: ParkosHttpError|NumeracionAgotadaError|undefined; };
//   trigger:
//     1. idempotencyKey = buildIdempotencyKey({method:'POST', path:`/.../${uuid}/reintentar`, body:{}})
//     2. parkosFetch → POST .../reintentar {headers:{'Idempotency-Key': idempotencyKey}}
//     3. 401 → useAuthStore.clear() + parkos:auth:cleared → throw ParkosHttpError(401)
//     4. 409 numeracion_agotada → throw NumeracionAgotadaError
//     5. 201 → mutate(`/facturacion/factura-electronica/${uuid}`) → await → return {uuid_envio, estado:'pendiente', uuid_envio_padre}

// FacturaDetalle.tsx — NEW (routed page)
export function FacturaDetalle(): JSX.Element {
  const { uuid } = useParams<{uuid:string}>();
  const { data, error } = useFacturaElectronica(uuid ?? null);
  const { trigger: reintentar, isMutating, error: reintError } = useReintentarFE();
  const [numeracionAgotada, setNumeracionAgotada] = useState(false);
  return (
    <article data-testid="factura-detalle">
      <header><h1>{t('fe.titulo')}</h1></header>
      {uuid && <FacturaElectronicaRetryPanel uuid_fe={uuid} />}  {/* polling + estado + cufe */}
      {data?.estado_dian === 'rechazado' && (
        <Button data-testid="fe-reintentar" disabled={isMutating} onClick={async () => {
          setNumeracionAgotada(false);
          try { await reintentar(uuid); } catch (e) {
            if (e instanceof NumeracionAgotadaError) setNumeracionAgotada(true);
          }
        }}>{t('fe.reintentar')}</Button>
      )}
      {numeracionAgotada && <div role="alert" data-testid="fe-banner-numeracion-agotada">{t('fe.errors.numeracion_agotada')}</div>}
    </article>
  );
}
```

## 6. Testing Strategy

- **Hook unit (5)**: `useFacturaElectronica.test.ts` F4 (estado='aceptado' → `refreshInterval(latest)=0`) + F5 (estado='rechazado' → 0) — vitest with `vi.advanceTimersByTime`. `useReintentarFE.test.ts` T1 (POST 201 → returns `{uuid_envio, estado:'pendiente', uuid_envio_padre}`), T2 (409 `numeracion_agotada` → throws `NumeracionAgotadaError`), T3 (401 → `useAuthStore.clear` + event dispatched) — mirrors `useRegistrarSalida.test.ts` R1/R4/R5.
- **Component (5)**: `FacturaDetalle.test.tsx` T1 (estado='pendiente' → "Pendiente" label); T2 (estado='aceptado' → "Aceptado" + CUFE visible); T3 (estado='rechazado' → "Rechazado" + "Reintentar" button visible); T4 (click "Reintentar" → `useReintentarFE.trigger` called with uuid); T5 (after `trigger` throws `NumeracionAgotadaError` → banner with `role="alert"`).
- **Integration (2)**: `<PagoSheet />` P6 (existing tests still pass — `navigate` invocation doesn't break sheet lifecycle); `FacturaElectronicaRetryPanel` consumes `useReintentarFE` (existing test still passes — FE-3 fetcher URL invariant preserved).
- **e2e (3 stub)**: `e2e/fe.spec.ts` — S1 (estado visible on page load); S2 (polling active while `pendiente|enviado`, stops on terminal via `vi.useFakeTimers`); S3 (reintentar button → POST → cache mutated). Sandbox F.6 caveat per F8.1 precedent.

## 7. Threat Matrix

N/A — renderer-only; F1.10 backend unchanged; F3.1 401 invariant preserved verbatim; F7.2 `Idempotency-Key` SHA-256 closure reused. `NumeracionAgotadaError` typed class is the only new attack surface and it carries no payload.

## 8. Migration

None. No DB / Alembic / backend / Docker change. Renderer-only delta. `facturaApi.ts::FacturaReadSchema::factura_electronica: z.unknown()` carry-forward is flagged as **ABIERTO-F8.2-01** follow-up for F8.3 / F8.x (tracked in apply-progress.md + verify-report.md).

## 9. Open Questions

### OD-1 — Polling stops on BOTH terminal states (`aceptado | rechazado`)?
- **Proposal**: stop on BOTH (ratified in proposal §7). `useReintentarFE` re-engages polling because the new chain tip is `pendiente`.
- **Mitigation**: `mutate()` is awaited inside `trigger()` (R1) so UI re-renders with the new chain tip in the same commit.
- **Status**: RATIFIED in proposal §7.

### OD-2 — `useReintentarFE` revalidates cache internally vs consumer-driven?
- **Proposal**: revalidate inside the hook (mirrors F7.2 `useRegistrarSalida` precedent — hook owns the cache).
- **Status**: RATIFIED in proposal §7.

## 10. Review Workload Forecast

Forecast ~300 LOC vs 800 budget → **no `size:exception`**. **Chained PRs: No** (single PR, 4 commits). Drift guard: `useFacturaElectronica.refreshInterval` MUST be the callback form (not the constant) — verified by F4 + F5 unit tests. `useReintentarFE` MUST be the only mutation hook for `.../reintentar` — verified by `FacturaElectronicaRetryPanel` test (inline `parkosFetch` is gone).
