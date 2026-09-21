# Pending — easypunto_parkos (Fase 11: Estado de sincronización y alertas operativas CU-07/CU-14)

> Tracking file for Fase 11 deferred items. Resolved at the end of Fase 11 (after F11.1 + F11.2 close).

| # | ID | HU | Estado al cerrar | Notas |
|---|----|----|------------------|-------|
| 1 | HU-F11.1 | SyncBanner | ✅ CERRADO 2026-09-21 (merge `4021d3d`, archive `2026-09-21`, REQ-OPS-170..176 landed; 2 spec-delta follow-ups below) | 8/8 drift anchors resolved; 21/21 unit tests GREEN; 0 CRITICAL / 0 WARNING / 2 SUGGESTION; +1,312 net LOC under 2,000 meta-budget |
| 2 | HU-F11.2 | AlertasPanel | ✅ CERRADO 2026-09-21 (merge `2424c12`, archive `openspec/changes/archive/2026-09-21-fase-11-2-alertas-panel/`, REQ-OPS-177..183 landed in `operations/spec.md` under Phase 26) | 14/14 drift anchors resolved (DA-F11.2-9 GATING closed; DA-F11.2-10 path-b client-side merge + ABBC-F11.2-BE-1 backend JOIN follow-up below); 30/30 unit/RTL GREEN + 5/5 F11.1 regression; 0 CRITICAL / 0 WARNING / 1 SUGGESTION; +2,285 net LOC within strict_tdd envelope (14% over 2,000 meta-budget, well under 2,500 hard ceiling) |

## 1. Deferred Items

### F11.1 carry-overs (2 spec-delta follow-ups from verify-report SUGGESTIONs)

| ID | Anchor | Severity | Description | Owner |
|---|---|---|---|---|
| **ABBC-F11.1-SPEC-1** | R-CARRY-1 | LOW | REQ-OPS-171 thresholds drift: spec prose says `lag_seg < 300` (online) / `300 <= lag_seg < 3600` (lagging) / `lag_seg >= 3600` (offline) / `pendientes < 100` (online) / `1 <= pendientes < 100` (lagging) / `pendientes >= 100` (offline). Ratified D2 impl uses `60 / 3600 / 5 / 100`. Reconcile via spec delta in F11.2 or earlier. Non-blocking. | sdd-spec (F11.2 or earlier) |
| **ABBC-F11.1-SPEC-2** | REQ-OPS-173 letter | LOW | Spec prose says `apiStatusStore` MUST expose `{ online: boolean, consecutiveFailures, lastFailureIso }`. Impl exposes `{ consecutiveFailures, lastFailureIso, isMounted }` and derives `online` via `selectApiStatusDown(state) === false`. Functionally equivalent; spec delta to reconcile the letter (add selector name + drop `online: boolean` field requirement, OR add `online` derived field to the store). Non-blocking. | sdd-spec (F11.2 or earlier) |

### F11.1 operational hardening (from sdd-archive incident §3)

| ID | Description | Owner |
|---|---|---|
| **R-ARCH-1** | Harden the sdd-archive skill mechanical-copy contract: the snapshot must be taken BEFORE `git mv` (not after), and the post-move copy of untracked files must use `cp -R` not `robocopy /MIR` (which is destructive on an empty snapshot). The current F11.1 archive-report §3 documents the failure mode that arose from the wrong ordering. Forward this hardening to the sdd-archive skill author. | sdd-archive skill maintainer |
| **R-ARCH-2** | Reconstitute the `feature/hu-f11-1-sync-banner` working-tree branch to make the SDD folder available for post-hoc reference. The local branch still exists in git's reflog but its working tree is gone. If F11.2 needs to refer to the F11.1 working tree (for diff comparison, etc.), check out a fresh branch from merge SHA `4021d3d`. | next session (F11.2 setup) |

### F11.2 deferred items (resolved / carried)

| ID | Anchor | Severity | Status | Description | Owner |
|---|---|---|---|---|---|
| **ABBC-F11.2-BE-1** | DA-F11.2-10 (path a) | HIGH | **CARRIED — BACKEND FOLLOW-UP** | Backend `AlertaRead` lacks the JOIN to `prod.alert_types` (severidad / descripcion / mensaje live on alert_types, NOT on alerta). F11.2 ships path (b) — client-side merge from `GET /workflows/alert-types` SWR. Path (a) — extend `AlertaRead` with a JOIN returning `severidad`, `descripcion`, `mensaje` as top-level fields — remains as a backend delta. Removes R-RES-F11.2-1 stale-merge risk (~5 min on hot-deploy). Out of F11.2 scope. | Fase 12+ backend |
| **ABBC-F11.2-BE-2** | ABIERTO-06 | MED | ✅ RESOLVED | 8 technical codes (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`) are dropped SILENTLY client-side via `BUSINESS_ALERT_CODES` whitelist in `features/alertas/constants.ts`. Cloud-side `JobSyncCloud` continues to surface them in Grafana. Set membership is O(1) `Set.has(...)` per row (REQ-OPS-182). | F11.2 |
| **ABBC-F11.2-FE-1** | REQ-OPS-178 | MED | ✅ RESOLVED | `<AlertasPanel />` mounted globally in `src/renderer/App.tsx` between `<SyncBanner />` and `<main>`. SWR polling cadence `30_000 ms` (matches F11.1 SyncBanner precedent; REQ-OPS-179 §3 + DA-F11.2-6). Gated on `branchUuid !== null` so the fetcher does not fire on `/login` / `/caja/abrir-turno` (REQ-OPS-139 lazy-mount precedent). | F11.2 |
| **ABBC-F11.2-I18N-1** | REQ-OPS-178 | LOW | ✅ RESOLVED | i18n keys added to `apps/electron-sucursal/src/renderer/i18n/locales/alertas.json`: `dashboard.{title, drillDown, markResolved, error, empty, filters.label}`, `severidad.{alta, media, baja}`, `actions.{marcarRevisada, cancelar, filtro}`, `empty.noAlerts`, `desc.{descuadre_critico, fe_error_toppoint, numeracion_toppoint_agotada, cache_desactualizado, capacidad_agotada_forzado, arqueo_sin_cerrar, caja_sin_apertura, suscripcion_proxima_vencer, reimpresion_excesiva, fallo_conexion_local, diferencia_datafono}`. en-US + pt-BR fall back via `fallbackLng: 'es-CO'` (only es-CO exists today). | F11.2 |

### Cross-fase housekeeping carries (preserved from F10.3 pending-fase-10.md)

These are unchanged from F10.3 closure (Engram #1916). Resolved at the end of Fase 11 housekeeping pass:

| ID | Description |
|---|---|
| ABBC-F10.1-BE-1 | `tolerancia_*` backend fields (Fase 13+ admin) |
| ABBC-F10.1-BE-2 | vitest coverage thresholds (housekeeping) |
| ABBC-F10.1-LINT-1 | Pre-existing lint debt (housekeeping) |
| ABBC-F10.2-LINT | Pre-existing lint debt (housekeeping) |
| ABBC-F10.2-BE-1 | Arqueo orphan reconciler (post-Fase-13) |
| ABBC-F10.3-BE-1 | `perm_arqueo_cerrar_cualquiera` JWT issuer delta (F12.x RBAC) |
| ABBC-F10.3-FE-1 | `useArqueoResumen` aggregate Zod schema reconciliation (post-F10.3) |

## 2. Spec delta follow-ups

The 2 F11.1 spec-delta follow-ups (ABBC-F11.1-SPEC-1, ABBC-F11.1-SPEC-2) are the only spec deltas required before F11.2 begins. Both are LOW severity and non-blocking. Recommended approach: bundle them into the F11.2 spec delta as a "F11.1 reconciliation" appendix at the top of the F11.2 spec, OR land them as a separate one-commit spec delta in the next housekeeping commit.

> F11.2 status: the "F11.1 reconciliation" appendix was authored at `openspec/changes/fase-11-2-alertas-panel/specs/spec.md` (last section, "F11.1 Spec-Delta Appendix (carry-overs reconciled)") per R-CARRY-1 + REQ-OPS-173 + R-F11.1-CARRY-2 — non-blocking, no conflict with F11.2.

## 3. Forward hooks

- ✅ **F11.2 (AlertasPanel)** — CLOSED 2026-09-21. 7 strict-TDD commits on `feature/hu-f11-2-alertas-panel`; merge SHA pending orchestrator merge --no-ff to `dev`.
- **F12.x (observability)** — export `apiStatusStore.consecutiveFailures` as a Prometheus gauge (forward hook from F11.1). Optionally also `openAlertsCount` from `useAlertas` (forward hook from F11.2 — derived selector pattern per F11.1 R-CARRY-1).
- **Future WebSocket sync migration (v2)** — `useSyncEstado` SWR `refreshInterval` will be removed when WS lands; derived-state selector in REQ-OPS-171 reused verbatim (forward hook from F11.1). F11.2 carries the same forward hook for `useAlertas` (REQ-OPS-179 invariant).
- **ABBC-F11.2-BE-1 (carried)** — backend delta to extend `AlertaRead` with JOIN to `prod.alert_types`. Removes R-RES-F11.2-1 stale-merge risk. Out of F11.2 scope; tracked for Fase 12+.

## 4. Resolution policy

This file resolves when:
1. ✅ F11.2 closes (archive moves to `openspec/changes/archive/2026-09-21-fase-11-2-alertas-panel/`).
2. The 2 F11.1 spec-delta follow-ups (ABBC-F11.1-SPEC-1, ABBC-F11.1-SPEC-2) are either reconciled in a future spec delta OR explicitly marked "won't fix" in a future sdd-archive report.
3. The cross-fase housekeeping carries (ABBC-F10.*) are resolved by their respective future fases.
4. ABBC-F11.2-BE-1 (backend JOIN follow-up) lands in a future fase.

At that point, replace `pending-fase-11.md` with `pending-fase-12.md` for the next fase backlog.
