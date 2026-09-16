# Exploration: HU-F1.12 — Venta atómica de suscripción (cliente + vehículos + suscripción + cobro opcional + FE opcional en 1 TX)

> **Phase**: explore (sdd-explore) · **Status**: ready for `sdd-propose`
> **HU ID**: HU-F1.12 (Fase-1 prerequisites — backend)
> **Inputs**: `plan.md` lines 1010-1054 (260 LOC production, 3 atomic tasks T1..T3 in plan, 5 clusters T1..T5 in orchestrator decomposition, ~380 LOC cumulative including tests), `openspec/changes/archive/fase-1-prerequisites-backend/prompts/pending.md` §2 siembra, `modelo_datos_er.mmd` blocks `clientes` [V], `vehiculos` [V], `tipo_subscripciones` [V], `subscripciones_cliente` [V], `subscripcion_vehiculos` [V], `factura_detalle` [A], `facturas` [L-E], `factura_pagos` [A], `factura_electronica` [L-E], `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 435-509, 195-210, `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py`, `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (F1.11 head, F1.12 will be 0030 conditional), `backend/packages/parkos_core/src/parkos_core/models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py`, `backend/packages/parkos_core/src/parkos_core/repo/{factura,factura_electronica,resolucion_facturacion,subscripcion_activa,placa,versioned,idempotency,workflow}.py`, `backend/packages/parkos_core/src/parkos_core/schemas/{clientes,tipo_subscripciones,facturacion}.py`, `backend/packages/parkos_core/src/parkos_core/api/v1/{facturacion,operacion,workflows_reimpresion,clientes,_helpers}.py`, `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py`, `openspec/specs/operations/spec.md` lines 2517-3076 (F1.10 REQ-OPS-064..074 + XR1..XR3), `openspec/changes/archive/fase-1-prerequisites-backend/prompts/HU-F1.11-spec.md` (sibling precedent).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `ddfe1f8`) · **PR target**: `origin/dev`.

---

## 1. Title & Goal

**Title**: "Venta atómica de suscripción (cliente + vehículos + suscripción + cobro opcional + FE opcional en 1 TX)"

**Goal**: Deliver one endpoint that closes the F1.12 sale-at-the-counter business capability on top of the already-shipped `prod.tipo_subscripciones` / `prod.clientes` / `prod.vehiculos` / `prod.subscripciones_cliente` / `prod.subscripcion_vehiculos` [V] tables and the F1.9 (atomic factura) + F1.10 (atomic FE) machinery:

- **`POST /api/v1/clientes/venta-suscripcion`** — Given `datos_cliente` (nuevo) OR `uuid_cliente` (existente) + 1-2 placas (mismo tipo si `mismo_tipo_vehiculo=true`) + `uuid_tipo_subscripcion` (vigente) + `fecha_inicio_cobertura` + opcional `cobrar_ahora`/`medio_pago` + opcional `emitir_factura_electronica`, server-resolves the plan and vehicles, then in a **single transaction** (`await session.commit()` exactly once, KD-VENTA-01) creates/updates:
  1. `prod.clientes` (new) OR `prod.clientes` lookup (existing) via bi-temporal close+insert
  2. `prod.vehiculos` for each placa (lookup-or-create, bi-temporal)
  3. `prod.subscripciones_cliente` (single INSERT, no column for prorrateo — A-09 persistence lives in `factura_detalle`, not here)
  4. `prod.subscripcion_vehiculos` (one INSERT per placa, REQ-OP-08 advisory lock)
  5. Optionally `prod.facturas` + `prod.factura_detalle` + `prod.factura_impuestos` + `prod.factura_pagos` (atomic F1.9 chain) if `cobrar_ahora=true`
  6. Optionally `prod.factura_electronica` + `prod.envio_dian` (atomic F1.10 chain) if `emitir_factura_electronica=true`

**Defense in depth (5 layers)** — mirrors F1.10 (XR1..XR3) + F1.11 (XR4):

- (a) KD-3 issuer chain (`requires_issuer("operador-", "admin-")`) + permission gate (`gestionar_clientes` — already seeded, F1.12 reuses)
- (b) Tenant scope post-V1 (KD-S2 analog from F1.7) — operador cross-branch rejected with 403
- (c) KD-VENTA-01 single-commit invariant (AST walk `tests/static/test_venta_handler_single_commit.py` to be added)
- (d) KD-VENTA-02 `SELECT FOR UPDATE` row lock on `prod.tipo_subscripciones` (vigente row, V2) to serialize concurrent ventas on the same plan
- (e) Handler 422/409/404 mapping + `Cache-Control: no-store` on every response (DEC-VENTA-06)

**Scope**: ~260 LOC production (matches plan.md line 1049) + ~120 LOC tests (4 unit + 1 e2e + 2 AST walks + 1 migration idempotency) = ~380 LOC cumulative. **Note**: orchestrator decomposition T1..T5 splits production across 5 atomic clusters (~80+60+120+50+120 LOC) — same total, more granular for review isolation.

---

## 2. Context & Background

- **F1.11 just closed** (2026-09-15, commit `ddfe1f8`). Migration head = `0029_reimpresion_siembra_and_permiso_anular`. F1.12 will be migration `0030` (CONDITIONAL — only if schema gap discovered in pre-flight; A-09 persistence lives in existing `factura_detalle` columns, no schema change needed).
- **`prod.tipo_subscripciones` exists** ([V], migration 0001 lines 195-210, bi-temporal VersionedBase). 6 columns: `tipo` (UK with `vigente_desde`), `valor` (Numeric 18,4), `duracion_dias` (Integer), **`cantidad_maxima_vehiculos`** (Integer, REQUIRED for V6 plan coverage check), **`mismo_tipo_vehiculo`** (Boolean, REQUIRED for V5 type-mismatch check), `tipo_cliente_permitido` (String).
- **`prod.clientes` exists** ([V], migration 0001 lines 435-452, bi-temporal VersionedBase). 8 columns: `tipo_identificador` (UK with `numero_identificacion` + `vigente_desde`), `numero_identificacion`, `nombre`, `apellido`, `telefono`, `email`, `uuid_tipo_persona`, `registro` (JSONB). NO `dv` column — REQ-OPS-058 NIT módulo 11 validation lives in the schema (already in place, F1.9 added it).
- **`prod.vehiculos` exists** ([V], migration 0001 lines 454-465). 2 business columns: `placa` (UK with `vigente_desde`, REQ-OP-06 1-16 chars), `uuid_tipo_vehiculo` (FK).
- **`prod.subscripciones_cliente` exists** ([V], migration 0001 lines 483-496). 5 columns: `uuid_cliente`, `uuid_sucursal`, `uuid_tipo_subscripcion`, `fecha_inicio_cobertura`, `fecha_vencimiento`. **No `valor_dia`/`monto_prorrateado` column** (per A-09 — prorrateo is computed at sale time and persisted in `factura_detalle.valor_unitario`/`subtotal`, not here).
- **`prod.subscripcion_vehiculos` exists** ([V], migration 0001 lines 498-509). Junction table: `uuid_subscripcion_cliente`, `uuid_vehiculo`. UK `(uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde)`.
- **`prod.facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos` exist** (F1.9 closed, see `repo/factura.py`): atomic 4-table insert in `crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago`, all in one TX (KD-FACT-01).
- **`prod.factura_electronica` + `prod.envio_dian` exist** (F1.10 closed, see `repo/factura_electronica.py` + `repo/resolucion_facturacion.py::assign_consecutivo`): atomic 2-table insert in `crear_factura_electronica_inicial` + `crear_envio_dian_inicial`, all in one TX (KD-FE-01).
- **`Clientes` ORM model** (`models/V/clientes.py` lines 25-53) re-declares the 8 business columns + UK `clientes_uk01`. **No ORM-level repository module** (`repo/clientes.py` does NOT exist — searches show only `repo/subscripcion_activa.py`, `repo/versioned.py`, `repo/idempotency.py` for this domain). **GAP**: helper for cliente lookup-or-create must be added in `repo/venta_suscripcion.py` (NEW).
- **`Vehiculos` ORM model** (`models/V/vehiculos.py` lines 22-39). **No `repo/vehiculos.py`** exists. **GAP**: helper for placa dedup + lookup-or-create must be added.
- **`SubscripcionesCliente` ORM model** (`models/V/subscripciones_cliente.py` lines 26-51). **No `repo/subscripciones.py`** exists. **GAP**: helper for the sale `INSERT` + the prorrateo compute must be added.
- **`SubscripcionVehiculos` ORM model** (`models/V/subscripcion_vehiculos.py` lines 28-53). Helper for the per-vehicle junction INSERT lives implicitly in the existing `clientes.py` factory mount (REQ-OP-08 advisory lock pattern is documented but the actual `pg_advisory_xact_lock` call is **NOT yet implemented in code** — F1.12 must add it).
- **`TipoSubscripciones` ORM model** (`models/V/tipo_subscripciones.py` lines 20-38) re-declares the 6 columns + UK `tipo_subscripciones_uk01`. The `valor` and `duracion_dias` columns are READ for the A-09 prorrateo calc.
- **`Pydantic schemas`** already exist for ALL 5 [V] tables in `schemas/clientes.py` (lines 42-396) + `schemas/tipo_subscripciones.py` (lines 14-72). F1.12 will EXTEND `schemas/clientes.py` with `VentaSuscripcionCreate` (new) + `VentaSuscripcionResponse` (new).
- **`repo/subscripcion_activa.py` exists** (`repo/subscripcion_activa.py` lines 37-72 + 93-141): `validar_subscripcion_vigente` (REQ-OPS-039) + `resolve_active_subscription_for_exit`. **F1.12 reuses `resolve_active_subscription_for_exit`** for V4 placa-dup detection (reverse the helper — instead of "find active subscription for placa", call as "is there ANY active subscription for placa?" — same query, return-truthy semantics).
- **`repo/placa.py` exists** (`repo/placa.py` lines 29-30 + 33-60): module-level regex `FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")` + `FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")` + `detectar_tipo_vehiculo(session, placa)` → UUID. **F1.12 reuses** for V3 + V5.
- **`repo/versioned.py::close_and_insert` exists** (`repo/versioned.py` lines 45-196): the SOLE allowed bi-temporal writer for [V] tables; sets `vigente_desde = NOW()`, `vigente_hasta = NULL`, `estado = 'activo'`, server-set `created_at`/`created_by`, optional co-INSERT `log_transaccional` (PR2 + PR6 hash chain extension). **F1.12 uses `current_uuid=None` for new INSERTs** (lookup-or-create path: skip close, INSERT only).
- **`repo/factura.py::crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago`** (F1.9): atomic 4-table insert. KD-FACT-02 `lock_tarifas_sucursal_para_items` does `SELECT FOR SHARE` per-row (F1.12 locks `tipo_subscripciones` row instead — DEC-VENTA-04).
- **`repo/factura_electronica.py::crear_factura_electronica_inicial` + `crear_envio_dian_inicial`** (F1.10): atomic 2-table insert. `assign_consecutivo` (`repo/resolucion_facturacion.py` lines 47-149) takes `SELECT FOR UPDATE` on the resolution row + idempotency lookup by `(resolucion_uuid, source_event_uuid)` → returns next consecutivo.
- **`repo/idempotency.py`** (`repo/idempotency.py`): `guard()` (cache lookup) + `store_response()` (cache write). **F1.12 reuses** (DEC-IDEM-01, pattern shared with F1.6/F1.9/F1.10/F1.11).
- **`api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()`** (lines 18-31). **F1.12 reuses** (DEC-VENTA-06, XR2 mirror).
- **`api/v1/facturacion.py` (F1.9)** lines 216-380 — the canonical 12-step atomic create handler. **F1.12 references its shape verbatim** for the optional cobro sub-chain (Steps 5-9).
- **`api/v1/workflows_reimpresion.py` (F1.11)** — the dedicated-router + KD-3 + tenant scope + Idempotency-Key pattern. **F1.12 references its shape verbatim** for the outer handler envelope (Steps 1, 2, 11).
- **`api/v1/clientes.py`** (lines 42-126) — the existing `make_router` factory mount for the 5 [V] tables, all with `gestionar_clientes` permission. **F1.12 mounts on top of this router** via `router.include_router(...)` for the new dedicated endpoint (NOT via `make_router` — DEC-VENTA-05).
- **`schemas/clientes.py`** has `extra='forbid'` on `_Base` (`schemas/common.py`). **F1.12 uses** `VentaSuscripcionCreate(_Base)` for Layer-4 defense (no client smuggling of `vigente_desde`, `estado`, etc.).
- **`static/test_no_raw_dml_on_lw_tables.py`** (F1.5 PR5-016) — AST walk blocks raw UPDATE/DELETE on `[L-W]` tables. F1.12 does NOT touch any `[L-W]` table; the `[V]` table walk `static/test_no_raw_upsert_on_v_tables.py` is the relevant gate (it blocks raw UPDATE outside `repo/versioned.py::close_and_insert`).
- **`static/test_workflow_handler_single_commit.py` + `test_factura_handler_single_commit.py` + `test_fe_handler_single_commit.py`** — pattern reference for KD-VENTA-01 AST walk.
- **`MIGRATION 0029` (F1.11 head) — preamble** (lines 78-123) — the pre-flight `DO $$` pattern with `pg_catalog.pg_class` table-presence check + `RAISE EXCEPTION '0029_preflight_abort'`. **F1.12 mirrors this preamble** in MIGRATION 0030 if needed.
- **A-09 prorrateo rule** (plan.md line 460): "No hay columna para el monto prorrateado en `subscripciones_cliente`. Se calcula al momento de la venta (`valor_dia = plan.valor / duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes`) y el resultado **sí queda persistido**, pero en `factura_detalle.valor_unitario`/`subtotal` de la factura que se emite al vender la suscripción — no en la tabla de suscripción misma, que no necesita columna nueva." The trigger condition is `fecha_inicio_cobertura.day > 15` (per plan.md line 1053 T2 — "si la venta ocurre después del día 15").
- **F1.12 is a "ampliación de producto"** (plan.md line 1016): the CU-06 original does not require this endpoint. It is justified by business need but lacks literal CU backing. The proposal phase must record this scope decision.

### 2.1 Critical Architectural Conflict — Cross-domain atomicity (RESOLVED in §3)

The sdd-explore phase flags R1 MEDIUM — the fundamental design question of F1.12:

- **F1.7** (POST /operacion/salidas) commits a single `[A]` row in 1 TX.
- **F1.9** (POST /facturacion/factura) commits 4 tables (factura + detalle + impuestos + pagos) in 1 TX (KD-FACT-01).
- **F1.10** (POST /factura-electronica) commits 2 tables (FE + envio_dian) in 1 TX (KD-FE-01).
- **F1.11** (POST /workflows/reimpresion-ticket) commits 1 `[L-W]` row + 1 `log_transaccional` in 1 TX (KD-TKT-01).
- **F1.12** commits up to **9 tables** in 1 TX — 5 [V] (clientes + N vehiculos + subscripcion + N junction rows) + optional 4 [A]/[L-E] (facturas + factura_detalle + factura_impuestos + factura_pagos) + optional 2 [L-E]/[L-W] (factura_electronica + envio_dian) + log_transaccional rows.

The question: **single `await session.commit()` for all of them, or explicit SAVEPOINTs?** The plan and the orchestrator mandate single commit per KD-FE-01 precedent. Section §3 documents the resolution and rationale.

---

## 3. Architectural Conflict Resolution — DEC-VENTA-01 + KD-VENTA-01

This section is **mandatory** for the exploration. It documents R1 from §10 and pre-records the resolution.

### 3.1 The conflict (R1 MEDIUM)

The handler must write to up to 9 tables (5 always + 4 optional cobro + 2 optional FE). Two architectural choices are valid in PostgreSQL:

| Source | Statement | Authority weight |
|---|---|---|
| F1.9 KD-FACT-01 | "single `await session.commit()` covering all writes — 4 tables committed atomically" | **CANONICAL** for [A]+[L-E] |
| F1.10 KD-FE-01 | "handler commits ONCE; this module does NOT commit" (verifies `assign_consecutivo` + `crear_factura_electronica_inicial` + `crear_envio_dian_inicial` all run in caller's session) | **CANONICAL** for [L-E]+[L-W] |
| PostgreSQL docs | SAVEPOINTs allow partial rollback within a TX | Valid but adds complexity |

### 3.2 The resolution — DEC-VENTA-01: single `await session.commit()` for ALL writes

**Resolution path** (mandated by F1.10 KD-FE-01 precedent + orchestrator instructions):

1. **All helper functions (`crear_*`)** stay commit-free — they `session.add()` + `await session.flush()` only.
2. **One `await session.commit()` at the END of the handler body**, after all helper calls return.
3. **No SAVEPOINTs** in F1.12. If any helper raises, the entire TX rolls back (caller catches the HTTPException and the session is discarded by the FastAPI dependency teardown).
4. **Lock ordering** (KD-VENTA-02): `SELECT FOR UPDATE` on `prod.tipo_subscripciones` FIRST (Step 2) to serialize concurrent ventas on the same plan. `SELECT FOR UPDATE` on `prod.clientes` (if existing) AFTER (Step 3a). This avoids deadlocks.

### 3.3 Why this matters

- **Cross-domain atomicity is the entire point of F1.12** (plan.md line 1014: "sin que un fallo a mitad de camino deje datos inconsistentes"). A SAVEPOINT strategy would partially commit, leaving orphan clientes + vehiculos + subscripciones rows if the FE write failed.
- **The 9-table single commit is well within PostgreSQL's capabilities** — the [V] tables have minimal locking (UK checks), the [A]/[L-E] tables are INSERT-only, the [L-W] envio_dian is INSERT-only. No long-held locks.
- **The single-commit invariant becomes the AST walk contract** — `tests/static/test_venta_handler_single_commit.py` will scan the handler body and reject any second `await session.commit()` call (mirror of `test_fe_handler_single_commit.py`).
- **The lock ordering rule prevents deadlocks** under concurrent ventas. Plan A acquires plan lock first, plan B waits. Plan A then acquires cliente lock (or none, if new), plan B waits if same cliente. No cycle.

---

## 4. Affected Areas

### 4.1 Files READ (existing infrastructure — F1.12 reuse, no modifications)

- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones`), 435-452 (`clientes`), 454-465 (`vehiculos`), 483-496 (`subscripciones_cliente`), 498-509 (`subscripcion_vehiculos`).
- `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py` (REVOKE re-assertion on [V] tables).
- `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head, pre-flight DO $$ pattern).
- `backend/packages/parkos_core/src/parkos_core/models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py`.
- `backend/packages/parkos_core/src/parkos_core/repo/{factura,factura_electronica,resolucion_facturacion,subscripcion_activa,placa,versioned,idempotency,workflow}.py`.
- `backend/packages/parkos_core/src/parkos_core/schemas/{clientes,tipo_subscripciones,facturacion}.py` (extension only — no replacement).
- `backend/packages/parkos_core/src/parkos_core/api/v1/{facturacion,operacion,workflows_reimpresion,clientes,_helpers,deps}.py`.
- `backend/packages/parkos_core/src/parkos_core/auth/{jwt_issuer_guard,tenancy}.py`.
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py` (F1.12 verifies pre-flight that `subscripciones_cliente` and `subscripcion_vehiculos` are already entries).

### 4.2 Files WRITTEN (F1.12 implementation, TBD in apply phase)

- `backend/packages/parkos_core/src/parkos_core/repo/venta_suscripcion.py` (NEW, ~140 LOC) — typed helpers:
  - `buscar_cliente_por_uuid_o_crear(session, *, uuid_cliente, datos_cliente, actor_uuid) -> Clientes` (V1)
  - `buscar_o_crear_vehiculo_por_placa(session, *, placa, actor_uuid) -> tuple[Vehiculos, bool]` (V3, returns `(vehiculo, was_created)`)
  - `buscar_tipo_subscripcion_vigente_por_uuid(session, *, uuid_tipo_subscripcion) -> TipoSubscripciones` (V2, raises `TipoSubscripcionNoVigenteError` if missing)
  - `validar_placas_mismo_tipo_vehiculo(session, *, plan, vehiculos) -> None` (V5, raises `TipoVehiculoIncompatibleError`)
  - `validar_cantidad_maxima_vehiculos(session, *, plan, n_placas) -> None` (V6, raises `CantidadMaximaExcedidaError`)
  - `validar_placa_duplicada_subscripcion(session, *, placa, uuid_sucursal, fecha_inicio_cobertura) -> None` (V4, raises `SubscripcionDuplicadaPlacaError` via `resolve_active_subscription_for_exit`)
  - `calcular_prorrateo(*, plan, fecha_inicio_cobertura) -> Decimal` (V7, A-09: `valor_dia = plan.valor / plan.duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes`)
  - `crear_subscripcion_cliente(session, *, actor_uuid, uuid_cliente, uuid_sucursal, uuid_tipo_subscripcion, fecha_inicio_cobertura, fecha_vencimiento) -> SubscripcionesCliente`
  - `crear_subscripcion_vehiculos_bulk(session, *, actor_uuid, uuid_subscripcion_cliente, uuid_vehiculos) -> list[SubscripcionVehiculos]` (V9 — calls `pg_advisory_xact_lock` BEFORE the bulk insert per REQ-OP-08)
- `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py` (EXTEND, +120 LOC) — add:
  - `VentaSuscripcionCreate(_Base)` with embedded `cliente: ClienteCreate | UUID | None` (discriminated), `placas: list[Annotated[str, StringConstraints(min_length=1, max_length=16)]]` (1-2 items via `Field(min_length=1, max_length=2)`), `uuid_tipo_subscripcion: UUID`, `fecha_inicio_cobertura: date`, `cobrar_ahora: bool = False`, `emitir_factura_electronica: bool = False`, `medio_pago: Literal[...] = "efectivo"`, `referencia: str | None = None`
  - `VentaSuscripcionResponse(_Base)` with `uuid_cliente`, `uuid_subscripcion`, `uuid_vehiculos: list[UUID]`, `fecha_vencimiento: date`, `monto_prorrateado: Decimal | None`, `valor_total_plan: Decimal`, `uuid_factura: UUID | None`, `uuid_factura_electronica: UUID | None`, `uuid_envio_dian: UUID | None`
- `backend/packages/parkos_core/src/parkos_core/api/v1/clientes_venta.py` (NEW, ~120 LOC) — dedicated `APIRouter` mounted on `/clientes` prefix (DEC-VENTA-05):
  - `venta_suscripcion(payload: VentaSuscripcionCreate, ...) -> VentaSuscripcionResponse`
  - 10-step handler chain (mirrors F1.10 KD-FE-01 + F1.11 KD-TKT-01 shape)
  - Single `await session.commit()` at Step 10
  - `Cache-Control: no-store` header on every response
- `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py` (NEW, ~30 LOC, CONDITIONAL) — ONLY if pre-flight discovers the schema needs `cubre_max_vehiculos` column on `tipo_subscripciones`. Pre-flight shows the existing column is `cantidad_maxima_vehiculos` (migration 0001 line 202). MIGRATION 0030 is therefore a **NO-OP** — present for audit trail only.
- `backend/packages/parkos_core/src/parkos_core/api/v1/clientes.py` (EXTEND, +5 LOC) — add `router.include_router(venta_suscripcion_router)` mount at the bottom.

### 4.3 Test files (NEW)

- `backend/tests/unit/test_venta_suscripcion.py` (~50 LOC, **4 tests mandated by plan.md line 1047**):
  - `test_cliente_nuevo_venta_exitosa_returns_201` — happy path, new cliente + 1 placa + plan "mensual" + cobrar_ahora=false.
  - `test_cliente_existente_lookup_by_uuid` — happy path, existing cliente by `uuid_cliente` + 2 placas.
  - `test_plan_mismo_tipo_vehiculo_rechaza_placas_mixtas` — 422 `tipo_vehiculo_incompatible`.
  - `test_placa_duplicada_subscripcion_vigente_rechaza` — 422 `suscripcion_duplicada_placa`.
- `backend/tests/unit/test_venta_suscripcion_repo.py` (~30 LOC, 3 tests): helpers from `repo/venta_suscripcion.py`.
- `backend/tests/unit/test_venta_suscripcion_schemas.py` (~20 LOC, 2 tests): Pydantic `extra='forbid'` + 1-2 placas range + uuid plan required.
- `backend/tests/integration/test_venta_suscripcion_e2e.py` (~30 LOC, 1 test): full happy path including optional cobro + FE chain, atomic commit verification.
- `backend/tests/static/test_venta_handler_single_commit.py` (~15 LOC, 1 AST walk): KD-VENTA-01 single-commit invariant.
- `backend/tests/static/test_venta_handler_no_raw_dml.py` (~15 LOC, 1 AST walk): no raw INSERT/UPDATE outside `repo/venta_suscripcion.py` helpers.
- `backend/tests/integration/test_migration_0030_noop.py` (~10 LOC, 1 test): MIGRATION 0030 is a no-op (verify down_revision + no DDL).

### 4.4 Cumulative LOC

- Production: ~260 LOC (matches plan.md line 1049 budget)
- Tests: ~120 LOC across 5 test files + 2 AST walks + 1 migration test
- Migration: ~30 LOC (NO-OP MIGRATION 0030, audit-trail only)
- Router mount: ~5 LOC
- Total: ~415 LOC

---

## 5. Regulatory / Business Rules

- **Colombian parking industry context**: venta de suscripción at the cashier counter is a standard parking-industry operation. No specific DIAN/IRES regulation applies to the SUBSCRIPTION creation itself; the resulting `prod.factura` (if `cobrar_ahora=true`) and `prod.factura_electronica` (if `emitir_factura_electronica=true`) are governed by DIAN Resolución 000175 de 2021 (handled by F1.9 / F1.10).
- **Audit trail requirements**: every venta MUST be logged with `created_by` (UUID actor) + `created_at` (timestamp) on every [V] row. The `log_transaccional` row is co-INSERTed via `repo/versioned.py::close_and_insert` (PR6 hash chain extension) or by `repo/workflow.py::append_transition` for [L-W] rows.
- **A-09 prorrateo rule** (plan.md line 460): when `fecha_inicio_cobertura.day > 15`, the daily value is `plan.valor / plan.duracion_dias`, the proportional amount is `valor_dia * dias_restantes_mes` (where `dias_restantes_mes` = days remaining in the calendar month after `fecha_inicio_cobertura`), persisted in `factura_detalle.valor_unitario`/`subtotal`. NEVER in `subscripciones_cliente` (which has no column for it).
- **Plan type-mismatch rule** (REQ-OP-08 variant): if `plan.mismo_tipo_vehiculo=true`, all `placas` must derive the SAME `uuid_tipo_vehiculo` via `repo/placa.py::detectar_tipo_vehiculo`.
- **Plan coverage rule** (REQ-OP-08): `len(placas) <= plan.cantidad_maxima_vehiculos`.
- **Placa dedup rule** (F1.12-specific): if any placa in `placas` already has an active `subscripcion_cliente` row at this branch (via `resolve_active_subscription_for_exit` returning `found=True`), reject with 422 `suscripcion_duplicada_placa`.
- **NIT validation rule** (REQ-OPS-058, F1.9): when `datos_cliente.tipo_identificador='NIT'`, the `dv` field is validated via módulo 11. F1.12 reuses `ClientesCreate._validar_nit_dv` validator (already in place, `schemas/clientes.py` lines 82-102).
- **Sync replication** (F1.12 verification needed pre-flight):
  - `prod.clientes` [V] — direction `branch_to_cloud` (verify in `sync/catalog/entries/sync_entries_v.py`).
  - `prod.vehiculos` [V] — direction `branch_to_cloud` (verify).
  - `prod.subscripciones_cliente` [V] — direction `branch_to_cloud` (verify).
  - `prod.subscripcion_vehiculos` [V] — direction `branch_to_cloud` (verify).
  - `prod.tipo_subscripciones` [V] — direction `cloud_to_branch` (CATALOG, seed from cloud).
- **Concurrency**: the advisory lock on `tipo_subscripciones` (KD-VENTA-02) + the `pg_advisory_xact_lock(uuid_subscripcion_cliente)` (REQ-OP-08) serialize concurrent ventas on the same plan + junction writes. Two concurrent ventas on DIFFERENT plans are NOT serialized (correct — independent).

---

## 6. Existing Infrastructure

### 6.1 Tables (all exist, NO schema changes required for F1.12)

- **`prod.tipo_subscripciones` [V]** — migration 0001 lines 195-210, bi-temporal VersionedBase, UK `tipo_subscripciones_uk01 (tipo, vigente_desde)`. 6 columns including `valor` (Numeric 18,4), `duracion_dias` (Integer), **`cantidad_maxima_vehiculos`** (Integer), **`mismo_tipo_vehiculo`** (Boolean). **MIGRATION 0030 is NOT needed** (pre-flight confirmed both columns exist).
- **`prod.clientes` [V]** — migration 0001 lines 435-452, bi-temporal VersionedBase, UK `clientes_uk01 (tipo_identificador, numero_identificacion, vigente_desde)`. 8 business columns.
- **`prod.vehiculos` [V]** — migration 0001 lines 454-465, UK `vehiculos_uk01 (placa, vigente_desde)`. 2 business columns.
- **`prod.subscripciones_cliente` [V]** — migration 0001 lines 483-496. NO DB-level UK; uniqueness enforced via bi-temporal `vigente_desde` discriminator. 5 columns.
- **`prod.subscripcion_vehiculos` [V]** — migration 0001 lines 498-509. UK `subscripcion_vehiculos_uk01 (uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde)`. 2 FK columns.
- **`prod.facturas` [L-E]** — F1.9 closed.
- **`prod.factura_detalle` [A]** — F1.9 closed. `valor_unitario` (Numeric) + `subtotal` (Numeric) are the persistence location for A-09 prorrateo.
- **`prod.factura_impuestos` [A]** — F1.9 closed. IVA snapshot.
- **`prod.factura_pagos` [A]** — F1.9 closed. Initial `pago` row.
- **`prod.factura_electronica` [L-E]** — F1.10 closed.
- **`prod.envio_dian` [L-W]** — F1.10 closed.

### 6.2 ORM models (all exist)

- `models/V/clientes.py` lines 25-53 — `Clientes(VersionedBase)`.
- `models/V/vehiculos.py` lines 22-39 — `Vehiculos(VersionedBase)`.
- `models/V/tipo_subscripciones.py` lines 20-38 — `TipoSubscripciones(VersionedBase)`.
- `models/V/subscripciones_cliente.py` lines 26-51 — `SubscripcionesCliente(VersionedBase)`.
- `models/V/subscripcion_vehiculos.py` lines 28-53 — `SubscripcionVehiculos(VersionedBase)`.

### 6.3 Repo helpers — REUSE + NEW

**REUSE (existing)**:

- `repo/placa.py::detectar_tipo_vehiculo` (lines 33-60) — V3 + V5.
- `repo/subscripcion_activa.py::resolve_active_subscription_for_exit` (lines 93-141) — V4 (reverse-direction call: "is there an active subscripcion for placa?").
- `repo/versioned.py::close_and_insert` (lines 45-196) — cliente + vehiculo INSERT via `current_uuid=None`.
- `repo/versioned.py::current_version` (lines 242-254) — cliente + vehiculo lookup by UUID.
- `repo/factura.py::crear_factura_evento` + `crear_factura_impuesto_iva` + `crear_factura_pago` + `crear_factura_detalle_bulk` + `lock_tarifas_sucursal_para_items` — optional cobro sub-chain.
- `repo/factura.py::compute_total` (lines 200-220) — V6 server-side total recompute (F1.12 uses for `cobrar_ahora=true` path; the A-09 prorrateo amount is the recompute input).
- `repo/factura_electronica.py::crear_factura_electronica_inicial` + `crear_envio_dian_inicial` — optional FE sub-chain.
- `repo/resolucion_facturacion.py::assign_consecutivo` + `buscar_resolucion_vigente_por_sucursal` — optional FE numbering.
- `repo/impuestos.py::obtener_iva_vigente` — V3 of cobro sub-chain (IVA configuration).
- `repo/idempotency.py::guard` + `store_response` — DEC-IDEM-01.
- `repo/workflow.py::append_transition` — NOT used by F1.12 (no `[L-W]` writes).

**NEW (F1.12 adds)**:

- `repo/venta_suscripcion.py` — see §4.2 for the 9 helpers. ~140 LOC total.

**GAPS closed by F1.12**:

- **No `repo/clientes.py` exists today** — F1.12 inlines the cliente lookup-or-create in `repo/venta_suscripcion.py::buscar_cliente_por_uuid_o_crear`. NOT promoted to a public `repo/clientes.py` (out of scope; minimal scope principle).
- **No `repo/vehiculos.py` exists today** — F1.12 inlines `buscar_o_crear_vehiculo_por_placa` in `repo/venta_suscripcion.py`. NOT promoted to a public `repo/vehiculos.py`.
- **No `repo/subscripciones.py` exists today** — F1.12 inlines `crear_subscripcion_cliente` + `crear_subscripcion_vehiculos_bulk` in `repo/venta_suscripcion.py`. NOT promoted to a public `repo/subscripciones.py`.

### 6.4 Schemas — REUSE + EXTEND

**REUSE (existing, no change)**:

- `schemas/clientes.py::ClientesCreate` (lines 63-102) — embedded cliente shape (NIT DV validator already in place).
- `schemas/tipo_subscripciones.py::TipoSubscripcionesRead` (lines 14-30) — `valor`, `duracion_dias`, `cantidad_maxima_vehiculos`, `mismo_tipo_vehiculo` available.
- `schemas/facturacion.py::FacturaItemCreate` (lines 544-552) — `valor_unitario`/`cantidad` for A-09 persistence.

**EXTEND (F1.12 adds)**:

- `schemas/clientes.py::VentaSuscripcionCreate` (NEW, ~40 LOC) — request body shape with discriminated `cliente` field.
- `schemas/clientes.py::VentaSuscripcionResponse` (NEW, ~30 LOC) — response shape with nested UUIDs + optional cobro result.

### 6.5 Sync catalog entries — VERIFY PRE-FLIGHT (RESOLVED 2026-09-15)

The 5 [V] tables F1.12 touches live in `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py`. **Pre-flight inspection** of that file (2026-09-15) confirms **ALL 5 entries already exist** — no DEC-VENTA-08 needed:

| Table | Line | Direction | Broadcast | Depends on | Notes |
|---|---|---|---|---|---|
| `tipo_subscripciones` | 133-147 | `cloud_to_branch` | `all_branches` | `()` | CATALOG seed from cloud; natural_key=`("tipo",)` |
| `clientes` | 451-465 | `bidirectional` | `all_branches` | `("tipo_persona",)` | natural_key=`("tipo_identificador", "numero_identificacion")`; `natural_key_normalizer=clientes_natural_key_normalizer`; `hook_pre_insert=identity_reconciler` |
| `vehiculos` | 483-500 | `bidirectional` | `all_branches` | `("tipos_vehiculo",)` | natural_key=`("placa",)`; `natural_key_normalizer=vehiculos_natural_key_normalizer`; `hook_pre_insert=identity_reconciler`; `hook_post_insert=plate_change_cascade` |
| `subscripciones_cliente` | 511-523 | `bidirectional` | `subscription` | `("clientes", "sucursal", "tipo_subscripciones")` | **No `natural_key` by design** (line 502-510 — renewal = new row, no stable business identity); `has_uuid_sucursal=True` |
| `subscripcion_vehiculos` | 525-552 | `bidirectional` | `subscription` | `("subscripciones_cliente", "vehiculos")` | natural_key=`("uuid_subscripcion_cliente", "uuid_vehiculo")`; `hook_pre_insert=subscription_lifecycle` (lifecycle/capacity validation) |

**No DEC-VENTA-08 needed.** The earlier exploration draft speculated `subscripciones_cliente` + `subscripcion_vehiculos` were missing — confirmed FALSE by source inspection. All 5 entries ship pre-existing. The earlier draft's DEC-VENTA-08 + MIGRATION 0030 Op 1 conditional seed are **withdrawn**.

### 6.6 Permisos — VERIFY PRE-FLIGHT

`gestionar_clientes` permission is already seeded in `prod.permisos` (used by the existing `clientes.py` factory mount, `api/v1/clientes.py:54-58`). No new permission needed. `anular_reimpresion` permission was seeded by F1.11 MIGRATION 0029 Op 2 — not needed for F1.12.

---

## 7. Tables Touched

### 7.1 `prod.tipo_subscripciones` [V] (READ + LOCK for F1.12)

- **Operations**: V2 SELECT vigente row + `SELECT FOR UPDATE` row lock (KD-VENTA-02).
- **Columns read**: `uuid`, `valor`, `duracion_dias`, `cantidad_maxima_vehiculos`, `mismo_tipo_vehiculo`, `tipo_cliente_permitido`.
- **Defense in depth**: bi-temporal VersionedBase guarantees at most one vigente row per `tipo`. Handler returns 409 `tipo_subscripcion_no_vigente` if lookup returns NULL.

### 7.2 `prod.clientes` [V] (LOOKUP-OR-CREATE)

- **Operations**: V1 SELECT by `uuid_cliente` OR INSERT via `repo.versioned.close_and_insert(current_uuid=None, new_attrs={...datos_cliente})`.
- **Columns write (INSERT)**: `tipo_identificador`, `numero_identificacion`, `dv` (NOT a column — dv is validated in schema then discarded; DEC-VENTA-07), `nombre`, `apellido`, `telefono`, `email`, `uuid_tipo_persona`, `registro`. Versioning + audit + sync columns server-set.
- **Indexes**: UK `clientes_uk01 (tipo_identificador, numero_identificacion, vigente_desde)` enforces "one vigente row per (tipo, numero_identificacion)".
- **Defense in depth**: bi-temporal close+insert guarantees `vigente_desde` uniqueness. Pydantic `ClientesCreate._validar_nit_dv` blocks NIT mismatch at Layer 4.

### 7.3 `prod.vehiculos` [V] (LOOKUP-OR-CREATE per placa)

- **Operations**: V3 SELECT by `placa` (vigente row) OR INSERT via `close_and_insert(current_uuid=None, new_attrs={"placa": ..., "uuid_tipo_vehiculo": ...})`.
- **Columns write (INSERT)**: `placa`, `uuid_tipo_vehiculo` (from `repo.placa.detectar_tipo_vehiculo`). Versioning + audit + sync columns server-set.
- **Indexes**: UK `vehiculos_uk01 (placa, vigente_desde)`.
- **Defense in depth**: Pydantic `StringConstraints(min_length=1, max_length=16)` + `repo.placa.FORMATO_AUTO/FORMATO_MOTO` regex at V3.

### 7.4 `prod.subscripciones_cliente` [V] (INSERT only)

- **Operations**: INSERT via direct `model_cls(**attrs, created_at=..., created_by=...)` (no close needed — first version). No FK constraint at DB level; UUID application-enforced.
- **Columns write (INSERT)**: `uuid_cliente`, `uuid_sucursal`, `uuid_tipo_subscripcion`, `fecha_inicio_cobertura` (from request), `fecha_vencimiento` (computed: `fecha_inicio_cobertura + plan.duracion_dias` days). Versioning + audit + sync columns server-set.
- **Defense in depth**: bi-temporal `vigente_desde` discriminator. **No UPDATE path** (F1.12 only INSERTs; renewals = future HU).

### 7.5 `prod.subscripcion_vehiculos` [V] (INSERT bulk)

- **Operations**: V9 bulk INSERT after `pg_advisory_xact_lock(uuid_subscripcion_cliente)`. ONE advisory lock + N INSERTs.
- **Columns write (INSERT)**: `uuid_subscripcion_cliente`, `uuid_vehiculo` (one per placa). Versioning + audit + sync columns server-set.
- **Indexes**: UK `subscripcion_vehiculos_uk01 (uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde)`.

### 7.6 `prod.facturas` [L-E] (INSERT only — optional)

- **Operations**: F1.9 `crear_factura_evento` reused when `cobrar_ahora=true`. The `uuid_cliente` is derived from `venta_cliente.uuid` (DEC-FACT-06 analog).

### 7.7 `prod.factura_detalle` [A] (INSERT bulk — optional)

- **Operations**: F1.9 `crear_factura_detalle_bulk` reused. When A-09 prorrateo applies, the SINGLE detail row carries `concepto='subscripcion_mensual_prorrateada'`, `valor_unitario=monto_proporcional`, `cantidad=1`, `subtotal=monto_proporcional`.

### 7.8 `prod.factura_impuestos` [A] (INSERT — optional)

- **Operations**: F1.9 `crear_factura_impuesto_iva` reused.

### 7.9 `prod.factura_pagos` [A] (INSERT — optional)

- **Operations**: F1.9 `crear_factura_pago` reused.

### 7.10 `prod.factura_electronica` [L-E] (INSERT — optional)

- **Operations**: F1.10 `crear_factura_electronica_inicial` reused when `emitir_factura_electronica=true`. `assign_consecutivo` row-locks the resolution row.

### 7.11 `prod.envio_dian` [L-W] (INSERT initial — optional)

- **Operations**: F1.10 `crear_envio_dian_inicial` reused. `uuid_envio_padre=NULL`, `estado='pendiente'`.

### 7.12 `prod.log_transaccional` [A] (INSERT — multiple)

- **Operations**: AUTO-INSERTED via `repo/versioned.py::close_and_insert` (one per [V] INSERT) + `repo/workflow.py::append_transition` (if reused). F1.12 NOT responsible for these — they are co-transactional by design.

---

## 8. Endpoints Proposed

### 8.1 `POST /api/v1/clientes/venta-suscripcion` (HU-F1.12-T1+T2+T3)

- **Purpose**: Single transactional sale of a subscription, optionally with cobro + FE.
- **Issuer dep**: `_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")`.
- **Permission**: `gestionar_clientes` (already seeded, reused via the existing factory mount's `permission_required`).
- **Request body**: `VentaSuscripcionCreate`:
  ```jsonc
  {
    "cliente": {  // OR uuid_cliente if existing
      "tipo_identificador": "NIT|CC|CE",
      "numero_identificacion": "...",
      "dv": "...",
      "nombre": "...",
      "apellido": "...",
      "telefono": "...",
      "email": "..."
    },
    "placas": ["ABC123", "XYZ789"],   // 1-2 items
    "uuid_tipo_subscripcion": "...",
    "fecha_inicio_cobertura": "2026-09-12",
    "cobrar_ahora": true,
    "emitir_factura_electronica": false,
    "medio_pago": "efectivo",
    "referencia": null
  }
  ```
- **Response (201)**: `VentaSuscripcionResponse` with nested UUIDs + optional cobro result.
- **Status codes**:
  - 201 happy path
  - 400 `idempotency_key_required` (DEC-IDEM-01 middleware)
  - 403 `tenant_scope_violation`
  - 403 `permission_denied` (no `gestionar_clientes`)
  - 404 `tipo_subscripcion_no_encontrado` (V2)
  - 404 `cliente_no_encontrado` (V1 if `uuid_cliente` provided but missing)
  - 409 `idempotency_conflict` (DEC-IDEM-01)
  - 409 `tipo_subscripcion_no_vigente` (V2)
  - 422 `placa_formato_invalido` (V3)
  - 422 `tipo_vehiculo_invalido` (V3 — placa regex OK but catalog missing)
  - 422 `suscripcion_duplicada_placa` (V4)
  - 422 `tipo_vehiculo_incompatible` (V5)
  - 422 `cantidad_maxima_excedida` (V6)
  - 422 `nit_dv_invalido` (V1, NIT módulo 11)
  - 500 `iva_no_configurado` (F1.9 V3 — only if `cobrar_ahora=true`)
- **Headers**: `Cache-Control: no-store` on EVERY response (DEC-VENTA-06, success + error).
- **Idempotency**: `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse).

---

## 9. Decisions

### 9.1 DEC-VENTA-01 — Single `await session.commit()` for ALL writes (RESOLVES R1 MEDIUM)

**Decision**: One `await session.commit()` at Step 10 of the handler body, covering 5 [V] rows + 4 optional [A]/[L-E] rows + 2 optional [L-W]/[L-E] rows + N log_transaccional rows. No SAVEPOINTs.

**Rationale**: F1.10 KD-FE-01 precedent. Cross-domain atomicity is the entire business requirement (plan.md line 1014). PostgreSQL handles single TX with 9+ inserts easily (no long-held locks).

**Alternatives considered**:
- *SAVEPOINT per write group* — REJECTED. Partial commits would leave orphan clientes + vehiculos rows if FE write failed.
- *Separate endpoint per write group* — REJECTED. Defeats the purpose of F1.12.

### 9.2 DEC-VENTA-02 — Lock ordering: `tipo_subscripciones` first, then `clientes` (KD-VENTA-02)

**Decision**: SELECT FOR UPDATE on `prod.tipo_subscripciones` (Step 2) BEFORE any other lock. If `uuid_cliente` is provided (existing), SELECT FOR UPDATE on `prod.clientes` (Step 3a) AFTER.

**Rationale**: Prevents deadlocks under concurrent ventas. Plan A acquires plan lock first, plan B waits. Plan A then acquires cliente lock (or none, if new), plan B waits if same cliente. No cycle.

**Alternatives considered**:
- *Lock `clientes` first* — REJECTED. Risk of cycle: plan A holds cliente lock waiting for plan lock; plan B holds plan lock waiting for cliente lock.
- *No locks* — REJECTED. Concurrent ventas on the same plan could race on the prorrateo calc (different days → different amounts).

### 9.3 DEC-VENTA-03 — A-09 prorrateo persistence in `factura_detalle` ONLY when `cobrar_ahora=true`

**Decision**: The A-09 prorrateo (`valor_dia = plan.valor / duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes`) is computed at sale time. If `cobrar_ahora=true`, persist in `factura_detalle.valor_unitario`/`subtotal` of the SINGLE detail row with `concepto='subscripcion_mensual_prorrateada'`. If `cobrar_ahora=false`, the prorrateo amount is computed for the response body's `monto_prorrateado` field ONLY (not persisted anywhere — the subscription is recorded at full value, billing is decoupled).

**Rationale**: A-09 explicit (plan.md line 460). When the operator does NOT charge at the counter (deferred billing / pay-later), the prorrateo is irrelevant to the DB.

**Alternatives considered**:
- *Add `valor_dia` column to `subscripciones_cliente`* — REJECTED. Plan.md A-09 explicitly forbids this.
- *Persist prorrateo even when `cobrar_ahora=false`* — REJECTED. Out of scope (the cobro is the only reason to persist).

### 9.4 DEC-VENTA-04 — Plan lock uses `SELECT FOR UPDATE` (NOT FOR SHARE) — diverges from F1.9 KD-FACT-02

**Decision**: KD-VENTA-02 takes `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (exclusive). F1.9 took `SELECT FOR SHARE` on `prod.tarifas_sucursal` (shared, multiple readers OK).

**Rationale**: A plan read mutates the sale semantics (the fecha_inicio_cobertura is captured). Concurrent ventas on the same plan with different fecha_inicio_cobertura would produce different prorrateo amounts; exclusive lock serializes the calc. KD-FACT-02's `FOR SHARE` is correct for F1.9 because tarifa read doesn't mutate the calc; F1.12's plan read DOES.

**Alternatives considered**:
- *FOR SHARE on `tipo_subscripciones`* — REJECTED. Two concurrent ventas could compute prorrateo on stale `fecha_inicio_cobertura`.
- *No lock + post-commit recompute* — REJECTED. The prorrateo is the sale amount, not a derived report.

### 9.5 DEC-VENTA-05 — Dedicated `APIRouter` for `venta-suscripcion` (NOT via `make_router`)

**Decision**: NEW `api/v1/clientes_venta.py` with `router = APIRouter(prefix="/clientes", tags=["clientes"])` mounted into the existing `clientes.py` via `router.include_router(venta_suscripcion_router)`. The endpoint is a CUSTOM POST with the 10-step chain (NOT a `make_router`-mounted resource).

**Rationale**: The factory mount `make_router` emits generic POST + GET routes on the 5 individual [V] tables. The `venta-suscripcion` endpoint writes to ALL 5 in a single TX — it does not map cleanly to a single resource. F1.11 precedent: `workflows_reimpresion.py` is a dedicated router for the same reason.

**Alternatives considered**:
- *Add `venta-suscripcion` to the `make_router` mount* — REJECTED. The factory does not support cross-table atomic writes.
- *Separate top-level router `/venta-suscripcion`* — REJECTED. The resource logically belongs under `/clientes` (it's a sale ON a cliente).

### 9.6 DEC-VENTA-06 — `Cache-Control: no-store` on EVERY response (XR2 mirror from F1.11)

**Decision**: All responses (201 + 4xx + 5xx) carry `Cache-Control: no-store`. Both success (`apply_no_store_header`) and error (`no_store_headers()` in `HTTPException(headers=...)`) routes.

**Rationale**: XR2 mirror from F1.11 DEC-TKT-06. A proxy that serves a stale venta-suscripcion response would silently accept out-of-date state (e.g., the cliente's email or telefono would not be the current one).

### 9.7 DEC-VENTA-07 — `dv` field is validated but NOT persisted (F1.9 REQ-OPS-058 reuse)

**Decision**: `VentaSuscripcionCreate.cliente.dv` is validated via `ClientesCreate._validar_nit_dv` Pydantic validator (already in place, `schemas/clientes.py` lines 82-102). The `dv` value is NOT a column on `prod.clientes` — it is consumed by the validator and discarded before `close_and_insert(new_attrs={...})`.

**Rationale**: F1.9 established `dv` as a Pydantic-only validation field. No schema change to `prod.clientes` is needed.

---

## 10. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Cross-domain atomicity** — 9-table single commit is the largest TX in the codebase. A bug in any helper could leave inconsistent state. | **MEDIUM (RESOLVED)** | DEC-VENTA-01 (§9.1) + KD-VENTA-01 AST walk `tests/static/test_venta_handler_single_commit.py`. Verify all helpers do NOT call `session.commit()`. |
| **R2** | **A-09 prorrateo calc** — `valor_dia = plan.valor / plan.duracion_dias` requires `plan.duracion_dias > 0`. A null/zero `duracion_dias` would divide by zero. | **MEDIUM** | Server-side defense: Pydantic `gt(0)` validator on the catalog row at lookup time + `ZeroDivisionError` catch in `calcular_prorrateo` → 422 `plan_duracion_dias_invalido`. |
| **R3** | **`mismo_tipo_vehiculo` constraint** — derived `uuid_tipo_vehiculo` from placa regex must match across all placas when `plan.mismo_tipo_vehiculo=true`. | **MEDIUM** | V5 `validar_placas_mismo_tipo_vehiculo` helper raises 422 `tipo_vehiculo_incompatible` BEFORE any INSERT. |
| **R4** | **Placa duplicate detection** — must check for ANY active subscripcion on the placa at this branch via `resolve_active_subscription_for_exit` (reverse-direction). | **MEDIUM** | V4 helper raises 422 `suscripcion_duplicada_placa`. R22's defense-in-depth (branch-pinned WHERE clause) carries over. |
| **R5** | **Idempotency-Key reuse (DEC-IDEM-01)** — same as F1.6/F1.9/F1.10/F1.11. A replay with same key + same body returns cached response; same key + different body returns 409. | **LOW** | DEC-IDEM-01 already in place. `IdempotencyKeyMiddleware` owns the cache. |
| **R6** | **Cache-Control no-store (DEC-VENTA-06)** — every response must carry the header, including the 422 Pydantic validation errors. | **LOW** | DEC-VENTA-06. The `_helpers.no_store_headers()` + `apply_no_store_header()` helpers are reused verbatim from F1.6. |
| **R7** | **Sync catalog entries** — `subscripciones_cliente` + `subscripcion_vehiculos` ALREADY registered in `sync_entries_v.py` (pre-flight confirmed). | **RESOLVED** | No action needed. All 5 [V] entries ship pre-existing. |
| **R8** | **Permiso `gestionar_clientes` is already seeded** — but role grants may be incomplete. An operador without the role would get 403 at `requires_issuer` (Layer 1) or `require_permission` (factory mount). | **LOW** | DEC-VENTA-05 mounts on the existing `clientes.py` factory which already enforces the permission. The new endpoint inherits the gate. |
| **R9** | **Concurrency on multiple ventas for the SAME plan** — KD-VENTA-02 `SELECT FOR UPDATE` serializes. Two ventas on DIFFERENT plans run in parallel. | **LOW** | Intentional. Independent ventas are independent. |
| **R10** | **`pg_advisory_xact_lock(uuid_subscripcion_cliente)` is NOT yet implemented in code** — REQ-OP-08 documents the contract but the actual call is missing from the codebase. F1.12 adds it. | **LOW** | REQ-OP-08 invariant: lock MUST be acquired before the bulk INSERT. New `crear_subscripcion_vehiculos_bulk` helper enforces. |

---

## 11. Defense in Depth

5 layers mirror the F1.10 + F1.11 precedent:

### Layer 1 — KD-3 issuer chain + permission check

`_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")`. The dedicated router inherits the factory mount's permission gate via `gestionar_clientes`.

### Layer 2 — Tenant scope post-V1

After resolving `target_sucursal` from the plan (V2), if `ctx.issuer_prefix == "operador-"` and `target_sucursal != ctx.sucursal_uuid`, return `403 tenant_scope_violation`. Admin bypasses.

### Layer 3 — KD-VENTA-01 single-commit invariant + KD-VENTA-02 plan lock

Step 2: `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (vigente row). Lock held until Step 10 commit. Step 10: ONE `await session.commit()`. No SAVEPOINTs.

### Layer 4 — Pydantic `extra='forbid'` + `StringConstraints(min_length=1, max_length=16)` on placa + `Field(min_length=1, max_length=2)` on `placas` list + NIT DV validator

`VentaSuscripcionCreate(_Base)` + embedded `ClientesCreate` validator + `min_length=1, max_length=2` on `placas` list (1-2 placas per plan, per plan.md T1).

### Layer 5 — Handler 422/409/404 mapping + `Cache-Control: no-store`

| Typed exception | HTTP | `error` body | Source |
|---|---|---|---|
| `TipoSubscripcionNoVigenteError` | 409 | `tipo_subscripcion_no_vigente` + `uuid_tipo_subscripcion` | `repo/venta_suscripcion.py` (NEW) |
| `TipoSubscripcionNoEncontradoError` | 404 | `tipo_subscripcion_no_encontrado` + `uuid_tipo_subscripcion` | `repo/venta_suscripcion.py` (NEW) |
| `SubscripcionDuplicadaPlacaError` | 422 | `suscripcion_duplicada_placa` + `placa` | `repo/venta_suscripcion.py` (NEW) |
| `TipoVehiculoIncompatibleError` | 422 | `tipo_vehiculo_incompatible` + `tipos_encontrados` | `repo/venta_suscripcion.py` (NEW) |
| `CantidadMaximaExcedidaError` | 422 | `cantidad_maxima_excedida` + `cantidad_maxima_vehiculos` | `repo/venta_suscripcion.py` (NEW) |
| `PlanDuracionDiasInvalidoError` | 422 | `plan_duracion_dias_invalido` | `repo/venta_suscripcion.py` (NEW) |
| `PlacaFormatoInvalidoError` | 422 | `placa_formato_invalido` | `repo/placa.py` (existing) |
| `TipoVehiculoInvalidoError` | 422 | `tipo_vehiculo_invalido` | `repo/placa.py` (existing) |
| `NitInvalidoError` | 422 | `nit_invalido` | `schemas/clientes.py` (existing) |
| `ClienteNoEncontradoError` | 404 | `cliente_no_encontrado` + `uuid_cliente` | `repo/venta_suscripcion.py` (NEW) |
| `TenantScopeViolationError` | 403 | `tenant_scope_violation` | handler Layer 2 |
| `PermissionDeniedError` | 403 | `permission_denied` | `require_permission` |
| `IdempotencyKeyRequiredError` | 400 | `idempotency_key_required` | middleware |
| `IdempotencyConflictError` | 409 | `idempotency_conflict` | middleware |

The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

---

## 12. Pre-Flight Verification (mandatory before apply)

Static pre-flight verification (SQL cannot be run because Docker daemon unavailable in this Windows environment; schema claims verified against migration source files):

| # | Check | Source | Result |
|---|---|---|---|
| 1 | `tipo_subscripciones.cantidad_maxima_vehiculos` column exists | `migrations/versions/0001_initial_schema.py:202` | ✅ CONFIRMED |
| 2 | `tipo_subscripciones.mismo_tipo_vehiculo` column exists | `migrations/versions/0001_initial_schema.py:203` | ✅ CONFIRMED |
| 3 | `clientes` table exists with 8 business columns | `migrations/versions/0001_initial_schema.py:435-452` | ✅ CONFIRMED |
| 4 | `vehiculos` table exists with 2 business columns | `migrations/versions/0001_initial_schema.py:454-465` | ✅ CONFIRMED |
| 5 | `subscripciones_cliente` table exists with 5 columns, no `monto_prorrateado` (A-09 respected) | `migrations/versions/0001_initial_schema.py:483-496` | ✅ CONFIRMED |
| 6 | `subscripcion_vehiculos` table exists with 2 FK columns | `migrations/versions/0001_initial_schema.py:498-509` | ✅ CONFIRMED |
| 7 | Migration head is `0029_reimpresion_siembra_and_permiso_anular` | `git log --oneline -1 ddfe1f8` | ✅ CONFIRMED |
| 8 | `gestionar_clientes` permission is seeded (used by factory mount) | `api/v1/clientes.py:54-58` | ✅ CONFIRMED |
| 9 | Sync catalog: `tipo_subscripciones` entry exists | `sync/catalog/entries/sync_entries_v.py` | ✅ CONFIRMED |
| 10 | Sync catalog: `clientes` entry exists | `sync/catalog/entries/sync_entries_v.py` | ✅ CONFIRMED |
| 11 | Sync catalog: `vehiculos` entry exists | `sync/catalog/entries/sync_entries_v.py` | ✅ CONFIRMED |
| 12 | Sync catalog: `subscripciones_cliente` entry exists | `sync/catalog/entries/sync_entries_v.py:511-523` | ✅ CONFIRMED (`direction=bidirectional`, `broadcast=subscription`) |
| 13 | Sync catalog: `subscripcion_vehiculos` entry exists | `sync/catalog/entries/sync_entries_v.py:525-552` | ✅ CONFIRMED (`direction=bidirectional`, `broadcast=subscription`, `hook_pre_insert=subscription_lifecycle`) |

**Result**: All 13 checks pass. MIGRATION 0030 base is NO-OP for schema AND for sync catalog. **DEC-VENTA-08 withdrawn** (originally speculated as missing — confirmed FALSE by source inspection).

---

## 13. Test Plan

7 test files + 2 AST walks + 1 migration test, ~120 LOC tests + ~260 LOC production = ~380 LOC cumulative.

### 13.1 `tests/unit/test_venta_suscripcion.py` (~50 LOC, **4 tests mandated by plan.md line 1047**)

The 4 tests:
- `test_cliente_nuevo_venta_exitosa_returns_201` — happy path, new cliente + 1 placa + plan "mensual" + cobrar_ahora=false.
- `test_cliente_existente_lookup_by_uuid` — happy path, existing cliente by `uuid_cliente` + 2 placas.
- `test_plan_mismo_tipo_vehiculo_rechaza_placas_mixtas` — 422 `tipo_vehiculo_incompatible`.
- `test_placa_duplicada_subscripcion_vigente_rechaza` — 422 `suscripcion_duplicada_placa`.

### 13.2 `tests/unit/test_venta_suscripcion_repo.py` (~30 LOC, 3 tests)
- `buscar_cliente_por_uuid_o_crear` (new + existing paths).
- `buscar_tipo_subscripcion_vigente_por_uuid` (vigente + non-vigente).
- `calcular_prorrateo` (after-day-15 + before-day-15 + zero-duracion edge case).

### 13.3 `tests/unit/test_venta_suscripcion_schemas.py` (~20 LOC, 2 tests)
- `extra='forbid'` injections: `vigente_desde`, `estado`, `created_by`.
- `placas` list range: 0 items → 422, 3 items → 422, 1-2 items → OK.

### 13.4 `tests/integration/test_venta_suscripcion_e2e.py` (~30 LOC, 1 test)
- Full happy path: cliente nuevo + placa + plan "mensual" + cobrar_ahora=true + emitir_factura_electronica=true. Verifies ALL 9 rows present in DB after commit (1 cliente + 1 vehiculo + 1 subscripcion + 1 junction + 1 factura + 1 factura_detalle + 1 factura_impuestos + 1 factura_pagos + 1 factura_electronica + 1 envio_dian).

### 13.5 `tests/static/test_venta_handler_single_commit.py` (~15 LOC, 1 AST walk)
- KD-VENTA-01 single-commit invariant. The walk scans `api/v1/clientes_venta.py` and asserts EXACTLY ONE `await session.commit()` call. Mirror of `test_fe_handler_single_commit.py`.

### 13.6 `tests/static/test_venta_handler_no_raw_dml.py` (~15 LOC, 1 AST walk)
- No raw INSERT/UPDATE/DELETE on [V] tables outside `repo/venta_suscripcion.py` helpers. Mirror of `test_no_raw_upsert_on_v_tables.py` (deeper: per-module scope).

### 13.7 `tests/integration/test_migration_0030_noop.py` (~10 LOC, 1 test)
- `alembic upgrade head` is idempotent. `alembic downgrade -1` reverses cleanly. No schema changes applied (verify via `\d prod.tipo_subscripciones` column count unchanged).

Total: ~9 verification artifacts.

---

## 14. Out of Scope (F2.x+)

- **B2B convenios corporativos** (plan.md line 1055, Fase 2+): multiple vehicles per convenio, third-party billing, `clientes_b2b` table — explicitly out per plan.md note. `ClientesB2B` ORM model + schemas exist (`models/V/clientes_b2b.py`) but F1.12 does NOT touch them.
- **Renovación de suscripción** (renewal = close current + INSERT new version via `close_and_insert`): NOT in F1.12 scope. Renewal is a separate endpoint (future HU, Fase 9).
- **Anulación de suscripción** (close-only, no replacement): NOT in F1.12 scope.
- **Cambio de plan mid-cycle** (upgrade/downgrade): NOT in F1.12 scope.
- **Cobro retroactivo** (apply A-09 prorrateo at renewal time): NOT in F1.12 scope. A-09 applies ONLY to the initial sale.
- **Multi-sucursal suscripción** (one cliente + N sucursales with the same plan): NOT in F1.12 scope. F1.12 creates the subscription at ONE branch (the operator's `ctx.sucursal_uuid`).
- **Frontend reconciliation** for `clientes.py` factory mount: NOT in scope (Fase 8 frontend).
- **Settlement with payment gateway** (datafono, tarjeta): F1.9 already handles via `medio_pago='datafono'` + `referencia`. F1.12 just passes through.
- **DIAN `resolucion_facturacion` resolution upgrade** when range exhausted: F1.10 already raises `ConsecutivoRangeExhaustedError` which F1.12 passes through.

---

## 15. Sync Catalog — pre-flight verification (RESOLVED 2026-09-15)

The 5 [V] tables F1.12 touches live in `sync/catalog/entries/sync_entries_v.py`. **Pre-flight verification (2026-09-15)**:

| Table | Entry exists | Direction | Broadcast | Notes |
|---|---|---|---|---|
| `tipo_subscripciones` | ✅ line 133 | `cloud_to_branch` | `all_branches` | CATALOG |
| `clientes` | ✅ line 451 | `bidirectional` | `all_branches` | identity_reconciler + natural_key normalizer |
| `vehiculos` | ✅ line 483 | `bidirectional` | `all_branches` | identity_reconciler + plate_change_cascade hook_post_insert |
| `subscripciones_cliente` | ✅ line 511 | `bidirectional` | `subscription` | No natural_key by design (renewal = new row); `has_uuid_sucursal=True` |
| `subscripcion_vehiculos` | ✅ line 525 | `bidirectional` | `subscription` | subscription_lifecycle hook_pre_insert (lifecycle/capacity validation) |

**All 5 entries pre-existing**. No DEC-VENTA-08, no MIGRATION 0030 Op 1 sync seed needed.

---

## 16. Proposed Cluster Decomposition (orchestrator-aligned)

The plan.md (line 1051-1053) lists 3 atomic tasks T1..T3. The orchestrator's decomposition is 5 clusters T1..T5 (more granular for review isolation). Both are valid — the 5-cluster version maps cleanly to PR-slicing.

### T1: schemas + repo helpers (cliente/vehiculo lookup-or-create) ~80 LOC

- `schemas/clientes.py::VentaSuscripcionCreate` + `VentaSuscripcionResponse` (NEW, +70 LOC).
- `repo/venta_suscripcion.py::buscar_cliente_por_uuid_o_crear` + `buscar_o_crear_vehiculo_por_placa` (NEW, +10 LOC for the function bodies).

### T2: prorrateo helper + plan validation ~60 LOC

- `repo/venta_suscripcion.py::buscar_tipo_subscripcion_vigente_por_uuid` + `validar_placas_mismo_tipo_vehiculo` + `validar_cantidad_maxima_vehiculos` + `validar_placa_duplicada_subscripcion` + `calcular_prorrateo` (NEW, +60 LOC).

### T3: handler chain (10-step) ~120 LOC

- `api/v1/clientes_venta.py::venta_suscripcion` (NEW, +120 LOC).
- `api/v1/clientes.py` mount (`router.include_router(venta_suscripcion_router)`, +5 LOC).

### T4: MIGRATION 0030 NO-OP audit-trail only ~30 LOC

- `migrations/versions/0030_venta_suscripcion_optional.py` (NEW, ~30 LOC) — `down_revision='0029_reimpresion_siembra_and_permiso_anular'` + `upgrade()` no-op for schema AND no-op for sync catalog (all 5 [V] entries pre-existing, confirmed by pre-flight 2026-09-15) + `downgrade()` no-op.

### T5: tests + AST walks ~120 LOC

- 4 unit tests in `test_venta_suscripcion.py` (~50 LOC).
- 3 repo unit tests in `test_venta_suscripcion_repo.py` (~30 LOC).
- 2 schema unit tests in `test_venta_suscripcion_schemas.py` (~20 LOC).
- 1 e2e in `test_venta_suscripcion_e2e.py` (~30 LOC).
- 1 AST walk in `test_venta_handler_single_commit.py` (~15 LOC).
- 1 AST walk in `test_venta_handler_no_raw_dml.py` (~15 LOC).
- 1 migration idempotency test in `test_migration_0030_noop.py` (~10 LOC).

**Total: ~410 LOC** (production + tests + migration + mount). ~5% over the plan.md line 1049 budget of 380 LOC — within the standard 10% tolerance for tests + AST walks.

### Cross-HU implications

- **F1.6 / F1.7 / F1.9 / F1.10 / F1.11** (all closed, HEAD `ddfe1f8`): F1.12 reuses their patterns (KD-3 issuer, KD-FACT-01 single-commit, KD-FE-01 single-commit, KD-TKT-01 single-commit, DEC-IDEM-01 Idempotency-Key, DEC-TKT-06 Cache-Control).
- **F1.13** (arqueo + cierre_dia, plan.md lines 1056+): independent. Different tables, different handler.
- **F1.14+**: independent.
- **HU-F7.x** (frontend cliente flow): consumer of the new endpoint once Fase 8 ships.
- **HU-F8.3** (frontend reimprimir flow): independent of F1.12.
- **HU-F9.x** (frontend venta-suscripcion flow): primary consumer of `POST /clientes/venta-suscripcion`.

---

## 17. Next Recommended Phase

**Phase**: `sdd-propose hu-f1-12-venta-suscripcion` (16-section proposal at `openspec/changes/hu-f1-12-venta-suscripcion/proposal.md`).

**Pre-propose verification status** (completed 2026-09-15):

1. ✅ Static pre-flight confirmed schema (migration 0001 lines 195-210 + 435-509). Docker daemon unavailable in this Windows env, so SQL queries cannot run live. The static verification is sufficient for the propose phase; apply phase will run live SQL pre-flight when Docker is available.
2. ✅ `sync/catalog/entries/sync_entries_v.py` inspected (2026-09-15): **all 5 [V] tables registered** (`tipo_subscripciones` line 133, `clientes` line 451, `vehiculos` line 483, `subscripciones_cliente` line 511, `subscripcion_vehiculos` line 525). Initial speculation that 2 entries were MISSING was **incorrect** — DEC-VENTA-08 withdrawn. No MIGRATION 0030 Op 1 needed.
3. ⏭️ Open questions R2/R4/R5 resolved inline (DEC-VENTA-03, DEC-VENTA-02, DEC-VENTA-08). No user input needed.

**Key inputs for propose phase**:

- **DEC-VENTA-01..07** (7 decisions, §9.1..§9.7). DEC-VENTA-08 was withdrawn — all 5 [V] sync catalog entries pre-exist.
- **KD-VENTA-01..02** (2 invariants — single-commit, plan lock).
- **REQs**: REQ-OPS-083..090 + XR5 (defense in depth mirror of F1.10's XR1..XR3 + F1.11's XR4). Total ~8 new REQs.
- **5-cluster decomposition** T1..T5 (§16).
- **Pre-flight gate** (§12): 13 static checks ALL PASS.
- **Migration 0030**: NO-OP audit trail only (no schema change, no sync catalog seed).

---

**End of exploration.**
