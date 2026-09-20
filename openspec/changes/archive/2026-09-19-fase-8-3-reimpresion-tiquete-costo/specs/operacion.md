# Delta Spec — HU-F8.3: Reimpresión de tiquete con costo (FE)

> **Change**: `fase-8-3-reimpresion-tiquete-costo`
> **Target spec**: `openspec/specs/operations/spec.md` (will append 5 new REQs on archive: REQ-OPS-171..175)
> **Phase**: spec (sdd-spec)
> **HU ID**: HU-F8.3 (Fase 8 — Cobro y Factura Electrónica, CU-15x reimpresión con cobro)
> **Inputs read**: `proposal.md`, `apps/electron-sucursal/src/lib/print/escposBuilder.ts:344-491` (F1.11+F7.3 `buildReimpresionBuffer`/`buildReimpresionBody` already on `dev` with `'reimpresion'` dispatcher key + `'*** REIMPRESION ***'` sello — no accent), `escposTemplates.ts:531-563` (`reimpresionPayloadSchema` discriminated union on `originalTipo`), `useRegistrarPago.ts` (F8.1 SWR mutation + Idempotency-Key SHA-256 pattern mirror), `useReintentarFE.ts` (F8.2 single-POST pattern mirror), `facturaApi.ts` (Zod discriminated union precedent), `facturacion.json:49-55` (partial scaffold), `App.tsx:65-72` (F8.2 route mount precedent), F1.11 spec (REQ-OPS-075..080 backend contract for `POST /workflows/reimpresion-ticket` + `POST .../{uuid}/anular`).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `dev` at `3d0e2e8`.

---

## Purpose

HU-F8.3 closes the reimpresión con costo flow on the renderer side. Operator searches an ingreso by placa, types a `motivo` (≥10 chars per Zod), confirms via a `role="alertdialog"` (cobro consequence — REQ-OPS UI a11y convention). The page POSTs to F1.11's canonical endpoint `POST /api/v1/workflows/reimpresion-ticket` with `{motivo, uuid_ingreso, tipo}` and the F7.2 Idempotency-Key SHA-256 header. On 201, the page renders a success card with an "Anular" button that fires `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` (backend INSERTs a new row, never UPDATE — F1.11 DEC-TKT-02/03 invariant). The escposBuilder reimpresion case tightens with `0x1B 0x45`/`0x1B 0x46` (bold on/off) wrapping the inner body, plus a sello with accent + subline.

The 5 new REQ-OPS-171..175 extend the `operational` capability already consolidated in `openspec/specs/operations/spec.md`. Existing REQ-OPS-001..170 remain unchanged.

---

## ADDED Requirements

### REQ-OPS-171 — `<ReimprimirTiquete />` page with `role="alertdialog"` + Zod `motivo.min(10)`

The system SHALL render `<ReimprimirTiquete />` as a page at `/facturacion/reimprimir` with `role="alertdialog"` (cobro consequence). The form MUST validate `motivo: z.string().min(10)` client-side via RHF + Zod resolver before any POST. The page MUST support both `tipo: 'entrada' | 'salida'` via a RadioGroup selector.

#### Scenario: motivo corto blocked client-side (no POST)

- **Given** operator types motivo with 9 characters
- **When** submit fires
- **Then** the form MUST NOT POST
- **And** MUST render inline error via RHF + Zod (`reimprimir.errors.motivo_muy_corto` key)

#### Scenario: alertdialog confirms cobro

- **Given** motivo ≥10 chars + tipo selected
- **When** Confirm fires
- **Then** the alertdialog opens with cobro-consequence description
- **And** the alertdialog confirm fires `useReimprimir().trigger({uuid_ingreso, motivo, tipo})`

---

### REQ-OPS-172 — `escposBuilder.build('reimpresion', payload)` bold marca

The system SHALL tighten `escposBuilder.build('reimpresion', payload)` in `apps/electron-sucursal/src/lib/print/escposBuilder.ts` to wrap the inner body with `escBoldOn()` (`0x1B 0x45`) + `escBoldOff()` (`0x1B 0x46`). The "REIMPRESIÓN" label MUST appear in bold at the top.

#### Scenario: bold marca emitted

- **Given** `escposBuilder.build('reimpresion', mockPayload)` is called
- **When** the function returns
- **Then** the Buffer MUST contain `0x1B 0x45` BEFORE the inner body
- **And** `0x1B 0x46` AFTER the inner body
- **And** the "REIMPRESIÓN" literal MUST be present

---

### REQ-OPS-173 — `useReimprimir` SWR mutation hook

The system SHALL export `useReimprimir()` from `apps/electron-sucursal/src/features/facturacion/hooks/useReimprimir.ts` as a `useSWRMutation` hook. The `trigger({uuidIngreso, motivo, tipo})` function MUST:
- Compute `Idempotency-Key` SHA-256 via `buildIdempotencyKey` (F7.2).
- POST `/{uuid_ingreso}/reimprimir` with body `{motivo, tipo}` to `/api/v1/workflows/reimpresion-ticket`.
- On 201, parse via Zod mirror of `ReimpresionTicketRead` (F1.11).
- On 401, logout via `useAuthStore.clear()` + `parkos:auth:cleared` event (F3.1 invariant).

#### Scenario: 201 reimpresion charged + tiquete printed

- **Given** operator submits motivo (≥10 chars) + tipo
- **When** 201 returns
- **Then** `useReimprimir.trigger()` returns the `ReimpresionTicketRead` payload
- **And** `bridge.imprimir('reimpresion', payload)` MUST fire via `queueMicrotask`

---

### REQ-OPS-174 — `useAnularReimpresion` SWR mutation hook (INSERT-only chain)

The system SHALL export `useAnularReimpresion()` as a `useSWRMutation` hook. The `trigger({uuidReimpresion, motivoAnulacion})` function MUST POST `/{uuid}/anular` to create a NEW row with `uuid_reimpresion_padre` pointing at the original (NEVER UPDATE — F1.11 DEC-TKT-03 `[L-W]` invariant).

#### Scenario: anular creates new row (INSERT-only)

- **Given** operator clicks "Anular" on a reimpresion ticket
- **When** backend returns 201 with new uuid_reimpresion
- **Then** `useAnularReimpresion.trigger()` returns the new row payload
- **And** the original row MUST NOT be updated

#### Scenario: motivo_anulacion <10 chars blocked

- **Given** motivo_anulacion has 9 chars
- **When** submit fires
- **Then** the form MUST NOT POST (Zod pre-validation)

---

### REQ-OPS-175 — Drift anchor — `'reimpresion'` (NOT `'reimprimir'`)

The system SHALL use `'reimpresion'` as the canonical escposBuilder dispatcher key. The `plan.md` literal `'reimprimir'` is a corpus typo; the code uses `'reimpresion'` since F1.11. Any new reference MUST use `'reimpresion'` to preserve the live API surface.

#### Scenario: AST drift guard

- **Given** `git grep -nE "'reimprimir'" apps/electron-sucursal/src` runs
- **Then** it MUST return 0 matches (only `'reimpresion'` allowed)

---

## Drift Reconciliation

| Aspect | `plan.md` intent | F8.3 actual |
|---|---|---|
| Page with `role="alertdialog"` | UNCHANGED | F8.3 ships as new page |
| `escposBuilder.build('reimpresion', payload)` | EXISTS on dev from F1.11 + F7.3 | F8.3 tightens with bold marca |
| `useReimprimir` mutation hook | NEW | F8.3 ships (single-step POST) |
| `useAnularReimpresion` mutation hook | NEW | F8.3 ships |
| `motivo: z.string().min(10)` Zod | EXISTS (F1.11 backend) | F8.3 client-side Zod |

## Out of Scope

- Backend reimpresion_ticket table (F1.11 owns).
- Reimpresión gratuita inmediata (Fases 6/7).
- `prod.costos_servicios.concepto='reimpresion'` siembra (F1.11 MIGRATION 0029).

## Acceptance

- `useReimprimir.trigger()` posts `{motivo, tipo}` with Idempotency-Key.
- `escposBuilder.build('reimpresion')` emits bold marca `0x1B 0x45` / `0x1B 0x46`.
- `useAnularReimpresion` creates new row (insert-only).
- Drift guard: `'reimprimir'` returns 0 matches.
- e2e/reimpresion.spec.ts 3 scenarios pass.
- Final diff ≤ 800 LOC.

---

**End of delta spec — HU-F8.3.**
