# Tasks: hu-f1-7-salidas

> **Change**: `hu-f1-7-salidas`
> **Phase**: tasks (sdd-tasks) — checklist only, do NOT implement
> **HU**: HU-F1.7 — Server-side enforcement of `POST /api/v1/operacion/salidas` (rotación + mensualidad derivation, KD-FORZADO-01 verbatim reuse de F1.6, KD-IVA inline-seed via MIGRATION 0026, tarifa vigente vía `prod.calcular_cotizacion` PL/pgSQL F1.8 con lock FOR SHARE continuo en la misma TX). 220 LOC budget per `plan.md` línea 835.
> **Status**: READY — 22 tasks planned across 8 phases (1 migration + 4 repo+ORM + 3 schemas + 1 handler + 5 tests + 2 AST walks + 4 housekeeping + 2 archive). TDD-strict defense in depth (D-HU-F1.7-7 5 layers: regex/KD-3 server-side → KD-FORZADO chain → alerta INSERT same-TX → AST walk ordering gate → partial unique index + REVOKE/IMMUTABLE).
> **Preflight (this session)**: `pace=auto`, `artifact_store=hybrid`, `delivery_strategy=auto-chain` (cached per F1.6 precedent), `review_budget_lines=400` (vigente en `openspec/config.yaml`), `commit_ceiling_loc=800`.
> **Branch topology**: rama única `feat/fase-1-prerequisites-backend` (HEAD `2a2cbd2`); un único PR directo a `origin/dev` (matches F1.5/F1.6 precedent). Commit split interno: 2 commits ≤800 LOC cada uno (apply-código + tests+verification).
> **TDD discipline note (Phase 1)**: every task follows **RED → GREEN → REFACTOR**. RED test is written first (must fail by construction with `ImportError`, `relationError`, or `AssertionError`); GREEN implementation makes the test pass minimally; REFACTOR cleans duplication. No GREEN-without-RED.
> **Inputs read**: `exploration.md` (16 sections, V1..V5 + KD-FORZADO-01 reuse, 9 risks R1..R9, files-to-touch §16), `proposal.md` (D-HU-F1.7-1..20, KD-V1..V5 + DEC-MONO-01 + DEC-SUC-21-NEW + DEC-SAL-01 + DEC-IMP-01 + DEC-FORZADO-01 + DEC-IDEM-01 adoptados, 10 OQ cerradas §11), `specs/operational/spec.md` (REQ-OPS-042..052 RFC 2119, 35 escenarios), `design.md` (16 sections, 12-step handler skeleton §7, MIGRATION 0026 SQL body §8, repo skeleton §9, AST walk ordering gate §15, R1..R9 riesgos).
> **Precedents mirrored**: F1.6 (REQ-OPS-034..041, KD-FORZADO-01 verbatim reuse, KD-7 pre-flight `DO $$` pattern, defense in depth 4-layer, AST walks for ordering gate, commit `21097c8`), F1.8 (REQ-OPS-022..025, PL/pgSQL VOLATILE `calcular_cotizacion` + `FOR SHARE` lock continuity KD-1, KD-IVA resolver recipe, commit `a3d0c39`), F1.5 (REQ-OPS-030..033, MV pattern + KD-7 pre-flight, commit `fc72adb`), F1.4 (REQ-OPS-017..021, bi-temporal predicate reusable in V2, commit `467b4f0`), F1.3 (REQ-OPS-026..029, partial unique index pattern `unique_active_sesion_per_user` + AST walk, commit `ca3f9bf`).
> **Skills loaded**: `gentle-sdd-tasks` (paths injected via orchestrator).

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~1,500 across 1 PR (migration 0026 ~140 LOC + 4 NEW repo/ORM files ~270 LOC + 2 MODIFIED `api/v1/operacion.py`+`schemas/operacion.py` ~130 LOC + 5 NEW test files ~810 LOC + 2 AST walks ~200 LOC + spec delta ~50 LOC + 1 archive commit) |
| Total tasks | 22 (1 preflight + 1 migration RED/GREEN + 4 repo+ORM RED/GREEN pairs + 1 schemas + 1 handler + 5 tests + 2 AST walks + 4 housekeeping + 3 archive) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Medium** — F1.7 es ~1.7x F1.6's LOC pero cohesivo (un único endpoint nuevo, un único módulo `repo/salida.py`); 2-commit split interno (apply-código ≤800 LOC + tests+verification ≤700 LOC) mantiene cada commit bajo el techo `commitlint` |
| Chained PRs recommended | No — un único PR (matches F1.5/F1.6 precedent `feat/fase-1-prerequisites-backend` → `origin/dev`); defensa en profundidad se prueba in-place |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Un único PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 2 commits internos: (1) apply-código (migration 0026 + ORM `Salida` + `repo/salida.py` + `repo/impuestos.py` + schemas + handler); (2) tests + verification (5 test files + 2 AST walks + suite verde + ruff/mypy clean + factory_intact/event_helper_intact/auth_tenancy_intact gates) |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesivo single-endpoint; budget risk Medium pero dentro del precedente F1.6 |

| Phase | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|-------|-------|---------------|----------------|----------------|
| Phase 0: Pre-flight verification | T0.1..T0.3 | — | — | 0 |
| Phase 1: Migration 0026 | T1.1..T1.4 | ~140 LOC (migration) | ~80 LOC (idempotency test) | 220 |
| Phase 2: ORM `Salida` + repo helpers | T2.1..T2.5 | ~270 LOC (40 ORM + 180 repo salida + 50 repo impuestos) | ~150 LOC (3 RED tests) | 640 |
| Phase 3: Schemas Pydantic | T3.1..T3.4 | ~80 LOC (2 schemas + 4 errors) | ~80 LOC (RED test) | 800 |
| Phase 4: Handler `create_salida` | T4.1..T4.3 | ~200 LOC (handler 12-step chain) | ~400 LOC (10 RED tests) | 1,400 |
| Phase 5: Test files consolidation | T5.1..T5.5 | — | ~700 LOC (5 test files consolidated) | 2,100 |
| Phase 6: AST walk invariants | T6.1..T6.3 | — | ~200 LOC (2 AST walks) | 2,300 |
| Phase 7: CI gates + housekeeping | T7.1..T7.4 | refactor (sin LOC nuevo) | — | 2,300 |
| Phase 8: OpenSpec archive | T8.1..T8.3 | archive commit | — | 2,300 |
| **Total** | **22** | **~690 LOC impl** | **~1,610 LOC tests** | **~2,300 LOC cumulative workload (apply deltas ~800 LOC net)** |

> Tope por commit: <800 LOC. Apply-código cabe en ~490 LOC net (≤800 OK). El split en 2 commits se ejecuta como 2 commits consecutivos dentro del mismo PR (no chained PRs). El `net diff` total del PR (~800 LOC impl + tests como archivos nuevos) cumple el budget.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| PR1 (único, 2 commits) | Commit 1 (apply-código): MIGRATION 0026 + 4 NEW `repo/*.py`/`models/L_S/*.py` + `create_salida` handler append + `schemas/operacion.py` append. Commit 2 (tests+verification): 5 test files + 2 AST walks + suite verde + ruff/mypy clean + factory_intact/event_helper_intact/auth_tenancy_intact. Commit 3 (archive): OpenSpec archive separate | `feat/fase-1-prerequisites-backend` → `origin/dev` | `uv run pytest backend/tests/unit/test_operacion_salidas.py backend/tests/unit/test_operacion_salidas_kd_forzado.py backend/tests/integration/test_salida_create_db.py backend/tests/integration/test_migration_0026_idempotent.py backend/tests/static/test_salida_handler_step_order.py backend/tests/static/test_no_write_after_salida_insert.py -q` | `pg_engine` real (`parkos-branch-db:5433`) con `PARKOS_DOCKER_TEST=1` para tests integración (T2.1, T5.3, T5.4); unit tests sin DB; AST walks parsean `api/v1/operacion.py::create_salida` y `repo/salida.py::crear_salida_evento` | Revert PR; migración `alembic downgrade -1` elimina index `one_exit_per_ingreso` + DELETE del `alert_types` rows + DELETE de `impuestos.IVA` (superuser; triggers respetados); handler revierte a F1.6 thin (sin `create_salida`); 4 NEW `repo/*.py` + ORM se vuelven unused pero harmless; schemas se eliminan via `git revert` |

## Tareas

### Phase 0 — Pre-flight verification (gate, ~10 LOC sin producción)

- [x] **T-HU-F1.7-0.1** [VERIFICATION] — Verify `prod.impuestos`, `prod.salidas`, `prod.alert_types` existen en DB.
  - **Acción**: ejecutar `psql $DATABASE_URL -c "\d prod.impuestos"`, `psql $DATABASE_URL -c "\d prod.salidas"`, `psql $DATABASE_URL -c "\d prod.alert_types"`. Cada uno debe listar columnas sin error.
  - **Validación**: 3 comandos exit 0; output muestra columnas de cada tabla. Si alguna falla → bloqueante para Phase 1 (MIGRATION 0026 Op 1 pre-flight abortaría).

- [x] **T-HU-F1.7-0.2** [VERIFICATION] — Verify F1.8 PL/pgSQL `prod.calcular_cotizacion` existe.
  - **Acción**: ejecutar `psql $DATABASE_URL -c "SELECT prod.calcular_cotizacion('<test_uuid>')::jsonb"` (con un uuid válido de un ingreso existente, o un uuid dummy que retornará `ingreso_no_encontrado`).
  - **Validación**: comando exit 0; output muestra jsonb `{"error":"ingreso_no_encontrado",...}` (o un payload `cobrar:true/false`). Si falla con `function does not exist` → bloqueante para Phase 2 (handler Step 7) y Phase 4 (test T4.1).

- [x] **T-HU-F1.7-0.3** [VERIFICATION] — Verify F1.6 `repo/ingreso.py::validar_kd_forzado` es importable.
  - **Acción**: ejecutar `uv run python -c "from parkos_core.repo.ingreso import validar_kd_forzado; print(validar_kd_forzado.__doc__[:100])"`.
  - **Validación**: exit 0; output muestra docstring del helper. Si falla con `ImportError` → bloqueante para Phase 2 (repo/salida.py reuso) y Phase 4 (handler Step 6 V4).
  - **Exit criteria Phase 0**: ALL 3 verifications pass → proceed to Phase 1.

### Phase 1 — MIGRATION 0026 (RED → GREEN, ~140 LOC impl + ~80 LOC test)

- [x] **T-HU-F1.7-1.1** [GREEN] — Create `migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py` (~140 LOC)
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py` (nuevo).
  - **Contenido**: `revision = "0026_seed_impuestos_iva_and_one_exit_per_ingreso"`, `down_revision = "0025_alerta_datos_nuevos"` (F1.6 chain head); `from alembic import op`; constante `_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"` (precedente F1.5/F1.6); `upgrade()` ejecuta 4 operaciones en orden:
    1. **Op 1 — Pre-flight `DO $$`** (KD-7 F1.6 pattern): `DECLARE _n_impuestos, _n_salidas, _n_alert_types bigint; SELECT count(*) INTO _n_impuestos FROM pg_catalog.pg_class WHERE relname='impuestos' AND relnamespace='prod'::regnamespace; IF _n_impuestos IS NULL OR _n_impuestos = 0 THEN RAISE EXCEPTION '0026_preflight_abort: tabla prod.impuestos no existe. Aplique migrations 0001-0025 antes.'; END IF;` (repetir para `salidas` y `alert_types`). Emits `RAISE NOTICE` con row counts.
    2. **Op 2 — Inline-seed `impuestos.IVA`** (KD-IVA resolver para F1.8): `INSERT INTO prod.impuestos (uuid, codigo, nombre, porcentaje, vigente_desde, vigente_hasta, estado, created_at) VALUES (gen_random_uuid(), 'IVA', 'IVA', 0.19, NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()) ON CONFLICT (codigo, vigente_desde) DO NOTHING;`. `porcentaje=0.19` regulatory constant IVA Colombia 2026 (locked F1.8 design.md §4 KD-IVA).
    3. **Op 3 — Inline-seed 2 `alert_types`** (F1.7 alerts V2/V5 bypass): `INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity) VALUES ('subscripcion_vencida_forzado', 'Salida vehicular forzada por administrador al detectar subscripción vencida al momento de salida', 'warning'), ('tarifa_vigente_forzado', 'Salida vehicular forzada por administrador al detectar tarifa no vigente al momento de salida', 'warning') ON CONFLICT (tipo_alerta) DO NOTHING;` (respeta trigger `alert_types_inmutable` migration 0013 — INSERT-only para `rol_app`).
    4. **Op 4 — Partial unique index `one_exit_per_ingreso`** (KD-S16 TOCTOU closure): `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso ON prod.salidas (uuid_ingreso) WHERE NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida = prod.salidas.uuid AND a.tipo_anulable = 'salida' AND a.estado = 'ejecutada');`. `CONCURRENTLY` para no lock reads/writes en producción; `IF NOT EXISTS` para idempotencia.
  - `downgrade()` ejecuta reverse order: (a) `DROP INDEX IF EXISTS prod.one_exit_per_ingreso`; (b) `DELETE FROM prod.alert_types WHERE tipo_alerta IN ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado')` (superuser; bypass `alert_types_inmutable`); (c) `DELETE FROM prod.impuestos WHERE codigo='IVA' AND estado='activo'` (superuser; R8 caveat — si trigger `impuestos_inmutable` existe, workaround = `UPDATE … SET estado='inactivo'`).
  - **Acción**: pegar exactamente el SQL skeleton; header `from __future__ import annotations` + `from alembic import op`; constantes + pre-flight + 4 ops + downgrade; docstring con referencia a REQ-OPS-051 + REQ-OPS-052 + KD-7 F1.6 pattern + KD-IVA blocker F1.8. — **Validación**: `uv run python -c "from parkos_core.migrations.versions import _dummy"` (import OK sin error syntax); file size ~140 LOC.

- [x] **T-HU-F1.7-1.2** [RED] — Write `tests/integration/test_migration_0026_idempotent.py` con 2 RED tests
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_0026_re_apply_ok` — apply `alembic upgrade head` 2 veces seguidas; assert second es no-op (Op 2 `ON CONFLICT DO NOTHING` no duplica fila `prod.impuestos`; Op 3 `ON CONFLICT DO NOTHING` no duplica filas `prod.alert_types`; Op 4 `IF NOT EXISTS` no recrea index `prod.one_exit_per_ingreso`).
    - T2: `test_iva_row_present_post_migration` — assert `prod.impuestos` contiene exactamente 1 fila con `codigo='IVA', porcentaje=0.19, vigente_hasta IS NULL, estado='activo'`; assert `prod.alert_types` contiene 2 filas con `tipo_alerta IN ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado')` y `severity='warning'`; assert `pg_indexes` muestra index `one_exit_per_ingreso` sobre `prod.salidas (uuid_ingreso)`.
  - **Patrón F1.5/F1.6**: `pg_engine` real (testcontainers precedent F1.4); sembrar fixtures via SQL directo; asserts via `SELECT count(*) FROM …`.
  - **Acción**: usar `pg_engine` fixture; tests parametrizados; asserts sobre `prod.impuestos`, `prod.alert_types`, `pg_indexes`. — **Archivo**: `backend/tests/integration/test_migration_0026_idempotent.py` (nuevo, ~80 LOC, 2 tests). — **Validación**: `uv run pytest backend/tests/integration/test_migration_0026_idempotent.py -q` con `PARKOS_DOCKER_TEST=1` falla con `ImportError` (migration 0026 no existe) o `relationError` (pre-migration columns missing) o `index 'one_exit_per_ingreso' does not exist` (Op 4 no aplicada).

- [x] **T-HU-F1.7-1.3** [GREEN] — Run `alembic upgrade head` + run tests → GREEN
  - **Acción**: ejecutar `uv run alembic upgrade head` (aplica 0026 al DB de test); luego `uv run pytest backend/tests/integration/test_migration_0026_idempotent.py -q` con `PARKOS_DOCKER_TEST=1`.
  - **Validación**: `2 passed` (T1 + T2); alembic log muestra `0026_preflight: prod.impuestos existe con N filas`, `0026_preflight: prod.salidas existe con M filas`, `0026_preflight: prod.alert_types existe con K filas`, `INSERT INTO prod.impuestos` (1 fila insertada), `INSERT INTO prod.alert_types` (2 filas), `CREATE UNIQUE INDEX` (success).

- [x] **T-HU-F1.7-1.4** [GREEN] — Verify downgrade funciona (`alembic downgrade -1` → re-upgrade)
  - **Acción**: ejecutar `uv run alembic downgrade -1` (debería ejecutar Op 4 reverse `DROP INDEX`, Op 3 reverse `DELETE` alert_types, Op 2 reverse `DELETE` impuestos); luego `uv run alembic upgrade head` (debería re-aplicar sin error — idempotente).
  - **Validación**: downgrade exit 0 con `DROP INDEX`, `DELETE 2`, `DELETE 1`; re-upgrade exit 0 con `INSERT`, `INSERT`, `CREATE INDEX` (3 ops no-op via `ON CONFLICT DO NOTHING` + `IF NOT EXISTS`); T2 tests still pass post re-upgrade; assert no duplicate rows.
  - **Commit suggestion**: `feat(backend): HU-F1.7 — MIGRATION 0026 impuestos.IVA + alert_types + partial unique index (KD-IVA resolver)`.
  - **Exit criteria Phase 1**: T1.1 written; T1.2 RED tests written; T1.3 GREEN; T1.4 downgrade + re-upgrade verde; cumulative ~220 LOC en migración + tests.

### Phase 2 — ORM model `Salida` + Repo helpers (RED → GREEN, ~270 LOC impl + ~150 LOC tests)

- [x] **T-HU-F1.7-2.1** [RED] — Write `tests/integration/test_salida_create_db.py` con 3 RED tests
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`, mapean design §9 File 4):
    - T1: `test_buscar_ingreso_activo_por_uuid_existente` — seed `prod.ingreso(X, placa='ABC123')` con `vigente_hasta IS NULL` y NO salidas previas; `await repo_salida.buscar_ingreso_activo_por_uuid(session, uuid_ingreso=X)` retorna `Ingreso` instance con `uuid == X`.
    - T2: `test_buscar_ingreso_activo_por_uuid_inexistente` — sin seed; `buscar_ingreso_activo_por_uuid(session, uuid_ingreso=DUMMY)` retorna `None`.
    - T3: `test_crear_salida_evento_maps_integrityerror_to_salidaduplicada` — seed `prod.ingreso(X)`; first call a `crear_salida_evento` succeeds; second call (mismo `new_attrs`) raises `SalidaDuplicada` (mapped from `IntegrityError("one_exit_per_ingreso")`).
  - **Patrón F1.4/F1.6**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; sembrar via SQL directo al engine.
  - **Acción**: importar `repo.salida` (falla con `ImportError`); usar `pytest_asyncio.fixture`; asserts via `await session.get(Ingreso, X)` y `pytest.raises(SalidaDuplicada)`. — **Archivo**: `backend/tests/integration/test_salida_create_db.py` (nuevo, ~150 LOC, 3 tests). — **Validación**: `ImportError: cannot import name 'buscar_ingreso_activo_por_uuid' from 'parkos_core.repo.salida'` o `ModuleNotFoundError: No module named 'parkos_core.repo.salida'`.

- [x] **T-HU-F1.7-2.2** [GREEN] — Create `models/L_S/salida.py` ORM (~40 LOC)
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/models/L_S/salida.py` (nuevo, cierra pre-existing gap — tabla `prod.salidas` existe desde migration 0001 sin ORM).
  - **Contenido**: `class Salida(LifecycleEventBase)` con `__tablename__ = "salidas"`; columns `uuid_sucursal: Mapped[uuid_lib.UUID | None]` (`PG_UUID(as_uuid=True)`, `nullable=True`), `uuid_ingreso: Mapped[uuid_lib.UUID | None]` (`PG_UUID(as_uuid=True)`, `nullable=False`), `fecha_salida: Mapped[datetime | None]` (`DateTime(timezone=False)`, `nullable=True`), `fecha_retencion_hasta: Mapped[date | None]` (`Date`, `nullable=True`); `__table_args__ = ({"schema": "prod", "extend_existing": True},)`; docstring REQ-OPS-048 + DEC-SAL-01 + DEC-SUC-21-NEW (sin columna `tipo_salida`) + KD-FORZADO-01 (sin columnas `forzado`/`motivo`) + partial unique index `one_exit_per_ingreso`.
  - **Acción**: importar `uuid_lib`, `date`, `datetime`, `Mapped`, `mapped_column`, `Date`, `DateTime`, `PG_UUID`, `LifecycleEventBase`; `__all__ = ["Salida"]`. — **Validación**: `uv run python -c "from parkos_core.models.L_S.salida import Salida; print(Salida.__tablename__)"` exit 0; output `salidas`.

- [x] **T-HU-F1.7-2.3** [GREEN] — Create `repo/salida.py` (~180 LOC) con 4 helpers + 1 typed exception
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/salida.py` (nuevo).
  - **Contenido**:
    - `class SalidaDuplicada(Exception)` — 409 discriminator (mapped from `IntegrityError` con `err.orig` conteniendo `"one_exit_per_ingreso"`).
    - `async def buscar_ingreso_activo_por_uuid(session, *, uuid_ingreso) -> Ingreso | None` — V1 SELECT con `text("SELECT i.* FROM prod.ingreso i WHERE i.uuid = :uuid AND i.vigente_hasta IS NULL AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida = s.uuid AND a.tipo_anulable = 'salida' AND a.estado = 'ejecutada'))")`; row → `Ingreso` via `session.get(Ingreso, uuid_ingreso)` (read-only).
    - `async def cotizar_para_salida(session, *, uuid_ingreso) -> dict[str, Any]` — V5 thin wrapper sobre `repo.cotizacion.cotizar_ingreso` (F1.8 verbatim reuse); retorna jsonb payload de `prod.calcular_cotizacion`.
    - `async def crear_salida_evento(session, *, actor_uuid, new_attrs) -> Salida` — Step 8 INSERT: `Salida(**new_attrs, created_at=datetime.now(UTC).replace(tzinfo=None), created_by=actor_uuid)`; `session.add(new_row)`; `await session.flush()` con `except IntegrityError as err: if "one_exit_per_ingreso" in str(err.orig): raise SalidaDuplicada() from err; raise`.
    - `async def insertar_alerta_salida_forzado(session, *, uuid_sucursal, uuid_salida, actor_uuid, motivo, tipo_alerta) -> None` — Step 9 alerta: `Alerta(uuid_sucursal=..., uuid_usuario=actor_uuid, tipo_alerta=tipo_alerta, estado='abierta', timestamp_evento=datetime.now(UTC).replace(tzinfo=None), uuid_arqueo=None, datos_nuevos={"motivo": motivo, "uuid_salida": str(uuid_salida)})`; `session.add(alerta)`; `await session.flush()`.
  - **Acción**: importar `uuid_lib`, `datetime`, `UTC`, `Any`, `text`, `IntegrityError`, `AsyncSession`, `from ..models.L_E.ingreso import Ingreso`, `from ..models.L_S.salida import Salida`, `from ..models.L_W.alerta import Alerta`, `from .cotizacion import cotizar_ingreso`; `__all__ = ["SalidaDuplicada", "buscar_ingreso_activo_por_uuid", "cotizar_para_salida", "crear_salida_evento", "insertar_alerta_salida_forzado"]`; docstring REQ-OPS-043/047/048/050/051 + DEC-SAL-01 + KD-S7 lock continuity (Step 7→8→9 in single TX). — **Validación**: T2.1 3 tests PASS; `from parkos_core.repo.salida import SalidaDuplicada` resolves sin error.

- [x] **T-HU-F1.7-2.4** [GREEN] — Create `repo/impuestos.py` (~50 LOC)
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/impuestos.py` (nuevo).
  - **Contenido**: `async def validar_iva_configurado(session: AsyncSession) -> bool` — read helper: `now = datetime.now(UTC).replace(tzinfo=None); stmt = select(Impuestos).where(Impuestos.codigo == 'IVA', Impuestos.vigente_hasta.is_(None), Impuestos.estado == 'activo', Impuestos.vigente_desde <= now); return (await session.execute(stmt)).scalar_one_or_none() is not None`. Usado por HU-F1.9 facturación snapshot validation, HU-F14.2 audit, y test mocks. PL/pgSQL `prod.calcular_cotizacion` lee `prod.impuestos` directamente sin pasar por este helper (no es hot path).
  - **Acción**: importar `UTC`, `datetime`, `select`, `AsyncSession`, `from ..models.V.impuestos import Impuestos`; `__all__ = ["validar_iva_configurado"]`; docstring REQ-OPS-052 + KD-IVA F1.8. — **Validación**: `uv run python -c "from parkos_core.repo.impuestos import validar_iva_configurado; print(validar_iva_configurado.__doc__[:100])"` exit 0.

- [x] **T-HU-F1.7-2.5** [GREEN] — Run integration tests → GREEN
  - **Acción**: ejecutar `uv run pytest backend/tests/integration/test_salida_create_db.py -q` con `PARKOS_DOCKER_TEST=1`.
  - **Validación**: `3 passed` (T1, T2, T3); logs muestran INSERTs correctos en `prod.salidas`; T3 verifica que second call raises `SalidaDuplicada` (post-0026 partial unique index enforce).
  - **Commit suggestion**: `feat(backend): HU-F1.7 — ORM Salida + repo/salida helpers + repo/impuestos validator`.
  - **Exit criteria Phase 2**: T2.1 RED tests written; T2.2 ORM model; T2.3 repo helpers; T2.4 impuestos helper; T2.5 tests verde; cumulative ~640 LOC (incluyendo 150 LOC tests).

### Phase 3 — Schemas Pydantic (RED → GREEN, ~80 LOC impl + ~80 LOC test)

- [x] **T-HU-F1.7-3.1** [RED] — Write RED tests for `SalidaCreateForzado` y `SalidaReadForzado`
  - **Tests** (mapean design §6):
    - T1: `test_salida_create_forzado_rechaza_tipo_salida_injection` — `SalidaCreateForzado.model_validate({"uuid_ingreso": uuid, "tipo_salida": "ROTACION"})` raises `pydantic.ValidationError` (DEC-SUC-21-NEW extra='forbid').
    - T2: `test_salida_create_forzado_rechaza_cotizacion_snapshot_injection` — `SalidaCreateForzado.model_validate({"uuid_ingreso": uuid, "cotizacion_snapshot": {...}})` raises `ValidationError` (extra='forbid').
    - T3: `test_salida_read_forzado_tipo_salida_literal_validation` — `SalidaReadForzado.model_validate({..., "tipo_salida": "INVALID"})` raises `ValidationError` (Literal discriminator).
    - T4: `test_salida_read_forzado_default_fields` — `SalidaReadForzado.model_validate(minimal_dict)` accepts with `forzado_en_creacion: false`, `motivo_forzado: None`, `cotizacion_snapshot: None`.
  - **Patrón F1.6**: pure Pydantic validation tests, sin DB.
  - **Acción**: importar `SalidaCreateForzado`, `SalidaReadForzado` from `parkos_core.schemas.operacion` (falla con `ImportError`); usar `pytest.raises(ValidationError)`. — **Archivo**: `backend/tests/unit/test_schemas_salida.py` (nuevo, ~80 LOC, 4 tests). — **Validación**: `ImportError: cannot import name 'SalidaCreateForzado' from 'parkos_core.schemas.operacion'`.

- [x] **T-HU-F1.7-3.2** [GREEN] — Add `SalidaCreateForzado` + `SalidaReadForzado` a `schemas/operacion.py` (~50 LOC)
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (modificado, append post-F1.6 block).
  - **Contenido**:
    - `class SalidaCreateForzado(_Base)` con `model_config = ConfigDict(extra="forbid")` (heredado de `_Base`); fields `uuid_ingreso: uuid_lib.UUID` (REQUIRED), `placa: str | None = None` (OPTIONAL V3), `observaciones: str | None = None` (OPTIONAL V4 KD-FORZADO-01 prefix), `forzado: bool = False` (OPTIONAL bypass V2/V5).
    - `class SalidaReadForzado(_Base)` con fields inherited from `SalidaRead` (`uuid`, `created_at`, `created_by`, `sync_status`, `sync_timestamp`, `sync_attempts`, `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`) + NEW F1.7: `tipo_salida: Literal["MENSUALIDAD", "ROTACION"]`, `forzado_en_creacion: bool = False`, `motivo_forzado: str | None = None`, `cotizacion_snapshot: CotizarFacturacion | None = None`.
  - **Acción**: importar `Literal` de `typing`; append al final post-F1.6 block; docstring REQ-OPS-042 + D-HU-F1.7-19. — **Validación**: T1+T2+T3+T4 PASS; `extra='forbid'` heredado de `_Base`.

- [x] **T-HU-F1.7-3.3** [GREEN] — Add 4 typed error classes (`IngresoNoEncontradoError`, `SalidaDuplicadaError`, `PlacaNoCoincideConIngresoError`, `TarifaVigenteNoEncontradaError`) (~30 LOC)
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (mismo archivo, append post `SalidaReadForzado`).
  - **Contenido**: cada uno hereda `_Base` con `model_config = ConfigDict(extra="forbid")`; cada uno tiene un campo `error: Literal["..."]` discriminator + campos contextuales:
    - `IngresoNoEncontradoError`: `error: Literal["ingreso_no_encontrado"]`, `uuid_ingreso: uuid_lib.UUID` (404).
    - `SalidaDuplicadaError`: `error: Literal["salida_duplicada"]`, `uuid_ingreso: uuid_lib.UUID` (409).
    - `PlacaNoCoincideConIngresoError`: `error: Literal["placa_no_coincide_con_ingreso"]`, `placa_request: str`, `placa_ingreso: str` (422).
    - `TarifaVigenteNoEncontradaError`: `error: Literal["tarifa_vigente_no_encontrada"]` (422, V5 sin bypass).
  - **Acción**: append al final del archivo; docstring REQ-OPS-043/045/047/051 + D-HU-F1.7-19. — **Validación**: imports sin error; `IngresoNoEncontradoError.model_validate({"error": "wrong_value", "uuid_ingreso": uuid})` raises `ValidationError` (Literal discriminator enforce).

- [x] **T-HU-F1.7-3.4** [GREEN] — Run tests → GREEN
  - **Acción**: ejecutar `uv run pytest backend/tests/unit/test_schemas_salida.py -q`.
  - **Validación**: `4 passed` (T1..T4); no regression en tests pre-existentes (`test_schemas_ingreso.py` F1.6 sigue PASS).
  - **Commit suggestion**: `feat(backend): HU-F1.7 — schemas operacion.py SalidaCreate/ReadForzado + 4 typed errors`.
  - **Exit criteria Phase 3**: T3.1 RED tests; T3.2 + T3.3 schemas; T3.4 tests verde; cumulative ~800 LOC.

### Phase 4 — Handler `create_salida` (RED → GREEN, ~50 LOC net impl + ~400 LOC tests)

- [x] **T-HU-F1.7-4.1** [RED] — Write `tests/unit/test_operacion_salidas.py` con 10 RED tests parametrizados (~400 LOC)
  - **Tests** (mapean design §10 handler 12-step chain):
    - T1: `test_salida_rotacion_exitosa` — happy rotación: POST `{"uuid_ingreso": I, "placa": "ABC123"}` (operator JWT, ctx OK, vigente tarifa, vigente IVA, no subscripcion) → 201 + `SalidaReadForzado{tipo_salida:"ROTACION", forzado_en_creacion:false, motivo_forzado:null, cotizacion_snapshot:{cobrar:true,subtotal,iva,total,...}}`; DB row inserted en `prod.salidas`. REQ-OPS-042/047/049 + V5 tarifa vigente.
    - T2: `test_salida_rotacion_sin_tarifa_vigente` — V5 returns `error:tarifa_no_vigente` without `forzado` → 422 `tarifa_vigente_no_encontrada` (F1.8 KD-3 propagado); no DB row. REQ-OPS-047.
    - T3: `test_salida_rotacion_forzada_con_alerta` — V5 returns `error:tarifa_no_vigente` con `forzado=true` + motivo `[FORZADO: cliente pago en efectivo 2026-09-14]` → 201 + `tipo_salida:"ROTACION"` + alerta `tarifa_vigente_forzado` en `prod.alerta`. REQ-OPS-046/047/050 + KD-FORZADO-01.
    - T4: `test_salida_rotacion_duplicada_409` — second POST same `uuid_ingreso` → 409 `salida_duplicada` (post-0026 partial unique index). REQ-OPS-051.
    - T5: `test_salida_mensualidad_vigente_exitosa` — ingreso con `uuid_subscripcion_cliente` vigente, F1.8 returns `cobrar:false,motivo:mensualidad_vigente` → 201 + `tipo_salida:"MENSUALIDAD"` + `cotizacion_snapshot:None`. REQ-OPS-049.
    - T6: `test_salida_mensualidad_vencida_sin_forzado_422` — `subscripcion_inactiva_o_vencida` sin forzado → 422; no DB row. REQ-OPS-044.
    - T7: `test_salida_mensualidad_vencida_con_forzado_201` — V2 bypassed + motivo → 201 + `tipo_salida:"ROTACION"` (F1.8 finds no subscription at branch → `cobrar:true`) + alerta `subscripcion_vencida_forzado`. REQ-OPS-044/049/050.
    - T8: `test_salida_placa_no_coincide_422` — V3 placa mismatch (Auto vs Moto) → 422 `placa_no_coincide_con_ingreso`. REQ-OPS-045.
    - T9: `test_salida_kd_forzado_prefijo_valido_201` — `forzado=true` + motivo ≥10 chars → bypass activo (covered by T3 if applicable). REQ-OPS-046.
    - T10: `test_salida_kd_forzado_motivo_insuficiente_422` — motivo 9 chars → 422 `motivo_forzado_insuficiente`. REQ-OPS-046.
  - **Patrón F1.3/F1.5/F1.6**: `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-` fixture; real `pg_engine` con `PARKOS_DOCKER_TEST=1`; `pytest.mark.parametrize` para variantes de scenario.
  - **Acción**: parametrizar `pytest.mark.parametrize("test_case", [T1..T10])`; usar fixtures `operator_jwt`, `seed_tipos_vehiculo`, `seed_tarifas_sucursal`, `seed_subscripciones_cliente`, `seed_impuestos_iva`, `seed_ingreso`; assert response shape via `pydantic.SalidaReadForzado.model_validate(response.json())`. — **Archivo**: `backend/tests/unit/test_operacion_salidas.py` (nuevo, ~400 LOC, 10 tests parametrizados). — **Validación**: `ImportError` de `SalidaCreateForzado`/`SalidaReadForzado` (Phase 3 ya resuelve) o `404 Not Found` (handler no registrado en router) o `pydantic.ValidationError` (campo `tipo_salida` faltante en response).

- [x] **T-HU-F1.7-4.2** [GREEN] — Add `create_salida` handler a `api/v1/operacion.py` (~50 LOC net impl, ~200 LOC total handler con docstring + responses)
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modificado, append post-`create_ingreso` lines ~294-510).
  - **Contenido**: handler signature `async def create_salida(payload: SalidaCreateForzado, response: Response, session: AsyncSession = Depends(get_session), ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_ingreso_issuer_dep)) -> SalidaReadForzado`. 12-step chain (D-HU-F1.7-20 strict order):
    - Step 1: KD-3 issuer claims + `no_store = no_store_headers()`.
    - Step 2 (V1): `ingreso = await buscar_ingreso_activo_por_uuid(session, uuid_ingreso=payload.uuid_ingreso); if ingreso is None: raise HTTPException(404, {"error":"ingreso_no_encontrado", "uuid_ingreso":str(payload.uuid_ingreso)}, headers=no_store)`.
    - Step 3 (tenant scope post-V1): `target_sucursal = ingreso.uuid_sucursal; if ctx.issuer_prefix == "operador-" and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid): raise HTTPException(403, {"error":"tenant_scope_violation", "uuid_ingreso":...}, headers=no_store)`.
    - Step 4 (V2): `bypass_reason: str | None = None; if ingreso.uuid_subscripcion_cliente is not None: sub_result = await validar_subscripcion_vigente(session, uuid_subscripcion_cliente=ingreso.uuid_subscripcion_cliente, forzado=payload.forzado); if not sub_result.vigente: if not payload.forzado: raise HTTPException(422, {"error":"subscripcion_inactiva_o_vencida"}, headers=no_store); bypass_reason = "subscripcion_vencida"`.
    - Step 5 (V3): `if payload.placa is not None: tipo_req = await detectar_tipo_vehiculo(session, payload.placa); tipo_ing = await detectar_tipo_vehiculo(session, ingreso.placa or ""); if tipo_req != tipo_ing: raise HTTPException(422, {"error":"placa_no_coincide_con_ingreso", "placa_request":payload.placa, "placa_ingreso":ingreso.placa}, headers=no_store)`.
    - Step 6 (V4 KD-FORZADO-01 verbatim reuse): `motivo = validar_kd_forzado(payload.observaciones, payload.forzado); if motivo is not None and bypass_reason is None: bypass_reason = "forzado"`.
    - **Step 7 (V5) CRITICAL — INVOKE `cotizar_para_salida` BEFORE `session.flush()` to hold FOR SHARE lock continuous across INSERT**: `try: cotizacion = await cotizar_para_salida(session, uuid_ingreso=payload.uuid_ingreso); except TarifaNoVigente: if not bypass_reason: raise HTTPException(422, {"error":"tarifa_vigente_no_encontrada"}, headers=no_store); bypass_reason = "tarifa_no_vigente"; cotizacion = {"cobrar":True}; except IVANoConfigurado: raise HTTPException(500, {"error":"iva_no_configurado"}, headers=no_store)`. Derivar `tipo_salida: Literal["MENSUALIDAD", "ROTACION"] = "MENSUALIDAD" if cotizacion.get("cobrar") is False else "ROTACION"`.
    - Step 8 (INSERT): `new_attrs = {"uuid_sucursal":target_sucursal, "uuid_ingreso":payload.uuid_ingreso, "fecha_salida":datetime.now(UTC).replace(tzinfo=None), "fecha_retencion_hasta":date.today() + relativedelta(years=2)}; try: new_row = await crear_salida_evento(session, actor_uuid=ctx.actor_uuid, new_attrs=new_attrs); except SalidaDuplicada: raise HTTPException(409, {"error":"salida_duplicada", "uuid_ingreso":...}, headers=no_store)`.
    - Step 9 (alertas same-TX + single commit): `if bypass_reason == "subscripcion_vencida": await insertar_alerta_salida_forzado(session, uuid_sucursal=target_sucursal, uuid_salida=new_row.uuid, actor_uuid=ctx.actor_uuid, motivo=motivo or "(sin motivo)", tipo_alerta="subscripcion_vencida_forzado"); elif bypass_reason == "tarifa_no_vigente": await insertar_alerta_salida_forzado(..., tipo_alerta="tarifa_vigente_forzado"); await session.commit()` (KD-S7 lock release).
    - Step 10: derivación `tipo_salida` (ya en Step 7; documented for AST walk literal).
    - Step 11 (response): `apply_no_store_header(response); await session.refresh(new_row); base = SalidaRead.model_validate(new_row).model_dump(); return SalidaReadForzado(**base, tipo_salida=tipo_salida, forzado_en_creacion=bypass_reason is not None, motivo_forzado=motivo if bypass_reason else None, cotizacion_snapshot=CotizarFacturacion.model_validate(cotizacion) if tipo_salida == "ROTACION" else None)`.
    - Step 12: return 201.
  - **CRITICAL hard rule (KD-S7)**: Step 7 (`cotizar_para_salida`) MUST execute BEFORE Step 8 (`crear_salida_evento`) AND inside the same transaction. The FOR SHARE lock acquired in Step 7 is held through Step 8 INSERT and Step 9 alerta INSERT until the single `session.commit()` in Step 9. NO `session.commit()` between Step 7 and Step 9; NO sub-transactions; NO `SAVEPOINT`. The `crear_salida_evento` internal `session.flush()` is OK (it does NOT release the FOR SHARE lock).
  - **Acción**: append imports (`from ..repo.salida import (buscar_ingreso_activo_por_uuid, cotizar_para_salida, crear_salida_evento, insertar_alerta_salida_forzado, SalidaDuplicada)`, `from ..repo.subscripcion_activa import validar_subscripcion_vigente`, `from ..repo.placa import detectar_tipo_vehiculo`, `from ..repo.ingreso import validar_kd_forzado`, `from ..repo.cotizacion import (TarifaNoVigente, IVANoConfigurado)`, `from ..schemas.operacion import (SalidaCreateForzado, SalidaReadForzado, SalidaRead, CotizarFacturacion)`); append `@router.post("/salidas", response_model=SalidaReadForzado, status_code=201, ...)` decorator con `responses={400:..., 403:..., 404:..., 409:..., 422:..., 500:...}`; append handler function body per D-HU-F1.7-20; docstring REQ-OPS-042..052 + D-HU-F1.7-20 + KD-S7 lock continuity. — **Validación**: T4.1 10 tests PASS; `git diff api/v1/__init__.py` vacío; `git diff api/v1/router_factory.py` vacío (CI gate `factory_intact`); `git diff api/deps.py` vacío; `git diff auth/tenancy.py` vacío (CI gate `auth_tenancy_intact`).

- [x] **T-HU-F1.7-4.3** [GREEN] — Run tests → GREEN
  - **Acción**: ejecutar `uv run pytest backend/tests/unit/test_operacion_salidas.py -q` con `PARKOS_DOCKER_TEST=1`.
  - **Validación**: `10 passed` (T1..T10); response shapes validados vía `pydantic.SalidaReadForzado.model_validate(response.json())`; no regression en tests F1.6 pre-existentes (`test_operacion_ingresos_validaciones.py` sigue PASS).
  - **Commit suggestion**: `feat(backend): HU-F1.7 — POST /operacion/salidas handler with 12-step chain (KD-FORZADO reuse F1.6 + lock continuity F1.8)`.
  - **Exit criteria Phase 4**: T4.1 RED tests written; T4.2 handler; T4.3 tests verde; cumulative ~1400 LOC (incluyendo 400 LOC tests).

### Phase 5 — Test files consolidation (RED → GREEN, ~700 LOC tests)

- [x] **T-HU-F1.7-5.1** [GREEN] — `tests/unit/test_operacion_salidas.py` (~400 LOC, 10 tests parametrizados — consolidado de T4.1)
  - **Archivo**: `backend/tests/unit/test_operacion_salidas.py` (nuevo).
  - **Contenido**: 10 tests parametrizados vía `pytest.mark.parametrize("test_case", [T1..T10])` cubriendo rotación (T1..T4), mensualidad (T5..T8), KD-FORZADO (T9..T10); helpers `_build_ingreso_test_case`, `_assert_response_shape`, `_assert_alerta_inserted`; fixtures `operator_jwt`, `seed_tipos_vehiculo`, `seed_tarifas_sucursal`, `seed_subscripciones_cliente`, `seed_impuestos_iva`, `seed_ingreso`.
  - **Acción**: parametrized; pre-Phase 4 RED imports fail; post-Phase 4 GREEN all 10 PASS. — **Validación**: `10 passed` con `PARKOS_DOCKER_TEST=1`.

- [x] **T-HU-F1.7-5.2** [GREEN] — `tests/unit/test_operacion_salidas_kd_forzado.py` (~80 LOC, 2 tests)
  - **Tests**:
    - T1: `test_validar_kd_forzado_reuse_desde_repo_ingreso_para_salida` — direct unit test sobre `repo.ingreso.validar_kd_forzado` reusado en handler salida path; valida que las 3 422 discriminators (`motivo_forzado_requerido`, `forzado_contradiccion`, `motivo_forzado_insuficiente`) siguen disparando correctamente desde el contexto salida (no duplica tests F1.6, solo verifica la integración).
    - T2: `test_kd_forzado_no_se_duplica_en_repo_salida` — verifica que `repo/salida.py` NO define `validar_kd_forzado` (single source of truth via re-exports F1.6 verbatim reuse); `import parkos_core.repo.salida` no expone la función (DRY contract).
  - **Patrón F1.6**: pure helper tests, sin HTTP, sin DB.
  - **Acción**: importar `validar_kd_forzado` from `parkos_core.repo.ingreso`; `pytest.raises(HTTPException)` con match de `detail`. — **Archivo**: `backend/tests/unit/test_operacion_salidas_kd_forzado.py` (nuevo, ~80 LOC, 2 tests). — **Validación**: `2 passed` sin DB.

- [x] **T-HU-F1.7-5.3** [GREEN] — `tests/integration/test_salida_create_db.py` (~250 LOC, 3 DB tests — consolidado de T2.1)
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_insert_salida_con_alerta_forzado_atomico` — seed `prod.ingreso(X)`, `prod.tarifas_sucursal` vigente, `prod.impuestos.IVA`; simular `forzado=true` + motivo; assert `prod.salidas` row + `prod.alerta` row inserted en single commit (R5 verification).
    - T2: `test_partial_unique_index_emite_409` — seed `prod.ingreso(X)`, `prod.salidas(X)` already (non-anulada); second attempt to insert `prod.salidas(X)` raises `IntegrityError` con substring `"one_exit_per_ingreso"`; `repo.salida.crear_salida_evento` mapea a `SalidaDuplicada` (R4 verification, post-0026).
    - T3: `test_iva_no_sembrado_retorna_500` — `DELETE FROM prod.impuestos WHERE codigo='IVA'` (cleanup); attempt salida with vigente tarifa → `prod.calcular_cotizacion` returns `error:iva_no_configurado`; `cotizar_para_salida` raises `IVANoConfigurado`; handler maps to 500. Cleanup: re-insert IVA row post-test.
  - **Acción**: usar `pg_engine` fixture; sembrar via SQL directo; asserts sobre `prod.salidas.count(*)`, `prod.alerta.datos_nuevos`. — **Archivo**: `backend/tests/integration/test_salida_create_db.py` (nuevo, ~250 LOC, 3 tests). — **Validación**: `3 passed` con `PARKOS_DOCKER_TEST=1`.

- [x] **T-HU-F1.7-5.4** [GREEN] — `tests/integration/test_migration_0026_idempotent.py` (~80 LOC, 1 test — consolidado de T1.2)
  - **Tests**: `test_0026_re_apply_ok` + `test_iva_row_present_post_migration` (cubierto en T1.2).
  - **Acción**: ejecutar `alembic upgrade head` 2 veces, asserts sobre `prod.impuestos`, `prod.alert_types`, `pg_indexes`. — **Validación**: `2 passed` con `PARKOS_DOCKER_TEST=1`.

- [x] **T-HU-F1.7-5.5** [VERIFICATION] — Run `uv run pytest -q backend/tests/` completo (skip Docker-gated SKIPs)
  - **Acción**: ejecutar `uv run pytest -q backend/tests/ --ignore=backend/tests/integration` (unit + static); luego `PARKOS_DOCKER_TEST=1 uv run pytest -q backend/tests/integration/` (integration).
  - **Validación**: suite verde, 0 regresiones en F1.5/F1.6/F1.8 pre-existentes; F1.7 contributes ~10 unit + 3 integration + 1 idempotency migration + 2 AST walks = ~16 nuevos tests verdes; cumulative test count documented.
  - **Commit suggestion**: `test(backend): HU-F1.7 — unit tests for create_salida + KD-FORZADO + migration idempotency + integration DB`.
  - **Exit criteria Phase 5**: T5.1 + T5.2 + T5.3 + T5.4 + T5.5 verde; cumulative ~2100 LOC.

### Phase 6 — AST walk invariants (RED → GREEN, ~200 LOC)

- [x] **T-HU-F1.7-6.1** [GREEN] — `tests/static/test_salida_handler_step_order.py` (~100 LOC, 1 AST walk)
  - **Test**: `test_create_salida_handler_invoca_helpers_en_orden_correcto` — AST-walk `api/v1/operacion.py::create_salida` body usando `ast.parse` + recursion via `iter_child_nodes` (NOT `ast.walk`, que es BFS — `iter_child_nodes` es DFS que preserva source order); walk statements, collect function/method call names en source order; assert sequence contiene literal ordered pattern: `buscar_ingreso_activo_por_uuid` → `validar_subscripcion_vigente` → `detectar_tipo_vehiculo` (×2 calls — payload.placa AND ingreso.placa) → `validar_kd_forzado` → `cotizar_para_salida` → `crear_salida_evento` → `insertar_alerta_salida_forzado`. R7 invariante — CI gate contra future-dev reordering.
  - **Patrón F1.3/F1.6 precedent (`test_kd_forzado_in_handler.py`)**: usar `ast.parse` + `iter_child_nodes` + `ast.FunctionDef` + `ast.Call`; extraer `call.func.id` o `call.func.attr` (cubrir tanto calls directos como via `repo.X.Y`).
  - **Acción**: importar `ast`; `path = "backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py"`; `tree = ast.parse(open(path).read())`; localizar `create_salida` via `ast.walk` + `ast.FunctionDef.name == 'create_salida'`; `for node in ast.walk(create_salida): if isinstance(node, ast.Call): collect_call_names.append(get_func_name(node))`; assert subsequence match con helpers list. — **Archivo**: `backend/tests/static/test_salida_handler_step_order.py` (nuevo, ~100 LOC, 1 test). — **Validación**: PASS (handler creado en T4.2 invoca helpers en orden correcto); FAIL si reorder futuro.

- [x] **T-HU-F1.7-6.2** [GREEN] — `tests/static/test_no_write_after_salida_insert.py` (~100 LOC, 1 AST walk)
  - **Tests**:
    - T1: `test_crear_salida_evento_rechaza_update_delete_truncate` — AST-walk `repo/salida.py::crear_salida_evento` body; rechazar `UPDATE | DELETE | TRUNCATE | MERGE | FOR UPDATE | FOR SHARE` literals (case-insensitive, fuera de strings/comments) AFTER the `INSERT` statement location. Locks DEC-SAL-01 insert-only contract sobre `prod.salidas` post-creación (R-A3 analog F1.6).
    - T2: `test_handler_new_attrs_no_contiene_tipo_salida_monto_columns` — AST-walk `api/v1/operacion.py::create_salida` body; localizar `new_attrs = {...}` dict literal; assert que NO contiene keys `tipo_salida`, `valor`, `subtotal`, `iva`, `total`, `cobrar`, `forzado`, `motivo_forzado` (DEC-SUC-21-NEW + DEC-SUC-23 + KD-FORZADO-01 verification — R6 mitigation).
  - **Patrón F1.3/F1.5/F1.6/F1.8 precedents (`test_no_write_in_ocupacion.py`, `test_no_write_after_insert.py`)**: usar `ast.parse` + `ast.walk`; tokenizar identifiers + strings; rechazar tokens case-insensitive que contengan `UPDATE`, `DELETE`, `TRUNCATE`, `MERGE`, `FOR UPDATE`, `FOR SHARE`; reportar primer match ofensivo con línea.
  - **Acción**: `path = "backend/packages/parkos_core/src/parkos_core/repo/salida.py"`; `tree = ast.parse(open(path).read())`; localizar `crear_salida_evento` via `ast.walk` + `ast.FunctionDef.name == 'crear_salida_evento'`; walk `ast.Assign` targets / `ast.Dict` keys; reportar violaciones. — **Archivo**: `backend/tests/static/test_no_write_after_salida_insert.py` (nuevo, ~100 LOC, 2 tests). — **Validación**: PASS (handler + repo creados en Phase 2/4 no contienen write verbs ni monto columns en `new_attrs`); FAIL si futuro dev introduce violation.

- [x] **T-HU-F1.7-6.3** [VERIFICATION] — Run both AST walks pass (no errors)
  - **Acción**: ejecutar `uv run pytest backend/tests/static/test_salida_handler_step_order.py backend/tests/static/test_no_write_after_salida_insert.py -q`.
  - **Validación**: `3 passed` (1 + 2 tests); no errors.
  - **Commit suggestion**: `test(backend): HU-F1.7 — AST walks handler step-order + no-write-after-insert (lock invariants)`.
  - **Exit criteria Phase 6**: T6.1 + T6.2 + T6.3 verde; cumulative ~2300 LOC.

### Phase 7 — CI gates verification + housekeeping (~10 LOC, no net production change)

- [x] **T-HU-F1.7-7.1** [VERIFICATION] — CI gate: `git diff api/v1/__init__.py` MUST be empty (router factory intact)
  - **Acción**: ejecutar `git diff backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` (F1.6 precedent — router ya está montado en línea 143 con `r.include_router(operacion.router)`).
  - **Validación**: output vacío (0 líneas cambiadas). Si drift detectado → revert el archivo accidentalmente modificado; NO chained edits.

- [x] **T-HU-F1.7-7.2** [VERIFICATION] — CI gate: `git diff backend/packages/parkos_core/src/parkos_core/router_factory.py` MUST be empty
  - **Acción**: ejecutar `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` (F1.1 commit `f7cb37a` intact).
  - **Validación**: output vacío. Si drift detectado → revert.

- [x] **T-HU-F1.7-7.3** [VERIFICATION] — CI gate: `git diff backend/packages/parkos_core/src/parkos_core/repo/event.py` MUST be empty
  - **Acción**: ejecutar `git diff backend/packages/parkos_core/src/parkos_core/repo/event.py` (F1.6 `event_helper_intact` precedent).
  - **Validación**: output vacío. Si drift detectado → revert.

- [x] **T-HU-F1.7-7.4** [VERIFICATION] — Verify `_ingreso_issuer_dep` import is not duplicated in `operacion.py`
  - **Acción**: ejecutar `rg -n "_ingreso_issuer_dep" backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` — debe aparecer exactamente 2 veces (1 definition + 1 usage en `create_ingreso` línea 137 + 1 usage en `create_salida` línea 611 = 3 total).
  - **Validación**: 3 matches exactos, no duplicates; if > 3 → housekeeping commit removes redundant import. Si housekeeping necesario: commit `chore(backend): HU-F1.7 — housekeeping de duplicate _ingreso_issuer_dep import` (~2 LOC removal).
  - **Exit criteria Phase 7**: 4 CI gates verde; 0 housekeeping drift.

### Phase 8 — OpenSpec archive (separate commit, ~open artifacts)

- [x] **T-HU-F1.7-8.1** [VERIFICATION] — Verify all 4 artifacts (exploration, proposal, spec, design, tasks) presentes en `openspec/changes/hu-f1-7-salidas/`
  - **Acción**: ejecutar `ls -la openspec/changes/hu-f1-7-salidas/` — debe mostrar `exploration.md`, `proposal.md`, `design.md`, `tasks.md` (este archivo), `specs/operational/spec.md`.
  - **Validación**: 5 archivos presentes (4 inputs + 1 tasks output). Si falta alguno → bloqueante para archive phase.

- [x] **T-HU-F1.7-8.2** [VERIFICATION] — Verify `verify-report.md` will be produced by `sdd-verify` phase next (NOT in this phase)
  - **Acción**: confirmar que `sdd-verify` phase es el siguiente (per orchestrator workflow); tasks phase NO produce `verify-report.md`.
  - **Validación**: tasks phase scope cerrado; verify-report será producido en `sdd-verify` phase post-apply.

- [x] **T-HU-F1.7-8.3** [ENGRAM] — Save Engram observation for tasks phase
  - **Acción**: ejecutar `mem_save(title="sdd/HU-F1.7-salidas/tasks", topic_key="sdd/hu-f1-7-salidas/tasks", type="architecture", project="easypuinto-parkos-software", capture_prompt=false, content="22 tasks planned across 8 phases for HU-F1.7 POST /operacion/salidas. ~690 LOC impl + ~1610 LOC tests = ~2300 LOC cumulative workload (apply deltas ~800 LOC net). Phases: 0 preflight (3 verifications) → 1 migration 0026 (4 ops: preflight + IVA seed + 2 alert_types + partial unique index one_exit_per_ingreso) → 2 ORM Salida + repo/salida (4 helpers + SalidaDuplicada) + repo/impuestos → 3 schemas (SalidaCreateForzado + SalidaReadForzado + 4 typed errors) → 4 handler create_salida 12-step chain (KD-FORZADO verbatim reuse F1.6 + lock continuity F1.8) → 5 tests consolidation (10 unit + 2 KD + 3 integration + 1 idempotency + 1 AST walk verification) → 6 AST walks (step order via iter_child_nodes DFS + no-write-after-insert + no-tipo_salida-column verification) → 7 CI gates (factory_intact + event_helper_intact + auth_tenancy_intact + no-duplicate-import) → 8 archive (verify artifacts + defer verify-report to sdd-verify phase + Engram save). Hard rules: DEC-MONO-01 single handler; DEC-SUC-21-NEW tipo_salida never persisted; DEC-SAL-01 salida append-only; DEC-IMP-01 IVA seeded inline; DEC-FORZADO-01 verbatim reuse; KD-S7 lock continuity single TX single commit; DEC-IDEM-01 Idempotency-Key header not correlacion_id. Per-commit <800 LOC; 2-commit split (apply-código ≤490 LOC + tests+verification ≤700 LOC). Single PR to origin/dev (matches F1.5/F1.6 precedent).")`.
  - **Validación**: engram save success; topic_key `sdd/hu-f1-7-salidas/tasks` reusable para upserts.
  - **Commit suggestion**: `chore(openspec): HU-F1.7 — archivar change folder tras tasks completion` (separate archive commit per F1.6 precedent commit `2a2cbd2`).
  - **Exit criteria Phase 8**: 5 artifacts presentes; verify-report deferral documented; Engram observation saved; tasks phase complete.

## Cross-phase constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` ni `FOR UPDATE|SHARE` en `create_salida` handler — AST walk `test_salida_handler_step_order.py` (T6.1) lo enforza en CI sobre `repo/salida.py::crear_salida_evento` y `api/v1/operacion.py::create_salida`.
- NO `tipo_salida`, `valor`, `subtotal`, `iva`, `total`, `cobrar`, `forzado`, `motivo_forzado` keys en `new_attrs` dict literal del handler — AST walk `test_no_write_after_salida_insert.py` T2 (T6.2) lo enforza (DEC-SUC-21-NEW + DEC-SUC-23 + KD-FORZADO-01 verification, R6 mitigation).
- NO `Co-authored-by:` ni trailers AI en commits; conventional commits, español neutral.
- NO SQLite en tests — `pg_engine` real o `testcontainers[postgres]` (precedente F1.4/F1.5/F1.6).
- NO modificación de `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate (Phase 7 T7.2).
- NO modificación de `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate cross-cutting (no aplica a F1.7).
- NO modificación de `api/v1/__init__.py` — el router ya estaba montado (Phase 7 T7.1).
- NO modificación de `api/deps.py` ni `auth/tenancy.py` — reusan KD-3 chain + errores tipados intactos.
- NO modificación de `repo/event.py` — `event_helper_intact` CI gate (Phase 7 T7.3).
- NO modificación de `repo/cotizacion.py` (F1.8) — `cotizar_ingreso` reusado verbatim para V5 thin wrapper.
- NO modificación de `repo/ingreso.py` — `validar_kd_forzado` reusado verbatim para V4 (REQ-OPS-046).
- NO modificación de `repo/subscripcion_activa.py` (F1.6) — `validar_subscripcion_vigente` reusado verbatim para V2 (REQ-OPS-044).
- NO modificación de `repo/placa.py` (F1.6) — `detectar_tipo_vehiculo` reusado verbatim para V3 (REQ-OPS-045).
- NO `correlacion_id` en el body (DEC-IDEM-01) — header `Idempotency-Key` via PR2 middleware.
- NO lock pesimista (`SELECT … FOR UPDATE/SHARE`) sobre `prod.ingreso` / `prod.subscripciones_cliente` desde el endpoint (KD-V4, KD-S7 solo lock sobre `tarifas_sucursal` via F1.8 PL/pgSQL).
- NO `forzado`, `tipo_salida`, `motivo`, ni monto columns en `prod.salidas` (DEC-SAL-01 + DEC-SUC-21-NEW + DEC-SUC-23 + KD-FORZADO-01) — derivado server-side, devuelto en respuesta, NUNCA persistido.
- Header `Cache-Control: no-store` en TODA respuesta 2xx/4xx/5xx del endpoint (consistente con F1.3/F1.5/F1.6/F1.8 precedents via `no_store_headers()` helper).
- Discriminadores de error estables: `missing_sucursal_context` (400), `tenant_scope_violation` (403 operador), `ingreso_no_encontrado` (404 V1 unified), `salida_duplicada` (409 partial unique index), `placa_no_coincide_con_ingreso` (422 V3), `motivo_forzado_requerido` (422 KD-FORZADO-01), `forzado_contradiccion` (422 KD-FORZADO-01), `motivo_forzado_insuficiente` (422 KD-FORZADO-01), `subscripcion_inactiva_o_vencida` (422 V2), `tarifa_vigente_no_encontrada` (422 V5), `iva_no_configurado` (500 KD-IVA post-0026: never).
- Precedencia de errores (D-HU-F1.7-20): KD-3 (400/403) > V1 (404 ingreso) > tenant scope (403) > V2 (422 sub) > V3 (422 placa) > V4 (422 KD-FORZADO) > V5 (422 tarifa) > INSERT (409 dup) > 201.
- Migration `0026` debe usar `INSERT ... ON CONFLICT DO NOTHING` (alert_types_inmutable trigger bloquea UPDATE/DELETE para non-superuser); downgrade corre como superuser en alembic.
- `datos_nuevos` JSONB column (post-0025 F1.6) carries motivo + uuid_salida para auditoría (R-A2 F1.6 mitigation, replicated for salidas with `uuid_salida` instead of `uuid_ingreso`).
- `prod.alerta.datos_nuevos` parseable via `json.loads()` en tests integración (T5.3 T1).
- **CRITICAL** Orden de invocaciones del handler estricto (D-HU-F1.7-20): KD-3 → V1 → tenant scope → V2 → V3 → V4 → V5 → INSERT → alerta (same TX) → derivar tipo_salida → 201. AST walk (T6.1) verifica literal order.
- **CRITICAL** Step 7 (`cotizar_para_salida`) MUST execute BEFORE Step 8 (`crear_salida_evento`) AND inside the same transaction (KD-S7 lock continuity). The FOR SHARE lock acquired in Step 7 is held through Step 8 INSERT and Step 9 alerta INSERT until the single `session.commit()` in Step 9. NO `session.commit()` between Step 7 and Step 9; NO sub-transactions; NO `SAVEPOINT`.
- **CRITICAL** `bypass_reason` discriminator: `None` → `"forzado"` (after V4 KD-FORZADO-01 pass) → `"subscripcion_vencida"` (after V2 bypass) → `"tarifa_no_vigente"` (after V5 bypass). Alerta INSERT solo si `bypass_reason in {"subscripcion_vencida", "tarifa_no_vigente"}` (R2 mitigation).
- Tope por commit: <800 LOC. Apply-código ≤490 LOC net (commit 1), tests+verification ≤700 LOC (commit 2), archive commit (commit 3).
- Mensajes conventional commit; cuerpo técnico en español neutral.

## Acceptance Gates

- TDD strict: RED primero, GREEN mínimo, REFACTOR último. Phase 1 explicitly notes this discipline.
- 22 tasks completados en orden: T0.1..T0.3 → T1.1..T1.4 → T2.1..T2.5 → T3.1..T3.4 → T4.1..T4.3 → T5.1..T5.5 → T6.1..T6.3 → T7.1..T7.4 → T8.1..T8.3.
- Conventional commits atómicos (3 commits en 1 PR): commit 1 `feat(backend): HU-F1.7 — MIGRATION 0026 + ORM Salida + repo/salida + repo/impuestos + schemas + handler create_salida (KD-FORZADO reuse F1.6 + lock continuity F1.8)` (~690 LOC impl ≤800 OK); commit 2 `test(backend): HU-F1.7 — unit + integration + AST walk tests for create_salida (defense in depth 5-layer)` (~1610 LOC tests); commit 3 `chore(openspec): HU-F1.7 — archivar change folder tras tasks completion` (archive move). Sin `Co-authored-by:`, sin trailers IA.
- Tests pasan contra DB real con `PARKOS_DOCKER_TEST=1`: 10 HTTP unit (T4.1/T5.1) + 2 KD-FORZADO unit (T5.2) + 4 schemas unit (T3.1) + 3 DB integration (T2.1/T5.3) + 2 migration idempotency (T1.2/T5.4) + 1 AST walk step order (T6.1) + 2 AST walk no-write (T6.2) = **~24 tests nuevos en 9 archivos**.
- ruff + mypy --strict clean sobre los 8 archivos nuevos/modificados (1 migration + 4 NEW repo/ORM + 2 MODIFIED handler/schemas + 6 NEW tests + 2 NEW AST walks = 15 archivos total menos overlap).
- 4 CI gates verdes (Phase 7): `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`.
- 0 regresiones introducidas por F1.7; las fallas preexistentes documentadas en baseline F1.6 se mantienen sin nuevos archivos fallando.
- REQ-OPS-042..052 traceability verificada: cada REQ tiene ≥1 RED test que la prueba (T4.1 + T5.3 mapping).
- Threat matrix §10 verificada: T1 SQL injection → V3 regex/placa rechaza; T2 cross-tenant → KD-3 chain + tenant scope post-V1; T3 stale client UUID → V1 server overwrite (ingreso); T4 motivo corto → V4 KD-FORZADO 422; T5 IVA no configurado → 500 KD-IVA (post-0026: never); T6 alerta huérfana → same TX single commit (KD-S7); T7 future-dev reorder → AST walk step order (T6.1); T8 pgcode leak → typed Pydantic errors (SalidaDuplicada → 409); T9 tipo_salida injection → extra='forbid' (T3.1 T1); T10 concurrent salidas → partial unique index one_exit_per_ingreso → 409 (T5.3 T2).
- Architecture risks §13 (R1..R9) verificadas: R1 KD-IVA → MIGRATION 0026 Op 2 inline-seed + pre-flight abort; R2 ORM gap → T2.2 model + T2.1 DB test; R3 lock continuity → KD-S7 single TX + AST walk (T6.1); R4 TOCTOU race → partial unique index (T5.3 T2); R5 alerta huérfana → same TX (T5.3 T1); R6 DEC-SUC-21-NEW → AST walk no-tipo_salida (T6.2 T2); R7 strict order → AST walk step order (T6.1); R8 `impuestos_inmutable` → T1.4 downgrade +1 verification; R9 placa opcional → V3 server trust uuid (T4.1 T8).

## Out of Scope Tasks

- Visibilidad cross-branch global para `admin-`. Sale del scope: KD-3 acota a `claims["sucursales_permitidas"]`.
- Push de `tipo_salida` vía websocket / SSE. Sale del scope: cliente recibe `tipo_salida` en response del POST; no streaming necesario.
- Workflow de anulación (`prod.anulaciones(tipo_anulable='salida')` workflow para revertir salida post-creación). DEC-SAL-01 delega a Fase 7+; el partial unique index `one_exit_per_ingreso` permite una nueva salida si la anterior fue anulada (`NOT EXISTS` sobre `anulaciones WHERE estado='ejecutada'`).
- `correlacion_id` en el payload. DEC-IDEM-01 delega idempotencia al header `Idempotency-Key` (PR2 middleware).
- Lock pesimista (`SELECT … FOR UPDATE/SHARE`) sobre `prod.ingreso` / `prod.subscripciones_cliente` desde el endpoint (KD-V4, KD-S7 solo lock sobre `tarifas_sucursal` via F1.8 PL/pgSQL).
- View `V_SALIDA_TIPO` para query directa de `tipo_salida`. Sale del scope: cliente deriva desde response field; future HU puede crear la view si necesario.
- Numeración de FE (factura electrónica) integration. Fase 8 (HU-F1.10); F1.7 solo persiste el lifecycle event, no la factura.
- Versión de UI cliente (Fase 2 frontend — `web_sucursal/src/lib/validation/salida.ts` debe desactivar pre-classification de `tipo_salida` cuando este endpoint esté en producción). F1.7 **NO** modifica el cliente; cleanup post-archive.
- Permisos RBAC diferenciados para `forzado` (e.g. "solo admin-"). D-HU-F1.7-18 acepta ambos `operador-` y `admin-` para MVP; alert + audit log detectan abuse.
- Alertas adicionales (`placa_no_coincide_forzado`, `subscripcion_sin_vehiculo`). Solo se insertan `subscripcion_vencida_forzado` y `tarifa_vigente_forzado` (KD-S12 + R2 mitigation); otras alertas son operacionales y salen del scope.
- Métricas / observabilidad del handler (contador `forzado=true`, latencia p99). Alineado con HU-F1.X de observabilidad (futuro).
- Cleanup del cliente (`web_sucursal/src/lib/validation/salida.ts` pre-classification de `tipo_salida`). F1.7 delivers server-side enforcement; client cleanup post-archive.
- Auto-cleanup de huérfanos. Owner decide manualmente.
- Aplicar el mismo patrón bi-temporal canónico a otras tablas `[V]`. Sale del scope de F1.7 (ya reusado via `bitemporal_vigente_predicate` F1.4 en V5).
- Circuit breaker / retry budget sobre alerta INSERT. Sale del scope: FK commit ordering garantiza no huérfanas (R5 mitigation via single `session.commit()`).
- Migración nacional de formatos de placa (e.g. Mercosur 2027). KD-V2 hardcoded para MVP (precedente F1.6).

## References

- `exploration.md`, `proposal.md`, `specs/operational/spec.md`, `design.md` en `openspec/changes/hu-f1-7-salidas/`.
- Precedente F1.6: `openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/tasks.md` (23 tasks T-HU-F1.6-1..23, KD-FORZADO-01 verbatim reuse + AST walk + pre-flight pattern + 11-step handler chain, commit `21097c8`).
- Precedente F1.8: `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/` (PL/pgSQL VOLATILE `calcular_cotizacion` + KD-1 FOR SHARE lock continuity + KD-IVA resolver recipe, commit `a3d0c39`).
- Precedente F1.5: `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/tasks.md` (18 tasks T-HU-F1.5-1..18, MV + KD-7 pre-flight + AST walk pattern, commit `fc72adb`).
- Precedente F1.4: `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/tasks.md` (8 tasks T-HU-F1.4-1..9, bi-temporal predicate + helper-pure pattern, commit `467b4f0`).
- Precedente F1.3: `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/tasks.md` (13 tasks T-HU-F1.3-1..13, partial unique index `unique_active_sesion_per_user` + custom handler + AST walk, commit `ca3f9bf`).
- Precedente F1.2: `openspec/changes/archive/2026-09-14-hu-f1-2-login-jwt/tasks.md` (TenantContext extraction + auth dependency pattern).
- `modelo_datos_er.mmd` § `prod.salidas` `[A]` (761-777), `prod.ingreso` `[L-E]` (577-596), `prod.impuestos` `[V]` (187-207), `prod.tarifas_sucursal` `[V]` (406-426), `prod.subscripciones_cliente` `[V]` (496-518), `prod.subscripcion_vehiculos` `[V]` (538-557), `prod.vehiculos` `[V]` (519-537), `prod.alert_types` `[V]` (post-0013), `prod.alerta` `[L-W]` (952-974), `prod.anulaciones` `[V]` `[L-W]`.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` — router custom línea 84, `_ingreso_issuer_dep` línea 86, `create_ingreso` líneas 132-294 (F1.6 11-step), `create_salida` líneas ~296-510 (F1.7 NEW 12-step).
- `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` — `validar_kd_forzado` reusado verbatim para V4 (REQ-OPS-046, F1.6 intact).
- `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py` — `validar_subscripcion_vigente` reusado verbatim para V2 (REQ-OPS-044, F1.6 intact).
- `backend/packages/parkos_core/src/parkos_core/repo/placa.py` — `detectar_tipo_vehiculo` reusado verbatim para V3 (REQ-OPS-045, F1.6 intact).
- `backend/packages/parkos_core/src/parkos_core/repo/cotizacion.py` — `cotizar_ingreso` reusado verbatim para V5 thin wrapper (REQ-OPS-047, F1.8 intact).
- `backend/packages/parkos_core/src/parkos_core/repo/alerta.py` — `insertar_alerta_forzado` pattern; F1.7 crea `insertar_alerta_salida_forzado` con `datos_nuevos` shape carrying `uuid_salida` instead of `uuid_ingreso` (REQ-OPS-050).
- `backend/packages/parkos_core/migrations/versions/0022_create_calcular_cotizacion.py` — F1.8 PL/pgSQL `prod.calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb VOLATILE` con `SELECT … FOR SHARE` sobre `tarifas_sucursal` (KD-1 invariant).
- `backend/packages/parkos_core/migrations/versions/0025_add_alerta_datos_nuevos_and_alert_type.py` — F1.6 alert column + alert_type seed; MIGRATION 0026 stacks on top via `down_revision = "0025_alerta_datos_nuevos"`.
- `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` — `alert_types_inmutable` BEFORE UPDATE/DELETE trigger (líneas 132-147); `rol_app` es INSERT-only; MIGRATION 0026 Op 3 uses `INSERT ... ON CONFLICT DO NOTHING` to idempotently add `subscripcion_vencida_forzado` y `tarifa_vigente_forzado`.
- `backend/packages/parkos_core/migrations/versions/0023_unique_active_sesion_per_user.py` — F1.3 partial unique index `unique_active_sesion_per_user`; MIGRATION 0026 Op 4 mirrors pattern for `one_exit_per_ingreso` on `prod.salidas`.
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` — `TenantContext` + `get_tenant_ctx` + errores tipados `TenantScopeViolation` (líneas 60-65) + `SucursalNotPermitted` (115-131). Intact.
- `backend/packages/parkos_core/src/parkos_core/api/deps.py` — `get_tenant_ctx` + `requires_issuer` + `_ingreso_issuer_dep`. Intact.
- `backend/packages/parkos_core/src/parkos_core/base.py` — `LifecycleEventBase` con audit + sync mixins; `models/L_S/salida.py::Salida` hereda de esta base.
- `openspec/specs/operations/spec.md` — agrega REQ-OPS-042..052 (11 requirements nuevos) + entrada en `## Modified Capabilities`. Sin cambio sobre REQ-OPS-001..041.
- `plan.md` lines 798-841 — HU-F1.7 budget (220 LOC), DEC-SUC-21-NEW (tipo_salida nunca columna), DEC-SUC-23 (sin monto en salidas), DEC-MONO-01 (single handler consolidation), KD-IVA inline-seed (F1.8 blocker resolution).
- `modelo_datos_er.mmd` líneas 761-777 — `prod.salidas` `[A]` columnas: uuid, uuid_sucursal, uuid_ingreso, fecha_salida, fecha_retencion_hasta, created_at, created_by, sync_status, sync_timestamp, sync_attempts. SIN `tipo_salida`, SIN `forzado`, SIN `motivo_forzado` columns.
- `modelo_datos_er.mmd` líneas 577-596 — `prod.ingreso` `[L-E]` columnas: uuid, uuid_sucursal, placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente, fecha_ingreso, observaciones, created_at, created_by, sync_*. F1.7 V1 SELECT (read-only).
- `modelo_datos_er.mmd` líneas 187-207 — `prod.impuestos` `[V]` columnas: uuid, codigo (UK01), nombre, porcentaje, vigente_desde, vigente_hasta, estado, created_at. MIGRATION 0026 Op 2 inline-seeds fila `codigo='IVA', porcentaje=0.19`.
- `openspec/config.yaml` — `review_budget_lines: 400`, `commit_ceiling_loc: 800`, conventional commits enforced.