# Alcance del pull cloud → sucursal

> Qué recibe cada sucursal de `POST /sync/pull`, cómo se decide y cómo agregar una tabla.
> Fuente de verdad: `sync/motor/pull_scope.py` (reglas) y `backend/tests/pull_scope_expected.py` (clase esperada por tabla). Esta página resume ambos; si difiere del código, gana el código.

## En una frase

La sucursal se identifica por su JWT `sync-agent-` (nunca por un parámetro). El filtro es **SQL** (`build_scope_predicate`), el resolver Python solo re-verifica `single_branch`, el `override` propio y la `subscription` directa (el resto lo garantiza el SQL), y una compuerta estática impide registrar una tabla sin decidir su alcance. El pull solo entrega filas **vigentes** (`vigente_hasta IS NULL`) de las tablas `[V]`.

## Matriz de alcance

Clases (`EXPECTED_SCOPE`) → política del catálogo (`broadcast_policy`):

| Clase | Política | Regla SQL |
|---|---|---|
| `global` | `all_branches` | sin filtro |
| `owned` | `single_branch` | `uuid_sucursal = :s` (en `sucursal`: `uuid = :s`) |
| `override` | `all_branches_with_override` | `uuid_sucursal IS NULL OR uuid_sucursal = :s` |
| `subscription` | `subscription` | directa: `uuid_sucursal = :s`; transitiva: padre en `subscripciones_cliente` con `uuid_sucursal = :s` |
| `derived` | `derived` | regla propia por tabla (ver abajo) |

Tablas por clase:

| Clase | Tablas |
|---|---|
| `global` | `permisos`, `tipo_persona`, `tipos_vehiculo`, `tipo_subscripciones`, `tipo_tarifa`, `tipo_sucursal`, `tipo_arqueo`, `impuestos`, `otros_cobros`, `costos_servicios` |
| `owned` | `sucursal`, `resolucion_facturacion`, `usuarios_sucursal`, `documentos`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal` |
| `override` | `configuracion_tolerancias`, `configuracion_seguridad` |
| `subscription` | `subscripciones_cliente` (directa), `subscripcion_vehiculos` (transitiva por `uuid_subscripcion_cliente`) |
| `derived` | `usuarios`, `permisos_usuario`, `empresa`, `clientes`, `clientes_b2b`, `vehiculos` |

### Reglas `derived`

| Tabla | Entrega la fila si... |
|---|---|
| `usuarios` | su `uuid` está en `usuarios_sucursal` **vigente** de la sucursal |
| `permisos_usuario` | su `uuid_usuario` cumple la regla de `usuarios` |
| `clientes` | tiene suscripción **o** factura electrónica en la sucursal, resuelto por **llave natural** `(tipo_identificador, numero_identificacion normalizado)` de *cualquier* versión referenciada |
| `clientes_b2b` | su `uuid_cliente` es una versión de un cliente en alcance (misma llave natural) |
| `vehiculos` | está ligado por `subscripcion_vehiculos` a una suscripción de la sucursal, por `placa` normalizada de cualquier versión ligada |
| `empresa` | es la empresa de `sucursal.uuid_empresa` (por NIT entre versiones); si es `NULL` o desconocida, las empresas abiertas |

Por qué la llave natural: un cambio de versión `[V]` (`close_and_insert`) crea un `uuid` nuevo, mientras que suscripciones y facturas (tabla `[A]`) siguen apuntando al `uuid` viejo y cerrado. Las suscripciones **no** se filtran por vigencia (una renovación inserta una fila nueva). No hay rama por `sync_identity_alias`: esa tabla no tiene sucursal, es local al nodo y nadie la escribe.

Una llave natural que normaliza a cadena vacía (`'---'` → `''`) **no es una llave**: la regla la excluye de los dos lados de la comparación (`<> ''` explícito, no `nullif(...)`, para que el planificador siga usando `ix_clientes_nk_open`, `ix_clientes_nk` e `ix_vehiculos_nk_open`, que indexan la expresión sin envolver). Una fila sin llave sigue llegando por su `uuid` si la sucursal la referencia, pero ya no arrastra a todas las demás filas con llave vacía (esto aplica también al NIT de `empresa`).

### Entrega por entrada al alcance (`derived`)

El pull incremental (`since_seq` = cursor − 1) selecciona por el `created_at` **propio** de la fila. En una tabla `derived` eso no dice *cuándo entró la fila al alcance*: un usuario creado hace meses y asignado hoy a la sucursal tiene `created_at` viejo pero una fila puente `usuarios_sucursal` nueva. Sin tratamiento llegaba la fila puente y nunca el usuario (el login offline fallaba); lo mismo con clientes y vehículos que ganan una suscripción o factura después, `clientes_b2b`, `permisos_usuario` y `empresa`.

Cómo funciona (`build_scope_entry_predicate` + `_fetch_pull_rows`):

1. La página se arma igual que antes (por `created_at` propio, corte global por `LIMIT`) y `next_seq` es el `seq` máximo entregado en ella. Nada de lo siguiente mueve el cursor.
2. Para cada tabla `derived` (solo si `since_seq > 0`; con `0` toda fila ya califica) se evalúa **la misma regla de alcance** restringida a filas puente con `created_at` en la ventana que el cursor acaba de cruzar: `[since_seq + 1, max_seq_visto]`, sin tope superior si la página no se cortó por `LIMIT`.
3. Esas filas ("entraron al alcance") se entregan **antes** que la página: padres antes que los hijos que los referencian (usuarios antes que `usuarios_sucursal`, clientes antes que sus suscripciones). Las que ya vienen en la página no se repiten.
4. Fila puente por tabla: `usuarios` y `permisos_usuario` → `usuarios_sucursal` vigente nueva (de un usuario recién asignado llegan **todos** sus permisos abiertos); `clientes` y `clientes_b2b` → suscripción o factura nueva en la sucursal (por llave natural); `vehiculos` → suscripción **o** vínculo `subscripcion_vehiculos` nuevo; `empresa` → fila propia de `sucursal` creada en la ventana.
5. Una fila puede reenviarse (tiene varias filas puente en la ventana, o su puente es una factura, que no es una tabla del pull y por tanto no hace avanzar el cursor, así que se repite hasta que lleguen filas nuevas de otras tablas). Es **idempotente**: `apply_guard.row_already_present` la convierte en no-op en la sucursal.

Como el `LIMIT` corta solo la página, una fila puente cortada trae a sus padres en la página que la entrega, no antes: sin pérdida y sin estancar el cursor (el estancamiento sería inevitable si las filas de `created_at` viejo contaran para el `LIMIT` y no movieran `next_seq`).

### Lo que nunca se entrega

- Filas cerradas de tablas `[V]` (el pull no propaga cierres de vigencia).
- `log_transaccional`: `bidirectional` con `broadcast_policy=None`; no tiene alcance de pull y `_fetch_pull_rows` lo omite (`PULL_DIRECTION_WITHOUT_POLICY`).
- Cualquier entrada cuya dirección no sea `cloud_to_branch` ni `bidirectional`.
- Usuarios, clientes y vehículos de una sucursal sin vínculo con la solicitante. Un cliente nuevo para una sede se crea local y el cloud lo reconcilia al subir.

## Runbook: agregar una tabla al pull

1. **Decidir la clase.** Si lleva datos personales, nunca `global`: `ALL_BRANCHES_ALLOWLIST` solo admite catálogos de referencia.
2. **Declarar la política** en la entrada del catálogo (`sync/catalog/entries/`), con la `direction` correcta.
3. **Registrar la regla** si no es `global`:
   - `owned` / `override` / `subscription` directa: basta la política y `has_uuid_sucursal=True`.
   - `subscription` transitiva: agregar el padre a `_TRANSITIVE_SUBSCRIPTION_PARENT` (`broadcast_resolver.py`).
   - `derived`: agregar `_DERIVED_RULES["<tabla>"]` en `pull_scope.py`, reutilizando los subselects existentes. La regla recibe `since_floor`/`until_ceiling` opcionales y los aplica al `created_at` de las **filas puente**: sin ventana es el alcance, con ventana es la entrada al alcance (ver arriba); y debe cubrirse con un caso en `test_sync_pull_scope_entry.py`.
4. **Actualizar `EXPECTED_SCOPE`** en `backend/tests/pull_scope_expected.py` (y `ALL_BRANCHES_ALLOWLIST` solo si es un catálogo sin datos personales).
5. **Probar la no-fuga**: la matriz parametrizada (`test_sync_pull_scope_matrix.py`) o, para `derived`, un caso en `test_sync_pull_scope_derived.py`.
6. **Índices** para la subconsulta nueva, en una migración aparte.
7. **Ejecutar la compuerta**: `tests/static/test_pull_scope_guardrails.py` debe pasar; falla si la tabla no tiene regla, no figura en `EXPECTED_SCOPE` o la clase no coincide con la política.

```powershell
cd backend
$env:TEST_PG_IMAGE='parkos-postgres:16-pgpartman'
uv run pytest tests/static/test_pull_scope_guardrails.py tests/unit/test_pull_scope.py tests/integration/test_sync_pull_scope_matrix.py -p no:cacheprovider --no-cov
```

## Limitaciones conocidas

| # | Limitación | Detalle y salida |
|---|---|---|
| 1 | **Reconciliación con datos idénticos y FK** | Si la sucursal B crea localmente un cliente idéntico (misma llave natural) a uno que ya existe en el cloud, la reconciliación es un *noop* sin fila en `sync_identity_alias`. El `uuid` local de B queda desconocido para el cloud, y el push posterior de `subscripciones_cliente` de B falla con `apply_error` (violación de FK) de forma permanente. Fijado con el test `test_identical_push_dependents_of_b_reach_the_cloud` (`xfail(strict=True)`, en `test_sync_pull_scope_reconciliation.py`); pasa a error duro cuando se corrija. |
| 2 | **Cierre de membresía en cloud** | El pull entrega solo filas vigentes, así que un cierre de `usuarios_sucursal` hecho en el cloud no llega a la sucursal: la fila local de `usuarios` (y su membresía local) siguen vigentes. Se deduce del filtro vigente de `_fetch_pull_rows`; no existe un mecanismo de propagación de cierres. Mientras tanto, la fila de `usuarios` fuera de alcance queda inofensiva pero con datos personales (ver 7). |
| 3 | **El login de sucursal no exige membresía vigente** | `api/v1/auth.py` busca al usuario por email vigente (líneas 221-227), elige la primera asignación vigente solo para resolver parámetros de bloqueo, y si no hay ninguna deja `branch_uuid = None` sin rechazar (244-253); el token se emite igualmente con `sucursal: None` (363-372). Además `auth/tenancy.py` (≈110-118) para `operador-` solo exige que exista el claim `sucursal`, sin validar membresía. Las líneas se verificaron el 2026-10-05; pueden moverse. Conviene decidir si el login debe rechazar a quien no tenga `usuarios_sucursal` vigente. |
| 4 | **Fallback de `empresa` con `uuid_empresa` NULL** | Si `sucursal.uuid_empresa` es `NULL` se entregan todas las empresas abiertas. En un despliegue con varias empresas, cada sucursal **debe** tener `uuid_empresa`; de lo contrario recibe las de las demás. |
| 5 | **Escaneo completo de `clientes` y `vehiculos`** | La consulta de página (con `created_at >= floor`) mide ≈1,6 ms con 20 000 filas. La consulta de entrada al alcance (se ejecuta en cada pull con `since_seq > 0`, aunque no haya filas puente nuevas) recorre la tabla: `EXPLAIN ANALYZE` medido ≈31 ms en `clientes` y ≈11 ms en `vehiculos` con 20 000 filas y 200 suscripciones, lineal con el tamaño. Salida: una comprobación previa barata de "¿hay filas puente nuevas en la ventana?" que omita la consulta, o reescribir el `OR` como `UNION`. Sin urgencia; revisar al crecer el volumen. |
| 6 | **Migraciones `0083` y `0084` bloquean escrituras** | Usan `CREATE INDEX` simple (Alembic corre en transacción, no admite `CONCURRENTLY`): mientras se construye, la tabla no admite escrituras, y `factura_electronica`, `usuarios_sucursal` y `clientes` no son tablas pequeñas. Ambas empiezan con `SET LOCAL lock_timeout = '5s'` (patrón de `0008`): si una transacción larga ya tiene el bloqueo, la migración falla rápido y se reintenta en vez de encolar a los escritores. Aplicar en ventana de baja carga; para tablas muy grandes, crear el índice con `CONCURRENTLY` fuera de Alembic. |
| 9 | **`UPDATE` in situ de `sucursal.uuid_empresa`** | La entrega por entrada al alcance de `empresa` se dispara cuando la fila de `sucursal` se crea dentro de la ventana del cursor. Un `UPDATE` directo de `uuid_empresa` no cambia `created_at` y el cursor no lo ve; la empresa llega solo cuando cambia la propia (`created_at` nuevo) o en un pull con `since_seq = 0`. |
| 7 | **Datos ya sobre-entregados** | Las bases de sucursal pueden conservar filas de otras sucursales recibidas antes del cambio. El diagnóstico es `backend/scripts/report_pull_scope_overdelivery.py` (solo lectura, solo conteos). La limpieza (dejarlas o un cierre lógico **no propagable**) la decide el responsable: un cierre lógico local normal sobre `clientes`/`vehiculos` (bidireccionales) se encola en `sync_queue` y viaja al cloud, donde cerraría la fila canónica para las demás sucursales. |
| 8 | **`sync/cutover/backfill.py` sin filtro por sucursal** | No tiene llamador en producción. Si se conecta a una ruta real debe aplicar `build_scope_predicate`. |

La barrera adicional en base de datos está propuesta en [ADR-005](./decisiones-tecnicas.md#adr-005-red-de-seguridad-en-base-de-datos-para-syncpull), pendiente de decisión.

## Propuesta: comentarios del ER por reformular

`modelo_datos_er.mmd` es canónico y `check_schema_match.py` lo compara: **no se edita sin aprobación del responsable**. Propuesta de redacción (solo comentarios `%%`, sin cambio de esquema):

| Entidad | Texto actual (línea) | Propuesta |
|---|---|---|
| `usuarios` | "Maestro global de operadores; se administra en cloud y se replica a sucursales para login offline" (8) | "...se administra en cloud; cada sucursal recibe solo los usuarios con membresía vigente en ella (login offline)" |
| `permisos_usuario` | "Junction usuario-permiso; otorgar inserta fila, revocar cierra vigencia" (50) | Agregar: "se replica solo para los usuarios con membresía vigente en la sucursal" |
| `clientes` | "Maestro de clientes identificados..." (472) | Agregar: "cada sucursal recibe solo los clientes con suscripción o factura en ella; los demás se reconcilian por llave natural al subir" |
| `clientes_b2b` | "Extensión 1:1 de clientes..." (497) | Agregar: "sigue el alcance de su cliente" |
| `vehiculos` | "Vehículos registrados, solo requeridos para suscripciones..." (542) | Agregar: "cada sucursal recibe solo los vinculados a suscripciones propias" |

Nota: hoy solo el comentario de `usuarios` afirma literalmente que se "replica a sucursales"; los otros omiten el alcance, y el comentario de `sucursal` ("solo sus filas + catálogos") es el que quedaba incumplido para estas tablas. La redacción propuesta lo hace explícito. El comentario de `permisos` ("replica cloud a sucursales") es correcto: es un catálogo `global`.
