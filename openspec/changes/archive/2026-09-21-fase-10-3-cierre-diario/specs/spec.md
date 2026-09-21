# Delta Spec: `operations` — HU-F10.3 Cierre Diario (Multi-Session Daily Reconciliation)

## Phase

HU-F10.3 (Fase 10, third and final HU). Frontend-only delta over
the base spec `operations` (REQ-OPS-091..097 shipped at F1.13 backend;
REQ-OPS-027..029 at F3.3 sesion cycle; REQ-OPS-152..156 at F10.1 arqueo
parcial; REQ-OPS-157..162 at F10.2 cierre de turno). Branch
`feature/hu-f10-3-cierre-diario` (created from `dev`). Author
`Parkos Dev <dev@parkos.local>`. Strict-TDD ACTIVE.

## Gap

`REQ-OPS-163..168` — the next six correlatives free after `REQ-OPS-162`
(F10.2 archive, ratified at merge SHA `9878392` per
`openspec/specs/operations/spec.md:6311`). Numbering verified by
`Select-String -Pattern "^### REQ-OPS-\d+" openspec/specs/operations/spec.md
| Select-Object -Last 6`: last entry is `REQ-OPS-162`.

Q1, Q2, Q3 from the proposal are **resolved via repo inspection** in
this phase (see Drift reconciliation table for evidence paths):

- **Q1 (DA-F10.3-4) RESOLVED**: the F1.13 backend
  `GET /caja/arqueo/resumen` ALREADY returns the per-session array since
  F1.13 shipped. `backend/packages/parkos_core/src/parkos_core/schemas/caja.py:316-346`
  defines `ArqueoResumenRead { fecha, uuid_sucursal, sesiones:
  list[ArqueoResumenItem], cierre_dia: ArqueoResumenItem | None }`.
  The FE `useArqueoResumen` Zod schema at
  `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts:10-18`
  is DRIFTED (expects aggregate `total_efectivo_cop`/`total_datafono_cop`/
  `diferencia_cop`/`sesiones_cerradas` fields that the backend never
  returns — flagged as NEW-DA-F10.3-9, deferred to follow-up PR for
  reconciliation, NOT in F10.3 scope). F10.3 introduces a NEW sibling
  SWR hook `useArqueoResumenPorSesion` that consumes the per-session
  shape from the same backend endpoint with the corrected Zod schema.

- **Q2 (DA-F10.3-2) RESOLVED**: admin- JWT issuer ALREADY grants
  technical access to `POST /caja/arqueo`. Backend issuer gate at
  `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py:61`
  is `requires_issuer("operador-", "admin-")` — admin- tokens have
  no `sucursal_uuid` pinning (verified at
  `auth/tokens.py:144-152` `_audience_for` + `auth/__init__.py` admin
  claims), so a supervisor with an admin- JWT can close ANY branch's
  open sessions via `tipo_arqueo='cierre_dia'`. The
  `perm_arqueo_cerrar_cualquiera` permission does NOT exist in the
  codebase (`grep -r perm_arqueo_cerrar_cualquiera backend/`
  returned 0 hits; only `perm_arqueo_cerrar` at
  `backend/tests/unit/test_auth_me.py:139` for the close-own-session
  flow). No new JWT issuer permission is required; FE gates UI on
  admin- issuer presence (`useAuthStore.accessToken` claims).

- **Q3 (DA-F10.3-7) RESOLVED via deprecate-without-delete**:
  `useCierreDiario()` at
  `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts:100-118`
  is BUGGY: payload schema declares `uuid_sesion: string` (line 109) but
  the backend cross-validation at `caja_arqueo.py:122-128` explicitly
  REJECTS `cierre_dia` with non-null `uuid_sesion` (returns
  `400 cierre_dia_no_acepta_uuid_sesion`). The F8.x caller
  `apps/electron-sucursal/src/features/caja/components/CierreDiarioDialog.tsx:91`
  still invokes this helper and would regress if the helper were
  deleted. **Recommendation**: in T2 of F10.3 PR, mark
  `useCierreDiario()` with `@deprecated` JSDoc tag + a
  `console.warn(...)` in dev mode (when `import.meta.env.DEV` is
  true). Do NOT delete in F10.3 scope. The new `cierreDiarioChain.ts`
  helper is the forward path; the F8.x consumer continues using the
  deprecated helper until a follow-up housekeeping PR migrates it.

## ADDED Requirements

### REQ-OPS-163 — `GET /caja/arqueo/resumen` per-session shape: `useArqueoResumenPorSesion` SWR hook exposes `ArqueoResumenRead.sesiones[]`

**Given** the F1.13 backend
`apps/electron-sucursal/src/features/caja/api/caja_arqueo.get_arqueo_resumen`
returns `ArqueoResumenRead { fecha: date, uuid_sucursal: UUID,
sesiones: ArqueoResumenItem[], cierre_dia: ArqueoResumenItem | null }`
(verified at
`backend/packages/parkos_core/src/parkos_core/schemas/caja.py:335-346`
and the handler at `api/v1/caja_arqueo.py:337-413`),
and the F10.1 `useArqueoResumen` Zod schema at
`apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts:10-18`
expects aggregate fields that the backend does NOT return
(`total_efectivo_cop`, etc. — drift anchor NEW-DA-F10.3-9, out of
F10.3 scope),
and each `ArqueoResumenItem` carries
`uuid_sesion, uuid_usuario, timestamp_apertura, timestamp_cierre,
estado, valor_efectivo_esperado, valor_datafono_esperado,
valor_efectivo_reportado, valor_datafono_reportado, uuid_arqueo`
**When** `sdd-apply` adds the new sibling hook
**Then** `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts`
MUST export a new function `useArqueoResumenPorSesion(uuid_sucursal:
string | null, fecha: string | null)` returning
`{ data: ArqueoResumenPorSesion | undefined, error: Error | undefined,
refresh: () => Promise<...> }`
**And** the hook MUST fetch
`GET /api/v1/caja/arqueo/resumen?uuid_sucursal=...&fecha=...` via
the existing `parkosFetch` wrapper (F2.2 invariant: Authorization
Bearer + 401 retry-once + 5xx backoff), deduping 10s, and retry on
errors that are NOT 401/403/404 (matching the F10.1 hook policy at
`useArqueo.ts:76-81`)
**And** the hook MUST parse the response with a Zod schema that
mirrors `ArqueoResumenRead` exactly:
`{ fecha: z.string(), uuid_sucursal: z.string().uuid(), sesiones:
z.array(z.object({ uuid_sesion: z.string().uuid().nullable(),
uuid_usuario: z.string().uuid().nullable(), timestamp_apertura:
z.string().nullable(), timestamp_cierre: z.string().nullable(),
estado: z.string().nullable(),
valor_efectivo_esperado: z.number().nullable(),
valor_datafono_esperado: z.number().nullable(),
valor_efectivo_reportado: z.number().nullable(),
valor_datafono_reportado: z.number().nullable(),
uuid_arqueo: z.string().uuid().nullable() })),
cierre_dia: z.object({...}).nullable() }`
**And** the hook MUST key the SWR cache as
`/caja/arqueo/resumen?uuid_sucursal=${uuid_sucursal}&fecha=${fecha}`
when both `uuid_sucursal` and `fecha` are non-null AND `accessToken`
is non-null (matches F10.1 hook key gate at `useArqueo.ts:67-69`)
**And** the hook MUST call `useAuthStore.getState().clear()` +
`dispatchEvent(new Event('parkos:auth:cleared'))` on 401
(matches F10.1 hook policy at `useArqueo.ts:82-89`)
**And** the hook MUST NOT mutate or replace the legacy
`useArqueoResumen` export (regression guard for F10.1
`CierreDiarioDialog.tsx` and `ArqueoParcial.tsx` callers — the legacy
hook keeps its (drifted) aggregate Zod schema unchanged; the
NEW-DA-F10.3-9 reconciliation is a separate follow-up).

#### Scenario: per-session table renders 3 sessions (2 closed + 1 open)

- **Given** the backend `GET /caja/arqueo/resumen` returns
  `{ fecha: "2026-09-21", uuid_sucursal: "S",
  sesiones: [{ uuid_sesion: "S1", uuid_usuario: "U1",
  timestamp_apertura: "...", timestamp_cierre: "...",
  estado: "cerrado", valor_efectivo_esperado: 50000,
  valor_datafono_esperado: 0,
  valor_efectivo_reportado: 50000, valor_datafono_reportado: 0,
  uuid_arqueo: "A1" },
  { uuid_sesion: "S2", uuid_usuario: "U2",
  timestamp_apertura: "...", timestamp_cierre: "...",
  estado: "cerrado", ... },
  { uuid_sesion: "S3", uuid_usuario: "U1",
  timestamp_apertura: "...", timestamp_cierre: null,
  estado: "abierta", valor_efectivo_esperado: null,
  valor_datafono_esperado: null,
  valor_efectivo_reportado: null, valor_datafono_reportado: null,
  uuid_arqueo: null }],
  cierre_dia: null }`
- **When** the F10.3 `<CierreDiario />` page mounts
  `/caja/cierre-diario` and the hook resolves
- **Then** the page MUST render a `<table
  data-testid="cierre-diario-sesiones">` with 3 rows
  (`<tbody>` children count == 3)
- **And** each row MUST render: `uuid_usuario` (or email fallback),
  `timestamp_apertura` (formatted `es-CO`), `estado` (color-coded
  badge: green `cerrado`, amber `abierta`), `valor_efectivo_esperado`
  formatted as `${N.toLocaleString('es-CO')}` (null for open
  sessions shows `—`), `valor_efectivo_reportado` similarly, and
  `diferencia` computed as
  `valor_efectivo_reportado - valor_efectivo_esperado` (or `—`
  when either is null)
- **And** the table footer MUST aggregate:
  `Σ valor_efectivo_reportado` (only over closed sessions),
  `Σ valor_datafono_reportado`, `Σ diferencia`
- **And** axe-core MUST report zero WCAG 2.1 AA violations on the
  table (semantic `<table>` + `<th scope="col">` + `<caption>`).

#### Scenario: `cierre_dia` already exists for the day — Confirmar disabled with banner

- **Given** the backend response includes
  `cierre_dia: { uuid_sesion: null, uuid_usuario: "U9",
  timestamp_apertura: null, timestamp_cierre: null,
  estado: "cerrado",
  valor_efectivo_esperado: 150000,
  valor_datafono_esperado: 30000,
  valor_efectivo_reportado: 150000,
  valor_datafono_reportado: 30000,
  uuid_arqueo: "AD0" }`
- **When** the page renders
- **Then** the Confirmar button MUST be disabled
  (`disabled={form.formState.isSubmitting || cierreDiaExists}`)
  with `data-testid="cierre-diario-confirmar"`
- **And** a yellow banner `<div role="status"
  data-testid="cierre-diario-already-closed">` MUST render with
  i18n key `cierreDiario.alreadyClosed` and the literal text "Ya
  existe un cierre diario para hoy — consulta el reporte"
- **And** the form below the table MUST be replaced by the banner
  (no `<input>` elements mounted when `cierreDiaExists === true`).

### REQ-OPS-164 — `<CierreDiario />` routed page mirrors F10.2 sequencer with 2-step closure (POST `/caja/arqueo` + ESC/POS)

**Given** the F10.2 `cerrarTurnoChain.ts` pattern (8-case error
precedence, REQ-OPS-159 codified at
`apps/electron-sucursal/src/features/caja/pages/cerrarTurnoChain.ts:136-222`),
and F10.3 multi-session closure requires a DIFFERENT sequencer
shape: (a) POST /caja/arqueo with `tipo_arqueo='cierre_dia'`,
`uuid_sesion=null`, `valor_efectivo_reportado`,
`valor_datafono_reportado`, optional `justificacion`; (b) ESC/POS
print via `bridge.imprimir('arqueo', { ..., auditoria_codigo:
'cierre_dia' })` (BORDER tolerant — does NOT abort on printer
failure per DA-F10.2-5 RESOLVED),
and the supervisor may close OTHER operators' sessions per
DA-F10.3-2 — therefore the F3.3 logout-on-success trifecta
(`useAuthStore.clear()` + `parkos:auth:cleared` event +
`navigate('/login?closed=true')`) MUST NOT fire because the
supervisor's own sesion is not the one being closed,
**When** `sdd-apply` creates the new page
**Then** `apps/electron-sucursal/src/features/caja/pages/CierreDiario.tsx`
MUST be a routed page component (NOT a dialog; the F8.x
`CierreDiarioDialog.tsx` is the per-session quick-close drawer and
remains untouched per proposal §Out-of-Scope)
**And** the route MUST be registered at
`apps/electron-sucursal/src/renderer/App.tsx` as `<Route
path="/caja/cierre-diario" element={<ProtectedRoute><CierreDiario
/></ProtectedRoute>} />` (ProtectedRoute gates by login state, NOT
by permission — the supervisor flow is gated by `useAuthStore`
admin- issuer check, not by the route)
**And** the page MUST render: (i) a `<h1>` with i18n key
`cierreDiario.title` and accessible `<main lang="es-CO">` wrapper;
(ii) the per-session `<ResumenTablaSesiones>` from REQ-OPS-163;
(iii) the `<CierreDiarioForm requiredMode="cierre_dia">` instance
(NEW component, NOT reusing `<ArqueoSheet>` — `<ArqueoSheet>` is the
drawer used by ArqueoParcial and CerrarTurno; F10.3 needs a
full-page form with `<ArqueoSheet requiredMode='cierre_dia'>`
semantics but inline layout); (iv) the Confirmar button +
Cancelar button (Cancelar navigates to `/`)
**And** the page MUST wire the `runCierreDiarioChain` helper
(REQ-OPS-166) as the 2-step sequencer: (a) POST /caja/arqueo; (b)
ESC/POS print; (c) success navigates to `/` (Dashboard, NOT
`/login?closed=true` — the supervisor flow does not log out per
DA-F10.3-2 + Q1 resolved above) with a `<Alert>` banner listing the
closed sessions
**And** the page MUST NOT call `useSesionActiva().cerrarSesion(...)`
(the F3.3 logout helper — REQ-OPS-160 owns it for single-session
flows only; F10.3 closes MULTIPLE sessions atomically via the
backend `cerrar_sesiones_del_dia_bulk` call inside the POST handler
at `caja_arqueo.py:266-272`)
**And** the page MUST NOT call `useAuthStore.getState().clear()` or
`dispatchEvent('parkos:auth:cleared')` (DA-F10.3-2 RESOLVED —
supervisor flow preserves own session)
**And** the page MUST preserve F10.1 + F10.2 WCAG 2.1 AA: shadcn
`<Form>` primitives provide `aria-invalid` + `aria-describedby` +
`<FormMessage role="alert">`; axe-core MUST report zero violations
on `/caja/cierre-diario` (page + form + table).

#### Scenario: happy-path multi-session closure (2 already-closed + 1 open) closes only the open one

- **Given** the per-session resumen returns 3 sessions (S1 closed,
  S2 closed, S3 open by operator U1), `cierre_dia` is null, the
  supervisor is authenticated with an admin- JWT (no
  `sucursal_uuid`), the live resumen totales show
  `Σ valor_efectivo_reportado=150000`,
  `Σ valor_datafono_reportado=30000`, `Σ diferencia=0`
- **When** the supervisor enters
  `valor_efectivo_reportado=150000`,
  `valor_datafono_reportado=30000`, leaves `justificacion` empty,
  clicks Confirmar
- **Then** the page MUST call
  `useArqueo().submit({ uuid_sesion: null, tipo_arqueo: "cierre_dia",
  valor_efectivo_reportado: 150000, valor_datafono_reportado: 30000 })`
  (no `justificacion` field — `Σ|diferencia|=0`)
- **And** the backend response MUST be `201 { uuid: AD }` where
  `AD` is the new cierre_dia arqueo uuid (the handler at
  `caja_arqueo.py:241-329` returns the `ArqueoReadForHandler` shape)
- **And** the page MUST then call
  `bridge.imprimir('arqueo', { uuid: "AD", auditoria_codigo:
  "cierre_dia" })` exactly once (F10.1 escpos dispatcher, no F10.3
  changes)
- **And** the page MUST NOT call
  `useSesionActiva().cerrarSesion(...)` (multi-session closure is
  the backend's job, not the FE's)
- **And** the page MUST navigate to `/` (Dashboard, NOT
  `/login?closed=true`) with a `<Alert data-testid="cierre-diario-success">`
  banner listing `Sesiones cerradas: 1 (S3) — Arqueo: AD`
- **And** `useAuthStore.getState().accessToken` MUST remain non-null
  (supervisor stays logged in — own session is NOT closed)
- **And** `bridge.imprimir` MUST NOT throw / abort the success path
  even if the printer is offline (DA-F10.3-6 RESOLVED via F10.2
  escpos regex extension; failure is logged but the flow continues).

#### Scenario: `Σ|diferencia|>0` requires global `justificacion.min(3)`

- **Given** the per-session resumen returns `Σ|diferencia|=3000`
  (e.g. one session reported 97000 vs expected 100000),
  `cierre_dia` is null, the form is rendered
- **When** the supervisor enters the reported totals with empty
  `justificacion`
- **Then** the Zod schema MUST branch to the F10.2
  `arqueoSchemaStrict` variant (top-level
  `z.string().trim().min(3, 'justificacion_requerida')` per
  REQ-OPS-158), the Confirmar button MUST be disabled on initial
  render, and the `<FormMessage>` MUST render with i18n key
  `cierreDiario.justificacionRequerida`
- **And** after the supervisor types
  `justificacion.trim().length >= 3`, the button re-enables,
  submission proceeds with the `justificacion` field, the backend
  records `alerta tipo_alerta='descuadre_critico'` per
  REQ-OPS-094 + `caja_arqueo.py:277-308` (descuadre_critico
  conditional INSERT when `|diferencia| > tolerancia`)
- **And** the success path navigates to `/` with the success
  banner unchanged from the happy path.

#### Scenario: backend POST returns `5xx` leaves all open sessions OPEN

- **Given** the live resumen shows S3 open, the form is filled with
  `Σ|diferencia|=0`
- **When** `useArqueo().submit(...)` throws `ParkosHttpError` with
  `status===500`
- **Then** the page MUST re-render with a red banner
  `<div role="alert" data-testid="cierre-diario-error-5xx">` with
  i18n key `cierreDiario.errorCierreFallido` and the literal text
  "No se pudo registrar el cierre diario — reintente; si persiste
  contacte al supervisor"
- **And** the sequencer MUST NOT call `bridge.imprimir(...)` (no
  print on failure)
- **And** S3 MUST remain OPEN (the POST failed before the single
  `session.commit()` at `caja_arqueo.py:311` — KD-ARQUEO-01
  invariant guarantees atomicity; on rollback, NO
  `cerrar_sesiones_del_dia_bulk` side effect persists)
- **And** the form fields MUST remain editable so the supervisor
  can retry with corrected values
- **And** `useAuthStore.getState().accessToken` MUST remain non-null
  (no logout — supervisor's own session preserved).

### REQ-OPS-165 — `useArqueoResumenPorSesion` Zod schema mirrors `ArqueoResumenRead` exactly (regression guard against F10.1 aggregate drift)

**Given** the F1.13 backend ships `ArqueoResumenRead` at
`backend/packages/parkos_core/src/parkos_core/schemas/caja.py:335-346`
with `extra='forbid'` (Pydantic layer 4 contract — adding a
client-side field would 422 the request), and the legacy
`useArqueoResumen` Zod schema at
`apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts:10-18`
does NOT include the `sesiones: ArqueoResumenItem[]` array,
**When** `sdd-apply` adds the new sibling hook
**Then** the new Zod schema (REQ-OPS-163) MUST mirror the backend
Pydantic schema field-for-field (one-to-one name + type mapping)
**And** the schema MUST use `z.string()` for `fecha` (ISO 8601 date
string — the backend serializes `date` as `YYYY-MM-DD`), not
`z.date()` (FE accepts the JSON-serialized string form)
**And** the schema MUST mark every per-session field as
`.nullable()` because closed-session rows have all fields populated
while open-session rows have `null` for cierre-time, valores
reportados, and `uuid_arqueo` (verified at `caja.py:328-332`)
**And** the schema MUST enforce `extra='forbid'` semantics on the
FE side by using `z.object({...}).strict()` on each
`ArqueoResumenItem` and on the top-level `ArqueoResumenRead` —
this is a regression guard against future backend shape drift
that the FE Zod layer would silently accept
**And** the schema MUST export `ArqueoResumenPorSesion` type alias
(`z.infer<typeof ArqueoResumenPorSesionSchema>`) so the page
`<CierreDiario />` consumes a typed prop
**And** the schema MUST NOT redefine or shadow the legacy
`ArqueoResumenSchema` — both schemas coexist; the legacy schema's
drift (NEW-DA-F10.3-9) is acknowledged and forwarded to the
follow-up reconciliation PR.

#### Scenario: backend response with extra field is rejected by Zod `.strict()`

- **Given** the backend returns a future-shaped response with an
  extra `metadata` field at the top level that is NOT in the
  current Pydantic schema
- **When** the FE Zod `.strict()` parses the response
- **Then** Zod MUST throw a `ZodError` listing the
  `metadata` field as `unrecognized_keys`
- **And** the hook's `error` field MUST be set to the `ZodError`,
  the SWR `data` MUST be `undefined`, and the page MUST render
  `<Skeleton data-testid="cierre-diario-schema-drift">` with
  console.error reporting the Zod error message
- **And** this behavior is the regression guard — the legacy
  `useArqueoResumen` would have silently dropped the extra field
  and returned `data` (F10.1 Zod schema is NOT strict, drift
  anchor NEW-DA-F10.3-9).

### REQ-OPS-166 — `cierreDiarioChain.ts` pure helper: 2-step sequencer (POST arqueo + ESC/POS) for multi-session closure

**Given** the F10.2 `cerrarTurnoChain.ts` pattern
(`apps/electron-sucursal/src/features/caja/pages/cerrarTurnoChain.ts:136-222`)
established the convention of a pure helper extracted for
unit-testability, returning a discriminated result envelope for the
orchestrator to map to UI banners + `navigate(...)`,
and F10.3 needs a DIFFERENT sequencer shape (no PUT sesion-close;
POST is the only mutation; backend handles mass-close of all
sessions of the day in-tx), and the architectural canon in
`AGENTS.md` §1-§3 forbids physical DELETE on `[A]` tables and
forbids retry loops (F10.2 codified this verbatim),
**When** `sdd-apply` creates the new helper
**Then** `apps/electron-sucursal/src/features/caja/pages/cierreDiarioChain.ts`
MUST export `runCierreDiarioChain(args)` returning a discriminated
`CierreDiarioChainResult` envelope with kinds: `'success'`,
`'arqueo_fallido'`, `'red_arqueo'`, `'ya_cerrado'`,
`'permiso_insuficiente'` (the supervisor scope gate, per
DA-F10.3-2 + REQ-OPS-167 below)
**And** the helper MUST type `args.submitArqueo` as a structural
`ArqueoSubmitFn` with the cierre_dia payload shape:
`(payload: { uuid_sesion: null; tipo_arqueo: 'cierre_dia';
valor_efectivo_reportado: number; valor_datafono_reportado: number;
justificacion?: string }) => Promise<{ uuid: string }>`
(the `uuid_sesion` literal type is `null`, NOT `string` — this is
the corrigendum for the buggy `useCierreDiario()` helper at
`useArqueo.ts:107-117` that incorrectly typed it as `string`)
**And** the helper MUST type `args.bridge` as a minimal
`CierreDiarioBridge` interface (`imprimir(kind, payload) =>
Promise<unknown>`) matching the F10.2 precedent at
`cerrarTurnoChain.ts:29-31`
**And** the helper MUST execute in this exact order:
1. POST /caja/arqueo (via `submitArqueo`); on error, return
   matching error kind (`'arqueo_fallido'` for `ParkosHttpError`,
   `'red_arqueo'` for `TypeError`/network).
2. ESC/POS print via `bridge.imprimir('arqueo', { uuid, ...
   arqueoResult, auditoria_codigo: 'cierre_dia' })`; failure is
   logged but DOES NOT abort the flow (DA-F10.3-6 RESOLVED, F10.2
   C5 regex extension).
3. Return `{ kind: 'success', uuid_arqueo }` with the captured
   uuid for the orchestrator's success banner.
**And** the helper MUST NOT call any sesion-close helper — the
backend's `cerrar_sesiones_del_dia_bulk` (KD-ARQUEO-03, triggered
at `caja_arqueo.py:266-272` when `codigo_tipo_arqueo ==
'cierre_dia'`) handles all per-session closures inside the POST
handler's single `session.commit()` (KD-ARQUEO-01 atomicity
guarantee at `caja_arqueo.py:311`)
**And** the helper MUST NOT implement any retry loop (no
`Promise.retry`, no `setTimeout` re-issue, no SWR mutate) — errors
are terminal; recovery is supervisor-driven
**And** the helper MUST NOT attempt client-side DELETE on the
arqueo `[A]` row (canon §1-§3 forbids physical DELETE; ABBC-F10.2-BE-1
for the orphan reconciler stays as the future automated
remediation, not in this chain)
**And** the helper MUST be import-pure (no React hooks, no
side-effectful module-level state) so the unit test
`apps/electron-sucursal/src/features/caja/pages/__tests__/cierreDiarioChain.test.ts`
can call it with a mocked `submitArqueo` and `bridge` and assert
the discriminated result.

#### Scenario: happy-path 2-step sequencer closes all open sessions atomically

- **Given** the mocked `submitArqueo` resolves
  `{ uuid: "AD0" }` (201 from backend) and the mocked `bridge.imprimir`
  resolves `{ ok: true }`
- **When** the helper runs
- **Then** the result MUST be
  `{ kind: 'success', uuid_arqueo: 'AD0' }`
- **And** `submitArqueo` MUST have been called exactly once with
  `{ uuid_sesion: null, tipo_arqueo: 'cierre_dia',
  valor_efectivo_reportado: 150000,
  valor_datafono_reportado: 30000 }` (the `justificacion` field is
  omitted when `Σ|diferencia|=0` — wire-body minimization mirror
  of F10.2 `buildArqueoBody` at `cerrarTurnoChain.ts:84-100`)
- **And** `bridge.imprimir` MUST have been called exactly once with
  `{ uuid: 'AD0', auditoria_codigo: 'cierre_dia' }` — the
  `auditoria_codigo` discriminator flows through unchanged from
  F10.2 (F10.1 escpos regex extension at `lib/print/escposBuilder.ts:498`
  emits `Codigo: ${payload.auditoria_codigo}` and accepts
  `'cierre_dia'` without escpos changes).

#### Scenario: bridge failure is logged but does NOT abort success

- **Given** the mocked `submitArqueo` resolves `{ uuid: 'AD0' }` and
  the mocked `bridge.imprimir` rejects with
  `Error('printer offline')`
- **When** the helper runs
- **Then** the result MUST STILL be
  `{ kind: 'success', uuid_arqueo: 'AD0' }` (printer failure is
  non-fatal per F10.2 DA-F10.2-5 RESOLVED)
- **And** `console.warn` MUST have been called with the literal
  prefix `'escpos_printer_offline'` followed by the error message
  (observability hook for the supervisor to investigate post-hoc).

#### Scenario: POST `400 cierre_dia_no_acepta_uuid_sesion` from backend surfaces input contract drift

- **Given** the orchestrator (or a future caller) accidentally
  passes `uuid_sesion: 'S1'` instead of `null`
- **When** the backend rejects with `400 cierre_dia_no_acepta_uuid_sesion`
  (verified at `caja_arqueo.py:122-128`)
- **Then** the helper MUST return
  `{ kind: 'arqueo_fallido', status: 400, error: 'cierre_dia_no_acepta_uuid_sesion' }`
- **And** the orchestrator MUST render the red banner
  `cierreDiario.errorCierreDiaNoAceptaSesion` — this is a
  programmer-error indicator (the FE never passes `uuid_sesion`
  for cierre_dia per REQ-OPS-164; the banner is a defensive UX
  for any future regression).

### REQ-OPS-167 — Supervisor role gate: `<CierreDiario />` renders the supervisor-gated variant when the authenticated JWT issuer is admin- (no new permission required)

**Given** the F1.13 backend gate at
`backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py:61`
is `requires_issuer("operador-", "admin-")` (both issuers can call
POST /caja/arqueo), and admin- tokens have NO `sucursal_uuid`
pinning (verified at
`backend/packages/parkos_core/src/parkos_core/auth/tokens.py:144-152`
`_audience_for("admin-")` returns `'parkos-admin'`, distinct from
`'parkos-branch'` for operador-), and the supervisor pattern is
operationally: a multi-branch admin authenticates once with an
admin- JWT, then can drive closures at any branch,
**When** `sdd-apply` adds the role gate
**Then** `apps/electron-sucursal/src/features/caja/pages/CierreDiario.tsx`
MUST read the issuer from `useAuthStore` (the store keeps the
parsed JWT claims; verify shape at the auth store API)
**And** when the issuer is `'admin-'` (supervisor path), the page
MUST render the supervisor variant: the per-session table shows
ALL sessions of the day for the active branch
(selected via a `useAuthStore.sucursal` selector or via a separate
`<SucursalSelector />` dropdown IF the supervisor has
multiple `sucursales_permitidas` — see Forward hooks for
`/admin/me` reuse); the Confirmar button is enabled; success
navigates to `/` (Dashboard) with the success banner
**And** when the issuer is `'operador-'` AND the operator has only
ONE branch in their `sucursales_permitidas` (the F10.1/F10.2
single-branch operator flow), the page MUST render the
single-branch variant: the per-session table is pre-scoped to
that operator's branch; Confirmar is enabled; success navigates to
`/` (Dashboard — NOT `/login?closed=true`; the F10.2 logout
trifecta is OWNED by `useSesionActiva().cerrarSesion` and F10.3
does NOT call it per DA-F10.3-2 + REQ-OPS-164)
**And** when the issuer is `'operador-'` BUT the operator's
`sucursales_permitidas` contains 2+ branches (multi-branch
operator — a future Fase 11+ flow), the page MUST render a
"Sucursal pendiente de selección" placeholder banner with i18n
key `cierreDiario.multiBranchOperatorPending` until the operator
selects a branch via the F11.x BranchSelector (out of F10.3 scope;
the placeholder is defensive)
**And** the page MUST NOT introduce a new `perm_arqueo_cerrar_cualquiera`
permission check (the permission does not exist in the codebase
and is not needed — admin- issuer gating is the canonical
supervisor signal; introducing a new permission at the JWT issuer
level is an out-of-scope JWT delta that lands in F12.x RBAC
housekeeping)
**And** an ABBC-F10.3-BE-1 SHALL be added to
`pending-fase-10.md` for FUTURE work to introduce the
`perm_arqueo_cerrar_cualquiera` permission at the JWT issuer level
(parallel to `perm_arqueo_cerrar` for own-session); this gives
operators a future-proof audit trail for supervisor-vs-operator
distinction in JWT claims (out of F10.3 scope).

#### Scenario: admin- JWT renders the supervisor variant

- **Given** the `useAuthStore.accessToken` payload decodes with
  `iss: 'admin-cloud'` (admin- prefix), `sucursales_permitidas:
  ['S1', 'S2', 'S3']` (multi-branch supervisor), and the page
  mounts
- **When** the page resolves the active branch (defaults to the
  first `sucursales_permitidas` if no prior selection)
- **Then** the page MUST render the per-session table for that
  branch
- **And** the page MUST show a "Sucursal: <branch-name>" badge
  with `data-testid="cierre-diario-branch-context"` so the
  supervisor confirms they're closing the right branch
- **And** the Confirmar button MUST be enabled
- **And** success navigates to `/` with the success banner.

#### Scenario: operador- JWT with single branch renders the operator variant

- **Given** `useAuthStore.accessToken` decodes with
  `iss: 'operador-cloud'`, `sucursales_permitidas: ['S1']` (single
  branch), and the page mounts
- **When** the page resolves the active branch
- **Then** the page MUST render the per-session table pre-scoped
  to S1
- **And** the Confirmar button MUST be enabled
- **And** success navigates to `/` (Dashboard, NOT
  `/login?closed=true` — F10.3 does NOT call `cerrarSesion`).

#### Scenario: backend returns `403 tenant_scope_violation` for cross-branch admin attempt surfaces the FE error

- **Given** the supervisor's `sucursales_permitidas` is `['S1']`
  (NOT `['S1', 'S2']`) but the page incorrectly tries to close S2
  (defensive — the page itself scopes to the first permitida,
  but a future regression might allow a branch switcher)
- **When** the POST returns `403 tenant_scope_violation` (verified
  at `caja_arqueo.py:138-150` for `operador-` cross-branch)
- **Then** the helper MUST return
  `{ kind: 'permiso_insuficiente', status: 403, error:
  'tenant_scope_violation' }`
- **And** the page MUST render the red banner
  `cierreDiario.errorPermisoInsuficiente` with the literal text
  "No tiene permiso para cerrar esta sucursal — contacte al
  administrador del sistema"
- **And** the form MUST remain editable so the supervisor can
  re-select a permitted branch.

### REQ-OPS-168 — `@deprecated` JSDoc tag on `useCierreDiario()` (T2 of F10.3 PR) without deletion; preserves F8.x `CierreDiarioDialog.tsx:91` caller

**Given** the buggy `useCierreDiario()` at
`apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts:100-118`
declares `payload.uuid_sesion: string` (line 109) which collides
with the backend cross-validation at
`backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py:122-128`
that REJECTS `cierre_dia` with non-null `uuid_sesion`
(`400 cierre_dia_no_acepta_uuid_sesion`), and the F8.x caller
`apps/electron-sucursal/src/features/caja/components/CierreDiarioDialog.tsx:91`
still invokes this helper via
`useArqueo().submit({ uuid_sesion, tipo_arqueo: 'cierre_dia', ... })`
(NOT via `useCierreDiario().ejecutar(...)` — verified: the dialog
calls `submit` directly, not `ejecutar`; the dialog's bug surface
is different but the helper remains on the deprecated track),
**When** `sdd-apply` deprecates the helper
**Then** the JSDoc block immediately above `useCierreDiario` MUST
include the tag `@deprecated` followed by the literal text:
"use the `useArqueo().submit({ uuid_sesion: null, tipo_arqueo:
'cierre_dia', ... })` path via `runCierreDiarioChain` from
`pages/cierreDiarioChain.ts` (REQ-OPS-166) for the F10.3 routed
page; the F8.x `CierreDiarioDialog` consumer remains on the
deprecated helper until a follow-up housekeeping PR migrates it"
**And** the function body MUST remain bit-identical (no behavior
change) — the bug remains, but the helper is documented as
deprecated and the FE team has a clear migration path
**And** a development-mode `console.warn(...)` MUST fire the first
time `useCierreDiario().ejecutar` is called when
`import.meta.env.DEV === true` (Vite injects this in dev mode;
production builds dead-code-eliminate the guard). The warning
message MUST include the literal text
`'useCierreDiario is deprecated — migrate to cierreDiarioChain
(REQ-OPS-166). Removal in next major.'`
**And** the helper MUST NOT be removed in F10.3 scope — the F8.x
`<CierreDiarioDialog>` consumer would regress (no compile-time
import error, runtime crash). Deletion is reserved for a future
housekeeping PR after the F8.x consumer migrates to the chain
helper (or to the new `useArqueo().submit({ uuid_sesion: null,
... })` direct path)
**And** the deprecation timeline MUST be recorded in
`openspec/changes/fase-10-3-cierre-diario/specs/deprecation-log.md`
(new file): "useCierreDiario deprecated 2026-09-21 in HU-F10.3
PR; removal target: HU-F11.x (sync worker UI migration) or later
Fase 11 housekeeping. F8.x CierreDiarioDialog.tsx:91 consumer
must migrate before removal."

#### Scenario: dev-mode console warning fires on `useCierreDiario().ejecutar` call

- **Given** `import.meta.env.DEV === true` (Vite dev server)
- **When** any code calls `useCierreDiario().ejecutar({ uuid_sesion:
  'S1', valor_efectivo_reportado: 100, ... })`
- **Then** `console.warn` MUST fire exactly once per page-load with
  the literal text
  `'useCierreDiario is deprecated — migrate to cierreDiarioChain
  (REQ-OPS-166). Removal in next major.'`
- **And** the helper's body MUST remain bit-identical (no behavior
  change to the existing buggy path — the warning is observability
  only).

#### Scenario: production build dead-code-eliminates the warn guard

- **Given** `import.meta.env.DEV === false` (Vite production build
  with terser/swc minification)
- **When** the helper is bundled
- **Then** the `console.warn` call MUST be tree-shaken (the
  `if (import.meta.env.DEV)` branch becomes unreachable; Vite +
  Rollup tree-shake it)
- **And** the helper's runtime behavior is bit-identical to the
  pre-F10.3 state.

### REQ-OPS-169 — `e2e/cierre-diario.spec.ts` Playwright extension with multi-session scenarios + supervisor variant + fecha-boundary rejections

**Given** `e2e/arqueo.spec.ts` (F10.1 file, extended at F10.2 with
3 cierre-turno scenarios per REQ-OPS-161) ships 6 total scenarios
under `test.skip` per the F9.x precedent (Engram `#1894`),
**When** `sdd-apply` extends the e2e surface
**Then** `apps/electron-sucursal/e2e/arqueo.spec.ts` MUST grow
exactly 4 new scenarios (extend F10.1 file per the F10.2 precedent):

1. **multi-session happy path (2 closed + 1 open)** — mock the
   `GET /caja/arqueo/resumen` response with 3 sesiones
   (S1 closed, S2 closed, S3 open by U1); mount
   `/caja/cierre-diario`; assert the table renders 3 rows; fill
   the form with `Σ|diferencia|=0`; click Confirmar; assert the
   intercepted POST body carries
   `{ uuid_sesion: null, tipo_arqueo: "cierre_dia",
   valor_efectivo_reportado: ...,
   valor_datafono_reportado: ... }` (no `justificacion`); assert
   the `bridge.imprimir` call fires with
   `auditoria_codigo === 'cierre_dia'`; assert the URL navigates
   to `/` (NOT `/login?closed=true`); assert
   `useAuthStore.getState().accessToken` remains non-null.
2. **`Σ|diferencia|>0` requires global `justificacion`** — mock
   the resumen with `Σ|diferencia|=3000`; assert the Confirmar
   button is disabled until `justificacion.length >= 3`; type
   the justificacion; assert the POST body carries the field;
   assert `alerta tipo_alerta='descuadre_critico'` fires.
3. **supervisor admin- JWT variant** — set the
   `useAuthStore.accessToken` claims to `{ iss: "admin-cloud",
   sucursales_permitidas: ["S1"] }` (or equivalent mock);
   navigate to `/caja/cierre-diario`; assert the supervisor
   variant renders (branch-context badge visible); complete the
   happy path; assert `useAuthStore.getState().accessToken`
   remains non-null AND the URL navigates to `/` (NOT
   `/login?closed=true`).
4. **fecha boundary — future date rejected** — use a future date
   in the date picker (or pass it as a query param mock if the
   picker uses a controlled value); assert the page renders a
   yellow banner `cierreDiario.fechaFuturoRechazado` and the
   Confirmar button is disabled (DA-F10.3-3 RESOLVED: future is
   rejected, past is read-only, today is writeable).

**And** all 4 scenarios MUST mark `test.skip` per F9.x precedent
(F10.1 + F10.2 e2e files all `test.skip`; CI gate is `tsc --noEmit`
+ `vitest run`; Playwright runs in a follow-up CI matrix when the
dev environment is stable)
**And** the scenarios MUST NOT mutate `prod.factura_pagos`
directly (`fn_factura_pagos_inmutable` trigger would fire;
defense in depth per `AGENTS.md` §3) — mocks via
`page.route('/api/v1/caja/arqueo/resumen', ...)` and
`page.route('/api/v1/caja/arqueo', ...)`
**And** the scenarios MUST NOT insert rows in a way that forks
the hash chain — single-shot per scenario; the
`job_sync_cloud.hash_chain_verifier_loop` (PR9b) is the safety net
**And** the scenarios MUST reuse the F10.1 fixtures
(`VALID_ARQUEO_PAYLOAD`, `ARQUEO_RESUMEN_FIXTURE`) where possible
to avoid drift; new fixtures (`ARQUEO_RESUMEN_POR_SESION_FIXTURE`
with 3 sesiones) MUST live alongside the legacy fixtures in
`e2e/arqueo.spec.ts`
**And** an axe-core check on `/caja/cierre-diario` MUST report
zero WCAG 2.1 AA violations (RNF-022; extends F10.1 + F10.2
axe-core coverage to the new page).

#### Scenario: multi-session happy path submits with cierre_dia discriminator and navigates to /

- **Given** the electron-sucursal dev server is up, the supervisor
  is authenticated with admin- JWT, the mock
  `GET /caja/arqueo/resumen` returns 3 sesiones (S1 closed, S2
  closed, S3 open) with `Σ|diferencia|=0`, the mock
  `POST /caja/arqueo` returns `201 { uuid: "AD0" }`
- **When** the supervisor navigates to `/caja/cierre-diario`,
  enters `Σ valor_efectivo_reportado=150000` and
  `Σ valor_datafono_reportado=30000`, leaves `justificacion`
  empty, clicks Confirmar
- **Then** the intercepted POST body MUST equal
  `{ uuid_sesion: null, tipo_arqueo: "cierre_dia",
  valor_efectivo_reportado: 150000,
  valor_datafono_reportado: 30000 }` (no `justificacion` field
  — `Σ|diferencia|=0`)
- **And** `bridge.imprimir` MUST be called exactly once with
  `kind='arqueo'` and `payload.auditoria_codigo === 'cierre_dia'`
- **And** the URL MUST navigate to `/` (Dashboard, NOT
  `/login?closed=true`)
- **And** `useAuthStore.getState().accessToken` MUST remain
  non-null
- **And** axe-core MUST report zero violations on `/` (the
  post-success Dashboard page, no leftover focus traps from the
  cierre-diario form).

#### Scenario: fecha future boundary rejects submission

- **Given** the supervisor picks a date 7 days in the future via
  the date picker (or the mock GET returns a 400 for future dates
  per the F1.13 boundary — verify behavior at design time; F10.3
  SPEC defensively assumes the FE guards before the GET round-trip)
- **When** the page renders with the future date
- **Then** the page MUST render the yellow banner
  `cierreDiario.fechaFuturoRechazado` with the literal text
  "La fecha seleccionada está en el futuro — no se permite
  cierre diario para fechas futuras"
- **And** the Confirmar button MUST be disabled
  (`data-testid="cierre-diario-confirmar"` `disabled={true}`)
- **And** the per-session table MUST NOT fetch (the hook key is
  `null` when fecha is in the future, so SWR skips the network
  call — efficiency guard against wasted backend round-trip).

## Drift reconciliation table

| # | Drift anchor (from proposal §Risks + this phase) | Spec resolution | Where it lands downstream |
|---|---|---|---|
| DA-F10.3-1 | Multi-session atomicity — backend MUST close ALL open sessions or NONE; verify F1.13 handler commits within one tx; FE assumes all-or-nothing success. | RESOLVED: KD-ARQUEO-01 single-commit invariant at `caja_arqueo.py:311` (`await session.commit()` covers 4 table families); Step 9 `cerrar_sesiones_del_dia_bulk` (KD-ARQUEO-03) executed in-tx before commit. REQ-OPS-164 scenario 3 codifies the all-or-none contract with explicit test that 5xx leaves all open sessions OPEN. | design.md: backend invariant note; tasks.md T3 (cierreDiarioChain) + T5 (page); apply: scenarios in `cierreDiario.test.tsx` mock the 5xx response and assert S3 stays OPEN. |
| DA-F10.3-2 | Supervisor closes OTHER operator's session. JWT scope must include `perm_arqueo_cerrar_cualquiera`. | RESOLVED via repo inspection (Q2 closed): backend gate at `caja_arqueo.py:61` is `requires_issuer("operador-", "admin-")`; admin- tokens have no `sucursal_uuid` pinning, so a supervisor with admin- JWT can close ANY branch's sessions. The permission `perm_arqueo_cerrar_cualquiera` does NOT exist in the codebase (grep 0 hits), but is NOT needed at the JWT issuer level — admin- issuer gating is the canonical supervisor signal. REQ-OPS-167 codifies the FE gate via `useAuthStore` admin- check. ABBC-F10.3-BE-1 added to `pending-fase-10.md` for FUTURE `perm_arqueo_cerrar_cualquiera` introduction at JWT issuer level (out of F10.3 scope; lands in F12.x RBAC housekeeping). | design.md: JWT issuer note; tasks.md T5 (page gate) + T7 (i18n `cierreDiario.*`); apply: scenarios in `cierreDiario.test.tsx` mock admin- and operador- claims and assert variant rendering. |
| DA-F10.3-3 | Fecha boundary — today default (writeable); past read-only (no new arqueo); future REJECTED. | RESOLVED: REQ-OPS-164 + REQ-OPS-169 scenario 4 codify the three states. The date picker `max=today` attribute blocks future dates at the UI layer; the hook key-gate at REQ-OPS-165 (`uuid_sucursal && fecha && accessToken`) returns `null` for future dates, skipping the network call (efficiency). The "past read-only" semantics are encoded by the page rendering the per-session table for past dates WITHOUT the Confirmar button (the arqueo write path is blocked at the UI layer for `fecha < today`). | design.md: date picker pattern; tasks.md T5; apply: page component uses `<Input type="date" max={todayISO()} />`. |
| DA-F10.3-4 | Per-session resumen shape — `useArqueoResumen` returns aggregate (`sesiones_cerradas` count, NO list). Backend REQ-OPS-097 may not return per-session rows. | RESOLVED via repo inspection (Q1 closed): the F1.13 backend `GET /caja/arqueo/resumen` ALREADY returns the per-session array since F1.13 shipped. `backend/.../schemas/caja.py:335-346` defines `ArqueoResumenRead { fecha, uuid_sucursal, sesiones: list[ArqueoResumenItem], cierre_dia: ArqueoResumenItem | None }`. F10.3 introduces the new SWR hook `useArqueoResumenPorSesion` (REQ-OPS-163) that consumes the per-session shape with a corrected Zod schema (REQ-OPS-165). The legacy `useArqueoResumen` aggregate schema is NOT mutated in F10.3 (regression guard for F10.1 callers); the drift is flagged as NEW-DA-F10.3-9 for a follow-up reconciliation PR. | design.md: hook contract; tasks.md T2 (hook) + T8 (e2e fixtures); apply: new hook + page uses `data.sesiones[]` for the per-session table. |
| DA-F10.3-5 | Aggregate-justification rule — if `Σ\|diferencia_cop\|>0` across all sessions, global `justificacion` OBLIGATORIA. Mirror F10.2 REQ-OPS-158. | RESOLVED: REQ-OPS-164 scenario 2 codifies the rule. The `<CierreDiarioForm requiredMode="cierre_dia">` selects the F10.2 `arqueoSchemaStrict` Zod variant (top-level `z.string().trim().min(3, 'justificacion_requerida')`); the page computes `Σ|diferencia|` from the per-session rows (REQ-OPS-163) and surfaces the totals below the table. When `Σ|diferencia|>0` AND `justificacion.length < 3`, the Confirmar button stays disabled. The rule composes with REQ-OPS-158: F10.2 already shipped the strict-mode branch; F10.3 reuses it via `requiredMode='cierre_dia'` (a forward hook from F10.2 per the F10.2 spec REQ-OPS-158 "F10.3 will reuse this branch" note). | design.md: Zod schema composition; tasks.md T4 (form); apply: `requiredMode='cierre_dia'` in the inline CierreDiarioForm, NOT in `<ArqueoSheet>` (which stays as the drawer for ArqueoParcial + CerrarTurno). |
| DA-F10.3-6 | escpos `auditoria_codigo='cierre_dia'` already accepted via F10.2 C5 regex extension; no escpos changes. | RESOLVED: REQ-OPS-166 scenario 1 codifies the wire flow. The `bridge.imprimir('arqueo', { uuid, auditoria_codigo: 'cierre_dia' })` call is bit-identical to F10.2's `cierre_turno` invocation; `lib/print/escposBuilder.ts:498` emits `Codigo: ${payload.auditoria_codigo}\n` and accepts both values without escpos changes. The 12-line body shape is shared across `auditoria` / `cierre_turno` / `cierre_dia` — only the discriminator differs. | design.md: data-flow note; tasks.md NONE; apply NONE — escpos dispatcher unchanged. |
| DA-F10.3-7 | Existing `useCierreDiario()` helper (`useArqueo.ts:100-118`) passes `uuid_sesion: string`; collide with backend's `uuid_sesion=null` requirement. Deprecate (mark `@deprecated`, leave body unchanged) in same PR. | RESOLVED via repo inspection (Q3 closed) + REQ-OPS-168. The JSDoc tag `@deprecated` + dev-mode `console.warn` mark the helper as deprecated without changing behavior. The F8.x CierreDiarioDialog.tsx:91 caller is NOT in the F10.3 migration path (the dialog calls `useArqueo().submit(...)` directly, not `useCierreDiario().ejecutar(...)`, so the dialog's bug surface is independent — the helper deprecation is forward-looking). Deletion is reserved for a future housekeeping PR (F11.x sync worker UI migration, or later Fase 11). The deprecation timeline is recorded in `specs/deprecation-log.md`. | design.md: none — deprecation is a documentation-only change; tasks.md T2 (RED test for the warn) + T2 (GREEN impl); apply: JSDoc + console.warn + deprecation-log.md. |
| DA-F10.3-8 | Strict-TDD 5-7x forecast: 200 LOC nominal → 1500-2500 net LOC actual (F10.1=1566, F10.2=2037 precedent, both ratified size:exception per `AGENTS.md`). | RESOLVED by orchestrator routing (`delivery_strategy=ask-on-risk`): the spec describes INTENT, the tasks forecast ~1500-2500 net LOC, and `sdd-apply` will surface the actual forecast at design time. The spec does NOT pre-seek exception; the orchestrator routes per `openspec/chores.tasks` (800 LOC nominal budget per commit; size:exception ratified for F10.1 + F10.2 precedent). | tasks.md: 8 atomic tasks per proposal T1-T8; apply: paired RED→GREEN commits per `work-unit-commits` skill; verify: lines + branches coverage per file. |
| **NEW** DA-F10.3-9 | F10.1 `useArqueoResumen` Zod schema (`useArqueo.ts:10-18`) is DRIFTED — expects aggregate fields (`total_efectivo_cop`, etc.) that the F1.13 backend has NEVER returned. | RESOLVED (deferred to follow-up PR, NOT in F10.3 scope): F10.3 introduces the corrected sibling hook `useArqueoResumenPorSesion` (REQ-OPS-163) with a fresh Zod schema (REQ-OPS-165). The legacy `useArqueoResumen` aggregate schema is NOT modified in F10.3 (regression guard for F10.1 ArqueoParcial.tsx + CierreDiarioDialog.tsx callers — both still call `useArqueoResumen` and would silently break if the Zod schema was mutated). A follow-up housekeeping PR (post-F10.3) reconciles `useArqueoResumen` to the new schema; ABBC-F10.3-FE-1 added to `pending-fase-10.md`. | tasks.md T2 (new hook, NO mutation of legacy); apply: new file `cierreDiarioHooks.ts` (or extension of `useArqueo.ts`) with the corrected schema. |

## Validation matrix

| Validator | File path | Scenarios | Threshold |
|---|---|---|---|
| `vitest` unit | `apps/electron-sucursal/src/features/caja/pages/__tests__/cierreDiarioChain.test.ts` (NEW) | 3: happy-path 2-step sequencer; bridge failure is non-fatal; backend `400 cierre_dia_no_acepta_uuid_sesion` surfaces input drift | lines ≥80, branches ≥75 |
| `vitest` unit | `apps/electron-sucursal/src/features/caja/hooks/__tests__/useArqueoResumenPorSesion.test.ts` (NEW) | 3: per-session array renders 3 rows; `cierre_dia` already-closed disables Confirmar; 401 triggers `useAuthStore.clear()` + `parkos:auth:cleared` | lines ≥85 |
| `vitest` unit | `apps/electron-sucursal/src/features/caja/components/__tests__/CierreDiarioForm.test.tsx` (NEW) | 2: `requiredMode='cierre_dia'` top-level rejection on render; button disabled until `justificacion.length >= 3` | lines ≥85 |
| `vitest` unit | `apps/electron-sucursal/src/features/caja/pages/__tests__/CierreDiario.test.tsx` (NEW) | 4: happy path multi-session closure; `Σ|diferencia|>0` requires justificacion; supervisor admin- variant; backend 5xx leaves S3 OPEN | lines ≥80, branches ≥75 |
| `vitest` unit | `apps/electron-sucursal/src/features/caja/hooks/__tests__/useCierreDiario.deprecation.test.ts` (NEW) | 2: dev-mode `console.warn` fires on `ejecutar(...)` call; production build tree-shakes the warn guard | lines ≥70 |
| `playwright` e2e | `apps/electron-sucursal/e2e/arqueo.spec.ts` (MODIFIED, extend F10.1 file) | 4 per REQ-OPS-169 (all `test.skip` per F9.x precedent; Engram `#1894`) | passes 100% when CI matrix enables Playwright |
| `tsc --noEmit` | workspace-wide | REQ-OPS-163..169 type-correct (no `any` for the per-session array; Zod schema discriminated by `cierre_dia` presence) | zero errors |
| `eslint` | workspace-wide | REQ-OPS-163..169 lint-clean (no unused `useCierreDiario` refactor; no unused Zod fields) | zero errors |
| `@axe-core/playwright` | `apps/electron-sucursal/e2e/arqueo.spec.ts` (last scenario) | 1: WCAG 2.1 AA on `/caja/cierre-diario` (page + form + table) | zero violations |
| `openspec/scripts/check_schema_match.py` | workspace-root | unchanged schema (F10.3 is frontend-only — no migration) | exits 0 |
| `pending-fase-10.md` integrity | workspace-root | ABBC-F10.2-BE-1 entry preserved; NEW ABBC-F10.3-BE-1 added (perm_arqueo_cerrar_cualquiera JWT issuer delta); NEW ABBC-F10.3-FE-1 added (useArqueoResumen aggregate Zod schema reconciliation) | text grep: `"ABBC-F10.2-BE-1"` present; `"ABBC-F10.3-BE-1"` present; `"ABBC-F10.3-FE-1"` present |

## Risk acknowledgements

| Risk id (proposal §Risks + this phase) | Status | Residual |
|---|---|---|
| DA-F10.3-1 — Multi-session atomicity | RESOLVED | REQ-OPS-164 scenario 3 codifies the all-or-none contract. KD-ARQUEO-01 backend invariant is the long-term backstop. E2E + unit coverage is the regression guard. |
| DA-F10.3-2 — Supervisor closes OTHER operator's session | RESOLVED (Q2 closed via repo inspection) | REQ-OPS-167 gates FE on admin- issuer; backend `requires_issuer("operador-", "admin-")` is the long-term backstop. ABBC-F10.3-BE-1 forward reference for future `perm_arqueo_cerrar_cualquiera` JWT issuer permission. |
| DA-F10.3-3 — Fecha boundary | RESOLVED | REQ-OPS-164 + REQ-OPS-169 scenario 4 lock the three states (today writeable, past read-only, future rejected). Hook key-gate efficiency: future dates skip the network call. |
| DA-F10.3-4 — Per-session resumen shape (Q1) | RESOLVED | REQ-OPS-163 + REQ-OPS-165 codify the per-session shape from `ArqueoResumenRead`. New-DA-F10.3-9 (legacy aggregate Zod drift) is forwarded to a follow-up PR. |
| DA-F10.3-5 — Aggregate-justification rule | RESOLVED | REQ-OPS-164 scenario 2 + F10.2 REQ-OPS-158 `requiredMode='cierre_dia'` strict-mode Zod variant lock the contract. |
| DA-F10.3-6 — escpos `auditoria_codigo='cierre_dia'` discriminator | RESOLVED (no code change) | `lib/print/escposBuilder.ts:498` emits `Codigo: ${payload.auditoria_codigo}` — `cierre_dia` flows through unchanged. The 12-line body shape is shared with `auditoria` and `cierre_turno`. |
| DA-F10.3-7 — `useCierreDiario()` deprecation | RESOLVED (Q3 closed via repo inspection) | REQ-OPS-168 codifies the `@deprecated` JSDoc + dev-mode `console.warn`. Helper is NOT deleted in F10.3 scope (F8.x CierreDiarioDialog.tsx:91 caller regression guard). Deletion target: F11.x sync worker UI migration or later Fase 11 housekeeping. Timeline in `specs/deprecation-log.md`. |
| DA-F10.3-8 — Strict-TDD coverage budget | RESOLVED (orchestrator routes) | 8 atomic tasks per proposal T1-T8, paired RED→GREEN commits per `work-unit-commits` skill. Forecast ~1500-2500 net LOC; size:exception pattern (F10.1=1566, F10.2=2037) is the precedent. Orchestrator will ratify per `delivery_strategy=ask-on-risk`. |
| **NEW** DA-F10.3-9 — F10.1 `useArqueoResumen` Zod drift | RESOLVED (deferred) | F10.3 introduces the new sibling hook `useArqueoResumenPorSesion` with a corrected schema (REQ-OPS-163 + REQ-OPS-165). The legacy aggregate schema is NOT modified (regression guard). ABBC-F10.3-FE-1 in `pending-fase-10.md` for a follow-up housekeeping PR. |
| **NEW** — F8.x CierreDiarioDialog.tsx:91 caller regression risk | RESOLVED | The dialog calls `useArqueo().submit(...)` directly (line 89-95), NOT `useCierreDiario().ejecutar(...)`. The dialog has its OWN bug surface (passes `uuid_sesion: uuid_sesion` where backend requires `null` for cierre_dia) but is OUT OF F10.3 SCOPE per proposal §Out-of-Scope. The dialog continues working with the existing bug. Future fix is in a separate housekeeping PR (out of Fase 10). |

## Forward hooks

- **HU-F11.x (sync worker UI + alertas CU-07/14)**: will reuse the
  `runCierreDiarioChain` helper (REQ-OPS-166) and the
  `useArqueoResumenPorSesion` SWR hook (REQ-OPS-163) for any
  "Cierre diario desde worker UI" flow. The supervisor-gated
  variant (REQ-OPS-167) is the canonical pattern; F11.x sync
  worker may add a "Force cierre diario" button that uses the
  same chain.
- **HU-F12.x (reportería + RBAC housekeeping)**: ABBC-F10.3-BE-1
  introduces the `perm_arqueo_cerrar_cualquiera` permission at
  the JWT issuer level, parallel to `perm_arqueo_cerrar` for
  own-session closures. This gives operators a future-proof
  audit trail for supervisor-vs-operator distinction in JWT
  claims. F12.x is the natural home because RBAC housekeeping
  is a Fase 12 deliverable.
- **ABBC-F10.2-BE-1 (arqueo orphan reconciler, post-Fase-13
  backend admin)**: the long-term automated reconciler that
  retries the PUT on orphan arqueos. Detection:
  `prod.arqueo WHERE uuid_sesion IS NULL AND estado = 'pendiente'
  AND created_at < now() - INTERVAL '15 minutes'`. Action:
  re-issue `PUT /caja-sesion/sesion/{uuid}/cerrar` under a
  supervisor-aware retry policy (max 3 attempts, exponential
  backoff). Out of scope for Fase 10; the FE UX (F10.2
  REQ-OPS-159 cases 5-7) is the interim remediation.
- **ABBC-F10.3-BE-1 (perm_arqueo_cerrar_cualquiera JWT issuer
  delta, post-F12.x)**: forward reference for introducing the
  supervisor permission at the JWT issuer level. Out of F10.3
  scope; lands in F12.x RBAC housekeeping.
- **ABBC-F10.3-FE-1 (useArqueoResumen aggregate Zod schema
  reconciliation, post-F10.3 housekeeping)**: forward reference
  for reconciling the legacy F10.1 `useArqueoResumen` aggregate
  Zod schema to the actual F1.13 backend response shape (per
  NEW-DA-F10.3-9). The F10.3 spec introduces the new sibling
  hook `useArqueoResumenPorSesion` (REQ-OPS-163); the legacy
  hook stays untouched in F10.3 scope (regression guard). The
  follow-up housekeeping PR mutates the legacy hook's Zod
  schema to match the backend and migrates the F10.1
  ArqueoParcial.tsx + CierreDiarioDialog.tsx callers to use
  either the new hook OR a unified aggregate projection.
- **`bridge.imprimir('arqueo', payload)` reuse**: F10.1 ships
  the escpos dispatcher; F10.2 and F10.3 can both invoke it
  without escpos changes. The 12-line body shape is shared
  across `auditoria` / `cierre_turno` / `cierre_dia` — only the
  `auditoria_codigo` discriminator differs.
- **`useArqueoResumen` aggregate Zod schema (F10.1 legacy)**:
  OUT OF F10.3 SCOPE. F10.3 introduces the new sibling hook
  (REQ-OPS-163) for the per-session shape; the legacy aggregate
  schema is forwarded to ABBC-F10.3-FE-1 for a follow-up
  housekeeping PR. The legacy hook continues to be called by
  F10.1 ArqueoParcial.tsx and F8.x CierreDiarioDialog.tsx —
  both retain their existing behavior (which is broken against
  the F1.13 backend, but that's a pre-existing drift, not
  introduced by F10.3).

## References

- Base spec: `openspec/specs/operations/spec.md` (REQ-OPS-091..097
  F1.13 backend; REQ-OPS-027..029 F3.3 sesion cycle;
  REQ-OPS-152..156 F10.1 arqueo parcial; REQ-OPS-157..162 F10.2
  cierre de turno).
- Proposal: `openspec/changes/fase-10-3-cierre-diario/proposal.md`.
- F10.1 archived delta spec:
  `openspec/changes/archive/2026-09-21-fase-10-1-arqueo-parcial/specs/spec.md`.
- F10.2 archived delta spec:
  `openspec/changes/archive/2026-09-21-fase-10-2-cierre-turno/specs/spec.md`.
- Engram: `#1908` (sdd-propose HU-F10.3 proposal); `#1909` (this
  spec, sdd-spec); `#1907` (F10.2 archive session); `#1899` (Q1
  decision: KEEP F3.3 logout — F10.3 does NOT call `cerrarSesion`
  per DA-F10.3-2); `#1894` (F10.1 size exception, F9.x
  `test.skip` precedent); `#1888` (F10.1 sync verifier); `#1887`
  (Fase 10 SDD preflight).
- Architectural canon: `AGENTS.md` §1 (audit-first), §2
  (bi-temporal), §3 (C/Q/U only — no DELETE), §3.4 (sync canon,
  hash chain).
- Plan: `plan.md:2246-2264` (HU-F10.3 — Cierre diario).
- Substrate files (verified paths):
  - `apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts`
    (lines 100-118: buggy `useCierreDiario()` — `@deprecated`
    target; lines 10-18: drifted aggregate Zod schema —
    ABBC-F10.3-FE-1 forward reference)
  - `apps/electron-sucursal/src/features/caja/components/ArqueoSheet.tsx`
    (lines 122-123: `requiredMode='cierre_dia'` already accepted
    by the strict-mode Zod variant per F10.2 REQ-OPS-158)
  - `apps/electron-sucursal/src/features/caja/components/CierreDiarioDialog.tsx`
    (line 91: `useArqueo().submit({ ..., tipo_arqueo: 'cierre_dia' })`
    caller — F8.x, OUT OF F10.3 SCOPE per proposal §Out-of-Scope;
    bug surface independent of `useCierreDiario()` deprecation)
  - `apps/electron-sucursal/src/features/caja/pages/CerrarTurno.tsx`
    (F10.2 sequencer pattern to mirror — 3 steps for F10.2 vs 2
    steps for F10.3 because backend `cerrar_sesiones_del_dia_bulk`
    handles per-session closure in-tx)
  - `apps/electron-sucursal/src/features/caja/pages/cerrarTurnoChain.ts`
    (F10.2 pure helper pattern to mirror — discriminated result
    envelope, no retry loop, no client-side DELETE)
  - `apps/electron-sucursal/src/features/caja/hooks/useSesionActiva.ts`
    (F3.3 logout-on-success helper — OWNED by `cerrarSesion`; F10.3
    does NOT call it per DA-F10.3-2)
  - `apps/electron-sucursal/src/features/caja/api/sesionActivaApi.ts`
    (F3.3 HTTP layer — `cerrarSesion()` PUT helper; F10.3 does NOT
    call it)
  - `apps/electron-sucursal/src/renderer/App.tsx` (route registration
    at line 61-68: F10.2 `/caja/cerrar-turno` pattern to mirror;
    F10.3 adds `/caja/cierre-diario` at line 70-76)
  - `apps/electron-sucursal/src/lib/print/escposBuilder.ts`
    (line 498: `Codigo: ${payload.auditoria_codigo}` —
    `cierre_dia` flows through unchanged)
  - `apps/electron-sucursal/src/renderer/i18n/locales/caja.json`
    (`cierreDiario.*` keys — extend, don't replace)
  - `apps/electron-sucursal/e2e/arqueo.spec.ts` (F10.1 file,
    extended at F10.2 with 3 cierre-turno scenarios; F10.3 extends
    with 4 cierre-diario scenarios per REQ-OPS-169)
  - `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py`
    (line 61: `requires_issuer("operador-", "admin-")` — admin-
    grants supervisor access; line 122-128: cierre_dia
    cross-validation rejects `uuid_sesion != null`; line 311:
    KD-ARQUEO-01 single-commit atomicity invariant; line 337-413:
    GET resumen handler returns per-session `sesiones[]` array)
  - `backend/packages/parkos_core/src/parkos_core/schemas/caja.py`
    (lines 316-346: `ArqueoResumenItem` + `ArqueoResumenRead` —
    source of truth for the per-session shape)
  - `backend/packages/parkos_core/src/parkos_core/auth/tokens.py`
    (line 144-152: `_audience_for` — admin- returns
    `'parkos-admin'`, distinct from `'parkos-branch'` for
    operador-, no `sucursal_uuid` pinning)
  - `pending-fase-10.md` (item #4: ABBC-F10.2-BE-1, preserved;
    NEW: ABBC-F10.3-BE-1 for perm_arqueo_cerrar_cualquiera;
    NEW: ABBC-F10.3-FE-1 for useArqueoResumen aggregate Zod
    reconciliation)
