# Proposal: HU-F7.3 — Tiquetes de salida (CU-15S) + salida-mensualidad (CU-15SM)

> **Change**: `fase-7-3-tiquetes-salida`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F7.3 (Fase 7 — Salida y cálculo de tarifa, tiquetes pivot)
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC/PR`, strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` (per AGENTS.md gitflow). No AI attribution in commits.
> **Inputs read**:
>   - `plan.md` lines 1779-1826 (F7.3 block + 19/15 field lists)
>   - `plan.md` lines 415-420 (DEC-SUC-26 — QR + logo beyond CU-15x literal)
>   - `plan.md` lines 421-425 (DEC-SUC-27 — sequence correction: CU-15S after pago, CU-15SM immediate)
>   - `plan.md` line 444 (DEC-SUC-29 — backoff tables; CU-15x uses escpos-impresora retry)
>   - `openspec/changes/archive/2026-09-17-fase-5-2-escpos-builder-fallback/` (F5.2 skeleton)
>   - `openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/` (F6.2 CU-15E precedent)
>   - `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/` (F7.2 baseline merged at `d157195`)
>   - `apps/electron-sucursal/src/lib/print/escposBuilder.ts:240-273` (live `buildSalidaBody` — emits 17 fields, NOT 19)
>   - `apps/electron-sucursal/src/lib/print/escposBuilder.ts:275-301` (live `buildSalidaMensualidadBody` — emits 14 fields, missing the `*** PAGO CON MENSUALIDAD ***` sello literal)
>   - `apps/electron-sucursal/src/lib/print/escposTemplates.ts:369-401` (live `salidaPayloadSchema` + `salidaMensualidadPayloadSchema` — both present in F5.2)
>   - `apps/electron-sucursal/src/features/operacion/components/SalidaMensualidad.tsx:41-47` (F7.2 fires `bridge.imprimir('salida_mensualidad', { uuid_salida })` envelope — needs full payload shape from F7.3)
>   - `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` (F5.2 byte-level fixtures)
> **Skills loaded**: `sdd-propose` (this phase), `_shared/sdd-phase-common` (Section B/C/D envelope).

## 1. Intent

HU-F7.3 closes the F7.2 → CU-04 pivot on the print-envelope layer: from a successful `POST /operacion/salidas` (F1.7), the renderer fires the typed `bridge.imprimir` envelope carrying the full `SalidaPayload` (CU-15S) or `SalidaMensualidadPayload` (CU-15SM). The pure renderer-side `escposBuilder.build('salida' | 'salida-mensualidad', payload)` function (F5.2 skeleton, **already shipped** with both cases wired to `buildSalidaBuffer` / `buildSalidaMensualidadBuffer` — see `escposBuilder.ts:350-366`) emits the exact byte stream that `bridge.imprimir` ships to `escpos-usb` (F5.1).

**Drift reconciliation** between `plan.md` F7.3 block and the merged `dev` branch:

1. **F5.2 already shipped `salida` and `salida-mensualidad` cases** in the `build()` dispatcher (verified `escposBuilder.ts:391-427`). F7.3's work is NOT "add new cases" — it is **tightening the body emission** of the existing stubs to match the EXACT 19/15 field lists of CU-15S/CU-15SM (current `buildSalidaBody` emits 17 fields, missing "Tarifa aplicada", "Fecha" (date-only), "Horario atención" and "Observaciones"; current `buildSalidaMensualidadBody` emits 14 fields and is missing the sello `*** PAGO CON MENSUALIDAD ***` literal that plan.md mandates as a CU-15SM visual distinguisher).
2. **DEC-SUC-28** requires the header to be **dinámico de sucursal**, NOT the corpus defect "PARQUEADERO PUBLICO" fixed string. The current `buildSalidaBody` / `buildSalidaMensualidadBody` emit "PARKINGOS" as a constant (F6.2 inherited this from F5.2). F7.3 swaps the constant for `payload.sucursal.encabezado` (new field on the payload schemas).
3. **DEC-SUC-27** sequence correction: CU-15S prints **AFTER pago confirmation** (Fase 8 HU-F8.1). F7.3 only DELIVERS `build('salida', payload)` — F8.1 is the call site. CU-15SM prints IMMEDIATELY at salida mensualidad (Fase 7) — F7.2 already fires the envelope (`SalidaMensualidad.tsx:41-47`); F7.3 fills the payload shape.
4. **DEC-SUC-26** transversal: both tiquetes must include QR + logo (DEC-SUC-26 explicitly notes that CU-15S/CU-15SM literal field lists do NOT include QR + logo, but they are required anyway). F7.3 adds the `;QR:` + `;LOGO:` markers + placeholder glyph to both bodies (F6.2 precedent at `escposBuilder.ts:230-234`).

The user-facing payoff: from a confirmed salida (rotación or mensualidad), the operator hands the customer a printed tiquete that is final at emission (DEC-SUC-27 — no reprint gating on a cloud round-trip), with QR for traceability and logo for brand identity.

## 2. Scope

### 2.1 In scope (T1..T3 + I1)

- **T1 — `buildSalidaBody` tightening** (UPDATE `escposBuilder.ts:240-273`): emit the EXACT 19 conceptual fields of CU-15S per `plan.md:1789-1807` in the canonical order. Add the 2 missing fields (tarifa aplicada, fecha operación as date-only, horario atención, observaciones) and the 2 DEC-SUC-26 additions (QR + logo markers). Replace the "PARKINGOS" header constant with `payload.sucursal.encabezado` (DEC-SUC-28). Keep the sello "*** SALIDA ***" (NOT "TIQUETE DE SALIDA" — `plan.md:1787` notes the corpus has both but the sello is the visual anchor, DEC-SUC-27 invariant: sello is "*** SALIDA ***" for rotación, "*** PAGO CON MENSUALIDAD ***" for mensualidad).
- **T2 — `buildSalidaMensualidadBody` sello + tightening** (UPDATE `escposBuilder.ts:275-301`): add the sello `*** PAGO CON MENSUALIDAD ***` (literal text) wrapped by `escText2x()` (`0x1B 0x21 0x30`) — DEC-SUC-27 invariant, the visual distinguisher that prevents the cajero from confusing a tiquete sin cobro with one cobrado. Emit the EXACT 15 conceptual fields of CU-15SM (mismo patrón que CU-15E sin desglose de cobro). Add the 2 DEC-SUC-26 additions (QR + logo). Replace "PARKINGOS" header with `payload.sucursal.encabezado` (DEC-SUC-28).
- **T3 — Payload schemas tightening** (UPDATE `escposTemplates.ts:369-401`): add `sucursal.encabezado: string` (DEC-SUC-28 dynamic header source), `tarifaAplicada: number` on `salidaPayloadSchema` (CU-15S field 9, currently absent), `horarioAtencion: string` on both schemas (CU-15S field 19 part a, CU-15SM field 14 part a), `observaciones: string.optional()` on `salidaPayloadSchema` (CU-15S field 19 part d). Add `qrDataUrl: string` + `logoDataUrl: string` as REQUIRED on `salidaPayloadSchema` (DEC-SUC-26) — currently F5.2 shipped them only on `salidaMensualidadPayloadSchema` as `.optional()`.
- **I1 — `SalidaMensualidad.tsx` full payload wiring** (UPDATE `apps/electron-sucursal/src/features/operacion/components/SalidaMensualidad.tsx`): replace the F7.2 envelope `{ uuid_salida }` with the full `SalidaMensualidadPayload` object. F7.3 ships the `useSalidaMensualidadPayload(uuid_salida)` hook that hydrates the payload from the F1.7 `GET /operacion/salidas/:uuid` response (F2.x canonical, no new endpoint) + the F1.7 documents fetch (cached per F6.2 design §"Caller-side cache"). Hook returns the typed payload + the `bridge.imprimir` envelope shape. F7.2's typed event stays unchanged at the boundary; only the payload shape fills in.

### 2.2 Out of scope

- **HU-F8.1 — PagoModal (rotación → CU-04)**: separate change. F7.3 only DELIVERS `build('salida', payload)`; F8.1 CALLS it after pago confirmation (`plan.md:1843` — "Given el pago confirmado, Then se dispara la impresión del tiquete de salida (CU-15S, HU-F7.3)"). F7.3 acceptance criterion R1 in §6 depends on F8.1 consuming the builder.
- **CU-15S print trigger integration**: F8.1 owns the call site. F7.3 delivers the builder; F8.1 imports + invokes it.
- **Printer hardware fallback chain** (`escpos-usb` → `window.print()`): F5.1 owns (`DEC-SUC-08` line `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/`). F7.3 only emits the byte buffer.
- **New endpoints on `api-sucursal`**: zero. CU-15S/CU-15SM data comes from existing F1.7 `GET /operacion/salidas/:uuid` (F2.x canonical) + F1.7 `GET /documentos` (A-01 — certificado + logo).
- **`log_transaccional(accion='impreso')` backend INSERT**: A-05 — backend concern (F5.6 owns). F7.3 documents the row payload shape only (mirror F6.2 precedent at `docs/f6-2-integration.md`); the actual INSERT is out of scope.
- **Reimpression workflow**: separate HU (F8.x — reimpresión con costo). The `reimpresion` case in `build()` already routes to `buildReimpresionBuffer` (F5.2 shipped).
- **Backend changes**: zero.
- **Release branch + tag**: per gitflow, this change goes to `dev` only.
- **Vite cache invalidation post-merge**: handled by AGENTS.md post-merge script.

## 3. Approach

### 3.1 Decision Path 1 — Tighten existing stubs (no new cases)

The F5.2 + F6.2 skeleton ALREADY ships `salidaPayloadSchema` + `salidaMensualidadPayloadSchema` (`escposTemplates.ts:369-401`) and the dispatcher routes to all 4 cases (`escposBuilder.ts:391-427`). F7.3's work is to refine the BODY emission of the existing `buildSalidaBody` and `buildSalidaMensualidadBody` stubs to match the EXACT 19/15 conceptual field lists of CU-15S/CU-15SM. No new file, no new module — strict extension of the F5.2 + F6.2 invariants:

- Purity preserved (no DOM, no IPC, no `window.print()` — F5.2 R4).
- The 4-tipo dispatcher (`build(tipo, payload)`) is unchanged.
- `formatCOP` reuse (DEC-SUC-07 inline copy, F5.2 R2).
- ISO 8601 timestamps passed through verbatim (F5.2 R4 — no implicit `new Date()`).

### 3.2 Decision Path 2 — `sucursal.encabezado` on the payload (DEC-SUC-28 fix)

DEC-SUC-28 requires the header to be dinámico de sucursal, NOT the corpus defect "PARQUEADERO PUBLICO" fixed string. F7.3 adds `sucursal: { encabezado: string, ... }` to both payload schemas; the builder reads `payload.sucursal.encabezado` instead of the "PARKINGOS" constant. The header becomes the FIRST line of the tiquete body. The constant fallback `'PARKINGOS'` is removed — if the caller omits `sucursal.encabezado`, Zod rejects with `EscposPayloadMissingFieldError`.

Alternative rejected: read `sucursal.encabezado` from a separate global store — couples the pure builder to the renderer's state, breaks F5.2 R4 purity.

### 3.3 Decision Path 3 — Sello `*** PAGO CON MENSUALIDAD ***` with `0x1B 0x21 0x30` (DEC-SUC-27 invariant)

CU-15SM carries a sello distinct from CU-15S. The sello is:

```
0x1B 0x21 0x30    ← escText2x() (text 2x height)
'*** PAGO CON MENSUALIDAD ***\n'
0x1B 0x21 0x00    ← escTextReset() (text 1x1 reset)
```

The bytes are emitted by `buildSalidaMensualidadBody` (T2). The unit test asserts `Buffer.indexOf(Buffer.from([0x1b, 0x21, 0x30]))` is followed by the literal string `'*** PAGO CON MENSUALIDAD ***'`. CU-15S uses the sello `*** SALIDA ***` (DEC-SUC-27 verbatim, the corpus defect that CU original dice "TIQUETE DE SALIDA" for both is corrected here — `plan.md:1787` ratifies the sello distinction).

### 3.4 Decision Path 4 — QR + logo via `documentos` (DEC-SUC-26, A-01 reuse)

CU-15S and CU-15SM both include QR (`parkos://salida/<uuid_salida>?placa=<placa>`) and logo (base64 PNG from `GET /documentos?uuid_sucursal=X&tipo=logo`). F7.3 emits the same `;QR:` + `;LOGO:` text markers as `buildEntradaBody` (F6.2 precedent at `escposBuilder.ts:230-234`). The QR rasterization is the caller's responsibility (F5.2 R4 purity). The logo empty-string fallback renders the placeholder glyph `▢` (F6.2 precedent). Payload schemas tighten `qrDataUrl` + `logoDataUrl` to REQUIRED on `salidaPayloadSchema` (currently `.optional()`).

### 3.5 Drift Reconciliation — Skeleton vs F7.3 final shape

| Aspect | F5.2/F6.2 skeleton (live on dev) | F7.3 final shape |
|---|---|---|
| `salidaPayloadSchema` | 16 fields (no `tarifaAplicada`, no `horarioAtencion`, no `observaciones`; `qrDataUrl`+`logoDataUrl` `.optional()`) | 21 fields (add `tarifaAplicada`, `horarioAtencion`, `observaciones`, `sucursal.encabezado`; tighten `qrDataUrl`+`logoDataUrl` to required) |
| `salidaMensualidadPayloadSchema` | 14 fields (no `sucursal.encabezado`; `qrDataUrl`+`logoDataUrl` `.optional()`) | 17 fields (add `sucursal.encabezado`; tighten `qrDataUrl`+`logoDataUrl` to required) |
| `buildSalidaBody` body emission | 17 conceptual fields; header constant "PARKINGOS"; sello "*** SALIDA ***" | 21 conceptual fields (19 CU-15S + 2 DEC-SUC-26); header `payload.sucursal.encabezado` (DEC-SUC-28); sello "*** SALIDA ***" preserved; QR + logo markers added |
| `buildSalidaMensualidadBody` body emission | 14 conceptual fields; header constant "PARKINGOS"; NO sello | 17 conceptual fields (15 CU-15SM + 2 DEC-SUC-26); header `payload.sucursal.encabezado` (DEC-SUC-28); sello "*** PAGO CON MENSUALIDAD ***" with `escText2x`/`escTextReset` wrap added; QR + logo markers added |
| SalidaMensualidad.tsx envelope | `{ uuid_salida }` (F7.2 typed event placeholder) | full `SalidaMensualidadPayload` (F7.3 fills the shape via `useSalidaMensualidadPayload`) |
| CU-15S trigger | F8.1 owns (HU-F8.1 PagoModal — separate change) | F8.1 CALLS `bridge.imprimir({ buffer: build('salida', payload).toString('base64') })` after pago confirmado |

## 4. Affected files

| File | Action | LOC est. | Notes |
|---|---|---|---|
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | UPDATE | +60 (delta) | Tighten `buildSalidaBody` (T1: +30 LOC for the 4 missing fields + QR + logo + header swap) and `buildSalidaMensualidadBody` (T2: +30 LOC for the sello wrap + QR + logo + header swap). Dispatcher unchanged. |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | UPDATE | +25 (delta) | Add `sucursal.encabezado` to both schemas (T3); add `tarifaAplicada`/`horarioAtencion`/`observaciones` to `salidaPayloadSchema`; tighten `qrDataUrl`+`logoDataUrl` to required on `salidaPayloadSchema`. |
| `apps/electron-sucursal/src/features/operacion/components/SalidaMensualidad.tsx` | UPDATE | +15 (delta) | Wire `useSalidaMensualidadPayload()` (I1) to fill the full payload before `bridge.imprimir('salida_mensualidad', payload)`. F7.2 envelope shape expands from `{ uuid_salida }` to `SalidaMensualidadPayload`. |
| `apps/electron-sucursal/src/features/operacion/hooks/useSalidaMensualidadPayload.ts` | NEW | 50 | SWR hook that hydrates `SalidaMensualidadPayload` from `GET /operacion/salidas/:uuid` (F1.7) + `GET /documentos` (F1.7, electron-store cache F6.2 design). Returns `{ payload, error, isLoading }`. Mirror F6.1 `useIngresoActivo` pattern. |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida.test.ts` | NEW | 100 | 19-byte-presence scenarios for CU-15S (mirror F6.2 `escposBuilder.entrada.test.ts` precedent at `__tests__/escposBuilder.entrada.test.ts:100+`). Each scenario asserts `Buffer.indexOf(<campo>) >= 0` for the value emitted. Plus sello "*** SALIDA ***" presence + QR + logo markers. |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.salida_mensualidad.test.ts` | NEW | 80 | 15-byte-presence scenarios for CU-15SM. CRITICAL: asserts `Buffer.indexOf([0x1b, 0x21, 0x30])` is followed by `'*** PAGO CON MENSUALIDAD ***'` (DEC-SUC-27 invariant). Plus QR + logo markers + dynamic header (NOT "PARKINGOS"). |
| `apps/electron-sucursal/src/features/operacion/hooks/__tests__/useSalidaMensualidadPayload.test.ts` | NEW | 70 | 4 scenarios: success path, documents cache hit, documents cache miss (404), Zod rejection when `sucursal.encabezado` missing. Mirror F6.1 hook test pattern. |
| `apps/electron-sucursal/e2e/salida-tiquete.spec.ts` | NEW | 80 | 3 scenarios: (a) salida rotación → F8.1 stub triggers `build('salida', payload)` (mocked bridge.imprimir spy), (b) salida mensualidad → SalidaMensualidad fires `build('salida_mensualidad', payload)` immediately, (c) printer disconnected → F5.1 fallback chain still produces valid buffer (F5.1 owner — F7.3 only asserts no crash). Playwright + axe-core WCAG gate. |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | UPDATE | +5 keys (delta) | `salida_mensualidad.tiquete_sello`, `salida.tiquete_sello`, `salida.tiquete_qr`, `salida.tiquete_logo_missing`, `salida.errors.sucursal_encabezado_missing`. Locale es-CO primary. |
| **Total new LOC** | | **+380** | Within 800 LOC budget; no `size:exception` needed. |
| **Total updated LOC (deltas)** | | **+100** | |
| **Grand total LOC** | | **~480** | |

## 5. Dependencies

### 5.1 Already-merged prerequisites (verified on `dev` at `d157195`)

- **F7.2 — `SalidaMensualidad` + `useRegistrarSalida`** (merged 2026-09-19, `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/`): ships the typed `bridge.imprimir('salida_mensualidad', payload)` envelope event. **Required** — F7.3 fills the payload shape.
- **F5.2 — `escposBuilder` skeleton** (merged, `openspec/changes/archive/2026-09-17-fase-5-2-escpos-builder-fallback/`): ships the 4-tipo dispatcher + the 9 ESC/POS opcodes + the 2 named error classes + `salidaPayloadSchema` + `salidaMensualidadPayloadSchema` + `buildSalidaBuffer` + `buildSalidaMensualidadBuffer`. **Required** — F7.3 tightens the body emission of these stubs.
- **F5.1 — `bridge.imprimir` IPC + `escpos-usb` driver** (merged, `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/`): ships the IPC channel + escpos-usb + window.print() fallback. **Required** — F7.3 only emits the byte buffer.
- **F6.2 — CU-15E precedent** (merged, `openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/`): ships `buildEntradaBuffer` + 17-field `TiqueteEntradaCampos` + `buildEntradaPayload` factory + QR + logo emission pattern. **Required** — F7.3 mirrors the byte-presence test pattern + the QR/logo text markers + the placeholder glyph.
- **F1.7 — `GET /operacion/salidas/:uuid` + `GET /documentos`** (merged): the canonical endpoints for hydrating `SalidaMensualidadPayload`. **Required** — F7.3's `useSalidaMensualidadPayload` hook reads from these.
- **F2.x — `parkosFetch` + `useAuthStore`** (merged): the canonical HTTP client + auth store. **Required** — `useSalidaMensualidadPayload` composes both.

### 5.2 Forward-dependents (do NOT block F7.3)

- **HU-F8.1 — PagoModal**: consumes F7.3's `build('salida', payload)` after pago confirmado (CU-04 BR1, `plan.md:1843`). F8.1 acceptance criterion requires the call `bridge.imprimir({ buffer: escposBuilder.build('salida', payload).toString('base64'), ticketId: uuid_salida })`. F7.3 only DELIVERS the builder; F8.1 CALLS it.
- **HU-F5.6 — Backend `log_transaccional(accion='impreso')`**: the backend INSERT that records the print state row per A-05. F7.3 documents the row payload shape (mirror F6.2 `docs/f6-2-integration.md`); the actual INSERT is out of scope.

### 5.3 Skill + tooling prerequisites

- `react` skill (loaded by parent) — D-073 stack, Vite 5, shadcn/ui único, RHF + Zod, i18next es-CO, WCAG 2.1 AA via axe-core.
- `python` skill (loaded by parent for backend reading) — FastAPI/Pydantic/SQLAlchemy 2.0 async conventions, but F7.3 ships no backend code.

## 6. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **CU-15S print trigger lives in F8.1** — if F8.1 ships without integrating F7.3's builder, tiquete won't print. The operator hands the customer nothing. | MED | (a) F8.1 acceptance criterion (R-8.1-AC-7) requires `bridge.imprimir(escposBuilder.build('salida', payload))`. (b) F7.3's `escposBuilder.salida.test.ts` is a unit-level guarantee that the buffer is byte-correct; F8.1's e2e covers the integration. (c) Drift guard `tests/static/test_salida_handler_uses_builder.py` asserts `grep -r 'escposBuilder.build(.salida.' apps/electron-sucursal/src/features/caja` (F8.1 location) returns ≥1 match. |
| **R2** | **19 vs 15 field count drift** — corpus has 19 for CU-15S literal, but DEC-SUC-26 adds QR+logo as separate fields, bringing CU-15S total to 21. CU-15SM has 15 literal + 2 DEC-SUC-26 = 17. Off-by-one errors in the body emission will silently mis-render. | LOW | (a) Proposal §4 file table pins the EXACT 19 + 2 / 15 + 2 field lists verbatim from `plan.md:1789-1807, 1810`. (b) `escposBuilder.salida.test.ts` enforces 21 byte-presence scenarios (one per field). (c) `escposBuilder.salida_mensualidad.test.ts` enforces 17 byte-presence scenarios. (d) The mapped-type exhaustiveness pattern from F6.2 (`TiqueteEntradaCampos` at `escposTemplates.ts:196-214`) extends to `TiqueteSalidaCampos` (21 keys) + `TiqueteSalidaMensualidadCampos` (17 keys); removing a key fails `tsc --noEmit`. |
| **R3** | **Sello `*** PAGO CON MENSUALIDAD ***` bytes `0x1B 0x21 0x30` may not render on all printers** — the opcode is standard ESC/POS but older printers may ignore it. | LOW | (a) `escposBuilder.salida_mensualidad.test.ts` asserts the bytes are emitted (the builder's job). Printer behavior is hardware-specific and F5.1 owns the fallback chain. (b) The sello text is also wrapped by `escBoldOn`/`escBoldOff` for redundancy across printer firmware generations. |
| **R4** | **Logo fetch network failure** — if `GET /documentos?uuid_sucursal=X&tipo=logo` returns 404 or the cache is cold, the tiquete must still print. | MED | (a) F6.2 design precedent: empty `logoDataUrl` renders the placeholder glyph `▢` (DEC-SUC-08). (b) `useSalidaMensualidadPayload` falls back to `logoDataUrl: ''` on 404 — verified by `useSalidaMensualidadPayload.test.ts` scenario "documents cache miss". (c) Electron-store cache key `parkos.documents.v1` (F6.2 design) holds the last good fetch for 24h TTL. (d) DEC-SUC-26 explicit: "logo is añadir" — not strictly required by CU-15x. |
| **R5** | **DEC-SUC-28 header swap breaks existing CU-15E callers** — `buildEntradaBuffer` currently emits the "PARKINGOS" constant. If F7.3 swaps both bodies to read `payload.sucursal.encabezado`, F6.2's `EntradaPayload` schema lacks the field and the build fails. | MED | (a) F7.3 adds `sucursal.encabezado` to ALL THREE payloads (`entrada`, `salida`, `salida-mensualidad`) in the SAME migration step. (b) F6.2's `buildEntradaPayload` factory is updated to set `sucursal.encabezado` from the same `SucursalForPayload` (just adds the new field). (c) `entradaPayloadSchema` test in `escposBuilder.entrada.test.ts` is extended with the new field presence scenario. (d) Drift guard: `grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` returns 0 matches after F7.3 lands. |
| **R-DRIFT** | **`plan.md` F7.3 block references "PAGO CON MENSUALIDAD" sello as `*** PAGO CON MENSUALIDAD ***`** (plan.md:1787 verbatim), but the current `buildSalidaMensualidadBody` emits the sello text WITHOUT the `escText2x` wrap — the sello is the same height as the rest of the body. | LOW | (a) Drift reconciled explicitly in §1 + §3.3. (b) `escposBuilder.salida_mensualidad.test.ts` asserts the `0x1B 0x21 0x30` opcode PRECEDES the sello literal. (c) Drift documented in `apply-progress.md` as known spec-vs-code mismatch resolved by F7.3. |

## 7. Open decisions to ratify

Two open decisions require user ratification before `sdd-spec` locks them.

### OD-1 — Sello "*** PAGO CON MENSUALIDAD ***" en CU-15S cuando la salida es por mensualidad Y el cliente eligió FE con datos propios?

**Proposal**: **NO** — el sello SOLO aparece en CU-15SM (sin cobro). CU-15S es para salidas con cobro (rotación); su sello es "*** SALIDA ***" (DEC-SUC-27 invariant). Si el cliente eligió FE con datos propios en una salida por mensualidad, la transacción es no-cobro y se imprime CU-15SM (no CU-15S).

**Alternatives**: (a) SÍ — el sello distingue CU-15S-mensualidad-de-CU-15S-rotación. (b) SÍ pero con texto distinto: "*** MENSUALIDAD FACTURADA ***".

**Ratification needed**: confirmar NO (DEC-SUC-27 + plan.md:1787 son literales al respecto).

### OD-2 — ¿Logo debe aparecer también en CU-15SM?

**Proposal**: **SÍ** — mismo formato que CU-15S (DEC-SUC-26 transversal — "logo en todo tiquete"). El placeholder glyph `▢` se renderiza si el cache está frío o si `GET /documentos?uuid_sucursal=X&tipo=logo` retorna 404.

**Alternatives**: (a) NO — el tiquete de mensualidad es más simple, sin logo. (b) Logo solo si el cliente lo pidió explícitamente.

**Ratification needed**: confirmar SÍ (DEC-SUC-26 ya lo dice transversalmente — la política de marca exige logo en todo tiquete).

## 8. PR shape

### 8.1 Single PR topology

| Field | Value |
|---|---|
| Branch | `feature/hu-f7-3-tiquetes-salida` |
| Target | `dev` (gitflow — NEVER `main`) |
| Work units | T1, T2, T3 + I1 (4 commits) |
| Commit strategy | `work-unit-commits` skill — each T/I is a separate reviewable commit |
| Conventional Commits | strict (no `Co-authored-by` AI trailers per AGENTS.md canon) |
| LOC budget | 800 lines per PR; F7.3 forecast = ~480 LOC |
| `size:exception` required | No (under 800 LOC threshold) |
| Chained PRs | No (single PR, all commits to `feature/hu-f7-3-...` → `dev`) |

### 8.2 Commit plan (work-unit-commits skill)

Each commit MUST compile + pass all tests independently (strict TDD).

| # | Commit | Type | Scope | Files | TDD phase |
|---|---|---|---|---|---|
| 1 | `feat(print): salidaPayloadSchema adds tarifaAplicada + horarioAtencion + observaciones + sucursal.encabezado + required qr/logo (DEC-SUC-26, DEC-SUC-28)` | feat | print | UPDATE escposTemplates.ts, UPDATE escposTemplates.test.ts | RED (5 schema rejection tests fail) → GREEN |
| 2 | `feat(print): buildSalidaBuffer emits 21 conceptual fields (19 CU-15S + QR + logo) with dynamic sucursal header` | feat | print | UPDATE escposBuilder.ts, NEW escposBuilder.salida.test.ts (21 byte-presence scenarios) | RED (21 tests fail) → GREEN |
| 3 | `feat(print): buildSalidaMensualidadBuffer emits 17 fields (15 CU-15SM + QR + logo) with *** PAGO CON MENSUALIDAD *** sello` | feat | print | UPDATE escposBuilder.ts, NEW escposBuilder.salida_mensualidad.test.ts (17 byte-presence scenarios + sello opcode assertion) | RED (18 tests fail) → GREEN |
| 4 | `feat(operacion): useSalidaMensualidadPayload SWR hook + SalidaMensualidad full payload wiring` | feat | operacion | NEW useSalidaMensualidadPayload.ts, NEW useSalidaMensualidadPayload.test.ts, UPDATE SalidaMensualidad.tsx (+15 delta), UPDATE operacion.json (+5 keys), NEW e2e/salida-tiquete.spec.ts | RED (4 hook tests + 3 e2e scenarios fail) → GREEN |
| 5 | `refactor(print): buildEntradaBuffer consumes sucursal.encabezado (DEC-SUC-28 transversal fix)` | refactor | print | UPDATE escposBuilder.ts, UPDATE escposTemplates.ts (buildEntradaPayload factory), UPDATE escposBuilder.entrada.test.ts (+1 header scenario) | RED (existing tests fail on header absence) → GREEN |
| 6 | `docs(sdd): F7.3 spec delta REQ-OPS-158..160 in operations/spec.md` | docs | sdd | UPDATE openspec/changes/fase-7-3-tiquetes-salida/specs/operations/spec.md, UPDATE openspec/specs/operations/spec.md | Spec sync |

### 8.3 PR title + body

- **Title**: `feat(print): HU-F7.3 tiquetes salida CU-15S + CU-15SM con QR + logo + dynamic header (DEC-SUC-26, DEC-SUC-27, DEC-SUC-28)`
- **Body**: Conventional Commits footer with `Refs: HU-F7.3`, `Refs: REQ-OPS-158..160`, `Closes: plan.md:1779-1826`. Bullet list of the 6 T/I/E work units. Drift reconciliation note (§3.5) inline. Rollback plan: revert the single branch (`feature/hu-f7-3-...` → `dev`), no DB migration, no backend change. The 4 commits are atomic per work-unit (revertible individually via `git revert <sha>` without breaking the build).

### 8.4 Verification gate (pre-merge)

- [ ] `git diff dev..feature/hu-f7-3-...` ≤ 800 LOC
- [ ] `pnpm --filter electron-sucursal lint` exits 0
- [ ] `pnpm --filter electron-sucursal typecheck` exits 0 (incl. `tsc --strict` exhaustiveness on the 3 mapped-type field sets)
- [ ] `pnpm --filter electron-sucursal test:coverage` exits 0 with per-file thresholds met for `escposBuilder.ts`, `escposTemplates.ts`, `useSalidaMensualidadPayload.ts`
- [ ] `pnpm --filter electron-sucursal e2e -- salida-tiquete.spec.ts` exits 0 with 3 scenarios passing
- [ ] Drift guard: `grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` returns 0 matches (DEC-SUC-28 fix verification)
- [ ] Drift guard: `grep -r '0x1B 0x21 0x30' apps/electron-sucursal/src/lib/print/__tests__` returns ≥2 matches (CU-15SM sello + CU-15E sello both present)
- [ ] `gh pr merge --squash --body-file` produces a squash commit with no `Co-authored-by` AI trailer

### 8.5 Post-merge (per AGENTS.md gitflow + override rule 2026-09-17)

1. `git checkout dev` + `git merge --ff-only feature/hu-f7-3-tiquetes-salida` (or `--no-ff` if not direct descendant).
2. `git push origin dev`.
3. `git branch -d feature/hu-f7-3-tiquetes-salida` + `git push origin --delete feature/hu-f7-3-tiquetes-salida`.
4. Vite cache invalidation: kill port 5173 + restart with `--force` per AGENTS.md.
5. Engram `mem_save` of the canonical `buildSalidaBuffer` + `buildSalidaMensualidadBuffer` + `useSalidaMensualidadPayload` decisions (post-merge convention).
6. F8.1 developer notification: the builder is now available at `escposBuilder.build('salida', payload)` and must be integrated into PagoModal's `onConfirmado` callback.

## 9. Success criteria

1. `escposBuilder.build('salida', mockPayload)` returns a `Buffer` containing all 21 conceptual fields (19 CU-15S + 2 DEC-SUC-26) in canonical order, with `payload.sucursal.encabezado` as the first line (DEC-SUC-28 fix).
2. `escposBuilder.build('salida_mensualidad', mockPayload)` returns a `Buffer` containing all 17 conceptual fields (15 CU-15SM + 2 DEC-SUC-26) in canonical order, with the sello `*** PAGO CON MENSUALIDAD ***` preceded by the `0x1B 0x21 0x30` opcode and followed by `0x1B 0x21 0x00` (text size reset).
3. `escposBuilder.build('entrada', mockPayload)` (F6.2 invariant preserved) continues to emit the 17 conceptual fields of CU-15E with `payload.sucursal.encabezado` as the first line.
4. `useSalidaMensualidadPayload(uuid_salida)` returns a valid `SalidaMensualidadPayload` that passes `salidaMensualidadPayloadSchema.parse()` (Zod exhaustive).
5. `SalidaMensualidad.tsx` calls `bridge.imprimir('salida_mensualidad', payload)` with the full payload (not the F7.2 envelope placeholder `{ uuid_salida }`) after successful salida mensualidad.
6. `e2e/salida-tiquete.spec.ts` passes 3 scenarios: rotación (mocked F8.1 trigger), mensualidad (immediate print envelope), printer disconnected (F5.1 fallback chain still produces valid buffer).
7. Drift guards pass: `grep -r 'PARKINGOS' apps/electron-sucursal/src/lib/print` returns 0 matches.
8. WCAG 2.1 AA: axe-core reports 0 violations on `<SalidaMensualidad />` (no new visible UI; the change is purely the print pipeline).
9. `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the full `electron-sucursal` workspace.
10. The mapped-type exhaustiveness check on `TiqueteSalidaCampos` (21 keys) and `TiqueteSalidaMensualidadCampos` (17 keys) fails `tsc --noEmit` if any key is renamed or removed (mirror F6.2 `TiqueteEntradaCampos` invariant).

## 10. Out of scope (re-iterated for emphasis)

- HU-F8.1 — PagoModal (separate change). F8.1 CALLS `build('salida', payload)`.
- CU-15S print trigger integration — F8.1 owns the call site.
- Printer hardware fallback chain (`escpos-usb` → `window.print()`) — F5.1 owns.
- New endpoints on `api-sucursal` — none needed (F1.7 + F2.x canonical).
- `log_transaccional(accion='impreso')` backend INSERT — F5.6 owns (A-05).
- Reimpression workflow — F8.x separate change.
- Backend changes — zero.
- Release branch + tag — post-merge operational, not PR scope.
- Vite cache invalidation post-merge — handled by AGENTS.md script.

## 11. Relevant files (canonical pointers)

**OpenSpec / plan / spec**:
- `openspec/changes/fase-7-3-tiquetes-salida/proposal.md` (this file)
- `openspec/changes/fase-7-3-tiquetes-salida/exploration.md` (sdd-explore phase, future — skipped, proposal absorbed context)
- `openspec/changes/fase-7-3-tiquetes-salida/specs/operations/spec.md` (sdd-spec delta, REQ-OPS-158..160)
- `openspec/changes/fase-7-3-tiquetes-salida/design.md` (sdd-design phase, future)
- `openspec/changes/fase-7-3-tiquetes-salida/tasks.md` (sdd-tasks phase, future)
- `openspec/changes/fase-7-3-tiquetes-salida/apply-progress.md` (sdd-apply phase, future)
- `openspec/changes/fase-7-3-tiquetes-salida/verify-report.md` (sdd-verify phase, future)
- `plan.md` lines 1779-1826 (F7.3 block + 19/15 field lists + DEC-SUC-26/27/28 invariants)
- `openspec/specs/operations/spec.md` (F7.2 REQ-OPS-152..157 baseline — F7.3 extends with REQ-OPS-158..160)

**Archive precedents**:
- `openspec/changes/archive/2026-09-17-fase-5-1-printer-service/{proposal,design,tasks,verify-report}.md` (F5.1 bridge.imprimir IPC)
- `openspec/changes/archive/2026-09-17-fase-5-2-escpos-builder-fallback/{proposal,design,tasks,verify-report}.md` (F5.2 escposBuilder skeleton)
- `openspec/changes/archive/2026-09-17-fase-6-2-tiquete-entrada/{proposal,design,tasks,verify-report}.md` (F6.2 CU-15E — exact precedent for byte-presence tests + QR/logo emission)
- `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/{proposal,design,tasks,verify-report}.md` (F7.2 baseline merged)

**Frontend source (live on `dev` at `d157195`)**:
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (F5.2+F6.2 skeleton — targets of T1+T2 tightening)
- `apps/electron-sucursal/src/lib/print/escposTemplates.ts` (F5.2+F6.2 schemas — targets of T3 tightening)
- `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` (F5.2 fallback — out of scope for F7.3)
- `apps/electron-sucursal/src/features/operacion/components/SalidaMensualidad.tsx:41-47` (F7.2 envelope — target of I1 wiring)
- `apps/electron-sucursal/src/features/operacion/hooks/useRegistrarSalida.ts` (F7.2 hook — provides `result.uuid_salida` consumed by `useSalidaMensualidadPayload`)
- `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts:100+` (F6.2 byte-presence test pattern — F7.3 mirrors verbatim)

**Files NOT touched (deliberate)**:
- `apps/electron-sucursal/src/main/services/*` (does not exist; the F5.1/F5.2 archive proposal referenced `main/services/printer.ts` and `main/services/escposBuilder.ts` but the actual shipped location is `src/lib/print/` — F5.2 drift guard verified)
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts::build()` dispatcher (unchanged — F5.2 ships the 4-tipo dispatcher)
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts::isTiqueteTipo()` (unchanged — F5.2 ships the 4-tipo narrowing)
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts::validatePayload()` (unchanged — F5.2 ships the 4-tipo schema map)
- `backend/**` (zero backend changes; F1.7 already ships `GET /operacion/salidas/:uuid` + `GET /documentos`)

## 12. Next steps

1. **sdd-spec** (`fase-7-3-tiquetes-salida`): author the delta spec against `openspec/specs/operations/spec.md` (add REQ-OPS-158..160 with 3 scenarios: REQ-OPS-158 `buildSalidaBuffer` 21-field byte presence + DEC-SUC-28 dynamic header, REQ-OPS-159 `buildSalidaMensualidadBuffer` 17-field byte presence + sello `0x1B 0x21 0x30` opcode invariant, REQ-OPS-160 `useSalidaMensualidadPayload` SWR hook + SalidaMensualidad full payload wiring). Drift reconciliation captured as REQ-OPS-158 MUST requirement that the builder reads `payload.sucursal.encabezado` (NOT the "PARKINGOS" constant).
2. **sdd-design**: technical design for the body emission tightening + `useSalidaMensualidadPayload` SWR hook + the SalidaMensualidad wiring. Cite F6.2 mapped-type exhaustiveness pattern verbatim. Cite F5.2 R4 purity invariants. Show the canonical `SalidaMensualidadPayload` shape from `escposTemplates.ts:385-401` post-tightening.
3. **sdd-tasks**: 6-commit plan from §8.2 mapped to T-HU-F7.3-1..N task IDs with RED/GREEN/REFACTOR phases per commit.
4. **sdd-apply**: implement + verify + merge to `dev` per AGENTS.md gitflow + override rule. Notify F8.1 developer that `escposBuilder.build('salida', payload)` is now ready to integrate.
5. **sdd-verify**: run verification per §8.4 success criteria; produce `verify-report.md` with drift-guard grep outputs.
6. **sdd-archive**: sync delta specs to `openspec/specs/operations/spec.md` (canonical), archive the change folder.
