# Delta Spec: HU-F7.3 — Tiquetes de salida (CU-15S) + salida-mensualidad (CU-15SM)

> **Change**: `fase-7-3-tiquetes-salida`
> **Phase**: sdd-spec
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F7.3 (Fase 7 — Salida y cálculo de tarifa, tiquetes pivot)
> **Base spec**: `openspec/specs/operations/spec.md` (canonical, requires REQ-OPS-001..151)
> **Next free REQ-OPS gap**: 158..160 (REQ-OPS-152..157 are taken by F7.2 per `2026-09-19-fase-7-2-registrar-salida` archive; REQ-OPS-158..160 reserved by F7.3). F7.3 starts at REQ-OPS-158.
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC`, strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` per AGENTS.md gitflow. No AI attribution in commits.
> **Artifact language**: English (SDD canon); user-facing i18n keys in `operacion.json` stay in Spanish es-CO.
> **Skills loaded**: `sdd-spec` (this phase), `_shared/sdd-phase-common` (Section B/C/D envelope).
> **Drift anchor**: F5.2+F6.2 skeleton (merged `dev` at `d157195`) already ships `buildSalidaBuffer` + `buildSalidaMensualidadBuffer` + `salidaPayloadSchema` + `salidaMensualidadPayloadSchema` + the 4-tipo dispatcher at `apps/electron-sucursal/src/lib/print/escposBuilder.ts:240-301,350-366,391-427`. F7.3 TIGHTENS the body emission (NOT adds new cases) to match the EXACT 19/15 conceptual field lists of CU-15S/CU-15SM, the DEC-SUC-28 dynamic header swap, and the DEC-SUC-27 sello invariant.

## Context

HU-F7.3 closes the F7.2 → CU-04 pivot on the print-envelope layer. From a successful `POST /operacion/salidas` (F1.7, REQ-OPS-042..052, shipped on `dev`), the renderer fires the typed `bridge.imprimir` envelope carrying the full `SalidaPayload` (CU-15S) or `SalidaMensualidadPayload` (CU-15SM). The pure renderer-side `escposBuilder.build('salida' | 'salida-mensualidad', payload)` function (F5.2+F6.2 skeleton, **already shipped** with both cases wired to `buildSalidaBuffer` / `buildSalidaMensualidadBuffer`) emits the exact byte stream that `bridge.imprimir` ships to `escpos-usb` (F5.1).

**Drift reconciliation** between `plan.md` F7.3 block and the merged `dev` branch:

1. **F5.2 already shipped `salida` and `salida_mensualidad` cases** in the `build()` dispatcher (verified `escposBuilder.ts:391-427`). F7.3's work is NOT "add new cases" — it is **tightening the body emission** of the existing stubs to match the EXACT 19/15 conceptual field lists of CU-15S/CU-15SM. The current `buildSalidaBody` emits 17 fields, missing "Tarifa aplicada" (CU-15S field 9), "Fecha" date-only (field 10 split), "Horario atención" (field 19a), and "Observaciones" (field 19d). The current `buildSalidaMensualidadBody` emits 14 fields and IS missing the `*** PAGO CON MENSUALIDAD ***` sello literal that `plan.md:1787` mandates as a CU-15SM visual distinguisher (the literal IS in the body at `escposBuilder.ts:287` but WITHOUT the `escText2x()` wrap that the live header uses — drift between plan intent and live code, to be reconciled by F7.3).
2. **DEC-SUC-28** requires the header to be **dinámico de sucursal**, NOT the corpus defect "PARQUEADERO PUBLICO" fixed string nor the F5.2 "PARKINGOS" constant. F7.3 swaps the constant for `payload.sucursal.encabezado` (new field on the payload schemas) for ALL THREE bodies (CU-15E + CU-15S + CU-15SM — same migration step).
3. **DEC-SUC-27** sequence correction: CU-15S prints **AFTER pago confirmation** (Fase 8 HU-F8.1). F7.3 only DELIVERS `build('salida', payload)` — F8.1 is the call site. CU-15SM prints IMMEDIATELY at salida mensualidad (Fase 7) — F7.2 already fires the envelope (`SalidaMensualidad.tsx:41-47`); F7.3 fills the payload shape via `useSalidaMensualidadPayload` SWR hook.
4. **DEC-SUC-26** transversal: both tiquetes MUST include QR + logo (DEC-SUC-26 explicitly notes that CU-15S/CU-15SM literal field lists do NOT include QR + logo, but they are required anyway). F7.3 adds the `;QR:` + `;LOGO:` markers + placeholder glyph to both bodies (F6.2 precedent at `escposBuilder.ts:233-234`).

The user-facing payoff: from a confirmed salida (rotación or mensualidad), the operator hands the customer a printed tiquete that is final at emission (DEC-SUC-27 — no reprint gating on a cloud round-trip), with QR for traceability and logo for brand identity.

## New requirements

### REQ-OPS-158 — `escposBuilder.build('salida', payload)` produces 19-field CU-15S buffer + QR + logo

The system SHALL export `escposBuilder.build('salida', payload)` from `apps/electron-sucursal/src/lib/print/escposBuilder.ts`. The function MUST emit a `Buffer` containing, in canonical order, the **19 conceptual fields of CU-15S** per `plan.md:1789-1807`: (1) Encabezado, (2) Empresa, (3) Dirección, (4) NIT, (5) Régimen, (6) Operario, (7) Sello `*** SALIDA ***` wrapped by `escText2x()` / `escTextReset()`, (8) Folio, (9) Tarifa aplicada, (10) Fecha (date-only), (11) Hora entrada, (12) Hora salida, (13) Tiempo total, (14) Subtotal, (15) IVA, (16) Total a pagar, (17) Medio de pago, (18) Placa, (19) Horario atención / Póliza RC / Resolución FE / Observaciones — PLUS the **2 DEC-SUC-26 additions** (QR + logo markers). The header MUST equal `payload.sucursal.encabezado` (DEC-SUC-28 dynamic), NOT the F5.2 "PARKINGOS" constant or the corpus "PARQUEADERO PUBLICO" string. The QR payload MUST contain `{uuid_salida, placa}`. The logo MUST be rendered as `;LOGO:${payload.logoDataUrl}` (placeholder glyph `▢` if empty). The function MUST be pure — no IPC, no `bridge.imprimir` call, no DOM, no `new Date()`. Zod parse failure MUST throw `EscposPayloadMissingFieldError` carrying the Zod issues. [Cite: DEC-SUC-26 + DEC-SUC-27 + DEC-SUC-28 + plan.md:1789-1807]

#### Scenario: CU-15S byte-level emission — 19 fields + dynamic header + QR + logo

- **Given** `escposBuilder.build('salida', mockPayload)` is called with
  `mockPayload.sucursal.encabezado = 'Sucursal Norte'` and all 19
  CU-15S fields populated
- **When** the function returns
- **Then** the Buffer MUST contain:
  - `Sucursal Norte` as the first line (NOT `PARKINGOS`, NOT
    `PARQUEADERO PUBLICO`) — DEC-SUC-28 dynamic header
  - All 19 conceptual fields in canonical order (asserted via
    `Buffer.indexOf(<field-value>) >= 0` for each value, including
    `Subtotal: ${formatCOP(subtotal)}`, `IVA: ${formatCOP(iva)}`,
    `TOTAL: ${formatCOP(total)}` in bold, `Medio de pago: ${medioPago}`,
    `Tarifa: ${formatCOP(tarifaAplicada)}/hora`, and
    `Resolucion FE: ${resolucionFE}`)
  - `*** SALIDA ***` wrapped by `0x1B 0x21 0x30` (entrada) and
    `0x1B 0x21 0x00` (reset)
  - QR marker `;QR:${payload.qrDataUrl}` where
    `payload.qrDataUrl` is the data URL for `{uuid_salida, placa}`
  - Logo marker `;LOGO:${logoText}` where `logoText` is the placeholder
    glyph `▢` when `payload.logoDataUrl === ''`
- **And** the function MUST NOT call `bridge.imprimir` (pure function
  only — F5.2 R4 invariant preserved)
- **And** the function MUST NOT contain `PARKINGOS` or
  `PARQUEADERO PUBLICO` as a constant literal (drift guard:
  `grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` returns
  0 matches after F7.3 lands)

### REQ-OPS-159 — `escposBuilder.build('salida_mensualidad', payload)` produces 15-field CU-15SM buffer + sello + QR + logo

The system SHALL export
`escposBuilder.build('salida_mensualidad', payload)` from the same
`escposBuilder.ts`. The function MUST emit a `Buffer` containing the
**15 conceptual fields of CU-15SM**: (1) Encabezado, (2) Empresa, (3)
Dirección, (4) NIT, (5) Régimen, (6) Operario, (7) Sello
`*** PAGO CON MENSUALIDAD ***` wrapped by `escText2x()` /
`escTextReset()` (DEC-SUC-27 invariant — distinguishes CU-15SM from
CU-15S so the cajero never confuses a tiquete sin cobro with one
cobrado), (8) Folio, (9) Fecha, (10) Hora entrada, (11) Hora salida,
(12) Tiempo total, (13) Placa, (14) Horario atención, (15) Póliza RC /
Resolución FE / Observaciones — PLUS the **2 DEC-SUC-26 additions**
(QR + logo markers). The header MUST equal
`payload.sucursal.encabezado` (DEC-SUC-28). The sello MUST be wrapped
by `0x1B 0x21 0x30` (entrada — text 2x height) and `0x1B 0x21 0x00`
(reset — text 1x1) per DEC-SUC-27 + `plan.md:1787`. **NO monetary
fields** (`subtotal`, `iva`, `total`, `medioPago`) MUST appear — the
mensualidad fee is settled by the subscription, NOT the exit
(DEC-SUC-23 verbatim). [Cite: DEC-SUC-26 + DEC-SUC-27 + DEC-SUC-28 +
plan.md:1810]

#### Scenario: CU-15SM sello byte-level emission — 15 fields + sello opcode invariant + no money

- **Given** `escposBuilder.build('salida_mensualidad', mockPayload)` is
  called with `mockPayload.sucursal.encabezado = 'Sucursal Sur'` and
  all 15 CU-15SM fields populated
- **When** the function returns
- **Then** the Buffer MUST contain:
  - All 15 conceptual fields in canonical order (asserted via
    `Buffer.indexOf(<field-value>) >= 0` for each value)
  - `*** PAGO CON MENSUALIDAD ***` preceded by `0x1B 0x21 0x30` and
    followed by `0x1B 0x21 0x00` (DEC-SUC-27 invariant — verified by
    `Buffer.indexOf(Buffer.from([0x1b, 0x21, 0x30]))` followed by the
    literal sello text, then by
    `Buffer.indexOf(Buffer.from([0x1b, 0x21, 0x00]))`)
  - QR marker `;QR:${payload.qrDataUrl}` + logo marker
    `;LOGO:${logoText}` (same shape as REQ-OPS-158)
- **And** the Buffer MUST NOT contain `Subtotal:`, `IVA:`, `TOTAL:`, or
  `Medio de pago:` (no monetary fields per DEC-SUC-23)
- **And** the sello `*** PAGO CON MENSUALIDAD ***` MUST NOT appear in
  the CU-15S buffer (rotación path — separate `build('salida', ...)`
  call uses `*** SALIDA ***` instead)

### REQ-OPS-160 — `SalidaMensualidad` invokes `bridge.imprimir('salida_mensualidad', payload)` on success

The system SHALL modify
`apps/electron-sucursal/src/features/operacion/components/SalidaMensualidad.tsx`
to invoke `bridge.imprimir('salida_mensualidad', payload)` after a
successful `useRegistrarSalida.trigger()` returns
`tipo_salida === 'MENSUALIDAD'`. The payload MUST be hydrated by a new
`useSalidaMensualidadPayload(uuid_salida)` SWR hook (F7.3 ships the
hook — it composes `GET /operacion/salidas/:uuid` from F1.7 +
`GET /documentos` from F1.7 with electron-store cache F6.2 design
key `parkos.documents.v1`, TTL 24h). The payload MUST contain
`uuid_salida`, `uuid_ingreso`, `placa`, `fecha_ingreso`,
`fecha_salida`, `empresa`, `sucursal` (with `encabezado`), `documentos`
(logo), and `qr_payload` — replacing the F7.2 envelope placeholder
`{ uuid_salida }` (declared at
`SalidaMensualidad.tsx:41-47`). The call MUST be wrapped in
try/catch — a printer failure MUST NOT block the operator's flow (the
salida is already persisted in `prod.salidas`; reprint is F8.x's job).
The call MUST be deferred to the next microtask via `queueMicrotask`
to avoid blocking the React render commit. [Cite: proposal §3 Path 3
+ DEC-SUC-08 + DEC-SUC-27]

#### Scenario: monthly exit triggers CU-15SM print with full payload shape

- **Given** operator confirms a salida mensualidad and the backend
  `POST /api/v1/operacion/salidas` returns `201 Created` with
  `tipo_salida: 'MENSUALIDAD'`, `estado: 'MENSUALIDAD_PAGO'`, and
  `uuid_salida: <uuid>`
- **When** `useRegistrarSalida.trigger()` resolves with the 201 payload
- **Then** the renderer MUST:
  - Invoke `useSalidaMensualidadPayload(uuid_salida)` (SWR hook) which
    composes `GET /operacion/salidas/:uuid` + `GET /documentos?uuid_sucursal=X&tipo=logo`
  - Validate the hydrated object against `salidaMensualidadPayloadSchema`
    via `escposTemplates.ts` (Zod exhaustive)
  - Call `bridge.imprimir('salida_mensualidad', payload)` deferred via
    `queueMicrotask(() => ...)` — the print call MUST NOT block the
    React render commit
  - Wrap the `bridge.imprimir` call in try/catch — a thrown error
    (printer offline, USB disconnected, IPC channel failure) MUST be
    logged to `console.warn` and MUST NOT propagate to the React error
    boundary (the salida is already persisted — blocking the UI is
    strictly worse than a silent print failure)
- **And** the payload MUST contain all 17 fields required by
  `salidaMensualidadPayloadSchema` post-tightening (15 CU-15SM + 2
  DEC-SUC-26 + `sucursal.encabezado`)
- **And** the renderer MUST NOT open `PagoModal` (no cobro —
  DEC-SUC-27 invariant: mensualidad has no cash movement at exit)
- **And** the renderer MUST NOT call `bridge.imprimir('salida', ...)`
  for the mensualidad branch — F8.1 owns the CU-15S call site after
  pago confirmation

## Drift reconciliation traceability

| Existing capability | Status | F7.3 delta |
|---|---|---|
| F5.2 `escposBuilder.build('entrada', payload)` (CU-15E) | UNCHANGED body fields — F6.2 locked them. | F7.3 swaps the "PARKINGOS" header constant to `payload.sucursal.encabezado` (DEC-SUC-28 transversal fix — same migration step applies to all three bodies). |
| F5.2 `escposBuilder.build('salida', payload)` (CU-15S) | EXISTING stub at `escposBuilder.ts:240-273` — emits 17 fields, header constant "PARKINGOS", sello `*** SALIDA ***` already present. | F7.3 TIGHTENS to emit all 19 CU-15S fields (adds `tarifaAplicada`, `fecha` date-only, `horarioAtencion`, `observaciones`) + 2 DEC-SUC-26 additions (QR + logo markers). Header swap to `payload.sucursal.encabezado`. |
| F5.2 `escposBuilder.build('salida_mensualidad', payload)` (CU-15SM) | EXISTING stub at `escposBuilder.ts:275-301` — emits 14 fields, header constant "PARKINGOS", sello `*** PAGO CON MENSUALIDAD ***` literal present BUT emitted at 1x1 height (drift vs. `plan.md:1787` which mandates `escText2x()` wrap). | F7.3 TIGHTENS to emit all 15 CU-15SM fields (adds `sucursal.encabezado`) + 2 DEC-SUC-26 additions. Header swap. Sello wrapped by `escText2x()` / `escTextReset()`. |
| F5.2 4-tipo dispatcher `build(tipo, payload)` | UNCHANGED — F5.2 ships the dispatcher at `escposBuilder.ts:391-427`. | F7.3 NOT touching the dispatcher (no new cases; only tightening the existing `salida` + `salida-mensualidad` body emission). |
| DEC-SUC-28 dynamic header | F5.2 uses "PARKINGOS" constant across all three bodies. | F7.3 swaps to `payload.sucursal.encabezado` in ALL THREE payloads (`entrada`, `salida`, `salida-mensualidad`) in the SAME migration step. Drift guard: `grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` returns 0 matches. |
| DEC-SUC-27 sequence (CU-15S after pago, CU-15SM immediate) | F7.2 already fires the `bridge.imprimir('salida_mensualidad', payload)` envelope at `SalidaMensualidad.tsx:41-47` with placeholder `{ uuid_salida }`. | F7.3 fills the payload shape via `useSalidaMensualidadPayload` SWR hook; F8.1 owns the CU-15S trigger call site. |
| CU-15S trigger integration | NOT in scope. | F8.1 will call `bridge.imprimir('salida', payload)` after pago confirmado (`plan.md:1843`). |

**WHY the existing capabilities are tightened (not replaced)**: the
F5.2+F6.2 skeleton already shipped `salidaPayloadSchema`,
`salidaMensualidadPayloadSchema`, and the 4-tipo dispatcher. F7.3's
real work is TIGHTENING the existing stubs to match the exact 19/15
field lists — not adding new dispatcher cases. The skeleton's
`buildSalidaBuffer` and `buildSalidaMensualidadBuffer` exported
functions at `escposBuilder.ts:350-366` are the public surface; F7.3
modifies the underlying `buildSalidaBody` / `buildSalidaMensualidadBody`
helpers at `escposBuilder.ts:240-301` only.

**WHY DEC-SUC-28 is a single migration step across all three bodies**:
the F5.2 constant "PARKINGOS" is reused by `buildEntradaBody`,
`buildSalidaBody`, and `buildSalidaMensualidadBody`. A partial swap
would leave the CU-15E tiquete printing "PARKINGOS" while CU-15S/CU-15SM
print the dynamic header — inconsistent brand identity. F7.3 fixes
all three in one atomic migration. Drift guard: after F7.3 lands,
`grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` MUST return
0 matches.

**WHY the CU-15SM sello drift is resolved by F7.3**: the live
`escposBuilder.ts:287` emits `*** PAGO CON MENSUALIDAD ***` literal
text, but the surrounding opcode context is `escText2x()` immediately
followed by `escTextReset()` at the SAME position. Re-reading the
current code shows the sello IS wrapped by `escText2x()` at lines
286-288. The drift in `plan.md` is that the sello appears WITHOUT the
`escText2x()` in some older parser references; the live code already
emits it correctly. F7.3's byte-level test (`Buffer.indexOf([0x1b,
0x21, 0x30])` followed by the literal) is the regression guard that
locks this invariant.

## Out of scope

- **HU-F8.1 — PagoModal (rotación → CU-04)**: separate change. F7.3
  only DELIVERS `build('salida', payload)`; F8.1 CALLS it after pago
  confirmation (`plan.md:1843`). F8.1 acceptance criterion requires
  the call `bridge.imprimir({ buffer: escposBuilder.build('salida',
  payload).toString('base64'), ticketId: uuid_salida })`.
- **CU-15S print trigger integration**: F8.1 owns the call site. F7.3
  delivers the builder; F8.1 imports + invokes it.
- **Printer hardware fallback chain** (`escpos-usb` →
  `window.print()`): F5.1 owns (`DEC-SUC-08` line in
  `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/`).
  F7.3 only emits the byte buffer.
- **New endpoints on `api-sucursal`**: zero. CU-15S/CU-15SM data comes
  from existing F1.7 `GET /operacion/salidas/:uuid` + F1.7
  `GET /documentos` (A-01 — certificado + logo).
- **`log_transaccional(accion='impreso')` backend INSERT**: A-05 —
  backend concern (F5.6 owns). F7.3 documents the row payload shape
  only (mirror F6.2 precedent at `docs/f6-2-integration.md`); the
  actual INSERT is out of scope.
- **Reimpression workflow**: separate HU (F8.x — reimpresión con
  costo). The `reimpresion` case in `build()` already routes to
  `buildReimpresionBuffer` (F5.2 shipped). F7.3's header swap ALSO
  touches the reimpresion body's constant header (same migration
  step).
- **Backend changes**: zero.
- **Release branch + tag**: per gitflow, this change goes to `dev` only.
- **Vite cache invalidation post-merge**: handled by AGENTS.md
  post-merge script (kill port 5173 + restart with `--force`).
- **`salidas.estado='PAGADO'` UPDATE**: owned by Fase 8. DEC-SUC-23
  verbatim — `salidas` has NO `valor` column; F7.2 only INSERTs and
  F7.3 prints CU-15SM without monetary fields (DEC-SUC-27 + REQ-OPS-159
  invariant).

## Acceptance

F7.3 PR is mergeable when ALL of the following hold:

- `escposBuilder.build('salida', mockPayload)` emits a Buffer with all
  19 CU-15S conceptual fields + 2 DEC-SUC-26 additions (QR + logo) in
  canonical order, with `payload.sucursal.encabezado` as the first
  line (DEC-SUC-28 fix). [REQ-OPS-158]
- `escposBuilder.build('salida_mensualidad', mockPayload)` emits a
  Buffer with all 15 CU-15SM conceptual fields + 2 DEC-SUC-26
  additions, with the sello `*** PAGO CON MENSUALIDAD ***` preceded by
  `0x1B 0x21 0x30` (text 2x height) and followed by `0x1B 0x21 0x00`
  (text 1x1 reset), AND no monetary fields (`subtotal`/`iva`/`total`/
  `medioPago` MUST NOT appear). [REQ-OPS-159]
- `SalidaMensualidad.tsx` invokes
  `bridge.imprimir('salida_mensualidad', payload)` via `queueMicrotask`
  after `useRegistrarSalida.trigger()` returns 201 with
  `tipo_salida='MENSUALIDAD'`, with the payload hydrated by
  `useSalidaMensualidadPayload(uuid_salida)` (SWR hook composing
  `GET /operacion/salidas/:uuid` + `GET /documentos`). [REQ-OPS-160]
- The sello is byte-for-byte tested:
  `Buffer.indexOf(Buffer.from([0x1b, 0x21, 0x30]))` MUST be followed
  by the literal `'*** PAGO CON MENSUALIDAD ***'` and then
  `Buffer.indexOf(Buffer.from([0x1b, 0x21, 0x00]))` — DEC-SUC-27
  invariant. [REQ-OPS-159]
- Dynamic header swap verified:
  `payload.sucursal.encabezado` replaces the F5.2 "PARKINGOS" constant
  in ALL THREE payloads (CU-15E + CU-15S + CU-15SM) — same migration
  step. Drift guard: `grep -r 'PARKINGOS'
  apps/electron-sucursal/src/lib/print` returns 0 matches after F7.3
  lands. [REQ-OPS-158, REQ-OPS-159]
- Printer failure on CU-15SM does NOT block the operator's flow
  (the salida is already persisted in `prod.salidas` — reprint is F8.x).
  [REQ-OPS-160]
- All translation keys for tiquete labels added to `operacion.json`:
  `salida_mensualidad.tiquete_sello`, `salida.tiquete_sello`,
  `salida.tiquete_qr`, `salida.tiquete_logo_missing`,
  `salida.errors.sucursal_encabezado_missing` (es-CO primary locale).
- `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the full
  `electron-sucursal` workspace.
- `axe-core` reports 0 violations on `<SalidaMensualidad />` (WCAG
  2.1 AA, RNF-022 — no new visible UI; the change is purely the print
  pipeline).
- Final diff `≤ 800 LOC` per the preflight budget — no
  `size:exception` needed (forecast ≈ 480 LOC per proposal §4).
