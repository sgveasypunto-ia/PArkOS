# Delta Spec: `operations` — HU-F10.2 Cierre de Turno (frontend)

## Phase

HU-F10.2 (Fase 10, segunda de 3). Frontend-only delta over the base spec
`operations` (REQ-OPS-091..097 shipped en F1.13 backend; REQ-OPS-027..029
shipped en F3.3 sesion cycle; REQ-OPS-152..156 shipped en F10.1 arqueo
parcial). Branch `feature/hu-f10-2-cierre-turno` (created from `dev`).
Author `Parkos Dev <dev@parkos.local>`. Strict-TDD ACTIVE.
800-LOC review budget per `openspec/chores.tasks` (HU forecast ~300 LOC:
CerrarTurno rewrite + CerrarTurnoForm diff + ArqueoSheet prop + CerrarTurno
unit tests + 3 e2e scenarios + 1 ABBC forward reference).

## Gap

`REQ-OPS-157..162` — the next six correlatives free after `REQ-OPS-156`
(F10.1 archive; live in `openspec/specs/operations/spec.md:6068`).
NOT reusing the `091..097` range (F1.13 backend, immutable) nor the
`027..029` range (F3.3 sesion cycle, already shipped) nor the
`152..156` range (F10.1 substrate, already shipped). Numbering verified
by `Select-String -Pattern "^### REQ-OPS-\d+" openspec/specs/operations/spec.md | Select-Object -Last 10`:
last entry is `REQ-OPS-156` (line 6068).

Q1 (logout-on-success) is **pre-resolved** by Engram `#1899` (decision
ratified 2026-09-21): **KEEP F3.3 logout behavior** (`useAuthStore.clear()`
+ `dispatchEvent('parkos:auth:cleared')` + `navigate('/login?closed=true',
{ replace: true })`) — codified by `DEC-F3.3-03` and asserted by F3.30 e2e
scenarios E3 + A1 in `e2e/caja/turno.spec.ts`. This delta MUST inherit that
behavior verbatim; any deviation requires a Fase 3 follow-up HU, NOT a
F10.2 spec change.

## ADDED Requirements

### REQ-OPS-157 — `CerrarTurno` page chains `POST /caja/arqueo` (tipo_arqueo='cierre_turno') + `PUT /caja-sesion/sesion/{uuid}/cerrar` on a single confirmation

**Given** the F3.3 placeholder at
`apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx:1-112`
ships the `cerrarSesion` leg only (PUT leg with stub fields
`valor_final_efectivo` + `valor_final_datafono` + `observaciones_cierre`)
and the F10.1 substrate at
`apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts:30-44`
already exposes `submit({ ..., tipo_arqueo: 'auditoria' | 'cierre_turno'
| 'cierre_dia' })`
**When** `sdd-apply` rewrites the orchestrator
**Then** the `CerrarTurno.tsx` `onSubmit` handler MUST first await
`useArqueo().submit({ uuid_sesion: sesion.uuid, tipo_arqueo: 'cierre_turno',
valor_efectivo_reportado, valor_datafono_reportado,
justificacion: justificacion || undefined })` and MUST then await
`cerrarSesion(sesion.uuid, { valor_final_efectivo,
valor_final_datafono, ...(observaciones_cierre ? { observaciones_cierre }
: {}) })` in that exact order, both inside the SAME `try { ... } catch`
block
**And** if `useArqueo().submit(...)` throws (Zod validation,
`ParkosHttpError` 4xx/5xx, network), the orchestrator MUST NOT call
`cerrarSesion(...)` — the error propagates to the form's
`<FormMessage role="alert">` and the sesion remains OPEN
**And** the `<ArqueoSheet>` instance MUST NOT be rendered inside the
`CerrarTurno` route — the inline arqueo inputs live inside
`<CerrarTurnoForm>`, NOT inside a drawer (REQ-OPS-152 F10.1 substrate
owns the drawer for ArqueoParcial; reuse on CerrarTurno would create a
competing drawer instance per F10.1 drift anchor #2)
**And** the route `apps/electron-sucursal/src/renderer/App.tsx:62-65`
(`/caja/cerrar-turno` → `<CerrarTurno />`) MUST remain unchanged
**And** the page MUST preserve F3.3 WCAG 2.1 AA semantics: shadcn
`<Form>` primitives provide `aria-invalid` + `aria-describedby` +
`<FormMessage role="alert">` automatically; axe-core MUST report zero
violations on the route.

#### Scenario: happy path with `|diferencia_efectivo|=0` saves arqueo + closes sesion + redirects

- **Given** an operador is authenticated, `useSesionActiva()` returns
  `{ sesion.uuid: S }`, and the live `useArqueoResumen` returns
  `valor_esperado_efectivo=100000`, `valor_esperado_datafono=0`,
  `tolerancia_efectivo=1000`, `tolerancia_datafono=500`
- **When** the operator enters `valor_efectivo_reportado=100000`,
  `valor_datafono_reportado=0`, leaves `justificacion` empty, and clicks
  Confirmar
- **Then** the orchestrator MUST call `useArqueo().submit({ uuid_sesion: "S",
  tipo_arqueo: "cierre_turno", valor_efectivo_reportado: 100000,
  valor_datafono_reportado: 0 })` (no `justificacion` field — `|diff|=0`)
  → backend returns `201 { uuid: A }`
- **And** the orchestrator MUST then call
  `cerrarSesion("S", { valor_final_efectivo: 100000,
  valor_final_datafono: 0 })` → backend returns `200`
- **And** the orchestrator MUST then call `useAuthStore.getState().clear()`
  + `dispatchEvent(new Event('parkos:auth:cleared'))` +
  `navigate('/login?closed=true', { replace: true })`
  (`DEC-F3.3-03` canon, exact verbatim)
- **And** `bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_turno'
  })` MUST fire exactly once (F10.1 escpos dispatcher, no F10.2 change)

#### Scenario: `|diferencia_efectivo|=3000` (exceeds tolerancia) requires `justificacion.min(3)`

- **Given** the resumen returns `valor_esperado_efectivo=100000`,
  `tolerancia_efectivo=1000`, and the operator enters
  `valor_efectivo_reportado=97000` (diferencia = -3000)
- **When** the form is rendered without `justificacion`
- **Then** the submit button MUST be disabled
  (`disabled={form.formState.isSubmitting || !justificacionValid}`)
- **And** after the operator types `justificacion.length >= 3`, the
  button re-enables, submission proceeds with the justificacion field,
  the backend records `alerta 'descuadre_critico'` per
  REQ-OPS-094 (inserta via `alerta_tipos='descuadre_critico'` trigger on
  `arqueo` row when `|diferencia| > tolerancia_efectivo` AND
  `tipo_arqueo='cierre_turno'`)
- **And** the sequencer completes with the `?closed=true` redirect
  unchanged from the happy path

#### Scenario: PUT `409 sesion_ya_cerrada` after POST 201 — orphan arqueo surfaced

- **Given** the POST succeeds and returns `{ uuid: A }`, then the PUT
  returns `409 {"error": "sesion_ya_cerrada"}` (the sesion was already
  closed by a parallel operator action or by the backend timeout race)
- **When** the orchestrator's catch block inspects the error
- **Then** the orchestrator MUST render the red banner
  `cerrarTurno.errorCierreYaCerrado` (i18n key) with the literal
  text "Arqueo registrado pero la sesión ya estaba cerrada — contacte
  al supervisor" AND MUST surface the `uuid` value `A` as
  `data-testid="cerrar-turno-orphan-uuid"` for the supervisor
  remediation script (ABBC-F10.2-BE-1 future reconciler)
- **And** the orchestrator MUST NOT call `useAuthStore.clear()` — the
  operator remains logged in
- **And** the orchestrator MUST NOT call `navigate()` — the route stays
  mounted so the operator can read the banner

### REQ-OPS-158 — `<ArqueoSheet>` `requiredMode` prop promotes `justificacion` to top-level `z.string().min(3)` when set to `'cierre_turno'`

**Given** the current `ArqueoSheet` at
`apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx:48-66`
declares a single `arqueoSchema` with a `superRefine` that requires
`justificacion.min(3)` ONLY when `|diferencia|>0` (F10.1 lenient path),
and the F10.1 `<ArqueoParcial>` page consumes `<ArqueoSheet>` without
any `requiredMode` prop (F10.1 default behavior is bit-identical to
F10.1 REQ-OPS-154)
**When** `sdd-apply` extends the `<ArqueoSheet>` prop surface
**Then** the `ArqueoSheetProps` interface MUST grow an optional
discriminator field `requiredMode?: 'parcial' | 'cierre_turno' |
'cierre_dia'` (the literal `'auditoria'` MUST NOT be accepted — F10.1
drawer calls it `'auditoria'` but the prop is keyed on the UI surface
role, not the backend discriminator; the backend discriminator is
inside `useArqueo().submit({ tipo_arqueo })` and is separate)
**And** when `requiredMode === 'cierre_turno'`, the Zod schema MUST
branch to a strict-mode variant where `justificacion` is declared at
the top level as `z.string().trim().min(3, 'justificacion_requerida')`
(NOT `.optional()`, NOT behind `superRefine`); the refinement
`Math.abs(diferencia_efectivo) + Math.abs(diferencia_datafono) > 0` is
applied separately as an `<Alert variant="warning">` UI affordance but
MUST NOT gate the validation
**And** when `requiredMode === 'parcial'` (the F10.1 'arqueo parcial'
page) or `requiredMode` is `undefined` (the F10.1 default), the schema
MUST keep the existing `superRefine` path verbatim — the existing
`ArqueoParcial` page (REQ-OPS-152) MUST remain regression-clean
**And** when `requiredMode === 'cierre_dia'`, the strict-mode variant
MUST apply identically to `cierre_turno` (F10.3 will reuse this branch;
F10.2 ships the union member but F10.3 is responsible for the consumer)
**And** the `<ArqueoSheet>` MUST also disable its Confirmar button
(`disabled={... || (requiredMode === 'cierre_turno' &&
justificacion.length < 3)}`) when the strict-mode variant fails the
top-level check — visual feedback is required, not just schema-level
**And** the prop MUST NOT change the wire shape of `useArqueo().submit()`
— the `justificacion?: string` field is already conditional in the
hook payload (`useArqueo.ts:35`), so the F10.1 backend contract
(REQ-OPS-091) is unaffected.

#### Scenario: F10.1 `ArqueoParcial` page is bit-identical when `requiredMode` is `undefined`

- **Given** the F10.1 `<ArqueoParcial>` page at
  `apps/electron-sucursal/src/features/caja/pages/ArqueoParcial.tsx`
  (REQ-OPS-152) renders `<ArqueoSheet uuid_sesion={sesion.uuid} />`
  with NO `requiredMode` prop
- **When** the operator enters `valor_efectivo_reportado=47000` with
  `diferencia=-3000`
- **Then** the `<ArqueoSheet>` MUST behave IDENTICALLY to F10.1
  (`superRefine` path): submit button MAY be enabled with empty
  justificacion if the user disables the warning; the `FormMessage`
  MUST appear only after a submit attempt with empty justificacion
  (no top-level Zod rejection on render)
- **And** no regression in F10.1 e2e scenarios in `e2e/arqueo.spec.ts`
  (REQ-OPS-156 scenario 2 still asserts `disabled` while empty +
  re-enables after `length>=3` — this is the F10.1 path, NOT the F10.2
  strict-mode path)

#### Scenario: `CerrarTurno` strict-mode blocks submission while `justificacion` empty

- **Given** `CerrarTurno` mounts `<ArqueoSheet requiredMode="cierre_turno"
  uuid_sesion={sesion.uuid} expected={resumen}>` (the proposed inline
  pattern, OR a separate `<CerrarTurnoArqueoForm>` shim — the prop
  contract is the same in both)
- **When** the operator enters `valor_efectivo_reportado=97000` with
  `diferencia=-3000` and `justificacion.length=0`
- **Then** the Zod schema MUST reject with
  `justificacion_requerida` on the `justificacion` field at the TOP
  LEVEL (not via superRefine), the submit button MUST be disabled on
  initial render (NOT just after a submit attempt), and the
  `<FormMessage>` MUST render with the i18n key
  `cerrarTurno.arqueoJustificacionRequerida`
- **And** after the operator types `justificacion.length >= 3`, the
  button re-enables and submission proceeds

### REQ-OPS-159 — POST-then-PUT sequencer with rollback-safe error mapping (no DELETE, no retry loop)

**Given** the architectural canon in `AGENTS.md` §1-§3 forbids physical
DELETE on `[A]` tables, no DELETE endpoint exists, and
`prod.arqueo` is `[A]` with `REVOKE DELETE` from `rol_app` (audit-first
canon)
**When** the F10.2 sequencer runs
**Then** the success path MUST be exactly: `POST /caja/arqueo` → 201
→ capture `{ uuid: A }` → `PUT /caja-sesion/sesion/{uuid}/cerrar` →
200 → `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')` +
`navigate('/login?closed=true', { replace: true })` (REQ-OPS-157
happy-path branch)
**And** the error mapping MUST cover, in this exact precedence order:
1. **`useArqueo().submit(...)` throws `ZodError`** → re-render
   `<FormMessage role="alert">` with the per-field error keys (NO
   network call, NO navegate)
2. **`useArqueo().submit(...)` throws `ParkosHttpError` with
   `status===400` and `detail.error==='arqueo_invalid'`** →
   re-render field-level errors from `detail.campo` array (legacy key
   drift anchor surfaced as Pydantic validation messages)
3. **`useArqueo().submit(...)` throws `ParkosHttpError` with
   `status===5xx`** → red banner `cerrarTurno.errorArqueoFallido` with
   "Reintente — si persiste contacte al supervisor"; the form stays
   editable, the sequencer does NOT proceed to `cerrarSesion`
4. **`useArqueo().submit(...)` throws network error** (TypeError on
   `fetch`, `AbortError`, etc.) → red banner
   `cerrarTurno.errorRedArqueo`
5. **`cerrarSesion(...)` throws `SesionAlreadyClosedError`** (F3.3
   `404 sesion_not_found` mapping) → red banner
   `cerrarTurno.errorCierreYaCerrado` + navigate `/login` (no
   `?closed=true`, per `DEC-F3.3-07`); the `uuid_arqueo` from step 1
   IS surfaced as `data-testid="cerrar-turno-orphan-uuid"` for
   ABBC-F10.2-BE-1 reconciler
6. **`cerrarSesion(...)` throws `ParkosHttpError` with `status===409`
   and `detail.error==='sesion_ya_cerrada'`** → same mapping as #5
7. **`cerrarSesion(...)` throws `ParkosHttpError` with `status===5xx`
   OR network error** → red banner
   `cerrarTurno.errorCierreFallido` with the literal text "Arqueo
   registrado pero no se pudo cerrar sesión — contacte al supervisor.
   Ref: <uuid_arqueo>"; the `uuid_arqueo` from step 1 IS surfaced as
   `data-testid="cerrar-turno-orphan-uuid"`; the sequencer MUST NOT
   call `useAuthStore.clear()` and MUST NOT navigate (the operator
   stays on the route to read the banner; a future retry is under
   supervisor guidance)
8. **`cerrarSesion(...)` throws `ParkosHttpError` with `status===401`**
   → F3.3 fallback path: `useAuthStore.clear()` +
   `dispatchEvent('parkos:auth:cleared')` + `navigate('/login')` (NO
   `?closed=true` — the close did not succeed)
**And** the sequencer MUST NOT implement any retry loop — no
`Promise.retry()`, no `setTimeout` re-issue, no SWR mutate. Errors are
terminal; recovery is operator-driven with the surfaced `uuid_arqueo`
(ABBC-F10.2-BE-1 is the future automated reconciler)
**And** the sequencer MUST NOT attempt client-side DELETE on the
arqueo `[A]` row — the operation is physically impossible (DB REVOKE)
and forbidden by canon
**And** the sequencer MUST NOT call `useAuthStore.clear()` in cases 1-4
or 7 — clearing prematurely would log the operator out of an open
session while the sequencer still has work to do.

#### Scenario: PUT 409 after POST 201 surfaces orphan uuid without logout

- **Given** `useArqueo().submit(...)` returns `{ uuid: "A" }` and
  `cerrarSesion(...)` throws `ParkosHttpError` with `status===409` and
  `detail={"error": "sesion_ya_cerrada"}`
- **When** the catch block runs
- **Then** the form MUST re-render with the red banner
  `cerrarTurno.errorCierreFallido` (NOT `errorCierreYaCerrado` — the
  error is `sesion_ya_cerrada`, not `sesion_not_found`)
- **And** the banner text MUST include the literal substring
  `Ref: A` where `A` is the orphan arqueo uuid
- **And** the page MUST stay mounted at `/caja/cerrar-turno` (no
  `navigate('/login')` — the sesion is already closed by the backend,
  but the operator needs to read the banner before the next action)
- **And** `useAuthStore.getState().accessToken` MUST remain non-null
  (no `clear()` call) — the next operator action is on the same shell

#### Scenario: POST 5xx leaves sesion OPEN and form editable

- **Given** `useArqueo().submit(...)` throws `ParkosHttpError` with
  `status===500`
- **When** the catch block runs
- **Then** the form MUST re-render with the red banner
  `cerrarTurno.errorArqueoFallido`
- **And** the sequencer MUST NOT call `cerrarSesion(...)` (no orphan
  arqueo to reconcile — the POST failed)
- **And** the form fields MUST remain editable so the operator can
  retry the POST with corrected values
- **And** `useAuthStore.getState().accessToken` MUST remain non-null

### REQ-OPS-160 — `useSesionActiva.cerrarSesion` API client codifies the F3.3 logout-on-success helper for F11.x reuse

**Given** the existing `cerrarSesion` function at
`apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts`
(imported by `CerrarTurno.tsx:29-32`) and the F3.3 logout-on-success
helper pattern at `CerrarTurno.tsx:60-66` (`useAuthStore.clear()` +
`dispatchEvent('parkos:auth:cleared')` + `navigate('/login?closed=true',
{ replace: true })`) — codified by `DEC-F3.3-03` and asserted by F3.30
e2e scenarios in `e2e/caja/turno.spec.ts`
**When** `sdd-apply` extends the API client
**Then** `sesionActivaApi.cerrarSesion(uuid, payload)` MUST remain a
pure HTTP wrapper: `PUT /api/v1/caja-sesion/sesion/{uuid}/cerrar` with
the request body, returning the `SesionRead` response, throwing
`SesionAlreadyClosedError` on `404 sesion_not_found`, throwing
`ParkosHttpError` on any other non-2xx (the F3.3 contract, unchanged)
**And** `sdd-apply` MUST NOT mutate the existing F3.3
`handleSuccess()` callback in `CerrarTurno.tsx` — the orchestrator
already encapsulates the store-clear + event-dispatch + navigate
trifecta, and Q1 (Engram `#1899`) ratifies it verbatim
**And** the F11.x sync worker UI MUST be able to consume the same
`cerrarSesion` helper + the same `handleSuccess` pattern without
re-deriving the logout contract — `sdd-design` for F11.x SHOULD
extract the trifecta into a `usePostCerrarSesion()` helper hook if
material, but F10.2 MUST NOT do that extraction preemptively
**And** the API client MUST NOT depend on `useNavigate` (it is a pure
function, not a hook) — the navigation is the orchestrator's
responsibility, never the API client's.

#### Scenario: `cerrarSesion` throws `SesionAlreadyClosedError` propagates to the orchestrator's catch block

- **Given** the sesion was already closed by a parallel action
- **When** `cerrarSesion(uuid, payload)` runs
- **Then** the function MUST throw `SesionAlreadyClosedError` (the
  F3.3 typed exception class) with `uuid_sesion=uuid` and
  `original_error='sesion_not_found'`
- **And** the `CerrarTurno` orchestrator's catch block MUST match on
  `err instanceof SesionAlreadyClosedError` and MUST navigate to
  `/login` (no `?closed=true`) per `DEC-F3.3-07`

#### Scenario: F11.x sync UI reuses `cerrarSesion` without re-deriving logout

- **Given** a future F11.x component (out of F10.2 scope) renders a
  "Cerrar sesión" button
- **When** the component invokes `cerrarSesion(uuid, payload)` then
  runs the same `useAuthStore.getState().clear()` +
  `dispatchEvent('parkos:auth:cleared')` + `navigate('/login?closed=true',
  { replace: true })` trifecta (verbatim copy from `CerrarTurno.tsx:60-66`)
- **Then** the F3.30 e2e scenario E3 in `e2e/caja/turno.spec.ts`
  MUST continue to pass without modification (regression guard for
  the logout contract)

### REQ-OPS-161 — `e2e/arqueo.spec.ts` Playwright extension with cierre-turno scenarios + F3.3 logout regression

**Given** `e2e/arqueo.spec.ts` (F10.1 file) ships 3 scenarios covering
the ArqueoParcial page, and `e2e/caja/turno.spec.ts` (F3.3 file) ships
E3 + A1 covering the F3.3 logout-on-success flow with `?closed=true`
**When** `sdd-apply` extends the F10.1 e2e file (proposal §In Scope #6
precedent: extend `arqueo.spec.ts`, `test.skip` per F9.x)
**Then** `e2e/arqueo.spec.ts` MUST grow exactly 3 new scenarios:

1. **happy path with `tipo_arqueo='cierre_turno'` and diferencia=0** —
   mount `/caja/cerrar-turno`, enter the exact `valor_esperado_*`
   values, click Confirmar, assert the POST body carries
   `tipo_arqueo='cierre_turno'` (the discriminator check), assert the
   `?closed=true` redirect fires, assert
   `bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_turno'
   })` is called exactly once.
2. **strict-mode `|diferencia|>0` requires justificacion inline** —
   mount `/caja/cerrar-turno`, enter `valor_efectivo_reportado=97000`
   with `valor_esperado=100000` (diferencia = -3000), assert the
   `<ArqueoSheet requiredMode="cierre_turno">` (or the equivalent
   inline CerrarTurnoArqueoForm shim) renders with the Confirmar
   button disabled while `justificacion.length < 3`, becomes enabled
   after `length >= 3`, and the POST body carries the justificacion
   field with the desuadre alerta firing.
3. **F3.3 logout regression** — mount `/caja/cerrar-turno`, complete
   the happy path, assert `useAuthStore.getState().accessToken` is
   `null` after the redirect, assert the URL is exactly
   `/login?closed=true`, assert the `parkos:auth:cleared` event fired
   (Playwright `page.evaluate(() => window.__lastClearedEvent)` or
   equivalent mock), assert no ArqueoParcial side effects (the F4
   hotkey and `useDashboardDrawerStore.open` state from F10.1
   `ArqueoParcial` page are unaffected).

**And** the scenarios MUST mark `test.skip` per the F9.x precedent
(Engram `#1894`) — F10.1 `e2e/arqueo.spec.ts` ships all scenarios
with `test.skip` and the CI gate is `tsc --noEmit` + `vitest run` only;
Playwright e2e runs in a follow-up CI matrix when the dev environment
is stable
**And** the scenarios MUST NOT mutate `prod.factura_pagos` directly
(`fn_factura_pagos_inmutable` trigger would fire; defense in depth per
AGENTS.md §3) — mocks via `page.route('/api/v1/caja/arqueo', ...)` and
`page.route('/api/v1/caja-sesion/sesion/:uuid/cerrar', ...)`
**And** the scenarios MUST NOT insert rows in a way that forks the
hash chain — single-shot per scenario; the
`job_sync_cloud.hash_chain_verifier_loop` (PR9b, Engram `#1888`) is
the safety net
**And** the scenarios MUST reuse the F10.1 fixtures (`VALID_ARQUEO_PAYLOAD`
etc.) where possible to avoid drift; only add new fixtures if the new
flow demands them
**And** an axe-core check on `/caja/cerrar-turno` MUST report zero
WCAG 2.1 AA violations (RNF-022; extends F10.1 axe-core coverage).

#### Scenario: happy-path cierre-turno submits with discriminator and redirects

- **Given** the electron-sucursal dev server is up, the operador is
  authenticated, the active `sesion.uuid = S`, and the resumen mock
  returns `{ valor_esperado_efectivo: 100000, valor_esperado_datafono:
  0, tolerancia_efectivo: 1000, tolerancia_datafono: 500 }`
- **When** the operator navigates to `/caja/cerrar-turno`, types
  `100000` in efectivo and `0` in datafono, leaves justificacion empty,
  and clicks Confirmar
- **Then** the intercepted POST body MUST equal
  `{ uuid_sesion: "S", tipo_arqueo: "cierre_turno",
  valor_efectivo_reportado: 100000, valor_datafono_reportado: 0 }` (no
  `justificacion` field — `|diff|=0`)
- **And** the intercepted PUT body MUST equal
  `{ uuid_sesion: "S", valor_final_efectivo: 100000,
  valor_final_datafono: 0 }`
- **And** `bridge.imprimir` MUST be called exactly once with
  `kind='arqueo'` and the payload's `auditoria_codigo === 'cierre_turno'`
- **And** the URL MUST navigate to `/login?closed=true`
- **And** axe-core MUST report zero violations on the post-redirect
  `/login` page (no leftover focus traps from the cerrar-turno form).

#### Scenario: F3.3 logout-on-success regression guard

- **Given** the suite has just completed the happy-path scenario
- **When** the test inspects `window.__lastClearedEvent` (or the
  equivalent Playwright mock)
- **Then** the variable MUST equal `'parkos:auth:cleared'`
- **And** `useAuthStore.getState().accessToken` MUST be `null`
- **And** the URL MUST be exactly `/login?closed=true` (query string
  `closed=true` is the operator-facing success signal — per Q1,
  Engram `#1899`)
- **And** the F10.1 ArqueoParcial page MUST NOT have been mounted at
  any point (the F4 hotkey and `useDashboardDrawerStore.open` state
  are clean — no cross-contamination).

### REQ-OPS-162 — `pending-fase-10.md` ABBC-F10.2-BE-1 forward reference (already added 2026-09-21)

**Given** the F10.2 sequencer cannot rollback a successful POST +
failed PUT (REQ-OPS-159 cases 5-7), and the architectural canon forbids
physical DELETE on `[A]` tables, and `prod.arqueo` is `[A]` with
`REVOKE DELETE` from `rol_app`
**When** `sdd-apply` lands F10.2
**Then** the file `pending-fase-10.md` MUST retain the entry
`ABBC-F10.2-BE-1` (already added 2026-09-21, item #4) verbatim — the
forward reference is for a future "arqueo orphan reconciler" job
(outside Fase 10 scope, post-Fase-13 backend admin) that detects
arqueos with `uuid_sesion IS NULL` in `pendiente` state + created >X
min ago, and retries the PUT under a supervisor-aware retry policy
**And** F10.2 MUST NOT implement the reconciler — the entry stays
forwarded, the FE UX (REQ-OPS-159 cases 5-7) is the interim
remediation path
**And** the spec MUST reference ABBC-F10.2-BE-1 in the "Forward
hooks" section below and in REQ-OPS-157 scenario 3 + REQ-OPS-159
cases 5-7
**And** the entry MUST NOT be marked "RESOLVED" at F10.2 archive time
— it transfers to a future HU owner (likely Fase 13 backend admin or
Fase 16 housekeeping).

#### Scenario: ABBC-F10.2-BE-1 is referenced but not implemented

- **Given** the F10.2 spec is archived (delta synced to
  `openspec/specs/operations/spec.md`)
- **When** the operator opens `pending-fase-10.md`
- **Then** item #4 MUST still read "ABBC-F10.2-BE-1" with status
  "no bloquea F10.2 (FE muestra `uuid_arqueo` en banner de error para
  remediación manual)" and origin "HU-F10.2 propose (drift anchor
  DA-F10.2-2)"
- **And** the entry MUST cite the spec's `REQ-OPS-159` cases 5-7 as
  the interim remediation UX.

## Drift reconciliation table

| # | Drift anchor (from proposal §Risks) | Spec resolution | Where it lands downstream |
|---|---|---|---|
| DA-F10.2-1 | `justificacion` asymmetry — F10.1 had it as `superRefine` (lenient); F10.2 needs it as top-level `min(3)` (strict). Wrong wiring re-enables the lenient path for cierre de turno. | RESOLVED in REQ-OPS-158: `<ArqueoSheet requiredMode>` prop discriminates the strict-mode branch (top-level `min(3)`); F10.1 `ArqueoParcial` keeps `requiredMode={undefined}` → bit-identical `superRefine` path. Default `undefined` is the F10.1 contract. | design.md: prop surface; tasks.md T1 + T2 (ArqueoSheet diff + CerrarTurno wiring); apply: extend prop interface + Zod branch + CerrarTurno unit test for both paths. |
| DA-F10.2-2 | Sequencing rollback policy — POST /arqueo succeeds but PUT /sesion/{uuid}/cerrar fails leaves orphan arqueo `[A]` + open session. No DELETE endpoint (architecture canon). | RESOLVED in REQ-OPS-159 cases 5-7: error UX surfaces `uuid_arqueo` via `data-testid="cerrar-turno-orphan-uuid"` banner; no retry loop; no `useAuthStore.clear()` (operator stays on route to read the banner). ABBC-F10.2-BE-1 in `pending-fase-10.md` commits the long-term orphan reconciler to a future backend PR. | design.md: error-mapping table; tasks.md T3 (error UX) + T4 (orphan uuid surfacing); apply: catch-block branches + i18n keys. |
| DA-F10.2-3 | Hook duplication — risk of a parallel `useCerrarTurno` hook. | RESOLVED by spec (no new hook): orchestrate inline in `CerrarTurno.tsx` using existing `useArqueo().submit()` + `cerrarSesion()` (F3.3 helper) + `useSesionActiva()`. `sdd-design` MAY extract a `usePostCerrarSesion()` helper only if material; F10.2 MUST NOT preempt that. | design.md: component tree; tasks.md: NONE; apply: NONE — inline orchestration in the page. |
| DA-F10.2-4 | Logout-on-success — input slice says "do NOT logout"; F3.3 e2e specs E3 + A1 in `e2e/caja/turno.spec.ts` assert `useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')` + `navigate('/login?closed=true')`. | RESOLVED (auto, Engram `#1899` ratified 2026-09-21): KEEP F3.3 behavior verbatim. `DEC-F3.3-03` canon + E3/A1 e2e regression guard. Q1 closed pre-spec. The CerrarTurno.tsx `handleSuccess` (line 60-66) is preserved; REQ-OPS-160 codifies the helper for F11.x reuse. | design.md: control-flow note; tasks.md: NONE (already shipped); apply: NONE — the F3.3 pattern is the contract. |
| DA-F10.2-5 | ESC/POS body discriminator — F10.1 escpos body emits `Codigo: <auditoria_codigo>`; F10.2 needs the same body with `auditoria_codigo='cierre_turno'`. | RESOLVED by documentation (no escpos change required). `lib/print/escposBuilder.ts:498` emits `Codigo: ${payload.auditoria_codigo}\n` — the discriminator carries the 12-line body shape unchanged. `useArqueo().submit()` returns `{ uuid }`; the renderer derives `auditoria_codigo='cierre_turno'` from the call site (the `tipo_arqueo` discriminator) and passes it to `bridge.imprimir('arqueo', { ..., auditoria_codigo: 'cierre_turno' })`. | design.md: data-flow note; tasks.md: NONE; apply: NONE — escpos dispatcher unchanged. |
| DA-F10.2-6 | Strict-TDD coverage budget — F10.2 adds 1 page-level file (rewrite), 1 component-level diff (CerrarTurnoForm + ArqueoSheet prop), 3 e2e scenarios, ≥3 unit tests. Strict-TDD requires every behavior to ship RED→GREEN. | RESOLVED by `tasks.md` (paired work-unit commits per `work-unit-commits` skill): C1 (RED tests for sequencing) + C2 (GREEN impl); C3 (RED tests for strict-mode prop) + C4 (GREEN impl); C5 (RED tests for error mapping) + C6 (GREEN impl); C7 (RED e2e scenarios) + C8 (GREEN apply). Total ~300 LOC, well under the 800-LOC budget per commit. | tasks.md: 8 paired work-units; apply: RED-then-GREEN per commit. |

## Validation matrix

| Validator | File path | Scenarios | Threshold |
|---|---|---|---|
| `vitest` unit | `apps/electron-sucursal/src/features/caja/pages/__tests__/CerrarTurno.test.tsx` (NEW) | 3: happy path POST→PUT→logout; strict-mode blocks empty justificacion; PUT 409 surfaces orphan uuid without logout | lines ≥80, branches ≥75 |
| `vitest` unit | `apps/electron-sucursal/src/features/caja/components/__tests__/CerrarTurnoForm.test.tsx` (MODIFIED) | 2 (extend existing F3.3): `requiredMode='cierre_turno'` top-level rejection on render; button disabled until `justificacion.length >= 3` | lines ≥85 |
| `vitest` unit | `apps/electron-sucursal/src/features/caja/components/__tests__/ArqueoSheet.test.tsx` (NEW or MODIFIED) | 2: `requiredMode={undefined}` → bit-identical to F10.1 (regression); `requiredMode='cierre_turno'` → strict-mode path | lines ≥85 |
| `playwright` e2e | `apps/electron-sucursal/e2e/arqueo.spec.ts` (MODIFIED, extend F10.1 file) | 3 per REQ-OPS-161 (all `test.skip` per F9.x precedent; Engram `#1894`) | passes 100% when CI matrix enables Playwright |
| `tsc --noEmit` | workspace-wide | REQ-OPS-157..162 type-correct (no `any` for the `requiredMode` discriminator; Zod branch discriminated) | zero errors |
| `eslint` | workspace-wide | REQ-OPS-157..162 lint-clean (no unused `justificacion` refactor; no unused `diferencia_*` fields) | zero errors |
| `@axe-core/playwright` | `apps/electron-sucursal/e2e/arqueo.spec.ts` (last scenario) | 1: WCAG 2.1 AA on `/caja/cerrar-turno` | zero violations |
| `openspec/scripts/check_schema_match.py` | workspace-root | unchanged schema (F10.2 is frontend-only — no migration) | exits 0 |
| `pending-fase-10.md` integrity | workspace-root | ABBC-F10.2-BE-1 entry preserved at archive time | text grep: `"ABBC-F15.2-BE-1"` absent (F10.2 does NOT renumber it); `"ABBC-F10.2-BE-1"` present |

## Risk acknowledgements

| Risk id (proposal §Risks) | Status | Residual |
|---|---|---|
| DA-F10.2-1 — `justificacion` asymmetry (strict-mode vs lenient) | RESOLVED | REQ-OPS-158 prop branch + REQ-OPS-157 scenario 2 lock the contract. F10.1 `ArqueoParcial` regression-clean (REQ-OPS-158 scenario 1). E2E + unit coverage is the long-term backstop. |
| DA-F10.2-2 — Sequencing rollback policy (orphan arqueo) | RESOLVED (interim) | REQ-OPS-159 cases 5-7 + ABBC-F10.2-BE-1 forward reference. FE surfaces the `uuid_arqueo` for supervisor-driven remediation. Long-term reconciler is post-Fase-13 backend admin. |
| DA-F10.2-3 — Hook duplication | RESOLVED | REQ-OPS-157 orchestrator uses existing `useArqueo().submit()` + `cerrarSesion()` inline. No new `useCerrarTurno` hook. `sdd-design` may extract `usePostCerrarSesion()` if material; out of F10.2. |
| DA-F10.2-4 — Logout-on-success (Q1) | RESOLVED (auto, pre-spec) | Engram `#1899` ratified 2026-09-21. F3.3 behavior kept verbatim. `DEC-F3.3-03` + E3/A1 e2e are the canon. Changing it requires a Fase 3 follow-up HU. |
| DA-F10.2-5 — ESC/POS body discriminator | RESOLVED (no code change) | `escposBuilder.ts:498` already emits `Codigo: ${payload.auditoria_codigo}` — `cierre_turno` flows through unchanged. The 12-line body shape is the same. |
| DA-F10.2-6 — Strict-TDD coverage budget | RESOLVED | `tasks.md` enforces 8 paired work-unit commits (C1..C8). Total ~300 LOC. Well under the 800-LOC budget per commit. |
| **NEW** — Substrate path drift | RESOLVED (documentation) | Proposal §Substrate listed `apps/electron-sucursal/src/features/turno/hooks/useSesionActiva.ts` and `apps/electron-sucursal/src/i18n/es-CO/caja.json`; the actual paths are `src/features/caja/hooks/useSesionActiva.ts` and `src/renderer/i18n/locales/caja.json`. The spec uses the actual paths. The e2e file `e2e/turno.spec.ts` referenced in the input is at `e2e/caja/turno.spec.ts`. F10.2 apply uses the live tree; no path change required. |
| **NEW** — `CerrarTurno` page already exists as F3.3 stub | RESOLVED (documentation) | REQ-OPS-157 rewrites `CerrarTurno.tsx` in-place; the F3.3 fields (`valor_final_*`, `observaciones_cierre`) are PRESERVED on the PUT leg, the arquee fields (`valor_efectivo_reportado`, etc.) are NEW on the POST leg. The two coexist per proposal §Out-of-Scope. |
| **NEW** — F10.3 will consume REQ-OPS-158 `requiredMode='cierre_dia'` | FORWARDED | F10.2 ships the union member `'cierre_dia'` in the `requiredMode` discriminator (REQ-OPS-158). F10.3 owns the `<CierreDiarioDialog>` consumer that passes `requiredMode='cierre_dia'` to `<ArqueoSheet>`. The discriminator union is closed at F10.2; F10.3 is a consumer, not a producer. |

## Forward hooks

- **HU-F10.3 (Cierre diario)**: will reuse REQ-OPS-158's
  `requiredMode='cierre_dia'` branch (the strict-mode Zod variant is
  shared with `cierre_turno`; F10.3 owns the `<CierreDiarioDialog>`
  consumer that passes the new discriminator value to `<ArqueoSheet>`).
  F10.3 will reuse the sequencer pattern (REQ-OPS-159) for the
  multi-session cierre diario flow. `CierreDiarioDialog.tsx:91` already
  invokes `useArqueo().submit({ ..., tipo_arqueo: 'cierre_dia' })` —
  F10.3 is responsible for the chained sesion-close semantics, NOT
  F10.2.
- **HU-F11.x (sync worker UI + alertas CU-07/14)**: will reuse
  `sesionActivaApi.cerrarSesion(uuid, payload)` (REQ-OPS-160) for any
  "Cerrar sesión desde worker UI" button. The logout-on-success
  trifecta (`useAuthStore.clear()` + `dispatchEvent('parkos:auth:cleared')`
  + `navigate('/login?closed=true', { replace: true })`) is verbatim
  F3.3 + REQ-OPS-157 — F11.x may extract `usePostCerrarSesion()` if
  material, but MUST NOT modify the existing F3.3 contract.
- **ABBC-F10.2-BE-1 (arqueo orphan reconciler, post-Fase-13 backend
  admin)**: the long-term automated reconciler that retries the PUT on
  orphan arqueos. Detection: `prod.arqueo WHERE uuid_sesion IS NULL AND
  estado = 'pendiente' AND created_at < now() - INTERVAL '15 minutes'`.
  Action: re-issue `PUT /caja-sesion/sesion/{uuid}/cerrar` under a
  supervisor-aware retry policy (max 3 attempts, exponential backoff).
  Out of scope for Fase 10; the FE UX (REQ-OPS-159 cases 5-7) is the
  interim remediation.
- **`bridge.imprimir('arqueo', payload)` reuse**: F10.1 ships the
  escpos dispatcher; F10.2 and F11.x can both invoke it without
  escpos changes. The 12-line body shape is shared across
  `auditoria` / `cierre_turno` / `cierre_dia` — only the
  `auditoria_codigo` discriminator differs.
- **`useArqueoResumen` SWR hook**: unchanged across F10.1, F10.2, F10.3.
  F11.x alerta dashboards may consume it for live descuadre
  thresholds.

## References

- Base spec: `openspec/specs/operations/spec.md` (REQ-OPS-091..097 F1.13
  backend; REQ-OPS-027..029 F3.3 sesion cycle; REQ-OPS-152..156 F10.1
  arqueo parcial).
- Proposal: `openspec/changes/fase-10-2-cierre-turno/proposal.md`.
- F10.1 archived delta spec:
  `openspec/changes/archive/2026-09-21-fase-10-1-arqueo-parcial/specs/spec.md`.
- Engram: `#1899` (Q1 decision: KEEP F3.3 logout); `#1894` (F10.1 size
  exception, F9.x test.skip precedent); `#1888` (F10.1 sync verifier);
  `#1887` (Fase 10 SDD preflight).
- Architectural canon: `AGENTS.md` §1 (audit-first), §2 (bi-temporal),
  §3 (C/Q/U only — no DELETE), §3.4 (sync canon, hash chain).
- Plan: `plan.md:2185-2205` (HU-F10.2 — Cierre de turno).
- Substrate files (verified paths):
  - `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts`
  - `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx`
  - `apps/electron-sucursal/src/features/caja/components/CerrarTurnoForm.tsx`
  - `apps/electron-sucursal/src/features/caja/components/CierreDiarioDialog.tsx`
  - `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx`
  - `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts`
  - `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts`
  - `apps/electron-sucursal/src/renderer/App.tsx` (route
    `/caja/cerrar-turno` at line 62-65)
  - `apps/electron-sucursal/src/lib/print/escposBuilder.ts`
    (line 498: `Codigo:` line)
  - `apps/electron-sucursal/src/renderer/i18n/locales/caja.json`
    (`cerrarTurno.*` keys — extend, don't replace)
  - `apps/electron-sucursal/e2e/arqueo.spec.ts` (F10.1 file, extend)
  - `apps/electron-sucursal/e2e/caja/turno.spec.ts` (F3.3 e2e, do not
    modify — regression guard)
  - `pending-fase-10.md` (item #4: ABBC-F10.2-BE-1, preserved).