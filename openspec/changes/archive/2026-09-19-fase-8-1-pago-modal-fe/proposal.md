# Proposal: HU-F8.1 — Modal de pago (efectivo/datáfono) con FE

> **Change**: `fase-8-1-pago-modal-fe`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F8.1 (Fase 8 — Cobro y Factura Electrónica, CU-04 + CU-05)
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC/PR`, strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` (per AGENTS.md gitflow). No AI attribution in commits.
> **Inputs read**:
>   - `plan.md` lines 1828-1948 (F8.1 block: ACs + ER + Zod + e2e + sequence diagram + `envio_dian`)
>   - `plan.md` line 419 (DEC-SUC-04 — `parkosFetch` retry + `Idempotency-Key`)
>   - `plan.md` lines 442-443 (DEC-SUC-27 — CU-15S prints AFTER pago confirmation)
>   - `plan.md` line 443 (DEC-SUC-28 — FE numeration real via `assign_consecutivo`)
>   - `plan.md` lines 522-526 (NIT + email reference cases)
>   - `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (F8.1 scaffold — partial PagoForm, FE consumidor-final default; needs refactor to shell + inner PagoModal)
>   - `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.test.tsx` (5 P1..P5 scenarios already passing on `dev`)
>   - `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` (F8.2 polling hook — out of scope for F8.1, mentioned for adjacency)
>   - `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` (F8.2 retry panel — out of scope)
>   - `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` (F7.2 host — opens `pago` drawer)
>   - `apps/electron-sucursal/src/features/operacion/hooks/useRegistrarSalida.ts` (F7.2 SWR mutation — pattern mirror)
>   - `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` (F7.2 `buildIdempotencyKey` SHA-256 helper — **reused as-is**)
>   - `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` (REQ-OPS-138 single-drawer store; `'pago'` already in `DrawerKind` union)
>   - `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (F5.2+F6.2+F7.3 skeleton; 4-tipo dispatcher; F8.1 adds 5th `recibo_pago` case)
>   - `openspec/changes/archive/2026-09-19-fase-7-3-tiquetes-salida/` (F7.3 baseline merged; CU-15S discriminated `salidaPayloadSchema` ships `medioPago` field ready)
>   - `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/` (F7.2 baseline merged; `useRegistrarSalida` pattern mirror)
>   - `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/` (F1.9 backend canonical: `POST /facturacion/factura` + `POST /facturacion/factura-pagos`)
>   - `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/` (F1.10 FE numeration via `assign_consecutivo` SELECT...FOR UPDATE)
> **Skills loaded**: `sdd-propose` (this phase), `_shared/sdd-phase-common` (Section B/C/D envelope).

## 1. Intent

HU-F8.1 closes the F7.2 → CU-04 + CU-05 pivot on the renderer side. From a confirmed `tipo_salida='ROTACION'` (F7.2), the operator opens the `pago` drawer via `useDashboardDrawerStore.open('pago', pagoAnchorId)`; inside the drawer, `<PagoModal />` renders the RHF+Zod form (medio `efectivo` | `datáfono`, vueltos en vivo, voucher manual, optional "Factura con mis datos" toggle). On submit, `useRegistrarPago()` fires two POSTs (`/facturacion/factura` then `/facturacion/factura-pagos`) with `Idempotency-Key` SHA-256 closure (F7.2 helper reuse), receives 201 with `{ uuid_factura, uuid_factura_electronica, estado_fe: 'pendiente' }`, and immediately calls `bridge.imprimir('salida', payload)` (CU-15S, F7.3 builder) followed by `bridge.imprimir('recibo_pago', payload)` (new 5th dispatcher case).

**Critical drift reconciliation** (between `plan.md` F8.1 text and the merged `dev` branch):

1. **A `PagoSheet.tsx` skeleton ALREADY exists** at `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` with a basic PagoForm (medio, monto, nit, voucher), FE consumidor-final default `222222222222222`, and 5 passing tests (P1..P5 in `PagoSheet.test.tsx`). F8.1's work is NOT to write the PagoSheet from scratch — it is to **extract the inner content into a new `<PagoModal />`** (the FE con datos toggle + vueltos en vivo + voucher live + Zod discriminated union) and reduce `PagoSheet` to the drawer shell (REQ-OPS-138 single-drawer invariant, focus-restore on close).
2. **An `escposBuilder` 4-tipo dispatcher already exists** (`entrada` | `salida` | `salida-mensualidad` | `reimpresion`). F8.1 ADDS a 5th case `'recibo_pago'` + `reciboPagoPayloadSchema` (Zod) + `buildReciboPagoBuffer()` + `reciboPagoBody()` — mirrors F7.3's tightening pattern (no new dispatcher switch arms; one more case wired).
3. **DEC-SUC-28 numeration is OWNED by F1.10's `assign_consecutivo`** (SELECT...FOR UPDATE per `uuid_sucursal`). F8.1's `recibo_pago` uses its OWN numeración `sucursal-YYYYMMDD-NNNNNN` (DEC-SUC-28 adjacent decision — ver `ABIERTO-02` per `plan.md:1843`); the renderer just displays the string the backend returns, never invents it.
4. **The F7.3 `salidaPayloadSchema` already carries `medioPago`** (`escposBuilder.ts:260` — `Medio de pago: ${payload.medioPago}`), so no new fields are needed on the CU-15S path. F8.1 only populates it.
5. **`FacturaElectronicaRetryPanel.tsx` and `useFacturaElectronica.ts` already exist** (F8.2 territory). F8.1 wires a pointer to the `uuid_fe` after the 201 but DOES NOT implement the polling (F8.2 owns `RefreshInterval: 30_000`).

User-facing payoff: from a confirmed salida rotación, the operador cobra sin salir de la pantalla principal, FE a consumidor final por defecto (sin preguntar), FE con datos propios opcional con validación cliente-side (NIT módulo 11 + email RFC 5322) antes de enviar. El pago SIEMPRE se registra; la FE SIEMPRE se genera (BR1 CU-04, regulación DIAN).

## 2. Scope

### 2.1 In scope (T1..T5 + I1)

- **T1 — `validarNitModulo11(nit, dv)` pure helper** (NEW `apps/electron-sucursal/src/lib/validation/nit.ts`): standard DIAN módulo 11 algorithm with per-digit weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59]`, `dv = (11 - (sum mod 11)) mod 11` mapped to `0..9` string. Returns `{ ok: true }` or `{ ok: false, dvEsperado: string }` (so the UI can show the DV expected per `plan.md:1861`). Input normalization: strip dots/dashes/spaces before validation. 5 unit tests + reference case `800.123.456-7` → `{ok:true}` and negative `800.123.456-1` → `{ok:false, dvEsperado:'7'}` per `plan.md:522-523`.
- **T2 — `<PagoModal />` inner content** (NEW `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx`): RHF + Zod resolver + vueltos en vivo (`useMemo(() => recibido - total, [recibido, total])`) + voucher manual `string.min(1)` when `medio='datafono'` + checkbox FE con datos propios (default unchecked, label "Factura a nombre del cliente (opcional); por defecto, factura a consumidor final" per `plan.md:1845` verbatim copy). Zod discriminated union: when `fe_con_datos=true`, `nit`/`dv`/`nombre`/`email` become required + `validarNitModulo11` + RFC 5322 refine. Render: `<SheetContent><PagoModal/></SheetContent>` inside `<PagoSheet />` (extraction).
- **T3 — `useRegistrarPago(uuidSalida, payload)` SWR mutation hook** (NEW `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts`): mirrors F7.2 `useRegistrarSalida` pattern (`useSWRMutation` + `Idempotency-Key` from `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` + 401 → `useAuthStore.clear()` + `parkos:auth:cleared`). Two-step POST: `POST /facturacion/factura` first → returns `{ uuid_factura }`; then `POST /facturacion/factura-pagos` with `{ uuid_factura, uuid_salida, medio_pago, valor, referencia_voucher? }` → returns `{ uuid_factura, uuid_factura_electronica, estado_fe, numero_recibo }`. Errors: 409 `numeracion_agotada` surfaces to UI (only FE error that reaches the operator, per `plan.md:1956`).
- **T4 — `<PagoSheet />` refactor** (UPDATE `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx`): reduce to drawer shell — `<Sheet><SheetContent><PagoModal total_cop={...} onConfirmado={useRegistrarPago(...).trigger}/></SheetContent></Sheet>`. REQ-OPS-138 single-drawer invariant preserved (focus restore, `Esc` close). Existing 5 P1..P5 tests in `PagoSheet.test.tsx` must still pass — refactor is transparent to them.
- **T5 — CU-15S + recibo_pago print trigger after 201** (UPDATE `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` + NEW escposBuilder extension): after 201, fire `queueMicrotask(() => try { bridge.imprimir('salida', buildSalidaPayload(...)) } catch ...)`. Same `deferredSafePrint` pattern as F7.2's `SalidaMensualidad` (`SalidaMensualidad.tsx:66-81`) — non-blocking on printer failure, no React error boundary propagation. Then `bridge.imprimir('recibo_pago', buildReciboPagoPayload(...))`.
- **I1 — `e2e/pago.spec.ts` 6 scenarios** (NEW): (1) efectivo vueltos correctos, (2) datáfono voucher manual, (3) FE consumidor final (checkbox sin marcar → NIT `222222222222222`), (4) FE con datos propios (NIT válido + email válido), (5) NIT inválido bloquea submit (422 cliente-side), (6) pago mixto → documentar como OUT OF SCOPE (mirror F7.3 e2e style + axe-core WCAG gate).
- **T6 — `recibo_pago` escposBuilder case** (UPDATE `apps/electron-sucursal/src/lib/print/escposBuilder.ts` + NEW `reciboPagoPayloadSchema`): add `reciboPagoPayloadSchema` to `escposTemplates.ts` (separador + sucursal.encabezado + empresa + numero_recibo + uuid_factura + uuid_factura_electronica + medio_pago + valor_recibido_cop + vueltos_cop + fecha + operador); add `buildReciboPagoBuffer()` + `reciboPagoBody()` to `escposBuilder.ts`; extend the 5-way `build()` dispatcher; extend `validatePayload()` 5-way switch. New 5th tipo: `'recibo_pago'`. Schema test mirrors F6.2 `entradaPayloadSchema` precedent.

### 2.2 Out of scope

- **HU-F8.2 — FE status polling + retry panel**: separate change. F8.1 only POINTS to `uuid_factura_electronica` after the 201; `FacturaElectronicaRetryPanel.tsx` + `useFacturaElectronica.ts` already exist on `dev` (F8.2 territory — 30s polling). F8.1 wires a `useState<uuid_fe>` in PagoModal but does not render the panel.
- **HU-F8.3 — Reimpresión con costo**: separate change (operador reimprime días después, crea `reimpresion_ticket` + cobra `costos_servicios`).
- **Backend FE numeration logic**: F1.10 owns (`assign_consecutivo` SELECT...FOR UPDATE). F8.1 only reads `numero_recibo` from the 201 response.
- **Backend TopPoint integration**: cloud-only (PR11 / `envio_dian` table).
- **SDK datáfono**: BR6 — datáfono = voucher manual, sin SDK en MVP.
- **Pago mixto (efectivo + datáfono)**: plan.md:1875 lo documenta como explícitamente OUT OF SCOPE para esta versión.
- **Backend changes**: zero. F1.9 ya cierra `POST /facturacion/factura` + `POST /facturacion/factura-pagos`.
- **Release branch + tag**: per gitflow, este cambio va a `dev` only.
- **Vite cache invalidation post-merge**: AGENTS.md post-merge script.

## 3. Approach

### 3.1 Decision Path 1 — PagoSheet refactor (extract inner PagoModal)

The existing `PagoSheet.tsx` (F8.1 partial scaffold) is a monolithic 240-LOC component that mixes drawer shell (Sheet/SheetContent/SheetHeader/focus-restore) with form content (RHF/Zod/medioPago/montoRecibido/nit/voucher). F8.1 SPLITS it:

- **`<PagoSheet />`** becomes the shell only: 60 LOC. Reads `useDashboardDrawerStore.openDrawer === 'pago'`, renders `<Sheet><SheetContent><PagoModal onConfirmado={...} /></SheetContent></Sheet>`. The 5 existing P1..P5 tests in `PagoSheet.test.tsx` still pass (drawer behaviour unchanged).
- **`<PagoModal />`** becomes the inner content: 200 LOC. Receives `total_cop: number`, `uuid_ingreso: string | null`, `onConfirmado(uuid_factura): Promise<void>`. Internally uses `useRegistrarPago(uuid_ingreso)` for the actual mutation; the `onConfirmado` prop is the parent's `useState<uuid_factura>` setter that wires the F8.2 panel.

Rationale: matches the `<SalidaSheet>` / `<SalidaPanel>` precedent at `SalidaSheet.tsx:54-70` — sheet shell wraps content panel; both are independently testable. Avoids the anti-pattern of mounting `useSWRMutation` inside a Radix Sheet portal (the existing `PagoSheet` initializes the RHF form even when the drawer is closed, which violates REQ-OPS-139 lazy-mount).

### 3.2 Decision Path 2 — Discriminated union on FE con datos toggle

Zod schema (per `plan.md:1855` expanded):

```typescript
const baseFields = z.object({
  medio: z.enum(['efectivo', 'datafono']),
  monto_recibido_cop: z.coerce.number().int().nonnegative(),
  voucher: z.string().trim().optional(),
  fe_con_datos: z.boolean(),
});

const clienteFinalSchema = z.object({
  fe_con_datos: z.literal(false),
  nit: z.literal('222222222222222'),
  dv: z.string().optional(),
  nombre: z.literal('Consumidor final'),
  email: z.string().optional(),
});

const clientePropioSchema = z.object({
  fe_con_datos: z.literal(true),
  nit: z.string().trim().regex(/^\d{9,15}$/, 'nit_formato_invalido'),
  dv: z.string().length(1),
  nombre: z.string().trim().min(3),
  email: z.string().email(),
}).superRefine((data, ctx) => {
  const r = validarNitModulo11(data.nit, data.dv);
  if (!r.ok) ctx.addIssue({ code: 'custom', path: ['dv'], message: `nit_invalido:dv_esperado_${r.dvEsperado}` });
});

export const pagoFormSchema = z.discriminatedUnion('fe_con_datos', [
  baseFields.merge(clienteFinalSchema),
  baseFields.merge(clientePropioSchema),
]);
```

`voucher` field becomes required at the form level when `medio='datafono'` via Zod refine (NOT a discriminated union on `medio` because both branches share the base shape). UI disable Confirm when `monto_recibido_cop < total_cop` (efectivo) or `voucher === ''` (datáfono).

### 3.3 Decision Path 3 — `useRegistrarPago` two-step POST

Mirrors F7.2's `useRegistrarSalida` (`useRegistrarSalida.ts:73-101`):

```typescript
async function mutateFn(_key, { arg: { uuidSalida, payload } }) {
  const idem = await buildIdempotencyKey({
    method: 'POST', path: '/api/v1/facturacion/factura',
    body: { uuid_salida: uuidSalida, ...payload },
  });
  try {
    const rawFactura = await parkosFetch<{ uuid_factura: string }>(
      '/api/v1/facturacion/factura',
      { method: 'POST', body: JSON.stringify({ uuid_salida: uuidSalida, ...payload }),
        headers: { 'Idempotency-Key': idem } },
    );
    const idem2 = await buildIdempotencyKey({
      method: 'POST', path: '/api/v1/facturacion/factura-pagos',
      body: { uuid_factura: rawFactura.uuid_factura, uuid_salida: uuidSalida,
              medio_pago: payload.medio, valor: payload.monto_recibido_cop,
              referencia_voucher: payload.voucher },
    });
    const rawPagos = await parkosFetch<{ uuid_factura: string; uuid_factura_electronica: string;
                                         estado_fe: 'pendiente' | 'aceptado' | 'rechazado';
                                         numero_recibo: string }>(
      '/api/v1/facturacion/factura-pagos',
      { method: 'POST', body: JSON.stringify({ uuid_factura: rawFactura.uuid_factura, ... }),
        headers: { 'Idempotency-Key': idem2 } },
    );
    return rawPagos;
  } catch (err) {
    // 401 → useAuthStore.clear + parkos:auth:cleared (preserve F3.1 invariant)
    // 409 numeracion_agotada → throw NumeracionAgotadaError (only FE error UI handles)
    // Other 4xx/5xx → rethrow as ParkosHttpError
  }
}
```

The two Idempotency-Keys differ (different `path`) — server-side dedup is per-path. The 24h cache window (F1.6 middleware) absorbs accidental re-clicks.

### 3.4 Decision Path 4 — Recibo de pago as escposBuilder 5th case

Mirrors F7.3's `salida` tightening pattern (`escposBuilder.ts:224-284`). New payload shape:

```typescript
export const reciboPagoPayloadSchema = z.object({
  sucursal: SucursalForPayload,                            // DEC-SUC-28 dynamic header
  empresa: EmpresaForPayload,
  operario: z.string(),
  numero_recibo: z.string().regex(/^[A-Z0-9-]+$/),          // e.g. 'SUC-20260919-000123'
  uuid_factura: z.string().uuid(),
  uuid_factura_electronica: z.string().uuid(),
  fecha_pago: z.string(),                                   // ISO 8601 verbatim (F5.2 R4)
  medio_pago: z.enum(['efectivo', 'datafono']),
  monto_total_cop: z.number().int().nonnegative(),
  monto_recibido_cop: z.number().int().nonnegative(),
  vueltos_cop: z.number().int().nonnegative().default(0),
  voucher: z.string().optional(),
  qrDataUrl: z.string(),
  logoDataUrl: z.string(),
});
```

Body emission: header (sucursal.encabezado) → sello `*** RECIBO DE PAGO ***` wrapped in `escText2x()/escTextReset()` → `Recibo No.: {numero_recibo}` → `Factura: {uuid_factura}` → `FE: {uuid_factura_electronica}` → `Fecha: {formatFecha(fecha_pago)} {formatHora(fecha_pago)}` → `Medio: {medio_pago}` → `Voucher: {voucher ?? '—'}` → `Total: {formatCOP(monto_total_cop)}` → bold `RECIBIDO: {formatCOP(monto_recibido_cop)}` → `Vueltos: {formatCOP(vueltos_cop)}` → `;QR:{qrDataUrl}` + `;LOGO:{logoText}` (mirror F6.2/F7.3 DEC-SUC-26).

### 3.5 Drift Reconciliation — Skeleton vs F8.1 final shape

| Aspect | F8.1 scaffold (live on dev) | F8.1 final shape |
|---|---|---|
| `PagoSheet.tsx` | 240 LOC monolith (shell + form + RHF + Zod + focus-restore) | 60 LOC shell only (Sheet + SheetContent + PagoModal composition + focus-restore) |
| `PagoModal.tsx` | (does not exist) | 200 LOC inner content (RHF + Zod discriminated union + vueltos live + voucher conditional + checkbox FE) |
| `validarNitModulo11()` | (does not exist) | 50 LOC pure helper + 80 LOC unit tests (5 scenarios) |
| `useRegistrarPago()` | (does not exist) | 70 LOC SWR mutation hook + 100 LOC tests (4 scenarios) |
| `escposBuilder` | 4-tipo dispatcher (`entrada`/`salida`/`salida-mensualidad`/`reimpresion`) | 5-tipo dispatcher (+ `recibo_pago`); +1 schema in `escposTemplates.ts` |
| `recibo_pago` builder | (does not exist) | NEW `buildReciboPagoBuffer` + `reciboPagoBody` + `reciboPagoPayloadSchema` (Zod) |
| `PagoSheet.test.tsx` P1..P5 | 5 passing on `dev` | 5 STILL passing (drawer shell behaviour unchanged after refactor) |
| `FacturaElectronicaRetryPanel.tsx` | Exists on `dev` (F8.2 territory) | F8.1 sets `uuid_fe` state; F8.2 wires the polling. NOT modified in F8.1. |
| CU-15S print trigger | F7.3 ships `build('salida', payload)` + `medioPago` field ready | F8.1 CALLS it from `<PagoModal />` after 201 (DEC-SUC-27 verbatim) |
| Recibo de pago print | (does not exist) | F8.1 CALLS `bridge.imprimir('recibo_pago', payload)` after CU-15S |

## 4. Affected files

| File | Action | LOC est. | Notes |
|---|---|---|---|
| `apps/electron-sucursal/src/lib/validation/nit.ts` | NEW | 50 | T1 — `validarNitModulo11` pure helper (módulo 11 algoritmo + normalization + 2 return shapes). |
| `apps/electron-sucursal/src/lib/validation/nit.test.ts` | NEW | 80 | T1 — 5 unit tests: `800.123.456-7` ok, `800.123.456-1` dv='7' expected, leading-zero NIT, 15-digit NIT, normalization with dots/dashes. |
| `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` | NEW | 200 | T2 — RHF + Zod discriminated union + vueltos live + voucher conditional + checkbox FE con datos + copy obligatoria "Factura a nombre del cliente (opcional); por defecto, factura a consumidor final" (`plan.md:1845` literal). |
| `apps/electron-sucursal/src/features/facturacion/components/PagoModal.test.tsx` | NEW | 150 | T2 — 7 scenarios: vueltos live, voucher required for datáfono, FE consumidor final default, FE con datos propios (NIT ok), NIT inválido blocks submit, email RFC 5322 invalid, mixed pago out-of-scope banner. |
| `apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts` | NEW | 60 | T3 — Zod schema mirror of `FacturaCreate` + `FacturaPagosCreate` + `FacturaPagosRead` response shapes. Mirrors F7.2 `salidaApi.ts` precedent. |
| `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` | NEW | 70 | T3 — SWR mutation hook. Two-step POST + `Idempotency-Key` SHA-256 + 401/409/422 error mapping. Mirror F7.2 `useRegistrarSalida.ts:73-101`. |
| `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.test.ts` | NEW | 100 | T3 — 4 scenarios: efectivo success → 201 + uuid_fe, datáfono success → 201 + voucher, 401 → auth cleared, 409 numeracion_agotada → UI banner. |
| `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` | UPDATE | −180 (delta: 240 → 60) | T4 — reduce to drawer shell; mount `<PagoModal total_cop onConfirmado />`. Existing P1..P5 tests still pass. |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | UPDATE | +80 (delta) | T6 — add `buildReciboPagoBuffer` + `reciboPagoBody` + 5th `case 'recibo_pago'` in dispatcher. DEC-SUC-28 dynamic header + DEC-SUC-26 QR + logo markers + DEC-SUC-27 sello `*** RECIBO DE PAGO ***` with `escText2x()/escTextReset()` wrap. |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | UPDATE | +35 (delta) | T6 — `reciboPagoPayloadSchema` Zod + `ReciboPagoPayload` type + `ReciboPagoTipo` literal + extend `TIQUETE_TIPOS` constant. |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.recibo.test.ts` | NEW | 80 | T6 — 8 byte-presence scenarios: header from `sucursal.encabezado`, sello + `0x1B 0x21 0x30` opcode, numero_recibo, uuid_factura, uuid_factura_electronica, medio_pago, vueltos, QR + logo markers. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx` | UPDATE | +15 (delta) | T4 wiring — wire `<CotizacionPanel onConfirmar />` → `useRegistrarSalida()` + on `tipo_salida='ROTACION'` → `open('pago', pagoAnchorId)` + pass `cotizacion.total` as `total_cop` to the PagoSheet. Mirror F7.2 §3.1 precedent. |
| `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` | UPDATE | +12 keys (delta) | T2 — `pago.fe_con_datos_label` (copy obligatoria verbatim), `pago.fe_con_datos_help`, `pago.vueltos`, `pago.monto_insuficiente`, `pago.voucher_requerido`, `pago.nit_invalido_dv`, `pago.email_invalido`, `pago.errors.numeracion_agotada`, `pago.errors.network`, `recibo.titulo`, `recibo.sello`, `recibo.recibido`. |
| `apps/electron-sucursal/e2e/pago.spec.ts` | NEW | 130 | I1 — 6 Playwright scenarios per `plan.md:1868-1875`. axe-core WCAG gate. |
| **Total new LOC** | | **+1010** | |
| **Total updated LOC (deltas)** | | **+131** (−180 PagoSheet refactor + 6 net updates) | |
| **Grand total LOC** | | **~1140** | **EXCEEDS 800 LOC budget — `size:exception` required (R1 in §6)** |

## 5. Dependencies

### 5.1 Already-merged prerequisites (verified on `dev`)

- **F7.2 — `SalidaFlow` + `useRegistrarSalida` + `buildIdempotencyKey`** (merged): ships the SWR mutation pattern + SHA-256 helper that F8.1's `useRegistrarPago` mirrors verbatim. **Required**.
- **F7.3 — `escposBuilder` 4-tipo dispatcher + CU-15S body emission + `medioPago` field on `salidaPayloadSchema`** (merged): ships the exact builder F8.1 invokes after 201. **Required**.
- **F1.9 — `POST /facturacion/factura` + `POST /facturacion/factura-pagos`** (merged): the canonical backend endpoints F8.1's two-step POST consumes. **Required**.
- **F1.10 — FE numeration via `assign_consecutivo`** (merged): owns the `numero_recibo` value the 201 returns. F8.1 only displays it. **Required**.
- **F1.6 — `IdempotencyKeyMiddleware` 24h cache** (merged, PR2): the backend dedup F8.1's SHA-256 headers depend on. **Required**.
- **F2.x — `parkosFetch` + `useAuthStore`** (merged): canonical HTTP client + auth store. **Required**.
- **F4.2 — `formatCOP`** (merged): F8.1 reuses in vueltos display. **Required**.
- **DEC-SUC-06 — RHF + Zod (`zodResolver`)** (verified at `plan.md:421`): F8.1 follows verbatim.
- **REQ-OPS-138 single-drawer store** (F6.1 `dashboardDrawerStore.ts`): `'pago'` already in `DrawerKind` union. **Required**.

### 5.2 Forward-dependents (do NOT block F8.1)

- **HU-F8.2 — FE status polling**: F8.1 sets `uuid_fe` state but F8.2 owns the `useFacturaElectronica` polling (`useFacturaElectronica.ts` already on `dev`, F8.2 territory).
- **HU-F8.3 — Reimpresión con costo**: F8.3 owns the `reimpresion_ticket` workflow + `costos_servicios` charging.
- **HU-F8.x — Recibo de pago re-issue**: when F8.x adds the reprint-recibo flow, it reuses F8.1's `build('recibo_pago', payload)` (the dispatcher case is now available).

### 5.3 Skill + tooling prerequisites

- `react` skill (loaded by parent) — D-073 stack, Vite 5, shadcn/ui único, RHF + Zod, i18next es-CO, WCAG 2.1 AA via axe-core.
- `python` skill (loaded by parent for backend reading) — F8.1 ships no backend code; F1.9/F1.10 already close the backend.

## 6. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **F8.1 forecast ~1140 LOC vs 800 budget** — needs `size:exception`. The FE con datos shape (discriminated union + vueltos live + voucher conditional) is integral; cannot split into chained PRs without leaving the form incomplete or the dispatcher without its 5th case. | HIGH | (a) RATIFIED in tasks phase — single-PR with `size:exception`. F7.1 precedent: 935 LOC vs 800 also ratified (Engram session 2026-09-19, size:exception accepted by user). (b) Drift guard `tests/static/test_pago_form_is_atomic.py` asserts `PagoSheet.tsx` + `PagoModal.tsx` + `useRegistrarPago.ts` + `validarNitModulo11.ts` + `escposBuilder.recibo_pago.ts` ship in the same commit. (c) 6-commit work-unit plan (§8.2) keeps each commit reviewable. |
| **R2** | **Backend FE failure isolation depends on F1.10 contract** — if FE TopPoint returns 5xx asynchronously, pago is committed but UI doesn't know. The pago is recorded in `factura_pagos` regardless (BR5 CU-04); FE failure flows through `envio_dian` (cloud-side), not through the operator terminal. | MED | (a) Plan §1956 — 409 `numeracion_agotada` is the ONLY FE error path that surfaces to UI (raises `<NumeracionAgotadaError />` banner). Other 5xx fall through silently and are re-queued via `envio_dian` workflow. (b) `useRegistrarPago` returns 201 with `estado_fe='pendiente'` — UI sets `uuid_fe` so F8.2's polling panel takes over. (c) Drift guard `tests/static/test_pago_doesnt_block_on_fe.py` asserts `useRegistrarPago` does NOT retry on FE state changes (post-201, the FE status is F8.2's concern). |
| **R3** | **NIT módulo 11 validation edge cases** — leading zeros, padded DV, alpha characters, very short/long NITs. | LOW | (a) Validator normalizes: strip non-digits, pad DV to single char, accept 9-15 digit NITs (DIAN range). (b) `nit.test.ts` covers: `800.123.456-7` (ref), `800.123.456-1` (negative), `123-456-7` (short), `800000000-0` (zero), `222222222222222` (consumidor final — known-valid). (c) The reference case in `plan.md:522-523` is the explicit canonical test. |
| **R4** | **Recibo de pago numeración `sucursal-YYYYMMDD-NNNNNN` is local to F1.10 backend** — risk of collision if N resets per day or branches share the same prefix. | LOW | (a) Backend F1.10 owns the counter via `assign_consecutivo` SELECT...FOR UPDATE per `uuid_sucursal` (verified `atomic_next_consecutivo.py`). (b) Renderer just displays the string the 201 returns — never invents. (c) The `numero_recibo` schema regex `/^[A-Z0-9-]+$/` accepts the format F1.10 emits. |
| **R5** | **Doble-click during in-flight pago** — duplicate INSERT or 409 `factura_duplicada`. | LOW | (a) `useSWRMutation.isMutating` UI disable on Confirm button (`PagoModal.tsx` — mirrors F7.2 R2 invariant at `useRegistrarSalida.ts` §6 R2). (b) `Idempotency-Key` SHA-256 closure on BOTH POSTs (`/factura` + `/factura-pagos`) — same body → same key, server-side 24h cache dedup. (c) `e2e/pago.spec.ts` scenario 6 (mixed-pago OOS banner) plus a manual rapid-click scenario in dev. |
| **R6** | **`<PagoSheet />` refactor breaks the 5 passing P1..P5 tests** if the focus-restore / single-drawer behaviour drifts. | MED | (a) The refactor preserves the `<Sheet>` + `<SheetContent>` + focus-restore pattern verbatim (`PagoSheet.tsx:118-122` unchanged). (b) `PagoSheet.test.tsx` P1..P5 only assert drawer state — no form internals. (c) `PagoModal.test.tsx` covers the form internals separately (7 scenarios). |
| **R-DRIFT** | **`plan.md` mentions `useVueltos` hook** (`plan.md:1853`) — `useVueltos` does NOT exist on `dev`. F8.1 must either ship the hook or inline `useMemo`. | LOW | (a) `useMemo(() => Math.max(0, recibido - total), [recibido, total])` is 1 line — extracting a hook adds complexity without value. (b) Inline `useMemo` accepted as the canonical pattern (matches F7.1 `useCountdown` precedent at `useCountdown.ts`). (c) If vueltos logic grows (denominaciones_permitidas per ABIERTO-200), the `useVueltos` extraction becomes a follow-up per `plan.md:7413`. |
| **R7** | **Print trigger fires before the 201 response is rendered** — if `bridge.imprimir` blocks the React commit, the operator sees a blank panel for 200ms+ on slow printers. | LOW | (a) `deferredSafePrint` helper (F7.2 precedent at `SalidaMensualidad.tsx:66-81`) wraps both `bridge.imprimir` calls in `queueMicrotask` + `try/catch`. (b) Print failure does NOT propagate to the React error boundary. (c) The `setUuidFe` state setter runs SYNCHRONOUSLY before the `queueMicrotask`, so F8.2's panel mounts immediately. |

## 7. Open decisions to ratify

Three open decisions require user ratification before `sdd-spec` locks them.

### OD-1 — Voucher field type: `string` or `number`?

**Proposal**: **`string`** (datáfono vouchers can have letters + numbers — e.g., `"VISA-1234"`, `"MASTERCARD-9012-3456"`, or even alphanumeric internal references).

**Alternatives**: (a) `number` only — forces numeric-only vouchers, breaks real-world datáfono outputs. (b) Discriminated union on `medio='datafono'` with `voucher: z.string().min(1)` required.

**Ratification needed**: confirm `string` (F8.1 spec default). Alternative (b) adds redundant complexity since the same schema handles both branches with `.optional()`.

### OD-2 — Recibo de pago print order: ANTES or DESPUÉS of CU-15S?

**Proposal**: **DESPUÉS** (operador arranca con el CU-15S — la salida lógica — y termina con el recibo de pago — el comprobante del cobro).

**Alternatives**: (a) ANTES — el recibo es "lo que el cliente se lleva", el CU-15S es "lo que la sucursal archiva". (b) Simultáneo — fire both in parallel via two `queueMicrotask`s.

**Ratification needed**: confirm DESPUÉS. Plan §1843 implies sequential ("se dispara la impresión del tiquete de salida (CU-15S, HU-F7.3) y del recibo de pago").

### OD-3 — `validarNitModulo11` accepts NIT with dots/dashes (`800.123.456-7`) or digits-only (`800123456`)?

**Proposal**: **normalizar input** — strip non-digits antes de validar; aceptar ambos formatos. La UI muestra el valor normalizado en el campo.

**Alternatives**: (a) strict — solo formato canónico `^\d{9,15}-\d$`. (b) Dual — accept both, return error if neither canonical form parses.

**Ratification needed**: confirm normalizar. Real-world NITs in Colombia are typed in both forms (accounting software, scanner OCR, operator typing). Strict-only would generate needless friction.

## 8. PR shape

### 8.1 Single PR topology

| Field | Value |
|---|---|
| Branch | `feature/hu-f8-1-pago-modal-fe` |
| Target | `dev` (gitflow — NEVER `main`) |
| Work units | T1, T2, T3, T4, T5, T6 + I1 (7 commits) |
| Commit strategy | `work-unit-commits` skill — each T/I is a separate reviewable commit |
| Conventional Commits | strict (no `Co-authored-by` AI trailers per AGENTS.md canon) |
| LOC budget | 800 lines per PR; F8.1 forecast = ~1140 LOC |
| `size:exception` required | **YES** — 1140 LOC > 800 budget (+340, +42.5%) |
| Chained PRs | **NO** — FE con datos discriminated union + vueltos live + voucher conditional + recibo_pago builder extension are integral; cannot split without leaving the form or the dispatcher broken |

### 8.2 Commit plan (work-unit-commits skill)

Each commit MUST compile + pass all tests independently (strict TDD).

| # | Commit | Type | Scope | Files | TDD phase |
|---|---|---|---|---|---|
| 1 | `feat(validation): validarNitModulo11 pure helper + 5 unit tests (DEC-SUC-04, plan.md:522)` | feat | validation | NEW nit.ts, NEW nit.test.ts | RED (5 tests fail: ref ok + 4 negatives) → GREEN |
| 2 | `feat(facturacion): PagoModal extracted from PagoSheet with FE con datos toggle + vueltos live` | feat | facturacion | NEW PagoModal.tsx, NEW PagoModal.test.tsx, UPDATE PagoSheet.tsx (−180 delta) | RED (7 tests fail) → GREEN (5 existing PagoSheet P1..P5 still pass; 7 PagoModal scenarios pass) |
| 3 | `feat(facturacion): useRegistrarPago SWR mutation + 4 unit tests (mirror useRegistrarSalida)` | feat | facturacion | NEW facturaApi.ts, NEW useRegistrarPago.ts, NEW useRegistrarPago.test.ts | RED (4 tests fail: efectivo ok, datáfono ok, 401 auth cleared, 409 numeracion_agotada) → GREEN |
| 4 | `feat(operacion): SalidaPanel wires open('pago', pagoAnchorId) on tipo_salida='ROTACION'` | refactor | operacion | UPDATE SalidaPanel.tsx (+15 delta) | RED (existing test fails on missing `open('pago', ...)` call) → GREEN |
| 5 | `feat(print): recibo_pago escposBuilder 5th case + ReciboPagoPayload schema + 8 byte-presence tests` | feat | print | UPDATE escposBuilder.ts (+80 delta), UPDATE escposTemplates.ts (+35 delta), NEW escposBuilder.recibo.test.ts | RED (8 byte-presence tests fail) → GREEN; existing 4-tipo dispatcher tests still pass |
| 6 | `feat(facturacion): PagoModal fires CU-15S + recibo_pago prints after 201 via deferredSafePrint` | feat | facturacion | UPDATE PagoModal.tsx (add deferredSafePrint import + 2 calls), NEW e2e/pago.spec.ts (6 scenarios) | RED (e2e fails on missing print spy call) → GREEN |
| 7 | `docs(sdd): F8.1 spec delta REQ-OPS-161..165 in operations/spec.md + i18n keys + drift guards` | docs | sdd | UPDATE facturacion.json (+12 keys), UPDATE openspec/changes/fase-8-1-pago-modal-fe/specs/operations/spec.md, UPDATE openspec/specs/operations/spec.md | Spec sync + drift guards |

### 8.3 PR title + body

- **Title**: `feat(facturacion): HU-F8.1 pago modal (efectivo/datáfono) + FE consumidor-final/con-datos + recibo_pago (size:exception 1140 LOC)`
- **Body**: Conventional Commits footer with `Refs: HU-F8.1`, `Refs: REQ-OPS-161..165`, `Closes: plan.md:1828-1948`. Bullet list of the 7 T/I/E work units. Drift reconciliation note (§3.5) inline — explicit acknowledgement that PagoSheet was a partial F8.1 scaffold and F8.1 extracts PagoModal + adds recibo_pago case. Rollback plan: revert the single branch (`feature/hu-f8-1-...` → `dev`), no DB migration, no backend change. The 7 commits are atomic per work-unit (revertible individually via `git revert <sha>` without breaking the build).

### 8.4 Verification gate (pre-merge)

- [ ] `git diff dev..feature/hu-f8-1-...` ≤ 1140 LOC (with `size:exception` ratified)
- [ ] `pnpm --filter electron-sucursal lint` exits 0
- [ ] `pnpm --filter electron-sucursal typecheck` exits 0 (incl. `tsc --strict` exhaustiveness on Zod discriminated union `fe_con_datos`)
- [ ] `pnpm --filter electron-sucursal test` exits 0 with all 5 PagoSheet P1..P5 + 7 PagoModal + 4 useRegistrarPago + 8 escposBuilder.recibo + 5 nit tests passing
- [ ] `pnpm --filter electron-sucursal e2e -- pago.spec.ts` exits 0 with 6 scenarios passing
- [ ] Drift guard: `grep -r "PARKINGOS" apps/electron-sucursal/src/lib/print` returns 0 matches (DEC-SUC-28 invariant preserved post-refactor)
- [ ] Drift guard: `grep -r "validarNitModulo11" apps/electron-sucursal/src/lib/validation` returns ≥5 matches (5 unit tests)
- [ ] Drift guard: `grep -r "buildReciboPagoBuffer" apps/electron-sucursal/src` returns ≥3 matches (escposBuilder definition + PagoModal caller + test import)
- [ ] Drift guard: `tests/static/test_pago_form_is_atomic.py` asserts PagoSheet + PagoModal + useRegistrarPago + validarNitModulo11 + escposBuilder.recibo all ship in the same branch
- [ ] axe-core WCAG 2.1 AA: 0 violations on `<PagoModal />` + `<PagoSheet />` (gated per CI per DEC-SUC-10)
- [ ] `gh pr merge --squash --body-file` produces a squash commit with no `Co-authored-by` AI trailer

### 8.5 Post-merge (per AGENTS.md gitflow + override rule 2026-09-17)

1. `git checkout dev` + `git merge --ff-only feature/hu-f8-1-pago-modal-fe` (or `--no-ff` if not direct descendant).
2. `git push origin dev`.
3. `git branch -d feature/hu-f8-1-pago-modal-fe` + `git push origin --delete feature/hu-f8-1-pago-modal-fe`.
4. Vite cache invalidation: kill port 5173 + restart with `--force` per AGENTS.md.
5. Engram `mem_save` of the canonical `validarNitModulo11` + `PagoModal` composition + `useRegistrarPago` two-step POST + `buildReciboPagoBuffer` decisions (post-merge convention).
6. F8.2 developer notification: PagoModal now exposes `uuid_fe` via `useState`; wire `useFacturaElectronica(uuid_fe)` into the existing `FacturaElectronicaRetryPanel.tsx` for the 30s polling.

## 9. Success criteria

1. `validarNitModulo11('800.123.456', '7')` returns `{ok:true}`; `validarNitModulo11('800.123.456', '1')` returns `{ok:false, dvEsperado:'7'}`; normalization strips dots/dashes/spaces.
2. `<PagoSheet />` mount → REQ-OPS-138 single-drawer preserved (P1..P5 still pass); focus restored to anchor on close.
3. `<PagoModal />` opens with `total_cop` pre-filled, vueltos live (`useMemo`), FE consumidor-final default (NIT `222222222222222`), copy obligatoria literal "Factura a nombre del cliente (opcional); por defecto, factura a consumidor final".
4. Toggle FE con datos propios → NIT/DV/nombre/email required + `validarNitModulo11` + RFC 5322 refine; invalid NIT blocks submit and shows DV expected.
5. Confirm → `useRegistrarPago` issues two POSTs with `Idempotency-Key` SHA-256 closure; 401 clears auth (F3.1 invariant); 409 `numeracion_agotada` raises a localized banner.
6. 201 response → `setUuidFe(uuid_factura_electronica)` + `bridge.imprimir('salida', buildSalidaPayload(...))` (CU-15S via F7.3 builder) + `bridge.imprimir('recibo_pago', buildReciboPagoPayload(...))` (new 5th case) — both deferred to `queueMicrotask` + `try/catch`.
7. `escposBuilder.build('recibo_pago', mockPayload)` returns a `Buffer` containing all 8 conceptual fields (header `payload.sucursal.encabezado` + sello `*** RECIBO DE PAGO ***` with `0x1B 0x21 0x30` opcode + numero_recibo + uuid_factura + uuid_factura_electronica + medio_pago + vueltos + QR + logo markers).
8. `e2e/pago.spec.ts` passes 6 scenarios: efectivo vueltos / datáfono voucher / FE consumidor-final / FE con datos / NIT inválido / pago mixto (OOS banner).
9. Drift guards pass: PagoSheet + PagoModal + useRegistrarPago + validarNitModulo11 + escposBuilder.recibo all ship in the same branch (no PR split).
10. `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the full `electron-sucursal` workspace.
11. The Zod discriminated union `pagoFormSchema` exhaustiveness check fails `tsc --noEmit` if either branch (`clienteFinalSchema` or `clientePropioSchema`) is renamed or removed.

## 10. Out of scope (re-iterated for emphasis)

- HU-F8.2 — FE status polling + retry panel (`useFacturaElectronica.ts` already on `dev`, F8.2 territory).
- HU-F8.3 — Reimpresión con costo (separate change; `reimpresion_ticket` workflow + `costos_servicios`).
- Backend FE numeration logic — F1.10 owns `assign_consecutivo`.
- Backend TopPoint integration — cloud-only (PR11 / `envio_dian` table).
- SDK datáfono — BR6, voucher manual only.
- Pago mixto (efectivo + datáfono) — plan.md:1875 explícitamente OUT OF SCOPE.
- Backend changes — zero.
- Release branch + tag — post-merge operational, not PR scope.
- Vite cache invalidation post-merge — handled by AGENTS.md script.

## 11. Relevant files (canonical pointers)

**OpenSpec / plan / spec**:
- `openspec/changes/fase-8-1-pago-modal-fe/proposal.md` (this file)
- `openspec/changes/fase-8-1-pago-modal-fe/specs/operations/spec.md` (sdd-spec delta, REQ-OPS-161..165)
- `openspec/changes/fase-8-1-pago-modal-fe/design.md` (sdd-design phase, future)
- `openspec/changes/fase-8-1-pago-modal-fe/tasks.md` (sdd-tasks phase, future)
- `openspec/changes/fase-8-1-pago-modal-fe/apply-progress.md` (sdd-apply phase, future)
- `openspec/changes/fase-8-1-pago-modal-fe/verify-report.md` (sdd-verify phase, future)
- `plan.md` lines 1828-1948 (F8.1 block: ACs + ER + Zod + e2e + sequence + `envio_dian` state)
- `openspec/specs/operations/spec.md` (F7.2 REQ-OPS-152..157 baseline — F8.1 extends with REQ-OPS-161..165)

**Archive precedents**:
- `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/{proposal,design,tasks,verify-report}.md` (F7.2 — `useRegistrarSalida` SWR mutation + `buildIdempotencyKey` + 409 `salida_duplicada` error mapping)
- `openspec/changes/archive/2026-09-19-fase-7-3-tiquetes-salida/{proposal,design,tasks,verify-report}.md` (F7.3 — `escposBuilder` tightening + `buildSalidaBuffer` 21-field + DEC-SUC-28 dynamic header; F8.1 mirrors the 5th-case pattern)
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/{proposal,design,tasks,verify-report}.md` (F1.9 backend canonical — `POST /facturacion/factura` + `POST /facturacion/factura-pagos` contracts)
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/{proposal,design,tasks,verify-report}.md` (F1.10 FE numeration + `envio_dian` state machine)
- `openspec/changes/archive/2026-09-19-fase-7-1-busqueda-tolerante-cotizacion/{proposal,design,tasks,verify-report}.md` (F7.1 — `size:exception` precedent ratified for 935 LOC)

**Frontend source (live on `dev` at `ba1f349`)**:
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (F8.1 scaffold — target of T4 refactor to shell)
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.test.tsx` (5 P1..P5 scenarios — MUST still pass post-refactor)
- `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` (F8.2 polling hook — F8.1 does NOT modify)
- `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` (F8.2 retry panel — F8.1 does NOT modify)
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (F5.2+F6.2+F7.3 — target of T6 5th-case extension)
- `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (F5.2+F6.2+F7.3 — target of T6 `reciboPagoPayloadSchema`)
- `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx:80,116-117` (F7.2 host — `open('pago', pagoAnchorId)` already wired; F8.1 verifies the call site + passes `cotizacion.total` as `total_cop`)
- `apps/electron-sucursal/src/features/operacion/hooks/useRegistrarSalida.ts` (F7.2 SWR mutation pattern — F8.1 `useRegistrarPago` mirrors)
- `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` (F7.2 `buildIdempotencyKey` — F8.1 reuses as-is)
- `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` (REQ-OPS-138 single-drawer store; `'pago'` already in `DrawerKind` union)
- `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` (F8.1 scaffold keys — T2 extends with 12 new keys)

**Files NOT touched (deliberate)**:
- `backend/**` (zero backend changes; F1.9/F1.10 already ship the canonical endpoints + numeration)
- `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` (F8.2 owns; F8.1 sets `uuid_fe` state, F8.2 wires the polling)
- `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` (F8.2 owns; F8.1 does not mount this panel)
- `apps/electron-sucursal/src/features/operacion/components/SalidaMensualidad.tsx` (F7.2 mensualidad path unchanged; no pago needed)
- `apps/electron-sucursal/src/main/services/*` (printer hardware fallback chain — F5.1 owns)

## 12. Next steps

1. **sdd-spec** (`fase-8-1-pago-modal-fe`): author the delta spec against `openspec/specs/operations/spec.md` (add REQ-OPS-161..165 with 5 scenarios: REQ-OPS-161 `validarNitModulo11` pure helper + 5 unit tests, REQ-OPS-162 `<PagoModal />` RHF + Zod discriminated union + vueltos live + voucher conditional, REQ-OPS-163 `useRegistrarPago` two-step SWR mutation with `Idempotency-Key` SHA-256, REQ-OPS-164 `escposBuilder.build('recibo_pago', payload)` 5th case + `reciboPagoPayloadSchema` + DEC-SUC-27 `*** RECIBO DE PAGO ***` sello with `0x1B 0x21 0x30` opcode, REQ-OPS-165 `<PagoSheet />` refactor to drawer shell preserving P1..P5 + atomic PagoSheet+PagoModal+useRegistrarPago+validarNitModulo11+escposBuilder.recibo drift guard).
2. **sdd-design**: technical design for the PagoModal composition + Zod discriminated union + `useRegistrarPago` two-step POST + `reciboPagoPayloadSchema` builder extension. Cite F7.2 `useRegistrarSalida` mirror precedent verbatim. Cite F7.3 `salidaPayloadSchema.medioPago` already-present field (no schema change needed). Show the canonical `PagoModalProps` + `ReciboPagoPayload` shapes.
3. **sdd-tasks**: 7-commit plan from §8.2 mapped to T-HU-F8.1-1..N task IDs with RED/GREEN/REFACTOR phases per commit. Flag `size:exception` for 1140 LOC vs 800 (R1 in §6, F7.1 precedent ratified 2026-09-19).
4. **sdd-apply**: implement + verify + merge to `dev` per AGENTS.md gitflow + override rule. Notify F8.2 developer that `uuid_fe` is now exposed via `useState` in PagoModal.
5. **sdd-verify**: run verification per §8.4 success criteria; produce `verify-report.md` with drift-guard grep outputs (PagoSheet+PagoModal+useRegistrarPago+validarNitModulo11+escposBuilder.recibo atomicity, 5 PagoSheet P1..P5 still pass, 7 PagoModal scenarios, 4 useRegistrarPago scenarios, 8 escposBuilder.recibo scenarios, 6 e2e pago scenarios, 0 axe-core WCAG 2.1 AA violations).
6. **sdd-archive**: sync delta specs to `openspec/specs/operations/spec.md` (canonical), archive the change folder.
