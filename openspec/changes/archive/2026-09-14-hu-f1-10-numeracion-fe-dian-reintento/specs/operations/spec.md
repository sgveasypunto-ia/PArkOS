# Delta Spec: operations — hu-f1-10-numeracion-fe-dian-reintento

> **Delta for change**: `hu-f1-10-numeracion-fe-dian-reintento`
> **Capability**: `operational`
> **Date**: 2026-09-14
> **Source of truth**: `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-proposal.md` (16 sections, ~700 LOC), `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-explore.md` (16 sections, ~970 LOC, observation #1568)
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F1.10 (Fase-1 prerequisites — backend)
> **Precedente upstream**: this delta extends the `operational` capability already consolidated in `openspec/specs/operations/spec.md` (last REQ-OPS-NNN vigente: **REQ-OPS-063** after the merge of HU-F1.9 in commit `47d5630`). HU-F1.10 introduces **11 new requirements** (`REQ-OPS-064..074`) covering the three endpoints (`POST /api/v1/facturacion/factura-electronica`, `GET /api/v1/facturacion/factura-electronica/{uuid}`, `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar`), the six server-side validations (V1 `factura_no_encontrada`, V2 `factura_electronica_ya_existe` with DB partial UK defense, V3 `resolucion_no_vigente`, V4 rango_exhausto `numeracion_agotada` + alerta, V5 chain tip `reintento_no_permitido` / `envio_dian_already_pending`, V6 status quo), the KD-FE-01 single-commit invariant, the KD-FE-02 SELECT FOR UPDATE reuse from F1.9's `assign_consecutivo`, the DEC-FE-01 branch-initiated `envio_dian` with sync catalog flip (MIGRATION 0028 Op 1), the DEC-FE-02 retry chain via NEW row + `uuid_envio_padre` (NEVER UPDATE), the DEC-FE-03 range exhaustion → 409 + alerta, the DEC-FE-04 retry guard on `aceptado`, and the DEC-FE-05 `assign_consecutivo` reused as-is. REQ-OPS-001..063 remain unchanged.
> **Inputs** (full traceability): `plan.md` lines 939-979 (HU-F1.10, 4 atomic tasks T1..T4, 230 LOC budget), `plan.md` línea 951 (forbidden `SIM-YYYY-MM-DD-NNNNNN` fallback), `plan.md` línea 949 (alerta `fe_numbering_exhausted` already seeded), `modelo_datos_er.mmd` lines 689-705 (`prod.factura_electronica` `[L-E]` snapshot pattern) + 891-914 (`prod.envio_dian` `[L-W]` self-FK chain — post-archive comment update from "CLOUD-ONLY" to "BRANCH-INITIATED"), `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 875-891 (`factura_electronica` create_table + UK01 `(uuid_resolucion_facturacion, consecutivo)`) + 976-993 (`envio_dian` create_table + UK02 `(uuid_factura_electronica, uuid_envio_padre)`) + 1595-1842 (FKs) + 2646-2712 (audit/versioning triggers) + 2864-2900 (sync enqueue triggers), `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109 (`prod.v_factura_electronica_acuse` view, `DISTINCT ON (uuid_factura_electronica) ORDER BY timestamp_evento DESC`), `backend/packages/parkos_core/migrations/versions/0027_*` (F1.9 head), `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py` (LifecycleEventBase), `backend/packages/parkos_core/src/parkos_core/models/L_W/envio_dian.py` (WorkflowBase + self-FK `uuid_envio_padre` + `cufe` + `estado`), `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` (VersionedBase, bi-temporal, `prefijo` + `rango_desde`/`rango_hasta`, NO `consecutivo_actual` per 4NF), `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo` (verified, lines 99-108 idempotency, lines 114-120 SELECT FOR UPDATE, lines 143-147 `ConsecutivoRangeExhaustedError`), `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (F1.9 handler pattern verbatim), `backend/packages/parkos_core/src/parkos_core/repo/workflow.py::read_chain_tip` (F1.5 PR5-016), `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py::AlertaFactory` (F1.8 T-PR8-002), `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136 (`envio_dian` `cloud_to_branch` direction per D1-rev — **FLIPPED in DEC-FE-01 / MIGRATION 0028 Op 1**), `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/{exploration,proposal,design,tasks,verify-report,archive-report}.md` (precedent KD-3 issuer + 12-step handler + KD-FACT-01 single-commit + AST walks), `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/{exploration,proposal,design,tasks,verify-report,archive-report}.md` (precedent KD-S2 tenant scope, `one_exit_per_ingreso` partial UK), `openspec/specs/operations/spec.md` (66 REQs REQ-OPS-001..063 merged post-F1.9).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `47d5630`) · **PR target**: `origin/dev`.
> **Note on DEC-FE-01**: `envio_dian` writes are branch-initiated. plan.md línea 953 is canonical; ER `CLOUD-ONLY` comment (modelo_datos_er.mmd línea 892) is updated post-archive in a separate PR; sync catalog flipped via MIGRATION 0028 Op 1 (pre-flight + `UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian' AND direction='cloud_to_branch'`). Downgrade reverses the flip.

> **Pre-apply verification findings** (incorporated into this delta):
>
> - **R1 RESOLVED (DEC-FE-01)**: Architectural conflict on `envio_dian` ownership — plan.md línea 953 mandates branch INSERTs; ER línea 892 says CLOUD-ONLY; sync catalog says `cloud_to_branch`. Resolution per plan.md (canonical authority): branch INSERTs; sync catalog flipped in MIGRATION 0028 Op 1; ER comment updated post-archive. Documented in proposal §3.
> - **R2 MEDIUM (REQ-OPS-073)**: Vigente resolution lookup at handler entry — V3 SELECT must defensively `ORDER BY vigente_desde DESC LIMIT 1 WHERE vigente_hasta IS NULL AND estado='activo'` to handle a corrupt DB with multiple vigente rows. New helper `repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal`.
> - **R3 MEDIUM (REQ-OPS-070)**: Chain integrity via `uuid_envio_padre` FK — existing UK02 `(uuid_factura_electronica, uuid_envio_padre)` per migration 0001 línea 901 enforces chain integrity. Reuses `repo/workflow.read_chain_tip` (F1.5 PR5-016).
> - **R4 LOW**: DIAN web service integration — MVP mocks the response; real integration deferred to Fase 4. `/reintentar` only INSERTs a new `envio_dian` row, never calls DIAN synchronously.
> - **R5 LOW (REQ-OPS-074)**: Prefijo snapshot on `prod.factura_electronica` at INSERT time — the prefijo is denormalized from `prod.resolucion_facturacion` and is the historical truth. 4NF + plan.md línea 697 correct. No mitigation beyond documentation.

## Purpose

HU-F1.10 closes the **DIAN regulatory extension** on top of F1.9's internal billing by exposing three handlers that together materialize the fiscal side-car:

- `POST /api/v1/facturacion/factura-electronica` — given a paid `prod.facturas.uuid`, the branch server-assigns `prefijo`+`consecutivo` via the existing `assign_consecutivo` helper (SELECT FOR UPDATE on `prod.resolucion_facturacion`), INSERTs a `prod.factura_electronica` row (1:1 with the internal factura), and INSERTs the initial `prod.envio_dian` row with `estado='pendiente'` and `uuid_envio_padre=NULL`.
- `GET /api/v1/facturacion/factura-electronica/{uuid}` — JOINs the existing `prod.v_factura_electronica_acuse` view (migration 0009, already present) to expose the raw `estado` (`pendiente|enviado|aceptado|rechazado`) and the latest `cufe` + `timestamp_evento` (never a fabricated `reportado_dian` boolean).
- `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` — INSERTs a **NEW** `prod.envio_dian` row with `uuid_envio_padre` pointing at the previous chain tip. **NEVER UPDATE.** The retry chain is the audit trail of every transition.

The handler enforces **six server-side validations V1..V6**: (V1) `prod.facturas.uuid` exists → 404 `factura_no_encontrada`; (V2) NO existing `prod.factura_electronica` row for `uuid_factura` → 409 `factura_electronica_ya_existe` (with DB-layer partial UK `one_fe_per_factura` defense in depth); (V3) vigente `prod.resolucion_facturacion` row for the sucursal → 409 `resolucion_no_vigente`; (V4) range exhaustion on `assign_consecutivo` → 409 `numeracion_agotada` + alerta `fe_numbering_exhausted`; (V5) on `/reintentar`, chain tip state guards → 409 `reintento_no_permitido` (on `aceptado`) or 409 `envio_dian_already_pending` (on `pendiente`); (V6) status quo (no extra validation; happy path). KD-FE-01 single-commit invariant mirrors F1.9's KD-FACT-01: a single `await session.commit()` materializes the FE row + initial envio row atomically. KD-FE-02 is the F1.9 `assign_consecutivo` SELECT FOR UPDATE (already in place; reused as-is per DEC-FE-05). DEC-FE-01 mandates branch-initiated `envio_dian` writes and flips the sync catalog from `cloud_to_branch` to `branch_to_cloud` in MIGRATION 0028 Op 1. DEC-FE-02 mandates retry chain via NEW row + `uuid_envio_padre` (NEVER UPDATE on user-meaningful fields). DEC-FE-03 mandates 409 `numeracion_agotada` + alerta on range exhaustion. DEC-FE-04 mandates 409 `reintento_no_permitido` on `aceptado` chain tips.

**Defense in depth (5 layers)** mirrors the F1.9 precedent: (a) KD-3 issuer chain `_fe_issuer_dep = requires_issuer("operador-", "admin-")`; (b) tenant scope post-V1 (KD-S2 analog from F1.7); (c) DB-layer partial unique index `one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL` (MIGRATION 0028 Op 2 — closes the V2 SELECT-before-INSERT race window); (d) `assign_consecutivo` SELECT FOR UPDATE on `prod.resolucion_facturacion` (already in place per F1.9 / T-PR9-002 / D1-rev); (e) handler 409 mapping for `numeracion_agotada`, `reintento_no_permitido`, `envio_dian_already_pending`, `factura_electronica_ya_existe`.

> **Migration 0028 ops**: (Op 1) pre-flight `ASSERT` that the 4 tables exist + sync catalog flip (`UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian' AND direction='cloud_to_branch'`); (Op 2) partial unique index `one_fe_per_factura` (`CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`); (Op 3) covering index `idx_envio_dian_chain_tip (uuid_factura_electronica, timestamp_evento DESC) WHERE uuid_factura_electronica IS NOT NULL` (`CREATE INDEX CONCURRENTLY IF NOT EXISTS`); (Op 4) defensive `GRANT` re-assertion for `rol_app`; (Downgrade) reverse order, superuser context for `DROP INDEX CONCURRENTLY`, reverse the sync catalog flip.

---

## ADDED Requirements

### REQ-OPS-064 — Server-assigns `prefijo`+`consecutivo` via `assign_consecutivo` (SELECT FOR UPDATE on `prod.resolucion_facturacion`)

**Level**: SHALL. **Statement**: The branch MUST assign `prefijo`+`consecutivo` to a new `prod.factura_electronica` row by calling `repo/resolucion_facturacion.py::assign_consecutivo(session, *, resolucion_uuid, source_event_uuid) -> int` (verified signature, lines 97-149) with the vigente `prod.resolucion_facturacion` row's `uuid` for the factura's sucursal. The helper MUST take `SELECT ... FOR UPDATE` on the resolution row (lines 114-120) and increment the next consecutive value atomically within the request's TX. The prefijo is snapshotted separately from the vigente resolution row at INSERT time (REQ-OPS-074).

**Rationale**: plan.md línea 953 mandates `assign_consecutivo` (real numeración, NOT fallback `SIM-YYYY-MM-DD-NNNNNN` per línea 951). DIAN Resolución 000175 de 2021 + Decreto 2242 de 2015 require contiguous numbering inside the authorized `rango_desde`..`rango_hasta` range. The SELECT FOR UPDATE closes the concurrent assignment race at the row level.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py` lines 97-149 (helper verified 2026-09-14); `plan.md` línea 953.

#### Scenario 1: Happy path — `assign_consecutivo` returns next consecutivo and INSERT proceeds

**Given** a paid `prod.facturas.uuid=:f` with `uuid_sucursal=:s` and `estado` derivado `in {emitida, pagada}`
**And** a vigente `prod.resolucion_facturacion` row with `uuid=:r`, `prefijo='FE'`, `rango_desde=1`, `rango_hasta=5000`, `vigente_hasta IS NULL`, `estado='activo'`
**And** `COALESCE(MAX(consecutivo), 0)` over `prod.factura_electronica` WHERE `uuid_resolucion_facturacion=:r` returns `41`
**When** the handler reaches Step 6 of `create_factura_electronica` and invokes `await assign_consecutivo(session, resolucion_uuid=:r, source_event_uuid=:f)`
**Then** the helper MUST take `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion WHERE uuid=:r` (lock held until `await session.commit()` at Step 11)
**And** MUST return `int(41 + 1) = 42` (`next_value=42`).
**And** MUST NOT raise `ConsecutivoRangeExhaustedError` (since `42 <= rango_hasta=5000`).
**And** Step 7 of the handler MUST INSERT a `prod.factura_electronica` row with `prefijo='FE'` (from `:r`) and `consecutivo=42`.
**And** the handler MUST respond `201 Created` with `FacturaElectronicaRead{prefijo:'FE', consecutivo:42, ...}` and `Cache-Control: no-store`.

#### Scenario 2: Idempotency on retry of same `(resolucion_uuid, source_event_uuid)`

**Given** a prior successful POST that INSERTed `prod.factura_electronica(consecutivo=42)` for `(resolucion_uuid=:r, uuid_factura=:f)`
**When** the same client POSTs `/api/v1/facturacion/factura-electronica` with `{"uuid_factura":":f"}` again (same `Idempotency-Key` or natural retry)
**Then** `assign_consecutivo` MUST execute the idempotency check at lines 99-108 FIRST and MUST return `int(42)` directly without taking any lock or running `MAX(consecutivo)+1`.
**And** the handler MUST NOT INSERT a NEW `prod.factura_electronica` row (the SELECT-by-`uuid_factura` in V2 catches it before INSERT and returns 409 `factura_electronica_ya_existe`).
**And** no NEW `prod.resolucion_facturacion` consecutivo MUST be consumed (idempotency invariant).

#### Scenario 3: Concurrent POSTs on the same resolution serialize cleanly

**Given** two concurrent TXs both POSTing `/api/v1/facturacion/factura-electronica` for the same `:f` with the same resolution `:r`
**When** both TXs invoke `assign_consecutivo(session, resolucion_uuid=:r, source_event_uuid=:f)` simultaneously
**Then** the FIRST TX MUST acquire `SELECT ... FOR UPDATE` on `:r` and proceed to compute `consecutivo=42`.
**And** the SECOND TX MUST block at the SELECT FOR UPDATE until the FIRST TX commits.
**And** after the FIRST TX commits, the SECOND TX MUST acquire the lock and proceed to compute `consecutivo=43` (atomic MAX()+1 over the now-committed state).
**And** NO gap in the consecutivo sequence MUST be introduced (DIAN numbering contiguity invariant).

#### Scenario 4: 4NF snapshot pattern — `prefijo` snapshot is independent of later resolution changes

**Given** a vigente resolution `:r` with `prefijo='FE'` at INSERT time
**When** the FE row is INSERTed with `prefijo='FE'` and `consecutivo=42`
**Then** `prod.factura_electronica.prefijo='FE'` is a denormalized snapshot.
**And** a later `UPDATE prod.resolucion_facturacion SET prefijo='FX' WHERE uuid=:r` MUST NOT retroactively alter `prod.factura_electronica.prefijo` (4NF — the FE's prefijo is the historical truth at INSERT time).
**And** a later bi-temporal versioning of `:r` (close + new row with new `prefijo='FX'`) MUST also NOT alter `prod.factura_electronica.prefijo`.

#### Definition of Done for REQ-OPS-064

- MIGRATION 0028 (or earlier) does NOT modify `assign_consecutivo`; the helper is reused verbatim from F1.9 / T-PR9-002 / D1-rev.
- The handler Step 6 of `create_factura_electronica` calls `await assign_consecutivo(session, resolucion_uuid=:r, source_event_uuid=uuid_factura)` with the resuelción's `uuid` from V3 (REQ-OPS-073).
- Unit test `tests/unit/test_factura_electronica_repo.py::test_assign_consecutivo_for_fe_returns_next_value` PASSES (returns 42 for MAX=41, range=1..5000).
- Integration test `tests/integration/test_factura_electronica_atomicidad_db.py::test_concurrent_post_serializes_consecutivos` PASSES (two concurrent TXs commit with consecutivos 42 and 43, no gap).
- `Cache-Control: no-store` header verified on 201 / 409 / 500 responses (REQ-OPS-XR2 from F1.9).

### REQ-OPS-065 — Initial `prod.envio_dian` row with `estado='pendiente'` is INSERTed in the SAME `await session.commit()` as the `prod.factura_electronica` INSERT (KD-FE-01 single-commit)

**Level**: SHALL. **Statement**: The branch MUST INSERT a `prod.envio_dian` row with `estado='pendiente'`, `uuid_envio_padre=NULL`, `cufe=NULL`, `respuesta_proveedor=NULL`, `payload={prefijo, consecutivo, uuid_factura}` (JSONB snapshot) in the SAME `await session.commit()` as the `prod.factura_electronica` INSERT. KD-FE-01 single-commit invariant is the mirror of F1.9 KD-FACT-01.

**Rationale**: An `envio_dian` chain without its parent FE is an audit orphan; an FE without its initial envio is a fiscal breach (DIAN requires the submission trail to exist from the moment of numbering). Single-commit atomicity closes both risks.

**Source**: plan.md línea 953; F1.9 KD-FACT-01 (REQ-OPS-060).

#### Scenario 1: Atomic insert — both rows visible together to subsequent SELECTs

**Given** a paid `prod.facturas.uuid=:f` and a vigente resolution `:r` with `prefijo='FE'` and `rango_hasta=5000`
**When** the handler reaches Step 11 of `create_factura_electronica` and calls `await session.commit()` after Steps 7 (INSERT FE) and Step 10 (INSERT envio_dian)
**Then** exactly one `prod.factura_electronica` row MUST exist for `:f` (UK01 on `(uuid_resolucion_facturacion, consecutivo)` enforces uniqueness).
**And** exactly one `prod.envio_dian` row MUST exist with `uuid_factura_electronica = <fe.uuid>` AND `uuid_envio_padre IS NULL` AND `estado='pendiente'` AND `cufe IS NULL`.
**And** both rows MUST be visible to subsequent SELECTs in the same session (no isolation drift).

#### Scenario 2: Atomic rollback on FK violation — neither row persisted

**Given** the handler Step 7 (INSERT FE) succeeds but Step 10 (INSERT envio_dian) raises a FK violation (e.g. `uuid_resolucion_facturacion=:fake` not found)
**When** the request returns 5xx
**Then** `await session.commit()` MUST NOT be called (single-commit invariant, KD-FE-01).
**And** NEITHER the FE row NOR the envio_dian row MUST be persisted (single TX rollback).
**And** the partial unique index `one_fe_per_factura` MUST NOT have a pending entry (no half-applied state).

#### Scenario 3: Prefijo+consecutivo denormalized onto `envio_dian.payload`

**Given** `prod.factura_electronica` has `prefijo='FE'` and `consecutivo=42`
**When** the initial `prod.envio_dian` row is INSERTed
**Then** `envio_dian.payload` MUST include `prefijo='FE'` AND `consecutivo=42` AND `uuid_factura=:f` (JSONB denormalized snapshot for the cloud dispatcher to consume).
**And** the handler MUST NOT include any PII in `payload` (no `cliente.email`, no `cliente.telefono`, no `direccion`); the cloud dispatcher reconstructs the full payload from the sync replication.

#### Scenario 4: Initial row has `uuid_envio_padre IS NULL`

**Given** a fresh POST request (not a retry)
**When** the initial `prod.envio_dian` row is INSERTed
**Then** `envio_dian.uuid_envio_padre IS NULL` MUST hold (first row in the chain; the chain tip is the row itself).
**And** `envio_dian.uuid_factura_electronica = <fe.uuid>` MUST hold (NOT NULL FK).
**And** `envio_dian.estado='pendiente'` MUST hold (cloud dispatcher hasn't picked it up yet).

#### Definition of Done for REQ-OPS-065

- Handler Step 10 INSERTs the initial `envio_dian` row in the same `await session.commit()` as Step 7's FE INSERT (no intermediate commit).
- AST walk `tests/static/test_fe_handler_single_commit.py` PASSES (asserts `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(n.value.func, 'attr', '') == 'commit']) == 1`).
- Integration test `tests/integration/test_factura_electronica_atomicidad_db.py::test_rollback_no_orphan_fe_or_envio` PASSES.
- Unit test `tests/unit/test_factura_electronica_repo.py::test_crear_envio_dian_reintento_initial_no_padre` PASSES (initial row has `uuid_envio_padre IS NULL`).

### REQ-OPS-066 — Range exhaustion → HTTP 409 `numeracion_agotada` + alerta `fe_numbering_exhausted` fired in same TX (DEC-FE-03)

**Level**: MUST. **Statement**: When `assign_consecutivo` raises `ConsecutivoRangeExhaustedError` (verified, helper source lines 143-147 — `next_value > rango_hasta`), the handler MUST catch the typed exception, fire the already-seeded alerta `fe_numbering_exhausted` via `repo/alert_types.py::AlertaFactory(session, ctx).fire(...)` in the SAME TX, and return HTTP `409 Conflict` with body `{"error":"numeracion_agotada", "uuid_resolucion_facturacion":"<uuid>", "rango_hasta":<int>, "prefijo":"<str>"}`. The pgcode MUST NEVER appear in the response body, headers, or info+ logs.

**Rationale**: plan.md línea 949 mandates the alerta; línea 951 explicitly forbids the `SIM-YYYY-MM-DD-NNNNNN` fallback; the typed 409 body gives the operator enough context to request a new resolution from DIAN.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py` lines 143-147 (verified); `plan.md` líneas 949-951; `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py::AlertaFactory` (F1.8 T-PR8-002).

#### Scenario 1: Range exhausted — handler catches, fires alerta, returns 409

**Given** a resolution `:r` with `prefijo='FE'`, `rango_desde=1`, `rango_hasta=5000`, vigente
**And** `COALESCE(MAX(consecutivo), 0)` over `prod.factura_electronica` for `:r` returns `5000` (range fully consumed)
**When** the handler invokes `await assign_consecutivo(session, resolucion_uuid=:r, source_event_uuid=:f)`
**Then** the helper MUST raise `ConsecutivoRangeExhaustedError("resolucion_facturacion :r range exhausted: next consecutivo 5001 exceeds rango_hasta=5000")`.
**And** the handler MUST catch the exception in Step 6 of `create_factura_electronica`, MUST fire `AlertaFactory(session, ctx).fire("fe_numbering_exhausted", motivo=str(exc))` BEFORE raising the HTTP 409.
**And** MUST return `409 Conflict` with body `{"error":"numeracion_agotada","uuid_resolucion_facturacion":":r","rango_hasta":5000,"prefijo":"FE"}` and `Cache-Control: no-store`.
**And** the response body MUST NOT contain `"22000"`, the literal text `"range exhausted"`, or any pgcode.

#### Scenario 2: No FE row, no envio_dian row on exhaustion

**Given** the range-exhausted state above
**When** POST `/api/v1/facturacion/factura-electronica` returns 409 `numeracion_agotada`
**Then** `prod.factura_electronica` MUST have zero new rows for `:f`.
**And** `prod.envio_dian` MUST have zero new rows for `:f` (Step 7 INSERT is gated by successful `assign_consecutivo`).
**And** `prod.alertas` MUST have exactly one NEW row with `tipo_alerta='fe_numbering_exhausted'`, `estado='abierta'`, and `datos_nuevos` carrying `{uuid_resolucion_facturacion, rango_hasta, prefijo, uuid_factura}` for operator diagnostics.

#### Scenario 3: Alerta payload includes range context for operator triage

**Given** the range-exhausted state and a successful alerta INSERT
**When** the operator queries `prod.alertas WHERE tipo_alerta='fe_numbering_exhausted' ORDER BY created_at DESC LIMIT 1`
**Then** the alerta row MUST include `datos_nuevos.uuid_resolucion_facturacion = :r` AND `datos_nuevos.rango_hasta = 5000` AND `datos_nuevos.prefijo = 'FE'` AND `datos_nuevos.uuid_factura = :f` (jsonb).
**And** the alerta MUST be fired with `actor_uuid = ctx.actor_uuid` and `uuid_sucursal = :s` (F1.8 `AlertaFactory` API).

#### Definition of Done for REQ-OPS-066

- MIGRATION 0028 does NOT add the alerta seed (already seeded in `0010_add_alert_types.py` per `plan.md` línea 949 + `repo/alert_types.py::AlertaFactory`).
- Handler Step 6 catch block fires `AlertaFactory(...).fire('fe_numbering_exhausted', motivo=str(exc))` and maps to `409 numeracion_agotada`.
- Unit test `tests/unit/test_factura_electronica_create_handler.py::test_create_fe_returns_409_numeracion_agotada_alerta_fired` PASSES (range=5000 with MAX=5000 → 409 + alerta row).
- Integration test verifies `prod.alertas` row created with the expected `tipo_alerta='fe_numbering_exhausted'` and JSONB payload.

### REQ-OPS-067 — At most one vigente `prod.factura_electronica` row per `prod.facturas.uuid` (V2 + DB partial UK `one_fe_per_factura`)

**Level**: MUST. **Statement**: The system MUST enforce at most one `prod.factura_electronica` row per `prod.facturas.uuid`. The application-layer V2 SELECT-before-INSERT (Step 4 of `create_factura_electronica`) is the primary guard; the DB-layer partial unique index `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL` (MIGRATION 0028 Op 2) is the defense-in-depth layer that closes the TOCTOU race between two concurrent POSTs that both pass V2. A `psycopg2.errors.UniqueViolation` (pgcode `23505`) MUST be caught by the handler and mapped to `409 Conflict` with body `{"error":"factura_electronica_ya_existe", "uuid_factura":"<uuid>"}`. The pgcode MUST NEVER appear in the response body, headers, or info+ logs.

**Rationale**: plan.md línea 953 mandates one FE per internal factura; the F1.9 `one_factura_per_salida` partial UK (migration 0027) transitively enforces this when `uuid_factura` is NOT NULL, but the partial UK on FE is the direct invariant. Defense in depth against concurrent cajeros or operator mis-clicks.

**Source**: `plan.md` línea 953; `backend/packages/parkos_core/migrations/versions/0027_*` precedent (`one_factura_per_salida`); F1.7 `one_exit_per_ingreso` precedent (migration 0026 Op 4).

#### Scenario 1: First POST creates the FE row

**Given** a paid `prod.facturas.uuid=:f` with no existing `prod.factura_electronica` row
**When** the client POSTs `/api/v1/facturacion/factura-electronica` with `{"uuid_factura":":f"}`
**Then** the V2 SELECT-by-`uuid_factura` MUST return `None`.
**And** the handler MUST proceed to Step 5 (V3 resuelve resolution) and Step 6 (`assign_consecutivo`).
**And** exactly one `prod.factura_electronica` row MUST exist for `uuid_factura=:f` after the successful commit.

#### Scenario 2: Second POST returns 409 `factura_electronica_ya_existe`

**Given** an existing `prod.factura_electronica` row with `uuid_factura=:f` (created by the first POST in Scenario 1)
**When** the client POSTs `/api/v1/facturacion/factura-electronica` with `{"uuid_factura":":f"}` again (different `Idempotency-Key` or natural retry)
**Then** V2 MUST return the existing FE row (non-None).
**And** the handler MUST return `409 Conflict` with body `{"error":"factura_electronica_ya_existe", "uuid_factura":":f"}` and `Cache-Control: no-store`.
**And** NO second `prod.factura_electronica` row MUST be INSERTed (Step 5 onward is unreachable on V2 hit).
**And** the original FE row MUST remain unchanged.

#### Scenario 3: TOCTOU race past V2 — partial UK forces UniqueViolation

**Given** two concurrent TXs both POSTing `/factura-electronica` with `{"uuid_factura":":f}` simultaneously
**And** both pass V2 SELECT (both see `None` for `:f`)
**When** both TXs reach Step 7 INSERT `prod.factura_electronica(uuid_factura=:f, ...)`
**Then** the partial UK `one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL` MUST reject the second INSERT with `psycopg2.errors.UniqueViolation` (pgcode `23505`).
**And** the handler MUST catch the exception by pgcode (`pgcode == '23505'`), MUST NOT rely on Python `isinstance` alone.
**And** MUST translate to `HTTPException(status_code=409, detail={"error":"factura_electronica_ya_existe", "uuid_factura":":f"})`.
**And** the response body MUST NOT contain the substring `"23505"` or any pgcode reference.

#### Definition of Done for REQ-OPS-067

- MIGRATION 0028 Op 2 creates the partial UK `one_fe_per_factura` with `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`.
- Handler Step 4 performs the V2 SELECT-by-`uuid_factura` and returns 409 on hit.
- Handler catches `psycopg2.errors.UniqueViolation` (pgcode `23505`) on the INSERT path and maps to 409.
- Unit test `tests/unit/test_factura_electronica_create_handler.py::test_create_fe_returns_409_factura_electronica_ya_existe` PASSES.
- Integration test `tests/integration/test_factura_electronica_atomicidad_db.py::test_concurrent_post_uk_race` PASSES (two concurrent TXs → exactly one succeeds, the other returns 409).
- Downgrade of MIGRATION 0028 drops the partial UK.

### REQ-OPS-068 — GET endpoint JOINs `prod.v_factura_electronica_acuse` view (NEVER direct SELECT on `prod.envio_dian` for `envio_actual`)

**Level**: SHALL. **Statement**: The `GET /api/v1/facturacion/factura-electronica/{uuid}` endpoint MUST return a response shape `FacturaElectronicaRead` with `envio_actual: EnvioDianRead` whose `estado`, `cufe`, `timestamp_evento` are SERVER-DERIVED via JOIN against the existing `prod.v_factura_electronica_acuse` view (`backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109, `DISTINCT ON (uuid_factura_electronica) ORDER BY timestamp_evento DESC NULLS LAST, uuid DESC`). The handler MUST NEVER execute a direct SELECT against `prod.envio_dian` when computing `envio_actual` (the view is the single source of truth for the latest chain tip).

**Rationale**: The view already encodes the `DISTINCT ON … ORDER BY timestamp_evento DESC` semantic; querying `prod.envio_dian` directly would duplicate the logic and risk inconsistency between read paths. Centralizing on the view simplifies future ER changes (e.g. `envio_dian` partitioning) and enforces the "view is the canonical read path" convention (F1.7 + F1.9 precedent).

**Source**: `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109 (verified).

#### Scenario 1: Happy path — view returns the latest envio row

**Given** a `prod.factura_electronica` row with `uuid=:fe_uuid` and `consecutivo=42`
**And** one `prod.envio_dian` row with `uuid_factura_electronica=:fe_uuid`, `estado='aceptado'`, `cufe='abc123'`, `timestamp_evento='2026-09-14T10:00:00Z'`
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** the handler MUST JOIN `prod.v_factura_electronica_acuse WHERE uuid_factura_electronica=:fe_uuid`.
**And** MUST return `200 OK` with `FacturaElectronicaRead{envio_actual: EnvioDianRead{estado:'aceptado', cufe:'abc123', timestamp_evento:'2026-09-14T10:00:00Z', ...}}` and `Cache-Control: no-store`.

#### Scenario 2: No envio rows (defensive null mapping)

**Given** an FE row with `uuid=:fe_uuid` and zero `prod.envio_dian` rows (shouldn't happen after REQ-OPS-065 atomic insert, but defensive)
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** the view JOIN returns no row.
**And** the handler MUST return `200 OK` with `FacturaElectronicaRead{envio_actual: null, ...}` (defensive null mapping; the FE exists but the chain is empty).
**And** MUST NOT raise 404 or 5xx (this is a defensive read for legacy data, not an error).

#### Scenario 3: Multiple envio rows — view picks the latest by `timestamp_evento DESC`

**Given** an FE with 3 `prod.envio_dian` rows: `e1` with `estado='rechazado'`, `timestamp_evento='2026-09-14T08:00:00Z'`; `e2` with `estado='pendiente'`, `timestamp_evento='2026-09-14T09:00:00Z'`; `e3` with `estado='aceptado'`, `cufe='abc123'`, `timestamp_evento='2026-09-14T10:00:00Z'`
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** the view MUST return the LATEST row by `timestamp_evento DESC NULLS LAST, uuid DESC` (per `DISTINCT ON`).
**And** `envio_actual.estado='aceptado'` AND `envio_actual.cufe='abc123'` MUST be returned.

#### Definition of Done for REQ-OPS-068

- Handler Step 3 of `get_factura_electronica` SELECTs from `prod.v_factura_electronica_acuse` via `session.execute(text("SELECT estado, cufe, timestamp_evento, uuid FROM prod.v_factura_electronica_acuse WHERE uuid_factura_electronica = :uuid"))`.
- Handler MUST NOT query `prod.envio_dian` directly for `envio_actual` (enforced by code review + handler 3-step chain).
- MIGRATION 0028 Op 3 adds covering index `idx_envio_dian_chain_tip (uuid_factura_electronica, timestamp_evento DESC)` for the JOIN performance.
- Unit test `tests/unit/test_factura_electronica_get_handler.py::test_get_fe_returns_estado_aceptado_with_cufe` PASSES.
- Unit test `tests/unit/test_factura_electronica_get_handler.py::test_get_fe_returns_latest_envio_via_view` PASSES (3-row chain → latest by timestamp_evento DESC).

### REQ-OPS-069 — GET response `envio_actual` exposes `estado` (Literal) + `cufe` (nullable) + `timestamp_evento`; server NEVER fabricates `reportado_dian` boolean

**Level**: SHALL. **Statement**: The GET response `envio_actual: EnvioDianRead` MUST carry `estado` as `Literal["pendiente", "enviado", "aceptado", "rechazado"]`, `cufe` as `Annotated[str, StringConstraints(min_length=1, max_length=255)] | None`, and `timestamp_evento` as ISO-8601 UTC datetime. The server MUST NEVER fabricate a `reportado_dian` boolean (plan.md línea 947 FORBIDDEN); state is derived purely from `envio_dian.estado` via the view. `motivo_rechazo` MUST be exposed when present on the latest envio.

**Rationale**: 4NF compliance — state lives on `envio_dian`, not duplicated on `factura_electronica`. A fabricated `reportado_dian` boolean would create a denormalization that drifts from the source of truth. The `Literal` type forces the client to handle all four states explicitly.

**Source**: plan.md línea 947 (forbidden `reportado_dian`); ER `modelo_datos_er.mmd` línea 700 (`cufe y reportado_dian eliminados (4FN)`); migration 0001 lines 976-993 (`envio_dian.estado` enum).

#### Scenario 1: Aceptado with CUFE — both fields populated

**Given** an envio with `estado='aceptado'`, `cufe='abc123'`, `timestamp_evento='2026-09-14T10:00:00Z'`
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** `envio_actual.estado='aceptado'` AND `envio_actual.cufe='abc123'` AND `envio_actual.timestamp_evento='2026-09-14T10:00:00Z'` MUST be returned.
**And** the response MUST NOT include any `reportado_dian` field (server never fabricates it).

#### Scenario 2: Pendiente without CUFE — null mapping

**Given** an envio with `estado='pendiente'`, `cufe=NULL`, `timestamp_evento='2026-09-14T10:00:00Z'` (initial envio, cloud dispatcher hasn't picked it up yet)
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** `envio_actual.estado='pendiente'` AND `envio_actual.cufe=null` AND `envio_actual.timestamp_evento='2026-09-14T10:00:00Z'` MUST be returned.

#### Scenario 3: Rechazado with motivo_rechazo — full context exposed

**Given** an envio with `estado='rechazado'`, `cufe=NULL`, `motivo_rechazo='Error X: CUFE signature mismatch'`, `timestamp_evento='2026-09-14T10:00:00Z'`
**When** the client GETs `/api/v1/facturacion/factura-electronica/:fe_uuid`
**Then** `envio_actual.estado='rechazado'` AND `envio_actual.motivo_rechazo='Error X: CUFE signature mismatch'` MUST be returned.
**And** the response MUST allow `motivo_rechazo` to be `null` when the field is absent (e.g. `aceptado` envios have no motivo_rechazo).

#### Definition of Done for REQ-OPS-069

- Pydantic v2 schema `EnvioDianRead` with `estado: Literal["pendiente", "enviado", "aceptado", "rechazado"]`, `cufe: str | None`, `timestamp_evento: datetime`, `motivo_rechazo: str | None = None` (no `reportado_dian` field).
- `ER modelo_datos_er.mmd` línea 700 comment (`cufe y reportado_dian eliminados (4FN)`) preserved as-is.
- Unit tests `test_get_aceptado_with_cufe` + `test_get_pendiente_without_cufe` + `test_get_rechazado_with_motivo` PASS.

### REQ-OPS-070 — Retry INSERTs NEW `prod.envio_dian` row with `uuid_envio_padre` pointing at previous chain tip (NEVER UPDATE — DEC-FE-02)

**Level**: SHALL. **Statement**: The `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` endpoint MUST INSERT a NEW `prod.envio_dian` row with `uuid_envio_padre` pointing at the previous chain tip (the latest existing envio_dian row for the FE, identified via `repo/workflow.read_chain_tip` — F1.5 PR5-016). The endpoint MUST NEVER UPDATE existing envio rows (DEC-FE-02: the chain IS the audit trail). The `[L-W]` WorkflowBase MAY UPDATE `vigente_hasta` on the closed version for bi-temporal versioning, but user-meaningful fields (`estado`, `cufe`, `uuid_envio_padre`, `motivo_rechazo`) MUST be insert-only.

**Rationale**: 4NF compliance (state lives on `envio_dian.estado`, not duplicated on `factura_electronica`). Audit trail completeness (every transition is a row with `created_at`, `created_by`, `timestamp_evento`). Cloud-dispatcher-outage tolerance (the chain grows locally; cloud catches up via sync replication). DIAN audit requires immutable transitions per Resolución 000175 de 2021.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/workflow.py::read_chain_tip` (F1.5 PR5-016); `modelo_datos_er.mmd` lines 891-914; plan.md línea 953.

#### Scenario 1: First retry — chain grows by 1, original row unchanged

**Given** a `prod.factura_electronica` row `:fe` with one `prod.envio_dian` row `:e1` (the original, with `estado='rechazado'`, `uuid_envio_padre=NULL`)
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** `repo_factura_electronica.buscar_envio_dian_chain_tip(session, uuid_factura_electronica=:fe)` MUST return `:e1` (the latest by `timestamp_evento DESC`).
**And** the handler MUST INSERT a NEW `prod.envio_dian` row `:e2` with `uuid_factura_electronica=:fe`, `uuid_envio_padre=:e1`, `estado='pendiente'`, `cufe=NULL`, `payload=<snapshot>`.
**And** the original row `:e1` MUST remain unchanged (no UPDATE).
**And** the response MUST be `201 Created` with `EnvioDianRetryRead{uuid=:e2, uuid_factura_electronica=:fe, estado:'pendiente', uuid_envio_padre=:e1, timestamp_evento:<now>}`.

#### Scenario 2: Second retry — chain grows by 1, previous tip becomes non-tip

**Given** the state after Scenario 1 (`:fe` with `:e1` rechazo and `:e2` pendiente)
**And** `:e2` has `estado='rechazado'` (cloud dispatcher processed and rejected)
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar` again
**Then** `read_chain_tip` MUST return `:e2` (latest by timestamp_evento DESC).
**And** a NEW `:e3` MUST be INSERTed with `uuid_envio_padre=:e2` (chain tip moves to `:e3`).
**And** `:e1` and `:e2` MUST remain unchanged.

#### Scenario 3: Chain reconstruction via recursive SELECT on `uuid_envio_padre`

**Given** an FE `:fe` with 5 envio_dian rows `:e1`, `:e2`, `:e3`, `:e4`, `:e5` forming a chain (each row's `uuid_envio_padre` = previous row's `uuid`, except `:e1` which is `NULL`)
**When** a recursive WITH query `WITH RECURSIVE chain AS (SELECT * FROM prod.envio_dian WHERE uuid_factura_electronica=:fe AND uuid_envio_padre IS NULL UNION ALL SELECT e.* FROM prod.envio_dian e JOIN chain c ON e.uuid_envio_padre = c.uuid) SELECT uuid, uuid_envio_padre, estado, timestamp_evento FROM chain ORDER BY timestamp_evento ASC` executes
**Then** the chain MUST be reconstructed in order: `:e1` (root, `uuid_envio_padre=NULL`) → `:e2` → `:e3` → `:e4` → `:e5` (tip).
**And** each row's `estado` MUST be preserved (`:e1`='pendiente' initial, `:e2`='rechazado', `:e3`='pendiente' retry, `:e4`='aceptado', `:e5`='pendiente' retry).
**And** the chain integrity MUST be verifiable end-to-end (no orphans, no cycles, every row references the previous via `uuid_envio_padre`).

#### Scenario 4: AST walk — handler emits ONLY INSERT on `prod.envio_dian` for the chain (no UPDATE)

**Given** the source file `api/v1/facturacion.py` containing `retry_factura_electronica`
**When** `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` runs
**Then** the AST walk MUST assert that no `UPDATE prod.envio_dian ...` statement or `update(EnvioDian)` SQLAlchemy core call appears in the handler body.
**And** MUST assert that exactly one `INSERT INTO prod.envio_dian` (or equivalent `crear_envio_dian_reintento` helper call) appears.
**And** MUST assert `len(commits) == 1` (single-commit invariant).

#### Definition of Done for REQ-OPS-070

- Handler `/reintentar` Step 5 INSERTs a NEW `envio_dian` row via `repo_factura_electronica.crear_envio_dian_reintento(session, ..., uuid_envio_padre=tip_envio.uuid)`.
- Handler MUST NOT call any UPDATE on `prod.envio_dian` for user-meaningful fields.
- AST walk `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` PASSES (no UPDATE statements, exactly 1 INSERT, exactly 1 commit).
- Unit tests `test_first_retry` + `test_second_retry` + `test_chain_reconstruction` PASS.

### REQ-OPS-071 — Retry NOT allowed on chain tip `estado='aceptado'` (409 `reintento_no_permitido`); NOT allowed on `pendiente` (409 `envio_dian_already_pending`) (DEC-FE-04)

**Level**: MUST. **Statement**: When the latest `prod.envio_dian` chain tip's `estado='aceptado'`, the `/reintentar` endpoint MUST return HTTP `409 Conflict` with body `{"error":"reintento_no_permitido", "uuid_factura_electronica":"<uuid>", "estado_actual":"aceptado"}` (DEC-FE-04). Only `rechazado` (and `enviado` for completeness, though cloud dispatcher should normally advance it) chain tips may be retried. When the chain tip is `pendiente`, the endpoint MUST return `409 {"error":"envio_dian_already_pending", "uuid_factura_electronica":"<uuid>", "uuid_envio_pendiente":"<tip.uuid>"}` (rapid-retry guard).

**Rationale**: plan.md línea 969. `aceptado` is the terminal success state — retrying creates a phantom chain that misleads DIAN audits. `pendiente` means the cloud dispatcher is still working — the client just needs to wait. The 409 prevents accidental retry storms.

**Source**: plan.md línea 969; DEC-FE-04 in `HU-F1.10-proposal.md` §6.4.

#### Scenario 1: Retry blocked on `aceptado` chain tip

**Given** an FE `:fe` with the latest envio `:e_tip` having `estado='aceptado'`, `cufe='abc123'`
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** `read_chain_tip` MUST return `:e_tip` with `estado='aceptado'`.
**And** the handler MUST return `409 Conflict` with body `{"error":"reintento_no_permitido", "uuid_factura_electronica":":fe", "estado_actual":"aceptado"}` and `Cache-Control: no-store`.
**And** NO new `prod.envio_dian` row MUST be INSERTed.

#### Scenario 2: Retry allowed on `rechazado` chain tip

**Given** an FE `:fe` with the latest envio `:e_tip` having `estado='rechazado'`, `motivo_rechazo='...'`
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** `read_chain_tip` MUST return `:e_tip` with `estado='rechazado'`.
**And** the handler MUST INSERT a NEW envio row `:e_new` with `uuid_envio_padre=:e_tip`, `estado='pendiente'`.
**And** MUST return `201 Created` with `EnvioDianRetryRead{uuid=:e_new, ...}`.

#### Scenario 3: Retry blocked on `pendiente` chain tip (cloud dispatcher working)

**Given** an FE `:fe` with the latest envio `:e_tip` having `estado='pendiente'` (initial envio from REQ-OPS-065, cloud dispatcher hasn't picked it up yet)
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** `read_chain_tip` MUST return `:e_tip` with `estado='pendiente'`.
**And** the handler MUST return `409 Conflict` with body `{"error":"envio_dian_already_pending", "uuid_factura_electronica":":fe", "uuid_envio_pendiente":":e_tip"}` and `Cache-Control: no-store`.
**And** NO new `prod.envio_dian` row MUST be INSERTed (rapid-retry guard).

#### Scenario 4: Retry allowed on `enviado` chain tip (defensive)

**Given** an FE `:fe` with the latest envio `:e_tip` having `estado='enviado'` (cloud dispatcher has POSTed to DIAN but not received response yet)
**When** the client POSTs `/api/v1/facturacion/factura-electronica/:fe/reintentar`
**Then** the handler MAY return `409 envio_dian_already_pending` (defensive: cloud is still working; rapid-retry creates noise)
**Or** the handler MAY proceed to INSERT a new envio row (operator has explicit knowledge the cloud is stuck).
**And** whichever behavior is implemented MUST be consistent across the codebase and MUST be unit-tested.

#### Definition of Done for REQ-OPS-071

- Handler Step 4 of `retry_factura_electronica` calls `repo_factura_electronica.buscar_envio_dian_chain_tip(session, uuid_factura_electronica=:fe)` and inspects `tip.estado`.
- Handler returns `409 reintento_no_permitido` on `estado='aceptado'`, `409 envio_dian_already_pending` on `estado='pendiente'`, and proceeds to INSERT on `estado='rechazado'` (or `enviado`, per Scenario 4 decision).
- Unit tests `test_retry_blocked_on_aceptado` + `test_retry_allowed_on_rechazado` + `test_retry_blocked_on_pendiente` PASS.

### REQ-OPS-072 — `prod.envio_dian` writes are branch-initiated; sync catalog direction flipped to `branch_to_cloud` in MIGRATION 0028 Op 1 (DEC-FE-01)

**Level**: SHALL. **Statement**: `prod.envio_dian` INSERTs MUST be branch-initiated for the initial state and every retry transition. The sync catalog entry for `envio_dian` MUST be flipped from `direction='cloud_to_branch'` to `direction='branch_to_cloud'` in MIGRATION 0028 Op 1 (DEC-FE-01, plan.md línea 953 canonical). The cloud dispatcher consumes the chain via sync replication in `branch_to_cloud` direction for state-machine advancement (`pendiente → enviado → aceptado | rechazado`). The downgrade MUST reverse the flip.

**Rationale**: plan.md línea 953 is canonical (per user mandate "siempre remitete al plan.md"). The cloud-only assumption from PR2 (ER `modelo_datos_er.mmd` línea 892 "CLOUD-ONLY") is aspirational and incompatible with retry semantics (UUID v4 generation must be offline-safe; UPDATE would break the audit trail). The `[L-W]` WorkflowBase mandate of INSERT-only per transition is preserved. The ER diagram comment is updated post-archive from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync" (separate PR for traceability).

**Source**: plan.md línea 953; `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136; `modelo_datos_er.mmd` línea 892 (post-archive update).

#### Scenario 1: Sync catalog flip applied by MIGRATION 0028 Op 1

**Given** MIGRATION 0028 Op 1 SQL `UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian' AND direction='cloud_to_branch';` is applied
**When** the operator queries `SELECT direction FROM sync_catalog WHERE table_name='envio_dian';`
**Then** the result MUST be `branch_to_cloud`.
**And** the migration MUST be idempotent: a second application MUST NOT change the direction (the WHERE clause filters on the old value).

#### Scenario 2: Branch INSERTs replicate to cloud via flipped direction

**Given** a branch TX INSERTs a NEW `prod.envio_dian` row via the `/reintentar` endpoint (REQ-OPS-070)
**When** the sync dispatcher runs (per F1.5 PR5-016 sync infrastructure, R-D8 stage-4 cutover)
**Then** the row MUST be replicated to the cloud (direction=`branch_to_cloud` per MIGRATION 0028 Op 1).
**And** the cloud dispatcher MUST consume the chain via the `branch_to_cloud` sync channel, POST to DIAN provider, and write transition rows (`enviado → aceptado | rechazado`) via the SAME sync channel (bidirectional sync on the same row, mediated by the version row).

#### Scenario 3: Downgrade reverses the flip

**Given** MIGRATION 0028 is downgraded
**When** the downgrade's `UPDATE sync_catalog SET direction='cloud_to_branch' WHERE table_name='envio_dian' AND direction='branch_to_cloud';` executes
**Then** the direction MUST revert to `cloud_to_branch` (pre-F1.10 state).
**And** the downgrade MUST execute AFTER the `DROP INDEX CONCURRENTLY` statements in the downgrade block (reverse order).

#### Definition of Done for REQ-OPS-072

- MIGRATION 0028 Op 1 SQL body `UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian' AND direction='cloud_to_branch';` is present.
- MIGRATION 0028 downgrade reverses the flip in reverse order.
- Unit test `tests/integration/test_migration_0028_idempotent.py::test_sync_catalog_envio_dian_direction_flipped_to_branch_to_cloud` PASSES.
- Integration test `tests/integration/test_branch_insert_replicates_to_cloud.py::test_branch_envio_dian_replicates_to_cloud` PASSES (mock cloud dispatcher receives the row).
- ER `modelo_datos_er.mmd` línea 892 comment update is tracked as a separate post-archive PR (not in F1.10 archive).

### REQ-OPS-073 — Vigente resolution lookup at `NOW()` with defensive `ORDER BY vigente_desde DESC LIMIT 1` (V3)

**Level**: SHALL. **Statement**: The handler MUST look up the vigente `prod.resolucion_facturacion` row for the factura's sucursal using a new helper `repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal(session, *, uuid_sucursal: UUID) -> ResolucionFacturacion | None` with the defensive query `SELECT * FROM prod.resolucion_facturacion WHERE uuid_sucursal = :uuid_sucursal AND vigente_hasta IS NULL AND estado = 'activo' ORDER BY vigente_desde DESC LIMIT 1`. A corrupt DB with multiple vigente rows MUST deterministically pick the most recent by `vigente_desde DESC`.

**Rationale**: The bi-temporal VersionedBase model (migration 0001 line 332) keeps all historical version rows; the vigente predicate (`vigente_hasta IS NULL`) is the natural filter, but a corrupt DB with multiple vigentes must still resolve deterministically. R2 MEDIUM mitigation per `HU-F1.10-proposal.md` §7.

**Source**: `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` (VersionedBase); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 332 (bi-temporal index).

#### Scenario 1: Single vigente — handler picks that row

**Given** `prod.resolucion_facturacion` has exactly one row for `uuid_sucursal=:s` with `vigente_hasta IS NULL`, `estado='activo'`, `prefijo='FE'`, `rango_hasta=5000`, `vigente_desde='2026-01-01'`
**When** `create_factura_electronica` Step 5 invokes `await buscar_resolucion_vigente_por_sucursal(session, uuid_sucursal=:s)`
**Then** the helper MUST return the single row.
**And** MUST NOT raise (V3 happy path).

#### Scenario 2: Multiple vigentes (corrupt DB) — handler picks latest by `vigente_desde DESC`

**Given** `prod.resolucion_facturacion` has two rows for `uuid_sucursal=:s` with `vigente_hasta IS NULL`, `estado='activo'` (a corrupt state that should never occur, but defensive):
- row `r1`: `vigente_desde='2026-01-01'`, `prefijo='FE'`, `rango_hasta=5000`
- row `r2`: `vigente_desde='2026-09-01'`, `prefijo='FX'`, `rango_hasta=9999`
**When** `create_factura_electronica` Step 5 invokes `buscar_resolucion_vigente_por_sucursal(session, uuid_sucursal=:s)`
**Then** the helper MUST return `r2` (latest by `vigente_desde DESC`).
**And** MUST NOT raise (defensive, NOT an error).

#### Scenario 3: No vigente — handler returns 409 `resolucion_no_vigente`

**Given** `prod.resolucion_facturacion` has zero rows for `uuid_sucursal=:s` with `vigente_hasta IS NULL`, `estado='activo'` (all resolutions are expired or inactivas)
**When** `create_factura_electronica` Step 5 invokes `buscar_resolucion_vigente_por_sucursal(session, uuid_sucursal=:s)`
**Then** the helper MUST return `None`.
**And** the handler MUST return `409 Conflict` with body `{"error":"resolucion_no_vigente", "uuid_sucursal":":s"}` and `Cache-Control: no-store`.
**And** NO `prod.factura_electronica` row MUST be INSERTed.

#### Definition of Done for REQ-OPS-073

- New helper `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal` with signature `async def buscar_resolucion_vigente_por_sucursal(session, *, uuid_sucursal: UUID) -> ResolucionFacturacion | None`.
- Handler Step 5 calls the helper and maps `None` → 409 `resolucion_no_vigente`.
- Unit test `tests/unit/test_factura_electronica_repo.py::test_buscar_resolucion_vigente_por_sucursal_returns_latest` PASSES (single vigente + multi-vigente corrupt cases).
- Unit test `tests/unit/test_factura_electronica_create_handler.py::test_create_fe_returns_409_resolucion_no_vigente` PASSES.

### REQ-OPS-074 — Prefijo snapshot on `prod.factura_electronica.prefijo` at INSERT time (denormalized from vigente resolution; 4NF snapshot pattern)

**Level**: SHALL. **Statement**: The handler MUST denormalize the vigente `prod.resolucion_facturacion.prefijo` onto the new `prod.factura_electronica.prefijo` at INSERT time. The FE's `prefijo` is the historical truth — subsequent changes to the resolution's `prefijo` (e.g. a new resolution with `prefijo='FX'` supersedes the old `prefijo='FE'`) MUST NOT retroactively alter the FE's `prefijo` (4NF snapshot pattern per plan.md línea 697 and `modelo_datos_er.mmd` línea 700).

**Rationale**: 4NF — the FE's prefijo is the snapshot at the moment of numbering. DIAN audits require that historical documents reference the prefijo they were issued under, not the current prefijo of the resolution.

**Source**: plan.md línea 697; ER `modelo_datos_er.mmd` línea 700; `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py`.

#### Scenario 1: Prefijo snapshotted at INSERT, immutable thereafter

**Given** a vigente resolution `:r` with `prefijo='FE'`
**When** the FE row is INSERTed with `prefijo='FE'` and `consecutivo=42`
**Then** `prod.factura_electronica.prefijo='FE'` MUST be persisted.
**And** a later `UPDATE prod.resolucion_facturacion SET prefijo='FX' WHERE uuid=:r` MUST NOT change `prod.factura_electronica.prefijo` (still `'FE'`).
**And** a later bi-temporal versioning of `:r` (close + new row with `prefijo='FX'`) MUST also NOT change `prod.factura_electronica.prefijo` (still `'FE'`).

#### Scenario 2: Two FE rows from different resolution eras show independent prefijos

**Given** two FE rows:
- FE1: inserted under resolution A with `prefijo='FE'`, `consecutivo=42`
- FE2: inserted under resolution B with `prefijo='FX'`, `consecutivo=1`
**When** both rows are queried via `GET /api/v1/facturacion/factura-electronica/{uuid}` for FE1 and FE2
**Then** FE1's response MUST carry `prefijo='FE'` (snapshot from resolution A era).
**And** FE2's response MUST carry `prefijo='FX'` (snapshot from resolution B era).
**And** no cross-contamination MUST occur (FE2's `prefijo='FX'` MUST NOT bleed into FE1's response).

#### Definition of Done for REQ-OPS-074

- Handler Step 7 reads `resolucion.prefijo` from the vigente row returned by V3 and uses it as the `prefijo` argument to `crear_factura_electronica_inicial`.
- Unit test `tests/unit/test_factura_electronica_repo.py::test_prefijo_snapshot_independent_of_resolution_change` PASSES.
- Integration test `tests/integration/test_factura_electronica_atomicidad_db.py::test_two_fe_rows_different_prefijo_eras` PASSES.

---

## Cross-Cutting Requirements

### REQ-OPS-XR1 — Defense in depth: 5 layers (mirror of F1.9 REQ-OPS-XR1, F1.10-specific)

**Given** the FE + envio chain is critical to DIAN regulatory compliance (numbering contiguity, audit trail integrity, cloud-dispatcher-outage tolerance)
**When** any layer of the defense fails
**Then** the remaining 4 layers MUST contain the failure:

1. **(a) KD-3 issuer chain**: `_fe_issuer_dep = requires_issuer("operador-", "admin-")` (F1.9 pattern verbatim). Branch operator with `emitir_factura` permission emits; admin cross-branch. Applied at handler entry as a FastAPI dependency; runs BEFORE any handler body code.
2. **(b) Tenant scope post-V1**: After resolving `target_sucursal` from `prod.facturas.uuid_sucursal` (V1 in `POST /factura-electronica`) or from `prod.factura_electronica.uuid_sucursal` (V1 in `GET` and `/reintentar`), if `ctx.issuer_prefix == "operador-"` AND `(ctx.sucursal_uuid is None OR target_sucursal != ctx.sucursal_uuid)`, return `403 {"error":"tenant_scope_violation"}`. Admin (`admin-`) bypasses. KD-S2 analog from F1.7.
3. **(c) DB-layer partial unique index `one_fe_per_factura`**: MIGRATION 0028 Op 2 `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL`. Defense in depth: closes the V2 SELECT-before-INSERT TOCTOU race window between two concurrent cajeros attempting the same `prod.facturas.uuid`. `psycopg2.errors.UniqueViolation` (pgcode `23505`) maps to `409 factura_electronica_ya_existe` (REQ-OPS-067 Scenario 3).
4. **(d) `assign_consecutivo` SELECT FOR UPDATE**: `repo/resolucion_facturacion.py::assign_consecutivo` already takes `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion` (verified, source lines 114-120). Lock held until `await session.commit()`. Concurrent calls on the SAME resolution serialize cleanly. NO modification in F1.10 (DEC-FE-05).
5. **(e) Handler 409 mapping + typed exceptions**: 8 typed exceptions mapped to HTTP responses per `HU-F1.10-proposal.md` §8 Layer 5 table. The pgcode NEVER appears in the response body, headers, or info+ logs.

**RFC 2119**: MUST (each layer independently tested; failure of any one layer MUST be contained by the other 4).

#### Scenario: layer (c) — concurrent INSERT same `uuid_factura` raises `UniqueViolationError` → 409

**Given** `prod.factura_electronica` row with `uuid_factura=:f` already exists
**When** concurrent TX attempts `INSERT INTO prod.factura_electronica (uuid_factura, ...) VALUES (:f, ...)`
**Then** PostgreSQL MUST raise `psycopg2.errors.UniqueViolation` (pgcode `23505`).
**And** the handler MUST translate to `HTTPException(status_code=409, detail={"error":"factura_electronica_ya_existe", "uuid_factura":":f"})`.

### REQ-OPS-XR2 — `Cache-Control: no-store` header on all responses (mirror of F1.9 REQ-OPS-XR2)

**Given** FE responses must never be cached (defense in depth against cache poisoning of `cufe`, `estado`, `timestamp_evento`)
**When** any handler under `/api/v1/facturacion/factura-electronica` responds (2xx, 4xx, or 5xx)
**Then** the response MUST carry `Cache-Control: no-store` header.

#### Scenario: 201 Created carries `Cache-Control: no-store`

**When** `POST /factura-electronica` returns `201 Created`
**Then** the response MUST carry `Cache-Control: no-store`.

#### Scenario: 409 `numeracion_agotada` carries `Cache-Control: no-store`

**When** `POST /factura-electronica` returns `409 numeracion_agotada`
**Then** the response MUST carry `Cache-Control: no-store`.

### REQ-OPS-XR3 — KD-FE-01 single `await session.commit()` invariant (mirror of F1.9 REQ-OPS-XR3 / KD-FACT-01)

**RFC 2119**: The `create_factura_electronica` and `retry_factura_electronica` handler bodies in `api/v1/facturacion.py` MUST each contain **EXACTLY ONE** `await session.commit()` call. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements **MUST NOT** appear anywhere in the handler body or its callees (KD-FE-01 + DEC-FE-01).

**Defense**: AST walks enforce the invariant:

- `tests/static/test_fe_handler_single_commit.py` parses `create_factura_electronica` body using `ast.walk` BFS and asserts:
  - `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call) and getattr(n.value.func, 'attr', '') == 'commit']) == 1`
  - `len([n for n in ast.walk(body) if isinstance(n, ast.Call) and getattr(n.func, 'attr', '') == 'begin_nested']) == 0`
  - No `SAVEPOINT` or `RELEASE SAVEPOINT` string literals in the body.
- `tests/static/test_fe_retry_handler_single_commit.py` enforces the same invariant for `retry_factura_electronica`.
- `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` enforces that no UPDATE on user-meaningful fields appears in the retry handler.

#### Scenario: T10 AST walk enforces exactly 1 commit call in `create_factura_electronica`

**Given** the source file `api/v1/facturacion.py` containing `create_factura_electronica`
**When** `tests/static/test_fe_handler_single_commit.py` runs
**Then** the AST walk MUST assert `commit_count == 1`; if multiple commits OR any `begin_nested` OR any `SAVEPOINT` is detected, the test MUST fail with a typed error referencing the offending AST node line number.

#### Scenario: handler with two `commit()` calls MUST fail AST walk

**Given** a hypothetical handler with `await session.commit()` at line 50 and `await session.commit()` at line 80
**When** the AST walk runs
**Then** `commit_count == 2` MUST trigger test failure with message `"KD-FE-01 violation: expected 1 commit, found 2 at lines [50, 80]"`.

---

## Authoring & Test Inventory

- **Author**: Parkos Dev <dev@parkos.local>
- **Commits**: conventional commits in neutral Spanish, NO AI attribution (Co-Authored-By trailers forbidden per global project rules).
- **Tests**: ~24 tests across 7 files + 2 AST walks.
  - `tests/unit/test_factura_electronica_numeracion.py` (~120 LOC, **3 tests** per plan.md línea 971: T1 `test_asignacion_normal_exitosa_returns_201`, T2 `test_rango_agotado_returns_409_with_alerta`, T3 `test_reintento_encadenado_creates_new_envio_chain`).
  - `tests/unit/test_factura_electronica_schemas.py` (~80 LOC, **4 tests**: `test_fe_create_rejects_prefijo_injection`, `test_fe_create_rejects_consecutivo_injection`, `test_fe_create_rejects_uuid_resolucion_injection`, `test_numeracion_agotada_error_schema_typed`).
  - `tests/unit/test_factura_electronica_repo.py` (~100 LOC, **5 tests**: `test_buscar_factura_electronica_por_factura_returns_none`, `test_crear_factura_electronica_inicial_inserts_row`, `test_buscar_envio_dian_chain_tip_returns_latest`, `test_crear_envio_dian_reintento_sets_uuid_envio_padre`, `test_crear_envio_dian_reintento_initial_no_padre`, `test_buscar_resolucion_vigente_por_sucursal_returns_latest`, `test_prefijo_snapshot_independent_of_resolution_change`).
  - `tests/unit/test_factura_electronica_create_handler.py` (~120 LOC, **5 tests**: `test_create_fe_happy_path_returns_201`, `test_create_fe_assign_consecutivo_idempotent_on_retry`, `test_create_fe_returns_404_factura_no_encontrada`, `test_create_fe_returns_409_factura_electronica_ya_existe`, `test_create_fe_returns_409_numeracion_agotada_alerta_fired`, `test_create_fe_returns_409_resolucion_no_vigente`).
  - `tests/unit/test_factura_electronica_get_handler.py` (~50 LOC, **3 tests**: `test_get_fe_returns_estado_aceptado_with_cufe`, `test_get_fe_returns_estado_pendiente_when_no_envio`, `test_get_fe_returns_latest_envio_via_view`).
  - `tests/unit/test_factura_electronica_retry_handler.py` (~80 LOC, **3 tests**: `test_retry_fe_happy_path_returns_201_with_new_envio`, `test_retry_fe_returns_409_si_chain_tip_aceptado`, `test_retry_fe_returns_409_si_chain_tip_pendiente`, `test_retry_fe_returns_404_si_fe_no_existe`).
  - `tests/integration/test_migration_0028_idempotent.py` (~80 LOC, **3 tests**: `test_migration_0028_idempotent_upgrade_downgrade_upgrade`, `test_sync_catalog_envio_dian_direction_flipped_to_branch_to_cloud`, `test_one_fe_per_factura_partial_uk_blocks_duplicate_fe`).
  - `tests/integration/test_factura_electronica_atomicidad_db.py` (~150 LOC, **2 tests**: `test_concurrent_post_serializes_consecutivos`, `test_concurrent_post_uk_race`, `test_rollback_no_orphan_fe_or_envio`, `test_two_fe_rows_different_prefijo_eras`).
  - `tests/static/test_fe_handler_single_commit.py` (~40 LOC, **1 AST walk**: KD-FE-01 single-commit invariant for `create_factura_electronica`).
  - `tests/static/test_fe_retry_handler_single_commit.py` (~40 LOC, **1 AST walk**: KD-FE-01 single-commit invariant for `retry_factura_electronica`).
  - `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` (~40 LOC, **1 AST walk**: no UPDATE on `prod.envio_dian` user-meaningful fields).
  - **Total**: ~24 unit/integration tests + 3 AST walks = ~27 verification points across ~860 LOC cumulative (630 tests + 230 production).

- **Predecessor conventions reused**: F1.9 KD-3 issuer (`requires_issuer("operador-", "admin-")`), 12-step handler chain pattern, single-commit invariant (KD-FACT-01 → KD-FE-01), `assign_consecutivo` SELECT FOR UPDATE (D1-rev, F1.9 T-PR9-002), `repo/workflow.read_chain_tip` (F1.5 PR5-016), `repo/alert_types.py::AlertaFactory` (F1.8 T-PR8-002), partial unique index pattern (F1.7 `one_exit_per_ingreso`, F1.9 `one_factura_per_salida`), AST walk pattern, `Idempotency-Key` header (DEC-IDEM-01 reuse from F1.6 + F1.9), `v_factura_electronica_acuse` view (migration 0009, F1.5 PR5-016).

- **Migration**: MIGRATION 0028 (~120 LOC, 3 ops + downgrade):
  - Op 1: pre-flight `ASSERT` + sync catalog flip `UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian' AND direction='cloud_to_branch';`
  - Op 2: partial unique index `one_fe_per_factura` (`CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`)
  - Op 3: covering index `idx_envio_dian_chain_tip` (`CREATE INDEX CONCURRENTLY IF NOT EXISTS`)
  - Op 4 (defensive): `GRANT SELECT, INSERT, UPDATE ON prod.factura_electronica TO rol_app; GRANT SELECT, INSERT, UPDATE ON prod.envio_dian TO rol_app;`
  - Downgrade: reverse order, `DROP INDEX CONCURRENTLY` for both indexes, reverse sync catalog flip.

## References

- `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-proposal.md` (16 sections, DEC-FE-01..05, KD-FE-01..02, 11 REQ-OPS-064..074 placeholders, MIGRATION 0028 plan, 24 tests + 2 AST walks, 5-layer defense)
- `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-explore.md` (16 sections, ~970 LOC, observation #1568 — R1..R5 risk identification + DEC-FE-01 conflict resolution)
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/specs/operations/spec.md` (canonical precedent, REQ-OPS-053..063, XR1..XR3 cross-cutting)
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/{exploration,proposal,design,tasks,verify-report,archive-report}.md` (precedent for KD-3 issuer + 12-step handler + KD-FACT-01 single-commit + AST walks)
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/{exploration,proposal,design,tasks,verify-report,archive-report}.md` (precedent KD-S2 tenant scope, `one_exit_per_ingreso` partial UK)
- `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/{exploration,proposal,design,tasks}.md` (precedent `repo/workflow.read_chain_tip`)
- `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/{exploration,proposal,design,tasks}.md` (precedent `repo/alert_types.py::AlertaFactory`)
- `openspec/specs/operations/spec.md` (66 REQs REQ-OPS-001..063 merged post-F1.9 — target for REQ-OPS-064..074 merge on archive)
- `plan.md` lines 939-979 (HU-F1.10 definition, 4 atomic tasks T1..T4, 230 LOC budget)
- `plan.md` line 949 (alerta `fe_numbering_exhausted` already seeded)
- `plan.md` line 951 (forbidden fallback `SIM-YYYY-MM-DD-NNNNNN` numbering)
- `plan.md` line 953 (`envio_dian` INSERT por transición, nunca UPDATE, BRANCH-initiated)
- `plan.md` line 969 (retry only on `rechazado`; block on `aceptado`)
- `plan.md` line 697 (`prefijo` snapshot pattern, 4NF)
- `plan.md` línea 947 (forbidden `reportado_dian` boolean)
- `modelo_datos_er.mmd` lines 689-705 (`prod.factura_electronica` [L-E] snapshot pattern, `cufe y reportado_dian eliminados (4FN)`)
- `modelo_datos_er.mmd` lines 891-914 (`prod.envio_dian` [L-W] self-FK chain — post-archive comment update from "CLOUD-ONLY" to "BRANCH-INITIATED")
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 875-891 (`factura_electronica` create_table + UK01 `(uuid_resolucion_facturacion, consecutivo)`)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 976-993 (`envio_dian` create_table + UK02 `(uuid_factura_electronica, uuid_envio_padre)`)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 1595-1842 (FKs), 2646-2712 (audit/versioning triggers), 2864-2900 (sync enqueue triggers)
- `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109 (`prod.v_factura_electronica_acuse` view, DISTINCT ON latest envio)
- `backend/packages/parkos_core/migrations/versions/0027_*` (F1.9 head — `one_factura_per_salida` partial UK precedent)
- `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py` (LifecycleEventBase + UK `(uuid_resolucion_facturacion, consecutivo)`)
- `backend/packages/parkos_core/src/parkos_core/models/L_W/envio_dian.py` (WorkflowBase + self-FK `uuid_envio_padre` + `cufe` + `estado`)
- `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` (VersionedBase, bi-temporal, `prefijo` + `rango_desde`/`rango_hasta`, NO `consecutivo_actual` per 4NF)
- `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo` (verified, lines 99-108 idempotency, lines 114-120 SELECT FOR UPDATE, lines 143-147 `ConsecutivoRangeExhaustedError`)
- `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal` (NEW helper per REQ-OPS-073)
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py::read_chain_tip` (F1.5 PR5-016, reused for `/reintentar` chain tip lookup)
- `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py::AlertaFactory` (F1.8 T-PR8-002, fires `fe_numbering_exhausted` on range exhaustion)
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136 (`envio_dian` `cloud_to_branch` direction per D1-rev — **FLIPPED in DEC-FE-01** / MIGRATION 0028 Op 1)
- `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (F1.9 handler pattern verbatim, extended with 3 new handlers)
- `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (F1.9 patterns + new `FacturaElectronicaCreate`, `FacturaElectronicaRead`, `EnvioDianRead`, `EnvioDianRetryRead` + 7 typed error schemas)