# Tasks: HU-F8.1 — Pago bloquea salida (atomic combined endpoint)

**Change**: `hu-f8-1-pago-bloquea-salida` | **Approach**: Approach (a), user-ratified 2026-09-23.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1300-1800 (4 PRs chained) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR1 BE schema (~250 LOC) → PR2 BE endpoint+tests (~450 LOC) → PR3 FE removal (~-260 LOC) → PR4 FE rewire+AlertDialog (~450 LOC) |
| Delivery strategy | auto-chain |
| Chain strategy | pending — orchestrator asks user |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Pre-mint UUID helper + `crear_factura_evento` accepts pre-minted UUID | PR 1 | `pytest backend/tests/unit/test_factura_repo_premint.py -v` | `docker exec parkos-api-sucursal python -m pytest backend/tests/unit/test_factura_repo_premint.py` | Revert PR1 schema+repo; legacy `POST /operacion/salidas` keeps working |
| 2 | Handler `create_salida_con_cobro` 16-step + router + integration tests + AST walker | PR 2 | `pytest backend/tests/integration/test_salida_con_cobro.py backend/tests/static/test_salida_con_cobro_handler_step_order.py -v` | E2E Vite: Login → Ingreso → Salida → Pago via Swagger `/operacion/salida-con-cobro` | Revert PR2 router+handler; legacy endpoint still 410 Gone until re-enable patch |
| 3 | FE removal: delete `useAnularSalidaNoPagada.{ts,test.ts}`, revert `PagoSheet.handleClose`, drop P6/P7 tests | PR 3 | `pnpm vitest run src/features/facturacion/components/PagoSheet.test.tsx --reporter=verbose` | `git diff --stat dev..HEAD -- apps/electron-sucursal/src/features/facturacion/hooks/useAnularSalidaNoPagada.*` shows -260 LOC | `git revert PR3` restores legacy hooks; FE reverts to old cancel-on-close behavior |
| 4 | FE rewire: `SalidaFlow` no `useRegistrarSalida`, `PagoSheet` POSTs `/salida-con-cobro`, `SalidaMensualidad` AlertDialog 2s + alerta row, nullable `uuid_salida` | PR 4 | `pnpm vitest run src/features/operacion/components/SalidaFlow.test.tsx src/features/operacion/components/SalidaMensualidad.test.tsx --reporter=verbose` | Manual Chrome DevTools MCP: Login → Ingreso → Confirmar Salida → PagoSheet opens → Efectivo → CU-15S prints | `git revert PR4`; FE falls back to `useRegistrarSalida` + `useAnularSalidaNoPagada` (broken but functional) |

## Phase 1: PR1 BE schema + repo pre-mint (~5 tasks)

- [ ] 1.1 RED: write `backend/tests/unit/test_factura_repo_premint.py::test_crear_factura_evento_accepts_preminted_uuid` (failing)
- [ ] 1.2 GREEN: refactor `backend/.../repo/factura.py::crear_factura_evento` to accept `uuid_pre_minted: UUID | None`
- [ ] 1.3 RED: write `backend/tests/unit/test_salida_repo_premint.py::test_salida_repo_premint_helper`
- [ ] 1.4 GREEN: add `backend/.../repo/salida.py::pre_mint_salida_uuid()` helper
- [ ] 1.5 REFACTOR: extract `_uuid7()` to `backend/.../lib/uuids.py`; update both repos

## Phase 2: PR2 BE endpoint combined (~15 tasks)

- [ ] 2.1 RED: `backend/tests/static/test_salida_con_cobro_handler_step_order.py` AST walker asserts 16-step order (KD-3 → V1 → V5 → V4 → KD-FORZADO-01 → V1+V2 → V3 → V6 → V8 → pre-mint → KD-FACT-01 → INSERTs → alerta same-TX → V9 → commit)
- [ ] 2.2 RED: `backend/tests/static/test_salida_con_cobro_single_commit.py` asserts exactly ONE `await session.commit()`
- [ ] 2.3 RED: `backend/tests/static/test_salida_con_cobro_no_write_after_factura_pagos.py` asserts `factura_pagos INSERT` precedes `salidas INSERT`
- [ ] 2.4 RED: `backend/tests/integration/test_salida_con_cobro.py::test_happy_path_rotacion_201`
- [ ] 2.5 RED: `test_happy_path_mensualidad_with_alerta_row`
- [ ] 2.6 RED: `test_legacy_salidas_returns_410`
- [ ] 2.7 RED: `test_mensualidad_without_confirmacion_returns_409`
- [ ] 2.8 RED: `test_rotacion_with_subscription_returns_409_mensualidad_no_aplica`
- [ ] 2.9 RED: `test_atomic_rollback_on_fk_violation` (zero rows in 5 tables)
- [ ] 2.10 RED: `test_idempotency_key_replay_returns_cached_201`
- [ ] 2.11 GREEN: `backend/.../schemas/operacion.py::SalidaConCobroCreate` (new Pydantic)
- [ ] 2.12 GREEN: `backend/.../services/salida_con_cobro_service.py::create_salida_con_cobro` (16-step handler)
- [ ] 2.13 GREEN: register router `POST /api/v1/operacion/salida-con-cobro` in `backend/.../api/v1/operacion.py`
- [ ] 2.14 GREEN: update legacy `POST /api/v1/operacion/salidas` rotación path → 410 Gone (preserve mensualidad branch via `confirmado_operador_explicit`)
- [ ] 2.15 REFACTOR: extract common validation helpers; document KD-S7 lock pattern in module docstring

## Phase 3: PR3 FE removal (~7 tasks)

- [ ] 3.1 Delete `apps/electron-sucursal/src/features/facturacion/hooks/useAnularSalidaNoPagada.ts`
- [ ] 3.2 Delete `apps/electron-sucursal/src/features/facturacion/hooks/useAnularSalidaNoPagada.test.ts`
- [ ] 3.3 Update `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx::handleClose` to drop annulment trigger
- [ ] 3.4 Update `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.test.tsx` to remove P6/P7 scenarios
- [ ] 3.5 RED: write `PagoSheet.test.tsx::test_handleClose_does_not_call_anular`
- [ ] 3.6 GREEN: refactor `PagoSheet.handleClose` to just close the drawer (no side-effect)
- [ ] 3.7 REFACTOR: clean unused imports (`ParkosHttpError`, `buildIdempotencyKey`)

## Phase 4: PR4 FE rewire (~13 tasks)

- [ ] 4.1 RED: `SalidaFlow.test.tsx::test_confirmar_does_not_call_registrar_salida`
- [ ] 4.2 GREEN: refactor `SalidaFlow.tsx::handleConfirmar` to open `PagoSheet` directly
- [ ] 4.3 RED: `PagoSheet.test.tsx::test_submit_calls_salida_con_cobro_endpoint`
- [ ] 4.4 GREEN: refactor `PagoSheet.tsx::handleSubmit` to call `POST /api/v1/operacion/salida-con-cobro`
- [ ] 4.5 Update `apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts` (+`PostSalidaConCobroPayload`)
- [ ] 4.6 RED: `SalidaMensualidad.test.tsx::test_alertdialog_hold_to_confirm_2s`
- [ ] 4.7 GREEN: add `SalidaMensualidad.tsx::ConfirmDialog` (shadcn `<AlertDialog>` + 2s hold)
- [ ] 4.8 GREEN: refactor `SalidaMensualidad.tsx::handleConfirmar` to require AlertDialog confirmation then `POST /operacion/salida-con-cobro` with `mensualidad=true & confirmado_operador_explicit=true`
- [ ] 4.9 Update `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts::PagoContext` to make `uuid_salida` nullable
- [ ] 4.10 RED: `dashboardDrawerStore.test.ts::test_pago_context_uuid_salida_can_be_null`
- [ ] 4.11 GREEN: update store types
- [ ] 4.12 E2E: `apps/electron-sucursal/e2e/operacion/salida-con-cobro-rotacion.spec.ts` (login → ingreso → confirmar salida → pago efectivo → 201 → CU-15S)
- [ ] 4.13 E2E: `apps/electron-sucursal/e2e/operacion/salida-con-cobro-mensualidad.spec.ts` (login → ingreso mensualidad → confirmar → AlertDialog 2s hold → 201 → alerta row visible)
