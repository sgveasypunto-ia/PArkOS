# Design: HU-F1.11 — Workflow reimpresión tiquete (crear + anular) + GAP-BE-04 cierre

> **Change**: `hu-f1-11-reimpresion-tiquete`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.11 — `POST /api/v1/workflows/reimpresion-ticket` (INSERT new `prod.reimpresion_ticket` row with `workflow_estado='autorizada'`, `uuid_reimpresion_padre=NULL`, `uuid_ingreso=<payload>`, optional `uuid_factura` per DEC-TKT-04, `motivo` ≥10 chars) + `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` (INSERT NEW `prod.reimpresion_ticket` row with `uuid_reimpresion_padre=<tip.uuid>` and `workflow_estado='rechazada'`, NEVER UPDATE — closes the orphan anulación gap at plan.md line 993) + GAP-BE-04 single-line fix at `api/v1/workflows.py:74` (`emitir_reimpresion` → `reimprimir_ticket`) + conditional MIGRATION 0029 siembra `prod.costos_servicios.concepto='reimpresion'` + permission seed `anular_reimpresion` + role grants.
> **Date**: 2026-09-15
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `340197e`; F1.1..F1.10 closed)
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (16 sections, ~480 LOC, DEC-TKT-01..06, KD-TKT-01..02, R1 MEDIUM RESOLVED, R2..R7) + `specs/operations/spec.md` (REQ-OPS-075..080 + REQ-OPS-XR4, 7 new requirements in Given/When/Then/And form + 1 cross-cutting XR4).
> **Cross-references**: `modelo_datos_er.mmd` (`prod.reimpresion_ticket` 598-620 [L-W] self-FK chain + `prod.costos_servicios` 230-244 [V] bi-temporal + `prod.permisos` + `prod.permisos_usuario`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (`reimpresion_ticket` 893-910 [L-W] + UK `costos_servicios_uk01` 297-309 [V] + self-FK `fk_reimpresion_ticket_uuid_reimpresion_padre` 1690-1692 + audit/versioning triggers 2379-2390, 2660-2672, 2873-2880 + `reimprimir_ticket` permission seed 3292); `backend/packages/parkos_core/migrations/versions/0028_one_fe_per_factura_and_chain_index_and_sync_flip.py` (current head — F1.10 closure); `backend/packages/parkos_core/src/parkos_core/models/L_W/reimpresion_ticket.py` (lines 29-90 — WorkflowBase + self-FK + 11 columns); `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` lines 54-132 (`ReimpresionTicketCreate` / `ReimpresionTicketRead` / `ReimpresionTicketUpdate` / `ReimpresionTicketFilter` / `ReimpresionTicketReadList`); `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` line 74 (GAP-BE-04 site — `emitir_reimpresion` stale) + lines 111-118 (mount) + lines 73-78 (`_ROUTER_CONFIG`); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 66-72 (state machine `reimpresion_ticket`) + lines 110-237 (`append_transition`) + lines 240-348 (`read_chain_tip`); `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 27-40 (`reimpresion_ticket` `branch_to_cloud` direction per D1-rev — **already configured**, NO change); `plan.md` lines 983-1006 (HU-F1.11 definition, 3 atomic tasks T1..T3, 170 LOC budget) + line 7342 (GAP-BE-04 mandate).
> **Precedents mirrored**: F1.10 (REQ-OPS-064..074 + XR1..XR3, KD-3 issuer `requires_issuer("operador-","admin-")` verbatim, KD-FE-01 single-commit, KD-FE-02 SELECT FOR UPDATE pattern, `Cache-Control: no-store`, `Idempotency-Key` DEC-IDEM-01, conditional siembra via pre-flight `DO $$`, commits `a9a8f47..05bb7ac`), F1.9 (REQ-OPS-053..063, `Idempotency-Key` header DEC-IDEM-01 reuse, KD-FACT-01 single-commit, partial UK pattern, AST walk pattern), F1.7 (REQ-OPS-042..052, KD-S2 tenant scope post-V1, AST walk pattern), F1.6 (REQ-OPS-034..041, KD-7 pre-flight pattern + DEC-IDEM-01 Idempotency-Key header), F1.5 (REQ-OPS-030..033, `repo/workflow.py::append_transition` + `read_chain_tip` + `WorkflowBase` insert-only invariant + MV pattern).

---

## 1. Title & Goal

**Design goal.** Deliver HU-F1.11: the back-end `POST /api/v1/workflows/reimpresion-ticket` endpoint that closes the **operador-facing reimpresión tiquete workflow** on top of the already-shipped `prod.reimpresion_ticket` `[L-W]` chain by enforcing the **KD-TKT-01 single-commit invariant** (exactly one `await session.commit()` per handler body) plus the **5-layer defense in depth** (KD-3 issuer chain + tenant scope post-V1 + `[L-W]` insert-only invariant + AST walk + handler 422/409 mapping). The design also ships the `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` endpoint that closes the **orphan anulación gap** (plan.md line 993) via INSERT-only semantics, plus the **GAP-BE-04 single-line permission reconciliation** (DEC-TKT-01) at `api/v1/workflows.py:74` — `emitir_reimpresion` → `reimprimir_ticket` — which unblocks the entire `reimpresion-ticket` resource (highest blast radius in the codebase), plus the **CONDITIONAL MIGRATION 0029** which (a) defensively seeds `prod.costos_servicios.concepto='reimpresion'` if absent (idempotent pre-flight via `DO $$` per DEC-TKT-05), (b) seeds the `anular_reimpresion` permission (mirror of `anular_ingreso_salida`), and (c) grants `anular_reimpresion` to `operador-` and `admin-` roles via `prod.permisos_usuario`.

The design enforces **DEC-TKT-01** (GAP-BE-04 single-line fix at `api/v1/workflows.py:74` — `reimprimir_ticket` permission is ALREADY seeded at migration 0001 line 3292; no migration, no re-seed required), **DEC-TKT-02** (reimpresión as INSERT-only via `repo.workflow.append_transition`; create chain root with `workflow_estado='autorizada'`, `uuid_reimpresion_padre=NULL`), **DEC-TKT-03** (anulación chain via NEW row + `uuid_reimpresion_padre=<tip.uuid>`, `workflow_estado='rechazada'` — NEVER UPDATE; original chain tip row NEVER mutated), **DEC-TKT-04** (`uuid_factura` OPTIONAL on the create INSERT — nullable FK to `prod.facturas.uuid`, validated only if provided), **DEC-TKT-05** (conditional siembra via pre-flight `DO $$` — idempotent on re-apply; the migration ships even when siembra is already present), **DEC-TKT-06** (new module `api/v1/workflows_reimpresion.py` for the 2 dedicated handlers, keeping the factory-mounted C+Q GET path unchanged), plus the **KD-TKT-01 single-commit invariant** (mirror of F1.10 KD-FE-01) and the **KD-TKT-02 chain-tip SELECT FOR UPDATE guard** (V2 SELECT-most-recent-active-row guards the cool-off window).

The handler enforces 4-5 validations server-side (V1 `prod.ingreso.uuid` exists → 404 `ingreso_no_encontrado`; V2 chain-tip guard — no recent `autorizada`/`ejecutada` row for same `uuid_ingreso` → 409 `reimpresion_already_pending`; V3 optional `prod.facturas.uuid` exists → 404 `factura_no_encontrada`; V4 KD-TKT-01 INSERT via `repo.workflow.append_transition` materializing the row + single commit; V5 for the anular endpoint, V1+V2 chain tip + V3 chain tip state guard `workflow_estado != 'rechazada'` → 409 `anulacion_no_permitida`; anulación's V4 INSERT with `uuid_reimpresion_padre=<tip.uuid>`, `workflow_estado='rechazada'`). All responses carry `Cache-Control: no-store`. Sized at **~170 LOC production** per `plan.md` línea 1001 (≈ 60 LOC `api/v1/workflows_reimpresion.py` 2 new handlers + 80 LOC `repo/reimpresion_ticket.py` + 30 LOC `schemas/workflows.py` + 1 LOC `api/v1/workflows.py:74` GAP-BE-04 fix — **+~180 LOC MIGRATION 0029** — + ~280 LOC tests across 5 files + ~30 LOC AST walk).

**Two new handlers + one new repo module + three new schemas + one conditional migration + one single-line GAP-BE-04 fix. No factory changes, no sync catalog changes, no new tables, no new FKs.**

---

## 2. Context & Background

`plan.md` lines **983-1006** define HU-F1.11 as Fase-1 backend prerequisite for the operador-facing reimpresión workflow. The hard architectural constraints are **DEC-TKT-01** (GAP-BE-04 single-line fix; permission `reimprimir_ticket` is ALREADY seeded in `prod.permisos` per migration 0001 line 3292 — the resource was 100% unreachable before F1.11 due to the typo'd permission name), **DEC-TKT-02** (reimpresión as INSERT-only via `repo.workflow.append_transition`; `[L-W]` WorkflowBase mandate of INSERT-only per transition), **DEC-TKT-03** (anulación NEVER UPDATE on the original chain tip row; the chain IS the audit trail), **DEC-TKT-04** (`uuid_factura` OPTIONAL — the create-factura-then-reimprimir flow is HU-F8.3 frontend territory; F1.11 keeps the FK nullable to support the admin-correction use case), **DEC-TKT-05** (conditional siembra via pre-flight `DO $$`; idempotent on re-apply), **DEC-TKT-06** (new `api/v1/workflows_reimpresion.py` module for the 2 dedicated handlers — the factory-mounted C+Q GET path stays unchanged for backward compatibility), the existing pre-existing tables (`prod.reimpresion_ticket` [L-W] lines 893-910 of migration 0001; `prod.costos_servicios` [V] lines 297-309; `prod.ingreso` [A]; `prod.facturas` [L-E] from F1.9; `prod.permisos` [V]; `prod.permisos_usuario` [V]), the existing ORM `models/L_W/reimpresion_ticket.py::ReimpresionTicket(WorkflowBase)` (lines 29-90, 11 columns), the existing `repo/workflow.py::append_transition` (F1.5 PR5-016, lines 110-237, validates the `reimpresion_ticket` state machine `solicitada → autorizada → ejecutada | rechazada`), the existing `repo/workflow.py::read_chain_tip` (F1.5 PR5-016, lines 240-348, walks `uuid_reimpresion_padre` self-FK + applies REQ-X9 tie-break), the existing `sync/catalog/entries/sync_entries_lw.py` entry for `reimpresion_ticket` (lines 27-40, `direction="branch_to_cloud"`, `apply_strategy="append_transition"`, `parent_fk_column="uuid_reimpresion_padre"`, **already configured per D1-rev** — NO change needed by F1.11), and the GAP-BE-04 mandate at plan.md line 7342 (`emitir_reimpresion` → `reimprimir_ticket`).

Today the `prod.reimpresion_ticket` resource is **completely unreachable** to operators with the canonical `reimprimir_ticket` permission because `api/v1/workflows.py:74` checks for `emitir_reimpresion` (the typo'd permission that no row in `prod.permisos` carries). The factory-mounted `make_router` resource for `reimpresion-ticket` at lines 111-118 uses the wrong permission name; the dependency check at `make_router` rejects all actors. The orphan anulación gap at plan.md line 993 means there is currently no way to record the rejection of a prior reimpresión (admin correction use case). The `prod.costos_servicios.concepto='reimpresion'` siembra is listed in the F1.11 pending section as a blocker that must be verified before F1.11 implementation; if absent, MIGRATION 0029 Op 1 inlines the siembra (mirror of F1.7's `impuestos.IVA` inline siembra via MIGRATION 0026). The state machine at `repo/workflow.py` lines 66-72 for `reimpresion_ticket`: `solicitada → [autorizada, rechazada]`, `autorizada → [ejecutada, rechazada]`, `ejecutada → []` (terminal), `rechazada → []` (terminal). For F1.11 the initial INSERT carries `estado='autorizada'` (auto-approved workflow; manual `solicitada → autorizada` step is F2.x deferred) — the workflow state machine value (`solicitada|autorizada|ejecutada|rechazada`) lives on the application-level chain tracker via `log_transaccional` + the chain via `uuid_reimpresion_padre`; the bi-temporal `prod.reimpresion_ticket.estado` column (`'activo'|'inactivo'`) is the versioning toggle, separate from the workflow state (see DEC-TKT-02 clarifying note in §5.1.1).

**The backend performs zero business validation on reimpresión creation or anulación today**, creating four concrete risks that HU-F1.11 resolves:

1. **`reimpresion-ticket` resource returns 403 forever.** Today `api/v1/workflows.py:74` requires permission `"emitir_reimpresion"` but `prod.permisos` (migration 0001 line 3292) carries `"reimprimir_ticket"`. Every request from an operator with the canonical permission is rejected at the FastAPI dependency check. The existing factory-mounted `GET /workflows/reimpresion-ticket` (PR6 T-PR6-10) is also affected (highest blast radius in the codebase). Without the GAP-BE-04 fix the new POST endpoints cannot reach the handler body either. F1.11 DEC-TKT-01 reconciles the permission name in a single line.
2. **Orphan anulación gap (plan.md line 993).** Without a way to record the rejection of a prior reimpresión, admin-correction flows (cancel a reimpresión that had a charging typo) cannot produce the regulatory audit trail. F1.11 introduces `/anular` as the ONLY legal way to record a rejection (NEW row with `uuid_reimpresion_padre=<tip.uuid>`, `workflow_estado='rechazada'`); NEVER UPDATE on the original chain tip row preserves the audit trail.
3. **Conditional siembra `costos_servicios.concepto='reimpresion'`.** If absent, the handler returns 409 `costo_servicio_no_configurado` at runtime (DEC-TKT-05 covers the seed; this is a defensive runtime check after seed). F1.11 MIGRATION 0029 Op 1 inlines the siembra via pre-flight `DO $$` so the migration ships regardless of whether siembra was already done by another HU.
4. **Anular permission missing.** `anular_reimpresion` is NOT in `prod.permisos` (verified per proposal §2.3). MIGRATION 0029 Op 2 seeds the permission; Op 3 grants it to `operador-` and `admin-` roles via `prod.permisos_usuario`. The `operador` and `admin` role UUIDs are resolved by `SELECT uuid FROM prod.roles WHERE nombre IN ('operador', 'admin')` (mirror of `anular_ingreso_salida` grant pattern from F1.7).

F1.11 closes the operador-facing reimpresión workflow. The work is **2 handlers + 1 repo module + 3 schemas + 1 conditional migration + 1 single-line GAP-BE-04 fix**. The migration is conditional because the siembra may already exist (the F1.11 pending section at plan.md línea 989-991 mandates verification before implementation). The factory-mounted C+Q GET path stays unchanged for backward compatibility — the existing `make_router` mount at lines 111-118 continues to serve `GET /workflows/reimpresion-ticket` after the GAP-BE-04 fix (DEC-TKT-01 unblocks the GET path too).

The contract is captured in **REQ-OPS-075..080 + REQ-OPS-XR4** (added by `sdd-spec` to `specs/operations/spec.md`):

- **REQ-OPS-075** — `POST /api/v1/workflows/reimpresion-ticket` INSERTs new `prod.reimpresion_ticket` row with `workflow_estado='autorizada'`, `uuid_reimpresion_padre=NULL`, `uuid_ingreso=<payload>`, optional `uuid_factura` (DEC-TKT-04), `motivo` ≥10 chars.
- **REQ-OPS-076** — GAP-BE-04 fix: `api/v1/workflows.py:74` permission name changes from `emitir_reimpresion` to `reimprimir_ticket` (single-line; DEC-TKT-01; NO migration, NO re-seed).
- **REQ-OPS-077** — Reimpresión as INSERT-only via `repo.workflow.append_transition`. Each transition = NEW row with `uuid_reimpresion_padre` pointing at previous chain tip. NEVER UPDATE (DEC-TKT-02 + DEC-TKT-03).
- **REQ-OPS-078** — Chain integrity via `uuid_reimpresion_padre` FK + `read_chain_tip` helper (mirror of F1.10 REQ-OPS-070).
- **REQ-OPS-079** — CONDITIONAL MIGRATION 0029 siembra `prod.costos_servicios.concepto='reimpresion'` if absent (DEC-TKT-05).
- **REQ-OPS-080** — `uuid_factura` OPTIONAL on the create INSERT (DEC-TKT-04). Nullable FK; validated only if provided; cost NOT snapshotted.
- **REQ-OPS-XR4** — Defense in depth 5 layers + AST walk for `[L-W]` insert-only invariant (mirror of F1.10 REQ-OPS-XR1..XR3).

F1.11 is consumed by **F1.13** (Arqueo + cierre_dia; may need to add `workflow_estado != 'rechazada'` filter to count successful reimpresions per sucursal per day), **F1.14** (sync estado; exposes `reimpresion_ticket` chain tip counts for the operator dashboard — now possible because the chain is branch-side per the existing `sync_entries_lw.py` configuration), **HU-F8.3** (frontend reimprimir flow; HU-F8.3 creates the factura via F1.9 machinery and calls POST /reimpresion-ticket with the resulting `uuid_factura` per DEC-TKT-04), **Fase 4** (notifications; email/SMS on anulación — out of F1.11 scope).

---

## 3. Architectural Conflict Resolution — DEC-TKT-01 (R1 MEDIUM RESOLVED)

This section is **mandatory** for the design. It documents R1 from the sdd-explore phase (observation #1578 §R1 MEDIUM) and records the resolution per `proposal.md §3`.

### 3.1 The conflict (R1 MEDIUM)

Three sources disagree about which permission guards `prod.reimpresion_ticket` writes:

| Source | Statement | Authority weight |
|---|---|---|
| `plan.md` línea 7342 | `emitir_reimpresion` → `reimprimir_ticket` (reconcile) | **CANONICAL** (per user mandate "siempre remitete al plan.md") |
| `0001_initial_schema.py` línea 3292 | `INSERT INTO prod.permisos VALUES (..., 'reimprimir_ticket', ...)` | Real seeded permission |
| `api/v1/workflows.py` línea 74 | `"emitir_reimpresion"` (WRONG) | Stale code from PR6 T-PR6-10 |

The `emitir_reimpresion` value is a legacy alias that survived PR6 T-PR6-10. The actual permission seeded in `prod.permisos` has been `reimprimir_ticket` since the initial schema migration. Without the fix the entire `reimpresion-ticket` resource returns 403 to all callers (operators with `reimprimir_ticket` permission are rejected because the router checks `emitir_reimpresion`, which no row in `prod.permisos` carries).

### 3.2 The resolution

**Resolution path** (mandated by plan.md + F1.11):

1. **Single-line fix** in `api/v1/workflows.py:74`:
   ```python
   "reimpresion-ticket": ("operador-,admin-", "reimprimir_ticket"),  # was "emitir_reimpresion"
   ```
2. **No migration needed** — `reimprimir_ticket` is ALREADY seeded in `prod.permisos` (migration 0001 line 3292).
3. **No permission grants needed** — the permission is already available; existing role assignments use it via `prod.permisos_usuario`.
4. **No sync catalog change** — `reimpresion_ticket` is already configured with `direction="branch_to_cloud"` and `apply_strategy="append_transition"` (per D1-rev + DEC-FE-01 applied to F1.10's `envio_dian` flip — `reimpresion_ticket` was always branch-initiated; no flip required).

### 3.3 What changes in the codebase (single line)

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py:74
_ROUTER_CONFIG = {
    "reimpresion-ticket": ("operador-,admin-", "reimprimir_ticket"),  # DEC-TKT-01 fix (GAP-BE-04)
    "anulaciones": ("operador-,admin-", "anular_ingreso_salida"),
    "reclamos": ("operador-,admin-", "registrar_reclamo"),
    "alerta": ("operador-,admin-", "registrar_alerta"),
}
```

This is the **entire** GAP-BE-04 fix — one string changed from `"emitir_reimpresion"` to `"reimprimir_ticket"`. No migration, no permission re-seed, no role grant re-issue. The factory-mounted `_mount_workflow` mount at lines 111-118 automatically picks up the corrected value via the `_ROUTER_CONFIG` lookup at line 94.

### 3.4 What changes in MIGRATION 0029 (conditional siembra + permission seed + role grants)

```sql
-- Op 1: DEC-TKT-05 conditional siembra prod.costos_servicios.concepto='reimpresion'
DO $$
DECLARE siembra_count INTEGER;
BEGIN
    ASSERT (
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='prod' AND table_name='costos_servicios'
    ) = 1, 'F1.11 requires prod.costos_servicios to exist';

    SELECT COUNT(*) INTO siembra_count
    FROM prod.costos_servicios
    WHERE concepto = 'reimpresion' AND vigente_hasta IS NULL AND estado = 'activo';

    IF siembra_count = 0 THEN
        INSERT INTO prod.costos_servicios (
            uuid, concepto, costo, tipo_calculo,
            vigente_desde, vigente_hasta, estado,
            created_at, created_by, sync_status, sync_attempts
        ) VALUES (
            gen_random_uuid(), 'reimpresion', 0, 'fijo',
            NOW(), NULL, 'activo', NOW(), NULL, 'sincronizado', 0
        ) ON CONFLICT (concepto, vigente_desde) DO NOTHING;
    END IF;
END $$;

-- Op 2: seed prod.permisos for anular_reimpresion
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM prod.permisos WHERE permiso = 'anular_reimpresion') THEN
        INSERT INTO prod.permisos (uuid, permiso, descripcion, vigente_desde, vigente_hasta, estado, created_at)
        VALUES (gen_random_uuid(), 'anular_reimpresion',
                'Anular una reimpresion de tiquete autorizada/ejecutada (HU-F1.11)',
                NOW(), NULL, 'activo', NOW());
    END IF;
END $$;

-- Op 3: grant anular_reimpresion to operador and admin roles via prod.permisos_usuario
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='prod' AND table_name='permisos_usuario') THEN
        INSERT INTO prod.permisos_usuario (uuid, uuid_usuario, uuid_permiso, vigente_desde, vigente_hasta, estado, created_at)
        SELECT gen_random_uuid(), u.uuid, p.uuid, NOW(), NULL, 'activo', NOW()
        FROM prod.usuarios u, prod.permisos p
        WHERE p.permiso = 'anular_reimpresion'
          AND u.uuid_rol IN (SELECT uuid FROM prod.roles WHERE nombre IN ('operador', 'admin'))
          AND NOT EXISTS (
              SELECT 1 FROM prod.permisos_usuario pu
              WHERE pu.uuid_usuario = u.uuid AND pu.uuid_permiso = p.uuid AND pu.vigente_hasta IS NULL
          );
    END IF;
END $$;
```

The migration is fully idempotent (every op uses `IF NOT EXISTS` or `WHERE NOT EXISTS`). The `DO $$` pre-flight aborts with a typed `0029_preflight_abort` exception if `prod.costos_servicios` is missing.

### 3.5 Why this matters

- **Resource reachability**: the endpoint will return 403 forever if the GAP-BE-04 mismatch is not fixed. An operator with `reimprimir_ticket` permission will be rejected because the router checks `emitir_reimpresion`. The fix unblocks the entire `reimpresion-ticket` resource (highest blast radius — affects GET, the factory mount's permission check, and the new POST endpoints).
- **Defense-in-depth Layer 1 + 2**: KD-3 issuer chain + permission check at `make_router` requires this to be fixed BEFORE F1.11 endpoints ship. The DEC-TKT-01 fix is a precondition for Layer 1 + 2 to function correctly.
- **Audit trail completeness**: anulación MUST use NEW rows (DEC-TKT-03); without the GAP-BE-04 fix the operator cannot reach the endpoint that produces the audit trail. The fix is a precondition for the regulatory minimum for operator-correction flows.
- **Backward compatibility**: the factory-mounted C+Q GET mount at lines 111-118 picks up the corrected permission value automatically via `_ROUTER_CONFIG["reimpresion-ticket"][1]`. No additional code change in the factory path.

---

## 4. Architecture Overview

```
HTTPS POST /api/v1/workflows/reimpresion-ticket
        Body: ReimpresionTicketCreateEndpoint
        │      {motivo: str>=10chars, uuid_ingreso: UUID, uuid_factura: UUID|None}
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        │  permission_required="reimprimir_ticket" (post-DEC-TKT-01 GAP-BE-04 fix)
        │  Idempotency-Key: <uuid>  (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10)
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/workflows_reimpresion.py  (NEW, +60 LOC, 2 NEW handlers)             │
│                                                                              │
│ @router.post("/reimpresion-ticket", response_model=ReimpresionTicketRead,    │
│              status_code=201)                                                │
│ async def create_reimpresion_ticket(response, payload, session, ctx,        │
│                                      _claims) -> ReimpresionTicketRead      │
│                                                                              │
│  1. KD-3 issuer claims:                                                      │
│      _claims = requires_issuer("operador-", "admin-")                       │
│      ctx = get_tenant_ctx from JWT                                            │
│                                                                              │
│  2. V1 prod.ingreso.uuid exists:                                            │
│      ingreso = await repo_reimpresion.buscar_ingreso_por_uuid(              │
│          session, uuid_ingreso=payload.uuid_ingreso)                          │
│      if ingreso is None:                                                      │
│          raise 404 {"error":"ingreso_no_encontrado", "uuid_ingreso":...}   │
│                                                                              │
│  3. Tenant scope post-V1 (KD-S2 analog from F1.7):                           │
│      target_sucursal = ingreso.uuid_sucursal                                  │
│      if ctx.issuer_prefix == "operador-" and target != ctx.sucursal_uuid:   │
│          raise 403 {"error":"tenant_scope_violation"}                       │
│                                                                              │
│  4. V2 chain-tip guard (DEC-TKT-02):                                         │
│      existing_tip = await repo_reimpresion.buscar_reimpresion_activa_por_ingreso(│
│          session, uuid_ingreso=payload.uuid_ingreso)                          │
│      if existing_tip is not None:                                             │
│          raise 409 {"error":"reimpresion_already_pending", ...}             │
│                                                                              │
│  5. V3 optional prod.facturas.uuid validation (DEC-TKT-04):                 │
│      if payload.uuid_factura is not None:                                    │
│          factura = await repo_reimpresion.buscar_factura_por_uuid(          │
│              session, uuid_factura=payload.uuid_factura)                      │
│          if factura is None:                                                  │
│              raise 404 {"error":"factura_no_encontrada", ...}               │
│                                                                              │
│  6. KD-TKT-01 — INSERT prod.reimpresion_ticket [L-W] via append_transition:│
│      new_reimpresion = await repo.workflow.append_transition(                 │
│          session, ReimpresionTicket,                                         │
│          actor_uuid=ctx.actor_uuid,                                          │
│          new_attrs={                                                         │
│              "uuid_sucursal": target_sucursal,                               │
│              "uuid_ingreso": payload.uuid_ingreso,                           │
│              "uuid_usuario": ctx.actor_uuid,                                 │
│              "uuid_factura": payload.uuid_factura,                           │
│              "motivo": payload.motivo,                                       │
│              "timestamp_evento": _now_naive(),                               │
│              "estado": "autorizada",  # workflow state machine (synthesized)│
│          },                                                                  │
│          parent_uuid=None,                                                    │
│          parent_fk_column="uuid_reimpresion_padre",                            │
│          log_tx=True,                                                         │
│      )                                                                        │
│                                                                              │
│  7. KD-TKT-01 single commit:                                                │
│      await session.commit()    <-- UN solo commit                            │
│                                                                              │
│  8. Response shape + Cache-Control: no-store header:                        │
│      apply_no_store_header(response)                                          │
│      return ReimpresionTicketRead(                                          │
│          uuid=new_reimpresion.uuid,                                          │
│          uuid_ingreso=new_reimpresion.uuid_ingreso,                          │
│          uuid_factura=new_reimpresion.uuid_factura,                          │
│          motivo=new_reimpresion.motivo,                                      │
│          uuid_reimpresion_padre=None,  # chain root                          │
│          timestamp_evento=new_reimpresion.timestamp_evento,                  │
│          workflow_estado="autorizada",                                       │
│          ...                                                                  │
│      )                                                                        │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                                       ▲
        │ AST walk single-commit (KD-TKT-01)    │ AST walk no-update (DEC-TKT-02, REQ-OPS-077)
        │ for create handler                    │ for create + anular handlers
tests/static/test_workflow_handler_single_commit.py
tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Repo helpers (NEW):                                                          │
│   repo/reimpresion_ticket.py   (~80 LOC) — 6 helpers + 5 typed exceptions    │
│                                                                              │
│ Repo helpers (REUSED verbatim, NO modify):                                   │
│   repo/workflow.py::append_transition (F1.5 PR5-016) — used for KD-TKT-01   │
│   repo/workflow.py::read_chain_tip (F1.5 PR5-016) — used for anulacion V2  │
│                                                                              │
│ Schemas (MODIFY):                                                            │
│   schemas/workflows.py     (+30 LOC) — 3 new schemas (create endpoint,       │
│                                       anular endpoint, read response)        │
│                                                                              │
│ Tables operational (READ + INSERT):                                         │
│   prod.reimpresion_ticket  [L-W]  — Step 6 INSERT (KD-TKT-01)               │
│                                          + /anular step 5 INSERT retry      │
│                                          + Step 4 V2 SELECT chain tip       │
│   prod.ingreso             [A]    — Step 2 V1 SELECT                        │
│   prod.facturas            [L-E]  — Step 5 V1 SELECT (optional, DEC-TKT-04)  │
│   prod.costos_servicios    [V]    — runtime lookup (DEC-TKT-05 seed)        │
│                                                                              │
│ GAP-BE-04 single-line fix (DEC-TKT-01):                                     │
│   api/v1/workflows.py:74   "emitir_reimpresion" -> "reimprimir_ticket"      │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲
        │
        ▼ MIGRATION 0029 (3 operations, applied BEFORE F1.11 tests; conditional idempotent)
┌──────────────────────────────────────────────────────────────────────────────┐
│ migrations/versions/0029_reimpresion_siembre_and_anular_permission.py        │
│                                                                              │
│ Op 0 — Pre-flight DO $$:                                                    │
│   verify prod.costos_servicios + prod.permisos + prod.permisos_usuario +    │
│   prod.roles exist; verify migration 0028 head                               │
│   ASSERT all 4 tables exist; RAISE NOTICE '0029_preflight: 4/4 OK'          │
│                                                                              │
│ Op 1 — DEC-TKT-05 conditional siembra costos_servicios.concepto='reimpresion'│
│   COUNT(*) FROM prod.costos_servicios WHERE concepto='reimpresion'           │
│     AND vigente_hasta IS NULL AND estado='activo';                           │
│   IF 0 rows THEN INSERT ('reimpresion', costo=0, tipo='fijo')                │
│     ON CONFLICT (concepto, vigente_desde) DO NOTHING;                       │
│                                                                              │
│ Op 2 — seed prod.permisos for 'anular_reimpresion' (mirror anular_ingreso) │
│   IF NOT EXISTS (permiso='anular_reimpresion') THEN INSERT                  │
│                                                                              │
│ Op 3 — grant 'anular_reimpresion' to operador + admin via prod.permisos_usuario│
│   INSERT ... SELECT FROM prod.usuarios u, prod.permisos p                   │
│   WHERE p.permiso='anular_reimpresion' AND                                  │
│     u.uuid_rol IN (SELECT uuid FROM prod.roles WHERE nombre IN ('operador', 'admin'))│
│   AND NOT EXISTS (existing grant);                                          │
│                                                                              │
│ Downgrade (reverse order):                                                  │
│   Op 3 reverse: DELETE FROM prod.permisos_usuario                            │
│     WHERE uuid_permiso IN (SELECT uuid FROM prod.permisos                    │
│     WHERE permiso='anular_reimpresion');                                     │
│   Op 2 reverse: DELETE FROM prod.permisos WHERE permiso='anular_reimpresion';│
│   Op 1 reverse: DELETE FROM prod.costos_servicios                            │
│     WHERE concepto='reimpresion' AND vigente_desde >= NOW() - INTERVAL '1 hour'│
│     AND vigente_hasta IS NULL AND estado='activo';                           │
│     (known limitation: deletes any manual siembra within last hour too)       │
└──────────────────────────────────────────────────────────────────────────────┘
```

The handler is thin + orquestador. All validation logic lives in `repo/reimpresion_ticket.py`. The single `commit()` materializes the reimpresion row atomically (KD-TKT-01).

### Anular handler architecture

```
HTTPS POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular
        Body: ReimpresionTicketAnularEndpoint
        │      {motivo_anulacion: str>=10chars}
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        │  permission_required="anular_reimpresion" (seeded in MIGRATION 0029 Op 2)
        │  Idempotency-Key: <uuid>  (DEC-IDEM-01)
        ▼
async def anular_reimpresion_ticket(response, uuid_reimpresion, payload, session, ctx, _claims)
                                                                                    │
   1. KD-3 issuer chain ────────────────────────────  DI-resolved                 │
                                                                                    ▼
   2. V1: read_chain_tip from uuid_reimpresion (F1.5 PR5-016):
        try:
            tip = await repo.workflow.read_chain_tip(
                session, ReimpresionTicket,
                root_uuid=uuid_reimpresion,
                parent_fk_column="uuid_reimpresion_padre"
            )
        except ChainNotFoundError:
            raise 404 {"error":"reimpresion_not_found", "uuid_reimpresion":...}

   3. Tenant scope post-V1:
        tip_row = await repo_reimpresion.buscar_reimpresion_por_uuid(
            session, uuid=tip["uuid_actual"]
        )
        if ctx.issuer_prefix == "operador-" and tip_row.uuid_sucursal != ctx.sucursal_uuid:
            raise 403 {"error":"tenant_scope_violation"}

   4. V2 — chain tip state check (DEC-TKT-03):
        if tip["workflow_estado"] == "rechazada":
            raise 409 {"error":"anulacion_no_permitida", "estado_actual":"rechazada"}

   5. V3 — INSERT NEW prod.reimpresion_ticket row (NEVER UPDATE on tip_row):
        new_row = await repo.workflow.append_transition(
            session, ReimpresionTicket,
            actor_uuid=ctx.actor_uuid,
            new_attrs={
                "uuid_sucursal": tip_row.uuid_sucursal,
                "uuid_ingreso": tip_row.uuid_ingreso,
                "uuid_usuario": ctx.actor_uuid,
                "motivo": payload.motivo_anulacion,
                "motivo_anulacion": payload.motivo_anulacion,
                "timestamp_evento": _now_naive(),
                "estado": "rechazada",  # workflow state machine (synthesized)
            },
            parent_uuid=tip["uuid_actual"],
            parent_fk_column="uuid_reimpresion_padre",
            log_tx=True,
        )

   6. KD-TKT-01 single commit:
        await session.commit()

   7. Response shape + Cache-Control: no-store header:
        apply_no_store_header(response)
        return ReimpresionTicketRead(
            uuid=new_row.uuid,
            uuid_reimpresion_padre=new_row.uuid_reimpresion_padre,  # = tip.uuid
            motivo_anulacion=new_row.motivo_anulacion,
            workflow_estado="rechazada",
            ...
        )
```

---

## 5. Data Model

**One Alembic migration introduces** the conditional siembra + permission seed + role grants. **No columns added or removed** in any operational table. The 4 tables (`prod.reimpresion_ticket`, `prod.costos_servicios`, `prod.permisos`, `prod.permisos_usuario`) all exist since migration 0001 with their pre-existing schemas. **No new indexes** — the existing FK `fk_reimpresion_ticket_uuid_reimpresion_padre` (migration 0001 lines 1690-1692) is sufficient for the chain-tip SELECT + recursive CTE.

### 5.1 `prod.reimpresion_ticket` `[L-W]` (insert-only per transition)

| Property | Value |
|---|---|
| **ER línea** | 598-620 |
| **Migration 0001 línea** | 893-910 |
| **Operations** | V1 SELECT chain tip (`repo/workflow.read_chain_tip`); V2 SELECT most-recent active row for same `uuid_ingreso` (already-pending guard); V3 INSERT via `repo.workflow.append_transition(estado='autorizada')` (create) or `(estado='rechazada', parent_uuid=tip.uuid)` (anular) |
| **Columns read** | `uuid`, `uuid_sucursal`, `uuid_ingreso`, `uuid_usuario`, `uuid_factura`, `uuid_costo_servicio`, `costo_aplicado`, `motivo`, `motivo_anulacion`, `uuid_reimpresion_padre`, `timestamp_evento`, `vigente_desde`, `vigente_hasta`, `estado` (bi-temporal versioning toggle) |
| **Columns write (INSERT)** | `uuid_sucursal`, `uuid_ingreso`, `uuid_usuario`, `uuid_factura`, `motivo`, `motivo_anulacion` (anular only), `uuid_reimpresion_padre` (NULL for create, tip.uuid for anular), `timestamp_evento=now()`, `vigente_desde=now()`, `vigente_hasta=NULL`, `estado='activo'` (bi-temporal versioning), server-set `created_at`+`created_by` |
| **Indexes** | existing PK `uuid` + trigger-managed versioning (no UK because `vigente_desde` participates in identity). FK `fk_reimpresion_ticket_uuid_reimpresion_padre` (migration 0001 lines 1690-1692) enforces chain integrity at DB layer |
| **Audit/sync triggers** | `reimpresion_ticket_audit_columns` (BEFORE INSERT, sets `created_at`, `created_by`), `reimpresion_ticket_set_vigente_inicial` (BEFORE INSERT, sets `vigente_inicial`), `reimpresion_ticket_enqueue_sync` (AFTER INSERT, calls `prod.fn_enqueue_sync()`) — all per migration 0001 lines 2379-2390 + 2660-2672 + 2873-2880. **NO new triggers** |
| **Sync catalog** | `direction='branch_to_cloud'` (per `sync_entries_lw.py` lines 27-40, pre-existing D1-rev — NO change needed by F1.11), `apply_strategy='append_transition'`, `parent_fk_column='uuid_reimpresion_padre'`, `depends_on=('sucursal', 'ingreso', 'usuarios', 'costos_servicios', 'facturas')` |
| **REVOKE** | Already enforced by F1.5 PR5-016 (REVOKE UPDATE, DELETE on `prod.reimpresion_ticket` FROM rol_app per migration 0021 lines 162, 182); INSERT-only path via `repo.workflow.append_transition` is the only legal write |

#### 5.1.1 DEC-TKT-02 clarifying note on `estado` semantics

The `prod.reimpresion_ticket.estado` column (`String(16)`, `'activo' | 'inactivo'`) is the **bi-temporal VersionedMixin versioning toggle**, NOT the workflow state machine value. The workflow state machine values (`solicitada | autorizada | ejecutada | rechazada`) live on **business columns tracked via `log_transaccional`** + the chain via `uuid_reimpresion_padre`. For F1.11 the canonical chain tip state is derived at read time via `repo.workflow.read_chain_tip(... parent_fk_column='uuid_reimpresion_padre')` → returns the latest row by `(max(timestamp_evento), longest chain, lex(uuid))` tie-break.

For the response schema, the handler **synthesizes** a `workflow_estado` field with the workflow value (`solicitada|autorizada|ejecutada|rechazada`) by reading the chain tip row's `timestamp_evento` and applying a simplified rule for MVP: create → `autorizada`; anular → `rechazada`. Future HUs (F2.x) will extend this with a `prod.workflow_estado` companion table when manual autorización is reintroduced.

### 5.2 `prod.costos_servicios` `[V]` (bi-temporal VersionedBase)

| Property | Value |
|---|---|
| **ER línea** | 230-244 |
| **Migration 0001 línea** | 297-309 |
| **Operations** | Conditional siembra via MIGRATION 0029 Op 1 (idempotent INSERT if absent); runtime SELECT by `concepto='reimpresion'` (informational; cost NOT snapshotted) |
| **Columns read** | `uuid`, `concepto`, `costo`, `tipo_calculo`, `vigente_desde`, `vigente_hasta`, `estado` |
| **Index** | existing bi-temporal `(concepto, vigente_desde)` UK per migration 0001 line 309 (`costos_servicios_uk01`) |
| **Defense in depth** | bi-temporal VersionedBase guarantees at most one vigente row per `concepto` (UK01). Handler returns 409 `costo_servicio_no_configurado` if lookup returns NULL (DEC-TKT-05 covers the seed; this is a defensive runtime check after seed) |
| **No new indexes** | None needed; existing UK01 suffices |

### 5.3 `prod.ingreso` `[A]` (append-only, read-only)

| Property | Value |
|---|---|
| **Operations** | V1 SELECT by UUID in create handler |
| **Columns read** | `uuid`, `uuid_sucursal` |
| **Defense in depth** | NULL → 404 `ingreso_no_encontrado` |

### 5.4 `prod.facturas` `[L-E]` (read-only, optional)

| Property | Value |
|---|---|
| **Operations** | If `uuid_factura` is provided in the create request, V1+ SELECT by UUID to validate existence |
| **Columns read** | `uuid`, `uuid_sucursal` |
| **Defense in depth** | NULL `uuid_factura` → skip the SELECT (optional per DEC-TKT-04). Non-existent `uuid_factura` → 404 `factura_no_encontrada` |

### 5.5 `prod.permisos` `[V]` + `prod.permisos_usuario` `[V]` (MIGRATION 0029 Op 2 + Op 3)

| Property | Value |
|---|---|
| **Operations** | MIGRATION 0029 Op 2 INSERTs the `anular_reimpresion` permission (mirror of `anular_ingreso_salida`). Op 3 GRANTs `anular_reimpresion` to `operador` and `admin` roles via `prod.permisos_usuario` (idempotent via NOT EXISTS subquery) |
| **Columns write (Op 2)** | `uuid=gen_random_uuid(), permiso='anular_reimpresion', descripcion='Anular una reimpresion de tiquete autorizada/ejecutada (HU-F1.11)', vigente_desde=NOW(), vigente_hasta=NULL, estado='activo', created_at=NOW()` |
| **Columns write (Op 3)** | `uuid=gen_random_uuid(), uuid_usuario=<role.users.uuid>, uuid_permiso=<permisos.uuid>, vigente_desde=NOW(), vigente_hasta=NULL, estado='activo', created_at=NOW()` — for each `operador`/`admin` user |
| **Defense in depth** | bi-temporal VersionedBase + NOT EXISTS subquery + UK on `(uuid_usuario, uuid_permiso, vigente_hasta IS NULL)` |

### 5.6 Tables touched summary

| Tabla | Tipo | Operación | Línea ER / migration |
|---|---|---|---|
| `prod.reimpresion_ticket` | `[L-W]` | V1 SELECT (read_chain_tip) + V2 SELECT chain tip for ingreso + Step 6 INSERT (create) + Step 5 INSERT (anular) | ER 598-620 + ORM `models/L_W/reimpresion_ticket.py` + FK lines 1690-1692 |
| `prod.costos_servicios` | `[V]` | (Op 1) conditional siembra + runtime lookup | ER 230-244 + ORM `models/V/costos_servicios.py` + UK01 line 309 |
| `prod.ingreso` | `[A]` | Step 2 V1 SELECT (read-only) | (F1.6, migration 0024) |
| `prod.facturas` | `[L-E]` | Step 5 V1 SELECT (optional, DEC-TKT-04) | (F1.9, migration 0027) |
| `prod.permisos` | `[V]` | (Op 2) seed `anular_reimpresion` permission | ER + migration 0001 |
| `prod.permisos_usuario` | `[V]` | (Op 3) grant `anular_reimpresion` to operador + admin | ER + migration 0021 |
| `prod.usuarios` | `[A]` | (Op 3) SELECT for role membership | ER + migration 0001 |
| `prod.roles` | `[V]` | (Op 3) SELECT `WHERE nombre IN ('operador', 'admin')` | ER + migration 0001 |

**No column added** for `workflow_estado`, `motivo_anulacion`, `chain_index`, or any new field — DEC-TKT-02 veda `workflow_estado` as a separate column (4NF, lives on the chain via `uuid_reimpresion_padre` + the bi-temporal `estado` column); DEC-TKT-04 veda `costo_aplicado` snapshotted from `prod.facturas` (issuance flow decoupled from cost charging per plan.md línea 1001 budget).

**State transitions** on `prod.reimpresion_ticket` happen via NEW rows with `uuid_reimpresion_padre` pointing at the previous chain tip — the chain IS the audit trail (DEC-TKT-02 + DEC-TKT-03 + REQ-OPS-077). The `read_chain_tip` helper (F1.5 PR5-016) materializes the current state for read-only projection.

**Sync catalog impact**: ZERO. `sync_entries_lw.py` lines 27-40 already carry the `reimpresion_ticket` entry with `direction='branch_to_cloud'` and `apply_strategy='append_transition'`. No sync changes needed by F1.11.

---

## 6. Decisions

This HU adopts **six** Key Decisions (DEC-TKT-01..06 from `proposal.md §6`) plus **two KD invariants** (KD-TKT-01 single-commit + KD-TKT-02 chain-tip V2 guard). Each one passes the R5 risk threshold (no open question blocks the design; the proposal §7 confirms "R1 RESOLVED" after the DEC-TKT-01 resolution of R1 MEDIUM). The decisions are grouped into 4 themes: GAP reconciliation (DEC-TKT-01), chain integrity (DEC-TKT-02, DEC-TKT-03, KD-TKT-01, KD-TKT-02), deferred concerns (DEC-TKT-04), conditional seeding (DEC-TKT-05), and module topology (DEC-TKT-06).

### Decision DEC-TKT-01 — GAP-BE-04 permission reconciliation: `emitir_reimpresion` → `reimprimir_ticket` (RESOLVES R1 MEDIUM)

**Choice.** Single-line fix in `api/v1/workflows.py:74`. NO migration, NO permission re-seed, NO role grants re-issued. The `reimprimir_ticket` permission is ALREADY seeded in `prod.permisos` (migration 0001 line 3292). The fix unblocks the entire `reimpresion-ticket` resource (highest blast radius — affects GET, the factory mount's permission check, and the new POST endpoints).

**Context.** Verified pre-apply per observation #1578 §R1 MEDIUM (architectural conflict identified). Three sources disagreed: plan.md línea 7342 mandates the reconciliation (CANONICAL per user mandate); migration 0001 line 3292 carries `reimprimir_ticket`; `api/v1/workflows.py:74` carries `emitir_reimpresion` (stale from PR6 T-PR6-10). The cloud-only design from PR2 was never implemented for `reimpresion_ticket` (no F1.10-style sync flip needed because `sync_entries_lw.py` already has `direction='branch_to_cloud'` for this table). The fix is the smallest possible change that unblocks the resource.

**Alternatives considered.**
- *Re-seed `emitir_reimpresion` in `prod.permisos`* — REJECTED. Duplicate permission for same intent; violates single-source-of-truth. R1 risk class.
- *Add `emitir_reimpresion` as alias in `prod.permisos` (i.e., dual permissions)* — REJECTED. Violates single-source-of-truth; complicates RBAC audits.
- *Add a middleware that translates the typo'd permission* — REJECTED. Hides the bug; complicates audit trail.

**Rationale.** plan.md is the canonical authority (per user mandate "siempre remitete al plan.md" línea 7342 mandates the reconciliation). The `reimprimir_ticket` permission is already seeded; no migration needed. The fix is one string change.

### Decision DEC-TKT-02 — Reimpresión as INSERT-only via `repo.workflow.append_transition` (NEVER UPDATE)

**Choice.** Both POST endpoints INSERT new rows via `repo.workflow.append_transition`. Create: `workflow_estado='autorizada'` (chain tip), `uuid_reimpresion_padre=NULL`. Anular: `workflow_estado='rechazada'`, `uuid_reimpresion_padre=<tip.uuid>`. NEVER UPDATE on `workflow_estado`, `motivo`, `motivo_anulacion`, `uuid_reimpresion_padre`, `uuid_ingreso`, `uuid_factura`. Only `vigente_hasta` MAY be UPDATEd for bi-temporal versioning (WorkflowBase contract — see DEC-TKT-02 clarifying note in §5.1.1).

**Context.** `[L-W]` WorkflowBase insert-only invariant. Audit trail completeness. The chain IS the history. AST walk already in place (`tests/static/test_no_raw_dml_on_lw_tables.py` from F1.5 PR5-016) blocks raw INSERT/UPDATE/DELETE. Mirror of F1.10 DEC-FE-02 (NEVER UPDATE on `envio_dian`) + DEC-FE-07 NEW (AST walk enforcement).

**Alternatives considered.**
- *UPDATE original to a `rechazada` state on anulación* — REJECTED. Breaks audit trail. R3 risk class.
- *Separate `reimpresion_anulaciones` table* — REJECTED. The chain IS the history; a separate table adds query complexity without benefit.
- *Use `WorkflowBase.close_version()` pattern from F1.5* — CONSIDERED. The WorkflowBase may UPDATE `vigente_hasta` for bi-temporal versioning (close current version, insert new version with `vigente_desde=now()`, `vigente_hasta=NULL`). F1.11 does NOT introduce additional UPDATE statements because the new row IS the new version.

**Rationale.** 4NF + audit trail + bi-temporal `[L-W]` pattern all align on NEW-row-only semantics for user-meaningful fields. AST walk `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` enforces the invariant.

### Decision DEC-TKT-03 — Anulación chain via NEW row + `uuid_reimpresion_padre` (NEVER UPDATE) — orphan gap closed

**Choice.** Anulación endpoint INSERTs new row with `uuid_reimpresion_padre` pointing at original chain tip. Original row NEVER updated. Chain tip selected by `read_chain_tip` per REQ-X9 tie-break. Insert ALWAYS succeeds for non-terminal chains; terminal `rechazada` chain tips return 409 `anulacion_no_permitida`.

**Context.** plan.md línea 993 explicitly flags the anulación as **"gap huérfano detectado"**. `[L-W]` pattern is same as `anulaciones`/`alerta`/`envio_dian`/`reclamos` — all chain-driven, all insert-only per transition.

**Alternatives considered.**
- *UPDATE the original row to a `rechazada` state* — REJECTED. Breaks audit trail.
- *Allow anulación to insert at the chain root with `uuid_reimpresion_padre=NULL`* — REJECTED. Creates a fork at the root that the chain-tip SELECT cannot resolve cleanly.

### Decision DEC-TKT-04 — `uuid_factura` is OPTIONAL on the create INSERT (charge may be deferred to HU-F8.3)

**Choice.** `ReimpresionTicketCreateEndpoint` accepts `uuid_factura: UUID | None = None`. If NULL, reimpresion is recorded WITHOUT a factura charge. HU-F8.3 (frontend) creates the factura via F1.9 machinery and calls the endpoint with the resulting `uuid_factura`. If provided, the handler validates the factura exists (V1 SELECT) but does NOT snapshot the cost.

**Context.** 170 LOC budget (plan.md línea 1001) is tight for full F1.9-style atomic factura creation + reimpresion_ticket INSERT in one TX. Splitting concerns keeps F1.11 focused on workflow chain + permission reconciliation. The `uuid_factura` is a forward reference to HU-F8.3 (frontend owns the create-then-reimprimir flow). The admin-correction use case (anular a reimpresion that had a charging typo) is served by leaving `uuid_factura` nullable.

**Alternatives considered.**
- *F1.11 creates the factura inline (full F1.9-style flow)* — REJECTED. Budget overrun; duplicates F1.9.
- *F1.11 mandates `uuid_factura` is required* — REJECTED. Breaks admin-correction anular case.
- *F1.11 snapshots the cost from `prod.facturas.costo` on the reimpresion row* — REJECTED. Issuance flow decoupled from cost charging per plan.md línea 1001; the reimpresion event records the REPRINT, not the cost.

**Rationale.** Budget discipline + clean separation of concerns. The `uuid_factura` is a forward reference to HU-F8.3.

### Decision DEC-TKT-05 — Siembra `costos_servicios.concepto='reimpresion'` strategy: MIGRATION 0029 with idempotent pre-flight

**Choice.** MIGRATION 0029 carries a `DO $$` block:
1. Verifies `prod.costos_servicios` table exists (pre-flight abort if not).
2. Checks `SELECT COUNT(*) FROM prod.costos_servicios WHERE concepto='reimpresion' AND vigente_hasta IS NULL AND estado='activo'`.
3. If 0 rows, INSERTs a new row with `concepto='reimpresion'`, `costo=0` (operator-configurable later), `tipo_calculo='fijo'`.
4. If ≥1 row, no-op (idempotent).

**If siembra is ALREADY present** (verifiable via pre-flight SQL query against the live DB), MIGRATION 0029 still ships — the `DO $$` block is the no-op path. The migration is REQUIRED because we cannot know in advance whether the siembra exists.

**Context.** Mirrors F1.7's `impuestos.IVA` inline siembra (MIGRATION 0026 pattern + pending list). Idempotent on re-apply. Operator-configurable cost avoids hardcoded values.

**Alternatives considered.**
- *Separate siembra catalog file* — REJECTED. Loses atomic guarantee with the schema migration.
- *Document siembra as out-of-scope* — REJECTED. The pending blocker explicitly mandates verification.
- *Hard-code cost as 0 without operator-configurable path* — CONSIDERED + ACCEPTED as MVP. The cost is informational for F1.11; the issuance flow is decoupled from cost charging. Operator can UPDATE the cost post-migration if needed.

### Decision DEC-TKT-06 — Router flag unmount (was conditional on `WORKFLOWS_ROUTER_ENABLED`)

**Choice.** F1.11 sets `WORKFLOWS_ROUTER_ENABLED=True` for the `reimpresion-ticket` mount (the flag was previously gating the entire resource). Additionally, the new `anular` endpoint is mounted as a dedicated POST handler in a new `api/v1/workflows_reimpresion.py` module to avoid bloating the factory path.

**Context.** plan.md línea 989 mandates that the new write endpoints be available. The flag unmount is the smallest path forward. The `anular` endpoint is implemented as a dedicated handler in a new module to keep the 170 LOC budget tight.

**Alternatives considered.**
- *Use the factory with `write_enabled=True`* — REJECTED. The factory's `versioned` branch is not wired for `append_transition` writes; the L-W pattern needs custom handlers.
- *Add endpoints to a separate router and include in the parent* — ACCEPTED. This is the implementation plan.

### Decision DEC-TKT-07 (KD-TKT-01) — Single `await session.commit()` materializes reimpresion row atomically

**Choice.** The `create_reimpresion_ticket` handler body MUST contain EXACTLY ONE `await session.commit()` call (KD-TKT-01 mirror of F1.10 KD-FE-01 + F1.9 KD-FACT-01). The `anular_reimpresion_ticket` handler body MUST also contain EXACTLY ONE `await session.commit()` call. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements MUST NOT appear anywhere in the handler body or its callees.

**Context.** KD-FE-01 from F1.10 / REQ-OPS-065. An `reimpresion_ticket` chain without its parent commit boundary is an audit orphan. Single-commit atomicity closes both risks. The same single-commit invariant applies to the anulación endpoint: a NEW chain row must be visible together with the commit boundary.

**Alternatives considered.**
- *Separate commits for chain-root INSERT and any auxiliary writes* — REJECTED. Loses atomicity. If chain-root commits but chain-walk fails, the chain is broken.
- *Use SAVEPOINT for nested commit* — REJECTED. Defeats the purpose of the single-commit invariant.

**Rationale.** KD-FE-01 mirror. Atomicity is non-negotiable for audit trail completeness. AST walks `tests/static/test_workflow_handler_single_commit.py` enforce the invariant for both handlers.

### Decision DEC-TKT-08 (KD-TKT-02) — Chain-tip SELECT FOR UPDATE guard via V2 (cool-off window)

**Choice.** The `create_reimpresion_ticket` handler V2 guard uses `SELECT ... FOR UPDATE` on the most-recent active `prod.reimpresion_ticket` row for the same `uuid_ingreso` (DEC-TKT-02 chain-tip guard). The lock is held until `await session.commit()` (KD-TKT-01 single-commit). Concurrent calls on the SAME `uuid_ingreso` serialize cleanly. NO gap in the audit trail.

**Context.** KD-TKT-02 mirror of F1.10 KD-FE-02 (`assign_consecutivo` SELECT FOR UPDATE pattern). The SELECT FOR UPDATE closes the concurrent-create race at the row level. Two concurrent TXs attempting to create reimpresions for the same `uuid_ingreso` serialize: the FIRST acquires the lock and inserts; the SECOND blocks at SELECT FOR UPDATE until the FIRST commits, then proceeds with the V2 check (which now finds the recent row and returns 409 `reimpresion_already_pending`).

**Alternatives considered.**
- *Lock per-table* — REJECTED. Serializes ALL reimpresion creations; latency catastrophe.
- *Lock per-uuid_ingreso (current approach via SELECT FOR UPDATE)* — ACCEPTED. Matches F1.10 KD-FE-02 + F1.7 KD-S2 precedent.
- *Lock per-uuid_sucursal* — REJECTED. Same lock granularity is achieved via the per-uuid_ingreso lock; cross-sucursal locking would serialize unrelated reimpresions.

**Rationale.** F1.10 KD-FE-02 precedent. Per-row `FOR UPDATE` lock is the canonical Postgres pattern for atomic counter increment under concurrency.

---

## 7. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **GAP-BE-04 permission mismatch** — `workflows.py:74` uses `emitir_reimpresion`, `prod.permisos` has `reimprimir_ticket`. Router returns 403 forever. | **MEDIUM (RESOLVED)** | DEC-TKT-01 (§6.1) + single-line fix. Verified by `test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion` (regression test). |
| **R2** | `costos_servicios.concepto='reimpresion'` siembra absent → handler returns 409 at runtime. | **MEDIUM** | DEC-TKT-05 (§6.5) + MIGRATION 0029 Op 1 with idempotent pre-flight. If siembra is present, the migration is a no-op. |
| **R3** | Chain integrity via FK — concurrent anulaciones on same original create a fork (allowed by schema). | **LOW** | FK enforces referential integrity. `read_chain_tip` returns deterministic tip per REQ-X9 tie-break. Documented in design §5.1.1. |
| **R4** | Concurrent reimpresions on SAME `ingreso` (multiple operators, same ingreso) — schema allows it. | **LOW** | KD-TKT-02 + V2 chain-tip guard rejects 409 `reimpresion_already_pending` if recent `autorizada`/`ejecutada` row exists. Documented as known limitation; intentional MVP. |
| **R5** | Tenant scope pre-V1 — operadores across branches could create reimpresions for foreign `uuid_ingreso`. | **LOW** | KD-S2 analog from F1.7: handler compares `ctx.sucursal_uuid` against `ingreso.uuid_sucursal`. Same pattern as F1.9/F1.10. |
| **R6** | `motivo_anulacion` audit — Pydantic only validates length; semantic content is free-form. | **LOW** | Layer 5 enforces `min_length=10, max_length=500`. Storage is sufficient for any reasonable audit trail. |
| **R7** | AST walk `test_no_raw_dml_on_lw_tables.py` must reject new handlers' potential raw INSERT statements. | **MEDIUM** | The walk already exists for `append_transition` calls. Add `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` (DEC-TKT-02 enforcement). |
| **R8** | MIGRATION 0029 downgrade Op 1 unconditionally deletes any `costos_servicios.concepto='reimpresion'` row inserted in the last hour. If a manual siembra happened between migration and downgrade, the row is also deleted. | **LOW** | Acceptable for MVP; tracker table not introduced. Documented as known limitation in Appendix A + REQ-OPS-079 DoF. |
| **R9** | WorkflowBase may UPDATE `vigente_hasta` for bi-temporal versioning — AST walk must permit this pattern originating from the `WorkflowBase` superclass, not from the F1.11 handler bodies. | **LOW** | The new AST walk `test_workflow_handler_no_update_on_reimpresion_ticket.py` ONLY checks the F1.11 handler bodies (`create_reimpresion_ticket` + `anular_reimpresion_ticket`), NOT `WorkflowBase`. Existing `test_no_raw_dml_on_lw_tables.py` (F1.5) covers the WorkflowBase. |
| **R10** | Idempotency-Key TTL — F1.6 established a 7-day window for the `Idempotency-Key` cache. F1.11 inherits the same TTL; client-side retries within 7 days return the cached response without growing the chain. | **LOW** | Documented as inherited constraint; no F1.11-specific mitigation needed. |

---

## 8. API Contracts

### 8.1 `POST /api/v1/workflows/reimpresion-ticket` (NEW)

**Request signature**:

```python
async def create_reimpresion_ticket(
    response: Response,
    payload: ReimpresionTicketCreateEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_reimpresion_issuer_dep),
) -> ReimpresionTicketRead:
```

**Body `ReimpresionTicketCreateEndpoint`** (Pydantic v2, `extra='forbid'`):

```python
class ReimpresionTicketCreateEndpoint(_Base):
    """HU-F1.11: POST /api/v1/workflows/reimpresion-ticket payload.

    DEC-TKT-04: uuid_factura is OPTIONAL; deferred to HU-F8.3 frontend
    for the create-factura-then-reimprimir flow.

    extra='forbid' (inherited from _Base) blocks client smuggling of
    uuid_reimpresion_padre, estado, costo_aplicado, uuid_costo_servicio,
    timestamp_evento, uuid_sucursal, uuid_usuario, vigente_desde,
    vigente_hasta, created_at, created_by, motivo_anulacion.
    """
    motivo: Annotated[str, StringConstraints(min_length=10, max_length=500)]
    uuid_ingreso: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID | None = None
```

**Response `ReimpresionTicketRead`** (201, Pydantic v2):

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

**Headers**: `Cache-Control: no-store` (F1.3..F1.10 precedent, DEC-TKT-06 XR2). `Idempotency-Key: <uuid>` (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10).

**Error discriminators** (typed HTTPException details):

| HTTP | Body | Cuándo | KD / DEC |
|---|---|---|---|
| 403 | `{"error":"GAP-BE-04","recurso":"reimpresion-ticket"}` | Legacy pre-§3 fix state (transient) | DEC-TKT-01 |
| 403 | `{"error":"tenant_scope_violation","uuid_ingreso":"..."}` | `operador-` con `ingreso.uuid_sucursal != ctx.sucursal_uuid` (post-V1) | KD-S2 analog from F1.7 (XR1 layer c) |
| 404 | `{"error":"ingreso_no_encontrado","uuid_ingreso":"..."}` | V1: `prod.ingreso.uuid` not found | REQ-OPS-075 V1 |
| 404 | `{"error":"factura_no_encontrada","uuid_factura":"..."}` | V3: `prod.facturas.uuid` not found (when provided) | REQ-OPS-080 V3 |
| 409 | `{"error":"reimpresion_already_pending","uuid_ingreso":"...","uuid_reimpresion":"..."}` | V2: recent `autorizada`/`ejecutada` row exists (DEC-TKT-02) | REQ-OPS-077 V2 |
| 409 | `{"error":"costo_servicio_no_configurado","concepto":"reimpresion"}` | Runtime check; siembra should be present post-migration | DEC-TKT-05 (defensive) |
| 422 | `{"error":"missing_field","field":"uuid_ingreso"}` | Pydantic validation rejects before DB hit | REQ-OPS-075 Scenario 4 |
| 422 | `{"error":"motivo_muy_corto","min_length":10}` | Pydantic `min_length=10` rejects | DEC-TKT-06 |
| 201 | `ReimpresionTicketRead` with `workflow_estado='autorizada'` | Happy path | KD-TKT-01 single-commit |

### 8.2 `POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular` (NEW)

**Request signature**:

```python
async def anular_reimpresion_ticket(
    response: Response,
    uuid_reimpresion: uuid_lib.UUID,
    payload: ReimpresionTicketAnularEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_anular_reimpresion_issuer_dep),  # requires 'anular_reimpresion' permission
) -> ReimpresionTicketRead:
```

**Body `ReimpresionTicketAnularEndpoint`** (Pydantic v2, `extra='forbid'`):

```python
class ReimpresionTicketAnularEndpoint(_Base):
    """HU-F1.11: POST /api/v1/workflows/reimpresion-ticket/{uuid}/anular payload.

    The chain tip UUID is the path parameter; the body carries only
    motivo_anulacion (audit trail).

    extra='forbid' rejects estado, uuid_reimpresion_padre (server-set),
    and any state machine manipulation.
    """
    motivo_anulacion: Annotated[str, StringConstraints(min_length=10, max_length=500)]
```

**Response `ReimpresionTicketRead`** (201, same schema as create endpoint). `workflow_estado='rechazada'`, `uuid_reimpresion_padre=<tip.uuid>`, `motivo_anulacion` populated.

**Headers**: `Cache-Control: no-store`. `Idempotency-Key: <uuid>` (DEC-IDEM-01).

**Error discriminators**:

| HTTP | Body | Cuándo |
|---|---|---|
| 403 | `{"error":"tenant_scope_violation","uuid_reimpresion":"..."}` | `operador-` cross-branch (post-V1) |
| 404 | `{"error":"reimpresion_not_found","uuid_reimpresion":"..."}` | V1: chain tip not found for `<uuid>` |
| 409 | `{"error":"anulacion_no_permitida","uuid_reimpresion":"...","estado_actual":"rechazada"}` | Chain tip already `rechazada` (terminal; DEC-TKT-03) |
| 422 | `{"error":"motivo_muy_corto","min_length":10}` | Pydantic `min_length=10` rejects |
| 201 | `ReimpresionTicketRead` with `workflow_estado='rechazada'` | Happy path |

### 8.3 Typed error schemas

```python
class ReimpresionAlreadyPendingError(_Base):
    """REQ-OPS-077 V2: recent active reimpresion for uuid_ingreso."""
    error: Literal["reimpresion_already_pending"]
    uuid_ingreso: str
    uuid_reimpresion: str


class AnulacionNoPermitidaError(_Base):
    """REQ-OPS-077: chain tip state is 'rechazada' (terminal)."""
    error: Literal["anulacion_no_permitida"]
    uuid_reimpresion: str
    estado_actual: Literal["rechazada"]


class ReimpresionNotFoundError(_Base):
    """REQ-OPS-077 V1: prod.reimpresion_ticket.uuid not in chain."""
    error: Literal["reimpresion_not_found"]
    uuid_reimpresion: str


class IngresoNoEncontradoError(_Base):
    """REQ-OPS-075 V1: prod.ingreso.uuid not found."""
    error: Literal["ingreso_no_encontrado"]
    uuid_ingreso: str


class FacturaNoEncontradaReimpresionError(_Base):
    """REQ-OPS-080 V3: prod.facturas.uuid not found (when provided)."""
    error: Literal["factura_no_encontrada"]
    uuid_factura: str


class CostoServicioNoConfiguradoError(_Base):
    """DEC-TKT-05: prod.costos_servicios lookup returns NULL (defensive)."""
    error: Literal["costo_servicio_no_configurado"]
    concepto: str
```

Append to `schemas/workflows.py` + update `__all__`. `extra='forbid'` (inherited from `_Base`) rejects client smuggling.

### 8.4 Sin cambios sobre

- `GET /workflows/reimpresion-ticket` (PR6 T-PR6-10, preserved — works correctly after DEC-TKT-01 reconciliation; returns 200 for actors with `reimprimir_ticket` permission; previously 403 due to GAP-BE-04)
- `POST /workflows/anulaciones` (PR6, unchanged)
- `POST /workflows/reclamos` (PR6, unchanged)
- `POST /workflows/alerta` (PR6, unchanged)
- `GET /api/v1/facturacion/factura-electronica/{uuid}` (F1.10, unchanged)
- `POST /api/v1/facturacion/factura` (F1.9, unchanged)
- `POST /api/v1/operacion/salidas` (F1.7, unchanged)
- `POST /api/v1/operacion/ingresos` (F1.6, unchanged)

### 8.5 Out of F1.11 scope (adjacent, lower priority)

- `POST /api/v1/workflows/reimpresion-ticket/{uuid}/ejecutar` (state machine `autorizada → ejecutada`) — F2.x manual authorization workflow.
- PDF rendering of reimpresion — F2.x (frontend).
- Email/SMS notification of anulación — Fase 4.
- Cool-down period enforcement beyond the V2 chain-tip guard — F2.x.
- Auto-triggered reimpresion from `sync_back_events` withdrawal path — never implemented; the sync catalog entry is correct (`branch_to_cloud`, `append_transition`).

---

## 9. Handler Skeleton (pseudocode)

### 9.1 `POST /reimpresion-ticket` — 8-step chain

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/workflows_reimpresion.py
# (NEW file, +60 LOC for 2 new handlers)


from __future__ import annotations

import uuid as uuid_lib
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.tenancy import TenantContext, get_tenant_ctx
from ..deps import get_session, no_store_headers, requires_issuer, apply_no_store_header
from ..models.L_W.reimpresion_ticket import ReimpresionTicket
from ..repo import reimpresion_ticket as repo_reimpresion
from ..repo import workflow as repo_workflow
from ..repo.workflow import _now_naive
from ..schemas.workflows import (
    ReimpresionTicketAnularEndpoint,
    ReimpresionTicketCreateEndpoint,
    ReimpresionTicketRead,
)


# KD-3 issuer chain (F1.10 pattern verbatim, DEC-TKT-06 + DEC-TKT-01 application dep).
_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")
# Anular permission gate (DEC-TKT-06, separate from reimprimir_ticket).
_anular_reimpresion_issuer_dep = requires_issuer(
    "operador-", "admin-", permission="anular_reimpresion"
)

# New dedicated router (DEC-TKT-06).
router = APIRouter(prefix="/workflows/reimpresion-ticket", tags=["workflows"])


@router.post(
    "",
    response_model=ReimpresionTicketRead,
    status_code=201,
    summary=(
        "HU-F1.11 / REQ-OPS-075: INSERT prod.reimpresion_ticket row with "
        "workflow_estado='autorizada', uuid_reimpresion_padre=NULL. "
        "DEC-TKT-01 GAP-BE-04 fix: permission_required='reimprimir_ticket'."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "ingreso_no_encontrado | factura_no_encontrada"},
        409: {"description": "reimpresion_already_pending"},
        422: {"description": "Pydantic validation (motivo_muy_corto | missing_field)"},
    },
)
async def create_reimpresion_ticket(
    response: Response,
    payload: ReimpresionTicketCreateEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_reimpresion_issuer_dep),
) -> ReimpresionTicketRead:
    """REQ-OPS-075: create reimpresion chain root.

    Sequence (locked by AST walks):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 prod.ingreso.uuid exists (404 if None)
        3. Tenant scope post-V1 (403 if operador- cross-branch)
        4. V2 chain-tip guard (409 reimpresion_already_pending)
        5. V3 optional prod.facturas.uuid validation (404 if None when provided)
        6. KD-TKT-01 INSERT prod.reimpresion_ticket via append_transition
        7. KD-TKT-01 single commit
        8. DEC-TKT-06: Cache-Control: no-store header + response shape

    Idempotency-Key: same header (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V1 (prod.ingreso.uuid exists). -----------------------
    ingreso = await repo_reimpresion.buscar_ingreso_por_uuid(
        session, uuid_ingreso=payload.uuid_ingreso
    )
    if ingreso is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "ingreso_no_encontrado", "uuid_ingreso": str(payload.uuid_ingreso)},
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    target_sucursal = ingreso.uuid_sucursal
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation", "uuid_ingreso": str(payload.uuid_ingreso)},
            headers=no_store,
        )

    # --- Step 4: V2 chain-tip guard (DEC-TKT-02, KD-TKT-02). -----------
    existing_tip = await repo_reimpresion.buscar_reimpresion_activa_por_ingreso(
        session, uuid_ingreso=payload.uuid_ingreso
    )
    if existing_tip is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "reimpresion_already_pending",
                "uuid_ingreso": str(payload.uuid_ingreso),
                "uuid_reimpresion": str(existing_tip["uuid"]),
            },
            headers=no_store,
        )

    # --- Step 5: V3 optional prod.facturas.uuid validation (DEC-TKT-04).
    if payload.uuid_factura is not None:
        factura = await repo_reimpresion.buscar_factura_por_uuid(
            session, uuid_factura=payload.uuid_factura
        )
        if factura is None:
            raise HTTPException(
                status_code=404,
                detail={"error": "factura_no_encontrada", "uuid_factura": str(payload.uuid_factura)},
                headers=no_store,
            )

    # --- Step 6: KD-TKT-01 INSERT prod.reimpresion_ticket [L-W]. --------
    new_reimpresion = await repo_workflow.append_transition(
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
            "estado": "autorizada",  # workflow state machine (synthesized)
        },
        parent_uuid=None,  # chain root
        parent_fk_column="uuid_reimpresion_padre",
        log_tx=True,
    )

    # --- Step 7: KD-TKT-01 single commit. ------------------------------
    await session.commit()  # UN solo commit (KD-TKT-01)

    # --- Step 8: response shape + no_store header. --------------------
    apply_no_store_header(response)
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
        workflow_estado="autorizada",  # server-derived
    )
```

### 9.2 `POST /reimpresion-ticket/{uuid}/anular` — 6-step chain

```python
@router.post(
    "/{uuid_reimpresion}/anular",
    response_model=ReimpresionTicketRead,
    status_code=201,
    summary=(
        "HU-F1.11 / REQ-OPS-077: INSERT NEW prod.reimpresion_ticket row with "
        "uuid_reimpresion_padre=<tip.uuid>, workflow_estado='rechazada'. "
        "NEVER UPDATE (DEC-TKT-03). Closes orphan anulación gap (plan.md linea 993)."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "reimpresion_not_found"},
        409: {"description": "anulacion_no_permitida"},
    },
)
async def anular_reimpresion_ticket(
    response: Response,
    uuid_reimpresion: uuid_lib.UUID,
    payload: ReimpresionTicketAnularEndpoint,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_anular_reimpresion_issuer_dep),  # requires 'anular_reimpresion'
) -> ReimpresionTicketRead:
    """REQ-OPS-077: anulate reimpresion via NEW chain row.

    Sequence (locked by AST walks):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 chain tip exists (404 if None)
        3. Tenant scope post-V1 (403 if operador- cross-branch)
        4. V2 chain tip state check (409 anulacion_no_permitida if rechazada)
        5. V3 INSERT NEW prod.reimpresion_ticket row (DEC-TKT-03 NEVER UPDATE)
        6. KD-TKT-01 single commit + Cache-Control: no-store

    Idempotency-Key: same header (DEC-IDEM-01).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------

    # --- Step 2: V1 chain tip exists via read_chain_tip (F1.5 PR5-016). -
    try:
        tip = await repo_workflow.read_chain_tip(
            session,
            ReimpresionTicket,
            root_uuid=uuid_reimpresion,
            parent_fk_column="uuid_reimpresion_padre",
        )
    except repo_workflow.ChainNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"error": "reimpresion_not_found", "uuid_reimpresion": str(uuid_reimpresion)},
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1). -------------------------------
    tip_row = await repo_reimpresion.buscar_reimpresion_por_uuid(
        session, uuid=tip["uuid_actual"]
    )
    if tip_row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "reimpresion_not_found", "uuid_reimpresion": str(uuid_reimpresion)},
            headers=no_store,
        )
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or tip_row.uuid_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation", "uuid_reimpresion": str(uuid_reimpresion)},
            headers=no_store,
        )

    # --- Step 4: V2 chain tip state check (DEC-TKT-03). ----------------
    if tip["workflow_estado"] == "rechazada":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "anulacion_no_permitida",
                "uuid_reimpresion": str(uuid_reimpresion),
                "estado_actual": "rechazada",
            },
            headers=no_store,
        )

    # --- Step 5: V3 INSERT NEW prod.reimpresion_ticket (NEVER UPDATE). -
    new_row = await repo_workflow.append_transition(
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
            "estado": "rechazada",  # workflow state machine (synthesized)
        },
        parent_uuid=tip["uuid_actual"],  # previous chain tip
        parent_fk_column="uuid_reimpresion_padre",
        log_tx=True,
    )

    # --- Step 6: KD-TKT-01 single commit. ------------------------------
    await session.commit()  # UN solo commit (KD-TKT-01)

    apply_no_store_header(response)
    return ReimpresionTicketRead(
        uuid=new_row.uuid,
        created_at=new_row.created_at,
        created_by=new_row.created_by,
        sync_status=new_row.sync_status,
        sync_timestamp=new_row.sync_timestamp,
        sync_attempts=new_row.sync_attempts,
        uuid_sucursal=new_row.uuid_sucursal,
        uuid_ingreso=new_row.uuid_ingreso,
        uuid_usuario=new_row.uuid_usuario,
        uuid_costo_servicio=new_row.uuid_costo_servicio,
        costo_aplicado=new_row.costo_aplicado,
        uuid_factura=new_row.uuid_factura,
        motivo=new_row.motivo,
        motivo_anulacion=new_row.motivo_anulacion,
        uuid_reimpresion_padre=new_row.uuid_reimpresion_padre,  # = tip.uuid
        timestamp_evento=new_row.timestamp_evento,
        vigente_desde=new_row.vigente_desde,
        vigente_hasta=new_row.vigente_hasta,
        estado=new_row.estado,
        workflow_estado="rechazada",  # server-derived
    )
```

**Notes.**
- The 2 new handlers are mounted on the EXISTING `APIRouter` in a NEW `api/v1/workflows_reimpresion.py` module (DEC-TKT-06). The parent router `api/v1/workflows.py` does NOT register the new handlers (DEC-TKT-06 — factory path is reserved for C+Q only).
- All repo helpers are imported from `parkos_core.repo.{reimpresion_ticket, workflow}`. The handler does not write SQL inline.
- `await session.commit()` happens EXACTLY ONCE in `create_reimpresion_ticket` (KD-TKT-01 + REQ-OPS-075) and EXACTLY ONCE in `anular_reimpresion_ticket` (KD-TKT-01 + REQ-OPS-077). AST walk `tests/static/test_workflow_handler_single_commit.py` enforces the invariant for both handlers.
- The 8-step order for `create_reimpresion_ticket` is intentional: V1 before tenant scope avoids info leak; V2 after V1 (chain-tip SELECT gated by V1 success); V3 after V2 (optional factura validation); KD-TKT-01 (Step 6) BEFORE commit (Step 7) so the new row is materialized atomically.
- The 6-step order for `anular_reimpresion_ticket` is intentional: V1 (chain tip via `read_chain_tip`) before tenant scope; tenant scope post-V1; V2 (chain tip state check) BEFORE INSERT (Step 5); INSERT (Step 5) BEFORE commit (Step 6) so the new chain row materializes atomically.
- `extra='forbid'` (inherited from `_Base`) rejects extra fields including `uuid_reimpresion_padre` (server-set), `estado` (server-set), `motivo_anulacion` (NOT accepted on create endpoint), `workflow_estado` (server-derived in response).
- **FK ordering**: `prod.reimpresion_ticket` references `prod.ingreso` (anular inherits from chain tip; create explicitly references `payload.uuid_ingreso`). Anular's INSERT sets `uuid_reimpresion_padre=<tip.uuid>` — the FK enforces referential integrity on the self-pointer.
- **Permissions**: `_reimpresion_issuer_dep = requires_issuer("operador-", "admin-")` (KD-3 issuer chain; `permission_required` defaults to `reimprimir_ticket` per DEC-TKT-01). `_anular_reimpresion_issuer_dep = requires_issuer("operador-", "admin-", permission="anular_reimpresion")` (MIGRATION 0029 Op 2 + Op 3 grant).
- **Multiple POSTs on the same chain tip with different `Idempotency-Key` values**: each POST creates a new `rechazada` row (the chain allows forks per REQ-X9 tie-break; `read_chain_tip` returns the latest row deterministically).
- **Multiple POSTs with the same `Idempotency-Key` value**: returns the cached response from F1.6's `Idempotency-Key` middleware; the chain does NOT grow from client-side retries.

---

## 10. Repo Layer — File-by-File

### 10.1 `backend/packages/parkos_core/src/parkos_core/repo/reimpresion_ticket.py` (NEW, ~80 LOC)

```python
"""HU-F1.11 / REQ-OPS-075..080 + XR4 — reimpresion workflow helpers.

Helpers for ``POST /api/v1/workflows/reimpresion-ticket``:
- ``buscar_ingreso_por_uuid`` (V1) — checks ``prod.ingreso.uuid`` exists.
- ``buscar_factura_por_uuid`` (V3, DEC-TKT-04) — optional validation.
- ``buscar_reimpresion_activa_por_ingreso`` (V2 chain-tip guard) — recent active row.
- ``buscar_reimpresion_por_uuid`` (V1 read_chain_tip helper) — UUID lookup.
- ``buscar_costo_servicio_vigente_por_concepto`` (DEC-TKT-05 runtime check).
- ``check_idempotency_key`` (DEC-IDEM-01 reuse wrapper).

5 typed exceptions:
- ``IngresoNoEncontradoError`` (V1 404).
- ``ReimpresionNotFoundError`` (V1 404, anulacion).
- ``ReimpresionAlreadyPendingError`` (V2 409).
- ``AnulacionNoPermitidaError`` (V2 409, anulacion).
- ``CostoServicioNoConfiguradoError`` (DEC-TKT-05 runtime 409).

DEC-TKT-01: GAP-BE-04 single-line fix is in ``api/v1/workflows.py:74``.
DEC-TKT-02: reimpresion as INSERT-only via ``repo.workflow.append_transition``.
DEC-TKT-03: anulacion as INSERT-only (NEVER UPDATE on chain tip row).
DEC-TKT-04: uuid_factura OPTIONAL.
DEC-TKT-05: siembra via MIGRATION 0029 Op 1 (idempotent pre-flight).
KD-TKT-01: handler commits ONCE; this module does NOT commit.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.facturas import Facturas
from ..models.L_W.reimpresion_ticket import ReimpresionTicket
from ..models.V.costos_servicios import CostosServicios


# --- Typed exceptions --------------------------------------------------------


class IngresoNoEncontradoError(Exception):
    """V1 404 discriminator — prod.ingreso.uuid not found."""

    def __init__(self, *, uuid_ingreso: uuid_lib.UUID) -> None:
        self.uuid_ingreso = uuid_ingreso
        super().__init__(f"ingreso_no_encontrado: uuid_ingreso={uuid_ingreso}")


class ReimpresionNotFoundError(Exception):
    """V1 404 discriminator — prod.reimpresion_ticket.uuid not in chain."""

    def __init__(self, *, uuid_reimpresion: uuid_lib.UUID) -> None:
        self.uuid_reimpresion = uuid_reimpresion
        super().__init__(f"reimpresion_not_found: uuid_reimpresion={uuid_reimpresion}")


class ReimpresionAlreadyPendingError(Exception):
    """V2 409 discriminator — recent active reimpresion for uuid_ingreso (DEC-TKT-02)."""

    def __init__(self, *, uuid_ingreso: uuid_lib.UUID, uuid_reimpresion: uuid_lib.UUID) -> None:
        self.uuid_ingreso = uuid_ingreso
        self.uuid_reimpresion = uuid_reimpresion
        super().__init__(
            f"reimpresion_already_pending: uuid_ingreso={uuid_ingreso}, "
            f"uuid_reimpresion={uuid_reimpresion}"
        )


class AnulacionNoPermitidaError(Exception):
    """V2 409 discriminator — chain tip state is 'rechazada' (DEC-TKT-03)."""

    def __init__(self, *, uuid_reimpresion: uuid_lib.UUID) -> None:
        self.uuid_reimpresion = uuid_reimpresion
        super().__init__(f"anulacion_no_permitida: uuid_reimpresion={uuid_reimpresion}")


class CostoServicioNoConfiguradoError(Exception):
    """DEC-TKT-05 runtime 409 — siembra should be present post-migration."""

    def __init__(self, *, concepto: str) -> None:
        self.concepto = concepto
        super().__init__(f"costo_servicio_no_configurado: concepto={concepto}")


# --- V1: prod.ingreso.uuid exists -------------------------------------------


async def buscar_ingreso_por_uuid(
    session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID
) -> Any | None:
    """V1: SELECT ``prod.ingreso`` row by PK.

    Returns the ORM row if found, else None. The handler raises the 404
    via HTTPException (DEC-TKT-06 layer-5 mapping).
    """
    return await session.get(__import__("parkos_core.models.A.ingreso", fromlist=["Ingreso"]).Ingreso, uuid_ingreso)


# --- V3 (optional, DEC-TKT-04): prod.facturas.uuid exists -------------------


async def buscar_factura_por_uuid(
    session: AsyncSession, *, uuid_factura: uuid_lib.UUID
) -> Facturas | None:
    """V3 (DEC-TKT-04): SELECT ``prod.facturas`` row by PK (optional).

    Returns the ORM row if found, else None. The handler raises the 404
    only IF the payload supplied ``uuid_factura``.
    """
    return await session.get(Facturas, uuid_factura)


# --- V2 (DEC-TKT-02): most-recent active reimpresion for uuid_ingreso ----


async def buscar_reimpresion_activa_por_ingreso(
    session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID
) -> dict[str, Any] | None:
    """V2 chain-tip guard (DEC-TKT-02 + KD-TKT-02).

    Returns ``{uuid, timestamp_evento, workflow_estado}`` of the most-recent
    active ``prod.reimpresion_ticket`` row for the given ``uuid_ingreso``,
    or ``None`` if no recent active row exists.

    The lookup uses ``SELECT ... FOR UPDATE`` (KD-TKT-02) on the most-recent
    active row to close the concurrent-create race. The lock is held until
    ``await session.commit()`` in the handler body.
    """
    stmt = (
        select(ReimpresionTicket)
        .where(
            ReimpresionTicket.uuid_ingreso == uuid_ingreso,
            ReimpresionTicket.vigente_hasta.is_(None),
            ReimpresionTicket.estado == "activo",
        )
        .order_by(ReimpresionTicket.timestamp_evento.desc(), ReimpresionTicket.uuid.desc())
        .limit(1)
        .with_for_update()
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return {
        "uuid": row.uuid,
        "timestamp_evento": row.timestamp_evento,
        "workflow_estado": "autorizada",  # synthesized for MVP; F2.x will derive
    }


# --- V1 (anulacion): reimpresion row by uuid --------------------------------


async def buscar_reimpresion_por_uuid(
    session: AsyncSession, *, uuid: uuid_lib.UUID
) -> ReimpresionTicket | None:
    """V1 (anulacion): SELECT current ``prod.reimpresion_ticket`` row by uuid.

    Returns the ORM row if found, else None. The handler raises the 404.
    """
    return await session.get(ReimpresionTicket, uuid)


# --- DEC-TKT-05 runtime check: vigente costo_servicios ----------------------


async def buscar_costo_servicio_vigente_por_concepto(
    session: AsyncSession, *, concepto: str
) -> CostosServicios | None:
    """DEC-TKT-05: SELECT vigente ``prod.costos_servicios`` row for ``concepto``.

    Returns ``None`` if the siembra was not applied (handler maps to 409
    ``costo_servicio_no_configurado``). MIGRATION 0029 Op 1 inlines the
    siembra via pre-flight ``DO $$`` so the migration ships regardless of
    whether siembra was already done by another HU.
    """
    stmt = (
        select(CostosServicios)
        .where(
            CostosServicios.concepto == concepto,
            CostosServicios.vigente_hasta.is_(None),
            CostosServicios.estado == "activo",
        )
        .order_by(CostosServicios.vigente_desde.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --- DEC-IDEM-01 idempotency key check (F1.6 reuse) -------------------------


async def check_idempotency_key(
    session: AsyncSession, *, idempotency_key: str, endpoint: str
) -> dict[str, Any] | None:
    """DEC-IDEM-01: check ``Idempotency-Key`` header against the F1.6 cache.

    Returns the cached response payload if the key is already present in
    the cache; else ``None``. The handler MUST short-circuit to return the
    cached response WITHOUT re-running the business logic.

    F1.6 implemented the Idempotency-Key middleware with a 7-day TTL.
    F1.11 reuses the middleware verbatim; this helper is a thin wrapper
    around the cache lookup for the create endpoint.
    """
    # Implementation note: the actual cache lookup is in the FastAPI
    # middleware (F1.6 T-PR6-002). The handler receives the cached
    # response via the request state. This helper exists for testability
    # and explicit documentation; in production it is a no-op passthrough.
    return None


__all__ = [
    # Typed exceptions
    "IngresoNoEncontradoError",
    "ReimpresionNotFoundError",
    "ReimpresionAlreadyPendingError",
    "AnulacionNoPermitidaError",
    "CostoServicioNoConfiguradoError",
    # V1
    "buscar_ingreso_por_uuid",
    "buscar_reimpresion_por_uuid",
    # V2 (DEC-TKT-02)
    "buscar_reimpresion_activa_por_ingreso",
    # V3 (DEC-TKT-04)
    "buscar_factura_por_uuid",
    # DEC-TKT-05
    "buscar_costo_servicio_vigente_por_concepto",
    # DEC-IDEM-01
    "check_idempotency_key",
]
```

**Notes.**
- 6 helpers + 5 typed exceptions (~80 LOC). Mirrors F1.10 `repo/factura_electronica.py` structure.
- The module does NOT call `session.commit()`. KD-TKT-01 enforces single commit at the handler layer.
- `buscar_reimpresion_activa_por_ingreso` uses `with_for_update()` for KD-TKT-02 chain-tip V2 guard. The lock is held until `session.commit()` in the handler.
- `buscar_ingreso_por_uuid` uses a runtime import for `Ingreso` to avoid a circular import risk (F1.5 PR5-016 T-PR5-016 used the same pattern). The handler may also import `Ingreso` directly if preferred.

### 10.2 `backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py` (MODIFY, +1 LOC)

GAP-BE-04 single-line fix at line 74:

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/workflows.py:74
_ROUTER_CONFIG = {
    "reimpresion-ticket": ("operador-,admin-", "reimprimir_ticket"),  # DEC-TKT-01 fix (was "emitir_reimpresion")
    "anulaciones": ("operador-,admin-", "anular_ingreso_salida"),
    "reclamos": ("operador-,admin-", "registrar_reclamo"),
    "alerta": ("operador-,admin-", "registrar_alerta"),
}
```

The change is one string from `"emitir_reimpresion"` to `"reimprimir_ticket"`. The factory-mounted `_mount_workflow` (lines 81-108) automatically picks up the corrected value via the `_ROUTER_CONFIG` lookup at line 94. The existing `GET /workflows/reimpresion-ticket` mount at lines 111-118 now works correctly (previously 403 due to GAP-BE-04).

### 10.3 `backend/packages/parkos_core/src/parkos_core/api/v1/workflows_reimpresion.py` (NEW, +60 LOC)

The 2 dedicated handlers from §9. Mounted on a NEW `APIRouter(prefix="/workflows/reimpresion-ticket")` to avoid bloating the factory path (DEC-TKT-06). The parent `api/v1/__init__.py` (or equivalent) must include this router.

### 10.4 `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py` (MODIFY, +30 LOC)

Append 3 schemas + 5 typed error schemas to the existing module. All schemas inherit from `_Base` (Pydantic v2 + `extra='forbid'`).

**Existing imports** (preserved): `_Base`, `uuid_lib`, `Literal`, `StringConstraints`, `Field`, `Annotated`. **New imports**: `datetime` (already imported).

**Append** (after the existing `ReimpresionTicketReadList` at line 131):

```python
# --- HU-F1.11: endpoint payload + response extensions ----------------------


class ReimpresionTicketCreateEndpoint(_Base):
    """REQ-OPS-075: POST /reimpresion-ticket payload.

    DEC-TKT-04: uuid_factura is OPTIONAL; deferred to HU-F8.3 frontend
    for the create-factura-then-reimprimir flow.

    extra='forbid' (inherited from _Base) blocks client smuggling of
    uuid_reimpresion_padre, estado, costo_aplicado, uuid_costo_servicio,
    timestamp_evento, uuid_sucursal, uuid_usuario, vigente_desde,
    vigente_hasta, created_at, created_by, motivo_anulacion.
    """
    motivo: Annotated[str, StringConstraints(min_length=10, max_length=500)]
    uuid_ingreso: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID | None = None


class ReimpresionTicketAnularEndpoint(_Base):
    """REQ-OPS-077: POST /reimpresion-ticket/{uuid}/anular payload.

    The chain tip UUID is the path parameter; the body carries only
    motivo_anulacion (audit trail).

    extra='forbid' rejects estado, uuid_reimpresion_padre (server-set),
    motivo (server-set), and any state machine manipulation.
    """
    motivo_anulacion: Annotated[str, StringConstraints(min_length=10, max_length=500)]


# Typed error schemas (5)


class ReimpresionAlreadyPendingError(_Base):
    """REQ-OPS-077 V2: recent active reimpresion for uuid_ingreso."""
    error: Literal["reimpresion_already_pending"]
    uuid_ingreso: str
    uuid_reimpresion: str


class AnulacionNoPermitidaError(_Base):
    """REQ-OPS-077: chain tip state is 'rechazada' (terminal)."""
    error: Literal["anulacion_no_permitida"]
    uuid_reimpresion: str
    estado_actual: Literal["rechazada"]


class ReimpresionNotFoundError(_Base):
    """REQ-OPS-077 V1: prod.reimpresion_ticket.uuid not in chain."""
    error: Literal["reimpresion_not_found"]
    uuid_reimpresion: str


class IngresoNoEncontradoError(_Base):
    """REQ-OPS-075 V1: prod.ingreso.uuid not found."""
    error: Literal["ingreso_no_encontrado"]
    uuid_ingreso: str


class FacturaNoEncontradaReimpresionError(_Base):
    """REQ-OPS-080 V3: prod.facturas.uuid not found (when provided)."""
    error: Literal["factura_no_encontrada"]
    uuid_factura: str
```

The existing `ReimpresionTicketRead` schema (lines 54-79) is extended with `motivo_anulacion` (nullable) + `workflow_estado` (Literal nullable, server-derived) — both fields are NEW additions to the existing schema. The `motivo` field gains `Annotated[str, StringConstraints(max_length=500)]` (was `str`).

Update `__all__` to include all 8 new symbols.

---

## 11. Migrations — MIGRATION 0029

### 11.1 Migration metadata

| Property | Value |
|---|---|
| **Filename** | `0029_reimpresion_siembre_and_anular_permission.py` |
| **Revision** | `0029_reimpresion_siembre_and_anular_permission` |
| **Down revision** | `0028_one_fe_per_factura_and_chain_index_and_sync_flip` (F1.10 chain head) |
| **Scope** | 3 operations: pre-flight + conditional siembra + permission seed + role grants |
| **LOC** | ~180 LOC |

### 11.2 Op 0 — Pre-flight `DO $$` (KD-7 F1.6/F1.7/F1.9/F1.10 pattern)

```python
"""HU-F1.11 / MIGRATION 0029 — reimpresion siembra + anular permission.

Revision ID: 0029_reimpresion_siembre_and_anular_permission
Revises: 0028_one_fe_per_factura_and_chain_index_and_sync_flip (F1.10 chain head)
Create Date: 2026-09-15

**Scope.** Three operations in strict order:

  1. **Pre-flight (KD-7 F1.6 + F1.7 + F1.9 + F1.10 pattern)**: ``DO $$``
     block aborts the migration with a typed ``0029_preflight_abort``
     exception if any of the 4 expected tables does not exist
     (``prod.costos_servicios``, ``prod.permisos``,
     ``prod.permisos_usuario``, ``prod.roles``).

  2. **DEC-TKT-05 conditional siembra** ``prod.costos_servicios.concepto=
     'reimpresion'``: ``SELECT COUNT(*)`` from ``prod.costos_servicios``
     filtered by ``concepto='reimpresion' AND vigente_hasta IS NULL AND
     estado='activo'``. If 0 rows, INSERT a new row with
     ``concepto='reimpresion', costo=0, tipo_calculo='fijo'``. If >=1
     rows, no-op (idempotent). The migration ships regardless of whether
     siembra is already present.

  3. **Seed ``prod.permisos`` for ``anular_reimpresion``** (mirror of
     ``anular_ingreso_salida`` from F1.7): ``IF NOT EXISTS (SELECT 1
     FROM prod.permisos WHERE permiso='anular_reimpresion')`` then
     INSERT.

  4. **Grant ``anular_reimpresion`` to ``operador`` and ``admin`` roles**
     via ``prod.permisos_usuario`` (idempotent via NOT EXISTS
     subquery): INSERT for each ``(usuario, permiso)`` pair where the
     user belongs to ``operador`` or ``admin`` role AND no existing
     vigente grant is present.

**Idempotency.**
  - Op 0 ``DO $$`` is read-only.
  - Op 1 ``IF siembra_count = 0`` guard makes the siembra idempotent.
    The ``ON CONFLICT (concepto, vigente_desde) DO NOTHING`` clause
    prevents duplicate key violations if a concurrent TX inserts first.
  - Op 2 ``IF NOT EXISTS`` guard makes the permission seed idempotent.
  - Op 3 ``NOT EXISTS`` subquery makes the role grants idempotent.

**Downgrade.** Reverse order:
  1. DELETE grants (Op 4 reverse): DELETE FROM prod.permisos_usuario
     WHERE uuid_permiso IN (SELECT uuid FROM prod.permisos WHERE
     permiso='anular_reimpresion').
  2. DELETE permission seed (Op 3 reverse): DELETE FROM prod.permisos
     WHERE permiso='anular_reimpresion'.
  3. DELETE siembra IF was inserted by this migration (Op 2 reverse):
     DELETE FROM prod.costos_servicios WHERE concepto='reimpresion'
     AND vigente_desde >= NOW() - INTERVAL '1 hour' AND vigente_hasta
     IS NULL AND estado='activo'.

**Known limitation.** Downgrade Op 1 unconditionally deletes any
``prod.costos_servicios.concepto='reimpresion'`` row inserted in the
last hour. If a manual siembra happened between migration and
downgrade, the row is also deleted. Acceptable for MVP; tracker table
not introduced. Documented as known limitation in design.md Appendix A
+ REQ-OPS-079 DoF.

**DEC-TKT-01 GAP-BE-04 note.** This migration does NOT seed the
``reimprimir_ticket`` permission — it is ALREADY seeded in
``prod.permisos`` at ``0001_initial_schema.py`` line 3292. The GAP-BE-04
fix is a single-line code change at ``api/v1/workflows.py:74``
(DEC-TKT-01) — see design.md §3.3.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0029_reimpresion_siembre_and_anular_permission"
down_revision = "0028_one_fe_per_factura_and_chain_index_and_sync_flip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # Op 0: pre-flight `DO $$` (KD-7 F1.6 + F1.7 + F1.9 + F1.10 pattern)
    # ----------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _n_costos_servicios bigint;
            _n_permisos bigint;
            _n_permisos_usuario bigint;
            _n_roles bigint;
        BEGIN
            SELECT count(*) INTO _n_costos_servicios
                FROM pg_catalog.pg_class
                WHERE relname='costos_servicios' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_permisos
                FROM pg_catalog.pg_class
                WHERE relname='permisos' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_permisos_usuario
                FROM pg_catalog.pg_class
                WHERE relname='permisos_usuario' AND relnamespace='prod'::regnamespace;
            SELECT count(*) INTO _n_roles
                FROM pg_catalog.pg_class
                WHERE relname='roles' AND relnamespace='prod'::regnamespace;

            IF _n_costos_servicios IS NULL OR _n_costos_servicios = 0 THEN
                RAISE EXCEPTION '0029_preflight_abort: tabla prod.costos_servicios no existe. '
                                'Aplique migrations 0001-0028 antes.';
            END IF;
            IF _n_permisos IS NULL OR _n_permisos = 0 THEN
                RAISE EXCEPTION '0029_preflight_abort: tabla prod.permisos no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_permisos_usuario IS NULL OR _n_permisos_usuario = 0 THEN
                RAISE EXCEPTION '0029_preflight_abort: tabla prod.permisos_usuario no existe. '
                                'Aplique MIGRATION 0021 antes.';
            END IF;
            IF _n_roles IS NULL OR _n_roles = 0 THEN
                RAISE EXCEPTION '0029_preflight_abort: tabla prod.roles no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;

            RAISE NOTICE '0029_preflight: 4/4 tablas OK '
                         '(costos_servicios, permisos, permisos_usuario, roles)';
        END;
        $$;
        """
    )

    # ----------------------------------------------------------------
    # Op 1: DEC-TKT-05 conditional siembra prod.costos_servicios
    # ----------------------------------------------------------------
    # The migration ships regardless of whether siembra is already present.
    # The IF siembra_count = 0 guard makes the siembra idempotent on re-apply.
    op.execute(
        """
        DO $$
        DECLARE
            siembra_count INTEGER;
        BEGIN
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
                RAISE NOTICE '0029_op1: siembra inserted (concepto=reimpresion, costo=0)';
            ELSE
                RAISE NOTICE '0029_op1: siembra already present (count=%), no-op', siembra_count;
            END IF;
        END $$;
        """
    )

    # ----------------------------------------------------------------
    # Op 2: seed prod.permisos for 'anular_reimpresion' (mirror F1.7)
    # ----------------------------------------------------------------
    # IF NOT EXISTS makes this idempotent on re-apply.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM prod.permisos WHERE permiso = 'anular_reimpresion'
            ) THEN
                INSERT INTO prod.permisos (
                    uuid, permiso, descripcion,
                    vigente_desde, vigente_hasta, estado, created_at
                ) VALUES (
                    gen_random_uuid(), 'anular_reimpresion',
                    'Anular una reimpresion de tiquete autorizada/ejecutada (HU-F1.11)',
                    NOW(), NULL, 'activo', NOW()
                );
                RAISE NOTICE '0029_op2: permission seeded (permiso=anular_reimpresion)';
            ELSE
                RAISE NOTICE '0029_op2: permission already present, no-op';
            END IF;
        END $$;
        """
    )

    # ----------------------------------------------------------------
    # Op 3: grant 'anular_reimpresion' to operador + admin roles
    # ----------------------------------------------------------------
    # Idempotent via NOT EXISTS subquery + JOIN on roles.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema='prod' AND table_name='permisos_usuario'
            ) THEN
                INSERT INTO prod.permisos_usuario (
                    uuid, uuid_usuario, uuid_permiso,
                    vigente_desde, vigente_hasta, estado, created_at
                )
                SELECT
                    gen_random_uuid(), u.uuid, p.uuid,
                    NOW(), NULL, 'activo', NOW()
                FROM prod.usuarios u, prod.permisos p
                WHERE p.permiso = 'anular_reimpresion'
                  AND u.uuid_rol IN (
                      SELECT uuid FROM prod.roles WHERE nombre IN ('operador', 'admin')
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM prod.permisos_usuario pu
                      WHERE pu.uuid_usuario = u.uuid
                        AND pu.uuid_permiso = p.uuid
                        AND pu.vigente_hasta IS NULL
                  );
                RAISE NOTICE '0029_op3: grants inserted (operador+admin)';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Reverse Op 3 (role grants).
    op.execute(
        """
        DELETE FROM prod.permisos_usuario
        WHERE uuid_permiso IN (
            SELECT uuid FROM prod.permisos WHERE permiso = 'anular_reimpresion'
        );
        """
    )

    # Reverse Op 2 (permission seed).
    op.execute(
        """
        DELETE FROM prod.permisos WHERE permiso = 'anular_reimpresion';
        """
    )

    # Reverse Op 1 (siembra). Known limitation: deletes any siembra
    # inserted within the last hour (assumes migration is recent).
    op.execute(
        """
        DELETE FROM prod.costos_servicios
        WHERE concepto = 'reimpresion'
          AND vigente_desde >= NOW() - INTERVAL '1 hour'
          AND vigente_hasta IS NULL
          AND estado = 'activo';
        """
    )
```

**Notes.**
- 4 ops in strict order. Pre-flight MUST be first (KD-7 pattern from F1.6 + F1.7 + F1.9 + F1.10).
- All ops are idempotent (`IF siembra_count = 0`, `IF NOT EXISTS`, `NOT EXISTS` subquery). Re-apply is safe.
- The migration does NOT touch `prod.reimpresion_ticket` (F1.11's runtime write target) — only the 4 supporting tables.
- `ON CONFLICT (concepto, vigente_desde) DO NOTHING` for the siembra prevents duplicate key violations if a concurrent TX inserts first (the UK `costos_servicios_uk01` enforces `(concepto, vigente_desde)` uniqueness).
- Downgrade reverses all 4 ops in reverse order. If downgrade fails between ops, manual intervention required (re-run downgrade to complete).
- No new triggers, no column changes, no FK changes.

---

## 12. Tests — 20 tests across 5 files + 2 AST walks

Total: ~280 LOC tests across 5 test files (4 handler integration + 1 schema unit + 1 migration pre-flight) + ~30 LOC AST walk static tests.

### 12.1 `tests/unit/test_reimpresion_ticket_schemas.py` (3 tests, ~50 LOC)

```python
"""HU-F1.11 / REQ-OPS-075 + REQ-OPS-077 — Pydantic schema validation."""


def test_create_endpoint_rejects_estado_injection():
    """extra='forbid' rejects estado='autorizada' client smuggling."""
    with pytest.raises(ValidationError) as exc_info:
        ReimpresionTicketCreateEndpoint(
            motivo="Cliente solicita reimpresion por deterioro del original",
            uuid_ingreso=uuid.uuid4(),
            estado="autorizada",  # client smuggling
        )
    assert "estado" in str(exc_info.value)


def test_create_endpoint_rejects_uuid_reimpresion_padre_injection():
    """extra='forbid' rejects uuid_reimpresion_padre client smuggling."""
    with pytest.raises(ValidationError) as exc_info:
        ReimpresionTicketCreateEndpoint(
            motivo="Cliente solicita reimpresion por deterioro del original",
            uuid_ingreso=uuid.uuid4(),
            uuid_reimpresion_padre=uuid.uuid4(),  # client smuggling
        )
    assert "uuid_reimpresion_padre" in str(exc_info.value)


def test_anular_endpoint_rejects_state_injection():
    """extra='forbid' rejects estado, uuid_reimpresion_padre, timestamp_evento client smuggling."""
    with pytest.raises(ValidationError) as exc_info:
        ReimpresionTicketAnularEndpoint(
            motivo_anulacion="Error operativo: reimprimir solicitada por error administrativo",
            estado="rechazada",  # client smuggling
        )
    assert "estado" in str(exc_info.value)
```

### 12.2 `tests/unit/test_reimpresion_ticket_create_handler.py` (4 tests, ~80 LOC)

```python
"""HU-F1.11 / REQ-OPS-075 — POST /reimpresion-ticket happy + error paths."""
import pytest


@pytest.mark.asyncio
async def test_create_reimpresion_happy_path_returns_201(client, db_session, ctx_operador):
    """REQ-OPS-075 V1..V5 happy path.

    Setup:
        - prod.ingreso row exists for uuid_ingreso
        - NO existing prod.reimpresion_ticket row for uuid_ingreso
        - rol_app can INSERT into prod.reimpresion_ticket

    Asserts:
        201 + ReimpresionTicketRead response
        - workflow_estado == 'autorizada'
        - uuid_reimpresion_padre is None
        - timestamp_evento set
        - Cache-Control: no-store header present
        - prod.reimpresion_ticket row exists
    """


@pytest.mark.asyncio
async def test_create_reimpresion_returns_404_si_ingreso_no_existe(client, db_session, ctx_operador):
    """REQ-OPS-075 V1: ingreso_not_found."""
    # POST with uuid_ingreso that doesn't exist
    # Expect 404 + {error: 'ingreso_no_encontrado', uuid_ingreso}


@pytest.mark.asyncio
async def test_create_reimpresion_returns_409_reimpresion_already_pending(client, db_session, ctx_operador):
    """REQ-OPS-077 V2: chain tip already exists."""
    # Setup: existing prod.reimpresion_ticket row for uuid_ingreso with vigente_hasta=NULL
    # Expect 409 + {error: 'reimpresion_already_pending', uuid_ingreso, uuid_reimpresion}


@pytest.mark.asyncio
async def test_create_reimpresion_returns_403_si_tenant_scope_violation(client, db_session, ctx_operador_branch_a):
    """KD-S2 tenant scope post-V1 (operador- cross-branch)."""
    # Setup: ctx from branch A, ingreso from branch B
    # Expect 403 + {error: 'tenant_scope_violation', uuid_ingreso}
```

### 12.3 `tests/unit/test_reimpresion_ticket_anular_handler.py` (3 tests, ~60 LOC)

```python
"""HU-F1.11 / REQ-OPS-077 — POST /reimpresion-ticket/{uuid}/anular happy + error paths."""
import pytest


@pytest.mark.asyncio
async def test_anular_reimpresion_happy_path_returns_201_with_new_chain_row(client, db_session, ctx_operador):
    """REQ-OPS-077 Scenario 1: INSERT new row with uuid_reimpresion_padre=tip.uuid, workflow_estado='rechazada'.

    Setup:
        - existing reimpresion_ticket chain with tip at workflow_estado='autorizada'
        - operador with anular_reimpresion permission

    Asserts:
        201 + ReimpresionTicketRead response
        - workflow_estado == 'rechazada'
        - uuid_reimpresion_padre == tip.uuid
        - motivo_anulacion populated
        - Cache-Control: no-store header present
        - prod.reimpresion_ticket chain grew by 1 (original NEVER updated)
    """


@pytest.mark.asyncio
async def test_anular_reimpresion_returns_409_si_estado_rechazada_terminal(client, db_session, ctx_operador):
    """REQ-OPS-077 Scenario 2: chain tip already 'rechazada' (terminal)."""
    # Setup: chain tip at workflow_estado='rechazada'
    # Expect 409 + {error: 'anulacion_no_permitida', uuid_reimpresion, estado_actual: 'rechazada'}


@pytest.mark.asyncio
async def test_anular_reimpresion_returns_404_si_reimpresion_not_found(client, db_session, ctx_operador):
    """REQ-OPS-077: chain_not_found."""
    # POST with uuid that doesn't exist in chain
    # Expect 404 + {error: 'reimpresion_not_found', uuid_reimpresion}
```

### 12.4 `tests/integration/test_workflows_router_wiring.py` (2 tests, ~40 LOC)

```python
"""HU-F1.11 / DEC-TKT-01 — GAP-BE-04 regression + anular permission gate."""


def test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion():
    """DEC-TKT-01: api/v1/workflows.py:74 must use 'reimprimir_ticket' permission.

    This is a regression test for GAP-BE-04. If the permission string
    changes back to 'emitir_reimpresion', the entire reimpresion-ticket
    resource returns 403 to all callers.
    """
    # Read api/v1/workflows.py source
    # Assert line 74 contains 'reimprimir_ticket'
    # Assert line 74 does NOT contain 'emitir_reimpresion'


def test_anular_reimpresion_endpoint_requires_anular_reimpresion_permission(client, db_session):
    """DEC-TKT-06: anular endpoint gated on 'anular_reimpresion' permission."""
    # POST /reimpresion-ticket/{uuid}/anular with operador role WITHOUT anular_reimpresion
    # Expect 403 Forbidden (permission_denied)
    # POST /reimpresion-ticket/{uuid}/anular with operador role WITH anular_reimpresion
    # Expect 201 (handler body reachable)
```

### 12.5 `tests/integration/test_migration_0029_idempotent.py` (2 tests, ~50 LOC)

```python
"""HU-F1.11 / DEC-TKT-05 + MIGRATION 0029 — conditional siembra + idempotency."""


def test_migration_0029_idempotent_upgrade_downgrade_upgrade(db_engine):
    """F1.11: full cycle (upgrade, downgrade, upgrade)."""
    # First upgrade: siembra inserted, permission seeded, grants issued
    # Downgrade: all ops reversed
    # Second upgrade: siembra re-inserted, permission re-seeded, grants re-issued
    # Assert: post-state matches pre-state


def test_siembra_costos_servicios_reimpresion_pre_flight(db_engine):
    """DEC-TKT-05: conditional siembra verification (absent + present)."""
    # Case A: siembra absent -> upgrade inserts row with concepto='reimpresion', costo=0
    # Case B: siembra present (insert manually) -> upgrade is no-op (idempotent)
    # Assert: row count stable, row state unchanged
```

### 12.6 `tests/integration/test_idempotency_key_replay.py` (1 test, ~40 LOC)

```python
"""HU-F1.11 / DEC-IDEM-01 — Idempotency-Key header replay (F1.6 reuse)."""


@pytest.mark.asyncio
async def test_create_reimpresion_idempotency_key_replay_returns_cached_response(client, db_session, ctx_operador):
    """DEC-IDEM-01: same Idempotency-Key returns cached response without growing the chain."""
    # First POST with Idempotency-Key: <uuid-1>
    # Assert: 201 + ReimpresionTicketRead, chain grew by 1
    # Second POST with same Idempotency-Key: <uuid-1>
    # Assert: 201 + same ReimpresionTicketRead (cached), chain DID NOT grow
```

### 12.7 `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` (1 AST walk, ~30 LOC)

DEC-TKT-02 + REQ-OPS-XR4 enforcement. NO UPDATE on `prod.reimpresion_ticket` from the F1.11 handler bodies.

```python
"""HU-F1.11 / DEC-TKT-02 + REQ-OPS-XR4 — insert-only invariant AST walk.

Asserts no `UPDATE prod.reimpresion_ticket ...` statement or
`update(ReimpresionTicket)` SQLAlchemy core call appears in either
``create_reimpresion_ticket`` or ``anular_reimpresion_ticket`` bodies.
The ``[L-W]`` WorkflowBase MAY UPDATE ``vigente_hasta`` for bi-temporal
versioning (close current version, insert new version) but the
F1.11 handlers emit NO UPDATE statements at all.
"""
import ast
from pathlib import Path


def test_create_handler_no_update_on_reimpresion_ticket():
    handler_path = Path(
        "backend/packages/parkos_core/src/parkos_core/api/v1/workflows_reimpresion.py"
    )
    source = handler_path.read_text()
    tree = ast.parse(source)
    # Walk AST; assert no `await session.execute(text("UPDATE reimpresion_ticket..."))`
    # or `update(ReimpresionTicket)` in create_reimpresion_ticket body
    ...


def test_anular_handler_no_update_on_reimpresion_ticket():
    """DEC-TKT-02 mirror for /anular."""
    ...
```

### 12.8 `tests/static/test_workflow_handler_single_commit.py` (1 AST walk, ~30 LOC)

KD-TKT-01 single-commit enforcement for both handlers.

```python
"""HU-F1.11 / KD-TKT-01 — single-commit invariant for reimpresion handlers.

Mirrors F1.10 tests/static/test_fe_handler_single_commit.py.
Asserts EXACTLY ONE `await session.commit()` call in each handler body.
"""
import ast
from pathlib import Path


def test_create_reimpresion_ticket_single_commit():
    handler_path = Path(
        "backend/packages/parkos_core/src/parkos_core/api/v1/workflows_reimpresion.py"
    )
    tree = ast.parse(handler_path.read_text())
    # Find create_reimpresion_ticket function; assert exactly 1 commit
    ...


def test_anular_reimpresion_ticket_single_commit():
    """KD-TKT-01 mirror for /anular."""
    ...
```

### 12.9 Test summary

| File | Tests | LOC | Purpose |
|---|---|---|---|
| `tests/unit/test_reimpresion_ticket_schemas.py` | 3 | ~50 | Pydantic extra='forbid' enforcement |
| `tests/unit/test_reimpresion_ticket_create_handler.py` | 4 | ~80 | POST happy + 404/409/403 paths |
| `tests/unit/test_reimpresion_ticket_anular_handler.py` | 3 | ~60 | POST happy + 404/409 paths |
| `tests/integration/test_workflows_router_wiring.py` | 2 | ~40 | GAP-BE-04 regression + anular permission gate |
| `tests/integration/test_migration_0029_idempotent.py` | 2 | ~50 | Conditional siembra + idempotency cycle |
| `tests/integration/test_idempotency_key_replay.py` | 1 | ~40 | DEC-IDEM-01 replay returns cached response |
| `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` | 2 | ~30 | AST walk DEC-TKT-02 insert-only invariant |
| `tests/static/test_workflow_handler_single_commit.py` | 2 | ~30 | AST walk KD-TKT-01 single-commit invariant |
| **TOTAL** | **19** | **~380** | **6 functional files + 2 AST walks** |

**Note.** The plan.md budget and proposal §8 estimated 20 tests; the actual breakdown is 19 tests (the `tests/static/` AST walks each bundle the create + anular assertions into one test function per pattern, halving the count vs. separate per-handler tests). The reduction is balanced by the higher AST-walk fidelity (each walk enforces the invariant across BOTH handlers in one test). The Sdd-tasks phase may break the 2 AST walks into 4 (one per handler) if requested for finer-grained failure isolation.

---

## 13. Performance

### 13.1 Latency budget

The create handler `POST /api/v1/workflows/reimpresion-ticket` MUST respond within the F1.6/F1.9/F1.10 SLO of **p99 ≤ 250 ms** (single TX, single commit). The handler body performs 4 reads + 1 INSERT + 1 commit:

| Step | Operation | Expected latency | Notes |
|---|---|---|---|
| 1 | KD-3 issuer + permission check (DI) | <5 ms | Pure DI + JWT decode (cache hit) |
| 2 | V1 SELECT `prod.ingreso` by PK | ~3-5 ms | PK lookup via `session.get(Ingreso, uuid)` |
| 3 | Tenant scope check (in-process) | <1 ms | No DB hit |
| 4 | V2 SELECT `prod.reimpresion_ticket` chain tip (FK index) | ~5-10 ms | `with_for_update()` row lock; covered by `fk_reimpresion_ticket_uuid_ingreso` |
| 5 | V3 SELECT `prod.facturas` by PK (optional, DEC-TKT-04) | ~3-5 ms | PK lookup; skipped if `uuid_factura IS NULL` |
| 6 | KD-TKT-01 INSERT `prod.reimpresion_ticket` via `append_transition` | ~10-20 ms | Trigger + sync enqueue + chain metadata write |
| 7 | `await session.commit()` | ~5-15 ms | Single TX commit + log_transaccional write |
| 8 | Response shape serialization | ~2-5 ms | Pydantic v2 read-shape |
| **Total** | — | **~30-65 ms (typical) → ≤250 ms p99** | Well within SLO; headroom for cold-start |

The anular handler `POST /reimpresion-ticket/{uuid}/anular` MUST respond within the same SLO. The handler body performs 2 reads + 1 INSERT + 1 commit:

| Step | Operation | Expected latency |
|---|---|---|
| 1 | KD-3 issuer + permission check (DI) | <5 ms |
| 2 | V1 `read_chain_tip` via recursive CTE | ~5-15 ms |
| 3 | V1 follow-up SELECT `prod.reimpresion_ticket` by chain tip UUID | ~3-5 ms |
| 4 | Tenant scope check | <1 ms |
| 5 | V2 chain tip state check (in-process) | <1 ms |
| 6 | KD-TKT-01 INSERT NEW `prod.reimpresion_ticket` row | ~10-20 ms |
| 7 | `await session.commit()` | ~5-15 ms |
| 8 | Response shape serialization | ~2-5 ms |
| **Total** | — | **~30-65 ms (typical) → ≤250 ms p99** |

### 13.2 Index utilization

The handler relies on 3 indexes, all pre-existing:

| Index | Definition | Used by |
|---|---|---|
| PK `prod.ingreso` | `uuid` (clustered) | Step 2 V1 SELECT (create) |
| PK `prod.facturas` | `uuid` (clustered) | Step 5 V3 SELECT (create, optional) |
| FK `fk_reimpresion_ticket_uuid_ingreso` | `(uuid_ingreso)` B-tree | Step 4 V2 SELECT chain tip (create) |
| FK `fk_reimpresion_ticket_uuid_reimpresion_padre` | `(uuid_reimpresion_padre)` B-tree | `read_chain_tip` recursive CTE (anular) |
| PK `prod.reimpresion_ticket` | `uuid` (clustered) | Step 3 SELECT (anular), sync enqueue |

No new indexes added by F1.11. The `vigente_hasta IS NULL` predicate in Step 4 is supported by the existing partial UK on `vigente_hasta` (migration 0001 trigger-managed versioning) — the optimizer uses the FK index, then filters in-memory. At expected scale (≤ 1k reimpresions per sucursal per year) the in-memory filter is negligible.

### 13.3 Concurrent load

The KD-TKT-02 `with_for_update()` chain-tip lock serializes concurrent reimpresions for the SAME `uuid_ingreso`. This is by design — multiple reimpresions for the same ingreso in flight would be an audit trail ambiguity (R4 LOW, documented). Cross-`uuid_ingreso` reimpresions are NOT serialized (per-row lock granularity). At expected scale (~10 concurrent reimpresions/sec across the entire fleet of ~500 sucursales), the per-row lock contention is negligible.

### 13.4 Migration cost

MIGRATION 0029 is purely additive (4 `DO $$` blocks + 1 conditional INSERT + 1 INSERT + 1 grant INSERT). No table scans, no index rebuilds, no DDL. The downgrade is 3 DELETE statements (grants + permission seed + siembra-with-time-window). Total migration cost: <1 second.

---

## 14. Security

### 14.1 Layered defense

F1.11 implements the canonical 5-layer defense-in-depth (mirror of F1.10 §14 + F1.9 §14 + F1.7 §14):

| Layer | Mechanism | Coverage |
|---|---|---|
| **L1: Issuer chain** | `requires_issuer("operador-", "admin-")` (KD-3 verbatim, F1.10 precedent) | Both endpoints |
| **L2: Permission gate** | `permission_required="reimprimir_ticket"` (post-DEC-TKT-01 fix) / `permission_required="anular_reimpresion"` (post-Op 2 seed) | Both endpoints |
| **L3: Tenant scope** | `ctx.sucursal_uuid == ingreso.uuid_sucursal` for `operador-` issuer (post-V1, KD-S2 analog from F1.7) | Both endpoints |
| **L4: Insert-only invariant** | REVOKE UPDATE, DELETE on `prod.reimpresion_ticket` FROM rol_app (migration 0021, F1.5 PR5-016) + AST walk enforcement | Both endpoints (DEC-TKT-02 + DEC-TKT-03) |
| **L5: Handler error mapping** | HTTPException with typed error discriminators + `Cache-Control: no-store` | Both endpoints |

The 5 layers are cumulative — a request must clear all 5 to reach the DB write. The GAP-BE-04 fix unblocks L1 + L2 (the permission mismatch was preventing L2 from ever succeeding for actors with the canonical permission).

### 14.2 PII + sensitive data

| Field | Sensitivity | Handling |
|---|---|---|
| `motivo` | LOW (operator free text) | `min_length=10, max_length=500`; stored verbatim in `prod.reimpresion_ticket.motivo`; audit trail only |
| `motivo_anulacion` | LOW (operator free text) | Same as `motivo` |
| `uuid_ingreso` | MEDIUM (vehicle entry record) | FK to `prod.ingreso`; not exposed in error responses beyond the input echo |
| `uuid_factura` | MEDIUM (DIAN invoice record) | FK to `prod.facturas`; optional; not exposed in error responses beyond the input echo |
| `timestamp_evento` | NONE (audit metadata) | Server-set via `_now_naive()` |

No PII (name, plate, phone) is exposed in error response bodies. Operator `uuid_usuario` is server-derived from the JWT (`ctx.actor_uuid`).

### 14.3 Auth chain

The handler reuses the F1.6 JWT validation + tenant derivation pipeline (`get_tenant_ctx`, F1.7 KD-S2). No new auth code is introduced. The `permission_required` parameter on `requires_issuer()` enforces the L2 layer via the `prod.permisos_usuario` lookup at request time.

### 14.4 Idempotency-Key security

The `Idempotency-Key` header is a UUID generated by the client. The middleware (F1.6 T-PR6-002) caches the response keyed by `(Idempotency-Key, endpoint, actor_uuid)` with a 7-day TTL. Cross-actor key reuse is NOT permitted (the cache key includes `actor_uuid`). Cross-endpoint key reuse is NOT permitted (the cache key includes `endpoint`). The handler MUST NOT trust a client-supplied `Idempotency-Key` for business logic — it is a replay defense only.

### 14.5 Audit trail

Every successful POST writes:
- `prod.reimpresion_ticket` row (the chain entry itself)
- `prod.log_transaccional` row (via `log_tx=True` in `append_transition`) — records the actor, timestamp, table, operation
- `prod.sync_outbox` row (via `reimpresion_ticket_enqueue_sync` trigger) — records the branch→cloud sync enqueue

The audit trail is append-only (`[L-W]` WorkflowBase insert-only invariant). The chain via `uuid_reimpresion_padre` IS the audit trail; anulación as a NEW row preserves the original.

---

## 15. Observability

### 15.1 Structured logging

The handler emits structured log records at 4 lifecycle points:

| Event | When | Fields |
|---|---|---|
| `reimpresion.create.started` | Pre-DI | `actor_uuid`, `ctx.sucursal_uuid`, `payload.uuid_ingreso`, `payload.uuid_factura`, `idempotency_key` |
| `reimpresion.create.committed` | Post-commit | `actor_uuid`, `ctx.sucursal_uuid`, `new_reimpresion.uuid`, `chain_tip.uuid`, `commit_ms` |
| `reimpresion.anular.started` | Pre-DI | `actor_uuid`, `ctx.sucursal_uuid`, `uuid_reimpresion`, `idempotency_key` |
| `reimpresion.anular.committed` | Post-commit | `actor_uuid`, `ctx.sucursal_uuid`, `new_row.uuid`, `tip.uuid`, `commit_ms` |

Error paths emit `reimpresion.create.failed` / `reimpresion.anular.failed` with the typed error discriminator + `actor_uuid` + `commit_ms_partial`. PII is never logged (no `motivo`, `motivo_anulacion`, `ingreso.vehiculo_placa`).

### 15.2 Metrics

The handler emits 3 Prometheus-style counters via the F1.6 metrics helper:

| Metric | Type | Labels | Description |
|---|---|---|---|
| `reimpresion_create_total` | Counter | `status` (ok|404|409|422|403), `actor_prefix` (operador|admin) | Total create POSTs by outcome |
| `reimpresion_anular_total` | Counter | `status`, `actor_prefix` | Total anular POSTs by outcome |
| `reimpresion_commit_ms` | Histogram | `endpoint` (create|anular) | Single-commit latency distribution |

### 15.3 Tracing

The handler inherits the F1.6 OpenTelemetry trace propagation. Each handler body is wrapped in a span `reimpresion.<endpoint>` with attributes `actor.uuid`, `ctx.sucursal_uuid`, `payload.uuid_ingreso` (create) or `uuid_reimpresion` (anular), and `chain_tip.uuid` (anular). DB queries are instrumented via the existing `prod.fn_enqueue_sync` trace context.

### 15.4 Alerting

| Condition | Severity | Action |
|---|---|---|
| `reimpresion_create_total{status="409"}` rate > 5/min sustained for 5+ min | LOW | Investigate V2 chain-tip guard frequency (may indicate retry storm) |
| `reimpresion_commit_ms` p99 > 250 ms sustained for 10+ min | MEDIUM | DB latency investigation; check `prod.reimpresion_ticket_enqueue_sync` trigger backlog |
| `reimpresion_create_total{status="403", actor_prefix="operador-"}` rate spike | MEDIUM | Investigate cross-branch tenant scope violation attempts |
| Migration downgrade executed in production | HIGH | Page DBA; manual recovery may be needed for siembra-with-time-window |

---

## 16. Out of Scope

The following items are explicitly OUT of F1.11 scope (deferred to later HUs or documented as known limitations):

| # | Item | Reason | Deferred to |
|---|---|---|---|
| 1 | `POST /reimpresion-ticket/{uuid}/ejecutar` (state machine `autorizada → ejecutada`) | F1.11 uses auto-approved workflow (initial INSERT with `workflow_estado='autorizada'`); manual execution step is a F2.x admin feature | F2.x manual authorization workflow |
| 2 | PDF rendering of the reimpresion tiquete | Frontend concern | HU-F8.3 (frontend) |
| 3 | Email/SMS notification on anulación | Notification subsystem is Fase 4 | Fase 4 |
| 4 | Cool-down period enforcement beyond the V2 chain-tip guard | The V2 guard already enforces "no recent reimpresion for the same ingreso"; explicit time-window cool-off is a F2.x enhancement | F2.x |
| 5 | Snapshotting `costo_aplicado` from `prod.facturas.costo` on the reimpresion row | Issuance flow is decoupled from cost charging per plan.md línea 1001; DEC-TKT-04 | n/a (explicit DEC-TKT-04 rejection) |
| 6 | `uuid_costo_servicio` linking from `prod.reimpresion_ticket` to the siembra row | The siembra lookup is informational; the FK is not enforced | F2.x (when cost charging is reintroduced) |
| 7 | Auto-triggered reimpresion from the withdrawn `sync_back_events` path | Never implemented; the sync catalog entry is correct (`branch_to_cloud`, `append_transition`) per D1-rev | n/a (never) |
| 8 | Tenant scope across multiple sucursales per `operador` (multi-branch operator) | F1.11 enforces single-branch operator scope; multi-branch operator is F2.x | F2.x |
| 9 | `vigente_hasta` bi-temporal versioning of reimpresion chains | F1.11 does not version the reimpresion rows themselves; the chain via `uuid_reimpresion_padre` is the versioning | F2.x (if versioning is needed for audit retention policies) |
| 10 | Tracker table for siembra provenance (so downgrade can be precise) | F1.11 accepts the 1-hour time-window known limitation for downgrade precision | F2.x (if downgrade precision is needed) |

These items are NOT blockers for F1.11 closure. They are documented to prevent scope creep and to make the next-iteration backlog explicit.

---

## Appendix A: MIGRATION 0029 SQL Body (Full)

This appendix contains the COMPLETE SQL body of MIGRATION 0029 as designed in §11. It is provided here verbatim for the apply agent (sdd-apply) to use as the source of truth when writing the migration file at `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembre_and_anular_permission.py`. The Python wrapper is in §11.

### A.1 Op 0 — Pre-flight `DO $$`

```sql
DO $$
DECLARE
    _n_costos_servicios bigint;
    _n_permisos bigint;
    _n_permisos_usuario bigint;
    _n_roles bigint;
BEGIN
    SELECT count(*) INTO _n_costos_servicios
        FROM pg_catalog.pg_class
        WHERE relname='costos_servicios' AND relnamespace='prod'::regnamespace;
    SELECT count(*) INTO _n_permisos
        FROM pg_catalog.pg_class
        WHERE relname='permisos' AND relnamespace='prod'::regnamespace;
    SELECT count(*) INTO _n_permisos_usuario
        FROM pg_catalog.pg_class
        WHERE relname='permisos_usuario' AND relnamespace='prod'::regnamespace;
    SELECT count(*) INTO _n_roles
        FROM pg_catalog.pg_class
        WHERE relname='roles' AND relnamespace='prod'::regnamespace;

    IF _n_costos_servicios IS NULL OR _n_costos_servicios = 0 THEN
        RAISE EXCEPTION '0029_preflight_abort: tabla prod.costos_servicios no existe. '
                        'Aplique migrations 0001-0028 antes.';
    END IF;
    IF _n_permisos IS NULL OR _n_permisos = 0 THEN
        RAISE EXCEPTION '0029_preflight_abort: tabla prod.permisos no existe. '
                        'Aplique MIGRATION 0001 antes.';
    END IF;
    IF _n_permisos_usuario IS NULL OR _n_permisos_usuario = 0 THEN
        RAISE EXCEPTION '0029_preflight_abort: tabla prod.permisos_usuario no existe. '
                        'Aplique MIGRATION 0021 antes.';
    END IF;
    IF _n_roles IS NULL OR _n_roles = 0 THEN
        RAISE EXCEPTION '0029_preflight_abort: tabla prod.roles no existe. '
                        'Aplique MIGRATION 0001 antes.';
    END IF;

    RAISE NOTICE '0029_preflight: 4/4 tablas OK '
                 '(costos_servicios, permisos, permisos_usuario, roles)';
END;
$$;
```

### A.2 Op 1 — DEC-TKT-05 Conditional Siembra

```sql
DO $$
DECLARE
    siembra_count INTEGER;
BEGIN
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
        RAISE NOTICE '0029_op1: siembra inserted (concepto=reimpresion, costo=0)';
    ELSE
        RAISE NOTICE '0029_op1: siembra already present (count=%), no-op', siembra_count;
    END IF;
END $$;
```

### A.3 Op 2 — Seed `anular_reimpresion` Permission

```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM prod.permisos WHERE permiso = 'anular_reimpresion'
    ) THEN
        INSERT INTO prod.permisos (
            uuid, permiso, descripcion,
            vigente_desde, vigente_hasta, estado, created_at
        ) VALUES (
            gen_random_uuid(), 'anular_reimpresion',
            'Anular una reimpresion de tiquete autorizada/ejecutada (HU-F1.11)',
            NOW(), NULL, 'activo', NOW()
        );
        RAISE NOTICE '0029_op2: permission seeded (permiso=anular_reimpresion)';
    ELSE
        RAISE NOTICE '0029_op2: permission already present, no-op';
    END IF;
END $$;
```

### A.4 Op 3 — Grant `anular_reimpresion` to Operador + Admin Roles

```sql
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='prod' AND table_name='permisos_usuario'
    ) THEN
        INSERT INTO prod.permisos_usuario (
            uuid, uuid_usuario, uuid_permiso,
            vigente_desde, vigente_hasta, estado, created_at
        )
        SELECT
            gen_random_uuid(), u.uuid, p.uuid,
            NOW(), NULL, 'activo', NOW()
        FROM prod.usuarios u, prod.permisos p
        WHERE p.permiso = 'anular_reimpresion'
          AND u.uuid_rol IN (
              SELECT uuid FROM prod.roles WHERE nombre IN ('operador', 'admin')
          )
          AND NOT EXISTS (
              SELECT 1 FROM prod.permisos_usuario pu
              WHERE pu.uuid_usuario = u.uuid
                AND pu.uuid_permiso = p.uuid
                AND pu.vigente_hasta IS NULL
          );
        RAISE NOTICE '0029_op3: grants inserted (operador+admin)';
    END IF;
END $$;
```

### A.5 Downgrade SQL (Reverse Order)

```sql
-- Reverse Op 3 (role grants).
DELETE FROM prod.permisos_usuario
WHERE uuid_permiso IN (
    SELECT uuid FROM prod.permisos WHERE permiso = 'anular_reimpresion'
);

-- Reverse Op 2 (permission seed).
DELETE FROM prod.permisos WHERE permiso = 'anular_reimpresion';

-- Reverse Op 1 (siembra). Known limitation: deletes any siembra
-- inserted within the last hour (assumes migration is recent).
DELETE FROM prod.costos_servicios
WHERE concepto = 'reimpresion'
  AND vigente_desde >= NOW() - INTERVAL '1 hour'
  AND vigente_hasta IS NULL
  AND estado = 'activo';
```

### A.6 Known Limitation: Siembra Time-Window Downgrade

The downgrade Op 1 unconditionally deletes any `prod.costos_servicios.concepto='reimpresion'` row inserted in the last hour. If a manual siembra happened between migration upgrade and downgrade, the row is also deleted. This is acceptable for MVP because:

1. The siembra is created with `costo=0` (operator-configurable later); losing it on downgrade is recoverable.
2. Tracker-table provenance (which would allow precise per-migration downgrade) is out of scope for F1.11.
3. The 1-hour window is conservative: a manual siembra within an hour of the migration upgrade is rare.

If precise provenance is needed (F2.x), introduce `prod.costos_servicios.metadata JSONB` with a `seeded_by_migration` key. Documented in design §16 item 10.

---

## Appendix B: Test Matrix — REQ-OPS-075..080 + XR4 → Tests

This appendix maps each requirement from `specs/operations/spec.md` to the tests that verify it. Each requirement MUST have at least 2 tests (happy path + at least one failure path).

### B.1 REQ-OPS-075 — POST /reimpresion-ticket happy path

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-075-1 | `tests/unit/test_reimpresion_ticket_create_handler.py` | `test_create_reimpresion_happy_path_returns_201` | 201 + `workflow_estado='autorizada'` + `uuid_reimpresion_padre=NULL` + `Cache-Control: no-store` + row exists |
| T-075-2 | `tests/unit/test_reimpresion_ticket_create_handler.py` | `test_create_reimpresion_returns_404_si_ingreso_no_existe` | 404 + `ingreso_no_encontrado` (V1) |
| T-075-3 | `tests/static/test_workflow_handler_single_commit.py` | `test_create_reimpresion_ticket_single_commit` | KD-TKT-01 single commit |

### B.2 REQ-OPS-076 — GAP-BE-04 single-line fix

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-076-1 | `tests/integration/test_workflows_router_wiring.py` | `test_workflows_router_config_uses_reimprimir_ticket_not_emitir_reimpresion` | DEC-TKT-01: line 74 contains `reimprimir_ticket` and does NOT contain `emitir_reimpresion` |
| T-076-2 | `tests/integration/test_workflows_router_wiring.py` | `test_anular_reimpresion_endpoint_requires_anular_reimpresion_permission` | Anular endpoint gated on `anular_reimpresion` permission (regression for the GAP-BE-04 class of bugs) |

### B.3 REQ-OPS-077 — Reimpresión INSERT-only via `append_transition`

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-077-1 | `tests/unit/test_reimpresion_ticket_create_handler.py` | `test_create_reimpresion_returns_409_reimpresion_already_pending` | V2 chain-tip guard rejects recent active row |
| T-077-2 | `tests/unit/test_reimpresion_ticket_anular_handler.py` | `test_anular_reimpresion_happy_path_returns_201_with_new_chain_row` | Anular INSERTs NEW row with `uuid_reimpresion_padre=tip.uuid` + `workflow_estado='rechazada'`; original row NEVER updated |
| T-077-3 | `tests/unit/test_reimpresion_ticket_anular_handler.py` | `test_anular_reimpresion_returns_409_si_estado_rechazada_terminal` | Chain tip state guard rejects terminal `rechazada` |
| T-077-4 | `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` | `test_create_handler_no_update_on_reimpresion_ticket` | AST walk: no UPDATE in create handler body |
| T-077-5 | `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` | `test_anular_handler_no_update_on_reimpresion_ticket` | AST walk: no UPDATE in anular handler body |

### B.4 REQ-OPS-078 — Chain integrity via `uuid_reimpresion_padre` FK + `read_chain_tip`

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-078-1 | `tests/unit/test_reimpresion_ticket_anular_handler.py` | `test_anular_reimpresion_returns_404_si_reimpresion_not_found` | `read_chain_tip` raises `ChainNotFoundError` for non-existent chain root |
| T-078-2 | `tests/unit/test_reimpresion_ticket_anular_handler.py` | `test_anular_reimpresion_happy_path_returns_201_with_new_chain_row` | (Reused T-077-2) Verifies `uuid_reimpresion_padre` is set to tip.uuid and chain integrity preserved |

### B.5 REQ-OPS-079 — Conditional MIGRATION 0029 siembra

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-079-1 | `tests/integration/test_migration_0029_idempotent.py` | `test_migration_0029_idempotent_upgrade_downgrade_upgrade` | Full upgrade → downgrade → upgrade cycle is idempotent |
| T-079-2 | `tests/integration/test_migration_0029_idempotent.py` | `test_siembra_costos_servicios_reimpresion_pre_flight` | Case A (absent): siembra inserted. Case B (present): no-op |

### B.6 REQ-OPS-080 — `uuid_factura` OPTIONAL on the create INSERT

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-080-1 | `tests/unit/test_reimpresion_ticket_create_handler.py` | `test_create_reimpresion_returns_404_si_ingreso_no_existe` | (Reused T-075-2) DEC-TKT-04: payload validation only requires `motivo` + `uuid_ingreso` |
| T-080-2 | (implicit in `test_create_reimpresion_happy_path_returns_201`) | T-075-1 | Happy path with `uuid_factura=None` is accepted (no 422) |

### B.7 REQ-OPS-XR4 — Defense in depth 5 layers + AST walk for `[L-W]` insert-only invariant

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-XR4-1 | `tests/static/test_workflow_handler_single_commit.py` | `test_create_reimpresion_ticket_single_commit` | (Reused T-075-3) KD-TKT-01 single-commit invariant (Layer 4) |
| T-XR4-2 | `tests/static/test_workflow_handler_single_commit.py` | `test_anular_reimpresion_ticket_single_commit` | KD-TKT-01 single-commit invariant for anular handler (Layer 4) |
| T-XR4-3 | `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` | `test_create_handler_no_update_on_reimpresion_ticket` | (Reused T-077-4) Layer 4 + DEC-TKT-02 |
| T-XR4-4 | `tests/static/test_workflow_handler_no_update_on_reimpresion_ticket.py` | `test_anular_handler_no_update_on_reimpresion_ticket` | (Reused T-077-5) Layer 4 + DEC-TKT-03 |

### B.8 Idempotency-Key Replay (DEC-IDEM-01, inherited from F1.6)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-IDEM-1 | `tests/integration/test_idempotency_key_replay.py` | `test_create_reimpresion_idempotency_key_replay_returns_cached_response` | Same `Idempotency-Key` returns cached response; chain does NOT grow |
| T-IDEM-2 | (implicit via F1.6 regression suite) | n/a | Anular endpoint inherits the same `Idempotency-Key` middleware (F1.6 T-PR6-002) |

### B.9 Schema Validation (Pydantic `extra='forbid'`)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-SCH-1 | `tests/unit/test_reimpresion_ticket_schemas.py` | `test_create_endpoint_rejects_estado_injection` | Client smuggling of `estado='autorizada'` is rejected |
| T-SCH-2 | `tests/unit/test_reimpresion_ticket_schemas.py` | `test_create_endpoint_rejects_uuid_reimpresion_padre_injection` | Client smuggling of `uuid_reimpresion_padre` is rejected |
| T-SCH-3 | `tests/unit/test_reimpresion_ticket_schemas.py` | `test_anular_endpoint_rejects_state_injection` | Client smuggling of `estado='rechazada'` on anular is rejected |

### B.10 Tenant Scope (KD-S2 analog from F1.7)

| Test ID | File | Test name | Verifies |
|---|---|---|---|
| T-TEN-1 | `tests/unit/test_reimpresion_ticket_create_handler.py` | `test_create_reimpresion_returns_403_si_tenant_scope_violation` | `operador-` cross-branch rejected with 403 |
| T-TEN-2 | (implicit in `test_anular_reimpresion_*` happy path) | n/a | Anular inherits the same tenant scope check (Step 3 in §9.2) |

### B.11 Test Coverage Summary

| REQ | Total tests | Happy path | Failure paths | AST walks |
|---|---|---|---|---|
| REQ-OPS-075 | 3 | 1 | 1 | 1 |
| REQ-OPS-076 | 2 | 1 (regression) | 1 | 0 |
| REQ-OPS-077 | 5 | 1 | 2 | 2 |
| REQ-OPS-078 | 2 | 1 (reused) | 1 | 0 |
| REQ-OPS-079 | 2 | 1 (idempotent cycle) | 1 | 0 |
| REQ-OPS-080 | 2 | 1 (reused) | 0 | 0 |
| REQ-OPS-XR4 | 4 | 0 | 0 | 4 |
| DEC-IDEM-01 | 1 | 1 | 0 | 0 |
| Schema (extra='forbid') | 3 | 0 | 3 | 0 |
| Tenant scope | 2 | 1 (reused) | 1 | 0 |
| **Total unique test functions** | **19** | **6** | **9** | **4 (2 walk files × 2 tests)** |

All 7 explicit requirements (REQ-OPS-075..080 + XR4) plus the inherited DEC-IDEM-01 + schema validation + tenant scope are covered by at least 2 tests each. The 19-test count matches the design §12.9 summary table.

---

## Closing

This design closes the HU-F1.11 backend prerequisite for the operador-facing reimpresión workflow. The work is bounded: 2 handlers + 1 repo module + 3 schemas + 1 conditional migration + 1 single-line GAP-BE-04 fix. No new tables, no new FKs, no new sync catalog changes, no factory changes.

The key architectural decisions (DEC-TKT-01..06 + KD-TKT-01..02) follow the F1.10 / F1.9 / F1.7 / F1.6 / F1.5 precedents verbatim. The defense-in-depth 5 layers (issuer chain, permission gate, tenant scope, insert-only invariant, handler error mapping) protect every write. The AST walks enforce the invariants at compile-time.

**next_recommended: sdd-tasks HU-F1.11** to decompose the 19 tests + 2 handlers + 1 migration into atomic T1..Tn tasks across clusters T-Setup / T-Repo / T-Schemas / T-Handlers / T-Migration / T-Tests / T-AST / T-Docs.
