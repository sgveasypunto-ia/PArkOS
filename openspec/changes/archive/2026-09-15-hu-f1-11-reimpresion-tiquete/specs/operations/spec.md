# Delta Spec — HU-F1.11: Workflow reimpresión tiquete (crear + anular)

> **Change**: `hu-f1-11-reimpresion-tiquete`
> **Target spec**: `openspec/specs/operations/spec.md` (will append 7 new REQs on archive: REQ-OPS-075..080 + REQ-OPS-XR4)
> **Phase**: spec (sdd-spec)
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F1.11 (Fase-1 prerequisites — backend)
> **Inputs**: `openspec/changes/hu-f1-11-reimpresion-tiquete/proposal.md` (~480 LOC, 16 sections, 2026-09-15), Engram obs #1578 (explore) + #1579 (propose), `plan.md` lines 983-1006 + line 7342 (GAP-BE-04), `modelo_datos_er.mmd` lines 230-244 + 598-620 + 1150-1155, `migrations/0001_initial_schema.py` lines 893-910 + 1638-1692, `models/L_W/reimpresion_ticket.py` lines 29-90, `schemas/workflows.py` lines 50-132, `api/v1/workflows.py` lines 73-78 + 111-118, `repo/workflow.py` lines 66-72 + 110-237 + 240-348, `sync/catalog/entries/sync_entries_lw.py` lines 27-40, `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/specs/operations/spec.md` (precedent), `openspec/specs/operations/spec.md` (80 REQs canonical).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `340197e`) · **PR target**: `origin/dev`.
> **Note on DEC-TKT-01..06**: GAP-BE-04 fix is single-line; conditional siembra via pre-flight `DO $$`; `uuid_factura` optional.

---

## Purpose

HU-F1.11 closes the **operador-facing reimpresión tiquete workflow** on top of the already-shipped `prod.reimpresion_ticket` `[L-W]` chain by exposing two POST endpoints + one single-line permission fix + a conditional MIGRATION 0029 siembra. The deltas materialize the workflow contract: every transition is a NEW row, the chain IS the audit trail, and the resource must finally be reachable to operators with `reimprimir_ticket` permission.

The 7 new REQ-OPS-NNN (REQ-OPS-075..080 + REQ-OPS-XR4) extend the `operational` capability already consolidated in `openspec/specs/operations/spec.md` (last REQ-OPS-NNN vigente: **REQ-OPS-074 + XR1..XR3** after the merge of HU-F1.10 in commit `05bb7ac`). REQ-OPS-001..074 + XR1..XR3 remain unchanged.

---

## ADDED Requirements

### REQ-OPS-075 — POST endpoint INSERTs new `prod.reimpresion_ticket` row with `workflow_estado='autorizada'`

**Level**: SHALL. **Statement**: The branch MUST INSERT a new `prod.reimpresion_ticket` row with `workflow_estado='autorizada'`, `uuid_reimpresion_padre=NULL`, `uuid_ingreso=<ingreso.uuid>`, optional `uuid_factura`, `motivo` captured from request, `bi-temporal_estado='activo'`. The handler MUST resolve GAP-BE-04 by using permission name `reimprimir_ticket` (DEC-TKT-01), and MUST NOT use the typo'd `emitir_reimpresion` permission string.

**Rationale**: plan.md lines 989-991 mandate the create endpoint; the `reimprimir_ticket` permission is already seeded in `prod.permisos` (migration 0001 line 3292). GAP-BE-04 reconciliation (plan.md line 7342) is the precondition for the resource being reachable at all. The `[L-W]` WorkflowBase insert-only invariant keeps every create as a new chain root.

**Source**: `plan.md` lines 989-991 (acceptance criteria for crear); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 3292 (`reimprimir_ticket` permission seed); `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` line 74 (GAP-BE-04 site); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 66-72 (state machine); `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` lines 50-132 (`ReimpresionTicketCreate` / `ReimpresionTicketRead`); `backend/packages/parkos_core/src/parkos_core/models/L_W/reimpresion_ticket.py` lines 29-90.

#### Scenario 1: Happy path with `uuid_ingreso` only — INSERT `workflow_estado='autorizada'`, no `uuid_factura`

**Given** an operador with role granted `reimprimir_ticket` permission (NOT `emitir_reimpresion` per GAP-BE-04)
**And** an existing `prod.ingreso.uuid=:i` with `uuid_sucursal=:s`
**And** no existing `prod.reimpresion_ticket` row for `uuid_ingreso=:i`
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket` with body `{"motivo":"Cliente solicita reimpresión por deterioro del original", "uuid_ingreso":":i", "uuid_factura":null}`
**Then** the handler MUST INSERT a new `prod.reimpresion_ticket` row with `workflow_estado='autorizada'`, `uuid_reimpresion_padre=NULL`, `uuid_ingreso=:i`, `uuid_factura=NULL`, `motivo=<payload.motivo>`, `bi-temporal_estado='activo'`, `timestamp_evento=NOW()`.
**And** MUST return `201 Created` with body `ReimpresionTicketRead{uuid:<new.uuid>, workflow_estado:'autorizada', uuid_reimpresion_padre:null, ...}` and `Cache-Control: no-store`.

#### Scenario 2: Happy path with `uuid_factura` populated — optional FK accepted

**Given** an operador with `reimprimir_ticket` permission
**And** an existing `prod.ingreso.uuid=:i` AND an existing `prod.facturas.uuid=:f`
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket` with body `{"motivo":"...", "uuid_ingreso":":i", "uuid_factura":":f"}`
**Then** the handler MUST validate `prod.facturas.uuid=:f` exists (V1 SELECT).
**And** MUST INSERT a new `prod.reimpresion_ticket` row with `uuid_factura=:f` populated (DEC-TKT-04 OPTIONAL).
**And** MUST return `201 Created` with `ReimpresionTicketRead{uuid_factura:":f", workflow_estado:'autorizada', ...}`.

#### Scenario 3: GAP-BE-04 fix verified — `reimprimir_ticket` permission accepted, `emitir_reimpresion` rejected

**Given** the handler dependency at `api/v1/workflows.py:74` was changed from `emitir_reimpresion` to `reimprimir_ticket` (DEC-TKT-01)
**When** an operador with role granted `reimprimir_ticket` POSTs to the endpoint
**Then** the request MUST succeed (201 Created) and the prior 403 caused by GAP-BE-04 MUST be gone.
**And** conversely, an operador with role granted ONLY the legacy `emitir_reimpresion` (no `reimprimir_ticket`) MUST receive `403` — proving the typo'd permission is no longer in the dependency check.

#### Scenario 4: `422` on missing `uuid_ingreso` (Pydantic validation rejects before DB hit)

**Given** a request body that omits the required `uuid_ingreso` field
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket` with `{"motivo":"...texto suficientemente largo...", "uuid_factura":null}`
**Then** Pydantic v2 schema validation MUST reject the request before any handler body code runs.
**And** MUST return `422 Unprocessable Entity` with body `{"error":"missing_field", "field":"uuid_ingreso"}` and `Cache-Control: no-store`.
**And** NO `prod.reimpresion_ticket` row MUST be INSERTed.

#### Definition of Done for REQ-OPS-075

- Handler `_create_reimpresion_ticket` wired in new module `api/v1/workflows_reimpresion.py` with `POST /api/v1/workflows/reimpresion-ticket`.
- KD-3 issuer chain `_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` applied via FastAPI dependency.
- Handler calls `repo.workflow.append_transition(...)` with `parent_uuid=None, parent_fk_column="uuid_reimpresion_padre"`.
- GAP-BE-04 fix applied at `api/v1/workflows.py:74` (single-line; DEC-TKT-01).
- Unit tests `test_happy_path_uuid_ingreso_only` + `test_happy_path_uuid_factura_populated` + `test_gap_be_04_reimpresion_resource_unblocked` + `test_422_missing_uuid_ingreso` PASS.
- `Cache-Control: no-store` header verified on 201 / 422 / 500 responses.

---

### REQ-OPS-076 — GAP-BE-04 fix: permission name `emitir_reimpresion` → `reimprimir_ticket` (single-line)

**Level**: MUST. **Statement**: The handler dependency MUST use permission name `reimprimir_ticket` (NOT the typo `emitir_reimpresion` from GAP-BE-04). The fix is a single-line change at `api/v1/workflows.py:74`. This unblocks the entire `reimpresion-ticket` resource (currently returns 403 to all callers because no operador has the typo'd permission in `prod.permisos`).

**Rationale**: plan.md line 7342 mandates the reconciliation as GAP-BE-04 (highest blast radius — affects the entire `reimpresion-ticket` resource, not just the new POST endpoints). `reimprimir_ticket` is ALREADY seeded in `prod.permisos` (migration 0001 line 3292); no migration needed, no re-seed required. The existing `prod.permisos_usuario` grants already cover the canonical permission name.

**Source**: `plan.md` line 7342 (GAP-BE-04 reconciliation mandate); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 3292 (`reimprimir_ticket` permission seed); `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` line 74 (GAP-BE-04 site, current stale value `"emitir_reimpresion"`).

#### Scenario 1: Permission check uses correct name `reimprimir_ticket`

**Given** the handler dependency at `api/v1/workflows.py:74`
**When** the dependency module is loaded by the FastAPI router
**Then** the required permission string MUST equal `"reimprimir_ticket"` (NOT `"emitir_reimpresion"`).
**And** a code-level regression test MUST assert `permission_required == "reimprimir_ticket"`.

#### Scenario 2: Operator granted `reimprimir_ticket` succeeds

**Given** an operador role with the canonical permission `reimprimir_ticket` granted via `prod.permisos_usuario`
**When** the operador POSTs to `/api/v1/workflows/reimpresion-ticket`
**Then** the request MUST pass the dependency check and reach the handler body (201 Created on happy path).

#### Scenario 3: Operator granted only the typo'd `emitir_reimpresion` is rejected

**Given** an operador role with only the legacy typo'd permission `emitir_reimpresion` granted (and NOT `reimprimir_ticket`)
**When** the operador POSTs to `/api/v1/workflows/reimpresion-ticket`
**Then** the request MUST fail with `403 Forbidden` (the dependency check no longer recognizes `emitir_reimpresion`).
**And** the test MUST verify the rejection to prove the typo'd permission is no longer in the dependency check.

#### Definition of Done for REQ-OPS-076

- `api/v1/workflows.py:74` changed from `"emitir_reimpresion"` to `"reimprimir_ticket"`.
- No migration; no permission re-seed; no role grants re-issued.
- Integration test `tests/integration/test_workflows_router_wiring.py::test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion` PASSES.
- Integration test `tests/integration/test_workflows_router_wiring.py::test_anular_reimpresion_endpoint_requires_anular_reimpresion_permission` PASSES.

---

### REQ-OPS-077 — Anulación endpoint INSERTs NEW row with `workflow_estado='rechazada'` + `motivo_anulacion`

**Level**: SHALL. **Statement**: The branch MUST INSERT a NEW `prod.reimpresion_ticket` row with `workflow_estado='rechazada'`, `motivo_anulacion` captured from request, `uuid_reimpresion_padre=<tip.uuid>` (the current chain tip). The handler MUST use permission `anular_reimpresion` (separate from `reimprimir_ticket`, seeded in MIGRATION 0029 Op 2 and granted to roles in Op 3). The original chain tip row MUST NEVER be UPDATEd (DEC-TKT-03 + `[L-W]` insert-only invariant).

**Rationale**: plan.md line 993 explicitly flags the anulación as **"gap huérfano detectado"**. The `[L-W]` WorkflowBase pattern mirrors `anulaciones` / `alerta` / `envio_dian`: anulación is a NEW row that captures the audit trail of why a prior transición is being rejected. Closing this gap is the regulatory minimum for operator-correction flows (admin cancels a prior reimpresión that had a charging typo).

**Source**: `plan.md` line 993 (orphan anulación gap); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition`); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 240-348 (`read_chain_tip`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 1638-1692 (FK constraint on `uuid_reimpresion_padre`).

#### Scenario 1: Happy path anulación — INSERT NEW row with `workflow_estado='rechazada'`, `uuid_reimpresion_padre=<tip.uuid>`

**Given** an existing reimpresion_ticket chain with tip `<tip>` at `workflow_estado='autorizada' | 'ejecutada' | 'solicitada'`
**And** an operador with role granted `anular_reimpresion` permission
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket/{uuid}/anular` with body `{"motivo_anulacion":"Error operativo: reimprimir solicitada por error administrativo"}`
**Then** `repo.workflow.read_chain_tip(session, ReimpresionTicket, root_uuid=uuid, parent_fk_column="uuid_reimpresion_padre")` MUST return `<tip>`.
**And** the handler MUST INSERT a NEW `prod.reimpresion_ticket` row with `workflow_estado='rechazada'`, `uuid_reimpresion_padre=<tip.uuid>`, `motivo_anulacion=<payload.motivo_anulacion>`, `bi-temporal_estado='activo'`.
**And** the original `<tip>` row MUST remain unchanged (NEVER UPDATE on user-meaningful fields).
**And** MUST return `201 Created` with `ReimpresionTicketRead{uuid:<new.uuid>, workflow_estado:'rechazada', uuid_reimpresion_padre:"<tip.uuid>", motivo_anulacion:"...", ...}` and `Cache-Control: no-store`.

#### Scenario 2: Anulación blocked when chain tip already `rechazada` (terminal state)

**Given** an existing reimpresion_ticket chain with tip `<tip>` at `workflow_estado='rechazada'` (terminal — already anulada)
**And** an operador with `anular_reimpresion` permission
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket/{uuid}/anular` again
**Then** `read_chain_tip` MUST return `<tip>` with `workflow_estado='rechazada'`.
**And** the handler MUST return `409 Conflict` with body `{"error":"anulacion_no_permitida", "uuid_reimpresion":"<uuid>", "estado_actual":"rechazada"}` and `Cache-Control: no-store`.
**And** NO NEW `prod.reimpresion_ticket` row MUST be INSERTed (terminal state guard).

#### Scenario 3: Permission check — `anular_reimpresion` gate enforced

**Given** the handler dependency at the new module requires permission `anular_reimpresion`
**When** an operador role is granted `anular_reimpresion` via MIGRATION 0029 Op 3 + `prod.permisos_usuario`
**Then** the endpoint MUST accept the request (handler body reachable).
**And** an operador without `anular_reimpresion` MUST receive `403 Forbidden`.

#### Definition of Done for REQ-OPS-077

- Handler `_anular_reimpresion_ticket` wired in `api/v1/workflows_reimpresion.py` with `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular`.
- KD-3 issuer chain `_anular_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` applied via FastAPI dependency with `permission_required="anular_reimpresion"`.
- Handler calls `repo.workflow.append_transition(...)` with `parent_uuid=tip.uuid, parent_fk_column="uuid_reimpresion_padre"` and `workflow_estado='rechazada'`.
- Single-commit invariant preserved (KD-TKT-01 — exactly one `await session.commit()`).
- Unit tests `test_happy_path_anulacion` + `test_anulacion_blocked_when_already_rechazada` + `test_403_without_anular_reimpresion_permission` PASS.
- `Cache-Control: no-store` header verified on 201 / 409 / 500 responses.

---

### REQ-OPS-078 — Chain integrity via `uuid_reimpresion_padre` FK + `read_chain_tip` helper

**Level**: SHALL. **Statement**: The handler MUST use `repo/workflow.py::read_chain_tip` to find the current chain tip (latest row by `timestamp_evento DESC LIMIT 1`, with the REQ-X9 tie-break `(max(timestamp_evento), longest chain, lex(uuid))`). The NEW row's `uuid_reimpresion_padre` MUST reference the chain tip's `uuid`. The chain MUST be reconstructable by recursive SELECT on `uuid_reimpresion_padre`. The FK constraint on `prod.reimpresion_ticket.uuid_reimpresion_padre` (migration 0001 lines 1690-1692) MUST be enforced at the DB layer.

**Rationale**: plan.md línea 953 + the F1.5 PR5-016 precedent establish the chain IS the audit trail. FK enforces referential integrity at the DB layer; `read_chain_tip` encodes the canonical tie-break. Without this contract the anulación chain can fork unpredictably and produce orphans that block regulatory audits.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 240-348 (`read_chain_tip`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 1690-1692 (FK `fk_reimpresion_ticket_uuid_reimpresion_padre`); plan.md línea 953.

#### Scenario 1: `read_chain_tip` returns the latest row by `timestamp_evento DESC`

**Given** 3 `prod.reimpresion_ticket` rows in a chain: `:r1` (root, `uuid_reimpresion_padre=NULL`, `timestamp_evento='2026-09-15T10:00:00Z'`), `:r2` (`uuid_reimpresion_padre=:r1.uuid`, `timestamp_evento='2026-09-15T11:00:00Z'`), `:r3` (`uuid_reimpresion_padre=:r2.uuid`, `timestamp_evento='2026-09-15T12:00:00Z'`)
**When** the handler invokes `read_chain_tip(session, ReimpresionTicket, root_uuid=:r1.uuid, parent_fk_column="uuid_reimpresion_padre")`
**Then** the helper MUST return `:r3` (latest by `timestamp_evento DESC`, applying the REQ-X9 tie-break on equal timestamps).
**And** the returned object MUST expose `uuid_actual=:r3.uuid` AND `estado=:r3.workflow_estado`.

#### Scenario 2: Chain reconstruction via recursive CTE on `uuid_reimpresion_padre`

**Given** 5 `prod.reimpresion_ticket` rows `:e1`, `:e2`, `:e3`, `:e4`, `:e5` forming a chain (each row's `uuid_reimpresion_padre` = previous row's `uuid`, except `:e1` which is `NULL`)
**When** a recursive WITH query `WITH RECURSIVE chain AS (SELECT * FROM prod.reimpresion_ticket WHERE uuid=:e1.uuid AND uuid_reimpresion_padre IS NULL UNION ALL SELECT e.* FROM prod.reimpresion_ticket e JOIN chain c ON e.uuid_reimpresion_padre = c.uuid) SELECT uuid, uuid_reimpresion_padre, workflow_estado, timestamp_evento FROM chain ORDER BY timestamp_evento ASC` executes
**Then** the chain MUST be reconstructed in order: `:e1` (root, `uuid_reimpresion_padre=NULL`) → `:e2` → `:e3` → `:e4` → `:e5` (tip).
**And** each row's `workflow_estado` MUST be preserved.

#### Scenario 3: FK constraint enforces referential integrity on `uuid_reimpresion_padre`

**Given** a NEW `prod.reimpresion_ticket` row INSERT with `uuid_reimpresion_padre=<fake.uuid>` (UUID that does NOT exist in the table)
**When** the INSERT is executed
**Then** PostgreSQL MUST raise `psycopg2.errors.ForeignKeyViolation` (pgcode `23503`) at the DB layer.
**And** the handler MUST translate this exception to a typed 5xx (NEVER expose the pgcode in response body, headers, or info+ logs).

#### Definition of Done for REQ-OPS-078

- `repo/workflow.py::read_chain_tip` reused from F1.5 PR5-016 (no modification).
- Handler anulación uses `read_chain_tip(session, ReimpresionTicket, root_uuid=uuid_reimpresion, parent_fk_column="uuid_reimpresion_padre")`.
- Unit tests `test_read_chain_tip_returns_latest` + `test_chain_reconstruction_recursive_cte` + `test_fk_constraint_violation_raises_typed_exception` PASS.
- FK constraint verification via raw SQL `INSERT INTO prod.reimpresion_ticket (uuid, uuid_reimpresion_padre, ...) VALUES (gen_random_uuid(), gen_random_uuid(), ...)` raises `23503`.

---

### REQ-OPS-079 — CONDITIONAL MIGRATION 0029 siembra `costos_servicios.concepto='reimpresion'` if absent

**Level**: MUST. **Statement**: MIGRATION 0029 Op 1 MUST pre-flight `prod.costos_servicios WHERE concepto='reimpresion' AND vigente_hasta IS NULL AND estado='activo'`. If row absent (count == 0), INSERT a new row with `concepto='reimpresion', costo=0, tipo_calculo='fijo', vigente_desde=NOW(), vigente_hasta=NULL, estado='activo'`. If row present (count >= 1), no-op (idempotent). This is defensive: F1.11 ships regardless of whether siembra was already done by another HU.

**Rationale**: Mirrors F1.7's `impuestos.IVA` inline siembra (MIGRATION 0026 pattern + pending list). Idempotent on re-apply. Operator-configurable cost avoids hardcoded values — the cost is informational for F1.11 (the issuance flow is decoupled from cost charging; see DEC-TKT-04). The migration MUST ship even when siembra is already present because we cannot know in advance whether it exists at deployment time.

**Source**: `plan.md` lines 989-1006 (F1.11 mandate); `modelo_datos_er.mmd` lines 230-244 (`costos_servicios` [V]); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 297-309 (`costos_servicios` create_table).

#### Scenario 1: Siembra absent → INSERT

**Given** no vigente `prod.costos_servicios` row with `concepto='reimpresion'` (count == 0 from the pre-flight SELECT)
**When** MIGRATION 0029 Op 1 is applied
**Then** the `DO $$` block MUST INSERT a new `prod.costos_servicios` row with `uuid=gen_random_uuid(), concepto='reimpresion', costo=0, tipo_calculo='fijo', vigente_desde=NOW(), vigente_hasta=NULL, estado='activo', created_at=NOW(), created_by=NULL, sync_status='sincronizado', sync_attempts=0`.
**And** the `ON CONFLICT (concepto, vigente_desde) DO NOTHING` clause MUST prevent duplicate key violations if a concurrent TX inserts first.

#### Scenario 2: Siembra present → no-op (idempotent)

**Given** an existing vigente `prod.costos_servicios` row with `concepto='reimpresion'` (count >= 1 from the pre-flight SELECT, possibly inserted by a manual siembra or prior migration run)
**When** MIGRATION 0029 Op 1 is applied
**Then** the `DO $$` block MUST NOT INSERT a new row (the `IF siembra_count = 0` guard skips the INSERT branch).
**And** the existing row MUST remain unchanged (no UPDATE).
**And** the migration MUST be idempotent: a second application MUST NOT change the state.

#### Definition of Done for REQ-OPS-079

- MIGRATION 0029 Op 1 `DO $$` block with pre-flight `ASSERT prod.costos_servicios exists` + count check + conditional INSERT.
- MIGRATION 0029 Op 2 seeds `anular_reimpresion` permission (`INSERT INTO prod.permisos VALUES (..., 'anular_reimpresion', ...)` if NOT EXISTS).
- MIGRATION 0029 Op 3 grants `anular_reimpresion` to `operador` and `admin` roles via `prod.permisos_usuario` (idempotent via NOT EXISTS subquery).
- Integration test `tests/integration/test_migration_0029_idempotent.py::test_siembra_costos_servicios_reimpresion_pre_flight` PASSES (covers both absent and present cases).
- Integration test `tests/integration/test_migration_0029_idempotent.py::test_migration_0029_idempotent_upgrade_downgrade_upgrade` PASSES.

---

### REQ-OPS-080 — `uuid_factura` OPTIONAL (DEC-TKT-04) — nullable FK

**Level**: SHALL. **Statement**: The `prod.reimpresion_ticket.uuid_factura` column is OPTIONAL (nullable FK to `prod.facturas.uuid`). F1.11 does NOT require a `prod.facturas` row to exist for reimpresión. The full create-factura-then-reimprimir flow is deferred to HU-F8.3 (frontend Fase 8). If `uuid_factura` IS provided, the handler validates existence via V1 SELECT but does NOT snapshot the cost (the issuance flow is decoupled from cost charging per DEC-TKT-04).

**Rationale**: 170 LOC budget (plan.md line 1001) is tight for a full F1.9-style atomic factura creation + reimpresion_ticket INSERT in one TX. Splitting concerns keeps F1.11 focused on workflow chain + permission reconciliation. The admin-correction use case (anular a reimpresion that had a charging typo) is served by leaving `uuid_factura` nullable.

**Source**: `plan.md` line 1001 (170 LOC budget); `backend/packages/parkos_core/src/parkos_core/models/L_W/reimpresion_ticket.py` lines 29-90 (`uuid_factura` nullable column); `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` lines 50-132 (`ReimpresionTicketCreate` schema).

#### Scenario 1: `uuid_factura: null` accepted — reimpresión recorded without factura

**Given** a request body `{"motivo":"...", "uuid_ingreso":":i", "uuid_factura":null}`
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket`
**Then** Pydantic v2 schema validation MUST accept `uuid_factura: null` as valid input.
**And** the handler MUST skip the V1 SELECT-by-`uuid_factura` (the `if payload.uuid_factura is not None` guard).
**And** MUST INSERT a new `prod.reimpresion_ticket` row with `uuid_factura=NULL`.
**And** MUST return `201 Created` with `ReimpresionTicketRead{uuid_factura:null, workflow_estado:'autorizada', ...}`.

#### Scenario 2: `uuid_factura` populated accepted — FK validated, not snapshotted

**Given** an existing `prod.facturas.uuid=:f`
**When** the client POSTs `/api/v1/workflows/reimpresion-ticket` with body `{"motivo":"...", "uuid_ingreso":":i", "uuid_factura":":f"}`
**Then** the handler MUST execute the V1 SELECT `SELECT uuid FROM prod.facturas WHERE uuid=:f` and find the row.
**And** MUST INSERT a new `prod.reimpresion_ticket` row with `uuid_factura=:f` populated.
**And** MUST return `201 Created` with `ReimpresionTicketRead{uuid_factura:":f", workflow_estado:'autorizada', ...}`.
**And** the handler MUST NOT read or copy `prod.facturas.costo` to the reimpresion row (issuance flow decoupled from cost charging).

#### Definition of Done for REQ-OPS-080

- Pydantic v2 `ReimpresionTicketCreateEndpoint` schema with `uuid_factura: uuid_lib.UUID | None = None` and `extra='forbid'` (inherited from `_Base`).
- Handler `_create_reimpresion_ticket` Step 4 conditionally validates `uuid_factura` only if not None.
- Unit tests `test_uuid_factura_null_accepted` + `test_uuid_factura_populated_validates_fk` + `test_404_uuid_factura_not_found` PASS.
- Schema `ReimpresionTicketRead` exposes `uuid_factura: uuid_lib.UUID | None` (nullable).

---

### REQ-OPS-XR4 — Defense in depth: 5 layers + AST walk for `[L-W]` insert-only invariant (mirror F1.9 XR1..XR3 + F1.10 XR1..XR3)

**Level**: SHALL. **Statement**: F1.11 MUST apply the F1.10 defense-in-depth pattern: (1) KD-3 issuer chain `_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` + `_anular_reimpresion_issuer_dep`; (2) permission check (`reimprimir_ticket` for create + `anular_reimpresion` for anular — Layer 1 + 2 combined per F1.10 pattern, with GAP-BE-04 reconciled via DEC-TKT-01); (3) tenant scope post-V1 (KD-S2 analog from F1.7) — `operador-` issuer forbidden from cross-branch `uuid_sucursal != ctx.sucursal_uuid`; (4) FK chain integrity via `uuid_reimpresion_padre` (REQ-OPS-078); (5) handler 422/409 mapping (REQ-OPS-077 + REQ-OPS-075 Scenario 4). Additionally, an AST walk MUST enforce the `[L-W]` insert-only invariant: NO UPDATE statements on `prod.reimpresion_ticket` user-meaningful fields (`workflow_estado`, `motivo`, `motivo_anulacion`, `uuid_reimpresion_padre`) from the F1.11 handler bodies. Only `vigente_hasta` MAY be UPDATEd for bi-temporal versioning (WorkflowBase contract).

**Rationale**: 4NF compliance (state lives on the chain, not duplicated on the original row). Audit trail completeness (every transition is a row with `created_at`, `created_by`, `timestamp_evento`). Defense in depth against accidental UPDATE in future HUs that touch the reimpresion handler.

**Source**: `tests/static/test_no_raw_dml_on_lw_tables.py` (F1.5 PR5-016 precedent); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition`); F1.10 REQ-OPS-XR1..XR3 mirror.

#### Scenario 1: AST walk — no UPDATE on user-meaningful fields

**Given** the source files `api/v1/workflows_reimpresion.py` containing `create_reimpresion_ticket` and `anular_reimpresion_ticket`
**When** `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` runs
**Then** the AST walk MUST assert that no `UPDATE prod.reimpresion_ticket ...` statement or `update(ReimpresionTicket)` SQLAlchemy core call appears in either handler body.
**And** MUST assert that no UPDATE on `workflow_estado`, `motivo`, `motivo_anulacion`, `uuid_reimpresion_padre`, `uuid_ingreso`, `uuid_factura` appears.
**And** MUST assert that exactly one `INSERT INTO prod.reimpresion_ticket` (or equivalent `repo.workflow.append_transition(...)` helper call) appears per handler.
**And** MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(n.value.func, 'attr', '') == 'commit']) == 1` per handler (KD-TKT-01 single-commit invariant).

#### Scenario 2: `vigente_hasta` MAY be UPDATEd (bi-temporal versioning)

**Given** the bi-temporal WorkflowBase pattern from F1.5 PR5-016
**When** the WorkflowBase closes a version (sets `vigente_hasta=NOW()` for the previous active row)
**Then** this UPDATE MUST be allowed (the ONLY UPDATE allowed by WorkflowBase on the L-W tables).
**And** the AST walk MUST permit `update(...).where(...).values(vigente_hasta=...)` patterns originating from the `WorkflowBase` superclass.

#### Definition of Done for REQ-OPS-XR4

- AST walk `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` PASSES for both `create_reimpresion_ticket` and `anular_reimpresion_ticket`.
- KD-TKT-01 single-commit invariant verified via `tests/static/test_workflow_handler_single_commit.py` (separate AST walk per F1.10 pattern).
- 5-layer defense verified by integration tests covering each layer independently.

---

## Cross-Cutting Requirements

The following XR requirements reaffirm F1.10's XR1..XR3 (issuer chain, tenant scope, idempotency, cache-control, AST walks) and the new XR4 specific to F1.11:

- **REQ-OPS-XR1 (mirror F1.9 + F1.10)** — Defense in depth: 5 layers. Layer (a) KD-3 issuer chain `requires_issuer("operador-", "admin-")`; Layer (b) permission check `reimprimir_ticket` + `anular_reimpresion` (GAP-BE-04 reconciled per DEC-TKT-01); Layer (c) tenant scope post-V1 — `operador-` issuer forbidden from cross-branch `uuid_sucursal != ctx.sucursal_uuid` (KD-S2 analog from F1.7); Layer (d) FK chain integrity via `uuid_reimpresion_padre` (REQ-OPS-078); Layer (e) handler 422/409 mapping. Each layer independently tested; failure of any one layer MUST be contained by the other 4.

- **REQ-OPS-XR2 (mirror F1.9 + F1.10)** — `Cache-Control: no-store` header on all responses from `/api/v1/workflows/reimpresion-ticket/**` endpoints (201, 404, 409, 422, 5xx).

- **REQ-OPS-XR3 (mirror F1.9 + F1.10)** — KD-TKT-01 single `await session.commit()` invariant per handler body. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements MUST NOT appear. AST walks enforce the invariant for both `create_reimpresion_ticket` and `anular_reimpresion_ticket`.

- **REQ-OPS-XR4 (NEW for F1.11)** — Insert-only invariant AST walk on `[L-W]` reimpresion_ticket. NO UPDATE on user-meaningful fields from the F1.11 handlers. Only `vigente_hasta` MAY be UPDATEd by WorkflowBase for bi-temporal versioning (WorkflowBase contract).

---

## Definition of Done (entire HU-F1.11)

- [ ] `api/v1/workflows.py:74` changed from `"emitir_reimpresion"` to `"reimprimir_ticket"` (DEC-TKT-01 / GAP-BE-04).
- [ ] New module `api/v1/workflows_reimpresion.py` mounted with 2 handlers (`POST /api/v1/workflows/reimpresion-ticket` + `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular`).
- [ ] MIGRATION 0029 applied: Op 1 conditional siembra `costos_servicios.concepto='reimpresion'`, Op 2 seed `anular_reimpresion` permission, Op 3 grants `anular_reimpresion` to operador + admin roles.
- [ ] All 6 new REQ-OPS-075..080 implemented + verified.
- [ ] REQ-OPS-XR4 insert-only AST walk PASSES.
- [ ] ~14 tests across 5 test files + 1 AST walk PASS:
  - `tests/unit/test_reimpresion_ticket_schemas.py` (3 tests)
  - `tests/unit/test_reimpresion_ticket_create_handler.py` (4 tests)
  - `tests/unit/test_reimpresion_ticket_anular_handler.py` (3 tests)
  - `tests/integration/test_workflows_router_wiring.py` (2 tests — GAP-BE-04 regression + anular permission gate)
  - `tests/integration/test_migration_0029_idempotent.py` (2 tests)
  - `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` (1 AST walk)
- [ ] `Cache-Control: no-store` verified on 201 / 404 / 409 / 422 / 5xx responses.
- [ ] KD-TKT-01 single-commit invariant verified per handler via AST walk.
- [ ] Tenant scope post-V1 verified (operador- cross-branch → 403 `tenant_scope_violation`).
- [ ] `Idempotency-Key` HTTP header supported (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10).
- [ ] No AI attribution in commits (no `Co-authored-by:`, no AI trailers).

---

## References

- `openspec/changes/hu-f1-11-reimpresion-tiquete/proposal.md` (~480 LOC, 16 sections, DEC-TKT-01..06, KD-TKT-01..02, 7 REQ-OPS-075..080 placeholders + XR4, MIGRATION 0029 plan, ~14 tests + 1 AST walk, 5-layer defense)
- `openspec/changes/archive/2026-09-14-hu-f1-10-numeracion-fe-dian-reintento/specs/operations/spec.md` (precedent for F1.10 spec structure with 11 REQ-OPS-064..074 + XR1..XR3)
- `openspec/specs/operations/spec.md` (80 REQs REQ-OPS-001..074 + XR1..XR3 merged post-F1.10 — target for REQ-OPS-075..080 + XR4 merge on archive)
- `plan.md` lines 983-1006 (HU-F1.11 definition, 3 atomic tasks T1..T3, 170 LOC budget)
- `plan.md` line 989 (acceptance criteria for crear)
- `plan.md` line 991 (acceptance criteria for anular)
- `plan.md` line 993 (gap huérfano anulación)
- `plan.md` line 1001 (170 LOC budget)
- `plan.md` line 7342 (GAP-BE-04 permission reconciliation mandate)
- `modelo_datos_er.mmd` lines 230-244 (`costos_servicios` [V])
- `modelo_datos_er.mmd` lines 598-620 (`reimpresion_ticket` [L-W])
- `modelo_datos_er.mmd` lines 1150-1155 (FK relationships)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 297-309 (`costos_servicios` create_table)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 893-910 (`reimpresion_ticket` create_table)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 1638-1692 (FKs including `fk_reimpresion_ticket_uuid_reimpresion_padre` at 1690-1692)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 2379-2390, 2660-2672, 2873-2880 (triggers: audit, version, sync enqueue)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 3292 (`reimprimir_ticket` permission seed)
- `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py` lines 162, 182
- `backend/packages/parkos_core/migrations/versions/0028_one_fe_per_factura_and_chain_index_and_sync_flip.py` (current head)
- `backend/packages/parkos_core/src/parkos_core/models/L_W/reimpresion_ticket.py` lines 29-90
- `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` lines 50-132 (`ReimpresionTicketCreate` / `ReimpresionTicketRead`)
- `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` lines 73-78 (GAP-BE-04 site) + 111-118 (mount)
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 66-72 (state machine for `reimpresion_ticket`)
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 110-237 (`append_transition`)
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 240-348 (`read_chain_tip`)
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 27-40 (sync catalog entry for `reimpresion_ticket`)
- Engram observation #1578 (F1.11 exploration, `sdd/hu-f1-11-reimpresion-tiquete/explore`)
- Engram observation #1579 (F1.11 proposal, `sdd/hu-f1-11-reimpresion-tiquete/propose`)
- `tests/static/test_no_raw_dml_on_lw_tables.py` (F1.5 PR5-016 precedent for AST walks)
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/specs/operations/spec.md` (KD-3 issuer + 12-step handler + KD-FACT-01 single-commit precedent)
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/specs/operations/spec.md` (KD-S2 tenant scope precedent)

---

**End of delta spec — HU-F1.11.**