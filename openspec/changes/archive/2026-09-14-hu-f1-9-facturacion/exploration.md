# Exploration: HU-F1.9 — Facturación transaccional + NIT módulo 11

> **Change**: `hu-f1-9-facturacion`
> **Phase**: explore (sdd-explore)
> **HU**: HU-F1.9 — `POST /api/v1/facturacion/factura` (transaccional atómico: `facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos`) + `POST /api/v1/facturacion/factura-pagos` (validación voucher datáfono) + helper `validar_nit_modulo11` (NIT módulo 11, DIAN check digit).
> **Date**: 2026-09-14
> **Working dir**: `E:\easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `def754d`; F1.1..F1.8 cerradas).
> **Precedents read**: `archive/2026-09-14-hu-f1-8-cotizar/{exploration,design}.md` (PL/pgSQL VOLATILE + lock FOR SHARE + KD-1), `archive/2026-09-14-hu-f1-7-salidas/{exploration,design}.md` (12-step handler chain + single-commit invariant + MIGRATION 0026 KD-IVA resolver), `openspec/specs/operations/spec.md` (52 REQs REQ-OPS-001..052 merged), `modelo_datos_er.mmd` (`facturas` 667-687, `factura_detalle` 780-794, `factura_pagos` 843-861, `factura_electronica` 689-705, `clientes` 449-472, `resolucion_facturacion` 315-332, `impuestos` 187-207), `plan.md` (HU-F1.9 lines 891-935 — 330 LOC, 4 tasks T1..T4), `backend/packages/parkos_core/migrations/versions/0001_initial_schema.py` (líneas 435-452 `clientes`, 607-654 `facturas`+`factura_detalle`, 688-717 `factura_pagos`, 875-891 `factura_electronica`, 1378 `fk_facturas_uuid_salida`, 2024-2088 `fn_*_inmutable` triggers).

## 1. Contexto de la HU

HU-F1.9 closes the **billing** (facturación) half of CU-04 (CU-04 = "Gestionar Cobro"). Se activa tras F1.7 (cerrada) y F1.8 (cerrada):

- **F1.8** (cerrada, `a3d0c39`) ya retorna el desglose fiscal (`subtotal`, `iva`, `total`) via `prod.calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb VOLATILE` con `SELECT … FOR SHARE` sobre `tarifas_sucursal`. HU-F1.9 **reusa este desglose como insumo principal** — NO recalcula IVA server-side, lee el snapshot ya calculado.
- **F1.7** (cerrada, `c320d0f`+`aa2fc9b`+`f826e8c`) ya inserta `prod.salidas` atómicamente. HU-F1.9 corre **después** del cierre de salida: la transacción de facturación es un nuevo handler que toma `uuid_salida` como input y produce `facturas` + `factura_detalle` + `factura_impuestos` + `factura_pagos` en una sola TX.
- **KD-IVA** (F1.8 blocker) **YA RESUELTO** por MIGRATION 0026 de F1.7 (Op 2 inline-seed `prod.impuestos.IVA` con `porcentaje=0.19`). `validar_iva_configurado()` de F1.7 retorna `True` post-deploy.

**Tamaño**: 330 LOC per `plan.md` línea 929 (≈50 LOC handler `create_factura` + 80 LOC handler `create_factura_pagos` + 100 LOC `repo/factura.py` + 50 LOC `repo/nit_modulo11.py` + 50 LOC schemas nuevos — NO migration nueva preferentemente — + ~700 LOC tests).

**Endpoints target**:
1. `POST /api/v1/facturacion/factura` — atomic transaction: facturas + factura_detalle + factura_impuestos + factura_pagos + (single commit). Returns `201` con `FacturaRead` que incluye consecutivo provisional.
2. `POST /api/v1/facturacion/factura-pagos` — voucher validation for datáfono (`400 voucher_requerido` if `medio_pago='datafono'` sin `referencia`).
3. `GET /api/v1/facturacion/facturas/{uuid}` — read single (adjacent).
4. `GET /api/v1/facturacion/facturas?uuid_cliente=...&fecha_desde=...&fecha_hasta=...` — query by cliente + date range (adjacent).

**Wiring adicional**: helper `validar_nit_modulo11(nit, dv)` applied at Pydantic v2 layer to `ClientesCreate` (always) and `FacturaItemConDatosPropios` (only when `fe_con_datos=true`).

## 2. Endpoint target

### `POST /api/v1/facturacion/factura` (NUEVO, transaccional atómico)

```python
@router.post(
    "/factura",
    response_model=FacturaRead,
    status_code=201,
    summary="HU-F1.9: transaccional atómico — facturas + detalle + impuestos + pagos + lock FOR SHARE tarifas",
    responses={
        400: {"description": "voucher_requerido | monto_insuficiente"},
        404: {"description": "salida_no_encontrada | cliente_no_encontrado | tarifa_no_vigente"},
        422: {"description": "nit_invalido | email_invalido | detalle_invalido | total_no_coherente"},
        500: {"description": "iva_no_configurado (KD-IVA post-0026 deploy: never)"},
    },
)
```

**Path registered in**: nueva dependencia `r.include_router(facturacion.router)` en `api/v1/__init__.py`.

**Issuer dep**: `_facturacion_issuer_dep = requires_issuer("admin-", "cajero-")` — HU-F1.9 introduce el prefijo `cajero-` (cajero de sucursal emite facturas). Admin puede emitir cross-sucursal.

### `POST /api/v1/facturacion/factura-pagos` (NUEVO)

Idéntico issuer dep. Recibe `FacturaPagoAdicionalCreate` (uuid_factura + medio_pago + valor + referencia + uuid_sesion). Solo aplica a facturas en estado `emitida` (no `pagada`, no `anulada`).

### Adjacent read endpoints (proposed, lower priority for F1.9)

- `GET /facturacion/facturas/{uuid}` — read `prod.facturas` joined con view derivada.
- `GET /facturacion/facturas?uuid_cliente=...&fecha_desde=...&fecha_hasta=...` — paginated list.

## 3. Tablas y modelos

| Tabla | Tipo (ER) | Estado F1.9 | Rol |
|---|---|---|---|
| `prod.facturas` | `[L-E]` | **INSERT** (Step 9) | Lifecycle event; composite PK `(uuid, fecha_retencion_hasta)`; ORM `Facturas(LifecycleEventBase)` ya existe. **NO** tiene columna `uuid_cliente` — DEC-FACT-06. |
| `prod.factura_detalle` | `[A]` | **INSERT** (Step 10) | Composite PK + monthly pg_partman partition; ORM `FacturaDetalle(AppendOnlyBase)` ya existe. |
| `prod.factura_impuestos` | `[A]` | **INSERT** (Step 10) | Snapshot del IVA: `uuid_impuesto`, `base_calculo`, `porcentaje_aplicado`, `valor`. ORM ya existe. |
| `prod.factura_pagos` | `[A]` | **INSERT** (Step 10) | Composite PK + monthly pg_partman partition; ORM `FacturaPagos(AppendOnlyBase)` ya existe. |
| `prod.clientes` | `[V]` | **SELECT/INSERT condicional** | UK `(tipo_identificador, numero_identificacion, vigente_desde)` ya en 0001:450. La columna de NIT se llama **`numero_identificacion`**, no `documento`. ORM `Clientes(VersionedBase)` ya existe. |
| `prod.impuestos` | `[V]` | **SELECT** (V3) | `validar_iva_configurado()` de F1.7 retorna `True` post-0026 deploy. |
| `prod.tarifas_sucursal` | `[V]` | **SELECT FOR SHARE** (KD-FACT-02) | Mismo lock pattern que F1.7/F1.8. |
| `prod.salidas` | `[A]` | **SELECT** (V1) | El cliente envía `uuid_salida`; server valida que existe + es facturable. |
| `prod.ingreso` | `[L-E]` | **SELECT** (V1 derivado) | Para derivar `uuid_sucursal`. |
| `prod.forma_pago` | `[V]` | **NO EXISTE EN DB** | **GAP**: el plan.md asume catálogo `forma_pago` pero la tabla **NO está creada**. Hoy `prod.factura_pagos.medio_pago` es string libre. F1.9 introduce la tabla como **migration 0027 opcional** (DEC-FACT-07). |
| `prod.retencion` | `[A]` | **NO EXISTE EN DB** | **GAP**: el brief menciona `prod.retencion` con campo `beneficiario` y descuento RETCONT 11% sobre servicios (DIAN 2026). Hoy NO existe. F1.9 introduce la tabla como **migration 0027 opcional** (DEC-FACT-04). |
| `prod.assign_consecutivo` | Python helper | **EXISTE** | **GAP vs brief**: el brief dice "PL/pgSQL function `assign_consecutivo` (ya implementado)". Realidad: `assign_consecutivo` es **helper Python asíncrono** en `backend/.../repo/resolucion_facturacion.py::assign_consecutivo`, branch-local, con `SELECT ... FOR UPDATE`. **No es PL/pgSQL**; F1.10 owns enhancements. F1.9 lo reusa tal cual. |
| `prod.factura_electronica` | `[L-E]` | NO TOCADO en F1.9 | F1.10 owns numbering + estado DIAN. |

**Defense in depth ya en DB** (migration 0001):
- `prod.factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`: tienen `fn_*_inmutable` triggers (líneas 2024-2088) que rechazan UPDATE/DELETE.
- `prod.facturas` is `[L-E]` — **TO VERIFY** si tiene REVOKE explícito o `fn_facturas_inmutable` trigger.

## 4. Validaciones V1..V6

### V1 — Salida existe y es facturable

- `SELECT … FROM prod.salidas WHERE uuid = :p AND fecha_retencion_hasta = :frh`.
- Server también verifica que NO exista aún una `factura` con `uuid_salida = :p` y estado derivado `emitida` o `pagada`.
- Si no encuentra → `404 {"error":"salida_no_encontrada", "uuid_salida":"..."}`.
- Sin bypass — una salida ya facturada no puede re-facturarse.

### V2 — Cliente existe (cuando `fe_con_datos=true`)

- `SELECT … FROM prod.clientes WHERE tipo_identificador='NIT' AND numero_identificacion=:nit AND vigente_hasta IS NULL AND estado='activo'`.
- Si no encuentra Y `fe_con_datos=true` → 404 `cliente_no_encontrado`.
- Si `fe_con_datos=false` (consumidor final): no requiere cliente.

### V3 — IVA configurado

- `repo/impuestos.py::validar_iva_configurado(session)` reusado verbatim de F1.7.
- Si retorna `False` → 500 `iva_no_configurado`.

### V4 — Detalle items coherentes

- Lista `items: list[FacturaItemCreate]` con `cantidad > 0`, `valor_unitario >= 0`, `concepto: Literal['servicio', 'producto']`, `uuid_tarifa_sucursal: UUID | None`.
- Si `items=[]` → 422 `detalle_invalido`.

### V5 — NIT módulo 11 (cuando `fe_con_datos=true`)

- Helper `validar_nit_modulo11(nit: str, dv: str) -> bool` en `repo/nit_modulo11.py` (~50 LOC).
- Algorithm: weighted sum con weights `[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]` aplicados **de derecha a izquierda** sobre los dígitos del NIT (sin el DV).
- Pydantic v2 validator en `FacturaItemConDatosPropios` (`@field_validator('numero_identificacion')`) aplica el helper.

### V6 — Total coherente (assert ±0.01 COP)

- Server computa `total_server = subtotal_items + iva - retencion` (donde `retencion=0` en MVP).
- Compara con `payload.total`.
- Si `abs(total_server - payload.total) > Decimal("0.01")` → 422 `total_no_coherente`.

## 5. KD-FACT-01 — Single-TX atomicidad

**Choice.** Una sola `await session.commit()` materializa las 4 tablas (`facturas` + `factura_detalle` (N filas) + `factura_impuestos` (1 fila IVA) + `factura_pagos` (1 fila)) atómicamente.

**Lock + orden**:
1. **V1**: SELECT `prod.salidas` por PK.
2. **V2**: SELECT `prod.clientes` por UK.
3. **V3**: `validar_iva_configurado()`.
4. **V5** (si `fe_con_datos=true`): `validar_nit_modulo11()`.
5. **V6** (assert): server-side recompute.
6. **Lock FOR SHARE**: si algún item referencia `uuid_tarifa_sucursal`, `SELECT ... FOR SHARE` per-row.
7. **INSERT `prod.facturas`** + flush.
8. **INSERT `prod.factura_detalle` (N rows, bulk)** + flush.
9. **INSERT `prod.factura_impuestos` (1 row IVA snapshot)** + flush.
10. **INSERT `prod.factura_pagos` (1 row pago)** + flush.
11. **Single `await session.commit()`** — libera lock + materializa atómicamente.

**AST walk T-x9.1** (`tests/static/test_factura_handler_single_commit.py`, ~80 LOC): enforces exactamente **UN** `session.commit()` en el handler.

## 6. KD-FACT-02 — Lock FOR SHARE `tarifas_sucursal`

**Choice.** Si `factura_detalle.uuid_tarifa_sucursal IS NOT NULL`, server ejecuta `SELECT ... FOR SHARE` per-row sobre cada `tarifas_sucursal` referenciada **antes** del INSERT. Lock mantenido hasta `session.commit()`.

**Alternatives**:
- Sin lock (lock-free): rejected — abre ventana de inconsistencia.
- Lock per-table: rejected — serializa TODAS las facturaciones.

**Rationale.** Per-row `FOR SHARE` mantiene el lock solo sobre las filas que están siendo facturadas.

## 7. DEC / Reconciliaciones

### DEC-FACT-01 — `factura` nunca UPDATE post-creation

Una vez insertada, una factura es inmutable. Defense in depth en DB layer: **TO VERIFY** que migration 0001 tiene REVOKE UPDATE/DELETE sobre `prod.facturas`. Si falta, **migration 0027** debe añadir trigger `fn_facturas_inmutable`.

### DEC-FACT-02 — NIT módulo 11 algoritmo canónico (DIAN)

NO alternative algorithms. Helper `validar_nit_modulo11` es la única implementación válida.

### DEC-FACT-03 — IVA desde `prod.impuestos` only

NO hardcoded constants en Python. Si la DIAN cambia el IVA, basta con INSERT nueva fila `prod.impuestos` con nuevo `porcentaje`.

### DEC-FACT-04 — Retención REQUIERE tabla `prod.retencion`

MVP de F1.9 NO aplica retención. Razones:
- `prod.retencion` NO existe en DB (gap pre-existente).
- Sin la tabla, NO se puede snapshotear el porcentaje RETCONT ni el `concepto`.
- Ownership del catálogo de retenciones está fuera del corpus actual.

**Recomendación**: deferir `prod.retencion` a Fase 4 (contabilidad).

### DEC-FACT-05 — Consecutivo numbering DELEGADO a F1.10

`prod.facturas` NO recibe `prefijo` + `consecutivo` (esos viven en `factura_electronica`, F1.10 owns). F1.9 crea la factura interna con `uuid` y la retorna al cliente.

### DEC-FACT-06 — `uuid_cliente` NO vive en `prod.facturas`

Confirmado en migration 0001: solo `uuid_sucursal`, `subtotal`, `descuento`, `total`, `uuid_ingreso`, `uuid_salida`. El cliente asociado se deriva via:
- `facturas.uuid_salida` → `salidas.uuid_ingreso` → `ingreso.placa` → `vehiculos.placa`
- O via lookup `prod.clientes` por `numero_identificacion` del payload.

**Implicación**: el response `FacturaRead` debe incluir `uuid_cliente` como campo derivado (server-side lookup), NO como FK almacenada.

### DEC-FACT-07 — `prod.forma_pago` catálogo: DECIDIR en propose

**Opción A** (recomendada para MVP): NO crear `prod.forma_pago`. El campo `prod.factura_pagos.medio_pago` es `String()` libre; el cliente envía uno de `{'efectivo', 'tarjeta', 'transferencia', 'datafono', 'mixto'}` (enum Pydantic v2 enforced).

**Opción B** (más completa): crear `prod.forma_pago [V]` (migration 0027). **Trade-off**: +120 LOC.

**Recomendación**: Opción A.

### DEC-FACT-08 — `consumidor_final` placeholder

Si `fe_con_datos=false`, el handler NO crea ni requiere cliente. La factura se emite como "consumidor final" (NIT genérico `222222222222`).

### DEC-FACT-09 — NIT normalization

Helper `validar_nit_modulo11` debe:
- Strip leading zeros (`"000123"` → `"123"`).
- Strip non-digits (`"800.123.456-7"` con guión → `"800123456"`).
- Si el NIT resultante tiene <5 dígitos → reject.
- Si `dv` no es dígito → reject.

## 8. Migración (potentially)

**Decisión preferente: NO nueva migration** (F1.9 aplica sobre migration 0026 chain head sin DDL). Razones:
- `prod.facturas`, `prod.factura_detalle`, `prod.factura_impuestos`, `prod.factura_pagos`, `prod.clientes`, `prod.impuestos`, `prod.tarifas_sucursal`, `prod.salidas`, `prod.ingreso`: ya existen en migration 0001.
- `prod.impuestos.IVA` ya sembrado en migration 0026 (F1.7).
- `prod.factura_detalle_inmutable`, `prod.factura_impuestos_inmutable`, `prod.factura_pagos_inmutable` triggers ya existen (migrations 0001 líneas 2024-2088).
- `prod.facturas_inmutable` trigger **FALTA** (to verify, then migration 0027 si falta).

**Plan B — migration 0027 si gaps confirmados**:
- **Op 1**: pre-flight `DO $$` verifica existencia de las 7 tablas.
- **Op 2** (conditional, si falta `fn_facturas_inmutable`): CREATE TRIGGER equivalente a `fn_factura_detalle_inmutable` para `prod.facturas`.

**Recomendación**: apply sin migration (preferida) si `fn_facturas_inmutable` ya existe. Si NO, migration 0027 mínima (Op 1+2 solamente).

## 9. Auth pattern

```python
@router.post(
    "/factura",
    response_model=FacturaRead,
    status_code=201,
    summary="HU-F1.9: transaccional atómico — facturas + detalle + impuestos + pagos",
    responses={
        400: {"description": "voucher_requerido | monto_insuficiente"},
        404: {"description": "salida_no_encontrada | cliente_no_encontrado | tarifa_no_vigente"},
        422: {"description": "nit_invalido | email_invalido | detalle_invalido | total_no_coherente"},
        500: {"description": "iva_no_configurado"},
    },
)
async def create_factura(
    response: Response,
    payload: FacturaCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaRead:
```

**Issuer dep**: `_facturacion_issuer_dep = requires_issuer("admin-", "cajero-")`.

**Cross-tenant**: `ctx.sucursal_uuid == payload.uuid_sucursal` (operador case) OR `payload.uuid_sucursal in ctx.sucursales_permitidas` (admin case). Server deriva `uuid_sucursal` del `salidas.uuid_sucursal`.

## 10. Locking + concurrencia

- **FOR SHARE** sobre `prod.tarifas_sucursal` per-row (KD-FACT-02).
- **NO lock** sobre `prod.salidas` (V1 read by PK).
- **NO lock** sobre `prod.clientes` (V2 read by UK).
- **Single TX, single commit** (KD-FACT-01).
- **Concurrent issue**: 2 cajeros intentando facturar la misma `uuid_salida` simultáneamente. **Defense**: partial unique index sobre `prod.factura_pagos.uuid_factura` con `WHERE tipo_movimiento='pago'` (impide 2 pagos a la misma factura).
- **TO VERIFY**: partial unique index `one_pago_per_factura_init` en `prod.factura_pagos`.

## 11. Handler pattern

**Secuencia estricta de 12 pasos** (locked por AST walk `test_factura_handler_step_order.py`):

```python
async def create_factura(
    response: Response,
    payload: FacturaCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaRead:
    no_store = no_store_headers()

    # --- Step 1: KD-3 issuer claims + no_store headers. --------------
    # Resolved via dependency injection.

    # --- Step 2: V1 salida existe y es facturable. -------------------
    salida = await repo_factura.buscar_salida_facturable(session, uuid_salida=payload.uuid_salida)
    if salida is None:
        raise HTTPException(404, {"error": "salida_no_encontrada", "uuid_salida": str(payload.uuid_salida)}, headers=no_store)

    # --- Step 3: tenant scope post-V1 (KD-S2 analog). ---------------
    target_sucursal = salida.uuid_sucursal
    if ctx.issuer_prefix == "cajero-" and target_sucursal != ctx.sucursal_uuid:
        raise HTTPException(403, {"error": "tenant_scope_violation", "uuid_salida": str(payload.uuid_salida)}, headers=no_store)

    # --- Step 4: V2 cliente (si fe_con_datos=true). ------------------
    cliente_uuid: uuid_lib.UUID | None = None
    if payload.fe_con_datos:
        cliente = await repo_factura.buscar_o_crear_cliente_por_nit(
            session, numero_identificacion=payload.fe_datos_cliente.numero_identificacion,
            datos=payload.fe_datos_cliente,
        )
        if cliente is None:
            raise HTTPException(404, {"error": "cliente_no_encontrado"}, headers=no_store)
        cliente_uuid = cliente.uuid

    # --- Step 5: V3 IVA configurado. ---------------------------------
    if not await validar_iva_configurado(session):
        raise HTTPException(500, {"error": "iva_no_configurado"}, headers=no_store)

    # --- Step 6: V4 detalle items coherentes. ------------------------
    items_validados = repo_factura.validar_items(payload.items)
    if not items_validados:
        raise HTTPException(422, {"error": "detalle_invalido", "min_items": 1}, headers=no_store)

    # --- Step 7: KD-FACT-02 lock FOR SHARE per-row. -----------------
    await repo_factura.lock_tarifas_sucursal_para_items(session, items=items_validados)

    # --- Step 8: server-side recompute total (V6 assert). -----------
    total_server = repo_factura.compute_total(items=items_validados, iva=0.19, retencion=Decimal("0"))
    if abs(total_server - payload.total) > Decimal("0.01"):
        raise HTTPException(422, {
            "error": "total_no_coherente",
            "total_recibido": str(payload.total),
            "total_calculado": str(total_server),
            "diferencia": str(abs(total_server - payload.total)),
        }, headers=no_store)

    # --- Step 9: INSERT prod.facturas [L-E]. ------------------------
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

    # --- Step 10: INSERT factura_detalle (N rows) + impuestos + pago.
    await repo_factura.crear_factura_detalle_bulk(session, uuid_factura=new_factura.uuid, items=items_validados)
    await repo_factura.crear_factura_impuesto_iva(session, uuid_factura=new_factura.uuid, base=total_server)
    new_pago = await repo_factura.crear_factura_pago(
        session,
        uuid_factura=new_factura.uuid,
        medio_pago=payload.medio_pago,
        valor=payload.total,
        referencia=payload.referencia,
        uuid_sesion=ctx.uuid_sesion,
    )

    # --- Step 11: single commit (KD-FACT-01). -----------------------
    await session.commit()

    # --- Step 12: response shape. -----------------------------------
    apply_no_store_header(response)
    await session.refresh(new_factura)
    return FacturaRead(...)
```

**Handler para `/factura-pagos`** (separado, ~50 LOC, similar estructura):

```python
async def create_factura_pago(
    payload: FacturaPagoAdicionalCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_facturacion_issuer_dep),
) -> FacturaPagoRead:
    # V1: factura existe + estado emitido
    # V2: tenant scope
    # V3: voucher_requerido si medio_pago='datafono' y referencia vacía
    # V4: monto_insuficiente si valor < total pendiente
    # Step: INSERT prod.factura_pagos + single commit
    # Response: FacturaPagoRead
```

## 12. Repositorio nuevo / modificado

### NEW: `repo/factura.py` (~250 LOC)

Helpers para `POST /facturacion/factura` + `POST /facturacion/factura-pagos`:
- `buscar_salida_facturable` (V1)
- `buscar_o_crear_cliente_por_nit` (V2 + módulo11 path)
- `validar_items` (V4, Pydantic re-check)
- `lock_tarifas_sucursal_para_items` (KD-FACT-02 SELECT FOR SHARE)
- `compute_total` (V6 server-side recompute)
- `crear_factura_evento` (Step 9 INSERT [L-E])
- `crear_factura_detalle_bulk` (Step 10 bulk INSERT [A])
- `crear_factura_impuesto_iva` (Step 10 INSERT [A])
- `crear_factura_pago` (Step 10 INSERT [A])

### NEW: `repo/factura_detalle.py` (~80 LOC)

```python
"""HU-F1.9 / REQ-OPS-053..060 — Bulk insert helper for ``prod.factura_detalle``.

Single helper ``crear_factura_detalle_bulk(session, *, uuid_factura, items)``
that inserts N rows in a single ``session.add_all([...])`` call (no per-row
flush). The caller commits (KD-FACT-01 single-commit invariant).
"""
```

### NEW: `repo/nit_modulo11.py` (~50 LOC)

```python
"""HU-F1.9 / REQ-OPS-053..060 — DIAN NIT módulo 11 validator.

The Colombian NIT (Número de Identificación Tributaria) MUST be validated
against its check digit (DV) per the algoritmo de módulo 11 established by
DIAN. The check digit is computed from the preceding digits using weights
[3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71] applied
right-to-left.

Public API:
    validar_nit_modulo11(nit: str, dv: str | int) -> bool
    dv_esperado(nit: str) -> int

DIAN official algorithm reference: Resolución 000175 de 2021.
"""
from __future__ import annotations

import re

# Weights for módulo 11 (right-to-left, recycled cyclically if NIT >15 digits)
_MOD11_WEIGHTS: tuple[int, ...] = (71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3)
_NON_DIGIT_RE = re.compile(r"\D+")


def _normalize_nit(nit: str) -> str:
    """Strip non-digits, leading zeros. Returns digits-only string."""
    digits = _NON_DIGIT_RE.sub("", nit)
    return digits.lstrip("0") or "0"


def dv_esperado(nit: str) -> int:
    """Compute DV expected for the given NIT (without DV digit)."""
    digits = _normalize_nit(nit)
    if len(digits) < 5:
        raise ValueError(f"NIT too short: {digits!r} (min 5 digits)")
    sum_ponderada = 0
    for idx, digit_char in enumerate(reversed(digits)):
        weight = _MOD11_WEIGHTS[idx % len(_MOD11_WEIGHTS)]
        sum_ponderada += int(digit_char) * weight
    mod = sum_ponderada % 11
    return mod  # DIAN convention: DV = mod (NOT 11-mod). Verify against DIAN spec.
```

**ALGORITHM CORRECTION NOTE**: Two variants exist in Colombian regulation:
- Variant A (DIAN clásica): `DV = sum_ponderada % 11` (NOT 11-mod).
- Variant B (algunos terceros): `DV = 11 - (sum_ponderada % 11)`, con ajustes.

**TO VERIFY** pre-apply against DIAN's Resolución 000175 of 2021. Reference test case `800.123.456-7` discriminates them.

### REUSE (NO modificar)

- `repo/impuestos.py::validar_iva_configurado` (F1.7) — V3 read.
- `repo/resolucion_facturacion.py::assign_consecutivo` (existing, branch-local) — F1.10 owns enhancements.
- `repo/versioned.close_and_insert` (F1.5 PR5-016) — for `clientes` insert.
- `schemas/facturacion.py` (existing PR6) — extend with new Create/Read schemas.

### MODIFY

- `api/v1/__init__.py` — `r.include_router(facturacion.router)` (NEW line).
- `api/v1/facturacion.py` — NEW file (~150 LOC: 2 handlers + dependencies).
- `schemas/facturacion.py` — ADD `FacturaCreate`, `FacturaRead`, `FacturaItemCreate`, `FacturaItemRead`, `FacturaPagoAdicionalCreate`, `FacturaPagoRead`, 4 typed errors.
- `schemas/clientes.py` — ADD Pydantic v2 validator on `ClientesCreate.numero_identificacion` que llama `validar_nit_modulo11` cuando `tipo_identificador='NIT'`.

### NO tocado (deliberado)

- `api/v1/operacion.py` — F1.7 ya cierra salida. F1.9 NO se monta ahí.
- `models/{L_E/facturas,A/factura_detalle,A/factura_impuestos,A/factura_pagos,V/clientes}.py` — los ORMs ya existen.
- `repo/cotizacion.py`, `repo/salida.py` — F1.8/F1.7 reusados, NO se invocan en F1.9.

## 13. Schemas nuevos

`schemas/facturacion.py` (MODIFICAR, +80 LOC):

```python
# --- HU-F1.9 / REQ-OPS-053..060 -----------------------------------------


class FacturaItemConDatosPropios(_Base):
    """Client data block for ``fe_con_datos=true`` payloads."""
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
                raise ValueError(f"DV inválido: recibido={dv}, esperado={expected}")
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
    """HU-F1.9: POST /facturacion/factura response + GET /facturacion/facturas/{uuid}."""
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
    estado: Literal["emitida", "pagada", "anulada"]  # derived from V_FACTURA_ESTADO


class FacturaPagoAdicionalCreate(_Base):
    """HU-F1.9: POST /facturacion/factura-pagos payload."""
    uuid_factura: uuid_lib.UUID
    medio_pago: Literal["efectivo", "tarjeta", "transferencia", "datafono", "mixto"]
    valor: Decimal = Field(gt=Decimal("0"))
    referencia: Annotated[str, StringConstraints(min_length=1, max_length=255)] | None = None
    uuid_sesion: uuid_lib.UUID | None = None


# --- Typed error schemas (D-HU-F1.9-9) ----------------------------------


class NitInvalidoError(_Base):
    error: Literal["nit_invalido"]
    dv_esperado: int
    dv_recibido: str


class ClienteNoEncontradoError(_Base):
    error: Literal["cliente_no_encontrado"]
    numero_identificacion: str


class DetalleInvalidoError(_Base):
    error: Literal["detalle_invalido"]
    min_items: int


class TotalNoCoherenteError(_Base):
    error: Literal["total_no_coherente"]
    total_recibido: str
    total_calculado: str
    diferencia: str
```

`extra='forbid'` (heredado de `_Base`) en todos.

## 14. KD preliminares

- **KD-FACT-01**: Single `await session.commit()` materializa 4 tablas atómicamente. AST walk `test_factura_handler_single_commit.py` enforces `len(commits) == 1`.
- **KD-FACT-02**: `SELECT ... FOR SHARE` per-row sobre `prod.tarifas_sucursal`.
- **KD-NIT-01**: Algoritmo módulo 11 verificado contra spec DIAN (Resolución 000175 de 2021).
- **KD-NIT-02**: Atomicidad enforced via AST walk single-commit.
- **KD-NIT-03**: Lock FOR SHARE on tarifas_sucursal per item.
- **KD-NIT-04**: Cliente existe + estado='activo' (cuando `fe_con_datos=true`).
- **KD-NIT-05**: forma_pago enum validated at Pydantic layer.
- **KD-NIT-06**: Total coherence check.
- **KD-NIT-07**: Voucher reference REQUIRED when `medio_pago='datafono'`.

## 15. Test patterns

Total: ~14 tests across 5 files.

### `tests/unit/test_facturacion_factura.py` (~400 LOC, 6 tests)

- `test_factura_atomica_rotacion_exitosa_returns_201` — T1: happy path.
- `test_factura_consumidor_final_sin_datos_cliente` — T2: `fe_con_datos=false`.
- `test_factura_con_datos_cliente_nit_valido` — T3: `NIT 800.123.456-7 + DV=7` passes.
- `test_factura_con_datos_cliente_nit_invalido_returns_422` — T4: DV mismatched.
- `test_factura_detalle_items_vacio_returns_422` — T5: `items=[]`.
- `test_factura_total_no_coherente_returns_422` — T6: total differs.

### `tests/unit/test_validar_nit_modulo11.py` (~150 LOC, 4 tests)

- `test_nit_referencia_800_123_456_7_valido` — T1: DIAN reference case.
- `test_nit_800_123_456_5_invalido_dv_mismatch` — T2.
- `test_nit_con_ceros_a_la_izquierda_normaliza` — T3.
- `test_nit_con_guion_y_puntos_normaliza` — T4.

### `tests/unit/test_facturacion_factura_pagos.py` (~150 LOC, 2 tests)

- `test_factura_pago_datafono_sin_referencia_returns_400` — T1: `voucher_requerido`.
- `test_factura_pago_datafono_con_referencia_returns_201` — T2.

### `tests/integration/test_factura_atomicidad_db.py` (~250 LOC, 2 tests, `PARKOS_DOCKER_TEST=1`)

- `test_factura_atomica_rollback_si_detalle_falla` — T1.
- `test_factura_lock_for_share_sobre_tarifas` — T2.

### AST walks (2 tests)

- `tests/static/test_factura_handler_single_commit.py` (~80 LOC) — KD-FACT-01.
- `tests/static/test_factura_handler_step_order.py` (~80 LOC) — 12-step order.

## 16. Artifacts + Riesgos (R1..R7)

### Artifacts

```
openspec/changes/hu-f1-9-facturacion/exploration.md        ← este archivo
openspec/changes/hu-f1-9-facturacion/proposal.md          (sdd-propose)
openspec/changes/hu-f1-9-facturacion/specs/operational/spec.md  (sdd-spec)
openspec/changes/hu-f1-9-facturacion/design.md            (sdd-design)
openspec/changes/hu-f1-9-facturacion/tasks.md             (sdd-tasks)
openspec/changes/hu-f1-9-facturacion/verify-report.md     (sdd-verify)
```

**Backend (NEW):**
- `api/v1/facturacion.py` (~150 LOC, 2 handlers)
- `repo/factura.py` (~250 LOC, 9 helpers + 3 typed exceptions)
- `repo/factura_detalle.py` (~80 LOC, 1 bulk helper)
- `repo/nit_modulo11.py` (~50 LOC, módulo 11 algorithm)

**Backend (MODIFY):**
- `api/v1/__init__.py` — `r.include_router(facturacion.router)` (+1 line)
- `schemas/facturacion.py` (+80 LOC)
- `schemas/clientes.py` (+10 LOC)

**Migration (CONDITIONAL):**
- `migrations/versions/0027_facturas_inmutable_trigger.py` (~80 LOC, **only if** `fn_facturas_inmutable` not present in 0001)

**Tests (NEW):**
- `tests/unit/test_facturacion_factura.py` (~400 LOC, 6 tests)
- `tests/unit/test_validar_nit_modulo11.py` (~150 LOC, 4 tests)
- `tests/unit/test_facturacion_factura_pagos.py` (~150 LOC, 2 tests)
- `tests/integration/test_factura_atomicidad_db.py` (~250 LOC, 2 tests)
- `tests/static/test_factura_handler_single_commit.py` (~80 LOC)
- `tests/static/test_factura_handler_step_order.py` (~80 LOC)

### Riesgos

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | Algoritmo NIT módulo 11 incorrecto (variante A vs B) | **CRITICAL** | Pre-apply verify contra DIAN Resolución 000175 de 2021 + test `800.123.456-7`. RIESGO-SUC-04 plan.md:2679 ya identifica este riesgo. |
| **R2** | Falta `fn_facturas_inmutable` trigger sobre `prod.facturas` | **HIGH** | TO VERIFY pre-apply via `grep "fn_facturas_inmutable" migrations/`. Si falta, migration 0027 Op 2. |
| **R3** | Partial unique index `one_pago_per_factura_init` NO existe | **HIGH** | TO VERIFY pre-apply. Si falta, migration 0027 Op 3. |
| **R4** | `prod.retencion` y `prod.forma_pago` NO existen en DB | **MEDIUM** | DEC-FACT-04 + DEC-FACT-07: MVP sin ellas. Enum Pydantic enforced. Deferir a Fase 4. |
| **R5** | `prod.facturas.uuid_cliente` NO existe como columna | **MEDIUM** | DEC-FACT-06: `uuid_cliente` derivado server-side, NO persistido. |
| **R6** | Forma de pago no validada contra catálogo en DB | **LOW** | DEC-FACT-07 Opción A: Pydantic `Literal[...]` enforced. |
| **R7** | Lock continuidad entre `/factura` y `/factura-pagos` es 2 TX | **LOW** | Cada handler abre su propia TX. Idempotency-Key header (PR2) maneja retries. |
