# Delta Spec — Operations (ingresos sin placa: bici / patineta)

> **Change**: `ingreso-multi-tipo-consecutivo`
> **Phase**: spec (sdd-spec)
> **Status**: ready-for-sdd-design
> **Date**: 2026-09-22
> **Author**: Parkos Dev <dev@parkos.local>
> **Base spec**: `openspec/specs/operations/spec.md` (canonical, last REQ-OPS = 190)
> **Delta scope**: 8 ADDED requirements (REQ-OPS-191..198) + 1 MODIFIED requirement (REQ-OPS-040 V8 skip for no-placa)
> **Numeración verificada**: operations spec ya ocupa REQ-OPS-001..190; el proposal propuso 143..150 pero esos están tomados por F1.8 Cotización (HU-F1.8, lines 5827..6068) y F11.2/F12.1 alerts. Se reasignó a **191..198** manteniendo la monotonicidad.

## 1. Motivation

The operator's `POST /operacion/ingresos` flow today accepts only `carro` and `moto`, identified by regex. Bicycles and patinetas — already seeded in `prod.tipos_vehiculo` and `prod.cantidad_vehiculos_sucursal` via commit `281bb66` to `dev` — have no registration path: they enter informally, with no audit trail, no cupo enforcement, and no visible identification on the tiquete. The MV `mv_ocupacion_diaria` (REQ-OPS-032..033) already counts these vehicles by `(uuid_sucursal, uuid_tipo_vehiculo)`; the catalog is ready; the cupos are seeded. **Only the entry point is missing.** Without this change, the seeded catalog work is dead weight and REQ-OPS-133 (cupo enforcement) is violated silently for bici/patineta.

This delta closes the loop. The operator picks between two side-by-side buttons (`Con placa` default + `Sin placa` secondary) on `Principal.tsx` and `IngresoPanel.tsx`. The `Sin placa` flow triggers a parallel backend path that generates a per-`(uuid_sucursal, uuid_tipo_vehiculo)` monotonic `consecutivo` in format `<TIPO>-NNNNNN-<uuid8>` (e.g. `BICI-000001-3f8a1b2c`), substitutes it for `placa` in the tiquete (`Identificación:` label), and routes through the existing V1+V2+V3+V4+V5+V9 chain — the chain already supports `uuid_tipo_vehiculo` independently of placa (REQ-OPS-134 short-circuit).

Multi-tenant isolation is preserved by scoping the counter to `(uuid_sucursal, uuid_tipo_vehiculo)`; two branches can both have `BICI-000001-...` without collision. Audit-first is preserved because `assign_ingreso_consecutivo` is consumed inside the existing `repo.event.record_event` flow — `consecutivo` flows into `log_transaccional.datos_nuevos` automatically and the SHA256 hash chain continues unbroken. **DEC-INCOME-01** (locked in proposal §4) explicitly names the column `prod.ingreso.consecutivo` as the parking-lot identifier for bici/patineta to avoid confusion with DIAN invoice numbering (`prod.factura_electronica.consecutivo`, a separate concern with different UK, format, and lifecycle).

## 2. ADDED Requirements

### REQ-OPS-191 — Server-side `consecutivo` assignment for no-placa ingresos

The backend MUST assign a `consecutivo` for every ingreso where `payload.placa is None` AND `uuid_tipo_vehiculo` corresponds to a catalog tipo without placa requirement (`bicicleta`, `patineta`). The `consecutivo` MUST be a string of the form `<TIPO>-NNNNNN-<uuid8>`:
- `TIPO` = `TiposVehiculo.tipo.upper()` (e.g. `BICI`, `PATIN`)
- `NNNNNN` = 6-digit zero-padded integer, monotonic per `(uuid_sucursal, uuid_tipo_vehiculo)`
- `<uuid8>` = first 8 hex chars of `Ingreso.uuid` (= `source_event_uuid.hex[:8]`)

The backend MUST compute and persist `consecutivo` at INSERT time only; no UPDATE path exists (AST lock per `tests/static/test_no_write_after_insert.py`).

**Rationale**: substitutes the placa as the operator-facing identifier. `<uuid8>` gives every row a stable suffix that survives replication (cloud preserves the branch-assigned value verbatim per `cloud-edge-sync-architecture` + DEC-SUC-28). The 6-digit zero-padded format handles up to 999,999 ingresos per `(sucursal, tipo)` — well beyond any realistic single-branch scale.

#### Scenario: primer ingreso sin placa para una sucursal+tipo
- **Given** `(D2049f2, bicicleta)` has no prior ingreso
- **When** the operator POSTs `{placa_presente: false, uuid_tipo_vehiculo: <uuid bicicleta>}`
- **Then** the backend MUST persist the row with `consecutivo = "BICI-000001-3f8a1b2c"` (where `3f8a1b2c` = the row's `uuid.hex[:8]`)
- **And** the 201 response body MUST include `consecutivo` (REQ-OPS-194 variant).

#### Scenario: ingresos consecutivos son monotónicos
- **Given** the previous scenario's row exists
- **When** the operator POSTs a second no-placa ingreso for the same `(sucursal, tipo)`
- **Then** `consecutivo = "BICI-000002-<uuid8>"` (zero-padded 6 digits, monotonically increasing).

#### Scenario: namespaces independientes por tipo y por sucursal
- **Given** `(D2049f2, bicicleta)` counter=5, `(D-other, bicicleta)` counter=100, `(D2049f2, patineta)` counter=3
- **When** three POSTs fire (one per pair)
- **Then** the three `consecutivo` values are `BICI-000006-...`, `BICI-000101-...`, `PATIN-000004-...` respectively (no cross-collision).

**Verification**: `backend/tests/unit/test_repo_ingreso_consecutivo.py::test_consecutivo_monotonic_per_sucursal_tipo` + `test_consecutivo_format_<TIPO>_NNNNNN_<uuid8>`.
**Cross-refs**: `assign_consecutivo` precedent (`backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py:47-183`, T-PR9-002); `modelo_datos_er.mmd` lines 577-596 (canonical `[L-E] ingreso` shape).

---

### REQ-OPS-192 — Columna `consecutivo` en `prod.ingreso` (nullable, INSERT-only)

`prod.ingreso` MUST expose a new column `consecutivo: VARCHAR(20) NULL`. The column MUST NOT be UPDATEd after INSERT. A partial unique index `CREATE UNIQUE INDEX uq_ingreso_consecutivo ON prod.ingreso(uuid_sucursal, uuid_tipo_vehiculo, consecutivo) WHERE consecutivo IS NOT NULL` MUST reject duplicate `consecutivo` values within a `(sucursal, tipo)` namespace — defense in depth on top of REQ-OPS-191.

**Rationale**: nullable so existing carro/moto rows (pre-change) stay `consecutivo = NULL` without breaking. Partial UK only applies to NOT NULL — legacy rows unaffected. Backward-compatible with F6.1 schema (no wire-shape break for clients that don't read `consecutivo`).

#### Scenario: fila carro/moto existente conserva `consecutivo=NULL`
- **Given** `prod.ingreso` already has a row `(uuid_sucursal=X, placa=ABC123)` inserted before this migration
- **When** migration `0042_add_consecutivo_to_ingreso` runs
- **Then** the existing row MUST have `consecutivo = NULL`
- **And** `SELECT * FROM prod.ingreso WHERE uuid = <existing_uuid>` MUST return `consecutivo = NULL`.

#### Scenario: INSERT con `consecutivo` duplicado en el mismo namespace revienta con 23505
- **Given** `(X, bicicleta)` already has `consecutivo = "BICI-000001-3f8a1b2c"`
- **When** an INSERT attempts `consecutivo = "BICI-000001-aabbccdd"` for the same `(X, bicicleta)`
- **Then** the INSERT MUST fail with PostgreSQL error `23505 unique_violation`.

**Verification**: migration `0042_add_consecutivo_to_ingreso.py` (ADD COLUMN + partial UK; pre-flight `alembic upgrade --sql` per `config.yaml rules.tasks`).
**Cross-refs**: AGENTS.md §Architectural Principles §1 (audit-first, bi-temporal, no physical DELETE); precedent `0037_add_uuid_subscripcion_cliente_to_facturas.py`.

---

### REQ-OPS-193 — Counter table `[A]` `prod.ingreso_consecutivo_contador` con REVOKE + trigger

A new `[A]` table `prod.ingreso_consecutivo_contador` MUST maintain `ultimo_consecutivo` per `(uuid_sucursal, uuid_tipo_vehiculo)`. Schema: `(uuid, uuid_sucursal, uuid_tipo_vehiculo, ultimo_consecutivo INT, last_event_uuid UUID, sync_status, created_at, created_by, fecha_retencion_hasta)`.

The migration MUST include in the SAME script (per `config.yaml rules.tasks`):
1. `REVOKE UPDATE, DELETE ON prod.ingreso_consecutivo_contador FROM rol_app`
2. A `BEFORE UPDATE OR DELETE` trigger that raises an exception outside the carve-out columns (`ultimo_consecutivo`, `last_event_uuid`) — these two columns ARE updatable by `rol_app` to advance the counter
3. `fecha_retencion_hasta` with 5-year retention (DIAN compliance per `openspec/config.yaml`)
4. Sync trigger exclusion `WHEN (TG_TABLE_NAME <> 'ingreso_consecutivo_contador')` to avoid recursion per AGENTS.md precedent for `sync_queue`

**Rationale**: the `[A]` audit-first treatment (REVOKE + trigger) is non-negotiable per AGENTS.md §1. A new `[A]` table is the cost of pure-Python `SELECT FOR UPDATE` semantics; the alternative (`MAX+1` inline in handler) has a known race condition between concurrent kiosko POSTs (rejected as Approach A3 in exploration §Approaches).

#### Scenario: REVOKE bloquea UPDATE desde `rol_app` excepto en columnas carve-out
- **Given** `rol_app` has `SELECT, INSERT` on `prod.ingreso_consecutivo_contador` but not `UPDATE`
- **When** a backend connection as `rol_app` runs `UPDATE prod.ingreso_consecutivo_contador SET uuid_tipo_vehiculo = '...' WHERE uuid = ...`
- **Then** the UPDATE MUST fail with insufficient privilege.

#### Scenario: 10 POSTs concurrentes al mismo namespace producen 10 consecutivos distintos
- **Given** `(X, bicicleta)` has no counter row yet
- **When** 10 concurrent POSTs fire via `asyncio.gather` for the same `(X, bicicleta)`
- **Then** the 10 returned `consecutivo` values MUST all be distinct and `000001..000010` (no collision, no gap).

**Verification**: `backend/tests/unit/test_repo_ingreso_consecutivo.py::test_concurrent_lock_serializes_assignment` + `backend/tests/integration/test_consecutivo_concurrent_posts.py::test_10_concurrent_posts_no_collision` (asyncio.gather). Migration verifies REVOKE + trigger via `infra/docker/entrypoint.sh::pg_trigger_check` at boot.
**Cross-refs**: precedent `prod.idempotency_keys` (50th table, same mitigation pattern); `assign_consecutivo` for `factura_electronica` precedent.

---

### REQ-OPS-194 — Discriminated-union Zod en `POST /api/v1/operacion/ingresos`

The frontend MUST send `POST /api/v1/operacion/ingresos` with a discriminated-union payload keyed on `placa_presente: boolean`:
- Variant `true`: `{placa_presente: z.literal(true), placa: <regex>, uuid_tipo_vehiculo?: uuid, ...}` (existing F6.1 shape)
- Variant `false`: `{placa_presente: z.literal(false), uuid_tipo_vehiculo: uuid, ...}` (new no-placa shape)

The Zod schema MUST reject mixed payloads (e.g. `placa_presente: true, placa: null` or `placa_presente: false, placa: 'ABC123'`). The server response shape MUST add `consecutivo: z.string().nullable()` to `PostIngresoResponseSchema`.

**Rationale**: discriminated union is the cleanest wire-shape for two parallel payload variants — explicit at the call site, validated at compile time. `null` for legacy carro/moto rows preserves wire compat with F6.1 clients.

#### Scenario: POST con placa válida retorna 201 sin `consecutivo`
- **Given** the operator typed `ABC123` and pressed Enter
- **When** the frontend POSTs `{placa_presente: true, placa: "ABC123"}`
- **Then** the server returns 201 with `{uuid_ingreso, tipo_entrada, consecutivo: null}`.

#### Scenario: POST sin placa + bici retorna 201 con `consecutivo`
- **Given** the operator clicked `Sin placa` and selected `Bicicleta`
- **When** the frontend POSTs `{placa_presente: false, uuid_tipo_vehiculo: <uuid bici>}`
- **Then** the server returns 201 with `{uuid_ingreso, tipo_entrada: "ROTACION", consecutivo: "BICI-000001-3f8a1b2c"}`.

#### Scenario: payload mixto es rechazado por Zod con 422
- **Given** any malformed variant (`{placa_presente: true, placa: null}` o `{placa_presente: false, placa: 'ABC123'}`)
- **When** the frontend POSTs the malformed payload
- **Then** Zod MUST reject with a typed `ZodError` carrying the discriminator field path (no server round-trip wasted).

**Verification**: `apps/electron-sucursal/src/features/operacion/lib/__tests__/ingresoApi.test.ts::test_postIngreso_payload_validation` (discriminated union); backend `backend/tests/unit/test_operacion_ingresos_validaciones.py::test_post_ingreso_no_placa_accepted` + `test_post_ingreso_placa_y_consecutivo_rejected`.
**Cross-refs**: precedent F6.1 `PostIngresoPayloadSchema` (`apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts:33-49`); Zod discriminated-union docs.

---

### REQ-OPS-195 — Dos botones `Con placa` / `Sin placa` en `Principal.tsx` e `IngresoPanel.tsx`

The pages `Principal.tsx` (standalone) and `IngresoPanel.tsx` (drawer variant in dashboard-hub) MUST render two side-by-side `<Button>` components at the top of each page: `Con placa` (visually dominant, default selected) and `Sin placa` (secondary variant). Clicking `Sin placa` MUST swap the active panel to `<IngresoSinPlacaPanel>`; clicking `Con placa` MUST swap back to `<PlacaInput>`. A successful submit from either panel MUST reset the selection to `Con placa`.

**Rationale**: the operator's muscle memory (type placa + Enter) is preserved by keeping `Con placa` visually dominant. Two `<Button>`s are more direct than tabs/cards for a binary choice (per Q5 decision in exploration §Open questions). Atomic dependency — both pages updated in the same PR per R8 mitigation.

#### Scenario: operador ve dos botones al cargar la página
- **Given** the operator opens `Principal.tsx` (or `IngresoPanel.tsx`)
- **When** the page renders
- **Then** `Con placa` MUST be visually dominant (default `variant="default"` per shadcn/ui)
- **And** `Sin placa` MUST be visible and clickable.

#### Scenario: click en `Sin placa` cambia al panel no-placa
- **Given** the operator is on `Principal.tsx`
- **When** the operator clicks `Sin placa`
- **Then** the panel MUST swap to `<IngresoSinPlacaPanel>` (showing `<TipoSelect>` + `Generar ingreso`)
- **And** `Con placa` MUST lose its dominant styling.

**Verification**: `apps/electron-sucursal/src/features/operacion/components/__tests__/Principal.test.tsx` (NEW — gap G12) + `IngresoPanel.test.tsx` (NEW); E2E `apps/electron-sucursal/e2e/ingreso-sin-placa.spec.ts` (Playwright, deferred per sandbox F.6 precedent).
**Cross-refs**: shadcn/ui `<Button>` component; precedent F6.1 toggle (rejected as approach — this is side-by-side, not toggle).

---

### REQ-OPS-196 — `<IngresoSinPlacaPanel>` con `<TipoSelect>` filtrado a tipos sin placa

A new component `<IngresoSinPlacaPanel>` MUST consume a new hook `useTiposVehiculoSinPlaca()` (which filters `useTiposVehiculo()` to exclude `carro` and `moto`), render a `<TipoSelect>` listing the remaining types (`bicicleta`, `patineta`), and a `Generar ingreso` button that constructs the payload `{placa_presente: false, uuid_tipo_vehiculo: <selección>}` and calls `postIngreso`. If the catalog returns no bici/patineta for the branch, the panel MUST show "Esta sucursal no admite ingresos sin placa" and disable the button.

**Rationale**: dedicated hook (per Q4 decision) keeps single-responsibility and aligns with the F3.3 `useSesionActiva` precedent. The disabled-state message is the failure mode when a branch hasn't seeded bici/patineta cupos.

#### Scenario: operador selecciona bicicleta y genera ingreso
- **Given** `useTiposVehiculoSinPlaca()` returns `[{tipo: 'bicicleta'}, {tipo: 'patineta'}]`
- **When** the operator selects `bicicleta` and clicks `Generar ingreso`
- **Then** the frontend POSTs `{placa_presente: false, uuid_tipo_vehiculo: <uuid bici>}` → 201 with `consecutivo` → `<TiqueteModal>` opens showing `Identificación: BICI-000001-...`.

#### Scenario: sucursal sin bici/patineta muestra mensaje
- **Given** `useTiposVehiculoSinPlaca()` returns `[]`
- **When** the panel renders
- **Then** the panel MUST show the disabled-state message ("Esta sucursal no admite ingresos sin placa")
- **And** MUST NOT show the `Generar ingreso` button.

**Verification**: hook test `apps/electron-sucursal/src/features/catalogos/hooks/__tests__/useTiposVehiculoSinPlaca.test.tsx` (filter logic + dedup 5min per F4.1 precedent); component test `apps/electron-sucursal/src/features/operacion/components/__tests__/IngresoSinPlacaPanel.test.tsx` (NEW).
**Cross-refs**: precedent `useTiposVehiculo` (F4.1); shadcn/ui `<Select>` component.

---

### REQ-OPS-197 — Render `Identificación:` en tiquete, `fallbackBrowser`, y `<TiqueteModal>` para ingresos sin placa

For every payload where `consecutivo` is non-NULL, the printer path (`escposBuilder.build('entrada', payload)`), the browser fallback (`fallbackBrowser.buildEntrada(payload)`), and `<TiqueteModal>` MUST render the line `Identificación: {consecutivo}` in place of `Placa: {placa}`. The discriminator at the payload level is `payload.placa === null` (no-placa variant) vs `payload.placa !== null` (legacy placa variant). The `entradaPayloadSchema` MUST be a discriminated union exported as `z.union([EntradaPlacaSchema, EntradaConsecutivoSchema])`. The byte-fixture test MUST pin the exact sequence `Identificación: BICI-000001-3f8a1b2c\n` at the position of the original `Placa:` line in the buffer.

**Rationale**: the field name stays `consecutivo` (semantic identifier), the rendered label is `Identificación` (operator-facing per Q3 / DEC-SUC-26). The union prevents the print layer from receiving a partial payload that has neither placa nor consecutivo.

#### Scenario: tiquete de carro imprime `Placa: ABC123` (regresión)
- **Given** an ingreso with `placa = "ABC123"` (legacy F6.1 flow)
- **When** `escposBuilder.build('entrada', payload)` runs
- **Then** the buffer MUST contain the literal `Placa: ABC123\n` byte sequence (no `Identificación:` line).

#### Scenario: tiquete de bici imprime `Identificación: BICI-000001-3f8a1b2c`
- **Given** an ingreso with `placa = null` and `consecutivo = "BICI-000001-3f8a1b2c"`
- **When** `escposBuilder.build('entrada', payload)` runs
- **Then** the buffer MUST contain the literal `Identificación: BICI-000001-3f8a1b2c\n` byte sequence (no `Placa:` line).

**Verification**: byte-fixture `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` (extend with T14 + T15); `fallbackBrowser.entrada.test.ts` (extend with T16); component test `apps/electron-sucursal/src/features/operacion/components/__tests__/TiqueteModal.test.tsx` (NEW — gap G12, T18 + T19).
**Cross-refs**: precedent `escposTemplates.ts::entradaPayloadSchema`; DEC-SUC-26 (QR payload embeds `parkos://ingreso/<uuid>?consecutivo=<consecutivo>` for no-placa variant — verify in design).

---

### REQ-OPS-198 — Validación de cupo se aplica a ingresos sin placa (cupo agotado → 422 motivo_forzado_requerido)

The backend MUST execute `validar_cupo_disponible(session, uuid_sucursal, uuid_tipo_vehiculo)` for no-placa ingresos (REQ-OPS-191 variant) IDENTICALLY to placa ingresos. If `cupo_agotado=True` for `(sucursal, bici|patineta)`, the handler MUST respond `422 motivo_forzado_requerido` with `cupo_maximo` and `activos` in the body. The operator MUST be able to retry with `forzado=true` + `observaciones: "[FORZADO: <motivo ≥10 chars>]"` via the existing `<ForzarIngresoModal>` (no new modal). If `cupo_no_configurado=True` (no bici/patineta cupos seeded for the branch), the handler MUST respond `422 cupo_no_configurado` with `forzado_permitido: true`.

**Rationale**: `validar_cupo_disponible` is already tipo-agnostic (`repo/ocupacion.py:138-214`). Reusing `<ForzarIngresoModal>` per Q9 avoids a second modal and preserves the F6.1 forzado UX verbatim.

#### Scenario: cupo de bicicleta agotado → 422 motivo_forzado_requerido
- **Given** `(X, bicicleta)` has `cantidad_vehiculos_sucursal.cantidad = 20` AND `mv_ocupacion_diaria.activos = 20`
- **When** the operator POSTs a no-placa bici ingreso
- **Then** the response MUST be `422` with body `{"error": "motivo_forzado_requerido", "cupo_maximo": 20, "activos": 20}`.

#### Scenario: operador fuerza con motivo válido → 201 + alerta
- **Given** the previous scenario's 422 response
- **When** the operator retries with `forzado: true, observaciones: "[FORZADO: evento de inauguración]"` (≥10 chars after prefix)
- **Then** the backend MUST persist the row with `consecutivo` AND insert an `alerta tipo_alerta='cupo_agotado_forzado'`.

#### Scenario: cupo no configurado para bici → 422 cupo_no_configurado
- **Given** `cantidad_vehiculos_sucursal` has no row for `(X, bicicleta)`
- **When** the operator POSTs a no-placa bici ingreso
- **Then** the response MUST be `422` with body `{"error": "cupo_no_configurado", "forzado_permitido": true}`.

**Verification**: `backend/tests/unit/test_operacion_ingresos_validaciones.py::test_post_ingreso_sin_placa_cupo_agotado` + `test_post_ingreso_sin_placa_forzado_motivo_valido`; integration `backend/tests/integration/test_ocupacion_view.py::test_mv_ocupacion_diaria_counts_no_placa_ingreso` (regression — MV counts non-placa INSERTs).
**Cross-refs**: `validar_cupo_disponible` (`repo/ocupacion.py:138-214`); precedent `<ForzarIngresoModal>` (F6.1, `Principal.tsx:147-172` + `IngresoPanel.tsx:202-227`).

---

## 3. MODIFIED Requirements

### REQ-OPS-040 — V8: `ingreso_activo_existente` returns 409 with `uuid_ingreso_existente`; SKIP for no-placa

(Previously: V8 was unconditional — the handler always invoked `existe_ingreso_activo` with `placa = payload.placa or ""`. For no-placa ingresos this searched by `placa=""` and never blocked a duplicate, defeating the purpose of the check. Defense in depth: the partial UK on `prod.ingreso.consecutivo` (REQ-OPS-192) catches duplicates at DB level instead.)

**Given** the request body has reached V8 (all prior validations passed)
**When** the handler invokes
`repo/ingreso.py::existe_ingreso_activo(session, *, uuid_sucursal=X, placa=P)` which executes `EXISTS (SELECT 1 FROM prod.ingreso i WHERE i.uuid_sucursal=X AND i.placa=P AND NOT EXISTS (SELECT 1 FROM prod.salidas s WHERE s.uuid_ingreso=i.uuid AND s.uuid_sucursal=i.uuid_sucursal) AND NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_ingreso=i.uuid AND a.estado='ejecutada' AND a.tipo_anulable IN ('ingreso','salida')))`
**Then** if the predicate returns a row, the helper MUST return the `uuid` of the existing active ingreso
**And** the handler MUST raise `HTTPException(status_code=409, detail={"error": "ingreso_activo_existente", "uuid_ingreso_existente": "<uuid>"})`
**And** the handler MUST NOT acquire any `SELECT … FOR UPDATE/SHARE` lock — KD-V4 eventual consistency via `mv_ocupacion_diaria` is acceptable for V2 (R8); V8 goes directly to the authoritative tables (< 50ms p99 expected; EXPLAIN ANALYZE confirmed in design.md)
**And** for no-placa ingresos (REQ-OPS-191 variant where `payload.placa is None`), the handler MUST SKIP the V8 check entirely — duplicate detection for no-placa is delegated to the partial UK on `prod.ingreso.consecutivo` (REQ-OPS-192).
**RFC 2119**: MUST (predicate shape with two `NOT EXISTS` clauses, 409 with literal `uuid_ingreso_existente` key, no pessimistic lock, skip when `placa is None`).

#### Scenario: placa activa sin salida ni anulación returns 409

- **Given** `prod.ingreso` already contains `(uuid_sucursal=X, placa=ABC123)` with no row in `prod.salidas` and no row in `prod.anulaciones` with `estado='ejecutada'`
- **When** the operator POSTs `{"placa": "ABC123"}` (all prior V validations pass)
- **Then** the response MUST be `409 Conflict` with body `{"error": "ingreso_activo_existente", "uuid_ingreso_existente": "<existing_uuid>"}`
- **And** `prod.ingreso` MUST have no new rows.

#### Scenario: placa con salida previa no anulada permite nuevo ingreso

- **Given** the existing `(X, ABC123)` ingreso has a non-anulada row in `prod.salidas` (the previous ciclo closed)
- **When** the operator POSTs `{"placa": "ABC123"}`
- **Then** `existe_ingreso_activo` MUST return `None` (the previous activo was eliminated by the salida) and the handler MUST proceed to INSERT a new `prod.ingreso` row.

#### Scenario: placa con anulación ejecutada permite nuevo ingreso

- **Given** the existing `(X, ABC123)` ingreso has a row in `prod.anulaciones` with `estado='ejecutada' AND tipo_anulable='ingreso'`
- **When** the operator POSTs `{"placa": "ABC123"}`
- **Then** `existe_ingreso_activo` MUST return `None` and the handler MUST proceed to INSERT.

#### Scenario: ingreso sin placa skipea V8 y delega duplicados al UK parcial

- **Given** the operator POSTs a no-placa ingreso `{placa_presente: false, uuid_tipo_vehiculo: <uuid bici>}` (REQ-OPS-194 variant)
- **When** the handler reaches V8
- **Then** the handler MUST NOT invoke `existe_ingreso_activo` (the check is meaningless with `placa = null`)
- **And** duplicate detection MUST be enforced by the partial UK on `prod.ingreso.consecutivo` (REQ-OPS-192) — two POSTs with the same `consecutivo` from a race condition MUST raise `23505 unique_violation`.

---

## 4. Cross-cutting concerns

| Concern | Disposition |
|---|---|
| **Audit-first** | `assign_ingreso_consecutivo` is consumed inside `repo.event.record_event` flow. `consecutivo` flows into `log_transaccional.datos_nuevos` automatically via the canonical payload (`event.py:115-137`). SHA256 hash chain continues unbroken — verified. No explicit handling needed. |
| **Multi-tenant** | Counter scoped to `(uuid_sucursal, uuid_tipo_vehiculo)`. Partial UK `WHERE consecutivo IS NOT NULL` enforces at DB level. Two branches can both have `BICI-000001-...` without collision. |
| **Sync (eventual)** | PR9b sync stub propagates the new row with its `consecutivo` via `record_event`. Cloud preserves branch-assigned value verbatim (`cloud-edge-sync-architecture` §4 + DEC-SUC-28). No additional sync work. |
| **Hash chain** | The new column is part of the row, so it lands in `log_transaccional.datos_nuevos` via `record_event`'s canonical payload (`event.py:115-137`). Chain forward-verifiable by cloud's `hash_chain_verifier_loop` (PR9b). |
| **AST lock `[L-E]` insert-only** | `consecutivo` is assigned ONCE at INSERT inside `repo.ingreso.crear_ingreso_evento`. No UPDATE path exists. `tests/static/test_no_write_after_insert.py` enforces. |
| **i18n** | 7 new keys in `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json`: `ingreso_sin_placa_cta`, `ingreso_sin_placa_selector_label`, `ingreso_sin_placa_tipo_bicicleta`, `ingreso_sin_placa_tipo_patineta`, `ingreso_sin_placa_generar_boton`, `ingreso_sin_placa_exito`, `tiquete_identificacion_label`. |
| **Conventional commits** | Per AGENTS.md canon — `feat(operacion): add ingreso.consecutivo column + counter table + assign helper (HU-F4.1-NN)` etc. No `Co-Authored-By` AI trailers. |

## 5. Out of scope (deferred)

- **Reset del consecutivo** — monotónico forever per Q1 (counter only increments within `(uuid_sucursal, uuid_tipo_vehiculo)`).
- **UI admin para gestionar resoluciones** — no aplica; `prod.ingreso.consecutivo` is NOT a DIAN invoice number.
- **Cambios en salidas** — handler de salida lee JOIN sin cambios (verify in design phase).
- **Cambios en sync pipeline** — `record_event` fluye la columna automáticamente.
- **Generación de UUID v8 custom** — usamos v4 estándar `gen_random_uuid()`.
- **Multi-idioma para `operacion.json`** — solo es-CO en este PR; en-US/pt-BR follow-up si se requiere.
- **Selector manual de tipo en flujo con placa** — BR2 invariante; autodetección por regex es la ÚNICA fuente válida.
- **Auto-renew / auto-cancel del counter** — operacionales, follow-up.

## 6. References

- `openspec/changes/ingreso-multi-tipo-consecutivo/proposal.md` (proposal, 205 líneas)
- `openspec/changes/ingreso-multi-tipo-consecutivo/exploration.md` (exploration, 278 líneas)
- `openspec/specs/operacion.md` (canonical spec for operacion-ingreso; expected rename to `operacion-ingreso.md` during archive per operations spec precedent)
- `openspec/specs/operations/spec.md` (REQ-OPS-040 V8 base being modified; REQ-OPS-034..041 V-chain baseline; REQ-OPS-125..130 F4.1 catalogo precedent; REQ-OPS-184..190 latest added)
- `openspec/specs/catalogos.md` (`useTarifasVigentes` precedent for the `useTiposVehiculoSinPlaca` hook)
- `openspec/specs/impresion.md` (F5.1/F5.2/F6.2 escposBuilder + fallbackBrowser precedent)
- `openspec/changes/archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo/proposal.md` (precedent — detection + useTiposVehiculo hook)
- `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/` (precedent — Principal + PlacaInput + TiqueteModal baseline)
- `openspec/changes/archive/2026-09-19-fase-7-3-tiquetes-salida/` (precedent — escposBuilder byte-fixture pattern)
- `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo:47-183` (counter helper precedent — T-PR9-002)
- `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py::validar_cupo_disponible:138-214` (cupo validator — already tipo-agnostic)
- `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py` (Ingreso ORM — `[L-E]` insert-only)
- `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts:33-49` (current Zod schema — refactored to discriminated union)
- `apps/electron-sucursal/src/lib/print/escposTemplates.ts::entradaPayloadSchema` (current discriminated-by-placa schema — extended)
- AGENTS.md §Architectural Principles (audit-first, bi-temporal, C/Q/U-no-D, multi-tenant, hash chain)
- AGENTS.md §Operational Timeouts (migration pre-flight verification, REVOKE + trigger in same script)
- `openspec/config.yaml` `rules.tasks` (REVOKE + trigger in same migration for `[A]` tables; pre-flight `alembic upgrade --sql`)
- `modelo_datos_er.mmd` lines 577-596 (canonical `[L-E] ingreso` shape — pre-change baseline)
- DEC-INCOME-01 (locked in proposal §4): `prod.ingreso.consecutivo` is the parking-lot identifier for bici/patineta — NOT a DIAN invoice number.
