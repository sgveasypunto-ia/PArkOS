# PRD: configuracion_tolerancias (T29)

> **SINGLETON** — cash-session tolerances for `arqueo` difference checks (`tolerancia_efectivo`, `tolerancia_datafono`). Versioned via `vigente_desde`/`vigente_hasta` like all `[V]` tables but with UNIQUE partial index enforcing ONE vigente row. The vigente tolerance at the moment of `arqueo` is what matters — NOT the current one if config changed later. Snapshot semantics: the `arqueo` row implicitly captures the vigente UUID.

## Required References

### Canonical files outside this folder
- **Data Model**: [`modelo_datos_er.mmd`](../../../modelo_datos_er.mmd)
- **Project Context**: [`openspec/PROJECT_CONTEXT.md`](../../PROJECT_CONTEXT.md)
- **Testing Capabilities**: [`openspec/TESTING_CAPABILITIES.md`](../../TESTING_CAPABILITIES.md)
- **Stack / Conventions**: [`AGENTS.md`](../../../AGENTS.md)
- **Roadmap**: [`openspec/_meta/roadmap.md`](../roadmap.md)
- **Iteration Plan**: [`openspec/_meta/iteration_plan.md`](../iteration_plan.md)
- **Meta-PRD-00 Scaffold**: [`_meta/00_scaffold.md`](_meta/00_scaffold.md)
- **Meta-PRD-01 Models**: [`_meta/01_models.md`](_meta/01_models.md)
- **Meta-PRD-02 Jobs**: [`_meta/02_jobs_queries.md`](_meta/02_jobs_queries.md)
- **Meta-PRD-03 APIs**: [`_meta/03_apis_queries.md`](_meta/03_apis_queries.md)
- **Use-case generation prompt**: [`_meta/04_use_case_generation_prompt.md`](_meta/04_use_case_generation_prompt.md)

### Shared PRD references (this folder)
- **UUIDv4 Strategy**: [`_shared/uuid-v4-strategy.md`](_shared/uuid-v4-strategy.md)
- **SOLID Principles**: [`_shared/solid-principles.md`](_shared/solid-principles.md) — *rule S: tolerances are policy inputs consulted at arqueo time*
- **CodeGraph Usage**: [`_shared/codegraph-usage.md`](_shared/codegraph-usage.md)
- **Layer Impact Map**: [`_shared/layer-impact-map.md`](_shared/layer-impact-map.md)
- **FK Naming Convention**: [`_shared/fk-naming-convention.md`](_shared/fk-naming-convention.md)
- **Workflow Chains**: [`_shared/workflow-chains.md`](_shared/workflow-chains.md) — *n/a for this `[V]` non-workflow table*
- **References Index**: [`_shared/references.md`](_shared/references.md)

## 1. Metadata
- **Table name**: `prod.configuracion_tolerancias`
- **SQL name**: `configuracion_tolerancias` (with `prod` schema)
- **Enforcement level**: `[V]` projection (singleton via UNIQUE partial index on `vigente_hasta IS NULL`)
- **Retention**: indefinite (singleton)
- **Origin**: F1 (schema, singleton seeded) + IT-2 (admin CRUD)
- **PRD status**: Draft
- **PRD version**: 2.0 (re-do: use cases rewritten with deep cross-table analysis per `04_use_case_generation_prompt.md`; restructured to canonical 12-section format; 4 use cases covering admin set, branch reads in cash-session flow, snapshot-at-arquo semantics, and alerta diferencia_arqueo trigger)
- **Last updated**: 2026-08-31

## 2. UUIDv4 Handling
- See `_shared/uuid-v4-strategy.md`. PK `uuid` server-generated. Singleton: one row only.

## 3. SOLID Atomic Breakdown
- **S**: "one tolerance configuration". Tolerances are policy inputs consulted at `arqueo` time — NOT referenced by FK from `arqueo` (snapshot semantic via `created_at` + vigente lookup).
- **O**: new columns via migration (e.g., adding `tolerancia_efectivo_porcentaje` as a percentage-based alternative).
- **I**: admin CRUD via `api_admin /configuracion-tolerancias`; branch reads own vigente at arqueo time; cloud admin reads cross-branch state for audit.
- **D**: `parkos_core/models/V/configuracion_tolerancias.py` (model); `parkos_core/arqueo/tolerance_resolver.py` (vigente lookup at arqueo time).
- **Atomic**: INSERT (initial seed), UPDATE (archive old + create new with vigente_desde=NOW()).

## 4. FK Map

### Outgoing FKs
| Column | Targets | Cardinality | ON DELETE | Notes |
|---|---|---|---|---|
| NONE | — | — | — | singleton |

### Incoming FKs (read-only, no FK — snapshot semantic)
| Source | Column | Cardinality | Notes |
|---|---|---|---|
| NONE | — | — | `configuracion_tolerancias` is NOT referenced by FK from `arqueo`. The vigente tolerance at the moment of arqueo is what matters (snapshot via `created_at` + vigente lookup). See use case 7.3 for snapshot semantics. |

## 5. Atomic DB Operations

| Op | Allowed? | Mechanism |
|---|---|---|
| INSERT | YES | Singleton seed (one row only — UNIQUE partial index `(vigente_hasta IS NULL)` enforces) |
| UPDATE | YES (archive only) | UPDATE old row sets `vigente_hasta=NOW()`; new row inserted with new UUID. NEVER modify `tolerancia_efectivo` of existing version — compliance. |
| DELETE | NO | Archive via version flow |

**Special rules**:
- Singleton enforced via UNIQUE partial index `(vigente_hasta IS NULL)` — at most one vigente row.
- Versioning is mandatory for compliance. Every tolerance change = new row version + archive old. The `log_transaccional` row records `datos_anteriores` and `datos_nuevos` for probatory integrity.
- The vigente lookup query: `SELECT * FROM configuracion_tolerancias WHERE vigente_hasta IS NULL`. Always returns 1 row (enforced by UNIQUE partial index).
- The vigente-at-arqueo lookup: `SELECT * FROM configuracion_tolerancias WHERE vigente_desde <= $arqueo.created_at AND (vigente_hasta IS NULL OR vigente_hasta > $arqueo.created_at)`. Returns the version that was vigente at the arqueo moment — for retroactive audit.

## 6. CodeGraph Dependencies
- `api_admin/routers/configuracion_tolerancias.py::PATCH /configuracion-tolerancias` (admin only).
- `api_sucursal/routers/configuracion_tolerancias.py::GET /configuracion-tolerancias` (own vigente; used at arqueo time).
- `parkos_core/arqueo/tolerance_resolver.py::vigente(at_datetime)` (single-row lookup).
- `parkos_core/arqueo/diferencia_calculator.py::check_tolerancia(arqueo, tolerancia)` (returns `bool exceeds_tolerance`).
- `web_admin/ConfiguracionToleranciasForm` (singleton form).
- `web_sucursal/CierreCajaForm` (displays vigente tolerance for operator's reference).

## 7. Use Cases enabled by this table

The `configuracion_tolerancias` table is the **singleton that defines cash-session tolerances** (`tolerancia_efectivo`, `tolerancia_datafono`) for the `arqueo` flow at sesion close. Versioned like other `[V]` tables but with UNIQUE partial index enforcing ONE vigente row at any time. The vigente tolerance at the moment of `arqueo` is what matters — if admin later changes the tolerance, the previous arqueo's diferencia-vs-tolerance calculation remains valid (snapshot semantic via created_at + vigente lookup). Use cases below describe admin set, branch reads in cash-session flow, the snapshot-at-arquo semantics, and the `alerta diferencia_arqueo` trigger. **Manual operator input** (no cameras, no OCR, no QR scanners per the system constraint).

### 7.1 Use Case: `uc.tolerancias.admin-set`

Cloud admin sets tolerance values via `web_admin/ConfiguracionToleranciasForm`. Fills `tolerancia_efectivo=5000` (COP), `tolerancia_datafono=10000`. Backend creates a NEW version (archive old with `vigente_hasta=NOW()`, INSERT new with `vigente_desde=NOW()`). Parametrization push delivers the new version to all branches. The UNIQUE partial index on `(vigente_hasta IS NULL)` enforces exactly one vigente row.

**Actor**: admin (cloud)

**Pre-conditions**: admin has `permiso='configurar_tolerancias'`; `tolerancia_efectivo >= 0` and `tolerancia_datafono >= 0`.

**Steps**:
1. Admin opens `web_admin/ConfiguracionTolerancias`, edits `tolerancia_efectivo` and `tolerancia_datafono`.
2. Frontend PATCHes `api_admin /configuracion-tolerancias` (admin- JWT) with `{tolerancia_efectivo=5000, tolerancia_datafono=10000, vigente_desde=NOW()}`.
3. Backend validates `permisos_usuario` for `permiso='configurar_tolerancias'`; rejects 403 if missing.
4. Backend SELECTs the current vigente row with `SELECT FOR UPDATE` (serializes concurrent admin edits).
5. Backend opens TX; SELECT chain anchor from `log_transaccional` for `uuid_sucursal=$admin_primary_branch`.
6. UPDATE current vigente row SET `vigente_hasta=NOW()` (archive old version).
7. INSERT new `configuracion_tolerancias` row (`uuid=server-generated`, `tolerancia_efectivo=5000`, `tolerancia_datafono=10000`, `vigente_desde=NOW()`, `vigente_hasta=NULL`, `estado='activo'`). The UNIQUE partial index enforces singleton.
8. INSERT `log_transaccional` (`accion='tolerancias_actualizadas'`, `tabla_afectada='configuracion_tolerancias'`, `uuid_registro_afectado=$new_uuid`, `uuid_usuario=$admin_uuid`, `uuid_sucursal=$admin_primary_branch`, `datos_anteriores={tolerancia_efectivo: $old, tolerancia_datafono: $old}`, `datos_nuevos={tolerancia_efectivo: 5000, tolerancia_datafono: 10000}`).
9. `queue_processor.enqueue('configuracion_tolerancias', $new_uuid, $new_snapshot)` → parametrization push for all branches within 30s.
10. Also enqueue the archived row.
11. Backend returns `{new_uuid, old_uuid_archived}` to frontend.
12. Branch receives parametrization; UPSERT new row, UPDATE local old row with `vigente_hasta=NOW()`.
13. Next `arqueo` at branch (use case 7.2) uses the new tolerance.
14. Admin UI shows: "Tolerances updated. Effective immediately."

**Tables touched (writes)**: `configuracion_tolerancias` (1 archive UPDATE + 1 INSERT new), `log_transaccional` (1 row), `sync_queue` (2 parametrization items).
**Tables touched (reads)**: `permisos_usuario` (RBAC), `configuracion_tolerancias` (current vigente + FOR UPDATE), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
**FKs traversed**: `configuracion_tolerancias` has NO outgoing FKs. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `configuracion_tolerancias.uuid`.
**Sync behavior**:
- Branch → cloud: NO.
- Cloud → branch: YES — parametrization push delivers new + archived version to all branches within 30s.
- DIAN trigger: NO.
- Hash chain impact: YES — cloud chain extends by 1 row (admin's branch key); each branch chain extends by 1 row on receipt.
**Integration**:
- Reads from: `permisos_usuario` (RBAC), `configuracion_tolerancias` (current state), `log_transaccional` (chain anchor), `usuarios` (admin), `sucursal` (admin primary branch).
- Writes to: `configuracion_tolerancias` (archive + new), `log_transaccional` (audit), `sync_queue` (parametrization).
- Cross-cutting: the UNIQUE partial index `(vigente_hasta IS NULL)` enforces singleton semantics. Unlike multi-row `[V]` tables (e.g., `tarifas_sucursal`), there is exactly ONE vigente `configuracion_tolerancias` row at any time. Branches UPSERT the row locally; the `vigente_hasta IS NULL` filter returns the current vigente row.
- Related: see T43 (`sesion`) and T34 (`arqueo`) for the parent cash-session flow.

### 7.2 Use Case: `uc.tolerancias.branch-reads-on-cierre-caja-arquo`

Operator at the booth closes sesion at end of shift. Opens `CierreCajaForm`, enters `valor_efectivo_reportado` (cash counted) and `valor_datafono_reportado` (card terminal report). Backend computes `diferencia_efectivo = reportado - esperado`, `diferencia_datafono = reportado - esperado`. SELECTs vigente `configuracion_tolerancias`. If `ABS(diferencia_efectivo) > tolerancia_efectivo` OR `ABS(diferencia_datafono) > tolerancia_datafono`: INSERT `alerta tipo_alerta='diferencia_arqueo'` workflow root.

**Actor**: operator (branch)

**Pre-conditions**: branch has parametrized vigente `configuracion_tolerancias` (use case 7.1); operator has an open `sesion` (T43); `factura_pagos` accumulated during the sesion (the "expected" totals).

**Steps**:
1. Operator opens `web_sucursal/CierreCajaForm`. The form pre-fills `valor_inicial_efectivo` (from sesion apertura) and prompts for `valor_efectivo_reportado`, `valor_datafono_reportado`.
2. Operator counts cash in the drawer, types the total into `valor_efectivo_reportado`. Same for datafono (the terminal's daily report).
3. Frontend POSTs `api_sucursal /arqueos` with `{uuid_sesion, valor_efectivo_reportado, valor_datafono_reportado, observaciones}`.
4. Backend SELECTs vigente `configuracion_tolerancias` WHERE `vigente_hasta IS NULL`. Returns the row with `tolerancia_efectivo=$t1, tolerancia_datafono=$t2`.
5. Backend SELECTs `factura_pagos` SUM WHERE `uuid_sucursal=$branch AND uuid_sesion=$sesion_uuid AND medio_pago='efectivo'` (the expected efectivo). Same for `medio_pago='datafono'`.
6. Backend computes:
   - `diferencia_efectivo = valor_efectivo_reportado - valor_efectivo_esperado`
   - `diferencia_datafono = valor_datafono_reportado - valor_datafono_esperado`
7. INSERT `arqueo` row (`uuid=server-generated`, `uuid_sucursal=$branch`, `valor_efectivo_esperado`, `valor_datafono_esperado`, `valor_efectivo_reportado`, `valor_datafono_reportado`, `diferencia_efectivo`, `diferencia_datafono`, `fecha_retencion_hasta=$created_at + 2_years`).
8. **Snapshot semantic**: the `arqueo` row captures the vigente `configuracion_tolerancias.uuid` implicitly via the `created_at` timestamp. Sprint 5 may add explicit `uuid_tolerancia_vigente` column to `arqueo` for clarity. For now: implicit via created_at correlation.
9. Backend opens TX; SELECT chain anchor from `log_transaccional`.
10. INSERT `log_transaccional` (`accion='arqueo_registrado'`, `tabla_afectada='arqueo'`, `uuid_registro_afectado=$arqueo_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `datos_nuevos={diferencia_efectivo, diferencia_datafono, tolerancia_efectivo_vigente: $t1, tolerancia_datafono_vigente: $t2}`).
11. If `ABS(diferencia_efectivo) > tolerancia_efectivo OR ABS(diferencia_datafono) > tolerancia_datafono`: trigger `alerta` (use case 7.4). Otherwise: just log success.
12. UPDATE `sesion` SET `estado='cerrada', timestamp_cierre=NOW()` (with `log_transaccional` for the UPDATE — T43 use case 7.2).
13. `queue_processor.enqueue('arqueo', $uuid, $snapshot)`.
14. Operator UI shows: "Arqueo registrado. Diferencia efectivo: $Y (tolerancia: $t1) → OK / ALERTA".

**Tables touched (writes)**: `arqueo` (1 row), `log_transaccional` (1+ rows for arqueo + sesion close + alerta if applicable), `sesion` (UPDATE), `sync_queue` (1+ items).
**Tables touched (reads)**: `configuracion_tolerancias` (vigente for tolerance check), `sesion` (current sesion), `factura_pagos` (SUM for expected), `log_transaccional` (chain anchor), `usuarios` (operator), `sucursal` (tenant).
**FKs traversed**: `arqueo.uuid_sucursal` → `sucursal.uuid`. `sesion.uuid_sucursal` → `sucursal.uuid`; `sesion.uuid_usuario` → `usuarios.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `arqueo.uuid` (or `sesion.uuid` for the close).
**Sync behavior**:
- Branch → cloud: YES — `arqueo` + `log_transaccional` + `sesion` UPDATE push via `sync_queue` within 30s.
- Cloud → branch: NO (no parametrization impact).
- DIAN trigger: NO (arqueo doesn't trigger DIAN).
- Hash chain impact: YES — branch chain extends by 2-4 rows (arqueo_registrado, sesion_cerrada, alerta_emitida if applicable); cloud chain extends correspondingly.
**Integration**:
- Reads from: `configuracion_tolerancias` (vigente for tolerance), `sesion` (current), `factura_pagos` (SUM for expected), `log_transaccional` (chain anchor), `usuarios`, `sucursal`.
- Writes to: `arqueo` (the cash count), `log_transaccional` (audits), `sesion` (close UPDATE), `sync_queue`.
- Cross-cutting: this is the canonical **cash-session tolerance** flow. The vigente `configuracion_tolerancias` is read at the moment of arqueo; the result (within tolerance or alert) is the cash-session decision.
- Related: see T43 (`sesion`) for the sesion lifecycle; T34 (`arqueo`) for the parent arqueo flow; T41 (`alerta`) for the diferencia_arqueo alert workflow.

### 7.3 Use Case: `uc.tolerancias.snapshot-at-arquo-moment-no-retroactive-effect`

The tolerance that matters for an arqueo is the **vigente at the moment of the arqueo** — NOT the current one if admin later changes the tolerance. This is the snapshot semantic for compliance. Example: Operator closes sesion at 18:00, tolerance vigente at that moment is `tolerancia_efectivo=5000`, diferencia=$4000 (within tolerance, no alert). Admin then changes tolerance to `tolerancia_efectivo=3000` at 19:00. The arqueo from 18:00 is UNAFFECTED — it was within tolerance AT THE TIME; re-evaluating it with the new tolerance (which would now trigger an alert) is incorrect.

**Actor**: system (no actor — semantic invariant)

**Pre-conditions**: an arqueo row exists in `prod.arqueo`; the vigente `configuracion_tolerancias` may have been updated since.

**Steps**:
1. Operator closes sesion at 18:00. SELECT `configuracion_tolerancias` vigente → `tolerancia_efectivo=$5000`.
2. Computes `diferencia_efectivo=$4000`. $4000 < $5000 → no alert. INSERT `arqueo` row.
3. Admin updates `configuracion_tolerancias` at 19:00 → `tolerancia_efectivo=$3000` (archive old, INSERT new).
4. Audit query: "Did the 18:00 arqueo exceed tolerance?" Answer: NO (it was $4000 with tolerance $5000 vigente at that moment).
5. The `arqueo` row's `created_at` timestamp + the implicitly captured `configuracion_tolerancias.uuid` (the one vigente at 18:00) preserve this evidence.
6. If the system were to re-evaluate the 18:00 arqueo with the new $3000 tolerance, it would say ALERT — but that's wrong. The arqueo is historical evidence, not subject to retroactive re-evaluation.
7. The retroactive lookup query: `SELECT * FROM configuracion_tolerancias WHERE vigente_desde <= '2026-01-15T18:00:00' AND (vigente_hasta IS NULL OR vigente_hasta > '2026-01-15T18:00:00')` — returns the version vigente at 18:00. This query is used for audit reports; NOT for retroactive alert generation.

**Tables touched (writes)**: `configuracion_tolerancias` (archive + new from admin update), `log_transaccional` (admin update audit).
**Tables touched (reads)**: `arqueo` (historical record), `configuracion_tolerancias` (current vigente — but the audit query uses the vigente AT ARQUEO TIME, which requires looking up the version vigente at `arqueo.created_at`).
**FKs traversed**: `configuracion_tolerancias` has NO FKs. `arqueo.uuid_sucursal` → `sucursal.uuid`.
**Sync behavior**:
- Branch → cloud: NO (this is a semantic invariant).
- Cloud → branch: YES — parametrization push for the admin's tolerance update.
- DIAN trigger: NO.
- Hash chain impact: YES — each admin update extends the chain; each branch's receipt extends the chain.
**Integration**:
- Reads from: `arqueo` (historical), `configuracion_tolerancias` (vigente at arqueo.created_at — query joins `vigente_desde <= arqueo.created_at AND (vigente_hasta IS NULL OR vigente_hasta > arqueo.created_at)`).
- Writes to: NONE for this use case (the invariant is observational).
- Cross-cutting: this is the **snapshot semantic for compliance** applied to a singleton. Just like `tarifas_sucursal` snapshot preserves the historical tariff, the vigente `configuracion_tolerancias` at the moment of arqueo is the one that governs the diferencia check.
- Related: see T34 (`arqueo`) for the parent flow; T43 (`sesion`) for sesion close. Sprint 5 may add an explicit `uuid_tolerancia_vigente` column to `arqueo` for unambiguous snapshot reference.

### 7.4 Use Case: `uc.tolerancias.alerta-diferencia-arquo-triggered`

When `ABS(diferencia_efectivo) > tolerancia_efectivo` OR `ABS(diferencia_datafono) > tolerancia_datafono` at the arqueo (use case 7.2), the system INSERTs `alerta tipo_alerta='diferencia_arqueo'` workflow chain root. Admin sees the alert in `web_admin/AlertasList` and triages via the workflow chain (`abierta → en_revision → resuelta`). Resolution may include investigating cash mishandling, retraining the operator, or accepting the loss as operational variance.

**Actor**: operator (branch, triggers via arqueo) + admin (cloud, alerted via workflow)

**Pre-conditions**: an arqueo is being registered with `|diferencia| > tolerancia`; `usuarios` has admin role assigned for triage.

**Steps**:
1. (Continues from use case 7.2 step 11) Backend computed `ABS(diferencia_efectivo) > tolerancia_efectivo`. Trigger gate.
2. Backend INSERTs `alerta` workflow chain root (`uuid=server-generated`, `uuid_sucursal=$branch`, `uuid_usuario=$admin_to_notify`, `uuid_arqueo=$arqueo_uuid`, `uuid_alerta_padre=NULL`, `tipo_alerta='diferencia_arqueo'`, `valor_diferencia_efectivo=$diferencia_efectivo`, `valor_diferencia_datafono=$diferencia_datafono`, `estado='abierta'`, `timestamp_evento=NOW()`, `observaciones='arqueo_excede_tolerancia'`).
3. Backend INSERTs `log_transaccional` (`accion='alerta_emitida'`, `tabla_afectada='alerta'`, `uuid_registro_afectado=$alert_uuid`, `uuid_usuario=$operator_uuid`, `uuid_sucursal=$branch`, `uuid_referencia=$arqueo_uuid`).
4. `queue_processor.enqueue('alerta', $uuid, $snapshot)` → parametrization to cloud.
5. Admin sees `alerta tipo_alerta='diferencia_arqueo'` in `web_admin/AlertasList` (red badge).
6. Admin clicks the alert → opens detail view: shows arqueo values, expected vs reported, tolerance vigente at arqueo time, branch info.
7. Admin triages via workflow chain: clicks `En Revisión` → INSERT new `alerta` row with `uuid_alerta_padre=$root, estado='en_revision', uuid_usuario=$admin_uuid`. INSERT `log_transaccional`.
8. Admin investigates (calls operator, reviews CCTV if available — out of system scope). May decide: cash mishandling (issue a correction `factura` or write-off), operator retraining, or accept as variance.
9. Admin clicks `Resuelta` → INSERT new `alerta` row with `uuid_alerta_padre=$en_revision, estado='resuelta', uuid_usuario=$admin_uuid, observaciones='investigated_cash_mishandling_<operator>'`. INSERT `log_transaccional`.
10. The alert workflow chain is complete: 3 rows total (root + en_revision + resuelta).

**Tables touched (writes)**: `alerta` (workflow chain: 1-3 rows), `log_transaccional` (1-3 rows for the chain transitions), `sync_queue` (parametrization).
**Tables touched (reads)**: `configuracion_tolerancias` (vigente for tolerance), `arqueo` (diferencia computation), `usuarios` (operator + admin), `sucursal` (branch), `log_transaccional` (chain anchor).
**FKs traversed**: `alerta.uuid_sucursal` → `sucursal.uuid`; `alerta.uuid_usuario` → `usuarios.uuid` (responsible); `alerta.uuid_arqueo` → `arqueo.uuid` (the originating arqueo); `alerta.uuid_alerta_padre` → `alerta.uuid` (workflow chain self-reference for transitions). `arqueo.uuid_sucursal` → `sucursal.uuid`. `log_transaccional.uuid_usuario` → `usuarios.uuid`; `log_transaccional.uuid_sucursal` → `sucursal.uuid`; `log_transaccional.uuid_registro_afectado` (polymorphic) → `alerta.uuid`; `log_transaccional.uuid_referencia` (polymorphic) → `arqueo.uuid`.
**Sync behavior**:
- Branch → cloud: YES — `alerta` + `log_transaccional` push via `sync_queue` within 30s.
- Cloud → branch: NO (alerts are cloud-admin-tracked; branch sees its own alert in `web_sucursal/AlertasList`).
- DIAN trigger: NO.
- Hash chain impact: YES — branch chain extends by 1-3 rows (alerta + transitions); cloud chain extends correspondingly on receipt.
**Integration**:
- Reads from: `configuracion_tolerancias` (vigente), `arqueo` (diferencia), `usuarios` (operator + admin), `sucursal` (branch), `log_transaccional` (chain anchor).
- Writes to: `alerta` (workflow chain), `log_transaccional` (audits), `sync_queue`.
- Cross-cutting: this is the **canonical cash-session alert**. The `alerta tipo_alerta='diferencia_arqueo'` enum value distinguishes this from other alert types (`cupo_lleno`, `subscripcion_rotacion`, `rango_agotado`, `login_lockout`, `hash_chain_break`, etc.).
- Related: see T41 (`alerta`) for the workflow chain lifecycle; T34 (`arqueo`) for the parent flow.

## 8. Layer-by-Layer Impact
Layers: 1, 6, 7, 10, 11, 13, 14, 24, 31.

## 9. RED Tests
- (RED) Singleton check: second INSERT with `vigente_hasta=NULL` → UNIQUE violation.
- (RED) Admin PATCH `/configuracion-tolerancias` → old row archived, new row vigente.
- (RED) Admin PATCH without `permiso='configurar_tolerancias'` → 403.
- (RED) Branch operator JWT to `api_admin /configuracion-tolerancias` → 401 (admin-only).
- (RED) Vigente lookup at arqueo: returns exactly 1 row.
- (RED) Vigente-at-arqueo lookup: SELECT with `vigente_desde <= arqueo.created_at AND (vigente_hasta IS NULL OR vigente_hasta > arqueo.created_at)` returns the version vigente at that moment.
- (RED) `ABS(diferencia_efectivo) > tolerancia_efectivo` → INSERT `alerta tipo_alerta='diferencia_arqueo'` workflow root.
- (RED) After admin PATCHes the tolerance (new version), historical `arqueo` rows still reference the OLD tolerance (snapshot preserved via created_at correlation).
- (RED) Hash chain: cloud-side `log_transaccional` written for each tolerance change; branch chain extends on parametrization receipt.

## 10. Implementation Tasks
- [x] F1.x Schema + UNIQUE partial index on vigentes.
- [x] F1.x Seed (singleton with defaults: tolerancia_efectivo=5000, tolerancia_datafono=10000).
- [ ] IT-2.x: `api_admin /configuracion-tolerancias` (PATCH, GET).
- [ ] IT-2.x: parametrization push on tolerance change.
- [ ] IT-2.x: `parkos_core/arqueo/tolerance_resolver.py::vigente()` with caching.
- [ ] IT-2.x: `parkos_core/arqueo/diferencia_calculator.py::check_tolerancia()`.
- [ ] IT-2.x: `web_admin/ConfiguracionToleranciasForm`.
- [ ] Sprint 5: add explicit `uuid_tolerancia_vigente` column to `arqueo` for unambiguous snapshot reference.

## 11. Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Tolerance change during sesion | Low | Snapshot at cierre time (vigente at arqueo.created_at is the one that governs) |
| Tolerance set too tight (false positive alerts) | Med | Admin reviews alerta workflow; can accept as variance |
| Tolerance set too loose (missed cash mishandling) | Med | Cross-validate with `factura_pagos` aggregates + manual audit |
| Singleton drift (multiple vigentes from migration bug) | Low | UNIQUE partial index enforces; entrypoint checks on boot |

## 12. Open Questions
- (a) Per-branch tolerance overrides? Out of MVP — single corporate-wide tolerance.
- (b) Time-of-day variations (different tolerance for peak hours)? Sprint 5 — would require a `tolerancias_horario` extension table.
- (c) Percentage-based tolerance (e.g., `tolerancia_efectivo_pct` instead of fixed COP)? Sprint 5 — useful for high-volume branches.
- (d) Auto-unlock of `alerta` after operator's next arqueo is within tolerance? Sprint 5.
- (e) Explicit `uuid_tolerancia_vigente` column in `arqueo`? Recommended for sprint 5 (avoids created_at correlation fragility).