# Spec: operational

> **Delta for change**: `hu-f1-8-cotizar`
> **Capability**: `operational`
> **Date**: 2026-09-14
> **Source of truth**: `openspec/changes/hu-f1-8-cotizar/proposal.md`
> (D-HU-F1.8-1..7), `exploration.md` (KD-1 lock, KD-2 hardcoded CASE, KD-3 typed error,
> KD-IVA off-scope seed), `plan.md` GAP-BE-09 contract lines 7423–7446.
> **Precedente upstream**: este change extiende la capability **operational** ya
> consolidada en `openspec/specs/operations/spec.md` (último REQ-OPS-NNN vigente:
> REQ-OPS-021 tras el merge de HU-F1.4). HU-F1.8 introduce 4 requirements nuevos
> (REQ-OPS-022..025) sobre esa misma capability; los REQ-OPS-001..021 NO se modifican.

## Purpose

Adds the server-side cotización endpoint for HU-F1.8, complementing the HU-F1.4
vigente filter. The endpoint computes the fiscal breakdown (`subtotal`, `iva`,
`total`, `tiempo_minutos`) and the 15-minute validity window that the future
HU-F1.7 `POST /operacion/salidas` will consume as the canonical quote. The whole
pricing formula lives in a single `STABLE` PL/pgSQL function
`prod.calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb`, executed inside a
transactional context so that a `SELECT … FOR SHARE` on `prod.tarifas_sucursal`
prevents a tariff closure between cotización and cobro (KD-1). The handler
`GET /api/v1/operacion/cotizar?uuid_ingreso={uuid}` is a thin wrapper that maps
the JSONB envelope to either `CotizarResponse` (200) or a typed `HTTPException`
(`ingreso_no_encontrado` 404, `tarifa_no_vigente` 404, `iva_no_configurado` 500).

## Requirements

### REQ-OPS-022: GET `/api/v1/operacion/cotizar?uuid_ingreso` returns the fiscal breakdown
**Given** an open `prod.ingreso` row for `uuid_ingreso=X` (i.e. without any non-anulada
`prod.salidas`), an active row in `prod.tarifas_sucursal` for the
`(uuid_sucursal, uuid_tipo_vehiculo)` combination that is vigente at `NOW()` per the
bi-temporal predicate (`vigente_desde <= NOW() AND (vigente_hasta IS NULL OR
vigente_hasta > NOW()) AND estado='activo'`), and an active row in `prod.impuestos`
with `nombre='IVA'` and `porcentaje > 0` that is also vigente at `NOW()`
**When** the handler receives the request with a valid JWT bearing an `operador-`
or `admin-` issuer (`_ingreso_issuer_dep`)
**Then** the PL/pgSQL `prod.calcular_cotizacion(p_uuid_ingreso)` MUST execute
`SELECT … FOR SHARE` against the matched `tarifas_sucursal` row, MUST compute
`subtotal`, `iva`, `total`, `tiempo_minutos`, and `vigente_hasta = NOW() + INTERVAL
'15 minutes'`, MUST apply the formula `iva = total * porcentaje_impuesto` and
`subtotal = total - iva`, and MUST return `200 OK` with body
`{cobrar: true, subtotal, iva, total, tiempo_minutos, tarifa_uuid, vigente_hasta}`
**And** the response MUST carry the header `Cache-Control: no-store` so no proxy
or intermediary can serve a stale quote (R8).

### REQ-OPS-023: Active monthly subscription by plate returns `cobrar: false`
**Given** the `prod.ingreso` row exists and is open, AND the plate joined through
`prod.subscripcion_vehiculos` → `prod.subscripciones_cliente` → `prod.vehiculos`
has an active subscription vigente at `NOW()` per the same bi-temporal predicate
**When** the handler invokes `prod.calcular_cotizacion(p_uuid_ingreso)`
**Then** the PL/pgSQL MUST delegate to the SQL port of
`resolve_active_subscription_for_exit` (precedent at
`backend/.../api/v1/operacion.py:215-277`), MUST short-circuit the pricing
pipeline, and MUST return `200 OK` with body `{cobrar: false,
motivo: "mensualidad_vigente"}`
**And** the PL/pgSQL MUST NOT acquire the `SELECT … FOR SHARE` lock on
`tarifas_sucursal` and MUST NOT invoke the pricing formula, because no cash
movement applies — the monthly fee is settled by the subscription, not the exit.

### REQ-OPS-024: Typed errors with explicit precedence
**Given** any valid request carrying a JWT signed by an allowed issuer
**When** the PL/pgSQL function evaluates its preconditions for
`p_uuid_ingreso`
**Then** the function MUST return the first applicable error in this exact
precedence order: (1) `jsonb_build_object('error', 'ingreso_no_encontrado')` →
handler maps to `404 Not Found` when the `uuid_ingreso` does not exist in
`prod.ingreso` or already has a non-anulada row in `prod.salidas`; (2)
`jsonb_build_object('error', 'tarifa_no_vigente')` → handler maps to
`404 Not Found` when the previous check passed but no `tarifas_sucursal` row
satisfies the bi-temporal predicate for the
`(uuid_sucursal, uuid_tipo_vehiculo)` combination at `NOW()` (KD-3); (3)
`jsonb_build_object('error', 'iva_no_configurado')` → handler maps to
`500 Internal Server Error` when the two previous checks passed but no
`prod.impuestos` row has `nombre='IVA'` vigente at `NOW()` with
`porcentaje > 0` (KD-IVA — seeding is out of scope of F1.8 and is owned by
HU-F14.2 Parte II)
**And** the precedence MUST be strictly
`ingreso_no_encontrado > tarifa_no_vigente > iva_no_configurado`; no other
ordering is permitted, and a single response MUST never combine two error codes.

### REQ-OPS-025: `calcular_cotizacion` declares STABLE or VOLATILE; AST walk rejects mutations

> **Note**: Originally letter-stated as `STABLE` only; reconciled 2026-09-14 to accept `VOLATILE` when `SELECT ... FOR SHARE` is required (Postgres rejects shared locks in STABLE/IMMUTABLE functions). The read-only guarantee is enforced by an AST walk over the migration body rejecting INSERT|UPDATE|DELETE|TRUNCATE|MERGE tokens, not by the volatility declaration.

**Given** the Alembic migration 0022 declares the function with `LANGUAGE plpgsql STABLE` or `LANGUAGE plpgsql VOLATILE` (either is acceptable; VOLATILE is required when using `SELECT ... FOR SHARE`)
**When** `pytest tests/static/test_no_write_in_calcular_cotizacion.py` runs
**Then** the test MUST walk the migration body, parse `op.execute("""...""")`, and reject any `INSERT|UPDATE|DELETE|TRUNCATE|MERGE` token (case-insensitive, outside string literals and comments)
**And** the test MUST be a regular part of the pytest collection (auto-discovered in `backend/tests/static/`)
**And** the full `uv run pytest -q backend/tests/` MUST pass with this AST check included.

## Modified Capabilities

- `operational`: the HU-F1.4 vigente filter is preserved unchanged
  (REQ-OPS-017..021 still apply); this delta adds the cotización surface that
  consumes it (REQ-OPS-022..025). The merged main spec
  (`openspec/specs/operations/spec.md`) gains four requirements and no existing
  requirement is modified.
- `backend/packages/parkos_core/migrations/versions/0022_create_calcular_cotizacion.py`
  (NUEVO) — `CREATE FUNCTION prod.calcular_cotizacion(uuid) RETURNS jsonb
  LANGUAGE plpgsql STABLE` plus `GRANT EXECUTE` to `parkos_app`. No table or
  column changes; `modelo_datos_er.mmd` intact.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (MODIFICAR)
  — new `@router.get("/cotizar")` handler over the existing custom `APIRouter`
  (line 52), guarding the response with `Cache-Control: no-store` and
  `_ingreso_issuer_dep`.
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (MODIFICAR)
  — new `CotizarResponse` Pydantic model with discriminator `cobrar: bool` and
  conditional fields `motivo`, `subtotal`, `iva`, `total`, `tiempo_minutos`,
  `tarifa_uuid`, `vigente_hasta`.
- `backend/packages/parkos_core/src/parkos_core/repo/cotizacion.py` (NUEVO) —
  thin async wrapper `cotizar_ingreso(session, *, uuid_ingreso) -> dict`
  invoking the PL/pgSQL and mapping JSONB envelopes to typed exceptions.
- `backend/tests/static/test_no_write_in_calcular_cotizacion.py` (NUEVO) —
  AST guard enforcing `STABLE` and no `INSERT|UPDATE|DELETE|TRUNCATE|MERGE`
  in the function body (R7).
- `backend/tests/unit/test_calcular_cotizacion.py` (NUEVO) and
  `backend/tests/integration/test_calcular_cotizacion_db.py` (NUEVO) — RED-then-
  GREEN coverage for REQ-OPS-022..025.

## Out of Scope

- Seeding `prod.impuestos` with `nombre='IVA'` — owned by HU-F14.2 Parte II
  (KD-IVA). Apply does NOT seed; design documents the exact recipe.
- A `POST /operacion/cotizar` endpoint (side-effecting). The contract is GET
  only and idempotent.
- Adding a `unidad_minutos` column to the ER. The CASE mapping lives inside the
  PL/pgSQL (KD-2).
- Reimplementing `resolve_active_subscription_for_exit` — the helper is reused
  via a SQL port; if HU-F1.4 changes the helper, sync the constant
  SQL manually (drift risk documented in `exploration.md`).
- Locks on `prod.impuestos` or `prod.subscripciones_cliente`. Only
  `prod.tarifas_sucursal` is locked `FOR SHARE` (KD-1).
