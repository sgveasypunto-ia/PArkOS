# Tasks: hu-f1-6-validaciones-post-ingresos

> **Change**: `hu-f1-6-validaciones-post-ingresos`
> **Phase**: tasks (sdd-tasks) — checklist only, do NOT implement
> **HU**: HU-F1.6 — Server-side validation of `POST /api/v1/operacion/ingresos` (regex placa, KD-FORZADO bypass, cupo via `mv_ocupacion_diaria`, no-duplicate active ingreso, `tipo_entrada` server-side derivation). 260 LOC budget per `plan.md` línea 787.
> **Status**: READY — 23/23 tasks planned (1 migration + 6 repo RED/GREEN + 8 handler RED/GREEN + 2 schemas + 2 static guards + 2 refactor + 2 verification). TDD-strict defense in depth (D-HU-F1.6-7 4 layers).
> **Preflight (this session)**: `pace=auto`, `artifact_store=hybrid`, `delivery_strategy=auto-chain` (cached), `review_budget_lines=400` (vigente en `openspec/config.yaml`).
> **Branch topology**: rama única `feat/fase-1-prerequisites-backend` (HEAD `e1cc79b`); un único PR directo a `origin/dev` (matches F1.5 precedent). Commit split interno: 2 commits ≤800 LOC cada uno (apply-código + tests+verification).
> **Inputs read**: `exploration.md` (16 sections, V1..V9 + KD-FORZADO-01, files-to-touch §15), `proposal.md` (D-HU-F1.6-1..13, KD-V1..V9 + KD-FORZADO-01 adoptados, 10 OQ cerradas §12), `specs/operational/spec.md` (REQ-OPS-034..041 RFC 2119), `design.md` (15 sections, R-A1..R-A7 architecture risks, 11-step handler skeleton §7, repo skeleton §8, threat matrix §10, traceability §11), `models/L_W/alerta.py` (verified: NO `datos_nuevos` JSONB column), `migrations/versions/0013_add_alert_types.py` (verified: `alert_types_inmutable` BEFORE UPDATE/DELETE trigger blocks non-superuser writes), `migrations/versions/0024_add_mv_ocupacion_diaria.py` (last head — 0025 is next slot, `down_revision = "0024_mv_ocupacion_diaria"`).
> **Orchestrator addendum (pre-design amendment)**: migration 0025 IS required (breaks original "no migration" promise); 2 sub-tasks: (a) `ALTER TABLE prod.alerta ADD COLUMN IF NOT EXISTS datos_nuevos JSONB`; (b) `INSERT INTO prod.alert_types (..., 'capacidad_agotada_forzado', ...) ON CONFLICT (tipo_alerta) DO NOTHING` (alert_types_inmutable trigger blocks UPDATE/DELETE for non-superuser — rol_app is INSERT-only).
> **Precedents mirrored**: F1.5 (REQ-OPS-030..033, MV pattern + KD-7 pre-flight + AST walk, commit `fc72adb`), F1.4 (REQ-OPS-017..021, bi-temporal predicate reusable in V3, commit `467b4f0`), F1.3 (REQ-OPS-026..029, AST walk + custom handler before factory + partial unique index, commit `ca3f9bf`), F1.8 (REQ-OPS-022..025, AST walk read-only, commit `de4d2fc`).
> **Skills loaded**: `gentle-sdd-tasks` (paths injected).

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~1,400 across 1 PR (migration ~85 LOC + 4 NEW repo files ~320 LOC + 2 MODIFIED repo files +70 LOC + handler ~232 LOC + schemas +80 LOC + 6 NEW test files ~1,060 LOC + spec delta ~50 LOC) |
| Total tasks | 23 (1 migration + 6 repo RED/GREEN pairs + 8 handler RED/GREEN pairs + 2 schemas + 2 static guards + 2 refactor + 2 verification) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Medium** — F1.6 es ~4x F1.5's LOC pero cohesivo (un único endpoint, un único módulo `repo/ingreso.py`); 2-commit split interno (apply-código ≤800 LOC + tests+verification ≤800 LOC) mantiene cada commit bajo el techo `commitlint` |
| Chained PRs recommended | No — un único PR (matches F1.5 precedent `feat/fase-1-prerequisites-backend` → `origin/dev`); defensa en profundidad se prueba in-place |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Un único PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 2 commits internos: (1) apply-código (migration + repos + handler + schemas); (2) tests + verification |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesivo single-endpoint; budget risk Medium pero dentro del precedente F1.5 |

| Phase | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|-------|-------|---------------|----------------|----------------|
| Section 0: Migration 0025 | T0.1 | ~85 LOC (migration) | — | 85 |
| Section 1: Repo layer RED | T1.1..T1.3 | — | ~110 LOC (3 test files) | 195 |
| Section 2: Repo layer GREEN | T2.1..T2.3 | ~140 LOC (repo helpers) | — | 335 |
| Section 3: Handler layer RED | T3.1..T3.4 | — | ~870 LOC (4 test files) | 1,205 |
| Section 4: Handler layer GREEN | T4.1..T4.4 | ~282 LOC (handler + repo additions) | — | 1,487 |
| Section 5: Schemas + integration | T5.1..T5.2 | ~80 LOC (schemas) | — | 1,567 |
| Section 6: Static guards | T6.1..T6.2 | — | ~180 LOC (2 AST walks) | 1,747 |
| Section 7: Refactor | T7.1..T7.2 | refactor (sin LOC nuevo) | — | 1,747 |
| Section 8: Verification | T8.1..T8.2 | — | suite run | 1,747 |
| **Total** | **23** | **~587 LOC impl** | ~1,160 LOC tests | **~1,747 LOC** |

> Tope por commit: <800 LOC. Apply-código cabe en ~587 LOC (≤800 OK). El split en 2 commits se ejecuta como 2 commits consecutivos dentro del mismo PR (no chained PRs).

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| PR1 (único, 2 commits) | Commit 1 (apply-código): migration 0025 + 4 NEW `repo/*.py` + 2 MODIFIED `repo/*.py` + handler `create_ingreso` replace + `schemas/operacion.py` append. Commit 2 (tests+verification): 6 test files + suite verde + static guards + ruff/mypy clean + factory_intact/event_helper_intact/auth_tenancy_intact | `feat/fase-1-prerequisites-backend` → `origin/dev` | `uv run pytest backend/tests/unit/test_operacion_ingresos_validaciones.py backend/tests/unit/test_operacion_ingresos_kd_forzado.py backend/tests/unit/test_repo_placa.py backend/tests/integration/test_ingreso_create_db.py backend/tests/static/test_no_write_after_insert.py backend/tests/static/test_kd_forzado_in_handler.py -q` | `pg_engine` real (`parkos-branch-db:5433`) con `PARKOS_DOCKER_TEST=1` para tests integración (T3.3, T3.4); unit tests sin DB; AST walks parsean `repo/ingreso.py::crear_ingreso_evento` y `api/v1/operacion.py::create_ingreso` | Revert PR; migración `alembic downgrade -1` elimina columna `datos_nuevos` + DELETE del `alert_types` row (superuser; alert_types_inmutable trigger no bloquea a superuser); handler revierte a F1.5 thin pass-through; 4 NEW `repo/*.py` se vuelven unused pero harmless |

## Tareas

### Section 0: Migration `0025_add_alerta_datos_nuevos_and_alert_type` (RED → GREEN)

- [x] **T-HU-F1.6-0.1** [RED-GREEN-REFACTOR] — migration 0025 (~85 LOC) + pre-flight test
  - RED test:
    - T1: aplicar `alembic upgrade head` sobre schema pre-0024 (post-0024 con `alert_types` sembrado en F1.14) → assert nueva columna `prod.alerta.datos_nuevos JSONB NULLABLE` existe + assert fila `('capacidad_agotada_forzado', 'Ingreso vehicular forzado por administrador al detectar cupo agotado en la sucursal', 'warning')` existe en `prod.alert_types` con `created_at` reciente.
    - T2: aplicar `alembic downgrade -1` → assert columna `datos_nuevos` se eliminó (`DROP COLUMN IF EXISTS`) + assert fila `capacidad_agotada_forzado` se eliminó (`DELETE FROM prod.alert_types WHERE tipo_alerta='capacidad_agotada_forzado'` — corre como superuser en alembic, bypassea `alert_types_inmutable`).
    - T3: re-aplicar `alembic upgrade head` → assert idempotente: `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING` no duplica fila.
  - Patrón F1.5: pre-flight `DO $$` con `SELECT count(*) FROM pg_catalog.pg_class WHERE relname='alerta'` (KD-7 pre-flight pattern); `PARKOS_DOCKER_TEST=1` + `pg_engine` real.
  - GREEN migration `0025_add_alerta_datos_nuevos_and_alert_type.py`:
    1. Pre-flight `DO $$` block: `DECLARE _n_alerta bigint; SELECT count(*) INTO _n_alerta FROM pg_catalog.pg_class WHERE relname='alerta'; RAISE NOTICE '0025_preflight: prod.alerta existe con % filas'; IF _n_alerta IS NULL THEN RAISE EXCEPTION '0025_preflight_abort: tabla prod.alerta no existe' END IF;`.
    2. `ALTER TABLE prod.alerta ADD COLUMN IF NOT EXISTS datos_nuevos JSONB`.
    3. `INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity) VALUES ('capacidad_agotada_forzado', 'Ingreso vehicular forzado por administrador al detectar cupo agotado en la sucursal', 'warning') ON CONFLICT (tipo_alerta) DO NOTHING` (idempotente; respeta `alert_types_inmutable` trigger que bloquea UPDATE/DELETE para no-superuser).
    4. `GRANT SELECT, INSERT ON prod.alerta TO parkos_app` (la columna `datos_nuevos` hereda privilegios por DEFAULT si no se especifica).
  - Downgrade:
    1. `DELETE FROM prod.alert_types WHERE tipo_alerta='capacidad_agotada_forzado'` (admin-only since `alert_types_inmutable` blocks non-superuser; alembic runs as superuser).
    2. `ALTER TABLE prod.alerta DROP COLUMN IF EXISTS datos_nuevos`.
  - `revision = "0025_alerta_datos_nuevos"`, `down_revision = "0024_mv_ocupacion_diaria"` (F1.5 chain head).
  - **Acción**: pegar exactamente el SQL skeleton; header `from __future__ import annotations` + `from alembic import op`; constantes `_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"` (precedente F1.5); docstring con referencia a REQ-OPS-041.C + R-A1 (alert_types_inmutable trigger) + R-A2 (jsonb audit column). — **Archivos**: `backend/packages/parkos_core/migrations/versions/0025_add_alerta_datos_nuevos_and_alert_type.py` (nuevo, **~85 LOC**); `backend/tests/integration/test_migration_0025_datos_nuevos.py` (nuevo, ~50 LOC, 3 tests RED-by-construction). — **Validación**: `uv run pytest backend/tests/integration/test_migration_0025_datos_nuevos.py -q` con `PARKOS_DOCKER_TEST=1` falla con `relationError` (column `datos_nuevos` no existe) antes de GREEN; tras GREEN muestra `3 passed`; round-trip upgrade → downgrade → upgrade idempotente.

### Section 1: Repo layer RED (3 archivos de test nuevos)

- [x] **T-HU-F1.6-1.1** [RED] — `test_repo_placa.py` con 6 parametrized regex tests (RED-by-construction)
  - Tests (mapean `repo/placa.py::detectar_tipo_vehiculo`):
    - T1: `ABC123` → UUID de `prod.tipos_vehiculo` con `tipo='Auto'` vigente.
    - T2: `ABC12D` → UUID de `prod.tipos_vehiculo` con `tipo='Moto'` vigente.
    - T3: `AB12` (4 chars) → `None` (regex mismatch).
    - T4: `abc123` (lowercase) → `None` (regex strict, DEC-SUC-22).
    - T5: `AB1234` (3 letras + 4 dígitos, no patrón) → `None`.
    - T6: `ABC-123` (con guión) → `None`.
  - Patrón F1.5: `pytest.mark.parametrize`; sembrar `prod.tipos_vehiculo` con `tipo='Auto'/'Moto'` y `vigente_hasta IS NULL AND estado='activo'`; usar `pg_engine` real con `PARKOS_DOCKER_TEST=1`.
  - **Acción**: importar `detectar_tipo_vehiculo` desde `parkos_core.repo.placa`; usar `pytest_asyncio.fixture` para sembrar fixture de tipos_vehiculo; asserts sobre `result.uuid` y `result is None`. — **Archivos**: `backend/tests/unit/test_repo_placa.py` (nuevo, ~80 LOC, 6 tests parametrizados). — **Validación**: `uv run pytest backend/tests/unit/test_repo_placa.py -q` falla con `ImportError` (`parkos_core.repo.placa` no existe) o `ModuleNotFoundError`.

- [x] **T-HU-F1.6-1.2** [RED] — `test_repo_subscripcion_activa.py::validar_subscripcion_vigente` (RED-by-construction)
  - Tests:
    - T1: `prod.subscripciones_cliente(S)` con `vigente_hasta IS NULL`, `estado='activo'`, `fecha_vencimiento >= today` → `validar_subscripcion_vigente(session, uuid_subscripcion_cliente=S, forzado=False)` retorna `SubscripcionValidationResult(vigente=True)`. REQ-OPS-039 scenario "subscripcion vigente procede".
    - T2: `prod.subscripciones_cliente(S)` con `fecha_vencimiento = today - 1 day` → retorna `vigente=False, subscripcion=None` con `forzado=False`. REQ-OPS-039 scenario "subscripcion vencida".
    - T3: misma T2 state con `forzado=True` → retorna `vigente=False` (walk-in auditado; caller procede). REQ-OPS-039 scenario "walk-in".
    - T4: `prod.subscripciones_cliente(S)` con `estado='inactivo'` (vigente en fechas) → retorna `vigente=False`. REQ-OPS-039 scenario "subscripcion inactiva".
  - Patrón F1.4: reusar helper `repo/subscripcion_activa.py` extraído de `resolve_active_subscription_for_exit` (T-PR5-016).
  - **Acción**: importar `validar_subscripcion_activa` from `parkos_core.repo.subscripcion_activa`; sembrar fixtures via SQL directo; asserts sobre `result.vigente`. — **Archivos**: `backend/tests/unit/test_repo_subscripcion_activa.py` (nuevo, ~120 LOC, 4 tests parametrizados). — **Validación**: `ImportError: cannot import name 'validar_subscripcion_vigente'` o `ModuleNotFoundError: subscripcion_activa`.

- [x] **T-HU-F1.6-1.3** [RED] — `test_repo_alerta.py::insertar_alerta_forzado` (RED-by-construction, mock session)
  - Tests:
    - T1: `insertar_alerta_forzado(session, uuid_sucursal=X, uuid_ingreso=I, actor_uuid=A, motivo='cupo agotado por cita medica urgente')` → assert `session.add` llamado con instancia de `Alerta` con `tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`, `uuid_sucursal=X`, `uuid_usuario=A`, `uuid_arqueo=None`, `datos_nuevos == json.dumps({'motivo': 'cupo agotado por cita medica urgente', 'uuid_ingreso': str(I)})` (post-migration 0025 jsonb column).
  - Patrón F1.4 / F1.5: `unittest.mock.AsyncMock(spec=AsyncSession)` para session; `session.add = MagicMock()` para capturar el `Alerta` instance; asserts sobre atributos del mock.
  - **Acción**: importar `insertar_alerta_forzado` from `parkos_core.repo.alerta`; mockear `session.add` y `session.flush`; usar `json.dumps` para comparar `datos_nuevos`. — **Archivos**: `backend/tests/unit/test_repo_alerta.py` (nuevo, ~80 LOC, 1 test). — **Validación**: `ImportError: cannot import name 'insertar_alerta_forzado' from 'parkos_core.repo.alerta'`.

### Section 2: Repo layer GREEN (3 archivos NEW)

- [x] **T-HU-F1.6-2.1** [GREEN] — `repo/placa.py` (~30 LOC)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/repo/placa.py` (nuevo).
  - Contenido: `FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")` + `FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")` (module-level constants, D-HU-F1.6-4, KD-V2 hardcoded MVP); `async def detectar_tipo_vehiculo(session: AsyncSession, placa: str | None) -> uuid_lib.UUID | None` con `if placa is None: return None`, match contra `FORMATO_AUTO` → `'Auto'` / `FORMATO_MOTO` → `'Moto'`, lazy `select(TiposVehiculo.uuid).where(TiposVehiculo.tipo == tipo_nombre, TiposVehiculo.vigente_hasta.is_(None), TiposVehiculo.estado == 'activo')`, `scalar_one_or_none()`.
  - **Acción**: importar `re`, `uuid as uuid_lib`, `select`, `AsyncSession`, `from ..models.V.tipos_vehiculo import TiposVehiculo`; `__all__ = ["FORMATO_AUTO", "FORMATO_MOTO", "detectar_tipo_vehiculo"]`; docstring REQ-OPS-038 + DEC-SUC-22 + D-HU-F1.6-4. — **Validación**: T1.1 (6 tests) PASS; import sin error.

- [x] **T-HU-F1.6-2.2** [GREEN] — `repo/subscripcion_activa.py` (~50 LOC)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py` (nuevo).
  - Contenido: `@dataclass(frozen=True) class SubscripcionValidationResult` con `vigente: bool`, `subscripcion: SubscripcionesCliente | None = None`; `async def validar_subscripcion_vigente(session, *, uuid_subscripcion_cliente: uuid_lib.UUID, forzado: bool = False) -> SubscripcionValidationResult` con SELECT bi-temporal (`vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >= NOW()`), `scalar_one_or_none()`; si row: `SubscripcionValidationResult(vigente=True, subscripcion=row)`; si None y forzado=True: walk-in auditado retorna `vigente=False, subscripcion=None` (caller procede); si None y forzado=False: `vigente=False`. También portar verbatim `resolve_active_subscription_for_exit` desde `api/v1/operacion.py:326-388` (~63 LOC, T-PR5-016) para F7 reuse (R-A5 mitigation: handler imports from single repo surface).
  - **Acción**: importar `uuid_lib`, `datetime`, `date`, `UTC`, `select`, `AsyncSession`, `from ..models.V.subscripcion_vehiculos import SubscripcionVehiculos`, `from ..models.V.subscripciones_cliente import SubscripcionesCliente`, `from ..models.V.vehiculos import Vehiculos`; `__all__ = ["SubscripcionValidationResult", "resolve_active_subscription_for_exit", "validar_subscripcion_vigente"]`; docstring REQ-OPS-039 + R-A5 + R22 defense in depth. — **Validación**: T1.2 (4 tests) PASS; import sin error; `validar_subscripcion_vigente` es `await`-able.

- [x] **T-HU-F1.6-2.3** [GREEN] — `repo/alerta.py` (~60 LOC)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/repo/alerta.py` (nuevo).
  - Contenido: `async def insertar_alerta_forzado(session: AsyncSession, *, uuid_sucursal: uuid_lib.UUID, uuid_ingreso: uuid_lib.UUID, actor_uuid: uuid_lib.UUID, motivo: str) -> Alerta` que crea `Alerta(uuid_sucursal=uuid_sucursal, uuid_usuario=actor_uuid, tipo_alerta='capacidad_agotada_forzado', estado='abierta', timestamp_evento=datetime.now(UTC).replace(tzinfo=None), uuid_arqueo=None)`, asigna `datos_nuevos = json.dumps({"motivo": motivo, "uuid_ingreso": str(uuid_ingreso)})` (post-0025 jsonb column, R-A2 mitigation), `session.add(alerta)`, `await session.flush()` (para popular `alerta.uuid` antes del commit).
  - **Acción**: importar `uuid_lib`, `json`, `datetime`, `UTC`, `AsyncSession`, `from ..models.L_W.alerta import Alerta`; `__all__ = ["insertar_alerta_forzado"]`; docstring REQ-OPS-041.C + R2 + R5 mitigation + R-A1 audit jsonb. — **Validación**: T1.3 (1 test mock) PASS; import sin error.

### Section 3: Handler layer RED (4 archivos de test)

- [x] **T-HU-F1.6-3.1** [RED] — `test_operacion_ingresos_validaciones.py` con 8 parametrized HTTP tests (RED-by-construction)
  - Tests (mapean 8 escenarios del design §9 File 1):
    - T1: `POST /api/v1/operacion/ingresos` con `{"placa": "ABC123"}` (operador- JWT, ctx OK) → 201 con `IngresoReadForzado{tipo_entrada: "ROTACION", forzado_en_creacion: false, motivo_forzado: None}`; DB row inserted. REQ-OPS-034/038/041.
    - T2: `{"placa": "abc123"}` (lowercase) → 422 `{"error": "placa_formato_invalido", "formatos_aceptados": ["ABC123", "ABC12D"]}`; no DB row. REQ-OPS-038.
    - T3: `{"placa": "ABC123", "uuid_subscripcion_cliente": S}` con `subscripciones_cliente(S)` vigente → 201 con `tipo_entrada == "MENSUALIDAD"`. REQ-OPS-039 + V9.
    - T4: `{"placa": "ABC123"}` (sin subscripcion) → 201 con `tipo_entrada == "ROTACION"`. REQ-OPS-041 V9.
    - T5: seed `cantidad_vehiculos_sucursal(X, Auto)=50` + `mv_ocupacion_diaria.activos=50`; `{"placa": "ABC123"}` sin forzado → 422 `{"error": "motivo_forzado_requerido", "cupo_maximo": 50, "activos": 50}`; no DB row. REQ-OPS-035.
    - T6: misma seed T5 + `{"placa": "ABC123", "forzado": true, "observaciones": "[FORZADO: cliente con cita medica urgente 2026-09-14]"}` → 201 + alerta `tipo_alerta=='capacidad_agotada_forzado'` con `datos_nuevos.motivo=='cliente con cita medica urgente 2026-09-14'`; ambos rows (ingreso + alerta) presentes tras commit (R5 verification). REQ-OPS-035 + REQ-OPS-041.C.
    - T7: insert prior `prod.ingreso(X, ABC123)` sin salidas/anulaciones; `{"placa": "ABC123"}` → 409 `{"error": "ingreso_activo_existente", "uuid_ingreso_existente": <prior_uuid>}`; no new row. REQ-OPS-040.
    - T8: `{"placa": "abc123", "uuid_subscripcion_cliente": S}` → 422 `placa_formato_invalido` (NO `subscripcion_inactiva_o_vencida`); locks V5-before-V6 order. R7 invariante.
  - Patrón F1.3 / F1.5: `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-` fixture de `tests/unit/test_auth_login_password.py`; real `pg_engine` con `PARKOS_DOCKER_TEST=1`.
  - **Acción**: parametrizar `pytest.mark.parametrize("test_case", [T1..T8])`; usar fixtures `operator_jwt`, `seed_tipos_vehiculo`, `seed_cantidad_vehiculos_sucursal`, `seed_mv_ocupacion_diaria`, `seed_subscripciones_cliente`; assert response shape via `pydantic.IngresoReadForzado.model_validate(response.json())`. — **Archivos**: `backend/tests/unit/test_operacion_ingresos_validaciones.py` (nuevo, ~400 LOC, 8 tests parametrizados). — **Validación**: `uv run pytest backend/tests/unit/test_operacion_ingresos_validaciones.py -q` falla con `ImportError` de `IngresoCreateForzado`/`IngresoReadForzado` o `404 Not Found` (handler no actualizado) o `pydantic.ValidationError` (campo `tipo_entrada` faltante en response).

- [x] **T-HU-F1.6-3.2** [RED] — `test_operacion_ingresos_kd_forzado.py` con 4 KD-FORZADO unit tests (RED-by-construction)
  - Tests (mapean KD-FORZADO-01):
    - T1: `validar_kd_forzado("[FORZADO: cliente con cita medica urgente]", True) == "cliente con cita medica urgente"` (stripped).
    - T2: `validar_kd_forzado("cliente sin placa", True)` raises `HTTPException(422, {"error": "motivo_forzado_requerido"})`.
    - T3: `validar_kd_forzado("[FORZADO: a b]", True)` raises 422 con `error == "motivo_forzado_insuficiente", min_chars == 10`.
    - T4: `validar_kd_forzado("[FORZADO: prueba cliente]", False)` raises 422 con `error == "forzado_contradiccion"`.
  - Pure helper tests (sin HTTP, sin DB).
  - **Acción**: importar `validar_kd_forzado` from `parkos_core.repo.ingreso`; `pytest.raises(HTTPException)` con match de `detail`. — **Archivos**: `backend/tests/unit/test_operacion_ingresos_kd_forzado.py` (nuevo, ~150 LOC, 4 tests). — **Validación**: `ImportError: cannot import name 'validar_kd_forzado' from 'parkos_core.repo.ingreso'`.

- [x] **T-HU-F1.6-3.3** [RED] — `test_ingreso_create_db.py` con 3 DB integration tests (RED-by-construction, `PARKOS_DOCKER_TEST=1`)
  - Tests (mapean design §9 File 4):
    - T1: `test_insert_ingreso_con_alerta_capacidad_agotada_same_tx` — seed `cantidad=50, activos=50` + `mv_refresh`; POST con prefix válido → assert ambas filas (`prod.ingreso` + `prod.alerta`) presentes tras commit; `prod.alerta.tipo_alerta == 'capacidad_agotada_forzado'`, `datos_nuevos.motivo == '<stripped>'` (jsonb parse). R5 single-commit verification.
    - T2: `test_duplicado_activo_rechazado_con_uuid_ingreso_existente` — insert prior `prod.ingreso(X, ABC123)`; POST → 409 con `uuid_ingreso_existente` matching prior UUID; new DB row absent. REQ-OPS-040.
    - T3: `test_subscripcion_vencida_returns_422_sin_forzado` — seed `subscripciones_cliente(S)` con `fecha_vencimiento = today - 1`; POST `{"placa": "ABC123", "uuid_subscripcion_cliente": S}` → 422 con `error == "subscripcion_inactiva_o_vencida"`. REQ-OPS-039.
  - Patrón F1.3 / F1.8: sembrar fixtures via SQL directo al engine de testcontainers; cleanup con `await session.rollback()` + `DELETE FROM`.
  - **Acción**: usar `pg_engine` fixture (testcontainers precedent F1.4); sembrar `prod.sucursal`, `prod.tipos_vehiculo`, `prod.cantidad_vehiculos_sucursal`, `prod.subscripciones_cliente`, refresh `prod.mv_ocupacion_diaria`; asserts sobre `prod.ingreso.count(*)`, `prod.alerta.datos_nuevos` (jsonb parse con `json.loads`). — **Archivos**: `backend/tests/integration/test_ingreso_create_db.py` (nuevo, ~250 LOC, 3 tests). — **Validación**: `uv run pytest backend/tests/integration/test_ingreso_create_db.py -q` con `PARKOS_DOCKER_TEST=1` falla con `ImportError` de `repo/alerta.py::insertar_alerta_forzado` o `column "datos_nuevos" does not exist` (pre-0025).

- [x] **T-HU-F1.6-3.4** [RED] — `test_kd_forzado_in_handler.py` AST walk (RED-by-construction, sin DB)
  - Test (mapea R7 invariante):
    - T1: `test_create_ingreso_handler_invoca_helpers_en_orden_correcto` — `ast.parse()` sobre `api/v1/operacion.py`; localizar `create_ingreso` via `ast.walk` + `ast.FunctionDef.name == 'create_ingreso'`; extraer secuencia de `ast.Call` nodes whose function name matches uno de `[detectar_tipo_vehiculo, validar_tipo_vehiculo_vigente, validar_kd_forzado, validar_cupo_disponible, validar_tarifa_vigente, validar_subscripcion_vigente, existe_ingreso_activo, crear_ingreso_evento, insertar_alerta_forzado, record_event]`; assert order matches D-HU-F1.6-11 (regex → tipo → KD-FORZADO → cupo → tarifa → sub → no-dup → INSERT). R7 CI gate contra future-dev reordering.
  - Patrón F1.3 / F1.5: AST walks previos (`test_no_write_in_ocupacion.py`, `test_kd_chain_in_handler.py`).
  - **Acción**: usar `ast.parse()` + `ast.walk()` + `ast.FunctionDef` + `ast.Call`; extraer `call.func.id` o `call.func.attr` (cubrir tanto calls directos como via `repo.subscripcion_activa.validar_subscripcion_vigente`); assert con `pytest` secuencia exacta. — **Archivos**: `backend/tests/static/test_kd_forzado_in_handler.py` (nuevo, ~80 LOC, 1 test). — **Validación**: `ImportError` o `AssertionError` por helper no encontrado en secuencia (handler F1.5 thin pass-through no invoca helpers).

### Section 4: Handler layer GREEN (handler + 2 MODIFIED `repo/*.py`)

- [x] **T-HU-F1.6-4.1** [GREEN] — Replace `create_ingreso` en `api/v1/operacion.py` (lines 92-114 → ~232 LOC)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modificado, replace).
  - Contenido (11-step sequence per design §7):
    1. KD-3: `target = payload.uuid_sucursal or ctx.sucursal_uuid; if not target: 400 missing_sucursal_context; if ctx.issuer_prefix == "operador-" and target != ctx.sucursal_uuid: 403 tenant_scope_violation`.
    2. V5: `uuid_tipo_vehiculo = await detectar_tipo_vehiculo(session, payload.placa); if None: 422 placa_formato_invalido {formatos_aceptados: ["ABC123", "ABC12D"]}` (D-HU-F1.6-6 server overwrites client value).
    3. V4: `if not await validar_tipo_vehiculo_vigente(session, uuid_tipo_vehiculo=uuid_tipo_vehiculo): 422 tipo_vehiculo_invalido` (KD-V3 no bypass on catalog defect).
    4. KD-FORZADO-01: `motivo = validar_kd_forzado(payload.observaciones, payload.forzado); bypass_reason: str | None = "forzado" if motivo else None`.
    5. V1+V2: `cupo_result = await validar_cupo_disponible(session, uuid_sucursal=target, uuid_tipo_vehiculo=uuid_tipo_vehiculo, forzado=bool(bypass_reason)); if cupo_result.cupo_no_configurado: 422 cupo_no_configurado {forzado_permitido: True}; if cupo_result.cupo_agotado: if not bypass_reason: 422 motivo_forzado_requerido {cupo_maximo, activos}; else: bypass_reason = "cupo_agotado"`.
    6. V3: `tarifa_result = await validar_tarifa_vigente(session, uuid_sucursal=target, uuid_tipo_vehiculo=uuid_tipo_vehiculo, at=datetime.now(UTC).replace(tzinfo=None), forzado=bool(bypass_reason)); if not tarifa_result.vigente and not bypass_reason: 422 tarifa_vigente_no_encontrada`.
    7. V6: `if payload.uuid_subscripcion_cliente: sub_result = await validar_subscripcion_vigente(session, uuid_subscripcion_cliente=payload.uuid_subscripcion_cliente, forzado=bool(bypass_reason)); if not sub_result.vigente and not bypass_reason: 422 subscripcion_inactiva_o_vencida`.
    8. V8: `uuid_activo = await existe_ingreso_activo(session, uuid_sucursal=target, placa=payload.placa); if uuid_activo: 409 ingreso_activo_existente {uuid_ingreso_existente: str(uuid_activo)}` (D-HU-F1.6-3 sin lock pesimista).
    9. INSERT + alerta (same TX): `new_attrs = payload.model_dump(exclude_none=True, exclude={"forzado"}); new_attrs["uuid_tipo_vehiculo"] = uuid_tipo_vehiculo; new_row = await crear_ingreso_evento(session, actor_uuid=ctx.actor_uuid, new_attrs=new_attrs); if bypass_reason == "cupo_agotado": await insertar_alerta_forzado(session, uuid_sucursal=target, uuid_ingreso=new_row.uuid, actor_uuid=ctx.actor_uuid, motivo=motivo or "(sin motivo)"); await session.commit()` (UN solo commit, R5).
    10. V9 derivation: `tipo_entrada: Literal["MENSUALIDAD", "ROTACION"] = "MENSUALIDAD" if payload.uuid_subscripcion_cliente else "ROTACION"` (DEC-SUC-21, keyed on subscripcion NOT on forzado).
    11. Response: `response.headers["Cache-Control"] = "no-store"; return IngresoReadForzado(**IngresoRead.model_validate(new_row).model_dump(), tipo_entrada=tipo_entrada, forzado_en_creacion=bypass_reason is not None, motivo_forzado=motivo if bypass_reason else None)`.
  - **Acción**: append imports (`from datetime import UTC, datetime`, `from ..repo.placa import detectar_tipo_vehiculo`, `from ..repo.ingreso import (validar_tipo_vehiculo_vigente, validar_kd_forzado, existe_ingreso_activo, crear_ingreso_evento, insertar_alerta_forzado)`, `from ..repo.ocupacion import validar_cupo_disponible`, `from ..repo.tarifas_vigencia import validar_tarifa_vigente`, `from ..repo.subscripcion_activa import validar_subscripcion_vigente`, `from ..schemas.operacion import IngresoCreateForzado, IngresoReadForzado, IngresoRead`); mantener `_ingreso_issuer_dep`, `get_tenant_ctx`, `get_session` chain intactos; docstring REQ-OPS-034..041 + D-HU-F1.6-7 + D-HU-F1.6-11. — **Validación**: T3.1 (8 tests) PASS, T3.4 (1 AST walk) PASS; `git diff backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` vacío; `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` vacío (CI gate `factory_intact`); `git diff backend/packages/parkos_core/src/parkos_core/api/deps.py` vacío; `git diff backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` vacío (CI gate `auth_tenancy_intact`).

- [x] **T-HU-F1.6-4.2** [GREEN] — `repo/ingreso.py` NEW (~180 LOC, 8 helpers + KD-FORZADO + alerta re-export)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` (nuevo).
  - Contenido: module-level `FORZADO_PREFIX = "[FORZADO: "`, `FORZADO_MIN_MOTIVO_CHARS = 10` (R-A1 audit constants); `async def validar_tipo_vehiculo_vigente(session, *, uuid_tipo_vehiculo) -> bool` (V4, NO honor `forzado`, KD-V3); `async def existe_ingreso_activo(session, *, uuid_sucursal, placa) -> uuid_lib.UUID | None` con `text(...)` EXISTS query (V8, NO lock pesimista, D-HU-F1.6-3); `def validar_kd_forzado(observaciones, forzado) -> str | None` con 3 discriminadores `HTTPException(422, ...)` (KD-FORZADO-01); `async def crear_ingreso_evento(session, *, actor_uuid, new_attrs) -> Ingreso` thin wrapper de `record_event(Ingreso, log_tx=True)`; re-exports `validar_cupo_disponible` (from `repo/ocupacion.py`), `validar_tarifa_vigente` (from `repo/tarifas_vigencia.py`), `insertar_alerta_forzado` (from `repo/alerta.py`), `validar_subscripcion_vigente` (from `repo/subscripcion_activa.py`); `__all__ = ["FORZADO_PREFIX", "FORZADO_MIN_MOTIVO_CHARS", "validar_tipo_vehiculo_vigente", "existe_ingreso_activo", "validar_kd_forzado", "crear_ingreso_evento", "validar_cupo_disponible", "validar_tarifa_vigente", "validar_subscripcion_vigente", "insertar_alerta_forzado"]`.
  - **Acción**: importar `uuid_lib`, `HTTPException`, `select`, `text`, `AsyncSession`, `from ..models.L_E.ingreso import Ingreso`, `from ..models.V.tipos_vehiculo import TiposVehiculo`, `from .event import record_event`, `from .ocupacion import validar_cupo_disponible`, `from .tarifas_vigencia import validar_tarifa_vigente`, `from .subscripcion_activa import validar_subscripcion_vigente`, `from .alerta import insertar_alerta_forzado`; `git diff backend/packages/parkos_core/src/parkos_core/repo/event.py` vacío (CI gate `event_helper_intact`). — **Validación**: T1.3 (1 mock test), T3.1 (8 tests), T3.2 (4 KD tests), T3.4 (1 AST walk) todos PASS.

- [x] **T-HU-F1.6-4.3** [GREEN] — `repo/ocupacion.py` MODIFY (+40 LOC: `validar_cupo_disponible` + `CupoValidationResult`)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` (modificado, append post-`get_ocupacion_puros_activos`).
  - Contenido: `@dataclass(frozen=True) class CupoValidationResult` con `cupo_no_configurado: bool`, `cupo_agotado: bool`, `cupo_maximo: int`, `activos: int`; `async def validar_cupo_disponible(session, *, uuid_sucursal, uuid_tipo_vehiculo, forzado=False) -> CupoValidationResult` que llama `get_ocupacion_puros_activos(session, uuid_sucursal=uuid_sucursal)`, busca match por `uuid_tipo_vehiculo`, si no match o `match.cupo_maximo == 0` → `cupo_no_configurado=True`; si `match.activos >= match.cupo_maximo and not forzado` → `cupo_agotado=True`; sino OK.
  - **Acción**: importar `dataclass`; append post-`get_ocupacion_puros_activos` (F1.5); docstring REQ-OPS-034/035 + KD-V4 + R2. — **Validación**: T3.1 T5/T6 PASS; import sin error.

- [x] **T-HU-F1.6-4.4** [GREEN] — `repo/tarifas_vigencia.py` MODIFY (+30 LOC: `validar_tarifa_vigente` + `TarifaValidationResult`)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (modificado, append post-`list_tarifas_vigentes`).
  - Contenido: `@dataclass(frozen=True) class TarifaValidationResult` con `vigente: bool`, `tarifa: TarifasSucursal | None = None`; `async def validar_tarifa_vigente(session, *, uuid_sucursal, uuid_tipo_vehiculo, at: datetime, forzado=False) -> TarifaValidationResult` con `v_utc = _to_utc_naive(at); stmt = select(TarifasSucursal).where(TarifasSucursal.uuid_sucursal == uuid_sucursal, TarifasSucursal.uuid_tipo_vehiculo == uuid_tipo_vehiculo, bitemporal_vigente_predicate(TarifasSucursal, v_utc)).limit(1); row = (await session.execute(stmt)).scalar_one_or_none(); if row: return TarifaValidationResult(vigente=True, tarifa=row); return TarifaValidationResult(vigente=False, tarifa=None)` (reusa `bitemporal_vigente_predicate` F1.4 verbatim).
  - **Acción**: importar `dataclass`, `datetime`; reusar `_to_utc_naive` + `bitemporal_vigente_predicate` ya existentes (F1.4); docstring REQ-OPS-036 + bi-temporal canónico F1.4. — **Validación**: T3.1 PASS; `git diff backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` solo agrega, no modifica funciones existentes (F1.4 CI gate `tarifas_vigencia_intact`).

### Section 5: Schemas + handler integration (2 tasks)

- [x] **T-HU-F1.6-5.1** [GREEN] — `schemas/operacion.py` MODIFY (+80 LOC: `IngresoCreateForzado`, `IngresoReadForzado`, 7 error classes)
  - Archivo: `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (modificado, append post-F1.8 block).
  - Contenido:
    - `class IngresoCreateForzado(_Base)` con `model_config = ConfigDict(extra="forbid")`, fields `uuid_sucursal: uuid_lib.UUID | None = None`, `placa: str | None = None`, `uuid_tipo_vehiculo: uuid_lib.UUID | None = None` (server overwrites via V5), `uuid_subscripcion_cliente: uuid_lib.UUID | None = None`, `fecha_ingreso: datetime | None = None`, `observaciones: str | None = None`, `forzado: bool = False` (D-HU-F1.6-5).
    - `class IngresoReadForzado(_Base)` con fields inherited (uuid, created_at, created_by, sync_status, sync_timestamp, sync_attempts, uuid_sucursal, placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente, fecha_ingreso, observaciones) + `tipo_entrada: Literal["MENSUALIDAD", "ROTACION"]`, `forzado_en_creacion: bool = False`, `motivo_forzado: str | None = None`.
    - 7 error classes: `CupoNoConfiguradoError(_Base)` (`error: Literal["cupo_no_configurado"]`, `forzado_permitido: Literal[True]`); `MotivoForzadoRequeridoError(_Base)` (`error: Literal["motivo_forzado_requerido"]`, `cupo_maximo: int`, `activos: int`); `TarifaVigenteNoEncontradaError(_Base)` (`error: Literal["tarifa_vigente_no_encontrada"]`); `PlacaFormatoInvalidoError(_Base)` (`error: Literal["placa_formato_invalido"]`, `formatos_aceptados: list[str]`); `SubscripcionInactivaOVencidaError(_Base)` (`error: Literal["subscripcion_inactiva_o_vencida"]`); `IngresoActivoExistenteError(_Base)` (`error: Literal["ingreso_activo_existente"]`, `uuid_ingreso_existente: uuid_lib.UUID`); `TipoVehiculoInvalidoError(_Base)` (`error: Literal["tipo_vehiculo_invalido"]`).
  - **Acción**: importar `Literal` de `typing`; append al final post-F1.8 block; mantener `IngresoCreate`/`IngresoRead`/`IngresoReadList`/`IngresoFilter` como deprecated aliases (backward compat F1.5); docstring REQ-OPS-034..041 + D-HU-F1.6-10. — **Validación**: T3.1 PASS; `extra='forbid'` heredado de `_Base`; `IngresoCreateForzado.model_validate({"tipo_entrada": "ROTACION"})` raises 422 Pydantic (extra field rejected, R6 mitigation).

- [x] **T-HU-F1.6-5.2** [GREEN] — Modify `repo/subscripcion_activa.py` para re-export `validar_subscripcion_vigente` desde `parkos_core.repo.ingreso` (R-A5 mitigation)
  - Contenido: confirmar que `__all__` en `repo/subscripcion_activa.py` incluye `validar_subscripcion_vigente`; confirmar que `repo/ingreso.py` re-exporta `validar_subscripcion_vigente` desde `repo/subscripcion_activa.py` (single import surface para handler).
  - **Acción**: audit imports — handler debe importar `validar_subscripcion_vigente` desde `parkos_core.repo.ingreso` (single surface); `repo/subscripcion_activa.py` mantiene ambas firmas (`validar_subscripcion_vigente` V6 + `resolve_active_subscription_for_exit` F7). — **Validación**: T3.1 PASS; `from parkos_core.repo.ingreso import validar_subscripcion_vigente` resuelve sin error.

### Section 6: Static guards (AST walks, 2 archivos)

- [x] **T-HU-F1.6-6.1** [GREEN] — `tests/static/test_no_write_after_insert.py` (defense in depth, ~100 LOC, 1 AST walk)
  - Test: `test_crear_ingreso_evento_rechaza_update_delete_truncate` — AST-walk `repo/ingreso.py::crear_ingreso_evento`; rechazar `UPDATE | DELETE | TRUNCATE | FOR UPDATE | FOR SHARE` literals en el cuerpo (case-insensitive, fuera de strings/comentarios). Locks R-A3 insert-only contract sobre `prod.ingreso` post-creación.
  - Patrón F1.3 / F1.5 / F1.8 precedents (`test_no_write_in_ocupacion.py`, `test_no_write_in_calcular_cotizacion.py`).
  - **Acción**: usar `ast.parse()` sobre `repo/ingreso.py`; localizar `crear_ingreso_evento` via `ast.walk` + `ast.FunctionDef.name == 'crear_ingreso_evento'`; tokenizar identifiers + strings; rechazar tokens case-insensitive que contengan `UPDATE`, `DELETE`, `TRUNCATE`, `MERGE`, `FOR UPDATE`, `FOR SHARE`; reportar primer match ofensivo con línea. — **Archivos**: `backend/tests/static/test_no_write_after_insert.py` (nuevo, ~100 LOC, 1 test). — **Validación**: PASS (handler creado en T4.1 + repo en T4.2 no contienen write verbs).

- [x] **T-HU-F1.6-6.2** [GREEN] — `tests/static/test_kd_forzado_in_handler.py` (R7 invariante, ~80 LOC, 1 AST walk)
  - Test: `test_create_ingreso_handler_invoca_helpers_en_orden_correcto` — AST-walk `api/v1/operacion.py::create_ingreso`; extraer secuencia de `ast.Call` nodes whose function name matches uno de `[detectar_tipo_vehiculo, validar_tipo_vehiculo_vigente, validar_kd_forzado, validar_cupo_disponible, validar_tarifa_vigente, validar_subscripcion_vigente, existe_ingreso_activo, crear_ingreso_evento, insertar_alerta_forzado, record_event]`; assert order matches D-HU-F1.6-11 (regex → tipo → KD-FORZADO → cupo → sub → no-dup → INSERT → alerta). R7 invariante — CI gate contra future-dev reordering.
  - Patrón F1.3 / F1.5 precedents.
  - **Acción**: usar `ast.parse()` + `ast.walk()` + `ast.FunctionDef` + `ast.Call`; extraer `call.func.id` o `call.func.attr` (cubrir calls directos y via `repo.X.Y`); assert con secuencia exacta. — **Archivos**: `backend/tests/static/test_kd_forzado_in_handler.py` (nuevo, ~80 LOC, 1 test). — **Validación**: PASS (handler T4.1 invoca helpers en orden correcto).

### Section 7: Refactor (2 tasks)

- [x] **T-HU-F1.6-7.1** [REFACTOR] — Extract `_cotizar_no_store_headers()` helper en `api/v1/_helpers.py` (R-A6 mitigation)
  - Contenido: helper compartido `_cotizar_no_store_headers() -> dict[str, str]` que retorna `{"Cache-Control": "no-store"}`; usar en TODAS las `HTTPException(...)` raises del handler `create_ingreso` (11 raises: 400, 403, 422×7, 409). Reemplaza los headers repetidos inline en F1.5/F1.8 precedents.
  - **Acción**: crear `api/v1/_helpers.py` (nuevo, ~10 LOC); modificar `operacion.py` para usar `headers=_cotizar_no_store_headers()` en cada raise; docstring R-A6. — **Validación**: T3.1 (8 tests) sigue PASS; `ruff check` clean; no regression en F1.5/F1.8 precedents que también usan este helper.

- [x] **T-HU-F1.6-7.2** [REFACTOR] — Reduce handler docstrings to 1-line + extract KD-FORZADO chain a `repo/ingreso.py::validar_kd_forzado_chain()` private helper
  - Contenido: handler `create_ingreso` docstring reduce a 1-line summary + REQ-OPS-034..041 reference; KD-FORZADO chain (steps 4-5-6-7 with `bypass_reason` propagation) encapsulado en `repo/ingreso.py::validar_kd_forzado_chain(...)` private helper; el handler solo llama el helper y recibe el `bypass_reason`.
  - **Acción**: añadir private helper (~30 LOC) en `repo/ingreso.py`; handler simplified (~190 LOC, vs 232); tests T3.1/T3.2 siguen PASS sin modificación. — **Validación**: T3.1 (8 tests), T3.2 (4 KD tests), T3.4 (1 AST walk) siguen PASS; `ruff check` clean; T3.4 sigue verificando orden literal (helper extraído mantiene orden).

### Section 8: Verification (2 tasks)

- [x] **T-HU-F1.6-8.1** [VERIFICATION] — Suite completa verde + 0 CRITICAL + no regresión F1.5/F1.4/F1.3
  - **Acción**: ejecutar `uv run pytest -q backend/tests/unit/test_operacion_ingresos_validaciones.py backend/tests/unit/test_operacion_ingresos_kd_forzado.py backend/tests/unit/test_repo_placa.py backend/tests/unit/test_repo_subscripcion_activa.py backend/tests/unit/test_repo_alerta.py backend/tests/integration/test_ingreso_create_db.py backend/tests/integration/test_migration_0025_datos_nuevos.py backend/tests/static/test_no_write_after_insert.py backend/tests/static/test_kd_forzado_in_handler.py` → objetivo **9 archivos / ~22 tests passed**, 0 CRITICAL failures. Adicional: ejecutar `uv run pytest -q backend/tests/` (suite completa) → 0 regresiones en F1.5/F1.4/F1.3 (las fallas preexistentes documentadas en baseline F1.8 se mantienen sin nuevos archivos fallando). — **Archivos**: ninguno nuevo (verifica toda la suite). — **Validación**: log muestra `~22 passed` en suite F1.6 + suite completa sin nuevos CRITICAL; ningún test previo en estado `FAILED` o `ERROR` atribuible a F1.6.

- [x] **T-HU-F1.6-8.2** [VERIFICATION] — ruff + mypy --strict + factory_intact + event_helper_intact + auth_tenancy_intact
  - **Acción**: ejecutar en orden:
    1. `uv run ruff check backend/packages/parkos_core/migrations/versions/0025_add_alerta_datos_nuevos_and_alert_type.py backend/packages/parkos_core/src/parkos_core/repo/placa.py backend/packages/parkos_core/src/parkos_core/repo/ingreso.py backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py backend/packages/parkos_core/src/parkos_core/repo/alerta.py backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py backend/packages/parkos_core/src/parkos_core/schemas/operacion.py backend/tests/unit/test_operacion_ingresos_validaciones.py backend/tests/unit/test_operacion_ingresos_kd_forzado.py backend/tests/unit/test_repo_placa.py backend/tests/unit/test_repo_subscripcion_activa.py backend/tests/unit/test_repo_alerta.py backend/tests/integration/test_ingreso_create_db.py backend/tests/integration/test_migration_0025_datos_nuevos.py backend/tests/static/test_no_write_after_insert.py backend/tests/static/test_kd_forzado_in_handler.py` → `All checks passed!`.
    2. `uv run ruff format --check` sobre los 11 archivos de implementación → exit 0.
    3. `uv run mypy --strict backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py backend/packages/parkos_core/src/parkos_core/repo/placa.py backend/packages/parkos_core/src/parkos_core/repo/ingreso.py backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py backend/packages/parkos_core/src/parkos_core/repo/alerta.py backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` → `Success: no issues found`.
    4. CI gates: `git diff backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` → vacío; `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` → vacío (`factory_intact`); `git diff backend/packages/parkos_core/src/parkos_core/api/deps.py` → vacío; `git diff backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` → vacío (`auth_tenancy_intact`); `git diff backend/packages/parkos_core/src/parkos_core/repo/event.py` → vacío (`event_helper_intact`); `git diff backend/packages/parkos_core/src/parkos_core/jobs/runner.py` → vacío (`worker_base_intact`).
  - **Archivos**: ninguno nuevo (verifica lint + type + gates). — **Validación**: ruff + mypy + 6 CI gates todos verdes; ningún archivo nuevo/modificado introduce pre-existing housekeeping.

## Cross-phase constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` ni `FOR UPDATE|SHARE` en `create_ingreso` handler — AST walk `test_no_write_after_insert.py` (T6.1) lo enforza en CI sobre `repo/ingreso.py::crear_ingreso_evento`.
- NO `Co-authored-by:` ni trailers AI en commits; conventional commits, español neutral.
- NO SQLite en tests — `pg_engine` real o `testcontainers[postgres]` (precedente F1.4/F1.5).
- NO modificación de `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate.
- NO modificación de `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate (no aplica a F1.6 pero se mantiene como gate cross-cutting).
- NO modificación de `api/v1/__init__.py` — el router ya estaba montado.
- NO modificación de `api/deps.py` ni `auth/tenancy.py` — reusan KD-3 chain + errores tipados intactos.
- NO modificación de `repo/event.py` — `event_helper_intact` CI gate (el handler reusa `record_event` verbatim).
- NO modificación de `repo/tarifas_vigencia.py::list_tarifas_vigentes` — F1.4 intact; solo append `validar_tarifa_vigente` (+30 LOC).
- NO `correlacion_id` en el body (DEC-IDEM-01) — header `Idempotency-Key` via PR2 middleware.
- NO `CHECK constraint` sobre `prod.ingreso.placa` (A-03) — regex server-side + KD-V2 hardcoded.
- NO lock pesimista (`SELECT … FOR UPDATE/SHARE`) sobre `prod.ingreso` / `prod.salidas` / `prod.anulaciones` desde el endpoint (KD-V4, R8).
- NO `forzado` ni `tipo_entrada` columnas en `prod.ingreso` (DEC-SUC-21 + KD-FORZADO-01) — derivado server-side, devuelto en respuesta, NUNCA persistido.
- Header `Cache-Control: no-store` en TODA respuesta 2xx/4xx/5xx del endpoint (consistente con F1.3/F1.5/F1.8 precedents).
- Discriminadores de error estables: `missing_sucursal_context` (400), `tenant_scope_violation` (403 operador), `sucursal_not_permitted` (403 admin), `placa_formato_invalido` (422 V5), `tipo_vehiculo_invalido` (422 V4), `forzado_contradiccion` (422 KD-FORZADO-01), `motivo_forzado_requerido` (422 KD-FORZADO-01/V2), `motivo_forzado_insuficiente` (422 KD-FORZADO-01), `cupo_no_configurado` (422 V1), `tarifa_vigente_no_encontrada` (422 V3), `subscripcion_inactiva_o_vencida` (422 V6), `ingreso_activo_existente` (409 V8).
- Precedencia de errores (D-HU-F1.6-11): KD-3 (400/403) > V5 (422 placa) > V4 (422 tipo) > KD-FORZADO (422) > V1+V2 (422 cupo) > V3 (422 tarifa) > V6 (422 sub) > V8 (409 dup) > 201.
- Migration `0025` debe usar `INSERT ... ON CONFLICT (tipo_alerta) DO NOTHING` (alert_types_inmutable trigger bloquea UPDATE/DELETE para non-superuser); downgrade corre como superuser en alembic.
- `datos_nuevos` JSONB column (post-0025) carries motivo + uuid_ingreso para auditoría (R-A2 mitigation).
- `prod.alerta.datos_nuevos` parseable via `json.loads()` en tests integración (T3.3 T1).
- Orden de invocaciones del handler estricto (D-HU-F1.6-11): KD-3 → V5 → V4 → KD-FORZADO → V1+V2 → V3 → V6 → V8 → INSERT → alerta (same TX) → V9 derivar → 201. AST walk (T3.4 + T6.2) verifica literal order.
- `bypass_reason` discriminator: `None` → `"forzado"` (after KD-FORZADO-01 pass) → `"cupo_agotado"` (after V2 bypass). Alerta INSERT solo si `bypass_reason == "cupo_agotado"` (R2 mitigation).
- Tope por commit: <800 LOC. Apply-código ≤587 LOC (commit 1), tests+verification ≤800 LOC (commit 2).
- Mensajes conventional commit; cuerpo técnico en español neutral.

## Acceptance Gates

- TDD strict: RED primero, GREEN mínimo, REFACTOR último.
- 23 tasks completados en orden: T0.1 → T1.1..T1.3 → T2.1..T2.3 → T3.1..T3.4 → T4.1..T4.4 → T5.1..T5.2 → T6.1..T6.2 → T7.1..T7.2 → T8.1..T8.2.
- Conventional commit atómico (2 commits en 1 PR): commit 1 `feat(backend): anadir migration 0025 + validaciones server-side POST /operacion/ingresos para HU-F1.6` (~587 LOC); commit 2 `test(backend): anadir 6 archivos de tests para HU-F1.6 validaciones post-ingresos` (~1,160 LOC). Sin `Co-authored-by:`, sin trailers IA.
- Tests pasan contra DB real con `PARKOS_DOCKER_TEST=1`: 8 HTTP unit (T3.1) + 4 KD-FORZADO unit (T3.2) + 6 regex unit (T1.1) + 4 subsc unit (T1.2) + 1 alerta mock (T1.3) + 3 DB integration (T3.3) + 3 migration (T0.1) + 1 AST walk no-write (T6.1) + 1 AST walk order (T6.2) = **~31 tests nuevos en 9 archivos**.
- ruff + mypy --strict clean sobre los 11 archivos nuevos/modificados (1 migration + 8 backend + 6 tests = 15 archivos total menos重叠).
- 6 CI gates verdes: `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `tarifas_vigencia_intact`, `worker_base_intact`.
- 0 regresiones introducidas por F1.6; las fallas preexistentes documentadas en baseline F1.8 se mantienen sin nuevos archivos fallando.
- REQ-OPS-034..041 traceability verificada: cada REQ tiene ≥1 RED test que la prueba (T3.1 + T3.3 mapping).
- Threat matrix §10 verificada: T1 SQL injection → V5 regex rechaza; T2 cross-tenant → KD-3 chain; T3 stale client UUID → V5 server overwrite; T4 motivo corto → KD-FORZADO 422; T5 MV lag → KD-V4 eventual consistency; T6 alerta huérfana → same TX; T7 future-dev reorder → AST walk; T8 pgcode leak → typed Pydantic errors.
- Architecture risks §13 (R-A1..R-A7) verificadas: R-A1 alert_types_inmutable trigger respetado (idempotent INSERT); R-A2 jsonb audit column post-0025; R-A3 insert-only enforced por T6.1 AST; R-A5 single import surface via `repo/ingreso.py` re-exports; R-A6 `_cotizar_no_store_headers()` helper extract en T7.1; R-A7 KD-FORZADO chain extracted en T7.2.

## Out of Scope Tasks

- Visibilidad cross-branch global para `admin-`. Sale del scope: KD-3 acota a `claims["sucursales_permitidas"]`.
- Push de `cupo` vía websocket / SSE. Sale del scope: cliente hace polling 10s (`plan.md:1422-1442`).
- Mitigación de RIESGO-SUC-02 (lag máximo 10s). Sale del scope: el corpus ya lo documenta como riesgo vivo aceptado; KD-V4 eventual consistency.
- Endpoint `GET /operacion/ingresos/{uuid}/validar` (preview sin INSERT). Sale del scope: handler hace insert o 422, sin preview.
- Lock pesimista sobre `prod.ingreso` / `prod.salidas` / `prod.anulaciones`. Sale del scope (D-HU-F1.6-3).
- Indexación adicional sobre `prod.ingreso` para V8. Sale del scope: índice `(uuid_sucursal, placa, created_at)` post-F1.5 mantiene < 50ms p99.
- Versión de UI cliente (Fase 2 frontend — `web_sucursal` debe desactivar `lib/validation/placa.ts` A-03 cuando este endpoint esté en producción). F1.6 NO modifica el cliente; cleanup post-archive.
- Workflow de anulación (`prod.anulaciones` workflow para revertir ingreso post-creación). DEC-ANUL-01 delega a Fase 7+.
- `correlacion_id` en el payload. DEC-IDEM-01 delega idempotencia al header `Idempotency-Key` (PR2 middleware).
- Regex configurable (catálogo, settings, JSON, BD). A-03 / KD-V2 hardcoded para MVP; configurable en HU futura con cat tabla.
- Migración nacional de formatos de placa (e.g. Mercosur 2027). KD-V2 hardcoded para MVP.
- Permisos RBAC diferenciados para `forzado` (e.g. "solo admin-"). KD-V8 acepta ambos `operador-` y `admin-` para MVP.
- Alertas adicionales (`placa_no_reconocida_forzado`, `subscripcion_sin_vehiculo`). Solo se inserta `capacidad_agotada_forzado` (R2 mitigation).
- Métricas / observabilidad del handler (contador `forzado=true`, latencia p99). Alineado con HU-F1.X de observabilidad (futuro).
- Auto-cleanup de huérfanos. Owner decide manualmente.
- Aplicar el mismo patrón bi-temporal canónico a otras tablas `[V]` (e.g. `cantidad_vehiculos_sucursal`). Sale del scope de F1.6 (ya reusado via `bitemporal_vigente_predicate`).
- Circuit breaker / retry budget sobre alerta INSERT. Sale del scope: FK commit ordering garantiza no huérfanas.

## References

- `exploration.md`, `proposal.md`, `specs/operational/spec.md`, `design.md` en `openspec/changes/hu-f1-6-validaciones-post-ingresos/`.
- Precedente F1.5: `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/tasks.md` (18 tasks T-HU-F1.5-1..18, MV + KD-7 pre-flight + AST walk pattern, commit `fc72adb`).
- Precedente F1.4: `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/tasks.md` (8 tasks T-HU-F1.4-1..9, bi-temporal predicate + helper-pure pattern, commit `467b4f0`).
- Precedente F1.3: `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/tasks.md` (13 tasks T-HU-F1.3-1..13, partial unique index + custom handler + AST walk, commit `ca3f9bf`).
- Precedente F1.8: `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/tasks.md` (13 tasks T-HU-F1.8-1..13, PL/pgSQL migration + custom handler + AST walk pattern, commit `a3d0c39`).
- Precedente F1.2: `openspec/changes/archive/2026-09-14-hu-f1-2-login-jwt/tasks.md` (TenantContext extraction + auth dependency pattern).
- `modelo_datos_er.mmd` § ingreso `[L-E]` (577-596), cantidad_vehiculos_sucursal `[V]` (428-446), tipos_vehiculo `[V]` (87-104), tarifas_sucursal `[V]` (406-426), subscripciones_cliente [V], subscripcion_vehiculos [V], vehiculos [V], alerta `[L-W]` (952-974), salidas `[A]` (761-777), anulaciones `[L-W]`.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` — router custom, `_ingreso_issuer_dep` línea 64, `create_ingreso` líneas 92-114 (thin pass-through F1.5), `cotizar_ingreso_handler` línea 219.
- `backend/packages/parkos_core/src/parkos_core/repo/event.py` — `record_event` base (intact, F1.6 thin wrapper `crear_ingreso_evento`).
- `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` — `get_ocupacion_puros_activos` (F1.5 intact, F1.6 appends `validar_cupo_disponible` + `CupoValidationResult`).
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` — `list_tarifas_vigentes` + `bitemporal_vigente_predicate` (F1.4 intact, F1.6 appends `validar_tarifa_vigente` + `TarifaValidationResult`).
- `backend/packages/parkos_core/src/parkos_core/models/L_W/alerta.py` — `Alerta` model (NO `datos_nuevos` JSONB column pre-0025; migration 0025 adds it).
- `backend/packages/parkos_core/migrations/versions/0013_add_alert_types.py` — `alert_types_inmutable` BEFORE UPDATE/DELETE trigger (líneas 132-147); rol_app is INSERT-only; migration 0025 uses `INSERT ... ON CONFLICT DO NOTHING` to idempotently add `capacidad_agotada_forzado`.
- `backend/packages/parkos_core/migrations/versions/0024_add_mv_ocupacion_diaria.py` — last migration applied (F1.5 chain head); `0025` is the next slot with `down_revision = "0024_mv_ocupacion_diaria"`.
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` — `TenantContext` + `get_tenant_ctx` + errores tipados `TenantScopeViolation` (líneas 60-65) + `SucursalNotPermitted` (115-131).
- `backend/packages/parkos_core/src/parkos_core/api/deps.py` — `get_tenant_ctx` + `requires_issuer` + `_ingreso_issuer_dep`.
- `openspec/specs/operations/spec.md` — agrega REQ-OPS-034..041 (8 requirements nuevos) + entrada en `## Modified Capabilities` (V1, V2, V3, V4, V5, V6, V8, V9, KD-FORZADO-01, KD-FORZADO-01.alerta). Sin cambio sobre REQ-OPS-001..033.
- `plan.md` lines 786-798 — HU-F1.6 budget (260 LOC), DEC-SUC-11 (línea 426, cupo vía MV), DEC-SUC-21 (línea 590, tipo_entrada nunca columna), DEC-SUC-22 (línea 595, regex estricta), KD-FORZADO A-04 addendum #4.
- `plan.md` línea 2677 — RIESGO-SUC-02 (lag MV 10s, riesgo vivo aceptado).
- `modelo_datos_er.mmd` líneas 577-596 — `prod.ingreso` `[L-E]` columnas: uuid, uuid_sucursal, placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente, fecha_ingreso, observaciones, created_at, created_by.
- `openspec/config.yaml` — `review_budget_lines: 400`, `commit_ceiling_loc: 800`, conventional commits enforced.