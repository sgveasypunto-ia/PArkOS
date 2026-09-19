# Verify Report: HU-F7.1 — Búsqueda tolerante y cotización (CU-02)

> **Change**: `fase-7-1-busqueda-tolerante-cotizacion`
> **Phase**: verify (sdd-verify)
> **Status**: PENDING — to be filled by sdd-verify phase
> **Created**: 2026-09-19 (sdd-apply Commit 8 seed)

## Purpose

This document is the placeholder for the sdd-verify phase output.
After sdd-verify runs, this file will contain:

1. **Pre-merge acceptance gates** (per `proposal.md §8.4`):
   - `git diff dev..feature/hu-f7-1-...` ≤ 800 LOC (`size:exception` RATIFIED — forecast 935, actual ~937)
   - `pnpm --filter electron-sucursal lint` exits 0
   - `pnpm --filter electron-sucursal typecheck` exits 0
   - `pnpm --filter electron-sucursal test:coverage` exits 0 with all 8 per-file thresholds met (5 existing + 3 new)
   - `pnpm --filter electron-sucursal test -- --run -t "WCAG"` (axe-core on `<CotizacionPanel />`) exits 0 violations
   - `gh pr merge --squash --body-file` produces a squash commit with no `Co-authored-by` AI trailer

2. **Scenario verification** (per `specs/operations.md`):
   - REQ-OPS-143 rotación + mensualidad scenarios
   - REQ-OPS-144 `buscarIngresoTolerante` DEC-SUC-22 separation
   - REQ-OPS-145 401 logout + 5s timeout
   - REQ-OPS-146 countdown red-threshold + `aria-live`
   - REQ-OPS-147 `formatCOP` only (git grep verification)
   - REQ-OPS-148 `cotizar.errors.iva_no_configurado` graceful banner
   - REQ-OPS-149 10 tests total pass
   - REQ-OPS-150 8 per-file thresholds met
   - REQ-OPS-151 variant generation bounded

3. **Drift reconciliation traceability** (per `specs/operations.md`):
   - REQ-OPS-022 unchanged on server (consumed by client)
   - REQ-OPS-023 mensualidad short-circuit rendered
   - REQ-OPS-024 typed errors with precedence
   - REQ-OPS-132 fetcher-closure preserved

## Status

This file will be populated by the sdd-verify sub-agent after the apply phase completes successfully. The sdd-apply phase has shipped 8 commits; sdd-verify owns the final acceptance gate before merge to `dev`.
