# Pending — easypunto_parkos (Fase 11: Estado de sincronización y alertas operativas CU-07/CU-14)

> Tracking file for Fase 11 deferred items. Resolved at the end of Fase 11 (after F11.1 + F11.2 close).

| # | ID | HU | Estado al abrir | Notas |
|---|----|----|----------------|-------|
| 1 | HU-F11.1 | SyncBanner | ✅ CERRADO 2026-09-21 (merge `4021d3d`, archive `2026-09-21`, REQ-OPS-170..176 landed; 2 spec-delta follow-ups below) | 8/8 drift anchors resolved; 21/21 unit tests GREEN; 0 CRITICAL / 0 WARNING / 2 SUGGESTION; +1,312 net LOC under 2,000 meta-budget |
| 2 | HU-F11.2 | AlertasPanel | pendiente (depends on `apiStatusStore` from F11.1) | 11 business alerts visible, 8 technical hidden (ABIERTO-06); DEC-SUC-25 append-only "marcar revisada" pattern; REQ-OPS-177+ next free spec gap |

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

### F11.2 deferred items (planned for the next SDD cycle)

| ID | Anchor | Severity | Description | Owner |
|---|---|---|---|---|
| **ABBC-F11.2-BE-1** | (planned) | LOW | Backend `alerta` table API endpoints (`GET /alertas?uuid_sucursal=...` + `POST /alertas/{uuid}/revisada`) — confirm schema supports append-only "marcar revisada" via DEC-SUC-25 (no UPDATE/DELETE on the row). | F11.2 sdd-design |
| **ABBC-F11.2-BE-2** | (planned) | MED | 8 technical alerts (`hash_chain_anomaly`, `dian_rechazada`, etc.) — confirm they are NOT surfaced in the FE AlertasPanel per ABIERTO-06 (only logged via `alerta` table; BE rotates them after N days). | F11.2 sdd-design |
| **ABBC-F11.2-FE-1** | (planned) | MED | `AlertasPanel` mount point + lifecycle (when does it poll? on what cadence? mount/unmount on route change?). Reuse `apiStatusStore` from F11.1 to suppress alert rendering while `consecutiveFailures >= 3`. | F11.2 sdd-design |
| **ABBC-F11.2-I18N-1** | (planned) | LOW | New locale keys `alertasPanel.*` in `apps/electron-sucursal/src/renderer/i18n/locales/sync.json` (or new `alertas.json`). Distinct from F11.1 `syncBanner.*` / `localApiDownBanner.*` keys per DA-F11.1-6 spirit. | F11.2 sdd-design |

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

## 3. Forward hooks

- **F11.2 (AlertasPanel)** — launch `sdd-propose` with `change=fase-11-2-alertas-panel` after the housekeeping commit for F11.1 lands on `dev`. Substrate carries (`apiStatusStore`, `useSyncEstado` SWR pattern, `App.tsx` mount slot).
- **F12.x (observability)** — export `apiStatusStore.consecutiveFailures` as a Prometheus gauge (forward hook from F11.1).
- **Future WebSocket sync migration (v2)** — `useSyncEstado` SWR `refreshInterval` will be removed when WS lands; derived-state selector in REQ-OPS-171 reused verbatim (forward hook from F11.1).

## 4. Resolution policy

This file resolves when:
1. F11.2 closes (archive moves to `openspec/changes/archive/2026-MM-DD-fase-11-2-alertas-panel/`).
2. The 2 F11.1 spec-delta follow-ups (ABBC-F11.1-SPEC-1, ABBC-F11.1-SPEC-2) are either reconciled in a future spec delta OR explicitly marked "won't fix" in a future sdd-archive report.
3. The cross-fase housekeeping carries (ABBC-F10.*) are resolved by their respective future fases.

At that point, replace `pending-fase-11.md` with `pending-fase-12.md` for the next fase backlog.