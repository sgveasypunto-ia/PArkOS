# Exploration: salida condicional al pago (opción A, ambos flujos)

**HU:** `hu-f8-1-pago-bloquea-salida`
**Date:** 2026-09-23
**Author:** sdd-explore (sub-agent)
**Branch context:** starting from `fix/hu-f8-1-anular-salida-no-pagada` (will be replaced)

---

## Current State

### What works today (and where the gap lives)

1. **`SalidaFlow` triggers `POST /operacion/salidas` on "Cobrar".** In rotación, the moment
   the operator confirms the cotizacion (line 112 of `apps/electron-sucursal/src/features/operacion/components/SalidaFlow.tsx`),
   `trigger({uuid_ingreso})` fires. The backend handler at
   `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:467` runs a 12-step
   chain. **Step 8 (`line 619`) INSERTs `prod.salidas` BEFORE the pago** — the operator
   is not paid yet.
2. **Cupo is released AT Step 8, before pago.** DEC-SUC-23 (plan.md:438) commits
   this as intentional: "`salidas` solo se actualiza una vez en todo el ciclo: `UPDATE
   salidas SET estado='PAGADO'` al completar el pago (única excepción documentada al patrón
   insert-only de esta tabla)". The DB row's `estado` does not exist as a column —
   `prod.salidas` columns are `uuid`, `uuid_sucursal`, `uuid_ingreso`, `fecha_salida`,
   `fecha_retencion_hasta`, audit. The "pending" state is purely a UI inference.
3. **`POST /operacion/salidas/mensualidad` does NOT exist yet.** plan.md:807/1707
   reference it as the second handler in HU-F1.7, but the current router at
   `operacion.py:441` only mounts the rotation endpoint. `SalidaMensualidad.tsx` calls
   the *same* `trigger({uuid_ingreso})` and reads `result.tipo_salida === 'MENSUALIDAD'`
   server-derived from `prod.calcular_cotizacion` (F1.8 derivation: `cobrar:false`).
4. **`POST /facturacion/factura` REQUIRES `uuid_salida`.** Schema at
   `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py:585` declares
   `uuid_salida: uuid_lib.UUID` (no default). Handler Step 2 at
   `api/v1/facturacion.py:265` calls `repo_factura.buscar_salida_facturable` and 404s
   if the row is missing. **Today the BACKEND's factura endpoint cannot run until the
   salida row exists.**
5. **Open question: does the FE flow actually work end-to-end today?** The renderer-side
   `PostFacturaPayload` (`apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts:73-89`)
   does NOT carry `uuid_salida` — it sends only `uuid_ingreso + medio_pago + (monto_recibido_cents | voucher) + cliente`.
   `PagoSheet.handleSubmit` (`PagoSheet.tsx:210-275`) builds that body. With Opción A
   premise (no `uuid_salida` yet), this payload would 422 against the current schema. The
   `facturacion/factura.py` line 332 validator (`total_no_coherente`) and the `items`
   field requirements (1-50 `FacturaItemCreate`) are also not honored by the FE — the
   FE never sends `items[]`. **Action item:** F8.1 was implemented FE-side without
   touching the BE contrato for cobro puro; the FE was wired to call `POST
   /facturacion/factura` with a simplified payload that does not match the schema.
6. **The fix `fix/hu-f8-1-anular-salida-no-pagada` wrote two new files (WIP):**
   `apps/electron-sucursal/src/features/facturacion/hooks/useAnularSalidaNoPagada.ts`
   and `useAnularSalidaNoPagada.test.ts`. Both reach `POST /workflows/anulaciones`
   with `tipo_anulable='salida'`. The hook is wired into `PagoSheet.handleClose`
   (`PagoSheet.tsx:193`) as fire-and-forget whenever the operator closes the pago
   drawer without paying (Cancelar / X / overlay / Escape). The BE endpoint already
   supports `tipo_anulable='salida'`, `uuid_salida` optional-but-validated
   (`schemas/workflows.py:184-200`).
7. **`anulaciones` `[L-W]` workflow is the canonical correction path.** Per
   `modelo_datos_er.mmd:622-643`: `anulaciones` has `tipo_anulable∈{ingreso,salida}`,
   `uuid_ingreso` always populated, `uuid_salida` populated when `tipo_anulable='salida'`,
   `estado∈{solicitada,aprobada,ejecutada}`, `uuid_anulacion_padre` chains transitions.
   The `V_INGRESO_ESTADO` view joins `anulaciones` (line 404 of plan.md: `Activo -->
   Finalizado: INSERT salidas sin anular`, `Finalizado --> Activo: INSERT anulaciones
   (tipo_anulable='salida', estado='ejecutada')`).

### Entry chain (F1.7 lock, `static/test_salida_handler_step_order.py`)

The 12-step chain in `operacion.py::create_salida` is locked at the AST level. Steps that
matter for this exploration:

| Step | Code | Effect |
|------|------|--------|
| 1 | line 503 | KD-3 issuer claims (DI) |
| 2 | line 508 | `buscar_ingreso_activo_por_uuid` (V1 — 404 if None) |
| 3 | line 521 | tenant scope (post-V1) |
| 4 | line 537 | V2 subscripcion vigente (only when `ingreso.uuid_subscripcion_cliente IS NOT NULL`) |
| 5 | line 553 | V3 placa matches |
| 6 | line 569 | V4 KD-FORZADO-01 prefix contract |
| 7 | line 574 | `cotizar_para_salida` → `calcular_cotizacion` (F1.8 PL/pgSQL); acquires `SELECT ... FOR SHARE` on `tarifas_sucursal` (KD-S7) |
| 8 | line 619 | **`crear_salida_evento` → INSERT `prod.salidas` [A] (DEC-SAL-01, append-only, REVOKE UPDATE)** |
| 9 | line 653 | optional alerta + **single `session.commit()`** — KD-S7 lock release |
| 10 | line 683 | tipo_salida documented (already derived in Step 7) |
| 11 | line 686 | response shape |
| 12 | line 701 | 201 SalidaReadForzado |

Plus a downstream MV refresh (`mv_ocupacion_diaria`) after commit (line 666).

**The lock that KD-S7 holds from Step 7 through Step 9 is the architectural reason
HU-F1.9 and F1.7 were sequenced** (cotizar → INSERT salida → commit). When `salidas`
gets pushed after pago, the lock can NOT cross the FE-RPC boundary — KD-S7 forces
single-commit. This is the structural reason a "two-step" implementation
(`POST /facturacion/factura` then `POST /operacion/salidas`) needs a fresh handler
that does the lock HOLDS across both writes (Option a) or a relaxed lock discipline
(Option b).

---

## Affected Areas

### Backend

- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:467` (`create_salida`)
  — must NOT be called when cobrar=true until cobro completes. Reorder trigger.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:600-617` (`new_attrs`)
  — adds `fecha_retencion_hasta` (DIAN 2y retention). Reuse for the new "salida
  post-pago" path.
- `backend/packages/parkos_core/src/parkos_core/api/v1/facturacion.py:222`
  (`create_factura`) — needs `uuid_salida` dropped from required (or entirely new
  signature). Currently 12-step; with Option (a), re-use for the cobro side and add a
  new combined endpoint.
- `backend/packages/parkos_core/src/parkos_core/schemas/facturacion.py:578` (`FacturaCreate`)
  — `uuid_salida: uuid_lib.UUID` (required) must become nullable, OR a new
  `SalidaConCobroCreate` schema is added.
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py:425` (`SalidaCreateForzado`)
  — needs `uuid_factura: uuid_lib.UUID | None = None` field (Option b), OR is unused in
  favor of the new combined endpoint (Option a).
- `backend/packages/parkos_core/src/parkos_core/repo/salida.py` — `crear_salida_evento`
  must accept optional `uuid_factura` (Option b) OR be called from a new repo helper
  (Option a).
- `backend/packages/parkos_core/src/parkos_core/repo/factura.py:382`
  (`crear_factura_evento`) — currently sets `uuid_salida` as a required field in
  `new_attrs`. Must become optional for the no-salida-yet path.
- `backend/packages/parkos_core/src/parkos_core/migrations/versions/` — no DB migration
  needed if `uuid_factura` lives in JSONB or is rejected (salidas `[A]` append-only per
  DEC-SAL-01). Confirmed in `modelo_datos_er.mmd:762-778`: salidas has no `uuid_factura`
  column; solution is FK from `prod.facturas.uuid_salida` (nullable for cobro-from-cobro path
  where salida is inserted *during* the same TX, then UPDATEd in the same TX to point at
  the new `facturas.uuid`).

### Backend tests (affected by contract change)

- `backend/tests/integration/test_salida_create_db.py` — happy-path INSERT test will need
  to NOT pre-create `prod.salidas`; now salida is created post-pago.
- `backend/tests/unit/test_operacion_salidas.py` (F1.7 unit, 4 cases) — contract change
  ripples.
- `backend/tests/unit/test_operacion_salidas_kd_forzado.py` — V2/V5 alerts fired
  conditional on bypass; if salida is created post-pago, the alerts may be moved to the
  cobro pipeline instead.
- `backend/tests/static/test_salida_handler_step_order.py` — locks the 12-step order;
  option (a) replaces the chain entirely; option (b) extends it with a new step 7.5
  (`uuid_factura` resolution).
- `backend/tests/static/test_no_write_after_salida_insert.py` — confirms no further
  writes after Step 8. **Will need an explicit exception for the reverse path (UPDATE
  `facturas.uuid_salida`) if option (b) is chosen.**
- `backend/tests/static/test_factura_handler_step_order.py` (likely — verify) — locks
  the 13-step chain for `create_factura`.
- `backend/tests/static/test_factura_handler_single_commit.py` — KD-FACT-01 single-commit
  invariant. Option (a) creates a third single-commit endpoint that owns 5-6 INSERTs;
  the AST walker may need a new test.

### Frontend

- `apps/electron-sucursal/src/features/operacion/components/SalidaFlow.tsx:109-156`
  (`handleConfirmar`) — must NOT call `useRegistrarSalida().trigger()` for rotación.
  Instead, just open `PagoSheet` with the cotizacion context; the BE does the joined
  work.
- `apps/electron-sucursal/src/features/operacion/components/SalidaMensualidad.tsx:102-132`
  — for mensualidad, the operator must give an explicit confirmation modal (per user's
  scope decision) before `trigger()` fires (no payment needed; fee settled by
  subscription). Existing "Confirmar" button may need a new modal wrapper
  (`<ConfirmarMensualidadModal />` shadcn AlertDialog).
- `apps/electron-sucursal/src/features/operacion/components/SalidaPanel.tsx:211-239`
  (`handleOpenPago`) — currently pushes `{uuid_ingreso, uuid_salida, total_cop}` into
  `pagoContext`. For option (a), `uuid_salida` is NULL at open time; for option (b),
  the FE needs to first POST `/facturacion/factura`, get `uuid_factura`, then call
  `useRegistrarSalida({uuid_ingreso, uuid_factura})`, then push `uuid_salida` to
  PagoSheet.
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.tsx:118-313`
  — `pagadoRef.current`, `useAnularSalidaNoPagada` plumbing (lines 134, 184-208) is
  the entire F8.1-b patch. **With option A, this auto-annulment branch becomes DEAD
  code**: there is no `prod.salidas` row to annul when the operador closes without
  paying, because the row was never inserted.
- `apps/electron-sucursal/src/features/facturacion/hooks/useAnularSalidaNoPagada.ts` and
  `useAnularSalidaNoPagada.test.ts` — **proposed for deletion** under option A.
- `apps/electron-sucursal/src/features/facturacion/components/PagoSheet.test.tsx:18-24`
  (P6 + P7 tests) — **proposed for deletion** under option A; or rewritten to assert that
  the close-without-pay path is a no-op (no annulment call).
- `apps/electron-sucursal/src/features/facturacion/api/facturaApi.ts` — `PostFacturaPayload`
  must be enriched with `uuid_salida: string` for option (b), or replaced with a `POST
  /operacion/salida-con-cobro` payload for option (a).
- `apps/electron-sucursal/src/features/operacion/api/salidaApi.ts` —
  `SalidaReadForzado` schema already accounts for the post-pago salida.
- `apps/electron-sucursal/src/renderer/store/dashboardDrawerStore.ts:78-82`
  (`PagoContext`) — `uuid_salida` becomes nullable for option (a).
- `apps/electron-sucursal/src/renderer/App.tsx` (sketch — verify) — monthly subscription
  confirmation modal: where it mounts, what guard ensures the FE shows it for
  mensalidades only.

### Plan / spec docs

- `plan.md:898` ("salidas.estado pasa a 'PAGADO' al completar el pago") — Plan still
  asserts that `salidas.estado` is the column for the "paid" marker. The ER has no such
  column (`modelo_datos_er.mmd:762-778`). **This is a plan↔ER drift** (matches a known
  pattern documented in Engram #1894 / #2051). Under option A, the "INSERT only"
  garantee is strengthened instead.
- `plan.md:438` (DEC-SUC-23) — explicitly states cupo is released immediately at salida
  INSERT. This is the design canon the user is now overriding. **The change creates a
  small DEC-SUC-23-b or DEC-SUC-23' note acknowledging that the model was intentional but
  causes the operator-visible gap; the change moves the cupo's release boundary to
  the pago-completed TX.**
- `openspec/specs/operations/spec.md` — REQ-OPS-042..052 (HU-F1.7/F7.2) — must be
  REDELT'd: change Step 8's "insert salida immediately" to "wait for pago, then insert
  salida in the cobro's TX".

---

## Approaches

### Approach (a) — Backend atómico (new endpoint)

**`POST /operacion/salida-con-cobro`** — single handler that takes the pago body
(`uuid_ingreso`, `medio_pago`, `monto_recibido`, `voucher?`, `cliente`), internally:

1. KD-3 (issuer claims) → V1 (ingreso exists) → tenant scope.
2. **KD-NEW: V_subscript_rotacion_only** — `prod.calcular_cotizacion(uuid_ingreso)` must
   return `cobrar: true`. If `cobrar: false`, reject with `409 mensualidad_no_aplica`
   and tell the FE to use `POST /operacion/salidas` + operator confirmation.
3. KD-S7: acquire `SELECT ... FOR SHARE` on `tarifas_sucursal` (same lock as F1.7
   Step 7 + F1.9 Step 7).
4. Validations V4 (KD-FORZADO-01 prefix) + datafono voucher.
5. **INSERT `prod.salidas`** with the new `uuid_factura=NULL` first (so the FK target
   exists before the FK source row is written). **OR pre-mint the `facturas.uuid` and
   pass it down as `salidas.uuid_factura`** — but `[A]` append-only forbids mutating a
   row, so the operation must INSERT `salidas` with `uuid_factura` already set. The
   clean sequence is:
   - Mint `uuid_salida` and `uuid_factura` UPDATEs the operator-issued UUIDs.
   - INSERT `salidas(uuid=uuid_salida, uuid_factura=uuid_factura, …)`.
   - INSERT `facturas(uuid=uuid_factura, uuid_salida=uuid_salida, …)` (FK bidirectional,
     pre-resolved).
6. INSERT `factura_detalle(N rows)` + `factura_impuestos(1 row)` + `factura_pagos(1 row)`.
7. Single `await session.commit()` (KD-S7 release).
8. FE print pipeline (already wired, untouched).
9. Response: `{uuid_factura, uuid_salida, numero_recibo, items, total}`.

**For mensualidad (option (a) variante):** `POST /operacion/salida-mensualidad` keeps the
existing `POST /operacion/salidas` shape (rotate the existing handler to consume a new
optional `confirmado_operador_explicit: bool` field) — the FE wraps the operator
confirmation in a shadcn AlertDialog before calling.

| Pro | Con |
|-----|-----|
| Atomicidad real: salida + factura + pagos nunca pueden quedar inconsistentes (no FK orphans, no half-paid). | Big handler — 16 steps (F1.7 12 + F1.9 13, deduped ~5). Estimated 280–380 LOC backend. |
| Simplifica FE: una sola POST; no choreography; no race entre UUIDs. | El FE necesita el mismo endpoint para rotación Y mensualidad? Mejor crear 2 endpoints separados para mantener explosión semántica. |
| Cashier-state-clean: `prod.facturas.uuid_salida` populated at INSERT time, no UPDATE needed. `V_INGRESO_ESTADO` flips `cerrado` immediately on commit. | Alarga el lock `SELECT FOR SHARE` on `tarifas_sucursal` para que cubra la escritura de `factura_detalle`/`factura_impuestos`/`factura_pagos` — KD-S7 se mantiene, pero la latencia del lock pasa de "salida only" a "todo el pago". |
| El huérfano scenario desaparece: si el operator cierra el modal sin pagar, NO se llama nada, no hay nada que limpiar. **El código F8.1-b (`useAnularSalidaNoPagada` + PagoSheet `handleClose`) se elimina.** | Tests: hay que reescribir `test_salida_create_db.py` + `test_factura_handler_step_order.py` + el AST walker `test_salida_handler_step_order.py`. Estimado de churn en tests: 300+ LOC. |
| Patrón KD-FACT-01 (single commit) ya está duplicado en `clientes_venta.py` (8a) — agregar un tercer caso es razonable. | Riesgo: si por error otro caller llama al endpoint viejo, se rompe la regla auditoría. Mitigación: el endpoint viejo `POST /operacion/salidas` rota a `DEPRECATED` y retorna 410 Gone (defense in depth). |
| | Mayor delta de archivos en `apps/electron-sucursal`: `facturaApi.ts`, `useRegistrarPago.ts`, `PagoSheet.tsx`, `useAnularSalidaNoPagada.{ts,test.ts}`, `PagoSheet.test.tsx` — todos impactados. Estimado 700-1000 LOC frontend churn. |
| | `plan.md:898` dice "salidas.estado pasa a 'PAGADO' al completar el pago" — cambiamos esto a "salidas y factura nacen juntas, no hay UPDATE → estado es derivado via `V_INGRESO_ESTADO`". SPEC DRIFT conocido. |

**Effort: Medium-High.** BE: ~280–380 LOC + tests (~350 LOC). FE: ~600–1000 LOC (incluye eliminación de F8.1-b). Tests AST: ~80 LOC. Total forecast: ~1300–1800 LOC (sobre el per-HU review budget de **800** que el orchestrator confirmó para F8.x; meta-budget 2000 NO aplica — explícito en el prompt).

### Approach (b) — Backend dos pasos

**Two endpoints kept; one new body field.**

1. Modify `POST /facturacion/factura` to accept `uuid_salida: uuid_lib.UUID | None`.
   When NULL, the handler does NOT call `buscar_salida_facturable` and stores
   `facturas.uuid_salida = NULL`. Downstream V_FACTURA_ESTADO is unaffected (still emits
   based on `anulaciones + factura_pagos` join).
2. Modify `POST /operacion/salidas` to accept `uuid_factura: uuid_lib.UUID | None`.
   When NULL (legacy path), behavior is unchanged. When present, the handler Step 8
   INSERTs `salidas` with `uuid_factura=uuid_factura` (the column would need to be
   added or hidden in a JSONB `datos_nuevos` since `prod.salidas` has no such column).
3. FE rewires: (a) cotizar, (b) PagoSheet posts `POST /facturacion/factura` with
   `uuid_ingreso` only (no `uuid_salida` yet) — receives `uuid_factura` in response,
   (c) then `useRegistrarSalida().trigger({uuid_ingreso, uuid_factura})`,
   (d) post-print envelope as today.
4. **Cupo release point is now the post-factura pago commit**, not the post-salida
   INSERT — but since `salidas` is the `[A]` event that closes the ingreso in
   `V_INGRESO_ESTADO`, the visual state still flips at the salida INSERT.

| Pro | Con |
|-----|-----|
| Endpoints existentes se preservan — los callers que no sean rotación (suscripción venta, reimpresión, etc.) no se rompen. | **NO atómico.** Si el FE crashes entre (b) y (c), queda una `factura` sin `salida` asociada. Cobrador+salida divorciados en `V_INGRESO_ESTADO`. La conciliación queda como trabajo manual / cron job huérfano. |
| Menor churn en backend handler: dos ediciones quirúrgicas (cada una ~50 LOC + tests) vs un endpoint nuevo de 280-380 LOC. | Doble round-trip FE→BE→FE→BE: latencia visible (3G/4G kiosko link inestable = timeouts, customer walking away). |
| El código F8.1-b (auto-annul) puede quedarse en paz: si la salida NO se inserta en (c), no hay nada que anular. Pero hay que armar una transición para "factura sin salida" (cobro sin vehículo saliendo) — Y esto contradice DEC-SUC-23 ("el monto viaja en estado de UI hasta que se persiste como facturas") porque ahora la factura SE persiste antes de la salida. **Esto transforma 'reimpresión' en anomalía.** | El cobro queda persistido ANTES de que el ingreso cierre. La liquidación `get_operacion_ocupacion` puede sobre-contar cupos (un coche ya cobrando sigue ocupando cupo hasta que se confirme la salida). Riesgo operativo HIGH si el cliente paga y se va sin scan de salida. |
| Lock duration: KD-S7 se aplica por separado en cada endpoint. No se alarga. | **SPEC DRIFT**: el modelo de datos (modelo_datos_er.mmd:677) dice explícitamente "Lifecycle derivado via vista V_FACTURA_ESTADO (anulaciones ejecutadas) - no se almacena (4FN + insert-only)". Hoy la factura es un insert que depende de la salida: FK `facturas.uuid_salida`. Si permitimos `uuid_salida = NULL` para rotación normal, rompemos la integridad referencial conceptual del modelo. |
| | FK enforcement: la DB no tiene `FOREIGN KEY (uuid_salida)` declarada (verificar ER — `facturas.uuid_salida FK "salida que cerró la estadía facturada"`, modelado:762 relations), así que `NULL` es físicamente válido. Pero la promesa semántica del modelo se rompe. |
| | Tests churn menor pero manejo de errores nuevos (`factura_sin_salida_huerfana`, `salida_sin_factura_previa` reconciler). |
| | Salida mensualidad sigue separada; ese endpoint se mantiene en `POST /operacion/salidas/mensualidad` (nuevo, según plan).

**Effort: Medium.** BE: ~120 LOC + tests ~150 LOC (incluyendo reconciler/diagnostic endpoint). FE: ~700 LOC (reordenamiento del flujo + nuevo modal mensualidad si se incluye). Total forecast: ~1100 LOC.

---

## Cupo (release) semantics — recommandé decision

In approach (a), the cupo is released at the END of the atomic TX, when the
`session.commit()` succeeds. The MV (`prod.mv_ocupacion_diaria`) refresh inside the
handler keeps the same observability guarantees as today (post-commit refresh
try/catch + log+continue on failure, operator never blocked by MV).

In approach (b), the cupo is released at the SECOND commit (the `POST /operacion/salidas`
commit). Same observable behavior, but a tiny window opens between the two commits where
the cliente already paid (factura + factura_pagos persisted) but the cupo still counts
them. For a 200-300ms gap on a healthy connection this is fine. For a flaky 4G
connection this can be minutes — operator will see "vehiculos dentro = 51 / 50" until
the second POST lands. Recommend an idempotent retry helper (already exists per the F2.2
auth/retry precedent) to close the gap.

**Recommended semantic regardless of approach:** release cupo at the LAST write that
commits in the chain that closes `V_INGRESO_ESTADO`. For approach (a) that's the
`salida+fatura+pago` commit. For approach (b) that's the second commit.

---

## Monthly subscription: confirmation modal

The user ratified: even though no cobro happens, the operator must give explicit
confirmation in a modal before the salida is registered. Both approaches inherit this
constraint. The implementation is independent of the atómico/dos-pasos choice — it's a
shadcn `<AlertDialog>` wrapping the "Confirmar" button in `<SalidaMensualidad />`, with
two-step confirmation: "Press 1 to confirm" or "Hold-to-confirm 2s" pattern.

Open: should there be a tiempo de expiración? The current `cotizar_para_salida` returns
15 min (REQ-OPS-146); for mensualidad that's nonsense (no cobro). Reuse the existing
cotizacion as a "subscripcion still vigente" check (not as a price-quote TTL). The
modal can offer a "Renovar mensualidad" link if the subscripcion is expired (redirects
to the wizard at `/clientes/venta-suscripcion`).

Audit: every explicit confirmation should log to `prod.alerta` with
`tipo_alerta='confirmacion_explicit_mensualidad'` (new catalog value). This provides the
"who confirmed this" trail that plan.md's CU-04 BR5 calls for.

---

## Recommendation

**Approach (a) — backend atómico via `POST /operacion/salida-con-cobro`.** Rationale:

1. **El gap del operador se cierra con UNA POST.** Las dos pasos crean un failure mode de
   "factura cobrada sin salida" exactamente del tipo que el usuario quiere evitar. El
   problema que el usuario planteó fue "que pasa si llegan hasta allá y no pagan y queda
   cerrado" — el approach (b) introduce un problema complementario "que pasa si paga y
   la salida no se inserta".
2. **El código F8.1-b desaparece limpiamente.** Los hooks `useAnularSalidaNoPagada`,
   `PagoSheet.handleClose`, PagoSheet P6/P7 tests, todos se eliminan — no son
   "fix forward", son trabajo que el approach (a) vuelve innecesario. Esto es el ROI
   más tangible del approach (a): -260 LOC de código defensivo que nunca debería
   haber existido si el contrato original hubiera sido coherente.
3. **Una sola atomicidad cumple KD-S7 KD-FACT-01 KD-FE-01 en un solo lugar.** Los tres
   patterns single-commit ya están duplicados en el codebase (F1.7 + F1.9 + clientes_venta).
   Unir el patrón bajo un endpoint consciente es el siguiente paso natural del refactor.
4. **Forzamos a resolver la spec drift `plan.md:898` ("salidas.estado='PAGADO'")** que
   está mal — el modelo no tiene columna `estado`. Mejor corregir ahora en F8.1 que
   arrastrar el bug a Fase 11/12 cuando más código dependa de él.

**Costos que aceptar:**

- 1300-1800 LOC forecast total: 600-800 BE+tests + 600-1000 FE. **Sobre el review budget
  per-HU de 800.** Requiere chained PR o size:exception ratification.
- Reescritura de test AST `test_salida_handler_step_order.py`. Es la única static-test
  que rompe semánticamente. Necesita un `test_salida_con_cobro_handler_step_order.py`
  nuevo que documente el AST del nuevo endpoint.
- DEC-SUC-23 cambia: cupo ya no se libera en el INSERT de salida, sino en el commit del
  pago. Plan.md necesita una nota de plan↔ER reconciliation.

---

## Risks

1. **Churn de tests AST.** `test_salida_handler_step_order.py` y `test_no_write_after_salida_insert.py`
   son canónicos (lockean la cadena de 12 pasos + el no-escribir-después-INSERT). El
   approach (a) los invalida. Plan: crear `test_salida_con_cobro_handler_step_order.py` con
   los 16 pasos nuevos + mantener el viejo endpoint como DEPRECATED (rutas retornan 410)
   para que la suite legacy siga verde.

2. **`factura_pagos` REQUIRES `uuid_factura` populated.** Schema line 443. Si el approach
   (a) mint-ea primero `salidas` con `uuid_factura=NULL`, después agrega la FK desde
   `facturas`, NO funciona sin UPDATE. Solución: el plan es pre-mint ambos UUIDs
   (`salidas.uuid` Y `facturas.uuid`) antes del primer INSERT, y setear ambos FK en el
   mismo INSERT (bidireccional). **Requiere refactorizar `crear_factura_evento` para no
   autogenerar el UUID de la factura**, sino aceptar uno pre-asignado.

3. **Lock contention.** El `SELECT ... FOR SHARE` sobre `tarifas_sucursal` actualmente
   se mantiene ~80ms (estimado del flujo de cotizar solo). Con approach (a), el mismo
   lock cubre ~250-400ms (INSERT 5-6 filas extras). Bajo carga (8 cajeros simultáneos
   facturando a la vez en una sede grande) puede causar convoy; mitigation: el patrón
   ya está probado (F1.9 mantiene el lock a través de 4 tablas), agregar una 5ª no
   cambia la dinámica.

4. **FE removal de `useAnularSalidaNoPagada` deja código WIP huérfano.** `fix/hu-f8-1-anular-salida-no-pagada`
   (la rama actual) tiene `PagoSheet.tsx`, `useAnularSalidaNoPagada.{ts,test.ts}`,
   `PagoSheet.test.tsx` modificados. Todos esos cambios se mueven a `git revert` o
   `git checkout dev -- <files>` cuando aplicamos el approach (a). **Confirmar con el
   orchestrator antes de apply si el usuario quiere preservar alguna parte de F8.1-b
   como audit-trail.**

5. **`V_INGRESO_ESTADO` transient state.** Durante el approach (a) el handler está
   bloqueado dentro del mismo TX; el operador no ve paneles intermedios (no hay
   "salida insertada pero factura pendiente"). Pero los webhooks de sync (`sync_outbox`
   del BE) ven la transición ABrupta. Si el cloud-side reconciler asume "salida es
   acto 1, factura es acto 2" puede romperse. **Mitigation:** verificar con
   `repo/sync_outbox.py` cómo se publican los eventos `[A]` (probablemente
   individualmente). Si se publican individualmente, el FE reconciler del cloud ve la
   salida Y la factura en el mismo sync tick — sin problema.

6. **SPEC DRIFT `plan.md:898`.** El plan dice "salidas.estado pasa a 'PAGADO'". El
   modelo no tiene esa columna. Esto es un bug de plan↔ER conocido (Engram #1916
   documentó el patrón). Approach (a) NO introduce el bug — ya existe. Pero nuestra
   change debe anotar el drift y proponer una corrección (probablemente: borrar la
   línea del plan o reemplazar por "el cobro y la salida nacen juntos, el estado
   derivado es via `V_INGRESO_ESTADO`").

7. **`models/A/factura_pagos.uuid_factura` is NOT NULL in SQLAlchemy** (verify at
   `models/A/factura_pagos.py:62`). Plan is fine — factura_pagos always references a
   real factura. No drift.

8. **`tests/static/test_no_delete_routes.py` + `test_no_write_in_caja_sesion_me.py`** —
   These static tests guard no-DELETE + read-only invariants. Approach (a) does not
   violate either, but the new endpoint must NOT contain a `DELETE` route, an `UPDATE`
   free-SQL, or a raw UPSERT. The factory `router_factory` will reject anyway, but
   verify the new handler doesn't ship with ad-hoc SQL outside repo helpers.

---

## Ready for Proposal

**Yes** — with 3 items the orchestrator must surface to the user before `sdd-propose`:

1. **Choose approach (a) or (b).** This exploration strongly recommends (a) for the four
   reasons above. The orchestrator should: (i) confirm with the user OR ratify alone if
   the user already implied (a), (ii) if (a), propose the endpoint name and signature
   (`POST /operacion/salida-con-cobro` is suggested), (iii) if (b), propose the
   `FacturaCreate.uuid_salida | None` breaking change.

2. **F8.1-b (auto-annulment) disposition.** Under approach (a), the entire
   `fix/hu-f8-1-anular-salida-no-pagada` WIP branch becomes obsolete. Two sub-options:
   (i) **abandon cleanly** — `git checkout dev -- <files>` + delete the two new files,
   the operator's worry is structurally solved; (ii) **preserve as audit-trail** — keep
   the test files but route the annulment to `prod.alerta` instead of `prod.anulaciones`
   (no behavior but documents "this branch spent N days solving a gap the architecture
   finally closes"). Recommended: option (i) cleaner.

3. **`SalidaMensualidad` confirmation modal.** Confirm spec: shadcn AlertDialog with
   texto "Confirmar salida sin pago (mensualidad vigente)". Should the modal log to
   `prod.alerta` with `tipo_alerta='confirmacion_explicit_mensualidad'`? Should there
   be a 2-second hold-to-confirm timer for safety? Confirm with the user.

Once those three are answered, `sdd-propose` can draft the proposal with the chosen
approach and the audit-trail disposition baked in. Forecast for chained PR split
(strategy: 1 endpoint + 1 schema change + 4 FE renames + 2 test rewrites = 4 chained
PRs at ~400 LOC each, under the 800 per-HU budget without needing size:exception).
