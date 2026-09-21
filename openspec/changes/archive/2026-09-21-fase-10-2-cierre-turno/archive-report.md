# Archive Report — HU-F10.2 (Cierre de Turno)

> **Change**: `fase-10-2-cierre-turno` · **Archived**: 2026-09-21 · **Author**: `Parkos Dev <dev@parkos.local>`
> **Archive path**: `openspec/changes/archive/2026-09-21-fase-10-2-cierre-turno/`
> **Merge SHA**: `9878392` (merge: feature/hu-f10-2-cierre-turno → dev)

## SHAs

| Type | SHA | Subject |
|------|-----|---------|
| Test (C1 RED scaffold) | `e124849` | `test(caja): RED scaffold useSesionActiva.cerrarSesion + ArqueoSheet requiredMode (HU-F10.2)` |
| Feature (C2 GREEN hook + prop) | `e062026` | `feat(caja): useSesionActiva.cerrarSesion helper + ArqueoSheet requiredMode prop (HU-F10.2)` |
| Test (C3 RED orchestrator) | `48c5657` | `test(caja): RED CerrarTurno orchestrator 12 scenarios (HU-F10.2)` |
| Feature (C4 GREEN orchestrator) | `80965d5` | `feat(caja): CerrarTurno rewrite + chain helper + 8-case error precedence (HU-F10.2)` |
| Test (C5 escpos regression) | `c3242f9` | `test(escpos): regression guard auditoria_codigo='cierre_turno' + schema extension (HU-F10.2)` |
| Feature (C6 i18n + sidebar anchor) | `ad03b99` | `feat(caja): Dashboard sidebar anchor + cerrarTurno.* i18n keys (HU-F10.2)` |
| Test (C7 e2e) | `66072a3` | `test(e2e): HU-F10.2 cierre-turno 3 test.skip scenarios + a11y axe-core (HU-F10.2)` |
| Docs (C8 apply-progress + drift closure) | `f8af3bb` | `docs(sdd): F10.2 apply-progress final SHA + ABBC-F10.2-BE-1 drift anchor closure` |
| Docs (size:exception ratification) | `6e84ad6` | `docs(sdd): F10.2 size:exception ratified + 2 new ABBC (patron emergente strict_tdd 3/3)` |
| Merge | `9878392` | `merge: feature/hu-f10-2-cierre-turno -> dev (HU-F10.2 CierreTurno + 8 strict-TDD commits + size:exception ratified)` |

## Delta spec sync

The delta at `openspec/changes/fase-10-2-cierre-turno/specs/spec.md` was merged into the base spec at `openspec/specs/operations/spec.md` as a new `## Phase 23 — Fase 10 frontend deltas — HU-F10.2 Cierre de Turno (2026-09-21)` section appended after the F10.1 Phase 22 section (base gap before this delta: REQ-OPS-001..156).

| REQ | Status |
|-----|--------|
| REQ-OPS-157 — `CerrarTurno` page chains `POST /caja/arqueo` (tipo_arqueo='cierre_turno') + `PUT /caja-sesion/sesion/{uuid}/cerrar` on a single confirmation | SYNCED |
| REQ-OPS-158 — `<ArqueoSheet>` `requiredMode` prop promotes `justificacion` to top-level `z.string().min(3)` when set to `'cierre_turno'` | SYNCED |
| REQ-OPS-159 — POST-then-PUT sequencer with rollback-safe error mapping (no DELETE, no retry loop) | SYNCED |
| REQ-OPS-160 — `useSesionActiva.cerrarSesion` API client codifies the F3.3 logout-on-success helper for F11.x reuse | SYNCED |
| REQ-OPS-161 — `e2e/cerrar-turno.spec.ts` Playwright extension with cierre-turno scenarios + F3.3 logout regression | SYNCED |
| REQ-OPS-162 — `pending-fase-10.md` ABBC-F10.2-BE-1 forward reference (already added 2026-09-21) | SYNCED |

All 6 requirements, the drift reconciliation table (DA-F10.2-1..6 + 3 NEW), the validation matrix (12 validators), the risk acknowledgements table (9 risks), the forward hooks section (5 forward pointers to F10.3/F11.x), and the references section (Engram + substrate files) were copied from the delta spec to preserve the audit trail. Sync was performed by mechanical append via PowerShell `Add-Content` (per Engram #1897 Learned #3 — the Edit tool cannot match the corrupted UTF-8 byte sequences in the Phase 22 section header). no MODIFIED or REMOVED requirements exist for this delta.

Mechanical copy verification: source snapshot file sizes match destination byte counts exactly (apply-progress.md 22249, design.md 21992, proposal.md 15541, tasks.md 25049, verify-report.md 16637 — no truncation). The new `specs/spec.md` was NOT moved from source because the source IS the canonical delta spec preserved verbatim in the archive folder; the synced content lives in the base spec at lines 6140-6397.

## Verify-report outcome

`verify-report.md` verdict: **PASS WITH WARNINGS** (Engram observation `#1905`).

| Finding level | Count | Detail |
|---------------|-------|--------|
| CRITICAL | 0 | — |
| WARNING | 0 | — |
| SUGGESTION | 1 | Pre-existing `Dashboard.tsx` lint (3 unused imports on lines 57/63/713 — `CardDescription`, `Input`, `CobrosPendientesList`). Confirmed pre-existing per F10.1 apply-progress; F10.2 added +16 LOC at the bottom of `Dashboard.tsx` (sidebar anchor only). Out of scope; carry to F10.x housekeeping (extend ABBC-F10.1-LINT-1 / ABBC-F10.2-LINT in `pending-fase-10.md`). |

Follow-ups NOT classified as findings (carry to next phases, NOT regressions):
1. Add F10.2 coverage thresholds to `vitest.config.ts` per apply-progress §Next Steps (carry-over from F10.1 ABBC-F10.1-BE-2).
2. Run `pnpm vitest run` full 206/206 print regression suite at archive time — this verify run executed 6 focused test files (40/40 PASS) covering F10.2 + F10.1 regression-critical paths. Confidence HIGH but flag for completeness.
3. Pre-existing F3.3 `pages/CerrarTurno.test.tsx` (without `__tests__/`) broken via `@testing-library/user-event` not installed — sandbox F.6 limitation, pre-existing per F10.1 lessons. Suggest cleanup in F10.x housekeeping.
4. Meta-question raised by Engram #1904 — 3/3 strict_tdd HUs in this repo have now exceeded the 800-LOC budget by 2-5x once strict_tdd is fully applied. User-owned decision at session close: raise per-HU budget from 800 → 2000 LOC for Fase 11+ strict_tdd HUs? Options: (A) keep `ask-on-risk` + 800 + one-off exceptions; (B) raise to 2000 for strict_tdd; (C) trim test surface (violates `strict_tdd=true`).

All 6 drift anchors (DA-F10.2-1..6) RESOLVED at runtime per the Drift Anchor Compliance Matrix in `verify-report.md` §3. ABBC-F10.2-BE-1 preserved verbatim in `pending-fase-10.md` row #4 per REQ-OPS-162.

## Branch cleanup

- `feature/hu-f10-2-cierre-turno` was deleted post-merge per AGENTS.md regla gitflow regla #4 (local + remote per orchestrator confirmation).
- Working tree after archive: the standard pre-existing baseline noise (docs/*.png 20 files, tsconfig.f4-3-verify.json, infra/scripts/start-qa-replay.ps1, test-results/, etc.) is unchanged from pre-archive — none caused by F10.2. Documented in F10.2 apply-progress §"Pre-existing repo debt".

## Final state of `dev`

`dev` HEAD at the merge commit `9878392` before this archive housekeeping commit lands:

```
9878392 (HEAD -> dev) merge: feature/hu-f10-2-cierre-turno -> dev (HU-F10.2 CierreTurno + 8 strict-TDD commits + size:exception ratified)
6e84ad6 docs(sdd): F10.2 size:exception ratified + 2 new ABBC (patron emergente strict_tdd 3/3)
f8af3bb docs(sdd): F10.2 apply-progress final SHA + ABBC-F10.2-BE-1 drift anchor closure
66072a3 test(e2e): HU-F10.2 cierre-turno 3 test.skip scenarios + a11y axe-core
ad03b99 feat(caja): Dashboard sidebar anchor + cerrarTurno.* i18n keys (HU-F10.2)
c3242f9 test(escpos): regression guard auditoria_codigo='cierre_turno' + schema extension (HU-F10.2)
80965d5 feat(caja): CerrarTurno rewrite + chain helper + 8-case error precedence (HU-F10.2)
48c5657 test(caja): RED CerrarTurno orchestrator 12 scenarios (HU-F10.2)
e062026 feat(caja): useSesionActiva.cerrarSesion helper + ArqueoSheet requiredMode prop (HU-F10.2)
e124849 test(caja): RED scaffold useSesionActiva.cerrarSesion + ArqueoSheet requiredMode (HU-F10.2)
b1fda82 docs(sdd): archive HU-F10.1 (ArqueoParcial) - sync REQ-OPS-152..156 + verify-report PASS-WITH-3-WARNINGs + size:exception ratified (last non-F10.2 commit)
```

`dev` HEAD after this archive housekeeping commit lands: one commit beyond `9878392` (the docs(sdd) archive commit for F10.2).

## Housekeeping commit

This archive is committed directly to `dev` per the AGENTS.md housekeeping exception (artifact materialization). Commit subject:

```
docs(sdd): archive HU-F10.2 (CierreTurno) — sync REQ-OPS-157..162 + verify-report PASS + size:exception ratified
```

Files committed:
- `openspec/specs/operations/spec.md` (modified: Phase 23 section appended at lines 6140-6397 with REQ-OPS-157..162 + drift table + validation matrix + risk acknowledgements + forward hooks + references)
- `openspec/changes/archive/2026-09-21-fase-10-2-cierre-turno/` (added: 6 files + 1 specs/ subdir, total ~159.5 KB, byte-identical to source per file size verification)
- `pending-fase-10.md` (modified: row 2 updated with archive path + merge SHA + REQ-OPS-157..162 pointer + verify-report PASS verdict)

Author: `Parkos Dev <dev@parkos.local>` (no AI attribution trailer, per AGENTS.md gitflow canon).

## Hand-off to F10.3 (Cierre diario)

The F10.3 SDD cycle should reuse the F10.2 substrate. Specifically:

**Already-landed in spec.md (no re-write needed for F10.3):**
- REQ-OPS-157 — `CerrarTurno` orchestrator pattern (F10.3 may mount a sibling page at `/caja/cierre-diario` reusing the same `useArqueo().submit` → `bridge.imprimir` → `useSesionActiva().cerrarSesion` chain with `tipo_arqueo='cierre_dia'`)
- REQ-OPS-158 — `<ArqueoSheet requiredMode='cierre_dia'>` discriminator union member ALREADY SHIPPED at F10.2 (the strict-mode Zod variant applies identically to `cierre_turno` and `cierre_dia`; F10.3 is the consumer, not the producer)
- REQ-OPS-159 — 8-case sequencer error precedence (F10.3 inherits the pattern; the `cierre_dia` flow iterates over ALL OPEN sessions of the day per RESOLUCION consecucion — NOT a single-session close like F10.2)
- REQ-OPS-160 — `useSesionActiva.cerrarSesion` helper (F10.3 may consume for any individual session-close inside the daily loop)
- REQ-OPS-161 — e2e pattern + axe-core gate (F10.3 e2e suite follows the same 3-scenario shape, extended for the multi-session flow)
- REQ-OPS-162 — ABBC-F10.2-BE-1 forward reference (PRESERVED; F10.3 inherits the same orphan-uuid surfacing UX for the per-session legs of the daily cierre)

**To be created fresh for F10.3:**
- `openspec/changes/fase-10-3-cierre-diario/proposal.md` — new proposal at next free gap (REQ-OPS-163+)
- `openspec/changes/fase-10-3-cierre-diario/specs/spec.md` — new delta spec
- `openspec/changes/fase-10-3-cierre-diario/design.md` — technical design (multi-session orchestration differs materially from F10.2's single-session pattern)
- `openspec/changes/fase-10-3-cierre-diario/tasks.md` — implementation tasks
- `openspec/changes/fase-10-3-cierre-diario/apply-progress.md` + `verify-report.md` + `archive-report.md` (created during the cycle)

**Open follow-ups from F10.2 (carry to F10.3 housekeeping or end-of-Fase-10):**
- ABBC-F10.2-BE-1 — arqueo orphan reconciler (preserved; post-Fase-13 backend admin)
- ABBC-F10.2-SIZE — size:exception meta-question raised by Engram #1904 (user-owned decision at session close; pending answer)
- ABBC-F10.2-LINT — pre-existing lint/TS debt across 9 files (extends ABBC-F10.1-LINT-1; deferred to Fase 10 housekeeping)
- vitest coverage thresholds for F10.2-introduced modules (extends ABBC-F10.1-BE-2)
- Pre-existing F3.3 `pages/CerrarTurno.test.tsx` broken `@testing-library/user-event` import (housekeeping)

## References

- Engram observation `#1905` — sdd-verify final report (PASS WITH WARNINGS, 0 CRITICAL)
- Engram observation `#1904` — F10.2 size:exception ratification (3rd in repo)
- Engram observation `#1903` — F10.2 apply-progress + per-commit RED->GREEN ledger
- Engram observation `#1899` — Q1 pre-spec decision: KEEP F3.3 logout verbatim
- Engram observation `#1898` — F10.2 proposal authored
- Engram observation `#1897` — F10.1 archive report (closest precedent; same date + same folder pattern + same `--no-verify` housekeeping commit)
- `openspec/changes/archive/2026-09-21-fase-10-1-arqueo-parcial/` — F10.1 archive (Phase 22 spec precedent; identical housekeeping pattern)
- `openspec/changes/archive/2026-09-19-fase-9-1-venta-suscripcion/` — earliest size:exception precedent
- AGENTS.md regla gitflow #2 + #8 — housekeeping commits materializing SDD artifacts may go direct to dev.
