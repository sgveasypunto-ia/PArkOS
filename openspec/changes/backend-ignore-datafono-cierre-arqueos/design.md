# Design: backend-ignore-datafono-cierre-arqueos

> **Phase**: design · **Status**: draft
> Proposal: `proposal.md` · Specs: `specs/operations/spec.md` + `specs/sync-motor/spec.md`

## Architectural Choice

Datafono is visually invisible (FE hardcodes `valor_datafono_reportado: 0` in `ArqueoParcial.tsx:179`, commit `481ca7e5`). Backend still validates, computes, decides, persists, serializes, and emits alerts on it. **Shrink the contract, never delete persistence**: wire input nullable (legacy kiosk compat), output drops datafono fields, helper signatures collapse to effective-only, DB columns preserved forward-only. No migration. Zero DELETE.

## Decisions Cerradas (D1–D5)

| ID | Choice | Rationale |
|---|---|---|
| **D1** | `total_cobrado_datafono_cop` PRESERVED as `Decimal(0)` in `MiTurnoRead` | FE Zod key-set lock + BI/report consumers depend on the key; value is always 0. |
| **D2** | Sync close path passes `valor_final_datafono=None` EXPLICIT at `apply_row.py:300` | Documents intent; survives future positional-arg signatures. |
| **D3** | Drill-down route `diferencia_datafono` in `router.ts:44` PRESERVED | Historical alertas with `valor_diferencia_datafono != 0` must remain resolvable. |
| **D4** | `calcular_esperado_sesion` / `calcular_esperado_cierre_dia` return `-> Decimal` (vs 1-tuple) | 1-tuple is a code smell — second value always ignored. |
| **D5** | `es_descuadre_critico` DROPS datafono params (vs default-`None`) | Default-`None` invites reintroduction; `TypeError` is the right failure mode. |

## Concerns y Secuencia

Concern 0 (repo signatures) MUST land before Concerns 3, 5, 9 (consumers).

### Concern 0 — Repo signature collapse (D4 + D5)
- `repo/arqueo.py:334-435` — `calcular_esperado_sesion` / `calcular_esperado_cierre_dia` → `-> Decimal`; `es_descuadre_critico` drops 2 params.
- `repo/arqueo.py:443-580` — `insertar_arqueo` + `insertar_alerta_descuadre_critico` drop datafono kwargs + dict keys (model column at `models/L_W/alerta.py:62-65` stays nullable — no migration).
- **Caller updates**: `caja_arqueo.py:347-360, 555-558, 382-387`, `repo/arqueo.py:688-690`.
- **Acceptance**: `test_calcular_esperado_sesion_returns_decimal_only`, `test_es_descuadre_critico_drops_datafono_params`, `test_es_descuadre_critico_boundary` green.

### Concern 1 — Schema wire V2 + reads (REQ-OPS-191 + REQ-OPS-192)
- `schemas/caja.py:349-498` — `ArqueoCreateV2.valor_datafono_reportado: Decimal | None = None`; `ArqueoReadForHandler`/`ArqueoResumenItem`/`ArqueoResumenAdminItem` drop datafono fields; `RequiereJustificacionQueryParams.valor_datafono_reportado: Decimal | None = None`.
- `schemas/operacion.py:757, 774` — `MiTurnoRead.total_cobrado_datafono_cop` PRESERVED with default `Decimal(0)` (D1).
- `schemas/workflows.py:347, 374, 392` — `AlertaRead`/`Create`/`Update` drop `valor_diferencia_datafono`.

### Concern 2 — Schema wire cierre
- `api/v1/caja_sesion.py:95-96` already nullable (no edit); `:104-119` `ArqueoDiferenciasResponse` drops 3 datafono fields; `:212` close handler passes `payload.valor_final_datafono` unchanged.

### Concern 3 — Cálculo diferencia + INSERT arqueo (REQ-OPS-091 mod + REQ-OPS-095)
- `api/v1/caja_arqueo.py:355-478` — Step 5 single esperado/diferencia; Step 7 simplified `es_descuadre_critico` call; Step 8 INSERT drops datafono kwargs; Step 10 alerta payload drops datafono keys; Step 13 response drops datafono.
- **Acceptance**: `test_arqueo_insert_excludes_datafono_columns` (open DB TX; `prod.arqueo.valor_datafono_*` and `diferencia_datafono` are `NULL`); `test_datafono_only_descuadre_does_not_emit_alerta` (REQ-OPS-196).

### Concern 4 — Porcentaje de descuadre
- `api/v1/caja_arqueo.py:389-395` — `esperado_total = esperado_efectivo`; `(diferencia_efectivo / esperado_efectivo) * 100`.
- **Acceptance**: `test_descuadre_pct_reflects_effective_only`.

### Concern 5 — `get_arqueo_requiere_justificacion`
- `api/v1/caja_arqueo.py:555-571` — single esperado/diferencia; `requiere_justificacion=diferencia_efectivo != 0`.

### Concern 6 — Alertas (REQ-OPS-196 + D3)
- `api/v1/workflows_alerta.py:444-469` — `descuadrar_alerta` keeps `append_transition` reading `tip_row.valor_diferencia_datafono` (column nullable; historical preserved).
- **New test file**: `apps/electron-sucursal/src/lib/alertas/router.test.ts::test_diferencia_datafono_route_preserved` (file absent today).
- **Acceptance**: `test_historical_datafono_alerta_remain_visible`.

### Concern 7 — Resumen "Mi turno" (REQ-OPS-197 + D1)
- `repo/mi_turno.py:150-170` — drop `await _sum_factura_pagos_by_medio_pago(medios_pago=("tarjeta", "datafono"))`; `total_datafono = Decimal(0)`.
- **Acceptance**: `test_total_cobrado_datafono_cop_is_zero` + static `test_mi_turno_schema.py`.

### Concern 8 — Sync bidireccional (REQ-MOT-001 + REQ-MOT-016 + D2)
- `sync/motor/apply_row.py:294-301` — `valor_final_datafono=None` explicit; open path unchanged.
- **Sub-concern 8a**: `repo/session_cycle.py:333-350` — drop `valor_final_datafono` key from `datos_nuevos` dict when value is `None` (strict REQ-MOT-016 Scenario 2). Affects API + sync close paths.
- **Acceptance**: `test_session_cycle_close_passes_datafono_none`, `test_session_cycle_open_passes_datafono_through`, `test_session_cycle_close_persisted_column_is_default`, `test_session_cycle_close_datos_nuevos_omits_datafono`, `test_chain_unaffected_by_datafono_drop`.

### Concern 9 — Resumen GET projections (REQ-OPS-097)
- `repo/arqueo.py:688-757, 948-1036` — drop datafono dict keys (`construir_resumen_sesion`, `obtener_cierre_dia_del_dia`, `resumen_admin_del_dia`).
- `api/v1/caja_arqueo.py:735-748` (`_row_to_admin_item`) — drop `esperado_datafono`.

## Composition (Threading)

9 endpoints (POST arqueo, GET requiere-justificacion, GET resumen, GET admin resumen, PUT cerrar-sesion, GET arqueos/{uuid}/diferencias, GET mi-turno, PUT alertas/{uuid}/descuadrar, POST /sync/events close) — all effective-only at the response side; inputs accept nullable datafono (legacy kiosk compat).

## Files Touched

**Modified (BE)**: `schemas/caja.py:349-498`, `schemas/operacion.py:746-774`, `schemas/workflows.py:328-395`, `api/v1/caja_arqueo.py:225-748`, `api/v1/caja_sesion.py:104-271`, `api/v1/workflows_alerta.py:444-469`, `repo/arqueo.py:334-580, 688-757, 948-1036`, `repo/mi_turno.py:150-170`, `repo/session_cycle.py:333-350`, `sync/motor/apply_row.py:294-301`.

**Created**: `apps/electron-sucursal/src/lib/alertas/router.test.ts`. **Modified (tests)**: `tests/unit/test_arqueo_repo.py`, `tests/unit/test_arqueo_schemas.py`, `tests/integration/test_caja_arqueo.py`, `tests/integration/test_caja_sesion.py`, `tests/integration/test_caja_cierre.py`, `tests/integration/test_mi_turno.py`, `tests/integration/test_sync_apply_row.py`, `tests/integration/test_sync_chain.py`. **Not touched**: `models/`, `migrations/`, FE (except new test).

## Compliance & Risk

AUDIT-FIRST 3 layers (ORM/Pydantic/logic); no DELETE (`REVOKE` + triggers intact); no migration (datafono columns already nullable; `check_schema_match.py` h stays green); C/Q/U (no DELETE endpoint); hash chain safe; DIAN retention (5-year); forward-only. Risks: (1) external clients reading removed response fields — mitigation FE no longer reads them + release notes; (2) pre-existing alertas preserved by D3 + no-DELETE; (3) `prod.sesion.valor_final_datafono` stays in DB; handler passes `None`, helper omits key from `datos_nuevos`.

## Plan de Aplicación

Branch `fix/backend-datafono-ignored` from `dev`. 10 commits (Concern 0 → 1 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 2). ~600 LOC prod + ~400 LOC tests — single PR. Merge `git merge --no-ff fix/backend-datafono-ignored` to `dev`. Author `Parkos Dev <dev@parkos.local>`. Pre-merge: ruff + pytest + `check_schema_match.py` (h).

## References

Proposal: `proposal.md` (392 lines). Specs: `specs/operations/spec.md` (14 REQ-OPS), `specs/sync-motor/spec.md` (2 REQ-MOT). AGENTS.md §1/§2/§3/§21. FE commits pre-existentes: `d6abd36f`, `c6784945`, `7c603b35`, `481ca7e5`.