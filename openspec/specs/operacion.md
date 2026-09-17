# Spec: Operacion Ingreso (Fase 6.1 — CU-01 + CU-15E)

> **Change**: `fase-6-1-flujo-ingreso`
> **Domain**: `operacion-ingreso` (new capability)
> **Phase**: spec (sdd-spec)
> **Inputs read**: `proposal.md` §Capabilities §Approach §Risks; `plan.md` lines 1496-1604 (F6.1 + sequence mermaid), 412-492 (DEC-SUC-* + A-04); `modelo_datos_er.mmd` `ingreso` table (lines 577-596); `apps/electron-sucursal/src/lib/validation/placa.ts` (F4.1 strict detector); `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (F4.1 SWR hook); `apps/electron-sucursal/src/lib/print/escposBuilder.ts` (F5.2 typed); `openspec/specs/impresion.md` (F5.1+F5.2 contract); `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (F1.6 + F1.5 — verified endpoints present, see Open question below); `openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/{proposal,tasks}.md` (F1.6 server-side validation chain).

## ADDED Requirements

### Requirement: Plate Input Auto-focus + Normalization

The system SHALL normalize the typed plate to MAYÚSCULAS (trim + uppercase + strip whitespace, per F4.1 normalization), SHALL auto-focus the input on mount, and SHALL submit on Enter.

#### Scenario: Plate normalized to uppercase + auto-focused

- GIVEN the operator is on `Principal.tsx` and no modal is open
- WHEN the screen first renders
- THEN the plate input MUST receive focus automatically
- AND when the operator types `abc 12d` the displayed value MUST be `ABC12D`.

#### Scenario: Submit by Enter key

- GIVEN the input has a valid-looking value (`REGEX_AUTO\|REGEX_MOTO` matches)
- WHEN the operator presses `Enter`
- THEN the form MUST submit without requiring a button click.

### Requirement: Active-Ingreso Check (DEC-SUC-22, BR3, plan.md line 1507)

The system SHALL query for an existing open `ingreso` for the typed plate at the current branch. If one exists, the system SHALL redirect transparently to `SalidaFlow` (Fase 7 stub URL) — never display a double-entry error.

#### Scenario: Plate has open ingreso — transparent redirect

- GIVEN the typed plate `ABC123`
- WHEN the active-check query returns ≥1 ingreso with derived state `abierto`
- THEN the UI MUST redirect to `SalidaFlow` (Fase 7 stub URL)
- AND no error toast MUST be shown to the operator (transparent redirect per plan.md error table line 1530).

#### Scenario: Plate has no open ingreso — proceed

- GIVEN the typed plate `ABC123`
- WHEN the active-check query returns 0 items
- THEN the UI MUST proceed to the confirmar-ingreso step.

### Requirement: Server-Bounded Tipo Entrada Banner (DEC-SUC-21, plan.md line 1508)

The system MUST derive `tipo_entrada` (`MENSUALIDAD \| ROTACION`) from the server response (`ingreso.uuid_subscripcion_cliente IS NOT NULL`) and SHALL never persist the value client-side.

#### Scenario: Mensualidad active — banner shows client name

- GIVEN the `POST /operacion/ingresos` response contains `tipo_entrada === "MENSUALIDAD"` and `uuid_subscripcion_cliente` non-null
- WHEN the success view is shown
- THEN a banner MUST read "Mensualidad activa" with the client name resolved via a follow-up SWR fetch of the subscription.

#### Scenario: Rotación — banner shows default label

- GIVEN the response has `tipo_entrada === "ROTACION"`
- WHEN the success view is shown
- THEN a banner MUST read "Rotación".

### Requirement: Forced-Ingreso Modal with motivo ≥10 chars (A-04, KD-FORZADO-01)

The system MUST show `ForzarIngresoModal` when `POST /operacion/ingresos` returns `422 motivo_forzado_requerido`. The modal MUST validate the motivo with Zod `min(10)` and prepend `[FORZADO: <motivo>]` to `observaciones` on retry.

#### Scenario: Cupo agotado — modal demands motivo

- GIVEN `cupo_maximo === activos` (server returns `motivo_forzado_requerido`)
- WHEN the modal opens
- THEN the operator MUST enter a motivo with ≥10 characters before the confirm button enables
- AND on confirm the retry POST MUST set `observaciones: "[FORZADO: <motivo>]"` and `forzado: true`.

#### Scenario: motivo <10 chars — submit blocked inline

- GIVEN the operator has typed 5 characters in the motivo textarea
- WHEN the operator clicks confirm
- THEN the modal MUST show inline error "El motivo debe tener al menos 10 caracteres"
- AND the POST MUST NOT fire.

### Requirement: Auto-Print Tiquete de Entrada on 200 (DEC-SUC-27, plan.md line 1509)

On `201` from `POST /operacion/ingresos`, the system MUST call `bridge.imprimir(escposBuilder.build('entrada', payload))` automatically. A "Imprimir" button MUST remain available in `TiqueteModal` for free reprint (E3 exemption, distinct from Fase 8 reimpresion_ticket workflow).

#### Scenario: Successful 201 — tiquete prints automatically

- GIVEN a successful `201` with `uuid_ingreso` in the response body
- WHEN the success handler runs
- THEN `bridge.imprimir` MUST be called once with the F5.2 builder output
- AND `TiqueteModal` MUST open with `role="dialog"`.

#### Scenario: Printer offline — ingreso persists, banner shows

- GIVEN the auto-print returns `printer_offline` from IPC
- WHEN the IPC promise rejects
- THEN a banner MUST read "Impresora no disponible, reintentando…"
- AND the ingreso MUST remain persisted (DB INSERT is the source of truth)
- AND the F5.1 retry queue MUST drain when the printer reconnects.

### Requirement: Idempotent POST via Idempotency-Key (DEC-SUC-04)

The `POST /operacion/ingresos` request MUST include the header `Idempotency-Key: <SHA-256(method + path + body)>` so re-submits (network retry, operator double-press) return the same response.

#### Scenario: Operator double-press — second POST returns the same 201

- GIVEN the operator submits `placa=ABC123`
- WHEN the operator presses the confirm button twice within 500ms
- THEN both POSTs MUST carry the same `Idempotency-Key` header
- AND the server MUST return the same `uuid_ingreso` for both (F1.6 Idempotency-Key middleware PR2).

#### Scenario: Body mutation — Idempotency-Key differs

- GIVEN the operator edits `observaciones` between two submissions
- WHEN the second submit fires
- THEN the second `Idempotency-Key` MUST differ (different SHA-256 hash of the body)
- AND the server MUST treat it as a new request (correct: the operator actually changed something).

## Error Catalog

| Code | Source | UI Action |
|------|--------|-----------|
| `placa_formato_invalido` | client Zod / backend `422` | Inline error "Placa no coincide con ningún formato conocido (Auto: ABC123, Moto: ABC12D)", input stays open. |
| `motivo_forzado_requerido` | backend `422` | Open `ForzarIngresoModal` with motivo field focused. |
| `motivo_forzado_insuficiente` | backend `422` | Inline error in modal: motivo needs ≥10 chars. |
| `forzado_contradiccion` | backend `422` | Banner error; close modal and re-open with corrected prefijo. |
| `cupo_no_configurado` | backend `422` | Banner error suggesting admin action. |
| `tarifa_vigente_no_encontrada` | backend `422` | Banner error suggesting admin action. |
| `subscripcion_inactiva_o_vencida` | backend `422` | Banner error; F7 Salida flow handles the walk-in audit. |
| `ingreso_activo_existente` (409) | backend | **NOT shown as error** — transparent redirect to `SalidaFlow`. |
| `printer_offline` | F5.1 IPC | Banner "Impresora no disponible, reintentando…"; ingreso persisted. |
| `tenant_scope_violation` (403) | backend | parkosFetch handles session redirect to login. |
| `network_error` | parkosFetch | parkosFetch retry on 5xx (3 attempts, backoff 300/600/1200ms); on final failure show "Sin conexión" toast. |

## Open question / Blocker

**Missing backend endpoint**: the literal endpoint `GET /operacion/ingresos?placa=X&activo=true` does NOT exist in `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py`. Verified state (F1.6 archive):

| Endpoint | Status |
|----------|--------|
| `POST /operacion/ingresos` | ✅ Exists (F1.6 archive, line 116-305) — full validation chain + V9 `tipo_entrada` derivation. |
| `GET /operacion/ingresos` | ✅ Exists (line 603-624) — list with `uuid_sucursal` + `placa` filters, **NO `activo` query param**. |
| `GET /operacion/ingresos/{uuid}/estado` | ✅ Exists (line 556-600) — derived state (`abierto` / `cerrado` / `anulada`). |
| `GET /operacion/ingresos/{uuid}` | ✅ Exists (line 539-553). |
| `GET /operacion/ocupacion` | ✅ Exists (line 812-899). |
| `GET /operacion/ingresos?placa=X&activo=true` | ❌ **Missing** — exact endpoint signature requested by plan.md line 1518 and F6.1 proposal does not exist. |

**Resolution paths** (orchestrator decision required):

1. **(Recommended — zero backend change)** F6.1 uses two-call composition: `GET /operacion/ingresos?placa=X` → for each result call `GET /operacion/ingresos/{uuid}/estado` → filter to `estado === "abierto"` → redirect on ≥1 match. Latency: 1+ round-trips (typically 1 for occasional, 2+ for monthly subs with N placas). N+1 acceptable for MVP given placa lookup is typically 0-3 rows.
2. **(Companion backend PR)** Add `activo: bool \| None = None` query param to `GET /operacion/ingresos` (~10 LOC in `api/v1/operacion.py`, ~5 LOC test). Backend filter: `JOIN NOT EXISTS salidas + NOT EXISTS anulaciones` OR reuse `repo.ingreso.py::existe_ingreso_activo(placa)` predicate in a WHERE clause. Cleanest from a UI perspective; smallest backend change.

**Decision**: defer to design phase (Tasks §T0 will codify the choice). Per the prompt's instruction: do not invent or stub the missing endpoint.