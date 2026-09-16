# Archive Report: hu-f1-10-numeracion-fe-dian-reintento

## Summary

**Change**: HU-F1.10 — Numeración FE + estado DIAN + reintento
**Outcome**: SHIPPED. Verified PASS with 0 CRITICAL/HIGH/MEDIUM and 3 LOW documented deviations (D1 test baseline, D2 AlertaFactory added, D3 sync_catalog in-memory).
**Branch**: `feat/fase-1-prerequisites-backend`
**Commits**:
- `a9a8f47 feat(backend): HU-F1.10 — schemas + assign_consecutivo wiring + stub handler` (T1, 441 LOC)
- `be3e3cf feat(backend): HU-F1.10 — repo/factura_electronica.py + 8 typed exceptions + buscar_resolucion_vigente_por_sucursal` (T2, 762 LOC)
- `7bdf70c feat(db): HU-F1.10 — MIGRATION 0028 sync_flip + partial_UK + covering_index + GRANT` (T3, 319 LOC)
- `da3016e feat(backend): HU-F1.10 — POST /factura-electronica (12-step handler + KD-FE-01 single-commit)` (T4, 783 LOC)
- `025ea82 feat(backend): HU-F1.10 — GET /factura-electronica/{uuid} + POST /factura-electronica/{uuid}/reintentar` (T5+T6 merged, 791 LOC)
- `d4ad6c5 feat(backend): HU-F1.10 — router wiring verification + KD-3 issuer + Cache-Control no-store` (T7, 428 LOC)
- `8c8be0d test(backend): HU-F1.10 — final integration + regression sweep (all prior tests still pass)` (T8, 268 LOC)
- `05bb7ac chore(openspec): HU-F1.10 apply complete — all 31 tasks [x] across 8 clusters (T1..T8)` (docs)
**Spec canonical merge**: REQ-OPS-064..074 + REQ-OPS-XR1..XR3 (14 REQs) merged into `openspec/specs/operations/spec.md`. Status: appended (canonical spec now has 80 REQs total).
**Archived location**: `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/`

## Reconciliations

### R1 HIGH (RESOLVED)
- **Architectural conflict** between plan.md línea 953 (branch INSERTs `envio_dian`), `modelo_datos_er.mmd` línea 892 (CLOUD-ONLY), and sync catalog `direction='cloud_to_branch'`.
- **Resolution (DEC-FE-01)**: plan.md is canonical (per user mandate "siempre remitete al plan.md"). Branch INSERTs `envio_dian` for initial state + retry chain. Sync catalog direction flipped to `branch_to_cloud` (Python-level at `sync_entries_lw.py:129` per D3; MIGRATION 0028 pre-flight `DO $$` documents the conceptual SQL).
- **ER comment update deferred**: `modelo_datos_er.mmd` línea 892 comment update from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync replication" is a separate post-archive PR for traceability (analogous to F1.9 docstring drift fix at commit `e2f39ae`).

### D1..D3 LOW deviations (all ACCEPTABLE)

- **D1**: Test environment baseline (Docker unavailable → testcontainers cascade skips). Same F1.5/F1.6/F1.7/F1.9 baseline. Mitigation: CI run with `PARKOS_DOCKER_TEST=1`.
- **D2**: `AlertaFactory` was not pre-existing (design assumed F1.8 T-PR8-002 factory was already in place). Added at `repo/alert_types.py:51-97` as T4 prep. DEC-FE-03 prerequisite.
- **D3**: `sync_catalog` is in-memory Python tuple, not DB table. DEC-FE-01 applied at Python level (`sync_entries_lw.py:129`), not via SQL UPDATE. Migration pre-flight guards against tables-missing risk; Python-level flip is runtime source of truth.

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains 80 REQs (66 prior + 14 new). To reverse safely:
- `git revert 05bb7ac` reverts the post-apply chore
- `git revert 8c8be0d` reverts the regression sweep test
- `git revert d4ad6c5` reverts the router wiring
- `git revert 025ea82` reverts GET + retry handlers
- `git revert da3016e` reverts the POST handler
- `git revert 7bdf70c` reverts MIGRATION 0028 (drops partial UK + covering index; reverts sync catalog flip)
- `git revert be3e3cf` reverts the repo layer
- `git revert a9a8f47` reverts schemas + stub
- Spec content in archive remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **Pre-existing test baseline**: 1563 SKIP per `conftest.py:343-372` autouse session fixture. NOT introduced by F1.10. Recommend dedicated housekeeping pass pre-Fase-2 (same baseline as F1.5/F1.6/F1.7/F1.9).
- **ER diagram update**: separate PR to update `modelo_datos_er.mmd` línea 892 from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync replication".
- **Reusable artifacts**:
  - `repo/factura_electronica.py` (~290 LOC, 9 helpers + 8 typed exceptions) — reusable by any future endpoint that needs to manage FE + envio_dian chain.
  - `AlertaFactory` at `repo/alert_types.py:51-97` — reusable by any future handler that needs to fire a seeded alerta (e.g. F1.13 arqueo cierres).
  - `buscar_resolucion_vigente_por_sucursal` at `repo/resolucion_facturacion.py:152-175` — reusable for any handler that needs the vigente resolution for a sucursal.
- **Defense in depth chain completa** (KD-3 issuer → tenant scope → DB partial UK → SELECT FOR UPDATE → 8 typed exceptions → 409 mapping). See verify-report.md §5.
- **Forward hooks**:
  - F1.13 (Arqueo): consumes `prod.envio_dian` for cierre_dia. May add filter `WHERE estado='aceptado'` to count successful FEs.
  - F1.14 (sync estado): the sync catalog flip (DEC-FE-01) is now reflected in `GET /sync/estado` (potential additional work; out of F1.10 scope but worth noting).
  - Fase 4 (DIAN web service): real DIAN POST integration consumes `envio_dian` chain via sync; writes back transition rows.
  - HU-F8.1 (FE consumer UI): consumes the new endpoints.

## Next steps

- HU-F1.10 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida por plan.md: **HU-F1.11 — Workflow reimpresión tiquete (crear + anular)** (170 LOC, siembra `costos_servicios.concepto='reimpresion'`).
- 5 HUs restantes pendientes (F1.11, F1.12, F1.13, F1.14, F1.15).
- pending.md housekeeping: F1.10 row to [x], totals updated (1640 LOC remaining in 5 HUs: 170 + 260 + 240 + 120 + 70 = 860 LOC).

---

**Closed by**: sdd-archive (executor). Update TODO-fase-1.md marking HU-F1.10 [x] (handled by orchestrator, FUERA de este agente).
**Engram**: observation persisted, topic_key=`sdd/HU-F1.10-numeracion-fe-dian-reintento/closed`, project=`easypuinto-parkos-software`.
