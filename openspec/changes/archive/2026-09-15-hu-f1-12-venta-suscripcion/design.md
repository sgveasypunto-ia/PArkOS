# Design: HU-F1.12 — Venta atómica de suscripción (cliente + vehículos + suscripción + cobro opcional + FE opcional en 1 TX)

> **Change**: `hu-f1-12-venta-suscripcion`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.12 — `POST /api/v1/clientes/venta-suscripcion` (1 dedicated handler) — Given `datos_cliente` (new) OR `uuid_cliente` (existing) + 1-2 placas (mismo tipo si `plan.mismo_tipo_vehiculo=true`) + `uuid_tipo_subscripcion` (vigente) + `fecha_inicio_cobertura` + optional `cobrar_ahora`/`medio_pago` + optional `emitir_factura_electronica`, server-resolves the plan + vehicles, then in a **single `await session.commit()` (KD-VENTA-01)** writes up to 9 tables: 5 `[V]` (clientes + vehiculos + subscripciones_cliente + subscripcion_vehiculos + tipo_subscripciones lock-only) + 4 optional `[A]`/`[L-E]` cobro (`facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos`) when `cobrar_ahora=true` + 2 optional `[L-W]`/`[L-E]` FE (`factura_electronica` + `envio_dian`) when `emitir_factura_electronica=true` + N `log_transaccional` co-INSERTs.
> **Date**: 2026-09-15
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `ddfe1f8`; F1.1..F1.11 closed)
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (16 sections, ~485 LOC, DEC-VENTA-01..07 + DEC-VENTA-08 WITHDRAWN, KD-VENTA-01..02, R1 MEDIUM RESOLVED, R2..R10) + `specs/operations/spec.md` (REQ-OPS-083..090 + REQ-OPS-XR5, 8 new requirements in Given/When/Then/And form + 1 cross-cutting XR5).
> **Cross-references**: `modelo_datos_er.mmd` (`tipo_subscripciones` [V] line 105, `clientes` [V] line 449, `vehiculos` [V] line 519, `subscripciones_cliente` [V] line 496, `subscripcion_vehiculos` [V] line 538, `facturas` [L-E], `factura_detalle` [A], `factura_impuestos` [A], `factura_pagos` [A], `factura_electronica` [L-E], `envio_dian` [L-W]); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (`tipo_subscripciones` lines 195-210, `clientes` lines 435-452, `vehiculos` lines 454-465, `subscripciones_cliente` lines 483-496, `subscripcion_vehiculos` lines 498-509, FK relationships lines 1138-1145); `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head — pre-flight `DO $$` pattern reused for MIGRATION 0030); `backend/packages/parkos_core/src/parkos_core/models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py`; `backend/packages/parkos_core/src/parkos_core/repo/{factura,factura_electronica,resolucion_facturacion,subscripcion_activa,placa,versioned,idempotency}.py`; `backend/packages/parkos_core/src/parkos_core/schemas/{clientes,tipo_subscripciones,facturacion}.py`; `backend/packages/parkos_core/src/parkos_core/api/v1/{facturacion,workflows_reimpresion,clientes,_helpers}.py`; `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py` (lines 133, 451, 483, 511, 525 — all 5 [V] entries verified pre-existing 2026-09-15); `plan.md` lines 1010-1054 (HU-F1.12 definition, 3 atomic tasks T1..T3, 260 LOC production budget, 4 tests mandated at line 1047, A-09 prorrateo decay rule at line 460); `openspec/specs/operations/spec.md` lines 2517-3076 (F1.10 REQ-OPS-064..074 + XR1..XR3 + F1.11 REQ-OPS-075..080 + XR4).
> **Precedents mirrored**: F1.11 (REQ-OPS-075..080 + XR4, KD-3 issuer `requires_issuer("operador-","admin-")` verbatim, KD-TKT-01 single-commit AST walk, DEC-TKT-06 `Cache-Control: no-store`, DEC-IDEM-01 `Idempotency-Key` middleware, dedicated `APIRouter` pattern), F1.10 (REQ-OPS-064..074 + XR1..XR3, KD-FE-01 single-commit, `assign_consecutivo` `SELECT FOR UPDATE` pattern), F1.9 (REQ-OPS-053..063, KD-FACT-01 single-commit + KD-FACT-02 `FOR SHARE` lock pattern, 12-step atomic create handler canonical shape, `crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago` helpers), F1.7 (REQ-OPS-042..052, KD-S2 tenant scope post-V1), F1.6 (REQ-OPS-034..041, KD-7 pre-flight pattern, DEC-IDEM-01 Idempotency-Key header, `get_tenant_ctx` derivation).

---

## 1. Title & Goal

**Design goal.** Deliver HU-F1.12: the back-end `POST /api/v1/clientes/venta-suscripcion` endpoint that closes the **operador-facing atomic sale-at-the-counter workflow** on top of the already-shipped `prod.tipo_subscripciones` / `prod.clientes` / `prod.vehiculos` / `prod.subscripciones_cliente` / `prod.subscripcion_vehiculos` `[V]` tables and the F1.9 (atomic factura) + F1.10 (atomic FE) machinery by enforcing the **KD-VENTA-01 single-commit invariant** (exactly one `await session.commit()` per handler body covering up to 9 tables + `log_transaccional` rows) plus the **KD-VENTA-02 plan lock** (`SELECT FOR UPDATE` exclusive on `prod.tipo_subscripciones` vigente row, DEC-VENTA-04) plus the **5-layer defense in depth** (KD-3 issuer chain + tenant scope post-V1 + KD-VENTA-01 single-commit + KD-VENTA-02 plan lock + handler 422/409/404 mapping + `Cache-Control: no-store`).

The design enforces **DEC-VENTA-01** (single `await session.commit()` at Step 10 covers 5 [V] + optional 4 [A]/[L-E] + optional 2 [L-W]/[L-E] + log_transaccional rows; NO SAVEPOINT; RESOLVES R1 MEDIUM), **DEC-VENTA-02** (lock ordering: plan lock FIRST on `prod.tipo_subscripciones`, cliente lock AFTER on `prod.clientes` if existing — KD-VENTA-02 ordering rule prevents AB-BA deadlocks), **DEC-VENTA-03** (A-09 prorrateo `valor_dia = plan.valor / plan.duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes` when `fecha_inicio_cobertura.day > 15` — persistence in `factura_detalle.valor_unitario`/`subtotal` ONLY when `cobrar_ahora=true`; null in response body otherwise), **DEC-VENTA-04** (plan lock type `SELECT FOR UPDATE` exclusive — diverges from F1.9 KD-FACT-02 `FOR SHARE` because plan read mutates sale semantics — `fecha_inicio_cobertura` is captured and A-09 prorrateo calc depends on it), **DEC-VENTA-05** (dedicated `APIRouter` mounted via `router.include_router(venta_suscripcion_router)` on the existing `clientes.py` factory — NOT via `make_router` factory which does not support cross-table atomic writes), **DEC-VENTA-06** (`Cache-Control: no-store` on EVERY response — XR2 mirror from F1.11 DEC-TKT-06), **DEC-VENTA-07** (`dv` field validated by Pydantic per REQ-OPS-058 but NOT persisted — `prod.clientes` has no `dv` column; consumed by `ClientesCreate._validar_nit_dv` and discarded before `close_and_insert(new_attrs={...})`), plus the **KD-VENTA-01 single-commit invariant** (mirror of F1.10 KD-FE-01 + F1.11 KD-TKT-01) and the **KD-VENTA-02 plan lock** (`SELECT FOR UPDATE` exclusive on `prod.tipo_subscripciones` vigente row at Step 2).

The handler enforces 9 validations server-side across the 10-step chain:

- V1 cliente lookup-or-create: `datos_cliente` → `repo.versioned.close_and_insert(current_uuid=None, new_attrs={...})`; `uuid_cliente` → `repo.versioned.current_version(uuid=...)`; raises 404 `cliente_no_encontrado` if existing UUID missing, 422 `nit_dv_invalido` if NIT módulo 11 fails (REQ-OPS-058 reuse).
- V2 plan lock + lookup: `SELECT * FROM prod.tipo_subscripciones WHERE uuid=:p AND vigente_hasta IS NULL ORDER BY vigente_desde DESC LIMIT 1 FOR UPDATE` (KD-VENTA-02 + DEC-VENTA-04); raises 404 `tipo_subscripcion_no_encontrado` if missing, 422 `plan_duracion_dias_invalido` if `duracion_dias=0` (ZeroDivisionError catch).
- V3 per-placa lookup-or-create `prod.vehiculos`: regex validation via `repo.placa.FORMATO_AUTO/FORMATO_MOTO`; `repo.placa.detectar_tipo_vehiculo(session, placa)` → UUID; `close_and_insert(current_uuid=None, ...)` for new; raises 422 `placa_formato_invalido`, 422 `tipo_vehiculo_invalido`.
- V4 per-placa duplicate detection: `resolve_active_subscription_for_exit(session, placa=..., uuid_sucursal=..., fecha_inicio_cobertura=...)` (F1.7 reuse, reverse-direction) raises 422 `suscripcion_duplicada_placa`.
- V5 `mismo_tipo_vehiculo` constraint: when `plan.mismo_tipo_vehiculo=true`, all placas MUST derive the SAME `uuid_tipo_vehiculo` via `validar_placas_mismo_tipo_vehiculo`; raises 422 `tipo_vehiculo_incompatible`.
- V6 `cantidad_maxima_vehiculos` constraint: `len(placas) <= plan.cantidad_maxima_vehiculos` via `validar_cantidad_maxima_vehiculos`; raises 422 `cantidad_maxima_excedida`.
- V7 A-09 prorrateo compute: `valor_dia = plan.valor / plan.duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes` (only applied when `fecha_inicio_cobertura.day > 15`).
- V8 optional F1.9 cobro sub-chain (`crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago`) when `cobrar_ahora=true`; A-09 prorrateo persisted in `factura_detalle` single row with `concepto='subscripcion_mensual_prorrateada'`.
- V8b optional F1.10 FE sub-chain (`assign_consecutivo` + `crear_factura_electronica_inicial` + `crear_envio_dian_inicial`) when `emitir_factura_electronica=true`.
- V9 INSERT `prod.subscripciones_cliente` + `pg_advisory_xact_lock(uuid_subscripcion_cliente)` + bulk INSERT `prod.subscripcion_vehiculos` (one row per placa, REQ-OP-08 advisory lock).

All responses carry `Cache-Control: no-store`. Sized at **~260 LOC production** per `plan.md` line 1049 (= ~120 LOC `api/v1/clientes_venta.py` dedicated handler + ~140 LOC `repo/venta_suscripcion.py` 9 helpers + 6 typed exceptions + ~30 LOC MIGRATION 0030 NO-OP audit trail + ~5 LOC `api/v1/clientes.py` mount + ~120 LOC tests + ~30 LOC AST walks). Total cumulative: ~415 LOC.

**One new handler + one new repo module + two new Pydantic schemas (request + response) + 7 typed error schemas + one NO-OP MIGRATION 0030 + one router mount extension. No factory changes, no sync catalog changes, no new tables, no new FKs, no new permissions.**

---

## 2. Context & Background

`plan.md` lines **1010-1054** define HU-F1.12 as Fase-1 backend prerequisite for the operador-facing atomic sale-at-the-counter workflow. The hard architectural constraints are **DEC-VENTA-01** (single `await session.commit()` at Step 10 covering all writes — RESOLVES R1 MEDIUM cross-domain atomicity), **DEC-VENTA-02** (lock ordering: plan lock FIRST on `prod.tipo_subscripciones`, cliente lock AFTER on `prod.clientes` if existing — KD-VENTA-02 AB-BA deadlock prevention), **DEC-VENTA-03** (A-09 prorrateo persistence in `factura_detalle` ONLY when `cobrar_ahora=true`; null in response otherwise), **DEC-VENTA-04** (`SELECT FOR UPDATE` exclusive on `prod.tipo_subscripciones` — diverges from F1.9 KD-FACT-02 `FOR SHARE` because plan read mutates sale semantics via A-09 prorrateo calc), **DEC-VENTA-05** (dedicated `APIRouter` mounted via `router.include_router` — NOT via `make_router` factory), **DEC-VENTA-06** (`Cache-Control: no-store` on EVERY response), **DEC-VENTA-07** (`dv` validated by Pydantic but NOT persisted — `prod.clientes` has no `dv` column), the existing pre-existing tables (`prod.tipo_subscripciones` [V] lines 195-210 of migration 0001; `prod.clientes` [V] lines 435-452; `prod.vehiculos` [V] lines 454-465; `prod.subscripciones_cliente` [V] lines 483-496; `prod.subscripcion_vehiculos` [V] lines 498-509; `prod.facturas` [L-E] + `prod.factura_detalle` [A] + `prod.factura_impuestos` [A] + `prod.factura_pagos` [A] from F1.9; `prod.factura_electronica` [L-E] + `prod.envio_dian` [L-W] from F1.10), the existing ORM models (`models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py`), the existing `repo/placa.py::detectar_tipo_vehiculo` + `FORMATO_AUTO` + `FORMATO_MOTO` regexes (V3 + V5), the existing `repo/subscripcion_activa.py::resolve_active_subscription_for_exit` (V4 reverse-direction reuse), the existing `repo/versioned.py::close_and_insert(current_uuid=None)` + `current_version(uuid=...)` (V1 lookup-or-create), the existing `repo/factura.py::crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago` (V8 cobro sub-chain), the existing `repo/factura_electronica.py::crear_factura_electronica_inicial` + `crear_envio_dian_inicial` + `repo/resolucion_facturacion.py::assign_consecutivo` (V8b FE sub-chain), the existing `repo/idempotency.py` (DEC-IDEM-01 reuse, Idempotency-Key middleware), the existing `api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()` (DEC-VENTA-06 reuse), the existing `api/v1/facturacion.py` lines 216-380 (F1.9 canonical 12-step atomic create handler — referenced for the optional V8 cobro sub-chain shape), the existing `api/v1/workflows_reimpresion.py` (F1.11 dedicated-router + KD-3 + tenant scope + Idempotency-Key pattern — referenced for the outer handler envelope shape), the existing `api/v1/clientes.py` lines 42-126 (`make_router` factory mount for the 5 [V] tables, all with `gestionar_clientes` permission — F1.12 mounts on top via `router.include_router(venta_suscripcion_router)`, NOT via `make_router`), the existing `schemas/clientes.py` (`ClientesCreate._validar_nit_dv` Pydantic validator at lines 82-102 — REQ-OPS-058 NIT módulo 11 reuse from F1.9), the existing `schemas/clientes.py::_Base` (`extra='forbid'` — Layer 4 defense), the existing `static/test_no_raw_upsert_on_v_tables.py` AST walk (Layer 4 enforcement — F1.12 deepens with `tests/static/test_venta_handler_no_raw_dml.py` per-module scope), the `MIGRATION 0029` preamble pattern (lines 78-123 — `DO $$` block with `pg_catalog.pg_class` table-presence check + `RAISE EXCEPTION '0029_preflight_abort'` — F1.12 mirrors this preamble in MIGRATION 0030 pre-flight `DO $$` for the 5 [V] tables), the A-09 prorrateo rule (plan.md line 460: `valor_dia = plan.valor / duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes`; persisted in `factura_detalle.valor_unitario`/`subtotal` ONLY when cobrar_ahora=true — NEVER in `subscripciones_cliente` which has no column for it; trigger condition `fecha_inicio_cobertura.day > 15`), and the F1.12 "ampliación de producto" scope decision (plan.md line 1016: CU-06 original does not require this endpoint; business need justifies the work but lacks literal CU backing — proposal phase records this scope decision).

**The backend has no atomic sale-at-the-counter endpoint today**, creating five concrete risks that HU-F1.12 resolves:

1. **No atomic cliente + vehiculos + suscripcion write.** Today the operador must compose the sale across multiple endpoints (no `clientes.py` write path, no `vehiculos.py` write path, no `subscripciones.py` write path — only bi-temporal `close_and_insert` helpers per [V] table exist individually in `repo/versioned.py`). Each write is its own TX, leaving the system in an inconsistent state on mid-flight failure. F1.12 introduces the single `await session.commit()` covering 5 [V] rows atomically.
2. **No F1.9 cobro + subscription composition.** Today a subscription sale with `cobrar_ahora=true` cannot happen in one TX — the subscription writes commit BEFORE the factura writes (or vice versa). F1.12 composes the optional V8 cobro sub-chain (F1.9 helpers) inside the same KD-VENTA-01 commit.
3. **No F1.10 FE + subscription composition.** Today the FE flow follows the cobro flow in a separate TX. F1.12 composes the optional V8b FE sub-chain (F1.10 helpers + `assign_consecutivo`) inside the same KD-VENTA-01 commit.
4. **A-09 prorrateo has no persistence path.** Today A-09 prorrateo is computed in the front-end or as a derived report, never persisted with the subscription. F1.12 computes at sale time + persists in `factura_detalle.valor_unitario`/`subtotal` (single detail row with `concepto='subscripcion_mensual_prorrateada'`) when `cobrar_ahora=true` (DEC-VENTA-03). The prorrateo amount is reflected in the response body's `monto_prorrateado` field (null when `cobrar_ahora=false`).
5. **No `prod.tipo_subscripciones` plan concurrency control.** Today multiple concurrent ventas on the same plan could compute prorrateo on stale `fecha_inicio_cobertura` snapshots (R9 LOW). F1.12 introduces KD-VENTA-02 `SELECT FOR UPDATE` exclusive lock on the vigente plan row at Step 2 — held until the single commit at Step 10.

F1.12 closes the operador-facing atomic sale-at-the-counter workflow. The work is **1 handler + 1 repo module + 2 request/response schemas + 7 typed error schemas + 1 NO-OP MIGRATION 0030 + 1 router mount extension**. MIGRATION 0030 is a NO-OP audit trail because pre-flight (2026-09-15) confirms all 5 [V] tables already exist with the required columns (`cantidad_maxima_vehiculos`, `mismo_tipo_vehiculo`, `duracion_dias`), all 5 [V] sync catalog entries are already registered, and `gestionar_clientes` permission is already seeded (migration 0001 line 3292). **DEC-VENTA-08 (initially speculated as needing to seed missing sync entries) is WITHDRAWN** — all 5 [V] entries pre-exist at `sync_entries_v.py` lines 133, 451, 483, 511, 525.

The contract is captured in **REQ-OPS-083..090 + REQ-OPS-XR5** (added by `sdd-spec` to `specs/operations/spec.md`):

- **REQ-OPS-083** — Single-commit atomic invariant: ONE `await session.commit()` at Step 10 covers 5 [V] + optional 4 [A]/[L-E] + optional 2 [L-W]/[L-E] + log_transaccional rows. No SAVEPOINTs. Enforced by KD-VENTA-01 AST walk.
- **REQ-OPS-084** — Plan lock type + ordering: `SELECT FOR UPDATE` exclusive on `prod.tipo_subscripciones` (KD-VENTA-02 + DEC-VENTA-04). Diverges from F1.9 KD-FACT-02 (`FOR SHARE`). Required because plan read mutates sale semantics via A-09 prorrateo.
- **REQ-OPS-085** — Lock ordering rule: plan lock FIRST (Step 2), cliente lock AFTER (Step 3a, only when `uuid_cliente` provided). Prevents deadlocks under concurrent ventas.
- **REQ-OPS-086** — A-09 prorrateo rule: `valor_dia = plan.valor / plan.duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes` when `fecha_inicio_cobertura.day > 15`. Persistence in `factura_detalle.valor_unitario`/`subtotal` ONLY when `cobrar_ahora=true`; null in response body otherwise.
- **REQ-OPS-087** — Plan lock type rationale: `SELECT FOR UPDATE` (exclusive) on `prod.tipo_subscripciones`. Diverges from F1.9 KD-FACT-02 (`SELECT FOR SHARE` on `prod.tarifas_sucursal`). Required because plan read mutates the sale semantics (captured `fecha_inicio_cobertura`).
- **REQ-OPS-088** — Dedicated `APIRouter` for `venta-suscripcion` mounted under `/clientes` prefix via `router.include_router`. NOT via `make_router` factory. Endpoint inherits `gestionar_clientes` permission from the factory mount.
- **REQ-OPS-089** — `dv` field is validated by Pydantic (`ClientesCreate._validar_nit_dv`, REQ-OPS-058 reuse from F1.9) but NOT persisted. `prod.clientes` has no `dv` column.
- **REQ-OPS-090** — `Cache-Control: no-store` on EVERY response (201 + 4xx + 5xx). Success path: `apply_no_store_header(response)`. Error path: `HTTPException(headers=no_store_headers())`.
- **REQ-OPS-XR5** — Single-commit AST walk: `tests/static/test_venta_handler_single_commit.py` enforces EXACTLY ONE `await session.commit()` call in `api/v1/clientes_venta.py::venta_suscripcion`. Mirror of F1.10's XR1 (single-commit) + F1.11's XR4 (insert-only).

F1.12 is consumed by **F1.13** (Arqueo + cierre_dia; may need to add `estado='activo' AND vigente_hasta IS NULL` filter to `prod.subscripciones_cliente` aggregation per sucursal per day), **F1.14** (sync estado; exposes `prod.subscripciones_cliente` + `prod.subscripcion_vehiculos` for the operator dashboard — already configured by the existing sync catalog entries), **HU-F7.x** (frontend cliente flow; consumer of the new endpoint once Fase 8 ships), **HU-F9.x** (frontend venta-suscripcion flow; primary consumer of `POST /clientes/venta-suscripcion`), **Fase 4** (notifications; email/SMS on subscription confirmation — out of F1.12 scope).

---

## 3. Architectural Conflict Resolution — DEC-VENTA-01 (R1 MEDIUM RESOLVED)

This section is **mandatory** for the design. It documents R1 from the sdd-explore phase (observation §R1 MEDIUM) and records the resolution per `proposal.md §3`.

### 3.1 The conflict (R1 MEDIUM)

The handler must write to up to 9 tables (5 always + 4 optional cobro + 2 optional FE). Three architectural choices are valid in PostgreSQL:

| Source | Statement | Authority weight |
|---|---|---|
| F1.9 KD-FACT-01 | "single `await session.commit()` covering all writes — 4 tables committed atomically" | **CANONICAL** for [A]+[L-E] |
| F1.10 KD-FE-01 | "handler commits ONCE; this module does NOT commit" (verifies `assign_consecutivo` + `crear_factura_electronica_inicial` + `crear_envio_dian_inicial` all run in caller's session) | **CANONICAL** for [L-E]+[L-W] |
| F1.11 KD-TKT-01 | "exactly one `await session.commit()` per handler body" | **CANONICAL** for [L-W] insert-only |
| PostgreSQL docs | SAVEPOINTs allow partial rollback within a TX | Valid but adds complexity |

### 3.2 The resolution — DEC-VENTA-01: single `await session.commit()` for ALL writes

**Resolution path** (mandated by F1.10 KD-FE-01 + F1.11 KD-TKT-01 precedent):

1. **All helper functions (`crear_*` + `close_and_insert`)** stay commit-free — they `session.add()` + `await session.flush()` only. Mirrors F1.9 + F1.10 + F1.11 helpers verbatim.
2. **One `await session.commit()` at Step 10 of the handler body**, after all helper calls return (5 [V] + optional 4 [A]/[L-E] + optional 2 [L-W]/[L-E] + N log_transaccional rows).
3. **No SAVEPOINTs** in F1.12. If any helper raises, the entire TX rolls back (caller catches the HTTPException and the session is discarded by the FastAPI dependency teardown).
4. **Lock ordering** (KD-VENTA-02): `SELECT FOR UPDATE` on `prod.tipo_subscripciones` FIRST (Step 2) to serialize concurrent ventas on the same plan. `SELECT FOR UPDATE` on `prod.clientes` (if existing) AFTER (Step 3a). This avoids deadlocks.

### 3.3 Why this matters

- **Cross-domain atomicity is the entire point of F1.12** (plan.md line 1014: "sin que un fallo a mitad de camino deje datos inconsistentes"). A SAVEPOINT strategy would partially commit, leaving orphan clientes + vehiculos + subscripciones rows if the FE write failed.
- **The 9-table single commit is well within PostgreSQL's capabilities** — the [V] tables have minimal locking (UK checks), the [A]/[L-E] tables are INSERT-only, the [L-W] `envio_dian` is INSERT-only. No long-held locks.
- **The single-commit invariant becomes the AST walk contract** — `tests/static/test_venta_handler_single_commit.py` will scan the handler body and reject any second `await session.commit()` call (mirror of `test_fe_handler_single_commit.py` + `test_workflow_handler_single_commit.py`).
- **The lock ordering rule prevents deadlocks** under concurrent ventas. Plan A acquires plan lock first, plan B waits. Plan A then acquires cliente lock (or none, if new), plan B waits if same cliente. No cycle.

### 3.4 What changes in the codebase

**Production code (~260 LOC)**:
- NEW `api/v1/clientes_venta.py` — dedicated `APIRouter` with 1 handler (~120 LOC, DEC-VENTA-05).
- NEW `repo/venta_suscripcion.py` — 9 helpers + 7 typed exceptions (~140 LOC).
- NEW `schemas/clientes.py::VentaSuscripcionCreate` + `VentaSuscripcionResponse` + 7 typed error schemas (~70 LOC extension).
- EXTEND `api/v1/clientes.py` — `router.include_router(venta_suscripcion_router)` mount (~5 LOC).
- NEW `migrations/versions/0030_venta_suscripcion_optional.py` — NO-OP audit trail (~30 LOC).

**Tests (~120 LOC)**:
- 4 unit tests in `tests/unit/test_venta_suscripcion.py` (plan.md line 1047 mandate).
- 3 repo unit tests in `tests/unit/test_venta_suscripcion_repo.py`.
- 2 schema unit tests in `tests/unit/test_venta_suscripcion_schemas.py`.
- 1 e2e in `tests/integration/test_venta_suscripcion_e2e.py`.
- 1 AST walk in `tests/static/test_venta_handler_single_commit.py` (KD-VENTA-01).
- 1 AST walk in `tests/static/test_venta_handler_no_raw_dml.py` (DEC-VENTA-05 enforcement).
- 1 migration idempotency test in `tests/integration/test_migration_0030_noop.py`.

### 3.5 What changes in MIGRATION 0030 (conditional — RESOLVED as NO-OP)

```sql
-- Op 0: pre-flight DO $$ (KD-7 F1.6 + F1.7 + F1.9 + F1.10 + F1.11 pattern)
DO $$
BEGIN
    ASSERT (
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='prod' AND table_name IN (
            'tipo_subscripciones', 'clientes', 'vehiculos',
            'subscripciones_cliente', 'subscripcion_vehiculos'
        )
    ) = 5, 'F1.12 requires all 5 [V] tables to exist';
    RAISE NOTICE '0030_preflight: 5/5 tablas OK (5 [V] tables)';
END $$;

-- upgrade() and downgrade() are NO-OPs — schema unchanged, sync catalog
-- unchanged (all 5 [V] entries pre-existing per DEC-VENTA-08 WITHDRAWN),
-- permisos unchanged (gestionar_clientes already seeded).
```

The migration is fully idempotent (pre-flight is read-only, `upgrade()` and `downgrade()` are no-ops). The `DO $$` pre-flight aborts with a typed `0030_preflight_abort` exception if any of the 5 [V] tables is missing.

---

## 4. Architecture Overview

```
HTTPS POST /api/v1/clientes/venta-suscripcion
        Body: VentaSuscripcionCreate
        │      {cliente | uuid_cliente, placas[1-2], uuid_tipo_subscripcion,
        │       fecha_inicio_cobertura, cobrar_ahora?, emitir_factura_electronica?,
        │       medio_pago?, referencia?}
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        │  permission_required="gestionar_clientes" (inherited from factory mount)
        │  Idempotency-Key: <uuid>  (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10 + F1.11)
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/clientes_venta.py  (NEW, +120 LOC, 1 dedicated handler)               │
│                                                                              │
│ @router.post("/venta-suscripcion", response_model=VentaSuscripcionResponse,  │
│              status_code=201)                                                │
│ async def venta_suscripcion(response, payload, session, ctx, _claims)        │
│                                                                              │
│  1. KD-3 issuer claims (DI-resolved)                                         │
│      _claims = requires_issuer("operador-", "admin-")                       │
│      ctx = get_tenant_ctx from JWT                                            │
│                                                                              │
│  2. V2 KD-VENTA-02 + DEC-VENTA-04 — SELECT FOR UPDATE on plan:              │
│      plan = await repo_venta.buscar_tipo_subscripcion_vigente_por_uuid(     │
│          session, uuid_tipo_subscripcion=payload.uuid_tipo_subscripcion       │
│      )                                                                         │
│      if plan is None:                                                         │
│          raise 404 {"error":"tipo_subscripcion_no_encontrado", ...}          │
│                                                                              │
│  2a. Layer 2 — Tenant scope post-V1 (KD-S2 analog from F1.7):              │
│      target_sucursal = ctx.sucursal_uuid                                       │
│      if ctx.issuer_prefix == "operador-" and target_sucursal != ctx...:      │
│          raise 403 {"error":"tenant_scope_violation"}                       │
│                                                                              │
│  3. V1 cliente lookup-or-create:                                              │
│      cliente = await repo_venta.buscar_cliente_por_uuid_o_crear(           │
│          session, uuid_cliente=payload.uuid_cliente,                          │
│          datos_cliente=payload.cliente, actor_uuid=ctx.actor_uuid,            │
│      )                                                                         │
│                                                                              │
│  3a. (Optional) V3a — SELECT FOR UPDATE on clientes (only when existing):   │
│      if payload.uuid_cliente is not None:                                     │
│          cliente_row = SELECT ... FOR UPDATE on prod.clientes.uuid=:c       │
│          (DEC-VENTA-02: AFTER plan lock, BEFORE any INSERT)                  │
│                                                                              │
│  4. V3 per-placa lookup-or-create prod.vehiculos:                            │
│      for placa in payload.placas:                                            │
│          vehiculo, _was_created = await repo_venta.buscar_o_crear_           │
│              vehiculo_por_placa(session, placa=placa, actor_uuid=ctx...)      │
│                                                                              │
│  5. V5 validar_placas_mismo_tipo_vehiculo:                                    │
│      await repo_venta.validar_placas_mismo_tipo_vehiculo(                   │
│          session, plan=plan, vehiculos=vehiculos                              │
│      )                                                                         │
│                                                                              │
│  6. V6 validar_cantidad_maxima_vehiculos:                                    │
│      await repo_venta.validar_cantidad_maxima_vehiculos(                    │
│          session, plan=plan, n_placas=len(payload.placas)                    │
│      )                                                                         │
│                                                                              │
│  7. V4 per-placa placa-duplicate:                                            │
│      for placa in payload.placas:                                            │
│          await repo_venta.validar_placa_duplicada_subscripcion(            │
│              session, placa=placa, uuid_sucursal=target_sucursal,            │
│              fecha_inicio_cobertura=payload.fecha_inicio_cobertura           │
│          )                                                                     │
│                                                                              │
│  8. V7 A-09 prorrateo compute:                                                │
│      monto_proporcional = repo_venta.calcular_prorrateo(                    │
│          plan=plan, fecha_inicio_cobertura=payload.fecha_inicio_cobertura    │
│      )                                                                         │
│                                                                              │
│  9. V9 INSERT subscripcion_cliente + junction rows (with advisory lock):     │
│      fecha_vencimiento = payload.fecha_inicio_cobertura                       │
│          + timedelta(days=plan.duracion_dias)                                │
│      subscripcion = await repo_venta.crear_subscripcion_cliente(           │
│          session, actor_uuid=ctx.actor_uuid,                                  │
│          uuid_cliente=cliente.uuid, uuid_sucursal=target_sucursal,           │
│          uuid_tipo_subscripcion=plan.uuid,                                   │
│          fecha_inicio_cobertura=payload.fecha_inicio_cobertura,              │
│          fecha_vencimiento=fecha_vencimiento,                                │
│      )                                                                         │
│      junction_rows = await repo_venta.crear_subscripcion_vehiculos_bulk(   │
│          session, actor_uuid=ctx.actor_uuid,                                 │
│          uuid_subscripcion_cliente=subscripcion.uuid,                        │
│          uuid_vehiculos=[v.uuid for v in vehiculos],                        │
│      )  # pg_advisory_xact_lock INSIDE the helper (REQ-OP-08)               │
│                                                                              │
│  8a. (Optional) F1.9 cobro sub-chain (when cobrar_ahora=true):              │
│      uuid_factura = None                                                       │
│      if payload.cobrar_ahora:                                                 │
│          uuid_factura = await _factura_sub_chain(                            │
│              session, cliente=cliente, subscripcion=subscripcion,            │
│              plan=plan, monto_proporcional=monto_proporcional,              │
│              medio_pago=payload.medio_pago, referencia=payload.referencia,  │
│              ctx=ctx,                                                         │
│          )                                                                     │
│                                                                              │
│  8b. (Optional) F1.10 FE sub-chain (when emitir_factura_electronica=true):  │
│      uuid_fe = None; uuid_envio = None                                       │
│      if payload.emitir_factura_electronica and uuid_factura is not None:     │
│          uuid_fe, uuid_envio = await _fe_sub_chain(                          │
│              session, uuid_factura=uuid_factura, ctx=ctx,                    │
│          )                                                                     │
│                                                                              │
│ 10. KD-VENTA-01 SINGLE COMMIT:                                                │
│      await session.commit()  # UN solo commit (covers all 9 tables + log)   │
│                                                                              │
│ 11. DEC-VENTA-06 — Cache-Control: no-store + response shape:                │
│      apply_no_store_header(response)                                          │
│      return VentaSuscripcionResponse(                                        │
│          uuid_cliente=cliente.uuid, uuid_subscripcion=subscripcion.uuid,     │
│          uuid_vehiculos=[v.uuid for v in vehiculos],                        │
│          uuid_sucursal=target_sucursal,                                      │
│          fecha_inicio_cobertura=payload.fecha_inicio_cobertura,              │
│          fecha_vencimiento=fecha_vencimiento,                                │
│          valor_total_plan=plan.valor,                                         │
│          monto_prorrateado=monto_proporcional if payload.cobrar_ahora       │
│                            else None,  # DEC-VENTA-03                       │
│          uuid_factura=uuid_factura,                                          │
│          uuid_factura_electronica=uuid_fe,                                  │
│          uuid_envio_dian=uuid_envio,                                          │
│      )                                                                         │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                                       ▲
        │ AST walk single-commit (KD-VENTA-01)  │ AST walk no-raw-DML (DEC-VENTA-05)
        │ for venta_suscripcion                 │ for venta_suscripcion
tests/static/test_venta_handler_single_commit.py
tests/static/test_venta_handler_no_raw_dml.py
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Repo helpers (NEW):                                                          │
│   repo/venta_suscripcion.py   (~140 LOC) — 9 helpers + 7 typed exceptions    │
│                                                                              │
│ Repo helpers (REUSED verbatim, NO modify):                                   │
│   repo/versioned.py::close_and_insert (F1.5) — used for V1 + V3             │
│   repo/versioned.py::current_version (F1.5) — used for V1 lookup             │
│   repo/placa.py::detectar_tipo_vehiculo (F1.7) — used for V3 + V5           │
│   repo/placa.py::FORMATO_AUTO/FORMATO_MOTO regex — used for V3                │
│   repo/subscripcion_activa.py::resolve_active_subscription_for_exit (F1.7) │
│     — used for V4 (reverse-direction query: "is there ANY active for placa?")│
│   repo/factura.py::crear_factura_evento + crear_factura_detalle_bulk +      │
│     crear_factura_impuesto_iva + crear_factura_pago (F1.9) — used for V8    │
│   repo/factura.py::compute_total (F1.9) — V8 total recompute                │
│   repo/factura_electronica.py::crear_factura_electronica_inicial +           │
│     crear_envio_dian_inicial (F1.10) — used for V8b                          │
│   repo/resolucion_facturacion.py::assign_consecutivo (F1.10) — V8b FE numbering│
│   repo/impuestos.py::obtener_iva_vigente (F1.9) — V8 IVA lookup             │
│   repo/idempotency.py::guard + store_response (F1.6) — DEC-IDEM-01 reuse    │
│                                                                              │
│ Schemas (MODIFY):                                                            │
│   schemas/clientes.py     (+70 LOC) — VentaSuscripcionCreate +              │
│                                       VentaSuscripcionResponse +             │
│                                       7 typed error schemas                  │
│                                                                              │
│ Tables operational (READ + INSERT):                                          │
│   prod.tipo_subscripciones  [V]  — Step 2 V2 SELECT FOR UPDATE (KD-VENTA-02)│
│   prod.clientes             [V]  — Step 3 V1 SELECT (existing) or INSERT    │
│                                           (new via close_and_insert)         │
│   prod.vehiculos            [V]  — Step 4 V3 INSERT (per placa, 1-2)        │
│   prod.subscripciones_cliente [V] — Step 9 V9 INSERT (single)                │
│   prod.subscripcion_vehiculos [V] — Step 9 V9 bulk INSERT (per placa)       │
│   prod.facturas              [L-E] — Step 8a V8 INSERT (optional)            │
│   prod.factura_detalle       [A]  — Step 8a V8 bulk INSERT (optional)        │
│   prod.factura_impuestos     [A]  — Step 8a V8 INSERT (optional)            │
│   prod.factura_pagos         [A]  — Step 8a V8 INSERT (optional)            │
│   prod.factura_electronica   [L-E] — Step 8b V8b INSERT (optional)           │
│   prod.envio_dian            [L-W] — Step 8b V8b INSERT (optional)           │
│   prod.log_transaccional     [A]  — auto-co-INSERT via close_and_insert     │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲
        │
        ▼ MIGRATION 0030 (NO-OP audit trail — applied BEFORE F1.12 tests)
┌──────────────────────────────────────────────────────────────────────────────┐
│ migrations/versions/0030_venta_suscripcion_optional.py                        │
│                                                                              │
│ Op 0 — Pre-flight DO $$:                                                    │
│   ASSERT all 5 [V] tables exist (information_schema.tables check)          │
│   RAISE NOTICE '0030_preflight: 5/5 tablas OK'                              │
│                                                                              │
│ upgrade() — NO-OP:                                                           │
│   Schema unchanged (all 5 [V] tables pre-exist in migration 0001)            │
│   Sync catalog unchanged (all 5 [V] entries pre-existing)                    │
│   Permisos unchanged (gestionar_clientes already seeded)                     │
│                                                                              │
│ downgrade() — NO-OP:                                                         │
│   This migration added no DDL, no rows, no grants.                           │
│                                                                              │
│ down_revision = '0029_reimpresion_siembra_and_permiso_anular'                │
└──────────────────────────────────────────────────────────────────────────────┘
```

The handler is thin + orquestador. All validation logic lives in `repo/venta_suscripcion.py`. The single `commit()` at Step 10 materializes all rows atomically (KD-VENTA-01).

### Sub-chain reference shapes

**F1.9 cobro sub-chain (Step 8a, when `cobrar_ahora=true`)** — mirrors `api/v1/facturacion.py::create_factura` lines 216-380 verbatim. The `_factura_sub_chain` helper in `clientes_venta.py` is a private function (NOT a public endpoint) that:
1. Sources IVA rate via `obtener_iva_vigente(session)` (raises 500 `iva_no_configurado` if NULL).
2. Builds the SINGLE `factura_detalle` row with `concepto='subscripcion_mensual_prorrateada'` + `valor_unitario=monto_proporcional` + `cantidad=1` + `subtotal=monto_proporcional` (A-09 persistence per DEC-VENTA-03) when `fecha_inicio_cobertura.day > 15`; otherwise `concepto='subscripcion_mensual'` + `valor_unitario=plan.valor`.
3. Calls `crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago` (all commit-free, all in caller's session).
4. Returns `uuid_factura`.

**F1.10 FE sub-chain (Step 8b, when `emitir_factura_electronica=true` and `uuid_factura is not None`)** — mirrors F1.10 `repo/factura_electronica.py` helpers. The `_fe_sub_chain` helper in `clientes_venta.py` is a private function that:
1. Calls `assign_consecutivo(session, source_event_uuid=uuid_factura, ...)` to obtain the next consecutivo from the resolution row (takes `SELECT FOR UPDATE` on `prod.resolucion_facturacion` vigente row).
2. Calls `crear_factura_electronica_inicial(session, uuid_factura=uuid_factura, ...)` to INSERT `prod.factura_electronica` + create the envio_dian chain root.
3. Calls `crear_envio_dian_inicial(session, uuid_factura_electronica=uuid_fe, ...)` to INSERT `prod.envio_dian` initial row with `estado='pendiente'`, `uuid_envio_padre=NULL`.
4. Returns `(uuid_fe, uuid_envio)`.

Both sub-chains share the caller's session and commit boundary (KD-VENTA-01). They do NOT call `session.commit()` themselves — they `session.add()` + `await session.flush()` only.

---

## 5. Component Diagram

```
backend/packages/parkos_core/src/parkos_core/
├── api/v1/
│   ├── clientes.py            (MODIFY, +5 LOC)  ── router.include_router(...)
│   ├── clientes_venta.py      (NEW, +120 LOC)    ── dedicated router + 1 handler
│   ├── facturacion.py         (READ-ONLY ref)    ── canonical 12-step pattern
│   ├── workflows_reimpresion.py (READ-ONLY ref) ── dedicated-router pattern
│   └── _helpers.py            (REUSE)            ── no_store_headers + apply_no_store_header
├── repo/
│   ├── venta_suscripcion.py   (NEW, +140 LOC)    ── 9 helpers + 7 typed exceptions
│   ├── versioned.py           (REUSE)            ── close_and_insert + current_version
│   ├── placa.py               (REUSE)            ── FORMATO_AUTO/MOTO + detectar_tipo_vehiculo
│   ├── subscripcion_activa.py (REUSE)            ── resolve_active_subscription_for_exit
│   ├── factura.py             (REUSE)            ── F1.9 atomic 4-table chain
│   ├── factura_electronica.py (REUSE)            ── F1.10 atomic 2-table chain
│   ├── resolucion_facturacion.py (REUSE)        ── assign_consecutivo
│   ├── impuestos.py           (REUSE)            ── obtener_iva_vigente
│   └── idempotency.py         (REUSE)            ── DEC-IDEM-01 middleware
├── schemas/
│   ├── clientes.py            (EXTEND, +70 LOC)  ── VentaSuscripcionCreate + Response + 7 errors
│   ├── tipo_subscripciones.py (REUSE)            ── TipoSubscripcionesRead (for plan fields)
│   └── common.py              (REUSE)            ── _Base with extra='forbid'
├── models/V/
│   ├── clientes.py            (REUSE)            ── ORM model
│   ├── vehiculos.py           (REUSE)            ── ORM model
│   ├── tipo_subscripciones.py (REUSE)            ── ORM model
│   ├── subscripciones_cliente.py (REUSE)        ── ORM model
│   └── subscripcion_vehiculos.py (REUSE)        ── ORM model
├── auth/
│   └── tenancy.py             (REUSE)            ── TenantContext + get_tenant_ctx
├── migrations/versions/
│   └── 0030_venta_suscripcion_optional.py (NEW, ~30 LOC)   ── NO-OP audit trail
└── sync/catalog/entries/
    └── sync_entries_v.py      (NO CHANGE)        ── all 5 [V] entries pre-existing
```

**Module-level responsibilities:**

| Module | Type | Responsibility |
|---|---|---|
| `api/v1/clientes_venta.py` | NEW | Dedicated `APIRouter` (DEC-VENTA-05) + 1 handler `venta_suscripcion` with 10-step chain. Calls helpers in `repo/venta_suscripcion.py` + the existing `repo/factura.py` + `repo/factura_electronica.py` + `repo/resolucion_facturacion.py` for optional V8/V8b sub-chains. Single `await session.commit()` at Step 10. |
| `repo/venta_suscripcion.py` | NEW | 9 typed helpers (V1..V9) + 7 typed exceptions. ALL helpers stay commit-free — they `session.add()` + `await session.flush()` only (KD-VENTA-01 contract). Reuses `repo.versioned.close_and_insert`, `repo.placa.detectar_tipo_vehiculo`, `repo.subscripcion_activa.resolve_active_subscription_for_exit`. NO new ORM model changes. |
| `schemas/clientes.py` | EXTEND | +70 LOC: `VentaSuscripcionCreate(_Base)` request schema with discriminated `cliente | uuid_cliente`; `VentaSuscripcionResponse(_Base)` response schema with nested UUIDs + optional cobro result; 7 typed error schemas (one per typed exception). All inherit `extra='forbid'` (inherited from `_Base`). |
| `api/v1/clientes.py` | MODIFY | +5 LOC: add `from .clientes_venta import router as venta_suscripcion_router` + `router.include_router(venta_suscripcion_router)` mount at the bottom. The factory mount + `gestionar_clientes` permission gate are inherited. |
| `migrations/versions/0030_venta_suscripcion_optional.py` | NEW | ~30 LOC NO-OP audit trail. Pre-flight `DO $$` block confirms all 5 [V] tables exist. `upgrade()` and `downgrade()` are empty. `down_revision='0029_reimpresion_siembra_and_permiso_anular'`. |

**Data flow for one POST `/clientes/venta-suscripcion`:**

```
FastAPI route resolution
  └─▶ clientes.py router
        └─▶ router.include_router(venta_suscripcion_router)
              └─▶ clientes_venta.py::venta_suscripcion (10-step chain)
                    ├─▶ KD-3 issuer dep (DI-resolved)
                    ├─▶ repo_venta.buscar_tipo_subscripcion_vigente_por_uuid  (V2 SELECT FOR UPDATE)
                    ├─▶ (Optional) Tenant scope check (in-process)
                    ├─▶ repo_venta.buscar_cliente_por_uuid_o_crear  (V1)
                    ├─▶ (Optional) SELECT FOR UPDATE on prod.clientes (Step 3a)
                    ├─▶ repo_venta.buscar_o_crear_vehiculo_por_placa  (V3, per placa)
                    ├─▶ repo_venta.validar_placas_mismo_tipo_vehiculo  (V5)
                    ├─▶ repo_venta.validar_cantidad_maxima_vehiculos  (V6)
                    ├─▶ repo_venta.validar_placa_duplicada_subscripcion  (V4, per placa)
                    ├─▶ repo_venta.calcular_prorrateo  (V7 A-09)
                    ├─▶ repo_venta.crear_subscripcion_cliente  (V9 INSERT)
                    ├─▶ repo_venta.crear_subscripcion_vehiculos_bulk  (V9 bulk INSERT + advisory lock)
                    ├─▶ (Optional) _factura_sub_chain  (F1.9 helpers, when cobrar_ahora=true)
                    ├─▶ (Optional) _fe_sub_chain  (F1.10 helpers, when emitir_factura_electronica=true)
                    ├─▶ await session.commit()  (KD-VENTA-01 single commit)
                    ├─▶ apply_no_store_header(response)
                    └─▶ return VentaSuscripcionResponse(...)
```

---

## 6. Data Model

**No Alembic migration introduces schema changes.** MIGRATION 0030 is a NO-OP audit trail — present only for head-pointer continuity. The 5 [V] tables F1.12 touches already exist with all required columns (`cantidad_maxima_vehiculos`, `mismo_tipo_vehiculo`, `duracion_dias`); all 5 [V] sync catalog entries are already registered; `gestionar_clientes` permission is already seeded.

### 6.1 `prod.tipo_subscripciones` [V] (READ + LOCK)

| Property | Value |
|---|---|
| **ER línea** | 105 |
| **Migration 0001 línea** | 195-210 |
| **Operations** | V2 SELECT vigente row + `SELECT FOR UPDATE` row lock (KD-VENTA-02 + DEC-VENTA-04). No INSERT, no UPDATE. |
| **Columns read** | `uuid`, `tipo`, `valor` (Numeric 18,4), `duracion_dias` (Integer), `cantidad_maxima_vehiculos` (Integer), `mismo_tipo_vehiculo` (Boolean), `tipo_cliente_permitido` |
| **Columns write** | None |
| **Indexes** | UK `tipo_subscripciones_uk01 (tipo, vigente_desde)` |
| **Defense in depth** | bi-temporal VersionedBase guarantees at most one vigente row per `tipo`. Handler returns 404 `tipo_subscripcion_no_encontrado` if lookup returns NULL; 422 `plan_duracion_dias_invalido` if `duracion_dias=0` (ZeroDivisionError catch in `calcular_prorrateo`); KD-VENTA-02 `SELECT FOR UPDATE` exclusive lock prevents concurrent ventas on the same plan from racing on A-09 prorrateo calc. |
| **REVOKE** | Already enforced by F1.5 PR5-016 (REVOKE UPDATE, DELETE on `[V]` tables FROM rol_app per migration 0021 lines 162, 182). |

### 6.2 `prod.clientes` [V] (LOOKUP-OR-CREATE)

| Property | Value |
|---|---|
| **ER línea** | 449 |
| **Migration 0001 línea** | 435-452 |
| **Operations** | V1 SELECT by `uuid_cliente` (existing) + optional `SELECT FOR UPDATE` (Step 3a, when existing) OR INSERT via `repo.versioned.close_and_insert(current_uuid=None, new_attrs={...datos_cliente})`. |
| **Columns write (INSERT)** | `tipo_identificador`, `numero_identificacion`, `nombre`, `apellido`, `telefono`, `email`, `uuid_tipo_persona`, `registro`. Versioning + audit + sync columns server-set. **No `dv` column** — `dv` is validated by Pydantic then discarded (DEC-VENTA-07, REQ-OPS-058 reuse from F1.9). |
| **Indexes** | UK `clientes_uk01 (tipo_identificador, numero_identificacion, vigente_desde)` |
| **Defense in depth** | bi-temporal close+insert guarantees `vigente_desde` uniqueness. Pydantic `ClientesCreate._validar_nit_dv` blocks NIT mismatch at Layer 4 (422 `nit_dv_invalido`). DEC-VENTA-02 lock ordering: plan lock FIRST (Step 2), cliente lock AFTER (Step 3a) — prevents AB-BA deadlocks. |
| **FK relationships** | FK from `prod.subscripciones_cliente.uuid_cliente` (ER línea 1140) |

### 6.3 `prod.vehiculos` [V] (LOOKUP-OR-CREATE per placa)

| Property | Value |
|---|---|
| **ER línea** | 519 |
| **Migration 0001 línea** | 454-465 |
| **Operations** | V3 SELECT by `placa` (vigente row) OR INSERT via `close_and_insert(current_uuid=None, new_attrs={"placa": ..., "uuid_tipo_vehiculo": ...})`. |
| **Columns write (INSERT)** | `placa`, `uuid_tipo_vehiculo` (from `repo.placa.detectar_tipo_vehiculo`). Versioning + audit + sync columns server-set. |
| **Indexes** | UK `vehiculos_uk01 (placa, vigente_desde)` |
| **Defense in depth** | Pydantic `StringConstraints(min_length=1, max_length=16)` + `repo.placa.FORMATO_AUTO/FORMATO_MOTO` regex at V3 (422 `placa_formato_invalido`). `detectar_tipo_vehiculo` raises 422 `tipo_vehiculo_invalido` if catalog missing. |
| **FK relationships** | FK from `prod.subscripcion_vehiculos.uuid_vehiculo` (ER línea 1145) |

### 6.4 `prod.subscripciones_cliente` [V] (INSERT only)

| Property | Value |
|---|---|
| **ER línea** | 496 |
| **Migration 0001 línea** | 483-496 |
| **Operations** | INSERT via direct `model_cls(**attrs, created_at=..., created_by=...)` (no close needed — first version). No FK constraint at DB level; UUID application-enforced. |
| **Columns write (INSERT)** | `uuid_cliente`, `uuid_sucursal`, `uuid_tipo_subscripcion`, `fecha_inicio_cobertura` (from request), `fecha_vencimiento` (computed: `fecha_inicio_cobertura + plan.duracion_dias` days). Versioning + audit + sync columns server-set. |
| **Defense in depth** | bi-temporal `vigente_desde` discriminator. **No UPDATE path** (F1.12 only INSERTs; renewals = future HU). NO `valor_dia`/`monto_prorrateado` column — A-09 prorrateo persistence lives in `factura_detalle.valor_unitario`/`subtotal` (DEC-VENTA-03), NOT here (plan.md A-09 explicit). |
| **FK relationships** | FK to `prod.clientes.uuid` (ER línea 1140), `prod.sucursal.uuid` (ER línea 1139), `prod.tipo_subscripciones.uuid` (ER línea 1138) |

### 6.5 `prod.subscripcion_vehiculos` [V] (INSERT bulk)

| Property | Value |
|---|---|
| **ER línea** | 538 |
| **Migration 0001 línea** | 498-509 |
| **Operations** | V9 bulk INSERT after `pg_advisory_xact_lock(uuid_subscripcion_cliente)`. ONE advisory lock + N INSERTs (one per placa). |
| **Columns write (INSERT)** | `uuid_subscripcion_cliente`, `uuid_vehiculo`. Versioning + audit + sync columns server-set. |
| **Indexes** | UK `subscripcion_vehiculos_uk01 (uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde)` |
| **Defense in depth** | `pg_advisory_xact_lock` inside `crear_subscripcion_vehiculos_bulk` helper (REQ-OP-08 invariant — F1.12 first implements the lock that the contract documents). |

### 6.6 `prod.facturas` [L-E] (INSERT only — optional, when `cobrar_ahora=true`)

| Property | Value |
|---|---|
| **Operations** | F1.9 `crear_factura_evento` reused. `uuid_cliente` derived from `venta_cliente.uuid` (DEC-FACT-06 analog from F1.9). |
| **Defense in depth** | All F1.9 helpers commit-free; INSERT only. The KD-VENTA-01 commit at Step 10 covers this row. |

### 6.7 `prod.factura_detalle` [A] (INSERT bulk — optional)

| Property | Value |
|---|---|
| **Operations** | F1.9 `crear_factura_detalle_bulk` reused. When A-09 prorrateo applies, the SINGLE detail row carries `concepto='subscripcion_mensual_prorrateada'`, `valor_unitario=monto_proporcional`, `cantidad=1`, `subtotal=monto_proporcional` (DEC-VENTA-03). Otherwise, `concepto='subscripcion_mensual'`, `valor_unitario=plan.valor`. |

### 6.8 `prod.factura_impuestos` [A] (INSERT — optional)

| Property | Value |
|---|---|
| **Operations** | F1.9 `crear_factura_impuesto_iva` reused. IVA snapshot from `obtener_iva_vigente`. |

### 6.9 `prod.factura_pagos` [A] (INSERT — optional)

| Property | Value |
|---|---|
| **Operations** | F1.9 `crear_factura_pago` reused. `medio_pago=payload.medio_pago`, `valor=monto_proporcional OR plan.valor`. |

### 6.10 `prod.factura_electronica` [L-E] (INSERT — optional, when `emitir_factura_electronica=true`)

| Property | Value |
|---|---|
| **Operations** | F1.10 `crear_factura_electronica_inicial` reused. `assign_consecutivo` row-locks the resolution row (DEC-FE-04 from F1.10). |

### 6.11 `prod.envio_dian` [L-W] (INSERT initial — optional)

| Property | Value |
|---|---|
| **Operations** | F1.10 `crear_envio_dian_inicial` reused. `uuid_envio_padre=NULL`, `estado='pendiente'`. |

### 6.12 `prod.log_transaccional` [A] (INSERT — multiple, AUTO)

| Property | Value |
|---|---|
| **Operations** | AUTO-INSERTED via `repo/versioned.py::close_and_insert` (one per [V] INSERT — co-transactional). F1.12 NOT responsible for these rows — they are co-transactional by design (PR2 + PR6 hash chain extension). |

### 6.13 Tables touched summary

| Table | Type | Operation | Lines ER / migration |
|---|---|---|---|
| `tipo_subscripciones` | `[V]` | V2 SELECT FOR UPDATE (KD-VENTA-02) | ER 105 / migration 0001 lines 195-210 |
| `clientes` | `[V]` | V1 SELECT (existing) + optional SELECT FOR UPDATE (Step 3a) + INSERT (new) | ER 449 / migration 0001 lines 435-452 |
| `vehiculos` | `[V]` | V3 SELECT (per placa, existing) + INSERT (per placa, new) | ER 519 / migration 0001 lines 454-465 |
| `subscripciones_cliente` | `[V]` | V9 INSERT (single) | ER 496 / migration 0001 lines 483-496 |
| `subscripcion_vehiculos` | `[V]` | V9 bulk INSERT (per placa, with advisory lock) | ER 538 / migration 0001 lines 498-509 |
| `facturas` | `[L-E]` | (Optional, V8) INSERT | (F1.9, migration 0027) |
| `factura_detalle` | `[A]` | (Optional, V8) bulk INSERT | (F1.9, migration 0027) |
| `factura_impuestos` | `[A]` | (Optional, V8) INSERT | (F1.9, migration 0027) |
| `factura_pagos` | `[A]` | (Optional, V8) INSERT | (F1.9, migration 0027) |
| `factura_electronica` | `[L-E]` | (Optional, V8b) INSERT | (F1.10, migration 0028) |
| `envio_dian` | `[L-W]` | (Optional, V8b) INSERT initial | (F1.10, migration 0028) |
| `log_transaccional` | `[A]` | AUTO co-INSERT (per [V] INSERT) | (F1.5 PR5-016, migration 0021) |

**No column added** for `valor_dia`, `monto_prorrateado`, or any new field. **No FK added**. **No new index added**. **No new trigger added**. **No sync catalog change** — all 5 [V] entries pre-existing at `sync_entries_v.py` lines 133, 451, 483, 511, 525 (DEC-VENTA-08 WITHDRAWN).

**State transitions** happen via NEW rows with `vigente_desde=now()` discriminator on the [V] tables; chain integrity is via the bi-temporal `vigente_hasta` discriminator (NEVER UPDATE on user-meaningful fields per F1.5 PR5-016). The state machine for subscriptions is implicit via `fecha_vencimiento` (computed at sale time: `fecha_inicio_cobertura + plan.duracion_dias`); renewal = future HU; cancellation = future HU (out of F1.12 scope).

**Sync catalog impact**: ZERO. `sync_entries_v.py` already carries all 5 [V] entries. No sync changes needed by F1.12.

---

## 7. Concurrency & Locking

### 7.1 Lock inventory

The handler acquires locks in strict order (KD-VENTA-02):

| Order | Lock type | Target | When acquired | When released |
|---|---|---|---|---|
| 1 | `SELECT ... FOR UPDATE` (exclusive) | `prod.tipo_subscripciones.uuid=:p` (vigente row) | Step 2 | Step 10 (commit) |
| 2a | `SELECT ... FOR UPDATE` (exclusive, conditional) | `prod.clientes.uuid=:c` (only when `payload.uuid_cliente is not None`) | Step 3a | Step 10 (commit) |
| 3 | `pg_advisory_xact_lock(uuid_subscripcion_cliente)` (transaction-scoped advisory) | Hash of `uuid_subscripcion_cliente` | Inside `crear_subscripcion_vehiculos_bulk` (Step 9) | Step 10 (commit) |

No other locks are acquired. The [A]/[L-E]/[L-W] writes (cobro + FE sub-chains) acquire their own locks internally (`assign_consecutivo` takes `SELECT FOR UPDATE` on `prod.resolucion_facturacion`; `crear_factura_evento` takes `SELECT FOR UPDATE` on `prod.tarifas_sucursal` per KD-FACT-02) but those locks are independent and serialize only the relevant sub-domain.

### 7.2 DEC-VENTA-02 lock ordering rule (KD-VENTA-02)

The handler MUST acquire the plan lock FIRST (Step 2) before any other lock. The handler MUST acquire the cliente lock (Step 3a, only when existing) AFTER. The handler MUST NOT reverse the ordering.

**Why**: prevents AB-BA deadlocks under concurrent ventas on the same `prod.clientes` UUID. Consider:

- TX-A: `uuid_tipo_subscripcion=:p1` (plan A) + `uuid_cliente=:c` (existing cliente).
- TX-B: `uuid_tipo_subscripcion=:p2` (plan B) + `uuid_cliente=:c` (same cliente).

If the cliente lock were acquired FIRST:
- TX-A acquires `:c`, waits for `:p1`.
- TX-B acquires `:c` (impossible — TX-A holds it), TX-B waits for `:c` first → AB-BA deadlock.
- PostgreSQL detects the cycle and kills one TX with `deadlock_detected`.

With the plan lock FIRST:
- TX-A acquires `:p1` (independent of `:p2`).
- TX-B acquires `:p2` (independent of `:p1`).
- TX-A acquires `:c` (no other TX holds it yet).
- TX-B waits at `:c` until TX-A commits.
- TX-A commits, releases `:c` + `:p1`.
- TX-B acquires `:c`, proceeds to Step 4+.
- No deadlock, no abort.

### 7.3 KD-VENTA-02 plan lock type — `SELECT FOR UPDATE` (NOT `FOR SHARE`)

The handler takes `SELECT ... FOR UPDATE` (exclusive) on `prod.tipo_subscripciones`. F1.9 took `SELECT ... FOR SHARE` (shared) on `prod.tarifas_sucursal` (KD-FACT-02). The divergence is intentional (DEC-VENTA-04).

**Why exclusive**: A plan read mutates the sale semantics — `fecha_inicio_cobertura` is captured and A-09 prorrateo calc depends on it. Two concurrent ventas on the SAME plan with DIFFERENT `fecha_inicio_cobertura` would produce DIFFERENT prorrateo amounts. `FOR SHARE` allows multiple readers to proceed in parallel, but each reader would compute prorrateo on its OWN `fecha_inicio_cobertura` snapshot — there's no read consistency issue at the row level (the plan row doesn't change), but the SALE LOGIC depends on the order in which the two ventas reach Step 8 (V7 prorrateo compute). The exclusive lock serializes the calc, ensuring each venta sees a deterministic snapshot of (plan, fecha_inicio_cobertura).

**Why `FOR SHARE` was correct for F1.9**: A tarifa read does NOT mutate the calc — the `valor_unitario` + `cantidad` are server-derived from the items, and the server-side recompute (Step 8 in `create_factura`) is idempotent on the tarifa values. Concurrent facturas on the same tarifa can proceed in parallel because each factura sees a coherent snapshot of (tarifa, items).

### 7.4 Deadlock analysis

Under DEC-VENTA-02 + KD-VENTA-02:

- **Same plan + same cliente (different ventas)**: serialized at Step 2. No deadlock.
- **Different plans + same cliente**: independent plan locks. Cliente lock at Step 3a serializes. No deadlock.
- **Same plan + different clientes**: serialized at Step 2 (the plan lock). Different cliente inserts proceed independently. No deadlock.
- **Different plans + different clientes**: fully parallel. No contention.
- **Same plan + new cliente (no existing cliente)**: serialized at Step 2. Cliente INSERT at Step 3 is a new row — no row-level lock. Different ventas on the same plan serialize at Step 2.

The only deadlock risk is reversing the order (cliente FIRST). DEC-VENTA-02 veda this.

### 7.5 pg_advisory_xact_lock (REQ-OP-08)

The handler calls `pg_advisory_xact_lock(uuid_subscripcion_cliente)` inside `crear_subscripcion_vehiculos_bulk` BEFORE the bulk INSERT. The advisory lock is transaction-scoped (`xact_lock` variant) — released automatically at commit/rollback.

**Why**: REQ-OP-08 documents the contract for serializing junction-table writes for the same subscription. F1.12 implements the lock that the contract specifies. Concurrent calls on the same `uuid_subscripcion_cliente` serialize at the advisory lock; concurrent calls on DIFFERENT `uuid_subscripcion_cliente` proceed in parallel (advisory locks are 64-bit integers, no row-level contention).

---

## 8. Transaction Boundaries

### 8.1 DEC-VENTA-01 — Single `await session.commit()` for ALL writes

The handler body issues EXACTLY ONE `await session.commit()` call at Step 10. All helper functions (`buscar_*`, `validar_*`, `crear_*`) are commit-free — they `session.add()` + `await session.flush()` only (or read-only).

### 8.2 KD-VENTA-01 — Single-commit invariant (AST walk enforced)

The AST walk `tests/static/test_venta_handler_single_commit.py` scans `api/v1/clientes_venta.py::venta_suscripcion` body and asserts:

- `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'commit']) == 1`
- `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'begin_nested']) == 0`
- NO occurrence of the literal string `"SAVEPOINT"` in the handler body.

Any of these three conditions failing breaks KD-VENTA-01 and the test fails.

### 8.3 KD-VENTA-01 invariant rationale

Cross-domain atomicity is the entire business requirement (plan.md line 1014). The 9-table single commit is well within PostgreSQL's capabilities — the [V] tables have minimal locking (UK checks), the [A]/[L-E]/[L-W] writes are INSERT-only, no long-held locks. SAVEPOINTs would partially commit, leaving orphan clientes + vehiculos + subscripciones rows if the FE write failed (R1 MEDIUM).

### 8.4 Helper commit-free contract

All 9 helpers in `repo/venta_suscripcion.py` are commit-free:

| Helper | Operation | Commits? |
|---|---|---|
| `buscar_cliente_por_uuid_o_crear` (V1) | SELECT + INSERT (close_and_insert) | NO |
| `buscar_tipo_subscripcion_vigente_por_uuid` (V2) | SELECT FOR UPDATE | NO |
| `buscar_o_crear_vehiculo_por_placa` (V3) | SELECT + INSERT (close_and_insert) | NO |
| `validar_placas_mismo_tipo_vehiculo` (V5) | read-only validation | NO |
| `validar_cantidad_maxima_vehiculos` (V6) | in-process validation | NO |
| `validar_placa_duplicada_subscripcion` (V4) | SELECT | NO |
| `calcular_prorrateo` (V7) | in-process Decimal math | NO |
| `crear_subscripcion_cliente` (V9) | INSERT | NO |
| `crear_subscripcion_vehiculos_bulk` (V9) | pg_advisory_xact_lock + bulk INSERT | NO |

Plus all reused F1.9/F1.10 helpers (already commit-free per their contracts):

| Helper | Operation | Commits? |
|---|---|---|
| `repo.factura.crear_factura_evento` (F1.9) | INSERT | NO |
| `repo.factura.crear_factura_detalle_bulk` (F1.9) | bulk INSERT | NO |
| `repo.factura.crear_factura_impuesto_iva` (F1.9) | INSERT | NO |
| `repo.factura.crear_factura_pago` (F1.9) | INSERT | NO |
| `repo.factura_electronica.crear_factura_electronica_inicial` (F1.10) | INSERT | NO |
| `repo.factura_electronica.crear_envio_dian_inicial` (F1.10) | INSERT | NO |
| `repo.resolucion_facturacion.assign_consecutivo` (F1.10) | SELECT FOR UPDATE + read | NO |

All commits are owned by the handler at Step 10.

---

## 9. Validation Chain (V1..V9)

The 10-step handler chain runs 9 server-side validations. Each validation either succeeds (proceed to next step) or raises `HTTPException` with a typed error discriminator (mapped from `repo.venta_suscripcion.py` typed exceptions). The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

### 9.1 V1 — Cliente lookup-or-create

**Step**: 3 (handler) · **Helper**: `buscar_cliente_por_uuid_o_crear(session, *, uuid_cliente, datos_cliente, actor_uuid)`

**Logic**:
- If `payload.uuid_cliente is not None` (existing): call `repo.versioned.current_version(uuid=payload.uuid_cliente)` → return ORM row.
- Else (new): call `repo.versioned.close_and_insert(current_uuid=None, new_attrs={tipo_identificador, numero_identificacion, nombre, apellido, telefono, email, uuid_tipo_persona, registro})` → return ORM row. The `dv` field is NOT included (DEC-VENTA-07, REQ-OPS-058).

**Errors**:
- 404 `cliente_no_encontrado` (uuid_cliente provided but missing)
- 422 `nit_dv_invalido` (NIT módulo 11 fails — raised by `ClientesCreate._validar_nit_dv` Pydantic validator at Layer 4, before reaching this helper)

### 9.2 V2 — Plan lock + lookup

**Step**: 2 (handler) · **Helper**: `buscar_tipo_subscripcion_vigente_por_uuid(session, *, uuid_tipo_subscripcion)`

**Logic**:
```sql
SELECT * FROM prod.tipo_subscripciones
WHERE uuid = :p AND vigente_hasta IS NULL
ORDER BY vigente_desde DESC LIMIT 1
FOR UPDATE
```

**Errors**:
- 404 `tipo_subscripcion_no_encontrado` (lookup returns NULL)
- 422 `plan_duracion_dias_invalido` (`duracion_dias=0` — caught in `calcular_prorrateo` at V7 via `ZeroDivisionError`)

### 9.3 V3 — Per-placa lookup-or-create

**Step**: 4 (handler, in `for placa in payload.placas` loop) · **Helper**: `buscar_o_crear_vehiculo_por_placa(session, *, placa, actor_uuid)`

**Logic**:
1. Validate `placa` against `FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")` + `FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")` — if neither matches, raise 422.
2. Call `repo.placa.detectar_tipo_vehiculo(session, placa)` → returns UUID of `prod.tipos_vehiculo` row.
3. Call `repo.versioned.current_version(vehiculo_class, uuid_or_lookup={placa: placa})` → if found, return.
4. Else call `repo.versioned.close_and_insert(current_uuid=None, new_attrs={placa, uuid_tipo_vehiculo})` → return.

**Errors**:
- 422 `placa_formato_invalido` (regex miss)
- 422 `tipo_vehiculo_invalido` (catalog missing)

### 9.4 V4 — Per-placa duplicate detection

**Step**: 7 (handler, in `for placa in payload.placas` loop) · **Helper**: `validar_placa_duplicada_subscripcion(session, *, placa, uuid_sucursal, fecha_inicio_cobertura)`

**Logic**: reverse-direction call to `repo.subscripcion_activa.resolve_active_subscription_for_exit(session, placa, uuid_sucursal, fecha_inicio_cobertura)`. If returns `found=True`, raise 422 `suscripcion_duplicada_placa`. (Existing F1.7 helper; F1.12 uses its truthy return semantics.)

**Errors**:
- 422 `suscripcion_duplicada_placa`

### 9.5 V5 — `mismo_tipo_vehiculo` constraint

**Step**: 5 (handler) · **Helper**: `validar_placas_mismo_tipo_vehiculo(session, *, plan, vehiculos)`

**Logic**: when `plan.mismo_tipo_vehiculo=true`, all `vehiculos[i].uuid_tipo_vehiculo` MUST be equal. If any mismatch, raise 422 with `tipos_encontrados=[...]`.

**Errors**:
- 422 `tipo_vehiculo_incompatible`

### 9.6 V6 — `cantidad_maxima_vehiculos` constraint

**Step**: 6 (handler) · **Helper**: `validar_cantidad_maxima_vehiculos(session, *, plan, n_placas)`

**Logic**: `if n_placas > plan.cantidad_maxima_vehiculos: raise 422`.

**Errors**:
- 422 `cantidad_maxima_excedida`

### 9.7 V7 — A-09 prorrateo compute

**Step**: 8 (handler) · **Helper**: `calcular_prorrateo(*, plan, fecha_inicio_cobertura) -> Decimal`

**Logic**:
```python
if plan.duracion_dias <= 0:
    raise PlanDuracionDiasInvalidoError()
valor_dia = plan.valor / plan.duracion_dias
if fecha_inicio_cobertura.day > 15:
    dias_restantes_mes = (
        calendar.monthrange(fecha_inicio_cobertura.year, fecha_inicio_cobertura.month)[1]
        - fecha_inicio_cobertura.day
    )
    monto_proporcional = valor_dia * dias_restantes_mes
else:
    monto_proporcional = plan.valor  # full value
return monto_proporcional
```

**Errors**:
- 422 `plan_duracion_dias_invalido` (`duracion_dias=0`, ZeroDivisionError catch)

### 9.8 V8 — Optional F1.9 cobro sub-chain

**Step**: 8a (handler, when `cobrar_ahora=true`) · **Sub-chain**: `_factura_sub_chain(session, cliente, subscripcion, plan, monto_proporcional, medio_pago, referencia, ctx)`

**Logic**: mirrors `api/v1/facturacion.py::create_factura` Steps 5-10 verbatim. Calls:
1. `obtener_iva_vigente(session)` — raise 500 `iva_no_configurado` if NULL.
2. `crear_factura_evento(session, actor_uuid=ctx.actor_uuid, new_attrs={uuid_sucursal, uuid_ingreso=None, uuid_salida=None, subtotal=monto_proporcional, descuento=0, total=monto_proporcional})`.
3. `crear_factura_detalle_bulk(session, uuid_factura, items=[FacturaItemCreate(concepto='subscripcion_mensual_prorrateada' | 'subscripcion_mensual', valor_unitario=monto_proporcional | plan.valor, cantidad=1, subtotal=...)])`.
4. `crear_factura_impuesto_iva(session, uuid_factura, base=monto_proporcional, iva=iva_porcentaje)`.
5. `crear_factura_pago(session, uuid_factura, medio_pago=medio_pago, valor=monto_proporcional, referencia=referencia, uuid_sesion=ctx.uuid_sesion)`.

Returns `uuid_factura`.

**Errors**:
- 500 `iva_no_configurado` (F1.9 V3 — only if `cobrar_ahora=true`)

### 9.9 V8b — Optional F1.10 FE sub-chain

**Step**: 8b (handler, when `emitir_factura_electronica=true` AND `uuid_factura is not None`) · **Sub-chain**: `_fe_sub_chain(session, uuid_factura, ctx)`

**Logic**: mirrors F1.10 `repo/factura_electronica.py` pattern:
1. `assign_consecutivo(session, source_event_uuid=uuid_factura, ...)` — `SELECT FOR UPDATE` on resolution row + idempotency lookup → returns next consecutivo.
2. `crear_factura_electronica_inicial(session, uuid_factura=uuid_factura, ...)` — INSERT.
3. `crear_envio_dian_inicial(session, uuid_factura_electronica=uuid_fe, ...)` — INSERT initial with `estado='pendiente'`.

Returns `(uuid_fe, uuid_envio)`.

**Errors**:
- 409 `consecutivo_range_exhausted` (F1.10 ConsecutivoRangeExhaustedError — passes through)

### 9.10 V9 — INSERT subscription + junction

**Step**: 9 (handler) · **Helpers**: `crear_subscripcion_cliente` + `crear_subscripcion_vehiculos_bulk`

**Logic**:
```python
fecha_vencimiento = payload.fecha_inicio_cobertura + timedelta(days=plan.duracion_dias)
subscripcion = await crear_subscripcion_cliente(
    session, actor_uuid=ctx.actor_uuid,
    uuid_cliente=cliente.uuid, uuid_sucursal=target_sucursal,
    uuid_tipo_subscripcion=plan.uuid,
    fecha_inicio_cobertura=payload.fecha_inicio_cobertura,
    fecha_vencimiento=fecha_vencimiento,
)
junction_rows = await crear_subscripcion_vehiculos_bulk(
    session, actor_uuid=ctx.actor_uuid,
    uuid_subscripcion_cliente=subscripcion.uuid,
    uuid_vehiculos=[v.uuid for v in vehiculos],
)
```

Inside `crear_subscripcion_vehiculos_bulk`:
```python
# REQ-OP-08: advisory lock BEFORE bulk INSERT
await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": uuid_to_int64(uuid_subscripcion_cliente)})
for v_uuid in uuid_vehiculos:
    session.add(SubscripcionVehiculos(
        uuid_subscripcion_cliente=uuid_subscripcion_cliente,
        uuid_vehiculo=v_uuid,
        vigente_desde=datetime.utcnow(),
        vigente_hasta=None,
        estado='activo',
        created_at=datetime.utcnow(),
        created_by=actor_uuid,
    ))
await session.flush()
```

### 9.11 Validation chain summary

| Step | Validation | Helper | Errors |
|---|---|---|---|
| 1 | KD-3 issuer | DI-resolved | 403 (no operador/admin prefix) |
| 2 | Plan lock + lookup (KD-VENTA-02 + DEC-VENTA-04) | `buscar_tipo_subscripcion_vigente_por_uuid` | 404 `tipo_subscripcion_no_encontrado` |
| 2a | Tenant scope post-V1 | in-process | 403 `tenant_scope_violation` |
| 3 | Cliente lookup-or-create (V1) | `buscar_cliente_por_uuid_o_crear` | 404 `cliente_no_encontrado`, 422 `nit_dv_invalido` (Pydantic) |
| 3a | Cliente lock (optional, DEC-VENTA-02) | SELECT FOR UPDATE | — |
| 4 | Per-placa lookup-or-create (V3) | `buscar_o_crear_vehiculo_por_placa` | 422 `placa_formato_invalido`, 422 `tipo_vehiculo_invalido` |
| 5 | `mismo_tipo_vehiculo` (V5) | `validar_placas_mismo_tipo_vehiculo` | 422 `tipo_vehiculo_incompatible` |
| 6 | `cantidad_maxima_vehiculos` (V6) | `validar_cantidad_maxima_vehiculos` | 422 `cantidad_maxima_excedida` |
| 7 | Per-placa duplicate (V4) | `validar_placa_duplicada_subscripcion` | 422 `suscripcion_duplicada_placa` |
| 8 | A-09 prorrateo (V7) | `calcular_prorrateo` | 422 `plan_duracion_dias_invalido` |
| 9 | INSERT subscription + junction (V9) | `crear_subscripcion_cliente` + `crear_subscripcion_vehiculos_bulk` | (none — INSERT only) |
| 8a | Optional cobro (V8) | `_factura_sub_chain` (F1.9 helpers) | 500 `iva_no_configurado` |
| 8b | Optional FE (V8b) | `_fe_sub_chain` (F1.10 helpers) | 409 `consecutivo_range_exhausted` |
| 10 | SINGLE COMMIT (KD-VENTA-01) | `await session.commit()` | — |
| 11 | Response shape + no_store | `apply_no_store_header(response)` | — |

---

## 10. State Machine

**F1.12 has NO explicit FSM.** Subscription state is implicit via bi-temporal `vigente_desde`/`vigente_hasta`:

| State | Derivation |
|---|---|
| **vigente** | `vigente_hasta IS NULL AND estado='activo' AND NOW() BETWEEN fecha_inicio_cobertura AND fecha_vencimiento` |
| **future** | `vigente_hasta IS NULL AND estado='activo' AND fecha_inicio_cobertura > NOW()` (subscription not yet started) |
| **expired** | `vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento < NOW()` (no expiration close — renewal = future HU) |
| **cancelled** | `vigente_hasta IS NOT NULL AND estado='inactivo'` (close-only, future HU) |

The bi-temporal `vigente_desde`/`vigente_hasta` columns are server-set on INSERT; `estado` is server-set to `'activo'`. The `fecha_vencimiento` column is computed at sale time (`fecha_inicio_cobertura + plan.duracion_dias`).

### 10.1 No UPDATE path

F1.12 only INSERTs into `prod.subscripciones_cliente` + `prod.subscripcion_vehiculos`. There is no UPDATE path for subscription state transitions. Renewals, cancellations, and plan changes are explicitly out of F1.12 scope (see §15 Out of Scope).

### 10.2 Implicit transitions

| Event | Effect |
|---|---|
| NOW() advances past `fecha_vencimiento` | Subscription is "expired" but the row remains vigente (no close). The query for active subscriptions filters by `fecha_vencimiento >= NOW()`. |
| Renewal (future HU) | INSERT new `prod.subscripciones_cliente` row with new `fecha_inicio_cobertura` + new `fecha_vencimiento`. Old row remains unchanged. |
| Cancellation (future HU) | UPDATE `vigente_hasta = NOW()` on the existing row + INSERT `estado='inactivo'` for bi-temporal close. |

### 10.3 Why no explicit FSM

Subscriptions are time-bounded (plan-based), not event-bounded (state-machine). The implicit bi-temporal state suffices for all F1.12 use cases. Explicit FSM machinery (state column + transition table) would be premature for F1.12.

---

## 11. Decisions

This HU adopts **seven** Key Decisions (DEC-VENTA-01..07 from `proposal.md §6`; DEC-VENTA-08 WITHDRAWN after pre-flight 2026-09-15) plus **two KD invariants** (KD-VENTA-01 single-commit + KD-VENTA-02 plan lock V2 + DEC-VENTA-04 exclusive). Each decision passes the R5 risk threshold (no open question blocks the design; the proposal §7 confirms "R1 RESOLVED" after the DEC-VENTA-01 resolution of R1 MEDIUM). The decisions are grouped into 5 themes: cross-domain atomicity (DEC-VENTA-01), lock ordering (DEC-VENTA-02, DEC-VENTA-04, KD-VENTA-02), persistence semantics (DEC-VENTA-03), module topology (DEC-VENTA-05), and policy (DEC-VENTA-06, DEC-VENTA-07).

### Decision DEC-VENTA-01 — Single `await session.commit()` for ALL writes (RESOLVES R1 MEDIUM)

**Choice.** One `await session.commit()` at Step 10 of the handler body, covering 5 [V] rows + 4 optional [A]/[L-E] rows + 2 optional [L-W]/[L-E] rows + N `log_transaccional` rows. No SAVEPOINTs. All helper functions (`crear_*`) stay commit-free — they `session.add()` + `await session.flush()` only.

**Context.** R1 MEDIUM (the fundamental design question of F1.12). F1.9 KD-FACT-01 + F1.10 KD-FE-01 + F1.11 KD-TKT-01 establish the single-commit invariant as the canonical pattern. Cross-domain atomicity is the entire business requirement (plan.md line 1014). PostgreSQL handles single TX with 9+ inserts easily (no long-held locks).

**Alternatives considered.**
- *SAVEPOINT per write group* — REJECTED. Partial commits would leave orphan clientes + vehiculos rows if FE write failed.
- *Separate endpoint per write group* — REJECTED. Defeats the purpose of F1.12.

**Rationale.** F1.10 KD-FE-01 precedent. Single-commit invariant becomes the AST walk contract (KD-VENTA-01). KD-VENTA-02 lock ordering prevents deadlocks.

### Decision DEC-VENTA-02 — Lock ordering: `tipo_subscripciones` first, then `clientes` (KD-VENTA-02)

**Choice.** `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (Step 2) BEFORE any other lock. If `uuid_cliente` is provided (existing), `SELECT FOR UPDATE` on `prod.clientes` (Step 3a) AFTER.

**Context.** Prevents AB-BA deadlocks under concurrent ventas. Plan A acquires plan lock first, plan B waits. Plan A then acquires cliente lock (or none, if new), plan B waits if same cliente. No cycle.

**Alternatives considered.**
- *Lock `clientes` first* — REJECTED. AB-BA deadlock risk: plan A holds cliente lock waiting for plan lock; plan B holds plan lock waiting for cliente lock.
- *No locks* — REJECTED. Concurrent ventas on the same plan could race on the prorrateo calc (different days → different amounts).

**Rationale.** F1.10 KD-FE-01 + F1.7 KD-S2 + F1.11 KD-TKT-02 precedent. Lock ordering is the canonical Postgres pattern for multi-table writes under concurrency.

### Decision DEC-VENTA-03 — A-09 prorrateo persistence in `factura_detalle` ONLY when `cobrar_ahora=true`

**Choice.** The A-09 prorrateo (`valor_dia = plan.valor / duracion_dias`; `monto_proporcional = valor_dia * dias_restantes_mes` when `fecha_inicio_cobertura.day > 15`) is computed at sale time. If `cobrar_ahora=true`, persist in `factura_detalle.valor_unitario`/`subtotal` of the SINGLE detail row with `concepto='subscripcion_mensual_prorrateada'`. If `cobrar_ahora=false`, the prorrateo amount is computed for the response body's `monto_prorrateado` field ONLY (not persisted anywhere — the subscription is recorded at full value, billing is decoupled).

**Context.** plan.md line 460 (A-09 explicit) + plan.md line 1016 (scope). When the operator does NOT charge at the counter (deferred billing / pay-later), the prorrateo is irrelevant to the DB. `subscripciones_cliente` has NO `valor_dia`/`monto_prorrateado` column.

**Alternatives considered.**
- *Add `valor_dia` column to `subscripciones_cliente`* — REJECTED. plan.md A-09 explicitly forbids this.
- *Persist prorrateo even when `cobrar_ahora=false`* — REJECTED. Out of scope (the cobro is the only reason to persist).
- *Apply A-09 prorrateo to the subscription's `valor_unitario` directly* — REJECTED. The subscription's "value" is the plan's `valor`; prorrateo is a billing artifact.

**Rationale.** A-09 explicit + billing decoupling principle. The prorrateo is a calculation result, not a subscription attribute.

### Decision DEC-VENTA-04 — Plan lock uses `SELECT FOR UPDATE` (NOT FOR SHARE) — diverges from F1.9 KD-FACT-02

**Choice.** KD-VENTA-02 takes `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (exclusive). F1.9 took `SELECT FOR SHARE` on `prod.tarifas_sucursal` (shared, multiple readers OK).

**Context.** A plan read mutates the sale semantics (the `fecha_inicio_cobertura` is captured and A-09 prorrateo calc depends on it). Concurrent ventas on the same plan with different `fecha_inicio_cobertura` would produce different prorrateo amounts; exclusive lock serializes the calc. KD-FACT-02's `FOR SHARE` is correct for F1.9 because tarifa read doesn't mutate the calc; F1.12's plan read DOES.

**Alternatives considered.**
- *FOR SHARE on `tipo_subscripciones`* — REJECTED. Two concurrent ventas could compute prorrateo on stale `fecha_inicio_cobertura`.
- *No lock + post-commit recompute* — REJECTED. The prorrateo is the sale amount, not a derived report.

**Rationale.** Sale semantics mutation justifies exclusive lock granularity. F1.9 KD-FACT-02 (`FOR SHARE`) is the canonical pattern for non-mutating reads; F1.12 diverges intentionally because the read DOES mutate the calc.

### Decision DEC-VENTA-05 — Dedicated `APIRouter` for `venta-suscripcion` (NOT via `make_router`)

**Choice.** NEW `api/v1/clientes_venta.py` with `router = APIRouter(prefix="/clientes", tags=["clientes"])` mounted into the existing `clientes.py` via `router.include_router(venta_suscripcion_router)`. The endpoint is a CUSTOM POST with the 10-step chain (NOT a `make_router`-mounted resource).

**Context.** The factory mount `make_router` emits generic POST + GET routes on the 5 individual [V] tables. The `venta-suscripcion` endpoint writes to ALL 5 in a single TX — it does not map cleanly to a single resource. F1.11 precedent: `workflows_reimpresion.py` is a dedicated router for the same reason.

**Alternatives considered.**
- *Add `venta-suscripcion` to the `make_router` mount* — REJECTED. The factory does not support cross-table atomic writes.
- *Separate top-level router `/venta-suscripcion`* — REJECTED. The resource logically belongs under `/clientes` (it's a sale ON a cliente).

**Rationale.** Module topology mirrors F1.11. The `gestionar_clientes` permission is inherited from the parent factory mount via `router.include_router` (DEC-VENTA-08 analog for permission propagation).

### Decision DEC-VENTA-06 — `Cache-Control: no-store` on EVERY response (XR2 mirror from F1.11)

**Choice.** All responses (201 + 4xx + 5xx) carry `Cache-Control: no-store`. Both success (`apply_no_store_header(response)`) and error (`no_store_headers()` in `HTTPException(headers=...)`) routes.

**Context.** XR2 mirror from F1.11 DEC-TKT-06. A proxy that serves a stale `venta-suscripcion` response would silently accept out-of-date state (e.g., the cliente's email or telefono would not be the current one).

**Alternatives considered.**
- *Conditional `no-store` only on success* — REJECTED. Cached error responses would mask the current state.
- *`Cache-Control: max-age=0, must-revalidate`* — REJECTED. Weaker guarantee than `no-store`.

**Rationale.** `no-store` is the strongest cache directive. The handler is a write endpoint — the response must never be served from cache.

### Decision DEC-VENTA-07 — `dv` field is validated but NOT persisted (F1.9 REQ-OPS-058 reuse)

**Choice.** `VentaSuscripcionCreate.cliente.dv` is validated via `ClientesCreate._validar_nit_dv` Pydantic validator (already in place, `schemas/clientes.py` lines 82-102). The `dv` value is NOT a column on `prod.clientes` — it is consumed by the validator and discarded before `close_and_insert(new_attrs={...})`.

**Context.** F1.9 established `dv` as a Pydantic-only validation field. No schema change to `prod.clientes` is needed.

**Alternatives considered.**
- *Add `dv` column to `prod.clientes`* — REJECTED. F1.9 rejected this; `dv` is a Módulo 11 check digit, not a stored attribute.
- *Skip NIT validation entirely* — REJECTED. REQ-OPS-058 mandates NIT validación at the schema layer.

**Rationale.** F1.9 REQ-OPS-058 reuse. The schema layer is the canonical validation point.

### Decision DEC-VENTA-08 — WITHDRAWN (sync catalog all 5 [V] entries pre-existing)

**Context.** Originally speculated that `subscripciones_cliente` + `subscripcion_vehiculos` were MISSING from `sync_entries_v.py`. **Pre-flight inspection (2026-09-15) confirms FALSE** — all 5 [V] entries exist (`sync_entries_v.py` lines 133, 451, 483, 511, 525). MIGRATION 0030 Op 1 sync catalog seed is NOT needed.

**Rationale.** See §6.13 + proposal §5.13. The earlier draft's DEC-VENTA-08 + MIGRATION 0030 Op 1 sync seed are WITHDRAWN.

### Decision KD-VENTA-01 — Single-commit invariant (AST walk enforced)

**Choice.** The `venta_suscripcion` handler body MUST contain EXACTLY ONE `await session.commit()` call. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements MUST NOT appear anywhere in the handler body or its callees.

**Context.** KD-VENTA-01 mirror of F1.10 KD-FE-01 + F1.9 KD-FACT-01 + F1.11 KD-TKT-01. A 9-table sale without its parent commit boundary is an atomicity orphan. Single-commit atomicity closes R1 MEDIUM.

**Alternatives considered.**
- *Separate commits for [V] and optional [A]/[L-E]/[L-W]* — REJECTED. Loses atomicity. If [V] commits but cobro fails, orphan clientes + vehiculos + subscripciones rows.
- *Use SAVEPOINT for nested commit* — REJECTED. Defeats the purpose of the single-commit invariant.

**Rationale.** KD-FE-01 + KD-TKT-01 mirror. Atomicity is non-negotiable for cross-domain sale semantics. AST walks `tests/static/test_venta_handler_single_commit.py` enforces the invariant.

### Decision KD-VENTA-02 — `SELECT FOR UPDATE` row lock on `prod.tipo_subscripciones` (DEC-VENTA-04)

**Choice.** The handler V2 guard uses `SELECT ... FOR UPDATE` on the vigente `prod.tipo_subscripciones` row for `payload.uuid_tipo_subscripcion`. The lock is held until `await session.commit()` at Step 10. Concurrent calls on the SAME plan serialize cleanly.

**Context.** KD-TKT-02 + DEC-VENTA-04 mirror of F1.10 KD-FE-02 (`assign_consecutivo` `SELECT FOR UPDATE` pattern). The `SELECT FOR UPDATE` exclusive lock closes the concurrent-create race at the row level. Two concurrent TXs attempting ventas on the same plan serialize: the FIRST acquires the lock and inserts; the SECOND blocks at SELECT FOR UPDATE until the FIRST commits.

**Alternatives considered.**
- *Lock per-table* — REJECTED. Serializes ALL ventas; latency catastrophe.
- *Lock per-uuid_tipo_subscripcion (current approach via SELECT FOR UPDATE)* — ACCEPTED. Matches F1.10 KD-FE-02 + F1.7 KD-S2 precedent.
- *Lock per-uuid_sucursal* — REJECTED. Cross-sucursal locking would serialize unrelated ventas.

**Rationale.** F1.10 KD-FE-02 precedent. Per-row `FOR UPDATE` lock is the canonical Postgres pattern for atomic counter increment under concurrency. DEC-VENTA-04 exclusive type (NOT FOR SHARE) is justified by the plan read mutating sale semantics via A-09 prorrateo.

---

## 12. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Cross-domain atomicity** — 9-table single commit is the largest TX in the codebase. A bug in any helper could leave inconsistent state. | **MEDIUM (RESOLVED)** | DEC-VENTA-01 (§11) + KD-VENTA-01 AST walk `tests/static/test_venta_handler_single_commit.py`. Verify all helpers do NOT call `session.commit()`. |
| **R2** | **A-09 prorrateo calc** — `valor_dia = plan.valor / plan.duracion_dias` requires `plan.duracion_dias > 0`. A null/zero `duracion_dias` would divide by zero. | **MEDIUM** | Server-side defense: `ZeroDivisionError` catch in `calcular_prorrateo` → 422 `plan_duracion_dias_invalido`. Plus Pydantic validation at `TipoSubscripcionesRead` lookup time. |
| **R3** | **`mismo_tipo_vehiculo` constraint** — derived `uuid_tipo_vehiculo` from placa regex must match across all placas when `plan.mismo_tipo_vehiculo=true`. | **MEDIUM** | V5 `validar_placas_mismo_tipo_vehiculo` helper raises 422 `tipo_vehiculo_incompatible` BEFORE any INSERT. |
| **R4** | **Placa duplicate detection** — must check for ANY active subscripcion on the placa at this branch via `resolve_active_subscription_for_exit` (reverse-direction). | **MEDIUM** | V4 helper raises 422 `suscripcion_duplicada_placa`. F1.7's branch-pinned WHERE clause carries over. |
| **R5** | **Idempotency-Key reuse (DEC-IDEM-01)** — same as F1.6/F1.9/F1.10/F1.11. A replay with same key + same body returns cached response; same key + different body returns 409. | **LOW** | DEC-IDEM-01 already in place. `IdempotencyKeyMiddleware` owns the cache. |
| **R6** | **Cache-Control no-store (DEC-VENTA-06)** — every response must carry the header, including the 422 Pydantic validation errors. | **LOW** | DEC-VENTA-06. The `_helpers.no_store_headers()` + `apply_no_store_header()` helpers are reused verbatim from F1.6/F1.9/F1.10/F1.11. |
| **R7** | **Sync catalog entries** — `subscripciones_cliente` + `subscripcion_vehiculos` ALREADY registered in `sync_entries_v.py` (pre-flight confirmed 2026-09-15). | **RESOLVED** | DEC-VENTA-08 WITHDRAWN. No action needed. All 5 [V] entries ship pre-existing. |
| **R8** | **Permiso `gestionar_clientes` is already seeded** — but role grants may be incomplete. An operador without the role would get 403 at `requires_issuer` (Layer 1) or `require_permission` (factory mount). | **LOW** | DEC-VENTA-05 mounts on the existing `clientes.py` factory which already enforces the permission. The new endpoint inherits the gate. |
| **R9** | **Concurrency on multiple ventas for the SAME plan** — KD-VENTA-02 `SELECT FOR UPDATE` serializes. Two ventas on DIFFERENT plans run in parallel. | **LOW** | Intentional. Independent ventas are independent. |
| **R10** | **`pg_advisory_xact_lock(uuid_subscripcion_cliente)` is NOT yet implemented in code** — REQ-OP-08 documents the contract but the actual call is missing from the codebase. F1.12 adds it. | **LOW** | REQ-OP-08 invariant: lock MUST be acquired before the bulk INSERT. New `crear_subscripcion_vehiculos_bulk` helper enforces. |
| **R11** | **MIGRATION 0030 head-pointer continuity** — if the migration is skipped in a future DB environment, the `down_revision` chain breaks and downstream migrations cannot apply. | **LOW** | Pre-flight `DO $$` block confirms all 5 [V] tables exist. MIGRATION 0030 is required for head-pointer continuity, even though `upgrade()` and `downgrade()` are no-ops. |
| **R12** | **DEC-VENTA-04 (FOR UPDATE not FOR SHARE) divergence from F1.9 KD-FACT-02** — future HUs may mistakenly apply `FOR SHARE` to `tipo_subscripciones` reads, breaking the prorrateo calc serialization. | **LOW** | DEC-VENTA-04 documented in design §11. `buscar_tipo_subscripcion_vigente_por_uuid` helper uses `with_for_update()` exclusively; AST walk + comment enforce. |

---

## 13. Performance & Scaling

### 13.1 Latency budget

The handler `POST /api/v1/clientes/venta-suscripcion` MUST respond within the F1.6/F1.9/F1.10/F1.11 SLO of **p99 ≤ 250 ms** (single TX, single commit). The handler body performs up to 16 reads + 9 INSERTs + 1 commit + 1 advisory lock:

| Step | Operation | Expected latency | Notes |
|---|---|---|---|
| 1 | KD-3 issuer + permission check (DI) | <5 ms | Pure DI + JWT decode (cache hit) |
| 2 | V2 SELECT `prod.tipo_subscripciones` FOR UPDATE | ~5-10 ms | `vigente_hasta IS NULL` partial UK + FK index |
| 2a | Tenant scope check (in-process) | <1 ms | No DB hit |
| 3 | V1 cliente lookup-or-create | ~10-30 ms | SELECT (existing) OR INSERT via `close_and_insert` (new) + co-INSERT `log_transaccional` |
| 3a | (Optional) SELECT FOR UPDATE on `prod.clientes` | ~3-5 ms | PK lookup; covered by `clientes_uk01` |
| 4 | V3 per-placa lookup-or-create (1-2 placas) | ~10-30 ms | SELECT (existing) + INSERT (new) per placa + co-INSERT `log_transaccional` |
| 5 | V5 mismo_tipo_vehiculo validation (in-process) | <1 ms | No DB hit |
| 6 | V6 cantidad_maxima validation (in-process) | <1 ms | No DB hit |
| 7 | V4 per-placa placa-dup (1-2 placas) | ~5-15 ms | FK index on `subscripciones_cliente` + branch filter |
| 8 | V7 A-09 prorrateo compute (in-process) | <1 ms | Pure Decimal math |
| 9 | V9 INSERT `subscripciones_cliente` + advisory lock + bulk INSERT `subscripcion_vehiculos` | ~10-25 ms | 1 INSERT + 1 advisory lock + 1-2 INSERTs + co-INSERT `log_transaccional` |
| 8a | (Optional) F1.9 cobro sub-chain (4 INSERTs) | ~15-30 ms | IVA lookup + 4 INSERTs |
| 8b | (Optional) F1.10 FE sub-chain (3 ops: assign_consecutivo FOR UPDATE + 2 INSERTs) | ~15-30 ms | SELECT FOR UPDATE + 2 INSERTs |
| 10 | KD-VENTA-01 single commit | ~10-30 ms | Single TX commit + log_transaccional writes + sync enqueue |
| 11 | Response shape serialization | ~2-5 ms | Pydantic v2 read-shape |
| **Total (no cobro, no FE)** | — | **~55-160 ms (typical) → ≤250 ms p99** | Well within SLO |
| **Total (with cobro, no FE)** | — | **~70-190 ms (typical) → ≤250 ms p99** | Within SLO |
| **Total (with cobro + FE)** | — | **~85-220 ms (typical) → ≤250 ms p99** | Within SLO with headroom |

### 13.2 Index utilization

The handler relies on 7 indexes, all pre-existing:

| Index | Definition | Used by |
|---|---|---|
| UK `tipo_subscripciones_uk01 (tipo, vigente_desde)` | Migration 0001 line 209 | Step 2 V2 SELECT FOR UPDATE (vigente row resolution) |
| UK `clientes_uk01 (tipo_identificador, numero_identificacion, vigente_desde)` | Migration 0001 line 451 | Step 3 V1 INSERT (close_and_insert UK check) + Step 3a SELECT |
| UK `vehiculos_uk01 (placa, vigente_desde)` | Migration 0001 line 464 | Step 4 V3 INSERT (close_and_insert UK check) |
| UK `subscripcion_vehiculos_uk01 (uuid_subscripcion_cliente, uuid_vehiculo, vigente_desde)` | Migration 0001 line 508 | Step 9 V9 bulk INSERT UK check |
| FK `fk_subscripciones_cliente_uuid_cliente` | Migration 0001 (ER línea 1140) | Step 7 V4 placa-dup query |
| FK `fk_subscripcion_vehiculos_uuid_subscripcion_cliente` | Migration 0001 (ER línea 1144) | Step 9 V9 advisory lock + bulk INSERT |
| FK `fk_subscripcion_vehiculos_uuid_vehiculo` | Migration 0001 (ER línea 1145) | Step 9 V9 bulk INSERT |

No new indexes added by F1.12. The `vigente_hasta IS NULL` predicate in Step 2 (V2) is supported by the existing partial UK on `vigente_hasta` (migration 0001 trigger-managed versioning) — the optimizer uses the FK index, then filters in-memory. At expected scale (≤ 100 ventas per sucursal per day), the in-memory filter is negligible.

### 13.3 Concurrent load

The KD-VENTA-02 `SELECT FOR UPDATE` plan lock serializes concurrent ventas on the SAME `uuid_tipo_subscripcion`. This is by design — multiple ventas on the same plan in flight would race on A-09 prorrateo amounts (R9 LOW, documented). Cross-plan ventas are NOT serialized (independent locks per plan row). At expected scale (~10 concurrent ventas/sec across the entire fleet of ~500 sucursales), the per-row lock contention is negligible.

The pg_advisory_xact_lock on `uuid_subscripcion_cliente` (REQ-OP-08) is acquired AFTER the plan lock and AFTER the subscription INSERT — it serializes junction-table writes for the SAME `uuid_subscripcion_cliente`. Concurrent ventas on different subscriptions are NOT serialized at this lock (the UUID is the lock key, no row-level contention).

### 13.4 Migration cost

MIGRATION 0030 is purely a pre-flight `DO $$` block + `upgrade()` no-op + `downgrade()` no-op. No table scans, no index rebuilds, no DDL, no DML. The pre-flight is a single `information_schema.tables` COUNT query (~1 ms). Total migration cost: <100 ms.

---

## 14. Migrations

### 14.1 Migration metadata

| Property | Value |
|---|---|
| **Filename** | `0030_venta_suscripcion_optional.py` |
| **Revision** | `0030_venta_suscripcion_optional` |
| **Down revision** | `0029_reimpresion_siembra_and_permiso_anular` (F1.11 chain head) |
| **Scope** | Pre-flight `DO $$` block only. `upgrade()` and `downgrade()` are NO-OPs. |
| **LOC** | ~30 LOC |

### 14.2 Op 0 — Pre-flight `DO $$` (KD-7 F1.6 + F1.7 + F1.9 + F1.10 + F1.11 pattern)

```python
"""HU-F1.12 / MIGRATION 0030 — NO-OP audit trail (venta suscripcion).

Revision ID: 0030_venta_suscripcion_optional
Revises: 0029_reimpresion_siembra_and_permiso_anular (F1.11 chain head)
Create Date: 2026-09-15

**Scope.** NO-OP audit trail only.

  Pre-flight (KD-7 F1.6 + F1.7 + F1.9 + F1.10 + F1.11 pattern):
  ``DO $$`` block aborts the migration with a typed ``0030_preflight_abort``
  exception if any of the 5 expected [V] tables does not exist
  (``prod.tipo_subscripciones``, ``prod.clientes``, ``prod.vehiculos``,
  ``prod.subscripciones_cliente``, ``prod.subscripcion_vehiculos``).

**Pre-flight verified 2026-09-15:**
  - All 5 [V] tables pre-exist (migration 0001 lines 195-509).
  - All 5 [V] sync catalog entries pre-exist (``sync_entries_v.py``
    lines 133, 451, 483, 511, 525). DEC-VENTA-08 WITHDRAWN.
  - ``gestionar_clientes`` permission pre-seeded at migration 0001
    line 3292 area.

**Idempotency.**
  - Op 0 ``DO $$`` is read-only.
  - ``upgrade()`` and ``downgrade()`` are no-ops.

**Downgrade.** Reverse order: NO-OP (this migration added no DDL, no
rows, no grants).

**Cross-references.**
  - F1.6/F1.7/F1.9/F1.10/F1.11 MIGRATION pre-flight ``DO $$`` block
    pattern (KD-7).
  - F1.9 KD-FACT-01 + F1.10 KD-FE-01 + F1.11 KD-TKT-01 — single-commit
    precedent for the optional cobro + FE sub-chains.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0030_venta_suscripcion_optional"
down_revision = "0029_reimpresion_siembra_and_permiso_anular"
branch_labels = None
depends_on = None


# Matches the F1.5 / F1.6 / F1.10 migration pattern (0028 lines 90-91):
# cap any blocking DDL at 5s so the migration cannot stall the alembic
# runtime on a busy DB.
_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Apply the F1.12 NO-OP audit trail + pre-flight assertion."""
    op.execute(_LOCK_TIMEOUT_SQL)

    # ----------------------------------------------------------------
    # Op 0: pre-flight `DO $$` (KD-7 F1.6 + F1.7 + F1.9 + F1.10 + F1.11)
    # ----------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _n_tipo_subscripciones bigint;
            _n_clientes bigint;
            _n_vehiculos bigint;
            _n_subscripciones_cliente bigint;
            _n_subscripcion_vehiculos bigint;
        BEGIN
            SELECT count(*) INTO _n_tipo_subscripciones
                FROM pg_catalog.pg_class
                WHERE relname='tipo_subscripciones' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_clientes
                FROM pg_catalog.pg_class
                WHERE relname='clientes' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_vehiculos
                FROM pg_catalog.pg_class
                WHERE relname='vehiculos' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_subscripciones_cliente
                FROM pg_catalog.pg_class
                WHERE relname='subscripciones_cliente' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_subscripcion_vehiculos
                FROM pg_catalog.pg_class
                WHERE relname='subscripcion_vehiculos' AND relnamespace='prod'::regnamespace;

            IF _n_tipo_subscripciones IS NULL OR _n_tipo_subscripciones = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.tipo_subscripciones no existe. '
                                'Aplique migrations 0001-0029 antes.';
            END IF;
            IF _n_clientes IS NULL OR _n_clientes = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.clientes no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_vehiculos IS NULL OR _n_vehiculos = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.vehiculos no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_subscripciones_cliente IS NULL OR _n_subscripciones_cliente = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.subscripciones_cliente no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_subscripcion_vehiculos IS NULL OR _n_subscripcion_vehiculos = 0 THEN
                RAISE EXCEPTION '0030_preflight_abort: tabla prod.subscripcion_vehiculos no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;

            RAISE NOTICE '0030_preflight: 5/5 tablas OK '
                         '(tipo_subscripciones, clientes, vehiculos, '
                         'subscripciones_cliente, subscripcion_vehiculos)';
        END;
        $$;
        """
    )

    # ----------------------------------------------------------------
    # upgrade() is NO-OP: schema unchanged, sync catalog unchanged,
    # permisos unchanged. Audit trail only.
    # ----------------------------------------------------------------


def downgrade() -> None:
    """Reverse the F1.12 NO-OP (this migration added no DDL, no rows)."""
    # ----------------------------------------------------------------
    # downgrade() is NO-OP: nothing to reverse.
    # ----------------------------------------------------------------
    pass
```

### 14.3 Pre-flight verified (2026-09-15)

| # | Check | Source | Result |
|---|---|---|---|
| 1 | `prod.tipo_subscripciones` table exists | `migration 0001 lines 195-210` | CONFIRMED |
| 2 | `prod.tipo_subscripciones.cantidad_maxima_vehiculos` column exists | `migration 0001 line 202` | CONFIRMED |
| 3 | `prod.tipo_subscripciones.mismo_tipo_vehiculo` column exists | `migration 0001 line 203` | CONFIRMED |
| 4 | `prod.clientes` table exists with 8 business columns | `migration 0001 lines 435-452` | CONFIRMED |
| 5 | `prod.vehiculos` table exists with 2 business columns | `migration 0001 lines 454-465` | CONFIRMED |
| 6 | `prod.subscripciones_cliente` table exists with 5 columns, NO `monto_prorrateado` (A-09 respected) | `migration 0001 lines 483-496` | CONFIRMED |
| 7 | `prod.subscripcion_vehiculos` table exists with 2 FK columns | `migration 0001 lines 498-509` | CONFIRMED |
| 8 | Migration head is `0029_reimpresion_siembra_and_permiso_anular` | `git log --oneline -1 ddfe1f8` | CONFIRMED |
| 9 | `gestionar_clientes` permission is seeded (used by factory mount) | `api/v1/clientes.py:54-58` | CONFIRMED |
| 10 | Sync catalog: all 5 [V] entries registered | `sync/catalog/entries/sync_entries_v.py` | CONFIRMED |

All 10 checks pass. MIGRATION 0030 is NO-OP for schema, sync catalog, and permisos. DEC-VENTA-08 WITHDRAWN.

### 14.4 Notes

- 1 op (pre-flight). `upgrade()` is empty after the pre-flight. `downgrade()` is empty.
- The pre-flight is fully idempotent (read-only). Re-apply is safe.
- The migration does NOT touch any [V] table — only verifies their existence.
- No new triggers, no column changes, no FK changes, no sync catalog changes.
- The `lock_timeout = '5s'` matches the F1.5/F1.6/F1.10 pattern (MIGRATION 0028 lines 90-91).

---

## 15. Out of Scope

The following items are explicitly OUT of F1.12 scope (deferred to later HUs or documented as known limitations):

| # | Item | Reason | Deferred to |
|---|---|---|---|
| 1 | **B2B convenios corporativos** (plan.md line 1055, Fase 2+): multiple vehicles per convenio, third-party billing, `clientes_b2b` table | Explicitly out per plan.md note. `ClientesB2B` ORM model + schemas exist (`models/V/clientes_b2b.py`) but F1.12 does NOT touch them. | Fase 2+ |
| 2 | **Renovación de suscripción** (renewal = close current + INSERT new version via `close_and_insert`) | NOT in F1.12 scope. Renewal is a separate endpoint (future HU, Fase 9). | Fase 9 |
| 3 | **Anulación de suscripción** (close-only, no replacement) | NOT in F1.12 scope. | Future HU |
| 4 | **Cambio de plan mid-cycle** (upgrade/downgrade) | NOT in F1.12 scope. | Future HU |
| 5 | **Cobro retroactivo** (apply A-09 prorrateo at renewal time) | NOT in F1.12 scope. A-09 applies ONLY to the initial sale. | Future HU |
| 6 | **Multi-sucursal suscripción** (one cliente + N sucursales with the same plan) | NOT in F1.12 scope. F1.12 creates the subscription at ONE branch (the operator's `ctx.sucursal_uuid`). | Future HU |
| 7 | **Frontend reconciliation** for `clientes.py` factory mount | NOT in scope (Fase 8 frontend). | Fase 8 |
| 8 | **Settlement with payment gateway** (datafono, tarjeta) | F1.9 already handles via `medio_pago='datafono'` + `referencia`. F1.12 just passes through. | n/a (inherited) |
| 9 | **DIAN `resolucion_facturacion` resolution upgrade** when range exhausted | F1.10 already raises `ConsecutivoRangeExhaustedError` which F1.12 passes through. | n/a (inherited) |
| 10 | **Explicit FSM column** for subscription state | F1.12 uses implicit bi-temporal state (`vigente_hasta` + `estado` + `fecha_vencimiento`). Explicit FSM would be premature. | Future HU (if state machine is added) |

These items are NOT blockers for F1.12 closure. They are documented to prevent scope creep and to make the next-iteration backlog explicit.

---

## 16. References

- `plan.md` lines 1010-1054 (HU-F1.12 definition, 3 atomic tasks T1..T3, 260 LOC production budget, 4 tests mandated at line 1047)
- `plan.md` lines 1016, 1053 (scope decision: "ampliación de producto" + A-09 prorrateo decay rule)
- `plan.md` line 460 (A-09 prorrateo — no `monto_prorrateado` column on `subscripciones_cliente`)
- `modelo_datos_er.mmd` line 105 (`tipo_subscripciones`), 449 (`clientes`), 496 (`subscripciones_cliente`), 519 (`vehiculos`), 538 (`subscripcion_vehiculos`)
- `modelo_datos_er.mmd` lines 1138-1145 (FK relationships: `clientes → subscripciones_cliente`, `tipo_subscripciones → subscripciones_cliente`, `subscripciones_cliente → subscripcion_vehiculos`, `vehiculos → subscripcion_vehiculos`)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones`), 435-452 (`clientes`), 454-465 (`vehiculos`), 483-496 (`subscripciones_cliente`), 498-509 (`subscripcion_vehiculos`)
- `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py` (REVOKE re-assertion on [V] tables)
- `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head, pre-flight DO $$ pattern reused for MIGRATION 0030)
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py` lines 133-147 (`tipo_subscripciones`), 451-465 (`clientes`), 483-500 (`vehiculos`), 511-523 (`subscripciones_cliente`), 525-552 (`subscripcion_vehiculos`) — **all 5 [V] entries verified pre-existing 2026-09-15**
- `backend/packages/parkos_core/src/parkos_core/models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py` (ORM models, all existing)
- `backend/packages/parkos_core/src/parkos_core/repo/{factura,factura_electronica,resolucion_facturacion,subscripcion_activa,placa,versioned,idempotency,workflow}.py` (helpers reused + new `venta_suscripcion.py`)
- `backend/packages/parkos_core/src/parkos_core/schemas/{clientes,tipo_subscripciones,facturacion}.py` (schemas extended with `VentaSuscripcionCreate` + `VentaSuscripcionResponse` + 7 typed error schemas)
- `backend/packages/parkos_core/src/parkos_core/api/v1/{facturacion,workflows_reimpresion,clientes,_helpers,deps}.py` (handler envelope references)
- `backend/packages/parkos_core/src/parkos_core/auth/{jwt_issuer_guard,tenancy}.py` (KD-3 issuer chain + `TenantContext`)
- `openspec/specs/operations/spec.md` lines 2517-3076 (F1.10 REQ-OPS-064..074 + XR1..XR3 + F1.11 REQ-OPS-075..080 + XR4)
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/proposal.md` (sibling precedent for 16-section structure)
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/design.md` (~2450 LOC, 16 sections + 2 appendices precedent for the dedicated-router + KD-3 + tenant scope + Idempotency-Key pattern)
- `openspec/changes/hu-f1-12-venta-suscripcion/proposal.md` (~485 LOC, 16 sections, DEC-VENTA-01..07 + DEC-VENTA-08 WITHDRAWN, KD-VENTA-01..02, R1 MEDIUM RESOLVED, R2..R10)
- `openspec/changes/hu-f1-12-venta-suscripcion/exploration.md` (17 sections, ~770 LOC, pre-flight 2026-09-15 confirms all 5 [V] tables + sync catalog entries pre-existing)
- `openspec/changes/hu-f1-12-venta-suscripcion/specs/operations/spec.md` (REQ-OPS-083..090 + REQ-OPS-XR5, 8 new requirements in Given/When/Then/And form + 1 cross-cutting XR5)

---

## Appendix A: MIGRATION 0030 SQL Body (Full)

This appendix contains the COMPLETE SQL body of MIGRATION 0030 as designed in §14. It is provided here verbatim for the apply agent (sdd-apply) to use as the source of truth when writing the migration file at `backend/packages/parkos_core/migrations/versions/0030_venta_suscripcion_optional.py`. The Python wrapper is in §14.2.

### A.1 Op 0 — Pre-flight `DO $$`

```sql
DO $$
DECLARE
    _n_tipo_subscripciones bigint;
    _n_clientes bigint;
    _n_vehiculos bigint;
    _n_subscripciones_cliente bigint;
    _n_subscripcion_vehiculos bigint;
BEGIN
    SELECT count(*) INTO _n_tipo_subscripciones
        FROM pg_catalog.pg_class
        WHERE relname='tipo_subscripciones' AND relnamespace='prod'::regnamespace;
    SELECT count(*) INTO _n_clientes
        FROM pg_catalog.pg_class
        WHERE relname='clientes' AND relnamespace='prod'::regnamespace;
    SELECT count(*) INTO _n_vehiculos
        FROM pg_catalog.pg_class
        WHERE relname='vehiculos' AND relnamespace='prod'::regnamespace;
    SELECT count(*) INTO _n_subscripciones_cliente
        FROM pg_catalog.pg_class
        WHERE relname='subscripciones_cliente' AND relnamespace='prod'::regnamespace;
    SELECT count(*) INTO _n_subscripcion_vehiculos
        FROM pg_catalog.pg_class
        WHERE relname='subscripcion_vehiculos' AND relnamespace='prod'::regnamespace;

    IF _n_tipo_subscripciones IS NULL OR _n_tipo_subscripciones = 0 THEN
        RAISE EXCEPTION '0030_preflight_abort: tabla prod.tipo_subscripciones no existe. '
                        'Aplique migrations 0001-0029 antes.';
    END IF;
    IF _n_clientes IS NULL OR _n_clientes = 0 THEN
        RAISE EXCEPTION '0030_preflight_abort: tabla prod.clientes no existe. '
                        'Aplique MIGRATION 0001 antes.';
    END IF;
    IF _n_vehiculos IS NULL OR _n_vehiculos = 0 THEN
        RAISE EXCEPTION '0030_preflight_abort: tabla prod.vehiculos no existe. '
                        'Aplique MIGRATION 0001 antes.';
    END IF;
    IF _n_subscripciones_cliente IS NULL OR _n_subscripciones_cliente = 0 THEN
        RAISE EXCEPTION '0030_preflight_abort: tabla prod.subscripciones_cliente no existe. '
                        'Aplique MIGRATION 0001 antes.';
    END IF;
    IF _n_subscripcion_vehiculos IS NULL OR _n_subscripcion_vehiculos = 0 THEN
        RAISE EXCEPTION '0030_preflight_abort: tabla prod.subscripcion_vehiculos no existe. '
                        'Aplique MIGRATION 0001 antes.';
    END IF;

    RAISE NOTICE '0030_preflight: 5/5 tablas OK '
                 '(tipo_subscripciones, clientes, vehiculos, '
                 'subscripciones_cliente, subscripcion_vehiculos)';
END;
$$;
```

### A.2 `upgrade()` SQL Body (NO-OP)

```sql
-- upgrade() body is empty after the pre-flight. This migration adds:
--   - NO DDL
--   - NO rows
--   - NO grants
--   - NO sync catalog changes
-- The migration exists for head-pointer continuity only.
SELECT 1;  -- no-op marker
```

### A.3 `downgrade()` SQL Body (NO-OP)

```sql
-- downgrade() body is empty. This migration is fully reversible because
-- it added no DDL, no rows, no grants. The pre-flight DO $$ is read-only
-- and does not need to be reversed.
SELECT 1;  -- no-op marker
```

### A.4 Migration metadata

```python
revision = "0030_venta_suscripcion_optional"
down_revision = "0029_reimpresion_siembra_and_permiso_anular"
branch_labels = None
depends_on = None
```

### A.5 Known Limitation: NO-OP audit trail

This migration is a NO-OP audit trail. It exists for:

1. Head-pointer continuity in the alembic version chain.
2. Pre-flight verification that all 5 [V] tables exist (read-only check).
3. Documentation of the DEC-VENTA-08 WITHDRAWN decision (all 5 [V] sync catalog entries pre-existing).

The migration is NOT required for the schema or sync catalog or permisos. It IS required for the head pointer. If the migration is skipped in a future DB environment, downstream migrations cannot apply (`alembic upgrade head` will fail at the next migration's `down_revision` check).

---

## Appendix B: Test Matrix — REQ-OPS-083..090 + XR5 → Tests

This appendix maps each requirement from `specs/operations/spec.md` to the tests that verify it. Each requirement MUST have at least 2 tests (happy path + at least one failure path). Mirrors F1.11 design Appendix B precedent.

### B.1 REQ-OPS-083 — Single-commit atomic invariant (KD-VENTA-01)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-083-1 | `tests/unit/test_venta_suscripcion.py` | `test_cliente_nuevo_venta_exitosa_returns_201` | Happy path: 201 + 5 [V] rows visible post-commit |
| T-083-2 | `tests/integration/test_venta_suscripcion_e2e.py` | `test_venta_e2e_cobro_fe_full_happy_path` | Full happy path with cobro + FE: 9 rows visible post-commit |
| T-083-3 | `tests/static/test_venta_handler_single_commit.py` | `test_venta_suscripcion_single_commit` | KD-VENTA-01: AST walk asserts EXACTLY ONE `await session.commit()` in handler body |
| T-083-4 | `tests/static/test_venta_handler_single_commit.py` | `test_venta_suscripcion_no_savepoint` | AST walk asserts NO `begin_nested()` / `SAVEPOINT` in handler body |

### B.2 REQ-OPS-084 — Plan lock `SELECT FOR UPDATE` (KD-VENTA-02 + DEC-VENTA-04)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-084-1 | `tests/unit/test_venta_suscripcion_repo.py` | `test_buscar_tipo_subscripcion_vigente_por_uuid_returns_plan` | V2 happy path: vigente plan returned |
| T-084-2 | `tests/unit/test_venta_suscripcion_repo.py` | `test_buscar_tipo_subscripcion_vigente_por_uuid_raises_when_no_vigente` | V2 404: no vigente plan |
| T-084-3 | `tests/unit/test_venta_suscripcion_repo.py` | `test_buscar_tipo_subscripcion_vigente_por_uuid_uses_with_for_update` | Helper uses `with_for_update()` (KD-VENTA-02 + DEC-VENTA-04) |

### B.3 REQ-OPS-085 — Lock ordering: plan lock before cliente lock

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-085-1 | `tests/unit/test_venta_suscripcion_repo.py` | `test_plan_lock_acquired_before_cliente_lock_in_handler_body` | AST walk asserts `buscar_tipo_subscripcion_vigente_por_uuid` call appears before `buscar_cliente_por_uuid_o_crear` call in handler body |
| T-085-2 | (Implicit via T-083-1 happy path) | n/a | DEC-VENTA-02 ordering rule verified by manual code review |

### B.4 REQ-OPS-086 — A-09 prorrateo rule (DEC-VENTA-03)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-086-1 | `tests/unit/test_venta_suscripcion_repo.py` | `test_calcular_prorrateo_after_day_15_returns_proportional` | V7: after-day-15 prorrateo calc |
| T-086-2 | `tests/unit/test_venta_suscripcion_repo.py` | `test_calcular_prorrateo_before_day_15_returns_full_value` | V7: before-day-15 = full `plan.valor` |
| T-086-3 | `tests/unit/test_venta_suscripcion_repo.py` | `test_calcular_prorrateo_zero_duracion_raises` | V7: `duracion_dias=0` → 422 `plan_duracion_dias_invalido` |
| T-086-4 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_response_monto_prorrateado_null_when_cobrar_ahora_false` | DEC-VENTA-03: response `monto_prorrateado` is null when `cobrar_ahora=false` |

### B.5 REQ-OPS-087 — Plan lock type rationale (DEC-VENTA-04)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-087-1 | (Implicit via T-084-3) | n/a | DEC-VENTA-04: `with_for_update()` (exclusive, NOT `with_for_share()`) |
| T-087-2 | (Implicit via code review) | n/a | Helper comment + DEC-VENTA-04 documented in design §11 |

### B.6 REQ-OPS-088 — Dedicated `APIRouter` (DEC-VENTA-05)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-088-1 | `tests/integration/test_venta_suscripcion_e2e.py` | `test_venta_e2e_endpoint_reachable_at_clientes_venta_suscripcion` | Endpoint mounted at `POST /api/v1/clientes/venta-suscripcion` |
| T-088-2 | `tests/integration/test_venta_suscripcion_e2e.py` | `test_venta_e2e_inherits_gestionar_clientes_permission` | Permission gate inherited from factory mount (operador without `gestionar_clientes` → 403) |

### B.7 REQ-OPS-089 — `dv` field validated but NOT persisted (DEC-VENTA-07)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-089-1 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_accepts_cliente_con_dv_nit_valido` | NIT + dv válido: Pydantic validates, INSERT proceeds |
| T-089-2 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_rejects_cliente_con_dv_nit_invalido` | NIT + dv inválido: 422 `nit_dv_invalido` (Pydantic) |
| T-089-3 | `tests/integration/test_venta_suscripcion_e2e.py` | `test_venta_e2e_dv_not_persisted_in_clientes_row` | Post-commit, `prod.clientes` row has NO `dv` column (DEC-VENTA-07) |

### B.8 REQ-OPS-090 — `Cache-Control: no-store` on EVERY response (DEC-VENTA-06)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-090-1 | `tests/unit/test_venta_suscripcion.py` | `test_venta_suscripcion_happy_path_includes_no_store_header` | 201 response carries `Cache-Control: no-store` |
| T-090-2 | `tests/unit/test_venta_suscripcion.py` | `test_plan_mismo_tipo_vehiculo_rechaza_placas_mixtas_includes_no_store_header` | 422 error response carries `Cache-Control: no-store` |
| T-090-3 | `tests/unit/test_venta_suscripcion.py` | `test_placa_duplicada_subscripcion_vigente_rechaza_includes_no_store_header` | 422 error response carries `Cache-Control: no-store` |

### B.9 REQ-OPS-XR5 — Defense in depth 5 layers + AST walk for single-commit

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-XR5-1 | `tests/static/test_venta_handler_single_commit.py` | `test_venta_suscripcion_single_commit` | (Reused T-083-3) KD-VENTA-01 single-commit invariant |
| T-XR5-2 | `tests/static/test_venta_handler_single_commit.py` | `test_venta_suscripcion_no_savepoint` | (Reused T-083-4) No SAVEPOINT / begin_nested |
| T-XR5-3 | `tests/static/test_venta_handler_no_raw_dml.py` | `test_venta_suscripcion_no_raw_dml_on_v_tables` | No raw INSERT/UPDATE/DELETE on [V] tables in handler body (DEC-VENTA-05 enforcement) |
| T-XR5-4 | `tests/unit/test_venta_suscripcion.py` | (Implicit via T-090-1..3) | All responses (success + error) carry `Cache-Control: no-store` |

### B.10 Idempotency-Key Replay (DEC-IDEM-01, inherited from F1.6)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-IDEM-1 | `tests/integration/test_venta_suscripcion_e2e.py` | `test_venta_e2e_idempotency_key_replay_returns_cached_response` | Same `Idempotency-Key` returns cached response; NO new DB rows |
| T-IDEM-2 | (Implicit via F1.6 regression suite) | n/a | Endpoint inherits the same `Idempotency-Key` middleware (F1.6 T-PR6-002) |

### B.11 Schema Validation (Pydantic `extra='forbid'`)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-SCH-1 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_rejects_vigente_desde_injection` | Client smuggling of `vigente_desde` is rejected |
| T-SCH-2 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_rejects_estado_injection` | Client smuggling of `estado='activo'` is rejected |
| T-SCH-3 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_rejects_created_by_injection` | Client smuggling of `created_by` is rejected |
| T-SCH-4 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_rejects_uuid_sucursal_injection` | Client smuggling of `uuid_sucursal` is rejected |
| T-SCH-5 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_rejects_placas_count_0` | Pydantic `Field(min_length=1)` rejects 0 placas |
| T-SCH-6 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_rejects_placas_count_3` | Pydantic `Field(max_length=2)` rejects 3 placas |
| T-SCH-7 | `tests/unit/test_venta_suscripcion_schemas.py` | `test_create_endpoint_rejects_cliente_and_uuid_cliente_both_provided` | Model validator: exactly one of `cliente` or `uuid_cliente` |

### B.12 Tenant Scope (KD-S2 analog from F1.7)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-TEN-1 | `tests/unit/test_venta_suscripcion.py` | `test_venta_suscripcion_returns_403_si_tenant_scope_violation` | `operador-` cross-branch rejected with 403 |
| T-TEN-2 | (Implicit in happy path) | n/a | Same-branch operador accepted (200/201) |

### B.13 MIGRATION 0030 NO-OP idempotency

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-MIG-1 | `tests/integration/test_migration_0030_noop.py` | `test_migration_0030_idempotent_upgrade_downgrade_upgrade` | Full upgrade → downgrade → upgrade cycle is idempotent |
| T-MIG-2 | `tests/integration/test_migration_0030_noop.py` | `test_migration_0030_preflight_aborts_if_v_table_missing` | Pre-flight `DO $$` raises `0030_preflight_abort` if any [V] table missing |

### B.14 Repo Helpers (3 tests, ~30 LOC)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-REPO-1 | `tests/unit/test_venta_suscripcion_repo.py` | `test_buscar_cliente_por_uuid_o_crear_new_path` | New cliente via `close_and_insert(current_uuid=None)` |
| T-REPO-2 | `tests/unit/test_venta_suscripcion_repo.py` | `test_buscar_cliente_por_uuid_o_crear_existing_path` | Existing cliente via `current_version(uuid=...)` |
| T-REPO-3 | `tests/unit/test_venta_suscripcion_repo.py` | `test_validar_placa_duplicada_subscripcion_returns_422_when_active_found` | V4 reverse-direction: active subscripcion for placa → 422 |

### B.15 Test Coverage Summary

| REQ | Total tests | Happy path | Failure paths | AST walks |
|---|---|---|---|---|
| REQ-OPS-083 | 4 | 2 | 0 | 2 |
| REQ-OPS-084 | 3 | 1 | 1 | 0 |
| REQ-OPS-085 | 2 | 1 | 0 | 1 |
| REQ-OPS-086 | 4 | 2 | 1 | 0 |
| REQ-OPS-087 | 2 | 0 | 0 | 0 (code review) |
| REQ-OPS-088 | 2 | 1 | 1 | 0 |
| REQ-OPS-089 | 3 | 1 | 1 | 0 |
| REQ-OPS-090 | 3 | 1 | 2 | 0 |
| REQ-OPS-XR5 | 4 | 0 | 0 | 3 |
| DEC-IDEM-01 | 2 | 1 | 0 | 0 |
| Schema (extra='forbid') | 7 | 0 | 7 | 0 |
| Tenant scope | 2 | 1 | 1 | 0 |
| MIGRATION 0030 | 2 | 1 | 1 | 0 |
| Repo helpers | 3 | 2 | 1 | 0 |
| **Total unique test functions** | **~43** | **~14** | **~17** | **~6** |

All 8 explicit requirements (REQ-OPS-083..090) + the cross-cutting XR5 + the inherited DEC-IDEM-01 + schema validation + tenant scope + MIGRATION 0030 idempotency + repo helpers are covered by at least 2 tests each (where applicable). The breakdown matches the proposal §11.1..11.7 test files (~14 test functions across 7 files, expanded with the new repo + schema + migration + AST walk tests).

---

## Closing

This design closes the HU-F1.12 backend prerequisite for the operador-facing atomic sale-at-the-counter workflow. The work is bounded: 1 handler + 1 repo module + 2 Pydantic schemas + 7 typed error schemas + 1 NO-OP MIGRATION 0030 + 1 router mount extension. No new tables, no new FKs, no sync catalog changes, no permission re-seeds.

The key architectural decisions (DEC-VENTA-01..07 + DEC-VENTA-08 WITHDRAWN + KD-VENTA-01..02) follow the F1.11 / F1.10 / F1.9 / F1.7 / F1.6 / F1.5 precedents verbatim. The defense-in-depth 5 layers (issuer chain, permission gate, tenant scope, single-commit invariant, handler error mapping) protect every write. The AST walks enforce the invariants at compile-time.

**next_recommended: sdd-tasks hu-f1-12-venta-suscripcion** to decompose the 43 tests + 1 handler + 1 migration into atomic T1..Tn tasks across clusters T-Setup / T-Schema / T-Repo / T-Hand


