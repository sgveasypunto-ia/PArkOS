# HU-F1.1 — Spec

> Bug transversal **GAP-BE-02** (plan.md Parte IV §1.2). Cierra `HU-F1.1`
> de Parte I Fase 1 del plan maestro.

## Resumen del bug

`backend/packages/parkos_core/src/parkos_core/api/router_factory.py:105`
ejecuta `stmt.order_by(model_cls.vigente_desde.desc(), model_cls.uuid.asc())`
sin guarda `hasattr`, mientras que la línea 104 (el `.where()` sobre
`vigente_hasta`) sí está protegida por el mismo `hasattr(model_cls, "vigente_hasta")`
de la línea 103. La línea 107-113 (comparación de cursor) tampoco está
protegida.

Cualquier router armado con `make_router` para un modelo que NO declara
`vigente_desde` levanta `InvalidRequestError`/`AttributeError` al evaluar
`model_cls.vigente_desde` (SQLAlchemy 2.0 lo trata como `InvalidRequestError:
Mapper 'mapped class Arqueo' has no property 'vigente_desde'`).

## Modelos afectados

### Sin `vigente_desde` (hoy explotan — FIX los unifica)

| Heredan de | Modelos concretos |
|---|---|
| `AppendOnlyBase` (todos los `[A]`) | `Arqueo`, `Caja`, `FacturaDetalle`, `FacturaImpuestos`, `FacturaOtrosCobros`, `FacturaPagos`, `IdempotencyKeys`, `LogTransaccional`, `PairingTokens`, `RevocacionFactura`, `Salidas`, `SyncConflict`, `SyncLog`, `SyncQueue`, `SyncQueueLwBuffer` |
| `SessionBase` (`[L-S]`) | `Sesion` |
| `LifecycleEventBase` (`[L-E]`) | `Facturas`, `FacturaElectronica`, `Ingreso` |
| `Base` puro | `AlertTypes` |

### Con `vigente_desde` (funcionan hoy — siguen funcionando idénticos)

| Modelo | Origen de la columna |
|---|---|
| Todos los `[V]` (26) | `VersionedMixin` (en `VersionedBase`) |
| `Alerta`, `Anulaciones`, `EnvioDian`, `Reclamos`, `ReimpresionTicket`, `ValidacionEvento` (`[L-W]`) | re-declarada localmente con `nullable=True` |
| `Login` (`[L-S]`) | re-declarada localmente para semántica de sesión |
| `RevokedSyncJwt` (`[A]`) | re-declarada localmente para UK |

## Contrato del nuevo `Cursor`

Dataclass en `parkos_core/repo/pagination.py`:

```python
@dataclass(frozen=True)
class Cursor:
    vigente_desde: str | None = None  # ISO 8601 (para [V] y [L-W]/[L-S] con vigente_desde)
    created_at:    str | None = None  # ISO 8601 (para [A], [L-E], [L-S]-Sesion)
    uuid:          str                # uuid string (siempre presente)
```

`encode` escribe los tres campos cuando están presentes (omite los `None`).
`decode` valida que **exactamente uno** de `vigente_desde`/`created_at`
esté presente (no ambos, no ninguno). El formato base64url(JSON) se mantiene
— la única diferencia es que JSON ahora puede tener `vigente_desde` o
`created_at`, no obligatorio el primero.

Compatibilidad hacia atrás: cursores emitidos con `vigente_desde` antes
de este cambio siguen siendo decodificables — son indistinguibles de los
nuevos (mismo JSON, mismo base64url).

## Contrato del nuevo `_order_key`

Helper privado en `router_factory.py`:

```python
def _order_key(model_cls: type) -> tuple[ColumnElement, str]:
    """Return (order_col_desc, cursor_field_name) for ``model_cls``.

    - Si el modelo declara ``vigente_desde``: ``(vigente_desde.desc(), "vigente_desde")``.
    - Si no: ``(created_at.desc(), "created_at")``.
    """
```

Se usa en 3 lugares de `list_endpoint`:

1. `order_by(...)` — recibe la columna desc.
2. `.where(...)` del cursor — recibe la columna asc y compara por su nombre
   en `Cursor`.
3. Construcción de `next_cursor` — recibe el nombre del campo del cursor
   para extraerlo de `last` (que tiene `vigente_desde` o no según el modelo).

## Endpoints modificados (sin path nuevo, sin body nuevo)

- `GET /caja/caja` → ahora responde 200 (antes 500)
- `GET /caja/arqueo` → ahora responde 200 (antes 500)
- `GET /caja-sesion/sesion` → ahora responde 200 (antes 500)
- `GET /workflows/alerta` → comportamiento **idéntico** (control de regresión)
- `GET /workflows/anulaciones` → comportamiento idéntico
- `GET /workflows/reclamos` → comportamiento idéntico
- `GET /workflows/reimpresion-ticket` → comportamiento idéntico
- `GET /catalogos/*` (los que montan modelos `[V]`) → comportamiento idéntico

## Archivos a tocar

| Archivo | Cambio |
|---|---|
| `backend/packages/parkos_core/src/parkos_core/api/router_factory.py` | Agregar helper `_order_key`, usar en 3 sitios de `list_endpoint` |
| `backend/packages/parkos_core/src/parkos_core/repo/pagination.py` | Ampliar `Cursor` (vigente_desde + created_at opcionales), actualizar `encode`/`decode` |
| `backend/tests/unit/test_router_factory_no_vigente_desde.py` | **NUEVO** — 4 casos de prueba |

Sin migración Alembic (cambio de código puro, sin tocar ER ni schema).

## Tests añadidos (4 casos)

1. **Empty Arqueo**: `GET /caja/arqueo` con colección vacía → 200
   `{items: [], next_cursor: null}`. (Demuestra que el `order_by` no rompe.)
2. **Arqueo con 3 filas seedeadas**: `GET /caja/arqueo` → 200 con items en
   orden `created_at DESC`, `next_cursor` presente.
3. **Arqueo paginación con cursor**: `GET /caja/arqueo?cursor=<next>`
   devuelve la fila restante, sin repetir las anteriores. Demuestra que
   el cursor `created_at` + `uuid` funciona correctamente.
4. **Sucursal (control de regresión)**: `GET /empresa/sucursal` →
   comportamiento idéntico al actual (`vigente_desde DESC, uuid ASC`).

## Dependencias previas (todas cumplidas)

- Merge `b326c9e` (22 commits de `feature/motor_sync_correcciones_integridad`):
  fix PEP 563 `dd500c2` que mejora el binding del body (commit independiente
  a este bug).
- Commit `3269d3e` pre-Fase-1: bcrypt real en `POST /auth/login`.

## Supuestos tomados

1. **Fallback a `created_at`, no a `timestamp_evento`**: el plan sugiere
   `getattr(model_cls, "timestamp_evento", model_cls.created_at)` (línea 7312
   de plan.md Parte IV §1.2), pero el prompt de la HU fija `created_at`.
   Razones para usar `created_at`: (a) está en TODOS los modelos vía
   `AuditMixin`; (b) `timestamp_evento` solo está en algunos `[L-E]` y `[L-W]`,
   no en `[A]` ni en `Sesion`; (c) `created_at` tiene semántica uniforme
   "cuándo se insertó la fila" que es lo correcto para ordenar listados
   genéricos. Decisión: `created_at` en TODOS los casos sin `vigente_desde`.
2. **Cursor mantiene un único formato opaco (base64url(JSON))** — la
   ampliación del schema JSON es backward-compatible: clientes existentes
   que solo ven cursores `vigente_desde` siguen funcionando sin cambios.
3. **No se introduce un segundo dataclass `Cursor2`** — la opción era crear
   un tipo nuevo, pero ampliar el mismo preserva el contrato de "el cursor
   es opaco y opaco a la evolución" (comentario en `pagination.py:5-8`).

## Riesgos abiertos

- Si una HU futura necesita un cursor con **dos** campos (p.ej. paginar
  por `(timestamp_evento DESC, uuid ASC)` para [L-E]), este mismo Cursor
  admite añadir un tercer campo opcional. No se anticipa pero el patrón
  escala.
- El helper `_order_key` solo cubre DOS opciones (`vigente_desde` o
  `created_at`). Cualquier modelo que tampoco tenga `created_at` (hoy no
  existe ninguno, pero `IdempotencyKeys` hereda `AppendOnlyBase` que hereda
  `AuditMixin` → SÍ tiene `created_at`) reventaría. Lo verifico en el test
  caso 1 (Arqueo sí tiene `created_at`).
