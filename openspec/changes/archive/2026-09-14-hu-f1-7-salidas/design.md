# Design: HU-F1.7 — POST /operacion/salidas (rotación + mensualidad derivation)

> **Change**: `hu-f1-7-salidas`
> **Phase**: design (sdd-design)
> **HU**: HU-F1.7 — Server-side enforcement of `POST /operacion/salidas`: rotación vs mensualidad derivation, KD-FORZADO-01 bypass reusado de F1.6, KD-IVA inline-seed via MIGRATION 0026, tarifa vigente vía `prod.calcular_cotizacion` (PL/pgSQL F1.8 VOLATILE) con lock FOR SHARE continuo.
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `2a2cbd2`; F1.1..F1.6 cerradas, F1.8 cerrada, F1.7 en design)
> **PR target**: `origin/dev`
> **Source of truth**: `proposal.md` (D-HU-F1.7-1..20, 12 KDs adopted, 7 reconciliations DEC-SUC-21-NEW / DEC-SAL-01 / DEC-IMP-01 / DEC-IDEM-01 / DEC-FORZADO-01 / DEC-MONO-01 / DEC-SUC-23) + `exploration.md` (16 sections, V1..V5 + R1..R9, files-to-touch §16) + `specs/operational/spec.md` (REQ-OPS-042..052, 11 requirements in Given/When/Then/And form).
> **Cross-references**: `modelo_datos_er.mmd` (`prod.salidas` 761-777 [A], `prod.ingreso` 577-596 [L-E], `prod.impuestos` 187-207 [V], `prod.tarifas_sucursal` 406-426 [V], `prod.subscripciones_cliente` 496-518 [V], `prod.subscripcion_vehiculos` 538-557 [V], `prod.vehiculos` 519-537 [V], `prod.alert_types` [V], `prod.alerta` [L-W], `prod.anulaciones` [L-W]).
> **Precedents mirrored**: F1.6 (REQ-OPS-034..041, KD-FORZADO-01 verbatim reuse, KD-7 pre-flight DO $$ pattern, defense in depth 4-layer, AST walks for ordering gate, commit `2a2cbd2`), F1.8 (REQ-OPS-022..025, PL/pgSQL VOLATILE `calcular_cotizacion` + `FOR SHARE` lock continuity KD-1, KD-IVA resolver recipe, commit `a3d0c39`), F1.5 (REQ-OPS-030..033, MV pattern, MV stale data acceptance, commit `fc72adb`), F1.4 (REQ-OPS-017..021, bi-temporal predicate reusable in V2, commit `467b4f0`), F1.3 (REQ-OPS-026..029, partial unique index pattern + AST walk + pre-flight abort, commit `ca3f9bf`).

---

## 1. Title & Goal

**Design goal.** Deliver HU-F1.7: the back-end `POST /api/v1/operacion/salidas` endpoint that closes the exit half of CU-01/CU-02/CU-03M by enforcing 5 server-side validations V1..V5 plus the KD-FORZADO-01 bypass contract (reusado verbatim de F1.6), invoking `prod.calcular_cotizacion(:uuid_ingreso)` (PL/pgSQL F1.8 VOLATILE) inline within the same transaction to preserve the `FOR SHARE` lock continuity (KD-1 invariant from F1.8 design.md §6 Cross-HU), and deriving `tipo_salida = MENSUALIDAD | ROTACION` server-side from the `cobrar` flag returned by F1.8 (DEC-SUC-21-NEW analogue of DEC-SUC-21 for ingreso, value **never persisted** in `prod.salidas`). The design also ships **MIGRATION 0026** which (a) inline-seeds `prod.impuestos.IVA` (`porcentaje=0.19`) to unblock F1.8 deployment (KD-IVA blocker, F1.8 design.md §4 KD-IVA), (b) seeds 2 alert_types (`subscripcion_vencida_forzado` and `tarifa_vigente_forzado`, both `severity='warning'`) required by the alerta same-TX insertion on V2/V5 bypass (D-HU-F1.7-12), and (c) creates the partial unique index `one_exit_per_ingreso` on `prod.salidas (uuid_ingreso) WHERE NOT EXISTS (...)` to close the TOCTOU race window on V1 EXISTS subquery (DEC-SAL-01, KD-S16). The design enforces **DEC-MONO-01** (orchestrator consolidation: one handler instead of plan.md's two endpoints), **DEC-SAL-01** (salida never UPDATE post-creation; corrections via `prod.anulaciones(tipo_anulable='salida')` workflow, deferred to Fase 7+), and the **5-layer defense in depth** (D-HU-F1.7-7): regex/placa server-side → KD-FORZADO chain → alerta INSERT same-TX → AST walk ordering gate → partial unique index + REVOKE/IMMUTABLE. Closes three contractual dependencies: CU-02 (salida con cobro facturado), CU-03M (salida de mensualidad), and F8 facturación (HU-F1.9 reads `cotizacion_snapshot`). Sized at **220 LOC** (plan.md línea 835): ~200 LOC handler + 4 new `repo/*.py` modules (~320 LOC total) + schemas (+80 LOC) + 1 Alembic migration (~120 LOC) + 6 test files (~1,000 LOC). **One new endpoint, one new ORM model, one new migration, no factory changes, no sync catalog changes.**

## 2. Context & Background

`plan.md` lines **798-841** define HU-F1.7 as Fase-1 backend prerequisite for F7 (Salida post-flow). The hard architectural constraints are **DEC-SUC-21-NEW** (analog of DEC-SUC-21 for ingreso: `tipo_salida` never persisted as a column in `prod.salidas`; derived server-side from F1.8 `cobrar` flag and returned in `SalidaReadForzado`), **DEC-SUC-23** (`salidas` has no monto column; monto lives in `prod.factura_detalle`, ER 780-794), **DEC-SAL-01** (append-only `[A]` event; corrections via `prod.anulaciones(tipo_anulable='salida')` workflow, deferred to Fase 7+), **DEC-MONO-01** (orchestrator consolidation: one handler instead of plan.md's two endpoints), **DEC-IMP-01** (`impuestos.IVA` inline-seeded in MIGRATION 0026, apply of F1.7 advances the F1.8 KD-IVA blocker as a side effect, ownership remains HU-F14.2 Parte II), and the existing `prod.salidas` table that has existed since migration 0001 (líneas 571-591, partitioned monthly by `fecha_retencion_hasta`, with REVOKE UPDATE/DELETE at línea 2923 and trigger `fn_salidas_inmutable` at líneas 1990-2003) but has no ORM mapping — F1.7 closes this pre-existing gap with `models/L_S/salida.py`.

Today the URL `POST /api/v1/operacion/salidas` is **not registered** in the FastAPI router (`grep "POST.*salidas" backend/` → 0 matches confirmed in F1.8 exploration). The helper `resolve_active_subscription_for_exit` (T-PR5-016) already lives in `api/v1/operacion.py:500-562` since PR5 (extracted to `repo/subscripcion_activa.py` by F1.6), but no HTTP handler invokes it for the exit flow. The operator's screen at the parking lot accepts a vehicle at exit and POSTs to a non-existent endpoint, or relies on an undocumented internal procedure. **The backend performs zero business validation on salidas**, creating five concrete risks that HU-F1.7 resolves:

1. **Salida duplicada / cross-tenant bypass** — without server-side validation, a stale client or alternate consumer can submit the same `uuid_ingreso` twice and create two `prod.salidas` rows. The DB has REVOKE + trigger but no constraint preventing duplicate inserts.
2. **Tipo derivativo client-side** — `tipo_salida = MENSUALIDAD | ROTACION` is currently derived client-side; the corpus requires server-side derivation (DEC-SUC-21-NEW).
3. **KD-IVA blocker (F1.8 deployment)** — `impuestos.IVA` is not seeded in any migration 0001-0025 (`grep "INSERT INTO prod.impuestos"` → 0 matches confirmed in F1.8 exploration:56). Every cotización returns `500 iva_no_configurado`. F1.7's MIGRATION 0026 closes this blocker inline.
4. **Lock continuity gap** — F1.8 holds `SELECT … FOR SHARE` on `tarifas_sucursal` inside `calcular_cotizacion` (D-HU-F1.8-1, KD-1). If F1.7 invokes `calcular_cotizacion` in a different transaction from the INSERT into `salidas`, the lock is released between cotizar and registrar, opening a window where another TX closes the tariff.
5. **TOCTOU race on V1 EXISTS subquery** — two concurrent requests can both pass V1's "no salida for this ingreso" check and create duplicate salidas. The partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4) closes the window via `UniqueViolationError → 409 salida_duplicada`.

F1.7 consolidates the **two endpoints from plan.md** (`POST /operacion/salidas` rotación + `POST /operacion/salidas/mensualidad`) into **one handler** that derives `tipo_salida` server-side from F1.8's `cobrar` flag (DEC-MONO-01, orchestrator decision). This reduces surface area, reuses F1.8's atomic lock, and makes the client indifferent to the path.

The contract is captured in **REQ-OPS-042..052** (added by `sdd-spec` to `specs/operational/spec.md`):

- **REQ-OPS-042** — POST /operacion/salidas contract with KD-3 tenant scope.
- **REQ-OPS-043** — V1: ingreso activo exists; unified 404 discriminator.
- **REQ-OPS-044** — V2: subscripción vigente al momento salida (F1.6 reuse).
- **REQ-OPS-045** — V3: placa matches ingreso (F1.6 reuse).
- **REQ-OPS-046** — V4: KD-FORZADO-01 prefix contract (F1.6 verbatim reuse).
- **REQ-OPS-047** — V5: tarifa vigente via F1.8 PL/pgSQL; lock FOR SHARE continuity.
- **REQ-OPS-048** — INSERT `prod.salidas` `[A]` append-only via DEC-SAL-01.
- **REQ-OPS-049** — `tipo_salida` derived server-side; never persisted.
- **REQ-OPS-050** — alerta same-TX for V2/V5 bypass.
- **REQ-OPS-051** — partial unique index `one_exit_per_ingreso`; 409 mapping.
- **REQ-OPS-052** — inline-seed `impuestos.IVA`; KD-IVA blocker resolved.

F1.7 is consumed by **F8** (CU-02 Salida con cobro facturado, plan línea 798-810), **F9** (CU-03M Salida de mensualidad, plan línea 812-826), **HU-F1.9** (facturación: HU-F1.9 reads `prod.salidas` + `cotizacion_snapshot` to assemble `factura_detalle`, ER 780-794). It closes the server-side enforcement surface for salidas and leaves a clean separation between the lifecycle event (`prod.salidas`, append-only) and the fiscal breakdown (`cotizacion_snapshot` ephemeral + `factura_detalle` future).

## 3. Decisions

This HU adopts **twenty** Key Decisions (D-HU-F1.7-1..20 from `proposal.md §2`). Each one passes the R5 risk threshold (no open question blocks the design; the proposal §11 confirms `Sin preguntas abiertas`). The decisions are grouped into 7 themes: consolidation (D-HU-F1.7-1), persistence discipline (D-HU-F1.7-2..3), catalog seeds (D-HU-F1.7-4..5), bypass scope (D-HU-F1.7-6), concurrency (D-HU-F1.7-7), tenant + UX (D-HU-F1.7-8..11, D-HU-F1.7-19), schema design (D-HU-F1.7-12..16, D-HU-F1.7-20), idempotency + RBAC (D-HU-F1.7-17..18).

### Decision D-HU-F1.7-1 (DEC-MONO-01) — One handler `POST /api/v1/operacion/salidas` derives `tipo_salida` server-side

**Choice.** A single handler `POST /api/v1/operacion/salidas` registers on the existing `APIRouter` (no new module under `api/v1/`); the URL is brand new (not replacing an existing endpoint). The handler derives `tipo_salida = MENSUALIDAD | ROTACION` from the `cobrar` flag returned by `prod.calcular_cotizacion(:uuid_ingreso)` (F1.8 PL/pgSQL). NOT two endpoints (`/salidas` + `/salidas/mensualidad`) as originally proposed in `plan.md` lines 7438-7447.

**Context.** `plan.md` line 814 originally proposed two endpoints. The orchestrator consolidates to one (DEC-MONO-01, exploration §6): reduces surface area from 2 handlers to 1, reuses F1.8's atomic lock atómicamente (KD-1 invariant), makes the client indifferent to the path (sends `uuid_ingreso`, receives `tipo_salida`). The trade-off: clients lose the UI pre-classification toggle (operator UI may have "is this a mensualidad salida?" button); the server-side derivation is the new authority.

**Alternatives considered.**
- *Two endpoints `POST /operacion/salidas` + `POST /operacion/salidas/mensualidad`* — rejected: doubles handler count; the F1.8 lock would have to be acquired twice in different transactions; risk of inter-endpoint inconsistency when V5 (tarifa) is computed in one handler and the INSERT happens in another; not aligned with F1.6's DEC-SUC-21 pattern.
- *Single endpoint with client-provided `tipo_salida`* — rejected: defeats DEC-SUC-21-NEW; clients could lie about the tipo to skip alerta; no audit trail.
- *Single endpoint with payload discriminator `es_mensualidad: bool`* — rejected: leaks server-side logic; F1.8 already returns the discriminator; redundant client signal.

**Rationale.** One handler with server-side derivation is consistent with DEC-SUC-21 (F1.6) and the F1.8 contract (`cobrar:bool` is the discriminator). The handler is ~200 LOC, fits in `api/v1/operacion.py` adjacent to `create_ingreso` (lines 132-294) at lines ~296-510.

### Decision D-HU-F1.7-2 (DEC-SUC-21-NEW) — `tipo_salida` never persisted in `prod.salidas`

**Choice.** `tipo_salida = MENSUALIDAD | ROTACION` is derived server-side from the `cobrar` flag of `prod.calcular_cotizacion`, returned in `SalidaReadForzado.tipo_salida: Literal["MENSUALIDAD", "ROTACION"]`, and **NEVER persisted** in `prod.salidas`. The `prod.salidas` table has no `tipo_salida` column by design (4FN — analogue of DEC-SUC-21 for ingreso, F1.6).

**Context.** `modelo_datos_er.mmd` lines 761-777 define `prod.salidas` without a `tipo_salida` column. Adding it would create a derived-data redundancy: the source of truth is the F1.8 PL/pgSQL function which already encodes the decision (mensualidad vigente → `cobrar:false`; rotación → `cobrar:true` with fiscal breakdown). If a future HU needs direct query of `tipo_salida`, a view `V_SALIDA_TIPO` may be added; F1.7 does NOT create it (out of scope per proposal §3.2).

**Alternatives considered.**
- *Add `tipo_salida` column to `prod.salidas`* — rejected: 4FN violation; derived-data redundancy; one more column to maintain; F1.8 already returns the discriminator.
- *Add view `V_SALIDA_TIPO` with `cobrar` flag join* — rejected: out of scope for F1.7; not needed by F1.9 (which reads `cotizacion_snapshot` directly).

**Rationale.** The `tipo_salida` field in the response is the client's view of the same logic. Persisting it would create two sources of truth (the column AND the cotization response) that must be kept in sync.

### Decision D-HU-F1.7-3 (DEC-SAL-01) — `salidas` is append-only `[A]`; corrections via `prod.anulaciones`

**Choice.** `prod.salidas` is append-only. Corrections post-creation go through `prod.anulaciones(tipo_anulable='salida')` workflow (Fase 7+, deferred). Defense in depth at DB layer: REVOKE UPDATE, DELETE (migration 0001 línea 2923) + trigger `fn_salidas_inmutable` (líneas 1990-2003) + partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4) which allows a new salida IF the previous one was anulada (the `NOT EXISTS` predicate excludes anuladas from the index).

**Context.** Analogue of DEC-ANUL-01 for ingreso (F1.6). The DB already has REVOKE + trigger; F1.7 does not introduce new DB-level constraints. F1.7 closes the pre-existing TOCTOU race via the partial unique index (which is the only new schema object introduced by this HU).

**Alternatives considered.**
- *Allow UPDATE on `prod.salidas` for `motivo` correction* — rejected: defeats audit trail; `motivo` lives in `prod.alerta.datos_nuevos` when bypassed.
- *Implement anulación workflow in F1.7* — rejected: out of scope per proposal §3.2; deferred to Fase 7+.

**Rationale.** The DB-level constraints are already in place; F1.7's contribution is the partial unique index (KD-S16) which serves dual purpose: (a) TOCTOU race closure, (b) post-anulación re-creation pathway.

### Decision D-HU-F1.7-4 (DEC-IMP-01) — `impuestos.IVA` inline-seeded in MIGRATION 0026

**Choice.** `prod.impuestos.IVA` is inline-seeded in MIGRATION 0026 Op 2 via `INSERT … ON CONFLICT (codigo, vigente_desde) DO NOTHING` with `porcentaje=0.19` (IVA Colombia 2026 regulatory constant, locked in F1.8 design.md §4 KD-IVA). The seed advances the F1.8 KD-IVA blocker as a side effect of the F1.7 apply. Ownership of the `impuestos` catalog scope remains HU-F14.2 Parte II; F1.7's inline-seed is the chain head's deployment prerequisite.

**Context.** F1.8 documented KD-IVA as a deployment blocker: every cotización returns `500 iva_no_configurado` until `impuestos.IVA` is seeded (F1.8 design.md §4 KD-IVA, verify-report R1). F1.6 established the inline-seed pattern in MIGRATION 0025 (`INSERT … ON CONFLICT (tipo_alerta) DO NOTHING`). F1.7 mirrors it for `impuestos`. The exact recipe matches F1.8 design.md §4 KD-IVA `Exact seeding recipe`.

**Alternatives considered.**
- *Seed from a separate catalog migration (HU-F14.2 Parte II)* — rejected: blocks F1.8 deployment in all environments until HU-F14.2 ships; the seed is a 1-row operation that can safely live in MIGRATION 0026.
- *Hardcode `porcentaje=0.19` in Python* — rejected: violates "single source of truth in DB" (F1.8 design.md §4 KD-IVA rejected the same alternative).

**Rationale.** The inline-seed resolves the F1.8 deployment blocker with 6 lines of SQL and respects the established pattern from MIGRATION 0025.

### Decision D-HU-F1.7-5 (DEC-FORZADO-01 reuse) — KD-FORZADO-01 prefix contract reusado verbatim de F1.6

**Choice.** `repo/ingreso.py::validar_kd_forzado(observaciones, forzado) -> str | None` from F1.6 is **reusado verbatim** without modification. Same 422 discriminators (`motivo_forzado_requerido`, `forzado_contradiccion`, `motivo_forzado_insuficiente`); same `FORZADO_PREFIX = "[FORZADO: "` constant; same `FORZADO_MIN_MOTIVO_CHARS = 10` minimum.

**Context.** One implementation, one test, one audit trail. F1.6's 4 KD-FORZADO unit tests already cover the contract; F1.7 adds 2 more tests (`tests/unit/test_operacion_salidas_kd_forzado.py`) only to verify the contract still holds when invoked from the new salida path. No duplication.

**Alternatives considered.**
- *Re-implement KD-FORZADO-01 in `repo/salida.py`* — rejected: violates DRY; risk of contract drift between ingreso and income validations.
- *Extract to a shared `repo/forzado.py` module* — rejected: over-engineering for a 30-LOC helper; F1.6 keeps it in `repo/ingreso.py` and that's fine.

**Rationale.** Verbatim reuse is the simplest, lowest-risk path. The function signature `validar_kd_forzado(observaciones: str | None, forzado: bool) -> str | None` is payload-agnostic; the caller (handler) decides the alert context.

### Decision D-HU-F1.7-6 — Bypass scope narrower in F1.7 vs F1.6 (V2 and V5 only)

**Choice.** The KD-FORZADO-01 bypass applies to **V2 (subscripción vencida) and V5 (tarifa no vigente) ONLY**. NOT to V1 (ingreso activo), V3 (placa matches), or any other validation.

**Context.** V1 (ingreso activo) and V3 (placa matches) are correctness invariants — without an ingreso, there is nothing to close; placa mismatch is a bug or fraud attempt, not an operational state. V2 (subscripción) and V5 (tarifa) are operational state that may change between ingreso and salida (subscripción puede vencer; tarifa puede cerrar). The narrower scope aligns with the operational reality.

**Alternatives considered.**
- *Same bypass scope as F1.6 (V1+V2+V3+V6)* — rejected: V1 has no "vencido entre ingreso y salida" state; V3 has no operational meaning; bypassing them would allow nonsense exits.
- *Bypass all 5 validations* — rejected: defeats the validation purpose.

**Rationale.** The narrower scope matches the operational semantics. The F1.6 contract is reused; only the subset of validations it applies to changes.

### Decision D-HU-F1.7-7 (KD-S7 lock continuity) — `calcular_cotizacion` invoked inline within the same TX as the INSERT

**Choice.** `prod.calcular_cotizacion(:uuid_ingreso)` (F1.8 PL/pgSQL VOLATILE) is invoked **inside the same transaction** as the INSERT into `prod.salidas`. Single `await session.commit()`. NO sub-transactions. NO `SAVEPOINT`. NO `session.begin_nested()`.

**Context.** F1.8 PL/pgSQL is `VOLATILE` (REQ-OPS-025 deviation letter, user approved 2026-09-14). The `SELECT … FOR SHARE` lock on `tarifas_sucursal` acquired by F1.8 (KD-1 invariant from F1.8 design.md §6 Cross-HU) must remain held through the INSERT into `prod.salidas` and the INSERT into `prod.alerta` for atomicity. If `calcular_cotizacion` is invoked in a different transaction from the INSERT, the lock is released between cotizar and registrar, opening a window where another TX closes the tariff.

**Alternatives considered.**
- *Invoke `calcular_cotizacion` in a separate transaction (2 commits)* — rejected: breaks KD-1 lock continuity; F1.8 design.md §6 Cross-HU explicitly rejects this for F1.7.
- *Lock `tarifas_sucursal` from Python (asyncio.Lock + row-level)* — rejected: weaker than DB-level `FOR SHARE`; cannot span Python → PL/pgSQL boundary.

**Rationale.** Single TX is the only way to preserve the F1.8 KD-1 invariant. The handler structure mirrors F1.8's GET /cotizar pattern but extends to include the INSERT and the alerta.

### Decision D-HU-F1.7-8 (KD-S1 unified 404) — Single 404 discriminator for "no existe / ya cerrado / anulado"

**Choice.** `404 ingreso_no_encontrado` is the **single** response when `uuid_ingreso` doesn't exist, when the income already has a salida (not anulada), or when the income was anulado. The discriminator body carries `uuid_ingreso` for debugging but no internal state.

**Context.** Operational equivalence: in all three cases, there is nothing to close. A unified discriminator simplifies the error taxonomy and prevents information leak (a caller cannot distinguish "uuid never existed" from "uuid existed but is now closed" from "uuid was anulado" — useful for defense-in-depth against enumeration attacks).

**Alternatives considered.**
- *Distinct 404 discriminators (`ingreso_no_existe`, `ingreso_ya_cerrado`, `ingreso_anulado`)* — rejected: information leak; complicates error taxonomy; no operational value.
- *404 for "no existe" + 409 for "ya cerrado"* — rejected: 409 Conflict is for state transitions; the resource is closed, not conflicting.

**Rationale.** Unified 404 aligns with the F1.6 pattern (V8 returns 409 only when there is a conflict; "no active resource" is 404). The `ingreso_no_encontrado` body carries `uuid_ingreso` for debugging; the partial unique index (KD-S16) handles the "ya cerrado" race differently (409 `salida_duplicada`).

### Decision D-HU-F1.7-9 (KD-S2 tenant scope post-V1) — 404 before 403 (defense-in-depth)

**Choice.** Tenant scope check happens **after V1** (`404 ingreso_no_encontrado` first, then `403 tenant_scope_violation` if `operador-` with cross-branch ingreso). 404 before 403.

**Context.** If the operador doesn't have access to the uuid_ingreso, returning 403 before 404 leaks "the uuid exists somewhere". 404 first (no leak), then 403 if the ingreso exists. The 403 only fires if the ingreso exists AND the operador's JWT claims don't include its `uuid_sucursal`. This is a defense-in-depth control that F1.6 didn't need (F1.6 received `uuid_sucursal` in the payload and validated it pre-V1); F1.7 derives the sucursal from the ingreso (different shape, different ordering).

**Alternatives considered.**
- *403 before 404 (strict tenant isolation)* — rejected: information leak; UX worse (operador gets 403 even when the ingreso doesn't exist, which is confusing).

**Rationale.** 404-first aligns with the F1.6 pattern (V8 returns 409 after all other gates pass) and respects the corpus "single source of truth" rule (the resource is the ingreso, not the tenant claim).

### Decision D-HU-F1.7-10 (KD-S3 placa optional) — Placa in payload is optional; server trusts uuid_ingreso if absent

**Choice.** `placa: str | None = None` in `SalidaCreateForzado`. If provided, server confirms against `ingreso.placa` (V3). If absent, server trusts `uuid_ingreso` (server's authoritative uuid→placa mapping).

**Context.** Operator may know `uuid_ingreso` from a QR scan but not the placa. F1.7 follows the F1.6 pattern: server is the authority on uuid→placa mapping; client confirms only when it has additional context. The V3 check is a defense-in-depth against QR mis-scans (e.g., the operator scans a QR from a different vehicle's receipt).

**Alternatives considered.**
- *Placa required* — rejected: poor UX; the operator may not have visual access to the vehicle at the moment of exit.
- *Skip V3 entirely* — rejected: defense-in-depth gap; QR mis-scans go unnoticed.

**Rationale.** Optional with server-side confirmation is the optimal UX + security balance.

### Decision D-HU-F1.7-11 (KD-S4 cotizacion_snapshot scoped) — `cotizacion_snapshot` only when `tipo_salida=ROTACION`

**Choice.** `cotizacion_snapshot: CotizarFacturacion | None = None` in `SalidaReadForzado`. Populated when `tipo_salida=ROTACION`; `None` when `tipo_salida=MENSUALIDAD`.

**Context.** When `tipo_salida=MENSUALIDAD`, the operator's screen does not need the fiscal breakdown (no cobro). Returning a smaller response shape simplifies client logic (no "did they pay or not?" branching) and matches the business reality.

**Alternatives considered.**
- *Always include `cotizacion_snapshot`* — rejected: forces clients to ignore the field for MENSUALIDAD; larger response; no operational value.

**Rationale.** Conditional inclusion is the optimal contract: clients can switch on `tipo_salida` and access `cotizacion_snapshot` only when needed.

### Decision D-HU-F1.7-12 (KD-S5 distinct alerta types) — Two alert_types seeded in MIGRATION 0026 Op 3

**Choice.** Two NEW `alert_types` rows seeded in MIGRATION 0026 Op 3: `subscripcion_vencida_forzado` (only if V2 bypassed) and `tarifa_vigente_forzado` (only if V5 bypassed). Both `severity='warning'`. Inserted in **same TX** as the salida INSERT (one `await session.commit()`).

**Context.** Differentiated reporting without string concatenation. Defense against orphan alertas (R5): a single commit materializes salida + alerta atomically. One alerta per bypassed validation (V2 and V5 are mutually exclusive in practice — if both bypassed, the handler emits the most recent one, not both; documented in design §6).

**Alternatives considered.**
- *Single `forzado` alert_type for all bypasses* — rejected: loses granularity; manager cannot report on "subscripcion vs tarifa" separately.
- *String concat in `datos_nuevos` jsonb* — rejected: catalog-level discriminators are more indexable; UI queries filter on `tipo_alerta`.

**Rationale.** Two distinct types matches the operational semantics. The alert_type seed uses the same `ON CONFLICT (tipo_alerta) DO NOTHING` pattern as MIGRATION 0025.

### Decision D-HU-F1.7-13 (KD-S6 retención 2 años) — `fecha_retencion_hasta = fecha_salida + 2 years`

**Choice.** `fecha_retencion_hasta` is computed server-side as `date.today() + relativedelta(years=2)` (2 years operational retention from `fecha_salida`). Consistent with operational retention for other `[A]` tables (`anulaciones`, `reimpresion_ticket`). Enables monthly partitioning on `fecha_retencion_hasta`.

**Context.** `prod.salidas` is partitioned monthly by `fecha_retencion_hasta` (migration 0001 líneas 571-591). 2-year retention is the corpus standard. The date is computed in Python using `dateutil.relativedelta` (already a F1.4 dependency).

**Alternatives considered.**
- *Compute from `now()` instead of `fecha_salida`* — rejected: would shift the retention boundary each time the row is read; not idempotent.
- *3-year retention* — rejected: doubles storage cost; corpus specifies 2-year.

**Rationale.** 2-year from `fecha_salida` is the operational standard and aligns with the existing partition strategy.

### Decision D-HU-F1.7-14 — Reuse pre-existing `models/A/salidas.py::Salidas(AppendOnlyBase)` (~85 LOC, pre-existing since PR1a, complemented by `repo/salida.py`)

**Choice.** REUSE the pre-existing `models/A/salidas.py::Salidas(AppendOnlyBase)` (composite PK `uuid+fecha_retencion_hasta`, monthly `RANGE (fecha_retencion_hasta)` partition, pre-existing since PR1a). Do NOT create the originally-proposed `models/L_S/salida.py` based on `LifecycleEventBase`. The pre-existing model exposes exactly the columns the table has: `uuid` (server_default `gen_random_uuid()`), `fecha_retencion_hasta` (server_default `current_date()`), `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`. `__table_args__` includes the composite `PrimaryKeyConstraint("uuid", "fecha_retencion_hasta", name="salidas_pk")`. **Closes the pre-existing gap** by adopting the prior `[A]`-class ORM rather than creating a new `[L-S]` model.

**Context.** Defense-in-depth at the ORM layer (improved over the original proposal). The pre-existing `Salidas(AppendOnlyBase)` inherits the `__write_only__` ORM marker from `AppendOnlyBase`, which `tests/static/test_no_raw_dml_on_a_tables.py` reads to reject any `session.execute(update/delete)` against `salidas` outside `repo/append_only.py`. This is **superior** to the proposed `LifecycleEventBase`-derived model because it adds an AST-level DML rejection gate that the `[L-S]`-style class would not have inherited. The model is used for INSERT only — V1 (ingreso lookup) uses `select(Ingreso)` from F1.6's existing ORM. The model does NOT expose `tipo_salida` (DEC-SUC-21-NEW) or `forzado` or `motivo` columns.

**Alternatives considered.**
- *Original proposal — create `models/L_S/salida.py` based on `LifecycleEventBase`* — rejected at apply: the table already had a `[A]` ORM (`models/A/salidas.py`) since PR1a with composite PK + monthly partition; reusing it preserved defense-in-depth (REVOKE + `fn_salidas_inmutable` + `__write_only__` + AST walk DML rejection). Creating a parallel `[L_S]` model would have doubled the ORM surface for the same table.
- *Raw SQL for INSERT (no ORM)* — rejected: inconsistent with F1.5/F1.6; harder to test; loses the audit/sync mixin integration.
- *Add `tipo_salida` / `forzado` / `motivo` columns to the ORM* — rejected: DEC-SUC-21-NEW veda; KD-FORZADO-01 veda.

**Rationale.** Reuse the pre-existing `[A]`-class ORM with composite PK + monthly partition + `__write_only__` marker. INSERT-only via `repo/salida.py::crear_salida_evento`. The `repo/salida.py` module (~180 LOC, NEW) provides the 4 helpers and 1 typed exception, completing the chain.

### Decision D-HU-F1.7-15 — New `repo/salida.py` (~180 LOC) + `repo/impuestos.py` (~50 LOC)

**Choice.** `repo/salida.py` has 4 async helpers:
- `buscar_ingreso_activo_por_uuid(session, *, uuid_ingreso) -> Ingreso | None` (V1)
- `cotizar_para_salida(session, *, uuid_ingreso) -> dict[str, Any]` (V5 thin wrapper over F1.8)
- `crear_salida_evento(session, *, actor_uuid, new_attrs) -> Salida` (Step 8 INSERT + `IntegrityError → SalidaDuplicada`)
- `insertar_alerta_salida_forzado(session, *, uuid_sucursal, uuid_salida, actor_uuid, motivo, tipo_alerta)` (Step 9 alerta)

Plus typed exception `SalidaDuplicada(Exception)` for 409 mapping. `repo/impuestos.py` has `validar_iva_configurado(session) -> bool` (read helper for HU-F1.9 + HU-F14.2 audit + test mocks).

**Context.** Encapsulates SQL + bi-temporal predicates + lock boundaries; testable without HTTP; consistent with F1.6 `repo/ingreso.py` and F1.8 `repo/cotizacion.py`. Single import surface for the handler.

**Alternatives considered.**
- *Multiple files (`repo/v1_ingreso.py`, `repo/v5_cotizar.py`)* — rejected: bloats import surface; 4 functions in one module is clean.
- *Inline SQL in the handler* — rejected: violates F1.4/F1.5/F1.6/F1.8 pattern; not testable without HTTP.

**Rationale.** Single module per domain resource keeps the import surface tight.

### Decision D-HU-F1.7-16 (KD-V8 partial unique index) — `one_exit_per_ingreso` closes TOCTOU race

**Choice.** MIGRATION 0026 Op 4: `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso ON prod.salidas (uuid_ingreso) WHERE NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida = prod.salidas.uuid AND a.tipo_anulable = 'salida' AND a.estado = 'ejecutada')`. `CONCURRENTLY` for no lock on reads/writes; `IF NOT EXISTS` for idempotency.

**Context.** Same pattern as `unique_active_sesion_per_user` (migration 0023, F1.3). The `NOT EXISTS` clause excludes anuladas: once a salida is anulada, a new salida for the same `uuid_ingreso` becomes possible (the F1.9 facturación flow may need to re-create a salida if the first was anulada within the retention window). The `CONCURRENTLY` is required because production may have live SELECT/INSERT on `prod.salidas`.

**Alternatives considered.**
- *Simple `UNIQUE INDEX (uuid_ingreso)` (no WHERE clause)* — rejected: blocks re-creation post-anulación; F1.9 cannot recover from a wrong salida.
- *Pessimistic lock `FOR UPDATE` on `prod.ingreso` in V1* — rejected: serializes all exits; bursts of N operadores create queue; F1.8 design.md §6 Cross-HU doesn't propose this either.

**Rationale.** Partial unique index with `NOT EXISTS` excludes anuladas — the race window is closed AND the recovery pathway is preserved.

### Decision D-HU-F1.7-17 (DEC-IDEM-01 reuse) — Idempotency via `Idempotency-Key` HTTP header (PR2)

**Choice.** No `correlacion_id` in payload. Idempotency is handled by the existing `IdempotencyKeyMiddleware` (PR2, `api/deps.py`) reading the `Idempotency-Key` HTTP header.

**Context.** DEC-IDEM-01 from F1.6 applies equally to F1.7. Adding `correlacion_id` to the body would create two idempotency surfaces.

**Alternatives considered.**
- *Add `correlacion_id: uuid_lib.UUID | None` to body* — rejected: doubles surface; DEC-IDEM-01 veto.

**Rationale.** Header-based idempotency is the corpus pattern; F1.7 inherits verbatim.

### Decision D-HU-F1.7-18 (KD-V8 issuer parity) — Both `operador-` and `admin-` can emit `forzado=true`

**Choice.** No RBAC difference for `forzado=true`. The existing `_ingreso_issuer_dep = requires_issuer("operador-", "admin-")` accepts both issuers; the KD-FORZADO-01 contract applies uniformly.

**Context.** KD-V8 in F1.6 exploration §12 adopts issuer parity for MVP. The alerta `datos_nuevos` records `actor_uuid` for audit trail. If "solo admin-" is needed, the check is added in a future HU.

**Alternatives considered.**
- *RBAC differentiation (admin only)* — rejected: complicates MVP; the alert + log_transaccional hash chain already records who did what.

**Rationale.** Issuer parity simplifies MVP. The audit trail is the enforcement surface, not the RBAC layer.

### Decision D-HU-F1.7-19 — Schemas: `SalidaCreateForzado`, `SalidaReadForzado`, 4 typed errors

**Choice.** Add to `schemas/operacion.py` (~80 LOC):
- `SalidaCreateForzado` (input: `uuid_ingreso: UUID`, `placa: str | None`, `observaciones: str | None`, `forzado: bool = False`).
- `SalidaReadForzado` (output: existing `SalidaRead` fields + `tipo_salida: Literal["MENSUALIDAD", "ROTACION"]`, `forzado_en_creacion: bool`, `motivo_forzado: str | None`, `cotizacion_snapshot: CotizarFacturacion | None`).
- 4 typed errors: `IngresoNoEncontradoError`, `SalidaDuplicadaError`, `PlacaNoCoincideConIngresoError`, `TarifaVigenteNoEncontradaError`.

`extra='forbid'` (inherited from `_Base`) rejects extra fields including `tipo_salida` (DEC-SUC-21-NEW defense).

**Context.** Pydantic v2 typed discriminators (`Literal[...]`) lock the response contract. The 4 errors cover V1 (404), Step 8 (409), V3 (422), V5 (422).

**Alternatives considered.**
- *Generic `HTTPException(detail={"error": str})`* — rejected: not typed; clients cannot discriminate without string match.
- *One mega-schema with optional fields* — rejected: weakens the discriminator; clients cannot rely on field presence.

**Rationale.** 4 schemas mirror the 4 discriminators. `SalidaReadForzado` is the additive delta to `SalidaRead` (no field removed or renamed; additive only).

### Decision D-HU-F1.7-20 (D-HU-F1.7-20 strict order) — 12-step handler chain locked by AST walk

**Choice.** The handler invokes helpers in this literal order (verified by `tests/static/test_salida_handler_step_order.py`):

1. **Step 1** — KD-3 issuer claims + `no_store` headers.
2. **Step 2** — V1: `buscar_ingreso_activo_por_uuid` (404 if None).
3. **Step 3** — Tenant scope (post-V1): `target_sucursal = ingreso.uuid_sucursal`; 403 if `operador-` mismatch.
4. **Step 4** — V2: `validar_subscripcion_vigente` if `ingreso.uuid_subscripcion_cliente is not None`; 422 if not vigente without bypass; `bypass_reason = "subscripcion_vencida"` if forzado.
5. **Step 5** — V3: `detectar_tipo_vehiculo` on payload.placa AND ingreso.placa; 422 if mismatch.
6. **Step 6** — V4: `validar_kd_forzado` (F1.6 verbatim); sets `bypass_reason: str | None`.
7. **Step 7** — V5: `cotizar_para_salida` (calls F1.8 PL/pgSQL inline); raises `TarifaNoVigente` / `IVANoConfigurado`. Derives `tipo_salida`.
8. **Step 8** — INSERT salida via `crear_salida_evento`; `IntegrityError("one_exit_per_ingreso") → 409 SalidaDuplicada`.
9. **Step 9** — Alerta same-TX if `bypass_reason == "subscripcion_vencida" | "tarifa_no_vigente"`. Single `await session.commit()`.
10. **Step 10** — Derivación `tipo_salida` (DEC-SUC-21-NEW; documented for AST walk literal).
11. **Step 11** — `apply_no_store_header(response)` + `session.refresh(new_row)`.
12. **Step 12** — Return `SalidaReadForzado`.

The AST walk `tests/static/test_salida_handler_step_order.py` enforces this literal order. The order is intentional: V1 before tenant scope avoids info leak; V4 before V5 ensures the bypass contract is established before the tarifa is evaluated; Step 8 (INSERT) before Step 9 (alerta) ensures the FK ordering (alerta.uuid_salida references salida.uuid, populated after the salida INSERT).

**Context.** Defense-in-depth: V1 antes que tenant scope evita leak de existencia; V4 antes que V5 evita bypass por tarifa inválida; Step 8 al final garantiza rechazo de duplicado solo después de pasar todo lo demás.

**Alternatives considered.**
- *Parallel validation (asyncio.gather)* — rejected: complicates the bypass contract (KD-FORZADO-01); sequential is easier to reason about and matches the 422 precedence.
- *Reverse order (V8 first)* — rejected: a duplicate with bad placa would be reported as "salida_duplicada" instead of "placa_formato_invalido" — operator can't see the real error.

**Rationale.** Sequential validation with explicit ordering is the cleanest abstraction. The AST walk is a CI gate that locks the order against future-dev reordering.

## 4. Architecture Overview

```
HTTPS POST /api/v1/operacion/salidas
        Body: SalidaCreateForzado
        │      {uuid_ingreso, placa?, observaciones?, forzado?: bool = false}
        │  Idempotency-Key: <uuid>   (header, PR2 middleware)
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/operacion.py  (MODIFICAR, add create_salida lines ~296-510)           │
│                                                                              │
│ @router.post("/salidas", response_model=SalidaReadForzado, status_code=201) │
│ async def create_salida(payload, response, session, ctx, _claims)           │
│                                                                              │
│  1. KD-3 issuer claims + no_store headers (Step 1)                          │
│  2. V1 buscar_ingreso_activo_por_uuid (Step 2 → 404)                         │
│  3. Tenant scope post-V1 (Step 3 → 403)                                     │
│  4. V2 validar_subscripcion_vigente if applicable (Step 4)                   │
│  5. V3 detectar_tipo_vehiculo x 2 (Step 5 → 422)                            │
│  6. V4 validar_kd_forzado (Step 6 → bypass_reason)                          │
│  7. V5 cotizar_para_salida → F1.8 PL/pgSQL inline (Step 7)                  │
│       └── tipo_salida derived (DEC-SUC-21-NEW)                              │
│  8. INSERT prod.salidas [A] (Step 8 → 409 on index violation)               │
│  9. alerta same-TX if V2/V5 bypassed (Step 9) + single commit()             │
│ 10. tipo_salida documented for AST walk (Step 10)                           │
│ 11. response shape + session.refresh (Step 11)                              │
│ 12. return 201 SalidaReadForzado (Step 12)                                  │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                            ▲                       ▲
        │ AST walk                   │ AST walk              │ SELECT-only
        │ ordering gate              │ no-write gate         │ (FOR SHARE on
        │                            │                       │  tarifas_sucursal)
tests/static/test_salida_handler_step_order.py
tests/static/test_no_write_after_salida_insert.py
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Repo helpers (NEW):                                                         │
│   repo/salida.py              (180 LOC) — V1 + V5 wrapper + INSERT + alerta│
│   repo/impuestos.py           (50 LOC) — validar_iva_configurado            │
│                                                                              │
│ Repo helpers (REUSED verbatim, NO modify):                                  │
│   repo/ingreso.py             (F1.6) — validar_kd_forzado (V4)             │
│   repo/subscripcion_activa.py (F1.6) — validar_subscripcion_vigente (V2)    │
│   repo/cotizacion.py          (F1.8) — cotizar_ingreso (V5 wrapper)            │
│   repo/placa.py               (F1.6) — detectar_tipo_vehiculo (V3)          │
│   repo/alerta.py              (F1.6) — insertar_alerta_forzado (pattern)     │
│                                                                              │
│ ORM model (NEW):                                                            │
│   models/L_S/salida.py        (40 LOC) — LifecycleEventBase + sync mixins   │
│                                                                              │
│ Tablas operacionales (READ + INSERT, MIGRATION 0026 introduces index/seed):│
│   prod.ingreso                  [L-E]  — V1 read PK + placa + fecha_ingreso │
│   prod.salidas                  [A]    — Step 8 INSERT [A] append-only       │
│   prod.subscripciones_cliente   [V]    — V2 revalidate (F1.6 helper)         │
│   prod.subscripcion_vehiculos   [V]    — V2 junction (F1.6 helper)           │
│   prod.vehiculos                [V]    — V3 via placa (F1.6 helper)          │
│   prod.tarifas_sucursal         [V]    — V5 SELECT FOR SHARE (F1.8 KD-1)     │
│   prod.impuestos                [V]    — V5 read IVA% (post-0026 seeded)    │
│   prod.alert_types              [V]    — MIGRATION 0026 Op 3 seeds 2 types  │
│   prod.alerta                   [L-W] — Step 9 INSERT V2/V5 bypassed        │
│   prod.anulaciones              [V]    — V1/V8 EXISTS NOT EXCLUDED          │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲
        │
        ▼ MIGRATION 0026 (4 operations, applied BEFORE F1.7 tests)
┌──────────────────────────────────────────────────────────────────────────────┐
│ migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py     │
│                                                                              │
│ Op 1 — Pre-flight DO $$ (KD-7 pattern F1.6):                                │
│   verify prod.impuestos, prod.salidas, prod.alert_types exist               │
│   RAISE EXCEPTION '0026_preflight_abort: ...' if missing                    │
│                                                                              │
│ Op 2 — Inline-seed impuestos.IVA (KD-IVA resolver):                         │
│   INSERT INTO prod.impuestos (uuid, codigo, nombre, porcentaje,             │
│                                vigente_desde, vigente_hasta, estado,         │
│                                created_at)                                  │
│   VALUES (gen_random_uuid(), 'IVA', 'IVA', 0.19,                            │
│           NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW())                  │
│   ON CONFLICT (codigo, vigente_desde) DO NOTHING;                           │
│                                                                              │
│ Op 3 — Inline-seed 2 alert types (F1.7 alerts):                             │
│   INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)         │
│   VALUES                                                                    │
│       ('subscripcion_vencida_forzado',                                       │
│        'Salida vehicular forzada por administrador al detectar subscripción │
│         vencida al momento de salida', 'warning'),                          │
│       ('tarifa_vigente_forzado',                                            │
│        'Salida vehicular forzada por administrador al detectar tarifa no    │
│         vigente al momento de salida', 'warning')                            │
│   ON CONFLICT (tipo_alerta) DO NOTHING;                                     │
│                                                                              │
│ Op 4 — Partial unique index one_exit_per_ingreso (KD-S16):                  │
│   CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso       │
│       ON prod.salidas (uuid_ingreso)                                        │
│       WHERE NOT EXISTS (                                                    │
│           SELECT 1 FROM prod.anulaciones a                                   │
│           WHERE a.uuid_salida = prod.salidas.uuid                           │
│             AND a.tipo_anulable = 'salida'                                   │
│             AND a.estado = 'ejecutada'                                       │
│       );                                                                    │
│                                                                              │
│ Downgrade (reverse order):                                                  │
│   DROP INDEX IF EXISTS prod.one_exit_per_ingreso;                           │
│   DELETE FROM prod.alert_types WHERE tipo_alerta IN                          │
│       ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado');            │
│   DELETE FROM prod.impuestos WHERE codigo='IVA' AND estado='activo';         │
└──────────────────────────────────────────────────────────────────────────────┘
```

The handler is thin + orchestador. All validation logic lives in `repo/*.py` and PL/pgSQL. The single `commit()` materializes the salida + alerta atomically and releases the `FOR SHARE` lock from F1.8's `calcular_cotizacion` (KD-S7).

## 5. Data Model

**One Alembic migration introduces** the partial unique index + seeds 3 rows (1 impuesto + 2 alert_types). No columns added or removed in any operational table.

| Tabla | Tipo | Operación | Línea ER / migration |
|---|---|---|---|
| `prod.ingreso` | `[L-E]` | V1 SELECT (read-only) | 577-596 |
| `prod.salidas` | `[A]` | Step 8 INSERT (append-only) | 761-777 |
| `prod.salidas` | `[A]` | (Op 4) partial unique index | 761-777 |
| `prod.subscripciones_cliente` | `[V]` | V2 SELECT | 496-518 |
| `prod.subscripcion_vehiculos` | `[V]` | V2 junction | 538-557 |
| `prod.vehiculos` | `[V]` | V3 via placa | 519-537 |
| `prod.tarifas_sucursal` | `[V]` | V5 SELECT FOR SHARE | 406-426 |
| `prod.impuestos` | `[V]` | V5 read `nombre='IVA'` (post-0026) | 187-207 |
| `prod.impuestos` | `[V]` | (Op 2) INSERT new row `codigo='IVA'` | — |
| `prod.alert_types` | `[V]` | (Op 3) INSERT 2 new rows | — |
| `prod.alerta` | `[L-W]` | Step 9 INSERT (V2/V5 bypassed) | 952-974 |

**Columns read (no DDL)**:

| Tabla | Columna | Lectura |
|---|---|---|
| `prod.ingreso` | `uuid`, `uuid_sucursal`, `placa`, `uuid_tipo_vehiculo`, `uuid_subscripcion_cliente`, `fecha_ingreso` | V1 SELECT |
| `prod.subscripciones_cliente` | `fecha_vencimiento`, `estado`, `vigente_hasta` | V2 SELECT |
| `prod.tarifas_sucursal` | `vigente_desde`, `vigente_hasta`, `estado`, `valor`, `valor_plena` | V5 SELECT FOR SHARE |
| `prod.impuestos` | `nombre='IVA'`, `porcentaje` | V5 SELECT (post-0026) |
| `prod.salidas` | `uuid`, `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`, `fecha_retencion_hasta`, `created_at`, `created_by`, `sync_*` | Step 8 INSERT |

**Columns written (Step 8 INSERT only)**:

| Tabla | Columna | Valor |
|---|---|---|
| `prod.salidas` | `uuid` | DB default `gen_random_uuid()` |
| `prod.salidas` | `uuid_sucursal` | `ingreso.uuid_sucursal` (server-derived) |
| `prod.salidas` | `uuid_ingreso` | `payload.uuid_ingreso` |
| `prod.salidas` | `fecha_salida` | `datetime.now(UTC).replace(tzinfo=None)` |
| `prod.salidas` | `fecha_retencion_hasta` | `date.today() + relativedelta(years=2)` |
| `prod.salidas` | `created_at` | `datetime.now(UTC).replace(tzinfo=None)` |
| `prod.salidas` | `created_by` | `ctx.actor_uuid` |
| `prod.salidas` | `sync_status` | (default) |
| `prod.salidas` | `sync_timestamp` | (default NULL) |
| `prod.salidas` | `sync_attempts` | (default 0) |

**No column added for `tipo_salida`, `forzado`, `motivo`** — DEC-SUC-21-NEW veda `tipo_salida` columna; KD-FORZADO-01 veda `forzado`/`motivo` columnas. The motivo lives in `prod.alerta.datos_nuevos` (jsonb, added by MIGRATION 0025 in F1.6) when bypassed. The `tipo_salida` is returned in the response only.

**Sync catalog impact**: zero changes. The `salidas` table is `[A]` (audit), not synced to cloud (same as `anulaciones`, `reimpresion_ticket`). New alert_types rows are `[V]` reference data; if HU-F14.2 Parte II sync covers `alert_types`, the seeded rows propagate via the existing sync pipeline.

## 6. API Contracts

### `POST /api/v1/operacion/salidas` (NEW)

**Request signature**:

```python
async def create_salida(
    response: Response,
    payload: SalidaCreateForzado,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> SalidaReadForzado:
```

**Body `SalidaCreateForzado`** (Pydantic v2, `extra='forbid'`):

```python
class SalidaCreateForzado(_Base):
    """INSERT payload for ``prod.salidas`` ([A] append-only event, HU-F1.7).

    Identifies the ingreso to close. Sucursal is resolved server-side from
    the ingreso (NEW in F1.7 — client does not send). Placa is optional:
    if sent, server confirms against ingreso (V3); otherwise server trusts
    ``uuid_ingreso``.

    ``extra='forbid'`` (inherited from ``_Base``) rejects extra fields,
    including attempts to inject ``tipo_salida`` (DEC-SUC-21-NEW).
    """
    uuid_ingreso: uuid_lib.UUID         # REQUIRED — ingreso to close
    placa: str | None = None            # OPTIONAL — V3 confirmation
    observaciones: str | None = None    # OPTIONAL — KD-FORZADO-01 prefix
    forzado: bool = False               # OPTIONAL — bypass V2/V5
```

**Response `SalidaReadForzado`** (201, Pydantic v2):

```python
class SalidaReadForzado(_Base):
    """Response shape for ``POST /operacion/salidas`` (HU-F1.7).

    Additive delta to ``SalidaRead`` (no field removed or renamed):
    - ``tipo_salida``: Literal['MENSUALIDAD', 'ROTACION'] (DEC-SUC-21-NEW)
    - ``forzado_en_creacion``: True iff KD-FORZADO-01 bypass was used
    - ``motivo_forzado``: stripped motivo, or None
    - ``cotizacion_snapshot``: CotizarFacturacion if ROTACION, None if MENSUALIDAD
    """
    # Inherited from SalidaRead (10 columns):
    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_ingreso: uuid_lib.UUID | None
    fecha_salida: datetime | None
    # NEW (F1.7):
    tipo_salida: Literal["MENSUALIDAD", "ROTACION"]
    forzado_en_creacion: bool = False
    motivo_forzado: str | None = None
    cotizacion_snapshot: CotizarFacturacion | None = None
```

**Headers**: `Cache-Control: no-store` (consistent with F1.3/F1.5/F1.6/F1.8 precedents).

**Error discriminators** (typed HTTPException details):

| HTTP | Body | Cuándo | KD |
|---|---|---|---|
| 400 | `{"error":"missing_sucursal_context"}` | unlikely (server resolves from income) | KD-3 |
| 403 | `{"error":"tenant_scope_violation","uuid_ingreso":"..."}` | `operador-` with `ingreso.uuid_sucursal != ctx.sucursal_uuid` | KD-S2 (post-V1) |
| 404 | `{"error":"ingreso_no_encontrado","uuid_ingreso":"..."}` | V1: uuid no existe, ya tiene salida, o fue anulado | KD-S1 (unified) |
| 409 | `{"error":"salida_duplicada","uuid_ingreso":"..."}` | partial unique index `one_exit_per_ingreso` violated | KD-S16 |
| 422 | `{"error":"placa_no_coincide_con_ingreso","placa_request":"...","placa_ingreso":"..."}` | V3: optional placa mismatch | V3 |
| 422 | `{"error":"motivo_forzado_requerido"}` | `forzado=true` sin prefijo `[FORZADO: …]` | KD-FORZADO-01 |
| 422 | `{"error":"forzado_contradiccion"}` | `forzado=false` con prefijo | KD-FORZADO-01 |
| 422 | `{"error":"motivo_forzado_insuficiente","min_chars":10}` | motivo <10 chars tras prefijo | KD-FORZADO-01 |
| 422 | `{"error":"subscripcion_inactiva_o_vencida"}` | V2: subscripción `fecha_vencimiento < NOW()` o `estado='inactivo'` (sin forzado) | V2 |
| 422 | `{"error":"tarifa_vigente_no_encontrada"}` | V5: F1.8 returned `error:tarifa_no_vigente` (sin forzado) | V5 |
| 500 | `{"error":"iva_no_configurado"}` | V5: F1.8 returned `error:iva_no_configurado` (post-0026 deploy: never; pre-0026: blocked) | KD-IVA (D-HU-F1.7-4) |
| 201 | `SalidaReadForzado` with `tipo_salida`, `forzado_en_creacion`, `motivo_forzado`, `cotizacion_snapshot` | happy path | — |

**Sin cambios sobre**:
- `POST /operacion/ingresos` (F1.6)
- `GET /operacion/ingresos/{uuid}` (F1.5)
- `GET /operacion/ingresos/{uuid}/estado` (F1.5)
- `GET /operacion/ingresos` (F1.5 list)
- `GET /operacion/ocupacion` (F1.5)
- `GET /operacion/cotizar?uuid_ingreso` (F1.8)

## 7. Handler Skeleton

**Path**: `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (modify, add lines ~296-510, ~200 LOC).

The handler is registered on the existing `APIRouter` (no new module added under `api/v1/`); the decorator `@router.post("/salidas")` is adjacent to `@router.post("/ingresos")` (line 132) and shares the dependency chain. The 12-step sequence (D-HU-F1.7-20) is enforced by the AST walk `tests/static/test_salida_handler_step_order.py`.

```python
# backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py
# (ADD create_salida after create_ingreso, lines ~296-510)


@router.post(
    "/salidas",
    response_model=SalidaReadForzado,
    status_code=201,
    summary=(
        "HU-F1.7 / REQ-OPS-042..052: validated register of a vehicle exit "
        "(salida, [A] append-only) with tipo_salida server-side derivation."
    ),
    responses={
        400: {"description": "missing_sucursal_context"},
        403: {"description": "tenant_scope_violation (operador)"},
        404: {"description": "ingreso_no_encontrado (V1)"},
        409: {"description": "salida_duplicada (partial unique index)"},
        422: {
                "description": (
                    "placa_no_coincide_con_ingreso (V3) | "
                    "motivo_forzado_requerido (KD-FORZADO-01) | "
                    "forzado_contradiccion (KD-FORZADO-01) | "
                    "motivo_forzado_insuficiente (KD-FORZADO-01) | "
                    "subscripcion_inactiva_o_vencida (V2) | "
                    "tarifa_vigente_no_encontrada (V5)"
                )
            },
        500: {"description": "iva_no_configurado (KD-IVA, post-0026: never)"},
    },
)
async def create_salida(
    payload: SalidaCreateForzado,
    response: Response,
    session: AsyncSession = Depends(get_session),  # noqa: B008
    ctx: TenantContext = Depends(get_tenant_ctx),  # noqa: B008
    _claims: None = Depends(_ingreso_issuer_dep),
) -> SalidaReadForzado:
    """REQ-OPS-042..052: validated vehicle exit, [A] event.

    Dependency chain (same as create_ingreso, F1.6):
        _ingreso_issuer_dep   -> requires_issuer("operador-", "admin-")
        get_tenant_ctx        -> TenantContext { actor_uuid, sucursal_uuid, ... }
        get_session           -> AsyncSession (request-scoped)

    Sequence (D-HU-F1.7-20 12-step chain, locked by AST walk):
        1. KD-3 issuer claims + no_store headers
        2. V1 ingreso activo exists (404 if None)
        3. tenant scope post-V1 (403 if operador cross-branch)
        4. V2 subscripción vigente al momento salida (422 if not bypassed)
        5. V3 placa matches ingreso (422 if mismatch)
        6. V4 KD-FORZADO-01 prefix contract (sets bypass_reason)
        7. V5 tarifa vigente via F1.8 PL/pgSQL (derives tipo_salida)
        8. INSERT prod.salidas [A] (409 on partial unique index)
        9. alerta same-TX if V2/V5 bypassed + single commit() (KD-S7)
       10. tipo_salida documented for AST walk literal
       11. response shape + session.refresh
       12. return 201 SalidaReadForzado

    Lock continuity (KD-S7, KD-1 from F1.8): the prod.calcular_cotizacion
    call in Step 7 acquires SELECT ... FOR SHARE on tarifas_sucursal.
    The lock is held through Step 8 (INSERT salida) and Step 9 (alerta
    INSERT). Released at session.commit() in Step 9. NO sub-transactions,
    NO SAVEPOINT (KD-S7 invariant).

    The Idempotency-Key header is checked by the FastAPI middleware
    (PR2 IdempotencyKeyMiddleware).
    """
    no_store = no_store_headers()

    # --- Step 1: KD-3 (issuer claims + no_store). ----------------------
    # Resolved via dependency injection; no client-supplied sucursal
    # (server derives from ingreso.uuid_sucursal in Step 3).

    # --- Step 2: V1 (ingreso activo exists). ----------------------------
    ingreso = await buscar_ingreso_activo_por_uuid(
        session, uuid_ingreso=payload.uuid_ingreso
    )
    if ingreso is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "ingreso_no_encontrado",
                "uuid_ingreso": str(payload.uuid_ingreso),
            },
            headers=no_store,
        )

    # --- Step 3: tenant scope (post-V1, KD-S2). ------------------------
    target_sucursal = ingreso.uuid_sucursal
    if (
        ctx.issuer_prefix == "operador-"
        and (ctx.sucursal_uuid is None or target_sucursal != ctx.sucursal_uuid)
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tenant_scope_violation",
                "uuid_ingreso": str(payload.uuid_ingreso),
            },
            headers=no_store,
        )

    # --- Step 4: V2 (subscripcion vigente al momento salida). -----------
    bypass_reason: str | None = None
    if ingreso.uuid_subscripcion_cliente is not None:
        sub_result = await validar_subscripcion_vigente(
            session,
            uuid_subscripcion_cliente=ingreso.uuid_subscripcion_cliente,
            forzado=payload.forzado,
        )
        if not sub_result.vigente:
            if not payload.forzado:
                raise HTTPException(
                    status_code=422,
                    detail={"error": "subscripcion_inactiva_o_vencida"},
                    headers=no_store,
                )
            bypass_reason = "subscripcion_vencida"

    # --- Step 5: V3 (placa matches ingreso). ---------------------------
    if payload.placa is not None:
        tipo_req = await detectar_tipo_vehiculo(session, payload.placa)
        tipo_ing = await detectar_tipo_vehiculo(session, ingreso.placa or "")
        if tipo_req != tipo_ing:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "placa_no_coincide_con_ingreso",
                    "placa_request": payload.placa,
                    "placa_ingreso": ingreso.placa,
                },
                headers=no_store,
            )

    # --- Step 6: V4 KD-FORZADO-01 prefix contract (F1.6 verbatim). -----
    motivo = validar_kd_forzado(payload.observaciones, payload.forzado)
    if motivo is not None and bypass_reason is None:
        bypass_reason = "forzado"  # generic bypass reason for V5 only

    # --- Step 7: V5 tarifa vigente via F1.8 PL/pgSQL inline. -----------
    try:
        cotizacion = await cotizar_para_salida(
            session, uuid_ingreso=payload.uuid_ingreso
        )
    except TarifaNoVigente:
        if not bypass_reason:
            raise HTTPException(
                status_code=422,
                detail={"error": "tarifa_vigente_no_encontrada"},
                headers=no_store,
            )
        bypass_reason = "tarifa_no_vigente"
        cotizacion = {"cobrar": True}  # placeholder for snapshot shape
    except IVANoConfigurado:
        # KD-IVA — post-0026 deploy: never; pre-0026: blocked.
        raise HTTPException(
            status_code=500,
            detail={"error": "iva_no_configurado"},
            headers=no_store,
        )

    # Derive tipo_salida from F1.8's cobrar flag (DEC-SUC-21-NEW):
    tipo_salida: Literal["MENSUALIDAD", "ROTACION"] = (
        "MENSUALIDAD" if cotizacion.get("cobrar") is False else "ROTACION"
    )

    # --- Step 8: INSERT salida [A] append-only (DEC-SAL-01). ----------
    new_attrs = {
        "uuid_sucursal": target_sucursal,
        "uuid_ingreso": payload.uuid_ingreso,
        "fecha_salida": datetime.now(UTC).replace(tzinfo=None),
        "fecha_retencion_hasta": date.today() + relativedelta(years=2),
    }
    try:
        new_row = await crear_salida_evento(
            session,
            actor_uuid=ctx.actor_uuid,
            new_attrs=new_attrs,
        )
    except SalidaDuplicada:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "salida_duplicada",
                "uuid_ingreso": str(payload.uuid_ingreso),
            },
            headers=no_store,
        )

    # --- Step 9: alertas same-TX (KD-S12, R5) + single commit(). ------
    if bypass_reason == "subscripcion_vencida":
        await insertar_alerta_salida_forzado(
            session,
            uuid_sucursal=target_sucursal,
            uuid_salida=new_row.uuid,
            actor_uuid=ctx.actor_uuid,
            motivo=motivo or "(sin motivo)",
            tipo_alerta="subscripcion_vencida_forzado",
        )
    elif bypass_reason == "tarifa_no_vigente":
        await insertar_alerta_salida_forzado(
            session,
            uuid_sucursal=target_sucursal,
            uuid_salida=new_row.uuid,
            actor_uuid=ctx.actor_uuid,
            motivo=motivo or "(sin motivo)",
            tipo_alerta="tarifa_vigente_forzado",
        )
    await session.commit()  # UN solo commit (KD-S7 lock release)

    # --- Step 10: derivar tipo_salida (DEC-SUC-21-NEW). ----------------
    # Already derived in Step 7. Documented here for AST walk literal.

    # --- Step 11: response shape. -------------------------------------
    apply_no_store_header(response)
    await session.refresh(new_row)
    base = SalidaRead.model_validate(new_row).model_dump()
    return SalidaReadForzado(
        **base,
        tipo_salida=tipo_salida,  # type: ignore[arg-type]
        forzado_en_creacion=bypass_reason is not None,
        motivo_forzado=motivo if bypass_reason else None,
        cotizacion_snapshot=(
            CotizarFacturacion.model_validate(cotizacion)
            if tipo_salida == "ROTACION"
            else None
        ),
    )
    # --- Step 12: 201 SalidaReadForzado. ------------------------------
```

**Notes.**

- The handler is **registered on the existing `APIRouter`** (no new module added under `api/v1/`); the decorator `@router.post("/salidas")` is adjacent to `@router.post("/ingresos")` (line 132). The dependency chain `_ingreso_issuer_dep → get_tenant_ctx → get_session` is **verbatim** from `create_ingreso`. No new dependency factories.
- All repo helpers are imported from `parkos_core.repo.{salida, placa, subscripcion_activa, cotizacion, alerta, impuestos}`. The handler does not write SQL inline.
- The `bypass_reason` discriminator is a string literal refined through 3 states: `None` (no bypass), `"forzado"` (generic, before V5 evaluation), `"subscripcion_vencida"` (V2 bypass), `"tarifa_no_vigente"` (V5 bypass). The V2/V5 cases are mutually exclusive in the handler (V2 is checked first; if it fires, V5 is bypassed for alerta purposes but the tarifa is still evaluated for snapshot).
- `await session.commit()` happens exactly once, AFTER the optional alerta INSERT (R5 mitigation: no orphaned alerts). The `FOR SHARE` lock from F1.8 PL/pgSQL is released at this commit (KD-S7).
- The `forzado_contradiccion` and `motivo_forzado_requerido` / `motivo_forzado_insuficiente` 422 paths are raised INSIDE `validar_kd_forzado` (Step 6), before V5. The handler does not catch them — they propagate to FastAPI's default exception handler.
- The `extra='forbid'` on `_Base` rejects extra fields; clients sending `tipo_salida` (an attempt to inject a column that doesn't exist) are rejected with 422 before the handler runs.
- **FK ordering**: `prod.alerta` has no FK constraint to `prod.salidas` (alerts are independent events keyed by `uuid_sucursal` + `uuid_usuario`); Step 9 INSERT of the alerta can happen in any order relative to Step 8 INSERT of the salida. However, the alerta `datos_nuevos` jsonb carries `{"motivo": ..., "uuid_salida": str(new_row.uuid)}` — populated AFTER `session.flush()` of the salida (so `new_row.uuid` is the DB-generated UUID). The FK ordering is: (a) Step 8 INSERT + flush, (b) Step 9 alerta INSERT (reads `new_row.uuid` from the flushed row), (c) Step 9 single commit.

## 8. Migration 0026 — Complete DDL

**Path**: `backend/packages/parkos_core/migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py` (~120 LOC).

```python
"""HU-F1.7 / MIGRATION 0026 — KD-IVA resolver + 2 alert_types seed + partial
unique index ``one_exit_per_ingreso``.

Revision ID: 0026_seed_impuestos_iva_and_one_exit_per_ingreso
Revises: 0025_alerta_datos_nuevos (F1.6 chain head)
Create Date: 2026-09-14

**Scope.** Four operations in strict order:

  1. **Pre-flight (KD-7 F1.6 pattern)**: ``DO $$`` block aborts the
     migration with a typed ``0026_preflight_abort`` exception if
     ``prod.impuestos``, ``prod.salidas``, or ``prod.alert_types`` does
     not exist (e.g., a fresh deployment that never ran migrations
     0001-0025). Emits ``RAISE NOTICE`` with the row counts for the
     alembic log.

  2. **Inline-seed ``impuestos.IVA`` (KD-IVA resolver for F1.8)**:
     ``INSERT INTO prod.impuestos (...) VALUES (... 'IVA', 0.19 ...)
     ON CONFLICT (codigo, vigente_desde) DO NOTHING``. The UK constraint
     ``(codigo, vigente_desde)`` is the conflict target; the
     ``porcentaje=0.19`` is the regulatory constant locked in F1.8
     design.md §4 KD-IVA (IVA Colombia 2026). After this migration,
     F1.8 deployment is unblocked.

  3. **Inline-seed 2 alert types**: ``INSERT INTO prod.alert_types
     (tipo_alerta, descripcion, severity) VALUES
     ('subscripcion_vencida_forzado', ..., 'warning'),
     ('tarifa_vigente_forzado', ..., 'warning') ON CONFLICT (tipo_alerta)
     DO NOTHING``. Respects the ``alert_types_inmutable`` trigger
     (migration 0013) — INSERT-only for ``rol_app``. Same pattern as
     MIGRATION 0025 alert_type seed (F1.6).

  4. **Partial unique index ``one_exit_per_ingreso`` (KD-S16)**:
     ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
     one_exit_per_ingreso ON prod.salidas (uuid_ingreso) WHERE NOT
     EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida =
     prod.salidas.uuid AND a.tipo_anulable = 'salida' AND a.estado =
     'ejecutada')``. ``CONCURRENTLY`` for no lock on reads/writes;
     ``IF NOT EXISTS`` for idempotency. Closes TOCTOU race on V1 EXISTS
     subquery; ``UniqueViolationError → 409 salida_duplicada``.

**Idempotency.**
  - Op 2 ``ON CONFLICT (codigo, vigente_desde) DO NOTHING`` is the
    standard pattern; re-apply is a no-op.
  - Op 3 ``ON CONFLICT (tipo_alerta) DO NOTHING`` is the same pattern
    as MIGRATION 0025.
  - Op 4 ``CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS`` allows
    re-apply without raising (the index already exists, no DDL needed).
  - The pre-flight Op 1 ``DO $$`` block is idempotent (count check is
    read-only, no DDL).

**Downgrade.**
  1. ``DROP INDEX IF EXISTS prod.one_exit_per_ingreso`` (Op 4 reverse).
  2. ``DELETE FROM prod.alert_types WHERE tipo_alerta IN
     ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado')`` (Op 3
     reverse; runs as superuser to bypass ``alert_types_inmutable``).
  3. ``DELETE FROM prod.impuestos WHERE codigo='IVA' AND estado='activo'``
     (Op 2 reverse; runs as superuser). **Caveat (R8)**: if
     ``impuestos_inmutable`` trigger exists (verified pre-F1.7-apply
     via ``grep impuestos_inmutable migrations/``), the DELETE may be
     blocked. Workaround: NO downgrade in production; create
     compensatory migration setting ``estado='inactivo'`` instead.

**Pre-flight ordering (Op 1)**: the DO $$ block aborts BEFORE any INSERT,
so a missing table does not leave partial state. The DO $$ block is the
FIRST statement in the upgrade() function.

**Cross-references.**
  - F1.8 design.md §4 KD-IVA — the inline-seed matches the documented
    seeding recipe.
  - F1.6 MIGRATION 0025 — Op 3 mirrors the alert_type seed pattern.
  - F1.3 MIGRATION 0023 — Op 4 mirrors the partial unique index pattern
    (unique_active_sesion_per_user).
  - ``repo/salida.py::crear_salida_evento`` (NEW, F1.7) catches
    ``IntegrityError("one_exit_per_ingreso")`` and maps to
    ``SalidaDuplicada → 409``.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0026_seed_impuestos_iva_and_one_exit_per_ingreso"
down_revision = "0025_alerta_datos_nuevos"
branch_labels = None
depends_on = None


# Matches the F1.5 / F1.6 migration pattern (0024_add_mv_ocupacion_diaria.py
# line 61 + 0025_add_alerta_datos_nuevos.py line 65): cap any blocking DDL
# at 5s so the migration cannot stall the alembic runtime on a busy DB.
_LOCK_TIMEOUT_SQL = "SET lock_timeout = '5s'"


def upgrade() -> None:
    """Apply the F1.7 IVA seed + 2 alert_types + partial unique index."""
    op.execute(_LOCK_TIMEOUT_SQL)

    # 1) Pre-flight (KD-7 F1.6 pattern): 3 tables must exist.
    op.execute(
        """
        DO $$
        DECLARE
            _n_impuestos bigint;
            _n_salidas bigint;
            _n_alert_types bigint;
        BEGIN
            SELECT count(*) INTO _n_impuestos
            FROM pg_catalog.pg_class
            WHERE relname='impuestos' AND relnamespace='prod'::regnamespace;
            RAISE NOTICE '0026_preflight: prod.impuestos existe con % filas',
                _n_impuestos;
            IF _n_impuestos IS NULL OR _n_impuestos = 0 THEN
                RAISE EXCEPTION '0026_preflight_abort: tabla prod.impuestos no existe. Aplique migrations 0001-0025 antes.';
            END IF;

            SELECT count(*) INTO _n_salidas
            FROM pg_catalog.pg_class
            WHERE relname='salidas' AND relnamespace='prod'::regnamespace;
            RAISE NOTICE '0026_preflight: prod.salidas existe con % filas',
                _n_salidas;
            IF _n_salidas IS NULL OR _n_salidas = 0 THEN
                RAISE EXCEPTION '0026_preflight_abort: tabla prod.salidas no existe.';
            END IF;

            SELECT count(*) INTO _n_alert_types
            FROM pg_catalog.pg_class
            WHERE relname='alert_types' AND relnamespace='prod'::regnamespace;
            RAISE NOTICE '0026_preflight: prod.alert_types existe con % filas',
                _n_alert_types;
            IF _n_alert_types IS NULL OR _n_alert_types = 0 THEN
                RAISE EXCEPTION '0026_preflight_abort: tabla prod.alert_types no existe.';
            END IF;
        END $$;
        """
    )

    # 2) Inline-seed prod.impuestos.IVA (KD-IVA resolver for F1.8).
    #    codigo='IVA' is the UK01 of impuestos (modelo_datos_er.mmd:187-207).
    #    The ON CONFLICT uses the UK constraint (codigo, vigente_desde)
    #    for idempotency.
    #    porcentaje=0.19 is the regulatory constant (IVA Colombia 2026).
    op.execute(
        """
        INSERT INTO prod.impuestos (
            uuid, codigo, nombre, porcentaje,
            vigente_desde, vigente_hasta, estado, created_at
        ) VALUES (
            gen_random_uuid(), 'IVA', 'IVA', 0.19,
            NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
        )
        ON CONFLICT (codigo, vigente_desde) DO NOTHING
        """
    )

    # 3) Inline-seed 2 alert_types (F1.7 alerts).
    #    Respects alert_types_inmutable trigger (migration 0013) —
    #    INSERT-only for rol_app; ON CONFLICT DO NOTHING is idempotent.
    op.execute(
        """
        INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
        VALUES
            (
                'subscripcion_vencida_forzado',
                'Salida vehicular forzada por administrador al detectar '
                'subscripción vencida al momento de salida',
                'warning'
            ),
            (
                'tarifa_vigente_forzado',
                'Salida vehicular forzada por administrador al detectar '
                'tarifa no vigente al momento de salida',
                'warning'
            )
        ON CONFLICT (tipo_alerta) DO NOTHING
        """
    )

    # 4) Partial unique index one_exit_per_ingreso (KD-S16, TOCTOU closure).
    #    CONCURRENTLY for no lock on reads/writes; IF NOT EXISTS for idempotency.
    #    The WHERE NOT EXISTS clause excludes anuladas: once a salida is
    #    anulada, a new salida for the same uuid_ingreso becomes possible.
    op.execute(
        """
        CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso
            ON prod.salidas (uuid_ingreso)
            WHERE NOT EXISTS (
                SELECT 1 FROM prod.anulaciones a
                WHERE a.uuid_salida = prod.salidas.uuid
                  AND a.tipo_anulable = 'salida'
                  AND a.estado = 'ejecutada'
            )
        """
    )


def downgrade() -> None:
    """Reverse the F1.7 IVA seed + 2 alert_types + partial unique index.

    Runs as superuser (alembic) so the ``alert_types_inmutable`` trigger
    does NOT block the DELETE.

    Reverse order (Op 4 → Op 3 → Op 2):
      1. DROP INDEX
      2. DELETE alert_types
      3. DELETE impuestos (workaround if impuestos_inmutable exists: NO
         downgrade; create compensatory migration setting estado='inactivo').
    """
    op.execute(_LOCK_TIMEOUT_SQL)

    # Op 4 reverse: DROP INDEX.
    op.execute("DROP INDEX IF EXISTS prod.one_exit_per_ingreso")

    # Op 3 reverse: DELETE 2 alert_types (superuser; bypasses inmutable trigger).
    op.execute(
        "DELETE FROM prod.alert_types "
        "WHERE tipo_alerta IN ("
        "'subscripcion_vencida_forzado', 'tarifa_vigente_forzado')"
    )

    # Op 2 reverse: DELETE prod.impuestos.IVA (superuser).
    # Caveat (R8): if impuestos_inmutable trigger is present, this DELETE
    # may be blocked. Verification pre-F1.7-apply:
    #   grep -r "impuestos_inmutable" migrations/
    # If trigger exists, the workaround is:
    #   UPDATE prod.impuestos
    #   SET estado='inactivo', vigente_hasta=NOW() AT TIME ZONE 'UTC'
    #   WHERE codigo='IVA' AND vigente_hasta IS NULL;
    # Document this in the verify-report.md if the trigger exists.
    op.execute(
        "DELETE FROM prod.impuestos "
        "WHERE codigo='IVA' AND estado='activo'"
    )


__all__ = ["downgrade", "upgrade"]
```

**Notes.**

- The migration is **deterministic** in its order: pre-flight first (abort if any table missing), then IVA seed, then alert_types seed, then partial unique index. Re-application is a no-op (ON CONFLICT DO NOTHING + IF NOT EXISTS).
- The `CREATE UNIQUE INDEX CONCURRENTLY` cannot run inside an Alembic transaction (PostgreSQL limitation); Alembic detects this and switches to autocommit mode for the DDL. The `CONCURRENTLY` is required because production may have live SELECT/INSERT on `prod.salidas`. If a concurrent `INSERT` happens during the index build, the index build will wait for it (no lock acquired on the table).
- The downgrade's `DELETE FROM prod.alert_types` runs as superuser (alembic's default connection) to bypass the `alert_types_inmutable` trigger.
- The downgrade's `DELETE FROM prod.impuestos` may collide with `impuestos_inmutable` trigger if it exists (R8 risk). Verification pre-F1.7-apply is `grep impuestos_inmutable migrations/`; if the trigger exists, the downgrade is replaced by an `UPDATE … SET estado='inactivo'` workaround.

## 9. Repo Skeleton — File-by-File

### 9.1 `backend/packages/parkos_core/src/parkos_core/models/A/salidas.py` (REUSED, pre-existing since PR1a)

`prod.salidas` has existed since migration 0001 (lines 571-591, partitioned monthly by `fecha_retencion_hasta`) and had a pre-existing `[A]`-class ORM mapping (`models/A/salidas.py::Salidas(AppendOnlyBase)`, ~85 LOC, pre-existing since PR1a). **F1.7 reuses this pre-existing mapping** instead of creating a new `models/L_S/salida.py` based on `LifecycleEventBase` (the originally-proposed approach, D-HU-F1.7-14 supersession).

```python
"""ORM model for ``prod.salidas`` (vehicle exit [A] event, PR6-T05a).

Maps 1:1 to the migration in ``0001_initial_schema.py`` (lines 557-580).
The table was created in PR1a but the ORM class was deferred to PR6 — it
is the missing polymorphic target referenced from
``repo/workflow.py::polymorphic_row_exists`` (REQ-OP-08, REQ-23-W-POLYMORPHIC-FK).

Range-partitioned monthly by ``fecha_retencion_hasta`` (DIAN 5+ year
retention, pg_partman parent). Composite PK on
``(uuid, fecha_retencion_hasta)`` overrides ``IdMixin``'s single-column PK.

``[A]`` inmutability is enforced at the DB layer by the
``REVOKE UPDATE, DELETE`` from ``rol_app`` + the
``BEFORE UPDATE OR DELETE`` trigger installed in migration ``0001``. The
ORM marker ``__write_only__`` (inherited from :class:`AppendOnlyBase`) is
read by ``tests/static/test_no_raw_dml_on_a_tables.py`` to reject any
``session.execute(update/delete)`` against ``salidas`` outside
``repo/append_only.py``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import Date, DateTime, PrimaryKeyConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import AppendOnlyBase


class Salidas(AppendOnlyBase):
    """[A] Append-only vehicle exit event.

    Written via :func:`repo.append_only.append_event` (single INSERT
    helper, REQ-10-A-INSERCION). Never updated or deleted: the original
    exit record is permanent; corrections are expressed as new
    compensating ``[L-W]`` rows (e.g. ``anulaciones``) and never as a
    mutation of this row.
    """

    __tablename__ = "salidas"

    # --- Composite PK columns (override IdMixin's primary_key=True) ---
    uuid: Mapped[uuid_lib.UUID] = mapped_column(  # type: ignore[override]
        PG_UUID(as_uuid=True),
        nullable=False,
        server_default=func.gen_random_uuid(),
    )
    fecha_retencion_hasta: Mapped[date] = mapped_column(  # type: ignore[override]
        Date,
        nullable=False,
        server_default=func.current_date(),
    )

    # --- Business columns ---
    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    uuid_ingreso: Mapped[uuid_lib.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
    )
    fecha_salida: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "uuid",
            "fecha_retencion_hasta",
            name="salidas_pk",
        ),
        {
            "schema": "prod",
            "extend_existing": True,
            "postgresql_partition_by": "RANGE (fecha_retencion_hasta)",
        },
    )


__all__ = ["Salidas"]
```

**Notes.**

- The pre-existing model exposes exactly the columns the table has (no extras). The `extend_existing=True` allows re-mapping if `prod.salidas` is added to other ORM contexts.
- No `tipo_salida`, `forzado`, `motivo`, or `valor` columns — DEC-SUC-21-NEW + KD-FORZADO-01 + DEC-SUC-23 veda.
- Composite PK `(uuid, fecha_retencion_hasta)` overrides `IdMixin`'s single-column PK; this is required by the monthly `RANGE` partition strategy.
- The `__write_only__` ORM marker inherited from `AppendOnlyBase` is the **defense-in-depth upgrade** over the originally-proposed `LifecycleEventBase` derivation: `tests/static/test_no_raw_dml_on_a_tables.py` reads `__write_only__` to reject any `session.execute(update/delete)` against `salidas` outside `repo/append_only.py`. The `[L_S]`-style class would not have inherited this marker.

### 9.2 `backend/packages/parkos_core/src/parkos_core/repo/salida.py` (NEW, ~180 LOC)

```python
"""HU-F1.7 / REQ-OPS-042..052 — Salida lifecycle (rotación + mensualidad).

Helpers for ``POST /operacion/salidas``:
- ``buscar_ingreso_activo_por_uuid`` (V1)
- ``cotizar_para_salida`` (V5 wrapper over F1.8 PL/pgSQL, raises typed exceptions)
- ``crear_salida_evento`` (Step 8 INSERT [A] via ORM, IntegrityError → SalidaDuplicada)
- ``insertar_alerta_salida_forzado`` (Step 9, alerts for V2/V5 bypass)
- ``SalidaDuplicada`` (typed 409 mapping)

DEC-SAL-01: writes are append-only. NO UPDATE, NO DELETE.
DEC-SUC-21-NEW: tipo_salida is derived in the handler, NOT persisted.
KD-S7: the cotizar_para_salida call shares the caller's transaction;
       no sub-transactions or SAVEPOINT inside the repo.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.ingreso import Ingreso
from ..models.L_S.salida import Salida
from ..models.L_W.alerta import Alerta
from ..repo.cotizacion import (
    CotizacionError,
    IngresoNoEncontrado,
    IVANoConfigurado,
    TarifaNoVigente,
)


class SalidaDuplicada(Exception):
    """409 — partial unique index ``one_exit_per_ingreso`` violated.

    Raised when ``prod.salidas`` rejects an INSERT due to the
    ``one_exit_per_ingreso`` partial unique index (migration 0026).
    Mapped to HTTP 409 by the handler.
    """


async def buscar_ingreso_activo_por_uuid(
    session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID
) -> Ingreso | None:
    """V1: SELECT ingreso WHERE uuid=:p AND vigente_hasta IS NULL
    AND NOT EXISTS salidas (no anulada).

    Returns the ORM ``Ingreso`` row if found, None otherwise.
    """
    # Fast path: direct PK lookup + bi-temporal predicate.
    ingreso_row = await session.get(Ingreso, uuid_ingreso)
    if ingreso_row is None or ingreso_row.vigente_hasta is not None:
        return None

    # Existence check: NOT EXISTS salidas not anulada.
    stmt = text(
        """
        SELECT 1 FROM prod.salidas s
        WHERE s.uuid_ingreso = :uuid_ingreso
          AND NOT EXISTS (
              SELECT 1 FROM prod.anulaciones a
              WHERE a.uuid_salida = s.uuid
                AND a.tipo_anulable = 'salida'
                AND a.estado = 'ejecutada'
          )
        LIMIT 1
        """
    )
    exists = (
        await session.execute(stmt, {"uuid_ingreso": str(uuid_ingreso)})
    ).first()
    if exists is not None:
        return None  # already has a non-anulada salida
    return ingreso_row


async def cotizar_para_salida(
    session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID
) -> dict[str, Any]:
    """V5: invoke ``prod.calcular_cotizacion(:uuid_ingreso)`` and return jsonb.

    Reuses F1.8's PL/pgSQL function via ``repo.cotizacion.cotizar_ingreso``.
    The difference with the GET /cotizar handler is that here the caller
    controls the exception flow (no HTTPException mapping); the handler
    decides whether to insert an alerta or raise 422.

    KD-S7: this call shares the caller's transaction. The PL/pgSQL
    ``SELECT ... FOR SHARE`` on ``tarifas_sucursal`` is held until
    ``session.commit()`` in the handler. NO sub-transactions.

    Raises:
        IngresoNoEncontrado: ``{error:ingreso_no_encontrado}`` payload (covered by V1)
        TarifaNoVigente: ``{error:tarifa_no_vigente}`` payload (KD-3, F1.8)
        IVANoConfigurado: ``{error:iva_no_configurado}`` payload (KD-IVA, F1.8)
    """
    from ..repo.cotizacion import cotizar_ingreso
    return await cotizar_ingreso(session, uuid_ingreso=uuid_ingreso)


async def crear_salida_evento(
    session: AsyncSession,
    *,
    actor_uuid: uuid_lib.UUID,
    new_attrs: dict[str, Any],
) -> Salida:
    """Step 8: INSERT ``prod.salidas`` [A] (append-only).

    Defense in depth: REVOKE UPDATE, DELETE (migration 0001 línea 2923)
    + ``fn_salidas_inmutable`` trigger (líneas 1990-2003) + partial unique
    index ``one_exit_per_ingreso`` (migration 0026).

    Raises:
        SalidaDuplicada: ``IntegrityError`` with code 23505 on the
                        ``one_exit_per_ingreso`` partial unique index.
                        Mapped to HTTP 409 by the handler.
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    new_row = Salida(
        **new_attrs,
        created_at=now,
        created_by=actor_uuid,
    )
    session.add(new_row)
    try:
        await session.flush()
    except IntegrityError as err:
        # psycopg2/asyncpg: UniqueViolationError code 23505.
        if "one_exit_per_ingreso" in str(err.orig):
            raise SalidaDuplicada() from err
        raise
    return new_row


async def insertar_alerta_salida_forzado(
    session: AsyncSession,
    *,
    uuid_sucursal: uuid_lib.UUID,
    uuid_salida: uuid_lib.UUID,
    actor_uuid: uuid_lib.UUID,
    motivo: str,
    tipo_alerta: str,  # 'subscripcion_vencida_forzado' | 'tarifa_vigente_forzado'
) -> Alerta:
    """Step 9: INSERT ``prod.alerta`` for V2/V5 bypass.

    Same TX as the salida INSERT (caller commits). R5 mitigation:
    FK commit ordering — alerta only commits if salida OK.

    ``datos_nuevos`` jsonb (column added by MIGRATION 0025 in F1.6)
    carries ``{"motivo": motivo, "uuid_salida": str(uuid_salida)}``.
    """
    alerta = Alerta(
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=actor_uuid,
        tipo_alerta=tipo_alerta,
        estado="abierta",
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
        uuid_arqueo=None,
        datos_nuevos={
            "motivo": motivo,
            "uuid_salida": str(uuid_salida),
        },
    )
    session.add(alerta)
    await session.flush()
    return alerta


__all__ = [
    "SalidaDuplicada",
    "buscar_ingreso_activo_por_uuid",
    "cotizar_para_salida",
    "crear_salida_evento",
    "insertar_alerta_salida_forzado",
]
```

**Notes.**

- `buscar_ingreso_activo_por_uuid` does NOT acquire a pessimistic lock (D-HU-F1.7-3, KD-V8). The PK lookup is atomic; the EXISTS subquery is < 5ms p99 with the F1.5 `(uuid_sucursal, placa, created_at)` index (salidas uses an FK index on `uuid_ingreso` from the PK-side relation).
- `cotizar_para_salida` reuses `repo.cotizacion.cotizar_ingreso` from F1.8 (no re-implementation). The exceptions are typed at the F1.8 layer.
- `crear_salida_evento` uses the ORM (no raw SQL for INSERT); the `IntegrityError → SalidaDuplicada` mapping is the only error handling.
- `insertar_alerta_salida_forzado` writes to `prod.alerta` (existing `[L-W]` table, MIGRATION 0025 added `datos_nuevos` jsonb). The jsonb shape is slightly different from F1.6's alerta (uses `uuid_salida` instead of `uuid_ingreso`).

### 9.3 `backend/packages/parkos_core/src/parkos_core/repo/impuestos.py` (NEW, ~50 LOC)

```python
"""HU-F1.7 — inline-seed helper for ``prod.impuestos`` (KD-IVA resolver).

Provides read access to the canonical IVA tax row (codigo='IVA',
porcentaje=0.19). The row itself is inserted by migration 0026 via
``INSERT ... ON CONFLICT (codigo, vigente_desde) DO NOTHING``.

This module is a thin wrapper — the PL/pgSQL function
``prod.calcular_cotizacion`` reads ``prod.impuestos`` directly without
going through Python. The helper exists for:
- HU-F1.9 (facturación) snapshot validation.
- HU-F14.2 audit (verify IVA seeded post-deploy).
- Test fixtures (mock the read).

Idempotent on re-apply. ``validar_iva_configurado`` returns True iff the
IVA row exists and is vigente at NOW(); the contract is the same as
F1.8's PL/pgSQL predicate.
"""
from __future__ import annotations

from datetime import UTC, datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.V.impuestos import Impuestos


async def validar_iva_configurado(session: AsyncSession) -> bool:
    """Return True iff ``prod.impuestos`` has a vigente row with codigo='IVA'.

    Predicate (bi-temporal [V]):
        codigo = 'IVA'
        AND vigente_hasta IS NULL
        AND estado = 'activo'
        AND vigente_desde <= NOW()
    """
    now = datetime.now(UTC).replace(tzinfo=None)
    stmt = select(Impuestos).where(
        Impuestos.codigo == "IVA",
        Impuestos.vigente_hasta.is_(None),
        Impuestos.estado == "activo",
        Impuestos.vigente_desde <= now,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    return row is not None


__all__ = ["validar_iva_configurado"]
```

**Notes.**

- `validar_iva_configurado` is used for health checks and test mocks, NOT in the hot path. The hot path (V5) reads IVA directly via F1.8 PL/pgSQL.
- The module does NOT provide a write helper (the row is seeded by MIGRATION 0026 and managed by HU-F14.2 Parte II catalog ops).

### 9.4 `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (MODIFY, +80 LOC)

Appends the new schemas after the existing F1.5 / F1.6 / F1.8 block. The existing `IngresoCreate` / `IngresoRead` / `CotizarResponse` are kept as deprecated aliases for backward compatibility.

```python
# ADD to existing schemas/operacion.py after the F1.6 block:


# --- HU-F1.7 / REQ-OPS-042..052 -----------------------------------------


class SalidaCreateForzado(_Base):
    """INSERT payload for ``prod.salidas`` ([A] append-only event, HU-F1.7).

    Identifies the ingreso to close. Sucursal is resolved server-side from
    the ingreso (NEW in F1.7 — client does not send). Placa is optional:
    if sent, server confirms against ingreso (V3); otherwise server trusts
    ``uuid_ingreso``.

    ``extra='forbid'`` (inherited from ``_Base``) rejects extra fields,
    including attempts to inject ``tipo_salida`` (DEC-SUC-21-NEW).
    """
    uuid_ingreso: uuid_lib.UUID         # REQUIRED — ingreso to close
    placa: str | None = None            # OPTIONAL — V3 confirmation
    observaciones: str | None = None    # OPTIONAL — KD-FORZADO-01 prefix
    forzado: bool = False               # OPTIONAL — bypass V2/V5


class SalidaReadForzado(_Base):
    """Response shape for ``POST /operacion/salidas`` (HU-F1.7).

    Additive delta to ``SalidaRead`` (no field removed or renamed):
    - ``tipo_salida``: Literal['MENSUALIDAD', 'ROTACION'] (DEC-SUC-21-NEW)
    - ``forzado_en_creacion``: True iff KD-FORZADO-01 bypass was used
    - ``motivo_forzado``: stripped motivo, or None
    - ``cotizacion_snapshot``: CotizarFacturacion if ROTACION, None if MENSUALIDAD
    """
    # Inherited from SalidaRead (10 columns):
    uuid: uuid_lib.UUID
    created_at: datetime
    created_by: uuid_lib.UUID | None
    sync_status: str | None
    sync_timestamp: datetime | None
    sync_attempts: int | None
    uuid_sucursal: uuid_lib.UUID | None
    uuid_ingreso: uuid_lib.UUID | None
    fecha_salida: datetime | None
    # NEW (F1.7):
    tipo_salida: Literal["MENSUALIDAD", "ROTACION"]
    forzado_en_creacion: bool = False
    motivo_forzado: str | None = None
    cotizacion_snapshot: CotizarFacturacion | None = None


# --- Typed error schemas (D-HU-F1.7-19) ----------------------------------


class IngresoNoEncontradoError(_Base):
    """V1 404 discriminator — uuid_ingreso no existe, ya cerrado, o anulado."""
    error: Literal["ingreso_no_encontrado"]
    uuid_ingreso: uuid_lib.UUID


class SalidaDuplicadaError(_Base):
    """Step 8 409 discriminator — partial unique index violated."""
    error: Literal["salida_duplicada"]
    uuid_ingreso: uuid_lib.UUID


class PlacaNoCoincideConIngresoError(_Base):
    """V3 422 discriminator — optional placa mismatch."""
    error: Literal["placa_no_coincide_con_ingreso"]
    placa_request: str
    placa_ingreso: str


class TarifaVigenteNoEncontradaError(_Base):
    """V5 422 discriminator — when not bypassed."""
    error: Literal["tarifa_vigente_no_encontrada"]


# Append ``SalidaCreateForzado`` / ``SalidaReadForzado`` / 4 errors to __all__.
```

**Notes.**

- `extra='forbid'` (inherited from `_Base`) rejects `tipo_salida` (DEC-SUC-21-NEW) and `correlacion_id` (DEC-IDEM-01) before the handler runs.
- `SalidaReadForzado.cotizacion_snapshot` reuses the existing `CotizarFacturacion` schema from F1.8 — no new schema introduced.

## 10. Locking + Concurrency

**Lock pesimista FOR SHARE en `tarifas_sucursal`** — replicado del F1.8 KD-1. The handler invokes `SELECT prod.calcular_cotizacion(:uuid_ingreso) AS payload` **dentro de la misma transacción** que el INSERT en `salidas`. El PL/pgSQL mantiene `FOR SHARE` lock sobre `tarifas_sucursal` hasta `session.commit()`.

**NO lock pesimista en `prod.ingreso` SELECT** (V1) — el SELECT por PK es atómico; el `EXISTS` subquery para verificar "no salida previa" es vulnerable a TOCTOU race, pero el partial unique index `one_exit_per_ingreso` (Op 4) cierra la ventana: si dos requests concurrentes intentan INSERT, el segundo recibe `UniqueViolationError` y se mapea a `409 salida_duplicada`. La latencia del SELECT vs INSERT es despreciable (< 5ms p99).

**Lock pesimista opcional en `prod.subscripciones_cliente`** — NO. Reusamos `validar_subscripcion_vigente` que es SELECT puro sin lock. Riesgo de subscripción cambiando de estado entre V2 y V5 es aceptable (es read-mostly; cambios son admin-actions infrecuentes).

**NO sub-transactions, NO SAVEPOINT.** The handler does NOT use `session.begin_nested()` or `SAVEPOINT`. The `await session.commit()` is the only commit point (KD-S7 invariant). AST walk `test_salida_handler_step_order.py` rejects multiple `session.commit()` calls.

**Orden de release:** el lock `FOR SHARE` se libera en `session.commit()` (Step 9, mismo punto donde el INSERT se materializa). Garantía: la transacción cotizar→validar→INSERT es atómica; otra TX no puede modificar `tarifas_sucursal` mientras el handler corre.

**Concurrencia horizontal:** múltiples salidas en distintas sucursales no compiten por el mismo lock (lock es per-row, no per-table). Múltiples salidas en la misma sucursal sobre distintos `uuid_ingreso` tampoco compiten (cada una lockea su propia fila de `tarifas_sucursal` por combinación `(uuid_sucursal, uuid_tipo_vehiculo)`).

**FK ordering**: `prod.alerta` has no FK constraint to `prod.salidas` (alerts are independent events keyed by `uuid_sucursal` + `uuid_usuario`). The order is: (a) Step 8 INSERT + flush (so `new_row.uuid` is populated), (b) Step 9 alerta INSERT (reads `new_row.uuid` from the flushed row to populate `datos_nuevos.uuid_salida`), (c) Step 9 single commit. Both rows materialize atomically.

## 11. Defense in Depth (5-layer)

The validation chain is layered such that no single failure can bypass the whole (D-HU-F1.7-7):

1. **Layer 1 (DB)**: `prod.salidas` has REVOKE UPDATE/DELETE (migration 0001 línea 2923) + `fn_salidas_inmutable` trigger (líneas 1990-2003) + partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4). `alert_types_inmutable` trigger (migration 0013) protects the 2 new alert_types from UPDATE/DELETE by `rol_app`. `impuestos_inmutable` trigger (if exists per R8) protects the IVA row from DELETE.
2. **Layer 2 (Repo)**: `repo/salida.py::crear_salida_evento` captures `IntegrityError` with code `23505` on `one_exit_per_ingreso` and raises `SalidaDuplicada` typed exception. The handler maps it to 409.
3. **Layer 3 (Handler)**: 12-step chain catches typed exceptions (`SalidaDuplicada`, `TarifaNoVigente`, `IVANoConfigurado`, `IngresoNoEncontrado`) and maps to HTTPError with discriminators. Single `await session.commit()` ensures atomicity (KD-S7).
4. **Layer 4 (Audit)**: same-TX alertas (`subscripcion_vencida_forzado`, `tarifa_vigente_forzado`) inserted in Step 9 with `datos_nuevos` jsonb carrying `{"motivo": ..., "uuid_salida": str(uuid_salida)}`. One alerta per bypassed validation (V2 or V5 mutually exclusive).
5. **Layer 5 (AST walk)**: 2 AST walks enforce code-level contracts (`test_salida_handler_step_order.py` for ordering, `test_no_write_after_salida_insert.py` for no UPDATE/DELETE/TRUNCATE).

**Cross-cutting defense**: KD-FORZADO-01 prefix contract (F1.6 verbatim reuse) prevents desynchronized `forzado` bool vs `observaciones` prefix; the 3 discriminators (`motivo_forzado_requerido`, `forzado_contradiccion`, `motivo_forzado_insuficiente`) catch client-side inconsistencies.

## 12. AST Walk Invariants

The handler's correctness relies on 2 AST walks that verify code-level contracts at CI time. Both walks use **source-ordered recursion** (`ast.NodeVisitor` with `generic_visit` + `visit` for nested statements), NOT `ast.walk` (which is BFS and breaks ordering when nested `if`/`for`/`with`/`async with` blocks contain helpers).

### 12.1 `tests/static/test_salida_handler_step_order.py` (~100 LOC, 1 AST walk)

**Purpose.** Locks the literal order of helper invocations in `create_salida` (D-HU-F1.7-20). Reorders or omissions break the 12-step chain.

**Walk strategy:**

```python
import ast
import pathlib

TARGET_PATH = (
    pathlib.Path("backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py")
)
TARGET_FUNC = "create_salida"
EXPECTED_CALLS = [
    "buscar_ingreso_activo_por_uuid",   # Step 2 (V1)
    "validar_subscripcion_vigente",      # Step 4 (V2)
    "detectar_tipo_vehiculo",            # Step 5 (V3) — appears 2x
    "validar_kd_forzado",                # Step 6 (V4)
    "cotizar_para_salida",               # Step 7 (V5)
    "crear_salida_evento",               # Step 8 (INSERT)
    "insertar_alerta_salida_forzado",    # Step 9 (alerta)
]


class SourceOrderedCallCollector(ast.NodeVisitor):
    """AST visitor that collects function call names in source order.

    Uses NodeVisitor.generic_visit (depth-first, pre-order) instead of
    ast.walk (BFS) so the order matches the literal source code order.
    Handles nested if/for/with/async-with/try blocks via recursive
    generic_visit.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Extract the called function name (handles both bare names and
        # attribute access like `repo.salida.buscar_ingreso_activo_por_uuid`).
        name = _extract_call_name(node.func)
        if name is not None:
            self.calls.append(name)
        # Do NOT call generic_visit here — we only care about the
        # outermost call name; nested calls (e.g. inside an arg) are
        # noise for ordering purposes.
        # Actually: we DO want nested if/for to contain their calls.
        # generic_visit will visit child nodes including nested stmts.
        self.generic_visit(node)


def _extract_call_name(func: ast.expr) -> str | None:
    """Extract the rightmost name from a Call.func node.

    - `buscar(...)` → 'buscar'
    - `repo.salida.buscar(...)` → 'buscar'
    - `await buscar(...)` → 'buscar' (Await is wrapped by visitor)
    """
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    """Find a top-level async function by name."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_create_salida_invoca_helpers_en_orden_correcto() -> None:
    source = TARGET_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = _find_function(tree, TARGET_FUNC)
    assert func is not None, f"Function {TARGET_FUNC} not found in {TARGET_PATH}"

    collector = SourceOrderedCallCollector()
    collector.visit(func)

    # Filter to the expected calls in order. Each EXPECTED_CALLS entry
    # must appear in the call sequence in the same order; extra calls
    # (e.g. session.commit, no_store_headers) are allowed but must not
    # break the order.
    filtered = [c for c in collector.calls if c in EXPECTED_CALLS]
    assert filtered == EXPECTED_CALLS, (
        f"Handler {TARGET_FUNC} calls out of order. "
        f"Expected: {EXPECTED_CALLS}; "
        f"Got: {filtered}"
    )

    # Also verify single commit (KD-S7 invariant):
    commits = [c for c in collector.calls if c == "commit"]
    assert len(commits) <= 1, (
        f"Handler {TARGET_FUNC} has {len(commits)} session.commit() calls. "
        "KD-S7 invariant: exactly ONE commit() per request."
    )
```

**Notes.**

- The `SourceOrderedCallCollector` uses `ast.NodeVisitor` with `generic_visit` for depth-first traversal (vs `ast.walk`'s BFS). This preserves source code order even when helpers are nested inside `if`/`for`/`try` blocks.
- `_extract_call_name` handles both bare names (`buscar(...)`) and attribute chains (`repo.salida.buscar(...)`); the rightmost segment is used.
- The walk collects ALL call names, then filters to the expected set in order. Extra calls (e.g. `session.commit`, `no_store_headers`, `apply_no_store_header`, `SalidaRead.model_validate`) are allowed but must not break the order.
- The `commits` check enforces KD-S7 (single commit per request).

### 12.2 `tests/static/test_no_write_after_salida_insert.py` (~100 LOC, 1 AST walk)

**Purpose.** Rejects `UPDATE | DELETE | TRUNCATE | MERGE` in `repo/salida.py::crear_salida_evento` after the INSERT (D-HU-F1.7-7 Layer 5, R6 DEC-SUC-21-NEW verification). Mirrors `test_no_write_in_calcular_cotizacion.py` (F1.8).

```python
import ast
import pathlib

TARGET_PATH = (
    pathlib.Path("backend/packages/parkos_core/src/parkos_core/repo/salida.py")
)
TARGET_FUNC = "crear_salida_evento"
FORBIDDEN_AFTER_INSERT = {"UPDATE", "DELETE", "TRUNCATE", "MERGE"}


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


class WriteAfterInsertDetector(ast.NodeVisitor):
    """Detects UPDATE/DELETE/TRUNCATE/MERGE string literals appearing AFTER
    the first INSERT in the function body.

    DEC-SAL-01: salida is append-only. The function body may contain an
    INSERT (the only legitimate write) but no UPDATE/DELETE/TRUNCATE/MERGE.
    """

    def __init__(self) -> None:
        self.insert_seen = False
        self.violation: str | None = None

    def _check_string(self, s: str) -> None:
        if not self.insert_seen:
            return
        upper = s.upper()
        for forbidden in in FORBIDDEN_AFTER_INSERT:
            if forbidden in upper:
                self.violation = (
                    f"Forbidden DDL/DML keyword '{forbidden}' found in "
                    f"string literal after INSERT: '{s}'"
                )
                return

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            self._check_string(node.value)
        self.generic_visit(node)

    def visit_SqlQueryMarker(self, node: ast.AST) -> None:
        """Optional: marker for SQL strings. Apply phase may add a
        custom node marker; if absent, fall back to constant string check.
        """
        pass


def test_crear_salida_evento_rechaza_update_delete_truncate() -> None:
    source = TARGET_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = _find_function(tree, TARGET_FUNC)
    assert func is not None, f"Function {TARGET_FUNC} not found in {TARGET_PATH}"

    detector = WriteAfterInsertDetector()
    detector.visit(func)
    assert detector.violation is None, detector.violation
```

**Notes.**

- The walk is permissive: it only flags UPDATE/DELETE/TRUNCATE/MERGE string literals appearing AFTER the first INSERT-like construct. Pre-INSERT helper queries (e.g. `text("SELECT ...")`) are allowed.
- The apply phase may enhance the walk to use a custom AST marker (`SqlQueryMarker`) for SQL strings; if absent, the string-literal check is sufficient (any `text("UPDATE ...")` would be flagged).

## 13. Tests Plan

The test plan is **14 tests across 6 test files**, mirroring F1.6's split (HTTP unit + KD-FORZADO unit + DB integration + AST static + migration idempotency). Each test name documents the test intent for OPS auditing; the file paths align with `proposal.md §11`.

### File 1: `backend/tests/unit/test_operacion_salidas.py` (~400 LOC, 10 HTTP-level tests)

Uses `httpx.AsyncClient + ASGITransport` (F1.3 / F1.5 / F1.6 / F1.8 precedent) and the JWT `operador-` fixture from `tests/unit/test_auth_login_password.py`. Real `pg_engine` (no SQLite per project rule).

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_salida_rotacion_exitosa_returns_201_with_tipo_rotacion` | Seed ingreso + tarifa vigente + calcular_cotizacion returns `cobrar:true`; POST returns 201; `body.tipo_salida == "ROTACION"`, `body.cotizacion_snapshot is not None`; DB row inserted. REQ-OPS-047 + REQ-OPS-048 + REQ-OPS-049. |
| **T2** | `test_salida_rotacion_sin_tarifa_vigente_returns_422` | calcular_cotizacion returns `error:tarifa_no_vigente`; POST returns 422 with `body.error == "tarifa_vigente_no_encontrada"`; no DB row. REQ-OPS-047. |
| **T3** | `test_salida_rotacion_forzada_con_alerta_tarifa_vigente` | calcular_cotizacion returns `error:tarifa_no_vigente`; POST with `forzado=true` + valid prefix returns 201; `body.tipo_salida == "ROTACION"`; `prod.alerta` row exists with `tipo_alerta == "tarifa_vigente_forzado"`, `datos_nuevos.motivo == stripped`. REQ-OPS-047 + REQ-OPS-050. |
| **T4** | `test_salida_rotacion_duplicada_returns_409` | Seed ingreso with prior salida; POST same `uuid_ingreso` returns 409 with `body.error == "salida_duplicada"`; no new DB row. REQ-OPS-051. |
| **T5** | `test_salida_mensualidad_vigente_returns_201_with_tipo_mensualidad` | Seed ingreso + subscripcion vigente + calcular_cotizacion returns `cobrar:false, motivo:mensualidad_vigente`; POST returns 201; `body.tipo_salida == "MENSUALIDAD"`, `body.cotizacion_snapshot is None`. REQ-OPS-044 + REQ-OPS-049. |
| **T6** | `test_salida_mensualidad_vencida_returns_422_sin_forzado` | Seed ingreso + subscripcion `fecha_vencimiento < today`; POST returns 422 with `body.error == "subscripcion_inactiva_o_vencida"`; no DB row. REQ-OPS-044. |
| **T7** | `test_salida_mensualidad_vencida_con_forzado_returns_201_con_alerta` | Same setup as T6 with `forzado=true` + valid prefix; POST returns 201; `body.tipo_salida == "ROTACION"` (F1.8 returns `cobrar:true` when no subscription at branch); `prod.alerta` row with `tipo_alerta == "subscripcion_vencida_forzado"`. REQ-OPS-044 + REQ-OPS-050. |
| **T8** | `test_salida_placa_no_coincide_returns_422` | Seed ingreso with placa `ABC123`; POST `{"placa": "XYZ789"}` returns 422 with `body.error == "placa_no_coincide_con_ingreso"`; no DB row. REQ-OPS-045. |
| **T9** | `test_salida_kd_forzado_prefijo_valido_devuelve_201` | POST with `forzado=true` + `[FORZADO: cliente con cita medica urgente]` (≥10 chars); bypass active; 201 returned. REQ-OPS-046. |
| **T10** | `test_salida_kd_forzado_motivo_9_chars_returns_422` | POST with `forzado=true` + `[FORZADO: a b]` (9 chars); returns 422 with `body.error == "motivo_forzado_insuficiente"`. REQ-OPS-046. |

### File 2: `backend/tests/unit/test_operacion_salidas_kd_forzado.py` (~80 LOC, 2 tests)

Pure helper tests (no HTTP, no DB). Reuses F1.6's 4 KD-FORZADO unit tests; F1.7 adds 2 tests only to verify the contract still holds when invoked from the new salida path.

| # | Test Name | Asserts |
|---|---|---|
| **T1** | `test_validar_kd_forzado_prefijo_valido_devuelve_motivo` | `validar_kd_forzado("[FORZADO: cliente con cita medica urgente]", True) == "cliente con cita medica urgente"` (stripped). REQ-OPS-046. |
| **T2** | `test_validar_kd_forzado_motivo_insuficiente_raises_422` | `validar_kd_forzado("[FORZADO: a b]", True)` raises 422 with `min_chars == 10`. REQ-OPS-046. |

### File 3: `backend/tests/integration/test_salida_create_db.py` (~250 LOC, 3 DB tests, `PARKOS_DOCKER_TEST=1`)

Uses real `pg_engine` + `psycopg` direct SQL for seed/cleanup.

| # | Test Name | Asserts |
|---|---|---|
| **T11** | `test_insert_salida_con_alerta_forzado_atomico` | Real DB; POST with V2 bypass + motivo; assert both `prod.salidas` and `prod.alerta` rows present after commit; `prod.alerta.tipo_alerta == 'subscripcion_vencida_forzado'`, `datos_nuevos.motivo == stripped`, `datos_nuevos.uuid_salida == <salida uuid>`. Verifies single-commit (R5) + FK ordering. REQ-OPS-050. |
| **T12** | `test_partial_unique_index_emite_409` | Real DB; `asyncio.gather` 2 concurrent POSTs same `uuid_ingreso`; one succeeds, one returns 409 `salida_duplicada`. Verifies KD-S16 closure. REQ-OPS-051. |
| **T13** | `test_iva_no_sembrado_retorna_500` | Real DB; DELETE the IVA row (superuser); POST returns 500 with `body.error == "iva_no_configurado"`. Verifies KD-IVA pre-0026 behavior. REQ-OPS-052. |

### File 4: `backend/tests/integration/test_migration_0026_idempotent.py` (~150 LOC, 1 test)

| # | Test Name | Asserts |
|---|---|---|
| **T14** | `test_migration_0026_idempotent_runs_twice` | Run `alembic upgrade head` 2 times; second is no-op. Verifies `ON CONFLICT DO NOTHING` + `IF NOT EXISTS` idempotency. REQ-OPS-052. |

### File 5: `backend/tests/static/test_salida_handler_step_order.py` (~100 LOC, 1 AST walk)

R7 invariante — literal order verification (D-HU-F1.7-20). See §12.1 for the walk.

### File 6: `backend/tests/static/test_no_write_after_salida_insert.py` (~100 LOC, 1 AST walk)

Cross-cutting defense-in-depth gate (F1.8 precedent `test_no_write_in_calcular_cotizacion.py` adapted). See §12.2 for the walk.

**Coverage map.** The 14 tests in 6 files cover:

- HTTP happy + sad paths for the endpoint (T1..T8 in File 1).
- KD-FORZADO-01 discriminator contract reuse (T1..T2 in File 2).
- DB round-trip for atomicity, partial unique index, and IVA blocker (T11..T13 in File 3).
- Migration idempotency (T14 in File 4).
- AST gate locking the literal validation order (File 5).
- AST gate locking the insert-only contract (File 6).

Cross-cutting CI gates from `proposal.md §9.7`: `ruff check`, `ruff format --check`, `mypy --strict` on the 4 new + 2 modified backend files. `factory_intact` gate (F1.1 / F1.3 precedent) verifies `git diff backend/packages/parkos_core/src/parkos_core/api/v1/router_factory.py` returns empty. `event_helper_intact` gate verifies `git diff backend/packages/parkos_core/src/parkos_core/repo/event.py` returns empty. `auth_tenancy_intact` gate verifies `git diff backend/packages/parkos_core/src/parkos_core/auth/tenancy.py` returns empty. `f16_helpers_intact` gate verifies `git diff backend/packages/parkos_core/src/parkos_core/repo/ingreso.py backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py backend/packages/parkos_core/src/parkos_core/repo/placa.py backend/packages/parkos_core/src/parkos_core/repo/alerta.py` returns empty (F1.6 helpers reused verbatim). `f18_helpers_intact` gate verifies `git diff backend/packages/parkos_core/src/parkos_core/repo/cotizacion.py` returns empty.

## 14. Threat Matrix

The applicability-driven threat matrix covers eight attack surfaces specific to HU-F1.7. The defenses are layered (D-HU-F1.7-7, 5 layers) and KD-1..KD-20 plus the AST walks + integration tests cap the residual risk at **Low** for each row.

| # | Threat | Attack Vector | Defense in Depth Layer | Residual Risk | KD Mitigates |
|---|---|---|---|---|---|
| **T1** | SQL injection via `placa` or `uuid_ingreso` payload | Stale / malicious client passes raw SQL fragment in placa | V3 regex server-side rejects non-`FORMATO_AUTO` / `FORMATO_MOTO` patterns with 422 BEFORE any SQL is constructed (only when placa provided); `detectar_tipo_vehiculo` uses parameterized SQL (F1.6 reuse); `buscar_ingreso_activo_por_uuid` uses bind params; `calcular_cotizacion` is PL/pgSQL (F1.8, no injection surface) | Low | D-HU-F1.7-6 (bypass scope), D-HU-F1.7-10 (placa optional) |
| **T2** | Cross-tenant bypass: operador- JWT from sucursal X POSTs `uuid_ingreso` of sucursal Y's ingreso to pollute Y's `prod.salidas` | Stale client or replay queue attempts to close another branch's income | KD-3 chain validates `target_sucursal = ingreso.uuid_sucursal` for `operador-` (Step 3 post-V1); `admin-` bounded by `claims["sucursales_permitidas"]` (already enforced in `get_tenant_ctx`); SQLAlchemy event listener `set_tenant_context` auto-filters SELECT | Low | D-HU-F1.7-9 (KD-S2, post-V1) |
| **T3** | Stale client sends `tipo_salida: "ROTACION"` (an attempt to inject the non-existent column) | Stale client or malicious actor tries to override server-side derivation | Pydantic `extra='forbid'` (inherited from `_Base`) rejects the field with 422 BEFORE the handler runs; client receives 422 with a clear discriminator | Low | D-HU-F1.7-2 (DEC-SUC-21-NEW), D-HU-F1.7-19 (typed schemas) |
| **T4** | Operator typos motivo as `[FORZADO: x]` (3 chars) to force a tarifa-bypass exit | Malicious operator wants to insert a salida without proper audit | KD-FORZADO-01 helper (F1.6 reuse) rejects motivo < 10 chars with `422 motivo_forzado_insuficiente`; the alert is only emitted when V5 is bypassed with motivo ≥ 10 chars; operator's intent is recorded but cannot bypass the substantive-reason gate | Low | D-HU-F1.7-5 (FORZADO_MIN_MOTIVO_CHARS=10) |
| **T5** | Tarifa closes between `cotizar` and INSERT `salidas` (lock continuity gap) | Worker/admin updates `tarifas_sucursal.vigente_hasta` between the two operations | KD-S7: `prod.calcular_cotizacion` (F1.8 PL/pgSQL) invoked inline within the same TX; `FOR SHARE` lock on `tarifas_sucursal` held until `session.commit()`; no other TX can modify the row | Low | D-HU-F1.7-7 (KD-S7), KD-1 from F1.8 |
| **T6** | Two concurrent requests both pass V1 EXISTS check and create duplicate salidas (TOCTOU race) | Bursts of N operadores at the same branch | Partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4) closes the window; `IntegrityError(23505) → SalidaDuplicada → 409`; integration test T12 verifies with `asyncio.gather` | Low | D-HU-F1.7-16 (KD-S16), D-HU-F1.7-3 (DEC-SAL-01) |
| **T7** | Alerta orphaned when INSERT `salidas` succeeds but alerta INSERT fails (FK constraint) | Catalog `tarifa_vigente_forzado` typo, FK to `prod.alerta` missing | D-HU-F1.7-12 (KD-S5): same `await session.commit()` covers both rows; FK commit ordering guarantees alerta only commits if salida OK; integration test T11 verifies rollback path | Low | D-HU-F1.7-12 (KD-S12 same-TX), D-HU-F1.7-7 Layer 4 |
| **T8** | Future developer reorders V8 before V2 in the handler | Refactor PR moves the tarifa check earlier to "fail fast" | AST walk `test_salida_handler_step_order.py` (File 5) verifies the literal order; CI gate catches reorderings before merge; KD-S7 invariant | Low | D-HU-F1.7-20 (AST walk gate), D-HU-F1.7-7 Layer 5 |
| **T9** | `impuestos.IVA` row not seeded, every cotización returns 500 | Pre-0026 deploy in a fresh environment | MIGRATION 0026 Op 2 inline-seeds `impuestos.IVA` (`codigo='IVA'`, `porcentaje=0.19`); pre-flight Op 1 aborts if `prod.impuestos` missing; integration test T13 verifies the 500 path | Low | D-HU-F1.7-4 (DEC-IMP-01), KD-IVA from F1.8 |

**Notes.** The threats in scope (HTTP / DB / catalog / lock / future-dev reordering) fall under the design's boundaries. No additional threat rows are required.

## 15. Traceability Matrix

The traceability map bridges the 11 REQ-OPS-NNN introduced by F1.7 to the design sections, skeleton files, and the tests that prove them. Each row is a **must-pass** contract; missing any row is a verification failure.

| REQ-OPS | Description | Design Section | Skeleton File | Test File |
|---|---|---|---|---|
| **REQ-OPS-042** | POST /operacion/salidas contract with KD-3 tenant scope | §4 (architecture), §6 (API), §7 (handler) | `backend/.../api/v1/operacion.py::create_salida` (§7, +200 LOC) | T1..T10 (File 1) |
| **REQ-OPS-043** | V1 ingreso activo exists; unified 404 discriminator | §3 D-HU-F1.7-8 (KD-S1), §7 Step 2 | `backend/.../repo/salida.py::buscar_ingreso_activo_por_uuid` (§9.2) + `schemas/operacion.py::IngresoNoEncontradoError` (§9.4) | T1 (rotation success implies V1 passed), T5 (mensualidad success), T6 (V2 422 implies V1 passed), T8 (V3 422 implies V1 passed) |
| **REQ-OPS-044** | V2 subscripción vigente al momento salida (F1.6 reuse) | §3 D-HU-F1.7-6 (bypass scope), §7 Step 4 | `backend/.../repo/subscripcion_activa.py::validar_subscripcion_vigente` (F1.6, NO modify) | T6 (V2 422), T7 (V2 bypass + alerta) |
| **REQ-OPS-045** | V3 placa matches ingreso (F1.6 reuse) | §3 D-HU-F1.7-6 (bypass scope), §7 Step 5 | `backend/.../repo/placa.py::detectar_tipo_vehiculo` (F1.6, NO modify) | T8 (V3 422) |
| **REQ-OPS-046** | V4 KD-FORZADO-01 prefix contract (F1.6 verbatim reuse) | §3 D-HU-F1.7-5, §7 Step 6 | `backend/.../repo/ingreso.py::validar_kd_forzado` (F1.6, NO modify) | T1..T2 (File 2), T9..T10 (File 1) |
| **REQ-OPS-047** | V5 tarifa vigente via F1.8 PL/pgSQL; lock FOR SHARE continuity | §3 D-HU-F1.7-7 (KD-S7), §7 Step 7, §10 (Locking) | `backend/.../repo/cotizacion.py::cotizar_ingreso` (F1.8, NO modify) | T1..T3 (File 1), T13 (File 3) |
| **REQ-OPS-048** | INSERT `prod.salidas` `[A]` append-only via DEC-SAL-01 | §3 D-HU-F1.7-3 (DEC-SAL-01), §7 Step 8, §9.1 (model) | `backend/.../repo/salida.py::crear_salida_evento` (§9.2) | T1, T5 (happy paths imply INSERT succeeded) |
| **REQ-OPS-049** | `tipo_salida` derived server-side; never persisted | §3 D-HU-F1.7-2 (DEC-SUC-21-NEW), §7 Step 11, §9.4 (schemas) | `backend/.../schemas/operacion.py::SalidaReadForzado.tipo_salida` (§9.4) | T1 (`tipo_salida=="ROTACION"`), T5 (`tipo_salida=="MENSUALIDAD"`) |
| **REQ-OPS-050** | Alerta same-TX for V2/V5 bypass | §3 D-HU-F1.7-12 (KD-S5), §7 Step 9, §9.2 (insertar_alerta_salida_forzado) | `backend/.../repo/salida.py::insertar_alerta_salida_forzado` (§9.2) | T3, T7 (File 1), T11 (File 3) |
| **REQ-OPS-051** | Partial unique index `one_exit_per_ingreso`; 409 mapping | §3 D-HU-F1.7-16 (KD-S16), §8 (Migration 0026 Op 4), §9.2 (SalidaDuplicada) | `backend/.../repo/salida.py::SalidaDuplicada` (§9.2) + `migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py` (§8) | T4 (File 1), T12 (File 3) |
| **REQ-OPS-052** | Inline-seed `impuestos.IVA`; KD-IVA blocker resolved | §3 D-HU-F1.7-4 (DEC-IMP-01), §8 (Migration 0026 Op 1+2), §9.3 (impuestos repo) | `migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py::upgrade` Op 2 + `backend/.../repo/impuestos.py::seed_iva_inline` (§9.3, F1.8 reuse) | T13 (File 3), T14 (File 4) |

**Coverage proof.** Every REQ-OPS-NNN (042..052, 11 rows) maps to (a) one or more design decisions (D-HU-F1.7-N), (b) at least one section of this design.md (1..15), (c) at least one skeleton file (in §7, §8, §9, §10), and (d) at least one test (T1..T14 across Files 1..6). Missing a single row breaks the design's gate; the `tests/` and `migrations/versions/` apply phases reference this matrix as their acceptance ledger.

---

## 16. Operational Notes

**Apply ordering.** When `sdd-apply` consumes this design.md, the implementation order is:

1. **Migration 0026 first** (§8) — `alembic upgrade head` must succeed before any code change. The migration is idempotent (T14). If MIGRATION 0026 fails, the design cannot be applied to a clean DB; this is a hard pre-condition.
2. **Models second** (§9.1) — `models/L_S/salida.py` is the only new ORM model; it must be mapped before any repo helper can write to `prod.salidas`.
3. **Repo helpers third** (§9.2 + §9.3) — `repo/salida.py` (4 functions) + `repo/impuestos.py` (F1.8 reuse, no new LOC) must be importable before the handler.
4. **Schemas fourth** (§9.4) — `SalidaCreate`, `SalidaRead`, `SalidaReadForzado` + 3 error discriminators must be defined before the handler signature is type-checked.
5. **Handler fifth** (§7) — `create_salida` (~200 LOC) registers on the existing `APIRouter` of `api/v1/operacion.py`. The handler MUST be appended after `create_ingreso` (currently ending at line 294), around lines 296-510.
6. **AST walks last** (§12) — both static gates live in `tests/static/` and reference the handler + repo paths by absolute `pathlib.Path`. They should run in `pre-commit` and the CI `static-checks` job.
7. **Tests seventh** (§13) — 14 tests across 6 files. Run with `pytest -m unit` (T1..T10) and `pytest -m integration -k salida` (T11..T14) with `PARKOS_DOCKER_TEST=1`.

**Idempotency checks.**

- MIGRATION 0026: `ADD COLUMN IF NOT EXISTS` (N/A — no ADD COLUMN), `INSERT ... ON CONFLICT DO NOTHING` for IVA + 2 alert_types (Op 2 + Op 3), `CREATE INDEX IF NOT EXISTS` for `one_exit_per_ingreso` (Op 4). Verified by T14.
- Handler: each request opens one transaction; the 12-step chain is read-only except Steps 8 (INSERT salida) and 9 (INSERT alerta). Re-running after a network failure returns 5xx without partial state (single commit).
- Repo: `crear_salida_evento` flushes before commit; `IntegrityError(23505)` on the unique index raises `SalidaDuplicada` BEFORE the alerta insert; the handler maps to 409 and the request terminates without commit.

**Reversibility.** The single Alembic downgrade (§8) reverses all 4 operations: DELETE `one_exit_per_ingreso` index → DELETE `alert_types` rows → DELETE `impuestos.IVA` row → DROP pre-flight no-op. The downgrade runs as superuser (alembic) and respects `alert_types_inmutable` / `impuestos_inmutable` triggers by deleting with `WHERE tipo_alerta='…'` / `WHERE codigo='IVA'` (deterministic PK-based filter). Any `prod.salidas` rows inserted by HU-F1.7 are retained; the table is not dropped (R8 risk note: `prod.salidas` is FK target for `prod.factura_detalle.uuid_salida` in ER 780-794, so it cannot be dropped post-Fase-1).

**Cross-HU debt.** F1.7 consumes:

- F1.6 helpers (NO modify): `repo/ingreso.py::validar_kd_forzado`, `repo/subscripcion_activa.py::validar_subscripcion_vigente`, `repo/placa.py::detectar_tipo_vehiculo`, `repo/alerta.py::insertar_alerta_forzado` (forzado payload pattern reused). Verified by `f16_helpers_intact` CI gate.
- F1.8 helpers (NO modify): `repo/cotizacion.py::cotizar_ingreso`, the PL/pgSQL `prod.calcular_cotizacion`, the typed exceptions (`CotizacionError`, `IngresoNoEncontrado`, `TarifaNoVigente`, `IVANoConfigurado`). Verified by `f18_helpers_intact` CI gate.

**Out of scope (deferred).**

- `prod.anulaciones(tipo_anulable='salida')` workflow — Fase 7+ per DEC-SAL-01.
- `V_SALIDA_TIPO` view (4FN-friendly `tipo_salida` query path) — out of scope per proposal §3.2.
- Real-time WS push of `tipo_salida` to operator UI — Fase 9.
- Billing integration (`prod.factura_detalle`) — HU-F1.9 (Fase-1 Parte II).

---

**END OF DESIGN — `hu-f1-7-salidas`**

The next phase is **sdd-tasks**, which decomposes this design into a sequenced `tasks.md` (typically 6-10 tasks mirroring the apply ordering in §16 step 1..7). `sdd-spec` is currently in flight and will deliver `specs/operational/spec.md` with REQ-OPS-042..052 in canonical Given/When/Then/And form; the design's traceability matrix (§15) references these IDs as placeholders until sdd-spec lands.