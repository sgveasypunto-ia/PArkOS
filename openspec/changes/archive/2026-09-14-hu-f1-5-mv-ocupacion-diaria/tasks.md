# Tasks: hu-f1-5-mv-ocupacion-diaria

> **Change**: `hu-f1-5-mv-ocupacion-diaria`
> **Phase**: tasks (sdd-tasks) — checklist only, do NOT implement
> **HU**: HU-F1.5 — Materialized view `prod.mv_ocupacion_diaria` + `GET /api/v1/operacion/ocupacion` + worker `RefreshMvOcupacionWorker`
> **Status**: READY — 18/18 tasks planned (8 RED + 6 GREEN + 1 REFACTOR + 3 VERIFICATION), TDD-strict (defense in depth)
> **Preflight (this session)**: `pace=auto`, `artifact_store=hybrid`, `delivery_strategy=auto-chain`,
>   `review_budget_lines=400` (vigente en `openspec/config.yaml`)
> **Branch topology**: rama única `feat/fase-1-prerequisites-backend` (HEAD `b5dd006`); un único PR directo
>   a `feat/fase-1-prerequisites-backend` por chained-pr policy (cambio cohesivo, ~160 LOC implementación + tests defense in depth).
> **Inputs read**: `exploration.md` (14 secciones, KD preliminares 1..6, archivos a tocar §13),
>   `proposal.md` (D-HU-F1.5-1..10, KD-1..6 confirmadas §2, OQ cerradas §12),
>   `specs/operational/spec.md` (REQ-OPS-030..033 RFC 2119),
>   `design.md` (11 secciones, 7 KD, SQL skeleton §4, Python skeleton §5, endpoint §6, schema §7, repo §8, threat matrix §9, traceability §10, test plan §11),
>   precedent `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/tasks.md` (13 tasks T-HU-F1.3-1..13, partial unique index + custom handler + AST walk, commit `ca3f9bf`).
> **Skills loaded**: `python`, `gentle-sdd-tasks` (paths injected)

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~330 across 1 PR (migración ~85 LOC + worker ~50 LOC + schemas ~20 LOC + repo helper ~25 LOC + endpoint handler ~30 LOC + unit tests ~120 LOC + integration tests ~100 LOC + static AST test ~40 LOC + spec delta ~30 LOC) |
| Total tasks | 18 (8 RED + 6 GREEN + 1 REFACTOR + 3 VERIFICATION) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | Low — cambio cohesivo en un módulo nuevo `repo/ocupacion.py` + un worker nuevo `jobs/refresh_mv_ocupacion.py` + un schema addition + una migración + cinco archivos de tests; sin tocar `WorkerRunner` base ni `make_router` ni `api/v1/__init__.py` |
| Chained PRs recommended | No — alcance acotado a un único MV read-only + endpoint GET read-only + worker aislado; contrato KD-1..KD-7 cerrado en design |
| Chain strategy | n/a (single PR) |
| Suggested split | Un único PR: `feat/fase-1-prerequisites-backend` → `origin/dev` |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No |

| Phase | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|-------|-------|---------------|----------------|----------------|
| Section 1: Migration | T1..T5 | ~85 LOC (migration) | ~50 LOC (preflight test) | 135 |
| Section 2: Worker | T6..T9 | ~50 LOC (worker) | ~80 LOC (cycle tests) | 265 |
| Section 3: Endpoint + schemas + repo | T10..T14 | ~75 LOC (schemas 20 + repo 25 + handler 30) | ~120 LOC (HTTP unit) | 460 |
| Section 4: Defense + verification | T15..T18 | — | ~40 LOC (AST) + ~100 LOC (DB integration) + suite run | 600 |
| **Total** | **18** | **~210 LOC impl** | **~390 LOC tests** | **~600 LOC** |

> Tope por commit: <800 LOC. Tests típicamente no cuentan al tope de 160 LOC de la HU pero los cuento para forecast. Implementación pura (migración + worker + endpoint + schemas + repo) cabe en ~210 LOC; la HU declara 160 LOC por el `repo/ocupacion.py` separado del scope (helper) — el delta de 50 LOC se absorbe en el design §1.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| PR1 (único) | Migración 0024 (pre-flight `DO $$` + `CREATE MATERIALIZED VIEW` + UNIQUE INDEX CONCURRENTLY) + worker `RefreshMvOcupacionWorker` (KD-5 fallback) + schemas `OcupacionItem`/`OcupacionResponse` + repo helper `repo/ocupacion.py` + handler `GET /operacion/ocupacion` (KD-3 authz) + 4 HTTP unit tests + 2 DB integration tests + 2 migration tests + 1 AST walk + 2 worker cycle tests + delta en spec canonical | `feat/fase-1-prerequisites-backend` → `origin/dev` | `uv run pytest backend/tests/unit/test_operacion_ocupacion.py backend/tests/integration/test_mv_ocupacion_diaria_db.py backend/tests/integration/test_migration_0024_mv.py backend/tests/integration/test_refresh_mv_job.py backend/tests/static/test_no_write_in_ocupacion.py -q` | `pg_engine` real (`parkos-branch-db:5433`) para tests integración con `PARKOS_DOCKER_TEST=1`; unit tests sin DB; AST check parsea `operacion.py::get_ocupacion` | Revert PR; migración se elimina con `alembic downgrade -1` (DROP MATERIALIZED VIEW); worker NSSM se desinstala sin tocar api-sucursal; handler se elimina al revertir el router; schemas quedan en `schemas/operacion.py` pero son unused |

## Tareas

### Section 1: Migration `prod.mv_ocupacion_diaria` (RED → GREEN → REFACTOR)

- [ ] **T-HU-F1.5-1** [RED] — `test_migration_0024_mv.py` con pre-flight test
  - Tests:
    - T1: aplicar migración sobre schema con datos sucios (5 ingresos, 2 con salida, 1 anulada) → view existe + UNIQUE INDEX aplicado sin colisiones + `repo/ocupacion.get_ocupacion_puros_activos` retorna filas solo para los 2 activos.
    - T2: aplicar migración sobre schema con `prod.ingreso` excediendo umbral 50M (simulado vía mock de `count(*)`) → `RAISE EXCEPTION` aborta la transacción; view NO queda creada.
  - Patrón F1.3: `PARKOS_DOCKER_TEST=1` + `pg_engine` real.
  - **Acción**: parametrizar `pytest` con `pytest.mark.parametrize` para T1/T2; usar `mock.patch("sqlalchemy.text")` para simular `count(*) > 50_000_000`; asserts sobre `pg_class.relname == 'mv_ocupacion_diaria'` y `pg_index.indisunique == True`. — **Archivos**: `backend/tests/integration/test_migration_0024_mv.py` (nuevo, ~50 LOC, 2 tests). — **Validación**: `uv run pytest backend/tests/integration/test_migration_0024_mv.py -q` falla con `ImportError` de `0024_add_mv_ocupacion_diaria` (módulo no existe) o `relationError` por view no presente.

- [ ] **T-HU-F1.5-2** [GREEN] — `0024_add_mv_ocupacion_diaria.py` migration (~85 LOC)
  - Archivo: `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py`
  - Contenido: pre-flight `DO $$` block (DECLARE `_n_ingreso bigint, _n_anul bigint, _n_salidas bigint`; SELECT count(*) en cada tabla; `RAISE NOTICE 'mv_ocupacion_diaria_preflight: ...'`; IF `_n_ingreso > 50_000_000` THEN `RAISE EXCEPTION 'mv_ocupacion_diaria_preflight_abort: ...'` END IF); `CREATE MATERIALIZED VIEW prod.mv_ocupacion_diaria AS SELECT i.uuid_sucursal, i.uuid_tipo_vehiculo, count(*) AS activos FROM prod.ingreso i WHERE i.uuid_tipo_vehiculo IS NOT NULL AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid AND s.uuid_sucursal = i.uuid_sucursal) AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_ingreso = i.uuid AND a.estado = 'ejecutada' AND a.tipo_anulable IN ('ingreso', 'salida')) GROUP BY i.uuid_sucursal, i.uuid_tipo_vehiculo`; `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS prod.uq_mv_ocupacion_diaria_sucursal_tipo ON prod.mv_ocupacion_diaria (uuid_sucursal, uuid_tipo_vehiculo)`; `GRANT SELECT ON prod.mv_ocupacion_diaria TO parkos_app`.
  - `revision = "0024_mv_ocupacion_diaria"`, `down_revision = "0023_unique_active_sesion_per_user"` (F1.3 chain head).
  - Downgrade: `DROP MATERIALIZED VIEW IF EXISTS prod.mv_ocupacion_diaria`.
  - **Acción**: pegar exactamente el SQL skeleton del design.md §4; header `from __future__ import annotations` + `from alembic import op`; constantes `_PREFLIGHT_THRESHOLD_INFO = 10_000_000`, `_PREFLIGHT_THRESHOLD_ABORT = 50_000_000`; docstring con referencia a REQ-OPS-032 + KD-7. — **Archivos**: `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` (nuevo, **~85 LOC**). — **Validación**: `uv run alembic upgrade head` aplica 0024 contra `parkos-branch-db` con `PARKOS_DOCKER_TEST=1`; `\d prod.mv_ocupacion_diaria` en psql muestra la view con UNIQUE INDEX `uq_mv_ocupacion_diaria_sucursal_tipo`.

- [ ] **T-HU-F1.5-3** [GREEN] — Aplicar migración y verificar T1 del test pasa
  - **Acción**: ejecutar `uv run alembic upgrade head` en test schema; validar que el UNIQUE INDEX `prod.uq_mv_ocupacion_diaria_sucursal_tipo` existe; ejecutar T1 del test pre-flight (`test_apply_with_dirty_data_creates_view_and_index`); assert que `repo/ocupacion.get_ocupacion_puros_activos(session, uuid_sucursal=X)` retorna solo los 2 ingresos activos. — **Archivos**: ninguno nuevo (verifica T-HU-F1.5-2). — **Validación**: T1 PASS; T2 sigue RED (50M abort pendiente verificación con mock — ver T-HU-F1.5-4).

- [ ] **T-HU-F1.5-4** [GREEN] — Verificar abort en 50M con fixture mock + round-trip downgrade/upgrade
  - **Acción**: insertar fixture que retorna `count(*) = 50_000_001` vía `mock.patch` sobre `op.execute` o usando una vista de test con `prod.ingreso` sobredimensionado; ejecutar T2 del test pre-flight (`test_preflight_aborts_on_simulated_50m_rows`); assert `RAISE EXCEPTION` con mensaje conteniendo `mv_ocupacion_diaria_preflight_abort`; luego ejecutar `alembic downgrade -1` y re-`alembic upgrade head` (round-trip idempotencia) — verificar que el UNIQUE INDEX `IF NOT EXISTS` permite re-aplicar sin recrear; verificar que `DOWNGRADE` elimina la view. — **Archivos**: ninguno nuevo (verifica T-HU-F1.5-2 + extiende T-HU-F1.5-1). — **Validación**: T2 PASS; round-trip PASS (downgrade + upgrade sin errores); `prod.mv_ocupacion_diaria` existe después de re-upgrade.

- [ ] **T-HU-F1.5-5** [REFACTOR] — Extraer constantes pre-flight y mejorar mensajes de error
  - **Acción**: si las constantes `_PREFLIGHT_THRESHOLD_INFO = 10_000_000` y `_PREFLIGHT_THRESHOLD_ABORT = 50_000_000` se referencian en otros tests o futuras migraciones, extraer a un módulo compartido `migrations/_preflight_thresholds.py`; mejorar mensajes de error del `RAISE EXCEPTION` con sugerencia accionable ("aproveche índice (uuid_sucursal, uuid_tipo_vehiculo) en prod.ingreso"); aplicar `ruff format` sobre el archivo de migración; verificar `__all__` orden. — **Archivos**: `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` (formato + comentarios), posible nuevo `backend/packages/parkos_core/migrations/_preflight_thresholds.py` (~10 LOC, solo si hay duplicación). — **Validación**: T1 + T2 siguen pasando; `ruff check` retorna `All checks passed!`; `mypy --strict` retorna `Success: no issues found`.

### Section 2: Worker `RefreshMvOcupacionWorker` (RED → GREEN)

- [ ] **T-HU-F1.5-6** [RED] — `test_refresh_mv_job.py` con 2 cycle tests (RED-by-construction)
  - Tests:
    - T1: `RefreshMvOcupacionWorker(session=mock, refresh_interval_s=10)` invoca `cycle()` una vez → assert `session.execute` llamado con `text("REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria")` + `session.commit()` + `asyncio.sleep(10)`.
    - T2: configurar `session.execute` para que raise `psycopg2.errors.FeatureNotSupported` en la primera llamada (path CONCURRENTLY) → invocar `cycle()` → assert segunda llamada es `text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria")` (plain, sin `CONCURRENTLY`); worker NO raises; log captura `refresh_mv_concurrently_failed_fallback`.
  - Patrón F1.3: `unittest.mock.AsyncMock` para session; `pytest.MonkeyPatch` para `asyncio.sleep`.
  - **Acción**: usar `AsyncMock(spec=AsyncSession)` con `session.execute.side_effect = [FeatureNotSupported(...), MagicMock()]` para T2; patchear `asyncio.sleep` con `AsyncMock` para verificar el intervalo; capturar logs con `caplog` (pytest fixture) en nivel `WARNING`. — **Archivos**: `backend/tests/integration/test_refresh_mv_job.py` (nuevo, ~80 LOC, 2 tests). — **Validación**: `uv run pytest backend/tests/integration/test_refresh_mv_job.py -q` falla con `ImportError` de `parkos_core.jobs.refresh_mv_ocupacion` (módulo no existe) o `AttributeError` por clase `RefreshMvOcupacionWorker` no definida.

- [ ] **T-HU-F1.5-7** [GREEN] — `refresh_mv_ocupacion.py` worker (~50 LOC)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py`
  - Contenido: `class RefreshMvOcupacionWorker(WorkerRunner)` con `DEFAULT_REFRESH_INTERVAL_S = 10`; `__init__(self, *, session: AsyncSession, refresh_interval_s: int = DEFAULT_REFRESH_INTERVAL_S)` que delega a `super().__init__(name="refresh_mv_ocupacion")` y florea `refresh_interval_s = max(5, int(refresh_interval_s))`; `async def cycle(self)` que intenta `REFRESH MATERIALIZED VIEW CONCURRENTLY prod.mv_ocupacion_diaria` + `commit`; en `except Exception` log `refresh_mv_concurrently_failed_fallback` con `extra={"event": ..., "exception_class": type(exc).__name__}` + `rollback` + fallback `REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria` (plain) + `commit`; inner `except Exception` log `refresh_mv_ocupacion_both_branches_failed`; `await asyncio.sleep(self.refresh_interval_s)` al final (post-cycle).
  - CLI: `async def _run_worker(database_url: str, refresh_interval_s: int) -> int` que crea engine asyncpg + session; `def main(argv: Optional[list[str]] = None) -> int` con argparse (`--refresh-interval-s`, `--database-url` default `PARKOS_BRANCH_DB_DSN` env); `if __name__ == "__main__": raise SystemExit(main())`.
  - **Acción**: importar `WorkerRunner` desde `.runner` (precedente `sync_sucursal.py`); usar `from sqlalchemy import text`; NO modificar `jobs/runner.py` (CI gate `worker_base_intact`); docstring con referencia a REQ-OPS-033 + KD-1 + KD-5. — **Archivos**: `backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py` (nuevo, **~50 LOC**). — **Validación**: `python -c "from parkos_core.jobs.refresh_mv_ocupacion import RefreshMvOcupacionWorker; print(RefreshMvOcupacionWorker.DEFAULT_REFRESH_INTERVAL_S)"` ejecuta sin error; T1 de T-HU-F1.5-6 PASS.

- [ ] **T-HU-F1.5-8** [GREEN] — Verificar T1 (cycle normal) y edge cases del worker
  - **Acción**: ejecutar T1 de T-HU-F1.5-6 con `caplog.at_level("DEBUG")` → assert log contiene `refresh_mv_ocupacion_cycle_ok`; verificar que `WorkerRunner` base NO fue modificado con `git diff backend/packages/parkos_core/src/parkos_core/jobs/runner.py` (debe retornar vacío — CI gate `worker_base_intact`); verificar que `refresh_interval_s = 4` se florea a 5 (límite inferior de seguridad); verificar que CLI `python -m parkos_core.jobs.refresh_mv_ocupacion --help` muestra las opciones. — **Archivos**: ninguno nuevo (verifica T-HU-F1.5-7). — **Validación**: T1 PASS; log contiene `refresh_mv_ocupacion_cycle_ok`; `worker_base_intact` verde; CLI help funcional.

- [ ] **T-HU-F1.5-9** [GREEN] — Verificar T2 (KD-5 fallback) y ausencia de pgcode en logs
  - **Acción**: ejecutar T2 de T-HU-F1.5-6 con `mock.patch("psycopg2.errors.FeatureNotSupported")`; assert worker completó sin raise; assert log NO contiene `pgcode` ni repr del exception (solo `exception_class = 'FeatureNotSupported'`); assert segunda llamada `session.execute` fue `REFRESH MATERIALIZED VIEW` (sin CONCURRENTLY); verificar que `exception_class` field del log es exactamente `type(exc).__name__` (no `repr(exc)`). — **Archivos**: ninguno nuevo (verifica T-HU-F1.5-7 + KD-5 + R6 mitigation pgcode leak). — **Validación**: T2 PASS; `caplog.records` no contiene `pgcode` ni string `"23505"`; worker continúa después del fallback.

### Section 3: Endpoint `GET /api/v1/operacion/ocupacion` (RED → GREEN)

- [ ] **T-HU-F1.5-10** [RED] — `test_operacion_ocupacion.py` con 4 HTTP tests (RED-by-construction)
  - Tests:
    - T1: `operador-` JWT con `sucursal=X` → `GET /operacion/ocupacion?uuid_sucursal=X` retorna `200` con `OcupacionResponse` (items non-empty, ORDER BY tv.tipo, `generado_en` ISO-8601 UTC). REQ-OPS-030.
    - T2: `operador-` JWT con `sucursal=X` → `GET /operacion/ocupacion?uuid_sucursal=Y` retorna `403` con body `{"error": "tenant_scope_violation"}`; sin pgcode, sin driver string, sin uuid_sucursal value. REQ-OPS-031 KD-3.
    - T3: `admin-` JWT con `claims["sucursales_permitidas"] = [X]` + header `X-Sucursal-Context: X` → `GET /operacion/ocupacion?uuid_sucursal=X` retorna `200`. REQ-OPS-031 KD-3 admin scope.
    - T4: `admin-` JWT sin `X-Sucursal-Context` y sin `claims["sucursales_permitidas"]` → `GET /operacion/ocupacion` (sin query param) retorna `400` con body `{"error": "missing_sucursal_context"}`. REQ-OPS-031 KD-3 missing.
  - Patrón F1.3 / F1.8: `httpx.AsyncClient + ASGITransport(app)` + JWT operador fixture.
  - **Acción**: parametrizar `pytest` con `pytest.mark.parametrize("test_case", [T1, T2, T3, T4])`; usar `httpx.AsyncClient(transport=ASGITransport(app))` + fixtures `operator_jwt`, `admin_jwt_with_branch`, `admin_jwt_no_branch`; assert response shape via `pydantic.OcupacionResponse.model_validate(response.json())`. — **Archivos**: `backend/tests/unit/test_operacion_ocupacion.py` (nuevo, ~120 LOC, 4 tests). — **Validación**: `uv run pytest backend/tests/unit/test_operacion_ocupacion.py -q` falla con `404 Not Found` (ruta `/ocupacion` no registrada) o `ImportError` de `schemas.operacion.OcupacionResponse`.

- [ ] **T-HU-F1.5-11** [GREEN] — Schemas `OcupacionItem` + `OcupacionResponse` (~20 LOC)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (modificado, append)
  - Contenido: `class OcupacionItem(_Base)` con `uuid_tipo_vehiculo: uuid_lib.UUID`, `tipo: str`, `cupo_maximo: int`, `activos: int`, `disponible: int`; `class OcupacionResponse(_Base)` con `uuid_sucursal: uuid_lib.UUID`, `items: list[OcupacionItem]`, `generado_en: datetime`. `_Base` ya tiene `model_config = ConfigDict(extra="forbid")` (precedente F1.8) — herencia preserva el contrato.
  - **Acción**: importar `uuid as uuid_lib` + `from datetime import datetime`; append al final del archivo post-F1.8 (`CotizarResponse`); docstring con referencia a REQ-OPS-030 + KD-6 (`disponible` puede ser negativo); comentario inline que `disponible` es derivado server-side (`cupo_maximo - activos`). — **Archivos**: `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (modificado, append, **~20 LOC**). — **Validación**: `python -c "from parkos_core.schemas.operacion import OcupacionItem, OcupacionResponse; print(OcupacionResponse.model_config)"` ejecuta sin error; `extra='forbid'` confirmado.

- [ ] **T-HU-F1.5-12** [GREEN] — Repo helper `repo/ocupacion.py` (~25 LOC)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` (nuevo)
  - Contenido: `@dataclass(frozen=True) class OcupacionItemRow` con `uuid_tipo_vehiculo: uuid_lib.UUID, tipo: str, cupo_maximo: int, activos: int` + `@property def disponible(self) -> int: return self.cupo_maximo - self.activos`; `async def get_ocupacion_puros_activos(session: AsyncSession, *, uuid_sucursal: uuid_lib.UUID) -> list[OcupacionItemRow]` con `text("SELECT mv.uuid_tipo_vehiculo AS uuid_tipo_vehiculo, tv.tipo AS tipo, COALESCE(cvs.cantidad, 0) AS cupo_maximo, mv.activos AS activos FROM prod.mv_ocupacion_diaria mv JOIN prod.tipos_vehiculo tv ON tv.uuid = mv.uuid_tipo_vehiculo AND tv.vigente_hasta IS NULL LEFT JOIN prod.cantidad_vehiculos_sucursal cvs ON cvs.uuid_sucursal = mv.uuid_sucursal AND cvs.uuid_tipo_vehiculo = mv.uuid_tipo_vehiculo AND cvs.vigente_hasta IS NULL WHERE mv.uuid_sucursal = :uuid_sucursal ORDER BY tv.tipo")` + bind params `{"uuid_sucursal": uuid_sucursal}`.
  - **Acción**: importar `text` de `sqlalchemy` + `AsyncSession` de `sqlalchemy.ext.asyncio`; docstring con referencia a REQ-OPS-030 + KD-6; usar bind params (NO string interpolation — KD-1 SQL injection hygiene). — **Archivos**: `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` (nuevo, **~25 LOC**). — **Validación**: `python -c "from parkos_core.repo.ocupacion import get_ocupacion_puros_activos, OcupacionItemRow"` ejecuta sin error; `OcupacionItemRow.disponible` retorna `cupo_maximo - activos`.

- [ ] **T-HU-F1.5-13** [GREEN] — Handler `get_ocupacion` en `operacion.py` (~30 LOC)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modificado, append)
  - Contenido: imports (`from uuid import UUID` + `from fastapi import Depends, HTTPException, Query, Response` + `from datetime import datetime, timezone` + schemas + repo + `TenantScopeViolation, SucursalNotPermitted`); `@router.get("/ocupacion", response_model=OcupacionResponse, summary="...", responses={400: ..., 403: ..., 503: ...})`; `async def get_ocupacion(response: Response, uuid_sucursal: UUID | None = Query(None, description="..."), session: AsyncSession = Depends(get_session), ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_ingreso_issuer_dep)) -> OcupacionResponse`.
  - Lógica: target = uuid_sucursal or ctx.sucursal_uuid; if target is None: HTTPException(400, detail={"error": "missing_sucursal_context"}); if ctx.issuer_prefix == "operador-": if ctx.sucursal_uuid is None or target != ctx.sucursal_uuid: raise TenantScopeViolation(actor_uuid=ctx.actor_uuid); elif ctx.issuer_prefix == "admin-": if target not in (ctx.claims or {}).get("sucursales_permitidas", []): raise SucursalNotPermitted(target_sucursal=target); items = await get_ocupacion_puros_activos(session, uuid_sucursal=target); response.headers["Cache-Control"] = "no-store"; return OcupacionResponse(uuid_sucursal=target, items=[OcupacionItem.model_validate(it) for it in items], generado_en=datetime.now(tz=timezone.utc)).
  - **Acción**: append el handler al final del archivo post-`cotizar_ingreso_handler` (paths no colisionan — FastAPI matchea por especificidad); NO modificar `make_router`; docstring con referencia a REQ-OPS-030 + REQ-OPS-031 + KD-3. — **Archivos**: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modificado, append, **~30 LOC**). — **Validación**: T1 + T3 de T-HU-F1.5-10 PASS; T2 + T4 siguen RED por mapping de errores pendiente en T-HU-F1.5-14.

- [ ] **T-HU-F1.5-14** [GREEN] — Verificar 4/4 HTTP tests PASS + factory_intact
  - **Acción**: ejecutar `uv run pytest -q backend/tests/unit/test_operacion_ocupacion.py`; objetivo 4/4 PASS; verificar header `Cache-Control: no-store` presente en respuestas 200; verificar body de T2 NO contiene `pgcode` ni driver string; verificar body de T4 contiene exactamente `{"error": "missing_sucursal_context"}`; verificar `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` retorna vacío (CI gate `factory_intact`); verificar `git diff backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` retorna vacío (router ya estaba montado en línea 143). — **Archivos**: ninguno nuevo (verifica T-HU-F1.5-11/12/13). — **Validación**: log muestra `4 passed`; `factory_intact` verde; `__init__.py` intacto.

  Log esperado (post-GREEN):
  ```
  tests\unit\test_operacion_ocupacion.py ....                          [100%]
  ============================== 4 passed in <TBD>s ==============================
  ```

### Section 4: Defense in depth & verification (CROSS-CUTTING)

- [ ] **T-HU-F1.5-15** [GREEN] — `test_no_write_in_ocupacion.py` AST walk (defense in depth)
  - Test: AST walk sobre `api/v1/operacion.py::get_ocupacion` rechaza `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` en el cuerpo. Patrón F1.3 / F1.8.
  - **Acción**: usar `ast.parse()` sobre el archivo fuente de `operacion.py`; localizar la función `get_ocupacion` via `ast.walk` + `ast.FunctionDef.name == 'get_ocupacion'`; tokenizar identificadores + strings; rechazar tokens case-insensitive fuera de strings/comentarios que contengan `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `MERGE`, `FOR UPDATE`, `FOR SHARE`; reportar primer match ofensivo con línea + número de ocurrencia. — **Archivos**: `backend/tests/static/test_no_write_in_ocupacion.py` (nuevo, **~40 LOC**, 1 test). — **Validación**: `uv run pytest backend/tests/static/test_no_write_in_ocupacion.py -q` PASS (handler ya creado en T-HU-F1.5-13 y no contiene write verbs).

- [ ] **T-HU-F1.5-16** [GREEN] — `test_mv_ocupacion_diaria_db.py` con 2 DB integration tests (defense in depth)
  - Tests:
    - T1: insertar `ingreso(uuid_sucursal=X, uuid_tipo_vehiculo=T, fecha_ingreso=now)`; `await session.execute(text("REFRESH MATERIALIZED VIEW prod.mv_ocupacion_diaria"))`; `repo/ocupacion.get_ocupacion_puros_activos(session, uuid_sucursal=X)` retorna 1 row con `activos == 1`, `cupo_maximo == 0` (no cvs row), `disponible == -1` (KD-6 valid negative).
    - T2: insertar `ingreso` + insertar `salidas(uuid_ingreso=I, uuid_sucursal=X)`; refresh MV; assert items para `(X, T)` es empty (ingreso NO longer "activo").
  - Requiere `PARKOS_DOCKER_TEST=1` y `parkos-branch-db`.
  - Patrón F1.3 / F1.8: sembrar fixtures via `INSERT` directo al engine de testcontainers; cleanup al final con `await session.rollback()`.
  - **Acción**: usar `pg_engine` fixture (testcontainers precedent F1.4); sembrar `prod.sucursal`, `prod.tipos_vehiculo`, `prod.cantidad_vehiculos_sucursal` (vigente_hasta IS NULL); ejecutar el refresh; llamar `get_ocupacion_puros_activos`; asserts sobre `OcupacionItemRow.activos` y `OcupacionItemRow.disponible`. — **Archivos**: `backend/tests/integration/test_mv_ocupacion_diaria_db.py` (nuevo, ~100 LOC, 2 tests). — **Validación**: `uv run pytest backend/tests/integration/test_mv_ocupacion_diaria_db.py -q` con `PARKOS_DOCKER_TEST=1` muestra `2 passed`; sin Docker, tests skip con mensaje claro.

- [ ] **T-HU-F1.5-17** [VERIFICATION] — Suite completa verde + ruff + mypy + factory_intact + worker_base_intact
  - **Acción**: ejecutar las 5 suites en orden:
    1. `uv run pytest -q backend/tests/unit/test_operacion_ocupacion.py backend/tests/integration/test_mv_ocupacion_diaria_db.py backend/tests/integration/test_migration_0024_mv.py backend/tests/integration/test_refresh_mv_job.py backend/tests/static/test_no_write_in_ocupacion.py` → objetivo `10 passed` (4 HTTP + 2 DB + 2 migration + 2 worker + 1 AST), 0 CRITICAL failures.
    2. `uv run ruff check backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py backend/packages/parkos_core/src/parkos_core/schemas/operacion.py backend/tests/unit/test_operacion_ocupacion.py backend/tests/integration/test_mv_ocupacion_diaria_db.py backend/tests/integration/test_migration_0024_mv.py backend/tests/integration/test_refresh_mv_job.py backend/tests/static/test_no_write_in_ocupacion.py` → `All checks passed!`.
    3. `uv run ruff format --check backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py backend/packages/parkos_core/src/parkos_core/schemas/operacion.py backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` → exit 0.
    4. `uv run mypy --strict backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py backend/packages/parkos_core/src/parkos_core/schemas/operacion.py backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` → `Success: no issues found`.
    5. `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` → vacío (CI gate `factory_intact`).
    6. `git diff backend/packages/parkos_core/src/parkos_core/jobs/runner.py` → vacío (CI gate `worker_base_intact`).
    7. `git diff backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` → vacío (router ya estaba montado).
  - Capturar log con baseline observado; si hay regresión en tests previos, NO marcar `[x]` hasta revertir el cambio que la introdujo. — **Archivos**: ninguno nuevo (verifica toda la suite + static gates). — **Validación**: log muestra `10 passed`; ruff + mypy + factory_intact + worker_base_intact todos verdes; ningún test previo en estado `FAILED` o `ERROR`.

- [ ] **T-HU-F1.5-18** [VERIFICATION] — `git add` + conventional commit atómico
  - **Acción**: ejecutar `git add backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py backend/packages/parkos_core/src/parkos_core/jobs/refresh_mv_ocupacion.py backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py backend/packages/parkos_core/src/parkos_core/schemas/operacion.py backend/tests/unit/test_operacion_ocupacion.py backend/tests/integration/test_mv_ocupacion_diaria_db.py backend/tests/integration/test_migration_0024_mv.py backend/tests/integration/test_refresh_mv_job.py backend/tests/static/test_no_write_in_ocupacion.py openspec/specs/operations/spec.md` + `git commit -m "feat(backend): anadir materialized view mv_ocupacion_diaria + endpoint GET /operacion/ocupacion + worker refresh_mv_ocupacion para HU-F1.5"` (español neutral, NO `Co-authored-by:`, NO trailers IA, <800 LOC diff). Verificar `git log -1 --format='%an %ae'` retorna `Parkos Dev <parkos@example.com>` (NO `noreply@anthropic.com`).
  - Conventional commit body (opcional): 3-5 líneas describiendo KD-1 (worker separado NSSM), KD-2 (UNIQUE INDEX natural composite CONCURRENTLY), KD-3 (autorización por sucursal), KD-5 (fallback plain REFRESH), KD-7 (pre-flight 10M NOTICE / 50M ABORT).
  - **Archivos**: ninguno nuevo (commit final). — **Validación**: `git log -1 --stat` muestra el diff total <800 LOC; el commit subject contiene el HU ID; ningún trailer AI presente.

## Cross-phase constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` ni `FOR UPDATE|SHARE` en `get_ocupacion` — AST walk (T-HU-F1.5-15) lo enforza en CI.
- NO `Co-authored-by:` ni trailers AI en commits; conventional commits, español neutral.
- NO SQLite en tests — `pg_engine` real o `testcontainers[postgres]` (precedente F1.4).
- NO modificación de `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate.
- NO modificación de `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate (la subclase `RefreshMvOcupacionWorker` reusa la base tal cual, D-HU-F1.5-1).
- NO modificación de `api/v1/__init__.py` — el router ya estaba montado en línea 143.
- NO `INSERT|UPDATE|DELETE` en `prod.mv_ocupacion_diaria` desde el endpoint `/operacion/ocupacion` — read-only por contrato (REQ-OPS-030).
- NO `pgcode` en response body, headers, ni log lines at `info+` — REQ-OPS-031 RFC 2119 MUST; KD-5 fallback log solo `exception_class` (R6 mitigation).
- NO `CREATE INDEX` (sin `CONCURRENTLY`) sobre la view — KD-2: `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` (REVIEW-style precedent `0023_unique_active_sesion_per_user.py`).
- NO uso de `cantidad_vehiculos_sucursal.disponible` (columna NO existe en el ER; KD-6 omission — `disponible` es derivado, no persistido).
- NO auto-refresh en `startup` del worker — KD-5 acepta lag de `2 × refresh_interval_s`; RIESGO-SUC-02 ya documenta el riesgo vivo.
- NO circuit breaker — KD-5 acepta fallos transitorios; logs estructurados `refresh_mv_concurrently_failed_fallback` + `refresh_mv_ocupacion_both_branches_failed`.
- NO auto-close / auto-cleanup de huérfanos — fuera de scope; owner decide manualmente.
- NO `DELETE /operacion/ocupacion/{uuid_tipo_vehiculo}` — endpoint read-only (idempotente), F1.5 no crea write surface.
- NO métricas/observabilidad del refresh — futuro HU-F1.X.
- NO seed operativo NSSM del worker — responsabilidad de `infra/` (documentado en design §1 KD-1, fuera de este change).
- Header `Cache-Control: no-store` en respuesta 200 de `/operacion/ocupacion` (consistente con F1.8 R8 / F1.3 R8).
- Discriminadores de error estables: `tenant_scope_violation`, `sucursal_not_permitted`, `missing_sucursal_context`, `ocupacion_materializada_error` (futuro KD-5 surface).
- Precedencia de errores: `400 missing_sucursal_context > 403 tenant_scope_violation > 403 sucursal_not_permitted > 401/403 issuer`.
- Mensajes conventional commit; cuerpo técnico en español neutral.

## Acceptance Gates

- TDD strict: RED primero, GREEN mínimo, REFACTOR último.
- Conventional commit atómico: `feat(backend): anadir materialized view mv_ocupacion_diaria + endpoint GET /operacion/ocupacion + worker refresh_mv_ocupacion para HU-F1.5` (≤800 LOC).
- Sin `Co-authored-by:`, sin trailers IA.
- Tests pasan contra DB real con `PARKOS_DOCKER_TEST=1` (4 HTTP unit + 2 DB integration + 2 migration pre-flight + 2 worker cycle + 1 AST walk = 11 tests nuevos).
- ruff + mypy --strict clean sobre los 10 archivos nuevos/modificados.
- `factory_intact` CI gate verde (`git diff api/v1/router_factory.py` vacío).
- `worker_base_intact` CI gate verde (`git diff jobs/runner.py` vacío).
- `__init__.py` intacto (`git diff api/v1/__init__.py` vacío).
- 0 regresiones introducidas por F1.5; las fallas preexistentes documentadas en baseline F1.8 (25 fallas conocidas) se mantienen sin nuevos archivos fallando.

## Out of Scope Tasks

- Visibilidad cross-branch para `admin-` (consultar cualquier `uuid_sucursal` global). Sale del scope: admin_views cloud-only es producto separado. KD-3 acota a `claims["sucursales_permitidas"]`.
- Push de ocupación vía websocket / SSE. Sale del scope: el cliente hace polling 10s (`plan.md:1422-1442`).
- Mitigación de RIESGO-SUC-02 (lag máximo 10s en momentos de alta rotación). Sale del scope: el corpus ya lo documenta como riesgo vivo aceptado.
- Endpoint `GET /operacion/ocupacion/{uuid_tipo_vehiculo}` filtrado por tipo. Sale del scope: el breakdown completo cabe en una sola respuesta JSON.
- Lock pesimista `SELECT … FOR SHARE` sobre `ingreso` / `salidas` / `anulaciones`. Sale del scope: la vista materializada usa snapshot MVCC consistente.
- Indexación `(uuid_sucursal, uuid_tipo_vehiculo)` sobre `prod.ingreso` para acelerar el primer refresh. Precondición documentada en pre-flight (> 50M filas).
- Siembra operativa del refresh job vía systemd / cron / k8s CronJob. La operación NSSM es responsabilidad de `infra/`.
- Versionado de UI cliente (Fase 2 frontend — `OcupacionStrip` consumirá el endpoint).
- Métricas / observabilidad del refresh (contador de cycles, latencia p99 del `REFRESH`, alertas). Alineado con HU-F1.X de observabilidad (futuro).
- Tabla `categorias_vehiculo` para agrupar tipos (Auto/Moto/Camioneta). No existe en el ER.
- Endpoint `GET /operacion/ocupacion/resumen` (agregado `{cupo_total, activos_total, disponible_total}`). KD-4 eligió breakdown por tipo.
- Auto-cleanup de huérfanos (sesiones activas sin cierre, ingresos sin salida). Owner decide manualmente.
- Aplicar el mismo patrón materialized view a otras tablas `[L-*]` (ej. `prod.caja`, `prod.factura`). Fuera de scope.
- Circuit breaker con auto-recovery tras N successful refreshes. KD-5 acepta fallos transitorios; breaker es concern de observabilidad futura.

## References

- `exploration.md`, `proposal.md`, `specs/operational/spec.md`, `design.md` en `openspec/changes/hu-f1-5-mv-ocupacion-diaria/`.
- Precedente F1.3: `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/tasks.md` (13 tasks T-HU-F1.3-1..13, partial unique index + custom handler + AST walk pattern, commit `ca3f9bf`).
- Precedente F1.8: `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/tasks.md` (13 tasks T-HU-F1.8-1..13, PL/pgSQL migration + custom handler + AST walk pattern, commit `a3d0c39`).
- Precedente F1.4: `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/tasks.md` (helper-pure pattern + bi-temporal precedent, commit `de4d2fc`).
- Precedente F1.2: `openspec/changes/archive/2026-09-14-hu-f1-2-login-jwt/tasks.md` (TenantContext extraction + auth dependency pattern).
- `modelo_datos_er.mmd` § ingreso `[L-E]` (líneas 577-596), cantidad_vehiculos_sucursal `[V]` (428-446), tipos_vehiculo `[V]` (87-104), salidas `[A]` (761-777), anulaciones `[L-W]`.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` — router custom, `_ingreso_issuer_dep` línea 64, `cotizar_ingreso_handler` línea 219, `derived state` líneas 152-168.
- `backend/packages/parkos_core/src/parkos_core/jobs/runner.py` — `WorkerRunner` base (signal handlers, exit codes 0/1/2).
- `backend/packages/parkos_core/src/parkos_core/jobs/sync_sucursal.py` — `SyncSucursalWorker` con `cycle()` async + `DEFAULT_POLL_INTERVAL_S = 10` (precedente de KD-1 worker NSSM separado).
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` — `TenantContext` + `get_tenant_ctx` + errores tipados `TenantScopeViolation` (líneas 60-65) + `SucursalNotPermitted` (115-131).
- `backend/packages/parkos_core/src/parkos_core/api/deps.py` — `get_tenant_ctx` + `requires_issuer`.
- `backend/packages/parkos_core/migrations/versions/0023_unique_active_sesion_per_user.py` — última migración aplicada; **0024 es el próximo slot disponible** (`down_revision = "0023_unique_active_sesion_per_user"`).