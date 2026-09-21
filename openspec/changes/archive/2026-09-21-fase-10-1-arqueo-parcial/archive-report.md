# Archive Report — HU-F10.1 (Arqueo Parcial)

> **Change**: `fase-10-1-arqueo-parcial` · **Archived**: 2026-09-21 · **Author**: `Parkos Dev <dev@parkos.local>`
> **Archive path**: `openspec/changes/archive/2026-09-21-fase-10-1-arqueo-parcial/`
> **Merge SHA**: `033f654` (merge: feature/hu-f10-1-arqueo-parcial → dev)

## SHAs

| Type | SHA | Subject |
|------|-----|---------|
| Test (T1 RED→GREEN pair) | `3525544` | `test(caja): ArqueoParcial + ArqueoSheet + useArqueo test scaffold` |
| Feature (T1 feat) | `cf128f8` | `feat(caja): ArqueoParcial routed page + ArqueoSheet wiring + useArqueo rename` |
| Feature (T2 feat) | `9669673` | `feat(print): arqueo dispatcher key + ArqueoPayloadSchema + buildArqueoBody` |
| Feature (T2 feat cont.) | `3d00c5b` | `feat(caja): ArqueoSheet Zod refinement + warning alert + formatCOP reuse` |
| Test (T2 RED→GREEN) | `c1932f6` | `test(caja): ArqueoSheet Zod refinement tests + live diferencia alert tests` |
| Docs (T3 apply-progress SHA log) | `262a238` | `docs(sdd): F10.1 apply-progress final SHA + drift anchor rollback log` |
| Test (T4 e2e scaffold) | `b5264b5` | `test(caja): useArqueo.test.ts ESLint cleanup` |
| Apply doc | `dc16578` | `docs(sdd): F10.1 apply-progress SHAs + ESLint cleanup note` |
| Pending doc | `fac0063` | `docs(sdd): pending-fase-10.md housekeeping for Fase 10 (HU-F10.1)` |
| Merge | `033f654` | `merge: feature/hu-f10-1-arqueo-parcial → dev (HU-F10.1 ArqueoParcial + 8 strict-TDD commits + size:exception)` |

## Delta spec sync

The delta at `openspec/changes/fase-10-1-arqueo-parcial/specs/spec.md` was merged into the base spec at `openspec/specs/operations/spec.md` as a new `## Phase 22 — Fase 10 frontend deltas — HU-F10.1 Arqueo Parcial (2026-09-21)` section appended after REQ-OPS-151.

| REQ | Status |
|-----|--------|
| REQ-OPS-152 — `<ArqueoParcial>` routed page wraps `<ArqueoSheet>` + `useArqueo` SWR at `/caja/arqueo-parcial` | SYNCED |
| REQ-OPS-153 — `useArqueo.submit` payload field naming aligned to REQ-OPS-091 backend contract | SYNCED |
| REQ-OPS-154 — `justificacion` Zod refinement required when `|diferencia|>0` | SYNCED |
| REQ-OPS-155 — `'arqueo'` ESC/POS dispatcher key added to `TiqueteTipo` union | SYNCED |
| REQ-OPS-156 — `e2e/arqueo.spec.ts` Playwright 3-scenario end-to-end coverage | SYNCED |

All 5 requirements, the drift-reconciliation table (DA-1..DA-7), the validation matrix (8 validators), the risk acknowledgements table (7 risks), and the references section were copied verbatim from the delta spec to preserve the audit trail. Sync was performed by appending the new Phase 22 section to the existing spec; no MODIFIED or REMOVED requirements exist for this delta.

## Verify-report outcome

`verify-report.md` verdict: **PASS WITH WARNINGS** (Engram observation `#1895`).

The 3 WARNINGs are pre-existing or carried-and-documented in `pending-fase-10.md` and are NOT regressions from F10.1:

1. **ABBC-F10.1-LINT-1** — Pre-existing ESLint debt in `Dashboard.tsx` lines 57/63/697 (`CardDescription`, `Input`, `CobrosPendientesList` unused). Already tracked in `pending-fase-10.md` §2.
2. **Pre-existing vitest failures** — 17 failures across 11 files, all NOT touched by F10.1 (`@testing-library/user-event` resolution + Dashboard cold-mount spy issues — sandbox F.6 npm-install limitation).
3. **ABBC-F10.1-BE-1** — Backend `GET /caja/arqueo/resumen` does NOT expose `tolerancia_efectivo`/`tolerancia_datafono`. FE uses sensible defaults 1_000/500 COP. Already tracked in `pending-fase-10.md` §2.

3 SUGGESTIONs also recorded: `coverage.thresholds` CI gate (ABBC-F10.1-BE-2), working-tree cleanup (Fase 7 archive leftovers + `test-results/`), and a roundtrip CI integration test (F10.2/F10.3 forward hook). All three are non-blocking hardening items.

## Branch cleanup

- `feature/hu-f10-1-arqueo-parcial` was deleted post-merge per AGENTS.md regla gitflow regla #4.
- Working tree after archive: only `apps/electron-sucursal/test-results/` (gitignored) and 4 untracked stale files in `openspec/changes/archive/2026-09-19-fase-7-{1,2}/` remain — all pre-existing carry-overs documented in `pending-fase-10.md` §3 and Fase 10 closure housekeeping.

## Final state of `dev`

`dev` HEAD at the merge commit `033f654` after this housekeeping commit lands:

```
033f654 (HEAD -> dev) merge: feature/hu-f10-1-arqueo-parcial → dev
fac0063 docs(sdd): pending-fase-10.md housekeeping for Fase 10 (HU-F10.1)
dc16578 docs(sdd): F10.1 apply-progress SHAs + ESLint cleanup note (HU-F10.1)
b5264b5 test(caja): useArqueo.test.ts ESLint cleanup (HU-F10.1 follow-up)
262a238 docs(sdd): F10.1 apply-progress final SHA + drift anchor rollback log
c1932f6 test(caja): ArqueoSheet Zod refinement + alert + formatCOP coverage
3d00c5b feat(caja): ArqueoSheet Zod refinement + warning alert + formatCOP
9669673 feat(print): arqueo dispatcher key + ArqueoPayloadSchema + buildArqueoBody
cf128f8 feat(caja): ArqueoParcial routed page + ArqueoSheet wiring + useArqueo rename
3525544 test(caja): ArqueoParcial + ArqueoSheet + useArqueo test scaffold (RED)
9d30bef ... (prior F9.2 merge — last non-F10.1 commit on dev)
```

## Housekeeping commit

This archive is committed directly to `dev` per the AGENTS.md housekeeping exception (artifact materialization). Commit subject:

```
docs(sdd): archive HU-F10.1 (ArqueoParcial) — sync REQ-OPS-152..156 + verify-report PASS-WITH-3-WARNINGs + size:exception ratified
```

Files committed:
- `openspec/specs/operations/spec.md` (modified: +151 lines, REQ-OPS-152..156 + drift/validation/risk/references tables)
- `openspec/changes/archive/2026-09-21-fase-10-1-arqueo-parcial/` (added: 6 files + 1 specs/ subdir)
- `pending-fase-10.md` (modified: row 1 updated with archive path + merge SHA + REQ-OPS-152..156 pointer)

Author: `Parkos Dev <dev@parkos.local>` (no AI attribution trailer).

## Hand-off to F10.2 (Cierre de turno)

The F10.2 SDD cycle should reuse the F10.1 foundation. Specifically:

**Already-landed in spec.md (no re-write needed for F10.2):**
- REQ-OPS-152 — `<ArqueoParcial>` routed page pattern (F10.2 may mount a sibling page at `/caja/cerrar-turno` reusing the same component tree)
- REQ-OPS-153 — `useArqueo.submit` payload contract (F10.2 calls `submit({ tipo_arqueo: 'cierre_turno', ... })` with same renamed keys)
- REQ-OPS-154 — `justificacion` Zod refinement (F10.2 requires `justificacion` per REQ-OPS-094 when `diferencia != 0` AND `tipo_arqueo = 'cierre_turno'`)
- REQ-OPS-155 — `'arqueo'` ESC/POS dispatcher (F10.2 may reuse the same dispatcher key for the cierre turno print, OR introduce a new `'cierre_turno'` key — to be decided at F10.2 proposal time)
- REQ-OPS-156 — e2e pattern + axe-core gate (F10.2 e2e suite follows the same 3-scenario shape)

**To be created fresh for F10.2:**
- `openspec/changes/fase-10-2-cierre-turno/proposal.md` — new proposal
- `openspec/changes/fase-10-2-cierre-turno/specs/spec.md` — new delta spec at next free gap (REQ-OPS-157..) for the F10.2-specific surface
- `openspec/changes/fase-10-2-cierre-turno/design.md` — technical design
- `openspec/changes/fase-10-2-cierre-turno/tasks.md` — implementation tasks
- `openspec/changes/fase-10-2-cierre-turno/apply-progress.md` + `verify-report.md` + `archive-report.md` (created during the cycle)

**Open follow-ups from F10.1 (carry to F10.2 housekeeping):**
- ABBC-F10.1-BE-1 — backend `GET /caja/arqueo/resumen` tolerance fields (Fase 13+ or as standalone)
- ABBC-F10.1-BE-2 — vitest coverage thresholds for F10.1-introduced modules
- ABBC-F10.1-LINT-1 — pre-existing `Dashboard.tsx` lint cleanup

## References

- Engram observation `#1895` — sdd-verify final report (PASS WITH WARNINGS)
- Engram observation `#1896` — sdd-verify session summary
- Engram observation `#1894` — F10.1 size:exception ratification
- Engram observation `#1893` — sdd-apply session summary
- `openspec/changes/archive/2026-09-19-fase-9-1-venta-suscripcion/` — closest archive precedent (size:exception + PENDING-fase-9 + features). F10.1 follows same shape.
- AGENTS.md regla gitflow #8 — housekeeping commits materializing SDD artifacts may go direct to dev.