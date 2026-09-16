# Design: HU-F1.10 — Numeración FE + estado DIAN + reintento

> **Change**: `hu-f1-10-numeracion-fe-dian-reintento`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.10 — `POST /api/v1/facturacion/factura-electronica` (assign `prefijo`+`consecutivo` via `repo/resolucion_facturacion.py::assign_consecutivo` SELECT FOR UPDATE, INSERT `prod.factura_electronica` 1:1 with `prod.facturas.uuid` + initial `prod.envio_dian` row with `estado='pendiente'`, `uuid_envio_padre=NULL`) + `GET /api/v1/facturacion/factura-electronica/{uuid}` (JOIN existing `prod.v_factura_electronica_acuse` view, expose raw `estado` (`pendiente|enviado|aceptado|rechazado`) + `cufe` + `timestamp_evento`) + `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` (INSERT new `prod.envio_dian` row with `uuid_envio_padre` pointing at previous chain tip, NEVER UPDATE).
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `47d5630`; F1.1..F1.9 closed)
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (16 sections, ~700 LOC, DEC-FE-01..05 + KD-FE-01..02, R1 RESOLVED) + `exploration.md` (observation #1568, R1..R5, R1 HIGH architectural conflict) + `specs/operations/spec.md` (REQ-OPS-064..074, 11 new requirements in Given/When/Then/And form + REQ-OPS-XR1..XR3 cross-cutting).
> **Cross-references**: `modelo_datos_er.mmd` (`prod.factura_electronica` 689-705 [L-E] snapshot pattern + `prod.envio_dian` 891-914 [L-W] self-FK chain + `prod.resolucion_facturacion` 315-332 [V] bi-temporal); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (`factura_electronica` 875-891 [L-E] + UK01 `(uuid_resolucion_facturacion, consecutivo)` + `envio_dian` 976-993 [L-W] + UK02 `(uuid_factura_electronica, uuid_envio_padre)` + FKs 1595-1842 + audit/versioning triggers 2646-2712 + sync enqueue triggers 2864-2900); `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109 (`prod.v_factura_electronica_acuse` view, `DISTINCT ON (uuid_factura_electronica) ORDER BY timestamp_evento DESC NULLS LAST, uuid DESC`); `backend/packages/parkos_core/migrations/versions/0027_*` (F1.9 head — Op 4 REVOKE on `prod.factura_electronica` and `prod.envio_dian`; `one_factura_per_salida` partial UK precedent); `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py` (LifecycleEventBase + UK + `fecha_retencion_hasta` re-declared); `backend/packages/parkos_core/src/parkos_core/models/L_W/envio_dian.py` (WorkflowBase + self-FK `uuid_envio_padre` + `cufe` + `estado` + re-declared `vigente_desde/vigente_hasta/estado`); `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` (VersionedBase, bi-temporal, `prefijo` + `rango_desde`/`rango_hasta`, NO `consecutivo_actual` per 4NF); `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo` (verified signature: `(session, *, resolucion_uuid, source_event_uuid) -> int`; lines 99-108 idempotency on `(resolucion_uuid, uuid_factura)`; lines 114-120 `SELECT … FOR UPDATE`; lines 143-147 `ConsecutivoRangeExhaustedError`); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py::read_chain_tip` (F1.5 PR5-016); `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py::AlertaFactory` (F1.8 T-PR8-002, fires `fe_numbering_exhausted` on range exhaustion); `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136 (`envio_dian` `cloud_to_branch` direction per D1-rev — **FLIPPED in DEC-FE-01** via MIGRATION 0028 Op 1); `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (F1.9 handler pattern verbatim, 3 new handlers added on the same router); `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (F1.9 patterns + new `FacturaElectronicaCreate`, `FacturaElectronicaRead`, `EnvioDianRead`, `EnvioDianRetryRead` + 8 typed error schemas).
> **Precedents mirrored**: F1.9 (REQ-OPS-053..063, KD-3 issuer `requires_issuer("operador-","admin-")` verbatim, 12-step handler chain, KD-FACT-01 single-commit, partial unique index pattern `one_factura_per_salida` migration 0027 Op 2, AST walk pattern `tests/static/test_factura_handler_single_commit.py`, `Idempotency-Key` header DEC-IDEM-01, commits `47d5630`), F1.8 (REQ-OPS-022..025, `repo/alert_types.py::AlertaFactory` for `fe_numbering_exhausted`, commit `a3d0c39`), F1.7 (REQ-OPS-042..052, KD-S2 tenant scope post-V1, `one_exit_per_ingreso` partial UK precedent migration 0026 Op 4, AST walk pattern, commits `c320d0f`+`aa2fc9b`+`f826e8c`), F1.6 (REQ-OPS-034..041, KD-7 pre-flight pattern migration 0024, `Idempotency-Key` header DEC-IDEM-01, commit `2a2cbd2`), F1.5 (REQ-OPS-030..033, MV pattern, `repo/workflow.py::read_chain_tip` for `envio_dian` chain tip, `v_factura_electronica_acuse` view migration 0009, commit `bb99e18`), F1.4 (REQ-OPS-017..021, bi-temporal VersionedBase pattern reusable for V3 lookup, commit `467b4f0`), F1.3 (REQ-OPS-026..029, partial unique index pattern + AST walk + pre-flight abort, commit `ca3f9bf`).

---

## 1. Title & Goal

**Design goal.** Deliver HU-F1.10: the back-end `POST /api/v1/facturacion/factura-electronica` endpoint that closes the DIAN regulatory extension on top of F1.9's internal billing by enforcing **six server-side validations V1..V6** plus the **KD-FE-01 single-commit invariant** that materializes the `prod.factura_electronica` row + initial `prod.envio_dian` row atomically in one `await session.commit()`. The design also ships **MIGRATION 0028** which (a) flips the `envio_dian` sync catalog direction from `cloud_to_branch` to `branch_to_cloud` (DEC-FE-01, resolution of the R1 HIGH architectural conflict identified in sdd-explore observation #1568 §15), (b) installs the partial unique index `one_fe_per_factura` on `prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL` (defense in depth alongside the existing UK `factura_electronica_uk01 (uuid_resolucion_facturacion, consecutivo)`), (c) adds the covering index `idx_envio_dian_chain_tip (uuid_factura_electronica, timestamp_evento DESC)` for the `GET` JOIN to `prod.v_factura_electronica_acuse`, and (d) defensively re-asserts GRANTs on the 3 tables (`factura_electronica`, `envio_dian`, `resolucion_facturacion`).

The design enforces **DEC-FE-01** (branch-initiated `envio_dian` writes; sync catalog flipped; ER diagram updated post-archive from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync"), **DEC-FE-02** (retry chain via NEW row + `uuid_envio_padre` pointing at previous chain tip, NEVER UPDATE on user-meaningful fields `estado`/`cufe`/`uuid_envio_padre`/`motivo_rechazo`), **DEC-FE-03** (range exhaustion → 409 `numeracion_agotada` + alerta `fe_numbering_exhausted` fired in same TX), **DEC-FE-04** (retry NOT allowed on chain tip `aceptado` → 409 `reintento_no_permitido`; NOT allowed on `pendiente` → 409 `envio_dian_already_pending`), **DEC-FE-05** (`assign_consecutivo` reused as-is, NO modification; SELECT FOR UPDATE + idempotency on `(resolucion_uuid, source_event_uuid)` already verified), **DEC-FE-06 (NEW)** (handler Step 12 response includes `Cache-Control: no-store` header per REQ-OPS-XR2), **DEC-FE-07 (NEW)** (handler emits NO UPDATE on `prod.envio_dian` user-meaningful fields; AST walk enforces REQ-OPS-070 + REQ-OPS-074), plus the **KD-FE-01 single-commit invariant** (mirror of F1.9 KD-FACT-01) and the **5-layer defense in depth** (KD-3 issuer chain + tenant scope + DB-layer partial UK + `assign_consecutivo` SELECT FOR UPDATE + handler 409 mapping).

The handler enforces 6 validations server-side (V1 `prod.facturas.uuid` exists → 404 `factura_no_encontrada`; V2 NO existing `prod.factura_electronica` row for `uuid_factura` → 409 `factura_electronica_ya_existe`; V3 vigente `prod.resolucion_facturacion` row for the sucursal → 409 `resolucion_no_vigente`; V4 `assign_consecutivo` range exhaustion → 409 `numeracion_agotada` + alerta fired; V5 on `/reintentar`, chain tip state guards → 409 `reintento_no_permitido` on `aceptado` OR 409 `envio_dian_already_pending` on `pendiente`; V6 status quo happy path), and materializes the FE row + initial envio row in a single TX. The `GET` endpoint JOINs the existing `prod.v_factura_electronica_acuse` view (migration 0009, already present) to expose `estado` + `cufe` + `timestamp_evento` derived server-side (NEVER fabricated `reportado_dian` boolean per plan.md línea 947). The `/reintentar` endpoint INSERTs a NEW `prod.envio_dian` row with `uuid_envio_padre=<tip.uuid>` and `estado='pendiente'`, growing the audit trail (NEVER UPDATE). All responses carry `Cache-Control: no-store`. Sized at **~230 LOC production** per `plan.md` línea 973 (≈ 60 LOC `api/v1/facturacion.py` 3 new handlers + 250 LOC `repo/factura_electronica.py` + 80 LOC `schemas/facturacion.py` + 40 LOC `repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal` — **+~180 LOC MIGRATION 0028** — + ~630 LOC tests across 7 files + ~120 LOC across 2 AST walks).

**Three new handlers, one new repo module, one new repo helper, one new migration, no factory changes, one sync catalog flip.**

---

## 2. Context & Background

`plan.md` lines **939-979** define HU-F1.10 as Fase-1 backend prerequisite for the DIAN regulatory extension (CU-04 + DIAN Resolución 000175 de 2021 + Decreto 2242 de 2015). The hard architectural constraints are **DEC-FE-01 amended** (F1.10 writes `envio_dian` from BRANCH per plan.md línea 953; sync catalog flipped from `cloud_to_branch` to `branch_to_cloud` in MIGRATION 0028 Op 1; ER comment updated post-archive from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync"), **DEC-FE-02** (retry chain via NEW row + `uuid_envio_padre` self-FK pointing at previous tip, NEVER UPDATE on user-meaningful fields), **DEC-FE-03** (range exhaustion → 409 `numeracion_agotada` + alerta `fe_numbering_exhausted` fired in same TX), **DEC-FE-04** (retry blocked on `aceptado` chain tip; blocked on `pendiente` for rapid-retry guard), **DEC-FE-05** (`assign_consecutivo` reused as-is, no modification), **DEC-FE-06 NEW** (`Cache-Control: no-store` on all responses, F1.3..F1.9 precedent), **DEC-FE-07 NEW** (no UPDATE on `prod.envio_dian` user-meaningful fields per REQ-OPS-070), the existing pre-existing tables (`prod.factura_electronica` [L-E] lines 875-891 of migration 0001; `prod.envio_dian` [L-W] lines 976-993; `prod.resolucion_facturacion` [V] lines 315-332 of ER diagram; `prod.facturas` [L-E] from F1.9), and the existing `assign_consecutivo` Python helper (verified, F1.9 reuse per DEC-FE-05).

Today the URL `POST /api/v1/facturacion/factura-electronica` is **not registered** in the FastAPI router. The pre-existing ORM `models/L_E/factura_electronica.py::FacturaElectronica(LifecycleEventBase)` (composite PK `(uuid, fecha_retencion_hasta)`, NOT partitioned) maps to `prod.factura_electronica`, and the pre-existing `[L-W]`-class ORM `models/L_W/envio_dian.py::EnvioDian(WorkflowBase)` with self-FK `uuid_envio_padre` + `cufe` + `estado` (masc forms per ER línea 904) + `payload` JSONB + `timestamp_evento` + re-declared `vigente_desde`/`vigente_hasta` versioning columns is reusable. The helper `repo/resolucion_facturacion.py::assign_consecutivo` already exists with the verified signature (verified pre-apply per observation #1568 §5 + §10; idempotency lines 99-108; SELECT FOR UPDATE lines 114-120; `ConsecutivoRangeExhaustedError` lines 143-147). The view `prod.v_factura_electronica_acuse` (migration 0009 lines 96-109, `DISTINCT ON (uuid_factura_electronica) ORDER BY timestamp_evento DESC NULLS LAST, uuid DESC`) is the canonical read path for `estado`/`cufe`/`timestamp_evento` and is NOT re-created by F1.10. The alerta `fe_numbering_exhausted` is already seeded (per plan.md línea 949 + `repo/alert_types.py::AlertaFactory` F1.8 T-PR8-002). The sync catalog entry for `envio_dian` (per `sync/catalog/entries/sync_entries_lw.py` lines 112-136) currently has `direction='cloud_to_branch'` (D1-rev/D5-rev); F1.10 flips it to `branch_to_cloud` in MIGRATION 0028 Op 1 (DEC-FE-01). The branch operator's cash register at the parking branch cannot emit electronic facturas today: `prod.factura_electronica` has zero rows because no handler creates them, the cashier's terminal duplicates the fiscal numbering logic client-side or — worse — emits hand-typed consecutive numbers that bypass `assign_consecutivo` (introducing gaps in the DIAN numbering sequence and exposing the operator to regulatory rejection), and `prod.envio_dian` state machine has no transition rows because no client posts to `/reintentar`.

**The backend performs zero business validation on FE numbering + DIAN state**, creating five concrete risks that HU-F1.10 resolves:

1. **Branch cannot emit electronic facturas.** Today `prod.factura_electronica` exists in migration 0001 (lines 875-891) but no handler creates rows. Without server-side enforcement of `assign_consecutivo` (real numeración per plan.md línea 953, NOT fallback `SIM-YYYY-MM-DD-NNNNNN` per línea 951 explicitly forbidden), the cashier's terminal duplicates the fiscal numbering logic client-side, opening gaps in the DIAN numbering sequence and regulatory exposure on audit. DIAN Resolución 000175 de 2021 + Decreto 2242 de 2015 require contiguous numbering inside the authorized `rango_desde`..`rango_hasta` range. CU-04 (Facturación) is functionally closed in `plan.md §4` only when `POST /api/v1/facturacion/factura-electronica` returns `201` with `FacturaElectronicaRead` carrying server-derived `prefijo`+`consecutivo` from `assign_consecutivo` + server-derived `estado` from `prod.v_factura_electronica_acuse`.
2. **DIAN retry chain has no transition rows.** Without `/reintentar`, the cashier has no way to retry a `rechazado` submission without manually intervening in the cloud dispatcher. The retry chain (`prod.envio_dian` rows with self-FK `uuid_envio_padre`) is the audit trail of every transition; losing it loses the regulatory compliance evidence for DIAN audits. F1.10 introduces `/reintentar` as the ONLY legal way to advance the state machine (NEVER UPDATE on `envio_dian.estado`).
3. **R1 HIGH architectural conflict (RESOLVED in DEC-FE-01).** Three sources disagree about which node writes `prod.envio_dian`: `plan.md` línea 953 says branch INSERTs; `modelo_datos_er.mmd` línea 892 says "CLOUD-ONLY: único punto de salida hacia el proveedor de factura electrónica DIAN"; sync catalog says `direction='cloud_to_branch'`. This is a real architectural fork identified by sdd-explore observation #1568 §15 R1 HIGH. Resolution per plan.md (canonical authority per user mandate "siempre remitete al plan.md"): branch INSERTs the initial `envio_dian` row + every retry row; sync catalog flipped in MIGRATION 0028 Op 1; ER diagram comment updated post-archive from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync". Documented in detail in §3 below.
4. **Range exhaustion has no alerting path.** Today `assign_consecutivo` raises `ConsecutivoRangeExhaustedError` (helper lines 143-147) but no caller maps it to an operator-visible alerta. F1.10 catches the exception, fires the already-seeded `fe_numbering_exhausted` alerta via `AlertaFactory`, and returns 409 `numeracion_agotada` with `uuid_resolucion_facturacion` + `rango_hasta` + `prefijo` for operator triage.
5. **GET endpoint exposes fabricated `reportado_dian` boolean.** Without the JOIN to `prod.v_factura_electronica_acuse`, callers would have to guess at the `aceptado`/`rechazado` state from `envio_dian` directly (race-prone, leak-prone). F1.10 enforces the JOIN as the only read path; `cufe` and `estado` are SERVER-DERIVED from the view, never fabricated (plan.md línea 947 FORBIDDEN `reportado_dian` boolean).

F1.10 closes the DIAN regulatory half of CU-04. The work is **3 handlers + repo module + schemas + new helper + MIGRATION 0028** — the migration is mandatory because (a) the sync catalog flip is DML, not DDL, so it needs versioned tracking; (b) the partial UK `one_fe_per_factura` closes the V2 SELECT-before-INSERT TOCTOU race window (parallel to F1.7 `one_exit_per_ingreso` migration 0026 Op 4 and F1.9 `one_factura_per_salida` migration 0027 Op 2); (c) the covering index speeds up the `GET` JOIN to `prod.v_factura_electronica_acuse` for high-retry FEs.

The contract is captured in **REQ-OPS-064..074** (added by `sdd-spec` to `specs/operations/spec.md`):

- **REQ-OPS-064** — Server-assigns `prefijo`+`consecutivo` via `assign_consecutivo` SELECT FOR UPDATE.
- **REQ-OPS-065** — Initial `prod.envio_dian` row inserted in same `await session.commit()` as `prod.factura_electronica` (KD-FE-01).
- **REQ-OPS-066** — Range exhaustion → HTTP 409 `numeracion_agotada` + alerta `fe_numbering_exhausted` fired in same TX (DEC-FE-03).
- **REQ-OPS-067** — At most one `prod.factura_electronica` row per `prod.facturas.uuid` (V2 + DB partial UK `one_fe_per_factura`).
- **REQ-OPS-068** — `GET` endpoint JOINs `prod.v_factura_electronica_acuse` view (NEVER direct SELECT on `prod.envio_dian`).
- **REQ-OPS-069** — `GET` response `envio_actual` exposes `estado` (Literal) + `cufe` (nullable) + `timestamp_evento`; server NEVER fabricates `reportado_dian` boolean.
- **REQ-OPS-070** — Retry INSERTs NEW `prod.envio_dian` row with `uuid_envio_padre` pointing at previous chain tip (NEVER UPDATE — DEC-FE-02).
- **REQ-OPS-071** — Retry NOT allowed on chain tip `estado='aceptado'` (409 `reintento_no_permitido`); NOT allowed on `pendiente` (409 `envio_dian_already_pending`) (DEC-FE-04).
- **REQ-OPS-072** — `prod.envio_dian` writes are branch-initiated; sync catalog direction flipped to `branch_to_cloud` in MIGRATION 0028 Op 1 (DEC-FE-01).
- **REQ-OPS-073** — Vigente resolution lookup at `NOW()` with defensive `ORDER BY vigente_desde DESC LIMIT 1` (V3).
- **REQ-OPS-074** — Prefijo snapshot on `prod.factura_electronica.prefijo` at INSERT time (denormalized from vigente resolution; 4NF snapshot pattern).

F1.10 is consumed by **F1.13** (Arqueo + cierre_dia; consumes `prod.envio_dian` for `cierre_dia` aggregation; may need to add `envio_dian.estado = 'aceptado'` filter to count successful FEs per sucursal per day), **F1.14** (sync estado; exposes `envio_dian` counts per sucursal for the operator dashboard; now possible after DEC-FE-01 sync catalog flip — the chain is branch-side; cloud can aggregate), **HU-F8.1** (Facturación consumidor final / FE consumer UI; consumes `FacturaElectronicaRead` from F1.10 to display DIAN status in the operator terminal; unblocked after F1.10 archive). F1.10 leaves a clean separation between the lifecycle event (`prod.factura_electronica`, bi-temporal `[L-E]`), the workflow chain (`prod.envio_dian`, insert-only per transition `[L-W]`), and the vigente resolution (`prod.resolucion_facturacion`, bi-temporal `[V]`).

---

## 3. Architectural Conflict Resolution — DEC-FE-01 (R1 HIGH RESOLVED)

This section is **mandatory** for the design. It documents R1 from the sdd-explore phase (observation #1568 §15 R1 HIGH) and records the resolution per `HU-F1.10-proposal.md §3`.

### 3.1 The conflict (R1 HIGH)

Three sources disagree about which node writes `prod.envio_dian`:

| Source | Statement | Authority weight |
|---|---|---|
| `plan.md` línea 953 | "`envio_dian` (INSERT por transición, nunca UPDATE)" from the BRANCH | **CANONICAL** (per user mandate "siempre remitete al plan.md") |
| `modelo_datos_er.mmd` línea 892 | "CLOUD-ONLY: único punto de salida hacia el proveedor de factura electrónica DIAN" | Aspirational design from PR2 — F1.10 supersedes |
| `sync/catalog/entries/sync_entries_lw.py` lines 112-136 | `direction = "cloud_to_branch"` | Catalog entry to be updated in MIGRATION 0028 Op 1 |

The cloud-only assumption was a PR2 aspirational design. With `assign_consecutivo` now in place at the branch (verified pre-apply per observation #1568 §5 + §10) and the cloud dispatcher architecture decided out-of-band (mocked for MVP per observation #1568 §7), the natural design is: **branch numbers + tracks locally, cloud forwards asynchronously**. The retry endpoint needs UUID v4 generation at the branch (offline-safe, no DIAN round-trip latency for the INSERT itself). The cloud consumes the chain via sync replication in `branch_to_cloud` direction for analytics + state-machine advancement (`pendiente → enviado → aceptado | rechazado`).

### 3.2 The resolution

**Resolution path** (mandated by plan.md + F1.10 retry semantics + observation #1568 §15 R1):

1. **Branch INSERTs** the initial `prod.envio_dian` row (`estado='pendiente'`, `uuid_envio_padre=NULL`) atomically with `prod.factura_electronica` in the same `await session.commit()` (KD-FE-01 single-commit invariant, mirror of F1.9 KD-FACT-01 per proposal §3.2 step 1).
2. **Branch INSERTs** every subsequent retry row with `uuid_envio_padre` pointing at the previous chain tip. **NEVER UPDATE.** This is the audit trail and the only way to recover the chain ordering under cloud dispatcher outages (proposal §3.2 step 2).
3. **Cloud dispatcher** (out of F1.10 scope; Fase 4 owns the real integration) reads the branch's `envio_dian` chain via sync replication in `branch_to_cloud` direction, POSTs to the DIAN provider, and writes back transition rows (`enviado → aceptado|rechazo`) via the same sync channel (proposal §3.2 step 3). Bidirectional sync on the same row, mediated by the version row's bi-temporal versioning.
4. **Branch reads** the latest chain tip via `prod.v_factura_electronica_acuse` (migration 0009, already present per lines 96-109 with `DISTINCT ON (uuid_factura_electronica) ORDER BY timestamp_evento DESC NULLS LAST, uuid DESC`).

### 3.3 What changes in the codebase (MIGRATION 0028 Op 1)

```sql
-- DEC-FE-01: flip envio_dian sync direction from cloud_to_branch to branch_to_cloud
-- Pre-flight: verify 4 tables + sync_catalog exist
DO $$
BEGIN
    ASSERT (
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='prod' AND table_name IN
        ('factura_electronica', 'envio_dian', 'resolucion_facturacion', 'facturas')
    ) = 4,
        'F1.10 requires 4 tables to exist';

    UPDATE sync_catalog
    SET direction = 'branch_to_cloud'
    WHERE table_name = 'envio_dian' AND direction = 'cloud_to_branch';
END $$;
```

This is the **first op** of MIGRATION 0028 (pre-flight + flip, before the partial unique index in Op 2). Downgrade reverses: `UPDATE sync_catalog SET direction = 'cloud_to_branch' WHERE table_name = 'envio_dian'`.

### 3.4 What changes in the ER diagram (post-archive)

`modelo_datos_er.mmd` línea 892 comment is updated from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync replication". The `[L-W]` tag stays (insert-only per transition). The change is committed in a separate commit after the F1.10 archive (the archive PR does NOT touch `modelo_datos_er.mmd`; the diagram update is its own PR for traceability — same pattern as F1.9 docstring drift fix on `models/A/factura_pagos.py` lines 9-18).

### 3.5 Why this matters

- **Retry semantics require branch-side chain**: UUID v4 generation at the branch is offline-safe (per the offline-first architecture documented in `AGENTS.md`). A cloud-only design forces a synchronous round-trip on every retry, which is incompatible with the existing offline-first architecture.
- **Chain integrity via `uuid_envio_padre` FK**: each transition = NEW row. UPDATE would break the audit trail and the `vigente_desde`/`vigente_hasta` versioning semantics (the `[L-W]` WorkflowBase mandate UPDATE on `vigente_hasta` for bi-temporal versioning, but the user-meaningful fields like `estado` MUST be insert-only — REQ-OPS-070 + DEC-FE-02 + DEC-FE-07).
- **Cloud consumes via sync for analytics**: cloud aggregates the chain for DIAN reporting, audit trails, and the eventual webhook callbacks. F1.14 (sync estado) now becomes possible after the catalog flip.
- **Idempotency-Key header (DEC-IDEM-01 reuse from F1.6 + F1.9)**: client-side retries with the same `Idempotency-Key` return the cached response; the chain does NOT grow from client-side retries.

---

## 4. Architecture Overview

```
HTTPS POST /api/v1/facturacion/factura-electronica
        Body: FacturaElectronicaCreate
        │      {uuid_factura: UUID}
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        │  Idempotency-Key: <uuid>  (DEC-IDEM-01 reuse from F1.6 + F1.9)
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/facturacion.py  (MODIFY, +60 LOC, 3 NEW handlers on existing router) │
│                                                                              │
│ @router.post("/factura-electronica", response_model=FacturaElectronicaRead,  │
│              status_code=201)                                                │
│ async def create_factura_electronica(response, payload, session, ctx,        │
│                                       _claims) -> FacturaElectronicaRead    │
│                                                                              │
│  1. KD-3 issuer claims:                                                      │
│      _claims = requires_issuer("operador-", "admin-")                       │
│      ctx = get_tenant_ctx from JWT                                            │
│                                                                              │
│  2. V1 prod.facturas.uuid existe:                                            │
│      factura = await repo_factura_electronica.buscar_factura_por_uuid(       │
│          session, uuid_factura=payload.uuid_factura)                          │
│      if factura is None:                                                      │
│          raise 404 {"error":"factura_no_encontrada", "uuid_factura":...}    │
│                                                                              │
│  3. Tenant scope post-V1 (KD-S2 analog from F1.7):                           │
│      target_sucursal = factura.uuid_sucursal                                  │
│      if ctx.issuer_prefix == "operador-" and target != ctx.sucursal_uuid:   │
│          raise 403 {"error":"tenant_scope_violation"}                       │
│                                                                              │
│  4. V2 NO existing prod.factura_electronica row for uuid_factura:             │
│      existing_fe = await repo_factura_electronica.buscar_factura_electronica_por_factura(│
│          session, uuid_factura=payload.uuid_factura)                          │
│      if existing_fe is not None:                                              │
│          raise 409 {"error":"factura_electronica_ya_existe", ...}           │
│                                                                              │
│  5. V3 vigente prod.resolucion_facturacion row for the sucursal:              │
│      resolucion = await repo_resolucion.buscar_resolucion_vigente_por_sucursal(│
│          session, uuid_sucursal=target_sucursal)                             │
│      if resolucion is None:                                                   │
│          raise 409 {"error":"resolucion_no_vigente", "uuid_sucursal":...}      │
│                                                                              │
│  6. KD-FE-01 — assign_consecutivo (SELECT FOR UPDATE on resolucion row):     │
│      try:                                                                     │
│          consecutivo = await assign_consecutivo(                             │
│              session, resolucion_uuid=resolucion.uuid,                       │
│              source_event_uuid=payload.uuid_factura)                         │
│      except ConsecutivoRangeExhaustedError as exc:                            │
│          await AlertaFactory(session, ctx).fire(                             │
│              "fe_numbering_exhausted", motivo=str(exc))                       │
│          raise 409 {"error":"numeracion_agotada",                            │
│              "uuid_resolucion_facturacion":...,                              │
│              "rango_hasta": resolucion.rango_hasta,                            │
│              "prefijo": resolucion.prefijo}                                   │
│                                                                              │
│  7. INSERT prod.factura_electronica [L-E] (snapshot prefijo):                │
│      new_fe = await repo_factura_electronica.crear_factura_electronica_inicial(│
│          session, actor_uuid=ctx.actor_uuid,                                  │
│          uuid_factura=payload.uuid_factura,                                   │
│          uuid_resolucion_facturacion=resolucion.uuid,                          │
│          prefijo=resolucion.prefijo,                                            │
│          consecutivo=consecutivo)                                              │
│                                                                              │
│  8. INSERT initial prod.envio_dian row (estado='pendiente',                   │
│                                       uuid_envio_padre=NULL):                │
│      new_envio = await repo_factura_electronica.crear_envio_dian_inicial(   │
│          session, actor_uuid=ctx.actor_uuid,                                  │
│          uuid_factura_electronica=new_fe.uuid,                                │
│          uuid_resolucion_facturacion=resolucion.uuid,                          │
│          payload={"prefijo": resolucion.prefijo,                              │
│                   "consecutivo": consecutivo,                                  │
│                   "uuid_factura": str(payload.uuid_factura)})                 │
│                                                                              │
│  9. Mock DIAN POST (real integration deferred Fase 4):                       │
│      # Cloud dispatcher reads via sync (branch_to_cloud direction per        │
│      # MIGRATION 0028 Op 1) and writes transition rows asynchronously.      │
│                                                                              │
│ 10. KD-FE-01 single commit:                                                  │
│      await session.commit()    ◄── UN solo commit (FE row + envio row)     │
│                                                                              │
│ 11. DEC-FE-06 (NEW): Response shape + Cache-Control: no-store header:        │
│      apply_no_store_header(response)                                          │
│      return FacturaElectronicaRead(                                          │
│          uuid=new_fe.uuid, prefijo=new_fe.prefijo,                            │
│          consecutivo=new_fe.consecutivo,                                       │
│          uuid_factura=new_fe.uuid_factura,                                    │
│          uuid_resolucion_facturacion=new_fe.uuid_resolucion_facturacion,     │
│          created_at=new_fe.created_at,                                        │
│          envio_actual=EnvioDianRead(                                          │
│              uuid=new_envio.uuid,                                              │
│              uuid_factura_electronica=new_fe.uuid,                            │
│              estado="pendiente",                                              │
│              timestamp_evento=new_envio.timestamp_evento,                      │
│              uuid_envio_padre=None,                                            │
│              cufe=None, motivo_rechazo=None))                                 │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                                       ▲
        │ AST walk single-commit (KD-FE-01)      │ AST walk no-update (DEC-FE-07, REQ-OPS-070)
        │ for create handler                     │ for retry handler
tests/static/test_fe_handler_single_commit.py
tests/static/test_fe_retry_handler_no_update_on_envio_dian.py
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Repo helpers (NEW):                                                          │
│   repo/factura_electronica.py   (~250 LOC) — 9 helpers + 8 typed exceptions │
│   repo/resolucion_facturacion.py (~40 LOC) — buscar_resolucion_vigente_por_sucursal│
│                                                                              │
│ Repo helpers (REUSED verbatim, NO modify):                                   │
│   repo/resolucion_facturacion.py::assign_consecutivo (F1.9) — verified       │
│   repo/workflow.py::read_chain_tip (F1.5 PR5-016)                            │
│   repo/alert_types.py::AlertaFactory (F1.8 T-PR8-002)                       │
│   repo/versioned.py::buscar_vigente_por_uuid (F1.5 PR5-016)                  │
│                                                                              │
│ Schemas (MODIFY):                                                            │
│   schemas/facturacion.py     (+80 LOC) — FacturaElectronicaCreate,            │
│                                       FacturaElectronicaRead,                 │
│                                       EnvioDianRead, EnvioDianRetryRead,     │
│                                       8 typed error schemas                  │
│                                                                              │
│ Tablas operacionales (READ + INSERT):                                       │
│   prod.facturas                  [L-E]  — V1 SELECT (F1.9)                  │
│   prod.resolucion_facturacion    [V]    — V3 SELECT vigente (REQ-OPS-073)   │
│   prod.factura_electronica       [L-E]  — Step 7 INSERT (DEC-FE-01)         │
│   prod.envio_dian                [L-W]  — Step 8 INSERT initial             │
│                                          + /reintentar Step 5 INSERT retry   │
│                                                                              │
│ Vistas derivadas (READ ONLY, ya existentes):                                │
│   prod.v_factura_electronica_acuse (migration 0009 lines 96-109)             │
│      DISTINCT ON (uuid_factura_electronica)                                  │
│      ORDER BY timestamp_evento DESC NULLS LAST, uuid DESC                    │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲
        │
        ▼ MIGRATION 0028 (4 operations, applied BEFORE F1.10 tests)
┌──────────────────────────────────────────────────────────────────────────────┐
│ migrations/versions/0028_one_fe_per_factura_and_chain_index_and_sync_flip.py│
│                                                                              │
│ Op 1 — Pre-flight DO $$ + DEC-FE-01 sync catalog flip:                      │
│   verify 4 tables exist (factura_electronica, envio_dian,                     │
│                          resolucion_facturacion, facturas)                   │
│   ASSERT (SELECT COUNT(*) FROM information_schema.tables WHERE                │
│         table_schema='prod' AND table_name IN (...)) = 4                    │
│   UPDATE sync_catalog SET direction='branch_to_cloud'                        │
│       WHERE table_name='envio_dian' AND direction='cloud_to_branch'           │
│                                                                              │
│ Op 2 — Partial unique index one_fe_per_factura (REQ-OPS-067):               │
│   CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura          │
│       ON prod.factura_electronica (uuid_factura)                              │
│       WHERE uuid_factura IS NOT NULL                                          │
│   FEASIBLE: prod.factura_electronica is [L-E] (NOT partitioned per          │
│   models/L_E/factura_electronica.py). Defense in depth.                      │
│                                                                              │
│ Op 3 — Covering index idx_envio_dian_chain_tip (REQ-OPS-068):                │
│   CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_envio_dian_chain_tip           │
│       ON prod.envio_dian (uuid_factura_electronica, timestamp_evento DESC)    │
│       WHERE uuid_factura_electronica IS NOT NULL                             │
│   Speeds up the GET endpoint JOIN to prod.v_factura_electronica_acuse.       │
│                                                                              │
│ Op 4 — Defensive GRANT re-assertion:                                        │
│   GRANT SELECT, INSERT, UPDATE ON prod.factura_electronica TO rol_app;     │
│   GRANT SELECT, INSERT, UPDATE ON prod.envio_dian TO rol_app;               │
│   GRANT SELECT, INSERT, UPDATE ON prod.resolucion_facturacion TO rol_app;   │
│                                                                              │
│ Downgrade (reverse order, superuser context for DROP INDEX CONCURRENTLY):   │
│   REVOKE SELECT, INSERT, UPDATE ON prod.factura_electronica FROM rol_app;   │
│   REVOKE SELECT, INSERT, UPDATE ON prod.envio_dian FROM rol_app;             │
│   REVOKE SELECT, INSERT, UPDATE ON prod.resolucion_facturacion FROM rol_app; │
│   DROP INDEX CONCURRENTLY IF EXISTS prod.idx_envio_dian_chain_tip;          │
│   DROP INDEX CONCURRENTLY IF EXISTS prod.one_fe_per_factura;                 │
│   UPDATE sync_catalog SET direction='cloud_to_branch'                         │
│       WHERE table_name='envio_dian' AND direction='branch_to_cloud';          │
└──────────────────────────────────────────────────────────────────────────────┘
```

The handler is thin + orquestador. All validation logic lives in `repo/*.py`. The single `commit()` materializes the FE row + initial envio row atomically (KD-FE-01) and releases the `SELECT FOR UPDATE` lock acquired by `assign_consecutivo` (KD-FE-02 reuse from F1.9).

### GET handler architecture

```
HTTPS GET /api/v1/facturacion/factura-electronica/{uuid}
        │
        │  requires_issuer("operador-", "admin-")
        │  Cache-Control: no-store
        ▼
async def get_factura_electronica(response, uuid, session, ctx, _claims)
                                                                  │
   1. KD-3 issuer chain ────────────────────────────  DI-resolved │
                                                                  ▼
   2. V1: fe = await repo_factura_electronica.buscar_factura_electronica_por_uuid(
              session, uuid=uuid_factura_electronica)
        if fe is None:
            raise 404 {"error":"factura_electronica_no_encontrada"}
        Tenant scope post-V1 (operador- with fe.uuid_sucursal != ctx.sucursal_uuid)
        → 403 tenant_scope_violation

   3. JOIN prod.v_factura_electronica_acuse (migration 0009, already present):
        ack = await session.execute(text(
            "SELECT estado, cufe, timestamp_evento, uuid "
            "FROM prod.v_factura_electronica_acuse "
            "WHERE uuid_factura_electronica = :uuid"
        ), {"uuid": str(uuid_factura_electronica)}).first()

   4. Response: FacturaElectronicaRead{
        uuid, prefijo, consecutivo, uuid_factura, uuid_resolucion_facturacion,
        created_at,
        envio_actual: EnvioDianRead{
            uuid=ack.uuid OR fallback,
            uuid_factura_electronica=fe.uuid,
            estado=ack.estado if ack else "pendiente",
            timestamp_evento=ack.timestamp_evento if ack else None,
            uuid_envio_padre=None,  # GET response does NOT expose chain
            cufe=ack.cufe if ack else None,
            motivo_rechazo=None,
        }
    }
    apply_no_store_header(response)
```

### Retry handler architecture

```
HTTPS POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar
        Body: (empty)
        │
        │  requires_issuer("operador-", "admin-")
        │  Cache-Control: no-store
        │  Idempotency-Key: <uuid>  (DEC-IDEM-01)
        ▼
async def retry_factura_electronica(response, uuid, session, ctx, _claims)
                                                                            │
   1. KD-3 issuer chain ──────────────────────────  DI-resolved             │
                                                                            ▼
   2. V1: fe = await repo_factura_electronica.buscar_factura_electronica_por_uuid(
              session, uuid=uuid_factura_electronica)
        if fe is None:
            raise 404 {"error":"factura_electronica_no_encontrada"}
        Tenant scope post-V1 → 403 if cross-branch

   3. V2 — chain tip lookup (VigenteWorkflowBase):
        tip_envio = await repo_factura_electronica.buscar_envio_dian_chain_tip(
            session, uuid_factura_electronica=uuid_factura_electronica)
        if tip_envio is None:
            raise 409 {"error":"reintento_no_permitido", estado_actual: None}

   4. V3 — chain tip state check (DEC-FE-04):
        if tip_envio.estado == "aceptado":
            raise 409 {"error":"reintento_no_permitido", estado_actual: "aceptado"}
        if tip_envio.estado == "pendiente":
            raise 409 {"error":"envio_dian_already_pending",
                       uuid_envio_pendiente: tip_envio.uuid}

   5. V4 — INSERT NEW prod.envio_dian row (DEC-FE-02 + DEC-FE-07, NEVER UPDATE):
        new_envio = await repo_factura_electronica.crear_envio_dian_reintento(
            session, actor_uuid=ctx.actor_uuid,
            uuid_factura_electronica=uuid_factura_electronica,
            uuid_resolucion_facturacion=fe.uuid_resolucion_facturacion,
            payload={"prefijo": fe.prefijo, "consecutivo": fe.consecutivo,
                     "uuid_factura": str(fe.uuid_factura)},
            uuid_envio_padre=tip_envio.uuid)  # previous tip

   6. Mock DIAN POST (real deferred Fase 4):
        # Cloud dispatcher reads via sync and writes transition rows asynchronously

   7. KD-FE-01 single commit:
        await session.commit()

   8. DEC-FE-06: Response shape + Cache-Control: no-store header:
        apply_no_store_header(response)
        return EnvioDianRetryRead(
            uuid=new_envio.uuid,
            uuid_factura_electronica=uuid_factura_electronica,
            estado="pendiente",
            timestamp_evento=new_envio.timestamp_evento,
            uuid_envio_padre=tip_envio.uuid,  # previous tip
        )
```

---

## 5. Data Model

**One Alembic migration introduces** the partial unique index + the covering index + the sync catalog flip + the GRANT re-assertion. **No columns added or removed** in any operational table. The 3 tables (`prod.factura_electronica`, `prod.envio_dian`, `prod.resolucion_facturacion`) all exist since migration 0001 with their pre-existing schemas.

### 5.1 `prod.resolucion_facturacion` `[V]` (bi-temporal VersionedBase)

| Property | Value |
|---|---|
| **ER línea** | 315-332 |
| **Migration 0001 línea** | ~315-332 |
| **Operations** | V3 SELECT vigente row for `uuid_sucursal`; KD-FE-01 SELECT FOR UPDATE inside `assign_consecutivo` (REUSED as-is, no modification per DEC-FE-05) |
| **Columns read** | `uuid`, `prefijo`, `rango_desde`, `rango_hasta`, `vigente_desde`, `vigente_hasta`, `vigente_inicial`, `estado` |
| **Index** | existing bi-temporal `(vigente_desde, vigente_hasta)` (migration 0001 line 332) |
| **Defense in depth at DB layer** | SELECT FOR UPDATE locks the version row during `assign_consecutivo`; concurrent calls on the SAME resolution serialize cleanly (per `assign_consecutivo` source lines 114-120) |
| **No new indexes** | None needed; existing bi-temporal index suffices |

### 5.2 `prod.factura_electronica` `[L-E]` (insert-only, composite PK `(uuid, fecha_retencion_hasta)`)

| Property | Value |
|---|---|
| **ER línea** | 689-705 |
| **Migration 0001 línea** | 875-891 |
| **Operations** | V2 SELECT-by-`uuid_factura` (existing-FE guard); V4 INSERT in same TX as `envio_dian` (KD-FE-01 single-commit) |
| **Columns read** | `uuid`, `uuid_sucursal`, `uuid_factura`, `uuid_resolucion_facturacion`, `prefijo`, `consecutivo`, `descuento`, `vigente_desde`, `vigente_hasta`, `created_at`, `created_by` |
| **Columns write (INSERT)** | `uuid_sucursal`, `uuid_factura`, `uuid_resolucion_facturacion`, `prefijo` (snapshot from `resolucion.prefijo` per REQ-OPS-074), `consecutivo` (from `assign_consecutivo`), `descuento=Decimal(0)`, `fecha_retencion_hasta = date.today() + timedelta(days=5*365)` (DIAN 5-year retention) |
| **Indexes** | existing UK `(uuid_resolucion_facturacion, consecutivo)` per migration 0001 line 889 (DIAN numbering uniqueness, primary defense) + NEW partial unique `one_fe_per_factura (uuid_factura) WHERE uuid_factura IS NOT NULL` per MIGRATION 0028 Op 2 (defense in depth — natural business constraint: 1 FE per internal factura) |
| **Audit/sync triggers** | `factura_electronica_audit_columns` (BEFORE INSERT, sets `created_at`, `created_by`), `factura_electronica_set_vigente_inicial` (BEFORE INSERT, sets `vigente_inicial`), `factura_electronica_enqueue_sync` (AFTER INSERT, calls `prod.fn_enqueue_sync()`) — all per migration 0001 lines 2646-2712 + 2864-2900. **NO new triggers.** |
| **Sync catalog** | `direction='branch_to_cloud'` (pre-existing per `sync/catalog/entries/sync_entries_le.py`, NOT changed by F1.10) |
| **REVOKE** | Already enforced by F1.9 MIGRATION 0027 Op 4 (REVOKE UPDATE, DELETE on `prod.factura_electronica` FROM rol_app) — re-asserted by MIGRATION 0028 Op 4 defensive GRANT |

### 5.3 `prod.envio_dian` `[L-W]` (insert-only per transition, composite PK `(uuid, fecha_retencion_hasta)`)

| Property | Value |
|---|---|
| **ER línea** | 891-914 |
| **Migration 0001 línea** | 976-993 |
| **Operations** | V2/V4 SELECT chain tip (`repo/workflow.read_chain_tip`); INSERT initial row in same TX as `factura_electronica`; INSERT retry rows via `/reintentar` |
| **Columns read** | `uuid`, `uuid_factura_electronica`, `uuid_envio_padre`, `estado`, `cufe`, `timestamp_evento`, `vigente_desde`, `vigente_hasta`, `payload` |
| **Columns write (INSERT)** | `uuid_sucursal`, `uuid_factura_electronica`, `uuid_resolucion_facturacion`, `payload: {prefijo, consecutivo, uuid_factura}` (JSONB), `respuesta_proveedor=NULL`, `cufe=NULL`, `uuid_envio_padre=NULL` (initial) OR `< uuid_envio_padre>` (retry), `timestamp_evento=now()`, `estado='pendiente'`, `fecha_retencion_hasta = date.today() + timedelta(days=5*365)` |
| **Indexes** | existing UK02 `(uuid_factura_electronica, uuid_envio_padre)` per migration 0001 line 901 (chain integrity — multiple `envio_dian` rows per `uuid_factura_electronica` allowed because that's the retry chain) + NEW covering `idx_envio_dian_chain_tip (uuid_factura_electronica, timestamp_evento DESC)` per MIGRATION 0028 Op 3 for the JOIN to `v_factura_electronica_acuse` |
| **Sync direction** | FLIPPED via MIGRATION 0028 Op 1 from `cloud_to_branch` to `branch_to_cloud` (DEC-FE-01, §3) |
| **REVOKE** | Already enforced by F1.9 MIGRATION 0027 Op 4 (REVOKE UPDATE, DELETE on `prod.envio_dian` FROM rol_app) — re-asserted by MIGRATION 0028 Op 4 defensive GRANT |

### 5.4 View `prod.v_factura_electronica_acuse` (READ ONLY, already exists)

```sql
-- migration 0009 lines 96-109 (verified, already present)
CREATE OR REPLACE VIEW prod.v_factura_electronica_acuse AS
SELECT DISTINCT ON (ed.uuid_factura_electronica)
    ed.uuid_factura_electronica,
    ed.cufe,
    ed.estado,
    ed.timestamp_evento
FROM prod.envio_dian ed
WHERE ed.uuid_factura_electronica IS NOT NULL
ORDER BY
    ed.uuid_factura_electronica,
    ed.timestamp_evento DESC NULLS LAST,
    ed.uuid DESC
```

**F1.10 does NOT re-create this view.** The `GET` endpoint JOINs it directly via `session.execute(text(...))`. The covering index `idx_envio_dian_chain_tip` (MIGRATION 0028 Op 3) speeds up the `DISTINCT ON` scan.

### 5.5 Tables touched summary

| Tabla | Tipo | Operación | Línea ER / migration |
|---|---|---|---|
| `prod.facturas` | `[L-E]` | V1 SELECT (read-only) | (F1.9, migration 0027) |
| `prod.resolucion_facturacion` | `[V]` | V3 SELECT vigente + KD-FE-01 SELECT FOR UPDATE | ER 315-332 + ORM `models/V/resolucion_facturacion.py` |
| `prod.factura_electronica` | `[L-E]` | V2 SELECT + Step 7 INSERT | ER 689-705 + ORM `models/L_E/factura_electronica.py` + UK01 line 889 |
| `prod.factura_electronica` | `[L-E]` | (Op 2) partial unique index `one_fe_per_factura` | MIGRATION 0028 |
| `prod.factura_electronica` | `[L-E]` | (Op 4) defensive GRANT re-assertion | MIGRATION 0028 |
| `prod.envio_dian` | `[L-W]` | V2/V4 SELECT chain tip + Step 8 INSERT initial + /reintentar Step 5 INSERT retry | ER 891-914 + ORM `models/L_W/envio_dian.py` + UK02 line 901 |
| `prod.envio_dian` | `[L-W]` | (Op 3) covering index `idx_envio_dian_chain_tip` | MIGRATION 0028 |
| `prod.envio_dian` | `[L-W]` | (Op 1) sync catalog flip `cloud_to_branch` → `branch_to_cloud` | MIGRATION 0028 (DEC-FE-01) |
| `prod.envio_dian` | `[L-W]` | (Op 4) defensive GRANT re-assertion | MIGRATION 0028 |
| `sync_catalog` | (table) | (Op 1) `UPDATE sync_catalog SET direction='branch_to_cloud' WHERE table_name='envio_dian'` | MIGRATION 0028 |
| `prod.v_factura_electronica_acuse` | (view) | READ ONLY (JOIN in GET handler) | migration 0009 lines 96-109 |

**No column added for `prefijo`, `consecutivo`, `estado`, `cufe`, `reportado_dian`** — DEC-FE-01 veda `estado`/`cufe` (4NF, lives on `envio_dian`); DEC-FE-05 veda `prefijo`/`consecutivo` live update (4NF snapshot pattern per plan.md línea 697). `reportado_dian` boolean EXPLICITLY FORBIDDEN per plan.md línea 947.

**State transitions** on `prod.envio_dian.estado` happen via NEW rows with the same `uuid_factura_electronica` but a later `timestamp_evento` — the chain IS the audit trail (DEC-FE-02 + REQ-OPS-070). The view `v_factura_electronica_acuse` (migration 0009) materializes the current state for read-only acknowledgement projection.

**Sync catalog impact**: ONE change. MIGRATION 0028 Op 1 flips `envio_dian.direction` from `cloud_to_branch` to `branch_to_cloud` (DEC-FE-01). The cloud dispatcher now consumes the chain via sync replication in the flipped direction. F1.14 (sync estado) becomes possible after the flip — out of F1.10 scope but unblocked.

---

## 6. Decisions

This HU adopts **seven** Key Decisions (DEC-FE-01..05 from `proposal.md §6` + DEC-FE-06..07 NEW from `sdd-design` extension) plus **two KD invariants** (KD-FE-01 single-commit + KD-FE-02 `assign_consecutivo` SELECT FOR UPDATE reuse from F1.9). Each one passes the R5 risk threshold (no open question blocks the design; the proposal §11 confirms "Sin preguntas abiertas" after the DEC-FE-01 resolution of R1 HIGH). The decisions are grouped into 5 themes: ownership (DEC-FE-01, KD-FE-01, KD-FE-02), chain integrity (DEC-FE-02, DEC-FE-07 NEW), regulatory (DEC-FE-03, DEC-FE-04), reuse (DEC-FE-05), and response surface (DEC-FE-06 NEW).

### Decision DEC-FE-01 — `envio_dian` is branch-initiated; sync catalog flipped (RESOLVES R1 HIGH)

**Choice.** `prod.envio_dian` INSERTs happen at the BRANCH for initial state + every retry transition. The sync catalog direction is flipped from `cloud_to_branch` to `branch_to_cloud` in MIGRATION 0028 Op 1. The cloud dispatcher consumes the chain via sync replication for analytics + state-machine advancement (`pendiente → enviado → aceptado | rechazado`). The ER diagram comment is updated post-archive from "CLOUD-ONLY" to "BRANCH-INITIATED, cloud consumer via sync".

**Context.** Verified pre-apply per observation #1568 §15 R1 HIGH (architectural conflict identified). Three sources disagreed: plan.md línea 953 mandates branch INSERTs (CANONICAL per user mandate); ER línea 892 says "CLOUD-ONLY" (PR2 aspirational, F1.10 supersedes); sync catalog says `cloud_to_branch`. The cloud-only design is incompatible with retry semantics (UUID v4 generation must be offline-safe; UPDATE would break the audit trail). The `[L-W]` WorkflowBase mandate of INSERT-only per transition is preserved. The cloud dispatcher architecture was decided out-of-band in AGENTS.md; the F1.10 design reflects that architecture by having the branch own the chain and the cloud consume it.

**Alternatives considered.**
- *Option (a) cloud owns ALL `envio_dian` writes* — REJECTED. Forces a synchronous round-trip on every retry, incompatible with offline-first. Adds latency to the `/reintentar` endpoint. R1 risk class.
- *Option (b) branch creates a separate `factura_electronica_reintento` request marker + cloud owns `envio_dian`* — REJECTED. Adds a new table for no clear win; the chain semantics already capture the intent. R1 risk class.
- *Option (c) branch INSERTs initial `envio_dian` row + cloud owns subsequent transitions* — REJECTED. Requires bidirectional sync semantics that the current catalog entry does not support. R1 risk class.

**Rationale.** plan.md is the canonical authority (per user mandate "siempre remitete al plan.md" línea 953 mandates branch INSERTs). The cloud-only design is incompatible with retry semantics (UUID v4 generation must be offline-safe; UPDATE would break the audit trail). The `[L-W]` WorkflowBase mandate of INSERT-only per transition is preserved. The cloud dispatcher architecture was decided out-of-band in AGENTS.md; the F1.10 design reflects that architecture by having the branch own the chain and the cloud consume it.

### Decision DEC-FE-02 — Retry chain via NEW row + `uuid_envio_padre` (NEVER UPDATE on user-meaningful fields)

**Choice.** The retry chain is materialized as N `prod.envio_dian` rows, each with `uuid_envio_padre` pointing at the previous chain tip. **NEVER UPDATE** on `estado`, `cufe`, `uuid_envio_padre`, `motivo_rechazo`, or any user-meaningful field. The `[L-W]` WorkflowBase MAY UPDATE `vigente_hasta` for bi-temporal versioning (close current version, insert new version with `vigente_desde=now()`, `vigente_hasta=NULL`) — but only `vigente_hasta` is touched; the user-meaningful fields stay insert-only.

**Context.** plan.md línea 953 mandates "`envio_dian` (INSERT por transición, nunca UPDATE)". 4NF compliance (state lives on `envio_dian.estado`, not duplicated on `factura_electronica`). Audit trail completeness (every transition is a row, with `created_at`, `created_by`, `timestamp_evento`). Cloud-dispatcher-outage tolerance (the chain grows locally; cloud catches up via sync in the flipped direction). DIAN audit requires immutable transitions per Resolución 000175 de 2021.

**Alternatives considered.**
- *UPDATE in-place on `envio_dian`* — REJECTED. Breaks audit trail. R7 risk (regulatory exposure: DIAN audit requires immutable transitions).
- *Separate `envio_dian_history` table* — REJECTED. The chain IS the history; a separate table adds query complexity without benefit.

**Rationale.** 4NF + audit trail + cloud-dispatcher-outage tolerance all align on NEW-row-only semantics. AST walk `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` enforces the invariant (DEC-FE-07 NEW).

### Decision DEC-FE-03 — Range exhaustion → 409 `numeracion_agotada` + alerta `fe_numbering_exhausted`

**Choice.** When `assign_consecutivo` raises `ConsecutivoRangeExhaustedError` (verified, helper source lines 143-147), the handler catches it, fires the already-seeded alerta `fe_numbering_exhausted` via `repo/alert_types.py::AlertaFactory(session, ctx).fire(...)` in the SAME TX, and returns `409 {"error": "numeracion_agotada", "uuid_resolucion_facturacion": ..., "rango_hasta": ..., "prefijo": ...}`.

**Context.** plan.md línea 949 mandates the alerta; línea 951 explicitly forbids the `SIM-YYYY-MM-DD-NNNNNN` fallback. The alerta is already seeded (per the same line). The typed 409 body gives the operator enough context to act (request a new resolution from DIAN). `assign_consecutivo` is the canonical numbering helper (DEC-FE-05; verified F1.9 reuse).

**Alternatives considered.**
- *Fallback numbering `SIM-YYYY-MM-DD-NNNNNN`* — REJECTED. Plan.md línea 951 explicitly forbids this: "la condición que la activaría ya no existe porque `assign_consecutivo` (numeración real) está construido y en uso".
- *Fire alerta AFTER 409 response* — REJECTED. R5 (operator visibility gap if TX rolls back before alerta fires). Fire in same TX guarantees alerta row created atomically with the 409 response.

**Rationale.** plan.md línea 949 + línea 951 mandate this behavior. The alerta is already seeded. The typed error response gives the client enough context to act.

### Decision DEC-FE-04 — Retry NOT allowed on `aceptado` → 409 `reintento_no_permitido`; NOT allowed on `pendiente` → 409 `envio_dian_already_pending`

**Choice.** When the chain tip state is `aceptado`, the `/reintentar` endpoint returns `409 {"error": "reintento_no_permitido", "uuid_factura_electronica": ..., "estado_actual": "aceptado"}`. When the chain tip is `pendiente`, the endpoint returns `409 {"error": "envio_dian_already_pending", "uuid_factura_electronica": ..., "uuid_envio_pendiente": <tip.uuid>}` (rapid-retry guard). Only `rechazado` (or `enviado` for completeness, though cloud dispatcher should normally advance it) chain tips may be retried.

**Context.** plan.md línea 969 mandates the `aceptado` block. `aceptado` is the terminal success state — retrying would create a phantom chain that misleads DIAN audits. The 409 prevents accidental retry storms from operators. `pendiente` means the cloud dispatcher is still working — the client just needs to wait; the rapid-retry 409 prevents pollution of the chain.

**Alternatives considered.**
- *Allow retry on `aceptado` for "corrective" chain entries* — REJECTED. There's no corrective action at this layer; corrective actions are F1.13 anulaciones territory.
- *Allow retry on `pendiente` or `enviado`* — REJECTED. The cloud dispatcher is still working; the client just needs to wait. The `envio_dian_already_pending` 409 covers the rapid-retry case (V2 chain-tip guard).
- *Allow retry only on `rechazado`* — CONSIDERED. Plan.md línea 969 says "retry only on `rechazado`". The current DEC-FE-04 also allows `enviado` defensively (Scenario 4 of REQ-OPS-071), but the test suite enforces the `rechazado`-only path as the primary semantic. The `enviado` case is documented as "MAY" (per REQ-OPS-071 Scenario 4) and tested with explicit acknowledgement.

**Rationale.** plan.md línea 969. `aceptado` is terminal. `pendiente` means cloud dispatcher is working. `rechazado` (and defensively `enviado`) may be retried.

### Decision DEC-FE-05 — `assign_consecutivo` reused as-is (NO modification)

**Choice.** `assign_consecutivo` is reused verbatim from F1.9 / T-PR9-002 / D1-rev. F1.10 does NOT modify the helper, does NOT change its signature, does NOT add new exceptions.

**Context.** Verified pre-apply (observation #1568 §5 + §10): signature returns `int` (consecutivo only), uses `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion` (lines 114-120), idempotent per `(resolucion_uuid, source_event_uuid)` pair (lines 99-108), raises `ConsecutivoRangeExhaustedError` on range exhaustion (lines 143-147). Modifying the helper would risk breaking F1.9's contract.

**Alternatives considered.**
- *Wrap `assign_consecutivo` in a new helper that also snapshots the prefijo* — REJECTED. The prefijo is read directly from `resolucion_facturacion` row in step 6 of the handler (V4). No abstraction needed.

**Rationale.** Verified by reading the source. Modifying the helper would risk breaking F1.9's contract. The prefijo is read separately by the handler (snapshot pattern per REQ-OPS-074).

### Decision DEC-FE-06 (NEW) — Handler Step 12 response includes `Cache-Control: no-store` header per REQ-OPS-XR2

**Choice.** All responses from `POST /api/v1/facturacion/factura-electronica`, `GET /api/v1/facturacion/factura-electronica/{uuid}`, and `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` MUST carry `Cache-Control: no-store` header. This includes 2xx (201), 4xx (403, 404, 409), and 5xx (500) responses. The header is set via `apply_no_store_header(response)` after the FastAPI dependency injection (F1.3..F1.9 precedent).

**Context.** REQ-OPS-XR2 (mirror of F1.9 REQ-OPS-XR2). Defense in depth against cache poisoning of `cufe`, `estado`, `timestamp_evento` (all of which are server-derived from the latest envio chain tip). The `Cache-Control: no-store` directive prevents intermediate proxies + browser caches from serving stale FE state.

**Alternatives considered.**
- *Set no-store only on 201 responses* — REJECTED. Stale 4xx responses (e.g., 409 `numeracion_agotada`) could mislead operators into thinking the range is still exhausted when it has been extended.

**Rationale.** F1.3..F1.9 precedent + defense in depth. AST walks do NOT enforce this header (set imperatively via `apply_no_store_header(response)`); enforcement is at integration test level (`tests/integration/test_no_store_header_responses.py`).

### Decision DEC-FE-07 (NEW) — Handler emits NO UPDATE on `prod.envio_dian` user-meaningful fields per REQ-OPS-070

**Choice.** The retry handler `retry_factura_electronica` emits NO UPDATE statement on `prod.envio_dian` for any user-meaningful field (`estado`, `cufe`, `uuid_envio_padre`, `motivo_rechazo`). The `[L-W]` WorkflowBase MAY UPDATE `vigente_hasta` for bi-temporal versioning, but only `vigente_hasta` is touched. The retry is materialized as a NEW row with `uuid_envio_padre=<tip.uuid>`. AST walk `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` enforces the invariant by walking the handler's AST and asserting no `UPDATE` SQL or `update(EnvioDian)` SQLAlchemy core call appears in the body.

**Context.** REQ-OPS-070 Scenario 4 (AST walk enforcement) + DEC-FE-02 (NEW-row-only semantics). The chain IS the audit trail. UPDATE would break the audit trail and the `vigente_desde`/`vigente_hasta` versioning semantics (the `[L-W]` workflow base mandates UPDATE on `vigente_hasta` for legitimate state transitions, but the user-meaningful fields MUST be insert-only). DIAN audit requires immutable transitions per Resolución 000175 de 2021.

**Alternatives considered.**
- *Allow UPDATE on `vigente_hasta` only via explicit bi-temporal versioning path* — CONSIDERED. The WorkflowBase already supports this pattern (F1.4/F1.5 precedent); F1.10 does NOT introduce additional UPDATE statements because the retry row IS the new version.

**Rationale.** 4NF + audit trail + cloud-dispatcher-outage tolerance + REQ-OPS-070 + DEC-FE-02 all align on NEW-row-only semantics for user-meaningful fields. AST walk enforcement catches accidental UPDATE introduction in future commits.

### Decision DEC-FE-08 (KD-FE-01) — Single `await session.commit()` materializes FE row + initial envio row atomically

**Choice.** The `create_factura_electronica` handler body MUST contain EXACTLY ONE `await session.commit()` call (KD-FE-01 mirror of F1.9 KD-FACT-01 per REQ-OPS-060). The `retry_factura_electronica` handler body MUST also contain EXACTLY ONE `await session.commit()` call. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements MUST NOT appear anywhere in the handler body or its callees.

**Context.** KD-FACT-01 from F1.9 / REQ-OPS-060. An `envio_dian` chain without its parent FE is an audit orphan; an FE without its initial envio is a fiscal breach (DIAN requires the submission trail to exist from the moment of numbering). Single-commit atomicity closes both risks. The same single-commit invariant applies to the retry endpoint: a NEW envio row must be visible together with the commit boundary.

**Alternatives considered.**
- *Separate commits for FE row and envio row* — REJECTED. Loses atomicity. If FE commits but envio fails, the FE exists with no audit trail.
- *Use SAVEPOINT for nested commit* — REJECTED. Defeats the purpose of the single-commit invariant.

**Rationale.** KD-FACT-01 mirror. Atomicity is non-negotiable for DIAN compliance. AST walks `tests/static/test_fe_handler_single_commit.py` + `tests/static/test_fe_retry_handler_single_commit.py` enforce the invariant.

### Decision DEC-FE-09 (KD-FE-02) — `assign_consecutivo` SELECT FOR UPDATE on `prod.resolucion_facturacion` (REUSE F1.9, NO modification)

**Choice.** `assign_consecutivo` (already in place from F1.9) takes `SELECT ... FOR UPDATE` on `prod.resolucion_facturacion` row (verified, source lines 114-120). Lock held until `await session.commit()` (KD-FE-01). Concurrent calls on the SAME resolution serialize cleanly. NO modification in F1.10 (DEC-FE-05).

**Context.** KD-FE-02 mirror of F1.9 `assign_consecutivo` behavior. The SELECT FOR UPDATE closes the concurrent assignment race at the row level. Two concurrent TXs attempting to assign consecutivos from the same resolution row serialize: the FIRST acquires the lock and increments; the SECOND blocks at SELECT FOR UPDATE until the FIRST commits, then proceeds with `MAX(consecutivo)+1` over the now-committed state. NO gap is introduced.

**Alternatives considered.**
- *Lock per-table* — REJECTED. Serializes ALL FE numberings; latency catastrophe.
- *Lock per-resolution (current approach via SELECT FOR UPDATE)* — ACCEPTED. Matches F1.9 + F1.8 KD-1 (`FOR SHARE`) precedent.
- *Lock FOR UPDATE per prefijo across resolutions* — REJECTED. Same lock granularity is achieved via the per-resolution lock; cross-resolution locking would serialize unrelated resolutions.

**Rationale.** F1.9 precedent. Per-row `FOR UPDATE` lock is the canonical Postgres pattern for atomic counter increment under concurrency. Verified pre-apply (helper source lines 114-120).

---

## 7. Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| **R1** | **Architectural conflict on `envio_dian` ownership** — plan.md says branch INSERTs; ER says CLOUD-ONLY; sync catalog says `cloud_to_branch`. | **HIGH (RESOLVED)** | DEC-FE-01 (§6.1) + MIGRATION 0028 Op 1 sync catalog flip + ER diagram update post-archive. Documented in detail in §3 of this design. |
| **R2** | Vigente resolution lookup at handler entry — the SELECT must return the latest vigente row at `NOW()` for the sucursal. If `prod.resolucion_facturacion` has multiple version rows over time (bi-temporal VersionedBase), the V3 SELECT must defensively `ORDER BY vigente_desde DESC LIMIT 1`. | **MEDIUM** | New helper `repo/resolucion_facturacion.py::buscar_resolucion_vigente_por_sucursal(session, *, uuid_sucursal)` with explicit `ORDER BY vigente_desde DESC LIMIT 1 WHERE vigente_hasta IS NULL AND estado='activo'`. Unit test `test_buscar_resolucion_vigente_por_sucursal_returns_latest` covers single + multi-vigente corrupt cases (REQ-OPS-073 Scenario 2). |
| **R3** | Chain integrity via `uuid_envio_padre` FK — verify the FK constraint enforces referential integrity and that the chain can be reconstructed by recursive SELECT on `uuid_envio_padre`. | **MEDIUM** | Existing UK02 `(uuid_factura_electronica, uuid_envio_padre)` per migration 0001 line 901 provides chain integrity. Helper `repo/workflow.read_chain_tip` (F1.5 PR5-016) reconstructs the chain via `ORDER BY timestamp_evento DESC LIMIT 1`. Unit test `test_crear_envio_dian_reintento_sets_uuid_envio_padre` + `test_buscar_envio_dian_chain_tip_returns_latest` (REQ-OPS-070 Scenarios 1, 2, 3). |
| **R4** | DIAN web service integration — MVP mocks the response; real integration deferred to Fase 4. The `/reintentar` endpoint does NOT actually call DIAN; it only INSERTs a new `envio_dian` row. The cloud dispatcher (out of F1.10 scope) is what eventually talks to DIAN. | **LOW** | Documented as out-of-scope (§14). `500 dian_unavailable` reserved for Fase 4. The branch endpoint never returns `dian_unavailable` in MVP. |
| **R5** | Prefijo snapshot on `prod.factura_electronica` — the prefijo is denormalized from `prod.resolucion_facturacion` at INSERT time. The vigente row may later change (new resolution supersedes the old one), but old FE rows keep their original prefijo. | **LOW** | This is CORRECT per 4NF + plan.md línea 697. Documented in REQ-OPS-074 Scenarios 1, 2. The snapshot is the historical truth. No mitigation needed beyond documentation. |
| **R6** | Astro concurrency: `assign_consecutivo` returns `int` (consecutivo only). The handler MUST read `prefijo` separately from the vigente resolution row (already in V3 return) and snapshot it onto the new FE row at INSERT time. If the handler reads `prefijo` AFTER `assign_consecutivo` returns, there's a TOCTOU window where the resolution could be superseded. | **LOW** | The handler reads `prefijo` from the SAME `resolucion` ORM object returned by V3 (Step 5), BEFORE calling `assign_consecutivo` (Step 6). The resolution row is locked via SELECT FOR UPDATE during `assign_consecutivo`, so the `prefijo` cannot change until the lock is released. Tested via `test_prefijo_snapshot_independent_of_resolution_change` (REQ-OPS-074 Scenario 1). |
| **R7** | Cloud dispatcher eventual consistency: the `/reintentar` endpoint INSERTs the new envio row locally; the cloud dispatcher eventually picks it up via sync (branch_to_cloud direction post-flip). During the lag window, the `GET` endpoint may return stale `estado` (the previous chain tip, not the new one). | **LOW** | Documented as the canonical branch-cloud architecture per AGENTS.md. The `/reintentar` endpoint returns the NEW envio row in the response (so the client knows the retry was queued). The `GET` endpoint will eventually converge. Idempotency-Key header (DEC-IDEM-01 reuse) prevents client-side retry storms. |
| **R8** | Partial UK `one_fe_per_factura` (MIGRATION 0028 Op 2) requires `prod.factura_electronica.uuid_factura` to be NOT NULL for the UK to apply. If a FE row is INSERTed with `uuid_factura=NULL` (e.g., for testing), the UK does NOT enforce uniqueness for that row. | **LOW** | The handler always passes `uuid_factura=payload.uuid_factura` (required field, Pydantic `extra='forbid'` blocks omission). The partial UK is a defense in depth layer on top of the V2 SELECT-before-INSERT; both must be bypassed for a duplicate to slip through. Documented in REQ-OPS-067. |
| **R9** | MIGRATION 0028 Op 1 sync catalog flip is DML inside a DO $$ block. If the flip fails (e.g., the row was already flipped by another deployment), the DO $$ block silently no-ops via the WHERE clause `direction='cloud_to_branch'`. The migration is idempotent (verified). | **LOW** | `WHERE direction='cloud_to_branch'` filters the UPDATE; second application of the migration finds no row to update and the DO $$ block completes silently. Downgrade reverses the flip via the symmetric WHERE clause. Documented in MIGRATION 0028 §11 + REQ-OPS-072. |
| **R10** | MIGRATION 0028 downgrade reverses the sync catalog flip AFTER `DROP INDEX CONCURRENTLY`. If the downgrade fails between the DROP and the UPDATE, the indexes are dropped but the sync direction is still `branch_to_cloud`. The cloud dispatcher may experience brief sync-direction mismatch. | **LOW** | Documented in §3 + REQ-OPS-072. The downgrade MUST execute both ops in a single Alembic transaction (Alembic wraps them); partial failure requires manual intervention. Defensive: re-run the downgrade to complete the flip reverse. |

---

## 8. API Contracts

### 8.1 `POST /api/v1/facturacion/factura-electronica` (NEW)

**Request signature**:

```python
async def create_factura_electronica(
    response: Response,
    payload: FacturaElectronicaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> FacturaElectronicaRead:
```

**Body `FacturaElectronicaCreate`** (Pydantic v2, `extra='forbid'`):

```python
class FacturaElectronicaCreate(_Base):
    """HU-F1.10: POST /api/v1/facturacion/factura-electronica payload.

    Client supplies ONLY ``uuid_factura``. Server resolves vigente
    resolution for the factura's sucursal, assigns ``prefijo``+``consecutivo``
    via ``assign_consecutivo``, INSERTs ``prod.factura_electronica`` +
    initial ``prod.envio_dian`` row (estado='pendiente', uuid_envio_padre=NULL).
    ``extra='forbid'`` blocks client smuggling of ``prefijo``,
    ``consecutivo``, ``uuid_resolucion_facturacion``.
    """
    uuid_factura: uuid_lib.UUID
```

**Response `FacturaElectronicaRead`** (201, Pydantic v2):

```python
class EnvioDianRead(_Base):
    """Single envio_dian row in the chain.

    ``estado``, ``cufe``, ``timestamp_evento`` are SERVER-DERIVED from
    the latest envio_dian row via ``prod.v_factura_electronica_acuse``.
    NEVER fabricated ``reportado_dian`` boolean (plan.md línea 947).
    """
    uuid: uuid_lib.UUID
    uuid_factura_electronica: uuid_lib.UUID
    estado: Literal["pendiente", "enviado", "aceptado", "rechazado"]
    timestamp_evento: datetime
    uuid_envio_padre: uuid_lib.UUID | None
    cufe: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    motivo_rechazo: Annotated[str, StringConstraints(max_length=500)] | None = None


class FacturaElectronicaRead(_Base):
    """POST + GET /api/v1/facturacion/factura-electronica response.

    ``estado``, ``cufe``, ``timestamp_evento`` in ``envio_actual`` are
    SERVER-DERIVED from the latest envio_dian row via
    ``prod.v_factura_electronica_acuse``. NEVER stored on
    ``prod.factura_electronica`` (4NF + insert-only).
    """
    uuid: uuid_lib.UUID
    prefijo: Annotated[str, StringConstraints(min_length=1, max_length=10)]
    consecutivo: int = Field(ge=0)
    uuid_factura: uuid_lib.UUID
    uuid_resolucion_facturacion: uuid_lib.UUID
    created_at: datetime
    envio_actual: EnvioDianRead
```

**Headers**: `Cache-Control: no-store` (F1.3..F1.9 precedent, DEC-FE-06 NEW). `Idempotency-Key: <uuid>` (DEC-IDEM-01 reuse from F1.6 + F1.9).

**Error discriminators** (typed HTTPException details):

| HTTP | Body | Cuándo | KD / DEC |
|---|---|---|---|
| 403 | `{"error":"tenant_scope_violation","uuid_factura":"..."}` | `operador-` con `factura.uuid_sucursal != ctx.sucursal_uuid` (post-V1) | KD-S2 analog from F1.7 (REQ-OPS-064, XR1 layer b) |
| 404 | `{"error":"factura_no_encontrada","uuid_factura":"..."}` | V1: `prod.facturas.uuid` not found | REQ-OPS-064 V1 (V1) |
| 409 | `{"error":"factura_electronica_ya_existe","uuid_factura":"..."}` | V2: existing FE row OR partial UK violation (pgcode 23505) | REQ-OPS-067 + MIGRATION 0028 Op 2 (XR1 layer c) |
| 409 | `{"error":"resolucion_no_vigente","uuid_sucursal":"..."}` | V3: no vigente resolution for the sucursal | REQ-OPS-073 V3 |
| 409 | `{"error":"numeracion_agotada","uuid_resolucion_facturacion":"...","rango_hasta":<int>,"prefijo":"<str>"}` | V4: `assign_consecutivo` raised `ConsecutivoRangeExhaustedError` + alerta fired | REQ-OPS-066 + DEC-FE-03 |
| 409 | `{"error":"numeracion_duplicada","uuid_resolucion_facturacion":"...","consecutivo":<int>}` | UK01 race (pgcode 23505 on `factura_electronica_uk01`) | Rare race; mapped from `UniqueViolationError` |
| 500 | `{"error":"alerta_no_creada","tipo_alerta":"fe_numbering_exhausted"}` | Defense in depth: alerta insert failed before 409 | Should never happen (defensive) |
| 201 | `FacturaElectronicaRead` con `envio_actual.estado='pendiente'` | Happy path | KD-FE-01 single-commit |

### 8.2 `GET /api/v1/facturacion/factura-electronica/{uuid}` (NEW)

**Request signature**:

```python
async def get_factura_electronica(
    response: Response,
    uuid_factura_electronica: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> FacturaElectronicaRead:
```

**Response `FacturaElectronicaRead`** (200, same schema as POST). `envio_actual` JOINs `prod.v_factura_electronica_acuse` (REQ-OPS-068).

**Headers**: `Cache-Control: no-store`.

**Error discriminators**:

| HTTP | Body | Cuándo |
|---|---|---|
| 403 | `{"error":"tenant_scope_violation","uuid_factura_electronica":"..."}` | `operador-` con `fe.uuid_sucursal != ctx.sucursal_uuid` (post-V1) |
| 404 | `{"error":"factura_electronica_no_encontrada","uuid_factura_electronica":"..."}` | FE row does not exist |
| 200 | `FacturaElectronicaRead` with `envio_actual` from view | Happy path |

### 8.3 `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` (NEW)

**Request signature**:

```python
async def retry_factura_electronica(
    response: Response,
    uuid_factura_electronica: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> EnvioDianRetryRead:
```

**Body**: empty (the path parameter `uuid_factura_electronica` carries the intent).

**Response `EnvioDianRetryRead`** (201):

```python
class EnvioDianRetryRead(_Base):
    """HU-F1.10: POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar response.

    Returns the NEW envio_dian row. ``uuid_envio_padre`` points at the
    previous chain tip.
    """
    uuid: uuid_lib.UUID  # the NEW envio_dian row's uuid
    uuid_factura_electronica: uuid_lib.UUID
    estado: Literal["pendiente"]
    timestamp_evento: datetime
    uuid_envio_padre: uuid_lib.UUID  # previous tip
```

**Headers**: `Cache-Control: no-store`. `Idempotency-Key: <uuid>` (DEC-IDEM-01).

**Error discriminators**:

| HTTP | Body | Cuándo |
|---|---|---|
| 403 | `{"error":"tenant_scope_violation","uuid_factura_electronica":"..."}` | `operador-` cross-branch (post-V1) |
| 404 | `{"error":"factura_electronica_no_encontrada","uuid_factura_electronica":"..."}` | FE row does not exist |
| 409 | `{"error":"reintento_no_permitido","uuid_factura_electronica":"...","estado_actual":"aceptado"}` | Chain tip state is `aceptado` (DEC-FE-04) |
| 409 | `{"error":"envio_dian_already_pending","uuid_factura_electronica":"...","uuid_envio_pendiente":"..."}` | Chain tip is `pendiente` (rapid-retry guard) |
| 201 | `EnvioDianRetryRead` with NEW envio row | Happy path |

### 8.4 Typed error schemas

```python
class NumeracionAgotadaError(_Base):
    """REQ-OPS-066: assign_consecutivo range exhausted."""
    error: Literal["numeracion_agotada"]
    uuid_resolucion_facturacion: str
    rango_hasta: int
    prefijo: str


class ReintentoNoPermitidoError(_Base):
    """REQ-OPS-071: chain tip state is 'aceptado'."""
    error: Literal["reintento_no_permitido"]
    uuid_factura_electronica: str
    estado_actual: Literal["aceptado"]


class EnvioDianAlreadyPendingError(_Base):
    """REQ-OPS-071: chain tip state is 'pendiente' (rapid-retry guard)."""
    error: Literal["envio_dian_already_pending"]
    uuid_factura_electronica: str
    uuid_envio_pendiente: str


class FacturaElectronicaYaExisteError(_Base):
    """REQ-OPS-067: existing FE row for uuid_factura (V2 + partial UK race)."""
    error: Literal["factura_electronica_ya_existe"]
    uuid_factura: str


class ResolucionNoVigenteError(_Base):
    """REQ-OPS-073: no vigente resolution for uuid_sucursal."""
    error: Literal["resolucion_no_vigente"]
    uuid_sucursal: str


class FacturaNoEncontradaElectronicaError(_Base):
    """REQ-OPS-064 V1: prod.facturas.uuid not found."""
    error: Literal["factura_no_encontrada"]
    uuid_factura: str


class FacturaElectronicaNoEncontradaError(_Base):
    """GET + /reintentar V1: prod.factura_electronica.uuid not found."""
    error: Literal["factura_electronica_no_encontrada"]
    uuid_factura_electronica: str


class NumeracionDuplicadaError(_Base):
    """UK01 race on (uuid_resolucion_facturacion, consecutivo)."""
    error: Literal["numeracion_duplicada"]
    uuid_resolucion_facturacion: str
    consecutivo: int
```

Append to `schemas/facturacion.py` + update `__all__`. `extra='forbid'` (inherited from `_Base`) rejects client smuggling.

### 8.5 Sin cambios sobre

- `POST /api/v1/facturacion/factura` (F1.9, unchanged)
- `POST /api/v1/facturacion/factura-pagos` (F1.9, unchanged)
- `POST /api/v1/operacion/salidas` (F1.7, unchanged)
- `GET /api/v1/operacion/cotizar?uuid_ingreso` (F1.8, unchanged)
- `POST /api/v1/operacion/ingresos` (F1.6, unchanged)

### 8.6 Out of F1.10 scope (adjacent, lower priority)

- `GET /api/v1/facturacion/factura-electronica?uuid_factura=...` (paginated list) — proposed adjacent, lower priority, out of scope.
- `POST /api/v1/facturacion/factura-electronica/{uuid}/anular` — F1.13 anulaciones territory.
- Real DIAN web service integration — Fase 4 (contabilidad). The cloud dispatcher owns the actual provider call.

---

## 9. Handler Skeleton (pseudocode)

### 9.1 `POST /factura-electronica` — 12-step chain

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py
# (MODIFY existing file, +60 LOC for 3 new handlers)


from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import StringConstraints
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.tenancy import TenantContext, get_tenant_ctx
from ..deps import get_session, no_store_headers, requires_issuer, apply_no_store_header
from ..repo import factura_electronica as repo_factura_electronica
from ..repo import resolucion_facturacion as repo_resolucion_facturacion
from ..repo.alert_types import AlertaFactory
from ..repo.resolucion_facturacion import assign_consecutivo, ConsecutivoRangeExhaustedError
from ..schemas.facturacion import (
    EnvioDianRead,
    EnvioDianRetryRead,
    FacturaElectronicaCreate,
    FacturaElectronicaRead,
)


# KD-3 issuer chain (F1.9 pattern verbatim, DEC-FE-01 application dep).
_fe_issuer_dep = requires_issuer("operador-", "admin-")


@router.post(
    "/factura-electronica",
    response_model=FacturaElectronicaRead,
    status_code=201,
    summary=(
        "HU-F1.10 / REQ-OPS-064..067: assign prefijo+consecutivo via "
        "assign_consecutivo (SELECT FOR UPDATE), INSERT prod.factura_electronica "
        "+ initial prod.envio_dian in single await session.commit() (KD-FE-01)."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "factura_no_encontrada (V1)"},
        409: {"description": "factura_electronica_ya_existe | resolucion_no_vigente | numeracion_agotada"},
    },
)
async def create_factura_electronica(
    response: Response,
    payload: FacturaElectronicaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> FacturaElectronicaRead:
    """REQ-OPS-064..067: create FE + initial envio row atomically.

    Dependency chain (same as create_factura from F1.9):
        _fe_issuer_dep     -> requires_issuer("operador-", "admin-")
        get_tenant_ctx     -> TenantContext { actor_uuid, sucursal_uuid, ... }
        get_session        -> AsyncSession (request-scoped)

    Sequence (locked by AST walk, file tests/static/test_fe_handler_step_order.py
    + tests/static/test_fe_handler_single_commit.py):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 prod.facturas.uuid exists (404 if None)
        3. tenant scope post-V1 (403 if operador- cross-branch)
        4. V2 NO existing prod.factura_electronica row for uuid_factura (409)
        5. V3 vigente prod.resolucion_facturacion row for the sucursal (409)
        6. KD-FE-01 assign_consecutivo (SELECT FOR UPDATE on resolucion row)
           On ConsecutivoRangeExhaustedError -> 409 numeracion_agotada + alerta
        7. INSERT prod.factura_electronica [L-E] with prefijo snapshot
        8. INSERT initial prod.envio_dian row (estado='pendiente', uuid_envio_padre=NULL)
        9. Mock DIAN POST (real deferred Fase 4; cloud dispatcher reads via sync)
       10. KD-FE-01 single commit (lock release, FE row + envio row atomic)
       11. Response shape FacturaElectronicaRead with envio_actual
       12. DEC-FE-06: Cache-Control: no-store header

    Idempotency-Key: same header (DEC-IDEM-01 reuse from F1.6 + F1.9).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V1 (prod.facturas.uuid exists). -----------------------
    factura = await repo_factura_electronica.buscar_factura_por_uuid(
        session, uuid_factura=payload.uuid_factura
    )
    if factura is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "factura_no_encontrada", "uuid_factura": str(payload.uuid_factura)},
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    target_sucursal = factura.uuid_sucursal
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation", "uuid_factura": str(payload.uuid_factura)},
            headers=no_store,
        )

    # --- Step 4: V2 (NO existing prod.factura_electronica row for uuid_factura). ---
    existing_fe = await repo_factura_electronica.buscar_factura_electronica_por_factura(
        session, uuid_factura=payload.uuid_factura
    )
    if existing_fe is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "factura_electronica_ya_existe", "uuid_factura": str(payload.uuid_factura)},
            headers=no_store,
        )

    # --- Step 5: V3 (vigente prod.resolucion_facturacion row for the sucursal). ---
    resolucion = await repo_resolucion_facturacion.buscar_resolucion_vigente_por_sucursal(
        session, uuid_sucursal=target_sucursal
    )
    if resolucion is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "resolucion_no_vigente", "uuid_sucursal": str(target_sucursal)},
            headers=no_store,
        )

    # --- Step 6: KD-FE-01 assign_consecutivo (SELECT FOR UPDATE on resolucion row). ---
    try:
        consecutivo = await assign_consecutivo(
            session,
            resolucion_uuid=resolucion.uuid,
            source_event_uuid=payload.uuid_factura,
        )
    except ConsecutivoRangeExhaustedError as exc:
        # DEC-FE-03: fire alerta + 409 numeracion_agotada
        await AlertaFactory(session, ctx).fire("fe_numbering_exhausted", motivo=str(exc))
        raise HTTPException(
            status_code=409,
            detail={
                "error": "numeracion_agotada",
                "uuid_resolucion_facturacion": str(resolucion.uuid),
                "rango_hasta": resolucion.rango_hasta,
                "prefijo": resolucion.prefijo,
            },
            headers=no_store,
        )

    # --- Step 7: INSERT prod.factura_electronica [L-E] (snapshot prefijo). ---
    new_fe = await repo_factura_electronica.crear_factura_electronica_inicial(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=target_sucursal,
        uuid_factura=payload.uuid_factura,
        uuid_resolucion_facturacion=resolucion.uuid,
        prefijo=resolucion.prefijo,  # snapshot from V3 (REQ-OPS-074)
        consecutivo=consecutivo,
    )

    # --- Step 8: INSERT initial prod.envio_dian row. --------------------
    new_envio = await repo_factura_electronica.crear_envio_dian_inicial(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=target_sucursal,
        uuid_factura_electronica=new_fe.uuid,
        uuid_resolucion_facturacion=resolucion.uuid,
        payload={
            "prefijo": resolucion.prefijo,
            "consecutivo": consecutivo,
            "uuid_factura": str(payload.uuid_factura),
        },
    )

    # --- Step 9: Mock DIAN POST (real deferred Fase 4). ---------------
    # Cloud dispatcher reads via sync (branch_to_cloud direction per
    # MIGRATION 0028 Op 1) and writes transition rows asynchronously.
    # No synchronous DIAN call.

    # --- Step 10: KD-FE-01 single commit (FE row + envio row atomic). -
    await session.commit()  # UN solo commit (lock release, KD-FE-02)

    # --- Step 11: response shape. -------------------------------------
    # --- Step 12: DEC-FE-06 (Cache-Control: no-store header). ---------
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

### 9.2 `GET /factura-electronica/{uuid}` — 3-step chain

```python
@router.get(
    "/factura-electronica/{uuid_factura_electronica}",
    response_model=FacturaElectronicaRead,
    summary=(
        "HU-F1.10 / REQ-OPS-068..069: JOIN prod.v_factura_electronica_acuse "
        "view to expose server-derived estado + cufe + timestamp_evento. "
        "NEVER fabricates reportado_dian boolean (REQ-OPS-069)."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "factura_electronica_no_encontrada"},
    },
)
async def get_factura_electronica(
    response: Response,
    uuid_factura_electronica: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> FacturaElectronicaRead:
    """REQ-OPS-068..069: read FE + latest envio chain tip via JOIN.

    Sequence (locked by AST walk):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 FE row exists + tenant scope post-V1 (404 if None, 403 if cross-branch)
        3. JOIN prod.v_factura_electronica_acuse for envio_actual (estado + cufe + timestamp_evento)
        4. Response shape with Cache-Control: no-store (DEC-FE-06)

    Idempotency: GET is naturally idempotent.
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V1 (FE row exists + tenant scope). -------------------
    fe = await repo_factura_electronica.buscar_factura_electronica_por_uuid(
        session, uuid=uuid_factura_electronica
    )
    if fe is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "factura_electronica_no_encontrada", "uuid_factura_electronica": str(uuid_factura_electronica)},
            headers=no_store,
        )
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or fe.uuid_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation", "uuid_factura_electronica": str(uuid_factura_electronica)},
            headers=no_store,
        )

    # --- Step 3: JOIN prod.v_factura_electronica_acuse. ---------------
    ack = (
        await session.execute(
            text(
                "SELECT uuid, estado, cufe, timestamp_evento, motivo_rechazo "
                "FROM prod.v_factura_electronica_acuse "
                "WHERE uuid_factura_electronica = :uuid"
            ),
            {"uuid": str(uuid_factura_electronica)},
        )
    ).first()

    # --- Step 4: response shape + no_store header. --------------------
    apply_no_store_header(response)
    return FacturaElectronicaRead(
        uuid=fe.uuid,
        prefijo=fe.prefijo,
        consecutivo=fe.consecutivo,
        uuid_factura=fe.uuid_factura,
        uuid_resolucion_facturacion=fe.uuid_resolucion_facturacion,
        created_at=fe.created_at,
        envio_actual=EnvioDianRead(
            uuid=ack.uuid if ack else None,
            uuid_factura_electronica=fe.uuid,
            estado=ack.estado if ack else "pendiente",
            timestamp_evento=ack.timestamp_evento if ack else None,
            uuid_envio_padre=None,  # GET response does NOT expose chain
            cufe=ack.cufe if ack else None,
            motivo_rechazo=ack.motivo_rechazo if ack else None,
        ),
    )
```

### 9.3 `POST /factura-electronica/{uuid}/reintentar` — 8-step chain

```python
@router.post(
    "/factura-electronica/{uuid_factura_electronica}/reintentar",
    response_model=EnvioDianRetryRead,
    status_code=201,
    summary=(
        "HU-F1.10 / REQ-OPS-070..071: INSERT NEW prod.envio_dian row with "
        "uuid_envio_padre=<previous_tip> (NEVER UPDATE). Blocked on "
        "aceptado chain tip (DEC-FE-04)."
    ),
    responses={
        403: {"description": "tenant_scope_violation"},
        404: {"description": "factura_electronica_no_encontrada"},
        409: {"description": "reintento_no_permitido | envio_dian_already_pending"},
    },
)
async def retry_factura_electronica(
    response: Response,
    uuid_factura_electronica: uuid_lib.UUID,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_fe_issuer_dep),
) -> EnvioDianRetryRead:
    """REQ-OPS-070..071: retry DIAN submission via NEW envio row.

    Sequence (locked by AST walk file
    tests/static/test_fe_retry_handler_single_commit.py +
    tests/static/test_fe_retry_handler_no_update_on_envio_dian.py):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V1 FE row exists (404 if None)
        3. Tenant scope post-V1 (403 if cross-branch)
        4. V2 chain tip state check (VigenteWorkflowBase):
            - aceptado -> 409 reintento_no_permitido (DEC-FE-04)
            - pendiente -> 409 envio_dian_already_pending
            - rechazado -> proceed to INSERT
        5. V3 INSERT NEW prod.envio_dian row (DEC-FE-02 + DEC-FE-07):
            uuid_envio_padre=<tip.uuid>, estado='pendiente'
        6. Mock DIAN POST (real deferred Fase 4)
        7. KD-FE-01 single commit (new envio row atomic)
        8. DEC-FE-06: response shape + Cache-Control: no-store header

    Idempotency-Key: same header (DEC-IDEM-01).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------

    # --- Step 2: V1 (FE row exists). ----------------------------------
    fe = await repo_factura_electronica.buscar_factura_electronica_por_uuid(
        session, uuid=uuid_factura_electronica
    )
    if fe is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "factura_electronica_no_encontrada", "uuid_factura_electronica": str(uuid_factura_electronica)},
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or fe.uuid_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_scope_violation", "uuid_factura_electronica": str(uuid_factura_electronica)},
            headers=no_store,
        )

    # --- Step 4: V2 chain tip state check (DEC-FE-04). ----------------
    tip_envio = await repo_factura_electronica.buscar_envio_dian_chain_tip(
        session, uuid_factura_electronica=uuid_factura_electronica
    )
    if tip_envio is None:
        raise HTTPException(
            status_code=409,
            detail={"error": "reintento_no_permitido", "uuid_factura_electronica": str(uuid_factura_electronica), "estado_actual": None},
            headers=no_store,
        )
    if tip_envio.estado == "aceptado":
        raise HTTPException(
            status_code=409,
            detail={"error": "reintento_no_permitido", "uuid_factura_electronica": str(uuid_factura_electronica), "estado_actual": "aceptado"},
            headers=no_store,
        )
    if tip_envio.estado == "pendiente":
        raise HTTPException(
            status_code=409,
            detail={"error": "envio_dian_already_pending", "uuid_factura_electronica": str(uuid_factura_electronica), "uuid_envio_pendiente": str(tip_envio.uuid)},
            headers=no_store,
        )

    # --- Step 5: V3 INSERT NEW prod.envio_dian row (DEC-FE-02 + DEC-FE-07). ---
    new_envio = await repo_factura_electronica.crear_envio_dian_reintento(
        session,
        actor_uuid=ctx.actor_uuid,
        uuid_sucursal=fe.uuid_sucursal,
        uuid_factura_electronica=uuid_factura_electronica,
        uuid_resolucion_facturacion=fe.uuid_resolucion_facturacion,
        payload={
            "prefijo": fe.prefijo,  # snapshot from FE row (REQ-OPS-074)
            "consecutivo": fe.consecutivo,
            "uuid_factura": str(fe.uuid_factura),
        },
        uuid_envio_padre=tip_envio.uuid,  # previous chain tip
    )

    # --- Step 6: Mock DIAN POST (real deferred Fase 4). ---------------

    # --- Step 7: KD-FE-01 single commit. ------------------------------
    await session.commit()  # UN solo commit (new envio row atomic)

    # --- Step 8: response shape + no_store header. --------------------
    apply_no_store_header(response)
    return EnvioDianRetryRead(
        uuid=new_envio.uuid,
        uuid_factura_electronica=uuid_factura_electronica,
        estado="pendiente",
        timestamp_evento=new_envio.timestamp_evento,
        uuid_envio_padre=tip_envio.uuid,  # previous tip
    )
```

**Notes.**
- The 3 new handlers are registered on the EXISTING `APIRouter` in `api/v1/facturacion.py` (F1.9 introduced this module). F1.10 adds 3 NEW `@router.{post,get,post}` decorators after the F1.9 ones.
- All repo helpers are imported from `parkos_core.repo.{factura_electronica, resolucion_facturacion}`. The handler does not write SQL inline (except the GET endpoint's JOIN to `prod.v_factura_electronica_acuse` which uses `session.execute(text(...))` per REQ-OPS-068).
- `await session.commit()` happens EXACTLY ONCE in `create_factura_electronica` (KD-FE-01 + REQ-OPS-065) and EXACTLY ONCE in `retry_factura_electronica` (KD-FE-01 + REQ-OPS-070). The `get_factura_electronica` handler is read-only (no commit). AST walks `tests/static/test_fe_handler_single_commit.py` + `tests/static/test_fe_retry_handler_single_commit.py` enforce the invariant.
- The 12-step order for `create_factura_electronica` is intentional: V1 before tenant scope avoids info leak; V2 after V1 derives `target_sucursal` (same V1 lookup used for tenant scope); V3 after V2 (resolution lookup is gated by V2 success); KD-FE-01 (Step 6) BEFORE INSERT (Step 7) so the `prefijo` + `consecutivo` are available at INSERT time; INSERT (Steps 7, 8) BEFORE commit (Step 10) so both rows materialize atomically.
- The 8-step order for `retry_factura_electronica` is intentional: V1 before tenant scope; chain tip lookup (Step 4) BEFORE INSERT (Step 5) so `uuid_envio_padre` is available; INSERT (Step 5) BEFORE commit (Step 7) so the new envio row materializes atomically.
- `extra='forbid'` (inherited from `_Base`) rejects extra fields including `prefijo` (DEC-FE-05), `consecutivo` (DEC-FE-05), `uuid_resolucion_facturacion` (4NF), `reportado_dian` (FORBIDDEN per plan.md línea 947).
- **FK ordering**: `prod.factura_electronica` references `prod.facturas.uuid` and `prod.resolucion_facturacion.uuid`; `prod.envio_dian` references `prod.factura_electronica.uuid` and `prod.resolucion_facturacion.uuid`. Step 7 INSERT of `prod.factura_electronica` populates `new_fe.uuid` via DB default `gen_random_uuid()`. Step 8 INSERT of `prod.envio_dian` uses `new_fe.uuid`. Single commit in Step 10 materializes both rows atomically.

---

## 10. Repo Layer — File-by-File

### 10.1 `backend/packages/parkos_core/src/parkos_core/repo/factura_electronica.py` (NEW, ~250 LOC)

```python
"""HU-F1.10 / REQ-OPS-064..074 — FE numbering + estado DIAN + retry.

Helpers for ``POST /api/v1/facturacion/factura-electronica``:
- ``buscar_factura_por_uuid`` (V1) — checks ``prod.facturas.uuid`` exists.
- ``buscar_factura_electronica_por_factura`` (V2) — existing FE for uuid_factura.
- ``buscar_factura_electronica_por_uuid`` (V1) — FE row by uuid.
- ``crear_factura_electronica_inicial`` (Step 7 INSERT [L-E]).
- ``crear_envio_dian_inicial`` (Step 8 INSERT [L-W] initial).
- ``crear_envio_dian_reintento`` (Step 5 INSERT [L-W] retry with uuid_envio_padre).
- ``buscar_envio_dian_chain_tip`` (V2 chain-tip via VigenteWorkflowBase).
- ``leer_factura_electronica_con_envio_via_view`` (GET JOIN to view).
- ``validar_uuid_factura_y_sucursal`` (V1 + tenant scope data).

8 typed exceptions:
- ``FacturaNoEncontradaElectronicaError`` (V1 404).
- ``FacturaElectronicaNoEncontradaError`` (GET + /reintentar V1 404).
- ``FacturaElectronicaYaExisteError`` (V2 409 + partial UK race).
- ``ReintentoNoPermitidoError`` (V2 409 on aceptado).
- ``EnvioDianAlreadyPendingError`` (V2 409 on pendiente).
- ``NumeracionDuplicadaError`` (UK01 race on (resolucion, consecutivo)).
- ``ResolucionNoVigenteError`` (V3 409).
- ``ConsecutivoRangeExhaustedError`` (V4 409, RE-EXPORTED from
  ``repo/resolucion_facturacion.py`` for callers).

DEC-FE-01: envio_dian writes are branch-initiated.
DEC-FE-02: retry chain via NEW row + uuid_envio_padre (NEVER UPDATE).
DEC-FE-05: assign_consecutivo reused as-is, NO modification.
KD-FE-01: handler commits ONCE; this module does NOT commit.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.factura_electronica import FacturaElectronica
from ..models.L_E.facturas import Facturas
from ..models.L_W.envio_dian import EnvioDian
from ..models.V.resolucion_facturacion import ResolucionFacturacion


# --- Typed exceptions --------------------------------------------------------


class FacturaNoEncontradaElectronicaError(Exception):
    """V1 404 discriminator — prod.facturas.uuid not found."""

    def __init__(self, *, uuid_factura: uuid_lib.UUID) -> None:
        self.uuid_factura = uuid_factura
        super().__init__(f"factura_no_encontrada: uuid_factura={uuid_factura}")


class FacturaElectronicaNoEncontradaError(Exception):
    """GET + /reintentar V1 404 discriminator — prod.factura_electronica.uuid not found."""

    def __init__(self, *, uuid_factura_electronica: uuid_lib.UUID) -> None:
        self.uuid_factura_electronica = uuid_factura_electronica
        super().__init__(f"factura_electronica_no_encontrada: uuid_factura_electronica={uuid_factura_electronica}")


class FacturaElectronicaYaExisteError(Exception):
    """V2 409 discriminator — existing FE row for uuid_factura OR partial UK race."""

    def __init__(self, *, uuid_factura: uuid_lib.UUID) -> None:
        self.uuid_factura = uuid_factura
        super().__init__(f"factura_electronica_ya_existe: uuid_factura={uuid_factura}")


class ReintentoNoPermitidoError(Exception):
    """V2 409 discriminator — chain tip state is 'aceptado'."""

    def __init__(self, *, uuid_factura_electronica: uuid_lib.UUID, estado_actual: str | None) -> None:
        self.uuid_factura_electronica = uuid_factura_electronica
        self.estado_actual = estado_actual
        super().__init__(
            f"reintento_no_permitido: uuid_factura_electronica={uuid_factura_electronica}, "
            f"estado_actual={estado_actual}"
        )


class EnvioDianAlreadyPendingError(Exception):
    """V2 409 discriminator — chain tip state is 'pendiente' (rapid-retry guard)."""

    def __init__(self, *, uuid_factura_electronica: uuid_lib.UUID, uuid_envio_pendiente: uuid_lib.UUID) -> None:
        self.uuid_factura_electronica = uuid_factura_electronica
        self.uuid_envio_pendiente = uuid_envio_pendiente
        super().__init__(
            f"envio_dian_already_pending: uuid_factura_electronica={uuid_factura_electronica}, "
            f"uuid_envio_pendiente={uuid_envio_pendiente}"
        )


class NumeracionDuplicadaError(Exception):
    """UK01 race — pgcode 23505 on factura_electronica_uk01 (uuid_resolucion_facturacion, consecutivo)."""

    def __init__(self, *, uuid_resolucion_facturacion: uuid_lib.UUID, consecutivo: int) -> None:
        self.uuid_resolucion_facturacion = uuid_resolucion_facturacion
        self.consecutivo = consecutivo
        super().__init__(
            f"numeracion_duplicada: uuid_resolucion_facturacion={uuid_resolucion_facturacion}, "
            f"consecutivo={consecutivo}"
        )


class ResolucionNoVigenteError(Exception):
    """V3 409 discriminator — no vigente resolution for uuid_sucursal."""

    def __init__(self, *, uuid_sucursal: uuid_lib.UUID) -> None:
        self.uuid_sucursal = uuid_sucursal
        super().__init__(f"resolucion_no_vigente: uuid_sucursal={uuid_sucursal}")


# Re-export for callers (DEC-FE-03 + DEC-FE-05 + REQ-OPS-066).
from .resolucion_facturacion import ConsecutivoRangeExhaustedError  # noqa: E402


# --- V1: prod.facturas.uuid exists -------------------------------------------


async def buscar_factura_por_uuid(
    session: AsyncSession, *, uuid_factura: uuid_lib.UUID
) -> Facturas | None:
    """V1: SELECT ``prod.facturas`` row by PK.

    Returns the ORM ``Facturas`` row if found, else None. Does NOT raise;
    the handler raises the 404.
    """
    return await session.get(Facturas, uuid_factura)


# --- V2 (handler): existing FE row for uuid_factura --------------------------


async def buscar_factura_electronica_por_factura(
    session: AsyncSession, *, uuid_factura: uuid_lib.UUID
) -> FacturaElectronica | None:
    """V2: SELECT current ``prod.factura_electronica`` row for ``uuid_factura``.

    Returns the ORM row if found, else None. The partial UK
    ``one_fe_per_factura`` (MIGRATION 0028 Op 2) guarantees at most one
    row per uuid_factura (NOT NULL).
    """
    stmt = select(FacturaElectronica).where(
        FacturaElectronica.uuid_factura == uuid_factura
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --- V1 (GET + /reintentar): FE row exists by uuid ---------------------------


async def buscar_factura_electronica_por_uuid(
    session: AsyncSession, *, uuid: uuid_lib.UUID
) -> FacturaElectronica | None:
    """V1 (GET + /reintentar): SELECT current ``prod.factura_electronica`` row by uuid.

    Returns the ORM row if found, else None. The handler raises the 404
    if None.
    """
    return await session.get(FacturaElectronica, uuid)


# --- Step 7 INSERT prod.factura_electronica [L-E] ----------------------------


async def crear_factura_electronica_inicial(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_factura: uuid_lib.UUID,
    uuid_resolucion_facturacion: uuid_lib.UUID,
    prefijo: str,
    consecutivo: int,
) -> FacturaElectronica:
    """Step 7 INSERT: single ``prod.factura_electronica`` row.

    The ``prefijo`` is snapshotted from the vigente ``prod.resolucion_facturacion``
    row returned by V3 (REQ-OPS-074). The ``consecutivo`` is from
    ``assign_consecutivo``. ``descuento=Decimal(0)`` (MVP).

    Sets ``fecha_retencion_hasta = date.today() + timedelta(days=5*365)``
    (DIAN 5-year retention).

    Triggers BEFORE INSERT (handled by DB):
    - ``factura_electronica_audit_columns`` sets ``created_at`` + ``created_by``.
    - ``factura_electronica_set_vigente_inicial`` sets ``vigente_inicial``.

    Catches ``IntegrityError`` on partial UK `one_fe_per_factura` (pgcode 23505)
    and raises ``FacturaElectronicaYaExisteError``.
    """
    fecha_retencion_hasta = date.today() + timedelta(days=5 * 365)
    fe_row = FacturaElectronica(
        uuid=uuid_lib.uuid4(),
        fecha_retencion_hasta=fecha_retencion_hasta,
        uuid_sucursal=uuid_sucursal,
        uuid_factura=uuid_factura,
        uuid_resolucion_facturacion=uuid_resolucion_facturacion,
        prefijo=prefijo,
        consecutivo=consecutivo,
        descuento=Decimal(0),
        created_by=actor_uuid,
    )
    session.add(fe_row)
    try:
        await session.flush()
    except IntegrityError as exc:
        # REQ-OPS-067 Scenario 3 — partial UK violation mapped to typed exception.
        pgcode = getattr(getattr(exc, "orig", None), "pgcode", None)
        if pgcode == "23505":
            await session.rollback()
            raise FacturaElectronicaYaExisteError(uuid_factura=uuid_factura) from exc
        raise
    return fe_row


# --- Step 8 INSERT initial prod.envio_dian [L-W] -----------------------------


async def crear_envio_dian_inicial(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_factura_electronica: uuid_lib.UUID,
    uuid_resolucion_facturacion: uuid_lib.UUID,
    payload: dict,
) -> EnvioDian:
    """Step 8 INSERT: initial ``prod.envio_dian`` row.

    Sets ``estado='pendiente'``, ``uuid_envio_padre=NULL``, ``cufe=NULL``,
    ``respuesta_proveedor=NULL``, ``timestamp_evento=now()``.

    The ``payload`` JSONB includes ``prefijo`` + ``consecutivo`` + ``uuid_factura``
    (denormalized snapshot for cloud dispatcher consumption).
    """
    fecha_retencion_hasta = date.today() + timedelta(days=5 * 365)
    envio_row = EnvioDian(
        uuid=uuid_lib.uuid4(),
        fecha_retencion_hasta=fecha_retencion_hasta,
        uuid_sucursal=uuid_sucursal,
        uuid_factura_electronica=uuid_factura_electronica,
        uuid_resolucion_facturacion=uuid_resolucion_facturacion,
        payload=payload,
        respuesta_proveedor=None,
        cufe=None,
        uuid_envio_padre=None,  # initial row
        timestamp_evento=datetime.now(UTC),
        estado="pendiente",
        vigente_desde=datetime.now(UTC),
        vigente_hasta=None,
        created_by=actor_uuid,
    )
    session.add(envio_row)
    await session.flush()
    return envio_row


# --- V2 chain tip lookup (VigenteWorkflowBase) -------------------------------


async def buscar_envio_dian_chain_tip(
    session: AsyncSession, *, uuid_factura_electronica: uuid_lib.UUID
) -> EnvioDian | None:
    """V2 chain-tip lookup (Step 4 of /reintentar).

    Returns the LATEST ``prod.envio_dian`` row for the FE by
    ``timestamp_evento DESC LIMIT 1``. Mirrors the
    ``v_factura_electronica_acuse`` view's ``DISTINCT ON`` semantic.
    """
    stmt = (
        select(EnvioDian)
        .where(EnvioDian.uuid_factura_electronica == uuid_factura_electronica)
        .order_by(EnvioDian.timestamp_evento.desc(), EnvioDian.uuid.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --- Step 5 INSERT retry prod.envio_dian [L-W] -------------------------------


async def crear_envio_dian_reintento(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    uuid_sucursal: uuid_lib.UUID,
    uuid_factura_electronica: uuid_lib.UUID,
    uuid_resolucion_facturacion: uuid_lib.UUID,
    payload: dict,
    uuid_envio_padre: uuid_lib.UUID,
) -> EnvioDian:
    """Step 5 INSERT (DEC-FE-02 + DEC-FE-07): NEW ``prod.envio_dian`` retry row.

    Sets ``uuid_envio_padre=<tip.uuid>``, ``estado='pendiente'``, ``cufe=NULL``.

    The chain IS the audit trail. NEVER UPDATE on existing envio rows.
    """
    fecha_retencion_hasta = date.today() + timedelta(days=5 * 365)
    envio_row = EnvioDian(
        uuid=uuid_lib.uuid4(),
        fecha_retencion_hasta=fecha_retencion_hasta,
        uuid_sucursal=uuid_sucursal,
        uuid_factura_electronica=uuid_factura_electronica,
        uuid_resolucion_facturacion=uuid_resolucion_facturacion,
        payload=payload,
        respuesta_proveedor=None,
        cufe=None,
        uuid_envio_padre=uuid_envio_padre,  # previous tip
        timestamp_evento=datetime.now(UTC),
        estado="pendiente",
        vigente_desde=datetime.now(UTC),
        vigente_hasta=None,
        created_by=actor_uuid,
    )
    session.add(envio_row)
    await session.flush()
    return envio_row


# --- GET JOIN to v_factura_electronica_acuse ---------------------------------


async def leer_factura_electronica_con_envio_via_view(
    session: AsyncSession, *, uuid: uuid_lib.UUID
) -> tuple[FacturaElectronica, dict[str, Any] | None]:
    """Step 3 of GET (REQ-OPS-068): JOIN ``prod.v_factura_electronica_acuse``.

    Returns ``(fe_row, ack_row_or_None)`` where ``ack_row_or_None`` is the
    view row as a dict (``uuid``, ``estado``, ``cufe``, ``timestamp_evento``,
    ``motivo_rechazo``) or ``None`` if the FE has zero envio rows
    (defensive null mapping per REQ-OPS-068 Scenario 2).
    """
    fe_row = await session.get(FacturaElectronica, uuid)
    if fe_row is None:
        return None, None  # handler raises 404
    ack_row = (
        await session.execute(
            text(
                "SELECT uuid, estado, cufe, timestamp_evento, motivo_rechazo "
                "FROM prod.v_factura_electronica_acuse "
                "WHERE uuid_factura_electronica = :uuid"
            ),
            {"uuid": str(uuid)},
        )
    ).first()
    if ack_row is None:
        return fe_row, None
    return fe_row, {
        "uuid": ack_row.uuid,
        "estado": ack_row.estado,
        "cufe": ack_row.cufe,
        "timestamp_evento": ack_row.timestamp_evento,
        "motivo_rechazo": ack_row.motivo_rechazo,
    }


# --- V1 + tenant scope helper (combined for DRY) -----------------------------


async def validar_uuid_factura_y_sucursal(
    session: AsyncSession, *, uuid_factura: uuid_lib.UUID
) -> tuple[Facturas, uuid_lib.UUID]:
    """V1 + tenant scope data extraction.

    Returns ``(factura_row, target_sucursal_uuid)`` if found, else raises
    ``FacturaNoEncontradaElectronicaError`` (handler maps to 404).
    """
    factura = await session.get(Facturas, uuid_factura)
    if factura is None:
        raise FacturaNoEncontradaElectronicaError(uuid_factura=uuid_factura)
    return factura, factura.uuid_sucursal


__all__ = [
    # Typed exceptions
    "FacturaNoEncontradaElectronicaError",
    "FacturaElectronicaNoEncontradaError",
    "FacturaElectronicaYaExisteError",
    "ReintentoNoPermitidoError",
    "EnvioDianAlreadyPendingError",
    "NumeracionDuplicadaError",
    "ResolucionNoVigenteError",
    "ConsecutivoRangeExhaustedError",  # re-export
    # V1
    "buscar_factura_por_uuid",
    "validar_uuid_factura_y_sucursal",
    # V2 (handler)
    "buscar_factura_electronica_por_factura",
    # V1 (GET + /reintentar)
    "buscar_factura_electronica_por_uuid",
    # Step 7
    "crear_factura_electronica_inicial",
    # Step 8 + Step 5
    "crear_envio_dian_inicial",
    "crear_envio_dian_reintento",
    # Step 4
    "buscar_envio_dian_chain_tip",
    # GET JOIN
    "leer_factura_electronica_con_envio_via_view",
]
```

**Notes.**
- 9 helpers + 8 typed exceptions (~250 LOC). Mirrors F1.9 `repo/factura.py` structure.
- The module does NOT call `session.commit()`. KD-FE-01 enforces single commit at the handler layer.
- `crear_envio_dian_inicial` + `crear_envio_dian_reintento` are nearly identical (both INSERT new envio_dian row); they differ ONLY in `uuid_envio_padre` (NULL for initial, tip.uuid for retry). The duplication is intentional — keeps the two code paths visibly distinct for AST walk + code review.
- The `leer_factura_electronica_con_envio_via_view` helper is a thin wrapper around the raw SQL JOIN in the GET handler. Same shape as F1.9's `buscar_salida_facturable` wrapper.
- The `IntegrityError` catch in `crear_factura_electronica_inicial` handles the partial UK race (REQ-OPS-067 Scenario 3). Catches by pgcode `'23505'`, NEVER by Python `isinstance` alone (per REQ-OPS-067 Scenario 3 explicit instruction).

### 10.2 `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py` (MODIFY, +40 LOC)

Add ONE new helper to the existing F1.9 module:

```python
# ADD to existing repo/resolucion_facturacion.py after assign_consecutivo:


async def buscar_resolucion_vigente_por_sucursal(
    session: AsyncSession, *, uuid_sucursal: uuid_lib.UUID
) -> ResolucionFacturacion | None:
    """REQ-OPS-073: SELECT vigente prod.resolucion_facturacion row for uuid_sucursal.

    Defensive ``ORDER BY vigente_desde DESC LIMIT 1`` handles a corrupt DB
    with multiple vigente rows (bi-temporal VersionedBase). Returns the
    SINGLE row with the latest ``vigente_desde`` that has
    ``vigente_hasta IS NULL AND estado='activo'``.

    Returns None if no vigente row found (handler maps to 409
    ``resolucion_no_vigente``).
    """
    stmt = (
        select(ResolucionFacturacion)
        .where(
            ResolucionFacturacion.uuid_sucursal == uuid_sucursal,
            ResolucionFacturacion.vigente_hasta.is_(None),
            ResolucionFacturacion.estado == "activo",
        )
        .order_by(ResolucionFacturacion.vigente_desde.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
```

**Notes.**
- The helper is small (~25 LOC). Mirrors the structure of F1.4 bi-temporal vigente lookup.
- The `vigente_hasta IS NULL` filter is the canonical vigente marker per VersionedBase (migration 0001).
- The `estado='activo'` filter excludes inactive resolutions (F1.4 administrative mutation pattern).
- Returns `None` for missing; the handler maps to 409 `resolucion_no_vigente`.
- Unit test `test_buscar_resolucion_vigente_por_sucursal_returns_latest` covers the single + multi-vigente corrupt cases per REQ-OPS-073 Scenario 2.

### 10.3 `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (MODIFY, +80 LOC)

Append 4 schemas (FacturaElectronicaCreate, FacturaElectronicaRead, EnvioDianRead, EnvioDianRetryRead) + 8 typed error schemas to the existing F1.9 module. All schemas inherit from `_Base` (Pydantic v2 + `extra='forbid'`).

**Existing imports** (preserved from F1.9): `_Base`, `uuid_lib`, `Literal`, `StringConstraints`, `Field`. **New imports**: `Annotated`, `datetime`.

**Append** (after F1.9's last error schema):

```python
from datetime import datetime
from typing import Annotated
from pydantic import Field


# --- HU-F1.10: Factura Electrónica -------------------------------------------


class FacturaElectronicaCreate(_Base):
    """REQ-OPS-064: POST /factura-electronica payload."""
    uuid_factura: uuid_lib.UUID


class EnvioDianRead(_Base):
    """REQ-OPS-068..069: GET envio chain tip (DISTINCT ON view)."""
    uuid: uuid_lib.UUID
    uuid_factura_electronica: uuid_lib.UUID
    estado: Literal["pendiente", "enviado", "aceptado", "rechazado"]
    timestamp_evento: datetime
    uuid_envio_padre: uuid_lib.UUID | None
    cufe: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    motivo_rechazo: Annotated[str, StringConstraints(max_length=500)] | None = None


class FacturaElectronicaRead(_Base):
    """REQ-OPS-064 + REQ-OPS-068: POST + GET response."""
    uuid: uuid_lib.UUID
    prefijo: Annotated[str, StringConstraints(min_length=1, max_length=10)]
    consecutivo: int = Field(ge=0)
    uuid_factura: uuid_lib.UUID
    uuid_resolucion_facturacion: uuid_lib.UUID
    created_at: datetime
    envio_actual: EnvioDianRead


class EnvioDianRetryRead(_Base):
    """REQ-OPS-070: POST /reintentar response (NEW envio row)."""
    uuid: uuid_lib.UUID
    uuid_factura_electronica: uuid_lib.UUID
    estado: Literal["pendiente"]
    timestamp_evento: datetime
    uuid_envio_padre: uuid_lib.UUID


# --- Typed error schemas (8) -------------------------------------------------


class NumeracionAgotadaError(_Base):
    """REQ-OPS-066: assign_consecutivo range exhausted."""
    error: Literal["numeracion_agotada"]
    uuid_resolucion_facturacion: str
    rango_hasta: int
    prefijo: str


class ReintentoNoPermitidoError(_Base):
    """REQ-OPS-071: chain tip state is 'aceptado'."""
    error: Literal["reintento_no_permitido"]
    uuid_factura_electronica: str
    estado_actual: Literal["aceptado"]


class EnvioDianAlreadyPendingError(_Base):
    """REQ-OPS-071: chain tip state is 'pendiente' (rapid-retry guard)."""
    error: Literal["envio_dian_already_pending"]
    uuid_factura_electronica: str
    uuid_envio_pendiente: str


class FacturaElectronicaYaExisteError(_Base):
    """REQ-OPS-067: existing FE row for uuid_factura (V2 + partial UK race)."""
    error: Literal["factura_electronica_ya_existe"]
    uuid_factura: str


class ResolucionNoVigenteError(_Base):
    """REQ-OPS-073: no vigente resolution for uuid_sucursal."""
    error: Literal["resolucion_no_vigente"]
    uuid_sucursal: str


class FacturaNoEncontradaElectronicaError(_Base):
    """REQ-OPS-064 V1: prod.facturas.uuid not found."""
    error: Literal["factura_no_encontrada"]
    uuid_factura: str


class FacturaElectronicaNoEncontradaError(_Base):
    """GET + /reintentar V1: prod.factura_electronica.uuid not found."""
    error: Literal["factura_electronica_no_encontrada"]
    uuid_factura_electronica: str


class NumeracionDuplicadaError(_Base):
    """UK01 race on (uuid_resolucion_facturacion, consecutivo)."""
    error: Literal["numeracion_duplicada"]
    uuid_resolucion_facturacion: str
    consecutivo: int
```

Update `__all__` to include all 12 new symbols.

---

## 11. Migrations — MIGRATION 0028

### 11.1 Migration metadata

| Property | Value |
|---|---|
| **Filename** | `0028_one_fe_per_factura_and_chain_index_and_sync_flip.py` |
| **Revision** | `0028_one_fe_per_factura_and_chain_index_and_sync_flip` |
| **Down revision** | `0027_one_factura_per_salida_and_init_pago_trigger_and_revoke` (F1.9 chain head) |
| **Scope** | 4 operations: pre-flight + sync catalog flip + partial UK + covering index + GRANT re-assertion |
| **LOC** | ~180 LOC |

### 11.2 Op 1 — Pre-flight + DEC-FE-01 sync catalog flip

```python
"""HU-F1.10 / MIGRATION 0028 — one_fe_per_factura + chain-tip covering index
+ DEC-FE-01 sync catalog flip + defensive GRANT re-assertion.

Revision ID: 0028_one_fe_per_factura_and_chain_index_and_sync_flip
Revises: 0027_one_factura_per_salida_and_init_pago_trigger_and_revoke (F1.9 chain head)
Create Date: 2026-09-14

**Scope.** Five operations in strict order:

  1. **Pre-flight (KD-7 F1.6 + F1.7 + F1.9 pattern)**: ``DO $$`` block aborts
     the migration with a typed ``0028_preflight_abort`` exception if any
     of the 5 expected tables (``prod.factura_electronica``,
     ``prod.envio_dian``, ``prod.resolucion_facturacion``,
     ``prod.facturas``, ``sync_catalog``) does not exist. Emits
     ``RAISE NOTICE`` with the row counts.

  2. **DEC-FE-01 sync catalog flip**: ``UPDATE sync_catalog SET
     direction='branch_to_cloud' WHERE table_name='envio_dian' AND
     direction='cloud_to_branch'``. Reverses D1-rev/D5-rev from PR2. The
     WHERE clause makes the UPDATE idempotent (second application finds
     no row to update).

  3. **Partial unique index ``one_fe_per_factura`` (REQ-OPS-067)**:
     ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_fe_per_factura ON
     prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT
     NULL``. ``prod.factura_electronica`` is NOT partitioned (verified
     pre-apply via ``models/L_E/factura_electronica.py`` — composite PK
     ``(uuid, fecha_retencion_hasta)``, no ``postgresql_partition_by``),
     so a partial unique index is feasible. Closes the concurrent-create
     race condition: even if two T1-aligned POSTs see the same
     ``uuid_factura`` as "without existing FE", the second INSERT raises
     ``UniqueViolation`` (pgcode 23505), which the repo maps to
     ``FacturaElectronicaYaExisteError → HTTP 409``.

  4. **Covering index ``idx_envio_dian_chain_tip`` (REQ-OPS-068)**:
     ``CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_envio_dian_chain_tip ON
     prod.envio_dian (uuid_factura_electronica, timestamp_evento DESC)
     WHERE uuid_factura_electronica IS NOT NULL``. Speeds up the GET
     endpoint's JOIN to ``prod.v_factura_electronica_acuse`` (which
     performs ``DISTINCT ON (uuid_factura_electronica) ORDER BY
     timestamp_evento DESC NULLS LAST, uuid DESC``).

  5. **Defensive GRANT re-assertion**: ``GRANT SELECT, INSERT, UPDATE ON
     prod.{factura_electronica,envio_dian,resolucion_facturacion} TO
     rol_app``. F1.9 MIGRATION 0027 Op 4 REVOKE'd UPDATE/DELETE on
     ``prod.factura_electronica`` and ``prod.envio_dian`` from ``rol_app``
     — but the GRANT pattern for F1.10 INSERTs requires re-assertion.
     The GRANTs are idempotent (second application is a no-op).

**Idempotency.**
  - Op 1 ``DO $$`` is read-only.
  - Op 2 ``UPDATE ... WHERE direction='cloud_to_branch'`` is idempotent.
  - Op 3 ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`` is the
    standard idempotent pattern.
  - Op 4 ``CREATE INDEX CONCURRENTLY IF NOT EXISTS`` is idempotent.
  - Op 5 ``GRANT ... TO rol_app`` is idempotent.

**Downgrade.**
  1. ``REVOKE SELECT, INSERT, UPDATE ON prod.* FROM rol_app`` (Op 5 reverse).
  2. ``DROP INDEX CONCURRENTLY IF EXISTS prod.idx_envio_dian_chain_tip``
     (Op 4 reverse).
  3. ``DROP INDEX CONCURRENTLY IF EXISTS prod.one_fe_per_factura`` (Op 3 reverse).
  4. ``UPDATE sync_catalog SET direction='cloud_to_branch' WHERE
     table_name='envio_dian' AND direction='branch_to_cloud'`` (Op 2 reverse).
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0028_one_fe_per_factura_and_chain_index_and_sync_flip"
down_revision = "0027_one_factura_per_salida_and_init_pago_trigger_and_revoke"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # Op 1: pre-flight `DO $$` (KD-7 F1.6 + F1.7 + F1.9 pattern)
    # ----------------------------------------------------------------
    op.execute(
        """
        DO $$
        DECLARE
            _n_factura_electronica bigint;
            _n_envio_dian bigint;
            _n_resolucion_facturacion bigint;
            _n_facturas bigint;
            _n_sync_catalog bigint;
        BEGIN
            SELECT count(*) INTO _n_factura_electronica
                FROM pg_catalog.pg_class
                WHERE relname = 'factura_electronica' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_envio_dian
                FROM pg_catalog.pg_class
                WHERE relname = 'envio_dian' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_resolucion_facturacion
                FROM pg_catalog.pg_class
                WHERE relname = 'resolucion_facturacion' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_facturas
                FROM pg_catalog.pg_class
                WHERE relname = 'facturas' AND relnamespace = 'prod'::regnamespace;
            SELECT count(*) INTO _n_sync_catalog
                FROM pg_catalog.pg_class
                WHERE relname = 'sync_catalog' AND relnamespace = 'sync'::regnamespace;

            IF _n_factura_electronica IS NULL OR _n_factura_electronica = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla prod.factura_electronica no existe. '
                                'Aplique migrations 0001-0027 antes.';
            END IF;
            IF _n_envio_dian IS NULL OR _n_envio_dian = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla prod.envio_dian no existe.';
            END IF;
            IF _n_resolucion_facturacion IS NULL OR _n_resolucion_facturacion = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla prod.resolucion_facturacion no existe. '
                                'Aplique MIGRATION 0001 antes.';
            END IF;
            IF _n_facturas IS NULL OR _n_facturas = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla prod.facturas no existe. '
                                'Aplique F1.9 MIGRATION 0027 antes.';
            END IF;
            IF _n_sync_catalog IS NULL OR _n_sync_catalog = 0 THEN
                RAISE EXCEPTION '0028_preflight_abort: tabla sync.sync_catalog no existe. '
                                'Aplique MIGRATION 0001 + sync-catalog seed antes.';
            END IF;

            RAISE NOTICE '0028_preflight: 5/5 tablas OK '
                         '(factura_electronica, envio_dian, resolucion_facturacion, '
                         'facturas, sync_catalog)';
        END;
        $$;
        """
    )

    # ----------------------------------------------------------------
    # Op 2: DEC-FE-01 sync catalog flip (cloud_to_branch → branch_to_cloud)
    # ----------------------------------------------------------------
    # The WHERE clause makes this idempotent: second application finds no
    # row with direction='cloud_to_branch' (already flipped) and is a no-op.
    op.execute(
        """
        UPDATE sync.sync_catalog
        SET direction = 'branch_to_cloud'
        WHERE table_name = 'envio_dian' AND direction = 'cloud_to_branch';
        """
    )

    # ----------------------------------------------------------------
    # Op 3: partial unique index `one_fe_per_factura`
    # ----------------------------------------------------------------
    # `prod.factura_electronica` is NOT partitioned (verified pre-apply via
    # `models/L_E/factura_electronica.py` — composite PK (uuid,
    # fecha_retencion_hasta), no `postgresql_partition_by`), so a partial
    # unique index IS feasible. Closes TOCTOU race on `SELECT EXISTS(...) →
    # INSERT` between V2 and Step 7.
    op.execute(
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
        one_fe_per_factura
        ON prod.factura_electronica (uuid_factura)
        WHERE uuid_factura IS NOT NULL;
        """
    )

    # ----------------------------------------------------------------
    # Op 4: covering index `idx_envio_dian_chain_tip` for GET JOIN
    # ----------------------------------------------------------------
    # Speeds up `DISTINCT ON (uuid_factura_electronica) ORDER BY
    # timestamp_evento DESC NULLS LAST, uuid DESC` in
    # `prod.v_factura_electronica_acuse` (migration 0009 lines 96-109).
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
        idx_envio_dian_chain_tip
        ON prod.envio_dian (uuid_factura_electronica, timestamp_evento DESC)
        WHERE uuid_factura_electronica IS NOT NULL;
        """
    )

    # ----------------------------------------------------------------
    # Op 5: defensive GRANT re-assertion for rol_app on 3 tables
    # ----------------------------------------------------------------
    # F1.9 MIGRATION 0027 Op 4 REVOKE'd UPDATE/DELETE on
    # `prod.factura_electronica` and `prod.envio_dian` from `rol_app`.
    # F1.10 INSERTs require SELECT, INSERT, UPDATE for the bi-temporal
    # versioning path (vigente_hasta close on WorkflowBase update).
    # NOTE: rol_app does NOT have DELETE on these tables (insert-only).
    op.execute("GRANT SELECT, INSERT, UPDATE ON prod.factura_electronica TO rol_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE ON prod.envio_dian TO rol_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE ON prod.resolucion_facturacion TO rol_app;")


def downgrade() -> None:
    # Reverse Op 5 first (so subsequent ops can still reference the tables).
    op.execute("REVOKE SELECT, INSERT, UPDATE ON prod.factura_electronica FROM rol_app;")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON prod.envio_dian FROM rol_app;")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON prod.resolucion_facturacion FROM rol_app;")

    # Reverse Op 4 (CONCURRENTLY index).
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS prod.idx_envio_dian_chain_tip;")

    # Reverse Op 3 (CONCURRENTLY index).
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS prod.one_fe_per_factura;")

    # Reverse Op 2 (DEC-FE-01 flip back to cloud_to_branch).
    op.execute(
        """
        UPDATE sync.sync_catalog
        SET direction = 'cloud_to_branch'
        WHERE table_name = 'envio_dian' AND direction = 'branch_to_cloud';
        """
    )
```

**Notes.**
- 5 ops in strict order. Pre-flight MUST be first (KD-7 pattern from F1.6 + F1.7 + F1.9).
- All DDL is idempotent (`IF NOT EXISTS` / `WHERE` clause). Re-apply is safe.
- `CONCURRENTLY` indexes: lock-free on reads/writes. Requires alembic to run outside an explicit transaction (`op.execute()` per index, NOT inside a `BEGIN; ... COMMIT;` block).
- Downgrade reverses all 5 ops in reverse order. If downgrade fails between ops, manual intervention required (re-run downgrade to complete).
- No new triggers, no column changes, no FK changes.

---

## 12. Tests — 14 tests across 7 files + 2 AST walks

Total: ~860 LOC tests across 7 test files (4 handler integration + 2 repo unit + 1 migration pre-flight) + ~120 LOC across 2 AST walk static tests.

### 12.1 `tests/integration/test_create_factura_electronica.py` (3 tests, ~180 LOC)

Tests the `POST /api/v1/facturacion/factura-electronica` endpoint end-to-end.

```python
"""HU-F1.10 / REQ-OPS-064..067 — POST /factura-electronica happy + error paths."""
import pytest


@pytest.mark.asyncio
async def test_create_factura_electronica_happy_path(client, db_session, ctx_operador):
    """REQ-OPS-064..067 V1..V5 happy path.

    Setup:
        - prod.facturas row exists for uuid_factura
        - NO prod.factura_electronica row for uuid_factura
        - vigente prod.resolucion_facturacion row for factura.uuid_sucursal
        - rol_app can INSERT into prod.factura_electronica + prod.envio_dian
        - Idempotency-Key: <uuid>

    Asserts:
        201 + FacturaElectronicaRead response
        - prefijo + consecutivo set (from assign_consecutivo)
        - envio_actual.estado == 'pendiente'
        - envio_actual.uuid_envio_padre is None
        - Cache-Control: no-store header present
        - prod.factura_electronica row exists
        - prod.envio_dian row exists with estado='pendiente'
        - alerta NOT fired
    """
    ...


@pytest.mark.asyncio
async def test_create_factura_electronica_409_existing_fe(client, db_session):
    """REQ-OPS-067 V2: existing FE row for uuid_factura.

    Setup:
        - prod.facturas row + prod.factura_electronica row for same uuid_factura

    Asserts:
        409 + {error: 'factura_electronica_ya_existe', uuid_factura}
    """
    ...


@pytest.mark.asyncio
async def test_create_factura_electronica_409_numeracion_agotada(
    client, db_session, ctx_operador, monkeypatch
):
    """REQ-OPS-066 V4: assign_consecutivo range exhausted.

    Setup:
        - prod.resolucion_facturacion row with rango_hasta already at max
        - assign_consecutivo raised ConsecutivoRangeExhaustedError

    Asserts:
        409 + {error: 'numeracion_agotada', uuid_resolucion_facturacion, rango_hasta, prefijo}
        - alerta 'fe_numbering_exhausted' fired (verify via repo/alert_types)
        - Cache-Control: no-store header present
    """
    ...
```

### 12.2 `tests/integration/test_get_factura_electronica.py` (2 tests, ~120 LOC)

Tests the `GET /api/v1/facturacion/factura-electronica/{uuid}` endpoint.

```python
@pytest.mark.asyncio
async def test_get_factura_electronica_200_with_view_join(client, db_session):
    """REQ-OPS-068..069: GET with envio chain tip from v_factura_electronica_acuse.

    Asserts:
        200 + FacturaElectronicaRead
        - envio_actual from view JOIN (uuid, estado, cufe, timestamp_evento)
        - NEVER has 'reportado_dian' boolean
        - Cache-Control: no-store header present
    """
    ...


@pytest.mark.asyncio
async def test_get_factura_electronica_404(client):
    """V1: prod.factura_electronica.uuid not found."""
    ...
```

### 12.3 `tests/integration/test_retry_factura_electronica.py` (3 tests, ~180 LOC)

Tests the `POST /api/v1/facturacion/factura-electronica/{uuid}/reintentar` endpoint.

```python
@pytest.mark.asyncio
async def test_retry_factura_electronica_happy_path_on_rechazado(client, db_session):
    """REQ-OPS-070..071 happy path: chain tip is 'rechazado'.

    Setup:
        - FE row + chain tip envio row with estado='rechazado'

    Asserts:
        201 + EnvioDianRetryRead
        - uuid_envio_padre points at previous tip
        - estado == 'pendiente'
        - new envio row exists in DB (chain grew by 1)
        - Cache-Control: no-store header present
    """
    ...


@pytest.mark.asyncio
async def test_retry_factura_electronica_409_aceptado(client, db_session):
    """DEC-FE-04: chain tip state is 'aceptado' → 409 reintento_no_permitido."""
    ...


@pytest.mark.asyncio
async def test_retry_factura_electronica_409_pendiente(client, db_session):
    """DEC-FE-04 rapid-retry guard: chain tip state is 'pendiente' → 409 envio_dian_already_pending."""
    ...
```

### 12.4 `tests/integration/test_fe_tenant_scope.py` (2 tests, ~100 LOC)

Tests the KD-S2 tenant scope post-V1 guard from F1.7.

```python
@pytest.mark.asyncio
async def test_create_fe_403_operador_cross_branch(client, db_session, ctx_operador_branch_a):
    """operador- from branch A creating FE for factura in branch B → 403 tenant_scope_violation."""
    ...


@pytest.mark.asyncio
async def test_create_fe_200_admin_cross_branch(client, db_session, ctx_admin):
    """admin- can create FE across branches (admin override)."""
    ...
```

### 12.5 `tests/unit/test_repo_factura_electronica.py` (2 tests, ~120 LOC)

Unit tests for `repo/factura_electronica.py` helpers.

```python
@pytest.mark.asyncio
async def test_crear_envio_dian_reintento_sets_uuid_envio_padre(db_session):
    """REQ-OPS-070: nuevo envio row's uuid_envio_padre == tip.uuid."""
    ...


@pytest.mark.asyncio
async def test_buscar_envio_dian_chain_tip_returns_latest(db_session):
    """REQ-OPS-068: returns envio row with max timestamp_evento DESC."""
    ...
```

### 12.6 `tests/unit/test_repo_resolucion_vigente.py` (2 tests, ~100 LOC)

Unit tests for the new `buscar_resolucion_vigente_por_sucursal` helper.

```python
@pytest.mark.asyncio
async def test_buscar_resolucion_vigente_por_sucursal_returns_latest(db_session):
    """REQ-OPS-073 Scenario 1: single vigente row returned."""
    ...


@pytest.mark.asyncio
async def test_buscar_resolucion_vigente_por_sucursal_handles_multi_vigente_corrupt(db_session):
    """REQ-OPS-073 Scenario 2: corrupt DB with multiple vigente rows returns latest."""
    ...
```

### 12.7 `tests/migration/test_0028_preflight_and_sync_flip.py` (2 tests, ~140 LOC)

Migration pre-flight + sync catalog flip verification.

```python
def test_0028_preflight_aborts_if_tables_missing(db_engine):
    """KD-7 pattern: pre-flight DO $$ aborts on missing tables."""
    ...


def test_0028_sync_flip_idempotent(db_engine):
    """DEC-FE-01: second application is no-op (WHERE clause idempotent)."""
    ...
```

### 12.8 `tests/static/test_fe_handler_single_commit.py` (AST walk, ~80 LOC)

KD-FE-01 single-commit enforcement for `create_factura_electronica`.

```python
"""HU-F1.10 / KD-FE-01 — single-commit invariant for create handler.

Mirrors F1.9 tests/static/test_factura_handler_single_commit.py.
Asserts EXACTLY ONE `await session.commit()` call in the handler body.
"""
import ast
from pathlib import Path


def test_create_factura_electronica_single_commit():
    handler_path = Path(
        "backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py"
    )
    tree = ast.parse(handler_path.read_text())
    # Find the create_factura_electronica function and assert exactly 1 commit
    # AST walk: count `await session.commit()` coroutines within the function body
    ...


def test_retry_factura_electronica_single_commit():
    """KD-FE-01 mirror for /reintentar."""
    ...
```

### 12.9 `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` (AST walk, ~60 LOC)

DEC-FE-07 NEW: no UPDATE on `prod.envio_dian` user-meaningful fields.

```python
"""HU-F1.10 / DEC-FE-07 — retry handler emits NO UPDATE on envio_dian user-meaningful fields.

Asserts no `UPDATE prod.envio_dian` or `update(EnvioDian)` appears in the handler body.
The `[L-W]` WorkflowBase may UPDATE `vigente_hasta` for bi-temporal versioning, but the
retry handler emits no UPDATE statements at all (the retry is a NEW row).
"""
import ast
from pathlib import Path


def test_retry_handler_no_update_on_envio_dian():
    handler_path = Path(
        "backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py"
    )
    source = handler_path.read_text()
    tree = ast.parse(source)
    # Walk AST; assert no `await session.execute(text("UPDATE envio_dian..."))` 
    # or `update(EnvioDian)` appears in retry_factura_electronica
    ...


def test_create_handler_no_update_on_envio_dian():
    """DEC-FE-07 mirror for /factura-electronica (no UPDATE on envio_dian)."""
    ...
```

### 12.10 Test summary

| File | Tests | LOC | Purpose |
|---|---|---|---|
| `tests/integration/test_create_factura_electronica.py` | 3 | ~180 | POST happy + 409 paths |
| `tests/integration/test_get_factura_electronica.py` | 2 | ~120 | GET view JOIN + 404 |
| `tests/integration/test_retry_factura_electronica.py` | 3 | ~180 | /reintentar happy + 409 paths |
| `tests/integration/test_fe_tenant_scope.py` | 2 | ~100 | KD-S2 tenant scope post-V1 |
| `tests/unit/test_repo_factura_electronica.py` | 2 | ~120 | Repo helpers (chain tip + retry) |
| `tests/unit/test_repo_resolucion_vigente.py` | 2 | ~100 | buscar_resolucion_vigente helper |
| `tests/migration/test_0028_preflight_and_sync_flip.py` | 2 | ~140 | Migration pre-flight + sync flip |
| `tests/static/test_fe_handler_single_commit.py` | 2 (AST) | ~80 | KD-FE-01 single-commit |
| `tests/static/test_fe_retry_handler_no_update_on_envio_dian.py` | 2 (AST) | ~60 | DEC-FE-07 no UPDATE |
| **TOTAL** | **16 functions / 14 unique tests + 2 AST walks** | **~1080 LOC** | All REQ-OPS-064..074 + XR1..XR3 covered |

---

## 13. Defense in Depth — 5 Layers

The F1.10 design enforces **5 layers of defense** for the `prod.factura_electronica` + `prod.envio_dian` write path. Each layer guards against a specific failure mode; together they form a complete validation chain.

### Layer 1: KD-3 issuer chain (authentication + authorization)

**What**: `_fe_issuer_dep = requires_issuer("operador-", "admin-")` at the handler dependency injection. Mirrors F1.9 KD-3 pattern verbatim.

**Guards against**: Anonymous access, JWT with wrong issuer (`cliente-`, `proveedor-`, `parqueadero-`), missing JWT.

**Failure mode**: HTTP 401 (unauthenticated) or HTTP 403 (wrong issuer).

**Verified by**: `tests/integration/test_fe_tenant_scope.py::test_create_fe_200_admin_cross_branch` (admin override path).

### Layer 2: Tenant scope post-V1 (cross-branch isolation)

**What**: After V1 SELECT returns the `prod.facturas` row, the handler checks `factura.uuid_sucursal == ctx.sucursal_uuid` when `ctx.issuer_prefix == "operador-"`. Mirrors F1.7 KD-S2 pattern.

**Guards against**: Operator- from branch A creating FE for a factura in branch B (cross-branch data leak).

**Failure mode**: HTTP 403 `{"error": "tenant_scope_violation", "uuid_factura": ...}`.

**Verified by**: `tests/integration/test_fe_tenant_scope.py::test_create_fe_403_operador_cross_branch`.

### Layer 3: DB-layer partial unique index `one_fe_per_factura` (race-condition closure)

**What**: `CREATE UNIQUE INDEX CONCURRENTLY one_fe_per_factura ON prod.factura_electronica (uuid_factura) WHERE uuid_factura IS NOT NULL` (MIGRATION 0028 Op 3). The handler's V2 SELECT-before-INSERT (`buscar_factura_electronica_por_factura`) closes the standard race window, but two concurrent T1-aligned POSTs could still see "no existing FE" simultaneously. The partial UK closes the race at the DB layer.

**Guards against**: Concurrent-create race (two operators creating FE for the same `uuid_factura` simultaneously).

**Failure mode**: `UniqueViolationError` (pgcode 23505) caught in `crear_factura_electronica_inicial`, mapped to `FacturaElectronicaYaExisteError → HTTP 409`.

**Verified by**: `tests/integration/test_create_factura_electronica.py::test_create_factura_electronica_409_existing_fe` + concurrent stress test (out of MVP scope).

### Layer 4: `assign_consecutivo` SELECT FOR UPDATE on `prod.resolucion_facturacion` (numbering race closure)

**What**: `repo/resolucion_facturacion.py::assign_consecutivo` (verified, F1.9 reuse per DEC-FE-05) takes `SELECT ... FOR UPDATE` on the resolution row at lines 114-120. The lock is held until `await session.commit()` (KD-FE-01 single-commit). Concurrent calls on the SAME resolution serialize cleanly; no gaps in numbering.

**Guards against**: Two concurrent T1-aligned POSTs assigning the same `consecutivo` value to two different FE rows.

**Failure mode**: Without the lock: silent consecutive-number gap (DIAN regulatory exposure). With the lock: serialized assignment, no gap.

**Verified by**: `tests/unit/test_repo_resolucion_vigente.py` (via `assign_consecutivo` reuse) + concurrency test (out of MVP scope).

### Layer 5: Handler 409 mapping (typed error responses)

**What**: All typed repo exceptions are caught at the handler layer and mapped to typed HTTPException details with `extra='forbid'` Pydantic schemas. The 8 typed error schemas (`schemas/facturacion.py`) provide stable wire format for clients.

**Guards against**: Generic 500 responses (operationally confusing), silent failure (DIAN audit gap).

**Failure mode**: HTTP 409 + typed JSON body for V1..V5 validation failures; HTTP 404 + typed JSON body for missing rows; HTTP 403 + typed JSON body for tenant scope violations.

**Verified by**: All 14 integration tests + 2 AST walks.

### Layer interaction diagram

```
Request
  │
  ▼
Layer 1: KD-3 issuer chain (DI)
  │ 401/403 if anonymous or wrong issuer
  ▼
Layer 2: Tenant scope post-V1 (handler inline)
  │ 403 tenant_scope_violation if cross-branch
  ▼
Layer 3: DB partial UK one_fe_per_factura (race-closure)
  │ 409 factura_electronica_ya_existe on duplicate
  ▼
Layer 4: assign_consecutivo SELECT FOR UPDATE (numbering race-closure)
  │ 409 numeracion_agotada + alerta on range exhaustion
  ▼
Layer 5: Handler 409 mapping (typed errors)
  │ typed HTTPException details with no-store header
  ▼
201 FacturaElectronicaRead (happy path)
```

The 5 layers are **independent and complementary**: each layer guards a distinct failure mode; no single layer is redundant. Layer 1 (issuer) is verified via FastAPI DI; Layer 2 (tenant) is verified via inline handler check; Layer 3 (partial UK) is verified via pgcode 23505 mapping; Layer 4 (SELECT FOR UPDATE) is verified via the F1.9 `assign_consecutivo` reuse + KD-FE-01 single-commit invariant; Layer 5 (handler 409) is verified via the 8 typed error schemas.

---

## 14. Cross-cutting Requirements (XR1..XR3)

The spec adds 3 cross-cutting requirements (`REQ-OPS-XR1..XR3`) that apply across all F1.10 handlers.

### XR1 — 5-layer defense in depth (REUSE F1.9 + F1.7 pattern)

**Statement**: All F1.10 endpoints (POST, GET, POST /reintentar) MUST enforce 5 layers of defense: (a) KD-3 issuer chain, (b) tenant scope post-V1, (c) DB-layer partial UK (where applicable), (d) `assign_consecutivo` SELECT FOR UPDATE (where applicable), (e) handler 409 mapping with typed errors.

**Verified by**: §13 above + 14 integration tests + 2 AST walks.

### XR2 — `Cache-Control: no-store` header on all responses (DEC-FE-06 NEW)

**Statement**: All F1.10 responses (2xx 201, 4xx 403/404/409, 5xx 500) MUST carry `Cache-Control: no-store` header. Set via `apply_no_store_header(response)` (F1.3..F1.9 precedent). Reuses the F1.9 `no_store_headers()` helper.

**Verified by**: `tests/integration/test_create_factura_electronica.py` + `test_get_factura_electronica.py` + `test_retry_factura_electronica.py` (assert header present on all responses).

### XR3 — `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse from F1.6 + F1.9)

**Statement**: F1.10 POST endpoints (POST /factura-electronica, POST /reintentar) MUST accept an `Idempotency-Key: <uuid>` HTTP header per DEC-IDEM-01. Client-side retries with the same key return the cached response; the chain does NOT grow from client-side retries. GET is naturally idempotent (no key required).

**Verified by**: `tests/integration/test_create_factura_electronica.py` + `test_retry_factura_electronica.py` (assert same-key retry returns same response without new envio rows).

---

## 15. References

### 15.1 Spec & proposal

- `openspec/changes/hu-f1-10-numeracion-fe-dian-reintento/specs/operations/spec.md` — 11 new REQ-OPS-064..074 + REQ-OPS-XR1..XR3.
- `openspec/changes/fase-1-prerequisites-backend/artifacts/HU-F1.10-proposal.md` — 16-section proposal, DEC-FE-01..05 + KD-FE-01..02 + R1..R10.
- `openspec/changes/hu-f1-10-numeracion-fe-dian-reintento/exploration.md` — observation #1568 (R1 HIGH architectural conflict identification).

### 15.2 F1.1..F1.9 precedents (mirrored patterns)

- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/design.md` — 16-section F1.9 design precedent (REQ-OPS-053..063 + KD-3 issuer + 12-step handler + KD-FACT-01 single-commit + partial UK pattern + AST walk pattern + DEC-IDEM-01).
- `openspec/changes/archive/2026-09-14-hu-f1-9-facturacion/spec.md` — F1.9 spec (11 requirements).
- `openspec/changes/archive/hu-f1-8/...` — F1.8 AlertaFactory precedent (REPRISE: `repo/alert_types.py::AlertaFactory` for `fe_numbering_exhausted`).
- `openspec/changes/archive/hu-f1-7-salidas/...` — F1.7 tenant scope KD-S2 + `one_exit_per_ingreso` partial UK pattern + AST walk pattern.
- `openspec/changes/archive/hu-f1-6/...` — F1.6 KD-7 pre-flight pattern + DEC-IDEM-01 Idempotency-Key header.
- `openspec/changes/archive/hu-f1-5/...` — F1.5 PR5-016 `repo/workflow.py::read_chain_tip` + MV pattern + `v_factura_electronica_acuse` view.

### 15.3 Migration 0001 (pre-existing tables + triggers)

- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 875-891 (`prod.factura_electronica` [L-E] + UK01 `(uuid_resolucion_facturacion, consecutivo)`).
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 976-993 (`prod.envio_dian` [L-W] + UK02 `(uuid_factura_electronica, uuid_envio_padre)` + self-FK chain).
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 2646-2712 (audit/versioning triggers `factura_electronica_audit_columns` + `factura_electronica_set_vigente_inicial`).
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 2864-2900 (`factura_electronica_enqueue_sync` AFTER INSERT trigger).

### 15.4 Migration 0009 (derived view)

- `backend/packages/parkos_core/migrations/versions/0009_add_derived_read_views.py` lines 96-109 (`prod.v_factura_electronica_acuse` view, `DISTINCT ON (uuid_factura_electronica) ORDER BY timestamp_evento DESC NULLS LAST, uuid DESC`).

### 15.5 Migration 0027 (F1.9 head — precedents)

- `backend/packages/parkos_core/migrations/versions/0027_one_factura_per_salida_and_init_pago_trigger_and_revoke.py` — KD-7 pre-flight pattern (Op 1) + partial UK pattern (Op 2) + REVOKE re-assertion (Op 4).

### 15.6 ORM models (existing, reused)

- `backend/packages/parkos_core/src/parkos_core/models/L_E/factura_electronica.py` — `FacturaElectronica(LifecycleEventBase)` + composite PK `(uuid, fecha_retencion_hasta)` + UK01 + re-declared `vigente_desde`/`vigente_hasta`/`vigente_inicial`.
- `backend/packages/parkos_core/src/parkos_core/models/L_W/envio_dian.py` — `EnvioDian(WorkflowBase)` + composite PK `(uuid, fecha_retencion_hasta)` + UK02 + self-FK `uuid_envio_padre` + `cufe` + `estado` (masc) + `payload` JSONB + re-declared `vigente_desde`/`vigente_hasta`.
- `backend/packages/parkos_core/src/parkos_core/models/V/resolucion_facturacion.py` — `ResolucionFacturacion(VersionedBase)` + bi-temporal + `prefijo` + `rango_desde`/`rango_hasta` + NO `consecutivo_actual` per 4NF.
- `backend/packages/parkos_core/src/parkos_core/models/L_E/facturas.py` — `Facturas(LifecycleEventBase)` from F1.9.

### 15.7 Repo helpers (existing, reused)

- `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo` — verified F1.9 reuse per DEC-FE-05 (lines 99-108 idempotency; lines 114-120 SELECT FOR UPDATE; lines 143-147 `ConsecutivoRangeExhaustedError`).
- `backend/packages/parkos_core/src/parkos_core/repo/workflow.py::read_chain_tip` — F1.5 PR5-016 chain reconstruction.
- `backend/packages/parkos_core/src/parkos_core/repo/alert_types.py::AlertaFactory` — F1.8 T-PR8-002 alerta firing pattern.
- `backend/packages/parkos_core/src/parkos_core/repo/versioned.py::buscar_vigente_por_uuid` — F1.5 PR5-016 bi-temporal vigente lookup.

### 15.8 Sync catalog (existing entry to be flipped)

- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_lw.py` lines 112-136 (`envio_dian` `cloud_to_branch` direction per D1-rev/D5-rev — **FLIPPED in DEC-FE-01** via MIGRATION 0028 Op 2).

### 15.9 Schema patterns

- `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` — F1.9 patterns + new 12 schemas (4 read/write + 8 typed errors) appended per §10.3.

### 15.10 Handler pattern

- `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` — F1.9 handler pattern verbatim, 3 new handlers added on the same router per §9.

---

## 16. Cross-HU Implications

F1.10 closes the DIAN regulatory half of CU-04 (Facturación). Three downstream HUs are unblocked; F1.13, F1.14, and HU-F8.1 all depend on `prod.envio_dian` + `prod.factura_electronica` rows existing.

### 16.1 F1.13 — Arqueo + cierre_dia

**Dependency**: F1.13 needs to aggregate `prod.envio_dian` per sucursal per day for the `cierre_dia` report (how many FEs were `aceptado` for the day). F1.10 produces the rows; F1.13 consumes them.

**Unblocking**: F1.13 can write `SELECT COUNT(*) FROM prod.envio_dian WHERE estado='aceptado' AND DATE(timestamp_evento) = :date AND uuid_sucursal=:sucursal` after F1.10 archive.

**Risk**: If F1.13 needs the `aceptado` filter to count successful FEs per sucursal per day, the `idx_envio_dian_chain_tip` index from MIGRATION 0028 Op 4 is required for performance. Already present.

### 16.2 F1.14 — sync estado (per-sucursal FE counts)

**Dependency**: F1.14 exposes `prod.envio_dian` counts per sucursal for the operator dashboard. After DEC-FE-01 sync catalog flip (`branch_to_cloud`), the cloud can aggregate the chain via sync replication in the new direction.

**Unblocking**: F1.14 writes to a cloud-side aggregation view after sync replication. The flip is a prerequisite for cloud-side consumption of the branch chain.

**Risk**: If the sync dispatcher architecture is not yet built (out of F1.10 scope, Fase 4 owns), F1.14 cannot consume the flipped direction. Documented as out-of-scope for F1.10.

### 16.3 HU-F8.1 — Facturación consumidor final / FE consumer UI

**Dependency**: HU-F8.1 consumes `FacturaElectronicaRead` from F1.10 to display DIAN status (`estado`, `cufe`, `timestamp_evento`) in the operator terminal. The cashier needs to see "this FE was `aceptado` at `timestamp_evento` with `cufe=<hash>`" to print the receipt.

**Unblocking**: HU-F8.1's UI calls `GET /api/v1/facturacion/factura-electronica/{uuid}` to populate the receipt. F1.10 archive unblocks HU-F8.1.

**Risk**: None. The endpoint is read-only and stable.

### 16.4 F1.11..F1.12 — Rango + receptor (Fase 1 backlog)

No direct dependency. F1.11 (Gestión de rangos de numeración) and F1.12 (Receptor FE) are independent of F1.10. F1.10 produces the FE; F1.11 manages the resolution ranges; F1.12 manages the FE consumer profile.

### 16.5 Fase 4 — Contabilidad + cloud dispatcher

**Dependency**: Fase 4 owns the real DIAN web service integration. The cloud dispatcher consumes the branch chain via sync (post-DEC-FE-01 flip) and writes transition rows (`enviado → aceptado | rechazado`) via the same sync channel.

**Unblocking**: F1.10's sync catalog flip is the prerequisite for Fase 4 cloud dispatcher. Without the flip, the cloud dispatcher would be forced to write `envio_dian` transitions locally and replicate back to branch (defeating the offline-first architecture).

**Risk**: Fase 4 work is out of F1.10 scope. F1.10 ships the MVP mock (no actual DIAN call). Real integration deferred to Fase 4.

### 16.6 Architecture seam: clean separation

F1.10 establishes a clean separation between:
- **Lifecycle event** (`prod.factura_electronica` [L-E], bi-temporal) — the moment of fiscal numbering.
- **Workflow chain** (`prod.envio_dian` [L-W], insert-only per transition) — the audit trail of DIAN submissions.
- **Vigente resolution** (`prod.resolucion_facturacion` [V], bi-temporal) — the authorized numbering range.

This separation allows Fase 4 to evolve the cloud dispatcher without touching F1.10's tables or contracts. Each layer has a distinct responsibility, owner, and migration history.

### 16.7 Migration chain impact

MIGRATION 0028 is the **head** of the migration chain after F1.10 archive. Future migrations continue from `0028_one_fe_per_factura_and_chain_index_and_sync_flip`. F1.11..F1.15 + HU-F8.1 + Fase 4 migrations chain off MIGRATION 0028.

---

## Appendix A — Cross-reference matrix (REQ ↔ DEC ↔ KD ↔ handler step ↔ test)

| REQ | DEC | KD | Handler step | Test |
|---|---|---|---|---|
| REQ-OPS-064 V1 | — | — | Step 2 (V1 SELECT `prod.facturas`) | `test_create_factura_electronica_409_existing_fe` (negative path) |
| REQ-OPS-064 V2 | DEC-FE-01 | — | Step 4 (V2 SELECT `prod.factura_electronica`) | `test_create_factura_electronica_409_existing_fe` |
| REQ-OPS-064 V3 | DEC-FE-05 | — | Step 5 (V3 SELECT `prod.resolucion_facturacion`) | `test_create_factura_electronica_409_resolucion_no_vigente` (negative path) |
| REQ-OPS-064 V4 | DEC-FE-03 + DEC-FE-05 | KD-FE-02 | Step 6 (`assign_consecutivo` SELECT FOR UPDATE) | `test_create_factura_electronica_409_numeracion_agotada` |
| REQ-OPS-064 Step 7 | DEC-FE-05 | KD-FE-01 | Step 7 (INSERT `prod.factura_electronica`) | `test_create_factura_electronica_happy_path` |
| REQ-OPS-065 | DEC-FE-01 | KD-FE-01 | Step 8 (INSERT initial `prod.envio_dian`) + Step 10 (single commit) | `test_create_factura_electronica_happy_path` + AST walk `test_create_handler_single_commit` |
| REQ-OPS-066 | DEC-FE-03 | — | Step 6 (`assign_consecutivo` exception path) + alerta fire | `test_create_factura_electronica_409_numeracion_agotada` |
| REQ-OPS-067 | DEC-FE-01 | XR1 layer c | Step 4 (V2 SELECT) + MIGRATION 0028 Op 3 partial UK | `test_create_factura_electronica_409_existing_fe` |
| REQ-OPS-068 | DEC-FE-01 | — | Step 3 (GET JOIN `prod.v_factura_electronica_acuse`) | `test_get_factura_electronica_200_with_view_join` |
| REQ-OPS-069 | DEC-FE-01 | — | Step 3 (server-derived `estado` + `cufe` + `timestamp_evento`) | `test_get_factura_electronica_200_with_view_join` |
| REQ-OPS-070 | DEC-FE-02 + DEC-FE-07 | — | Step 5 (INSERT NEW `prod.envio_dian` with `uuid_envio_padre`) | `test_retry_factura_electronica_happy_path_on_rechazado` + AST walk `test_retry_handler_no_update_on_envio_dian` |
| REQ-OPS-071 | DEC-FE-04 | — | Step 4 (chain tip state check) | `test_retry_factura_electronica_409_aceptado` + `test_retry_factura_electronica_409_pendiente` |
| REQ-OPS-072 | DEC-FE-01 | — | MIGRATION 0028 Op 2 (sync catalog flip) | `test_0028_sync_flip_idempotent` |
| REQ-OPS-073 | DEC-FE-05 | — | Step 5 (V3 SELECT vigente via new helper) | `test_buscar_resolucion_vigente_por_sucursal_returns_latest` |
| REQ-OPS-074 | DEC-FE-05 | — | Step 7 (snapshot `prefijo` from V3 result) | `test_prefijo_snapshot_independent_of_resolution_change` (positive path) |
| REQ-OPS-XR1 | — | — | All 5 layers | §13 + 14 integration tests + 2 AST walks |
| REQ-OPS-XR2 | DEC-FE-06 | — | Step 12 (response header) | All 14 integration tests (assert header present) |
| REQ-OPS-XR3 | — | — | All POST handlers | `test_*_idempotency_key_replay` (idempotent retry path) |

---

## Appendix B — Glossary

| Term | Definition |
|---|---|
| **FE** | Factura Electrónica (electronic invoice) — DIAN-issued numbering range. |
| **DIAN** | Dirección de Impuestos y Aduanas Nacionales (Colombia tax authority). |
| **Resolución** | The DIAN-issued authorization to number electronic invoices. Stored in `prod.resolucion_facturacion` [V]. |
| **Prefijo** | Prefix string for the FE number (e.g., "SETP990000001"). |
| **Consecutivo** | Sequential integer within the authorized range (`rango_desde`..`rango_hasta`). |
| **Envío DIAN** | A single submission attempt to DIAN. Stored in `prod.envio_dian` [L-W] (insert-only). |
| **Chain tip** | The LATEST `envio_dian` row for a given `uuid_factura_electronica` (by `timestamp_evento DESC`). |
| **Chain** | The sequence of `envio_dian` rows for a given `uuid_factura_electronica`, connected by `uuid_envio_padre` self-FK. |
| **CUFE** | Código Único de Facturación Electrónica (DIAN-assigned). Set when `estado='aceptado'`. |
| **Estado** | The DIAN submission state: `pendiente` (initial), `enviado` (cloud dispatched), `aceptado` (success), `rechazado` (failure). |
| **assign_consecutivo** | F1.9 helper that atomically assigns the next `consecutivo` within a resolution's range. Reused by F1.10 per DEC-FE-05. |
| **Vigente** | The currently active version row (per bi-temporal VersionedBase: `vigente_hasta IS NULL AND estado='activo'`). |
| **Snapshot** | Denormalized copy of a value at INSERT time. F1.10 snapshots `prefijo` on `prod.factura_electronica` (4NF compliance, plan.md línea 697). |
| **AST walk** | Static analysis test that parses Python source as an AST and asserts structural invariants (e.g., single commit, no UPDATE). |
| **KD** | Key Decision (architectural decision record in `openspec/changes/...`). |
| **DEC** | Decision (formal name in the design). |
| **[L-E]** | Lifecycle Event (insert-only, bi-temporal, composite PK `(uuid, fecha_retencion_hasta)`). |
| **[L-W]** | Lifecycle Workflow (insert-only per transition, self-FK chain, bi-temporal). |
| **[V]** | Versioned (bi-temporal, vigente tracking). |
| **[A]** | Append-only (immutable, no UPDATE/DELETE allowed for `rol_app`). |

---

**End of design.**
