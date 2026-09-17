# Design: F1.12 V8/V8b STUB closure

> **Change**: `2026-09-17-f1-12-v8-v8b-stub-closure`
> **Phase**: design (sdd-design)
> **Capability**: operations (extends REQ-OPS-083..090)
> **Delivery**: single-pr (4 commits, 1 migration + 1 ORM + 1 dataclass + 1 handler edit + 1 test edit)

## Technical Approach

### File operations (atomic per commit)

**Commit 1** — MIGRATION 0037 (idempotent): `backend/packages/parkos_core/migrations/versions/0037_add_uuid_subscripcion_cliente_to_facturas.py`
- `ALTER TABLE prod.facturas ADD COLUMN IF NOT EXISTS uuid_subscripcion_cliente UUID NULL`
- FK `fk_facturas_subscripcion_cliente` via DO block (Alembic's create_foreign_key is not replay-safe)
- `ON DELETE SET NULL` (DIAN retention forbids cascade-delete of issued invoices)

**Commit 2** — ORM update: `models/L_E/facturas.py`
- Add `uuid_subscripcion_cliente: Mapped[uuid_lib.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)`

**Commit 3** — TenantContext extension: `auth/tenancy.py`
- Add `uuid_sesion: uuid_lib.UUID | None = None` field to `@dataclass(frozen=True) class TenantContext`
- `get_tenant_ctx()` reads `claims.get('sesion')` for `operador-` issuer; passes through as `uuid_sesion_ctx`
- `admin-` and `sync-agent-` issuers always get `uuid_sesion=None` (no turno)

**Commit 4** — Handler + tests: `api/v1/clientes_venta.py` + `tests/unit/test_venta_suscripcion_handler.py`
- Step 8a (V8): inline voucher check → IVA gate (`obtener_iva_vigente`) → `crear_factura_evento` with `uuid_subscripcion_cliente=subscripcion.uuid` → `crear_factura_detalle_bulk` (1 row, `tipo='servicio'`, `concepto='subscripcion_mensual_prorrateada'` or `'subscripcion_mensual'`) → `crear_factura_impuesto_iva` → `crear_factura_pago` with `uuid_sesion=ctx.uuid_sesion`
- Step 8b (V8b): `buscar_resolucion_vigente_por_sucursal` → prefijo not-empty check → `assign_consecutivo(session, resolucion.uuid, source_event_uuid=subscripcion.uuid)` (idempotent per pair) → `crear_factura_electronica_inicial` → `crear_envio_dian_inicial`
- Response: `monto_prorrateado` is set when `cobrar_ahora=True AND monto_proporcional is not None`
- 2 new unit tests: voucher_requerido (400) + V8 cobro subchain call-all-helpers

### Q1-A: factura → subscripcion linkage

**Source-of-truth anchor**: `models/L_E/facturas.py:28-72` (current schema) + `models/V/subscripciones_cliente.py:26` (FK target).

```sql
-- MIGRATION 0037 upgrade() body
ALTER TABLE prod.facturas
  ADD COLUMN IF NOT EXISTS uuid_subscripcion_cliente UUID NULL;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint
                 WHERE conname = 'fk_facturas_subscripcion_cliente'
                   AND conrelid = 'prod.facturas'::regclass) THEN
    ALTER TABLE prod.facturas
      ADD CONSTRAINT fk_facturas_subscripcion_cliente
      FOREIGN KEY (uuid_subscripcion_cliente)
      REFERENCES prod.subscripciones_cliente (uuid)
      ON DELETE SET NULL;
  END IF;
END$$;
```

**Why nullable + ON DELETE SET NULL:**
- Nullable: F1.8/F1.9 callers leave it None (they use `uuid_ingreso` / `uuid_salida`). Only the F1.12 venta-atómica path populates it.
- `ON DELETE SET NULL` (not CASCADE): when a `prod.subscripciones_cliente` row is closed-and-archived (the bi-temporal `[V]` lifecycle creates new versions, never deletes; but the `ON DELETE` covers catastrophic admin actions), historical `prod.facturas` rows MUST be preserved — DIAN retention forbids losing the invoice.

### Q2: TenantContext.uuid_sesion

**Source-of-truth anchor**: `auth/tenancy.py:28-35` (current dataclass) + `api/v1/facturacion.py:376,466` (the F1.9 reads that already expect `ctx.uuid_sesion`).

```python
# New dataclass field
@dataclass(frozen=True)
class TenantContext:
    actor_uuid: uuid_lib.UUID
    actor_rol: str
    issuer_prefix: str
    sucursal_uuid: uuid_lib.UUID | None
    uuid_sesion: uuid_lib.UUID | None = None  # NEW
```

```python
# get_tenant_ctx() operador branch (new code)
sesion_str = claims.get("sesion")
uuid_sesion_ctx: uuid_lib.UUID | None = None
if sesion_str:
    try:
        uuid_sesion_ctx = uuid_lib.UUID(sesion_str)
    except (ValueError, TypeError):
        uuid_sesion_ctx = None  # malformed -> None (do NOT raise 401)
```

**Why silent fallback on malformed claim:** operators between turnos (logged in but no active `prod.sesion`) carry no `sesion` claim; raising 401 would lock them out mid-shift. `None` flows through to `factura_pagos.uuid_sesion` which is already nullable.

### V8 cobro sub-chain (Step 8a)

**Source-of-truth anchor**: `api/v1/clientes_venta.py:234-241` (current empty block) + REQ-OPS-090 canon (`operations/spec.md` lines 3611-3636) + `plan.md` line 1053 T2.

```
Step 8a flow:
1. datafono sin referencia -> 400 voucher_requerido
2. obtener_iva_vigente() == None -> 500 iva_no_configurado
3. monto_a_cobrar = monto_proporcional if fecha_inicio_cobertura.day > 15 else plan.valor
4. detalle_concepto = "subscripcion_mensual_prorrateada" | "subscripcion_mensual"
5. iva_monto = monto_a_cobrar * iva_porcentaje (quantize 0.01)
6. total_con_iva = monto_a_cobrar + iva_monto
7. crear_factura_evento(new_attrs={uuid_sucursal, subtotal=monto_a_cobrar, descuento=0, total=total_con_iva, uuid_subscripcion_cliente=subscripcion.uuid})
8. crear_factura_detalle_bulk([FacturaItemCreate(tipo="servicio", concepto=detalle_concepto, cantidad=1, valor_unitario=monto_a_cobrar)])
9. crear_factura_impuesto_iva(uuid_factura, base=monto_a_cobrar, iva=iva_porcentaje)
10. crear_factura_pago(uuid_factura, medio_pago, valor=total_con_iva, referencia, uuid_sesion=ctx.uuid_sesion)
```

### V8b FE sub-chain (Step 8b)

**Source-of-truth anchor**: `api/v1/clientes_venta.py:243-250` (current empty block) + REQ-OPS-064..074 canon (F1.10) + `plan.md` line 2029 (Tablas ER tocadas includes `factura_electronica`).

```
Step 8b flow (gated on emitir_factura_electronica AND uuid_factura is not None):
1. buscar_resolucion_vigente_por_sucursal(uuid_sucursal) -> None -> 404 resolucion_facturacion_no_encontrada
2. resolucion.prefijo is None or empty -> 409 resolucion_sin_prefijo
3. assign_consecutivo(resolucion.uuid, source_event_uuid=subscripcion.uuid) -> int (idempotent)
   ConsecutivoRangeExhaustedError -> 409 numeracion_agotada
4. crear_factura_electronica_inicial(uuid_factura, uuid_resolucion_facturacion, prefijo, consecutivo)
   FacturaElectronicaYaExisteError -> 409 (carries uuid_factura)
5. crear_envio_dian_inicial(uuid_factura_electronica, payload={prefijo, consecutivo, uuid_factura, uuid_subscripcion_cliente})
```

**Why `source_event_uuid=subscripcion.uuid` for assign_consecutivo:**
`assign_consecutivo` is idempotent on the `(resolucion_uuid, source_event_uuid)` pair. Using `subscripcion.uuid` (deterministic, unique per venta) makes the FE consecutivo a deterministic function of the subscripcion — replays produce the same consecutivo, no collisions across re-attempts.

## Validation chain

1. `uv run alembic upgrade head --sql` → migration 0037 rendered SQL is INSERT-idempotent.
2. `uv run pytest tests/unit/test_venta_suscripcion*.py -v` → 50/50 pass (2 new + 48 pre-existing).
3. `uv run mypy --strict packages/parkos_core/src/parkos_core/api/v1/clientes_venta.py` → 5 errors (all pre-existing baseline, none introduced by this change).
4. `uv run mypy --strict packages/parkos_core/src/parkos_core/auth/tenancy.py` → 0 errors (TenantContext extension is type-safe).
5. `git grep "^### Requirement: REQ-OPS-090" openspec/specs/operations/spec.md` → 1 match (canon unchanged; this change implements the existing requirement).
6. `tests/static/test_venta_handler_single_commit.py` → PASS (exactly 1 `await session.commit()` after V8 inserts added).

## File inventory

**New files (1):**
- `backend/packages/parkos_core/migrations/versions/0037_add_uuid_subscripcion_cliente_to_facturas.py` (~70 LOC)

**Modified files (4):**
- `backend/packages/parkos_core/src/parkos_core/models/L_E/facturas.py` (+10 LOC: column declaration + docstring)
- `backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` (+25 LOC: dataclass field + operador branch + admin-/sync-agent defaults)
- `backend/packages/parkos_core/src/parkos_core/api/v1/clientes_venta.py` (+95 LOC: V8 + V8b wired helpers + 3 new imports + response tweak)
- `backend/tests/unit/test_venta_suscripcion_handler.py` (+125 LOC: 2 new tests + helper patches)

**SDD artifacts (6):**
- `openspec/changes/2026-09-17-f1-12-v8-v8b-stub-closure/{proposal,design,tasks,verify-report,archive-report}.md`
- `openspec/changes/2026-09-17-f1-12-v8-v8b-stub-closure/specs/operations/spec.md` (NO-OP delta stub — REQ-OPS-090 already in canon)

Total: 7 file touches (~325 LOC delta production + 125 LOC tests).

## Verification plan

| # | Gate | Method | Expected |
|---|---|---|---|
| G1 | Migration 0037 applies | `uv run alembic upgrade head` on testcontainer DB | exit 0 |
| G2 | Migration idempotency | `uv run alembic upgrade head` twice | exit 0 second time (no-op) |
| G3 | Migration downgrade | `uv run alembic downgrade -1` + `upgrade head` | exit 0 + exit 0 |
| G4 | All 50 unit tests pass | `uv run pytest tests/unit/test_venta_suscripcion*.py -v` | 50 passed |
| G5 | mypy strict on handler (no new errors) | `uv run mypy --strict .../clientes_venta.py` | 5 errors (same as baseline) |
| G6 | mypy strict on tenancy | `uv run mypy --strict .../auth/tenancy.py` | 0 errors |
| G7 | AST walk single-commit | `uv run pytest tests/static/test_venta_handler_single_commit.py -v` | PASS (1 commit) |
| G8 | Spec canon unchanged | `git grep "^### Requirement: REQ-OPS-090" openspec/specs/operations/spec.md` | 1 match (unchanged) |
| G9 | Commit hygiene | `git log -p` on feature branch | author Parkos Dev, no Co-authored-by, conventional Spanish |

## Out of scope

- AST walk tests for V8 specifically (mock tests already pin the contract; AST walk to land in a separate quality refactor)
- Integration tests with testcontainers (require Docker — sandbox limitation; CI matrix required)
- `ConsecutivoRangeExhaustedError` typed attributes (currently `RuntimeError` plain; F1.10 still uses this; refactor out of scope)
- V8 FE dispatcher to DIAN provider (cloud-side, Fase 2 Parte II; this change stops at the FE row + `envio_dian` insert)