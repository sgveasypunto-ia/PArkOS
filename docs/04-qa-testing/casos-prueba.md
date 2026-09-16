# Casos de prueba reales

> Metodología: se seleccionaron y leyeron 19 archivos de prueba reales del repositorio (`backend/tests/`), priorizando los relacionados con concurrencia/integridad y complementando con casos representativos de catálogo, sincronización, DIAN, reglas arquitectónicas, migraciones y rendimiento. Cada entrada referencia una función de prueba real y describe, en palabras propias a partir de la lectura del archivo, el escenario de negocio que verifica — ninguna cifra ni escenario fue inventado. Ver [`plan-pruebas.md`](./plan-pruebas.md) para la estrategia general y la sección de concurrencia ampliada.

Total de casos documentados en este archivo: **19** (uno por archivo seleccionado; varias entradas mencionan funciones hermanas del mismo archivo como contexto adicional).

## Unitarias — núcleo de catálogo y sincronización

### `backend/tests/unit/test_catalog_counts.py`
- **Función representativa**: `test_sync_catalog_composition_by_audit_class`
- **Categoría**: unit
- **Escenario verificado**: que el catálogo de sincronización mantenga la composición exacta pactada por clase de auditoría (26 `[V]` + 3 `[L-E]` + 6 `[L-W]` + 2 `[L-S]` + 9 `[A]` = 46), y que junto con las 3 tablas locales y las 5 fuera de catálogo sumen las 54 tablas de producción clasificadas — protege contra una tabla mal clasificada, duplicada o "perdida" entre catálogos.

### `backend/tests/unit/test_dependency_graph.py`
- **Función representativa**: `test_depends_on_matches_er` (complementada por `test_cycle_raises_at_import`)
- **Categoría**: unit
- **Escenario verificado**: que las dependencias (`depends_on`) declaradas por cada entrada del catálogo coincidan exactamente, tabla por tabla, con las llaves foráneas obligatorias re-derivadas mecánicamente del modelo entidad-relación (`modelo_datos_er.mmd`) — y que un ciclo de dependencias inyectado se detecte al importar el módulo, no al aplicar datos en producción.

### `backend/tests/unit/test_conflict_resolver.py`
- **Función representativa**: `test_versioned_table_rejects_stale_seq`
- **Categoría**: unit (concurrencia)
- **Escenario verificado**: que el punto de entrada de resolución de conflictos rechace como conflicto (`CONFLICT_V`) una escritura remota sobre una tabla versionada sin llave natural cuando su secuencia no es estrictamente más nueva que la ya persistida localmente — la forma más directa de un conflicto de escritura concurrente sobre la misma fila.

### `backend/tests/unit/test_resolve_conflict.py`
- **Función representativa**: `test_ls_applies_when_timestamp_evento_is_wire_string`
- **Categoría**: unit (concurrencia, regresión real)
- **Escenario verificado**: que la política de resolución para tablas de sesión acepte la marca de tiempo también cuando llega en el formato real de red (cadena ISO-8601), no solo como objeto `datetime` de prueba — reproduce un `TypeError` real ocurrido en producción pese a que el resto de la suite pasaba en verde.

### `backend/tests/unit/test_verify_chain.py`
- **Función representativa**: `test_colliding_timestamp_evento_does_not_false_positive`
- **Categoría**: unit (concurrencia/integridad, regresión real)
- **Escenario verificado**: que eventos concurrentes que comparten la misma marca de tiempo de negocio no bifurquen la cadena de hash — reproduce con UUIDs fijados deliberadamente un incidente real donde el desempate por UUID elegía el predecesor incorrecto, y confirma que ordenar por el momento real de inserción evita el falso positivo de ruptura de cadena.

### `backend/tests/unit/test_hash_chain.py`
- **Función representativa**: `test_hash_chain_append_second_row_links_to_prior`
- **Categoría**: unit (integridad)
- **Escenario verificado**: que cada fila nueva de auditoría encadenada enlace su `hash_anterior` con el `hash_actual` de la fila inmediatamente previa de la misma sucursal, y que la primera fila de una sucursal ancle contra el hash génesis — la invariante base de la que depende toda la detección de manipulación. El mismo archivo documenta, vía `pytest.skip`, que la detección de escrituras fuera de orden aún no existe (gap conocido, no una regresión).

### `backend/tests/unit/test_sync_router.py`
- **Función representativa**: `TestSyncPush.test_push_rejects_revoked_jwt_with_401`
- **Categoría**: unit
- **Escenario verificado**: que el endpoint `POST /sync/push` rechace con 401 una solicitud firmada con un JWT de sincronización ya revocado. El mismo archivo cubre además, sobre el mismo endpoint, el reemplazo idempotente vía `X-Request-Id` y el límite de tasa con encabezado `Retry-After`.

## Unitarias — DIAN

### `backend/tests/unit/test_dian_backoff.py`
- **Función representativa**: `test_curve_is_distinct_from_the_general_sync_queue_curve`
- **Categoría**: unit (dian)
- **Escenario verificado**: que la curva de reintentos específica para el proveedor DIAN (1 min → 5 min → 15 min → 1 h → 6 h → 24 h) esté declarada en un único lugar del código y sea distinta de la curva general de reintentos de `sync_queue` — evita que catálogo y despachador diverjan silenciosamente si alguien redeclara la constante en vez de importarla.

### `backend/tests/unit/dian/test_dispatcher.py`
- **Función representativa**: `test_dispatcher_timeout_retries_then_alerts`
- **Categoría**: unit (dian)
- **Escenario verificado**: que cuando el proveedor DIAN queda indefinidamente "en proceso", el despachador agote su presupuesto de reintentos de sondeo y registre el envío con estado `timeout` más una alerta `dian_timeout`, devolviendo el control al llamador sin propagar una excepción. El mismo archivo cubre además, contra un `httpx.MockTransport` que simula la API real de Factus, los caminos de aceptación, rechazo, error 4xx en el envío inicial, error del proveedor durante el sondeo, autenticación faltante y timeout de conexión.

## Integración — concurrencia y dependencias

### `backend/tests/integration/test_parent_missing_buffer_drain.py`
- **Función representativa**: `test_parent_missing_buffer_drain`
- **Categoría**: integration (concurrencia)
- **Escenario verificado**: que una fila hija (detalle de factura) que llega antes que su fila padre (factura) se guarde en un buffer de espera en vez de fallar, que el emisor se dé por entregado sin penalización de reintentos, y que la fila bufferizada se aplique automáticamente en cuanto el padre efectivamente llega.

### `backend/tests/integration/test_buffer_ttl_escalation.py`
- **Función representativa**: `test_buffer_ttl_escalation_emits_one_alert_no_requeue` (complementada por `test_buffer_ttl_sweep_ignores_non_expired_rows`)
- **Categoría**: integration (concurrencia)
- **Escenario verificado**: que una fila en el buffer de dependencias cuyo padre nunca llega dentro del tiempo de espera configurado emita exactamente una alerta de cadena de flujo huérfana, no genere reintentos de sincronización adicionales, y nunca se elimine (contrato de solo-anexado) aunque quede marcada como fallida; una fila todavía dentro del plazo permanece intacta tras el barrido.

### `backend/tests/integration/test_sync_cloud_concurrent_sessions.py`
- **Función representativa**: `test_apply_and_verify_iterations_run_concurrently_without_session_conflict`
- **Categoría**: integration (concurrencia, regresión real de producción)
- **Escenario verificado**: que el ciclo de aplicación de pendientes y el ciclo de verificación de cadena de hash del worker de sincronización en la nube puedan correr genuinamente en paralelo sin colisionar sobre la misma sesión de base de datos — reproduce y confirma la corrección de un fallo real observado en Docker donde ambos ciclos compartían una sesión no segura para concurrencia.

### `backend/tests/integration/test_offline_numbering_reconciliation_on_reconnect.py`
- **Función representativa**: `test_offline_numbering_reconciles_without_collision_on_reconnect`
- **Categoría**: integration (concurrencia — numeración offline)
- **Escenario verificado**: que facturas electrónicas numeradas localmente mientras la sucursal está genuinamente desconectada de la nube (con un intento de conexión real rechazado) lleguen al nodo central, al reconectar, con su consecutivo y su identidad exactos — sin colisión, sin hueco en la numeración y sin que el documento original sea reescrito en destino.

### `backend/tests/integration/test_apply_pending_no_self_duplicate.py`
- **Función representativa**: `test_apply_pending_batch_once_does_not_duplicate_self_originated_row`
- **Categoría**: integration (concurrencia, regresión real de producción)
- **Escenario verificado**: que el ciclo de aplicación de pendientes no reaplique ni duplique una fila que él mismo originó — reproduce un defecto real donde otorgar un permiso producía dos filas activas por un solo evento de cola, y confirma que tras la corrección queda una única fila activa y la cola liquida correctamente.

## Integración — flujos de negocio

### `backend/tests/integration/test_pairing_flow.py`
- **Función representativa**: `test_pair_happy_path`
- **Categoría**: integration
- **Escenario verificado**: que un token de emparejamiento de un solo uso, emitido por un administrador para una sucursal, permita a esa sucursal consumirlo y obtener un JWT de sincronización real. El archivo documenta 9 escenarios de emparejamiento en su docstring (reuso, expiración, revocación, sucursal incorrecta, límite de tasa, permisos de archivo del JWT persistido, entre otros) y suma después 2 pruebas más de backfill topológico de catálogo añadidas posteriormente en el mismo archivo; varios de los 9 escenarios originales están marcados `xfail` por gaps preexistentes fuera de alcance (ver `plan-pruebas.md` §7).

## Estáticas — reglas arquitectónicas

### `backend/tests/static/test_no_raw_dml_on_a_tables.py`
- **Función representativa**: `test_no_raw_dml_on_a_tables`
- **Categoría**: static
- **Escenario verificado**: que ningún archivo de las capas de API o repositorio ejecute un INSERT/UPDATE/DELETE crudo contra una tabla de solo-anexado (`[A]`) fuera de los tres helpers explícitamente permitidos — un escaneo AST que impide en tiempo de CI que alguien elud el contrato de append-only escribiendo SQL directo en vez de usar el helper canónico.

### `backend/tests/static/test_no_delete_routes.py`
- **Función representativa**: `test_openapi_contains_no_delete_operations`
- **Categoría**: static
- **Escenario verificado**: que ninguna de las dos aplicaciones FastAPI reales (admin y sucursal) exponga en su esquema OpenAPI generado en runtime una sola operación HTTP DELETE — refuerza en tiempo de ejecución, sobre el esquema real, la misma prohibición que el resto del archivo ya verifica por escaneo estático del código fuente.

## Migraciones

### `backend/tests/migrations/test_partman_parents.py`
- **Función representativa**: `test_partman_parents_match`
- **Categoría**: migrations
- **Escenario verificado**: que las 8 tablas `[A]` de mayor volumen (`salidas`, `caja`, `arqueo`, `factura_detalle`, `factura_pagos`, `log_transaccional`, `sync_queue`, `sync_log`) queden registradas como padres de partición mensual en `partman.part_config` tras aplicar las migraciones — hoy las 3 funciones del archivo están marcadas `xfail(strict=True)` por un defecto de migración conocido y documentado como fuera de alcance de este cambio.

## Rendimiento / carga

### `backend/tests/bench/test_read_local_seq_load.py`
- **Función representativa**: `test_read_local_seq_p95_and_hit_rate_under_load`
- **Categoría**: bench
- **Escenario verificado**: que la caché de lectura de secuencia local sostenga una latencia p95 ≤ 5 ms y una tasa de aciertos ≥ 95 % bajo 1.000 lecturas concurrentes ejecutadas contra un patrón de ráfaga sobre un conjunto pequeño de filas "calientes" (el patrón real de un pico de conflictos de escritura), no una muestra uniforme sobre las ~10.000 filas sembradas.

## Resumen por categoría

| Categoría | Casos documentados |
|---|---:|
| unit (núcleo) | 7 |
| unit (dian) | 2 |
| integration (concurrencia) | 5 |
| integration (flujo de negocio) | 1 |
| static | 2 |
| migrations | 1 |
| bench | 1 |
| **Total** | **19** |

## Referencias

- [`plan-pruebas.md`](./plan-pruebas.md) — pirámide de pruebas, política de cobertura, fixtures compartidas y sección de concurrencia ampliada.
- [`../runbooks/sync/`](../runbooks/sync/) — runbooks operativos de las alertas relacionadas con los casos de concurrencia listados aquí.
