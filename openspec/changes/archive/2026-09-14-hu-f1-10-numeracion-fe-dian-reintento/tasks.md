# Tasks — HU-F1.10: Numeración FE + estado DIAN + reintento

> **Change**: `hu-f1-10-numeracion-fe-dian-reintento`
> **Phase**: tasks (sdd-tasks)
> **Status**: ready for `sdd-apply` (TDD-strict RED→GREEN→REFACTOR)
> **HU ID**: HU-F1.10 (Fase-1 prerequisites — backend)
> **Inputs**:
> - `openspec/changes/hu-f1-10-numeracion-fe-dian-reintento/design.md` (16 sections + 2 appendices, 2026-09-14)
> - `openspec/changes/hu-f1-10-numeracion-fe-dian-reintento/specs/operations/spec.md` (14 REQs REQ-OPS-064..074 + XR1..XR3)
> - `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-proposal.md` (16 sections, DEC-FE-01..05, KD-FE-01..02)
> - `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/tasks.md` (canonical precedent — 8 clusters T1..T8)
> - `plan.md` lines 939-979 (HU-F1.10 plan, 4 atomic tasks, ~230 LOC budget)
> - `modelo_datos_er.mmd` lines 689-705 (`prod.factura_electronica` [L-E]) + 891-914 (`prod.envio_dian` [L-W])
> - `migrations/versions/0001_initial_schema.py` lines 875-891 + 976-993
> - `migrations/versions/0009_add_derived_read_views.py` lines 96-109 (`v_factura_electronica_acuse`)
> - `migrations/versions/0027_*` (F1.9 head — REVOKE on `prod.factura_electronica` and `prod.envio_dian`)
> - `models/L_E/factura_electronica.py` (LifecycleEventBase) + `L_W/envio_dian.py` (WorkflowBase + self-FK) + `V/resolucion_facturacion.py` (VersionedBase)
> - `repo/resolucion_facturacion.py::assign_consecutivo` (verified, SELECT FOR UPDATE, idempotency)
> - `api/v1/facturacion.py` (F1.9 handler pattern)
> - `schemas/facturacion.py` (F1.9 patterns + 4 new schemas + 8 typed errors)
> - `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/{proposal,design,tasks,verify-report,archive-report}.md`
>
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `47d5630`) · **PR target**: `origin/dev`.
> **TDD discipline**: RED→GREEN→REFACTOR per cluster. Each commit <800 LOC. Each cluster ends with all tests PASS.
> **Atomic commit strategy**: 8 atomic commits expected (1 per cluster T1..T8).
> **Skills loaded**: `gentle-sdd-tasks` (paths injected via orchestrator).

---

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~860 across 1 PR (MIGRATION 0028 ~180 LOC + 3 NEW repo files ~290 LOC + 1 MODIFIED schemas +80 LOC + 1 MODIFIED handler ~60 LOC + 1 NEW repo helper ~40 LOC + 5 NEW test files ~600 LOC + 2 AST walks ~80 LOC) |
| Total tasks | ~30 (8 clusters: T1 schemas 5 tasks + T2 repo 4 tasks + T3 migration 3 tasks + T4 create handler 6 tasks + T5 get handler 3 tasks + T6 retry handler 5 tasks + T7 router 3 tasks + T8 regression 2 tasks) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Medium** — F1.10 is ~0.7x F1.9's LOC pero cohesivo (3 NEW handlers on existing router + 1 NEW repo module); 8-commit split (one per cluster T1..T8) mantiene cada commit bajo el techo `commitlint` de 800 LOC |
| Chained PRs recommended | No — un único PR (matches F1.7 + F1.9 precedent); defensa en profundidad se prueba in-place |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Un único PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 8 commits internos, uno por cluster T1..T8 (T1 ~110 LOC, T2 ~290 LOC, T3 ~250 LOC, T4 ~300 LOC, T5 ~120 LOC, T6 ~280 LOC, T7 ~60 LOC, T8 ~10 LOC). |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesivo single-resource + 8-commit split mantiene budget risk Medium dentro del precedente F1.7 + F1.9 |

| Cluster | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|---------|-------|---------------|----------------|----------------|
| T1 Schemas Pydantic v2 + assign_consecutivo wiring | T1.1..T1.5 | ~80 LOC (schemas + errors + stub) | ~30 LOC (3 RED tests) | 110 |
| T2 Repo layer + 8 typed exceptions | T2.1..T2.4 | ~290 LOC (9 helpers + 8 exceptions) | ~100 LOC (4 RED tests) | 500 |
| T3 MIGRATION 0028 (4 ops + downgrade) | T3.1..T3.3 | ~180 LOC (4 ops + downgrade) | ~70 LOC (3 RED tests) | 750 |
| T4 POST /factura-electronica handler (12-step + KD-FE-01) | T4.1..T4.6 | ~60 LOC (1 handler + KD-FE-01) | ~240 LOC (5 RED + 1 AST walk) | 1,050 |
| T5 GET /factura-electronica/{uuid} handler (3-step) | T5.1..T5.3 | ~30 LOC (1 handler + view JOIN) | ~90 LOC (2 RED tests) | 1,170 |
| T6 POST /reintentar handler (8-step + DEC-FE-07) | T6.1..T6.5 | ~40 LOC (1 handler + chain INSERT) | ~240 LOC (3 RED + 2 AST walks) | 1,450 |
| T7 Router wiring + KD-3 issuer + Cache-Control | T7.1..T7.3 | ~60 LOC (3 routes wired) | ~120 LOC (3 RED tests) | 1,630 |
| T8 Final integration + regression sweep | T8.1..T8.2 | ~10 LOC (verify sweep) | ~150 LOC (regression sweep) | 1,790 |
| **Total** | **~30** | **~750 LOC impl** | **~1,040 LOC tests** | **~1,790 LOC cumulative workload (apply deltas ~860 LOC net)** |

> Tope por commit: <800 LOC. Cada cluster T1..T8 cabe en ≤800 LOC net (T1 ~110, T2 ~290, T3 ~250, T4 ~300, T5 ~120, T6 ~280, T7 ~180, T8 ~160). T3 y T4 pueden requerir split en 2 sub-commits si exceden 800 — orquestador decide según diff real al apply.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| T1 | Pydantic v2 schemas + assign_consecutivo stub wiring | `feat/fase-1-prerequisites-backend` → `origin/dev` (commit 1) | `uv run pytest backend/tests/unit/test_factura_electronica_schemas.py -q` | unit tests sin DB; pure Pydantic validation | Revert schema extensions + delete stub handler |
| T2 | Repo helpers (`factura_electronica.py`) + 8 typed exceptions | commit 2 | `uv run pytest backend/tests/unit/test_factura_electronica_repo.py -q` | unit tests con `pg_engine` mock; pure Python validation paths | Delete new repo file; no DB impact |
| T3 | MIGRATION 0028 (4 ops + downgrade) | commit 3 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0028_idempotent.py -q` | `pg_engine` real (testcontainers precedent F1.4); asserts sobre `pg_indexes`, `sync_catalog` | `alembic downgrade -1` (Op 4 reverse + Op 3 reverse + Op 2 reverse + Op 1 reverse) |
| T4 | POST /factura-electronica handler (12-step + KD-FE-01 + AST walk) | commit 4 | `uv run pytest backend/tests/unit/test_factura_electronica_create_handler.py backend/tests/static/test_fe_handler_single_commit.py -q` | `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-` fixture; real `pg_engine` con `PARKOS_DOCKER_TEST=1`; AST walk no DB | Revert handler addition |
| T5 | GET /factura-electronica/{uuid} handler (3-step + view JOIN) | commit 5 | `uv run pytest backend/tests/unit/test_factura_electronica_get_handler.py -q` | HTTP integration tests with real DB | Revert handler addition |
| T6 | POST /factura-electronica/{uuid}/reintentar handler (8-step + DEC-FE-07 AST walks) | commit 6 | `uv run pytest backend/tests/unit/test_factura_electronica_retry_handler.py backend/tests/static/test_fe_retry_handler_single_commit.py backend/tests/static/test_fe_retry_handler_no_update_on_envio_dian.py -q` | HTTP integration tests + 2 AST walks (single commit + no UPDATE) | Revert handler addition + remove 2 walk files |
| T7 | Router wiring + KD-3 issuer + Cache-Control no-store | commit 7 | `uv run pytest backend/tests/integration/test_factura_electronica_router.py -q` | HTTP integration tests with full app | Revert router additions |
| T8 | Final integration + regression sweep | commit 8 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/ -q` | full suite verde; F1.5/F1.6/F1.7/F1.8/F1.9 sin regresión | n/a (sweep only) |

---

## Tareas

### Cluster T1 — Pydantic schemas + assign_consecutivo wiring (~80 LOC impl + ~30 LOC tests)

- [x] **T-HU-F1.10-T1.1** [RED] — Write failing tests for Pydantic v2 schemas `FacturaElectronicaCreate` + `FacturaElectronicaRead` + `EnvioDianRead` + `EnvioDianRetryRead` with `extra='forbid'`, `Literal` estado, `Annotated` constraints.
  - **Tests** (pure Pydantic validation, sin DB):
    - T1: `test_fe_create_rejects_prefijo_injection` — `FacturaElectronicaCreate.model_validate({"uuid_factura": fake_uuid, "prefijo": "SETP"})` raises `ValidationError` (extra='forbid' rejects DEC-FE-05 client smuggling).
    - T2: `test_fe_create_rejects_consecutivo_injection` — `consecutivo=4521` raises `ValidationError`.
    - T3: `test_fe_create_rejects_uuid_resolucion_injection` — `uuid_resolucion_facturacion=...` raises `ValidationError`.
    - T4: `test_numeracion_agotada_error_schema_typed` — `NumeracionAgotadaError.model_validate({"error": "numeracion_agotada", "uuid_resolucion_facturacion": "<uuid>", "rango_hasta": 5000, "prefijo": "FE"})` succeeds; `Literal["numeracion_agotada"]` enforced.
  - **Patrón F1.9** (`test_facturacion_schemas.py`): pure Pydantic validation tests, sin HTTP, sin DB.
  - **Acción**: importar `FacturaElectronicaCreate`, `FacturaElectronicaRead`, `EnvioDianRead`, `EnvioDianRetryRead`, `NumeracionAgotadaError` from `parkos_core.schemas.facturacion` (falla con `ImportError`); usar `pytest.raises(ValidationError)`. — **Archivo**: `backend/tests/unit/test_factura_electronica_schemas.py` (nuevo, ~80 LOC, 4 tests). — **Validación**: `ImportError: cannot import name 'FacturaElectronicaCreate' from 'parkos_core.schemas.facturacion'`.

- [x] **T-HU-F1.10-T1.2** [GREEN] — Extend `schemas/facturacion.py` (+~80 LOC) with `FacturaElectronicaCreate`, `FacturaElectronicaRead`, `EnvioDianRead`, `EnvioDianRetryRead`, plus 8 typed error schemas.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (modificado, append post-F1.9 block).
  - **Contenido**:
    - `class FacturaElectronicaCreate(_Base)`: `uuid_factura: uuid_lib.UUID` (extra='forbid' inherited from `_Base`).
    - `class EnvioDianRead(_Base)`: `uuid: uuid_lib.UUID`; `uuid_factura_electronica: uuid_lib.UUID`; `estado: Literal["pendiente", "enviado", "aceptado", "rechazado"]`; `timestamp_evento: datetime`; `uuid_envio_padre: uuid_lib.UUID | None`; `cufe: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None`; `motivo_rechazo: Annotated[str, StringConstraints(max_length=500)] | None = None`.
    - `class FacturaElectronicaRead(_Base)`: `uuid: uuid_lib.UUID`; `prefijo: Annotated[str, StringConstraints(min_length=1, max_length=10)]`; `consecutivo: int = Field(ge=0)`; `uuid_factura: uuid_lib.UUID`; `uuid_resolucion_facturacion: uuid_lib.UUID`; `created_at: datetime`; `envio_actual: EnvioDianRead`.
    - `class EnvioDianRetryRead(_Base)`: `uuid: uuid_lib.UUID`; `uuid_factura_electronica: uuid_lib.UUID`; `estado: Literal["pendiente"]`; `timestamp_evento: datetime`; `uuid_envio_padre: uuid_lib.UUID`.
    - 8 typed errors: `NumeracionAgotadaError`, `ReintentoNoPermitidoError`, `EnvioDianAlreadyPendingError`, `FacturaElectronicaYaExisteError`, `ResolucionNoVigenteError`, `FacturaNoEncontradaElectronicaError`, `FacturaElectronicaNoEncontradaError`, `NumeracionDuplicadaError`.
  - **Acción**: append all classes + update `__all__`; imports `from datetime import datetime`, `from typing import Annotated`, `from pydantic import Field`; docstring REQ-OPS-064..074 + DEC-FE-01..07 + KD-FE-01. — **Validación**: T1.1 4 tests PASS.

- [x] **T-HU-F1.10-T1.3** [RED] — Write failing test for `assign_consecutivo` (F1.9 helper, REQ-OPS-064) returning next value + idempotency on `(resolucion_uuid, source_event_uuid)`.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`, mapa design §10.1):
    - T1: `test_assign_consecutivo_for_fe_returns_next_value` — seed `prod.resolucion_facturacion(R, rango_desde=1, rango_hasta=5000)` with prior FE rows having `consecutivo=41`; `await assign_consecutivo(session, resolucion_uuid=R, source_event_uuid=:f)` returns `int(42)`.
    - T2: `test_assign_consecutivo_idempotent_on_same_source` — seed prior FE row with `(uuid_resolucion_facturacion=R, uuid_factura=:f, consecutivo=42)`; `await assign_consecutivo(session, resolucion_uuid=R, source_event_uuid=:f)` returns `int(42)` (idempotency on lines 99-108).
    - T3: `test_assign_consecutivo_range_exhausted_raises` — seed `MAX=5000`; `assign_consecutivo` raises `ConsecutivoRangeExhaustedError`.
  - **Patrón F1.9**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; helper verified pre-apply (lines 99-108 idempotency, 114-120 SELECT FOR UPDATE, 143-147 range exhaustion).
  - **Acción**: importar `assign_consecutivo`, `ConsecutivoRangeExhaustedError` from `parkos_core.repo.resolucion_facturacion`. — **Archivo**: `backend/tests/unit/test_factura_electronica_numeracion.py` (nuevo, ~30 LOC, 1 test for now). — **Validación**: tests rely on F1.9 helper which already exists; they should PASS post T1.5 GREEN (handler wires `assign_consecutivo`).

- [x] **T-HU-F1.10-T1.4** [RED] — Write failing HTTP test for `POST /api/v1/facturacion/factura-electronica` stub returning 501 (stub phase — full impl in T4).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_fe_endpoint_stub_returns_501_or_404` — POST `{"uuid_factura": fake_uuid}` with `operador-X` JWT → 501 (Not Implemented) or 404 (route not registered). Stub returns `NotImplementedError` to verify the handler entry point exists.
  - **Patrón F1.9** (`test_facturacion_factura.py`): HTTP integration test with `httpx.AsyncClient` + JWT fixture.
  - **Acción**: POST to `/api/v1/facturacion/factura-electronica`; expect 501/404. — **Archivo**: extend T1.3 file (`backend/tests/unit/test_factura_electronica_numeracion.py`) with +~20 LOC, 1 test. — **Validación**: 404 (route not registered).

- [x] **T-HU-F1.10-T1.5** [GREEN] — Author stub handler `_create_factura_electronica` (~30 LOC) in `api/v1/facturacion.py` that wires `assign_consecutivo` import + registers the POST route (full 12-step impl in T4).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (modificado, append post-F1.9 handlers).
  - **Contenido**: `_fe_issuer_dep = requires_issuer("operador-", "admin-")`; `@router.post("/factura-electronica", response_model=FacturaElectronicaRead, status_code=201, responses={403:..., 404:..., 409:...})`; `async def create_factura_electronica(response: Response, payload: FacturaElectronicaCreate, session: AsyncSession = Depends(get_session), ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_fe_issuer_dep)) -> FacturaElectronicaRead`; **stub body**: `raise NotImplementedError("HU-F1.10 full impl in T4")`.
  - **Acción**: register route + import `assign_consecutivo`, `ConsecutivoRangeExhaustedError` from `parkos_core.repo.resolucion_facturacion`; docstring REQ-OPS-064 + DEC-FE-01 + KD-FE-01. — **Validación**: T1.4 test passes (501 NotImplementedError); F1.9 endpoints still work (no regression).

  **Commit suggestion**: `feat(backend): HU-F1.10 — schemas + assign_consecutivo wiring + stub handler`.

  **Exit criteria T1**: T1.1..T1.5 verde; ~110 LOC cumulative.

### Cluster T2 — Repo layer + 8 typed exceptions (~290 LOC impl + ~100 LOC tests)

- [x] **T-HU-F1.10-T2.1** [RED] — Write failing tests for `repo/factura_electronica.py::buscar_resolucion_vigente_por_sucursal` (REQ-OPS-073, R2 mitigation), `buscar_factura_electronica_por_factura`, `buscar_envio_dian_chain_tip`, `crear_factura_electronica_inicial`.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`, mapean design §10.1):
    - T1: `test_buscar_resolucion_vigente_por_sucursal_returns_latest` — seed 2 `prod.resolucion_facturacion` rows for `uuid_sucursal=S` with `vigente_hasta IS NULL`, `estado='activo'` (one with `vigente_desde='2026-01-01'`, other with `'2026-09-01'`); helper returns the latest (the one with `'2026-09-01'`).
    - T2: `test_buscar_resolucion_vigente_por_sucursal_returns_none_when_no_vigent` — no vigente rows; returns `None`.
    - T3: `test_buscar_factura_electronica_por_factura_returns_none` — no FE for uuid_factura; returns `None`.
    - T4: `test_buscar_envio_dian_chain_tip_returns_latest` — seed 3 envio rows (e1 rechazado, e2 pendiente, e3 aceptado); `buscar_envio_dian_chain_tip` returns `e3` (latest by `timestamp_evento DESC`).
  - **Patrón F1.9** (`test_repo_factura.py`): `pg_engine` real con `PARKOS_DOCKER_TEST=1`; sembrar via SQL directo al engine.
  - **Acción**: importar `buscar_resolucion_vigente_por_sucursal`, `buscar_factura_electronica_por_factura`, `buscar_envio_dian_chain_tip` from `parkos_core.repo.factura_electronica` (falla con `ImportError`). — **Archivo**: `backend/tests/unit/test_factura_electronica_repo.py` (nuevo, ~100 LOC, 4 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.10-T2.2** [RED] — Write failing tests for `crear_factura_electronica_inicial`, `crear_envio_dian_inicial`, `crear_envio_dian_reintento` (Steps 7 + 8 + /reintentar Step 5).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_crear_factura_electronica_inicial_inserts_row` — seed `prod.facturas(F)`; `crear_factura_electronica_inicial(session, ..., uuid_factura=F, prefijo='FE', consecutivo=42)` returns `FacturaElectronica` with `prefijo='FE'`, `consecutivo=42`.
    - T2: `test_crear_envio_dian_inicial_sets_uuid_envio_padre_null` — `crear_envio_dian_inicial` returns `EnvioDian` with `uuid_envio_padre IS NULL`, `estado='pendiente'`.
    - T3: `test_crear_envio_dian_reintento_sets_uuid_envio_padre_to_tip` — seed FE + initial envio tip; `crear_envio_dian_reintento(..., uuid_envio_padre=tip.uuid)` returns new `EnvioDian` with `uuid_envio_padre=tip.uuid`.
  - **Patrón F1.9**: `pg_engine` real; partial unique index pattern (F1.9 `one_factura_per_salida` analog).
  - **Acción**: imports `crear_factura_electronica_inicial`, `crear_envio_dian_inicial`, `crear_envio_dian_reintento` from `parkos_core.repo.factura_electronica`. — **Archivo**: extend T2.1 file (`backend/tests/unit/test_factura_electronica_repo.py`) with +~40 LOC, 3 tests. — **Validación**: `ImportError`.

- [x] **T-HU-F1.10-T2.3** [GREEN] — Author `repo/factura_electronica.py` (~250 LOC) with 9 helpers + 8 typed exceptions + re-export `ConsecutivoRangeExhaustedError`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura_electronica.py` (nuevo).
  - **Contenido**:
    - 8 typed exceptions: `FacturaNoEncontradaElectronicaError` (V1 404), `FacturaElectronicaNoEncontradaError` (GET + /reintentar V1 404), `FacturaElectronicaYaExisteError` (V2 409 + partial UK race), `ReintentoNoPermitidoError` (V2 409 on aceptado), `EnvioDianAlreadyPendingError` (V2 409 on pendiente), `NumeracionDuplicadaError` (UK01 race), `ResolucionNoVigenteError` (V3 409), `ConsecutivoRangeExhaustedError` (re-exported from `repo.resolucion_facturacion`).
    - 9 helpers: `buscar_factura_por_uuid` (V1, `await session.get(Facturas, uuid_factura)`); `validar_uuid_factura_y_sucursal` (V1 + tenant scope data); `buscar_factura_electronica_por_factura` (V2 SELECT by `uuid_factura`); `buscar_factura_electronica_por_uuid` (GET + /reintentar V1); `crear_factura_electronica_inicial` (Step 7 INSERT [L-E], catches IntegrityError pgcode 23505 → FacturaElectronicaYaExisteError); `crear_envio_dian_inicial` (Step 8 INSERT [L-W] with `uuid_envio_padre=NULL`, `estado='pendiente'`); `crear_envio_dian_reintento` (Step 5 INSERT [L-W] retry with `uuid_envio_padre=tip.uuid`); `buscar_envio_dian_chain_tip` (V2 chain tip via `ORDER BY timestamp_evento.desc(), uuid.desc() LIMIT 1`); `leer_factura_electronica_con_envio_via_view` (GET JOIN to `prod.v_factura_electronica_acuse`).
  - **Acción**: docstring REQ-OPS-064..074 + DEC-FE-01..07 + KD-FE-01; imports `from ..models.L_E.factura_electronica import FacturaElectronica`, `from ..models.L_E.facturas import Facturas`, `from ..models.L_W.envio_dian import EnvioDian`, `from sqlalchemy import select, text`, `from sqlalchemy.exc import IntegrityError`; `__all__` updated. — **Validación**: T2.1 4 tests PASS + T2.2 3 tests PASS.

- [x] **T-HU-F1.10-T2.4** [GREEN] — Add new helper `buscar_resolucion_vigente_por_sucursal` (~25 LOC) to existing `repo/resolucion_facturacion.py` (REQ-OPS-073, R2 mitigation).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py` (modificado, append post-F1.9 `assign_consecutivo`).
  - **Contenido**: `async def buscar_resolucion_vigente_por_sucursal(session, *, uuid_sucursal: uuid_lib.UUID) -> ResolucionFacturacion | None` — `stmt = select(ResolucionFacturacion).where(ResolucionFacturacion.uuid_sucursal == uuid_sucursal, ResolucionFacturacion.vigente_hasta.is_(None), ResolucionFacturacion.estado == "activo").order_by(ResolucionFacturacion.vigente_desde.desc()).limit(1)`; `return (await session.execute(stmt)).scalar_one_or_none()`.
  - **Acción**: append helper after `assign_consecutivo`; docstring REQ-OPS-073 + R2 mitigation; update `__all__`. — **Validación**: T2.1 T1+T2 PASS (single + multi-vigente corrupt cases).

  **Commit suggestion**: `feat(backend): HU-F1.10 — repo/factura_electronica.py + 8 typed exceptions + buscar_resolucion_vigente_por_sucursal`.

  **Exit criteria T2**: T2.1..T2.4 verde; ~500 LOC cumulative (impl + tests).

### Cluster T3 — MIGRATION 0028 (4 ops + downgrade, ~180 LOC impl + ~70 LOC tests)

- [x] **T-HU-F1.10-T3.1** [RED] — Write failing tests for MIGRATION 0028 pre-flight `DO $$` 4-table existence check + DEC-FE-01 sync catalog flip.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0028_preflight_aborta_con_tabla_faltante` — DROP TABLE `prod.envio_dian` (test-only); `alembic upgrade head` raises `0028_preflight_abort: F1.10 requires 4 tables to exist` (pre-flight abort). Re-CREATE TABLE post-test cleanup.
    - T2: `test_sync_catalog_envio_dian_direction_flipped_to_branch_to_cloud` — post-`alembic upgrade head`, query `sync_catalog WHERE table_name='envio_dian'` returns `direction='branch_to_cloud'`.
  - **Patrón F1.9 / F1.7**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; KD-7 pre-flight `DO $$` block pattern reused verbatim.
  - **Acción**: alembic `upgrade head` invoca migration 0028 (falla con pre-flight abort o sync_catalog not flipped). — **Archivo**: `backend/tests/integration/test_migration_0028_idempotent.py` (nuevo, ~40 LOC, 2 tests). — **Validación**: migration 0028 not yet authored.

- [x] **T-HU-F1.10-T3.2** [RED] — Write failing tests for Op 2 partial unique index `one_fe_per_factura` + Op 3 covering index `idx_envio_dian_chain_tip` + Op 4 GRANT re-assertion.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_one_fe_per_factura_partial_uk_blocks_duplicate_fe` — post-migration, insert 2 `prod.factura_electronica` rows with same `uuid_factura=X` (non-NULL); second INSERT raises `IntegrityError` pgcode 23505 with substring `one_fe_per_factura`.
    - T2: `test_idx_envio_dian_chain_tip_covering_index_exists` — post-migration, query `pg_indexes WHERE indexname='idx_envio_dian_chain_tip'` returns 1 row with columns `uuid_factura_electronica, timestamp_evento DESC`.
    - T3: `test_grant_reassertion_post_migration` — post-migration, query `information_schema.role_table_grants WHERE grantee='rol_app' AND table_name IN ('factura_electronica', 'envio_dian', 'resolucion_facturacion')`; assert `privilege_type IN ('SELECT', 'INSERT', 'UPDATE')`.
  - **Patrón F1.9 / F1.7**: `pg_engine` real; partial unique index pattern (`one_exit_per_ingreso` F1.7 migration 0026 Op 4, `one_factura_per_salida` F1.9 migration 0027 Op 2 analog).
  - **Acción**: extend T3.1 file (`backend/tests/integration/test_migration_0028_idempotent.py`) with +~50 LOC, 3 tests. — **Validación**: post-migration, indexes + grants enforced.

- [x] **T-HU-F1.10-T3.3** [GREEN] — Author `migrations/versions/0028_one_fe_per_factura_and_chain_index_and_sync_flip.py` (~180 LOC) with 4 ops + pre-flight + downgrade (REQ-OPS-067 + REQ-OPS-068 + REQ-OPS-072).
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0028_one_fe_per_factura_and_chain_index_and_sync_flip.py` (nuevo).
  - **Contenido**:
    - `revision = "0028_one_fe_per_factura_and_chain_index_and_sync_flip"`; `down_revision = "0027_*"` (F1.9 head).
    - `from alembic import op`.
    - `def upgrade() -> None`:
      - Op 1: pre-flight `DO $$` block asserting 4 tables exist + `UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian' AND direction='cloud_to_branch'` (DEC-FE-01).
      - Op 2: `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL` (REQ-OPS-067, defense in depth).
      - Op 3: `CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_envio_dian_chain_tip ON prod.envio_dian (uuid_factura_electronica, timestamp_evento DESC) WHERE uuid_factura_electronica IS NOT NULL` (REQ-OPS-068 covering index).
      - Op 4: defensive `GRANT SELECT, INSERT, UPDATE ON prod.factura_electronica TO rol_app;` + same for `prod.envio_dian` + `prod.resolucion_facturacion`.
    - `def downgrade() -> None`: reverse order — REVOKE → DROP INDEX CONCURRENTLY (chain_tip) → DROP INDEX CONCURRENTLY (one_fe_per_factura) → `UPDATE sync_catalog SET direction='cloud_to_branch' WHERE table_name='envio_dian' AND direction='branch_to_cloud'` (DEC-FE-01 reverse).
  - **Acción**: paste verbatim from design §3.3 + §6 (MIGRATION 0028 SQL body). — **Validación**: T3.1 2 tests PASS + T3.2 3 tests PASS; downgrade reverses all 4 ops cleanly.

  **Commit suggestion**: `feat(db): HU-F1.10 — MIGRATION 0028 sync_flip + partial_UK + covering_index + GRANT`.

  **Exit criteria T3**: T3.1..T3.3 verde; ~750 LOC cumulative (impl + tests).

### Cluster T4 — POST /factura-electronica handler (12-step + KD-FE-01, ~60 LOC impl + ~240 LOC tests)

- [x] **T-HU-F1.10-T4.1** [RED] — Write failing HTTP test for `POST /api/v1/facturacion/factura-electronica` happy path (V1..V6 all pass, KD-FE-01 single commit).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_create_fe_happy_path_returns_201` — seed `prod.facturas(F)` + `prod.resolucion_facturacion(R, prefijo='FE', rango_desde=1, rango_hasta=5000)`; POST `{"uuid_factura": F}` with `operador-X` JWT → 201 + `FacturaElectronicaRead{prefijo:'FE', consecutivo:<N>, uuid_factura:F, envio_actual: EnvioDianRead{estado:'pendiente', uuid_envio_padre:None, ...}}` + `Cache-Control: no-store` header. Verify exactly 1 `prod.factura_electronica` row + exactly 1 `prod.envio_dian` row in DB.
  - **Patrón F1.9** (`test_facturacion_factura.py`): `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-` fixture; real `pg_engine` con `PARKOS_DOCKER_TEST=1`.
  - **Acción**: importar `FacturaElectronicaCreate`, `FacturaElectronicaRead` from `parkos_core.schemas.facturacion`; use `pytest_asyncio.fixture` + `seed_resolucion`, `seed_factura` fixtures. — **Archivo**: `backend/tests/unit/test_factura_electronica_create_handler.py` (nuevo, ~80 LOC, 1 test). — **Validación**: `NotImplementedError` (stub from T1.5 still present).

- [x] **T-HU-F1.10-T4.2** [GREEN] — Implement `api/v1/facturacion.py::create_factura_electronica` 12-step chain (Step 1 KD-3 issuer, Step 2 V1 factura exists, Step 3 tenant scope post-V1, Step 4 V2 no existing FE, Step 5 V3 vigente resolution, Step 6 KD-FE-01 `assign_consecutivo`, Step 7 INSERT FE row, Step 8 INSERT initial envio row, Step 9 mock DIAN POST, Step 10 single `await session.commit()`, Step 11 response shape, Step 12 `Cache-Control: no-store`).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (modificado, replace T1.5 stub body, +~60 LOC).
  - **Contenido**: replace `NotImplementedError` with full 12-step body per design §9.1 verbatim; imports `from ..repo.factura_electronica import buscar_factura_por_uuid, buscar_factura_electronica_por_factura, crear_factura_electronica_inicial, crear_envio_dian_inicial`; `from ..repo.resolucion_facturacion import buscar_resolucion_vigente_por_sucursal`; `from ..repo.alert_types import AlertaFactory`; docstring REQ-OPS-064..067 + DEC-FE-01..03 + KD-FE-01.
  - **Acción**: paste verbatim from design §9.1 lines 888-1059. — **Validación**: T4.1 1 test PASS; both `prod.factura_electronica` + `prod.envio_dian` rows inserted atomically.

- [x] **T-HU-F1.10-T4.3** [RED] — Write failing HTTP tests for V2 + V3 + V4 error paths.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_create_fe_returns_404_factura_no_encontrada` — POST with non-existent `uuid_factura` → 404 + body `{"error":"factura_no_encontrada","uuid_factura":"..."}` + `Cache-Control: no-store`. No INSERT.
    - T2: `test_create_fe_returns_409_factura_electronica_ya_existe` — seed pre-existing `prod.factura_electronica(F)` for the same `uuid_factura`; POST → 409 + body `{"error":"factura_electronica_ya_existe","uuid_factura":"..."}`. No new INSERT.
    - T3: `test_create_fe_returns_409_resolucion_no_vigente` — seed `prod.facturas(F)` but NO vigente resolution for the sucursal; POST → 409 + body `{"error":"resolucion_no_vigente","uuid_sucursal":"..."}`.
    - T4: `test_create_fe_returns_409_numeracion_agotada_alerta_fired` — seed resolution with `MAX=5000=rango_hasta` (exhausted); POST → 409 + body `{"error":"numeracion_agotada","uuid_resolucion_facturacion":"...","rango_hasta":5000,"prefijo":"FE"}` + verify `prod.alertas` has 1 NEW row with `tipo_alerta='fe_numbering_exhausted'`.
  - **Patrón F1.9**: HTTP integration tests with `httpx.AsyncClient` + JWT fixtures + real DB.
  - **Acción**: extend T4.1 file with +~80 LOC, 4 tests. — **Validación**: pre-implementation, tests fail with 500 (handler does not raise typed exceptions).

- [x] **T-HU-F1.10-T4.4** [GREEN] — Confirm all 4 V2 + V3 + V4 error tests pass (after T4.2 implementation).
  - **Acción**: ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_factura_electronica_create_handler.py -q`. — **Validación**: 5 tests PASS (T4.1 + T4.3 T1..T4).

- [x] **T-HU-F1.10-T4.5** [RED] — Write failing AST walk `tests/static/test_fe_handler_single_commit.py` enforcing exactly 1 `await session.commit()` invocation in `create_factura_electronica` body (KD-FE-01, F1.9 `test_factura_handler_single_commit.py` pattern reused).
  - **Tests**:
    - T1: `test_create_factura_electronica_handler_invokes_session_commit_exactly_once` — `ast.parse` `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py`; locate `create_factura_electronica` via `ast.walk + ast.AsyncFunctionDef.name == 'create_factura_electronica'`; collect commits via `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and getattr(n.value.func, "attr", "") == "commit"])`; assert `commit_count == 1`. Also assert `len([n for n in ast.walk(body) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "begin_nested"]) == 0`; assert NO `SAVEPOINT` / `RELEASE SAVEPOINT` string literals.
  - **Patrón F1.9** (`test_factura_handler_single_commit.py`): `ast.parse` + recursion via `iter_child_nodes`.
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_fe_handler_single_commit.py` (nuevo, ~40 LOC, 1 AST walk). — **Validación**: post T4.2 GREEN, `commit_count == 1` (handler has 1 commit at Step 10).

- [x] **T-HU-F1.10-T4.6** [GREEN] — Confirm AST walk passes (with `create_factura_electronica` having exactly 1 commit).
  - **Acción**: ejecutar `uv run pytest backend/tests/static/test_fe_handler_single_commit.py -q`. — **Validación**: `1 passed`.

  **Commit suggestion**: `feat(backend): HU-F1.10 — POST /factura-electronica (12-step handler + KD-FE-01 single-commit)`.

  **Exit criteria T4**: T4.1..T4.6 verde; ~1,050 LOC cumulative (impl + tests).

### Cluster T5 — GET /factura-electronica/{uuid} handler (3-step, ~30 LOC impl + ~90 LOC tests)

- [x] **T-HU-F1.10-T5.1** [RED] — Write failing HTTP test for `GET /api/v1/facturacion/factura-electronica/{uuid}` happy path (REQ-OPS-068..069).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_get_fe_returns_estado_aceptado_with_cufe` — seed `prod.factura_electronica(FE, uuid_factura=F)` + 1 `prod.envio_dian` row with `uuid_factura_electronica=FE, estado='aceptado', cufe='abc123'`. GET `/factura-electronica/{FE.uuid}` with `operador-X` JWT → 200 + `FacturaElectronicaRead{envio_actual: EnvioDianRead{estado:'aceptado', cufe:'abc123', uuid_envio_padre:None}}` + `Cache-Control: no-store`. JOIN to `prod.v_factura_electronica_acuse` must return the latest row.
  - **Patrón F1.9** (`test_facturacion_factura.py`): HTTP integration test with JWT fixture + real DB.
  - **Acción**: importar `FacturaElectronicaRead` from `parkos_core.schemas.facturacion`; use `pytest_asyncio.fixture` + `seed_factura_electronica_con_envio` fixture. — **Archivo**: `backend/tests/unit/test_factura_electronica_get_handler.py` (nuevo, ~40 LOC, 1 test). — **Validación**: 404 (handler not registered).

- [x] **T-HU-F1.10-T5.2** [GREEN] — Implement `api/v1/facturacion.py::get_factura_electronica` 3-step chain (Step 1 KD-3 issuer, Step 2 V1 FE row exists + tenant scope, Step 3 JOIN `prod.v_factura_electronica_acuse` for `envio_actual`, Step 4 response + `Cache-Control: no-store`).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (modificado, append after `create_factura_electronica`, +~30 LOC).
  - **Contenido**: `@router.get("/factura-electronica/{uuid_factura_electronica}", response_model=FacturaElectronicaRead, responses={403:..., 404:...})`; `async def get_factura_electronica(response: Response, uuid_factura_electronica: uuid_lib.UUID, session: AsyncSession = Depends(get_session), ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_fe_issuer_dep)) -> FacturaElectronicaRead`; body per design §9.2 lines 1077-1149 verbatim.
  - **Acción**: paste verbatim from design §9.2. — **Validación**: T5.1 1 test PASS; JOIN to view returns latest envio with `estado='aceptado'` + `cufe='abc123'`.

- [x] **T-HU-F1.10-T5.3** [RED] — Write failing HTTP test for defensive null mapping (REQ-OPS-068 Scenario 2 — FE row exists but zero envio rows).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_get_fe_returns_estado_pendiente_when_no_envio` — seed `prod.factura_electronica(FE)` with zero `prod.envio_dian` rows; GET → 200 + `FacturaElectronicaRead{envio_actual: EnvioDianRead{estado:'pendiente', uuid_envio_padre:None, cufe:null, ...}}` (defensive null mapping; no 404 / 5xx).
  - **Patrón F1.9**: HTTP integration test.
  - **Acción**: extend T5.1 file with +~40 LOC, 1 test. — **Validación**: pre-implementation, view JOIN returns no row → fallback to `estado='pendiente'`.

  **Commit suggestion**: `feat(backend): HU-F1.10 — GET /factura-electronica/{uuid} (3-step handler + view JOIN)`.

  **Exit criteria T5**: T5.1..T5.3 verde; ~1,170 LOC cumulative (impl + tests).

### Cluster T6 — POST /factura-electronica/{uuid}/reintentar handler (8-step + DEC-FE-07, ~40 LOC impl + ~240 LOC tests)

- [x] **T-HU-F1.10-T6.1** [RED] — Write failing HTTP test for `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` happy path (rechazado chain tip → new pendiente envio).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_retry_fe_happy_path_returns_201_with_new_envio` — seed `prod.factura_electronica(FE)` + 1 `prod.envio_dian` row `:e1` with `estado='rechazado'`. POST `/factura-electronica/{FE.uuid}/reintentar` with `operador-X` JWT → 201 + `EnvioDianRetryRead{uuid=:e2, uuid_factura_electronica=FE.uuid, estado:'pendiente', uuid_envio_padre=:e1.uuid, timestamp_evento:<now>}` + `Cache-Control: no-store`. Verify 2 envio_dian rows total (e1 + e2).
  - **Patrón F1.9**: HTTP integration test with JWT fixture + real DB.
  - **Acción**: importar `EnvioDianRetryRead` from `parkos_core.schemas.facturacion`; use `pytest_asyncio.fixture` + `seed_envio_dian_rechazado` fixture. — **Archivo**: `backend/tests/unit/test_factura_electronica_retry_handler.py` (nuevo, ~60 LOC, 1 test). — **Validación**: 404 (handler not registered).

- [x] **T-HU-F1.10-T6.2** [GREEN] — Implement `api/v1/facturacion.py::retry_factura_electronica` 8-step chain (Step 1 KD-3 issuer, Step 2 V1 FE row exists, Step 3 tenant scope post-V1, Step 4 V2 chain tip state check [aceptado→409, pendiente→409, rechazado/enviado→proceed], Step 5 V3 INSERT new envio row with `uuid_envio_padre=tip.uuid`, Step 6 mock DIAN POST, Step 7 single `await session.commit()`, Step 8 response + `Cache-Control: no-store`).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (modificado, append after `get_factura_electronica`, +~40 LOC).
  - **Contenido**: `@router.post("/factura-electronica/{uuid_factura_electronica}/reintentar", response_model=EnvioDianRetryRead, status_code=201, responses={403:..., 404:..., 409:...})`; `async def retry_factura_electronica(response: Response, uuid_factura_electronica: uuid_lib.UUID, session: AsyncSession = Depends(get_session), ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_fe_issuer_dep)) -> EnvioDianRetryRead`; body per design §9.3 lines 1169-1275 verbatim.
  - **Acción**: paste verbatim from design §9.3. — **Validación**: T6.1 1 test PASS; chain grows by 1 row, original `:e1` unchanged.

- [x] **T-HU-F1.10-T6.3** [RED] — Write failing HTTP tests for 409 discriminators (DEC-FE-04): `aceptado` → 409 `reintento_no_permitido`; `pendiente` → 409 `envio_dian_already_pending`.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_retry_fe_returns_409_si_chain_tip_aceptado` — seed FE + envio with `estado='aceptado'`; POST /reintentar → 409 + body `{"error":"reintento_no_permitido","uuid_factura_electronica":"...","estado_actual":"aceptado"}` + `Cache-Control: no-store`. No new INSERT.
    - T2: `test_retry_fe_returns_409_si_chain_tip_pendiente` — seed FE + envio with `estado='pendiente'` (initial envio from POST /factura-electronica); POST /reintentar → 409 + body `{"error":"envio_dian_already_pending","uuid_factura_electronica":"...","uuid_envio_pendiente":"..."}`.
    - T3: `test_retry_fe_returns_404_si_fe_no_existe` — POST /reintentar with non-existent `uuid_factura_electronica` → 404 + body `{"error":"factura_electronica_no_encontrada","uuid_factura_electronica":"..."}`.
  - **Patrón F1.9**: HTTP integration tests.
  - **Acción**: extend T6.1 file with +~60 LOC, 3 tests. — **Validación**: pre-implementation, tests fail with 500 (handler does not raise typed exceptions).

- [x] **T-HU-F1.10-T6.4** [RED] — Write failing AST walk `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` enforcing NO UPDATE on `prod.envio_dian` user-meaningful fields in `retry_factura_electronica` body (DEC-FE-07 NEW, REQ-OPS-070).
  - **Tests**:
    - T1: `test_retry_handler_no_update_on_envio_dian_user_meaningful_fields` — `ast.parse` `api/v1/facturacion.py`; locate `retry_factura_electronica`; walk statements via `iter_child_nodes`; assert no `UPDATE prod.envio_dian` string literal; assert no `update(EnvioDian)` SQLAlchemy core call; assert exactly one `INSERT INTO prod.envio_dian` (via `crear_envio_dian_reintento` helper call).
  - **Patrón F1.9** (`test_factura_handler_single_commit.py`): `ast.parse` + `iter_child_nodes` DFS.
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` (nuevo, ~40 LOC, 1 AST walk). — **Validación**: post T6.2 GREEN, walk passes (only INSERT via `crear_envio_dian_reintento`, no UPDATE).

- [x] **T-HU-F1.10-T6.5** [GREEN] — Confirm all 3 retry handler tests + AST walk pass; add `tests/static/test_fe_retry_handler_single_commit.py` AST walk enforcing 1 `await session.commit()` in `retry_factura_electronica` (KD-FE-01 mirror).
  - **Acciones**:
    1. Ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_factura_electronica_retry_handler.py backend/tests/static/test_fe_retry_handler_no_update_on_envio_dian.py -q` → 4 tests PASS.
    2. Crear `backend/tests/static/test_fe_retry_handler_single_commit.py` (~40 LOC) mirroring T4.5 pattern but for `retry_factura_electronica`. Assert `commit_count == 1`; assert no `begin_nested`; assert no `SAVEPOINT` / `RELEASE SAVEPOINT`.
  - **Validación**: 4 tests PASS + new AST walk passes (1 commit in retry handler body at Step 7).

  **Commit suggestion**: `feat(backend): HU-F1.10 — POST /factura-electronica/{uuid}/reintentar (8-step handler + DEC-FE-07 AST walks)`.

  **Exit criteria T6**: T6.1..T6.5 verde; ~1,450 LOC cumulative (impl + tests).

### Cluster T7 — Router wiring + KD-3 issuer + Cache-Control no-store (~60 LOC impl + ~120 LOC tests)

- [x] **T-HU-F1.10-T7.1** [RED] — Write failing HTTP test asserting `requires_issuer("operador-", "admin-")` issuer dep is applied at handler entry (Layer 1 of defense in depth).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_fe_endpoint_rejects_non_operador_admin_issuer_with_403` — POST `/factura-electronica` with JWT `cajero-X` (NOT `operador-` nor `admin-`) → 403 + body `{"error":"issuer_forbidden", ...}` (issuer dep runs BEFORE handler body). No SELECT.
  - **Patrón F1.9** (`test_facturacion_factura.py`): HTTP integration test with parametrized JWT fixture.
  - **Acción**: POST with `cajero-X` JWT; expect 403 from issuer dep. — **Archivo**: `backend/tests/integration/test_factura_electronica_router.py` (nuevo, ~50 LOC, 1 test). — **Validación**: handler accepts any JWT (issuer dep not enforced).

- [x] **T-HU-F1.10-T7.2** [RED] — Write failing HTTP tests asserting `Cache-Control: no-store` header on all responses (2xx, 4xx, 5xx — DEC-FE-06 NEW, REQ-OPS-XR2).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_fe_endpoint_201_response_carries_cache_control_no_store` — happy path POST → 201 with `Cache-Control: no-store` header.
    - T2: `test_fe_endpoint_404_response_carries_cache_control_no_store` — POST with non-existent `uuid_factura` → 404 with `Cache-Control: no-store` header.
    - T3: `test_fe_endpoint_409_response_carries_cache_control_no_store` — POST with existing FE row → 409 with `Cache-Control: no-store` header.
  - **Patrón F1.9**: HTTP integration test asserting header presence.
  - **Acción**: extend T7.1 file with +~50 LOC, 3 tests. — **Validación**: pre-implementation, `Cache-Control: no-store` absent.

- [x] **T-HU-F1.10-T7.3** [GREEN] — Wire all 3 routes (`POST /factura-electronica`, `GET /factura-electronica/{uuid}`, `POST /factura-electronica/{uuid}/reintentar`) + verify KD-3 issuer dep + `Cache-Control: no-store` on all responses.
  - **Acciones**:
    1. Verify `_fe_issuer_dep = requires_issuer("operador-", "admin-")` already defined in `api/v1/facturacion.py` (T1.5) and applied to all 3 handlers (T4.2, T5.2, T6.2).
    2. Verify `no_store = no_store_headers()` at top of each handler + `apply_no_store_header(response)` before return + `headers=no_store` in all `HTTPException` constructors.
    3. Confirm router registration on FastAPI app (already in F1.9).
  - **Validación**: T7.1 1 test PASS + T7.2 3 tests PASS; no regression F1.5..F1.9.

  **Commit suggestion**: `feat(backend): HU-F1.10 — router wiring verification + KD-3 issuer + Cache-Control no-store`.

  **Exit criteria T7**: T7.1..T7.3 verde; ~1,630 LOC cumulative (impl + tests).

### Cluster T8 — Final integration + regression sweep (~10 LOC impl + ~150 LOC tests)

- [x] **T-HU-F1.10-T8.1** [RED] — Write failing full-suite integration test verifying all 3 endpoints + MIGRATION 0028 end-to-end (POST → GET → /reintentar on rechazo → GET).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_fe_full_chain_post_get_retry_get_returns_expected_estados` — seed `prod.facturas(F)` + `prod.resolucion_facturacion(R)`; POST /factura-electronica → 201 with `estado='pendiente'`; GET → 200 with `estado='pendiente'`, `cufe=null`; mock cloud dispatcher advancing envio to `estado='rechazado'` (manual UPDATE on DB for test); POST /reintentar → 201 with NEW envio row + `uuid_envio_padre=tip.uuid`; GET → 200 with `estado='pendiente'` (new envio tip). Verify chain integrity: exactly 2 envio_dian rows.
  - **Patrón F1.9** (`test_factura_handler_integration.py`): full HTTP integration test with multi-step scenario.
  - **Acción**: extend T4.1 or T6.1 file with +~50 LOC, 1 test. — **Validación**: pre-implementation, multi-step scenario fails at first step.

- [x] **T-HU-F1.10-T8.2** [GREEN] — Run full regression sweep verifying F1.5/F1.6/F1.7/F1.8/F1.9 tests still pass after F1.10 changes (no_regresion gate).
  - **Acciones**:
    1. Ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/ -q` (full suite, skip Docker-gated SKIPs where env not set).
    2. Verify F1.9 tests still pass: `test_facturacion_factura.py`, `test_facturacion_factura_pagos.py`, `test_migration_0027_idempotent.py`, AST walks KD-FACT-01.
    3. Verify F1.7 tests still pass: `test_salidas_*`, KD-FORZADO-01 AST walks.
    4. Verify F1.8 tests still pass: PL/pgSQL `calcular_cotizacion` + KD-1 FOR SHARE.
    5. Verify F1.6 tests still pass: KD-FORZADO-01 prefix contract.
    6. Verify F1.5 tests still pass: MV pattern + `repo/workflow.read_chain_tip`.
  - **Validación**: full suite verde; 0 regresiones introducidas por F1.10; las fallas preexistentes documentadas en baseline F1.9 se mantienen sin nuevos archivos fallando.

  **Commit suggestion**: `test(backend): HU-F1.10 — final integration + regression sweep (all prior tests still pass)`.

  **Exit criteria T8**: T8.1..T8.2 verde; ~1,790 LOC cumulative (impl + tests).

---

## Cross-cluster constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` en `create_factura_electronica` handler outside the 4 expected INSERTs (Steps 7 + 8, with retry Step 5 only on `/reintentar` handler) — AST walk `tests/static/test_fe_handler_single_commit.py` (T4.5) enforces via KD-FE-01 single-commit invariant.
- NO `UPDATE prod.envio_dian` on user-meaningful fields (`estado`, `cufe`, `uuid_envio_padre`, `motivo_rechazo`) en `retry_factura_electronica` handler — AST walk `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` (T6.4) enforces via DEC-FE-07 NEW (REQ-OPS-070 Scenario 4).
- NO hardcoded fallback numbering (`SIM-YYYY-MM-DD-NNNNNN`) — plan.md línea 951 explicitly forbids; only `assign_consecutivo` is used (REQ-OPS-064, DEC-FE-05).
- NO `Co-authored-by:` ni trailers AI en commits; conventional commits, neutral Spanish.
- NO SQLite en tests — `pg_engine` real o `testcontainers[postgres]` (precedente F1.4/F1.5/F1.6/F1.7/F1.9).
- NO modificación de `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate (matches F1.7 + F1.9).
- NO modificación de `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate cross-cutting.
- NO modificación de `api/deps.py` ni `auth/tenancy.py` — KD-3 chain + errores tipados intactos.
- NO modificación de `repo/event.py` — `event_helper_intact` CI gate (matches F1.7 + F1.9).
- NO modificación de `repo/resolucion_facturacion.py::assign_consecutivo` — reused verbatim per DEC-FE-05 (NO modification; F1.9 helper).
- NO modificación de `repo/workflow.py::read_chain_tip` — reused verbatim (F1.5 PR5-016).
- NO modificación de `repo/alert_types.py::AlertaFactory` — reused verbatim (F1.8 T-PR8-002).
- NO `correlacion_id` en el body (DEC-IDEM-01) — header `Idempotency-Key` via PR2 middleware.
- NO `prefijo` + `consecutivo` en `prod.facturas` — DEC-FACT-05 (F1.9); FE numbering lives on `prod.factura_electronica`.
- NO `cufe` column en `prod.factura_electronica` — 4NF; lives on `prod.envio_dian` only (REQ-OPS-069, plan.md línea 947).
- NO `reportado_dian` boolean anywhere — plan.md línea 947 explicitly FORBIDDEN.
- NO `prod.forma_pago` catálogo (DEC-FACT-07 Opción A) — Pydantic `Literal[...]` enforced.
- NO `xml_firmado` column on `prod.factura_electronica` — Fase 4 deferred.
- Header `Cache-Control: no-store` en TODA respuesta 2xx/4xx/5xx del endpoint (via `no_store_headers()` helper + `apply_no_store_header(response)` + `headers=no_store` param in `HTTPException` constructors) — DEC-FE-06 NEW.
- Discriminadores de error estables: `tenant_scope_violation` (403 operador cross-branch), `factura_no_encontrada` (404 V1), `factura_electronica_no_encontrada` (404 GET + /reintentar), `factura_electronica_ya_existe` (409 V2 + partial UK race), `resolucion_no_vigente` (409 V3), `numeracion_agotada` (409 V4 + alerta fired), `numeracion_duplicada` (409 UK01 race), `reintento_no_permitido` (409 chain tip aceptado), `envio_dian_already_pending` (409 chain tip pendiente), `alerta_no_creada` (500 defense in depth).
- Precedencia de errores: KD-3 (403 issuer) > V1 (404 factura) > tenant scope (403) > V2 (409 ya_existe) > V3 (409 no_vigente) > V4 (409 agotada) > Step 7 INSERT (409 dup) > Step 10 commit > Step 12 response 201.
- Migration `0028` debe usar `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` (idempotente; `CONCURRENTLY` no lock reads/writes en producción).
- `prod.factura_electronica` is `[L-E]` (NOT partitioned) — partial unique index `one_fe_per_factura (uuid_factura) WHERE uuid_factura IS NOT NULL` IS feasible (verified design §5.2).
- `prod.envio_dian` is `[L-W]` insert-only per transition (WorkflowBase) — UPDATE forbidden on user-meaningful fields.
- **CRITICAL** Single `await session.commit()` (KD-FE-01) en `create_factura_electronica` (Step 10) — `prod.factura_electronica` + `prod.envio_dian` atomically materialized.
- **CRITICAL** Single `await session.commit()` (KD-FE-01) en `retry_factura_electronica` (Step 7) — NEW envio row atomic.
- **CRITICAL** `assign_consecutivo` SELECT FOR UPDATE lock held until `await session.commit()` (KD-FE-02). Concurrent calls on SAME resolution serialize cleanly.
- **CRITICAL** Step 6 (`assign_consecutivo`) MUST execute BEFORE Step 7 (INSERT FE) so `consecutivo` is available at INSERT time.
- **CRITICAL** `prefijo` snapshotted from vigente `resolucion.prefijo` (REQ-OPS-074) — subsequent resolution changes do NOT retroactively alter FE.prefijo (4NF snapshot pattern).
- Tope por commit: <800 LOC. Cada cluster T1..T8 cabe en ≤800 LOC net (T1 ~110, T2 ~290, T3 ~250, T4 ~300, T5 ~120, T6 ~280, T7 ~180, T8 ~160). T3 y T4 pueden requerir split en 2 sub-commits si exceden 800 — orquestador decide según diff real al apply.
- Mensajes conventional commit; cuerpo técnico en neutral Spanish.

## Acceptance Gates

- TDD strict: RED primero, GREEN mínimo, REFACTOR último. Cluster T1 explicitly notes this discipline.
- ~30 tasks completados en orden: T1.1..T1.5 → T2.1..T2.4 → T3.1..T3.3 → T4.1..T4.6 → T5.1..T5.3 → T6.1..T6.5 → T7.1..T7.3 → T8.1..T8.2.
- Conventional commits atómicos (8 commits en 1 PR):
  - commit 1 `feat(backend): HU-F1.10 — schemas + assign_consecutivo wiring + stub handler` (~110 LOC);
  - commit 2 `feat(backend): HU-F1.10 — repo/factura_electronica.py + 8 typed exceptions + buscar_resolucion_vigente_por_sucursal` (~290 LOC);
  - commit 3 `feat(db): HU-F1.10 — MIGRATION 0028 sync_flip + partial_UK + covering_index + GRANT` (~250 LOC);
  - commit 4 `feat(backend): HU-F1.10 — POST /factura-electronica (12-step handler + KD-FE-01 single-commit)` (~300 LOC);
  - commit 5 `feat(backend): HU-F1.10 — GET /factura-electronica/{uuid} (3-step handler + view JOIN)` (~120 LOC);
  - commit 6 `feat(backend): HU-F1.10 — POST /factura-electronica/{uuid}/reintentar (8-step handler + DEC-FE-07 AST walks)` (~280 LOC);
  - commit 7 `feat(backend): HU-F1.10 — router wiring verification + KD-3 issuer + Cache-Control no-store` (~180 LOC);
  - commit 8 `test(backend): HU-F1.10 — final integration + regression sweep (all prior tests still pass)` (~160 LOC).
  - Sin `Co-authored-by:`, sin trailers IA.
- Tests pasan contra DB real con `PARKOS_DOCKER_TEST=1`: 4 Pydantic schemas (T1.1) + 1 assign_consecutivo wiring (T1.3) + 4 repo unit (T2.1) + 3 repo unit (T2.2) + 5 migration idempotency (T3.1 + T3.2) + 1 HTTP happy path (T4.1) + 4 V2+V3+V4 error paths (T4.3) + 1 AST walk KD-FE-01 (T4.5) + 1 HTTP GET happy (T5.1) + 1 HTTP GET null mapping (T5.3) + 1 HTTP retry happy (T6.1) + 3 HTTP retry 409/404 (T6.3) + 1 AST walk DEC-FE-07 no UPDATE (T6.4) + 1 AST walk KD-FE-01 retry (T6.5) + 1 router issuer 403 (T7.1) + 3 Cache-Control no-store (T7.2) + 1 full-chain integration (T8.1) = **~36 tests nuevos en 11 archivos**.
- ruff + mypy --strict clean sobre los 9 archivos nuevos/modificados (2 NEW `repo/*.py` + 1 NEW migration + 1 NEW handler appends + 1 MODIFIED schemas + 1 MODIFIED `repo/resolucion_facturacion.py` + 1 MODIFIED `api/v1/facturacion.py` + 8 NEW tests + 3 NEW AST walks).
- 5 CI gates verdes (matches F1.7 + F1.9): `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.9`.
- 0 regresiones introducidas por F1.10; las fallas preexistentes documentadas en baseline F1.9 se mantienen sin nuevos archivos fallando.
- REQ-OPS-064..074 + REQ-OPS-XR1..XR3 traceability verificada: cada REQ tiene ≥1 RED test que la prueba (T1.1 + T1.3 + T2.1..T2.3 + T3.1 + T3.2 + T4.1 + T4.3 + T5.1 + T5.3 + T6.1 + T6.3 + T7.1 + T7.2 + T8.1 mapping).
- Architecture risks §7 (R1..R10) verificadas: R1 envio_dian ownership RESOLVED via DEC-FE-01 (T3.1 + T3.2 sync_catalog flip + MIGRATION 0028 Op 1); R2 vigente resolution lookup → T2.4 helper with defensive ORDER BY vigente_desde DESC LIMIT 1 (T2.1 T1+T2 PASS); R3 chain integrity via uuid_envio_padre FK → T2.2 T3 + T6.1 + T6.3 verify; R4 DIAN web service → Fase 4 deferred (mock in MVP); R5 prefijo snapshot → T2.3 + T4.2 (REQ-OPS-074); R6 prefijo TOCTOU → T4.2 Step 5 reads prefijo BEFORE Step 6 `assign_consecutivo`; R7 cloud dispatcher eventual consistency → documented (DEC-FE-02 retry chain grows locally); R8 partial UK uuid_factura NOT NULL → T2.3 handler always passes `uuid_factura` (extra='forbid'); R9 MIGRATION 0028 sync flip idempotency → T3.1 WHERE clause `direction='cloud_to_branch'` filters UPDATE; R10 downgrade reverse order → T3.3 `def downgrade()` reverses in correct order.

## Out of Scope Tasks

- Real DIAN web service integration — Fase 4 (contabilidad); cloud dispatcher handles the actual provider call asynchronously via sync.
- Automatic retry policy (exponential backoff) — cloud dispatcher concern; branch endpoint only INSERTs the retry row.
- CUFE signing — Fase 4. `cufe` is NULL on initial envio; populated by cloud dispatcher when DIAN returns signed CUFE.
- `prod.factura_electronica.xml_firmado` column — Fase 4. Not in F1.10 scope.
- Multi-resolution concurrent numbering — out of scope for F1.10; MVP supports a single vigente resolution per prefijo per sucursal.
- Anulación of FE — F1.13 owns via `prod.anulaciones(tipo_anulable='factura_electronica')` workflow.
- Cloud-side state-machine advancement (`pendiente → enviado → aceptado | rechazado`) — out of F1.10 scope; cloud dispatcher writes transition rows via flipped `branch_to_cloud` sync channel.
- `GET /api/v1/facturacion/factura-electronica?uuid_factura=...` (paginated list) — proposed adjacent endpoint, lower priority, out of F1.10 scope.
- `cufe` column on `prod.factura_electronica` — explicitly FORBIDDEN per 4NF (ER línea 700); lives on `prod.envio_dian` only.
- `reportado_dian` boolean — explicitly FORBIDDEN per plan.md línea 947.
- `prod.factura_electronica.estado` column — explicitly FORBIDDEN per 4NF; state lives on `prod.envio_dian.estado` only.
- ER diagram comment update (`CLOUD-ONLY` → `BRANCH-INITIATED`) — separate post-archive PR for traceability (matches F1.9 docstring drift pattern).

## Commit summary (8 expected atomic commits)

| # | Cluster | Commit message | Files | LOC est. |
|---|---|---|---|---|
| 1 | T1 | `feat(backend): HU-F1.10 — schemas + assign_consecutivo wiring + stub handler` | 1 NEW test + 1 MODIFIED schemas + 1 MODIFIED handler (stub) | ~110 |
| 2 | T2 | `feat(backend): HU-F1.10 — repo/factura_electronica.py + 8 typed exceptions + buscar_resolucion_vigente_por_sucursal` | 1 NEW repo + 1 MODIFIED repo + 1 NEW test | ~290 |
| 3 | T3 | `feat(db): HU-F1.10 — MIGRATION 0028 sync_flip + partial_UK + covering_index + GRANT` | 1 NEW migration + 1 NEW integration test | ~250 |
| 4 | T4 | `feat(backend): HU-F1.10 — POST /factura-electronica (12-step handler + KD-FE-01 single-commit)` | 1 MODIFIED handler (replace stub) + 1 NEW unit test + 1 NEW AST walk | ~300 |
| 5 | T5 | `feat(backend): HU-F1.10 — GET /factura-electronica/{uuid} (3-step handler + view JOIN)` | 1 MODIFIED handler + 1 NEW unit test | ~120 |
| 6 | T6 | `feat(backend): HU-F1.10 — POST /factura-electronica/{uuid}/reintentar (8-step handler + DEC-FE-07 AST walks)` | 1 MODIFIED handler + 1 NEW unit test + 2 NEW AST walks | ~280 |
| 7 | T7 | `feat(backend): HU-F1.10 — router wiring verification + KD-3 issuer + Cache-Control no-store` | 1 NEW integration test (verifies wiring) | ~180 |
| 8 | T8 | `test(backend): HU-F1.10 — final integration + regression sweep (all prior tests still pass)` | 1 NEW full-chain test + verify regression | ~160 |

**Total**: 8 commits, ~1,790 LOC cumulative (impl + tests), 1 PR to `origin/dev`.

## Definition of Done (apply phase)

- [ ] 14 tests + 2 AST walks (KD-FE-01 create + KD-FE-01 retry + DEC-FE-07 no UPDATE) PASS via `uv run pytest backend/tests/unit/test_factura_electronica_*.py backend/tests/static/test_fe_*.py -q`
- [ ] 3 integration tests (router + no-store + full chain) PASS via `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_factura_electronica_*.py backend/tests/integration/test_migration_0028_*.py -q`
- [ ] MIGRATION 0028 applied + downgrade reverses cleanly via `alembic upgrade head` + `alembic downgrade -1`
- [ ] 3 handlers (`create_factura_electronica`, `get_factura_electronica`, `retry_factura_electronica`) implemented per design §9.1, §9.2, §9.3
- [ ] `repo/factura_electronica.py` 9 helpers + 8 typed exceptions authored (DEC-FE-01..07)
- [ ] `repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal` added (REQ-OPS-073, R2 mitigation)
- [ ] 3 endpoints wired in router with `requires_issuer("operador-", "admin-")` + `Cache-Control: no-store` (DEC-FE-06)
- [ ] KD-FE-01 single-commit invariant verified via AST walks on both create + retry handlers
- [ ] DEC-FE-07 no UPDATE on `prod.envio_dian` user-meaningful fields verified via AST walk on retry handler
- [ ] `assign_consecutivo` reused as-is, NOT modified (DEC-FE-05)
- [ ] `repo/workflow.read_chain_tip` + `repo/alert_types.AlertaFactory` reused as-is, NOT modified
- [ ] DEC-FE-01 sync catalog flip applied via MIGRATION 0028 Op 1 (`direction='branch_to_cloud'`)
- [ ] REQ-OPS-064..074 + REQ-OPS-XR1..XR3 traceability verified via per-REQ tests
- [ ] All F1.5/F1.6/F1.7/F1.8/F1.9 tests still PASS (no_regresion gate)
- [ ] ruff + mypy --strict clean on all 9 new/modified files
- [ ] 5 CI gates verde (`factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.9`)
- [ ] 0 regresiones introducidas; baseline F1.9 fallas preexistentes documented + unchanged
- [ ] 8 atomic commits authored with conventional commit messages, neutral Spanish, NO `Co-authored-by:` trailers

## Next phase

`sdd-apply HU-F1.10` — TDD-strict RED→GREEN→REFACTOR per cluster T1..T8. Orchestrator executes the 8 atomic commits in order, verifies each cluster's exit criteria, and routes to `sdd-verify` after all commits land.

## References

- `openspec/changes/hu-f1-10-numeracion-fe-dian-reintento/design.md` (16 sections + 2 appendices, 2026-09-14) — architecture + MIGRATION 0028 + handler skeletons + 14 tests + 2 AST walks.
- `openspec/changes/hu-f1-10-numeracion-fe-dian-reintento/specs/operations/spec.md` (~440 LOC, 14 REQs REQ-OPS-064..074 + XR1..XR3) — operational requirements.
- `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-proposal.md` (16 sections, DEC-FE-01..05 + DEC-FE-06..07 NEW, KD-FE-01..02) — pre-design proposal.
- `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-explore.md` (16 sections, ~970 LOC, observation #1568) — pre-apply verification findings (R1..R5).
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/tasks.md` (621 LOC, 8 clusters T1..T8, ~30 tasks) — **canonical precedent** for F1.10 structure.
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/{exploration,proposal,design,tasks,verify-report,archive-report}.md` — F1.9 full cycle precedent.
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/tasks.md` — F1.7 precedent (KD-S2 tenant scope, `one_exit_per_ingreso` partial UK).
- `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/tasks.md` — F1.5 precedent (`repo/workflow.read_chain_tip`).
- `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/tasks.md` — F1.8 precedent (`repo/alert_types.py::AlertaFactory`).
- `openspec/specs/operations/spec.md` — 66 REQs REQ-OPS-001..063 merged post-F1.9; target for REQ-OPS-064..074 merge on archive.
- `plan.md` lines 939-979 — HU-F1.10 definition, 4 atomic tasks T1..T4, ~230 LOC budget.
- `plan.md` línea 951 (forbidden fallback `SIM-YYYY-MM-DD-NNNNNN` numbering).
- `plan.md` línea 949 (alerta `fe_numbering_exhausted` already seeded).
- `plan.md` línea 953 (`envio_dian` INSERT por transición, nunca UPDATE, BRANCH-initiated).
- `plan.md` línea 969 (retry only on `rechazado`; block on `aceptado`).
- `plan.md` línea 697 (`prefijo` snapshot pattern, 4NF).
- `plan.md` línea 947 (forbidden `reportado_dian` boolean).
- `modelo_datos_er.mmd` lines 689-705 (`prod.factura_electronica` [L-E] snapshot pattern, "cufe y reportado_dian eliminados (4FN)").
- `modelo_datos_er.mmd` lines 891-914 (`prod.envio_dian` [L-W] self-FK chain — post-archive comment update from "CLOUD-ONLY" to "BRANCH-INITIATED").
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 875-891 (`factura_electronica` create_table + UK01) + 976-993 (`envio_dian` create_table + UK02) + 1595-1842 (FKs) + 2646-2712 (audit/versioning triggers) + 2864-2900 (sync enqueue triggers).
- `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109 (`prod.v_factura_electronica_acuse` view, DISTINCT ON latest envio).
- `backend/packages/parkos_core/migrations/versions/0027_*` (F1.9 head — REVOKE on `prod.factura_electronica`).
- `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py` (LifecycleEventBase).
- `backend/packages/parkos_core/src/parkos_core/models/L_W/envio_dian.py` (WorkflowBase + self-FK `uuid_envio_padre`).
- `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` (VersionedBase, bi-temporal).
- `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo` (verified, lines 99-108 idempotency, lines 114-120 SELECT FOR UPDATE, lines 143-147 `ConsecutivoRangeExhaustedError`).
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py::read_chain_tip` (F1.5 PR5-016, reused for `/reintentar` chain tip lookup).
- `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py::AlertaFactory` (F1.8 T-PR8-002, fires `fe_numbering_exhausted` on range exhaustion).
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136 (`envio_dian` `cloud_to_branch` direction per D1-rev — **FLIPPED in DEC-FE-01** / MIGRATION 0028 Op 1).
- `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (F1.9 handler pattern verbatim, extended with 3 new handlers).
- `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (F1.9 patterns + new `FacturaElectronicaCreate`, `FacturaElectronicaRead`, `EnvioDianRead`, `EnvioDianRetryRead` + 8 typed error schemas).
- `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` (`no_store_headers` + `apply_no_store_header` F1.6 R-A6 helpers).
- DIAN Resolución 000175 de 2021, Decreto 2242 de 2015 — Colombian electronic invoicing framework.
- PostgreSQL 15 documentation, Chapter 5.4 (Constraints) — partial unique index pattern.
- PostgreSQL 15 documentation, Chapter 38 (Triggers) — BEFORE INSERT trigger pattern.
- SQLAlchemy 2.0 documentation — `with_for_update(read=True)` for `FOR SHARE` semantics; async session patterns.
- Pydantic v2 documentation — `@field_validator` + `extra='forbid'` + `Literal` + `Annotated` patterns.
