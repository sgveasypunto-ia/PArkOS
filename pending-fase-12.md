# Pending — easypunto_parkos (Fase 12: Reportería local mínima CU-09)

> Tracking file for Fase 12 deferred items. Resolved at the end of Fase 12 (after F12.1 close).

| # | ID | HU | Estado al cerrar | Notas |
|---|----|----|------------------|-------|
| 1 | HU-F12.1 | MiTurnoPanel | ✅ CERRADO 2026-09-21 (branch `feature/hu-f12-1-mi-turno` HEAD `6c4943a`; 9 strict-TDD commits; REQ-OPS-184..190 landed in `operations/spec.md` under Phase 26) | 10/10 drift anchors resolved (DA-F12.1-1 / DA-F12.1-9 GATING closed via defense-in-depth key-set lock in BOTH pytest + vitest); 13 BE tests GREEN (5 schema + 3 SQL builder + 5 endpoint) + 24 FE tests GREEN (8 schema + 10 hook + 6 panel) + 2 e2e scenarios `test.skip` (sandbox F.6); 0 new ruff / mypy / ts-strict violations; net ~1,100 LOC under 2,000 meta-budget |

## 1. Deferred Items

### F12.1 carries (resolved at apply close — no carry-forward)

| ID | Anchor | Severity | Status | Description |
|---|---|---|---|---|
| (none) | — | — | ✅ RESOLVED | No drift anchors, risk anchors, or scope items carried out of F12.1. The read-only aggregator uses canonical F1.13 `repo.arqueo._sum_factura_pagos_by_medio_pago` helper verbatim (R-F12.1-2) and the open-window temporal JOIN preserves `[L-E]` / `[A]` immutability (R-F12.1-1, DA-F12.1-10). No migration script was added (`python openspec/scripts/check_schema_match.py` exits 0 unchanged). |

### Cross-fase housekeeping carries (preserved from F11.x closure)

These are unchanged from F11.2 closure (Engram #1942, #1943). Resolved at the end of Fase 12 housekeeping pass:

| ID | Severity | Description | Owner |
|---|---|---|---|
| ABBC-F10.1-BE-1 | — | `tolerancia_*` backend fields (Fase 13+ admin) | Fase 13+ |
| ABBC-F10.1-BE-2 | — | vitest coverage thresholds (housekeeping) | housekeeping |
| ABBC-F10.1-LINT-1 | — | Pre-existing lint debt (housekeeping) | housekeeping |
| ABBC-F10.2-LINT | — | Pre-existing lint debt (housekeeping) | housekeeping |
| ABBC-F10.2-BE-1 | — | Arqueo orphan reconciler (post-Fase-13) | Fase 13+ |
| ABBC-F10.3-BE-1 | — | `perm_arqueo_cerrar_cualquiera` JWT issuer delta (F12.x RBAC) | Fase 12+ RBAC |
| ABBC-F10.3-FE-1 | — | `useArqueoResumen` aggregate Zod schema reconciliation (post-F10.3) | post-F12 |
| ABBC-F11.1-SPEC-1 | LOW | REQ-OPS-171 thresholds drift (spec prose 300/3600 vs impl 60/3600); non-blocking | spec delta |
| ABBC-F11.1-SPEC-2 | LOW | REQ-OPS-173 letter drift (`apiStatusStore` shape); non-blocking | spec delta |
| ABBC-F11.2-BE-1 | HIGH | Backend `AlertaRead` lacks JOIN to `prod.alert_types` (severidad / descripcion / mensaje); F11.2 ships client-side merge; backend delta carries | Fase 12+ backend |
| R-ARCH-1 | — | sdd-archive skill mechanical-copy contract hardening (snapshot BEFORE `git mv`; `cp -R` not `robocopy /MIR`) | sdd-archive skill |
| R-ARCH-2 | — | Reconstitute `feature/hu-f11-1-sync-banner` working tree from merge SHA `4021d3d` (next session) | next session |

## 2. Spec delta follow-ups

None introduced by F12.1. The 2 F11.1 spec-delta follow-ups (ABBC-F11.1-SPEC-1, ABBC-F11.1-SPEC-2) remain LOW-severity / non-blocking from F11.2 closure.

## 3. Forward hooks

- **F12.x next (mi-turno historical comparison / multi-turn)** — out of F12.1 scope per proposal §Out-of-Scope. A future HU could read `prod.sesion` history joined with `prod.factura_pagos` for past-turn comparison.
- **ABBC-F11.2-BE-1 (carried)** — backend delta to extend `AlertaRead` with JOIN to `prod.alert_types`. Out of F12.1 scope; tracked here.
- **Future WebSocket sync migration (v2)** — `useMiTurno` SWR `refreshInterval` will be removed when WS lands; same as F11.x forward hook.

## 4. Resolution policy

This file resolves when:

1. ✅ F12.1 closes (archive moves to `openspec/changes/archive/2026-09-21-fase-12-1-mi-turno/`).
2. No F12.1-deferred items exist (clean closure).
3. Cross-fase carries remain owned by their respective future fases.
4. ABBC-F11.2-BE-1 lands in a future fase (F12.x backend delta).

At that point, replace `pending-fase-12.md` with `pending-fase-13.md` for the next fase backlog.

---

**F12.1 closure evidence**: see `openspec/changes/fase-12-1-mi-turno/apply-progress.md` (TDD cycle evidence + drift-anchor coverage matrix + commit SHAs).