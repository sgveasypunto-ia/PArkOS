# Proposal: Fase 6.1 — Flujo de ingreso vehicular (CU-01) en Principal.tsx

## Intent

Deliver the operator-facing vehicle-entry flow on `Principal.tsx` (Fase 6, CU-01, CU-15E): a single text field for plate input with auto-focus and uppercase normalization, an active-ingreso check that transparently redirects double-entry attempts to the SalidaFlow, server-derived `tipo_entrada` banner (Mensualidad vs Rotación, **never persisted**), forced-ingress modal when cupo is exhausted (Zod `min(10)` motivo, KD-FORZADO-01 prefix `[FORZADO: <motivo>]`), and automatic tiquete printing on `200` from `POST /operacion/ingresos` via the F5.1 bridge + F5.2 builder with a no-cost reprint button always available (DEC-SUC-27, E3 exemption). This is the first end-user-first CU in the closed mobile-e branch app.

## Scope

### In Scope

- `apps/electron-sucursal/src/features/operacion/{components,hooks,lib,pages}/PlacaInput.tsx|useIngresoActivo.ts|ingresoApi.ts|TiqueteModal.tsx|ForzarIngresoModal.tsx|Principal.tsx` — new feature folder.
- Reuse `apps/electron-sucursal/src/lib/validation/placa.ts::detectarTipoVehiculo()` + `REGEX_AUTO|MOTO` (F4.1) — strict, no typing tolerance (DEC-SUC-22).
- Reuse `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (F4.1) for the `tipo_entrada` display label.
- Reuse `parkosFetch` (DEC-SUC-04) with `Idempotency-Key = SHA-256(method+path+body)` + `X-Sucursal-Context` header on the mutation; SWR (DEC-SUC-05) for the read of `/operacion/ingresos?placa=X`.
- RHF + Zod (DEC-SUC-06) with `placaSchema` and `motivoForzadoSchema` colocated next to the form/feature that uses them.
- Auto-print on `200` via `bridge.imprimir(escposBuilder.build('entrada', payload))` (F5.1 + F5.2); manual "Imprimir" button always available for free reprint (DEC-SUC-27 + plan.md E3 exemption, distinct from `reimpresion_ticket` workflow in Fase 8).
- i18n keys in `apps/electron-sucursal/src/locales/es-CO.json` (operator-facing) and `en-US.json`/`pt-BR.json` (translations).

### Out of Scope

- **Backend changes**: `POST /operacion/ingresos` is closed by HU-F1.6 (F1.6 archive). F6.1 is renderer-only.
- Salida flow, cotización, pago (CU-02/03/04) → Fase 7 / Fase 8.
- Reimpresión con costo via `reimpresion_ticket` → Fase 8.
- The `EntradaPayload` typed schema — F6.2 owns it; F6.1 imports the typed interface from `escposTemplates.ts` (F5.2) once both land. If F6.2 hasn't merged yet, F6.1 declares a local inline interface mirroring the F5.2 `EntradaPayload` Zod schema — keep shape in sync.
- `log_transaccional(accion='impreso')` persistence (A-05) — F6.2 owns the backend write; F6.1's bridge call carries `uuidRegistro` so the F6.2 backend path can persist it.
- F4.3 `OcupacionStrip` component is **not a hard dependency** — F4.3 does not exist in any archive (verified). F6.1's `Principal.tsx` may render a lightweight inline cupo display by calling `GET /operacion/ocupacion` directly via SWR; the rich `OcupacionStrip` UI is deferred until F4.3 lands.
- The literal `GET /operacion/ingresos?placa=X&activo=true` endpoint does not exist in `api/v1/operacion.py` (see Spec §Open question / Blocker). F6.1 either uses the existing `GET /operacion/ingresos?placa=X` + `GET /operacion/ingresos/{uuid}/estado` composition or ships with a small companion backend PR adding `activo=true`. Resolved at design time.

## Capabilities

### New Capabilities

- **`operacion-ingreso`**: operator-facing vehicle-entry flow on `Principal.tsx` covering plate input, active-check redirect, server-derived tipo_entrada banner, forced-ingress modal with motivo, auto-print of tiquete de entrada, and idempotent POST.

### Modified Capabilities

- None. Existing `operations` spec (post-F1.6) covers server validation; F6.1 only adds a renderer consumer.

## Approach

RHF + Zod form colocated at the form component; SWR hook for the active-check read; `parkosFetch` POST with `Idempotency-Key` header (PR2 middleware already in place, F2.2 archive) for the mutation; result handler triggers F5.1 bridge call with F5.2 builder payload; `TiqueteModal` (role="dialog") shows success + manual reprint button; `ForzarIngresoModal` is a separate presentational component with its own Zod schema and minimal surface area. All async paths emit structured events for the operator: redirect to SalidaFlow on 409, error banner on 422, printer-offline banner on `printer_offline` IPC.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/features/operacion/**` | New | The new feature folder. |
| `apps/electron-sucursal/src/locales/{es-CO,en-US,pt-BR}.json` | Modified | Add `operacion.ingreso.*` namespace. |
| `apps/electron-sucursal/src/lib/validation/placa.ts` | Unchanged | Reuse F4.1 strict detector + regex constants. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` | Unchanged | Reuse F4.1 SWR hook for tipo display label. |
| `backend/packages/parkos_core/**` | Unchanged (F6.1 scope) | Optional companion backend task to add `activo=true` query param to `GET /operacion/ingresos` — see Spec §Open question. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Literal `GET /operacion/ingresos?placa=X&activo=true` endpoint missing in backend | Confirmed | Two-call composition (`list_ingresos?placa=X` + `ingresos/{uuid}/estado`) satisfies the active-check capability with zero backend change. Companion backend task T0 in tasks.md if operator prefers an explicit `activo` query param. |
| F4.3 `OcupacionStrip` does not exist (not in archive, not in active changes) | Confirmed | F6.1 ships an inline cupo display by calling `GET /operacion/ocupacion` directly. No F4.3 dependency. |
| `EntradaPayload` type not yet defined by F6.2 | Medium | Inline typed interface in F6.1 mirroring F5.2 `escposTemplates.ts` Zod schema; cross-coupling boundary documented; F6.2 ships the canonical schema and F6.1 imports it. |
| Duplicate POST (network retry by SWR/operator) | Low | `Idempotency-Key` header (DEC-SUC-04) makes re-submits return the same response. parkosFetch retry on 5xx only (DEC-SUC-04) — never on 4xx. |
| Printer offline (forced) | Medium | DEC-SUC-08 IPC fallback: tiquete queda en cola persistente (`parkos.print.queue.v1` electron-store, F5.1 R5) + non-blocking "Impresora no disponible, reintentando…" banner. Ingreso already persisted in DB. |
| Backend `POST /operacion/ingresos` returning 409 on duplicate-active | Already handled | UI does NOT show this as an error — transparent redirect to `SalidaFlow` (Fase 7 stub URL). Matches plan.md line 1507 + plan.md error table. |

## Rollback Plan

Renderer-only change. Revert the PR (git revert on `feature/hu-f6-1-flujo-ingreso`). Database INSERTs of `ingreso` rows persisted during the rolled-back window remain in the DB (insert-only, per ER canon). Operators must manually correct via `anulaciones` workflow (Fase 7) if needed — out of F6.1 scope. The new `src/features/operacion/` folder is fully removable in one commit (no shared types, no schema migration).

## Dependencies

- `apps/electron-sucursal/src/lib/validation/placa.ts` (F4.1, MERGED) — strict detector + regex constants.
- `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (F4.1, MERGED) — SWR hook for tipo label.
- `apps/electron-sucursal/src/services/parkosFetch.ts` (F2.2, MERGED) — Idempotency-Key + X-Sucursal-Context + 401 refresh.
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` + `escposTemplates.ts` (F5.2, MERGED) — `build('entrada', payload): Buffer` + `EntradaPayload` Zod schema.
- `apps/electron-sucursal/electron/bridge.d.ts` (F5.1, MERGED) — `bridge.imprimir({ buffer: base64 })` IPC contract.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (F1.6, MERGED) — `POST /operacion/ingresos` with full validation chain + `GET /operacion/ingresos` list + `GET /operacion/ingresos/{uuid}/estado` derived state + `GET /operacion/ocupacion`.
- F6.2 (Fase 6.2 — owner of canonical `EntradaPayload` type) — not blocking; F6.1 declares a local typed interface mirroring F5.2 Zod schema until F6.2 lands.

## Success Criteria

- [ ] 5 e2e scenarios green (plan.md F6.1): rotación, mensualidad, redirect on active, forzado con alerta, fallback térmico.
- [ ] `npx tsc --noEmit` y `npx eslint --max-warnings 0` exit 0 sobre los archivos nuevos.
- [ ] `@axe-core/playwright` WCAG 2.1 AA sin violaciones en `Principal.tsx` y sus 2 modales.
- [ ] `npx vitest run src/features/operacion` verde — unit tests de `useIngresoActivo` (SWR shape), `PlacaInput` (auto-focus + uppercase + submit por Enter), `ingresoApi` (Idempotency-Key derivation), `ForzarIngresoModal` (Zod `min(10)`).
- [ ] Smoke `npm run build` verde (electron-builder compila sin warnings nuevos).
- [ ] Conventional commits (sin Co-Authored-By); PR a `dev` (nunca `main`); author `Parkos Dev <dev@parkos.local>`.