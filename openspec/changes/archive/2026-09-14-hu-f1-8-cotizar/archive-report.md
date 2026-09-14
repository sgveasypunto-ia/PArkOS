# Archive Report: hu-f1-8-cotizar

## Summary

**Change**: HU-F1.8 — Function `calcular_cotizacion` (PL/pgSQL) + `GET /operacion/cotizar`.
**Outcome**: SHIPPED. Verified PASS with 0 CRITICAL/HIGH/MEDIUM and 2 LOW documented deviations.
**Branch**: `feat/fase-1-prerequisites-backend`.
**Commits**:
- `a3d0c39 feat(backend): anadir PL/pgSQL calcular_cotizacion + GET /operacion/cotizar para HU-F1.8` (codigo: 8 files, +1923/-18)
- `9ebaed6 docs(openspec): HU-F1.8 — planeacion canonica del change hu-f1-8-cotizar` (docs: 5 canonicos, +1151/-0)
**Spec canonical merge**: REQ-OPS-022..025 merged into `openspec/specs/operations/spec.md`. REQ-OPS-025 letter RECONCILED: originally mandated `STABLE`; Postgres rejects `SELECT ... FOR SHARE` in STABLE functions, so the apply transitioned to `VOLATILE` and the read-only enforcement is now AST-walk-based. User approved 2026-09-14. Status: appended-with-reconciliation.
**Archived location**: `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/`

## Reconciliations

### REQ-OPS-025 letter (LOW L1)
- **Spec original letter**: declared `STABLE` + AST walk rejects mutations.
- **Code reality**: function is `VOLATILE` (Postgres constraint, `FeatureNotSupportedError` on `FOR SHARE` in STABLE/IMMUTABLE).
- **Spirit preserved**: AST walk `tests/static/test_no_write_in_calcular_cotizacion.py` continues rejecting INSERT|UPDATE|DELETE|TRUNCATE|MERGE within the function body.
- **Decision**: usuario aprobo 2026-09-14 aceptar VOLATILE siempre que AST walk este presente. REQ-OPS-025 canonico ahora declara "STABLE o VOLATILE aceptable, AST walk es la garantia read-only real".
- **Implicacion operativa**: si futura HU cambia la volatilidad a STABLE, debe documentar la perdida de KD-1 (lock FOR SHARE). Patron reusable: toda PL/pgSQL con `FOR SHARE` debe aceptar VOLATILE o reposicionarse.

### Tiempo_minutos `int | float`
- Schema `CotizarResponse` declara `tiempo_minutos: int | float` (T-7 del apply). Aceptable porque billing usa `CEIL(...)` internamente; el campo es informativo. Out of scope de spec change.

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-022..025 (with REQ-OPS-025 reconciled). To reverse safely: `git revert a3d0c39` reverts code; `git revert 9ebaed6` reverts docs. The spec content remains in archive as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **KD-IVA deployment blocker**: `impuestos.IVA` MUST be seeded before enabling F1.8 in any environment. Recipe in `design.md §4 KD-IVA`. Ownership: HU-F14.2 Parte II (out of scope F1.8). All HU-F1.8 calls return 500 `iva_no_configurado` until this is resolved.
- **25 pre-existing test failures**: `test_buffer_ttl_escalation.py`, `test_reverse_dry_run.py`, `test_router_factory_payload_body_binding.py`, `test_stage_runner.py`, `test_agents_md_no_superseded_terms.py::plan.md:3465`, plus 20 others. NO introduced by F1.8. Recommend dedicated housekeeping pass pre-Fase-2.
- **ruff `extend-select` deprecation** in repo-level `pyproject.toml`: out of F1.8 scope. Needs future tooling migration.
- **Reusable artifact**: PL/pgSQL `prod.calcular_cotizacion` (`0022_create_calcular_cotizacion.py`) will be CONSUMED by HU-F1.7 `POST /operacion/salidas` — that HU must replicate the lock `FOR SHARE` and the AST guard.
- **Forward hooks** (from design.md §9):
  - KD-2 CASE: if `tipo_tarifa.diaria` (1440) is added in future, requires `ALTER FUNCTION ... LANGUAGE plpgsql`.
  - KD-3 error code: pattern `{"error":"code"}` generalizable.

## Next steps

- HU-F1.8 cerrada. Continuar cadencia "una HU por turno". Siguiente sugerida: HU-F1.7 `POST /operacion/salidas` (220 LOC, depende de F1.8 cerrado, requiere sembrar IVA — bloqueante ahora).
- 10 HUs restantes pendientes (F1.3, F1.5, F1.6, F1.7 — parcialmente bloqueada por KD-IVA hasta siembra, F1.9..F1.15).

---

**Closed by**: sdd-archive (executor). Update TODO-fase-1.md marking HU-F1.8 [x] (handled by orchestrator, FUERA de este agente).
**Engram**: observation persisted, topic_key=sdd/HU-F1.8/closed, project=easypuinto-parkos-software.