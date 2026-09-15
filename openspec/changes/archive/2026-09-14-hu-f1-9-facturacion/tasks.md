# Tasks: hu-f1-9-facturacion

> **Change**: `hu-f1-9-facturacion`
> **Phase**: tasks (sdd-tasks) — checklist only, do NOT implement
> **HU**: HU-F1.9 — `POST /api/v1/facturacion/factura` (atomic 4-table insert: `prod.facturas` + `prod.factura_detalle` + `prod.factura_impuestos` + `prod.factura_pagos`) + `POST /api/v1/facturacion/factura-pagos` (voucher validation for datáfono) + helper `repo/nit_modulo11.py` (DIAN módulo 11) wired into Pydantic v2 validators at `ClientesCreate` (always) and `FacturaItemConDatosPropios` (when `fe_con_datos=true`). 330 LOC budget per `plan.md` línea 929.
> **Status**: READY — ~30 atomic tasks planned across 8 clusters (T1..T8). TDD-strict defense in depth (D-HU-F1.9-7 5 layers: KD-3 issuer chain → KD-FACT-02 FOR SHARE → partial unique index `one_factura_per_salida` → `IntegrityError` catch → 409 mapping).
> **Preflight (this session)**: `pace=auto`, `artifact_store=hybrid`, `delivery_strategy=auto-chain` (cached per F1.7 precedent), `review_budget_lines=400`, `commit_ceiling_loc=800`.
> **Branch topology**: rama única `feat/fase-1-prerequisites-backend` (HEAD `def754d`); un único PR directo a `origin/dev` (matches F1.5/F1.6/F1.7/F1.8 precedent). Commit split interno: 8 commits atómicos ≤800 LOC cada uno (one per cluster T1..T8).
> **TDD discipline note (cluster overview)**: every task follows **RED → GREEN → REFACTOR**. RED test is written first (must fail by construction with `ImportError`, `ValidationError`, or `AssertionError`); GREEN implementation makes the test pass minimally; REFACTOR cleans duplication. No GREEN-without-RED.
> **Inputs read**: `exploration.md` (16 sections, V1..V6 + KD-FACT-R3, 7 risks R1..R7, files-to-touch §16), `proposal.md` (D-HU-F1.9-1..12, DEC-FACT-01..09 + DEC-FACT-10..11 + KD-FACT-01..02 + KD-NIT-01..07, 10 OQ cerradas §11), `specs/operations/spec.md` (REQ-OPS-053..063 RFC 2119, 35 escenarios + REQ-OPS-XR1..XR3 cross-cutting), `design.md` (16 sections, 12-step handler skeleton §7, MIGRATION 0027 SQL body §8, repo skeleton §9, AST walks §11.4, 7 risks R1..R7).
> **Precedents mirrored**: F1.7 (REQ-OPS-042..052, KD-FORZADO-01 verbatim reuse, KD-7 pre-flight `DO $$` pattern, defense in depth 5-layer, AST walks for ordering gate + single-commit invariant, commits `c320d0f`+`aa2fc9b`+`f826e8c`), F1.8 (REQ-OPS-022..025, PL/pgSQL VOLATILE `calcular_cotizacion` + `FOR SHARE` lock continuity KD-1, commit `a3d0c39`), F1.6 (REQ-OPS-034..041, KD-FORZADO-01 prefix contract verbatim reuse, commit `2a2cbd2`), F1.5 (REQ-OPS-030..033, MV pattern + KD-7 pre-flight, commit `bb99e18`), F1.4 (REQ-OPS-017..021, bi-temporal predicate reusable in V1/V2, commit `467b4f0`), F1.3 (REQ-OPS-026..029, partial unique index pattern + AST walk, commit `ca3f9bf`).
> **Skills loaded**: `gentle-sdd-tasks` (paths injected via orchestrator).

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~1,640 across 1 PR (MIGRATION 0027 ~120 LOC + 3 NEW repo files ~330 LOC + 2 MODIFIED schemas ~90 LOC + 1 NEW handler ~150 LOC + 1 MODIFIED `api/v1/__init__.py` +1 line + 5 NEW test files ~1310 LOC + 2 AST walks ~160 LOC + 1 docstring drift fix ~1 LOC + 1 OpenAPI/frontend stub ~120 LOC) |
| Total tasks | ~30 (8 clusters: T1 schemas 6 tasks + T2 repo 9 tasks + T3 migration 9 tasks + T4 handler 6 tasks + T5 tests 13 tasks + T6 AST walks 4 tasks + T7 OpenAPI/frontend 4 tasks + T8 docstring drift 2 tasks) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Medium** — F1.9 is ~1.1x F1.7's LOC pero cohesivo (un único módulo nuevo `api/v1/facturacion.py`); 8-commit split interno (one per cluster T1..T8) mantiene cada commit bajo el techo `commitlint` de 800 LOC |
| Chained PRs recommended | No — un único PR (matches F1.7 precedent); defensa en profundidad se prueba in-place |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Un único PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 8 commits internos, uno por cluster T1..T8 (T1 ~90 LOC, T2 ~330 LOC, T3 ~120 LOC, T4 ~150 LOC, T5 ~1310 LOC tests, T6 ~160 LOC walks, T7 ~120 LOC stub, T8 ~1 LOC drift). |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesivo single-resource + 8-commit split mantiene budget risk Medium dentro del precedente F1.7 |

| Cluster | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|---------|-------|---------------|----------------|----------------|
| T1 Schemas Pydantic + NIT módulo 11 helper | T1.1..T1.6 | ~90 LOC (helper 50 + schema 30 + errores 10) | ~80 LOC (3 RED tests) | 170 |
| T2 Repo layer (factura + factura_detalle + NIT) | T2.1..T2.19 | ~330 LOC (9 helpers + 5 typed exceptions) | ~150 LOC (5 RED tests) | 650 |
| T3 MIGRATION 0027 (partial unique index + trigger + REVOKE) | T3.1..T3.9 | ~120 LOC (4 ops + downgrade) | ~150 LOC (3 RED tests) | 920 |
| T4 Handler / Router (`create_factura` + `create_factura_pagos`) | T4.1..T4.6 | ~150 LOC (2 handlers + deps) | ~150 LOC (3 RED tests) | 1,220 |
| T5 Tests + DB integration | T5.1..T5.13 | — | ~1310 LOC (5 files, 16 tests) | 2,530 |
| T6 AST walks (single-commit + step-order) | T6.1..T6.4 | — | ~160 LOC (2 walks) | 2,690 |
| T7 OpenAPI + frontend router stub | T7.1..T7.4 | ~120 LOC (openapi yaml + router stub) | ~40 LOC (2 RED tests) | 2,850 |
| T8 Docstring drift fix (factura_pagos.py lines 9-18) | T8.1..T8.2 | ~1 LOC | ~10 LOC (1 RED test) | 2,861 |
| **Total** | **~30** | **~810 LOC impl** | **~2,050 LOC tests** | **~2,860 LOC cumulative workload (apply deltas ~800 LOC net)** |

> Tope por commit: <800 LOC. Cada cluster T1..T8 cabe en ≤800 LOC net (T1 ~170, T2 ~330, T3 ~270, T4 ~300, T5 ~1310, T6 ~160, T7 ~160, T8 ~11). T5 (tests) requiere split en 2 sub-commits si excede 800 — orquestador decide según diff real al apply.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| T1 | Schemas Pydantic v2 + NIT módulo 11 helper | `feat/fase-1-prerequisites-backend` → `origin/dev` (commit 1) | `uv run pytest backend/tests/unit/test_validar_nit_modulo11.py backend/tests/unit/test_facturacion_schemas.py -q` | unit tests sin DB; pure Pydantic + pure helper | Delete `repo/nit_modulo11.py` + revert schema extensions |
| T2 | Repo helpers (`factura.py` + `factura_detalle.py`) | commit 2 | `uv run pytest backend/tests/unit/test_repo_factura.py -q` | unit tests con `pg_engine` mock (no `PARKOS_DOCKER_TEST`); pure Python validation paths | Delete 2 new repo files; no DB impact |
| T3 | MIGRATION 0027 (4 ops) | commit 3 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0027_idempotent.py -q` | `pg_engine` real (testcontainers precedent F1.4); sembrar fixtures via SQL directo; asserts sobre `pg_indexes`, `pg_trigger` | `alembic downgrade -1` (Op 3 reverse + Op 2 reverse) |
| T4 | Handler + router (2 endpoints) | commit 4 | `uv run pytest backend/tests/unit/test_facturacion_factura.py backend/tests/unit/test_facturacion_factura_pagos.py -q` | `httpx.AsyncClient + ASGITransport(app)` + JWT `cajero-` fixture; real `pg_engine` con `PARKOS_DOCKER_TEST=1` | Revert handler addition + remove `r.include_router(facturacion.router)` |
| T5 | Tests + DB integration | commit 5 | `uv run pytest backend/tests/unit backend/tests/integration -q` | full suite verde; F1.5/F1.6/F1.7/F1.8 sin regresión | Remove new test files |
| T6 | AST walks (single-commit + step-order) | commit 6 | `uv run pytest backend/tests/static/ -q` | pure AST parsing; no DB | Remove 2 walk files |
| T7 | OpenAPI + frontend router stub | commit 7 | `uv run pytest backend/tests/unit/test_openapi_facturacion.py backend/tests/unit/test_frontend_router_stub.py -q` | pure import + spec parse; no DB | Delete `apps/facturacion/router.py` + `apps/facturacion/openapi.yaml` |
| T8 | Docstring drift fix | commit 8 | `uv run pytest backend/tests/static/test_factura_pagos_docstring_no_drift.py -q` | pure AST + regex; no DB | Revert 1-line edit on `models/A/factura_pagos.py` |

## Tareas

### Cluster T1 — Schemas Pydantic + NIT módulo 11 helper (~80 LOC impl + ~80 LOC tests)

- [x] **T-HU-F1.9-T1.1** [RED] — Write failing test for `repo/nit_modulo11.py::validar_nit_modulo11` with DIAN reference case `800.123.456-7` → DV=7.
  - **Tests** (pure helper, sin DB):
    - T1: `test_dian_reference_800_123_456_7_passes` — `validar_nit_modulo11("800.123.456-7", "7") is True`; `validar_nit_modulo11("800.123.456-7", "8") is False`; `dv_esperado("800.123.456") == 7` (Variant A discriminator); `MOD11_WEIGHTS == (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)`.
  - **Patrón F1.7**: pure Python helper test, sin HTTP, sin DB.
  - **Acción**: importar `validar_nit_modulo11`, `dv_esperado`, `MOD11_WEIGHTS` from `parkos_core.repo.nit_modulo11` (falla con `ImportError`); usar `assert` literals. — **Archivo**: `backend/tests/unit/test_validar_nit_modulo11.py` (nuevo, ~30 LOC, 1 test). — **Validación**: `ImportError: cannot import name 'validar_nit_modulo11' from 'parkos_core.repo.nit_modulo11' (or module does not exist)`.

- [x] **T-HU-F1.9-T1.2** [GREEN] — Create `repo/nit_modulo11.py` (~50 LOC) with `MOD11_WEIGHTS`, `dv_esperado`, `validar_nit_modulo11`, `_normalize_nit`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/nit_modulo11.py` (nuevo).
  - **Contenido**: `MOD11_WEIGHTS: tuple[int, ...] = (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)` (right-to-left, recycled cyclically si NIT >15 digits); `_NON_DIGIT_RE = re.compile(r"\D+")`; `_normalize_nit(nit: str) -> str` (strip non-digits + lstrip("0") OR "0"); `dv_esperado(nit: str) -> int` (right-to-left weighted sum + `sum % 11` — Variant A canónica per DIAN Resolución 000175 de 2021); `validar_nit_modulo11(nit: str, dv: str | int) -> bool` (cast dv → int + return `dv_int == dv_esperado(nit)`; catches `ValueError`, `TypeError` returning False).
  - **Acción**: `from __future__ import annotations`; imports stdlib `re` only; `__all__ = ["MOD11_WEIGHTS", "dv_esperado", "validar_nit_modulo11"]`; docstring REQ-OPS-058 + DEC-FACT-09 + DIAN Resolución 000175 de 2021 reference. — **Validación**: T1 test PASS; `from parkos_core.repo.nit_modulo11 import validar_nit_modulo11; assert validar_nit_modulo11("800.123.456-7", "7") is True`.

- [x] **T-HU-F1.9-T1.3** [RED] — Write failing tests for `FacturaItemConDatosPropios` Pydantic v2 `@field_validator("numero_identificacion")` invoking `validar_nit_modulo11`.
  - **Tests** (pure Pydantic validation, sin DB):
    - T1: `test_factura_datos_cliente_rechaza_nit_dv_invalido` — `FacturaItemConDatosPropios.model_validate({tipo_identificador:"NIT", numero_identificacion:"800.123.456", dv:"5", nombre:"X", apellido:"Y"})` raises `pydantic.ValidationError` with body containing `DV inválido: recibido=5, esperado=7`.
    - T2: `test_factura_datos_cliente_acepta_nit_dv_valido` — DV=7 → validation succeeds.
    - T3: `test_factura_datos_cliente_acepta_cc_sin_dv` — `tipo_identificador="CC"` sin DV → validation succeeds (módulo 11 SKIPPED).
  - **Patrón F1.7**: pure Pydantic validation tests, sin HTTP, sin DB.
  - **Acción**: importar `FacturaItemConDatosPropios` from `parkos_core.schemas.facturacion` (falla con `ImportError`); usar `pytest.raises(ValidationError)`. — **Archivo**: `backend/tests/unit/test_facturacion_schemas.py` (nuevo, ~40 LOC, 3 tests). — **Validación**: `ImportError: cannot import name 'FacturaItemConDatosPropios' from 'parkos_core.schemas.facturacion'`.

- [x] **T-HU-F1.9-T1.4** [GREEN] — Extend `schemas/clientes.py` (+~10 LOC) with Pydantic v2 `@field_validator("numero_identificacion")` calling `validar_nit_modulo11` when `tipo_identificador='NIT'`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py` (modificado, append post-F1.5 block).
  - **Contenido**: extend `ClientesCreate` schema with `@field_validator("numero_identificacion")` que invoca `validar_nit_modulo11(v, info.data.get("dv"))` cuando `info.data.get("tipo_identificador") == "NIT"`; raise `ValueError("DV inválido: recibido={dv}, esperado={expected}")` on mismatch.
  - **Acción**: append `@field_validator` decorator; imports `validar_nit_modulo11`, `dv_esperado` from `parkos_core.repo.nit_modulo11`; `model_config = ConfigDict(extra="forbid")` (heredado de `_Base`). — **Validación**: `ClientesCreate.model_validate({tipo_identificador:"NIT", numero_identificacion:"800.123.456-7", dv:"7", nombre:"X", apellido:"Y"})` succeeds; `dv:"5"` raises `ValidationError`.

- [x] **T-HU-F1.9-T1.5** [RED] — Write failing tests for `FacturaCreate` Pydantic v2 with `extra='forbid'`, `min_length=1` items, `Literal` medio_pago, voucher_requerido cross-field.
  - **Tests** (pure Pydantic validation, sin DB):
    - T1: `test_factura_create_rechaza_extra_fields` — `FacturaCreate.model_validate({...payload..., uuid_cliente:"..."})` raises `ValidationError` (extra='forbid' rejects DEC-FACT-06 client injection).
    - T2: `test_factura_create_rechaza_items_vacio` — `items=[]` raises `ValidationError` (Field min_length=1).
    - T3: `test_factura_create_acepta_medio_pago_literal_valido` — `medio_pago="efectivo"` succeeds.
    - T4: `test_factura_create_rechaza_medio_pago_literal_invalido` — `medio_pago="efectivoUSD"` raises `ValidationError` (Literal discriminator REQ-OPS-053 + DEC-FACT-07).
    - T5: `test_factura_pago_adicional_voucher_requerido_datafono` — `FacturaPagoAdicionalCreate.model_validate({medio_pago:"datafono", referencia:"", valor:5000, uuid_factura:fake})` raises `ValidationError` (cross-field validator).
  - **Patrón F1.7**: pure Pydantic validation tests, sin HTTP, sin DB.
  - **Acción**: importar `FacturaCreate`, `FacturaItemCreate`, `FacturaPagoAdicionalCreate` from `parkos_core.schemas.facturacion` (falla con `ImportError`). — **Archivo**: `backend/tests/unit/test_facturacion_schemas.py` (mismo archivo, +40 LOC, 5 tests). — **Validación**: `ImportError: cannot import name 'FacturaCreate' from 'parkos_core.schemas.facturacion'`.

- [x] **T-HU-F1.9-T1.6** [GREEN] — Author `schemas/facturacion.py` (+~80 LOC) with `FacturaItemConDatosPropios`, `FacturaItemCreate`, `FacturaCreate`, `FacturaItemRead`, `FacturaRead`, `FacturaPagoAdicionalCreate`, `FacturaPagoRead`, 4 typed errors.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (modificado, append post-F1.5/F1.6/F1.7 block).
  - **Contenido**:
    - `class FacturaItemConDatosPropios(_Base)`: `tipo_identificador: Literal["NIT","CC","CE","pasaporte"]`; `numero_identificacion: Annotated[str, StringConstraints(min_length=5, max_length=20)]`; `dv: Annotated[str, StringConstraints(min_length=1, max_length=2)] | None = None`; `nombre: Annotated[str, StringConstraints(min_length=1, max_length=120)]`; `apellido: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None`; `email: Annotated[str, StringConstraints(min_length=5, max_length=120)] | None = None`; `telefono: Annotated[str, StringConstraints(min_length=7, max_length=20)] | None = None`; `@field_validator("numero_identificacion")` calling `validar_nit_modulo11` when `tipo_identificador="NIT"`.
    - `class FacturaItemCreate(_Base)`: `tipo: Literal["servicio","producto"]`; `concepto: Annotated[str, StringConstraints(min_length=1, max_length=255)]`; `cantidad: int = Field(gt=0, le=999)`; `valor_unitario: Decimal = Field(ge=Decimal("0"), le=Decimal("999999999.9999"))`; `uuid_tarifa_sucursal: uuid_lib.UUID | None = None`.
    - `class FacturaCreate(_Base)`: `uuid_salida: uuid_lib.UUID`; `items: list[FacturaItemCreate] = Field(min_length=1, max_length=50)`; `subtotal: Decimal`; `total: Decimal`; `medio_pago: Literal["efectivo","tarjeta","transferencia","datafono","mixto"]`; `referencia: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None`; `fe_con_datos: bool = False`; `fe_datos_cliente: FacturaItemConDatosPropios | None = None`.
    - `class FacturaItemRead(_Base)`: `uuid`, `tipo`, `concepto`, `cantidad`, `valor_unitario`, `subtotal`.
    - `class FacturaRead(_Base)`: `uuid`, `created_at`, `uuid_sucursal`, `uuid_ingreso | None`, `uuid_salida | None`, `subtotal`, `descuento`, `total`, `uuid_cliente | None` (DEC-FACT-06 derivado), `items: list[FacturaItemRead]`, `estado: Literal["emitida","pagada","anulada"]`.
    - `class FacturaPagoAdicionalCreate(_Base)`: `uuid_factura`, `medio_pago: Literal[...]`, `valor: Decimal = Field(gt=Decimal("0"))`, `referencia | None`, `uuid_sesion | None`.
    - `class FacturaPagoRead(_Base)`: `uuid`, `uuid_factura`, `medio_pago`, `valor`, `referencia | None`, `timestamp_evento`.
    - `class NitInvalidoErrorSchema(_Base)`: `error: Literal["nit_invalido"]`, `dv_esperado: int`, `dv_recibido: str`.
    - `class ClienteNoEncontradoErrorSchema(_Base)`: `error: Literal["cliente_no_encontrado"]`, `numero_identificacion: str`.
    - `class DetalleInvalidoErrorSchema(_Base)`: `error: Literal["detalle_invalido"]`, `min_items: int`.
    - `class TotalNoCoherenteErrorSchema(_Base)`: `error: Literal["total_no_coherente"]`, `total_recibido: str`, `total_calculado: str`, `diferencia: str`.
  - **Acción**: append all classes + update `__all__`; imports `from pydantic import Field, StringConstraints, field_validator`; docstring REQ-OPS-053..063 + DEC-FACT-06/07/08 + D-HU-F1.9-19. — **Validación**: T1.3 + T1.5 8 tests PASS; `FacturaCreate.model_validate({"uuid_salida": fake, "items": [], "subtotal": 0, "total": 0, "medio_pago": "efectivo"})` raises `ValidationError` on min_length=1.

  **Commit suggestion**: `feat(backend): HU-F1.9 — schemas Pydantic + NIT módulo 11 helper`.

  **Exit criteria T1**: T1.1 RED; T1.2 GREEN; T1.3 RED; T1.4 GREEN; T1.5 RED; T1.6 GREEN; ~170 LOC cumulative.

### Cluster T2 — Repo layer (~330 LOC impl + ~150 LOC tests)

- [x] **T-HU-F1.9-T2.1** [RED] — Write failing tests for `repo/factura.py::buscar_salida_facturable` (returns `Salidas | None`).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`, mapean design §9 File 1):
    - T1: `test_buscar_salida_facturable_existente_sin_factura_previa` — seed `prod.salidas(X, uuid_ingreso=I)` with no prior `prod.facturas` referencing X; `buscar_salida_facturable(session, uuid_salida=X)` returns `Salidas` instance.
    - T2: `test_buscar_salida_facturable_inexistente` — sin seed; `buscar_salida_facturable(session, uuid_salida=DUMMY)` returns `None`.
    - T3: `test_buscar_salida_facturable_ya_facturada` — seed `prod.salidas(X)` + `prod.facturas(X)` (uuid_salida=X); `buscar_salida_facturable` returns `None` (DEC-FACT-01 unified discriminator).
  - **Patrón F1.7**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; sembrar via SQL directo al engine.
  - **Acción**: importar `buscar_salida_facturable` from `parkos_core.repo.factura` (falla con `ImportError`); usar `pytest_asyncio.fixture`; asserts via `await session.get(Salidas, X)`. — **Archivo**: `backend/tests/integration/test_repo_factura.py` (nuevo, ~80 LOC, 3 tests). — **Validación**: `ImportError: cannot import name 'buscar_salida_facturable' from 'parkos_core.repo.factura' (or module does not exist)`.

- [x] **T-HU-F1.9-T2.2** [GREEN] — Implement `buscar_salida_facturable` (~25 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (nuevo, base file).
  - **Contenido**: `async def buscar_salida_facturable(session, *, uuid_salida) -> Any | None` — V1 SELECT con `await session.get(Salidas, uuid_salida)` (fast path PK); if None → return None; then V1 EXISTS check via `await session.execute(text("SELECT 1 FROM prod.facturas WHERE uuid_salida = :uuid_salida AND uuid_salida IS NOT NULL LIMIT 1"), {"uuid_salida": str(uuid_salida)})`; if exists → return None (already facturada, DEC-FACT-01 unified discriminator); else return salida_row.
  - **Acción**: local import `from ..models.A.salidas import Salidas` para evitar cycle; imports `text`, `AsyncSession`, `uuid_lib`; docstring REQ-OPS-054 + DEC-FACT-01. — **Validación**: T2.1 3 tests PASS.

- [x] **T-HU-F1.9-T2.3** [RED] — Write failing tests for `repo/factura.py::buscar_o_crear_cliente_por_nit` (upsert pattern, returns `Clientes | None`).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_buscar_o_crear_cliente_por_nit_existente` — seed `prod.clientes(N, tipo='NIT', estado='activo', vigente_hasta=NULL)`; `buscar_o_crear_cliente_por_nit(session, numero_identificacion=N, datos=FacturaItemConDatosPropios(...))` returns `Clientes` instance.
    - T2: `test_buscar_o_crear_cliente_por_nit_inexistente_retorna_none` — sin seed; returns `None` (NO auto-create per REQ-OPS-055).
    - T3: `test_buscar_o_crear_cliente_por_nit_inactivo_excluido` — seed with `estado='inactivo'`; returns `None` (vigente + activo predicate).
  - **Patrón F1.7**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`.
  - **Acción**: importar `buscar_o_crear_cliente_por_nit` from `parkos_core.repo.factura` (falla con `ImportError`); asserts via `await session.get(Clientes, N)`. — **Archivo**: `backend/tests/integration/test_repo_factura.py` (mismo archivo, +30 LOC, 3 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.9-T2.4** [GREEN] — Implement `buscar_o_crear_cliente_por_nit` (~40 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (mismo file, append).
  - **Contenido**: `async def buscar_o_crear_cliente_por_nit(session, *, numero_identificacion: str, datos: FacturaItemConDatosPropios) -> Clientes | None` — V2 SELECT con `stmt = select(Clientes).where(Clientes.tipo_identificador == datos.tipo_identificador, Clientes.numero_identificacion == numero_identificacion, Clientes.vigente_hasta.is_(None), Clientes.estado == "activo")`; returns `scalar_one_or_none()`.
  - **Acción**: imports `from ..models.V.clientes import Clientes`, `from sqlalchemy import select`; docstring REQ-OPS-055. — **Validación**: T2.3 3 tests PASS.

- [x] **T-HU-F1.9-T2.5** [RED] — Write failing tests for `repo/factura.py::validar_items` (assert `len(items) >= 1`, `cantidad > 0`, `valor_unitario >= 0`).
  - **Tests** (pure Python, sin DB):
    - T1: `test_validar_items_rechaza_lista_vacia` — `validar_items([])` returns `[]` (handler raises 422 detalle_invalido).
    - T2: `test_validar_items_acepta_items_validos` — items con `cantidad=1, valor_unitario=5000` passes through unchanged.
  - **Patrón F1.7**: pure helper tests.
  - **Acción**: importar `validar_items` from `parkos_core.repo.factura` (falla con `ImportError`). — **Archivo**: `backend/tests/unit/test_repo_factura_helpers.py` (nuevo, ~25 LOC, 2 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.9-T2.6** [GREEN] — Implement `validar_items` (~25 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (mismo file).
  - **Contenido**: `def validar_items(items: list[FacturaItemCreate]) -> list[FacturaItemCreate]` — V4 defense-in-depth re-check; if `not items` returns `[]`; else returns `items` (Pydantic already enforces min_length=1, gt(0), ge(0), Literal[tipo]).
  - **Acción**: pure function, no session; docstring REQ-OPS-057 + DEC-FACT-04 (Fase 4 deferred retencion). — **Validación**: T2.5 2 tests PASS.

- [x] **T-HU-F1.9-T2.7** [RED] — Write failing tests for `repo/factura.py::lock_tarifas_sucursal_para_items` (KD-FACT-02 SELECT FOR SHARE per-row, idempotent on dedupe by uuid_tarifa_sucursal).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_lock_tarifas_sucursal_per_row_with_for_share` — seed 2 `prod.tarifas_sucursal` rows (T1, T2); items reference T1+T2; `lock_tarifas_sucursal_para_items(session, items)` acquires locks (verify via `pg_locks` query: 2 entries in `prod.tarifas_sucursal`).
    - T2: `test_lock_tarifas_sucursal_no_op_on_items_without_tarifa_ref` — items con `uuid_tarifa_sucursal=None`; lock function returns without acquiring locks.
    - T3: `test_lock_tarifas_sucursal_dedup_duplicate_uuids` — items reference same uuid 3x; lock function dedupes (1 lock acquired, not 3).
  - **Patrón F1.8**: `pg_engine` real; assert via `pg_locks`.
  - **Acción**: importar `lock_tarifas_sucursal_para_items` from `parkos_core.repo.factura` (falla con `ImportError`). — **Archivo**: `backend/tests/integration/test_repo_factura.py` (mismo file, +30 LOC, 3 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.9-T2.8** [GREEN] — Implement `lock_tarifas_sucursal_para_items` (~35 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (mismo file).
  - **Contenido**: `async def lock_tarifas_sucursal_para_items(session, *, items: list[FacturaItemCreate]) -> None` — KD-FACT-02 dedup `tarifs_uuids = {item.uuid_tarifa_sucursal for item in items if item.uuid_tarifa_sucursal is not None}`; if empty → return; SELECT `select(TarifasSucursal).where(TarifasSucursal.uuid.in_(tarifs_uuids)).with_for_update(read=True)` (psycopg2/asyncpg FOR SHARE); materialize via `list(result.scalars())`; lock held until caller's `session.commit()`.
  - **Acción**: imports `from ..models.V.tarifas_sucursal import TarifasSucursal`; docstring REQ-OPS-061 + KD-FACT-02 + DEC-FACT-02. — **Validación**: T2.7 3 tests PASS; `pg_locks` shows per-row FOR SHARE.

- [x] **T-HU-F1.9-T2.9** [RED] — Write failing tests for `repo/factura.py::compute_total` (assert ±0.01 COP tolerance on subtotal + IVA - retencion).
  - **Tests** (pure Python, sin DB):
    - T1: `test_compute_total_subtotal_iva_sin_retencion` — items=[{cantidad:1, valor_unitario:5000}], iva=Decimal("0.19"), retencion=Decimal("0") → returns `Decimal("5950.00")` (5000 + 950).
    - T2: `test_compute_total_zero_items` — items=[] → returns `Decimal("0.00")` (no IVA computed).
    - T3: `test_compute_total_quantize_precision` — items=[{cantidad:3, valor_unitario:1234.56}], iva=Decimal("0.08") → returns `Decimal("3997.69")` (3*1234.56=3703.68 + 296.2944 → quantize 0.01 → 3999.97). Tolerance: verify Decimal quantize to "0.01" exactly.
  - **Patrón F1.7**: pure helper tests.
  - **Acción**: importar `compute_total` from `parkos_core.repo.factura` (falla con `ImportError`). — **Archivo**: `backend/tests/unit/test_repo_factura_helpers.py` (mismo file, +25 LOC, 3 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.9-T2.10** [GREEN] — Implement `compute_total` (~25 LOC) with retencion=Decimal("0") placeholder (DEC-FACT-04 Fase 4 deferral).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (mismo file).
  - **Contenido**: `def compute_total(*, items: list[FacturaItemCreate], iva: Decimal, retencion: Decimal = Decimal("0")) -> Decimal` — V6 server-side recompute: `subtotal_items = sum((item.cantidad * item.valor_unitario for item in items), Decimal("0"))`; `iva_monto = (subtotal_items * iva).quantize(Decimal("0.01"))`; `total = subtotal_items + iva_monto - retencion`; return `total.quantize(Decimal("0.01"))`.
  - **Acción**: pure function, no session; docstring REQ-OPS-059 + DEC-FACT-04 (MVP sin retención). — **Validación**: T2.9 3 tests PASS.

- [x] **T-HU-F1.9-T2.11** [RED] — Write failing tests for `repo/factura.py::crear_factura_evento` (INSERT prod.facturas with composite PK enforced).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_crear_factura_evento_inserta_una_fila` — `crear_factura_evento(session, actor_uuid=A, new_attrs={uuid_sucursal:S, uuid_ingreso:I, uuid_salida:Sal, subtotal:5000, descuento:0, total:5950})` returns `Facturas` with `uuid != None`, `created_at != None`.
    - T2: `test_crear_factura_evento_duplicada_uuid_salida_raise_factura_duplicada_error` — seed pre-existing `prod.facturas(X, uuid_salida=Sal)`; second call with same `uuid_salida=Sal` raises `FacturaDuplicadaError` (partial unique index `one_factura_per_salida` from MIGRATION 0027 Op 2; post-0027 only).
  - **Patrón F1.7**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; partial unique index enforcement post-0027.
  - **Acción**: importar `crear_factura_evento`, `FacturaDuplicadaError` from `parkos_core.repo.factura` (falla con `ImportError`); use `pytest.raises(FacturaDuplicadaError)`. — **Archivo**: `backend/tests/integration/test_repo_factura.py` (mismo file, +30 LOC, 2 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.9-T2.12** [GREEN] — Implement `crear_factura_evento` (~40 LOC) + `FacturaDuplicadaError`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (mismo file).
  - **Contenido**: `class FacturaDuplicadaError(Exception)` — 409 discriminator; `async def crear_factura_evento(session, *, actor_uuid, new_attrs) -> Facturas` — Step 9 INSERT [L-E]: `now = datetime.now(UTC).replace(tzinfo=None)`; `new_row = Facturas(**new_attrs, created_at=now, created_by=actor_uuid)`; `session.add(new_row)`; `try: await session.flush() except IntegrityError as err: if "one_factura_per_salida" in str(err.orig): raise FacturaDuplicadaError() from err; raise`; return new_row.
  - **Acción**: imports `from datetime import UTC, datetime`, `from sqlalchemy.exc import IntegrityError`, `from ..models.L_E.facturas import Facturas`; docstring REQ-OPS-060 + DEC-FACT-01 (amended: F1.9 only INSERTs). — **Validación**: T2.11 2 tests PASS.

- [x] **T-HU-F1.9-T2.13** [RED] — Write failing tests for `repo/factura_detalle.py::crear_factura_detalle_bulk` (bulk_insert_mappings over N rows).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_crear_factura_detalle_bulk_inserta_n_filas` — seed `prod.facturas(F)`; 3 items; `crear_factura_detalle_bulk(session, uuid_factura=F, items)` returns list of 3 `FacturaDetalle` rows; verify `prod.factura_detalle` has 3 rows for F.
    - T2: `test_crear_factura_detalle_bulk_empty_returns_empty` — items=[] → returns `[]`, no rows inserted.
  - **Patrón F1.7**: `pg_engine` real.
  - **Acción**: importar `crear_factura_detalle_bulk` from `parkos_core.repo.factura_detalle` (falla con `ImportError`). — **Archivo**: `backend/tests/integration/test_repo_factura_detalle.py` (nuevo, ~25 LOC, 2 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.9-T2.14** [GREEN] — Implement `crear_factura_detalle_bulk` in `repo/factura_detalle.py` (~30 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura_detalle.py` (nuevo).
  - **Contenido**: `async def crear_factura_detalle_bulk(session, *, uuid_factura, items: Sequence[FacturaItemCreate]) -> list[FacturaDetalle]` — bulk INSERT via `session.add_all([FacturaDetalle(uuid_factura=uuid_factura, tipo=item.tipo, concepto=item.concepto, cantidad=item.cantidad, valor_unitario=item.valor_unitario, subtotal=(item.cantidad * item.valor_unitario).quantize(Decimal("0.01")), uuid_tarifa_sucursal=item.uuid_tarifa_sucursal, fecha_retencion_hasta=frh) for item in items])`; `frh = date.today() + timedelta(days=5*365)` (DIAN 5-year retention); `await session.flush()`; return new_rows.
  - **Acción**: imports `from datetime import date, timedelta`, `from decimal import Decimal`, `from ..models.A.factura_detalle import FacturaDetalle`; `__all__ = ["crear_factura_detalle_bulk"]`; docstring REQ-OPS-053 + DEC-FACT-01. — **Validación**: T2.13 2 tests PASS.

- [x] **T-HU-F1.9-T2.15** [RED] — Write failing tests for `repo/factura.py::crear_factura_impuesto_iva` (INSERT 1 row IVA snapshot).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_crear_factura_impuesto_iva_inserta_snapshot` — seed `prod.impuestos.IVA(porcentaje=0.19)`, `prod.facturas(F)`; `crear_factura_impuesto_iva(session, uuid_factura=F, base=5000)` returns `FacturaImpuestos` with `valor=950`, `porcentaje_aplicado=0.19`.
    - T2: `test_crear_factura_impuesto_iva_sin_iva_row_raise` — `DELETE FROM prod.impuestos WHERE codigo='IVA'`; `crear_factura_impuesto_iva` raises `NoResultFound` (or `MultipleResultsFound`).
  - **Patrón F1.7**: `pg_engine` real; F1.7 KD-IVA resolver test pattern reused.
  - **Acción**: importar `crear_factura_impuesto_iva` from `parkos_core.repo.factura` (falla con `ImportError`). — **Archivo**: `backend/tests/integration/test_repo_factura.py` (mismo file, +25 LOC, 2 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.9-T2.16** [GREEN] — Implement `crear_factura_impuesto_iva` (~25 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (mismo file).
  - **Contenido**: `async def crear_factura_impuesto_iva(session, *, uuid_factura, base: Decimal) -> FacturaImpuestos` — Step 10b: read `iva_row = (await session.execute(select(Impuestos).where(Impuestos.codigo == "IVA", Impuestos.vigente_hasta.is_(None), Impuestos.estado == "activo"))).scalar_one()`; `iva_monto = (base * iva_row.porcentaje).quantize(Decimal("0.01"))`; `new_row = FacturaImpuestos(uuid_factura=uuid_factura, uuid_impuesto=iva_row.uuid, base_calculo=base, porcentaje_aplicado=iva_row.porcentaje, valor=iva_monto, fecha_retencion_hasta=date.today() + timedelta(days=5*365))`; `session.add(new_row)`; `await session.flush()`; return new_row.
  - **Acción**: imports `from ..models.V.impuestos import Impuestos`, `from ..models.A.factura_impuestos import FacturaImpuestos`; docstring REQ-OPS-053 + DEC-FACT-03. — **Validación**: T2.15 2 tests PASS.

- [x] **T-HU-F1.9-T2.17** [RED] — Write failing tests for `repo/factura.py::crear_factura_pago` (INSERT prod.factura_pagos with tipo_movimiento='pago', raise PagoDuplicadoError if init pago already exists for uuid_factura).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_crear_factura_pago_inserta_pago_inicial` — seed `prod.facturas(F)`; `crear_factura_pago(session, uuid_factura=F, medio_pago="efectivo", valor=5950)` returns `FacturaPagos` with `tipo_movimiento="pago"`.
    - T2: `test_crear_factura_pago_duplicado_raise_pago_duplicado_error` — seed `prod.factura_pagos(F, tipo_movimiento='pago')`; second call with same uuid_factura raises `PagoDuplicadoError` (BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness` post-MIGRATION 0027 Op 3).
  - **Patrón F1.7**: `pg_engine` real; trigger enforcement post-0027.
  - **Acción**: importar `crear_factura_pago`, `PagoDuplicadoError` from `parkos_core.repo.factura` (falla con `ImportError`); use `pytest.raises(PagoDuplicadoError)`. — **Archivo**: `backend/tests/integration/test_repo_factura.py` (mismo file, +25 LOC, 2 tests). — **Validación**: `ImportError`.

- [x] **T-HU-F1.9-T2.18** [GREEN] — Implement `crear_factura_pago` (~50 LOC) + `PagoDuplicadoError`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (mismo file).
  - **Contenido**: `class PagoDuplicadoError(Exception)` — 409 discriminator; `async def crear_factura_pago(session, *, uuid_factura, medio_pago, valor, referencia=None, uuid_sesion=None) -> FacturaPagos` — Step 10c: `new_row = FacturaPagos(uuid_factura=uuid_factura, medio_pago=medio_pago, valor=valor, referencia=referencia, uuid_sesion=uuid_sesion, tipo_movimiento="pago", fecha_retencion_hasta=date.today() + timedelta(days=5*365), timestamp_evento=datetime.now(UTC).replace(tzinfo=None))`; `session.add(new_row)`; `try: await session.flush() except IntegrityError as err: if "factura_pagos_init_pago_uniqueness" in str(err.orig): raise PagoDuplicadoError(uuid_factura=uuid_factura) from err; raise`; return new_row.
  - **Acción**: imports `from ..models.A.factura_pagos import FacturaPagos`; docstring REQ-OPS-053 + DEC-FACT-01. — **Validación**: T2.17 2 tests PASS.

- [x] **T-HU-F1.9-T2.19** [GREEN] — Define 4 typed exceptions in `repo/factura.py` (~40 LOC total): `SalidaNoFacturableError`, `ClienteNoEncontradoFacturaError`, `NitInvalidoError`, `TotalNoCoherenteError`, `VoucherRequeridoError`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (mismo file, top of file after imports).
  - **Contenido**:
    - `class SalidaNoFacturableError(Exception)` — V1 404 discriminator, `def __init__(self, *, uuid_salida)`; DEC-FACT-01 unified.
    - `class ClienteNoEncontradoFacturaError(Exception)` — V2 404 discriminator, `def __init__(self, *, numero_identificacion)`.
    - `class NitInvalidoError(Exception)` — V5 422 discriminator, `def __init__(self, *, dv_esperado: int, dv_recibido: str)`.
    - `class TotalNoCoherenteError(Exception)` — V6 422 discriminator, `def __init__(self, *, total_recibido, total_calculado, diferencia)`.
    - `class VoucherRequeridoError(Exception)` — V7 400 discriminator, `def __init__(self, *, medio_pago: str)`.
  - **Acción**: imports stdlib `uuid_lib`; append all 5 classes + update `__all__`; docstring REQ-OPS-053..063 + D-HU-F1.9-19. — **Validación**: imports succeed; `pytest.raises(SalidaNoFacturableError)` instantiable with `uuid_salida=uuid4()`.

  **Commit suggestion**: `feat(backend): HU-F1.9 — repo layer (factura + factura_detalle + NIT módulo 11)`.

  **Exit criteria T2**: T2.1..T2.19 verde; ~650 LOC cumulative (impl + tests).

### Cluster T3 — MIGRATION 0027 (~120 LOC impl + ~150 LOC tests)

- [x] **T-HU-F1.9-T3.1** [RED] — Write failing test for migration 0027 pre-flight `DO $$` 9-table existence check.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0027_preflight_aborta_con_tabla_faltante` — DROP TABLE `prod.facturas` (test-only); `alembic upgrade head` raises `0027_preflight_abort: tabla prod.facturas no existe` (or equivalent pre-flight exception); re-CREATE TABLE post-test cleanup.
    - T2: `test_migration_0027_preflight_pasa_con_tablas_presentes` — todas las 9 tablas existen post-0026; `alembic upgrade head` succeeds (no pre-flight abort).
  - **Patrón F1.6 / F1.7**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; KD-7 pre-flight `DO $$` block pattern reused verbatim.
  - **Acción**: alembic `upgrade head` invoca migration 0027 (falla con `relation "prod.facturas" does not exist` o pre-flight abort). — **Archivo**: `backend/tests/integration/test_migration_0027_idempotent.py` (nuevo, ~50 LOC, 2 tests). — **Validación**: `FAILED: alembic upgrade head` no aplica (migration 0027 no existe aún).

- [x] **T-HU-F1.9-T3.2** [GREEN] — Author `migrations/versions/0027_add_factura_immutability_and_init_pago_uniqueness.py` Op 1 pre-flight.
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0027_add_factura_immutability_and_init_pago_uniqueness.py` (nuevo, ~30 LOC of the full migration body, focusing on Op 1 first).
  - **Contenido**: `revision = "0027_add_factura_immutability_and_init_pago_uniqueness"`; `down_revision = "0026_seed_impuestos_iva_and_one_exit_per_ingreso"` (F1.7 chain head); `from alembic import op`; `def upgrade() -> None`: `op.execute("SET lock_timeout = '5s'")`; Op 1 = pre-flight `DO $$` block per design §8 (verify 9 tables: `facturas, factura_detalle, factura_impuestos, factura_pagos, clientes, impuestos, tarifas_sucursal, salidas, ingreso`).
  - **Acción**: pegar Op 1 pre-flight SQL skeleton verbatim from design §8 lines 1035-1068. — **Validación**: T3.1 2 tests PASS (T1 pre-flight aborts; T2 pre-flight succeeds).

- [x] **T-HU-F1.9-T3.3** [RED] — Write failing test for `one_factura_per_salida` partial unique index (MIGRATION 0027 Op 2).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_partial_unique_index_one_factura_per_salida_existe_post_migration` — post-`alembic upgrade head`, query `pg_indexes WHERE indexname='one_factura_per_salida'` returns 1 row.
    - T2: `test_insert_duplicate_uuid_salida_raise_unique_violation` — insert 2 `prod.facturas` rows with same `uuid_salida` (non-NULL); second INSERT raises `IntegrityError` pgcode 23505.
    - T3: `test_partial_unique_index_permite_uuid_salida_null` — INSERT `prod.facturas (uuid_salida=NULL)` succeeds (multiple rows allowed with NULL uuid_salida).
  - **Patrón F1.7**: `pg_engine` real; partial unique index pattern (`one_exit_per_ingreso` analog) reused.
  - **Acción**: alembic `upgrade head` applies migration; assert via `SELECT 1 FROM pg_indexes WHERE indexname='one_factura_per_salida'`. — **Archivo**: `backend/tests/integration/test_migration_0027_idempotent.py` (mismo file, +40 LOC, 3 tests). — **Validación**: `pg_indexes` query returns 0 rows (index does not exist yet).

- [x] **T-HU-F1.9-T3.4** [GREEN] — Author Op 2 partial unique index `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_factura_per_salida ON prod.facturas (uuid_salida) WHERE uuid_salida IS NOT NULL`.
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0027_add_factura_immutability_and_init_pago_uniqueness.py` (mismo file, append Op 2 after Op 1).
  - **Contenido**: `op.execute("CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_factura_per_salida ON prod.facturas (uuid_salida) WHERE uuid_salida IS NOT NULL")`. `CONCURRENTLY` for no lock on reads/writes durante creación; `IF NOT EXISTS` for idempotencia. **FEASIBILITY verified**: `prod.facturas` is NOT partitioned per migration 0001 lines 607-626 + ORM `models/L_E/facturas.py` lines 62-72 (composite PK only, no `postgresql_partition_by`).
  - **Acción**: append Op 2 SQL after Op 1. — **Validación**: T3.3 3 tests PASS.

- [x] **T-HU-F1.9-T3.5** [RED] — Write failing test for `fn_factura_pagos_init_pago_uniqueness` BEFORE INSERT trigger.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_trigger_factura_pagos_init_pago_uniqueness_existe_post_migration` — `SELECT 1 FROM pg_trigger WHERE tgname='factura_pagos_init_pago_uniqueness'` returns 1 row.
    - T2: `test_insert_segundo_init_pago_raise_unique_violation` — seed `prod.facturas(F)` + `prod.factura_pagos(F, tipo_movimiento='pago')`; second INSERT `prod.factura_pagos(F, tipo_movimiento='pago')` raises `IntegrityError` pgcode 23505 with substring `factura_pagos_init_pago_uniqueness`.
    - T3: `test_insert_reverso_no_bloqueado` — seed `prod.factura_pagos(F, tipo_movimiento='pago')`; INSERT `prod.factura_pagos(F, tipo_movimiento='reverso')` succeeds (reversos excluded from init-pago uniqueness check; F1.13 owns reverso enforcement).
  - **Patrón F1.7**: trigger pattern analogía `fn_factura_pagos_reverso_uniqueness` (migration 0004 lines 35-66).
  - **Acción**: alembic `upgrade head` aplica trigger; assert via `pg_trigger` query. — **Archivo**: `backend/tests/integration/test_migration_0027_idempotent.py` (mismo file, +40 LOC, 3 tests). — **Validación**: `pg_trigger` query returns 0 rows (trigger does not exist yet).

- [x] **T-HU-F1.9-T3.6** [GREEN] — Author Op 3 BEFORE INSERT trigger (analogía migration 0004 lines 35-66 pattern).
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0027_add_factura_immutability_and_init_pago_uniqueness.py` (mismo file, append Op 3).
  - **Contenido**:
    - `op.execute("CREATE OR REPLACE FUNCTION prod.fn_factura_pagos_init_pago_uniqueness() RETURNS trigger AS $$ BEGIN IF NEW.tipo_movimiento IN ('pago', 'ajuste') AND NEW.uuid_factura IS NOT NULL THEN IF EXISTS (SELECT 1 FROM prod.factura_pagos WHERE uuid_factura = NEW.uuid_factura AND tipo_movimiento IN ('pago', 'ajuste') AND NOT (NEW.uuid IS NOT NULL AND uuid = NEW.uuid)) THEN RAISE EXCEPTION 'factura_pagos init pago uniqueness violation: uuid_factura=% already has an init pago', NEW.uuid_factura USING ERRCODE = 'unique_violation'; END IF; END IF; RETURN NEW; END; $$ LANGUAGE plpgsql;")`.
    - `op.execute("DROP TRIGGER IF EXISTS factura_pagos_init_pago_uniqueness ON prod.factura_pagos;")`.
    - `op.execute("CREATE TRIGGER factura_pagos_init_pago_uniqueness BEFORE INSERT ON prod.factura_pagos FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_init_pago_uniqueness();")`.
  - **Acción**: append Op 3 SQL after Op 2. — **Validación**: T3.5 3 tests PASS.

- [x] **T-HU-F1.9-T3.7** [RED] — Write failing test for REVOKE re-assertion + idempotent fn_*_inmutable trigger re-install (4 [A] tables: factura_detalle, factura_impuestos, factura_otros_cobros, factura_pagos).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_revoke_re_assertion_post_migration` — query `information_schema.role_table_grants WHERE grantee='rol_app'` shows only `SELECT, INSERT` (no `UPDATE, DELETE`) for the 4 [A] tables.
    - T2: `test_idempotent_fn_inmutable_triggers_re_installed` — `SELECT 1 FROM pg_trigger WHERE tgname IN ('factura_detalle_inmutable', 'factura_impuestos_inmutable', 'factura_pagos_inmutable')` returns 3 rows.
    - T3: `test_migration_0027_re_apply_ok` — `alembic upgrade head` 2 veces seguidas; second es no-op (Op 2 `IF NOT EXISTS`, Op 3 `DROP IF EXISTS + CREATE`).
  - **Patrón F1.7**: analogía migration 0004 lines 68-78 (REVOKE re-assertion + idempotent trigger re-install).
  - **Acción**: alembic `upgrade head` aplica Op 4; assert via `information_schema` + `pg_trigger`. — **Archivo**: `backend/tests/integration/test_migration_0027_idempotent.py` (mismo file, +20 LOC, 3 tests). — **Validación**: Op 4 not yet applied; triggers exist from migration 0001 lines 2024-2088 but REVOKE not re-asserted.

- [x] **T-HU-F1.9-T3.8** [GREEN] — Author Op 4 (REVOKE/GRANT + DROP TRIGGER IF EXISTS + CREATE TRIGGER for each).
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0027_add_factura_immutability_and_init_pago_uniqueness.py` (mismo file, append Op 4).
  - **Contenido**:
    - For each table in `("factura_detalle", "factura_impuestos", "factura_otros_cobros", "factura_pagos")`: `op.execute(f"REVOKE UPDATE, DELETE ON prod.{table} FROM rol_app;")`; `op.execute(f"GRANT SELECT, INSERT ON prod.{table} TO rol_app;")`.
    - For each table in `("factura_detalle", "factura_impuestos", "factura_pagos")`: `op.execute(f"DROP TRIGGER IF EXISTS {table}_inmutable ON prod.{table};")`; `op.execute(f"CREATE TRIGGER {table}_inmutable BEFORE UPDATE OR DELETE ON prod.{table} FOR EACH ROW EXECUTE FUNCTION prod.fn_{table}_inmutable();")`.
    - `op.execute("DROP TRIGGER IF EXISTS factura_pagos_reverso_uniqueness ON prod.factura_pagos;")`; `op.execute("CREATE TRIGGER factura_pagos_reverso_uniqueness BEFORE INSERT ON prod.factura_pagos FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_reverso_uniqueness();")` (defensive re-install from migration 0004 lines 61-66).
  - **Acción**: append Op 4 SQL after Op 3. — **Validación**: T3.7 3 tests PASS.

- [x] **T-HU-F1.9-T3.9** [REFACTOR] — Add `def downgrade() -> None` with reverse order (Op 3 → Op 2) + add pre-flight `DO $$` block at migration head with 9-table existence check (idempotency on downgrade + re-upgrade).
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0027_add_factura_immutability_and_init_pago_uniqueness.py` (mismo file, append `def downgrade()`).
  - **Contenido**:
    - `def downgrade() -> None`: `op.execute("SET lock_timeout = '5s'")`; `op.execute("DROP TRIGGER IF EXISTS factura_pagos_init_pago_uniqueness ON prod.factura_pagos;")`; `op.execute("DROP FUNCTION IF EXISTS prod.fn_factura_pagos_init_pago_uniqueness();")`; `op.execute("DROP INDEX IF EXISTS prod.one_factura_per_salida")` (Op 2 reverse).
    - Note: Op 4 cannot be cleanly reversed (REVOKE statements are correct and should NOT be re-granted on downgrade; fn_*_inmutable triggers remain in place; factura_pagos_reverso_uniqueness trigger remains in place).
  - **Acción**: append `def downgrade()`; docstring note that Op 4 has no clean reverse (matches F1.7 design §8 note). — **Validación**: `alembic downgrade -1` executes Op 3 reverse + Op 2 reverse without error; `alembic upgrade head` re-applies all 4 ops successfully (idempotency).

  **Commit suggestion**: `feat(db): HU-F1.9 — MIGRATION 0027 one_factura_per_salida + init_pago trigger + REVOKE re-assertion`.

  **Exit criteria T3**: T3.1..T3.9 verde; ~920 LOC cumulative (impl + tests).

### Cluster T4 — Handler / Router (~150 LOC impl + ~150 LOC tests)

- [x] **T-HU-F1.9-T4.1** [RED] — Write failing HTTP test for `POST /api/v1/facturacion/factura` happy path (V1..V6 all pass, KD-FACT-01 single commit).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_factura_atomica_rotacion_exitosa_returns_201` — seed `prod.salidas(X)`, `prod.tarifas_sucursal(T)`, `prod.impuestos.IVA`; POST `{"uuid_salida":X, "items":[{"tipo":"servicio","concepto":"parqueo","cantidad":1,"valor_unitario":5000,"uuid_tarifa_sucursal":T}], "subtotal":5000, "total":5950, "medio_pago":"efectivo", "fe_con_datos":false}` with `cajero-X` JWT → 201 + `FacturaRead{estado:"emitida", uuid_cliente:null, total:5950}`; verify 4 tables have rows.
  - **Patrón F1.7**: `httpx.AsyncClient + ASGITransport(app)` + JWT `cajero-` fixture; real `pg_engine` con `PARKOS_DOCKER_TEST=1`.
  - **Acción**: importar `FacturaCreate`, `FacturaRead` from `parkos_core.schemas.facturacion`; use `pytest_asyncio.fixture` + `seed_tarifas_sucursal`, `seed_impuestos_iva`, `seed_salida` fixtures. — **Archivo**: `backend/tests/unit/test_facturacion_factura.py` (nuevo, ~80 LOC, 1 test). — **Validación**: `ImportError: cannot import name 'create_factura' from 'parkos_core.api.v1.facturacion' (or module does not exist)` or `404 Not Found` (handler not registered).

- [x] **T-HU-F1.9-T4.2** [GREEN] — Implement `api/v1/facturacion.py::create_factura` 12-step chain (Step 1 KD-3 issuer, Step 2 V1 salida, Step 3 tenant scope post-V1, Step 4 V2 cliente, Step 5 V3 IVA, Step 6 V4 detalle, Step 7 KD-FACT-02 FOR SHARE, Step 8 V6 total, Step 9 INSERT facturas, Step 10a/b/c INSERT detalle+impuestos+pagos, Step 11 single `await session.commit()`, Step 12 response shape).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (nuevo, ~120 LOC).
  - **Contenido**: `router = APIRouter(prefix="/facturacion", tags=["facturacion"])`; `_facturacion_issuer_dep = requires_issuer("admin-", "cajero-")`; `@router.post("/factura", response_model=FacturaRead, status_code=201, responses={403:..., 404:..., 409:..., 422:..., 500:...})`; `async def create_factura(response: Response, payload: FacturaCreate, session: AsyncSession = Depends(get_session), ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_facturacion_issuer_dep)) -> FacturaRead`; body follows design §7 verbatim (12 steps).
  - **Acción**: imports `from ..deps import get_session, no_store_headers, requires_issuer, apply_no_store_header`, `from ..auth.tenancy import TenantContext, get_tenant_ctx`, `from ..repo.factura import *`, `from ..repo.factura_detalle import crear_factura_detalle_bulk`, `from ..repo.impuestos import validar_iva_configurado`, `from ..schemas.facturacion import (FacturaCreate, FacturaItemRead, FacturaRead)`; docstring REQ-OPS-053..063 + DEC-FACT-01..09 + KD-FACT-01/02. — **Validación**: T4.1 1 test PASS; 4 tables populated atomically.

- [x] **T-HU-F1.9-T4.3** [RED] — Write failing HTTP test for `POST /api/v1/facturacion/factura-pagos` happy path.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_factura_pago_datafono_con_referencia_returns_201` — seed `prod.facturas(F, estado='emitida')`; POST `{"uuid_factura":F, "medio_pago":"datafono", "valor":1000, "referencia":"VCHR-12345"}` with `cajero-` JWT → 201 + `FacturaPagoRead{referencia:"VCHR-12345", valor:1000}`.
  - **Patrón F1.7**: HTTP integration test pattern.
  - **Acción**: importar `FacturaPagoAdicionalCreate`, `FacturaPagoRead` from `parkos_core.schemas.facturacion`. — **Archivo**: `backend/tests/unit/test_facturacion_factura_pagos.py` (nuevo, ~40 LOC, 1 test). — **Validación**: `ImportError` or `404 Not Found`.

- [x] **T-HU-F1.9-T4.4** [GREEN] — Implement `api/v1/facturacion.py::create_factura_pago` 5-step chain (Step 1 KD-3 issuer, Step 2 V5 voucher_requerido, Step 3 tenant scope, Step 4 INSERT factura_pagos, Step 5 single `await session.commit()`).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (mismo file, ~50 LOC appended).
  - **Contenido**: `@router.post("/factura-pagos", response_model=FacturaPagoRead, status_code=201, responses={400:..., 404:..., 422:..., 409:...})`; `async def create_factura_pago(response: Response, payload: FacturaPagoAdicionalCreate, session: AsyncSession = Depends(get_session), ctx: TenantContext = Depends(get_tenant_ctx), _claims: None = Depends(_facturacion_issuer_dep)) -> FacturaPagoRead`; body per design §7 verbatim (5 steps).
  - **Acción**: append handler after `create_factura`; imports already present. — **Validación**: T4.3 1 test PASS.

- [x] **T-HU-F1.9-T4.5** [REFACTOR] — Extract common `no_store_headers` + `apply_no_store_header` calls (reuse `_helpers.py`).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (mismo file).
  - **Contenido**: ensure both handlers call `no_store = no_store_headers()` at top + `apply_no_store_header(response)` before return; consolidate `_facturacion_issuer_dep = requires_issuer("admin-", "cajero-")` once (not duplicated).
  - **Acción**: extract issuer_dep to module-level constant; ensure Cache-Control: no-store on all 2xx/4xx/5xx responses via `headers=no_store` param in `HTTPException` constructors. — **Validación**: AST walk `test_factura_handler_no_store_header.py` (added in T6 cluster) passes.

- [x] **T-HU-F1.9-T4.6** [RED] — Write failing HTTP tests for 4xx/5xx discriminators (404 salida_no_encontrada, 422 nit_invalido, 422 total_no_coherente, 500 iva_no_configurado, 400 voucher_requerido, 409 one_factura_per_salida_violation).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_factura_salida_inexistente_returns_404` — POST with non-existent uuid_salida → 404 + body `{"error":"salida_no_encontrada","uuid_salida":"..."}`; no INSERT.
    - T2: `test_factura_nit_invalido_returns_422` — `fe_con_datos=true` + `dv:"5"` for `800.123.456` → 422 + body `{"error":"nit_invalido","dv_esperado":7,"dv_recibido":"5"}` (Pydantic raises ValidationError → FastAPI maps to 422).
    - T3: `test_factura_total_no_coherente_returns_422` — payload `total=6000` vs server-computed `5950` → 422 + body `{"error":"total_no_coherente","total_recibido":"6000","total_calculado":"5950","diferencia":"50"}`; no INSERT.
    - T4: `test_factura_iva_no_configurado_returns_500` — DELETE `prod.impuestos WHERE codigo='IVA'` (pre-test); POST happy path → 500 + body `{"error":"iva_no_configurado"}`; cleanup re-INSERT IVA.
    - T5: `test_factura_pago_datafono_sin_referencia_returns_400` — POST `/factura-pagos` with `medio_pago="datafono"`, `referencia=""` → 400 + body `{"error":"voucher_requerido"}`; no INSERT.
    - T6: `test_factura_duplicada_returns_409` — seed `prod.salidas(X)` + `prod.facturas(X, uuid_salida=X)`; second POST with same uuid_salida → 409 + body `{"error":"factura_duplicada","uuid_salida":"X"}` (post-MIGRATION 0027 Op 2 partial unique index violation → IntegrityError → FacturaDuplicadaError → 409).
  - **Patrón F1.7**: HTTP integration tests with `httpx.AsyncClient` + JWT fixtures + real DB.
  - **Acción**: import schemas + handler; parametrizar `pytest.mark.parametrize("test_case", [T1..T6])`. — **Archivo**: extend T4.1 file (`backend/tests/unit/test_facturacion_factura.py`) with +~80 LOC for 6 discriminator tests. — **Validación**: each test fails with expected HTTP code (pre-implementation: 500 or 404 placeholder).

  **Commit suggestion**: `feat(backend): HU-F1.9 — handlers POST /factura + POST /factura-pagos`.

  **Exit criteria T4**: T4.1..T4.6 verde; ~1,220 LOC cumulative (impl + tests).

### Cluster T5 — Tests + DB integration (~850 LOC tests)

- [x] **T-HU-F1.9-T5.1** [RED] — Write failing test for `repo/nit_modulo11.py::validar_nit_modulo11` with 4 cases (reference DIAN `800.123.456-7` → 7, short NIT raises, non-digit chars stripped, leading zeros stripped).
  - **Tests** (pure helper, sin DB):
    - T1: `test_dian_reference_800_123_456_7_passes` — `validar_nit_modulo11("800.123.456-7", "7") is True`; `dv_esperado("800.123.456") == 7`.
    - T2: `test_short_nit_raises` — `dv_esperado("123")` raises `ValueError` (NIT <5 digits).
    - T3: `test_non_digit_chars_stripped` — `validar_nit_modulo11("800.123.456-7", "7") is True` (dash + dot stripped).
    - T4: `test_leading_zeros_stripped` — `validar_nit_modulo11("000123-1", "1") is True` (normalized to `"123"`).
    - T5: `test_dv_non_digit_returns_false` — `validar_nit_modulo11("800.123.456", "X") is False`.
  - **Patrón F1.7**: pure Python helper tests.
  - **Acción**: imports from `parkos_core.repo.nit_modulo11`. — **Archivo**: `backend/tests/unit/test_validar_nit_modulo11.py` (extend T1.1 file, +~30 LOC). — **Validación**: 5 tests PASS post T1.2 GREEN.

- [x] **T-HU-F1.9-T5.2** [GREEN] — Confirm tests pass.
  - **Acción**: ejecutar `uv run pytest backend/tests/unit/test_validar_nit_modulo11.py -q`. — **Validación**: `5 passed`.

- [x] **T-HU-F1.9-T5.3** [RED] — Write failing DB integration test for MIGRATION 0027 Op 2 (insert duplicate `uuid_salida` → IntegrityError pgcode 23505).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0027_op2_unique_violation` — seed 2 `prod.facturas` rows with same `uuid_salida=X`; second INSERT raises `IntegrityError` with pgcode `23505` and substring `one_factura_per_salida`.
  - **Patrón F1.7**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; partial unique index pattern test.
  - **Acción**: alembic `upgrade head` applies 0027; assert via direct INSERT. — **Archivo**: `backend/tests/integration/test_migration_0027_idempotent.py` (mismo file, +~25 LOC, 1 test). — **Validación**: post-0027, `one_factura_per_salida` index enforces uniqueness; `IntegrityError` raised.

- [x] **T-HU-F1.9-T5.4** [GREEN] — Confirm test passes (gated by `PARKOS_DOCKER_TEST=1` per F1.7 D0 precedent).
  - **Acción**: ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0027_idempotent.py -q`. — **Validación**: `1 passed` (test_migration_0027_op2_unique_violation).

- [x] **T-HU-F1.9-T5.5** [RED] — Write failing DB integration test for MIGRATION 0027 Op 3 (insert 2nd init pago for same uuid_factura → IntegrityError pgcode 23505).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0027_op3_trigger_unique_violation` — seed `prod.facturas(F)` + `prod.factura_pagos(F, tipo_movimiento='pago')`; second INSERT `prod.factura_pagos(F, tipo_movimiento='pago')` raises `IntegrityError` with substring `factura_pagos_init_pago_uniqueness` and pgcode `23505` (BEFORE INSERT trigger `RAISE EXCEPTION USING ERRCODE='unique_violation'`).
  - **Patrón F1.7**: trigger enforcement test analogía `fn_factura_pagos_reverso_uniqueness`.
  - **Acción**: alembic `upgrade head` applies 0027; assert via direct INSERT. — **Archivo**: `backend/tests/integration/test_migration_0027_idempotent.py` (mismo file, +~25 LOC, 1 test). — **Validación**: post-0027, trigger fires; `IntegrityError` raised.

- [x] **T-HU-F1.9-T5.6** [GREEN] — Confirm test passes.
  - **Acción**: ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0027_idempotent.py -q`. — **Validación**: `2 passed` (T5.3 + T5.5).

- [x] **T-HU-F1.9-T5.7** [RED] — Write failing DB integration test for MIGRATION 0027 Op 4 (REVOKE re-assertion + idempotent trigger re-install; re-apply migration → no error).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0027_op4_revoke_reassertion` — query `information_schema.role_table_grants WHERE grantee='rol_app'` and table_name IN ('factura_detalle', 'factura_impuestos', 'factura_otros_cobros', 'factura_pagos'); assert `privilege_type IN ('SELECT', 'INSERT')` only (no `UPDATE`, `DELETE`).
    - T2: `test_migration_0027_op4_idempotent_reapply` — `alembic upgrade head` 2 veces seguidas; second es no-op (Op 2 `IF NOT EXISTS`, Op 3 `DROP IF EXISTS + CREATE`, Op 4 `REVOKE` idempotent + `DROP IF EXISTS + CREATE`); assert no errors.
  - **Patrón F1.7**: REVOKE re-assertion + idempotent trigger re-install test pattern.
  - **Acción**: alembic `upgrade head` applies 0027; query `information_schema` + re-run `alembic upgrade head`. — **Archivo**: `backend/tests/integration/test_migration_0027_idempotent.py` (mismo file, +~40 LOC, 2 tests). — **Validación**: post-0027, REVOKE enforced + idempotency confirmed.

- [x] **T-HU-F1.9-T5.8** [GREEN] — Confirm tests pass.
  - **Acción**: ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0027_idempotent.py -q`. — **Validación**: `4 passed` (T5.3, T5.5, T5.7 T1, T5.7 T2).

- [x] **T-HU-F1.9-T5.9** [RED] — Write failing HTTP unit test for `POST /factura` atomicidad (mock session.commit, verify exactly 1 invocation, mock session.rollback on IntegrityError).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_post_factura_invoke_session_commit_exactly_once` — patch `session.commit` with `AsyncMock(side_effect=lambda: setattr(counter, 'commits', counter.commits + 1))`; POST happy path; assert `counter.commits == 1` (KD-FACT-01 invariant).
    - T2: `test_post_factura_integrity_error_rolls_back` — simulate `IntegrityError` on Step 10b `crear_factura_impuesto_iva`; patch `session.rollback` with `AsyncMock`; verify `rollback` invoked (no orphan rows).
  - **Patrón F1.7**: HTTP integration test with `unittest.mock.patch.object(session, 'commit')` to count calls.
  - **Acción**: import handler + use `pytest_asyncio.fixture` + `unittest.mock`. — **Archivo**: `backend/tests/unit/test_facturacion_atomicidad.py` (nuevo, ~60 LOC, 2 tests). — **Validación**: 1 test PASS (counter); 1 test PASS (rollback invoked).

- [x] **T-HU-F1.9-T5.10** [GREEN] — Confirm tests pass.
  - **Acción**: ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_facturacion_atomicidad.py -q`. — **Validación**: `2 passed`.

- [x] **T-HU-F1.9-T5.11** [RED] — Write failing HTTP unit test for `POST /factura-pagos` voucher_requerido (medio_pago='datafono' without referencia → 400).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_factura_pago_datafono_sin_referencia_returns_400_voucher_requerido` — POST `{"uuid_factura":F, "medio_pago":"datafono", "valor":1000, "referencia":null}` → 400 + body `{"error":"voucher_requerido","medio_pago":"datafono"}`; no INSERT.
    - T2: `test_factura_pago_datafono_referencia_empty_string_returns_400` — POST `{"uuid_factura":F, "medio_pago":"datafono", "valor":1000, "referencia":""}` → 400 (empty string treated as missing).
  - **Patrón F1.7**: HTTP integration test pattern.
  - **Acción**: import handler + use fixtures. — **Archivo**: extend T4.3 file (`backend/tests/unit/test_facturacion_factura_pagos.py`) with +~30 LOC, 2 tests. — **Validación**: both tests PASS post T4.4 GREEN.

- [x] **T-HU-F1.9-T5.12** [GREEN] — Confirm tests pass.
  - **Acción**: ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/unit/test_facturacion_factura_pagos.py -q`. — **Validación**: `3 passed` (T4.3 happy path + T5.11 T1 + T5.11 T2).

- [x] **T-HU-F1.9-T5.13** [REFACTOR] — Split test files (`test_facturacion_factura.py`, `test_facturacion_factura_pagos.py`, `test_validar_nit_modulo11.py`, `test_factura_atomicidad_db.py`, `test_migration_0027_idempotent.py`) into canonical 5-file layout (no further test additions; only reorganize to match F1.7 precedent split).
  - **Archivos**: ensure each test file is self-contained + uses canonical fixture patterns from F1.7 (`seed_tarifas_sucursal`, `seed_impuestos_iva`, `seed_salida`, `seed_clientes`, `cajero_jwt`).
  - **Acción**: extract shared fixtures to `conftest.py` if duplicated across files. — **Validación**: `uv run pytest backend/tests/ -q` (skip Docker-gated SKIPs) verde; no regresión F1.5/F1.6/F1.7/F1.8.

  **Commit suggestion**: `test(backend): HU-F1.9 — DB integration tests + handler unit tests + NIT módulo 11`.

  **Exit criteria T5**: T5.1..T5.13 verde; ~2,530 LOC cumulative (impl + tests).

### Cluster T6 — AST walks (~80 LOC tests)

- [x] **T-HU-F1.9-T6.1** [RED] — Write failing AST walk `tests/static/test_factura_handler_single_commit.py` enforcing exactly 1 `await session.commit()` invocation in `api/v1/facturacion.py::create_factura` function body (KD-FACT-01 invariant, F1.7 pattern reused).
  - **Tests**:
    - T1: `test_create_factura_handler_invokes_session_commit_exactly_once` — AST.parse `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py`; locate `create_factura` via `ast.walk + ast.AsyncFunctionDef.name == 'create_factura'`; collect commits via `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and getattr(n.value.func, "attr", "") == "commit"])`; assert `commit_count == 1`. Also assert `len([n for n in ast.walk(body) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "begin_nested"]) == 0`; assert NO `SAVEPOINT` / `RELEASE SAVEPOINT` string literals.
  - **Patrón F1.7** (`test_salida_handler_step_order.py`): `ast.parse` + recursion via `iter_child_nodes` (NOT `ast.walk` which is BFS — `iter_child_nodes` is DFS that preserves source order).
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_factura_handler_single_commit.py` (nuevo, ~80 LOC, 1 AST walk). — **Validación**: post T4.2 GREEN, `commit_count == 1` (handler has 1 commit at Step 11); FAIL if future-dev introduces multiple commits.

- [x] **T-HU-F1.9-T6.2** [GREEN] — Confirm walk passes (with `create_factura` having exactly 1 commit).
  - **Acción**: ejecutar `uv run pytest backend/tests/static/test_factura_handler_single_commit.py -q`. — **Validación**: `1 passed`.

- [x] **T-HU-F1.9-T6.3** [RED] — Write failing AST walk `tests/static/test_factura_handler_step_order.py` enforcing 12-step chain order via `_visit` recursion with `iter_child_nodes` (F1.7 `test_salida_handler_step_order.py` pattern).
  - **Tests**:
    - T1: `test_create_factura_handler_invoca_helpers_en_orden_correcto` — AST.parse `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py`; locate `create_factura`; walk statements via `iter_child_nodes` recursion (DFS); collect function/method call names en source order; assert sequence contains literal ordered pattern: `buscar_salida_facturable` → `validar_iva_configurado` (tenant scope step 3 is conditional, so check for it inside `if ctx.issuer_prefix == "cajero-"` block) → `buscar_o_crear_cliente_por_nit` (conditional on `payload.fe_con_datos`) → `validar_items` → `lock_tarifas_sucursal_para_items` → `compute_total` → `crear_factura_evento` → `crear_factura_detalle_bulk` → `crear_factura_impuesto_iva` → `crear_factura_pago` → `session.commit`.
  - **Patrón F1.7**: `ast.parse` + recursion via `iter_child_nodes` + `ast.FunctionDef` / `ast.AsyncFunctionDef` + `ast.Call`; extract `call.func.id` (direct) or `call.func.attr` (via `repo.X.Y`).
  - **Acción**: import `ast`, `pathlib.Path`; walk `body` recursively. — **Archivo**: `backend/tests/static/test_factura_handler_step_order.py` (nuevo, ~80 LOC, 1 AST walk). — **Validación**: post T4.2 GREEN, walk passes (correct step ordering); FAIL si future-dev reorder.

- [x] **T-HU-F1.9-T6.4** [GREEN] — Confirm walk passes (with correct step ordering).
  - **Acción**: ejecutar `uv run pytest backend/tests/static/test_factura_handler_step_order.py -q`. — **Validación**: `1 passed`.

  **Commit suggestion**: `test(backend): HU-F1.9 — AST walks KD-FACT-01 (single commit) + 12-step order`.

  **Exit criteria T6**: T6.1..T6.4 verde; ~2,690 LOC cumulative (impl + tests).

### Cluster T7 — OpenAPI + frontend stub (~120 LOC impl + ~40 LOC tests)

- [x] **T-HU-F1.9-T7.1** [RED] — Write failing test asserting OpenAPI spec at `apps/facturacion/openapi.yaml` exists and contains `/api/v1/facturacion/factura` + `/api/v1/facturacion/factura-pagos` paths.
  - **Tests**:
    - T1: `test_openapi_facturacion_yaml_existe` — assert `Path("apps/facturacion/openapi.yaml").is_file()`.
    - T2: `test_openapi_facturacion_contiene_paths_factura_y_factura_pagos` — parse YAML; assert `paths["/api/v1/facturacion/factura"]` and `paths["/api/v1/facturacion/factura-pagos"]` exist.
    - T3: `test_openapi_facturacion_contiene_responses_typed_errors` — assert components.schemas contain `NitInvalidoErrorSchema`, `ClienteNoEncontradoErrorSchema`, `DetalleInvalidoErrorSchema`, `TotalNoCoherenteErrorSchema`.
  - **Patrón F1.7**: pure file existence + YAML parse tests, sin DB.
  - **Acción**: import `yaml` (PyYAML), `pathlib.Path`. — **Archivo**: `backend/tests/unit/test_openapi_facturacion.py` (nuevo, ~25 LOC, 3 tests). — **Validación**: `FileNotFoundError: apps/facturacion/openapi.yaml`.

- [x] **T-HU-F1.9-T7.2** [GREEN] — Author `apps/facturacion/openapi.yaml` with 2 paths + 7 typed errors + request/response schemas.
  - **Archivo**: `apps/facturacion/openapi.yaml` (nuevo, ~80 LOC).
  - **Contenido**:
    - `openapi: 3.0.0`; `info: {title: facturacion-billing, version: 1.0.0}`; `paths:`:
      - `/api/v1/facturacion/factura`:
        - `post:` with `requestBody` (FacturaCreate schema), `responses` (201 FacturaRead, 403 tenant_scope, 404 salida_no_encontrada, 409 factura_duplicada, 422 nit_invalido+detalle_invalido+total_no_coherente, 500 iva_no_configurado).
      - `/api/v1/facturacion/factura-pagos`:
        - `post:` with `requestBody` (FacturaPagoAdicionalCreate schema), `responses` (201 FacturaPagoRead, 400 voucher_requerido, 404 factura_no_encontrada, 409 pago_duplicado, 422 monto_insuficiente).
    - `components.schemas`: FacturaCreate, FacturaItemCreate, FacturaRead, FacturaItemRead, FacturaPagoAdicionalCreate, FacturaPagoRead, NitInvalidoErrorSchema, ClienteNoEncontradoErrorSchema, DetalleInvalidoErrorSchema, TotalNoCoherenteErrorSchema (7+).
  - **Acción**: paste verbatim from design §6 + §10.1. — **Validación**: T7.1 3 tests PASS.

- [x] **T-HU-F1.9-T7.3** [RED] — Write failing test asserting frontend router stub at `apps/facturacion/router.py` registers 2 endpoints (forwarding to backend).
  - **Tests**:
    - T1: `test_frontend_router_stub_existe` — assert `Path("apps/facturacion/router.py").is_file()`.
    - T2: `test_frontend_router_stub_importa_sin_error` — `import apps.facturacion.router` succeeds; module exports `router` (APIRouter instance).
  - **Patrón F1.7**: pure import test, sin DB.
  - **Acción**: import `from apps.facturacion import router as fe_router`. — **Archivo**: `backend/tests/unit/test_frontend_router_stub.py` (nuevo, ~15 LOC, 2 tests). — **Validación**: `ModuleNotFoundError: No module named 'apps.facturacion'`.

- [x] **T-HU-F1.9-T7.4** [GREEN] — Author `apps/facturacion/router.py` (~120 LOC stub, forwards to backend).
  - **Archivo**: `apps/facturacion/router.py` (nuevo, ~120 LOC).
  - **Contenido**:
    - `from fastapi import APIRouter, Depends, Request`; `from parkos_core.deps.auth import get_current_actor, require_roles`; `from parkos_core.api.v1.facturacion import router as backend_router`.
    - `router = APIRouter(prefix="/facturacion", tags=["facturacion"])`; forward 2 endpoints: `@router.post("/factura")` + `@router.post("/factura-pagos")` that delegate to `backend_router` via FastAPI dependency injection (or just re-export `backend_router` with adjusted prefix).
    - Stub JWT auth + role check (mirror F1.7 `apps/operacion/router.py`).
  - **Acción**: paste verbatim from design §10.1 (router skeleton). — **Validación**: T7.3 2 tests PASS.

  **Commit suggestion**: `feat(apps): HU-F1.9 — OpenAPI spec + frontend router stub`.

  **Exit criteria T7**: T7.1..T7.4 verde; ~2,850 LOC cumulative (impl + tests).

### Cluster T8 — Docstring drift fix (~1 LOC impl + ~10 LOC tests)

- [x] **T-HU-F1.9-T8.1** [RED] — Write failing static test asserting `models/A/factura_pagos.py` lines 9-18 docstring does NOT reference `0004_add_factura_pagos_reverso_index.py` (does NOT exist).
  - **Tests**:
    - T1: `test_factura_pagos_docstring_no_references_nonexistent_migration` — read `backend/packages/parkos_core/src/parkos_core/models/A/factura_pagos.py`; extract docstring (lines 9-18); assert `re.search(r"0004_add_factura_pagos_reverso_index\.py", docstring) is None`; assert `re.search(r"0004_add_factura_pagos_reverso_trigger\.py", docstring) is not None` (correct filename).
  - **Patrón F1.7**: pure regex test on docstring; AST walk pattern reused.
  - **Acción**: import `re`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_factura_pagos_docstring_no_drift.py` (nuevo, ~10 LOC, 1 test). — **Validación**: pre-fix, `re.search(r"0004_add_factura_pagos_reverso_index\.py", docstring)` matches (drift present).

- [x] **T-HU-F1.9-T8.2** [GREEN] — Edit `models/A/factura_pagos.py` lines 9-18 single-line fix: replace `0004_add_factura_pagos_reverso_index.py` → `0004_add_factura_pagos_reverso_trigger.py`.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/models/A/factura_pagos.py` (modificado, ~1 LOC change).
  - **Contenido**: lines 9-18 docstring has a pre-existing drift referencing `0004_add_factura_pagos_reverso_index.py` which does NOT exist; the actual migration is `0004_add_factura_pagos_reverso_trigger.py`. Replace substring verbatim.
  - **Acción**: single-line `Edit` with `old_string="0004_add_factura_pagos_reverso_index.py"`; `new_string="0004_add_factura_pagos_reverso_trigger.py"`. — **Validación**: T8.1 1 test PASS; docstring now references correct migration filename.

  **Commit suggestion**: `chore(backend): HU-F1.9 — fix stale docstring drift on factura_pagos ORM`.

  **Exit criteria T8**: T8.1..T8.2 verde; ~2,861 LOC cumulative (impl + tests).

## Cross-cluster constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` en `create_factura` handler outside the 4 expected INSERTs (Step 9 + Step 10a/b/c) — AST walk `test_factura_handler_single_commit.py` (T6.1) enforces via KD-FACT-01 single-commit invariant + `test_factura_handler_step_order.py` (T6.3) enforces 12-step order.
- NO hardcoded IVA percentage (`Decimal("0.19")`) en `compute_total`; caller passes IVA from `prod.impuestos` (DEC-FACT-03).
- NO `Co-authored-by:` ni trailers AI en commits; conventional commits, neutral Spanish.
- NO SQLite en tests — `pg_engine` real o `testcontainers[postgres]` (precedente F1.4/F1.5/F1.6/F1.7).
- NO modificación de `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate (matches F1.7).
- NO modificación de `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate cross-cutting.
- NO modificación de `api/deps.py` ni `auth/tenancy.py` — KD-3 chain + errores tipados intactos.
- NO modificación de `repo/event.py` — `event_helper_intact` CI gate (matches F1.7).
- NO modificación de `repo/impuestos.py` (F1.7) — `validar_iva_configurado` reusado verbatim para V3.
- NO modificación de `repo/cotizacion.py` (F1.8) — `calcular_cotizacion` no se invoca desde F1.9.
- NO modificación de `repo/ingreso.py` — `validar_kd_forzado` no se invoca desde F1.9.
- NO modificación de `repo/subscripcion_activa.py` (F1.6) ni `repo/placa.py` (F1.6).
- NO `correlacion_id` en el body (DEC-IDEM-01) — header `Idempotency-Key` via PR2 middleware.
- NO `uuid_cliente` como columna persistente en `prod.facturas` (DEC-FACT-06) — derivado server-side en `FacturaRead.uuid_cliente`.
- NO `prefijo` + `consecutivo` en `prod.facturas` (DEC-FACT-05) — F1.10 owns FE numbering.
- NO `prod.forma_pago` catálogo (DEC-FACT-07 Opción A) — Pydantic `Literal[...]` enforced.
- NO `prod.retencion` table (DEC-FACT-04) — `compute_total` accepts `retencion=Decimal("0")` placeholder.
- NO `prod.factura_electronica` modifications (F1.10 owns).
- NO `prod.facturas.uuid_cliente` FK column — DEC-FACT-06 (4FN compliance).
- Header `Cache-Control: no-store` en TODA respuesta 2xx/4xx/5xx del endpoint (via `no_store_headers()` helper + `apply_no_store_header(response)`).
- Discriminadores de error estables: `voucher_requerido` (400 datafono), `monto_insuficiente` (400 factura-pagos), `tenant_scope_violation` (403 cajero cross-branch), `salida_no_encontrada` (404 V1 unified), `cliente_no_encontrado` (404 V2), `factura_duplicada` (409 partial unique index), `pago_duplicado` (409 BEFORE INSERT trigger), `detalle_invalido` (422 V4), `nit_invalido` (422 V5 Pydantic), `total_no_coherente` (422 V6), `iva_no_configurado` (500 V3, post-0026: never).
- Precedencia de errores (D-HU-F1.9-12): KD-3 (400/403) > V1 (404 salida) > tenant scope (403) > V2 (404 cliente) > V3 (500 IVA) > V4 (422 detalle) > V5 Pydantic (422 nit) > KD-FACT-02 lock > V6 (422 total) > Step 9 INSERT (409 dup) > Step 11 commit > Step 12 response 201.
- Migration `0027` debe usar `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` (idempotente; `CONCURRENTLY` no lock reads/writes en producción).
- `prod.facturas` is `[L-E]` bi-temporal versioning — NO `fn_facturas_inmutable` trigger needed (DEC-FACT-01 amended; bi-temporal PK handles immutability).
- `prod.factura_pagos` is partitioned by `RANGE (fecha_retencion_hasta)` (migration 0001 line 716) — partial unique index INFEASIBLE; BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness` is the only DB-layer defense.
- **CRITICAL** Single `await session.commit()` (KD-FACT-01) at Step 11 — locks released + 4 tables atomically materialized.
- **CRITICAL** Step 7 (`lock_tarifas_sucursal_para_items`) MUST execute BEFORE Step 8 (`compute_total`) AND inside the same transaction (KD-FACT-02 lock continuity). The FOR SHARE lock acquired in Step 7 is held through Step 8 (V6), Step 9 INSERT, Step 10 INSERTs until the single `session.commit()` in Step 11.
- **CRITICAL** `fe_con_datos=false` SKIPS Step 4 V2 entirely (DEC-FACT-08 consumidor final placeholder; no FK lookup).
- **CRITICAL** `medio_pago="datafono"` requires `referencia` non-empty (voucher_requerido, KD-NIT-07) en AMBOS endpoints `/factura` y `/factura-pagos`.
- Tope por commit: <800 LOC. Cada cluster T1..T8 cabe en ≤800 LOC net (T1 ~170, T2 ~480, T3 ~270, T4 ~300, T5 ~150 added this cluster, T6 ~160, T7 ~160, T8 ~11). T2 y T5 pueden requerir split en 2 sub-commits si exceden 800 — orquestador decide según diff real al apply.
- Mensajes conventional commit; cuerpo técnico en neutral Spanish.

## Acceptance Gates

- TDD strict: RED primero, GREEN mínimo, REFACTOR último. Cluster T1 explicitly notes this discipline.
- ~30 tasks completados en orden: T1.1..T1.6 → T2.1..T2.19 → T3.1..T3.9 → T4.1..T4.6 → T5.1..T5.13 → T6.1..T6.4 → T7.1..T7.4 → T8.1..T8.2.
- Conventional commits atómicos (8 commits en 1 PR):
  - commit 1 `feat(backend): HU-F1.9 — schemas Pydantic + NIT módulo 11 helper` (~170 LOC);
  - commit 2 `feat(backend): HU-F1.9 — repo layer (factura + factura_detalle + NIT)` (~480 LOC);
  - commit 3 `feat(db): HU-F1.9 — MIGRATION 0027 one_factura_per_salida + init_pago trigger + REVOKE re-assertion` (~270 LOC);
  - commit 4 `feat(backend): HU-F1.9 — handlers POST /factura + POST /factura-pagos` (~300 LOC);
  - commit 5 `test(backend): HU-F1.9 — DB integration tests + handler unit tests + NIT módulo 11` (~150 LOC este cluster + ~1310 LOC cumulative tests files; orquestador decide split si >800);
  - commit 6 `test(backend): HU-F1.9 — AST walks KD-FACT-01 (single commit) + 12-step order` (~160 LOC);
  - commit 7 `feat(apps): HU-F1.9 — OpenAPI spec + frontend router stub` (~160 LOC);
  - commit 8 `chore(backend): HU-F1.9 — fix stale docstring drift on factura_pagos ORM` (~11 LOC).
  - Sin `Co-authored-by:`, sin trailers IA.
- Tests pasan contra DB real con `PARKOS_DOCKER_TEST=1`: 6 HTTP unit (T4.1 + T4.3 + T4.6) + 5 NIT módulo 11 (T5.1) + 4 cliente schema (T1.3 + T1.5) + 9 repo unit (T2.5 + T2.9) + 7 repo integration (T2.1 + T2.3 + T2.7 + T2.11 + T2.13 + T2.15 + T2.17) + 9 migration idempotency (T3.1 + T3.3 + T3.5 + T3.7 + T5.3 + T5.5 + T5.7) + 2 atomicidad (T5.9) + 2 voucher (T5.11) + 1 docstring drift (T8.1) + 3 OpenAPI (T7.1) + 2 frontend router (T7.3) + 2 AST walks (T6.2 + T6.4) = **~53 tests nuevos en 16 archivos**.
- ruff + mypy --strict clean sobre los 10 archivos nuevos/modificados (3 NEW `repo/*.py` + 1 NEW migration + 1 NEW `api/v1/facturacion.py` + 2 MODIFIED schemas + 1 MODIFIED `models/A/factura_pagos.py` + 1 NEW `apps/facturacion/router.py` + 1 NEW `apps/facturacion/openapi.yaml` + 11 NEW tests + 2 NEW AST walks).
- 5 CI gates verdes (matches F1.7): `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.8`.
- 0 regresiones introducidas por F1.9; las fallas preexistentes documentadas en baseline F1.8 se mantienen sin nuevos archivos fallando.
- REQ-OPS-053..063 + REQ-OPS-XR1..XR3 traceability verificada: cada REQ tiene ≥1 RED test que la prueba (T1.3 + T1.5 + T2.1..T2.18 + T3.1..T3.8 + T4.1..T4.6 mapping).
- Threat matrix §10 verificada: T1 concurrent cajeros race → 5-layer defense (partial unique index + BEFORE INSERT trigger + repo typed exception + handler 12-step + AST walks); T2 bi-temporal versioning → DEC-FACT-01 amended (no fn_facturas_inmutable); T3 pagos partitioned → BEFORE INSERT trigger analogía migration 0004; T4 bulk insert flusher OOM → `session.add_all` + single flush; T5 network blip → KD-FACT-01 single commit + atomicidad test; T6 NIT algorithm Variant A vs B → reference test `800.123.456-7`; T7 datáfono voucher missing → V7 server-side check + 400 `voucher_requerido`.
- Architecture risks §6 (R1..R7) verificadas: R1 NIT módulo 11 Variant A vs B → T1.1 reference test + T1.2 implementation; R2 `fn_facturas_inmutable` → DEC-FACT-01 amended (no trigger needed); R3 partial unique index feasibility → MIGRATION 0027 Op 2 confirmed (facturas NOT partitioned); R4 `prod.retencion`/`prod.forma_pago` → DEC-FACT-04 + DEC-FACT-07 deferred to Fase 4; R5 `uuid_cliente` not persisted → DEC-FACT-06 server-derived; R6 forma_pago validation → DEC-FACT-07 Literal Pydantic; R7 lock continuity `/factura` ↔ `/factura-pagos` → 2 separate TX + Idempotency-Key + partial unique index `one_factura_per_salida` (R3 closure).

## Out of Scope Tasks

- Numeración FE + estado DIAN (`POST /facturacion/factura-electronica`). Fase 8 (HU-F1.10); F1.9 solo persiste el lifecycle event, no la factura electrónica. DEC-FACT-05.
- Retención RETCONT 11% sobre servicios. Deferred a Fase 4 (contabilidad). `prod.retencion` NO existe en DB. DEC-FACT-04.
- Catálogo `prod.forma_pago [V]`. Deferred a Fase 4. DEC-FACT-07 Opción A (Pydantic Literal enforced).
- FK `prod.facturas.uuid_cliente`. Deferred (4FN compliance + Fase 4 ownership). DEC-FACT-06 (server-derived).
- Anulación de factura (`emitida → anulada`). Deferred a HU-F1.13 (Arqueo) via `prod.anulaciones(tipo_anulable='factura')` workflow — Fase 7+. DEC-FACT-01.
- `GET /api/v1/facturacion/facturas/{uuid}` adjacent read. Out of F1.9 scope; lower priority.
- `GET /api/v1/facturacion/facturas?uuid_cliente=...` paginated list. Out of F1.9 scope; lower priority.
- Auto-creación de cliente en V2. F1.9 returns 404 `cliente_no_encontrado`; caller decides whether to POST `/clientes` first.
- Asignación de `prefijo` + `consecutivo` a `prod.facturas`. DEC-FACT-05. F1.10 owns.
- Cleanup of client-side derivation logic in `web_sucursal/src/lib/validation/factura.ts`. Fase 2 frontend — post-archive cleanup.
- `/factura` Idempotency-Key handling. DEC-IDEM-01 reuse from F1.6 (header-based dedup; no body-level `correlacion_id`).
- `/api/v1/facturacion/factura-electronica/{uuid}/reintentar`. F1.10 (reintento DIAN).
- Multi-payment with several `pagos` lines (REQ-NFR-16). F2.x; F1.9 supports exactly ONE initial `pago` per factura (Step 10c).
- Auto-creación de clientes en cascada. F2.x (with auto-NIT-DV validation).
- Factura reversión/anulación workflow. F1.13 (Arqueo) via `repo/factura_pagos.py::reverse_payment` (existing, reused verbatim).
- POS terminal integration (proto). F4.x (WebSocket datáfono integration).
- Withholding retention at invoice-time. F4.x (ReteFuente/ReteICA).
- IGV/ReteFuente/ReteICA taxes. F3.x (F1.9 snapshots IVA only).
- Multi-line receipts (combining salidas + reservas). F3.x.
- Factura electrónica XML/PDF generation. F2.x.

## References

- `openspec/changes/hu-f1-9-facturacion/exploration.md` (~32KB, 16 sections, R1..R7) — pre-apply verification findings.
- `openspec/changes/hu-f1-9-facturacion/proposal.md` (~1432 lines, 12 sections, DEC-FACT-01..09 + DEC-FACT-10..11, KD-FACT-01..02 + KD-NIT-01..07, 5-layer defense, 10 acceptance tests T1..T10).
- `openspec/changes/hu-f1-9-facturacion/specs/operations/spec.md` (~440 LOC, REQ-OPS-053..063 + REQ-OPS-XR1..XR3, ~35 escenarios) — operational requirements.
- `openspec/changes/hu-f1-9-facturacion/design.md` (~2780 LOC, 16 sections) — architecture + migration details + AST walks + 14 tests.
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/tasks.md` (~600 LOC, 22 atomic tasks across 8 phases) — **canonical precedent** for F1.9 structure.
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/verify-report.md` — F1.7 verify (D0+D1+D8 lessons learned).
- `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/tasks.md` — F1.8 tasks (PL/pgSQL VOLATILE + lock FOR SHARE pattern, commit `a3d0c39`).
- `openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/tasks.md` — F1.6 tasks (KD-FORZADO-01 pattern, commit `2a2cbd2`).
- `modelo_datos_er.mmd` — `prod.facturas` 667-687 `[L-E]` (bi-temporal, NOT partitioned), `prod.factura_detalle` 780-794 `[A]`, `prod.factura_pagos` 843-861 `[A]` (RANGE partitioned by `fecha_retencion_hasta`), `prod.factura_impuestos` 801-822 `[A]`, `prod.factura_electronica` 689-705 `[L-E]`, `prod.clientes` 449-472 `[V]`, `prod.impuestos` 187-207 `[V]`, `prod.tarifas_sucursal` 406-426 `[V]`, `prod.salidas` 761-777 `[A]`, `prod.ingreso` 577-596 `[L-E]`.
- `backend/packages/parkos_core/src/parkos_core/models/L_E/facturas.py` (lines 62-72: `__table_args__` confirmed no `postgresql_partition_by` — partial unique index `one_factura_per_salida` IS feasible).
- `backend/packages/parkos_core/src/parkos_core/models/A/factura_pagos.py` (lines 9-18: pre-existing docstring drift TODO — references `0004_add_factura_pagos_reverso_index.py` instead of `0004_add_factura_pagos_reverso_trigger.py`).
- `backend/packages/parkos_core/src/parkos_core/repo/impuestos.py::validar_iva_configurado` (F1.7 helper, REUSED VERBATIM en F1.9 V3).
- `backend/packages/parkos_core/src/parkos_core/repo/factura_pagos.py` (existing, `reverse_payment` helper for F1.13 — REUSED VERBATIM, NOT modified).
- `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` (`no_store_headers` + `apply_no_store_header` F1.6 R-A6 helpers).
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (F1.7 12-step handler chain precedent — `create_salida` lines 296-510, F1.7 commit `c320d0f`).
- `backend/packages/parkos_core/migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py` (F1.7 migration, pre-flight pattern + partial unique index `one_exit_per_ingreso` — chain head for MIGRATION 0027).
- `backend/packages/parkos_core/migrations/versions/0004_add_factura_pagos_reverso_trigger.py` (lines 35-66 — BEFORE INSERT trigger pattern analogía for `fn_factura_pagos_init_pago_uniqueness`; lines 68-78 — REVOKE re-assertion pattern analogía for Op 4).
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (lines 435-452 `clientes`, 607-654 `facturas`+`factura_detalle` (NOT partitioned), 688-717 `factura_pagos` (RANGE partitioned), 1378 `fk_facturas_uuid_salida`, 2024-2088 `fn_*_inmutable` triggers).
- `openspec/specs/operations/spec.md` — agrega REQ-OPS-053..063 (11 requirements nuevos) + REQ-OPS-XR1..XR3 (3 cross-cutting) + entrada en `## Modified Capabilities`. Sin cambio sobre REQ-OPS-001..052.
- `plan.md` lines 891-935 — HU-F1.9 budget (330 LOC).
- `plan.md` line 7672 — CU-04 closure context.
- `plan.md` lines 2630-2637 — table impact table (`facturas` F1.9, `factura_detalle` F1.9, `factura_impuestos` F1.9, `factura_pagos` F1.9, `clientes` F1.9, `salidas` F1.7 + F1.9).
- `plan.md` lines 2403-2407 — endpoint table (`/facturacion/factura`, `/facturacion/factura-pagos` both closed in HU-F1.9; `/facturacion/factura-electronica` closed in HU-F1.10).
- `plan.md` line 2527 — F1.9 success criteria checkpoint.
- DIAN Resolución 000175 de 2021, Anexo Técnico de Facturación Electrónica, Numeral 11.1 — NIT módulo 11 algoritmo Variant A canónica (source for `MOD11_WEIGHTS`).
- PostgreSQL 15 documentation, Chapter 5.4 (Constraints) — partial unique index on partitioned tables limitation.
- PostgreSQL 15 documentation, Chapter 38 (Triggers) — BEFORE INSERT trigger pattern.
- SQLAlchemy 2.0 documentation — `with_for_update(read=True)` for `FOR SHARE` semantics in async sessions.
- Pydantic v2 documentation — `@field_validator` + `extra='forbid'` patterns.
