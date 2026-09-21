# `GET /api/v1/operacion/mi-turno` (HU-F12.1)

Read-only per-turn KPI aggregate for the operator's active cash session
(``prod.sesion``). Backs the `<MiTurnoPanel />` widget on the kiosk
dashboard — REQ-OPS-184..187.

## Request

| Field | Type | Required | Source |
|-------|------|----------|--------|
| `uuid_sesion` | UUID (query string) | yes | `useSesionActiva().sesion.uuid` (F3.3 substrate) |
| Bearer token | `Authorization: Bearer <jwt>` | yes | `operador-` or `admin-` issuer |

```bash
curl -sS \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/json" \
  "http://localhost:8000/api/v1/operacion/mi-turno?uuid_sesion=${UUID_SESION}"
```

## Response (200)

```jsonc
{
  "uuid_sesion": "00000000-0000-0000-0000-000000000001",
  "uuid_sucursal": "00000000-0000-0000-0000-000000000002",
  "timestamp_calculo": "2026-09-21T08:00:00",
  "ingresos_count": 3,
  "salidas_count": 2,
  "total_cobrado_efectivo_cop": 50000,
  "total_cobrado_datafono_cop": 30000
}
```

Response headers:

| Header | Value | Rationale |
|--------|-------|-----------|
| `Cache-Control` | `no-store` | Per-turn metrics change every minute; an HTTP cache that serves a stale quote would silently surface out-of-date KPIs (R-A6 mitigation, F1.3 / F1.5 / F1.8 precedent). |

## Error responses

| Status | `detail.error` | Cause |
|--------|----------------|-------|
| 403 | `sesion_cross_branch_forbidden` | Operator JWT pinned to branch A, request `uuid_sesion` whose `Sesion.uuid_sucursal == B`. The handler resolves `Sesion.uuid_sucursal` server-side (REQ-OPS-185, DA-F12.1-2) — any cross-branch attempt is rejected before the SUM runs. |
| 404 | `sesion_not_found` | `uuid_sesion` does not exist in `prod.sesion`. |
| 401 | (auth chain) | Bearer token missing / invalid / expired (handled by `requires_issuer("operador-", "admin-")` dep). |

All error responses also carry `Cache-Control: no-store`.

## Aggregation contract (REQ-OPS-184 + REQ-OPS-186)

* `ingresos_count` and `salidas_count` derive from a **Sesion open-window
  temporal JOIN** over `prod.ingreso` and `prod.salidas`. The window is
  `[sesion.timestamp_apertura, sesion.timestamp_cierre]` (open session
  uses the NULL guard `timestamp_cierre IS NULL`). The branch scope is
  `Sesion.uuid_sucursal`, propagated into the FILTER — no `uuid_sesion`
  column is added to those tables (would violate ER.mmd 4FN canon on
  `[L-E]` / `[A]`, R-F12.1-1).
* `total_cobrado_efectivo_cop` = `SUM(prod.factura_pagos.valor)`
  filtered by `medio_pago == 'efectivo' AND tipo_movimiento == 'pago'`.
* `total_cobrado_datafono_cop` = same SUM, filtered by
  `medio_pago IN ('tarjeta', 'datafono')`.
* Both SUMs use the canonical F1.13 helper
  ``repo.arqueo._sum_factura_pagos_by_medio_pago`` verbatim (R-F12.1-2).
* Zero-state (no events in window) returns 200 with all count/decimal
  fields equal to `0` — **never 404** (REQ-OPS-184 S2, DA-F12.1-4).
* `timestamp_calculo` is naive UTC from `repo.session_cycle._now_naive()`
  at request time. FE serializes via ISO 8601 (Zod `z.string()`).

## Drift gate (DA-F12.1-1 / DA-F12.1-9)

The 7-field wire shape is locked on both sides of the boundary:

* BE pytest: `backend/tests/unit/test_mi_turno_schema.py` reads
  `MiTurnoRead.model_fields.keys()` and asserts equality with the
  fixture `EXPECTED_KEYS`.
* FE vitest: `apps/electron-sucursal/src/lib/api/schemas/__tests__/mi-turno.test.ts`
  reads `Object.keys(MiTurnoSchema.shape)` and asserts equality with the
  same fixture.

Adding a field to either side without updating the other breaks CI on
both pyramids — defense in depth against BE / FE drift (F11.1 / F11.2
precedent).

## Polling cadence (FE side)

`useMiTurno` SWR hook polls every `15_000` ms (REQ-OPS-188) with a
`dedupingInterval: 5_000` deduping window. Faster than the F11.x 30s
cadence because turn-scoped metrics change every minute the operator is
on the kiosk — see `R-F12.1-4` mitigation: `prod.sesion` partial unique
index bounds SUM cardinality to one active sesion per operator.

## See also

* `openspec/changes/fase-12-1-mi-turno/specs/spec.md` — REQ-OPS-184..190
* `openspec/changes/fase-12-1-mi-turno/design.md` — AD-1..AD-7
* `openspec/changes/fase-12-1-mi-turno/tasks.md` — C-B1..C-F6 commit plan
* `backend/packages/parkos_core/src/parkos_core/repo/mi_turno.py` —
  aggregator implementation
* `backend/packages/parkos_core/src/parkos_core/app/sql/mi_turno_query.py`
  — pure SQL builder (Sesion open-window temporal JOIN)
* `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py`
  — `MiTurnoRead` Pydantic class