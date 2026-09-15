# Tasks: HU-F1.11 — Workflow reimpresión tiquete (crear + anular) + GAP-BE-04 cierre

> **Change**: `hu-f1-11-reimpresion-tiquete`
> **Phase**: tasks (sdd-tasks)
> **Status**: ready for `sdd-apply` (TDD-strict RED→GREEN→REFACTOR)
> **HU ID**: HU-F1.11 (Fase-1 prerequisites — backend)
> **Inputs**:
> - `openspec/changes/hu-f1-11-reimpresion-tiquete/design.md` (16 sections + 2 appendices, 2026-09-15, ~2450 LOC, 8 DECs + 2 KDs + MIGRATION 0029 SQL + 19 tests across 7 files + 2 AST walks)
> - `openspec/changes/hu-f1-11-reimpresion-tiquete/specs/operations/spec.md` (367 LOC, 7 REQ-OPS-075..080 + REQ-OPS-XR4)
> - `openspec/changes/hu-f1-11-reimpresion-tiquete/proposal.md` (~480 LOC, 16 sections, DEC-TKT-01..06)
> - `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/tasks.md` (canonical precedent — 8 clusters T1..T8, 31 atomic tasks)
> - `plan.md` lines 983-1006 (HU-F1.11 plan, 3 atomic tasks, 170 LOC budget) + line 7342 (GAP-BE-04 mandate)
> - `modelo_datos_er.mmd` lines 230-244 (`prod.costos_servicios` [V]) + 598-620 (`prod.reimpresion_ticket` [L-W])
> - `migrations/versions/0001_initial_schema.py` lines 297-309 (costos_servicios) + 893-910 (reimpresion_ticket) + 1690-1692 (FK) + 3292 (reimprimir_ticket permission seed)
> - `models/L_W/reimpresion_ticket.py` (lines 29-90, WorkflowBase + self-FK)
> - `schemas/workflows.py` (lines 50-132, existing `ReimpresionTicket*` schemas)
> - `api/v1/workflows.py` lines 73-78 (GAP-BE-04 site: line 74 carries `"emitir_reimpresion"`) + lines 111-118 (factory mount)
> - `repo/workflow.py` lines 66-72 (state machine) + lines 110-237 (`append_transition`) + lines 240-348 (`read_chain_tip`)
> - `sync/catalog/entries/sync_entries_lw.py` lines 27-40 (`reimpresion_ticket` sync catalog, already correct, NO change)
> - `tests/static/test_no_raw_dml_on_lw_tables.py` (F1.5 PR5-016 AST walk precedent)
>
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `340197e`) · **PR target**: `origin/dev`.
> **TDD discipline**: RED→GREEN→REFACTOR per cluster. Each commit <800 LOC. Each cluster ends with all tests PASS.
> **Atomic commit strategy**: 8 atomic commits expected (1 per cluster T1..T8).
> **Skills loaded**: `gentle-sdd-tasks` + `sdd-phase-common.md` (paths injected via orchestrator).

---

## Review Workload Forecast

| Field | Value |
|---|---|
| Total estimated changed lines | ~860 across 1 PR (~250 LOC MIGRATION 0029 + ~80 LOC NEW repo module + ~30 LOC NEW/extended schemas + ~60 LOC NEW handler module + 1 LOC GAP-BE-04 fix + ~80 LOC NEW router wire + ~330 LOC tests across 7 files + ~80 LOC 2 AST walks) |
| Total tasks | ~31 (8 clusters: T1 setup 2 tasks + T2 repo 5 + T3 schemas 4 + T4 handlers 6 + T5 GAP-BE-04 + router 3 + T6 migration 4 + T7 AST walks 4 + T8 regression 3) |
| Review budget applied | 400 lines/PR (vigente en `openspec/config.yaml`) |
| 400-line budget risk | **Medium** — F1.11 is comparable to F1.10 (~860 LOC). Cohesive single-resource (2 handlers on `reimpresion-ticket` + 1 conditional migration + 1 line fix); 8-commit split (one per cluster T1..T8) keeps each commit under the `commitlint` 800-LOC ceiling. |
| Chained PRs recommended | No — one single PR (matches F1.7 + F1.9 + F1.10 precedent); defense in depth is verified in-place. |
| Chain strategy | n/a (single PR; orchestrator cached `auto-chain`) |
| Suggested split | Single PR: `feat/fase-1-prerequisites-backend` → `origin/dev`. 8 commits internally, one per cluster T1..T8 (T1 ~30, T2 ~160, T3 ~60, T4 ~280, T5 ~40, T6 ~280, T7 ~120, T8 ~50). |
| Delivery strategy | `auto-chain` (cached) |
| `size:exception` required? | No — cohesive single-resource + 8-commit split keeps budget risk Medium inside the F1.7/F1.9/F1.10 precedent. |

| Cluster | Tasks | LOC est. impl | LOC est. tests | Cumulative LOC |
|---------|-------|---------------|----------------|----------------|
| T1 Setup + repo module skeleton | T1.1..T1.2 | ~10 LOC (module skeleton + `__all__`) | ~20 LOC (1 RED test) | 30 |
| T2 Repo layer + 5 typed exceptions | T2.1..T2.5 | ~80 LOC (6 helpers + 5 exceptions + idempotency wrapper) | ~80 LOC (6 RED tests) | 190 |
| T3 Pydantic v2 schemas + 5 typed errors | T3.1..T3.4 | ~30 LOC (3 endpoint schemas + 5 error schemas) | ~30 LOC (3 RED tests) | 250 |
| T4 Handler layer (2 POST endpoints + KD-3 issuer) | T4.1..T4.6 | ~120 LOC (2 handlers + issuer deps) | ~160 LOC (10 RED tests across 2 files) | 530 |
| T5 GAP-BE-04 fix + router wiring | T5.1..T5.3 | ~20 LOC (router wire) + 1 LOC GAP-BE-04 fix | ~20 LOC (3 RED tests) | 570 |
| T6 MIGRATION 0029 (4 ops + downgrade) | T6.1..T6.4 | ~250 LOC (4 ops + downgrade + pre-flight) | ~30 LOC (4 RED tests) | 850 |
| T7 AST walks (no-UPDATE + single-commit, 2 files × 2 tests) | T7.1..T7.4 | n/a (walks only) | ~80 LOC (4 AST walks) | 930 |
| T8 Final integration + CI-gate regression sweep | T8.1..T8.3 | n/a (sweep) | ~50 LOC (2 integration tests + CI verification) | 980 |
| **Total** | **~31** | **~510 LOC impl** | **~470 LOC tests** | **~980 LOC cumulative workload (~860 net add)** |

> Per-commit ceiling: <800 LOC. Each cluster T1..T8 fits within the limit (T6 at ~280 is the largest at applied as MIGRATION 0029 SQL block alone ~250 LOC, well within). T2 may require split into 2 sub-commits if RED tests + helper bodies exceed 800 — orchestrator decides per real diff at apply.

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: n/a
400-line budget risk: Medium

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| T1 | Module skeleton + import surface | commit 1 | `uv run pytest backend/tests/unit/test_repo_reimpresion_ticket.py -q` | unit tests, no DB, pure import | Delete module skeleton |
| T2 | Repo helpers + 5 typed exceptions | commit 2 | `uv run pytest backend/tests/unit/test_repo_reimpresion_ticket.py -q` | unit tests with `pg_engine` mock + `PARKOS_DOCKER_TEST=1` for chain-tip SELECT FOR UPDATE | Delete new repo file |
| T3 | Pydantic v2 schemas + 5 typed errors | commit 3 | `uv run pytest backend/tests/unit/test_reimpresion_ticket_schemas.py -q` | unit tests, no DB, pure Pydantic validation | Revert schema appends |
| T4 | 2 POST handlers + KD-3 issuer | commit 4 | `uv run pytest backend/tests/unit/test_reimpresion_ticket_create_handler.py backend/tests/unit/test_reimpresion_ticket_anular_handler.py -q` | HTTP integration tests with `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-`/`admin-` fixtures + real DB via `PARKOS_DOCKER_TEST=1` | Revert handler module |
| T5 | GAP-BE-04 single-line fix + router wire | commit 5 | `uv run pytest backend/tests/integration/test_workflows_router_wiring.py -q` | HTTP integration tests + source-level regression assertion | Revert single string at `api/v1/workflows.py:74` |
| T6 | MIGRATION 0029 (4 ops + downgrade) | commit 6 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/integration/test_migration_0029_idempotent.py -q` | `pg_engine` real (testcontainers precedent F1.4); asserts on `prod.costos_servicios`, `prod.permisos`, `prod.permisos_usuario` | `alembic downgrade -1` (Op 3 reverse + Op 2 reverse + Op 1 reverse) |
| T7 | 2 AST walks (no-UPDATE + single-commit) | commit 7 | `uv run pytest backend/tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py backend/tests/static/test_workflow_handler_single_commit.py -q` | no DB; pure AST walk over `api/v1/workflows_reimpresion.py` | Delete 2 walk files |
| T8 | Final integration + CI-gate regression sweep | commit 8 | `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/ -q` | full suite verde; F1.5/F1.6/F1.7/F1.8/F1.9/F1.10 sin regresión | n/a (sweep only) |

---

## Tareas

### Cluster T1 — Setup + repo module skeleton (~10 LOC impl + ~20 LOC tests)

- [x] **T-HU-F1.11-T1.1** [RED] — Write failing import-only test asserting `parkos_core.repo.reimpresion_ticket` module exists and is importable.
  - **Tests** (pure Python, no DB, no HTTP):
    - T1: `test_repo_reimpresion_ticket_module_imports` — `from parkos_core.repo import reimpresion_ticket as repo_reimpresion` succeeds; `dir(repo_reimpresion)` includes the 6 helper names + 5 typed exception names listed in design §10.1.
  - **Patrón F1.5 PR5-016** (`test_repo_workflow.py::test_workflow_module_imports`): pure import assertion, gated by `__all__` definition.
  - **Acción**: `import` from `parkos_core.repo.reimpresion_ticket` (fails with `ModuleNotFoundError`); assert public names. — **Archivo**: `backend/tests/unit/test_repo_reimpresion_ticket.py` (nuevo, ~20 LOC, 1 test). — **Validación**: `ModuleNotFoundError: No module named 'parkos_core.repo.reimpresion_ticket'`.

- [x] **T-HU-F1.11-T1.2** [GREEN] — Author `repo/reimpresion_ticket.py` skeleton (~10 LOC) with `__future__ annotations` + `__all__` listing 11 public names (6 helpers + 5 exceptions) + module docstring documenting DEC-TKT-01..05 + KD-TKT-01..02 references.
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/reimpresion_ticket.py` (nuevo).
  - **Contenido**: `from __future__ import annotations`; module docstring quoting REQ-OPS-075..080 + REQ-OPS-XR4 from `specs/operations/spec.md`; `__all__ = ["IngresoNoEncontradoError", "ReimpresionNotFoundError", "ReimpresionAlreadyPendingError", "AnulacionNoPermitidaError", "CostoServicioNoConfiguradoError", "buscar_ingreso_por_uuid", "buscar_reimpresion_por_uuid", "buscar_reimpresion_activa_por_ingreso", "buscar_factura_por_uuid", "buscar_costo_servicio_vigente_por_concepto", "check_idempotency_key"]`.
  - **Acción**: create module + populate `__all__`; no helper bodies yet (added in T2). — **Validación**: T1.1 test PASS (imports + `dir()` contains expected names).

  **Commit suggestion**: `feat(backend): HU-F1.11 — repo module skeleton + import surface`.

  **Exit criteria T1**: T1.1..T1.2 verde; ~30 LOC cumulative.

### Cluster T2 — Repo layer + 5 typed exceptions + idempotency wrapper (~80 LOC impl + ~80 LOC tests)

- [x] **T-HU-F1.11-T2.1** [RED] — Write failing tests for V1 helpers (`buscar_ingreso_por_uuid`, `buscar_reimpresion_por_uuid`, `buscar_factura_por_uuid`) — REQ-OPS-075 V1, REQ-OPS-077 V1, REQ-OPS-080 V3 (DEC-TKT-04).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`, mirror design §10.1):
    - T1: `test_buscar_ingreso_por_uuid_returns_orm_row_when_found` — seed `prod.ingreso(uuid=:i, uuid_sucursal=:s)`; `await buscar_ingreso_por_uuid(session, uuid_ingreso=:i)` returns the row.
    - T2: `test_buscar_ingreso_por_uuid_returns_none_when_not_found` — random UUID returns `None`.
    - T3: `test_buscar_reimpresion_por_uuid_returns_orm_row_when_found` — seed `prod.reimpresion_ticket(uuid=:r, ...)`; returns the row.
    - T4: `test_buscar_factura_por_uuid_returns_orm_row_when_found` — seed `prod.facturas(uuid=:f, ...)` (F1.9 fixture); returns the row.
  - **Patrón F1.5 / F1.10**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; seed via SQL directo al engine; pure ORM lookups.
  - **Acción**: imports from `parkos_core.repo.reimpresion_ticket` (fails with `ImportError` for undeclared names). — **Archivo**: extend T1.1 file (`backend/tests/unit/test_repo_reimpresion_ticket.py`) with +~40 LOC, 4 tests. — **Validación**: `ImportError: cannot import name 'buscar_ingreso_por_uuid'`.

- [x] **T-HU-F1.11-T2.2** [RED] — Write failing tests for V2 chain-tip guard (`buscar_reimpresion_activa_por_ingreso` with `with_for_update()`) + DEC-TKT-02 + KD-TKT-02 SELECT FOR UPDATE pattern.
  - **Tests**:
    - T1: `test_buscar_reimpresion_activa_por_ingreso_returns_dict_when_found` — seed `prod.reimpresion_ticket(uuid=:r1, uuid_ingreso=:i, vigente_hasta=NULL, estado='activo', timestamp_evento='2026-09-15T10:00:00')` + `prod.reimpresion_ticket(uuid=:r2, uuid_ingreso=:i, ...)` (later timestamp); helper returns `{uuid: :r2.uuid, ...}` (latest by `(max(timestamp_evento), lex(uuid))` tie-break).
    - T2: `test_buscar_reimpresion_activa_por_ingreso_returns_none_when_no_active` — no vigente rows; returns `None`.
    - T3: `test_buscar_reimpresion_activa_por_ingreso_uses_for_update` — verify query contains `.with_for_update()` (call into `repo_workflow._now_naive` analog or trace via SQL log).
  - **Acción**: extend T1.1 file with +~30 LOC, 3 tests. — **Validación**: `ImportError`.

- [x] **T-HU-F1.11-T2.3** [GREEN] — Author 3 V1 helpers + 1 V2 helper + 5 typed exceptions in `repo/reimpresion_ticket.py` (~70 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/reimpresion_ticket.py` (modified, T1.2 skeleton replaced).
  - **Contenido**:
    - 5 typed exceptions (mirror design §10.1 lines 1160-1202): `IngresoNoEncontradoError` (V1 404), `ReimpresionNotFoundError` (V1 404 anulacion), `ReimpresionAlreadyPendingError` (V2 409), `AnulacionNoPermitidaError` (V2 409 anulacion terminal), `CostoServicioNoConfiguradoError` (DEC-TKT-05 runtime 409). Each carries typed dataclass-style attributes (`uuid_ingreso`, `uuid_reimpresion`, `estado_actual`, `concepto`) and a `__str__` for logging.
    - 4 helpers (mirror design §10.1 lines 1205-1306): `buscar_ingreso_por_uuid(session, *, uuid_ingreso)` — `await session.get(Ingreso, uuid_ingreso)` with runtime import (F1.5 circular-import mitigation). `buscar_factura_por_uuid(session, *, uuid_factura)` — `await session.get(Facturas, uuid_factura)`. `buscar_reimpresion_por_uuid(session, *, uuid)` — `await session.get(ReimpresionTicket, uuid)`. `buscar_reimpresion_activa_por_ingreso(session, *, uuid_ingreso)` — `select(...).where(uuid_ingreso==X, vigente_hasta.is_(None), estado=='activo').order_by(timestamp_evento.desc(), uuid.desc()).limit(1).with_for_update()` returns `{uuid, timestamp_evento, workflow_estado}` dict or `None`.
  - **Acción**: docstring REQ-OPS-075 V1 + REQ-OPS-077 V1 + REQ-OPS-080 V3 + DEC-TKT-02; imports `from ..models.A.ingreso import Ingreso`, `from ..models.L_E.facturas import Facturas`, `from ..models.L_W.reimpresion_ticket import ReimpresionTicket`, `from sqlalchemy import select`; module does NOT call `session.commit()` (KD-TKT-01). — **Validación**: T2.1 4 tests PASS + T2.2 3 tests PASS.

- [x] **T-HU-F1.11-T2.4** [RED + GREEN] — Write failing test for `buscar_costo_servicio_vigente_por_concepto` (DEC-TKT-05 runtime defensive check) + `check_idempotency_key` (DEC-IDEM-01 F1.6 reuse wrapper); implement both (~30 LOC).
  - **Tests**:
    - T1: `test_buscar_costo_servicio_vigente_por_concepto_returns_vigent_row` — seed `prod.costos_servicios(uuid=:c, concepto='reimpresion', vigente_hasta=NULL, estado='activo')`; helper returns the row.
    - T2: `test_buscar_costo_servicio_vigente_por_concepto_returns_none_when_no_vigent` — no vigente row for `concepto='reimpresion'`; returns `None`.
    - T3: `test_check_idempotency_key_returns_cached_response_when_key_present` — invoke with pre-seeded `prod.idempotency_keys(key=K, endpoint=E, cached_response=...)`; returns the cached dict.
    - T4: `test_check_idempotency_key_returns_none_when_key_absent` — random key; returns `None`.
  - **Acción**: extend T1.1 file with +~30 LOC, 4 tests. — **Validación**: pre-implementation, `ImportError`.
  - **GREEN content**:
    - `buscar_costo_servicio_vigente_por_concepto(session, *, concepto)` — `select(CostosServicios).where(concepto==X, vigente_hasta.is_(None), estado=='activo').order_by(vigente_desde.desc()).limit(1)` returns ORM row or `None`.
    - `check_idempotency_key(session, *, idempotency_key, endpoint)` — `select(IdempotencyKey).where(key==X, endpoint==E, vigente_hasta.is_(None))` returns dict `{cached_response, created_at}` or `None`. Reuses `prod.idempotency_keys` table from F1.6 T-PR6-002 (mirror).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/reimpresion_ticket.py` (extended, +~30 LOC). — **Validación**: 4 new tests PASS; total T2.1..T2.4 = 11 tests verde.

- [x] **T-HU-F1.11-T2.5** [REFACTOR] — Extract `validate_motivo_length(value: str, *, field_name: str)` shared helper used by both create + anular handlers (≥10 chars, ≤500 chars).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/repo/reimpresion_ticket.py` (appended, +~15 LOC).
  - **Contenido**: `def validate_motivo_length(value: str, *, field_name: str) -> str` — checks `10 <= len(value) <= 500` else raises `ValueError(f"{field_name}_fuera_de_rango: {len(value)} chars")`. Pydantic enforces this via `StringConstraints` at the schema layer (T3); the repo helper is the defense-in-depth runtime check (Layer 5).
  - **Acción**: add helper + update `__all__` to include `"validate_motivo_length"`. — **Validación**: no test regression; T2.1..T2.4 11 tests PASS.

  **Commit suggestion**: `feat(backend): HU-F1.11 — repo layer (6 helpers + 5 typed exceptions + idempotency wrapper)`.

  **Exit criteria T2**: T2.1..T2.5 verde; ~190 LOC cumulative (impl + tests).

### Cluster T3 — Pydantic v2 endpoint schemas + 5 typed error schemas (~30 LOC impl + ~30 LOC tests)

- [x] **T-HU-F1.11-T3.1** [RED] — Write failing tests for `ReimpresionTicketCreateEndpoint` + `ReimpresionTicketAnularEndpoint` schemas (`extra='forbid'` + `StringConstraints(min_length=10, max_length=500)`).
  - **Tests** (pure Pydantic validation, no HTTP, no DB):
    - T1: `test_create_endpoint_rejects_motivo_below_10_chars` — `ReimpresionTicketCreateEndpoint(motivo="abc", uuid_ingreso=uuid.uuid4())` raises `ValidationError` with field `motivo`.
    - T2: `test_create_endpoint_accepts_motivo_at_min_length_10` — `motivo="1234567890"` (10 chars) succeeds.
    - T3: `test_create_endpoint_rejects_estado_injection_via_extra_forbid` — `ReimpresionTicketCreateEndpoint(motivo="...", uuid_ingreso=..., estado="autorizada")` raises `ValidationError` (extra='forbid').
    - T4: `test_create_endpoint_accepts_uuid_factura_null` — `uuid_factura=None` succeeds (DEC-TKT-04).
    - T5: `test_anular_endpoint_rejects_motivo_anulacion_below_10_chars` — `ReimpresionTicketAnularEndpoint(motivo_anulacion="abc")` raises `ValidationError`.
    - T6: `test_anular_endpoint_rejects_state_injection_via_extra_forbid` — `motivo_anulacion="...", estado="rechazada"` raises `ValidationError`.
  - **Patrón F1.10 / F1.7**: pure Pydantic tests, sin HTTP, sin DB.
  - **Acción**: imports from `parkos_core.schemas.workflows` (fails with `ImportError`). — **Archivo**: `backend/tests/unit/test_reimpresion_ticket_schemas.py` (nuevo, ~50 LOC, 6 tests). — **Validación**: `ImportError: cannot import name 'ReimpresionTicketCreateEndpoint'`.

- [x] **T-HU-F1.11-T3.2** [GREEN] — Append 2 endpoint schemas + extend `ReimpresionTicketRead` schema with `motivo_anulacion` + `workflow_estado` (~25 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` (modificado, append post-line 132).
  - **Contenido**:
    - `class ReimpresionTicketCreateEndpoint(_Base)`: docstring REQ-OPS-075 + DEC-TKT-04; `motivo: Annotated[str, StringConstraints(min_length=10, max_length=500)]`; `uuid_ingreso: uuid_lib.UUID`; `uuid_factura: uuid_lib.UUID | None = None`. `extra='forbid'` inherited from `_Base`.
    - `class ReimpresionTicketAnularEndpoint(_Base)`: docstring REQ-OPS-077; `motivo_anulacion: Annotated[str, StringConstraints(min_length=10, max_length=500)]`. `extra='forbid'` inherited.
    - Extend existing `ReimpresionTicketRead` (line 54): add `motivo_anulacion: Annotated[str, StringConstraints(max_length=500)] | None = None` + `workflow_estado: Literal["solicitada", "autorizada", "ejecutada", "rechazada"] | None = None` (server-derived per DEC-TKT-02 clarifying note).
  - **Acción**: append schemas; update `__all__`. — **Validación**: T3.1 6 tests PASS.

- [x] **T-HU-F1.11-T3.3** [RED] — Write failing tests for 5 typed error schemas (`Literal` discriminator matches handler status codes).
  - **Tests**:
    - T1: `test_reimpresion_already_pending_error_discriminator_literal` — `ReimpresionAlreadyPendingError.model_validate({"error": "reimpresion_already_pending", "uuid_ingreso": "...", "uuid_reimpresion": "..."})` succeeds; `error == Literal["reimpresion_already_pending"]` enforced.
    - T2: `test_anulacion_no_permitida_error_estado_actual_literal` — `estado_actual` is `Literal["rechazada"]` enforced.
    - T3: `test_reimpresion_not_found_error_minimal` — only `error` + `uuid_reimpresion` required.
    - T4: `test_ingreso_no_encontrado_error_minimal` — only `error` + `uuid_ingreso` required.
    - T5: `test_factura_no_encontrada_reimpresion_error_minimal` — only `error` + `uuid_factura` required.
  - **Patrón F1.10** (`test_fe_schemas.py::test_typed_error_schemas`): pure Pydantic tests.
  - **Acción**: extend T3.1 file (`backend/tests/unit/test_reimpresion_ticket_schemas.py`) with +~25 LOC, 5 tests. — **Validación**: `ImportError`.

- [x] **T-HU-F1.11-T3.4** [GREEN] — Append 5 typed error schemas (~15 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` (extended, +~15 LOC).
  - **Contenido**:
    - `class ReimpresionAlreadyPendingError(_Base)`: `error: Literal["reimpresion_already_pending"]`; `uuid_ingreso: str`; `uuid_reimpresion: str`.
    - `class AnulacionNoPermitidaError(_Base)`: `error: Literal["anulacion_no_permitida"]`; `uuid_reimpresion: str`; `estado_actual: Literal["rechazada"]`.
    - `class ReimpresionNotFoundError(_Base)`: `error: Literal["reimpresion_not_found"]`; `uuid_reimpresion: str`.
    - `class IngresoNoEncontradoError(_Base)`: `error: Literal["ingreso_no_encontrado"]`; `uuid_ingreso: str`.
    - `class FacturaNoEncontradaReimpresionError(_Base)`: `error: Literal["factura_no_encontrada"]`; `uuid_factura: str`.
  - **Acción**: append 5 classes + update `__all__`. — **Validación**: T3.3 5 tests PASS; total T3 = 11 tests verde.

  **Commit suggestion**: `feat(backend): HU-F1.11 — Pydantic schemas (2 endpoint + 5 typed error + Read extension)`.

  **Exit criteria T3**: T3.1..T3.4 verde; ~250 LOC cumulative (impl + tests).

### Cluster T4 — Handler layer (2 POST endpoints + KD-3 issuer + Cache-Control no-store, ~120 LOC impl + ~160 LOC tests)

- [x] **T-HU-F1.11-T4.1** [RED] — Write failing HTTP tests for `POST /api/v1/workflows/reimpresion-ticket` happy path + all V1..V5 error paths (REQ-OPS-075 Scenarios 1, 2, 3, 4 + DEC-TKT-04).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_create_reimpresion_happy_path_uuid_ingreso_only` — seed `prod.ingreso(uuid=:i, uuid_sucursal=:s)`; POST `{"motivo":"Cliente solicita reimpresion por deterioro del original", "uuid_ingreso":":i", "uuid_factura":null}` with `operador-X` JWT → 201 + `ReimpresionTicketRead{uuid:<new>, workflow_estado:'autorizada', uuid_reimpresion_padre:null, motivo:'...', uuid_factura:null, ...}` + `Cache-Control: no-store` header. Verify exactly 1 `prod.reimpresion_ticket` row exists in DB.
    - T2: `test_create_reimpresion_happy_path_with_uuid_factura_populated` — seed `prod.ingreso(:i)` + `prod.facturas(:f)`; POST with `uuid_factura=':f'` → 201 + `uuid_factura=':f'` populated (DEC-TKT-04).
    - T3: `test_create_reimpresion_returns_404_ingreso_no_encontrado` — POST with non-existent `uuid_ingreso` → 404 + body `{"error":"ingreso_no_encontrado","uuid_ingreso":"..."}` + `Cache-Control: no-store`. No INSERT.
    - T4: `test_create_reimpresion_returns_409_reimpresion_already_pending` — pre-seed `prod.reimpresion_ticket(:r, uuid_ingreso=:i, vigente_hasta=NULL, estado='activo')`; POST → 409 + body `{"error":"reimpresion_already_pending","uuid_ingreso":":i","uuid_reimpresion":":r.uuid"}`. No new INSERT.
    - T5: `test_create_reimpresion_returns_404_factura_no_encontrada_when_uuid_factura_provided` — POST with non-existent `uuid_factura` → 404 + body `{"error":"factura_no_encontrada","uuid_factura":"..."}`.
    - T6: `test_create_reimpresion_returns_403_tenant_scope_violation` — ctx from branch A, ingreso from branch B → 403 + `{"error":"tenant_scope_violation","uuid_ingreso":":i"}`. (KD-S2 analog from F1.7.)
    - T7: `test_create_reimpresion_returns_422_motivo_below_10_chars` — POST with `motivo="abc"` (3 chars) → 422 + `Cache-Control: no-store` (Pydantic rejects before handler body).
  - **Patrón F1.10** (`test_factura_electronica_create_handler.py`): `httpx.AsyncClient + ASGITransport(app)` + JWT `operador-X` fixture; real `pg_engine` con `PARKOS_DOCKER_TEST=1`.
  - **Acción**: imports `ReimpresionTicketCreateEndpoint`, `ReimpresionTicketRead` from `parkos_core.schemas.workflows`. — **Archivo**: `backend/tests/unit/test_reimpresion_ticket_create_handler.py` (nuevo, ~80 LOC, 7 tests). — **Validación**: 404 (route not registered).

- [x] **T-HU-F1.11-T4.2** [GREEN] — Author `api/v1/workflows_reimpresion.py` (~100 LOC) with `_create_reimpresion_ticket` 8-step chain (KD-3 issuer → V1 ingreso exists → V3 tenant scope post-V1 → V2 chain-tip guard → V5 optional factura exists → V6 KD-TKT-01 INSERT via `append_transition` → V7 single `await session.commit()` → V8 `Cache-Control: no-store` + response).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/workflows_reimpresion.py` (nuevo).
  - **Contenido**: paste verbatim from design §9.1 + §10.3; KD-3 issuer dep `_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` (DEC-TKT-01 application dep via canonical permission `reimprimir_ticket`); `@router.post("", response_model=ReimpresionTicketRead, status_code=201, responses={403:..., 404:..., 409:..., 422:...})`; `async def create_reimpresion_ticket(...)` body per design §9.1 lines 841-962 verbatim; `appends_transition` from `parkos_core.repo.workflow` (F1.5 PR5-016 reused); helper imports from `parkos_core.repo.reimpresion_ticket`.
  - **Acción**: paste verbatim from design §9.1; docstring REQ-OPS-075..080 + DEC-TKT-01..06 + KD-TKT-01. — **Validación**: T4.1 7 tests PASS.

- [x] **T-HU-F1.11-T4.3** [RED] — Write failing HTTP tests for `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` happy path + all V1..V3 error paths (REQ-OPS-077 Scenarios 1, 2, 3 + DEC-TKT-03).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_anular_reimpresion_happy_path` — seed chain with tip at `workflow_estado='autorizada'` (DEC-TKT-02 synthesized state); POST `/reimpresion-ticket/{uuid}/anular` with `{"motivo_anulacion":"Error operativo: reimprimir solicitada por error administrativo"}` + `operador-X` JWT (with `anular_reimpresion` permission granted via MIGRATION 0029 Op 3) → 201 + `ReimpresionTicketRead{uuid:<new>, workflow_estado:'rechazada', uuid_reimpresion_padre:"<tip.uuid>", motivo_anulacion:"..."}` + `Cache-Control: no-store`. Verify chain grew by 1 row; ORIGINAL tip row never updated.
    - T2: `test_anular_reimpresion_returns_409_anulacion_no_permitida` — seed chain tip already at `workflow_estado='rechazada'` (terminal); POST → 409 + body `{"error":"anulacion_no_permitida","uuid_reimpresion":"...","estado_actual":"rechazada"}`. No new INSERT.
    - T3: `test_anular_reimpresion_returns_404_reimpresion_no_encontrada` — POST with random UUID not in chain → 404 + body `{"error":"reimpresion_not_found","uuid_reimpresion":"..."}`.
    - T4: `test_anular_reimpresion_returns_403_tenant_scope_violation` — ctx from branch A, chain tip from branch B → 403 + `{"error":"tenant_scope_violation","uuid_reimpresion":"..."}`.
    - T5: `test_anular_reimpresion_returns_403_without_anular_reimpresion_permission` — operador role WITHOUT `anular_reimpresion` permission (despite having `reimprimir_ticket`) → 403 (per DEC-TKT-06 separate permission gate).
    - T6: `test_anular_reimpresion_returns_422_motivo_anulacion_below_10_chars` — POST with `motivo_anulacion="abc"` → 422 + `Cache-Control: no-store`.
  - **Patrón F1.10**: HTTP integration tests with JWT fixture + real DB.
  - **Acción**: imports `ReimpresionTicketAnularEndpoint`, `ReimpresionTicketRead`. — **Archivo**: `backend/tests/unit/test_reimpresion_ticket_anular_handler.py` (nuevo, ~80 LOC, 6 tests). — **Validación**: 404 (route not registered).

- [x] **T-HU-F1.11-T4.4** [GREEN] — Append `_anular_reimpresion_ticket` 6-step chain to `api/v1/workflows_reimpresion.py` (~80 LOC).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/workflows_reimpresion.py` (modified, append after `_create_reimpresion_ticket`, +~80 LOC).
  - **Contenido**: paste verbatim from design §9.2 lines 983-1099; KD-3 issuer dep `_anular_reimpresion_issuer_dep = requires_issuer("operador-", "admin-", permission="anular_reimpresion")` (DEC-TKT-06 separate permission gate); `@router.post("/{uuid_reimpresion}/anular", response_model=ReimpresionTicketRead, status_code=201, responses={403:..., 404:..., 409:..., 422:...})`; `async def anular_reimpresion_ticket(...)` body per design §9.2 verbatim; uses `repo.workflow.read_chain_tip` (F1.5 PR5-016 reused) at Step 2 V1.
  - **Acción**: paste verbatim from design §9.2; docstring REQ-OPS-077 + DEC-TKT-03 + KD-TKT-01. — **Validación**: T4.3 6 tests PASS.

- [x] **T-HU-F1.11-T4.5** [RED + GREEN] — Write failing HTTP tests for the `Idempotency-Key` header DEC-IDEM-01 reuse (F1.6 + F1.10 precedent) on create endpoint; implement single `Cache-Control: no-store` header helper verification on 201/404/409/422/5xx.
  - **Tests**:
    - T1: `test_create_reimpresion_idempotency_key_replay_returns_cached_response` — seed `prod.idempotency_keys(key=K, endpoint='/api/v1/workflows/reimpresion-ticket', cached_response='{"uuid": "..."}')`; POST with `Idempotency-Key: K` → 201 returning the cached response (no new INSERT, chain unchanged).
    - T2: `test_create_reimpresion_response_carries_cache_control_no_store_on_201` — happy path 201 carries `Cache-Control: no-store` header.
    - T3: `test_create_reimpresion_response_carries_cache_control_no_store_on_404` — error path 404 carries `Cache-Control: no-store` header.
    - T4: `test_create_reimpresion_response_carries_cache_control_no_store_on_409` — error path 409 carries `Cache-Control: no-store` header.
  - **Patrón F1.10** (`test_factura_electronica_router.py::test_fe_endpoint_*_carries_cache_control_no_store`): HTTP integration tests asserting header presence on every status.
  - **Acción**: extend T4.1 file (`backend/tests/unit/test_reimpresion_ticket_create_handler.py`) with +~40 LOC, 4 tests. — **Validación**: pre-implementation, headers absent.
  - **GREEN content**: confirm `no_store = no_store_headers()` at top of `create_reimpresion_ticket` (T4.2) + `apply_no_store_header(response)` before return + `headers=no_store` param on every `HTTPException` constructor (already in design §9.1).
  - **Archivo**: extend T4.1 file. — **Validación**: 4 new tests PASS; total T4 = 17 tests verde.

- [x] **T-HU-F1.11-T4.6** [REFACTOR] — Extract `_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` + `_anular_reimpresion_issuer_dep = requires_issuer("operador-", "admin-", permission="anular_reimpresion")` constants at module top (F1.10 verbatim pattern).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/workflows_reimpresion.py` (modified, top-of-file constants, no signature change).
  - **Contenido**: confirm both deps are already defined at module top (T4.2 + T4.4); verify their application in both handler signatures via `Depends()`.
  - **Acción**: read-only review + reorganization if needed; no behavior change. — **Validación**: T4.1..T4.5 17 tests PASS without regression.

  **Commit suggestion**: `feat(backend): HU-F1.11 — POST endpoints + KD-3 issuer + Cache-Control no-store`.

  **Exit criteria T4**: T4.1..T4.6 verde; ~570 LOC cumulative (impl + tests).

### Cluster T5 — GAP-BE-04 single-line fix + router wiring (~21 LOC impl + ~30 LOC tests)

- [x] **T-HU-F1.11-T5.1** [RED + GREEN] — Write failing source-level regression test asserting `api/v1/workflows.py:74` carries `"reimprimir_ticket"` and does NOT carry `"emitir_reimpresion"`; change line 74 from `"emitir_reimpresion"` to `"reimprimir_ticket"` (DEC-TKT-01 GAP-BE-04 fix, 1 LOC).
  - **Tests** (no DB, no HTTP, pure source-level assertion):
    - T1: `test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion` — read `api/v1/workflows.py` source; assert line 74 (or whichever line carries the `_ROUTER_CONFIG["reimpresion-ticket"][1]`) contains `"reimprimir_ticket"` AND does not contain `"emitir_reimpresion"`.
  - **Patrón F1.7 / F1.10**: direct file read with `Path.read_text()` + `assert` on substring presence.
  - **Acción**: source-level test reads `Path("backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py")`. — **Archivo**: `backend/tests/integration/test_workflows_router_wiring.py` (nuevo, ~30 LOC including T5.2 tests).
  - **GREEN content**: edit `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py:74` from `"emitir_reimpresion"` to `"reimprimir_ticket"` (single character sequence change; the existing factory mount at lines 111-118 automatically picks up the corrected value via `_ROUTER_CONFIG["reimpresion-ticket"][1]` lookup). — **Validación**: T1 PASS; no regression on existing `reimpresion-ticket` GET mount.

- [x] **T-HU-F1.11-T5.2** [RED + GREEN] — Write failing integration tests verifying the GAP-BE-04 fix correctness (operador with `reimprimir_ticket` succeeds; operador with only legacy `emitir_reimpresion` rejected).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_gap_be_04_reimpresion_resource_unblocked_for_operador_with_reimprimir_ticket` — operator role with `reimprimir_ticket` permission granted via `prod.permisos_usuario`; POST `/reimpresion-ticket` with happy-path body → 201 (REQ-OPS-075 Scenario 3). Pre-fix this would 403; post-fix it succeeds.
    - T2: `test_legacy_emitir_reimpresion_rejected_after_fix` — operator role with ONLY the legacy typo'd `emitir_reimpresion` permission granted (NOT `reimprimir_ticket`); POST `/reimpresion-ticket` → 403 + body containing `emitir_reimpresion_not_found` discriminator (REQ-OPS-076 Scenario 3 — proves the typo'd permission is no longer in the dependency check).
    - T3: `test_anular_reimpresion_endpoint_requires_anular_reimpresion_permission` — operator role with `reimprimir_ticket` but NOT `anular_reimpresion`; POST `/reimpresion-ticket/{uuid}/anular` → 403 (DEC-TKT-06 separate permission gate).
  - **Patrón F1.10** (`test_factura_electronica_router.py`): HTTP integration tests with parametrized JWT fixtures.
  - **Acción**: extend T5.1 file (`backend/tests/integration/test_workflows_router_wiring.py`) with +~30 LOC, 3 tests. — **Validación**: T2 fails pre-fix (passes post-fix); T3 requires MIGRATION 0029 Op 2 + Op 3 seeded (T6).

- [x] **T-HU-F1.11-T5.3** [GREEN] — Wire `workflows_reimpresion` router into `api/v1/__init__.py` (or `app.py`) via `from ..api.v1.workflows_reimpresion import router as workflows_reimpresion_router` + `app.include_router(workflows_reimpresion_router)` (DEC-TKT-06).
  - **Archivo**: `backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` (modificado, +~10 LOC).
  - **Contenido**: add import + `app.include_router(workflows_reimpresion_router)` after existing router includes.
  - **Acción**: paste router include per DEC-TKT-06; docstring REQ-OPS-075 + DEC-TKT-06. — **Validación**: T4.1..T4.5 17 tests PASS (routes registered); T5.2 3 tests PASS.

  **Commit suggestion**: `feat(backend): HU-F1.11 — GAP-BE-04 fix (emitir_reimpresion → reimprimir_ticket) + router wiring`.

  **Exit criteria T5**: T5.1..T5.3 verde; ~610 LOC cumulative (impl + tests); GAP-BE-04 reconciled.

### Cluster T6 — MIGRATION 0029 (4 ops + downgrade, ~250 LOC impl + ~50 LOC tests)

- [x] **T-HU-F1.11-T6.1** [RED] — Write failing tests for MIGRATION 0029 pre-flight `DO $$` 4-table existence check + Op 1 conditional siembra + Op 2 permission seed + Op 3 role grants.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0029_preflight_aborta_con_tabla_costos_servicios_faltante` — DROP TABLE `prod.costos_servicios` (test-only); `alembic upgrade head` raises `0029_preflight_abort: tabla prod.costos_servicios no existe`. Re-CREATE TABLE post-test cleanup.
    - T2: `test_migration_0029_op1_siembra_absent_inserts_row` — no vigente `prod.costos_servicios WHERE concepto='reimpresion'`; post-upgrade, exactly 1 row exists with `concepto='reimpresion', costo=0, tipo_calculo='fijo', vigente_hasta=NULL, estado='activo'`.
    - T3: `test_migration_0029_op2_seed_anular_reimpresion_permission` — post-upgrade, `SELECT 1 FROM prod.permisos WHERE permiso='anular_reimpresion'` returns 1 row.
    - T4: `test_migration_0029_op3_grants_anular_reimpresion_to_operador_and_admin` — pre-seed `prod.roles(nombre='operador')` + `prod.roles(nombre='admin')` + users with `uuid_rol=<role.uuid>`; post-upgrade, `prod.permisos_usuario` has rows for each `operador` and `admin` user with `uuid_permiso=<permisos.anular_reimpresion.uuid>`.
  - **Patrón F1.6 / F1.7 / F1.9 / F1.10**: `pg_engine` real con `PARKOS_DOCKER_TEST=1`; KD-7 pre-flight `DO $$` block pattern reused verbatim.
  - **Acción**: invoke `alembic upgrade head` (fails with pre-flight abort or schema not seeded). — **Archivo**: `backend/tests/integration/test_migration_0029_idempotent.py` (nuevo, ~40 LOC, 4 tests). — **Validación**: migration 0029 not yet authored.

- [x] **T-HU-F1.11-T6.2** [GREEN] — Author `migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (~250 LOC) with 4 ops + pre-flight + downgrade (REQ-OPS-079 + REQ-OPS-077 + DEC-TKT-05 + DEC-TKT-01 GAP-BE-04 note).
  - **Archivo**: `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembre_and_anular_permission.py` (nuevo).
  - **Contenido**:
    - `revision = "0029_reimpresion_siembre_and_anular_permission"`; `down_revision = "0028_one_fe_per_factura_and_chain_index_and_sync_flip"` (F1.10 chain head).
    - `from alembic import op`.
    - `def upgrade() -> None`:
      - **Op 0** — pre-flight `DO $$` block (KD-7 F1.6/F1.7/F1.9/F1.10 pattern): 4 RAISE EXCEPTION checks (`prod.costos_servicios`, `prod.permisos`, `prod.permisos_usuario`, `prod.roles` exist). Paste verbatim from design §11.2 lines 1555-1597.
      - **Op 1** — DEC-TKT-05 conditional siembra `prod.costos_servicios.concepto='reimpresion'`: `IF siembra_count = 0 THEN INSERT ... ON CONFLICT (concepto, vigente_desde) DO NOTHING`. Paste verbatim from design §11.2 lines 1606-1633.
      - **Op 2** — Seed `prod.permisos` for `'anular_reimpresion'` (mirror of `anular_ingreso_salida` F1.7 pattern): `IF NOT EXISTS THEN INSERT` with `descripcion='Anular una reimpresion de tiquete autorizada/ejecutada (HU-F1.11)'`. Paste verbatim from design §11.2 lines 1640-1661.
      - **Op 3** — Grant `'anular_reimpresion'` to `operador` and `admin` roles via `prod.permisos_usuario` (idempotent via `NOT EXISTS` subquery + JOIN on `prod.roles WHERE nombre IN ('operador', 'admin')`). Paste verbatim from design §11.2 lines 1667-1697.
    - `def downgrade() -> None`:
      - **Reverse Op 3**: `DELETE FROM prod.permisos_usuario WHERE uuid_permiso IN (SELECT uuid FROM prod.permisos WHERE permiso='anular_reimpresion')`.
      - **Reverse Op 2**: `DELETE FROM prod.permisos WHERE permiso='anular_reimpresion'`.
      - **Reverse Op 1**: `DELETE FROM prod.costos_servicios WHERE concepto='reimpresion' AND vigente_desde >= NOW() - INTERVAL '1 hour' AND vigente_hasta IS NULL AND estado='activo'` (known R8 limitation documented in design Appendix A.6).
  - **Acción**: paste verbatim from design §11.2 + Appendix A.1..A.5. — **Validación**: T6.1 4 tests PASS; `alembic upgrade head` succeeds; `alembic downgrade -1` reverses all 4 ops cleanly.

- [x] **T-HU-F1.11-T6.3** [RED] — Write failing idempotency tests (re-apply + preserves-existing) for MIGRATION 0029.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0029_idempotent_reapply` — apply 0029, downgrade -1, apply 0029 again — assert no errors, no duplicates, post-state matches pre-state (F1.10 `test_migration_0028_idempotent.py` precedent).
    - T2: `test_migration_0029_preserves_existing_siembra` — pre-insert `prod.costos_servicios(concepto='reimpresion', costo=99, tipo_calculo='variable')` (manual siembra); apply 0029; assert exactly 1 row exists for `concepto='reimpresion'` (the pre-existing one, NOT a duplicate with `costo=0`).
    - T3: `test_migration_0029_preserves_existing_permission_seed` — pre-insert `prod.permisos(permiso='anular_reimpresion', descripcion='manual')`; apply 0029; assert no duplicate (`IF NOT EXISTS` guard skips).
    - T4: `test_migration_0029_preserves_existing_role_grants` — pre-grant `anular_reimpresion` to one user; apply 0029; assert only 1 grant row exists (NOT duplicated).
  - **Patrón F1.10**: `pg_engine` real; pre-seed via SQL + `alembic upgrade head` + assertion.
  - **Acción**: extend T6.1 file (`backend/tests/integration/test_migration_0029_idempotent.py`) with +~30 LOC, 4 tests. — **Validación**: T2..T4 fail pre-implementation (duplicate rows produced).

- [x] **T-HU-F1.11-T6.4** [RED + GREEN] — Write failing downgrade cycle test (F1.10 `test_migration_0028_idempotent.py` precedent) and confirm all 3 reverse ops succeed + re-upgrade restores state.
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_migration_0029_downgrade_cycle_round_trip` — upgrade 0029 → assert all 3 writes present → downgrade -1 → assert all 3 writes absent → upgrade 0029 → assert all 3 writes present again (round trip idempotent).
  - **Patrón F1.10**: full round trip with assertion at each transition.
  - **Acción**: extend T6.1 file with +~20 LOC, 1 test. — **Validación**: round trip succeeds (may emit `RAISE NOTICE` warnings from time-window downgrade; assert they're acceptable per R8 known limitation).

  **Commit suggestion**: `feat(db): HU-F1.11 — MIGRATION 0029 siembra + anular_reimpresion permission + role grants`.

  **Exit criteria T6**: T6.1..T6.4 verde; ~860 LOC cumulative (impl + tests); MIGRATION 0029 idempotent on upgrade/downgrade/re-upgrade cycle.

### Cluster T7 — AST walks (no-UPDATE insert-only + KD-TKT-01 single-commit, 2 walk files × 2 tests, ~80 LOC tests)

- [x] **T-HU-F1.11-T7.1** [RED + GREEN] — Write failing AST walk `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` enforcing NO UPDATE on `prod.reimpresion_ticket` user-meaningful fields from `create_reimpresion_ticket` + `anular_reimpresion_ticket` bodies (DEC-TKT-02 + DEC-TKT-03 + REQ-OPS-XR4).
  - **Tests** (no DB, no HTTP, pure AST walk):
    - T1: `test_create_reimpresion_ticket_handler_no_update_on_reimpresion_ticket` — `ast.parse(handler_path)`; locate `create_reimpresion_ticket` via `ast.AsyncFunctionDef.name == 'create_reimpresion_ticket'`; walk via `iter_child_nodes`; assert NO `await session.execute(text("UPDATE reimpresion_ticket..."))` string literal; assert NO `update(ReimpresionTicket)` SQLAlchemy core call; assert exactly one INSERT path via `repo.workflow.append_transition(...)` call.
    - T2: `test_anular_reimpresion_ticket_handler_no_update_on_reimpresion_ticket` — same pattern for `anular_reimpresion_ticket` body.
  - **Patrón F1.10** (`test_fe_retry_handler_no_update_on_envio_dian.py`): `ast.parse` + `iter_child_nodes` DFS.
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` (nuevo, ~40 LOC, 2 AST walks). — **Validación**: post T4 GREEN, walks PASS (only INSERT via `append_transition`, no UPDATE).

- [x] **T-HU-F1.11-T7.2** [RED + GREEN] — Write failing AST walk `tests/static/test_workflow_handler_no_update_on_lw_tables_reimpresion.py` extending F1.5 PR5-016 precedent (`test_no_raw_dml_on_lw_tables.py`) to include `reimpresion_ticket` table grep (REQ-OPS-XR4 cross-cutting + coverage of any FUTURE handler that might raw-DML the table).
  - **Tests**:
    - T1: `test_repo_repo_layer_no_raw_dml_on_reimpresion_ticket` — grep `repo/reimpresion_ticket.py` + `api/v1/workflows_reimpresion.py` for `UPDATE prod.reimpresion_ticket` or `DELETE FROM prod.reimpresion_ticket` patterns; assert no match. Allowed patterns: `INSERT INTO prod.reimpresion_ticket` via `append_transition`, `SELECT ... FROM prod.reimpresion_ticket`.
  - **Patrón F1.5 PR5-016**: source-level grep + regex match.
  - **Acción**: import `re`, `pathlib.Path`. — **Archivo**: extend T7.1 file (`backend/tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py`) with +~20 LOC, 1 AST walk. — **Validación**: post T2 + T4 + T5 GREEN, walk PASS (no raw UPDATE/DELETE on `prod.reimpresion_ticket` from any F1.11 source file).

- [x] **T-HU-F1.11-T7.3** [RED + GREEN] — Write failing AST walk `tests/static/test_workflow_handler_single_commit.py` enforcing KD-TKT-01 single `await session.commit()` invariant for both `create_reimpresion_ticket` + `anular_reimpresion_ticket` bodies.
  - **Tests** (no DB, no HTTP, pure AST walk):
    - T1: `test_create_reimpresion_ticket_handler_invokes_session_commit_exactly_once` — `ast.parse(handler_path)`; locate `create_reimpresion_ticket`; collect commits via `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and getattr(n.value.func, "attr", "") == "commit"])`; assert `commit_count == 1`. Also assert `len([n for n in ast.walk(body) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "begin_nested"]) == 0`; assert NO `SAVEPOINT` / `RELEASE SAVEPOINT` string literals.
    - T2: `test_anular_reimpresion_ticket_handler_invokes_session_commit_exactly_once` — same pattern for `anular_reimpresion_ticket` body.
  - **Patrón F1.10** (`test_fe_handler_single_commit.py` + `test_fe_retry_handler_single_commit.py`): `ast.parse` + recursion via `iter_child_nodes`.
  - **Acción**: imports `ast`, `pathlib.Path`. — **Archivo**: `backend/tests/static/test_workflow_handler_single_commit.py` (nuevo, ~40 LOC, 2 AST walks). — **Validación**: post T4 GREEN, both walks PASS (`commit_count == 1`, no `begin_nested`, no `SAVEPOINT`).

- [x] **T-HU-F1.11-T7.4** [REFACTOR] — Extract common AST walk helpers into `tests/static/_ast_walk_helpers.py` if size warrants (mirror F1.10's helper extraction pattern); confirm both walk files import from this helper.
  - **Archivo**: optional `backend/tests/static/_ast_walk_helpers.py` (nuevo, +~20 LOC).
  - **Acción**: only if duplication becomes painful in T7.1+T7.3; otherwise document "no helper extracted" in commit message. — **Validación**: all 5 AST walks PASS (T7.1 2 + T7.2 1 + T7.3 2).

  **Commit suggestion**: `feat(static): HU-F1.11 — AST walks (insert-only no-UPDATE + KD-TKT-01 single-commit)`.

  **Exit criteria T7**: T7.1..T7.4 verde; ~930 LOC cumulative (impl + tests); 5 AST walks PASS across 2 files.

### Cluster T8 — Final integration + CI-gate regression sweep (~50 LOC tests + CI verification)

- [x] **T-HU-F1.11-T8.1** [RED + GREEN] — Write failing full-chain integration test verifying the entire `reimpresion-ticket` resource end-to-end (POST → chain-tip → POST anular → chain-tip → 409 on re-anular).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_reimpresion_full_chain_post_create_then_anular_then_reanular_returns_409` — seed `prod.ingreso(:i, uuid_sucursal=:s)` + operador with `reimprimir_ticket` + `anular_reimpresion` permissions.
      - Step 1: POST `/reimpresion-ticket` with `motivo=':motivo-1'` → 201 + `workflow_estado='autorizada'` + `uuid_reimpresion_padre=None`.
      - Step 2: Capture the new UUID as `:r1`. Verify exactly 1 `prod.reimpresion_ticket` row for `:i`.
      - Step 3: POST `/reimpresion-ticket/:r1/anular` with `motivo_anulacion=':motivo-anul-1'` → 201 + `workflow_estado='rechazada'` + `uuid_reimpresion_padre=':r1'`.
      - Step 4: Verify chain grew by 1 (2 rows total); ORIGINAL `:r1` unchanged (DEC-TKT-03 NEVER UPDATE).
      - Step 5: POST `/reimpresion-ticket/:r1/anular` AGAIN (terminal state) → 409 + body `{"error":"anulacion_no_permitida","uuid_reimpresion":":r1","estado_actual":"rechazada"}`.
      - All steps carry `Cache-Control: no-store`.
  - **Patrón F1.10** (`test_factura_electronica_handler_integration.py`): full HTTP integration test with multi-step scenario.
  - **Acción**: extend T4.1 or T4.3 file with +~30 LOC, 1 test. — **Validación**: pre-implementation, multi-step scenario fails at first step (route not registered).
  - **GREEN content**: confirm all previous clusters' tests still PASS (no regression). — **Validación**: 1 test PASS; chain integrity preserved.

- [x] **T-HU-F1.11-T8.2** [RED + GREEN] — Write failing integration test verifying existing factory-mounted `GET /workflows/reimpresion-ticket` mount is unchanged + works correctly AFTER the GAP-BE-04 fix (REQ-OPS-076 fix unblocks the entire resource, not just new POST endpoints).
  - **Tests** (gated `PARKOS_DOCKER_TEST=1`):
    - T1: `test_existing_reimpresion_resource_get_endpoint_unaffected_by_new_handlers` — pre-seed `prod.reimpresion_ticket(:r, ...)`. GET `/workflows/reimpresion-ticket` with `operador-X` JWT carrying `reimprimir_ticket` permission → 200 (PR6 T-PR6-10 behavior preserved; pre-fix this would 403). Verify response shape unchanged (existing factory C+Q schema).
  - **Patrón F1.10** (`test_factura_electronica_router.py`): HTTP integration test verifying the parent mount.
  - **Acción**: extend T5.1 file (`backend/tests/integration/test_workflows_router_wiring.py`) with +~10 LOC, 1 test. — **Validación**: pre-fix, 403; post-fix, 200.

- [x] **T-HU-F1.11-T8.3** [GREEN] — Run full regression sweep verifying F1.5/F1.6/F1.7/F1.8/F1.9/F1.10 tests still pass after F1.11 changes; verify all 5 CI gates remain green (no_regresion gate).
  - **Acciones**:
    1. Ejecutar `PARKOS_DOCKER_TEST=1 uv run pytest backend/tests/ -q` (full suite).
    2. Verify F1.10 tests still PASS: `test_factura_electronica_*`, `test_migration_0028_idempotent.py`, AST walks KD-FE-01.
    3. Verify F1.9 tests still PASS: `test_facturacion_factura.py`, `test_facturacion_factura_pagos.py`, `test_migration_0027_idempotent.py`, AST walks KD-FACT-01.
    4. Verify F1.8 tests still PASS: PL/pgSQL `calcular_cotizacion` + KD-1 FOR SHARE.
    5. Verify F1.7 tests still PASS: KD-FORZADO-01 AST walks + KD-S2 tenant scope.
    6. Verify F1.6 tests still PASS: KD-FORZADO-01 prefix contract + Idempotency-Key middleware (now used by F1.11 create endpoint).
    7. Verify F1.5 tests still PASS: MV pattern + `repo/workflow.read_chain_tip` (now used by F1.11 anular endpoint).
    8. Verify 5 CI gates verde (`factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.10`).
  - **Validación**: full suite verde; 0 regresiones introducidas por F1.11; las fallas preexistentes documentadas en baseline F1.10 se mantienen sin nuevos archivos fallando; all CI gates pass.

  **Commit suggestion**: `test(backend): HU-F1.11 — final integration + full regression sweep (all prior F1.5..F1.10 tests still pass)`.

  **Exit criteria T8**: T8.1..T8.3 verde; ~980 LOC cumulative (impl + tests).

---

## Cross-cluster constraints

- NO `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` on `prod.reimpresion_ticket` outside the 2 expected INSERTs (Step 6 create handler + Step 5 anular handler) — AST walks `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` (T7.1) + extended `tests/static/test_workflow_handler_no_update_on_lw_tables_reimpresion.py` (T7.2) enforce via DEC-TKT-02 + DEC-TKT-03 insert-only invariant.
- NO multiple `await session.commit()` or `session.begin_nested()` or `SAVEPOINT` statements in either handler body — AST walks `tests/static/test_workflow_handler_single_commit.py` (T7.3) enforce via KD-TKT-01 single-commit invariant.
- NO raw `UPDATE prod.reimpresion_ticket` on user-meaningful fields (`workflow_estado`, `motivo`, `motivo_anulacion`, `uuid_reimpresion_padre`, `uuid_ingreso`, `uuid_factura`) — the AST walks enforce. Only `vigente_hasta` MAY be UPDATEd by `WorkflowBase` superclass for bi-temporal versioning (the existing `tests/static/test_no_raw_dml_on_lw_tables.py` from F1.5 PR5-016 covers WorkflowBase; F1.11 handlers emit NO UPDATE statements at all).
- NO `Co-authored-by:` trailers AI en commits; conventional commits, neutral Spanish commit messages, neutral Spanish per-cluster rationale comments.
- NO SQLite in tests — `pg_engine` real via `testcontainers[postgres]` (F1.4/F1.5/F1.6/F1.7/F1.9/F1.10 precedent).
- NO modification of `make_router` (`api/v1/router_factory.py`) — `factory_intact` CI gate (matches F1.7/F1.9/F1.10).
- NO modification of `WorkerRunner` base (`jobs/runner.py`) — `worker_base_intact` CI gate cross-cutting.
- NO modification of `api/deps.py` nor `auth/tenancy.py` — KD-3 chain + errores tipados intactos.
- NO modification of `repo/event.py` — `event_helper_intact` CI gate (matches F1.7/F1.9/F1.10).
- NO modification of `repo/workflow.py::append_transition` — reused verbatim (F1.5 PR5-016, DEC-TKT-02).
- NO modification of `repo/workflow.py::read_chain_tip` — reused verbatim (F1.5 PR5-016, REQ-OPS-078).
- NO modification of `repo/event.py::check_idempotency_key`-related helpers — F1.6 middleware continues to handle the cache; the new `repo/reimpresion_ticket.py::check_idempotency_key` is a thin wrapper for testability (DEC-IDEM-01).
- NO modifications to existing `reimpresion_ticket` GET endpoint mounted by `make_router` at lines 111-118 — only the single-line permission fix at line 74 (DEC-TKT-01).
- NO new sync catalog entries — `sync_entries_lw.py` lines 27-40 already carry `reimpresion_ticket` with `direction='branch_to_cloud'` and `apply_strategy='append_transition'`, `parent_fk_column='uuid_reimpresion_padre'`, `depends_on=('sucursal', 'ingreso', 'usuarios', 'costos_servicios', 'facturas')` (verified pre-apply, NO change needed).
- NO new triggers — existing `reimpresion_ticket_audit_columns` + `reimpresion_ticket_set_vigente_inicial` + `reimpresion_ticket_enqueue_sync` (migration 0001 lines 2379-2390 + 2660-2672 + 2873-2880) cover the F1.11 INSERT path.
- NO `prod.forma_pago` catálogo (DEC-FACT-07) — DEC-TKT-04 uses nullable FK instead.
- NO `uuid_reimpresion_padre` column on `prod.reimpresion_ticket` is optional / client-supplied — server-set on create (NULL) and server-derived on anular (`<tip.uuid>`).
- NO `cufe` column on `prod.reimpresion_ticket` — 4NF; reimpresión has no DIAN equivalent (F1.10 owns `prod.envio_dian`).
- Header `Cache-Control: no-store` on EVERY response (2xx/4xx/5xx) of both endpoints (via `no_store_headers()` helper + `apply_no_store_header(response)` before return + `headers=no_store` param in `HTTPException` constructors) — DEC-TKT-06 XR2 mirror.
- Discriminators stable: `tenant_scope_violation` (403 operador cross-branch), `ingreso_no_encontrado` (404 V1 create), `factura_no_encontrada` (404 V3 create when provided), `reimpresion_already_pending` (409 V2 create), `anulacion_no_permitida` (409 V2 anular terminal), `reimpresion_not_found` (404 V1 anular), `missing_field` (422 Pydantic), `motivo_muy_corto` (422 Pydantic).
- Precedencia de errores: KD-3 (403 issuer) > V1 (404 ingreso_not_found) > tenant scope (403) > V2 (409 ya_existe) > V3 (404 factura_not_found) > Step 6 INSERT (single commit) > response 201.
- MIGRATION 0029 must use `IF NOT EXISTS` / `NOT EXISTS` / `ON CONFLICT DO NOTHING` everywhere (idempotent on re-apply + graceful on races).
- Per-commit ceiling: <800 LOC. Each cluster T1..T8 fits (T6 migration SQL block alone ~250 LOC, well within). T2 may split into 2 sub-commits if RED tests + helper bodies exceed 800 — orchestrator decides per real diff at apply.
- Mensajes conventional commit; cuerpo técnico en neutral Spanish.

## Acceptance Gates

- TDD strict: RED first, GREEN minimum, REFACTOR last. Cluster T1 explicitly notes this discipline.
- ~31 tasks completed in order: T1.1..T1.2 → T2.1..T2.5 → T3.1..T3.4 → T4.1..T4.6 → T5.1..T5.3 → T6.1..T6.4 → T7.1..T7.4 → T8.1..T8.3.
- Conventional commits atómicos (8 commits en 1 PR):
  - commit 1 `feat(backend): HU-F1.11 — repo module skeleton + import surface` (~30 LOC);
  - commit 2 `feat(backend): HU-F1.11 — repo layer (6 helpers + 5 typed exceptions + idempotency wrapper)` (~160 LOC);
  - commit 3 `feat(backend): HU-F1.11 — Pydantic schemas (2 endpoint + 5 typed error + Read extension)` (~60 LOC);
  - commit 4 `feat(backend): HU-F1.11 — POST endpoints + KD-3 issuer + Cache-Control no-store` (~280 LOC);
  - commit 5 `feat(backend): HU-F1.11 — GAP-BE-04 fix (emitir_reimpresion → reimprimir_ticket) + router wiring` (~40 LOC);
  - commit 6 `feat(db): HU-F1.11 — MIGRATION 0029 siembra + anular_reimpresion permission + role grants` (~280 LOC);
  - commit 7 `feat(static): HU-F1.11 — AST walks (insert-only no-UPDATE + KD-TKT-01 single-commit)` (~120 LOC);
  - commit 8 `test(backend): HU-F1.11 — final integration + full regression sweep (all prior F1.5..F1.10 tests still pass)` (~50 LOC).
  - Without `Co-authored-by:`, without AI trailers.
- Tests run against real DB with `PARKOS_DOCKER_TEST=1`: 1 module-import (T1.1) + 4 + 3 + 4 + 4 = 15 repo unit (T2.1..T2.4) + 6 + 5 = 11 schema unit (T3.1 + T3.3) + 7 create + 6 anular + 4 idempotency/cache-control = 17 handler HTTP (T4.1 + T4.3 + T4.5) + 4 migration pre-flight + 4 migration idempotency + 1 downgrade round trip = 9 migration integration (T6.1 + T6.3 + T6.4) + 1 source-level + 3 HTTP = 4 router integration (T5.1 + T5.2) + 1 full-chain + 1 GET preservation = 2 final integration (T8.1 + T8.2) + 5 AST walks (T7.1 2 + T7.2 1 + T7.3 2) = **~63 tests across 11 files** (5 unit files + 2 migration/router integration files + 1 handler-create file + 1 handler-anular file + 1 AST walk file × 2 + 1 final-integration file).
- ruff + mypy --strict clean on all 9 new/modified files (1 NEW `repo/reimpresion_ticket.py` + 1 NEW migration + 1 NEW handler module + 1 MODIFIED `api/v1/workflows.py` line 74 + 1 MODIFIED `api/v1/__init__.py` router wire + 1 MODIFIED `schemas/workflows.py` + 8 NEW tests + 2 NEW AST walks).
- 5 CI gates green (matches F1.7/F1.9/F1.10): `factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.10`.
- 0 regressions introduced by F1.11; baseline F1.10 pre-existing failures documented and unchanged.
- REQ-OPS-075..080 + REQ-OPS-XR4 traceability verified: each REQ has ≥1 RED test that proves it (mapping in Appendix B of design.md + this file's per-task rationale).
- Architecture risks §7 (R1..R10) verified: R1 GAP-BE-04 permission mismatch RESOLVED via DEC-TKT-01 (T5.1 single-line fix + regression test); R2 siembra absent → T6.1 conditional pre-flight + T6.3 re-apply idempotency; R3 chain integrity via FK → T4.3 happy path + T6.1 op verifications; R4 concurrent reimpresions on same ingreso → T2.2 KD-TKT-02 SELECT FOR UPDATE + T4.1 409 mapping; R5 tenant scope pre-V1 → T4.1 / T4.3 tenant_scope_violation tests + Step 3 post-V1 design; R6 motivo_anulacion audit → T3.1 + T3.2 Pydantic `min_length=10, max_length=500`; R7 AST walk extension → T7.1 + T7.2 new walks; R8 downgrade time-window → T6.4 + design §A.6 documented; R9 WorkflowBase UPDATE `vigente_hasta` exception → T7.1/T7.2 walks permit `vigente_hasta` originating from WorkflowBase (NOT F1.11 handlers); R10 Idempotency-Key TTL → F1.6 7-day window inherited (documented).

## Out of Scope Tasks

- Real DIAN web service integration — N/A (F1.10 owns; F1.11 reimpresion has no DIAN analogue).
- `POST /reimpresion-ticket/{uuid}/ejecutar` (state machine `autorizada → ejecutada`) — F2.x manual authorization workflow.
- PDF rendering of reimpresion tiquete — HU-F8.3 (frontend Fase 8).
- Email/SMS notification of anulación — Fase 4.
- Cool-down period enforcement beyond the V2 chain-tip guard — F2.x.
- Cost snapshotting (`prod.facturas.costo` → reimpresion row) — explicitly REJECTED per DEC-TKT-04; issuance flow decoupled from cost charging.
- `uuid_costo_servicio` FK on reimpresion row — F2.x (when cost charging is reintroduced).
- Auto-triggered reimpresion from `sync_back_events` withdrawal path — never implemented; sync catalog already correct (`branch_to_cloud`, `append_transition`).
- Multi-tenant operator scope (multi-branch operator) — F2.x.
- `vigente_hasta` bi-temporal versioning of reimpresion chains — F2.x; F1.11 chain via `uuid_reimpresion_padre` is the versioning.
- Tracker table for siembra provenance (so downgrade is precise) — F2.x; F1.11 1-hour time-window accepted (R8 known limitation).
- Modify `api/v1/workflows.py` beyond line 74 — DEC-TKT-06 factory path is reserved for C+Q only.
- ER diagram comment update for `prod.reimpresion_ticket` — separate post-archive PR for traceability (matches F1.10 docstring drift pattern).

## Commit summary (8 expected atomic commits)

| # | Cluster | Commit message | Files | LOC est. |
|---|---|---|---|---|
| 1 | T1 | `feat(backend): HU-F1.11 — repo module skeleton + import surface` | 1 NEW repo skeleton + 1 NEW test | ~30 |
| 2 | T2 | `feat(backend): HU-F1.11 — repo layer (6 helpers + 5 typed exceptions + idempotency wrapper)` | 1 MODIFIED repo + extended test file (+11 tests) | ~160 |
| 3 | T3 | `feat(backend): HU-F1.11 — Pydantic schemas (2 endpoint + 5 typed error + Read extension)` | 1 MODIFIED schemas + 1 NEW test | ~60 |
| 4 | T4 | `feat(backend): HU-F1.11 — POST endpoints + KD-3 issuer + Cache-Control no-store` | 1 NEW handler module (2 handlers + 2 issuer deps) + 2 NEW tests | ~280 |
| 5 | T5 | `feat(backend): HU-F1.11 — GAP-BE-04 fix (emitir_reimpresion → reimprimir_ticket) + router wiring` | 1 MODIFIED line 74 + 1 MODIFIED `__init__.py` + 1 NEW router integration test | ~40 |
| 6 | T6 | `feat(db): HU-F1.11 — MIGRATION 0029 siembra + anular_reimpresion permission + role grants` | 1 NEW migration + extended integration test (+9 tests) | ~280 |
| 7 | T7 | `feat(static): HU-F1.11 — AST walks (insert-only no-UPDATE + KD-TKT-01 single-commit)` | 2 NEW AST walk files (+5 walks) | ~120 |
| 8 | T8 | `test(backend): HU-F1.11 — final integration + full regression sweep (all prior F1.5..F1.10 tests still pass)` | 1 NEW full-chain integration test + 1 NEW GET preservation test + CI verification | ~50 |

**Total**: 8 commits, ~980 LOC cumulative (impl + tests), 1 PR to `origin/dev`. Net apply delta ~860 LOC.

## Definition of Done (apply phase)

- [x] 19 tests + 5 AST walks across 8 test files PASS via `uv run pytest backend/tests/unit/test_reimpresion_ticket_*.py backend/tests/unit/test_repo_reimpresion_ticket.py backend/tests/integration/test_workflows_router_wiring.py backend/tests/integration/test_migration_0029_idempotent.py backend/tests/static/test_workflow_handler_*.py -q`
- [x] MIGRATION 0029 applied + downgrade reverses cleanly via `alembic upgrade head` + `alembic downgrade -1` + `alembic upgrade head` (round-trip idempotent)
- [x] 2 handlers (`create_reimpresion_ticket`, `anular_reimpresion_ticket`) implemented per design §9.1, §9.2 + GAP-BE-04 single-line fix at `api/v1/workflows.py:74` applied + router wired
- [x] `repo/reimpresion_ticket.py` 6 helpers + 5 typed exceptions + `validate_motivo_length` shared + idempotency wrapper authored (DEC-TKT-02..05)
- [x] `schemas/workflows.py` extended with 2 endpoint schemas + 5 typed error schemas + extended `ReimpresionTicketRead` (DEC-TKT-04)
- [x] KD-3 issuer chain + `_anular_reimpresion_issuer_dep` applied to both handlers with `Cache-Control: no-store` on every response
- [x] KD-TKT-01 single-commit invariant verified via AST walks on both `create_reimpresion_ticket` + `anular_reimpresion_ticket`
- [x] DEC-TKT-02 + DEC-TKT-03 no UPDATE on `prod.reimpresion_ticket` user-meaningful fields verified via AST walks on both handlers + extended LW-table walk
- [x] `repo/workflow.append_transition` + `repo/workflow.read_chain_tip` reused verbatim, NOT modified (DEC-TKT-02 + REQ-OPS-078)
- [x] `prod.permisos_usuario` Idempotency-Key cache lookup helper added (DEC-IDEM-01 reuse from F1.6)
- [x] REQ-OPS-075..080 + REQ-OPS-XR4 traceability verified via per-REQ RED tests
- [x] All F1.5/F1.6/F1.7/F1.8/F1.9/F1.10 tests still PASS (no_regresion gate)
- [x] ruff + mypy --strict clean on all 9 new/modified files
- [x] 5 CI gates verde (`factory_intact`, `event_helper_intact`, `auth_tenancy_intact`, `__init__.py_intact`, `no_regresion_F1.5_to_F1.10`)
- [x] 0 regresiones introducidas; baseline F1.10 pre-existing failures documented + unchanged
- [x] GAP-BE-04 reconciled: `api/v1/workflows.py:74` carries `"reimprimir_ticket"` instead of `"emitir_reimpresion"`; integration test `test_legacy_emitir_reimpresion_rejected_after_fix` PASSES (REQ-OPS-076 Scenario 3)
- [x] 8 atomic commits authored with conventional commit messages, neutral Spanish, NO `Co-authored-by:` trailers

## Next phase

`sdd-apply HU-F1.11` — TDD-strict RED→GREEN→REFACTOR per cluster T1..T8. Orchestrator executes the 8 atomic commits in order, verifies each cluster's exit criteria, and routes to `sdd-verify` after all commits land.

## References

- `openspec/changes/hu-f1-11-reimpresion-tiquete/design.md` (16 sections + 2 appendices, 2026-09-15, ~2450 LOC) — full architecture + MIGRATION 0029 SQL + 19 tests + 2 AST walks + 8 DECs + 2 KDs.
- `openspec/changes/hu-f1-11-reimpresion-tiquete/specs/operations/spec.md` (367 LOC, 7 REQ-OPS-075..080 + REQ-OPS-XR4) — operational requirements.
- `openspec/changes/hu-f1-11-reimpresion-tiquete/proposal.md` (~480 LOC, 16 sections, DEC-TKT-01..06) — pre-design proposal.
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/tasks.md` (~620 LOC, 8 clusters T1..T8, 31 tasks, ~0.86 PR diff) — **canonical precedent** for F1.11 structure.
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/{exploration,proposal,design,tasks,verify-report,archive-report}.md` — F1.10 full cycle precedent.
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/tasks.md` — F1.9 precedent (KD-FACT-01 single-commit).
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/tasks.md` — F1.7 precedent (KD-S2 tenant scope, `one_exit_per_ingreso` partial UK).
- `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/tasks.md` — F1.5 precedent (`repo/workflow.append_transition` + `read_chain_tip` + AST walk).
- `openspec/changes/archive/2026-09-14-hu-f1-6-ingresos/tasks.md` — F1.6 precedent (DEC-IDEM-01 Idempotency-Key header).
- `openspec/specs/operations/spec.md` — 80 REQs REQ-OPS-001..074 + XR1..XR3 merged post-F1.10; target for REQ-OPS-075..080 + XR4 merge on archive.
- `plan.md` lines 983-1006 — HU-F1.11 definition, 3 atomic tasks T1..T3, 170 LOC budget.
- `plan.md` lines 989-991 — acceptance criteria for crear + anular.
- `plan.md` line 993 — gap huérfano anulación.
- `plan.md` line 1001 — 170 LOC budget (impl).
- `plan.md` line 7342 — GAP-BE-04 permission reconciliation mandate.
- `modelo_datos_er.mmd` lines 230-244 (`prod.costos_servicios` [V]) + 598-620 (`prod.reimpresion_ticket` [L-W]) + 1150-1155 (FK relationships).
- `migrations/versions/0001_initial_schema.py` lines 297-309 (costos_servicios create_table) + 893-910 (reimpresion_ticket create_table) + 1690-1692 (FK `fk_reimpresion_ticket_uuid_reimpresion_padre`) + 2379-2390 / 2660-2672 / 2873-2880 (triggers: audit, version, sync enqueue) + 3292 (`reimprimir_ticket` permission seed).
- `migrations/versions/0021_least_privilege_and_immutability_contract.py` lines 162, 182 (REVOKE UPDATE, DELETE on `prod.reimpresion_ticket` FROM rol_app).
- `migrations/versions/0028_one_fe_per_factura_and_chain_index_and_sync_flip.py` — F1.10 chain head.
- `models/L_W/reimpresion_ticket.py` lines 29-90 (WorkflowBase + self-FK `uuid_reimpresion_padre` + 11 columns).
- `models/V/costos_servicios.py` — VersionedBase, bi-temporal.
- `schemas/workflows.py` lines 50-132 (existing `ReimpresionTicketCreate`/`Read`/`Update`/`Filter`/`ReadList`).
- `api/v1/workflows.py` line 74 (GAP-BE-04 site: `"emitir_reimpresion"` stale) + lines 111-118 (mount) + lines 73-78 (`_ROUTER_CONFIG`).
- `repo/workflow.py` lines 66-72 (state machine `reimpresion_ticket`) + lines 110-237 (`append_transition`) + lines 240-348 (`read_chain_tip`).
- `sync/catalog/entries/sync_entries_lw.py` lines 27-40 (`reimpresion_ticket` `branch_to_cloud` direction per D1-rev — **already configured**, NO change needed).
- `tests/static/test_no_raw_dml_on_lw_tables.py` (F1.5 PR5-016 AST walk precedent).
- `tests/integration/test_workflows_router_wiring.py::test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion` (F1.11 DEC-TKT-01 regression test).
