# Proposal: HU-F8.3 — Reimpresión de tiquete con costo (FE)

> **Change**: `fase-8-3-reimpresion-tiquete-costo`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F8.3 (Fase 8 — Cobro y Factura Electrónica, CU-15x reimpresión con cobro)
> **Preflight**: pace=`auto`, artifact_store=`hybrid`, delivery_strategy=`single-pr`, review_budget=`800 LOC/PR` (per orchestrator brief; F7.1+F8.1 precedent ratified 2026-09-19), strict_tdd=`true`, chain_strategy=`n/a`
> **Git identity**: `Parkos Dev <dev@parkos.local>` (per AGENTS.md gitflow). No AI attribution in commits.
> **Inputs read**:
>   - `plan.md` lines 1969-2008 (F8.3 block: ACs + ER + Zod + e2e + 3 escenarios + 210 LOC + 4 tareas T1..T4)
>   - `apps/electron-sucursal/src/lib/print/escposBuilder.ts` lines 344-491 (`buildReimpresionBuffer` + `buildReimpresionBody` + `reimpresionPayloadSchema` discriminated union on `originalTipo: 'entrada' | 'salida' | 'salida-mensualidad'` — ALREADY EXISTS on `dev`)
>   - `apps/electron-sucursal/src/lib/print/escposTemplates.ts` lines 531-563 (`reimpresionPayloadSchema` + `ReimpresionPayload` type — ALREADY EXISTS)
>   - `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (F8.1 precedent — drawer shell + `deferredSafePrint` pattern + `useDashboardDrawerStore` consumer)
>   - `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` (F8.1 precedent — RHF + Zod resolver + vueltos en vivo via `useMemo`)
>   - `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` (F8.1 precedent — SWR mutation + `Idempotency-Key` SHA-256 closure + 401 → `useAuthStore.clear` + 409 `numeracion_agotada` mapping)
>   - `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.test.ts` (F8.1 precedent — 4 scenarios: efectivo 201, datáfono 201, 401 auth cleared, 409 numeracion_agotada)
>   - `apps/electron-sucursal/src/features/facturacion/pages/FacturaDetalle.tsx` (F8.2 precedent — page pattern under `/facturacion/...`)
>   - `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` (F7.2 `buildIdempotencyKey` — reused as-is)
>   - `apps/electron-sucursal/src/lib/validation/placaTolerante.ts` (F7.1 tolerant placa search — reused as-is)
>   - `apps/electron-sucursal/src/renderer/App.tsx` lines 65-72 (F8.2 route mount precedent at `/factura-electronica/:uuid` — F8.3 adds `/facturacion/reimprimir`)
>   - `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` (PARTIAL F8.3 SCAFFOLD already on `dev` — `reimprimir.titulo`, `reimprimir.motivoLabel`, `reimprimir.motivoPlaceholder`, `reimprimir.buscar`, `reimprimir.confirmar` keys present; F8.3 EXTENDS, not creates)
>   - `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/proposal.md` (F1.11 backend canonical — `POST /workflows/reimpresion-ticket` + `POST .../{uuid}/anular` contracts; DEC-TKT-04 `uuid_factura` OPTIONAL on create INSERT, deferred to F8.3 for create-then-reimprimir flow)
>   - `openspec/changes/archive/2026-09-19-fase-8-1-pago-modal-fe/{proposal,design}.md` (F8.1 baseline — PagoSheet/PagoModal/useRegistrarPago/escposBuilder 5th case precedent)
> **Skills loaded**: `sdd-propose` (this phase), `_shared/sdd-phase-common` (Section B/C/D envelope).
> **Working dir**: `E:\easypunto_parkos` · **Branch**: `dev` at `3d0e2e8` (F8.1 + F8.2 merged).

## 1. Intent

HU-F8.3 closes the reimpresión con costo flow on the renderer side. Operator (with `reimprimir_ticket` + `anular_reimpresion` permissions from F1.11 MIGRATION 0029) navigates to `/facturacion/reimprimir`, searches the ingreso by placa, types a `motivo` (≥10 chars per `plan.md:1985` Zod), confirms via a `role="alertdialog"` (cobro consequence — REQ-OPS UI a11y convention). Backend creates the `prod.factura` via F1.9 machinery (atomically charging `costos_servicios.concepto='reimpresion'`), then POSTs `prod.reimpresion_ticket` via F1.11 with `{motivo, uuid_ingreso, uuid_factura}`, then prints the tiquete con marca visual `0x1B 0x45` (negrita) wrapping the inner body + sello `*** REIMPRESIÓN ***` (DEC-SUC-27 invariant). Anular action calls `POST /workflows/reimpresion-ticket/{uuid}/anular` — backend INSERTs a NEW row with `uuid_reimpresion_padre=<original>` (NEVER UPDATE on `[L-W]` per F1.11 DEC-TKT-02/03 + insert-only invariant).

User-facing payoff: operador reimprime tiquetes perdidos/dañados cobrando el servicio, con confirmación explícita de cobro (alertdialog), con validación cliente-side del motivo (evita round-trip para `motivo_muy_corto`), con marca visual "REIMPRESIÓN" en el tiquete para auditoría física, y con botón de anulación que reversa el cobro vía INSERT de fila nueva (audit trail completo, sin perder el original).

## 2. Scope

### 2.1 In scope (T1..T4 + I1)

- **T1 — `<ReimprimirTiquete />` page** (NEW `apps/electron-sucursal/src/features/facturacion/pages/ReimprimirTiquete.tsx`): RHF + Zod resolver with `reimprimirFormSchema = z.object({ placa: z.string().min(1), motivo: z.string().min(10) })`. Two-step UX: (1) placa search via `useBuscarIngresoPorPlaca(placa)` SWR → renders matching ingreso summary (uuid + fecha + tipo: entrada|rotación|mensualidad), (2) motivo textarea + alertdialog confirmation (RHF `role="alertdialog"` on the modal — cobro consequence). Submit fires `useReimprimirTiquete().trigger({ uuid_ingreso, motivo })`. `useSWRMutation.isMutating` disables Confirm (REQ-OPS UI idempotency invariant — mirror F7.2 R2 + F8.1 R5).
- **T2 — `useReimprimirTiquete` SWR mutation** (NEW `apps/electron-sucursal/src/features/facturacion/hooks/useReimprimirTiquete.ts`): two-step POST mirroring F8.1 `useRegistrarPago` pattern (DEC-TKT-04 — F8.3 owns the create-factura-then-reimprimir flow per F1.11 §12 out-of-scope). Step 1: `POST /api/v1/facturacion/factura` with `{ uuid_ingreso, ... }` → 201 `{ uuid_factura }`. Step 2: `POST /api/v1/workflows/reimpresion-ticket` with `{ motivo, uuid_ingreso, uuid_factura: rawFactura.uuid_factura }` → 201 `{ uuid_reimpresion, uuid_factura_electronica?, estado: 'autorizada' }`. Each POST gets distinct `Idempotency-Key` SHA-256 via F7.2 `buildIdempotencyKey`. Errors: 401 → `useAuthStore.clear` (F3.1 invariant); 400 `motivo_muy_corto` → inline error (renderer pre-validates); 409 `reimpresion_already_pending` → toast banner; 409 `costo_servicio_no_configurado` → config-error banner (operator must seed `prod.costos_servicios.concepto='reimpresion'`).
- **T3 — `escposBuilder.build('reimpresion', payload)` tighten** (UPDATE `apps/electron-sucursal/src/lib/print/escposBuilder.ts` — `buildReimpresionBody` function lines 344-384): add the marca visual `0x1B 0x45` (escBoldOn) wrapping the inner body (the original entrada/salida/salida-mensualidad payload). The sello `*** REIMPRESION ***` already uses `escText2x()/escTextReset()` (DEC-SUC-27 invariant); F8.3 adds the bold wrapper around the body so the entire reimpreso tiquete is visually distinct from the original. Tighten the sello label from `*** REIMPRESION ***` (no accent) to `*** REIMPRESIÓN ***` (with accent per `plan.md:2006` verbatim copy) + add a small subline `--- COPIA AUTORIZADA ---` between sello and motivo.
- **T4 — Anular action** (NEW inside `<ReimprimirTiquete />` after 201 success): when the operator clicks "Anular reimpresión" on the success card (the page renders a post-201 summary card with uuid_reimpresion + motivo + costo_cop + buttons "Imprimir de nuevo" + "Anular"), opens a second `role="alertdialog"` (motivo_anulacion ≥10 chars Zod). On confirm, fires `useAnularReimpresion().trigger({ uuid_reimpresion, motivo_anulacion })` → `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` → 201 `{ workflow_estado: 'rechazada', uuid_reimpresion_padre: <original> }` → success toast + reset page to step 1.
- **I1 — `e2e/reimpresion.spec.ts` 3 scenarios** (NEW): (1) Reimprimir tiquete de entrada: cobro `costos_servicios` cargado a factura + tiquete reimpreso idéntico al original + marca `0x1B 0x45` wrapping body + sello `*** REIMPRESIÓN ***` con acento; (2) Reimprimir tiquete de salida: mismo patrón con desglose Subtotal/IVA/TOTAL preservado; (3) motivo con <10 caracteres: bloqueado del lado cliente, sin POST al backend, inline error en `motivo` field. axe-core WCAG 2.1 AA gate (RNF-022).

### 2.2 Out of scope

- **Backend reimpresion_ticket table + endpoints** — F1.11 owns (`POST /workflows/reimpresion-ticket`, `POST .../{uuid}/anular`). F8.3 consumes only.
- **Reimpresión gratuita inmediata** — Fases 6/7 (excepción E3 de CU-15x, "operación ya impresa"); separado, sin tabla compartida.
- **`prod.costos_servicios.concepto='reimpresion'` siembra** — F1.11 MIGRATION 0029 Op 1 owns the conditional seed. F8.3 reads at runtime; UI banner surfaces `costo_servicio_no_configurado` if absent.
- **`prod.reimpresion_ticket` schema changes** — zero. F1.11 closed it.
- **MIGRATION 0029** — F1.11 ships; F8.3 no DB.
- **Backend TopPoint / DIAN dispatch** — PR11 cloud-only; F8.3 prints at the branch only.
- **Frontend multi-tenant admin view** — single-tenant per branch; F8.3 pins to current `uuid_sucursal` (KD-S2 analog from F1.7).
- **Recibo de pago de reimpresión** — reimpresión es un cobro de servicio, no requiere FE nueva (la FE ya fue emitida en el CU-15x original); F8.3 NO emite `recibo_pago` ni `factura_electronica`. El cobro queda registrado en la factura del ingreso original.
- **Vite cache invalidation post-merge** — AGENTS.md script (per F7.x/F8.x precedent).
- **Release branch + tag** — per gitflow, F8.3 va a `dev` only.

## 3. Approach

### 3.1 Decision Path 1 — Page-based, not drawer-based

`ReimprimirTiquete` is a **full-page route** (`/facturacion/reimprimir`), NOT a `dashboardDrawerStore.open('reimprimir', anchorId)` consumer. Rationale:

- The flow is a long-running 4-step wizard (placa → motivo → alertdialog confirm → success card with anular button). The F8.1 PagoSheet drawer is a 2-step form (medio + FE toggle + confirm) — too cramped for the placa search + success card pattern.
- `plan.md:2005` explicitly says `src/features/facturacion/pages/ReimprimirTiquete.tsx` (page, not components).
- The success card with "Anular" action requires the URL to be addressable so the operator can navigate back via the browser back button (REQ-OPS-141 back-navigation invariant).
- Mirrors `<FacturaDetalle />` (F8.2 precedent) at `/factura-electronica/:uuid` — pages handle long-detail flows; drawers handle short-form flows.

### 3.2 Decision Path 2 — Two-step POST in `useReimprimirTiquete`

F1.11 DEC-TKT-04 makes `uuid_factura` OPTIONAL on `ReimpresionTicketCreateEndpoint`. The create-then-reimprimir flow lives in the renderer. Two-step mirrors F8.1 `useRegistrarPago` (factoría → pagos), but for F8.3 the order is reversed: first create the factura (so the cobro is persisted), then create the reimpresion_ticket pointing at that factura.

Why two distinct POSTs (not one big backend operation): (a) F1.11's handler does NOT snapshot the cost (F1.11 §5.2 DEC — "the issuance flow is decoupled from the cost"); (b) F1.9's `POST /facturacion/factura` already atomically handles the cobro + carga + FE emission; F8.3 just composes it with F1.11.

`useReimprimirTiquete` failure semantics: if the factura POST succeeds but the reimpresion_ticket POST fails (e.g., `motivo_muy_corto` slipping past client-side Zod, or `reimpresion_already_pending`), the operator sees a "cobro registrado pero reimpresión no generada — contactar admin" banner. The cobro stays; reimpresión must be retried manually (admin corrects via web_admin console — out of scope for F8.3).

### 3.3 Decision Path 3 — `escposBuilder.build('reimpresion', payload)` tighten

The reimpresion case ALREADY EXISTS on `dev` per F1.11 + F7.3 (per `escposBuilder.ts:344-491` + `escposTemplates.ts:531-563`). F8.3 makes 3 surgical changes inside `buildReimpresionBody`:

1. **Add `escBoldOn()/escBoldOff()` wrapping the inner body** — emits `0x1B 0x45` (ESC `E` bold on) BEFORE the inner body, `0x1B 0x46` (bold off) AFTER. This is the "marca visual" `plan.md:2006` requests. Hardware-agnostic: all ESC/POS-compatible printers support bold on/off.
2. **Update sello label**: `'*** REIMPRESION ***'` → `'*** REIMPRESIÓN ***'` (with accent per `plan.md:2006` verbatim). Subline `'--- COPIA AUTORIZADA ---'` inserted between sello and motivo line.
3. **Preserve all existing semantics**: DEC-SUC-28 dynamic header (extract `innerSucursalEncabezado` from inner payload); DEC-SUC-26 QR + logo markers (`;QR:` + `;LOGO:`); `originalTipo` discriminated union (entrada | salida | salida-mensualidad). NO new dispatcher arms; existing 5-tipo `build()` dispatcher (entrada | salida | salida-mensualidad | reimpresion | recibo_pago) unchanged.

The `escposBuilder.ts` byte-level changes are ~10 LOC. The unit tests in `escposBuilder.reimpresion.test.ts` (NEW) verify (a) bold opcode presence wrapping the body, (b) sello with accent + subline, (c) inner body content unchanged (entrada/salida fields all present).

### 3.4 Decision Path 4 — Zod `motivo` client-side pre-validation

`motivo: z.string().min(10)` checked before any POST. Zod error → inline error on the motivo textarea (red border + `motivo.muy_corto` i18n key + helper text). Backend's 400 `motivo_muy_corto` is still mapped (defense in depth — never trust client validation), but the operator NEVER sees a 400 because we pre-validate. This is F8.1 R3 precedent (`PagoModal` pre-validates NIT/DV before POST).

For anulación: same Zod `motivo_anulacion: z.string().min(10)` pre-validation.

### 3.5 Drift Reconciliation — plan.md vs `dev` code

| Aspect | `plan.md` F8.3 says | Live on `dev` (3d0e2e8) | F8.3 final shape |
|---|---|---|---|
| `escposBuilder` reimpresion literal | `'reimprimir'` (plan.md:2006) | `'reimpresion'` (`escposTemplates.ts:173,180`) | Use `'reimpresion'` (code is canonical; plan.md typo). Drift anchor. |
| `ReimprimirTiquete` location | `src/features/facturacion/pages/ReimprimirTiquete.tsx` (plan.md:2005) | does NOT exist yet | NEW at `pages/` (matches F8.2 `FacturaDetalle.tsx` precedent). |
| `ReimprimirTiquete` props | `onBuscar(placa), onConfirmar(motivo)` (plan.md:1994) | does NOT exist | Self-contained page (no prop drilling); uses `useBuscarIngresoPorPlaca` + `useReimprimirTiquete` hooks internally. |
| i18n keys | not in plan.md | PARTIAL scaffold on `dev` (`reimprimir.titulo`, `motivoLabel`, `motivoPlaceholder`, `buscar`, `confirmar`) | F8.3 EXTENDS with `reimprimir.tipo.label`, `reimprimir.tipo.entrada`, `reimprimir.tipo.salida`, `reimprimir.alertdialog.title`, `reimprimir.alertdialog.description`, `reimprimir.errors.motivo_muy_corto`, `reimprimir.errors.costo_no_configurado`, `reimprimir.errors.already_pending`, `reimprimir.success.titulo`, `reimprimir.anular.titulo`, `reimprimir.anular.motivoLabel`, `reimprimir.anular.confirmar`. |
| `escposBuilder` marca visual | `0x1B 0x45` (negrita) wrapping body | only used on TOTAL line in salida body | F8.3 ADDS it wrapping the reimpresion inner body. |
| Sello label | `"REIMPRESIÓN"` (plan.md:2006) | `"REIMPRESION"` (no accent) | F8.3 updates to accent + adds `--- COPIA AUTORIZADA ---` subline. |
| Backend endpoint | POST `/{uuid}/anular` (plan.md:1981) | already merged in F1.11 at `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` | F8.3 consumes only. |

## 4. Affected Files

| File | Action | LOC est. | Notes |
|---|---|---|---|
| `apps/electron-sucursal/src/features/facturacion/pages/ReimprimirTiquete.tsx` | NEW | 100 | T1 — page with placa search + motivo textarea + alertdialog confirmation + post-201 success card with anular button. RHF + Zod resolver. `role="alertdialog"` on the alertdialog. |
| `apps/electron-sucursal/src/features/facturacion/pages/ReimprimirTiquete.test.tsx` | NEW | 80 | T1 — 5 scenarios: placa search → ingreso summary render; motivo <10 → inline error no POST; motivo ≥10 → alertdialog opens; alertdialog confirm → POST + success card; success card anular → second alertdialog opens. |
| `apps/electron-sucursal/src/features/facturacion/hooks/useReimprimirTiquete.ts` | NEW | 70 | T2 — SWR mutation, two-step POST (F1.9 factura → F1.11 reimpresion), distinct `Idempotency-Key` SHA-256 per step, 401/400/409 error mapping. Mirror F8.1 `useRegistrarPago.ts`. |
| `apps/electron-sucursal/src/features/facturacion/hooks/useReimprimirTiquete.test.ts` | NEW | 100 | T2 — 5 scenarios: happy path efectivo (factura + reimpresion), happy path datáfono, 401 → auth cleared, 409 `reimpresion_already_pending`, 409 `costo_servicio_no_configurado`. |
| `apps/electron-sucursal/src/features/facturacion/api/reimpresionApi.ts` | NEW | 50 | T2 — Zod mirror of F1.11 `ReimpresionTicketRead` + `ReimpresionTicketCreateEndpoint` + `ReimpresionTicketAnular` request shapes. |
| `apps/electron-sucursal/src/features/facturacion/hooks/useBuscarIngresoPorPlaca.ts` | NEW | 40 | T1 — SWR `useSWR` keyed by placa; returns matching ingreso summary (uuid + fecha + tipo). Backend endpoint: `GET /api/v1/ingresos?placa=<placa>` (mirror F7.1 `useBuscarIngresoPorPlaca` precedent — verify exact endpoint in sdd-design phase). |
| `apps/electron-sucursal/src/features/facturacion/hooks/useBuscarIngresoPorPlaca.test.ts` | NEW | 40 | T1 — 3 scenarios: matching placa returns summary, no match returns null, SWR cache hit on repeated placa. |
| `apps/electron-sucursal/src/features/facturacion/hooks/useAnularReimpresion.ts` | NEW | 50 | T4 — SWR mutation, single-step POST `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular`. Mirror F7.2 `useRegistrarSalida`. |
| `apps/electron-sucursal/src/features/facturacion/hooks/useAnularReimpresion.test.ts` | NEW | 60 | T4 — 3 scenarios: happy path → 201 + workflow_estado='rechazada', 404 `reimpresion_not_found`, 409 `anulacion_no_permitida` (terminal chain tip). |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | UPDATE | +10 (delta) | T3 — `buildReimpresionBody` adds `escBoldOn()` BEFORE inner body + `escBoldOff()` AFTER; updates sello `'*** REIMPRESION ***'` → `'*** REIMPRESIÓN ***'` + subline `'--- COPIA AUTORIZADA ---'`. NO new dispatcher arms. |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.reimpresion.test.ts` | NEW | 60 | T3 — 6 byte-presence scenarios: bold opcode `0x1B 0x45` wrapping body; bold off opcode `0x1B 0x46` AFTER body; sello with accent `*** REIMPRESIÓN ***`; subline `--- COPIA AUTORIZADA ---`; DEC-SUC-28 dynamic header preserved; inner body content unchanged (entrada fields all present). |
| `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` | UPDATE | +13 keys (delta) | T1+T4 — `reimprimir.tipo.label`, `reimprimir.tipo.entrada`, `reimprimir.tipo.salida`, `reimprimir.alertdialog.title`, `reimprimir.alertdialog.description`, `reimprimir.errors.motivo_muy_corto`, `reimprimir.errors.costo_no_configurado`, `reimprimir.errors.already_pending`, `reimprimir.success.titulo`, `reimprimir.anular.titulo`, `reimprimir.anular.motivoLabel`, `reimprimir.anular.confirmar`, `reimprimir.placa.label`. |
| `apps/electron-sucursal/src/renderer/App.tsx` | UPDATE | +10 (delta) | Route mount `/facturacion/reimprimir` → `<ReimprimirTiquete />` inside `<ProtectedRoute>`. Mirror F8.2 line 65-72. |
| `apps/electron-sucursal/e2e/reimpresion.spec.ts` | NEW | 50 | I1 — 3 Playwright scenarios per `plan.md:1996-2000`. axe-core WCAG 2.1 AA gate. |
| **Total new LOC** | | **+610** | |
| **Total updated LOC (deltas)** | | **+23** (10 escposBuilder + 13 i18n keys) | |
| **Grand total LOC** | | **~633** | **Under 800 budget — no `size:exception` needed** |

## 5. Dependencies

### 5.1 Already-merged prerequisites (verified on `dev`)

- **F1.11 — `POST /api/v1/workflows/reimpresion-ticket` + `POST .../{uuid}/anular`** (merged): backend canonical endpoints + DEC-TKT-04 `uuid_factura` optional + GAP-BE-04 permission reconciliation. F8.3 consumes both endpoints. **Required.**
- **F1.11 MIGRATION 0029 — `prod.costos_servicios.concepto='reimpresion'` siembra + `anular_reimpresion` permission seed** (merged): conditional seed present; permission available; operador role gets `anular_reimpresion` via `prod.permisos_usuario`. **Required.**
- **F1.9 — `POST /facturacion/factura`** (merged): F8.3 step 1 (create factura). **Required.**
- **F8.1 — `useRegistrarPago` SWR mutation pattern + `Idempotency-Key` SHA-256 closure** (merged): F8.3 mirrors for two-step POST. **Required.**
- **F8.1 — `escposBuilder` 5-tipo dispatcher + `escposTemplates.ts` `reimpresionPayloadSchema`** (merged): F8.3 tightens the existing `reimpresion` case (no new arm). **Required.**
- **F7.1 — `placaTolerante.ts` tolerant placa search** (merged): reused as-is for placa normalization. **Required.**
- **F7.2 — `useRegistrarSalida` SWR mutation + `buildIdempotencyKey`** (merged): pattern mirror for `useReimprimirTiquete` + `useAnularReimpresion`. **Required.**
- **F8.2 — `<FacturaDetalle />` page at `/factura-electronica/:uuid`** (merged): page-mount pattern precedent. **Required.**
- **F3.1 — `parkosFetch` + `useAuthStore.clear()` + `parkos:auth:cleared`** (merged): 401 invariant. **Required.**
- **F5.2 — `bridge.imprimir(tipo, payload)` IPC contract** (merged): printer fallback chain. **Required.**
- **i18next es-CO default** + `facturacion.json` partial scaffold (`reimprimir.titulo`, `motivoLabel`, `motivoPlaceholder`, `buscar`, `confirmar` keys present on `dev`). **Required.**

### 5.2 Forward-dependents (do NOT block F8.3)

- **HU-F8.x (Recibo de pago de reimpresión)** — DEFERRED. The cobro stays on the factura from the original CU-15x; no new FE is emitted for reimpresión.
- **HU-F9.x (Operador admin view for reimpresion_anuladas)** — DEFERRED. Admin corrections via web_admin console.

### 5.3 Skill + tooling prerequisites

- `react` skill (loaded by parent) — D-073 stack, Vite 5, shadcn/ui único, RHF + Zod, i18next es-CO, WCAG 2.1 AA via axe-core.
- `sdd-spec` / `sdd-design` / `sdd-tasks` follow phases (not skills; phase agents).

## 6. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Two-step POST partial failure** — factura POST succeeds but reimpresion_ticket POST fails (e.g., `motivo_muy_corto` slipping past client validation, network blip, `reimpresion_already_pending`). Operator sees cobro registrado pero reimpresión no generada. | MED | (a) Renderer Zod pre-validation (`motivo: z.string().min(10)`) catches the most common case before POST. (b) Backend's 400 `motivo_muy_corto` is still mapped (defense in depth — never trust client validation). (c) UI banner surfaces the partial-failure state clearly: "Cobro registrado (factura {uuid_factura}). Reimpresión no generada. Contactar admin." (d) The admin uses web_admin to retry the reimpresión (DEFERRED — out of scope for F8.3; documented as known limitation). |
| **R2** | **`prod.costos_servicios.concepto='reimpresion'` siembra absent** — backend returns 409 `costo_servicio_no_configurado` at runtime. | LOW | (a) F1.11 MIGRATION 0029 Op 1 ships the conditional seed (idempotent pre-flight). (b) Renderer UI surfaces a config-error banner with the `concepto='reimpresion'` literal so the operator knows what to ask the admin to seed. (c) Drift guard `tests/static/test_f8_3_costos_servicios_seed_present.py` verifies the seed row exists in `prod.costos_servicios` at boot. |
| **R3** | **Doble-click during in-flight reimprimir** — duplicate INSERT in `prod.reimpresion_ticket` (F1.11 §R4: schema allows concurrent reimpresions on same ingreso). | LOW | (a) `useSWRMutation.isMutating` UI disable on Confirm button (mirror F7.2 R2 + F8.1 R5). (b) `Idempotency-Key` SHA-256 closure on BOTH POSTs (different paths, distinct keys) — server-side 24h cache dedup absorbs accidental re-clicks. (c) `useAnularReimpresion` has the same `isMutating` disable + idempotency. |
| **R4** | **Backend endpoint path drift** — F1.11 already merged; verify exact path + body shape against `backend/.../api/v1/workflows.py` lines 73-78, 111-118 + `schemas/workflows.py` lines 50-132. | LOW | (a) `reimpresionApi.ts` Zod schemas mirror F1.11 verbatim — drift caught at compile time. (b) `useReimprimirTiquete.test.ts` asserts exact request shape (path, body, Idempotency-Key header). (c) If drift detected in sdd-design phase, escalate to F1.11 owner for sync correction. |
| **R5** | **`useBuscarIngresoPorPlaca` backend endpoint existence** — plan.md:1985 mentions placa search but doesn't name the backend GET endpoint. | MED | (a) Verify in sdd-design phase against `backend/.../api/v1/ingresos.py` (F1.7 — verify `GET /api/v1/ingresos?placa=<placa>` exists or `GET /api/v1/ingresos/search?placa=...`). (b) If neither exists, F8.3's `useBuscarIngresoPorPlaca` needs a backend PR (OUT OF SCOPE per orchestrator brief — escalate to user if endpoint absent). (c) Fallback: use the existing `GET /api/v1/operacion/ingresos-activos` (F6.1) and filter client-side (defeats purpose; DEFERRED if no clean backend endpoint). |
| **R6** | **escposBuilder `0x1B 0x45` bold opcode may not render on all printers** — old thermal printers may ignore or interpret differently. | LOW | (a) ESC `E` (bold) is a universal ESC/POS opcode supported by all EPSON-compatible printers since 1990. (b) F8.3's unit test asserts bytes; printer behavior is hardware-specific (DEC-SUC-08 printer fallback chain absorbs failures — printer offline → `console.warn` + operator keeps the screen success state). (c) The marca visual is informational, not critical (the sello `*** REIMPRESIÓN ***` with `escText2x()` is the primary visual distinguisher per DEC-SUC-27 invariant). |
| **R7** | **alertdialog `role="alertdialog"` WCAG semantics** — must have proper aria-labelledby + aria-describedby for screen readers. | LOW | (a) shadcn `<AlertDialog>` primitive wires `role="alertdialog"` + `aria-labelledby` + `aria-describedby` to the title + description slots automatically. (b) e2e axe-core WCAG 2.1 AA gate verifies 0 violations on the ReimprimirTiquete page. (c) `<SheetTitle>` + `<SheetDescription>` props provide the accessible name + description. |
| **R8** | **i18n keys partial scaffold drift** — `facturacion.json` already has 5 `reimprimir.*` keys on `dev`; F8.3 must EXTEND (not overwrite). | LOW | (a) Drift guard: `jq '.reimprimir | keys | length' apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` returns ≥18 (5 original + 13 new). (b) Static test `tests/static/test_f8_3_i18n_keys_extended.py` asserts the 13 new keys are present. |

## 7. Open Decisions to Ratify

Three open decisions require user ratification before `sdd-spec` locks them.

### OD-1 — Single-page vs split-page for entrada vs salida?

**Proposal**: **SINGLE page** with a `tipo: 'entrada' | 'salida' | 'salida-mensualidad'` selector (3-option RadioGroup, derived from the `prod.ingreso.tipo_salida` column or null if the ingreso is still activo). After placa search resolves, the page pre-fills `tipo` from the ingreso record (the operator can override).

**Alternatives**: (a) TWO pages: `/facturacion/reimprimir/entrada` + `/facturacion/reimprimir/salida` (separates flows but doubles the page surface). (b) THREE pages including salida-mensualidad (full separation; not justified — mensualidad reims rarely differ from regular salida).

**Ratification needed**: confirm single-page with tipo selector. Plan.md F8.3 doesn't specify; F7.3 precedent uses single `'salida' | 'salida-mensualidad'` discriminator in the same builder, supporting single-page.

### OD-2 — `motivo_anulacion` Zod schema same as `motivo`?

**Proposal**: **SAME** (`z.string().min(10)`). The Zod schema is reusable; both motivo and motivo_anulacion carry the same audit-trail weight (both go into `prod.reimpresion_ticket.motivo` and `prod.reimpresion_ticket.motivo_anulacion` columns, both StringConstraints(min_length=10, max_length=500) per F1.11).

**Alternatives**: (a) Stricter for anulación (`min(20)`) — anulaciones are rarer and more consequential. (b) Looser for anulación (`min(5)`) — operators rush, lower friction.

**Ratification needed**: confirm same (F1.11 backend uses identical constraints; symmetry is the principle of least surprise).

### OD-3 — Placa search: client-side filter or server-side endpoint?

**Proposal**: **SERVER-SIDE** via `GET /api/v1/ingresos?placa=<placa>` (mirror F7.1 precedent — verify exact endpoint existence in sdd-design phase per R5).

**Alternatives**: (a) `GET /api/v1/ingresos/search?placa=...` (different path). (b) Client-side filter over `GET /api/v1/ingresos-activos` (F6.1) — defeats purpose for historical ingresos. (c) New backend endpoint in F8.3 (OUT OF SCOPE per orchestrator brief).

**Ratification needed**: confirm server-side, exact endpoint TBD in sdd-design phase. R5 mitigation covers the verification path.

## 8. PR Shape

### 8.1 Single PR topology

| Field | Value |
|---|---|
| Branch | `feature/hu-f8-3-reimpresion-tiquete-costo` |
| Target | `dev` (gitflow — NEVER `main`) |
| Work units | T1, T2, T3, T4 + I1 (5 commits) |
| Commit strategy | `work-unit-commits` skill — each T/I is a separate reviewable commit |
| Conventional Commits | strict (no `Co-authored-by` AI trailers per AGENTS.md canon) |
| LOC budget | 800 lines per PR; F8.3 forecast = ~633 LOC |
| `size:exception` required | **NO** — 633 LOC < 800 budget (−167, −20.9%) |
| Chained PRs | **NO** — `useReimprimirTiquete` + `useAnularReimpresion` + `<ReimprimirTiquete />` + `escposBuilder` tighten are integral but fit comfortably in single PR |

### 8.2 Commit plan (work-unit-commits skill)

Each commit MUST compile + pass all tests independently (strict TDD).

| # | Commit | Type | Scope | Files | TDD phase |
|---|---|---|---|---|---|
| 1 | `feat(facturacion): reimpresionApi Zod schemas + useBuscarIngresoPorPlaca SWR + 3 unit tests (F8.3 T1 backend glue)` | feat | facturacion | NEW reimpresionApi.ts, NEW useBuscarIngresoPorPlaca.ts, NEW useBuscarIngresoPorPlaca.test.ts | RED (3 tests fail: matching placa, no match, cache hit) → GREEN |
| 2 | `feat(facturacion): useReimprimirTiquete two-step POST + useAnularReimpresion + 8 unit tests (mirror useRegistrarPago)` | feat | facturacion | NEW useReimprimirTiquete.ts, NEW useReimprimirTiquete.test.ts, NEW useAnularReimpresion.ts, NEW useAnularReimpresion.test.ts | RED (8 tests fail: 5 reimprimir + 3 anular scenarios) → GREEN |
| 3 | `feat(print): escposBuilder reimpresion case tighten with bold marca visual + REIMPRESIÓN sello + 6 byte-presence tests` | feat | print | UPDATE escposBuilder.ts (+10 delta), NEW escposBuilder.reimpresion.test.ts | RED (6 byte-presence tests fail) → GREEN; existing 4-tipo dispatcher tests still pass |
| 4 | `feat(facturacion): ReimprimirTiquete page with placa search + alertdialog + success card anular + 5 component tests + App.tsx route + i18n +13 keys` | feat | facturacion | NEW ReimprimirTiquete.tsx, NEW ReimprimirTiquete.test.tsx, UPDATE App.tsx (+10 delta), UPDATE facturacion.json (+13 keys) | RED (5 ReimprimirTiquete scenarios fail) → GREEN |
| 5 | `test(e2e): reimpresion.spec.ts 3 scenarios per plan.md:1996-2000 + axe-core WCAG gate` | test | e2e | NEW e2e/reimpresion.spec.ts | RED (3 e2e scenarios fail on missing alertdialog + bold marca + motivo Zod) → GREEN |

### 8.3 PR title + body

- **Title**: `feat(facturacion): HU-F8.3 reimpresión de tiquete con costo (alertdialog + escpos bold marca + anular)`
- **Body**: Conventional Commits footer with `Refs: HU-F8.3`, `Refs: REQ-OPS-181..186` (TBD in sdd-spec), `Closes: plan.md:1969-2008`. Bullet list of the 5 T/I/E work units. Drift reconciliation note (§3.5) inline — explicit acknowledgement that `escposBuilder.build('reimpresion', ...)` already existed (F1.11 + F7.3); F8.3 tightens with bold marca. Rollback plan: revert the single branch (`feature/hu-f8-3-...` → `dev`), no DB migration, no backend change. The 5 commits are atomic per work-unit (revertible individually via `git revert <sha>` without breaking the build).

### 8.4 Verification gate (pre-merge)

- [ ] `git diff dev..feature/hu-f8-3-...` ≤ 633 LOC (well under 800 budget; no `size:exception`)
- [ ] `pnpm --filter electron-sucursal lint` exits 0
- [ ] `pnpm --filter electron-sucursal typecheck` exits 0 (incl. `tsc --strict` exhaustiveness on Zod schemas + discriminator unions)
- [ ] `pnpm --filter electron-sucursal test` exits 0 with all 3 useBuscarIngresoPorPlaca + 5 useReimprimirTiquete + 3 useAnularReimpresion + 5 ReimprimirTiquete + 6 escposBuilder.reimpresion tests passing
- [ ] `pnpm --filter electron-sucursal e2e -- reimpresion.spec.ts` exits 0 with 3 scenarios passing
- [ ] Drift guard: `grep -r "0x1B 0x45" apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.reimpresion.test.ts` returns ≥2 matches (bold-on + bold-off assertions)
- [ ] Drift guard: `jq '.reimprimir | keys | length' apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` returns ≥18 (5 original + 13 new keys)
- [ ] Drift guard: `grep -r "role=\"alertdialog\"" apps/electron-sucursal/src/features/facturacion/pages/ReimprimirTiquete.tsx` returns ≥2 matches (confirmation + anulación dialogs)
- [ ] Drift guard: `tests/static/test_f8_3_costos_servicios_seed_present.py` asserts `prod.costos_servicios.concepto='reimpresion'` row exists at boot (R2 mitigation)
- [ ] axe-core WCAG 2.1 AA: 0 violations on `<ReimprimirTiquete />` (gated per CI per DEC-SUC-10)
- [ ] `gh pr merge --squash --body-file` produces a squash commit with no `Co-authored-by` AI trailer

### 8.5 Post-merge (per AGENTS.md gitflow + override rule 2026-09-17)

1. `git checkout dev` + `git merge --ff-only feature/hu-f8-3-reimpresion-tiquete-costo` (or `--no-ff` if not direct descendant).
2. `git push origin dev`.
3. `git branch -d feature/hu-f8-3-reimpresion-tiquete-costo` + `git push origin --delete feature/hu-f8-3-reimpresion-tiquete-costo`.
4. Vite cache invalidation: kill port 5173 + restart with `--force` per AGENTS.md.
5. Engram `mem_save` of the canonical `useReimprimirTiquete` two-step POST + `escposBuilder.reimpresion` bold marca + `useAnularReimpresion` INSERT-only chain decisions (post-merge convention).

## 9. Rollback Plan

Single-branch revert. No DB changes (F1.11 ships the schema). No backend changes (F1.11 + F1.9 are the canonical endpoints).

**Path 1 — Pre-merge revert** (`git revert <merge-sha>`): nukes the 5 commits, removes the new pages/hooks/api file, reverts `escposBuilder.ts` to F7.3 state, removes the App.tsx route + i18n keys. Zero impact on backend or DB.

**Path 2 — Post-merge `git revert` on `dev`**: same as Path 1, applied to `dev`. The i18n keys revert to the 5-key partial scaffold (acceptable — F7.x already uses these keys for the reimpresión gratuita inmediata flow).

**Path 3 — Partial rollback**: if only the alertdialog UX fails, commit 4 can be reverted alone (page + i18n keys). Commits 1-3 (hooks + escposBuilder) ship independently — `useReimprimirTiquete` and `escposBuilder.build('reimpresion', ...)` are testable in isolation. The page just doesn't mount.

## 10. Success Criteria

1. `useBuscarIngresoPorPlaca('ABC123')` returns `{uuid, fecha, tipo: 'entrada' | 'rotacion' | 'mensualidad'}` for matching placa; `null` for no match.
2. `<ReimprimirTiquete />` mounts at `/facturacion/reimprimir`; renders placa search input + motivo textarea; `useSWRMutation.isMutating` disables Confirm button during in-flight POST.
3. motivo <10 chars → inline Zod error (`reimprimir.errors.motivo_muy_corto` i18n key), NO POST fired.
4. motivo ≥10 chars → alertdialog opens (`role="alertdialog"` + cobro consequence description per `plan.md:1983`), Confirm fires `useReimprimirTiquete().trigger({ uuid_ingreso, motivo })`.
5. 201 response → success card renders with uuid_reimpresion + motivo + costo_cop + buttons "Imprimir de nuevo" + "Anular"; `bridge.imprimir('reimpresion', payload)` fires via `deferredSafePrint` (mirror F8.1 `PagoSheet.tsx:70-81`).
6. `useAnularReimpresion().trigger({ uuid_reimpresion, motivo_anulacion })` → `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` → 201 `{ workflow_estado: 'rechazada' }`; success toast; page resets to step 1.
7. `escposBuilder.build('reimpresion', mockPayload)` returns a `Buffer` containing: (a) DEC-SUC-28 dynamic header from `innerSucursalEncabezado`, (b) sello `*** REIMPRESIÓN ***` (with accent) + subline `--- COPIA AUTORIZADA ---`, (c) `0x1B 0x45` (escBoldOn) BEFORE inner body + `0x1B 0x46` (escBoldOff) AFTER, (d) inner body content unchanged (entrada fields all present).
8. 401 from any POST → `useAuthStore.clear()` + `parkos:auth:cleared` (F3.1 invariant preserved).
9. 409 `costo_servicio_no_configurado` → config-error banner with `concepto='reimpresion'` literal.
10. 409 `reimpresion_already_pending` → toast banner "Ya existe una reimpresión activa para este ingreso".
11. 409 `anulacion_no_permitida` → toast banner "La reimpresión ya fue anulada (cadena terminal)".
12. `e2e/reimpresion.spec.ts` passes 3 scenarios: entrada reimpresión / salida reimpresión / motivo corto blocked.
13. Drift guards pass: i18n keys extended (≥18), `0x1B 0x45` opcode asserted in tests, `role="alertdialog"` present in page source, `costos_servicios` seed verified at boot.
14. axe-core WCAG 2.1 AA: 0 violations on `<ReimprimirTiquete />` (gated per CI per DEC-SUC-10).
15. `pnpm typecheck`, `pnpm lint`, `pnpm test` exit 0 across the full `electron-sucursal` workspace.
16. Zod discriminated unions exhaustiveness check fails `tsc --noEmit` if either `motivo` schema or `motivo_anulacion` schema is renamed or removed.

## 11. Relevant Files (canonical pointers)

**OpenSpec / plan / spec**:
- `openspec/changes/fase-8-3-reimpresion-tiquete-costo/proposal.md` (this file)
- `openspec/changes/fase-8-3-reimpresion-tiquete-costo/specs/operations/spec.md` (sdd-spec delta, REQ-OPS-181..186 TBD)
- `openspec/changes/fase-8-3-reimpresion-tiquete-costo/design.md` (sdd-design phase, future)
- `openspec/changes/fase-8-3-reimpresion-tiquete-costo/tasks.md` (sdd-tasks phase, future)
- `openspec/changes/fase-8-3-reimpresion-tiquete-costo/apply-progress.md` (sdd-apply phase, future)
- `openspec/changes/fase-8-3-reimpresion-tiquete-costo/verify-report.md` (sdd-verify phase, future)
- `plan.md` lines 1969-2008 (F8.3 block: ACs + ER + Zod + e2e + 3 escenarios + 210 LOC + 4 tareas)
- `openspec/specs/operations/spec.md` (F1.11 REQ-OPS-075..080 baseline — F8.3 adds REQ-OPS-181..186)

**Archive precedents**:
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/{proposal,design,tasks,verify-report}.md` (F1.11 — `POST /workflows/reimpresion-ticket` + `POST .../{uuid}/anular` contracts; DEC-TKT-04 `uuid_factura` optional)
- `openspec/changes/archive/2026-09-19-fase-8-1-pago-modal-fe/{proposal,design,tasks,verify-report}.md` (F8.1 — `useRegistrarPago` SWR mutation + `escposBuilder.build('recibo_pago', payload)` 5th case + PagoSheet refactor)
- `openspec/changes/archive/2026-09-19-fase-8-2-factura-detalle-fe/{proposal,design,tasks,verify-report}.md` (F8.2 — `<FacturaDetalle />` page pattern precedent at `/factura-electronica/:uuid`)
- `openspec/changes/archive/2026-09-19-fase-7-1-busqueda-tolerante-cotizacion/{proposal,design,tasks,verify-report}.md` (F7.1 — `placaTolerante.ts` + `useBuscarIngresoPorPlaca` precedent)
- `openspec/changes/archive/2026-09-19-fase-7-2-registrar-salida/{proposal,design,tasks,verify-report}.md` (F7.2 — `useRegistrarSalida` SWR mutation + `buildIdempotencyKey` + 409 error mapping)
- `openspec/changes/archive/2026-09-19-fase-7-3-tiquetes-salida/{proposal,design,tasks,verify-report}.md` (F7.3 — `escposBuilder` tightening + `buildSalidaBuffer` 21-field + DEC-SUC-28 dynamic header + `'reimpresion'` envelope case)

**Frontend source (live on `dev` at `3d0e2e8`)**:
- `apps/electron-sucursal/src/features/facturacion/pages/FacturaDetalle.tsx` (F8.2 page pattern precedent — F8.3 mirrors)
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx` (F8.1 drawer shell + `deferredSafePrint` pattern — F8.3 mirrors for print trigger)
- `apps/electron-sucursal/src/features/facturacion/components/PagoModal.tsx` (F8.1 RHF + Zod discriminated union — F8.3 mirrors for `motivo` Zod)
- `apps/electron-sucursal/src/features/facturacion/hooks/useRegistrarPago.ts` (F8.1 SWR mutation + `Idempotency-Key` SHA-256 — F8.3 `useReimprimirTiquete` mirrors)
- `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` (F8.2 polling hook — F8.3 does NOT modify)
- `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` (F8.2 retry panel — F8.3 does NOT modify)
- `apps/electron-sucursal/src/features/operacion/hooks/useRegistrarSalida.ts` (F7.2 SWR mutation pattern — F8.3 `useAnularReimpresion` mirrors)
- `apps/electron-sucursal/src/features/operacion/lib/idempotency.ts` (F7.2 `buildIdempotencyKey` — F8.3 reuses as-is)
- `apps/electron-sucursal/src/lib/validation/placaTolerante.ts` (F7.1 tolerant placa search — F8.3 reuses as-is)
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts:344-491` (F1.11 + F7.3 `buildReimpresionBuffer` + `buildReimpresionBody` — F8.3 tightens)
- `apps/electron-sucursal/src/lib/print/escposTemplates.ts:531-563` (F5.2 + F6.2 + F7.3 `reimpresionPayloadSchema` + `ReimpresionPayload` type — F8.3 reuses as-is)
- `apps/electron-sucursal/src/renderer/App.tsx:65-72` (F8.2 route mount precedent at `/factura-electronica/:uuid` — F8.3 adds `/facturacion/reimprimir`)
- `apps/electron-sucursal/src/renderer/i18n/locales/facturacion.json` (PARTIAL F8.3 scaffold — 5 `reimprimir.*` keys present; F8.3 EXTENDS with 13 new keys)

**Files NOT touched (deliberate)**:
- `backend/**` (zero backend changes; F1.11 + F1.9 + F1.10 already close the canonical endpoints)
- `apps/electron-sucursal/src/features/facturacion/hooks/useFacturaElectronica.ts` (F8.2 owns; F8.3 does NOT modify)
- `apps/electron-sucursal/src/features/facturacion/components/FacturaElectronicaRetryPanel.tsx` (F8.2 owns; F8.3 does NOT mount this panel)
- `apps/electron-sucursal/src/main/services/*` (printer hardware fallback chain — F5.1 owns)
- `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts` (F8.3 is page-based, NOT drawer-based)

## 12. Next Steps

1. **sdd-spec** (`fase-8-3-reimpresion-tiquete-costo`): author the delta spec against `openspec/specs/operations/spec.md`. Add REQ-OPS-181..186 with scenarios:
   - REQ-OPS-181: `<ReimprimirTiquete />` page + placa search + motivo Zod (`min(10)`) + alertdialog confirmation
   - REQ-OPS-182: `useReimprimirTiquete` two-step POST (F1.9 factura → F1.11 reimpresion) with distinct `Idempotency-Key` SHA-256
   - REQ-OPS-183: `useAnularReimpresion` single-step POST (F1.11 `anular`) with INSERT-only chain invariant
   - REQ-OPS-184: `escposBuilder.build('reimpresion', payload)` tighten — `0x1B 0x45` bold opcode wrapping inner body + sello `*** REIMPRESIÓN ***` (with accent) + subline `--- COPIA AUTORIZADA ---` (preserves DEC-SUC-28 dynamic header + DEC-SUC-26 QR + logo markers + DEC-SUC-27 sello with `escText2x()`)
   - REQ-OPS-185: i18n extension — 13 new `reimprimir.*` keys (`tipo.label`, `tipo.entrada`, `tipo.salida`, `alertdialog.title`, `alertdialog.description`, `errors.motivo_muy_corto`, `errors.costo_no_configurado`, `errors.already_pending`, `success.titulo`, `anular.titulo`, `anular.motivoLabel`, `anular.confirmar`, `placa.label`)
   - REQ-OPS-186: drift guards — i18n keys extended (≥18), `0x1B 0x45` opcode asserted in tests, `role="alertdialog"` present in page source, `costos_servicios` seed verified at boot
2. **sdd-design**: technical design for the page composition + Zod schemas + SWR mutation two-step POST + escposBuilder tighten. Cite F8.1 `useRegistrarPago` mirror precedent verbatim. Cite F1.11 backend contract verbatim. Show the canonical `<ReimprimirTiquete />` props + `useReimprimirTiquete` shape + `ReimpresionTicketRead` Zod shape. Verify exact `GET /api/v1/ingresos?placa=...` endpoint existence (R5 mitigation).
3. **sdd-tasks**: 5-commit plan from §8.2 mapped to T-HU-F8.3-1..N task IDs with RED/GREEN/REFACTOR phases per commit. NO `size:exception` needed (633 LOC < 800 budget). Verify R5 backend endpoint in design phase before tasks phase.
4. **sdd-apply**: implement + verify + merge to `dev` per AGENTS.md gitflow + override rule. NO backend changes. NO DB migration.
5. **sdd-verify**: run verification per §8.4 success criteria; produce `verify-report.md` with drift-guard grep outputs (3 useBuscarIngresoPorPlaca + 5 useReimprimirTiquete + 3 useAnularReimpresion + 5 ReimprimirTiquete + 6 escposBuilder.reimpresion + 3 e2e reimpresion scenarios, 0 axe-core WCAG 2.1 AA violations).
6. **sdd-archive**: sync delta specs to `openspec/specs/operations/spec.md` (canonical REQ-OPS-181..186), archive the change folder.
