# Design: HU-F1.8 — calcular_cotizacion + GET /operacion/cotizar

> **Change**: `hu-f1-8-cotizar`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.8 — Function `calcular_cotizacion` + `GET /operacion/cotizar`
> **Date**: 2026-09-14
> **Source of truth**: `proposal.md` (D-HU-F1.8-1..7) and `exploration.md`.
> **Cross-references**: `plan.md` (HU-F1.8 lines 845-887, GAP-BE-09 contract lines 7423-7446, A-02 adaptation line 453), `modelo_datos_er.mmd` (`ingreso` 577-596, `tarifas_sucursal` 406-426, `impuestos` 187-207, `subscripciones_cliente` 496-518, `subscripcion_vehiculos` 538-557, `vehiculos` 519-537, `salidas` 761-777, `tipo_tarifa` 128-144, `tipos_vehiculo` 87-104, `sucursal` 341-365), `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (`resolve_active_subscription_for_exit` 215-277, `APIRouter` custom line 52), precedent `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/` (bi-temporal predicate reused, commit `de4d2fc`).

## 1. Context

HU-F1.8 delivers the server-side quotation of an `ingreso`. It is the "calculate the receipt before paying" primitive that HU-F1.7 (`POST /operacion/salidas`) and HU-F1.9 (facturación) require as input. Given a `uuid_ingreso`, it returns the fiscal breakdown (`subtotal`, `iva`, `total`, `tiempo_minutos`) plus a 15-minute validity window so downstream consumers can reject expired quotations without re-querying the DB. The contract is fixed in `plan.md` §1.8 GAP-BE-09 (lines 7423-7446) and the formula in DEC-SUC-24 / CU-02 AC7.

This change ships **4 key decisions (KD)** captured in the proposal and confirmed 2026-09-14:

- **KD-1** — pessimistic lock `SELECT … FOR SHARE` on `tarifas_sucursal` inside the PL/pgSQL function (closes the race window between cotizar and POST /salidas).
- **KD-2** — `unidad_minutos` resolved via a hardcoded `CASE tipo_tarifa.tipo` inside PL/pgSQL (no `unidad_minutos` column added to the canonical ER).
- **KD-3** — new typed error `404 tarifa_no_vigente` (distinguishes "no applicable tariff" from "ingreso inválido").
- **KD-IVA** — `impuestos.IVA` seeding is **out of scope** for F1.8 (ownership HU-F14.2 Parte II); design documents the seeding as a deployment blocker with the exact recipe.

Files produced by this change: `migrations/versions/0022_create_calcular_cotizacion.py` (new), `api/v1/operacion.py` (modify), `schemas/operacion.py` (modify), `repo/cotizacion.py` (new), `tests/unit/test_calcular_cotizacion.py` (new), `tests/integration/test_calcular_cotizacion_db.py` (new), `openspec/specs/operations/spec.md` (modify).

## 2. Goals & Non-Goals (architectural)

**Goals.**

1. All pricing logic lives in PL/pgSQL — the handler is a thin adapter. This is the only way to guarantee transactional atomicity between `cotizar` and `POST /salidas`.
2. The function declares `STABLE` (not `VOLATILE`) and is enforced read-only by an AST check in CI — no `INSERT|UPDATE|DELETE` allowed in its body.
3. Lock scope is minimal: only `tarifas_sucursal` (KD-1); `impuestos` and `subscripciones_cliente` are read without locking.
4. The function returns `jsonb` (not a SQL row type) so the contract can evolve without an Alembic schema migration per field.
5. Existing precedent `resolve_active_subscription_for_exit` (`operacion.py:215-277`) is reused — ported into SQL inside the function (no HTTP round-trip, no Python re-implementation).

**Non-Goals.**

1. No ER migration — `modelo_datos_er.mmd` is byte-identical before and after.
2. No `make_router` change — `/operacion` uses an `APIRouter` custom (`operacion.py:52`), precedent.
3. No seeding of `impuestos.IVA` — KD-IVA, HU-F14.2 Parte II.
4. No coupling to client-side calculation.
5. No new `vigente_hasta` semantics on `tarifas_sucursal` — that is HU-F1.4's surface; F1.8's `vigente_hasta` is the **cotización's** 15-minute validity, not the tariff's.
6. No lock on `vehiculos` or `subscripciones_cliente`.

## 3. Architecture Overview

```
HTTPS GET /api/v1/operacion/cotizar?uuid_ingreso={uuid}
        │
        │  requires_issuer("operador-", "admin-")
        │  Cache-Control: no-store  (R8)
        ▼
┌────────────────────────────────────────────────────────────────────┐
│ api/v1/operacion.py  (APIRouter custom, line 52)                   │
│ @router.get("/cotizar")  (NUEVO handler cotizar_ingreso)           │
│                                                                    │
│ 1. validate uuid_ingreso (Pydantic UUID4)                          │
│ 2. repo/cotizacion.py::cotizar_ingreso(session, *, uuid_ingreso)   │
│      │  SELECT prod.calcular_cotizacion(:uuid) AS payload          │
│      ▼                                                             │
│ 3. map jsonb → CotizarResponse | HTTPException                     │
│      {error:'ingreso_no_encontrado'}      → 404                    │
│      {error:'tarifa_no_vigente'}          → 404  (KD-3)             │
│      {error:'iva_no_configurado'}         → 500  (KD-IVA)           │
│      {cobrar:false, motivo:...}           → 200                     │
│      {cobrar:true, subtotal, iva, ...}    → 200                     │
└────────────────────────────────────────────────────────────────────┘
        │
        ▼ PL/pgSQL  prod.calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb   STABLE
┌────────────────────────────────────────────────────────────────────┐
│ BEGIN;                                                             │
│   1. SELECT ingreso + NOT EXISTS salidas no-anulada                 │
│      → 0 filas → jsonb {error:'ingreso_no_encontrado'}             │
│                                                                    │
│   2. port of resolve_active_subscription_for_exit (PL/pgSQL)       │
│      → si mensualidad vigente →                                    │
│        jsonb {cobrar:false, motivo:'mensualidad_vigente'}          │
│                                                                    │
│   3. SELECT … FROM tarifas_sucursal                                │
│      WHERE vigente_desde<=NOW() AND (vig_hasta IS NULL OR >NOW())  │
│        AND estado='activo'                                          │
│      FOR SHARE                       ◄── KD-1 lock pesimista       │
│      → 0 filas → jsonb {error:'tarifa_no_vigente'}    (KD-3)       │
│                                                                    │
│   4. SELECT porcentaje FROM impuestos WHERE nombre='IVA'           │
│      → 0 filas → jsonb {error:'iva_no_configurado'} (KD-IVA)      │
│                                                                    │
│   5. compute jsonb                                                 │
│      tiempo_minutos = EXTRACT(EPOCH FROM (NOW()-fecha_ingreso))/60 │
│      unidad_minutos = CASE tipo  (KD-2)                             │
│          WHEN 'fraccion' THEN 15                                   │
│          WHEN 'hora'     THEN 60                                   │
│          WHEN 'nocturna' THEN 720                                  │
│          ELSE                  1                                   │
│      END                                                           │
│      tiempo_tar_plena = (valor_plena / valor) * unidad_minutos     │
│      IF valor_plena>0 AND tiempo_minutos >= tiempo_tar_plena       │
│        THEN total = valor_plena                                    │
│        ELSE total = valor * CEIL(tiempo_minutos)                   │
│      iva     = ROUND(total * porcentaje, 2)                        │
│      subtotal = ROUND(total - iva, 2)                              │
│      total_out = ROUND(total, 2)                                   │
│      vigente_hasta = NOW() + INTERVAL '15 minutes'                 │
│ RETURN jsonb_build_object(...)                                     │
│ COMMIT;                                                            │
└────────────────────────────────────────────────────────────────────┘
        │
        ▼ JSON response (Cache-Control: no-store)
```

**Annotations.** The function is `STABLE` (KD-IVA AST check enforces this). The lock `FOR SHARE` is held for the whole transaction. The handler reuses `resolve_active_subscription_for_exit` ported to SQL — no HTTP round-trip. Zero side-effects in DB (verified by `test_no_write_in_calcular_cotizacion.py`).

## 4. Key Decisions

### Decision: KD-1 — Pessimistic lock `SELECT … FOR SHARE` on `tarifas_sucursal`

**Choice.** Inside the PL/pgSQL function, after the bi-temporal predicate resolves the row, execute `SELECT … FOR SHARE` on the `tarifas_sucursal` row.

**Context.** Race window between cotizar and HU-F1.7 `POST /operacion/salidas`. Without the lock, a tariff could be closed (`vigente_hasta` set) between the cotización and the cobro, producing inconsistent fiscal data.

**Alternatives considered.**

- `FOR UPDATE` — rejected: more restrictive than needed; would serialize every cotización even when only DELETE/UPDATE on the row is the contention vector.
- Skip-lock (NOWAIT / SKIP LOCKED) — rejected: would yield inconsistent quotation under load (caller could receive a "no tariff" answer while a concurrent transaction is mid-insert of an updated row).
- Python-level lock (asyncio.Lock in handler) — rejected: cannot span the HTTP→PL/pgSQL→F1.7 boundary; weaker than DB-enforced atomicity.

**Rationale.** DB-level lock guarantees transactional atomicity cotización → POST /salidas stronger than any Python-level lock. `FOR SHARE` permits multiple concurrent cotizaciones but blocks DELETE/UPDATE/ALTER on the row until commit. For our `[V]` model where only parameterized admin UPDATEs reach `tarifas_sucursal.vigente_hasta`, there is no real operational impact.

**Forward compatibility.** HU-F1.7 (`POST /operacion/salidas`) will replicate the same lock; this invariant is documented in §6 Cross-HU.

### Decision: KD-2 — `unidad_minutos` resolved via hardcoded `CASE` in PL/pgSQL

**Choice.** Hardcoded `CASE tipo_tarifa.tipo WHEN 'fraccion' THEN 15 WHEN 'hora' THEN 60 WHEN 'nocturna' THEN 720 ELSE 1 END` inside the PL/pgSQL function body.

**Context.** The A-02 formula `tiempo_tar_plena = (valor_plena/valor) * unidad_minutos` requires `unidad_minutos`. `tipo_tarifa.tipo` is a `string` enum (`hora|fraccion|plena|nocturna`); there is no `unidad_minutos` column in the ER (`modelo_datos_er.mmd:128-144`, `models/V/tipo_tarifa.py`).

**Alternatives considered.**

- Add `unidad_minutos` column to `tipo_tarifa` and to a new Alembic migration — rejected: adds a column the rest of the system doesn't read, polluting the ER canonical and forcing an E-5 ([V]) write surface where read-only is sufficient.
- Add a column to `tarifas_sucursal` per-row — rejected: redundancy; the modality is already declared in `tipo_tarifa.tipo`.
- External Python dict — rejected: violates "all pricing logic lives in PL/pgSQL" goal and breaks atomicity.

**Rationale.** Encapsulates the A-02 adaptation in the function, avoiding a collateral ER migration. `tipo_tarifa` with 4 discrete values does not benefit from normalization in V1.

**Trade-off (explicit).** If a new `tipo_tarifa` is added in the future (e.g. `diaria = 1440 min`), the function must be `ALTER FUNCTION ... LANGUAGE plpgsql`. Acceptable; documented as extensibility hook in §9.

### Decision: KD-3 — New typed error `404 tarifa_no_vigente`

**Choice.** When `ingreso` exists and has no associated `salidas`, but no `tarifas_sucursal` row is vigente for `(uuid_sucursal, uuid_tipo_vehiculo)` at `t=NOW()`, return `404 {"error":"tarifa_no_vigente"}`.

**Context.** `exploration.md` identified that the GAP-BE-09 contract did not specify this case. The current 404 `ingreso_no_encontrado` only covers uuid-not-found / already-closed. A new typed error is required to distinguish "the ingreso is fine but the catalog does not cover this combination at this instant".

**Alternatives considered.**

- 422 (semantic invalid) — rejected: the request is well-formed; the *resource* just has no applicable rate at the queried instant. 404 fits the REST semantics ("no representation found for this resource at this time").
- 500 (system error) — rejected: this is an expected business state, not a system failure.
- Merge with `ingreso_no_encontrado` — rejected: callers cannot distinguish "wrong uuid" from "tariff gap"; debugging and metrics become noisy.

**Rationale.** Consistent with the existing `ingreso_no_encontrado` (404) and `iva_no_configurado` (500) pattern. 404 (not 422) because the requested combination has no applicable tariff at the current instant.

**Precedence.** `ingreso_no_encontrado` > `tarifa_no_vigente` > `iva_no_configurado` (see REQ-OPS-024). The function evaluates in that order; the first failure short-circuits.

### Decision: KD-IVA — `impuestos.IVA` seeding out of scope

**Choice.** F1.8 apply phase does **NOT** seed `impuestos.IVA`. Ownership is transferred to HU-F14.2 Parte II. `design.md` declares the seeding as a deployment blocker and documents the exact recipe.

**Context.** All migrations 0001-0021 do not insert any row into `prod.impuestos` (verified via grep: 0 matches). Triggers and schema exist (lines 2357-2366, 266-280), but the row must be seeded at runtime via `POST /catalogos/impuestos`. Until that happens, every cotización returns `500 iva_no_configurado`. This is **expected and testable** — apply does not seed.

**Alternatives considered.**

- Seed a default 19% IVA from F1.8 — rejected: introduces a regulatory assumption (19% Colombia) into a change that should not carry it; ownership dispute with HU-F14.2.
- Read `porcentaje` from a hardcoded constant in the handler — rejected: violates "single source of truth in DB"; breaks the audit trail.
- Skip the SELECT and assume IVA = 0 — rejected: silent tax evasion risk; contractually a `500`.

**Rationale.** Confirmed by user 2026-09-14: apply of F1.8 does not seed. Housekeeping pre-deployment is the responsibility of the operational team executing the seeded recipe. Recipe below.

**Exact seeding recipe (pre-deployment):**

```sql
INSERT INTO prod.impuestos (
  uuid, nombre, porcentaje, vigente_desde, vigente_hasta, estado, created_at
) VALUES (
  gen_random_uuid(), 'IVA', 0.19, NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
);
```

**Alternative via API:** `POST /api/v1/catalogos/impuestos` with JSON body `{nombre:'IVA', porcentaje:0.19, vigente_desde: now(UTC)}`.

**Production verification (run before enabling F1.8):**

```sql
SELECT 1 FROM prod.impuestos
 WHERE nombre='IVA' AND estado='activo'
   AND NOW() BETWEEN vigente_desde AND COALESCE(vigente_hasta, NOW() + interval '1 day');
-- must return 1 row.
```

**Housekeeping.** Separate task `chore(seed): sembrar impuestos.IVA pendiente — HU-F1.8 bloqueada hasta KYC` outside this change.

## 5. Data Flow (sequence diagram)

```
operador/admin   FastAPI router    PL/pgSQL             prod.*
   │                  │                │                    │
   │ GET /cotizar?uuid_ingreso=X      │                    │
   ├─────────────────►│                │                    │
   │                  │ SELECT prod.calcular_cotizacion(:u) │
   │                  │────────────────────────────────►    │
   │                  │                │                    │
   │                  │   ┌─ step 1: SELECT ingreso ────┐   │
   │                  │   │ NOT EXISTS salidas         │   │
   │                  │   └────────────────────────────┘   │
   │                  │                │                    │
   │                  │   ┌─ step 2: subscripcion check ─┐  │
   │                  │   │ (port resolve_active_…)      │  │
   │                  │   └────────────────────────────┘   │
   │                  │                │                    │
   │                  │   ┌─ step 3: SELECT tarifa ──────┐  │
   │                  │   │  FOR SHARE   (KD-1)          ├──►tarifas_sucursal
   │                  │   └────────────────────────────┘   │
   │                  │                │                    │
   │                  │   ┌─ step 4: SELECT impuestos ───┐  │
   │                  │   │ WHERE nombre='IVA'           ├──►impuestos
   │                  │   └────────────────────────────┘   │
   │                  │                │                    │
   │                  │   ┌─ step 5: compute jsonb ──────┐  │
   │                  │   │ subtotal, iva, total         │  │
   │                  │   │ tiempo_minutos               │  │
   │                  │   │ vigente_hasta = NOW()+15min  │  │
   │                  │   └────────────────────────────┘   │
   │                  │                │                    │
   │                  │  jsonb  ◄──────│                    │
   │                  │  map to HTTPException | 200        │
   │ ◄──── 200 OK ────┤  (headers: Cache-Control: no-store)
```

## 6. Cross-HU Interaction

| HU | State | Interaction |
|---|---|---|
| **HU-F1.4** | merged (`de4d2fc`) | Reusable bi-temporal predicate. The PL/pgSQL replicates the formula manually for atomicity. **If F1.4's predicate changes, the SQL constant here must be synchronized manually.** Risk of drift documented; CI cross-test compares the resolved set between the Python helper `repo/tarifas_vigencia.py` and a fixture invocation of `calcular_cotizacion`. |
| **HU-F1.7** | future (`POST /operacion/salidas`) | Will consume the cotización via `vigente_hasta` validation (`cotizacion_expirada` 410). **Decision: F1.7 will also invoke `calcular_cotizacion(...)` via PL/pgSQL (same name), NOT via HTTP, to avoid the round-trip and keep lock continuity.** Will replicate the `FOR SHARE` lock on `tarifas_sucursal` (KD-1 invariant). |
| **HU-F1.9** | future (facturación) | Will read the cotización result as input for the accounting entry. Discriminator `cobrar:false, motivo:'mensualidad_vigente'` is the no-fiscal-row path; `cobrar:true` is the full-breakdown path. |
| **HU-F14.2 Parte II** | future | Owner of `impuestos.IVA` seeding (KD-IVA). Deployment blocker for F1.8 in any environment where IVA has not been seeded. |

## 7. Threat Matrix (CRÍTICO)

| # | Threat | Mitigation | KD |
|---|---|---|---|
| T1 | Cotización serves tariff data that closes between `cotizar` and `POST /salidas` | `FOR SHARE` on `tarifas_sucursal` inside the transaction | KD-1 |
| T2 | Non-deterministic monetary rounding drift | `Numeric(18,4)` storage + `ROUND(...,2)` in jsonb output + `Decimal` in Python | R2 |
| T3 | Clandestine INSERT in PL/pgSQL breaks idempotencia | AST check `test_no_write_in_calcular_cotizacion.py` rejects `INSERT|UPDATE|DELETE` in body | R7 |
| T4 | Reverse proxy serves cotización from 1 hour ago | `Cache-Control: no-store` on handler response | R8 |
| T5 | Ingreso closed but operator tries to cotizar | 404 `ingreso_no_encontrado` via `NOT EXISTS salidas` join | REQ-OPS-024 |
| T6 | Combination has no vigente tarifa at `t=NOW()` | 404 `tarifa_no_vigente` (KD-3) | KD-3 |
| T7 | No `impuestos.IVA` row seeded | 500 `iva_no_configurado` (KD-IVA); pre-deployment recipe documented | KD-IVA |
| T8 | Drift tz in `fecha_ingreso` | UTC-naive predicate in PL/pgSQL; HU-F1.6 normalizes entrada; tested with tz-aware fixtures | R6 |

## 8. Migration Strategy

Alembic migration `0022_create_calcular_cotizacion.py`. Structure:

```python
def upgrade() -> None:
    op.execute("""
    CREATE OR REPLACE FUNCTION prod.calcular_cotizacion(p_uuid_ingreso uuid)
    RETURNS jsonb
    LANGUAGE plpgsql
    STABLE  -- KD-IVA: AST check enforces this declaration
    AS $$
    DECLARE
        v_ingreso record;
        v_tarifa record;
        v_impuesto record;
        v_subscripcion record;
        v_total numeric(18,4);
        v_iva numeric(18,4);
        v_subtotal numeric(18,4);
        v_tiempo interval;
        v_tiempo_minutos numeric;
        v_valor_plena numeric;
        v_unidad_minutos int;
        v_vigente_hasta timestamptz;
    BEGIN
        -- 1. Ingreso existe y no cerrado
        SELECT i.uuid_sucursal, i.uuid_tipo_vehiculo, i.placa, i.fecha_ingreso,
               EXISTS(SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso = i.uuid AND s.estado <> 'anulada') AS tiene_salida
          INTO v_ingreso
          FROM prod.ingreso i
         WHERE i.uuid = p_uuid_ingreso AND i.vigente_hasta IS NULL;
        IF NOT FOUND OR v_ingreso.tiene_salida THEN
            RETURN jsonb_build_object('error','ingreso_no_encontrado');
        END IF;

        -- 2. Mensualidad vigente (KD portado de operacion.py:215-277)
        -- SELECT INTO v_subscripcion ... (port resolve_active_subscription_for_exit)
        IF FOUND THEN
            RETURN jsonb_build_object('cobrar', false, 'motivo','mensualidad_vigente');
        END IF;

        -- 3. Tarifa vigente con lock FOR SHARE (KD-1)
        SELECT t.valor, t.valor_plena, t.uuid_tipo_tarifa, tt.tipo
          INTO v_tarifa
          FROM prod.tarifas_sucursal t
          JOIN prod.tipo_tarifa tt ON tt.uuid = t.uuid_tipo_tarifa
         WHERE t.uuid_sucursal = v_ingreso.uuid_sucursal
           AND t.uuid_tipo_vehiculo = v_ingreso.uuid_tipo_vehiculo
           AND t.estado='activo'
           AND t.vigente_desde <= NOW()
           AND (t.vigente_hasta IS NULL OR t.vigente_hasta > NOW())
         LIMIT 1
           FOR SHARE;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('error','tarifa_no_vigente');
        END IF;

        -- 4. Impuesto IVA vigente (KD-IVA)
        SELECT porcentaje INTO v_impuesto
          FROM prod.impuestos
         WHERE nombre='IVA' AND estado='activo'
           AND vigente_desde <= NOW() AND (vigente_hasta IS NULL OR vigente_hasta > NOW())
         ORDER BY vigente_desde DESC LIMIT 1;
        IF NOT FOUND THEN
            RETURN jsonb_build_object('error','iva_no_configurado');
        END IF;

        -- 5. Compute (KD-2 hardcoded CASE)
        v_tiempo := NOW() - v_ingreso.fecha_ingreso;
        v_tiempo_minutos := EXTRACT(EPOCH FROM v_tiempo) / 60.0;

        v_unidad_minutos := CASE v_tarifa.tipo
            WHEN 'fraccion' THEN 15
            WHEN 'hora' THEN 60
            WHEN 'nocturna' THEN 720
            ELSE 1
        END;

        IF v_tarifa.valor_plena > 0 THEN
            v_valor_plena := (v_tarifa.valor_plena / v_tarifa.valor) * v_unidad_minutos;
            IF v_tiempo_minutos >= v_valor_plena THEN
                v_total := v_tarifa.valor_plena;
            ELSE
                v_total := v_tarifa.valor * CEIL(v_tiempo_minutos);
            END IF;
        ELSE
            v_total := v_tarifa.valor * CEIL(v_tiempo_minutos);
        END IF;

        v_iva := ROUND(v_total * v_impuesto.porcentaje, 2);
        v_subtotal := ROUND(v_total - v_iva, 2);
        v_vigente_hasta := NOW() + interval '15 minutes';

        RETURN jsonb_build_object(
            'cobrar', true,
            'subtotal', v_subtotal,
            'iva', v_iva,
            'total', v_total,
            'tiempo_minutos', v_tiempo_minutos,
            'tarifa_uuid', v_tarifa.uuid_tipo_tarifa,
            'vigente_hasta', v_vigente_hasta
        );
    END;
    $$;

    GRANT EXECUTE ON FUNCTION prod.calcular_cotizacion(uuid) TO parkos_app;
    """)

def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS prod.calcular_cotizacion(uuid);")
```

The full PL/pgSQL is the reference for `apply`; this `design.md` is the source of truth for the architectural decisions.

## 9. Extensibility Hooks (forward-looking)

- **KD-2 CASE.** If a new `tipo_tarifa` (e.g. `diaria = 1440 min`) is added in the future, the function requires `ALTER FUNCTION ... LANGUAGE plpgsql` to update the `CASE` clause. Documented as housekeeping pre-Fase-2.
- **KD-3 error code pattern.** The pattern `{"error":"code"}` is generalized; if more detail is required, add a wrapper object (e.g. `{"error":"tarifa_no_vigente", "combinacion":{...}}`) without breaking the discriminator.
- **Lock scope.** If HU-F1.7 needs to also lock `vehiculos` (currently no), extend KD-1.
- **A-02 formula source.** If `unidad_minutos` becomes a first-class column in `tipo_tarifa` (post-Fase-2), KD-2 collapses to `v_unidad_minutos := tipo_tarifa.unidad_minutos`. Migration path: add column, backfill from CASE, replace CASE with column reference.

## 10. Rollback Plan

- `alembic downgrade -1` reverts the migration; the PL/pgSQL function disappears.
- If the function is active in production and an immediate rollback is required: `DROP FUNCTION prod.calcular_cotizacion(uuid);` (manual).
- **Risk.** The FastAPI handler remains registered after rollback; on receiving a request it will return 500. Clients must be prepared to retry with circuit breaker behavior (out of F1.8 scope).
- No data is mutated by the function (AST check enforces), so rollback is non-destructive.

## 11. Open Questions

**None.** The 4 KD (KD-1 lock, KD-2 CASE, KD-3 error 404, KD-IVA seeding) are confirmed by the user 2026-09-14. The exploration documented the seeding of `impuestos.IVA` as a deployment blocker; `sdd-apply` for this change does **NOT** seed by contract (KD-IVA). Seeding is a pre-deployment operational prerequisite, with the exact recipe documented in §4 KD-IVA.
