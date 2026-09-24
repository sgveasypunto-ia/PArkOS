# Design: HU-F8.1 — Pago bloquea salida (opción A, ambos flujos)

**Change**: `hu-f8-1-pago-bloquea-salida` | **Approach**: Atomic single-endpoint (Approach (a), user-ratified 2026-09-23)

## Technical Approach

Replace `POST /operacion/salidas` (12-step, INSERTs salida BEFORE cobro) with **`POST /operacion/salida-con-cobro`** — atomic 16-step chain, ONE `await session.commit()`. Pre-mint `salidas.uuid` + `facturas.uuid` (no UPDATE on `[A]`). KD-S7 covers full TX. Mensualidad = branch on `mensualidad=true && confirmado_operador_explicit=true` (audit row). Legacy → `410 Gone`. FE: `PagoSheet` orchestrates; F8.1-b `useAnularSalidaNoPagada` + `PagoSheet.handleClose` annulment deleted.

**Spec drift.** `specs/salida-con-cobro/spec.md:21` says "INSERT `prod.salidas(uuid_factura=pre-mint)`", but `prod.salidas` has NO `uuid_factura` column. FK is `facturas.uuid_salida → salidas.uuid`. PG FKs non-deferrable → INSERT order MUST be `salidas` first. Flag for sdd-archive: update REQ-SCC-001 wording.

## Architecture Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Atomicidad | New `salida-con-cobro` endpoint | Closes operator gap; unifies KD-S7 + KD-FACT-01 |
| 2 | UUID pre-mint | Pre-mint pair; order `salidas`→`facturas`→...→`factura_pagos` | No UPDATE on `[A]`; honors FK direction |
| 3 | Legacy endpoint | `410 Gone` | Forces FE migration; old AST test stays green |
| 4 | Mensualidad branch | Same endpoint + `mensualidad` flag + `confirmado_operador_explicit` | One URL; F1.7 `tipo_salida` derivation intact |
| 5 | Idempotency | Reuse `IdempotencyKeyMiddleware` (F1.6) | SHA-256 hash unchanged; header passthrough wired |
| 6 | Lock continuity | KD-S7 from Step 7 through Step 16 (commit) | F1.9 precedent (4-table write, single commit) |
| 7 | FE inversion | `PagoSheet.submit` calls `salida-con-cobro` | Single round-trip; PagoContext drops `uuid_salida` |

## Data Flow

```
[Operator Cobrar] →<SalidaFlow>→<CotizacionPanel onConfirmar>
  └─ openDrawer('pago', anchorId, {uuid_ingreso, total_cop})
       └─<PagoSheet>→<PagoModal onSubmit>
            └─ POST /api/v1/operacion/salida-con-cobro (Idempotency-Key: sha256)
                  ▼  FastAPI → create_salida_con_cobro
  ┌──────────────────────────────────────────────────────────────┐
  │ 1. KD-3 issuer + no_store                                    │
  │ 2-6. V1 ingreso, tenant, V2 sub, V3 placa, V4 KD-FORZADO     │
  │ 7. V5 cotizar_para_salida  ◀── KD-S7 SELECT FOR SHARE         │
  │ 8. validar_items + IVA + lock_tarifas_sucursal (rotación)    │
  │ 9. cobrar=false && !mensualidad → 409                         │
  │10. PRE-MINT uuid_salida, uuid_factura                         │
  │11. INSERT prod.salidas [A] (uuid=uuid_salida, ...)            │
  │12. INSERT prod.facturas (uuid=uuid_factura, uuid_salida=...)  │
  │13. INSERT prod.factura_detalle (N)                            │
  │14. INSERT prod.factura_impuestos (1, IVA snapshot)            │
  │15. INSERT prod.factura_pagos (1)                              │
  │16a. if mensualidad: INSERT prod.alerta tipo=confirmacion_…     │
  │16b. await session.commit()  ◀── KD-S7 release                 │
  │16c. try/log/continue: refresh_mv_ocupacion_diaria             │
  │16d. response {uuid_factura, uuid_salida, total, ...}          │
  └──────────────────────────────────────────────────────────────┘
                  ▼  201 → PagoSheet: CU-15S print + recibo + navigate
```

## File Changes (4 chained PRs, ≤800 LOC each)

**PR1 BE schema+repo** (~250 LOC): `schemas/operacion.py` (+SalidaConCobroCreate/Read); `repo/factura.py::crear_factura_evento` (pre-mint UUID); `migrations/versions/0042_seed_alert_type_confirmacion_mensualidad.py`.

**PR2 BE endpoint** (~450 LOC): `api/v1/operacion.py` (+create_salida_con_cobro, rotate create_salida → 410); new `tests/static/test_salida_con_cobro_handler_step_order.py`; repoint `test_no_write_after_salida_insert.py`; new `tests/integration/test_salida_con_cobro_atomic.py`.

**PR3 FE removal** (~-260 LOC): DELETE `apps/.../hooks/useAnularSalidaNoPagada.{ts,test.ts}`; revert `PagoSheet.tsx`; drop P6/P7 tests; revert `SalidaPanel.tsx`/`SalidaFlow.tsx`/`DrawerHost.tsx`/`dashboardDrawerStore.ts`.

**PR4 FE rewire** (~450 LOC): `SalidaMensualidad.tsx` (AlertDialog + 2s hold); `useRegistrarPago.ts` (POST → `/operacion/salida-con-cobro`); `salidaApi.ts` (+SalidaConCobroReadSchema).

## Interfaces / Contracts

**`POST /api/v1/operacion/salida-con-cobro`** — rotación + mensualidad.
- Req: `{uuid_ingreso, medio_pago, monto_recibido_cents?, voucher?, items?, cliente?, mensualidad?, confirmado_operador_explicit?}`
- 201: `{uuid_salida, uuid_factura|null, tipo_salida, numero_recibo|null, total_cents|null, cotizacion_snapshot|null}`
- Err: 410 `endpoint_deprecated`, 404 `ingreso_no_encontrado`, 403 `tenant_scope_violation`, 409 (`mensualidad_no_aplica` | `confirmacion_operador_requerida` | `salida_duplicada`), 422, 500 `iva_no_configurado`

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit | `crear_factura_evento` honors pre-mint UUID | pytest |
| Integration | 16-step happy + FK rollback + 410 + 409 + KD-FACT-01 | pytest + testcontainers |
| Static AST | 16-step order + ONE commit; `factura_pagos` precedes `salidas` precedes `commit` | pytest AST |
| FE vitest | `SalidaFlow` no useRegistrarSalida; `PagoSheet.submit` POSTs salida-con-cobro; AlertDialog 2s | vitest + happy-dom |
| E2E | Full rotación + full mensualidad | playwright |

## Threat Matrix

| Boundary | Applicable | Safe behavior | Failure | Planned RED tests |
|---|---|---|---|---|
| Documentation-like paths | N/A — no executable Markdown | — | — | — |
| Git repo selection | N/A — standard gitflow | — | — | — |
| Commit state | N/A — per AGENTS.md | — | — | — |
| Push state | N/A — per AGENTS.md | — | — | — |
| PR commands | N/A — orchestrator handles | — | — | — |
| **HTTP routing** | Applicable | New path accepts `Idempotency-Key`; legacy returns 410 + replacement hint | 5xx → middleware 500; legacy POST MUST NOT fall through | `test_legacy_salidas_returns_410` + `test_salida_con_cobro_rejects_without_idempotency_key` |

## Migration / Rollout

**No Alembic DDL migration.** `prod.salidas` not modified (DEC-SAL-01 append-only). Only `0042_seed_alert_type_confirmacion_mensualidad.py` adds one `prod.alert_types` row (ON CONFLICT). Backwards-incompatible once PR2 lands. Sequence: PR1 → PR2 → PR3 → PR4. 410 Gone IS the rollout switch (revert PR2 to recover).

## Open Questions

- REQ-SCC-001 wording (`salidas(uuid_factura=pre-mint)`) contradicts ER — propose spec update at archive.
- Should `prod.factura_electronica` get `uuid_salida` populated? Out of scope; flag for next change.

### Next Step

Ready for `sdd-tasks`.
