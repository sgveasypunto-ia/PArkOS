# Delta Spec: `operations` — HU-F10.1 Arqueo Parcial (frontend)

## Phase

HU-F10.1 (Fase 10, primera de 3). Frontend-only delta sobre el spec base
`operations` (REQ-OPS-091..097 shipped en F1.13). Branch
`feature/hu-f10-1-arqueo-parcial`. Author `Parkos Dev <dev@parkos.local>`.
Strict-TDD ACTIVE. 800 LOC review budget (HU ~260).

## Gap

`REQ-OPS-152..156` — los siguientes cinco correlativos libres después del
último REQ-OPS-151 existente. NO se reusan los rangos 091..097 (perimidos
a la F1.13 backend) ni se mezclan con los números 176..185 que el
proposal mencionó pero no existen en el spec (último real: REQ-OPS-151,
verificado por grep recursivo sobre `openspec/specs/operations/spec.md`).

## ADDED Requirements

### REQ-OPS-152 — `<ArqueoParcial>` routed page wraps `<ArqueoSheet>` + `useArqueo` SWR at `/caja/arqueo-parcial`

**Given** the operator is authenticated with an `operador-` JWT, an active
`sesion` exists for the branch pinned by the electron-sucursal shell, and
the operator presses `F4` (or clicks the sidebar Arqueo link) from the
Dashboard
**When** the renderer navigates to `/caja/arqueo-parcial`
**Then** the route MUST mount a new page
`apps/electron-sucursal/src/features/caja/pages/ArqueoParcial.tsx` that
RENDERS the existing `<ArqueoSheet />` (`features/caja/components/ArqueoSheet.tsx`)
verbatim, passing `uuid_sesion={sesionActual.uuid}` from
`useSesionActiva()` (F3.3 / REQ-OPS-120) as the single prop
**And** the route MUST be declared in `apps/electron-sucursal/src/renderer/App.tsx`
BEFORE the `*` catch-all so FastAPI-equivalent React Router matches the
literal path ahead of any parametric fallback
**And** the page MUST preserve the existing F4 hotkey + sidebar button
behavior in `Dashboard.tsx` (the existing `openDrawer('arqueo',
'sidebar-arqueo')` call from F3.3 continues to drive the same drawer)
**And** the page MUST NOT render a competing drawer instance when the
route is mounted — a single `<ArqueoSheet>` instance owns the
`useDashboardDrawerStore` open state
**And** the route MUST be keyboard-accessible per WCAG 2.1 AA
(`@axe-core/playwright` zero violations; RNF-022).

#### Scenario: F4 hotkey opens drawer inside the routed page

- **Given** an operador is logged in with an active `sesion` for branch X
  and is currently viewing `/dashboard`
- **When** the operator presses the `F4` key
- **Then** the URL MUST navigate to `/caja/arqueo-parcial`
- **And** the `<ArqueoSheet>` drawer MUST open on the right side of the
  viewport (`side="right"`) bound to `useDashboardDrawerStore.open ===
  'arqueo'`
- **And** the sheet MUST display the form with `uuid_sesion` populated
  from the active session
- **And** closing the sheet MUST return focus to the originating anchor
  (F3.3 `lastAnchorId` precedent — `document.getElementById(lastAnchorId)
  ?.focus()`).

#### Scenario: deep-link to `/caja/arqueo-parcial` without active session renders fallback

- **Given** an operador opens `/caja/arqueo-parcial` directly (no prior
  session, no F4 hotkey), and `useSesionActiva()` returns `{ sesion: null,
  isLoading: false }`
- **When** the routed page mounts
- **Then** the page MUST render the existing F3.3 fallback message
  inviting the operator to open a turn first (`AbrirTurno` precedent)
- **And** the `<ArqueoSheet>` MUST render with `uuid_sesion={null}` so
  the submit button is disabled (`disabled={!uuid_sesion || isSubmitting}`)
- **And** no 404 / 500 surface is allowed on the routed page — the page
  is a UX shell, not a network entry.

### REQ-OPS-153 — `useArqueo.submit` payload field naming aligned to REQ-OPS-091 backend contract

**Given** the backend `POST /caja/arqueo` (REQ-OPS-091 §3700 single-commit)
expects the canonical field set
`{ uuid_sesion, tipo_arqueo, valor_efectivo_reportado, valor_datafono_reportado,
justificacion? }`, and the current
`apps/electron-sucursal/src/features/caja/hooks/useArqueo.ts::useArqueo().submit`
declares `efectivo_contado_cop` / `datafono_contado_cop` / `observaciones`
**When** `sdd-apply` edits `useArqueo.ts` and the dependent Zod schema
`arqueoSchema` in `features/caja/components/ArqueoSheet.tsx`
**Then** the `submit` argument type MUST be renamed to
`valor_efectivo_reportado: number`, `valor_datafono_reportado: number`,
and `justificacion?: string`
**And** the Zod `arqueoSchema` keys MUST match (`valor_efectivo_reportado:
z.coerce.number().int().nonnegative()`,
`valor_datafono_reportado: z.coerce.number().int().nonnegative()`,
`justificacion: z.string().trim().optional()`)
**And** the `<ArqueoSheet>` form fields MUST rename accordingly
(`name="valor_efectivo_reportado"`, `name="valor_datafono_reportado"`,
`name="justificacion"`) and the `data-testid` attributes MUST be
`arqueo-efectivo`, `arqueo-datafono`, `arqueo-justificacion`
**And** the `useCierreDiario.ejecutar()` payload MUST use the renamed
keys verbatim — `useCierreDiario` chains `submit(...)` with
`tipo_arqueo='cierre_dia'`, so the rename propagates automatically
**And** the renamed payload MUST match the Zod schema in the same module
(`z.object({ uuid: z.string().uuid() })` for the response — unchanged)
**And** the existing `useArqueoResumen` SWR hook MUST stay unchanged
(it already parses the correct field shape — only the `submit` path
renames)
**And** the change MUST land as a single atomic refactor (no
intermediate state where the UI sends one name and the hook expects
another — would otherwise produce a silent 422).

#### Scenario: happy-path submit reaches backend with renamed keys

- **Given** the renamed `useArqueo.submit` is wired to the form, and an
  active `sesion.uuid = S`
- **When** the operator enters `100000` in efectivo and `0` in datafono
  and clicks Confirmar
- **Then** the request body MUST be exactly
  `{ uuid_sesion: "S", tipo_arqueo: "auditoria",
  valor_efectivo_reportado: 100000, valor_datafono_reportado: 0 }`
  (no `observaciones`, no `efectivo_contado_cop`)
- **And** the backend MUST return `201 Created` with `{ uuid: <nuevo_uuid> }`
  (REQ-OPS-091 happy path)
- **And** the sheet MUST close and return focus to `lastAnchorId` per the
  existing F3.3 precedent.

#### Scenario: missing justificacion on diferencia=0 passes the schema

- **Given** the operator enters `valor_efectivo_reportado` matching the
  `valor_esperado_efectivo` returned by `GET /caja/arqueo/resumen` so
  `diferencia === 0`
- **When** the form is submitted without `justificacion`
- **Then** the Zod `arqueoSchema` MUST accept the payload (justificacion
  is `.optional()` at the schema level — REQ-OPS-096 backend permits,
  REQ-OPS-154 UI gates only when `|diferencia|>0`)
- **And** the request MUST reach the backend with NO `justificacion`
  field
- **And** the backend MUST accept the missing field per REQ-OPS-094
  (justificacion required only when `diferencia != 0` AND
  `tipo_arqueo in ('cierre_turno','cierre_dia')`).

### REQ-OPS-154 — `justificacion` Zod refinement required when `|diferencia|>0`

**Given** the live resumen fetch from `GET /caja/arqueo/resumen` returns
`valor_esperado_efectivo`, `valor_esperado_datafono`, `tolerancia_efectivo`,
`tolerancia_datafono` (per REQ-OPS-097 §3919 formula
`valor_inicial_efectivo + Σ factura_pagos`)
**When** the operator enters `valor_efectivo_reportado` and
`valor_datafono_reportado` and the renderer computes
`diferencia_cop = (reportado - esperado)` per medio
**Then** the `arqueoSchema` refinement MUST require `justificacion.min(3)`
when `Math.abs(diferencia_cop_efectivo) > 0` OR
`Math.abs(diferencia_cop_datafono) > 0`
**And** the UI MUST display a shadcn `<Alert variant="warning">` when
`Math.abs(diferencia_cop) > tolerancia_efectivo` (per medio), with the
i18n key `caja.descuadre_pct` informational subtext — the
`descuadre_pct` percentage is INFORMATIONAL only (NEVER a gate)
**And** the alert MUST NOT block submission — the operator MAY confirm
the arqueo even with `|diferencia|>tolerancia`; the backend inserts
`alerta 'descuadre_critico'` per REQ-OPS-095 when the threshold is
crossed
**And** the `justificacion` field MUST render BELOW the diferencia
warning (visual hierarchy: warning first, justification second) and MUST
show the `<FormMessage />` error when validation fails
**And** the renderer MUST NOT compute the expected values locally
(reading `factura_pagos` directly is forbidden — `fn_factura_pagos_inmutable`
trigger blocks any UPDATE; expected comes from the GET endpoint only,
defense in depth per AGENTS.md §3).

#### Scenario: diferencia > 0 surfaces warning + blocks submit until justificacion entered

- **Given** the resumen returns `valor_esperado_efectivo=50000`,
  `tolerancia_efectivo=1000`, and the operator enters
  `valor_efectivo_reportado=47000` (diferencia = -3000, exceeds tolerance)
- **When** the form is rendered
- **Then** a `<Alert variant="warning">` MUST show the message
  `caja.descuadre_warning` with the `valor_esperado`, `valor_reportado`,
  and `diferencia_cop` formatted via `formatCOP()` (DEC-SUC-07 helper in
  `lib/print/escposTemplates.ts:69`)
- **And** the submit button MUST be disabled while `justificacion.length < 3`
- **And** after the operator types a justificacion of ≥3 chars, the
  button re-enables and submission proceeds
- **And** the request body MUST include the `justificacion` field
  verbatim.

#### Scenario: diferencia = 0 has no warning and no required justificacion

- **Given** the operator enters the exact `valor_esperado_*` returned by
  the resumen
- **When** the form is rendered
- **Then** no `<Alert>` is rendered
- **And** the `justificacion` field MUST be optional (no required marker,
  no FormMessage)
- **And** the submit button MUST be enabled without any justificacion.

### REQ-OPS-155 — `'arqueo'` ESC/POS dispatcher key added to `TiqueteTipo` union

**Given** the renderer dispatches `bridge.imprimir(escposBuilder.build(tipo,
payload))` for each printed ticket, and the current `TiqueteTipo` union
in `lib/print/escposTemplates.ts` covers only `entrada | salida |
salida-mensualidad | reimpresion | recibo_pago`
**When** `sdd-apply` extends the dispatcher to support the F10.1
arqueo-parcial print
**Then** `TiqueteTipo` MUST grow a sixth literal: `'arqueo'` (the F8.3
REQ-OPS-175 drift anchor precedent forbids alternate spellings — only
`'arqueo'` is allowed; NOT `'arqueo_parcial'`, NOT `'ticket_arqueo'`)
**And** `TIQUETE_TIPOS` MUST include `'arqueo'` as the 6th entry
**And** a new Zod schema `arqueoPayloadSchema` MUST be declared with the
fields: `sucursal` (encabezado, same `sucursalSchema` reused),
`uuid_sesion` (uuid), `base_efectivo_cop` (int, nonneg),
`valor_esperado_efectivo` (int, nonneg),
`valor_esperado_datafono` (int, nonneg),
`valor_reportado_efectivo` (int, nonneg),
`valor_reportado_datafono` (int, nonneg),
`diferencia_efectivo` (int, signed),
`diferencia_datafono` (int, signed), `tolerancia_efectivo` (int, nonneg),
`tolerancia_datafono` (int, nonneg), `justificacion` (string, optional),
`auditoria_codigo` (string, format `^AUD-\d{8}-\d{6}$`), `fecha` (ISO
8601 datetime), `uuid_sesion_short` (string, last 8 chars of
`uuid_sesion`)
**And** the `payloadSchemaByTipo` map MUST add the `arqueo` entry
**And** a `buildArqueoBody(payload)` helper MUST be added in
`lib/print/escposBuilder.ts` emitting, in order:
  1. centered bold header `ARQUEO PARCIAL — <sucursal.encabezado>` (DEC-SUC-28)
  2. `Sello: *** ARQUEO PARCIAL ***` wrapped in `escText2x()` /
     `escTextReset()` (DEC-SUC-04 sellos precedent)
  3. `Codigo: <auditoria_codigo>`
  4. `Fecha: <formatFechaCorta(fecha)>` (es-CO short per F6.2)
  5. `Sesion: <uuid_sesion_short>` (last 8 chars; the full UUID is
     captured by the backend `arqueo` row in `log_transaccional` for
     audit chain)
  6. `Base: <formatCOP(base_efectivo_cop)>`
  7. `Esperado efectivo: <formatCOP(valor_esperado_efectivo)>`
  8. `Reportado efectivo: <formatCOP(valor_reportado_efectivo)>`
  9. `Diferencia efectivo: ±<formatCOP(diferencia_efectivo)>` with sign
     prefix (sign MUST be `+` for non-negative, `-` for negative — NEVER
     `±`)
  10. `Tolerancia efectivo: <formatCOP(tolerancia_efectivo)>`
  11. same 5-line block for `datafono`
  12. `Justificacion: <justificacion>` ONLY when `justificacion.length > 0`
      (no line when absent — silent omission)
**And** a `buildArqueoBuffer(payload)` MUST wrap the body with the standard
`escInit() / buildArqueoBody() / cutPartial() / lf()` envelope (DEC-SUC-08
precedent)
**And** the `build()` dispatcher switch MUST add the `case 'arqueo'`
branch (exhaustiveness preserved — `tsc --noEmit` fails if the case is
forgotten)
**And** the renderer MUST print the buffer via
`bridge.imprimir('arqueo', payload)` IMMEDIATELY after a successful
`POST /caja/arqueo` (no deferral — the audit trail must include the
printed copy)

#### Scenario: buildArqueoBuffer emits all 12 conceptual fields with correct formatting

- **Given** an `ArqueoPayload` with base=50000, esperado_efectivo=120000,
  reportado_efectivo=118000, diferencia_efectivo=-2000,
  tolerancia_efectivo=1000, esperado_datafono=30000,
  reportado_datafono=30000, diferencia_datafono=0,
  tolerancia_datafono=500, justificacion="Faltante en caja menor",
  auditoria_codigo="AUD-20260921-000123",
  fecha="2026-09-21T14:30:00.000Z",
  uuid_sesion="abc12345-6789-0abc-1234-56789abcdef0"
- **When** `escposBuilder.build('arqueo', payload)` is invoked
- **Then** the returned `Buffer` MUST contain the literal UTF-8
  substrings: `"ARQUEO PARCIAL — "`, `"*** ARQUEO PARCIAL ***"`,
  `"AUD-20260921-000123"`, `"21/09/2026 14:30"`, `"Sesion: abcdef0"` (last
  8 chars after stripping dashes), `"$ 50.000"`, `"$ 120.000"`,
  `"$ 118.000"`, `"- $ 2.000"` (signed diferencia), `"$ 1.000"`,
  `"$ 30.000"`, `"$ 30.000"`, `"$ 0"`, `"$ 500"`, `"Justificacion:
  Faltante en caja menor"`
- **And** the buffer MUST start with `0x1B 0x40` (ESC @ init) and end
  with `0x1D 0x56 0x00 0x0A` (GS V 0 partial cut + LF) — same envelope
  as the other 5 builders.

#### Scenario: justificacion absent emits no `Justificacion:` line

- **Given** the same payload but `justificacion` is the empty string
- **When** `buildArqueoBuffer(payload)` is invoked
- **Then** the returned `Buffer` MUST NOT contain the literal substring
  `"Justificacion:"` (no empty line, no placeholder).

### REQ-OPS-156 — `e2e/arqueo.spec.ts` Playwright 3-scenario end-to-end coverage

**Given** the new routed page, renamed hook, and `'arqueo'` dispatcher
land atomically with the strict-TDD RED→GREEN pair per
`work-unit-commits` skill
**When** `sdd-apply` adds `apps/electron-sucursal/e2e/arqueo.spec.ts`
**Then** the file MUST declare exactly 3 `@playwright/test` scenarios:

1. **happy-path with diferencia=0** — open `/caja/arqueo-parcial` with
   `sesion_activa` mocked at the SWR layer, type the exact
   `valor_esperado_*` from the resumen, click Confirmar, assert the
   backend POST receives the renamed fields verbatim
   (`valor_efectivo_reportado` etc.), the response is `201`, the sheet
   closes, focus returns to `lastAnchorId`, and the bridge.imprimir call
   fires once with `'arqueo'` dispatcher key.
2. **warning + required justificacion path** — same boot, but type a
   `valor_efectivo_reportado` that produces `diferencia = -3000` against
   `tolerancia_efectivo=1000`, assert the `<Alert variant="warning">` is
   rendered with `caja.descuadre_warning` text, the submit button is
   disabled while `justificacion` is empty, becomes enabled after
   typing ≥3 chars, and the POST body carries the justificacion field.
3. **field-name regression guard** — assert the old
   `efectivo_contado_cop` / `datafono_contado_cop` / `observaciones`
   keys are NOT present in any POST body captured during the suite
   (intercept the `parkosFetch` call via Playwright's
   `page.route('/api/v1/caja/arqueo', ...)` and assert the JSON keys)

**And** the test file MUST NOT mutate `prod.factura_pagos` directly
(drift anchor #6 — `fn_factura_pagos_inmutable` trigger would fire; the
test mocks the resumen endpoint with `page.route()` instead, defense in
depth per AGENTS.md §3)
**And** the test file MUST NOT insert rows in a way that forks the hash
chain — single-shot per scenario; `job_sync_cloud.hash_chain_verifier_loop`
is the safety net (already shipped per Engram session #1888)
**And** `pnpm --filter electron-sucursal exec playwright test
e2e/arqueo.spec.ts` MUST run green in CI before merge to `dev`
**And** an axe-core check on `/caja/arqueo-parcial` MUST report zero
WCAG 2.1 AA violations (RNF-022).

#### Scenario: happy path submits with renamed keys and prints the arqueo buffer

- **Given** the electron-sucursal dev server is up, the operador is
  authenticated, the active `sesion.uuid = S`, and the resumen mock
  returns `{ valor_esperado_efectivo: 100000,
  valor_esperado_datafono: 0, tolerancia_efectivo: 1000,
  tolerancia_datafono: 500 }`
- **When** the operator navigates to `/caja/arqueo-parcial`, types 100000
  in efectivo and 0 in datafono, and clicks Confirmar
- **Then** the intercepted POST body MUST equal
  `{ uuid_sesion: "S", tipo_arqueo: "auditoria",
  valor_efectivo_reportado: 100000, valor_datafono_reportado: 0 }`
  (no `observaciones`, no legacy keys)
- **And** `bridge.imprimir` MUST be called exactly once with kind=`'arqueo'`
- **And** the sheet MUST close (DOM no longer has `[data-testid=arqueo-sheet][data-state=open]`)
- **And** axe-core MUST report zero violations on the page.

#### Scenario: field-name regression guard rejects legacy keys

- **Given** the suite has run any of the 3 scenarios
- **When** `page.route('/api/v1/caja/arqueo', route => route.continue())`
  captures the POST body
- **Then** the JSON MUST NOT contain keys `efectivo_contado_cop`,
  `datafono_contado_cop`, or `observaciones` (legacy drift anchor #1)
- **And** the JSON MUST contain exactly the renamed keys when
  `|diferencia|>0` (justificacion present): `valor_efectivo_reportado`,
  `valor_datafono_reportado`, `justificacion`
- **And** when `diferencia=0`, `justificacion` MUST be absent (not sent
  as empty string).

## Drift reconciliation table

| # | Drift anchor (from proposal §Risks) | Spec resolution | Where it lands downstream |
|---|---|---|---|
| 1 | Field naming: `efectivo_contado_cop` vs `valor_efectivo_reportado` — silent 422 risk | RESOLVED in REQ-OPS-153 (rename + Zod + testid + e2e regression guard REQ-OPS-156 scenario 3). UI aligns to backend. | design.md: data-model delta; tasks.md T1+T2 (single atomic refactor); apply: rename + test. |
| 2 | AC `/caja/arqueo-parcial` routed page; current UX is a Sheet drawer | RESOLVED in REQ-OPS-152 — route WRAPS drawer (preserves F4 hotkey + sidebar anchor + `useDashboardDrawerStore` state). No competing drawer instance. | design.md: component tree; tasks.md T1; apply: new page file + route line. |
| 3 | BR1 base configurable vs `sesion.valor_inicial_efectivo` — vigente or snapshot? | RESOLVED with documentation (NO schema change required). REQ-OPS-097 §3919 already reads `sesion.valor_inicial_efectivo` at the moment of the GET; this is the vigente base AT THE TIME OF THE QUERY (the column IS the vigente base snapshot of the session). Frontend consumes as-is — no `configuracion_caja.base_efectivo_vigente` migration needed for F10.1. If a future HU needs the historical base at session open, that is a separate backend ticket. | design.md: data-flow note; tasks.md: NONE; apply: NONE. |
| 4 | Justification asymmetry: UI requires on `|diferencia|>0`; backend REQ-OPS-096 accepts `auditoria` without it | RESOLVED with documentation (no code change). REQ-OPS-154 codifies the asymmetry: UI is the gatekeeper for warning + required-justification; backend permits as audit-trail-only (REQ-OPS-094 only requires justificacion on `cierre_turno`/`cierre_dia`, NOT on `auditoria`). | design.md: control-flow note; tasks.md: NONE (already in REQ-OPS-154); apply: NONE. |
| 5 | `'arqueo'` ESC/POS dispatcher key missing | RESOLVED in REQ-OPS-155 — `'arqueo'` added to `TiqueteTipo`, `TIQUETE_TIPOS`, `payloadSchemaByTipo`, body builder + buffer + dispatcher switch. | design.md: byte-layout spec; tasks.md T3; apply: extend escposTemplates + escposBuilder. |
| 6 | `factura_pagos` immutability | DOCUMENTED in REQ-OPS-154 (renderer MUST NOT compute expected by summing local state — fetch GET only) and REQ-OPS-156 (e2e MUST NOT mutate `prod.factura_pagos` — mocks via `page.route()`). | design.md: data-isolation note; tasks.md: NONE (already in REQ-OPS-154/156); apply: enforce via code review. |
| 7 | Hash chain extension on every `[A]` row | DOCUMENTED in REQ-OPS-156 (e2e is single-shot per scenario; no out-of-order writes; `job_sync_cloud.hash_chain_verifier_loop` is the safety net). | design.md: operational note; tasks.md: NONE; apply: NONE — rely on already-shipped verifier loop (Engram #1888). |

## Validation matrix

| Validator | File path | Scenarios | Threshold |
|---|---|---|---|
| `vitest` unit | `apps/electron-sucursal/src/features/caja/pages/__tests__/ArqueoParcial.test.tsx` (NEW) | 3: route mounts + sheet wraps; live diferencia alert renders; field rename in submit | lines ≥90, branches ≥85 |
| `vitest` unit | `apps/electron-sucursal/src/features/caja/hooks/__tests__/useArqueo.test.ts` (NEW) | 2: renamed payload shape; resumen hook unchanged | lines ≥90 |
| `vitest` unit | `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.arqueo.test.ts` (NEW) | 3: 12-field layout with literal substrings; justificacion absent; envelope init/cut/LF | lines ≥95 |
| `vitest` unit | `apps/electron-sucursal/src/lib/print/__tests__/escposTemplates.arqueo.test.ts` (NEW) | 2: schema parses; `TIQUETE_TIPOS` exhaustiveness | lines ≥95 |
| `playwright` e2e | `apps/electron-sucursal/e2e/arqueo.spec.ts` (NEW) | 3 per REQ-OPS-156 | passes 100% |
| `tsc --noEmit` | workspace-wide | REQ-OPS-152..156 type-correct | zero errors |
| `eslint` | workspace-wide | REQ-OPS-152..156 lint-clean | zero errors |
| `@axe-core/playwright` | `apps/electron-sucursal/e2e/arqueo.spec.ts` (last scenario) | 1: WCAG 2.1 AA | zero violations |

## Risk acknowledgements

| Risk id (proposal §Risks) | Status | Residual |
|---|---|---|
| 1 — Field naming drift (silent 422) | RESOLVED | REQ-OPS-153 + REQ-OPS-156 scenario 3 lock the contract. E2E regression guard is the long-term backstop. |
| 2 — AC routed page vs current drawer UX | RESOLVED | REQ-OPS-152 wraps, preserving F3.3 F4 hotkey + sidebar anchor. Future F10.2/F10.3 may migrate to a tabbed layout — out of scope. |
| 3 — BR1 base configurable semantics | RESOLVED (no schema change) | If a future HU requires historical base at session open, file a separate backend ticket against `sesion.valor_inicial_efectivo`. |
| 4 — Justification asymmetry | RESOLVED (no code change) | REQ-OPS-154 codifies UI-gating; REQ-OPS-094 codifies backend-permitting. Both paths agree on the success outcome. |
| 5 — `'arqueo'` dispatcher missing | RESOLVED | REQ-OPS-155 adds the key + builder + dispatcher case + 3 unit tests. |
| 6 — `factura_pagos` immutability | RESOLVED (documentation + test isolation) | E2E uses `page.route()` mocks; renderer consumes GET only. |
| 7 — Hash chain forking | RESOLVED (relies on shipped verifier) | `job_sync_cloud.hash_chain_verifier_loop` (PR9b) catches forks; e2e is single-shot. |

## References

- Base spec: `openspec/specs/operations/spec.md` (REQ-OPS-091..097, F1.13 backend contract).
- Proposal: `openspec/changes/fase-10-1-arqueo-parcial/proposal.md`.
- Engram mirrors: `#1888` (proposal), `#1887` (SDD session preflight Fase 10).
- Architectural canon: `E:\easypunto_parkos\AGENTS.md` §1 (audit-first), §2 (bi-temporal), §3 (C/Q/U only — no DELETE).
