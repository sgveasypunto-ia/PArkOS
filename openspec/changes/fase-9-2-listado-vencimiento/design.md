# Design: HU-F9.2 Listado y alerta de vencimiento

## Technical Approach

Capa única — frontend-only sobre dos endpoints read-only de
`subscripciones_cliente`. Reutiliza la composición SWR ya probada en
F3.3 `useSesionActiva` + F6.1 `useIngresoActivo` (key gating por
`(accessToken, uuid_sucursal)`, 401-clear invariant, `dedupingInterval`,
`shouldRetryOnError` excluyendo 401/403/404). El componente presentacional
es desacoplado del fetch — el hook entrega el array filtrado y ordenado,
y el componente lo renderiza.

Constante única `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` en
`lib/constants.ts`. Cero estado global nuevo, cero mutaciones. La página
`<Listado />` y el banner del `<Dashboard />` son consumidores del mismo
hook, así que la latencia del banner es a lo sumo 60s después del listado
(acceptable — el banner es informativo, no crítico).

No hay migración ni feature flag: lectura-only, sin cambios de schema,
sin índices nuevos, sin ALTER en `subscripciones_cliente`.

## Architecture Decisions

### Decision: single source of truth via constant

**Choice**: `DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` exportado de
`lib/constants.ts`, sin override por suscripción.
**Alternatives considered**: (a) leer desde `tipo_sucursal.caracteristicas`
JSON en runtime; (b) per-row column en `subscripciones_cliente`.
**Rationale**: ER no tiene columna (4FN); característica JSON requiere
backend round-trip; plan.md:2105 deja ABIERTO-05 explícito. F9.2 ships
global only.

### Decision: hook polling cadence 60s

**Choice**: `refreshInterval: 60_000` (= 60 seconds).
**Alternatives considered**: (a) 30s — duplica tráfico sin valor; (b)
300s — latency del banner percibido peor; (c) on-demand only — el
operador espera varios segundos para ver cambios.
**Rationale**: 60s balance entre freshness y traffic. La lista `/suscripciones`
puede usar `dedupingInterval` más alto (60s también) y son SWR keys distintas.
Verificable en e2e.

### Decision: filter+sort en cliente, NO en backend

**Choice**: el backend devuelve todas las vigentes de la sede, el hook
filtra `dias < 0` y ordena por `fecha_vencimiento` ASC client-side.
**Alternatives considered**: (a) backend `?proximas=true&limit=5` — otro
endpoint, otro deploy, más riesgo.
**Rationale**: El set esperado por sede es decenas, no miles. Procesar
en cliente reduce round-trips, y deja el backend libre de policy que
puede cambiar con el override per-row (ABIERTO-05).

### Decision: integración en Dashboard.tsx (no Principal.tsx)

**Choice**: F9.2 banner y panel se montan en `Dashboard.tsx`
(`apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx`).
**Alternatives considered**: crear `Principal.tsx` como nuevo file;
rechazado — introduciría ruta muerta y duplicación de Layout.
**Rationale**: `Principal.tsx` NO existe en `dev`. El plan.md lo referencia
(line 2122) por un nombre histórico del hub F6.x; el nombre canon en
`dev` es `Dashboard.tsx`. Disclosed in apply-progress.

### Decision: hook & component no agregan SWR mutation

**Choice**: ambos son solo-lectura (SWR poll, sin `useSWRMutation`).
**Alternatives considered**: añadir un `markAsContacted` mutación al
banner; rechazado — fuera de scope.
**Rationale**: El banner es solo informativo. La notificación push / el
recordatorio automático son work futuro.

## Data Flow

```
                              ┌────────────────────────────┐
   GET /api/v1/suscripciones- │  backend (existing)         │
   cliente/proximas-vencer ──►│  subscripciones_cliente     │
   ?uuid_sucursal=X           │  + JOIN plan/cliente/sucursal│
                              └────────────┬───────────────┘
                                           │
                                           ▼
       ┌─────────────────────────────────────────────────────────┐
       │  useSuscripcionesProximasVencer(uuid_sucursal)          │
       │  - SWR key gated by accessToken + uuid_sucursal         │
       │  - refreshInterval: 60_000                              │
       │  - 401 → useAuthStore.clear() + parkos:auth:cleared     │
       │  - filter: dias_para_vencer >= 0  (exclude vencidas)    │
       │  - sort:   fecha_vencimiento ASCENDING                  │
       │  - default: DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7     │
       └──────────────────┬──────────────────┬───────────────────┘
                          │                  │
                          ▼                  ▼
        ┌──────────────────────────┐  ┌────────────────────────────┐
        │ <Listado />              │  │ <Dashboard /> banner       │
        │ /suscripciones           │  │ role="alert"               │
        │ - useSuscripcionesList   │  │ + panel top-5 right sidebar│
        │   (F9.1 SWR read)        │  │ data-testid                │
        │ - búsqueda cliente-side  │  │ =dashboard-vencimiento-*   │
        │ - DataTable 5 cols       │  └────────────────────────────┘
        └──────────────────────────┘
```

## File Changes

| File | Action | Description |
|---|---|---|
| `apps/electron-sucursal/src/features/suscripciones/lib/constants.ts` | Create | `export const DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7` |
| `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.ts` | Create | SWR hook (poll 60s, filter, sort) |
| `apps/electron-sucursal/src/features/suscripciones/hooks/useSuscripcionesProximasVencer.test.ts` | Create | 3 vitest tests |
| `apps/electron-sucursal/src/features/suscripciones/pages/Listado.tsx` | Create | DataTable + búsqueda cliente-side |
| `apps/electron-sucursal/src/features/suscripciones/pages/Listado.test.tsx` | Create | 3 component tests |
| `apps/electron-sucursal/src/features/caja/pages/Dashboard.tsx` | Modify | Inline banner + panel top-5 |
| `apps/electron-sucursal/src/renderer/App.tsx` | Modify | Register `/suscripciones` route |
| `apps/electron-sucursal/src/renderer/i18n/locales/suscripciones.json` | Modify | +8 keys |
| `apps/electron-sucursal/e2e/suscripciones-lista.spec.ts` | Create | 2 Playwright stub scenarios |
| `apps/electron-sucursal/vitest.config.ts` | Modify | +2 per-file coverage thresholds |

## Interfaces / Contracts

```typescript
// lib/constants.ts
export const DEFAULT_DIAS_ALERTA_PRE_VENCIMIENTO = 7;

// hooks/useSuscripcionesProximasVencer.ts
export interface ProximaVencer {
  uuid: string;            // uuid_subscripcion
  placa: string;
  cliente_nombre: string;
  plan_nombre: string;
  fecha_vencimiento: string;  // ISO YYYY-MM-DD
  estado: 'activa' | 'vencida' | 'suspendida';
  dias_para_vencer: number;   // floor((vencimiento - NOW).days); <0 filtered
}

export function useSuscripcionesProximasVencer(
  uuid_sucursal: string | null,
): {
  data: ProximaVencer[] | undefined;
  error: Error | undefined;
  isLoading: boolean;
  refresh: () => Promise<ProximaVencer[] | undefined>;
};

// pages/Listado.tsx (search filter — pure)
export function filterBySearch(
  rows: ProximaVencer[],
  query: string,
): ProximaVencer[]; // case-insensitive .includes() on placa OR cliente_nombre
```

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit (hook) | filter excludes vencidas; sort ASC; empty array | `renderHook` + `vi.mock('@parkos/ui-kit/fetch')` (F9.1 precedent) |
| Component (page) | render shows 5 columns; search input filters; empty search shows all | RTL `render` + `fireEvent.change`; mock `useSuscripcionesList` |
| E2E (Playwright) | `/suscripciones` route loads; banner appears with stub backend | `page.goto('/suscripciones')` + `expect(page.getByTestId('listado-search-input')).toBeVisible()` |
| Drift | `git grep dias_alerta_pre_vencimiento_override` returns 0 | Pre-commit verification |

## Threat Matrix

N/A — no routing, no shell, no subprocess, no VCS/PR automation,
no executable-file classification, no process-integration boundary.

## Migration / Rollout

No migration required. F9.2 is purely additive:

1. `lib/constants.ts` ships with the constant (no DDL).
2. SWR hooks hit existing endpoints; no DB change.
3. `<Dashboard />` updates render banner conditionally;
   no change for usuarios sin vencimientos próximos (banner = null).
4. `/suscripciones` route is new; existing `/suscripciones/venta` wizard
   (F9.1) is unaffected.

Rollout = branch → squash-merge to `dev` → release. Rollback =
single `git revert` of the merge commit on `dev` (read-only feature).

## Open Questions

- [x] **OD-1 polling cadence** — RATIFIED: 60_000 ms (60s).
  Rationale: balance traffic vs freshness; verifiable in e2e.

No other open questions. ABIERTO-05 is OUT of scope per plan.md:2105
and is wired as a drift guard.

## Review Workload Forecast

- Estimated changed lines: ~300 (10 files, mostly NEW small ones)
- 400-line budget risk: **Low**
- Chained PRs recommended: **No** — single PR, well under budget
- Delivery strategy: **single-pr**
- Size exception needed: **No**
