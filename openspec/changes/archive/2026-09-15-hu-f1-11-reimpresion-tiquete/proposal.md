# Proposal: HU-F1.11 — Workflow reimpresión tiquete (crear + anular) + GAP-BE-04 cierre

> **Change**: `hu-f1-11-reimpresion-tiquete` · **Folder**: `openspec/changes/hu-f1-11-reimpresion-tiquete/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.11 (Fase-1 prerequisites — backend)
> **Inputs**: `plan.md` lines 983-1006 (170 LOC, 3 atomic tasks T1..T3), Engram observation #1578 (F1.11 exploration, 16 sections, ~770 LOC), `modelo_datos_er.mmd` lines 230-244 (`costos_servicios` [V]), 598-620 (`reimpresion_ticket` [L-W]), 1150-1155 (FK relationships), `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 297-309 (`costos_servicios`), 893-910 (`reimpresion_ticket`), 1638-1692 (FKs), 2379-2390, 2660-2672, 2873-2880 (triggers), 3292 (`reimprimir_ticket` permission seed), `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py` lines 162, 182, `backend/packages/parkos_core/migrations/versions/0028_one_fe_per_factura_and_chain_index_and_sync_flip.py` (current head), `backend/packages/parkos_core/src/parkos_core/models/L_W/reimpresion_ticket.py` lines 29-90, `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` lines 54-132, `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` lines 73-78 (GAP-BE-04), 111-118, `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 66-72, 110-237, 240-348, `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 27-40, `openspec/specs/operations/spec.md` lines 2517-3076 (REQ-OPS-064..074 + XR1..XR3 from F1.10), `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-proposal.md` (precedent).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `340197e`) · **PR target**: `origin/dev`.
> **Language note**: artifact authored in English per the project's `Language Domain Contract` (default for technical SDD artifacts). DEC-TKT-NN and KD-TKT-NN identifiers follow the established F1.x naming pattern.

---

## 1. Title & Goal

**Title**: "Workflow reimpresión tiquete (crear + anular) + GAP-BE-04 cierre"

**Goal**: Deliver two endpoints + one single-line permission fix + conditional MIGRATION 0029 siembra on top of the already-shipped `prod.reimpresion_ticket` `[L-W]` chain:

1. **`POST /api/v1/workflows/reimpresion-ticket`** — Given an `ingreso` UUID and a `motivo` of ≥10 characters, INSERTs a new `prod.reimpresion_ticket` row with `estado='autorizada'` (after the canonical seed INSERT marking the transition through `repo.workflow.append_transition`) and `uuid_reimpresion_padre=NULL`. Optional `uuid_factura` may be referenced when an existing `prod.factura` is associated (DEC-TKT-04).
2. **`POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular`** — Closes the **orphan anulación gap** by INSERTing a NEW `prod.reimpresion_ticket` row with `uuid_reimpresion_padre` pointing at the chain tip and `estado='rechazada'` (**NEVER UPDATE** the original — `[L-W]` insert-only invariant). Carries `motivo_anulacion`.
3. **GAP-BE-04 single-line fix** — `api/v1/workflows.py:74` permission name `emitir_reimpresion` → `reimprimir_ticket`. Currently returns 403 for the entire `reimpresion-ticket` resource (highest blast radius in the codebase).
4. **MIGRATION 0029 (CONDITIONAL)** — Pre-flight `DO $$` seeds `prod.costos_servicios.concepto='reimpresion'` if absent (idempotent on re-apply; no-op if already seeded manually by another HU).

**Defense in depth (5 layers)**: (a) KD-3 issuer chain (`requires_issuer("operador-", "admin-")`), (b) permission check `reimprimir_ticket` (create) + `anular_reimpresion` (anular) — Layer 1 + 2 combined per F1.10 pattern, (c) tenant scope post-V1 (KD-S2 analog from F1.7), (d) WorkflowBase insert-only invariant + AST walk `tests/static/test_no_raw_dml_on_lw_tables.py` (already in place per F1.5 PR5-016), (e) handler 422 mapping for `motivo_muy_corto` and 409 for `reimpresion_already_pending` + `anulacion_no_permitida`.

**Scope**: ~170 LOC production (matches plan.md line 1001) + ~280 LOC tests across 5 files = ~450 LOC cumulative.

---

## 2. Context & Background

- **F1.10 closed** (2026-09-14, 16 commits `a9a8f47..05bb7ac`). Migration head = `0028_one_fe_per_factura_and_chain_index_and_sync_flip`. F1.11 next migration is `0029`. The 11 REQs REQ-OPS-064..074 + XR1..XR3 are merged into `openspec/specs/operations/spec.md`.
- **`prod.reimpresion_ticket` already exists** (`[L-W]`, migration 0001 lines 893-910). `WorkflowBase` (insert-only per transition) + self-FK `uuid_reimpresion_padre` (lines 1690-1692 — referenced as `uuid_reimpresion_padre` in the ORM model; the migration uses the same name). Audit trigger `reimpresion_ticket_audit_columns`, version trigger `reimpresion_ticket_set_vigente_inicial`, sync enqueue trigger `reimpresion_ticket_enqueue_sync` per migration 0001 lines 2660-2672 + 2873-2880.
- **`prod.costos_servicios` already exists** (`[V]`, migration 0001 lines 297-309). Composite UK `costos_servicios_uk01 (concepto, vigente_desde)` enforces "one vigente row per concept" via the bi-temporal VersionedBase pattern.
- **`ReimpresionTicket` ORM model exists** (`models/L_W/reimpresion_ticket.py` lines 29-90). Carries all 11 columns + re-declares `vigente_desde`/`vigente_hasta`/`estado`.
- **`ReimpresionTicketCreate`/`Read`/`Update`/`Filter`/`ReadList` Pydantic schemas exist** (`schemas/workflows.py` lines 54-132). `motivo` is `str` with `max_length=1000` (no min_length — the ≥10 character gate is enforced at the Pydantic v2 strict `StringConstraints` schema in §9 below, per plan.md line 989).
- **`repo.workflow.append_transition` exists** (F1.5 PR5-016, `repo/workflow.py` lines 110-237). Validates the transition against `STATE_MACHINES["reimpresion_ticket"]` (lines 66-72): `solicitada → autorizada → ejecutada | rechazada`. Server-sets `created_at`, `created_by`. Optionally co-INSERTs a `log_transaccional` row.
- **`repo.workflow.read_chain_tip` exists** (F1.5 PR5-016, `repo/workflow.py` lines 240-348). Walks the `uuid_reimpresion_padre` self-FK and returns the chain tip per the REQ-X9 tie-break.
- **Sync catalog entry already configured** (`sync/catalog/entries/sync_entries_lw.py` lines 27-40). `direction = "branch_to_cloud"`, `sync_strategy = "append"`, `apply_strategy = "append_transition"`, `parent_fk_column = "uuid_reimpresion_padre"`, `depends_on = ("sucursal", "ingreso", "usuarios", "costos_servicios", "facturas")`.
- **GAP-BE-04 reconciliation** (plan.md line 7342): the `ReimpresionTicket` mount in `api/v1/workflows.py` line 74 currently uses permission `"emitir_reimpresion"`, but `prod.permisos` seeded at `0001_initial_schema.py` line 3292 is `"reimprimir_ticket"`. The router returns 403 forever (the permission check at `make_router` rejects any actor). F1.11 must reconcile this as part of the implementation (single-line fix in `workflows.py:74`).
- **Siembra `costos_servicios.concepto='reimpresion'`** is listed in the F1.11 pending section as a blocker — MUST be verified before F1.11 implementation; if absent, MIGRATION 0029 Op 1 inlines the siembra (mirror of F1.7's `impuestos.IVA` siembra via MIGRATION 0026).
- **Workflow state machine** (`repo/workflow.py` lines 66-72):
  ```
  reimpresion_ticket:
    solicitada   → [autorizada, rechazada]
    autorizada   → [ejecutada, rechazada]
    ejecutada    → []   (terminal)
    rechazada    → []   (terminal)
  ```
  The initial INSERT carries `estado='autorizada'` (auto-approved workflow; manual `solicitada → autorizada` step is F2.x deferred); anulación INSERTs `estado='rechazada'` with `motivo_anulacion` populated.
- **No REQ-OPS exists for reimpresion** in `openspec/specs/operations/spec.md` (verified). F1.11 introduces REQ-OPS-075..080 (+ XR4 defense in depth mirror of F1.10's XR1..XR3).

### 2.1 Critical Architectural Conflict — GAP-BE-04 permission mismatch (RESOLVED in §3)

The sdd-explore phase flags R1 MEDIUM — a real architectural fork:

- **`prod.permisos.permiso` seeded** (migration 0001 line 3292): `reimprimir_ticket`.
- **`api/v1/workflows.py` line 74** uses: `"emitir_reimpresion"` (WRONG).
- **plan.md line 7342** mandates the reconciliation as GAP-BE-04.

The `emitir_reimpresion` value is a legacy alias that survived PR6 T-PR6-10. The actual permission seeded in `prod.permisos` has been `reimprimir_ticket` since the initial schema migration. Without the fix the entire `reimpresion-ticket` resource returns 403 to all callers (operators with `reimprimir_ticket` permission are rejected because the router checks `emitir_reimpresion`, which no row in `prod.permisos` carries).

---

## 3. Architectural Conflict Resolution — DEC-TKT-01

This section is **mandatory** for the proposal. It documents R1 from §7 and records the resolution.

### 3.1 The conflict (R1 MEDIUM)

Two sources disagree about which permission guards `prod.reimpresion_ticket` writes:

| Source | Statement | Authority weight |
|---|---|---|
| `plan.md` line 7342 | `emitir_reimpresion` → `reimprimir_ticket` (reconcile) | **CANONICAL** (per user mandate "siempre remitete al plan.md") |
| `0001_initial_schema.py` line 3292 | `INSERT INTO prod.permisos VALUES (..., 'reimprimir_ticket', ...)` | Real seeded permission |
| `api/v1/workflows.py` line 74 | `"emitir_reimpresion"` (WRONG) | Stale code from PR6 |

### 3.2 The resolution

**Resolution path** (mandated by plan.md + F1.11):

1. **Single-line fix** in `api/v1/workflows.py:74`:
   ```python
   "reimpresion-ticket": ("operador-,admin-", "reimprimir_ticket"),  # was "emitir_reimpresion"
   ```
2. **No migration needed** — `reimprimir_ticket` is ALREADY seeded in `prod.permisos` (migration 0001 line 3292).
3. **No permission grants** needed — the permission is already available; existing role assignments use it via `prod.permisos_usuario`.

### 3.3 Why this matters

- **The endpoint will return 403 forever** if the permission mismatch is not fixed. An operator with `reimprimir_ticket` permission will be rejected because the router checks `emitir_reimpresion`.
- **Highest blast radius**: affects the entire `reimpresion-ticket` resource, not just the new POST endpoints. The existing `GET /workflows/reimpresion-ticket` would also return 403 to any actor (the mount's permission check applies to all operations).
- **Defense-in-depth Layer 1**: KD-3 issuer chain + permission check at `make_router` requires this to be fixed BEFORE F1.11 endpoints ship.

---

## 4. Endpoints

Two endpoints. Both mounted under `/api/v1/workflows/reimpresion-ticket` (hyphenated, F1.x convention).

### 4.1 `POST /api/v1/workflows/reimpresion-ticket` (HU-F1.11-T1)

- **Purpose**: INSERT a NEW `prod.reimpresion_ticket` row with `estado='autorizada'`, `uuid_reimpresion_padre=NULL`. Server resolves chain tip + applies issuance date.
- **Issuer dep**: `_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` (F1.10 pattern verbatim).
- **Permission**: `reimprimir_ticket` (after DEC-TKT-01 reconciliation).
- **Request body** (`ReimpresionTicketCreateEndpoint`, §9.1): `{motivo: str (≥10 chars, ≤500), uuid_ingreso: UUID, uuid_factura: UUID | None}`. `extra='forbid'` blocks client smuggling of `uuid_reimpresion_padre`, `estado`, `costo_aplicado`, `uuid_costo_servicio`, `timestamp_evento`.
- **Response (201)**: `ReimpresionTicketRead` with `estado='autorizada'`, `uuid_reimpresion_padre=NULL`, `timestamp_evento=now()`.
- **Status codes**:
  - `201 Created` — happy path
  - `400 motivo_muy_corto` — Pydantic `min_length=10` rejects before DB hit
  - `403 GAP-BE-04` (legacied as `emitir_reimpresion_not_found` if not yet reconciled) — pre-§3 fix state
  - `404 ingreso_no_encontrado` — V1
  - `403 tenant_scope_violation` — operador- with cross-branch (post-V1)
  - `409 reimpresion_already_pending` — chain-tip guard (V2: a recent `autorizada`/`ejecutada` row exists for the same `uuid_ingreso` within the cool-off window; DEC-TKT-02)
- **Headers**: `Cache-Control: no-store`.
- **Idempotency**: `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10).

### 4.2 `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` (HU-F1.11-T2)

- **Purpose**: INSERT a NEW `prod.reimpresion_ticket` row with `uuid_reimpresion_padre = <uuid>.uuid_reimpresion_padre_chain_tip` (or `<uuid>` directly if it IS the chain tip) and `estado='rechazada'`. **NEVER UPDATE** the original — `[L-W]` insert-only invariant. Closes the **orphan anulación gap** (plan.md line 993).
- **Issuer dep**: same as 4.1.
- **Permission**: `anular_reimpresion` (new permission seeded in MIGRATION 0029 Op 2; mirror of `anular_ingreso_salida`).
- **Request body** (`ReimpresionTicketAnular`, §9.1): `{motivo_anulacion: str (≥10 chars, ≤500)}`.
- **Response (201)**: `ReimpresionTicketRead` with `estado='rechazada'`, `uuid_reimpresion_padre = <tip.uuid>`, `motivo_anulacion` populated.
- **Status codes**:
  - `201 Created` — happy path (new chain row inserted)
  - `400 motivo_muy_corto` — Pydantic `min_length=10` rejects before DB hit
  - `404 reimpresion_not_found` — V1: `<uuid>` not in chain
  - `403 tenant_scope_violation` — operador- with cross-branch
  - `409 anulacion_no_permitida` — chain tip state is already `rechazada` (terminal; V2)
- **Headers**: `Cache-Control: no-store`.
- **Idempotency**: `Idempotency-Key` HTTP header (DEC-IDEM-01). Multiple POSTs with different keys on the same chain tip create multiple `rechazada` rows (the chain allows forks per REQ-X9 tie-break); multiple POSTs with the same key return the cached response.

### 4.3 (Out of scope) `GET /workflows/reimpresion-ticket`

The existing GET mount (preserved from PR6) works correctly after DEC-TKT-01 reconciliation — returns 200 for actors with `reimprimir_ticket` permission (previously 403 due to permission mismatch).

---

## 5. Tables Touched

Four tables. Three read-only, one read+insert. No schema changes to existing tables. MIGRATION 0029 adds 1 conditional siembra + 1 permission seed + 1 role-permission grant.

### 5.1 `prod.reimpresion_ticket` `[L-W]` (INSERT-only per transition)

- **Operations**: V1 SELECT chain tip (`repo/workflow.read_chain_tip`); V2 SELECT most-recent active row for same `uuid_ingreso` (already-pending guard); V3 INSERT via `repo.workflow.append_transition(estado='autorizada')` (create) or `(estado='rechazada', parent_fk_column='uuid_reimpresion_padre', parent_uuid=tip.uuid)` (anular).
- **Columns write (INSERT)**:
  - Create: `uuid_sucursal`, `uuid_ingreso`, `uuid_usuario`, `motivo`, optional `uuid_factura`, `vigente_desde=now()`, `vigente_hasta=NULL`, `estado='activo'`, `uuid_reimpresion_padre=NULL`, `timestamp_evento=now()`, `created_at`+`created_by` (server-set).
  - Anular: same columns PLUS `motivo_anulacion`, with `uuid_reimpresion_padre=<tip.uuid>` and `estado='rechazada'` is NOT a separate column — the chain tip row itself is at `estado='autorizada'`; the new row ALSO uses `estado='activo'` versioning + the chain state is carried via the bi-temporal versioning + chain walk. **The state machine value** (`solicitada|autorizada|ejecutada|rechazada`) lives on the application-level tracker (see DEC-TKT-02 clarifying note).
- **Indexes**: existing PK `uuid` + trigger-managed versioning. FK `fk_reimpresion_ticket_uuid_reimpresion_padre` (migration 0001 lines 1690-1692) enforces chain integrity.
- **Defense in depth**: FK constraint blocks orphan chain pointers. Audit triggers + sync enqueue trigger fire automatically. AST walk `tests/static/test_no_raw_dml_on_lw_tables.py` (F1.5 PR5-016) blocks raw INSERT/UPDATE/DELETE.

#### 5.1.1 DEC-TKT-02 clarifying note on `estado` semantics

The `prod.reimpresion_ticket.estado` column (String(16), `'activo' | 'inactivo'`) is the **bi-temporal VersionedMixin versioning toggle**, NOT the workflow state machine value. The workflow state machine values (`solicitada | autorizada | ejecutada | rechazada`) live on **business columns tracked via `log_transaccional`** + the chain via `uuid_reimpresion_padre`. For F1.11 the canonical chain tip state is derived at read time via `repo.workflow.read_chain_tip(... parent_fk_column='uuid_reimpresion_padre')` → returns the latest row by `(max(timestamp_evento), longest chain, lex(uuid))` tie-break.

For the response schema, the handler **synthesizes** a `estado` field with the workflow value (`solicitada|autorizada|ejecutada|rechazada`) by reading the chain tip row's `timestamp_evento` and applying a simplified rule for MVP: create → `autorizada`; anular → `rechazada`. Future HUs (F2.x) will extend this with a `prod.workflow_estado` companion table when manual autorización is reintroduced.

### 5.2 `prod.costos_servicios` `[V]` (SELECT for vigente row)

- **Operations**: Conditional siembra via MIGRATION 0029 (one-time idempotent INSERT if absent); otherwise zero writes from F1.11. Pre-flight at migration time verifies existence.
- **Columns read**: `uuid`, `concepto`, `costo`, `tipo_calculo`, `vigente_desde`, `vigente_hasta`, `estado`. F1.11 does NOT consume `costos_servicios.costo` because the **issuance flow is decoupled from the cost** (the reimpresion records an EVENT; charging an existing `uuid_factura` is optional via `uuid_factura` field per DEC-TKT-04). The handler reads the vigente row ONLY to validate that the operator has configured `concepto='reimpresion'`; cost value is informational.
- **Defense in depth**: bi-temporal VersionedBase guarantees at most one vigente row per `concepto`. Handler returns 409 `costo_servicio_no_configurado` if lookup returns NULL (DEC-TKT-05 covers the seed; this is a defensive runtime check after seed).

### 5.3 `prod.ingreso` `[A]` (SELECT-only)

- **Operations**: V1 SELECT by UUID in create handler.
- **Columns read**: `uuid`, `uuid_sucursal`.
- **Defense in depth**: NULL → 404 `ingreso_no_encontrado`.

### 5.4 `prod.facturas` `[A]` (READ-only, optional)

- **Operations**: If `uuid_factura` is provided in the create request, V1+ SELECT by UUID to validate existence. The cost is NOT snapshotted from the factura — the reimpresion event is recorded independently.
- **Defense in depth**: NULL `uuid_factura` → skip the SELECT (optional per DEC-TKT-04). Non-existent `uuid_factura` → 404 `factura_no_encontrada`.

### 5.5 `prod.permisos` `[V]` + `prod.permisos_usuario` `[V]` (MIGRATION 0029 Op 2)

- **Operations**: MIGRATION 0029 Op 2 INSERTs the `anular_reimpresion` permission (mirror of `anular_ingreso_salida`). Op 3 GRANTs `anular_reimpresion` to the `operador` and `admin` roles via `prod.permisos_usuario` (or `prod.roles_permisos` depending on the implementation in migration 0021). Verify against existing schema before writing.

---

## 6. Decisions

### 6.1 DEC-TKT-01 — GAP-BE-04 permission reconciliation: `emitir_reimpresion` → `reimprimir_ticket` (RESOLVES R1 MEDIUM)

**Decision**: Single-line fix in `api/v1/workflows.py:74`. NO migration, NO permission re-seed.

**Rationale**: plan.md line 7342 mandates the reconciliation as GAP-BE-04. `reimprimir_ticket` is already seeded at `0001_initial_schema.py` line 3292. The fix unblocks the entire `reimpresion-ticket` resource (highest blast radius).

**Alternatives considered**:
- *Re-seed `emitir_reimpresion`* — REJECTED. Duplicate permission for same intent; violates single-source-of-truth.
- *Add `emitir_reimpresion` as alias* — REJECTED. Violates single-source-of-truth.

### 6.2 DEC-TKT-02 — Reimpresión as INSERT-only via `repo.workflow.append_transition` (NEVER UPDATE)

**Decision**: Both POST endpoints INSERT new rows via `append_transition`. Create: `estado='autorizada'` (chain tip), `uuid_reimpresion_padre=NULL`. Anular: `estado='rechazada'`, `uuid_reimpresion_padre=<tip.uuid>`. NEVER UPDATE.

**Rationale**: `[L-W]` WorkflowBase insert-only invariant. Audit trail completeness. The chain IS the history. AST walk already in place blocks raw DML.

**Alternatives considered**:
- *UPDATE original to a `rechazada` state* — REJECTED. Breaks audit trail. R3 risk.
- *Separate `reimpresion_anulaciones` table* — REJECTED. The chain IS the history.

### 6.3 DEC-TKT-03 — Anulación chain via NEW row + `uuid_reimpresion_padre` (NEVER UPDATE) — orphan gap closed

**Decision**: Anulación endpoint INSERTs new row with `uuid_reimpresion_padre` pointing at original chain tip. Original row NEVER updated. Chain tip selected by `read_chain_tip` per REQ-X9 tie-break. Insert ALWAYS succeeds for non-terminal chains; terminal `rechazada` chain tips return 409 `anulacion_no_permitida`.

**Rationale**: plan.md line 993 explicitly flags the anulación as **"gap huérfano detectado"**. `[L-W]` pattern is same as `anulaciones`/`alerta`/`envio_dian`.

### 6.4 DEC-TKT-04 — `uuid_factura` is OPTIONAL on the create INSERT (charge may be deferred to HU-F8.3)

**Decision**: `ReimpresionTicketCreateEndpoint` accepts `uuid_factura: UUID | None = None`. If NULL, reimpresion is recorded WITHOUT a factura charge. HU-F8.3 (frontend) creates the factura via F1.9 machinery and calls the endpoint with the resulting `uuid_factura`. If provided, the handler validates the factura exists (V1 SELECT) but does NOT snapshot the cost.

**Rationale**: 170 LOC budget is tight for full F1.9-style atomic factura creation + reimpresion_ticket INSERT in one TX. Splitting concerns keeps F1.11 focused on workflow chain + permission reconciliation. The `uuid_factura` is a forward reference to HU-F8.3 (frontend owns the create-then-reimprimir flow). The admin-correction use case (anular a reimpresion that had a charging typo) is served by leaving `uuid_factura` nullable.

**Alternatives considered**:
- *F1.11 creates the factura inline* — REJECTED. Budget overrun; duplicates F1.9.
- *F1.11 mandates `uuid_factura` is required* — REJECTED. Breaks admin-correction anular case.

### 6.5 DEC-TKT-05 — Siembra `costos_servicios.concepto='reimpresion'` strategy: MIGRATION 0029 with idempotent pre-flight

**Decision**: MIGRATION 0029 carries a `DO $$` block:
1. Verifies `prod.costos_servicios` table exists (pre-flight abort if not).
2. Checks `SELECT COUNT(*) FROM prod.costos_servicios WHERE concepto='reimpresion' AND vigente_hasta IS NULL AND estado='activo'`.
3. If 0 rows, INSERTs a new row with `concepto='reimpresion'`, `costo=0` (operator-configurable later), `tipo_calculo='fijo'`.
4. If ≥1 row, no-op (idempotent).

**If siembra is ALREADY present** (verifiable via pre-flight SQL query against the live DB), MIGRATION 0029 still ships — the `DO $$` block is the no-op path. The migration is REQUIRED because we cannot know in advance whether the siembra exists.

**Rationale**: Mirrors F1.7's `impuestos.IVA` inline siembra (MIGRATION 0026 pattern + pending list). Idempotent on re-apply. Operator-configurable cost avoids hardcoded values.

**Alternatives considered**:
- *Separate siembra catalog file* — REJECTED. Loses atomic guarantee with the schema migration.
- *Document siembra as out-of-scope* — REJECTED. The pending blocker explicitly mandates verification.

### 6.6 DEC-TKT-06 — Router flag unmount (was conditional on `WORKFLOWS_ROUTER_ENABLED`)

**Decision**: F1.11 sets `WORKFLOWS_ROUTER_ENABLED=True` for the `reimpresion-ticket` mount (the flag was previously gating the entire resource). Additionally, the new `anular` endpoint is mounted as a dedicated POST handler alongside the existing factory-mounted C+Q endpoints (not via the factory's `write_enabled=True` to keep the 170 LOC budget tight).

**Rationale**: plan.md line 989 mandates that the new write endpoints be available. The flag unmount is the smallest path forward. The `anular` endpoint is implemented as a dedicated handler in a new `api/v1/workflows_reimpresion.py` module to avoid bloating the factory path.

**Alternatives considered**:
- *Use the factory with `write_enabled=True`* — REJECTED. The factory's `versioned` branch is not wired for `append_transition` writes; the L-W pattern needs custom handlers.
- *Add endpoints to a separate router and include in the parent* — ACCEPTED. This is the implementation plan.

---

## 7. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **GAP-BE-04 permission mismatch** — `workflows.py:74` uses `emitir_reimpresion`, `prod.permisos` has `reimprimir_ticket`. Router returns 403 forever. | **MEDIUM (RESOLVED)** | DEC-TKT-01 (§6.1) + single-line fix. Verified by `test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion` (regression test). |
| **R2** | `costos_servicios.concepto='reimpresion'` siembra absent → handler returns 409 at runtime. | **MEDIUM** | DEC-TKT-05 (§6.5) + MIGRATION 0029 Op 1 with idempotent pre-flight. If siembra is present, the migration is a no-op. |
| **R3** | Chain integrity via FK — concurrent anulaciones on same original create a fork (allowed by schema). | **LOW** | FK enforces referential integrity. `read_chain_tip` returns deterministic tip per REQ-X9 tie-break. Documented in design. |
| **R4** | Concurrent reimpresions on SAME `ingreso` (multiple operators, same ingreso) — schema allows it. | **LOW** | INTENTIONAL — the chain captures every event. Cool-down not enforced at MVP. Documented as known limitation. |
| **R5** | Tenant scope pre-V1 — operadores across branches could create reimpresions for foreign `uuid_ingreso`. | **LOW** | KD-S2 analog from F1.7: handler compares `ctx.sucursal_uuid` against `ingreso.uuid_sucursal`. Same pattern as F1.9/F1.10. |
| **R6** | `motivo_anulacion` audit — Pydantic only validates length; semantic content is free-form. | **LOW** | Layer 5 enforces `min_length=10, max_length=500`. Storage is sufficient for any reasonable audit trail. |
| **R7** | AST walk `test_no_raw_dml_on_lw_tables.py` must reject new handlers' potential raw INSERT statements. | **MEDIUM** | The walk already exists for `append_transition` calls. Add `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` (DEC-TKT-02 enforcement). |

---

## 8. Defense in Depth

5 layers mirror the F1.10 / F1.9 precedent:

### Layer 1 — KD-3 issuer chain + permission check (GAP-BE-04 reconciled via DEC-TKT-01)

`_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")`. `permission_required="reimprimir_ticket"` (after reconciliation, §3). For the `anular` endpoint, `permission_required="anular_reimpresion"` (seeded in MIGRATION 0029 Op 2 + granted to roles in Op 3).

### Layer 2 — Tenant scope post-V1

After resolving `target_sucursal` from `prod.ingreso.uuid_sucursal` (V1 in create) or from `prod.reimpresion_ticket.uuid_sucursal` (V1 in anular), if `ctx.issuer_prefix == "operador-"` and `target_sucursal != ctx.sucursal_uuid`, return `403 tenant_scope_violation`. Admin (`admin-`) bypasses.

### Layer 3 — DB-layer FK chain integrity via `uuid_reimpresion_padre`

Existing FK constraint (migration 0001 lines 1690-1692) enforces referential integrity for chain self-pointer. Orphan chain pointers blocked at DB layer.

### Layer 4 — WorkflowBase insert-only invariant + AST walk

`WorkflowBase.__workflow_only__` AST marker (F1.5 PR5-016). `tests/static/test_no_raw_dml_on_lw_tables.py` enforces ALL write paths flow through `repo.workflow.append_transition`. F1.11 adds `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` for the DEC-TKT-02 INSERT-only invariant (no UPDATE on `prod.reimpresion_ticket` rows from the new handlers).

### Layer 5 — Handler 422/409 mapping + typed exceptions

| Typed exception | HTTP | `error` body | Source |
|---|---|---|---|
| `IngresoNoEncontradoError` | 404 | `ingreso_no_encontrado` + `uuid_ingreso` | `repo/reimpresion_ticket.py` (NEW) |
| `ReimpresionNotFoundError` | 404 | `reimpresion_not_found` + `uuid` | `repo/reimpresion_ticket.py` (NEW) |
| `ReimpresionAlreadyPendingError` | 409 | `reimpresion_already_pending` + `uuid_ingreso` | `repo/reimpresion_ticket.py` (NEW) |
| `AnulacionNoPermitidaError` | 409 | `anulacion_no_permitida` + `estado_actual` | `repo/reimpresion_ticket.py` (NEW) |
| `CostoServicioNoConfiguradoError` | 409 | `costo_servicio_no_configurado` + `concepto` | `repo/reimpresion_ticket.py` (NEW) |
| `MotivoMuyCortoError` | 400 | `motivo_muy_corto` + `min_length=10` | Pydantic `min_length` |
| `IllegalTransitionError` | 409 | `illegal_transition` + `from_estado` + `to_estado` | `repo/workflow.py` (existing) |
| `ChainNotFoundError` | 404 | `chain_not_found` + `root_uuid` | `repo/workflow.py` (existing) |
| `WorkflowError` | 500 | `workflow_error` | `repo/workflow.py` (existing) |

The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

---

## 9. API Contracts

Same schemas as the orchestrator brief, in full Pydantic v2 form. Append to `schemas/workflows.py` + update `__all__`.

### 9.1 Request schemas

```python
class ReimpresionTicketCreateEndpoint(_Base):
    """HU-F1.11: POST /api/v1/workflows/reimpresion-ticket payload.

    DEC-TKT-04: uuid_factura is OPTIONAL; deferred to HU-F8.3 frontend
    for the create-factura-then-reimprimir flow.

    extra='forbid' (inherited from _Base) blocks client smuggling of
    uuid_reimpresion_padre, estado, costo_aplicado, uuid_costo_servicio,
    timestamp_evento, uuid_sucursal, uuid_usuario, vigente_desde,
    vigente_hasta, created_at, created_by.
    """
    motivo: Annotated[str, StringConstraints(min_length=10, max_length=500)]
    uuid_ingreso: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID | None = None


class ReimpresionTicketAnular(_Base):
    """HU-F1.11: POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular payload.

    The chain tip UUID is the path parameter; the body carries only
    motivo_anulacion (audit trail).

    extra='forbid' rejects estado, uuid_reimpresion_padre (server-set),
    and any state machine manipulation.
    """
    motivo_anulacion: Annotated[str, StringConstraints(min_length=10, max_length=500)]
```

### 9.2 Response schemas

The response uses the existing `ReimpresionTicketRead` schema (schemas/workflows.py lines 54-79). The handler **synthesizes** the workflow-level `estado` field as `Literal["solicitada", "autorizada", "ejecutada", "rechazada"]` for the response payload (the bi-temporal `estado` column is separate; see §5.1.1 DEC-TKT-02 clarifying note).

```python
class ReimpresionTicketRead(_Base):
    """Read-back for prod.reimpresion_ticket (existing schema, extended).

    The workflow_estado field is server-derived from the chain tip:
    - Create response: 'autorizada'
    - Anular response: 'rechazada' with motivo_anulacion populated
    """
    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_ingreso: uuid_lib.UUID | None
    uuid_usuario: uuid_lib.UUID | None
    uuid_costo_servicio: uuid_lib.UUID | None
    costo_aplicado: Decimal | None
    uuid_factura: uuid_lib.UUID | None
    motivo: Annotated[str, StringConstraints(max_length=500)] | None = None
    motivo_anulacion: Annotated[str, StringConstraints(max_length=500)] | None = None
    uuid_reimpresion_padre: uuid_lib.UUID | None
    timestamp_evento: datetime | None
    vigente_desde: datetime | None
    vigente_hasta: datetime | None
    estado: str | None  # bi-temporal versioning toggle ('activo' | 'inactivo')
    workflow_estado: Literal["solicitada", "autorizada", "ejecutada", "rechazada"] | None = None
    # server-derived
```

### 9.3 Typed error schemas

```python
class ReimpresionAlreadyPendingError(_Base):
    error: Literal["reimpresion_already_pending"]
    uuid_ingreso: str


class AnulacionNoPermitidaError(_Base):
    error: Literal["anulacion_no_permitida"]
    uuid_reimpresion: str
    estado_actual: str


class ReimpresionNotFoundError(_Base):
    error: Literal["reimpresion_not_found"]
    uuid_reimpresion: str


class IngresoNoEncontradoError(_Base):
    error: Literal["ingreso_no_encontrado"]
    uuid_ingreso: str


class CostoServicioNoConfiguradoError(_Base):
    error: Literal["costo_servicio_no_configurado"]
    concepto: str
```

Append to `schemas/workflows.py` + update `__all__`. `extra='forbid'` (inherited from `_Base`) rejects client smuggling.

---

## 10. Handler Skeleton

Two handlers, each mirroring the F1.10 retry handler structure. All single-commit (KD-TKT-01 single-commit invariant).

### 10.1 `POST /workflows/reimpresion-ticket` — 8-step chain

```python
async def create_reimpresion_ticket(
    response: Response,
    payload: ReimpresionTicketCreateEndpoint,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_reimpresion_issuer_dep),
) -> ReimpresionTicketRead:
    no_store = no_store_headers()

    # Step 1: KD-3 issuer + no_store (resolved via DI)

    # Step 2: V1 — prod.ingreso.uuid exists + tenant scope
    ingreso = await repo_reimpresion.buscar_ingreso_por_uuid(
        session, uuid_ingreso=payload.uuid_ingreso
    )
    if ingreso is None:
        raise HTTPException(404, {"error": "ingreso_no_encontrado", "uuid_ingreso": str(payload.uuid_ingreso)}, headers=no_store)

    target_sucursal = ingreso.uuid_sucursal
    if ctx.issuer_prefix == "operador-" and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid):
        raise HTTPException(403, {"error": "tenant_scope_violation"}, headers=no_store)

    # Step 3: V2 — no recent active chain row for the same uuid_ingreso
    existing_tip = await repo_reimpresion.buscar_reimpresion_activa_por_ingreso(
        session, uuid_ingreso=payload.uuid_ingreso
    )
    if existing_tip is not None:
        raise HTTPException(409, {"error": "reimpresion_already_pending", "uuid_ingreso": str(payload.uuid_ingreso), "uuid_reimpresion": str(existing_tip["uuid_actual"])}, headers=no_store)

    # Step 4: optional uuid_factura validation
    if payload.uuid_factura is not None:
        factura = await repo_reimpresion.buscar_factura_por_uuid(
            session, uuid_factura=payload.uuid_factura
        )
        if factura is None:
            raise HTTPException(404, {"error": "factura_no_encontrada", "uuid_factura": str(payload.uuid_factura)}, headers=no_store)

    # Step 5: KD-TKT-01 — INSERT prod.reimpresion_ticket [L-W] via append_transition
    new_reimpresion = await repo.workflow.append_transition(
        session,
        ReimpresionTicket,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": target_sucursal,
            "uuid_ingreso": payload.uuid_ingreso,
            "uuid_usuario": ctx.actor_uuid,
            "uuid_factura": payload.uuid_factura,
            "motivo": payload.motivo,
            "timestamp_evento": _now_naive(),
            "estado": "autorizada",  # workflow state machine value (synthesized)
        },
        parent_uuid=None,
        parent_fk_column="uuid_reimpresion_padre",
        log_tx=True,
    )

    # Step 6: KD-TKT-01 single commit
    await session.commit()
    await session.refresh(new_reimpresion)

    # Step 7: apply_no_store_header
    apply_no_store_header(response)

    # Step 8: response shape
    return ReimpresionTicketRead(
        uuid=new_reimpresion.uuid,
        created_at=new_reimpresion.created_at,
        created_by=new_reimpresion.created_by,
        sync_status=new_reimpresion.sync_status,
        sync_timestamp=new_reimpresion.sync_timestamp,
        sync_attempts=new_reimpresion.sync_attempts,
        uuid_sucursal=new_reimpresion.uuid_sucursal,
        uuid_ingreso=new_reimpresion.uuid_ingreso,
        uuid_usuario=new_reimpresion.uuid_usuario,
        uuid_costo_servicio=new_reimpresion.uuid_costo_servicio,
        costo_aplicado=new_reimpresion.costo_aplicado,
        uuid_factura=new_reimpresion.uuid_factura,
        motivo=new_reimpresion.motivo,
        motivo_anulacion=None,
        uuid_reimpresion_padre=new_reimpresion.uuid_reimpresion_padre,
        timestamp_evento=new_reimpresion.timestamp_evento,
        vigente_desde=new_reimpresion.vigente_desde,
        vigente_hasta=new_reimpresion.vigente_hasta,
        estado=new_reimpresion.estado,
        workflow_estado="autorizada",
    )
```

### 10.2 `POST /workflows/reimpresion-ticket/{uuid}/anular` — 6-step chain

```python
async def anular_reimpresion_ticket(
    response: Response,
    uuid_reimpresion: uuid_lib.UUID,
    payload: ReimpresionTicketAnular,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_anular_reimpresion_issuer_dep),  # requires 'anular_reimpresion' permission
) -> ReimpresionTicketRead:
    no_store = no_store_headers()

    # Step 1: KD-3 issuer + no_store (resolved via DI)

    # Step 2: V1 — chain tip exists
    try:
        tip = await repo.workflow.read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=uuid_reimpresion,
            parent_fk_column="uuid_reimpresion_padre",
        )
    except ChainNotFoundError:
        raise HTTPException(404, {"error": "reimpresion_not_found", "uuid_reimpresion": str(uuid_reimpresion)}, headers=no_store)

    # Step 3: Tenant scope post-V1
    tip_row = await repo_reimpresion.buscar_reimpresion_por_uuid(session, uuid=tip["uuid_actual"])
    if tip_row is None:
        raise HTTPException(404, {"error": "reimpresion_not_found", "uuid_reimpresion": str(uuid_reimpresion)}, headers=no_store)
    if ctx.issuer_prefix == "operador-" and (ctx.sucursal_uuid is None or tip_row.uuid_sucursal != ctx.sucursal_uuid):
        raise HTTPException(403, {"error": "tenant_scope_violation"}, headers=no_store)

    # Step 4: V2 — chain tip state check (anular NOT allowed if already rechazada terminal)
    if tip["estado"] == "rechazada":
        raise HTTPException(409, {"error": "anulacion_no_permitida", "uuid_reimpresion": str(uuid_reimpresion), "estado_actual": "rechazada"}, headers=no_store)

    # Step 5: KD-TKT-01 — INSERT new reimpresion_ticket row with uuid_reimpresion_padre=tip.uuid, estado='rechazada'
    new_row = await repo.workflow.append_transition(
        session,
        ReimpresionTicket,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": tip_row.uuid_sucursal,
            "uuid_ingreso": tip_row.uuid_ingreso,
            "uuid_usuario": ctx.actor_uuid,
            "motivo": payload.motivo_anulacion,
            "motivo_anulacion": payload.motivo_anulacion,
            "timestamp_evento": _now_naive(),
            "estado": "rechazada",  # workflow state machine value (synthesized)
        },
        parent_uuid=tip["uuid_actual"],
        parent_fk_column="uuid_reimpresion_padre",
        log_tx=True,
    )

    # Step 6: KD-TKT-01 single commit
    await session.commit()
    await session.refresh(new_row)

    apply_no_store_header(response)
    return ReimpresionTicketRead(
        ...,
        workflow_estado="rechazada",
        motivo_anulacion=new_row.motivo_anulacion,
        uuid_reimpresion_padre=new_row.uuid_reimpresion_padre,
    )
```

---

## 11. Tests

5 test files, ~280 LOC tests + ~170 LOC production = ~450 LOC cumulative. All AST walks + handler tests pattern after F1.9/F1.10.

### 11.1 `tests/unit/test_reimpresion_ticket_schemas.py` (~50 LOC, 3 tests)

- `test_create_endpoint_rejects_estado_injection` — `extra='forbid'` rejects `estado='autorizada'`.
- `test_create_endpoint_rejects_uuid_reimpresion_padre_injection` — rejects `uuid_reimpresion_padre=...`.
- `test_anular_endpoint_rejects_state_injection` — rejects `estado`, `uuid_reimpresion_padre`, `timestamp_evento`.

### 11.2 `tests/unit/test_reimpresion_ticket_create_handler.py` (~80 LOC, 4 tests)

- `test_create_reimpresion_happy_path_returns_201` — happy path: create row with `estado='autorizada'`, `uuid_reimpresion_padre=NULL`.
- `test_create_reimpresion_returns_404_si_ingreso_no_existe` — V1 ingreso_not_found.
- `test_create_reimpresion_returns_409_reimpresion_already_pending` — V2 chain tip already exists.
- `test_create_reimpresion_returns_403_si_tenant_scope_violation` — cross-branch operador- rejected.

### 11.3 `tests/unit/test_reimpresion_ticket_anular_handler.py` (~60 LOC, 3 tests)

- `test_anular_reimpresion_happy_path_returns_201_with_new_chain_row` — INSERT new row with `uuid_reimpresion_padre=tip.uuid`, `estado='rechazada'`.
- `test_anular_reimpresion_returns_409_si_estado_rechazada_terminal` — V2 chain tip already rechazada.
- `test_anular_reimpresion_returns_404_si_reimpresion_not_found` — V1 chain_not_found.

### 11.4 `tests/integration/test_workflows_router_wiring.py` (~40 LOC, 2 tests)

- `test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion` — GAP-BE-04 regression test (DEC-TKT-01).
- `test_anular_reimpresion_endpoint_requires_anular_reimpresion_permission` — verifies the `anular_reimpresion` permission gate.

### 11.5 `tests/integration/test_migration_0029_idempotent.py` (~50 LOC, 2 tests)

- `test_migration_0029_idempotent_upgrade_downgrade_upgrade` — full cycle.
- `test_siembra_costos_servicios_reimpresion_pre_flight` — DEC-TKT-05 verification (if siembra absent, INSERT; if present, no-op).

### 11.6 AST walks (mandatory)

- `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` (~30 LOC, 1 AST walk) — DEC-TKT-02 + REQ-INSERT-only invariant. `ast.walk()` over `create_reimpresion_ticket` and `anular_reimpresion_ticket` bodies enforces no raw UPDATE/DELETE on `ReimpresionTicket`.

Total: ~14 tests across 5 test files + 1 AST walk.

---

## 12. Out of Scope

1. **Create-factura-then-reimprimir flow** — HU-F8.3 (frontend Fase 8). F1.11 keeps `uuid_factura` optional (DEC-TKT-04).
2. **Autorización step** — the state machine `solicitada → autorizada` is automated in MVP; manual autorización (requester + authorizer + executor) deferred to F2.x.
3. **Email/SMS notifications on anulación** — Fase 4.
4. **Multi-tenant anulación audit** — single-tenant for F1.11.
5. **Cost recalculation engine** — F1.11 uses static `costos_servicios` vigente row.
6. **Cool-down period between reimpresions** — MVP allows concurrent reimpresions on the same `uuid_ingreso`; the chain captures every event.
7. **Read endpoint** — `GET /workflows/reimpresion-ticket` already exists in PR6. F1.11 does not modify it (DEC-TKT-01 fixes the permission gate; behavior unchanged).
8. **Real `costo` snapshot at issuance** — the cost is informational; F1.11 does not freeze cost on the row. Future HUs may add a `prod.reimpresion_costo` companion table.

---

## 13. Requirements (REQ-OPS-075..080)

The following REQ-OPS-NNN placeholders will be formalized by `sdd-spec` in `openspec/changes/hu-f1-11-reimpresion-tiquete/specs/operations/spec.md`:

- **REQ-OPS-075 (NEW)** — `POST /api/v1/workflows/reimpresion-ticket` contract: `ReimpresionTicketCreateEndpoint` input (`{motivo, uuid_ingreso, uuid_factura?}`) + `ReimpresionTicketRead` output (workflow_estado='autorizada'). KD-3 issuer chain (`requires_issuer("operador-", "admin-")`); `Cache-Control: no-store`; `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10).

- **REQ-OPS-076 (NEW, DEC-TKT-01)** — GAP-BE-04 fix: `api/v1/workflows.py:74` permission name changes from `emitir_reimpresion` to `reimprimir_ticket` (single-line fix). No migration, no re-seed required. Closes the highest-blast-radius permission mismatch in the codebase.

- **REQ-OPS-077 (NEW, DEC-TKT-02)** — Reimpresión as INSERT-only via `repo.workflow.append_transition`. Each transition = NEW row with `uuid_reimpresion_padre` pointing at previous chain tip. NEVER UPDATE.

- **REQ-OPS-078 (NEW, DEC-TKT-03)** — Anulación endpoint (`POST /workflows/reimpresion-ticket/{uuid}/anular`) INSERTs NEW row with `uuid_reimpresion_padre=<tip.uuid>` and `estado='rechazada'` (workflow_estado). Original row NEVER updated. Closes the orphan anulación gap (plan.md line 993).

- **REQ-OPS-079 (NEW, DEC-TKT-05)** — CONDITIONAL MIGRATION 0029 pre-flight + siembra. `DO $$` queries `prod.costos_servicios WHERE concepto='reimpresion' AND vigente_hasta IS NULL AND estado='activo'`; if 0 rows → INSERT; if ≥1 → no-op.

- **REQ-OPS-080 (NEW, DEC-TKT-04)** — `uuid_factura` OPTIONAL on the create INSERT. Nullable FK to `prod.facturas`. The handler validates existence IF provided, but does NOT snapshot the cost.

Additional defense-in-depth XR:

- **REQ-OPS-XR4 (NEW)** — Insert-only invariant AST walk: `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` enforces no raw UPDATE/DELETE on `prod.reimpresion_ticket` from the F1.11 handler bodies. Mirror of F1.10's XR1..XR3.

---

## 14. Migrations

**MIGRATION 0029** (~80 LOC, 3 ops + 1 downgrade block). `down_revision = "0028_one_fe_per_factura_and_chain_index_and_sync_flip"`.

### Op 1 — CONDITIONAL siembra `costos_servicios.concepto='reimpresion'` (DEC-TKT-05)

```sql
DO $$
DECLARE
    siembra_count INTEGER;
BEGIN
    ASSERT (
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='prod' AND table_name='costos_servicios'
    ) = 1, 'F1.11 requires prod.costos_servicios to exist';

    SELECT COUNT(*) INTO siembra_count
    FROM prod.costos_servicios
    WHERE concepto = 'reimpresion'
      AND vigente_hasta IS NULL
      AND estado = 'activo';

    IF siembra_count = 0 THEN
        INSERT INTO prod.costos_servicios (
            uuid, concepto, costo, tipo_calculo,
            vigente_desde, vigente_hasta, estado,
            created_at, created_by, sync_status, sync_attempts
        ) VALUES (
            gen_random_uuid(), 'reimpresion', 0, 'fijo',
            NOW(), NULL, 'activo', NOW(), NULL, 'sincronizado', 0
        )
        ON CONFLICT (concepto, vigente_desde) DO NOTHING;
    END IF;
END $$;
```

### Op 2 — Seed `anular_reimpresion` permission

```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM prod.permisos WHERE permiso = 'anular_reimpresion'
    ) THEN
        INSERT INTO prod.permisos (uuid, permiso, descripcion, vigente_desde, vigente_hasta, estado, created_at)
        VALUES (gen_random_uuid(), 'anular_reimpresion', 'Anular una reimpresion de tiquete autorizada/ejecutada (HU-F1.11)', NOW(), NULL, 'activo', NOW());
    END IF;
END $$;
```

### Op 3 — Grant `anular_reimpresion` to operador and admin roles

```sql
-- Grant to operador role
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='prod' AND table_name='permisos_usuario') THEN
        INSERT INTO prod.permisos_usuario (uuid, uuid_usuario, uuid_permiso, vigente_desde, vigente_hasta, estado, created_at)
        SELECT gen_random_uuid(), u.uuid, p.uuid, NOW(), NULL, 'activo', NOW()
        FROM prod.usuarios u, prod.permisos p
        WHERE p.permiso = 'anular_reimpresion'
          AND u.uuid_rol IN (
              SELECT uuid FROM prod.roles WHERE nombre IN ('operador', 'admin')
          )
          AND NOT EXISTS (
              SELECT 1 FROM prod.permisos_usuario pu
              WHERE pu.uuid_usuario = u.uuid AND pu.uuid_permiso = p.uuid AND pu.vigente_hasta IS NULL
          );
    END IF;
END $$;
```

### Downgrade (reverse order, superuser context)

```sql
-- Reverse role grants
DELETE FROM prod.permisos_usuario
WHERE uuid_permiso IN (SELECT uuid FROM prod.permisos WHERE permiso = 'anular_reimpresion');

-- Reverse permission seed
DELETE FROM prod.permisos WHERE permiso = 'anular_reimpresion';

-- Reverse siembra IF was inserted by this migration (no tracker; document as known limitation)
DELETE FROM prod.costos_servicios
WHERE concepto = 'reimpresion'
  AND vigente_desde >= NOW() - INTERVAL '1 hour'
  AND vigente_hasta IS NULL
  AND estado = 'activo';
```

**Known limitation**: Downgrade Op 1 unconditionally deletes any `costos_servicios.concepto='reimpresion'` row inserted in the last hour. If a manual siembra happened between migration and downgrade, the row is also deleted. Acceptable for MVP; tracker table not introduced. Documented as known limitation in design.md.

---

## 15. References

- `plan.md` lines 983-1006 (HU-F1.11 definition, 3 atomic tasks T1..T3, 170 LOC budget)
- `plan.md` lines 989-991 (acceptance criteria for crear + anular)
- `plan.md` line 993 (gap huérfano anulación)
- `plan.md` line 1001 (170 LOC budget)
- `plan.md` line 7342 (GAP-BE-04 permission reconciliation)
- `modelo_datos_er.mmd` lines 230-244 (`costos_servicios` [V])
- `modelo_datos_er.mmd` lines 598-620 (`reimpresion_ticket` [L-W])
- `modelo_datos_er.mmd` lines 1150-1155 (FK relationships)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 297-309 (costos_servicios), 893-910 (reimpresion_ticket), 1638-1692 (FKs), 2379-2390, 2660-2672, 2873-2880 (triggers), 3292 (reimprimir_ticket permission seed)
- `backend/packages/parkos_core/migrations/versions/0021_least_privilege_and_immutability_contract.py` lines 162, 182
- `backend/packages/parkos_core/migrations/versions/0028_one_fe_per_factura_and_chain_index_and_sync_flip.py` (current head)
- `backend/packages/parkos_core/src/parkos_core/models/L_W/reimpresion_ticket.py` lines 29-90
- `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` lines 50-132
- `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` lines 73-78 (GAP-BE-04) + 111-118 (mount)
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 66-72 (state machine), 110-237 (append_transition), 240-348 (read_chain_tip)
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 27-40
- Engram observation #1578 (F1.11 exploration, `sdd/hu-f1-11-reimpresion-tiquete/explore`)
- `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-proposal.md` (precedent for 16-section structure + defense-in-depth layers + KD-NN naming)
- `openspec/specs/operations/spec.md` lines 2517-3076 (REQ-OPS-064..074 + XR1..XR3 from F1.10)

---

## 16. Cross-HU Implications

| HU | Relationship | Implication |
|---|---|---|
| **F1.9 (closed)** | Independent. F1.9 atomically creates `prod.facturas`; F1.11 only OPTIONALLY references a `uuid_factura` (DEC-TKT-04). | No shared atomic transaction. HU-F8.3 owns the create-factura-then-reimprimir flow. |
| **F1.10 (closed)** | Independent. F1.10 owns `prod.factura_electronica` + `prod.envio_dian`. F1.11 reads nothing from those tables. | No interaction. |
| **F1.12 (Venta suscripción)** | Independent. | No interaction. |
| **F1.13 (Arqueo + cierre_dia)** | F1.13 may consume `prod.reimpresion_ticket` for `cierre_dia` reimpresion count (potential). | May need to add `workflow_estado != 'rechazada'` filter to F1.13 aggregation. F1.11 does NOT add this filter; F1.13 owns. |
| **F1.14 (sync estado)** | F1.14 may need to expose `reimpresion_ticket` chain tip for the operator dashboard. | Read-only GET mount already exists; F1.14 may query the new `workflow_estado` server-derived field. |
| **HU-F7.1 (Salida ingreso)** | Independent. | No interaction. |
| **HU-F8.3 (frontend reimprimir flow)** | Primary consumer of `uuid_factura` optional flow (DEC-TKT-04 deferred). | F8.3 creates the factura via F1.9 machinery, then calls POST /reimpresion-ticket with the resulting `uuid_factura`. |
| **Fase 4 (notifications)** | Deferred. Email/SMS on anulación. | Not in F1.11 scope. |

---

**End of proposal.**
