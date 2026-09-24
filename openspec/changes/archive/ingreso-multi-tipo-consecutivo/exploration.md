# Exploration: ingreso-multi-tipo-consecutivo

> **Phase**: explore (sdd-explore) · **Status**: ready for sdd-propose
> **Change name**: `ingreso-multi-tipo-consecutivo`
> **Folder**: `openspec/changes/ingreso-multi-tipo-consecutivo/`
> **Working dir**: `E:/easypunto_parkos` · **Platform**: Windows PowerShell 5.1
> **Branch**: feature branch TBD (the parent commit is `281bb66 chore(backend): seed tipos_vehiculo + cupos for D2049f2` on `feature/seed-tipos-vehiculo-d2049f2`)
> **PR target**: `origin/dev` (gitflow; SDD full lifecycle)
> **Date**: 2026-09-22
> **Author**: Parkos Dev <dev@parkos.local>
> **Inputs**: `modelo_datos_er.mmd` lines 577-596 (canonical `[L-E] ingreso` shape, 4NF, no `consecutivo` column); `plan.md` lines 437-468 (DEC-SUC-22 strict regex; A-04 forzado prefix; A-05 audit-only print state); `openspec/changes/archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo/exploration.md` (closest precedent for this kind of feature HU); `openspec/changes/archive/2026-09-15-hu-f1-6-validaciones-post-ingresos` (precedent for the V1-V9 validation chain); `openspec/changes/archive/2026-09-17-fase-7-3-tiquetes-salida/proposal.md` (precedent for byte-fixture + `<TiqueteModal>` updates + bridge.imprimir wiring)

## Summary

Today the operator's `POST /operacion/ingresos` flow accepts only `carro` and `moto`, identified by a regex over the typed placa (`detectar_tipo_vehiculo()` in both client and server, `^[A-Z]{3}[0-9]{3}$` and `^[A-Z]{3}[0-9]{2}[A-Z]$`). Vehicles that have no placa — `bicicleta` and `patineta` per the recently seeded catalog (`tipos_vehiculo` + `cantidad_vehiculos_sucursal` merged 2026-09-22, commit `281bb66`) — have no path to register. This change opens that path: the operator picks a no-placa tipo via a new UI flow, the backend stamps a per-`(uuid_sucursal, uuid_tipo_vehiculo)` monotonic `consecutivo` in the format `<TIPO>-<NNNNNN>-<uuid8>` (e.g. `BICI-000001-3f8a1b2c`), persists it as a new column on `prod.ingreso`, and reuses the existing V1+V2 cup validator with bici/patineta configured cupos. The change touches the request/response schema, the `Ingreso` ORM, the tiquete template, and the principal page (toggle between placa-driven and no-placa flows), while preserving every architectural invariant in `AGENTS.md` (audit-first, bi-temporal, C/Q/U-no-D, multi-tenant, hash chain).

## Current state — verified

### Catalog + cupos (precedent work, already shipped)

- **`backend/scripts/seed_tipos_y_cupos_sucursal.py`** lines 1-205 — Just merged to `dev` (commit `281bb66`). Seeds 4 `tipos_vehiculo` rows (`carro`, `moto`, `bicicleta`, `patineta`) into both `prod.tipos_vehiculo` (cloud + branch) and per-branch `cantidad_vehiculos_sucursal` (branch only) for `UUID_SUCURSAL = "2049f2cd-b2a8-4e45-9d19-31fa87eb67c6"` (50/30/20/10 cupos respectively). The `TiposVehiculo.tipo` strings are **lowercase** (`"carro"`, `"moto"`, `"bicicleta"`, `"patineta"`), matching the canonical seed. Quote (lines 19-22 of the script): *"the canonical seed for branch containers … uses lowercase `carro` / `moto` / `bicicleta` / `patineta`"*.
- **`backend/packages/parkos_core/src/parkos_core/repo/placa.py`** lines 47-87 — `detectar_tipo_vehiculo()` accepts `placa: str | None` and returns `None` when `placa is None` (line 73) — **the helper is already None-safe**. The helper looks up `TiposVehiculo.tipo.in_(["carro", "moto", "bicicleta", "patineta"])` (line 82) so the catalog side is ready for bici/patineta even though the regex side does not match them.
- **`backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py`** lines 138-214 — `validar_cupo_disponible()` is fully tipo-agnostic; it filters the MV result by `uuid_tipo_vehiculo` (line 186). With the bici/patineta cupos already seeded, V2 will return `cupo_agotado=True` when 20 bicicletas are inside the parqueadero — no helper changes needed.

### Backend POST handler — the chain that must accept a null placa

- **`backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py`** lines 145-316 — `create_ingreso()` runs the 11-step V-chain. Step 2 (lines 186-197) is the only step that **rebota with 422 `placa_formato_invalido`** when the regex does not match. Quote (line 186-188): *"uuid_tipo_vehiculo = payload.uuid_tipo_vehiculo / if uuid_tipo_vehiculo is None: / uuid_tipo_vehiculo = await detectar_tipo_vehiculo(session, payload.placa)"*. The explicit-UUID short-circuit (line 186) is already in place since REQ-OPS-134 — `payload.uuid_tipo_vehiculo` always wins over the regex. **The handler will accept a null-placa payload as long as the client supplies `uuid_tipo_vehiculo`**.
- **Step 8 (lines 271-274)** — Calls `existe_ingreso_activo(session, uuid_sucursal=target, placa=payload.placa or "")`. Today this works only because every ingreso has a placa; for no-placa ingresos this would search by `placa=""` (always empty), which currently returns no false positives. After this change, the operator could create two no-placa ingresos back-to-back — we must decide whether to skip V8 when `payload.placa is None` (recommended) or rely on the `consecutivo` UK (see §Open questions).
- **`backend/packages/parkos_core/src/parkos_core/repo/ingreso.py`** lines 57-127 — `existe_ingreso_activo()` is a single SQL `EXISTS` with `i.placa = :placa` (line 77). It accepts an empty string and returns no rows. Safe to call with `placa=""` but **does not prevent** two empty-placa ingresos in the same sucursal. Must be conditionally skipped for the no-placa path.
- **`backend/packages/parkos_core/src/parkos_core/schemas/operacion.py`** lines 75-104 (`IngresoCreate`) and lines 280-316 (`IngresoCreateForzado`) — Both already declare `placa: str | None = None` and `uuid_tipo_vehiculo: uuid_lib.UUID | None = None`. **No schema change is needed to accept `placa=null`**; we only need to add `consecutivo: str | None = None` to the request + response. The `IngresoRead` response shape (lines 50-72) needs the same column added so `<TiqueteModal>` can render it.
- **`backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py`** lines 28-60 — `Ingreso` ORM is `LifecycleEventBase` (insert-only, no UPDATE, AST-locked by `tests/static/test_no_write_after_insert.py`). Currently exposes 6 business columns. Adding a new nullable column `consecutivo` is a metadata-only `ADD COLUMN` (PG11+); the AST lock still holds because the column is INSERT-time only.
- **`backend/packages/parkos_core/migrations/versions/0037_add_uuid_subscripcion_cliente_to_facturas.py`** — Direct precedent for "add a nullable column + FK to an existing `[L-E]` table" (87 lines, idempotent via `ADD COLUMN IF NOT EXISTS` + `DO $$` block). The `consecutivo` column does not need a FK (no `prod.consecutivo` table); it is a pure business value, NOT a DIAN `consecutivo` (DIAN uses `prod.factura_electronica.consecutivo` which is unrelated to this change — see Risks R3).

### Frontend — the operator UI that needs a parallel no-placa path

- **`apps/electron-sucursal/src/features/operacion/pages/Principal.tsx`** lines 1-403 — The `Principal` page orchestrator. Line 268 renders a single `<PlacaInput>` and lines 97-145 (`handlePlacaSubmit`) drive the 201 + error mapping. The component is a single entry point; adding a no-placa flow requires either (a) a toggle above the input that swaps the panel, or (b) two buttons rendered side-by-side. The user has decided "two buttons separated" (per the orchestrator's brief, item 2 in "Decisiones ya tomadas").
- **`apps/electron-sucursal/src/features/operacion/components/PlacaInput.tsx`** lines 49-57 — `placaFormSchema.placa` is REQUIRED with the regex `REGEX_AUTO | REGEX_MOTO`. **The Zod schema makes `placa` non-nullable on the cliente**; we need a parallel `<IngresoSinPlacaPanel>` (or a similar name) that drives a separate Zod schema where `placa` is absent and `uuid_tipo_vehiculo` is REQUIRED.
- **`apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx`** lines 65-389 — The dashboard-hub variant of `Principal` (inlined into `DrawerHost.tsx` per the orchestrator-dashboard-hub PR-3). **Both `Principal` and `IngresoPanel` need the same dual-flow treatment** — they are duplicate-shaped by design (F6.1 + operador-dashboard-hub precedent). The work-unit-commits split will have to choose: update both in the same PR (atomic dependency) or factor a shared `<TipoIngresoToggle>` component first.
- **`apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts`** lines 33-49 — `PostIngresoPayloadSchema` declares `placa: z.string().regex(...)` as REQUIRED and `uuid_tipo_vehiculo: z.string().uuid()` as REQUIRED. **Both must become optional/conditional** so the same endpoint serves two payloads. **Discriminated union is the cleanest shape** — payload variant is `{ placa: string, uuid_tipo_vehiculo?: string }` (auto) or `{ placa: null, uuid_tipo_vehiculo: string, consecutivo: string }` (bici/patineta). The response shape (lines 43-48) needs `consecutivo: z.string().nullable()` added so `<TiqueteModal>` can render it.
- **`apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx`** lines 110-128 — Currently renders `Folio: {uuid_ingreso}` + `Tipo: {tipo_entrada}`. For bici/patineta, we must render `Identificación: {consecutivo}` in place of `Placa` (since there is no placa). The "always-on Imprimir" button (line 139-148) calls `buildPrintPayload(uuid_ingreso)` — `Principal.tsx:369-385` and `IngresoPanel.tsx:361-373` both build a stub `Buffer.from("tiquete:entrada:"+uuid, "utf8")`; a real `escposBuilder.build('entrada', payload)` will need `consecutivo` passed in.
- **`apps/electron-sucursal/src/lib/print/escposBuilder.ts`** line 205 — `lines.push(utf8("Placa: ${payload.placa}\n"))` is the doceavo line of the 19-field `buildEntradaBuffer`. For bici/patineta, this line must either be replaced with `Identificación: ${payload.consecutivo}` or guarded: `payload.placa ? Placa ... : Identificación ...`. **Precedent**: `escposTemplates.ts` lines 215 (`entradaPayloadSchema`) and 513 (`reciboPayloadSchema`) — both have `readonly placa: string`. Making `placa` nullable on the Zod schema + emitting a different label on a falsy value is the minimal change.
- **`apps/electron-sucursal/src/lib/print/escposTemplates.ts`** lines 142-156 — `placaSchema = z.string().regex(REGEX_AUTO|REGEX_MOTO)` is REQUIRED on every template that references `placa`. The 4 templates (`entradaPayloadSchema`, `salidaPayloadSchema`, `salidaMensualidadPayloadSchema`, `reciboPayloadSchema`) all reference it. **A schema relaxation here is a breaking change for salida/recibo** (which legitimately expect a placa on the ingreso). The cleanest approach: introduce a discriminated union at the template level (`EntradaPlaca | EntradaConsecutivo`) so `escposBuilder.build('entrada', payload)` only accepts the variant matching the tipo.

### i18n namespace

- **`apps/electron-sucursal/src/renderer/i18n/locales/operacion.json`** — Namespace pre-exists with 10+ keys (`ingreso`, `salida`, `placa`, `registrar`, etc.). The user's brief specifies `operacion` as the target namespace; keys to add: `ingreso_sin_placa_cta`, `ingreso_sin_placa_selector_label`, `ingreso_sin_placa_tipo_bicicleta`, `ingreso_sin_placa_tipo_patineta`, `ingreso_sin_placa_generar_boton`, `ingreso_sin_placa_exito`, `tiquete_identificacion_label` (replaces `tiquete_placa_label` for no-placa flow).

### Tests that already exist

- **`apps/electron-sucursal/src/lib/validation/placa.test.ts`** — 8 unit tests for `detectarTipoVehiculo()`. Unaffected by this change (no-placa path does not call `detectarTipoVehiculo`).
- **`backend/tests/unit/test_operacion_ingresos_validaciones.py`** — 8 parametrized scenarios for `POST /operacion/ingresos`. To be extended with 4 new scenarios (no-placa + bici, no-placa + patineta, no-placa + cupo agotado, no-placa + UUID error).
- **`apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts`** — 19-field byte fixture. To be extended with a 20th field case: `consecutivo` instead of `placa` for bici/patineta.
- **`apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts`** — HTML mirror. Same extension.

### Architectural invariants to honor

1. **`[L-E]` insert-only** — `consecutivo` is assigned at INSERT time, never UPDATEd (the AST walk `tests/static/test_no_write_after_insert.py` already enforces this; the new column must be in the INSERT path only, never in `new_attrs` of any UPDATE).
2. **Bi-temporal** — `Ingreso` carries `created_at`/`created_by` from `LifecycleEventBase`; no `vigente_desde`/`vigente_hasta` because it is not versioned. The `consecutivo` is a one-time value stamped at the moment of the event; versioning it would require a separate `[V]` projection table, which is out of scope.
3. **C/Q/U no DELETE** — No `DELETE` endpoint needed. No "cancelar ingreso sin placa" workflow because bici/patineta salidas are already modeled as `INSERT INTO prod.salidas`. The `consecutivo` stays on the row forever (per audit-first).
4. **Multi-tenant** — The `consecutivo` MUST be unique per `(uuid_sucursal, uuid_tipo_vehiculo)` — two branches can both have `BICI-000001-3f8a1b2c` without collision. Implementation choice: per-sucursal `SEQUENCE` per tipo, OR app-side counter via `MAX(consecutivo)+1` over a lock. See §Approaches below.
5. **Hash chain** — `consecutivo` is part of the row → ends up in `log_transaccional.datos_nuevos` automatically (via `record_event`'s canonical payload). The hash chain carries forward without any explicit handling (verified per `backend/packages/parkos_core/src/parkos_core/repo/event.py:115-137`).
6. **Sync (eventual)** — `[L-E]` tables are `branch_to_cloud` replicated (per `cloud-edge-sync-architecture` decision §4, sync pipeline is stub per PR9b). `consecutivo` flows with the row; cloud preserves the branch-assigned value. No additional sync configuration needed.

## Gaps

| # | Gap | Impact | Resolution path |
|---|---|---|---|
| G1 | `Ingreso` ORM has no `consecutivo` column | Cannot persist the new business value | Migration `0042_add_consecutivo_to_ingreso.py` adding `consecutivo: String(20) NULL` (nullable for backward compat — existing rows get NULL). UK on `(uuid_sucursal, uuid_tipo_vehiculo, consecutivo)` only when `consecutivo IS NOT NULL` (partial unique index; existing carro/moto rows stay non-unique). |
| G2 | `IngresoCreate.placa` is REQUIRED on frontend (Zod) | Cliente cannot send `placa=null` for bici/patineta | Refactor `PostIngresoPayloadSchema` to a discriminated union: `z.discriminatedUnion('placa_presente', [z.object({placa_presente: z.literal(true), placa: placaRegex, ...}), z.object({placa_presente: z.literal(false), uuid_tipo_vehiculo: uuidSchema, consecutivo: stringNonEmpty, ...})])`. Client must explicitly declare the variant. |
| G3 | `Principal.tsx` and `IngresoPanel.tsx` both render a single `<PlacaInput>` | The no-placa path has no entry point | Either (a) two CTA buttons side-by-side: "Con placa" + "Sin placa", or (b) a toggle above the input that swaps between `<PlacaInput>` and `<IngresoSinPlacaPanel>`. The user has chosen (a). Both `Principal` and `IngresoPanel` must be updated. |
| G4 | Backend Step 8 (`existe_ingreso_activo`) is unconditional | For no-placa, it searches by `placa=""` which always returns 0 rows — never blocks a duplicate no-placa ingreso | Either skip V8 when `payload.placa is None` (cleanest) OR rely on the partial unique index from G1 to enforce at DB level (defense in depth). Recommend BOTH: skip V8 in handler AND add partial UK as a safety net. |
| G5 | `validar_tipo_vehiculo_vigente` (Step 3, `repo/ingreso.py:34-54`) rejects inactive tipos | For bici/patineta, the tipo UUID must come from the F4.1 catalog; the fallback `HARDCODED_CATALOG` only contains carro+moto | Update `HARDCODED_CATALOG` in `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` to include bicicleta + patineta (with sentinel UUIDs that the sentinel-guard in `Principal.tsx:111-125` already filters out → backend derives via V5 by allowing cliente to send `uuid_tipo_vehiculo=null` for the no-placa path). Actually cleaner: for no-placa, the client MUST supply `uuid_tipo_vehiculo` explicitly (operator picks via `<TipoSelect>` from a NEW hook `useTiposVehiculoSinPlaca()` that returns ALL active tipos). |
| G6 | `escposBuilder` and `fallbackBrowser` always render `Placa:` | No way to print the `Identificación:` line for bici/patineta | Discriminated union on the template: `EntradaPayloadConsecutivo` extends the base with `readonly placa: null` and `readonly consecutivo: string`. Builder renders `Identificación: ${payload.consecutivo}` when `payload.placa === null`. Byte-fixture test pins the literal `Identificación:` byte sequence. |
| G7 | `<TiqueteModal>` shows `Folio: {uuid_ingreso}` only | For bici/patineta, the operator must see `Identificación: BICI-000001-3f8a1b2c` for the customer to take home | Add `consecutivo?: string | null` to `TiqueteModalProps`. Render `Identificación: {consecutivo}` when present, else the existing `Folio: {uuid_ingreso}` line. The uuid is still printed in the QR (DEC-SUC-26); both stay on the ticket. |
| G8 | `useTiposVehiculo()` (`features/catalogos/hooks/useTiposVehiculo.ts`) returns carro+moto from the fallback; client has no bicicleta/patineta sentinel | Operator cannot pick bicicleta/patineta from the `<TipoSelect>` | Extend the fallback to include `{tipo: 'bicicleta', uuid: '...0003'}` and `{tipo: 'patineta', uuid: '...0004'}`. Add a new exported hook `useTiposVehiculoSinPlaca()` that filters out carro+moto and returns only bici/patineta (for the no-placa flow). Reuse `useTiposVehiculo()` for the dashboard strip (all 4 tipos). |
| G9 | Idempotency-Key derivation uses `SHA256(POST\|path\|canonicalJSON(payload))` — a bici/patineta payload with `placa=null` produces a different key than `placa=""` | Retries of the same operator action always produce the same key (good), but a stale retry with `placa=""` (from a previous F6.1 schema) would map to a different idempotency row | The change to `placa: str \| None` is a one-way breakage; we accept the migration risk. Document in `proposal.md` that any in-flight client retries after deploy will see 409 (duplicate idempotency key) — but this is mitigated by the operator simply re-trying (the client generates a new canonicalJSON each time the operator edits). |
| G10 | `IngresoRead` does not expose `consecutivo` | Client cannot read it from the GET response | Add `consecutivo: str \| None = None` to `IngresoRead` (lines 50-72 of `schemas/operacion.py`). Pure additive — no wire break for existing clients (Pydantic `extra='forbid'` would reject the column on the `IngresoRead` schema because it is not declared). |
| G11 | The `mv_ocupacion_diaria` materialised view joins `prod.ingreso` to count `activos` per `(uuid_sucursal, uuid_tipo_vehiculo)` | No-placa ingresos will count correctly (they have a `uuid_tipo_vehiculo`) — verified mentally but not empirically. Add an integration test to assert `activos` increments on a no-placa INSERT. | Migration `0042` must include a re-create or REFRESH of the MV; or rely on `pg_partman` cron. Add a regression test in `backend/tests/integration/test_ocupacion_view.py` for the no-placa INSERT path. |
| G12 | `tiqueteModal.test.tsx` does not exist (TiqueteModal has no unit tests — verified by codegraph warning) | The new `Identificación` line ships untested at the component level | Add `apps/electron-sucursal/src/features/operacion/components/__tests__/TiqueteModal.test.tsx` with 2 cases: placa-flow (existing), consecutivo-flow (new). |

## Approaches

### A1 — Server-side trigger `BEFORE INSERT` for `consecutivo`

The DB trigger reads `MAX(consecutivo)+1` over `(uuid_sucursal, uuid_tipo_vehiculo, 'BICI')` and inserts the next value. Lock-free via the implicit row-write lock on the partial UK.

- **Pros**: No app-side coordination. Idempotency is implicit (retry of the same INSERT would re-fail the UK on `consecutivo` but INSERTs are auto-rolled-back if the rest of the TX fails). Aligns with the existing DB-level discipline (triggers own `vigente_desde`, `created_at`).
- **Cons**: Adds another trigger to the `[L-E]` table (currently `fn_set_vigente_inicial` + `fn_audit_columns` exist for `[V]`; `[L-E]` uses `LifecycleEventBase` server defaults only). Adds a `BEFORE INSERT` trigger that lives outside the existing helper surface. Testability suffers (must use `pg_dsn` to seed scenarios; can't unit-test in pure Python).
- **Effort**: HIGH (migration + trigger + 3 trigger-function-carve-outs + integration tests).

### A2 — App-side `assign_consecutivo(uuid_sucursal, uuid_tipo_vehiculo)` helper (preferred)

Mirrors the existing `repo/resolucion_facturacion.py::assign_consecutivo` (lines 47-183) — `SELECT ... FOR UPDATE` on a counter row, compute next, return. Reuses the same idempotency pattern: SELECT existing `(uuid_sucursal, uuid_tipo_vehiculo, source_event_uuid)` first; if absent, lock + max + 1 + return.

- **Pros**: Pure-Python helper, easy to test (`pytest-asyncio` with seeded counter row). No DB trigger surface to maintain. Aligns with the existing pattern from `assign_consecutivo` for `factura_electronica` (T-PR9-002).
- **Cons**: Requires a NEW `[A]` table `prod.ingreso_consecutivo_contador` carrying `(uuid, uuid_sucursal, uuid_tipo_vehiculo, ultimo_consecutivo, last_event_uuid)`. This is the **51st table** in the model — out-of-scope for `bootstrap-monorepo-foundation` per `AGENTS.md`. Mitigation: it is `[A]` (single INTEGER column updated atomically), so it gets REVOKE + `BEFORE UPDATE OR DELETE` trigger in the SAME migration, per the strict rule (`config.yaml rules.tasks`).
- **Effort**: MEDIUM (migration + helper + tests). Reuses the proven `assign_consecutivo` shape.

### A3 — Inline `MAX+1` in the handler (simpler, no counter table)

```python
next_cons = (await session.execute(text(
    "SELECT COALESCE(MAX(SPLIT_PART(consecutivo, '-', 2)::int), 0) + 1 "
    "FROM prod.ingreso WHERE uuid_sucursal = :u AND uuid_tipo_vehiculo = :t"
), {...})).scalar_one()
```

- **Pros**: Zero schema migration. One-line helper. No new `[A]` table.
- **Cons**: **Race condition between two POSTs concurrent for the same (sucursal, tipo)**. The `[L-E]` table has no UK on `consecutivo`, so two concurrent inserts could mint the same number; the partial UK from G1 would then reject the second one. **Not safe for concurrent kiosko traffic**.
- **Effort**: LOW (no migration; one helper; partial UK in migration).

### Recommendation: **A2 + A3 hybrid**

Use **A2** for the canonical counter (locked, idempotent, parallel kiosko-safe) AND **A3** as a backup calculation if the counter row is missing (degraded mode). The migration adds both: (a) the `[A]` counter table with REVOKE + trigger, (b) the partial UK on `ingreso.consecutivo`. The handler calls `assign_ingreso_consecutivo(session, uuid_sucursal, uuid_tipo_vehiculo, source_event_uuid)` which internally:
1. SELECT existing by `source_event_uuid` (idempotency).
2. If absent, SELECT FOR UPDATE on the counter row.
3. Compute next = `ultimo_consecutivo + 1`.
4. UPDATE counter row (operational UPDATE exception on `[A]`, allowed by the trigger carve-out for `ultimo_consecutivo` + `last_event_uuid` only).
5. Return `f"<TIPO>-{next:06d}-{uuid8}"` where `uuid8 = source_event_uuid.hex[:8]`.

This mirrors `assign_consecutivo` for `factura_electronica` exactly (T-PR9-002 already shipped this pattern; reuse verbatim where possible).

## Open questions for sdd-propose

> Each item below is a question for the orchestrator to ask the user in the `sdd-propose` interactive round, per the user's brief.

1. **`consecutivo` reset semantics** — The user said "monotónico forever (sin reset)". Confirmed: **NO reset on year change, NO reset on tipo change**. The counter only increments within `(uuid_sucursal, uuid_tipo_vehiculo)`. If the operator branch reconfigures cupos or the admin closes a tipo, the existing counters are preserved. **Confirm this matches the user's intent.**
2. **`<uuid8>` source** — Format `BICI-000001-<uuid8>`. Assumed: `uuid8 = source_event_uuid.hex[:8]` (first 8 hex chars of `Ingreso.uuid` which is `gen_random_uuid()` per `IdMixin`). **Confirm** — alternative would be `request_id` or `actor_uuid`, but the ingreso uuid is the most stable identifier and already flows in the response.
3. **Front-end TipoSelect source** — Two options:
   - **(a)** NEW hook `useTiposVehiculoSinPlaca()` returning only `bicicleta` + `patineta` from the catalog (filtered client-side from `useTiposVehiculo()`).
   - **(b)** Reuse `useTiposVehiculo()` and filter in the `<TipoSelect>` component itself.
   - **(a)** is cleaner (single responsibility, easy to test), **(b)** is fewer files. **Recommend (a)** — align with `useSesionActiva` precedent (F3.3 = single hook per concern).
4. **Two-buttons-vs-toggle layout** — The user said "two buttons separated". Three sub-options for layout:
   - **(i)** Two `<Button>` side-by-side at the top of `Principal.tsx` (`Con placa` | `Sin placa`), each opens a separate panel.
   - **(ii)** Two `<Tabs>` (shadcn) with the same content split.
   - **(iii)** Two `<Card>` stacked vertically.
   - **(i)** is the most direct read of "two buttons separated"; **(ii)** adds a tab strip that is overkill for a binary choice; **(iii)** wastes vertical space. **Recommend (i)**.
5. **`<IngresoSinPlacaPanel>` file location** — Where does the new component live?
   - **(a)** `features/operacion/components/IngresoSinPlacaPanel.tsx` (peer of `PlacaInput.tsx`).
   - **(b)** `features/operacion/components/IngresoSinPlacaForm.tsx` (peer of the form shape, not the panel).
   - **(a)** aligns with the existing `IngresoPanel`/`PlacaInput` naming; **(b)** is more "form-centric". **Recommend (a)**.
6. **Idempotency-Key migration risk** — Adding `consecutivo` to the canonical payload will invalidate the SHA-256 digest for any in-flight retry with `placa` populated. In practice, no operator retry takes more than 5 seconds; the migration risk is negligible. **Confirm acceptable** OR we add a backward-compat shim that ignores `consecutivo` from the canonical JSON for the first 7 days (rejected — adds complexity for a 5-second window).
7. **Should the operator pick the tipo BEFORE or AFTER clicking "Sin placa"?** — UX micro-decision. Two options:
   - **(i)** Operator clicks `Sin placa` → modal opens with the `<TipoSelect>` (Bicicleta/Patineta) + a `Generar ingreso` button. Single click → modal → fill → submit.
   - **(ii)** Operator clicks `Sin placa` → expands an inline panel with the `<TipoSelect>` + `Generar ingreso` button. Two clicks → fill → submit.
   - **(i)** is the modal pattern used by `<ForzarIngresoModal>` and `<TiqueteModal>` (consistency); **(ii)** is the inline pattern used by the observaciones textarea. **Recommend (i)** for symmetry.
8. **Cupo agotado UX** — When `cupo_agotado=True` for bici/patineta (20+ bicicletas ya en el parqueadero), the operator can still "forzar" with motivo ≥10 chars prefijo `[FORZADO: ...]`. The existing `<ForzarIngresoModal>` (Principal.tsx:147-172, IngresoPanel.tsx:202-227) handles the forzado flow for placa-driven ingresos. **Confirm**: the same modal can be reused for no-placa (it does not display the placa, only the motivo textarea). If yes, no new modal needed.
9. **Tiquete print label** — For bici/patineta, should the print buffer say `Identificación:` (DEC-SUC analogue) or `Consecutivo:` (literal technical name)? The user said `BICI-000001-<uuid8>` is the "identificación". **Recommend `Identificación:`** (operator-facing label; the underlying field name stays `consecutivo`).
10. **Sync replication** — The cloud currently receives `ingreso` rows via the `emit_sync_back_events_loop` stub (PR9b no-op). When sync ships, will the `consecutivo` column flow through? **Yes** — it is part of the row; the cloud does not assign a new number (cloud validates the branch-assigned value per AGENTS.md R3 and DEC-SUC-28). **No additional sync work needed.**

## Risks

| ID | Severity | Risk | Mitigation |
|---|---|---|---|
| **R1** | HIGH | **Race condition on `consecutivo` between two concurrent kiosko POSTs** for the same `(sucursal, tipo)` | Use Approach A2: `assign_ingreso_consecutivo` with `SELECT ... FOR UPDATE` on the counter row (per `assign_consecutivo` precedent, T-PR9-002). Add partial UK `(uuid_sucursal, uuid_tipo_vehiculo, consecutivo) WHERE consecutivo IS NOT NULL` as defense in depth. |
| **R2** | MED | **Existing carro/moto ingresos get `consecutivo=NULL`** (they are inserted without the field) | Schema column is nullable; existing rows keep `consecutivo=NULL`. The UK is partial (only on NOT NULL). Carro/moto are unaffected. Frontend `PostIngresoResponseSchema` declares `consecutivo: z.string().nullable()` so the cliente reads `null` for legacy rows. |
| **R3** | LOW | **DIAN `consecutivo` confusion** — `prod.factura_electronica.consecutivo` (DIAN invoice numbering, branch-assigned, range-gated by `resolucion_facturacion`) is unrelated to this `prod.ingreso.consecutivo` (parking identifier for bici/patineta) | Naming is intentional but collision-risk for future readers. Add a **DEDICATED DECISION** to the proposal: `DEC-INCOME-NN: ingreso.consecutivo is the parking-lot identifier for vehicles without placa (bici/patineta); it is NOT a DIAN invoice number. Both live on different tables with different UKs and different formats.` |
| **R4** | LOW | **Frontend Zod discriminated union breaks existing client** — `placa_presente: z.literal(true)` discriminator is a wire-shape change | Test the union's `.parse()` against the existing 6 F6.1 payloads (operacion.json regression suite). Document as wire-shape-version bump: v6.1.1 → v6.2.0 (semver minor because additive). |
| **R5** | MED | **`<IngresoSinPlacaPanel>` UX divergence from `<PlacaInput>`** — operators are trained to type a placa + press Enter; the new flow breaks that muscle memory | Document the new flow in the operador onboarding runbook; add a tooltip on the `Sin placa` button explaining "Vehículos sin placa (bicicletas, patinetas)"; keep the `Con placa` button visually dominant. |
| **R6** | MED | **Counter table `ingreso_consecutivo_contador` is the 51st table** — out of `bootstrap-monorepo-foundation` scope per AGENTS.md | Same precedent as `idempotency_keys` (50th, mitigated by PR7). Mitigation: `[A]` table gets REVOKE + trigger + `fecha_retencion_hasta` (5-year DIAN retention, even though it's operational) in the same migration per `config.yaml rules.tasks`. |
| **R7** | LOW | **AST walk `test_no_write_after_insert.py` rejects UPDATE/DELETE** — the new `consecutivo` column must never appear in `new_attrs` for an UPDATE | The column is INSERT-only; the handler calls `payload.model_dump(exclude_none=True)` and adds `consecutivo` to `new_attrs` BEFORE the INSERT. No UPDATE path exists. Verified mentally — the test scans `repo/ingreso.py::crear_ingreso_evento`, not the handler. |
| **R8** | LOW | **`Principal.tsx` and `IngresoPanel.tsx` are duplicate-shaped** — both need the dual-flow update | Either update both in the same PR (atomic, larger diff) or factor a `<TipoIngresoToggle>` shared component. **Recommend same PR** for atomicity; the changes are small (~10 LOC per file). |
| **R9** | LOW | **`sync_queue` recursion** — the new counter table is local-only (no `branch_to_cloud` propagation) but if the sync trigger is misconfigured, it could enqueue itself | The migration must include `WHEN (TG_TABLE_NAME <> 'ingreso_consecutivo_contador')` in the sync trigger (per AGENTS.md precedent for `sync_queue` exclusion). |
| **R10** | LOW | **`mv_ocupacion_diaria` REFRESH** — a no-placa INSERT increments `activos` correctly but the MV only refreshes every 10s (DEC-SUC-11); operator may see stale "cupo disponible" momentarily | Already-accepted latency per DEC-SUC-11; the V2 `cupo_agotado` validation reads the same MV, so the race is symmetric. No new mitigation needed. |
| **R11** | LOW | **Idempotency-Key migration** — old F6.1 payload (with `placa` string) hashes differently from the new discriminated-union payload | Operator retries within ~5s window are acceptable; document as known migration cost. |

## Dependencies

### Files to create (5 + tests)

| Path | LOC est. | Purpose |
|---|---:|---|
| `backend/packages/parkos_core/migrations/versions/0042_add_ingreso_consecutivo.py` | ~80 | ADD COLUMN `consecutivo VARCHAR(20) NULL` to `prod.ingreso`; partial UK `(uuid_sucursal, uuid_tipo_vehiculo, consecutivo) WHERE consecutivo IS NOT NULL`; CREATE `[A]` table `prod.ingreso_consecutivo_contador` (uuid, uuid_sucursal, uuid_tipo_vehiculo, ultimo_consecutivo, last_event_uuid, sync_status, created_at, created_by) + REVOKE UPDATE/DELETE on `rol_app` + `BEFORE UPDATE OR DELETE` trigger (carve-out for `ultimo_consecutivo` + `last_event_uuid` only) + sync-trigger exclusion |
| `backend/packages/parkos_core/src/parkos_core/repo/ingreso_consecutivo.py` | ~150 | `assign_ingreso_consecutivo(session, uuid_sucursal, uuid_tipo_vehiculo, source_event_uuid)` — SELECT existing + SELECT FOR UPDATE on counter row + max+1 + UPDATE + return formatted string `f"{TIPO}-{n:06d}-{uuid8}"` (mirrors `assign_consecutivo` from `repo/resolucion_facturacion.py:47-183` verbatim pattern) |
| `apps/electron-sucursal/src/features/operacion/components/IngresoSinPlacaPanel.tsx` | ~80 | RHF + Zod discriminated-union form; `<TipoSelect>` (filtered to bici/patineta) + `Generar ingreso` button + `observaciones` textarea + error display |
| `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts` (modify) | ~30 | Refactor `PostIngresoPayloadSchema` to discriminated union `z.discriminatedUnion('placa_presente', [...])`. Add `consecutivo: z.string().nullable()` to `PostIngresoResponseSchema`. |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculoSinPlaca.ts` | ~50 | NEW hook — SWR + fallback; returns only `bicicleta` + `patineta`. Reuses `useTiposVehiculo` dedup/dedupe pattern. |

### Files to modify (8)

| Path | Change |
|---|---|
| `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py` | Add `consecutivo: Mapped[str \| None] = mapped_column(String(20), nullable=True)` after `placa`. Pure additive. |
| `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` | Add `consecutivo: str \| None = None` to `IngresoRead` (line ~72), `IngresoCreate` (line ~104), `IngresoCreateForzado` (line ~300). Add a discriminated-union sub-schema for the no-placa payload variant. |
| `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` | Step 8: skip `existe_ingreso_activo` when `payload.placa is None`. Step 9: call `assign_ingreso_consecutivo(...)` when `payload.uuid_tipo_vehiculo` corresponds to bici/patineta (i.e. `payload.placa is None`); add `consecutivo` to `new_attrs`. Step 11: include `consecutivo` in the response. |
| `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` | Re-export `assign_ingreso_consecutivo` from the new module (per R-A5 precedent). |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | `buildEntradaBody`: when `payload.placa === null && payload.consecutivo`, render `Identificación: ${payload.consecutivo}` instead of `Placa: ${payload.placa}`. |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | Refactor `entradaPayloadSchema` to a discriminated union: `entradaPayloadSchemaPlaca` (current shape, REQUIRED `placa`) + `entradaPayloadSchemaConsecutivo` (REQUIRED `consecutivo`, `placa: null`). Export a top-level `entradaPayloadSchema = z.union([...])` so `escposBuilder.build('entrada', payload)` accepts both. |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | Mirror the `Identificación:` vs `Placa:` line in the HTML render path. |
| `apps/electron-sucursal/src/features/operacion/pages/Principal.tsx` | Add the two-button layout at line ~268. Render `<PlacaInput>` (current) OR `<IngresoSinPlacaPanel>` based on `useState<boolean>(false)` toggle. The handler flow stays similar — `postIngreso(payload)` is called from either path. |
| `apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx` | Same two-button treatment as Principal. |
| `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx` | Add `consecutivo?: string \| null` to `TiqueteModalProps`. Render `Identificación: {consecutivo}` line when present; keep `Folio: {uuid_ingreso}` always (for the QR and audit trail). |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | +6 i18n keys: `ingreso_sin_placa_cta`, `ingreso_sin_placa_selector_label`, `ingreso_sin_placa_tipo_bicicleta`, `ingreso_sin_placa_tipo_patineta`, `ingreso_sin_placa_generar_boton`, `tiquete_identificacion_label`. |

### Out-of-scope (explicit non-goals)

- **Sync workers** (`job_sync_*`) — no changes; the `consecutivo` flows with the row via the existing `[L-E]` sync path.
- **DIAN dispatcher** — no changes; `ingreso.consecutivo` is unrelated to `factura_electronica.consecutivo`.
- **Salida flow** — no changes; the salida handler reads `ingreso.placa` (or `ingreso.consecutivo` for bici/patineta) — verify during design phase but no handler change expected.
- **BFF (deferred to v2)** — no impact; the renderer talks directly to `api_sucursal` via `parkosFetch`.
- **`[L-E]` audit triggers** (`fn_audit_columns`) — no changes; the column is `created_at`-stamped via the existing flow.

## Test plan

### Backend unit tests (extending existing files)

| File | New test cases |
|---|---|
| `backend/tests/unit/test_operacion_ingresos_validaciones.py` | (T1) bici + cupo disponible → 201 + `consecutivo = "BICI-000001-..."`; (T2) patineta + cupo agotado + forzado motivo válido → 201 + alerta; (T3) bici + cupo agotado + no forzado → 422 `motivo_forzado_requerido`; (T4) bici + `uuid_tipo_vehiculo` inválido → 422 `tipo_vehiculo_invalido`; (T5) bici + `placa` provided (rejected by schema) → 422 schema validation; (T6) concurrent POSTs (10 tasks) for the same `(sucursal, tipo='bicicleta')` → 10 distinct consecutivos (race-condition guard). |
| `backend/tests/unit/test_repo_ingreso_consecutivo.py` (NEW) | (T7) idempotency: same `source_event_uuid` returns the same consecutivo across retries; (T8) counter increments monotonically per `(sucursal, tipo)`; (T9) formatted output matches `<TIPO>-{n:06d}-{uuid8}` for n=1..999; (T10) counter table REVOKE blocks UPDATE from `rol_app` (defense in depth). |
| `backend/tests/unit/test_operacion_ingresos_kd_forzado.py` | Extend to cover bici/patineta forzado (T11) — same motivo ≥10 char logic, but the motivo goes on a no-placa ingreso. |
| `backend/tests/static/test_no_write_after_insert.py` | No change — `consecutivo` is INSERT-only; the AST walk already rejects UPDATE/DELETE in `crear_ingreso_evento`. |

### Backend integration tests (extending)

| File | New test cases |
|---|---|
| `backend/tests/integration/test_ocupacion_view.py` | (T12) no-placa INSERT increments `mv_ocupacion_diaria.activos` for `(sucursal, 'bicicleta')`; (T13) `mv_ocupacion_diaria` does not regress for carro/moto (regression). |

### Frontend unit tests (extending)

| File | New test cases |
|---|---|
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` | (T14) `buildEntradaBuffer` with `{placa: null, consecutivo: 'BICI-000001-3f8a1b2c'}` emits `Identificación: BICI-000001-3f8a1b2c` literal byte sequence; (T15) existing placa-driven case still passes (regression). |
| `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` | (T16) HTML render path emits `<p>Identificación: ...</p>` for the consecutivo variant; (T17) regression for placa. |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/TiqueteModal.test.tsx` (NEW) | (T18) renders `Identificación:` line when `consecutivo` prop is provided; (T19) renders `Folio:` only when `consecutivo` is null. |
| `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.test.ts` (NEW) | (T20) discriminated-union validation accepts both variants; (T21) `placa` + `consecutivo` together is rejected (no mixing). |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculoSinPlaca.test.ts` (NEW) | (T22) returns only bici/patineta (filtered from fallback); (T23) SWR key null-when-no-token (precedent F3.3); (T24) dedupingInterval 5min (precedent F4.1). |

### E2E / smoke (deferred per F.6 sandbox precedent)

- Playwright spec for the no-placa flow — same F.6 caveat as F6.1/F6.2 (no exercisable UI in sandbox). The byte-fixture + unit-test boundary is the verification surface.

## Estimated LOC + PR split proposal

### LOC tally

| Area | LOC est. |
|---|---:|
| Backend migration (`0042_*`) | 80 |
| Backend repo (`ingreso_consecutivo.py` NEW) | 150 |
| Backend ORM + schema + handler (modify) | 90 |
| Backend tests (new + extend) | 280 |
| Frontend discriminated-union schema (modify) | 30 |
| Frontend `IngresoSinPlacaPanel` NEW | 80 |
| Frontend `useTiposVehiculoSinPlaca` NEW + tests | 100 |
| Frontend `Principal.tsx` + `IngresoPanel.tsx` modify | 60 |
| Frontend `TiqueteModal` modify + tests | 60 |
| Frontend `escposBuilder` + `escposTemplates` + `fallbackBrowser` modify | 60 |
| Frontend byte-fixture tests | 120 |
| i18n keys (`operacion.json`) | 5 |
| **TOTAL** | **~1115 LOC** |

### PR split — recommended

The total **1115 LOC** exceeds the 800-LOC single-PR budget per `openspec/config.yaml rules.tasks`. Per the chained-PR work-unit-commits skill:

| PR | Scope | Files | LOC est. | Strategy |
|---|---|---|---:|---|
| **PR-A** | Backend foundation: migration + counter helper + ORM + handler + tests | `0042_*`, `models/L_E/ingreso.py`, `schemas/operacion.py`, `api/v1/operacion.py`, `repo/ingreso_consecutivo.py`, `repo/ingreso.py`, 3 backend tests | **~600 LOC** | Single PR; gitflow to `dev`. |
| **PR-B** | Frontend wiring: API schema + `<IngresoSinPlacaPanel>` + `useTiposVehiculoSinPlaca` + `Principal` + `IngresoPanel` + `TiqueteModal` + i18n + tests | `ingresoApi.ts`, `IngresoSinPlacaPanel.tsx`, `useTiposVehiculoSinPlaca.ts`, `Principal.tsx`, `IngresoPanel.tsx`, `TiqueteModal.tsx`, `operacion.json`, 4 frontend tests | **~455 LOC** | Single PR; gitflow to `dev`. |
| **PR-C** (optional, if PR-B exceeds 400 LOC) | Print layer: `escposBuilder` + `escposTemplates` + `fallbackBrowser` + byte-fixture tests | 3 print files + 2 test files | **~180 LOC** | Chained-PR slice; feature branch out of PR-B's branch. |

**Recommended strategy**: 2 chained PRs (PR-A backend first, then PR-B frontend). PR-B's frontend is dependent on PR-A's response shape (`consecutivo` field on `IngresoRead`), so the dependency is linear. If PR-B's actual diff exceeds 400 LOC during implementation, split into PR-B1 (API + Panel + Hook) and PR-B2 (Print layer + TiqueteModal).

**Conventional Commits**:
- PR-A: `feat(operacion): add ingreso.consecutivo for bici/patineta parking identifier (HU-F4.1-NN)` + `feat(operacion): assign_consecutivo per (sucursal, tipo) with SELECT FOR UPDATE lock` + `test(operacion): 11 new scenarios for no-placa ingresos` (3 commits)
- PR-B: `feat(operacion): discriminated-union IngresoPayload (placa | consecutivo) for bici/patineta` + `feat(catalogos): useTiposVehiculoSinPlaca hook for bici/patineta filter` + `feat(ui): two-button flujo principal (con placa | sin placa)` + `feat(print): tiquete renders Identificación for consecutivo variant` (4 commits)

## Affected areas (summary)

| Area | Impact | Description |
|---|---|---|
| `backend/packages/parkos_core/migrations/versions/0042_add_ingreso_consecutivo.py` | NEW | Migration: column + partial UK + counter table + REVOKE + trigger |
| `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py` | Modified | +1 column `consecutivo` |
| `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` | Modified | +1 column on Read/Create/Forzado; discriminated-union sub-schema |
| `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` | Modified | Step 8 skip when placa=null; Step 9 assign consecutivo; Step 11 expose in response |
| `backend/packages/parkos_core/src/parkos_core/repo/ingreso_consecutivo.py` | NEW | `assign_ingreso_consecutivo` helper |
| `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` | Modified | Re-export helper |
| `backend/tests/unit/test_operacion_ingresos_validaciones.py` | Modified | +6 scenarios |
| `backend/tests/unit/test_repo_ingreso_consecutivo.py` | NEW | +4 unit tests for helper |
| `backend/tests/integration/test_ocupacion_view.py` | Modified | +2 scenarios for MV regression |
| `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts` | Modified | Discriminated union schema |
| `apps/electron-sucursal/src/features/operacion/components/IngresoSinPlacaPanel.tsx` | NEW | No-placa flow UI |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculoSinPlaca.ts` | NEW | Filtered tipos hook |
| `apps/electron-sucursal/src/features/operacion/pages/Principal.tsx` | Modified | Two-button layout |
| `apps/electron-sucursal/src/features/operacion/components/IngresoPanel.tsx` | Modified | Two-button layout |
| `apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx` | Modified | Render `Identificación:` line |
| `apps/electron-sucursal/src/lib/print/escposBuilder.ts` | Modified | Conditional `Identificación:` vs `Placa:` line |
| `apps/electron-sucursal/src/lib/print/escposTemplates.ts` | Modified | Discriminated-union `entradaPayloadSchema` |
| `apps/electron-sucursal/src/lib/print/fallbackBrowser.ts` | Modified | HTML mirror |
| `apps/electron-sucursal/src/renderer/i18n/locales/operacion.json` | Modified | +6 i18n keys |
| `apps/electron-sucursal/src/lib/print/__tests__/escposBuilder.entrada.test.ts` | Modified | +2 byte-fixture scenarios |
| `apps/electron-sucursal/src/lib/print/__tests__/fallbackBrowser.entrada.test.ts` | Modified | +1 HTML test |
| `apps/electron-sucursal/src/features/operacion/components/__tests__/TiqueteModal.test.tsx` | NEW | +2 component tests |
| `apps/electron-sucursal/src/features/operacion/lib/ingresoApi.test.ts` | NEW | +2 schema tests |
| `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculoSinPlaca.test.ts` | NEW | +3 hook tests |

## Architectural decisions cited

- **DEC-SUC-22** — `detectar_tipo_vehiculo` strict regex (no tolerance). **Unchanged**: no-placa flow does not call this helper; it uses `uuid_tipo_vehiculo` from the payload.
- **DEC-SUC-21** — `tipo_entrada` is DERIVED from `uuid_subscripcion_cliente IS NOT NULL` (mensualidad) or NULL (rotación). **Unchanged**: no-placa ingresos are always rotación; the handler computes `tipo_entrada = "ROTACION"` at Step 10.
- **DEC-SUC-26** — QR + logo on tiquetes. **Unchanged**: the QR embeds `parkos://ingreso/<uuid>?placa=<placa>` per the F6.2 builder; for no-placa ingresos, the URL uses `?consecutivo=<consecutivo>` instead.
- **DEC-SUC-27** — Auto-print on 201. **Unchanged**: the no-placa flow reuses `bridge.imprimir(payload)`; the print payload includes `consecutivo` so the tiquete identifies the vehicle.
- **DEC-SUC-11** — Ocupación via MV with 10s polling. **Unchanged**: no-placa ingresos count correctly because the MV groups by `(uuid_sucursal, uuid_tipo_vehiculo)`.
- **A-04** — `observaciones` with `[FORZADO: ...]` prefix. **Unchanged**: the no-placa flow reuses `<ForzarIngresoModal>` which does not depend on placa.
- **A-05** — `log_transaccional` audit. **Unchanged**: the `consecutivo` flows in `datos_nuevos` automatically via `record_event`'s canonical payload (event.py:115-137).
- **DEC-INCOME-NN (NEW)** — *to ratify in proposal:* `ingreso.consecutivo` is the parking-lot identifier for vehicles without placa (bici/patineta); it is NOT a DIAN invoice number. Both live on different tables with different UKs and different formats. Bici/patineta use `BICI-NNNNNN-<uuid8>` / `PATIN-NNNNNN-<uuid8>` (no range bounds, no DIAN resolution, monotonic forever per `(uuid_sucursal, uuid_tipo_vehiculo)`).

## Ready for proposal

**YES** — all 10 concrete questions in the orchestrator's brief are addressed in §Open questions above. The orchestrator should run `sdd-propose ingreso-multi-tipo-consecutivo` to lock the 10 questions and write `openspec/changes/ingreso-multi-tipo-consecutivo/proposal.md`.

The proposal phase will:
1. Confirm or override the 10 open questions.
2. Pick between Approach A2 (counter table) and A3 (MAX+1) — recommend A2.
3. Lock the PR split (PR-A backend, PR-B frontend).
4. Reference this exploration as the input artifact.

`status: ready-for-sdd-propose`

---

## Relevant files

- `E:\easypunto_parkos\modelo_datos_er.mmd` (lines 577-596 — canonical `[L-E] ingreso` shape, no `consecutivo` column today)
- `E:\easypunto_parkos\backend\packages\parkos_core\src\parkos_core\api\v1\operacion.py` (lines 145-316 — `create_ingreso` 11-step V-chain)
- `E:\easypunto_parkos\backend\packages\parkos_core\src\parkos_core\repo\placa.py` (lines 47-87 — `detectar_tipo_vehiculo` already None-safe)
- `E:\easypunto_parkos\backend\packages\parkos_core\src\parkos_core\repo\ocupacion.py` (lines 138-214 — `validar_cupo_disponible` already tipo-agnostic)
- `E:\easypunto_parkos\backend\packages\parkos_core\src\parkos_core\repo\ingreso.py` (lines 57-127 — `existe_ingreso_activo`; lines 174-194 — `crear_ingreso_evento`)
- `E:\easypunto_parkos\backend\packages\parkos_core\src\parkos_core\repo\resolucion_facturacion.py` (lines 47-183 — `assign_consecutivo` precedent for SELECT FOR UPDATE pattern)
- `E:\easypunto_parkos\backend\packages\parkos_core\src\parkos_core\models\L_E\ingreso.py` (60 lines — ORM model, `[L-E]` insert-only)
- `E:\easypunto_parkos\backend\packages\parkos_core\src\parkos_core\schemas\operacion.py` (lines 75-104, 280-316 — IngresoCreate/Forzado; lines 50-72 — IngresoRead)
- `E:\easypunto_parkos\backend\packages\parkos_core\migrations\versions\0037_add_uuid_subscripcion_cliente_to_facturas.py` (precedent for add-column migration)
- `E:\easypunto_parkos\backend\scripts\seed_tipos_y_cupos_sucursal.py` (lines 1-205 — just-merged catalog + cupos seed)
- `E:\easypunto_parkos\apps\electron-sucursal\src\features\operacion\pages\Principal.tsx` (403 lines — page orchestrator, needs two-button layout)
- `E:\easypunto_parkos\apps\electron-sucursal\src\features\operacion\components\IngresoPanel.tsx` (389 lines — duplicate of Principal for dashboard-hub)
- `E:\easypunto_parkos\apps\electron-sucursal\src\features\operacion\components\PlacaInput.tsx` (188 lines — existing placa flow)
- `E:\easypunto_parkos\apps\electron-sucursal\src\features\operacion\components\TiqueteModal.tsx` (163 lines — needs `consecutivo` prop)
- `E:\easypunto_parkos\apps\electron-sucursal\src\features\operacion\lib\ingresoApi.ts` (111 lines — Zod schemas)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\escposBuilder.ts` (line 205 — `Placa: ${payload.placa}` line)
- `E:\easypunto_parkos\apps\electron-sucursal\src\lib\print\escposTemplates.ts` (lines 142-156, 215 — placaSchema and entradaPayloadSchema)
- `E:\easypunto_parkos\apps\electron-sucursal\src\renderer\i18n\locales\operacion.json` (i18n namespace)
- `E:\easypunto_parkos\backend\tests\static\test_no_write_after_insert.py` (AST walk that locks `consecutivo` to INSERT-time only)
- `E:\easypunto_parkos\AGENTS.md` §1-3 (audit-first, bi-temporal, C/Q/U-no-D — the invariants this change must honor)
- `E:\easypunto_parkos\openspec\config.yaml` `rules.tasks` (800 LOC single-PR budget, REVOKE/trigger in same migration for `[A]` tables)
- `E:\easypunto_parkos\openspec\changes\archive\2026-09-16-hu-f4-1-deteccion-tipo-vehiculo\exploration.md` (precedent for F4.x exploration format)
- `E:\easypunto_parkos\openspec\changes\archive\2026-09-17-fase-7-3-tiquetes-salida\proposal.md` (precedent for chained-PR split + byte-fixture testing)
- `E:\easypunto_parkos\openspec\changes\archive\create-49-table-apis\exploration.md` (precedent for the master exploration format this file mirrors)
