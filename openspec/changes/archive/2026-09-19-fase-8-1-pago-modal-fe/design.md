# Design: HU-F8.1 — Pago modal (efectivo/datáfono) + FE + recibo

> **Change**: `fase-8-1-pago-modal-fe` | **Phase**: design | **HU**: HU-F8.1 (CU-04 + CU-05) | **Base**: `dev @ ba1f349` | **Forecast**: ~1140 LOC | **`size:exception` REQUIRED** (ratification pending in tasks phase)
> **Inputs**: `proposal.md` §1..§12; `specs/operacion.md` REQ-OPS-161..165 | **Drift anchor**: F7.2 `useRegistrarSalida.ts:73-101` + F7.3 `salidaPayloadSchema.medioPago` + 4-tipo `escposBuilder`

## 1. Technical Approach

Renderer-only. Split F8.1 `<PagoSheet />` (240 LOC on `dev`) into 60-LOC shell + 200-LOC `<PagoModal />`; mirror F7.2 `useRegistrarSalida` into `useRegistrarPago` (two-step `POST /facturacion/factura` → `/factura-pagos`, distinct `Idempotency-Key` SHA-256 each); extend `escposBuilder` 4→5 tipos with `'recibo_pago'`. `validarNitModulo11(input, dv)` (DIAN weights `[3,7,13,17,19,23,29,37,41,43,47,53,59]`) runs in `PagoModal`'s `superRefine` when `fe_con_datos=true`; vueltos via `useMemo(() => Math.max(0, recibido − total), [recibido, total])`. Print after 201: CU-15S FIRST (DEC-SUC-27) then recibo SECOND, both `queueMicrotask` + try/catch (`SalidaMensualidad.tsx:66-81` precedent) — printer failure → `console.warn`, never reaches React error boundary.

## 2. Architecture Decisions

- **AD1 — Extract PagoModal from PagoSheet** (vs from scratch): P1..P5 tests MUST stay green; shell + focus-restore preserved. Mirrors `<SalidaSheet>`/`<SalidaPanel>` split.
- **AD2 — `useMemo` vueltos inline** (vs `useVueltos` hook): 1 line arithmetic; `useCountdown` precedent inlines similarly. ABIERTO-200 deferred.
- **AD3 — `recibo_pago` as 5th `case`** (vs separate module): mirrors F7.3 tightening — no new switch arms for existing 4. Reuses schemas + formatters.
- **AD4 — Zod discriminated union on `fe_con_datos`** (vs separate forms): base shape shared; `superRefine` emits `nit_invalido:dv_esperado_<dvEsperado>` on path `['dv']`.
- **AD5 — FE-failure isolation transparent** (vs renderer polling): BR5 CU-04 — F1.10 returns 201 even on FE async failure; only `409 numeracion_agotada` surfaces. F8.2 owns `useFacturaElectronica`.
- **AD6 — `size:exception` for 1140 LOC vs 800 budget**: atomic — shell + form + mutation + helper + builder integral. F7.1 precedent (935 LOC) ratified 2026-09-19. 7 work-unit commits keep each reviewable.

## 3. Data Flow

```
SalidaPanel ──openDrawer('pago', anchorId)──> <PagoSheet shell>
  └─ <PagoModal> ──useRegistrarPago().trigger()──>
       buildIdempotencyKey(SHA-256, /factura) ──POST /facturacion/factura──> 201 {uuid_factura}
       buildIdempotencyKey(SHA-256, /factura-pagos) ──POST /facturacion/factura-pagos──> 201
       ├─ 401 → useAuthStore.clear() + parkos:auth:cleared [F3.1]
       ├─ 409 numeracion_agotada → throw NumeracionAgotadaError
       └─ 201 → setUuidFe(uuid_fe)
              ├─ queueMicrotask bridge.imprimir('salida', buildSalidaPayload())     [CU-15S, DEC-SUC-27 FIRST]
              ├─ queueMicrotask bridge.imprimir('recibo_pago', buildReciboPagoPayload())  [5th case, SECOND]
              └─ close()  [REQ-OPS-138]
```

## 4. File Changes (12 files, ~1140 LOC)

NEW: `lib/validation/nit.ts` (50) + `.test.ts` (80); `features/facturacion/components/PagoModal.tsx` (200) + `.test.tsx` (150); `features/facturacion/api/facturaApi.ts` (60); `features/facturacion/hooks/useRegistrarPago.ts` (70) + `.test.ts` (100); `lib/print/__tests__/escposBuilder.recibo.test.ts` (80); `e2e/pago.spec.ts` (130).
UPDATE: `features/facturacion/components/PagoSheet.tsx` (−180, 240→60); `lib/print/escposBuilder.ts` (+80); `lib/print/escposTemplates.ts` (+35); `features/operacion/components/SalidaPanel.tsx` (+15); `renderer/i18n/locales/facturacion.json` (+12 keys).

## 5. Interfaces / Contracts

```ts
// nit.ts (pure)
validarNitModulo11(input: string, dv: string): { ok: true } | { ok: false; dvEsperado: string };

// facturaApi.ts — Zod mirror of F1.9
PagoPayloadSchema = z.discriminatedUnion('fe_con_datos', [
  clienteFinalSchema.merge(baseFields),
  clientePropioSchema.merge(baseFields).superRefine((d, ctx) => {
    const r = validarNitModulo11(d.nit, d.dv);
    if (!r.ok) ctx.addIssue({ path:['dv'], message: `nit_invalido:dv_esperado_${r.dvEsperado}` });
  }),
]);
FacturaPagosRead { uuid_factura; uuid_factura_electronica; estado_fe; numero_recibo }
  // numero_recibo: DEC-SUC-28 — F1.10 owns counter; renderer NEVER invents.

// useRegistrarPago — mirrors useRegistrarSalida
useRegistrarPago(): { trigger(arg: { uuidSalida; payload: PagoPayload }): Promise<FacturaPagosRead>;
  isMutating: boolean; error: ParkosHttpError | NumeracionAgotadaError | undefined; };
class NumeracionAgotadaError extends Error { status=409; code='numeracion_agotada'; }

// escposBuilder.ts — 5th case
build(tipo: 'entrada'|'salida'|'salida-mensualidad'|'reimpresion'|'recibo_pago', payload: unknown): Buffer;
buildReciboPagoBuffer(payload: ReciboPagoPayload): Buffer;
reciboPagoPayloadSchema = z.object({ sucursal: sucursalSchema, empresa: empresaSchema,
  operario: z.string(), numero_recibo: z.string().regex(/^[A-Z0-9-]+$/),
  uuid_factura: z.string().uuid(), uuid_factura_electronica: z.string().uuid(),
  fecha_pago: z.string().datetime({ offset: true }),
  medio_pago: z.enum(['efectivo','datafono']),
  monto_total_cop: z.number().int().nonnegative(),
  monto_recibido_cop: z.number().int().nonnegative(),
  vueltos_cop: z.number().int().nonnegative().default(0),
  voucher: z.string().optional(), qrDataUrl: z.string(), logoDataUrl: z.string() });
```

## 6. Testing Strategy

- **Unit (5)** `nit.test.ts`: `800.123.456-7` ok; `-1` → `{ok:false,dvEsperado:'7'}`; digits-only; leading-zero; 15-digit.
- **Component (7)** `PagoModal.test.tsx`: vueltos live; voucher required datáfono; FE default; FE con-datos expands; invalid NIT + `dvEsperado`; invalid email (RFC 5322); `isMutating` disables Confirm.
- **Hook (4)** `useRegistrarPago.test.ts`: efectivo 201 + `uuid_fe`; datáfono 201 + `voucher`; 401 → `useAuthStore.clear`; 409 → `NumeracionAgotadaError`; two `Idempotency-Key`s differ.
- **byte-presence (8)** `escposBuilder.recibo.test.ts`: header; sello `*** RECIBO DE PAGO ***` with `0x1B 0x21 0x30`; `numero_recibo`; `uuid_factura`; `uuid_factura_electronica`; `medio_pago`; `vueltos` via `formatCOP`; `;QR:` + `;LOGO:`.
- **e2e (6)** `pago.spec.ts` + axe-core WCAG 2.1 AA: efectivo vueltos; datáfono voucher; FE consumidor-final; FE con datos propios; NIT inválido blocks (422); pago mixto → OOS banner.

## 7-9. Threat / Migration / Open Questions

N/A — renderer-only; F3.1 401 + F5.1 printer fallback + F7.2 `Idempotency-Key` SHA-256 preserved verbatim. No DB / Alembic / backend code. 3 ODs (voucher `string`, recibo AFTER CU-15S, NIT normalization) ratified in proposal §7.

## 10. Review Workload Forecast

Forecast ~1140 LOC vs 800 budget → **`size:exception` REQUIRED** (ratification pending in tasks phase). **Chained PRs: No** (FE con-datos + vueltos + voucher + recibo_pago are integral). 7 work-unit commits (T1 nit → T2 PagoModal + sheet refactor → T3 useRegistrarPago → T4 SalidaPanel wiring → T5/T6 recibo_pago builder + PagoModal print trigger → I1 e2e → docs sync). Drift guard: `tests/static/test_pago_form_is_atomic.py` asserts PagoSheet + PagoModal + useRegistrarPago + validarNitModulo11 + escposBuilder.recibo ship in same branch (F7.1 R1 mitigation).