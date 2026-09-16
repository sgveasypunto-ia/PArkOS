# Proposal: HU-F1.7 — Server-side enforcement of `POST /operacion/salidas` (rotación + mensualidad derivation)

> **Change**: `hu-f1-7-salidas`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.7 (Fase-1 prerequisites — backend)
> **Inputs**: `openspec/changes/hu-f1-7-salidas/exploration.md` (16 sections, 220 LOC,
> written 2026-09-14), `plan.md` (HU-F1.7 lines 798-841, CU-01/02/03M context lines
> 1715, 2400-2402, 2525, 2615, 7438-7447, 7500-7501, 7670-7671), `modelo_datos_er.mmd`
> (`prod.salidas` 761-777 [A], `prod.ingreso` 577-596 [L-E], `prod.impuestos` 187-207
> [V], `prod.tarifas_sucursal` 406-426 [V], `prod.subscripciones_cliente` 496-518 [V],
> `prod.alert_types` [V], `prod.alerta` [L-W]), `openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/`
> (precedente KD-FORZADO-01 verbatim reuse, commit `2a2cbd2`), `openspec/changes/archive/2026-09-14-hu-f1-8-cotizar/`
> (precedente PL/pgSQL `calcular_cotizacion` VOLATILE with KD-1 `FOR SHARE` lock continuity,
> commit `a3d0c39`), `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py::create_ingreso`
> (KD-3 tenant scope chain + `_ingreso_issuer_dep` reuso, lines 86-294),
> `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py::validar_kd_forzado`
> (F1.6 verbatim helper), `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py::validar_subscripcion_vigente`
> (F1.6 helper, reuso para V2), `backend/packages/parkos_core/src/parkos_core/repo/cotizacion.py::cotizar_ingreso`
> (F1.8 thin wrapper, reuso para V5).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend`
> (HEAD `2a2cbd2`) · **PR target**: `origin/dev`.

## 1. Why

Until F1.6 (archived in `21097c8`), only `POST /api/v1/operacion/ingresos` existed with
11 server-side validations. The symmetric `POST /api/v1/operacion/salidas` did not exist
in the router (zero `grep` matches in `backend/` confirmed during F1.8 exploration). The
helper `resolve_active_subscription_for_exit` (T-PR5-016) already lived in
`api/v1/operacion.py:500-562` since PR5, but no HTTP handler invoked it. `plan.md` line
7438–7447 specifies `POST /operacion/salidas` and `POST /operacion/salidas/mensualidad`
as the two endpoints that close CU-01 (salida rotación), CU-02 (salida con cobro
facturado) and CU-03M (salida de mensualidad).

The operator screen at the parking lot accepts a vehicle at exit; the moment the user
clicks "Registrar salida", the client runs **partial validations** before POSTing to the
backend: identification by `uuid_ingreso`, optional placa confirmation, optional
forzado bypass. Today, no backend handler exists for this flow — the operator's screen
must either duplicate the derivation logic client-side (reintroducing the bug class F1.6
fixed for ingresos) or rely on an undocumented internal procedure. **The backend performs
zero business validation on salidas.**

This creates five concrete risks that HU-F1.7 resolves:

1. **Salida duplicada / cross-tenant bypass** — without server-side validation, a stale
   client or alternate consumer can submit the same `uuid_ingreso` twice and create two
   `prod.salidas` rows. The DB has `REVOKE UPDATE, DELETE` + trigger `fn_salidas_inmutable`
   (migration 0001 lines 1990-2003, 2923) but no constraint preventing duplicate inserts.
   Defense-in-depth is absent.
3. **Tipo derivativo client-side** — `tipo_salida = MENSUALIDAD | ROTACION` is currently
   derived client-side from the pre-classification the operator's UI performs. The corpus
   requires server-side derivation (analogue of DEC-SUC-21 for ingreso) with the value
   returned in the response and **never persisted** in `prod.salidas`.
4. **KD-IVA blocker (F1.8 deployment)** — `impuestos.IVA` is not seeded in any migration
   0001-0025 (`grep "INSERT INTO prod.impuestos"` → 0 matches confirmed in F1.8
   exploration:56). Every cotización returns `500 iva_no_configurado`. F1.7's MIGRATION
   0026 closes this blocker inline (orchestrator pre-decision: apply of F1.7 advances the
   F1.8 blocker as a side effect, mirroring F1.6's `INSERT … ON CONFLICT (tipo_alerta)
   DO NOTHING` pattern).
5. **Lock continuity gap** — F1.8 holds `SELECT … FOR SHARE` on `tarifas_sucursal` inside
   the PL/pgSQL `calcular_cotizacion` (D-HU-F1.8-1, KD-1). If F1.7 invokes
   `calcular_cotizacion` in a different transaction from the INSERT into `salidas`, the
   lock is released between cotizar and registrar — opening a window where another TX
   closes the tarifa between cotizar and cobrar. F1.7 invokes `calcular_cotizacion`
   inline within the same handler TX (KD-S7).

F1.7 consolidates the **two endpoints from plan.md** (`POST /operacion/salidas` rotación
+ `POST /operacion/salidas/mensualidad`) into **one handler** that derives `tipo_salida`
server-side from F1.8's `cobrar` flag. This is the orchestrator's consolidation decision
(DEC-MONO-01, exploration §6): reduces surface area, reuses F1.8's lock atómicamente,
makes the client indifferent to the path. The handler enforces 5 validations
(V1 ingreso activo, V2 subscripción vigente al momento salida, V3 placa matches ingreso,
V4 KD-FORZADO-01 prefix contract, V5 tarifa vigente via F1.8 PL/pgSQL), inserts the
salida event, optionally inserts alerta for V2/V5 bypass, and returns `201` with the
derived `tipo_salida` and the `cotizacion_snapshot` (only for ROTACION).

F1.7 closes three contractual dependencies declared in `plan.md`:

- **CU-02 — Salida con cobro facturado (rotación)**: backend validates tarifa vigente
  at the moment of exit, persists the lifecycle event, snapshot the fiscal breakdown.
- **CU-03M — Salida de mensualidad**: backend returns `cobrar:false` from F1.8's PL/pgSQL
  via `resolve_active_subscription_for_exit`; F1.7 derives `tipo_salida=MENSUALIDAD`.
- **F8 — Facturación (HU-F1.9)**: F1.9 reads `prod.salidas` + `cotizacion_snapshot` to
  assemble `factura_detalle` (ER 780-794) with the desglose fiscal (`subtotal`, `iva`,
  `total`) and emits the factura.

The work is **handler + repo layer + schema + one Alembic migration** — the migration
is critical (MIGRATION 0026: KD-IVA inline-seed + 2 alert_types + partial unique index
`one_exit_per_ingreso`). Without 0026 applied, every salida returns `500
iva_no_configurado`. The 4-operation breakdown with explicit pre-flight (KD-7 pattern
from F1.6) is documented in §8 Approach.

## 2. Decision Summary

| # | Decision | Rationale |
|---|---|---|
| **D-HU-F1.7-1 (DEC-MONO-01)** | **One handler** `POST /api/v1/operacion/salidas` that derives `tipo_salida` server-side from F1.8's `cobrar` flag — NOT two endpoints (`/salidas` + `/salidas/mensualidad`) | Orchestrator consolidation; reduces surface area; reuses F1.8's atomic lock; client is indifferent to path; aligns with DEC-SUC-21 pattern from F1.6 |
| **D-HU-F1.7-2 (DEC-SUC-21-NEW)** | `tipo_salida = MENSUALIDAD | ROTACION` derived server-side from `cobrar`; returned in `SalidaReadForzado`; **NEVER persisted** in `prod.salidas` (no column, by 4FN design) | Analogue of DEC-SUC-21 for ingreso (F1.6); avoids 4FN violation; view `V_SALIDA_TIPO` may be added in future HU if direct query is needed |
| **D-HU-F1.7-3 (DEC-SAL-01)** | `salidas` is append-only `[A]` event; **NEVER UPDATE** post-creation; corrections via `prod.anulaciones(tipo_anulable='salida')` workflow (Fase 7+) | Defense in depth at DB layer: `REVOKE UPDATE, DELETE` already applied (migration 0001 línea 2923) + trigger `fn_salidas_inmutable` (líneas 1990-2003) + partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4) |
| **D-HU-F1.7-4 (DEC-IMP-01)** | `impuestos.IVA` inline-seeded in MIGRATION 0026 (apply of F1.7), via `INSERT … ON CONFLICT (codigo, vigente_desde) DO NOTHING` with `porcentaje=0.19` (IVA Colombia 2026 regulatory constant, locked in F1.8 design.md §4 KD-IVA) | KD-IVA blocker for F1.8 resolved as F1.7 side effect; ownership still HU-F14.2 Parte II but apply advances the dependency; mirrors F1.6 alert_type seed pattern (migration 0025) |
| **D-HU-F1.7-5 (DEC-FORZADO-01 reuse)** | KD-FORZADO-01 prefix contract (`[FORZADO: <motivo ≥10 chars>]` in `observaciones`) **reused verbatim** from F1.6 (`repo/ingreso.py::validar_kd_forzado`); same 422 errors (`motivo_forzado_requerido`, `forzado_contradiccion`, `motivo_forzado_insuficiente`); same tests (4 already exist in F1.6) | One implementation, one test, one audit; preserves uniform bypass contract across ingresos and salidas |
| **D-HU-F1.7-6** | Bypass scope is **narrower** in F1.7 vs F1.6: applies to V2 (subscripción vencida) and V5 (tarifa no vigente) ONLY; V1 (ingreso activo), V3 (placa matches) are NOT bypassable | V1/V3 are correctness invariants (without ingreso, no hay nada que cerrar; placa mismatch is bug, not operational state); V2/V5 are operational state that may change between ingreso and salida |
| **D-HU-F1.7-7 (KD-S7 lock continuity)** | F1.7 invokes `prod.calcular_cotizacion(:uuid_ingreso)` **inside the same transaction** as the INSERT into `salidas`; single `await session.commit()`; NO sub-transactions; NO `SAVEPOINT` | F1.8 PL/pgSQL is `VOLATILE` (REQ-OPS-025 deviation letter, user approved 2026-09-14); the `FOR SHARE` lock on `tarifas_sucursal` acquired by F1.8 must remain held through the INSERT for atomicity (KD-1 invariant from F1.8 design.md §6 Cross-HU) |
| **D-HU-F1.7-8 (KD-S1 unified 404)** | `404 ingreso_no_encontrado` is the **single** response when `uuid_ingreso` doesn't exist, when ingreso already has a salida (not anulada), or when the ingreso was anulado | Operational equivalence: in all three cases, there is nothing to close; simplifies error taxonomy; defense-in-depth — no information leak about internal state |
| **D-HU-F1.7-9 (KD-S2 tenant scope post-V1)** | Tenant scope check happens **after V1** (`404 ingreso_no_encontrado` first, then `403 tenant_scope_violation` if `operador-` with cross-branch `ingreso`); 404 before 403 (defense-in-depth, no info leak) | UX rationale: if the operador doesn't have access to the uuid_ingreso, returning 403 before 404 leaks "the uuid exists somewhere". Better UX is 404 first (no leak), then 403 if exists |
| **D-HU-F1.7-10 (KD-S3 placa optional)** | `placa` in `SalidaCreateForzado` is **optional**; if provided, server confirms against `ingreso.placa` (V3); if absent, server trusts `uuid_ingreso` | UX: operator may know `uuid_ingreso` from a scan but not the placa; client trusts server's authoritative uuid→placa mapping |
| **D-HU-F1.7-11 (KD-S4 cotizacion_snapshot scoped)** | `cotizacion_snapshot: CotizarFacturacion | None` in response is **None** when `tipo_salida=MENSUALIDAD` (no desglose fiscal needed, monthly subscribers don't get billed for this exit); populated when `tipo_salida=ROTACION` | Smaller response shape when MENSUALIDAD; client logic simplified (no "did they pay or not?" branching); matches the business reality |
| **D-HU-F1.7-12 (KD-S5 distinct alerta types)** | Two NEW `alert_types` seeded in MIGRATION 0026 Op 3: `subscripcion_vencida_forzado` (only if V2 bypassed) and `tarifa_vigente_forzado` (only if V5 bypassed); both `severity='warning'`; inserted in **same TX** as the salida INSERT | Differentiated reporting without string concat; defense-in-depth against orphan alertas (R5); one alerta per bypassed validation |
| **D-HU-F1.7-13 (KD-S6 retención 2 años)** | `fecha_retencion_hasta = fecha_salida + 2 years` (computed server-side); consistent with operational retention for other `[A]` tables (`anulaciones`, `reimpresion_ticket`); enables monthly partitioning on `fecha_retencion_hasta` | Operational retention; alignment with existing pattern |
| **D-HU-F1.7-14** | New `models/L_S/salida.py` ORM (~40 LOC) based on `LifecycleEventBase` with audit + sync mixins; **closes pre-existing gap** (`salidas` table exists in DB since migration 0001 but had no ORM); INSERT-only via `repo/salida.py::crear_salida_evento` | Defense-in-depth at ORM layer; consistency with `Ingreso` (F1.5/F1.6); avoids raw SQL for INSERT |
| **D-HU-F1.7-15** | New `repo/salida.py` (~180 LOC): `buscar_ingreso_activo_por_uuid` (V1), `cotizar_para_salida` (V5 thin wrapper over F1.8), `crear_salida_evento` (Step 8 INSERT + `IntegrityError → SalidaDuplicada`), `insertar_alerta_salida_forzado` (Step 9, alerts for V2/V5 bypass); new `repo/impuestos.py` (~50 LOC) with `validar_iva_configurado` (read helper for HU-F14.2 audit + test mocks) | Encapsulates SQL + bi-temporal predicates + lock boundaries; testable without HTTP; consistent with F1.6 `repo/ingreso.py` and F1.8 `repo/cotizacion.py` |
| **D-HU-F1.7-16 (KD-V8 partial unique index)** | MIGRATION 0026 Op 4: `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso ON prod.salidas (uuid_ingreso) WHERE NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida = prod.salidas.uuid AND a.tipo_anulable = 'salida' AND a.estado = 'ejecutada')` | Same pattern as `unique_active_sesion_per_user` (migration 0023, F1.3); closes TOCTOU race on V1 EXISTS subquery; `UniqueViolationError → 409 salida_duplicada`; `CONCURRENTLY` for no lock on reads/writes |
| **D-HU-F1.7-17 (DEC-IDEM-01 reuse)** | Idempotency via `Idempotency-Key` HTTP header (PR2 middleware); NOT `correlacion_id` in body | DEC-IDEM-01 from F1.6; avoids duplicating surface area |
| **D-HU-F1.7-18 (KD-V8 issuer parity)** | Both `operador-` and `admin-` can emit `forzado=true`; same pattern as F1.6 D-HU-F1.6-13 | RBAC differentiation deferred to future HU; alert + audit log detect abuse |
| **D-HU-F1.7-19** | Schemas `SalidaCreateForzado` (input: `uuid_ingreso`, optional `placa`, optional `observaciones`, optional `forzado`); `SalidaReadForzado` (output: existing Salida fields + `tipo_salida`, `forzado_en_creacion`, `motivo_forzado`, `cotizacion_snapshot`); 4 typed error classes (`IngresoNoEncontradoError`, `SalidaDuplicadaError`, `PlacaNoCoincideConIngresoError`, `TarifaVigenteNoEncontradaError`) | `extra='forbid'` (inherited from `_Base`); 422/404/409 with discriminators; rejects injection of `tipo_salida` field (DEC-SUC-21-NEW) |
| **D-HU-F1.7-20 (strict order)** | Validation order (D-HU-F1.7-11): KD-3 (issuer claims) → V1 ingreso activo exists → tenant scope (post-V1) → V2 subscripción vigente al momento salida → V3 placa matches ingreso → V4 KD-FORZADO-01 prefix contract → V5 tarifa vigente via F1.8 PL/pgSQL → INSERT salida `[A]` → alerta if V2/V5 bypassed → 201. AST walk `tests/static/test_salida_handler_step_order.py` locks the order literal | Defense-in-depth: V1 antes que tenant scope evita leak de existencia; V4 antes que V5 evita bypass por tarifa inválida; V8 al final garantiza rechazo de duplicado solo después de pasar todo lo demás |

## 3. Goals & Non-Goals

### 3.1 Goals

1. Expose **one** handler `POST /api/v1/operacion/salidas` that derives `tipo_salida`
   server-side from F1.8's `cobrar` flag, enforcing 5 validations (V1..V5) plus the
   KD-FORZADO-01 bypass contract.
2. Reuse `repo/ingreso.py::validar_kd_forzado` (F1.6) verbatim for V4 — one
   implementation, one test suite, one audit trail.
3. Reuse `repo/subscripcion_activa.py::validar_subscripcion_vigente` (F1.6) for V2
   revalidation at the moment of salida (subscripción may have expired since ingreso).
4. Reuse `repo/cotizacion.py::cotizar_ingreso` (F1.8 thin wrapper) for V5 — invoke
   PL/pgSQL `calcular_cotizacion` inline within the same TX as the salida INSERT
   (KD-S7 lock continuity).
5. Create `models/L_S/salida.py` ORM model (~40 LOC) closing the pre-existing gap —
   the `salidas` table has existed since migration 0001 but had no ORM mapping.
6. Create `repo/salida.py` (~180 LOC) with V1 (buscar_ingreso_activo_por_uuid), V5
   wrapper (cotizar_para_salida), Step 8 INSERT (crear_salida_evento with
   `IntegrityError → SalidaDuplicada`), Step 9 alert (insertar_alerta_salida_forzado).
7. Create `repo/impuestos.py` (~50 LOC) with `validar_iva_configurado(session)` helper
   for HU-F1.9 / HU-F14.2 audit + test mocks.
8. Resolve the **KD-IVA blocker** for F1.8 by inline-seeding `impuestos.IVA` in
   MIGRATION 0026 Op 2 (`codigo='IVA'`, `porcentaje=0.19`, `vigente_desde=NOW()`, `estado='activo'`).
10. Seed **2 alert types** in MIGRATION 0026 Op 3: `subscripcion_vencida_forzado`,
    `tarifa_vigente_forzado` (both `severity='warning'`).
11. Create **partial unique index** `one_exit_per_ingreso` on `prod.salidas` in
    MIGRATION 0026 Op 4 — closes TOCTOU race on V1 EXISTS subquery; `UniqueViolationError
    → 409 salida_duplicada`.
12. Maintain strict validation order (D-HU-F1.7-20) with AST walk
    `tests/static/test_salida_handler_step_order.py` to prevent reordering accidents.
13. Insert alert `subscripcion_vencida_forzado` or `tarifa_vigente_forzado` in **same
    transaction** as the salida INSERT (single `commit()`) — defense against orphan
    alerts (R5).
14. Cover with **14 tests**: 10 HTTP unit (rotación + mensualidad + KD-FORZADO +
    partial index) + 2 KD-FORZADO contract unit (F1.6 reuse) + 3 DB integration
    (insert+alert atomic, partial unique index → 409, IVA not seeded → 500) + 2 AST walks
    (step order literal, no UPDATE/DELETE/TRUNCATE in repo/salida.py).
15. Close three contractual dependencies: CU-02 (salida rotación), CU-03M (salida
    mensualidad), F8 facturación (HU-F1.9 reads `cotizacion_snapshot`).
16. Defense-in-depth with 5 layers (D-HU-F1.7-7): regex/KD-3 server-side + KD-FORZADO
    chain + alerta INSERT same-TX + AST walk ordering + partial unique index.

### 3.2 Non-Goals

1. NO second endpoint `POST /operacion/salidas/mensualidad` — consolidated into one
   handler with server-side derivation (DEC-MONO-01, orchestrator consolidation).
2. NO column `tipo_salida` in `prod.salidas` — derived server-side, returned in
   response, NEVER persisted (DEC-SUC-21-NEW, 4FN).
3. NO column `forzado` or `motivo` in `prod.salidas` — KD-FORZADO-01 contract reuses
   F1.6 prefix pattern; motivo lives in `prod.alerta.datos_nuevos` when bypassed.
4. NO lock pesimista on `prod.ingreso` SELECT (V1) — partial unique index closes
   TOCTOU race; `prod.ingreso` PK lookup is atomic; `EXISTS` subquery < 5ms p99.
5. NO lock pesimista on `prod.subscripciones_cliente` (V2) — read-mostly, admin
   actions are infrequent; race window acceptable.
6. NO `correlacion_id` in payload — DEC-IDEM-01 delegates idempotency to
   `Idempotency-Key` HTTP header (PR2 middleware, intact).
7. NO workflow de anulación (`prod.anulaciones` workflow for salidas) — DEC-SAL-01 +
   DEC-ANUL-01; deferred to Fase 7+ (`prod.salidas` is append-only; corrections via
   anulaciones table).
8. NO seeding of `impuestos.IVA` outside MIGRATION 0026 — apply of F1.7 is the single
   seed point. Re-seeding is a no-op (`ON CONFLICT DO NOTHING`).
9. NO view `V_SALIDA_TIPO` for direct tipo_salida query — derived from `cobrar` flag
   in `calcular_cotizacion` output. If a query needs the column, future HU creates the
   view.
10. NO numericacion de FE (factura electrónica) integration — Fase 8 (HU-F1.10);
    F1.7 only persists the lifecycle event, not the factura.
11. NO cleanup of client-side `tipo_salida` derivation — Fase 2 frontend scope; F1.7
    delivers server-side enforcement; client cleanup is post-archive.
12. NO modification to `IdempotencyKeyMiddleware` (PR2) — dedupe by header continues
    working; F1.7 handler only changes response shape in happy path (201) and adds
    404/409/422 before the INSERT.
13. NO modification to `migrations/versions/0022_create_calcular_cotizacion.py` — the
    PL/pgSQL function does not change; F1.7 invokes it.
14. NO modification to `models/L_E/ingreso.py` — V1 is read-only.
15. NO modification to `auth/tenancy.py` or `api/deps.py` — KD-3 chain intact.

## 4. Architecture Overview

```
HTTPS POST /api/v1/operacion/salidas
        Body: SalidaCreateForzado
        │      {uuid_ingreso, placa?, observaciones?, forzado?: bool = false}
        │  Idempotency-Key: <uuid>   (header, PR2 middleware)
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/operacion.py  (MODIFICAR, add create_salida lines ~296-360)           │
│                                                                              │
│ @router.post("/salidas", response_model=SalidaReadForzado, status_code=201) │
│ async def create_salida(payload, response, session, ctx, _claims)           │
│                                                                              │
│  1. KD-3 (issuer claims):                                                   │
│      _claims validated by requires_issuer("operador-", "admin-")             │
│      ctx from get_tenant_ctx                                                │
│                                                                              │
│  2. V1 (ingreso activo exists):                                            │
│      ingreso = await repo/salida.py::buscar_ingreso_activo_por_uuid(         │
│          session, uuid_ingreso=payload.uuid_ingreso)                        │
│      if ingreso is None:                                                    │
│          raise 404 {"error":"ingreso_no_encontrado", "uuid_ingreso":...}    │
│                                                                              │
│  3. tenant scope (post-V1, KD-S2):                                          │
│      target_sucursal = ingreso.uuid_sucursal                                │
│      if ctx.issuer_prefix == "operador-" and target != ctx.sucursal_uuid:   │
│          raise 403 {"error":"tenant_scope_violation", "uuid_ingreso":...}  │
│                                                                              │
│  4. V2 (subscripción vigente al momento salida):                           │
│      if ingreso.uuid_subscripcion_cliente is not None:                      │
│          sub_result = repo/subscripcion_activa.py::\                       │
│              validar_subscripcion_vigente(session, ...forzado=bool(bypass)) │
│          if not sub_result.vigente and not bypass:                           │
│              raise 422 {"error":"subscripcion_inactiva_o_vencida"}          │
│          if not sub_result.vigente and bypass:                              │
│              bypass_reason = "subscripcion_vencida"                         │
│                                                                              │
│  5. V3 (placa matches ingreso):                                             │
│      if payload.placa is not None:                                          │
│          tipo_req = repo/placa.py::detectar_tipo_vehiculo(payload.placa)    │
│          tipo_ing = repo/placa.py::detectar_tipo_vehiculo(ingreso.placa)    │
│          if tipo_req != tipo_ing:                                            │
│              raise 422 {"error":"placa_no_coincide_con_ingreso",...}        │
│                                                                              │
│  6. V4 (KD-FORZADO-01 prefix contract — F1.6 verbatim):                     │
│      motivo = repo/ingreso.py::validar_kd_forzado(                          │
│          payload.observaciones, payload.forzado)                            │
│      bypass_reason: str | None = "forzado" if motivo else None              │
│                                                                              │
│  7. V5 (tarifa vigente via F1.8 PL/pgSQL):                                  │
│      cotizacion = await repo/salida.py::cotizar_para_salida(                │
│          session, uuid_ingreso=payload.uuid_ingreso)                        │
│      # Invokes SELECT prod.calcular_cotizacion(:uuid) FOR SHARE              │
│      # Raises: IngresoNoEncontrado (covered V1), TarifaNoVigente,            │
│      #         IVANoConfigurado (post-0026 deploy: never)                   │
│      tipo_salida = "MENSUALIDAD" if cotizacion.cobrar is False              │
│                  else "ROTACION"                                            │
│      if "tarifa_no_vigente" sentinel and not bypass:                        │
│          raise 422 {"error":"tarifa_vigente_no_encontrada"}                  │
│      if "tarifa_no_vigente" sentinel and bypass:                            │
│          bypass_reason = "tarifa_no_vigente"                                │
│                                                                              │
│  8. INSERT salida [A] (KD-S6, KD-S7 same TX):                               │
│      new_attrs = {                                                          │
│          uuid_sucursal: target_sucursal,                                    │
│          uuid_ingreso: payload.uuid_ingreso,                                │
│          fecha_salida: datetime.now(UTC).replace(tzinfo=None),              │
│          fecha_retencion_hasta: date.today() + relativedelta(years=2),     │
│      }                                                                      │
│      new_row = await repo/salida.py::crear_salida_evento(                   │
│          session, actor_uuid=ctx.actor_uuid, new_attrs=new_attrs)           │
│      # IntegrityError("one_exit_per_ingreso") → 409 salida_duplicada        │
│                                                                              │
│  9. alertas same TX (KD-S12, R5):                                           │
│      if bypass_reason == "subscripcion_vencida":                             │
│          await repo/salida.py::insertar_alerta_salida_forzado(              │
│              session, ..., tipo_alerta="subscripcion_vencida_forzado")      │
│      elif bypass_reason == "tarifa_no_vigente":                             │
│          await repo/salida.py::insertar_alerta_salida_forzado(              │
│              session, ..., tipo_alerta="tarifa_vigente_forzado")            │
│      await session.commit()    ← UN solo commit (KD-S7 lock release)        │
│                                                                              │
│ 10. Derivar tipo_salida (DEC-SUC-21-NEW — already in Step 7):              │
│      # NUNCA persistir en prod.salidas (D-HU-F1.7-2)                        │
│                                                                              │
│ 11. response shape:                                                         │
│      apply_no_store_header(response)                                        │
│      await session.refresh(new_row)                                         │
│      return SalidaReadForzado(                                              │
│          uuid=new_row.uuid, ... +                                           │
│          tipo_salida=tipo_salida,                                           │
│          forzado_en_creacion=(bypass_reason is not None),                     │
│          motivo_forzado=motivo if bypass_reason else None,                   │
│          cotizacion_snapshot=CotizarFacturacion.model_validate(cotizacion)  │
│                            if tipo_salida == "ROTACION" else None,           │
│      )                                                                      │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                            ▲                       ▲
        │ AST walk                   │ AST walk              │ SELECT-only
        │ ordering gate              │ no-write gate         │ (with FOR SHARE
        │                            │                       │  on tarifas_sucursal)
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

The handler is thin + orchestador. All validation logic lives in `repo/*.py` and
PL/pgSQL. The single `commit()` materializes the salida + alerta atomically and
releases the `FOR SHARE` lock from F1.8's `calcular_cotizacion` (KD-S7).

## 5. Capabilities

### New

- **`operacion-salidas`** — covers the `POST /operacion/salidas` endpoint, the 5
  validations V1..V5, the KD-FORZADO-01 reuse contract, the server-side
  `tipo_salida` derivation, and the partial unique index `one_exit_per_ingreso`.
  Spec in `openspec/changes/hu-f1-7-salidas/specs/operacion-salidas/spec.md`,
  archived in `openspec/specs/operacion-salidas/spec.md` as **REQ-OPS-042..052**
  (11 requirements).
- **`repo/salida.py`** — helper module for salida lifecycle (V1 lookup, V5 wrapper,
  Step 8 append-only INSERT, Step 9 alert for V2/V5 bypass). Encapsulates SQL +
  bi-temporal predicates + lock boundaries.
- **`repo/impuestos.py`** — helper module for `impuestos.IVA` reads (HU-F14.2 audit +
  HU-F1.9 snapshot validation + test mocks).
- **`models/L_S/salida.py`** — ORM model for `prod.salidas`, closing the pre-existing
  gap (table exists since migration 0001 but no ORM mapping).
- **`catalog-impuestos`** — seed for `impuestos.IVA` row (KD-IVA blocker for F1.8
  resolved). Owned by F1.7 apply phase; HU-F14.2 Parte II keeps ownership of the
  catalog scope. Spec in `openspec/changes/hu-f1-7-salidas/specs/catalog-impuestos/spec.md`.

### Modified

- **`operations`** — the canonical capability adds REQ-OPS-042..052 (11 requirements):
  POST /operacion/salidas contract, V1..V5 validations, KD-FORZADO-01 prefix
  contract reuse, server-side `tipo_salida` derivation, alerta for V2/V5 bypass,
  partial unique index + 409 mapping, inline-seed `impuestos.IVA`. Spec deltada in
  `openspec/changes/hu-f1-7-salidas/specs/operations/spec.md`.
- **`api/v1/operacion.py::create_salida`** — NEW handler adjacent to
  `create_ingreso` (lines 132-294) at lines ~296-360; same `APIRouter` custom
  (`operacion.py:52`); same `_ingreso_issuer_dep` reuso. URL `/operacion/salidas`
  is brand new (not replacing an existing endpoint).
- **`schemas/operacion.py`** — add `SalidaCreateForzado` (input),
  `SalidaReadForzado` (output with `tipo_salida`, `forzado_en_creacion`,
  `motivo_forzado`, `cotizacion_snapshot`), 4 typed error classes
  (`IngresoNoEncontradoError`, `SalidaDuplicadaError`,
  `PlacaNoCoincideConIngresoError`, `TarifaVigenteNoEncontradaError`).
- **`migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py`** —
  NEW Alembic migration, `down_revision = "0025_alerta_datos_nuevos"`.

## 6. Data Model

`modelo_datos_er.mmd` tables `prod.salidas` (761-777, `[A]`),
`prod.ingreso` (577-596, `[L-E]`), `prod.impuestos` (187-207, `[V]`),
`prod.alert_types` (post-F1.6, `[V]`), `prod.tarifas_sucursal` (406-426, `[V]`,
post-F1.4 vigente_en), `prod.subscripciones_cliente` (496-518, `[V]`),
`prod.subscripcion_vehiculos` `[V]`, `prod.vehiculos` `[V]`, `prod.alerta` (L-W) —
**one Alembic migration introduces** the index + seeds the 3 rows.

**Columnas leídas/escritas** (todas existentes, sin DDL):

| Tabla | Columna | Operación | Línea ER / migration |
|---|---|---|---|
| `prod.ingreso` | `uuid`, `uuid_sucursal`, `placa`, `uuid_tipo_vehiculo`, `uuid_subscripcion_cliente`, `fecha_ingreso` | V1 SELECT (read-only) | 577-596 |
| `prod.salidas` | `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`, `fecha_retencion_hasta` | Step 8 INSERT | 761-777 |
| `prod.salidas` | `uuid_ingreso` | (Op 4) partial unique index | 761-777 |
| `prod.subscripciones_cliente` | `fecha_vencimiento`, `estado`, `vigente_hasta` | V2 SELECT | 496-518 |
| `prod.subscripcion_vehiculos` | `uuid_subscripcion`, `uuid_vehiculo` | V2 junction | 538-557 |
| `prod.vehiculos` | `placa`, `uuid` | V3 via placa | 519-537 |
| `prod.tarifas_sucursal` | `vigente_desde`, `vigente_hasta`, `estado`, `valor`, `valor_plena` | V5 SELECT FOR SHARE | 406-426 |
| `prod.impuestos` | `nombre='IVA'`, `porcentaje` | V5 SELECT (post-0026) | 187-207 |
| `prod.impuestos` | new row `codigo='IVA', porcentaje=0.19` | (Op 2) INSERT | — |
| `prod.alert_types` | new rows `subscripcion_vencida_forzado`, `tarifa_vigente_forzado` | (Op 3) INSERT | — |
| `prod.alerta` | `tipo_alerta`, `estado`, `datos_nuevos` | Step 9 INSERT (V2/V5 bypassed) | L-W |

**DDL nuevo** (migración `0026`):

```sql
-- Op 1 — Pre-flight (KD-7 pattern F1.6)
DO $$
DECLARE
    _n_impuestos bigint;
    _n_salidas bigint;
    _n_alert_types bigint;
BEGIN
    SELECT count(*) INTO _n_impuestos FROM pg_catalog.pg_class
        WHERE relname='impuestos' AND relnamespace='prod'::regnamespace;
    IF _n_impuestos IS NULL OR _n_impuestos = 0 THEN
        RAISE EXCEPTION '0026_preflight_abort: tabla prod.impuestos no existe. Aplique migrations 0001-0025 antes.';
    END IF;

    SELECT count(*) INTO _n_salidas FROM pg_catalog.pg_class
        WHERE relname='salidas' AND relnamespace='prod'::regnamespace;
    IF _n_salidas IS NULL OR _n_salidas = 0 THEN
        RAISE EXCEPTION '0026_preflight_abort: tabla prod.salidas no existe.';
    END IF;

    SELECT count(*) INTO _n_alert_types FROM pg_catalog.pg_class
        WHERE relname='alert_types' AND relnamespace='prod'::regnamespace;
    IF _n_alert_types IS NULL OR _n_alert_types = 0 THEN
        RAISE EXCEPTION '0026_preflight_abort: tabla prod.alert_types no existe.';
    END IF;
END $$;

-- Op 2 — Inline-seed impuestos.IVA (KD-IVA resolver)
INSERT INTO prod.impuestos (
    uuid, codigo, nombre, porcentaje,
    vigente_desde, vigente_hasta, estado, created_at
) VALUES (
    gen_random_uuid(), 'IVA', 'IVA', 0.19,
    NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
)
ON CONFLICT (codigo, vigente_desde) DO NOTHING;

-- Op 3 — Inline-seed 2 alert types (F1.7 alerts)
INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
VALUES
    ('subscripcion_vencida_forzado',
     'Salida vehicular forzada por administrador al detectar subscripción vencida al momento de salida',
     'warning'),
    ('tarifa_vigente_forzado',
     'Salida vehicular forzada por administrador al detectar tarifa no vigente al momento de salida',
     'warning')
ON CONFLICT (tipo_alerta) DO NOTHING;

-- Op 4 — Partial unique index one_exit_per_ingreso (KD-S16)
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso
    ON prod.salidas (uuid_ingreso)
    WHERE NOT EXISTS (
        SELECT 1 FROM prod.anulaciones a
        WHERE a.uuid_salida = prod.salidas.uuid
          AND a.tipo_anulable = 'salida'
          AND a.estado = 'ejecutada'
    );
```

**Downgrade** (reverse order):

```sql
DROP INDEX IF EXISTS prod.one_exit_per_ingreso;
DELETE FROM prod.alert_types
    WHERE tipo_alerta IN ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado');
DELETE FROM prod.impuestos WHERE codigo='IVA' AND estado='activo';
```

`DELETE` runs as superuser (alembic) to bypass the `alert_types_inmutable` trigger
(migration 0013). The `impuestos` DELETE may collide with `impuestos_inmutable` if
the trigger exists — verification pre-F1.7-apply pending (R8 risk). Workaround: NO
downgrade in production; create compensatory migration if needed.

**Why no model schema changes**: the handler operates on existing columns (V1 reads
ingreso, Step 8 inserts salida); no new columns in `prod.salidas` for `tipo_salida`
(DEC-SUC-21-NEW veda), `forzado`, or `motivo` (KD-FORZADO-01 veda). The motivo lives
in `prod.alerta.datos_nuevos` (jsonb) when bypassed.

**Sync catalog impact**: zero changes. The `salidas` table is `[A]` (audit), not
synced to cloud (same as `anulaciones`, `reimpresion_ticket`). New alert_types rows
are `[V]` reference data; if HU-F14.2 Parte II sync covers `alert_types`, the
seeded rows propagate via the existing sync pipeline.

## 7. API Surface

| Path | Method | Cambio | Issuer / rol |
|---|---|---|---|
| `/api/v1/operacion/salidas` | POST | NEW endpoint; URL not previously registered; response body gains `tipo_salida`, `forzado_en_creacion`, `motivo_forzado`, `cotizacion_snapshot` | `operador-`, `admin-` |

**Request signature**:

```python
async def create_salida(
    response: Response,
    payload: SalidaCreateForzado,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),
) -> SalidaReadForzado:
```

**Body `SalidaCreateForzado`**:

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

**Response `SalidaReadForzado`** (201):

```python
class SalidaReadForzado(_Base):
    """Response shape for ``POST /operacion/salidas`` (HU-F1.7).

    Additive delta to ``SalidaRead``:
    - ``tipo_salida``: Literal['MENSUALIDAD', 'ROTACION'] (DEC-SUC-21-NEW)
    - ``forzado_en_creacion``: True iff KD-FORZADO-01 bypass was used
    - ``motivo_forzado``: stripped motivo, or None
    - ``cotizacion_snapshot``: CotizarFacturacion if ROTACION, None if MENSUALIDAD
    """
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

**Errores tipados**:

| HTTP | Body | Cuándo | KD |
|---|---|---|---|
| 400 | `{"error":"missing_sucursal_context"}` | unlikely (server resolves from ingreso) | KD-3 |
| 403 | `{"error":"tenant_scope_violation"}` | `operador-` with `ingreso.uuid_sucursal != ctx.sucursal_uuid` | KD-S2 (post-V1) |
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

**Headers**: `Cache-Control: no-store` (alineado con F1.3/F1.5/F1.6/F1.8 precedents).

**Sin cambios sobre**:

- `POST /operacion/ingresos` (F1.6)
- `GET /operacion/ingresos/{uuid}` (F1.5)
- `GET /operacion/ingresos/{uuid}/estado` (F1.5)
- `GET /operacion/ingresos` (F1.5 list)
- `GET /operacion/ocupacion` (F1.5)
- `GET /operacion/cotizar?uuid_ingreso` (F1.8)

**Requirements planificados** (a ser formalizados en `specs/operations/spec.md` por
`sdd-spec`):

- `REQ-OPS-042` — handler `POST /api/v1/operacion/salidas` con `SalidaCreateForzado` /
  `SalidaReadForzado` contract; KD-3 tenant scope; `Cache-Control: no-store`.
- `REQ-OPS-043` — V1: ingreso activo exists (single 404 discriminator para "no
  existe / ya tiene salida / fue anulado").
- `REQ-OPS-044` — V2: subscripción vigente al momento salida (reuso verbatim de F1.6
  `validar_subscripcion_vigente`); 422 si no forzado; alerta si forzado.
- `REQ-OPS-045` — V3: placa matches ingreso (reuso verbatim de F1.6
  `detectar_tipo_vehiculo`); 422 sin bypass (correctness invariant).
- `REQ-OPS-046` — V4: KD-FORZADO-01 prefix contract reusado verbatim de F1.6
  (`repo/ingreso.py::validar_kd_forzado`); mismo 422 set.
- `REQ-OPS-047` — V5: tarifa vigente via `prod.calcular_cotizacion(:uuid_ingreso)`
  PL/pgSQL (F1.8 VOLATILE); lock FOR SHARE continuo en la misma TX (KD-S7).
- `REQ-OPS-048` — INSERT `prod.salidas` `[A]` append-only via
  `repo/salida.py::crear_salida_evento`; defensa in depth (REVOKE UPDATE,DELETE +
  trigger inmutable + partial unique index).
- `REQ-OPS-049` — `tipo_salida = MENSUALIDAD | ROTACION` derivado server-side del
  flag `cobrar` de `prod.calcular_cotizacion`; retornado en `SalidaReadForzado`;
  NUNCA persistido en `prod.salidas` (DEC-SUC-21-NEW).
- `REQ-OPS-050` — alerta same-TX (`subscripcion_vencida_forzado` para V2 bypass,
  `tarifa_vigente_forzado` para V5 bypass); una alerta por validación bypassed;
  insertada en el mismo `commit()` que el INSERT de salida (defense against R5).
- `REQ-OPS-051` — partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4);
  `UniqueViolationError` mapeado a `409 salida_duplicada`.
- `REQ-OPS-052` — inline-seed `impuestos.IVA` en MIGRATION 0026 Op 2 (`codigo='IVA'`,
  `porcentaje=0.19`, `vigente_desde=NOW() AT TIME ZONE 'UTC'`, `estado='activo'`);
  `ON CONFLICT (codigo, vigente_desde) DO NOTHING`; resuelve KD-IVA blocker de F1.8.

## 8. Approach

The implementation is **decomposed into 6 work units** that mirror the 12-step handler
chain (D-HU-F1.7-20). Each unit has autonomous scope, verification, and rollback.

### Unit 1 — ORM model + repo skeleton (no schema change)

Create `models/L_S/salida.py` (~40 LOC) and `repo/salida.py` (~180 LOC) with the
4 helpers (`buscar_ingreso_activo_por_uuid`, `cotizar_para_salida`,
`crear_salida_evento`, `insertar_alerta_salida_forzado`) plus typed exceptions
(`SalidaDuplicada`).

Verification: `repo/salida.py` is importable; ORM model maps to `prod.salidas`
columns; `crear_salida_evento` raises `SalidaDuplicada` on
`IntegrityError("one_exit_per_ingreso")` (mocked).

Rollback: delete the 2 files.

### Unit 2 — MIGRATION 0026 (4 operations, applied first)

Create `migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py`
(~120 LOC) with `down_revision = "0025_alerta_datos_nuevos"`. The migration has 4
operations in order:

**Op 1 — Pre-flight `DO $$` block (KD-7 pattern from F1.6 migration 0024)**:

```sql
DO $$
DECLARE
    _n_impuestos bigint;
    _n_salidas bigint;
    _n_alert_types bigint;
BEGIN
    SELECT count(*) INTO _n_impuestos
    FROM pg_catalog.pg_class
    WHERE relname='impuestos' AND relnamespace='prod'::regnamespace;
    IF _n_impuestos IS NULL OR _n_impuestos = 0 THEN
        RAISE EXCEPTION '0026_preflight_abort: tabla prod.impuestos no existe. Aplique migrations 0001-0025 antes.';
    END IF;

    SELECT count(*) INTO _n_salidas
    FROM pg_catalog.pg_class
    WHERE relname='salidas' AND relnamespace='prod'::regnamespace;
    IF _n_salidas IS NULL OR _n_salidas = 0 THEN
        RAISE EXCEPTION '0026_preflight_abort: tabla prod.salidas no existe.';
    END IF;

    SELECT count(*) INTO _n_alert_types
    FROM pg_catalog.pg_class
    WHERE relname='alert_types' AND relnamespace='prod'::regnamespace;
    IF _n_alert_types IS NULL OR _n_alert_types = 0 THEN
        RAISE EXCEPTION '0026_preflight_abort: tabla prod.alert_types no existe.';
    END IF;
END $$;
```

The pre-flight aborts with `0026_preflight_abort` if any of the 3 tables is missing,
mirroring F1.6 migration 0024's `0024_preflight_abort` pattern.

**Op 2 — Inline-seed `impuestos.IVA`** (resolves KD-IVA blocker from F1.8):

```sql
INSERT INTO prod.impuestos (
    uuid, codigo, nombre, porcentaje,
    vigente_desde, vigente_hasta, estado, created_at
) VALUES (
    gen_random_uuid(), 'IVA', 'IVA', 0.19,
    NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
)
ON CONFLICT (codigo, vigente_desde) DO NOTHING;
```

`codigo='IVA'` is the UK01 of `impuestos` (model `models/V/impuestos.py:35`). The
`ON CONFLICT` uses the UK constraint `(codigo, vigente_desde)` for idempotency.
`porcentaje=0.19` is the regulatory constant locked in F1.8 design.md §4 KD-IVA
(IVA Colombia 2026).

**Op 3 — Inline-seed 2 alert types** (V2/V5 bypass alerts):

```sql
INSERT INTO prod.alert_types (tipo_alerta, descripcion, severity)
VALUES
    ('subscripcion_vencida_forzado',
     'Salida vehicular forzada por administrador al detectar subscripción vencida al momento de salida',
     'warning'),
    ('tarifa_vigente_forzado',
     'Salida vehicular forzada por administrador al detectar tarifa no vigente al momento de salida',
     'warning')
ON CONFLICT (tipo_alerta) DO NOTHING;
```

Respects the trigger `alert_types_inmutable` (migration 0013) — INSERT-only for
`rol_app`. Same pattern as MIGRATION 0025 alert_type seed (F1.6).

**Op 4 — Partial unique index `one_exit_per_ingreso`** (closes TOCTOU race on V1):

```sql
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS one_exit_per_ingreso
    ON prod.salidas (uuid_ingreso)
    WHERE NOT EXISTS (
        SELECT 1 FROM prod.anulaciones a
        WHERE a.uuid_salida = prod.salidas.uuid
          AND a.tipo_anulable = 'salida'
          AND a.estado = 'ejecutada'
    );
```

`CONCURRENTLY` for no lock on reads/writes during creation in production. `IF NOT
EXISTS` for idempotency. Same pattern as F1.3 `unique_active_sesion_per_user`
(migration 0023). The INSERT conflict in the handler produces
`UniqueViolationError` (psycopg2/asyncpg code 23505) which `repo/salida.py` maps to
`SalidaDuplicada` → 409 `salida_duplicada`.

**Downgrade** (reverse order, superuser context for DELETE):

```sql
DROP INDEX IF EXISTS prod.one_exit_per_ingreso;
DELETE FROM prod.alert_types
    WHERE tipo_alerta IN ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado');
DELETE FROM prod.impuestos WHERE codigo='IVA' AND estado='activo';
```

Workaround if `impuestos_inmutable` trigger exists (R8): skip downgrade in production;
create compensatory migration to set `estado='inactivo'` instead.

Verification: `alembic upgrade head` succeeds; pre-flight aborts on simulated missing
tables; `INSERT … ON CONFLICT` is idempotent (run 2x, second is no-op); downgrade
removes all 4 ops.

Rollback: `alembic downgrade -1` (or compensatory migration if R8 trigger blocks).

### Unit 3 — Schemas + typed errors

Add to `schemas/operacion.py` (~80 LOC): `SalidaCreateForzado`, `SalidaReadForzado`,
and 4 typed error classes (`IngresoNoEncontradoError`, `SalidaDuplicadaError`,
`PlacaNoCoincideConIngresoError`, `TarifaVigenteNoEncontradaError`).

`extra='forbid'` (inherited from `_Base`) rejects extra fields — clients cannot
inject `tipo_salida` (DEC-SUC-21-NEW).

Verification: Pydantic rejects `payload.tipo_salida = "ROTACION"` with 422;
`SalidaReadForzado` validates against sample data.

Rollback: revert the schema additions.

### Unit 4 — Handler `create_salida`

Add to `api/v1/operacion.py` (~200 LOC) the 12-step handler chain per
D-HU-F1.7-20. Strict order: KD-3 → V1 → tenant scope → V3 → V4 → V5 → INSERT →
alerta → commit → derive tipo_salida → response. Lock continuity (KD-S7): the
`prod.calcular_cotizacion` invoke in Step 7 and the INSERT in Step 8 share the
same transaction; single `await session.commit()` in Step 9.

Verification: AST walk `tests/static/test_salida_handler_step_order.py` enforces
literal order; the handler compiles without syntax errors; happy path returns 201
with `tipo_salida`.

Rollback: revert the handler addition.

### Unit 5 — Tests (14 total)

**`tests/unit/test_operacion_salidas.py`** (~400 LOC, 10 tests):

Rotación (4 tests):

- T1: `test_salida_rotacion_exitosa` — happy path with `cobrar:true` →
  201 + `tipo_salida=ROTACION` + `cotizacion_snapshot`.
- T2: `test_salida_rotacion_sin_tarifa_vigente` — V5 returns `tarifa_no_vigente`
  without forzado → 422 `tarifa_vigente_no_encontrada` (F1.8 KD-3 propagado).
- T3: `test_salida_rotacion_forzada_con_alerta` — V5 returns `tarifa_no_vigente`
  with `forzado=true` + motivo → 201 + `tipo_salida=ROTACION` + alerta
  `tarifa_vigente_forzado`.
- T4: `test_salida_rotacion_duplicada_409` — second POST same `uuid_ingreso` →
  409 `salida_duplicada`.

Mensualidad (4 tests):

- T5: `test_salida_mensualidad_vigente_exitosa` — happy path with
  `cobrar:false,motivo:'mensualidad_vigente'` → 201 + `tipo_salida=MENSUALIDAD`
  + `cotizacion_snapshot=None`.
- T6: `test_salida_mensualidad_vencida_forzada` — V2 returns
  `subscripcion_inactiva_o_vencida` without forzado → 422.
- T7: `test_salida_mensualidad_vencida_con_forzado` — V2 bypassed + motivo → 201 +
  `tipo_salida=ROTACION` (F1.8 returns `cobrar:true` when no subscription at branch)
  + alerta `subscripcion_vencida_forzado`.
- T8: `test_salida_mensualidad_placa_no_coincide` — V3 placa mismatch → 422
  `placa_no_coincide_con_ingreso`.

KD-FORZADO (2 tests, F1.6 reuse validation):

- T9: `test_salida_kd_forzado_prefijo_valido` — motivo ≥10 chars → bypass activo.
- T10: `test_salida_kd_forzado_motivo_insuficiente` — motivo 9 chars → 422
  `motivo_forzado_insuficiente`.

**`tests/integration/test_salida_create_db.py`** (~250 LOC, 3 tests):

- T11: `test_insert_salida_con_alerta_forzado_atomico` — real DB, both INSERTs
  in single commit, rollback test (if alerta fails, INSERT rolls back).
- T12: `test_partial_unique_index_emite_409` — real DB, two concurrent threads, one
  succeeds one fails with `409 salida_duplicada`.
- T13: `test_iva_no_sembrado_retorna_500` — real DB, DELETE the IVA row, attempt
  salida, expect 500 `iva_no_configurado`.

**AST walks** (2 tests):

- `tests/static/test_salida_handler_step_order.py` (~100 LOC) — `ast.walk()` over
  `api/v1/operacion.py::create_salida` verifying literal order of
  `buscar_ingreso_activo_por_uuid` → `validar_subscripcion_vigente` →
  `detectar_tipo_vehiculo` (V3) → `validar_kd_forzado` →
  `cotizar_para_salida` → `crear_salida_evento` → `insertar_alerta_salida_forzado`.
- `tests/static/test_no_write_after_salida_insert.py` (~100 LOC) — `ast.walk()`
  rejecting `UPDATE|DELETE|TRUNCATE|MERGE` in `repo/salida.py`.

Verification: 14 tests green; `ruff check`, `ruff format --check`, `mypy --strict`
green on 9 files (4 new + 3 modified + 2 AST walks).

Rollback: remove the test files.

### Unit 6 — Spec deltas + Engram persistence

Persist spec deltas to `openspec/changes/hu-f1-7-salidas/specs/operations/spec.md`
with REQ-OPS-042..052 (11 requirements). Persist Engram observation
`sdd/hu-f1-7-salidas/propose` (architecture type).

Verification: spec.md has 11 new REQs in canonical format; Engram observation
recorded with `capture_prompt=false`.

Rollback: revert the spec changes; Engram observation stays (topic_key upserts).

### Step-by-step handler chain (12 steps, locked order)

The handler executes these steps in **strict literal order** (D-HU-F1.7-20,
A
ST walk `tests/static/test_salida_handler_step_order.py`):

1. **Step 1 — KD-3 issuer claims**: `_claims = requires_issuer("operador-", "admin-")`;
   `ctx = get_tenant_ctx` from JWT. Server resolves target sucursal from ingreso
   (different from F1.6 because cliente no envía sucursal en salida).

2. **Step 2 — V1 ingreso activo exists**:
   `ingreso = await repo_salida.buscar_ingreso_activo_por_uuid(session,
   uuid_ingreso=payload.uuid_ingreso)`. If None → 404 `ingreso_no_encontrado`.

3. **Step 3 — tenant scope (NUEVO en F1.7)**: `target_sucursal = ingreso.uuid_sucursal`.
   If `operador-` with cross-branch → 403 `tenant_scope_violation`. `admin-` already
   validated by `get_tenant_ctx`.

4. **Step 4 — V2 subscripción vigente al momento salida**: if
   `ingreso.uuid_subscripcion_cliente is not None`, invoke
   `validar_subscripcion_vigente(session, uuid_subscripcion_cliente=...,
   forzado=bool(bypass_reason))`. If not vigente without forzado → 422; if forzado →
   `bypass_reason = "subscripcion_vencida"`.

5. **Step 5 — V3 placa matches ingreso**: if `payload.placa is not None`, derive
   `tipo_placa = detectar_tipo_vehiculo(payload.placa)` and compare with
   `tipo_ingreso = detectar_tipo_vehiculo(ingreso.placa)`. If mismatch → 422
   `placa_no_coincide_con_ingreso`.

6. **Step 6 — V4 KD-FORZADO-01 prefix contract (F1.6 verbatim)**:
   `motivo = validar_kd_forzado(payload.observaciones, payload.forzado)`. Same 422
   errors as F1.6 (`motivo_forzado_requerido`, `forzado_contradiccion`,
   `motivo_forzado_insuficiente`). `bypass_reason: str | None = "forzado" if motivo
   else None`.

7. **Step 7 — V5 tarifa vigente via F1.8 PL/pgSQL**:
   `cotizacion = await repo_salida.cotizar_para_salida(session,
   uuid_ingreso=payload.uuid_ingreso)`. Invokes
   `SELECT prod.calcular_cotizacion(:uuid_ingreso)` (F1.8 VOLATILE) inside the same
   TX. Raises typed exceptions:
   - `IngresoNoEncontrado` (covered V1)
   - `TarifaNoVigente` → 422 if not bypass; alerta if bypass
   - `IVANoConfigurado` → 500 (post-0026 deploy: never)
   `tipo_salida = "MENSUALIDAD" if cotizacion.cobrar is False else "ROTACION"`.

8. **Step 8 — INSERT salida `[A]` con motivo (KD-S6, KD-S7 same TX)**:
   `new_attrs = {uuid_sucursal: target_sucursal, uuid_ingreso: payload.uuid_ingreso,
   fecha_salida: datetime.now(UTC).replace(tzinfo=None),
   fecha_retencion_hasta: date.today() + relativedelta(years=2)}`. `new_row = await
   repo_salida.crear_salida_evento(session, actor_uuid=ctx.actor_uuid,
   new_attrs=new_attrs)`. `IntegrityError("one_exit_per_ingreso") → SalidaDuplicada
   → 409`.

9. **Step 9 — alertas same TX (KD-S12, R5)**: if `bypass_reason == "subscripcion_vencida"`,
   insert alerta `subscripcion_vencida_forzado`. If `bypass_reason ==
   "tarifa_no_vigente"`, insert alerta `tarifa_vigente_forzado`. Both in same TX as
   Step 8. Single `await session.commit()` materializes salida + alerta atomically and
   releases FOR SHARE lock (KD-S7).

10. **Step 10 — derivar `tipo_salida` (DEC-SUC-21-NEW)**: already derived in Step 7;
    documented here for AST walk literal.

11. **Step 11 — response shape**: `apply_no_store_header(response)`;
    `await session.refresh(new_row)`; return `SalidaReadForzado(uuid=new_row.uuid, ...,
    tipo_salida=tipo_salida, forzado_en_creacion=(bypass_reason is not None),
    motivo_forzado=motivo if bypass_reason else None, cotizacion_snapshot=
    CotizarFacturacion.model_validate(cotizacion) if tipo_salida == "ROTACION" else None)`.

12. **Step 12 — return**: 201 with `SalidaReadForzado`.

### Lock continuity invariants (KD-S7)

- **Single transaction**: handler does NOT use sub-transactions or `SAVEPOINT`. The
  `await session.commit()` is the only commit point. AST walk
  `test_salida_handler_step_order.py` rejects multiple `session.commit()` calls.
- **FOR SHARE continuity**: `prod.calcular_cotizacion` in Step 7 acquires `FOR SHARE`
  on `tarifas_sucursal` PK (F1.8 KD-1). The lock is held through Step 8 (INSERT
  salida) and Step 9 (alerta INSERT). Released at `session.commit()`. No other TX can
  modify `tarifas_sucursal` between cotizar and registrar.
- **V1 race closure**: V1 EXISTS subquery is vulnerable to TOCTOU. Partial unique
  index `one_exit_per_ingreso` (MIGRATION 0026 Op 4) closes the window — if two
  concurrent requests both pass V1, the second INSERT receives `UniqueViolationError`
  → 409 `salida_duplicada`.

## 9. Risks & Mitigations

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | KD-IVA blocker: `impuestos.IVA` not seeded; every cotización returns 500 `iva_no_configurado`; F1.8 deployment blocked until seeded | **CRÍTICA** | MIGRATION 0026 Op 2 inline-seeds `impuestos.IVA` (`codigo='IVA'`, `porcentaje=0.19`) via `INSERT … ON CONFLICT (codigo, vigente_desde) DO NOTHING`; pre-flight Op 1 aborts if `prod.impuestos` table missing. After F1.7 apply, F1.8 deployment is unblocked. |
| **R2** | `Salida` ORM model doesn't exist (pre-existing gap); handler would need raw SQL for INSERT | Alta | F1.7 creates `models/L_S/salida.py` (~40 LOC, based on `LifecycleEventBase` with audit + sync mixins). Test T11 verifies INSERT via ORM; T12 verifies partial unique index. |
| **R3** | Lock continuity (KD-S7) broken by future dev — adding sub-transactions or multiple commits releases FOR SHARE early | Alta | Handler enforces single `await session.commit()`; AST walk `tests/static/test_salida_handler_step_order.py` rejects multiple `session.commit()` calls. Test T11 verifies atomicity via real DB. |
| **R4** | TOCTOU race on V1 EXISTS subquery — two concurrent requests both pass V1 and create duplicate salidas | Media | Partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4) closes the window. `UniqueViolationError` mapped to 409 `salida_duplicada`. Test T12 verifies with concurrent threads. |
| **R5** | Alerta huérfana — INSERT salida succeeds but alerta INSERT fails (FK, etc.); salida stays without audit trail | Media | Step 9 inserts alerta in same TX as Step 8 (single `commit()`); FK ordering guarantees alerta only commits if salida OK. Test T11 verifies rollback path. |
| **R6** | DEC-SUC-21-NEW verification — handler does NOT persist `tipo_salida` in `prod.salidas` | Baja | AST walk `test_no_write_after_salida_insert.py` verifies `new_attrs` doesn't contain `tipo_salida`/`valor`/`total`/`subtotal`. Code review on `repo/salida.py::crear_salida_evento`. |
| **R7** | Strict order V1→V2→V3→V4→V5 altered by future dev (e.g., V8 before V2 causes duplicate-with-cupo-agotado reported as duplicate not as cupo) | Media | AST walk `tests/static/test_salida_handler_step_order.py` verifies literal order of helper invocations. Same pattern as F1.6 `test_kd_forzado_in_handler.py`. |
| **R8** | `impuestos_inmutable` trigger may block DELETE in downgrade | Baja | Pre-F1.7-apply verification: `grep impuestos_inmutable migrations/` confirms if exists. If exists, downgrade 0026 fails → document workaround (NO downgrade in production; create compensatory migration setting `estado='inactivo'` instead). |
| **R9** | Optional placa may hide operator typos (e.g., scanning wrong vehicle's QR) | Baja | If client omits placa, server trusts `uuid_ingreso` (authoritative). UI must require visual confirmation; documented in `docs/`. Test T8 verifies V3 mismatch when placa provided. |

## 10. Reconciliation

| Code | Decision | Status | Rationale |
|---|---|---|---|
| **DEC-SUC-21-NEW** | `tipo_salida = MENSUALIDAD | ROTACION` derived server-side from F1.8's `cobrar` flag; returned in `SalidaReadForzado`; NEVER persisted in `prod.salidas` | NEW (F1.7) | Analogue of DEC-SUC-21 for ingreso (F1.6); 4FN compliance — `prod.salidas` has no `tipo_salida` column by design. View `V_SALIDA_TIPO` may be added in future HU if direct query is needed; F1.7 does NOT create it. |
| **DEC-SUC-23** | `salidas` has no monto column; monto lives in `prod.factura_detalle` (ER 780-794) | CONFIRMED | `plan.md` line 810 explicit: "ninguno persiste un monto en `salidas`"; DEC-SUC-23 from F1.6/F1.8 context applies equally to salidas. |
| **DEC-SAL-01** | `salidas` is append-only `[A]` event; NEVER UPDATE post-creation; corrections via `prod.anulaciones(tipo_anulable='salida')` workflow (Fase 7+) | NEW (F1.7) | Analogue of DEC-ANUL-01 for ingreso (F1.6). Defense in depth at DB layer: `REVOKE UPDATE, DELETE` already applied (migration 0001 línea 2923) + trigger `fn_salidas_inmutable` (líneas 1990-2003) + partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4). F1.7 does NOT create the anulación workflow — only leaves the door open. |
| **DEC-IMP-01** | `impuestos.IVA` inline-seeded in MIGRATION 0026 (F1.7 apply); ownership of catalog scope remains HU-F14.2 Parte II; apply advances the dependency | NEW (F1.7) | KD-IVA blocker for F1.8 (F1.8 exploration:121, verify-report:R1) is critical. F1.6 established inline-seed pattern in MIGRATION 0025. F1.7 mirrors it. Same `INSERT … ON CONFLICT (codigo, vigente_desde) DO NOTHING`. |
| **DEC-IDEM-01** | Idempotency via `Idempotency-Key` HTTP header (PR2 middleware); NOT `correlacion_id` in body | CONFIRMED (F1.6) | DEC-IDEM-01 from F1.6 applies equally to F1.7. |
| **DEC-FORZADO-01** | KD-FORZADO-01 prefix contract reused verbatim from F1.6; no deviation | CONFIRMED (F1.6 reuse) | D-HU-F1.7-5; one implementation, one test, one audit. |
| **DEC-MONO-01** | One handler `POST /operacion/salidas` derives `tipo_salida` server-side; NOT two endpoints | NEW (F1.7, orchestrator) | Orchestrator consolidation (exploration §6). Reduces surface area; reuses F1.8's atomic lock; client is indifferent to path. Trade-off: client loses pre-classification (operator UI may have a "is mensualidad?" toggle) — but gains server-side guarantee + reduces bug surface. |

## 11. Open Questions

Las 10 preguntas abiertas de `exploration.md §15` se resuelven en este proposal vía
adopción de KD / DEC / D-HU-F1.7-N:

- **OQ-1 (KD-S1 unified 404)** — RESUELTO (orchestrator-decided): favor de unificar
  404 `ingreso_no_encontrado` para "no existe / ya cerrado / anulado" — operacionalmente
  equivalente. Decisión D-HU-F1.7-8 + KD-S1.

- **OQ-2 (KD-S2 orden tenant scope)** — RESUELTO (orchestrator-decided): favor de
  404 antes de 403 (defense-in-depth, no info leak). Decisión D-HU-F1.7-9 + KD-S2.

- **OQ-3 (KD-S3 placa opcional)** — RESUELTO (orchestrator-decided): favor de
  opcional. Cliente puede conocer uuid_ingreso sin recordar placa. Decisión
  D-HU-F1.7-10 + KD-S3.

- **OQ-4 (KD-S4 `cotizacion_snapshot` en respuesta)** — RESUELTO (orchestrator-decided):
  favor de incluir solo cuando `tipo_salida=ROTACION`. Cuando MENSUALIDAD, cliente
  no necesita desglose fiscal (no cobra). Decisión D-HU-F1.7-11 + KD-S4.

- **OQ-5 (KD-S6 `fecha_retencion_hasta`)** — RESUELTO (orchestrator-decided): favor
  de 2 años desde `fecha_salida`. Coherente con particionamiento mensual existente
  en `prod.salidas`. Decisión D-HU-F1.7-13 + KD-S6.

- **OQ-6 (KD-S8 MIGRATION 0026 ordering)** — RESUELTO (orchestrator-decided): el
  apply de F1.7 corre **antes** que cualquier test del F1.7. 0026 es la chain head
  de F1.7 (down_revision = "0025_alerta_datos_nuevos").

- **OQ-7 (DEC-SUC-23-NEW confirmación)** — RESUELTO (orchestrator-decided): confirmar
  que el handler NO inserta ningún campo de monto en `prod.salidas`. AST walk
  `test_no_write_after_salida_insert.py` verifica literal. Decisión DEC-SUC-23 +
  D-HU-F1.7-19.

- **OQ-8 (Lock scope en alertas)** — RESUELTO (orchestrator-decided): `alerta` es
  append-only `[L-W]`, no requiere lock adicional. `insertar_alerta_salida_forzado`
  usa `session.flush()` sin `FOR UPDATE/SHARE`. Justificación: no hay race condition
  (alerta solo se inserta después del INSERT de salida exitoso).

- **OQ-9 (Idempotency-Key header REQUIRED)** — RESUELTO (orchestrator-decided): SÍ,
  mismo patrón que F1.6 `POST /ingresos`. Decisión DEC-IDEM-01 (F1.6) +
  D-HU-F1.7-17. No agregar `correlacion_id` al body.

- **OQ-10 (MIGRATION 0026 idempotency test)** — RESUELTO (orchestrator-decided):
  SÍ, test explícito verifica que 0026 puede correr 2 veces seguidas sin error
  (idempotente vía `ON CONFLICT DO NOTHING`). Test integration T-aux en
  `tests/integration/test_migration_0026_idempotent.py`.

**Sin preguntas abiertas para propose/design.** Si durante `sdd-design` surge
evidencia técnica fuerte para revisar alguna KD (ej: medición de EXPLAIN ANALYZE
muestra V1 > 50ms en producción simulada con 100M filas, o `impuestos_inmutable`
trigger existe y bloquea el downgrade), se reabre en `design.md` con evidencia.

## 12. Success Criteria

1. `pytest backend/tests/unit/test_operacion_salidas.py` verde — 10 tests
   parametrizados: T1 rotación exitosa 201 + `tipo_salida=ROTACION` +
   `cotizacion_snapshot`, T2 rotación sin tarifa 422, T3 rotación forzada con
   alerta 201, T4 duplicada 409, T5 mensualidad exitosa 201 + `tipo_salida=
   MENSUALIDAD` + `cotizacion_snapshot=None`, T6 mensualidad vencida sin forzado
   422, T7 mensualidad vencida con forzado 201 + alerta, T8 placa no coincide
   422, T9 KD-FORZADO prefijo válido, T10 KD-FORZADO motivo <10 chars.

2. `pytest backend/tests/unit/test_operacion_salidas_kd_forzado.py` verde — 2
   tests: T-aux prefix_mid_string_no_startswith_returns_none, T-aux KD-FORZADO
   contract reuse (no duplica tests F1.6).

3. `pytest backend/tests/integration/test_salida_create_db.py` verde — 3 DB tests
   (`PARKOS_DOCKER_TEST=1`): T11 insert+alerta same-TX, T12 partial unique
   index → 409, T13 IVA no sembrado → 500.

4. `pytest backend/tests/static/test_salida_handler_step_order.py` verde — 1 AST
   walk: orden literal de invocaciones en `create_salida` (V1 → tenant scope →
   V2 → V3 → V4 → V5 → INSERT → alerta → commit).

5. `pytest backend/tests/static/test_no_write_after_salida_insert.py` verde — 1
   AST walk: `repo/salida.py` rechaza `UPDATE|DELETE|TRUNCATE|MERGE`.

6. `pytest backend/tests/integration/test_migration_0026_idempotent.py` verde —
   1 migration test: corre `alembic upgrade head` 2 veces seguidas, segundo es
   no-op.

7. Defense-in-depth gate: cada una de las 5 capas (regex/KD-3 server-side,
   KD-FORZADO chain, alerta INSERT same-TX, AST walk ordering, partial unique
   index) tiene al menos un test que la rompe individualmente y verifica que las
   demás capas la contienen.

8. Transactional integrity gate: test integration T11 verifica que si
   `insertar_alerta_salida_forzado` falla (FK violation simulada), el INSERT del
   salida se hace rollback (no quedan filas huérfanas — R5).

9. KD-V8 issuer parity: test verifica que tanto `operador-` como `admin-` pueden
   emitir `forzado=true` y la alerta se inserta con `actor_uuid` correcto (no
   cross-tenant).

10. `SalidaReadForzado` carry-through: test verifica que `tipo_salida`,
    `forzado_en_creacion`, `motivo_forzado`, `cotizacion_snapshot` se devuelven
    en el 201; y que `tipo_salida` **NO** aparece en `prod.salidas` (DEC-SUC-21-NEW,
    query directa sobre la tabla — R6).

11. KD-IVA resolution gate: post-0026 apply, `repo/impuestos.py::
    validar_iva_configurado(session)` returns True; F1.8's
    `calcular_cotizacion` no returns `iva_no_configurado` en
    `pytest backend/tests/integration/test_cotizar_db.py` (regression test).

12. Precedente intacto: `git diff api/v1/__init__.py api/v1/router_factory.py
    api/deps.py auth/tenancy.py models/L_E/ingreso.py models/V/* migrations/
    versions/0022_*` retorna vacío. `git diff repo/ingreso.py
    repo/subscripcion_activa.py repo/cotizacion.py repo/placa.py repo/alerta.py`
    retorna vacío (F1.6/F1.8 helpers reutilizados verbatim).

13. `ruff check`, `ruff format --check`, `mypy --strict` verde sobre los 9
    archivos nuevos/modificados (4 nuevos + 5 modificados en backend + 5 test
    files).

14. Header `Cache-Control: no-store` presente en toda respuesta 2xx/4xx/5xx del
    endpoint (consistente con F1.3/F1.5/F1.6/F1.8 precedents).

15. Idempotency-Key REQUIRED gate: test verifica que el endpoint declara
    `Idempotency-Key` como header esperado (PR2 middleware behavior
    preserved; DEC-IDEM-01).

## 13. Out of Scope (deferred)

1. **Workflow de anulación** (`prod.anulaciones(tipo_anulable='salida')` workflow
   para revertir salida post-creación). DEC-SAL-01 delega a Fase 7+.
   `prod.salidas` nunca UPDATE post-creación; el partial unique index
   `one_exit_per_ingreso` permite una nueva salida si la anterior fue anulada
   (`NOT EXISTS` sobre `anulaciones WHERE estado='ejecutada'`).

2. **`correlacion_id`** en el payload. DEC-IDEM-01 delega idempotencia al header
   `Idempotency-Key` (PR2 middleware, intacto).

3. **Lock pesimista** (`SELECT … FOR UPDATE/SHARE`) sobre `prod.ingreso` /
   `prod.subscripciones_cliente` desde el endpoint. KD-S7 lock continuity sobre
   `tarifas_sucursal` vía F1.8 PL/pgSQL es suficiente; las otras tablas son
   read-mostly (admin actions infrecuentes).

4. **Versionado de UI cliente** (Fase 2 frontend — `web_sucursal` debe desactivar
   la clasificación client-side de `tipo_salida` cuando este endpoint esté en
   producción). F1.7 **NO** modifica el cliente; el cliente sigue mandando
   `uuid_ingreso` y el server deriva el tipo. La limpieza del cliente es
   cleanup post-archive.

5. **`POST /operacion/salidas/mensualidad`** — out of scope por DEC-MONO-01;
   consolidado en un solo handler.

6. **Endpoint `GET /operacion/salidas/{uuid}`** (preview sin insertar) — sale del
   scope; el handler hace insert o 422, sin preview.

7. **Alertas adicionales** (e.g. `placa_no_coincide_forzado`,
   `subscripcion_sin_vehiculo`). Solo se insertan
   `subscripcion_vencida_forzado` y `tarifa_vigente_forzado` (KD-S12); otras
   alertas son operacionales y salen del scope de F1.7.

8. **Cleanup del cliente** (`web_sucursal/src/lib/validation/salida.ts` —
   pre-clasificación client-side de `tipo_salida`). F1.7 entrega el server-side
   enforcement; el cleanup del cliente es post-archive.

9. **Numeración de factura electrónica** (FE) — Fase 8 (HU-F1.10);
   F1.7 solo persiste el lifecycle event, no la factura.

10. **Permisos RBAC diferenciados para `forzado`** (e.g. "solo admin-"). KD-V8
    acepta ambos `operador-` y `admin-` para MVP; check dedicado en HU futura.

11. **Métricas / observabilidad del handler** (contador de `forzado=true` por
    día, latencia p99 de `create_salida`). Sale del scope; alineado con HU-F1.X
    de observabilidad (futuro).

12. **Vista `V_SALIDA_TIPO`** para query directa de `tipo_salida`. Sale del
    scope; el cliente deriva del response field. Si query directa es necesaria,
    crear la vista en HU futura.

13. **Cambio de `valor_plena` / `unidad_minutos`** (KD-2 de F1.8). Encapsulado
    en PL/pgSQL; no se expone en el handler.

14. **Modificación a `IdempotencyKeyMiddleware`** (PR2). Intact; el handler
    validado solo cambia la respuesta en el happy path (201) y agrega
    404/409/422 antes del INSERT.

## 14. Relevant Files

**Nuevos** (4 archivos backend + 5 test files):

- `backend/packages/parkos_core/src/parkos_core/models/L_S/salida.py` (~40 LOC)
  — ORM model `Salida(LifecycleEventBase)` con audit + sync mixins; schema
  `prod.salidas`; cierra el gap pre-existente (tabla existe desde migration 0001).

- `backend/packages/parkos_core/src/parkos_core/repo/salida.py` (~180 LOC) — 4
  funciones puras: `buscar_ingreso_activo_por_uuid` (V1),
  `cotizar_para_salida` (V5 wrapper sobre F1.8), `crear_salida_evento` (Step 8
  INSERT + `IntegrityError → SalidaDuplicada`), `insertar_alerta_salida_forzado`
  (Step 9 alerts).

- `backend/packages/parkos_core/src/parkos_core/repo/impuestos.py` (~50 LOC) —
  `validar_iva_configurado(session) -> bool` para HU-F1.9 + HU-F14.2 audit +
  test mocks.

- `backend/packages/parkos_core/migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py`
  (~120 LOC) — Alembic: 4 operaciones (pre-flight + IVA seed + 2 alert_types
  seed + partial unique index); `down_revision = "0025_alerta_datos_nuevos"`.

- `backend/tests/unit/test_operacion_salidas.py` (~400 LOC, 10 tests) — T1..T10
  rotación + mensualidad + KD-FORZADO + duplicada + placa.

- `backend/tests/unit/test_operacion_salidas_kd_forzado.py` (~80 LOC, 2 tests)
  — T-aux prefix mid-string + contract reuse validation.

- `backend/tests/integration/test_salida_create_db.py` (~250 LOC, 3 tests) —
  T11 insert+alerta same-TX, T12 partial unique index → 409, T13 IVA no
  sembrado → 500. Requiere `PARKOS_DOCKER_TEST=1`.

- `backend/tests/integration/test_migration_0026_idempotent.py` (~150 LOC, 1
  test) — corre `alembic upgrade head` 2 veces, segundo no-op.

- `backend/tests/static/test_salida_handler_step_order.py` (~100 LOC, 1 AST
  walk) — orden literal de invocaciones en `create_salida` (KD-S20 invariante).

- `backend/tests/static/test_no_write_after_salida_insert.py` (~100 LOC, 1 AST
  walk) — `repo/salida.py` rechaza `UPDATE|DELETE|TRUNCATE|MERGE` (R6).

**Modificados** (2 archivos backend):

- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (add
  `create_salida` lines ~296-360, ~200 LOC) — handler con las 12 validaciones
  + KD-FORZADO-01 reuse + derivación `tipo_salida`. Mantiene `_ingreso_issuer_dep`
  + `get_tenant_ctx` intactos.

- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (+80 LOC) —
  agregar `SalidaCreateForzado`, `SalidaReadForzado`, 4 clases de error
  tipadas. `extra='forbid'` heredado de `_Base` rechaza inyección de
  `tipo_salida`.

- `openspec/specs/operations/spec.md` (MODIFICAR) — agregar REQ-OPS-042..052
  (11 requirements) + entrada en `## Modified Capabilities`.

**Archivos NO tocados (deliberado)**:

- `api/v1/__init__.py` (router ya montado en línea 143, incluye
  `operacion.router` que ahora registra `/salidas` automáticamente).
- `api/v1/router_factory.py` (`make_router` F1.1 commit `f7cb37a`, no se usa
  en `/operacion`).
- `api/deps.py` (centraliza `get_tenant_ctx` + `requires_issuer`, se reusa tal
  cual).
- `auth/tenancy.py` (KD-3 reusa los errores tipados ya definidos).
- `models/L_E/ingreso.py` (V1 hace read-only).
- `models/V/*` (sin cambios de esquema).
- `migrations/versions/0022_create_calcular_cotizacion.py` (F1.8 PL/pgSQL no
  cambia; F1.7 la invoca).
- `migrations/versions/0024_create_mv_ocupacion_diaria.py` (F1.5 MV no
  afectada).
- `migrations/versions/0025_alerta_datos_nuevos.py` (F1.6 alert_type seed; F1.7
  añade 0026 encima).
- `repo/event.py`, `repo/cotizacion.py` (F1.6/F1.8 helpers reusados sin
  modificación).
- `repo/ingreso.py` (F1.6 `validar_kd_forzado` reusado).
- `repo/subscripcion_activa.py` (F1.6 `validar_subscripcion_vigente` +
  `resolve_active_subscription_for_exit` reusados).
- `repo/placa.py` (F1.6 `detectar_tipo_vehiculo` reusado).
- `repo/alerta.py` (F1.6 `insertar_alerta_forzado` pattern; F1.7 crea
  `insertar_alerta_salida_forzado` con `datos_nuevos` shape diferente).
- `web_sucursal/src/lib/validation/salida.ts` (Fase 2 frontend; cleanup
  post-archive).

## 15. Requirements (delta — to be formalized in spec.md)

The following REQ-OPS-NNN placeholders will be formalized by `sdd-spec` in
`openspec/changes/hu-f1-7-salidas/specs/operations/spec.md`:

- **REQ-OPS-042 (NEW)** — POST /operacion/salidas contract: `SalidaCreateForzado`
  input + `SalidaReadForzado` output; KD-3 tenant scope; `Cache-Control: no-store`;
  `Idempotency-Key` HTTP header (DEC-IDEM-01).

- **REQ-OPS-043 (NEW)** — V1: ingreso activo exists. `404 ingreso_no_encontrado`
  unified discriminator para "uuid no existe / ya tiene salida / fue anulado"
  (KD-S1). SELECT directo a `prod.ingreso` con `vigente_hasta IS NULL AND NOT EXISTS
  salidas`; defense-in-depth vía partial unique index `one_exit_per_ingreso`
  (MIGRATION 0026 Op 4).

- **REQ-OPS-044 (NEW)** — V2: subscripción vigente al momento salida. Reuso
  verbatim de `repo/subscripcion_activa.py::validar_subscripcion_vigente` (F1.6);
  422 `subscripcion_inactiva_o_vencida` sin forzado; alerta
  `subscripcion_vencida_forzado` con forzado. Justificación: subscripción pudo
  vencer entre ingreso y salida.

- **REQ-OPS-045 (NEW)** — V3: placa matches ingreso. Reuso verbatim de
  `repo/placa.py::detectar_tipo_vehiculo` (F1.6) sobre `payload.placa` y
  `ingreso.placa`; case-insensitive normalizado. 422
  `placa_no_coincide_con_ingreso` sin bypass (correctness invariant). Placa
  opcional en payload.

- **REQ-OPS-046 (NEW)** — V4: KD-FORZADO-01 prefix contract reusado verbatim de
  F1.6 (`repo/ingreso.py::validar_kd_forzado`); mismo 422 set
  (`motivo_forzado_requerido`, `forzado_contradiccion`,
  `motivo_forzado_insuficiente`). Bypass aplica a V2 y V5 solamente (no a V1,
  V3). Tests compartidos con F1.6.

- **REQ-OPS-047 (NEW)** — V5: tarifa vigente via `prod.calcular_cotizacion(:
  uuid_ingreso)` PL/pgSQL (F1.8 VOLATILE); invocado dentro de la misma TX del
  handler (KD-S7 lock continuity); `SELECT … FOR SHARE` sobre
  `tarifas_sucursal` mantenido hasta `session.commit()`. 422
  `tarifa_vigente_no_encontrada` sin forzado; alerta
  `tarifa_vigente_forzado` con forzado. 500 `iva_no_configurado` post-0026
  deploy: never.

- **REQ-OPS-048 (NEW)** — INSERT `prod.salidas` `[A]` append-only via
  `repo/salida.py::crear_salida_evento`; defensa in depth: REVOKE UPDATE, DELETE
  (migration 0001 línea 2923) + trigger `fn_salidas_inmutable` (líneas 1990-2003)
  + partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op 4). NUNCA
  UPDATE post-creación (DEC-SAL-01).

- **REQ-OPS-049 (NEW)** — `tipo_salida = MENSUALIDAD | ROTACION` derivado
  server-side del flag `cobrar` de `prod.calcular_cotizacion`. Retornado en
  `SalidaReadForzado.tipo_salida`. NUNCA persistido en `prod.salidas` (DEC-SUC-
  21-NEW; 4FN). View `V_SALIDA_TIPO` queda como future work.

- **REQ-OPS-050 (NEW)** — alerta same-TX para V2/V5 bypass
  (`subscripcion_vencida_forzado` para V2 bypassed,
  `tarifa_vigente_forzado` para V5 bypassed); insertada en el mismo
  `commit()` que el INSERT de salida (defense against R5 orphan alertas).
  Una alerta por validación bypassed; `datos_nuevos` jsonb contiene `motivo` +
  `uuid_salida`. Respeto al trigger `alert_types_inmutable` (rol_app INSERT).

- **REQ-OPS-051 (NEW)** — partial unique index `one_exit_per_ingreso` sobre
  `prod.salidas (uuid_ingreso) WHERE NOT EXISTS (anulaciones ejecutadas)`
  (MIGRATION 0026 Op 4); `UniqueViolationError` (psycopg2/asyncpg code 23505)
  mapeado a 409 `salida_duplicada`. Cierra TOCTOU race en V1 EXISTS subquery.

- **REQ-OPS-052 (NEW)** — inline-seed `impuestos.IVA` en MIGRATION 0026 Op 2
  (`codigo='IVA'`, `porcentaje=0.19`, `vigente_desde=NOW() AT TIME ZONE 'UTC'`,
  `vigente_hasta=NULL`, `estado='activo'`); `ON CONFLICT (codigo,
  vigente_desde) DO NOTHING`; resuelve KD-IVA blocker de F1.8
  (`exploration.md:121` + `verify-report.md:R1`). Pre-flight abort si
  `prod.impuestos` no existe.

## 16. Next Steps

`design.md` will produce:

1. **MIGRATION 0026** con las 4 operaciones explícitas (§8 Approach Unit 2):
   pre-flight DO $$ (Op 1), inline-seed IVA (Op 2), inline-seed 2 alert_types
   (Op 3), partial unique index (Op 4). Downgrade reverse-order.
2. **Schemas** `SalidaCreateForzado`, `SalidaReadForzado`, 4 typed errors
   (IngresoNoEncontradoError, SalidaDuplicadaError, PlacaNoCoincideConIngresoError,
   TarifaVigenteNoEncontradaError) en `schemas/operacion.py`.
3. **ORM model** `Salida(LifecycleEventBase)` con audit + sync mixins en
   `models/L_S/salida.py`.
4. **Handler** `create_salida` con las 12 validaciones en estricto orden literal
   (§8 Approach Step 1..12); single `commit()` para atomicidad (KD-S7).
5. **Repo helpers** en `repo/salida.py` (4 funciones) + `repo/impuestos.py`
   (1 función).
6. **Tests** 14 totales (10 unit HTTP + 2 KD-FORZADO unit + 3 DB integration + 2
   AST walks) + 1 migration idempotency test.
7. **KD-letter** if any: si la validación EXPLAIN ANALYZE sobre el partial unique
   index en producción simulada con 100M `prod.salidas` filas muestra > 50ms p99,
   reabrir R8 mitigation.
8. **R8 verification** pre-apply: `grep impuestos_inmutable migrations/` confirma
   si existe; si existe, document workaround (NO downgrade; compensatory
   migration).

**Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`.
**Adopted KDs**: KD-S1, KD-S2, KD-S3, KD-S4, KD-S5, KD-S6, KD-S7, KD-S8, KD-S12,
KD-S16, KD-S20, KD-FORZADO-01 (12 KDs, all from explore §15 resolved).
**Precedents mirrored**: F1.6 (REQ-OPS-034..041, KD-FORZADO-01 verbatim, KD-7
pre-flight pattern, KD chain ordering), F1.8 (REQ-OPS-022..025, VOLATILE
`calcular_cotizacion`, `FOR SHARE` lock continuity KD-1), F1.5 (REQ-OPS-030..033,
MV pattern, KD-7 10M NOTICE / 50M ABORT), F1.4 (REQ-OPS-017..021, bi-temporal
predicate), F1.3 (REQ-OPS-026..029, partial unique index pattern + AST walk +
pre-flight abort).
**Commits future**: conventional commits only, no AI attribution.
**PR target**: `origin/dev` from `feat/fase-1-prerequisites-backend`.