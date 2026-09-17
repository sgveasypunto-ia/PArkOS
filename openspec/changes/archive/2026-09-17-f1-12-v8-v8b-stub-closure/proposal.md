# Proposal: F1.12 V8/V8b STUB closure (REQs plan.md + canon)

> **Change**: `2026-09-17-f1-12-v8-v8b-stub-closure`
> **Phase**: proposal (sdd-propose)
> **Capability**: operations (extends REQ-OPS-083..090 + REQ-OPS-XR5)
> **Date**: 2026-09-17
> **Author**: orchestrator

## Intent

Close the F1.12 STUB that the original archive-report deferred as "D2 LOW" — the
sub-chain that wires `cobrar_ahora=true` to the F1.9 cobro flow (V8) and
`emitir_factura_electronica=true` to the F1.10 FE flow (V8b). `plan.md`
lines 1033, 1036, 1053 T2, 2027, 2029 + REQ-OPS-090 canon explicitly require this;
the original deferral was an erroneous sub-agent judgment.

## Scope

**In scope:**
- New MIGRATION 0037 (nullable FK `prod.facturas.uuid_subscripcion_cliente`)
- ORM update `models/L_E/facturas.py` for the new column
- `auth/tenancy.py::TenantContext` extended with `uuid_sesion` (closes pre-existing F1.9 bug)
- `api/v1/clientes_venta.py` Step 8a (V8 cobro) + Step 8b (V8b FE) wired to F1.9/F1.10 helpers
- `schemas/facturacion.py::FacturaItemCreate` reused with `tipo="servicio"`
- 2 new unit tests in `tests/unit/test_venta_suscripcion_handler.py`
- NO spec delta (REQ-OPS-090 already in canon — change is pure implementation of existing requirement)

**Out of scope:**
- Frontend changes (Fase 1 frontend unchanged; V8 only matters on backend)
- AST walk tests for V8 (deferred — current mock tests pin the contract; AST walk to land in a future quality refactor)
- `ConsecutivoRangeExhaustedError` typed attributes (currently `RuntimeError` plain; F1.10 still uses this)

## Approach

1. Migration 0037 + ORM update (Q1-A: proper FK, ON DELETE SET NULL).
2. Extend `TenantContext` with `uuid_sesion` sourced from JWT `sesion` claim (Q2: closes pre-existing F1.9 bug as a side effect).
3. Reuse F1.9 helpers (`crear_factura_evento`, `crear_factura_detalle_bulk`, `crear_factura_impuesto_iva`, `crear_factura_pago`) and F1.10 helpers (`buscar_resolucion_vigente_por_sucursal`, `assign_consecutivo`, `crear_factura_electronica_inicial`, `crear_envio_dian_inicial`).
4. KD-VENTA-01 single-commit invariant preserved: V8 inserts are `session.add + flush` only; the handler's single `await session.commit()` at the end covers everything.

## Rationale

**Why now (not "D2 LOW"):** `plan.md` line 1053 T2 explicitly mandates the cobro
sub-chain be implemented (cálculo de prorrateo si la venta ocurre después
del día 15, persistido en `factura_detalle`). The original archive-report
called this LOW without cross-referencing plan.md — a verification gap that
this change closes.

**Why Q1-A (migration + FK) over Q1-B (orphan + response correlation):**
orchestrator decision on 2026-09-17. Reportería futuras (F17.2 reportería
operacional, F17.3 reportería financiera) will need to JOIN
`prod.facturas` with `prod.subscripciones_cliente` for venta-atómica
analysis. Orphan + response correlation would force a UNION across two
PK domains in every reportería query. The migration cost is one Alembic
script + one ORM column + a few regression tests; future-proofing value is
high.

**Why TenantContext extension now:** F1.9 production code at
`api/v1/facturacion.py:376,466` already reads `ctx.uuid_sesion` but the
dataclass does not declare it. Without this fix, V8 inherits the latent
`AttributeError` from F1.9. V12 close-out includes this 5-line dataclass
extension + the corresponding `get_tenant_ctx` branch.

## Risk

**Low.** Net new surface area is a single FK column + ~80 LOC of glue code in
the handler. All F1.9/F1.10 helpers are reused (no new helpers). KD-VENTA-01
single-commit invariant is verified by the existing AST walk
(`tests/static/test_venta_handler_single_commit.py`).

The pre-existing mypy baseline debt on the file (5 errors: lines 160, 206,
239, 453, 456) is documented in `verify-report.md` and is not introduced by
this change.

## Forward hooks

- Fase 1 frontend (already shipped): V8 response shape `VentaSuscripcionResponse` now carries real `uuid_factura` / `uuid_factura_electronica` / `uuid_envio_dian` UUIDs when `cobrar_ahora=true`. Frontend tiquete logic can re-print receipts with the real invoice reference.
- F11 sync: `prod.facturas` rows from V8 propagate via the existing `factura_*` sync catalog entries (`sync_catalog/spec.md`); `prod.subscripciones_cliente` is `[V]` bi-temporal and already sync'd. The new `uuid_subscripcion_cliente` FK column is sync'd as part of the parent `facturas` row (no catalog change needed).
- F17 reportería: JOIN via `facturas.uuid_subscripcion_cliente` is now available (was orphan before).

## Acceptance criteria

1. MIGRATION 0037 applies cleanly on fresh DB and is idempotent on replay.
2. `pytest tests/unit/test_venta_suscripcion*.py` → 50/50 pass (no regression; 2 new tests added).
3. `uv run mypy --strict packages/parkos_core/src/parkos_core/api/v1/clientes_venta.py` → 5 pre-existing errors only (no new errors introduced by this change).
4. `uv run mypy --strict packages/parkos_core/src/parkos_core/auth/tenancy.py` → 0 errors.
5. AST walk `tests/static/test_venta_handler_single_commit.py` still PASS (1 commit total).
6. Commit + merge to `dev` + push to `origin` with `--no-ff` per AGENTS.md regla #8.