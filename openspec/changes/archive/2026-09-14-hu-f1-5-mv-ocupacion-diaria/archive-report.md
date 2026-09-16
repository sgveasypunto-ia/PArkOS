# Archive Report: hu-f1-5-mv-ocupacion-diaria

## Summary

**Change**: HU-F1.5 — Materialized view `prod.mv_ocupacion_diaria` + endpoint `GET /api/v1/operacion/ocupacion` + `RefreshMvOcupacionWorker` with KD-5 fallback.
**Outcome**: SHIPPED. Verified PASS with 0 CRITICAL/HIGH/MEDIUM and 3 LOW (pre-existing baseline). 1 deliberate deviation D-F1.5-1 (KD-6-respecting repo SQL refactor, PASS).
**Branch**: `feat/fase-1-prerequisites-backend`.
**Commits**:
  - `bb99e18 feat(backend): HU-F1.5 — mv_ocupacion_diaria, worker REFRESH y endpoint GET /operacion/ocupacion` (codigo: 10 files, +2290/-1)
  - `<this-archive-commit> chore(openspec): archivar HU-F1.5 mv_ocupacion_diaria + endpoint /operacion/ocupacion (spec delta + change a archive + archive-report.md)`
**Spec canonical merge**: REQ-OPS-030..033 merged into `openspec/specs/operations/spec.md`. Status: appended.
**Archived location**: `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/`

## Reconciliations

One deliberate deviation **D-F1.5-1**: repo helper SQL drives from `prod.tipos_vehiculo tv LEFT JOIN prod.cantidad_vehiculos_sucursal cvs LEFT JOIN prod.mv_ocupacion_diaria mv` (not `mv LEFT JOIN tipos_vehiculo` as the design §8 skeleton proposed) — KD-6-respecting improvement that surfaces every configured `tipos_vehiculo` even when `activos == 0` (F4.3 `OcupacionStrip` empty-state UX renders "Auto: 0/50" for fresh branches instead of being absent). Documented in source docstring at `repo/ocupacion.py::get_ocupacion_puros_activos`. No REQ-OPS-NNN letter deviation. PASS.

**Mechanical move evidence** (per `skills/sdd-archive/SKILL.md` Mechanical Copy Contract):

- snapshot taken before move: `/tmp/sdd-archive-f15.4xXEYu/source/` containing `design.md, exploration.md, proposal.md, specs/operational/spec.md, tasks.md, verify-report.md`
- move: `mv openspec/changes/hu-f1-5-mv-ocupacion-diaria openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/` (plain `mv`; `git mv` failed because the source directory was untracked — `git status` reported `?? openspec/changes/hu-f1-5-mv-ocupacion-diaria/`)
- readback: `diff -r /tmp/sdd-archive-f15.4xXEYu/source/ openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/` returned **empty** (no differences) — passing evidence per the skill
- archive-report.md was authored at the archive location after the move (additive-only, excluded from the source/destination comparison)

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-030..033 + Modified Capabilities bullets. To reverse safely: `git revert <this-archive-commit>` reverts the merge; `git revert bb99e18` reverts the code commit (drops migration 0024, worker, endpoint, schemas, repo helper, tests). The spec content in archive remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **25 pre-existing test failures / skips**: baseline from F1.8/F1.3 verify-reports. NOT introduced by F1.5. Recommended housekeeping pre-Fase-2.
- **4 pre-existing mypy errors**: same baseline (`caja_sesion.py` handlers lines 79/134/163, `session_cycle.py` line 344 `rowcount`). Housekeeping separado.
- **ruff format cosmetic drift** (§5 L2 verify-report): 9 files reformattable (long f-string continuations only). Implementation files clean. Recommend optional `ruff format` housekeeping commit post-archive.
- **KD-IVA deployment blocker** (NOT applicable to F1.5). HU-F1.5 no depende de `impuestos.IVA` — Aplica a F1.7/F1.9 que siguen bloqueadas.
- **KD-1 operational**: NSSM service `refresh_mv_ocupacion` installation owned by `infra/`.
- **Reusable artifacts**: `get_ocupacion_puros_activos` (128 LOC, bind-param types, `tipos_vehiculo` LEFT JOIN pattern) reusable por F1.6 (cupo validation) y F4.3 (OcupacionStrip consumption).
- **Defense in depth chain documented** (9 layers): pre-flight `DO $$` + `UNIQUE INDEX CONCURRENTLY` + repo typed error + AST walk + `worker_base_intact` + `factory_intact` + `__init__.py_intact` + KD-5 fallback + bind params.
- **RIESGO-SUC-02 acceptance** (`plan.md:2677`): lag máximo `2 × refresh_interval_s` = 20s worst-case during KD-5 fallback. Documented operating characteristic.
- **Forward hooks**:
  - F1.6 (`POST /operacion/ingresos` validations): replicar patrón LEFT JOIN MV + KD-FORZADO prefix validation.
  - F4.3 (frontend OcupacionStrip): consumes `GET /operacion/ocupacion` polling 10s.
  - Si futura HU requiere "endpoint de ocupación con breakdown adicional por cliente/subscriptión", extender el SELECT con LEFT JOIN sobre la tabla `[L-E]` apropriada (sin partitioning de la MV — KD-2 natural composite se preserva).
- **D-F1.5-1 KD-6-respecting refactor** documented at `repo/ocupacion.py::get_ocupacion_puros_activos` docstring; future HU should NOT regress to `MV LEFT JOIN tipos_vehiculo` (would break F4.3 strip empty-state UX for fresh branches).

## Next steps

- HU-F1.5 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida por `plan.md:792` (dependencia): **HU-F1.6 — Validaciones reales en POST /operacion/ingresos** (260 LOC, depende F1.5 cerrado + F1.4 cerrado + KD-IVA no aplica).
- 8 HUs restantes pendientes (F1.6, F1.7 bloqueada por KD-IVA hasta siembra, F1.9 bloqueada por KD-IVA, F1.10..F1.15).
- `pending.md` actualizado: F1.5 marca `[~]` → `[x]`.

---

Closed by: sdd-archive (orchestrator-delegated executor). Update TODO-fase-1.md row 5 marking HU-F1.5 [x] (handled by orchestrator post-archive).
Engram: observation persisted, topic_key=`sdd/HU-F1.5-mv-ocupacion-diaria/closed`, project=`easypuinto-parkos-software`.