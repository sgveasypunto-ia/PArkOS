# Proposal: HU-F10.2 — Cierre de turno (frontend delta)

## Intent

Complete the F3.3 `CerrarTurno` placeholder by chaining the partial-arqueo
substrate shipped in HU-F10.1 (`useArqueo.submit` + `<ArqueoSheet>` + escpos
`'arqueo'` dispatcher) with the F1.13 backend
`PUT /caja-sesion/sesion/{uuid}/cerrar` so the operator can close a shift
with a single confirmation.

The F3.3 placeholder shipped only the PUT leg with a stub form (`valor_final_*`
+ `observaciones_cierre`) and a logout-on-success redirect
(`/login?closed=true`). It never wrote an arqueo `[A]` row, never invoked
`POST /caja/arqueo` with `codigo='cierre_turno'`, and never enforced the
**mandatory** justification when there is a descuadre (the F10.1 arqueo
parcial has it as a refinement; cierre de turno promotes it to a hard
requirement per plan.md:2185-2205 verbatim).

This HU-F10.2 delta is therefore a strict completion, not a redesign: the
arqueo-first sequencing, the tolerance/justification wiring, and the
descuadre alerta follow the F10.1 substrate with two semantic upgrades —
strict-mode justification and session-close sequencing.

## Scope

### In Scope

- `CerrarTurno.tsx` orchestrator rewrite: chain
  `useArqueo().submit({ tipo_arqueo: 'cierre_turno', ... })` →
  `sesionActivaApi.cerrarSesion(uuid, ...)` in a single confirmation.
- `CerrarTurnoForm.tsx` extension: replace the F3.3 stub fields with
  inline arqueo inputs (`valor_efectivo_reportado`,
  `valor_datafono_reportado`, `justificacion` REQUIRED when `|diff|>0`)
  plus live diferencia feedback via `useArqueoResumen`.
- New `<ArqueoSheet requiredMode="cierre_turno">` prop (or a sibling
  inline `<CerrarTurnoArqueoForm>` shim) that flips the existing
  `superRefine` into a top-level `z.string().min(3)` requirement when
  `|diferencia_efectivo| + |diferencia_datafono| > 0`, preserving the
  F10.1 `arqueo-parcial` page behavior unchanged.
- Rollback-safe error mapping:
  - `409 sesion_ya_cerrada` (from PUT) → `<FormMessage role="alert">` +
    `navigate('/login')` (no `?closed=true`).
  - 5xx/network mid-flow (POST succeeded, PUT failed) → red banner
    "Arqueo registrado pero no se pudo cerrar sesión — contacte al
    supervisor". DO NOT attempt client-side rollback: no DELETE
    endpoint exists and `arqueo` is `[A]` (immutable by design).
  - `400 arqueo_invalid` (e.g. legacy key drift) → field-level Zod
    errors.
- i18n additions to `apps/electron-sucursal/src/renderer/i18n/locales/caja.json`:
  `cerrarTurno.titulo`, `cerrarTurno.subtitulo`, `cerrarTurno.arqueoJustificacionRequerida`,
  `cerrarTurno.errorSecuenciaParcial`, `cerrarTurno.errorCierreFallido`.
- e2e scenarios in `apps/electron-sucursal/e2e/arqueo.spec.ts` (extend
  the F10.1 spec, `test.skip` per F9.x precedent):
  1. happy path — diferencia === 0, both POST and PUT succeed,
     `bridge.imprimir('arqueo', { codigo: 'cierre_turno' })` called once,
     redirect to `/login?closed=true`.
  2. justificacion obligatoria — diferencia === -3000, submit button
     stays disabled until justificacion >= 3 chars.
  3. secuencia parcial (POST OK + PUT 409 sesion_ya_cerrada) — red
     banner shown, arqueo UUID surfaced for supervisor remediation.
- Unit tests for `CerrarTurno` orchestrator + `CerrarTurnoForm`
  (RED→GREEN per strict_tdd=true). New file
  `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.test.tsx`
  + extension to `CerrarTurnoForm.test.tsx`.

### Out of Scope

- Backend changes. `POST /caja/arqueo` (HU-F1.13), `PUT /caja-sesion/sesion/{uuid}/cerrar` (HU-F1.13),
  and `GET /caja/arqueo/resumen` (HU-F1.13) are already shipped.
- `CerrarTurnoForm.tsx` field-name compatibility with `SesionCerrarRequest`.
  The PUT body keeps the F3.3 `valor_final_efectivo` /
  `valor_final_datafono` / `observaciones_cierre` shape; the arqueo
  side uses the F10.1 `valor_efectivo_reportado` /
  `valor_datafono_reportado` shape. Both surfaces coexist; mapping is
  the orchestrator's responsibility.
- Cierre diario (HU-F10.3). F10.3 ships its own `useCierreDiario`
  helper and will reuse the substrate with `tipo_arqueo='cierre_dia'`.
- Logout-on-success semantics. The F3.3
  `useAuthStore.clear() + parkos:auth:cleared + navigate('/login?closed=true')`
  flow is preserved (see Open Question Q1).
- Tolerance UI rendering of `tolerancia_efectivo` / `tolerancia_datafono`.
  Carried from F10.1 ABBC-F10.1-BE-1 (backend `/caja/arqueo/resumen`
  does NOT yet expose the tolerance fields; FE defaults to 1_000 / 500
  COP). F10.2 inherits the same fallback; not a new drift anchor.

## Capabilities

> Section contract between proposal and `sdd-spec`.

### New Capabilities

None. The cierre-de-turno flow is an extension of the existing
`caja/arqueo` capability (F10.1 REQ-OPS-152..156) and the existing
`caja/sesion` capability (F3.3 REQ-OPS-027..029). No new top-level
domain area is introduced.

### Modified Capabilities

- `operations` (delta spec): append REQ-OPS-157..161 covering the
  cierre-de-turno sequencing, strict-mode justificacion, error
  mapping, and e2e coverage. The delta scope matches the F10.1
  precedent (REQ-OPS-152..156 appended in spec.md lines 5952-6144).

## Approach

1. **Substrate reuse** — call `useArqueo().submit({ ..., tipo_arqueo:
   'cierre_turno' })` exactly as F10.1 does for `tipo_arqueo:
   'auditoria'`. The F10.1 hook already accepts the `cierre_turno`
   discriminator (verified at `useArqueo.ts:32`). The F10.1 escpos
   dispatcher (`escposBuilder.build('arqueo', payload)`) already
   supports arbitrary `auditoria_codigo` — we pass
   `auditoria_codigo: 'cierre_turno'` and the body emits the same 12
   conceptual lines. The F10.1 tolerance default (1_000 / 500 COP)
   stays.

2. **Strict-mode justification** — promote the F10.1 `superRefine` to
   a top-level `z.string().min(3)` rule when
   `|diferencia_efectivo| + |diferencia_datafono| > 0`. Two design
   options, recommend (a):
   - **(a)** `<ArqueoSheet requiredMode?: 'auditoria' | 'cierre_turno'>`
     prop; `requiredMode='cierre_turno'` swaps the refinement for a
     hard `min(3)` (additionally disables the submit button while
     empty). F10.1 ArqueoParcial page keeps
     `requiredMode` undefined (legacy `superRefine` path). Default
     `undefined` keeps the F10.1 behavior bit-identical.
   - **(b)** Sibling `<CerrarTurnoArqueoForm>` component. Higher
     surface area, lower coupling to F10.1.
   - Pick (a) — minimal diff, single regression surface, F10.1
     `ArqueoParcial` page untouched.

3. **Sequencing** — `CerrarTurno.tsx` orchestrator calls
   `useArqueo().submit(...)` and awaits it BEFORE
   `sesionActivaApi.cerrarSesion(uuid, ...)`. If `submit` throws, do
   NOT call `cerrarSesion` — propagate the error. If `submit` resolves
   and `cerrarSesion` throws:
   - `SesionAlreadyClosedError` (404 `sesion_not_found`) → render
     `cerrarTurno.errorCierreYaCerrado` + `navigate('/login')` without
     `?closed=true` (F3.3 DEC-F3.3-07 precedent).
   - `ParkosHttpError` 5xx or network → render
     `cerrarTurno.errorCierreFallido` with the returned `arqueo.uuid`
     surfaced in the banner so the operator can quote it to the
     supervisor. Do NOT clear auth; the operator remains logged in
     for the retry under supervisor guidance.
   - `ParkosHttpError` 401 → existing F3.3 fallback
     (`useAuthStore.clear() + parkos:auth:cleared`).

4. **Logout-on-success** — KEEP the F3.3
   `useAuthStore.clear() + parkos:auth:cleared + navigate('/login?closed=true')`
   flow (DEC-F3.3-03 + e2e scenario E3 in `turno.spec.ts:148-198` +
   a11y scenario A1 in `turno.spec.ts:200-264`). Surfacing this as
   Open Question Q1 — the input slice drift anchor DA-F10.2-4 says
   "do NOT logout", but the F3.3 e2e specs (already merged to `dev`)
   assert logout + `?closed=true`. Resolution belongs to `sdd-spec`.

5. **i18n** — add 5 keys to `caja.json`:
   `cerrarTurno.titulo`, `cerrarTurno.subtitulo`,
   `cerrarTurno.arqueoJustificacionRequerida`,
   `cerrarTurno.errorSecuenciaParcial`,
   `cerrarTurno.errorCierreFallido`.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx` | Modified | Orchestrator rewrite: chain `useArqueo().submit({ tipo_arqueo: 'cierre_turno' })` → `sesionActivaApi.cerrarSesion(...)`. Preserve F3.3 logout-on-success per Q1. |
| `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx` | Modified | Replace stub fields with inline arqueo inputs + `useArqueoResumen` live diferencia. Pass `requiredMode='cierre_turno'` to `<ArqueoSheet>`. |
| `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx` | Modified | Add optional `requiredMode?: 'auditoria' \| 'cierre_turno'` prop; flip the `superRefine` to a hard `min(3)` rule when `'cierre_turno'`. Default `undefined` → unchanged behavior. |
| `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts` | None | F10.1 already exposes `submit({ ..., tipo_arqueo: 'cierre_turno' })`. No change. |
| `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` | Modified | Append 5 keys under `cerrarTurno.*`. |
| `apps/electron-sucursal/e2e/arqueo.spec.ts` | Modified | Append 3 F10.2 scenarios (happy path with `tipo_arqueo='cierre_turno'`, justificacion obligatoria, secuencia parcial). All `test.skip` per F9.x precedent. |
| `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.test.tsx` | New | Unit tests for orchestrator sequencing + error mapping. |
| `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.test.tsx` | Modified | Add strict-mode justification coverage. |
| `openspec/specs/operations/spec.md` | Modified | Append REQ-OPS-157..161 (delta spec; F10.1 precedent at lines 5952-6144). |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| **DA-F10.2-1** `justificacion` asymmetry — F10.1 had it optional with `superRefine`; F10.2 needs it mandatory when `|diff|>0`. Wrong wiring re-enables the F10.1 lenient path for cierre de turno. | High | `<ArqueoSheet requiredMode="cierre_turno">` prop flips the refinement to a top-level `min(3)` rule. Unit + e2e coverage for the disabled-while-empty path. Spec test asserts both paths in one test matrix. |
| **DA-F10.2-2** Sequencing rollback policy — POST /caja/arqueo succeeds but PUT /sesion/{uuid}/cerrar fails leaves an orphan arqueo `[A]` row + open session. No DELETE endpoint (architecture canon). | High | Document the no-rollback rule in the design. UX surfaces `arqueo.uuid` for supervisor remediation. Spec scenarios cover (a) PUT 5xx → banner with uuid, (b) PUT 409 → login redirect, (c) PUT 401 → F3.3 fallback. Add an entry to `pending-fase-10.md` for a future "arqueo orphan reconciler" job (out of F10.2 scope). |
| **DA-F10.2-3** Hook duplication — risk of a parallel `useCerrarTurno` hook. | Low | Recommendation in Approach §3: orchestrate inline in `CerrarTurno.tsx` using `useArqueo().submit` + `useSesionActiva()`. No new hook unless `sdd-design` finds material reuse benefit. |
| **DA-F10.2-4** Logout-on-success — input slice says "do NOT trigger logout"; F3.3 e2e specs (E3 + A1 in `turno.spec.ts`) assert `useAuthStore.clear() + navigate('/login?closed=true')`. | High | **Open Question Q1** — surface to `sdd-spec`. Recommended default: KEEP F3.3 behavior (logout + redirect). Justification: e2e E3 + A1 already merged, F3.3 DEC-F3.3-03 codifies it, `?closed=true` is the operator-facing success signal that the turno is closed. Changing it requires breaking the F3.3 e2e scenarios and is a Fase 3 behavior change outside F10.2 scope. |
| **DA-F10.2-5** (NEW) `justificacion` semantics vs F10.1 — F10.1 escpos body emits `Justificacion:` line only when `payload.justificacion.length > 0`. F10.2 cierre de turno REQUIRES `justificacion` when `|diff|>0` — but the printed tiquete does not visibly differentiate `auditoria` from `cierre_turno`. | Low | No escpos change required — the 12-line body is the same; the `auditoria_codigo` field already carries the discriminator. Verify in spec: `escposBuilder.build('arqueo', { ..., auditoria_codigo: 'cierre_turno' })` round-trips a tiquete with `Codigo: cierre_turno`. |
| **DA-F10.2-6** (NEW) Strict-TDD coverage budget — F10.2 adds 2 page-level files + 1 component diff + 3 e2e scenarios; tests-must-lead estimate ~200 LOC of new tests. Strict TDD: every behavior ships RED→GREEN. | Med | `sdd-tasks` MUST emit work-unit commits pairing tests with implementation (e.g. C1: RED tests for sequencing, C2: GREEN impl; C3: RED tests for strict-mode, C4: GREEN impl). Each commit stays well below the 800-LOC budget. |

## Rollback Plan

- All changes are frontend-only. Revert merge commit on `dev`; no
  backend migration touched.
- F10.1 substrate (`useArqueo`, `<ArqueoSheet>` `auditoria` path,
  escpos `'arqueo'`) is untouched in its public surface. The new
  `requiredMode` prop is additive (default `undefined` → F10.1
  behavior preserved bit-identical).
- `CerrarTurno.tsx` orchestrator is rewritten; revert restores the F3.3
  placeholder behavior (PUT only, logout on success). This is a
  known regression of F10.2 functionality, NOT of the surrounding
  flows.
- i18n additions are additive under the `cerrarTurno.*` namespace;
  removed cleanly with no impact on F10.1 keys.

## Dependencies

- F10.1 substrate (shipped on `dev` at merge SHA `033f654`):
  `useArqueo().submit`, `<ArqueoSheet>` (default `requiredMode`
  behavior), escpos `'arqueo'` dispatcher, ABBC-F10.1-BE-1 tolerance
  fallback (FE defaults 1_000/500 COP).
- F1.13 backend `POST /caja/arqueo` + `PUT /caja-sesion/sesion/{uuid}/cerrar`.
- F3.3 `useSesionActiva()` + `useAuthStore.clear()` + logout UX
  precedent (`turno.spec.ts` E3 + A1).
- The branch `feature/hu-f10-2-cierre-turno` is created from `dev`
  by the orchestrator at apply time, not by this proposal.

## Success Criteria

- [ ] `CerrarTurno` chains `useArqueo().submit({ tipo_arqueo:
      'cierre_turno' })` → `cerrarSesion(uuid, ...)` on a single
      confirmation.
- [ ] `justificacion` is REQUIRED (top-level `z.string().min(3)`,
      submit disabled) when `|diferencia_efectivo| +
      |diferencia_datafono| > 0`. OPTIONAL when diferencia === 0.
- [ ] F10.1 `<ArqueoSheet requiredMode={undefined}>` default behavior
      is bit-identical (existing ArqueoParcial page regression-clean).
- [ ] Error mapping verified: 409 `sesion_ya_cerrada` →
      `navigate('/login')` without `?closed=true`; 5xx / network after
      POST succeeds → red banner with `arqueo.uuid` surfaced; 401 →
      F3.3 fallback.
- [ ] `bridge.imprimir('arqueo', { ..., auditoria_codigo:
      'cierre_turno' })` fires exactly once on success (e2e scenario 1).
- [ ] axe-core WCAG 2.1 AA: zero violations on `/caja/cerrar-turno`
      (extends turno.spec.ts A1).
- [ ] New unit tests: `CerrarTurno.test.tsx` +
      `CerrarTurnoForm.test.tsx` extension; coverage threshold per
      `sdd-init/parkos` (80% lines).
- [ ] Strict-TDD discipline: every work-unit commit ships with the
      failing test (RED) and the passing implementation (GREEN) as
      paired commits; no commit lands impl without tests or vice versa.
- [ ] size: budget honored (≤800 LOC per PR). F10.1 size:exception
      (Engram #1894) is the ONLY ratified exception in this session;
      F10.2 and F10.3 each must fit. Forecast for F10.2: ~300 LOC
      (page rewrite + form diff + ArqueoSheet prop + 3 e2e stubs +
      unit tests) — well under budget.
