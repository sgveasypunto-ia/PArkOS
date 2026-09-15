# Proposal: HU-F1.10 — Numeración FE + estado DIAN + reintento

> **Change**: `hu-f1-10-numeracion-fe-dian-reintento` (folder to be created at `openspec/changes/hu-f1-10-numeracion-fe-dian-reintento/`; artifact authored at `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-proposal.md` per orchestrator locator).
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.10 (Fase-1 prerequisites — backend)
> **Inputs**: `plan.md` lines 939-979 (230 LOC, 4 atomic tasks T1..T4), `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-explore.md` (16 sections, ~970 LOC, written 2026-09-14, observation #1568), `modelo_datos_er.mmd` (`prod.factura_electronica` 689-705 `[L-E]`, `prod.envio_dian` 891-914 `[L-W]`, `prod.resolucion_facturacion` 315-332 `[V]`), `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (`factura_electronica` 875-891 [L-E], `envio_dian` 976-993 [L-W], FKs 1595-1842, audit/versioning triggers 2646-2712, sync enqueue triggers 2864-2900), `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` (`prod.v_factura_electronica_acuse` lines 96-109 — DISTINCT ON latest envio_dian per FE, already present), `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py` (LifecycleEventBase + UK `(uuid_resolucion_facturacion, consecutivo)` + `fecha_retencion_hasta` re-declared), `backend/packages/parkos_core/src/parkos_core/models/L_W/envio_dian.py` (WorkflowBase + self-FK `uuid_envio_padre` + `cufe` + `estado` + re-declared `vigente_desde/vigente_hasta/estado`), `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` (VersionedBase, `prefijo` + `rango_desde`/`rango_hasta`, NO `consecutivo_actual` per 4NF), `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo` (verified, SELECT FOR UPDATE, idempotency, range exhaustion — returns `int`), `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (F1.9 handler pattern verbatim), `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/{exploration,proposal,design,tasks,verify-report,archive-report}.md` (precedent KD-3 issuer + 12-step handler + KD-FACT-01 single-commit + KD-FACT-02 FOR SHARE + AST walks), `openspec/specs/operations/spec.md` (66 REQs REQ-OPS-001..063 merged post-F1.9), `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136 (`envio_dian` `cloud_to_branch` direction per D1-rev — **FLIPPED in DEC-FE-01**).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `47d5630`) · **PR target**: `origin/dev`.
> **Language note**: artifact authored in English per the project's `Language Domain Contract` (default for technical SDD artifacts). DEC-FE-NN identifiers follow the F1.7..F1.9 DEC-SUC / DEC-SAL / DEC-FACT / DEC-FORZADO / DEC-MONO / DEC-IMP naming pattern. KD-FE-NN follow the F1.7..F1.9 KD-S / KD-1 / KD-FACT pattern.

---

## 1. Title & Goal

**Title**: "Numeración FE + estado DIAN + reintento"

**Goal**: Deliver three endpoints that together close the DIAN regulatory extension on top of F1.9's internal billing:

1. **`POST /api/v1/facturacion/factura-electronica`** — Given a paid `prod.facturas.uuid`, server-assigns `prefijo`+`consecutivo` via the existing `assign_consecutivo` helper (SELECT FOR UPDATE on `prod.resolucion_facturacion`), INSERTs `prod.factura_electronica` (1:1 with the internal factura), and INSERTs the initial `prod.envio_dian` row with `estado='pendiente'` and `uuid_envio_padre=NULL`.
2. **`GET /api/v1/facturacion/factura-electronica/{uuid}`** — JOIN the existing `prod.v_factura_electronica_acuse` view (migration 0009) to expose the raw `estado` (`pendiente|enviado|aceptado|rechazado`) and the latest `cufe` + `timestamp_evento` (never a fabricated `reportado_dian` boolean).
3. **`POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar`** — INSERT a **new** `prod.envio_dian` row with `uuid_envio_padre` pointing at the previous chain tip. **NEVER UPDATE.** The retry chain is the audit trail of every transition.

**Defense in depth (5 layers)**: (a) KD-3 issuer chain (`requires_issuer("operador-", "admin-")`), (b) tenant scope post-V1 (KD-S2 analog from F1.7), (c) DB-layer partial unique index `one_fe_per_factura` (MIGRATION 0028 Op 2 — defense in depth alongside the existing UK `(uuid_resolucion_facturacion, consecutivo)`), (d) `assign_consecutivo` SELECT FOR UPDATE (already in place, no modification), (e) handler 409 mapping for `numeracion_agotada`, `reintento_no_permitido`, `factura_electronica_ya_existe`.

**Scope**: ~230 LOC production (matches plan.md line 973) + ~630 LOC tests across 7 files = ~860 LOC cumulative.

---

## 2. Context & Background

- **F1.9 closed** (2026-09-14, 11 commits, HEAD `47d5630`). F1.9 atomically creates `prod.facturas` + `prod.factura_detalle` + `prod.factura_impuestos` + `prod.factura_pagos` (KD-FACT-01 single-commit invariant). F1.10 adds the DIAN regulatory side-car: the `prod.factura_electronica` row that carries the fiscal `prefijo`+`consecutivo`, plus the `prod.envio_dian` workflow chain that records every DIAN submission attempt.
- **Regulatory framework**: Colombian electronic invoicing is governed by **DIAN Resolución 000175 de 2021** + **Decreto 2242 de 2015**. Numbering MUST be contiguous inside the authorized `resolucion_facturacion` range (`rango_desde`..`rango_hasta`). The `prefijo` is snapshotted from the resolution at insert time (snapshot pattern, 4NF — the vigente resolution may later change but the historical FE keeps its original prefijo).
- **`assign_consecutivo` Python helper already exists** (T-PR9-002, D1-rev, F1.9 reused). Verified signature: `async def assign_consecutivo(session, *, resolucion_uuid, source_event_uuid) -> int` returns ONLY the next `consecutivo` (caller has the `prefijo` from the `resolucion_facturacion` row). Idempotent per `(resolucion_uuid, source_event_uuid)` pair (lines 99-108). Takes `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion` row (lines 114-120). Raises `ConsecutivoRangeExhaustedError` when `next_value > rango_hasta` (lines 143-147). **NO modification** in F1.10.
- **`v_factura_electronica_acuse` view already exists** (migration 0009 lines 96-109). Uses `DISTINCT ON (uuid_factura_electronica) ORDER BY timestamp_evento DESC` to expose the latest envio per FE. Columns: `(uuid_factura_electronica, cufe, estado, timestamp_evento)`. F1.10 does NOT create this view.
- **`prod.factura_electronica` is `[L-E]` (insert-only)** — `LifecycleEventBase` per migration 0001 lines 875-891. Composite PK `(uuid, fecha_retencion_hasta)`. Existing UK `factura_electronica_uk01 (uuid_resolucion_facturacion, consecutivo)` enforces DIAN numbering uniqueness inside a resolution's range.
- **`prod.envio_dian` is `[L-W]` (insert-only per transition)** — `WorkflowBase` per migration 0001 lines 976-993. Self-FK `uuid_envio_padre` provides the chain tip. State machine `pendiente → enviado → aceptado | rechazado` lives on `prod.envio_dian.estado` per ER línea 904 (masc forms — NEVER stored on `prod.factura_electronica` per 4NF).
- **The `alerta fe_numbering_exhausted` is already seeded** (per plan.md line 949). F1.10 fires it via `AlertaFactory` when `assign_consecutivo` raises `ConsecutivoRangeExhaustedError`.

### 2.1 Critical Architectural Conflict — `envio_dian` ownership (RESOLVED in §3)

The sdd-explore phase (observation #1568) flagged R1 HIGH — a real architectural fork:

- **plan.md línea 953** mandates: branch INSERTs `prod.envio_dian` rows for initial state + retry chain.
- **`modelo_datos_er.mmd` línea 892** says: `envio_dian` `[L-W]` is "**CLOUD-ONLY**: único punto de salida hacia el proveedor de factura electrónica DIAN".
- **Sync catalog** (`backend/.../sync/catalog/entries/sync_entries_lw.py` lines 112-136): `envio_dian` direction = `cloud_to_branch`.

This conflict is RESOLVED in DEC-FE-01 (see §6) by the user's standing mandate: **plan.md is the canonical authority**. The ER comment is updated post-archive; the sync catalog is flipped via MIGRATION 0028 Op 1.

---

## 3. Architectural Conflict Resolution — DEC-FE-01

This section is **mandatory** for the proposal. It documents R1 from the sdd-explore phase and records the resolution.

### 3.1 The conflict (R1 HIGH)

Three sources disagree about which node writes `prod.envio_dian`:

| Source | Statement | Authority weight |
|---|---|---|
| `plan.md` línea 953 | "`envio_dian` (INSERT por transición, nunca UPDATE)" from the BRANCH | **CANONICAL** (per user mandate "siempre remitete al plan.md") |
| `modelo_datos_er.mmd` línea 892 | "CLOUD-ONLY: único punto de salida hacia el proveedor de factura electrónica DIAN" | Aspirational design from PR2 — F1.10 supersedes |
| `sync/catalog/entries/sync_entries_lw.py` lines 112-136 | `direction = "cloud_to_branch"` | Catalog entry to be updated in MIGRATION 0028 Op 1 |

The cloud-only assumption was a PR2 aspirational design. With `assign_consecutivo` now in place at the branch and the cloud dispatcher architecture decided out-of-band (mocked for MVP), the natural design is: **branch numbers + tracks locally, cloud forwards asynchronously**. The retry endpoint needs UUID v4 generation at the branch (offline-safe, no DIAN round-trip latency for the INSERT itself). The cloud consumes the chain via sync replication for analytics + state-machine advancement.

### 3.2 The resolution

**Resolution path** (mandated by plan.md + F1.10 retry semantics):

1. **Branch INSERTs** the initial `prod.envio_dian` row (`estado='pendiente'`, `uuid_envio_padre=NULL`) atomically with `prod.factura_electronica` in the same `await session.commit()` (KD-FE-01 single-commit invariant, mirror of KD-FACT-01).
2. **Branch INSERTs** every subsequent retry row with `uuid_envio_padre` pointing at the previous chain tip. **NEVER UPDATE.** This is the audit trail and the only way to recover the chain ordering under cloud dispatcher outages.
3. **Cloud dispatcher** (out of F1.10 scope; Fase 4 owns the real integration) reads the branch's `envio_dian` chain via sync replication in `branch_to_cloud` direction, POSTs to the DIAN provider, and writes back transition rows (`enviado → aceptado|rechazo`) via the same sync channel.
4. **Branch reads** the latest chain tip via `prod.v_factura_electronica_acuse` (migration 0009, already present).

### 3.3 What changes in the codebase (MIGRATION 0028 Op 1)

```sql
-- DEC-FE-01: flip envio_dian sync direction from cloud_to_branch to branch_to_cloud
UPDATE sync_catalog
SET direction = 'branch_to_cloud'
WHERE table_name = 'envio_dian' AND direction = 'cloud_to_branch';
```

This is the **first op** of MIGRATION 0028 (pre-flight + flip, before the partial unique index in Op 2). Downgrade reverses: `UPDATE sync_catalog SET direction = 'cloud_to_branch' WHERE table_name = 'envio_dian'`.

### 3.4 What changes in the ER diagram (post-archive)

`modelo_datos_er.mmd` línea 892 comment is updated from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync replication". The `[L-W]` tag stays (insert-only per transition). The change is committed in a separate commit after the F1.10 archive (the archive PR does NOT touch `modelo_datos_er.mmd`; the diagram update is its own PR for traceability).

### 3.5 Why this matters

- **Retry semantics require branch-side chain**: UUID v4 generation at the branch is offline-safe. A cloud-only design forces a synchronous round-trip on every retry, which is incompatible with the existing offline-first architecture (per `AGENTS.md`).
- **Chain integrity via `uuid_envio_padre` FK**: each transition = NEW row. UPDATE would break the audit trail and the `vigente_desde`/`vigente_hasta` versioning semantics (the `[L-W]` workflow base mandates UPDATE on `vigente_hasta` for bi-temporal versioning, but the user-meaningful fields like `estado` MUST be insert-only).
- **Cloud consumes via sync for analytics**: cloud aggregates the chain for DIAN reporting, audit trails, and the eventual webhook callbacks.

---

## 4. Endpoints

Three endpoints. All mounted under `/api/v1/facturacion/factura-electronica` (hyphenated, F1.9 convention).

### 4.1 `POST /api/v1/facturacion/factura-electronica` (HU-F1.10-T1)

- **Purpose**: Assign `prefijo`+`consecutivo`, INSERT `prod.factura_electronica`, INSERT initial `prod.envio_dian` (`estado='pendiente'`).
- **Issuer dep**: `_fe_issuer_dep = requires_issuer("operador-", "admin-")` (F1.9 pattern verbatim).
- **Request body**: `FacturaElectronicaCreate` — `{uuid_factura: UUID}`. The server resolves the vigente resolution for the factura's sucursal; client cannot smuggle `prefijo`, `consecutivo`, `uuid_resolucion_facturacion` (Pydantic `extra='forbid'`).
- **Response (201)**: `FacturaElectronicaConEnvioRead` — `{uuid, prefijo, consecutivo, uuid_factura, uuid_resolucion_facturacion, created_at, envio_actual: {uuid, estado: "pendiente", timestamp_evento, uuid_envio_padre: null}}`.
- **Status codes**:
  - `201 Created` — happy path
  - `404 factura_no_encontrada` — `prod.facturas.uuid` not found (V1)
  - `403 tenant_scope_violation` — operador- with cross-branch (post-V1)
  - `409 factura_electronica_ya_existe` — V2 found existing FE for `uuid_factura`
  - `409 numeracion_agotada` — `assign_consecutivo` raised `ConsecutivoRangeExhaustedError` + alerta fired (V6)
  - `409 resolucion_no_vigente` — no vigente resolution for the sucursal (V3)
  - `500 dian_unavailable` — reserved for Fase 4 real integration (always 200 in MVP)
- **Headers**: `Cache-Control: no-store` (F1.3..F1.9 precedent).
- **Idempotency**: `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse from F1.6 + F1.9). Per-factura, `assign_consecutivo` is itself idempotent on `uuid_factura` (idempotency check lines 99-108).

### 4.2 `GET /api/v1/facturacion/factura-electronica/{uuid}` (HU-F1.10-T2)

- **Purpose**: Read FE + latest envio chain tip via JOIN to existing `prod.v_factura_electronica_acuse`.
- **Issuer dep**: same as 4.1.
- **Response (200)**: `FacturaElectronicaConEnvioRead` with `envio_actual.estado` and `envio_actual.cufe` derived from the view.
- **Status codes**:
  - `200 OK` — happy path
  - `404 factura_electronica_no_encontrada` — FE row does not exist
  - `403 tenant_scope_violation` — operador- with cross-branch
- **Headers**: `Cache-Control: no-store`.
- **Idempotency**: GET is naturally idempotent.

### 4.3 `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` (HU-F1.10-T3)

- **Purpose**: INSERT a NEW `prod.envio_dian` row with `uuid_envio_padre` pointing at the previous chain tip. NEVER UPDATE.
- **Issuer dep**: same as 4.1.
- **Request body**: empty (the path parameter `uuid` carries the intent).
- **Response (201)**: `EnvioDianRead` — `{uuid, uuid_factura_electronica, estado: "pendiente", timestamp_evento, uuid_envio_padre: <previous_tip.uuid>, cufe: null, motivo_rechazo: null}`.
- **Status codes**:
  - `201 Created` — happy path (new envio row inserted)
  - `404 factura_electronica_no_encontrada` — FE row does not exist
  - `403 tenant_scope_violation` — operador- with cross-branch
  - `409 reintento_no_permitido` — chain tip state is `aceptado` (terminal, DEC-FE-04)
  - `409 envio_dian_already_pending` — chain tip is already `pendiente` (no point retrying; cloud dispatcher hasn't picked it up yet — V2 chain-tip guard)
- **Headers**: `Cache-Control: no-store`.
- **Idempotency**: `Idempotency-Key` header (DEC-IDEM-01). Multiple POSTs with different keys are all accepted; the chain grows. Multiple POSTs with the same key return the cached response.

---

## 5. Tables Touched

Three tables. Two read, one read+insert. No schema changes to existing tables. MIGRATION 0028 adds 1 partial unique index + 1 covering index + the sync catalog flip.

### 5.1 `prod.resolucion_facturacion` `[V]` (bi-temporal VersionedBase)

- **Operations**: V3 SELECT vigente row for `uuid_sucursal`; KD-FE-01 SELECT FOR UPDATE inside `assign_consecutivo` (reused as-is, no modification).
- **Columns read**: `uuid`, `prefijo`, `rango_desde`, `rango_hasta`, `vigente_desde`, `vigente_hasta`, `vigente_inicial`, `estado`.
- **Index**: existing bi-temporal `(vigente_desde, vigente_hasta)` (migration 0001 line 332).
- **Defense in depth at DB layer**: SELECT FOR UPDATE locks the version row during `assign_consecutivo`; concurrent calls on the SAME resolution serialize cleanly (per `assign_consecutivo` source lines 114-120).

### 5.2 `prod.factura_electronica` `[L-E]` (insert-only, composite PK `(uuid, fecha_retencion_hasta)`)

- **Operations**: V2 SELECT-by-`uuid_factura` (existing-FE guard); V4 INSERT in same TX as `envio_dian` (KD-FE-01 single-commit).
- **Columns read/written**:
  - Read: `uuid`, `uuid_sucursal`, `uuid_factura`, `uuid_resolucion_facturacion`, `prefijo`, `consecutivo`, `descuento`, `vigente_desde`, `vigente_hasta`, `created_at`, `created_by`.
  - Write (INSERT): `uuid_sucursal`, `uuid_factura`, `uuid_resolucion_facturacion`, `prefijo` (snapshot from `resolucion.prefijo`), `consecutivo` (from `assign_consecutivo`), `descuento=Decimal(0)`, `fecha_retencion_hasta = date.today() + timedelta(days=5*365)` (DIAN 5-year retention).
- **Indexes**: existing UK `(uuid_resolucion_facturacion, consecutivo)` per migration 0001 line 889 (DIAN numbering uniqueness, primary defense). MIGRATION 0028 Op 2 adds partial unique `one_fe_per_factura (uuid_factura) WHERE uuid_factura IS NOT NULL` (defense in depth — natural business constraint: 1 FE per internal factura; F1.9's `one_factura_per_salida` on `prod.facturas` already enforces this transitively, the partial UK is redundant safety for the case where `uuid_factura` is nullable).
- **Audit/sync**: trigger `factura_electronica_audit_columns` (BEFORE INSERT, sets `created_at`, `created_by`), trigger `factura_electronica_set_vigente_inicial` (BEFORE INSERT, sets `vigente_inicial`), trigger `factura_electronica_enqueue_sync` (AFTER INSERT, calls `prod.fn_enqueue_sync()`) — all per migration 0001 lines 2646-2712 + 2864-2900. **NO new triggers.**

### 5.3 `prod.envio_dian` `[L-W]` (insert-only per transition, composite PK `(uuid, fecha_retencion_hasta)`)

- **Operations**: V2/V4 SELECT chain tip (`repo/workflow.read_chain_tip`); INSERT initial row in same TX as `factura_electronica`; INSERT retry rows via `/reintentar`.
- **Columns read/written**:
  - Read: `uuid`, `uuid_factura_electronica`, `uuid_envio_padre`, `estado`, `cufe`, `timestamp_evento`, `vigente_desde`, `vigente_hasta`.
  - Write (INSERT): `uuid_sucursal`, `uuid_factura_electronica`, `uuid_resolucion_facturacion`, `payload: {prefijo, consecutivo, uuid_factura}` (JSONB), `respuesta_proveedor=NULL`, `cufe=NULL`, `uuid_envio_padre=NULL` (initial) or `<tip.uuid>` (retry), `timestamp_evento=now()`, `estado='pendiente'`, `fecha_retencion_hasta = date.today() + timedelta(days=5*365)`.
- **Indexes**: existing UK02 `(uuid_factura_electronica, uuid_envio_padre)` per migration 0001 line 901 (chain integrity — the chain is the natural constraint; multiple `envio_dian` rows per `uuid_factura_electronica` are allowed because that's the retry chain). MIGRATION 0028 Op 3 adds covering `idx_envio_dian_chain_tip (uuid_factura_electronica, timestamp_evento DESC)` for the JOIN to `v_factura_electronica_acuse`.
- **Sync direction**: FLIPPED via MIGRATION 0028 Op 1 from `cloud_to_branch` to `branch_to_cloud` (DEC-FE-01, §3).

---

## 6. Decisions

### 6.1 DEC-FE-01 — `envio_dian` is branch-initiated; sync catalog flipped (RESOLVES R1 HIGH)

**Decision**: `prod.envio_dian` INSERTs happen at the BRANCH for initial state + every retry transition. The sync catalog direction is flipped from `cloud_to_branch` to `branch_to_cloud` in MIGRATION 0028 Op 1. The cloud dispatcher consumes the chain via sync replication for analytics + state-machine advancement (`pendiente → enviado → aceptado | rechazado`). The ER diagram comment is updated post-archive from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync".

**Rationale**: plan.md is the canonical authority (per user mandate "siempre remitete al plan.md" línea 953 mandates branch INSERTs). The cloud-only design is incompatible with retry semantics (UUID v4 generation must be offline-safe; UPDATE would break the audit trail). The `[L-W]` WorkflowBase mandate of INSERT-only per transition is preserved. The cloud dispatcher architecture was decided out-of-band in AGENTS.md; the F1.10 design reflects that architecture by having the branch own the chain and the cloud consume it.

**Alternatives considered**:
- *Option (a) cloud owns ALL `envio_dian` writes* — REJECTED. Forces a synchronous round-trip on every retry, incompatible with offline-first. Adds latency to the `/reintentar` endpoint. R1 risk class.
- *Option (b) branch creates a separate `factura_electronica_reintento` request marker + cloud owns `envio_dian`* — REJECTED. Adds a new table for no clear win; the chain semantics already capture the intent. R1 risk class.

### 6.2 DEC-FE-02 — Retry chain via NEW row + `uuid_envio_padre` (NEVER UPDATE)

**Decision**: The retry chain is materialized as N `prod.envio_dian` rows, each with `uuid_envio_padre` pointing at the previous chain tip. **NEVER UPDATE** on `estado`, `cufe`, `uuid_envio_padre`, or any user-meaningful field. The `[L-W]` WorkflowBase MAY UPDATE `vigente_hasta` for bi-temporal versioning (close current version, insert new version with `vigente_desde=now()`, `vigente_hasta=NULL`) — but only `vigente_hasta` is touched; the user-meaningful fields stay insert-only.

**Rationale**: 4NF compliance (state lives on `envio_dian.estado`, not duplicated on `factura_electronica`). Audit trail completeness (every transition is a row, with `created_at`, `created_by`, `timestamp_evento`). Cloud-dispatcher-outage tolerance (the chain grows locally; cloud catches up via sync).

**Alternatives considered**:
- *UPDATE in-place on `envio_dian`* — REJECTED. Breaks audit trail. R7 risk (regulatory exposure: DIAN audit requires immutable transitions).
- *Separate `envio_dian_history` table* — REJECTED. The chain IS the history; a separate table adds query complexity without benefit.

### 6.3 DEC-FE-03 — Range exhaustion → 409 `numeracion_agotada` + alerta `fe_numbering_exhausted`

**Decision**: When `assign_consecutivo` raises `ConsecutivoRangeExhaustedError` (verified, helper source lines 143-147), the handler catches it, fires the already-seeded alerta `fe_numbering_exhausted` via `repo/alert_types.py::AlertaFactory`, and returns `409 {"error": "numeracion_agotada", "uuid_resolucion_facturacion": ..., "rango_hasta": ..., "prefijo": ...}`.

**Rationale**: plan.md línea 949 mandates this behavior. The alerta is already seeded (per the same line). The typed error response gives the client enough context to act (request a new resolution from DIAN).

**Alternatives considered**:
- *Fallback numbering `SIM-YYYY-MM-DD-NNNNNN`* — REJECTED. Plan.md línea 951 explicitly forbids this: "la condición que la activaría ya no existe porque `assign_consecutivo` (numeración real) está construido y en uso".

### 6.4 DEC-FE-04 — Retry NOT allowed on `aceptado` → 409 `reintento_no_permitido`

**Decision**: When the chain tip state is `aceptado`, the `/reintentar` endpoint returns `409 {"error": "reintento_no_permitido", "uuid_factura_electronica": ..., "estado_actual": "aceptado"}`. Only `rechazado` chain tips may be retried (per plan.md línea 969).

**Rationale**: `aceptado` is the terminal success state — retrying would create a phantom chain that misleads DIAN audits. The 409 prevents accidental retry storms from operators.

**Alternatives considered**:
- *Allow retry on `aceptado` for "corrective" chain entries* — REJECTED. There's no corrective action at this layer; corrective actions are F1.13 anulaciones territory.
- *Allow retry on `pendiente` or `enviado`* — REJECTED. The cloud dispatcher is still working; the client just needs to wait. The `envio_dian_already_pending` 409 covers the rapid-retry case (V2 chain-tip guard).

### 6.5 DEC-FE-05 — `assign_consecutivo` reused as-is (NO modification)

**Decision**: `assign_consecutivo` is reused verbatim from F1.9 / T-PR9-002 / D1-rev. F1.10 does NOT modify the helper, does NOT change its signature, does NOT add new exceptions.

**Rationale**: Verified by reading the source: signature returns `int` (consecutivo only), uses `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion`, idempotent per `(resolucion_uuid, source_event_uuid)` pair, raises `ConsecutivoRangeExhaustedError` on range exhaustion. Modifying the helper would risk breaking F1.9's contract.

**Alternatives considered**:
- *Wrap `assign_consecutivo` in a new helper that also snapshots the prefijo* — REJECTED. The prefijo is read directly from `resolucion_facturacion` row in step 6 of the handler (V4). No abstraction needed.

---

## 7. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Architectural conflict on `envio_dian` ownership** — plan.md says branch INSERTs; ER says CLOUD-ONLY; sync catalog says `cloud_to_branch`. | **HIGH (RESOLVED)** | DEC-FE-01 (§6.1) + MIGRATION 0028 Op 1 sync catalog flip + ER diagram update post-archive. Documented in §3 of this proposal. |
| **R2** | Vigente resolution lookup at handler entry — the SELECT must return the latest vigente row at `NOW()` for the sucursal. If `prod.resolucion_facturacion` has multiple version rows over time (bi-temporal VersionedBase), the V3 SELECT must defensively `ORDER BY vigente_desde DESC LIMIT 1`. | **MEDIUM** | Use `repo/versioned.buscar_vigente_por_uuid` (F1.5 PR5-016) or new helper `repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal(session, *, uuid_sucursal)` with explicit `ORDER BY vigente_desde DESC LIMIT 1 WHERE vigente_hasta IS NULL AND estado='activo'`. Unit test `test_buscar_resolucion_vigente_por_sucursal_returns_latest`. |
| **R3** | Chain integrity via `uuid_envio_padre` FK — verify the FK constraint enforces referential integrity and that the chain can be reconstructed by recursive SELECT on `uuid_envio_padre`. | **MEDIUM** | Existing UK02 `(uuid_factura_electronica, uuid_envio_padre)` per migration 0001 line 901 provides chain integrity. Helper `repo/workflow.read_chain_tip` (F1.5 PR5-016) reconstructs the chain via `ORDER BY timestamp_evento DESC LIMIT 1`. Unit test `test_crear_envio_dian_reintento_sets_uuid_envio_padre` + `test_buscar_envio_dian_chain_tip_returns_latest`. |
| **R4** | DIAN web service integration — MVP mocks the response; real integration deferred to Fase 4. The `/reintentar` endpoint does NOT actually call DIAN; it only INSERTs a new `envio_dian` row. The cloud dispatcher (out of F1.10 scope) is what eventually talks to DIAN. | **LOW** | Documented as out-of-scope. `500 dian_unavailable` reserved for Fase 4. |
| **R5** | Prefijo snapshot on `prod.factura_electronica` — the prefijo is denormalized from `prod.resolucion_facturacion` at INSERT time. The vigente row may later change (new resolution supersedes the old one), but old FE rows keep their original prefijo. | **LOW** | This is CORRECT per 4NF + plan.md line 697. Documented in design.md. The snapshot is the historical truth. No mitigation needed beyond documentation. |

---

## 8. Defense in Depth

5 layers mirror the F1.9 precedent:

### Layer 1 — KD-3 issuer chain

`_fe_issuer_dep = requires_issuer("operador-", "admin-")` (F1.9 pattern verbatim). Branch operator with `emitir_factura` permission emits; admin cross-branch. Applied at handler entry as a FastAPI dependency. The dependency runs BEFORE any handler body code.

### Layer 2 — Tenant scope post-V1

After resolving `target_sucursal` from `prod.facturas.uuid_sucursal` (V1 in `POST /factura-electronica`) or from `prod.factura_electronica.uuid_sucursal` (V1 in `GET` and `/reintentar`), if `ctx.issuer_prefix == "operador-"` and `target_sucursal != ctx.sucursal_uuid`, return `403 {"error": "tenant_scope_violation"}`. Admin (`admin-`) bypasses. Same KD-S2 analog from F1.7.

### Layer 3 — DB-layer partial unique index `one_fe_per_factura`

MIGRATION 0028 Op 2: `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL`. Defense in depth: the natural business constraint is 1 FE per internal factura; the partial UK enforces it at the DB layer even if the application-layer V2 SELECT-before-INSERT race window opens. `UniqueViolationError` (psycopg2/asyncpg pgcode 23505) maps to `409 factura_electronica_ya_existe`.

### Layer 4 — `assign_consecutivo` SELECT FOR UPDATE

`repo/resolucion_facturacion.py::assign_consecutivo` already takes `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion` (verified, source lines 114-120). Lock held until `await session.commit()`. Concurrent calls on the SAME resolution serialize cleanly. **NO modification** in F1.10.

### Layer 5 — Handler 409 mapping + typed exceptions

`api/v1/facturacion.py` 3 handlers each map typed exceptions to HTTP responses:

| Typed exception (helper) | HTTP | `error` body | Source |
|---|---|---|---|
| `ConsecutivoRangeExhaustedError` | 409 | `numeracion_agotada` + `rango_hasta` + `prefijo` | `assign_consecutivo` |
| `FacturaElectronicaYaExisteError` | 409 | `factura_electronica_ya_existe` + `uuid_factura` | `repo/factura_electronica.py` |
| `ReintentoNoPermitidoError` | 409 | `reintento_no_permitido` + `estado_actual` | `repo/factura_electronica.py` |
| `EnvioDianAlreadyPendingError` | 409 | `envio_dian_already_pending` | `repo/factura_electronica.py` |
| `FacturaNoEncontradaElectronicaError` | 404 | `factura_no_encontrada` + `uuid_factura` | `repo/factura_electronica.py` |
| `FacturaElectronicaNoEncontradaError` | 404 | `factura_electronica_no_encontrada` | `repo/factura_electronica.py` |
| `ResolucionNoVigenteError` | 409 | `resolucion_no_vigente` + `uuid_sucursal` | `repo/resolucion_facturacion.py` (NEW) |
| `UniqueViolationError` (pgcode 23505) on `factura_electronica_uk01` | 409 | `numeracion_duplicada` (race on `(resolucion, consecutivo)`) | psycopg2/asyncpg handler |

The pgcode NEVER appears in the response body, headers, or info+ logs.

---

## 9. API Contracts

Same schemas as the orchestrator brief, in full Pydantic v2 form:

### 9.1 Request schemas

```python
class FacturaElectronicaCreate(_Base):
    """HU-F1.10: POST /api/v1/facturacion/factura-electronica payload.

    Client supplies ONLY uuid_factura. Server resolves vigente resolution,
    assigns prefijo+consecutivo via assign_consecutivo, INSERTs FE row +
    initial envio_dian row. extra='forbid' blocks client smuggling.
    """
    uuid_factura: uuid_lib.UUID
```

### 9.2 Response schemas

```python
class EnvioDianRead(_Base):
    """Single envio_dian row in the chain."""
    uuid: uuid_lib.UUID
    uuid_factura_electronica: uuid_lib.UUID
    estado: Literal["pendiente", "enviado", "aceptado", "rechazado"]
    timestamp_evento: datetime
    uuid_envio_padre: uuid_lib.UUID | None
    cufe: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    motivo_rechazo: Annotated[str, StringConstraints(max_length=500)] | None = None


class FacturaElectronicaRead(_Base):
    """POST + GET /api/v1/facturacion/factura-electronica response.

    estado, cufe, timestamp_evento are SERVER-DERIVED from the latest
    envio_dian row via prod.v_factura_electronica_acuse. NEVER stored on
    prod.factura_electronica (4NF + insert-only).
    """
    uuid: uuid_lib.UUID
    prefijo: Annotated[str, StringConstraints(min_length=1, max_length=10)]
    consecutivo: int = Field(ge=0)
    uuid_factura: uuid_lib.UUID
    uuid_resolucion_facturacion: uuid_lib.UUID
    created_at: datetime
    envio_actual: EnvioDianRead


class EnvioDianRetryRead(_Base):
    """POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar response."""
    uuid: uuid_lib.UUID  # the NEW envio_dian row's uuid
    uuid_factura_electronica: uuid_lib.UUID
    estado: Literal["pendiente"]
    timestamp_evento: datetime
    uuid_envio_padre: uuid_lib.UUID  # previous tip
```

### 9.3 Typed error schemas

```python
class NumeracionAgotadaError(_Base):
    error: Literal["numeracion_agotada"]
    uuid_resolucion_facturacion: str
    rango_hasta: int
    prefijo: str


class ReintentoNoPermitidoError(_Base):
    error: Literal["reintento_no_permitido"]
    uuid_factura_electronica: str
    estado_actual: Literal["aceptado"]


class FacturaElectronicaYaExisteError(_Base):
    error: Literal["factura_electronica_ya_existe"]
    uuid_factura: str


class FacturaNoEncontradaElectronicaError(_Base):
    error: Literal["factura_no_encontrada"]
    uuid_factura: str


class FacturaElectronicaNoEncontradaError(_Base):
    error: Literal["factura_electronica_no_encontrada"]
    uuid_factura_electronica: str


class EnvioDianAlreadyPendingError(_Base):
    error: Literal["envio_dian_already_pending"]
    uuid_factura_electronica: str
    uuid_envio_pendiente: str


class ResolucionNoVigenteError(_Base):
    error: Literal["resolucion_no_vigente"]
    uuid_sucursal: str
```

Append to `schemas/facturacion.py` + update `__all__`. `extra='forbid'` (inherited from `_Base`) rejects client smuggling.

---

## 10. Handler Skeleton

Three handlers, each mirroring the F1.9 12-step chain pattern. All single-commit (KD-FE-01).

### 10.1 `POST /factura-electronica` — 12-step chain

```python
async def create_factura_electronica(
    response: Response,
    payload: FacturaElectronicaCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_fe_issuer_dep),
) -> FacturaElectronicaRead:
    no_store = no_store_headers()

    # Step 1: KD-3 issuer + no_store (resolved via DI)

    # Step 2: V1 — prod.facturas.uuid exists
    factura = await repo_factura_electronica.buscar_factura_por_uuid(
        session, uuid_factura=payload.uuid_factura
    )
    if factura is None:
        raise HTTPException(404, {"error": "factura_no_encontrada", "uuid_factura": str(payload.uuid_factura)}, headers=no_store)

    # Step 3: Tenant scope post-V1 (KD-S2 analog from F1.7)
    target_sucursal = factura.uuid_sucursal
    if ctx.issuer_prefix == "operador-" and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid):
        raise HTTPException(403, {"error": "tenant_scope_violation"}, headers=no_store)

    # Step 4: V2 — NO existing prod.factura_electronica row for this uuid_factura
    existing_fe = await repo_factura_electronica.buscar_factura_electronica_por_factura(
        session, uuid_factura=payload.uuid_factura
    )
    if existing_fe is not None:
        raise HTTPException(409, {"error": "factura_electronica_ya_existe", "uuid_factura": str(payload.uuid_factura)}, headers=no_store)

    # Step 5: V3 — current resolucion_facturacion row exists for the sucursal
    resolucion = await repo_resolucion_facturacion.buscar_resolucion_vigente_por_sucursal(
        session, uuid_sucursal=target_sucursal
    )
    if resolucion is None:
        raise HTTPException(409, {"error": "resolucion_no_vigente", "uuid_sucursal": str(target_sucursal)}, headers=no_store)

    # Step 6: KD-FE-01 — assign_consecutivo (SELECT FOR UPDATE on resolucion row)
    try:
        consecutivo = await assign_consecutivo(
            session,
            resolucion_uuid=resolucion.uuid,
            source_event_uuid=payload.uuid_factura,
        )
    except ConsecutivoRangeExhaustedError as exc:
        await AlertaFactory(session, ctx).fire("fe_numbering_exhausted", motivo=str(exc))
        raise HTTPException(409, {"error": "numeracion_agotada", "uuid_resolucion_facturacion": str(resolucion.uuid), "rango_hasta": resolucion.rango_hasta, "prefijo": resolucion.prefijo}, headers=no_store)

    # Step 7: INSERT prod.factura_electronica [L-E]
    new_fe = await repo_factura_electronica.crear_factura_electronica_inicial(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_factura=payload.uuid_factura,
        uuid_resolucion_facturacion=resolucion.uuid,
        prefijo=resolucion.prefijo,
        consecutivo=consecutivo,
    )

    # Step 8: INSERT initial prod.envio_dian row (estado='pendiente', uuid_envio_padre=NULL)
    new_envio = await repo_factura_electronica.crear_envio_dian_inicial(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_factura_electronica=new_fe.uuid,
        uuid_resolucion_facturacion=resolucion.uuid,
        payload={"prefijo": resolucion.prefijo, "consecutivo": consecutivo, "uuid_factura": str(payload.uuid_factura)},
    )

    # Step 9: Mock DIAN POST (real integration deferred Fase 4)
    # In MVP, the cloud dispatcher reads via sync and writes the transition rows asynchronously.
    # No synchronous DIAN call here.

    # Step 10: KD-FE-01 single commit
    await session.commit()

    # Step 11: response shape + no_store header
    apply_no_store_header(response)
    return FacturaElectronicaRead(
        uuid=new_fe.uuid,
        prefijo=new_fe.prefijo,
        consecutivo=new_fe.consecutivo,
        uuid_factura=new_fe.uuid_factura,
        uuid_resolucion_facturacion=new_fe.uuid_resolucion_facturacion,
        created_at=new_fe.created_at,
        envio_actual=EnvioDianRead(
            uuid=new_envio.uuid,
            uuid_factura_electronica=new_fe.uuid,
            estado="pendiente",
            timestamp_evento=new_envio.timestamp_evento,
            uuid_envio_padre=None,
            cufe=None,
            motivo_rechazo=None,
        ),
    )
```

### 10.2 `GET /factura-electronica/{uuid}` — 3-step chain

```python
async def get_factura_electronica(
    response: Response,
    uuid_factura_electronica: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_fe_issuer_dep),
) -> FacturaElectronicaRead:
    no_store = no_store_headers()

    # Step 1: KD-3 issuer + no_store (resolved via DI)

    # Step 2: V1 — FE row exists + tenant scope
    fe = await repo_factura_electronica.buscar_factura_electronica_por_uuid(session, uuid=uuid_factura_electronica)
    if fe is None:
        raise HTTPException(404, {"error": "factura_electronica_no_encontrada", "uuid_factura_electronica": str(uuid_factura_electronica)}, headers=no_store)
    if ctx.issuer_prefix == "operador-" and (ctx.sucursal_uuid is None or fe.uuid_sucursal != ctx.sucursal_uuid):
        raise HTTPException(403, {"error": "tenant_scope_violation"}, headers=no_store)

    # Step 3: JOIN prod.v_factura_electronica_acuse for estado + cufe + timestamp_evento
    ack = await session.execute(
        text("SELECT estado, cufe, timestamp_evento FROM prod.v_factura_electronica_acuse WHERE uuid_factura_electronica = :uuid"),
        {"uuid": str(uuid_factura_electronica)},
    ).first()

    # Step 4: response shape
    apply_no_store_header(response)
    return FacturaElectronicaRead(
        uuid=fe.uuid,
        prefijo=fe.prefijo,
        consecutivo=fe.consecutivo,
        uuid_factura=fe.uuid_factura,
        uuid_resolucion_facturacion=fe.uuid_resolucion_facturacion,
        created_at=fe.created_at,
        envio_actual=EnvioDianRead(
            uuid=... or chain_tip.uuid,  # chain tip uuid from JOIN or fallback
            uuid_factura_electronica=fe.uuid,
            estado=ack.estado if ack else "pendiente",
            timestamp_evento=ack.timestamp_evento if ack else None,
            uuid_envio_padre=None,  # GET response does not expose chain
            cufe=ack.cufe if ack else None,
            motivo_rechazo=None,
        ),
    )
```

### 10.3 `POST /factura-electronica/{uuid}/reintentar` — 8-step chain

```python
async def retry_factura_electronica(
    response: Response,
    uuid_factura_electronica: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_fe_issuer_dep),
) -> EnvioDianRetryRead:
    no_store = no_store_headers()

    # Step 1: KD-3 issuer + no_store (resolved via DI)

    # Step 2: V1 — FE row exists
    fe = await repo_factura_electronica.buscar_factura_electronica_por_uuid(session, uuid=uuid_factura_electronica)
    if fe is None:
        raise HTTPException(404, {"error": "factura_electronica_no_encontrada", "uuid_factura_electronica": str(uuid_factura_electronica)}, headers=no_store)

    # Step 3: Tenant scope post-V1
    if ctx.issuer_prefix == "operador-" and (ctx.sucursal_uuid is None or fe.uuid_sucursal != ctx.sucursal_uuid):
        raise HTTPException(403, {"error": "tenant_scope_violation"}, headers=no_store)

    # Step 4: V2 — chain tip state check (no retry if aceptado, no rapid retry if pendiente)
    tip_envio = await repo_factura_electronica.buscar_envio_dian_chain_tip(
        session, uuid_factura_electronica=uuid_factura_electronica
    )
    if tip_envio is None:
        raise HTTPException(409, {"error": "reintento_no_permitido", "uuid_factura_electronica": str(uuid_factura_electronica), "estado_actual": None}, headers=no_store)
    if tip_envio.estado == "aceptado":
        raise HTTPException(409, {"error": "reintento_no_permitido", "uuid_factura_electronica": str(uuid_factura_electronica), "estado_actual": "aceptado"}, headers=no_store)
    if tip_envio.estado == "pendiente":
        raise HTTPException(409, {"error": "envio_dian_already_pending", "uuid_factura_electronica": str(uuid_factura_electronica), "uuid_envio_pendiente": str(tip_envio.uuid)}, headers=no_store)

    # Step 5: KD-FE-01 — INSERT new envio_dian row with uuid_envio_padre=tip.uuid, estado='pendiente'
    new_envio = await repo_factura_electronica.crear_envio_dian_reintento(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_factura_electronica=uuid_factura_electronica,
        uuid_resolucion_facturacion=fe.uuid_resolucion_facturacion,
        payload={"prefijo": fe.prefijo, "consecutivo": fe.consecutivo, "uuid_factura": str(fe.uuid_factura)},
        uuid_envio_padre=tip_envio.uuid,
    )

    # Step 6: Mock DIAN POST (real deferred Fase 4)
    # Cloud dispatcher reads via sync and writes transition rows asynchronously.

    # Step 7: KD-FE-01 single commit
    await session.commit()

    # Step 8: response shape + no_store header
    apply_no_store_header(response)
    return EnvioDianRetryRead(
        uuid=new_envio.uuid,
        uuid_factura_electronica=uuid_factura_electronica,
        estado="pendiente",
        timestamp_evento=new_envio.timestamp_evento,
        uuid_envio_padre=tip_envio.uuid,
    )
```

---

## 11. Tests

7 test files, ~630 LOC tests + ~230 LOC production = ~860 LOC cumulative. All AST walks + handler tests pattern after F1.9.

### 11.1 `tests/unit/test_factura_electronica_numeracion.py` (~120 LOC, 3 tests)

The 3 tests mandated by plan.md línea 971:

- `test_asignacion_normal_exitosa_returns_201` — happy path: POST `/factura-electronica` with valid `uuid_factura` → 201 with `prefijo`, `consecutivo`, `estado='pendiente'`. Verifies `prod.factura_electronica` row + `prod.envio_dian` initial row both populated atomically.
- `test_rango_agotado_returns_409_with_alerta` — `prod.resolucion_facturacion.rango_hasta` = `consecutivo_actual` (exhausted) → `assign_consecutivo` raises → handler catches, fires `fe_numbering_exhausted` alerta, returns 409 `numeracion_agotada`. Verifies alerta row created.
- `test_reintento_encadenado_creates_new_envio_chain` — happy path: POST `/reintentar` on `rechazado` FE → 201 with `uuid_envio_padre` pointing at previous tip. Verifies the chain grows; chain integrity via `uuid_envio_padre` self-FK.

### 11.2 `tests/unit/test_factura_electronica_schemas.py` (~80 LOC, 4 tests)

- `test_fe_create_rejects_prefijo_injection` — `extra='forbid'` rejects `prefijo='SETP'`.
- `test_fe_create_rejects_consecutivo_injection` — rejects `consecutivo=4521`.
- `test_fe_create_rejects_uuid_resolucion_injection` — rejects `uuid_resolucion_facturacion=...`.
- `test_numeracion_agotada_error_schema_typed` — typed error schema with `uuid_resolucion_facturacion`, `rango_hasta`, `prefijo`.

### 11.3 `tests/unit/test_factura_electronica_repo.py` (~100 LOC, 4 tests)

- `test_buscar_factura_electronica_por_factura_returns_none` — no FE yet.
- `test_crear_factura_electronica_inicial_inserts_row` — happy path.
- `test_buscar_envio_dian_chain_tip_returns_latest` — chain tip helper with multiple retries.
- `test_crear_envio_dian_reintento_sets_uuid_envio_padre` — chain linking.
- `test_crear_envio_dian_reintento_initial_no_padre` — initial envio has `uuid_envio_padre=NULL`.

### 11.4 `tests/unit/test_factura_electronica_create_handler.py` (~120 LOC, 5 tests)

- `test_create_fe_happy_path_returns_201` — full path: assign_consecutivo + new FE row + initial envio row.
- `test_create_fe_assign_consecutivo_idempotent_on_retry` — same `uuid_factura` returns same `consecutivo`.
- `test_create_fe_returns_404_factura_no_encontrada` — V1.
- `test_create_fe_returns_409_factura_electronica_ya_existe` — V2.
- `test_create_fe_returns_409_numeracion_agotada_alerta_fired` — range exhausted → alerta + 409.

### 11.5 `tests/unit/test_factura_electronica_get_handler.py` (~50 LOC, 2 tests)

- `test_get_fe_returns_estado_aceptado_with_cufe` — JOIN view returns latest envio.
- `test_get_fe_returns_estado_pendiente_when_no_envio` — fallback to 'pendiente'.

### 11.6 `tests/unit/test_factura_electronica_retry_handler.py` (~80 LOC, 3 tests)

- `test_retry_fe_happy_path_returns_201_with_new_envio` — rejected chain tip → new pendiente envio.
- `test_retry_fe_returns_409_si_chain_tip_aceptado` — terminal state.
- `test_retry_fe_returns_404_si_fe_no_existe` — V1.

### 11.7 `tests/integration/test_migration_0028_idempotent.py` (~80 LOC, 3 tests)

- `test_migration_0028_idempotent_upgrade_downgrade_upgrade` — full cycle.
- `test_sync_catalog_envio_dian_direction_flipped_to_branch_to_cloud` — DEC-FE-01 verification.
- `test_one_fe_per_factura_partial_uk_blocks_duplicate_fe` — partial UK defense in depth.

### 11.8 AST walks (mandatory)

- `tests/static/test_fe_handler_single_commit.py` (~40 LOC, 1 AST walk) — `ast.walk()` over `create_factura_electronica` body enforces `len(commits) == 1` literal.
- `tests/static/test_fe_retry_handler_single_commit.py` (~40 LOC, 1 AST walk) — same invariant for `retry_factura_electronica`.

Total: ~24 tests across 7 test files + 2 AST walks.

---

## 12. Out of Scope

1. **Real DIAN web service integration** — deferred to Fase 4 (contabilidad). The cloud dispatcher handles the actual provider call asynchronously (out of F1.10 scope).
2. **Automatic retry policy (exponential backoff)** — cloud dispatcher concern; the branch endpoint only INSERTs the retry row, the dispatcher decides when to pick it up.
3. **CUFE signing** — Fase 4. `cufe` is currently NULL on initial envio; populated by cloud dispatcher when DIAN returns the signed CUFE.
4. **`prod.factura_electronica.xml_firmado` column** — Fase 4. Not in scope for F1.10.
5. **Multi-resolution concurrent numbering** — out of scope for F1.10; MVP supports a single vigente resolution per prefijo per sucursal. Future HUs may add concurrent resolution support.
6. **Anulación of FE** — F1.13 owns. `prod.anulaciones` workflow (with `tipo_anulable='factura_electronica'`) is the canonical path for cancellation.
7. **Cloud-side state-machine advancement** (`pendiente → enviado → aceptado | rechazado`) — out of F1.10 scope. The cloud dispatcher writes transition rows on the same `prod.envio_dian` chain via the (now-flipped) `branch_to_cloud` sync channel.
8. **`GET /api/v1/facturacion/factura-electronica?uuid_factura=...`** (paginated list) — proposed adjacent endpoint, lower priority, out of F1.10 scope.
9. **`cufe` column on `prod.factura_electronica`** — explicitly FORBIDDEN per 4NF (ER línea 700: "cufe y reportado_dian eliminados (4FN): derivados - fuente: envio_dian (vista)"). The `cufe` lives on `prod.envio_dian` only; the read response derives it via `v_factura_electronica_acuse`.
10. **`reportado_dian` boolean on `prod.factura_electronica`** — explicitly FORBIDDEN per plan.md línea 947. The raw `estado` enum from `prod.envio_dian` is the only source of truth.

---

## 13. Requirements (REQ-OPS-064..074)

The following REQ-OPS-NNN placeholders will be formalized by `sdd-spec` in `openspec/changes/hu-f1-10-numeracion-fe-dian-reintento/specs/operations/spec.md`:

- **REQ-OPS-064 (NEW)** — `POST /api/v1/facturacion/factura-electronica` contract: `FacturaElectronicaCreate` input (`{uuid_factura}` only) + `FacturaElectronicaRead` output (server-derived `estado`, `cufe`, `timestamp_evento` from `prod.v_factura_electronica_acuse`). KD-3 issuer chain (`requires_issuer("operador-", "admin-")`); `Cache-Control: no-store`; `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse from F1.6 + F1.9).

- **REQ-OPS-065 (NEW)** — V1: `prod.facturas.uuid` exists. SELECT por PK; si no existe → 404 `factura_no_encontrada`. Defense-in-depth via partial unique index `one_fe_per_factura` (MIGRATION 0028 Op 2) — `UniqueViolationError` → 409 `factura_electronica_ya_existe`.

- **REQ-OPS-066 (NEW)** — V2: NO existing `prod.factura_electronica` row for `uuid_factura`. SELECT por `uuid_factura`; si existe → 409 `factura_electronica_ya_existe`. Partial UK `one_fe_per_factura` provides DB-layer defense in depth.

- **REQ-OPS-067 (NEW)** — V3: `prod.resolucion_facturacion` vigente row for the sucursal. SELECT `WHERE uuid_sucursal=:s AND vigente_hasta IS NULL AND estado='activo' ORDER BY vigente_desde DESC LIMIT 1` (defensive). Si no existe → 409 `resolucion_no_vigente`.

- **REQ-OPS-068 (NEW, KD-FE-01)** — `assign_consecutivo(session, *, resolucion_uuid, source_event_uuid) -> int` is reused as-is. SELECT FOR UPDATE on `prod.resolucion_facturacion` row + atomic MAX()+1 + idempotency check via existing FE row for `(resolucion_uuid, uuid_factura)`. Returns `int` (consecutivo). Caller snapshots `prefijo` from the vigente resolution row.

- **REQ-OPS-069 (NEW, DEC-FE-03)** — Range exhaustion (`next_value > rango_hasta`) raises `ConsecutivoRangeExhaustedError` (helper source lines 143-147). Handler catches, fires alerta `fe_numbering_exhausted` via `AlertaFactory`, returns 409 `numeracion_agotada` with `uuid_resolucion_facturacion`, `rango_hasta`, `prefijo`.

- **REQ-OPS-070 (NEW)** — Single `await session.commit()` materializes `prod.factura_electronica` (1 row) + `prod.envio_dian` (1 initial row) atomically. AST walk `tests/static/test_fe_handler_single_commit.py` enforces literal `len(commits) == 1`. KD-FE-01 mirror of F1.9 KD-FACT-01.

- **REQ-OPS-071 (NEW, DEC-FE-04)** — Retry endpoint V2: chain tip state check. `pendiente` → 409 `envio_dian_already_pending` (cloud dispatcher hasn't picked up yet). `aceptado` → 409 `reintento_no_permitido` (terminal state). `rechazado` or `enviado` → happy INSERT.

- **REQ-OPS-072 (NEW, DEC-FE-02)** — Retry chain via NEW `prod.envio_dian` row with `uuid_envio_padre` pointing at the previous chain tip. NEVER UPDATE. The chain IS the audit trail.

- **REQ-OPS-073 (NEW, DEC-FE-01)** — `prod.envio_dian` writes are branch-initiated. MIGRATION 0028 Op 1 flips `sync_catalog.direction` from `cloud_to_branch` to `branch_to_cloud` for `envio_dian`. Cloud dispatcher consumes via sync replication. ER diagram comment updated post-archive from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync".

- **REQ-OPS-074 (NEW)** — `GET /api/v1/facturacion/factura-electronica/{uuid}` JOINs `prod.v_factura_electronica_acuse` (migration 0009, already present). Returns `FacturaElectronicaRead` with server-derived `estado`, `cufe`, `timestamp_evento` from the latest chain tip. NO `cufe` column on `prod.factura_electronica` (4NF).

---

## 14. Migrations

**MIGRATION 0028** (~120 LOC, 3 ops + 1 downgrade block). `down_revision = "0027_facturas_inmutable_trigger"`.

### Op 1 — Pre-flight + sync catalog flip (DEC-FE-01)

```sql
DO $$
BEGIN
    -- Pre-flight: verify the 4 tables F1.10 depends on exist
    ASSERT (
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='prod' AND table_name IN
        ('factura_electronica', 'envio_dian', 'resolucion_facturacion', 'facturas')
    ) = 4,
        'F1.10 requires 4 tables to exist';

    -- DEC-FE-01: flip envio_dian sync direction from cloud_to_branch to branch_to_cloud
    UPDATE sync_catalog
    SET direction = 'branch_to_cloud'
    WHERE table_name = 'envio_dian' AND direction = 'cloud_to_branch';
END $$;
```

### Op 2 — Partial unique index `one_fe_per_factura`

```sql
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura
    ON prod.factura_electronica (uuid_factura)
    WHERE uuid_factura IS NOT NULL;
```

`CONCURRENTLY` for no lock on reads/writes during creation in production. `IF NOT EXISTS` for idempotency. Same pattern as F1.7 `one_exit_per_ingreso` (MIGRATION 0026 Op 4) and F1.9 `one_pago_per_factura_init` (MIGRATION 0027 Op 3).

### Op 3 — Covering index for chain tip lookup

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_envio_dian_chain_tip
    ON prod.envio_dian (uuid_factura_electronica, timestamp_evento DESC)
    WHERE uuid_factura_electronica IS NOT NULL;
```

Speeds up the GET endpoint JOIN to `prod.v_factura_electronica_acuse` (which uses `DISTINCT ON ... ORDER BY timestamp_evento DESC`). Without this index, the view's DISTINCT ON scan cost grows linearly with `envio_dian` rows per FE.

### Op 4 — REVOKE re-assertion (DEFENSIVE)

`prod.factura_electronica` and `prod.envio_dian` allow UPDATE on `vigente_hasta` for bi-temporal versioning. Re-assert GRANT to `rol_app` (no REVOKE needed):

```sql
GRANT SELECT, INSERT, UPDATE ON prod.factura_electronica TO rol_app;
GRANT SELECT, INSERT, UPDATE ON prod.envio_dian TO rol_app;
```

### Downgrade (reverse order, superuser context for DROP INDEX)

```sql
REVOKE SELECT, INSERT, UPDATE ON prod.factura_electronica FROM rol_app;
REVOKE SELECT, INSERT, UPDATE ON prod.envio_dian FROM rol_app;
DROP INDEX CONCURRENTLY IF EXISTS prod.idx_envio_dian_chain_tip;
DROP INDEX CONCURRENTLY IF EXISTS prod.one_fe_per_factura;

DO $$
BEGIN
    -- DEC-FE-01 downgrade: reverse sync catalog flip
    UPDATE sync_catalog
    SET direction = 'cloud_to_branch'
    WHERE table_name = 'envio_dian' AND direction = 'branch_to_cloud';
END $$;
```

---

## 15. References

- `plan.md` lines 939-979 (HU-F1.10 definition, 4 atomic tasks T1..T4, 230 LOC budget)
- `plan.md` line 951 (forbidden fallback `SIM-YYYY-MM-DD-NNNNNN` numbering)
- `plan.md` line 949 (alerta `fe_numbering_exhausted` already seeded)
- `modelo_datos_er.mmd` lines 689-705 (`factura_electronica` [L-E] snapshot pattern)
- `modelo_datos_er.mmd` lines 891-914 (`envio_dian` [L-W] self-FK chain) — **post-archive comment update**
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 875-891 (`factura_electronica` create_table + UK01)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 976-993 (`envio_dian` create_table + UK02)
- `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109 (`v_factura_electronica_acuse` view)
- `backend/packages/parkos_core/migrations/versions/0027_*` (F1.9 head — REVOKE on `prod.factura_electronica`)
- `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py` (LifecycleEventBase)
- `backend/packages/parkos_core/src/parkos_core/models/L_W/envio_dian.py` (WorkflowBase + self-FK `uuid_envio_padre`)
- `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` (VersionedBase, bi-temporal)
- `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo` (verified, no modification)
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py::read_chain_tip` (F1.5 PR5-016)
- `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py::AlertaFactory` (F1.8 T-PR8-002)
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136 (`envio_dian` catalog entry — **FLIPPED in DEC-FE-01**)
- `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (F1.9 patterns; `FacturaElectronicaCreate` PR6 schema EXCLUDES prefijo/consecutivo via `extra='forbid'`)
- `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (F1.9 handler pattern verbatim)
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/{exploration,proposal,design,tasks,verify-report,archive-report}.md` (precedent for KD-3 + 12-step chain + KD-FACT-01 single-commit + AST walks)
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/{exploration,proposal,design,tasks,verify-report,archive-report}.md` (precedent KD-S2 tenant scope, `one_exit_per_ingreso` partial UK)
- `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/{exploration,proposal,design,tasks}.md` (precedent `repo/workflow.read_chain_tip`)
- `openspec/specs/operations/spec.md` (66 REQs REQ-OPS-001..063 merged post-F1.9)
- `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-explore.md` (sdd-explore, observation #1568, 16 sections)

---

## 16. Cross-HU Implications

| HU | Relationship | Implication |
|---|---|---|
| **F1.9 (closed)** | F1.10 consumes `prod.facturas.uuid` (the internal factura created by F1.9) as the input to `POST /factura-electronica`. | V1 SELECT on `prod.facturas` is the entry point. F1.9's `one_factura_per_salida` partial UK provides the transitive guarantee that there's at most 1 FE per salida. |
| **F1.11 (Reimpresión tiquete)** | Independent. F1.11 creates `prod.reimpresion_ticket` rows; F1.10 reads `prod.factura_electronica` + `prod.envio_dian`. | No shared tables. No API interaction. |
| **F1.12 (Venta suscripción)** | Independent. F1.12 does not touch FE numbering. | No interaction. |
| **F1.13 (Arqueo + cierre_dia)** | F1.13 may consume `prod.envio_dian` for cierre_dia totals (count of `aceptado` envios per sucursal per day). | May need to add `envio_dian.estado = 'aceptado'` filter to F1.13 aggregation. F1.10 does NOT add this filter; F1.13 owns. |
| **F1.14 (sync estado)** | F1.14 may need to expose `envio_dian` counts per sucursal for the operator dashboard. | Now possible after DEC-FE-01 sync catalog flip (the chain is branch-side; cloud can aggregate). |
| **HU-F7.1 (Salida ingreso)** | F1.10 reads `prod.facturas.uuid_sucursal` to scope the vigente resolution lookup. | Tenant scope Layer 2 enforces operador- branch matching. |
| **HU-F8.1 (Facturación consumidor final)** | HU-F8.1 consumes the `FacturaElectronicaRead` response from F1.10 to display DIAN status in the operator terminal. | Unblocked after F1.10 archive. |

---

**End of proposal.**