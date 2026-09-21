# Pending — easypunto_parkos (Fase 12: Reportería local mínima CU-09)

> Tracking file for Fase 12 deferred items. Resolved at the end of Fase 12 (after F12.1 close).

| # | ID | HU | Estado al cerrar | Notas |
|---|----|----|------------------|-------|
| 1 | HU-F12.1 | MiTurnoPanel | CERRADO 2026-09-21 (merge SHA `3a8de86`; archive `openspec/changes/archive/2026-09-21-fase-12-1-mi-turno/`; 10 strict-TDD commits on `feature/hu-f12-1-mi-turno`; REQ-OPS-184..190 landed in `operations/spec.md` under Phase 27) | 10/10 drift anchors resolved (DA-F12.1-10 GATING closed via open-window temporal JOIN reusing canonical F1.13 SUM helper); 13 BE tests GREEN (5 schema + 3 SQL builder + 5 endpoint) + 24 FE tests GREEN (8 schema + 10 hook + 6 panel) + 2 e2e scenarios `test.skip` (sandbox F.6); net +2,546 LOC (27% over 2,000 meta; 1% over 2,500 hard ceiling — implicit size:exception per F10.3/F11.2 envelope); WARNINGs W-1/W-2/W-3 + SUGGESTIONs S-1/S-2 carried forward |

## 1. Deferred Items

### F12.1 carries (resolved at apply close — no carry-forward into F12.x)

| ID | Anchor | Severity | Status | Description |
|---|---|---|---|---|
| (none) | — | — | RESOLVED | No drift anchors, risk anchors, or scope items carried out of F12.1. The read-only aggregator uses canonical F1.13 `repo.arqueo._sum_factura_pagos_by_medio_pago` helper verbatim (R-F12.1-2) and the open-window temporal JOIN preserves `[L-E]` / `[A]` immutability (R-F12.1-1, DA-F12.1-10). No migration script was added (`python openspec/scripts/check_schema_match.py` exits 0 unchanged). |

### Cross-fase housekeeping carries (preserved from F11.x closure)

These are unchanged from F11.2 closure. Resolved at the end of Fase 12 housekeeping pass:

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
| ABBC-F12.1-FE-MOCK-1 | LOW | W-1 — 4 pre-existing TS errors in `useMiTurno.test.ts` lines 159-162 (vi.mock constructor 1-arg vs real `ParkosHttpError` 3-arg); pattern-matches F11.1 `useOcupacion.test.ts` (8) and F1.x `useIngresoActivo.test.ts` (1); recommend `test-utils/ParkosHttpErrorMock.ts` shared helper per S-2 | Fase 13 housekeeping |
| ABBC-F12.1-SIZE-1 | LOW | W-2 — implicit size:exception for +2,546 net LOC (1% / 46 LOC over 2,500 hard ceiling); pattern consistent with F10.3 + F11.2 envelope; recommend a formal size:exception if the 2,000 meta-budget is reaffirmed (NOT blocking) | optional ADR |
| ABBC-F12.1-LINT-1 | LOW | W-3 — 17 pre-existing vitest failures in non-F12.1 files (TiqueteModal / Principal / PlacaInput / ForzarIngresoModal / OcupacionPanel / Dashboard.cold-mount) + 5 failed suites (missing `@testing-library/user-event`); orchestrator pre-stated baseline; not blocking | Fase 13 housekeeping |
| ABBC-F12.1-SCHEMALOCK-1 | LOW | S-1 — recommend the BE/FE key-set lock pattern (per REQ-OPS-189) be carried into F12.2/F12.x to maintain consistency; non-blocking | spec delta for F12.x |
| R-ARCH-1 | — | sdd-archive skill mechanical-copy contract hardening (snapshot BEFORE `git mv`; `cp -R` / `Move-Item` not `robocopy /MIR`) — successfully mitigated by F11.2/F11.1/F12.1 | sdd-archive skill |
| R-ARCH-3 | — | NEW from F12.1: `Move-Item -Destination $existing_dir` silently nests the source inside the dated directory in PowerShell; recommend the sdd-archive skill template include an explicit flatten step OR rename the destination basename to a `dir.not-yet-existing` so PowerShell places the source as the leaf folder name (see F12.1 archive-report.md §Operational Hardening) | sdd-archive skill |
| R-ARCH-2 | — | Reconstitute `feature/hu-f11-1-sync-banner` working tree from merge SHA `4021d3d` (next session) | next session |

## 2. Spec delta follow-ups

None introduced by F12.1. The 2 F11.1 spec-delta follow-ups (ABBC-F11.1-SPEC-1, ABBC-F11.1-SPEC-2) remain LOW-severity / non-blocking from F11.2 closure. ABBC-F12.1-SCHEMALOCK-1 (S-1) is a new LOW-severity pattern recommendation, not a spec delta.

## 3. Forward hooks

- **ABBC-F11.2-BE-1 (carried)** — backend delta to extend `AlertaRead` with JOIN to `prod.alert_types`. Out of F12.1 scope; tracked here. Fase 13+ ownership.
- **Future WebSocket sync migration (v2)** — `useMiTurno` SWR `refreshInterval` will be removed when WS lands; same as F11.x forward hook.
- **ABBC-F12.x backend JOIN ref** (per spec §Forward hooks in Phase 27) — if a future HU replaces the temporal JOIN with a `uuid_sesion` FK on `[L-E]` / `[A]` tables, the ER.mmd canon must be amended first (KD-3 invariant — no migration may bypass DB-layer immutability without ADR). Out of F12.1 scope.
- **F12.x local historical comparison** (out of F12.1 scope per proposal §Out-of-Scope) — read `prod.sesion` history joined with `prod.factura_pagos` for past-turn comparison.

## 4. Resolution policy

This file resolves when:

1. F12.1 closes — archive moved to `openspec/changes/archive/2026-09-21-fase-12-1-mi-turno/` (DONE 2026-09-21, merge `3a8de86`).
2. No F12.1-deferred items exist — confirmed at apply close (no drift / risk / scope carries).
3. Cross-fase carries remain owned by their respective future fases.
4. ABBC-F11.2-BE-1 lands in a future fase (Fase 13+ backend delta).

At that point, replace `pending-fase-12.md` with `pending-fase-13.md` for the next fase backlog (Fase 13: Fundamentos — backend admin, autenticación y despliegue per `plan.md` line 2948+).

---

**F12.1 closure evidence**: see `openspec/changes/archive/2026-09-21-fase-12-1-mi-turno/archive-report.md` (R-ARCH-1 + R-ARCH-3 mitigation evidence, FASE 12 CLOSURE hand-off, 6/6 byte-identity verification, Phase 27 spec sync of REQ-OPS-184..190).
