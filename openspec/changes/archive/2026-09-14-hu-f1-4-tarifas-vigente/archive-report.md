# Archive Report: hu-f1-4-tarifas-vigente

## Summary

**Change**: HU-F1.4 — Filtro bi-temporal `vigente_en` en `GET /empresa/tarifas-sucursal`.
**Outcome**: SHIPPED.
**Branch**: `feat/fase-1-prerequisites-backend`.
**Commits**:
- `de4d2fc feat(backend): anadir filtro vigente_en en GET /empresa/tarifas-sucursal para HU-F1.4`
- `3844524 docs(openspec): HU-F1.4 — planeacion canonica del change hu-f1-4-tarifas-vigente`
**Spec canonical merge**: REQ-OPS-017..021 merged into `openspec/specs/operations/spec.md`. Status: appended.
**Archived location**: `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/`

## Reverted or not

No reverted. Shipped as-is. Cosmetic drift (proposal/design say "4 reqs", spec declares 5) reconciled via spec note in REQ-OPS-021.

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-017..021. To reverse safely: `git revert 3844524` reverts the docs commit; `git revert de4d2fc` reverts the code commit. The spec content in archive remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **Cosmetic commit message**: `de4d2fc` says "anadir" instead of "anadir". Aceptable por conventional commit, no requiere fixup.
- **Preexisting test failure (FUERA de scope)**: `tests/static/test_agents_md_no_superseded_terms.py` flaggea `plan.md:3465` por `consecutivo_actual`. NO introducido por HU-F1.4. Resolver en housekeeping separado del working tree.
- **Reusable artifact**: `bitemporal_vigente_predicate` en `repo/tarifas_vigencia.py` (~15 LOC) sera reusado desde `calcular_cotizacion` (HU-F1.8). Adelantado sin coste.
- **Spec divergence**: REQ-OPS-021 declarado aunque proposal/design decian "4 reqs". Aplicado durante implementacion por consistencia monotónica con REQ-OPS-001..016. La nota inicial en REQ-OPS-021 documenta esto para auditores.

## Next steps

- HU-F1.4 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida por plan.md: HU-F1.3 (constraint sesion unica + GET /caja-sesion/sesion/me, 110 LOC, nueva migracion 0022).
- 11 HUs restantes pendientes (F1.3, F1.5..F1.15).

---

**Closed by**: sdd-archive (executor). Update TODO-fase-1.md marking HU-F1.4 [x] (handled by orchestrator, FUERA de este agente).
**Engram**: observation persisted, topic_key=sdd/HU-F1.4/archive, project=easypuinto-parkos-software.
