# Tasks: hu-f1-13-arqueo

> **Change**: `hu-f1-13-arqueo` · **Phase**: tasks (sdd-tasks) · **HU**: HU-F1.13 — Endpoints arqueo + GAP-BE-05
> **Date**: 2026-09-15 · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a328957`) · **PR target**: `origin/dev`
> **Cumulative estimate**: ~590 LOC (290 prod + 220 tests + 80 migration)
> **Clusters**: T1..T5 + T-GAP-BE-05 (6 clusters)
> **Mandated tests**: 4 (plan.md line 1093)
>
> **Inputs**:
> - `openspec/changes/hu-f1-13-arqueo/design.md` (~1804 LOC, 16 sections, DEC-ARQUEO-01..10 + KD-ARQUEO-01..05 + MIGRATION 0031 SQL + 4 AST walks)
> - `openspec/changes/hu-f1-13-arqueo/proposal.md` (~485 LOC, 16 sections, R1..R12 risks, 6-cluster decomposition)
> - `openspec/changes/hu-f1-13-arqueo/specs/operations/spec.md` (~485 LOC, 8 REQ-OPS-091..097 + REQ-OPS-XR6)
> - `openspec/changes/hu-f1-13-arqueo/exploration.md` (~29 KB, 17 sections, pre-flight 18/20 PASS)
> - `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/tasks.md` (~860 LOC, 8 clusters T1..T8, 31 atomic tasks) — **canonical precedent**
> - `plan.md` lines 1058-1101 (HU-F1.13, 4 atomic tasks T1..T4, 240 LOC production budget, 4 tests mandated at line 1093, GAP-BE-05 mandate at lines 7349-7374)
> - `plan.md` line 458 (A-07 `cierre_dia` siembra)
> - `modelo_datos_er.mmd` blocks `tipo_arqueo` [V] line 167-185, `configuracion_tolerancias` [V] line 250-268, `sesion` [L-S] line 715-735, `alerta` [L-W] line 737-758, `arqueo` [A] line 957-978
> - `migrations/versions/0001_initial_schema.py` (`tipo_arqueo` lines 167-185, `sesion` lines 715-735, `alerta` lines 737-758, `arqueo` lines 957-978, immutability triggers lines 2024-2088)
> - `migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22)
> - `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (F1.11 head template for conditional siembra, lines 134-188)
> - `migrations/versions/0030_venta_suscripcion_optional.py` (F1.12 NO-OP audit trail head pre-F1.13)
> - `api/v1/caja.py` line 53 (GAP-BE-05 site #1 — `emitir_factura` → `realizar_arqueo`)
> - `api/v1/caja_sesion.py` line 257 (GAP-BE-05 site #2 — `emitir_factura` → `abrir_cerrar_caja`)
> - `models/V/{tipo_arqueo, configuracion_tolerancias}.py`, `models/A/{arqueo, alert_types, factura_pagos, log_transaccional}.py`, `models/L_S/sesion.py`, `models/L_W/alerta.py`
> - `repo/{append_only, workflow, session_cycle, sesion_activa, alert_types, idempotency, hash_chain}.py` (helpers reused verbatim)
> - `api/v1/{operacion, facturacion, workflows_reimpresion, clientes_venta, caja, caja_sesion, _helpers, deps}.py` (handler envelope references)
> - `auth/{jwt_issuer_guard, tenancy}.py` (KD-3 issuer chain + `TenantContext`)
> - `tests/static/{test_no_raw_dml_on_a_tables, test_venta_handler_single_commit, test_fe_handler_single_commit, test_workflow_handler_single_commit, test_salida_handler_step_order}.py` (AST walk precedents)
> - `schemas/common.py::_Base` (`extra='forbid'` — Layer 4 defense)
>
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `a328957`) · **PR target**: `origin/dev`.
> **TDD discipline**: RED→GREEN→REFACTOR per cluster. Each commit <800 LOC. Each cluster ends with all tests PASS.
> **Atomic commit strategy**: 9 atomic commits expected (T1, T2, T3, T4, T5, T6 = T5 tests, T7 = T-GAP-BE-05, plus router mount as separate commit).
> **Skills loaded**: `gentle-sdd-tasks` + `sdd-phase-common.md` (paths injected via orchestrator).

---

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~590 across 1 PR (~290 LOC production per `plan.md` line 1097 = ~180 LOC NEW `api/v1/caja_arqueo.py` + ~100 LOC NEW `repo/arqueo.py` + ~90 LOC EXTEND `schemas/caja.py` + ~5 LOC MODIFY `api/v1/caja.py` + ~5 LOC MODIFY `api/v1/caja_sesion.py` + ~80 LOC MIGRATION 0031 REAL siembra + ~10 LOC GAP-BE-05 fix + ~220 LOC tests + ~80 LOC 4 AST walks + ~30 LOC 1 migration test) |
| Total tasks | ~25 (6 clusters: T1 setup 2 + T2 repo+schemas 5 + T3 POST handler 4 + T4 GET handler 2 + T5 tests+AST walks 6 + T-GAP-BE-05 2 + supporting commit splits) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Medium** — F1.13 is comparable to F1.11 + F1.12 (~860 LOC cumulative). Cohesive single-resource (1 dedicated handler + 12 repo helpers + 5 schemas + 1 REAL migration + 2-line GAP-BE-05); 9-commit split (one per cluster T1..T5 + T-GAP-BE-05 + router mount) keeps each commit under the `commitlint` 800-LOC ceiling. |
| Chained PRs recommended | No — one single PR (matches F1.7 + F1.9 + F1.10 + F1.11 + F1.12 precedent); defense in depth is verified in-place. |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Single PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 9 commits internally (T1 ~80, T2a ~100, T2b ~90, T3a ~180, T3b ~30 router mount, T4 ~60, T5a ~50 AST walks, T5b ~170 tests + e2e + migration, T-GAP ~5 fix + test). |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesive single-resource + 9-commit split keeps budget risk Medium inside the F1.11/F1.12 precedent. |

| Cluster | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|---------|-------|---------------|----------------|----------------|
| T1 Setup + MIGRATION 0031 | T1.1..T1.2 | ~80 LOC (pre-flight + migration) | n/a | 80 |
| T2 Repo helpers + schemas | T2.1..T2.5 | ~190 LOC (10 typed helpers + 6 typed exceptions + 5 schemas + 6 typed errors) | n/a (tests in T5) | 270 |
| T3 POST handler | T3.1..T3.4 | ~180 LOC (12-step chain + typed-exception mapping + cierre_dia mass close + router mount) | n/a (tests in T5) | 450 |
| T4 GET handler | T4.1..T4.2 | ~60 LOC (6-step chain + cierre_dia aggregate) | n/a (tests in T5) | 510 |
| T5 Static AST walks + tests | T5.1..T5.6 | n/a (tests only) | ~220 LOC (3 AST walks + 4 mandated handler tests + 5 repo unit + 2 cierre_dia + 3 resumen + 1 e2e + 2 migration idempotency) | 730 |
| T-GAP-BE-05 Permiso fix | T-GAP.1..T-GAP.2 | ~5 LOC (2-line fix) | ~5 LOC (1 unit test) | 740 |
| **Total** | **~25** | **~510 LOC impl** | **~225 LOC tests** | **~590 LOC cumulative workload** |

> Per-commit ceiling: <800 LOC. Each cluster T1..T5 + T-GAP-BE-05 fits within the limit (T3 POST handler chain at ~180 LOC is the largest implementation block, well within). T2 may require mental split (T2.1..T2.4 helpers ~100 LOC + T2.5 schemas ~90 LOC = ~190 LOC). Orchestrator decides per real diff at apply.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| T1 | Pre-flight verify + MIGRATION 0031 siembra (Op 0 + Op 1 + Op 2 + Op 3) | commit 1 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0031_idempotency.py -q` | `pg_engine` real via `testcontainers[postgres]`; pre-flight DO $$ asserts 7 tables; Op 1 + Op 2 idempotent via `ON CONFLICT DO NOTHING` | `alembic downgrade -1` reverses Op 1 + Op 2; Op 3 NO-DDL |
| T2 | `repo/arqueo.py` 13 typed helpers + 6 typed exceptions + 5 schemas + 6 typed errors | commit 2 + commit 3 | `uv run pytest backend/tests/unit/test_arqueo_repo.py -q` | unit tests no DB (T2.1 + T2.4 + T2.5); pure Decimal math (T2.4); schema Pydantic validation (T2.5) | Delete helper bodies / schema appends |
| T3 | POST `/caja/arqueo` 12-step chain + typed-exception mapping + cierre_dia mass close + router mount | commit 4 + commit 5 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_arqueo_e2e.py -q` | HTTP integration with `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-`/`admin-` fixtures + real DB | Revert handler module + mount |
| T4 | GET `/caja/arqueo/resumen` 6-step chain + cierre_dia aggregate | commit 6 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_arqueo_resumen.py -q` | HTTP integration with real DB; verifies 200 OK + Cache-Control: no-store + JOIN sesion + factura_pagos | Revert handler module |
| T5 | 4 AST walks (KD-ARQUEO-01 single-commit + KD-ARQUEO-02 no raw DML + KD-ARQUEO-03 cierre_dia session_cycle + KD-ARQUEO-02 no UPDATE on [A]) + 4 mandated handler unit tests + repo unit + cierre_dia + resumen + e2e + migration idempotency | commit 7 + commit 8 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_arqueo_handler.py backend/tests/unit/test_arqueo_repo.py backend/tests/unit/test_cierre_dia.py backend/tests/unit/test_arqueo_resumen.py backend/tests/integration/test_arqueo_e2e.py backend/tests/integration/test_migration_0031_idempotency.py backend/tests/static/test_arqueo_handler_*.py -q` | real DB for unit + e2e; pure AST walks for static | Delete AST walk files |
| T-GAP-BE-05 | `api/v1/caja.py:53` + `api/v1/caja_sesion.py:257` 2-line permission fix + 1 unit test asserting 403 on `emitir_factura`-only role | commit 9 | `uv run pytest backend/tests/unit/test_gap_be_05.py -q` | HTTP integration with role fixtures; verifies `emitir_factura` → 403 + `realizar_arqueo`/`abrir_cerrar_caja` → 200 | Revert 2 lines |

---

## Tareas

### Cluster T1 — Setup & MIGRATION 0031 siembra (~80 LOC impl)

- [x] **T-HU-F1.13-T1.1** [RED + GREEN] — Pre-flight verification: grep across the repo for `prod.tipo_arqueo` (in `migrations/versions/0001_initial_schema.py` lines 167-185), `prod.arqueo` (lines 957-978), `prod.sesion` (lines 715-735), `prod.alerta` (lines 737-758), `prod.configuracion_tolerancias` (lines 250-268), `prod.factura_pagos` (lines 2024-2088), `prod.alert_types` (migration 0013); verify `cierre_dia` NOT seeded in `prod.tipo_arqueo` (grep returns 0 matches); verify `descuadre_critico` NOT seeded in `prod.alert_types` (grep returns 0 matches); verify GAP-BE-05 sites #1 + #2 still carry `permission_required="emitir_factura"` at `caja.py:53` + `caja_sesion.py:257`. Write `tests/integration/test_migration_0031_idempotency.py::test_pre_flight_tables_present` asserting the 7 tables exist via SQL `information_schema.tables` query.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_pre_flight_all_7_tables_exist` — query `information_schema.tables WHERE table_schema='prod' AND table_name IN ('tipo_arqueo', 'alert_types', 'arqueo', 'sesion', 'alerta', 'configuracion_tolerancias', 'factura_pagos')` returns exactly 7 rows.
    - T2: `test_pre_flight_cierre_dia_missing` — `SELECT COUNT(*) FROM prod.tipo_arqueo WHERE codigo='cierre_dia' AND vigente_hasta IS NULL` returns 0 (DEC-ARQUEO-09 gap confirmed pre-implementation).
    - T3: `test_pre_flight_descuadre_critico_missing` — `SELECT COUNT(*) FROM prod.alert_types WHERE tipo_alerta='descuadre_critico'` returns 0 (DEC-ARQUEO-09b gap confirmed pre-implementation).
    - T4: `test_gap_be_05_site_1_confirmed` — literal source-level read of `api/v1/caja.py:53` returns line containing `permission_required="emitir_factura"`.
    - T5: `test_gap_be_05_site_2_confirmed` — literal source-level read of `api/v1/caja_sesion.py:257` returns line containing `permission_required="emitir_factura"`.
  - **Patrón F1.11 + F1.12** (`test_migration_0029_idempotency.py` + `test_migration_0030_noop.py`): pre-flight `DO $$` table-presence assertion + source-level grep.
  - **Acción**: write test that asserts pre-flight state via SQL + source-level read of `api/v1/caja.py` and `api/v1/caja_sesion.py`. — **Archivo**: `backend/tests/integration/test_migration_0031_idempotency.py` (nuevo, partial ~30 LOC, 5 tests covering pre-flight + Op 1 + Op 2 idempotency). — **Validación**: pre-implementation, all 5 pre-flight tests PASS (pre-flight already satisfied 2026-09-15 per exploration §12).

- [x] **T-HU-F1.13-T1.2** [GREEN] — Author `migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` (~80 LOC, REAL siembra): Op 0 pre-flight `DO $$` block asserting all 7 tables exist + Op 1 siembra `prod.tipo_arqueo.codigo='cierre_dia'` (A-07, plan.md line 458) with `IF siembra_count = 0` + `ON CONFLICT (codigo, vigente_desde) DO NOTHING` + Op 2 siembra `prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'` with `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING` (respects `alert_types_inmutable` trigger migration 0013:21-22) + Op 3 NO-DDL comment for GAP-BE-05 (DEC-ARQUEO-08). `downgrade()` reverses Op 1 (close `vigente_hasta`) + Op 2 (DISABLE trigger + DELETE + ENABLE trigger). `down_revision='0030_venta_suscripcion_optional'`.
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` (nuevo, ~80 LOC).
  - **Contenido** (verbatim per proposal §14):
    ```python
    """0031_arqueo_cierre_dia_and_gap_be_05.py — MIGRATION 0031 (REAL siembra).

    Pre-flight 2026-09-15 confirmed:
    - prod.tipo_arqueo exists with 3 seeded values (cierre_turno, auditoria, cierre_sesion).
    - prod.alert_types exists with 9 seeded values (registry migration 0013 + 0025).
    - prod.tipo_arqueo.cierre_dia NOT seeded (A-07, plan.md line 458) → Op 1 seeds it.
    - prod.alert_types.descuadre_critico NOT seeded → Op 2 seeds it (F1.14 idempotency).
    - GAP-BE-05 site #1 (caja.py:53) + site #2 (caja_sesion.py:257) are Python-only
      fixes; NO migration needed (DEC-ARQUEO-08 + plan.md line 7359) → Op 3 NO-DDL comment.

    This migration ships:
    - Op 0: pre-flight DO $$ block asserting required tables exist.
    - Op 1: siembra prod.tipo_arqueo.codigo='cierre_dia' (A-07) — idempotent via
      IF siembra_count = 0 + ON CONFLICT (codigo, vigente_desde) DO NOTHING.
    - Op 2: siembra prod.alert_types.tipo_alerta='descuadre_critico', severity='critical'
      — idempotent via ON CONFLICT (tipo_alerta) DO NOTHING
      (respects alert_types_inmutable trigger, migration 0013:21-22).
    - Op 3: NO-DDL comment for GAP-BE-05 (Python-only correction in DEC-ARQUEO-08).

    Idempotency ensures F1.14's future seed of `descuadre_critico` becomes a no-op.
    """
    from alembic import op

    revision = "0031_arqueo_cierre_dia_and_gap_be_05"
    down_revision = "0030_venta_suscripcion_optional"
    branch_labels = None
    depends_on = None


    def upgrade() -> None:
        # Op 0: pre-flight DO $$ (KD-7 F1.6..F1.12 pattern)
        op.execute("""
            DO $$
            BEGIN
                ASSERT (
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema='prod' AND table_name IN (
                        'tipo_arqueo', 'alert_types', 'arqueo', 'sesion', 'alerta',
                        'configuracion_tolerancias', 'factura_pagos'
                    )
                ) = 7, 'F1.13 requires all 7 tables to exist';
            END $$;
        """)

        # Op 1: siembra prod.tipo_arqueo.codigo='cierre_dia' (A-07, plan.md line 458)
        op.execute("""
            DO $$
            DECLARE
                siembra_count INTEGER;
            BEGIN
                SELECT COUNT(*) INTO siembra_count
                FROM prod.tipo_arqueo
                WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL;
                IF siembra_count = 0 THEN
                    INSERT INTO prod.tipo_arqueo (codigo, nombre, vigente_desde, vigente_hasta, estado, created_at, created_by)
                    VALUES ('cierre_dia', 'Cierre de día (mass cierre de sesiones)', NOW(), NULL, 'activo', NOW(), 'migrations/0031');
                END IF;
            END $$;
        """)

        # Op 2: siembra prod.alert_types.tipo_alerta='descuadre_critico' (DEC-ARQUEO-09b)
        op.execute("""
            INSERT INTO prod.alert_types (tipo_alerta, severity, created_at, created_by)
            VALUES ('descuadre_critico', 'critical', NOW(), 'migrations/0031')
            ON CONFLICT (tipo_alerta) DO NOTHING;
        """)

        # Op 3: NO-DDL — GAP-BE-05 is a Python-only correction (DEC-ARQUEO-08)
        # Sites: api/v1/caja.py:53 + api/v1/caja_sesion.py:257
        # No DB schema changes; this comment serves as an audit-trail anchor.
        pass


    def downgrade() -> None:
        # Reverse Op 2: remove descuadre_critico from alert_types
        # NOTE: alert_types_inmutable trigger blocks DELETE; disable temporarily.
        op.execute("ALTER TABLE prod.alert_types DISABLE TRIGGER alert_types_inmutable;")
        op.execute("DELETE FROM prod.alert_types WHERE tipo_alerta = 'descuadre_critico';")
        op.execute("ALTER TABLE prod.alert_types ENABLE TRIGGER alert_types_inmutable;")

        # Reverse Op 1: close the vigente row for cierre_dia (bi-temporal VersionedBase)
        op.execute("""
            UPDATE prod.tipo_arqueo
            SET vigente_hasta = NOW()
            WHERE codigo = 'cierre_dia' AND vigente_hasta IS NULL;
        """)

        # Op 3: NO-DDL — GAP-BE-05 reversal is a Python revert (out of scope for downgrade()).
        pass
    ```
  - **Acción**: paste verbatim from design §3.5 + proposal §14; `revision="0031_arqueo_cierre_dia_and_gap_be_05"`; `down_revision="0030_venta_suscripcion_optional"`. — **Validación**: T1.1 pre-flight tests PASS pre-migration (gaps confirmed); post-migration `tests/integration/test_migration_0031_idempotency.py` round-trip test PASSes (upgrade → downgrade → upgrade idempotent).

  **Commit suggestion**: `chore(backend): HU-F1.13 — MIGRATION 0031 REAL siembra (cierre_dia + descuadre_critico + pre-flight DO $$)`.

  **Exit criteria T1**: T1.1..T1.2 verde; ~80 LOC cumulative; migration head = `0031_arqueo_cierre_dia_and_gap_be_05`; pre-flight DO $$ asserts all 7 tables exist; Op 1 seeds `cierre_dia` idempotently; Op 2 seeds `descuadre_critico` idempotently; downgrade reverses cleanly.

### Cluster T2 — Repo Helpers + Schemas (~190 LOC impl)

- [x] **T-HU-F1.13-T2.1** [RED + GREEN] — Author `repo/arqueo.py` skeleton (~10 LOC): `from __future__ annotations` + module docstring documenting DEC-ARQUEO-01..10 + KD-ARQUEO-01..05 references + define 6 typed exception classes (`TipoArqueoNoEncontradoError` 404, `SesionNoEncontradaError` 404, `ToleranciaNoConfiguradaError` 404, `SesionYaCerradaError` 409, `CierreDiaNoAceptaSesionError` 400, `JustificacionRequeridaError` 400) — each carrying typed dataclass-style attributes + `__str__` for logging + `__all__` listing the 13 helper names + 6 exception names.
  - **Tests** (pure Python, no DB, no HTTP):
    - T1: `test_repo_arqueo_module_imports` — `from parkos_core.repo import arqueo as repo_arqueo` succeeds; `dir(repo_arqueo)` includes 6 typed exception names (DEC-ARQUEO-01..10 references).
  - **Patrón F1.12** (`test_repo_venta_suscripcion_module_imports`): pure import assertion, gated by `__all__` definition.
  - **Acción**: `import` from `parkos_core.repo.arqueo` (fails with `ModuleNotFoundError`); assert public names. — **Archivo**: `backend/tests/unit/test_arqueo_repo.py` (nuevo, partial ~10 LOC, 1 test). — **Validación**: `ModuleNotFoundError: No module named 'parkos_core.repo.arqueo'`.

- [x] **T-HU-F1.13-T2.2** [RED + GREEN] — Implement `resolver_tipo_arqueo_por_uuid` (V1, ~20 LOC) with `SELECT * FROM prod.tipo_arqueo WHERE uuid=:t AND vigente_hasta IS NULL ORDER BY vigente_desde DESC LIMIT 1 FOR UPDATE` (KD-ARQUEO-08 + DEC-ARQUEO-09). Raises `TipoArqueoNoEncontradoError(uuid_tipo_arqueo=str(uuid))` when returns None. Returns the ORM `TipoArqueo` row.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_resolver_tipo_arqueo_por_uuid_returns_vigente_row` — seed `prod.tipo_arqueo(uuid=:t, codigo='auditoria', vigente_hasta=NULL)`; invoke → returns the row.
    - T2: `test_resolver_tipo_arqueo_por_uuid_raises_when_missing` — random UUID; helper raises `TipoArqueoNoEncontradoError(uuid_tipo_arqueo=str(<random>))`.
    - T3: `test_resolver_tipo_arqueo_por_uuid_uses_with_for_update` — verify SQL contains `FOR UPDATE` (KD-ARQUEO-08 + DEC-ARQUEO-09 exclusive lock, NOT `FOR SHARE` which F1.9 used on `prod.tarifas_sucursal`).
  - **Acción**: extend T2.1 file (`backend/tests/unit/test_arqueo_repo.py`) with +~30 LOC, 3 tests. — **Validación**: pre-implementation `ImportError: cannot import name 'resolver_tipo_arqueo_por_uuid'`.

- [x] **T-HU-F1.13-T2.3** [RED + GREEN] — Implement `resolver_tolerancia_vigente` (V3, ~15 LOC) + `validar_sesion_abierta_para_arqueo` (V4, ~15 LOC) + `es_descuadre_critico` (V7 DEC-ARQUEO-04 pure Decimal math, ~10 LOC) + `calcular_diferencia` helper (~5 LOC, returns tuple).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1` for tolerance + sesion; pure Decimal math for `es_descuadre_critico`):
    - T1: `test_resolver_tolerancia_vigente_branch_overrides_global` — seed branch row + global row; invoke with branch UUID → returns branch row (bi-temporal vigente lookup).
    - T2: `test_resolver_tolerancia_vigente_falls_back_to_global` — only global row exists; invoke with branch UUID → returns global row (NULL uuid_sucursal pattern).
    - T3: `test_resolver_tolerancia_vigente_raises_when_no_vigente` — no vigente row; raises `ToleranciaNoConfiguradaError(uuid_sucursal=str(uuid))`.
    - T4: `test_validar_sesion_abierta_para_arqueo_returns_open_sesion` — seed sesion with `estado='abierta', timestamp_cierre IS NULL`; invoke → returns sesion object.
    - T5: `test_validar_sesion_abierta_para_arqueo_raises_when_closed` — sesion with `timestamp_cierre='2026-09-14T18:30:00Z'`; raises `SesionYaCerradaError(uuid_sesion=str(uuid))`.
    - T6: `test_es_descuadre_critico_sobre_tolerancia_returns_true` — `diferencia_efectivo=150, tolerancia_efectivo=100` → True (|150| > 100).
    - T7: `test_es_descuadre_critico_igual_tolerancia_returns_false` — `diferencia_efectivo=100, tolerancia_efectivo=100` → False (strict inequality `>`, NOT `>=`; REQ-OPS-093 Scenario 3).
    - T8: `test_es_descuadre_critico_dentro_tolerancia_returns_false` — `diferencia_efectivo=50, tolerancia_efectivo=100` → False (|50| < 100).
  - **Archivo**: extend `repo/arqueo.py` (+~45 LOC); extend T2.1 file with +~50 LOC, 8 tests. — **Validación**: T1..T8 PASS.

- [x] **T-HU-F1.13-T2.4** [RED + GREEN] — Implement `calcular_esperado_sesion` (V5a, ~20 LOC) + `calcular_esperado_cierre_dia` (V5b, ~20 LOC) + `insertar_arqueo` (V8 KD-ARQUEO-02 via `append_event`, ~15 LOC) + `insertar_alerta_descuadre_critico` (V10 KD-ARQUEO-05 via `append_transition`, ~20 LOC) + `cerrar_sesiones_del_dia_bulk` (V9 KD-ARQUEO-03 iterating `close_session_with_log`, ~25 LOC) + `listar_sesiones_del_dia` (G3, ~15 LOC) + `listar_sesiones_abiertas_del_dia` (V9 helper, ~15 LOC) + `construir_resumen_sesion` (G4, ~20 LOC) + `obtener_cierre_dia_del_dia` (G5, ~15 LOC).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1` for helpers that touch DB; pure Decimal math for `calcular_diferencia`):
    - T1: `test_calcular_esperado_sesion_sums_factura_pagos_by_medio_pago` — seed sesion + 2 factura_pagos (efectivo + tarjeta); invoke → returns `(valor_inicial_efectivo + SUM(efectivo), valor_inicial_datafono + SUM(tarjeta, datafono))` (DEC-ARQUEO-10).
    - T2: `test_calcular_esperado_cierre_dia_aggregates_all_open_sesiones` — seed 3 open sesiones + factura_pagos for each; invoke → returns aggregate across all (cierre_dia path, DEC-ARQUEO-10).
    - T3: `test_insertar_arqueo_calls_append_event` — verify helper calls `repo.append_only.append_event(session, tabla='arqueo', ...)`; AST walk on helper body confirms NO raw `session.execute(insert(Arqueo))`.
    - T4: `test_insertar_alerta_descuadre_critico_calls_append_transition` — verify helper calls `repo.workflow.append_transition(session, tabla='alerta', tipo_alerta='descuadre_critico', ...)`; AST walk confirms NO raw `session.execute(insert(Alerta))`.
    - T5: `test_cerrar_sesiones_del_dia_bulk_iterates_per_open_sesion` — seed 3 sesiones (2 closed + 1 open); invoke → calls `close_session_with_log` exactly 1 time (NOT 3); REQ-OPS-092 Scenario 2.
    - T6: `test_cerrar_sesiones_del_dia_bulk_calls_close_session_with_log` — AST walk on helper body confirms presence of `close_session_with_log` call AND absence of `session.execute(update(Sesion))` (KD-ARQUEO-03).
    - T7: `test_listar_sesiones_del_dia_filters_by_sucursal_and_fecha` — seed 5 sesiones (3 at target + 2 elsewhere); invoke with target → returns 3 rows.
    - T8: `test_construir_resumen_sesion_includes_factura_pagos_sum` — seed sesion + arqueo + factura_pagos; invoke → returns `ArqueoResumenItem` with `valor_efectivo_esperado = valor_inicial_efectivo + SUM(...)`.
    - T9: `test_obtener_cierre_dia_del_dia_returns_aggregate` — seed cierre_dia arqueo (uuid_sesion=NULL); invoke → returns `ArqueoResumenItem(uuid_sesion=None)`.
  - **Archivo**: extend `repo/arqueo.py` (+~165 LOC); extend T2.1 file with +~70 LOC, 9 tests. — **Validación**: T1..T9 PASS; `__all__` now exposes all 13 helpers + 6 exceptions.

  **Commit suggestion (T2.1..T2.4)**: `feat(backend): HU-F1.13 — repo/arqueo.py 13 typed helpers + 6 typed exceptions (KD-ARQUEO-02/03/05/06/08 helpers)`.

- [x] **T-HU-F1.13-T2.5** [RED + GREEN] — Extend `schemas/caja.py` (~90 LOC) with `ArqueoCreateV2(_Base)` request + `ArqueoReadForHandler(_Base)` POST response + `ArqueoResumenItem(_Base)` per-sesion row + `ArqueoResumenRead(_Base)` GET response + `CierreDiarioQueryParams(_Base)` GET query params + 6 typed error schemas. All inherit `extra='forbid'` from `_Base` (Layer 4 defense).
  - **Tests** (pure Pydantic validation, no HTTP, no DB):
    - T1: `test_arqueo_create_v2_rejects_uuid_usuario_injection` — `ArqueoCreateV2(..., uuid_usuario='uuid')` raises `ValidationError` (extra='forbid').
    - T2: `test_arqueo_create_v2_rejects_fecha_retencion_hasta_injection` — `ArqueoCreateV2(..., fecha_retencion_hasta='2026-09-30')` raises `ValidationError`.
    - T3: `test_arqueo_create_v2_rejects_alerta_generada_injection` — `ArqueoCreateV2(..., alerta_generada=true)` raises `ValidationError`.
    - T4: `test_arqueo_create_v2_accepts_valid_payload` — `ArqueoCreateV2(uuid_tipo_arqueo=<uuid>, uuid_sesion=<uuid>, valor_efectivo_reportado=Decimal('148000'), valor_datafono_reportado=Decimal('320000'), justificacion='OK')` accepts.
    - T5: `test_arqueo_create_v2_accepts_uuid_sesion_null_for_cierre_dia` — `ArqueoCreateV2(..., uuid_sesion=None)` accepts.
    - T6: `test_arqueo_read_for_handler_codigo_tipo_arqueo_literal` — `ArqueoReadForHandler(..., codigo_tipo_arqueo='auditoria')` accepts; `'foo'` rejected.
    - T7: `test_arqueo_resumen_read_has_sesiones_and_cierre_dia_fields` — `ArqueoResumenRead(fecha=date.today(), uuid_sucursal=<uuid>, sesiones=[], cierre_dia=None)` accepts.
    - T8: `test_cierre_diario_query_params_requires_uuid_sucursal_and_fecha` — both required; missing either → `ValidationError`.
    - T9: `test_typed_error_tipo_arqueo_no_encontrado_carries_uuid` — `TipoArqueoNoEncontradoError(error='tipo_arqueo_no_encontrado', uuid_tipo_arqueo='<uuid>')` accepts.
    - T10: `test_typed_error_justificacion_requerida_carries_no_context` — `JustificacionRequeridaError(error='justificacion_requerida')` accepts (no contextual fields).
  - **Patrón F1.11 + F1.12** (`test_reimpresion_ticket_schemas.py` + `test_venta_suscripcion_schemas.py`): pure Pydantic tests, no HTTP, no DB.
  - **Acción**: extend T2.1 file (NEW `backend/tests/unit/test_arqueo_schemas.py`, ~30 LOC, 10 tests). — **Validación**: pre-implementation `ImportError` for the schema names.

  **Commit suggestion**: `feat(backend): HU-F1.13 — Pydantic schemas (ArqueoCreateV2 + 4 responses + 6 typed errors in schemas/caja.py)`.

  **Exit criteria T2**: T2.1..T2.5 verde; ~270 LOC cumulative; 13 helpers + 6 exceptions + 5 schemas + 6 typed errors exposed; `__all__` lists all 19 names.

### Cluster T3 — POST `/api/v1/caja/arqueo` Handler (~180 LOC impl + e2e in T5)

- [x] **T-HU-F1.13-T3.1** [RED + GREEN] — Stub `api/v1/caja_arqueo.py::post_arqueo` with KD-3 issuer dep (`_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")`) + `Idempotency-Key` middleware guard; write failing source-level test asserting the endpoint is NOT yet registered (404).
  - **Tests** (pure source-level + HTTP integration gated):
    - T1: `test_caja_arqueo_module_imports_with_post_arqueo_handler` — `from parkos_core.api.v1.caja_arqueo import router` succeeds; `dir(router)` does NOT yet contain `post_arqueo` (RED pre-implementation).
    - T2: `test_endpoint_arqueo_not_yet_registered` — HTTP GET against `/api/v1/caja/arqueo` returns 404 (route fully absent); test asserts 404.
  - **Patrón F1.11 + F1.12** (`test_reimpresion_ticket_create_handler.py` + `test_venta_suscripcion_e2e.py`): pure source-level + `httpx.AsyncClient + ASGITransport(app)`.
  - **Acción**: create stub module with `router = APIRouter(prefix="/caja", tags=["caja"])` + `from __future__ annotations` + import `_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-ARQUEO-05). — **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py` (nuevo, stub, ~10 LOC). — **Validación**: stub module imports; route returns 404.

- [x] **T-HU-F1.13-T3.2** [GREEN] — Implement Steps 1-7 of the 12-step chain in `post_arqueo` (~80 LOC): Step 1 V1 `resolver_tipo_arqueo_por_uuid` with SELECT FOR UPDATE (KD-ARQUEO-08 + DEC-ARQUEO-09) + 404 mapping for `TipoArqueoNoEncontradoError`; Step 2 V2 cierre_dia cross-validation (400 `cierre_dia_no_acepta_uuid_sesion` + 400 `sesion_requerida_para_auditoria_o_cierre_turno`); Step 2a Layer 2 tenant scope post-V1 (KD-S2 analog from F1.7); Step 3 V3 `resolver_tolerancia_vigente` (404 `tolerancia_no_configurada`); Step 4 V4 `validar_sesion_abierta_para_arqueo` (409 `sesion_ya_cerrada`); Step 5 V5 `calcular_esperado_sesion` OR `calcular_esperado_cierre_dia` + diferencia compute; Step 6 V6 justificacion check (400 `justificacion_requerida` per DEC-ARQUEO-07); Step 7 V7 `es_descuadre_critico`.
  - **Archivo**: extend `api/v1/caja_arqueo.py` (+~80 LOC).
  - **Contenido** (verbatim per design §4 step 1-7 + §10.1):
    ```python
    @router.post(
        "/arqueo",
        response_model=ArqueoReadForHandler,
        status_code=201,
        responses={
            400: {"model": CierreDiaNoAceptaSesionError},
            403: {"model": TenantScopeViolationError},
            404: {"model": TipoArqueoNoEncontradoError},
            409: {"model": SesionYaCerradaError},
        },
    )
    async def post_arqueo(
        response: Response,
        payload: ArqueoCreateV2,
        session: AsyncSession = Depends(get_session),
        ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(_caja_arqueo_issuer_dep),
    ) -> ArqueoReadForHandler:
        no_store = no_store_headers()

        # Step 1 (KD-ARQUEO-08 + DEC-ARQUEO-09): SELECT FOR UPDATE on prod.tipo_arqueo
        tipo_arqueo = await repo_arqueo.resolver_tipo_arqueo_por_uuid(
            session, uuid_tipo_arqueo=payload.uuid_tipo_arqueo
        )
        if tipo_arqueo is None:
            raise HTTPException(404, {"error": "tipo_arqueo_no_encontrado", "uuid_tipo_arqueo": str(payload.uuid_tipo_arqueo)}, headers=no_store)

        # Step 2 (V2): cierre_dia MUST have uuid_sesion NULL; otherwise required
        if tipo_arqueo.codigo == "cierre_dia" and payload.uuid_sesion is not None:
            raise HTTPException(400, {"error": "cierre_dia_no_acepta_uuid_sesion"}, headers=no_store)
        if tipo_arqueo.codigo != "cierre_dia" and payload.uuid_sesion is None:
            raise HTTPException(400, {"error": "sesion_requerida_para_auditoria_o_cierre_turno"}, headers=no_store)

        # Layer 2 — Tenant scope post-V1
        target_sucursal = ctx.sucursal_uuid

        # Step 3 (V3): tolerance vigente row by target_sucursal
        tolerancia = await repo_arqueo.resolver_tolerancia_vigente(session, uuid_sucursal=target_sucursal)
        if tolerancia is None:
            raise HTTPException(404, {"error": "tolerancia_no_configurada", "uuid_sucursal": str(target_sucursal)}, headers=no_store)

        # Step 4 (V4): validate sesion is open (when not cierre_dia)
        if payload.uuid_sesion is not None:
            sesion = await repo_arqueo.validar_sesion_abierta_para_arqueo(session, uuid_sesion=payload.uuid_sesion, target_sucursal=target_sucursal)
            if sesion is None:
                raise HTTPException(409, {"error": "sesion_ya_cerrada", "uuid_sesion": str(payload.uuid_sesion)}, headers=no_store)

        # Step 5 (V5 + DEC-ARQUEO-04 + DEC-ARQUEO-10): compute esperado + diferencia
        if tipo_arqueo.codigo == "cierre_dia":
            esperado_efectivo, esperado_datafono = await repo_arqueo.calcular_esperado_cierre_dia(session, target_sucursal=target_sucursal, fecha=date.today())
        else:
            esperado_efectivo, esperado_datafono = await repo_arqueo.calcular_esperado_sesion(session, uuid_sesion=payload.uuid_sesion)
        diferencia_efectivo = payload.valor_efectivo_reportado - esperado_efectivo
        diferencia_datafono = payload.valor_datafono_reportado - esperado_datafono

        # Step 6 (DEC-ARQUEO-07): justificacion required when diferencia != 0 in cierre paths
        if tipo_arqueo.codigo != "auditoria" and (diferencia_efectivo != 0 or diferencia_datafono != 0):
            if not payload.justificacion:
                raise HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store)

        # Step 7 (DEC-ARQUEO-04 + KD-ARQUEO-04): descuadre decision
        es_critico = repo_arqueo.es_descuadre_critico(
            diferencia_efectivo=diferencia_efectivo,
            diferencia_datafono=diferencia_datafono,
            tolerancia_efectivo=tolerancia.tolerancia_efectivo,
            tolerancia_datafono=tolerancia.tolerancia_datafono,
        )
    ```
  - **Acción**: docstring REQ-OPS-091..097 + DEC-ARQUEO-01..08 + KD-ARQUEO-01..05. — **Validación**: T3.1 2 tests PASS (route now registered); T5.4 mandated tests exercise Steps 1-7 paths.

- [x] **T-HU-F1.13-T3.3** [GREEN] — Implement Steps 8-12 (rest of writes + commit, ~80 LOC): Step 8 V8 `insertar_arqueo` (KD-ARQUEO-02 via `append_event`) + descuadre_pct informational; Step 9 V9 `cerrar_sesiones_del_dia_bulk` (DEC-ARQUEO-03 + KD-ARQUEO-03 iterating `close_session_with_log`) — `cierre_dia` path only; Step 10 V10 conditional `insertar_alerta_descuadre_critico` (KD-ARQUEO-05 + DEC-ARQUEO-05); Step 12 ONE `await session.commit()` (KD-ARQUEO-01 single-commit); Step 13 `apply_no_store_header(response)` + return `ArqueoReadForHandler`.
  - **Archivo**: extend `api/v1/caja_arqueo.py` (+~80 LOC).
  - **Contenido** (verbatim per design §4 step 8-13 + §10.1):
    ```python
        # Step 8 (KD-ARQUEO-02 + DEC-ARQUEO-02): INSERT prod.arqueo [A] via append_event
        descuadre_pct = None  # informational only (DEC-ARQUEO-04)
        if esperado_efectivo + esperado_datafono > 0:
            descuadre_pct = ((diferencia_efectivo + diferencia_datafono) / (esperado_efectivo + esperado_datafono)) * 100
        uuid_arqueo = await repo_arqueo.insertar_arqueo(
            session, actor_uuid=ctx.actor_uuid, uuid_tipo_arqueo=tipo_arqueo.uuid,
            uuid_sesion=payload.uuid_sesion, valor_efectivo_esperado=esperado_efectivo,
            valor_datafono_esperado=esperado_datafono, valor_efectivo_reportado=payload.valor_efectivo_reportado,
            valor_datafono_reportado=payload.valor_datafono_reportado,
            diferencia_efectivo=diferencia_efectivo, diferencia_datafono=diferencia_datafono,
            descuadre_pct=descuadre_pct, justificacion=payload.justificacion,
        )

        # Step 9 (DEC-ARQUEO-03 + KD-ARQUEO-03): cierre_dia path only — close all open sesiones
        if tipo_arqueo.codigo == "cierre_dia":
            await repo_arqueo.cerrar_sesiones_del_dia_bulk(
                session, actor_uuid=ctx.actor_uuid, target_sucursal=target_sucursal, fecha=date.today()
            )

        # Step 10 (KD-ARQUEO-05 + DEC-ARQUEO-05): conditional alerta INSERT via append_transition
        alerta_uuid = None
        alerta_generada = False
        if es_critico:
            alerta_uuid = await repo_arqueo.insertar_alerta_descuadre_critico(
                session, actor_uuid=ctx.actor_uuid, uuid_arqueo=uuid_arqueo,
                uuid_sucursal=target_sucursal, diferencia_efectivo=diferencia_efectivo,
                diferencia_datafono=diferencia_datafono, payload_json={
                    "diferencia_efectivo": str(diferencia_efectivo),
                    "diferencia_datafono": str(diferencia_datafono),
                    "tolerancia_efectivo": str(tolerancia.tolerancia_efectivo),
                    "tolerancia_datafono": str(tolerancia.tolerancia_datafono),
                    "descuadre_pct": str(descuadre_pct) if descuadre_pct else None,
                    "codigo_tipo_arqueo": tipo_arqueo.codigo,
                    "uuid_sesion": str(payload.uuid_sesion) if payload.uuid_sesion else None,
                },
            )
            alerta_generada = True

        # Step 12: KD-ARQUEO-01 SINGLE COMMIT (RESOLVES R1 HIGH)
        await session.commit()

        # Step 13: DEC-ARQUEO-06 — Cache-Control: no-store + response shape
        apply_no_store_header(response)
        return ArqueoReadForHandler(
            uuid=uuid_arqueo,
            uuid_tipo_arqueo=tipo_arqueo.uuid,
            codigo_tipo_arqueo=tipo_arqueo.codigo,
            uuid_sesion=payload.uuid_sesion,
            valor_efectivo_esperado=esperado_efectivo,
            valor_datafono_esperado=esperado_datafono,
            valor_efectivo_reportado=payload.valor_efectivo_reportado,
            valor_datafono_reportado=payload.valor_datafono_reportado,
            diferencia_efectivo=diferencia_efectivo,
            diferencia_datafono=diferencia_datafono,
            descuadre_pct=descuadre_pct,
            alerta_generada=alerta_generada,
            alerta_uuid=alerta_uuid,
        )
    ```
  - **Acción**: docstring KD-ARQUEO-01 single-commit invariant + DEC-ARQUEO-06 no-store + DEC-ARQUEO-03 cierre_dia path. — **Validación**: T5.4 mandated tests + T5.6 e2e exercise the full path.

- [x] **T-HU-F1.13-T3.4** [GREEN] — Dedicated `APIRouter` mount in `api/v1/caja_arqueo.py` + register in `api/v1/caja.py::__init__.py`. Append `from .caja_arqueo import router as caja_arqueo_router` + `router.include_router(caja_arqueo_router)` (DEC-ARQUEO-05). Mount extension: ~5 LOC.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` (modified, +~5 LOC); no modification to `__init__.py` (the factory mount is inherited).
  - **Acción**: append at bottom of `caja.py` after the existing `make_router(resource='caja')` factory mount. — **Validación**: T5.6 e2e confirms endpoint reachable at `/api/v1/caja/arqueo` POST.

  **Commit suggestion**: `feat(backend): HU-F1.13 — POST /caja/arqueo handler (12-step chain + KD-ARQUEO-01 single-commit + router mount)`.

  **Exit criteria T3**: T3.1..T3.4 verde; ~450 LOC cumulative (impl + tests); handler reachable end-to-end; 12-step chain enforces KD-ARQUEO-01 single-commit + KD-ARQUEO-08 lock ordering + DEC-ARQUEO-03 cierre_dia session_cycle + DEC-ARQUEO-06 no-store.

### Cluster T4 — GET `/api/v1/caja/arqueo/resumen` Handler (~60 LOC impl + tests in T5)

- [x] **T-HU-F1.13-T4.1** [GREEN] — Implement `get_arqueo_resumen` 6-step chain (~50 LOC): Step 1 Layer 1 issuer dep + permission gate (KD-3 + GAP-BE-05 `realizar_arqueo`); Step 2 Layer 2 tenant scope post-V1 (403 `tenant_scope_violation` if `operador-` cross-branch); Step 3 G3 `listar_sesiones_del_dia(session, uuid_sucursal=params.uuid_sucursal, fecha=params.fecha)` (returns list even if empty — NOT 404); Step 4 G4 per-sesion `construir_resumen_sesion(session, sesion=sesion)` (aggregate arqueo + factura_pagos SUM); Step 5 G5 `obtener_cierre_dia_del_dia(session, uuid_sucursal=params.uuid_sucursal, fecha=params.fecha)` (KD-ARQUEO-07 + DEC-ARQUEO-10); Step 6 G6 build `ArqueoResumenRead` + `apply_no_store_header(response)` + return.
  - **Archivo**: extend `api/v1/caja_arqueo.py` (+~50 LOC).
  - **Contenido** (verbatim per design §10.2):
    ```python
    @router.get(
        "/arqueo/resumen",
        response_model=ArqueoResumenRead,
        status_code=200,
    )
    async def get_arqueo_resumen(
        response: Response,
        params: CierreDiarioQueryParams = Depends(),
        session: AsyncSession = Depends(get_session),
        ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(_caja_resumen_issuer_dep),
    ) -> ArqueoResumenRead:
        no_store = no_store_headers()

        # Step 1+2: Layer 2 tenant scope
        if ctx.issuer_prefix == "operador-" and ctx.sucursal_uuid is not None and ctx.sucursal_uuid != params.uuid_sucursal:
            raise HTTPException(403, {"error": "tenant_scope_violation"}, headers=no_store)

        # Step 3: list sesiones of the day at branch
        sesiones = await repo_arqueo.listar_sesiones_del_dia(
            session, uuid_sucursal=params.uuid_sucursal, fecha=params.fecha
        )

        # Step 4: aggregate arqueo per sesion
        items: list[ArqueoResumenItem] = []
        for sesion in sesiones:
            item = await repo_arqueo.construir_resumen_sesion(session, sesion=sesion)
            items.append(item)

        # Step 5: cierre_dia aggregate (if exists for this fecha+sucursal)
        cierre_dia = await repo_arqueo.obtener_cierre_dia_del_dia(
            session, uuid_sucursal=params.uuid_sucursal, fecha=params.fecha
        )

        # Step 6: build ArqueoResumenRead + apply no-store
        resumen = ArqueoResumenRead(
            fecha=params.fecha,
            uuid_sucursal=params.uuid_sucursal,
            sesiones=items,
            cierre_dia=cierre_dia,
        )
        apply_no_store_header(response)
        return resumen
    ```
  - **Acción**: docstring REQ-OPS-097 + DEC-ARQUEO-06 + DEC-ARQUEO-07 + KD-ARQUEO-07. Define `_caja_resumen_issuer_dep = requires_issuer("operador-", "admin-")` (same issuer dep as POST). — **Validación**: T5.5 unit tests cover happy path + cierre_dia aggregate + empty day.

- [x] **T-HU-F1.13-T4.2** [GREEN] — Verify `get_arqueo_resumen` returns 200 OK with `Cache-Control: no-store` (DEC-ARQUEO-06) on every response including 200 (success) + 403 (tenant scope) + 422 (missing query params via Pydantic) + 5xx (defense in depth).
  - **Acción**: no source-level changes; verifies via T5.5 unit tests asserting the response header on each status code path. — **Validación**: T5.5 unit tests PASS.

  **Commit suggestion**: `feat(backend): HU-F1.13 — GET /caja/arqueo/resumen handler (6-step chain + cierre_dia aggregate)`.

  **Exit criteria T4**: T4.1..T4.2 verde; ~510 LOC cumulative (impl + tests); GET handler reachable end-to-end.

### Cluster T5 — Static AST walks + Tests (~220 LOC tests)

- [x] **T-HU-F1.13-T5.1** [RED + GREEN] — Write failing AST walk `tests/static/test_arqueo_handler_single_commit.py` enforcing KD-ARQUEO-01 single `await session.commit()` invariant (mirror of F1.10 `test_fe_handler_single_commit.py` + F1.11 `test_workflow_handler_single_commit.py` + F1.12 `test_venta_handler_single_commit.py`).
  - **Tests** (no DB, no HTTP, pure AST walk):
    - T1: `test_arqueo_single_commit_invariant` — `ast.parse(api/v1/caja_arqueo.py)`; locate `post_arqueo` via `ast.AsyncFunctionDef.name == 'post_arqueo'`; walk via `iter_child_nodes`; assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'commit']) == 1` (exactly one `await session.commit()` call).
    - T2: `test_arqueo_no_savepoint` — same walk; assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'begin_nested']) == 0`; assert NO occurrence of the literal string `"SAVEPOINT"` in the handler body.
  - **Patrón F1.10 + F1.11 + F1.12**: `ast.parse` + `iter_child_nodes` DFS.
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_arqueo_handler_single_commit.py` (nuevo, ~15 LOC, 2 AST walks). — **Validación**: post T3 GREEN, walks PASS.

- [x] **T-HU-F1.13-T5.2** [RED + GREEN] — Write failing AST walks `tests/static/test_arqueo_handler_no_raw_dml.py` (DEC-ARQUEO-02 + DEC-ARQUEO-05 enforcement, no raw INSERT/UPDATE/DELETE on `[A]`/`[V]` tables outside helpers) + `tests/static/test_arqueo_handler_no_update_on_a_tables.py` (KD-ARQUEO-02 enforcement, no UPDATE on user-meaningful fields of `[A]` tables in handler body).
  - **Tests** (no DB, no HTTP, source-level grep + AST walk):
    - T1: `test_arqueo_handler_no_raw_dml_on_a_tables` — read `api/v1/caja_arqueo.py` source; assert no occurrence of `INSERT INTO prod.arqueo`, `UPDATE prod.arqueo`, `DELETE FROM prod.arqueo`, `INSERT INTO prod.alerta`, `INSERT INTO prod.factura_pagos` patterns; allowed: `repo_arqueo.insertar_arqueo` + `repo_arqueo.insertar_alerta_descuadre_critico` helper calls.
    - T2: `test_arqueo_handler_no_raw_dml_on_v_tables` — assert no occurrence of `INSERT INTO prod.tipo_arqueo`, `UPDATE prod.tipo_arqueo`, `DELETE FROM prod.tipo_arqueo`, `INSERT INTO prod.configuracion_tolerancias` patterns.
    - T3: `test_arqueo_handler_no_update_on_a_tables` — assert no UPDATE on `[A]` tables (`prod.arqueo`, `prod.alerta`, `prod.factura_pagos`, `prod.alert_types`, `prod.log_transaccional`) outside the `repo.append_only` + `repo.workflow` + `repo.session_cycle` helpers.
  - **Patrón F1.5 PR5-016** (`test_no_raw_dml_on_a_tables.py` + F1.12 `test_venta_handler_no_raw_dml.py`): source-level grep + regex match.
  - **Acción**: import `re`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_arqueo_handler_no_raw_dml.py` (nuevo, ~20 LOC, 2 tests); `backend/tests/static/test_arqueo_handler_no_update_on_a_tables.py` (nuevo, ~15 LOC, 1 test). — **Validación**: post T3 GREEN, walks PASS.

- [x] **T-HU-F1.13-T5.3** [RED + GREEN] — Write failing AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (KD-ARQUEO-03 NEW walk — no precedent) enforcing that `post_arqueo` for `cierre_dia` codigo calls `repo.session_cycle.close_session_with_log` (NOT direct `session.execute(update(Sesion))`).
  - **Tests** (no DB, no HTTP, source-level grep + AST walk):
    - T1: `test_cierre_dia_branch_calls_close_session_with_log` — locate `post_arqueo` handler body; locate `if tipo_arqueo.codigo == "cierre_dia":` branch (or equivalent); assert at least one call to `close_session_with_log` within the branch (KD-ARQUEO-03 + DEC-ARQUEO-03).
    - T2: `test_cierre_dia_branch_no_raw_update_sesion` — within the `cierre_dia` branch, assert NO occurrence of `update(Sesion)` or `text("UPDATE prod.sesion ...")` or `session.execute(update(Sesion))` (KD-ARQUEO-03 enforcement).
    - T3: `test_handler_no_update_sesion_anywhere` — entire handler body (not just cierre_dia branch) MUST NOT contain raw `session.execute(update(Sesion))` or `text("UPDATE prod.sesion ...")` patterns (defense in depth).
  - **Patrón F1.12** (KD-VENTA-05 precedent): source-level grep + AST walk.
  - **Acción**: import `ast`, `re`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (nuevo, ~15 LOC, 3 AST walks). — **Validación**: post T3 GREEN + T4 GREEN, walks PASS.

  **Commit suggestion**: `feat(static): HU-F1.13 — AST walks (KD-ARQUEO-01 single-commit + DEC-ARQUEO-02 no raw DML + KD-ARQUEO-03 cierre_dia session_cycle + KD-ARQUEO-02 no UPDATE on [A])`.

- [x] **T-HU-F1.13-T5.4** [RED + GREEN] — Write `tests/unit/test_arqueo_handler.py` with **4 MANDATED tests per plan.md line 1093**: `test_sin_diferencia_arqueo_exitoso` + `test_diferencia_justificada_arqueo_exitoso` + `test_descuadre_sobre_tolerancia_genera_alerta` + `test_diferencia_sin_justificacion_400`. Plus DEC-ARQUEO-06 `Cache-Control: no-store` tests for REQ-OPS-091 Scenario 1 + XR6 Layer 5.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_sin_diferencia_arqueo_exitoso_returns_201` — happy path, `auditoria` codigo, `valor_efectivo_reportado=148000` (= esperado), `justificacion=null` → 201 + `ArqueoReadForHandler{uuid:<new>, alerta_generada=false, alerta_uuid=null}` + `Cache-Control: no-store`. Verify exactly 1 `prod.arqueo` row exists.
    - T2: `test_diferencia_justificada_arqueo_exitoso_returns_201` — `cierre_turno` codigo + `|diferencia_efectivo| < tolerancia_efectivo` (50 < 100) + `justificacion='Vueltos'` → 201 + `alerta_generada=false` (NOT a descuadre — within tolerance). Verify exactly 1 `prod.arqueo` row + 1 `prod.log_transaccional` row exist; ZERO `prod.alerta` rows.
    - T3: `test_descuadre_sobre_tolerancia_genera_alerta_returns_201_with_alerta` — `cierre_turno` codigo + `|diferencia_efectivo| > tolerancia_efectivo` (150 > 100) + `justificacion='Vueltos'` → 201 + `alerta_generada=true` + `alerta_uuid=<new>`. Verify exactly 1 `prod.arqueo` + 1 `prod.alerta` + 2 `prod.log_transaccional` rows exist.
    - T4: `test_diferencia_sin_justificacion_returns_400` — `cierre_turno` codigo + `diferencia_efectivo=50` (within tolerance but != 0) + `justificacion=null` → 400 `justificacion_requerida` + `Cache-Control: no-store`. Verify ZERO `prod.arqueo` rows exist (Step 6 short-circuits).
    - T5: `test_auditoria_con_diferencia_sin_justificacion_accepted` — DEC-ARQUEO-07 asymmetry: `auditoria` codigo + `diferencia_efectivo=50` (within tolerance) + `justificacion=null` → 201 (advertencia only).
    - T6: `test_cierre_dia_no_acepta_uuid_sesion_returns_400` — `cierre_dia` codigo + `uuid_sesion=<some>` → 400 `cierre_dia_no_acepta_uuid_sesion`.
    - T7: `test_sesion_ya_cerrada_returns_409` — `cierre_turno` + `uuid_sesion` referencing closed sesion → 409 `sesion_ya_cerrada`.
    - T8: `test_tipo_arqueo_no_encontrado_returns_404` — random `uuid_tipo_arqueo` → 404 `tipo_arqueo_no_encontrado`.
    - T9: `test_tolerancia_no_configurada_returns_404` — DELETE global tolerancia + branch tolerancia; → 404 `tolerancia_no_configurada`.
    - T10: `test_tenant_scope_violacion_returns_403` — `operador-` issuer with `ctx.sucursal_uuid=:s_other != :s_target` → 403 `tenant_scope_violation`.
    - T11: `test_permission_denied_returns_403` — `operador-` role with `emitir_factura` only (NOT `realizar_arqueo`) → 403 `permission_denied` (after GAP-BE-05 fix; pre-fix this test would FAIL).
  - **Patrón F1.11 + F1.12** (`test_reimpresion_ticket_create_handler.py` + `test_venta_suscripcion.py`): `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-X` fixture; real `pg_engine` con `PARKOS_DOCKER_TEST=1`.
  - **Archivo**: `backend/tests/unit/test_arqueo_handler.py` (nuevo, ~50 LOC, **4 MANDATED tests per plan.md line 1093** + 7 extra Cache-Control no-store + asymmetry tests for REQ-OPS-091 + XR6). — **Validación**: post T3 GREEN + T-GAP-BE-05 applied, all 11 tests PASS.

- [x] **T-HU-F1.13-T5.5** [RED + GREEN] — Write `tests/unit/test_arqueo_repo.py` (extend T2.1 file with full coverage) + `tests/unit/test_cierre_dia.py` (~40 LOC, 2 tests for cierre_dia path: 3-sesiones-2cerradas-1abieta + uuid_sesion_en_body_400) + `tests/unit/test_arqueo_resumen.py` (~30 LOC, 3 tests for empty day / single sesion with arqueo / cierre_dia aggregate at bottom).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - **T1 (test_arqueo_repo.py, ~50 LOC, 5 tests)** — `resolver_tipo_arqueo_por_uuid` (vigente + non-vigente + UUID malformed); `resolver_tolerancia_vigente` (branch + global fallback); `calcular_esperado_sesion` (sum by `medio_pago`); `validar_sesion_abierta_para_arqueo` (open + already-closed + not-found); `es_descuadre_critico` (sobre_tolerancia + igual_tolerancia + dentro_tolerancia).
    - **T2 (test_cierre_dia.py, ~40 LOC, 2 tests)**:
      - T2.1: `test_cierre_dia_masivo_3_sesiones_2_cerradas_1_abierta` — verifies that only the open sesion is closed, others already closed are skipped, arqueo `uuid_sesion=NULL` is INSERTed.
      - T2.2: `test_cierre_dia_no_acepta_uuid_sesion_returns_400` — POST with `codigo='cierre_dia'` + `uuid_sesion=...` → 400.
    - **T3 (test_arqueo_resumen.py, ~30 LOC, 3 tests)**:
      - T3.1: `test_resumen_dia_vacio_returns_200_with_empty_sesiones` — empty day, `sesiones=[]`, `cierre_dia=None` + `Cache-Control: no-store`.
      - T3.2: `test_resumen_dia_single_sesion_with_arqueo` — 1 sesion + 1 arqueo → 1 item with computed esperado.
      - T3.3: `test_resumen_dia_con_cierre_dia_aggregate` — N sesiones + 1 cierre_dia arqueo → N items + cierre_dia aggregate at bottom (KD-ARQUEO-07).
  - **Acción**: 3 NEW test files + extend existing T2.1 file with full coverage. — **Validación**: ~9 tests across 3 files PASS post T2 + T3 + T4 GREEN.

- [x] **T-HU-F1.13-T5.6** [RED + GREEN] — Write `tests/integration/test_arqueo_e2e.py` (~30 LOC, 1 test: full happy path with cierre_dia codigo + verify all rows visible post-commit: 1 arqueo + N sesiones cerradas + 1 cierre_dia alert optionally + N+2 log_transaccional rows) + extend `tests/integration/test_migration_0031_idempotency.py` (T1.1 partial) with full idempotency round-trip test.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - **T1 (test_arqueo_e2e.py, ~30 LOC, 1 test)**: `test_arqueo_e2e_full_happy_path_cierre_dia` — seed `prod.tipo_arqueo(uuid=:cierre_dia)` + `prod.configuracion_tolerancias(uuid_sucursal=:s)` + `prod.sesion(:ses1, :ses2)` (open) + `prod.factura_pagos` rows + `prod.permisos(:realizar_arqueo)` + `prod.permisos_usuario` + operador JWT. POST `{uuid_tipo_arqueo:<:cierre_dia>, uuid_sesion:null, valor_efectivo_reportado:<sum>, valor_datafono_reportado:<sum>, justificacion:'Cierre diario OK'}` with `Idempotency-Key: <uuid>` → 201. Verify exactly 1 `prod.arqueo` row + 2 `prod.sesion` rows UPDATEd to `estado='cerrada'` + 4 `prod.log_transaccional` rows (1 per arqueo + 1 per sesion UPDATE) + response shape correct + `Cache-Control: no-store`.
    - **T2 (test_migration_0031_idempotency.py, extend T1.1 with ~30 LOC, 5 tests)**:
      - T2.1: `test_migration_0031_idempotent_upgrade_downgrade_upgrade` — `alembic upgrade head` succeeds (asserts `DO $$` pre-flight passes — all 7 tables present + both seeds applied); `alembic downgrade -1` succeeds (Op 1 vigente_hasta closed + Op 2 descuadre_critico removed); `alembic upgrade head` succeeds again (round-trip idempotent).
      - T2.2: `test_migration_0031_preflight_aborts_if_table_missing` — DROP one table (test-only cleanup); `alembic upgrade head` raises `0031_preflight_abort: F1.13 requires all 7 tables to exist`. Re-CREATE TABLE post-test.
      - T2.3: `test_migration_0031_cierre_dia_seed_idempotent` — `alembic upgrade head` (1st time); `alembic upgrade head` (2nd time); verify only 1 row with `codigo='cierre_dia'` in `prod.tipo_arqueo` (ON CONFLICT DO NOTHING).
      - T2.4: `test_migration_0031_descuadre_critico_seed_idempotent` — verify only 1 row with `tipo_alerta='descuadre_critico'` in `prod.alert_types` (ON CONFLICT DO NOTHING).
      - T2.5: `test_migration_0031_gap_be_05_no_ddl` — verify NO schema changes (column count on `prod.tipo_arqueo` + `prod.alert_types` unchanged pre/post migration).
  - **Patrón F1.11 + F1.12** (`test_reimpresion_ticket_create_handler.py` + `test_venta_suscripcion_e2e.py` + `test_migration_0029_idempotency.py` + `test_migration_0030_noop.py`): HTTP integration via `httpx.AsyncClient` + `pg_engine` real via `testcontainers[postgres]`.
  - **Acción**: 1 NEW e2e file + extend T1.1 migration file. — **Validación**: T1 full happy path + T2.1 round-trip + T2.2 pre-flight abort + T2.3/T2.4 idempotent seeds + T2.5 NO-DDL PASS.

  **Commit suggestion**: `test(backend): HU-F1.13 — 4 mandated handler tests + 9 repo unit + 2 cierre_dia + 3 resumen + 1 e2e + 5 migration idempotency tests`.

  **Exit criteria T5**: T5.1..T5.6 verde; ~730 LOC cumulative (impl + tests); 4 AST walks + 4 mandated tests + ~14 unit/integration tests + 1 e2e + 5 migration tests PASS; KD-ARQUEO-01 single-commit + KD-ARQUEO-02/03/05 helpers + DEC-ARQUEO-06 no-store verified via AST walks; 4 mandated tests cover sin_diferencia/diferencia_justificada/descuadre_sobre_tolerancia/diferencia_sin_justificacion quadrants.

### Cluster T-GAP-BE-05 — Permiso Fix (~10 LOC impl + tests)

- [x] **T-HU-F1.13-T-GAP.1** [GREEN] — `api/v1/caja.py:53` — `permission_required="emitir_factura"` → `"permission_required="realizar_arqueo"` (1 line modification; DEC-ARQUEO-08 + plan.md lines 7349-7374 verbatim mandate).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` (MODIFIED, 1 line at :53).
  - **Acción**: source-level read confirms current `permission_required="emitir_factura"`; modify to `permission_required="realizar_arqueo"`. Both permissions pre-seeded (`realizar_arqueo` per plan.md line 4549; `emitir_factura` per F1.6). — **Validación**: T-GAP.2 unit test verifies the new permission string binds.

- [x] **T-HU-F1.13-T-GAP.2** [GREEN] — `api/v1/caja_sesion.py:257` — `permission_required="emitir_factura"` → `"permission_required="abrir_cerrar_caja"` (1 line modification; DEC-ARQUEO-08 + plan.md lines 7349-7374 verbatim mandate). Plus write `tests/unit/test_gap_be_05.py` (~5 LOC, 2 tests asserting 403 on missing permission + 200 on correct permission).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` (MODIFIED, 1 line at :257); NEW `backend/tests/unit/test_gap_be_05.py` (~5 LOC, 2 tests).
  - **Contenido del test file**:
    ```python
    """GAP-BE-05 verification: caja.py + caja_sesion.py permission correction.

    Sites:
    - api/v1/caja.py:53 — emitir_factura → realizar_arqueo
    - api/v1/caja_sesion.py:257 — emitir_factura → abrir_cerrar_caja
    """
    def test_caja_arqueo_endpoint_requires_realizar_arqueo_not_emitir_factura():
        # source-level read of api/v1/caja.py:53
        ...
        # assert HTTP 403 for operador with emitir_factura only
        # assert HTTP 201 for operador with realizar_arqueo (via T5.4 happy path)
        ...

    def test_caja_sesion_endpoint_requires_abrir_cerrar_caja_not_emitir_factura():
        # source-level read of api/v1/caja_sesion.py:257
        ...
        # assert HTTP 403 for operador with emitir_factura only
        # assert HTTP 200 for operador with abrir_cerrar_caja
        ...
    ```
  - **Acción**: source-level read confirms current `permission_required="emitir_factura"`; modify to `permission_required="abrir_cerrar_caja"`. `abrir_cerrar_caja` pre-seeded per F1.3. — **Validación**: 2 unit tests PASS; GAP-BE-05 closed.

  **Commit suggestion**: `fix(backend): HU-F1.13 — GAP-BE-05 2-line permission fix (caja.py:53 + caja_sesion.py:257)`.

  **Exit criteria T-GAP-BE-05**: T-GAP.1..T-GAP.2 verde; ~740 LOC cumulative (impl + tests); GAP-BE-05 closed; 2-line Python-only fix per plan.md lines 7349-7374 verbatim; both permission strings bind correctly per `tests/unit/test_gap_be_05.py`.

---

## Cross-cluster constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` on `prod.arqueo` / `prod.alerta` / `prod.sesion` / `prod.tipo_arqueo` / `prod.configuracion_tolerancias` / `prod.factura_pagos` outside the 13 helpers in `repo/arqueo.py` + the reused `repo/append_only.append_event` + `repo/workflow.append_transition` + `repo/session_cycle.close_session_with_log` — AST walks `tests/static/test_arqueo_handler_no_raw_dml.py` (T5.2) + `tests/static/test_arqueo_handler_no_update_on_a_tables.py` (T5.2) enforce via DEC-ARQUEO-02 + DEC-ARQUEO-05 + KD-ARQUEO-02.
- NO multiple `await session.commit()` or `session.begin_nested()` or `SAVEPOINT` statements in the POST handler body — AST walk `tests/static/test_arqueo_handler_single_commit.py` (T5.1) enforces via KD-ARQUEO-01 single-commit invariant.
- For `cierre_dia` codigo, the handler MUST call `close_session_with_log` per row (NOT raw `session.execute(update(Sesion))`) — AST walk `tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py` (T5.3) enforces via DEC-ARQUEO-03 + KD-ARQUEO-03 + `ls_session_guard` DB trigger.
- NO raw `UPDATE prod.arqueo` on user-meaningful fields (`valor_efectivo_esperado`, `diferencia_efectivo`, `alerta_generada`, etc.) — the AST walks enforce. Only the bi-temporal `vigente_hasta` MAY be UPDATEd by `VersionedBase` superclass for [V] tables (the existing `tests/static/test_no_raw_upsert_on_v_tables.py` from F1.5 PR5-016 covers `VersionedBase`).
- NO `Co-authored-by:` trailers AI en commits; conventional commits, neutral Spanish commit messages, neutral Spanish per-cluster rationale comments.
- NO SQLite in tests — `pg_engine` real via `testcontainers[postgres]` (F1.4/F1.5/F1.6/F1.7/F1.9/F1.10/F1.11/F1.12 precedent).
- NO modification of `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate (matches F1.7/F1.9/F1.10/F1.11/F1.12).
- NO modification of `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate cross-cutting.
- NO modification of `api/deps.py` nor `auth/tenancy.py` — KD-3 chain + errores tipados intactos.
- NO modification of `repo/event.py` — `event_helper_intact` CI gate (matches F1.7/F1.9/F1.10/F1.11/F1.12).
- NO modification of `repo/append_only.append_event` (F1.5 PR5-016, V8 Arqueo INSERT helper) — reused verbatim.
- NO modification of `repo/workflow.append_transition` (F1.5 PR5-016, V10 alerta INSERT helper) — reused verbatim.
- NO modification of `repo/session_cycle.close_session_with_log` (F1.3, V9 per-row sesion UPDATE) — reused verbatim; `ls_session_guard` DB trigger lines 286-289 intact.
- NO modification of `repo/alert_types.validate` + `AlertaFactory.fire` (F1.5/migration 0013, V10 alerta registry validation) — reused verbatim.
- NO modification of `repo/idempotency.py::guard` + `store_response` — F1.6 middleware continues to handle the cache; F1.13 endpoints inherit via DEC-IDEM-01.
- NO modification of `repo/sesion_activa.py::get_sesion_activa` — F1.3 reused verbatim.
- NO modification of `api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()` — F1.6 reused verbatim (lines 18-31, DEC-ARQUEO-06).
- NO modification of `api/v1/workflows_reimpresion.py` (F1.11 dedicated-router pattern reference) — read-only.
- NO modification of `api/v1/clientes_venta.py` (F1.12 dedicated-router + KD-VENTA-01 pattern reference) — read-only.
- NO modification of the existing factory mount at `api/v1/caja.py` lines 42-126 — F1.13 mounts on top via `router.include_router(caja_arqueo_router)` in DEC-ARQUEO-05, inherits `realizar_arqueo` permission gate after T-GAP-BE-05 fix at :53.
- NO modification of the existing factory mount at `api/v1/caja_sesion.py` lines 200-300 — F1.13 only changes 1 line at :257 (DEC-ARQUEO-08 GAP-BE-05 site #2: emitir_factura → abrir_cerrar_caja).
- NO new sync catalog entries — `sync_entries_v.py` lines 167-185 + `sync_entries_a.py` already carry all 5 entries with appropriate `direction`/`broadcast`/`hooks` settings (verified pre-apply, pre-flight 2026-09-15 confirmed no F1.13 sync catalog seeds needed per DEC-ARQUEO-09).
- NO new triggers — existing `tipo_arqueo_audit_columns` + `arqueo_inmutable` + `sesion_audit_columns` + `alerta_audit_columns` + `configuracion_tolerancias_audit_columns` + `_set_vigente_inicial` + `_enqueue_sync` + `ls_session_guard` + `alert_types_inmutable` (migration 0001 + 0013) cover the F1.13 INSERT paths.
- NO new permissions — `realizar_arqueo` pre-seeded (plan.md line 4549); `abrir_cerrar_caja` pre-seeded (F1.3).
- NO new role grants — operador + admin already granted both permissions per F1.3 closure.
- Header `Cache-Control: no-store` on EVERY response (201 + 4xx + 5xx) of BOTH endpoints (POST + GET) — via `no_store_headers()` helper + `apply_no_store_header(response)` before return + `headers=no_store` param in `HTTPException` constructors — DEC-ARQUEO-06 XR6 mirror from F1.10/F1.11/F1.12.
- Discriminators stable: `tenant_scope_violation` (403 operador cross-branch), `permission_denied` (403 no `realizar_arqueo`/`abrir_cerrar_caja`), `tipo_arqueo_no_encontrado` (404 V1), `sesion_no_encontrada` (404 V2), `tolerancia_no_configurada` (404 V3), `sesion_ya_cerrada` (409 V4), `cierre_dia_no_acepta_uuid_sesion` (400 V2), `sesion_requerida_para_auditoria_o_cierre_turno` (400 V2), `justificacion_requerida` (400 V6), `idempotency_key_required` (400 DEC-IDEM-01), `idempotency_conflict` (409 DEC-IDEM-01).
- Precedencia de errores: KD-3 (403 issuer) > Pydantic (422) > idempotency middleware (400/409) > V1 tipo_arqueo lookup (404) > tenant scope (403) > V2 cierre_dia cross-validation (400) > V3 tolerancia (404) > V4 sesion (409) > V6 justificacion (400) > V7 descuadre (no error) > V8 arqueo INSERT > V9 cierre_dia path > V10 alerta INSERT > Step 12 (single commit) > Step 13 (201 + Cache-Control).
- MIGRATION 0031 MUST be idempotent: pre-flight `DO $$` is read-only; Op 1 conditional siembra with `IF siembra_count = 0` + `ON CONFLICT DO NOTHING`; Op 2 conditional siembra with `INSERT ... ON CONFLICT DO NOTHING` (respects `alert_types_inmutable` trigger); Op 3 NO-DDL comment for GAP-BE-05.
- Per-commit ceiling: <800 LOC. Each cluster T1..T5 + T-GAP-BE-05 fits within the limit (T3 POST handler chain at ~180 LOC is the largest implementation block, well within). T2 may require mental split at apply (T2.1..T2.4 helpers ~100 LOC + T2.5 schemas ~90 LOC = ~190 LOC, split into T2 helpers commit + T2 schemas commit per commit plan) — orchestrator decides per real diff at apply.
- Mensajes conventional commit; cuerpo técnico en neutral Spanish.

## Acceptance Gates

- TDD strict: RED first, GREEN minimum, REFACTOR last. Clusters T2..T5 explicitly note this discipline.
- ~25 tasks completed in order: T1.1..T1.2 → T2.1..T2.5 → T3.1..T3.4 → T4.1..T4.2 → T5.1..T5.6 → T-GAP.1..T-GAP.2.
- Conventional commits atómicos (9 commits en 1 PR):
  - commit 1 `chore(backend): HU-F1.13 — MIGRATION 0031 REAL siembra (cierre_dia + descuadre_critico + pre-flight DO $$)` (~80 LOC);
  - commit 2 `feat(backend): HU-F1.13 — repo/arqueo.py 13 typed helpers + 6 typed exceptions` (~100 LOC);
  - commit 3 `feat(backend): HU-F1.13 — Pydantic schemas (ArqueoCreateV2 + 4 responses + 6 typed errors in schemas/caja.py)` (~90 LOC);
  - commit 4 `feat(backend): HU-F1.13 — POST /caja/arqueo handler (12-step chain + KD-ARQUEO-01 single-commit)` (~180 LOC);
  - commit 5 `feat(backend): HU-F1.13 — POST /caja/arqueo router mount (DEC-ARQUEO-05)` (~5 LOC);
  - commit 6 `feat(backend): HU-F1.13 — GET /caja/arqueo/resumen handler (6-step chain + cierre_dia aggregate)` (~60 LOC);
  - commit 7 `feat(static): HU-F1.13 — AST walks (KD-ARQUEO-01 single-commit + DEC-ARQUEO-02 no raw DML + KD-ARQUEO-03 cierre_dia session_cycle + KD-ARQUEO-02 no UPDATE on [A])` (~80 LOC);
  - commit 8 `test(backend): HU-F1.13 — 4 mandated handler tests + 9 repo unit + 2 cierre_dia + 3 resumen + 1 e2e + 5 migration idempotency tests` (~170 LOC);
  - commit 9 `fix(backend): HU-F1.13 — GAP-BE-05 2-line permission fix (caja.py:53 + caja_sesion.py:257)` (~5 LOC).
  - Without `Co-authored-by:`, without AI trailers.
- Tests run against real DB with `PARKOS_DOCKER_TEST=1`: 1 module-import (T2.1) + 3 + 8 + 9 = 20 repo unit (T2.2 + T2.3 + T2.4) + 10 schema unit (T2.5) + **4 mandated unit handler (T5.4)** + 7 extra handler asymmetry (T5.4) + 2 cierre_dia (T5.5) + 3 resumen (T5.5) + 1 e2e (T5.6) + 5 migration idempotency (T5.6 + T1.1) + 4 AST walks (T5.1 2 + T5.2 3 + T5.3 3 = 8 walk tests) + 2 GAP-BE-05 unit (T-GAP.2) = **~52 tests across 12 files** (7 unit/integration test files + 1 e2e + 1 migration + 3 AST walks).
- ruff + mypy --strict clean on all new/modified files (1 NEW `repo/arqueo.py` + 1 NEW `api/v1/caja_arqueo.py` + 1 EXTENDED `schemas/caja.py` + 1 MODIFIED `api/v1/caja.py` + 1 MODIFIED `api/v1/caja_sesion.py` + 1 NEW migration + 12 NEW tests + 4 NEW AST walks).
- 5 CI gates green (matches F1.7/F1.9/F1.10/F1.11/F1.12): `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.12`.
- 0 regressions introduced by F1.13; baseline F1.12 pre-existing failures documented and unchanged.
- REQ-OPS-091..097 + REQ-OPS-XR6 traceability verified: each REQ has ≥1 RED test that proves it (mapping in §11 of proposal.md + this file's per-task rationale).
- Architecture risks §10 (R1..R12) verified: R1 cross-domain atomicity → T3.3 Step 12 single commit + T5.1 AST walk verifies; R2 ls_session_guard rejection → T3.3 Step 9 cerrar_sesiones_del_dia_bulk + T5.3 AST walk verifies; R3 descuadre_critico missing → T1.2 MIGRATION 0031 Op 2 seeds; R4 cierre_dia missing → T1.2 MIGRATION 0031 Op 1 seeds; R5 tolerance wrong column → T2.3 es_descuadre_critico uses |diferencia| NOT pct; R6 justification asymmetry → T5.4 T5 test covers cierre_turno+sin_justificacion → 400; T-GAP.2 GAP-BE-05 wrong string → T-GAP.2 unit test asserts 403 + 200; R8 cierre_dia sync → DEC-ARQUEO-09 NOT extended to sync catalog (pre-existing cloud→branch entry propagates); R9 cierre_dia mass parallel → KD-ARQUEO-08 lock ordering + T2.4 test_cerrar_sesiones_del_dia_bulk_iterates; R10 descuadre_pct informational → DEC-ARQUEO-04 + docstring; R11 UI legend → DEC-ARQUEO-09 + UI deferred to Fase 10; R12 no-store → T5.4 unit test asserts header on 201/400/403/404/409/422.

## Out of Scope Tasks

- B2B arqueos (Fase 2+): corporate arqueos, multi-branch consolidated — out per plan.md line 1102.
- Multi-sucursal simultaneous arqueo (consolidated): out per plan.md scope.
- UI integration (Fase 10 HU-F10.1/10.2/10.3): deferred to Fase 10.
- Fase 10 reconciliación de tolerancia (pct vs absolute): plan.md line 1065 explicitly defers — Fase 10 owns.
- Filtros de consulta en `GET /caja/arqueo` (F18.1): out per plan.md Part 2 reference.
- `arqueo_pendiente_24h` alerta (F1.14): out per plan.md line 1105. F1.14's planned seed of `descuadre_critico` becomes a no-op after F1.13's MIGRATION 0031 Op 2.
- `ABIERTO-04` `cierre_sesion` dedicated flow (different from `cierre_dia` arqueo): out — Fase 2+ per exploration §14.
- `ABIERTO-200` `config_caja.redondeo` (config-level rounding rule): out — Fase 2+.
- Frontend reconciliation for `caja.py` factory mount: out (Fase 8 frontend).
- `diferencia_pct` based descuadre decision (Fase 10 owns pct vs absolute reconciliation): out — Fase 10.
- `arqueo_pendiente_24h` scheduled job (F1.14): out per plan.md line 1105.
- Recalculation of `descuadre_pct` after tolerance changes: out — Fase 2+.
- Notification of descuadre_critico to admin (alert_types.severity='critical' implies notification; F1.13 emits the alert, the consumer is downstream Fase 4): out.

## Commit summary (9 expected atomic commits)

| # | Cluster | Commit message | Files | LOC est. |
|---|---|---|---|---|
| 1 | T1 | `chore(backend): HU-F1.13 — MIGRATION 0031 REAL siembra (cierre_dia + descuadre_critico + pre-flight DO $$)` | 1 NEW migration + 1 partial NEW test (T1.1 pre-flight) | ~80 |
| 2 | T2a | `feat(backend): HU-F1.13 — repo/arqueo.py 13 typed helpers + 6 typed exceptions` | 1 NEW repo module + 1 NEW partial test | ~100 |
| 3 | T2b | `feat(backend): HU-F1.13 — Pydantic schemas (ArqueoCreateV2 + 4 responses + 6 typed errors in schemas/caja.py)` | 1 EXTENDED schemas + 1 NEW schema test | ~90 |
| 4 | T3a | `feat(backend): HU-F1.13 — POST /caja/arqueo handler (12-step chain + KD-ARQUEO-01 single-commit)` | 1 NEW handler module (POST part) | ~180 |
| 5 | T3b | `feat(backend): HU-F1.13 — POST /caja/arqueo router mount (DEC-ARQUEO-05)` | 1 MODIFIED `caja.py` (+5 LOC mount) | ~5 |
| 6 | T4 | `feat(backend): HU-F1.13 — GET /caja/arqueo/resumen handler (6-step chain + cierre_dia aggregate)` | 1 EXTENDED handler module (GET part) | ~60 |
| 7 | T5a | `feat(static): HU-F1.13 — AST walks (KD-ARQUEO-01 single-commit + DEC-ARQUEO-02 no raw DML + KD-ARQUEO-03 cierre_dia session_cycle + KD-ARQUEO-02 no UPDATE on [A])` | 4 NEW AST walk files | ~80 |
| 8 | T5b | `test(backend): HU-F1.13 — 4 mandated handler tests + 9 repo unit + 2 cierre_dia + 3 resumen + 1 e2e + 5 migration idempotency tests` | 7 NEW test files (handler + repo full + cierre_dia + resumen + e2e + migration extended + GAP-BE-05) | ~170 |
| 9 | T-GAP | `fix(backend): HU-F1.13 — GAP-BE-05 2-line permission fix (caja.py:53 + caja_sesion.py:257)` | 1 MODIFIED `caja.py` (1 line) + 1 MODIFIED `caja_sesion.py` (1 line) + 1 NEW test | ~5 |

**Total**: 9 commits, ~770 LOC cumulative (impl + tests + migration + AST walks), 1 PR to `origin/dev`. Net apply delta ~290 LOC production + ~220 LOC tests + ~80 LOC migration + ~80 LOC AST walks + ~5 LOC GAP-BE-05 fix.

## Definition of Done (apply phase)

- [ ] ~52 tests + 4 AST walks across 12 test files PASS via `uv run pytest backend/tests/unit/test_arqueo_handler.py backend/tests/unit/test_arqueo_repo.py backend/tests/unit/test_arqueo_schemas.py backend/tests/unit/test_cierre_dia.py backend/tests/unit/test_arqueo_resumen.py backend/tests/unit/test_gap_be_05.py backend/tests/integration/test_arqueo_e2e.py backend/tests/integration/test_migration_0031_idempotency.py backend/tests/static/test_arqueo_handler_*.py -q`
- [ ] MIGRATION 0031 applied + downgrade reverses cleanly via `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` (round-trip idempotent)
- [ ] 2 handlers (`POST /api/v1/caja/arqueo` + `GET /api/v1/caja/arqueo/resumen`) implemented per design §10 (12-step POST + 6-step GET)
- [ ] `repo/arqueo.py` 13 typed helpers + 6 typed exceptions authored (DEC-ARQUEO-01..10)
- [ ] `schemas/caja.py` extended with `ArqueoCreateV2` + `ArqueoReadForHandler` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams` + 6 typed errors
- [ ] KD-3 issuer chain `_caja_arqueo_issuer_dep = requires_issuer("operador-", "admin-")` applied with `Cache-Control: no-store` on every response
- [ ] KD-ARQUEO-01 single-commit invariant verified via AST walk on `post_arqueo`
- [ ] KD-ARQUEO-02 [A] append-only invariant verified via AST walk (`tests/static/test_arqueo_handler_no_update_on_a_tables.py`)
- [ ] KD-ARQUEO-03 `cierre_dia` session_cycle invariant verified via AST walk (`tests/static/test_arqueo_handler_cierre_dia_uses_session_cycle.py`)
- [ ] KD-ARQUEO-08 lock ordering verified (tipo_arqueo `SELECT FOR UPDATE` at Step 1 BEFORE all other locks)
- [ ] DEC-ARQUEO-04 tolerancia = absolute monto verified (boundary cases `==` tolerance → no alerta)
- [ ] DEC-ARQUEO-06 `Cache-Control: no-store` verified on 201 / 400 / 403 / 404 / 409 / 422 / 5xx responses
- [ ] DEC-ARQUEO-07 justification asymmetry verified (cierre_turno+cierre_dia+diferencia+sin_justificacion → 400; auditoria+diferencia+sin_justificacion → OK)
- [ ] DEC-ARQUEO-08 GAP-BE-05 verified (2-line permission fix + 1 unit test asserting 403/200)
- [ ] Tenant scope post-V1 verified (operador- cross-branch → 403 `tenant_scope_violation`)
- [ ] `Idempotency-Key` HTTP header supported (DEC-IDEM-01 reuse from F1.6/F1.9/F1.10/F1.11/F1.12)
- [ ] All F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11/F1.12 tests still PASS (no_regresion gate)
- [ ] ruff + mypy --strict clean on all 6 new/modified files
- [ ] 5 CI gates verde (`factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.12`)
- [ ] 0 regresiones introducidas; baseline F1.12 pre-existing failures documented + unchanged
- [ ] REQ-OPS-091..097 + REQ-OPS-XR6 traceability verified via per-REQ RED tests
- [ ] 9 atomic commits authored with conventional commit messages, neutral Spanish, NO `Co-authored-by:` trailers

## Next phase

`sdd-apply hu-f1-13-arqueo` — TDD-strict RED→GREEN→REFACTOR per cluster T1..T5 + T-GAP-BE-05. Orchestrator executes the 9 atomic commits in order, verifies each cluster's exit criteria, and routes to `sdd-verify` after all commits land.

## References

- `openspec/changes/hu-f1-13-arqueo/design.md` (~1804 LOC, 16 sections) — full architecture + MIGRATION 0031 SQL + 4 AST walks + 10 DECs + 5 KDs.
- `openspec/changes/hu-f1-13-arqueo/proposal.md` (~485 LOC, 16 sections, DEC-ARQUEO-01..10, KD-ARQUEO-01..05, R1..R12) — pre-design proposal.
- `openspec/changes/hu-f1-13-arqueo/exploration.md` (~29 KB, 17 sections, pre-flight 18/20 PASS) — pre-design exploration.
- `openspec/changes/hu-f1-13-arqueo/specs/operations/spec.md` (~485 LOC, 8 REQ-OPS-091..097 + REQ-OPS-XR6) — operational requirements.
- `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/tasks.md` (~860 LOC, 8 clusters T1..T8, 31 tasks, ~0.86 PR diff) — **canonical precedent** for F1.13 structure.
- `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/{proposal,design,specs/operations/spec.md,verify-report,archive-report}.md` — F1.12 full cycle precedent.
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/tasks.md` — F1.11 precedent (KD-TKT-01 single-commit + AST walk).
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/tasks.md` — F1.10 precedent (KD-FE-01 single-commit).
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/tasks.md` — F1.9 precedent (KD-FACT-01 single-commit + `crear_factura_*` helpers reused).
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/tasks.md` — F1.7 precedent (KD-S2 tenant scope post-V1, `resolve_active_subscription_for_exit` reuse).
- `openspec/changes/archive/2026-09-14-hu-f1-6-ingresos/tasks.md` — F1.6 precedent (DEC-IDEM-01 Idempotency-Key header + placa regex).
- `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/tasks.md` — F1.5 precedent (`repo/versioned.py::close_and_insert` + AST walk no-raw-UPSERT on [V]).
- `openspec/specs/operations/spec.md` lines 3217-3651 (XR1..XR5 progression + REQ-OPS-083..090 last-req-number series) — target for REQ-OPS-091..097 + XR6 merge on archive.
- `plan.md` lines 1058-1101 — HU-F1.13 definition, 4 atomic tasks T1..T4, 240 LOC production budget.
- `plan.md` lines 7349-7374 — GAP-BE-05 verbatim mandate + bundle recommendation.
- `plan.md` line 458 — A-07 `cierre_dia` siembra.
- `plan.md` line 1065 — tolerancia = monto absoluto.
- `plan.md` lines 1086-1091 + line 2476 — justificacion asymmetry.
- `plan.md` line 4549 — `realizar_arqueo` permission seeded.
- `plan.md` line 1093 — 4 tests mandated for `tests/unit/test_arqueo_handler.py`.
- `modelo_datos_er.mmd` line 167-185 (`tipo_arqueo` [V]), line 250-268 (`configuracion_tolerancias` [V]), line 715-735 (`sesion` [L-S]), line 737-758 (`alerta` [L-W]), line 957-978 (`arqueo` [A]).
- `migrations/versions/0001_initial_schema.py` lines 167-185 (`tipo_arqueo`), 250-268 (`configuracion_tolerancias`), 715-735 (`sesion`), 737-758 (`alerta`), 957-978 (`arqueo`), 2024-2088 (inmutability triggers).
- `migrations/versions/0013_add_alert_types.py` (registry + `alert_types_inmutable` trigger lines 21-22).
- `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head template for conditional siembra + permission seed pattern, lines 134-188).
- `migrations/versions/0030_venta_suscripcion_optional.py` (F1.12 NO-OP audit-trail head pre-F1.13).
- `api/v1/caja.py` line 53 (GAP-BE-05 site #1 confirmed).
- `api/v1/caja_sesion.py` line 257 (GAP-BE-05 site #2 confirmed).
- `models/V/{tipo_arqueo, configuracion_tolerancias}.py`, `models/A/{arqueo, alert_types, factura_pagos, log_transaccional}.py`, `models/L_S/sesion.py`, `models/L_W/alerta.py` — pre-existing ORM models (no change).
- `repo/append_only.py::append_event` (F1.5 PR5-016 lines 64-124 — reused for V8 Arqueo INSERT).
- `repo/workflow.py::append_transition` (F1.5 PR5-016 lines 110-237 — reused for V10 alerta INSERT).
- `repo/workflow.py::STATE_MACHINES['alerta']` (F1.5 PR5-016 lines 85-90 — initial {activa} only).
- `repo/session_cycle.py::close_session_with_log` (F1.3 lines 274-349 — reused for V9 per-row sesion UPDATE).
- `repo/session_cycle.py::validar_sesion_abierta` (F1.3/F1.5 precedent, reused for V4 fallback).
- `repo/sesion_activa.py::get_sesion_activa` (F1.3 — reused for V4).
- `repo/alert_types.py::validate` + `AlertaFactory.fire` (F1.5/migration 0013 — reused for V10).
- `repo/idempotency.py::guard` + `store_response` (F1.6 DEC-IDEM-01 — reused).
- `api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()` (F1.6 lines 18-31, DEC-ARQUEO-06 — reused).
- `api/v1/workflows_reimpresion.py` (F1.11 dedicated-router + KD-3 + tenant scope + Idempotency-Key pattern reference for the outer handler envelope shape).
- `api/v1/clientes_venta.py` (F1.12 dedicated-router + KD-VENTA-01 single-commit + DEC-VENTA-06 no-store + KD-VENTA-02 plan lock pattern reference for the 12-step handler chain shape).
- `schemas/common.py::_Base` (`extra='forbid'` — Layer 4 defense for `ArqueoCreateV2` + `ArqueoReadForHandler` + `ArqueoResumenItem` + `ArqueoResumenRead` + `CierreDiarioQueryParams` + 6 typed errors).
- `static/test_no_raw_dml_on_a_tables.py` (F1.5 PR5-016 AST walk precedent — basis for T5.2 + T5.3).
- `auth/{jwt_issuer_guard, tenancy}.py` — KD-3 issuer chain + `TenantContext` derivation.

---

**End of tasks.**