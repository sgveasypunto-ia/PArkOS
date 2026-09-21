# Tasks: HU-F10.2 Cierre de Turno (frontend delta)

## Header

| Field | Value |
|---|---|
| Change | `fase-10-2-cierre-turno` |
| Phase | sdd-tasks |
| Inputs read | `openspec/changes/fase-10-2-cierre-turno/{proposal.md,specs/spec.md,design.md}` (Engram #1898, #1900, #1901), `plan.md:2185-2205` (HU-F10.2 T1..T2), `apps/electron-sucursal/package.json` (verified scripts), `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts` (89 LOC; no `cerrarSesion` method yet — AD-4 work is GREEN), `pending-fase-10.md` line 27 (ABBC-F10.2-BE-1 already present, REQ-OPS-162). |
| Status | ready-for-apply |
| Preflight | pace=`auto`, artifact=`hybrid`, delivery=`ask-on-risk`, chain=`gitflow`, budget=`800` LOC, strict_tdd=`true`, test_runner=`vitest` + `playwright` (`test.skip` per F9.x / Engram #1894) |
| LOC forecast | ~340 LOC across 8 work-unit commits |

## Objective

As an operador, I want to close my shift with a mandatory arqueo, leaving
my sesion formally closed. Given the arqueo with `codigo='cierre_turno'`,
when the operator confirms (justificacion **mandatory** when
`|diferencia_efectivo| + |diferencia_datafono| > 0` — strict-mode
promotion from the F10.1 lenient `superRefine`), then
`sesion.timestamp_cierre` / `sesion.uuid_usuario_cierre` are completed,
`sesion.estado='cerrada'`, and the F3.3 logout-on-success trifecta
(`useAuthStore.clear()` + `parkos:auth:cleared` + `navigate('/login?closed=true', { replace: true })`)
fires verbatim per `DEC-F3.3-03` + Engram #1899. `factura_pagos` is
untouched in every branch (CU-10 canon). (plan.md:2187 HU-F10.2.Historia.)

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~340 |
| 400-line budget risk | Low |
| 800-line budget risk | Low |
| Chained PRs recommended | No |
| Size exception needed | No |
| Decision needed before apply | No |
| Delivery strategy | ask-on-risk |
| Chain strategy | gitflow (single feature branch `feature/hu-f10-2-cierre-turno` from `dev`) |
| Suggested split | single PR (8 work-units stay paired within C1..C8) |

```text
Decision: single-pr
Chained PRs: No
Chain strategy: n/a
Delivery strategy: ask-on-risk
Size exception: No
Review budget risk: Low
Review budget hard limit: 800 lines
Forecast ~340 LOC actual
```

### Suggested Work Units (per `work-unit-commits` skill)

| Unit | Files touched | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|--------------|-----------|----------------------|-----------------|-------------------|
| C1 (RED scaffold) | `useSesionActiva.cerrarSesion.test.ts` (NEW), `ArqueoSheet.test.tsx` (NEW) | PR 1 (single) | `pnpm vitest run src/features/caja/hooks/__tests__/useSesionActiva.cerrarSesion.test.ts src/features/caja/components/__tests__/ArqueoSheet.test.tsx` | N/A — unit-only | Revert C1 only; no production code touched. |
| C2 (GREEN hook + prop) | `useSesionActiva.ts` (ADD `cerrarSesion` method), `ArqueoSheet.tsx` (ADD `requiredMode` prop + Zod branch) | PR 1 | same as C1 — must now pass | `pnpm dev:renderer` mount `/caja/arqueo` (F10.1 regression) — superRefine path bit-identical | Revert C2 restores F10.1 `ArqueoParcial` superRefine verbatim + removes cerrarSesion helper. |
| C3 (RED orchestrator) | `CerrarTurno.test.tsx` (NEW) — 8-case precedence + happy-path stubs | PR 1 | `pnpm vitest run src/features/caja/pages/__tests__/CerrarTurno.test.tsx` | N/A — unit-only | Revert C3 only; production page untouched. |
| C4 (GREEN orchestrator) | `CerrarTurno.tsx` (REWRITE: 112 → ~155 LOC) | PR 1 | same as C3 — must now pass; plus full FE for regression | `pnpm dev:renderer` navigate `/caja/cerrar-turno` → submit happy path → expect `/login?closed=true` | Revert C4 restores F3.3 placeholder (PUT-only stub form). |
| C5 (escpos regression) | `escposBuilder.test.ts` (NEW or extended) — 1 test asserting `build('arqueo', { auditoria_codigo: 'cierre_turno' })` round-trips | PR 1 | `pnpm vitest run src/lib/print/__tests__/escposBuilder.test.ts` | N/A — unit-only | Revert C5 only; no production change. |
| C6 (i18n + sidebar anchor) | `caja.json` (APPEND 6 keys under `cerrarTurno.*`); Dashboard sidebar (ADD anchor to `/caja/cerrar-turno`) | PR 1 | `pnpm vitest run src/renderer/i18n` + `pnpm tsc -b` | `pnpm dev:renderer` mount Dashboard — anchor visible | Revert C6 strips 6 keys + removes sidebar anchor. **NOTE**: route `App.tsx:62-65` already exists per REQ-OPS-157 — DO NOT modify App.tsx. |
| C7 (e2e extension) | `e2e/arqueo.spec.ts` (APPEND 3 `test.skip` scenarios per REQ-OPS-161) | PR 1 | `pnpm playwright test e2e/arqueo.spec.ts e2e/caja/turno.spec.ts` (NOT-FAIL per F9.x) | N/A — `test.skip` per Engram #1894 | Revert C7 strips 3 scenarios; F10.1 + F3.3 scenarios unaffected. |

Commit C8 (`apply-progress.md` + drift-anchor closure) is a chore-only
post-apply ledger commit — no code/test diff. Runs AFTER `sdd-apply`
lands and reports final SHAs. Documented in §Commit plan below.

## Commit plan (final order — strict TDD, RED→GREEN paired)

### C1 (RED scaffold)

- [ ] 1.1 NEW `apps/electron-sucursal/src/features/caja/hooks/__tests__/useSesionActiva.cerrarSesion.test.ts` with 3 RED stubs: `helper-1-200-clear-event` (asserts `useAuthStore.getState().accessToken === null` + `parkos:auth:cleared` fired on 200 + returns `{ ok: true }`), `helper-2-404-sesion-already-closed` (returns `{ ok: false, status: 404 }` with `SesionAlreadyClosedError`), `helper-3-401-fallback` (clear + event fired, returns `{ ok: false, status: 401 }`). All three must FAIL because `cerrarSesion` does not exist on the hook yet (REQ-OPS-160).
- [ ] 1.2 NEW `apps/electron-sucursal/src/features/caja/components/__tests__/ArqueoSheet.test.tsx` with 2 RED stubs: `regression-f10.1` (asserts `requiredMode={undefined}` + diferencia=-3000 with empty justificacion does NOT block initial render — F10.1 superRefine path bit-identical) and `strict-3-top-level-min3` (asserts `requiredMode='cierre_turno'` rejects with `justificacion_requerida` at the top level on render, button `disabled`, message text matches i18n key `cerrarTurno.arqueoJustificacionRequerida`). Both FAIL because the prop is not yet declared (REQ-OPS-158).
- [ ] 1.3 Verify RED: `pnpm vitest run src/features/caja/hooks/__tests__/useSesionActiva.cerrarSesion.test.ts src/features/caja/components/__tests__/ArqueoSheet.test.tsx` exits non-zero; commit as `test(caja): RED scaffold for HU-F10.2 cerrarSesion hook + ArqueoSheet requiredMode`. Author: `Parkos Dev <dev@parkos.local>` (gitflow).

### C2 (GREEN hook + prop)

- [ ] 2.1 MODIFY `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts`: extend `UseSesionActivaReturn` with `cerrarSesion: (uuid: string, payload: SesionCerrarRequest) => Promise<CerrarSesionResult>` + new types `CerrarSesionResult` (`{ ok: true; status: 200; sesion: SesionRead } | { ok: false; status: number; error: SesionAlreadyClosedError | ParkosHttpError | unknown }`). Implementation: `useCallback` wraps `sesionActivaApi.cerrarSesion(uuid, payload)`; on 200 calls `useAuthStore.getState().clear()` + `window.dispatchEvent(new Event('parkos:auth:cleared'))` and returns `{ ok: true }`; on non-2xx returns `{ ok: false, status, error }` preserving the typed exception; on 401 also fires clear+event per F3.3 fallback (REQ-OPS-160, AD-4).
- [ ] 2.2 MODIFY `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx`: add `requiredMode?: 'parcial' | 'cierre_turno' | 'cierre_dia'` to `ArqueoSheetProps`; branch the local Zod schema — when `requiredMode === 'cierre_turno'` or `'cierre_dia'` declare `justificacion` as top-level `z.string().trim().min(3, 'justificacion_requerida')` (NOT optional, NOT superRefine); keep the `superRefine` path verbatim when `requiredMode === 'parcial'` or `undefined` (F10.1 regression-clean); add `data-testid="arqueo-required-justificacion"` element; add `disabled={... || (requiredMode === 'cierre_turno' && justificacion.length < 3)}` to the Confirmar button (REQ-OPS-158, AD-1).
- [ ] 2.3 Verify GREEN: same C1 command now exits 0; commit as `feat(caja): GREEN — useSesionActiva.cerrarSesion helper + ArqueoSheet requiredMode prop (REQ-OPS-158, REQ-OPS-160)`.

### C3 (RED orchestrator tests)

- [ ] 3.1 NEW `apps/electron-sucursal/src/features/caja/pages/__tests__/CerrarTurno.test.tsx` with RED stubs for the 8-case precedence + happy path: `seq-1-happy-path` (POST 201 → PUT 200 → `useAuthStore.clear` + `parkos:auth:cleared` + `navigate('/login?closed=true', { replace: true })` + `bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_turno' })` fires exactly once); `post-1-zod`, `post-2-400-arqueo-invalid`, `post-3-5xx-no-cerrarsesion`, `post-4-network-no-cerrarsesion`; `put-1-404-sesion-not-found` (banner + navigate `/login`, no `?closed=true`); `put-2-409-sesion-ya-cerrada` (banner + `Ref: A` + `data-testid="cerrar-turno-orphan-uuid"` + no clear + no navigate); `put-3-5xx-orphan-uuid`; `put-4-401-f3.3-fallback`; `no-retry-1-assert-no-mock-retry`. Mock `useArqueo`, `useSesionActiva`, `useArqueoResumen`, `useAuthStore`, `useNavigate`, `bridge.imprimir`. All RED because orchestrator is still F3.3 placeholder (REQ-OPS-157, REQ-OPS-159).
- [ ] 3.2 Verify RED: `pnpm vitest run src/features/caja/pages/__tests__/CerrarTurno.test.tsx` exits non-zero; commit as `test(caja): RED — CerrarTurno orchestrator 8-case precedence + happy path (REQ-OPS-157, REQ-OPS-159)`.

### C4 (GREEN orchestrator)

- [ ] 4.1 REWRITE `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx` (112 → ~155 LOC): inline orchestrator per AD-2 — `try` block: `await useArqueo().submit({ uuid_sesion: sesion.uuid, tipo_arqueo: 'cierre_turno', valor_efectivo_reportado, valor_datafono_reportado, justificacion: justificacion || undefined })`; on success capture `{ uuid: A }` and call `bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_turno' })` exactly once (BEFORE the PUT); `await useSesionActiva().cerrarSesion(sesion.uuid, { valor_final_efectivo, valor_final_datafono, ...(observaciones_cierre ? { observaciones_cierre } : {}) })`; on `{ ok: true }` `navigate('/login?closed=true', { replace: true })`. Catch block (8-case precedence per AD-3): ZodError → `<FormMessage role="alert">`; `ParkosHttpError 400 arqueo_invalid` → field-level from `detail.campo[]`; `ParkosHttpError 5xx` (POST) → `cerrarTurno.errorArqueoFallido` banner, form editable, NO `cerrarSesion` call; TypeError (POST) → `cerrarTurno.errorRedArqueo` banner; `SesionAlreadyClosedError` (404) → `cerrarTurno.errorCierreYaCerrado` banner + `navigate('/login')` no `?closed=true`; `ParkosHttpError 409 sesion_ya_cerrada` → `cerrarTurno.errorCierreFallido` + `Ref: A` + `data-testid="cerrar-turno-orphan-uuid"` + no clear + no navigate; `ParkosHttpError 5xx` or network (PUT) → same as 409 with surfaced `uuid_arqueo`; `ParkosHttpError 401` (PUT) — handled inside helper per AD-4 — orchestrator only navigates `/login` no `?closed=true`. NO retry loop. NO client-side DELETE. Preserves F3.30 e2e scenarios E3 + A1 in `e2e/caja/turno.spec.ts` (REQ-OPS-157, REQ-OPS-159, AD-2, AD-3, AD-5, AD-6).
- [ ] 4.2 Verify GREEN: same C3 command exits 0; full FE suite stays green (`pnpm vitest run`); commit as `feat(caja): GREEN — CerrarTurno orchestrator: POST arqueo → PUT sesion → F3.3 logout (REQ-OPS-157, REQ-OPS-159)`.

### C5 (escpos regression guard — NO code change)

- [ ] 5.1 NEW or extend `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` with 1 test: `escpos-arqueo-cierre-turno-round-trip` — assert `build('arqueo', { auditoria_codigo: 'cierre_turno', ...VALID_ARQUEO_PAYLOAD })` produces the 12-line body shape with `Codigo: cierre_turno` (DA-F10.2-5 RESOLVED, AD-6).
- [ ] 5.2 Verify: `pnpm vitest run src/lib/print/__tests__/escposBuilder.test.ts` exits 0; commit as `test(escpos): regression — auditoria_codigo='cierre_turno' round-trip (DA-F10.2-5)`. MAY be merged with C2 if scope <200 LOC effective.

### C6 (i18n + sidebar anchor)

- [ ] 6.1 MODIFY `apps/electron-sucursal/src/renderer/i18n/locales/caja.json`: APPEND (do NOT replace) 6 keys under `cerrarTurno.*`: `titulo`, `subtitulo`, `arqueoJustificacionRequerida` ("Justificación requerida (mín. 3 caracteres)"), `errorArqueoFallido` ("Arqueo no registrado — reintente"), `errorRedArqueo` ("Sin conexión — verifique la red"), `errorCierreFallido` ("Arqueo registrado pero no se pudo cerrar sesión — contacte al supervisor. Ref: {{uuid}}"), `errorCierreYaCerrado` ("Arqueo registrado pero la sesión ya estaba cerrada — contacte al supervisor"), `orphanContactSupervisor` ("Conserve este UUID y contacte al supervisor"). Also en-US + pt-BR mirrors (REQ-OPS-157 + REQ-OPS-159).
- [ ] 6.2 MODIFY Dashboard sidebar component (likely `apps/electron-sucursal/src/features/dashboard/components/DashboardSidebar.tsx` or equivalent — verify at apply): anchor link to `/caja/cerrar-turno` with i18n key `cerrarTurno.titulo`. Mirror F10.1 anchor pattern for `/caja/arqueo-parcial`.
- [ ] 6.3 **DO NOT modify** `apps/electron-sucursal/src/renderer/App.tsx` — the route `/caja/cerrar-turno` already exists at line 62-65 (REQ-OPS-157 "MUST remain unchanged").
- [ ] 6.4 Verify: `pnpm vitest run src/renderer/i18n` + `pnpm tsc -b` exits 0; commit as `feat(caja): GREEN — i18n cerrarTurno.* keys + Dashboard sidebar anchor`.

### C7 (e2e extension)

- [ ] 7.1 MODIFY `apps/electron-sucursal/e2e/arqueo.spec.ts`: APPEND (do NOT delete or rename any F10.1 or F3.3 scenario) 3 NEW `test.skip` scenarios per REQ-OPS-161: (a) `e2e-1-happy-cierre-turno` — mount `/caja/cerrar-turno`, enter exact `valor_esperado_*` values, click Confirmar, assert POST body has `tipo_arqueo='cierre_turno'` + PUT body discriminator + `bridge.imprimir` called once with `auditoria_codigo='cierre_turno'` + URL === `/login?closed=true`; (b) `e2e-2-strict-mode-justificacion` — `valor_efectivo_reportado=97000` with `valor_esperado=100000` (diferencia=-3000), Confirmar disabled while `justificacion.length < 3`, enables after `>= 3`, POST body carries justificacion + descuadre alerta; (c) `e2e-3-f3.3-logout-regression` — happy path completion, `useAuthStore.getState().accessToken === null`, URL === `/login?closed=true`, `window.__lastClearedEvent === 'parkos:auth:cleared'`, F10.1 ArqueoParcial side effects clean. Reuse F10.1 fixtures (`VALID_ARQUEO_PAYLOAD` etc.) where possible. Mocks via `page.route('/api/v1/caja/arqueo', ...)` + `page.route('/api/v1/caja-sesion/sesion/:uuid/cerrar', ...)`. Axe-core check on `/caja/cerrar-turno` reports zero WCAG 2.1 AA violations.
- [ ] 7.2 Verify: `pnpm playwright test e2e/arqueo.spec.ts e2e/caja/turno.spec.ts` runs all `test.skip` per F9.x / Engram #1894 (NOT-FAIL); commit as `test(e2e): HU-F10.2 cierre-turno — 3 new test.skip scenarios (REQ-OPS-161)`.

### C8 (apply-progress + drift-anchor closure — chore-only post-apply)

- [ ] 8.1 After `sdd-apply` lands C1..C7, create `openspec/changes/fase-10-2-cierre-turno/apply-progress.md` with: final commit SHAs (`git log --format='%H %s' feature/hu-f10-2-cierre-turno..HEAD` after merge to `dev`), test command results (lint + tsc + vitest + axe-core screenshots), drift-anchor resolution map (DA-F10.2-1..6 → commit pointers per §Drift-anchor verification checklist below), Engram mirror link.
- [ ] 8.2 Confirm `pending-fase-10.md` line 27 item #4 (`ABBC-F10.2-BE-1`) is PRESERVED verbatim — `grep ABBC-F10.2-BE-1 pending-fase-10.md` returns the row. NOT marked RESOLVED at archive time (REQ-OPS-162).
- [ ] 8.3 Commit as `chore(sdd): HU-F10.2 apply-progress + drift-anchor ledger closure`. Author `Parkos Dev <dev@parkos.local>`.

## Drift-anchor verification checklist

| Anchor | Spec resolution | Commit pointer | Closure evidence |
|---|---|---|---|
| **DA-F10.2-1** `justificacion` asymmetry (strict-mode vs F10.1 lenient) | REQ-OPS-158: `<ArqueoSheet requiredMode>` prop discriminates strict-mode branch | **C2** (`ArqueoSheet.test.tsx::strict-3-top-level-min3` + `regression-f10.1`); **C4** (orchestrator passes `requiredMode='cierre_turno'`); **C7** (`e2e-2-strict-mode-justificacion`) | All three test files reference both paths. F10.1 `ArqueoParcial` regression-clean per REQ-OPS-158 scenario 1 (`ArqueoSheet.test.tsx::regression-f10.1`). |
| **DA-F10.2-2** Sequencing rollback policy — orphan arqueo (POST 201 + PUT fail) | REQ-OPS-159 cases 5-7: 8-case catch block + `data-testid="cerrar-turno-orphan-uuid"` banner + `Ref: {{uuid}}` + NO clear + NO navigate. ABBC-F10.2-BE-1 in `pending-fase-10.md` line 27. | **C4** (`CerrarTurno.test.tsx::put-1-404-sesion-not-found`, `put-2-409-sesion-ya-cerrada`, `put-3-5xx-orphan-uuid`, `no-retry-1-assert-no-mock-retry`); **C6** (i18n key `cerrarTurno.errorCierreFallido` with `Ref: {{uuid}}`); **C8** (preserve `pending-fase-10.md` line 27) | All 4 RED tests in C3 pass GREEN in C4; C8 chore preserves the ABBC forward reference. ABBC-F10.2-BE-1 remains `no bloquea F10.2` per REQ-OPS-162. |
| **DA-F10.2-3** Hook duplication (`useCerrarTurno`) | REQ-OPS-160: orchestrate inline; no new hook | **C2** (extends existing `useSesionActiva` with `cerrarSesion` method, NOT a new `useCerrarTurno` hook); **C4** (inline orchestrator in `CerrarTurno.tsx`) | `grep -r 'useCerrarTurno' apps/electron-sucursal/src` returns 0 matches after apply. |
| **DA-F10.2-4** Logout-on-success (Q1) | REQ-OPS-160 + Engram #1899: KEEP F3.3 trifecta verbatim | **C2** (helper does clear+event on 200 + 401 fallback); **C4** (`CerrarTurno.test.tsx::seq-1-happy-path` asserts `useAuthStore.clear` + `parkos:auth:cleared` + `navigate('/login?closed=true', { replace: true })`); **C7** (`e2e-3-f3.3-logout-regression` verifies `e2e/caja/turno.spec.ts` E3 + A1 stay green) | F3.30 e2e E3 + A1 in `e2e/caja/turno.spec.ts` UNTOUCHED (do not modify per REQ-OPS-161); C4 orchestrator `handleSuccess` mirrors F3.3 verbatim. |
| **DA-F10.2-5** ESC/POS body discriminator | REQ-OPS-161: no escpos change required; `escposBuilder.build('arqueo', payload)` already emits `Codigo: ${payload.auditoria_codigo}` | **C5** (`escposBuilder.test.ts::escpos-arqueo-cierre-turno-round-trip`); **C4** (`bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_turno' })` fires once on success path) | `escposBuilder.ts:498` UNCHANGED. C5 test pins the discriminator. |
| **DA-F10.2-6** Strict-TDD coverage budget | 8 paired work-unit commits, ~340 LOC, well under 800 | All of C1..C7 stay paired RED→GREEN; C8 is chore-only | `git diff --stat origin/dev..feature/hu-f10-2-cierre-turno` ≤800 LOC after merge; per-commit diffs ≤60 LOC. |

## Test commands summary (in order)

```bash
# 1. Lint — workspace-wide
cd apps/electron-sucursal && pnpm lint

# 2. Typecheck — workspace-wide (tsc -b per package.json line 20)
cd apps/electron-sucursal && pnpm typecheck

# 3. Focused vitest — new F10.2 test files (RED→GREEN tracked)
cd apps/electron-sucursal && pnpm vitest run \
  src/features/caja/hooks/__tests__/useSesionActiva.cerrarSesion.test.ts \
  src/features/caja/components/__tests__/ArqueoSheet.test.tsx \
  src/features/caja/pages/__tests__/CerrarTurno.test.tsx

# 4. Full FE vitest — regression sweep (F10.1 ArqueoParcial + F3.3 CerrarTurno stub + F10.2 new)
cd apps/electron-sucursal && pnpm vitest run

# 5. Playwright e2e — NOT-FAIL per F9.x / Engram #1894 (all test.skip)
cd apps/electron-sucursal && pnpm playwright test \
  e2e/arqueo.spec.ts e2e/caja/turno.spec.ts

# 6. i18n key parity check (manual grep — no script needed)
cd apps/electron-sucursal && grep -c "cerrarTurno\." src/renderer/i18n/locales/caja.json
# Expect: ≥6 keys across es-CO + en-US + pt-BR mirrors
```

## Risk acknowledgements (copy from design §Risk acknowledgements)

| Risk | Status | Residual |
|---|---|---|
| **DA-F10.2-1** `justificacion` asymmetry (strict-mode vs F10.1 lenient) | RESOLVED | AD-1 + REQ-OPS-158 prop branch + REQ-OPS-158 scenarios 1-2. F10.1 ArqueoParcial regression-clean (REQ-OPS-158 scenario 1). Unit + e2e coverage is the long-term backstop. |
| **DA-F10.2-2** Orphan arqueo (POST 201 + PUT fail) | RESOLVED (interim) | AD-3 cases 5-7 + ABBC-F10.2-BE-1 forward reference (pending-fase-10.md item #4, preserved). FE surfaces `uuid_arqueo` via `data-testid="cerrar-turno-orphan-uuid"` for supervisor-driven remediation. Long-term reconciler is post-Fase-13 backend admin. |
| **DA-F10.2-3** Hook duplication (`useCerrarTurno`) | RESOLVED | AD-2 inline orchestrator. REQ-OPS-160 forbids preemptive extraction; F11.x may extract `usePostCerrarSesion()` if material, but is out of F10.2 scope. |
| **DA-F10.2-4** Logout-on-success (Q1) | RESOLVED (pre-spec, Engram #1899) | AD-5 verbatim. F3.30 e2e scenarios E3 + A1 in `e2e/caja/turno.spec.ts` are the regression guard. Any deviation requires a Fase 3 follow-up HU. |
| **DA-F10.2-5** ESC/POS body discriminator | RESOLVED (no code change) | AD-6. `escposBuilder.build('arqueo', payload)` already emits `Codigo: ${payload.auditoria_codigo}`; `cierre_turno` flows through unchanged. 12-line body shape identical to F10.1. |
| **DA-F10.2-6** Strict-TDD coverage budget | RESOLVED | 8 paired work-unit commits (C1..C8) per work-unit-commits skill. Total ~340 LOC, well under 800-LOC budget per commit. |
| **NEW** — F10.3 forward hook (`requiredMode='cierre_dia'`) | FORWARDED | `ArqueoSheet requiredMode='cierre_dia'` discriminator member ships at F10.2 (REQ-OPS-158 closed at F10.2). F10.3 owns the `<CierreDiarioDialog>` consumer. F10.2 does NOT wire the consumer. |
| **NEW** — Substrate path drift | RESOLVED (verified) | All file paths in spec + design match live tree: `apps/electron-sucursal/src/features/caja/{pages,components,hooks,api}/...` + `apps/electron-sucursal/src/renderer/{App.tsx,i18n/locales/caja.json}` + `apps/electron-sucursal/e2e/{arqueo,caja/turno}.spec.ts`. |
| **NEW** — `useAuthStore.clear()` dual invocation | RESOLVED | `useSesionActiva().cerrarSesion` helper does clear+event on 200 (AD-4). Orchestrator success path does NOT re-invoke clear (helper owns it); orchestrator only does `navigate('/login?closed=true', { replace: true })`. |

## Open decisions

None. AD-1..AD-6 are ratified inputs in design.md. Engram #1899 closes Q1
pre-spec (logout-on-success). The 8-case error precedence is enumerated
exhaustively (no missing case: ZodError, 400, 5xx, network on POST; 404,
409, 5xx, network on PUT, plus 401 fallback inside helper). ABBC-F10.2-BE-1
in `pending-fase-10.md` line 27 is preserved verbatim — forward reference
for the long-term arqueo orphan reconciler (post-Fase-13 backend admin).

## Relevant files

- `openspec/changes/fase-10-2-cierre-turno/{proposal.md,specs/spec.md,design.md,tasks.md}` — this change artifact set
- `openspec/specs/operations/spec.md` line 6068+ — REQ-OPS-157..162 appended at archive
- `plan.md:2185-2205` — HU-F10.2 source (HU-F10.2.Historia)
- `pending-fase-10.md` line 27 — ABBC-F10.2-BE-1 (PRESERVE verbatim)
- `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx` — REWRITE in C4
- `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx` — MODIFY in C2 (AD-1)
- `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx` — MODIFY in C4 (inline arqueo inputs + i18n)
- `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts` — MODIFY in C2 (AD-4)
- `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts` — UNCHANGED (F10.1 substrate)
- `apps/electron-sucursal/src/renderer/i18n/locales/caja.json` — APPEND 6+ keys in C6
- `apps/electron-sucursal/src/renderer/App.tsx` — UNCHANGED (route already exists at line 62-65)
- `apps/electron-sucursal/src/lib/print/escposBuilder.ts` — UNCHANGED (DA-F10.2-5)
- `apps/electron-sucursal/e2e/arqueo.spec.ts` — APPEND 3 `test.skip` scenarios in C7
- `apps/electron-sucursal/e2e/caja/turno.spec.ts` — UNCHANGED (F3.3 regression guard per REQ-OPS-161)
- NEW `apps/electron-sucursal/src/features/caja/pages/__tests__/CerrarTurno.test.tsx` (C3/C4)
- NEW `apps/electron-sucursal/src/features/caja/components/__tests__/ArqueoSheet.test.tsx` (C1/C2)
- NEW `apps/electron-sucursal/src/features/caja/hooks/__tests__/useSesionActiva.cerrarSesion.test.ts` (C1/C2)
- NEW or extended `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.test.ts` (C5)

## Implementation order (recommended)

1. `git fetch --prune origin && git checkout dev && git merge --ff-only origin/dev`
2. `git checkout -b feature/hu-f10-2-cierre-turno`
3. C1 (RED) → C2 (GREEN) → C3 (RED) → C4 (GREEN) → C5 → C6 → C7 (each ≤60 LOC delta; verify after each commit)
4. `git push -u origin feature/hu-f10-2-cierre-turno`
5. `gh pr create --base dev --head feature/hu-f10-2-cierre-turno --title "feat(caja): HU-F10.2 Cierre de turno — arqueo + cierre secuenciados (REQ-OPS-157..162)" --body-file openspec/changes/fase-10-2-cierre-turno/proposal.md`
6. After PR merge to `dev`: C8 chore commit (`apply-progress.md` + Engram mirror)
7. Orchestrator: `git merge --ff-only` (descendant of `dev`) + `git push origin dev` per AGENTS.md gitflow canon