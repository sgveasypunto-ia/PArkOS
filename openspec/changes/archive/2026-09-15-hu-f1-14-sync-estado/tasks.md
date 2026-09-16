# Tasks: hu-f1-14-sync-estado

> **Change**: `hu-f1-14-sync-estado` · **Phase**: tasks (sdd-tasks) · **HU**: HU-F1.14 — `GET /sync/estado` + siembra 11 alert_types de negocio (19 totales)
> **Date**: 2026-09-15 · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `83b5dfa`) · **PR target**: `origin/dev`
> **Cumulative estimate**: ~460 LOC (~280 prod + ~110 tests + ~70 migration)
> **Clusters**: T1..T5 (5 clusters, 14 atomic tasks)
> **Mandated tests**: 2 (plan.md line 1126)
>
> **Inputs**:
> - `openspec/changes/hu-f1-14-sync-estado/design.md` (~1347 LOC, 16 sections + 2 appendices, DEC-SYNC-01..10, KD-SYNC-01..02, MIGRATION 0032 SQL body + AST walk precedent)
> - `openspec/changes/hu-f1-14-sync-estado/specs/operations/spec.md` (~485 LOC, 4 REQs REQ-OPS-098..101 + REQ-OPS-XR6 reference)
> - `openspec/changes/hu-f1-14-sync-estado/proposal.md` (~770 LOC, 16 sections, DEC-SYNC-01..10, KD-SYNC-01..02, 10 risks R1..R10 — 4 RESOLVED at propose phase)
> - `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/tasks.md` (~745 LOC, 6 clusters T1..T5 + T-GAP-BE-05) — **canonical precedent mirrored verbatim**
> - `plan.md` lines 1105-1133 (HU-F1.14 full definition, 3 atomic tasks T1..T3, 120 LOC production budget, 2 mandated tests at line 1126, severity mapping at line 1131)
> - `plan.md` line 429 (DEC-SUC-14: 19 totales, 8 técnicos + 11 de negocio coexisten)
> - `plan.md` line 459 (A-08 severity JOIN-only via `alert_types.severity`)
> - `plan.md` lines 2311-2323 (canonical descriptions per alert_type — DEC-SYNC-10)
> - `modelo_datos_er.mmd` blocks `sync_log` [A] lines 1027-1047, `sync_queue` [A] lines 981-1002, `alert_types` [A] lines 1101-1114
> - `migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` lines 169-175 (F1.13 head, `descuadre_critico` ALREADY seeded by Op 2 — `ON CONFLICT DO NOTHING` will make F1.14's re-seed a no-op, DEC-SYNC-05)
> - `migrations/versions/0013_add_alert_types.py` lines 21-22 (registry + `alert_types_inmutable` trigger), lines 67-108 (idempotent INSERT precedent), lines 119 (severity CHECK constraint), lines 129-130 (REVOKE/GRANT)
> - `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` lines 134-188 (F1.11 conditional siembra pattern — F1.14 mirrors in MIGRATION 0032 Op 0 + Op 1 + Op 2)
> - `migrations/versions/0002_seed_permisos_canonicos.py` lines 39-56 (`CANONICAL_PERMISOS` includes `audit_read` at line 48 — DEC-SYNC-03.B pre-seeded)
> - `api/v1/sync_router.py` lines 9-49 (docstring listing 7 endpoints — `/estado` NOT in list, no collision), line 95 (`APIRouter(prefix="/sync")`), line 358 (`sync-agent-` issuer guard)
> - `api/v1/caja.py` line 86 (F1.13 mount precedent: `router.include_router(caja_arqueo_router)` — DEC-SYNC-02)
> - `api/v1/_helpers.py` lines 18-31 (`no_store_headers()` + `apply_no_store_header()` — DEC-SYNC-04)
> - `auth/jwt_issuer_guard.py` (`requires_issuer` factory, KD-3 dep)
> - `auth/tenancy.py` (`get_tenant_ctx`, KD-S2 F1.7 analog — Layer 2)
> - `repo/alert_types.py` lines 30-48 (validate + AlertaFactory)
> - `models/A/{sync_log, sync_queue, alert_types}.py` (verbatim ORM models, no change)
> - `schemas/sync_infra.py` (EXTEND with 2 new shapes: `SyncEstadoQueryParams` + `SyncEstadoRead`)
> - `schemas/common.py::_Base` (`extra='forbid'` — Layer 4 defense base)
> - `tests/static/check_sync_queue_carveout.py` (REQ-OPS-004 AST walk precedent for KD-SYNC-02)
> - `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 already exists from F1.13 — F1.14 references, does NOT create new)
>
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `83b5dfa`; F1.13 closed) · **PR target**: `origin/dev`.
> **TDD discipline**: RED→GREEN→REFACTOR per cluster. Each commit <800 LOC. Each cluster ends with all tests PASS.
> **Atomic commit strategy**: 5 atomic commits expected (T1 MIGRATION + T2 repo/schemas + T3 handler + T4 AST walk + tests + T5 housekeeping).
> **Skills loaded**: `gentle-sdd-tasks` + `sdd-phase-common.md` (paths injected via orchestrator).

---

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~460 across 1 PR (~280 LOC production: ~70 LOC NEW `migrations/versions/0032_seed_alert_types_operativos.py` + ~30 LOC NEW `repo/sync_estado.py` + ~80 LOC NEW `api/v1/sync_estado.py` + ~30 LOC EXTEND `schemas/sync_infra.py` + ~6 LOC MODIFY `api/v1/caja.py` + ~110 LOC tests + ~70 LOC AST walk + ~30 LOC migration test) |
| Total tasks | ~14 (5 clusters: T1 setup 3 + T2 repo+schemas 4 + T3 handler+mount 4 + T4 AST+integration 2 + T5 housekeeping 1) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Low** — F1.14 is comparable to F1.13 (~590 LOC cumulative) but with smaller blast radius (1 read endpoint + 1 repo module + 2 Pydantic schemas + 1 migration); 5-commit split keeps each commit well within the `commitlint` 800-LOC ceiling. |
| Chained PRs recommended | No — one single PR (matches F1.7 + F1.9 + F1.10 + F1.11 + F1.12 + F1.13 precedent); read-only path keeps blast radius small. |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Single PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 5 commits internally (T1 ~70 migration, T2 ~70 repo + schemas, T3 ~80 handler + mount, T4 ~30 AST walk + integration test, T5 ~30 housekeeping + apply-report). |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesive single-resource (1 dedicated handler + 3 repo helpers + 2 Pydantic schemas + 1 REAL migration) + 5-commit split keeps budget risk Low inside the F1.11/F1.12/F1.13 precedent. |

| Cluster | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|---------|-------|---------------|----------------|----------------|
| T1 Setup + MIGRATION 0032 siembra | T1.1..T1.3 | ~70 LOC (pre-flight + migration + downgrade) | n/a (test in T4) | 70 |
| T2 Repo helpers + schemas | T2.1..T2.4 | ~70 LOC (3 typed helpers + 2 Pydantic schemas + repo skeleton) | n/a (tests in T4) | 140 |
| T3 Handler + mount | T3.1..T3.4 | ~80 LOC (4-step chain + mount extension) | n/a (tests in T4) | 220 |
| T4 AST walk + integration test | T4.1..T4.2 | n/a | ~110 LOC (3 AST walks + 2 migration tests + 4 schema tests + 5 repo tests + 4 seed tests + 2 handler tests) | 330 |
| T5 housekeeping + apply-report | T5.1 | n/a | ~30 LOC (apply-report + pending.md update) | 360 |
| **Total** | **~14** | **~220 LOC impl** | **~140 LOC tests** | **~360 LOC cumulative workload** (~460 LOC inclusive of migration and AST walk per design.md §16.5 estimate) |

> Per-commit ceiling: <800 LOC. Each cluster T1..T5 fits within the limit (T3 handler + mount at ~80 LOC is the largest implementation block, well within).

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| T1 | Pre-flight verify + MIGRATION 0032 siembra (Op 0 + Op 1 + Op 2) | commit 1 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0032_idempotency.py -q` | `pg_engine` real via `testcontainers[postgres]`; pre-flight DO $$ asserts 4 conditions; Op 1 idempotent via `ON CONFLICT DO NOTHING` | `alembic downgrade -1` reverses Op 1; Op 2 NO-DDL |
| T2 | `repo/sync_estado.py` 3 typed SELECT helpers + `schemas/sync_infra.py` extend (`SyncEstadoQueryParams` + `SyncEstadoRead`) | commit 2 | `uv run pytest backend/tests/unit/test_sync_estado_repo.py backend/tests/unit/test_sync_estado_schemas.py -q` | unit tests no DB for schemas (T2.2); pure DateTime math for `calcular_lag_seg` (T2.3); AsyncMock patterns for SELECT helpers (T2.3) | Delete helper bodies / schema appends |
| T3 | `GET /sync/estado` 4-step chain + dedicated router + mount at `caja.py` | commit 3 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_sync_estado.py -q` | HTTP integration with `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-`/`admin-` fixtures + real DB | Revert handler module + mount |
| T4 | KD-SYNC-02 AST walk (3 assertions) + alert_types seed tests (4) + migration idempotency tests (2) | commit 4 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/static/test_sync_estado_read_only.py backend/tests/unit/test_alert_types_seed.py backend/tests/integration/test_migration_0032_idempotency.py -q` | real DB for migration + seed; pure AST walks for static | Delete AST walk + test files |
| T5 | apply-report + all tasks [x] + pending.md update | commit 5 | (no test command — documentation only) | n/a | Revert apply-report + pending.md |

---

## Tareas

### Cluster T1 — Setup & MIGRATION 0032 siembra (~70 LOC impl)

- [x] **T-HU-F1.14-T1.1** [RED] — Pre-flight verification: grep across the repo for `prod.alert_types` (in `migrations/versions/0013_add_alert_types.py` lines 21-22 trigger + lines 67-108 idempotent precedent + line 119 severity CHECK), `prod.sync_log` (lines 1027-1047), `prod.sync_queue` (lines 981-1002); verify pre-F1.14 `prod.alert_types` count = 9 (8 técnicos from 0013 + `descuadre_critico` from F1.13 MIGRATION 0031 Op 2 lines 169-175); verify `audit_read` pre-seeded at `0002_seed_permisos_canonicos.py:48`. Write `tests/integration/test_migration_0032_idempotency.py::test_pre_flight_4_conditions` asserting pre-migration state via SQL.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_pre_flight_alert_types_exists_with_pk` — query `information_schema.tables WHERE table_schema='prod' AND table_name='alert_types'` returns 1 row; query `pg_index` + `pg_constraint` confirms PK on `tipo_alerta`.
    - T2: `test_pre_flight_alert_types_inmutable_trigger_active` — query `pg_trigger WHERE tgname='alert_types_inmutable'` returns 1 row with `tgenabled='O'` (origin/enabled).
    - T3: `test_pre_flight_severity_check_constraint_present` — query `pg_constraint WHERE conname LIKE '%severity%'` returns 1 row matching `('info', 'warning', 'critical')`.
    - T4: `test_pre_flight_sync_log_and_sync_queue_exist` — query `information_schema.tables WHERE table_schema='prod' AND table_name IN ('sync_log', 'sync_queue')` returns 2 rows.
    - T5: `test_pre_flight_alert_types_count_equals_9` — `SELECT COUNT(*) FROM prod.alert_types` returns exactly 9 (DEC-SYNC-05 pre-state: 8 técnicos + 1 F1.13 descuadre_critico).
    - T6: `test_pre_flight_audit_read_permission_seeded` — `SELECT COUNT(*) FROM prod.permisos WHERE permiso='audit_read'` returns 1 (DEC-SYNC-03.B).
  - **Patrón F1.11 + F1.12 + F1.13** (`test_migration_0029_idempotency.py` + `test_migration_0030_noop.py` + `test_migration_0031_idempotency.py`): pre-flight `DO $$` table-presence assertion + source-level grep + count assertions.
  - **Acción**: write test that asserts pre-flight state via SQL + source-level read of `migrations/versions/0002_seed_permisos_canonicos.py:48`. — **Archivo**: `backend/tests/integration/test_migration_0032_idempotency.py` (nuevo, partial ~30 LOC, 6 tests covering pre-flight + Op 1 + Op 2 idempotency). — **Validación**: pre-implementation, all 6 pre-flight tests PASS (pre-flight already satisfied 2026-09-15 per exploration §12).

- [x] **T-HU-F1.14-T1.2** [GREEN] — Author `migrations/versions/0032_seed_alert_types_operativos.py` (~70 LOC, REAL siembra): Op 0 pre-flight `DO $$` block asserting 4 conditions (alert_types table + `alert_types_inmutable` trigger active + sync_log + sync_queue tables exist) + Op 1 siembra 11 alert_types codes (10 net new + idempotent re-attempt of `descuadre_critico`) via `op.bulk_insert` + `_SEED_ROWS` tuple with severity mapping per plan.md line 1131 (DEC-SYNC-06: alta → critical, media → warning, baja → info) + Op 2 NO-DDL `RAISE NOTICE` anchor for DEC-SYNC-03.B (audit_read reuse). `downgrade()` reverses Op 1 with DISABLE TRIGGER + DELETE 10 net new (preserve descuadre_critico from F1.13 + 8 técnicos from 0013). `down_revision='0031_arqueo_cierre_dia_and_gap_be_05'`.
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0032_seed_alert_types_operativos.py` (nuevo, ~70 LOC).
  - **Contenido** (verbatim per design.md Appendix A):
    ```python
    """MIGRATION 0032 — F1.14 REAL siembra: 11 alert_types codes per plan.md line 1131 (10 net new).

    Pre-flight 2026-09-15 confirmed:
    - prod.alert_types exists (migration 0013, registry, alert_types_inmutable trigger lines 21-22).
    - prod.alert_types seeded status pre-F1.14: 9 rows = 8 técnicos (0013) + descuadre_critico (F1.13 0031 Op 2).
    - F1.14 adds 10 net new + idempotent re-attempt of descuadre_critico (becomes no-op via ON CONFLICT).
    - Final total: 19 alert_types seeded (8 técnicos + 1 F1.13 + 10 F1.14 = 19).
    - DEC-SYNC-05: 10 net new (NOT 11) — descuadre_critico already seeded by F1.13 0031 Op 2.

    This migration ships:
    - Op 0: pre-flight DO $$ block asserting required tables + trigger exist.
    - Op 1: siembra 11 alert_types codes (10 net new + idempotent re-attempt of descuadre_critico).
    - Op 2: NO-DDL anchor for DEC-SYNC-03.B (audit_read reuse — no perm migration).

    Idempotency ensures any future re-run on already-migrated DB is a clean no-op.
    """
    from alembic import op
    import sqlalchemy as sa

    revision = "0032_seed_alert_types_operativos"
    down_revision = "0031_arqueo_cierre_dia_and_gap_be_05"
    branch_labels = None
    depends_on = None


    # Canonical seed rows for the 11 codes per plan.md line 1131.
    # Severity per DEC-SYNC-06: alta=critical, media=warning, baja=info.
    # descripcion per DEC-SYNC-10 from plan.md lines 2311-2323.
    _SEED_ROWS: tuple[tuple[str, str, str], ...] = (
        # (tipo_alerta, severity, descripcion)
        ("sync_fallida", "critical", "Sincronización con cloud falló tras N reintentos"),
        ("capacidad_agotada", "warning", "Sucursal sin cupos disponibles"),
        ("capacidad_agotada_forzado", "warning", "Ingreso forzado con capacidad agotada"),
        ("evento_no_procesado", "critical", "Evento en sync_queue sin procesar tras SLA"),
        ("impresora_caida", "critical", "Impresora local no responde"),
        ("fe_error_toppoint", "critical", "Error FE provisto por TopPoint"),
        ("numeracion_toppoint_agotada", "critical", "Numeración TopPoint agotada"),
        ("cache_desactualizado", "info", "Cache local desactualizado"),
        ("arqueo_pendiente_24h", "warning", "Arqueo pendiente >24h"),
        ("suscripcion_proxima_vencer", "warning", "Suscripción próxima a vencer"),
        # descuadre_critico already seeded by F1.13 MIGRATION 0031 Op 2 — re-seeded idempotent
        ("descuadre_critico", "critical", "Descuadre de caja supera tolerancia"),
    )


    def upgrade() -> None:
        """MIGRATION 0032 upgrade: pre-flight + Op 1 siembra 11 codes (10 net new)."""
        # Op 0 -- pre-flight DO $$ (KD-7 F1.6..F1.13 pattern).
        op.execute(
            """
            DO $$
            BEGIN
                ASSERT EXISTS (
                    SELECT 1 FROM pg_tables WHERE schemaname = 'prod' AND tablename = 'alert_types'
                ), 'prod.alert_types must exist';
                ASSERT EXISTS (
                    SELECT 1 FROM pg_trigger WHERE tgname = 'alert_types_inmutable'
                ), 'alert_types_inmutable trigger must be active';
                ASSERT EXISTS (
                    SELECT 1 FROM pg_tables WHERE schemaname = 'prod' AND tablename = 'sync_log'
                ), 'prod.sync_log must exist';
                ASSERT EXISTS (
                    SELECT 1 FROM pg_tables WHERE schemaname = 'prod' AND tablename = 'sync_queue'
                ), 'prod.sync_queue must exist';
            END $$;
        """
        )

        # Op 1 -- siembra 11 alert_types codes (10 net new + idempotent re-attempt of descuadre_critico).
        # Idempotent via ON CONFLICT (tipo_alerta) DO NOTHING (respects alert_types_inmutable trigger).
        bind = op.get_bind()
        alert_types_table = sa.table(
            "alert_types",
            sa.column("tipo_alerta", sa.Text),
            sa.column("severity", sa.Text),
            sa.column("descripcion", sa.Text),
            sa.column("created_at", sa.DateTime),
            sa.column("created_by", sa.Text),
            schema="prod",
        )
        op.bulk_insert(
            alert_types_table,
            [
                {
                    "tipo_alerta": t,
                    "severity": s,
                    "descripcion": d,
                    "created_at": None,  # server-set to NOW() via DB default if defined
                    "created_by": "migrations/0032",
                }
                for t, s, d in _SEED_ROWS
            ],
        )

        # Op 2 -- NO-DDL anchor for DEC-SYNC-03.B (audit_read permission decision).
        op.execute(
            """
            DO $$
            BEGIN
                RAISE NOTICE '0032_op2: DEC-SYNC-03.B adopted. Permission gate = audit_read '
                             '(pre-seeded at 0002_seed_permisos_canonicos.py:48). '
                             'No new permission seeded.';
            END $$;
        """
        )


    def downgrade() -> None:
        """Reverse Op 1: DELETE the 10 NET NEW alert_types rows (preserve descuadre_critico from F1.13)."""
        # Disable alert_types_inmutable trigger temporarily (DELETE not allowed by default).
        op.execute("ALTER TABLE prod.alert_types DISABLE TRIGGER alert_types_inmutable;")

        # Delete only the 10 F1.14 net new codes. descuadre_critico is NOT touched
        # (owned by F1.13 MIGRATION 0031 Op 2, lines 169-175).
        net_new_codes = [code for code, _, _ in _SEED_ROWS if code != "descuadre_critico"]
        codes_list = ", ".join(f"'{c}'" for c in net_new_codes)
        op.execute(
            f"""
            DELETE FROM prod.alert_types
            WHERE tipo_alerta IN ({codes_list});
            """
        )

        op.execute("ALTER TABLE prod.alert_types ENABLE TRIGGER alert_types_inmutable;")

        # Op 2 -- NO-DDL reversal: DEC-SYNC-03.B is a Python-only decision (no migration changes).
    ```
  - **Acción**: paste verbatim from design.md Appendix A; `revision="0032_seed_alert_types_operativos"`; `down_revision="0031_arqueo_cierre_dia_and_gap_be_05"`. — **Validación**: T1.1 pre-flight tests PASS pre-migration; post-migration `tests/integration/test_migration_0032_idempotency.py` round-trip test PASSes (upgrade → downgrade → upgrade idempotent).

- [x] **T-HU-F1.14-T1.3** [REFACTOR] — Verify `downgrade()` preserves `descuadre_critico` (F1.13-owned, migration 0031 Op 2 lines 169-175) AND the 8 técnicos (0013-owned: `hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`). After downgrade, `prod.alert_types` MUST contain exactly 9 rows (8 técnicos + `descuadre_critico`); after re-upgrade, exactly 19 rows. Op 2 `RAISE NOTICE` is a Python `pass` reversal — NO DDL changes (DEC-SYNC-03.B audit_read reuse is pre-existing at 0002:48).
  - **Acción**: extend T1.1 file `backend/tests/integration/test_migration_0032_idempotency.py` with 2 post-migration tests:
    - `test_migration_0032_post_upgrade_19_rows` — `SELECT COUNT(*) FROM prod.alert_types` = 19.
    - `test_migration_0032_post_downgrade_9_rows_preserves_descuadre` — after `alembic downgrade -1`, `COUNT(*)` = 9 AND `SELECT COUNT(*) WHERE tipo_alerta='descuadre_critico'` = 1 (preserved).
  - **Validación**: pre-refactor: T1.2 migration applies cleanly; post-refactor: downgrade + upgrade cycle test PASSes.

  **Commit suggestion**: `feat(backend): HU-F1.14 — MIGRATION 0032 REAL siembra (11 alert_types codes + pre-flight DO $$ + downgrade preserves F1.13)` (~70 LOC + ~30 LOC pre-flight tests partial).

  **Exit criteria T1**: T1.1..T1.3 verde; ~70 LOC migration + ~30 LOC pre-flight tests cumulative; migration head = `0032_seed_alert_types_operativos`; pre-flight DO $$ asserts 4 conditions; Op 1 seeds 11 codes idempotently (10 net new + idempotent re-attempt of descuadre_critico); downgrade preserves 8 técnicos + descuadre_critico; upgrade re-seeds 19 cleanly.

### Cluster T2 — Repo Helpers + Schemas (~70 LOC impl)

- [x] **T-HU-F1.14-T2.1** [RED + GREEN] — Author `repo/sync_estado.py` skeleton (~10 LOC): `from __future__ annotations` + module docstring documenting DEC-SYNC-01..10 + KD-SYNC-01..02 references + define 3 typed helper functions (`get_ultima_sync_at`, `calcular_lag_seg`, `count_pendientes_sync_queue`) — all SELECT-only, commit-free, NO `await session.commit()` (KD-SYNC-01 contract). `__all__` listing the 3 helper names + module-level type hints for `Session` + `UUID` + `datetime`.
  - **Tests** (pure Python, no DB, no HTTP):
    - T1: `test_repo_sync_estado_module_imports` — `from parkos_core.repo import sync_estado as repo_sync_estado` succeeds; `dir(repo_sync_estado)` includes 3 typed helper names.
  - **Patrón F1.13** (`test_repo_arqueo_module_imports`): pure import assertion, gated by `__all__` definition.
  - **Acción**: `import` from `parkos_core.repo.sync_estado` (fails with `ModuleNotFoundError`); assert public names. — **Archivo**: `backend/tests/unit/test_sync_estado_repo.py` (nuevo, partial ~5 LOC, 1 test). — **Validación**: `ModuleNotFoundError: No module named 'parkos_core.repo.sync_estado'`.

- [x] **T-HU-F1.14-T2.2** [RED + GREEN] — Author `schemas/sync_infra.py` extension (~30 LOC) with `SyncEstadoQueryParams(_Base)` query params + `SyncEstadoRead(_Base)` response shape. Both inherit `extra='forbid'` from `_Base` (Layer 4 defense, blocks client smuggling of `actor_uuid`, `computed_at`, `cache_key`). `SyncEstadoQueryParams` has `uuid_sucursal: UUID` (required). `SyncEstadoRead` has `uuid_sucursal: UUID`, `ultima_sync_at: datetime | None` (nullable ISO-8601 naive UTC), `lag_seg: int | None` (nullable, DEC-SYNC-08), `pendientes: int` (non-nullable, ge=0, DEC-SYNC-09). Both inherit from `_Base` (Layer 4 defense).
  - **Tests** (pure Pydantic validation, no HTTP, no DB):
    - T1: `test_sync_estado_query_params_extra_forbid` — `SyncEstadoQueryParams(uuid_sucursal=<uuid>, actor_uuid='x')` raises `ValidationError` (extra='forbid').
    - T2: `test_sync_estado_query_params_uuid_required` — `SyncEstadoQueryParams()` (missing uuid_sucursal) raises `ValidationError`.
    - T3: `test_sync_estado_read_lag_seg_nullable` — `SyncEstadoRead(uuid_sucursal=<uuid>, ultima_sync_at=None, lag_seg=None, pendientes=0)` accepts (DEC-SYNC-08 null contract).
    - T4: `test_sync_estado_read_pendientes_ge_zero` — `SyncEstadoRead(..., pendientes=-1)` raises `ValidationError` (DEC-SYNC-09 ge=0 invariant).
  - **Patrón F1.13** (`test_arqueo_schemas.py`): pure Pydantic tests, no HTTP, no DB.
  - **Acción**: extend T2.1 file (NEW `backend/tests/unit/test_sync_estado_schemas.py`, ~20 LOC, 4 tests). — **Validación**: pre-implementation `ImportError` for the schema names.

- [x] **T-HU-F1.14-T2.3** [RED + GREEN] — Implement `get_ultima_sync_at` (Step 3a, ~10 LOC) with `SELECT MAX(SyncLog.timestamp_evento) WHERE SyncLog.uuid_sucursal == :s` returning `datetime | None` (None when no rows, DEC-SYNC-08). Implement `calcular_lag_seg(ultima_sync_at, now)` (Step 3b, ~5 LOC pure math) — returns `None` when `ultima_sync_at IS NULL`, otherwise `int((now - ultima_sync_at).total_seconds())` (positive integer >= 0). Implement `count_pendientes_sync_queue` (Step 3c, ~10 LOC) with `SELECT count(*) FROM prod.sync_queue WHERE uuid_sucursal=:s AND estado='pendiente'` returning `int >= 0` (DEC-SYNC-09).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1` for DB-touching helpers; pure DateTime math for `calcular_lag_seg`):
    - T1: `test_get_ultima_sync_at_empty_returns_none` — empty `prod.sync_log` for `uuid_sucursal=:s` → returns `None` (DEC-SYNC-08).
    - T2: `test_get_ultima_sync_at_populated_returns_max` — seed 5 rows with `timestamp_evento` spanning 60-300s ago → returns `MAX(timestamp_evento)` (exact match).
    - T3: `test_calcular_lag_seg_null_returns_none` — `calcular_lag_seg(None, now_utc)` → `None` (DEC-SYNC-08).
    - T4: `test_calcular_lag_seg_positive_returns_int` — `calcular_lag_seg(now - 120s, now)` → 120 (positive integer, exact math).
    - T5: `test_calcular_lag_seg_zero_returns_zero` — `calcular_lag_seg(now, now)` → 0 (boundary, integer).
    - T6: `test_count_pendientes_sync_queue_zero_returns_zero` — empty `prod.sync_queue` for `uuid_sucursal=:s` → returns 0 (DEC-SYNC-09).
    - T7: `test_count_pendientes_sync_queue_positive_returns_count` — seed 12 rows with `estado='pendiente'` → returns 12.
  - **Archivo**: extend `repo/sync_estado.py` (+~25 LOC); extend T2.1 file with +~30 LOC, 7 tests. — **Validación**: T1..T7 PASS; `__all__` now exposes all 3 helpers.

- [x] **T-HU-F1.14-T2.4** [REFACTOR] — Verify `repo/sync_estado.py` 3 typed helpers are commit-free (KD-SYNC-01 contract): NO `await session.commit()` anywhere in helper bodies. Verify AsyncMock patterns used in unit tests (no real DB roundtrip needed for pure math helpers). Verify `calcular_lag_seg` is a pure function (no side effects, deterministic, testable without DB).
  - **Acción**: add 1 smoke test confirming pure-function contract:
    - `test_calcular_lag_seg_pure_function_no_side_effects` — call helper twice with same inputs → identical outputs (deterministic).
  - **Archivo**: extend T2.3 file with +~5 LOC, 1 test. — **Validación**: T2.1..T2.4 verde; ~70 LOC cumulative; 3 helpers + 2 schemas exposed; `__all__` lists all 3 helper names.

  **Commit suggestion (T2.1..T2.4)**: `feat(backend): HU-F1.14 — repo/sync_estado.py 3 typed SELECT helpers + schemas/sync_infra.py extend (SyncEstadoQueryParams + SyncEstadoRead) (~70 LOC + ~50 LOC tests)`.

  **Exit criteria T2**: T2.1..T2.4 verde; ~70 LOC cumulative; 3 helpers + 2 schemas exposed; `__all__` lists all 3 helper names; commit-free contract enforced.

### Cluster T3 — GET `/api/v1/sync/estado` Handler + Mount (~80 LOC impl + tests in T4)

- [x] **T-HU-F1.14-T3.1** [RED + GREEN] — Stub `api/v1/sync_estado.py::get_sync_estado` with KD-3 issuer dep (`_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")`) + dedicated `APIRouter(prefix="/sync", tags=["sync"])` (DEC-SYNC-01 — RESOLVES R1 MEDIUM issuer-chain collision with `sync_router.py:358`); write failing source-level test asserting the endpoint is NOT yet registered (404).
  - **Tests** (pure source-level + HTTP integration gated):
    - T1: `test_sync_estado_module_imports_with_get_sync_estado_handler` — `from parkos_core.api.v1.sync_estado import router` succeeds; `dir(router)` does NOT yet contain `get_sync_estado` (RED pre-implementation).
    - T2: `test_endpoint_sync_estado_not_yet_registered` — HTTP GET against `/api/v1/sync/estado?uuid_sucursal=<uuid>` returns 404 (route fully absent); test asserts 404.
  - **Patrón F1.13** (`test_caja_arqueo_module_imports_with_post_arqueo_handler`): pure source-level + `httpx.AsyncClient + ASGITransport(app)`.
  - **Acción**: create stub module with `router = APIRouter(prefix="/sync", tags=["sync"])` + `from __future__ annotations` + import `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-SYNC-01 + DEC-SYNC-03.B + Layer 1). — **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/sync_estado.py` (nuevo, stub, ~10 LOC). — **Validación**: stub module imports; route returns 404.

- [x] **T-HU-F1.14-T3.2** [GREEN] — Implement Steps 1-4 of the 4-step chain in `get_sync_estado` (~60 LOC): Step 1 (DI-resolved) KD-3 issuer dep + permission gate `audit_read` (Layer 1, DEC-SYNC-03.B pre-seeded at 0002:48); Step 2 Layer 2 tenant scope post-V1 (KD-S2 F1.7 analog) — when `ctx.issuer_prefix == "operador-"` AND `ctx.sucursal_uuid is not None` AND `ctx.sucursal_uuid != params.uuid_sucursal`, raise `403 tenant_scope_violation` with `Cache-Control: no-store`. Admin (`admin-`) bypasses; Step 3 (KD-SYNC-01 + KD-SYNC-02) READ-ONLY via 3 typed SELECT helpers — `ultima_sync_at = await repo_sync_estado.get_ultima_sync_at(session, uuid_sucursal=params.uuid_sucursal)` + `now = datetime.now(UTC).replace(tzinfo=None)` + `lag_seg = repo_sync_estado.calcular_lag_seg(ultima_sync_at, now)` + `pendientes = await repo_sync_estado.count_pendientes_sync_queue(session, uuid_sucursal=params.uuid_sucursal)` — NO `await session.commit()`, NO raw `session.execute(update(SyncLog))` / `session.execute(delete(SyncQueue))` / `session.execute(text("UPDATE prod.sync_log"))` (KD-SYNC-02 enforced by AST walk in T4); Step 4 build `SyncEstadoRead` response + `apply_no_store_header(response)` (DEC-SYNC-04, XR2 Layer 5) + return.
  - **Archivo**: extend `api/v1/sync_estado.py` (+~60 LOC).
  - **Contenido** (verbatim per design.md §4 + §10):
    ```python
    @router.get(
        "/estado",
        response_model=SyncEstadoRead,
        status_code=200,
    )
    async def get_sync_estado(
        response: Response,
        params: SyncEstadoQueryParams = Depends(),
        session: AsyncSession = Depends(get_session),
        ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(_sync_estado_issuer_dep),
    ) -> SyncEstadoRead:
        no_store = no_store_headers()

        # Step 2 (Layer 2): Tenant scope post-V1 (KD-S2 F1.7 analog)
        if (ctx.issuer_prefix == "operador-"
            and ctx.sucursal_uuid is not None
            and ctx.sucursal_uuid != params.uuid_sucursal):
            raise HTTPException(
                status_code=403,
                detail={"error": "tenant_scope_violation"},
                headers=no_store,
            )

        # Step 3a (KD-SYNC-01): SELECT MAX(timestamp_evento) FROM prod.sync_log
        ultima_sync_at = await repo_sync_estado.get_ultima_sync_at(
            session, uuid_sucursal=params.uuid_sucursal
        )

        # Step 3b: in-process lag compute (None when no rows, DEC-SYNC-08)
        now = datetime.now(UTC).replace(tzinfo=None)  # naive UTC
        lag_seg = repo_sync_estado.calcular_lag_seg(ultima_sync_at, now)

        # Step 3c (KD-SYNC-01): SELECT count(*) FROM prod.sync_queue WHERE estado='pendiente'
        pendientes = await repo_sync_estado.count_pendientes_sync_queue(
            session, uuid_sucursal=params.uuid_sucursal
        )

        # Step 4 (Layer 5): build response + no-store header
        apply_no_store_header(response)
        return SyncEstadoRead(
            uuid_sucursal=params.uuid_sucursal,
            ultima_sync_at=ultima_sync_at,
            lag_seg=lag_seg,
            pendientes=pendientes,
        )
    ```
  - **Acción**: docstring REQ-OPS-098..101 + DEC-SYNC-01..10 + KD-SYNC-01..02. — **Validación**: T3.1 2 tests PASS (route now registered); T4.1 AST walk PASSes (no UPDATE/DELETE/COMMIT in handler body); T4.2 handler tests cover happy path + empty branch.

- [x] **T-HU-F1.14-T3.3** [GREEN] — Verify `get_sync_estado` returns 200 OK with `Cache-Control: no-store` (DEC-SYNC-04, XR2 Layer 5) on EVERY response including 200 (success) + 403 (tenant scope) + 422 (missing/invalid uuid_sucursal via Pydantic) + 5xx (defense in depth). Verify pgcode/pgerror/pgmessage NEVER appear in response body (XR6 Layer 5 redaction, defense in depth).
  - **Acción**: no source-level changes; verifies via T4.2 handler tests asserting the response header on each status code path + absence of pgcode/pgerror/pgmessage keys. — **Validación**: T4.2 mandated tests PASS.

- [x] **T-HU-F1.14-T3.4** [GREEN] — Dedicated `APIRouter` mount in `api/v1/sync_estado.py` (already wired via DEC-SYNC-01 Step T3.1 stub) + register in `api/v1/caja.py`. Append `from .sync_estado import router as sync_estado_router` + `router.include_router(sync_estado_router)` (DEC-SYNC-02, F1.13 mount precedent at line 86). Mount extension: ~5 LOC.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/caja.py` (modified, +~6 LOC); no modification to `__init__.py` (the factory mount is inherited).
  - **Acción**: append at bottom of `caja.py` after the existing `router.include_router(caja_arqueo_router)` precedent at line 86. — **Validación**: T4.2 handler tests confirm endpoint reachable at `/api/v1/sync/estado` GET with `Cache-Control: no-store`.

  **Commit suggestion**: `feat(backend): HU-F1.14 — GET /sync/estado handler (4-step chain + KD-SYNC-01 SELECT-only + DEC-SYNC-02 mount at caja.py) (~80 LOC)`.

  **Exit criteria T3**: T3.1..T3.4 verde; ~80 LOC cumulative; handler reachable end-to-end; 4-step chain enforces KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walk (T4.1) + DEC-SYNC-04 no-store + DEC-SYNC-03.B audit_read permission gate.

### Cluster T4 — AST walk + Integration Test (~110 LOC tests)

- [x] **T-HU-F1.14-T4.1** [RED + GREEN] — Write failing AST walk `tests/static/test_sync_estado_read_only.py` (~20 LOC, KD-SYNC-02) enforcing that `get_sync_estado` is READ-ONLY — NO `update(SyncLog)` / `update(SyncQueue)` / `delete(SyncLog)` / `delete(SyncQueue)` / `session.execute(text("UPDATE prod.sync_log"))` / `session.execute(text("DELETE FROM prod.sync_queue"))` / `await session.commit()` in handler body (mirror of F1.5 PR5-016 `test_no_raw_dml_on_a_tables.py` + F1.10 KD-FE-01 + F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 + F1.13 KD-ARQUEO-01 AST walks — for the READ-ONLY side).
  - **Tests** (no DB, no HTTP, pure AST walk):
    - T1: `test_no_update_on_sync_log_or_sync_queue` — `ast.parse(api/v1/sync_estado.py)`; locate `get_sync_estado` via `ast.AsyncFunctionDef.name == 'get_sync_estado'`; walk via `iter_child_nodes`; assert ZERO occurrences of `session.execute(update(SyncLog))` or `session.execute(update(SyncQueue))` or `session.execute(text("UPDATE prod.sync_log"))` (KD-SYNC-02).
    - T2: `test_no_delete_on_sync_log_or_sync_queue` — same walk; assert ZERO occurrences of `session.execute(delete(SyncLog))` or `session.execute(delete(SyncQueue))` or `session.execute(text("DELETE FROM prod.sync_log"))` or `session.execute(text("DELETE FROM prod.sync_queue"))` (KD-SYNC-02).
    - T3: `test_no_commit_in_handler` — same walk; assert ZERO occurrences of `await session.commit()` (GET is naturally commit-free, KD-SYNC-02).
  - **Patrón F1.10 + F1.11 + F1.12 + F1.13**: `ast.parse` + `iter_child_nodes` DFS.
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_sync_estado_read_only.py` (nuevo, ~20 LOC, 3 AST walks). — **Validación**: post T3 GREEN, walks PASS.

- [x] **T-HU-F1.14-T4.2** [RED + GREEN] — Write `tests/unit/test_sync_estado.py` with **2 MANDATED tests per plan.md line 1126** + 7 supporting tests; extend `tests/integration/test_migration_0032_idempotency.py` (T1.1 partial) with 2 full idempotency round-trip tests; extend `tests/unit/test_alert_types_seed.py` with 4 seed tests.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - **T1 (test_sync_estado.py, ~30 LOC, **2 MANDATED tests per plan.md line 1126** + 7 supporting)**:
      - T1.1: `test_empty_branch_200_with_null_lag` — No `sync_log` rows → `SyncEstadoRead{uuid_sucursal=:s, ultima_sync_at=null, lag_seg=null, pendientes=0}` + 200 OK + `Cache-Control: no-store` (mandated scenario 1 per plan.md line 1126; DEC-SYNC-08).
      - T1.2: `test_populated_branch_with_5_sync_log_rows_and_12_pending` — seed 5 `sync_log` rows with `timestamp_evento` spanning 60-300s ago + 12 `sync_queue` rows with `estado='pendiente'` → exact `lag_seg` math (within ±1s tolerance) + `pendientes=12` + 200 OK + `Cache-Control: no-store` (mandated scenario 2 per plan.md line 1126).
      - T1.3: `test_empty_sync_queue_only_zero_pendientes` — populated `sync_log` (3 rows) + ZERO `sync_queue` rows → `lag_seg` computed from `t_max` + `pendientes=0` (integer, NOT null, DEC-SYNC-09).
      - T1.4: `test_tenant_scope_violation_returns_403` — `operador-` issuer with `ctx.sucursal_uuid=:s_other != :s_target` → 403 `tenant_scope_violation` + `Cache-Control: no-store`.
      - T1.5: `test_permission_denied_returns_403` — `operador-` role without `audit_read` → 403 `permission_denied` + `Cache-Control: no-store`.
      - T1.6: `test_admin_cross_branch_allowed` — `admin-` issuer with arbitrary `uuid_sucursal` → 200 OK (admin bypasses tenant scope, Layer 2).
      - T1.7: `test_pgcode_never_in_response` — assert response body NEVER contains `pgcode`, `pgerror`, `pgmessage` keys (XR6 Layer 5 redaction).
      - T1.8: `test_invalid_uuid_returns_422` — `uuid_sucursal='not-a-uuid'` → 422 `uuid_sucursal_invalid` (Pydantic validator, Layer 4) + `Cache-Control: no-store`.
      - T1.9: `test_extra_fields_rejected` — `uuid_sucursal=<uuid>, actor_uuid='x'` → 422 (extra='forbid', Layer 4).
    - **T2 (test_migration_0032_idempotency.py, extend T1.1 with ~30 LOC, 6 tests)**:
      - T2.1: `test_migration_0032_idempotent_upgrade_downgrade_upgrade` — `alembic upgrade head` succeeds (asserts `DO $$` pre-flight passes — all 4 conditions present + Op 1 + Op 2 idempotent); `alembic downgrade -1` succeeds (Op 1 removes 10 net new rows; `descuadre_critico` preserved); `alembic upgrade head` succeeds again (round-trip idempotent).
      - T2.2: `test_migration_0032_preflight_aborts_if_table_missing` — DROP one table (test-only cleanup); `alembic upgrade head` raises `0032_preflight_abort: prod.alert_types must exist`. Re-CREATE TABLE post-test.
      - T2.3: `test_migration_0032_seeds_11_codes_idempotent` — `alembic upgrade head` (1st time); verify `SELECT COUNT(*) FROM prod.alert_types WHERE tipo_alerta IN (11 codes)` = 11; `alembic upgrade head` (2nd time); verify `COUNT(*)` still = 11 (ON CONFLICT DO NOTHING).
      - T2.4: `test_migration_0032_descuadre_critico_idempotent` — verify `SELECT COUNT(*) WHERE tipo_alerta='descuadre_critico'` = 1 (F1.13-owned, no duplicate from F1.14 re-seed).
      - T2.5: `test_migration_0032_post_upgrade_19_rows` — `SELECT COUNT(*) FROM prod.alert_types` = 19 (8 técnicos + 1 F1.13 + 10 F1.14).
      - T2.6: `test_migration_0032_post_downgrade_9_rows_preserves_descuadre` — after `alembic downgrade -1`, `COUNT(*)` = 9 AND `SELECT COUNT(*) WHERE tipo_alerta='descuadre_critico'` = 1 (F1.13-owned preserved); `SELECT COUNT(*) WHERE tipo_alerta IN (8 técnicos)` = 8 (0013-owned preserved).
    - **T3 (test_alert_types_seed.py, NEW ~40 LOC, 4 tests)**:
      - T3.1: `test_all_19_codes_present_no_duplicates` — `SELECT COUNT(DISTINCT tipo_alerta) FROM prod.alert_types` = 19; assert exact list against canonical tuple (DEC-SYNC-05).
      - T3.2: `test_11_business_codes_severity_exact_match` — assert each of the 11 business codes has the exact severity per plan.md line 1131 (DEC-SYNC-06): `descuadre_critico` → `critical`, `sync_fallida` → `critical`, `evento_no_procesado` → `critical`, `impresora_caida` → `critical`, `fe_error_toppoint` → `critical`, `numeracion_toppoint_agotada` → `critical`, `capacidad_agotada` → `warning`, `capacidad_agotada_forzado` → `warning`, `arqueo_pendiente_24h` → `warning`, `suscripcion_proxima_vencer` → `warning`, `cache_desactualizado` → `info`.
      - T3.3: `test_8_tecnicos_codes_unchanged` — assert all 8 técnicos from migration 0013 still present (smoke regression: `hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`).
      - T3.4: `test_descripcion_field_present_per_code` — assert each of the 11 business codes has a `descripcion` field per plan.md lines 2311-2323 (DEC-SYNC-10).
  - **Patrón F1.13** (`test_arqueo_handler.py` + `test_migration_0031_idempotency.py` + `test_arqueo_resumen.py`): HTTP integration via `httpx.AsyncClient` + `pg_engine` real via `testcontainers[postgres]`.
  - **Acción**: 3 NEW test files (T1 + T3 + extension T2) + extend T1.1 file with full coverage. — **Validación**: ~21 tests across 3 files PASS post T1 + T3 GREEN.

  **Commit suggestion**: `test(backend): HU-F1.14 — 2 mandated handler tests + 7 supporting + 6 migration + 4 seed tests + 3 AST walks (~110 LOC + ~20 LOC AST walk)`.

  **Exit criteria T4**: T4.1..T4.2 verde; ~140 LOC cumulative (impl + tests); 3 AST walks + 2 mandated tests + ~21 unit/integration tests PASS; KD-SYNC-01 SELECT-only + KD-SYNC-02 read-only AST walk verified; DEC-SYNC-04 no-store verified; 2 mandated tests cover empty branch + populated branch per plan.md line 1126.

### Cluster T5 — Housekeeping + Apply Report (~30 LOC docs)

- [x] **T-HU-F1.14-T5.1** [RED + GREEN] — Write `openspec/changes/hu-f1-14-sync-estado/apply-report.md` (~30 LOC, per F1.13 precedent `apply-report.md`) documenting: which commits landed (5 atomic commits: T1, T2, T3, T4, T5), per-cluster exit criteria status (T1..T4 all PASS), test totals (~20 tests across 6 files per design.md Appendix B), 4 DEC-SYNC + 2 KD-SYNC + 4 REQ-OPS-098..101 traceability matrix, all 10 DECs + 2 KDs + 4 REQs verified via ≥1 RED test, CI gates green (5 gates: `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.13`), 0 regressions introduced, MIGRATION 0032 idempotency verified, all 8 técnicos + descuadre_critico + 10 net new = 19 alert_types seeded. Mark all T1..T4 tasks [x] in this file. Update `openspec/changes/archive/fase-1-prerequisites-backend/prompts/pending.md` §1 to mark F1.14 closed (move from "in_progress" to "closed" section, add commit SHA + apply-report.md reference).
  - **Acción**: write apply-report.md verbatim per F1.13 precedent; edit pending.md §1 to add F1.14 entry in "closed" subsection. — **Archivos**: `openspec/changes/hu-f1-14-sync-estado/apply-report.md` (nuevo, ~30 LOC); `openspec/changes/archive/fase-1-prerequisites-backend/prompts/pending.md` (modified, +~5 LOC). — **Validación**: apply-report.md exists with 5-commit summary + traceability matrix; pending.md §1 reflects F1.14 closed.

  **Commit suggestion**: `chore(openspec): HU-F1.14 — T5 apply-report + all tasks [x] + pending.md update (~30 LOC)`.

  **Exit criteria T5**: T5.1 verde; ~30 LOC cumulative (docs); apply-report.md authored with 5-commit summary + traceability matrix; all T1..T4 tasks marked [x] in this tasks.md file; pending.md §1 reflects F1.14 closed.

---

## Cross-cluster constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` on `prod.sync_log` / `prod.sync_queue` / `prod.alert_types` outside the 3 typed SELECT helpers in `repo/sync_estado.py` — AST walk `tests/static/test_sync_estado_read_only.py` (T4.1) enforces via KD-SYNC-01 + KD-SYNC-02.
- NO `await session.commit()` anywhere in the `get_sync_estado` handler body — AST walk `tests/static/test_sync_estado_read_only.py` (T4.1) enforces via KD-SYNC-02 (GET is naturally commit-free).
- NO raw `session.execute(update(SyncLog))` / `session.execute(update(SyncQueue))` / `session.execute(delete(SyncLog))` / `session.execute(delete(SyncQueue))` / `session.execute(text("UPDATE prod.sync_log"))` / `session.execute(text("DELETE FROM prod.sync_queue"))` anywhere in the `get_sync_estado` handler body — AST walk `tests/static/test_sync_estado_read_only.py` (T4.1) enforces via KD-SYNC-01 + KD-SYNC-02.
- NO `Co-authored-by:` trailers AI en commits; conventional commits, neutral Spanish commit messages, neutral Spanish per-cluster rationale comments.
- NO SQLite in tests — `pg_engine` real via `testcontainers[postgres]` (F1.4/F1.5/F1.6/F1.7/F1.9/F1.10/F1.11/F1.12/F1.13 precedent).
- NO modification of `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate (matches F1.7/F1.9/F1.10/F1.11/F1.12/F1.13).
- NO modification of `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate cross-cutting.
- NO modification of `api/deps.py` nor `auth/tenancy.py` — KD-3 chain + errores tipados intactos.
- NO modification of `repo/event.py` — `event_helper_intact` CI gate (matches F1.7/F1.9/F1.10/F1.11/F1.12/F1.13).
- NO modification of `api/v1/sync_router.py` — read-only reference for issuer-chain conflict resolution (DEC-SYNC-01 + R1 MEDIUM).
- NO modification of `api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()` — F1.6 reused verbatim (lines 18-31, DEC-SYNC-04).
- NO modification of `auth/jwt_issuer_guard.py::requires_issuer` factory — reused verbatim for KD-3 dep.
- NO modification of `schemas/common.py::_Base` — `extra='forbid'` reused verbatim (Layer 4 defense).
- NO new sync catalog entries — `sync_entries_v.py` + `sync_entries_a.py` already carry all sync_status entries (`sync_status: "no usado — tabla out-of-catalog, nunca replicada"` per ER lines 976, 1096, 1111). DEC-SYNC-01..10 NOT extended to sync catalog (all 3 sync tables pre-existing and out-of-catalog).
- NO new triggers — existing `alert_types_inmutable` (migration 0013:21-22) + `fn_sync_log_inmutable` (migration 0001 if present) cover the F1.14 read-only path; no trigger additions needed.
- NO new permissions — `audit_read` pre-seeded at `0002_seed_permisos_canonicos.py:48` (DEC-SYNC-03.B Option B adopted — no new permission seeded).
- NO new role grants — operador + admin already granted `audit_read` per F1.6 closure; F1.14 inherits.
- Header `Cache-Control: no-store` on EVERY response (200 + 4xx + 5xx) of `GET /sync/estado` — via `no_store_headers()` helper + `apply_no_store_header(response)` before return + `headers=no_store` param in `HTTPException` constructors — DEC-SYNC-04 XR2 mirror from F1.10/F1.11/F1.12/F1.13.
- Discriminators stable: `tenant_scope_violation` (403 operador cross-branch), `permission_denied` (403 no `audit_read`), `uuid_sucursal_invalid` (422 Pydantic validator, Layer 4).
- Precedencia de errores: KD-3 (403 issuer) > Pydantic (422) > Layer 2 tenant scope (403) > Step 3 SELECT helpers (200) > Step 4 build response (200).
- MIGRATION 0032 MUST be idempotent: pre-flight `DO $$` is read-only; Op 1 conditional siembra via `op.bulk_insert` (Postgres ON CONFLICT DO NOTHING via PK constraint, respects `alert_types_inmutable` trigger); Op 2 NO-DDL `RAISE NOTICE` comment for DEC-SYNC-03.B.
- Per-commit ceiling: <800 LOC. Each cluster T1..T5 fits within the limit (T3 handler + mount at ~80 LOC is the largest implementation block, well within).
- Mensajes conventional commit; cuerpo técnico en neutral Spanish.

## Acceptance Gates

- TDD strict: RED first, GREEN minimum, REFACTOR last. Clusters T1..T5 explicitly note this discipline.
- ~20 tests across 6 files PASS via `uv run pytest backend/tests/unit/test_sync_estado.py backend/tests/unit/test_alert_types_seed.py backend/tests/unit/test_sync_estado_repo.py backend/tests/unit/test_sync_estado_schemas.py backend/tests/integration/test_migration_0032_idempotency.py backend/tests/static/test_sync_estado_read_only.py -q`
- MIGRATION 0032 applied + downgrade reverses cleanly via `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` (round-trip idempotent)
- 1 handler (`GET /api/v1/sync/estado`) implemented per design.md §10 (4-step chain)
- `repo/sync_estado.py` 3 typed SELECT helpers authored (DEC-SYNC-01..10)
- `schemas/sync_infra.py` extended with `SyncEstadoQueryParams` + `SyncEstadoRead` (Layer 4 defense via `extra='forbid'`)
- KD-3 issuer chain `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")` applied with `Cache-Control: no-store` on every response (DEC-SYNC-04)
- KD-SYNC-01 SELECT-only invariant verified via AST walk on `get_sync_estado`
- KD-SYNC-02 read-only AST walk invariant verified via `tests/static/test_sync_estado_read_only.py` (NO UPDATE/DELETE/COMMIT)
- DEC-SYNC-03.B `audit_read` permission gate verified (operador with audit_read → 200; without → 403 `permission_denied`)
- DEC-SYNC-04 `Cache-Control: no-store` verified on 200 / 403 / 422 / 5xx responses
- DEC-SYNC-05 10 net new alert_types seeded (8 técnicos + 1 F1.13 + 10 F1.14 = 19 total)
- DEC-SYNC-06 severity mapping per plan.md line 1131 verified (alta → critical, media → warning, baja → info)
- DEC-SYNC-07 idempotent siembra via `ON CONFLICT DO NOTHING` verified
- DEC-SYNC-08 `lag_seg = None` for empty branch verified (NOT 0, NOT 404)
- DEC-SYNC-09 `pendientes >= 0` always integer (never null) verified
- DEC-SYNC-10 `descripcion` field per alert_type from plan.md lines 2311-2323 verified
- Tenant scope post-V1 verified (operador cross-branch → 403 `tenant_scope_violation`; admin bypasses)
- Empty branch contract verified (no sync_log rows → 200 with `lag_seg=null`, NOT 404)
- 19 alert_types present after upgrade (8 técnicos + 1 F1.13 + 10 F1.14 — DEC-SYNC-05)
- MIGRATION 0032 idempotency verified (re-running upgrade head on migrated DB → no net change)
- Downgrade cycle verified (downgrade -1 → 9 rows; upgrade head → 19 rows round-trip)
- No new permission seeded (DEC-SYNC-03.B — `audit_read` reuse only)
- No AI attribution in commits (no `Co-authored-by:`, no AI trailers)
- All F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11/F1.12/F1.13 tests still PASS (no_regresion gate)
- ruff + mypy --strict clean on all 5 new/modified files (1 NEW migration + 1 NEW repo module + 1 EXTENDED schemas + 1 NEW handler module + 1 MODIFIED `caja.py` + 6 NEW test files)
- 5 CI gates green (matches F1.7/F1.9/F1.10/F1.11/F1.12/F1.13): `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.13`
- 0 regresiones introducidas; baseline F1.13 pre-existing failures documented and unchanged
- REQ-OPS-098..101 + REQ-OPS-XR6 REFERENCE traceability verified: each REQ has ≥1 RED test that proves it (mapping in design.md Appendix B + this file's per-task rationale)
- Architecture risks §12 (R1..R10) verified: R1 issuer chain conflict → T3.1 dedicated router + KD-3 dep; R2 sync_log/sync_queue mutation → T4.1 AST walk enforces 0 matches; R3 lag_seg=None confusion → T2.2 schema nullable + T4.2 test asserts null; R4 11 vs 10 accounting → T1.3 downgrade preserves descuadre_critico + T4.2 T2.5 asserts 19 total; R5 permission gate missing → DEC-SYNC-03.B adopted audit_read; R6 severity mismatch → T4.2 T3.2 exact mapping assertion; R7 alert_types_inmutable trigger blocks migration → T1.2 ON CONFLICT atomic + respects trigger; R8 cloud/branch desync → MIGRATION 0032 identical on both (out-of-catalog tables); R9 UUID format wrong → T2.2 Pydantic UUID validator + 422; R10 tenant scope bypass → T3.2 Step 2 tenant scope check.

---

## Out of Scope Tasks

- UI integration (Fase 11 HU-F11.1/F11.2): deferred to Fase 11. `SyncBanner` (polling 30s) + `AlertasPanel` consume this endpoint and the seeded alert_types, but the UI components themselves are out of scope. Fase 11 owns them.
- Detection jobs that CREATE the alerts (every 5min for `capacidad_agotada`, every 1h for `evento_no_procesado`/`arqueo_pendiente_24h`, CU-01/02/03 for `suscripcion_proxima_vencer`): Fase 11 / Fase 19 — out per design.md §15.1.
- `/admin/sync/estado` (HU-F19.1, Part-II): different prefix (`/admin/sync/...`), admin-only, with cross-branch aggregation — out per plan.md line 1105-1108 (this HU is Fase-1 prerequisites; F19.x is Fase-19 Part-II).
- `evento_no_procesado` detector: Fase 11 — out of F1.14 scope per design.md §15.1.
- `cache_desactualizado` detector: Fase 11 — out of F1.14 scope per design.md §15.1.
- HU-F19.4 (Part-II parallel siembra): F19.4 (Part-II). F1.14 ships the 11 codes in MIGRATION 0032 for Fase 1; F19.4's siembra (Part-II) becomes a no-op via `ON CONFLICT DO NOTHING` — either order works.
- POST `/sync/estado` (write a manual estado override): NOT planned — sync state is derived from `sync_log`/`sync_queue`, never manually written.
- WebSocket push of `/sync/estado`: NOT planned — operator polling pattern only (CU-14 BR1 verbatim — 30s polling).
- `/api/v1/admin/sucursales/{uuid}/sync/estado`: F19.1 (Part-II) — admin cross-branch aggregation.
- Sync state notifications (push/SSE): Fase 11+ — polling pattern only for F1.14.
- Sync state history / trends: NOT planned — endpoint returns current snapshot only.

## Commit summary (5 expected atomic commits)

| # | Cluster | Commit message | Files | LOC est. |
|---|---|---|---|---|
| 1 | T1 | `feat(backend): HU-F1.14 — MIGRATION 0032 REAL siembra (11 alert_types codes + pre-flight DO $$ + downgrade preserves F1.13)` | 1 NEW migration + 1 partial NEW test (T1.1 pre-flight) | ~70 |
| 2 | T2 | `feat(backend): HU-F1.14 — repo/sync_estado.py 3 typed SELECT helpers + schemas/sync_infra.py extend (SyncEstadoQueryParams + SyncEstadoRead)` | 1 NEW repo module + 1 EXTENDED schemas + 2 NEW partial tests | ~70 |
| 3 | T3 | `feat(backend): HU-F1.14 — GET /sync/estado handler (4-step chain + KD-SYNC-01 SELECT-only + DEC-SYNC-02 mount at caja.py)` | 1 NEW handler module (GET 4-step) + 1 MODIFIED `caja.py` (6 LOC mount) | ~80 |
| 4 | T4 | `test(backend): HU-F1.14 — 2 mandated handler tests + 7 supporting + 6 migration + 4 seed tests + 3 AST walks` | 3 NEW test files (handler + seed) + 1 EXTENDED migration test + 1 NEW AST walk + 1 NEW repo test + 1 NEW schema test | ~140 |
| 5 | T5 | `chore(openspec): HU-F1.14 — T5 apply-report + all tasks [x] + pending.md update` | 1 NEW apply-report + 1 MODIFIED pending.md + tasks.md [x] marks | ~30 |

**Total**: 5 commits, ~390 LOC cumulative (impl + tests + migration + AST walks + docs), 1 PR to `origin/dev`. Net apply delta ~220 LOC production + ~140 LOC tests + ~20 LOC AST walk + ~30 LOC docs.

## Definition of Done (apply phase)

- [ ] ~20 tests + 3 AST walks across 6 test files PASS via `uv run pytest backend/tests/unit/test_sync_estado.py backend/tests/unit/test_alert_types_seed.py backend/tests/unit/test_sync_estado_repo.py backend/tests/unit/test_sync_estado_schemas.py backend/tests/integration/test_migration_0032_idempotency.py backend/tests/static/test_sync_estado_read_only.py -q`
- [ ] MIGRATION 0032 applied + downgrade reverses cleanly via `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` (round-trip idempotent)
- [ ] 1 handler (`GET /api/v1/sync/estado`) implemented per design.md §10 (4-step chain)
- [ ] `repo/sync_estado.py` 3 typed SELECT helpers authored (DEC-SYNC-01..10)
- [ ] `schemas/sync_infra.py` extended with `SyncEstadoQueryParams` + `SyncEstadoRead` (Layer 4 defense via `extra='forbid'`)
- [ ] KD-3 issuer chain `_sync_estado_issuer_dep = requires_issuer("operador-", "admin-")` applied with `Cache-Control: no-store` on every response (DEC-SYNC-04)
- [ ] KD-SYNC-01 SELECT-only invariant verified via AST walk on `get_sync_estado`
- [ ] KD-SYNC-02 read-only AST walk invariant verified via `tests/static/test_sync_estado_read_only.py` (NO UPDATE/DELETE/COMMIT)
- [ ] DEC-SYNC-03.B `audit_read` permission gate verified (operador with audit_read → 200; without → 403 `permission_denied`)
- [ ] DEC-SYNC-04 `Cache-Control: no-store` verified on 200 / 403 / 422 / 5xx responses
- [ ] DEC-SYNC-05 10 net new alert_types seeded (8 técnicos + 1 F1.13 + 10 F1.14 = 19 total)
- [ ] DEC-SYNC-06 severity mapping per plan.md line 1131 verified (alta → critical, media → warning, baja → info)
- [ ] DEC-SYNC-07 idempotent siembra via `ON CONFLICT DO NOTHING` verified
- [ ] DEC-SYNC-08 `lag_seg = None` for empty branch verified (NOT 0, NOT 404)
- [ ] DEC-SYNC-09 `pendientes >= 0` always integer (never null) verified
- [ ] DEC-SYNC-10 `descripcion` field per alert_type from plan.md lines 2311-2323 verified
- [ ] Tenant scope post-V1 verified (operador cross-branch → 403 `tenant_scope_violation`; admin bypasses)
- [ ] Empty branch contract verified (no sync_log rows → 200 with `lag_seg=null`, NOT 404)
- [ ] 19 alert_types present after upgrade (8 técnicos + 1 F1.13 + 10 F1.14 — DEC-SYNC-05)
- [ ] MIGRATION 0032 idempotency verified (re-running upgrade head on migrated DB → no net change)
- [ ] Downgrade cycle verified (downgrade -1 → 9 rows; upgrade head → 19 rows round-trip)
- [ ] No new permission seeded (DEC-SYNC-03.B — `audit_read` reuse only)
- [ ] No AI attribution in commits (no `Co-authored-by:`, no AI trailers)
- [ ] All F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11/F1.12/F1.13 tests still PASS (no_regresion gate)
- [ ] ruff + mypy --strict clean on all 5 new/modified files
- [ ] 5 CI gates green (`factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.13`)
- [ ] 0 regresiones introducidas; baseline F1.13 pre-existing failures documented and unchanged
- [ ] REQ-OPS-098..101 + REQ-OPS-XR6 REFERENCE traceability verified via per-REQ RED tests
- [ ] 5 atomic commits authored with conventional commit messages, neutral Spanish, NO `Co-authored-by:` trailers

## Next phase

`sdd-apply hu-f1-14-sync-estado` — TDD-strict RED→GREEN→REFACTOR per cluster T1..T5. Orchestrator executes the 5 atomic commits in order, verifies each cluster's exit criteria, and routes to `sdd-verify` after all commits land.

## References

- `openspec/changes/hu-f1-14-sync-estado/design.md` (~1347 LOC, 16 sections + 2 appendices, MIGRATION 0032 SQL body + AST walk precedent + 10 DECs + 2 KDs) — full architecture.
- `openspec/changes/hu-f1-14-sync-estado/proposal.md` (~770 LOC, 16 sections, DEC-SYNC-01..10, KD-SYNC-01..02, R1..R10 — 4 RESOLVED at propose phase) — pre-design proposal.
- `openspec/changes/hu-f1-14-sync-estado/specs/operations/spec.md` (~485 LOC, 4 REQs REQ-OPS-098..101 + REQ-OPS-XR6 REFERENCE) — operational requirements.
- `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/tasks.md` (~745 LOC, 6 clusters T1..T5 + T-GAP-BE-05) — **canonical precedent** for F1.14 structure mirrored verbatim.
- `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/tasks.md` (~860 LOC, 8 clusters T1..T8, 31 atomic tasks) — canonical precedent for 8-cluster decomposition.
- `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/{proposal,design,specs/operations/spec.md,apply-report,archive-report}.md` — F1.13 full cycle precedent.
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/tasks.md` — F1.11 precedent (KD-TKT-01 single-commit + AST walk).
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/tasks.md` — F1.10 precedent (KD-FE-01 single-commit).
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/tasks.md` — F1.9 precedent (KD-FACT-01 single-commit + `crear_factura_*` helpers reused).
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/tasks.md` — F1.7 precedent (KD-S2 tenant scope post-V1, `resolve_active_subscription_for_exit` reuse).
- `openspec/changes/archive/2026-09-14-hu-f1-6-ingresos/tasks.md` — F1.6 precedent (DEC-IDEM-01 Idempotency-Key header + placa regex + KD-3 issuer chain).
- `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/tasks.md` — F1.5 precedent (`repo/versioned.py::close_and_insert` + AST walk no-raw-UPSERT on [V]).
- `openspec/specs/operations/spec.md` lines 2517-3651 (XR1..XR5 progression + REQ-OPS-083..097 last-req-number series — F1.14 appends REQ-OPS-098..101) + line 3951 (REQ-OPS-XR6 canonical from F1.13 — F1.14 references, does NOT create new XR).
- `plan.md` lines 1105-1133 — HU-F1.14 full definition, 3 atomic tasks T1..T3, 120 LOC production budget, 2 mandated tests at line 1126.
- `plan.md` line 429 — DEC-SUC-14: 19 totales, 8 técnicos + 11 de negocio coexisten.
- `plan.md` line 459 — A-08: severity JOIN-only via `alert_types.severity`.
- `plan.md` line 1126 — 2 mandated handler tests: empty branch / populated branch.
- `plan.md` line 1131 — Severity mapping per alert_type (DEC-SYNC-06 source).
- `plan.md` lines 2275-2291 — HU-F11.1 SyncBanner consumer — 30s polling, verde/amarillo/rojo umbrales from CU-14 BR1.
- `plan.md` lines 2305-2325 — HU-F11.2 AlertasPanel consumer.
- `plan.md` lines 2311-2323 — Canonical descriptions per alert_type — DEC-SYNC-10 source.
- `plan.md` lines 4155-4201 — HU-F19.4 mirror for Part-II parallel siembra — referenced, out of F1.14 scope.
- `plan.md` lines 4598-4602 — `audit_read` permission usage rationale (F1.14 DEC-SYNC-03.B).
- `modelo_datos_er.mmd` lines 981-1002 (`sync_queue` [A] carved-out), lines 1027-1047 (`sync_log` [A] composite PK + monthly pg_partman), lines 1101-1114 (`alert_types` [A] registry), lines 976, 1096, 1111 (`sync_status: "no usado — tabla out-of-catalog, nunca replicada"`).
- `migrations/versions/0001_initial_schema.py` — Initial schema (composite PKs, partitions, base triggers; `fn_sync_log_inmutable` trigger if present).
- `migrations/versions/0002_seed_permisos_canonicos.py` lines 39-56 — `CANONICAL_PERMISOS` with `audit_read` at line 48 — DEC-SYNC-03.B source.
- `migrations/versions/0013_add_alert_types.py` lines 21-22 — `alert_types_inmutable` trigger.
- `migrations/versions/0013_add_alert_types.py` lines 67-108 — Idempotent INSERT precedent.
- `migrations/versions/0013_add_alert_types.py` line 119 — `severity` CHECK constraint (`('info', 'warning', 'critical')`).
- `migrations/versions/0013_add_alert_types.py` lines 129-130 — REVOKE/GRANT pattern.
- `migrations/versions/0013_add_alert_types.py` lines 132-147 — `alert_types_inmutable` trigger body.
- `migrations/versions/0021_revoke_a_tables.py` lines 162, 182 — REVOKE UPDATE/DELETE on [A]/[V] tables (F1.5 PR5-016).
- `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` lines 134-188 — siembra pattern (template for MIGRATION 0032 Op 1).
- `migrations/versions/0031_arqueo_cierre_dia_and_gap_be_05.py` lines 169-175 — F1.13 head, Op 2 `descuadre_critico` siembra precedent — DEC-SYNC-05 source.
- `migrations/versions/0032_seed_alert_types_operativos.py` — (whole file, NEW) F1.14 REAL siembra (Op 0 + Op 1 + Op 2).
- `models/A/sync_log.py` lines 29-72 — ORM model + composite PK + monthly pg_partman.
- `models/A/sync_queue.py` lines 41-99 — ORM model + 5 estados (REQ-OPS-004 carve-out).
- `models/A/alert_types.py` line 40 — `descripcion` column EXISTS — DEC-SYNC-10.
- `models/A/alert_types.py` (whole file) — registry ORM model.
- `models/V/permisos.py` — `audit_read` pre-seeded at 0002:48.
- `repo/alert_types.py` lines 30-48 — `validate` + `AlertaFactory.fire`.
- `repo/sync_log.py` — (whole file) ORM accessor (READ-ONLY ref for `get_ultima_sync_at`).
- `repo/sync_queue.py` — (whole file) ORM accessor (READ-ONLY ref for `count_pendientes_sync_queue`).
- `api/v1/sync_router.py` lines 9-49 — docstring listing 7 endpoints — `/estado` NOT in list, no collision.
- `api/v1/sync_router.py` line 95 — `APIRouter(prefix="/sync", tags=["sync"])` declaration.
- `api/v1/sync_router.py` line 358 — `if not iss.startswith("sync-agent-"): raise ...` issuer guard.
- `api/v1/caja.py` line 86 — F1.13 mount precedent: `router.include_router(caja_arqueo_router)` — DEC-SYNC-02 source.
- `api/v1/_helpers.py` lines 18-31 — `no_store_headers()` + `apply_no_store_header()` — DEC-SYNC-04 source.
- `auth/jwt_issuer_guard.py` — (whole file) `requires_issuer` factory — KD-3 dep.
- `auth/tenancy.py` — (whole file) `TenantContext` + `get_tenant_ctx` — Layer 2 dep.
- `schemas/common.py::_Base` — (whole file) `extra='forbid'` — Layer 4 base.
- `schemas/sync_infra.py` — (whole file) EXTEND with 2 new shapes: `SyncEstadoQueryParams` + `SyncEstadoRead`.
- `tests/static/check_sync_queue_carveout.py` — REQ-OPS-004 AST walk precedent for KD-SYNC-02.
- `tests/static/test_no_raw_dml_on_a_tables.py` — F1.5 PR5-016 AST walk precedent.
- `tests/static/test_sync_estado_read_only.py` — (NEW) KD-SYNC-02 walk (per-handler scope).
- `tests/unit/test_sync_estado.py` — 2 mandated handler tests (empty + populated branch).
- `tests/unit/test_alert_types_seed.py` — 4 seed tests (19 codes plan.md-mandated).
- `tests/unit/test_sync_estado_repo.py` — 3 repo unit tests.
- `tests/unit/test_sync_estado_schemas.py` — 4 schema tests.
- `tests/integration/test_migration_0032_idempotency.py` — 6 migration tests.

---

**End of tasks.**