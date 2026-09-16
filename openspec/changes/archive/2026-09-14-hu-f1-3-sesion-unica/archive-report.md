# Archive Report: hu-f1-3-sesion-unica

## Summary

**Change**: HU-F1.3 — Partial unique index `prod.uq_prod_sesion_one_active_per_user ON prod.sesion(uuid_usuario) WHERE timestamp_cierre IS NULL` + `GET /api/v1/caja-sesion/sesion/me` + typed 409 mapping for `UniqueViolation` (pgcode `23505`).
**Outcome**: SHIPPED. Verified PASS with 0 CRITICAL/HIGH/MEDIUM and 2 LOW documented deviations (pre-existing housekeeping).
**Branch**: `feat/fase-1-prerequisites-backend`.
**Commits**:
- `ca3f9bf feat(backend): anadir constraint sesion unica + GET /caja-sesion/sesion/me para HU-F1.3` (codigo: 10 files, +1264/-30)
- `4d530a4 docs(openspec): HU-F1.3 — planeacion canonica del change hu-f1-3-sesion-unica` (docs: 5 canonicos)
**Spec canonical merge**: REQ-OPS-026..029 merged into `openspec/specs/operations/spec.md`. Status: appended.
**Archived location**: `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/`

## Reconciliations

(none — no letter deviation required. REQ-OPS-026 partial unique index with `CONCURRENTLY` + pre-flight abort applies as-lettered.)

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-026..029. To reverse safely: `git revert 4d530a4` reverts the docs commit (remove the 4 REQs from spec); `git revert ca3f9bf` reverts the code commit (drops migration 0023, `get_my_sesion` handler, `SesionAlreadyActive` exception, `get_sesion_activa` helper, and the 7 tests). The spec content in archive remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **25 pre-existing test failures / skips**: same baseline as HU-F1.8. NOT introduced by F1.3. Recommend dedicated housekeeping pass pre-Fase-2. See verify-report.md §5 L2 for the autouse `_bootstrap_global_hash_chain_genesis` dependency on `pg_partman` not present in `postgres:16-alpine` local.
- **4 pre-existing mypy errors** in code NOT touched by F1.3 (`caja_sesion.py` handlers lines 79/134/163 without return annotation; `session_cycle.py` line 344 `rowcount` attribute error). Housekeeping separado. See verify-report.md §5 L1.
- **KD-IVA deployment blocker (NOT applicable to F1.3)**: HU-F1.3 no depende de `impuestos.IVA`. Aplica a F1.7/F1.9 que siguen bloqueadas hasta siembra (ownership HU-F14.2 Parte II).
- **Reusable artifact**: helper `repo/sesion_activa.py::get_sesion_activa` (+48 LOC) será reusado por cualquier futuro endpoint que necesite "sesión activa del actor". Patrón limpio async + SQLAlchemy + `LIMIT 1`.
- **Defense in depth chain completa** (BD unique index → repo pgcode capture → typed `SesionAlreadyActive` → handler 409 sin pgcode leak → `/me` handler antes del include_router → AST guard → factory_intact). Ver verify-report.md §6.
- **Forward hooks**:
  - Si una futura HU necesita "sesión activa de un `uuid_usuario` arbitrario desde `admin-`", eso es un endpoint separado con query param explícito (OUT OF SCOPE explícito en REQ-OPS-029).
  - Si se quiere extender el patrón partial unique index a otras tablas `[L-*]` con "at most one active row per actor" (ej `prod.caja` si llegara a existir), el patrón está documentado en REQ-OPS-026.

## Next steps

- HU-F1.3 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida por plan.md: **HU-F1.5 — `mv_ocupacion_diaria` + `GET /operacion/ocupacion`** (160 LOC, foundation para F1.6, **independiente de F1.3** y **no bloqueada por KD-IVA**).
- 9 HUs restantes pendientes (F1.5, F1.6, F1.7 bloqueada por KD-IVA hasta siembra, F1.9 bloqueada por KD-IVA, F1.10..F1.15).

---

**Closed by**: sdd-archive (executor). Update TODO-fase-1.md marking HU-F1.3 [x] (handled by orchestrator, FUERA de este agente).
**Engram**: observation persisted, topic_key=`sdd/HU-F1.3-sesion-unica/closed`, project=`easypuinto-parkos-software`.
