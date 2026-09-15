# Requisitos Funcionales — easypunto_parkos

[Índice general](../README.md) · [Historias de usuario](historias-usuario.md) · [Requisitos no funcionales](no-funcionales.md) · [Decisiones técnicas](../02-arquitectura/decisiones-tecnicas.md) · [Modelo de datos](../02-arquitectura/modelo-datos.md) · [Referencia de API](../03-desarrollo/api-reference.md)

> Catálogo de requisitos funcionales **reales**, verificados contra el código en `E:\easypunto_parkos` (routers de `backend/packages/parkos_core/src/parkos_core/api/v1/`, motor de sync, migraciones). Todo lo marcado **[Por definir]** o **[Roadmap]** no está implementado; se cita su fuente de planeación.

## 0. Contrato transversal: Consulta / Inserción / Actualización

Todo recurso de la API, sin excepción, expone como máximo tres operaciones — nunca una cuarta de borrado (`AGENTS.md` § Arquitectura, principio no negociable):

| Operación | Semántica | Verbo HTTP |
|---|---|---|
| **Consulta** | `SELECT` — lectura directa o vista derivada | `GET` |
| **Inserción** | `INSERT` de una fila nueva (nueva versión, evento o fila de un `[A]`) | `POST` |
| **Actualización** | Bi-temporal: cierra la fila vigente (`vigente_hasta = ahora`, `estado = inactivo`) **e** inserta la fila nueva con el estado actualizado | `PUT` |

No existe operación de eliminación en ningún nivel (API, ORM, SQL). Una corrección que conceptualmente "borraría" algo se modela siempre como una de estas tres formas:

1. Una fila nueva en una tabla de workflow (`anulaciones`, `reimpresion_ticket`, `reclamos`, `alerta`).
2. Una fila compensatoria (`factura_pagos.tipo_movimiento = 'reverso'`, referenciando `uuid_pago_revertido`).
3. Un estado derivado, calculado en el momento de la consulta y nunca almacenado (`V_FACTURA_ESTADO`, `V_INGRESO_ESTADO`, `V_FE_ESTADO_DIAN`, `V_RESOLUCION_CONSECUTIVO`).

El contrato se aplica de forma distinta según la **clase de auditoría** de cada tabla (`modelo_datos_er.mmd`, fuente de verdad; conteos confirmados 1:1 contra el diagrama real):

| Clase | Cant. | Semántica | Operación de "actualización" | Ejemplo |
|---|---|---|---|---|
| `[V]` proyección versionada | 26 | Estado actual con histórico completo | Cierra + inserta (bi-temporal) | `tipos_vehiculo`, `sucursal`, `usuarios` |
| `[L-E]` evento puro | 3 | El estado se **deriva** de otros eventos; nunca se muta | Solo inserción (evento nuevo) | `ingreso`, `facturas`, `factura_electronica` |
| `[L-W]` workflow encadenado | 6 | Cada transición es una fila nueva enlazada a la anterior (`uuid_*_padre`) | Solo inserción (nueva transición) | `anulaciones`, `reclamos`, `alerta`, `reimpresion_ticket`, `envio_dian`, `validacion_evento` |
| `[L-S]` sesión/ciclo | 2 | `UPDATE` limitado a columnas de cierre, con `log_transaccional` obligatorio en la misma transacción | `UPDATE` acotado por columna | `login`, `sesion` |
| `[A]` fuente de verdad append-only | 14 | Inmutable; `REVOKE UPDATE, DELETE` a nivel de base de datos | Solo inserción (evento o compensación) | `factura_detalle`, `factura_pagos`, `log_transaccional`, `caja`, `arqueo`, `sync_*` |

51 entidades de dominio (`modelo_datos_er.mmd`) + 3 tablas operativas sin bloque `%%[...]` en el diagrama (`idempotency_keys`, `pairing_tokens`, `revoked_sync_jwts`, todas `[A]`) = **54 tablas físicas**, confirmado contra `openspec/PROJECT_CONTEXT.md` (ADR-002) y contra el propio `.mmd`.

## 1. Gestión de catálogos

Nueve catálogos de configuración comparten un único router genérico parametrizable (`api/router_factory.py:39-243`, montado en `api/v1/catalogos.py:96`), todos `[V]`, todos con el mismo contrato C/I/A:

| Recurso | Ruta base | Permiso | Test |
|---|---|---|---|
| Tipo de persona (natural / jurídica) | `/catalogos/tipo-persona` | `config_catalogo` | `test_tipo_persona_crud.py` |
| Tipos de vehículo | `/catalogos/tipos-vehiculo` | `config_catalogo` | `test_tipos_vehiculo_crud.py` |
| Tipos de suscripción | `/catalogos/tipo-subscripciones` | `config_catalogo` | `test_tipo_subscripciones_crud.py` |
| Tipo de tarifa (hora, fracción, plena, nocturna) | `/catalogos/tipo-tarifa` | `config_catalogo` | `test_tipo_tarifa_crud.py` |
| Tipo de sucursal (modelo operativo) | `/catalogos/tipo-sucursal` | `config_catalogo` | `test_tipo_sucursal_crud.py` |
| Tipo de arqueo (cierre de turno, auditoría, cierre de sesión) | `/catalogos/tipo-arqueo` | `config_catalogo` | `test_tipo_arqueo_crud.py` |
| Impuestos (IVA, INC) | `/catalogos/impuestos` | `config_catalogo` | `test_impuestos_crud.py` |
| Otros cobros (seguro, lavado) | `/catalogos/otros-cobros` | `config_catalogo` | `test_otros_cobros_crud.py` |
| Costos de servicios internos (reimpresión) | `/catalogos/costos-servicios` | `config_catalogo` | `test_costos_servicios_crud.py` |

**RF-CAT-01**: cada recurso expone `GET ""` (lista), `GET /{uuid}` (detalle), `GET /{uuid}/history` (histórico completo de versiones), `POST ""` (alta de una nueva versión), `PUT /{uuid}` (versionado bi-temporal). Issuer requerido: `admin-` u `operador-`.

**RF-CAT-02**: los catálogos son datos maestros replicados de cloud a sucursal (política de sync `broadcast`); una sucursal offline sigue operando con la última copia local sincronizada.

**RF-CAT-03 — Configuración con excepción por sucursal**: `configuracion_tolerancias` y `configuracion_seguridad` (`api/v1/configuracion.py`) siguen el patrón "default global (`uuid_sucursal IS NULL`) + override opcional por sede"; `GET /configuracion/configuracion-seguridad/efectiva` resuelve cuál aplica. Fuente: `test_config_override_resolution.py`.

**RF-CAT-04 — Identidad tributaria y comercial**: `api/v1/empresa.py` gestiona `empresa` (razón social, NIT, régimen), `sucursal`, `documentos` (base64, tope 1 MB — `test_documentos_b64_cap.py`), `tarifas_sucursal` (precio por sede × tipo de vehículo × modalidad) y `cantidad_vehiculos_sucursal` (cupo por tipo). `resolucion_facturacion` (numeración DIAN por sede) es **exclusiva de cloud** — excluida del despliegue de sucursal por el boundary de `api/v1/__init__.py:86-130` (`PARKOS_DEPLOY=branch`).

## 2. Onboarding y pairing de sucursal

**RF-PAIR-01**: un administrador emite un token de emparejamiento de un solo uso con vigencia de 24 horas (`DEFAULT_TTL_HOURS`, `repo/pairing.py:56`) para una sucursal nueva. Solo se persiste el hash SHA-256 del token; el texto plano se devuelve una única vez. Límite: 5 emisiones por hora por administrador (`api/rate_limit_pairing.py`).

**RF-PAIR-02**: la sucursal consume el token contra `POST /sync/pair`. El consumo es atómico (`SELECT ... FOR UPDATE SKIP LOCKED`, `repo/pairing.py::consume_pairing_token`) para que dos intentos concurrentes con el mismo token no lo dupliquen. Como resultado, la sucursal recibe un JWT `sync-agent-` de larga duración.

**RF-PAIR-03**: la revocación de un token o del acceso de sincronización de una sucursal se expresa como una fila nueva en `revoked_sync_jwts` (nunca `UPDATE`, porque `pairing_tokens` es `[A]` inmutable). Endpoints: `POST /admin/pairing-tokens/{uuid}/revoke`, `POST /admin/sucursales/{uuid}/revoke-sync` — ambos `POST`, nunca `DELETE`.

**RF-PAIR-04 [Por definir]**: el flujo de aprovisionamiento de la infraestructura de la sucursal (contenedor, base de datos local) más allá del intercambio del token está fuera del alcance verificado en esta pasada — ver `infra/deploy/docker-compose.local.yml` y el entrypoint compartido (`infra/docker/entrypoint.sh`, mencionado en `AGENTS.md`) para el detalle operativo; documentarlo en [../05-manuales/operaciones.md](../05-manuales/operaciones.md).

## 3. Sincronización bidireccional

El motor de sync (`sync/motor/sync_motor.py::SyncMotor`) opera en dos modos, seleccionables por bandera de entorno (`PARKOS_SYNC_ENGINE`, `EngineMode`): `LEGACY` (aplicador previo, kill switch de rollback) y el motor **dirigido por catálogo** (`sync/motor/apply_row.py`), que es el modo activo por defecto en el código actual.

**RF-SYNC-01 — Transporte**: HTTP polling exclusivo (sin WebSocket en esta versión). Endpoints, todos bajo issuer `sync-agent-` salvo donde se indica:

| Endpoint | Función | Límite de tasa |
|---|---|---|
| `POST /sync/pair` | Emparejamiento inicial (público — el token plano es la credencial) | — |
| `POST /sync/push` | Sucursal → cloud: envía la cola pendiente | 60/min |
| `POST /sync/pull` | Cloud → sucursal (o sucursal → cloud): descarga cambios | 120/min |
| `POST /sync/events` | Recepción de filas individuales empujadas por el otro nodo | comparte cupo de `pull` |
| `POST /sync/heartbeat` | Reporta salud/actividad de la sucursal | 10/min |
| `POST /sync/rotate-jwt` | Rotación de la credencial `sync-agent-` | 1/min |
| `GET /sync/hello` | *Handshake* de protocolo dual: anuncia versión de protocolo y revisión de catálogo para que la sucursal elija automáticamente su aplicador de sync, antes de autenticarse. Sin auth (no expone datos sensibles); el cliente debe cachear la respuesta 300 s | — |

**RF-SYNC-02 — Orden de aplicación por dependencias**: `apply_batch` ordena un lote topológicamente sobre `spec.depends_on` (`sync/motor/dependency_orderer.py`) antes de aplicar fila por fila. Si el padre declarado de una fila aún no llegó, la fila se retiene en `sync_queue_lw_buffer` con TTL de 24 horas (`expires_at`) en lugar de fallar; al expirar sin resolverse, se marca `parent_missing_timeout`.

**RF-SYNC-03 — Aislamiento de filas inválidas**: una fila cuyo payload no puede aplicarse (columna inexistente, tipo inválido) se aísla sin interrumpir el resto del lote (fallback por fila) — `test_apply_loop_isolates_one_poisoned_row_via_per_row_fallback`.

**RF-SYNC-04 — Resolución de conflictos por clase de tabla** (`sync/conflict_resolver.py`, `AGENTS.md` § Sync; a validar contra `openspec/specs/sync-motor/spec.md` — ver nota abajo):

| Clase | Política por defecto |
|---|---|
| `[V]` | Manual (requiere intervención) |
| `[L-E]` | Append (ambas versiones conviven como eventos) |
| `[L-W]` | Append (la transición más reciente gana; ninguna se descarta) |
| `[A]` | Append |
| `[L-S]` | Manual |

**RF-SYNC-05 — Cadena de hash resiliente a sync parcial**: `log_transaccional` y `revocacion_factura` mantienen su cadena de hash por `uuid_sucursal`; cloud preserva la cadena de la sucursal tal cual y solo la extiende con filas propias de cloud (nunca la reescribe). Un job de verificación (`job_sync_cloud.hash_chain_verifier_loop`) detecta divergencias y genera la alerta `hash_chain_anomaly`.

**RF-SYNC-06 — Deduplicación de filas ya aplicadas**: antes de aplicar una fila `[V]` entrante, el motor verifica si el `uuid` ya existe (`apply_guard.row_already_present`) para no insertar un duplicado cuando el mismo registro llega por dos caminos (por ejemplo, una migración corrida en ambos nodos de forma independiente).

**RF-SYNC-07 — Descubrimiento de sucursales**: cloud mantiene una caché de sucursales activas (`sync/auto_discovery.py::BranchCache`, TTL 300s) construida por consulta directa a `sync_log`/`pairing_tokens`; una sucursal sin heartbeat reciente (> 30 días) dispara `stale_branch_registry`.

> **Nota de verificación pendiente**: la tabla de políticas de conflicto y el detalle de escenarios de `openspec/specs/sync-motor/spec.md` / `sync-catalog/spec.md` (specs vigentes, post fusión del cambio `2026-09-09-sync-overhaul`) se está confirmando en una pasada adicional; si difiere de lo listado arriba, esta sección debe actualizarse antes de considerarse definitiva. Ver también los runbooks operativos ya existentes en [../runbooks/sync/](../runbooks/sync/) (`conflict_rate.md`, `chain_break.md`, `sync_backlog.md`, `orphan_workflow.md`, `dependency_wait.md`, `client_volume.md`, `import_error.md`, `backfill_stalled.md`).

## 4. Ingreso y salida de vehículos

**RF-OPER-01**: `POST /operacion/ingresos` registra el ingreso como evento `[L-E]` insert-only (`repo/event.py::record_event`). Campos de negocio: placa, tipo de vehículo observado, suscripción aplicada (opcional).

**RF-OPER-02**: `GET /operacion/ingresos/{uuid}/estado` deriva el estado (`abierto | cerrado | anulada`) sin almacenarlo — hoy consulta `salidas` directamente como mecanismo transitorio, a la espera de que se monte la vista `V_INGRESO_ESTADO`.

**RF-OPER-03**: al momento de la salida, el sistema valida si la placa tiene una suscripción vigente **en la misma sucursal** (`operacion.py::resolve_active_subscription_for_exit`) — una suscripción de otra sede no es visible ni válida aquí, por diseño de alcance de sync (`broadcast_policy="subscription"`).

**RF-OPER-04 [Roadmap — hueco confirmado en código]**: no existe endpoint para registrar la salida de un vehículo (crear la fila `salidas`). Cita textual del propio repositorio (`api/v1/operacion.py:15-17`): *"the exit ('salida') HTTP endpoint itself is not built by any PR up to and including this one (no `salidas` CRUD route exists yet in this router or elsewhere in `api/v1/`)"*. La corrección de una salida ya registrada (salida errónea) sí está modelada a nivel de datos, vía `anulaciones` (`tipo_anulable = 'salida'`).

## 5. Gestión de usuarios y permisos

**RF-USR-01 — Autorización por permiso, no por rol grueso**: `auth/permissions.py::require_permission(codigo)` verifica en vivo, en cada solicitud, que el actor tenga una fila vigente en `permisos_usuario` unida a `permisos` con el código requerido (por ejemplo, `config_catalogo`, `gestionar_dian`). No se cachea en el JWT — revocar un permiso surte efecto en la siguiente solicitud.

**RF-USR-02 — Modelo de datos de usuarios y permisos** (`[V]`, `modelo_datos_er.mmd`): `usuarios` (rol grueso `admin | operador | supervisor`, credenciales, `cedula` como UK de negocio), `permisos` (catálogo atómico de permisos), `permisos_usuario` (junction: otorgar inserta fila, revocar cierra vigencia — histórico completo preservado), `usuarios_sucursal` (autoriza a un usuario a operar en una sede; el login valida contra esta tabla).

**RF-USR-03**: `GET /api/v1/admin/me` permite a un administrador consultar su propio perfil y sus permisos vigentes.

**RF-USR-04 [Roadmap]**: **no existe** un router de gestión de usuarios (alta de un operador nuevo, cambio de rol, asignación/revocación de permisos vía API). Confirmado por barrido explícito de `api/v1/`: no hay `usuarios.py` ni equivalente. Hoy `usuarios` y `permisos_usuario` solo se leen (`admin_views.py`) o se administran fuera de la API (siembra/migraciones). El patrón de `router_factory.py` usado por los 9 catálogos es directamente aplicable a `usuarios`/`permisos`/`permisos_usuario` si se decide construir este router — es una extensión del mismo mecanismo existente, no un diseño nuevo.

## 6. Facturación interna y pagos

**RF-FACT-01**: `facturas` (`[L-E]`) registra el documento de venta interno con sus totales como hechos legales de la emisión (`subtotal`, `descuento`, `total` — nunca recalculados retroactivamente).

**RF-FACT-02**: `factura_detalle`, `factura_impuestos`, `factura_otros_cobros` (todas `[A]`) copian un *snapshot* del catálogo vigente al momento de emitir (tarifa, porcentaje de impuesto, costo del cargo) — un cambio posterior en el catálogo nunca altera una factura ya emitida.

**RF-FACT-03**: `factura_pagos` (`[A]`) registra uno o varios medios de pago por factura (pago mixto). La numeración/consecutivo de facturación se valida vía `test_consecutivo_assignment.py`.

**RF-FACT-04 — Reverso, nunca eliminación**: un pago erróneo se corrige con una fila `tipo_movimiento = 'reverso'` que referencia `uuid_pago_revertido`; un índice único parcial (`uq_factura_pagos_reverso`) garantiza como máximo un reverso por pago (`DuplicateReversoError`, HTTP 409).

## 7. Facturación electrónica DIAN

**RF-DIAN-01 — Emisión 100% en sucursal**: `factura_electronica` se emite y numera en la sucursal, en línea o sin conexión, sin diferencia de comportamiento. El `consecutivo` se asigna dentro del rango autorizado por `resolucion_facturacion` de esa sede; unicidad por `(uuid_resolucion_facturacion, consecutivo)`.

**RF-DIAN-02 — Envío 100% centralizado en cloud**: cloud es el único punto de salida hacia el proveedor DIAN (`envio_dian`, `dian/cloud_router.py`, excluido del despliegue de sucursal por `PARKOS_DEPLOY` boundary). Cloud valida el `consecutivo` recibido contra el rango autorizado de la resolución antes de reenviarlo.

**RF-DIAN-03 — Reintentos con curva propia**: la curva de reintento DIAN (`dian/backoff.py::DIAN_BACKOFF_SCHEDULE`) es `1 min → 5 min → 15 min → 1 h → 6 h → 24 h` (6 intentos máximo — `DIAN_MAX_RETRIES`), deliberadamente más corta al inicio y con un techo de intentos más estricto que la curva general de sync (`repo/sync_queue.py::BACKOFF_SCHEDULE`, `1 min → 5 min → 30 min → 2 h → 12 h → 24 h`). Al agotar los 6 intentos, genera alerta crítica (`fe_provider_error` / `fe_numbering_exhausted`) en vez de fallar en silencio — justificado porque el documento ya consumió un consecutivo irrepetible en el momento de emitirse.

**RF-DIAN-04 — Serialización UBL 2.1**: `dian/cloud/ubl_serializer.py::serialize` construye el XML UBL 2.1 a partir de la fila `factura_electronica`. **[Por definir]**: la serialización actual emite datos mínimos válidos contra el XSD (proveedor, cliente y totales con valores de relleno) — la resolución de los datos reales de `empresa`/`clientes` y de las líneas de `factura_detalle` está marcada en el propio código como trabajo de una iteración posterior ("PR12" en los comentarios del archivo).

**RF-DIAN-05 — Revocación con cadena de hash propia**: `revocacion_factura` (`[A]`) mantiene su propia cadena SHA-256 por `uuid_sucursal`, independiente de la de `log_transaccional`. Se alimenta del webhook `POST /api/v1/revocacion-factura-webhook`.

**RF-DIAN-06 — Bandeja de validación en cloud**: `validacion_evento` (`[L-W]`, cloud-only) registra la validación administrativa de cada evento recibido de una sucursal, con hash del payload recibido para verificar integridad contra lo emitido originalmente.

## 8. Workflows operativos (anulaciones, reclamos, alertas, reimpresión)

Los cuatro workflows comparten el mismo patrón `[L-W]`: cada transición es una fila nueva enlazada a la anterior por una FK propia (`uuid_*_padre`), nunca un `UPDATE` sobre la fila previa.

**RF-WF-01 — Anulaciones**: cadena `solicitada → aprobada → ejecutada` sobre un ingreso o una salida (`tipo_anulable`). Solo la fila `ejecutada` tiene efecto sobre el estado derivado del documento afectado.

**RF-WF-02 — Reclamos**: referencia polimórfica (`tipo_reclamable`: `ingreso | salida | factura | subscripcion`, sin FK física) con cadena `abierto → en_revision → resuelto | rechazado`.

**RF-WF-03 — Reimpresión de ticket**: cobra el costo de servicio vigente al momento de reimprimir (snapshot); admite su propia anulación (`uuid_reimpresion_padre`). El documento reimpreso nunca depende de un round-trip a cloud para completarse.

**RF-WF-04 — Alertas**: se generan automáticamente (diferencia de arqueo, caja baja, falla de sync, sucursal offline) desde procesos internos del backend (jobs de sync, lógica de arqueo) que escriben directamente vía `repo/workflow.py`, sin pasar por un endpoint HTTP. La generación **manual** de una alerta (ej. un operador reportando fraude desde la interfaz) está prevista en el modelo (`tipo_alerta = 'manual'`) pero **no tiene endpoint de creación** hoy — ver RF-WF-06. Catálogo real de tipos (`alert_types`, sembrado de forma idempotente en cloud y en cada sucursal): `diferencia_arqueo`, `caja_baja`, `fraude`, `manual`, `sync_failure`, `branch_offline`, más `hash_chain_anomaly` y `stale_branch_registry` (generadas por los jobs de sync, no por el catálogo sembrado).

**RF-WF-05 — Bandeja de validación de eventos (cloud)**: ver RF-DIAN-06 — es un `[L-W]` general, no exclusivo de DIAN, aunque su primer uso documentado es sobre eventos entrantes de sucursal.

**RF-WF-06 [Roadmap — hueco confirmado en código]**: los 4 recursos anteriores se montan en `api/v1/workflows.py:106` con `write_enabled=False` — **hoy son de solo lectura vía API**. No se encontró en ningún módulo de `backend/packages/parkos_core/src/parkos_core/api/` un endpoint de creación o transición (`/solicitar`, `/aprobar`, `/ejecutar`, `/descartar`, `/rechazar`) para anulaciones, reclamos, alerta o reimpresión-ticket; el propio docstring del archivo lo declara explícitamente ("PR6 only exposes reads... Custom transition endpoints ship in PR7"). Esto no afecta la emisión **automática** de alertas por el motor de sync (RF-WF-04), que sí es real y no depende de un endpoint interactivo.

## 9. Caja y arqueo

**RF-CAJA-01**: `sesion` (`[L-S]`) representa el turno de caja de un operador (`POST /caja-sesion/sesiones` abre, `PUT /caja-sesion/sesion/{uuid}/cerrar` cierra). El cierre exige, en la misma transacción, una fila en `log_transaccional` (trigger `fn_sesion_ls_session_guard`).

**RF-CAJA-02**: `caja` (`[A]`) almacena fotos periódicas del efectivo/datáfono por sede; su evolución es la serie temporal de filas, sin agregación previa.

**RF-CAJA-03**: `arqueo` (`[A]`) compara lo esperado contra lo físicamente contado, clasificado por `tipo_arqueo` (cierre de turno, auditoría sorpresiva, cierre de sesión). Superar la tolerancia configurada dispara una `alerta`. Una corrección se modela como un **arqueo nuevo** del mismo turno que referencia al anterior — nunca como `UPDATE`.

**RF-CAJA-04 [Roadmap]**: `caja` y `arqueo` son de solo lectura por API HTTP hoy (`api/v1/caja.py`, `write_enabled=False`); su escritura real ocurre a través del motor de sync (aplicada como evento `append_event`), no por un endpoint interactivo directo. El propio comentario del archivo señala que los endpoints de escritura personalizados quedaron pendientes de una iteración posterior.

## 10. Panel administrativo y reportes

**RF-ADMIN-01**: `GET /api/v1/sucursales` lista las sucursales visibles para el administrador autenticado.

**RF-ADMIN-02**: `GET /api/v1/admin/sucursales/{uuid}/dashboard` agrega indicadores de una sucursal (requiere `X-Sucursal-Context` validado contra `sucursales_permitidas` del token).

**RF-ADMIN-03 [Por definir]**: no se verificó en esta pasada un módulo de reportes exportables (PDF/Excel) más allá del dashboard agregado; si existe, documentarlo en [../03-desarrollo/api-reference.md](../03-desarrollo/api-reference.md).

---

## Resumen de huecos detectados en esta pasada

| # | Hueco | Tratado como |
|---|---|---|
| 1 | Registrar salida de vehículo (`POST` sobre `salidas`) | Roadmap — confirmado textualmente en el código (§4) |
| 2 | Escritura HTTP directa de `caja`/`arqueo` | Roadmap — confirmado en código (§9) |
| 3 | Alta/edición de usuarios y asignación de roles vía API | Roadmap — confirmado por ausencia de router (§5) |
| 4 | Bloqueo de cuenta por intentos fallidos de login | Roadmap — función no-op documentada en código (ver [historias-usuario.md](historias-usuario.md)) |
| 5 | Datos reales de proveedor/cliente/líneas en la serialización UBL DIAN | Por definir — el propio código marca placeholders (§7, RF-DIAN-04) |
| 6 | Módulo de reportes exportables | Por definir — no verificado, no descartado (§10) |
| 7 | Política exacta de conflictos de sync contra el spec vigente (`sync-motor/spec.md`) | Marcado explícitamente como pendiente de confirmación (§3) — se corrige en cuanto se valide contra el spec |
| 8 | Transiciones de workflow (aprobar/ejecutar/descartar/rechazar) sin endpoint HTTP dedicado | Roadmap — confirmado por `write_enabled=False` en `api/v1/workflows.py:106` (§8, RF-WF-06) |
