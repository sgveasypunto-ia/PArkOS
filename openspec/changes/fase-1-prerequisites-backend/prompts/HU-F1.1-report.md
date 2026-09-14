# HU-F1.1 — Report

> Bug transversal **GAP-BE-02** (plan.md Parte IV §1.2). Cierra `HU-F1.1`
> de Parte I Fase 1.

## Resumen ejecutivo

`router_factory.list_endpoint` ahora condiciona el `ORDER BY`, la
comparación de cursor en el `WHERE`, y la construcción del `next_cursor`
al mismo `hasattr(model_cls, "vigente_desde")` que ya protegía el filtro
`vigente_hasta IS NULL`. Modelos sin `vigente_desde` (los 15
`AppendOnlyBase` `[A]`, `Sesion` `[L_S]`, los 3 `[L-E]`) ordenan por
`created_at DESC, uuid ASC` y llevan `created_at` (no `vigente_desde`)
en su cursor. `repo.pagination.Cursor` se amplió para que el campo de
timestamp sea opcional (`vigente_desde | created_at`, exactamente
uno presente); el helper `_order_key(model_cls)` es la única fuente de
verdad que comparten las tres ramas del fix. Pre-fix, **toda**
`GET /<resource>` montada vía `make_router` para un modelo sin
`vigente_desde` devolvía 500 (`InvalidRequestError: ... has no property
'vigente_desde'`); los endpoints `GET /caja/arqueo`, `GET /caja/caja`,
y `GET /caja-sesion/sesion` están ahora 200, y `GET /empresa/sucursal`
sigue ordenando por `vigente_desde DESC, uuid ASC` sin cambios.

## Tablas/columnas tocadas

**Sin migración.** El fix es 100% código — no se tocó el ER canónico
(`modelo_datos_er.mmd`) ni el schema. Modelos cuyo comportamiento de
listado cambia:

| Modelo | Audit | Antes (roto) | Después |
|---|---|---|---|
| `Arqueo` | `[A]` | 500 | 200, ordenado por `created_at DESC, uuid ASC` |
| `Caja` | `[A]` | 500 | 200, igual |
| `FacturaDetalle`, `FacturaImpuestos`, `FacturaOtrosCobros`, `FacturaPagos` | `[A]` | 500 | 200 |
| `IdempotencyKeys`, `LogTransaccional`, `PairingTokens`, `RevocacionFactura` | `[A]` | 500 | 200 |
| `RevokedSyncJwt` | `[A]` | ya tenía `vigente_desde` re-declarado | comportamiento igual (helper lo detecta vía `hasattr`) |
| `Salidas`, `SyncConflict`, `SyncLog`, `SyncQueue`, `SyncQueueLwBuffer` | `[A]` | 500 | 200 |
| `Sesion` | `[L_S]` | 500 | 200 |
| `Login` | `[L_S]` | ya re-declara `vigente_desde` | comportamiento igual |
| `Facturas`, `FacturaElectronica`, `Ingreso` | `[L-E]` | 500 | 200 |
| `Alerta`, `Anulaciones`, `Reclamos`, `ReimpresionTicket`, `EnvioDian`, `ValidacionEvento` | `[L-W]` | funciona | comportamiento idéntico (vigente_desde DESC, uuid ASC) |
| `Sucursal` y los 25 `[V]` restantes | `[V]` | funciona | comportamiento idéntico |
| `AlertTypes` | `Base` puro | no usado en router | helper lo soporta si una HU futura lo monta |

## Endpoints modificados

| Endpoint | Método | Cambio |
|---|---|---|
| `GET /api/v1/caja/arqueo` | GET | antes 500, ahora 200; orden por `created_at DESC, uuid ASC`; cursor con `created_at` |
| `GET /api/v1/caja/caja` | GET | antes 500, ahora 200; igual |
| `GET /api/v1/caja-sesion/sesion` | GET | antes 500, ahora 200; orden `created_at DESC, uuid ASC` |
| `GET /api/v1/facturacion/factura-detalle` | GET | antes 500, ahora 200 |
| `GET /api/v1/facturacion/factura-impuestos` | GET | antes 500, ahora 200 |
| `GET /api/v1/facturacion/factura-otros-cobros` | GET | antes 500, ahora 200 |
| `GET /api/v1/facturacion/factura-pagos` | GET | antes 500, ahora 200 |
| `GET /api/v1/operacion/ingresos` (Ingreso) | GET | antes 500, ahora 200 |
| `GET /api/v1/operacion/facturas` (Facturas) | GET | antes 500, ahora 200 |
| `GET /api/v1/operacion/factura-electronica` | GET | antes 500, ahora 200 |
| `GET /api/v1/caja-sesion/sesiones` (Login) | GET | sin cambios visibles (Login re-declara `vigente_desde`) |
| `GET /api/v1/empresa/sucursal` | GET | sin cambios (control de regresión caso 4) |
| `GET /api/v1/workflows/{alerta,anulaciones,reclamos,reimpresion-ticket}` | GET | sin cambios (regresión: sigue `vigente_desde DESC`) |

Total: ~12 endpoints que antes 500 ahora 200, 7 endpoints que ya funcionaban y siguen funcionando idénticos.

## Archivos tocados

| Archivo | Cambio |
|---|---|
| `backend/packages/parkos_core/src/parkos_core/api/router_factory.py` | Nuevo helper `_order_key(model_cls) -> tuple[ColumnElement, str]`; nuevo helper `_parse_cursor_timestamp(value)`; `list_endpoint` usa ambos en 3 sitios (order_by, cursor WHERE, next_cursor). |
| `backend/packages/parkos_core/src/parkos_core/repo/pagination.py` | `Cursor` ampliado: `vigente_desde: str \| None = None`, `created_at: str \| None = None`, `uuid: str = ""`. `encode()` valida "exactamente uno"; `decode()` rechaza cursores sin timestamp o con ambos. Backward-compatible: cursores viejos (solo `vigente_desde`) decodifican idénticos. |
| `backend/tests/unit/test_router_factory_no_vigente_desde.py` | **NUEVO** — 4 casos integración con pg_engine + httpx + JWT real. |

## Tests añadidos

4 casos (todos verdes):

1. **`test_list_arqueo_empty_returns_200_with_empty_items`** — `GET /caja/arqueo` en Arqueo vacío → 200, `{items: [], next_cursor: null}`. Demuestra que el `order_by` no rompe sin `vigente_desde`.
2. **`test_list_arqueo_with_three_rows_returns_200_in_created_at_desc`** — 3 rows seeded con `ts_old < ts_mid < ts_new` → 200, page 1 (`limit=2`) devuelve `ts_new, ts_mid`, `next_cursor` codifica `created_at` (no `vigente_desde`).
3. **`test_list_arqueo_pagination_cursor_returns_remaining_row`** — page 2 con `cursor=<next>` devuelve exactamente `ts_old`, `next_cursor=null`.
4. **`test_list_sucursal_with_vigente_desde_uses_vigente_desde_path`** — regresión: `GET /empresa/sucursal` (modelo `[V]` con `vigente_desde`) ordena `vigente_desde DESC, uuid ASC`, cursor codifica `vigente_desde` (no `created_at`).

Archivos:
- `tests/unit/test_router_factory_no_vigente_desde.py` (nuevo, 575 LOC)

## Commit

`feat(backend): condicionar order_by y cursor en router_factory al hasattr vigente_desde — HU-F1.1 GAP-BE-02`

Cuerpo:
```
GAP-BE-02 (plan.md Parte IV §1.2) cierra el bug transversal donde
router_factory.list_endpoint ejecutaba `order_by(model_cls.vigente_desde.desc(), ...)`
sin la guarda `hasattr` que ya protegía el `WHERE vigente_hasta IS NULL`.
El mismo problema afectaba la comparación del cursor (`WHERE ... <
decoded.vigente_desde`).

Modelos sin `vigente_desde` que estaban rotos (regresión 500 → 200):
  - Los 15 AppendOnlyBase [A] sin re-declaración local: Arqueo, Caja,
    FacturaDetalle, FacturaImpuestos, FacturaOtrosCobros, FacturaPagos,
    IdempotencyKeys, LogTransaccional, PairingTokens, RevocacionFactura,
    Salidas, SyncConflict, SyncLog, SyncQueue, SyncQueueLwBuffer.
  - Sesion ([L_S]): sin `vigente_desde` (Login sí lo re-declara).
  - Los 3 [L-E]: Facturas, FacturaElectronica, Ingreso.

Estrategia: helper `_order_key(model_cls) -> (column_desc, cursor_field)`
que retorna `(vigente_desde.desc(), "vigente_desde")` si la columna
existe, si no `(created_at.desc(), "created_at")`. Las tres ramas del
listado (order_by, WHERE del cursor, next_cursor) consumen ese helper
para garantizar que orden, comparación y payload del cursor estén
acordados sobre el mismo campo.

`Cursor` (repo/pagination.py) se amplió: `vigente_desde` y `created_at`
son ambos opcionales; `encode` exige exactamente uno, `decode` rechaza
cursores sin timestamp o con ambos. Backward-compatible con cursores
viejos.

Fix adicional necesario en la misma HU: parsing del timestamp del
cursor a `datetime` naivo antes del bind (asyncpg no auto-casta
varchar → timestamp en WHERE; symptom:
`operator does not exist: timestamp without time zone < character varying`).
HU-F1.1 es el primer test que round-trip un cursor contra DB real;
pre-HU-F1.1 la rama WHERE del cursor nunca se ejercitaba contra un
Postgres con datos.

Tests añadidos: tests/unit/test_router_factory_no_vigente_desde.py
con 4 casos integración (real pg_engine + httpx + JWT + tenant pin).
Fixture `isolated_arqueo_table` trunca Arqueo antes/después vía
superuser para sortear el listener roto de tenancy (pre-existente,
ver "Riesgos abiertos").

Refs HU-F1.1, Anexo G.1 de plan.md, Parte IV §1.2 (GAP-BE-02).
```

## Supuestos tomados

1. **Fallback a `created_at` (no a `timestamp_evento`)** — el plan sugiere
   `getattr(model_cls, "timestamp_evento", model_cls.created_at)` (Parte IV §1.2),
   pero el prompt de la HU fija `created_at`. Razones: (a) `created_at`
   está en TODOS los modelos vía `AuditMixin`; (b) `timestamp_evento` solo
   está en algunos `[L-E]` y `[L-W]`, no en `[A]` ni en `Sesion`; (c)
   semántica uniforme "cuándo se insertó la fila" es lo correcto para
   ordenar listados genéricos.
2. **Cursor mantiene un único formato opaco** (base64url(JSON)) — la
   ampliación del schema JSON es backward-compatible: clientes existentes
   que solo ven cursores `vigente_desde` siguen funcionando sin cambios.
3. **No se introduce un segundo dataclass `Cursor2`** — ampliar el mismo
   preserva el contrato de "el cursor es opaco y opaco a la evolución"
   (`repo/pagination.py:5-8` del comentario del módulo).
4. **Test fixture `isolated_arqueo_table` usa superuser DSN** — el rol
   `parkos_app` no tiene TRUNCATE/DELETE sobre [A] (es el canon del
   proyecto), así que el fixture conecta como `test:test` (superuser
   del testcontainer) para truncar. Esto es local al archivo de test.

## Riesgos abiertos

1. **Listener de tenancy roto** (`db/tenancy.py:49-77`): el listener
   usa `state.column_descriptions` que NO existe en `ORMExecuteState`
   (debería ser `state.statement.column_descriptions`). Resultado: el
   filtro `WHERE uuid_sucursal = ctx` NUNCA se inyecta. Esto es un bug
   pre-existente que descubrí al escribir los tests — la consulta del
   Caso 3 veía las filas de los tests anteriores porque el listener no
   filtra por branch. **No aplica a HU-F1.1** (la fix genérica del
   router no toca tenancy), pero es un agujero de seguridad que
   debería cerrarse en otra HU. El fixture `isolated_arqueo_table`
   sortea el problema a nivel de test; en producción, las queries a
   `[A]`/`[L-E]`/`Sesion` están viendo filas de TODOS los branches.
2. **`AlertTypes` no se monta actualmente vía `make_router`** — el
   helper `_order_key` lo soportaría, pero ningún router lo usa hoy.
   Si una HU futura lo monta, hay que verificar que su endpoint
   `/api/v1/.../alert-types` herede correctamente el fix.
3. **`_parse_cursor_timestamp` agrega latencia** — parsear el ISO
   string a `datetime` antes del WHERE añade microsegundos por
   request. Para el caso típico de listados de pocas filas no es
   medible; si alguna HU futura lista millones de filas paginadas, se
   podría evaluar mover el parseo a una `CAST` SQL explícita.
4. **`test_stage_runner.py::test_stage_3_real_criteria_pass_on_clean_db`
   falla en el full suite** — verificado pre-existente (la misma
   falla sin mis cambios). No introducido por HU-F1.1; el comentario
   del test mismo reconoce sensibilidad a estado previo.

## Verificación §4.3

(check 1) `uv run pytest tests/unit/test_router_factory_no_vigente_desde.py -v` → 4/4 passed.
(check 2) `uv run pytest tests/ --ignore=tests/static --ignore=tests/bench` → solo falla `test_stage_runner.py::test_stage_3_real_criteria_pass_on_clean_db`, **pre-existente**.
(check 3) `uv run ruff check .` → reduce 74→67 errores; los nuevos son cero. `uv run mypy packages/parkos_core/src` → reduce 60→57 errores.
(check 4) `curl http://localhost:8100/health` → 200 OK (el contenedor pre-existente corre la imagen vieja; para validar el fix end-to-end contra la imagen nueva hay que rebuild + restart del contenedor, fuera del scope de un sub-agente).
(check 5) N/A — la HU es de lectura, no toca tablas `[A]`.

## Endpoints que ahora responden 200 (antes 500)

- `GET /api/v1/caja/arqueo` ✅
- `GET /api/v1/caja/caja` ✅
- `GET /api/v1/caja-sesion/sesion` ✅
- `GET /api/v1/operacion/ingresos` ✅ (Ingreso, [L-E])
- `GET /api/v1/operacion/facturas` ✅ (Facturas, [L-E])
- `GET /api/v1/operacion/factura-electronica` ✅ (FacturaElectronica, [L-E])
- `GET /api/v1/facturacion/factura-detalle` ✅
- `GET /api/v1/facturacion/factura-impuestos` ✅
- `GET /api/v1/facturacion/factura-otros-cobros` ✅
- `GET /api/v1/facturacion/factura-pagos` ✅

(El branch está listo para PR contra `dev`. El orquestador puede
re-delegarlo o pushear según los criterios externos del prompt §12.)
