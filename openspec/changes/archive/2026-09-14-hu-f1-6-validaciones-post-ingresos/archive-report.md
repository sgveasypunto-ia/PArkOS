# Archive Report: hu-f1-6-validaciones-post-ingresos

## Summary

**Change**: HU-F1.6 — Server-side validation of `POST /api/v1/operacion/ingresos` (V1..V9 + KD-FORZADO-01). 260 LOC budget per `plan.md` línea 787, became ~3,300 LOC with tests + helpers + migration + schemas.
**Outcome**: SHIPPED — verify-report initial verdict was SHIPPED WITH WARNINGS (0 CRITICAL, 0 HIGH, 3 MEDIUM deviations M1+M2+M3, 4 LOW). Archive phase resolved M1 (KD-FORZADO-01 prefix detection aligned to spec `startswith`), M2 (V8 EXISTS predicate gained `s.uuid_sucursal` + `a.estado='ejecutada' AND a.tipo_anulable IN ('ingreso','salida')`), L1 (`forzado` kwarg removed from `validar_tipo_vehiculo_vigente`), and M3 (REQ-OPS-034..041 merged into canonical `operations/spec.md`). Final state: SHIPPED with all MEDIUM deviations closed inline.
**Branch**: `feat/fase-1-prerequisites-backend`.
**Commits**:
  - `fff6350 feat(backend): HU-F1.6 — validaciones server-side POST /operacion/ingresos con KD-FORZADO-01` (código: 13 files, +2122/-9)
  - `8590e2b test(backend): HU-F1.6 — validaciones POST /operacion/ingresos — 9 archivos de tests` (tests: 9 files, +1159/-17)
  - `ff41f8c fix(backend): HU-F1.6 — alinear KD-FORZADO-01 prefix, filtros EXISTS V8 y limpiar kwarg L1` (M1+M2+L1 archive-phase fixes + regression tests: 3 files, +143/-11)
  - `<this-archive-commit> chore(openspec): archivar HU-F1.6 validaciones POST /operacion/ingresos — REQ-OPS-034..041 merged` (spec merge + folder move + archive-report.md)
**Spec canonical merge**: REQ-OPS-034..041 (8 requirements, ~23.2 KB verbatim) merged into `openspec/specs/operations/spec.md`. `## Modified Capabilities` section gains 11 F1.6 deltas (V1, V2, V3, V4, V5, V6, V8, V9, KD-FORZADO-01, KD-FORZADO-01.alerta + migration 0025 + 2 new test files). REQ-OPS-001..033 unchanged.
**Archived location**: `openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/`

## Reconciliations

**No KD letter deviations** — all 10 KDs (KD-3, KD-6, KD-7, KD-V1..V9, KD-FORZADO-01) adopted as-lettered. The 3 verify-report MEDIUM deviations (M1, M2, M3) were resolved inline during the archive phase, NOT carried into the audit trail as open gaps. The 1 LOW deviation (L1 unused `forzado` kwarg) was also resolved inline. Final state: 0 open MEDIUM, 0 open LOW deviations.

**Inline resolutions** (commit `ff41f8c`):
- **M1 — KD-FORZADO-01 prefix detection**: implementation updated from `FORZADO_PREFIX in observaciones and observaciones.rstrip().endswith("]")` to spec-compliant `observaciones.startswith(FORZADO_PREFIX)`. Motivo extraction simplified to `observaciones[len(FORZADO_PREFIX):].rstrip("]").strip()` (was `index + rindex("]")`). All 4 canonical tests + 2 T-aux + 2 new M1 regression tests pass via direct venv invocation. 2 new regression tests added to `test_operacion_ingresos_kd_forzado.py`: `prefix_mid_string_no_startswith_returns_none` (covers prefix mid-string not triggering prefix contract) + `prefix_sin_cierre_raises_contradiccion` (covers `startswith` strict contract even without closing bracket).
- **M2 — V8 EXISTS predicate filters**: implementation updated to add the 3 spec'd filters in BOTH the EXISTS query and the ID re-select query: `s.uuid_sucursal = i.uuid_sucursal` for salidas; `a.estado='ejecutada' AND a.tipo_anulable IN ('ingreso','salida')` for anulaciones. 1 new regression test added to `test_ingreso_create_db.py`: `anulacion_pendiente_no_bloquea_nuevo_ingreso` (seeds an `estado='activo'` anulacion tied to the prior ingreso and asserts new ingreso with same placa proceeds to INSERT, NOT 409).
- **L1 — unused `forzado` kwarg**: `validar_tipo_vehiculo_vigente` signature dropped `forzado: bool = False` kwarg (KD-V3 preserved: function body never consulted `forzado`); signature aligned with design.md §8.2.
- **M3 — spec delta not created during apply**: archive phase owns the merge (per F1.3/F1.5/F1.8 precedent); REQ-OPS-034..041 blocks copied verbatim from `openspec/changes/hu-f1-6-validaciones-post-ingresos/specs/operational/spec.md` into `openspec/specs/operations/spec.md` `## Requirements` section (byte-identity verified via `diff -u` returning empty).

**Design decisions D-HU-F1.6-1..13 preserved in code**:
- D-1: handler in-place modification ✓
- D-2: KD-FORZADO-01 prefix contract ✓ (M1 resolved at archive)
- D-3: no lock pesimista ✓
- D-4: regex hardcoded at module level ✓
- D-5: prefix validated against `forzado` ✓ (M1 resolved)
- D-6: server overwrites client UUID ✓
- D-7: 4-layer defense in depth ✓
- D-8: 8 helpers in `repo/ingreso.py` ✓
- D-9: alerta only on V2 bypass ✓
- D-10: 7 typed error schemas + `IngresoCreateForzado` + `IngresoReadForzado` ✓
- D-11: 11-step strict ordering ✓ (AST walk `test_kd_forzado_in_handler.py` verified 9/9 step order)
- D-12: `Idempotency-Key` header (no `correlacion_id` in body) ✓ (PR2 middleware intact)
- D-13: Both `operador-` and `admin-` can emit `forzado=true` ✓

**Mechanical move evidence** (per `skills/sdd-archive/SKILL.md` Mechanical Copy Contract):

- snapshot taken before move: `.tmp_sdd/snapshot_pre_move/` containing `exploration.md, proposal.md, design.md, tasks.md, verify-report.md, specs/operational/spec.md`
- move: `mv openspec/changes/hu-f1-6-validaciones-post-ingresos/{exploration,proposal,design,tasks,verify-report}.md openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/` + `mv .../specs/operational/spec.md .../specs/operational/spec.md` (plain `mv`; source directory was untracked — `git status` reported `??` for the change folder pre-move)
- readback: `diff -r .tmp_sdd/snapshot_pre_move openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/` returned **empty** (no differences) — passing evidence per the skill
- archive-report.md was authored at the archive location after the move (additive-only, excluded from the source/destination comparison)
- spec canonical merge (`openspec/specs/operations/spec.md`) verified byte-identical insertion of REQ-OPS-034..041 via `diff -u` returning empty

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-034..041 + Modified Capabilities bullets. To reverse safely:
- Spec merge only: `git revert <this-archive-commit>` reverts the merge into canonical spec (the archived `spec.md` still preserves the source content).
- M1+M2+L1 inline fixes: `git revert ff41f8c` drops the spec-aligned prefix detection, the 3 EXISTS filters, and the `forzado` kwarg removal (M1+M2 deviations re-appear; L1 cosmetic regression).
- Code commit (apply): `git revert 8590e2b && git revert fff6350` (in order) reverts tests + apply (drops migration 0025, handler chain, schemas, 4 NEW repo modules, repo additions, tests). Migrations: `alembic downgrade -1` removes column `datos_nuevos` + DELETE del `alert_types` row `capacidad_agotada_forzado` (superuser; alert_types_inmutable trigger no bloquea a superuser).

The archived folder remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **25 pre-existing test failures / skips**: baseline from F1.5/F1.3/F1.8 verify-reports (pg_partman missing from `postgres:16-alpine` testcontainers). NOT introduced by F1.6. CI uses `parkos-postgres:16-pgpartman` (custom image with `pg_partman` pre-installed).
- **4 pre-existing mypy errors**: same baseline (`caja_sesion.py` handlers, `session_cycle.py` `rowcount`). Housekeeping separado.
- **ruff format cosmetic drift** (verify-report §5 L2): `backend/packages/api_admin/src/api_admin_main/__init__.py` has a trailing newline drift (NOT introduced by F1.6 — verified by `git show fc72adb:...api_admin/.../__init__.py | ruff format --check --diff`). Optional `ruff format` housekeeping commit post-archive.
- **KD-IVA deployment blocker** (NOT applicable to F1.6). HU-F1.6 no depende de `impuestos.IVA` — aplica a F1.7/F1.9 que siguen bloqueadas por KD-IVA hasta siembra.
- **RIESGO-SUC-02 acceptance** (`plan.md:2677`): lag máximo `2 × refresh_interval_s` = 20s worst-case during KD-5 fallback. V2 (cupo) reads via `mv_ocupacion_diaria` (F1.5); V8 reads `prod.ingreso` directly (no MV, no lock). Documented operating characteristic.
- **Reusable artifacts** (F1.6):
  - `repo/ingreso.py::validar_kd_forzado` (3 discriminadores + module constants) reusable por F4.1 (UI confirm modal) y F7 (anulación walk-in auditado).
  - `repo/placa.py::FORMATO_AUTO` / `FORMATO_MOTO` / `detectar_tipo_vehiculo` reusable por F1.7 (`buscarIngresoTolerante`) y F4.3 (input validation cliente).
  - `repo/subscripcion_activa.py::validar_subscripcion_vigente` + `resolve_active_subscription_for_exit` reusable por F1.7 (salida flow) y F7.
  - `repo/alerta.py::insertar_alerta_forzado` reusable por F7 (anulación) y F4.1 (UI toast warning).
  - Migration 0025 — adds `prod.alerta.datos_nuevos JSONB` column + 1 alert_type. Forward-compatible: future alert types can populate `datos_nuevos` without further migration.
- **Forward hooks**:
  - F1.7 (`POST /api/v1/operacion/salidas`): replicar patrón `repo/ingreso.py` + reusar `repo/subscripcion_activa.py::resolve_active_subscription_for_exit`.
  - F1.10 (`GET /api/v1/operacion/ingresos/{uuid}`): consume `IngresoReadForzado` schema, derive `tipo_entrada` from `uuid_subscripcion_cliente` (NOT from `forzado` — V9 invariant).
  - F1.11 (`GET /api/v1/operacion/ingresos` list): paginación + filtros vigentes (no new validators).
  - F1.12 (`POST /api/v1/operacion/salidas`): reusar `validar_subscripcion_vigente` (F1.6 export).
  - F1.13 (`GET /api/v1/operacion/salidas/{uuid}`): READ-only handler.
  - F1.14 (alert types seeding): owns seeding 11 business alert_types (F1.6 added 1: `capacidad_agotada_forzado` via migration 0025).
  - F1.15 (anulación workflow): reusar `validar_kd_forzado` prefix contract for anulación bypass (`[ANULADO: <motivo ≥10 chars>]`).
- **Configurable regex** (KD-V2 deferred): `repo/placa.py` module-level constants make a future cat-tabla swap a one-file edit.
- **EXPLAIN ANALYZE** for V8 query (R8 mitigation): run on a 1M-row fixture post-archive to confirm < 50ms p99.

## Next steps

- HU-F1.6 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida por `plan.md:792` (dependencia): **HU-F1.7 — Salida vehicular con subscripción** (260 LOC, depende F1.6 cerrado + KD-IVA no aplica para flujo de salida).
- 7 HUs restantes pendientes (F1.7, F1.9 bloqueada por KD-IVA hasta siembra, F1.10, F1.11, F1.12, F1.13, F1.14, F1.15).
- `pending.md` actualizado: F1.6 marca `[~]` → `[x]`.

---

Closed by: sdd-archive (orchestrator-delegated executor). Update TODO-fase-1.md row 6 marking HU-F1.6 [x] (handled by orchestrator post-archive).
Engram: observation persisted, topic_key=`sdd/hu-f1-6-validaciones-post-ingresos/archive`, project=`easypuinto-parkos-software`.