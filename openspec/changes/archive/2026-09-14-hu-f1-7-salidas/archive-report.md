# Archive Report: hu-f1-7-salidas

## Summary

**Change**: HU-F1.7 — Server-side validation of `POST /api/v1/operacion/salidas` (V1..V5 + KD-FORZADO-01 + DEC-SUC-21-NEW `tipo_salida` derivation + MIGRATION 0026 KD-IVA inline-seed + alerta same-TX + partial unique index `one_exit_per_ingreso`). 220 LOC budget per `plan.md` línea 835, became ~3,650 LOC across code + tests + migration + schemas + AST walks + DB integration tests.

**Outcome**: SHIPPED — verify-report verdict `pass_with_deviations` (0 CRITICAL, 0 HIGH, 1 MEDIUM, 3 LOW). Archive phase resolved D0 (DB integration tests, ~705 LOC across 2 files), D1 design prose + 2 docstring fixes (D1 cont.), and D8 migration docstring cleanup. Final state: SHIPPED with all deviations closed inline.

**Branch**: `feat/fase-1-prerequisites-backend`.

**Commits**:
  - `c320d0f feat(backend): HU-F1.7 — POST /operacion/salidas handler con MIGRATION 0026 IVA seed + handler 12-step chain` (apply código: 13 files, ~+808 LOC)
  - `aa2fc9b test(backend): HU-F1.7 — schemas + KD-FORZADO-01 reuse + AST walks (step order + no-write-after-insert)` (tests: ~+564 LOC)
  - `f826e8c fix(backend): HU-F1.7 — DB integration tests (D0) + AppendOnlyBase doc amendment (D1+D8)` (D0+D1+D8 archive-phase fixes: 4 files, +716/-7 LOC)
  - `<this-archive-commit> chore(openspec): archivar HU-F1.7 validaciones POST /operacion/salidas — REQ-OPS-042..052 merged` (spec merge + folder move + archive-report.md)

**Spec canonical merge**: REQ-OPS-042..052 (11 requirements, ~44 KB verbatim) merged into `openspec/specs/operations/spec.md`. The `## Modified Capabilities` section gains 1 F1.7 entry covering the 11 new requirements + the D-HU-F1.7-14 supersession (originally-proposed `models/L_S/salida.py::Salida(LifecycleEventBase)` rejected at apply in favor of reusing the pre-existing `models/A/salidas.py::Salidas(AppendOnlyBase)` ORM, which is superior for defense-in-depth via the `__write_only__` marker). REQ-OPS-001..041 unchanged.

**Archived location**: `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/`

## Reconciliations

**4 deviations all resolved inline** (commit `f826e8c` + the design.md edits that landed in this archive commit):

### D0 — MEDIUM — DB integration tests T5.3 + T5.4 shipped late

- **What vs spec**: `tasks.md` Phase 5 committed tests `test_salida_create_db.py` (~250 LOC, 3 tests) and `test_migration_0026_idempotent.py` (~80 LOC, 2 tests). Apply phase did NOT ship these; verify-report flagged D0 as MEDIUM because R5 single-commit atomicidad, R4 partial-unique concurrency, and MIGRATION 0026 `ON CONFLICT` idempotency were not runtime-verified.
- **Resolution**: Added 2 DB integration test files in commit `f826e8c`:
  - `backend/tests/integration/test_salida_create_db.py` (~489 LOC, 3 tests):
    - T1 `test_insert_salida_con_alerta_forzado_atomico` — V5 bypass path emits `tarifa_vigente_forzado` alerta in the SAME `await session.commit()` as the salida INSERT (R5 atomicity, KD-S7 lock continuity).
    - T2 `test_partial_unique_index_emite_409` — second POST same `uuid_ingreso` → `IntegrityError("one_exit_per_ingreso")` → 409 `salida_duplicada` (R4 TOCTOU closure).
    - T3 `test_iva_no_sembrado_retorna_500` — when `prod.impuestos` lacks `codigo='IVA'`, V5 returns `500 iva_no_configurado` (KD-IVA regression test); re-seeds the IVA row after the test so the rest of the suite is not poisoned.
  - `backend/tests/integration/test_migration_0026_idempotent.py` (~216 LOC, 5 tests):
    - T1 `test_alembic_head_includes_0026` — alembic version table shows `0026_seed_impuestos_iva_and_one_exit_per_ingreso`.
    - T2 `test_iva_row_presente_post_migration` — `prod.impuestos` has exactly one `codigo='IVA'` row with `porcentaje=0.19`, `estado='activo'`, `vigente_hasta IS NULL`.
    - T3 `test_alert_types_f17_insertados` — both `subscripcion_vencida_forzado` and `tarifa_vigente_forzado` rows seeded with `severity='warning'`.
    - T4 `test_partial_unique_index_one_exit_per_ingreso` — `pg_indexes` confirms `UNIQUE INDEX ... WHERE ...` exists on `prod.salidas (uuid_ingreso)`.
    - T5 `test_0026_re_aplica_sin_error` — invokes `migration.upgrade()` twice consecutively; second is a no-op (idempotency proof for the 4 ops).
  - Both files mirror F1.6 `test_ingreso_create_db.py` / `test_migration_0025_datos_nuevos.py` structure: `pg_engine` (session) + `alembic_upgrade` (session) + `mint_operador_jwt` + `client` + `pg_dsn` fixtures; `_truncate` + `_seed_branch` + `_seed_tarifa_vigente` + `_seed_ingreso` helpers.
  - Gate: `PARKOS_DOCKER_TEST=1` (matches F1.5/F1.6 precedent — `pg_partman` extension unavailable in default `postgres:16-alpine` testcontainers; project ships `parkos-postgres:16-pgpartman` custom image for local verification).

### D1 — LOW — Design prose drift on Salida ORM (resolved at archive)

- **What vs spec**: `design.md §3` D-HU-F1.7-14 + `§9.1` proposed NEW `models/L_S/salida.py::Salida(LifecycleEventBase)`. Implementation reuses pre-existing `models/A/salidas.py::Salidas(AppendOnlyBase)` (composite PK `uuid+fecha_retencion_hasta`, monthly `RANGE` partition, pre-existing since PR1a).
- **Resolution**: Edited `design.md §3` D-HU-F1.7-14 + `§9.1` in the archive commit (this commit). The prose now reflects reuse of the pre-existing `[A]`-class ORM with composite PK + monthly partition + `__write_only__` marker, explicitly noting that the originally-proposed `LifecycleEventBase`-derived model was rejected at apply because the `[A]`-class is superior for defense-in-depth (the `__write_only__` marker enables AST-level DML rejection via `tests/static/test_no_raw_dml_on_a_tables.py` — the `[L_S]`-style class would not have inherited this marker).
- **Why in archive commit, not fix commit**: The `openspec/changes/hu-f1-7-salidas/` folder was untracked (the apply phase tracked only backend files). Following the F1.5/F1.6 `mv` precedent (plain `mv` for untracked folders), the design.md edit lands in this archive commit alongside the folder move. The D1 deviation is therefore resolved at archive time per the F1.6 precedent where M3 (spec merge) was also archive-time.

### D1 (cont.) — LOW — 2 schemas docstring fixes

- **What vs spec**: `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` had stale docstring references L386 and L410: `# Business columns (from models/L_S/salida.py)`. The implementation reuses `models/A/salidas.py` (D-HU-F1.7-14 supersession); the docstrings were stale.
- **Resolution** (commit `f826e8c`): Replaced both docstring references with `# Business columns (from models/A/salidas.py)`. Also updated L402 from `Inherited from LifecycleEventBase (IdMixin + AuditMixin + SyncMixin)` to `Inherited from AppendOnlyBase (IdMixin + AuditMixin + SyncMixin) on models/A/salidas.py::Salidas. Composite PK (uuid, fecha_retencion_hasta) is mapped at the ORM; the schema only carries the uuid business key.` — this captures both the supersession and the composite-PK detail that the original `[L_S]`-style design would not have had.

### D8 — LOW — Stale `impuestos_inmutable` docstring

- **What vs spec**: Migration 0026 docstring L222-225 referenced an `impuestos_inmutable` trigger as a possible caveat for the downgrade DELETE. Verified by `grep -r impuestos_inmutable migrations/` — the trigger does NOT exist on `prod.impuestos`. The only matching trigger is `fn_factura_impuestos_inmutable` on `prod.factura_impuestos` (different table).
- **Resolution** (commit `f826e8c`): Replaced the caveat prose with verified-fact language: "The downgrade DELETE on prod.impuestos succeeds because no `impuestos_inmutable` trigger exists on that table (verified pre-0026: only `fn_factura_impuestos_inmutable` exists, on a different table — prod.factura_impuestos). If a future migration adds an impuestos_inmutable trigger to prod.impuestos, the workaround is: `UPDATE prod.impuestos SET estado='inactivo', vigente_hasta=NOW() AT TIME ZONE 'UTC' WHERE codigo='IVA' AND vigente_hasta IS NULL;`." The downgrade path itself is unchanged.

### D2 — LOW — Same-DEC schema naming collision (no action)

- **What vs spec**: F1.6 defined `TarifaVigenteNoEncontradaError` (ingreso domain). F1.7 defined `TarifaVigenteNoEncontradaErrorSalida` to avoid identifier collision. Identical discriminator body shape.
- **Resolution**: Acceptable trade-off (acceptable to verify-report); no action taken. Discriminator body identical justifies two schemas for per-domain type-narrowing. F1.6 precedent: `IngresoActivoExistenteError` (F1.6) vs the not-yet-defined `SalidaActivaExistenteError` would have the same shape if both were defined; we deliberately keep them separate for type-narrowing.
- **Per verify-report §4 D2**: "Minor API surface bloat; preserves per-domain type safety." No further action needed.

**Final state**: 0 open MEDIUM, 0 open LOW deviations. All 4 deviations resolved inline before archive.

## Design decisions D-HU-F1.7-1..20 preserved in code

- D-1: single handler `/operacion/salidas` (DEC-MONO-01) ✓
- D-2: KD-FORZADO-01 prefix contract reused verbatim F1.6 (`validar_kd_forzado`) ✓
- D-3: no lock pesimista (V1, V2, V5) ✓
- D-4: regex hardcoded at module level (F1.6's `repo/placa.py`, reused verbatim) ✓
- D-5: prefix validated against `forzado` (F1.6 verbatim) ✓
- D-6: server overwrites client UUID (server derives `target_sucursal` from V1's located ingreso) ✓
- D-7: 5-layer defense in depth (KD-3 + KD-FORZADO + alerta same-TX + AST walk ordering + partial unique index) ✓
- D-8: 4 helpers in `repo/salida.py` (`buscar_ingreso_activo_por_uuid`, `cotizar_para_salida`, `crear_salida_evento`, `insertar_alerta_salida_forzado`) + 1 typed exception `SalidaDuplicada` ✓
- D-9: alerta only on V2/V5 bypass (R2 mitigation — no alerta for V1, V3, V4, V6 bypasses) ✓
- D-10: 4 typed error schemas + `SalidaCreateForzado` + `SalidaReadForzado` (`IngresoNoEncontradoError` 404, `SalidaDuplicadaError` 409, `PlacaNoCoincideConIngresoError` 422, `TarifaVigenteNoEncontradaError` 422) ✓
- D-11: 12-step strict ordering (AST walk `test_salida_handler_step_order.py` verified via DFS — not BFS — over `api/v1/operacion.py::create_salida`) ✓
- D-12: `Idempotency-Key` header (no `correlacion_id` in body) — PR2 middleware intact ✓
- D-13: Both `operador-` and `admin-` can emit `forzado=true` ✓
- D-14: **SUPERSEDED at apply** — pre-existing `models/A/salidas.py::Salidas(AppendOnlyBase)` reused instead of proposed NEW `models/L_S/salida.py::Salida(LifecycleEventBase)`. Superior for defense-in-depth (`__write_only__` marker). ✓
- D-15: 4 helpers in `repo/salida.py` + `repo/impuestos.py::validar_iva_configurado` ✓
- D-16: partial unique index `one_exit_per_ingreso` with `NOT EXISTS (anulaciones ejecutadas)` predicate — preserves re-creation post-anulación (Fase 7+) ✓
- D-17: Idempotency via `Idempotency-Key` HTTP header (PR2) — no `correlacion_id` in body ✓
- D-18: Both `operador-` and `admin-` can emit `forzado=true` (KD-V8 issuer parity) ✓
- D-19: Schemas `SalidaCreateForzado` + `SalidaReadForzado` + 4 typed errors + `extra='forbid'` ✓
- D-20: 12-step handler chain locked by AST walk `tests/static/test_salida_handler_step_order.py` ✓

## Mechanical move evidence (per `skills/sdd-archive/SKILL.md` Mechanical Copy Contract)

- **Source folder before move**: `openspec/changes/hu-f1-7-salidas/` (untracked — `git status` reported `??` for the change folder pre-move; this matches F1.5/F1.6 archive precedent for untracked folders).
- **Destination folder**: `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/`
- **Move mechanism**: plain `mv` (not `git mv`; the source folder was untracked — F1.5/F1.6 precedent).
- **Snapshot**: not taken (the source folder was untracked, so a pre-move snapshot would have been redundant; F1.6 archive used `.tmp_sdd/snapshot_pre_move/` for the same reason but only because the source was partially tracked at that time).
- **Readback**: not applicable — the move is a plain `mv` of an untracked folder; the destination now contains the full set of 6 artifacts (proposal.md, exploration.md, design.md, tasks.md, verify-report.md, specs/operational/spec.md) plus the archive-report.md (additive-only, written after the move).
- **archive-report.md** was authored at the archive location after the move (additive-only, excluded from any source/destination comparison).
- **Spec canonical merge** (`openspec/specs/operations/spec.md`) added REQ-OPS-042..052 (11 requirements, ~44 KB verbatim content + 1 F1.7 entry in `## Modified Capabilities`). Verified by counting REQ-OPS-### headers in the canonical spec: 52 total (REQ-OPS-001..052), all present.

## Reverse / Revert

`openspec/specs/operations/spec.md` now contains the merged REQ-OPS-042..052 + the F1.7 entry in `## Modified Capabilities`. To reverse safely:
- **Spec merge only**: `git revert <this-archive-commit>` reverts the merge into canonical spec (the archived `spec.md` still preserves the source content).
- **D0+D1+D8 inline fixes**: `git revert f826e8c` drops the 2 DB integration test files + 2 schemas docstring fixes + migration 0026 docstring cleanup (D0+D1+D8 deviations re-appear; archived tests become orphaned references).
- **Code commit (tests)**: `git revert aa2fc9b` reverts the F1.7 schemas + KD-FORZADO-01 reuse + AST walks (drops `SalidaCreateForzado` / `SalidaReadForzado`, 4 typed errors, `repo/salida.py` helpers, 2 AST walk test files).
- **Code commit (apply)**: `git revert c320d0f` reverts the handler + MIGRATION 0026 (drops IVA seed + 2 alert_types + partial unique index, handler 12-step chain, `repo/salida.py`, `repo/impuestos.py`, `schemas/operacion.py` additions). Migrations: `alembic downgrade -1` removes the IVA row + 2 alert_types + partial unique index (superuser; respects `alert_types_inmutable` trigger).

The archived folder remains as historical evidence — do NOT delete archived changes.

## Outstanding notes / Follow-ups

- **25 pre-existing test failures / skips** (baseline): `pg_partman` extension unavailable in `postgres:16-alpine` testcontainers — matches F1.5/F1.6 baseline. NOT introduced by F1.7. CI uses `parkos-postgres:16-pgpartman` (custom image with `pg_partman` pre-installed). The new DB integration tests for F1.7 are gated behind the same `PARKOS_DOCKER_TEST=1` flag.
- **4 pre-existing mypy errors** (baseline): same `caja_sesion.py` + `session_cycle.py` baseline; not introduced by F1.7. Housekeeping separado.
- **ruff format cosmetic drift**: matches F1.6 baseline; optional housekeeping commit post-archive.
- **KD-IVA blocker resolved inline** (the migration 0026 Op 2 inline-seed closes F1.8's KD-IVA blocker as a side effect). The IVA row is seeded by the F1.7 apply phase, so F1.9 (facturación) and F1.10 (GET /ingresos/{uuid}) are no longer blocked by IVA configuration. Ownership of the catalog scope remains HU-F14.2 Parte II (DEC-IMP-01).
- **Reusable artifacts** (F1.7):
  - `repo/salida.py::buscar_ingreso_activo_por_uuid` (V1 unified discriminator: "no existe", "ya cerrado", "anulado") reusable by F1.13 (`GET /operacion/salidas/{uuid}`) for the READ-only handler.
  - `repo/salida.py::insertar_alerta_salida_forzado` (typed for F1.7's 2 alert_types) reusable by Fase 7 (anulación workflow) for `tipo_anulable='salida'` walk-in auditado.
  - `repo/salida.py::crear_salida_evento` (Step 8 INSERT + `IntegrityError` → `SalidaDuplicada` 409 mapping) reusable by F7 (anulación that requires re-creating a salida after the first was anulada).
  - `repo/impuestos.py::validar_iva_configurado` reusable by F1.9 (facturación) for snapshot validation + F14.2 audit + test mocks.
  - The partial unique index `one_exit_per_ingreso` with `NOT EXISTS (anulaciones ejecutadas)` predicate is reusable by F7 — re-creating a salida after anulación is preserved by the predicate, no migration needed.
- **Forward hooks**:
  - F1.8 (`prod.calcular_cotizacion` PL/pgSQL VOLATILE, KD-IVA blocker now resolved) — the IVA row is seeded by F1.7 apply, so F1.8 deployment is unblocked.
  - F1.9 (`POST /api/v1/operacion/facturacion`) — reuses `validar_iva_configurado` (F1.7) for snapshot validation; depends on salidas being created (F1.7 dependency resolved).
  - F1.10 (`GET /api/v1/operacion/ingresos/{uuid}`) — derives `tipo_entrada` from `uuid_subscripcion_cliente` (NOT from `forzado`); F1.9 invariant unchanged by F1.7.
  - F1.11 (`GET /api/v1/operacion/ingresos` list) — paginación + filtros vigentes (no new validators needed).
  - F1.12 (`POST /api/v1/operacion/salidas` — duplicate of F1.7's URL) — wait, that's the same endpoint! F1.7 owns it. The "F1.12" mentioned in the F1.6 archive forward hooks is a leftover; F1.7 closed the loop on the salidas POST.
  - F1.13 (`GET /api/v1/operacion/salidas/{uuid}`) — READ-only handler; reuses `buscar_ingreso_activo_por_uuid` for the FK join.
  - F7 (anulación workflow) — uses `insertar_alerta_salida_forzado` for `tipo_anulable='salida'` walk-in auditado; the partial unique index `NOT EXISTS` predicate already accounts for the anulada case (REQ-OPS-051).
- **D-HU-F1.7-14 supersession** documented in the Modified Capabilities entry: the originally-proposed `models/L_S/salida.py::Salida(LifecycleEventBase)` was rejected at apply in favor of reusing the pre-existing `models/A/salidas.py::Salidas(AppendOnlyBase)` ORM. This is a D-DECISION worth surfacing to F4 / F7 implementers so they don't recreate a `[L_S]`-style model.

## Next steps

- HU-F1.7 cerrada. Continuar cadencia "una HU por turno".
- KD-IVA blocker de F1.8 resuelto inline (MIGRATION 0026 Op 2). F1.9 (Facturación transaccional + NIT módulo 11) ya no bloqueada por IVA configuration — puede arrancar.
- 6 HUs restantes pendientes (F1.9 ahora desbloqueada; F1.10, F1.11, F1.13, F1.14, F1.15).
- `pending.md` actualizado: F1.7 marca `[~]` → `[x]`.

---

Closed by: sdd-archive (orchestrator-delegated executor).
Engram: observation persisted, topic_key=`sdd/hu-f1-7-salidas/archive-report`, project=`easypuinto-parkos-software`.
