# Proposal: HU-F8.2 — FacturaDetalle FE status + reintento

> **Change**: `fase-8-2-factura-detalle-fe`
> **Phase**: propose (sdd-propose)
> **HU**: HU-F8.2 (Fase 8 — CU-04 cierre DIAN)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC/PR`, strict_tdd=`true`
> **Branch**: `dev` (HEAD `4c969a5`, F8.1 merged)
> **Git identity**: `Parkos Dev <dev@parkos.local>`. No AI attribution per AGENTS.md canon.
> **Inputs read**:
>   - `plan.md` lines 1941-1966 (F8.2 ACs + ER + 409 numeracion_agotada + reintento pattern)
>   - `apps/electron-sucursal/src/features/facturacion/{components,hooks,api}/` (live `dev` state — see §0)
>   - `openspec/changes/archive/2026-09-19-fase-8-1-pago-modal-fe/{proposal,design,tasks,verify-report}.md` (F8.1 baseline + F8.2 handoff promise in §3.5)
>   - `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/{design,tasks,verify-report}.md` (F1.10 FE numeration + retry chain + `v_factura_electronica_acuse` view)
>   - `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/` (F7.2 — `buildIdempotencyKey` SHA-256 reuse)
> **Forecast**: ~380 LOC production + ~250 LOC tests (under 800 budget — **no `size:exception`**)

## 0. Drift Reconciliation (mandatory)

The orchestrator's brief assumes a green-field F8.2. The `dev` branch already contains F8.2-adjacent scaffolding shipped on the F8.1 PR (`feature/hu-f8-1-pago-modal-fe`):

| File | Status | What F8.2 changes |
|---|---|---|
| `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` | **EXISTS** (110 LOC, polls every 30s, lazy-mount, 401 → auth-clear) | Tighten polling to **gate by terminal state** (Decision Path 1). Add F4 + F5 unit tests. |
| `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.test.ts` | **EXISTS** (3 scenarios: F1 null key / F2 fetcher URL / F3 401 logout) | + 2 scenarios for terminal-state gating |
| `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` | **EXISTS** (93 LOC, presentational; calls `parkosFetch('/.../reintentar', {method:'POST'})` inline via `useCallback`) | Refactor to consume `useReintentarFE` hook (Decision Path 2). Drop inline fetch. |
| `apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts` | **EXISTS** (141 LOC) | `FacturaReadSchema::factura_electronica: z.unknown().nullable().optional()` — kept as-is in F8.2; flag as **ABIERTO-F8.2-01** follow-up for proper discriminated schema |
| `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` | **EXISTS** (189 LOC, F8.1 drawer) | Add `navigate('/factura-electronica/<uuid>')` after 201 — closes the F8.1 handoff that was deferred (§3.5 of F8.1 proposal) |
| `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` | **EXISTS** (382 LOC, F8.1 form) | **DO NOT MODIFY** — F8.1 owns |
| `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` | **EXISTS** (98 LOC, F8.1 mutation hook) | **DO NOT MODIFY** — F8.1 owns |

**Net F8.2 deliverables** (7 files touched, 1 NEW page, 1 NEW hook):

1. NEW `pages/FacturaDetalle.tsx` page (the `plan.md:1954` "Componentes UI: FacturaDetalle (page, ...)" — does NOT exist as a routed page; only the inner panel exists)
2. UPDATE `useFacturaElectronica.ts` — terminal-state polling gating
3. NEW `hooks/useReintentarFE.ts` — `useSWRMutation` hook for `POST /reintentar`
4. UPDATE `FacturaElectronicaRetryPanel.tsx` — consume the hook
5. UPDATE `PagoSheet.tsx` — navigate to FacturaDetalle after 201
6. UPDATE `facturacion.json` — `fe.estado.pendiente|enviado|aceptado|rechazado` (split), `fe.errors.numeracion_agotada`
7. NEW `e2e/fe.spec.ts` — 3 scenarios

## 1. Intent

From a confirmed `PagoSheet` 201, the operator lands on `FacturaDetalle` — a routed page that shows the current FE state (`pendiente | enviado | aceptado | rechazado`) and the CUFE when `aceptado`. Polls every 30s while not terminal. Reintentar fires `POST /factura-electronica/{uuid}/reintentar` — creates a NEW `envio_dian` row chained via `uuid_envio_padre`, NEVER UPDATE on `envio_dian` (F1.10 DEC-FE-02 + REQ-OPS-070). Range exhaustion (`409 numeracion_agotada`) surfaces a localized banner pointing at the already-seeded `fe_numbering_exhausted` alerta.

User-facing payoff: the operador ya no queda mirando una pantalla en blanco durante los 30-90 segundos que TopPoint demora en aceptar la FE. Tiene feedback inmediato del estado y puede reintentar un rechazo sin pedir ayuda al administrador (excepto `numeracion_agotada`, que es problema de la sucursal y requiere acción admin).

## 2. Scope

### 2.1 In scope (T1..T5 + I1)

- **T1 — `pages/FacturaDetalle.tsx`** (NEW, 80 LOC): routed page that mounts `<FacturaElectronicaRetryPanel />` + the `numeracion_agotada` banner + page header. Reads `uuid_fe` from a `useParams<{ uuid: string }>()` hook on the new `/factura-electronica/:uuid` route in `App.tsx`. Wrapped in `<ProtectedRoute>` (operador- JWT required, same as Dashboard).
- **T2 — `useFacturaElectronica` terminal-gating** (+15 LOC production + 40 LOC tests): change `refreshInterval: 30_000` (constant) to `refreshInterval: (latest) => terminal(latest) ? 0 : 30_000` (callback form). SWR treats `0` as "do not poll". Add tests F4 (terminal `aceptado` → 0) and F5 (terminal `rechazado` → 0).
- **T3 — `useReintentarFE` `useSWRMutation` hook** (NEW, 50 LOC production + 70 LOC tests): POST `/api/v1/facturacion/factura-electronica/{uuid}/reintentar` with `Idempotency-Key` SHA-256 from F7.2 `buildIdempotencyKey`. Returns `{uuid_envio, estado:'pendiente', uuid_envio_padre}`. Throws typed `NumeracionAgotadaError` on 409. Mirrors F7.2 `useRegistrarSalida.ts:73-101`.
- **T4 — `FacturaElectronicaRetryPanel.tsx` refactor** (−10/+15 LOC delta): drop the inline `parkosFetch` callback; consume `useReintentarFE`. The panel becomes a thin presentational layer over the hook.
- **T5 — `PagoSheet.tsx` handoff** (+10 LOC): after `await trigger(post)` succeeds and `result.factura_electronica` is non-null, call `navigate('/factura-electronica/<uuid_fe>')`. Closes the F8.1 §3.5 handoff. Guard: typeof narrow on `result.factura_electronica` (still `z.unknown()` per ABIERTO-F8.2-01).
- **T6 — i18n keys** (+5 keys): `fe.estado.pendiente`, `fe.estado.enviado`, `fe.estado.aceptado`, `fe.estado.rechazado` (split the current single `fe.pendiente|aceptado|rechazado`); `fe.errors.numeracion_agotada` (banner copy: "Numeración agotada. Contactar proveedor.").
- **I1 — `e2e/fe.spec.ts` 3 scenarios** (NEW, 40 LOC): (a) estado visible on page load (intercept GET + assert testid `fe-estado`); (b) polling active while `pendiente|enviado`, stops on `aceptado|rechazado` (use `vi.useFakeTimers()` + advance 30s); (c) reintentar button creates new envio row (intercept POST + assert response consumed + cache mutated).

### 2.2 Out of scope

- HU-F8.3 — reimpresión con costo (`reimpresion_ticket` workflow).
- Backend FE state machine — F1.10 owns.
- Cloud TopPoint integration — out of MVP scope per AGENTS.md cloud-only constraint.
- Strongly typing `FacturaReadSchema.factura_electronica: z.unknown()` — flagged as **ABIERTO-F8.2-01** follow-up (F8.3 or F8.x closes).
- Vite cache invalidation script — AGENTS.md post-merge.
- Release branch + tag — post-merge operational.
- Rewrite of `<FacturaElectronicaRetryPanel />` into a full page — we wrap it; refactor only where required for terminal-gating + the reintentar hook.

## 3. Capabilities

### 3.1 New Capabilities

- `factura-electronica-detalle`: the renderer-side FE status page (`FacturaDetalle`) + terminal-state polling termination + reintentar `useSWRMutation` hook contract + 409 numeracion_agotada banner. Becomes `openspec/specs/factura-electronica-detalle/spec.md`.

### 3.2 Modified Capabilities

- `operations`: F8.1 baseline (REQ-OPS-161..165) extended. Adds REQ-OPS-166 (FacturaDetalle routed page), REQ-OPS-167 (terminal-gating polling), REQ-OPS-168 (`useReintentarFE` `useSWRMutation` + `Idempotency-Key` SHA-256), REQ-OPS-169 (PagoSheet → FacturaDetalle navigate-after-201), REQ-OPS-170 (409 numeracion_agotada banner with localized copy + alerta pointer). Delta spec at `openspec/changes/fase-8-2-factura-detalle-fe/specs/operations/spec.md`.

## 4. Approach

### 4.1 Polling terminal-gating (Decision Path 1)

```ts
// apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts
const FE_REFRESH_INTERVAL_MS = 30_000;
const TERMINAL_STATES = new Set(['aceptado', 'rechazado']);

refreshInterval: (latestData) => {
  if (!latestData) return FE_REFRESH_INTERVAL_MS;
  return TERMINAL_STATES.has(latestData.estado_dian) ? 0 : FE_REFRESH_INTERVAL_MS;
}
```

SWR treats `0` as "do not poll". Stops on **BOTH** terminal states per OD-1. `useReintentarFE` re-engages polling because the new chain tip is `pendiente` (cache mutation re-triggers SWR with a fresh `latestData`).

### 4.2 Reintentar as `useSWRMutation` (Decision Path 2)

```ts
// apps/electron-sucursal/src/features/facturacion/hooks/useReintentarFE.ts
async function trigger(_key: string, { arg: uuid }: { arg: string }) {
  const idempotencyKey = await buildIdempotencyKey({
    method: 'POST', path: `/api/v1/facturacion/factura-electronica/${uuid}/reintentar`,
    body: {},
  });
  try {
    const raw = await parkosFetch<EnvioDianRetryRead>(`.../reintentar`, {
      method: 'POST', headers: { 'Idempotency-Key': idempotencyKey },
    });
    // Revalidate the polling cache so the new chain tip (`pendiente`) re-engages the 30s loop.
    await mutate(`/facturacion/factura-electronica/${uuid}`);
    return EnvioDianRetryReadSchema.parse(raw);
  } catch (err) {
    if (err instanceof ParkosHttpError) {
      if (err.status === 401) { useAuthStore.getState().clear(); window.dispatchEvent(new Event('parkos:auth:cleared')); }
      if (err.status === 409) throw new NumeracionAgotadaError(err.body);
    }
    throw err;
  }
}
```

`NumeracionAgotadaError` is a typed error class the `<FacturaDetalle />` page catches and renders as the banner.

### 4.3 FacturaDetalle as routed page (Decision Path 3)

```tsx
// apps/electron-sucursal/src/renderer/App.tsx (UPDATE)
<Route path="/factura-electronica/:uuid" element={
  <ProtectedRoute><FacturaDetalle /></ProtectedRoute>
} />

// apps/electron-sucursal/src/features/facturacion/pages/FacturaDetalle.tsx (NEW)
export function FacturaDetalle(): JSX.Element {
  const { uuid } = useParams<{ uuid: string }>();
  const reintentarError = useReintentarFEStore(/* subscribe to hook error */);
  return (
    <article>
      <header><h1>{t('facturacion:fe.titulo')}</h1></header>
      {uuid && <FacturaElectronicaRetryPanel uuid_fe={uuid} />}
      {reintentarError?.code === 'numeracion_agotada' && (
        <Banner role="alert">{t('facturacion:fe.errors.numeracion_agotada')}</Banner>
      )}
    </article>
  );
}
```

The existing `<FacturaElectronicaRetryPanel />` continues to call `useFacturaElectronica(uuid_fe)` internally — **no double-fetching** because the hook's SWR key gating is `null` when the parent already has the data (F8.1 invariant). The panel's `uuid_fe` prop is now passed by the page rather than the Dashboard.

### 4.4 PagoSheet → FacturaDetalle handoff (closes F8.1 §3.5)

```ts
// apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx (UPDATE)
const navigate = useNavigate();

const handleSubmit = useCallback(async (values: PagoFormValues) => {
  // ... existing code ...
  const result = await trigger(post);
  // F8.2 handoff — navigate to FE detail page if FE was created
  const fe = result.factura_electronica as { uuid?: string } | null | undefined;
  if (fe && typeof fe.uuid === 'string') {
    navigate(`/factura-electronica/${fe.uuid}`);
  }
  deferredSafePrint(emit, 'salida', { uuid_factura: result.uuid });
  deferredSafePrint(emit, 'recibo_pago', { uuid_factura: result.uuid, numero_recibo: result.numero_recibo });
  close();
}, [..., navigate]);
```

The `as` cast is justified by ABIERTO-F8.2-01 — F8.2 narrows the `z.unknown()` defensively without changing the schema.

## 5. Affected Areas

| Area | Action | LOC est. |
|---|---|---|
| `apps/electron-sucursal/src/features/facturacion/pages/FacturaDetalle.tsx` | NEW | 80 |
| `apps/electron-sucursal/src/features/facturacion/pages/FacturaDetalle.test.tsx` | NEW | 60 |
| `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` | UPDATE | +15 |
| `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.test.ts` | UPDATE | +40 |
| `apps/electron-sucursal/src/features/facturacion/hooks/useReintentarFE.ts` | NEW | 50 |
| `apps/electron-sucursal/src/features/facturacion/hooks/useReintentarFE.test.ts` | NEW | 70 |
| `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` | UPDATE | +5 net (−10 inline fetch, +15 hook consumption) |
| `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` | UPDATE | +10 (navigate + `useNavigate` import) |
| `apps/electron-sucursal/src/renderer/App.tsx` | UPDATE | +7 (1 new `<Route>` + import) |
| `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` | UPDATE | +5 keys |
| `apps/electron-sucursal/e2e/fe.spec.ts` | NEW | 40 |
| **Total new LOC** | | **~382** |

## 6. Risks

| # | Risk | Sev | Mitigation |
|---|---|---|---|
| **R1** | Polling stops on `aceptado` — `useReintentarFE` cache mutation re-triggers — but if `mutate()` is racy with the SWR cache, the panel briefly shows stale `aceptado` while the new `pendiente` row is fetched. | LOW | `mutate()` is awaited before returning from `useReintentarFE.trigger()` (synchronous cache update); UI re-renders with the new chain tip in the same React commit. |
| **R2** | `useReintentarFE` race with rapid clicks (operator double-tap on "Reintentar"). | LOW | `useSWRMutation.isMutating` disables the button (`FacturaElectronicaRetryPanel.tsx` — mirror F7.2 R2 invariant); `Idempotency-Key` SHA-256 from F7.2 `buildIdempotencyKey` dedups the second POST server-side (24h cache per F1.6). |
| **R3** | `FacturaDetalle` page mounted without auth context — could fetch without `accessToken`. | MED | The existing `useFacturaElectronica` SWR key gating already returns `null` when token is missing (existing pattern, F8.1); FacturaDetalle test covers the unauthenticated case with `<MemoryRouter>` + `useAuthStore.setState({ accessToken: null })`. |
| **R4** | Drift: `facturaApi.ts::FacturaReadSchema::factura_electronica: z.unknown()` — the F8.1 hook returns `unknown` for the FE UUID; PagoSheet must defensively narrow. | MED | Tighten to a discriminated union schema in **ABIERTO-F8.2-01** follow-up (F8.3 or F8.x); F8.2 keeps the `unknown` cast inside `PagoSheet.tsx` and asserts `typeof result.factura_electronica === 'object' && result.factura_electronica !== null && 'uuid' in result.factura_electronica` before navigating. |
| **R5** | Routing: the existing `App.tsx` (`react-router-dom` 6.x) does NOT yet have `/factura-electronica/:uuid`. | MED | Verify in sdd-design; F8.2 adds `<Route path="/factura-electronica/:uuid" element={<ProtectedRoute><FacturaDetalle /></ProtectedRoute>} />` (no auth-gate changes — same `operador-` JWT required via `ProtectedRoute`). |
| **R6** | Drift between `plan.md` F8.2 text (`pages/FacturaDetalle`) and the F8.1 scaffold (`components/FacturaElectronicaRetryPanel` already on dev). | DECISION | Reconciliation per §0: `pages/FacturaDetalle.tsx` is the routed page; `components/FacturaElectronicaRetryPanel.tsx` is the inner panel it mounts. Both ship in F8.2; no deletion. |
| **R7** | `409 numeracion_agotada` banner has no actionable CTA — operator clicks, nothing happens. | LOW | Banner copy explicitly says "Contactar proveedor." (admin resolves via resolution renewal — F1.10 owns). `role="alert"` per WCAG 2.1 AA so screen readers announce. |

## 7. Rollback Plan

Single revert: `git revert <merge-sha>` of `feature/hu-f8-2-...` onto `dev`. No DB migration, no backend change (F1.10 unchanged).

Per-commit revert (atomic work-unit-commits):

1. Revert `feat(facturacion): useReintentarFE hook` → polling still works inline (panel reverts to `parkosFetch` callback), navigation still works (just doesn't navigate).
2. Revert `feat(facturacion): useFacturaElectronica terminal-gating` → polling reverts to "always poll every 30s"; operator loses terminal-state optimization but functionality preserved.
3. Revert `feat(facturacion): FacturaDetalle page` → page still navigable to (404 from router); operator loses dedicated view but the inner panel still mounts inside Dashboard.
4. Revert `feat(facturacion): PagoSheet handoff` → no nav after 201; operator sees PagoSheet close normally; FE status visible only by manual Dashboard navigation (no auto-flow).
5. Revert `docs(sdd): i18n keys + 409 banner + e2e spec` → keys fall back to F8.1 defaults; no functional break.

Net effect of any single revert: operator loses ONE feature, but the rest of F8.2 stays.

## 8. Dependencies

- **F8.1** (merged 2026-09-19, commit `4c969a5`): `useRegistrarPago`, `PagoSheet`, `PagoModal`. **Required** — F8.2 closes the §3.5 handoff that F8.1 promised.
- **F1.10** (merged): `POST /api/v1/facturacion/factura-electronica` + `GET .../{uuid}` + `POST .../{uuid}/reintentar` + `prod.v_factura_electronica_acuse` view + `prod.envio_dian` retry chain. **Required**.
- **F7.2** (merged): `buildIdempotencyKey` for `Idempotency-Key` SHA-256 on `useReintentarFE`. **Required**.
- **F2.x** (merged): `parkosFetch`, `useAuthStore`, `ParkosHttpError`. **Required**.
- **F6.1** (merged): `dashboardDrawerStore` — unaffected (F8.2 uses route nav, not drawers).
- **React Router 6.x** (already in deps per `App.tsx`): `useParams`, `useNavigate`. **Required**.

## 9. Success Criteria

1. `<FacturaDetalle />` renders estado FE + CUFE if `aceptado` + reintentar button if `rechazado` + 409 banner on `numeracion_agotada`.
2. `useFacturaElectronica` polling stops on BOTH terminal states (`aceptado | rechazado`); tests F4 + F5 pass.
3. `useReintentarFE` issues POST with `Idempotency-Key`; 201 returns `{uuid_envio, estado:'pendiente', uuid_envio_padre}`; 409 surfaces `NumeracionAgotadaError`; 401 clears auth (F3.1 invariant).
4. `PagoSheet.handleSubmit` navigates to `/factura-electronica/<uuid_fe>` after a successful pago where `result.factura_electronica?.uuid` is a string.
5. `409 numeracion_agotada` banner renders localized copy "Numeración agotada. Contactar proveedor." with `role="alert"` (WCAG 2.1 AA).
6. `e2e/fe.spec.ts` 3 scenarios pass: estado visible / polling active+stops on terminal / reintentar.
7. `facturaApi.ts` typing improvement captured as **ABIERTO-F8.2-01** follow-up note in the verification report.
8. `pnpm typecheck`, `pnpm lint`, `pnpm test`, `pnpm e2e -- fe.spec.ts` exit 0.
10. axe-core WCAG 2.1 AA: 0 violations on `<FacturaDetalle />` + `<FacturaElectronicaRetryPanel />`.

## 10. Open Decisions to Ratify

### OD-1 — Polling stops on BOTH terminal states (`aceptado | rechazado`)?

- **Proposal**: stop on BOTH. Once `rechazado`, the operator's only forward path is the reintentar button — polling won't surface new state. Manual reintentar re-engages polling because the new chain tip is `pendiente`.
- **Alternative**: stop on `aceptado` only; keep polling `rechazado` for state changes (e.g., cloud-side reversal). Adds noise for an unlikely transition (cloud reversal requires admin action and is reflected via the alerta path, not the FE page).
- **Ratification needed**: confirm BOTH. (Plan.md F8.2 AC explicitly says "polling cada 30 s mientras el estado no sea terminal" — both `aceptado` and `rechazado` are terminal per F1.10 design §3.2 / DEC-FE-04.)

### OD-2 — `useReintentarFE` revalidates cache on 201, or returns the new chain tip and lets the consumer mutate?

- **Proposal**: revalidate inside the hook (`mutate(key)` after 201). Simpler API; one source of truth.
- **Alternative**: return `{ uuid_envio, uuid_factura_electronica }` and let the consumer mutate. More flexible (consumer can choose NOT to mutate if they want to keep the old display).
- **Ratification needed**: confirm revalidate-inside-hook (F7.2 `useRegistrarSalida` precedent — the hook owns the cache invalidation).

## 11. Out of Scope (re-iterated)

- HU-F8.3 (reimpresión con costo) — F8.3 territory.
- Backend FE state machine — F1.10 owns.
- TopPoint integration — cloud-only per AGENTS.md.
- Strongly typing `FacturaReadSchema.factura_electronica: z.unknown()` — **ABIERTO-F8.2-01** follow-up.
- Vite cache invalidation post-merge — AGENTS.md script.
- Release branch + tag — post-merge operational.
- Rewrite of `<FacturaElectronicaRetryPanel />` into a full page — refactor only where required.

## 12. Relevant Files

**OpenSpec / plan / spec**:
- `openspec/changes/fase-8-2-factura-detalle-fe/proposal.md` (this file)
- `openspec/changes/fase-8-2-factura-detalle-fe/specs/{factura-electronica-detalle,operations}/spec.md` (sdd-spec delta)
- `openspec/changes/fase-8-2-factura-detalle-fe/design.md` (sdd-design)
- `openspec/changes/fase-8-2-factura-detalle-fe/tasks.md` (sdd-tasks)
- `plan.md` lines 1941-1966 (F8.2 block: ACs + ER + 409 + reintento pattern)
- `openspec/specs/operations/spec.md` (F8.1 baseline REQ-OPS-161..165 — F8.2 extends REQ-OPS-166..170)

**Archive precedents**:
- `openspec/changes/archive/2026-09-19-fase-8-1-pago-modal-fe/{proposal,design,tasks,verify-report}.md` (F8.1 baseline — F8.2 §3.5 handoff)
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/{design,tasks,verify-report}.md` (F1.10 FE numeration + retry chain)
- `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/{proposal,design,tasks,verify-report}.md` (F7.2 — `useRegistrarSalida` SWR mutation + `buildIdempotencyKey`)

**Frontend source (live on `dev` at `4c969a5`)**:
- `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` — F8.2 tightens terminal-gating (T2)
- `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.test.ts` — F8.2 adds F4 + F5 (T2)
- `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` — F8.2 refactors to use `useReintentarFE` (T4)
- `apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts` — `factura_electronica: z.unknown()` carries over (ABIERTO-F8.2-01)
- `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` — F8.2 does NOT modify
- `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` — F8.2 does NOT modify
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` — F8.2 adds `navigate('/factura-electronica/<uuid>')` after 201 (T5)
- `apps/electron-sucursal/src/renderer/App.tsx` — F8.2 adds `<Route path="/factura-electronica/:uuid">` (T1)
- `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` — F8.2 extends `fe.*` + `fe.errors.*` (T6)
- `apps/electron-sucursal/e2e/fe.spec.ts` — F8.2 NEW (I1)

**Files NOT touched (deliberate)**:
- `backend/**` — F1.10 ships the backend; **zero backend changes** in F8.2
- `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` — F8.1 owns
- `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` — F8.1 owns
- `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` — F7.2 owns (F8.2 doesn't change the operator-flow into pago)

## 13. PR Shape (single PR, 5 commits, ~380 LOC under 800 budget)

| # | Commit | Type | Scope | Files | TDD phase |
|---|---|---|---|---|---|
| 1 | `feat(facturacion): useReintentarFE useSWRMutation hook + 3 unit tests (mirror useRegistrarSalida)` | feat | facturacion | NEW `useReintentarFE.ts` + tests | RED (3 tests fail: 201 ok, 409 numeracion_agotada, 401 auth-cleared) → GREEN |
| 2 | `feat(facturacion): useFacturaElectronica terminal-gating refreshInterval + 2 unit tests` | feat | facturacion | UPDATE `useFacturaElectronica.ts` (+15), UPDATE tests (+40) | RED (F4/F5 fail) → GREEN |
| 3 | `feat(facturacion): FacturaElectronicaRetryPanel consumes useReintentarFE (drop inline parkosFetch)` | refactor | facturacion | UPDATE `FacturaElectronicaRetryPanel.tsx` (net +5) | RED (existing test fails on missing mutation hook) → GREEN |
| 4 | `feat(facturacion): FacturaDetalle routed page + PagoSheet navigate-after-201 handoff + App.tsx route + i18n` | feat | facturacion | NEW `FacturaDetalle.tsx` + tests, UPDATE `PagoSheet.tsx` (+10), UPDATE `App.tsx` (+7), UPDATE `facturacion.json` (+5 keys), NEW `e2e/fe.spec.ts` | RED (3 e2e scenarios fail) → GREEN; existing F8.1 P1..P5 still pass |
| 5 | `docs(sdd): F8.2 spec delta REQ-OPS-166..170 + ABIERTO-F8.2-01 follow-up note` | docs | sdd | UPDATE `openspec/changes/fase-8-2-factura-detalle-fe/specs/operations/spec.md`, UPDATE `openspec/specs/operations/spec.md` | Spec sync |

**Branch**: `feature/hu-f8-2-factura-detalle-fe` → `dev`. **No `size:exception`** (382 LOC < 800 budget).

## 14. Next Steps

1. **sdd-spec**: author delta spec at `openspec/changes/fase-8-2-factura-detalle-fe/specs/operations/spec.md` (REQ-OPS-166..170, 5 scenarios each) + new full spec at `openspec/changes/fase-8-2-factura-detalle-fe/specs/factura-electronica-detalle/spec.md` (FacturaDetalle page contract + `useReintentarFE` hook contract + ABIERTO-F8.2-01 carry-forward).
2. **sdd-design**: technical design for `FacturaDetalle.tsx` page composition + `refreshInterval` callback gating + `useReintentarFE` `useSWRMutation` mirror-of-`useRegistrarSalida` + PagoSheet navigate-after-201.
3. **sdd-tasks**: 5-commit plan from §13 mapped to T-HU-F8.2-1..N task IDs with RED/GREEN/REFACTOR phases per commit. No `size:exception` required (under 800 LOC).
4. **sdd-apply**: implement + verify + merge to `dev` per AGENTS.md gitflow + override rule 2026-09-17.
5. **sdd-verify**: run verification per §9 success criteria; produce `verify-report.md` with test counts, axe-core 0-violations output, drift-guard grep outputs.
6. **sdd-archive**: sync delta specs to canonical `openspec/specs/operations/spec.md` + `openspec/specs/factura-electronica-detalle/spec.md`; archive the change folder.