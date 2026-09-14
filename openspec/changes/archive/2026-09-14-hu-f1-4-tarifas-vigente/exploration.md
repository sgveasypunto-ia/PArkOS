# Exploration: hu-f1-4-tarifas-vigente

> **Change**: `hu-f1-4-tarifas-vigente`
> **Phase**: explore (sdd-explore)
> **HU**: HU-F1.4 — Filtro temporal `vigente_en` sobre `GET /empresa/tarifas-sucursal`
> **Date**: 2026-09-14
> **Inputs read**:
    `openspec/specs/operations/spec.md` (REQ-OPS-001..016),
    `openspec/changes/archive/2026-09-09-sync-overhaul/` (proposal/design/tasks canónicos,
    patrón `SyncMotor`, formato de change),
    `modelo_datos_er.mmd` (tabla `tarifas_sucursal`, líneas 406–426),
    `backend/packages/parkos_core/src/parkos_core/api/router_factory.py` (HU-F1.1 GAP-BE-02,
    `hasattr(model_cls, "vigente_hasta")` estabilizado en commit `f7cb37a`),
    `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py` (configuración del router
    `tarifas-sucursal` y schemas Pydantic),
    `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py` (`TarifasSucursalFilter`,
    líneas 303–309),
    `backend/packages/parkos_core/src/parkos_core/api/v1/operacion.py:215-277`
    (precedente de punto-en-tiempo `resolve_active_subscription_for_exit(as_of=...)`),
    `plan.md` (línea 471, patrón bi-temporal canónico).

## Contexto y scope

HU-F1.4 extiende `GET /empresa/tarifas-sucursal` para aceptar un query param opcional
`vigente_en: datetime | None`. Cuando se omite, el endpoint se comporta exactamente como hoy
(solo versiones con `vigente_hasta IS NULL`); cuando se envía, aplica el predicado bi-temporal
canónico `vigente_desde <= :vigente_en AND (vigente_hasta IS NULL OR vigente_hasta > :vigente_en)`
filtrando adicionalmente `estado = 'activo'`. El objetivo es permitir que la UI administrativa
consulte tarifas pasadas o futuras sin tener que conocer los rangos exactos de cada versión.

El cambio está acotado al read path de un único recurso `[V]` versionado. No introduce nuevas
tablas, no agrega columnas, no crea migraciones Alembic, no toca el factory `make_router`
(estabilizado por HU-F1.1 GAP-BE-02 — `f7cb37a`), no modifica `make_router` ni crea endpoints
nuevos. La coexistencia con `make_router` se resuelve registrando un handler dedicado para
`GET /empresa/tarifas-sucursal` por delante del mount genérico — el factory sigue siendo la
opción por defecto para el resto de recursos.

## Tablas / columnas afectadas (con línea exacta del ER)

Única tabla tocada: `tarifas_sucursal` (modelo_datos_er.mmd líneas 406–426).

| Columna | Tipo (ER) | Línea | Rol en HU-F1.4 |
|---|---|---|---|
| `vigente_desde` | `timestamp` | 419 | Lado izquierdo del predicado (`<= :vigente_en`) |
| `vigente_hasta` | `timestamp NULL` | 420 | Lado derecho del predicado (`IS NULL OR > :vigente_en`) |
| `estado` | `string activo\|inactivo` | 421 | Filtro complementario (`= 'activo'`) |
| `uuid` | `uuid PK` | 409 | Identidad, sin cambios |
| `uuid_sucursal` | `uuid FK UK01` | 410 | Ya filtrable por `TarifasSucursalFilter.uuid_sucursal`, sin cambios |
| `uuid_tipo_vehiculo` | `uuid FK UK01` | 411 | Ya filtrable, sin cambios |
| `uuid_tipo_tarifa` | `uuid FK UK01` | 412 | Ya filtrable, sin cambios |
| `valor` | `decimal` | 413 | Salida, sin cambios |
| `valor_plena` | `decimal` | 414 | Salida, sin cambios |
| `created_at`, `created_by` | audit | 416–417 | Salida, sin cambios |
| `sync_*` | sync | 423–425 | Salida, sin cambios |

UK01 (`uuid_sucursal, uuid_tipo_vehiculo, uuid_tipo_tarifa, vigente_desde`) no se toca.
**Ninguna columna se modifica** — HU-F1.4 opera exclusivamente sobre columnas existentes.

## Endpoints afectados

| Path | Method | Cambio | Issuer / rol | Línea |
|---|---|---|---|---|
| `GET /empresa/tarifas-sucursal` | GET | query param opcional `vigente_en: datetime \| None = None`; handler dedicado que aplica `vigente_desde <= :vigente_en AND (vigente_hasta IS NULL OR vigente_hasta > :vigente_en) AND estado = 'activo'` | `admin-,operador-` con `config_tarifas` | `empresa.py:142-149` |

No se agregan nuevos paths. No se modifican `POST/PUT/GET /{uuid}/history`.

## Archivos a tocar

| Archivo | Acción | Por qué |
|---|---|---|
| `backend/packages/parkos_core/src/parkos_core/api/v1/empresa.py` | modificar | Registrar handler dedicado para `GET /empresa/tarifas-sucursal` por delante del mount genérico; lee `vigente_en`, llama al nuevo repo helper, devuelve `TarifasSucursalReadList` con la misma forma que hoy |
| `backend/packages/parkos_core/src/parkos_core/schemas/empresa.py` | modificar | Agregar `vigente_en: datetime \| None = None` a `TarifasSucursalFilter` (líneas 303–309) — el `Query` se declara en el handler, el schema solo lleva el campo |
| `backend/packages/parkos_core/src/parkos_core/repo/tarifas_vigencia.py` (nuevo) | crear | Helper puro `list_tarifas_vigentes(session, *, vigente_en, filter, cursor, limit) -> tuple[list[model], str \| None]`; encapsula la conversión tz→UTC, el predicado bi-temporal, el orden por `vigente_desde DESC, uuid ASC` y la decodificación del cursor — sigue el precedente de `_parse_cursor_timestamp` |
| `backend/tests/unit/test_tarifas_vigente_en.py` (nuevo) | crear | RED-then-GREEN: default = ahora; valor pasado; valor futuro; valor con tz offset; valor inválido; cursor compat con `vigente_en` ausente; integración con `estado='inactivo'` que debe excluirse |
| `backend/tests/integration/test_tarifas_vigente_en_db.py` (nuevo) | crear | DB-backed contra `pg_engine` real: misma tarifa en tres versiones (pasada, vigente, futura) con `estado` mixto; tres asserts sobre el conjunto resultante |
| `openspec/specs/operations/spec.md` | modificar | Agregar REQ-OPS-017..020 (4 requirements nuevos); `Modified Capabilities` |
| `openspec/changes/hu-f1-4-tarifas-vigente/{proposal,tasks,design,exploration}.md` + `specs/operational/spec.md` | crear | Este change (5 archivos) |

## Dependencias previas (commits de la rama)

| Commit | HU | Estado |
|---|---|---|
| `3269d3e` | bcrypt real en login (pre-Fase-1) | merged — sin impacto sobre HU-F1.4 |
| `f7cb37a` | HU-F1.1 GAP-BE-02 (router_factory con `hasattr` de `vigente_desde`) | merged — **NO se modifica**, es la base estable |
| `535676d` | HU-F1.2 (cookie httpOnly + lockout real + GET /auth/me) | merged — sin impacto directo sobre HU-F1.4 |

HU-F1.1 estabilizó el comportamiento default de `make_router` ("solo vigentes") usando
`hasattr(model_cls, "vigente_hasta")`. HU-F1.4 NO modifica `make_router`; agrega un handler
dedicado que se registra antes del mount genérico para `tarifas-sucursal`.

## Supuestos detectados (con conflictos resueltos)

1. **Conflicto plan.md vs `prompts/00-ejecutor-fase-1.md`** — RESUELTO a favor de plan.md.
   El prompt original divergía sobre si el alcance era (a) nuevo path
   `GET /tarifas-sucursal/vigentes` o (b) modificación del existente
   `GET /empresa/tarifas-sucursal`. La decisión contractual es **(b)**: se modifica el path
   existente con un query param opcional `vigente_en`. **No** se crea path nuevo. Documentado
   en `## Open Questions` de `proposal.md` (marcado RESUELTO) y replicado aquí.
2. **Default `vigente_en` cuando se omite** — RESUELTO a favor de `datetime.now(UTC)` (no se
   cambia el comportamiento actual del factory, que filtra `vigente_hasta IS NULL`). Esto
   preserva retrocompatibilidad al pie de la letra para clientes existentes.
3. **Conversión tz** — RESUELTO a favor de normalizar a UTC antes del bind (patrón
   `_parse_cursor_timestamp` de `router_factory.py:84-113`). El DB column es
   `DateTime(timezone=False)`; bindear con tz produce el bug documentado en el comentario
   de `_parse_cursor_timestamp`. Si `vigente_en` llega naive, se interpreta como UTC.
4. **Coexistencia con el factory** — RESUELTO a favor de **handler dedicado antes del
   mount genérico**. El factory sigue activo para todos los demás recursos `[V]`. Documentado
   como KD-1 en `design.md`.
5. **Inclusión de `estado='activo'`** — RESUELTO a favor de incluir el predicado. El ER
   declara `estado ∈ {activo, inactivo}`; aunque el factory hoy no filtra por `estado`, el
   modelo bi-temporal canónico del plan.md (línea 471) sí lo incluye. Es defensa en
   profundidad: nunca debe salir una tarifa inactiva sin que el caller lo pida
   explícitamente.

## Riesgos vivos identificados

- **R1**: Cambio de comportamiento silencioso si un caller existente dependiera del filtro
  default "solo vigentes" para `vigente_hasta IS NULL` pero ignora `estado='inactivo'`.
  Mitigación: el default `now(UTC)` colapsa al comportamiento actual para todas las filas
  activas vigentes; las filas inactivas ya no se devuelven aunque el caller no lo pida — esto
  es consistente con el patrón de `resolve_active_subscription_for_exit` y se testea.
- **R2**: Convivencia con cursor pagination — el orden del factory es
  `(vigente_desde DESC, uuid ASC)` para tablas con `vigente_desde`, pero el handler dedicado
  debe respetar exactamente ese orden para no romper cursors emitidos antes del despliegue.
  Mitigación: reutilizar el mismo `_parse_cursor_timestamp` + `_order_key` del factory.
- **R3**: El handler dedicado se registra por path (`/tarifas-sucursal`), no por método. Si
  en el futuro se agregan nuevos verbos al recurso, deben respetar el handler dedicado o
  reusar el factory. Mitigación: documentado en KD-4.

## Resumen ejecutivo

HU-F1.4 extiende `GET /empresa/tarifas-sucursal` con un query param opcional `vigente_en`
(default `now(UTC)`) que aplica el predicado bi-temporal canónico
`vigente_desde <= :vigente_en AND (vigente_hasta IS NULL OR vigente_hasta > :vigente_en) AND estado = 'activo'`.
No se toca ninguna tabla ni columna, no se modifica `make_router` (HU-F1.1 lo estabilizó), no
se crea migración Alembic, no se crea nuevo endpoint. El handler dedicado se registra antes
del mount genérico en `empresa.py` y delega en un nuevo helper puro
`repo/tarifas_vigencia.py` que normaliza tz→UTC, respeta el orden de cursor existente, y
preserva retrocompatibilidad al pie de la letra. Cobertura estimada ~250–350 LOC incluyendo
tests DB-backed. Cuatro requirements nuevos (REQ-OPS-017..020) en `operations/spec.md`.