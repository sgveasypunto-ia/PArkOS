# Delta Spec — HU-F1.12: Venta atómica de suscripción (cliente + vehículos + suscripción + cobro opcional + FE opcional en 1 TX)

> **Change**: `hu-f1-12-venta-suscripcion`
> **Target spec**: `openspec/specs/operations/spec.md` (will append 8 new REQs on archive: REQ-OPS-083..090 + REQ-OPS-XR5)
> **Phase**: spec (sdd-spec)
> **Status**: ready for `sdd-design` + `sdd-tasks` + `sdd-apply`
> **HU ID**: HU-F1.12 (Fase-1 prerequisites — backend)
> **Inputs**: `openspec/changes/hu-f1-12-venta-suscripcion/proposal.md` (~485 LOC, 16 sections, 2026-09-15, DEC-VENTA-01..07 + DEC-VENTA-08 WITHDRAWN, KD-VENTA-01..02, 8 REQ-OPS placeholders), `plan.md` lines 1010-1054 (260 LOC production, 3 atomic tasks T1..T3, 4 tests mandated at line 1047), `modelo_datos_er.mmd` blocks `tipo_subscripciones` [V] line 105, `clientes` [V] line 449, `vehiculos` [V] line 519, `subscripciones_cliente` [V] line 496, `subscripcion_vehiculos` [V] line 538, `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones`), 435-452 (`clientes`), 454-465 (`vehiculos`), 483-496 (`subscripciones_cliente`), 498-509 (`subscripcion_vehiculos`), `backend/packages/parkos_core/src/parkos_core/models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py`, `backend/packages/parkos_core/src/parkos_core/repo/{factura,factura_electronica,resolucion_facturacion,subscripcion_activa,placa,versioned,idempotency}.py`, `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py`, `backend/packages/parkos_core/src/parkos_core/api/v1/{facturacion,workflows_reimpresion,clientes,_helpers}.py`, `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py` (lines 133, 451, 483, 511, 525 — all 5 [V] entries verified pre-existing 2026-09-15), `openspec/specs/operations/spec.md` (last REQ-OPS-NNN vigente: **REQ-OPS-080 + XR4** after the merge of HU-F1.11 in commit `ddfe1f8`), `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/specs/operations/spec.md` (canonical Given/When/Then/And format precedent).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `ddfe1f8`) · **PR target**: `origin/dev`.
> **Note on DEC-VENTA-08 WITHDRAWN**: sync catalog pre-flight 2026-09-15 confirmed all 5 [V] entries pre-exist in `sync_entries_v.py`. MIGRATION 0030 is a NO-OP audit trail only — no DDL, no sync seed, no permission re-seed.

---

## Purpose

HU-F1.12 closes the **operador-facing atomic sale-at-the-counter workflow** on top of the already-shipped `prod.tipo_subscripciones` / `prod.clientes` / `prod.vehiculos` / `prod.subscripciones_cliente` / `prod.subscripcion_vehiculos` `[V]` tables and the F1.9 (atomic factura) + F1.10 (atomic FE) machinery by exposing one transactional endpoint that creates or looks-up a cliente, creates or looks-up vehiculos per placa, INSERTs the subscripcion + junction rows, and optionally runs the F1.9 cobro chain + the F1.10 FE chain — all in a single `await session.commit()` covering up to 9 tables + `log_transaccional` co-INSERTs.

The 8 new REQ-OPS-NNN (REQ-OPS-083..090 + REQ-OPS-XR5) extend the `operational` capability already consolidated in `openspec/specs/operations/spec.md`. REQ-OPS-001..080 + XR1..XR4 remain unchanged.

---

## ADDED Requirements

### REQ-OPS-083 — Single-commit atomicity across 9 tables (KD-VENTA-01)

**Source**: HU-F1.12 (DEC-VENTA-01) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST issue exactly one `await session.commit()` at the END of the request body (Step 10 of the 10-step chain), covering all 5 `[V]` writes (`prod.clientes`, `prod.vehiculos`, `prod.subscripciones_cliente`, `prod.subscripcion_vehiculos`, `prod.tipo_subscripciones` lock-only) + the 4 optional `[A]`/`[L-E]` cobro writes (`prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos`) when `cobrar_ahora=true` + the 2 optional `[L-W]`/`[L-E]` FE writes (`prod.factura_electronica`, `prod.envio_dian`) when `emitir_factura_electronica=true` + N `prod.log_transaccional` co-INSERTs. The handler MUST NOT use `session.begin_nested()` or `SAVEPOINT`. All helper functions (`crear_*`) MUST stay commit-free — they `session.add()` + `await session.flush()` only.

**Rationale**: Cross-domain atomicity is the entire business requirement (plan.md line 1014: "sin que un fallo a mitad de camino deje datos inconsistentes"). F1.10 KD-FE-01 + F1.11 KD-TKT-01 establish the single-commit invariant as the canonical pattern for multi-table writes. The 9-table single commit is well within PostgreSQL's capabilities — `[V]` tables have minimal locking (UK checks), `[A]`/`[L-E]`/`[L-W]` writes are INSERT-only, no long-held locks.

**Source**: `plan.md` line 1014 (atomicity mandate); `backend/packages/parkos_core/src/parkos_core/repo/versioned.py::close_and_insert` (commit-free contract); F1.10 REQ-OPS-065 (KD-FE-01 precedent); F1.11 REQ-OPS-XR3 (KD-TKT-01 single-commit precedent).

**Scenario 1: Happy path — all writes succeed in 1 commit, all rows visible post-response**
- **Given** a `VentaSuscripcionCreate` payload with valid `cliente` (new), 1 placa `ABC123`, a vigente `uuid_tipo_subscripcion`, `fecha_inicio_cobertura='2026-09-12'`, `cobrar_ahora=true`, `emitir_factura_electronica=true`
- **When** the handler reaches Step 10 and calls `await session.commit()` exactly once
- **Then** exactly one `prod.clientes` row MUST be visible (uuid matches response)
- **And** exactly one `prod.vehiculos` row MUST be visible (placa=`ABC123`)
- **And** exactly one `prod.subscripciones_cliente` row MUST be visible
- **And** exactly one `prod.subscripcion_vehiculos` row MUST be visible (junctions the subscription to the vehiculo)
- **And** exactly one `prod.facturas` row + 1 `prod.factura_detalle` row + 1 `prod.factura_impuestos` row + 1 `prod.factura_pagos` row MUST be visible
- **And** exactly one `prod.factura_electronica` row + 1 `prod.envio_dian` row MUST be visible
- **And** the response MUST be `201 Created` with `VentaSuscripcionResponse` carrying all nested UUIDs + `Cache-Control: no-store`.

**Scenario 2: Mid-flight failure — any helper raise rolls back the entire TX**
- **Given** the same valid payload but Step 8a (`_factura_sub_chain` when `cobrar_ahora=true`) raises `IvaNoConfiguradoError` because `prod.impuestos.IVA` row is missing
- **When** the handler catches the exception and returns `500 iva_no_configurado`
- **Then** `await session.commit()` MUST NOT be called (KD-VENTA-01)
- **And** the entire TX MUST be rolled back — ZERO `prod.clientes`, `prod.vehiculos`, `prod.subscripciones_cliente`, `prod.subscripcion_vehiculos`, `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos` rows MUST exist after the rollback (no orphan clientes / vehiculos / subscripciones if cobro failed)
- **And** NO `prod.factura_electronica` / `prod.envio_dian` rows MUST exist.

**Scenario 3: AST walk — handler source contains EXACTLY ONE `await session.commit()` call**
- **Given** the source file `api/v1/clientes_venta.py` containing `venta_suscripcion` handler
- **When** `tests/static/test_venta_handler_single_commit.py` runs an `ast.walk()` over the handler body
- **Then** the AST walk MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(n.value.func, 'attr', '') == 'commit']) == 1` (exactly one `await session.commit()` call)
- **And** MUST assert `len([n for n in ast.walk(body) if isinstance(n, ast.Await) and getattr(getattr(n.value, 'func', None), 'attr', '') == 'begin_nested']) == 0` (no SAVEPOINT)
- **And** MUST assert NO occurrence of the literal string `"SAVEPOINT"` in the handler body (defense in depth).

---

### REQ-OPS-084 — Plan lock `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (KD-VENTA-02 + DEC-VENTA-04)

**Source**: HU-F1.12 (DEC-VENTA-02 + DEC-VENTA-04) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST take `SELECT ... FOR UPDATE` (exclusive, NOT `FOR SHARE`) on the vigente `prod.tipo_subscripciones` row identified by `payload.uuid_tipo_subscripcion` BEFORE any other lock is acquired (Step 2 of the 10-step chain). The lock MUST be held until `await session.commit()` at Step 10. If the lookup returns no vigente row, the handler MUST raise `HTTPException(404, {"error": "tipo_subscripcion_no_encontrado", "uuid_tipo_subscripcion": str(payload.uuid_tipo_subscripcion)}, headers=no_store_headers())`. If multiple vigentes exist (corrupt DB), the handler MUST deterministically pick the latest by `vigente_desde DESC LIMIT 1`.

**Rationale**: The plan read mutates the sale semantics — `fecha_inicio_cobertura` is captured, and concurrent ventas on the SAME plan with different `fecha_inicio_cobertura` would produce different A-09 prorrateo amounts. `FOR SHARE` (F1.9 KD-FACT-02 pattern) is insufficient because two concurrent ventas could compute prorrateo on a stale snapshot. `FOR UPDATE` serializes the calc.

**Source**: `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones` schema + bi-temporal VersionedBase); F1.9 KD-FACT-02 (`FOR SHARE` precedent, intentionally diverged); F1.10 REQ-OPS-064 (`assign_consecutivo` `FOR UPDATE` precedent); `plan.md` lines 1010-1054 (KD-VENTA-02).

**Scenario 1: Single venta on plan — lock acquired, sold, released on commit**
- **Given** a vigente `prod.tipo_subscripciones` row with `uuid=:p`, `valor=50000`, `duracion_dias=30`, `cantidad_maxima_vehiculos=2`, `mismo_tipo_vehiculo=true`
- **When** the handler invokes `SELECT * FROM prod.tipo_subscripciones WHERE uuid=:p AND vigente_hasta IS NULL ORDER BY vigente_desde DESC LIMIT 1 FOR UPDATE`
- **Then** the row lock MUST be acquired (the TX owns the lock until commit)
- **And** the handler MUST proceed to Step 3 (cliente lookup-or-create)
- **And** after `await session.commit()` at Step 10, the lock MUST be released (other TXs can now lock the same row).

**Scenario 2: Concurrent ventas on SAME plan — second venta waits, then succeeds with fresh `fecha_inicio_cobertura` capture**
- **Given** two concurrent TXs both POST `/api/v1/clientes/venta-suscripcion` with the SAME `uuid_tipo_subscripcion=:p` but DIFFERENT `fecha_inicio_cobertura` (TX-A: `'2026-09-10'`, TX-B: `'2026-09-25'`)
- **When** both TXs reach Step 2 simultaneously
- **Then** TX-A MUST acquire `SELECT FOR UPDATE` on `:p` first
- **And** TX-B MUST block at the `SELECT FOR UPDATE` until TX-A commits
- **And** TX-B MUST re-read `:p` (no read snapshot taken before the lock release) and compute prorrateo on its OWN `fecha_inicio_cobertura='2026-09-25'` (after-day-15 prorrateo path)
- **And** TX-A MUST compute prorrateo on its OWN `fecha_inicio_cobertura='2026-09-10'` (no prorrateo, full `plan.valor`)
- **And** both ventas MUST succeed atomically with DIFFERENT prorrateo amounts persisted in each `prod.factura_detalle` row (no cross-contamination).

**Scenario 3: Concurrent ventas on DIFFERENT plans — NOT serialized, both succeed**
- **Given** two vigentes `prod.tipo_subscripciones` rows `:p1` (plan "mensualidad") and `:p2` (plan "trimestral")
- **When** two concurrent TXs POST with `uuid_tipo_subscripcion=:p1` and `uuid_tipo_subscripcion=:p2` respectively
- **Then** both TXs MUST acquire their respective plan locks independently (no mutual blocking)
- **And** both ventas MUST succeed atomically in their own TXs without serialization on the plan row.

---

### REQ-OPS-085 — Lock ordering: plan lock before cliente lock (deadlock prevention)

**Source**: HU-F1.12 (DEC-VENTA-02) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
When `payload.uuid_cliente` is provided (existing cliente), the handler MUST acquire the plan lock (`SELECT FOR UPDATE` on `prod.tipo_subscripciones`) FIRST (Step 2), then the cliente lock (`SELECT FOR UPDATE` on `prod.clientes`) AFTER (Step 3a). When `payload.cliente` is provided (new cliente, no existing row), the cliente lock is not acquired because `close_and_insert(current_uuid=None, ...)` INSERTs a new row without a prior lock. The handler MUST NOT reverse the ordering (cliente first, then plan).

**Rationale**: A consistent global lock ordering prevents deadlocks under concurrent ventas. Without it, Plan A could hold the cliente lock waiting for the plan lock while Plan B holds the plan lock waiting for the cliente lock — a classic AB-BA deadlock that PostgreSQL would resolve by killing one TX with `deadlock_detected`. F1.10 KD-FE-01 established the "external lock (resolution row) before internal write" pattern; F1.12 mirrors it for plan-before-cliente.

**Source**: F1.10 REQ-OPS-064 (external-lock-first pattern); `backend/packages/parkos_core/src/parkos_core/repo/workflow.py` lines 66-72 (state machine lock ordering precedent).

**Scenario 1: Plan A + existing cliente X, Plan B + existing cliente X — no deadlock**
- **Given** two concurrent ventas, both for the same existing cliente `:c` (uuid_cliente=:c):
  - TX-A: `uuid_tipo_subscripcion=:p1` (plan A), `uuid_cliente=:c`
  - TX-B: `uuid_tipo_subscripcion=:p2` (plan B), `uuid_cliente=:c`
- **When** both TXs reach Step 2 simultaneously
- **Then** TX-A MUST acquire the plan lock on `:p1` first
- **And** TX-B MUST acquire the plan lock on `:p2` (independent plan lock, no contention with TX-A)
- **And** TX-A MUST then acquire the cliente lock on `:c` (Step 3a) — no other TX holds `:c` yet
- **And** TX-B MUST wait at the cliente lock on `:c` until TX-A commits
- **And** after TX-A commits, TX-B MUST acquire `:c`, read the now-committed cliente state, and proceed to Step 4+ — no deadlock, no abort.

**Scenario 2: Reversed ordering — cliente first, then plan — REJECTED, would deadlock**
- **Given** a hypothetical handler that acquires `SELECT FOR UPDATE` on `prod.clientes` BEFORE `prod.tipo_subscripciones`
- **When** the two TXs from Scenario 1 run
- **Then** TX-A MUST acquire cliente lock `:c` first
- **And** TX-B MUST block at cliente lock `:c`
- **And** TX-A MUST then attempt to acquire plan lock `:p1` — succeeds independently
- **And** TX-A MUST commit and release `:c` and `:p1`
- **And** TX-B MUST acquire `:c`, then attempt to acquire `:p2` — also independent, no deadlock here
- **But** a third scenario (TX-A: plan A + cliente X; TX-B: plan B + cliente Y, where X and Y have a pending FK relationship via another join path) could exhibit a deadlock — the reversed ordering is REJECTED in DEC-VENTA-02 §6.2.

---

### REQ-OPS-086 — Placa format validation (V3 — `FORMATO_AUTO` / `FORMATO_MOTO`)

**Source**: HU-F1.12 (V3) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
Each placa string in `payload.placas` MUST match one of two regex patterns: `FORMATO_AUTO = re.compile(r"^[A-Z]{3}[0-9]{3}$")` for automobiles (e.g. `ABC123`) OR `FORMATO_MOTO = re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$")` for motorcycles (e.g. `ABC12D`). Both patterns are defined in `backend/packages/parkos_core/src/parkos_core/repo/placa.py`. If any placa in the list fails both regexes, the handler MUST raise `HTTPException(422, {"error": "placa_formato_invalido", "placa": <offending_placa>}, headers=no_store_headers())`. The Pydantic schema MUST also enforce `Annotated[list[str], Field(min_length=1, max_length=2)]` on `placas` AND `Annotated[str, StringConstraints(min_length=1, max_length=16)]` on each placa string. Layered defense: Pydantic rejects at parse time (Layer 4) AND `repo.placa` rejects at handler time (Layer 3 via KD-VENTA-02 plan lock ordering).

**Rationale**: F1.6 introduced `FORMATO_AUTO` + `FORMATO_MOTO` as the canonical placa validators. The 422 mapping ensures the operator gets a typed error pointing at the offending placa. The `min_length=1, max_length=2` on the list enforces the plan's `cantidad_maxima_vehiculos` upper bound at the schema layer (defense in depth against V6).

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/placa.py` lines 12-25 (regex constants); `plan.md` lines 1010-1054 (V3 mandate); F1.6 REQ-OPS-038 (placa validators precedent).

**Scenario 1: `ABC123` matches AUTO format — OK**
- **Given** a payload with `placas: ["ABC123"]`
- **When** the handler Step 4 invokes `repo.placa.validar_formato_placa("ABC123")`
- **Then** the validator MUST return `True` (matches `FORMATO_AUTO`)
- **And** the handler MUST proceed to `repo.placa.detectar_tipo_vehiculo("ABC123")` for V5.

**Scenario 2: `ABC12D` matches MOTO format — OK**
- **Given** a payload with `placas: ["ABC12D"]`
- **When** the handler Step 4 invokes `repo.placa.validar_formato_placa("ABC12D")`
- **Then** the validator MUST return `True` (matches `FORMATO_MOTO`)
- **And** the handler MUST proceed to lookup-or-create the vehiculo with `uuid_tipo_vehiculo` corresponding to "moto".

**Scenario 3: `abc123` (lowercase) — 422 `placa_formato_invalido`**
- **Given** a payload with `placas: ["abc123"]`
- **When** the handler Step 4 invokes `repo.placa.validar_formato_placa("abc123")`
- **Then** the validator MUST return `False` (lowercase `a` fails both `[A-Z]{3}` patterns)
- **And** the handler MUST raise `HTTPException(422, {"error": "placa_formato_invalido", "placa": "abc123"}, headers=no_store_headers())`
- **And** NO `prod.vehiculos` row MUST be INSERTed (validation failure short-circuits before Step 4 INSERT).

---

### REQ-OPS-087 — Tipo vehículo compatible constraint (V5 — `mismo_tipo_vehiculo`)

**Source**: HU-F1.12 (V5) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
When the resolved `prod.tipo_subscripciones.mismo_tipo_vehiculo=true`, the handler MUST verify that ALL placas in `payload.placas` derive the SAME `uuid_tipo_vehiculo` via `repo.placa.detectar_tipo_vehiculo(session, placa)`. If the derived tipos differ (e.g. one placa matches AUTO format and another matches MOTO format, OR two placas match AUTO format but one resolves to a catalog variant like "taxi" while the other resolves to "particular"), the handler MUST raise `HTTPException(422, {"error": "tipo_vehiculo_incompatible", "tipos_encontrados": [<list of distinct tipos>]}, headers=no_store_headers())`. When `mismo_tipo_vehiculo=false`, mixed tipos are accepted and no V5 check applies.

**Rationale**: Some plans are tipo-restricted (e.g. "plan solo para automóviles"). A plan with `mismo_tipo_vehiculo=true` means ALL subscribed vehicles must share the same tipo. The 422 mapping gives the operator a typed error listing the distinct tipos found.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/placa.py` lines 27-65 (`detectar_tipo_vehiculo`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 207 (`mismo_tipo_vehiculo` column); F1.6 REQ-OPS-038 (placa-to-tipo mapping precedent).

**Scenario 1: Plan with `mismo_tipo_vehiculo=true` + 2 placas of tipo "auto" — OK**
- **Given** a plan `:p` with `mismo_tipo_vehiculo=true`, `cantidad_maxima_vehiculos=2`
- **And** a payload with `placas: ["ABC123", "DEF456"]` (both match `FORMATO_AUTO`)
- **And** `repo.placa.detectar_tipo_vehiculo` returns the SAME `uuid_tipo_vehiculo` for both placas (catalog lookup against `prod.tipos_vehiculo`)
- **When** the handler Step 5 invokes `repo_venta.validar_placas_mismo_tipo_vehiculo(session, plan=:p, vehiculos=[<v1>, <v2>])`
- **Then** the validator MUST return without raising
- **And** the handler MUST proceed to Step 6 (V6 cantidad maxima check).

**Scenario 2: Plan with `mismo_tipo_vehiculo=true` + 1 auto + 1 moto — 422 `tipo_vehiculo_incompatible`**
- **Given** a plan `:p` with `mismo_tipo_vehiculo=true`, `cantidad_maxima_vehiculos=2`
- **And** a payload with `placas: ["ABC123", "XYZ12A"]` (AUTO + MOTO format)
- **When** the handler Step 5 invokes `validar_placas_mismo_tipo_vehiculo`
- **Then** the validator MUST detect that `detectar_tipo_vehiculo("ABC123")` returns `uuid_tipo_vehiculo=:t_auto` AND `detectar_tipo_vehiculo("XYZ12A")` returns `uuid_tipo_vehiculo=:t_moto` AND `:t_auto != :t_moto`
- **And** MUST raise `HTTPException(422, {"error": "tipo_vehiculo_incompatible", "tipos_encontrados": [":t_auto", ":t_moto"]}, headers=no_store_headers())`
- **And** NO `prod.subscripciones_cliente` row MUST be INSERTed (V5 failure short-circuits before Step 9).

**Scenario 3: Plan with `mismo_tipo_vehiculo=false` + mixed tipos — OK**
- **Given** a plan `:p` with `mismo_tipo_vehiculo=false`, `cantidad_maxima_vehiculos=2`
- **And** a payload with `placas: ["ABC123", "XYZ12A"]` (AUTO + MOTO format, distinct tipos)
- **When** the handler Step 5 invokes `validar_placas_mismo_tipo_vehiculo`
- **Then** the validator MUST return without raising (V5 check is SKIPPED because `mismo_tipo_vehiculo=false`)
- **And** the handler MUST proceed to Step 6.

---

### REQ-OPS-088 — Cantidad máxima vehículos constraint (V6 — `cantidad_maxima_vehiculos`)

**Source**: HU-F1.12 (V6) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST verify that `len(payload.placas) <= plan.cantidad_maxima_vehiculos`. If `len(payload.placas) > plan.cantidad_maxima_vehiculos`, the handler MUST raise `HTTPException(422, {"error": "cantidad_maxima_excedida", "cantidad_maxima_vehiculos": <plan.cantidad_maxima_vehiculos>, "placas_proporcionadas": <len(payload.placas)>}, headers=no_store_headers())`. The Pydantic schema MUST also enforce `Field(min_length=1, max_length=2)` on `placas` (Layer 4 defense in depth), so any payload with `len(placas) > 2` is rejected before reaching the handler body.

**Rationale**: Plans have a hard cap on how many vehicles a single subscription can cover (e.g. "plan mensual para 1 vehiculo" vs "plan familiar para 2 vehiculos"). The V6 check enforces the business contract. The Pydantic `max_length=2` is the hard upper bound across all plans (no plan in the catalog allows > 2 vehicles); the V6 helper adds the per-plan check.

**Source**: `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` line 206 (`cantidad_maxima_vehiculos` column); `plan.md` lines 1010-1054 (V6 mandate, 1-2 placas per plan).

**Scenario 1: Plan allows 1 vehiculo + 1 placa — OK**
- **Given** a plan `:p` with `cantidad_maxima_vehiculos=1`
- **And** a payload with `placas: ["ABC123"]`
- **When** the handler Step 6 invokes `validar_cantidad_maxima_vehiculos(session, plan=:p, n_placas=1)`
- **Then** the validator MUST return without raising (`1 <= 1`).

**Scenario 2: Plan allows 1 vehiculo + 2 placas — 422 `cantidad_maxima_excedida`**
- **Given** a plan `:p` with `cantidad_maxima_vehiculos=1`
- **And** a payload with `placas: ["ABC123", "DEF456"]`
- **When** the handler Step 6 invokes `validar_cantidad_maxima_vehiculos(session, plan=:p, n_placas=2)`
- **Then** the validator MUST detect that `2 > 1`
- **And** MUST raise `HTTPException(422, {"error": "cantidad_maxima_excedida", "cantidad_maxima_vehiculos": 1, "placas_proporcionadas": 2}, headers=no_store_headers())`
- **And** NO `prod.subscripcion_vehiculos` rows MUST be INSERTed (V6 failure short-circuits before Step 9b).

---

### REQ-OPS-089 — Placa duplicate detection (V4 — `suscripcion_duplicada_placa`)

**Source**: HU-F1.12 (V4) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
For each placa in `payload.placas`, the handler MUST call `repo.subscripcion_activa.resolve_active_subscription_for_exit(session, placa=<p>, uuid_sucursal=ctx.sucursal_uuid, fecha_salida=payload.fecha_inicio_cobertura)` (F1.7 reuse, return-truthy semantics — `found=True` when ANY active subscription exists at this branch for this placa). If the helper returns `found=True` for ANY placa, the handler MUST raise `HTTPException(422, {"error": "suscripcion_duplicada_placa", "placa": <offending_placa>, "uuid_sucursal": str(ctx.sucursal_uuid)}, headers=no_store_headers())`. The branch-pinned `WHERE uuid_sucursal == :this_branch` predicate (R22 defense-in-depth from F1.7) MUST be enforced — placas with active subscriptions at a DIFFERENT branch are accepted (cross-branch check NOT enforced in F1.12, deferred to a future cross-branch consistency HU).

**Rationale**: A placa cannot be subscribed twice at the same branch simultaneously (operator mis-clicks, fraudulent resubscription attempts). The reverse-direction reuse of `resolve_active_subscription_for_exit` is semantically equivalent to the F1.7 exit-check: "is there ANY active subscription for placa?" — F1.12 asks the same question before INSERTing the new subscription.

**Source**: `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py` lines 93-141 (`resolve_active_subscription_for_exit`); F1.7 REQ-OPS-039 (R22 branch-pinned predicate precedent); `plan.md` lines 1010-1054 (V4 mandate).

**Scenario 1: Placa new to branch — OK**
- **Given** a placa `ABC123` with NO active `prod.subscripciones_cliente` row at `ctx.sucursal_uuid=:s`
- **And** a payload with `placas: ["ABC123"]`
- **When** the handler Step 7 invokes `resolve_active_subscription_for_exit(session, placa="ABC123", uuid_sucursal=:s, fecha_salida=<fecha_inicio_cobertura>)`
- **Then** the helper MUST return `found=False` (no active subscription at this branch)
- **And** the handler MUST proceed to Step 8 (A-09 prorrateo calc).

**Scenario 2: Placa has active subscription at SAME branch — 422 `suscripcion_duplicada_placa`**
- **Given** an existing `prod.subscripciones_cliente` row `:sc1` with `uuid_cliente=:c1`, `uuid_sucursal=:s`, `uuid_tipo_subscripcion=:p`, `fecha_vencimiento='2026-12-31'` (active)
- **And** a `prod.vehiculos` row `:v` with `placa='ABC123'`
- **And** a `prod.subscripcion_vehiculos` row linking `:sc1` to `:v`
- **And** a new payload with `placas: ["ABC123"]`, `uuid_tipo_subscripcion=:p_new`, `uuid_cliente=:c2` (different cliente, same placa)
- **When** the handler Step 7 invokes `resolve_active_subscription_for_exit(session, placa="ABC123", uuid_sucursal=:s, fecha_salida=<new.fecha_inicio_cobertura>)`
- **Then** the helper MUST return `found=True` with `uuid_subscripcion=:sc1`
- **And** the handler MUST raise `HTTPException(422, {"error": "suscripcion_duplicada_placa", "placa": "ABC123", "uuid_sucursal": ":s"}, headers=no_store_headers())`
- **And** NO NEW `prod.subscripciones_cliente` row MUST be INSERTed (V4 failure short-circuits before Step 9).

**Scenario 3: Placa has active subscription at DIFFERENT branch — OK (cross-branch check not enforced in F1.12)**
- **Given** an existing `prod.subscripciones_cliente` row `:sc1` with `uuid_sucursal=:s_other` (different from `ctx.sucursal_uuid=:s_this`)
- **And** a `prod.vehiculos` row `:v` with `placa='ABC123'`
- **And** a new payload with `placas: ["ABC123"]`, `uuid_tipo_subscripcion=:p_new`
- **When** the handler Step 7 invokes `resolve_active_subscription_for_exit(session, placa="ABC123", uuid_sucursal=:s_this, fecha_salida=<new.fecha_inicio_cobertura>)`
- **Then** the helper MUST return `found=False` (the `:s_other` subscription is filtered out by the `WHERE uuid_sucursal == :this_branch` predicate)
- **And** the handler MUST proceed to Step 8 (cross-branch check is out of F1.12 scope; the new subscription is recorded at `:s_this` independently).

---

### REQ-OPS-090 — A-09 prorrateo calc and persistence (DEC-VENTA-03)

**Source**: HU-F1.12 (DEC-VENTA-03) · **Priority**: CRITICAL · **RFC 2119 keywords**: MUST

**Statement**:
The handler MUST compute the A-09 prorrateo at Step 8 via `repo_venta.calcular_prorrateo(plan=plan, fecha_inicio_cobertura=payload.fecha_inicio_cobertura)`. The formula: `valor_dia = plan.valor / plan.duracion_dias` (when `plan.duracion_dias > 0`, else `PlanDuracionDiasInvalidoError`); `dias_restantes_mes = (<last day of fecha_inicio_cobertura.month> - fecha_inicio_cobertura.day)` (calendar month after `fecha_inicio_cobertura`); `monto_proporcional = valor_dia * dias_restantes_mes` IF `fecha_inicio_cobertura.day > 15` ELSE `None` (no prorrateo before day 16). When `cobrar_ahora=true`, the handler MUST persist `monto_proporcional` in `prod.factura_detalle.valor_unitario` AND `prod.factura_detalle.subtotal` of the SINGLE detail row with `concepto='subscripcion_mensual_prorrateada'`, `cantidad=1`. When `cobrar_ahora=false`, the handler MUST NOT persist prorrateo anywhere — the prorrateo amount is returned in the response body's `monto_prorrateado` field only when `monto_proporcional is not None`, else `null`.

**Rationale**: plan.md line 460 explicitly: "no hay columna para el monto prorrateado en `subscripciones_cliente`. Se calcula al momento de la venta y el resultado sí queda persistido, pero en `factura_detalle.valor_unitario`/`subtotal` — no en la tabla de suscripción misma, que no necesita columna nueva." The decay rule (`day > 15`) is the plan.md trigger condition (line 1053 T2).

**Source**: `plan.md` line 460 (A-09 spec), line 1053 (T2 day > 15 trigger); `backend/packages/parkos_core/src/parkos_core/repo/factura.py::crear_factura_detalle_bulk` (F1.9 helper, reused with `concepto='subscripcion_mensual_prorrateada'`); `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 483-496 (`subscripciones_cliente` has NO prorrateo column by design).

**Scenario 1: `fecha_inicio_cobertura.day = 20` + `cobrar_ahora=true` — prorrateo persisted in `factura_detalle`**
- **Given** a plan `:p` with `valor=30000`, `duracion_dias=30`
- **And** a payload with `fecha_inicio_cobertura='2026-09-20'`, `cobrar_ahora=true`
- **When** the handler Step 8 invokes `calcular_prorrateo(plan=:p, fecha_inicio_cobertura='2026-09-20')`
- **Then** the helper MUST compute `valor_dia = 30000 / 30 = 1000.0` AND `dias_restantes_mes = (30 - 20) = 10` (September has 30 days)
- **And** MUST return `monto_proporcional = 1000.0 * 10 = 10000.0`
- **And** Step 8a (`_factura_sub_chain`) MUST persist `prod.factura_detalle` row with `concepto='subscripcion_mensual_prorrateada'`, `valor_unitario=10000.0`, `cantidad=1`, `subtotal=10000.0`
- **And** the response MUST include `monto_prorrateado=10000.0`.

**Scenario 2: `fecha_inicio_cobertura.day = 10` — no prorrateo, full `plan.valor` charged**
- **Given** a plan `:p` with `valor=30000`, `duracion_dias=30`
- **And** a payload with `fecha_inicio_cobertura='2026-09-10'`, `cobrar_ahora=true`
- **When** the handler Step 8 invokes `calcular_prorrateo(plan=:p, fecha_inicio_cobertura='2026-09-10')`
- **Then** the helper MUST detect `day=10` is NOT `> 15` and MUST return `monto_proporcional = None`
- **And** Step 8a MUST persist `prod.factura_detalle` row with `concepto='subscripcion_mensual'`, `valor_unitario=30000.0`, `cantidad=1`, `subtotal=30000.0` (full `plan.valor`, no prorrateo)
- **And** the response MUST include `monto_prorrateado=null` (no prorrateo applied).

**Scenario 3: `fecha_inicio_cobertura.day = 20` + `cobrar_ahora=false` — `monto_prorrateado` in response body only, no persistence**
- **Given** a plan `:p` with `valor=30000`, `duracion_dias=30`
- **And** a payload with `fecha_inicio_cobertura='2026-09-20'`, `cobrar_ahora=false` (deferred billing)
- **When** the handler Step 8 invokes `calcular_prorrateo(plan=:p, fecha_inicio_cobertura='2026-09-20')`
- **Then** the helper MUST return `monto_proporcional = 10000.0` (same calc as Scenario 1)
- **And** Step 8a MUST be SKIPPED (no `_factura_sub_chain` call because `cobrar_ahora=false`)
- **And** NO `prod.factura_detalle` row MUST be INSERTed with prorrateo (the prorrateo is NOT persisted when not charging)
- **And** the response MUST include `monto_prorrateado=10000.0` (informational, returned for the operator's records but NOT in the DB)
- **And** `uuid_factura` MUST be `null` in the response (no factura was created).

---

### REQ-OPS-XR5 — Defense in depth: 5 layers + single-commit AST walk

**Source**: HU-F1.12 (KD-VENTA-01 + KD-VENTA-02 + DEC-VENTA-05 + DEC-VENTA-06) · **Priority**: HIGH · **RFC 2119 keywords**: MUST

**Statement**:
F1.12 MUST apply the F1.10 + F1.11 defense-in-depth pattern (5 layers), each independently testable, with failure of any one layer contained by the other four:
- **Layer 1 — KD-3 issuer chain + permission gate**: `_venta_suscripcion_issuer_dep = requires_issuer("operador-", "admin-")` (FastAPI dependency) + permission `gestionar_clientes` inherited from the existing `clientes.py` factory mount via `router.include_router(...)` (DEC-VENTA-05).
- **Layer 2 — Tenant scope post-V1**: After resolving the target sucursal from `ctx.issuer_prefix`, if `ctx.issuer_prefix == "operador-"` and `ctx.sucursal_uuid != target_sucursal`, the handler MUST return `403 tenant_scope_violation` with `Cache-Control: no-store`. Admin (`admin-` prefix) bypasses.
- **Layer 3 — KD-VENTA-01 single-commit + KD-VENTA-02 plan lock**: AST walk `tests/static/test_venta_handler_single_commit.py` enforces EXACTLY ONE `await session.commit()` in the handler body. `SELECT FOR UPDATE` on `prod.tipo_subscripciones` (Step 2) precedes all other locks (REQ-OPS-084).
- **Layer 4 — Pydantic `extra='forbid'` + placa constraints + NIT DV validator**: `VentaSuscripcionCreate(_Base)` inherits `extra='forbid'` from `schemas/common.py` (blocks client smuggling of `uuid_sucursal`, `vigente_desde`, `estado`, `created_at`, `created_by`, `monto_prorrateado`, `valor_dia`, `dias_restantes_mes` — all server-derived). `placas: Annotated[list[str], Field(min_length=1, max_length=2)]` + per-placa `StringConstraints(min_length=1, max_length=16)` (REQ-OPS-086). NIT DV validator via `ClientesCreate._validar_nit_dv` (F1.9 REQ-OPS-058 reuse, DEC-VENTA-07 — `dv` is validated by Pydantic then discarded before INSERT).
- **Layer 5 — Handler 422/409/404 mapping + `Cache-Control: no-store`**: Every response (201 + 4xx + 5xx) carries `Cache-Control: no-store`. Success: `apply_no_store_header(response)`. Error: `HTTPException(headers=no_store_headers())`. Typed exceptions (`TipoSubscripcionNoVigenteError` 409, `TipoSubscripcionNoEncontradoError` 404, `SubscripcionDuplicadaPlacaError` 422, `TipoVehiculoIncompatibleError` 422, `CantidadMaximaExcedidaError` 422, `PlanDuracionDiasInvalidoError` 422, `PlacaFormatoInvalidoError` 422, `TipoVehiculoInvalidoError` 422, `NitInvalidoError` 422, `ClienteNoEncontradoError` 404, `TenantScopeViolationError` 403, `PermissionDeniedError` 403, `IdempotencyKeyRequiredError` 400, `IdempotencyConflictError` 409) map to the typed bodies documented in `schemas/clientes.py` §9.2. The pgcode / internal error code NEVER appears in response body, headers, or info+ logs.

**Rationale**: Defense in depth against accidental drift in any single layer. The AST walk is the F1.10 XR1 + F1.11 XR4 mirror for F1.12. The 5-layer pattern is the canonical backend invariant for multi-table atomic writes (F1.9 KD-FACT-01, F1.10 KD-FE-01, F1.11 KD-TKT-01).

**Source**: F1.9 REQ-OPS-058 (NIT DV validator precedent); F1.10 REQ-OPS-XR1 (single-commit AST walk precedent); F1.11 REQ-OPS-XR4 (insert-only AST walk precedent); `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py` lines 18-31 (`no_store_headers` + `apply_no_store_header`); `backend/packages/parkos_core/src/parkos_core/schemas/common.py::_Base` (`extra='forbid'`).

**Scenario 1: operador with `gestionar_clientes` + own branch — OK**
- **Given** an operador role granted `gestionar_clientes` permission via `prod.permisos_usuario`
- **And** `ctx.sucursal_uuid=:s` matching the operator's branch
- **And** a valid `VentaSuscripcionCreate` payload
- **When** the operador POSTs `/api/v1/clientes/venta-suscripcion`
- **Then** the request MUST pass Layer 1 (KD-3 issuer chain + permission gate) AND Layer 2 (tenant scope) AND reach the handler body
- **And** MUST return `201 Created` on the happy path.

**Scenario 2: operador with `gestionar_clientes` + DIFFERENT branch — 403 `tenant_scope_violation`**
- **Given** an operador role granted `gestionar_clientes` permission
- **And** `ctx.sucursal_uuid=:s_other` (operator's branch is `:s_other`, but the request's target sucursal is `:s_target != :s_other`)
- **When** the operador POSTs `/api/v1/clientes/venta-suscripcion`
- **Then** Layer 2 MUST reject with `403 Forbidden` and body `{"error": "tenant_scope_violation"}` and `Cache-Control: no-store`
- **And** NO DB writes MUST occur (handler body unreachable).

**Scenario 3: operador WITHOUT `gestionar_clientes` — 403 `permission_denied`**
- **Given** an operador role WITHOUT `gestionar_clientes` permission (e.g. role "operador-lectura")
- **When** the operador POSTs `/api/v1/clientes/venta-suscripcion`
- **Then** Layer 1 MUST reject with `403 Forbidden` and body `{"error": "permission_denied"}` and `Cache-Control: no-store`
- **And** Layer 2 (tenant scope) MUST NOT be evaluated (Layer 1 short-circuits first).

**Scenario 4: All responses (201 + 4xx + 5xx) carry `Cache-Control: no-store`**
- **Given** any response from `POST /api/v1/clientes/venta-suscripcion` (success or failure)
- **When** the response is emitted
- **Then** the `Cache-Control: no-store` header MUST be present on `201 Created`
- **And** MUST be present on `400 idempotency_key_required` / `403 tenant_scope_violation` / `403 permission_denied` / `404 tipo_subscripcion_no_encontrado` / `404 cliente_no_encontrado` / `409 tipo_subscripcion_no_vigente` / `409 idempotency_conflict` / `422 placa_formato_invalido` / `422 tipo_vehiculo_incompatible` / `422 cantidad_maxima_excedida` / `422 plan_duracion_dias_invalido` / `422 nit_dv_invalido` / `422 suscripcion_duplicada_placa` / `500 iva_no_configurado`
- **And** MUST be present on any uncaught 5xx (defense-in-depth).

---

## Cross-Cutting Requirements

The following XR requirements reaffirm F1.10's XR1..XR3 (issuer chain, tenant scope, idempotency, cache-control, AST walks) and the new XR5 specific to F1.12:

- **REQ-OPS-XR1 (mirror F1.9 + F1.10 + F1.11)** — Defense in depth: 5 layers. Layer (a) KD-3 issuer chain `requires_issuer("operador-", "admin-")`; Layer (b) permission check `gestionar_clientes` (inherited from factory mount per DEC-VENTA-05); Layer (c) tenant scope post-V1 — `operador-` issuer forbidden from cross-branch `target_sucursal != ctx.sucursal_uuid` (KD-S2 analog from F1.7); Layer (d) KD-VENTA-02 plan lock + KD-VENTA-01 single-commit (REQ-OPS-083 + REQ-OPS-084); Layer (e) handler 422/409/404 mapping. Each layer independently tested; failure of any one layer MUST be contained by the other 4.

- **REQ-OPS-XR2 (mirror F1.9 + F1.10 + F1.11)** — `Cache-Control: no-store` header on all responses from `POST /api/v1/clientes/venta-suscripcion` (201, 400, 403, 404, 409, 422, 5xx).

- **REQ-OPS-XR3 (mirror F1.10 + F1.11)** — KD-VENTA-01 single `await session.commit()` invariant per handler body. Multiple `commit()` calls, `session.begin_nested()`, or `SAVEPOINT` statements MUST NOT appear. AST walk `tests/static/test_venta_handler_single_commit.py` enforces the invariant for `venta_suscripcion`.

- **REQ-OPS-XR4 (mirror F1.11)** — Insert-only invariant AST walk on `[V]` tables (`prod.clientes`, `prod.vehiculos`, `prod.subscripciones_cliente`, `prod.subscripcion_vehiculos`). NO raw UPDATE/INSERT/DELETE on `[V]` tables outside `repo/venta_suscripcion.py` helpers + `repo/versioned.py::close_and_insert`. AST walk `tests/static/test_venta_handler_no_raw_dml.py` enforces the invariant.

- **REQ-OPS-XR5 (NEW for F1.12)** — F1.12 defense-in-depth 5-layer contract: KD-3 issuer chain + `gestionar_clientes` permission gate (Layer 1) + tenant scope post-V1 (Layer 2) + KD-VENTA-01 single-commit + KD-VENTA-02 plan lock (Layer 3) + Pydantic `extra='forbid'` + placa constraints + NIT DV validator (Layer 4) + handler 422/409/404 mapping + `Cache-Control: no-store` on every response (Layer 5).

---

## Definition of Done (entire HU-F1.12)

- [ ] New module `api/v1/clientes_venta.py` mounted under `/clientes` prefix via `router.include_router(venta_suscripcion_router)` in `api/v1/clientes.py` (DEC-VENTA-05).
- [ ] `POST /api/v1/clientes/venta-suscripcion` handler with 10-step chain (Steps 1-10) covering all 8 REQ-OPS-083..090 + XR5 contracts.
- [ ] New `repo/venta_suscripcion.py` (NEW, ~150 LOC) with helpers `buscar_cliente_por_uuid_o_crear`, `buscar_tipo_subscripcion_vigente_por_uuid`, `buscar_o_crear_vehiculo_por_placa`, `validar_placas_mismo_tipo_vehiculo`, `validar_cantidad_maxima_vehiculos`, `validar_placa_duplicada_subscripcion`, `calcular_prorrateo`, `crear_subscripcion_cliente`, `crear_subscripcion_vehiculos_bulk`, optional `_factura_sub_chain`, optional `_fe_sub_chain`.
- [ ] Pydantic schemas `VentaSuscripcionCreate` + `VentaSuscripcionResponse` + 7 typed error schemas appended to `schemas/clientes.py` (§9.1, §9.2).
- [ ] MIGRATION 0030 applied: NO-OP audit trail (pre-flight DO $$ asserts all 5 [V] tables exist; `upgrade()` + `downgrade()` no-ops).
- [ ] All 8 new REQ-OPS-083..090 implemented + verified.
- [ ] REQ-OPS-XR5 5-layer defense + AST walk PASSES.
- [ ] ~14 tests across 7 test files + 2 AST walks + 1 migration test PASS:
  - `tests/unit/test_venta_suscripcion.py` (4 tests, mandated by plan.md line 1047)
  - `tests/unit/test_venta_suscripcion_repo.py` (3 tests)
  - `tests/unit/test_venta_suscripcion_schemas.py` (2 tests)
  - `tests/integration/test_venta_suscripcion_e2e.py` (1 test)
  - `tests/static/test_venta_handler_single_commit.py` (1 AST walk — XR3)
  - `tests/static/test_venta_handler_no_raw_dml.py` (1 AST walk — XR4)
  - `tests/integration/test_migration_0030_noop.py` (1 test)
- [ ] `Cache-Control: no-store` verified on 201 / 400 / 403 / 404 / 409 / 422 / 5xx responses.
- [ ] KD-VENTA-01 single-commit invariant verified per handler via AST walk.
- [ ] KD-VENTA-02 plan lock ordering verified (plan before cliente) via concurrent integration test.
- [ ] Tenant scope post-V1 verified (operador- cross-branch → 403 `tenant_scope_violation`).
- [ ] A-09 prorrateo persistence verified (`factura_detalle.valor_unitario`/`subtotal` when `cobrar_ahora=true` AND `fecha_inicio_cobertura.day > 15`).
- [ ] `Idempotency-Key` HTTP header supported (DEC-IDEM-01 reuse from F1.6 + F1.9 + F1.10 + F1.11).
- [ ] No AI attribution in commits (no `Co-authored-by:`, no AI trailers).

---

## References

- `openspec/changes/hu-f1-12-venta-suscripcion/proposal.md` (~485 LOC, 16 sections, DEC-VENTA-01..07 + DEC-VENTA-08 WITHDRAWN, KD-VENTA-01..02, 8 REQ-OPS-083..090 + XR5 placeholders, MIGRATION 0030 NO-OP, ~14 tests + 2 AST walks, 5-layer defense)
- `plan.md` lines 1010-1054 (HU-F1.12 definition, 3 atomic tasks T1..T3, 4 tests mandated at line 1047, 260 LOC production budget)
- `plan.md` line 460 (A-09 prorrateo — no `monto_prorrateado` column on `subscripciones_cliente`)
- `plan.md` lines 1016, 1053 (scope decision: "ampliación de producto" + A-09 decay rule day > 15)
- `modelo_datos_er.mmd` line 105 (`tipo_subscripciones`), 449 (`clientes`), 496 (`subscripciones_cliente`), 519 (`vehiculos`), 538 (`subscripcion_vehiculos`)
- `modelo_datos_er.mmd` lines 1138-1145 (FK relationships: `clientes → subscripciones_cliente`, `tipo_subscripciones → subscripciones_cliente`, `subscripciones_cliente → subccion_vehiculos`, `vehiculos → subccion_vehiculos`)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines 195-210 (`tipo_subscripciones`), 435-452 (`clientes`), 454-465 (`vehiculos`), 483-496 (`subscripciones_cliente`), 498-509 (`subscripcion_vehiculos`)
- `backend/packages/parkos_core/migrations/versions/0029_reimpresion_siembra_and_permiso_anular.py` (current head; F1.12 will be migration `0030`)
- `backend/packages/parkos_core/src/parkos_core/sync/catalog/entries/sync_entries_v.py` lines 133-147 (`tipo_subscripciones`), 451-465 (`clientes`), 483-500 (`vehiculos`), 511-523 (`subscripciones_cliente`), 525-552 (`subscripcion_vehiculos`) — **all 5 [V] entries verified pre-existing 2026-09-15**
- `backend/packages/parkos_core/src/parkos_core/models/V/{clientes,vehiculos,tipo_subscripciones,subscripciones_cliente,subscripcion_vehiculos}.py` (ORM models, all existing)
- `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (F1.9 atomic 4-table cobro chain — `crear_factura_evento` + `crear_factura_detalle_bulk` + `crear_factura_impuesto_iva` + `crear_factura_pago`)
- `backend/packages/parkos_core/src/parkos_core/repo/factura_electronica.py` + `repo/resolucion_facturacion.py::assign_consecutivo` (F1.10 atomic 2-table FE chain)
- `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py::resolve_active_subscription_for_exit` (F1.7, lines 93-141 — reused for V4 placa-dup detection)
- `backend/packages/parkos_core/src/parkos_core/repo/placa.py` (F1.6 `FORMATO_AUTO` + `FORMATO_MOTO` + `detectar_tipo_vehiculo` — reused for V3 + V5)
- `backend/packages/parkos_core/src/parkos_core/repo/versioned.py::close_and_insert` (lines 45-196 — bi-temporal writer for `[V]` tables)
- `backend/packages/parkos_core/src/parkos_core/repo/idempotency.py` (DEC-IDEM-01 reuse)
- `backend/packages/parkos_core/src/parkos_core/api/v1/_helpers.py::no_store_headers()` + `apply_no_store_header()` (lines 18-31)
- `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py` (`ClientesCreate._validar_nit_dv` lines 82-102 — F1.9 REQ-OPS-058 NIT validator reused)
- `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (F1.9 lines 216-380 — canonical 12-step atomic create handler, shape verbatim for optional cobro sub-chain)
- `backend/packages/parkos_core/src/parkos_core/api/v1/workflows_reimpresion.py` (F1.11 dedicated-router + KD-3 + tenant scope + Idempotency-Key pattern)
- `openspec/specs/operations/spec.md` (80 REQs REQ-OPS-001..080 + XR1..XR4 merged post-F1.11 — target for REQ-OPS-083..090 + XR5 merge on archive)
- `openspec/changes/archive/2026-09-15-hu-f1-11-reimpresion-tiquete/specs/operations/spec.md` (canonical Given/When/Then/And format precedent; 7 REQs REQ-OPS-075..080 + XR4)

---

**End of delta spec — HU-F1.12.**