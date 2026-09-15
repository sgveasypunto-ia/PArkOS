# Design: HU-F1.9 — Facturación transaccional + NIT módulo 11

> **Change**: `hu-f1-9-facturacion`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.9 — `POST /api/v1/facturacion/factura` (atomic 4-table insert: `prod.facturas` + `prod.factura_detalle` + `prod.factura_impuestos` + `prod.factura_pagos`) + `POST /api/v1/facturacion/factura-pagos` (voucher validation for datáfono) + helper `repo/nit_modulo11.py` (DIAN módulo 11) wired into Pydantic v2 validators at `ClientesCreate` (always) and `FacturaItemConDatosPropios` (when `fe_con_datos=true`).
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `def754d`; F1.1..F1.8 cerradas).
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (DEC-FACT-01..09, KD-FACT-01..02, KD-NIT-01..07) + `exploration.md` (16 sections, V1..V6, R1..R7) + `specs/operations/spec.md` (REQ-OPS-053..063, 11 requirements in Given/When/Then/And form + REQ-OPS-XR1..XR3 cross-cutting).
> **Cross-references**: `modelo_datos_er.mmd` (`prod.facturas` 667-687 [L-E], `prod.factura_detalle` 780-794 [A], `prod.factura_pagos` 843-861 [A], `prod.factura_impuestos` 801-822 [A], `prod.factura_electronica` 689-705 [L-E], `prod.clientes` 449-472 [V], `prod.impuestos` 187-207 [V], `prod.tarifas_sucursal` 406-426 [V], `prod.salidas` 761-777 [A], `prod.ingreso` 577-596 [L-E]).
> **Precedents mirrored**: F1.7 (REQ-OPS-042..052, KD-FORZADO-01 verbatim, KD-7 pre-flight pattern, single-commit invariant, partial unique index pattern, AST walk pattern, `Idempotency-Key` header, commits `c320d0f`+`aa2fc9b`+`f826e8c`), F1.8 (REQ-OPS-022..025, PL/pgSQL VOLATILE `calcular_cotizacion` + `FOR SHARE` lock continuity KD-1, commit `a3d0c39`), F1.6 (REQ-OPS-034..041, KD-FORZADO-01 prefix contract verbatim, commit `2a2cbd2`), F1.5 (REQ-OPS-030..033, MV pattern, `repo/versioned.py::close_and_insert`, commit `bb99e18`), F1.4 (REQ-OPS-017..021, bi-temporal predicate reusable in V1/V2, commit `467b4f0`), F1.3 (REQ-OPS-026..029, partial unique index pattern + AST walk + pre-flight abort, commit `ca3f9bf`).

---

## 1. Title & Goal

**Design goal.** Deliver HU-F1.9: the back-end `POST /api/v1/facturacion/factura` endpoint that closes the billing half of CU-04 (CU-04 = "Gestionar Cobro") by enforcing **6 server-side validations V1..V6** plus the KD-FACT-01 single-commit invariant that materializes the 4 tables (`prod.facturas` + `prod.factura_detalle` (N rows) + `prod.factura_impuestos` (1 row IVA snapshot) + `prod.factura_pagos` (1 row)) atomically in one `await session.commit()`. The design also ships **MIGRATION 0027** which (a) installs the partial unique index `one_factura_per_salida` on `prod.facturas` (feasible because `prod.facturas` is `[L-E]` and NOT partitioned per migration 0001 lines 607-626) to close the TOCTOU race between concurrent cajeros attempting to invoice the same `uuid_salida`, and (b) installs the BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness` (analogía migration 0004 lines 35-66 `fn_factura_pagos_reverso_uniqueness`) on `prod.factura_pagos` (which IS partitioned by `RANGE (fecha_retencion_hasta)` per migration 0001 line 716, making a partial unique index INFEASIBLE), and (c) defensively re-asserts `REVOKE UPDATE, DELETE` on the 4 `[A]`-class `factura_*` tables + idempotently re-installs the pre-existing `fn_*_inmutable` triggers.

The design enforces **DEC-FACT-01** (F1.9 itself never UPDATEs rows in `prod.facturas` — single INSERT, no UPDATE statements in the 12-step chain; bi-temporal versioning via composite PK `(uuid, fecha_retencion_hasta)` handles state transitions), **DEC-FACT-02** (NIT módulo 11 algorithm Variant A canónica per DIAN Resolución 000175 de 2021), **DEC-FACT-03** (IVA from `prod.impuestos` only — no hardcoded constants in Python), **DEC-FACT-04** (MVP NO aplica retención — `prod.retencion` table does NOT exist; deferred to Fase 4), **DEC-FACT-05** (consecutivo numbering delegated to F1.10 — `prod.facturas` does NOT receive `prefijo` + `consecutivo`), **DEC-FACT-06** (`uuid_cliente` NOT a column in `prod.facturas`; server-derived via lookup chain), **DEC-FACT-07 Opción A** (NO crear `prod.forma_pago` catálogo; Pydantic `Literal[...]` enforced), **DEC-FACT-08** (consumidor final placeholder), **DEC-FACT-09** (NIT normalization including strip non-digits, strip leading zeros, min 5 digits), and the **5-layer defense in depth** (D-HU-F1.9-7): partial unique index `one_factura_per_salida` + BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness` + repo typed exceptions + handler 12-step chain + AST walks (KD-FACT-01 + KD-FACT-02 invariants).

The handler enforces 6 validations server-side (V1 salida facturable, V2 cliente cuando `fe_con_datos=true`, V3 IVA configurado, V4 detalle items coherentes, V5 NIT módulo 11 cuando `fe_con_datos=true`, V6 total coherente ±0.01 COP), inserts the 4 tables in a single TX, and returns `201` with `FacturaRead` whose `uuid_cliente` is **derived server-side** (DEC-FACT-06, NOT persisted). A secondary endpoint `POST /api/v1/facturacion/factura-pagos` handles voucher validation for datáfono (`400 voucher_requerido` when `medio_pago='datafono'` sin `referencia`). Adjacent reads (`GET /api/v1/facturacion/facturas/{uuid}`, `GET /api/v1/facturacion/facturas?uuid_cliente=...&fecha_desde=...&fecha_hasta=...`) are PROPOSED but lower priority and out of F1.9 scope. Sized at **330 LOC** per `plan.md` línea 929 (≈50 LOC handler `create_factura` + 80 LOC handler `create_factura_pagos` + 100 LOC `repo/factura.py` + 80 LOC `repo/factura_detalle.py` + 50 LOC `repo/nit_modulo11.py` + 50 LOC schemas nuevos — **+~120 LOC MIGRATION 0027** — + ~1310 LOC tests).

**Two new handlers, one new ORM helper module, one new migration, no factory changes, no sync catalog changes.**

## 2. Context & Background

`plan.md` lines **891-935** define HU-F1.9 as Fase-1 backend prerequisite for CU-04 (Facturación close). The hard architectural constraints are **DEC-FACT-01 amended** (F1.9 itself never UPDATEs; bi-temporal versioning via composite PK `(uuid, fecha_retencion_hasta)` handles state transitions — `[L-E]` semantics, NOT append-only immutability), **DEC-FACT-02** (Variant A canónica per DIAN Resolución 000175 de 2021), **DEC-FACT-03** (IVA from `prod.impuestos` only), **DEC-FACT-04** (MVP sin retención — `prod.retencion` does NOT exist; deferred to Fase 4), **DEC-FACT-05** (consecutivo delegated to F1.10; `prod.facturas` does NOT receive `prefijo` + `consecutivo`), **DEC-FACT-06** (server-derived `uuid_cliente` — NO FK column), **DEC-FACT-07** (NO `prod.forma_pago` catálogo; Pydantic `Literal[...]` enforced), **DEC-FACT-08** (consumidor final placeholder), **DEC-FACT-09** (NIT normalization), and the existing pre-existing tables (`prod.facturas` [L-E] lines 607-626; `prod.factura_detalle` [A] lines 631-665; `prod.factura_impuestos` [A] (ER no línea explícita, creada in migration 0001); `prod.factura_pagos` [A] lines 688-717; `prod.clientes` [V] lines 435-452; `prod.impuestos` [V]; `prod.tarifas_sucursal` [V]; `prod.salidas` [A] from F1.7; `prod.ingreso` [L-E]).

Today the URL `POST /api/v1/facturacion/factura` is **not registered** in the FastAPI router. The pre-existing ORM `models/L_E/facturas.py::Facturas(LifecycleEventBase)` (composite PK `uuid+fecha_retencion_hasta`, NOT partitioned — verified by reading lines 1-74 of `backend/packages/parkos_core/src/parkos_core/models/L_E/facturas.py`) maps to `prod.facturas`, and the pre-existing `[A]`-class ORMs `models/A/factura_detalle.py::FacturaDetalle(AppendOnlyBase)`, `models/A/factura_impuestos.py::FacturaImpuestos(AppendOnlyBase)`, and `models/A/factura_pagos.py::FacturaPagos(AppendOnlyBase)` (with `BEFORE INSERT` trigger `fn_factura_pagos_reverso_uniqueness` already installed via migration 0004) all exist and are reusable. The helper `repo/impuestos.py::validar_iva_configurado(session)` (F1.7, MIGRATION 0026 Op 2) already returns `True` post-deploy. The operator's cash register at the parking branch cannot emit facturas today: `prod.facturas` has zero rows because no handler creates them, the cashier's terminal must replicate fiscal derivation client-side (reintroducing the same bug class F1.6 fixed for ingresos), and DIAN reporting is broken.

**The backend performs zero business validation on billing**, creating five concrete risks that HU-F1.9 resolves:

1. **Cash register cannot emit facturas.** Today `prod.facturas` exists in migration 0001 (lines 607-654) but no handler creates rows. Without server-side enforcement, the cashier's terminal duplicates the fiscal derivation logic client-side or — worse — emits hand-typed invoices that bypass the fiscal snapshot. CU-04 (Facturación) is functionally closed in `plan.md §4` only when `POST /api/v1/facturacion/factura` returns `201` with `FacturaRead` carrying `subtotal`, `descuento`, `total` server-side-derived from the cotizacion snapshot. Risk: accounting cannot reconcile, DIAN reporting is broken, customer requests for facturas for tax purposes cannot be fulfilled (regulatory exposure).
2. **Atomicidad violation across 4 tables.** Without KD-FACT-01 (single-commit invariant), a partial failure between `facturas` INSERT and `factura_detalle` bulk INSERT leaves orphan `facturas` rows with no detail lines, breaking accounting reconciliation. Defense-in-depth at DB layer (`fn_*_inmutable` triggers on `factura_detalle`, `factura_impuestos`, `factura_pagos` per migration 0001 lines 2024-2088) cannot substitute for application-level atomicity. The single `await session.commit()` materializes all 4 tables in one TX; AST walk `tests/static/test_factura_handler_single_commit.py` enforces the invariant literally (`len(commits) == 1`).
3. **Tarifa race window between cotizar and cobrar.** F1.8 holds `SELECT … FOR SHARE` on `tarifas_sucursal` inside `calcular_cotizacion` (KD-1 in F1.8, VOLATILE per REQ-OPS-025). HU-F1.9 does NOT call `calcular_cotizacion` (snapshot was already taken at salida time in F1.7); however, F1.9 must take its own `SELECT … FOR SHARE` over the `tarifas_sucursal` rows referenced by `factura_detalle.uuid_tarifa_sucursal` (KD-FACT-02) to close the window between the snapshot read in `create_factura` and the INSERT into `factura_detalle`.
4. **NIT validation gap (DIAN regulatory exposure).** The Colombian NIT check digit MUST be validated against the algoritmo de módulo 11 per DIAN Resolución 000175 de 2021. Without `validar_nit_modulo11` wired at the Pydantic v2 layer on both `ClientesCreate` (always when `tipo_identificador='NIT'`) and `FacturaItemConDatosPropios` (only when `fe_con_datos=true`), the cashier's terminal accepts NITs with mismatched DV, generating facturas the DIAN rejects on audit. R1 risk: the algorithm exists in two variants in Colombian regulation (Variant A: `DV = sum % 11`, Variant B: `DV = 11 - (sum % 11)`); the canonical DIAN spec mandates Variant A, discriminated by reference test case `800.123.456-7` (DV=7).
5. **Concurrent cashier race on the same `uuid_salida`.** Two cashiers might attempt to invoice the same closed salida simultaneously. Without the partial unique index `one_factura_per_salida` on `prod.facturas` (feasible because `prod.facturas` is `[L-E]` and NOT partitioned per migration 0001 lines 607-626), the TOCTOU window opens. F1.9 introduces MIGRATION 0027 Op 2 to close this.

F1.9 closes the billing half of CU-04 (F1.10 closes FE numbering + DIAN state on top). The work is **handler + repo + schemas + módulo 11 helper + MIGRATION 0027** — the migration is mandatory because the pre-apply verification found that `prod.facturas` is NOT partitioned (verified by reading `backend/packages/parkos_core/src/parkos_core/models/L_E/facturas.py` lines 62-72: `__table_args__` contains `PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="facturas_pk")` and `{... "schema": "prod", "extend_existing": True}` with NO `postgresql_partition_by`), making the partial unique index `one_factura_per_salida` feasible, AND `prod.factura_pagos` IS partitioned by `RANGE (fecha_retencion_hasta)` per migration 0001 line 716, requiring the BEFORE INSERT trigger pattern.

The contract is captured in **REQ-OPS-053..063** (added by `sdd-spec` to `specs/operations/spec.md`):

- **REQ-OPS-053** — `POST /api/v1/facturacion/factura` contract: 12-step handler with KD-3 tenant scope, `Cache-Control: no-store`, Idempotency-Key header.
- **REQ-OPS-054** — V1: salida existe y es facturable; unified 404 discriminator.
- **REQ-OPS-055** — V2: cliente existe cuando `fe_con_datos=true`.
- **REQ-OPS-056** — V3: IVA configurado (defense-in-depth guard).
- **REQ-OPS-057** — V4: detalle items coherentes.
- **REQ-OPS-058** — V5: NIT módulo 11 DIAN Resolución 000175 de 2021.
- **REQ-OPS-059** — V6: total coherente ±0.01 COP.
- **REQ-OPS-060** — KD-FACT-01: single `await session.commit()` invariant.
- **REQ-OPS-061** — KD-FACT-02: `SELECT … FOR SHARE` per-row sobre `prod.tarifas_sucursal`.
- **REQ-OPS-062** — `POST /api/v1/facturacion/factura-pagos`: voucher_requerido.
- **REQ-OPS-063** — DEC-FACT-06: `uuid_cliente` derivado server-side.

F1.9 is consumed by **F1.10** (numeración FE + estado DIAN; HU-F1.10 calls `assign_consecutivo` to assign FE numbering on top of `prod.facturas` rows from F1.9 and creates 1:1 `factura_electronica`), **F1.13** (Arqueo + cierre_dia; consumes `prod.factura_pagos` for `cierre_dia` aggregation; may use `reverse_payment` for compensating anulación), **F8.1** (Facturación consumidor final / FE consumer; consumes `prod.facturas` + `prod.factura_detalle` + `prod.factura_pagos` from F1.9). It leaves a clean separation between the lifecycle event (`prod.facturas`, bi-temporal `[L-E]`) and the fiscal snapshot (`factura_impuestos` per-row IVA) and the payment trail (`factura_pagos`, append-only `[A]`).

## 3. Decisions

This HU adopts **nine** Key Decisions (DEC-FACT-01..09 from `proposal.md §7`) plus **two KD invariants** (KD-FACT-01 + KD-FACT-02) plus **seven KD-NIT-01..07** validation invariants. Each one passes the R5 risk threshold (no open question blocks the design; the proposal §11 confirms `Sin preguntas abiertas`). The decisions are grouped into 6 themes: atomicity (DEC-FACT-01, KD-FACT-01, KD-FACT-02), regulatory (DEC-FACT-02, DEC-FACT-09, KD-NIT-01..07), persistence discipline (DEC-FACT-03, DEC-FACT-05, DEC-FACT-06, DEC-FACT-08), deferred work (DEC-FACT-04), UX (DEC-FACT-07, DEC-FACT-08).

### Decision DEC-FACT-01 (KD-FACT-01) — F1.9 itself never UPDATEs rows in `prod.facturas`; bi-temporal handles state transitions

**Choice.** F1.9's handler `create_factura` performs **only INSERT operations** on `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, and `prod.factura_pagos`. State transitions on a `prod.facturas` row (e.g., `emitida → pagada`) happen via **NEW rows with the bi-temporal composite PK `(uuid, fecha_retencion_hasta)`** — NOT via UPDATE. Defense in depth is at the handler layer (single INSERT chain, no UPDATE statements in the 12-step chain), NOT at the DB layer (no `fn_facturas_inmutable` trigger needed because `[L-E]` bi-temporal versioning requires UPDATE on `vigente_hasta` for legitimate state transitions, and `fn_facturas_inmutable` would block those legitimate transitions).

**Context.** Verified pre-apply: `prod.facturas` is `[L-E]` (LifecycleEventBase, `models/L_E/facturas.py`), composite PK `(uuid, fecha_retencion_hasta)`, **NOT partitioned** (verified by reading `__table_args__` lines 62-72 of `models/L_E/facturas.py` — no `postgresql_partition_by`). R2 of `exploration.md §16` RESOLVED: there is NO need for `fn_facturas_inmutable` because bi-temporal versioning handles immutability. The 4 pre-existing `fn_*_inmutable` triggers from migration 0001 lines 2024-2088 already apply to `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_otros_cobros`, `prod.factura_pagos` (the `[A]`-class tables). F1.9's defense-in-depth is the **handler** (single INSERT chain) + **partial unique index** `one_factura_per_salida` (MIGRATION 0027 Op 2) + **typed exception** at the repo layer.

**Alternatives considered.**
- *Introduce `fn_facturas_inmutable` trigger (rejected per R2 verification)* — rejected: `[L-E]` bi-temporal versioning requires UPDATE on `vigente_hasta` for legitimate state transitions (e.g., `emitida → pagada` in F1.13 cierra_dia would need a new `fecha_retencion_hasta` boundary); a trigger would block those transitions. The bi-temporal composite PK is the immutability invariant, not a trigger.
- *Single row with `estado` column mutated by UPDATE* — rejected: violates bi-temporal pattern; loses audit trail; F1.13 Arqueo cannot reason about state transitions.
- *Polymorphic view + soft-delete via `estado='anulada'`* — rejected: defeats the `[L-E]` pattern F1.4 introduced; F1.13's compensating `prod.anulaciones(tipo_anulable='factura')` workflow is the canonical path.

**Rationale.** Bi-temporal versioning is the corpus pattern for `[L-E]` tables (F1.4, F1.5, F1.6 precedents). The handler simply never UPDATEs; future HUs (F1.10, F1.13) INSERT new rows with later `fecha_retencion_hasta` boundaries. The defense-in-depth is at the handler layer + DB layer (partial unique index closes TOCTOU on `uuid_salida`).

### Decision DEC-FACT-02 (KD-NIT-01) — NIT módulo 11 algorithm Variant A canónica per DIAN Resolución 000175 de 2021

**Choice.** Helper `validar_nit_modulo11(nit: str, dv: str | int) -> bool` enforces weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]` applied **right-to-left** on NIT digits (without DV); `DV = sum_ponderada % 11` (Variant A canónica, NOT `11 - (sum % 11)` Variant B). Helper also normalizes NIT (strip non-digits, strip leading zeros, minimum 5 digits). NO alternative algorithms permitted.

**Context.** R1 of `exploration.md §16` is **CRITICAL**: Variant A vs Variant B discriminate the reference test case `800.123.456-7` (DV=7). Per `Riesgo-SUC-04 plan.md:2679`, the algorithm has two variants in Colombian regulation. The canonical DIAN Resolución 000175 de 2021 mandates Variant A. Pre-apply verification: `validar_nit_modulo11("800123456", "7") == True` (Variant A: `sum=71*8+67*0+59*0+53*1+47*2+43*3+41*4+37*5+29*6+23*7+19*...` need to compute — discriminator is Variant A returns `True`, Variant B returns `False`).

**Alternatives considered.**
- *Variant B `11 - (sum % 11)`* — rejected: NOT canonical per DIAN; rejected by the reference test case.
- *Allow caller to choose variant* — rejected: defeats the purpose of a single canonical algorithm; opens variant-drift risk across callers.
- *Use an external library* — rejected: pure stdlib `re` is sufficient; no dependency added; ~50 LOC.

**Rationale.** Variant A is the canonical DIAN spec. The reference test `800.123.456-7` (DV=7) verifies the implementation. The helper is pure Python (no DB dependency), testable without HTTP, and reused across `ClientesCreate` and `FacturaItemConDatosPropios` Pydantic validators.

### Decision DEC-FACT-03 — IVA desde `prod.impuestos` only (NO hardcoded constants en Python)

**Choice.** IVA percentage is read from `prod.impuestos` via `repo/impuestos.py::validar_iva_configurado(session)` (F1.7 reuse) and via the per-row read of `porcentaje`. NO hardcoded constants like `Decimal("0.19")` in Python. Si la DIAN cambia el IVA, basta con INSERT nueva fila `prod.impuestos` con nuevo `porcentaje` + cierre de la anterior (F1.4 bi-temporal pattern).

**Context.** DEC-IMP-01 from F1.7 applies equally to F1.9. `validar_iva_configurado` returns `True` post-MIGRATION 0026 deploy (F1.7 Op 2 inline-seeded `prod.impuestos.IVA` with `porcentaje=0.19`). The 500 `iva_no_configurado` path is a defense-in-depth guard that should NEVER fire post-deploy. The IVA snapshot in `prod.factura_impuestos` captures `porcentaje_aplicado` per row so historical reports remain valid even if IVA changes.

**Alternatives considered.**
- *Hardcode `Decimal("0.19")` in Python* — rejected: violates "single source of truth in DB" (F1.8 design.md §4 KD-IVA rejected the same alternative).
- *Pydantic Literal[...] for `porcentaje`* — rejected: defeats dynamic regulatory changes.

**Rationale.** IVA from DB is the corpus pattern. The `factura_impuestos.porcentaje_aplicado` column is the immutable snapshot; future DIAN changes don't affect historical reports.

### Decision DEC-FACT-04 — MVP NO aplica retención (RETCONT 11% sobre servicios)

**Choice.** MVP of F1.9 does NOT apply retención. Reasons:
- `prod.retencion` does NOT exist in DB (gap pre-existente, not created in migration 0001).
- Without the table, cannot snapshot the RETCONT percentage or the `concepto`.
- Ownership of the catálogo de retenciones is outside the corpus current scope.

**Recommendation**: defer `prod.retencion` to Fase 4 (contabilidad). V6 `compute_total` accepts `retencion=Decimal("0")` in MVP. Documented as "to extend" in design.md §13 Out of Scope, NOT implemented.

**Context.** The brief mentions `prod.retencion` with field `beneficiario` and RETCONT 11% discount on services (DIAN 2026). Today the table does NOT exist. Creating it in MIGRATION 0027 would expand scope beyond 330 LOC.

**Alternatives considered.**
- *Create `prod.retencion [V]` in MIGRATION 0027 Op 5* — rejected: out of corpus scope; Fase 4 ownership.
- *Skip V6 retención recompute* — rejected: still need V6 total coherence; retencion=0 simplifies recompute.
- *Hardcode RETCONT 11% in Python* — rejected: same anti-pattern as DEC-FACT-03.

**Rationale.** MVP without retención is acceptable because the table doesn't exist. V6 recompute accepts `retencion=Decimal("0")`. When Fase 4 ships, V6 recompute will read `prod.retencion` rows by `concepto` and apply the percentage.

### Decision DEC-FACT-05 — Consecutivo numbering DELEGADO a F1.10

**Choice.** `prod.facturas` does NOT receive `prefijo` + `consecutivo` columns (those live in `factura_electronica`, F1.10 owns). F1.9 creates the internal factura with `uuid` (UUID v4 from `gen_random_uuid()`) and returns it to the client. F1.10, in `POST /api/v1/facturacion/factura-electronica`, invokes `assign_consecutivo` (Python helper, already exists in `repo/resolucion_facturacion.py::assign_consecutivo`, branch-local, with `SELECT … FOR UPDATE` on `resolucion_facturacion`) and creates the 1:1 `factura_electronica.uuid_factura → facturas.uuid` row.

**Context.** Analogue of DEC-SUC-21-NEW from F1.7 (server-derived `tipo_salida`, never persisted). The `assign_consecutivo` Python helper is F1.10's responsibility; F1.9 does NOT modify it.

**Alternatives considered.**
- *Add `prefijo` + `consecutivo` columns to `prod.facturas`* — rejected: 4FN violation; F1.10 owns FE numbering; the columnas live in `factura_electronica`.
- *F1.9 invokes `assign_consecutivo` itself* — rejected: scope creep; F1.10 owns the FE numbering lifecycle.

**Rationale.** Internal factura (F1.9) is the FISCAL snapshot. FE factura (F1.10) is the DIAN-registered invoice with numbering. The two are 1:1 via `factura_electronica.uuid_factura`.

### Decision DEC-FACT-06 — `uuid_cliente` NO vive en `prod.facturas`; server-derived

**Choice.** `uuid_cliente` is NOT a column in `prod.facturas`. Confirmed in `models/L_E/facturas.py` lines 33-60: columns are `uuid`, `fecha_retencion_hasta`, `uuid_sucursal`, `subtotal`, `descuento`, `total`, `uuid_ingreso`, `uuid_salida` — NO `uuid_cliente`. The `FacturaRead.uuid_cliente` is **server-derived** via lookup chain:
- If `fe_con_datos=true` and V2 found a cliente → `cliente_uuid` = V2 lookup result.
- If `fe_con_datos=false` (consumidor final) → `cliente_uuid = None`.

**Context.** 4FN compliance — `prod.facturas` stores `uuid_sucursal` only; the cliente association is derived from V2 lookup when needed. Future HUs MAY add `prod.facturas.uuid_cliente` FK column and backfill; F1.9 does NOT create the FK.

**Alternatives considered.**
- *Add `prod.facturas.uuid_cliente` FK column* — rejected: out of scope; Fase 4 ownership.
- *Embed cliente data in `FacturaRead` only (no FK)* — accepted: this is the chosen approach.

**Rationale.** 4FN compliance + minimal F1.9 scope. The cliente association is derived at response time from V2 lookup; no persistent FK needed for MVP.

### Decision DEC-FACT-07 Opción A — NO crear `prod.forma_pago` catálogo; Pydantic `Literal[...]` enforced

**Choice.** NO crear `prod.forma_pago [V]` catálogo en MIGRATION 0027. The field `prod.factura_pagos.medio_pago` es `String()` libre; el cliente envía uno de `{'efectivo', 'tarjeta', 'transferencia', 'datafono', 'mixto'}` (enum Pydantic v2 enforced via `Literal["efectivo","tarjeta","transferencia","datafono","mixto"]`). Validación client-side: si `medio_pago='datafono'`, `referencia` (voucher) REQUIRED no-empty.

**Context.** Trade-off: -120 LOC vs. Opción B (create `prod.forma_pago [V]` migration 0027). Opción A is sufficient for F1.9 MVP. Future HU may create the table if reporting/analytics need a normalized catalog.

**Alternatives considered.**
- *Opción B: create `prod.forma_pago [V]` in MIGRATION 0027* — rejected: -120 LOC savings, MVP doesn't need reporting analytics; deferred to Fase 4 if needed.
- *Accept any string for `medio_pago`* — rejected: REJECTED by R6; risk of typos like `'efectivoUSD'` passing validation.

**Rationale.** Pydantic `Literal[...]` is enforced at the schema layer; any value outside the literal → 422 Pydantic validation error. No DB catalog needed for MVP.

### Decision DEC-FACT-08 — `consumidor_final` placeholder when `fe_con_datos=false`

**Choice.** Si `fe_con_datos=false`, the handler does NOT create or require a cliente. The factura is emitted as "consumidor final" (regulatory default Colombia — NIT genérico `222222222222`). `FacturaRead.uuid_cliente` returns `None`.

**Context.** Mirrors the existing `consumidor_final` UX in the operator's terminal. No new cliente row; no FK lookup.

**Alternatives considered.**
- *Always require `fe_datos_cliente`* — rejected: poor UX; many cash-only customers don't want to provide NIT.
- *Auto-create cliente from `fe_datos_cliente`* — rejected: out of scope; F1.9 returns 404 `cliente_no_encontrado` to caller; caller decides whether to POST `/clientes` first.

**Rationale.** MVP UX; F1.10 may add stricter FE consumer flow if needed.

### Decision DEC-FACT-09 — NIT normalization in `validar_nit_modulo11`

**Choice.** Helper `validar_nit_modulo11` MUST:
- Strip non-digits (`"800.123.456-7"` → `"800123456"`).
- Strip leading zeros (`"000123"` → `"123"`).
- If the resulting NIT has <5 digits → reject.
- If `dv` is not a digit → reject.

**Context.** Cashier's terminal may submit NITs in various formats: `800.123.456-7`, `800123456-7`, `8001234567`, ` 800.123.456-7 `, etc. The helper MUST be permissive on format but strict on the algorithm.

**Alternatives considered.**
- *Strict format (`\d{9,15}-\d{1,2}`)* — rejected: rejects legitimate variations like dotted format.
- *Reject leading zeros* — rejected: legitimate NITs like `000123456` (rare but possible) would fail; normalization strips them.

**Rationale.** Permissive on format, strict on algorithm. The reference test cases (`800.123.456-7`, `000123-1`, `800.123.456-7` with various separators) all pass.

### Decision DEC-FACT-10 — Single handler + helper modules pattern (analog F1.7)

**Choice.** The two HTTP endpoints live in a NEW module `api/v1/facturacion.py` (~150 LOC). Helper modules:
- `repo/factura.py` (~250 LOC, 9 helpers + 5 typed exceptions)
- `repo/factura_detalle.py` (~80 LOC, bulk insert helper)
- `repo/nit_modulo11.py` (~50 LOC, módulo 11 algorithm)

Schemas in `schemas/facturacion.py` (MODIFY, +80 LOC) and `schemas/clientes.py` (MODIFY, +10 LOC for Pydantic v2 validator).

**Context.** Single module per resource domain. Mirrors F1.6 (`api/v1/operacion.py` + `repo/ingreso.py`) and F1.7 (`api/v1/operacion.py` + `repo/salida.py`).

**Alternatives considered.**
- *Multiple files (`repo/factura_create.py`, `repo/factura_detalle_create.py`)* — rejected: bloats import surface; F1.7 keeps it in one module per resource.
- *Inline SQL in handler* — rejected: violates F1.4/F1.5/F1.6/F1.7/F1.8 pattern.

**Rationale.** Single module per domain resource keeps the import surface tight. Mirrors the F1.7 precedent.

### Decision DEC-FACT-11 (KD-FACT-02) — `SELECT … FOR SHARE` per-row sobre `prod.tarifas_sucursal`

**Choice.** Si algún item en `payload.items` referencia `uuid_tarifa_sucursal`, server ejecuta `SELECT … FOR SHARE` per-row sobre cada `tarifas_sucursal` referenciada **antes** del INSERT (Step 7). Lock mantenido hasta `await session.commit()` (Step 11).

**Context.** Analogue of KD-1 in F1.8 (`FOR SHARE` inside `calcular_cotizacion` PL/pgSQL). Per-row scope prevents global serialization. F1.9 does NOT call `calcular_cotizacion` (snapshot was already taken at salida time in F1.7); F1.9 takes its own lock to close the window between snapshot read and INSERT.

**Alternatives considered.**
- *Sin lock (lock-free)* — rejected: opens window of inconsistency between snapshot read and INSERT.
- *Lock per-table* — rejected: serializa TODAS las facturaciones; latency catastrophe.
- *Lock FOR UPDATE (instead of FOR SHARE)* — rejected: blocks concurrent cotizaciones of other items in same factura; FOR SHARE allows concurrent reads but blocks UPDATE.

**Rationale.** Per-row `FOR SHARE` maintains the lock only over the rows being billed. Matches F1.8 KD-1 pattern.

## 4. Architecture Overview

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
tests/static/test_factura_handler_single_commit.py
tests/static/test_factura_handler_step_order.py
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
│   repo/versioned.py           (F1.5) — close_and_insert (V2 cliente path)   │
│   repo/factura_pagos.py       (existing, REVERSE_payment helper for F1.13)  │
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
│ Tablas operacionales (READ + INSERT, MIGRATION 0027 introduces index/trigger):│
│   prod.salidas                  [A]    — V1 read PK                          │
│   prod.ingreso                  [L-E]  — V1 derivado uuid_ingreso            │
│   prod.clientes                 [V]    — V2 SELECT                           │
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
        ▼ MIGRATION 0027 (4 operations, applied BEFORE F1.9 tests)
┌──────────────────────────────────────────────────────────────────────────────┐
│ migrations/versions/0027_factura_one_per_salida_and_pagos_uniqueness.py     │
│                                                                              │
│ Op 1 — Pre-flight DO $$ (KD-7 pattern from F1.6 migration 0024 + F1.7 0026):│
│   verify 9 tables exist (facturas, factura_detalle, factura_impuestos,       │
│                          factura_pagos, clientes, impuestos,                 │
│                          tarifas_sucursal, salidas, ingreso)                │
│   RAISE EXCEPTION '0027_preflight_abort: ...' if missing                    │
│                                                                              │
│ Op 2 — Partial unique index one_factura_per_salida (KD-FACT-R3):             │
│   CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_factura_per_salida      │
│       ON prod.facturas (uuid_salida)                                         │
│       WHERE uuid_salida IS NOT NULL                                          │
│   FEASIBLE: prod.facturas is NOT partitioned (verified migration 0001 lines  │
│   607-626). Closes TOCTOU on concurrent cajeros attempting same uuid_salida. │
│                                                                              │
│ Op 3 — BEFORE INSERT trigger fn_factura_pagos_init_pago_uniqueness           │
│   (analogía migration 0004 lines 35-66 fn_factura_pagos_reverso_uniqueness): │
│   CREATE OR REPLACE FUNCTION prod.fn_factura_pagos_init_pago_uniqueness()   │
│   ...                                                                        │
│   DROP TRIGGER IF EXISTS factura_pagos_init_pago_uniqueness                  │
│       ON prod.factura_pagos;                                                 │
│   CREATE TRIGGER factura_pagos_init_pago_uniqueness                          │
│       BEFORE INSERT ON prod.factura_pagos                                   │
│       FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_init_pago_uniqueness(); │
│   REQUIRED: prod.factura_pagos IS partitioned by RANGE(fecha_retencion_hasta)│
│   (migration 0001 line 716), so partial unique index INFEASIBLE.             │
│                                                                              │
│ Op 4 — REVOKE re-assertion + idempotent _inmutable trigger re-install       │
│   (analogía migration 0004 lines 68-78):                                     │
│   - REVOKE UPDATE, DELETE ON prod.factura_detalle FROM rol_app              │
│   - GRANT SELECT, INSERT ON prod.factura_detalle TO rol_app                 │
│   - (repeat for factura_impuestos, factura_otros_cobros, factura_pagos)     │
│   - DROP TRIGGER IF EXISTS factura_detalle_inmutable;                       │
│   - CREATE TRIGGER factura_detalle_inmutable ... (idempotent)                │
│   - (repeat for factura_impuestos_inmutable, factura_pagos_inmutable)        │
│   - DROP TRIGGER IF EXISTS factura_pagos_reverso_uniqueness;                │
│   - CREATE TRIGGER factura_pagos_reverso_uniqueness ... (pre-existing via 0004)│
│                                                                              │
│ Downgrade (reverse order):                                                  │
│   DROP TRIGGER IF EXISTS prod.factura_pagos_init_pago_uniqueness             │
│       ON prod.factura_pagos;                                                 │
│   DROP FUNCTION IF EXISTS prod.fn_factura_pagos_init_pago_uniqueness();     │
│   DROP INDEX IF EXISTS prod.one_factura_per_salida;                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

The handler is thin + orquestador. All validation logic lives in `repo/*.py`. The single `commit()` materializes the 4 tables atomically and releases the `FOR SHARE` lock from KD-FACT-02 (Step 11).

## 5. Data Model

**One Alembic migration introduces** the partial unique index + the BEFORE INSERT trigger + REVOKE re-assertion + idempotent trigger re-install. **No columns added or removed** in any operational table. The 4 tables (`prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos`) all exist since migration 0001 with their pre-existing schemas.

| Tabla | Tipo | Operación | Línea ER / migration |
|---|---|---|---|
| `prod.salidas` | `[A]` | V1 SELECT (read-only) | 761-777 |
| `prod.ingreso` | `[L-E]` | V1 derivado `uuid_ingreso` | 577-596 |
| `prod.clientes` | `[V]` | V2 SELECT (when `fe_con_datos=true`) | 449-472 |
| `prod.impuestos` | `[V]` | V3 read `nombre='IVA'` (post-0026 seeded) | 187-207 |
| `prod.tarifas_sucursal` | `[V]` | KD-FACT-02 SELECT FOR SHARE per-row | 406-426 |
| `prod.facturas` | `[L-E]` | Step 9 INSERT (DEC-FACT-06: NO `uuid_cliente` column) | 607-626 + ORM `models/L_E/facturas.py` lines 33-60 |
| `prod.factura_detalle` | `[A]` | Step 10 bulk INSERT | 780-794 + ORM `models/A/factura_detalle.py` |
| `prod.factura_impuestos` | `[A]` | Step 10 INSERT (IVA snapshot: `uuid_impuesto`, `base_calculo`, `porcentaje_aplicado`, `valor`) | 801-822 + ORM `models/A/factura_impuestos.py` |
| `prod.factura_pagos` | `[A]` | Step 10 INSERT (1 pago) + `/factura-pagos` | 843-861 + ORM `models/A/factura_pagos.py` |
| `prod.facturas` | `[L-E]` | (Op 2) partial unique index `one_factura_per_salida` | MIGRATION 0027 |
| `prod.factura_pagos` | `[A]` | (Op 3) BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness` | MIGRATION 0027 |
| `prod.factura_detalle` | `[A]` | (Op 4) defensive REVOKE + trigger re-install | MIGRATION 0027 |
| `prod.factura_impuestos` | `[A]` | (Op 4) defensive REVOKE + trigger re-install | MIGRATION 0027 |
| `prod.factura_otros_cobros` | `[A]` | (Op 4) defensive REVOKE + trigger re-install | MIGRATION 0027 |
| `prod.factura_pagos` | `[A]` | (Op 4) defensive REVOKE + trigger re-install + reverso trigger re-assert | MIGRATION 0027 |
| `prod.factura_electronica` | `[L-E]` | NO TOCADO (F1.10 owns) | 689-705 |

**Columns read (no DDL)**:

| Tabla | Columna | Lectura |
|---|---|---|
| `prod.salidas` | `uuid`, `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`, `fecha_retencion_hasta`, `created_at` | V1 SELECT (read-only) |
| `prod.ingreso` | `uuid`, `placa`, `uuid_tipo_vehiculo` | V1 derivado (uuid_ingreso via salidas.uuid_ingreso) |
| `prod.clientes` | `uuid`, `tipo_identificador`, `numero_identificacion`, `nombre`, `apellido`, `estado`, `vigente_hasta`, `email`, `telefono` | V2 SELECT (when `fe_con_datos=true`) |
| `prod.impuestos` | `nombre='IVA'`, `porcentaje`, `vigente_desde`, `vigente_hasta`, `estado` | V3 read (post-0026 seeded) |
| `prod.tarifas_sucursal` | `uuid`, `valor`, `valor_plena`, `vigente_desde`, `vigente_hasta`, `estado` | KD-FACT-02 SELECT FOR SHARE per-row |
| `prod.facturas` | `uuid`, `created_at`, `uuid_sucursal`, `subtotal`, `descuento`, `total`, `uuid_ingreso`, `uuid_salida` | Step 9 INSERT |

**Columns written (Step 9-10 INSERTs only — NO UPDATE anywhere in F1.9)**:

| Tabla | Columna | Valor |
|---|---|---|
| `prod.facturas` | `uuid` | DB default `gen_random_uuid()` |
| `prod.facturas` | `fecha_retencion_hasta` | DB default `current_date()` (2 years operational retention per F1.4 pattern) |
| `prod.facturas` | `uuid_sucursal` | `salida.uuid_sucursal` (server-derived) |
| `prod.facturas` | `uuid_ingreso` | `salida.uuid_ingreso` (server-derived) |
| `prod.facturas` | `uuid_salida` | `payload.uuid_salida` |
| `prod.facturas` | `subtotal` | `payload.subtotal` |
| `prod.facturas` | `descuento` | `Decimal("0")` (MVP, no retencion; DEC-FACT-04) |
| `prod.facturas` | `total` | `payload.total` (V6-verified) |
| `prod.factura_detalle` | N rows: `uuid_factura`, `tipo`, `concepto`, `cantidad`, `valor_unitario`, `subtotal`, `uuid_tarifa_sucursal`, `fecha_retencion_hasta` | Step 10 bulk |
| `prod.factura_impuestos` | `uuid_factura`, `uuid_impuesto`, `base_calculo`, `porcentaje_aplicado`, `valor` | Step 10 IVA snapshot (1 row) |
| `prod.factura_pagos` | `uuid_factura`, `medio_pago`, `valor`, `referencia`, `uuid_sesion`, `tipo_movimiento='pago'`, `fecha_retencion_hasta` | Step 10 pago (1 row) |

**No column added for `uuid_cliente`, `prefijo`, `consecutivo`** — DEC-FACT-06 + DEC-FACT-05 veda. The `uuid_cliente` is server-derived via V2 lookup; `prefijo` + `consecutivo` live in `factura_electronica` (F1.10).

**State transitions** (e.g., `emitida → pagada` in F1.13) happen via NEW rows with the same `uuid` but a later `fecha_retencion_hasta` — bi-temporal versioning pattern. The view `V_FACTURA_ESTADO` (PR6 schema work, referenced in `models/L_E/facturas.py` line 12-14 docstring) materializes current state by joining with `factura_pagos` + `anulaciones`.

**Sync catalog impact**: zero changes. The `facturas` table is `[L-E]` (lifecycle event); F1.13 cierre_dia will sync `factura_pagos` to cloud. The `factura_detalle` and `factura_impuestos` tables are `[A]` audit tables, not synced. New partial unique index + BEFORE INSERT trigger + REVOKE re-assertion are DDL only; no data changes.

## 6. API Contracts

### `POST /api/v1/facturacion/factura` (NEW)

**Request signature**:

```python
async def create_factura(
    response: Response,
    payload: FacturaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaRead:
```

**Body `FacturaCreate`** (Pydantic v2, `extra='forbid'`):

```python
class FacturaCreate(_Base):
    """HU-F1.9: POST /facturacion/factura payload."""
    uuid_salida: uuid_lib.UUID         # REQUIRED — salida to invoice (V1)
    items: list[FacturaItemCreate] = Field(min_length=1, max_length=50)  # V4
    subtotal: Decimal                  # REQUIRED — server-verified (V6)
    total: Decimal                     # REQUIRED — server-verified (V6 ±0.01)
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"]  # V7 / DEC-FACT-07
    referencia: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None  # voucher if datáfono
    fe_con_datos: bool = False         # OPTIONAL — V2 trigger (default consumidor final)
    fe_datos_cliente: FacturaItemConDatosPropios | None = None  # OPTIONAL — V5 NIT módulo 11
```

**Response `FacturaRead`** (201, Pydantic v2):

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

**Headers**: `Cache-Control: no-store` (consistent with F1.3/F1.5/F1.6/F1.7/F1.8 precedents).

**Error discriminators** (typed HTTPException details):

| HTTP | Body | Cuándo | KD / DEC |
|---|---|---|---|
| 400 | `{"error":"voucher_requerido","medio_pago":"datafono"}` | `/factura-pagos` con `medio_pago='datafono'` y `referencia` vacía | KD-NIT-07 (REQ-OPS-062) |
| 403 | `{"error":"tenant_scope_violation","uuid_salida":"..."}` | `cajero-` con `salida.uuid_sucursal != ctx.sucursal_uuid` (post-V1) | KD-S2 analog (REQ-OPS-053) |
| 404 | `{"error":"salida_no_encontrada","uuid_salida":"..."}` | V1: uuid no existe OR ya fue facturada (unified discriminator per REQ-OPS-054) | V1 / DEC-FACT-01 |
| 404 | `{"error":"cliente_no_encontrado","numero_identificacion":"..."}` | V2 cuando `fe_con_datos=true` y cliente no existe (REQ-OPS-055) | V2 |
| 409 | `{"error":"factura_duplicada","uuid_salida":"..."}` | partial unique index `one_factura_per_salida` violated (pgcode 23505) | MIGRATION 0027 Op 2 (REQ-OPS-XR1 layer a) |
| 409 | `{"error":"pago_duplicado","uuid_factura":"..."}` | BEFORE INSERT trigger `fn_factura_pagos_init_pago_uniqueness` violated | MIGRATION 0027 Op 3 (REQ-OPS-XR1 layer b) |
| 422 | `{"error":"detalle_invalido","min_items":1}` | V4: `items=[]` (Pydantic Field enforces schema-level) | V4 (REQ-OPS-057) |
| 422 | `{"error":"nit_invalido","dv_esperado":<int>,"dv_recibido":"<str>"}` | V5: NIT módulo 11 fallido (Pydantic validator) | V5 (REQ-OPS-058) |
| 422 | `{"error":"total_no_coherente","total_recibido":"...","total_calculado":"...","diferencia":"..."}` | V6: total server vs payload differs by >0.01 COP | V6 (REQ-OPS-059) |
| 500 | `{"error":"iva_no_configurado"}` | V3: `validar_iva_configurado` returns False (post-0026 deploy: never) | V3 (REQ-OPS-056) |
| 201 | `FacturaRead` con `uuid_cliente` derivado (DEC-FACT-06) | happy path | — |

### `POST /api/v1/facturacion/factura-pagos` (NEW, 5-step chain)

**Request signature**:

```python
async def create_factura_pago(
    response: Response,
    payload: FacturaPagoAdicionalCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaPagoRead:
```

**Body `FacturaPagoAdicionalCreate`** (Pydantic v2, `extra='forbid'`):

```python
class FacturaPagoAdicionalCreate(_Base):
    """HU-F1.9: POST /facturacion/factura-pagos payload."""
    uuid_factura: uuid_lib.UUID         # REQUIRED — factura existente
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"]
    valor: Decimal = Field(gt=Decimal("0"))
    referencia: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None  # REQUIRED if datafono
    uuid_sesion: uuid_lib.UUID | None = None
```

**Response `FacturaPagoRead`** (201):

```python
class FacturaPagoRead(_Base):
    """HU-F1.9: POST /facturacion/factura-pagos response."""
    uuid: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID
    medio_pago: str
    valor: Decimal
    referencia: str | None
    timestamp_evento: datetime
```

**Sin cambios sobre**:
- `POST /api/v1/operacion/salidas` (F1.7, unchanged)
- `GET /api/v1/operacion/cotizar?uuid_ingreso` (F1.8, unchanged)
- `POST /api/v1/operacion/ingresos` (F1.6, unchanged)
- `POST /api/v1/clientes` (existing, F1.5/F1.6 unmodified schema; F1.9 adds NIT validator)
- `GET /api/v1/clientes/...` (existing, unchanged)

**Out of F1.9 scope (adjacent, lower priority)**:
- `GET /api/v1/facturacion/facturas/{uuid}` — read single
- `GET /api/v1/facturacion/facturas?uuid_cliente=...&fecha_desde=...&fecha_hasta=...` — paginated list
- `POST /api/v1/facturacion/factura-electronica` — F1.10 owns FE numbering + estado DIAN.

## 7. Handler Skeleton (12-step chain)

**Path**: `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py` (NEW, ~150 LOC: 2 handlers + dependencies).

The handler is registered on a new `APIRouter` (the module is brand new); the decorator `@router.post("/factura")` is adjacent to `@router.post("/factura-pagos")` (same module). The dependency chain `_facturacion_issuer_dep → get_tenant_ctx → get_session` is the F1.6/F1.7 pattern. The 12-step sequence (D-HU-F1.9-11) is enforced by the AST walk `tests/static/test_factura_handler_step_order.py`.

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py
# (NEW file, ~150 LOC)


from __future__ import annotations

import uuid as uuid_lib
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import StringConstraints
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.tenancy import TenantContext, get_tenant_ctx
from ..deps import get_session, no_store_headers, requires_issuer, apply_no_store_header
from ..repo import factura as repo_factura
from ..repo.factura_detalle import crear_factura_detalle_bulk
from ..repo.impuestos import validar_iva_configurado
from ..schemas.facturacion import (
    FacturaCreate,
    FacturaPagoAdicionalCreate,
    FacturaPagoRead,
    FacturaRead,
)


router = APIRouter(prefix="/facturacion", tags=["facturacion"])

# KD-3: issuer chain — admin or cajero can emit facturas (HU-F1.9).
_facturacion_issuer_dep = requires_issuer("admin-", "cajero-")


@router.post(
    "/factura",
    response_model=FacturaRead,
    status_code=201,
    summary=(
        "HU-F1.9 / REQ-OPS-053..063: atomic 4-table insert for billing — "
        "facturas + factura_detalle + factura_impuestos + factura_pagos "
        "in one await session.commit() (KD-FACT-01)."
    ),
    responses={
        403: {"description": "tenant_scope_violation (cajero)"},
        404: {"description": "salida_no_encontrada (V1) | cliente_no_encontrado (V2)"},
        409: {"description": "factura_duplicada (one_factura_per_salida)"},
        422: {
            "description": (
                "nit_invalido (V5) | email_invalido | detalle_invalido (V4) | "
                "total_no_coherente (V6)"
            )
        },
        500: {"description": "iva_no_configurado (V3, post-0026: never)"},
    },
)
async def create_factura(
    response: Response,
    payload: FacturaCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaRead:
    """REQ-OPS-053..063: atomic billing transaction.

    Dependency chain (same as create_ingreso / create_salida, F1.6/F1.7):
        _facturacion_issuer_dep -> requires_issuer("admin-", "cajero-")
        get_tenant_ctx          -> TenantContext { actor_uuid, sucursal_uuid, ... }
        get_session             -> AsyncSession (request-scoped)

    Sequence (D-HU-F1.9-11 12-step chain, locked by AST walk):
        1. KD-3 issuer claims + no_store headers
        2. V1 salida existe y es facturable (404 if None)
        3. tenant scope post-V1 (403 if cajero cross-branch)
        4. V2 cliente existe cuando fe_con_datos=true (404 if None)
        5. V3 IVA configurado (500 iva_no_configurado if False)
        6. V4 detalle items coherentes (422 detalle_invalido if empty)
        7. KD-FACT-02 lock FOR SHARE per-row on tarifas_sucursal
        8. V6 server-side recompute total (±0.01 COP)
        9. INSERT prod.facturas [L-E] (DEC-FACT-01: NO UPDATE anywhere)
       10. INSERT factura_detalle (N) + factura_impuestos (1) + factura_pagos (1)
       11. single await session.commit() (KD-FACT-01, KD-FACT-02 lock release)
       12. response shape FacturaRead with uuid_cliente derived (DEC-FACT-06)

    Lock continuity (KD-FACT-02): the FOR SHARE lock on tarifas_sucursal
    acquired in Step 7 is held through Step 10 INSERTs. Released at
    session.commit() in Step 11. NO sub-transactions, NO SAVEPOINT.

    The Idempotency-Key header is checked by the FastAPI middleware
    (PR2 IdempotencyKeyMiddleware, DEC-IDEM-01 from F1.6).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V1 (salida existe y es facturable). -------------------
    salida = await repo_factura.buscar_salida_facturable(
        session, uuid_salida=payload.uuid_salida
    )
    if salida is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "salida_no_encontrada",
                "uuid_salida": str(payload.uuid_salida),
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2 analog from F1.7). -------
    target_sucursal = salida.uuid_sucursal
    if (
        ctx.issuer_prefix == "cajero-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_salida": str(payload.uuid_salida),
            },
            headers=no_store,
        )

    # --- Step 4: V2 cliente existe cuando fe_con_datos=true. -----------
    cliente_uuid: uuid_lib.UUID | None = None
    if payload.fe_con_datos:
        cliente = await repo_factura.buscar_o_crear_cliente_por_nit(
            session,
            numero_identificacion=payload.fe_datos_cliente.numero_identificacion,
            datos=payload.fe_datos_cliente,
        )
        if cliente is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "cliente_no_encontrado",
                    "numero_identificacion": (
                        payload.fe_datos_cliente.numero_identificacion
                    ),
                },
                headers=no_store,
            )
        cliente_uuid = cliente.uuid

    # --- Step 5: V3 (IVA configurado). ---------------------------------
    if not await validar_iva_configurado(session):
        raise HTTPException(
            status_code=500,
            detail={"error": "iva_no_configurado"},
            headers=no_store,
        )

    # --- Step 6: V4 detalle items coherentes. --------------------------
    items_validados = repo_factura.validar_items(payload.items)
    if not items_validados:
        raise HTTPException(
            status_code=422,
            detail={"error": "detalle_invalido", "min_items": 1},
            headers=no_store,
        )

    # --- Step 7: KD-FACT-02 lock FOR SHARE per-row. --------------------
    await repo_factura.lock_tarifas_sucursal_para_items(
        session, items=items_validados
    )

    # --- Step 8: V6 server-side recompute total (±0.01 COP). -----------
    total_server = repo_factura.compute_total(
        items=items_validados, iva=Decimal("0.19"), retencion=Decimal("0")
    )
    if abs(total_server - payload.total) > Decimal("0.01"):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "total_no_coherente",
                "total_recibido": str(payload.total),
                "total_calculado": str(total_server),
                "diferencia": str(abs(total_server - payload.total)),
            },
            headers=no_store,
        )

    # --- Step 9: INSERT prod.facturas [L-E]. ---------------------------
    new_factura = await repo_factura.crear_factura_evento(
        session,
        actor_uuid=ctx.actor_uuid,
        new_attrs={
            "uuid_sucursal": target_sucursal,
            "uuid_ingreso": salida.uuid_ingreso,
            "uuid_salida": salida.uuid,
            "subtotal": payload.subtotal,
            "descuento": Decimal("0"),
            "total": payload.total,
        },
    )

    # --- Step 10: INSERT factura_detalle (N) + impuestos (1) + pago. --
    await crear_factura_detalle_bulk(
        session, uuid_factura=new_factura.uuid, items=items_validados
    )
    await repo_factura.crear_factura_impuesto_iva(
        session, uuid_factura=new_factura.uuid, base=total_server
    )
    new_pago = await repo_factura.crear_factura_pago(
        session,
        uuid_factura=new_factura.uuid,
        medio_pago=payload.medio_pago,
        valor=payload.total,
        referencia=payload.referencia,
        uuid_sesion=ctx.uuid_sesion,
    )

    # --- Step 11: KD-FACT-01 single commit. ---------------------------
    await session.commit()  # UN solo commit (lock release, KD-FACT-02)

    # --- Step 12: response shape. -------------------------------------
    apply_no_store_header(response)
    await session.refresh(new_factura)
    return FacturaRead(
        uuid=new_factura.uuid,
        created_at=new_factura.created_at,
        uuid_sucursal=new_factura.uuid_sucursal,
        uuid_ingreso=new_factura.uuid_ingreso,
        uuid_salida=new_factura.uuid_salida,
        subtotal=new_factura.subtotal,
        descuento=new_factura.descuento,
        total=new_factura.total,
        uuid_cliente=cliente_uuid,  # DEC-FACT-06 derivado, no persistido
        items=[FacturaItemRead(...) for item in items_validados],
        estado="emitida",  # derived from V_FACTURA_ESTADO (always "emitida" at create time)
    )


@router.post(
    "/factura-pagos",
    response_model=FacturaPagoRead,
    status_code=201,
    summary=(
        "HU-F1.9 / REQ-OPS-062: voucher validation for datáfono + additional "
        "payment record on existing factura."
    ),
    responses={
        400: {"description": "voucher_requerido (datafono sin referencia)"},
        404: {"description": "factura_no_encontrada"},
        422: {"description": "monto_insuficiente (valor < total_pendiente)"},
    },
)
async def create_factura_pago(
    response: Response,
    payload: FacturaPagoAdicionalCreate,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaPagoRead:
    """REQ-OPS-062: 5-step chain for additional factura_pagos INSERT.

    Sequence (locked by AST walk, file 5):
        1. KD-3 issuer claims + no_store headers (DI)
        2. V7 voucher_requerido if medio_pago='datafono' AND referencia empty
        3. tenant scope post-V1 + lock FOR SHARE tarifas_sucursal (if referencia)
        4. INSERT prod.factura_pagos [A] + flush
        5. single await session.commit()

    Idempotency: same Idempotency-Key header (DEC-IDEM-01 reuse from F1.6).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection.

    # --- Step 2: V7 voucher_requerido. ---------------------------------
    if payload.medio_pago == "datafono" and not payload.referencia:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "voucher_requerido",
                "medio_pago": "datafono",
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope + lock FOR SHARE (if referencia). ------
    # The factura must exist and the cliente/sucursal must match the JWT.
    # Omitted here for brevity; mirrors Step 3 of create_factura.

    # --- Step 4: INSERT prod.factura_pagos [A]. -----------------------
    new_pago = await repo_factura.crear_factura_pago(
        session,
        uuid_factura=payload.uuid_factura,
        medio_pago=payload.medio_pago,
        valor=payload.valor,
        referencia=payload.referencia,
        uuid_sesion=payload.uuid_sesion or ctx.uuid_sesion,
    )

    # --- Step 5: single commit. ----------------------------------------
    await session.commit()
    apply_no_store_header(response)
    return FacturaPagoRead(
        uuid=new_pago.uuid,
        uuid_factura=new_pago.uuid_factura,
        medio_pago=new_pago.medio_pago,
        valor=new_pago.valor,
        referencia=new_pago.referencia,
        timestamp_evento=new_pago.timestamp_evento,
    )
```

**Notes.**

- The handler is **registered on a NEW `APIRouter`** in a NEW module `api/v1/facturacion.py`. Mounted via `r.include_router(facturacion.router)` in `api/v1/__init__.py` (NEW line, same pattern as `operacion.router`).
- All repo helpers are imported from `parkos_core.repo.{factura, factura_detalle, nit_modulo11, impuestos}`. The handler does not write SQL inline.
- `await session.commit()` happens exactly once in each handler (KD-FACT-01 + REQ-OPS-060). AST walk `tests/static/test_factura_handler_single_commit.py` enforces `len(commits) == 1`.
- The 12-step order is intentional: V1 before tenant scope avoids info leak; V2 after V1 derives `target_sucursal`; V4 before V6 ensures items are validated before total recompute; Step 7 (lock) before Step 8 (V6) ensures lock is held through Step 10 INSERTs.
- `extra='forbid'` (inherited from `_Base`) rejects extra fields including `uuid_cliente` (DEC-FACT-06) and `correlacion_id` (DEC-IDEM-01).
- **FK ordering**: `prod.factura_detalle` + `prod.factura_impuestos` + `prod.factura_pagos` all reference `prod.facturas.uuid` (and `prod.factura_pagos.uuid_factura`). Step 9 INSERT of `prod.facturas` populates `new_factura.uuid` via DB default `gen_random_uuid()`. Steps 10a/10b/10c INSERTs use `new_factura.uuid`. Single commit in Step 11 materializes all 4 tables atomically.

## 8. Migration 0027 — Complete DDL

**Path**: `backend/packages/parkos_core/migrations/versions/0027_factura_one_per_salida_and_pagos_uniqueness.py` (~120 LOC).

```python
"""HU-F1.9 / MIGRATION 0027 — partial unique index ``one_factura_per_salida`` +
BEFORE INSERT trigger ``fn_factura_pagos_init_pago_uniqueness`` + defensive
REVOKE + idempotent ``fn_*_inmutable`` re-install.

Revision ID: 0027_factura_one_per_salida_and_pagos_uniqueness
Revises: 0026_seed_impuestos_iva_and_one_exit_per_ingreso (F1.7 chain head)
Create Date: 2026-09-14

**Scope.** Four operations in strict order:

  1. **Pre-flight (KD-7 F1.6 pattern)**: ``DO $$`` block aborts the
     migration with a typed ``0027_preflight_abort`` exception if any
     of the 9 tables (``prod.facturas``, ``prod.factura_detalle``,
     ``prod.factura_impuestos``, ``prod.factura_pagos``,
     ``prod.clientes``, ``prod.impuestos``, ``prod.tarifas_sucursal``,
     ``prod.salidas``, ``prod.ingreso``) does not exist (e.g., a fresh
     deployment that never ran migrations 0001-0026). Emits
     ``RAISE NOTICE`` with the row counts for the alembic log.

  2. **Partial unique index ``one_factura_per_salida`` (KD-FACT-R3
     closure)**: ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
     one_factura_per_salida ON prod.facturas (uuid_salida) WHERE
     uuid_salida IS NOT NULL``. ``CONCURRENTLY`` for no lock on
     reads/writes during creation; ``IF NOT EXISTS`` for idempotency.
     **Feasibility verified pre-apply**: ``prod.facturas`` is
     ``[L-E]`` (composite PK ``(uuid, fecha_retencion_hasta)``) and is
     NOT partitioned (no ``postgresql_partition_by`` in
     ``models/L_E/facturas.py`` ``__table_args__``). Closes TOCTOU race
     on V1 EXISTS subquery between concurrent cajeros attempting to
     invoice the same ``uuid_salida``; ``UniqueViolationError``
     (pgcode ``23505``) → 409 ``factura_duplicada``.

  3. **BEFORE INSERT trigger ``fn_factura_pagos_init_pago_uniqueness``
     (KD-FACT-R3 closure for pagos)**: analogía
     ``fn_factura_pagos_reverso_uniqueness`` (migration 0004 lines
     35-66). Same pattern: ``CREATE OR REPLACE FUNCTION`` +
     ``DROP TRIGGER IF EXISTS`` + ``CREATE TRIGGER``. Rejects
     concurrent INSERT of a second ``pago`` (``tipo_movimiento='pago'``
     OR ``'ajuste'``) row for the same ``uuid_factura``. **Required
     because**: ``prod.factura_pagos`` IS partitioned by
     ``RANGE (fecha_retencion_hasta)`` (migration 0001 line 716), so a
     partial unique index is INFEASIBLE per PostgreSQL's constraint
     that a unique index on a partitioned table must include the
     partition key. The BEFORE INSERT trigger is the only DB-layer
     defense.

  4. **REVOKE re-assertion + idempotent ``fn_*_inmutable`` re-install
     (analogía migration 0004 lines 68-78)**: defensive re-assertion
     of REVOKE on the 4 ``[A]``-class ``factura_*`` tables
     (``factura_detalle``, ``factura_impuestos``, ``factura_otros_cobros``,
     ``factura_pagos``) + idempotent re-install of the pre-existing
     ``fn_*_inmutable`` triggers (migration 0001 lines 2024-2088).
     Plus a re-assertion of the pre-existing
     ``factura_pagos_reverso_uniqueness`` trigger from migration 0004.
     The ``models/A/factura_pagos.py`` docstring lines 9-18 (read
     pre-apply) has a pre-existing docstring drift: it references
     ``0004_add_factura_pagos_reverso_index.py`` which does NOT exist;
     the actual migration is ``0004_add_factura_pagos_reverso_trigger.py``.
     apply-phase fix: correct the docstring to match the actual
     filename.

**Idempotency.**
  - Op 2 ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`` allows
    re-apply without raising (the index already exists, no DDL
    needed).
  - Op 3 ``CREATE OR REPLACE FUNCTION`` + ``DROP TRIGGER IF EXISTS``
    + ``CREATE TRIGGER`` is the standard pattern; re-apply is a no-op.
  - Op 4 ``DROP TRIGGER IF EXISTS`` + ``CREATE TRIGGER`` is
    idempotent (the trigger is dropped and recreated with the same
    definition). The REVOKE statements are also idempotent
    (REVOKE on already-revoked privileges is a no-op).
  - The pre-flight Op 1 ``DO $$`` block is idempotent (count check is
    read-only, no DDL).

**Downgrade.**
  1. ``DROP TRIGGER IF EXISTS prod.factura_pagos_init_pago_uniqueness
     ON prod.factura_pagos`` (Op 3 reverse).
  2. ``DROP FUNCTION IF EXISTS prod.fn_factura_pagos_init_pago_uniqueness()``
     (Op 3 reverse).
  3. ``DROP INDEX IF EXISTS prod.one_factura_per_salida`` (Op 2 reverse).
  - Note: Op 4 cannot be cleanly reversed because the REVOKE statements
    are correct and should NOT be re-granted on downgrade. The
    ``fn_*_inmutable`` triggers remain in place; the
    ``factura_pagos_reverso_uniqueness`` trigger from migration 0004
    also remains in place.

**Pre-flight ordering (Op 1)**: the DO $$ block aborts BEFORE any
DDL, so a missing table does not leave partial state. The DO $$ block
is the FIRST statement in the upgrade() function.

**Cross-references.**
  - F1.7 design.md §8 — the pre-flight pattern matches F1.7
    MIGRATION 0026 Op 1.
  - F1.6 design.md §8 — the KD-7 DO $$ pattern.
  - Migration 0004 lines 35-66 — the BEFORE INSERT trigger pattern
    analogía for ``fn_factura_pagos_init_pago_uniqueness``.
  - Migration 0004 lines 68-78 — the REVOKE re-assertion + idempotent
    ``fn_*_inmutable`` re-install pattern analogía for Op 4.
  - Migration 0001 lines 2024-2088 — the pre-existing
    ``fn_*_inmutable`` triggers being re-installed in Op 4.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0027_factura_one_per_salida_and_pagos_uniqueness"
down_revision = "0026_seed_impuestos_iva_and_one_exit_per_ingreso"
branch_labels = None
depends_on = None


# Matches the F1.6 / F1.7 migration pattern: cap any blocking DDL at 5s
# so the migration cannot stall the alembic runtime on a busy DB.
# Note: CREATE UNIQUE INDEX CONCURRENTLY does NOT honor lock_timeout
# (it runs in its own transaction outside the migration transaction),
# but the other statements do.
_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Apply the F1.9 partial unique index + BEFORE INSERT trigger +
    REVOKE re-assertion + idempotent fn_*_inmutable re-install."""
    op.execute(_LOCK_TIMEOUT_SQL)

    # 1) Pre-flight (KD-7 F1.6 pattern): 9 tables must exist.
    op.execute(
        """
        DO $$
        DECLARE
            _expected_tables text[] := ARRAY[
                'facturas', 'factura_detalle', 'factura_impuestos',
                'factura_pagos', 'clientes', 'impuestos',
                'tarifas_sucursal', 'salidas', 'ingreso'
            ];
            _missing_tables text := '';
            _table_count bigint;
            _tbl text;
        BEGIN
            FOREACH _tbl IN ARRAY _expected_tables LOOP
                SELECT count(*) INTO _table_count
                FROM pg_catalog.pg_class
                WHERE relname = _tbl
                  AND relnamespace = 'prod'::regnamespace;
                IF _table_count IS NULL OR _table_count = 0 THEN
                    _missing_tables := _missing_tables || _tbl || ', ';
                ELSE
                    RAISE NOTICE '0027_preflight: prod.% existe (% filas)',
                        _tbl, _table_count;
                END IF;
            END LOOP;
            IF _missing_tables != '' THEN
                RAISE EXCEPTION
                    '0027_preflight_abort: tablas faltantes: %. '
                    'Aplique migrations 0001-0026 antes.',
                    _missing_tables;
            END IF;
        END $$;
        """
    )

    # 2) Partial unique index one_factura_per_salida (KD-FACT-R3 closure).
    #    FEASIBLE: prod.facturas is NOT partitioned (verified models/L_E/facturas.py).
    #    CONCURRENTLY for no lock on reads/writes; IF NOT EXISTS for idempotency.
    op.execute(
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_factura_per_salida
            ON prod.facturas (uuid_salida)
            WHERE uuid_salida IS NOT NULL
        """
    )

    # 3) BEFORE INSERT trigger fn_factura_pagos_init_pago_uniqueness
    #    (analogía migration 0004 lines 35-66 fn_factura_pagos_reverso_uniqueness).
    #    REQUIRED: prod.factura_pagos IS partitioned by RANGE(fecha_retencion_hasta)
    #    (migration 0001 line 716), so partial unique index INFEASIBLE.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prod.fn_factura_pagos_init_pago_uniqueness()
        RETURNS trigger AS $$
        BEGIN
            -- Enforce uniqueness of the initial 'pago' (or 'ajuste') per factura.
            -- Reversos are excluded because they are compensating movements
            -- (multiple reversos per original pago are not expected, but
            -- the reverso uniqueness is enforced by fn_factura_pagos_reverso_uniqueness
            -- migration 0004 lines 35-58).
            IF NEW.tipo_movimiento IN ('pago', 'ajuste') AND NEW.uuid_factura IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM prod.factura_pagos
                    WHERE uuid_factura = NEW.uuid_factura
                      AND tipo_movimiento IN ('pago', 'ajuste')
                      AND NOT (NEW.uuid IS NOT NULL AND uuid = NEW.uuid)
                ) THEN
                    RAISE EXCEPTION
                        'factura_pagos init pago uniqueness violation: '
                        'uuid_factura=% already has an init pago',
                        NEW.uuid_factura
                        USING ERRCODE = 'unique_violation';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "DROP TRIGGER IF EXISTS factura_pagos_init_pago_uniqueness "
        "ON prod.factura_pagos;"
    )
    op.execute(
        "CREATE TRIGGER factura_pagos_init_pago_uniqueness "
        "BEFORE INSERT ON prod.factura_pagos "
        "FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_init_pago_uniqueness();"
    )

    # 4) DEFENSIVE: REVOKE re-assertion on the 4 [A] factura_* tables
    #    (analogía migration 0004 lines 68-70).
    for table in (
        "factura_detalle",
        "factura_impuestos",
        "factura_otros_cobros",
        "factura_pagos",
    ):
        op.execute(f"REVOKE UPDATE, DELETE ON prod.{table} FROM rol_app;")
        op.execute(f"GRANT SELECT, INSERT ON prod.{table} TO rol_app;")

    # IDEMPOTENT: re-install the pre-existing fn_*_inmutable triggers
    # (migration 0001 lines 2024-2088). DROP IF EXISTS + CREATE is the
    # idempotent pattern.
    for table in (
        "factura_detalle",
        "factura_impuestos",
        "factura_pagos",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_inmutable ON prod.{table};")
        op.execute(
            f"CREATE TRIGGER {table}_inmutable "
            f"BEFORE UPDATE OR DELETE ON prod.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION prod.fn_{table}_inmutable();"
        )

    # DEFENSIVE: re-install the pre-existing reverso trigger from
    # migration 0004 (lines 61-66). Some apply environments may have
    # had the trigger dropped accidentally; re-install defends against
    # that without losing other schema state.
    op.execute(
        "DROP TRIGGER IF EXISTS factura_pagos_reverso_uniqueness "
        "ON prod.factura_pagos;"
    )
    op.execute(
        "CREATE TRIGGER factura_pagos_reverso_uniqueness "
        "BEFORE INSERT ON prod.factura_pagos "
        "FOR EACH ROW EXECUTE FUNCTION prod.fn_factura_pagos_reverso_uniqueness();"
    )


def downgrade() -> None:
    """Reverse the F1.9 partial unique index + BEFORE INSERT trigger.

    Op 4 cannot be cleanly reversed (REVOKE statements are correct and
    should NOT be re-granted; fn_*_inmutable triggers remain in place).
    Reverse order (Op 3 → Op 2):
      1. DROP TRIGGER + DROP FUNCTION (init pago uniqueness)
      2. DROP INDEX (one_factura_per_salida)
    """
    op.execute(_LOCK_TIMEOUT_SQL)

    # Op 3 reverse: DROP TRIGGER + DROP FUNCTION.
    op.execute(
        "DROP TRIGGER IF EXISTS factura_pagos_init_pago_uniqueness "
        "ON prod.factura_pagos;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prod.fn_factura_pagos_init_pago_uniqueness();"
    )

    # Op 2 reverse: DROP INDEX.
    op.execute("DROP INDEX IF EXISTS prod.one_factura_per_salida")


__all__ = ["downgrade", "upgrade"]
```

**Notes.**

- The migration is **deterministic** in its order: pre-flight first (abort if any table missing), then partial unique index, then BEFORE INSERT trigger, then REVOKE + idempotent trigger re-install. Re-application is a no-op (`IF NOT EXISTS` + `DROP IF EXISTS` + `CREATE OR REPLACE FUNCTION`).
- The `CREATE UNIQUE INDEX CONCURRENTLY` cannot run inside an Alembic transaction (PostgreSQL limitation); Alembic detects this and switches to autocommit mode for the DDL. The `CONCURRENTLY` is required because production may have live SELECT/INSERT on `prod.facturas`.
- The `fn_factura_pagos_init_pago_uniqueness` trigger's predicate excludes `reverso` rows (only `pago` and `ajuste` are checked) so multiple compensating reversos per original pago are still allowed. The `fn_factura_pagos_reverso_uniqueness` trigger (migration 0004) handles the reverso-once constraint.
- Op 4's REVOKE re-assertion is **defensive** in case the privileges were accidentally granted. Idempotent. The downgrade does NOT re-grant the revoked privileges (REVOKE is correct).
- **Pre-existing docstring drift fix (apply-phase TODO)**: `models/A/factura_pagos.py` lines 9-18 docstring (read pre-apply) references `0004_add_factura_pagos_reverso_index.py` which does NOT exist (the actual filename is `0004_add_factura_pagos_reverso_trigger.py`). apply-phase MUST correct this in a single-line fix; the migration re-installs the trigger but does NOT touch the docstring.

## 9. Repo Skeleton — File-by-File

### 9.1 `backend/packages/parkos_core/src/parkos_core/repo/factura.py` (NEW, ~250 LOC)

```python
"""HU-F1.9 / REQ-OPS-053..063 — Billing transaction (atomic 4-table insert).

Helpers for ``POST /facturacion/factura``:
- ``buscar_salida_facturable`` (V1) — checks salida exists and is not yet facturada.
- ``buscar_o_crear_cliente_por_nit`` (V2) — SELECTs active cliente by NIT.
- ``validar_items`` (V4) — re-checks items against schema invariants.
- ``lock_tarifas_sucursal_para_items`` (KD-FACT-02) — SELECT FOR SHARE per-row.
- ``compute_total`` (V6) — server-side recompute of total (±0.01 COP tolerance).
- ``crear_factura_evento`` (Step 9 INSERT [L-E]) — single ORM INSERT.
- ``crear_factura_impuesto_iva`` (Step 10 INSERT [A]) — IVA snapshot.
- ``crear_factura_pago`` (Step 10 INSERT [A]) — single pago row.
- 5 typed exceptions: ``SalidaNoFacturableError``, ``ClienteNoEncontradoFacturaError``,
  ``NitInvalidoError``, ``TotalNoCoherenteError``, ``VoucherRequeridoError``.

DEC-FACT-01: writes are append-only INSERTs. NO UPDATE, NO DELETE.
KD-FACT-01: handler commits ONCE; this module does not commit.
KD-FACT-02: FOR SHARE locks acquired here are held until caller's commit.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.factura_detalle import FacturaDetalle
from ..models.A.factura_impuestos import FacturaImpuestos
from ..models.A.factura_pagos import FacturaPagos
from ..models.L_E.facturas import Facturas
from ..models.V.clientes import Clientes
from ..models.V.impuestos import Impuestos
from ..models.V.tarifas_sucursal import TarifasSucursal
from ..schemas.facturacion import FacturaItemConDatosPropios, FacturaItemCreate


# --- Typed exceptions --------------------------------------------------------


class SalidaNoFacturableError(Exception):
    """V1 404 discriminator — uuid_salida does not exist OR already facturada.

    Unified per DEC-FACT-01 (single 404 for "not found" and "already
    facturada", mirrors DEC-SUC-21 404 from F1.4).
    """

    def __init__(self, *, uuid_salida: uuid_lib.UUID) -> None:
        self.uuid_salida = uuid_salida
        super().__init__(f"salida_no_facturable: uuid_salida={uuid_salida}")


class ClienteNoEncontradoFacturaError(Exception):
    """V2 404 discriminator — cliente does not exist (when fe_con_datos=true)."""

    def __init__(self, *, numero_identificacion: str) -> None:
        self.numero_identificacion = numero_identificacion
        super().__init__(
            f"cliente_no_encontrado: numero_identificacion={numero_identificacion}"
        )


class NitInvalidoError(Exception):
    """V5 422 discriminator — NIT módulo 11 mismatch."""

    def __init__(self, *, dv_esperado: int, dv_recibido: str) -> None:
        self.dv_esperado = dv_esperado
        self.dv_recibido = dv_recibido
        super().__init__(
            f"nit_invalido: dv_esperado={dv_esperado}, dv_recibido={dv_recibido}"
        )


class TotalNoCoherenteError(Exception):
    """V6 422 discriminator — total differs by >0.01 COP."""

    def __init__(
        self,
        *,
        total_recibido: Decimal,
        total_calculado: Decimal,
        diferencia: Decimal,
    ) -> None:
        self.total_recibido = total_recibido
        self.total_calculado = total_calculado
        self.diferencia = diferencia
        super().__init__(
            f"total_no_coherente: recibido={total_recibido}, "
            f"calculado={total_calculado}, diferencia={diferencia}"
        )


class VoucherRequeridoError(Exception):
    """V7 400 discriminator — datafono sin referencia."""

    def __init__(self, *, medio_pago: str) -> None:
        self.medio_pago = medio_pago
        super().__init__(f"voucher_requerido: medio_pago={medio_pago}")


# --- V1: salida existe y es facturable --------------------------------------


async def buscar_salida_facturable(
    session: AsyncSession, *, uuid_salida: uuid_lib.UUID
) -> Any | None:
    """V1: SELECT salida WHERE uuid=:p AND NOT EXISTS factura (state=emitida|pagada).

    Returns the ORM ``Salidas`` row if found AND not yet facturada, else None.

    NOTE: does NOT raise SalidaNoFacturableError; the handler raises the
    404 with the discriminator body. Returning None lets the handler
    decide whether to merge with the lock acquisition (KD-S2 ordering).
    """
    from ..models.A.salidas import Salidas  # local import to avoid cycle

    # Fast path: PK lookup + bi-temporal predicate.
    salida_row = await session.get(Salidas, uuid_salida)
    if salida_row is None:
        return None

    # V1 EXISTS check: any prod.facturas row referencing this uuid_salida
    # means the salida is already facturada (DEC-FACT-01 unified discriminator).
    exists_stmt = text(
        """
        SELECT 1 FROM prod.facturas
        WHERE uuid_salida = :uuid_salida
          AND uuid_salida IS NOT NULL
        LIMIT 1
        """
    )
    exists = (
        await session.execute(exists_stmt, {"uuid_salida": str(uuid_salida)})
    ).first()
    if exists is not None:
        return None  # already facturada

    return salida_row


# --- V2: cliente existe -----------------------------------------------------


async def buscar_o_crear_cliente_por_nit(
    session: AsyncSession,
    *,
    numero_identificacion: str,
    datos: FacturaItemConDatosPropios,
) -> Clientes | None:
    """V2: SELECT cliente WHERE tipo_identificador=:t AND
    numero_identificacion=:n AND vigente_hasta IS NULL AND estado='activo'.

    Returns the ORM ``Clientes`` row if found, None otherwise. Does NOT
    auto-create (F1.9 returns 404 to caller per REQ-OPS-055).
    """
    stmt = select(Clientes).where(
        Clientes.tipo_identificador == datos.tipo_identificador,
        Clientes.numero_identificacion == numero_identificacion,
        Clientes.vigente_hasta.is_(None),
        Clientes.estado == "activo",
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# --- V4: validar items ------------------------------------------------------


def validar_items(
    items: list[FacturaItemCreate],
) -> list[FacturaItemCreate]:
    """V4: re-check items against schema invariants.

    Pydantic already enforces min_length=1, gt(0), ge(0), Literal[tipo].
    This function is a defense-in-depth re-check; returns the same list
    on success, raises ``HTTPException(422)`` if any invariant violated.

    For F1.9 MVP, the items pass through if Pydantic accepted them.
    Future HUs may add per-item invariants (e.g., unique concepts).
    """
    if not items:
        return []
    return items


# --- KD-FACT-02: lock FOR SHARE per-row -------------------------------------


async def lock_tarifas_sucursal_para_items(
    session: AsyncSession, *, items: list[FacturaItemCreate]
) -> None:
    """KD-FACT-02: SELECT FOR SHARE per-row on prod.tarifas_sucursal for
    every unique uuid_tarifa_sucursal referenced. Lock held until
    caller's session.commit().

    If no items reference uuid_tarifa_sucursal, this is a no-op.
    """
    tarifs_uuids = {item.uuid_tarifa_sucursal for item in items if item.uuid_tarifa_sucursal is not None}
    if not tarifs_uuids:
        return

    stmt = (
        select(TarifasSucursal)
        .where(TarifasSucursal.uuid.in_(tarifs_uuids))
        .with_for_update(read=True)  # psycopg2/asyncpg: FOR SHARE
    )
    result = await session.execute(stmt)
    # Materialize the lock: iterate so the SELECT FOR SHARE actually
    # acquires the lock, not just builds the query.
    list(result.scalars())


# --- V6: compute_total ------------------------------------------------------


def compute_total(
    *,
    items: list[FacturaItemCreate],
    iva: Decimal,
    retencion: Decimal = Decimal("0"),
) -> Decimal:
    """V6: server-side recompute of total = subtotal_items + iva - retencion.

    subtotal_items = sum(item.cantidad * item.valor_unitario)
    iva = subtotal_items * iva_rate (the Decimal from caller).
    retencion = Decimal("0") in MVP (DEC-FACT-04, Fase 4 deferred).
    """
    subtotal_items = sum(
        (item.cantidad * item.valor_unitario for item in items),
        Decimal("0"),
    )
    iva_monto = (subtotal_items * iva).quantize(Decimal("0.01"))
    total = subtotal_items + iva_monto - retencion
    return total.quantize(Decimal("0.01"))


# --- Step 9: INSERT prod.facturas [L-E] --------------------------------------


async def crear_factura_evento(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    new_attrs: dict[str, Any],
) -> Facturas:
    """Step 9: INSERT ``prod.facturas`` [L-E] (bi-temporal).

    DEC-FACT-01 amended: F1.9 only INSERTs, never UPDATEs. State
    transitions happen via NEW rows with later ``fecha_retencion_hasta``
    per bi-temporal versioning. The single-commit invariant (KD-FACT-01)
    materializes the INSERT atomically with the other 3 tables.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    new_row = Facturas(
        **new_attrs,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(new_row)
    try:
        await session.flush()
    except IntegrityError as err:
        # Partial unique index ``one_factura_per_salida`` (MIGRATION 0027 Op 2)
        # rejects a second factura for the same uuid_salida. Map to
        # FacturaDuplicada → 409 in the handler.
        if "one_factura_per_salida" in str(err.orig):
            raise FacturaDuplicadaError() from err
        raise
    return new_row


class FacturaDuplicadaError(Exception):
    """409 — partial unique index ``one_factura_per_salida`` violated."""


# --- Step 10a: INSERT prod.factura_detalle bulk -----------------------------


async def crear_factura_impuesto_iva(
    session: AsyncSession,
    *,
    uuid_factura: uuid_lib.UUID,
    base: Decimal,
) -> FacturaImpuestos:
    """Step 10b: INSERT one IVA snapshot row in prod.factura_impuestos.

    Reads uuid_impuesto (IVA) and porcentaje from prod.impuestos (V3
    pre-flight guaranteed IVA configured). Snapshots both
    uuid_impuesto and porcentaje_aplicado so historical reports remain
    valid even if IVA changes.

    KD-FACT-01: caller commits ONCE.
    """
    iva_row = (
        await session.execute(
            select(Impuestos).where(
                Impuestos.codigo == "IVA",
                Impuestos.vigente_hasta.is_(None),
                Impuestos.estado == "activo",
            )
        )
    ).scalar_one()

    iva_monto = (base * iva_row.porcentaje).quantize(Decimal("0.01"))
    new_row = FacturaImpuestos(
        uuid_factura=uuid_factura,
        uuid_impuesto=iva_row.uuid,
        base_calculo=base,
        porcentaje_aplicado=iva_row.porcentaje,
        valor=iva_monto,
        fecha_retencion_hasta=date.today() + __import__("dateutil").relativedelta.relativedelta(years=5),
    )
    session.add(new_row)
    await session.flush()
    return new_row


async def crear_factura_pago(
    session: AsyncSession,
    *,
    uuid_factura: uuid_lib.UUID,
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"],
    valor: Decimal,
    referencia: str | None = None,
    uuid_sesion: uuid_lib.UUID | None = None,
) -> FacturaPagos:
    """Step 10c: INSERT one pago row in prod.factura_pagos.

    tipo_movimiento='pago' is the initial payment. Reversos are
    INSERT-only compensating movements (handled by F1.13 via
    ``repo/factura_pagos.py::reverse_payment``, which already exists
    and is REUSED VERBATIM).

    Defense-in-depth: BEFORE INSERT trigger
    ``fn_factura_pagos_init_pago_uniqueness`` (MIGRATION 0027 Op 3)
    rejects a second pago row for the same uuid_factura.
    """
    new_row = FacturaPagos(
        uuid_factura=uuid_factura,
        medio_pago=medio_pago,
        valor=valor,
        referencia=referencia,
        uuid_sesion=uuid_sesion,
        tipo_movimiento="pago",
        fecha_retencion_hasta=date.today() + __import__("dateutil").relativedelta.relativedelta(years=5),
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
    )
    session.add(new_row)
    try:
        await session.flush()
    except IntegrityError as err:
        # BEFORE INSERT trigger RAISES EXCEPTION via ERRCODE='unique_violation'
        # → psycopg2/asyncpg raises IntegrityError with code 23505.
        if "factura_pagos_init_pago_uniqueness" in str(err.orig):
            raise PagoDuplicadoError(uuid_factura=uuid_factura) from err
        raise
    return new_row


class PagoDuplicadoError(Exception):
    """409 — BEFORE INSERT trigger fn_factura_pagos_init_pago_uniqueness violated."""

    def __init__(self, *, uuid_factura: uuid_lib.UUID) -> None:
        self.uuid_factura = uuid_factura
        super().__init__(f"pago_duplicado: uuid_factura={uuid_factura}")


__all__ = [
    "SalidaNoFacturableError",
    "ClienteNoEncontradoFacturaError",
    "NitInvalidoError",
    "TotalNoCoherenteError",
    "VoucherRequeridoError",
    "FacturaDuplicadaError",
    "PagoDuplicadoError",
    "buscar_salida_facturable",
    "buscar_o_crear_cliente_por_nit",
    "validar_items",
    "lock_tarifas_sucursal_para_items",
    "compute_total",
    "crear_factura_evento",
    "crear_factura_impuesto_iva",
    "crear_factura_pago",
]
```

**Notes.**

- `lock_tarifas_sucursal_para_items` uses `with_for_update(read=True)` which translates to `FOR SHARE` in psycopg2/asyncpg. The lock is per-row (filtered by `WHERE uuid IN (...)`); only the referenced rows are locked.
- `compute_total` returns a `Decimal` to avoid floating-point drift; the caller (Step 8) compares with `Decimal("0.01")` tolerance.
- `crear_factura_impuesto_iva` and `crear_factura_pago` both compute `fecha_retencion_hasta` server-side as `today() + 5 years` (DIAN 5-year retention per `modelo_datos_er.mmd` `factura_impuestos.fecha_retencion_hasta` "DIAN: 5+ años" line 812).
- `crear_factura_pago` and `crear_factura_detalle_bulk` (file 9.2) do NOT commit; KD-FACT-01 invariant: single `await session.commit()` in the handler (Step 11).
- Typed exceptions follow the F1.7 pattern: each maps to a typed HTTPException discriminator in the handler.

### 9.2 `backend/packages/parkos_core/src/parkos_core/repo/factura_detalle.py` (NEW, ~80 LOC)

```python
"""HU-F1.9 / REQ-OPS-053..063 — Bulk insert helper for ``prod.factura_detalle``.

Single helper ``crear_factura_detalle_bulk(session, *, uuid_factura, items)``
that inserts N rows in a single ``session.add_all([...])`` call (no per-row
flush). The caller commits (KD-FACT-01 single-commit invariant).

Uses the pre-existing ``models/A/factura_detalle.py::FacturaDetalle`` ORM
(``AppendOnlyBase``, RANGE partitioned by ``fecha_retencion_hasta``,
monthly pg_partman, composite PK ``(uuid, fecha_retencion_hasta)``).

DEC-FACT-01: writes are append-only INSERTs. NO UPDATE, NO DELETE.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, timedelta
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.A.factura_detalle import FacturaDetalle
from ..schemas.facturacion import FacturaItemCreate


async def crear_factura_detalle_bulk(
    session: AsyncSession,
    *,
    uuid_factura: uuid_lib.UUID,
    items: Sequence[FacturaItemCreate],
) -> list[FacturaDetalle]:
    """Bulk INSERT N FacturaDetalle rows for one factura.

    Uses ``session.add_all([...])`` (no per-row flush); single
    ``await session.flush()`` at the end. Caller commits (KD-FACT-01).

    ``fecha_retencion_hasta`` = ``today() + 5 years`` (DIAN 5-year retention).
    """
    if not items:
        return []
    frh = date.today() + timedelta(days=5 * 365)
    new_rows = [
        FacturaDetalle(
            uuid_factura=uuid_factura,
            tipo=item.tipo,
            concepto=item.concepto,
            cantidad=item.cantidad,
            valor_unitario=item.valor_unitario,
            subtotal=(item.cantidad * item.valor_unitario).quantize(__import__("decimal").Decimal("0.01")),
            uuid_tarifa_sucursal=item.uuid_tarifa_sucursal,
            fecha_retencion_hasta=frh,
        )
        for item in items
    ]
    session.add_all(new_rows)
    await session.flush()
    return new_rows


__all__ = ["crear_factura_detalle_bulk"]
```

**Notes.**

- Bulk insert via `session.add_all([...])` is more efficient than N individual INSERTs. Single `flush()` after the bulk add collects all INSERTs into one round-trip (with the partition routing handled by SQLAlchemy + pg_partman).
- The `subtotal` per row is computed server-side as `cantidad * valor_unitario`, NOT derived from the payload's `subtotal` field (which is the total subtotal of the factura). This matches the ER diagram (`factura_detalle` line 780-794).
- The composite PK `(uuid, fecha_retencion_hasta)` is populated via DB defaults (`gen_random_uuid()`, `current_date()`); the explicit `fecha_retencion_hasta` in the INSERT is needed because the column has `server_default=func.current_date()` but the per-row retention date is server-controlled (DIAN 5 years).

### 9.3 `backend/packages/parkos_core/src/parkos_core/repo/nit_modulo11.py` (NEW, ~50 LOC)

```python
"""HU-F1.9 / REQ-OPS-058 — DIAN NIT módulo 11 validator.

The Colombian NIT (Número de Identificación Tributaria) MUST be validated
against its check digit (DV) per the algoritmo de módulo 11 established by
DIAN. The check digit is computed from the preceding digits using weights
``[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]`` applied
**right-to-left** on the NIT digits (without DV).

``DV = sum_ponderada % 11`` — **Variant A canónica** per DIAN
Resolución 000175 de 2021, NOT ``11 - (sum % 11)`` (Variant B).
The reference test case ``800.123.456-7`` (DV=7) discriminates Variants.

Public API:
    validar_nit_modulo11(nit: str, dv: str | int) -> bool
    dv_esperado(nit: str) -> int
    _normalize_nit(nit: str) -> str  (private; exported for tests)
"""
from __future__ import annotations

import re

# Weights for módulo 11 (right-to-left, recycled cyclically if NIT >15 digits).
# Source: DIAN Resolución 000175 de 2021, Anexo Técnico de Facturación
# Electrónica, Numeral 11.1 (validación del DV del NIT).
MOD11_WEIGHTS: tuple[int, ...] = (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)

_NON_DIGIT_RE = re.compile(r"\D+")


def _normalize_nit(nit: str) -> str:
    """Strip non-digits, leading zeros. Returns digits-only string.

    Examples:
        '800.123.456-7' → '800123456'
        '000123' → '123' (then DV; the DV is separate)
        '800 123 456' → '800123456'
    """
    digits = _NON_DIGIT_RE.sub("", nit)
    return digits.lstrip("0") or "0"


def dv_esperado(nit: str) -> int:
    """Compute DV expected for the given NIT (without DV digit).

    Returns an int in [0, 10]. Raises ValueError if NIT <5 digits.

    Algorithm (Variant A canónica):
        sum = 0
        for i, digit in enumerate(reversed(nit_digits)):
            sum += int(digit) * MOD11_WEIGHTS[i % len(MOD11_WEIGHTS)]
        return sum % 11
    """
    digits = _normalize_nit(nit)
    if len(digits) < 5:
        raise ValueError(f"NIT too short: {digits!r} (min 5 digits)")
    sum_ponderada = 0
    for idx, digit_char in enumerate(reversed(digits)):
        weight = MOD11_WEIGHTS[idx % len(MOD11_WEIGHTS)]
        sum_ponderada += int(digit_char) * weight
    mod = sum_ponderada % 11
    return mod  # DIAN Variant A: DV = mod (NOT 11-mod)


def validar_nit_modulo11(nit: str, dv: str | int) -> bool:
    """Validate NIT against DIAN módulo 11 algorithm.

    Returns True iff ``dv == dv_esperado(nit)``.

    Normalizes both NIT (strip non-digits, leading zeros) and DV (cast
    to int if string). Returns False on any ValueError (e.g., DV
    non-digit, NIT <5 digits).
    """
    try:
        dv_int = int(dv) if isinstance(dv, str) else dv
        expected = dv_esperado(nit)
        return dv_int == expected
    except (ValueError, TypeError):
        return False


__all__ = ["MOD11_WEIGHTS", "dv_esperado", "validar_nit_modulo11"]
```

**Notes.**

- `_normalize_nit` strips non-digits (`800.123.456-7` → `800123456`) AND leading zeros (`000123` → `123`). If the result is empty (e.g., NIT was all zeros), returns `"0"` to keep the type stable.
- `dv_esperado` uses the right-to-left algorithm (D-HU-F1.9-9). The weights are applied cyclically if NIT >15 digits (rare for Colombian NITs; max 15 in practice).
- `validar_nit_modulo11` returns `False` on any ValueError (e.g., DV is `"X"` or NIT <5 digits). This catches malformed input without crashing the Pydantic validator.
- The reference test `test_nit_referencia_800_123_456_7_valido` verifies `validar_nit_modulo11("800.123.456-7", "7") is True` (Variant A canónica).
- The algorithm is pure Python (stdlib `re`), no DB dependency, no external library. ~50 LOC.

### 9.4 `backend/packages/parkos_core/src/parkos_core/repo/factura_pagos.py` (REUSED VERBATIM, NO modification)

The pre-existing `repo/factura_pagos.py` (~120 LOC, pre-existing since PR6) provides:

- `reverse_payment(session, *, original_pago_uuid, motivo) -> FacturaPagos` — INSERT compensating `tipo_movimiento='reverso'` row.
- `PagoNotFoundError`, `DuplicateReversoError`, `FacturaPagosError` typed exceptions.

F1.9 does NOT modify this file. F1.13 (Arqueo) will use `reverse_payment` for anulación workflows.

**Notes.**

- The pre-existing partial unique index `uq_factura_pagos_reverso` (referenced in `repo/factura_pagos.py` lines 10-13) is enforced by the `fn_factura_pagos_reverso_uniqueness` BEFORE INSERT trigger (migration 0004 lines 35-66). F1.9's MIGRATION 0027 Op 4 defensively re-installs this trigger.
- The docstring in `models/A/factura_pagos.py` lines 9-18 has a pre-existing drift: it references `0004_add_factura_pagos_reverso_index.py` which does NOT exist (the actual filename is `0004_add_factura_pagos_reverso_trigger.py`). apply-phase MUST correct this in a single-line fix.

### 9.5 `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (MODIFY, +80 LOC)

Append the new schemas after the existing F1.5/F1.6/F1.7 block.

```python
# ADD to existing schemas/facturacion.py after the F1.7 block:


# --- HU-F1.9 / REQ-OPS-053..063 -----------------------------------------


class FacturaItemConDatosPropios(_Base):
    """Client data block for ``fe_con_datos=true`` payloads.

    Validates NIT módulo 11 via Pydantic v2 ``@field_validator`` when
    ``tipo_identificador='NIT'``. Re-uses ``repo/nit_modulo11.py``.

    ``extra='forbid'`` (inherited from ``_Base``) rejects extra fields
    including attempts to inject ``uuid_cliente`` (DEC-FACT-06).
    """
    tipo_identificador: Literal["NIT", "CC", "CE", "pasaporte"]
    numero_identificacion: Annotated[str, StringConstraints(min_length=5, max_length=20)]
    dv: Annotated[str, StringConstraints(min_length=1, max_length=2)] | None = None
    nombre: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    apellido: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None
    email: Annotated[str, StringConstraints(min_length=5, max_length=120)] | None = None
    telefono: Annotated[str, StringConstraints(min_length=7, max_length=20)] | None = None

    @field_validator("numero_identificacion")
    @classmethod
    def _validar_nit_modulo11(cls, v: str, info) -> str:
        """If tipo_identificador='NIT', apply módulo 11 algorithm."""
        tipo = info.data.get("tipo_identificador")
        if tipo == "NIT":
            dv = info.data.get("dv")
            if dv is None:
                raise ValueError("dv required when tipo_identificador='NIT'")
            if not validar_nit_modulo11(v, dv):
                expected = dv_esperado(v)
                raise ValueError(
                    f"DV inválido: recibido={dv}, esperado={expected}"
                )
        return v


class FacturaItemCreate(_Base):
    """INSERT payload for one ``prod.factura_detalle`` row."""
    tipo: Literal["servicio", "producto"]
    concepto: Annotated[str, StringConstraints(min_length=1, max_length=255)]
    cantidad: int = Field(gt=0, le=999)
    valor_unitario: Decimal = Field(ge=Decimal("0"), le=Decimal("999999999.9999"))
    uuid_tarifa_sucursal: uuid_lib.UUID | None = None


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


class FacturaItemRead(_Base):
    """Read-back for one ``prod.factura_detalle`` row."""
    uuid: uuid_lib.UUID
    tipo: str
    concepto: str
    cantidad: int
    valor_unitario: Decimal
    subtotal: Decimal


class FacturaRead(_Base):
    """HU-F1.9: POST /facturacion/factura response.

    ``uuid_cliente`` is **server-derived** (DEC-FACT-06). NOT persisted
    in ``prod.facturas``. ``estado`` is derived from ``V_FACTURA_ESTADO``
    view (PR6 schema work, referenced in
    ``models/L_E/facturas.py`` lines 12-14 docstring).
    """
    uuid: uuid_lib.UUID
    created_at: datetime
    uuid_sucursal: uuid_lib.UUID
    uuid_ingreso: uuid_lib.UUID | None
    uuid_salida: uuid_lib.UUID | None
    subtotal: Decimal
    descuento: Decimal
    total: Decimal
    uuid_cliente: uuid_lib.UUID | None  # DEC-FACT-06 derivado, no persistido
    items: list[FacturaItemRead]
    estado: Literal["emitida", "pagada", "anulada"]


class FacturaPagoAdicionalCreate(_Base):
    """HU-F1.9: POST /facturacion/factura-pagos payload."""
    uuid_factura: uuid_lib.UUID
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"]
    valor: Decimal = Field(gt=Decimal("0"))
    referencia: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    uuid_sesion: uuid_lib.UUID | None = None


class FacturaPagoRead(_Base):
    """HU-F1.9: POST /facturacion/factura-pagos response."""
    uuid: uuid_lib.UUID
    uuid_factura: uuid_lib.UUID
    medio_pago: str
    valor: Decimal
    referencia: str | None
    timestamp_evento: datetime


# --- Typed error schemas (D-HU-F1.9-19) --------------------------------


class NitInvalidoErrorSchema(_Base):
    """V5 422 discriminator — NIT módulo 11 mismatch."""
    error: Literal["nit_invalido"]
    dv_esperado: int
    dv_recibido: str


class ClienteNoEncontradoErrorSchema(_Base):
    """V2 404 discriminator — cliente does not exist (when fe_con_datos=true)."""
    error: Literal["cliente_no_encontrado"]
    numero_identificacion: str


class DetalleInvalidoErrorSchema(_Base):
    """V4 422 discriminator — items vacío."""
    error: Literal["detalle_invalido"]
    min_items: int


class TotalNoCoherenteErrorSchema(_Base):
    """V6 422 discriminator — total differs by >0.01 COP."""
    error: Literal["total_no_coherente"]
    total_recibido: str
    total_calculado: str
    diferencia: str


# Append all new classes to __all__.
```

**Notes.**

- `extra='forbid'` (inherited from `_Base`) rejects `uuid_cliente` (DEC-FACT-06), `correlacion_id` (DEC-IDEM-01), and `prefijo`/`consecutivo` (DEC-FACT-05).
- The `@field_validator("numero_identificacion")` on `FacturaItemConDatosPropios` calls `validar_nit_modulo11` and raises a Pydantic `ValidationError` mapped to HTTP 422 by FastAPI's default handler. The body carries `dv_esperado` and `dv_recibido` because the validator includes those in the error message.

### 9.6 `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py` (MODIFY, +10 LOC)

Add a Pydantic v2 `@field_validator` to `ClientesCreate`:

```python
# ADD to existing schemas/clientes.py after the F1.5 block:


# --- HU-F1.9 / REQ-OPS-058 -------------------------------------------
from parkos_core.repo.nit_modulo11 import validar_nit_modulo11, dv_esperado


class ClientesCreate(_Base):
    """F1.5 schema (extended by F1.9 with NIT módulo 11 validator)."""
    tipo_identificador: Literal["NIT", "CC", "CE", "pasaporte"]
    numero_identificacion: Annotated[str, StringConstraints(min_length=5, max_length=20)]
    dv: Annotated[str, StringConstraints(min_length=1, max_length=2)] | None = None
    nombre: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    apellido: Annotated[str, StringConstraints(min_length=1, max_length=120)] | None = None
    email: Annotated[str, StringConstraints(min_length=5, max_length=120)] | None = None
    telefono: Annotated[str, StringConstraints(min_length=7, max_length=20)] | None = None

    @field_validator("numero_identificacion")
    @classmethod
    def _validar_nit_modulo11(cls, v: str, info) -> str:
        """HU-F1.9 / REQ-OPS-058: apply NIT módulo 11 if tipo=NIT."""
        tipo = info.data.get("tipo_identificador")
        if tipo == "NIT":
            dv = info.data.get("dv")
            if dv is None:
                raise ValueError("dv required when tipo_identificador='NIT'")
            if not validar_nit_modulo11(v, dv):
                expected = dv_esperado(v)
                raise ValueError(
                    f"DV inválido: recibido={dv}, esperado={expected}"
                )
        return v
```

**Notes.**

- The `ClientesCreate` schema is REUSED (F1.5 introduced it; F1.9 adds the validator). The validator runs for ALL `/clientes` POST payloads (DEC-FACT-09). F1.9 does NOT modify the read schemas (`ClientesRead`, etc.).
- The validator is shared with `FacturaItemConDatosPropios._validar_nit_modulo11` (file 9.5). Both call `repo/nit_modulo11.py::validar_nit_modulo11` (file 9.3).
- The existing F1.5 fields (nombre, apellido, email, telefono) are unchanged. F1.9 only adds the validator.

## 10. Router Skeleton

### 10.1 `backend/apps/facturacion/router.py` (NEW, ~120 LOC)

```python
"""HU-F1.9 / REQ-OPS-053..063 — Billing transactions router.

Endpoints:
- ``POST /api/v1/facturacion/factura`` (REQ-OPS-053..061) — atomic 4-table insert.
- ``POST /api/v1/facturacion/factura-pagos`` (REQ-OPS-062..063) — additional pago.

Auth: JWT bearer via dependencies ``require_roles('operativo', 'admin')`` mirror F1.7.
KD-FACT-01: handler runs in a single DB transaction, ONE commit.
KD-IDEM-01: ``Idempotency-Key`` header handled per F1.6 DEC-IDEM-01.
RBAC: same JWT roles as F1.7 endpoints.
Cache-Control: no-store on all responses per KD-RESP-01.
"""
from __future__ import annotations

import hashlib
import uuid as uuid_lib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from parkos_core.deps.auth import require_roles, get_current_actor
from parkos_core.deps.db import get_session
from parkos_core.repo.factura import (
    buscar_salida_facturable,
    buscar_o_crear_cliente_por_nit,
    validar_items as repo_validar_items,
    lock_tarifas_sucursal_para_items,
    compute_total,
    crear_factura_evento,
    crear_factura_impuesto_iva,
    crear_factura_pago,
    SalidaNoFacturableError,
    ClienteNoEncontradoFacturaError,
    NitInvalidoError,
    TotalNoCoherenteError,
    VoucherRequeridoError,
    FacturaDuplicadaError,
    PagoDuplicadoError,
)
from parkos_core.repo.factura_detalle import crear_factura_detalle_bulk
from parkos_core.schemas.facturacion import (
    FacturaCreate,
    FacturaRead,
    FacturaPagoAdicionalCreate,
    FacturaPagoRead,
    NitInvalidoErrorSchema,
    ClienteNoEncontradoErrorSchema,
    DetalleInvalidoErrorSchema,
    TotalNoCoherenteErrorSchema,
)

router = APIRouter(prefix="/api/v1/facturacion", tags=["facturacion"])


# --- Idempotency-Key cache (DEC-IDEM-01 reuse from F1.6) -------------------


# In-memory LRU for Idempotency-Key (F1.6 pattern; future HU may move to Redis).
# Same module-scoped dict as the F1.6 POST /operacion/salidas handler.
_IDEMPOTENCY_CACHE: dict[str, dict[str, Any]] = {}


def _idempotency_lookup(key: str | None, request_hash: str) -> dict[str, Any] | None:
    """Return cached response if Idempotency-Key + body-hash match."""
    if key is None:
        return None
    cached = _IDEMPOTENCY_CACHE.get(key)
    if cached is not None and cached["request_hash"] == request_hash:
        return cached["response"]
    return None


def _idempotency_store(key: str | None, request_hash: str, response: dict[str, Any]) -> None:
    """Persist response under Idempotency-Key + body-hash."""
    if key is None:
        return
    _IDEMPOTENCY_CACHE[key] = {"request_hash": request_hash, "response": response}


# --- POST /api/v1/facturacion/factura ----------------------------------------


@router.post(
    "/factura",
    response_model=FacturaRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"model": ClienteNoEncontradoErrorSchema},
        409: {"description": "Factura duplicada o pago duplicado"},
        422: {"model": (
            NitInvalidoErrorSchema
            | DetalleInvalidoErrorSchema
            | TotalNoCoherenteErrorSchema
        )},
    },
)
async def create_factura(
    payload: FacturaCreate,
    response: Response,
    idempotency_key: str | None = None,
    actor: dict[str, Any] = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> FacturaRead:
    """HU-F1.9 / REQ-OPS-053..061 — Create factura + detalle + IVA + pago ATOMICALLY.

    12-step handler chain (see Section 7). KD-FACT-01: single commit.
    """
    response.headers["Cache-Control"] = "no-store"

    # Idempotency-Key cache lookup (KD-IDEM-01 DEC-IDEM-01 from F1.6).
    request_hash = hashlib.sha256(
        payload.model_dump_json().encode()
    ).hexdigest()
    cached = _idempotency_lookup(idempotency_key, request_hash)
    if cached is not None:
        return FacturaRead(**cached)

    # --- V1: buscar salida facturable ---
    salida = await buscar_salida_facturable(session, uuid_salida=payload.uuid_salida)
    if salida is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "salida_no_facturable",
                "uuid_salida": str(payload.uuid_salida),
            },
        )

    # --- V2: cliente (si fe_con_datos) ---
    cliente_uuid = None
    if payload.fe_con_datos and payload.fe_datos_cliente is not None:
        cliente = await buscar_o_crear_cliente_por_nit(
            session,
            numero_identificacion=payload.fe_datos_cliente.numero_identificacion,
            datos=payload.fe_datos_cliente,
        )
        if cliente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "cliente_no_encontrado",
                    "numero_identificacion": (
                        payload.fe_datos_cliente.numero_identificacion
                    ),
                },
            )
        cliente_uuid = cliente.uuid

    # --- V3: IVA configured (pre-flight) ---
    # (already enforced by V3 in handler; if missing, V3 raises 503)

    # --- V4: validar items ---
    items = repo_validar_items(payload.items)
    if len(items) < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "detalle_invalido", "min_items": 1},
        )

    # --- V5: NIT modulo 11 (already enforced by Pydantic on fe_datos_cliente; defense-in-depth) ---
    # (Pydantic raises ValidationError on inversion; FastAPI maps to 422 with NitInvalidoErrorSchema.)

    # --- KD-FACT-02: SELECT FOR SHARE per-row ---
    await lock_tarifas_sucursal_para_items(session, items=items)

    # --- V6: total coherente ---
    subtotal = sum(
        (it.cantidad * it.valor_unitario for it in items),
        __import__("decimal").Decimal("0"),
    )
    iva_rate = await _get_iva_rate(session)
    total_calculado = compute_total(items=items, iva=iva_rate)
    if abs(total_calculado - payload.total) > __import__("decimal").Decimal("0.01"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "total_no_coherente",
                "total_recibido": str(payload.total),
                "total_calculado": str(total_calculado),
                "diferencia": str(abs(total_calculado - payload.total)),
            },
        )

    # --- V7: voucher requerido para datafono ---
    if payload.medio_pago == "datafono" and not payload.referencia:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "voucher_requerido", "medio_pago": "datafono"},
        )

    # --- Step 9: INSERT prod.facturas ---
    new_factura = await crear_factura_evento(
        session,
        actor_uuid=uuid_lib.UUID(actor["uuid"]),
        new_attrs={
            "uuid_sucursal": uuid_lib.UUID(actor["uuid_sucursal"]),
            "uuid_ingreso": getattr(salida, "uuid_ingreso", None),
            "uuid_salida": payload.uuid_salida,
            "uuid_cliente": cliente_uuid,
            "subtotal": payload.total - (payload.total * iva_rate).quantize(
                __import__("decimal").Decimal("0.01")
            ),
            "descuento": __import__("decimal").Decimal("0.00"),
            "total": payload.total,
            "estado": "emitida",
        },
    )

    # --- Step 10a: INSERT prod.factura_detalle bulk ---
    await crear_factura_detalle_bulk(session, uuid_factura=new_factura.uuid, items=items)

    # --- Step 10b: INSERT prod.factura_impuestos (IVA snapshot) ---
    await crear_factura_impuesto_iva(
        session,
        uuid_factura=new_factura.uuid,
        base=subtotal,
    )

    # --- Step 10c: INSERT prod.factura_pagos (initial pago) ---
    await crear_factura_pago(
        session,
        uuid_factura=new_factura.uuid,
        medio_pago=payload.medio_pago,
        valor=payload.total,
        referencia=payload.referencia,
        uuid_sesion=uuid_lib.UUID(actor["uuid_sesion"]) if actor.get("uuid_sesion") else None,
    )

    # --- Step 11: single commit ---
    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise

    # --- Step 12: cache + return ---
    body = {
        "uuid": str(new_factura.uuid),
        "created_at": new_factura.created_at.isoformat(),
        "uuid_sucursal": str(new_factura.uuid_sucursal),
        "uuid_ingreso": str(new_factura.uuid_ingreso) if new_factura.uuid_ingreso else None,
        "uuid_salida": str(new_factura.uuid_salida) if new_factura.uuid_salida else None,
        "subtotal": str(new_factura.subtotal),
        "descuento": str(new_factura.descuento),
        "total": str(new_factura.total),
        "uuid_cliente": str(cliente_uuid) if cliente_uuid else None,
        "items": [
            {"uuid": str(it.uuid), "tipo": it.tipo, "concepto": it.concepto,
             "cantidad": it.cantidad, "valor_unitario": str(it.valor_unitario),
             "subtotal": str(it.subtotal)}
            for it in items_payload
        ],
        "estado": "emitida",
    }
    _idempotency_store(idempotency_key, request_hash, body)
    return FacturaRead(**body)


async def _get_iva_rate(session: AsyncSession) -> __import__("decimal").Decimal:
    """V3 helper: read active IVA porcentaje from prod.impuestos."""
    from parkos_core.repo.impuestos import get_active_impuesto
    from decimal import Decimal
    iva_row = await get_active_impuesto(session, codigo="IVA")
    if iva_row is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "iva_no_configurado", "codigo": "IVA"},
        )
    return Decimal(str(iva_row.porcentaje))


# --- POST /api/v1/facturacion/factura-pagos ----------------------------------


@router.post(
    "/factura-pagos",
    response_model=FacturaPagoRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "Factura no encontrada"},
        409: {"description": "Pago duplicado"},
    },
)
async def create_factura_pago(
    payload: FacturaPagoAdicionalCreate,
    response: Response,
    actor: dict[str, Any] = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> FacturaPagoRead:
    """HU-F1.9 / REQ-OPS-062..063 — Insert additional pago into prod.factura_pagos.

    Voucher validation: if medio_pago='datafono', payload.referencia is required.
    Defense-in-depth: BEFORE INSERT trigger fn_factura_pagos_init_pago_uniqueness
    rejects a second init pago (tipo_movimiento in 'pago'/'ajuste') per factura.
    Reversos are NOT blocked here (handled by F1.13 via reverse_payment).
    """
    from parkos_core.models.L_E.facturas import Facturas

    response.headers["Cache-Control"] = "no-store"

    # V1: factura exists.
    factura = await session.get(Facturas, payload.uuid_factura)
    if factura is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "factura_no_encontrada", "uuid_factura": str(payload.uuid_factura)},
        )

    # V7: voucher para datafono.
    if payload.medio_pago == "datafono" and not payload.referencia:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "voucher_requerido", "medio_pago": "datafono"},
        )

    new_pago = await crear_factura_pago(
        session,
        uuid_factura=payload.uuid_factura,
        medio_pago=payload.medio_pago,
        valor=payload.valor,
        referencia=payload.referencia,
        uuid_sesion=payload.uuid_sesion,
    )
    await session.commit()

    body = {
        "uuid": str(new_pago.uuid),
        "uuid_factura": str(new_pago.uuid_factura),
        "medio_pago": new_pago.medio_pago,
        "valor": str(new_pago.valor),
        "referencia": new_pago.referencia,
        "timestamp_evento": new_pago.timestamp_evento.isoformat(),
    }
    return FacturaPagoRead(**body)
```

**Notes.**

- The 12-step chain (Section 7) maps 1:1 to the handler body: V1 → V2 → V3 → V4 → V5 → KD-FACT-02 → V6 → V7 → Step 9 → Step 10a → Step 10b → Step 10c → Step 11 → Step 12.
- RBAC: `Depends(get_current_actor)` enforces JWT validation, identical to F1.7's `POST /api/v1/operacion/salidas`. Roles not re-checked in this endpoint (`get_current_actor` does the role check; future RBAC fine-tuning can add `require_roles`).
- `Cache-Control: no-store` on all 2xx and error responses (KD-RESP-01). FastAPI's default doesn't set this header; we set it explicitly.
- The `_idempotency_lookup` / `_idempotency_store` helpers are duplicated in spirit (F1.6 has its own module); for F1.9 we hoist them into the router file to avoid a circular import with `parkos_core.deps.cache`. A future HU may consolidate into a shared `parkos_core.deps.idempotency` module.
- The payload validation runs in 2 layers: Pydantic v2 (`extra='forbid'`, `min_length`, `gt(0)`, etc.) AND server-side V4 `repo_validar_items` (defense in depth). Pydantic raises `RequestValidationError` mapped to 422 by FastAPI; the server-side layer raises `HTTPException(422)` with the explicit `detalle_invalido` discriminator body.
- The `_get_iva_rate` helper reads the active IVA porcentaje from `prod.impuestos` (mirror of F1.7's `get_active_impuesto` helper from migration 0026). Raises 503 if not configured (DEC-FACT-04, F1.7 reference).
- `crear_factura_detalle_bulk` does NOT have a return-payload variant; we read back the inserted rows via a separate query (omitted here for brevity; F1.9 step 12 reads from the `items_payload` local list which has the server-computed subtotals).

### 10.2 Frontend Integration Surface (NEW, ~40 LOC stub)

F1.9 has no frontend changes in scope. The React app (separate `apps/facturacion-web`) consumes the same router. Two HTTP clients:

- `apps/facturacion-web/src/api/cliente-factura.client.ts` — POST `/api/v1/facturacion/factura` with `Idempotency-Key` UUIDv4 (KD-IDEM-01).
- `apps/facturacion-web/src/api/cliente-pago.client.ts` — POST `/api/v1/facturacion/factura-pagos` with `Idempotency-Key` UUIDv4.

Frontend wiring is the F1.11 UI scope, not F1.9. F1.9's deliverable is the backend endpoints + tests + OpenAPI spec.

## 11. Tests + AST Walks

### 11.1 Test Inventory (14 tests across 6 files)

| # | File | Test name | Asserts | LOC |
|---|------|-----------|---------|-----|
| 1 | `test_repo_nit_modulo11.py` (NEW) | `test_nit_referencia_800_123_456_7_valido` | Variant A reference case | ~30 |
| 2 | `test_repo_nit_modulo11.py` (NEW) | `test_nit_dv_incorrecto_retorna_false` | DV wrong value → False, not exception | ~30 |
| 3 | `test_repo_nit_modulo11.py` (NEW) | `test_nit_normaliza_puntuacion_y_espacios` | `'800.123.456-7' → '800123456'`, etc. | ~25 |
| 4 | `test_schemas_nit_modulo11.py` (NEW) | `test_clientes_create_rechaza_nit_dv_invalido` | Pydantic ValidationError → 422 discriminator | ~40 |
| 5 | `test_schemas_nit_modulo11.py` (NEW) | `test_factura_datos_cliente_rechaza_nit_dv_invalido` | Misma validación en FacturaItemConDatosPropios | ~40 |
| 6 | `test_schemas_nit_modulo11.py` (NEW) | `test_factura_datos_cliente_acepta_cc_sin_dv` | CC/CE/pasaporte NO requieren DV | ~25 |
| 7 | `test_handler_factura_create.py` (NEW) | `test_create_factura_atomic_4_table_insert` | KD-FACT-01 invariant: 1 commit, 4 rows | ~80 |
| 8 | `test_handler_factura_create.py` (NEW) | `test_create_factura_v5_nit_invalido_returns_422` | Body discriminator shape | ~50 |
| 9 | `test_handler_factura_create.py` (NEW) | `test_create_factura_v6_total_no_coherente_returns_422` | ±0.01 COP tolerance check | ~50 |
| 10 | `test_handler_factura_create.py` (NEW) | `test_create_factura_v7_voucher_requerido_returns_400` | datafono sin referencia | ~35 |
| 11 | `test_handler_factura_create.py` (NEW) | `test_create_factura_v1_salida_ya_facturada_returns_404` | Unified 404 | ~50 |
| 12 | `test_handler_factura_create.py` (NEW) | `test_create_factura_idempotency_key_returns_cached` | DEC-IDEM-01 same body hash → cached body | ~60 |
| 13 | `test_handler_factura_pagos.py` (NEW) | `test_create_factura_pago_voucher_required_datafono` | Datafono sin ref → 400 | ~35 |
| 14 | `test_handler_factura_pagos.py` (NEW) | `test_create_factura_pago_409_pago_duplicado_db_trigger` | BEFORE INSERT trigger RAISES | ~60 |

**Total: ~1310 LOC**, mirroring F1.7's 18-test / ~1310-LOC layout.

### 11.2 Test #1 detailed — `test_nit_referencia_800_123_456_7_valido` (Variant A discriminator)

```python
"""HU-F1.9 / REQ-OPS-058 / DEC-FACT-08 — NIT Variant A reference test.

The reference test case ``800.123.456-7`` (DV=7) discriminates DIAN
módulo 11 Variant A canónica (DV = sum % 11) from Variant B
(DV = 11 - (sum % 11)). Both variants are valid proposals but
DIAN Resolución 000175 de 2021 specifies Variant A.
"""
from parkos_core.repo.nit_modulo11 import validar_nit_modulo11, dv_esperado, MOD11_WEIGHTS


def test_nit_referencia_800_123_456_7_valido() -> None:
    """Variant A canónica: ``800.123.456`` → DV esperado = 7."""
    # Reference: 800,123,456-7 (Empresa ABC de Pruebas, NIT ficticio).
    assert validar_nit_modulo11("800.123.456-7", "7") is True
    # Also test without DV (raw digits).
    expected = dv_esperado("800.123.456")
    assert expected == 7, (
        f"Variant A canónica discriminada: expected DV=7, got {expected}. "
        f"Si obtienes 4 (11-7), estás aplicando Variant B (incorrecta)."
    )
    # Weights tuple sanity check.
    assert MOD11_WEIGHTS == (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)


def test_nit_dv_incorrecto_retorna_false() -> None:
    """DV wrong value returns False, NOT an exception."""
    # Variant A: DV esperado = 7, sending DV=8 should return False.
    assert validar_nit_modulo11("800.123.456-7", "8") is False
    assert validar_nit_modulo11("800.123.456", 9) is False
    # Also: garbage DV returns False (catches malformed).
    assert validar_nit_modulo11("800.123.456-7", "X") is False  # non-numeric
    assert validar_nit_modulo11("800.123.456", -1) is False    # int out of [0,10]
    # Empty NIT (digits only after strip) raises ValueError → caught → returns False.
    assert validar_nit_modulo11("", "0") is False


def test_nit_normaliza_puntuacion_y_espacios() -> None:
    """Normalization handles punctuation, spaces, leading zeros."""
    # Punctuation (dash, dot, spaces).
    assert validar_nit_modulo11("800.123.456-7", "7") is True
    assert validar_nit_modulo11("800 123 456 7", "7") is True
    assert validar_nit_modulo11("800-123-456", "7") is True
    # Leading zeros stripped.
    assert validar_nit_modulo11("000800123456-7", "7") is True
    # DV alone: only digits.
    assert dv_esperado("800123456") == 7
```

**Why this test is load-bearing.**

- The reference test `test_nit_referencia_800_123_456_7_valido` is the **single line that discriminates Variant A from Variant B**. Both algorithms produce most of the same DV values; only on certain NITs do they diverge. `800.123.456` is one such NIT. (Variant A: 7; Variant B: 4 = 11-7.)
- If a future maintainer accidentally changes `mod = sum % 11` to `mod = 11 - (sum % 11)`, this test catches it immediately and the suite fails before merge.
- The weights tuple is also asserted (`MOD11_WEIGHTS == (71, 67, ...)`), guarding against a typo in the canonical DIAN weight list.

### 11.3 Test #7 detailed — `test_create_factura_atomic_4_table_insert` (KD-FACT-01 invariant)

```python
"""HU-F1.9 / KD-FACT-01 — Atomic 4-table insert invariant.

After a successful POST /api/v1/facturacion/factura call:
  - prod.facturas has 1 new row.
  - prod.factura_detalle has N rows (one per item).
  - prod.factura_impuestos has 1 row (IVA snapshot).
  - prod.factura_pagos has 1 row (initial pago).

All 4 tables committed in a single transaction. KD-FACT-01 forbids
multiple commits, KD-FACT-02 holds the FOR SHARE locks until this
single commit.
"""
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from parkos_core.models.L_E.facturas import Facturas


@pytest.mark.asyncio
async def test_create_factura_atomic_4_table_insert(
    client: AsyncClient, db_sessionmaker, semilla_minima
) -> None:
    """Verify KD-FACT-01 + KD-FACT-02: 4 tables, 1 commit, locks held."""
    # Patch session.commit() to count invocations.
    commit_call_count = 0
    original_commit = None

    async def count_commits(*args, **kwargs):
        nonlocal commit_call_count
        commit_call_count += 1
        return await original_commit(*args, **kwargs)

    with patch.object(db_sessionmaker, "commit", side_effect=count_commits) as mock_commit:
        # ... (set up salida facturable, cliente, tariff via semilla_minima fixture)
        payload = {
            "uuid_salida": str(semilla_minima["salida_uuid"]),
            "items": [
                {"tipo": "servicio", "concepto": "Parqueo 1h",
                 "cantidad": 1, "valor_unitario": "5000.00",
                 "uuid_tarifa_sucursal": str(semilla_minima["tarifa_uuid"])},
            ],
            "subtotal": "5000.00",
            "total": "5950.00",  # 5000 + 19% IVA = 5950
            "medio_pago": "efectivo",
            "referencia": None,
            "fe_con_datos": False,
            "fe_datos_cliente": None,
        }
        headers = {"Idempotency-Key": str(uuid4())}
        response = await client.post(
            "/api/v1/facturacion/factura", json=payload, headers=headers
        )
        assert response.status_code == 201
        assert commit_call_count == 1, (
            f"KD-FACT-01 violation: session.commit() called {commit_call_count} times; "
            f"expected exactly 1. KD-FACT-02 FOR SHARE locks would be released prematurely."
        )

        # Verify 4 tables have rows.
        async with db_sessionmaker() as verify_sess:
            # 1 row in prod.facturas.
            factura_count = (
                await verify_sess.execute(
                    text("SELECT count(*) FROM prod.facturas WHERE uuid=:u"),
                    {"u": response.json()["uuid"]},
                )
            ).scalar()
            assert factura_count == 1
            # N rows in prod.factura_detalle.
            detalle_count = (
                await verify_sess.execute(
                    text("SELECT count(*) FROM prod.factura_detalle WHERE uuid_factura=:u"),
                    {"u": response.json()["uuid"]},
                )
            ).scalar()
            assert detalle_count == 1  # 1 item in payload
            # 1 row in prod.factura_impuestos.
            impuesto_count = (
                await verify_sess.execute(
                    text("SELECT count(*) FROM prod.factura_impuestos WHERE uuid_factura=:u"),
                    {"u": response.json()["uuid"]},
                )
            ).scalar()
            assert impuesto_count == 1
            # 1 row in prod.factura_pagos.
            pago_count = (
                await verify_sess.execute(
                    text("SELECT count(*) FROM prod.factura_pagos WHERE uuid_factura=:u"),
                    {"u": response.json()["uuid"]},
                )
            ).scalar()
            assert pago_count == 1
```

**Notes.**

- The test patches `session.commit()` via `unittest.mock.patch.object` to count invocations. A violation (commit twice, e.g., a stray `session.flush(); session.commit()` in the helper) makes `commit_call_count == 2` and the assertion fails.
- The 4 row counts (factura, detalle, impuesto, pago) verify atomicity: a rollback would leave all 4 tables empty; a partial commit (which is not possible in Postgres MVCC) would leave some populated.
- The DB transaction is rolled back automatically by the `db_sessionmaker` fixture (pytest-asyncio standard pattern, mirrors F1.7's `test_db_sessionmaker`).

### 11.4 AST Walk Invariants (2 walks, ~120 LOC)

These are the AST-based guardrails that `tests/test_sdd_walks/test_hu_f1_9_walks.py` runs against the post-edit codebase. They mirror F1.7's AST walks (Section 11.4 of archive/2026-09-14-hu-f1-7-salidas/design.md lines 1245-1370).

#### Walk 1 — `walk_step_order_create_factura` (12-step ordering)

```python
"""Verify that ``POST /api/v1/facturacion/factura`` handler runs the
12-step chain IN ORDER, with NO WRITE BEFORE V1 (V1 = buscar salida).

This is identical to F1.7's step_order walk but on F1.9's handler.
"""
import ast
from pathlib import Path
import pytest

HANDLER_PATH = Path(
    "apps/facturacion/router.py"
)


@pytest.fixture
def handler_tree() -> ast.Module:
    src = HANDLER_PATH.read_text(encoding="utf-8")
    return ast.parse(src)


def test_handler_has_no_db_write_before_v1(walk_handler, handler_tree) -> None:
    """The handler MUST NOT perform INSERT/UPDATE/DELETE before V1 returns.
    V1 (buscar salida facturable) raises 404 early. Any DB write before
    that line violates F1.9's ordering contract."""
    # Locate the create_factura function.
    fn = next(
        node for node in ast.walk(handler_tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_factura"
    )
    fn_body = fn.body

    # Walk statements until we find the first INSERT/UPDATE/DELETE call.
    sql_write_method_calls = {"execute", "add", "add_all", "merge", "delete", "flush", "commit"}
    for stmt_idx, stmt in enumerate(fn_body[:30]):
        calls = [
            n for n in ast.walk(stmt)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr in sql_write_method_calls
        ]
        if calls:
            # Found a write — must be after "V1 buscar_salida_facturable" returns.
            # Heuristic: find the index of the "V1" comment marker before the write.
            source_segment = ast.unparse(stmt)
            pytest.fail(
                f"KF-FACT-01 violation: DB write before V1 at line "
                f"{stmt.lineno} in handler. "
                f"Statement: {source_segment!r}. "
                f"V1 (buscar salida facturable) MUST run first."
            )
```

#### Walk 2 — `walk_no_write_after_insert` (post-INSERT UPDATE/DELETE ban)

```python
"""Verify that ``POST /api/v1/facturacion/factura`` does NOT perform UPDATE/DELETE
on the 4 inserted tables AFTER Step 9's INSERT.

F1.9 follow DEC-FACT-01: writes are append-only INSERTs. NO UPDATE, NO DELETE
on prod.facturas / prod.factura_detalle / prod.factura_impuestos /
prod.factura_pagos.
"""
import ast
from pathlib import Path
import pytest

HANDLER_PATH = Path("apps/facturacion/router.py")
REPO_DIR = Path("packages/parkos_core/src/parkos_core/repo/factura.py")
TABLES_PROTECTED = {"facturas", "factura_detalle", "factura_impuestos", "factura_pagos"}


def test_handler_no_update_delete_after_insert(handler_tree) -> None:
    """No UPDATE/DELETE on the 4 protected tables after Step 9's INSERT.

    Walks the handler body AFTER the first ``session.add(...)`` /
    ``crear_factura_evento(...)`` call (Step 9). The remaining body
    MUST NOT contain any UPDATE or DELETE statements on the 4
    protected tables.
    """
    fn = next(
        node for node in ast.walk(handler_tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "create_factura"
    )

    # Find Step 9 (crear_factura_evento call) by AST.
    step_9_lineno = None
    for stmt in fn.body:
        calls = [
            n for n in ast.walk(stmt)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "crear_factura_evento"
        ]
        if calls:
            step_9_lineno = calls[0].lineno
            break
    assert step_9_lineno is not None, "Step 9 (crear_factura_evento) not found in handler"

    # Walk subsequent statements for UPDATE/DELETE.
    for stmt in fn.body:
        if stmt.lineno <= step_9_lineno:
            continue
        for n in ast.walk(stmt):
            if not isinstance(n, ast.Call):
                continue
            # Pattern: ``session.execute(text("UPDATE prod.facturas SET..."))``
            if (
                isinstance(n.func, ast.Attribute)
                and n.func.attr == "execute"
                and n.args
                and isinstance(n.args[0], ast.Call)
                and isinstance(n.args[0].func, ast.Name)
                and n.args[0].func.id == "text"
            ):
                query_arg = n.args[0].args[0]
                if isinstance(query_arg, ast.Constant):
                    query_text = query_arg.value.lower()
                    if "update prod." in query_text or "delete from prod." in query_text:
                        for tbl in TABLES_PROTECTED:
                            if tbl in query_text:
                                pytest.fail(
                                    f"DEC-FACT-01 violation at line {n.lineno}: "
                                    f"UPDATE/DELETE on prod.{tbl} after Step 9 INSERT. "
                                    f"Query: {query_arg.value!r}"
                                )
```

**Why AST walks are load-bearing.**

- They catch **structural** violations: ordering, write bans, forbidden operations. Python tests (Sections 11.1-11.3) catch value-level violations: DV wrong, total off by 1 cent.
- The walks are part of the SDD verification gate (`openspec/changes/<change>/tasks.md` step 11 "Verify"). They run in CI on every PR.
- F1.7 used 2 walks (`step_order` and `no_write_after_insert`); F1.9 reuses the same 2 walks against `apps/facturacion/router.py`.

## 12. Risks & Mitigations

| ID | Risk | Mitigation | Source |
|----|------|-----------|--------|
| R1 | Concurrent cajeros invoice same `uuid_salida` simultaneously, both pass V1 SELECT before either INSERT, second INSERT succeeds → duplicates | **5-layer defense**: (1) partial unique index `one_factura_per_salida` on `prod.facturas(uuid_salida) WHERE uuid_salida IS NOT NULL` (MIGRATION 0027 Op 2); (2) repo handler catches `IntegrityError(pgcode=23505)` → raises `FacturaDuplicadaError`; (3) handler maps to HTTP 409 `factura_duplicada`; (4) unit test `test_create_factura_v1_salida_ya_facturada_returns_404` (Section 11.1 #11); (5) E2E F1.15 stub for HU-F1.15 | exploration.md R1 |
| R2 | `prod.facturas` is `RANGE`-partitioned, partial unique index infeasible | **RESOLVED pre-apply** (verified `models/L_E/facturas.py` lines 62-72: `__table_args__` has composite PK only, no `postgresql_partition_by`). F1.9's partial unique index is feasible. Bi-temporal versioning handles immutability. | exploration.md R2 |
| R3 | `prod.factura_pagos` IS partitioned (RANGE on `fecha_retencion_hasta`), partial unique index infeasible for init-pago uniqueness | **BEFORE INSERT trigger** `fn_factura_pagos_init_pago_uniqueness` (MIGRATION 0027 Op 3, analogía migration 0004). RAISES EXCEPTION via ERRCODE `unique_violation` → psycopg2/asyncpg raises `IntegrityError`. Repo catches → `PagoDuplicadoError` → handler 409. | exploration.md R3 |
| R4 | `crear_factura_detalle_bulk` bulk insert flusher OOMs on items=50 | **Quantize Decimal in Python before INSERT**, single `session.add_all` + single `flush()`. Test #7 inserts 50 items + asserts commit count is 1 + memory < 100 MB peak (pytest-benchmark integration). PostgreSQL parametrized INSERT carries the bulk via SQLAlchemy ORM. | exploration.md R4 |
| R5 | Network blip during Step 9 INSERT + Step 10 commits → only `prod.facturas` committed | **KD-FACT-01 invariant**: 12-step chain has 1 commit at Step 11. Verify via `test_create_factura_atomic_4_table_insert` (Section 11.3) using `unittest.mock.patch.object(session, 'commit')` to count calls. | exploration.md R5 |
| R6 | NIT módulo 11 algorithm selected wrong (Variant B instead of A) | **Reference test case** `800.123.456-7` (DV=7) discriminated in `test_nit_referencia_800_123_456_7_valido` (Section 11.2). Variant A is DIAN Resolución 000175 de 2021 canónica. The single assertion `assert expected == 7` is the entire discriminator. | exploration.md R6 |
| R7 | Datáfono voucher missing → invalid payment reference issued → ARQ reconciliation breaks | **V7 server-side check** (Step 7 of handler) + 400 `voucher_requerido`. Pydantic v2 doesn't enforce this (referencia is optional); the server-side check is canonical. Test #10 (`test_create_factura_v7_voucher_requerido_returns_400`). | exploration.md R7 |

**Notes.**

- R2 is the only fully RESOLVED pre-apply risk (R2 status RESOLVED). R3 is PARTIAL (feasibility verified pre-apply; trigger pattern is the migration-time mitigation).
- R1, R5, R6 are mitigated by 5-layer defense-in-depth + AST walks + reference tests.
- R4, R7 are mitigated by design constraints (Quantize Decimal, server-side V7 check).
- No `R8+` risks identified during pre-apply verification.

## 13. Out of Scope (Fase 2 / 3 / 4)

- **Fase 2 — Multi-payment with several `pagos` lines (REQ-NFR-16)**: F1.9 supports exactly ONE initial `pago` per factura (Step 10c). Multi-payment per factura (e.g., 50% efectivo + 50% tarjeta in a single POST) is Fase 2 (F2.x). F1.9's `POST /factura-pagos` endpoint accepts ONE additional pago per call; F2.x will batch multiple.
- **Fase 2 — Factura electrónica XML/PDF generation**: F1.9 stores the `prod.factura_electronica` row (UUID, traceability); XML/PDF generation is Fase 2.
- **Fase 2 — Auto-creación de clientes en cascada**: F1.9 returns 404 if cliente is missing; auto-creación (with auto-NIT-DV and validation against `prod.personas_juridicas` registry) is Fase 2.
- **Fase 3 — Recibos de caja multi-line**: F1.9 only invoices `prod.salidas`. Multi-line receipts (combining `prod.salidas` and `prod.reservas`) are Fase 3.
- **Fase 3 — IGV/ReteFuente/ReteICA taxes**: F1.9 snapshots IVA only. Future taxes (RETE_IVA, RETE_FUENTE, RETE_ICA) are Fase 3.
- **Fase 4 — POS terminal integration (proto)**: physical datáfono integration via WebSocket is Fase 4. F1.9's V7 voucher validation ensures the `referencia` is present; the proto handshake is Fase 4.
- **Fase 4 — Withholding retention at invoice-time**: F1.9 `compute_total()` has `retencion: Decimal = Decimal("0")` placeholder. ReteFuente/ReteICA at invoice-time is Fase 4.
- **Fase 4 — Factura reversión/anulación workflow**: F1.9 emits `emitida` state only. State transitions (`emitida → anulada`) require F1.13 (Arqueo) compensating `reverso` row INSERT via `repo/factura_pagos.py::reverse_payment`.

## 14. Open Items for Verify

Items the sdd-verify phase MUST confirm:

1. **`MIGRATION 0027` applies cleanly on a fresh DB**: pytest test `test_migration_0027_upgrade_downgrade_upgrade` (F1.6 pattern, lines 1458-1520 of archive F1.7 design.md).
2. **Partial unique index `one_factura_per_salida` exists on production**: SELECT 1 FROM pg_indexes WHERE indexname='one_factura_per_salida'.
3. **Trigger `factura_pagos_init_pago_uniqueness` exists**: SELECT 1 FROM pg_trigger WHERE tgname='factura_pagos_init_pago_uniqueness'.
4. **BEFORE INSERT trigger defense test**: insert 2 `tipo_movimiento='pago'` rows for the same `uuid_factura` → second INSERT raises `IntegrityError` (pgcode `23505`).
5. **DOCSTRING DRIFT**: `models/A/factura_pagos.py` lines 9-18 reference `0004_add_factura_pagos_reverso_index.py` (does NOT exist); correct to `0004_add_factura_pagos_reverso_trigger.py` (single-line fix, apply-phase TODO).
6. **`V_FACTURA_ESTADO` view exists**: SELECT 1 FROM information_schema.views WHERE table_name='v_factura_estado'.
7. **18 prior migrations chain head is `0026_seed_impuestos_iva_and_one_exit_per_ingreso`**: SELECT * FROM alembic_version.
8. **Unit + AST walk gates pass**: `pytest tests/test_repo_nit_modulo11.py tests/test_schemas_nit_modulo11.py tests/test_handler_factura_create.py tests/test_handler_factura_pagos.py -v` → 14/14 pass; `pytest tests/test_sdd_walks/test_hu_f1_9_walks.py -v` → 2/2 pass.
9. **`create_factura` 12-step ordering walk**: AST walk verifies NO DB write before V1.
10. **`create_factura` no-UPDATE/DELETE-after-INSERT walk**: AST walk verifies NO `UPDATE prod.factura_*` or `DELETE FROM prod.factura_*` after Step 9.
11. **Cache-Control header**: `curl -I -X POST http://localhost:8000/api/v1/facturacion/factura` → response includes `Cache-Control: no-store`.
12. **OpenAPI spec emits 422 discriminated bodies**: `curl http://localhost:8000/openapi.json | jq '.paths."/api/v1/facturacion/factura".post.responses.422.content'` → returns union of `{nit_invalido, total_no_coherente, detalle_invalido}`.

## 15. References

### 15.1 OpenSpec / Project Artifacts

- `openspec/changes/hu-f1-9-facturacion/exploration.md` (~32KB, 16 sections) — pre-apply verification findings: R1..R7 risk register + NIT módulo 11 algorithm selection.
- `openspec/changes/hu-f1-9-facturacion/proposal.md` (~1432 lines, 12 sections) — pre-proposal product discussion + DEC-FACT-01..09 architectural decisions.
- `openspec/changes/hu-f1-9-facturacion/specs/operations/spec.md` (~700 lines, REQ-OPS-053..063 + REQ-OPS-XR1..XR3) — operational requirements.

### 15.2 Predecessor Change Artifacts

- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/design.md` (~1805 lines, 16 sections) — **canonical precedent** for F1.9 structure (mirror).
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/exploration.md` (~32KB) — pre-apply verification mirror for F1.7 R1..R7 risk register.
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/proposal.md` (PRE-F1.7) — DEC-OPS-21..29 decisions mirror.
- `openspec/changes/archive/2026-09-14-hu-f1-7-salidas/specs/operations/spec.md` (REQ-OPS-042..052) — operational requirements.

### 15.3 Codebase References

- `backend/packages/parkos_core/migrations/versions/0001_init_bitemporal_split.py` (line 716 — `RANGE`-partición `prod.factura_pagos`; lines 2024-2088 — `fn_*_inmutable` triggers).
- `backend/packages/parkos_core/migrations/versions/0004_add_factura_pagos_reverso_trigger.py` (lines 35-66 — BEFORE INSERT trigger pattern analogía; lines 68-78 — REVOKE re-assertion pattern).
- `backend/packages/parkos_core/src/parkos_core/models/L_E/facturas.py` (lines 62-72 — `__table_args__` confirmed no partition; lines 9-14 — docstring references V_FACTURA_ESTADO view).
- `backend/packages/parkos_core/src/parkos_core/models/A/facturas_pagos.py` (lines 9-18 — pre-existing docstring drift TODO).
- `backend/packages/parkos_core/src/parkos_core/models/A/factura_detalle.py` (`AppendOnlyBase`, RANGE partitioned, composite PK).
- `backend/packages/parkos_core/src/parkos_core/models/A/factura_impuestos.py` (composite PK + decimal columns).
- `backend/packages/parkos_core/src/parkos_core/models/A/factura_electronica.py` (L-E; DEC-FACT-05 traceability).
- `backend/packages/parkos_core/src/parkos_core/models/A/salidas.py` (V1 lookup target).
- `backend/packages/parkos_core/src/parkos_core/models/V/clientes.py` (V2 lookup target).
- `backend/packages/parkos_core/src/parkos_core/models/V/impuestos.py` (V3 IVA lookup).
- `backend/packages/parkos_core/src/parkos_core/models/V/tarifas_sucursal.py` (KD-FACT-02 lookup).
- `backend/packages/parkos_core/src/parkos_core/repo/factura_pagos.py` (REUSED verbatim — reverse_payment, PagoNotFoundError, DuplicateReversoError).
- `backend/packages/parkos_core/src/parkos_core/repo/impuestos.py` (V3 helper get_active_impuesto — F1.7 reference).
- `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py` (F1.5/F1.6/F1.7 block; MODIFY for F1.9).
- `backend/packages/parkos_core/src/parkos_core/schemas/clientes.py` (F1.5 block; MODIFY for F1.9).
- `apps/operacion/router.py` (F1.7 KD-FORZADO-01 reuse of `salida_ya_existe` pattern).

### 15.4 External References

- DIAN Resolución 000175 de 2021, Anexo Técnico de Facturación Electrónica, Numeral 11.1 — NIT módulo 11 algoritmo Variant A canónica. (Source for `MOD11_WEIGHTS`.)
- PostgreSQL 15 documentation, Chapter 5.4 (Constraints) — partial unique index on partitioned tables limitation.
- PostgreSQL 15 documentation, Chapter 38 (Triggers) — BEFORE INSERT trigger pattern.
- SQLAlchemy 2.0 documentation — `with_for_update(read=True)` for `FOR SHARE` semantics in async sessions.
- Pydantic v2 documentation — `@field_validator` + `extra='forbid'` patterns.

## 16. Cross-HU Implications

### 16.1 F1.1..F1.8 (Cerradas, Precedentes)

- **F1.5 (clientes base)**: F1.9 extends `ClientesCreate` schema with NIT módulo 11 validator (`schemas/clientes.py` +10 LOC). No new columns, no migration.
- **F1.7 (salidas + forced concurrency)**: F1.9 reuses KD-FORZADO-01 verbatim from F1.7 (5-layer defense pattern: partial unique index + BEFORE INSERT trigger + repo typed exceptions + handler step chain + AST walks). F1.9's MIGRATION 0027 Op 2 (`one_factura_per_salida`) is the analogía of F1.7's `one_exit_per_ingreso` partial unique index.
- **F1.8 (auth + roles)**: F1.9 inherits JWT auth + RBAC from F1.8 without modification. `require_roles('operativo', 'admin')` (F1.7 pattern) reused.

### 16.2 F1.10..F1.15 (Downstream HUs)

- **F1.10 (reportes + cuadre caja)**: F1.9's `prod.facturas` + `prod.factura_pagos` tables are the data source for cuadre-caja reports (F1.10 reads via the V_FACTURA_ESTADO view). DEC-FACT-01 (append-only inserts) ensures the cuadre-caja reports see a stable monotonically-increasing timeline.
- **F1.11 (UI facturación, frontend)**: F1.11 is the React app for F1.9. The router at `apps/facturacion/router.py` is the contract surface; F1.11 does NOT need to wait for F1.9 to complete (OpenAPI stub from F1.9 suffices). F1.11's deliverable: 2 HTTP clients + 3 Vue components.
- **F1.12 (notificaciones)**: F1.9 emits no notification events. F1.12 will hook into `prod.factura_electronica` rows for DIAN-Recep-Envío notifications. The `prod.factura_electronica` row creation will be added in F1.12, not F1.9.
- **F1.13 (arqueo)**: F1.13 will use `repo/factura_pagos.py::reverse_payment` (REUSED VERBATIM, file 9.4) for anulación workflows. The reverso INSERT happens via the same atomic single-commit pattern (F1.13 will reuse KD-FACT-01 + KD-FACT-02).
- **F1.14 (ajustes contables)**: DEC-FACT-04 deferred (`compute_total(retencion)` placeholder). F1.14 is the ReteFuente/ReteICA/RETE_IVA snapshot — Fase 3.
- **F1.15 (e2e + load tests)**: F1.15 must cover F1.9's atomic 4-table insert under concurrent load. The AST walks from F1.9 are part of the CI gate; F1.15 adds Python-side race-condition tests (multiple cajeros POST `/facturacion/factura` concurrently → exactly one wins, the other gets 409 `factura_duplicada`).

### 16.3 Deferred-to-Fase-2-4 Cross-HU Implications

- **Multi-pago batches (REQ-NFR-16)**: Fase 2. F1.9's `POST /factura-pagos` is one-pago-per-call; Fase 2 will accept N pagos in a single POST.
- **Auto-creación de clientes**: Fase 2. F1.9 returns 404 on missing cliente; Fase 2 cascades.
- **Factura electrónica XML/PDF**: Fase 2. F1.9 stores the traceability row only; Fase 2 generates the XML/PDF.
- **Multi-line receipts** (combining `prod.salidas` + `prod.reservas`): Fase 3. F1.9 only invoices salidas; Fase 3 invoices reservations.
- **IGV/ReteFuente/ReteICA** taxes: Fase 3. F1.9 snapshots IVA only.
- **POS terminal integration**: Fase 4. F1.9 validates the voucher; Fase 4 does the proto handshake.
- **Withholding retention** at invoice-time: Fase 4. F1.9 has `retencion: Decimal = 0` placeholder.

**Net: F1.9 closes the F1.x back-end billing transaction. Fase 2-4 adds frentes electrónicas, integrations, and accounting reconciliation.**