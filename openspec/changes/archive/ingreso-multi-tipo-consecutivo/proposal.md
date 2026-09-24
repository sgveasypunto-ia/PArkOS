# Proposal — `ingreso-multi-tipo-consecutivo`: ingresos sin placa (bici / patineta) con consecutivo monotónico

> **Change**: `ingreso-multi-tipo-consecutivo` · **Folder**: `openspec/changes/ingreso-multi-tipo-consecutivo/`
> **Phase**: propose (sdd-propose) · **Status**: ready for `sdd-spec` + `sdd-design` (paralelo)
> **Fase**: 4 (Catálogos y ocupación en vivo) — continuación de HU-F4.1 + F6.1 + F7.3 (precedentes archivados 2026-09-16 / 17 / 19)
> **Working dir**: `E:/easypunto_parkos` · **Plataforma**: Windows PowerShell 5.1
> **Branch origen**: `dev` (commit `281bb66` ya mergeado — seed catálogo multi-tipo) · **PR target**: `origin/dev` (gitflow; chained PRs PR-A + PR-B)
> **Inputs**: `exploration.md` (278 líneas, 12 gaps G1..G12, 3 approaches A1..A3, 10 open questions, 11 risks R1..R11) + `modelo_datos_er.mmd` (49→51 tablas canónicas) + Engram `#1995` `sdd/ingreso-multi-tipo-consecutivo/explore`
> **Language**: español neutro profesional (artefacto de decisión de producto)
> **Conventional commits**: `feat(operacion)` / `feat(catalogos)` / `feat(print)` / `test(operacion)` — sin Co-authored-by

---

## 1. Intent (1 párrafo)

Habilitar el camino de `POST /operacion/ingresos` para vehículos sin placa — `bicicleta` y `patineta` — generando un `consecutivo` monotónico por `(uuid_sucursal, uuid_tipo_vehiculo)` con formato `<TIPO>-NNNNNN-<uuid8>` (ej: `BICI-000001-3f8a1b2c`) que sirve como **identificación visible para el cliente y el operador** (sustituye a la placa en el tiquete y en la pantalla), mantiene la validación de cupo por tipo via el MV `mv_ocupacion_diaria` ya seeded, y respeta todos los invariantes arquitectónicos (audit-first, bi-temporal, C/Q/U-no-D, multi-tenant, hash chain, sync eventual). El operador selecciona explícitamente entre dos botones separados en `Principal.tsx` y `IngresoPanel.tsx` — **NO toggle, NO inferencia** — preservando la regla de negocio BR2 de CU-01 (autodetección por regex es la ÚNICA fuente válida; el flujo sin placa es ortogonal y cliente-supplied).

---

## 2. Background

**Estado actual — solo `carro` y `moto` con regex**. `POST /operacion/ingresos` (HU-F1.6 archivado) acepta solo placas con formato `^[A-Z]{3}[0-9]{3}$` (Auto) o `^[A-Z]{3}[0-9]{2}[A-Z]$` (Moto). El helper `detectar_tipo_vehiculo()` ya es **None-safe** (`backend/packages/parkos_core/src/parkos_core/repo/placa.py:73`) y `validar_cupo_disponible()` es tipo-agnóstico (`repo/ocupacion.py:138-214`) — la cadena V1+V2 ya está lista para procesar bici/patineta, pero no hay camino de entrada. La columna `consecutivo` **no existe** en `prod.ingreso` (canon ER 4NF, `modelo_datos_er.mmd:577-596` — confirmado en `exploration.md:14`).

**Trigger — el seed ya mergeó a `dev`**. Commit `281bb66 chore(backend): seed tipos_vehiculo + cupos for D2049f2` (2026-09-22, ya en `dev`) sembró las 4 tipos (`carro`/`moto`/`bicicleta`/`patineta` — strings lowercase per canon) en `prod.tipos_vehiculo` y `cantidad_vehiculos_sucursal` (cupos 50/30/20/10 para la sucursal de prueba D2049f2). **La BD está lista pero el flujo de ingreso no la aprovecha.** F4.1 (`hu-f4-1-deteccion-tipo-vehiculo` archivado 2026-09-16) sentó las bases cliente (`detectarTipoVehiculo()` + `useTiposVehiculo()`); este cambio cierra el lazo.

**Valor para el operador y el cliente**. Hoy, una persona que llega al parqueadero con bicicleta o patineta (cliente legítimo del negocio según el CU) **no puede ingresar** — el operador lo rechaza o lo deja entrar sin trazabilidad (ingreso informal). El flag `cantidad_vehiculos_sucursal.cantidad = 20` para bicicleta ya está sembrado pero no se consume: el operador pierde cupo controlado, el cliente pierde identificación persistente (hoy no hay nada que mostrarle en el tiquete), y el admin pierde auditoría DIAN. Este cambio entrega la identificación visible y el control de cupo que el negocio necesita para operar con vehículos sin placa.

**Riesgo de NO hacerlo**. Ingresos informales → sin trazabilidad DIAN → sin auditoría → sin cupo controlado → violación directa de REQ-OPS-133 (`mv_ocupacion_diaria` MUST exist + cupos enforced) y de las premisas CU-01 (cliente legítimo del parqueadero). Además, el seed de catálogo mergeado quedaría **muerto** — trabajo sembrado pero no consumido por el flujo principal.

**Trigger técnico — el catálogo y cupos ya están sembrados, la pieza faltante es solo el handler + UI + persistencia**. Gaps G1..G12 del exploration.md mapean los 12 huecos exactos: columna faltante en ORM, schema sin `consecutivo`, V8 (existe_ingreso_activo) que buscaría por `placa=""` siempre vacío, escposBuilder que hardcodea `Placa:`, Zod frontend que requiere `placa`, Principal.tsx sin entry point no-placa. Cada uno tiene un camino de resolución concreto (ver §3 y §4).

---

## 3. Scope

### 3.1 In Scope (~1115 LOC → 2 chained PRs)

**Backend (PR-A, ~600 LOC)**:
- **Migración `0042_add_ingreso_consecutivo.py`** (~80 LOC). ADD COLUMN `consecutivo VARCHAR(20) NULL` a `prod.ingreso` (nullable para backward compat; filas carro/moto existentes quedan `consecutivo=NULL`). UK parcial `(uuid_sucursal, uuid_tipo_vehiculo, consecutivo) WHERE consecutivo IS NOT NULL` — defense in depth sobre R1 race condition. **CREATE nueva tabla `[A]` `prod.ingreso_consecutivo_contador`** (la **51ª tabla** del modelo, fuera del scope `bootstrap-monorepo-foundation` — sigue el precedent de `idempotency_keys`, mitigada igual: REVOKE UPDATE/DELETE + `BEFORE UPDATE OR DELETE` trigger en la **misma** migración, per `config.yaml rules.tasks`). Schema: `uuid, uuid_sucursal, uuid_tipo_vehiculo, ultimo_consecutivo INT, last_event_uuid UUID, sync_status, created_at, created_by`. Trigger con carve-out explícito para `ultimo_consecutivo` + `last_event_uuid` solamente. Sync-trigger exclusion (`WHEN TG_TABLE_NAME <> 'ingreso_consecutivo_contador'`) para evitar recursion per R9. Pre-flight `alembic upgrade --sql` antes de aplicar (per `config.yaml rules.tasks`).
- **`backend/packages/parkos_core/src/parkos_core/repo/ingreso_consecutivo.py`** (~150 LOC, NEW). Helper `assign_ingreso_consecutivo(session, uuid_sucursal, uuid_tipo_vehiculo, source_event_uuid) -> str`. Replica verbatim el patrón de `repo/resolucion_facturacion.py::assign_consecutivo:47-183`: (1) SELECT existing por `source_event_uuid` (idempotency); (2) SELECT FOR UPDATE sobre counter row; (3) `next = ultimo_consecutivo + 1`; (4) UPDATE counter row; (5) return `f"{TIPO}-{next:06d}-{source_event_uuid.hex[:8]}"`. TIPO viene del catálogo (`TiposVehiculo.tipo.upper()`).
- **ORM + schemas + handler modify** (~90 LOC). `models/L_E/ingreso.py` +1 columna `consecutivo`. `schemas/operacion.py` +1 campo en `IngresoRead`/`IngresoCreate`/`IngresoCreateForzado` (todos `str | None = None`) + sub-schema discriminated-union para no-placa variant. `api/v1/operacion.py`: Step 8 skip `existe_ingreso_activo` cuando `payload.placa is None`; Step 9 llamar `assign_ingreso_consecutivo(...)` cuando `payload.placa is None` y agregar `consecutivo` a `new_attrs` ANTES del INSERT (preserva AST lock R7); Step 11 incluir `consecutivo` en la response.
- **Tests backend** (~280 LOC). 6 nuevos scenarios en `test_operacion_ingresos_validaciones.py` (T1..T6, ver §5). 4 nuevos unit tests en `test_repo_ingreso_consecutivo.py` (T7..T10 — idempotency, monotonic, formato, REVOKE bloquea UPDATE desde `rol_app`). 2 nuevos scenarios en `test_ocupacion_view.py` (T12..T13, MV cuenta no-placa INSERT).

**Frontend (PR-B, ~455 LOC)**:
- **`apps/electron-sucursal/src/features/operacion/components/IngresoSinPlacaPanel.tsx`** (~80 LOC, NEW). RHF + Zod form con `<TipoSelect>` (filtrado a bici/patineta via `useTiposVehiculoSinPlaca()`) + botón "Generar ingreso" + textarea `observaciones` + display de error. Replica patrón `<PlacaInput>` (F6.1 archivado).
- **`apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculoSinPlaca.ts`** (~50 LOC, NEW). SWR + fallback, filtra el resultado de `useTiposVehiculo()` para retornar solo `bicicleta` + `patineta`. Reutiliza `dedupingInterval: 5min` (F4.1 precedent).
- **`apps/electron-sucursal/src/features/operacion/lib/ingresoApi.ts`** (~30 LOC, MODIFY). Refactor `PostIngresoPayloadSchema` a `z.discriminatedUnion('placa_presente', [...])`: variante 1 `{placa_presente: z.literal(true), placa: placaRegex, ...}` + variante 2 `{placa_presente: z.literal(false), uuid_tipo_vehiculo: uuidSchema, consecutivo: stringNonEmpty, ...}`. **No mezclar** — schema rechaza `placa + consecutivo` juntos. `PostIngresoResponseSchema` agrega `consecutivo: z.string().nullable()`.
- **`apps/electron-sucursal/src/features/operacion/pages/Principal.tsx` + `IngresoPanel.tsx`** (~60 LOC, MODIFY ambos). Layout de dos botones side-by-side (`Con placa` | `Sin placa`) en la parte superior de cada página. Atomic dependency — se actualizan en el mismo PR (R8 mitigated: changes pequeños, ~10 LOC cada uno, atomicity > factoring shared component ahora).
- **`apps/electron-sucursal/src/lib/print/escposBuilder.ts` + `escposTemplates.ts` + `fallbackBrowser.ts`** (~60 LOC, MODIFY). `buildEntradaBody` discrimina: si `payload.placa === null && payload.consecutivo` → `Identificación: ${payload.consecutivo}`; else → `Placa: ${payload.placa}` (F5.2 precedent). Refactor `entradaPayloadSchema` a discriminated union `entradaPayloadSchemaPlaca | entradaPayloadSchemaConsecutivo` exportado como `z.union([...])`.
- **`apps/electron-sucursal/src/features/operacion/components/TiqueteModal.tsx`** (~30 LOC, MODIFY). `TiqueteModalProps` agrega `consecutivo?: string | null`. Render condicional: si presente → `Identificación: {consecutivo}`; else → sigue el flujo actual. `Folio: {uuid_ingreso}` se mantiene siempre (para QR + audit trail, DEC-SUC-26).
- **`apps/electron-sucursal/src/renderer/i18n/locales/operacion.json`** (+6 keys, ~5 LOC). Namespace pre-existente. Keys: `ingreso_sin_placa_cta`, `ingreso_sin_placa_selector_label`, `ingreso_sin_placa_tipo_bicicleta`, `ingreso_sin_placa_tipo_patineta`, `ingreso_sin_placa_generar_boton`, `tiquete_identificacion_label`.
- **Tests frontend** (~120 LOC). 2 nuevos en `escposBuilder.entrada.test.ts` (T14..T15 — byte-fixture `Identificación: BICI-000001-3f8a1b2c` + regression placa). 1 nuevo en `fallbackBrowser.entrada.test.ts` (T16). 2 nuevos en `TiqueteModal.test.tsx` (NEW — T18..T19). 2 nuevos en `ingresoApi.test.ts` (NEW — T20..T21). 3 nuevos en `useTiposVehiculoSinPlaca.test.ts` (NEW — T22..T24).

**Conventional commits** (5 commits totales):
- **C1** (PR-A): `feat(operacion): add ingreso.consecutivo column + counter table + assign helper (HU-F4.1-NN)`
- **C2** (PR-A): `feat(operacion): assign_consecutivo per (sucursal, tipo) with SELECT FOR UPDATE lock`
- **C3** (PR-A): `test(operacion): 12 new scenarios for no-placa ingresos + helper + MV regression`
- **C4** (PR-B): `feat(operacion): discriminated-union IngresoPayload (placa | consecutivo) for bici/patineta`
- **C5** (PR-B): `feat(catalogos): useTiposVehiculoSinPlaca hook + two-button flujo principal + Identificación render`

Tests incluidos con código (work-unit-commits hard rule).

### 3.2 Out of Scope (explícitamente deferido)

- **Cambios en `cloud-edge-sync-architecture`**. El sync stub actual maneja la nueva columna automáticamente porque fluye con la fila via `record_event` (`event.py:115-137`). Cloud preserva el valor branch-assigned verbatim (R3 mitigated — no se asigna cloud-side). Sin trabajo adicional.
- **UI admin para gestionar resoluciones de facturación DIAN**. El `consecutivo` de ingreso **NO es DIAN** — es identificador interno del operador. Vive en tabla distinta con UK distinto y formato distinto. Naming explícito en §4 DEC-INCOME-01.
- **Auto-renew / auto-cancel / reset de consecutivos**. Monotónico forever por ahora (Q1 del exploration — default NO reset). Reset por administrador branch rearmado es follow-up.
- **Hash chain changes**. La nueva columna entra automáticamente en `log_transaccional.datos_nuevos` via `record_event`'s canonical payload. Sin manejo explícito.
- **Cambios en salidas / reimpresión / arqueo**. El `consecutivo` se persiste en el ingreso; las salidas lo leen via JOIN sin cambios al handler (verify en design phase).
- **Cambios en `mv_ocupacion_diaria`**. El MV ya cuenta por `(uuid_sucursal, uuid_tipo_vehiculo)` — no-placa INSERTs cuentan correctamente. Solo agregar test de regresión.
- **Backend cambios en sync workers** (`job_sync_*`). El sync pipeline stub (PR9b no-op) recibe la nueva fila completa. Sin trabajo.
- **BFF (deferred to v2)**. El renderer habla directo a `api_sucursal` via `parkosFetch`.
- **Selector manual de tipo en flujo con placa**. BR2 explícito: autodetección por regex es la ÚNICA fuente válida. No se rompe ese invariante.

---

## 4. Approach

**Estrategia técnica: hybrid Approach A2 + partial UK defense in depth**. Se eligió **A2 (helper app-side con `SELECT ... FOR UPDATE`)** sobre A1 (trigger DB) y A3 (MAX+1 inline) por tres razones: (a) reuso verbatim del patrón probado en `repo/resolucion_facturacion.py::assign_consecutivo:47-183` (T-PR9-002 ya shipped este patrón para `factura_electronica`); (b) testabilidad pura en Python sin `pg_dsn` (pytest-asyncio con seed row); (c) coherencia con la disciplina existente de DB-level (los triggers existentes viven en `[V]` para `vigente_desde`, no en `[L-E]` para business values). **A3 (race condition) se descarta explícitamente** — kiosko desatendido genera POSTs concurrentes legítimos, MAX+1 inline permite colisiones. **A2 + UK parcial** da defensa en profundidad: el helper bloquea con `FOR UPDATE` (canonical) y el UK parcial `WHERE consecutivo IS NOT NULL` rechaza a nivel DB si el helper falla (defense in depth).

**Backend (PR-A) — 5 sub-tareas en orden estricto**. T1: migración `0042_*` con columna + UK parcial + counter table + REVOKE + trigger + sync exclusion (pre-flight `alembic upgrade --sql`); T2: ORM `consecutivo` column; T3: schema `IngresoRead/Create/Forzado` + discriminated-union sub-schema; T4: helper `assign_ingreso_consecutivo`; T5: handler integration (Step 8 skip, Step 9 assign, Step 11 expose). Tests incluidos con cada sub-tarea (TDD strict per `config.yaml`). PR mergea a `dev` con pre-flight check + REVOKE/trigger verifier (entrypoint pattern).

**Frontend (PR-B) — 6 sub-tareas en orden estricto**. T1: discriminated-union Zod schema en `ingresoApi.ts`; T2: `useTiposVehiculoSinPlaca` hook + tests; T3: `<IngresoSinPlacaPanel>` component + tests; T4: dos-botones layout en `Principal.tsx` + `IngresoPanel.tsx`; T5: `escposBuilder` + `escposTemplates` + `fallbackBrowser` discriminated union + byte-fixture tests; T6: `<TiqueteModal>` `consecutivo` prop + tests + i18n keys. PR-B depende linealmente de PR-A merged (response shape con `consecutivo`). Si PR-B excede 400 LOC en implementación, split en PR-B1 (API + Panel + Hook) + PR-B2 (Print layer + TiqueteModal).

**Justificación del split (PR-A → PR-B)**. Backend y frontend son independientes en compilación, pero PR-B envía un payload que PR-A debe aceptar — si se invierte el orden, el cliente envía un schema que el backend rechaza. Orden PR-A → PR-B evita ese "frontend-broken-until-backend-merges" window. Estrategia de chain: `gitflow` — cada PR mergea a `dev` con branch independiente (no feature-branch-chain para PR-A y PR-B porque la dependencia es lineal y `dev` es el integrator canónico).

**DEC-INCOME-01 (NEW) — naming explícito para evitar confusión con DIAN**. `prod.ingreso.consecutivo` (parking-lot identifier for bici/patineta, formato `BICI/PATIN-NNNNNN-<uuid8>`, monotónico forever) vive separado de `prod.factura_electronica.consecutivo` (DIAN invoice numbering, formato numérico corto, range-gated por `resolucion_facturacion`). Distintos tablas, distintos UKs, distintos formatos, distintos lifecycles. El prefijo en el valor visible (`BICI-`/`PATIN-`) hace la distinción operativa inequívoca.

---

## 5. Acceptance Criteria (12 criterios verificables, agrupados por concern)

### (a) Generación de consecutivo

- **AC-1**: `Given` operador autenticado en D2049f2 con bici+patineta configuradas en `cantidad_vehiculos_sucursal`, `When` clickea "Sin placa" → selecciona "Bicicleta" → clickea "Generar ingreso", `Then` backend responde **201** con `consecutivo` formato `BICI-NNNNNN-<uuid8>` donde NNNNNN es `000001` para el primer ingreso y `<uuid8>` son los primeros 8 hex del `uuid_ingreso`.
- **AC-2**: `And` la fila se persiste en `prod.ingreso` con `placa=NULL`, `consecutivo="BICI-000001-3f8a1b2c"` (ejemplo), `uuid_tipo_vehiculo=<uuid bicicleta>`, `vigente=true` por defecto.
- **AC-3**: `And` un segundo ingreso consecutivo (mismo operador, 5 segundos después) genera `consecutivo="BICI-000002-<uuid8>"` — monotónico verified vía SELECT ordenado.
- **AC-4**: `And` 10 POSTs concurrentes al mismo `(sucursal, tipo='bicicleta')` (via `asyncio.gather`) generan **10 consecutivos distintos** sin colisión — lock test del helper `assign_ingreso_consecutivo`.

### (b) Flujo sin placa

- **AC-5**: `Given` operador autenticado, `When` clickea "Sin placa" → selecciona "Patineta", `Then` el POST envía payload variante `{placa_presente: false, uuid_tipo_vehiculo: <uuid>, consecutivo: undefined}` (cliente no asigna — backend asigna). Schema discriminated union acepta variante 2; rechaza variante 1 con `placa_presente: true + uuid_tipo_vehiculo: <uuid>` (no mezclar).
- **AC-6**: `And` el operador ve en `<TiqueteModal>` la línea `Identificación: PATIN-000001-<uuid8>` (no `Placa:`).
- **AC-7**: `And` el tiquete imprime (vía `escposBuilder.build('entrada', payload)`) la línea `Identificación: BICI-000001-3f8a1b2c` en el byte 12 del buffer de 19/20 campos — byte-fixture test pin exacto.

### (c) Cupo

- **AC-8**: `Given` sucursal tiene `cantidad_vehiculos_sucursal.cantidad = 20` para bicicleta y `mv_ocupacion_diaria.activos = 20` para `(sucursal, 'bicicleta')`, `When` operador intenta crear ingreso bici, `Then` backend responde **422 `motivo_forzado_requerido`** (cupo_agotado). Operador puede forzar con motivo ≥10 chars prefijo `[FORZADO: ...]` via `<ForzarIngresoModal>` existente (sin modal nuevo).
- **AC-9**: `And` el `mv_ocupacion_diaria` cuenta el nuevo activo en `activos` después del INSERT no-placa (regression test T12 — ver §6).

### (d) Auditoría

- **AC-10**: `And` la fila aparece en `log_transaccional.datos_nuevos` con `consecutivo` en el JSON canónico (A-05 + hash chain verified per R5 — no explicit handling needed, `record_event` fluye la columna).
- **AC-11**: `And` el AST walk `tests/static/test_no_write_after_insert.py` NO reporta regresión — `consecutivo` se asigna UNA vez al INSERT (no UPDATE path exists).

### (e) UI / tiquetes

- **AC-12**: `And` `<Principal.tsx>` y `<IngresoPanel.tsx>` renderizan ambos `Con placa` y `Sin placa` como botones side-by-side, manteniendo `Con placa` visualmente dominante (mitigación R5 — operador entrenado no se confunde). Tooltip en `Sin placa`: "Vehículos sin placa (bicicletas, patinetas)" (i18n key `operacion.ingreso_sin_placa_cta_tooltip`).

---

## 6. Open Questions (10 del exploration + 1 nuevo — necesitan respuesta humana ANTES de spec)

> Cada uno tiene recomendación por default. El gatekeeper debe confirmar/override ANTES de que `sdd-spec` arranque.

- **Q1 — Reset del `consecutivo`**. ¿Se resetea alguna vez (year change, tipo change, admin action)? — **Recomendación: NO, monotónico forever**. El counter solo incrementa dentro de `(uuid_sucursal, uuid_tipo_vehiculo)`. Si admin reconfigura cupos o cierra un tipo, los counters existentes NO se tocan. Confirmar con usuario.
- **Q2 — Source del `<uuid8>`**. ¿Los primeros 8 hex del `uuid_ingreso` (`Ingreso.uuid` = `gen_random_uuid()` per `IdMixin`), o del `request_id`, o del `actor_uuid`? — **Recomendación: `source_event_uuid.hex[:8]`** donde `source_event_uuid` es el `Ingreso.uuid` generado por el backend. Ya fluye en el body de response — el cliente lo lee del 201. Stable, único, derivado del evento.
- **Q3 — Etiqueta del tiquete**. ¿`Identificación:` o `Consecutivo:`? — **Recomendación: `Identificación:`** (operator-facing label). El field name subyacente sigue siendo `consecutivo`. DEC-SUC-26 ya usa "Identificación" implícitamente en el QR payload.
- **Q4 — Frontend TipoSelect source**. ¿(a) NEW hook `useTiposVehiculoSinPlaca()` (single responsibility, reusable) o (b) reuse `useTiposVehiculo()` y filtrar en `<TipoSelect>` (fewer files)? — **Recomendación: (a)** — alinea con precedent F3.3 `useSesionActiva` (un hook por concern).
- **Q5 — Layout dos botones**. ¿(i) dos `<Button>` side-by-side, (ii) dos `<Tabs>` shadcn, o (iii) dos `<Card>` stacked vertical? — **Recomendación: (i)** — read más directo de "two buttons separated"; (ii) overkill para binary choice; (iii) wastes vertical space en kiosko.
- **Q6 — File location de `<IngresoSinPlacaPanel>`**. ¿(a) `components/IngresoSinPlacaPanel.tsx` (peer de `PlacaInput`) o (b) `components/IngresoSinPlacaForm.tsx` (peer de form, no panel)? — **Recomendación: (a)** — alinea con `IngresoPanel`/`PlacaInput` naming.
- **Q7 — Idempotency-Key migration risk**. ¿Aceptable el riesgo de que retries con `placa=null` (nuevo) vs `placa=""` (F6.1 legacy) produzcan SHA-256 distintos? — **Recomendación: aceptar**. Operator retry window es ~5 segundos; la nueva canonicalJSON se genera en cada edit del form. Sin shim backward-compat — agrega complejidad para ventana de 5s. Documentar como cost conocido de la migración.
- **Q8 — UX "tipo before or after click Sin placa"**. ¿(i) click → modal con `<TipoSelect>` + Generar (consistente con `<ForzarIngresoModal>`/`<TiqueteModal>` precedent) o (ii) click → expand inline panel con `<TipoSelect>` + Generar (estilo observaciones textarea)? — **Recomendación: (i)** — simetría con modales existentes, más click pero menos scroll.
- **Q9 — Cupo agotado UX**. ¿Reusar `<ForzarIngresoModal>` existente (no muestra placa, solo motivo textarea) o modal nuevo específico para no-placa? — **Recomendación: reusar** — el modal no depende de placa. Sin modal nuevo.
- **Q10 — Sync replication**. ¿Cloud preserva el branch-assigned `consecutivo` verbatim (no asigna cloud-side) y el stub sync actual (PR9b no-op) fluye la columna automáticamente? — **Recomendación: SÍ**. Ya verificado que `record_event` fluye todo `new_attrs`. Sin trabajo adicional de sync.
- **Q11 (NUEVO) — ¿Bici/patineta salen con la misma modal de salida que carro/moto, o necesitan un flujo dedicado?**. — **Recomendación: misma modal**, el handler de salida (`POST /operacion/salidas`) ya busca por `uuid_ingreso` (no por placa), y el JOIN retorna `consecutivo` para mostrar al operador si está presente. **No requiere trabajo de salida** — verify en design phase. Si el operador necesita tipear el consecutivo en lugar de la placa para identificar el vehículo a la salida, eso es UX follow-up (forward F13.x).

---

## 7. Risks (resumen — 11 del exploration)

| ID | Sev | Risk | Mitigation |
|---|---|---|---|
| **R1** | HIGH | **Race condition en `consecutivo` entre POSTs concurrentes** mismo `(sucursal, tipo)` kiosko | Approach A2 (`SELECT FOR UPDATE` sobre counter row, `assign_consecutivo` precedent T-PR9-002) + UK parcial `(uuid_sucursal, uuid_tipo_vehiculo, consecutivo) WHERE consecutivo IS NOT NULL` como defense in depth. AC-4 lo testea con 10 `asyncio.gather`. |
| **R2** | MED | **Filas carro/moto existentes quedan con `consecutivo=NULL`** | Schema `consecutivo: str \| None = None`. UK parcial solo aplica a NOT NULL. Frontend `PostIngresoResponseSchema` declara `consecutivo: z.string().nullable()` — lee `null` para legacy rows sin breaking change. |
| **R3** | LOW | **DIAN `consecutivo` confusion** (`factura_electronica.consecutivo` vs `ingreso.consecutivo`) | DEC-INCOME-01 explícito + prefijo `BICI-`/`PATIN-` en valor visible + nombres de columna explícitos (`consecutivo_ingreso` si necesario en iteration posterior). |
| **R4** | LOW | **Discriminated-union Zod wire-shape change** (v6.1.1 → v6.2.0) | Aditivo (semver minor). Testea union `.parse()` contra los 6 payloads F6.1 existentes (regression suite `operacion.json`). |
| **R5** | MED | **`<IngresoSinPlacaPanel>` UX divergence de `<PlacaInput>`** | Tooltip en botón `Sin placa` explicando "Vehículos sin placa (bicicletas, patinetas)" (AC-12). Botón `Con placa` visualmente dominante. Documentar en runbook onboarding. |
| **R6** | MED | **Counter table es la 51ª tabla** (fuera de `bootstrap-monorepo-foundation`) | Precedent `idempotency_keys` (50ª, mitigada por PR7). Misma mitigación: `[A]` con REVOKE + `BEFORE UPDATE OR DELETE` trigger + `fecha_retencion_hasta` 5-year DIAN retention en **misma** migración per `config.yaml rules.tasks`. |
| **R7** | LOW | **AST walk `test_no_write_after_insert.py` rechaza UPDATE/DELETE en `[L-E]`** | `consecutivo` se asigna UNA vez al INSERT (en `new_attrs` ANTES del `repo.crear_ingreso_evento`). No hay path UPDATE para esta columna. AC-11 lo testea. |
| **R8** | LOW | **`Principal.tsx` y `IngresoPanel.tsx` son duplicate-shaped** | Ambos en el mismo PR (atomicity > factoring shared component ahora — R8 explicit). Cambios pequeños ~10 LOC cada uno. |
| **R9** | LOW | **`sync_queue` recursion** si sync trigger mal configurado | Migración incluye `WHEN (TG_TABLE_NAME <> 'ingreso_consecutivo_contador')` en sync trigger (AGENTS.md precedent para `sync_queue` exclusion). |
| **R10** | LOW | **`mv_ocupacion_diaria` 10s polling latency** (stale cupo momentáneo) | Ya aceptado per DEC-SUC-11. V2 `cupo_agotado` lee mismo MV — race simétrico. Sin nueva mitigación. |
| **R11** | LOW | **Idempotency-Key migration** (F6.1 legacy `placa=""` hash differs de nuevo `placa=null`) | Operator retry window ~5s aceptable. Documentado como known cost (Q7 del §6). |

---

## 8. Out of Scope (no incluidos ahora — repetir explícito)

- **Reset del `consecutivo`** (monotónico forever, Q1).
- **UI admin para gestionar resoluciones** (no es DIAN, RN3).
- **Cambios en sync pipeline** (record_event fluye la columna automáticamente).
- **Cambios en salidas / reimpresión / arqueo** (handler de salida lee JOIN; verify en design phase).
- **Cambios en `mv_ocupacion_diaria`** (ya cuenta por `(sucursal, tipo)` — solo agregar test regresión).
- **Auto-cancel / auto-renew** (Q1 — monotónico forever).
- **Hash chain changes** (A-05 verified per R5 — `record_event` fluye todo).
- **Backend sync workers** (`job_sync_*` — sin cambios).
- **BFF v2** (no impact).
- **Selector manual de tipo en flujo con placa** (BR2 invariante — no se rompe).
- **Multi-idioma para `operacion.json`** (sigue el precedent F2.x — solo es-CO en este PR; en-US/pt-BR follow-up si se requiere).

---

## 9. References

- **Inputs primarios**:
  - `openspec/changes/ingreso-multi-tipo-consecutivo/exploration.md` (278 líneas, 12 gaps, 3 approaches, 10 Q, 11 R) — base de este proposal.
  - Engram `#1995` `sdd/ingreso-multi-tipo-consecutivo/explore` — observation canónica de la fase explore.
- **Precedentes cercanos (archivados)**:
  - `openspec/changes/archive/2026-09-16-hu-f4-1-deteccion-tipo-vehiculo/` — `detectarTipoVehiculo()` + `useTiposVehiculo()` + REQ-OPS-125..130 (precedent formato proposal + DELTA spec).
  - `openspec/changes/archive/2026-09-17-fase-6-1-flujo-ingreso/` — `Principal.tsx` + `<PlacaInput>` + `<TiqueteModal>` baseline (precedent renderer).
  - `openspec/changes/archive/2026-09-19-fase-7-3-tiquetes-salida/` — `escposBuilder` + `escposTemplates` + byte-fixture pattern (precedent print layer).
- **Patrones de código a reutilizar verbatim**:
  - `backend/packages/parkos_core/src/parkos_core/repo/resolucion_facturacion.py::assign_consecutivo` (líneas 47-183) — patrón `SELECT FOR UPDATE` para el helper nuevo.
  - `backend/scripts/seed_tipos_y_cupos_sucursal.py` (líneas 1-205) — canon lowercase `carro`/`moto`/`bicicleta`/`patineta` para `TIPO.upper()` en el formato del consecutivo.
  - `apps/electron-sucursal/src/features/catalogos/hooks/useTiposVehiculo.ts` (F4.1 MERGED) — patrón SWR + fallback para `useTiposVehiculoSinPlaca.ts` nuevo.
- **Constraints arquitectónicos (no negociables)**:
  - `AGENTS.md` §Architectural Principles — audit-first, bi-temporal, C/Q/U-no-D, multi-tenant, hash chain.
  - `AGENTS.md` §Authorization Model — gitflow (PRs mergean a `dev`, releases a `main`).
  - `AGENTS.md` §DevOps — Docker image `ghcr.io/easypunto/parkos:vX.Y.Z`, BuildTarget/SERVICE_NAME.
  - `openspec/config.yaml` `rules.tasks` — REVOKE + trigger en misma migración para `[A]` tables; pre-flight `alembic upgrade --sql`.
- **Convenciones operativas**:
  - Conventional Commits sin Co-authored-by AI (AGENTS.md canon).
  - Branch naming `feature/hu-f4-1-NN-<slug>` (gitflow estrico AGENTS.md §12.2).
  - PR review budget 800 LOC per `config.yaml rules.tasks` — chained PRs PR-A + PR-B cubren los ~1115 LOC estimados.
  - PR-A → `dev` (merge `--ff-only` si descendiente directo, `--no-ff` si rebase upstream); branch borrada post-merge.

---

## Ready for next phase

**Status**: `ready-for-sdd-spec` + `sdd-design` (paralelo).
**Numeración REQ-OPS propuesta**: REQ-OPS-143..150 (continuación post-REQ-OPS-142 vigente; 8 new REQs planeados: 143 = helper assign, 144 = UK parcial counter, 145 = columna ingreso, 146 = discriminated union frontend, 147 = Sin placa panel + layout, 148 = escposBuilder Identificación, 149 = TiqueteModal render, 150 = WCAG forward). `sdd-spec` debe verificar numeración monotónica contra `operations/spec.md` antes de emitir.
**Decisiones locked (ratificadas en este proposal)**: DEC-INCOME-01 (naming), Approach A2 (counter table + UK parcial defense), split PR-A → PR-B (gitflow), open questions con defaults (Q1..Q11 §6 — el gatekeeper debe confirmar/override).
**Siguiente paso**: gatekeeper valida → `sdd-spec` emite specs/operations/spec.md delta → `sdd-design` emite design.md con secuencia + ER delta + discriminated union refs → `sdd-tasks` parte en 2 chained PRs.