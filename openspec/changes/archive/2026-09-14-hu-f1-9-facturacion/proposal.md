# Proposal: HU-F1.9 — Facturación transaccional + NIT módulo 11

> **Change**: `hu-f1-9-facturacion`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.9 (Fase-1 prerequisites — backend)
> **Inputs**: `openspec/changes/hu-f1-9-facturacion/exploration.md` (16 sections, ~670
> LOC, written 2026-09-14), `plan.md` (HU-F1.9 lines 891-935 — 330 LOC, 4 tasks
> T1..T4; HU-F1.9 in CU-04 context line 7672, table impact lines 2630-2637,
> endpoint table lines 2403-2407), `modelo_datos_er.mmd` (`prod.facturas` 667-687
> `[L-E]`, `prod.factura_detalle` 780-794 `[A]`, `prod.factura_impuestos`
> `[A]`, `prod.factura_pagos` 843-861 `[A]`, `prod.factura_electronica` 689-705
> `[L-E]`, `prod.clientes` 449-472 `[V]`, `prod.impuestos` 187-207 `[V]`,
> `prod.tarifas_sucursal` 406-426 `[V]`, `prod.salidas` 761-777 `[A]`,
> `prod.ingreso` 577-596 `[L-E]`),
> `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/{exploration,proposal,design,tasks,verify-report,archive-report}.md`
> (precedente KD-FORZADO-01 verbatim reuse + KD-7 pre-flight + 12-step handler
> pattern, commit `c320d0f`+`aa2fc9b`+`f826e8c`),
> `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/{exploration,proposal,design,tasks}.md`
> (precedente PL/pgSQL VOLATILE `calcular_cotizacion` + `FOR SHARE` lock continuity,
> commit `a3d0c39`),
> `openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/{proposal,design,tasks}.md`
> (precedente KD-FORZADO-01 prefix contract verbatim, commit `2a2cbd2`),
> `openspec/specs/operations/spec.md` (52 REQs REQ-OPS-001..052 merged, REQ-OPS-042..052
> from F1.7 already merged),
> `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (lines
> 435-452 `clientes`, 607-654 `facturas`+`factura_detalle`, 688-717 `factura_pagos`,
> 875-891 `factura_electronica`, 1378 `fk_facturas_uuid_salida`, 2024-2088
> `fn_*_inmutable` triggers).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend`
> (HEAD `def754d`) · **PR target**: `origin/dev`.
> **Language note**: artifact authored in English per the project's `Language
> Domain Contract` (default for technical SDD artifacts). DEC-FACT-NN identifiers
> follow the F1.7 + F1.6 DEC-SUC / DEC-SAL / DEC-FORZADO / DEC-MONO / DEC-IMP
> naming pattern. KD-FACT-NN follow the F1.7 KD-S + KD-1 pattern.

---

## 1. Why

Until F1.7 (archived `c320d0f`+`aa2fc9b`+`f826e8c`), `prod.salidas` is closed but
`prod.facturas` is never created. Until F1.8 (archived `a3d0c39`),
`prod.calcular_cotizacion(p_uuid_ingreso)` returns the fiscal breakdown but no
endpoint consumes it for billing. The cash register terminal at a parking branch
has no server-side enforcement of the "issue a factura" flow — the operator's UI
must either replicate the fiscal derivation client-side (reintroducing the same
bug class F1.6 fixed for ingresos) or rely on undocumented internal procedures.
**The backend performs zero business validation on billing.**

`plan.md` lines 891-935 specify the deliverables for HU-F1.9 (CU-04 Facturación
close, 330 LOC): `POST /facturacion/factura` (transaccional atómico:
`facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos` in **one**
`await session.commit()`) and `POST /facturacion/factura-pagos` (validación
`voucher_requerido` cuando `medio_pago='datafono'`), plus the módulo 11 NIT
validator wired at Pydantic v2 layer on `ClientesCreate` and on
`FacturaItemConDatosPropios`. The 4 atomic tasks T1..T4 mirror the 330 LOC
budget (≈50 LOC handler `create_factura` + 80 LOC handler `create_factura_pagos`
+ 100 LOC `repo/factura.py` + 50 LOC `repo/nit_modulo11.py` + 50 LOC schemas
nuevos — **NO migration nueva preferentemente** — + ~700 LOC tests).

This creates five concrete risks that HU-F1.9 resolves:

1. **Cash register cannot emit facturas**. Today `prod.facturas` exists in
   migration 0001 (lines 607-654) but no handler creates rows. Without server-side
   enforcement, the cashier's terminal duplicates the fiscal derivation logic
   client-side or — worse — emits hand-typed invoices that bypass the fiscal
   snapshot. CU-04 (Facturación) is functionally closed in plan.md §4 only when
   `POST /facturacion/factura` returns `201` with a `FacturaRead` carrying
   `subtotal`, `descuento`, `total` server-side-derived from the cotizacion snapshot.
   Risk: accounting cannot reconcile, DIAN reporting is broken, customer requests
   for facturas for tax purposes cannot be fulfilled (regulatory exposure).
2. **Atomicidad violation across 4 tables**. Without KD-FACT-01 (single-commit
   invariant), a partial failure between `facturas` insert and `factura_detalle`
   bulk insert leaves orphan `facturas` rows with no detail lines, breaking
   accounting reconciliation. Defense-in-depth at DB layer (`fn_*_inmutable`
   triggers on `factura_detalle`, `factura_impuestos`, `factura_pagos` per
   migration 0001 lines 2024-2088) cannot substitute for application-level
   atomicity. The single `await session.commit()` materializes all 4 tables
   in one TX; AST walk `test_factura_handler_single_commit.py` enforces the
   invariant literally (`len(commits) == 1`).
3. **Tarifa race window between cotizar and cobrar**. F1.8 holds `SELECT … FOR
   SHARE` on `tarifas_sucursal` inside `prod.calcular_cotizacion` (KD-1 in F1.8,
   VOLATILE per REQ-OPS-025). HU-F1.9 must NOT call `calcular_cotizacion`
   (snapshot was already taken at salida time in F1.7); however, F1.9 must take
   its own `SELECT … FOR SHARE` over the `tarifas_sucursal` rows referenced by
   `factura_detalle.uuid_tarifa_sucursal` (KD-FACT-02) to close the window
   between the snapshot read in `create_factura` and the INSERT into
   `factura_detalle`.
4. **NIT validation gap (DIAN regulatory exposure)**. The Colombian NIT check
   digit MUST be validated against the algoritmo de módulo 11 per DIAN
   Resolución 000175 de 2021. Without `validar_nit_modulo11` wired at the
   Pydantic v2 layer on both `ClientesCreate` (always when
   `tipo_identificador='NIT'`) and `FacturaItemConDatosPropios` (only when
   `fe_con_datos=true`), the cashier's terminal accepts NITs with mismatched
   DV, generating facturas the DIAN rejects on audit. R1 risk: the algorithm
   exists in two variants in Colombian regulation (Variant A: `DV = sum % 11`,
   Variant B: `DV = 11 - (sum % 11)`); the canonical DIAN spec mandates Variant A.
5. **Concurrent cashier race on the same `uuid_salida`**. Two cashiers might
   attempt to invoice the same closed salida simultaneously. Without the
   partial unique index `one_pago_per_factura_init` on `prod.factura_pagos`
   (matching the F1.7 `one_exit_per_ingreso` pattern), the TOCTOU window opens.
   F1.9 introduces a conditional MIGRATION 0027 if the index does not exist
   pre-apply.

F1.9 closes the billing half of CU-04 (F1.10 closes FE numbering + DIAN state on
top). The work is **handler + repo + schemas + módulo 11 helper + a CONDITIONAL
migration** — the migration is critical only if `fn_facturas_inmutable` trigger
and/or `one_pago_per_factura_init` partial unique index are missing in migration
0001. The 6-operation breakdown with explicit pre-flight (KD-7 pattern from F1.6
migration 0024, F1.7 migration 0026) is documented in §2 and §6. Defense in depth
has 5 layers: DB triggers + partial index + repo typed exceptions + handler
12-step chain + AST walks (KD-FACT-01 + KD-FACT-02 invariants).

The handler enforces 6 validations (V1 salida facturable, V2 cliente existe
when `fe_con_datos=true`, V3 IVA configurado, V4 detalle items coherentes, V5 NIT
módulo 11 cuando `fe_con_datos=true`, V6 total coherente ±0.01 COP), inserts
the 4 tables in a single TX, and returns `201` with a `FacturaRead` whose
`uuid_cliente` is **derived server-side** (DEC-FACT-06, not persisted). A
secondary endpoint `POST /facturacion/factura-pagos` handles voucher validation
for datáfono (`400 voucher_requerido` when `medio_pago='datafono'` sin
`referencia`). Adjacent reads (`GET /facturacion/facturas/{uuid}`, `GET
/facturacion/facturas?uuid_cliente=...&fecha_desde=...&fecha_hasta=...`) are
proposed but lower priority for F1.9.

---

## 2. What Changes

### 2.1 Decisions (DEC-FACT-01..09 + KD-FACT-01..02 + KD-NIT-01..07)

| # | Decision | Rationale |
|---|---|---|
| **DEC-FACT-01 (KD-FACT-01)** | Single `await session.commit()` materializes `facturas` + `factura_detalle` (N rows) + `factura_impuestos` (1 row) + `factura_pagos` (1 row) **atomically**; AST walk `tests/static/test_factura_handler_single_commit.py` enforces `len(commits) == 1` literal | Analogue of KD-S7 in F1.7 (`commit()` materializes salida + alerta atomically); same pattern as F1.6 single-commit chain. Defense in depth against partial failures (R2 risk class). |
| **DEC-FACT-02 (KD-FACT-02)** | `SELECT … FOR SHARE` per-row over `prod.tarifas_sucursal` for every row in `factura_detalle.uuid_tarifa_sucursal` referenced **before** the bulk INSERT; lock held until `session.commit()` | Analogue of KD-1 in F1.8 (FOR SHARE per row inside `calcular_cotizacion`); per-row scope prevents global serialization. Alternative "lock-free" rejected — opens window of inconsistency between snapshot read and INSERT. |
| **DEC-FACT-03** | IVA read from `prod.impuestos` ONLY; no hardcoded constants in Python; if DIAN changes the IVA, an INSERT into `prod.impuestos` with new `porcentaje` suffices | DEC-IMP-01 from F1.7 applies equally to F1.9; `validar_iva_configurado` reused verbatim from `repo/impuestos.py` (F1.7). 500 `iva_no_configurado` post-0026 deploy: never. |
| **DEC-FACT-04** | MVP F1.9 NO aplica retención (RETCONT 11% sobre servicios). Razones: `prod.retencion` NO existe en DB (gap pre-existente); sin la tabla, NO se puede snapshotear el porcentaje RETCONT ni el `concepto`; ownership del catálogo de retenciones está fuera del corpus actual | RECOMMENDED defer to Fase 4 (contabilidad). V6 `compute_total` accepts `retencion=Decimal("0")` in MVP. Documented as "to extend" in design.md, not implemented. |
| **DEC-FACT-05** | `prod.facturas` does NOT receive `prefijo` + `consecutivo` (those live in `factura_electronica`, F1.10 owns). F1.9 creates the internal factura with `uuid` and returns it to the client | Analogue of DEC-SUC-21-NEW from F1.7 for the `prefijo`/`consecutivo` derivation; the `assign_consecutivo` Python helper (existing, branch-local with `SELECT … FOR UPDATE` on `resolucion_facturacion`) is reused as-is in F1.10, NOT modified here. |
| **DEC-FACT-06** | `uuid_cliente` is **NOT** a column in `prod.facturas`. Confirmed in migration 0001: only `uuid_sucursal`, `subtotal`, `descuento`, `total`, `uuid_ingreso`, `uuid_salida` exist. The `FacturaRead` includes `uuid_cliente` as a **server-derived** field via lookup `salidas.uuid_ingreso` → `ingreso.placa` → `vehiculos.placa` → opcionalmente `clientes` por `numero_identificacion` del payload | 4FN / no FK in MVP; DEC-FACT-06 mirrors DEC-SUC-21-NEW (server-derived, never persisted). Future HU may add `prod.facturas.uuid_cliente` FK and backfill; F1.9 does NOT create the FK. |
| **DEC-FACT-07 Opción A** | NO crear `prod.forma_pago` catálogo. `prod.factura_pagos.medio_pago` is `String()` libre; Pydantic v2 `Literal["efectivo","tarjeta","transferencia","datafono","mixto"]` enforced. RECOMMENDED for MVP | Trade-off: -120 LOC vs. Opción B (create `prod.forma_pago [V]` migration 0027). Opción A is sufficient for F1.9; future HU may create the table if reporting/analytics need a normalized catalog. |
| **DEC-FACT-08** | If `fe_con_datos=false` (consumidor final), the handler does NOT create nor require a cliente. The factura is emitted as "consumidor final" with NIT genérico `222222222222` (DIAN convention) | Mirrors the existing `consumidor_final` UX in the operator's terminal. No new cliente row; no FK lookup. |
| **DEC-FACT-09 (KD-NIT-01)** | NIT módulo 11 algorithm is canonical per DIAN Resolución 000175 de 2021. Helper `validar_nit_modulo11(nit, dv) -> bool` enforces weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]` applied **right-to-left** on NIT digits (without DV); DV = `sum_ponderada % 11` (Variant A — DIAN canonical, NOT `11 - (sum % 11)` Variant B). Helper also normalizes NIT (strip non-digits, strip leading zeros, minimum 5 digits). NO alternative algorithms permitted. | R1 mitigation (CRITICAL): pre-apply verify against test case `800.123.456-7` which discriminates Variants A vs B. `dv_esperado` helper exposed for the 422 `nit_invalido` body to include `dv_esperado` and `dv_recibido`. |

### 2.2 Goals & Non-Goals

**Goals**:

1. Expose **two** handlers: `POST /api/v1/facturacion/factura` (12-step chain) +
   `POST /api/v1/facturacion/factura-pagos` (5-step chain). Both atomic, both
   returning 201/4xx/5xx with `Cache-Control: no-store`.
2. Enforce 6 validations server-side: V1 salida facturable, V2 cliente cuando
   `fe_con_datos=true`, V3 IVA configurado, V4 detalle items coherentes, V5 NIT
   módulo 11 cuando `fe_con_datos=true`, V6 total coherente ±0.01 COP.
3. Materialize 4 tables (`facturas` + `factura_detalle` + `factura_impuestos` +
   `factura_pagos`) in ONE `await session.commit()` (KD-FACT-01). AST walk
   enforces literal `len(commits) == 1`.
4. Take `SELECT … FOR SHARE` per-row on every `prod.tarifas_sucursal` referenced
   by `factura_detalle.uuid_tarifa_sucursal` before the bulk INSERT (KD-FACT-02).
   Lock held until `session.commit()`.
5. Reuse `repo/impuestos.py::validar_iva_configurado` (F1.7) verbatim for V3.
6. Wire `validar_nit_modulo11` helper (~50 LOC) at Pydantic v2 layer on
   `ClientesCreate.numero_identificacion` (always when
   `tipo_identificador='NIT'`) and on
   `FacturaItemConDatosPropios.numero_identificacion` (only when
   `fe_con_datos=true`).
7. Derive `uuid_cliente` server-side in `FacturaRead` (DEC-FACT-06); do NOT
   add `prod.facturas.uuid_cliente` FK column.
8. Apply **`Cache-Control: no-store`** to all 2xx/4xx/5xx responses (precedent
   F1.3/F1.5/F1.6/F1.7/F1.8 R8).
9. Return `400 voucher_requerido` for `POST /facturacion/factura-pagos` when
   `medio_pago='datafono'` and `referencia` is empty (R-KD-FACT-07).
10. Mount `facturacion.router` in `api/v1/__init__.py` via
    `r.include_router(facturacion.router)` (new line, same pattern as the
    `operacion.router` line).
11. **CONDITIONAL** MIGRATION 0027 (~80 LOC) introduced ONLY if
    `fn_facturas_inmutable` trigger and/or `one_pago_per_factura_init` partial
    unique index are missing pre-apply. Pre-apply verification:
    `grep "fn_facturas_inmutable" migrations/` and `grep "one_pago_per_factura_init"
    migrations/`. If both present in 0001, no migration needed.
12. Maintain strict 12-step order with AST walk
    `tests/static/test_factura_handler_step_order.py` locking the literal helper
    invocation order.
13. Cover with ~14 tests: 6 HTTP unit (rotación + consumidor final + NIT válido
    + NIT inválido + detalle vacío + total no coherente) + 4 NIT helper unit
    (DIAN reference + DV mismatch + leading zeros + dots/dashes) + 2 factura-pagos
    HTTP unit (datáfono sin/con referencia) + 2 DB integration (atomic rollback
    + FOR SHARE lock verification) + 2 AST walks (single-commit + step order).
14. Defense-in-depth with 5 layers: (a) DB `fn_*_inmutable` triggers +
    conditional `fn_facturas_inmutable`; (b) DB partial unique index
    `one_pago_per_factura_init`; (c) repo typed exceptions
    (`SalidaNoFacturableError`, `ClienteNoEncontradoFacturaError`,
    `NitInvalidoError`, `TotalNoCoherenteError`, `VoucherRequeridoError`); (d)
    handler 12-step chain + single commit + tenant scope post-V1; (e) AST walk
    single-commit + step order.

**Non-Goals**:

1. NO `POST /facturacion/factura-electronica` (F1.10 owns FE numbering +
   estado DIAN).
2. NO `prod.retencion` table creation in MVP (DEC-FACT-04 — deferred to Fase 4).
3. NO `prod.forma_pago` catálogo in MVP (DEC-FACT-07 Opción A — Pydantic Literal
   enforced, no DB catalog).
4. NO `prod.facturas.uuid_cliente` FK column (DEC-FACT-06 — derived server-side).
5. NO `assign_consecutivo` enhancements (F1.10 owns — branch-local Python helper
   with `SELECT … FOR UPDATE` on `resolucion_facturacion` reused as-is).
6. NO new cliente creation when `fe_con_datos=true` and cliente does not exist
   (V2 returns 404 `cliente_no_encontrado` — caller decides whether to retry
   with `clientes` endpoint first; F1.9 does NOT auto-create).
7. NO anulación of `prod.facturas` (DEC-FACT-01 — append-only; corrections via
   `prod.anulaciones(tipo_anulable='factura')` workflow — Fase 7+).
8. NO modifications to `prod.calcular_cotizacion` PL/pgSQL (F1.8 VOLATILE
   function untouched; F1.9 reads the cotizacion snapshot indirectly via
   `prod.salidas` derived data, not via the PL/pgSQL).
9. NO modifications to `IdempotencyKeyMiddleware` (PR2); F1.9 accepts same
   pattern as F1.7 — retries deduped by header; partial unique index handles
   concurrent cashier race.
10. NO `correlacion_id` in payload (DEC-IDEM-01 reuse from F1.6).
11. NO `prod.factura_electronica` modifications (F1.10 owns).
12. NO cleanup of client-side `uuid_cliente` derivation (Fase 2 frontend — post-
    archive cleanup).
13. NO `GET /facturacion/facturas/{uuid}` adjacent read endpoint in this HU
    (proposed, lower priority; F1.9 focuses on the 2 POST endpoints).
14. NO `GET /facturacion/facturas?uuid_cliente=...&fecha_desde=...&fecha_hasta=...`
    paginated list endpoint in this HU (proposed, lower priority).

### 2.3 Architecture Overview

```
HTTPS POST /api/v1/facturacion/factura
        Body: FacturaCreate
        │      {uuid_salida, items[], subtotal, total, medio_pago,
        │       referencia?, fe_con_datos?, fe_datos_cliente?}
        │  requires_issuer("admin-", "cajero-")   Cache-Control: no-store
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/facturacion.py  (NEW, ~150 LOC)                                       │
│                                                                              │
│ @router.post("/factura", response_model=FacturaRead, status_code=201)       │
│ async def create_factura(response, payload, session, ctx, _claims)           │
│                                                                              │
│  1. KD-3 (issuer claims):                                                    │
│      _claims = requires_issuer("admin-", "cajero-")                          │
│      ctx = get_tenant_ctx from JWT                                            │
│                                                                              │
│  2. V1 salida existe (busada no facturable si ya facturada):                  │
│      salida = await repo_factura.buscar_salida_facturable(                  │
│          session, uuid_salida=payload.uuid_salida)                            │
│      if salida is None:                                                      │
│          raise 404 {"error":"salida_no_encontrada", "uuid_salida":...}      │
│                                                                              │
│  3. Tenant scope (post-V1, KD-S2 analog from F1.7):                          │
│      target_sucursal = salida.uuid_sucursal                                   │
│      if ctx.issuer_prefix == "cajero-" and target != ctx.sucursal_uuid:     │
│          raise 403 {"error":"tenant_scope_violation"}                        │
│                                                                              │
│  4. V2 cliente existe cuando fe_con_datos=true:                              │
│      cliente_uuid: UUID | None = None                                        │
│      if payload.fe_con_datos:                                                │
│          cliente = await repo_factura.buscar_o_crear_cliente_por_nit(       │
│              session, numero_identificacion=payload.fe_datos_cliente.numero, │
│              datos=payload.fe_datos_cliente)                                 │
│          if cliente is None:                                                 │
│              raise 404 {"error":"cliente_no_encontrado"}                     │
│          cliente_uuid = cliente.uuid                                         │
│                                                                              │
│  5. V3 IVA configurado:                                                      │
│      if not await repo_impuestos.validar_iva_configurado(session):          │
│          raise 500 {"error":"iva_no_configurado"}                            │
│                                                                              │
│  6. V4 detalle items coherentes:                                             │
│      items_validados = repo_factura.validar_items(payload.items)             │
│      if not items_validados:                                                 │
│          raise 422 {"error":"detalle_invalido", "min_items": 1}              │
│                                                                              │
│  7. KD-FACT-02 lock FOR SHARE per-row:                                       │
│      await repo_factura.lock_tarifas_sucursal_para_items(                    │
│          session, items=items_validados)                                     │
│                                                                              │
│  8. V6 server-side recompute total (±0.01 COP):                               │
│      total_server = repo_factura.compute_total(                             │
│          items=items_validados, iva=Decimal("0.19"),                         │
│          retencion=Decimal("0"))                                              │
│      if abs(total_server - payload.total) > Decimal("0.01"):                │
│          raise 422 {"error":"total_no_coherente",                            │
│              "total_recibido":..., "total_calculado":...,                    │
│              "diferencia":...}                                                │
│                                                                              │
│  9. INSERT prod.facturas [L-E]:                                              │
│      new_factura = await repo_factura.crear_factura_evento(                  │
│          session, actor_uuid=ctx.actor_uuid,                                 │
│          new_attrs={                                                         │
│              "uuid_sucursal": target_sucursal,                               │
│              "uuid_ingreso": salida.uuid_ingreso,                            │
│              "uuid_salida": salida.uuid,                                     │
│              "subtotal": payload.subtotal,                                    │
│              "descuento": Decimal("0"),                                       │
│              "total": payload.total,                                          │
│          })                                                                  │
│                                                                              │
│ 10. INSERT factura_detalle (N rows) + factura_impuestos (1 row) +           │
│     factura_pagos (1 row):                                                   │
│      await repo_factura_detalle.crear_factura_detalle_bulk(                  │
│          session, uuid_factura=new_factura.uuid, items=items_validados)      │
│      await repo_factura.crear_factura_impuesto_iva(                          │
│          session, uuid_factura=new_factura.uuid, base=total_server)           │
│      new_pago = await repo_factura.crear_factura_pago(                       │
│          session, uuid_factura=new_factura.uuid,                              │
│          medio_pago=payload.medio_pago,                                      │
│          valor=payload.total,                                                │
│          referencia=payload.referencia,                                       │
│          uuid_sesion=ctx.uuid_sesion)                                         │
│                                                                              │
│ 11. KD-FACT-01 single commit:                                                │
│      await session.commit()    ◄── UN solo commit (lock release)             │
│                                                                              │
│ 12. Response shape:                                                          │
│      apply_no_store_header(response)                                         │
│      await session.refresh(new_factura)                                      │
│      return FacturaRead(                                                     │
│          uuid=new_factura.uuid, ... +                                        │
│          uuid_cliente=cliente_uuid (DEC-FACT-06 derivado, no persistido),     │
│          items=[FacturaItemRead(...) for each item],                          │
│          estado="emitida",                                                   │
│      )                                                                       │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                                       ▲
        │ AST walk single-commit                 │ AST walk step order
        │ (KD-FACT-01)                           │ (literal 12-step)
test_tests/static/test_factura_handler_single_commit.py
test_tests/static/test_factura_handler_step_order.py
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Repo helpers (NEW):                                                          │
│   repo/factura.py             (~250 LOC) — 9 helpers + 5 typed exceptions   │
│   repo/factura_detalle.py     (~80 LOC) — bulk insert helper                │
│   repo/nit_modulo11.py        (~50 LOC) — DIAN módulo 11 helper             │
│                                                                              │
│ Repo helpers (REUSED verbatim, NO modify):                                   │
│   repo/impuestos.py           (F1.7) — validar_iva_configurado             │
│   repo/versioned.py          (F1.5) — close_and_insert (V2 cliente path)    │
│                                                                              │
│ Schemas (MODIFY):                                                            │
│   schemas/facturacion.py     (+80 LOC) — FacturaCreate, FacturaRead,         │
│                                       FacturaItemCreate, FacturaItemRead,   │
│                                       FacturaPagoAdicionalCreate,            │
│                                       FacturaPagoRead, 4 typed errors       │
│   schemas/clientes.py        (+10 LOC) — Pydantic v2 @field_validator        │
│                                       on numero_identificacion when         │
│                                       tipo_identificador='NIT'              │
│                                                                              │
│ Tablas operacionales (READ + INSERT, NO migration preferida):                │
│   prod.salidas                  [A]    — V1 read PK                          │
│   prod.ingreso                  [L-E]  — V1 derivado uuid_ingreso            │
│   prod.clientes                 [V]    — V2 SELECT/INSERT condicional        │
│   prod.impuestos                [V]    — V3 read IVA%                        │
│   prod.tarifas_sucursal         [V]    — KD-FACT-02 SELECT FOR SHARE per-row│
│   prod.facturas                 [L-E]  — Step 9 INSERT (DEC-FACT-06: NO uuid_cliente column) │
│   prod.factura_detalle          [A]    — Step 10 bulk INSERT                 │
│   prod.factura_impuestos        [A]    — Step 10 INSERT (IVA snapshot)       │
│   prod.factura_pagos            [A]    — Step 10 INSERT (1 pago)             │
│   prod.factura_electronica      [L-E]  — NO TOCADO (F1.10 owns)              │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲
        │
        ▼ CONDITIONAL MIGRATION 0027 (only if pre-apply verify finds gaps)
┌──────────────────────────────────────────────────────────────────────────────┐
│ migrations/versions/0027_facturas_inmutable_trigger.py (~80 LOC)            │
│                                                                              │
│ Pre-apply verification (run before authoring migration):                     │
│   grep "fn_facturas_inmutable" migrations/                                   │
│   grep "one_pago_per_factura_init" migrations/                                │
│                                                                              │
│ IF both grep return 0 matches:                                               │
│   Migration 0027 introduces:                                                  │
│     Op 1 — pre-flight DO $$ (verify prod.facturas,                          │
│                                  prod.factura_pagos tables exist)            │
│     Op 2 — CREATE TRIGGER fn_facturas_inmutable on prod.facturas            │
│             (BEFORE UPDATE OR DELETE → RAISE EXCEPTION)                      │
│     Op 3 — CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS                   │
│             one_pago_per_factura_init                                        │
│             ON prod.factura_pagos (uuid_factura)                              │
│             WHERE tipo_movimiento='pago'                                    │
│                                                                              │
│ ELSE:                                                                        │
│   No migration authored; pre-apply verification report only.                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Capabilities

**New**:

- **`facturacion-billing`** — covers the 2 POST endpoints
  (`/facturacion/factura` + `/facturacion/factura-pagos`), the 6 validations
  V1..V6, the KD-FACT-01 single-commit invariant, the KD-FACT-02 `FOR SHARE`
  per-row lock, the módulo 11 NIT helper, the DEC-FACT-06 server-derived
  `uuid_cliente`, and the DEC-FACT-04 no-retención / DEC-FACT-07 no-forma_pago
  catálogo decisions. Spec in
  `openspec/changes/hu-f1-9-facturacion/specs/facturacion-billing/spec.md`,
  archived in `openspec/specs/facturacion-billing/spec.md` as **REQ-OPS-053..063**
  (11 requirements).
- **`repo/factura.py`** — helper module for billing lifecycle (V1 lookup,
  V2 cliente, V3 IVA, V4 detalle, V6 recompute, KD-FACT-02 lock, Step 9 INSERT,
  Step 10 INSERTs). Encapsulates SQL + bi-temporal predicates + lock boundaries.
- **`repo/factura_detalle.py`** — bulk insert helper for `prod.factura_detalle`
  (`session.add_all([...])`, no per-row flush).
- **`repo/nit_modulo11.py`** — DIAN Resolución 000175 de 2021 algoritmo;
  pure Python helper, no DB. Exposes `validar_nit_modulo11(nit, dv)` and
  `dv_esperado(nit)` for the 422 error response.

**Modified**:

- **`operations`** — the canonical capability adds REQ-OPS-053..063 (11 requirements):
  POST /facturacion/factura contract, V1..V6 validations, KD-FACT-01 single-
  commit invariant + AST walk, KD-FACT-02 `FOR SHARE` per-row lock, NIT módulo
  11 algorithm per DIAN Resolución 000175 de 2021, DEC-FACT-06 server-derived
  `uuid_cliente`, conditional MIGRATION 0027 if `fn_facturas_inmutable` and/or
  `one_pago_per_factura_init` missing. Spec deltada in
  `openspec/changes/hu-f1-9-facturacion/specs/operations/spec.md`.
- **`api/v1/__init__.py`** — `r.include_router(facturacion.router)` (NEW line,
  same pattern as `operacion.router` line).
- **`schemas/facturacion.py`** — add `FacturaCreate`, `FacturaRead`,
  `FacturaItemCreate`, `FacturaItemRead`, `FacturaPagoAdicionalCreate`,
  `FacturaPagoRead`, 4 typed error classes
  (`SalidaNoFacturableError`, `ClienteNoEncontradoFacturaError`,
  `NitInvalidoError`, `TotalNoCoherenteError`).
- **`schemas/clientes.py`** — add Pydantic v2 `@field_validator` on
  `ClientesCreate.numero_identificacion` calling `validar_nit_modulo11` when
  `tipo_identificador='NIT'`.
- **MIGRATION (CONDITIONAL)**: `migrations/versions/0027_facturas_inmutable_trigger.py`
  (~80 LOC) introduced ONLY if pre-apply verification finds both
  `fn_facturas_inmutable` trigger and `one_pago_per_factura_init` partial unique
  index missing.

### 2.5 Data Model

`modelo_datos_er.mmd` — **sin cambios de esquema si la migration 0027 condicional
NO aplica**. Si aplica, MIGRATION 0027 introduces:

1. `CREATE TRIGGER fn_facturas_inmutable BEFORE UPDATE OR DELETE ON prod.facturas
   FOR EACH ROW EXECUTE FUNCTION prod.fn_facturas_inmutable()` (mirroring
   `fn_factura_detalle_inmutable`, `fn_factura_impuestos_inmutable`,
   `fn_factura_pagos_inmutable` at lines 2024-2088 in migration 0001).
2. `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_pago_per_factura_init ON
   prod.factura_pagos (uuid_factura) WHERE tipo_movimiento='pago'`.

**Columnas leídas/escritas** (todas existentes, sin DDL cuando la migration es
NO necesaria):

| Tabla | Columna | Operación | Línea ER / migration |
|---|---|---|---|
| `prod.salidas` | `uuid`, `uuid_sucursal`, `uuid_ingreso` | V1 SELECT (read-only) | 761-777 |
| `prod.ingreso` | `uuid`, `placa`, `uuid_tipo_vehiculo` | V1 derivado | 577-596 |
| `prod.clientes` | `tipo_identificador`, `numero_identificacion`, `estado`, `vigente_hasta`, `nombre`, `apellido`, `email`, `telefono` | V2 SELECT/INSERT condicional | 449-472 |
| `prod.impuestos` | `nombre='IVA'`, `porcentaje`, `vigente_desde`, `vigente_hasta`, `estado` | V3 SELECT | 187-207 |
| `prod.tarifas_sucursal` | `uuid`, `valor`, `valor_plena`, `vigente_desde`, `vigente_hasta`, `estado` | KD-FACT-02 SELECT FOR SHARE per-row | 406-426 |
| `prod.facturas` | `uuid_sucursal`, `uuid_ingreso`, `uuid_salida`, `subtotal`, `descuento`, `total` | Step 9 INSERT `[L-E]` | 607-654 |
| `prod.factura_detalle` | `uuid_factura`, `tipo`, `concepto`, `cantidad`, `valor_unitario`, `subtotal`, `uuid_tarifa_sucursal` | Step 10 bulk INSERT `[A]` | 780-794 |
| `prod.factura_impuestos` | `uuid_factura`, `uuid_impuesto`, `base_calculo`, `porcentaje_aplicado`, `valor` | Step 10 INSERT (IVA snapshot) `[A]` | (migration 0001 sin ER explícito) |
| `prod.factura_pagos` | `uuid_factura`, `medio_pago`, `valor`, `referencia`, `uuid_sesion`, `tipo_movimiento='pago'` | Step 10 INSERT (1 pago) `[A]` | 843-861 |

**NO se persiste**: `uuid_cliente` en `prod.facturas` (DEC-FACT-06 — server-derived
in `FacturaRead` response). NO se persiste: `tipo_movimiento`, `dv`,
`validacion_nit` en `prod.factura_detalle` (metadata efímera).

**Defense in depth ya en DB** (migration 0001):

- `prod.factura_detalle`, `factura_impuestos`, `factura_otros_cobros`,
  `factura_pagos`: tienen `fn_*_inmutable` triggers (líneas 2024-2088) que
  rechazan UPDATE/DELETE.
- `prod.facturas` is `[L-E]` — **TO VERIFY pre-apply** si tiene REVOKE explícito
  o `fn_facturas_inmutable` trigger (R2 mitigation).

### 2.6 API Surface

| Path | Method | Cambio | Issuer / rol |
|---|---|---|---|
| `/api/v1/facturacion/factura` | POST | NEW endpoint; URL no previously in router; response shape `FacturaRead` with `uuid_cliente` derived | `admin-`, `cajero-` |
| `/api/v1/facturacion/factura-pagos` | POST | NEW endpoint; URL no previously in router; response shape `FacturaPagoRead` | `admin-`, `cajero-` |
| `/api/v1/facturacion/facturas/{uuid}` | GET | PROPOSED adjacent read (lower priority; out of F1.9 scope) | `admin-`, `cajero-` |
| `/api/v1/facturacion/facturas?uuid_cliente=...&fecha_desde=...&fecha_hasta=...` | GET | PROPOSED adjacent paginated list (lower priority; out of F1.9 scope) | `admin-`, `cajero-` |

**Request signature**:

```python
async def create_factura(
    response: Response,
    payload: FacturaCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaRead:
```

**Body `FacturaCreate`**:

```python
class FacturaCreate(_Base):
    """HU-F1.9: POST /facturacion/factura payload."""
    uuid_salida: uuid_lib.UUID
    items: list[FacturaItemCreate] = Field(min_length=1, max_length=50)
    subtotal: Decimal
    total: Decimal
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"]
    referencia: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    fe_con_datos: bool = False
    fe_datos_cliente: FacturaItemConDatosPropios | None = None
```

**Response `FacturaRead`** (201):

```python
class FacturaRead(_Base):
    """HU-F1.9: POST /facturacion/factura response."""
    uuid: uuid_lib.UUID
    created_at: datetime
    uuid_sucursal: uuid_lib.UUID
    uuid_ingreso: uuid_lib.UUID | None
    uuid_salida: uuid_lib.UUID | None
    subtotal: Decimal
    descuento: Decimal
    total: Decimal
    uuid_cliente: uuid_lib.UUID | None  # DEC-FACT-06 derivado, NO persistido
    items: list[FacturaItemRead]
    estado: Literal["emitida", "pagada", "anulada"]  # derived from V_FACTURA_ESTADO
```

**Errores tipados**:

| HTTP | Body | Cuándo | KD / DEC |
|---|---|---|---|
| 400 | `{"error":"voucher_requerido","medio_pago":"datafono"}` | `/factura-pagos` con `medio_pago='datafono'` y `referencia` vacía | KD-NIT-07 |
| 400 | `{"error":"monto_insuficiente","valor":...,"total_pendiente":...}` | `/factura-pagos` con `valor < total_pendiente` | R-KD-FACT-08 |
| 403 | `{"error":"tenant_scope_violation"}` | `cajero-` con `salida.uuid_sucursal != ctx.sucursal_uuid` (post-V1) | KD-S2 analog |
| 404 | `{"error":"salida_no_encontrada","uuid_salida":"..."}` | V1: uuid no existe o ya fue facturada | V1 |
| 404 | `{"error":"cliente_no_encontrado","numero_identificacion":"..."}` | V2 cuando `fe_con_datos=true` y cliente no existe | V2 |
| 409 | `{"error":"factura_duplicada","uuid_salida":"..."}` | partial unique index `one_pago_per_factura_init` violated (conditional migration 0027) | DEC-FACT-07 (R2) |
| 422 | `{"error":"detalle_invalido","min_items":1}` | V4: `items=[]` | V4 |
| 422 | `{"error":"nit_invalido","dv_esperado":...,"dv_recibido":...}` | V5: NIT módulo 11 fallido | V5 (DEC-FACT-09) |
| 422 | `{"error":"total_no_coherente","total_recibido":...,"total_calculado":...,"diferencia":...}` | V6: total server vs payload differs by >0.01 COP | V6 |
| 500 | `{"error":"iva_no_configurado"}` | V3: `validar_iva_configurado` returns False (post-0026 deploy: never) | V3 |
| 201 | `FacturaRead` con `uuid_cliente` derivado (DEC-FACT-06) | happy path | — |

**Headers**: `Cache-Control: no-store` (alineado con F1.3/F1.5/F1.6/F1.7/F1.8
precedents).

### 2.7 Approach

The implementation is **decomposed into 6 work units** that mirror the 12-step
handler chain. Each unit has autonomous scope, verification, and rollback.

**Unit 1 — NIT helper + repo skeleton (no schema change)**

Create `repo/nit_modulo11.py` (~50 LOC) with `validar_nit_modulo11(nit, dv)`,
`dv_esperado(nit)`, and `_normalize_nit(nit)`. Create `repo/factura.py` (~250
LOC) with the 9 helpers (`buscar_salida_facturable`, `buscar_o_crear_cliente_por_nit`,
`validar_items`, `lock_tarifas_sucursal_para_items`, `compute_total`,
`crear_factura_evento`, `crear_factura_detalle_bulk`, `crear_factura_impuesto_iva`,
`crear_factura_pago`) plus typed exceptions
(`SalidaNoFacturableError`, `ClienteNoEncontradoFacturaError`,
`NitInvalidoError`, `TotalNoCoherenteError`, `VoucherRequeridoError`).
Create `repo/factura_detalle.py` (~80 LOC) with the bulk insert helper.

Verification: `repo/factura.py` is importable; `validar_nit_modulo11("800123456",
"7")` returns True (DIAN reference case pre-spec); `validar_nit_modulo11("800123456",
"5")` returns False.

Rollback: delete the 3 files.

**Unit 2 — Schemas + typed errors + Pydantic validator**

Add to `schemas/facturacion.py` (~80 LOC): `FacturaCreate`, `FacturaRead`,
`FacturaItemCreate`, `FacturaItemRead`, `FacturaPagoAdicionalCreate`,
`FacturaPagoRead`, 4 typed error classes. Add to `schemas/clientes.py`
(~10 LOC): Pydantic v2 `@field_validator('numero_identificacion')` calling
`validar_nit_modulo11` when `tipo_identificador='NIT'`. `extra='forbid'`
(inherited from `_Base`) rejects extra fields.

Verification: Pydantic rejects `payload.tipo_identificador='NIT'` with mismatched
DV → 422; `FacturaRead` validates against sample data with `uuid_cliente=None`
(consumidor final).

Rollback: revert the schema additions.

**Unit 3 — CONDITIONAL MIGRATION 0027**

Pre-apply verification (RUN BEFORE authoring the migration):

```bash
grep "fn_facturas_inmutable" backend/packages/parkos_core/migrations/
grep "one_pago_per_factura_init" backend/packages/parkos_core/migrations/
```

**IF both greps return 0 matches**, create
`migrations/versions/0027_facturas_inmutable_trigger.py` (~80 LOC) with
`down_revision = "0026_seed_impuestos_iva_and_one_exit_per_ingreso"`. The
migration has 3 operations in order:

**Op 1 — Pre-flight `DO $$` block** (KD-7 pattern from F1.6 migration 0024 +
F1.7 migration 0026):

```sql
DO $$
DECLARE
    _n_facturas bigint;
    _n_factura_pagos bigint;
BEGIN
    SELECT count(*) INTO _n_facturas FROM pg_catalog.pg_class
        WHERE relname='facturas' AND relnamespace='prod'::regnamespace;
    IF _n_facturas IS NULL OR _n_facturas = 0 THEN
        RAISE EXCEPTION '0027_preflight_abort: tabla prod.facturas no existe. Aplique migrations 0001-0026 antes.';
    END IF;

    SELECT count(*) INTO _n_factura_pagos FROM pg_catalog.pg_class
        WHERE relname='factura_pagos' AND relnamespace='prod'::regnamespace;
    IF _n_factura_pagos IS NULL OR _n_factura_pagos = 0 THEN
        RAISE EXCEPTION '0027_preflight_abort: tabla prod.factura_pagos no existe.';
    END IF;
END $$;
```

**Op 2 — `CREATE TRIGGER fn_facturas_inmutable`** (mirrors `fn_factura_detalle_inmutable`,
`fn_factura_impuestos_inmutable`, `fn_factura_pagos_inmutable` at lines
2024-2088 in migration 0001):

```sql
CREATE OR REPLACE FUNCTION prod.fn_facturas_inmutable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'fn_facturas_inmutable: UPDATE/DELETE forbidden on prod.facturas (DEC-FACT-01)';
END;
$$;

CREATE TRIGGER trg_facturas_inmutable
    BEFORE UPDATE OR DELETE ON prod.facturas
    FOR EACH ROW EXECUTE FUNCTION prod.fn_facturas_inmutable();
```

**Op 3 — Partial unique index `one_pago_per_factura_init`** (closes TOCTOU
race on concurrent cashier attempts to invoice the same `uuid_salida`):

```sql
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_pago_per_factura_init
    ON prod.factura_pagos (uuid_factura)
    WHERE tipo_movimiento = 'pago';
```

`CONCURRENTLY` for no lock on reads/writes during creation in production. `IF
NOT EXISTS` for idempotency. Same pattern as F1.3 `unique_active_sesion_per_user`
(migration 0023) and F1.7 `one_exit_per_ingreso` (MIGRATION 0026 Op 4). The
INSERT conflict in the handler produces `UniqueViolationError` (psycopg2/asyncpg
code 23505) which `repo/factura.py` maps to `FacturaDuplicadaError` → 409
`factura_duplicada`.

**Downgrade** (reverse order, superuser context for DROP TRIGGER):

```sql
DROP TRIGGER IF EXISTS prod.trg_facturas_inmutable ON prod.facturas;
DROP FUNCTION IF EXISTS prod.fn_facturas_inmutable();
DROP INDEX IF EXISTS prod.one_pago_per_factura_init;
```

**ELSE** (both greps return ≥1 match): NO migration authored. Pre-apply
verification report only.

Verification: `alembic upgrade head` succeeds (if applicable); pre-flight aborts
on simulated missing tables; `CREATE UNIQUE INDEX CONCURRENTLY` is idempotent
(run 2x, second is no-op); downgrade removes all 3 ops.

Rollback: `alembic downgrade -1`.

**Unit 4 — Handler `create_factura` + `create_factura_pagos`**

Add `api/v1/facturacion.py` (~150 LOC: 2 handlers + dependencies). The
`create_factura` handler enforces the strict 12-step order per D-HU-F1.9-12
(see §2.3 Architecture). The `create_factura_pagos` handler (~50 LOC) is a
5-step chain: V1 factura existe + estado emitido; V2 tenant scope; V3
`voucher_requerido` cuando `medio_pago='datafono'` y `referencia` vacía; V4
`monto_insuficiente` si `valor < total_pendiente`; Step: INSERT
`prod.factura_pagos` + single commit. Single `await session.commit()` for
atomicity (KD-FACT-01). Mount the router via `api/v1/__init__.py`:
`r.include_router(facturacion.router)` (NEW line, same pattern as the existing
`operacion.router` line).

Verification: AST walk `tests/static/test_factura_handler_step_order.py` enforces
literal order; the handler compiles without syntax errors; happy path returns
201 with `FacturaRead` carrying `uuid_cliente` derived server-side (DEC-FACT-06).

Rollback: revert the handler addition + remove the include_router line.

**Unit 5 — Tests (~14 tests across 6 files)**

**`tests/unit/test_facturacion_factura.py`** (~400 LOC, 6 tests):

- T1: `test_factura_atomica_rotacion_exitosa_returns_201` — happy path ROTACION.
- T2: `test_factura_consumidor_final_sin_datos_cliente` — `fe_con_datos=false` →
  201 sin cliente.
- T3: `test_factura_con_datos_cliente_nit_valido` — `NIT 800.123.456-7 + DV=7` →
  201.
- T4: `test_factura_con_datos_cliente_nit_invalido_returns_422` — DV mismatched
  → 422 `nit_invalido` con `dv_esperado` y `dv_recibido`.
- T5: `test_factura_detalle_items_vacio_returns_422` — `items=[]` → 422
  `detalle_invalido`.
- T6: `test_factura_total_no_coherente_returns_422` — total differs by >0.01
  COP → 422 `total_no_coherente`.

**`tests/unit/test_validar_nit_modulo11.py`** (~150 LOC, 4 tests):

- T1: `test_nit_referencia_800_123_456_7_valido` — DIAN reference case.
- T2: `test_nit_800_123_456_5_invalido_dv_mismatch` — DV mismatched.
- T3: `test_nit_con_ceros_a_la_izquierda_normaliza` — `000123` → `123.
- T4: `test_nit_con_guion_y_puntos_normaliza` — `800.123.456-7` → `800123456`.

**`tests/unit/test_facturacion_factura_pagos.py`** (~150 LOC, 2 tests):

- T1: `test_factura_pago_datafono_sin_referencia_returns_400` — `voucher_requerido`.
- T2: `test_factura_pago_datafono_con_referencia_returns_201` — happy path.

**`tests/integration/test_factura_atomicidad_db.py`** (~250 LOC, 2 tests,
`PARKOS_DOCKER_TEST=1`):

- T1: `test_factura_atomica_rollback_si_detalle_falla` — simulate FK violation
  on `factura_detalle` INSERT; verify `facturas` row is also rolled back
  (no orphan).
- T2: `test_factura_lock_for_share_sobre_tarifas` — concurrent TX attempting
  `UPDATE tarifas_sucursal` while `create_factura` holds the lock; second TX
  blocks.

**AST walks** (2 tests):

- `tests/static/test_factura_handler_single_commit.py` (~80 LOC) — `ast.walk()`
  over `api/v1/facturacion.py::create_factura` enforcing `len(commits) == 1`.
- `tests/static/test_factura_handler_step_order.py` (~80 LOC) — `ast.walk()`
  enforcing literal 12-step order of helper invocations.

Verification: 14 tests green; `ruff check`, `ruff format --check`,
`mypy --strict` green on 6 new + 2 modified backend files + 6 test files.

Rollback: remove the test files.

**Unit 6 — Spec deltas + Engram persistence**

Persist spec deltas to
`openspec/changes/hu-f1-9-facturacion/specs/operations/spec.md` with
REQ-OPS-053..063 (11 requirements). Persist Engram observation
`sdd/hu-f1-9-facturacion/propose` (architecture type).

Verification: spec.md has 11 new REQs in canonical format; Engram observation
recorded with `capture_prompt=false`.

Rollback: revert the spec changes; Engram observation stays (topic_key upserts).

---

## 3. Impact

### 3.1 Affected Modules

| Area | Impact | Description |
|---|---|---|
| `prod.facturas` | INSERT (Step 9) | New rows created by `create_factura`. NOT modified post-insert (DEC-FACT-01 + conditional `fn_facturas_inmutable` trigger). |
| `prod.factura_detalle` | INSERT (Step 10) | Bulk insert via `repo/factura_detalle.py::crear_factura_detalle_bulk`. Append-only (`fn_factura_detalle_inmutable` trigger migration 0001). |
| `prod.factura_impuestos` | INSERT (Step 10) | IVA snapshot: `uuid_impuesto`, `base_calculo`, `porcentaje_aplicado`, `valor`. Append-only (`fn_factura_impuestos_inmutable`). |
| `prod.factura_pagos` | INSERT (Step 10 + /factura-pagos) | Single pago per `create_factura`; additional pagos via `create_factura_pagos`. Append-only (`fn_factura_pagos_inmutable`). |
| `prod.clientes` | SELECT/INSERT conditional (V2) | SELECT when `fe_con_datos=true` to find existing cliente; INSERT only via `repo/versioned.py::close_and_insert` if explicitly requested (F1.9 does NOT auto-create; F1.9 returns 404 `cliente_no_encontrado` to caller). |
| `prod.impuestos` | SELECT (V3) | `validar_iva_configurado` reusado verbatim de F1.7. NO modifications. |
| `prod.tarifas_sucursal` | SELECT FOR SHARE (KD-FACT-02) | Per-row lock on every `uuid_tarifa_sucursal` referenced in `factura_detalle`. NO modifications. |
| `prod.salidas` | SELECT (V1) | Read PK + `uuid_sucursal` + `uuid_ingreso`. NO modifications. |
| `prod.ingreso` | SELECT (V1 derived) | Read `placa` + `uuid_tipo_vehiculo` for `uuid_cliente` derivation (DEC-FACT-06). NO modifications. |
| `prod.factura_electronica` | NO TOCADO | F1.10 owns numbering + estado DIAN. F1.9 leaves the table untouched. |

### 3.2 Affected Endpoints

| Path | Method | Status |
|---|---|---|
| `/api/v1/facturacion/factura` | POST | NEW (F1.9 closes) |
| `/api/v1/facturacion/factura-pagos` | POST | NEW (F1.9 closes) |
| `/api/v1/facturacion/facturas/{uuid}` | GET | PROPOSED adjacent read (out of F1.9 scope; lower priority) |
| `/api/v1/facturacion/facturas?uuid_cliente=...&fecha_desde=...&fecha_hasta=...` | GET | PROPOSED adjacent list (out of F1.9 scope; lower priority) |
| `/api/v1/facturacion/factura-electronica` | POST | F1.10 (separate HU) |
| `/api/v1/operacion/salidas` | POST | UNCHANGED (F1.7 already closed) |
| `/api/v1/operacion/cotizar` | GET | UNCHANGED (F1.8 already closed) |
| `/api/v1/operacion/ingresos` | POST | UNCHANGED (F1.6 already closed) |

### 3.3 Affected Workflows

- **CU-04 (Facturación)**: F1.9 closes the billing half (internal factura +
  pagos). F1.10 closes FE numbering + DIAN state. CU-04 is functionally
  complete at the close of F1.10.
- **HU-F7.2 (Salida rotación)**: F1.7 already produces the `cotizacion_snapshot`
  in the salida response; F1.9 consumes it indirectly via V6 recompute (the
  client sends `subtotal` + `total` matching the cotizacion_snapshot).
- **HU-F8.1 (Facturación consumidor final / FE)**: HU-F8.1 consumes
  `prod.facturas` + `prod.factura_detalle` + `prod.factura_pagos` from F1.9.
  Unblocked after F1.9 archive.

### 3.4 New Dependencies

- **NO new Python dependencies**. Pure stdlib `re` (for NIT normalization) +
  existing Pydantic v2 + existing SQLAlchemy async.
- **NO new migration preferentemente**. MIGRATION 0027 is CONDITIONAL based on
  pre-apply grep verification.
- **NO new third-party services**. All logic is server-side.

### 3.5 APIs Called

- `prod.tarifas_sucursal` — V5 SELECT FOR SHARE per-row (KD-FACT-02).
- `prod.salidas` — V1 SELECT by PK.
- `prod.clientes` — V2 SELECT by UK `(tipo_identificador, numero_identificacion)`.
- `prod.impuestos` — V3 read (reused `validar_iva_configurado` from F1.7).
- `assign_consecutivo` (Python helper, branch-local) — DEFERRED to F1.10.
  F1.9 does NOT call `assign_consecutivo`; the internal factura has only
  `uuid` (no `prefijo` + `consecutivo` — DEC-FACT-05).

---

## 4. Out of Scope (deferred)

1. **Consecutivo FE + estado DIAN**: deferred to HU-F1.10
   (`POST /facturacion/factura-electronica`). DEC-FACT-05.
2. **Retención RETCONT 11% sobre servicios**: deferred to Fase 4 (contabilidad).
   `prod.retencion` table does NOT exist in migration 0001. DEC-FACT-04.
3. **`prod.forma_pago` catálogo CRUD**: deferred to Fase 4. Table does NOT exist.
   DEC-FACT-07 Opción A (Pydantic `Literal[...]` enforced) chosen for MVP.
4. **`prod.facturas.uuid_cliente` FK explícita**: deferred (table column does
   NOT exist). DEC-FACT-06 (server-derived `uuid_cliente` in
   `FacturaRead` response).
5. **Anulación de factura**: deferred to HU-F1.13 (workflow Arqueo + cierre_dia).
   DEC-FACT-01 (`prod.facturas` is append-only `[L-E]`; corrections via
   `prod.anulaciones(tipo_anulable='factura')` workflow — Fase 7+).
6. **`GET /api/v1/facturacion/facturas/{uuid}`**: adjacent read; lower priority.
   Out of F1.9 scope.
7. **`GET /api/v1/facturacion/facturas?uuid_cliente=...`**: paginated list;
   lower priority. Out of F1.9 scope.
8. **Auto-create cliente en V2**: V2 returns 404 `cliente_no_encontrado`; the
   caller decides whether to POST `/clientes` first. F1.9 does NOT auto-create.
9. **Asignación de `prefijo` + `consecutivo` a `prod.facturas`**: DEC-FACT-05.
   F1.9 produces internal factura with `uuid` only; F1.10 calls
   `assign_consecutivo` to assign FE numbering on top.
10. **Cleanup of client-side derivation logic in `web_sucursal`**: Fase 2
    frontend. Post-archive cleanup.
11. **`/api/v1/facturacion/factura` Idempotency-Key handling**: DEC-IDEM-01
    reuse from F1.6 (header-based dedup). No body-level `correlacion_id`.
12. **`/api/v1/facturacion/factura-electronica/{uuid}/reintentar`** endpoint:
    F1.10 (reintento DIAN).

---

## 5. Requirements (REQ-OPS-053..063)

The following REQ-OPS-NNN placeholders will be formalized by `sdd-spec` in
`openspec/changes/hu-f1-9-facturacion/specs/operations/spec.md`:

- **REQ-OPS-053 (NEW)** — `POST /api/v1/facturacion/factura` contract:
  `FacturaCreate` input + `FacturaRead` output; KD-3 tenant scope
  (`requires_issuer("admin-", "cajero-")`); `Cache-Control: no-store`;
  `Idempotency-Key` HTTP header (DEC-IDEM-01 reuse from F1.6).

- **REQ-OPS-054 (NEW)** — V1: `salida existe y es facturable`. SELECT directo a
  `prod.salidas` por PK + `uuid_ingreso`. Si no existe OR ya fue facturada
  (V1 EXISTS check sobre `prod.facturas` con `uuid_salida` matching) → 404
  `salida_no_encontrada`. Defense-in-depth via partial unique index
  `one_pago_per_factura_init` (MIGRATION 0027 conditional Op 3) — `UniqueViolationError`
  → 409 `factura_duplicada`.

- **REQ-OPS-055 (NEW)** — V2: `cliente existe cuando fe_con_datos=true`.
  SELECT sobre `prod.clientes WHERE tipo_identificador=:t AND
  numero_identificacion=:n AND vigente_hasta IS NULL AND estado='activo'`.
  Si no encuentra → 404 `cliente_no_encontrado`. Si `fe_con_datos=false`: no
  requiere cliente (DEC-FACT-08 consumidor final).

- **REQ-OPS-056 (NEW)** — V3: `IVA configurado`. Reuso verbatim de
  `repo/impuestos.py::validar_iva_configurado(session)` (F1.7). 500
  `iva_no_configurado` (post-0026 deploy: never).

- **REQ-OPS-057 (NEW)** — V4: `detalle items coherentes`. Lista
  `items: list[FacturaItemCreate]` con `cantidad > 0`, `valor_unitario >= 0`,
  `concepto: Literal["servicio", "producto"]`, `uuid_tarifa_sucursal: UUID | None`.
  Si `items=[]` → 422 `detalle_invalido`. (Schema enforces `min_length=1,
  max_length=50` via Pydantic `Field`.)

- **REQ-OPS-058 (NEW)** — V5: `NIT módulo 11 DIAN Resolución 000175 de 2021`.
  Helper `repo/nit_modulo11.py::validar_nit_modulo11(nit, dv) -> bool` aplica
  weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]`
  right-to-left sobre dígitos del NIT (sin DV); DV = `sum_ponderada % 11`
  (Variant A — DIAN canónico, NO Variant B). Helper normalizes NIT (strip
  non-digits, strip leading zeros, minimum 5 digits). Aplicado vía Pydantic
  v2 `@field_validator('numero_identificacion')` en `ClientesCreate`
  (siempre cuando `tipo_identificador='NIT'`) y en
  `FacturaItemConDatosPropios` (solo cuando `fe_con_datos=true`). Si DV no
  match → 422 `nit_invalido` con `dv_esperado: int` y `dv_recibido: str`.

- **REQ-OPS-059 (NEW)** — V6: `total coherente ±0.01 COP`. Server computa
  `total_server = subtotal_items + iva - retencion` donde `iva = subtotal *
  0.19` y `retencion = Decimal("0")` (DEC-FACT-04 MVP). Compara con
  `payload.total`. Si `abs(total_server - payload.total) > Decimal("0.01")`
  → 422 `total_no_coherente` con `total_recibido`, `total_calculado`,
  `diferencia`.

- **REQ-OPS-060 (NEW, KD-FACT-01)** — Single `await session.commit()`
  materializa las 4 tablas (`prod.facturas` + `prod.factura_detalle` (N rows) +
  `prod.factura_impuestos` (1 row) + `prod.factura_pagos` (1 row))
  atómicamente. AST walk `tests/static/test_factura_handler_single_commit.py`
  enforces literal `len(commits) == 1` en el handler body. Sin
  sub-transactions; sin SAVEPOINTs.

- **REQ-OPS-061 (NEW, KD-FACT-02)** — `SELECT ... FOR SHARE` per-row sobre
  `prod.tarifas_sucursal` para cada `uuid_tarifa_sucursal` referenced in
  `factura_detalle`. Lock mantenido hasta `await session.commit()`. NO lock
  sobre `prod.salidas` (V1 read by PK) ni `prod.clientes` (V2 read by UK).
  Lock per-row mantiene el lock solo sobre las filas que están siendo
  facturadas (no global).

- **REQ-OPS-062 (NEW)** — `POST /api/v1/facturacion/factura-pagos` — voucher
  requerido cuando `medio_pago='datafono'` y `referencia` vacía. 400
  `voucher_requerido` con `medio_pago: "datafono"`. Handler aplica 5-step
  chain: V1 factura existe + estado emitido; V2 tenant scope; V3
  `voucher_requerido`; V4 `monto_insuficiente` si `valor < total_pendiente`;
  Step: INSERT `prod.factura_pagos` + single commit.

- **REQ-OPS-063 (NEW, DEC-FACT-06)** — `uuid_cliente` en `FacturaRead` es
  derivado server-side vía lookup `salidas.uuid_ingreso` → `ingreso.placa` →
  `vehiculos.placa` → opcionalmente `clientes` por `numero_identificacion`
  del payload (V2 path). NO persistido en `prod.facturas` (4FN / no FK column
  in MVP). Future HU may add `prod.facturas.uuid_cliente` FK column and
  backfill; F1.9 does NOT create the FK.

---

## 6. Risks & Mitigations

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | Algoritmo NIT módulo 11 incorrecto (Variante A vs B). Si se elige Variant B (`DV = 11 - (sum % 11)`) en lugar de Variant A (`DV = sum % 11`), el DIAN rechaza todas las facturas en auditoría. | **CRITICAL** | DEC-FACT-09 fija Variant A canónica per DIAN Resolución 000175 de 2021. Pre-apply verify con test case `800.123.456-7 + DV=7` que discrimina las variantes (Variant A retorna `True`, Variant B retorna `False`). RIESGO-SUC-04 en `plan.md:2679` ya identifica este riesgo. `test_nit_referencia_800_123_456_7_valido` (T1 de `tests/unit/test_validar_nit_modulo11.py`) verifica el caso canónico. |
| **R2** | Falta `fn_facturas_inmutable` trigger sobre `prod.facturas`. La tabla `[L-E]` no tiene REVOKE explícito ni trigger inmutable en migration 0001 (líneas 607-654). Un dev futuro podría hacer UPDATE/DELETE accidentalmente. | **HIGH** | DEC-FACT-01 fija append-only. Pre-apply verify: `grep "fn_facturas_inmutable" migrations/`. Si retorna 0 matches, MIGRATION 0027 Op 2 añade `CREATE TRIGGER fn_facturas_inmutable`. Test T1 `test_factura_atomica_rotacion_exitosa_returns_201` verifica que UPDATE post-insert revienta. |
| **R3** | Partial unique index `one_pago_per_factura_init` NO existe en migration 0001. Sin el index, dos cajeros concurrentes podrían crear dos `prod.factura_pagos` rows para la misma factura (TOCTOU race). | **HIGH** | Pre-apply verify: `grep "one_pago_per_factura_init" migrations/`. Si retorna 0 matches, MIGRATION 0027 Op 3 crea `CREATE UNIQUE INDEX CONCURRENTLY`. Test T1 verifica atomicidad; T2 verifica FOR SHARE lock. |
| **R4** | `prod.retencion` y `prod.forma_pago` NO existen en DB. El brief menciona `prod.retencion` con campo `beneficiario` y descuento RETCONT 11% sobre servicios (DIAN 2026). | **MEDIUM** | DEC-FACT-04 + DEC-FACT-07: MVP sin estas tablas. V6 `compute_total` accepts `retencion=Decimal("0")`. Forma_pago enforced via Pydantic `Literal[...]`. Deferred a Fase 4 (contabilidad). Documented as "to extend" en design.md, not implemented. |
| **R5** | `prod.facturas.uuid_cliente` NO existe como columna en migration 0001 (líneas 607-654). Si el cliente espera `uuid_cliente` como FK persistente, hay confusión. | **MEDIUM** | DEC-FACT-06: `uuid_cliente` derivado server-side en `FacturaRead` response. NO FK explícita en MVP. Documentado en docstring del schema. Future HU may add FK + backfill. |
| **R6** | Forma de pago no validada contra catálogo en DB. Un cliente podría enviar `medio_pago='efectivoUSD'` (string libre) y se aceptaría. | **LOW** | DEC-FACT-07 Opción A: Pydantic `Literal["efectivo","tarjeta","transferencia","datafono","mixto"]` enforced at schema level. Cualquier valor fuera del literal → 422 Pydantic validation error. |
| **R7** | Lock continuidad entre `/factura` y `/factura-pagos` son 2 TX separadas. Si el cajero hace POST /factura (TX 1) y luego POST /factura-pagos (TX 2) con un delay, el lock FOR SHARE de TX 1 ya se liberó. | **LOW** | Cada handler abre su propia TX. Idempotency-Key header (DEC-IDEM-01 reuse from F1.6) maneja retries. Partial unique index `one_pago_per_factura_init` cierra concurrent cashier race. |

---

## 7. Decisions (DEC-FACT-01..09)

| Code | Decision | Status | Rationale |
|---|---|---|---|
| **DEC-FACT-01 (KD-FACT-01)** | Single `await session.commit()` materializes 4 tables atomically. AST walk `test_factura_handler_single_commit.py` enforces `len(commits) == 1`. | NEW (F1.9) | Analogue of KD-S7 (F1.7 single-commit for salida + alerta). Defense-in-depth at handler layer; DB triggers `fn_*_inmutable` (migration 0001 lines 2024-2088) provide complementary protection at DB layer for `factura_detalle`, `factura_impuestos`, `factura_pagos` (NOT `facturas` — R2 mitigation via conditional `fn_facturas_inmutable` MIGRATION 0027). |
| **DEC-FACT-02 (KD-FACT-02)** | `SELECT … FOR SHARE` per-row sobre `prod.tarifas_sucursal` para cada `uuid_tarifa_sucursal` en `factura_detalle`. Lock mantenido hasta `await session.commit()`. | NEW (F1.9) | Analogue of KD-1 (F1.8 `FOR SHARE` inside `calcular_cotizacion` PL/pgSQL). Per-row scope evita global serialization (F1.8 lock conflicts with concurrent cotizaciones; F1.9 lock isolated per row). Alternative "lock-free" rejected — opens window of inconsistency between snapshot read and INSERT. |
| **DEC-FACT-03** | IVA read from `prod.impuestos` ONLY; no hardcoded constants in Python. | CONFIRMED (F1.7 reuse) | DEC-IMP-01 from F1.7 applies equally. `validar_iva_configurado` reusado verbatim. `porcentaje` field is the regulatory constant, NOT Python literal. |
| **DEC-FACT-04** | MVP NO aplica retención (RETCONT 11% sobre servicios). `prod.retencion` does NOT exist in DB. Deferred to Fase 4. | NEW (F1.9) | Gap pre-existente. `prod.retencion` table not in migration 0001. Sin tabla, no se puede snapshotear porcentaje RETCONT ni `concepto`. V6 `compute_total` accepts `retencion=Decimal("0")`. Documented in design.md as "to extend". |
| **DEC-FACT-05** | `prod.facturas` does NOT receive `prefijo` + `consecutivo` (F1.10 owns). F1.9 creates internal factura with `uuid` only. | NEW (F1.9) | Analogue of DEC-SUC-21-NEW from F1.7 (server-derived `tipo_salida`, never persisted). `assign_consecutivo` Python helper (existing, branch-local with `SELECT … FOR UPDATE` on `resolucion_facturacion`) reused as-is in F1.10, NOT modified here. |
| **DEC-FACT-06** | `uuid_cliente` is **NOT** a column in `prod.facturas`. `FacturaRead.uuid_cliente` is server-derived via lookup chain. NO FK explícita en MVP. | NEW (F1.9) | 4FN compliance — `prod.facturas` (migration 0001 lines 607-654) only stores `uuid_sucursal`, `subtotal`, `descuento`, `total`, `uuid_ingreso`, `uuid_salida`. Lookup chain: `facturas.uuid_salida` → `salidas.uuid_ingreso` → `ingreso.placa` → `vehiculos.placa` → opcionalmente `clientes` por `numero_identificacion` del payload (V2 path). |
| **DEC-FACT-07 Opción A** | NO crear `prod.forma_pago` catálogo. `prod.factura_pagos.medio_pago` is `String()` libre; Pydantic `Literal[...]` enforced. RECOMMENDED for MVP. | NEW (F1.9) | Trade-off: -120 LOC vs. Opción B (create `prod.forma_pago [V]` migration 0027). Opción A is sufficient for F1.9. Future HU may create the table if reporting/analytics need normalized catalog. Decision recorded in design.md. |
| **DEC-FACT-08** | If `fe_con_datos=false`, the handler does NOT create nor require a cliente. Factura emitted as "consumidor final" with NIT genérico `222222222222` (DIAN convention). | NEW (F1.9) | Mirrors existing `consumidor_final` UX in operator's terminal. No new cliente row; no FK lookup. V2 returns 404 only when `fe_con_datos=true`. |
| **DEC-FACT-09 (KD-NIT-01)** | NIT módulo 11 algorithm is canonical per DIAN Resolución 000175 de 2021. Variant A: `DV = sum_ponderada % 11`. NO alternative algorithms permitted. Helper also normalizes NIT (strip non-digits, strip leading zeros, minimum 5 digits). | NEW (F1.9) | R1 mitigation (CRITICAL). Pre-apply verify against test case `800.123.456-7` which discriminates Variants A vs B. `dv_esperado` helper exposed for the 422 `nit_invalido` body to include `dv_esperado` and `dv_recibido`. |

---

## 8. Defense in Depth

5 layers protect the atomicidad + NIT validation + immutability invariants:

**(a) DB layer — `fn_*_inmutable` triggers + conditional `fn_facturas_inmutable`**

Migration 0001 lines 2024-2088 already has:
- `fn_factura_detalle_inmutable` on `prod.factura_detalle` (rejects UPDATE/DELETE).
- `fn_factura_impuestos_inmutable` on `prod.factura_impuestos`.
- `fn_factura_pagos_inmutable` on `prod.factura_pagos`.

**Conditional MIGRATION 0027 Op 2** adds `fn_facturas_inmutable` on `prod.facturas`
(NOT yet present in migration 0001 — R2 mitigation; pre-apply verify with `grep
"fn_facturas_inmutable"` confirms whether trigger exists; if not, MIGRATION 0027
Op 2 introduces it).

**(b) DB layer — partial unique index `one_pago_per_factura_init` (MIGRATION 0027 conditional Op 3)**

`CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_pago_per_factura_init ON
prod.factura_pagos (uuid_factura) WHERE tipo_movimiento='pago'` closes the
TOCTOU race between concurrent cajeros attempting to invoice the same
`uuid_salida`. `UniqueViolationError` (psycopg2/asyncpg pgcode 23505) maps to
409 `factura_duplicada`.

**(c) Repo layer — typed exceptions**

`repo/factura.py` defines 5 typed exceptions that wrap pgcode `23505` and other
constraint violations:
- `SalidaNoFacturableError(uuid_salida)` — V1 lookup miss / already-factured.
- `ClienteNoEncontradoFacturaError(numero_identificacion)` — V2 lookup miss.
- `NitInvalidoError(dv_esperado, dv_recibido)` — V5 algorithm mismatch.
- `TotalNoCoherenteError(total_recibido, total_calculado, diferencia)` — V6 ±0.01.
- `VoucherRequeridoError(medio_pago)` — KD-NIT-07 datáfono sin `referencia`.

Each exception maps to a typed HTTP error response. The pgcode NEVER appears in
the response body, headers, or info+ logs.

**(d) Handler layer — 12-step chain + single `await session.commit()`**

`api/v1/facturacion.py::create_factura` enforces:
- Strict 12-step order (locked by AST walk
  `tests/static/test_factura_handler_step_order.py`).
- Single `await session.commit()` (KD-FACT-01, locked by AST walk
  `tests/static/test_factura_handler_single_commit.py`).
- Tenant scope check post-V1 (KD-S2 analog from F1.7; 404 before 403 to avoid
  info leak).
- V6 total coherence assert (±0.01 COP) before INSERT.
- KD-FACT-02 `FOR SHARE` lock acquired before bulk INSERT.
- `Cache-Control: no-store` applied to all 2xx/4xx/5xx responses.

**(e) AST walk layer — invariant enforcement**

- `tests/static/test_factura_handler_single_commit.py` (~80 LOC) — `ast.walk()`
  over `create_factura` body; rejects multiple `session.commit()` calls.
  Locks KD-FACT-01 literal.
- `tests/static/test_factura_handler_step_order.py` (~80 LOC) — `ast.walk()`
  enforcing literal 12-step order of helper invocations (V1 → tenant scope →
  V2 → V3 → V4 → KD-FACT-02 → V6 → Step 9 INSERT → Step 10 INSERTs →
  Step 11 commit → Step 12 response). Same pattern as F1.6/F1.7 AST walks.

---

## 9. Open Questions (resolved in propose phase)

The 10 preguntas abiertas de `exploration.md §16` se resuelven en este proposal
vía DEC-FACT-NN:

- **OQ-1 (DEC-FACT-04 no retención)** — RESUELTO (orchestrator-decided): MVP NO
  aplica retención. `prod.retencion` does NOT exist in DB. Deferred to Fase 4.
  Decisión DEC-FACT-04 + V6 `compute_total` accepts `retencion=Decimal("0")`.

- **OQ-2 (DEC-FACT-06 uuid_cliente derivado)** — RESUELTO (orchestrator-decided):
  `uuid_cliente` server-derived in `FacturaRead` response. NO FK explícita en
  MVP. Decisión DEC-FACT-06.

- **OQ-3 (DEC-FACT-07 Opción A Pydantic-only enum)** — RESUELTO
  (orchestrator-decided): favor de Pydantic `Literal[...]` enforced, sin
  catálogo `prod.forma_pago` en MVP. Decisión DEC-FACT-07 Opción A.

- **OQ-4 (Algoritmo NIT módulo 11)** — RESUELTO (orchestrator-decided): Variant A
  canónica per DIAN Resolución 000175 de 2021. Decisión DEC-FACT-09. TO VERIFY
  pre-apply contra DIAN spec con test case `800.123.456-7 + DV=7` que
  discrimina Variants A vs B.

- **OQ-5 (Idempotency-Key header)** — RESUELTO (orchestrator-decided): NO
  requerido en F1.9. Mismo patrón que F1.7 — `Idempotency-Key` HTTP header
  (DEC-IDEM-01 reuse from F1.6). Single TX + 409 pgcode 23505 cubre retries;
  F1.9 acepta mismo patrón. NO `correlacion_id` en body.

- **OQ-6 (DEC-FACT-01 single commit)** — RESUELTO (orchestrator-decided): favor
  de single `await session.commit()` materializing 4 tables atomically. AST walk
  enforces literal `len(commits) == 1`. Decisión DEC-FACT-01.

- **OQ-7 (DEC-FACT-02 FOR SHARE per-row)** — RESUELTO (orchestrator-decided):
  favor de per-row `FOR SHARE` sobre `prod.tarifas_sucursal`. Decisión
  DEC-FACT-02. Alternative "lock-free" rejected (R3 risk class).

- **OQ-8 (V5 NIT validation trigger)** — RESUELTO (orchestrator-decided): NIT
  validación en Pydantic v2 layer (`@field_validator`) sobre
  `ClientesCreate.numero_identificacion` (always cuando
  `tipo_identificador='NIT'`) y sobre `FacturaItemConDatosPropios` (only
  cuando `fe_con_datos=true`). Pre-apply verify del algoritmo.

- **OQ-9 (conditional MIGRATION 0027)** — RESUELTO (orchestrator-decided): favor
  de migration CONDICIONAL basada en pre-apply `grep` de `fn_facturas_inmutable`
  y `one_pago_per_factura_init`. Si ambos grep retornan ≥1 match, no migration.
  Si ≥1 retorna 0 matches, MIGRATION 0027 introduce solo las ops faltantes.

- **OQ-10 (V6 total recompute ±0.01 COP)** — RESUELTO (orchestrator-decided):
  favor de tolerance ±0.01 COP (1 centavo colombiano). Decisión V6. Si la
  diferencia excede 0.01 COP, 422 `total_no_coherente` con `diferencia`
  string.

**Sin preguntas abiertas para propose/design**. Si durante `sdd-spec` surge
evidencia técnica fuerte para revisar alguna KD (ej: medición de EXPLAIN
ANALYZE muestra V1 > 50ms en producción simulada con 100M filas de `prod.salidas`,
o pre-apply grep encuentra AMBOS `fn_facturas_inmutable` y `one_pago_per_factura_init`
ya presentes en migration 0001 — en cuyo caso NO se crea MIGRATION 0027), se
reabre en `design.md` con evidencia.

---

## 10. Acceptance Criteria

10 tests across 6 files:

- **T1 Happy path ROTACION**: `POST /factura` con `uuid_salida` válido →
  `201` + `FacturaRead` con `uuid`, `created_at`, `uuid_sucursal`,
  `uuid_ingreso`, `uuid_salida`, `subtotal`, `descuento`, `total`,
  `uuid_cliente` derivado (DEC-FACT-06), `items: list[FacturaItemRead]`,
  `estado: "emitida"`. Las 4 tablas (`prod.facturas`, `prod.factura_detalle`,
  `prod.factura_impuestos`, `prod.factura_pagos`) pobladas atómicamente.

- **T2 Happy path CONSUMIDOR_FINAL**: `POST /factura` con
  `fe_con_datos=false` → `201` sin cliente. `uuid_cliente` en response es
  `None`. No row inserted en `prod.clientes`. Las 4 tablas pobladas.

- **T3 NIT válido**: `POST /factura` con `fe_con_datos=true` + NIT
  `800.123.456-7 + DV=7` → `201`. Helper `validar_nit_modulo11` retorna
  `True` (Variant A canónica).

- **T4 NIT inválido**: `POST /factura` con `fe_con_datos=true` + NIT
  `800.123.456-5 + DV=5` → `422 nit_invalido` con `dv_esperado=7` y
  `dv_recibido="5"`. No INSERT ocurre (pre-commit validation).

- **T5 Detalle vacío**: `POST /factura` con `items=[]` → `422 detalle_invalido`
  con `min_items=1`. Pydantic `Field(min_length=1)` enforces schema-level.

- **T6 Total incoherente**: `POST /factura` con `total` differs by >0.01 COP
  from server-computed `total_server` → `422 total_no_coherente` con
  `total_recibido`, `total_calculado`, `diferencia`.

- **T7 Voucher ausente**: `POST /factura-pagos` con
  `medio_pago='datafono'` sin `referencia` → `400 voucher_requerido` con
  `medio_pago: "datafono"`.

- **T8 Atomicidad**: simulate FK violation en INSERT `factura_detalle` (e.g.
  `uuid_tarifa_sucursal` referencing non-existent row). Verify that row en
  `prod.facturas` también rolled back (no orphan). 0 rows en `prod.facturas`,
  `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos` post
  rollback.

- **T9 Lock FOR SHARE**: concurrent TX attempting `UPDATE tarifas_sucursal`
  during `create_factura` holds the lock. Verify second TX blocks until
  `await session.commit()` releases the lock. Per-row scope: only the
  referenced `uuid_tarifa_sucursal` row is locked (not all
  `tarifas_sucursal` rows).

- **T10 Single-commit invariant**: AST walk
  `tests/static/test_factura_handler_single_commit.py` enforces exactly 1
  `session.commit()` en `create_factura` body. Test verifies the AST literal.

Defense-in-depth gate: cada una de las 5 capas (§8) tiene al menos un test que
la rompe individualmente y verifica que las demás capas la contienen:

- Layer (a) DB trigger: test simulates `UPDATE prod.factura_detalle` after
  insert → expects `fn_factura_detalle_inmutable` raises.
- Layer (b) Partial unique index (conditional MIGRATION 0027): test simulates
  concurrent INSERT same `uuid_factura` → expects `UniqueViolationError` →
  409 `factura_duplicada`.
- Layer (c) Typed exception: test simulates `IntegrityError("fk_*")` on
  `factura_detalle` INSERT → expects `FacturaDuplicadaError` / atomic rollback.
- Layer (d) Handler chain: tests T1..T9 verify the 12-step order + single
  commit + V6 ±0.01.
- Layer (e) AST walk: T10 verifies `len(commits) == 1`.

Transactional integrity gate: test integration T8 verifica que si
`crear_factura_detalle_bulk` falla (FK violation), el INSERT de `prod.facturas`
se hace rollback (no quedan filas huérfanas — KD-FACT-01).

Header gate: `Cache-Control: no-store` presente en toda respuesta 2xx/4xx/5xx
del endpoint (consistente con F1.3/F1.5/F1.6/F1.7/F1.8 precedents).

Pre-apply verification gate: pre-apply run of `grep "fn_facturas_inmutable"
migrations/` and `grep "one_pago_per_factura_init" migrations/`. Report
results; if either returns 0 matches, MIGRATION 0027 conditional authoring
proceeds; else no migration.

`ruff check`, `ruff format --check`, `mypy --strict` verde sobre los 8 archivos
nuevos/modificados (3 NEW + 2 MODIFY backend + 1 MODIFY `api/v1/__init__.py` +
1 MODIFY `schemas/clientes.py` + 1 conditional migration + 6 test files).

Precedente intacto: `git diff api/v1/operacion.py api/v1/empresa.py
api/deps.py auth/tenancy.py models/L_E/ingreso.py models/A/salidas.py models/V/*
repo/ingreso.py repo/subscripcion_activa.py repo/cotizacion.py repo/placa.py
repo/alerta.py repo/impuestos.py repo/versioned.py
migrations/versions/0026_*` retorna vacío (F1.6/F1.7/F1.8 helpers reutilizados
verbatim).

---

## 11. Dependencies & Sequencing

### 11.1 Depends on (closed)

- **HU-F1.7 (cerrada, `c320d0f`+`aa2fc9b`+`f826e8c`)** — `POST /operacion/salidas`
  con KD-FORZADO-01 verbatim reuse, KD-7 pre-flight, 12-step handler pattern,
  partial unique index `one_exit_per_ingreso`, MIGRATION 0026 KD-IVA resolver.
  F1.9 reuses `repo/impuestos.py::validar_iva_configurado` (F1.7) verbatim para
  V3.

- **HU-F1.8 (cerrada, `a3d0c39`)** — `prod.calcular_cotizacion(p_uuid_ingreso)`
  PL/pgSQL VOLATILE con `SELECT … FOR SHARE` sobre `tarifas_sucursal` (KD-1).
  F1.9 reuses the lock pattern via KD-FACT-02 (per-row scope on
  `factura_detalle.uuid_tarifa_sucursal`).

- **HU-F1.6 (cerrada, `2a2cbd2`)** — KD-FORZADO-01 prefix contract verbatim
  reuse pattern; `repo/ingreso.py::validar_kd_forzado` reference implementation.
  F1.9 does NOT use KD-FORZADO-01 directly (billing path has no V2/V5 bypass
  contract), but follows the same pattern for prefix validation on Pydantic
  schemas.

- **HU-F1.5 (cerrada, `bb99e18`)** — `repo/versioned.py::close_and_insert` (V2
  cliente conditional INSERT path). `prod.salidas` ORM model finalized in F1.7
  apply (originally proposed `models/L_S/salida.py` was superseded at apply in
  favor of reusing the pre-existing `[A]`-class ORM).

- **HU-F1.3 (cerrada, `ca3f9bf`)** — partial unique index pattern
  (`unique_active_sesion_per_user`) — F1.9's `one_pago_per_factura_init` mirrors
  this pattern.

- **HU-F1.4 (cerrada, `de4d2fc`)** — bi-temporal predicate
  (`bitemporal_vigente_predicate`) — F1.9 reads `prod.tarifas_sucursal` with the
  same predicate via KD-FACT-02 `FOR SHARE`.

- **HU-F1.2 (cerrada)** — KD-3 issuer chain (`_facturacion_issuer_dep =
  requires_issuer("admin-", "cajero-")`); `get_tenant_ctx` JWT extractor;
  `TenantContext` with `actor_uuid`, `sucursal_uuid`, `uuid_sesion`,
  `sucursales_permitidas`.

- **HU-F1.1 (cerrada, `f7cb37a`)** — `make_router` factory intact. F1.9 does
  NOT modify the factory (consistent with F1.6/F1.7/F1.8).

### 11.2 Blocks (unblocked after F1.9)

- **HU-F1.10** — Numeración FE + estado DIAN. HU-F1.10 needs `prod.facturas`
  rows (internal factura from F1.9) to number them via `assign_consecutivo` +
  `prod.factura_electronica`. Unblocked after F1.9 archive.

- **HU-F1.13** — Arqueo. HU-F1.13 consumes `prod.factura_pagos` for `cierre_dia`
  aggregation. Unblocked after F1.9 archive.

- **HU-F8.1** — Facturación consumidor final / FE consumer. HU-F8.1 consumes
  `prod.facturas` + `prod.factura_detalle` + `prod.factura_pagos` from F1.9.
  Unblocked after F1.9 archive.

### 11.3 Independent of (can run in parallel after F1.9)

- **HU-F1.11** — Reimpresión de tiquete. Independent of F1.9 (uses
  `prod.reimpresion_ticket` + `prod.costos_servicios` tables).
- **HU-F1.12** — Venta atómica de suscripción. Independent of F1.9 (uses
  `prod.subscripciones_cliente` + `prod.subscripcion_vehiculos` tables).
- **HU-F1.14** — Other CU-07 HUs. Independent of F1.9.
- **HU-F1.15** — Other HUs. Independent of F1.9.

### 11.4 Sequencing

```
explore ✅ → propose (this phase) → spec → design → tasks → apply → verify → archive
```

The proposal is ready for `sdd-spec` (REQ-OPS-053..063 formalization) +
`sdd-design` (architecture + migration details + AST walks + 14 tests) +
`sdd-tasks` (work units + acceptance gates).

**Adopted KDs**: KD-FACT-01, KD-FACT-02, KD-NIT-01, KD-NIT-02, KD-NIT-03,
KD-NIT-04, KD-NIT-05, KD-NIT-06, KD-NIT-07 (9 KDs, all from explore §14
resolved).

**Precedents mirrored**: F1.7 (KD-FORZADO-01 verbatim, KD-7 pre-flight, 12-step
handler chain, single-commit invariant, partial unique index pattern + AST walk
+ Idempotency-Key header), F1.8 (PL/pgSQL VOLATILE `calcular_cotizacion`,
`FOR SHARE` lock continuity KD-1), F1.6 (KD-FORZADO-01 prefix contract
verbatim, bi-temporal predicate reuse), F1.5 (KD-S1 unified 404 discriminator,
versioned.close_and_insert), F1.4 (bi-temporal `bitemporal_vigente_predicate`),
F1.3 (partial unique index pattern).

**Commits future**: conventional commits only, no AI attribution.

**PR target**: `origin/dev` from `feat/fase-1-prerequisites-backend`.

---

## 12. References

### 12.1 Files Read in This Phase

- `openspec/changes/hu-f1-9-facturacion/exploration.md` (just written by sdd-explore,
  16 sections, ~670 LOC)
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/{exploration,proposal,design,tasks,verify-report,archive-report}.md`
  (precedente: KD-FORZADO-01 verbatim + KD-7 pre-flight + 12-step handler
  pattern + MIGRATION 0026 + partial unique index pattern, commits `c320d0f`+
  `aa2fc9b`+`f826e8c`)
- `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/{exploration,proposal,design,tasks}.md`
  (precedente: PL/pgSQL VOLATILE `calcular_cotizacion` + `FOR SHARE` lock
  continuity KD-1, commit `a3d0c39`)
- `openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/{proposal,design,tasks}.md`
  (precedente: KD-FORZADO-01 prefix contract verbatim, commit `2a2cbd2`)
- `openspec/specs/operations/spec.md` (52 REQs REQ-OPS-001..052 merged, including
  REQ-OPS-042..052 from F1.7 already merged in archive `b4f1b45`)

### 12.2 Files to Reference During Apply/Verify

- `plan.md` lines 891-935 — HU-F1.9 definition (330 LOC, 4 tasks T1..T4)
- `plan.md` line 7672 — CU-04 closure context
- `plan.md` lines 2630-2637 — table impact table (`facturas` F1.9, `factura_detalle`
  F1.9, `factura_impuestos` F1.9, `factura_pagos` F1.9, `clientes` F1.9, `salidas`
  F1.7 + F1.9)
- `plan.md` lines 2403-2407 — endpoint table (`/facturacion/factura`,
  `/facturacion/factura-pagos` both closed in HU-F1.9;
  `/facturacion/factura-electronica` closed in HU-F1.10)
- `plan.md` lines 7449-7459 — `POST /facturacion/factura` JSON contract
- `plan.md` line 1849 — F8.1 tables consumed (`factura_pagos` INSERT,
  `facturas` INSERT, `factura_detalle` INSERT, `factura_impuestos` INSERT,
  `factura_electronica` INSERT, `salidas` UPDATE `estado='PAGADO'`)
- `plan.md` line 2527 — F1.9 success criteria checkpoint
- `modelo_datos_er.mmd` lines 667-687 — `prod.facturas [L-E]`
- `modelo_datos_er.mmd` lines 780-794 — `prod.factura_detalle [A]`
- `modelo_datos_er.mmd` lines 843-861 — `prod.factura_pagos [A]`
- `modelo_datos_er.mmd` lines 689-705 — `prod.factura_electronica [L-E]`
  (NO TOCADO en F1.9)
- `modelo_datos_er.mmd` lines 449-472 — `prod.clientes [V]`
- `modelo_datos_er.mmd` lines 187-207 — `prod.impuestos [V]`
- `modelo_datos_er.mmd` lines 406-426 — `prod.tarifas_sucursal [V]`
- `modelo_datos_er.mmd` lines 761-777 — `prod.salidas [A]` (F1.7 closed)
- `modelo_datos_er.mmd` lines 577-596 — `prod.ingreso [L-E]`
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines
  435-452 — `prod.clientes` (UK `(tipo_identificador, numero_identificacion,
  vigente_desde)`)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines
  607-654 — `prod.facturas` + `prod.factura_detalle` (TO VERIFY:
  `fn_facturas_inmutable` trigger existence)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines
  688-717 — `prod.factura_pagos` (TO VERIFY: `one_pago_per_factura_init`
  partial unique index existence)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines
  875-891 — `prod.factura_electronica` (F1.10 owns)
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines
  1378 — `fk_facturas_uuid_salida`
- `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` lines
  2024-2088 — `fn_*_inmutable` triggers for `factura_detalle`,
  `factura_impuestos`, `factura_pagos`
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` lines
  86-294 — `create_ingreso` (KD-3 tenant scope chain + `_ingreso_issuer_dep`
  reuse pattern, F1.6 commit `2a2cbd2`)
- `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py::validar_kd_forzado`
  (F1.6 verbatim helper, reference for `validar_nit_modulo11` Pydantic
  integration)
- `backend/packages/parkos_core/src/parkos_core/repo/cotizacion.py::cotizar_ingreso`
  (F1.8 thin wrapper, reference for `repo/factura.py` thin-wrapper pattern)
- `backend/packages/parkos_core/src/parkos_core/repo/impuestos.py::validar_iva_configurado`
  (F1.7 helper, REUSED VERBATIM in F1.9 V3)

### 12.3 Files to Author in Subsequent Phases

- `openspec/changes/hu-f1-9-facturacion/specs/facturacion-billing/spec.md` (NEW,
  sdd-spec)
- `openspec/changes/hu-f1-9-facturacion/specs/operations/spec.md` (NEW delta,
  sdd-spec)
- `openspec/changes/hu-f1-9-facturacion/design.md` (NEW, sdd-design)
- `openspec/changes/hu-f1-9-facturacion/tasks.md` (NEW, sdd-tasks)
- `openspec/changes/hu-f1-9-facturacion/verify-report.md` (NEW, sdd-verify)

### 12.4 Files to Author in Apply Phase

- `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (NEW,
  ~150 LOC: 2 handlers + dependencies)
- `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (NEW, ~250 LOC)
- `backend/packages/parkos_core/src/parkos_core/repo/factura_detalle.py` (NEW,
  ~80 LOC)
- `backend/packages/parkos_core/src/parkos_core/repo/nit_modulo11.py` (NEW, ~50 LOC)
- `backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py` (MODIFY,
  +1 line: `r.include_router(facturacion.router)`)
- `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (MODIFY,
  +80 LOC: `FacturaCreate`, `FacturaRead`, `FacturaItemCreate`,
  `FacturaItemRead`, `FacturaPagoAdicionalCreate`, `FacturaPagoRead`, 4 typed
  errors)
- `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py` (MODIFY,
  +10 LOC: Pydantic v2 `@field_validator` on `numero_identificacion`)
- `backend/packages/parkos_core/migrations/versions/0027_facturas_inmutable_trigger.py`
  (CONDITIONAL, ~80 LOC: pre-flight + `fn_facturas_inmutable` +
  `one_pago_per_factura_init`)
- `backend/packages/parkos_core/tests/unit/test_facturacion_factura.py` (NEW,
  ~400 LOC, 6 tests T1..T6)
- `backend/packages/parkos_core/tests/unit/test_validar_nit_modulo11.py` (NEW,
  ~150 LOC, 4 tests)
- `backend/packages/parkos_core/tests/unit/test_facturacion_factura_pagos.py`
  (NEW, ~150 LOC, 2 tests T7)
- `backend/packages/parkos_core/tests/integration/test_factura_atomicidad_db.py`
  (NEW, ~250 LOC, 2 tests T8+T9, `PARKOS_DOCKER_TEST=1`)
- `backend/packages/parkos_core/tests/static/test_factura_handler_single_commit.py`
  (NEW, ~80 LOC, 1 AST walk T10, KD-FACT-01)
- `backend/packages/parkos_core/tests/static/test_factura_handler_step_order.py`
  (NEW, ~80 LOC, 1 AST walk, 12-step order)
- `openspec/specs/operations/spec.md` (MODIFY, +11 REQs REQ-OPS-053..063 merged
  after archive)

### 12.5 Files NOT Touched (deliberate)

- `api/v1/operacion.py`, `api/v1/empresa.py`, `api/v1/caja_sesion.py` — F1.5/F1.6/F1.7
  handlers intact.
- `api/v1/router_factory.py` (`make_router` F1.1 commit `f7cb37a`, no se usa en
  `/facturacion`).
- `api/deps.py`, `auth/tenancy.py` — KD-3 chain intact.
- `models/L_E/ingreso.py`, `models/L_S/salida.py` (finalized F1.7), `models/V/*`,
  `models/A/{factura_detalle,factura_impuestos,factura_pagos}.py` — V1 reads are
  read-only; no schema changes.
- `repo/ingreso.py`, `repo/subscripcion_activa.py`, `repo/cotizacion.py`,
  `repo/placa.py`, `repo/alerta.py`, `repo/impuestos.py` (F1.7), `repo/versioned.py`
  (F1.5) — reused verbatim.
- `migrations/versions/0026_*` (F1.7 MIGRATION 0026) — chain head, NO modification.
- `IdempotencyKeyMiddleware` (PR2) — intact; DEC-IDEM-01 reuse.
- `web_sucursal/src/lib/validation/factura.ts` (Fase 2 frontend) — cleanup
  post-archive.

### 12.6 Decision Reconciliation Table

| Code | Source | Decision |
|---|---|---|
| DEC-FACT-01 | NEW (F1.9) | Single-commit invariant KD-FACT-01 |
| DEC-FACT-02 | NEW (F1.9) | FOR SHARE per-row lock KD-FACT-02 |
| DEC-FACT-03 | CONFIRMED (F1.7 reuse) | IVA from `prod.impuestos` only (DEC-IMP-01) |
| DEC-FACT-04 | NEW (F1.9) | MVP sin retención; deferred to Fase 4 |
| DEC-FACT-05 | NEW (F1.9) | `prod.facturas` sin `prefijo`+`consecutivo`; F1.10 owns |
| DEC-FACT-06 | NEW (F1.9) | `uuid_cliente` derivado server-side; NO FK |
| DEC-FACT-07 | NEW (F1.9) | Opción A: Pydantic `Literal[...]` enforced |
| DEC-FACT-08 | NEW (F1.9) | `consumidor_final` placeholder sin cliente |
| DEC-FACT-09 | NEW (F1.9) | NIT módulo 11 Variant A canónica (DIAN) |
| DEC-IMP-01 | CONFIRMED (F1.7) | `impuestos.IVA` inline-seeded in MIGRATION 0026 |
| DEC-IDEM-01 | CONFIRMED (F1.6) | Idempotency-Key HTTP header (PR2 middleware) |
| DEC-MONO-01 | CONFIRMED (F1.7) | One handler per resource; consolidation pattern |

---

**Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`.

**Adopted KDs**: KD-FACT-01, KD-FACT-02, KD-NIT-01..07 (9 KDs, all from explore
§14 resolved).

**Precedents mirrored**: F1.7 (REQ-OPS-042..052, KD-FORZADO-01 verbatim,
KD-7 pre-flight pattern, single-commit invariant, partial unique index
pattern + AST walk + Idempotency-Key header), F1.8 (REQ-OPS-022..025, VOLATILE
`calcular_cotizacion`, `FOR SHARE` lock continuity KD-1, 12-step handler
chain), F1.6 (REQ-OPS-034..041, KD-FORZADO-01 prefix contract verbatim, KD
chain ordering), F1.5 (REQ-OPS-030..033, KD-S1 unified 404 discriminator,
`repo/versioned.py::close_and_insert`), F1.4 (REQ-OPS-017..021, bi-temporal
predicate), F1.3 (REQ-OPS-026..029, partial unique index pattern + AST walk +
pre-flight abort).

**Commits future**: conventional commits only, no AI attribution.

**PR target**: `origin/dev` from `feat/fase-1-prerequisites-backend`.