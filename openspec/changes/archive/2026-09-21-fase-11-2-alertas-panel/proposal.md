# Proposal: HU-F11.2 — Panel de alertas locales (AlertasPanel)

**Change**: `fase-11-2-alertas-panel`
**Phase**: propose
**Status**: Draft
**Strict-TDD**: enforced
**Size budget**: 210 LOC forecast (under meta-budget 2000)

## Intent

Branch operators need a single side panel to view, understand, and resolve the 11 business alerts affecting their branch today. Without it, alerts surface only through opaque log entries — operators are blind to `descuadre_critico`, `fe_error_toppoint`, `numeracion_toppoint_agotada`, and the other 8 business alerts seeded by HU-F1.14, even when their cash-count / sync / DIAN pipeline is failing.

This HU closes the last gap of Fase 11 by shipping the `AlertasPanel` FE component, the 8-vs-11 client-side filter (ABIERTO-06), the per-`tipo_alerta` drill-down router, and the append-only "marcar revisada" transition (DEC-SUC-25). The corrected `GET /workflows/alerta` endpoint from HU-F1.1 is assumed working — F11.2 does not retouch the backend route.

## Scope

### In Scope

- `AlertasPanel.tsx` (list + filter chips by `tipo_alerta`/`severidad` + drill-down by `tipo_alerta`).
- Promote the `useAlertas` SWR stub from `features/sync/hooks/useSyncEstado.ts:110` (F11.1 scaffold) to `features/alertas/hooks/useAlertas.ts`; add `useResolverAlerta` for the append-only POST transition.
- `lib/alertas/router.ts` — per-`tipo_alerta` drill-down map (uuid_arqueo, uuid_FE, uuid_suscripcion, datos_nuevos.uuid_ingreso, etc.).
- `e2e/alertas-panel.spec.ts` — 2 scenarios (11 visibles + filterable; marcar-revisada → backend row persisted).
- Append-only `marcar-revisada` action: POST `AlertaCreate` with `uuid_alerta_padre` + `estado='resuelta'`. NO `PUT`/`PATCH` on `prod.alerta`.
- Client-side exclusion of the 8 technical codes (ABIERTO-06): `hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`.
- Reconcile FE Zod `estado` enum to match backend Pydantic (`activa | descartada | resuelta`) — DA-F11.2-9.
- Bootstrap covering tests for `AlertaRead`, `AlertaReadList`, `useAlertas`, `AlertaSchema` — DA-F11.2-11.

### Out of Scope

- Backend route handler modifications — F11.2 assumes `GET /workflows/alerta` works.
- Alert-types seed — already shipped in F1.14.
- Real-time push (WebSocket) — deferred to v2.
- Admin-side alertas UI in `web_admin` — separate HU.

## Capabilities

### New Capabilities

- `alertas-panel`: branch-side panel listing active alerts, filtering by `tipo_alerta`/`severidad`, drilling down to the source object, and resolving via append-only transition.

### Modified Capabilities

- None. `AlertasPanel` is purely additive at the spec level; backend `AlertaRead` is investigation-only.

## Approach

The FE work follows the F11.1 strict-TDD pattern exactly (RED → GREEN → REFACTOR, one behaviour per commit):

1. **RED** — bootstrap tests: `AlertaRead` schema parser (BE → FE), `useAlertas` SWR hook with mocked `parkosFetch`, `AlertaPanel` renders 11 alerts + 2 filters + drill-down, `useResolverAlerta` posts append-only and refreshes SWR cache.
2. **GREEN** — wire to live endpoint. Promote `useAlertas` to `features/alertas/hooks/useAlertas.ts`; delete the F11.1 stub from `useSyncEstado.ts`.
3. **REFACTOR** — split: `AlertaCard` (list item), `AlertaFilterChips` (filters), `DrillDownButton` (per-`tipo_alerta` router), `ResolverAlertaButton` (POST append).
4. **`alert_types` JOIN** — resolve DA-F11.2-10 in spec phase. If `AlertaRead` does NOT include `severidad`/`descripcion`, spec proposes a backend delta (extend `AlertaRead` with JOIN) OR a FE merge from `GET /workflows/alert-types`. Both are scoped for verification in spec, not in this proposal.
5. **e2e** — Playwright spec verifies (a) 11 business alerts visible + filterable + drill-down works, (b) `marcar-revisada` POST returns 200 AND a new row appears in `prod.alerta` with `uuid_alerta_padre` pointing to the original (backend assertion via test DB, not just local UI state — DA-F11.2-8).
6. **State vocabulary reconciliation** — DA-F11.2-9: FE Zod `estado` enum changes from `['abierta', 'cerrada']` to `['activa', 'descartada', 'resuelta']`; query param changes from `?estado=abierta` to `?estado=activa`. Acceptable break: F11.2 is the first HU that uses the hook in production; the F11.1 stub never shipped to users.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/features/sync/hooks/useSyncEstado.ts` | Modified | Delete F11.1 `useAlertas` / `AlertaSchema` / `AlertaArraySchema` / `fetchAlertas` (moved). |
| `apps/electron-sucursal/src/features/alertas/hooks/useAlertas.ts` | New | Promoted SWR hook with reconciled `estado` enum + `refreshInterval: 30_000`. |
| `apps/electron-sucursal/src/features/alertas/hooks/useResolverAlerta.ts` | New | POST append-only mutation; invalidates `useAlertas` SWR cache on success. |
| `apps/electron-sucursal/src/features/sync/components/AlertasPanel.tsx` | Modified | Promote from F11.1 stub to production: list + filters + drill-down + resolver (DA-F11.2-12). |
| `apps/electron-sucursal/src/features/alertas/components/AlertaCard.tsx` | New | Single alert row (severity badge, mensaje, drill-down button, resolver button). |
| `apps/electron-sucursal/src/features/alertas/components/AlertaFilterChips.tsx` | New | `tipo_alerta` + `severidad` filter chips (client-side). |
| `apps/electron-sucursal/src/lib/alertas/router.ts` | New | Per-`tipo_alerta` drill-down router map keyed by code with `uuid_*` field reference. |
| `apps/electron-sucursal/src/lib/alertas/constants.ts` | New | Whitelist of 8 technical codes (excluded) + sorted list of 11 business codes (informational). |
| `apps/electron-sucursal/e2e/alertas-panel.spec.ts` | New | 2 scenarios per plan; Playwright + backend DB assertion. |
| `apps/electron-sucursal/src/locales/{es-CO,en-US,pt-BR}.json` | Modified | i18n keys: `alertas.panel.*`, `alertas.severidad.{alta,media,baja}`, `alertas.action.markResolved`, `alertas.empty.*`. |
| `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` | Investigated | Confirm `AlertaRead` JOIN shape + state vocabulary (DA-F11.2-9, DA-F11.2-10). |
| `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` | Investigated | Confirm POST handler for transition + REQ-26 actor check on `resuelta` (DA-F11.2-2, DA-F11.2-13). |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| DA-F11.2-10: BE `AlertaRead` lacks `severidad`/`descripcion` | High | Decide backend delta vs FE merge in spec phase; spec must commit one path before tasks. |
| DA-F11.2-9: state vocabulary drift breaks F11.1 stub consumers | Med | One-line Zod enum change; delete stub cleanly; bump F11.1 module version. |
| DA-F11.2-2: backend POST endpoint shape not yet verified | Med | Spec phase reads `api/v1/workflows.py` POST handler; if absent, request backend delta in spec. |
| DA-F11.2-5: adding a 12th business alert breaks whitelist | Low | Whitelist encoded as constant array in `lib/alertas/constants.ts`; add 1 line per new business alert. |
| DA-F11.2-13: REQ-26 actor check mistakenly blocks self-resolve | Low | REQ-26 explicitly forbids self-`descartada` only; `resuelta` has no actor check — confirm in spec. |
| DA-F11.2-12: `AlertasPanel.tsx` F11.1 stub conflicts with new design | Med | Spec phase reads current stub before designing; clean rewrite acceptable. |
| Strict-TDD budget exceeded by 8-test bootstrap | Low | Forecast 210 LOC code + ~80 LOC tests; under 300 total. |

## Drift Anchors Surfaced

| ID | Severity | Title |
|----|----------|-------|
| DA-F11.2-1 | High | FE Zod `AlertaSchema` (7 fields) vs BE `AlertaRead` (19 fields) — operational fields missing. |
| DA-F11.2-2 | High | Backend POST for "marcar revisada" not yet verified — assume `POST /workflows/alerta` with `AlertaCreate`. |
| DA-F11.2-3 | Med | Filter UX — client-side (no BE `severidad` filter; `severidad` lives on `alert_types`). |
| DA-F11.2-4 | Med | Drill-down routing — per-`tipo_alerta` map; some types have no FK (`datos_nuevos.uuid_ingreso` fallback). |
| DA-F11.2-5 | Med | 8 technical alerts excluded at FE layer — whitelist as constant in `lib/alertas/constants.ts`. |
| DA-F11.2-6 | Low | Polling 30s already in F11.1 stub — no change. |
| DA-F11.2-7 | Low | Optional: use derived-selector for open-alerts counter badge (apiStatusStore pattern). |
| DA-F11.2-8 | Low | e2e verifies BACKEND state via test DB, not local UI. |
| **DA-F11.2-9** | **Gating** | **State vocabulary drift across 3 layers — reconcile to BE Pydantic enum `activa\|descartada\|resuelta`.** |
| **DA-F11.2-10** | **High** | **No JOIN to `alert_types` in `AlertaRead` — FE or BE merge decision needed.** |
| **DA-F11.2-11** | **High** | **No covering tests for `AlertaRead`, `useAlertas`, `AlertaSchema`, `AlertaReadList` — strict-TDD requires RED bootstrap.** |
| **DA-F11.2-12** | **Med** | **`AlertasPanel.tsx` already exists with 2 callers — inspect F11.1 stub before designing.** |
| **DA-F11.2-13** | **Med** | **REQ-26 actor-check applies only to `descartada`, not `resuelta` — confirm in spec.** |
| **DA-F11.2-14** | **Med** | **`datos_nuevos` JSONB not in FE schema — needed for `capacidad_agotada_forzado` drill-down.** |

## Rollback Plan

1. Revert the `feature/hu-f11-2-alertas-panel` merge to `dev`.
2. Restore `useAlertas` stub in `useSyncEstado.ts:110` (F11.1 state, with reverted `estado` enum).
3. Remove `apps/electron-sucursal/src/features/alertas/` directory.
4. Restore `AlertasPanel.tsx` to F11.1 stub state.
5. Revert i18n key additions under `alertas.*` namespace.
6. Backend untouched — no rollback needed.

## Dependencies

- `GET /api/v1/workflows/alerta` endpoint (assumed working post-F1.1).
- `prod.alert_types` seeded table (assumed from F1.14).
- F11.1 `apiStatusStore` and `parkosFetch` already shipped.
- React 18, Vite 5, TS strict, shadcn/ui (`Card`, `Badge`, `Sheet`, `DropdownMenu`, `Button`, `Toast`).

## Success Criteria

- [ ] 11 business alerts visible + filterable by `tipo_alerta`/`severidad`.
- [ ] 8 technical alerts excluded client-side (ABIERTO-06).
- [ ] Drill-down per `tipo_alerta` → source object (arqueo / FE / suscripcion / ingreso / none).
- [ ] `marcar-revisada` → POST 200 + new row in `prod.alerta` with `uuid_alerta_padre` pointing to original + `estado='resuelta'`.
- [ ] e2e 2/2 scenarios PASS (incl. backend DB assertion).
- [ ] Strict-TDD: RED → GREEN → REFACTOR commits; 21+ unit tests + 2 e2e GREEN.
- [ ] axe-core WCAG 2.1 AA: 0 violations on `AlertasPanel`.
- [ ] DA-F11.2-9 state vocabulary reconciled; DA-F11.2-10 JOIN decision implemented.
- [ ] F11.1 carry-overs (R-CARRY-1, REQ-OPS-173) reconciled in F11.2 spec delta appendix.

## F11.1 Carry-Overs (non-blocking)

Flagged in F11.1 verify-report; reconciled in F11.2 spec delta appendix:

- **R-CARRY-1** — derived `estado` thresholds in `apiStatusStore`. No conflict with F11.2.
- **REQ-OPS-173** — selector letter reserved for the F11.1 strip. No conflict; panel uses a separate i18n namespace (`alertas.*`).

## Open Questions

1. Does `AlertaRead` include JOIN fields from `alert_types` (`severidad`, `descripcion`)? — **DA-F11.2-10, must be resolved in spec phase.**
2. Is there a dedicated `POST /workflows/alerta` for transition, or does F11.2 reuse the existing create path? — **DA-F11.2-2, must be resolved in spec phase.**
3. Does the seeded alerts include `datos_nuevos` payload, and which `tipo_alerta` values populate it? — **DA-F11.2-14, must be resolved in spec phase.**
4. Is the F11.1 `AlertasPanel.tsx` stub a placeholder or partial implementation? — **DA-F11.2-12, must be inspected in spec phase.**