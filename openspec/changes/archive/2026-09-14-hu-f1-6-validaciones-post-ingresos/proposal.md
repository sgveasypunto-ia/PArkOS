# Proposal: HU-F1.6 — Validaciones reales en `POST /operacion/ingresos`

> **Change**: `hu-f1-6-validaciones-post-ingresos`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.6 (Fase-1 prerequisites — backend)
> **Inputs**: `openspec/changes/hu-f1-6-validaciones-post-ingresos/exploration.md`
> (16 sections, ~30KB, written 2026-09-14), `plan.md` (HU-F1.6 lines 786–798,
> DEC-SUC-11 línea 426, DEC-SUC-21 línea 590, DEC-SUC-22 línea 595, KD-FORZADO A-04
> addendum #4), `modelo_datos_er.mmd` (tables `ingreso` 577-596 [L-E],
> `cantidad_vehiculos_sucursal` 428-446 [V], `tipos_vehiculo` 87-104 [V],
> `tarifas_sucursal` 406-426 [V], `subscripciones_cliente`, `subscripcion_vehiculos`,
> `vehiculos`, `alerta` [L-W], `mv_ocupacion_diaria` post-F1.5),
> `openspec/changes/archive/2026-09-14-hu-f1-5-mv-ocupacion-diaria/` (precedente
> inmediato — REQ-OPS-030..033 + KD chain pattern + materialized view pattern,
> commit `fc72adb`), `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/`
> (precedente bi-temporal predicate reusable in V3, commit `467b4f0`),
> `openspec/changes/archive/2026-09-14-hu-f1-3-sesion-unica/` (precedente
> `partial unique index` + pre-flight abort + custom handler before factory +
> AST walk pattern, commit `ca3f9bf`),
> `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py::create_ingreso`
> (thin pass-through lines 92-114, F1.5 left it intentionally unvalidated),
> `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py::IngresoCreate`
> (current 6-column insert payload, no `forzado` field).
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-1-prerequisites-backend`
> (HEAD `e1cc79b`) · **PR target**: `origin/dev`.

## 1. Why

The operator screen at the parking lot accepts a vehicle and the moment the user clicks
"Registrar ingreso", the client (`web_sucursal/src/lib/validation/placa.ts`, A-03 of the
corpus) runs **four validations** before POSTing to the backend: regex over the plate
(`ABC123` for Auto, `ABC12D` for Moto), mensualidad-vs-rotación derivation from the
`uuid_subscripcion_cliente`, cupo check against the branch capacity, and duplicate-active
placa rejection. Today, the backend handler `POST /api/v1/operacion/ingresos`
(`api/v1/operacion.py:92-114`) is a **thin pass-through**: it accepts whatever the
Pydantic schema allows, calls `repo.event.record_event`, and returns 201. **The
backend performs zero business validation.**

This violates the corpus rule **"single source of truth"** and creates four concrete
risks:

1. A stale client (Electron autoupdate lag, manual deploy of a partial build) can submit
   `placa = "abc123"` (lowercase) or `placa = "AB12C"` (4 chars) and pollute `prod.ingreso`
   with rows that no downstream query (`GET /operacion/cotizar`, `GET /operacion/salida`
   in F7, audit reports) can match cleanly.
2. A consumer alternate (admin web portal, future mobile app, queued replay) can submit
   `forzado=true` semantics that never existed in the client without the server enforcing
   the KD-FORZADO chain (prefix `[FORZADO: <motivo ≥10 chars>]`).
3. The `OcupacionStrip` (F4.3, client polling `GET /operacion/ocupacion` every 10s) shows
   the configured cupo, but the server itself cannot enforce it on `POST` — so the strip
   is contradicted by a manual POST.
4. `tipo_entrada` (`MENSUALIDAD | ROTACION`) is **derived client-side today** and sent as
   an inferred column; the corpus requires it derived server-side (DEC-SUC-21) and
   returned in the response, **never persisted** in `prod.ingreso`.

F1.6 moves **all four validations + the KD-FORZADO bypass contract + the
`tipo_entrada` derivation** to the backend. The handler `create_ingreso` is replaced
(`+140 LOC`, ~`260 LOC` total per plan.md línea 787) with the layered defense-in-depth
chain that the precedent commits established. **The endpoint URL stays the same** —
backwards compatible with F1.5's PR5 and any consumer that POSTs against it. Only the
response body gains two fields (`tipo_entrada`, `forzado_en_creacion`, `motivo_forzado`)
and the error body gains typed discriminators (422 + 409).

F1.6 closes three contractual dependencies declared in `plan.md` and the precedents:

- **F6 — Ingreso vehicular (CU-01)**: the screen-to-DB contract for vehicle entry is
  enforced server-side end to end.
- **F4.3 — `OcupacionStrip`**: when the operator hits "ingreso", the vacancy check
  coincides with the polled strip (cupo via `mv_ocupacion_diaria`).
- **F7 — Salida (post-flow)**: the future exit flow can rely on `ingreso` rows having
  passed regex + subscripcion + cupo, so its derivation of `cobrar=false` from
  `mensualidad_vigente` (REQ-OPS-023) and the open-state derived view (`V_INGRESO_ESTADO`)
  are guaranteed to operate on clean rows.

The work is **purely handler + repo layer + schema** — **zero Alembic migration**, zero
model changes, zero sync catalog changes (validations live in `repo/*.py`; the data
model is read-only against existing columns).

## 2. Decision Summary

| # | Decisión | Rationale |
|---|---|---|
| **D-HU-F1.6-1** | **Modificar** el handler `create_ingreso` en `api/v1/operacion.py` — NO crear endpoint nuevo | URL `/api/v1/operacion/ingresos` ya está reservada por F1.5 PR5; el router factory (`make_router`) no se toca; el handler dedicado gana por orden de registro |
| **D-HU-F1.6-2 (KD-FORZADO-01)** | El ÚNICO bypass operacional a V1/V2/V3/V6 es `forzado=true` con prefijo `[FORZADO: <motivo ≥10 chars>]` parseado de `observaciones`. Si `forzado=true` sin prefijo → `422 motivo_forzado_requerido`; si `forzado=false` con prefijo → `422 forzado_contradiccion`; motivo <10 chars → `422 motivo_forzado_insuficiente` | Único contrato auditable sin columna nueva (A-04); parseo server-side, no confiar en flag booleano separado |
| **D-HU-F1.6-3 (KD-V4)** | Eventual consistency con la vista materializada `mv_ocupacion_diaria` (lag ≤10s post-F1.5). **NO** `SELECT … FOR UPDATE/SHARE`, **NO** lock pesimista | RIESGO-SUC-02 del corpus ya documenta el lag como riesgo vivo aceptado; el polling 10s del cliente y del refresh job es la fuente de verdad operacional |
| **D-HU-F1.6-4 (KD-V2)** | Regex hardcoded a nivel de módulo en `repo/placa.py` (constantes `FORMATO_AUTO = r"^[A-Z]{3}[0-9]{3}$"`, `FORMATO_MOTO = r"^[A-Z]{3}[0-9]{2}[A-Z]$"`) | A-03; CHECK constraint a nivel DB descartada por bloquear migración nacional futura; configurable en HU futura con cat tabla |
| **D-HU-F1.6-5 (KD-V7)** | `forzado` se **deriva** de `observaciones.startswith(FORZADO_PREFIX)`, NO se acepta como campo separado en el payload. El cliente manda `forzado: bool` opcional que el server valida contra el prefijo | Defensa en profundidad: si el cliente manda `forzado=true` pero `observaciones` no tiene prefijo, se rechaza con 422; la única fuente de verdad es el prefijo |
| **D-HU-F1.6-6** | Server **deriva** `uuid_tipo_vehiculo` desde la regex de placa (`detectar_tipo_vehiculo`) y **sobreescribe** el del cliente si no concuerda (BR2 CU-01) | Defense in depth — el cliente puede estar mal actualizado; la regex es la autoridad |
| **D-HU-F1.6-7 (KD-V9)** | Defensa en profundidad: 4 capas — (1) regex placa server-side sobreescribiendo `uuid_tipo_vehiculo`, (2) KD-FORZADO chain como precondición antes de V1/V2/V3/V6, (3) `record_event` + `insertar_alerta_forzado` en **misma transacción** (un solo `commit()`), (4) AST walk `tests/static/test_kd_forzado_in_handler.py` verifica el orden literal de invocaciones (R7) | Ningún fallo individual (cliente desactualizado, cliente bypass, alerta huérfana, orden alterado por dev futuro) puede bypassear el conjunto |
| **D-HU-F1.6-8** | Helper puro nuevo `repo/ingreso.py` con 8 funciones de validación (V1..V8 + derivación V9) + `repo/placa.py` (regex + derivación) + `repo/subscripcion_activa.py` (V6 + F7 reuse) + `repo/alerta.py` (insert alerta forzado) | Encapsula SQL + predicado bi-temporal reusable; testeable sin HTTP; consistente con F1.5 `repo/ocupacion.py` y F1.8 `repo/cotizacion.py` |
| **D-HU-F1.6-9** | Alerta `capacidad_agotada_forzado` insertada **solo si** V2 fue bypassed (`bypass_reason == "cupo_agotado"`); `tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`, motivo en `datos_nuevos` (jsonb) | Defense in depth (R2): evita alertas falsamente disparadas cuando el cupo estaba bien pero se forzó por otra razón (ej: tarifa no vigente) |
| **D-HU-F1.6-10** | Schemas `IngresoCreateForzado` (entrada) + `IngresoReadForzado` (salida con `tipo_entrada`) + 7 clases de error tipadas (`CupoNoConfiguradoError`, `MotivoForzadoRequeridoError`, `TarifaVigenteNoEncontradaError`, `PlacaFormatoInvalidoError`, `SubscripcionInactivaOVencidaError`, `IngresoActivoExistenteError`, `TipoVehiculoInvalidoError`) | `extra='forbid'` heredado de `_Base`; 422 con discriminador + payload estructurado |
| **D-HU-F1.6-11** | Orden estricto de validación: KD-3 tenant scope → V5 regex placa → V4 tipo vehículo vigente → KD-FORZADO-01 → V1+V2 cupo → V3 tarifa → V6 subscripción → V8 no-duplicado activo → INSERT `[L-E]` + alerta (mismo `commit()`) → derivar V9 `tipo_entrada` → 201 con `IngresoReadForzado`. AST walk verifica el orden literal (R7 invariante) | Defense in depth — V5 antes de KD-FORZADO evita bypass por regex inválida; V8 al final garantiza que solo se rechace duplicado después de pasar todas las demás (si no hay cupo o la placa es inválida, no es duplicado, es otro error) |
| **D-HU-F1.6-12 (KD-V6)** | Idempotencia via header HTTP `Idempotency-Key` (ya en PR2 middleware), NO se agrega `correlacion_id` al body | DEC-IDEM-01; evita duplicar el surface area |
| **D-HU-F1.6-13 (KD-V8)** | Tanto `operador-` como `admin-` pueden emitir `forzado=true`. Si se requiere "solo admin-", check dedicado en HU futura con flag RBAC | Aceptar ambos simplifica MVP; el log estructurado + alerta auditable detecta abuso |

## 3. Goals & Non-Goals

### 3.1 Goals

1. Modificar `POST /api/v1/operacion/ingresos` para aplicar 9 validaciones server-side
   (V1..V9) más el KD-FORZADO-01 como única ruta de bypass operacional.
2. Mover la derivación de `tipo_entrada` (`MENSUALIDAD | ROTACION`) al backend —
   server-side desde `uuid_subscripcion_cliente`, devuelto en respuesta, **nunca
   persistido** en `prod.ingreso` (DEC-SUC-21).
3. Mantener el orden de validación estricto (D-HU-F1.6-11) con verificación AST walk
   sobre el handler para evitar reordenamientos accidentales por devs futuros (R7).
4. Insertar alerta `capacidad_agotada_forzado` en **misma transacción** que el ingreso
   (un solo `commit()`) cuando V2 fue bypassed — defensa contra alerta huérfana (R5).
5. Sobreescribir `uuid_tipo_vehiculo` del cliente con el derivado de la regex de placa
   (BR2 CU-01) — defense in depth contra cliente desactualizado (D-HU-F1.6-6).
6. Aceptar `forzado` como flag explícito en el payload Y como prefijo
   `[FORZADO: …]` en `observaciones` — KD-FORZADO-01 contrato server-side (D-HU-F1.6-5).
7. Cerrar tres dependencias contractuales: F6 (CU-01 Ingreso), F4.3 (`OcupacionStrip`),
   F7 (Salida post-flow).
8. Defense in depth con 4 capas (D-HU-F1.6-7) — regex server-side + KD-FORZADO chain
   + alerta + AST walk.
9. Cubrir con 14 tests: 8 HTTP unit + 4 KD-FORZADO unit + 6 regex unit + 3 DB
   integration + 1 AST walk no-write + 1 AST walk order = **23 parametrizaciones
   distribuidas en 14 archivos de test**.
10. Mantener `api/v1/__init__.py`, `api/v1/router_factory.py`, `api/deps.py`,
    `auth/tenancy.py`, `models/*`, `migrations/*`, `repo/event.py`, `repo/cotizacion.py`
    intactos — solo se modifica `api/v1/operacion.py`, `schemas/operacion.py`,
    `repo/ocupacion.py`, `repo/tarifas_vigencia.py` y se crean 4 nuevos
    `repo/*.py`.

### 3.2 Non-Goals

1. NO se crea endpoint nuevo (`/ingresos-v2`, `/ingresos/validar`, etc.) — el handler
   dedicado reemplaza al actual in-place. URL y método POST sin cambios.
2. NO se introduce lock pesimista (`SELECT … FOR UPDATE/SHARE`) — la MV provee
   eventual consistency aceptable (KD-V4, RIESGO-SUC-02 del corpus).
3. NO se introduce columna nueva en `prod.ingreso` para `forzado` ni `tipo_entrada` —
   DEC-SUC-21 veda `tipo_entrada` columna; KD-FORZADO-01 veda columna `forzado`.
4. NO se introduce `correlacion_id` al payload — DEC-IDEM-01 delega idempotencia al
   header `Idempotency-Key` (PR2 middleware, intacto).
5. NO se crea workflow de anulación (`prod.anulaciones` workflow vive en Fase 7+) —
   DEC-ANUL-01; `ingreso` nunca UPDATE post-creación.
6. NO se hace regex configurable (catálogo, settings, JSON) — KD-V2 hardcoded para
   MVP, sale del scope (R3).
7. NO se introduce CHECK constraint en `prod.ingreso.placa` — bloquearía migración
   nacional futura (A-03).
8. NO se siembra catálogo adicional — `capacidad_agotada_forzado` ya sembrado en
   F1.14 (post-DEC-SUC-14), `tipos_vehiculo` vigente, `cantidad_vehiculos_sucursal`
   vigente, `tarifas_sucursal` vigente post-F1.4, `subscripciones_cliente` vigente
   — todo preexistente.
9. NO se crea endpoint `GET /operacion/ingresos/{uuid}/validar` (preview sin insertar)
   — el handler hace insert o 422, sin preview.
10. NO se modifica el `IdempotencyKeyMiddleware` (PR2) — la dedupe por header sigue
    funcionando; el handler validado solo cambia la respuesta en el happy path (201) y
    agrega 422/409 antes del INSERT.

## 4. Architecture Overview

```
HTTPS POST /api/v1/operacion/ingresos
        Body: IngresoCreateForzado
        │      {uuid_sucursal?, placa, uuid_tipo_vehiculo?,
        │       uuid_subscripcion_cliente?, fecha_ingreso?,
        │       observaciones?, forzado?: bool = false}
        │  Idempotency-Key: <uuid>   (header, manejado por PR2 middleware)
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ api/v1/operacion.py  (MODIFICAR, replace create_ingreso lines 92-114)         │
│                                                                              │
│ @router.post("/ingresos", response_model=IngresoReadForzado, status_code=201)│
│ async def create_ingreso(payload, response, session, ctx, _claims)           │
│                                                                              │
│  1. KD-3 (target_sucursal):                                                │
│      target = payload.uuid_sucursal or ctx.sucursal_uuid                    │
│      if not target: raise 400 missing_sucursal_context                      │
│      authorize target vs ctx (operador-/admin-)                             │
│      → 403 tenant_scope_violation / 403 sucursal_not_permitted               │
│                                                                              │
│  2. V5 regex placa → tipo derivado (D-HU-F1.6-6):                          │
│      uuid_tipo_vehiculo = repo/placa.py::detectar_tipo_vehiculo(payload.placa)│
│      if None: raise 422 placa_formato_invalido                              │
│                                                                              │
│  3. V4 tipo vehículo vigente:                                               │
│      if not repo/ingreso.py::validar_tipo_vehiculo_vigente(...):             │
│          raise 422 tipo_vehiculo_invalido                                   │
│                                                                              │
│  4. KD-FORZADO-01 (D-HU-F1.6-2, D-HU-F1.6-5):                              │
│      motivo = repo/ingreso.py::validar_kd_forzado(payload.observaciones,     │
│                                                    payload.forzado)         │
│      bypass_reason: str | None = None                                       │
│      if motivo and motivo.bypass == 'forzado':                              │
│          bypass_reason = motivo.bypass_reason                              │
│                                                                              │
│  5. V1+V2 cupo (KD-V4 eventual consistency):                                │
│      cupo_result = repo/ocupacion.py::validar_cupo_disponible(              │
│          session, uuid_sucursal=target,                                     │
│          uuid_tipo_vehiculo=uuid_tipo_vehiculo, forzado=bool(bypass_reason))│
│      if cupo_result.cupo_no_configurado:                                    │
│          raise 422 cupo_no_configurado (forzado_permitido: true)            │
│      if cupo_result.cupo_agotado:                                           │
│          raise 422 motivo_forzado_requerido (cupo_maximo, activos)          │
│                                                                              │
│  6. V3 tarifa vigente (bi-temporal canónico F1.4):                          │
│      tarifa_result = repo/tarifas_vigencia.py::validar_tarifa_vigente(      │
│          session, uuid_sucursal=target,                                     │
│          uuid_tipo_vehiculo=uuid_tipo_vehiculo,                              │
│          at=datetime.now(UTC), forzado=bool(bypass_reason))                 │
│      if not tarifa_result.vigente:                                          │
│          raise 422 tarifa_vigente_no_encontrada                             │
│                                                                              │
│  7. V6 subscripción (if provided):                                          │
│      if payload.uuid_subscripcion_cliente:                                  │
│          sub_result = repo/subscripcion_activa.py::\                        │
│              validar_subscripcion_vigente(                                  │
│                  session, uuid_subscripcion_cliente=…, forzado=…)            │
│          if not sub_result.vigente:                                         │
│              raise 422 subscripcion_inactiva_o_vencida                      │
│                                                                              │
│  8. V8 no-duplicado activo (D-HU-F1.6-3, sin lock):                         │
│      uuid_activo = repo/ingreso.py::existe_ingreso_activo(                  │
│          session, uuid_sucursal=target, placa=payload.placa)                │
│      if uuid_activo:                                                        │
│          raise 409 ingreso_activo_existente (uuid_ingreso_existente)        │
│                                                                              │
│  9. INSERT [L-E] + alerta (D-HU-F1.6-9, misma TX):                          │
│      new_row = await record_event(session, Ingreso, ...)                    │
│      if bypass_reason == "cupo_agotado":                                    │
│          await repo/alerta.py::insertar_alerta_forzado(                     │
│              session, uuid_sucursal=target, uuid_ingreso=new_row.uuid,      │
│              actor_uuid=ctx.actor_uuid, motivo=motivo)                      │
│      await session.commit()    ← UN solo commit                             │
│                                                                              │
│ 10. Derivar tipo_entrada (DEC-SUC-21, V9):                                  │
│      tipo_entrada = "MENSUALIDAD" if payload.uuid_subscripcion_cliente      │
│                     else "ROTACION"                                         │
│      # NUNCA persistir en prod.ingreso (D-HU-F1.6-3, DEC-SUC-21)            │
│                                                                              │
│ 11. response.headers["Cache-Control"] = "no-store"                          │
│ 12. return IngresoReadForzado.model_validate(new_row) + tipo_entrada       │
│             + forzado_en_creacion=(bypass_reason is not None)               │
│             + motivo_forzado=motivo if bypass_reason else None             │
└──────────────────────────────────────────────────────────────────────────────┘
        ▲                            ▲                       ▲
        │ AST walk                   │ AST walk              │ SELECT-only
        │ ordering gate              │ read-only gate        │ (sin lock)
        │                            │
tests/static/test_kd_forzado_in_handler.py
tests/static/test_no_write_in_ingreso.py
        │
        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ Repo helpers (NEW):                                                         │
│   repo/placa.py              (30 LOC) — regex + detectar_tipo_vehiculo      │
│   repo/ingreso.py            (180 LOC) — 8 funciones de validación + alerta │
│   repo/subscripcion_activa.py(50 LOC) — validar_subscripcion_vigente        │
│   repo/alerta.py             (60 LOC) — insertar_alerta_forzado              │
│   repo/ocupacion.py          (+40 LOC) — validar_cupo_disponible             │
│   repo/tarifas_vigencia.py   (+30 LOC) — validar_tarifa_vigente             │
│                                                                              │
│ Tablas operacionales (READ ONLY, sin DDL):                                  │
│   prod.ingreso                  [L-E]  — INSERT vía record_event             │
│   prod.cantidad_vehiculos_sucursal [V] — V1+V2 vía mv JOIN                  │
│   prod.mv_ocupacion_diaria      [MV]  — count(*) activos                    │
│   prod.tarifas_sucursal         [V]   — V3 bi-temporal                     │
│   prod.subscripciones_cliente   [V]   — V6 vigente                        │
│   prod.subscripcion_vehiculos   [V]   — junction V6                        │
│   prod.vehiculos                [V]   — V6 via placa                       │
│   prod.tipos_vehiculo           [V]   — V4 vigente                        │
│   prod.alerta                   [L-W] — INSERT capacidad_agotada_forzado    │
└──────────────────────────────────────────────────────────────────────────────┘
```

Toda la lógica de validación vive en el backend (`repo/*.py`); el handler HTTP es
thin + orchestador. El cliente **pierde toda capacidad de validación propia** (se
desactiva `web_sucursal/src/lib/validation/placa.ts` A-03 — sale del scope de F1.6,
queda como cleanup post-archive). Defense in depth = 4 capas (D-HU-F1.6-7).

## 5. Capabilities

### New

- **`repo/ingreso.py`** — helper puro async con 8 funciones de validación
  (`validar_tipo_vehiculo_vigente`, `validar_cupo_disponible` re-export, `validar_tarifa_vigente`
  re-export, `validar_subscripcion_vigente` re-export, `existe_ingreso_activo`,
  `validar_kd_forzado`, `crear_ingreso_evento` thin wrapper de `record_event`,
  `insertar_alerta_forzado` re-export). Encapsula las 9 validaciones V1..V9 con
  KD-FORZADO-01 como bypass.
- **`repo/placa.py`** — helper puro async con `FORMATO_AUTO`, `FORMATO_MOTO` (regex
  constantes a nivel de módulo), `detectar_tipo_vehiculo(placa) -> UUID | None`
  (lazy lookup `tipos_vehiculo` por el `tipo` derivado del regex).
- **`repo/subscripcion_activa.py`** — extrae `resolve_active_subscription_for_exit`
  (post-PR5) + check `fecha_vencimiento >= NOW()`; usado por V6 y reutilizado por F7.
- **`repo/alerta.py`** — helper puro `insertar_alerta_forzado` con
  `tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`, motivo en
  `datos_nuevos` (jsonb).
- **`validation-f1-6-post-ingresos`** — capability nueva que cubre las 9 validaciones
  server-side en `POST /operacion/ingresos` + el KD-FORZADO-01 chain + derivación
  `tipo_entrada` server-side. Spec en
  `openspec/changes/hu-f1-6-validaciones-post-ingresos/specs/operations/spec.md`,
  archivada en `openspec/specs/operations/spec.md` como **REQ-OPS-034..041**
  (8 requirements).

### Modified

- **`operations`** — la skill canónica agrega la regla "validación server-side completa
  en `POST /operacion/ingresos` con KD-FORZADO-01 como única ruta de bypass; tipo_entrada
  derivado server-side, nunca persistido". Sin cambio contractual sobre REQ-OPS-001..033
  (cubierto por F1.1..F1.5); sólo delta. Spec deltada en
  `openspec/changes/hu-f1-6-validaciones-post-ingresos/specs/operations/spec.md`.
- **`api/v1/operacion.py::create_ingreso`** — handler dedicado reemplazado in-place
  (líneas 92-114 → ~232 LOC). Mantiene `response_model=IngresoReadForzado` (antes
  `IngresoRead`), `status_code=201`, KD-3 chain intacta.
- **`schemas/operacion.py`** — agregar `IngresoCreateForzado` (entrada con `forzado`),
  `IngresoReadForzado` (salida con `tipo_entrada`, `forzado_en_creacion`,
  `motivo_forzado`), 7 clases de error tipadas (`CupoNoConfiguradoError`,
  `MotivoForzadoRequeridoError`, `TarifaVigenteNoEncontradaError`,
  `PlacaFormatoInvalidoError`, `SubscripcionInactivaOVencidaError`,
  `IngresoActivoExistenteError`, `TipoVehiculoInvalidoError`). Mantiene
  `IngresoCreate`/`IngresoRead` como alias deprecated (sin breaking change).

## 6. Data Model

`modelo_datos_er.mmd` tablas `prod.ingreso` (577-596, `[L-E]`),
`prod.cantidad_vehiculos_sucursal` (428-446, `[V]`),
`prod.tipos_vehiculo` (87-104, `[V]`),
`prod.tarifas_sucursal` (406-426, `[V]`, post-F1.4 vigente_en),
`prod.subscripciones_cliente` `[V]`, `prod.subscripcion_vehiculos` `[V]`,
`prod.vehiculos` `[V]`, `prod.alerta` `[L-W]`, `prod.mv_ocupacion_diaria` (post-F1.5) —
**sin cambios de esquema**. La operación es puramente de lectura/inserción sobre
columnas existentes.

**Columnas leídas** (todas existentes, sin DDL):

| Tabla | Columna | Lectura |
|---|---|---|
| `prod.ingreso` | `uuid`, `uuid_sucursal`, `placa`, `uuid_tipo_vehiculo`, `uuid_subscripcion_cliente` | V8 EXISTS check, INSERT vía record_event |
| `prod.tipos_vehiculo` | `uuid`, `tipo`, `vigente_hasta`, `estado` | V4 vigente, regex → UUID lookup |
| `prod.cantidad_vehiculos_sucursal` | `uuid_sucursal`, `uuid_tipo_vehiculo`, `cantidad` | V1+V2 vía mv JOIN |
| `prod.mv_ocupacion_diaria` | `uuid_sucursal`, `uuid_tipo_vehiculo`, `activos` | V1+V2 count(*) |
| `prod.tarifas_sucursal` | `vigente_desde`, `vigente_hasta`, `estado` | V3 bi-temporal canónico F1.4 |
| `prod.subscripciones_cliente` | `fecha_vencimiento`, `estado`, `vigente_hasta` | V6 vigente |
| `prod.subscripcion_vehiculos` | `uuid_subscripcion`, `uuid_vehiculo` | V6 junction |
| `prod.vehiculos` | `placa`, `uuid` | V6 via placa |
| `prod.alerta` | `tipo_alerta`, `estado`, `datos_nuevos` | INSERT `capacidad_agotada_forzado` |

**Por qué ningún modelo se toca**: el handler validado opera sobre columnas existentes
(V5 cubre regex en el server; V8 EXISTS a `prod.ingreso`; V1+V2 a la MV post-F1.5).
**NO** se agrega columna `forzado`, `tipo_entrada`, `motivo` — DEC-SUC-21 veda
`tipo_entrada` columna; KD-FORZADO-01 veda columna `forzado`. El motivo se almacena
en `prod.alerta.datos_nuevos` (jsonb) cuando aplica.

**NO Alembic migration**. F1.6 es read-only sobre el esquema.

**NO sync catalog changes**. Las validaciones viven en `repo/*.py`; el catálogo de sync
no se ve afectado. Solo cambia la **cantidad de filas que pasan las validaciones** —
filas inválidas se rechazan con 422 antes del INSERT.

## 7. API Surface

| Path | Method | Cambio | Issuer / rol |
|---|---|---|---|
| `/api/v1/operacion/ingresos` | POST | Handler dedicado reemplazado in-place; response body gana `tipo_entrada`, `forzado_en_creacion`, `motivo_forzado` | `operador-`, `admin-` |

**Request signature**:

```python
async def create_ingreso(
    payload: IngresoCreateForzado,
    response: Response,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),
) -> IngresoReadForzado:
```

**Body `IngresoCreateForzado`**:

```python
class IngresoCreateForzado(_Base):
    model_config = ConfigDict(extra="forbid")
    uuid_sucursal: uuid_lib.UUID | None = None
    placa: str | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None  # server overrides via V5 regex
    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    fecha_ingreso: datetime | None = None
    observaciones: str | None = None
    forzado: bool = False  # NEW (D-HU-F1.6-5; validated against prefijo)
```

**Response `IngresoReadForzado`** (201):

```python
class IngresoReadForzado(_Base):
    model_config = ConfigDict(extra="forbid")
    # inherited from IngresoRead: uuid, created_at, created_by, sync_status,
    #   sync_timestamp, sync_attempts, uuid_sucursal, placa, uuid_tipo_vehiculo,
    #   uuid_subscripcion_cliente, fecha_ingreso, observaciones
    tipo_entrada: Literal["MENSUALIDAD", "ROTACION"]   # NEW (V9)
    forzado_en_creacion: bool = False                    # NEW
    motivo_forzado: str | None = None                    # NEW (KD-FORZADO-01)
```

**Errores tipados**:

| HTTP | Body | Cuándo | KD |
|---|---|---|---|
| 400 | `{"error":"missing_sucursal_context"}` | `uuid_sucursal` ausente y `ctx.sucursal_uuid is None` (admin- sin header) | KD-3 |
| 403 | `{"error":"tenant_scope_violation"}` | `operador-` con `uuid_sucursal != ctx.sucursal_uuid` | KD-3 |
| 403 | `{"error":"sucursal_not_permitted"}` | `admin-` con `uuid_sucursal` fuera de `claims["sucursales_permitidas"]` | KD-3 |
| 422 | `{"error":"placa_formato_invalido","formatos_aceptados":["ABC123","ABC12D"]}` | regex server-side no matchea | V5 |
| 422 | `{"error":"tipo_vehiculo_invalido"}` | UUID no existe o `vigente_hasta IS NOT NULL` | V4 |
| 422 | `{"error":"forzado_contradiccion"}` | `forzado=false` pero `observaciones` empieza con `[FORZADO:` | KD-FORZADO-01 |
| 422 | `{"error":"motivo_forzado_requerido"}` | `forzado=true` sin prefijo `[FORZADO: …]` | KD-FORZADO-01 |
| 422 | `{"error":"motivo_forzado_insuficiente","min_chars":10}` | motivo <10 chars tras prefijo | KD-FORZADO-01 |
| 422 | `{"error":"cupo_no_configurado","forzado_permitido":true}` | sin fila en `cantidad_vehiculos_sucursal(X, T)` | V1 |
| 422 | `{"error":"motivo_forzado_requerido","cupo_maximo":N,"activos":N}` | cupo agotado sin forzado | V2 |
| 422 | `{"error":"tarifa_vigente_no_encontrada"}` | sin fila vigente en `tarifas_sucursal(X, T)` | V3 |
| 422 | `{"error":"subscripcion_inactiva_o_vencida"}` | subscripción `fecha_vencimiento < NOW()` o `estado='inactivo'` | V6 |
| 409 | `{"error":"ingreso_activo_existente","uuid_ingreso_existente":"..."}` | ya hay ingreso activo para `(X, placa)` | V8 |
| 201 | `IngresoReadForzado` con `tipo_entrada`, `forzado_en_creacion`, `motivo_forzado` | happy path | — |

**Headers**: `Cache-Control: no-store` (alineado con F1.3/F1.5/F1.8 precedents).

**Sin cambios sobre**:

- `GET /api/v1/operacion/ingresos/{uuid}` (F1.5)
- `GET /api/v1/operacion/ingresos/{uuid}/estado` (F1.5)
- `GET /api/v1/operacion/ingresos` (F1.5 list)
- `GET /api/v1/operacion/ocupacion` (F1.5)
- `GET /api/v1/operacion/cotizar?uuid_ingreso` (F1.8)

**Requirements planificados** (escritos en `specs/operations/spec.md` por `sdd-spec`):

- `REQ-OPS-034` — handler `create_ingreso` aplica 9 validaciones server-side V1..V9 con
  KD-FORZADO-01 como única ruta de bypass.
- `REQ-OPS-035` — regex placa Colombia server-side (`^[A-Z]{3}[0-9]{3}$` Auto |
  `^[A-Z]{3}[0-9]{2}[A-Z]$` Moto); 422 con `formatos_aceptados`.
- `REQ-OPS-036` — `uuid_tipo_vehiculo` derivado de regex sobreescribe al del cliente
  (BR2 CU-01).
- `REQ-OPS-037` — KD-FORZADO-01: prefijo `[FORZADO: <motivo ≥10 chars>]` parseado de
  `observaciones`; flag `forzado` validado contra prefijo; 422 con 3 discriminadores
  (`forzado_contradiccion`, `motivo_forzado_requerido`, `motivo_forzado_insuficiente`).
- `REQ-OPS-038` — V1+V2 cupo via `mv_ocupacion_diaria` JOIN
  `cantidad_vehiculos_sucursal`; `cupo_no_configurado` con `forzado_permitido: true`;
  `motivo_forzado_requerido` con `cupo_maximo`/`activos`.
- `REQ-OPS-039` — V3 tarifa vigente bi-temporal canónico reusando
  `bitemporal_vigente_predicate` de F1.4; `tarifa_vigente_no_encontrada` 422.
- `REQ-OPS-040` — V6 subscripción vigente (`fecha_vencimiento >= NOW() AND estado='activo'
  AND vigente_hasta IS NULL`); `subscripcion_inactiva_o_vencida` 422.
- `REQ-OPS-041` — V8 no-duplicado activo (`EXISTS` en `prod.ingreso` con
  `NOT EXISTS salidas` + `NOT EXISTS anulaciones`); 409 con
  `uuid_ingreso_existente`; defensa in depth — sin lock pesimista.
- (Plus 8-9 implied requirements for V4 tipo vehiculo, V9 derivación `tipo_entrada`,
  alerta `capacidad_agotada_forzado`, KD-3 authz, AST walk ordering, AST walk no-write,
  defense in depth 4 layers — concrete IDs assigned by `sdd-spec`.)

## 8. Risks & Mitigations

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | MV `mv_ocupacion_diaria` con lag ≤10s (post-F1.5 worker); eventual consistency puede causar `activos < cupo_maximo` justo después de un INSERT, dejando entrar un vehículo "extra" antes del próximo refresh | Media | RIESGO-SUC-02 del corpus ya documenta el lag como riesgo vivo aceptado; KD-V4 NO lock pesimista; alerta operativa si `refresh_duration_s > refresh_interval_s`; cliente `OcupacionStrip` muestra el mismo dato con polling 10s — la divergencia es aceptable |
| **R2** | Alerta `capacidad_agotada_forzado` falsamente disparada si `forzado=true` y cupo está bien (ej: tarifa no vigente forzada por error) | Baja | D-HU-F1.6-9: alerta SOLO si V2 fue bypassed (`bypass_reason == "cupo_agotado"`); una por ingreso (uuid_ingreso la hace única) |
| **R3** | Regex hardcoded rompible si se cambian formatos de placa nacional (ej: nueva normativa 2027) | Baja | KD-V2 hardcoded para MVP; configurable en HU futura con cat tabla (HU-F-XX.X); constante a nivel de módulo `repo/placa.py` permite reemplazo en un solo lugar; tests parametrizados cubren los 6 casos actuales |
| **R4** | Subscripción cross-tenant → V6 rechaza (defense in depth). Si el sync no trajo la subscripción al branch (R22), V6 falla aunque la subscripción exista en cloud | Baja | Defense in depth intencional; `subscripcion_inactiva_o_vencida` 422 motiva al operador a walk-in con `forzado=true` y alerta; resuelve el bug "subscripción fantasma" antes que aceptar sin verificación |
| **R5** | Ingreso y alerta deben estar en misma transacción (un commit). Si el INSERT del ingreso tiene éxito y la alerta falla (FK, etc.), quedaría ingreso sin alerta | Baja | D-HU-F1.6-9: `record_event` + `insertar_alerta_forzado` en **misma transacción** (un solo `await session.commit()`); FK commit ordering garantiza que alerta solo se inserta si ingreso OK |
| **R6** | `extra='forbid'` rechaza campos extra — clientes desactualizados que manden `tipo_entrada` (columna inexistente en `prod.ingreso`) u otros campos viejos serán rechazados con 422 | Baja | Defense in depth: explícito en el schema; Pydantic devuelve 422 con lista de campos extra; cliente debe actualizar; documento en design.md |
| **R7** | Orden de validación estricto (D-HU-F1.6-11) puede ser alterado por dev futuro (ej: mover V8 antes de V2 causa que un duplicado con cupo agotado se reporte como duplicado, no como cupo) | Media | AST walk `tests/static/test_kd_forzado_in_handler.py` verifica orden literal de invocaciones (regex → tipo → KD-FORZADO → cupo → tarifa → sub → no-dup → INSERT); CI gate; documentado en source docstring |
| **R8** | Definición operacional de "ingreso activo" via `EXISTS` directo a `prod.ingreso` + `NOT EXISTS salidas/anulaciones` < 50ms p99 esperado (índice `(uuid_sucursal, placa, created_at)` post-F1.5) | Baja | V8 va directo a tablas (authoritative), NO a la MV (stale eventual); `prod.ingreso` < 100M filas en MVP; EXPLAIN ANALYZE en test de performance; documentado en design.md |
| **R9** | Subscripción vigente + vehículo no incluido en `subscripcion_vehiculos` → walk-in auditado (mensualidad sin vehículo registrado). Edge case que el corpus declara como "walk-in auditado" | Baja | V6 acepta la subscripción si `fecha_vencimiento >= NOW()` independientemente de `subscripcion_vehiculos`; el futuro F7 (salida) reconcilia con `cobrar=false` cuando hay match; walk-in auditado documentado |

## 9. Success Criteria

1. `pytest backend/tests/unit/test_operacion_ingresos_validaciones.py` verde — 8
   parametrized HTTP tests: T1 placa válida Auto, T2 placa inválida, T3 mensualidad,
   T4 rotación, T5 cupo agotado sin forzado, T6 cupo agotado con forzado + alerta,
   T7 ingreso activo existente 409, T8 orden de validación regex-antes-mensualidad
   (R7 invariante).
2. `pytest backend/tests/unit/test_operacion_ingresos_kd_forzado.py` verde — 4 tests:
   T1 prefijo válido, T2 sin prefijo, T3 motivo 9 chars, T4 forzado=false con prefijo
   (contradicción).
3. `pytest backend/tests/unit/test_repo_placa.py` verde — 6 regex tests: T1 ABC123→Auto,
   T2 ABC12D→Moto, T3 AB12→None, T4 lowercase→None, T5 4 dígitos→None, T6 con guión→None.
4. `pytest backend/tests/integration/test_ingreso_create_db.py` verde — 3 DB tests
   (`PARKOS_DOCKER_TEST=1`): T1 insert + alerta (single commit), T2 duplicado activo
   rechazado, T3 subscripción vencida 422.
5. `pytest backend/tests/static/test_no_write_after_insert.py` verde — 1 AST walk:
   `repo/ingreso.py::crear_ingreso_evento` rechaza `UPDATE|DELETE|TRUNCATE`.
6. `pytest backend/tests/static/test_kd_forzado_in_handler.py` verde — 1 AST walk:
   `create_ingreso` llama `validar_kd_forzado(...)` ANTES de V1+V2+V3+V6 (R7
   invariante, orden literal).
7. Defense in depth gate: cada capa (regex server-side, KD-FORZADO chain, alerta
   INSERT same-TX, AST walk ordering) tiene al menos un test que la rompe
   individualmente y verifica que las demás capas la contienen.
8. Transactional integrity gate: test integration verifica que si `insertar_alerta_forzado`
   falla, el INSERT del ingreso se hace rollback (no quedan filas huérfanas — R5).
9. KD-V8 issuer parity: test verifica que tanto `operador-` como `admin-` pueden
   emitir `forzado=true` y la alerta se inserta con `actor_uuid` correcto (no
   cross-tenant).
10. `IngresoReadForzado` carry-through: test verifica que `tipo_entrada`,
    `forzado_en_creacion`, `motivo_forzado` se devuelven en el 201, y que
    `tipo_entrada` **NO** aparece en `prod.ingreso` (DEC-SUC-21, query directa
    sobre la tabla).
11. Precedente intacto: `git diff api/v1/__init__.py api/v1/router_factory.py
    api/deps.py auth/tenancy.py models/* migrations/*` retorna vacío.
12. `ruff check`, `ruff format --check`, `mypy --strict` verde sobre los 9 archivos
    nuevos/modificados (4 nuevos + 3 modificados en backend + 6 test files).
13. Header `Cache-Control: no-store` presente en toda respuesta 2xx/4xx/5xx del
    endpoint (consistente con F1.3/F1.5/F1.8 precedents).
14. Defense in depth gate: `validate_kd_forzado` rechaza `forzado=false` con prefijo
    (`422 forzado_contradiccion`) — invariante explícita en KD-FORZADO-01
    (D-HU-F1.6-5).

## 10. Out of Scope (deferred)

1. **Workflow de anulación** (`prod.anulaciones` workflow para revertir ingreso
   post-creación). DEC-ANUL-01 delega a Fase 7+. `ingreso` nunca UPDATE post-creación;
   `repo/ingreso.py::crear_ingreso_evento` thin wrapper de `record_event`, sin UPDATE
   path. (KD-V5)
2. **`correlacion_id`** en el payload. DEC-IDEM-01 delega idempotencia al header
   `Idempotency-Key` (PR2 middleware). (KD-V6)
3. **Regex configurable** (catálogo, settings, JSON, BD). A-03 / KD-V2 hardcoded para
   MVP; configurable en HU futura con cat tabla. (R3)
4. **Lock pesimista** (`SELECT … FOR UPDATE/SHARE`) sobre `prod.ingreso` /
   `prod.salidas` / `prod.anulaciones` desde el endpoint. KD-V4 eventual consistency
   aceptable (RIESGO-SUC-02 del corpus). (D-HU-F1.6-3)
5. **Versionado de UI cliente** (Fase 2 frontend — `web_sucursal` debe desactivar
   `lib/validation/placa.ts` A-03 cuando este endpoint esté en producción). F1.6
   **NO** modifica el cliente; el cliente sigue mandando el body completo y el server
   lo acepta. La desactivación del cliente es cleanup post-archive.
6. **`CHECK constraint`** sobre `prod.ingreso.placa`. A-03 descarta CHECK rígida;
   bloquearía migración nacional futura.
7. **Endpoint `GET /operacion/ingresos/{uuid}/validar`** (preview sin insertar).
   Sale del scope: el handler hace insert o 422, sin preview.
8. **Alertas adicionales** (e.g. `placa_no_reconocida_forzado`, `subscripcion_sin_vehiculo`).
   Solo se inserta `capacidad_agotada_forzado` (R2 mitigation); otras alertas son
   operacionales y salen del scope de F1.6.
9. **Cleanup del cliente** (`web_sucursal/src/lib/validation/placa.ts` A-03).
   F1.6 entrega el server-side enforcement; el cleanup del cliente es post-archive.
10. **Migración nacional de formatos de placa** (e.g. Mercosur 2027). KD-V2 hardcoded
    para MVP; sale del scope.
11. **Permisos RBAC diferenciados para `forzado`** (e.g. "solo admin-"). KD-V8
    acepta ambos `operador-` y `admin-` para MVP; check dedicado en HU futura.
12. **Métricas / observabilidad del handler** (contador de `forzado=true` por día,
    latencia p99 de `create_ingreso`). Sale del scope; alineado con HU-F1.X de
    observabilidad (futuro).

## 11. Relevant Files

**Nuevos** (4 archivos backend + 6 test files):

- `backend/packages/parkos_core/src/parkos_core/repo/ingreso.py` (~180 LOC) — 8
  funciones de validación V1..V9 + KD-FORZADO-01 + `crear_ingreso_evento` thin wrapper
  de `record_event` + `insertar_alerta_forzado` re-export.
- `backend/packages/parkos_core/src/parkos_core/repo/placa.py` (~30 LOC) — regex
  hardcoded (`FORMATO_AUTO`, `FORMATO_MOTO`) + `detectar_tipo_vehiculo(placa) -> UUID |
  None` con lazy lookup `tipos_vehiculo`.
- `backend/packages/parkos_core/src/parkos_core/repo/subscripcion_activa.py` (~50 LOC) —
  extrae `resolve_active_subscription_for_exit` (post-PR5) + check
  `fecha_vencimiento >= NOW()`; usado por V6 y reutilizado por F7.
- `backend/packages/parkos_core/src/parkos_core/repo/alerta.py` (~60 LOC) — helper puro
  `insertar_alerta_forzado` con `tipo_alerta='capacidad_agotada_forzado'`,
  `estado='abierta'`, motivo en `datos_nuevos` (jsonb).
- `backend/tests/unit/test_operacion_ingresos_validaciones.py` (~400 LOC, 8 parametrized
  HTTP tests) — T1..T8 cubriendo happy paths + cada validación 422 + orden (R7).
- `backend/tests/unit/test_operacion_ingresos_kd_forzado.py` (~150 LOC, 4 tests) — T1
  prefijo válido, T2 sin prefijo, T3 motivo 9 chars, T4 forzado=false con prefijo.
- `backend/tests/unit/test_repo_placa.py` (~80 LOC, 6 regex tests) — T1..T6 cubriendo
  los 6 formatos de placa.
- `backend/tests/integration/test_ingreso_create_db.py` (~250 LOC, 3 DB tests con
  `PARKOS_DOCKER_TEST=1`) — T1 insert + alerta (same TX), T2 duplicado activo
  rechazado, T3 subscripción vencida.
- `backend/tests/static/test_no_write_after_insert.py` (~100 LOC, 1 AST walk) —
  `repo/ingreso.py::crear_ingreso_evento` rechaza `UPDATE|DELETE|TRUNCATE`.
- `backend/tests/static/test_kd_forzado_in_handler.py` (~80 LOC, 1 AST walk) — orden
  literal de invocaciones en `create_ingreso` (regex → tipo → KD-FORZADO → cupo →
  tarifa → sub → no-dup → INSERT).

**Modificados** (4 archivos backend):

- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (replace
  `create_ingreso` líneas 92-114 → ~232 LOC) — handler dedicado con las 9 validaciones
  + KD-FORZADO-01 + derivación `tipo_entrada`.
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (+80 LOC) —
  agregar `IngresoCreateForzado` (entrada con `forzado`), `IngresoReadForzado` (salida
  con `tipo_entrada`, `forzado_en_creacion`, `motivo_forzado`), 7 clases de error
  tipadas.
- `backend/packages/parkos_core/src/parkos_core/repo/ocupacion.py` (+40 LOC) — agregar
  `validar_cupo_disponible(...)` reusando `get_ocupacion_puros_activos` (post-F1.5).
- `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (+30 LOC) —
  agregar `validar_tarifa_vigente(...)` reusando `bitemporal_vigente_predicate`
  (post-F1.4).
- `openspec/specs/operations/spec.md` — agregar REQ-OPS-034..041 (8 requirements) +
  entrada en `## Modified Capabilities`.

**Archivos NO tocados (deliberado)**:

- `api/v1/__init__.py` (router ya montado en línea 143).
- `api/v1/router_factory.py` (`make_router` F1.1 commit `f7cb37a`, no se usa en
  `/operacion`).
- `api/deps.py` (centraliza `get_tenant_ctx` + `requires_issuer`, se reusa tal cual).
- `auth/tenancy.py` (KD-3 reusa los errores tipados ya definidos en líneas 60-65 y
  115-131).
- `models/L_E/ingreso.py`, `models/V/cantidad_vehiculos_sucursal.py`,
  `models/V/tipos_vehiculo.py`, `models/V/tarifas_sucursal.py`,
  `models/V/subscripciones_cliente.py`, `models/V/subscripcion_vehiculos.py`,
  `models/V/vehiculos.py`, `models/L_W/alerta.py` (sin cambios de esquema, solo
  lectura).
- `migrations/*` (sin Alembic migration; F1.6 es read-only sobre el esquema).
- `repo/event.py` (`record_event` se reusa tal cual desde F1.5/PR5; el thin wrapper
  `crear_ingreso_evento` solo agrega logging).
- `repo/cotizacion.py` (helper F1.8, semánticamente reusable pero el patrón se aplica
  por separado a V3 tarifa en `repo/tarifas_vigencia.py`).
- `web_sucursal/src/lib/validation/placa.ts` (A-03 cliente; cleanup post-archive).

## 12. Open Questions

**Ninguna abierta**. Las 9 KD (KD-V1..KD-V9) + KD-FORZADO-01 están recomendadas en la
exploration con fecha 2026-09-14 y se adoptan sin disputa. Las 10 preguntas abiertas de
`exploration.md §14` quedan resueltas en este proposal vía adopción de KD:

- **OQ-1 (KD-V1 código 422)** — RESUELTO a favor de 422 (validación semántica,
  consistente con F1.5 `tarifa_no_vigente` / F1.8). Decisión D-HU-F1.6-10.
- **OQ-2 (KD-V2 regex hardcoded)** — RESUELTO a favor de hardcoded para MVP en
  `repo/placa.py`. Decisión D-HU-F1.6-4. Configurable en HU futura con cat tabla.
- **OQ-3 (KD-V4 eventual consistency)** — RESUELTO a favor de aceptar lag 10s vía MV
  post-F1.5; NO lock pesimista. Decisión D-HU-F1.6-3. RIESGO-SUC-02 del corpus ya
  documenta el lag como riesgo vivo aceptado.
- **OQ-4 (KD-V5 anulación out of scope)** — RESUELTO a favor de out of scope; DEC-ANUL-01
  delega a Fase 7+. Decisión documentada en `§3.2 Non-Goals` y `§10 Out of Scope`.
- **OQ-5 (KD-V6 no `correlacion_id`)** — RESUELTO a favor de NO agregar `correlacion_id`;
  idempotencia via header `Idempotency-Key` (PR2 middleware intacto). Decisión
  D-HU-F1.6-12.
- **OQ-6 (KD-V8 issuer parity para forzado)** — RESUELTO a favor de aceptar tanto
  `operador-` como `admin-` para `forzado=true`. Decisión D-HU-F1.6-13. RBAC dedicado en
  HU futura.
- **OQ-7 (Orden exacto de validación)** — RESUELTO a favor del orden D-HU-F1.6-11:
  KD-3 → V5 regex → V4 tipo → KD-FORZADO-01 → V1+V2 cupo → V3 tarifa → V6 sub → V8
  no-dup → INSERT + alerta (same TX) → V9 derivar tipo_entrada → 201. AST walk
  `tests/static/test_kd_forzado_in_handler.py` verifica el orden literal (R7 invariante).
- **OQ-8 (`uuid_tipo_vehiculo` sobreescrito por server)** — RESUELTO a favor de
  sobreescribir si no concuerda con regex derivado (BR2 CU-01, defense in depth contra
  cliente desactualizado). Decisión D-HU-F1.6-6.
- **OQ-9 (Default `uuid_sucursal`)** — RESUELTO a favor de `payload.uuid_sucursal or
  ctx.sucursal_uuid`, y si ambos None → `400 missing_sucursal_context`. Decisión
  documentada en architecture §4 (step 1).
- **OQ-10 (Una alerta por ingreso forzado)** — RESUELTO a favor de exactamente una
  alerta por ingreso forzado con `uuid_ingreso` como unique key; insertada en **misma
  transacción** que el INSERT del ingreso (un solo `commit()`). Decisión D-HU-F1.6-9 +
  R5 mitigación (mismo commit FK ordering).

Si durante `sdd-design` surge evidencia técnica fuerte para revisar alguna KD (ej:
medición de EXPLAIN ANALYZE muestra V8 > 50ms en producción simulada con 100M filas),
se reabre en `design.md` con evidencia. Caso base: el plan original está completo y es
ejecutable tal cual, con 260 LOC budget (plan.md línea 787) y defense in depth de 4
capas (D-HU-F1.6-7).

---

**Proposal Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`.
**Adopted KDs**: KD-V1, KD-V2, KD-V3, KD-V4, KD-V5, KD-V6, KD-V7, KD-V8, KD-V9,
KD-FORZADO-01 (10 KDs, all from explore §12).
**Precedents mirrored**: F1.5 (REQ-OPS-030..033, KD chain, MV pattern),
F1.4 (REQ-OPS-017..021, bi-temporal predicate), F1.3 (REQ-OPS-026..029, partial unique
index + AST walk + custom handler before factory), F1.8 (REQ-OPS-022..025, AST walk
read-only).
**Commits future**: conventional commits only, no AI attribution.
**PR target**: `origin/dev` from `feat/fase-1-prerequisites-backend`.
