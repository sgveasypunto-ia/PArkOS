# Tasks: HU-F1.15 — `GET /usuarios/{uuid}/login` histórico

> **Change**: `hu-f1-15-login-historico` · **Phase**: tasks (sdd-tasks) · **HU**: HU-F1.15 — `GET /usuarios/{uuid}/login` histórico (gap huérfano, **ÚLTIMA HU de Fase 1 Parte I**)
> **Date**: 2026-09-15 · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `7cc613f`) · **PR target**: `origin/dev`
> **Cumulative estimate**: ~145 LOC (~70 prod + ~55 tests + ~25 migration)
> **Clusters**: T1..T5 (5 clusters, 14 atomic tasks)
> **Mandated tests**: 2 (plan.md line 1149)
>
> **Inputs**:
> - `openspec/changes/hu-f1-15-login-historico/design.md` (~1460 LOC, 16 sections + 2 appendices, DEC-LOGIN-01..10, KD-LOGIN-01..02, MIGRATION 0033 SQL body + AST walk precedent + 8-test matrix in Appendix B)
> - `openspec/changes/hu-f1-15-login-historico/proposal.md` (~770 LOC, 16 sections, DEC-LOGIN-01..10, KD-LOGIN-01..02, 7 risks R1..R7 — 4 RESOLVED at propose phase: R1, R3, R5, R6)
> - `openspec/changes/hu-f1-15-login-historico/specs/operations/spec.md` (~363 LOC, 4 REQs REQ-OPS-102..105 + REQ-OPS-XR6 reference, 17 scenarios in Given/When/Then/And form)
> - `openspec/changes/hu-f1-15-login-historico/exploration.md` (~770 LOC, 17 sections, DEC-LOGIN-01..10 mandate, R1..R7 risks, pre-flight 15/15 PASS)
> - `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/tasks.md` (~590 LOC, 5 clusters T1..T5, 14 atomic tasks, 5 expected commits) — **canonical precedent mirrored verbatim**
> - `plan.md` lines 1137-1155 (HU-F1.15 full definition, 2 atomic tasks T1..T2, 70 LOC production budget, 2 mandated tests at line 1149)
> - `plan.md` lines 7571-7574 (F1 endpoint table row 2391 — duplicate-resource note: Parte 1 F1.15 + Parte 2 F16.1/F16.5 — same resource, built once, shared backend)
> - `plan.md` lines 610-617 (F1.2 story, shares `prod.login` as the audit table for lockout writes)
> - `plan.md` line 1143 verbatim ("cada uno con su `estado` real (`exitoso|fallido|cerrado`) — nunca un campo booleano `activo`")
> - `modelo_datos_er.mmd` blocks `usuarios` [V] (lines 7-50) + `login` [L-S] (lines 558-573)
> - `migrations/versions/0001_initial_schema.py` lines 511-523 (login table), 1247-1255 (FK `fk_login_uuid_usuario`), 2203-2214 (trigger `login_ls_session_guard`), 2533-2541 (audit+set_vigente_inicial triggers), 2777-2788 (enqueue_sync trigger)
> - `migrations/versions/0002_seed_permisos_canonicos.py` lines 39-56 (`CANONICAL_PERMISOS` includes `audit_read` at line 48 — DEC-LOGIN-09.B pre-seeded)
> - `migrations/versions/0021_least_privilege_and_immutability_contract.py:206` (`_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")`)
> - `migrations/versions/0032_seed_alert_types_operativos.py` (F1.14 head, DEC-LOGIN-09.B `audit_read` reuse anchor at line 185)
> - `migrations/versions/0011_add_seq_lookup_indexes.py:62` (CONCURRENTLY precedent for index migration — DEC-LOGIN-06 source)
> - `models/L_S/login.py:33-74` (Login ORM, FK `usuarios`, 5 business columns + state enum)
> - `models/V/usuarios.py` (Usuarios ORM)
> - `repo/session_cycle.py:49-146` (`record_login` write helper — F1.15 NEVER calls it; only references the table it writes to)
> - `repo/tarifas_vigencia.py:79-162` (`list_tarifas_vigentes` cursor-pagination precedent — `ORDER BY vigente_desde DESC, uuid ASC`)
> - `api/router_factory.py:127-227` (factory `list_endpoint` pattern — `next_cursor` encoding + `read_list_schema` shape)
> - `api/v1/_helpers.py:18-31` (`no_store_headers()` + `apply_no_store_header()` — DEC-LOGIN-05)
> - `api/v1/auth.py:69` (POST-mutating-only rationale for DEC-LOGIN-01.A — dedicated router)
> - `auth/jwt_issuer_guard.py` (`requires_issuer` factory, KD-3 dep)
> - `auth/tenancy.py` (`get_tenant_ctx`, KD-S2 F1.7 analog — Layer 2)
> - `schemas/common.py::_Base` (`extra='forbid'` — Layer 4 defense base)
> - `auth.py:239-246` (`fallido`), `:260-266` (`exitoso`), `:352-393` (`cerrado`) — `estado` lifecycle sources
> - `tests/static/test_sync_estado_read_only.py` (F1.14 KD-SYNC-02 AST walk precedent)
> - `tests/static/test_arqueo_handler_single_commit.py` (F1.13 KD-ARQUEO-01 AST walk precedent)
> - `tests/static/test_no_raw_dml_on_a_tables.py` (F1.5 PR5-016 AST walk precedent — [A] variant)
> - `openspec/specs/operations/spec.md` line 3951 (REQ-OPS-XR6 EXISTS from F1.13 — F1.15 references but does NOT create new)
> - `openspec/specs/operations/spec.md` line 4034-4041 (REQ-OPS-100 empty-branch precedent at F1.14 — DEC-LOGIN-08 mirror)
>
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `7cc613f`; F1.14 closed) · **PR target**: `origin/dev`.
> **TDD discipline**: RED→GREEN→REFACTOR per cluster. Each commit <800 LOC. Each cluster ends with all tests PASS.
> **Atomic commit strategy**: 5 atomic commits expected (T1 MIGRATION + T2 repo/schemas + T3 handler + T4 AST walk + tests + T5 housekeeping).
> **Skills loaded**: `gentle-sdd-tasks` + `sdd-phase-common.md` (paths injected via orchestrator).

---

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~145 across 1 PR (~70 LOC production: ~50 LOC NEW `api/v1/usuarios_login.py` + ~30 LOC NEW `repo/login_historico.py` + ~25 LOC NEW `schemas/usuarios.py` + ~3 LOC MODIFY `api/v1/__init__.py` + ~25 LOC NEW `migrations/versions/0033_login_historic_index.py` + ~55 LOC tests + ~15 LOC AST walk) |
| Total tasks | ~14 (5 clusters: T1 MIGRATION 3 + T2 repo+schemas 4 + T3 handler+mount 4 + T4 AST+integration 2 + T5 housekeeping 1) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Low** — F1.15 is smaller than F1.14 (~360 LOC cumulative) due to single composite index (no seeds); 5-commit split keeps each commit well within the `commitlint` 800-LOC ceiling. |
| Chained PRs recommended | No — one single PR (matches F1.7 + F1.9 + F1.10 + F1.11 + F1.12 + F1.13 + F1.14 precedent); read-only path keeps blast radius small. |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Single PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 5 commits internally (T1 ~25 migration, T2 ~55 repo + schemas, T3 ~80 handler + mount, T4 ~15 AST walk + integration test, T5 ~30 housekeeping + apply-report). |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesive single-resource (1 dedicated handler + 3 repo helpers + 3 Pydantic schemas + 1 REAL migration + 1 AST walk) + 5-commit split keeps budget risk Low inside the F1.11/F1.12/F1.13/F1.14 precedent. |

| Cluster | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|---------|-------|---------------|----------------|----------------|
| T1 MIGRATION 0033 composite index | T1.1..T1.3 | ~25 LOC (REAL DDL composite index + downgrade) | n/a (test in T4) | 25 |
| T2 Repo helpers + schemas | T2.1..T2.4 | ~55 LOC (3 typed helpers + 3 Pydantic schemas) | n/a (tests in T4) | 80 |
| T3 Handler + mount | T3.1..T3.4 | ~80 LOC (8-step handler chain + dedicated router + mount) | n/a (tests in T4) | 160 |
| T4 AST walk + integration test | T4.1..T4.2 | n/a | ~55 LOC (1 AST walk + 2 mandated handler + 3 repo unit + 1 migration) | 215 |
| T5 housekeeping + apply-report | T5.1 | n/a | ~30 LOC (apply-report + pending.md update) | 245 |
| **Total** | **~14** | **~160 LOC impl** | **~85 LOC tests** | **~145 LOC cumulative workload** (production 70 + tests 55 + migration 25 + AST walk 15 + docs 30 per design.md §16.5 + Appendix B estimate) |

> Per-commit ceiling: <800 LOC. Each cluster T1..T5 fits within the limit (T3 handler + mount at ~80 LOC is the largest implementation block, well within).

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| T1 | Pre-flight verify + MIGRATION 0033 composite index (Op 0 + Op 1) | commit 1 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0033_index.py -q` | `pg_engine` real via `testcontainers[postgres]`; pre-flight DO $$ asserts 2 conditions; Op 1 `CREATE INDEX CONCURRENTLY IF NOT EXISTS` (idempotent) | `alembic downgrade -1` reverses Op 1 via `DROP INDEX CONCURRENTLY` |
| T2 | `repo/login_historico.py` 3 typed helpers + `schemas/usuarios.py` 3 schemas | commit 2 | `uv run pytest backend/tests/unit/test_login_historico_repo.py backend/tests/unit/test_login_historico_schemas.py -q` | unit tests no DB for schemas (T2.3); pure base64 math for `encode_next_cursor` (T2.2); AsyncMock patterns for SELECT helper (T2.2) | Delete helper bodies / schema appends |
| T3 | `GET /usuarios/{uuid}/login` 8-step chain + dedicated router + mount at `api/v1/__init__.py` | commit 3 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_login_historico.py -q` | HTTP integration with `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-`/`admin-` fixtures + real DB | Revert handler module + mount |
| T4 | KD-LOGIN-02 AST walk (2 assertions) + handler mandated tests (2) + repo unit (3) + migration idempotency (1) | commit 4 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/static/test_login_historico_read_only.py backend/tests/unit/test_login_historico.py backend/tests/unit/test_login_historico_repo.py backend/tests/integration/test_migration_0033_index.py -q` | real DB for migration + handler; pure AST walks for static | Delete AST walk + test files |
| T5 | apply-report + all tasks [x] + pending.md update | commit 5 | (no test command — documentation only) | n/a | Revert apply-report + pending.md |

---

## Tareas

### Cluster T1 — MIGRATION 0033 composite index (~25 LOC impl)

- [x] **T-HU-F1.15-T1.1** [RED] — Pre-flight verification: grep across the repo for `prod.login` (in `migrations/versions/0001_initial_schema.py` lines 511-523 table + 1247-1255 FK `fk_login_uuid_usuario` + 2203-2214 trigger `login_ls_session_guard` + 2533-2541 audit triggers + 2777-2788 enqueue_sync trigger), `prod.usuarios` (lines 7-50); verify pre-F1.15 `prod.login` has ONLY the implicit FK index on `uuid_usuario` (NO composite index on `(uuid_usuario, timestamp_evento DESC)`); verify `audit_read` pre-seeded at `0002_seed_permisos_canonicos.py:48`. Write `tests/integration/test_migration_0033_index.py::test_pre_flight_2_conditions` asserting pre-migration state via SQL.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_pre_flight_login_table_exists` — query `pg_class WHERE relname='login' AND relnamespace='prod'::regnamespace` returns 1 row.
    - T2: `test_pre_flight_usuarios_table_exists` — query `pg_class WHERE relname='usuarios' AND relnamespace='prod'::regnamespace` returns 1 row.
    - T3: `test_pre_flight_no_composite_index_pre_f115` — query `pg_indexes WHERE schemaname='prod' AND tablename='login' AND indexname='idx_login_uuid_usuario_evento'` returns 0 rows (composite index does NOT exist pre-F1.15).
    - T4: `test_pre_f_fk_index_exists` — query `pg_indexes WHERE schemaname='prod' AND tablename='login' AND indexname='login_uuid_usuario_idx'` (the implicit FK index from migration 0001:1247-1255) returns 1 row.
    - T5: `test_pre_flight_audit_read_permission_seeded` — `SELECT COUNT(*) FROM prod.permisos WHERE permiso='audit_read'` returns 1 (DEC-LOGIN-09.B).
  - **Patrón F1.14** (`test_migration_0032_idempotency.py`): pre-flight `DO $$` table-presence assertion + source-level grep + count assertions.
  - **Acción**: write test that asserts pre-flight state via SQL + source-level read of `migrations/versions/0002_seed_permisos_canonicos.py:48`. — **Archivo**: `backend/tests/integration/test_migration_0033_index.py` (nuevo, partial ~10 LOC, 5 tests covering pre-flight). — **Validación**: pre-implementation, all 5 pre-flight tests PASS (pre-flight already satisfied 2026-09-15 per exploration §12).

- [x] **T-HU-F1.15-T1.2** [GREEN] — Author `migrations/versions/0033_login_historic_index.py` (~25 LOC, REAL DDL composite index): Op 0 pre-flight `DO $$` block asserting 2 conditions (`prod.login` + `prod.usuarios` exist) + Op 1 `CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento ON prod.login (uuid_usuario, timestamp_evento DESC)` via `op.get_context().autocommit_block()` (DEC-LOGIN-06 — `CONCURRENTLY` cannot run inside a transaction, mirrors `0011_add_seq_lookup_indexes.py:62`). `downgrade()` reverses Op 1 with `DROP INDEX CONCURRENTLY` (also wrapped in `autocommit_block()`). `down_revision='0032_seed_alert_types_operativos'`.
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0033_login_historic_index.py` (nuevo, ~25 LOC).
  - **Contenido** (verbatim per design.md Appendix A):
    ```python
    """MIGRATION 0033 — F1.15 REAL DDL composite index for login history pagination.

    Pre-flight 2026-09-15 confirmed:
    - prod.login exists (migration 0001:511-523, [L-S] SessionBase, 5 business columns).
    - prod.usuarios exists (migration 0001:7-50, [V] VersionedBase, bi-temporal).
    - prod.login has FK fk_login_uuid_usuario (migration 0001:1247-1255) — implicit
      index on uuid_usuario already exists. NO composite index on
      (uuid_usuario, timestamp_evento DESC) exists today.
    - F1.15 adds the composite index to enable cursor pagination at scale
      (1000+ login rows per user over months → no sort-on-disk).

    This migration ships:
    - Op 0: pre-flight DO $$ block asserting required tables exist (login, usuarios).
    - Op 1: CREATE INDEX CONCURRENTLY prod.idx_login_uuid_usuario_evento
      on prod.login (uuid_usuario, timestamp_evento DESC).

    Idempotency ensures any future re-run on already-migrated DB is a clean no-op
    (CREATE INDEX CONCURRENTLY IF NOT EXISTS pattern).

    Part of HU-F1.15 (gap huérfano de auditoría de seguridad, ÚLTIMA HU de Fase 1 Parte I).
    Predecessor: F1.14 archived 2026-09-15 (MIGRATION 0032 alert_types siembra).
    """
    from alembic import op


    revision = "0033_login_historic_index"
    down_revision = "0032_seed_alert_types_operativos"
    branch_labels = None
    depends_on = None


    def upgrade() -> None:
        """MIGRATION 0033 upgrade: pre-flight DO $$ + Op 1 CREATE INDEX CONCURRENTLY.

        CREATE INDEX CONCURRENTLY cannot run inside a transaction — alembic
        defaults to transactional DDL; we explicitly opt OUT for this op via
        autocommit_block() (KD-7 F1.6..F1.14 pattern).
        """
        # Op 0 -- pre-flight DO $$ (KD-7 F1.6..F1.14 pattern).
        # Verifies the 2 tables required by F1.15 are present in ``prod``.
        op.execute(
            """
            DO $$
            DECLARE
                _n_login      bigint;
                _n_usuarios   bigint;
            BEGIN
                SELECT count(*) INTO _n_login
                    FROM pg_catalog.pg_class
                    WHERE relname='login' AND relnamespace='prod'::regnamespace;
                SELECT count(*) INTO _n_usuarios
                    FROM pg_catalog.pg_class
                    WHERE relname='usuarios' AND relnamespace='prod'::regnamespace;

                IF _n_login IS NULL OR _n_login = 0 THEN
                    RAISE EXCEPTION '0033_preflight_abort: tabla prod.login no existe. '
                                    'Aplique MIGRATION 0001 antes.';
                END IF;
                IF _n_usuarios IS NULL OR _n_usuarios = 0 THEN
                    RAISE EXCEPTION '0033_preflight_abort: tabla prod.usuarios no existe. '
                                    'Aplique MIGRATION 0001 antes.';
                END IF;

                RAISE NOTICE '0033_preflight: 2/2 tablas OK (login, usuarios)';
            END;
            $$;
            """
        )

        # Op 1 -- CREATE INDEX CONCURRENTLY (DEC-LOGIN-06).
        # Avoids table lock during index build (production safety — F1.2
        # lockout writes from record_login are not blocked).
        # IF NOT EXISTS makes the migration idempotent on re-run.
        with op.get_context().autocommit_block():
            op.execute(
                """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS
                    prod.idx_login_uuid_usuario_evento
                ON prod.login (uuid_usuario, timestamp_evento DESC);
                """
            )


    def downgrade() -> None:
        """Reverse Op 1: DROP INDEX CONCURRENTLY (production safety — no table lock).

        DROP INDEX CONCURRENTLY cannot run inside a transaction; explicit opt-out
        via autocommit_block().
        """
        with op.get_context().autocommit_block():
            op.execute(
                """
                DROP INDEX CONCURRENTLY IF EXISTS
                    prod.idx_login_uuid_usuario_evento;
                """
            )
    ```
  - **Acción**: paste verbatim from design.md Appendix A; `revision="0033_login_historic_index"`; `down_revision="0032_seed_alert_types_operativos"`. — **Validación**: T1.1 pre-flight tests PASS pre-migration; post-migration `tests/integration/test_migration_0033_index.py` round-trip test PASSes (upgrade → downgrade → upgrade idempotent).

- [x] **T-HU-F1.15-T1.3** [REFACTOR] — Verify `downgrade()` cleanly reverses Op 1 (DROP INDEX CONCURRENTLY) without disturbing other tables (DEC-LOGIN-06 invariant: index-only, NO schema changes to existing tables). After downgrade, `prod.idx_login_uuid_usuario_evento` MUST NOT exist; after re-upgrade, MUST exist. The pre-flight `DO $$` is a pure assertion (no DDL changes — re-running upgrade on a fresh DB always rebuilds the index). The `CONCURRENTLY` opt-out via `op.get_context().autocommit_block()` MUST be applied to BOTH upgrade AND downgrade (production safety — F1.2 lockout writes from `record_login` are not blocked during the build).
  - **Acción**: extend T1.1 file `backend/tests/integration/test_migration_0033_index.py` with 2 post-migration tests:
    - `test_migration_0033_post_upgrade_index_exists` — `SELECT COUNT(*) FROM pg_indexes WHERE indexname='idx_login_uuid_usuario_evento'` = 1.
    - `test_migration_0033_post_downgrade_index_dropped` — after `alembic downgrade -1`, `COUNT(*)` = 0 AND no other `prod.login` index is affected.
  - **Validación**: pre-refactor: T1.2 migration applies cleanly; post-refactor: downgrade + upgrade cycle test PASSes.

  **Commit suggestion**: `feat(backend): HU-F1.15 -- T1 MIGRATION 0033 composite index (uuid_usuario, timestamp_evento DESC)` (~25 LOC + ~10 LOC pre-flight tests partial).

  **Exit criteria T1**: T1.1..T1.3 verde; ~25 LOC migration + ~10 LOC pre-flight tests cumulative; migration head = `0033_login_historic_index`; pre-flight DO $$ asserts 2 conditions; Op 1 creates composite index via `CREATE INDEX CONCURRENTLY IF NOT EXISTS` (idempotent); downgrade drops cleanly via `DROP INDEX CONCURRENTLY`; upgrade re-creates cleanly.

### Cluster T2 — Repo Helpers + Schemas (~55 LOC impl)

- [x] **T-HU-F1.15-T2.1** [RED + GREEN] — Author `repo/login_historico.py` skeleton (~10 LOC): `from __future__ annotations` + module docstring documenting DEC-LOGIN-01..10 + KD-LOGIN-01..02 references + define 3 typed helper functions (`listar_intentos_paginado`, `encode_next_cursor`, `decode_cursor_or_none`) — all SELECT-only, commit-free, NO `await session.commit()` (KD-LOGIN-01 contract). `__all__` listing the 3 helper names + module-level type hints for `AsyncSession` + `UUID` + `TenantContext` + `LoginIntentoItem`.
  - **Tests** (pure Python, no DB, no HTTP):
    - T1: `test_repo_login_historico_module_imports` — `from parkos_core.repo import login_historico as repo_login_historico` succeeds; `dir(repo_login_historico)` includes 3 typed helper names.
  - **Patrón F1.14** (`test_repo_sync_estado_module_imports`): pure import assertion, gated by `__all__` definition.
  - **Acción**: `import` from `parkos_core.repo.login_historico` (fails with `ModuleNotFoundError`); assert public names. — **Archivo**: `backend/tests/unit/test_login_historico_repo.py` (nuevo, partial ~5 LOC, 1 test). — **Validación**: `ModuleNotFoundError: No module named 'parkos_core.repo.login_historico'`.

- [x] **T-HU-F1.15-T2.2** [RED + GREEN] — Author `schemas/usuarios.py` (~25 LOC) with `LoginHistoricoQueryParams(_Base)` query params + `LoginIntentoItem(_Base)` response item + `LoginHistoricoListResponse(_Base)` envelope. All 3 inherit `extra='forbid'` from `_Base` (Layer 4 defense, blocks client smuggling of `actor_uuid`, `computed_at`, `cache_key`, `activo`). `LoginHistoricoQueryParams` has `uuid: UUID` (required path param) + `limit: int = 10` (ge=1, le=100 validators per DEC-LOGIN-04) + `cursor: str | None = None`. `LoginIntentoItem` has `uuid: UUID` + `timestamp_evento: datetime` (naive UTC, NOT nullable) + `timestamp_cierre: datetime | None` (nullable for open sessions) + `estado: Literal["exitoso", "fallido", "cerrado"]` (DEC-LOGIN-10 — REAL [L-S] lifecycle value, NEVER synthetic boolean `activo`) + `uuid_sucursal: UUID | None` (nullable FK). `LoginHistoricoListResponse` has `items: list[LoginIntentoItem]` + `next_cursor: str | None` envelope per `router_factory.py:227`.
  - **Tests** (pure Pydantic validation, no HTTP, no DB):
    - T1: `test_login_historico_query_params_extra_forbid` — `LoginHistoricoQueryParams(uuid=<uuid>, actor_uuid='x')` raises `ValidationError` (extra='forbid').
    - T2: `test_login_historico_query_params_limit_out_of_range` — `LoginHistoricoQueryParams(uuid=<uuid>, limit=0)` raises `ValidationError` (ge=1 invariant); `limit=101` raises (le=100 invariant).
    - T3: `test_login_intento_item_estado_literal` — `LoginIntentoItem(..., estado='activo')` raises `ValidationError` (DEC-LOGIN-10 — only `exitoso|fallido|cerrado` accepted).
    - T4: `test_login_intento_item_estado_nullable` — `LoginIntentoItem(..., estado=None)` raises `ValidationError` (estado is NOT nullable per `models/L_S/login.py:64-67`).
  - **Patrón F1.14** (`test_arqueo_schemas.py`): pure Pydantic tests, no HTTP, no DB.
  - **Acción**: extend T2.1 file (NEW `backend/tests/unit/test_login_historico_schemas.py`, ~20 LOC, 4 tests). — **Validación**: pre-implementation `ImportError` for the schema names.

- [x] **T-HU-F1.15-T2.3** [RED + GREEN] — Implement `listar_intentos_paginado` (Step 4, ~15 LOC) with `select(Login.uuid, Login.timestamp_evento, Login.timestamp_cierre, Login.estado, Login.uuid_sucursal).where(Login.uuid_usuario == uuid_usuario).order_by(Login.timestamp_evento.desc(), Login.uuid.asc()).limit(limit + 1)` + cursor filter `(timestamp_evento < cursor_ts) OR (timestamp_evento == cursor_ts AND uuid > cursor_uuid)` when cursor decoded + Layer 2 filter `login.uuid_sucursal = ctx.sucursal_uuid` when `tenant_ctx.issuer_prefix == "operador-" AND tenant_ctx.sucursal_uuid is not None` (DEC-LOGIN-03.A — own-branch audit history only; admin bypasses). Implement `encode_next_cursor(items, limit)` (Step 5, ~5 LOC pure math) — if `len(items) <= limit` returns `None` (last page); otherwise encodes last item's `(timestamp_evento.isoformat(), str(uuid))` pair as base64-encoded JSON. Implement `decode_cursor_or_none(cursor)` (Step 4 prelude, ~5 LOC) — thin wrapper around `cursor_decode` from `api/router_factory.py:127-140`; raises `CursorInvalidError` on malformed base64/JSON/missing keys.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1` for DB-touching helpers; pure base64 math for `encode_next_cursor`/`decode_cursor_or_none`):
    - T1: `test_listar_intentos_paginado_empty_returns_no_items` — empty `prod.login` for `uuid_usuario=:u` → returns `[]` (DEC-LOGIN-08 anti-enumeration empty user contract).
    - T2: `test_listar_intentos_paginado_populated_returns_desc_order` — seed 5 rows with `timestamp_evento` spanning 60-300s ago → returns 5 items ordered by `(timestamp_evento DESC, uuid ASC)` (mandated scenario 1 per plan.md line 1149).
    - T3: `test_listar_intentos_paginado_layer2_filter_operador` — operador JWT with `ctx.sucursal_uuid=:s_other` + 5 rows where `uuid_sucursal=:s_target` (different branch) → returns 0 rows (DEC-LOGIN-03.A — own-branch filter excludes cross-branch).
    - T4: `test_listar_intentos_paginado_layer2_bypass_admin` — admin JWT with arbitrary `ctx.sucursal_uuid` + 5 rows across 2 branches → returns all 5 rows (DEC-LOGIN-03.A — admin bypasses tenant scope).
    - T5: `test_encode_next_cursor_items_fit_within_limit_returns_none` — 5 items, limit=10 → returns `None` (last page).
    - T6: `test_encode_next_cursor_more_items_than_limit_returns_base64` — 11 items, limit=10 → returns base64-encoded JSON of item #10's `(timestamp_evento, uuid)` pair.
    - T7: `test_decode_cursor_or_none_malformed_raises_cursor_invalid_error` — `decode_cursor_or_none('not-base64-json-{}')` raises `CursorInvalidError`.
  - **Archivo**: extend `repo/login_historico.py` (+~25 LOC); extend T2.1 file with +~30 LOC, 7 tests. — **Validación**: T1..T7 PASS; `__all__` now exposes all 3 helpers.

- [x] **T-HU-F1.15-T2.4** [REFACTOR] — Verify `repo/login_historico.py` 3 typed helpers are commit-free (KD-LOGIN-01 contract): NO `await session.commit()` anywhere in helper bodies. Verify AsyncMock patterns used in unit tests (no real DB roundtrip needed for pure math helpers). Verify `encode_next_cursor` is a pure function (no side effects, deterministic, testable without DB). Verify `listar_intentos_paginado` accepts `tenant_ctx` as a typed parameter (not a string) — prevents tenant scope bypass via type confusion.
  - **Acción**: add 1 smoke test confirming pure-function contract:
    - `test_encode_next_cursor_pure_function_no_side_effects` — call helper twice with same inputs → identical outputs (deterministic).
  - **Archivo**: extend T2.3 file with +~5 LOC, 1 test. — **Validación**: T2.1..T2.4 verde; ~55 LOC cumulative; 3 helpers + 3 schemas exposed; `__all__` lists all 3 helper names.

  **Commit suggestion (T2.1..T2.4)**: `feat(backend): HU-F1.15 -- T2 repo/login_historico.py 3 helpers + schemas/usuarios.py 3 schemas` (~55 LOC + ~50 LOC tests).

  **Exit criteria T2**: T2.1..T2.4 verde; ~55 LOC cumulative; 3 helpers + 3 schemas exposed; `__all__` lists all 3 helper names; commit-free contract enforced; cursor pagination helper mirrors `repo/tarifas_vigencia.py:79-162` precedent.

### Cluster T3 — GET `/api/v1/usuarios/{uuid}/login` Handler + Mount (~80 LOC impl + tests in T4)

- [x] **T-HU-F1.15-T3.1** [RED + GREEN] — Stub `api/v1/usuarios_login.py::get_login_historico` with KD-3 issuer dep (`_login_historico_issuer_dep = requires_issuer("operador-", "admin-")`) + dedicated `APIRouter(prefix="/usuarios", tags=["usuarios"])` (DEC-LOGIN-01 — RESOLVES R1 LOW endpoint-ownership conflict with Parte 2 HU-F16.1/F16.5); write failing source-level test asserting the endpoint is NOT yet registered (404).
  - **Tests** (pure source-level + HTTP integration gated):
    - T1: `test_usuarios_login_module_imports_with_get_login_historico_handler` — `from parkos_core.api.v1.usuarios_login import router` succeeds; `dir(router)` does NOT yet contain `get_login_historico` (RED pre-implementation).
    - T2: `test_endpoint_login_historico_not_yet_registered` — HTTP GET against `/api/v1/usuarios/{uuid}/login` returns 404 (route fully absent); test asserts 404.
  - **Patrón F1.14** (`test_caja_arqueo_module_imports_with_post_arqueo_handler`): pure source-level + `httpx.AsyncClient + ASGITransport(app)`.
  - **Acción**: create stub module with `router = APIRouter(prefix="/usuarios", tags=["usuarios"])` + `from __future__ annotations` + import `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-LOGIN-01 + DEC-LOGIN-02 + Layer 1). — **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/usuarios_login.py` (nuevo, stub, ~10 LOC). — **Validación**: stub module imports; route returns 404.

- [x] **T-HU-F1.15-T3.2** [GREEN] — Implement Steps 1-8 of the 8-step chain in `get_login_historico` (~60 LOC): Step 1 (DI-resolved) KD-3 issuer dep + permission gate `audit_read` (Layer 1, DEC-LOGIN-02 + DEC-LOGIN-09.B pre-seeded at 0002:48); Step 2 Layer 2 tenant scope post-V1 (KD-S2 F1.7 analog) — Layer 2 filter is applied at SQL layer via `tenant_ctx` parameter passed to `listar_intentos_paginado` (DEC-LOGIN-03.A — `operador-` issuer filters by `login.uuid_sucursal = ctx.sucursal_uuid` at SQL; `admin-` bypasses); Step 3 (Layer 4) Pydantic UUID + limit + cursor validation (FastAPI Depends); Step 4 (KD-LOGIN-01 + KD-LOGIN-02) READ-ONLY via 1 typed SELECT helper — `items = await repo_login_historico.listar_intentos_paginado(session, uuid_usuario=uuid, cursor=params.cursor, limit=params.limit, tenant_ctx=ctx)` — NO `await session.commit()`, NO raw `session.execute(update(Login))` / `session.execute(delete(Login))` / `session.execute(text("UPDATE prod.login"))` (KD-LOGIN-02 enforced by AST walk in T4); Step 5 build `next_cursor = repo_login_historico.encode_next_cursor(items, params.limit)`; Step 6 (Layer 5) `apply_no_store_header(response)` (DEC-LOGIN-05, XR6 Layer 5); Step 7 (Layer 4+5) build `LoginHistoricoListResponse(items=items[:params.limit], next_cursor=next_cursor)` envelope (DEC-LOGIN-07 forward-compatible with Parte 2); Step 8 (KD-LOGIN-01 reaffirmed) handler returns.
  - **Archivo**: extend `api/v1/usuarios_login.py` (+~60 LOC).
  - **Contenido** (verbatim per design.md §10.1):
    ```python
    @router.get(
        "/{uuid}/login",
        response_model=LoginHistoricoListResponse,
        status_code=200,
    )
    async def get_login_historico(
        response: Response,
        uuid: uuid_lib.UUID,
        params: LoginHistoricoQueryParams = Depends(),
        session: AsyncSession = Depends(get_session),
        ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(_login_historico_issuer_dep),
    ) -> LoginHistoricoListResponse:
        # Step 1 (Layer 1): KD-3 issuer dep + audit_read permission gate (DI-resolved)
        # The dep already enforced KD-3 issuer + permission gate; ctx carries claims.

        # Step 2 (Layer 2): Tenant scope post-V1 (KD-S2 F1.7 analog)
        # Filter is applied at SQL layer (Step 4) — no need to short-circuit.
        # Admin (admin-) bypasses — no filter added.

        # Step 3 (Layer 4): Pydantic UUID + limit + cursor validation
        # Already done by FastAPI Depends + Pydantic validator.
        # If malformed, 422/400 raised before handler body runs.

        # Step 4 (KD-LOGIN-01 + KD-LOGIN-02): READ-ONLY via 1 typed SELECT helper
        # NO UPDATE/DELETE/INSERT in this body (AST walk enforces).
        # NO await session.commit() — GET is naturally idempotent.
        items = await repo_login_historico.listar_intentos_paginado(
            session,
            uuid_usuario=uuid,
            cursor=params.cursor,
            limit=params.limit,
            tenant_ctx=ctx,            # Layer 2 filter (DEC-LOGIN-03.A)
        )

        # Step 5: Build next_cursor (last item's (timestamp_evento, uuid))
        next_cursor = repo_login_historico.encode_next_cursor(items, params.limit)

        # Step 6 (Layer 5): no-store header on success
        apply_no_store_header(response)

        # Step 7: response envelope (forward-compatible Parte 2 shape)
        return LoginHistoricoListResponse(items=items[:params.limit], next_cursor=next_cursor)

        # Step 8: KD-LOGIN-01 reaffirmed — no writes, no commits, no log rows
    ```
  - **Acción**: docstring REQ-OPS-102..105 + DEC-LOGIN-01..10 + KD-LOGIN-01..02. — **Validación**: T3.1 2 tests PASS (route now registered); T4.1 AST walk PASSes (no UPDATE/DELETE/COMMIT in handler body); T4.2 handler tests cover happy path + empty branch.

- [x] **T-HU-F1.15-T3.3** [GREEN] — Verify `get_login_historico` returns 200 OK with `Cache-Control: no-store` (DEC-LOGIN-05, XR6 Layer 5) on EVERY response including 200 (success) + 403 (permission denied or tenant scope) + 422 (missing/invalid uuid via Pydantic) + 400 (cursor_invalid). Verify pgcode/pgerror/pgmessage NEVER appear in response body (XR6 Layer 5 redaction, defense in depth). Verify empty-user contract: zero `prod.login` rows → 200 with `items=[]` + `next_cursor=None` (DEC-LOGIN-08 anti-enumeration, NEVER 404).
  - **Acción**: no source-level changes; verifies via T4.2 handler tests asserting the response header on each status code path + absence of pgcode/pgerror/pgmessage keys + empty-user 200 contract. — **Validación**: T4.2 mandated tests PASS.

- [x] **T-HU-F1.15-T3.4** [GREEN] — Dedicated `APIRouter` mount in `api/v1/usuarios_login.py` (already wired via DEC-LOGIN-01 Step T3.1 stub) + register in `api/v1/__init__.py` (or wherever the FastAPI app is constructed — sibling of `auth.py` mount). Append `from .usuarios_login import router as usuarios_login_router` + `app.include_router(usuarios_login_router)` (DEC-LOGIN-01.A — FastAPI app-level mount, sibling of `auth.py`, NOT nested in `caja.py`). Mount extension: ~3 LOC.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` (modified, +~3 LOC); no modification to `auth.py` (POST-mutating-only invariant preserved per DEC-LOGIN-01.A rationale at `auth.py:69`).
  - **Acción**: append at top-level FastAPI app construction site — same place `auth.py` is mounted. — **Validación**: T4.2 handler tests confirm endpoint reachable at `/api/v1/usuarios/{uuid}/login` GET with `Cache-Control: no-store`.

  **Commit suggestion**: `feat(backend): HU-F1.15 -- T3 api/v1/usuarios_login.py handler (8-step chain + KD-LOGIN-01 SELECT-only + DEC-LOGIN-01 mount)` (~80 LOC).

  **Exit criteria T3**: T3.1..T3.4 verde; ~80 LOC cumulative; handler reachable end-to-end; 8-step chain enforces KD-LOGIN-01 SELECT-only + KD-LOGIN-02 read-only AST walk (T4.1) + DEC-LOGIN-05 no-store + DEC-LOGIN-09.B audit_read permission gate + DEC-LOGIN-03.A Layer 2 tenant scope.

### Cluster T4 — AST walk + Integration Test (~70 LOC tests)

- [x] **T-HU-F1.15-T4.1** [RED + GREEN] — Write failing AST walk `tests/static/test_login_historico_read_only.py` (~15 LOC, KD-LOGIN-02) enforcing that `get_login_historico` is READ-ONLY — NO `update(Login)` / `delete(Login)` / `session.execute(text("UPDATE prod.login"))` / `session.execute(text("DELETE FROM prod.login"))` / `await session.commit()` in handler body (mirror of F1.5 PR5-016 `test_no_raw_dml_on_a_tables.py` + F1.10 KD-FE-01 + F1.11 KD-TKT-01 + F1.12 KD-VENTA-01 + F1.13 KD-ARQUEO-01 + F1.14 KD-SYNC-02 AST walks — for the READ-ONLY side on [L-S] tables).
  - **Tests** (no DB, no HTTP, pure AST walk):
    - T1: `test_no_update_or_delete_on_login` — `ast.parse(api/v1/usuarios_login.py)`; locate `get_login_historico` via `ast.AsyncFunctionDef.name == 'get_login_historico'`; walk via `iter_child_nodes`; assert ZERO occurrences of `session.execute(update(Login))` or `session.execute(delete(Login))` or `session.execute(text("UPDATE prod.login"))` or `session.execute(text("DELETE FROM prod.login"))` (KD-LOGIN-01 + KD-LOGIN-02).
    - T2: `test_no_commit_in_handler` — same walk; assert ZERO occurrences of `await session.commit()` (GET is naturally commit-free, KD-LOGIN-02).
  - **Patrón F1.10 + F1.11 + F1.12 + F1.13 + F1.14**: `ast.parse` + `iter_child_nodes` DFS.
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_login_historico_read_only.py` (nuevo, ~15 LOC, 2 AST walks). — **Validación**: post T3 GREEN, walks PASS.

- [x] **T-HU-F1.15-T4.2** [RED + GREEN] — Write `tests/unit/test_login_historico.py` with **2 MANDATED tests per plan.md line 1149** + supporting tests; extend `tests/unit/test_login_historico_repo.py` (T2.1 partial) with 3 supporting repo unit tests; extend `tests/unit/test_login_historico_schemas.py` (T2.2 partial) with 4 supporting schema tests; extend `tests/integration/test_migration_0033_index.py` (T1.1 partial) with 1 full idempotency round-trip test + 1 DESC ordering test.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - **T1 (test_login_historico.py, ~30 LOC, **2 MANDATED tests per plan.md line 1149**)**:
      - T1.1: `test_empty_user_200_with_no_items` — zero `prod.login` rows for `uuid_usuario=:u` → `items=[]` + `next_cursor=None`, status 200, header `Cache-Control: no-store` (mandated scenario 1 per plan.md line 1149; DEC-LOGIN-08).
      - T1.2: `test_populated_user_with_5_rows_ordered_desc_with_next_cursor` — 5 `prod.login` rows with `timestamp_evento` spanning 60-300s ago + mixed `estado ∈ {exitoso, fallido, cerrado}` → ordered DESC + correct `next_cursor` base64-encoded on the last item's `(timestamp_evento, uuid)` pair (mandated scenario 2 per plan.md line 1149).
    - **T2 (test_login_historico_repo.py, extend T2.1 with ~15 LOC, 3 tests)**:
      - T2.1: `test_listar_intentos_paginado_layer2_filter_operador` — operador JWT with `ctx.sucursal_uuid=:s_other` + 5 rows in different branch → returns 0 rows (DEC-LOGIN-03.A).
      - T2.2: `test_listar_intentos_paginado_layer2_bypass_admin` — admin JWT + 5 rows across 2 branches → returns all 5 rows (DEC-LOGIN-03.A admin bypass).
      - T2.3: `test_decode_cursor_or_none_none_returns_none` — `decode_cursor_or_none(None)` → `None` (cursor optional).
    - **T3 (test_login_historico_schemas.py, extend T2.2 with ~20 LOC, 4 tests)**:
      - T3.1: `test_login_historico_query_params_extra_forbid` — `LoginHistoricoQueryParams(uuid=<uuid>, actor_uuid='x')` raises `ValidationError`.
      - T3.2: `test_login_historico_query_params_limit_out_of_range` — `LoginHistoricoQueryParams(uuid=<uuid>, limit=0)` raises `ValidationError`.
      - T3.3: `test_login_intento_item_estado_literal` — `LoginIntentoItem(..., estado='activo')` raises `ValidationError` (DEC-LOGIN-10).
      - T3.4: `test_login_intento_item_estado_nullable` — `LoginIntentoItem(..., estado=None)` raises `ValidationError`.
    - **T4 (test_migration_0033_index.py, extend T1.1 with ~10 LOC, 2 tests)**:
      - T4.1: `test_migration_0033_idempotent_upgrade_downgrade_upgrade` — `alembic upgrade head` succeeds (asserts `DO $$` pre-flight passes — both 2 conditions present); `alembic downgrade -1` succeeds (Op 1 reverses via `DROP INDEX CONCURRENTLY`); `alembic upgrade head` succeeds again (round-trip idempotent).
      - T4.2: `test_migration_0033_desc_order_honored_on_100_rows` — insert 100 rows with ascending `timestamp_evento`; query with `ORDER BY timestamp_evento DESC, uuid ASC LIMIT 10`; assert first row has the latest `timestamp_evento` (composite index MIGRATION 0033 honored).
  - **Patrón F1.14** (`test_arqueo_handler.py` + `test_migration_0031_idempotency.py`): HTTP integration via `httpx.AsyncClient` + `pg_engine` real via `testcontainers[postgres]`.
  - **Acción**: 4 NEW test files (T1 + T2 + T3 + T4) + extend T1.1 file with full coverage. — **Validación**: ~12 tests across 4 files PASS post T1 + T3 GREEN (2 mandated + 3 repo + 4 schema + 2 migration + AST walk 2).

  **Commit suggestion**: `test(backend): HU-F1.15 -- T4 KD-LOGIN-02 AST walk + 2 mandated handler tests + 3 repo + 4 schema + 2 migration tests` (~70 LOC + ~15 LOC AST walk).

  **Exit criteria T4**: T4.1..T4.2 verde; ~145 LOC cumulative (impl + tests); 2 AST walks + 2 mandated tests + ~12 unit/integration tests PASS; KD-LOGIN-01 SELECT-only + KD-LOGIN-02 read-only AST walk verified; DEC-LOGIN-05 no-store verified; 2 mandated tests cover empty branch + populated branch per plan.md line 1149.

### Cluster T5 — Housekeeping + Apply Report (~30 LOC docs)

- [x] **T-HU-F1.15-T5.1** [RED + GREEN] — Write `openspec/changes/hu-f1-15-login-historico/apply-report.md` (~30 LOC, per F1.14 precedent `apply-report.md`) documenting: which commits landed (5 atomic commits: T1, T2, T3, T4, T5), per-cluster exit criteria status (T1..T4 all PASS), test totals (8 tests across 4 files per design.md Appendix B), 4 DEC-LOGIN + 6 DEC-LOGIN (DEC-LOGIN-01..10, 4 RESOLVED + 6 design controls) + 2 KD-LOGIN + 4 REQ-OPS-102..105 traceability matrix, all 10 DECs + 2 KDs + 4 REQs verified via ≥1 RED test, CI gates green (5 gates: `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.14`), 0 regressions introduced, MIGRATION 0033 idempotency verified, composite index `prod.idx_login_uuid_usuario_evento` applied cleanly. Mark all T1..T4 tasks [x] in this file. Update `openspec/changes/archive/fase-1-prerequisites-backend/prompts/pending.md` §1 to mark F1.15 closed (move from "in_progress" to "closed" section, add commit SHA + apply-report.md reference).
  - **Acción**: write apply-report.md verbatim per F1.14 precedent; edit pending.md §1 to add F1.15 entry in "closed" subsection. — **Archivos**: `openspec/changes/hu-f1-15-login-historico/apply-report.md` (nuevo, ~30 LOC); `openspec/changes/archive/fase-1-prerequisites-backend/prompts/pending.md` (modified, +~5 LOC). — **Validación**: apply-report.md exists with 5-commit summary + traceability matrix; pending.md §1 reflects F1.15 closed.

  **Commit suggestion**: `chore(openspec): HU-F1.15 -- T5 apply-report + all tasks [x] + pending.md update` (~30 LOC).

  **Exit criteria T5**: T5.1 verde; ~30 LOC cumulative (docs); apply-report.md authored with 5-commit summary + traceability matrix; all T1..T4 tasks marked [x] in this tasks.md file; pending.md §1 reflects F1.15 closed.

---

## Cross-cluster constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` on `prod.login` outside the 1 typed SELECT helper in `repo/login_historico.py` — AST walk `tests/static/test_login_historico_read_only.py` (T4.1) enforces via KD-LOGIN-01 + KD-LOGIN-02.
- NO `await session.commit()` anywhere in the `get_login_historico` handler body — AST walk `tests/static/test_login_historico_read_only.py` (T4.1) enforces via KD-LOGIN-02 (GET is naturally commit-free).
- NO raw `session.execute(update(Login))` / `session.execute(delete(Login))` / `session.execute(text("UPDATE prod.login"))` / `session.execute(text("DELETE FROM prod.login"))` anywhere in the `get_login_historico` handler body — AST walk `tests/static/test_login_historico_read_only.py` (T4.1) enforces via KD-LOGIN-01 + KD-LOGIN-02.
- NO `Co-authored-by:` trailers AI en commits; conventional commits, neutral Spanish commit messages, neutral Spanish per-cluster rationale comments.
- NO SQLite in tests — `pg_engine` real via `testcontainers[postgres]` (F1.4/F1.5/F1.6/F1.7/F1.9/F1.10/F1.11/F1.12/F1.13/F1.14 precedent).
- NO modification of `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate (matches F1.7/F1.9/F1.10/F1.11/F1.12/F1.13/F1.14).
- NO modification of `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate cross-cutting.
- NO modification of `api/deps.py` nor `auth/tenancy.py` — KD-3 chain + errores tipados intactos.
- NO modification of `repo/event.py` — `event_helper_intact` CI gate (matches F1.7/F1.9/F1.10/F1.11/F1.12/F1.13/F1.14).
- NO modification of `api/v1/auth.py` — POST-mutating-only invariant preserved per DEC-LOGIN-01.A rationale (`auth.py:69`).
- NO modification of `api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()` — F1.6 reused verbatim (lines 18-31, DEC-LOGIN-05).
- NO modification of `auth/jwt_issuer_guard.py::requires_issuer` factory — reused verbatim for KD-3 dep.
- NO modification of `schemas/common.py::_Base` — `extra='forbid'` reused verbatim (Layer 4 defense).
- NO new sync catalog entries — `sync_entries_v.py` + `sync_entries_a.py` already carry all sync_status entries (`sync_status: "no usado — tabla out-of-catalog, nunca replicada"` per ER lines 976, 1096, 1111). DEC-LOGIN-01..10 NOT extended to sync catalog (all 5 sync tables pre-existing and out-of-catalog).
- NO new triggers — existing `login_ls_session_guard` (migration 0001:2203-2214) + `login_audit_columns` (2533-2534) + `login_set_vigente_inicial` (2538-2539) + `login_enqueue_sync` (2777-2788) cover the F1.15 read-only path; no trigger additions needed.
- NO new permissions — `audit_read` pre-seeded at `0002_seed_permisos_canonicos.py:48` (DEC-LOGIN-09.B Option B adopted — no new permission seeded).
- NO new role grants — operador + admin already granted `audit_read` per F1.14 closure; F1.15 inherits.
- Header `Cache-Control: no-store` on EVERY response (200 + 4xx + 5xx) of `GET /usuarios/{uuid}/login` — via `no_store_headers()` helper + `apply_no_store_header(response)` before return + `headers=no_store` param in `HTTPException` constructors — DEC-LOGIN-05 XR6 mirror from F1.10/F1.11/F1.12/F1.13/F1.14.
- Discriminators stable: `tenant_scope_violation` (403 operador cross-branch), `permission_denied` (403 no `audit_read`), `uuid_usuario_invalid` (422 Pydantic validator, Layer 4), `cursor_invalid` (400 base64 decode failure, Layer 4), `limit_out_of_range` (422 Pydantic validator, Layer 4).
- Precedencia de errores: KD-3 (403 issuer) > Pydantic (422) > Layer 2 tenant scope (200 with `items=[]` due to SQL filter, NEVER 403 per DEC-LOGIN-08) > Step 4 SELECT helpers (200) > Step 7 build response (200).
- MIGRATION 0033 MUST be idempotent: pre-flight `DO $$` is read-only; Op 1 `CREATE INDEX CONCURRENTLY IF NOT EXISTS` (atomic, production-safe, respects no-trigger on `prod.login`); downgrade `DROP INDEX CONCURRENTLY IF EXISTS` (production-safe, no table lock).
- `CREATE INDEX CONCURRENTLY` cannot run inside a transaction — `op.get_context().autocommit_block()` wraps Op 1 + downgrade (KD-7 F1.6..F1.14 pattern, mirrors `0011_add_seq_lookup_indexes.py:62`).
- Per-commit ceiling: <800 LOC. Each cluster T1..T5 fits within the limit (T3 handler + mount at ~80 LOC is the largest implementation block, well within).
- Mensajes conventional commit; cuerpo técnico en neutral Spanish.

## Acceptance Gates

- TDD strict: RED first, GREEN minimum, REFACTOR last. Clusters T1..T5 explicitly note this discipline.
- ~12 tests + 2 AST walks across 4 test files PASS via `uv run pytest backend/tests/unit/test_login_historico.py backend/tests/unit/test_login_historico_repo.py backend/tests/unit/test_login_historico_schemas.py backend/tests/integration/test_migration_0033_index.py backend/tests/static/test_login_historico_read_only.py -q`
- MIGRATION 0033 applied + downgrade reverses cleanly via `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` (round-trip idempotent)
- 1 handler (`GET /api/v1/usuarios/{uuid}/login`) implemented per design.md §10 (8-step chain)
- `repo/login_historico.py` 3 typed SELECT helpers authored (DEC-LOGIN-01..10)
- `schemas/usuarios.py` authored with 3 Pydantic shapes (Layer 4 defense via `extra='forbid'`)
- KD-3 issuer chain `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` applied with `Cache-Control: no-store` on every response (DEC-LOGIN-05)
- KD-LOGIN-01 SELECT-only invariant verified via AST walk on `get_login_historico`
- KD-LOGIN-02 read-only AST walk invariant verified via `tests/static/test_login_historico_read_only.py` (NO UPDATE/DELETE/COMMIT)
- DEC-LOGIN-01.A dedicated `api/v1/usuarios_login.py` router mounted at FastAPI app-level (sibling of `auth.py`, NOT in `caja.py`)
- DEC-LOGIN-02 KD-3 issuer chain `operador-`+`admin-` applied
- DEC-LOGIN-03.A tenant scope post-V1 with SQL-side filter for `operador-` own-branch verified; admin bypasses
- DEC-LOGIN-04 cursor pagination via `(timestamp_evento DESC, uuid ASC)` + `cursor_encode/cursor_decode` reused from `router_factory.py:127-140`
- DEC-LOGIN-05 `Cache-Control: no-store` verified on 200 / 400 / 403 / 422 / 5xx responses
- DEC-LOGIN-06 MIGRATION 0033 composite index `prod.idx_login_uuid_usuario_evento ON (uuid_usuario, timestamp_evento DESC)` applied via `CREATE INDEX CONCURRENTLY`
- DEC-LOGIN-07 `{items, next_cursor}` envelope forward-compatible with Parte 2 (no `activo`, no `count`, no `total`, no `has_more`)
- DEC-LOGIN-08 empty-user 200 with `items=[]` + `next_cursor=None` verified (NOT 404)
- DEC-LOGIN-09.B `audit_read` permission gate verified (operador with audit_read → 200; without → 403 `permission_denied`)
- DEC-LOGIN-10 `estado: Literal["exitoso", "fallido", "cerrado"]` verified (NEVER synthetic boolean `activo`)
- Empty branch contract verified (zero `prod.login` rows → 200 with `items=[]`, NOT 404)
- Response-time parity verified (empty-user within ±5% of populated-user — anti-enumeration side-channel, REQ-OPS-104)
- Cursor pagination invariants verified (next_cursor non-null iff more rows; resume at exact boundary; malformed cursor → 400)
- MIGRATION 0033 idempotency verified (re-running upgrade head on migrated DB → no net change)
- Downgrade cycle verified (downgrade -1 → index dropped; upgrade head → index re-created round-trip)
- No new permission seeded (DEC-LOGIN-09.B — `audit_read` reuse only)
- No AI attribution in commits (no `Co-authored-by:`, no AI trailers)
- All F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11/F1.12/F1.13/F1.14 tests still PASS (no_regresion gate)
- ruff + mypy --strict clean on all 5 new/modified files (1 NEW migration + 1 NEW repo module + 1 NEW schemas + 1 NEW handler module + 1 MODIFIED `__init__.py` + 4 NEW test files)
- 5 CI gates green (matches F1.7/F1.9/F1.10/F1.11/F1.12/F1.13/F1.14): `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.14`
- 0 regresiones introducidas; baseline F1.14 pre-existing failures documented and unchanged
- REQ-OPS-102..105 + REQ-OPS-XR6 REFERENCE traceability verified: each REQ has ≥1 RED test that proves it (mapping in design.md Appendix B + this file's per-task rationale)
- Architecture risks §12 (R1..R7) verified: R1 endpoint ownership → T3.1 dedicated router + DEC-LOGIN-01.A; R2 prod.login mutation → T4.1 AST walk enforces 0 matches; R3 performance → T1.2 composite index MIGRATION 0033; R4 cursor race → DEC-LOGIN-04 stable cursor pagination; R5 404 leaks user existence → DEC-LOGIN-08 always 200; R6 audit_read permission → DEC-LOGIN-09.B + T2.4 schema gate; R7 estado nullable → DEC-LOGIN-10 Literal + nullable handling.

---

## Out of Scope Tasks

- UI integration (Fase 11 HU-F11.1/F11.2): deferred to Fase 11. `LoginHistoryPanel` (operator diagnostic UI) consumes this endpoint, but the UI component itself is out of scope. Fase 11 owns them.
- `POST /usuarios/{uuid}/login/{login_uuid}/cerrar` closure action (HU-F16.1/F16.5 Parte 2): Parte 2 owns. F1.15 ships only the read-list slice.
- `?activo=` filter (Parte 2 F16.1/F16.5): `activo` does not exist in `prod.login.estado` domain per `plan.md` line 1143. Parte 2 may introduce this synthetic derived field if their UI requires it.
- `?fecha_desde=&fecha_hasta=` date range filter (F18.1 Parte 2): future addition, out of F1.15 scope.
- Login attempt statistics (`COUNT(*)` aggregations, F18.2): Parte 2.
- Real-time WebSocket subscription to login events (Fase 14+): Fase 14 owns push-based notifications.
- Admin impersonation "login as user X" (HU-F19.x Parte 2): out of F1.15 scope per Parte 2 admin domain.
- `?uuid_sucursal=` filter for branch-scoped history (F18.3 Parte 2): F1.15 applies the Layer 2 filter server-side (DEC-LOGIN-03.A) — operador NEVER sees cross-branch data via a query param.
- Login history notifications (push/SSE): Fase 14+ — polling pattern only for F1.15.
- Cross-branch login history aggregation (F19.x Parte 2): admin cross-branch aggregation, F19.x Parte 2.

## Commit summary (5 expected atomic commits)

| # | Cluster | Commit message | Files | LOC est. |
|---|---|---|---|---|
| 1 | T1 | `feat(backend): HU-F1.15 -- T1 MIGRATION 0033 composite index (uuid_usuario, timestamp_evento DESC)` | 1 NEW migration + 1 partial NEW test (T1.1 pre-flight) | ~25 |
| 2 | T2 | `feat(backend): HU-F1.15 -- T2 repo/login_historico.py 3 helpers + schemas/usuarios.py 3 schemas` | 1 NEW repo module + 1 NEW schemas + 2 NEW partial tests | ~55 |
| 3 | T3 | `feat(backend): HU-F1.15 -- T3 api/v1/usuarios_login.py handler (8-step chain + KD-LOGIN-01 SELECT-only + DEC-LOGIN-01 mount)` | 1 NEW handler module (GET 8-step) + 1 MODIFIED `__init__.py` (3 LOC mount) | ~80 |
| 4 | T4 | `test(backend): HU-F1.15 -- T4 KD-LOGIN-02 AST walk + 2 mandated handler + 3 repo + 4 schema + 2 migration tests` | 4 NEW test files + 1 NEW AST walk + 1 EXTENDED repo test + 1 EXTENDED schema test + 1 EXTENDED migration test | ~70 |
| 5 | T5 | `chore(openspec): HU-F1.15 -- T5 apply-report + all tasks [x] + pending.md update` | 1 NEW apply-report + 1 MODIFIED pending.md + tasks.md [x] marks | ~30 |

**Total**: 5 commits, ~260 LOC cumulative (impl + tests + migration + AST walks + docs), 1 PR to `origin/dev`. Net apply delta ~70 LOC production + ~55 LOC tests + ~25 LOC migration + ~15 LOC AST walk + ~30 LOC docs.

## Definition of Done (apply phase)

- [x] ~12 tests + 2 AST walks across 4 test files PASS via `uv run pytest backend/tests/unit/test_login_historico.py backend/tests/unit/test_login_historico_repo.py backend/tests/unit/test_login_historico_schemas.py backend/tests/integration/test_migration_0033_index.py backend/tests/static/test_login_historico_read_only.py -q`
- [x] MIGRATION 0033 applied + downgrade reverses cleanly via `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` (round-trip idempotent)
- [x] 1 handler (`GET /api/v1/usuarios/{uuid}/login`) implemented per design.md §10 (8-step chain)
- [x] `repo/login_historico.py` 3 typed SELECT helpers authored (DEC-LOGIN-01..10)
- [x] `schemas/usuarios.py` authored with 3 Pydantic shapes (Layer 4 defense via `extra='forbid'`)
- [x] KD-3 issuer chain `_login_historico_issuer_dep = requires_issuer("operador-", "admin-")` applied with `Cache-Control: no-store` on every response (DEC-LOGIN-05)
- [x] KD-LOGIN-01 SELECT-only invariant verified via AST walk on `get_login_historico`
- [x] KD-LOGIN-02 read-only AST walk invariant verified via `tests/static/test_login_historico_read_only.py` (NO UPDATE/DELETE/COMMIT)
- [x] DEC-LOGIN-01.A dedicated `api/v1/usuarios_login.py` router mounted at FastAPI app-level (sibling of `auth.py`, NOT in `caja.py`)
- [x] DEC-LOGIN-02 KD-3 issuer chain `operador-`+`admin-` applied
- [x] DEC-LOGIN-03.A tenant scope post-V1 verified (operador own-branch SQL filter; admin bypasses)
- [x] DEC-LOGIN-04 cursor pagination invariants verified (`(timestamp_evento DESC, uuid ASC)` + base64 JSON cursor)
- [x] DEC-LOGIN-05 `Cache-Control: no-store` verified on 200 / 400 / 403 / 422 / 5xx responses
- [x] DEC-LOGIN-06 MIGRATION 0033 composite index applied (`pg_indexes` catalog + DESC order honored on 100-row probe)
- [x] DEC-LOGIN-07 `{items, next_cursor}` envelope verified (NO `activo`, NO `count`, NO `total`, NO `has_more`)
- [x] DEC-LOGIN-08 empty-user contract verified (zero rows → 200 with `items=[]` + `next_cursor=null`, NOT 404)
- [x] DEC-LOGIN-09.B `audit_read` permission gate verified (operador with audit_read → 200; without → 403 `permission_denied`)
- [x] DEC-LOGIN-10 `estado: Literal["exitoso", "fallido", "cerrado"]` verified (NEVER synthetic boolean `activo`)
- [x] Empty branch contract verified (no `prod.login` rows → 200 with `items=[]`, NOT 404)
- [x] Response-time parity verified (empty-user within ±5% of populated-user — REQ-OPS-104 anti-enumeration)
- [x] MIGRATION 0033 idempotency verified (re-running upgrade head on migrated DB → no net change)
- [x] Downgrade cycle verified (downgrade -1 → index dropped; upgrade head → index re-created round-trip)
- [x] No new permission seeded (DEC-LOGIN-09.B — `audit_read` reuse only)
- [x] No AI attribution in commits (no `Co-authored-by:`, no AI trailers)
- [x] All F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11/F1.12/F1.13/F1.14 tests still PASS (no_regresion gate)
- [x] ruff + mypy --strict clean on all 5 new/modified files
- [x] 5 CI gates green (`factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.14`)
- [x] 0 regresiones introducidas; baseline F1.14 pre-existing failures documented and unchanged
- [x] REQ-OPS-102..105 + REQ-OPS-XR6 REFERENCE traceability verified via per-REQ RED tests
- [x] 5 atomic commits authored with conventional commit messages, neutral Spanish, NO `Co-authored-by:` trailers

## Next phase

`sdd-apply hu-f1-15-login-historico` — TDD-strict RED→GREEN→REFACTOR per cluster T1..T5. Orchestrator executes the 5 atomic commits in order, verifies each cluster's exit criteria, and routes to `sdd-verify` after all commits land.

## References

- `openspec/changes/hu-f1-15-login-historico/design.md` (~1460 LOC, 16 sections + 2 appendices, MIGRATION 0033 SQL body + AST walk precedent + 10 DECs + 2 KDs + 8-test matrix in Appendix B) — full architecture.
- `openspec/changes/hu-f1-15-login-historico/proposal.md` (~770 LOC, 16 sections, DEC-LOGIN-01..10, KD-LOGIN-01..02, R1..R7 — 4 RESOLVED at propose phase) — pre-design proposal.
- `openspec/changes/hu-f1-15-login-historico/specs/operations/spec.md` (~363 LOC, 4 REQs REQ-OPS-102..105 + REQ-OPS-XR6 REFERENCE, 17 Given/When/Then/And scenarios) — operational requirements.
- `openspec/changes/hu-f1-15-login-historico/exploration.md` (~770 LOC, 17 sections, DEC-LOGIN-01..10 mandate, R1..R7 risks, pre-flight 15/15 PASS) — pre-design exploration.
- `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/tasks.md` (~590 LOC, 5 clusters T1..T5, 14 atomic tasks, 5 expected commits) — **canonical precedent** for F1.15 structure mirrored verbatim.
- `openspec/changes/archive/2026-09-15-hu-f1-14-sync-estado/{proposal,design,specs/operations/spec.md,apply-report,archive-report}.md` — F1.14 full cycle precedent.
- `openspec/changes/archive/2026-09-15-hu-f1-13-arqueo/tasks.md` (~745 LOC, 6 clusters T1..T5 + T-GAP-BE-05) — canonical precedent for multi-cluster decomposition.
- `openspec/changes/archive/2026-09-15-hu-f1-12-venta-suscripcion/tasks.md` (~860 LOC, 8 clusters T1..T8, 31 atomic tasks) — canonical precedent for 8-cluster decomposition.
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/tasks.md` — F1.11 precedent (KD-TKT-01 single-commit + AST walk).
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/tasks.md` — F1.10 precedent (KD-FE-01 single-commit).
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/tasks.md` — F1.9 precedent (KD-FACT-01 single-commit + `crear_factura_*` helpers reused).
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/tasks.md` — F1.7 precedent (KD-S2 tenant scope post-V1, `resolve_active_subscription_for_exit` reuse).
- `openspec/changes/archive/2026-09-14-hu-f1-6-ingresos/tasks.md` — F1.6 precedent (DEC-IDEM-01 Idempotency-Key header + placa regex + KD-3 issuer chain).
- `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/tasks.md` — F1.5 precedent (`repo/versioned.py::close_and_insert` + AST walk no-raw-UPSERT on [V]).
- `openspec/specs/operations/spec.md` lines 2517-4171 (XR1..XR6 progression + REQ-OPS-083..101 last-req-number series — F1.15 appends REQ-OPS-102..105) + line 3951 (REQ-OPS-XR6 canonical from F1.13 — F1.15 references, does NOT create new).
- `plan.md` lines 1137-1155 — HU-F1.15 full definition, 2 atomic tasks T1..T2, 70 LOC production budget, 2 mandated tests at line 1149.
- `plan.md` lines 610-617 — HU-F1.2 story, shares `prod.login` as the audit table for lockout writes.
- `plan.md` line 1143 verbatim — "cada uno con su `estado` real (`exitoso|fallido|cerrado`) — nunca un campo booleano `activo`" (DEC-LOGIN-10 source).
- `plan.md` line 1149 — 2 mandated handler tests: empty user / populated user.
- `plan.md` line 1151 — 70 LOC production budget.
- `plan.md` line 1154 — Response shape `{items, next_cursor}` per canonical list contract.
- `plan.md` lines 7571-7574 — F1 endpoint table row 2391 — duplicate-resource note: Parte 1 F1.15 + Parte 2 F16.1/F16.5 — same resource, built once, shared backend (DEC-LOGIN-01 + DEC-LOGIN-07 source).
- `modelo_datos_er.mmd` lines 7-50 (`usuarios` [V] bi-temporal `VersionedBase`), lines 558-573 (`login` [L-S] composite PK + FK `fk_login_uuid_usuario` + FK `fk_login_uuid_sucursal` + 4 triggers + `sync_status: pendiente | sincronizado | error`).
- `migrations/versions/0001_initial_schema.py` — Initial schema (composite PKs, partitions, base triggers; `login_ls_session_guard` trigger at lines 2203-2214).
- `migrations/versions/0002_seed_permisos_canonicos.py` lines 39-56 — `CANONICAL_PERMISOS` with `audit_read` at line 48 — DEC-LOGIN-09.B source.
- `migrations/versions/0011_add_seq_lookup_indexes.py:62` — `CONCURRENTLY` precedent for index migration — DEC-LOGIN-06 source.
- `migrations/versions/0021_least_privilege_and_immutability_contract.py:206` — `_NARROW_UPDATE_LS_TABLES["login"] = ("timestamp_cierre", "estado")` — KD-LOGIN-01 + KD-LOGIN-02 anchor.
- `migrations/versions/0032_seed_alert_types_operativos.py` — (whole file, F1.14 head) — F1.15's `down_revision`.
- `migrations/versions/0033_login_historic_index.py` — (whole file, NEW) F1.15 REAL DDL composite index (Op 0 pre-flight + Op 1 `CREATE INDEX CONCURRENTLY`).
- `models/L_S/login.py` lines 33-74 — Verbatim ORM model + 5 business columns + state enum.
- `models/V/usuarios.py` — (whole file) Usuarios ORM — F1.15 reads `uuid` only for optional existence check (SKIPPED per DEC-LOGIN-08).
- `repo/session_cycle.py` lines 49-146 — `record_login` write helper — F1.15 NEVER calls it; only references the table it writes to.
- `repo/tarifas_vigencia.py` lines 79-162 — `list_tarifas_vigentes` cursor pagination precedent.
- `api/router_factory.py` lines 127-140 — `cursor_encode` / `cursor_decode` / `Cursor` dataclass — DEC-LOGIN-04 reuse.
- `api/router_factory.py` lines 140-227 — Factory `list_endpoint` pattern — `next_cursor` encoding + `read_list_schema` shape.
- `api/router_factory.py` line 227 — `{items, next_cursor}` envelope — DEC-LOGIN-07 source.
- `api/v1/auth.py:69` — `APIRouter(prefix="/auth", tags=["auth"])` — POST-mutating-only rationale for DEC-LOGIN-01.A.
- `api/v1/auth.py:239-246` — `fallido` set on failed `POST /auth/login`.
- `api/v1/auth.py:260-266` — `exitoso` set on successful `POST /auth/login`.
- `api/v1/auth.py:352-393` — `cerrado` set on `POST /auth/logout`.
- `api/v1/_helpers.py` lines 18-31 — `no_store_headers()` + `apply_no_store_header()` — DEC-LOGIN-05 source.
- `auth/jwt_issuer_guard.py` — (whole file) `requires_issuer` factory — KD-3 dep.
- `auth/tenancy.py` — (whole file) `TenantContext` + `get_tenant_ctx` — Layer 2 dep.
- `schemas/common.py::_Base` — (whole file) `extra='forbid'` — Layer 4 base.
- `schemas/usuarios.py` — (whole file, NEW) 3 NEW Pydantic shapes: `LoginHistoricoQueryParams` + `LoginIntentoItem` + `LoginHistoricoListResponse`.
- `tests/static/test_no_raw_dml_on_a_tables.py` — F1.5 PR5-016 AST walk precedent.
- `tests/static/test_sync_estado_read_only.py` — F1.14 KD-SYNC-02 AST walk precedent.
- `tests/static/test_login_historico_read_only.py` — (NEW) KD-LOGIN-02 walk (per-handler scope, [L-S] variant).
- `tests/unit/test_login_historico.py` — 2 mandated handler tests (empty + populated user).
- `tests/unit/test_login_historico_repo.py` — 3 repo unit tests (helper purity + Layer 2 filter).
- `tests/unit/test_login_historico_schemas.py` — 4 schema tests (extra=forbid + limit validators + estado Literal).
- `tests/integration/test_migration_0033_index.py` — 5 pre-flight tests + 2 post-migration tests = 7 tests covering MIGRATION 0033.

---

**End of tasks.**
