# Proposal: HU-F1.12 — Venta atómica de suscripción (cliente + vehículos + suscripción + cobro opcional + FE opcional en 1 TX)

> **Change**: `hu-f1-12-venta-suscripcion` · **Folder**: `openspec/changes/hu-f1-12-venta-suscripcion/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.12 (Fase-1 prerequisites — backend)
> **Inputs**: `plan.md` lines 1010-1054 (260 LOC production, 3 atomic tasks T1..T3, 4 tests mandated at line 1047), `openspec/changes/hu-f1-12-venta-suscripcion/exploration.md` (17 sections, ~770 LOC, DEC-VENTA-08 WITHDRAWN — all 5 [V] sync catalog entries pre-exist per pre-flight 2026-09-15), `modelo_datos_er.mmd` blocks `clientes` [V] line 449, `vehiculos` [V] line 519, `tipo_subscripciones` [V] line 105, `subscripciones_cliente` [V] line 496, `subscripcion_vehiculos` [V] line 538, `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones`), 435-452 (`clientes`), 454-465 (`vehiculos`), 483-496 (`subscripciones_cliente`), 498-509 (`subscripcion_vehiculos`), `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head; F1.12 will be migration `0030`), `backend/packages/parkos_core/src/parkos_core/models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py`, `backend/packages/parkos_core/src/parkos_core/repo/{factura,factura_electronica,resolucion_facturacion,subscripcion_activa,placa,versioned,idempotency}.py`, `backend/packages/parkos_core/src/parkos_core/schemas/{clientes,tipo_subscripciones,facturacion}.py`, `backend/packages/parkos_core/src/parkos_core/api/v1/{facturacion,workflows_reimpresion,clientes,_helpers}.py`, `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py` (lines 133, 451, 483, 511, 525 — all 5 [V] entries verified pre-existing), `openspec/specs/operations/spec.md` lines 2517-3076 (F1.10 REQ-OPS-064..074 + XR1..XR3 + F1.11 REQ-OPS-075..080 + XR4), `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/proposal.md` (sibling precedent).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `ddfe1f8`) · **PR target**: `origin/dev`.
> **Language note**: artifact authored in English per the project's `Language Domain Contract` (default for technical SDD artifacts). DEC-VENTA-NN and KD-VENTA-NN identifiers follow the established F1.x naming pattern.

---

## 1. Title & Goal

**Title**: "Venta atómica de suscripción (cliente + vehículos + suscripción + cobro opcional + FE opcional en 1 TX)"

**Goal**: Deliver one endpoint that closes the F1.12 sale-at-the-counter business capability on top of the already-shipped `prod.tipo_subscripciones` / `prod.clientes` / `prod.vehiculos` / `prod.subscripciones_cliente` / `prod.subscripcion_vehiculos` `[V]` tables and the F1.9 (atomic factura) + F1.10 (atomic FE) machinery:

- **`POST /api/v1/clientes/venta-suscripcion`** — Given `datos_cliente` (new) OR `uuid_cliente` (existing) + 1-2 placas (mismo tipo si `plan.mismo_tipo_vehiculo=true`) + `uuid_tipo_subscripcion` (vigente) + `fecha_inicio_cobertura` + optional `cobrar_ahora`/`medio_pago` + optional `emitir_factura_electronica`, server-resolves the plan and vehicles, then in a **single transaction** (`await session.commit()` exactly once, KD-VENTA-01) creates/updates:
  1. `prod.clientes` (new) OR `prod.clientes` lookup (existing) via bi-temporal close+insert.
  2. `prod.vehiculos` for each placa (lookup-or-create, bi-temporal).
  3. `prod.subscripciones_cliente` (single INSERT; no column for prorrateo — A-09 persistence lives in `factura_detalle`, not here).
  4. `prod.subscripcion_vehiculos` (one INSERT per placa, REQ-OP-08 advisory lock).
  5. Optionally `prod.facturas` + `prod.factura_detalle` + `prod.factura_impuestos` + `prod.factura_pagos` (atomic F1.9 chain) if `cobrar_ahora=true`.
  6. Optionally `prod.factura_electronica` + `prod.envio_dian` (atomic F1.10 chain) if `emitir_factura_electronica=true`.

**Defense in depth (5 layers)** — mirrors F1.10 (XR1..XR3) + F1.11 (XR4):

- (a) KD-3 issuer chain (`requires_issuer("operador-", "admin-")`) + permission gate (`gestionar_clientes` — already seeded, F1.12 reuses).
- (b) Tenant scope post-V1 (KD-S2 analog from F1.7) — operador cross-branch rejected with 403.
- (c) KD-VENTA-01 single-commit invariant (AST walk `tests/static/test_venta_handler_single_commit.py`).
- (d) KD-VENTA-02 `SELECT FOR UPDATE` row lock on `prod.tipo_subscripciones` (vigente row, V2) to serialize concurrent ventas on the same plan.
- (e) Handler 422/409/404 mapping + `Cache-Control: no-store` on every response (DEC-VENTA-06).

**Scope**: ~260 LOC production (matches plan.md line 1049) + ~120 LOC tests (4 unit + 3 repo unit + 2 schema unit + 1 e2e + 2 AST walks + 1 migration idempotency = ~14 test functions across 7 files) + ~30 LOC MIGRATION 0030 NO-OP audit trail = ~415 LOC cumulative. **Note**: orchestrator decomposition T1..T5 splits production across 5 atomic clusters (~80+60+120+50+120 LOC) — same total, more granular for review isolation.

---

## 2. Context & Background

- **F1.11 just closed** (2026-09-15, commit `ddfe1f8`). Migration head = `0029_reimpresion_siembra_and_permiso_anular`. F1.12 will be migration `0030` (CONDITIONAL — only if schema gap discovered; pre-flight shows no schema change needed).
- **`prod.tipo_subscripciones` exists** (`[V]`, migration 0001 lines 195-210, bi-temporal VersionedBase). UK `tipo_subscripciones_uk01 (tipo, vigente_desde)`. 6 columns: `tipo`, `valor` (Numeric 18,4), `duracion_dias` (Integer), **`cantidad_maxima_vehiculos`** (Integer, REQUIRED for V6 plan coverage check), **`mismo_tipo_vehiculo`** (Boolean, REQUIRED for V5 type-mismatch check), `tipo_cliente_permitido`.
- **`prod.clientes` exists** (`[V]`, migration 0001 lines 435-452, bi-temporal VersionedBase). UK `clientes_uk01 (tipo_identificador, numero_identificacion, vigente_desde)`. 8 business columns. **No `dv` column** — REQ-OPS-058 NIT módulo 11 validation lives in the schema (already in place, F1.9 added it).
- **`prod.vehiculos` exists** (`[V]`, migration 0001 lines 454-465). UK `vehiculos_uk01 (placa, vigente_desde)`. 2 business columns.
- **`prod.subscripciones_cliente` exists** (`[V]`, migration 0001 lines 483-496). 5 columns: `uuid_cliente`, `uuid_sucursal`, `uuid_tipo_subscripcion`, `fecha_inicio_cobertura`, `fecha_vencimiento`. **No `valor_dia`/`monto_prorrateado` column** (A-09 — prorrateo is computed at sale time and persisted in `factura_detalle.valor_unitario`/`subtotal`, not here).
- **`prod.subscripcion_vehiculos` exists** (`[V]`, migration 0001 lines 498-509). Junction table: `uuid_subscripcion_cliente`, `uuid_vehiculo`. UK `subscripcion_vehiculos_uk01 (uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde)`.
- **`prod.facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos` exist** (F1.9 closed, `repo/factura.py`): atomic 4-table insert in `crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago`, all in one TX (KD-FACT-01).
- **`prod.factura_electronica` + `prod.envio_dian` exist** (F1.10 closed, `repo/factura_electronica.py` + `repo/resolucion_facturacion.py::assign_consecutivo`): atomic 2-table insert in `crear_factura_electronica_inicial` + `crear_envio_dian_inicial`, all in one TX (KD-FE-01).
- **`Clientes` ORM model** (`models/V/clientes.py`) re-declares 8 business columns + UK `clientes_uk01`. **No `repo/clientes.py` exists today** — F1.12 inlines the cliente lookup-or-create in `repo/venta_suscripcion.py::buscar_cliente_por_uuid_o_crear` (NEW). Not promoted to a public `repo/clientes.py` (out of scope; minimal-scope principle).
- **`Vehiculos` ORM model** (`models/V/vehiculos.py`). **No `repo/vehiculos.py` exists** — F1.12 inlines `buscar_o_crear_vehiculo_por_placa` in `repo/venta_suscripcion.py`.
- **`SubscripcionesCliente` + `SubscripcionVehiculos` ORM models** exist. No `repo/subscripciones.py` exists — F1.12 inlines the INSERT helpers in `repo/venta_suscripcion.py`.
- **`TipoSubscripciones` ORM model** (`models/V/tipo_subscripciones.py`) re-declares 6 columns + UK. `valor` and `duracion_dias` are READ for A-09 prorrateo calc.
- **Pydantic schemas** already exist for ALL 5 [V] tables (`schemas/clientes.py` lines 42-396 + `schemas/tipo_subscripciones.py` lines 14-72). F1.12 EXTENDS `schemas/clientes.py` with `VentaSuscripcionCreate` (new) + `VentaSuscripcionResponse` (new).
- **`repo/subscripcion_activa.py::resolve_active_subscription_for_exit`** exists (lines 93-141). **F1.12 reuses** for V4 placa-dup detection (reverse-direction: "is there ANY active subscription for placa?" — same query, return-truthy semantics).
- **`repo/placa.py`** exists: `FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")` + `FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")` + `detectar_tipo_vehiculo(session, placa)` → UUID. **F1.12 reuses** for V3 + V5.
- **`repo/versioned.py::close_and_insert`** exists (lines 45-196): the SOLE allowed bi-temporal writer for [V] tables; sets `vigente_desde = NOW()`, `vigente_hasta = NULL`, `estado = 'activo'`, server-set `created_at`/`created_by`, optional co-INSERT `log_transaccional` (PR6 hash chain extension). **F1.12 uses `current_uuid=None` for new INSERTs**.
- **`repo/versioned.py::current_version`** (lines 242-254) — cliente + vehiculo lookup by UUID.
- **`repo/factura.py::crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago`** (F1.9): atomic 4-table insert. KD-FACT-02 `lock_tarifas_sucursal_para_items` does `SELECT FOR SHARE` per-row (F1.12 locks `tipo_subscripciones` row instead — DEC-VENTA-04).
- **`repo/factura_electronica.py::crear_factura_electronica_inicial` + `crear_envio_dian_inicial`** (F1.10): atomic 2-table insert. `assign_consecutivo` takes `SELECT FOR UPDATE` on the resolution row + idempotency lookup by `(resolucion_uuid, source_event_uuid)` → returns next consecutivo.
- **`repo/idempotency.py`** — `guard()` (cache lookup) + `store_response()` (cache write). **F1.12 reuses** (DEC-IDEM-01, shared with F1.6/F1.9/F1.10/F1.11).
- **`api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()`** (lines 18-31). **F1.12 reuses** (DEC-VENTA-06, XR2 mirror).
- **`api/v1/facturacion.py` (F1.9)** lines 216-380 — canonical 12-step atomic create handler. **F1.12 references its shape verbatim** for the optional cobro sub-chain (Steps 5-9).
- **`api/v1/workflows_reimpresion.py` (F1.11)** — dedicated-router + KD-3 + tenant scope + Idempotency-Key pattern. **F1.12 references its shape verbatim** for the outer handler envelope (Steps 1, 2, 11).
- **`api/v1/clientes.py`** (lines 42-126) — existing `make_router` factory mount for the 5 [V] tables, all with `gestionar_clientes` permission. **F1.12 mounts on top of this router** via `router.include_router(...)` for the new dedicated endpoint (NOT via `make_router` — DEC-VENTA-05).
- **`schemas/clientes.py`** has `extra='forbid'` on `_Base` (`schemas/common.py`). **F1.12 uses** `VentaSuscripcionCreate(_Base)` for Layer-4 defense.
- **`static/test_no_raw_dml_on_lw_tables.py`** (F1.5 PR5-016) — AST walk blocks raw UPDATE/DELETE on `[L-W]` tables. F1.12 does NOT touch any `[L-W]` table; the `[V]` table walk `static/test_no_raw_upsert_on_v_tables.py` is the relevant gate (blocks raw UPDATE outside `repo/versioned.py::close_and_insert`).
- **MIGRATION 0029 (F1.11 head) — preamble** (lines 78-123) — the pre-flight `DO $$` pattern with `pg_catalog.pg_class` table-presence check + `RAISE EXCEPTION '0029_preflight_abort'`. **F1.12 mirrors this preamble** in MIGRATION 0030.
- **A-09 prorrateo rule** (plan.md line 460): "No hay columna para el monto prorrateado en `subscripciones_cliente`. Se calcula al momento de la venta (`valor_dia = plan.valor / duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes`) y el resultado **sí queda persistido**, pero en `factura_detalle.valor_unitario`/`subtotal` de la factura que se emite al vender la suscripción — no en la tabla de suscripción misma, que no necesita columna nueva." Trigger condition: `fecha_inicio_cobertura.day > 15` (plan.md line 1053 T2).
- **F1.12 is a "ampliación de producto"** (plan.md line 1016): the CU-06 original does not require this endpoint. It is justified by business need but lacks literal CU backing. The proposal phase records this scope decision.

### 2.1 Critical Architectural Conflict — Cross-domain atomicity (RESOLVED in §3)

The sdd-explore phase flags R1 MEDIUM — the fundamental design question of F1.12:

- F1.7 (POST /operacion/salidas) commits a single `[A]` row in 1 TX.
- F1.9 (POST /facturacion/factura) commits 4 tables in 1 TX (KD-FACT-01).
- F1.10 (POST /factura-electronica) commits 2 tables in 1 TX (KD-FE-01).
- F1.11 (POST /workflows/reimpresion-ticket) commits 1 `[L-W]` row + 1 `log_transaccional` in 1 TX (KD-TKT-01).
- **F1.12 commits up to 9 tables in 1 TX** — 5 [V] + optional 4 [A]/[L-E] + optional 2 [L-E]/[L-W] + `log_transaccional` rows.

Question: single `await session.commit()` for all of them, or explicit SAVEPOINTs? Section §3 documents the resolution.

---

## 3. Architectural Conflict Resolution — DEC-VENTA-01

This section is **mandatory** for the proposal. It documents R1 from §7 and records the resolution.

### 3.1 The conflict (R1 MEDIUM)

The handler must write to up to 9 tables. Two architectural choices are valid in PostgreSQL:

| Source | Statement | Authority weight |
|---|---|---|
| F1.9 KD-FACT-01 | "single `await session.commit()` covering all writes — 4 tables committed atomically" | **CANONICAL** for [A]+[L-E] |
| F1.10 KD-FE-01 | "handler commits ONCE; this module does NOT commit" | **CANONICAL** for [L-E]+[L-W] |
| PostgreSQL docs | SAVEPOINTs allow partial rollback within a TX | Valid but adds complexity |

### 3.2 The resolution — DEC-VENTA-01: single `await session.commit()` for ALL writes

**Resolution path** (mandated by F1.10 KD-FE-01 precedent):

1. **All helper functions (`crear_*`)** stay commit-free — they `session.add()` + `await session.flush()` only.
2. **One `await session.commit()` at the END of the handler body**, after all helper calls return.
3. **No SAVEPOINTs** in F1.12. If any helper raises, the entire TX rolls back (caller catches the HTTPException and the session is discarded by the FastAPI dependency teardown).
4. **Lock ordering** (KD-VENTA-02): `SELECT FOR UPDATE` on `prod.tipo_subscripciones` FIRST (Step 2) to serialize concurrent ventas on the same plan. `SELECT FOR UPDATE` on `prod.clientes` (if existing) AFTER (Step 3a). This avoids deadlocks.

### 3.3 Why this matters

- **Cross-domain atomicity is the entire point of F1.12** (plan.md line 1014: "sin que un fallo a mitad de camino deje datos inconsistentes"). A SAVEPOINT strategy would partially commit, leaving orphan clientes + vehiculos + subscripciones rows if the FE write failed.
- **The 9-table single commit is well within PostgreSQL's capabilities** — the [V] tables have minimal locking (UK checks), the [A]/[L-E] tables are INSERT-only, the [L-W] `envio_dian` is INSERT-only. No long-held locks.
- **The single-commit invariant becomes the AST walk contract** — `tests/static/test_venta_handler_single_commit.py` will scan the handler body and reject any second `await session.commit()` call (mirror of `test_fe_handler_single_commit.py`).
- **The lock ordering rule prevents deadlocks** under concurrent ventas. Plan A acquires plan lock first, plan B waits. Plan A then acquires cliente lock (or none, if new), plan B waits if same cliente. No cycle.

---

## 4. Endpoints

One endpoint, mounted under `/api/v1/clientes` (the resource logically belongs under `/clientes` — it is a sale ON a cliente).

### 4.1 `POST /api/v1/clientes/venta-suscripcion` (HU-F1.12-T1+T2+T3)

- **Purpose**: Single transactional sale of a subscription, optionally with cobro + FE.
- **Issuer dep**: `_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")`.
- **Permission**: `gestionar_clientes` (already seeded, reused via the existing factory mount's `permission_required`).
- **Request body** (`VentaSuscripcionCreate`, §9.1):
  ```jsonc
  {
    "cliente": {                          // OR uuid_cliente if existing
      "tipo_identificador": "NIT|CC|CE",
      "numero_identificacion": "...",
      "dv": "...",                         // validated by Pydantic, NOT persisted (DEC-VENTA-07)
      "nombre": "...",
      "apellido": "...",
      "telefono": "...",
      "email": "..."
    },
    "placas": ["ABC123", "XYZ789"],       // 1-2 items
    "uuid_tipo_subscripcion": "...",
    "fecha_inicio_cobertura": "2026-09-12",
    "cobrar_ahora": true,
    "emitir_factura_electronica": false,
    "medio_pago": "efectivo",
    "referencia": null
  }
  ```
- **Response (201)** (`VentaSuscripcionResponse`): nested UUIDs + optional cobro result.
- **Status codes**:
  - `201 Created` — happy path
  - `400 idempotency_key_required` (DEC-IDEM-01 middleware)
  - `403 tenant_scope_violation`
  - `403 permission_denied` (no `gestionar_clientes`)
  - `404 tipo_subscripcion_no_encontrado` (V2)
  - `404 cliente_no_encontrado` (V1 if `uuid_cliente` provided but missing)
  - `409 idempotency_conflict` (DEC-IDEM-01)
  - `409 tipo_subscripcion_no_vigente` (V2)
  - `422 placa_formato_invalido` (V3)
  - `422 tipo_vehiculo_invalido` (V3 — placa regex OK but catalog missing)
  - `422 suscripcion_duplicada_placa` (V4)
  - `422 tipo_vehiculo_incompatible` (V5)
  - `422 cantidad_maxima_excedida` (V6)
  - `422 plan_duracion_dias_invalido` (V2 edge — `duracion_dias=0`)
  - `422 nit_dv_invalido` (V1, NIT módulo 11)
  - `500 iva_no_configurado` (F1.9 V3 — only if `cobrar_ahora=true`)
- **Headers**: `Cache-Control: no-store` on EVERY response (DEC-VENTA-06, success + error).
- **Idempotency**: `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse).

---

## 5. Tables Touched

Five [V] tables (always) + four optional [A]/[L-E] tables (when `cobrar_ahora=true`) + two optional [L-W]/[L-E] tables (when `emitir_factura_electronica=true`) + `log_transaccional` rows (auto-co-inserted by helpers). NO schema changes.

### 5.1 `prod.tipo_subscripciones` [V] (READ + LOCK)

- **Operations**: V2 SELECT vigente row + `SELECT FOR UPDATE` row lock (KD-VENTA-02, DEC-VENTA-04).
- **Columns read**: `uuid`, `valor`, `duracion_dias`, `cantidad_maxima_vehiculos`, `mismo_tipo_vehiculo`, `tipo_cliente_permitido`.
- **Defense in depth**: bi-temporal VersionedBase guarantees at most one vigente row per `tipo`. Handler returns 409 `tipo_subscripcion_no_vigente` if lookup returns NULL.

### 5.2 `prod.clientes` [V] (LOOKUP-OR-CREATE)

- **Operations**: V1 SELECT by `uuid_cliente` OR INSERT via `repo.versioned.close_and_insert(current_uuid=None, new_attrs={...datos_cliente})`.
- **Columns write (INSERT)**: `tipo_identificador`, `numero_identificacion`, `nombre`, `apellido`, `telefono`, `email`, `uuid_tipo_persona`, `registro`. Versioning + audit + sync columns server-set. **No `dv` column** — `dv` is validated by Pydantic then discarded (DEC-VENTA-07).
- **Indexes**: UK `clientes_uk01 (tipo_identificador, numero_identificacion, vigente_desde)`.
- **Defense in depth**: bi-temporal close+insert guarantees `vigente_desde` uniqueness. Pydantic `ClientesCreate._validar_nit_dv` blocks NIT mismatch at Layer 4.

### 5.3 `prod.vehiculos` [V] (LOOKUP-OR-CREATE per placa)

- **Operations**: V3 SELECT by `placa` (vigente row) OR INSERT via `close_and_insert(current_uuid=None, new_attrs={"placa": ..., "uuid_tipo_vehiculo": ...})`.
- **Columns write (INSERT)**: `placa`, `uuid_tipo_vehiculo` (from `repo.placa.detectar_tipo_vehiculo`).
- **Indexes**: UK `vehiculos_uk01 (placa, vigente_desde)`.
- **Defense in depth**: Pydantic `StringConstraints(min_length=1, max_length=16)` + `repo.placa.FORMATO_AUTO/FORMATO_MOTO` regex at V3.

### 5.4 `prod.subscripciones_cliente` [V] (INSERT only)

- **Operations**: INSERT via direct `model_cls(**attrs, created_at=..., created_by=...)` (no close needed — first version).
- **Columns write (INSERT)**: `uuid_cliente`, `uuid_sucursal`, `uuid_tipo_subscripcion`, `fecha_inicio_cobertura` (from request), `fecha_vencimiento` (computed: `fecha_inicio_cobertura + plan.duracion_dias` days).
- **Defense in depth**: bi-temporal `vigente_desde` discriminator. **No UPDATE path** (F1.12 only INSERTs; renewals = future HU).

### 5.5 `prod.subscripcion_vehiculos` [V] (INSERT bulk)

- **Operations**: V9 bulk INSERT after `pg_advisory_xact_lock(uuid_subscripcion_cliente)`. ONE advisory lock + N INSERTs.
- **Columns write (INSERT)**: `uuid_subscripcion_cliente`, `uuid_vehiculo` (one per placa).
- **Indexes**: UK `subscripcion_vehiculos_uk01 (uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde)`.

### 5.6 `prod.facturas` [L-E] (INSERT only — optional, when `cobrar_ahora=true`)

- **Operations**: F1.9 `crear_factura_evento` reused. `uuid_cliente` derived from `venta_cliente.uuid`.

### 5.7 `prod.factura_detalle` [A] (INSERT bulk — optional)

- **Operations**: F1.9 `crear_factura_detalle_bulk` reused. When A-09 prorrateo applies, the SINGLE detail row carries `concepto='subscripcion_mensual_prorrateada'`, `valor_unitario=monto_proporcional`, `cantidad=1`, `subtotal=monto_proporcional`.

### 5.8 `prod.factura_impuestos` [A] (INSERT — optional)

- **Operations**: F1.9 `crear_factura_impuesto_iva` reused.

### 5.9 `prod.factura_pagos` [A] (INSERT — optional)

- **Operations**: F1.9 `crear_factura_pago` reused.

### 5.10 `prod.factura_electronica` [L-E] (INSERT — optional, when `emitir_factura_electronica=true`)

- **Operations**: F1.10 `crear_factura_electronica_inicial` reused. `assign_consecutivo` row-locks the resolution row.

### 5.11 `prod.envio_dian` [L-W] (INSERT initial — optional)

- **Operations**: F1.10 `crear_envio_dian_inicial` reused. `uuid_envio_padre=NULL`, `estado='pendiente'`.

### 5.12 `prod.log_transaccional` [A] (INSERT — multiple)

- **Operations**: AUTO-INSERTED via `repo/versioned.py::close_and_insert` (one per [V] INSERT). F1.12 NOT responsible — they are co-transactional by design.

### 5.13 Sync catalog pre-flight (DEC-VENTA-08 WITHDRAWN — RESOLVED 2026-09-15)

| Table | Entry exists | Direction | Broadcast | Hooks | Source line |
|---|---|---|---|---|---|
| `tipo_subscripciones` | YES | `cloud_to_branch` | `all_branches` | `identity_reconciler` (pre) | `sync_entries_v.py:133-147` |
| `clientes` | YES | `bidirectional` | `all_branches` | `clientes_natural_key_normalizer` + `identity_reconciler` (pre) | `sync_entries_v.py:451-465` |
| `vehiculos` | YES | `bidirectional` | `all_branches` | `vehiculos_natural_key_normalizer` + `identity_reconciler` (pre) + `plate_change_cascade` (post) | `sync_entries_v.py:483-500` |
| `subscripciones_cliente` | YES | `bidirectional` | `subscription` | (no `natural_key` by design — renewal = new row) | `sync_entries_v.py:511-523` |
| `subscripcion_vehiculos` | YES | `bidirectional` | `subscription` | `subscription_lifecycle` (pre) | `sync_entries_v.py:525-552` |

**All 5 [V] entries pre-existing.** MIGRATION 0030 has NO sync catalog seed operation. DEC-VENTA-08 (initially speculated) is WITHDRAWN.

---

## 6. Decisions

### 6.1 DEC-VENTA-01 — Single `await session.commit()` for ALL writes (RESOLVES R1 MEDIUM)

**Decision**: One `await session.commit()` at Step 10 of the handler body, covering 5 [V] rows + 4 optional [A]/[L-E] rows + 2 optional [L-W]/[L-E] rows + N `log_transaccional` rows. No SAVEPOINTs.

**Rationale**: F1.10 KD-FE-01 precedent. Cross-domain atomicity is the entire business requirement (plan.md line 1014). PostgreSQL handles single TX with 9+ inserts easily (no long-held locks).

**Alternatives considered**:
- *SAVEPOINT per write group* — REJECTED. Partial commits would leave orphan clientes + vehiculos rows if FE write failed.
- *Separate endpoint per write group* — REJECTED. Defeats the purpose of F1.12.

### 6.2 DEC-VENTA-02 — Lock ordering: `tipo_subscripciones` first, then `clientes` (KD-VENTA-02)

**Decision**: `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (Step 2) BEFORE any other lock. If `uuid_cliente` is provided (existing), `SELECT FOR UPDATE` on `prod.clientes` (Step 3a) AFTER.

**Rationale**: Prevents deadlocks under concurrent ventas. Plan A acquires plan lock first, plan B waits. Plan A then acquires cliente lock (or none, if new), plan B waits if same cliente. No cycle.

**Alternatives considered**:
- *Lock `clientes` first* — REJECTED. Risk of cycle: plan A holds cliente lock waiting for plan lock; plan B holds plan lock waiting for cliente lock.
- *No locks* — REJECTED. Concurrent ventas on the same plan could race on the prorrateo calc (different days → different amounts).

### 6.3 DEC-VENTA-03 — A-09 prorrateo persistence in `factura_detalle` ONLY when `cobrar_ahora=true`

**Decision**: A-09 prorrateo (`valor_dia = plan.valor / duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes`) is computed at sale time. If `cobrar_ahora=true`, persist in `factura_detalle.valor_unitario`/`subtotal` of the SINGLE detail row with `concepto='subscripcion_mensual_prorrateada'`. If `cobrar_ahora=false`, the prorrateo amount is computed for the response body's `monto_prorrateado` field ONLY (not persisted — the subscription is recorded at full value, billing is decoupled).

**Rationale**: A-09 explicit (plan.md line 460). When the operator does NOT charge at the counter (deferred billing / pay-later), the prorrateo is irrelevant to the DB.

**Alternatives considered**:
- *Add `valor_dia` column to `subscripciones_cliente`* — REJECTED. plan.md A-09 explicitly forbids this.
- *Persist prorrateo even when `cobrar_ahora=false`* — REJECTED. Out of scope (the cobro is the only reason to persist).

### 6.4 DEC-VENTA-04 — Plan lock uses `SELECT FOR UPDATE` (NOT FOR SHARE) — diverges from F1.9 KD-FACT-02

**Decision**: KD-VENTA-02 takes `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (exclusive). F1.9 took `SELECT FOR SHARE` on `prod.tarifas_sucursal` (shared, multiple readers OK).

**Rationale**: A plan read mutates the sale semantics (the `fecha_inicio_cobertura` is captured). Concurrent ventas on the same plan with different `fecha_inicio_cobertura` would produce different prorrateo amounts; exclusive lock serializes the calc. KD-FACT-02's `FOR SHARE` is correct for F1.9 because tarifa read doesn't mutate the calc; F1.12's plan read DOES.

**Alternatives considered**:
- *FOR SHARE on `tipo_subscripciones`* — REJECTED. Two concurrent ventas could compute prorrateo on stale `fecha_inicio_cobertura`.
- *No lock + post-commit recompute* — REJECTED. The prorrateo is the sale amount, not a derived report.

### 6.5 DEC-VENTA-05 — Dedicated `APIRouter` for `venta-suscripcion` (NOT via `make_router`)

**Decision**: NEW `api/v1/clientes_venta.py` with `router = APIRouter(prefix="/clientes", tags=["clientes"])` mounted into the existing `clientes.py` via `router.include_router(venta_suscripcion_router)`. The endpoint is a CUSTOM POST with the 10-step chain (NOT a `make_router`-mounted resource).

**Rationale**: The factory mount `make_router` emits generic POST + GET routes on the 5 individual [V] tables. The `venta-suscripcion` endpoint writes to ALL 5 in a single TX — it does not map cleanly to a single resource. F1.11 precedent: `workflows_reimpresion.py` is a dedicated router for the same reason.

**Alternatives considered**:
- *Add `venta-suscripcion` to the `make_router` mount* — REJECTED. The factory does not support cross-table atomic writes.
- *Separate top-level router `/venta-suscripcion`* — REJECTED. The resource logically belongs under `/clientes` (it's a sale ON a cliente).

### 6.6 DEC-VENTA-06 — `Cache-Control: no-store` on EVERY response (XR2 mirror from F1.11)

**Decision**: All responses (201 + 4xx + 5xx) carry `Cache-Control: no-store`. Both success (`apply_no_store_header`) and error (`no_store_headers()` in `HTTPException(headers=...)`) routes.

**Rationale**: XR2 mirror from F1.11 DEC-TKT-06. A proxy that serves a stale `venta-suscripcion` response would silently accept out-of-date state (e.g., the cliente's email or telefono would not be the current one).

### 6.7 DEC-VENTA-07 — `dv` field is validated but NOT persisted (F1.9 REQ-OPS-058 reuse)

**Decision**: `VentaSuscripcionCreate.cliente.dv` is validated via `ClientesCreate._validar_nit_dv` Pydantic validator (already in place, `schemas/clientes.py` lines 82-102). The `dv` value is NOT a column on `prod.clientes` — it is consumed by the validator and discarded before `close_and_insert(new_attrs={...})`.

**Rationale**: F1.9 established `dv` as a Pydantic-only validation field. No schema change to `prod.clientes` is needed.

### 6.8 DEC-VENTA-08 — WITHDRAWN (sync catalog all 5 [V] entries pre-existing)

**Decision**: Originally speculated that `subscripciones_cliente` + `subscripcion_vehiculos` were MISSING from `sync_entries_v.py`. **Pre-flight inspection (2026-09-15) confirms FALSE** — all 5 [V] entries exist (`sync_entries_v.py` lines 133, 451, 483, 511, 525). MIGRATION 0030 Op 1 sync catalog seed is NOT needed.

**Rationale**: See §5.13 table. The earlier draft's DEC-VENTA-08 + MIGRATION 0030 Op 1 sync seed are WITHDRAWN.

---

## 7. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Cross-domain atomicity** — 9-table single commit is the largest TX in the codebase. A bug in any helper could leave inconsistent state. | **MEDIUM (RESOLVED)** | DEC-VENTA-01 (§6.1) + KD-VENTA-01 AST walk `tests/static/test_venta_handler_single_commit.py`. Verify all helpers do NOT call `session.commit()`. |
| **R2** | **A-09 prorrateo calc** — `valor_dia = plan.valor / plan.duracion_dias` requires `plan.duracion_dias > 0`. A null/zero `duracion_dias` would divide by zero. | **MEDIUM** | Server-side defense: Pydantic `gt(0)` validator at lookup time + `ZeroDivisionError` catch in `calcular_prorrateo` → 422 `plan_duracion_dias_invalido`. |
| **R3** | **`mismo_tipo_vehiculo` constraint** — derived `uuid_tipo_vehiculo` from placa regex must match across all placas when `plan.mismo_tipo_vehiculo=true`. | **MEDIUM** | V5 `validar_placas_mismo_tipo_vehiculo` helper raises 422 `tipo_vehiculo_incompatible` BEFORE any INSERT. |
| **R4** | **Placa duplicate detection** — must check for ANY active subscripcion on the placa at this branch via `resolve_active_subscription_for_exit` (reverse-direction). | **MEDIUM** | V4 helper raises 422 `suscripcion_duplicada_placa`. R22's defense-in-depth (branch-pinned WHERE clause) carries over. |
| **R5** | **Idempotency-Key reuse (DEC-IDEM-01)** — same as F1.6/F1.9/F1.10/F1.11. A replay with same key + same body returns cached response; same key + different body returns 409. | **LOW** | DEC-IDEM-01 already in place. `IdempotencyKeyMiddleware` owns the cache. |
| **R6** | **Cache-Control no-store (DEC-VENTA-06)** — every response must carry the header, including the 422 Pydantic validation errors. | **LOW** | DEC-VENTA-06. The `_helpers.no_store_headers()` + `apply_no_store_header()` helpers are reused verbatim from F1.6. |
| **R7** | **Sync catalog entries** — `subscripciones_cliente` + `subscripcion_vehiculos` ALREADY registered in `sync_entries_v.py` (pre-flight confirmed 2026-09-15). | **RESOLVED** | DEC-VENTA-08 WITHDRAWN. No action needed. All 5 [V] entries ship pre-existing. |
| **R8** | **Permiso `gestionar_clientes` is already seeded** — but role grants may be incomplete. An operador without the role would get 403 at `requires_issuer` (Layer 1) or `require_permission` (factory mount). | **LOW** | DEC-VENTA-05 mounts on the existing `clientes.py` factory which already enforces the permission. The new endpoint inherits the gate. |
| **R9** | **Concurrency on multiple ventas for the SAME plan** — KD-VENTA-02 `SELECT FOR UPDATE` serializes. Two ventas on DIFFERENT plans run in parallel. | **LOW** | Intentional. Independent ventas are independent. |
| **R10** | **`pg_advisory_xact_lock(uuid_subscripcion_cliente)` is NOT yet implemented in code** — REQ-OP-08 documents the contract but the actual call is missing from the codebase. F1.12 adds it. | **LOW** | REQ-OP-08 invariant: lock MUST be acquired before the bulk INSERT. New `crear_subscripcion_vehiculos_bulk` helper enforces. |

---

## 8. Defense in Depth

5 layers mirror the F1.10 + F1.11 precedent:

### Layer 1 — KD-3 issuer chain + permission check

`_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")`. The dedicated router inherits the factory mount's permission gate via `gestionar_clientes` (DEC-VENTA-05).

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

## 9. API Contracts

Append to `schemas/clientes.py` + update `__all__`.

### 9.1 Request schemas

```python
class VentaSuscripcionCreate(_Base):
    """HU-F1.12: POST /api/v1/clientes/venta-suscripcion payload.

    cliente OR uuid_cliente (discriminated union): exactly one is required.
    For embedded cliente, dv is validated by Pydantic (DEC-VENTA-07) but
    NOT persisted — `prod.clientes` has no `dv` column.

    extra='forbid' (inherited from _Base) blocks client smuggling of
    uuid_sucursal, vigente_desde, estado, created_at, created_by,
    monto_prorrateado (server-derived).
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


class VentaSuscripcionResponse(_Base):
    """HU-F1.12: POST /api/v1/clientes/venta-suscripcion response (201).

    Nested UUIDs + optional cobro result. monto_prorrateado is server-derived
    (A-09) — null when cobrar_ahora=false (DEC-VENTA-03).
    """
    uuid_cliente: uuid_lib.UUID
    uuid_subscripcion: uuid_lib.UUID
    uuid_vehiculos: list[uuid_lib.UUID]
    uuid_sucursal: uuid_lib.UUID
    fecha_inicio_cobertura: datetime.date
    fecha_vencimiento: datetime.date
    valor_total_plan: Decimal
    monto_prorrateado: Decimal | None = None    # A-09, only when cobrar_ahora=true
    uuid_factura: uuid_lib.UUID | None = None
    uuid_factura_electronica: uuid_lib.UUID | None = None
    uuid_envio_dian: uuid_lib.UUID | None = None
```

### 9.2 Typed error schemas

```python
class TipoSubscripcionNoVigenteError(_Base):
    error: Literal["tipo_subscripcion_no_vigente"]
    uuid_tipo_subscripcion: str


class TipoSubscripcionNoEncontradoError(_Base):
    error: Literal["tipo_subscripcion_no_encontrado"]
    uuid_tipo_subscripcion: str


class SubscripcionDuplicadaPlacaError(_Base):
    error: Literal["suscripcion_duplicada_placa"]
    placa: str


class TipoVehiculoIncompatibleError(_Base):
    error: Literal["tipo_vehiculo_incompatible"]
    tipos_encontrados: list[str]


class CantidadMaximaExcedidaError(_Base):
    error: Literal["cantidad_maxima_excedida"]
    cantidad_maxima_vehiculos: int


class PlanDuracionDiasInvalidoError(_Base):
    error: Literal["plan_duracion_dias_invalido"]


class ClienteNoEncontradoError(_Base):
    error: Literal["cliente_no_encontrado"]
    uuid_cliente: str
```

Append to `schemas/clientes.py` + update `__all__`. `extra='forbid'` (inherited from `_Base`) rejects client smuggling.

---

## 10. Handler Skeleton

One handler, 10-step chain mirroring F1.10 KD-FE-01 + F1.11 KD-TKT-01 shape.

```python
# api/v1/clientes_venta.py — NEW (~120 LOC)

router = APIRouter(prefix="/clientes", tags=["clientes"])


@router.post(
    "/venta-suscripcion",
    response_model=VentaSuscripcionResponse,
    status_code=201,
    responses={
        400: {"model": IdempotencyKeyRequiredError},
        403: {"model": TenantScopeViolationError},
        404: {"model": TipoSubscripcionNoEncontradoError},
        409: {"model": TipoSubscripcionNoVigenteError},
        422: {"model": SubscripcionDuplicadaPlacaError},
    },
)
async def venta_suscripcion(
    response: Response,
    payload: VentaSuscripcionCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_venta_suscripcion_issuer_dep),
) -> VentaSuscripcionResponse:
    no_store = no_store_headers()

    # Step 1: KD-3 issuer + Idempotency-Key middleware (resolved via DI)

    # Step 2 (KD-VENTA-02 + DEC-VENTA-04): SELECT FOR UPDATE on prod.tipo_subscripciones
    plan = await repo_venta.buscar_tipo_subscripcion_vigente_por_uuid(
        session, uuid_tipo_subscripcion=payload.uuid_tipo_subscripcion
    )
    if plan is None:
        raise HTTPException(404, {"error": "tipo_subscripcion_no_encontrado", "uuid_tipo_subscripcion": str(payload.uuid_tipo_subscripcion)}, headers=no_store)

    # Layer 2 — Tenant scope post-V1
    if ctx.issuer_prefix == "operador-" and ctx.sucursal_uuid is not None:
        # The plan is global; the sale is anchored at the operator's branch.
        target_sucursal = ctx.sucursal_uuid
    else:
        target_sucursal = ctx.sucursal_uuid  # admin: branch from JWT

    # Step 3 (V1): cliente lookup-or-create (new via close_and_insert(current_uuid=None); existing via current_version)
    cliente = await repo_venta.buscar_cliente_por_uuid_o_crear(
        session,
        uuid_cliente=payload.uuid_cliente,
        datos_cliente=payload.cliente,
        actor_uuid=ctx.actor_uuid,
    )

    # Step 4 (V3): per-placa lookup-or-create prod.vehiculos
    vehiculos = []
    for placa in payload.placas:
        vehiculo, _was_created = await repo_venta.buscar_o_crear_vehiculo_por_placa(
            session, placa=placa, actor_uuid=ctx.actor_uuid
        )
        vehiculos.append(vehiculo)

    # Step 5 (V5): validar_placas_mismo_tipo_vehiculo
    await repo_venta.validar_placas_mismo_tipo_vehiculo(session, plan=plan, vehiculos=vehiculos)

    # Step 6 (V6): validar_cantidad_maxima_vehiculos
    await repo_venta.validar_cantidad_maxima_vehiculos(session, plan=plan, n_placas=len(payload.placas))

    # Step 7 (V4): validar_placa_duplicada_subscripcion (per placa)
    for placa in payload.placas:
        await repo_venta.validar_placa_duplicada_subscripcion(
            session, placa=placa, uuid_sucursal=target_sucursal, fecha_inicio_cobertura=payload.fecha_inicio_cobertura
        )

    # Step 8 (V7): A-09 prorrateo compute
    monto_proporcional = repo_venta.calcular_prorrateo(plan=plan, fecha_inicio_cobertura=payload.fecha_inicio_cobertura)

    # Step 9 (V8 + V9): INSERT subscripcion_cliente + junction rows (with advisory lock)
    fecha_vencimiento = payload.fecha_inicio_cobertura + timedelta(days=plan.duracion_dias)
    subscripcion = await repo_venta.crear_subscripcion_cliente(
        session, actor_uuid=ctx.actor_uuid, uuid_cliente=cliente.uuid, uuid_sucursal=target_sucursal,
        uuid_tipo_subscripcion=plan.uuid, fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
        fecha_vencimiento=fecha_vencimiento,
    )
    junction_rows = await repo_venta.crear_subscripcion_vehiculos_bulk(
        session, actor_uuid=ctx.actor_uuid, uuid_subscripcion_cliente=subscripcion.uuid,
        uuid_vehiculos=[v.uuid for v in vehiculos],
    )

    # Step 8a (optional): F1.9 cobro sub-chain (when cobrar_ahora=true)
    uuid_factura = None
    if payload.cobrar_ahora:
        uuid_factura = await _factura_sub_chain(
            session, cliente=cliente, subscripcion=subscripcion, plan=plan,
            monto_proporcional=monto_proporcional, medio_pago=payload.medio_pago, referencia=payload.referencia,
            ctx=ctx,
        )

    # Step 8b (optional): F1.10 FE sub-chain (when emitir_factura_electronica=true)
    uuid_fe = None
    uuid_envio = None
    if payload.emitir_factura_electronica and uuid_factura is not None:
        uuid_fe, uuid_envio = await _fe_sub_chain(
            session, uuid_factura=uuid_factura, ctx=ctx,
        )

    # Step 10: KD-VENTA-01 SINGLE COMMIT
    await session.commit()

    apply_no_store_header(response)
    return VentaSuscripcionResponse(
        uuid_cliente=cliente.uuid,
        uuid_subscripcion=subscripcion.uuid,
        uuid_vehiculos=[v.uuid for v in vehiculos],
        uuid_sucursal=target_sucursal,
        fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
        fecha_vencimiento=fecha_vencimiento,
        valor_total_plan=plan.valor,
        monto_prorrateado=monto_proporcional if payload.cobrar_ahora else None,
        uuid_factura=uuid_factura,
        uuid_factura_electronica=uuid_fe,
        uuid_envio_dian=uuid_envio,
    )
```

Mount in `api/v1/clientes.py` (`+5 LOC`):
```python
from .clientes_venta import router as venta_suscripcion_router

router.include_router(venta_suscripcion_router)
```

---

## 11. Tests

7 test files + 2 AST walks + 1 migration test, ~120 LOC tests + ~260 LOC production + ~30 LOC migration = ~415 LOC cumulative.

### 11.1 `tests/unit/test_venta_suscripcion.py` (~50 LOC, **4 tests mandated by plan.md line 1047**)

- `test_cliente_nuevo_venta_exitosa_returns_201` — happy path, new cliente + 1 placa + plan "mensual" + `cobrar_ahora=false`.
- `test_cliente_existente_lookup_by_uuid` — happy path, existing cliente by `uuid_cliente` + 2 placas.
- `test_plan_mismo_tipo_vehiculo_rechaza_placas_mixtas` — 422 `tipo_vehiculo_incompatible`.
- `test_placa_duplicada_subscripcion_vigente_rechaza` — 422 `suscripcion_duplicada_placa`.

### 11.2 `tests/unit/test_venta_suscripcion_repo.py` (~30 LOC, 3 tests)

- `buscar_cliente_por_uuid_o_crear` (new + existing paths).
- `buscar_tipo_subscripcion_vigente_por_uuid` (vigente + non-vigente).
- `calcular_prorrateo` (after-day-15 + before-day-15 + zero-duracion edge case).

### 11.3 `tests/unit/test_venta_suscripcion_schemas.py` (~20 LOC, 2 tests)

- `extra='forbid'` injections: `vigente_desde`, `estado`, `created_by`, `uuid_sucursal`.
- `placas` list range: 0 items → 422, 3 items → 422, 1-2 items → OK.

### 11.4 `tests/integration/test_venta_suscripcion_e2e.py` (~30 LOC, 1 test)

- Full happy path: cliente nuevo + placa + plan "mensual" + `cobrar_ahora=true` + `emitir_factura_electronica=true`. Verifies ALL 9 rows present in DB after commit (1 cliente + 1 vehiculo + 1 subscripcion + 1 junction + 1 factura + 1 factura_detalle + 1 factura_impuestos + 1 factura_pagos + 1 factura_electronica + 1 envio_dian).

### 11.5 `tests/static/test_venta_handler_single_commit.py` (~15 LOC, 1 AST walk)

- KD-VENTA-01 single-commit invariant. The walk scans `api/v1/clientes_venta.py` and asserts EXACTLY ONE `await session.commit()` call. Mirror of `test_fe_handler_single_commit.py`.

### 11.6 `tests/static/test_venta_handler_no_raw_dml.py` (~15 LOC, 1 AST walk)

- No raw INSERT/UPDATE/DELETE on [V] tables outside `repo/venta_suscripcion.py` helpers. Mirror of `test_no_raw_upsert_on_v_tables.py` (deeper: per-module scope).

### 11.7 `tests/integration/test_migration_0030_noop.py` (~10 LOC, 1 test)

- `alembic upgrade head` is idempotent. `alembic downgrade -1` reverses cleanly. No schema changes applied (verify via `\d prod.tipo_subscripciones` column count unchanged).

Total: ~9 verification artifacts.

---

## 12. Out of Scope (F2.x+)

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

## 13. Requirements (REQ-OPS-083..090)

The following REQ-OPS-NNN placeholders will be formalized by `sdd-spec` in `openspec/changes/hu-f1-12-venta-suscripcion/specs/operations/spec.md`:

- **REQ-OPS-083 (NEW)** — `POST /api/v1/clientes/venta-suscripcion` contract: `VentaSuscripcionCreate` input (`{cliente|uuid_cliente, placas[1-2], uuid_tipo_subscripcion, fecha_inicio_cobertura, cobrar_ahora?, emitir_factura_electronica?, medio_pago?, referencia?}`) + `VentaSuscripcionResponse` output (nested UUIDs + optional cobro). KD-3 issuer chain (`requires_issuer("operador-", "admin-")`); `Cache-Control: no-store`; `Idempotency-Key` HTTP header (DEC-IDEM-01).

- **REQ-OPS-084 (NEW, DEC-VENTA-01)** — Single-commit atomic invariant: ONE `await session.commit()` at Step 10 covers 5 [V] + optional 4 [A]/[L-E] + optional 2 [L-W]/[L-E] + log_transaccional rows. No SAVEPOINTs. Enforced by KD-VENTA-01 AST walk.

- **REQ-OPS-085 (NEW, DEC-VENTA-02 + KD-VENTA-02)** — Lock ordering rule. `SELECT FOR UPDATE` on `prod.tipo_subscripciones` FIRST (Step 2); `SELECT FOR UPDATE` on `prod.clientes` (Step 3a, only when `uuid_cliente` provided) AFTER. Prevents deadlocks under concurrent ventas.

- **REQ-OPS-086 (NEW, DEC-VENTA-03)** — A-09 prorrateo rule. `valor_dia = plan.valor / plan.duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes` when `fecha_inicio_cobertura.day > 15`. Persistence in `factura_detalle.valor_unitario`/`subtotal` ONLY when `cobrar_ahora=true`; null in response body otherwise.

- **REQ-OPS-087 (NEW, DEC-VENTA-04)** — Plan lock type: `SELECT FOR UPDATE` (exclusive) on `prod.tipo_subscripciones`. Diverges from F1.9 KD-FACT-02 (`SELECT FOR SHARE` on `prod.tarifas_sucursal`). Required because plan read mutates the sale semantics (captured `fecha_inicio_cobertura`).

- **REQ-OPS-088 (NEW, DEC-VENTA-05)** — Dedicated `APIRouter` for `venta-suscripcion` mounted under `/clientes` prefix via `router.include_router`. NOT via `make_router` factory. Endpoint inherits `gestionar_clientes` permission from the factory mount.

- **REQ-OPS-089 (NEW, DEC-VENTA-07)** — `dv` field is validated by Pydantic (`ClientesCreate._validar_nit_dv`, REQ-OPS-058 reuse from F1.9) but NOT persisted. `prod.clientes` has no `dv` column.

- **REQ-OPS-090 (NEW, DEC-VENTA-06)** — `Cache-Control: no-store` on EVERY response (201 + 4xx + 5xx). Success path: `apply_no_store_header(response)`. Error path: `HTTPException(headers=no_store_headers())`.

Additional defense-in-depth XR:

- **REQ-OPS-XR5 (NEW)** — Single-commit AST walk: `tests/static/test_venta_handler_single_commit.py` enforces EXACTLY ONE `await session.commit()` call in `api/v1/clientes_venta.py::venta_suscripcion`. Mirror of F1.10's XR1 (single-commit) + F1.11's XR4 (insert-only).

---

## 14. Migrations

**MIGRATION 0030** (~30 LOC, NO-OP audit trail). `down_revision = "0029_reimpresion_siembra_and_permiso_anular"`.

```python
"""0030_venta_suscripcion_optional.py — MIGRATION 0030 (NO-OP audit trail).

Pre-flight 2026-09-15 confirmed:
- All 5 [V] tables F1.12 touches already exist with required columns
  (cantidad_maxima_vehiculos, mismo_tipo_vehiculo, duracion_dias).
- All 5 [V] sync catalog entries already registered in sync_entries_v.py
  (lines 133, 451, 483, 511, 525). DEC-VENTA-08 WITHDRAWN.
- `gestionar_clientes` permission already seeded at 0001 line 3292 area.

This migration ships for audit trail and head-pointer continuity only.
Both upgrade() and downgrade() are no-ops.
"""
from alembic import op

revision = "0030_venta_suscripcion_optional"
down_revision = "0029_reimpresion_siembra_and_permiso_anular"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NO-OP: schema unchanged (all 5 [V] tables pre-exist in migration 0001).
    # NO-OP: sync catalog unchanged (all 5 [V] entries pre-exist in sync_entries_v.py).
    # NO-OP: permisos unchanged (gestionar_clientes already seeded).
    # Audit trail only — see proposal §14.
    pass


def downgrade() -> None:
    # NO-OP: this migration added no DDL, no rows, no grants.
    pass
```

### Pre-flight DO $$ block (mandatory in upgrade preamble)

```sql
DO $$
BEGIN
    ASSERT (
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='prod' AND table_name IN (
            'tipo_subscripciones', 'clientes', 'vehiculos',
            'subscripciones_cliente', 'subscripcion_vehiculos'
        )
    ) = 5, 'F1.12 requires all 5 [V] tables to exist';
END $$;
```

---

## 15. References

- `plan.md` lines 1010-1054 (HU-F1.12 definition, 3 atomic tasks T1..T3, 4 tests mandated at line 1047, 260 LOC budget)
- `plan.md` lines 1016, 1053 (scope decision: "ampliación de producto" + A-09 prorrateo decay rule)
- `plan.md` line 460 (A-09 prorrateo — no `monto_prorrateado` column on `subscripciones_cliente`)
- `modelo_datos_er.mmd` line 105 (`tipo_subscripciones`), 449 (`clientes`), 496 (`subscripciones_cliente`), 519 (`vehiculos`), 538 (`subscripcion_vehiculos`)
- `modelo_datos_er.mmd` lines 1138-1145 (FK relationships: `clientes → subscripciones_cliente`, `tipo_subscripciones → subscripciones_cliente`, `subscripciones_cliente → subscripcion_vehiculos`, `vehiculos → subscripcion_vehiculos`)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones`), 435-452 (`clientes`), 454-465 (`vehiculos`), 483-496 (`subscripciones_cliente`), 498-509 (`subscripcion_vehiculos`)
- `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head, pre-flight DO $$ pattern)
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py` lines 133-147 (`tipo_subscripciones`), 451-465 (`clientes`), 483-500 (`vehiculos`), 511-523 (`subscripciones_cliente`), 525-552 (`subscripcion_vehiculos`) — **all 5 [V] entries verified pre-existing 2026-09-15**
- `backend/packages/parkos_core/src/parkos_core/models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py` (ORM models, all existing)
- `backend/packages/parkos_core/src/parkos_core/repo/{factura,factura_electronica,resolucion_facturacion,subscripcion_activa,placa,versioned,idempotency}.py` (helpers reused)
- `backend/packages/parkos_core/src/parkos_core/schemas/{clientes,tipo_subscripciones,facturacion}.py` (schemas extended)
- `backend/packages/parkos_core/src/parkos_core/api/v1/{facturacion,workflows_reimpresion,clientes,_helpers}.py` (handler envelope references)
- `openspec/specs/operations/spec.md` lines 2517-3076 (F1.10 REQ-OPS-064..074 + XR1..XR3 + F1.11 REQ-OPS-075..080 + XR4)
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/proposal.md` (sibling precedent for 16-section structure)
- `openspec/changes/hu-f1-12-venta-suscripcion/exploration.md` (DEC-VENTA-08 WITHDRAWN — sync catalog pre-flight 2026-09-15)

---

## 16. Cross-HU Implications

| HU | Relationship | Implication |
|---|---|---|
| **F1.9 (closed)** | Reuses F1.9 atomic 4-table cobro chain (`crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago`) when `cobrar_ahora=true`. KD-VENTA-01 commits F1.9 helpers in the same TX. | No shared atomic transaction boundary; F1.12 hosts the unified commit. |
| **F1.10 (closed)** | Reuses F1.10 atomic 2-table FE chain (`crear_factura_electronica_inicial` + `crear_envio_dian_inicial`) when `emitir_factura_electronica=true`. `assign_consecutivo` row-locks the resolution row. | Same TX as cobro + subscription writes. |
| **F1.11 (closed)** | Reuses F1.11 dedicated-router pattern (`api/v1/workflows_reimpresion.py` shape) for the outer handler envelope (Steps 1, 2, 11). Reuses DEC-TKT-06 `Cache-Control: no-store` (XR2 mirror). | No shared atomic transaction. |
| **F1.13 (Arqueo + cierre_dia)** | Independent. F1.13 may consume `prod.subscripciones_cliente` for `cierre_dia` count (potential). | May need to add `estado='activo' AND vigente_hasta IS NULL` filter to F1.13 aggregation. F1.12 does NOT add this filter; F1.13 owns. |
| **F1.14 (sync estado)** | F1.14 may need to expose `subscripciones_cliente` + `subscripcion_vehiculos` for the operator dashboard. | Read-only — already configured by the existing sync catalog entries (`sync_entries_v.py:511-552`). |
| **HU-F7.x (frontend cliente flow)** | Consumer of the new endpoint once Fase 8 ships. | Frontend owns the create-cliente UX flow. |
| **HU-F9.x (frontend venta-suscripcion flow)** | Primary consumer of `POST /clientes/venta-suscripcion`. | Frontend owns the counter-sale UX flow. |
| **Fase 4 (notifications)** | Deferred. Email/SMS on subscription confirmation. | Not in F1.12 scope. |

---

**End of proposal.**
