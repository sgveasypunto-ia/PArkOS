# Tasks: Fase 6.1 — Flujo de ingreso vehicular (CU-01 + CU-15E)

> **Change**: `fase-6-1-flujo-ingreso`
> **Phase**: tasks (sdd-tasks)
> **Inputs read**: `design.md` §Data Flow §File Changes; `specs/operacion-ingreso.md` §ADDED Requirements §Error Catalog; `proposal.md` §Scope §Dependencies; existing F4.3 hook pattern (`useOcupacion.ts`) + F4.1 detector (`placa.ts`).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~540 (renderer + bridge + e2e) |
| 400-line budget risk | Low |
| Chained PRs recommended | No (single-feature, low risk, renderer-only) |
| Suggested split | single PR to `feature/hu-f6-1-flujo-ingreso` |
| Delivery strategy | auto-chain |
| Chain strategy | pending (T0a is a tiny sibling PR to the bridge contract — not chained to F6.1) |
| Decision needed before apply | No (Path 1 locked) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Bridge buffer extension (T0a) | T0a PR | `tsc --noEmit` + `npm run test:bridge` | `npm run dev:electron` + manual ticket print | Revert PR; existing `bridge.imprimir({ lines })` callers unaffected |
| 2 | F6.1 feature end-to-end | F6.1 PR (single, 9 tasks) | `vitest run src/features/operacion` + `e2e operacion/ingreso.spec.ts` | `npm run dev:electron` against mock backend | Single revert of `src/features/operacion/**` + i18n delta |

## Phase 0: Bridge Prerequisite (sibling PR, merge FIRST)

- [x] **T0a** Extend `electron/bridge.d.ts::PrintPayload` with `buffer?: string` (base64) discriminated against existing `lines?: PrintLine[]`; update `electron/preload.ts` whitelist to route `buffer` payload to escpos-usb consumer.

## Phase 1: HTTP Layer (lib + api)

- [x] **T1** Create `src/features/operacion/lib/canonicalJson.ts` with deterministic `canonicalJSON(value)` (sorted keys, primitive strip) — pure function, 1 test for sorted-key stability.
- [x] **T2** Create `src/features/operacion/api/ingresoActivoApi.ts` exporting `getIngresosByPlaca(placa): Promise<Ingreso[]>` — wraps `parkosFetch('/api/v1/operacion/ingresos?placa=X')` and parses with `IngresoArraySchema`.
- [x] **T3** Create `src/features/operacion/lib/ingresoApi.ts` exporting `postIngreso(payload, idempotencyKey?): Promise<PostIngresoResponse>`; default `idempotencyKey = SHA-256('POST:/operacion/ingresos:' + canonicalJSON(payload))` per DEC-SUC-04. Unit test 3 scenarios from spec §Idempotent POST (double-press / body mutation / network retry).

## Phase 2: React Layer (hooks + components + page)

- [x] **T4** Create `src/features/operacion/hooks/useIngresoActivo.ts` — SWR hook returning `IngresoActivoState = { hasActive, latestIngreso, isLoading, error }`. Client-side filter: `latestIngreso = ingresos.sort((a,b)=> b.fecha_ingreso.localeCompare(a.fecha_ingreso))[0]` (Path 1 simplification documented in design §Open Questions). Mirrors `useOcupacion` shape (SWR key gated by `accessToken`, `shouldRetryOnError` excludes 401/403/404, 401 → `useAuthStore.clear()` + `parkos:auth:cleared`).
- [x] **T5** Create `src/features/operacion/components/PlacaInput.tsx` — RHF+Zod with `placaSchema = z.string().regex(REGEX_AUTO|REGEX_MOTO)` (import from `lib/validation/placa.ts`); `useRef<HTMLInputElement>` auto-focus on mount; uppercase normalization via `detectarTipoVehiculo`; submit on Enter; inline error reuses `operacion.json:placa_formato_invalido`.
- [x] **T6** Create `src/features/operacion/components/ForzarIngresoModal.tsx` — shadcn Dialog; `motivoSchema = z.string().min(10)`; on confirm POST retries with `observaciones: '[FORZADO: ' + motivo + ']', forzado: true` per A-04 + KD-FORZADO-01; inline error message from `operacion.json`.
- [x] **T7** Create `src/features/operacion/components/TiqueteModal.tsx` — shadcn Dialog with `role="dialog"` (axe-core target); Imprimir button → `escposBuilder.build('entrada', buildEntradaPayload(...)).toString('base64')` then `window.bridge.imprimir({ buffer, ticketId: uuid_ingreso })` per F6.2 integration doc; Siguiente button → reset form + clear `useIngresoActivo` cache via `mutate()`.
- [x] **T8** Create `src/features/operacion/pages/Principal.tsx` — page container; orchestrates `useIngresoActivo`, `<PlacaInput>`, inline `<OcupacionStrip>` (lightweight, from `useOcupacion`), `<ForzarIngresoModal>` on `422 motivo_forzado_requerido`, redirect to `/operacion/salida?uuid_ingreso=…` placeholder URL on `409 ingreso_activo_existente` (transparent, no error toast per plan.md line 1530), auto-print trigger on `201`.

## Phase 3: i18n + E2E (delta)

- [x] **T9** Add 8 keys to `src/renderer/i18n/locales/operacion.json`: `ingreso_placa_label`, `ingreso_mensualidad_activa`, `ingreso_rotacion_label`, `ingreso_forzar_title`, `ingreso_motivo_label`, `tiquete_entrada_imprimir`, `tiquete_entrada_siguiente`, `ingreso_printer_offline`. Reuse existing keys `placa_formato_invalido`, `ingreso_registrado_exitoso`, `tiquete_entrada_titulo`, `ingreso_observaciones_forzado`.

## Phase 4: Verification

- [x] **T10** Create `apps/electron-sucursal/e2e/operacion/ingreso.spec.ts` — 5 scenarios per plan.md F6.1: (E1) rotación happy path, (E2) mensualidad banner, (E3) transparent redirect on doble-ingreso → `SalidaFlow` placeholder, (E4) forzado `422 motivo_forzado_requerido` → modal accepts `≥10 chars`, (E5) `bridge.imprimir` rejects `printer_offline` → ingreso persists + banner visible; + 1 axe-core WCAG 2.1 AA snapshot on `Principal.tsx` + 2 modals. Spec runs in CI (skipped in sandbox per F4.3 precedent).

## Implementation Order

T0a MUST land before T8 (page render calls `bridge.imprimir({ buffer, ticketId })`). T1 → T2 feed `Principal.tsx`; T3 must land before T8 (page calls `postIngreso`). T4..T7 are sibling components, can be parallelized. T9 is post-merge canary in the e2e harness.

## Next Step

Ready for `sdd-apply` on `feature/hu-f6-1-flujo-ingreso`. Apply launches T0a as a sibling PR first (1 reviewer, ~10 LOC + tests), then T1..T9 in a single F6.1 PR to `dev` (per AGENTS.md gitflow).
