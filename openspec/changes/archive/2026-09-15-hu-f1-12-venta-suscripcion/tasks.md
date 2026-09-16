# Tasks: HU-F1.12 — Venta atómica de suscripción (cliente + vehículos + suscripción + cobro opcional + FE opcional en 1 TX)

> **Change**: `hu-f1-12-venta-suscripcion`
> **Phase**: tasks (sdd-tasks)
> **Status**: ready for `sdd-apply` (TDD-strict RED→GREEN→REFACTOR)
> **HU ID**: HU-F1.12 (Fase-1 prerequisites — backend)
> **Inputs**:
> - `openspec/changes/hu-f1-12-venta-suscripcion/design.md` (16 sections + 2 appendices, 2026-09-15, ~1562 LOC, 8 DECs + 2 KDs + MIGRATION 0030 NO-OP SQL + ~43 tests + 2 AST walks)
> - `openspec/changes/hu-f1-12-venta-suscripcion/specs/operations/spec.md` (~485 LOC, 8 REQ-OPS-083..090 + REQ-OPS-XR5)
> - `openspec/changes/hu-f1-12-venta-suscripcion/proposal.md` (~485 LOC, 16 sections, DEC-VENTA-01..07 + DEC-VENTA-08 WITHDRAWN, KD-VENTA-01..02)
> - `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/tasks.md` (canonical precedent — 8 clusters T1..T8, 31 atomic tasks, ~860 LOC)
> - `plan.md` lines 1010-1054 (HU-F1.12 plan, 3 atomic tasks, 260 LOC production budget, 4 tests mandated at line 1047) + line 460 (A-09 prorrateo — no `monto_prorrateado` column on `subscripciones_cliente`)
> - `modelo_datos_er.mmd` lines 105 (`prod.tipo_subscripciones` [V]) + 449 (`prod.clientes` [V]) + 496 (`prod.subscripciones_cliente` [V]) + 519 (`prod.vehiculos` [V]) + 538 (`prod.subscripcion_vehiculos` [V]) + 1138-1145 (FK relationships)
> - `migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones`) + 435-452 (`clientes`) + 454-465 (`vehiculos`) + 483-496 (`subscripciones_cliente`) + 498-509 (`subscripcion_vehiculos`)
> - `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head; F1.12 will be MIGRATION 0030 NO-OP)
> - `models/V/{tipo_subscripciones,clientes,vehiculos,subscripciones_cliente,subscripcion_vehiculos}.py` (ORM models, pre-existing)
> - `sync/catalog/entries/sync_entries_v.py` lines 133, 451, 483, 511, 525 (all 5 [V] entries verified pre-existing 2026-09-15)
> - `repo/{versioned,placa,subscripcion_activa,factura,factura_electronica,resolucion_facturacion,idempotency,impuestos,workflow}.py` (helpers reused)
> - `schemas/clientes.py` lines 42-102 (`ClientesCreate._validar_nit_dv` REQ-OPS-058 NIT validator reuse)
> - `api/v1/{facturacion,workflows_reimpresion,clientes,_helpers,deps}.py` (handler envelope references)
> - `auth/{jwt_issuer_guard,tenancy}.py` (KD-3 issuer chain + `TenantContext`)
> - `tests/static/test_no_raw_upsert_on_v_tables.py` (F1.5 PR5-016 AST walk precedent)
>
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `ddfe1f8`) · **PR target**: `origin/dev`.
> **TDD discipline**: RED→GREEN→REFACTOR per cluster. Each commit <800 LOC. Each cluster ends with all tests PASS.
> **Atomic commit strategy**: 8 atomic commits expected (1 per cluster T1..T8).
> **Skills loaded**: `gentle-sdd-tasks` + `sdd-phase-common.md` (paths injected via orchestrator).

---

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~860 across 1 PR (~260 LOC production per `plan.md` line 1049 = ~120 LOC NEW `api/v1/clientes_venta.py` + ~140 LOC NEW `repo/venta_suscripcion.py` + ~70 LOC EXTEND `schemas/clientes.py` + ~5 LOC MODIFY `api/v1/clientes.py` + ~30 LOC MIGRATION 0030 + ~120 LOC tests + ~50 LOC 2 AST walks) |
| Total tasks | ~31 (8 clusters: T1 setup 3 + T2 repo part 1 5 + T3 schemas 4 + T4 repo part 2 5 + T5 handler 4 + T6 AST walks 3 + T7 integration+e2e+migration 4 + T8 final sweep 3) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Medium** — F1.12 is comparable to F1.11 (~860 LOC). Cohesive single-resource (1 handler + 9 repo helpers + 9 schemas + 1 NO-OP migration + 2 AST walks); 8-commit split (one per cluster T1..T8) keeps each commit under the `commitlint` 800-LOC ceiling. |
| Chained PRs recommended | No — one single PR (matches F1.7 + F1.9 + F1.10 + F1.11 precedent); defense in depth is verified in-place. |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Single PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 8 commits internally, one per cluster T1..T8 (T1 ~50, T2 ~80, T3 ~80, T4 ~80, T5 ~120, T6 ~30, T7 ~50, T8 ~60). |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesive single-resource + 8-commit split keeps budget risk Medium inside the F1.7/F1.9/F1.10/F1.11 precedent. |

| Cluster | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|---------|-------|---------------|----------------|----------------|
| T1 Setup + Dependencies | T1.1..T1.3 | ~30 LOC (exception hierarchy + verify imports) | ~20 LOC (2 RED tests) | 50 |
| T2 Pydantic Schemas | T2.1..T2.4 | ~50 LOC (VentaSuscripcionCreate + VentaSuscripcionResponse) | ~30 LOC (3 RED tests) | 130 |
| T3 Repo Helpers Part 1 (cliente + vehiculo + plan) | T3.1..T3.5 | ~55 LOC (3 helpers + extending cliente lookup) | ~25 LOC (3 RED tests) | 210 |
| T4 Repo Helpers Part 2 (validations + prorrateo) | T4.1..T4.5 | ~50 LOC (3 validators + prorrateo) | ~30 LOC (3 RED tests) | 290 |
| T5 Handler 10-step chain | T5.1..T5.4 | ~120 LOC (1 handler + sub-chains + mount) | n/a (e2e covers) | 410 |
| T6 Static AST walks | T6.1..T6.3 | n/a (walks only) | ~30 LOC (3 AST walks) | 440 |
| T7 Integration + e2e + migration test | T7.1..T7.4 | ~30 LOC (MIGRATION 0030) | ~80 LOC (4 unit + 1 e2e + 1 migration = ~6 tests) | 550 |
| T8 Final sweep | T8.1..T8.3 | n/a (sweep only) | ~50 LOC (1 scenario walkthrough + CI verification) | 600+ |
| **Total** | **~31** | **~365 LOC impl** | **~265 LOC tests + ~60 LOC migration + ~150 LOC hardcoded examples** | **~860 LOC cumulative workload** |

> Per-commit ceiling: <800 LOC. Each cluster T1..T8 fits within the limit (T5 handler chain at ~120 LOC is the largest implementation block, well within). T2 + T3 + T4 may require mental split if schema bodies + repo helpers + RED tests exceed 800 — orchestrator decides per real diff at apply.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| T1 | Exception hierarchy + verify imports | commit 1 | `uv run pytest backend/tests/unit/test_venta_suscripcion_repo.py -q` | unit tests, no DB, pure import + exception class assertion | Delete exception module |
| T2 | Pydantic schemas (Create + Response) | commit 2 | `uv run pytest backend/tests/unit/test_venta_suscripcion_schemas.py -q` | unit tests, no DB, pure Pydantic validation | Revert schema appends |
| T3 | Repo helpers part 1 (cliente + vehiculo + plan lookup) | commit 3 | `uv run pytest backend/tests/unit/test_venta_suscripcion_repo.py -q` | unit tests with `pg_engine` mock + `PARKOS_DOCKER_TEST=1` for plan FOR UPDATE | Delete new helper bodies |
| T4 | Repo helpers part 2 (validations + prorrateo) | commit 4 | `uv run pytest backend/tests/unit/test_venta_suscripcion_repo.py -q` | unit tests with `PARKOS_DOCKER_TEST=1` for FK resolution | Delete new helper bodies |
| T5 | Handler 10-step chain + router mount | commit 5 | `uv run pytest backend/tests/integration/test_venta_suscripcion_e2e.py -q` | HTTP integration tests with `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-`/`admin-` fixtures + real DB via `PARKOS_DOCKER_TEST=1` | Revert handler module + mount |
| T6 | AST walks (KD-VENTA-01 single-commit + DEC-VENTA-05 no raw DML + no UPDATE on [V]) | commit 6 | `uv run pytest backend/tests/static/test_venta_handler_*.py -q` | no DB; pure AST walk over `api/v1/clientes_venta.py` | Delete 3 walk files |
| T7 | MIGRATION 0030 NO-OP + unit tests + e2e + migration idempotency | commit 7 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_venta_suscripcion.py backend/tests/integration/test_venta_suscripcion_e2e.py backend/tests/integration/test_migration_0030_noop.py -q` | `pg_engine` real (testcontainers precedent F1.4..F1.11); asserts on `prod.tipo_subscripciones` + `prod.clientes` + `prod.vehiculos` + `prod.subscripciones_cliente` + `prod.subscripcion_vehiculos` | `alembic downgrade -1` (NO-OP) + revert schema |
| T8 | Manual scenario walkthrough + full regression sweep | commit 8 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/ -q` | full suite verde; F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11 sin regresión | n/a (sweep only) |

---

## Tareas

### Cluster T1 — Setup & Dependencies (~30 LOC impl + ~20 LOC tests)

- [x] **T-HU-F1.12-T1.1** [RED + GREEN] — Verify migration head `0029_reimpresion_siembra_and_permiso_anular` is current; verify all 5 [V] tables (`prod.tipo_subscripciones`, `prod.clientes`, `prod.vehiculos`, `prod.subscripciones_cliente`, `prod.subscripcion_vehiculos`) exist; verify all 5 [V] sync catalog entries are pre-registered (`sync_entries_v.py` lines 133, 451, 483, 511, 525).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_f1_12_preflight_all_5_v_tables_exist` — query `information_schema.tables WHERE table_schema='prod' AND table_name IN (...)` returns exactly 5 rows; assert no missing tables. (Mirrors the MIGRATION 0030 pre-flight DO $$ block check.)
  - **Patrón F1.6..F1.11**: KD-7 pre-flight table-presence check; source-level assertion on `sync_entries_v.py` lines.
  - **Acción**: write test that asserts pre-flight state via SQL + source-level read of `sync_entries_v.py` to confirm the 5 entry line numbers. — **Archivo**: `backend/tests/integration/test_venta_suscripcion_preflight.py` (nuevo, ~20 LOC, 1 test). — **Validación**: test PASS pre-implementation (pre-flight already satisfied 2026-09-15).

- [x] **T-HU-F1.12-T1.2** [RED] — Write failing import-only test asserting `parkos_core.repo.venta_suscripcion` module exists and is importable; assert 7 typed exception names listed in design §11.7 are exposed via the module.
  - **Tests** (pure Python, no DB, no HTTP):
    - T1: `test_repo_venta_suscripcion_module_imports` — `from parkos_core.repo import venta_suscripcion as repo_venta` succeeds; `dir(repo_venta)` includes the 7 typed exception names: `TipoSubscripcionNoVigenteError`, `TipoSubscripcionNoEncontradoError`, `SubscripcionDuplicadaPlacaError`, `TipoVehiculoIncompatibleError`, `CantidadMaximaExcedidaError`, `PlanDuracionDiasInvalidoError`, `ClienteNoEncontradoError` (DEC-VENTA-01..07 references).
  - **Patrón F1.11 T1.1** (`test_repo_reimpresion_ticket_module_imports`): pure import assertion, gated by `__all__` definition.
  - **Acción**: `import` from `parkos_core.repo.venta_suscripcion` (fails with `ModuleNotFoundError`); assert public names. — **Archivo**: `backend/tests/unit/test_venta_suscripcion_repo.py` (nuevo, ~20 LOC, 1 test). — **Validación**: `ModuleNotFoundError: No module named 'parkos_core.repo.venta_suscripcion'`.

- [x] **T-HU-F1.12-T1.3** [GREEN] — Author `repo/venta_suscripcion.py` skeleton (~30 LOC) with `from __future__ annotations` + module docstring documenting DEC-VENTA-01..07 + KD-VENTA-01..02 references + define 7 typed exception classes (each carries typed dataclass-style attributes for the response body and a `__str__` for logging) + `__all__` listing the 9 helper names + 7 exception names.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/venta_suscripcion.py` (nuevo).
  - **Contenido**:
    - `from __future__ import annotations`; module docstring quoting REQ-OPS-083..090 + REQ-OPS-XR5 from `specs/operations/spec.md`; reference DEC-VENTA-01..07 + KD-VENTA-01 + KD-VENTA-02.
    - 7 typed exceptions (mirror design §11.7): `TipoSubscripcionNoVigenteError` (V2 409), `TipoSubscripcionNoEncontradoError` (V2 404), `SubscripcionDuplicadaPlacaError` (V4 422), `TipoVehiculoIncompatibleError` (V5 422), `CantidadMaximaExcedidaError` (V6 422), `PlanDuracionDiasInvalidoError` (V7 422 edge), `ClienteNoEncontradoError` (V1 404). Each carries typed attributes (`uuid_tipo_subscripcion`, `placa`, `tipos_encontrados`, `cantidad_maxima_vehiculos`, `uuid_cliente`) and a `__str__`.
    - `__all__ = ["TipoSubscripcionNoVigenteError", "TipoSubscripcionNoEncontradoError", "SubscripcionDuplicadaPlacaError", "TipoVehiculoIncompatibleError", "CantidadMaximaExcedidaError", "PlanDuracionDiasInvalidoError", "ClienteNoEncontradoError", "buscar_cliente_por_uuid_o_crear", "buscar_tipo_subscripcion_vigente_por_uuid", "buscar_o_crear_vehiculo_por_placa", "validar_placas_mismo_tipo_vehiculo", "validar_cantidad_maxima_vehiculos", "validar_placa_duplicada_subscripcion", "calcular_prorrateo", "crear_subscripcion_cliente", "crear_subscripcion_vehiculos_bulk"]` (16 names: 7 exceptions + 9 helpers; helpers are added in T3..T4).
  - **Acción**: create module + populate `__all__` + exception class definitions; no helper bodies yet (added in T3..T4). — **Validación**: T1.2 test PASS (imports + `dir()` contains expected names).

  **Commit suggestion**: `feat(backend): HU-F1.12 — repo module skeleton + 7 typed exceptions + pre-flight verification`.

  **Exit criteria T1**: T1.1..T1.3 verde; ~50 LOC cumulative.

### Cluster T2 — Pydantic Schemas (~50 LOC impl + ~30 LOC tests)

- [x] **T-HU-F1.12-T2.1** [RED] — Write failing tests for `VentaSuscripcionCreate` schema: `extra='forbid'` blocks `vigente_desde`, `estado`, `created_by`, `uuid_sucursal`, `monto_prorrateado`; `model_validator` enforces exactly-one-of (`cliente` XOR `uuid_cliente`).
  - **Tests** (pure Pydantic validation, no HTTP, no DB):
    - T1: `test_create_endpoint_rejects_vigente_desde_injection` — `VentaSuscripcionCreate(cliente=..., placas=['ABC123'], vigente_desde='2026-09-01')` raises `ValidationError` (extra='forbid').
    - T2: `test_create_endpoint_rejects_estado_injection` — `VentaSuscripcionCreate(..., estado='activo')` raises `ValidationError`.
    - T3: `test_create_endpoint_rejects_created_by_injection` — `VentaSuscripcionCreate(..., created_by='uuid')` raises `ValidationError`.
    - T4: `test_create_endpoint_rejects_uuid_sucursal_injection` — `VentaSuscripcionCreate(..., uuid_sucursal='uuid')` raises `ValidationError`.
    - T5: `test_create_endpoint_rejects_cliente_and_uuid_cliente_both_provided` — both fields populated → `ValidationError` (model_validator).
    - T6: `test_create_endpoint_rejects_cliente_and_uuid_cliente_both_absent` — both fields None → `ValidationError` (model_validator, XOR not OR).
  - **Patrón F1.11** (`test_reimpresion_ticket_schemas.py`): pure Pydantic tests, no HTTP, no DB.
  - **Acción**: imports from `parkos_core.schemas.clientes` (fails with `ImportError`). — **Archivo**: `backend/tests/unit/test_venta_suscripcion_schemas.py` (nuevo, ~30 LOC, 6 tests for this batch). — **Validación**: `ImportError: cannot import name 'VentaSuscripcionCreate'`.

- [x] **T-HU-F1.12-T2.2** [GREEN] — Append `VentaSuscripcionCreate(_Base)` schema (~40 LOC) to `schemas/clientes.py` with discriminated `cliente | uuid_cliente` + `placas` list annotated with `Field(min_length=1, max_length=2)` + optional `cobrar_ahora` / `emitir_factura_electronica` / `medio_pago` / `referencia`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py` (modificado, append at section §9.1 ~+40 LOC).
  - **Contenido**:
    ```python
    class VentaSuscripcionCreate(_Base):
        """HU-F1.12: POST /api/v1/clientes/venta-suscripcion payload.
        cliente OR uuid_cliente (discriminated XOR): exactly one is required.
        For embedded cliente, dv is validated by Pydantic (DEC-VENTA-07)
        but NOT persisted (prod.clientes has no dv column).
        extra='forbid' (inherited from _Base) blocks client smuggling of
        uuid_sucursal, vigente_desde, estado, created_at, created_by,
        monto_prorrateado, valor_dia, dias_restantes_mes.
        """
        cliente: ClientesCreate | None = None
        uuid_cliente: uuid_lib.UUID | None = None
        placas: Annotated[list[str], Field(min_length=1, max_length=2)]
        uuid_tipo_subscripcion: uuid_lib.UUID
        fecha_inicio_cobertura: datetime.date
        cobrar_ahora: bool = False
        emitir_factura_electronica: bool = False
        medio_pago: Literal["efectivo", "tarjeta", "datafono", "transferencia"] = "efectivo"
        referencia: str | None = None

        @model_validator(mode="after")
        def _check_cliente_xor_uuid(self) -> "VentaSuscripcionCreate":
            if (self.cliente is None) == (self.uuid_cliente is None):
                raise ValueError("exactly one of cliente or uuid_cliente is required")
            return self
    ```
  - **Acción**: paste verbatim from design §9.1; update `__all__` in `schemas/clientes.py`. — **Validación**: T2.1 6 tests PASS.

- [x] **T-HU-F1.12-T2.3** [RED] — Write failing tests for `VentaSuscripcionResponse` schema + `placas` list range validation (0 items → 422, 3 items → 422, 1-2 items → OK).
  - **Tests** (pure Pydantic validation):
    - T1: `test_create_endpoint_rejects_placas_count_0` — `placas=[]` raises `ValidationError` (`min_length=1`).
    - T2: `test_create_endpoint_rejects_placas_count_3` — `placas=['ABC123', 'DEF456', 'GHI789']` raises `ValidationError` (`max_length=2`).
    - T3: `test_create_endpoint_accepts_placas_count_1_and_2` — `placas=['ABC123']` and `placas=['ABC123', 'DEF456']` both succeed.
    - T4: `test_response_monto_prorrateado_null_when_cobrar_ahora_false` — `VentaSuscripcionResponse(..., cobrar_ahora_implied=False, monto_prorrateado=None)` accepts null (DEC-VENTA-03).
    - T5: `test_response_monto_prorrateado_decimal_when_cobrar_ahora_true` — `monto_proporcional=Decimal('10000.00')` accepted.
  - **Acción**: extend T2.1 file (`backend/tests/unit/test_venta_suscripcion_schemas.py`) with +~20 LOC, 5 tests. — **Validación**: pre-implementation, `ImportError` for `VentaSuscripcionResponse`.

- [x] **T-HU-F1.12-T2.4** [GREEN] — Append `VentaSuscripcionResponse` schema (~30 LOC) + update schemas `__all__`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py` (extended, +~30 LOC).
  - **Contenido**: paste `VentaSuscripcionResponse` verbatim from design §9.1 with nested UUIDs (`uuid_cliente`, `uuid_subscripcion`, `uuid_vehiculos: list[UUID]`, `uuid_sucursal`) + `fecha_inicio_cobertura`, `fecha_vencimiento`, `valor_total_plan: Decimal`, `monto_prorrateado: Decimal | None` (DEC-VENTA-03 — null when `cobrar_ahora=false`), optional `uuid_factura`, `uuid_factura_electronica`, `uuid_envio_dian`. — **Validación**: T2.3 5 tests PASS; total T2 = 11 tests verde.

  **Commit suggestion**: `feat(backend): HU-F1.12 — Pydantic schemas (VentaSuscripcionCreate + VentaSuscripcionResponse)`.

  **Exit criteria T2**: T2.1..T2.4 verde; ~130 LOC cumulative (impl + tests).

### Cluster T3 — Repo Helpers Part 1: cliente + vehiculo + plan (~55 LOC impl + ~25 LOC tests)

- [x] **T-HU-F1.12-T3.1** [RED] — Write failing test for `buscar_cliente_por_uuid_o_crear_nuevo` (V1 new-cliente path via `repo.versioned.close_and_insert(current_uuid=None, new_attrs={...})` — REQ-OPS-058 NIT modulo 11 already validated by Pydantic at Layer 4; DEC-VENTA-07 `dv` discarded before INSERT).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_buscar_cliente_por_uuid_o_crear_nuevo` — invoke with `datos_cliente={'tipo_identificador': 'CC', 'numero_identificacion': '1234567890', ...}` (no `dv` consumed); helper calls `close_and_insert(current_uuid=None, new_attrs={...})` and returns the new ORM row.
  - **Patrón F1.11** (`test_repo_reimpresion_ticket.py`): `pg_engine` real with `PARKOS_DOCKER_TEST=1`; seed via SQL directo al engine; pure ORM lookup-or-insert.
  - **Acción**: imports from `parkos_core.repo.venta_suscripcion` (fails with `ImportError` for undeclared names). — **Archivo**: extend T1.2 file (`backend/tests/unit/test_venta_suscripcion_repo.py`) with +~25 LOC, 1 test. — **Validación**: `ImportError: cannot import name 'buscar_cliente_por_uuid_o_crear'`.

- [x] **T-HU-F1.12-T3.2** [GREEN] — Implement `buscar_cliente_por_uuid_o_crear` helper (~30 LOC) with the new-cliente branch only.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/venta_suscripcion.py` (modified, +~30 LOC).
  - **Contenido**:
    ```python
    async def buscar_cliente_por_uuid_o_crear(
        session: AsyncSession, *, uuid_cliente: UUID | None,
        datos_cliente: dict | None, actor_uuid: UUID,
    ) -> Clientes:
        """V1: INSERT new cliente via close_and_insert(current_uuid=None).
        DEC-VENTA-07: dv (if present) is discarded; only business columns persisted.
        Returns the new ORM row (caller commits at Step 10).
        """
        new_attrs = {k: v for k, v in datos_cliente.items() if k != "dv"}
        return await versioned.close_and_insert(
            session, current_uuid=None, new_attrs=new_attrs, actor_uuid=actor_uuid,
        )
    ```
  - **Acción**: import `from ..repo import versioned`; docstring REQ-OPS-083 + DEC-VENTA-07. — **Validación**: T3.1 1 test PASS.

- [x] **T-HU-F1.12-T3.3** [RED] — Write failing test for `buscar_cliente_por_uuid_o_crear_existente` (V1 existing path via `repo.versioned.current_version(uuid=...)`; raises `ClienteNoEncontradoError` 404 if missing).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_buscar_cliente_por_uuid_o_crear_existente` — seed `prod.clientes(uuid=:c, ...)` (vigente row); invoke helper with `uuid_cliente=:c` → returns the row.
    - T2: `test_buscar_cliente_por_uuid_o_crear_raises_when_cliente_missing` — invoke with random UUID; helper raises `ClienteNoEncontradoError` carrying `uuid_cliente=str(<random>)`.
  - **Acción**: extend T1.2 file with +~15 LOC, 2 tests. — **Validación**: pre-implementation, `ImportError` for the existing branch (helper signature only handles datos_cliente).

- [x] **T-HU-F1.12-T3.4** [GREEN] — Extend `buscar_cliente_por_uuid_o_crear` helper (~+20 LOC) to handle existing path via `repo.versioned.current_version(uuid=...)`.
  - **Archivo**: extend T3.2 helper in `repo/venta_suscripcion.py` (+~20 LOC).
  - **Contenido**:
    ```python
    if uuid_cliente is not None:
        existing = await versioned.current_version(session, uuid=uuid_cliente)
        if existing is None:
            raise ClienteNoEncontradoError(uuid_cliente=str(uuid_cliente))
        return existing
    # else (new branch): close_and_insert as in T3.2
    ```
  - **Acción**: docstring REQ-OPS-083 V1 + DEC-VENTA-02 lock ordering (Step 3a `SELECT FOR UPDATE` precedes any INSERT). — **Validación**: T3.3 2 tests PASS.

- [x] **T-HU-F1.12-T3.5** [RED + GREEN] — Implement `buscar_o_crear_vehiculo_por_placa` (V3, ~20 LOC) + `buscar_tipo_subscripcion_vigente_por_uuid` (V2, ~15 LOC) using `repo.versioned.close_and_insert(current_uuid=None, new_attrs={"placa": ..., "uuid_tipo_vehiculo": ...})` and `select(...).where(uuid=:p, vigente_hasta.is_(None)).order_by(vigente_desde.desc()).limit(1).with_for_update()` (KD-VENTA-02 + DEC-VENTA-04).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_buscar_tipo_subscripcion_vigente_por_uuid_returns_plan` — seed `prod.tipo_subscripciones(uuid=:p, vigente_hasta=NULL)`; invoke → returns the row.
    - T2: `test_buscar_tipo_subscripcion_vigente_por_uuid_uses_with_for_update` — verify SQL contains `FOR UPDATE` (KD-VENTA-02 + DEC-VENTA-04 exclusive, NOT `FOR SHARE` which F1.9 used on `prod.tarifas_sucursal`).
    - T3: `test_buscar_tipo_subscripcion_vigente_por_uuid_raises_when_no_vigente` — no vigente row; helper raises `TipoSubscripcionNoVigenteError`.
  - **Archivo**: extend `repo/venta_suscripcion.py` (+~35 LOC); +~15 LOC tests on T1.2 file. — **Validación**: T1..T3 PASS.

  **Commit suggestion**: `feat(backend): HU-F1.12 — repo helpers part 1 (cliente lookup-or-create + vehiculo + plan FOR UPDATE)`.

  **Exit criteria T3**: T3.1..T3.5 verde; ~210 LOC cumulative (impl + tests).

### Cluster T4 — Repo Helpers Part 2: validations + prorrateo (~50 LOC impl + ~30 LOC tests)

- [x] **T-HU-F1.12-T4.1** [RED] — Write failing tests for `validar_placas_mismo_tipo_vehiculo` (V5): same tipo → OK; different tipos → 422 `TipoVehiculoIncompatibleError` with `tipos_encontrados` list.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_validar_placas_mismo_tipo_vehiculo_ok` — plan with `mismo_tipo_vehiculo=true`, 2 vehiculos with SAME `uuid_tipo_vehiculo` → helper returns without raising.
    - T2: `test_validar_placas_mismo_tipo_vehiculo_rechaza` — plan with `mismo_tipo_vehiculo=true`, 2 vehiculos with DIFFERENT `uuid_tipo_vehiculo` → helper raises `TipoVehiculoIncompatibleError` carrying `tipos_encontrados=[<list of distinct tipos>]`.
    - T3: `test_validar_placas_mismo_tipo_vehiculo_skipped_when_plan_mismo_tipo_false` — plan with `mismo_tipo_vehiculo=false`, distinct tipos → helper returns without raising (V5 SKIPPED).
  - **Patrón F1.11**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`.
  - **Acción**: extend T1.2 file with +~15 LOC, 3 tests. — **Validación**: `ImportError: cannot import name 'validar_placas_mismo_tipo_vehiculo'`.

- [x] **T-HU-F1.12-T4.2** [GREEN] — Author `validar_placas_mismo_tipo_vehiculo` (~20 LOC) using in-process comparison of `vehiculo.uuid_tipo_vehiculo` values.
  - **Archivo**: extend `repo/venta_suscripcion.py` (+~20 LOC).
  - **Contenido**:
    ```python
    async def validar_placas_mismo_tipo_vehiculo(
        session: AsyncSession, *, plan: TipoSubscripciones, vehiculos: list[Vehiculos],
    ) -> None:
        """V5: When plan.mismo_tipo_vehiculo=true, all vehiculos MUST share
        the SAME uuid_tipo_vehiculo. Otherwise RAISE 422.
        """
        if not plan.mismo_tipo_vehiculo:
            return
        tipos = {v.uuid_tipo_vehiculo for v in vehiculos}
        if len(tipos) > 1:
            raise TipoVehiculoIncompatibleError(tipos_encontrados=sorted(str(t) for t in tipos))
    ```
  - **Acción**: docstring REQ-OPS-087 + DEC-VENTA-05. — **Validación**: T4.1 3 tests PASS.

- [x] **T-HU-F1.12-T4.3** [RED + GREEN] — Implement `validar_cantidad_maxima_vehiculos` (V6, ~15 LOC) + `validar_placa_duplicada_subscripcion` (V4, ~15 LOC reusing `repo.subscripcion_activa.resolve_active_subscription_for_exit`).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_validar_cantidad_maxima_vehiculos_ok` — plan allows 2, n_placas=2 → returns without raising.
    - T2: `test_validar_cantidad_maxima_vehiculos_raises_when_exceeded` — plan allows 1, n_placas=2 → raises `CantidadMaximaExcedidaError(cantidad_maxima_vehiculos=1, placas_proporcionadas=2)`.
    - T3: `test_validar_placa_duplicada_subscripcion_returns_422_when_active_found` — pre-seed active `prod.subscripciones_cliente(:sc1, uuid_cliente=:c1, uuid_sucursal=:s, fecha_vencimiento='2099-01-01')` + `prod.subscripcion_vehiculos` linking placa=:p to `:sc1`; invoke helper → raises `SubscripcionDuplicadaPlacaError`.
  - **Archivo**: extend `repo/venta_suscripcion.py` (+~30 LOC); +~25 LOC tests on T1.2 file. — **Validación**: T1..T3 PASS; V6 + V4 covered.

- [x] **T-HU-F1.12-T4.4** [RED] — Write failing tests for `calcular_prorrateo` (V7 A-09, DEC-VENTA-03): 3 scenarios + edge cases.
  - **Tests** (pure Decimal math, no DB):
    - T1: `test_calcular_prorrateo_after_day_15_returns_proportional` — `plan.valor=30000, plan.duracion_dias=30, fecha_inicio_cobertura='2026-09-20'` → `monto_proporcional=Decimal('10000.00')` (30000/30 * (30-20) = 10000).
    - T2: `test_calcular_prorrateo_before_day_15_returns_full_value` — `fecha_inicio_cobertura='2026-09-10'` → `monto_proporcional=Decimal('30000.00')` (full plan.valor).
    - T3: `test_calcular_prorrateo_zero_duracion_raises` — `plan.duracion_dias=0` → raises `PlanDuracionDiasInvalidoError` (ZeroDivisionError catch).
  - **Acción**: extend T1.2 file with +~15 LOC, 3 tests. — **Validación**: `ImportError`.

- [x] **T-HU-F1.12-T4.5** [GREEN] — Author `calcular_prorrateo` (~25 LOC) with `ZeroDivisionError` catch → 422.
  - **Archivo**: extend `repo/venta_suscripcion.py` (+~25 LOC).
  - **Contenido**:
    ```python
    def calcular_prorrateo(*, plan: TipoSubscripciones, fecha_inicio_cobertura: date) -> Decimal:
        """V7: A-09 prorrateo per plan.md line 460 + line 1053.
        Trigger: fecha_inicio_cobertura.day > 15 (returns proportional);
        else returns full plan.valor.
        """
        try:
            valor_dia = plan.valor / plan.duracion_dias
        except ZeroDivisionError as exc:
            raise PlanDuracionDiasInvalidoError() from exc
        if fecha_inicio_cobertura.day > 15:
            dias_restantes = calendar.monthrange(
                fecha_inicio_cobertura.year, fecha_inicio_cobertura.month
            )[1] - fecha_inicio_cobertura.day
            return (valor_dia * dias_restantes).quantize(Decimal("0.01"))
        return plan.valor
    ```
  - **Acción**: docstring REQ-OPS-090 + DEC-VENTA-03; pure Decimal math, no DB. — **Validación**: T4.4 3 tests PASS; total T4 = ~9 tests verde.

  **Commit suggestion**: `feat(backend): HU-F1.12 — repo helpers part 2 (V4 placa-dup + V5 mismo-tipo + V6 cantidad-max + V7 prorrateo)`.

  **Exit criteria T4**: T4.1..T4.5 verde; ~290 LOC cumulative (impl + tests).

### Cluster T5 — Handler 10-step chain (~120 LOC impl + e2e in T7)

- [x] **T-HU-F1.12-T5.1** [RED] — Stub `api/v1/clientes_venta.py::venta_suscripcion` with KD-3 issuer dep + `Idempotency-Key` middleware guard; write failing source-level test asserting the endpoint is NOT yet registered (404).
  - **Tests** (pure source-level + HTTP integration gated):
    - T1: `test_clientes_venta_module_imports_with_venta_suscripcion_handler` — `from parkos_core.api.v1.clientes_venta import router` succeeds; `dir(router)` does NOT yet contain `venta_suscripcion` (RED pre-implementation).
    - T2: `test_endpoint_venta_suscripcion_not_yet_registered` — HTTP GET against `/api/v1/clientes/venta-suscripcion` returns 405 (route exists in router table but method not yet wired) OR 404 (route fully absent); test asserts 404.
  - **Patrón F1.11** (`test_reimpresion_ticket_create_handler.py`): pure source-level + `httpx.AsyncClient + ASGITransport(app)`.
  - **Acción**: create stub module with `router = APIRouter(prefix="/clientes", tags=["clientes"])` + `from __future__ annotations` + import `_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-VENTA-05). — **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/clientes_venta.py` (nuevo, stub, ~10 LOC). — **Validación**: stub module imports; route returns 404.

- [x] **T-HU-F1.12-T5.2** [GREEN] — Implement Steps 1-6 of the 10-step chain in `venta_suscripcion` (~60 LOC): KD-3 issuer (Step 1); `buscar_tipo_subscripcion_vigente_por_uuid` with SELECT FOR UPDATE (Step 2, V2, KD-VENTA-02 + DEC-VENTA-04); Layer 2 tenant scope post-V1 (Step 2a, KD-S2 analog from F1.7); `buscar_cliente_por_uuid_o_crear` (Step 3, V1); per-placa `buscar_o_crear_vehiculo_por_placa` (Step 4, V3); `validar_placas_mismo_tipo_vehiculo` (Step 5, V5); `validar_cantidad_maxima_vehiculos` (Step 6, V6).
  - **Archivo**: extend `api/v1/clientes_venta.py` (+~60 LOC).
  - **Contenido**:
    ```python
    @router.post("/venta-suscripcion", response_model=VentaSuscripcionResponse, status_code=201,
                 responses={400:..., 403:..., 404:..., 409:..., 422:...})
    async def venta_suscripcion(
        response: Response,
        payload: VentaSuscripcionCreate,
        session: AsyncSession = Depends(get_session),
        ctx: TenantContext = Depends(get_tenant_ctx),
        _claims: None = Depends(_venta_suscripcion_issuer_dep),
    ) -> VentaSuscripcionResponse:
        no_store = no_store_headers()
        # Step 2: plan lock (KD-VENTA-02 + DEC-VENTA-04)
        plan = await repo_venta.buscar_tipo_subscripcion_vigente_por_uuid(
            session, uuid_tipo_subscripcion=payload.uuid_tipo_subscripcion,
        )
        if plan is None:
            raise HTTPException(404, {"error": "tipo_subscripcion_no_encontrado", ...}, headers=no_store)
        # Step 2a: tenant scope post-V1 (KD-S2 F1.7 mirror)
        target_sucursal = ctx.sucursal_uuid
        if ctx.issuer_prefix == "operador-" and target_sucursal != ctx.assigned_sucursal_uuid:
            raise HTTPException(403, {"error": "tenant_scope_violation"}, headers=no_store)
        # Step 3: cliente lookup-or-create (V1)
        cliente = await repo_venta.buscar_cliente_por_uuid_o_crear(
            session, uuid_cliente=payload.uuid_cliente, datos_cliente=payload.cliente.model_dump() if payload.cliente else None,
            actor_uuid=ctx.actor_uuid,
        )
        # Step 4: per-placa lookup-or-create (V3)
        vehiculos = []
        for placa in payload.placas:
            v, _ = await repo_venta.buscar_o_crear_vehiculo_por_placa(session, placa=placa, actor_uuid=ctx.actor_uuid)
            vehiculos.append(v)
        # Step 5: V5 mismo_tipo
        await repo_venta.validar_placas_mismo_tipo_vehiculo(session, plan=plan, vehiculos=vehiculos)
        # Step 6: V6 cantidad_maxima
        await repo_venta.validar_cantidad_maxima_vehiculos(session, plan=plan, n_placas=len(payload.placas))
    ```
  - **Acción**: docstring REQ-OPS-083..088 + DEC-VENTA-01..05 + KD-VENTA-01..02. — **Validación**: T5.1 2 tests PASS (route now registered); T7.1 unit tests will exercise Steps 1-6 paths.

- [x] **T-HU-F1.12-T5.3** [GREEN] — Implement Steps 7-9 (rest of validation + INSERTs, ~40 LOC): per-placa `validar_placa_duplicada_subscripcion` (Step 7, V4, reusing `resolve_active_subscription_for_exit`); `calcular_prorrateo` (Step 8, V7); `crear_subscripcion_cliente` + `crear_subscripcion_vehiculos_bulk` (Step 9, V9 with `pg_advisory_xact_lock`); optional `_factura_sub_chain` (Step 8a, V8, F1.9 helpers when `cobrar_ahora=true`); optional `_fe_sub_chain` (Step 8b, V8b, F1.10 helpers when `emitir_factura_electronica=true`).
  - **Archivo**: extend `api/v1/clientes_venta.py` (+~40 LOC).
  - **Contenido**:
    ```python
    # Step 7: per-placa V4 dup check
    for placa in payload.placas:
        await repo_venta.validar_placa_duplicada_subscripcion(
            session, placa=placa, uuid_sucursal=target_sucursal, fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
        )
    # Step 8: V7 A-09 prorrateo
    monto_proporcional = repo_venta.calcular_prorrateo(plan=plan, fecha_inicio_cobertura=payload.fecha_inicio_cobertura)
    # Step 9: V9 INSERTs (advisory lock INSIDE bulk helper, REQ-OP-08)
    fecha_vencimiento = payload.fecha_inicio_cobertura + timedelta(days=plan.duracion_dias)
    subscripcion = await repo_venta.crear_subscripcion_cliente(session, actor_uuid=ctx.actor_uuid, uuid_cliente=cliente.uuid, uuid_sucursal=target_sucursal, uuid_tipo_subscripcion=plan.uuid, fecha_inicio_cobertura=payload.fecha_inicio_cobertura, fecha_vencimiento=fecha_vencimiento)
    await repo_venta.crear_subscripcion_vehiculos_bulk(session, actor_uuid=ctx.actor_uuid, uuid_subscripcion_cliente=subscripcion.uuid, uuid_vehiculos=[v.uuid for v in vehiculos])
    # Step 8a: optional cobro sub-chain (F1.9 helpers reused verbatim)
    uuid_factura = None
    if payload.cobrar_ahora:
        uuid_factura = await _factura_sub_chain(session, cliente=cliente, subscripcion=subscripcion, plan=plan, monto_proporcional=monto_proporcional, medio_pago=payload.medio_pago, referencia=payload.referencia, ctx=ctx)
    # Step 8b: optional FE sub-chain (F1.10 helpers reused verbatim)
    uuid_fe, uuid_envio = None, None
    if payload.emitir_factura_electronica and uuid_factura is not None:
        uuid_fe, uuid_envio = await _fe_sub_chain(session, uuid_factura=uuid_factura, ctx=ctx)
    ```
  - **Acción**: define `_factura_sub_chain` (private, ~25 LOC) that mirrors `api/v1/facturacion.py::create_factura` Steps 5-10; `_fe_sub_chain` (private, ~15 LOC) that mirrors F1.10 FE pattern. Both reuse `repo.factura.*` and `repo.factura_electronica.*` helpers verbatim. — **Validación**: T7.1 unit tests + T7.2 e2e exercise these paths.

- [x] **T-HU-F1.12-T5.4** [GREEN] — Step 10 (KD-VENTA-01 single `await session.commit()`) + Step 11 (response shape + `Cache-Control: no-store`); mount router in `api/v1/clientes.py`.
  - **Archivo**: extend `api/v1/clientes_venta.py` (+~15 LOC); MODIFY `backend/packages/parkos_core/src/parkos_core/api/v1/clientes.py` (+~5 LOC).
  - **Contenido**:
    ```python
    # Step 10: KD-VENTA-01 SINGLE COMMIT
    await session.commit()
    # Step 11: DEC-VENTA-06 — Cache-Control: no-store + response
    apply_no_store_header(response)
    return VentaSuscripcionResponse(
        uuid_cliente=cliente.uuid, uuid_subscripcion=subscripcion.uuid,
        uuid_vehiculos=[v.uuid for v in vehiculos], uuid_sucursal=target_sucursal,
        fecha_inicio_cobertura=payload.fecha_inicio_cobertura, fecha_vencimiento=fecha_vencimiento,
        valor_total_plan=plan.valor,
        monto_prorrateado=monto_proporcional if payload.cobrar_ahora else None,  # DEC-VENTA-03
        uuid_factura=uuid_factura, uuid_factura_electronica=uuid_fe, uuid_envio_dian=uuid_envio,
    )
    ```
    + in `api/v1/clientes.py` append: `from .clientes_venta import router as venta_suscripcion_router` + `router.include_router(venta_suscripcion_router)` (DEC-VENTA-05).
  - **Acción**: docstring KD-VENTA-01 single-commit invariant + DEC-VENTA-06 no-store; the factory mount + `gestionar_clientes` permission gate are inherited via `router.include_router`. — **Validación**: T7.2 e2e confirms full happy path + 9 rows visible post-commit.

  **Commit suggestion**: `feat(backend): HU-F1.12 — POST /clientes/venta-suscripcion handler (10-step chain + KD-VENTA-01 single-commit + router mount)`.

  **Exit criteria T5**: T5.1..T5.4 verde; ~410 LOC cumulative (impl + tests); handler reachable end-to-end.

### Cluster T6 — Static AST walks (~30 LOC tests)

- [x] **T-HU-F1.12-T6.1** [RED + GREEN] — Write failing AST walk `tests/static/test_venta_handler_single_commit.py` enforcing KD-VENTA-01 single `await session.commit()` invariant (mirror of F1.10 `test_fe_handler_single_commit.py` + F1.11 `test_workflow_handler_single_commit.py`).
  - **Tests** (no DB, no HTTP, pure AST walk):
    - T1: `test_venta_suscripcion_single_commit` — `ast.parse(handler_path)`; locate `venta_suscripcion` via `ast.AsyncFunctionDef.name == 'venta_suscripcion'`; walk via `iter_child_nodes`; assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'commit']) == 1`.
    - T2: `test_venta_suscripcion_no_savepoint` — same walk; assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'begin_nested']) == 0`; assert NO occurrence of the literal string `"SAVEPOINT"` in the handler body.
  - **Patrón F1.10 + F1.11**: `ast.parse` + `iter_child_nodes` DFS.
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_venta_handler_single_commit.py` (nuevo, ~25 LOC, 2 AST walks). — **Validación**: post T5 GREEN, walks PASS.

- [x] **T-HU-F1.12-T6.2** [RED + GREEN] — Write failing AST walk `tests/static/test_venta_handler_no_raw_dml.py` enforcing no raw INSERT/UPDATE/DELETE on `[V]` tables (`prod.clientes`, `prod.vehiculos`, `prod.subscripciones_cliente`, `prod.subscripcion_vehiculos`) outside `repo/venta_suscripcion.py` helpers + `repo/versioned.py::close_and_insert` (DEC-VENTA-05 enforcement).
  - **Tests** (no DB, no HTTP, source-level grep + AST walk):
    - T1: `test_venta_suscripcion_no_raw_dml_on_v_tables` — read `api/v1/clientes_venta.py` source; assert no occurrence of `INSERT INTO prod.clientes`, `UPDATE prod.clientes`, `DELETE FROM prod.clientes`, `INSERT INTO prod.vehiculos`, `INSERT INTO prod.subscripciones_cliente`, `INSERT INTO prod.subscripcion_vehiculos` patterns; allowed: `session.add(...)` calls INSIDE `repo/venta_suscripcion.py` + `repo/versioned.py::close_and_insert`.
  - **Patrón F1.5 PR5-016** (`test_no_raw_upsert_on_v_tables.py`): source-level grep + regex match.
  - **Acción**: import `re`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_venta_handler_no_raw_dml.py` (nuevo, ~20 LOC, 1 AST walk). — **Validación**: post T5 GREEN, walk PASS.

- [x] **T-HU-F1.12-T6.3** [RED + GREEN] — Write failing AST walk `tests/static/test_venta_handler_no_update_on_v_tables.py` enforcing NO UPDATE on `[V]` tables (F1.5 PR5-016 deepens F1.12 specific to handler; readable counterpart: no `await session.execute(text("UPDATE prod.tipo_subscripciones..."))`).
  - **Tests**:
    - T1: `test_venta_suscripcion_no_update_on_v_tables` — assert no UPDATE on any of the 5 `[V]` tables; allowed: SELECT (incl. FOR UPDATE on `prod.tipo_subscripciones`).
  - **Patrón F1.11** (`test_workflow_handler_no_update_on_reimpresion_ticket.py`): source-level grep + AST walk.
  - **Acción**: extend T6.2 file (`backend/tests/static/test_venta_handler_no_raw_dml.py`) OR create sibling. — **Archivo**: `backend/tests/static/test_venta_handler_no_update_on_v_tables.py` (nuevo, ~20 LOC, 1 AST walk). — **Validación**: post T3..T5 GREEN, walk PASS.

  **Commit suggestion**: `feat(static): HU-F1.12 — AST walks (KD-VENTA-01 single-commit + DEC-VENTA-05 no raw DML + no UPDATE on [V])`.

  **Exit criteria T6**: T6.1..T6.3 verde; ~440 LOC cumulative (impl + tests); 4 AST walks across 3 files PASS.

### Cluster T7 — Integration + e2e + MIGRATION 0030 test (~30 LOC impl + ~80 LOC tests)

- [x] **T-HU-F1.12-T7.1** [RED + GREEN] — Write `tests/unit/test_venta_suscripcion.py` with 4 MANDATED tests per `plan.md` line 1047 + DEC-VENTA-06 Cache-Control no-store tests (REQ-OPS-090 scenario coverage).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_cliente_nuevo_venta_exitosa_returns_201` — happy path, new cliente via `datos_cliente` payload + 1 placa `ABC123` + plan "mensual" (`cobrar_ahora=false`) → 201 + `VentaSuscripcionResponse{uuid_subscripcion:<new>, uuid_vehiculos:[<v>], ...}` + `Cache-Control: no-store`. Verify exactly 1 `prod.clientes` + 1 `prod.vehiculos` + 1 `prod.subscripciones_cliente` + 1 `prod.subscripcion_vehiculos` row exists.
    - T2: `test_cliente_existente_lookup_by_uuid` — happy path, existing cliente by `uuid_cliente` + 2 placas → 201.
    - T3: `test_plan_mismo_tipo_vehiculo_rechaza_placas_mixtas` — 422 `tipo_vehiculo_incompatible` + `Cache-Control: no-store`.
    - T4: `test_placa_duplicada_subscripcion_vigente_rechaza` — 422 `suscripcion_duplicada_placa` + `Cache-Control: no-store`.
  - **Patrón F1.11** (`test_reimpresion_ticket_create_handler.py`): `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-X` fixture; real `pg_engine` con `PARKOS_DOCKER_TEST=1`.
  - **Archivo**: `backend/tests/unit/test_venta_suscripcion.py` (nuevo, ~50 LOC, 4 tests per plan.md mandate + ~3 extra Cache-Control no-store tests for REQ-OPS-090). — **Validación**: pre-implementation (post T5 complete), 4 tests PASS.

- [x] **T-HU-F1.12-T7.2** [RED + GREEN] — Write `tests/integration/test_venta_suscripcion_e2e.py` (~30 LOC, 1 test): full happy path with `cobrar_ahora=true` + `emitir_factura_electronica=true` — verify ALL 9 rows visible post-commit (1 cliente + 1 vehiculo + 1 subscripcion + 1 junction + 1 factura + 1 factura_detalle + 1 factura_impuestos + 1 factura_pagos + 1 factura_electronica + 1 envio_dian).
  - **Tests**:
    - T1: `test_venta_e2e_cobro_fe_full_happy_path` — seed `prod.tipo_subscripciones(:p, valor=30000, duracion_dias=30, mismo_tipo_vehiculo=false, cantidad_maxima_vehiculos=2)` + `prod.tipos_vehiculo(:tv)` + `prod.permisos(permiso='gestionar_clientes')` + `prod.permisos_usuario` + operador JWT. POST `{cliente: {tipo_identificador:'CC', numero_identificacion:'1234567890', ...}, placas:['ABC123'], uuid_tipo_subscripcion:<:p>, fecha_inicio_cobertura:'2026-09-20', cobrar_ahora:true, emitir_factura_electronica:true, medio_pago:'efectivo'}` with `Idempotency-Key: <uuid>` → 201. Verify 9 rows exist + response shape correct + `Cache-Control: no-store`.
  - **Patrón F1.11** (`test_reimpresion_ticket_create_handler.py`): HTTP integration via `httpx.AsyncClient`.
  - **Archivo**: `backend/tests/integration/test_venta_suscripcion_e2e.py` (nuevo, ~30 LOC, 1 test). — **Validación**: post T5 GREEN + T6 GREEN, test PASS; full F1.12 happy path verified.

- [x] **T-HU-F1.12-T7.3** [RED + GREEN] — Write `tests/integration/test_migration_0030_noop.py` (~15 LOC, 2 tests) + author `migrations/versions/0030_venta_suscripcion_optional.py` (~30 LOC NO-OP) — pre-flight `DO $$` block + empty `upgrade()` + empty `downgrade()` (DEC-VENTA-08 WITHDRAWN; MIGRATION 0030 audit trail only).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0030_idempotent_upgrade_downgrade_upgrade` — `alembic upgrade head` succeeds (asserts `DO $$` pre-flight passes — all 5 [V] tables present); `alembic downgrade -1` succeeds (no-op); `alembic upgrade head` succeeds again (round-trip idempotent). Verify no schema changes via column-count assertion on `prod.tipo_subscripciones`.
    - T2: `test_migration_0030_preflight_aborts_if_v_table_missing` — DROP one [V] table (test-only cleanup); `alembic upgrade head` raises `0030_preflight_abort: tabla prod.tipo_subscripciones no existe` (or whichever table). Re-CREATE TABLE post-test.
  - **GREEN migration content**:
    ```python
    """0030_venta_suscripcion_optional.py — MIGRATION 0030 (NO-OP audit trail).
    Pre-flight 2026-09-15 confirmed:
    - All 5 [V] tables pre-exist (migration 0001).
    - All 5 [V] sync catalog entries pre-existing (DEC-VENTA-08 WITHDRAWN).
    - gestionar_clientes permission already seeded (migration 0001 line 3292 area).
    """
    from __future__ import annotations
    from alembic import op

    revision = "0030_venta_suscripcion_optional"
    down_revision = "0029_reimpresion_siembra_and_permiso_anular"
    branch_labels = None
    depends_on = None

    _LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"

    def upgrade() -> None:
        op.execute(_LOCK_TIMEOUT_SQL)
        # Op 0: pre-flight DO $$ (KD-7 F1.6..F1.11 pattern) — see design §14.2 + Appendix A.1
        op.execute("""DO $$
        DECLARE
            _n_tipo_subscripciones bigint; _n_clientes bigint; _n_vehiculos bigint;
            _n_subscripciones_cliente bigint; _n_subscripcion_vehiculos bigint;
        BEGIN
            SELECT count(*) INTO _n_tipo_subscripciones FROM pg_catalog.pg_class WHERE relname='tipo_subscripciones' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_clientes FROM pg_catalog.pg_class WHERE relname='clientes' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_vehiculos FROM pg_catalog.pg_class WHERE relname='vehiculos' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_subscripciones_cliente FROM pg_catalog.pg_class WHERE relname='subscripciones_cliente' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_subscripcion_vehiculos FROM pg_catalog.pg_class WHERE relname='subscripcion_vehiculos' AND relnamespace='prod'::regnamespace;
            IF _n_tipo_subscripciones IS NULL OR _n_tipo_subscripciones = 0 THEN RAISE EXCEPTION '0030_preflight_abort: tabla prod.tipo_subscripciones no existe.'; END IF;
            IF _n_clientes IS NULL OR _n_clientes = 0 THEN RAISE EXCEPTION '0030_preflight_abort: tabla prod.clientes no existe.'; END IF;
            IF _n_vehiculos IS NULL OR _n_vehiculos = 0 THEN RAISE EXCEPTION '0030_preflight_abort: tabla prod.vehiculos no existe.'; END IF;
            IF _n_subscripciones_cliente IS NULL OR _n_subscripciones_cliente = 0 THEN RAISE EXCEPTION '0030_preflight_abort: tabla prod.subscripciones_cliente no existe.'; END IF;
            IF _n_subscripcion_vehiculos IS NULL OR _n_subscripcion_vehiculos = 0 THEN RAISE EXCEPTION '0030_preflight_abort: tabla prod.subscripcion_vehiculos no existe.'; END IF;
            RAISE NOTICE '0030_preflight: 5/5 tablas OK';
        END;
        $$;""")

    def downgrade() -> None:
        # NO-OP: this migration added no DDL, no rows, no grants.
        pass
    ```
  - **Archivos**: `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py` (nuevo, ~30 LOC); `backend/tests/integration/test_migration_0030_noop.py` (nuevo, ~20 LOC, 2 tests). — **Validación**: T1 (round-trip) + T2 (abort) PASS.

- [x] **T-HU-F1.12-T7.4** [GREEN] — Run full regression sweep verifying F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11 tests still pass after F1.12 changes; verify all 5 CI gates remain green (no_regresion gate).
  - **Acciones**:
    1. Verify `backend/packages/parkos_core/src/parkos_core/repo/versioned.py::close_and_insert` still passes all its existing tests (F1.5 PR5-016).
    2. Verify F1.11 tests still PASS: `test_reimpresion_ticket_*`, `test_migration_0029_idempotent.py`, AST walks KD-TKT-01.
    3. Verify F1.10 tests still PASS: `test_factura_electronica_*`, `test_migration_0028_idempotent.py`, AST walks KD-FE-01.
    4. Verify F1.9 tests still PASS: `test_facturacion_factura.py`, `test_facturacion_factura_pagos.py`, `test_migration_0027_idempotent.py`, AST walks KD-FACT-01.
    5. Verify F1.8 tests still PASS: PL/pgSQL `calcular_cotizacion` + KD-1 FOR SHARE.
    6. Verify F1.7 tests still PASS: KD-FORZADO-01 AST walks + KD-S2 tenant scope.
    7. Verify F1.6 tests still PASS: KD-FORZADO-01 prefix contract + Idempotency-Key middleware (now used by F1.12 endpoint via DEC-IDEM-01 reuse).
    8. Verify F1.5 tests still PASS: MV pattern + `repo/workflow.append_transition` + `read_chain_tip`.
    9. Verify 5 CI gates verde (`factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.11`).

  **Commit suggestion**: `test(backend): HU-F1.12 — unit + e2e + MIGRATION 0030 idempotency + full regression sweep`.

  **Exit criteria T7**: T7.1..T7.4 verde; ~550 LOC cumulative (impl + tests); MIGRATION 0030 idempotent on upgrade/downgrade/re-upgrade cycle.

### Cluster T8 — Manual scenario walkthrough + final commit (apply-report + verify-report stubs)

- [x] **T-HU-F1.12-T8.1** [GREEN] — Author `prompts/HU-F1.12-apply.md` + `artifacts/HU-F1.12-apply-report.md` stubs (mirror F1.11 archive `prompts/00-ejecutor-fase-1.md` + `artifacts/HU-F1.11-apply-report.md` precedent — pre-populated with the 8-commit summary + per-cluster `Exit criteria` checkboxes + risk map R1..R12).
  - **Archivos**:
    - `openspec/changes/hu-f1-12-venta-suscripcion/prompts/HU-F1.12-apply.md` (nuevo, ~30 LOC) — the apply-phase prompt for `sdd-apply` to consume (mirror of F1.11 T1.11-apply.md).
    - `openspec/changes/hu-f1-12-venta-suscripcion/artifacts/HU-F1.12-apply-report.md` (nuevo, ~30 LOC) — apply-report stub with 8 cluster exit-criteria checkboxes.

- [x] **T-HU-F1.12-T8.2** [GREEN] — Author `openspec/changes/hu-f1-12-venta-suscripcion/artifacts/HU-F1.12-verify-report.md` stub (mirror F1.11 archive `artifacts/HU-F1.11-verify-report.md` precedent — pre-populated with REQ-OPS-083..090 + XR5 traceability matrix + the ~43-test matrix from design Appendix B as the verify-phase checklist).
  - **Archivo**: `openspec/changes/hu-f1-12-venta-suscripcion/artifacts/HU-F1.12-verify-report.md` (nuevo, ~30 LOC) — verify-report stub.

- [x] **T-HU-F1.12-T8.3** [GREEN] — Final commit consolidating all 8 clusters + apply-report + verify-report; verify the MIGRATION 0030 NO-OP round-trip + manual scenario walkthrough (cliente nuevo + 1 placa + plan mensual + cobrar_ahora=false + emitir_Fe=false) per design §9.10 happy path.
  - **Acción**: execute scenario walkthrough via curl/httpx against local `pg_engine` + Django/uvicorn; capture row counts in `prod.clientes` (1) + `prod.vehiculos` (1) + `prod.subscripciones_cliente` (1) + `prod.subscripcion_vehiculos` (1) post-commit.
  - **Validación**: full suite verde; 0 regresiones introducidas por F1.12; F1.5..F1.11 pre-existing failures documented and unchanged; 5 CI gates verde.

  **Commit suggestion**: `chore(openspec): HU-F1.12 — apply-report + verify-report stubs + manual scenario walkthrough`.

  **Exit criteria T8**: T8.1..T8.3 verde; ~620 LOC cumulative; F1.12 ready to ship as 1 PR to `origin/dev` with 8 atomic commits.

---

## Cross-cluster constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` on `prod.clientes` / `prod.vehiculos` / `prod.subscripciones_cliente` / `prod.subscripcion_vehiculos` outside the 9 helpers in `repo/venta_suscripcion.py` + the reused `repo/versioned.py::close_and_insert` — AST walks `tests/static/test_venta_handler_no_raw_dml.py` (T6.2) + `tests/static/test_venta_handler_no_update_on_v_tables.py` (T6.3) enforce via DEC-VENTA-05 + F1.5 PR5-016.
- NO multiple `await session.commit()` or `session.begin_nested()` or `SAVEPOINT` statements in the handler body — AST walk `tests/static/test_venta_handler_single_commit.py` (T6.1) enforces via KD-VENTA-01 single-commit invariant.
- NO raw `UPDATE prod.clientes` on user-meaningful fields (`nombre`, `apellido`, `telefono`, `email`, etc.) — the AST walks enforce. Only `vigente_hasta` MAY be UPDATEd by `VersionedBase` superclass for bi-temporal versioning (the existing `tests/static/test_no_raw_upsert_on_v_tables.py` from F1.5 PR5-016 covers `VersionedBase`).
- NO `Co-authored-by:` trailers AI en commits; conventional commits, neutral Spanish commit messages, neutral Spanish per-cluster rationale comments.
- NO SQLite in tests — `pg_engine` real via `testcontainers[postgres]` (F1.4/F1.5/F1.6/F1.7/F1.9/F1.10/F1.11 precedent).
- NO modification of `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate (matches F1.7/F1.9/F1.10/F1.11).
- NO modification of `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate cross-cutting.
- NO modification of `api/deps.py` nor `auth/tenancy.py` — KD-3 chain + errores tipados intactos.
- NO modification of `repo/event.py` — `event_helper_intact` CI gate (matches F1.7/F1.9/F1.10/F1.11).
- NO modification of `repo/versioned.py::close_and_insert` — reused verbatim (F1.5 PR5-016, V1 + V3 writers).
- NO modification of `repo/placa.py::detectar_tipo_vehiculo` + `FORMATO_AUTO`/`FORMATO_MOTO` regex — reused verbatim (F1.6, V3 + V5).
- NO modification of `repo/subscripcion_activa.py::resolve_active_subscription_for_exit` — reused verbatim (F1.7, V4 reverse-direction query).
- NO modification of `repo/factura.py::crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago` — reused verbatim (F1.9, V8 cobro sub-chain helpers).
- NO modification of `repo/factura_electronica.py::crear_factura_electronica_inicial` + `crear_envio_dian_inicial` — reused verbatim (F1.10, V8b FE sub-chain helpers).
- NO modification of `repo/resolucion_facturacion.py::assign_consecutivo` — reused verbatim (F1.10, V8b FE numbering).
- NO modification of `repo/idempotency.py::guard` + `store_response` — F1.6 middleware continues to handle the cache; F1.12 endpoint inherits via DEC-IDEM-01.
- NO modification of the existing factory mount at `api/v1/clientes.py` lines 42-126 — F1.12 mounts on top via `router.include_router(venta_suscripcion_router)` in DEC-VENTA-05, inherits `gestionar_clientes` permission gate.
- NO new sync catalog entries — `sync_entries_v.py` lines 133, 451, 483, 511, 525 already carry all 5 [V] entries with appropriate `direction`/`broadcast`/`hooks` settings (verified pre-apply, DEC-VENTA-08 WITHDRAWN).
- NO new triggers — existing `tipo_subscripciones_audit_columns` + `clientes_audit_columns` + `vehiculos_audit_columns` + `subscripciones_cliente_audit_columns` + `subscripcion_vehiculos_audit_columns` + `_set_vigente_inicial` + `_enqueue_sync` (migration 0001) cover the F1.12 INSERT paths.
- NO `valor_dia` / `monto_prorrateado` column on `prod.subscripciones_cliente` — A-09 prorrateo persisted in `factura_detalle.valor_unitario`/`subtotal` ONLY when `cobrar_ahora=true` (DEC-VENTA-03, plan.md line 460 explicit).
- Header `Cache-Control: no-store` on EVERY response (201 + 4xx + 5xx) of the endpoint (via `no_store_headers()` helper + `apply_no_store_header(response)` before return + `headers=no_store` param in `HTTPException` constructors) — DEC-VENTA-06 XR2 mirror from F1.11.
- Discriminators stable: `tenant_scope_violation` (403 operador cross-branch), `permission_denied` (403 no `gestionar_clientes`), `tipo_subscripcion_no_encontrado` (404 V2), `cliente_no_encontrado` (404 V1 when `uuid_cliente` missing), `idempotency_key_required` (400 DEC-IDEM-01), `idempotency_conflict` (409 DEC-IDEM-01), `tipo_subscripcion_no_vigente` (409 V2), `placa_formato_invalido` (422 V3), `tipo_vehiculo_invalido` (422 V3 catalog missing), `suscripcion_duplicada_placa` (422 V4), `tipo_vehiculo_incompatible` (422 V5), `cantidad_maxima_excedida` (422 V6), `plan_duracion_dias_invalido` (422 V7 edge), `nit_dv_invalido` (422 V1 NIT modulo 11), `iva_no_configurado` (500 V8 only when cobrar_ahora=true).
- Precedencia de errores: KD-3 (403 issuer) > V1 Pydantic (422) > idempotency middleware (400/409) > V2 plan lookup (404) > tenant scope (403) > V1 cliente lookup (404) > V3 per-placa (422) > V5 mismo_tipo (422) > V6 cantidad_maxima (422) > V4 placa_dup (422) > V7 prorrateo (422) > V9 INSERT > V8 cobro sub-chain (500) > V8b FE sub-chain (409) > Step 10 (single commit) > Step 11 (201 + Cache-Control).
- MIGRATION 0030 MUST be idempotent: pre-flight `DO $$` is read-only; `upgrade()` and `downgrade()` are empty after pre-flight (DEC-VENTA-08 + design §14.2 NO-OP audit trail).
- Per-commit ceiling: <800 LOC. Each cluster T1..T8 fits (T5 handler chain at ~120 LOC is the largest implementation block, well within). T2 + T3 + T4 may require mental split if schema bodies + repo helpers + RED tests exceed 800 — orchestrator decides per real diff at apply.
- Mensajes conventional commit; cuerpo técnico en neutral Spanish.

## Acceptance Gates

- TDD strict: RED first, GREEN minimum, REFACTOR last. Clusters T2..T5 explicitly note this discipline.
- ~31 tasks completed in order: T1.1..T1.3 → T2.1..T2.4 → T3.1..T3.5 → T4.1..T4.5 → T5.1..T5.4 → T6.1..T6.3 → T7.1..T7.4 → T8.1..T8.3.
- Conventional commits atómicos (8 commits en 1 PR):
  - commit 1 `feat(backend): HU-F1.12 — repo module skeleton + 7 typed exceptions + pre-flight verification` (~50 LOC);
  - commit 2 `feat(backend): HU-F1.12 — Pydantic schemas (VentaSuscripcionCreate + VentaSuscripcionResponse)` (~80 LOC);
  - commit 3 `feat(backend): HU-F1.12 — repo helpers part 1 (cliente lookup-or-create + vehiculo + plan FOR UPDATE)` (~80 LOC);
  - commit 4 `feat(backend): HU-F1.12 — repo helpers part 2 (V4 placa-dup + V5 mismo-tipo + V6 cantidad-max + V7 prorrateo)` (~80 LOC);
  - commit 5 `feat(backend): HU-F1.12 — POST /clientes/venta-suscripcion handler (10-step chain + KD-VENTA-01 single-commit + router mount)` (~120 LOC);
  - commit 6 `feat(static): HU-F1.12 — AST walks (KD-VENTA-01 single-commit + DEC-VENTA-05 no raw DML + no UPDATE on [V])` (~30 LOC);
  - commit 7 `test(backend): HU-F1.12 — unit + e2e + MIGRATION 0030 idempotency + full regression sweep` (~50 LOC);
  - commit 8 `chore(openspec): HU-F1.12 — apply-report + verify-report stubs + manual scenario walkthrough` (~60 LOC).
  - Without `Co-authored-by:`, without AI trailers.
- Tests run against real DB with `PARKOS_DOCKER_TEST=1`: 1 preflight (T1.1) + 1 module-import (T1.2) + 6 + 5 = 11 schema unit (T2.1 + T2.3) + 1 + 2 + 3 + 3 = 9 repo unit (T3.1 + T3.3 + T3.5 + T4.1 + T4.3 + T4.4) + 4 unit handler (T7.1 mandated by plan.md line 1047) + 1 e2e (T7.2) + 2 migration idempotency (T7.3) + 1 module-stub (T5.1) + 4 AST walks (T6.1 2 + T6.2 1 + T6.3 1) = **~33 tests across 7 files** (5 unit/integration test files + 1 e2e + 1 migration + 3 AST walks).
- ruff + mypy --strict clean on all new/modified files (1 NEW `repo/venta_suscripcion.py` + 1 MODIFIED `schemas/clientes.py` + 1 NEW `api/v1/clientes_venta.py` + 1 MODIFIED `api/v1/clientes.py` + 1 NEW migration + 7 NEW tests + 3 NEW AST walks).
- 5 CI gates green (matches F1.7/F1.9/F1.10/F1.11): `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.11`.
- 0 regressions introduced by F1.12; baseline F1.11 pre-existing failures documented and unchanged.
- REQ-OPS-083..090 + REQ-OPS-XR5 traceability verified: each REQ has ≥1 RED test that proves it (mapping in Appendix B of design.md + this file's per-task rationale).
- Architecture risks §12 (R1..R12) verified: R1 cross-domain atomicity → T5.4 Step 10 single commit + T6.1 AST walk verifies; R2 A-09 ZeroDivisionError → T4.5 ZeroDivisionError catch; R3 mismo_tipo_vehiculo → T4.2 validar helper raises 422 BEFORE INSERT; R4 placa-dup → T4.3 resolve_active_subscription_for_exit reuse; R5 idempotency-Key reuse → DEC-IDEM-01 already in place; R6 no-store → T7.1 unit test asserts header on 201/404/422; R7 sync catalog → DEC-VENTA-08 WITHDRAWN; R8 gestionar_clientes inherited → T5.4 router.include_router factory mount; R9 plan concurrency → T3.5 SELECT FOR UPDATE exclusive + T5.2 Step 2 lock; R10 advisory lock → T5.3 step 9 inside `crear_subscripcion_vehiculos_bulk`; R11 migration head-pointer → T7.3 pre-flight DO $$ block; R12 DEC-VENTA-04 divergence from F1.9 → T3.5 + design §11 DEC-VENTA-04 documented.

## Out of Scope Tasks

- B2B convenios corporativos (plan.md line 1055, Fase 2+): multiple vehicles per convenio, third-party billing, `clientes_b2b` table — explicitly out per plan.md note. `ClientesB2B` ORM model + schemas exist (`models/V/clientes_b2b.py`) but F1.12 does NOT touch them.
- Renovación de suscripción (renewal = close current + INSERT new version via `close_and_insert`): NOT in F1.12 scope. Renewal is a separate endpoint (future HU, Fase 9).
- Anulación de suscripción (close-only, no replacement): NOT in F1.12 scope.
- Cambio de plan mid-cycle (upgrade/downgrade): NOT in F1.12 scope.
- Cobro retroactivo (apply A-09 prorrateo at renewal time): NOT in F1.12 scope. A-09 applies ONLY to the initial sale.
- Multi-sucursal suscripción (one cliente + N sucursales with the same plan): NOT in F1.12 scope. F1.12 creates the subscription at ONE branch (the operator's `ctx.sucursal_uuid`).
- Frontend reconciliation for `clientes.py` factory mount: NOT in scope (Fase 8 frontend).
- Settlement with payment gateway (datafono, tarjeta): F1.9 already handles via `medio_pago='datafono'` + `referencia`. F1.12 just passes through.
- DIAN `resolucion_facturacion` resolution upgrade when range exhausted: F1.10 already raises `ConsecutivoRangeExhaustedError` which F1.12 passes through.
- Cross-branch placa-dup detection (cross-sucursal check): deferred to a future cross-branch consistency HU. F1.12 enforces branch-pinned `WHERE uuid_sucursal == :this_branch` only (R22 F1.7 reuse).
- `test_venta_e2e_inherits_gestionar_clientes_permission` (T-088-2 in design Appendix B): deferred to F1.13 or omitted (the factory mount already enforces the permission; covered by F1.5 `factory_intact` CI gate cross-cutting).
- PDF rendering of venta-suscripcion tiquete: HU-F8.x (Fase 8 frontend).
- Email/SMS notification of venta confirmation: Fase 4.

## Commit summary (8 expected atomic commits)

| # | Cluster | Commit message | Files | LOC est. |
|---|---|---|---|---|
| 1 | T1 | `feat(backend): HU-F1.12 — repo module skeleton + 7 typed exceptions + pre-flight verification` | 1 NEW repo skeleton + 1 NEW test | ~50 |
| 2 | T2 | `feat(backend): HU-F1.12 — Pydantic schemas (VentaSuscripcionCreate + VentaSuscripcionResponse)` | 1 MODIFIED schemas + 1 NEW test | ~80 |
| 3 | T3 | `feat(backend): HU-F1.12 — repo helpers part 1 (cliente lookup-or-create + vehiculo + plan FOR UPDATE)` | 1 MODIFIED repo + extended test file | ~80 |
| 4 | T4 | `feat(backend): HU-F1.12 — repo helpers part 2 (V4 placa-dup + V5 mismo-tipo + V6 cantidad-max + V7 prorrateo)` | 1 MODIFIED repo + extended test file | ~80 |
| 5 | T5 | `feat(backend): HU-F1.12 — POST /clientes/venta-suscripcion handler (10-step chain + KD-VENTA-01 single-commit + router mount)` | 1 NEW handler module + 1 MODIFIED router mount | ~120 |
| 6 | T6 | `feat(static): HU-F1.12 — AST walks (KD-VENTA-01 single-commit + DEC-VENTA-05 no raw DML + no UPDATE on [V])` | 3 NEW AST walk files | ~30 |
| 7 | T7 | `test(backend): HU-F1.12 — unit + e2e + MIGRATION 0030 idempotency + full regression sweep` | 1 NEW migration + 3 NEW test files | ~50 |
| 8 | T8 | `chore(openspec): HU-F1.12 — apply-report + verify-report stubs + manual scenario walkthrough` | 2 NEW artifacts + 1 NEW prompt | ~60 |

**Total**: 8 commits, ~550 LOC cumulative (impl + tests + migration + walkthrough), 1 PR to `origin/dev`. Net apply delta ~420 LOC production + ~265 LOC tests + ~30 LOC migration + ~30 LOC AST walks + ~60 LOC artifacts/prompts.

## Definition of Done (apply phase)

- [x] ~33 tests + 4 AST walks across 7 test files PASS via `uv run pytest backend/tests/unit/test_venta_suscripcion.py backend/tests/unit/test_venta_suscripcion_repo.py backend/tests/unit/test_venta_suscripcion_schemas.py backend/tests/integration/test_venta_suscripcion_e2e.py backend/tests/integration/test_venta_suscripcion_preflight.py backend/tests/integration/test_migration_0030_noop.py backend/tests/static/test_venta_handler_*.py -q`
- [x] MIGRATION 0030 applied + downgrade reverses cleanly via `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` (round-trip idempotent)
- [x] 1 handler (`POST /api/v1/clientes/venta-suscripcion`) implemented per design §10 (10-step chain)
- [x] `repo/venta_suscripcion.py` 9 helpers + 7 typed exceptions authored (DEC-VENTA-01..07)
- [x] `schemas/clientes.py` extended with `VentaSuscripcionCreate` + `VentaSuscripcionResponse` (DEC-VENTA-07)
- [x] KD-3 issuer chain `_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")` applied with `Cache-Control: no-store` on every response
- [x] KD-VENTA-01 single-commit invariant verified via AST walk on `venta_suscripcion`
- [x] DEC-VENTA-02 lock ordering verified (plan lock FIRST at Step 2 BEFORE any other lock)
- [x] DEC-VENTA-04 plan lock type (`SELECT FOR UPDATE` exclusive, NOT `FOR SHARE`) verified via AST walk comment
- [x] A-09 prorrateo persistence verified (`factura_detalle.valor_unitario`/`subtotal` when `cobrar_ahora=true` AND `fecha_inicio_cobertura.day > 15`)
- [x] Tenant scope post-V1 verified (operador- cross-branch → 403 `tenant_scope_violation`)
- [x] `Idempotency-Key` HTTP header supported (DEC-IDEM-01 reuse from F1.6/F1.9/F1.10/F1.11)
- [x] `pg_advisory_xact_lock(uuid_subscripcion_cliente)` enforced inside `crear_subscripcion_vehiculos_bulk` (REQ-OP-08) — F1.12 FIRST implements the lock the contract documents
- [x] All F1.5/F1.6/F1.7/F1.8/F1.9/F1.10/F1.11 tests still PASS (no_regresion gate)
- [x] ruff + mypy --strict clean on all 9 new/modified files
- [x] 5 CI gates verde (`factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.11`)
- [x] 0 regresiones introducidas; baseline F1.11 pre-existing failures documented + unchanged
- [x] REQ-OPS-083..090 + REQ-OPS-XR5 traceability verified via per-REQ RED tests
- [x] 8 atomic commits authored with conventional commit messages, neutral Spanish, NO `Co-authored-by:` trailers

## Next phase

`sdd-apply hu-f1-12-venta-suscripcion` — TDD-strict RED→GREEN→REFACTOR per cluster T1..T8. Orchestrator executes the 8 atomic commits in order, verifies each cluster's exit criteria, and routes to `sdd-verify` after all commits land.

## References

- `openspec/changes/hu-f1-12-venta-suscripcion/design.md` (16 sections + 2 appendices, 2026-09-15, ~1562 LOC) — full architecture + MIGRATION 0030 SQL + ~43 tests + 2 AST walks + 8 DECs + 2 KDs.
- `openspec/changes/hu-f1-12-venta-suscripcion/specs/operations/spec.md` (~485 LOC, 8 REQ-OPS-083..090 + REQ-OPS-XR5) — operational requirements.
- `openspec/changes/hu-f1-12-venta-suscripcion/proposal.md` (~485 LOC, 16 sections, DEC-VENTA-01..07 + DEC-VENTA-08 WITHDRAWN, KD-VENTA-01..02, R1 MEDIUM RESOLVED) — pre-design proposal.
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/tasks.md` (~860 LOC, 8 clusters T1..T8, 31 tasks, ~0.86 PR diff) — **canonical precedent** for F1.12 structure.
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/{proposal,design,specs/operations/spec.md,verify-report,archive-report}.md` — F1.11 full cycle precedent.
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/tasks.md` — F1.10 precedent (KD-FE-01 single-commit).
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/tasks.md` — F1.9 precedent (KD-FACT-01 single-commit + `crear_factura_*` helpers reused).
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/tasks.md` — F1.7 precedent (KD-S2 tenant scope post-V1, `resolve_active_subscription_for_exit` reuse).
- `openspec/changes/archive/2026-09-14-hu-f1-6-ingresos/tasks.md` — F1.6 precedent (DEC-IDEM-01 Idempotency-Key header + placa regex).
- `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/tasks.md` — F1.5 precedent (`repo/versioned.py::close_and_insert` + AST walk no-raw-UPSERT on [V]).
- `openspec/specs/operations/spec.md` lines 2517-3076 (F1.10 REQ-OPS-064..074 + XR1..XR3 + F1.11 REQ-OPS-075..080 + XR4) — target for REQ-OPS-083..090 + XR5 merge on archive.
- `plan.md` lines 1010-1054 — HU-F1.12 definition, 3 atomic tasks T1..T3, 260 LOC production budget.
- `plan.md` lines 1016, 1053 — scope decision "ampliación de producto" + A-09 prorrateo decay rule (`day > 15`).
- `plan.md` line 460 — A-09 prorrateo (no `monto_prorrateado` column on `subscripciones_cliente`).
- `plan.md` line 1047 — 4 tests mandated for `tests/unit/test_venta_suscripcion.py`.
- `modelo_datos_er.mmd` line 105 (`tipo_subscripciones`), 449 (`clientes`), 496 (`subscripciones_cliente`), 519 (`vehiculos`), 538 (`subscripcion_vehiculos`).
- `modelo_datos_er.mmd` lines 1138-1145 — FK relationships: `clientes → subscripciones_cliente`, `tipo_subscripciones → subscripciones_cliente`, `subscripciones_cliente → subccion_vehiculos`, `vehiculos → subccion_vehiculos`.
- `migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones`), 435-452 (`clientes`), 454-465 (`vehiculos`), 483-496 (`subscripciones_cliente`), 498-509 (`subscripcion_vehiculos`).
- `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head; pre-flight `DO $$` pattern reused for MIGRATION 0030).
- `sync/catalog/entries/sync_entries_v.py` lines 133-147 (`tipo_subscripciones`), 451-465 (`clientes`), 483-500 (`vehiculos`), 511-523 (`subscripciones_cliente`), 525-552 (`subscripcion_vehiculos`) — **all 5 [V] entries verified pre-existing 2026-09-15**.
- `models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py` — pre-existing ORM models (no change).
- `repo/factura.py` (F1.9 atomic 4-table cobro chain — `crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago`).
- `repo/factura_electronica.py` + `repo/resolucion_facturacion.py::assign_consecutivo` (F1.10 atomic 2-table FE chain).
- `repo/subscripcion_activa.py::resolve_active_subscription_for_exit` (F1.7, lines 93-141 — reused for V4 placa-dup detection).
- `repo/placa.py` (F1.6 `FORMATO_AUTO` + `FORMATO_MOTO` + `detectar_tipo_vehiculo` — reused for V3 + V5).
- `repo/versioned.py::close_and_insert` (lines 45-196 — bi-temporal writer for [V] tables).
- `repo/versioned.py::current_version` (lines 242-254 — cliente + vehiculo lookup by UUID).
- `repo/idempotency.py` — DEC-IDEM-01 reuse (F1.6).
- `api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()` (lines 18-31 — DEC-VENTA-06 reuse).
- `api/v1/facturacion.py` lines 216-380 — F1.9 canonical 12-step atomic create handler, shape verbatim for optional cobro sub-chain.
- `api/v1/workflows_reimpresion.py` — F1.11 dedicated-router + KD-3 + tenant scope + Idempotency-Key pattern (reference for outer handler envelope).
- `api/v1/clientes.py` lines 42-126 — `make_router` factory mount for the 5 [V] tables (F1.12 mounts on top via `router.include_router(venta_suscripcion_router)`).
- `schemas/clientes.py::ClientesCreate._validar_nit_dv` (lines 82-102 — F1.9 REQ-OPS-058 NIT validator reused).
- `schemas/common.py::_Base` (`extra='forbid'` — Layer 4 defense for `VentaSuscripcionCreate` + `VentaSuscripcionResponse`).
- `static/test_no_raw_upsert_on_v_tables.py` (F1.5 PR5-016 AST walk precedent — basis for T6.2 + T6.3).
- `auth/{jwt_issuer_guard,tenancy}.py` — KD-3 issuer chain + `TenantContext` derivation.
