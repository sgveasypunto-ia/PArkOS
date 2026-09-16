# Exploration: HU-F1.7 — POST /operacion/salidas (rotación + mensualidad derivation)

> **Change**: `hu-f1-7-salidas`
> **Phase**: explore (sdd-explore)
> **HU**: HU-F1.7 — Server-side enforcement of `POST /operacion/salidas`: rotación vs mensualidad derivation, KD-FORZADO-01 bypass reusado de F1.6, KD-IVA inline-seed via MIGRATION 0026, tarifa vigente vía `prod.calcular_cotizacion` (PL/pgSQL F1.8 VOLATILE) con lock FOR SHARE continuo.
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `2a2cbd2`; F1.1..F1.6 cerradas, F1.8 cerrada, F1.7 en explore)
> **PR target**: `origin/dev`
> **Precedente inmediato**: `archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/` (estructura espejo), `archive/2026-09-14-hu-f1-8-cotizar/` (patrón PL/pgSQL VOLATILE + lock + KD-IVA blocker)

---

## 1. Contexto de la HU

HU-F1.7 cierra la mitad "salida" del CU-01/CU-02/CU-03M. Hasta F1.6 (archivado en `21097c8`), solo existía el endpoint `POST /api/v1/operacion/ingresos` con sus 11 validaciones server-side. El endpoint simétrico `POST /api/v1/operacion/salidas` no existía en el router (`grep "POST.*salidas" backend/` → 0 matches confirmado en F1.8 exploration). El helper de lookup `resolve_active_subscription_for_exit` (T-PR5-016) ya vivía en `api/v1/operacion.py:500-562` desde PR5, pero ningún handler HTTP lo invocaba.

F1.7 entrega **un único handler** `POST /api/v1/operacion/salidas` que:

1. Localiza el `ingreso` activo por `uuid_ingreso` (V1).
2. Vuelve a validar la subscripción si el ingreso la referenciaba — pudo vencer entre entrada y salida (V2).
3. Confirma que la placa del request coincide con la del ingreso (V3).
4. Aplica KD-FORZADO-01 si `forzado=true` (V4, reusado verbatim de F1.6).
5. Invoca `prod.calcular_cotizacion(:uuid_ingreso)` (PL/pgSQL F1.8 VOLATILE) para validar tarifa vigente al momento de la salida (V5).
6. INSERT en `prod.salidas` `[A]` con `motivo` (observaciones raw, prefijo KD-FORZADO-01 aplicado en V4).
7. Deriva `tipo_salida = MENSUALIDAD | ROTACION` server-side desde el jsonb devuelto por F1.8 (`cobrar:false` → MENSUALIDAD; `cobrar:true` → ROTACION). **DEC-SUC-21-NEW**: NUNCA persistido en `prod.salidas` (la tabla no tiene columna para ello, análoga a DEC-SUC-21 del ingreso).
8. Inserta alerta si V2 o V5 fueron salvados por bypass.
9. Responde `201` con `SalidaReadForzado`.

**Dependencias (commits merged):**
- `21097c8` (HU-F1.6) — validaciones POST /ingresos + KD-FORZADO-01 contrato + helper `validar_subscripcion_vigente` + `resolve_active_subscription_for_exit` lifted a `repo/subscripcion_activa.py`.
- `a3d0c39` (HU-F1.8) — PL/pgSQL `prod.calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb VOLATILE` con `SELECT … FOR SHARE` sobre `tarifas_sucursal` + KD-3 `404 tarifa_no_vigente` + KD-IVA deployment blocker.
- `2a2cbd2` (HU-F1.6 archive) — branch actual limpia con F1.6 ya mergeada.

**KD-IVA blocker (precondición resuelta por F1.7):** `impuestos.IVA` NO está sembrado en ninguna migración 0001-0025 (grep `INSERT INTO prod.impuestos` → 0 matches confirmado en F1.8 exploration:56). Hasta F1.8, este era un deployment blocker (cada cotización devuelve 500). **Decisión del orchestrator:** inline-seed `impuestos.IVA` como parte de F1.7's apply phase (patrón F1.6/0025 con `INSERT … ON CONFLICT (codigo) DO NOTHING`). Documentado en §7 (MIGRATION 0026) y §16 (R1).

**Tamaño:** **220 LOC** (plan.md línea 835) — distribuido en ~50 LOC handler + ~180 LOC `repo/salida.py` + ~50 LOC `repo/impuestos.py` + ~80 LOC schemas + ~80 LOC migration.

---

## 2. Endpoint target

`POST /api/v1/operacion/salidas` con `SalidaCreateForzado`. Hosted en `api/v1/operacion.py::create_salida` (handler NUEVO, ~50 LOC adyacente al `create_ingreso` actual líneas 132-294). Router ya está reservado (`api/v1/__init__.py:143` → `r.include_router(operacion.router)`); sin cambios a `__init__.py`.

**Decisión de consolidación (vs. plan.md original):** plan.md línea 814 proponía DOS endpoints (`POST /operacion/salidas` rotación + `POST /operacion/salidas/mensualidad`). El input del orchestrator consolida a **un solo handler** que deriva `tipo_salida` server-side desde el flag `cobrar` de `prod.calcular_cotizacion`. Esta decisión:
- Reduce superficie de error (1 handler vs. 2).
- Reusa la decisión de tarifa vigente (F1.8 ya la hace atómicamente).
- Hace al cliente indiferente al path: envía `uuid_ingreso`, recibe `tipo_salida` en la respuesta.
- Mantiene equivalencia funcional: cliente puede derivar al endpoint "equivocado" — el server hace lo correcto.

El error `mensualidad_no_vigente` (400) del plan.md original queda cubierto por el caso `cobrar:false` con subscripción NO vigente al momento de salida → server responde `201` con `tipo_salida=ROTACION` (porque F1.8 detecta "no subscription at this branch" via `resolve_active_subscription_for_exit` y devuelve `cobrar:true` con desglose fiscal normal).

---

## 3. Tablas y modelos

| Tabla | Modelo | Estado F1.7 | Rol |
|---|---|---|---|
| `prod.ingreso` `[L-E]` | `models/L_E/ingreso.py` | SELECT (V1, V3) | PK lookup + read placa/fecha_ingreso/uuid_subscripcion_cliente |
| `prod.salidas` `[A]` | **FALTA `models/L_S/salida.py`** | INSERT nuevo (paso7) | Append-only event con partial unique index `one_exit_per_ingreso` (T-HU-F1.7-1) |
| `prod.subscripciones_cliente` `[V]` | `models/V/subscripciones_cliente.py` | SELECT (V2 via reuso F1.6) | Validar vigencia al momento de salida |
| `prod.subscripcion_vehiculos` `[V]` | junction | SELECT (V2 via reuso F1.6) | Join con subscripciones_cliente |
| `prod.vehiculos` `[V]` | `models/V/vehiculos.py` | SELECT (V3 via reuso F1.6) | placa match contra ingreso |
| `prod.calcular_cotizacion(p_uuid_ingreso uuid) RETURNS jsonb` | PL/pgSQL (migración 0022) | INVOKE (V5) | Lock FOR SHARE + compute tarifa vigente al momento salida |
| `prod.tarifas_sucursal` `[V]` | `models/V/tarifas_sucursal.py` | SELECT (vía F1.8 FOR SHARE) | KD-1 lock continuo |
| `prod.impuestos` `[V]` | `models/V/impuestos.py` | INSERT (migration 0026) | Inline-seed fila IVA (KD-IVA blocker) |
| `prod.alerta` `[L-W]` | `models/L_W/alerta.py` | INSERT (alertas V2/V5 bypassed) | Reuso verbatim de `repo/alerta.insertar_alerta_forzado` |
| `prod.mv_ocupacion_diaria` `[MV]` | (no model) | (read implícito vía V8 F1.6) | No tocado en F1.7 |

**Gap crítico pre-existente:** la tabla `prod.salidas` **existe en DB** desde migration 0001 (líneas 557-577, particionada mensualmente por `fecha_retencion_hasta`, trigger `fn_salidas_inmutable` línea 1990-2003, REVOKE UPDATE/DELETE línea 2923) — pero **no existe el modelo ORM** `Salida` en `models/L_S/`. Solo existen `sesion.py` y `login.py`. F1.7 debe crear `models/L_S/salida.py` (~40 LOC, basado en `LifecycleEventBase` con `audit`/`sync` mixins) o usar SQL crudo en el repo helper.

**Recomendación:** crear el ORM para mantener consistencia con F1.5/F1.6 (`Ingreso` usa `LifecycleEventBase`). El ORM sirve solo para el INSERT (no SELECT — el V1 ya trae el ingreso por PK vía `select(Ingreso)`).

**Definición operacional de "salida activa" para V8 (one_exit_per_ingreso):** índice único parcial `CREATE UNIQUE INDEX one_exit_per_ingreso ON prod.salidas (uuid_ingreso) WHERE NOT EXISTS (SELECT 1 FROM prod.anulaciones a WHERE a.uuid_salida = salidas.uuid AND a.estado='ejecutada')`. Mismo patrón que `unique_active_sesion_per_user` (migration 0023). El INSERT conflictivo produce `UniqueViolationError` que el handler mapea a `409 salida_duplicada`.

---

## 4. Validaciones V1..V5

### V1 — Ingreso activo existe

- `SELECT … FROM prod.ingreso WHERE uuid = :p AND vigente_hasta IS NULL AND NOT EXISTS (SELECT 1 FROM prod.salidas WHERE uuid_ingreso = :p)`.
- Si no encuentra fila → `404 {"error":"ingreso_no_encontrado", "uuid_ingreso":"..."}`. Razón unificada: cubre "uuid no existe", "ya tiene salida", "fue anulado" — todos equivalen operativamente a "no hay nada que cerrar".
- Sin bypass — un ingreso cerrado o inexistente no puede generar salida.

### V2 — Subscripción vigente al momento de salida

- Si el `ingreso.uuid_subscripcion_cliente IS NOT NULL` → reusa verbatim `repo.subscripcion_activa.validar_subscripcion_vigente(session, *, uuid_subscripcion_cliente, forzado=False)`.
- Si vigente → `ok`.
- Si `fecha_vencimiento < NOW()` o `estado != 'activo'` o `vigente_hasta IS NOT NULL` → 422 si no forzado, alerta si forzado.
- Justificación: la subscripción pudo vencer entre ingreso y salida (estacionamiento prolongado, suscripción mensual que expiró durante la estadía). Se re-valida al momento actual, no se confía en el snapshot del ingreso.

### V3 — Placa matches ingreso

- Reusa `repo/placa.detectar_tipo_vehiculo` (F1.6) sobre `payload.placa` Y compara con `ingreso.placa` case-insensitive normalizado (regex derivada en F1.6).
- Si mismatch → `422 {"error":"placa_no_coincide_con_ingreso", "placa_request":"ABC123", "placa_ingreso":"ABC123"}`.
- Sin bypass — discrepancia es bug del operador o intento de fraude, no estado operacional.
- Nota: el cliente puede NO enviar placa si conoce el uuid_ingreso (server lee del ingreso). Si envía placa, server la confirma.

### V4 — KD-FORZADO-01 prefix contract (reusado verbatim F1.6)

- `repo/ingreso.validar_kd_forzado(observaciones, forzado)` reusado sin modificación.
- Retorna `motivo` o `None`. Mismas reglas:
  - Sin prefijo + `forzado=true` → `422 {"error":"motivo_forzado_requerido"}`.
  - Con prefijo + `forzado=false` → `422 {"error":"forzado_contradiccion"}`.
  - Motivo < 10 chars tras el prefijo → `422 {"error":"motivo_forzado_insuficiente", "min_chars":10}`.
  - `forzado=true` + motivo válido → bypass permitido para V2 y/o V5.

### V5 — Tarifa vigente al momento de salida (vía F1.8 PL/pgSQL)

- Invoca `SELECT prod.calcular_cotizacion(:uuid_ingreso) AS payload` directamente via SQL crudo en `repo/salida.py` (NO usa `repo.cotizacion.cotizar_ingreso` que mapea a HTTPException — el F1.7 handler controla el flujo de excepciones).
- 3 outcomes:
  - `{"cobrar":true, subtotal, iva, total, tiempo_minutos, ...}` → INSERT salida con `tipo_salida=ROTACION`.
  - `{"cobrar":false, motivo:"mensualidad_vigente"}` → INSERT salida con `tipo_salida=MENSUALIDAD`. NO bypass — la mensualidad vigente al momento es el flujo normal esperado.
  - `{"error":"ingreso_no_encontrado"}` → 404 (cubierto por V1 antes).
  - `{"error":"tarifa_no_vigente"}` → 422 si no forzado; alerta `tarifa_vigente_forzado` si `forzado=true`.
  - `{"error":"iva_no_configurado"}` → **500** (KD-IVA ya resuelto por MIGRATION 0026 inline-seed; nunca debería ocurrir post-deploy).

**Lock continuidad (KD-1 invariante):** F1.7 invoca `calcular_cotizacion` **dentro de la misma transacción** que el INSERT de `salidas`. El `SELECT … FOR SHARE` sobre `tarifas_sucursal` se mantiene hasta el `session.commit()` del handler. Garantiza que la tarifa snapshot del cálculo es la misma que se usa para fines de auditoría (no hay ventana donde otra TX cierre la tarifa entre cotizar y registrar salida). Este invariante está documentado en F1.8 design.md §6 Cross-HU.

**Orden estricto (locked por AST walk):** V1 → V2 → V3 → V4 → V5 → INSERT → derivar tipo_salida → alertas → 201. Cualquier reordenación debe ser explícitamente justificada en proposal/design.

---

## 5. KD-FORZADO-01 (reutilizado de F1.6)

**Decisión:** KD-FORZADO-01 definido en F1.6 (archive `2026-09-14-hu-f1-6-validaciones-post-ingresos/design.md`) es contrato server-side canónico y se **reusa verbatim** en F1.7 sin modificación. Esto preserva:

- Una sola implementación: `repo/ingreso.validar_kd_forzado(observaciones, forzado) -> str | None`.
- Una sola prueba: `tests/unit/test_operacion_ingresos_kd_forzado.py` (4 tests ya existentes en F1.6) cubre el contrato compartido.
- Una sola auditoría: el formato `[FORZADO: <motivo ≥10 chars>]` es visible al admin y al log transaccional.

```python
# Reusado verbatim desde F1.6
from ..repo.ingreso import validar_kd_forzado  # NO se re-implementa en repo/salida.py

motivo = validar_kd_forzado(payload.observaciones, payload.forzado)
bypass_reason: str | None = "forzado" if motivo is not None else None
```

**Bypass scope en F1.7:** a diferencia de F1.6 (donde bypass aplica a V1+V2+V3+V6), en F1.7 el bypass aplica **solo a V2 (subscripción vencida) y V5 (tarifa no vigente)**. La justificación:

- V1 (ingreso activo existe) no es bypass-able — sin ingreso, no hay nada que cerrar.
- V3 (placa matches) no es bypass-able — discrepancia es bug, no estado operacional.
- V4 (KD-FORZADO-01) ES el bypass mismo.
- V5 (tarifa vigente) bypass-able: la tarifa pudo cerrar entre cotización y salida; forzar permite "cobrar con la última tarifa conocida" y registrar alerta.
- V2 (subscripción vencida) bypass-able: walk-in auditado (mensualidad que venció durante estadía prolongada — operador cobra rotación).

**Nuevas alertas (F1.7) que reutilizan el patrón de F1.6:**

1. `subscripcion_vencida_forzado` — solo si V2 fue salvada por bypass.
2. `tarifa_vigente_forzado` — solo si V5 fue salvada por bypass.

Ambas se siembran en MIGRATION 0026 junto con IVA (mismo `INSERT … ON CONFLICT (tipo_alerta) DO NOTHING` que 0025).

---

## 6. DEC / Reconciliaciones

### DEC-SUC-21-NEW — `tipo_salida` nunca columna

**Nueva decisión F1.7.** `tipo_salida = MENSUALIDAD | ROTACION` se deriva server-side desde el flag `cobrar` de `prod.calcular_cotizacion` y se devuelve en la respuesta `SalidaReadForzado`. NUNCA se persiste en `prod.salidas` (la tabla no tiene columna para ello, por diseño 4FN — al igual que `tipo_entrada` del ingreso DEC-SUC-21 en F1.6). La vista derivada `V_SALIDA_TIPO` puede montarse en HU futura si se requiere query directa; F1.7 NO la crea.

### DEC-SUC-23 — `salidas` sin columna de monto

**Confirmado.** El monto facturado vive en `prod.factura_detalle` (líneas 780-794 del ER) y se ensambla en CU-04. `salidas` es el evento "el vehículo salió"; el dinero va por otro camino. Plan.md línea 810 explícito: "ninguno persiste un monto en `salidas`".

### DEC-SAL-01 — Salida nunca UPDATE post-creación

**Nueva decisión F1.7.** Misma semántica que DEC-ANUL-01 para ingreso (F1.6). Una vez insertada, una salida es inmutable. La corrección se hace vía `prod.anulaciones(tipo_anulable='salida')` workflow (Fase 7+). F1.7 NO crea el workflow de anulación de salida — solo deja la puerta abierta vía `REVOKE UPDATE, DELETE` ya aplicado (migration 0001 línea 2923) + trigger `fn_salidas_inmutable` (líneas 1990-2003).

### DEC-IMP-01 — IVA sembrado en MIGRATION 0026

**Nueva decisión F1.7.** `impuestos.IVA` se siembra como parte de F1.7's apply phase. Razones:
- KD-IVA blocker de F1.8 (`exploration.md:121` y `verify-report.md:R1`) es bloqueante para el flujo completo.
- F1.6 ya estableció el patrón inline-seed en MIGRATION 0025 (`INSERT … ON CONFLICT (tipo_alerta) DO NOTHING`).
- Ownership sigue siendo HU-F14.2 Parte II pero el apply de F1.7 adelanta la dependencia crítica.

La fila sembrada es:

```sql
INSERT INTO prod.impuestos (
    uuid, codigo, nombre, porcentaje, vigente_desde, vigente_hasta, estado, created_at
) VALUES (
    gen_random_uuid(), 'IVA', 'IVA', 0.19,
    NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
) ON CONFLICT (codigo, vigente_desde) DO NOTHING;
```

`codigo='IVA'` es la UK01 de `impuestos` (modelo `models/V/impuestos.py:35`). El `ON CONFLICT` usa la UK constraint completa `(codigo, vigente_desde)`.

### DEC-IDEM-01 — Idempotencia via header, no vía `correlacion_id`

Confirmado. `Idempotency-Key` HTTP header (PR2) maneja retries. F1.7 NO agrega `correlacion_id` al INSERT.

### DEC-FORZADO-01 — Prefijo bypass Reusado verbatim F1.6. No hay desviación.

### DEC-MONO-01 — Un solo endpoint, derivación server-side

**Nueva decisión F1.7.** Consolida el plan original de 2 endpoints (`/salidas` + `/salidas/mensualidad`) en uno solo que deriva `tipo_salida` desde la respuesta de `calcular_cotizacion`. Trade-off: cliente pierde simetría con la UI anterior (que pre-clasificaba), pero gana garantía server-side + reduce superficie de bug + reusa lock atómico de F1.8.

---

## 7. Migración nueva

**MIGRATION 0026** (`backend/packages/parkos_core/migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py`):

```python
revision = "0026_seed_impuestos_iva_and_one_exit_per_ingreso"
down_revision = "0025_alerta_datos_nuevos"  # chain head actual
```

**4 operaciones (orden importa por dependencias):**

### Op 1 — Pre-flight (patrón F1.6 KD-7)

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

### Op 2 — Inline-seed `impuestos.IVA` (KD-IVA resolver)

```sql
INSERT INTO prod.impuestos (
    uuid, codigo, nombre, porcentaje, vigente_desde, vigente_hasta, estado, created_at
) VALUES (
    gen_random_uuid(), 'IVA', 'IVA', 0.19,
    NOW() AT TIME ZONE 'UTC', NULL, 'activo', NOW()
)
ON CONFLICT (codigo, vigente_desde) DO NOTHING;
```

**Porcentaje 0.19** = IVA Colombia 2026 (regulatory constant). Documentado en design.md §4 KD-IVA de F1.8 como el valor contractual; F1.7 respeta el mismo.

### Op 3 — Inline-seed 2 alert types (KD-FORZADO-01 + V2/V5 bypass)

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

Respeta el trigger `alert_types_inmutable` (migration 0013) — INSERT-only para rol_app.

### Op 4 — Partial unique index `one_exit_per_ingreso` (T-HU-F1.7-1)

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

`CONCURRENTLY` para no bloquear lecturas/escrituras en producción. `IF NOT EXISTS` para idempotencia. El INSERT conflictivo en handler produce `UniqueViolationError` que se mapea a `409 salida_duplicada`.

### Downgrade

```sql
DROP INDEX IF EXISTS prod.one_exit_per_ingreso;
DELETE FROM prod.alert_types WHERE tipo_alerta IN ('subscripcion_vencida_forzado', 'tarifa_vigente_forzado');
DELETE FROM prod.impuestos WHERE codigo='IVA' AND estado='activo';
```

`DELETE` corre como superuser (alembic) para bypassear el trigger `alert_types_inmutable`. El DELETE de `impuestos` puede chocar con `impuestos_inmutable` si existe — verificación pre-F1.7-apply pendiente (R8).

---

## 8. Auth pattern

```python
@router.post(
    "/salidas",
    response_model=SalidaReadForzado,
    status_code=201,
    summary="HU-F1.7: validated register of a vehicle exit (salida, [A] append-only)",
    responses={
        400: {"description": "missing_sucursal_context | mensualidad_no_vigente"},
        403: {"description": "tenant_scope_violation | sucursal_not_permitted"},
        404: {"description": "ingreso_no_encontrado"},
        409: {"description": "salida_duplicada"},
        422: {"description": "placa_no_coincide_con_ingreso | motivo_forzado_requerido | motivo_forzado_insuficiente | forzado_contradiccion | tarifa_vigente_no_encontrada | subscripcion_inactiva_o_vencida"},
        500: {"description": "iva_no_configurado (KD-IVA post-deploy)"},
    },
)
async def create_salida(
    response: Response,
    payload: SalidaCreateForzado,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),
) -> SalidaReadForzado:
```

KD-3 chain (post-HU-F1.2): `get_tenant_ctx` ya valida cross-tenant. Si pasa el handler, el resto opera dentro de sucursales_permitidas del JWT. Reuso del mismo `_ingreso_issuer_dep = requires_issuer("operador-", "admin-")` que `create_ingreso` (línea 86).

**Default `uuid_sucursal`:** derivado del `ingreso` encontrado en V1 (server-side, no del payload). El cliente no envía sucursal — el server la resuelve del ingreso. Si por alguna razón el `ingreso` no tiene `uuid_sucursal`, error 500 (debería ser imposible — `ingreso.uuid_sucursal` es NOT NULL).

**Tenant scope check (NUEVO en F1.7):** después de V1, verificar que `ingreso.uuid_sucursal == ctx.sucursal_uuid` (operador) o `in ctx.sucursales_permitidas` (admin). Si no → `403 tenant_scope_violation` con `uuid_ingreso` en el detail para debugging. Esto es un control de integridad nuevo vs F1.6 (donde el cliente enviaba `uuid_sucursal` y el server validaba). Justificación: previene que un operador de sucursal A cierre ingresos de sucursal B conociendo solo el UUID.

---

## 9. Locking + concurrencia

**Lock pesimista FOR SHARE en `tarifas_sucursal`** — replicado del F1.8 KD-1. El handler invoca `SELECT prod.calcular_cotizacion(:uuid_ingreso) AS payload` **dentro de la misma transacción** que el INSERT en `salidas`. El PL/pgSQL mantiene `FOR SHARE` lock sobre `tarifas_sucursal` hasta `session.commit()`.

**NO lock pesimista en `prod.ingreso` SELECT** — el SELECT por PK es atómico; el `EXISTS` subquery para verificar "no salida previa" es vulnerable a TOCTOU race, pero el partial unique index `one_exit_per_ingreso` (Op 4) cierra la ventana: si dos requests concurrentes intentan INSERT, el segundo recibe `UniqueViolationError` y se mapea a `409 salida_duplicada`. La latencia del SELECT vs INSERT es despreciable (< 5ms p99).

**Lock pesimista opcional en `prod.subscripciones_cliente`** — NO. Reusamos `validar_subscripcion_vigente` que es SELECT puro sin lock. Riesgo de subscripción cambiando de estado entre V2 y V5 es aceptable (es read-mostly; cambios son admin-actions infrecuentes).

**Orden de release:** el lock `FOR SHARE` se libera en `session.commit()` (línea ~50 del handler, mismo punto donde el INSERT se materializa). Garantía: la transacción cotizar→validar→INSERT es atómica; otra TX no puede modificar `tarifas_sucursal` mientras el handler corre.

**Concurrencia horizontal:** múltiples salidas en distintas sucursales no compiten por el mismo lock (lock es per-row, no per-table). Múltiples salidas en la misma sucursal sobre distintos `uuid_ingreso` tampoco compiten (cada una lockea su propia fila de `tarifas_sucursal` por combinación `(uuid_sucursal, uuid_tipo_vehiculo)`).

---

## 10. Handler pattern

Secuencia estricta de **12 pasos** (locked por AST walk `test_salida_handler_step_order.py`):

```python
async def create_salida(
    response: Response,
    payload: SalidaCreateForzado,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),
) -> SalidaReadForzado:
    no_store = no_store_headers()

    # --- Step 1: KD-3 (resolve ctx). ---------------------------
    # No target sucursal resolution from payload — server derives from ingreso.
    # (Different from F1.6 because cliente no envía sucursal en salida.)

    # --- Step 2: V1 (ingreso activo exists). -------------------
    ingreso = await repo_salida.buscar_ingreso_activo_por_uuid(session, uuid_ingreso=payload.uuid_ingreso)
    if ingreso is None:
        raise HTTPException(404, {"error": "ingreso_no_encontrado", "uuid_ingreso": str(payload.uuid_ingreso)}, headers=no_store)

    # --- Step 3: tenant scope (NUEVO). --------------------------
    target_sucursal = ingreso.uuid_sucursal
    if ctx.issuer_prefix == "operador-" and target_sucursal != ctx.sucursal_uuid:
        raise HTTPException(403, {"error": "tenant_scope_violation", "uuid_ingreso": str(payload.uuid_ingreso)}, headers=no_store)
    # admin- ya validado por get_tenant_ctx.

    # --- Step 4: V2 (subscripcion vigente al momento salida). --
    if ingreso.uuid_subscripcion_cliente is not None:
        sub_result = await validar_subscripcion_vigente(
            session,
            uuid_subscripcion_cliente=ingreso.uuid_subscripcion_cliente,
            forzado=bool(bypass_reason),
        )
        if not sub_result.vigente and not bypass_reason:
            raise HTTPException(422, {"error": "subscripcion_inactiva_o_vencida"}, headers=no_store)
        if not sub_result.vigente and bypass_reason:
            bypass_reason = "subscripcion_vencida"  # alerta diferenciada

    # --- Step 5: V3 (placa matches ingreso). -------------------
    if payload.placa is not None:
        tipo_placa = await detectar_tipo_vehiculo(session, payload.placa)
        tipo_ingreso = await detectar_tipo_vehiculo(session, ingreso.placa)
        if tipo_placa != tipo_ingreso:
            raise HTTPException(422, {
                "error": "placa_no_coincide_con_ingreso",
                "placa_request": payload.placa,
                "placa_ingreso": ingreso.placa,
            }, headers=no_store)

    # --- Step 6: V4 (KD-FORZADO-01 prefix contract). ----------
    motivo = validar_kd_forzado(payload.observaciones, payload.forzado)
    bypass_reason: str | None = "forzado" if motivo is not None else None

    # --- Step 7: V5 (tarifa vigente via F1.8 PL/pgSQL). --------
    cotizacion = await repo_salida.cotizar_para_salida(session, uuid_ingreso=payload.uuid_ingreso)
    # cotizacion is dict from jsonb; raises typed exceptions:
    #   IngresoNoEncontrado (cubierto por V1)
    #   TarifaNoVigente → 422 if not bypass_reason else alerta
    #   IVANoConfigurado → 500 (no debería ocurrir post-0026 deploy)
    tipo_salida: Literal["MENSUALIDAD", "ROTACION"]
    if cotizacion.get("cobrar") is False:
        tipo_salida = "MENSUALIDAD"
    else:
        tipo_salida = "ROTACION"
        if "tarifa_no_vigente" sentinel and not bypass_reason:
            raise HTTPException(422, {"error": "tarifa_vigente_no_encontrada"}, headers=no_store)
        if "tarifa_no_vigente" sentinel and bypass_reason:
            bypass_reason = "tarifa_no_vigente"

    # --- Step 8: INSERT salida [A] con motivo. -----------------
    new_attrs = {
        "uuid_sucursal": target_sucursal,
        "uuid_ingreso": payload.uuid_ingreso,
        "fecha_salida": datetime.now(UTC).replace(tzinfo=None),
        "fecha_retencion_hasta": date.today() + relativedelta(years=2),  # 2 años retención operacional
    }
    new_row = await repo_salida.crear_salida_evento(session, actor_uuid=ctx.actor_uuid, new_attrs=new_attrs)
    # UniqueViolationError → 409 salida_duplicada

    # --- Step 9: alertas (same TX, R5). ------------------------
    if bypass_reason == "subscripcion_vencida":
        await insertar_alerta_salida_forzado(
            session, uuid_sucursal=target_sucursal, uuid_salida=new_row.uuid,
            actor_uuid=ctx.actor_uuid, motivo=motivo or "(sin motivo)",
            tipo_alerta="subscripcion_vencida_forzado",
        )
    elif bypass_reason == "tarifa_no_vigente":
        await insertar_alerta_salida_forzado(
            session, uuid_sucursal=target_sucursal, uuid_salida=new_row.uuid,
            actor_uuid=ctx.actor_uuid, motivo=motivo or "(sin motivo)",
            tipo_alerta="tarifa_vigente_forzado",
        )

    await session.commit()

    # --- Step 10: derivar tipo_salida (DEC-SUC-21-NEW). -------
    # (Ya derivado en Step 7. Solo se documenta para AST walk.)

    # --- Step 11: response shape. -------------------------------
    apply_no_store_header(response)
    await session.refresh(new_row)
    return SalidaReadForzado(
        uuid=new_row.uuid,
        uuid_ingreso=new_row.uuid_ingreso,
        uuid_sucursal=new_row.uuid_sucursal,
        fecha_salida=new_row.fecha_salida,
        created_at=new_row.created_at,
        tipo_salida=tipo_salida,  # DEC-SUC-21-NEW: derivado, no persistido
        forzado_en_creacion=bypass_reason is not None,
        motivo_forzado=motivo if bypass_reason else None,
        cotizacion_snapshot=CotizarFacturacion.model_validate(cotizacion) if tipo_salida == "ROTACION" else None,
    )
```

**Lock continuidad Step7→8→9:** el lock `FOR SHARE` adquirido en Step 7 vía `calcular_cotizacion` se mantiene durante el INSERT (Step 8) y el INSERT de alerta (Step 9) hasta `session.commit()` (Step 9 final). Garantía transaccional: la tarifa snapshot del cálculo es la misma que se usa para auditoría.

**Alerta en misma TX (R5):** mismo patrón que F1.6. Un solo `commit()` materializa salida + alerta atómicamente.

---

## 11. Repositorio nuevo / modificado

### NEW: `repo/salida.py` (~180 LOC)

```python
"""HU-F1.7 / REQ-OPS-042..046 — Salida lifecycle (rotación + mensualidad).

Helpers para ``POST /operacion/salidas``:
- ``buscar_ingreso_activo_por_uuid`` (V1)
- ``cotizar_para_salida`` (V5 wrapper sobre F1.8 PL/pgSQL, raises typed exceptions)
- ``crear_salida_evento`` (Step 8, INSERT [A] via raw SQL)
- ``insertar_alerta_salida_forzado`` (Step 9, alertas V2/V5 bypassed)
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.L_E.ingreso import Ingreso
from ..models.L_S.salida import Salida  # NEW ORM model (created in F1.7)
from ..repo.cotizacion import (
    CotizacionError, IngresoNoEncontrado, IVANoConfigurado, TarifaNoVigente
)


class SalidaDuplicada(Exception):
    """409 — partial unique index ``one_exit_per_ingreso`` violated."""


async def buscar_ingreso_activo_por_uuid(session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID) -> Ingreso | None:
    """V1: SELECT ingreso WHERE uuid=:p AND NOT EXISTS salidas (no anulada)."""
    stmt = text("""
        SELECT i.* FROM prod.ingreso i
        WHERE i.uuid = :uuid AND i.vigente_hasta IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM prod.salidas s
            WHERE s.uuid_ingreso = i.uuid
              AND NOT EXISTS (
                SELECT 1 FROM prod.anulaciones a
                WHERE a.uuid_salida = s.uuid
                  AND a.tipo_anulable = 'salida'
                  AND a.estado = 'ejecutada'
              )
          )
    """)
    row = (await session.execute(stmt, {"uuid": str(uuid_ingreso)})).first()
    if row is None:
        return None
    # Map raw row → ORM Ingreso (read-only, no flush needed).
    return await session.get(Ingreso, uuid_ingreso)


async def cotizar_para_salida(session: AsyncSession, *, uuid_ingreso: uuid_lib.UUID) -> dict[str, Any]:
    """V5: invoke ``prod.calcular_cotizacion(:uuid_ingreso)`` and return jsonb payload.

    Reusa el wrapper de F1.8 (``repo.cotizacion.cotizar_ingreso``) — la diferencia
    con el GET /cotizar es solo que aquí NO se mapea a HTTPException; el handler
    de F1.7 controla el flujo de excepciones para insertar alertas si bypass.
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

    NO usa ``repo.event.record_event`` porque ``salidas`` es ``[A]`` (audit), no
    ``[L-E]`` (lifecycle event). La tabla tiene REVOKE UPDATE/DELETE ya aplicado
    (migration 0001 línea 2923) + trigger ``fn_salidas_inmutable`` (líneas 1990-2003). El partial unique index ``one_exit_per_ingreso`` (migration 0026)
    cierra la ventana TOCTOU.

    Raises:
        SalidaDuplicada: ``IntegrityError`` con código ``UniqueViolation``
                        sobre el índice parcial — mapeado a 409 por el handler.
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
        # psycopg2/asyncpg: UniqueViolationError code 23505
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
) -> None:
    """Step 9: INSERT ``prod.alerta`` for V2/V5 bypass."""
    from ..models.L_W.alerta import Alerta
    alerta = Alerta(
        uuid_sucursal=uuid_sucursal,
        uuid_usuario=actor_uuid,
        tipo_alerta=tipo_alerta,
        estado="abierta",
        timestamp_evento=datetime.now(UTC).replace(tzinfo=None),
        uuid_arqueo=None,
        datos_nuevos={"motivo": motivo, "uuid_salida": str(uuid_salida)},
    )
    session.add(alerta)
    await session.flush()
```

### NEW: `models/L_S/salida.py` (~40 LOC)

Basado en `LifecycleEventBase` (mismos mixins que `Ingreso`):

```python
"""ORM model for ``prod.salidas`` (vehicle exit [A] table, HU-F1.7).

The ``salidas`` table exists in DB since migration 0001 (lines 557-577)
but had no ORM mapping — this model closes the gap.

Writes MUST go through ``repo.salida.crear_salida_evento`` (DEC-SAL-01:
append-only). Defense in depth at DB layer: REVOKE UPDATE/DELETE
(migration 0001 línea 2923) + ``fn_salidas_inmutable`` trigger
(líneas 1990-2003).

Partial unique index ``one_exit_per_ingreso`` (migration 0026) prevents
duplicate exits for the same ingreso (unless the previous one was
annulled). INSERT conflict produces ``UniqueViolationError`` mapped to
``409 salida_duplicada``.
"""
from __future__ import annotations

import uuid as uuid_lib
from datetime import date, datetime

from sqlalchemy import Date, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import LifecycleEventBase


class Salida(LifecycleEventBase):
    """[A] Vehicle exit event — closes the estancia."""

    __tablename__ = "salidas"

    uuid_sucursal: Mapped[uuid_lib.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    uuid_ingreso: Mapped[uuid_lib.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    fecha_salida: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    fecha_retencion_hasta: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        {
            "schema": "prod",
            "extend_existing": True,
        },
    )


__all__ = ["Salida"]
```

### NEW: `repo/impuestos.py` (~50 LOC)

```python
"""HU-F1.7 — inline-seed helper for ``prod.impuestos`` (KD-IVA resolver).

Provides read access to the canonical IVA tax row (codigo='IVA',
porcentaje=0.19). The row itself is inserted by migration 0026 via
``INSERT … ON CONFLICT (codigo, vigente_desde) DO NOTHING``.

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
    """Return True iff ``prod.impuestos`` has a vigente row with codigo='IVA'."""
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

### Reuso (NO modificar)

- `repo/ingreso.validar_kd_forzado` (F1.6) — V4 prefix contract verbatim.
- `repo/subscripcion_activa.validar_subscripcion_vigente` (F1.6) — V2 revalidación.
- `repo/subscripcion_activa.resolve_active_subscription_for_exit` (F1.6 lifted) — uso interno en F1.8 PL/pgSQL; F1.7 NO lo llama directamente (F1.8 ya lo hace via SQL port).
- `repo/cotizacion.cotizar_ingreso` (F1.8) — V5 thin wrapper.
- `repo/placa.detectar_tipo_vehiculo` (F1.6) — V3 placa match.
- `repo/alerta.insertar_alerta_forzado` (F1.6) — patrón de INSERT; F1.7 crea `insertar_alerta_salida_forzado` con `datos_nuevos` shape diferente (`uuid_salida` en lugar de `uuid_ingreso`).

### Modificaciones

- `api/v1/operacion.py` (+200 LOC handler `create_salida` + 12 imports nuevos).
- `schemas/operacion.py` (+80 LOC: `SalidaCreateForzado`, `SalidaReadForzado`, 4 typed errors).

### NO tocado (deliberado)

- `api/v1/__init__.py` — router ya está incluido.
- `auth/tenancy.py` — `get_tenant_ctx` ya validado en F1.2.
- `api/deps.py` — `requires_issuer` reusado.
- `models/L_E/ingreso.py` — V1 hace read-only.
- `migrations/versions/0022_create_calcular_cotizacion.py` — la PL/pgSQL no cambia; F1.7 la invoca.

---

## 12. Schemas nuevos

`schemas/operacion.py` (MODIFICAR, +80 LOC):

```python
class SalidaCreateForzado(_Base):
    """INSERT payload for ``prod.salidas`` ([A] append-only event, HU-F1.7).

    Identifica el ingreso a cerrar. La sucursal se resuelve server-side
    del ingreso (NUEVO en F1.7 — cliente no envía). La placa es opcional:
    si se envía, server la confirma contra el ingreso (V3); si no, server
    confía en el uuid_ingreso.

    ``extra='forbid'`` (heredado de ``_Base``) rechaza campos extra,
    incluyendo intentos de inyectar ``tipo_salida`` (DEC-SUC-21-NEW).
    """
    # REQUERIDO — ingreso a cerrar
    uuid_ingreso: uuid_lib.UUID

    # OPTIONAL — placa a confirmar contra ingreso (V3)
    placa: str | None = None

    # OPTIONAL — observaciones con prefijo KD-FORZADO-01 si aplica (V4)
    observaciones: str | None = None

    # OPTIONAL — bypass para V2 y/o V5
    forzado: bool = False


class SalidaReadForzado(_Base):
    """Response shape for ``POST /operacion/salidas`` (HU-F1.7).

    Additive delta to ``SalidaRead``:
    - ``tipo_salida``: Literal['MENSUALIDAD', 'ROTACION'] (DEC-SUC-21-NEW, derivado server-side)
    - ``forzado_en_creacion``: True iff KD-FORZADO-01 bypass fue usado
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


# --- Typed error schemas (D-HU-F1.7-9) ----------------------------------

class IngresoNoEncontradoError(_Base):
    """V1 404 discriminator — uuid_ingreso no existe o ya cerrado."""
    error: Literal["ingreso_no_encontrado"]
    uuid_ingreso: uuid_lib.UUID


class SalidaDuplicadaError(_Base):
    """Step 8 409 discriminator — partial unique index violated."""
    error: Literal["salida_duplicada"]
    uuid_ingreso: uuid_lib.UUID


class PlacaNoCoincideConIngresoError(_Base):
    """V3 422 discriminator."""
    error: Literal["placa_no_coincide_con_ingreso"]
    placa_request: str
    placa_ingreso: str


class TarifaVigenteNoEncontradaError(_Base):
    """V5 422 discriminator (when not bypassed)."""
    error: Literal["tarifa_vigente_no_encontrada"]
```

`extra='forbid'` (heredado de `_Base`) en todos. El cliente no puede inyectar `tipo_salida` ni `cotizacion_snapshot` — ambos son derivados server-side.

---

## 13. KD preliminares

- **KD-S1**: `404 ingreso_no_encontrado` cubre "uuid no existe" + "ya tiene salida" + "fue anulado" — todos equivalen a "no hay nada que cerrar". Simplifica taxonomía de errores.
- **KD-S2**: Tenant scope check **post-V1** (no pre-V1 como F1.6). Justificación: si el operador no tiene acceso al uuid_ingreso, no gana nada devolver 403 antes de validar que existe — UX peor. Mejor 404 primero (defense in depth: no leak info), luego 403 si existe.
- **KD-S3**: Placa opcional en payload. Cliente puede conocer uuid_ingreso sin recordar placa. Si envía, server confirma (V3). Si no envía, server confía.
- **KD-S4**: `cotizacion_snapshot` en respuesta solo cuando `tipo_salida=ROTACION`. Cuando `MENSUALIDAD`, el cliente no necesita el desglose fiscal (no cobra). El response shape es más pequeño y la lógica del cliente más simple.
- **KD-S5**: Tipo de alerta diferenciado por bypass_reason (`subscripcion_vencida_forzado` vs `tarifa_vigente_forzado`). Permite reporting diferenciado sin unión de strings en queries.
- **KD-S6**: `fecha_retencion_hasta` se computa server-side como `fecha_salida + 2 años` (retención operacional, particionamiento mensual). Coherente con patrón de otras tablas `[A]` (`anulaciones`, `reimpresion_ticket`).
- **KD-S7**: Lock continuidad Step 7→8→9 garantizada por una sola TX. Handler NO usa `sub-transactions` ni `SAVEPOINT`. El `await session.commit()` único libera el lock FOR SHARE y materializa INSERTs atómicamente.
- **KD-S8**: MIGRATION 0026 es **precondición runtime** del F1.7. Si el deploy omite 0026, el F1.7 handler devuelve `500 iva_no_configurado` en cada salida. Documentar en design.md §10 Rollback Plan.

---

## 14. Test patterns

Total: **14 tests** distribuidos (más que el mínimo 12 por la complejidad del flujo derivativo).

### `tests/unit/test_operacion_salidas.py` (~400 LOC, 10 tests)

```python
# Rotación (4 tests)
async def test_salida_rotacion_exitosa(): ...           # T1: 201 + tipo_salida=ROTACION + cotizacion_snapshot
async def test_salida_rotacion_sin_tarifa_vigente(): ...  # T2: 422 tarifa_vigente_no_encontrada (F1.8 KD-3 propagado)
async def test_salida_rotacion_forzada_con_alerta(): ... # T3: 201 + tipo_salida=ROTACION + alerta tarifa_vigente_forzado
async def test_salida_rotacion_duplicada_409(): ...     # T4: second POST same uuid_ingreso → 409

# Mensualidad (4 tests)
async def test_salida_mensualidad_vigente_exitosa(): ...    # T5: 201 + tipo_salida=MENSUALIDAD + cotizacion_snapshot=None
async def test_salida_mensualidad_vencida_forzada(): ...    # T6: 422 subscripcion_inactiva_o_vencida (without forzado)
async def test_salida_mensualidad_vencida_con_forzado(): ... # T7: 201 + tipo_salida=ROTACION (F1.8 retorna cobrar:true) + alerta subscripcion_vencida_forzado
async def test_salida_mensualidad_placa_no_coincide(): ...  # T8: 422 placa_no_coincide_con_ingreso

# KD-FORZADO (2 tests)
async def test_salida_kd_forzado_prefijo_valido(): ...      # T9: motivo ≥10 chars → bypass activo
async def test_salida_kd_forzado_motivo_insuficiente(): ... # T10: motivo 9 chars → 422 motivo_forzado_insuficiente
```

### `tests/integration/test_salida_create_db.py` (~250 LOC, 3 tests DB)

- `test_insert_salida_con_alerta_forzado_atomico`: real DB, both INSERTs in single commit, rollback test.
- `test_partial_unique_index_emite_409`: real DB, two threads, one succeeds one fails.
- `test_iva_no_sembrado_retorna_500`: real DB, DELETE the IVA row, attempt salida, expect 500.

### AST walks

- `tests/static/test_salida_handler_step_order.py` (~100 LOC): 12-step order locked.
- `tests/static/test_no_write_after_salida_insert.py` (~100 LOC): rechaza UPDATE/DELETE/TRUNCATE en repo/salida.py.

---

## 15. Open questions para propose/design

1. **KD-S1 confirmación**: ¿`404 ingreso_no_encontrado` unificado para "no existe / ya cerrado / anulado" es aceptable? Propuesta: unificar en 404.
2. **KD-S2 orden tenant scope**: ¿404 antes de 403 (defense in depth) o 403 antes de 404 (leak prevention)? Propuesta: 404 primero.
3. **KD-S3 placa opcional**: ¿cliente siempre envía placa, o es opcional? Propuesta: opcional.
4. **KD-S4 `cotizacion_snapshot` en respuesta**: ¿se incluye cuando `tipo_salida=MENSUALIDAD`? Propuesta: NO.
5. **KD-S6 `fecha_retencion_hasta`**: ¿2 años desde `fecha_salida` o desde `now()`? Propuesta: 2 años desde `fecha_salida`.
6. **KD-S8 MIGRATION 0026 ordering**: el apply de F1.7 corre **antes** que cualquier test del F1.7. 0026 es la chain head de F1.7.
7. **DEC-SUC-23-NEW**: confirmar que el handler NO inserta ningún campo de monto en `prod.salidas`.
8. **Lock scope en alertas**: `alerta` es append-only `[L-W]`, no requiere lock adicional.
9. **Idempotency-Key header**: ¿F1.7 debe declararlo como REQUIRED en el endpoint? F1.6 lo hace para `POST /ingresos`. Propuesta: SÍ — mismo patrón.
10. **MIGRATION 0026 idempotency test**: test explícito que verifique que 0026 puede correr 2 veces seguidas sin error (idempotente).

---

## 16. Artifacts + Riesgos (R1..R9)

### Artifacts

```
openspec/changes/hu-f1-7-salidas/exploration.md        ← este archivo
openspec/changes/hu-f1-7-salidas/proposal.md
openspec/changes/hu-f1-7-salidas/specs/operational/spec.md
openspec/changes/hu-f1-7-salidas/design.md
openspec/changes/hu-f1-7-salidas/tasks.md
openspec/changes/hu-f1-7-salidas/verify-report.md
openspec/changes/archive/2026-09-14-hu-f1-7-salidas/archive-report.md
```

**Backend (NEW):**
- `migrations/versions/0026_seed_impuestos_iva_and_one_exit_per_ingreso.py` (~120 LOC)
- `models/L_S/salida.py` (~40 LOC)
- `repo/salida.py` (~180 LOC)
- `repo/impuestos.py` (~50 LOC)

**Backend (MODIFY):**
- `api/v1/operacion.py` (+200 LOC handler `create_salida`)
- `schemas/operacion.py` (+80 LOC: SalidaCreateForzado, SalidaReadForzado, 4 typed errors)

**Tests (NEW):**
- `tests/unit/test_operacion_salidas.py` (~400 LOC, 10 tests)
- `tests/unit/test_operacion_salidas_kd_forzado.py` (~80 LOC, 2 tests)
- `tests/integration/test_salida_create_db.py` (~250 LOC, 3 tests)
- `tests/static/test_salida_handler_step_order.py` (~100 LOC, 1 AST walk)
- `tests/static/test_no_write_after_salida_insert.py` (~100 LOC, 1 AST walk)

**NOT TOUCHED (deliberado):**
- `api/v1/__init__.py`
- `auth/tenancy.py`, `api/deps.py`
- `models/L_E/ingreso.py`
- `migrations/versions/0022_create_calcular_cotizacion.py` (F1.8 PL/pgSQL no cambia)
- `repo/event.py`, `repo/cotizacion.py` (reusados sin modificación)
- `repo/ingreso.py` (validar_kd_forzado reusado)
- `repo/subscripcion_activa.py` (validar_subscripcion_vigente + resolve_active_subscription_for_exit reusados)

### Riesgos

| # | Riesgo | Severidad | Mitigación |
|---|---|---|---|
| **R1** | KD-IVA blocker: `impuestos.IVA` no sembrado | **CRÍTICA** | MIGRATION 0026 inline-seed `INSERT … ON CONFLICT (codigo, vigente_desde) DO NOTHING` — resuelve blocker pre-F1.7-deploy. Pre-flight abort si tabla no existe. |
| **R2** | `Salida` ORM model no existe (gap pre-existente) | Alta | F1.7 crea `models/L_S/salida.py` (~40 LOC, basado en `LifecycleEventBase`). Test coverage en T11 (DB integration). |
| **R3** | Lock continuidad Step 7→8→9 | Alta | Una sola TX, handler NO usa sub-transactions. AST walk verifica que NO hay `session.commit()` intermedio. Test T11 verifica atomicidad. |
| **R4** | TOCTOU race en V8 (no-duplicado) | Media | Partial unique index `one_exit_per_ingreso` (MIGRATION 0026 Op4) cierra ventana. `UniqueViolationError` → 409. Test T12 verifica con `asyncio.gather` 2 concurrentes. |
| **R5** | V8 EXISTS subquery vs index | Baja | `prod.salidas` tiene índice sobre `uuid_ingreso` (FK implícita). EXISTS subquery < 5ms p99. Test performance mide < 50ms end-to-end. |
| **R6** | DEC-SUC-23-NEW verificación: handler no inserta monto en `salidas` | Baja | AST walk `test_no_write_after_salida_insert.py` verifica que `new_attrs` no contiene `valor`/`total`/`subtotal`. Code review en design.md §11. |
| **R7** | Orden estricto V1→V2→V3→V4→V5 | Media | AST walk `test_salida_handler_step_order.py` verifica orden literal. Mismo patrón que F1.6. |
| **R8** | `impuestos_inmutable` trigger puede bloquear DELETE en downgrade | Baja | Verificación pre-F1.7-apply: `grep impuestos_inmutable migrations/` debe confirmar si existe. Si existe, downgrade 0026 falla → documentar workaround (NO downgrade en producción; en su lugar crear migration compensatoria). |
| **R9** | Placa opcional puede ocultar typos del operador | Baja | Si cliente NO envía placa, server confía en uuid_ingreso. UI debe requerir confirmación visual previa. Documentar en `docs/`. |

---

**Explored by**: sdd-explore (sub-agent `a20a7dab4f51f2c83`).
**Engram**: persisted `sdd/hu-f1-7-salidas/explore` (id 1546).
**Next recommended**: `sdd-propose HU-F1.7`.

## Key Learnings

1. The `salidas` table exists in DB since migration 0001 (lines 557-577) but has no ORM model — F1.7 must create `models/L_S/salida.py` to close the pre-existing gap, not just modify code.
2. F1.8 `calcular_cotizacion` is `VOLATILE` not `STABLE` (REQ-OPS-025 deviation letter, user approved 2026-09-14), which means F1.7 must invoke the PL/pgSQL function inline within the same transaction as the salida INSERT to keep `FOR SHARE` lock continuity.
3. KD-IVA blocker resolved inline in F1.7 MIGRATION 0026 via `INSERT … ON CONFLICT (codigo, vigente_desde) DO NOTHING` pattern, mirroring F1.6 MIGRATION 0025 alert_type seed.
4. Partial unique index `one_exit_per_ingreso` (migration 0026 Op 4) is the defense-in-depth closure for the TOCTOU race on V8 EXISTS subquery.
5. DEC-SAL-01 establishes "salida never UPDATE post-creation" by reusing the existing `REVOKE UPDATE, DELETE` on `prod.salidas` + `fn_salidas_inmutable` trigger.
6. Consolidation decision: one handler `POST /operacion/salidas` derives `tipo_salida` server-side from F1.8 `cobrar` flag, instead of plan.md's two-endpoint design.
