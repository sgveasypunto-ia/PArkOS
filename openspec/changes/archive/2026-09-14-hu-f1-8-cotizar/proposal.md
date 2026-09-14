# Proposal: HU-F1.8 — calcular_cotizacion + GET /operacion/cotizar

> **Change**: `hu-f1-8-cotizar`
> **Phase**: propose (sdd-propose)
> **Status**: ready for `sdd-spec` + `sdd-design` + `sdd-tasks`
> **HU ID**: HU-F1.8 (Fase-1 prerequisites — backend)
> **Inputs**: `openspec/changes/hu-f1-8-cotizar/exploration.md` (this change), `plan.md`
> (HU-F1.8 lines 845–887, GAP-BE-09 contract lines 7423–7446, A-02 adaptation line 453,
> dependencia chain line 7461), `modelo_datos_er.mmd` (`ingreso` 577–596, `tarifas_sucursal`
> 406–426, `impuestos` 187–207, `subscripciones_cliente` 496–518, `salidas` 761–777),
> `openspec/changes/archive/2026-09-14-hu-f1-4-tarifas-vigente/` (precedente bi-temporal
> reusable, commit `de4d2fc`), `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py`
> (`resolve_active_subscription_for_exit` 215–277, `APIRouter` custom línea 52).

## 1. Why

`POST /operacion/salidas` (HU-F1.7) necesita calcular el recibo antes de cobrar; `POST
/facturacion/...` (HU-F1.9) necesita el desglose fiscal (`subtotal`, `iva`, `total`). Ninguno
de los dos puede confiar en una cotización client-side: el precio cambia por sede, tipo de
vehículo, modalidad, hora de salida y tarifa programada. Sin un endpoint server-side, el
cliente replicaría la fórmula y rompería atomicidad — un cambio de tarifa entre "cotizar" y
"salir" generaría cobros inconsistentes (riesgo R3 del explore).

`plan.md` Parte IV §1.8 GAP-BE-09 (7423–7446) fija el contrato: `GET
/api/v1/operacion/cotizar?uuid_ingreso={uuid}` devuelve `{cobrar, motivo?, subtotal?, iva?,
total?, tiempo_minutos?, tarifa_uuid?, vigente_hasta?}`. La vigencia de **15 minutos** permite
que HU-F1.7 valide `cotizacion_expirada` (410) sin reconsultar la DB. Esta HU aterriza la
función `calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb` en PL/pgSQL — única forma
de garantizar atomicidad tarifaria entre cotización y salida.

## 2. Decision Summary

| # | Decisión | Rationale |
|---|---|---|
| **D-HU-F1.8-1 (KD-1)** | Lock pesimista `SELECT … FOR SHARE` sobre `tarifas_sucursal` dentro de la PL/pgSQL | Atomicidad cotización → POST /salidas. HU-F1.7 replicará el mismo lock para cerrar la ventana. Previene que un `vigente_hasta` se setee entre cotización y cobro (R3) |
| **D-HU-F1.8-2 (KD-2)** | `unidad_minutos` (A-02) hardcoded `CASE tipo_tarifa.tipo WHEN 'fraccion' THEN 15 WHEN 'hora' THEN 60 WHEN 'nocturna' THEN 720 ELSE 1 END` dentro de la PL/pgSQL; cero columnas al ER | No agregar columna al ER canónico (`unidad_minutos` no existe en `modelo_datos_er.mmd`); encapsular en la función evita migración colateral; `tipo_tarifa.tipo` ya es la fuente de verdad declarada en el ER |
| **D-HU-F1.8-3 (KD-3)** | Nuevo error tipado `404 tarifa_no_vigente` cuando no hay fila `tarifas_sucursal` para la combinación en `t=NOW()` | Distinguir "sin tarifa" de "ingreso inválido" (404 vs 404 con códigos distintos); contrato GAP-BE-09 sin este código era ambiguo |
| **D-HU-F1.8-4 (KD-IVA)** | Siembra de `impuestos.IVA` fuera de scope de F1.8 (HU-F14.2 Parte II). `design.md` declarará bloqueante para despliegue con receta exacta (`infra/scripts/seed_catalogs.py` o `POST /catalogos/impuestos`) | KD-IVA confirmado por usuario 2026-09-14. Apply NO siembra. Toda cotización devuelve 500 `iva_no_configurado` hasta que se siembre — esto es esperado y testeable |
| **D-HU-F1.8-5** | Función PL/pgSQL `calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb` en migración Alembic nueva `0022`; grant `EXECUTE` a `parkos_app` | Server-side para atomicidad; jsonb para contrato flexible sin schema fijo en DB; migración Alembic coherente con el patrón del repo (0001–0021) |
| **D-HU-F1.8-6** | Handler `GET /operacion/cotizar?uuid_ingreso=X` sobre el `APIRouter` custom existente (`operacion.py:52`); NO `make_router` | `operacion.py` no usa factory; `resolve_active_subscription_for_exit` es el precedente raw-SQL dentro de la misma superficie |
| **D-HU-F1.8-7** | Helper Python thin wrapper `repo/cotizacion.py::cotizar_ingreso(session, *, uuid_ingreso) -> dict` que llama la función y mapea errores tipados a `HTTPException` | Cero lógica de cálculo en Python (toda la fórmula vive en PL/pgSQL); testeable sin HTTP; consistente con el patrón de `resolve_active_subscription_for_exit` |

## 3. Goals & Non-Goals

### 3.1 Goals

1. Exponer `GET /api/v1/operacion/cotizar?uuid_ingreso={uuid}` con respuesta conforme al
   contrato GAP-BE-09 (8 campos, discriminador `cobrar`).
2. Garantizar atomicidad tarifaria mediante `SELECT … FOR SHARE` sobre `tarifas_sucursal`
   dentro de la función PL/pgSQL.
3. Distinguir tres modos de respuesta: mensualidad vigente (`cobrar:false`), tarifa
   aplicable con desglose (`cobrar:true`), y errores tipados (`ingreso_no_encontrado`,
   `tarifa_no_vigente`, `iva_no_configurado`).
4. Implementar la fórmula literal de CU-02 AC7 (`iva = total * porcentaje_impuesto`,
   `subtotal = total - iva`) y la regla AC3 (`total = valor_plena` si
   `tiempo >= tiempo_tar_plena`, si no `valor * ceil(tiempo)`).
5. Marcar la cotización con `vigente_hasta = NOW() + 15 min` para que HU-F1.7 valide
   expiración sin reconsultar la DB.
6. Reutilizar `resolve_active_subscription_for_exit` (precedente HU-F1.4) para detectar
   mensualidad vigente sin duplicar lógica.
7. Mantener el router `/operacion` raw-SQL y la dependencia `_ingreso_issuer_dep`
   (`operador-`, `admin-`) sin modificación.

### 3.2 Non-Goals

1. NO se siembra `impuestos.IVA` — HU-F14.2 Parte II (KD-IVA, D-HU-F1.8-4).
2. NO se crea path nuevo `POST /operacion/cotizar` — sólo GET (idempotente).
3. NO se modifica `make_router` (`api/v1/router_factory.py`) — `/operacion` no lo usa.
4. NO se agrega columna `unidad_minutos` al ER — encapsulado en PL/pgSQL (KD-2).
5. NO se reimplementa `resolve_active_subscription_for_exit` — se reusa tal cual.
6. NO se introduce lock sobre `impuestos` ni `subscripciones_cliente` — sólo
   `tarifas_sucursal` (KD-1).
7. NO se crea tabla `tarifas_sucursal_extras`, `servicios_extras`, `categorias_vehiculo`
   ni `servicios` (verificado: 0 matches en el ER).
8. NO se modifica `repo/tarifas_vigencia.py` (helper F1.4) — su semántica bi-temporal es
   idéntica pero NO se llama desde Python; la PL/pgSQL hace todo server-side.
9. NO se crean índices nuevos — el `count(*)` de IVA y el lock sobre PK son eficientes al
   volumen esperado.

## 4. Architecture Overview

```
HTTPS GET /api/v1/operacion/cotizar?uuid_ingreso={uuid}
        │
        │  requires_issuer("operador-", "admin-")   Cache-Control: no-store
        ▼
┌────────────────────────────────────────────────────────────────────┐
│ api/v1/operacion.py  (APIRouter custom, línea 52)                  │
│ @router.get("/cotizar")  (NUEVO handler cotizar_ingreso)           │
│                                                                    │
│ 1. validar uuid_ingreso (Pydantic UUID4)                           │
│ 2. repo/cotizacion.py::cotizar_ingreso(session, uuid_ingreso)      │
│      │                                                             │
│      │  SELECT prod.calcular_cotizacion(:uuid) AS payload          │
│      │                                                             │
│      ▼                                                             │
│ 3. mapear error jsonb → HTTPException tipado                      │
│      - {error:"ingreso_no_encontrado"}     → 404                   │
│      - {error:"tarifa_no_vigente"}         → 404                   │
│      - {error:"iva_no_configurado"}        → 500                   │
│      - {cobrar:false, motivo:...}          → 200 (CotizarResponse) │
│      - {cobrar:true, subtotal, iva, ...}   → 200 (CotizarResponse) │
│      └─────────────────────────────────────────────────────────►   │
└────────────────────────────────────────────────────────────────────┘
        │
        ▼ PL/pgSQL  prod.calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb
┌────────────────────────────────────────────────────────────────────┐
│ BEGIN;                                                              │
│   a) SELECT uuid_sucursal, placa, uuid_tipo_vehiculo,              │
│            uuid_subscripcion_cliente, fecha_ingreso                │
│      FROM   prod.ingreso                                           │
│      WHERE  uuid = :p AND NOT EXISTS (                            │
│              SELECT 1 FROM prod.salidas s                          │
│              WHERE s.uuid_ingreso = i.uuid AND s.estado!='anulada')│
│      → si 0 filas → jsonb_build_object('error','ingreso_no_encontrado')│
│                                                                    │
│   b) reusar lógica de resolve_active_subscription_for_exit         │
│      (portar a SQL inline; o delegar a una sub-función SQL previa) │
│      → si mensualidad vigente →                                    │
│        jsonb_build_object('cobrar',false,'motivo','mensualidad_vigente')│
│                                                                    │
│   c) SELECT uuid, valor, valor_plena                               │
│      FROM   prod.tarifas_sucursal                                  │
│      WHERE  uuid_sucursal      = :s                                │
│        AND  uuid_tipo_vehiculo = :tv                               │
│        AND  uuid_tipo_tarifa   = ...                               │
│        AND  vigente_desde <= NOW()                                 │
│        AND  (vigente_hasta IS NULL OR vigente_hasta > NOW())        │
│        AND  estado='activo'                                        │
│      FOR SHARE      ◄── KD-1 lock pesimista                        │
│      → si 0 filas → jsonb_build_object('error','tarifa_no_vigente')│
│                                                                    │
│   d) SELECT porcentaje                                              │
│      FROM   prod.impuestos                                         │
│      WHERE  nombre='IVA' AND vigente_desde<=NOW()                  │
│        AND  (vigente_hasta IS NULL OR vigente_hasta > NOW())        │
│        AND  estado='activo'                                        │
│      LIMIT 1                                                       │
│      → si 0 filas → jsonb_build_object('error','iva_no_configurado')│
│                                                                    │
│   e) tiempo_minutos := CEIL(EXTRACT(EPOCH FROM (NOW()-fecha_ingreso))/60)│
│      unidad_minutos := CASE tipo_tarifa.tipo                       │
│                          WHEN 'fraccion' THEN 15                   │
│                          WHEN 'hora'     THEN 60                   │
│                          WHEN 'nocturna' THEN 720                  │
│                          ELSE                  1                   │
│                        END                                          │
│      tiempo_tar_plena := (valor_plena / valor) * unidad_minutos    │
│      IF valor_plena > 0 AND tiempo_minutos >= tiempo_tar_plena     │
│        THEN total := valor_plena                                   │
│        ELSE total := valor * CEIL(tiempo_minutos)                  │
│      END IF                                                        │
│                                                                    │
│   f) iva     := ROUND(total * porcentaje::numeric/100, 4)          │
│      subtotal := ROUND(total - iva, 4)                              │
│      total_out := ROUND(total, 2)                                   │
│      vigente_hasta := NOW() + INTERVAL '15 minutes'                │
│                                                                    │
│      RETURN jsonb_build_object(                                    │
│        'cobrar', true,                                             │
│        'subtotal', subtotal, 'iva', iva, 'total', total_out,       │
│        'tiempo_minutos', tiempo_minutos,                           │
│        'tarifa_uuid', uuid,                                        │
│        'vigente_hasta', to_char(vigente_hasta,'YYYY-MM-DD"T"HH24:MI:SS"Z"')│
│      );                                                            │
│ COMMIT;                                                            │
└────────────────────────────────────────────────────────────────────┘
        │
        ▼ respuesta JSON al cliente
```

Toda la fórmula y todos los locks viven en la DB. El handler HTTP es thin: parsea
`uuid_ingreso`, llama la función, mapea el `jsonb` a `CotizarResponse` o `HTTPException`.

## 5. Capabilities

### New

- **`operacion-cotizar`** — cubre el endpoint `GET /operacion/cotizar`, la función
  PL/pgSQL `calcular_cotizacion`, el schema `CotizarResponse` y los errores tipados
  (`ingreso_no_encontrado`, `tarifa_no_vigente`, `iva_no_configurado`). Spec en
  `openspec/changes/hu-f1-8-cotizar/specs/operacion-cotizar/spec.md`, archivada en
  `openspec/specs/operacion-cotizar/spec.md`.

### Modified

- **`operations`** — la skill canónica agrega el discriminador `cobrar: bool` y la rama
  `cobrar:false, motivo:'mensualidad_vigente'` como nuevo modo de respuesta del
  recurso `ingreso` desde la perspectiva del operador. Sin cambio contractual sobre
  REQ-OPS-001..021; sólo delta. Spec deltada en `openspec/changes/hu-f1-8-cotizar/specs/operations/spec.md`.

## 6. Data Model

`modelo_datos_er.mmd` — **sin cambios de esquema**. La migración `0022` sólo crea
`prod.calcular_cotizacion(...)` y otorga `EXECUTE` a `parkos_app`.

**Columnas leídas** (todas existentes):

| Tabla | Columna | Línea ER | Lectura |
|---|---|---|---|
| `ingreso` | `uuid_sucursal, placa, uuid_tipo_vehiculo, uuid_subscripcion_cliente, fecha_ingreso` | 577–596 | SELECT |
| `ingreso` | `uuid` | 577–596 | PK lookup |
| `tarifas_sucursal` | `uuid, valor, valor_plena` | 406–426 | SELECT … FOR SHARE (KD-1) |
| `tarifas_sucursal` | `vigente_desde, vigente_hasta, estado` | 406–426 | predicado bi-temporal |
| `impuestos` | `porcentaje` | 187–207 | SELECT |
| `impuestos` | `nombre='IVA'` | 187–207 | filtro |
| `impuestos` | `vigente_desde, vigente_hasta, estado` | 187–207 | predicado bi-temporal |
| `subscripciones_cliente` + `subscripcion_vehiculos` + `vehiculos` | joins | 496–518, 538–557, 519–537 | portar `resolve_active_subscription_for_exit` a SQL |
| `salidas` | existencia | 761–777 | NOT EXISTS sobre ingreso activo |
| `tipo_tarifa` | `tipo` (string) | 128–144 | JOIN; base del CASE KD-2 |
| `tipos_vehiculo` | (sin columnas) | 87–104 | JOIN FK |
| `sucursal` | (sin columnas) | 341–365 | JOIN FK |

**DDL nuevo** (migración `0022`):

```sql
CREATE OR REPLACE FUNCTION prod.calcular_cotizacion(p_uuid_ingreso uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
AS $$
  -- (cuerpo según §4 Architecture Overview; sin INSERT/UPDATE/DELETE)
$$;

GRANT EXECUTE ON FUNCTION prod.calcular_cotizacion(uuid) TO parkos_app;
```

Función marcada `STABLE` (no `VOLATILE`) — no muta estado, abre camino a optimizaciones
del planner. Defensa complementaria: AST check `test_no_write_in_calcular_cotizacion.py`
rechaza `INSERT|UPDATE|DELETE` en el cuerpo (R7).

## 7. API Surface

| Path | Method | Cambio | Issuer / rol |
|---|---|---|---|
| `/api/v1/operacion/cotizar` | GET | NUEVO endpoint con query param `uuid_ingreso: UUID4` | `operador-`, `admin-` |

**Request signature**:

```python
async def cotizar_ingreso(
    uuid_ingreso: UUID4 = Query(..., description="UUIDv4 del ingreso a cotizar"),
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),
) -> CotizarResponse:
```

**Response shape** (`CotizarResponse`):

```python
class CotizarResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cobrar: bool
    motivo: str | None = None                 # sólo si cobrar=false
    subtotal: Decimal | None = None           # sólo si cobrar=true
    iva: Decimal | None = None                # sólo si cobrar=true
    total: Decimal | None = None              # sólo si cobrar=true
    tiempo_minutos: int | None = None         # sólo si cobrar=true
    tarifa_uuid: UUID | None = None           # sólo si cobrar=true
    vigente_hasta: datetime | None = None     # sólo si cobrar=true; NOW()+15min
```

**Ejemplos**:

```json
// 200 OK — tarifa aplicable
{
  "cobrar": true,
  "subtotal": "10250.0000",
  "iva": "2050.0000",
  "total": "12300.00",
  "tiempo_minutos": 90,
  "tarifa_uuid": "…",
  "vigente_hasta": "2026-09-14T18:30:00Z"
}

// 200 OK — mensualidad vigente
{"cobrar": false, "motivo": "mensualidad_vigente"}
```

**Errores tipados**:

| HTTP | Body | Cuándo |
|---|---|---|
| 404 | `{"error":"ingreso_no_encontrado"}` | uuid no existe o ya tiene salida no anulada (plan.md:877) |
| 404 | `{"error":"tarifa_no_vigente"}` | no hay fila `tarifas_sucursal` para la combinación en `t=NOW()` (KD-3) |
| 500 | `{"error":"iva_no_configurado"}` | no hay fila `impuestos` con `nombre='IVA'` vigente (KD-IVA) |
| 401/403 | sin cambios | issuer inválido / falta token (precedente) |

**Headers**: `Cache-Control: no-store` (R8). `Content-Type: application/json; charset=utf-8`.

**Sin cambios sobre**:

- `POST /operacion/ingresos`, `GET /operacion/ingresos/{uuid}`,
  `GET /operacion/ingresos/{uuid}/estado`, `GET /operacion/ingresos` (precedentes).

**Requirements planificados** (escritos en spec.md por `sdd-spec`):

- `REQ-OPS-022` — endpoint `GET /operacion/cotizar` con contrato GAP-BE-09
- `REQ-OPS-023` — función `calcular_cotizacion` PL/pgSQL con fórmula CU-02 AC7 + KD-1 lock
- `REQ-OPS-024` — discriminador `cobrar` y motivo `mensualidad_vigente` reusando
  `resolve_active_subscription_for_exit`
- `REQ-OPS-025` — errores tipados `ingreso_no_encontrado`, `tarifa_no_vigente`,
  `iva_no_configurado` y header `Cache-Control: no-store`

## 8. Risks & Mitigations

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | `impuestos.IVA` NO sembrado — toda cotización devuelve 500 `iva_no_configurado` hasta siembra operativa | **CRÍTICA** | KD-IVA confirmado por usuario 2026-09-14. Apply NO siembra. `design.md` declara bloqueante para despliegue y documenta receta exacta (`infra/scripts/seed_catalogs.py` 1 row `nombre='IVA', porcentaje=19`) — ownership HU-F14.2 Parte II |
| **R2** | Redondeo monetario — `Numeric(18,4)` en storage vs 2 decimales en JSON | Media | `ROUND(total, 2)` en salida jsonb; `ROUND(iva/subtotal, 4)` en intermedios; tests con valores `12300.1234` |
| **R3** | Atomicidad — sin lock, tarifa podría cerrar entre cotización y POST /salidas | Media | KD-1: `SELECT … FOR SHARE` dentro de PL/pgSQL; HU-F1.7 replicará. Documentado como lock compartido (no exclusivo) para no serializar todas las cotizaciones |
| **R4** | Sin tarifa vigente para la combinación — error code no especificado en plan.md | Media | KD-3: nuevo error tipado `404 tarifa_no_vigente`. Distinguible de `ingreso_no_encontrado` por código en body |
| **R5** | Redondeo minutos `Math.ceil` — caso 90s→2min, 59s→1min, 60s→1min, 61s→2min | Baja | Test literal AC3 con 4-5 casos de borde parametrizados |
| **R6** | `fecha_ingreso` tz — columna `DateTime(timezone=False)` sembrada con `NOW()` UTC | Baja | `NOW()` en PL/pgSQL devuelve `timestamptz` consistente; verificación cruzada con HU-F1.6 (validaciones reales en `POST /operacion/ingresos`) cuando entre |
| **R7** | PL/pgSQL read-only — futuro dev podría agregar INSERT y romper idempotencia | Baja | Función marcada `STABLE`; AST check `test_no_write_in_calcular_cotizacion.py` rechaza `INSERT|UPDATE|DELETE` en el cuerpo. CI gate |
| **R8** | Cache-Control en respuesta — proxy podría servir cotización expirada | Baja | Header `Cache-Control: no-store` en handler; test verifica header presente |

## 9. Success Criteria

1. `GET /operacion/cotizar?uuid_ingreso=<uuid_válido>` con `tarifas_sucursal` vigente y
   `impuestos.IVA` sembrado devuelve `200` con los 7 campos numéricos/datetime del contrato
   y `cobrar:true`.
2. Con `subscripcion_cliente` vigente: `200 {"cobrar":false,"motivo":"mensualidad_vigente"}`.
3. Con uuid inexistente o con salida no anulada: `404
   {"error":"ingreso_no_encontrado"}`.
4. Sin fila `tarifas_sucursal` para la combinación: `404
   {"error":"tarifa_no_vigente"}`.
5. Sin fila `impuestos.IVA` vigente: `500 {"error":"iva_no_configurado"}`.
6. `vigente_hasta` ≈ `NOW() + 15 min` (tolerancia ±2s).
7. Header `Cache-Control: no-store` presente en toda respuesta 2xx/4xx/5xx del endpoint.
8. Función `calcular_cotizacion` marcada `STABLE` y sin `INSERT|UPDATE|DELETE` en cuerpo
   (verificado por AST check en CI).
9. Suite `pytest backend/tests/unit/test_calcular_cotizacion.py` y
   `backend/tests/integration/test_calcular_cotizacion_db.py` verde.
10. `ruff check`, `ruff format --check`, `mypy --strict` verde sobre los 4 archivos
    nuevos/modificados.
11. `EXPLAIN` sobre la función muestra índice/heap scan eficiente: lock `FOR SHARE`
    sobre PK de `tarifas_sucursal` con cardinalidad esperada < 100 filas/sede.
12. Ninguna migración Alembic nueva fuera de `0022_create_calcular_cotizacion.py`;
    `modelo_datos_er.mmd` intacto.

## 10. Out of Scope

1. Siembra de `impuestos.IVA` (KD-IVA, HU-F14.2 Parte II). Receta documentada en
   `design.md`, no aplicada en este change.
2. `POST /operacion/cotizar` (cotización con side-effects) — sólo GET idempotente.
3. Mensualidades con extensiones / prórogas / días adicionales — futuro producto.
4. Tarifas nocturnas con reglas especiales más allá del `CASE` KD-2 (no hay escalado por
   hora del día).
5. Re-implementar `resolve_active_subscription_for_exit` en PL/pgSQL — la PL/pgSQL invoca
   la misma lógica vía port directo; si HU-F1.4 cambia el helper Python, sincronizar
   manualmente la constante SQL (riesgo de drift documentado en `exploration.md` §Conflictos).
6. Refresh proactivo de cotización (HU-F1.7 decide si renegociar).
7. Tabla `tarifas_sucursal_extras`, `servicios_extras`, `categorias_vehiculo`,
   `servicios` — no existen en el ER; no se crean.
8. Versionado de UI cliente (Fase 2 frontend).
9. Lock sobre `impuestos` y `subscripciones_cliente` — sólo `tarifas_sucursal` (KD-1).

## 11. Relevant Files

- `backend/packages/parkos_core/migrations/versions/0022_create_calcular_cotizacion.py`
  (NUEVO) — Alembic: `CREATE FUNCTION prod.calcular_cotizacion(...) RETURNS jsonb` + GRANT.
- `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py` (MODIFICAR) —
  agregar handler `cotizar_ingreso` sobre `APIRouter` custom (línea 52); sin tocar los 5
  endpoints existentes.
- `backend/packages/parkos_core/src/parkos_core/schemas/operacion.py` (MODIFICAR) —
  agregar `CotizarResponse` con discriminador `cobrar` y campos opcionales.
- `backend/packages/parkos_core/src/parkos_core/repo/cotizacion.py` (NUEVO) — thin wrapper
  `cotizar_ingreso(session, *, uuid_ingreso) -> dict` que llama la PL/pgSQL y mapea
  jsonb a dict.
- `backend/tests/unit/test_calcular_cotizacion.py` (NUEVO) — escenarios plan.md + casos de
  borde AC3.
- `backend/tests/integration/test_calcular_cotizacion_db.py` (NUEVO) — DB-backed con siembra
  real IVA+tarifa+ingreso.
- `openspec/specs/operations/spec.md` (MODIFICAR) — `REQ-OPS-022..025` + entrada en
  `## Modified Capabilities`.
- `openspec/changes/hu-f1-8-cotizar/{proposal,specs/operacion-cotizar/spec.md,
  specs/operations/spec.md,design.md,tasks.md,exploration.md}` (NUEVOS, este change) — 6
  archivos.

**Archivos NO tocados (deliberado)**:

- `repo/tarifas_vigencia.py` (helper F1.4, semánticamente reusable pero NO se llama desde
  Python — la PL/pgSQL hace todo server-side para atomicidad).
- `api/v1/empresa.py`, `router_factory.py` (factory F1.1).
- `models/*` (sin cambios de esquema).

## 12. Open Questions

**Ninguna abierta**. Las 4 KD (KD-1 lock, KD-2 unidad_minutos, KD-3 error, KD-IVA siembra)
están confirmadas por el usuario con fecha 2026-09-14. El explore documenta el sembrado
de `impuestos.IVA` como **bloqueante para despliegue**; el sub-agente `sdd-apply` de este
change **NO siembra** por contrato (KD-IVA). La siembra queda como prerrequisito
operativo previo al primer deploy de HU-F1.8 en producción, con receta exacta
documentada en `design.md` (`infra/scripts/seed_catalogs.py` con `nombre='IVA',
porcentaje=19` o equivalente regulatorio local).
