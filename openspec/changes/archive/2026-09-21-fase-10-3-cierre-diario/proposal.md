# Proposal: HU-F10.3 — Cierre Diario (Multi-Session Daily Reconciliation)

## Intent

Multi-session day-end reconciliation for cajero and supervisor. Surface per-session totals across all open sessions of the day, accept a single confirmation that closes ALL of them via `POST /caja/arqueo` with `tipo_arqueo='cierre_dia'` and `uuid_sesion=NULL`. Reuses F10.1 substrate (`useArqueo`, `useArqueoResumen`), F10.2 substrate (`requiredMode='cierre_dia'` discriminator on `<ArqueoSheet>`, escpos regex already extended per DA-F10.2-5). F1.13 backend endpoints already shipped per REQ-OPS-091..097.

## Scope

### In Scope
- New page `apps/electron-sucursal/src/features/caja/pages/CierreDiario.tsx` (page, NOT dialog).
- New pure helper `apps/electron-sucursal/src/features/caja/pages/cierreDiarioChain.ts` mirroring F10.2's `cerrarTurnoChain.ts`.
- New route `/caja/cierre-diario` in `apps/electron-sucursal/src/renderer/App.tsx`.
- New per-session sibling hook `useArqueoResumenPorSesion(uuid_sucursal, fecha)` in `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts` (returns array of per-session breakdowns — current `useArqueoResumen` is aggregate-only).
- Deprecate buggy `useCierreDiario()` (lines 100-118 of `useArqueo.ts` — passes `uuid_sesion: string` whereas backend closure requires `null`).
- i18n keys `cierreDiario.*` in `apps/electron-sucursal/src/renderer/i18n/locales/caja.json`.
- New e2e spec `apps/electron-sucursal/e2e/cierre-diario.spec.ts` (3-session fixture: 2 closed + 1 open; supervisor variant; fecha-boundary rejections).
- Delta spec REQ-OPS-163..168 appended to `openspec/specs/operations/spec.md` as Phase 24.

### Out of Scope
- ABBC-F10.2-BE-1 orphan arqueo reconciler (post-Fase-13 backend).
- Supervisor RBAC UI changes (route guards rely on existing `ProtectedRoute` — backend JWT scope is the gating factor).
- Modifications to F8.x `CierreDiarioDialog.tsx` (per-session quick close — orthogonal flow).

## Capabilities

### Modified
- `caja` capability — append Phase 24 (REQ-OPS-163..168): multi-session cierre diario flow, atomicity contract, aggregate-justification rule, supervisor permission grammar, fecha-boundary semantics. Delta spec at `openspec/changes/fase-10-3-cierre-diario/specs/spec.md`.

## Approach

Sequencer mirrors F10.2 but flattens to **2 steps**: (a) `POST /caja/arqueo` with `tipo_arqueo='cierre_dia'`, `uuid_sesion=null` — backend atomically inserts arqueo AND mass-closes all open sessions of the day within one tx; (b) ESC/POS print via `bridge.imprimir('arqueo', { auditoria_codigo: 'cierre_dia' })` — BORDER tolerant (does not abort flow on printer failure per F10.2 DA-F10.2-5).

**NO call to `useSesionActiva().cerrarSesion`** — the F3.3 logout-on-success trifecta (`useAuthStore.clear()` + `parkos:auth:cleared` event + `navigate('/login?closed=true')`) MUST NOT fire, because a supervisor may close OTHER operators' sessions while their own session is either (i) closed already or (ii) still open and intentionally remaining. Success navigates to `/` (Dashboard) with a confirm banner listing the closed sessions.

Per-session resumen rendered on the page itself (custom `<ResumenTablaSesiones>`), not on `<ArqueoSheet>` — `<ArqueoSheet requiredMode='cierre_dia'>` is reused only for the global-justification form below the table. Strict TDD — paired RED→GREEN commits (work-unit-commits skill); expect ~1500-2500 net LOC after test surface (F10.1 1566, F10.2 2037 precedent).

## Atomic Tasks

| ID | Scope | File | Method |
|----|-------|------|--------|
| T1 | schema+Zod | `api/schemas/cierreDiarioSchema.ts` (new) | RED: Zod tests; GREEN: schema |
| T2 | hook | `hooks/useArqueo.ts` (`useArqueoResumenPorSesion`) | RED: SWR array tests; GREEN: impl + deprecate `useCierreDiario()` |
| T3 | chain | `pages/cierreDiarioChain.ts` (new) | RED: pure-helper tests; GREEN: 2-step sequencer |
| T4 | form | `components/CierreDiarioForm.tsx` (new) | RED: react-hook-form tests; GREEN: form + aggregate-justification rule |
| T5 | page | `pages/CierreDiario.tsx` (new) | RED: orchestrator tests; GREEN: wire |
| T6 | route | `renderer/App.tsx` | RED: 404 test; GREEN: register `/caja/cierre-diario` |
| T7 | i18n | `renderer/i18n/locales/caja.json` | chore: `cierreDiario.*` keys |
| T8 | e2e | `e2e/cierre-diario.spec.ts` (new) | RED: spec fails; GREEN: passes with axe-core |

## Dependencies

- F10.2 REQ-OPS-158 discriminator `requiredMode='cierre_dia'` on `<ArqueoSheet>` (closed at F10.2 archive).
- F10.1 `useArqueo().submit` (write path) + `useArqueoResumen` (aggregate, used as fallback).
- F1.13 backend endpoints `GET /caja/arqueo/resumen?uuid_sucursal=X&fecha=Y` + `POST /caja/arqueo` with `uuid_sesion=NULL` (already shipped).
- Architectural canon: API op contract C/Q/U only — backend `sesion` UPDATE is bi-temporal close+insert.

## Risks

| # | Anchor | Detail | Likelihood | Carries to |
|---|--------|--------|------------|------------|
| R1 | DA-F10.3-1 | Multi-session atomicity — backend MUST close ALL open sessions or NONE; verify F1.13 handler commits within one tx; FE assumes all-or-nothing success. | High | spec |
| R2 | DA-F10.3-2 | Supervisor closes OTHER operator's session. JWT scope must include `perm_arqueo_cerrar_cualquiera`; verify in F1.13 JWT issuer config (admin- vs operador-). F3.3 + F10.2 only close own session — supervisor-only flow. | High | spec |
| R3 | DA-F10.3-3 | Fecha boundary — today default (writeable); past read-only (no new arqueo); future REJECTED. UI + Zod guards. | Med | spec |
| R4 | DA-F10.3-4 | Per-session resumen shape — `useArqueoResumen` returns aggregate (`sesiones_cerradas` count, NO list). Backend REQ-OPS-097 may not return per-session rows. If absent, spec must add backend delta (out-of-F10.3-scope by default). | Med | spec |
| R5 | DA-F10.3-5 | Aggregate-justification rule — if `Σ\|diferencia_cop\|>0` across all sessions, global `justificacion` OBLIGATORIA. Mirror F10.2 REQ-OPS-158. Per-session |diff|>0 contributes to aggregate. | Low | spec |
| R6 | DA-F10.3-6 | escpos `auditoria_codigo='cierre_dia'` already accepted via F10.2 C5 regex extension; no escpos changes. | Low | spec |
| R7 | DA-F10.3-7 | Existing `useCierreDiario()` helper (`useArqueo.ts:100-118`) passes `uuid_sesion: string`; collide with backend's `uuid_sesion=null` requirement. Deprecate (mark `@deprecated`, leave body unchanged) in same PR. | Med | spec |
| R8 | DA-F10.3-8 | Strict-TDD 5-7x forecast: 200 LOC nominal → 1000-1500 net LOC actual (F10.1=1566, F10.2=2037 precedent, both ratified size:exception per AGENTS.md). Each forecast must independently prove necessity. Don't pre-seek exception; let orchestrator's `delivery_strategy=ask-on-risk` route. | High | apply |

## Rollback Plan

Drop `/caja/cierre-diario` route from `renderer/App.tsx`; delete `CierreDiario.tsx` + `cierreDiarioChain.ts` + `cierreDiarioForm.tsx` + `cierre-diario.spec.ts`; deprecate marker reverts to active on `useCierreDiario()` (or just revert the helper file). Revert REQ-OPS-163..168 delta from `openspec/specs/operations/spec.md` (remove Phase 24 section). `useArqueoResumenPorSesion` becomes unreachable. No DB migration (frontend-only change).

## Success Criteria

- [ ] `npm run typecheck` clean (0 errors).
- [ ] `npm run lint` clean (0 new warnings on touched files).
- [ ] `npm run test:unit` passes (vitest): Zod schema, hook array variant, chain helper, form, page orchestrator.
- [ ] `npm run test:e2e` passes (playwright): `cierre-diario.spec.ts` covers 3-session fixture, supervisor variant, fecha-boundary rejects future.
- [ ] axe-core WCAG 2.1 AA: 0 violations on `/caja/cierre-diario` (page + form + table).
- [ ] Branch `feature/hu-f10-3-cierre-diario` merged `--no-ff` to `dev` per AGENTS.md gitflow.
- [ ] Delta spec REQ-OPS-163..168 synced to `openspec/specs/operations/spec.md` as Phase 24 (sdd-archive).
