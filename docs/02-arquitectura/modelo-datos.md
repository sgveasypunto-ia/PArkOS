# Modelo de Datos

> **Diccionario de datos de easypunto_parkos.** Fuente de verdad canónica: [`modelo_datos_er.mmd`](../../modelo_datos_er.mmd) (raíz del repositorio), un `erDiagram` de Mermaid con comentarios de negocio por columna. Este documento es su traducción a prosa técnica de referencia; ante cualquier diferencia entre ambos, el `.mmd` manda.

## Contenido

1. [Resumen](#1-resumen)
2. [Convenciones comunes del modelo](#2-convenciones-comunes-del-modelo)
3. [Tablas centrales — diccionario detallado](#3-tablas-centrales--diccionario-detallado)
4. [Resto de entidades — tabla resumen por clase](#4-resto-de-entidades--tabla-resumen-por-clase)
5. [Tablas fuera del ERD (non-ER)](#5-tablas-fuera-del-erd-non-er)
6. [Particionado (pg_partman)](#6-particionado-pg_partman)

---

## 1. Resumen

easypunto_parkos persiste su dominio en **54 tablas físicas** del schema `prod`: **51 modeladas explícitamente** en el ERD canónico (`modelo_datos_er.mmd`) y **3 tablas de infraestructura** que quedan deliberadamente fuera de ese ERD (ver [sección 5](#5-tablas-fuera-del-erd-non-er)).

Cada tabla pertenece a exactamente una de **5 clases semánticas**, marcadas en el `.mmd` con un tag `%% [X]` por tabla. La clase determina qué escrituras están permitidas y cómo se garantiza:

| Clase | Nombre | Cant. | Semántica | Cómo se garantiza |
|---|---|---|---|---|
| `[V]` | Proyección versionada | 26 | Cada cambio de negocio inserta una fila nueva (`vigente_desde` / `vigente_hasta`); UPDATE crea versión, DELETE nunca ocurre | Convención de aplicación (insert-only lógico); `estado` se fija al insertar |
| `[L-E]` | Evento puro | 3 | El estado se deriva de otros eventos; solo INSERT | Sin columna de estado propia — se deriva vía vista (p. ej. `V_INGRESO_ESTADO`, `V_FACTURA_ESTADO`) |
| `[L-W]` | Workflow encadenado | 6 | Cada transición es una fila nueva con FK `uuid_*_padre` a la fila anterior (cadena lineal) | Encadenamiento por FK propio (UK02); la fila ya escrita nunca se actualiza |
| `[L-S]` | Sesión / ciclo | 2 | UPDATE legítimo (cierre) sobre `estado` / `timestamp_cierre` | El UPDATE exige registrar el hecho en `log_transaccional` en la misma transacción |
| `[A]` | Fuente de verdad append-only | 14 | Inmutable tras el INSERT | `REVOKE UPDATE/DELETE` a nivel de rol + trigger de bloqueo |

26 + 3 + 6 + 2 + 14 = **51**, cifra que coincide con el conteo real de bloques de entidad en el `.mmd`.

### Validación de integridad esquema↔código

Se ejecutó `openspec/scripts/check_schema_match.py` — compara el `.mmd` contra el Postgres real en 8 checks (existencia de tabla, columnas, UKs, FKs, revokes, triggers, particiones, entre otros) — contra las dos bases activas del entorno de referencia: **cloud** (puerto 5432) y **sucursal** (puerto 5433). Resultado: **100% match en ambas**. Este documento puede tratarse como fiel reflejo del esquema real vigente al momento de escribirse.

### Documentos relacionados

- Diagrama de clases: [`./diagramas-uml/02-clases.mermaid`](./diagramas-uml/02-clases.mermaid)
- Decisiones técnicas (4FN, versionado, cadenas de hash): [`./decisiones-tecnicas.md`](./decisiones-tecnicas.md)
- Seguridad y control de acceso (REVOKE, roles, mínimo privilegio): [`./seguridad.md`](./seguridad.md)
- Runbooks operativos de sincronización: [`../runbooks/sync/`](../runbooks/sync/)

---

## 2. Convenciones comunes del modelo

Para no repetir lo idéntico en cada tabla, estos bloques de columnas son estándar en (casi) todo el modelo y solo se nombran por excepción en las secciones siguientes:

- **PK**: `uuid` (UUIDv4 generado en el nodo que crea la fila — offline-safe, sin colisión entre sedes) en 50 de las 51 tablas. Única excepción: `alert_types`, con PK de negocio `tipo_alerta` (string).
- **Audit** (todas las tablas): `created_at` (timestamp UTC de inserción), `created_by` (uuid del usuario que originó la fila).
- **Versioning** (solo tablas `[V]`): `vigente_desde` (inicio de vigencia, parte de la UK de negocio), `vigente_hasta` (NULL = versión vigente; el momento de sistema del cierre queda en `log_transaccional`), `estado` (`activo` | `inactivo`).
- **Sync** (tablas replicadas cloud↔sucursal): `sync_status` (`pendiente` | `sincronizado` | `error`), `sync_timestamp`, `sync_attempts`. Excepción: `sync_queue_lw_buffer` y `alert_types` declaran estas tres columnas pero **no las usan** — son tablas *out-of-catalog* que existen igual (sembradas de forma idempotente) en cloud y en cada sucursal, sin replicarse fila a fila.

En las tablas siguientes solo se listan las columnas de negocio y las claves; los bloques de arriba se dan por heredados salvo que se indique lo contrario.

---

## 3. Tablas centrales — diccionario detallado

Cobertura en detalle: `usuarios`, `sucursal`, `vehiculos`, `subscripciones_cliente`, `ingreso`, `salidas`, `anulaciones`, `facturas`, `factura_electronica`, `log_transaccional`, `sync_queue`, `sync_conflict` (12 tablas). Se agregó `salidas` a la lista sugerida por ser el evento que cierra toda estadía abierta en `ingreso` y por ser, junto con `ingreso`, uno de los ejes del flujo operativo central.

### usuarios · `[V]`

*Maestro global de operadores; se administra en cloud y se replica a sucursales para permitir login offline.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador de la fila/versión |
| nombre | string | | Nombre de la persona |
| apellido | string | | Apellido de la persona |
| cedula | string | UK1 (+ vigente_desde) | Documento de identidad |
| email | string | | Correo de contacto y recuperación de acceso |
| password_hash | string | | Hash de la contraseña (nunca en claro) |
| fecha_cambio_password | timestamp | | Cuándo se estableció la contraseña actual (rotación por política) |
| rol | string | | Rol grueso: `admin` \| `operador` \| `supervisor` (el detalle fino vive en `permisos_usuario`) |

**Relaciones clave:** origen de `login` (sesiones), `permisos_usuario` (permisos otorgados), `usuarios_sucursal` (sedes autorizadas), y referenciado como actor en `reimpresion_ticket`, `anulaciones`, `alerta`, `sesion` (apertura y cierre de turno), `validacion_evento` y `log_transaccional`.

### sucursal · `[V]`

*Maestro de sedes; eje de particionamiento del sistema — la réplica local de cada sede contiene solo sus propias filas más los catálogos compartidos.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador de la fila/versión |
| nombre | string | | Nombre comercial de la sede |
| direccion | string | | Dirección física (se imprime en ticket/factura) |
| telefono | string | | Teléfono de contacto de la sede |
| prefijo_nombre | string | UK1 (+ vigente_desde) | Código corto identificador de la sede |
| ciudad | string | | Ciudad de la sede |
| horario | string | | Horario de operación publicado |
| uuid_tipo_sucursal | uuid | FK → tipo_sucursal | Modelo operativo de la sede |
| uuid_empresa | uuid | FK → empresa | Empresa a la que pertenece |

**Relaciones clave:** es la clave de scoping/particionamiento de prácticamente todo el modelo operativo — catálogos con override por sede (`configuracion_tolerancias`, `configuracion_seguridad`, `tarifas_sucursal`, `cantidad_vehiculos_sucursal`, `resolucion_facturacion`), operación diaria (`usuarios_sucursal`, `ingreso`, `salidas`, `anulaciones`, `reclamos`, `reimpresion_ticket`, `sesion`, `caja`, `arqueo`, `alerta`), toda la familia de facturación (`facturas`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos`, `factura_electronica`, `envio_dian`, `revocacion_factura`), sincronización (`sync_queue`, `sync_conflict`, `sync_log`, `sync_queue_lw_buffer`, `validacion_evento`) y auditoría (`log_transaccional`, `login`).

### vehiculos · `[V]`

*Vehículos registrados; solo se requieren para el flujo de suscripción — el vehículo ocasional entra con placa libre directamente en `ingreso`.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador de la fila/versión |
| placa | string | UK1 (+ vigente_desde) | Placa del vehículo |
| uuid_tipo_vehiculo | uuid | FK → tipos_vehiculo | Tipo del vehículo (valida `mismo_tipo_vehiculo` del plan) |

**Relaciones clave:** cubierto por `subscripcion_vehiculos` (junction con `subscripciones_cliente`).

### subscripciones_cliente · `[V]`

*Contratación de un plan por un cliente; renovar es una fila nueva; el ingreso suscrito la referencia.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador de la fila/versión |
| uuid_cliente | uuid | FK → clientes | Cliente que contrata |
| uuid_sucursal | uuid | FK → sucursal | Sede donde se vendió/aplica |
| uuid_tipo_subscripcion | uuid | FK → tipo_subscripciones | Plan contratado (versión vigente al contratar) |
| fecha_inicio_cobertura | date | | Inicio de cobertura (puede diferir de la fecha de compra) |
| fecha_vencimiento | date | | Fin de cobertura (inicio + `duracion_dias` del plan) |

**Relaciones clave:** cubre vehículos vía `subscripcion_vehiculos`; referenciada opcionalmente por `ingreso` (estadía suscrita, no ocasional) y por `reclamos` (`tipo_reclamable = subscripcion`).

### ingreso · `[L-E]`

*Evento núcleo del negocio: un vehículo entró a la sede; se crea offline-first y sube a cloud.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador del evento |
| uuid_sucursal | uuid | FK → sucursal | Sede donde entró el vehículo |
| placa | string | | Placa digitada por el operador (hecho del evento; puede no existir en `vehiculos`) |
| uuid_tipo_vehiculo | uuid | FK → tipos_vehiculo | Tipo observado al entrar (define la tarifa a aplicar) |
| uuid_subscripcion_cliente | uuid | FK → subscripciones_cliente (nullable) | Suscripción aplicada; NULL = estadía ocasional tarifada |
| fecha_ingreso | timestamp | | Momento de entrada; inicio del cálculo de estadía |
| observaciones | text | | Anotaciones del operador (estado del vehículo, objetos visibles) |

**Notas de diseño (4FN):** no tiene columna `estado` ni `fecha_salida` propias — el estado (activo/cerrado) se deriva vía la vista `V_INGRESO_ESTADO` (según exista una salida no anulada) y `fecha_salida` se obtiene de `salidas`.

**Relaciones clave:** origen de `reimpresion_ticket`, `salidas` (1:0..1, "sin salida mientras activo"), `anulaciones`, `reclamos` y `facturas`.

### salidas · `[A]`

*Evento de salida del vehículo; cierra la estadía (tiempo = `fecha_salida` − `fecha_ingreso`). Una salida errónea se corrige vía `anulaciones` (`tipo_anulable = salida`), nunca por UPDATE/DELETE.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador del evento |
| uuid_sucursal | uuid | FK → sucursal | Sede (redundancia controlada de particionamiento para sync) |
| uuid_ingreso | uuid | FK → ingreso; UK1 filtrada | Una salida **no anulada** por ingreso (índice único parcial; la placa se deriva vía `ingreso`) |
| fecha_salida | timestamp | | Momento de salida; fin del cálculo de estadía |
| fecha_retencion_hasta | date | | Retención operacional corta (p. ej. 2 años); particionable por mes |

**Relaciones clave:** origen de `facturas` y de `reclamos` (`tipo_reclamable = salida`); puede ser anulada por `anulaciones`. Tabla particionada (ver [sección 6](#6-particionado-pg_partman)).

### anulaciones · `[L-W]`

*Workflow de anulación de un `ingreso` O de una `salida`, con cadena de aprobación; solo la fila ejecutada anula.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador de esta transición |
| uuid_sucursal | uuid | FK → sucursal | Sede del ingreso afectado |
| tipo_anulable | string | | `ingreso` \| `salida` — qué se anula |
| uuid_ingreso | uuid | FK → ingreso | Ingreso afectado (siempre presente; en anulación de salida es el ingreso de esa salida) |
| uuid_salida | uuid | FK → salidas (nullable) | Salida anulada (solo si `tipo_anulable = salida`) |
| uuid_usuario | uuid | FK → usuarios | Usuario que ejecuta esta transición (solicita, aprueba o ejecuta) |
| motivo | text | | Justificación de la transición |
| uuid_anulacion_padre | uuid | FK → anulaciones; UK2 (cadena lineal) | Fila anterior de la cadena (NULL = solicitud inicial) |
| timestamp_evento | timestamp | | Cuándo se ejecutó esta transición |
| estado | string | | `solicitada` \| `aprobada` \| `ejecutada` |

**Relaciones clave:** autoexplicativa por diseño workflow (`uuid_anulacion_padre` apunta a la transición previa).

### facturas · `[L-E]`

*Documento de venta interno emitido en la sede; sus totales son hechos legales de la emisión, nunca recalculados.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador del documento |
| uuid_sucursal | uuid | FK → sucursal | Sede emisora |
| subtotal | decimal | | Suma de líneas tal como se emitió |
| descuento | decimal | | Descuento aplicado a nivel de documento |
| total | decimal | | Valor emitido del documento (hecho legal del evento) |
| uuid_ingreso | uuid | FK → ingreso | Estadía que se factura |
| uuid_salida | uuid | FK → salidas | Salida que cerró la estadía facturada |
| fecha_retencion_hasta | date | | Retención DIAN: 5+ años desde emisión |

**Notas de diseño (4FN):** no tiene columna `estado` propia — se deriva vía la vista `V_FACTURA_ESTADO` (según haya anulaciones ejecutadas).

**Relaciones clave:** desglosada en `factura_detalle`, `factura_impuestos`, `factura_otros_cobros` y `factura_pagos`; tiene 1:0..1 con `factura_electronica`; puede recibir cargos de `reimpresion_ticket`; puede ser objeto de `reclamos`.

### factura_electronica · `[L-E]`

*Versión DIAN de la factura interna; se emite EN la sucursal con SU resolución propia, y cloud la envía al proveedor vía `envio_dian`.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador del documento electrónico |
| uuid_sucursal | uuid | FK → sucursal | Sede emisora |
| uuid_factura | uuid | FK → facturas; UK2 (1:1) | Factura interna que representa |
| uuid_cliente | uuid | FK → clientes | Adquirente (titular fiscal del documento) |
| uuid_resolucion_facturacion | uuid | FK → resolucion_facturacion; UK1 (+ consecutivo) | Resolución DIAN de la sucursal emisora |
| prefijo | string | | Snapshot del prefijo de la resolución al emitir |
| consecutivo | bigint | UK1 | Asignado en sucursal dentro del rango de su resolución |
| descuento | decimal | | Descuento reflejado en el documento electrónico |
| fecha_retencion_hasta | date | | Retención DIAN: 5+ años desde emisión |

**Notas de diseño (4FN):** `numero_completo`, `cufe` y `reportado_dian` fueron eliminados del modelo — se derivan vía vista (`numero_completo` = `prefijo` + `consecutivo`) y vía `envio_dian` (`cufe`, estado de reporte a la DIAN). El estado de emisión se deriva vía `V_FE_ESTADO_DIAN` (según `revocacion_factura` / `envio_dian`).

**Relaciones clave:** enviada por `envio_dian` (cloud-only); puede ser objeto de `revocacion_factura` (como revocada o como reemplazo).

### log_transaccional · `[A]`

*Bitácora probatoria de toda acción relevante, con cadena de hashes por sede; hace auditable el patrón insert-only del resto del modelo.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador del registro de log |
| uuid_usuario | uuid | FK → usuarios | Quién ejecutó la acción |
| uuid_sucursal | uuid | FK → sucursal | Dónde se ejecutó |
| accion | string | | `crear` \| `actualizar` \| `eliminar` \| `revocar` \| `archivar` \| etc. |
| tabla_afectada | string | | Tabla sobre la que se actuó |
| uuid_registro_afectado | uuid | | Uuid del registro en `tabla_afectada` (polimórfico, sin FK física) |
| uuid_referencia | uuid | FK opcional | FK al evento origen (p. ej. una fila de `anulaciones`) |
| datos_anteriores | json | | Snapshot pre-cambio (NULL si es creación) |
| datos_nuevos | json | | Snapshot post-cambio (NULL si es lectura) |
| timestamp_evento | timestamp | | Cuándo ocurrió la acción en el negocio |
| hash_anterior | string | | SHA256 del log previo del mismo `uuid_sucursal` |
| hash_actual | string | | SHA256 de esta fila + `hash_anterior` |
| fecha_retencion_hasta | date | | Retención por compliance (depende de la acción; default 5 años) |

**Por qué importa:** es el registro obligatorio que respalda los UPDATE legítimos de las tablas `[L-S]` (`login`, `sesion`) y la evidencia probatoria de cadena de hashes del sistema, en el mismo espíritu que `revocacion_factura`. Tabla particionada (ver [sección 6](#6-particionado-pg_partman)).

### sync_queue · `[A]`

*Outbox de la sucursal hacia cloud. Es la única tabla del modelo con estado mutable por diseño — excepción explícita al patrón append-only, necesaria para implementar el patrón outbox.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador del ítem de cola |
| uuid_sucursal | uuid | FK → sucursal | Sucursal dueña de la cola |
| operacion | string | | Operación transportada (insert, cambio de estado) |
| tabla | string | | Tabla del registro afectado |
| uuid_registro | uuid | | Uuid del registro a sincronizar (polimórfico) |
| datos | json | | Payload del registro tal como debe aplicarse en cloud |
| prioridad | int | | Orden de despacho (p. ej. facturación antes que métricas) |
| estado | string | | `pendiente` \| `en_progreso` \| `exitoso` \| `fallido` \| `descartado` |
| intentos | int | | Reintentos de despacho consumidos |
| next_retry_at | timestamp | | Próximo reintento programado (backoff) |
| ultimo_error | text | | Último error del despacho, para diagnóstico |

**Ver también:** runbook [`sync_backlog.md`](../runbooks/sync/sync_backlog.md). Tabla particionada (ver [sección 6](#6-particionado-pg_partman)).

### sync_conflict · `[A]`

*Conflictos detectados al sincronizar (la versión local difiere de la de cloud); guarda ambas versiones y la resolución aplicada.*

| Columna | Tipo | Clave | Descripción |
|---|---|---|---|
| uuid | uuid | PK | Identificador del conflicto |
| uuid_sucursal | uuid | FK → sucursal | Sucursal involucrada |
| tabla | string | | Tabla en conflicto |
| uuid_registro | uuid | | Registro en conflicto (polimórfico) |
| datos_local | json | | Versión de la sucursal al detectar el conflicto |
| datos_cloud | json | | Versión de cloud |
| politica | string | | Regla de resolución aplicada (last-write-wins, cloud-wins) |
| resolucion | string | | Resultado de aplicar la política |
| timestamp_evento | timestamp | | Cuándo se detectó el conflicto |
| fecha_retencion_hasta | date | | Retención operacional: 1 año post-resolución |

**Ver también:** runbook [`conflict_rate.md`](../runbooks/sync/conflict_rate.md).

---

## 4. Resto de entidades — tabla resumen por clase

Las 39 entidades restantes del `.mmd` (51 totales − 12 detalladas arriba), agrupadas por clase.

### `[V]` — Proyección versionada (22 restantes)

| Tabla | Propósito |
|---|---|
| permisos | Catálogo global de permisos atómicos del sistema |
| permisos_usuario | Junction usuario–permiso; otorgar inserta fila, revocar cierra vigencia |
| tipo_persona | Catálogo: clasifica clientes (`natural` \| `jurídica`); define exigencias de facturación electrónica |
| tipos_vehiculo | Catálogo: clases de vehículo (carro, moto, bicicleta); base de tarifas, cupos y suscripciones |
| tipo_subscripciones | Catálogo: planes comerciales de suscripción |
| tipo_tarifa | Catálogo: modalidades de cobro por estadía (hora, fracción, plena, nocturna) |
| tipo_sucursal | Catálogo: clasifica sucursales por modelo operativo; sus características habilitan módulos |
| tipo_arqueo | Catálogo: clasifica los arqueos (cierre de turno, auditoría sorpresiva, cierre de sesión) |
| impuestos | Catálogo tributario (IVA, INC); la factura nunca lo lee en vivo, copia snapshot a `factura_impuestos` |
| otros_cobros | Catálogo de cargos adicionales facturables (seguro, lavado); snapshot en `factura_otros_cobros` |
| costos_servicios | Catálogo de servicios operativos internos (p. ej. reimpresión de ticket) |
| configuracion_tolerancias | Umbrales de diferencia aceptable en arqueos; patrón default global + override por sucursal |
| configuracion_seguridad | Política de acceso (expiración de password, bloqueo por intentos); default global + override por sucursal |
| empresa | Identidad tributaria del operador ante la DIAN; la numeración vive en `resolucion_facturacion` |
| resolucion_facturacion | Resolución de facturación DIAN propia de cada sucursal |
| usuarios_sucursal | Junction: autoriza a un usuario a operar en una sede (el login valida contra esta tabla) |
| documentos | Archivos administrativos de la sede (logos, plantillas), inline en base64 para disponibilidad offline |
| tarifas_sucursal | Precio por sede × tipo de vehículo × modalidad; el histórico reconstruye con qué tarifa se cobró |
| cantidad_vehiculos_sucursal | Cupo máximo de la sede por tipo de vehículo (cupo agregado, sin asignación de puesto individual) |
| clientes | Maestro de clientes identificados (facturación electrónica o suscripciones); el ocasional no requiere fila |
| clientes_b2b | Extensión 1:1 de clientes para corporativos con convenio (flotas, empresas) |
| subscripcion_vehiculos | Junction suscripción–vehículos cubiertos |

### `[L-E]` — Evento puro (0 restantes)

Las 3 tablas `[L-E]` del modelo (`ingreso`, `facturas`, `factura_electronica`) están cubiertas en la [sección 3](#3-tablas-centrales--diccionario-detallado).

### `[L-W]` — Workflow encadenado (5 restantes)

| Tabla | Propósito |
|---|---|
| reimpresion_ticket | Workflow de reimpresión de ticket perdido/dañado; cobra el servicio vigente y se carga a factura |
| reclamos | Workflow de reclamos del cliente sobre objetos reclamables (referencia polimórfica: ingreso, salida, factura o subscripción) |
| alerta | Workflow de alertas operativas; nace automática (arqueo, sync, offline) o manual (fraude) |
| envio_dian | Cloud-only: único punto de salida hacia el proveedor de facturación electrónica DIAN |
| validacion_evento | Cloud-only: bandeja del admin para validar cada evento recibido de sucursal |

### `[L-S]` — Sesión / ciclo (2 restantes)

| Tabla | Propósito |
|---|---|
| login | Bitácora de intentos de autenticación; alimenta el bloqueo por intentos fallidos |
| sesion | Turno de caja de un operador; base inicial + pagos del turno = esperado del arqueo |

### `[A]` — Fuente de verdad append-only (10 restantes)

| Tabla | Propósito |
|---|---|
| factura_detalle | Líneas de la factura: cada fila es un concepto cobrado con los valores exactos emitidos |
| factura_impuestos | Impuestos aplicados a la factura con snapshot de la tarifa vigente al emitir |
| factura_otros_cobros | Cargos adicionales aplicados a la factura, mismo patrón snapshot que los impuestos |
| factura_pagos | Medios de pago que saldaron la factura (pago mixto posible); reverso = fila compensatoria, nunca UPDATE |
| revocacion_factura | Revocaciones/notas de factura electrónica con cadena de hashes probatoria por sede |
| caja | Fotos periódicas del dinero en caja por sede; la evolución es la serie temporal de filas |
| arqueo | Conteo físico de caja contra lo esperado, clasificado por tipo; superar tolerancia dispara alerta |
| sync_log | Métrica por ciclo de sincronización de cada sucursal; alimenta alertas `sync_failure` y `branch_offline` |
| sync_queue_lw_buffer | Buffer de dependencia: retiene una fila hasta que su padre declarado (`depends_on`) llegue (TTL 24h) |
| alert_types | Catálogo de tipos de alerta, sembrado idempotente en cloud y sucursal; out-of-catalog, nunca replica |

---

## 5. Tablas fuera del ERD (non-ER)

Además de las 51 entidades de `modelo_datos_er.mmd`, el schema `prod` tiene **3 tablas de infraestructura** que quedan fuera del ERD por decisión de diseño explícita — no por omisión. Con estas, el total de tablas físicas reales es **54**.

Las 3 están documentadas de forma consistente en tres puntos del código:

- `LOCAL_ONLY_CATALOG` en [`backend/packages/parkos_core/src/parkos_core/sync/catalog/local_only_catalog.py`](../../backend/packages/parkos_core/src/parkos_core/sync/catalog/local_only_catalog.py)
- `EXPECTED_NON_ER_TABLES` en `openspec/scripts/check_schema_match.py:107`
- El criterio de diseño está registrado en `ADR-002` — `openspec/changes/archive/2026-09-09-sync-overhaul/adr/002-50-table-canon.md`

| Tabla | FKs reales | Nota |
|---|---|---|
| `idempotency_keys` | Ninguna | Infraestructura pura (deduplicación de requests); sin integridad referencial a negocio. Confirmado en su modelo ORM (`backend/packages/parkos_core/src/parkos_core/models/A/idempotency_keys.py`). |
| `revoked_sync_jwts` | Ninguna | Infraestructura de seguridad pura (lista de revocación de JWT); sin integridad referencial a negocio. Confirmado en `.../models/A/revoked_sync_jwts.py`. |
| `pairing_tokens` | `sucursal`, `usuarios` | Sí tiene FKs reales de negocio. Confirmado en `.../models/A/pairing_tokens.py`. |

**Por qué importa:** un visor de base de datos que arma su diagrama a partir de las FK reales de Postgres mostrará `idempotency_keys` y `revoked_sync_jwts` como tablas "sueltas", sin conexión al resto del grafo. Esto es **comportamiento esperado, no un bug** — son tablas de infraestructura sin relaciones de negocio por diseño; `pairing_tokens`, en cambio, sí aparecerá conectada.

---

## 6. Particionado (pg_partman)

8 tablas de alto volumen usan particionado gestionado por `pg_partman`:

| Tabla | Clase | Motivo |
|---|---|---|
| factura_detalle | `[A]` | Una fila por línea de factura — crece con cada venta |
| factura_pagos | `[A]` | Una o más filas por factura pagada (pago mixto) |
| log_transaccional | `[A]` | Bitácora de toda acción relevante del sistema |
| sync_log | `[A]` | Una fila por ciclo de sincronización de cada sucursal |
| sync_queue | `[A]` | Outbox de sincronización — alta rotación |
| caja | `[A]` | Fotos periódicas del efectivo por sede (serie temporal) |
| arqueo | `[A]` | Un conteo por turno/auditoría por sede |
| salidas | `[A]` | Una fila por estadía cerrada |

**Nota sobre la evidencia en el `.mmd`:** el `.mmd` confirma partición explícita ("particionable por mes") en `caja`, `salidas` y `arqueo`, y de forma más genérica ("archivado/particiones") en `sync_conflict`, `sync_log` y `log_transaccional`. No trae mención textual de partición para `factura_detalle`, `factura_pagos` ni `sync_queue`; su inclusión en esta lista de 8 se apoya en la configuración real de `pg_partman`, no en el comentario del ERD.

**Posible tabla adicional a confirmar:** `sync_queue_lw_buffer` (fuera de esta lista de 8; ver [sección 4](#4-resto-de-entidades--tabla-resumen-por-clase)) declara partición diaria **explícita** por `buffered_at` directamente en el `.mmd` ("clave de partición, particionado diario por pg_partman") — evidencia textual más fuerte que la de varias de las 8 tablas de arriba. Vale confirmar con el equipo si falta en el listado de tablas particionadas o si se excluye a propósito por ser un buffer efímero (TTL 24h) y no una tabla de negocio de alto volumen sostenido.

---

**Próximo paso:** para el diagrama de clases relacionado y el detalle de las decisiones de arquitectura que motivan el patrón de versionado/4FN, ver [`./decisiones-tecnicas.md`](./decisiones-tecnicas.md) y [`./diagramas-uml/02-clases.mermaid`](./diagramas-uml/02-clases.mermaid). Índice general de la documentación: [`../README.md`](../README.md).
