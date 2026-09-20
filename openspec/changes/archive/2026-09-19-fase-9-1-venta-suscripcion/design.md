# Design — HU-F9.1: Venta de suscripción desde caja (wizard 4 pasos)

> **Change**: `fase-9-1-venta-suscripcion` | **Phase**: sdd-design | **HU**: HU-F9.1
> **Source branch**: `dev` (at `a6ff5e3`) | **Target**: `feature/hu-f9-1-venta-suscripcion`
> **LOC forecast**: ~940 (RATIFIED `size:exception` user 2026-09-19)

## 1. Technical Approach

F9.1 is renderer-only. The atomic `POST /api/v1/clientes/venta-suscripcion` (F1.12, `a6ff5e3`) already exposes everything. The wizard is a 4-step state machine (`useState<VentaStepState>`) with per-step Zod that ends at F8.1's `<PagoModal />` for cobro. `useVentaSuscripcion` mirrors F7.2/F8.1 verbatim — `useSWRMutation` + F7.2 `buildIdempotencyKey` SHA-256 + 401 `useAuthStore.clear()` + typed error subclasses for 3 backend 422 codes. A-09 prorrateo is a pure helper mirroring F1.12 `calcular_prorrateo` verbatim so the badge never drifts from `factura_detalle.valor_unitario`.

## 2. Architecture Decisions

| # | Decision | Rationale | Rejected |
|---|---|---|---|
| AD1 | Wizard 4 pasos + per-step Zod `safeParse` | Local errors; matches F7.1/F7.2/F8.1 | Big-form schema at submit |
| AD2 | Embed F8.1 `<PagoModal />` in step 4 | OD-2 ratified; F8.1 owns vueltos/FE/NIT | Custom pago form duplicates F8.1 |
| AD3 | Client-side `calcularMontoProporcional` mirror | Pure, easy unit tests | Server round-trip for badge |
| AD4 | Typed `VentaSuscripcionError` subclasses | Mirrors F7.2 `SalidaDuplicadaError` | String-code discrimination |
| AD5 | `size:exception` RATIFIED for 940 LOC | Wizard integral; F7.1/F8.1 precedents | Chained PRs break PagoModal contract |

## 3. Data Flow

```
operador → <Venta /> (paso 1..4)
 paso1 Zod(cliente)                 → setPaso(2) | inline error
 paso2 Zod(placas 1..2) + FORMATO_AUTO/MOTO
                                     → setPaso(3) | typed inline errors
 paso3 Zod(uuid_tipo_subscripcion)  → setPaso(4)
 paso4 <PagoModal total={mp ?? plan.valor} uuid_ingreso={null} />
        → useVentaSuscripcion.trigger(payload):
            buildIdempotencyKey(SHA-256)
            POST /api/v1/clientes/venta-suscripcion
              201 → navigate('/suscripciones')
              401 → useAuthStore.clear() + 'parkos:auth:cleared'
              422 'suscripcion_duplicada_placa' | 'tipo_vehiculo_incompatible'
                 | 'cantidad_maxima_excedida' → typed → step 2 inline
              409 'idempotency_conflict' → toast
```

## 4. File Changes (~940 LOC)

| File | Action | LOC |
|---|---|---|
| `features/suscripciones/lib/prorrateo.ts` | NEW | 30 |
| `features/suscripciones/lib/prorrateo.test.ts` | NEW | 40 |
| `features/suscripciones/api/ventaSuscripcionApi.ts` | NEW | 70 |
| `features/suscripciones/hooks/useVentaSuscripcion.ts` | NEW | 100 |
| `features/suscripciones/hooks/useVentaSuscripcion.test.ts` | NEW | 150 |
| `features/suscripciones/pages/Venta.tsx` | NEW | 250 |
| `features/suscripciones/pages/Venta.test.tsx` | NEW | 200 |
| `hooks/useSuscripcionesList.ts` | UPDATE −20 | remove dead stub L80–98 |
| `i18n/locales/suscripciones.json` | UPDATE +20 | wizard keys |
| `renderer/App.tsx` | UPDATE +6 | `/suscripciones/venta` route |
| `vitest.config.ts` | UPDATE +9 | 3 thresholds |
| `e2e/suscripcion-venta.spec.ts` | NEW | 80 |
| **Total** | | **~935** |

## 5. Interfaces / Contracts

```typescript
// prorrateo.ts (pure)
export interface PlanProporcionalInput { valor: number; duracion_dias: number; }
export function calcularMontoProporcional(plan: PlanProporcionalInput, fecha: Date): number | null;
// null when fecha.day <= 15 (A-09)

// useVentaSuscripcion.ts
export interface VentaSuscripcionInput {
  cliente: { nit: string; nombre: string; email?: string | null };
  placas: string[];                          // 1..2
  uuid_tipo_subscripcion: string;
  fecha_inicio_cobertura: string;
  cobrar_ahora: boolean;
  medio_pago?: 'efectivo' | 'datafono';
  emitir_factura_electronica?: boolean;
}
export interface VentaSuscripcionRead {
  uuid_subscripcion: string;
  uuid_cliente: string;
  uuid_vehiculos: string[];
  uuid_factura: string | null;
  monto_prorrateado: number | null;
}
export class VentaSuscripcionDuplicatePlateError extends Error {
  public readonly status = 422; public readonly placa: string;
}
export class VentaSuscripcionTipoIncompatibleError extends Error {
  public readonly status = 422; public readonly tipos_encontrados: string[];
}
export class VentaSuscripcionCantidadMaximaError extends Error {
  public readonly status = 422; public readonly max: number;
}

// Venta.tsx state
export interface VentaStepState {
  paso: 1 | 2 | 3 | 4;
  cliente?: VentaSuscripcionInput['cliente'];
  placas?: string[];
  uuid_tipo_subscripcion?: string;
  fecha_inicio_cobertura?: string;
  monto_proporcional?: number | null;
}

// step 4 composition
<PagoModal uuid_ingreso={null}
           total_cop={mp ?? plan.valor}
           onSubmit={async (v) => { await trigger(build(v)); navigate('/suscripciones'); }} />
```

## 6. Testing Strategy

| Layer | File | # | Scenarios |
|---|---|---|---|
| Unit | `prorrateo.test.ts` | 4 | day≤15→null; day>15; `valor=30000,dur=30,day=19`→11000; day=30→1000 |
| Hook | `useVentaSuscripcion.test.ts` | 4 | 201→parsed; 422 dup-placa; 422 tipo-incompatible; 401→clear+event |
| Component | `Venta.test.tsx` | 7 | mount→paso1; step1→paso2; NIT corto→inline; placa dup→typed; step3→paso4; prorrateo badge day=20; confirm→trigger |
| e2e | `suscripcion-venta.spec.ts` | 4 | cliente nuevo (1 TX); cliente existente; mixed tipos→422; placa vigente→422 |
| Coverage | vitest.config.ts | 3 | prorrateo 95/95/90; hook 90/90/85; page 80/80/75 |
| Drift guard | shell | 1 | `useVentaSuscripcion` in `useSuscripcionesList.ts` → 0 matches |

Total: 19 tests + 3 thresholds + 1 drift guard.

## 7. Threat Matrix

N/A — renderer-only; data-layer threats owned by F1.12 (KD-VENTA-01 single-commit + XR5 5-layer defense). Threat surface purely UX. See proposal §6 R1..R7.

## 8. Migration

None — F9.1 ships ZERO migration files.

## 9. Open Questions

| # | Decision | Status |
|---|---|---|
| OD-1 | Cliente existente NIT auto-fill en step 1 | **RATIFIED YES** (proposal §7) |
| OD-2 | Reuse F8.1 `<PagoModal />` en step 4 | **RATIFIED YES** (proposal §7) |

## 10. Review Workload Forecast

| Metric | Value | Threshold | Verdict |
|---|---|---|---|
| Forecast LOC | ~935 | 800/PR | EXCEEDS — `size:exception` RATIFIED |
| Commits | 5 | ≤6 | OK |
| Files changed | 12 | ≤15 | OK |
| Backend touched | 0 | 0 | OK |
| Drift guards | 4 | ≥3 | OK |

**Decision needed before apply**: **Yes** (`size:exception` ratified).
**Chained PRs recommended**: **No** — single-PR integral.

---

**End of design — HU-F9.1.**
