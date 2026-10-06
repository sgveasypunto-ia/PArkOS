# Delta for operations — `backend-ignore-datafono-cierre-arqueos`

## Header

| Field | Value |
|---|---|
| Change | `backend-ignore-datafono-cierre-arqueos` |
| Phase | spec (sdd-spec) |
| Base spec | `openspec/specs/operations/spec.md` (last entry REQ-OPS-190 from F12.1) |
| Gap | Backend still computes / persists / serializes `datafono` on arqueo and cierre; UI already hardcodes `0` in 5 commits prior to `dev` |
| Decision refs | D1 (`mi_turno.total_cobrado_datafono_cop` → preserve as `0`), D2 (`sync apply_row` close path → `None` explicit), D3 (drill-down route `diferencia_datafono` → preserve), D4 (`calcular_esperado_*` signatures → `-> Decimal`), D5 (`es_descuadre_critico` signature → drop datafono params) |
| Compliance guard | No DROP COLUMN; `valor_datafono_*` columns preserved; no migration needed |
| Substrate verified | `schemas/caja.py:349-387`, `api/v1/caja_arqueo.py:355-477,563-570`, `api/v1/caja_sesion.py:95-270`, `repo/arqueo.py:334-435`, `repo/mi_turno.py:156,169`, `sync/motor/apply_row.py:300`, `models/L_W/alerta.py:62` (nullable, no migration) |

## MODIFIED Requirements

### Requirement: REQ-OPS-091 — `POST /api/v1/caja/arqueo` single-commit atomicity

**Source**: HU-F1.13 (KD-ARQUEO-01 + DEC-ARQUEO-01) · **Priority**: CRITICAL · **Previously**: included datafono in alerta condition; new: datafono excluded from alerta condition.

The handler `post_arqueo` MUST execute exactly ONE `await session.commit()` covering: (1) one `prod.arqueo` [A] INSERT — fields restricted to the datafono-ignored column set (no `valor_datafono_*`, no `diferencia_datafono`); (2) N `prod.sesion` UPDATEs on `cierre_dia` via `close_session_with_log`; (3) one conditional `prod.alerta` INSERT via `append_transition` when `|diferencia_efectivo| > tolerancia_efectivo` ONLY (datafono removed from the condition); (4) N+1 `prod.log_transaccional` co-INSERTs. The handler MUST NOT use `session.begin_nested()` or `SAVEPOINT`. Helper functions stay commit-free. On any raise, the TX MUST roll back. The response MUST return `201 Created` with `Cache-Control: no-store`.

#### Scenario: Happy path — datafono-ignored column set persists with no alerta

- **Given** a `cierre_turno` payload with `valor_efectivo_reportado=148000` matching `valor_efectivo_esperado=148000` (sin diferencia)
- **And** any `valor_datafono_reportado` value (or null) in the payload
- **When** the handler Step 12 commits
- **Then** the `prod.arqueo` row MUST contain the canonical columns only — `valor_datafono_esperado`, `valor_datafono_reportado`, `diferencia_datafono` MUST be `NULL` (or the column default, never populated by the handler)
- **And** ZERO `prod.alerta` rows MUST be INSERTed (datafono difference does not gate the alerta decision)
- **And** the response MUST be `201 Created` with `ArqueoReadForHandler` carrying no datafono fields (REQ-OPS-192).

### Requirement: REQ-OPS-093 — Tolerancia evaluated as ABSOLUTE monto on effective only

The handler MUST evaluate `es_descuadre_critico(diferencia_efectivo, tolerancia_efectivo)` by computing `abs(diferencia_efectivo) > tolerancia_efectivo`. The comparison MUST use the **absolute monto on the effective dimension only**; the datafono dimension is excluded from the decision per the F12.1.1 change. The `descuadre_pct` field (computed as `(diferencia_efectivo / esperado_efectivo) * 100` when esperado_efectivo > 0, else `None`) MUST be returned as informational only and MUST NOT participate in the alerta decision.

#### Scenario: `|diferencia_efectivo| < tolerancia` — NO descuadre alerta (datafono ignored)

- **Given** `valor_efectivo_esperado=100000`, `valor_efectivo_reportado=100050`, `tolerancia_efectivo=100`
- **And** any non-zero `diferencia_datafono` (e.g. `valor_datafono_reportado=50000` vs `esperado_datafono=0`)
- **When** the handler invokes `es_descuadre_critico(diferencia_efectivo=50, tolerancia_efectivo=100)`
- **Then** the helper MUST return `False`
- **And** the handler MUST NOT call `insertar_alerta_descuadre_critico` (datafono difference is irrelevant)
- **And** `descuadre_pct` MUST reflect effective only: `0.05` (NOT a sum with datafono).

### Requirement: REQ-OPS-094 — `justificacion` REQUIRED on `cierre_turno`/`cierre_dia` when `diferencia_efectivo != 0`

The handler MUST validate at Step 6: when `tipo_arqueo.codigo in ('cierre_turno','cierre_dia')` AND `diferencia_efectivo != 0` AND `payload.justificacion is None`, raise `HTTPException(400, {"error": "justificacion_requerida"}, headers=no_store_headers())`. The datafono dimension MUST NOT gate the justificacion requirement. For `auditoria` with `diferencia_efectivo != 0`, the request is accepted without justificacion (advertencia only).

#### Scenario: `cierre_turno` + effective diferencia != 0 + justificacion=null → 400

- **Given** `cierre_turno` payload with `valor_efectivo_reportado=148050` (`diferencia_efectivo=50`) and `justificacion=null`
- **And** any value of `valor_datafono_reportado` (e.g. `0`, `99999`, or null — none of which gates this validation)
- **When** Step 6 validates
- **Then** the handler MUST raise `400 justificacion_requerida`
- **And** NO `prod.arqueo` row MUST be INSERTed.

### Requirement: REQ-OPS-095 — `alerta 'descuadre_critico'` INSERTed with effective-only payload

When `es_descuadre_critico == True`, the handler MUST call `insertar_alerta_descuadre_critico` with `diferencia_efectivo=<diff_e>`, `tolerancia_efectivo=<tol_e>`, and `payload_json` containing only the effective fields. The helper MUST NOT accept `diferencia_datafono` / `tolerancia_datafono` as arguments (D5 default). The `append_transition` invocation MUST pass `tipo_alerta='descuadre_critico'`, `severity='critical'`, `uuid_recurso_origen=<uuid_arqueo>`, `tipo_recurso_origen='arqueo'`. The `alerta_generada=true` + `alerta_uuid=<uuid>` MUST appear in the `201 Created` response.

#### Scenario: effective descuadre → alerta via `append_transition` with effective-only payload

- **Given** `|diferencia_efectivo| > tolerancia_efectivo`
- **And** `prod.alert_types` has the row `('descuadre_critico','critical')`
- **When** the handler Step 10 invokes `insertar_alerta_descuadre_critico(...)`
- **Then** the helper MUST call `append_transition(session, tabla='alerta', tipo_alerta='descuadre_critico', ...)` with `payload_json={diferencia_efectivo, tolerancia_efectivo, valor_esperado_efectivo, valor_reportado_efectivo}` ONLY
- **And** the `prod.alerta` row created MUST have `valor_diferencia_datafono = NULL` (no datafono payload, even if historical pre-change rows had it populated)
- **And** the response MUST include `alerta_generada=true` + `alerta_uuid=<uuid>`.

### Requirement: REQ-OPS-097 — `GET /api/v1/caja/arqueo/resumen` returns effective-only JOIN

The handler `get_arqueo_resumen` MUST execute a read query returning one row per `prod.sesion` of the day. Each row MUST compute `valor_efectivo_esperado = sesion.valor_inicial_efectivo + COALESCE((SELECT SUM(valor) FROM prod.factura_pagos WHERE uuid_sesion=sesion.uuid AND medio_pago='efectivo' AND tipo_movimiento='pago'), 0)`. The `valor_datafono_esperado` field MUST NOT be projected in the response (the F12.1.1 change). The query MUST NOT execute any UPDATE/INSERT/DELETE on `prod.factura_pagos` (F1.9 immutability). If a `cierre_dia` arqueo exists for `(uuid_sucursal, fecha)`, it MUST appear at the bottom of the response as an aggregate item.

#### Scenario: Resumen con 1 sesion → 1 item, effective-only

- **Given** a GET `?uuid_sucursal=<:s>&fecha=2026-09-15` with 1 `prod.sesion` `:ses` (timestamp_apertura::date='2026-09-15', `valor_inicial_efectivo=50000`) and 2 `prod.factura_pagos` rows for `:ses` (`medio_pago='efectivo', valor=30000, tipo_movimiento='pago'` and `medio_pago='tarjeta', valor=20000, tipo_movimiento='pago'`)
- **When** the handler executes the read query
- **Then** the response MUST include exactly 1 `ArqueoResumenItem` for `:ses` with `valor_efectivo_esperado = 50000 + 30000 = 80000`
- **And** the item MUST NOT include `valor_datafono_esperado` (the field is dropped from the response shape per REQ-OPS-192).

## ADDED Requirements

### Requirement: REQ-OPS-191 — `ArqueoCreateV2.valor_datafono_reportado` accepts `null` and `Decimal` (backward-compat)

The Pydantic schema `ArqueoCreateV2` MUST declare `valor_datafono_reportado: Decimal | None = None` (previously required). The handler MUST accept the field as `None` (or any `Decimal`, ignored) without raising. Clients that omit the field (new build) MUST pass validation; clients that send a `Decimal` (legacy kiosk) MUST pass validation; clients that send `null` MUST pass validation. The handler MUST NOT use the value in any computation, alert decision, or persistence column beyond the historical `prod.arqueo.valor_datafono_reportado` column (which the handler continues to leave at the column default / `NULL`).

#### Scenario: legacy client sends `valor_datafono_reportado: 100000` → 201

- **Given** an `ArqueoCreateV2` payload with `valor_datafono_reportado=100000` and effective field set
- **When** the handler validates the body
- **Then** the request MUST pass schema validation
- **And** the response MUST be `201 Created` with no datafono fields in the body (REQ-OPS-192)
- **And** the `prod.arqueo.valor_datafono_reportado` column MUST be the column default (the handler does not propagate the wire value).

#### Scenario: new client omits the field → 201

- **Given** an `ArqueoCreateV2` payload without `valor_datafono_reportado` (omitted)
- **When** the handler validates the body
- **Then** the request MUST pass schema validation (`None` default applied).

### Requirement: REQ-OPS-192 — `ArqueoReadForHandler` and `ArqueoDiferenciasResponse` exclude datafono fields

The response schemas `ArqueoReadForHandler` and `ArqueoDiferenciasResponse` MUST NOT include the fields `valor_datafono_esperado`, `valor_datafono_reportado`, `diferencia_datafono`. (Previously these fields appeared with `Decimal` types — they are REMOVED from the wire shape, not made nullable.) Compliance: the corresponding `prod.arqueo` columns remain in the DB (no DROP), but the handler response and the cierre GET projections MUST NOT expose them.

#### Scenario: `ArqueoReadForHandler` happy path has no datafono fields

- **Given** a successful `POST /api/v1/caja/arqueo`
- **When** the response is rendered
- **Then** the body MUST NOT contain `valor_datafono_esperado`, `valor_datafono_reportado`, or `diferencia_datafono`
- **And** the `descuadre_pct` field, if present, MUST reflect effective only.

#### Scenario: `ArqueoDiferenciasResponse` has no datafono fields

- **Given** a `GET /api/v1/caja-sesion/arqueo/diferencias` (or equivalent close-summary endpoint)
- **When** the response is rendered
- **Then** the body MUST NOT contain `valor_datafono_esperado`, `valor_datafono_reportado`, or `diferencia_datafono`.

### Requirement: REQ-OPS-193 — `cierre_dia` path applies the datafono-ignored contract to the aggregate

The `cierre_dia` handler (the second handler in `api/v1/caja_arqueo.py` for the `cierre_dia` aggregate path) MUST compute `diferencia_efectivo` only. The `requiere_justificacion` gate MUST be `diferencia_efectivo != 0` (datafono removed). The `INSERT` into `prod.arqueo` for the `cierre_dia` row MUST follow the same effective-only column set as the arqueo-parcial path (REQ-OPS-191). The `es_descuadre_critico` call MUST be the effective-only signature (REQ-OPS-193 modified, REQ-OPS-195 added).

#### Scenario: `cierre_dia` with aggregate descuadre only on effective

- **Given** a `cierre_dia` payload where `sum(diferencia_efectivo)=1500 > tolerancia_efectivo` and `sum(diferencia_datafono)=0`
- **When** the handler executes
- **Then** the handler MUST generate ONE `alerta 'descuadre_critico'` for the effective aggregate
- **And** the response MUST NOT include any datafono field (REQ-OPS-192).

### Requirement: REQ-OPS-194 — `calcular_esperado_sesion` and `calcular_esperado_cierre_dia` return only effective (`-> Decimal`)

The repository helpers `calcular_esperado_sesion(session, ...)` and `calcular_esperado_cierre_dia(session, ...)` MUST return a single `Decimal` (the expected efectivo total) instead of the previous tuple `(esperado_efectivo, esperado_datafono)`. (D4 default; previously returned tuple, now reduced.) The `Decimal` value MUST equal `valor_inicial_efectivo + sum(factura_pagos WHERE medio_pago='efectivo' AND tipo_movimiento='pago')` for the open sesion (parcial) or aggregated for the day (cierre_dia). Call sites in `caja_arqueo.py` (both handlers) MUST be updated to receive a single `Decimal` and MUST NOT unpack a tuple.

#### Scenario: `calcular_esperado_sesion` returns single Decimal

- **Given** a sesion with `valor_inicial_efectivo=50000` and `factura_pagos` totaling 30000 efectivo
- **When** the handler calls `esperado = calcular_esperado_sesion(...)`
- **Then** `esperado` MUST be `Decimal('80000.00')` (a single value, not a tuple)
- **And** the handler MUST compute `diferencia_efectivo = valor_efectivo_reportado - esperado`.

### Requirement: REQ-OPS-195 — `es_descuadre_critico` signature drops datafono parameters

The repository helper `es_descuadre_critico(diferencia_efectivo, tolerancia_efectivo)` MUST return `bool` (the previous signature took `diferencia_datafono` and `tolerancia_datafono`; D5 default; those parameters are removed). The function MUST compute `abs(diferencia_efectivo) > tolerancia_efectivo` (strict `>` per F1.13 contract preserved). Call sites MUST pass only the two effective parameters; any caller that previously passed datafono parameters MUST be updated in the same change.

#### Scenario: effective-only descuadre evaluation

- **Given** `diferencia_efectivo=150`, `tolerancia_efectivo=100`
- **When** the handler calls `es_descuadre_critico(150, 100)`
- **Then** the helper MUST return `True` (abs(150) > 100)
- **And** the handler MUST proceed to `insertar_alerta_descuadre_critico` (REQ-OPS-095 modified).

#### Scenario: boundary value `|diferencia| == tolerancia` returns `False` (effective-only)

- **Given** `diferencia_efectivo=100`, `tolerancia_efectivo=100`
- **When** the handler calls `es_descuadre_critico(100, 100)`
- **Then** the helper MUST return `False` (strict `>` boundary, not `>=`).

### Requirement: REQ-OPS-196 — No new `diferencia_datafono` alertas are emitted; historical alertas remain visible

The system MUST NOT emit any new `prod.alerta` row whose decision was driven by the datafono dimension alone. Specifically: a sesion with `|diferencia_efectivo| <= tolerancia_efectivo` MUST NOT produce an `alerta 'descuadre_critico'` even when `|diferencia_datafono|` would have exceeded `tolerancia_datafono` under the pre-change contract. (Previously, a descuadre exclusively on datafono could trigger an alerta — that pathway is closed.) Historical `prod.alerta` rows with `valor_diferencia_datafono != 0` MUST remain in the table (the change is forward-only, no DELETE), and the bitácora MUST continue to surface them in the alerts list.

#### Scenario: descuadre only on datafono → NO alerta generated

- **Given** a sesion with `diferencia_efectivo=0` and `diferencia_datafono=500` (> tolerancia_datafono, pre-change threshold)
- **When** the handler completes a successful `POST /api/v1/caja/arqueo`
- **Then** ZERO `prod.alerta` rows MUST be created (the datafono-only descuadre is no longer alerta-worthy)
- **And** the response MUST be `201 Created` with `alerta_generada=false`, `alerta_uuid=null`.

#### Scenario: pre-existing datafono alertas remain visible in the bitácora

- **Given** a `prod.alerta` row with `valor_diferencia_datafono != 0` and `created_at < '2026-10-06'` (the change's commit date)
- **When** an admin reads the alerts list
- **Then** the row MUST appear in the response (no DELETE, no soft-delete; audit-first / append-only).

### Requirement: REQ-OPS-197 — `MiTurnoRead.total_cobrado_datafono_cop` returns `0` (D1 default)

The repository helper `calcular_resumen_mi_turno` MUST return `total_cobrado_datafono_cop: Decimal = 0` for every sesion, regardless of historical `factura_pagos` rows with `medio_pago IN ('tarjeta','datafono')`. (D1 default: preserve the field in the response shape for backward-compat with clients reading the field; the value is `0` because the operator no longer sees or types the datafono in the cierre.) The `MiTurnoRead` schema MUST keep the field `total_cobrado_datafono_cop: Decimal` (NOT removed) so external consumers that read the field continue to deserialize successfully. The `MedioPago` breakdown tuple in the helper MUST NOT include `'datafono'` (only `'efectivo'`); the datafono sum is forced to `0`.

#### Scenario: mi-turno with historical datafono payments returns `0`

- **Given** a sesion X with `factura_pagos` totaling 50000 efectivo + 30000 tarjeta (datafono medio)
- **When** the handler returns `MiTurnoRead`
- **Then** the response MUST include `total_cobrado_efectivo_cop=50000` AND `total_cobrado_datafono_cop=0`
- **And** the datafono total is `0` regardless of the historical `factura_pagos` aggregate.

#### Scenario: mi-turno zero state remains `0`

- **Given** a sesion with no `factura_pagos` rows
- **When** the handler returns `MiTurnoRead`
- **Then** `total_cobrado_datafono_cop` MUST be `0` (same as before, no change in the zero path).

### Requirement: REQ-OPS-198 — Sync `apply_row` close path passes `valor_final_datafono=None` (D2 default)

The sync motor's `apply_row(spec, payload, ...)` for `apply_strategy='session_cycle'` close path MUST invoke `repo.session_cycle.close_session_with_log(..., valor_final_datafono=None)` explicitly. (D2 default: explicit `None`, defense against future positional-arg signatures; semantically documents that the datafono dimension is not part of the close-wire.) The `apply_row` MUST NOT read `payload.get('valor_final_datafono')` to populate the argument — the close-time datafono is dropped at the sync layer, consistent with the API handler behavior (REQ-OPS-191).

#### Scenario: replicated close payload with `valor_final_datafono` key → stripped

- **Given** a sync `apply_row` invocation for the `session_cycle` close path with a payload containing `valor_final_datafono=50000`
- **When** the motor dispatches to `close_session_with_log`
- **Then** the helper MUST be called with `valor_final_datafono=None` (the wire value is dropped at the sync boundary, not propagated)
- **And** `prod.sesion.valor_final_datafono` MUST be the column default (`0` / `NULL`) — the persisted value does not reflect the wire value.

### Requirement: REQ-OPS-199 — Drill-down route for `diferencia_datafono` preserved for historical alertas (D3 default)

The frontend drill-down router entry keyed on the alert-type discriminator `diferencia_datafono` MUST remain in the route map (`apps/electron-sucursal/src/lib/alertas/router.ts:44` per F12.1.1 verification). The route MUST be reachable for any `prod.alerta` row with `valor_diferencia_datafono != 0` that pre-dates the change. New alerta emissions (post-change) MUST NOT route to this entry because the alert type is no longer emitted (REQ-OPS-196). The route preservation is a zero-cost change — the entry is unused by new flows but is required so that historical alertas remain resolvable in the bitácora UI.

#### Scenario: historical datafono alerta still routes to its drill-down

- **Given** a `prod.alerta` row with `tipo_alerta='descuadre_critico'`, `valor_diferencia_datafono != 0`, and `created_at < '2026-10-06'`
- **When** the admin opens the alerta in the bitácora and clicks the row
- **Then** the router MUST navigate to the drill-down view (route preserved verbatim)
- **And** the drill-down view MUST render the historical datafono value as it was at the time of the alerta.

## Cross-References

- `backend/packages/parkos_core/src/parkos_core/schemas/caja.py::ArqueoCreateV2` (line 349-365, `valor_datafono_reportado: Decimal | None = None`)
- `backend/packages/parkos_core/src/parkos_core/schemas/caja.py::ArqueoReadForHandler` (line 368-387, drop datafono fields)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py::post_arqueo` (line 355-477, effective-only INSERT + alerta)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_arqueo.py` cierre_dia handler (line 563-570)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py::ArqueoDiferenciasResponse` (line 104-119, drop datafono fields)
- `backend/packages/parkos_core/src/parkos_core/api/v1/caja_sesion.py` close handler (line 212, 247-270, `valor_final_datafono=None` passed)
- `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::calcular_esperado_sesion` (line 334-369, `-> Decimal`)
- `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::calcular_esperado_cierre_dia` (line 372-399, `-> Decimal`)
- `backend/packages/parkos_core/src/parkos_core/repo/arqueo.py::es_descuadre_critico` (line 417-435, drop datafono params)
- `backend/packages/parkos_core/src/parkos_core/repo/mi_turno.py` (line 156, 169, `total_cobrado_datafono_cop=0`)
- `backend/packages/parkos_core/src/parkos_core/sync/motor/apply_row.py` (line 300, `valor_final_datafono=None` explicit)
- `backend/packages/parkos_core/src/parkos_core/schemas/workflows.py::AlertaCreate`/`AlertaRead`/`AlertaUpdate` (line 348, 374, 392, drop datafono)
- `apps/electron-sucursal/src/lib/alertas/router.ts:44` (drill-down route preserved)

## Compliance & Invariants

- **AUDIT-FIRST (3 levels)**: ORM columns preserved (nullable already verified at `models/L_W/alerta.py:62`); Pydantic wire is nullable input / removed output; logic drops datafono from decisions. All three layers honored.
- **No DELETE**: no physical DELETE; `prod.alerta` and `prod.arqueo` rows are append-only.
- **No migration**: `valor_datafono_*` columns and `tolerancia_datafono` column are preserved on disk; the change is forward-only.
- **C/Q/U API contract**: no DELETE endpoint introduced; the input becomes nullable, the output reduces.
- **`check_schema_match.py` (h) gate**: must remain green — the 49-table schema and the 8 `pg_partman` parents are unaffected.

## Test Pinning (forward reference for sdd-tasks)

- `backend/tests/unit/test_arqueo_repo.py::test_calcular_esperado_sesion_returns_decimal_only` (covers REQ-OPS-194)
- `backend/tests/unit/test_arqueo_repo.py::test_es_descuadre_critico_drops_datafono_params` (covers REQ-OPS-195)
- `backend/tests/integration/test_caja_arqueo.py::test_arqueo_create_v2_accepts_null_datafono` (covers REQ-OPS-191)
- `backend/tests/integration/test_caja_arqueo.py::test_arqueo_create_v2_accepts_legacy_datafono_decimal` (covers REQ-OPS-191 backward-compat)
- `backend/tests/integration/test_caja_arqueo.py::test_arqueo_read_for_handler_excludes_datafono_fields` (covers REQ-OPS-192)
- `backend/tests/integration/test_caja_arqueo.py::test_arqueo_insert_excludes_datafono_columns` (covers REQ-OPS-091 modified)
- `backend/tests/integration/test_caja_arqueo.py::test_datafono_only_descuadre_does_not_emit_alerta` (covers REQ-OPS-196)
- `backend/tests/integration/test_caja_arqueo.py::test_historical_datafono_alerta_remain_visible` (covers REQ-OPS-196)
- `backend/tests/integration/test_caja_cierre.py::test_cierre_dia_aggregate_effective_only` (covers REQ-OPS-193)
- `backend/tests/integration/test_caja_sesion.py::test_arqueo_diferencias_response_excludes_datafono` (covers REQ-OPS-192)
- `backend/tests/integration/test_mi_turno.py::test_total_cobrado_datafono_cop_is_zero` (covers REQ-OPS-197)
- `backend/tests/integration/test_sync_apply_row.py::test_session_cycle_close_passes_datafono_none` (covers REQ-OPS-198)
- `apps/electron-sucursal/src/lib/alertas/router.test.ts::test_diferencia_datafono_route_preserved` (covers REQ-OPS-199)
