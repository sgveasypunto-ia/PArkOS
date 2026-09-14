# Exploration: hu-f1-8-cotizar

> **Change**: `hu-f1-8-cotizar`
> **Phase**: explore (sdd-explore)
> **HU**: HU-F1.8 — Function `calcular_cotizacion` + `GET /operacion/cotizar`
> **Date**: 2026-09-14
> **Inputs read**:
> `plan.md` (HU-F1.8 section lines 845–887, A-02 adaptation line 453, GAP-BE-09 contract lines 7423–7446, dependencia chain line 7461, riesgos vivos line 51),
> `modelo_datos_er.mmd` (`ingreso` 577–596, `tarifas_sucursal` 406–426, `impuestos` 187–207, `subscripciones_cliente` 496–518, `subscripcion_vehiculos` 538–557, `vehiculos` 519–537, `salidas` 761–777, `tipos_vehiculo` 87–104, `tipo_tarifa` 128–144, `sucursal` 341–365, `cantidad_vehiculos_sucursal` 428–448),
> `openspec/changes/fase-1-prerequisites-backend/prompts/TODO-fase-1.md` (riesgo vivo `impuestos.IVA` línea 51),
> `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/exploration.md` (plantilla canónica),
> `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (precedente `resolve_active_subscription_for_exit` líneas 215–277, router `/operacion` con 5 endpoints),
> `backend/packages/parkos_core/src/parkos_core/api/v1/__init__.py:133-148` (`r.include_router(operacion.router)`),
> `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (helper HU-F1.4),
> `backend/packages/parkos_core/src/parkos_core/models/L_E/ingreso.py`,
> `backend/packages/parkos_core/src/parkos_core/models/V/tarifas_sucursal.py`,
> `backend/packages/parkos_core/src/parkos_core/models/V/impuestos.py`,
> `backend/packages/parkos_core/src/parkos_core/models/V/subscripciones_cliente.py`,
> `backend/packages/parkos_core/src/parkos_core/schemas/impuestos.py`,
> `backend/packages/parkos_core/src/parkos_core/schemas/tipo_tarifa.py`,
> `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py:266-280,2357-2366` (definición + triggers; sin siembra de fila IVA).

## Contexto y scope

HU-F1.8 implementa la cotización server-side de una salida. Es el equivalente de "calcular el recibo antes de pagar": dado un `uuid_ingreso`, devuelve el desglose fiscal (`subtotal`, `iva`, `total`, `tiempo_minutos`) y la vigencia de 15 minutos del cálculo (para que HU-F1.7 `POST /operacion/salidas` pueda validar que la cotización referenciada no expiró — `cotizacion_expirada` 410). Es server-side e idempotente mientras la tarifa no cambie (DEC-SUC-12, línea 427 plan.md).

El contrato consolidado vive en `plan.md` Parte IV §1.8 GAP-BE-09 (líneas 7423–7446):

- Fórmula (DEC-SUC-24, literal CU-02 AC7): `iva = total_a_pagar * porcentaje_impuesto`; `subtotal = total_a_pagar - iva`.
- AC3: si `valor_plena > 0` y `tiempo >= tiempo_tar_plena`, cobrar `valor_plena`; en otro caso, `total_a_pagar = valor * Math.ceil(tiempo)`.
- A-02 (línea 453): `tiempo_tar_plena = (valor_plena / valor) * unidad_minutos`. PROBLEMA ABIERTO: `tipo_tarifa.tipo` es sólo un string (`hora` | `fraccion` | `plena` | `nocturna`); no hay columna `unidad_minutos` en el ER ni en el ORM (`models/V/tipo_tarifa.py`, `schemas/tipo_tarifa.py`). RESUELTO en design como KD-2: hardcoded `CASE` en PL/pgSQL.
- AC4 mensualidad: si la placa tiene `subscripciones_cliente` vigente, responder `{cobrar:false, motivo:'mensualidad_vigente'}`. Reutiliza `resolve_active_subscription_for_exit(placa, uuid_sucursal)`.
- AC5 iva_no_configurado: si no hay fila de `impuestos` vigente con `nombre='IVA'`, responder `500 {"error":"iva_no_configurado"}`. NO se calcula sin IVA. **Bloqueante crítico KD-IVA**: la siembra la hace HU-F14.2 Parte II. Apply NO siembra.

El change crea 1 endpoint nuevo (`GET /operacion/cotizar`), 1 función PL/pgSQL nueva (`calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb`), 1 helper Python (thin wrapper), 1 schema Pydantic de salida, y 1 migración Alembic.

## Tablas / columnas afectadas (con línea exacta del ER)

| Tabla | Tipo (ER) | Línea | Rol en HU-F1.8 | Lectura/Escritura |
|---|---|---|---|---|
| `ingreso` | `[L-E]` | 577–596 | `uuid_sucursal`, `placa`, `uuid_tipo_vehiculo`, `uuid_subscripcion_cliente`, `fecha_ingreso` | SELECT |
| `tarifas_sucursal` | `[V]` | 406–426 | `valor`/`valor_plena` Numeric(18,4), FKs, bi-temporal | SELECT con predicado bi-temporal canónico + KD-1 lock pesimista FOR SHARE |
| `impuestos` | `[V]` | 187–207 | `nombre='IVA'`, `porcentaje`, bi-temporal | SELECT con predicado bi-temporal |
| `subscripciones_cliente` | `[V]` | 496–518 | Join para detectar mensualidad vigente | SELECT (delega al helper existente) |
| `subscripcion_vehiculos` | `[V]` | 538–557 | Junction suscripción-vehículos | SELECT (join ya implementado) |
| `vehiculos` | `[V]` | 519–537 | `placa`, `vigente_hasta IS NULL` | SELECT (join ya implementado) |
| `salidas` | `[A]` | 761–777 | Validar que ingreso sigue activo (no `cerrado`) | SELECT (existencia) |

**Tablas que NO existen en el ER pero el prompt menciona** (verificado, 0 matches):
- `tarifas_sucursal_extras` — NO MATCH. La tarifa vigente se resuelve sólo con `tarifas_sucursal` + `bitemporal_vigente_predicate`.
- `servicios_extras` — NO MATCH. `costos_servicios` existe (líneas 230–249) pero es para cargos facturables, fuera de scope F1.8.
- `servicios` — NO MATCH como tabla independiente.
- `tipo_vehiculo` — el nombre real es **`tipos_vehiculo`** (plural, línea 87).
- `categorias_vehiculo` — NO MATCH.

**Sembrado de `impuestos.IVA`**: las migraciones 0001–0021 NO insertan ninguna fila en `prod.impuestos` (grep `impuestos.*INSERT|INSERT INTO prod.impuestos|nombre.*IVA` → 0 matches). Triggers existen (líneas 2357–2366), tabla creada (líneas 266–280), pero la fila debe sembrarse en runtime vía `POST /catalogos/impuestos`. Estado: `ivasembrado: no`. **KD-IVA**: bloqueante para despliegue, fuera de scope de apply.

## Endpoints existentes en `/operacion`

| Path | Method | Estado |
|---|---|---|
| `POST /operacion/ingresos` | POST | Existe ([L-E] insert-only) |
| `GET /operacion/ingresos/{uuid}` | GET | Existe |
| `GET /operacion/ingresos/{uuid}/estado` | GET | Existe (deriva abierto/cerrado/anulada) |
| `GET /operacion/ingresos` | GET | Existe con `uuid_sucursal`, `placa`, `limit` |
| `GET /operacion/cotizar` | GET | **NO EXISTE** — nuevo (F1.8) |
| `POST /operacion/salidas` | POST | **NO EXISTE** — depende de HU-F1.7 (no empezada) |

Router: `api/v1/__init__.py:143` → `r.include_router(operacion.router)` sin guards branch/cloud. Issuer dep: `_ingreso_issuer_dep = requires_issuer("operador-", "admin-")` (línea 54). NO existe `make_router` para `/operacion` — es `APIRouter` custom; HU-F1.8 sigue el mismo patrón con `@router.get("/cotizar", ...)`.

## Archivos a tocar (preliminar)

| Archivo | Acción | Por qué |
|---|---|---|
| `backend/packages/parkos_core/migrations/versions/0022_create_calcular_cotizacion.py` | crear | Migración Alembic con función PL/pgSQL `prod.calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb` |
| `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` | modificar | Agregar `GET /operacion/cotizar` handler (mismo patrón raw SQL que `get_ingreso_estado` línea 152) |
| `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` | modificar | Agregar `CotizarResponse` (discriminador `cobrar: bool`) |
| `backend/packages/parkos_core/src/parkos_core/repo/cotizacion.py` | crear | Helper Python `cotizar_ingreso(session, *, uuid_ingreso)` con errores tipados |
| `backend/tests/unit/test_calcular_cotizacion.py` | crear | Escenarios plan.md + casos de borde |
| `backend/tests/integration/test_calcular_cotizacion_db.py` | crear | DB-backed con siembra real IVA+tarifa+ingreso |
| `openspec/specs/operations/spec.md` | modificar | REQ-OPS-022..025 + Modified Capabilities |
| `openspec/changes/hu-f1-8-cotizar/{proposal,tasks,design,exploration}.md` + `specs/operational/spec.md` | crear | Change folder (5 archivos) |

**Archivos NO tocados (deliberado)**: `repo/tarifas_vigencia.py` (helper F1.4 se reusa semánticamente pero NO se llama desde Python — la función PL/pgSQL hace TODO server-side para garantizar atomicidad transaccional), `api/v1/empresa.py`, `router_factory.py`, `models/*`.

## Dependencias previas

| Commit | HU | Estado | Impacto |
|---|---|---|---|
| `de4d2fc` | HU-F1.4 (`vigente_en` en `tarifas_sucursal`) | merged | Reusable: predicado bi-temporal canónico ya verificado. La PL/pgSQL replica la fórmula; KD de design: sincronizar manualmente si cambia |
| `535676d` | HU-F1.2 (cookie + `/auth/me`) | merged | Sin impacto directo |
| `f7cb37a` | HU-F1.1 GAP-BE-02 (`make_router` estable) | merged | NO se toca |

**Precondiciones runtime (NO commits)**:
1. `impuestos.IVA` sembrado — **estado: NO** (ver §Tablas). CRÍTICO (KD-IVA).
2. `tipos_vehiculo` sembrado — asumido por HU de catálogo previa.
3. `tarifas_sucursal` sembrado para la combinación — estado unknown. Si no, KD-3: nuevo error tipado `404 tarifa_no_vigente`.

## Supuestos detectados

1. **Función vive en PL/pgSQL** — RESUELTO (plan.md línea 885).
2. **Path `GET /operacion/cotizar?uuid_ingreso=X`** — RESUELTO (plan.md línea 861).
3. **`ingreso_no_encontrado`** — RESUELTO a 404, cubre "no existe" + "ya tiene salida no anulada" (plan.md línea 877).
4. **Lock pesimista sobre `tarifas_sucursal`** — RESUELTO en design como KD-1: `SELECT … FOR SHARE` dentro de PL/pgSQL; F1.7 también debe tomarlo.
5. **Origen de `unidad_minutos` (A-02)** — RESUELTO en design como KD-2: hardcoded `CASE tipo_tarifa.tipo WHEN 'fraccion' THEN 15 WHEN 'hora' THEN 60 WHEN 'nocturna' THEN 720 ELSE 1 END` en PL/pgSQL.
6. **`fecha_calculo`** — RESUELTO a `NOW()` dentro de PL/pgSQL (no query param).
7. **`vigente_hasta` respuesta** — RESUELTO a `NOW() + 15 min` (vigencia de cotización, no de tarifa).

## Conflictos detectados

1. `plan.md` deja libre path — NO (fija `GET /operacion/cotizar`).
2. F1.7 ya empezada — NO (TODO-fase-1.md `[ ]` línea 24; grep `POST.*salidas` 0 matches en `backend/`).
3. `make_router` para `/operacion` — NO (es `APIRouter` custom en `operacion.py:52`).
4. Coexistencia con F1.4 — OK. Si cambia el predicado en F1.4, sincronizar manualmente constante SQL de F1.8.
5. `infra/scripts/seed_catalogs.py` sirve para sembrar IVA (1 row con JSON body) — fuera de scope F1.8, pero documentar la receta en design.

## Riesgos vivos identificados

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | `impuestos.IVA` NO sembrado — bloqueante F1.7/F1.9 | **CRÍTICA** | KD-IVA: recipe exacta en design; sub-agente apply NO siembra. Housekeeping pre-F1.8 responsabilidad HU-F14.2 Parte II. |
| **R2** | Redondeo monetario — `Numeric(18,4)` en storage, salida debe ser `ROUND(..., 2)` | Media | PL/pgSQL con `numeric`, `ROUND(total, 2)` en salida |
| **R3** | Atomicidad — sin lock, tarifa podría cerrar entre cotizar y POST /salidas | Media | KD-1: `SELECT … FOR SHARE` en PL/pgSQL; F1.7 replicará |
| **R4** | Sin tarifa vigente para la combinación — error code no especificado | Media | KD-3: nuevo `404 tarifa_no_vigente` tipado |
| **R5** | Redondeo minutos `Math.ceil` — caso 90s→2min, 59s→1min | Baja | Test literal AC3 |
| **R6** | `fecha_ingreso` tz — columna `DateTime(timezone=False)` sembrada con `NOW()` UTC | Baja | Verificar que F1.6 normalize tz→UTC |
| **R7** | PL/pgSQL read-only — futuro dev podría agregar INSERT y romper idempotencia | Baja | AST check `test_no_write_in_calcular_cotizacion.py` |
| **R8** | Cache-Control en respuesta — proxy podría servir cotización expirada | Baja | `Cache-Control: no-store` en handler |

## Resumen ejecutivo

HU-F1.8 implementa `calcular_cotizacion` (función PL/pgSQL `RETURNS jsonb` en migración nueva) + `GET /operacion/cotizar?uuid_ingreso=X` (handler FastAPI sobre el `APIRouter` custom existente, sin `make_router`). Tamaño estimado 200 LOC (plan.md:882). Fórmula literal: `iva = total * porcentaje_impuesto`; `subtotal = total - iva`; `total = valor_plena` si `tiempo >= tiempo_tar_plena` (A-02 con KD-2 hardcoded CASE), si no `valor * Math.ceil(tiempo)`. Mensualidad vigente → `{cobrar:false, motivo:'mensualidad_vigente'}` reusando `resolve_active_subscription_for_exit` (`operacion.py:215-277`). Error de IVA → `500 iva_no_configurado`. 4 KD: KD-1 lock pesimista FOR SHARE, KD-2 unidad_minutos hardcoded CASE, KD-3 error 404 tarifa_no_vigente, KD-IVA siembra fuera de scope. 8 archivos a tocar (2 nuevos, 6 modify).

**Bloqueante crítico KD-IVA**: `ivasembrado: no` — toda cotización devuelve 500 hasta que se siembre `nombre='IVA'`. Apply NO siembra (out of scope, HU-F14.2 Parte II). Design declara la siembra como bloqueante para despliegue y da la receta exacta.