# Exploration: HU-F1.6 — Validaciones reales en `POST /operacion/ingresos`

> **Change**: `hu-f1-6-validaciones-post-ingresos`
> **Phase**: explore (sdd-explore)
> **HU**: HU-F1.6 — Server-side enforcement of regex placa, mensualidad/rotación derivation, cupo via `mv_ocupacion_diaria`, KD-FORZADO prefix audit, no-duplicate active ingreso on the existing `POST /api/v1/operacion/ingresos` endpoint (modifies the handler F1.5 left as a thin pass-through).
> **Date**: 2026-09-14
> **Working dir**: `E:/easypunto_parkos`
> **Branch**: `feat/fase-1-prerequisites-backend` (HEAD `e1cc79b`; F1.1..F1.5 archivadas, F1.6 es el siguiente)
> **PR target**: `origin/dev`

## 1. Contexto de la HU

HU-F1.6 cierra el prerequisito backend de F6 — Ingreso vehicular (CU-01). Hasta F1.5, el endpoint `POST /api/v1/operacion/ingresos` (introducido en PR5) era un thin pass-through a `repo.event.record_event` (`operacion.py:105`): aceptaba el `IngresoCreate`, lo insertaba como `[L-E]` event sin validar nada del lado servidor. Las 4 validaciones que el CU-01 exige (regex de placa, detección mensualidad/rotación, cupo disponible vía `mv_ocupacion_diaria`, no-duplicado de placa activa en la sucursal) vivían exclusivamente en el cliente Electron (`web_sucursal/src/lib/validation/placa.ts`, A-03). Eso viola la regla "single source of truth" del corpus y crea un riesgo concreto: un cliente desactualizado o un consumidor alterno (admin web, integración futura, replay de cola) puede saltarse la validación y ensuciar `prod.ingreso` con filas inválidas.

F1.6 mueve **toda** la validación al backend y la aplica de forma consistente con DEC-SUC-11 (cupo siempre vía `mv_ocupacion_diaria`), DEC-SUC-22 (regex estricta), DEC-SUC-21 (tipo_entrada derivado), A-04 (forzado via prefijo `[FORZADO:` ≥10 chars, sin columna nueva). La respuesta agrega `tipo_entrada` (`MENSUALIDAD | ROTACION`) derivado server-side.

Tamaño: **260 LOC** (plan.md línea 787).

## 2. Endpoint target

`POST /api/v1/operacion/ingresos` con `IngresoCreateForzado`. Hosted en `api/v1/operacion.py::create_ingreso` (handler actual líneas 92-114). NO crea nuevo endpoint — la URL ya está reservada. F1.5 NO toca el `api/v1/__init__.py`.

## 3. Tablas y modelos

| Tabla | Modelo | Estado |
|---|---|---|
| `prod.ingreso` `[L-E]` | `models/L_E/ingreso.py` | insert-only (LifecycleEventBase + record_event) |
| `prod.tipos_vehiculo` `[V]` | `models/V/tipos_vehiculo.py` | vigente = `vigente_hasta IS NULL AND estado='activo'` |
| `prod.cantidad_vehiculos_sucursal` `[V]` | `models/V/cantidad_vehiculos_sucursal.py` | bi-temporal UK01 |
| `prod.mv_ocupacion_diaria` `[MV]` | (no model) | refresca cada 10s (post-F1.5) |
| `prod.tarifas_sucursal` `[V]` | `models/V/tarifas_sucursal.py` | bi-temporal post-F1.4 vigente_en |
| `prod.subscripciones_cliente` `[V]` | `models/V/subscripciones_cliente.py` | vigente = fecha_vencimiento >= NOW() |
| `prod.subscripcion_vehiculos` `[V]` | junction | post-PR4 |
| `prod.vehiculos` `[V]` | `models/V/vehiculos.py` | UK01 por placa |
| `prod.alerta` `[L-W]` | `models/L_W/alerta.py` | insert-only; uso para capacidad_agotada_forzado |

Definición operacional de "ingreso activo" para V8 (no-duplicado): `EXISTS (SELECT 1 FROM prod.ingreso i WHERE uuid_sucursal=X AND placa=Y AND NOT EXISTS (salidas no anuladas) AND NOT EXISTS (anulaciones ejecutadas))`. NO usa la MV (sería stale); va directo a las tablas (authoritative).

## 4. Validaciones V1..V9

### V1 — Cupo no configurado
- Sin fila en `cantidad_vehiculos_sucursal` para `(X, T)`.
- Si `forzado != true` → `422 {"error": "cupo_no_configurado", "forzado_permitido": true}`.
- Si `forzado=true` con prefijo válido → INSERT + alerta.

### V2 — Cupo disponible
- `cupo_maximo > 0` AND `activos >= cupo_maximo`.
- Si `forzado != true` → `422 {"error": "motivo_forzado_requerido", "cupo_maximo": N, "activos": N}`.
- Si `forzado=true` con prefijo válido → INSERT + alerta.

### V3 — Tarifa vigente
- Sin fila en `tarifas_sucursal` con `bitemporal_vigente_predicate(at)` para `(X, T)`.
- `422 {"error": "tarifa_vigente_no_encontrada"}` si no forzado.
- `forzado=true` permite (auditado).

### V4 — Tipo vehículo válido
- `422 {"error": "tipo_vehiculo_invalido"}` si UUID no existe o `vigente_hasta IS NOT NULL`. SIN bypass — bug del cliente.

### V5 — Regex placa Colombia
- Patrones: `^[A-Z]{3}[0-9]{3}$` (Auto) | `^[A-Z]{3}[0-9]{2}[A-Z]$` (Moto).
- `422 {"error": "placa_formato_invalido", "formatos_aceptados": [...]}`.
- Server **DERIVA** `uuid_tipo_vehiculo` desde regex y SOBREESCRIBE el del cliente (BR2 CU-01).
- Sin CHECK constraint (configurable futuro).

### V6 — Subscripción vigente
- Sin `vigente_hasta IS NULL AND estado='activo' AND fecha_vencimiento >= NOW()` para `uuid_subscripcion_cliente` provided.
- `422 {"error": "subscripcion_inactiva_o_vencida"}` si no forzado.
- `forzado=true` permite (walk-in auditado).

### V7 — Bi-temporal canónico
- Tarifas + cantidad consultados con `vigente_desde <= NOW() AND (vigente_hasta IS NULL OR vigente_hasta > NOW()) AND estado='activo'`. Reusa `bitemporal_vigente_predicate` de F1.4.

### V8 — No-duplicado activo
- `EXISTS` en `prod.ingreso` con `(uuid_sucursal, placa)` sin salida no anulada.
- `409 {"error": "ingreso_activo_existente", "uuid_ingreso_existente": "..."}`. Cliente deriva a `SalidaFlow`.

### V9 — Derivación `tipo_entrada`
- `tipo_entrada = "MENSUALIDAD" if uuid_subscripcion_cliente else "ROTACION"`.
- Devuelto en `IngresoReadForzado`, NUNCA persistido en `prod.ingreso` (DEC-SUC-21).

### KD-FORZADO-01 (decisión nueva)

**El ÚNICO bypass operacional a V1/V2/V3/V6 es `forzado=true` con prefijo `[FORZADO: <motivo ≥10 chars>]`**.

```python
FORZADO_PREFIX = "[FORZADO: "
FORZADO_MIN_MOTIVO_CHARS = 10

def validar_kd_forzado(observaciones: str | None, forzado: bool) -> str | None:
    if not forzado:
        if observaciones and observaciones.startswith(FORZADO_PREFIX):
            raise HTTPException(422, {"error": "forzado_contradiccion"})
        return None
    if not observaciones or not observaciones.startswith(FORZADO_PREFIX):
        raise HTTPException(422, {"error": "motivo_forzado_requerido"})
    motivo = observaciones[len(FORZADO_PREFIX):].rstrip("]")
    if len(motivo.strip()) < FORZADO_MIN_MOTIVO_CHARS:
        raise HTTPException(422, {"error": "motivo_forzado_insuficiente", "min_chars": 10})
    return motivo.strip()
```

Alerta: si `forzado=true` AND motivo válido AND V2 fue bypassed → INSERT `prod.alerta` con `tipo_alerta='capacidad_agotada_forzado'`, `estado='abierta'`, motivo en `datos_nuevos` (jsonb).

## 5. DEC / Reconciliaciones

### DEC-SUC-11 — Cupo siempre vía `mv_ocupacion_diaria`
Confirmado. V1+V2 consultan `mv_ocupacion_diaria` (post-F1.5) vía `repo/ocupacion.py::get_ocupacion_puros_activos`.

### DEC-SUC-21 — `tipo_entrada` nunca columna
Confirmado. Derivado server-side, devuelto en respuesta, NUNCA persistido en `prod.ingreso`.

### DEC-SUC-22 — Regex estricta, sin tolerancia
Confirmado. V5 usa regex exactas. NO normalización O↔0/I↔1 (esa vive en `buscarIngresoTolerante` F1.7).

### A-03 — Regex hardcoded por ahora
Constante a nivel de módulo en `repo/placa.py`. KD-V2 abierto.

### A-04 — Forzado via prefijo, sin columna
Confirmado. KD-FORZADO-01 contrato server-side.

### DEC-FORZADO-01 (nueva propuesta F1.6)
Documentada en design.md.

### DEC-ANUL-01 — `ingreso` nunca UPDATE post-creación
Out of scope F1.6. Workflow de anulación vive en `prod.anulaciones` (Fase 7+).

### DEC-IDEM-01 — Idempotencia via header, no vía `correlacion_id`
Ya cubierto por `Idempotency-Key` HTTP header (PR2). F1.6 NO agrega `correlacion_id`.

## 6. Migración nueva

**NINGUNA**. Validación server-side en V5 cubre regex; CHECK constraint rígida bloquearía migración nacional futura.

`capacidad_agotada_forzado` ya sembrado en F1.14 (post-DEC-SUC-14).

## 7. Auth pattern

```python
@router.post("/ingresos", response_model=IngresoReadForzado, status_code=201)
async def create_ingreso(
    payload: IngresoCreateForzado,
    response: Response,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(get_tenant_ctx),
    _claims: None = Depends(_ingreso_issuer_dep),
) -> IngresoReadForzado:
```

KD-3 chain (post-HU-F1.2): `get_tenant_ctx` ya valida cross-tenant. Si pasa el handler, el resto del flow opera dentro de sucursales_permitidas del JWT.

Default `uuid_sucursal`: si None en payload → `ctx.sucursal_uuid`; si sigue None → `400 missing_sucursal_context`.

## 8. Locking + concurrencia

INSERT simple sin lock explícito. Cupo via `mv_ocupacion_diaria` con lag máximo 10s (post-F1.5 worker) — eventual consistency aceptable (RIESGO-SUC-02). NO `SELECT FOR UPDATE`.

## 9. Handler pattern

Secuencia estricta:
1. KD-3 (target_sucursal + tenant scope)
2. V5 regex placa → tipo derivado
3. V4 tipo vehículo vigente
4. KD-FORZADO-01 (validar prefijo si aplica)
5. V1+V2 (cupo)
6. V3 (tarifa vigente)
7. V6 (subscripción si provided)
8. V8 (no-duplicado activo)
9. INSERT `[L-E]` vía `record_event` (single commit con alerta)
10. Derivar `tipo_entrada` (DEC-SUC-21)
11. 201 con `IngresoReadForzado`

Alerta `capacidad_agotada_forzado` se inserta en **misma transacción** que el INSERT del ingreso (un solo `commit()`).

## 10. Repositorio nuevo

**`repo/ingreso.py`** (NUEVO, ~180 LOC):
- `detectar_tipo_vehiculo(placa) -> UUID | None` (re-exporta de `repo/placa.py`)
- `validar_tipo_vehiculo_vigente(session, *, uuid_tipo_vehiculo) -> bool`
- `validar_cupo_disponible(session, *, uuid_sucursal, uuid_tipo_vehiculo, forzado=False) -> CupoValidationResult`
- `validar_tarifa_vigente(session, *, uuid_sucursal, uuid_tipo_vehiculo, at, forzado=False) -> TarifaValidationResult`
- `validar_subscripcion_vigente(session, *, uuid_subscripcion_cliente, forzado=False) -> SubscripcionValidationResult`
- `existe_ingreso_activo(session, *, uuid_sucursal, placa) -> UUID | None`
- `crear_ingreso_evento(...)` thin wrapper de `record_event`
- `insertar_alerta_forzado(session, *, uuid_sucursal, uuid_ingreso, actor_uuid, motivo) -> AlertaRow`

**`repo/placa.py`** (NUEVO, ~30 LOC):
```python
FORMATOS_ACEPTADOS = (re.compile(r"^[A-Z]{3}[0-9]{3}$"), re.compile(r"^[A-Z]{3}[0-9]{2}[A-Z]$"))
TIPO_POR_PATRON = {...}  # lazy lookup tipos_vehiculo

def detectar_tipo_vehiculo(placa: str) -> UUID | None: ...
```

**`repo/subscripcion_activa.py`** (NUEVO, ~50 LOC):
- Extrae `resolve_active_subscription_for_exit` (post-PR5) + check `fecha_vencimiento >= NOW()`.

**`repo/alerta.py`** (NUEVO, ~60 LOC):
- Helper `insertar_alerta_forzado(...)`.

**Modificaciones**:
- `repo/ocupacion.py` (+40 LOC) — agregar `validar_cupo_disponible(...)` reusando `get_ocupacion_puros_activos`.
- `repo/tarifas_vigencia.py` (+30 LOC) — agregar `validar_tarifa_vigente(...)` reusando `bitemporal_vigente_predicate`.

## 11. Schemas nuevos

`schemas/operacion.py` (MODIFICAR, +80 LOC):

```python
class IngresoCreateForzado(_Base):
    uuid_sucursal: uuid_lib.UUID | None = None
    placa: str | None = None
    uuid_tipo_vehiculo: uuid_lib.UUID | None = None  # server overrides via regex
    uuid_subscripcion_cliente: uuid_lib.UUID | None = None
    fecha_ingreso: datetime | None = None
    observaciones: str | None = None
    forzado: bool = False  # NEW


class IngresoReadForzado(_Base):
    # inherited: uuid, created_at, uuid_sucursal, placa, ...
    tipo_entrada: Literal["MENSUALIDAD", "ROTACION"]  # NEW
    forzado_en_creacion: bool = False  # NEW
    motivo_forzado: str | None = None  # NEW


class CupoNoConfiguradoError(_Base): error: Literal["cupo_no_configurado"]; forzado_permitido: Literal[True]
class MotivoForzadoRequeridoError(_Base): error: Literal["motivo_forzado_requerido"]; cupo_maximo: int; activos: int
class TarifaVigenteNoEncontradaError(_Base): error: Literal["tarifa_vigente_no_encontrada"]
class PlacaFormatoInvalidoError(_Base): error: Literal["placa_formato_invalido"]; formatos_aceptados: list[str]
class SubscripcionInactivaOVencidaError(_Base): error: Literal["subscripcion_inactiva_o_vencida"]
class IngresoActivoExistenteError(_Base): error: Literal["ingreso_activo_existente"]; uuid_ingreso_existente: uuid_lib.UUID
class TipoVehiculoInvalidoError(_Base): error: Literal["tipo_vehiculo_invalido"]
```

`extra='forbid'` (heredado de `_Base`).

## 12. KD preliminares

- **KD-V1**: `422 cupo_no_configurado` con `forzado_permitido: true`. Cliente renderiza "Cupo no configurado para Auto en sucursal X. ¿Desea forzar la entrada?".
- **KD-V2**: regex hardcoded para MVP (`repo/placa.py` constante). Configurable en HU futura.
- **KD-V3**: forzado bypass para V6 también — subscripción vencida es operacional, no bug.
- **KD-V4**: eventual consistency con la vista (lag 10s). NO lock pesimista.
- **KD-V5**: anulación out of scope (DEC-ANUL-01).
- **KD-V6**: NO `correlacion_id`; idempotencia via `Idempotency-Key` header.
- **KD-V7**: `forzado` parseado de `observaciones`, NO columna.
- **KD-V8**: tanto `operador-` como `admin-` pueden `forzado=true`. Si se requiere "solo admin-", check dedicado en HU futura.
- **KD-V9**: `observaciones` puede ser None cuando forzado=false.

## 13. Test patterns

- **`tests/unit/test_operacion_ingresos_validaciones.py`** (~400 LOC, 8 parametrized HTTP tests): T1 placa válida Auto, T2 placa inválida, T3 mensualidad, T4 rotación, T5 cupo agotado sin forzado, T6 cupo agotado con forzado + alerta, T7 ingreso activo existente 409, T8 orden de validación regex-antes-mensualidad.
- **`tests/unit/test_operacion_ingresos_kd_forzado.py`** (~150 LOC, 4 tests): T1 prefijo válido, T2 sin prefijo, T3 motivo 9 chars, T4 forzado=false con prefijo (contradicción).
- **`tests/unit/test_repo_placa.py`** (~80 LOC, 6 tests regex): T1 ABC123→Auto, T2 ABC12D→Moto, T3 AB12→None, T4 lowercase→None, T5 4 dígitos→None, T6 con guión→None.
- **`tests/integration/test_ingreso_create_db.py`** (~250 LOC, 3 DB tests `PARKOS_DOCKER_TEST=1`): T1 insert + alerta, T2 duplicado activo rechazado, T3 subscripción vencida.
- **`tests/static/test_no_write_after_insert.py`** (~100 LOC, 1 AST walk): `repo/ingreso.py::crear_ingreso_evento` rechaza `UPDATE|DELETE|TRUNCATE`.
- **`tests/static/test_kd_forzado_in_handler.py`** (~80 LOC, 1 AST walk): `create_ingreso` llama `validar_kd_forzado(...)` ANTES de otras validaciones (R7 invariante).

Total: 14 tests.

## 14. Open questions para resolve en propose/design

1. KD-V1 — código 422 (validación semántica, consistente con F1.5/F1.8 `tarifa_no_vigente`).
2. KD-V2 — hardcoded para MVP.
3. KD-V4 — eventual consistency (lag 10s), NO lock pesimista.
4. KD-V5 — out of scope.
5. KD-V6 — NO `correlacion_id`.
6. KD-V8 — `operador-` y `admin-` ambos pueden forzar.
7. Orden exacto: regex → tipo → KD-FORZADO → cupo → tarifa → subscripción → no-duplicado → INSERT.
8. `uuid_tipo_vehiculo` en payload: server sobreescribe si no concuerda con regex derivado (BR2 CU-01).
9. Default `uuid_sucursal`: si None → `ctx.sucursal_uuid`.
10. Alerta `capacidad_agotada_forzado` — una por ingreso forzado (uuid_ingreso la hace única).

## 15. Artifacts

```
openspec/changes/hu-f1-6-validaciones-post-ingresos/exploration.md     ← este archivo
openspec/changes/hu-f1-6-validaciones-post-ingresos/proposal.md
openspec/changes/hu-f1-6-validaciones-post-ingresos/specs/operational/spec.md
openspec/changes/hu-f1-6-validaciones-post-ingresos/design.md
openspec/changes/hu-f1-6-validaciones-post-ingresos/tasks.md
openspec/changes/hu-f1-6-validaciones-post-ingresos/verify-report.md
openspec/changes/archive/2026-09-14-hu-f1-6-validaciones-post-ingresos/archive-report.md
```

Backend:
- NEW: `repo/ingreso.py` (~180), `repo/placa.py` (~30), `repo/subscripcion_activa.py` (~50), `repo/alerta.py` (~60)
- MODIFY: `api/v1/operacion.py` (replace `create_ingreso`, +140 LOC), `schemas/operacion.py` (+80), `repo/ocupacion.py` (+40), `repo/tarifas_vigencia.py` (+30)
- NOT TOUCHED: `api/v1/__init__.py`, `models/*`, `migrations/*`, `repo/event.py`, `repo/cotizacion.py`, `auth/tenancy.py`, `api/deps.py`

## 16. Riesgos

- **R1 (Medio)**: MV lag 10s → eventual consistency. Aceptable (RIESGO-SUC-02). NO lock pesimista.
- **R2 (Bajo)**: alerta falsamente disparada si `forzado=true` y cupo está bien. Mitigación: alerta SOLO si V2 fue bypassed (`bypass_reason == 'cupo_agotado'`).
- **R3 (Bajo)**: regex hardcoded rompible. Mitigación: constante a nivel de módulo.
- **R4 (Bajo)**: subscripción cross-tenant → V6 rechaza (intencional, defense in depth).
- **R5 (Bajo)**: alerta e ingreso en misma transacción (un commit). R5 mitigación: FK commit ordering.
- **R6 (Bajo)**: `extra='forbid'` rechaza campos extra.
- **R7 (Medio)**: orden de validación estricto. Mitigación: AST walk `test_kd_forzado_in_handler.py` verifica orden literal.
- **R8 (Bajo)**: V8 directo a tablas (authoritative) < 50ms.
- **R9 (Bajo)**: subscripción vigente + vehículo no incluido en `subscripcion_vehiculos` → walk-in auditado.

---

**Explored by**: sdd-explore (sub-agent).
**Engram**: persisted `sdd/hu-f1-6-validaciones-post-ingresos/explore` (id 1536).
**Next recommended**: `sdd-propose HU-F1.6`.
