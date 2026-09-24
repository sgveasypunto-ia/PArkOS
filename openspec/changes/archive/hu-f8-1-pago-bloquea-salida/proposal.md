# Proposal: HU-F8.1 — Pago bloquea salida (opción A, ambos flujos)

**Change**: `hu-f8-1-pago-bloquea-salida`
**Date**: 2026-09-23
**Inputs**: `exploration.md` + Engram `#2051, #2052, #1894, #1916` + `plan.md:438, 805/1706, 898` + `modelo_datos_er.mmd:622-643, 762-778`

## Intent

`prod.salidas` is INSERTed **before** pago today (Step 8 of `create_salida` at `api/v1/operacion.py:619`). The operator must close the pago drawer so `useAnularSalidaNoPagada` auto-annuls. If forgotten, the record stays UI-inferred `PENDIENTE_PAGO` forever and cupo is gone per DEC-SUC-23. User: *"hasta que no se cobre y se genere factura no se debe cerrar el registro de parqueo"*.

## Scope

**In** — New `POST /operacion/salida-con-cobro` (atomic 16-step, single `session.commit()`); new `POST /operacion/salida-mensualidad` (F1.7 chain + `confirmado_operador_explicit: bool`); `SalidaCreateForzado` gains `uuid_factura: UUID | None`; `crear_factura_evento` accepts pre-minted UUID; shadcn `<AlertDialog>` + 2s hold-to-confirm for mensualidad + `prod.alerta.tipo_alerta='confirmacion_explicit_mensualidad'` (new catalog value); delete `useAnularSalidaNoPagada.{ts,test.ts}` + revert `PagoSheet.handleClose` lines 130-208 of `fix/hu-f8-1-anular-salida-no-pagada` + drop P6/P7 tests; old `POST /operacion/salidas` → `410 Gone`.

**Out** — DIAN `envio_dian`; plan↔ER reconciliation of `plan.md:898`.

## Capabilities

**New** — `salida-con-cobro`: atomic salida+factura+pago (rotación) and mensualidad-with-explicit-confirmation.

**Modified** — `operations`: REQ-OPS-042..052 RE-DELTed — Step 8 INSERT of `prod.salidas` moves *after* pago commit; `tipo_salida`, alerts, and `one_exit_per_ingreso` index preserved.

## Approach

**Backend atómico** (Approach (a), user-ratified). Handler `create_salida_con_cobro`:

- **Chain**: KD-3 → V1 → tenant → V2-V5 (verbatim).
- **Cotización**: F1.8 `calcular_cotizacion` — `cobrar:true`→rotación, `cobrar:false`→409 `mensualidad_no_aplica`.
- **Lock**: KD-S7 `SELECT ... FOR SHARE` on `tarifas_sucursal` covers whole TX.
- **FK**: pre-mint `salidas.uuid` + `facturas.uuid` (bidirectional, no UPDATE — `salidas` is `[A]` per DEC-SAL-01).
- **Writes**: INSERT `prod.salidas(uuid_factura=pre-mint)` → `prod.facturas(uuid_salida=pre-mint)` → `factura_detalle` (N) → `factura_impuestos` → `factura_pagos`.
- **Commit**: single `await session.commit()`; MV refresh post-commit (try/log/continue).
- **Response**: `{uuid_factura, uuid_salida, numero_recibo, items, total, cotizacion_snapshot}`.

**Mensualidad**: F1.7 handler accepts `confirmado_operador_explicit`; FE wraps Confirmar in AlertDialog with 2s hold; on submit logs `prod.alerta.tipo_alerta='confirmacion_explicit_mensualidad'` and POSTs salida.

## Affected Areas

| Area | Impact |
|---|---|
| `backend/.../api/v1/operacion.py` | Modified — combined + mensualidad handlers; old `create_salida` → 410 Gone. |
| `backend/.../repo/salida.py::crear_salida_evento` | Modified — `uuid_factura: UUID \| None`. |
| `backend/.../repo/factura.py::crear_factura_evento` | Modified — pre-minted UUID. |
| `backend/.../schemas/operacion.py::SalidaCreateForzado` | Modified — `confirmado_operador_explicit: bool = False`. |
| `backend/tests/static/test_salida_handler_step_order.py` | Replaced by `test_salida_con_cobro_handler_step_order.py` (16 steps). |
| `apps/electron-sucursal/.../SalidaFlow.tsx:109-156` | Drop `trigger()` for rotación. |
| `apps/electron-sucursal/.../SalidaMensualidad.tsx:102-132` | AlertDialog + 2s hold. |
| `apps/electron-sucursal/.../PagoSheet.tsx:118-313` | Revert `handleClose` anular; call new endpoint. |
| `apps/electron-sucursal/.../useAnularSalidaNoPagada.{ts,test.ts}` | Removed. |
| `apps/electron-sucursal/.../dashboardDrawerStore.ts:78-82` | `PagoContext.uuid_salida` nullable. |
| `openspec/specs/operations/spec.md` (REQ-OPS-042..052) | RE-DELTed. |
| `openspec/specs/salida-con-cobro/spec.md` | New full spec. |

## Risks

| Risk | Lik | Mitigation |
|---|---|---|
| AST test churn breaks 12-step + no-write invariants | Med | New 16-step test; legacy endpoint stays 410 Gone. |
| `crear_factura_evento` refactor for pre-mint UUID | Med | Surgical refactor + unit tests; preserves auto-gen. |
| 1300-1800 LOC > 800 per-HU budget | High | 4 chained PRs (user-defined): PR1 schema+repo ~400, PR2 endpoint+tests ~400, PR3 FE removal ~300, PR4 FE rewire+modal ~500. No `size:exception`. |
| Lock contention ~80ms→~400ms | Low | Pattern proven in F1.9 + `clientes_venta`. |
| `useAnularSalidaNoPagada` WIP orphan | Low | Clean abandon: `git checkout dev -- <files>` + delete hooks. |

## Rollback Plan

1. Revert `create_salida_con_cobro`; re-enable `create_salida` (drop 410 Gone).
2. `git revert` PR4..PR1 in reverse.
3. Re-apply `fix/hu-f8-1-anular-salida-no-pagada` patch from branch history.
4. `alembic downgrade -1` (no migration expected).
5. Verify: `check_schema_match.py` exits 0; legacy `test_salida_handler_step_order.py` passes.

## Dependencies

None external. Reuses KD-S7 (F1.7), KD-FACT-01 (F1.9), KD-FE-01 (F1.10), `prod.alerta` catalog (F11.2). New catalog value extends `catalogs/alert_types.py` only.

## Success Criteria

- [ ] `POST /operacion/salida-con-cobro` returns 201 in single `session.commit()`; FK bidirectional, no UPDATE on `salidas`.
- [ ] Old `POST /operacion/salidas` returns 410 Gone; legacy suite green.
- [ ] `useAnularSalidaNoPagada.{ts,test.ts}` deleted; `git diff dev` shows zero prod refs; P6/P7 tests removed.
- [ ] Mensualidad: 2s AlertDialog gates `POST /operacion/salida-mensualidad`; `prod.alerta` row per confirmation.
- [ ] `test_salida_con_cobro_handler_step_order.py` documents 16 steps; CI green.
- [ ] Coverage ≥ 80% on `parkos_core/api/v1/operacion.py` + `repo/salida.py` + `repo/factura.py`.
- [ ] 4 chained PRs merged to `dev` without `size:exception`; each ≤ 800 LOC.
