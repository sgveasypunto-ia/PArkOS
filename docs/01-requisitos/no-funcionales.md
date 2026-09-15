# Requisitos No Funcionales — easypunto_parkos

[Índice general](../README.md) · [Historias de usuario](historias-usuario.md) · [Requisitos funcionales](funcionales.md) · [Decisiones técnicas](../02-arquitectura/decisiones-tecnicas.md) · [Seguridad](../02-arquitectura/seguridad.md) · [Modelo de datos](../02-arquitectura/modelo-datos.md)

> Requisitos verificados contra código real (migraciones, modelos ORM, configuración de despliegue). Donde no se encontró un valor objetivo explícito (ej. un SLA de disponibilidad en porcentaje), se marca **[Por definir]** en vez de inventarlo.

## 1. Compliance y retención (DIAN, Colombia)

**RNF-COMP-01 — Retención mínima de 5 años**: toda tabla sujeta a fiscalización DIAN carga `fecha_retencion_hasta` (columna `RetentionMixin`, `models/base.py:119-130`). Confirmado en `factura_electronica`, `revocacion_factura`, `factura_detalle`, `factura_impuestos`, `factura_otros_cobros`, `factura_pagos` y `log_transaccional` (`modelo_datos_er.mmd`). El helper `repo/append_only.py::append_event` fija `NOW() + INTERVAL '5 years'` al insertar una fila DIAN; tablas `[A]` no-DIAN dejan la columna en `NULL` por defecto.

**RNF-COMP-02 — Retención operacional más corta para tablas no fiscales**: `salidas`, `caja`, `arqueo` y `sync_conflict`/`sync_log` documentan en el propio `.mmd` una retención operacional menor (ej. 1-2 años) que la fiscal de 5 años — ambas usan la misma columna `fecha_retencion_hasta`, pero con una política de archivado distinta. **[Por definir]**: el valor exacto en años de cada retención operacional no está codificado como constante verificable (a diferencia de la DIAN, que sí lo está); hoy es solo un comentario de diseño en el `.mmd`.

**RNF-COMP-03 — Borrado lógico exclusivo, sin excepción**: no existe una sentencia `DELETE` de negocio en ningún nivel (API, ORM, migraciones, scripts de siembra). Verificado estructuralmente por `backend/tests/static/test_no_delete_routes.py` (análisis AST + OpenAPI) y por el propio contrato `AppendOnlyBase` (`models/base.py:177-193`). Única excepción documentada y deliberada: `sync_queue` conserva el privilegio `DELETE` a nivel de rol de base de datos para un futuro *purge worker* aún no implementado (`test_revokes_active.py::test_sync_queue_has_update_delete`) — ver RNF-SEG-03.

**RNF-COMP-04 — Cadena probatoria SHA-256**: ver § 6 Auditabilidad.

**RNF-COMP-05 — Contrato de API restringido a Consulta/Inserción/Actualización**: ver [funcionales.md § 0](funcionales.md#0-contrato-transversal-consulta--inserción--actualización).

## 2. SLA (nivel de servicio)

**RNF-SLA-01 [Por definir]**: no se encontró en el repositorio un objetivo explícito de disponibilidad (ej. "99.9% mensual") ni de tiempo de respuesta máximo por endpoint. Los únicos valores temporales verificados son operativos, no contractuales:

| Parámetro | Valor real | Fuente |
|---|---|---|
| Reintento DIAN | `1 min → 5 min → 15 min → 1 h → 6 h → 24 h`, máx. 6 intentos | `dian/backoff.py::DIAN_BACKOFF_SCHEDULE` |
| Reintento de sync general | `1 min → 5 min → 30 min → 2 h → 12 h → 24 h` | `repo/sync_queue.py::BACKOFF_SCHEDULE` (citado en `dian/backoff.py`) |
| Backoff de worker ante error 5xx | `30s → 60s → 300s` | `jobs/runner.py::BACKOFF_5XX` |
| Backoff de worker ante error 4xx | `60s → 300s → 1800s → 7200s → 43200s → 86400s` | `jobs/runner.py::BACKOFF_4XX` |
| TTL del buffer de dependencias de sync | 24 h | `sync_queue_lw_buffer.expires_at` (`.mmd`) |
| Vigencia del token de pairing | 24 h (configurable hasta 168 h por el endpoint admin) | `repo/pairing.py::DEFAULT_TTL_HOURS` |
| Ventana de rotación de JWT (ambas claves vigentes) | `JWT_OVERLAP_HOURS = 24` | `AGENTS.md` § JWT |
| Frescura de la caché de sucursales activas | 300 s | `sync/auto_discovery.py::BranchCache` |
| Umbral de sucursal "estancada" | último heartbeat > 30 días | `AGENTS.md` (Risk Register) |

**RNF-SLA-02**: el health check de cada worker de sync se expone en `:9999/healthz`; Docker reinicia el contenedor tras 3 fallos consecutivos de health check (`AGENTS.md` § Risk Register).

## 3. Seguridad

### 3.1 Autenticación — JWT de tres emisores

**RNF-SEG-01**: tres conjuntos de claves, uno por emisor (`admin-`, `operador-`, `sync-agent-`), mutuamente excluyentes — no hay jerarquía implícita entre ellos (`auth/jwt_issuer_guard.py:1-9`). El prefijo `kid` identifica el emisor; un token cruzado se rechaza por `iss` + `aud`. Toda falla de validación de JWT responde `401` de forma controlada (nunca `500` sin manejar) — corregido explícitamente en `fix/close-gaps` (`AGENTS.md`, "Closed risks": `jwt_issuer_guard.verify_jwt` fue corregido porque un `JWTValidationError` se filtraba como 500).

**RNF-SEG-02**: rotación con solape — ambas claves (antigua y nueva) permanecen vigentes en el JWKS durante `JWT_OVERLAP_HOURS = 24` para no invalidar tokens en tránsito.

### 3.2 Autorización — de rol grueso a permiso fino y a alcance de sucursal

**RNF-SEG-03**: tres capas independientes, todas verificadas por request (nunca cacheadas en el token): emisor (`requires_issuer`), permiso (`require_permission`, consulta viva a `permisos_usuario`) y alcance de sucursal (`TenantContext`, encabezado `X-Sucursal-Context` validado contra `sucursales_permitidas`).

### 3.3 Privilegios de base de datos — hallazgo reciente crítico

**RNF-SEG-04 — Principio de mínimo privilegio real (migración `0021_least_privilege_and_immutability_contract`, del mismo día de esta documentación)**: hasta esta migración, la aplicación se conectaba con el **único rol con `LOGIN` existente**, que además era el superusuario de PostgreSQL (`POSTGRES_USER=parkos`). El rol de aplicación de menor privilegio (`rol_app`, creado desde la migración inicial) era `NOLOGIN` y nunca fue asumido por ninguna conexión real — es decir, **todo `REVOKE` escrito hasta ese momento era inerte**, porque un superusuario ignora cualquier `GRANT`/`REVOKE` por definición. Corregido así:

- Se crea `parkos_app` (`LOGIN INHERIT IN ROLE rol_app`) como la identidad real de conexión de la aplicación (`docker-compose.cloud.yml` y `docker-compose.local.yml` actualizados en el mismo cambio).
- Se cierran los privilegios por clase de tabla, columna por columna donde corresponde:

| Grupo de tablas | `UPDATE` permitido a `rol_app` | `DELETE` |
|---|---|---|
| 8 tablas `[L-W]`/`[L-E]` sin actualización legítima (`alerta`, `anulaciones`, `reclamos`, `reimpresion_ticket`, `validacion_evento`, `facturas`, `ingreso`, `factura_electronica`) | Ninguna columna | Revocado |
| `envio_dian` (única excepción con actualización legítima a mitad de ciclo de vida) | Solo columna `payload` | Revocado |
| 26 tablas `[V]` | Solo `vigente_hasta`, `estado` | Revocado |
| `login` | Solo `timestamp_cierre`, `estado` | Revocado |
| `sesion` | Solo `timestamp_cierre`, `uuid_usuario_cierre`, `estado` | Revocado |
| `alert_types` (catálogo sembrado) | Ninguna (además `INSERT` revocado — solo `SELECT`) | Revocado |
| `sync_queue` | Sin cambios — **excepción intencional y documentada**: conserva `UPDATE`/`DELETE` para un *purge worker* futuro | Sin cambios |

- **Asimetría residual, declarada explícitamente en la propia migración**: para las 11 tablas `[A]` que ya tenían un trigger `BEFORE UPDATE OR DELETE` por tabla desde la migración inicial (`fn_<tabla>_inmutable()`), la protección bloquea incluso al superusuario. Para las 36 tablas que esta migración restringe por primera vez, la protección es solo `GRANT`/`REVOKE` — `rol_app` no puede violar el contrato, pero una sesión conectada directamente como superusuario técnicamente sí podría. Cerrar esa brecha con un trigger equivalente queda como trabajo de seguimiento explícito, no resuelto en esta migración.
- **Hallazgo residual declarado**: la contraseña de conexión de `parkos_app` tiene un valor de desarrollo por defecto (configurable por variable de entorno); un despliegue real **debe** inyectarla desde gestión de secretos — señalado como pendiente en el propio docstring de la migración, no resuelto por ella.

**RNF-SEG-05 — Inmutabilidad reforzada en 3 capas (defensa en profundidad)**: API (sin endpoint de `DELETE`), ORM (helpers de "cerrar + insertar", sin `hard delete` sobre `[V]`/`[L]`) y base de datos (`REVOKE DELETE` + trigger `BEFORE UPDATE OR DELETE` en las 11 tablas `[A]` originales). Verificado end-to-end por `openspec/scripts/check_schema_match.py` (según `AGENTS.md`, confirma 100% de coincidencia entre el esquema real y `modelo_datos_er.mmd`: tablas, columnas, UKs, FKs, `REVOKE` en las tablas `[A]`, triggers `_inmutable` y los 8 padres `pg_partman`).

**RNF-SEG-06 — Protección de secretos en tránsito**: el token de pairing en texto plano se limpia explícitamente del entorno de proceso tras usarse (`os.environ.pop("PARKOS_PAIRING_TOKEN", None)`, `cli/pair.py`); solo su hash SHA-256 se persiste. TLS 1.3 exigido entre sucursal y cloud (`PARKOS_TLS=required`, terminación en `nginx`).

**RNF-SEG-07 — Idempotencia de escritura**: las escrituras que lo requieren pasan por un middleware de `Idempotency-Key` (`IdempotencyKeyMiddleware`, tabla `idempotency_keys`) para que un reintento de red por timeout no duplique un ingreso, un pago o un envío a DIAN.

**RNF-SEG-08 [Hallazgo — pendiente para producción]**: `CORSMiddleware` se configura con `allow_origins=["*"]` y `allow_credentials=True` en **ambos** servicios (`backend/packages/api_admin/src/api_admin_main/app.py:65-69`, `backend/packages/api_sucursal/src/api_sucursal_main/app.py:69-73`). El propio comentario del código lo marca como una decisión de desarrollo, no definitiva: *"CORS — dev: allow all origins. Tighten in PR7 with the production allowlist."* Combinar origen comodín con credenciales habilitadas es una práctica de riesgo reconocida; debe resolverse con una lista blanca de orígenes antes de un despliegue de producción.

## 4. Rendimiento y escalabilidad

**RNF-PERF-01 — Particionado mensual (`pg_partman`) en las tablas de alto volumen**: confirmado por `RANGE (fecha_retencion_hasta)` en la migración inicial (`0001_initial_schema.py`) y en cada modelo ORM (`postgresql_partition_by`), exactamente en las 8 tablas señaladas:

| Tabla | Clase | Clave de partición |
|---|---|---|
| `factura_detalle` | `[A]` | `fecha_retencion_hasta` |
| `factura_pagos` | `[A]` | `fecha_retencion_hasta` |
| `log_transaccional` | `[A]` | `fecha_retencion_hasta` |
| `sync_log` | `[A]` | `fecha_retencion_hasta` |
| `sync_queue` | `[A]` | `fecha_retencion_hasta` |
| `caja` | `[A]` | `fecha_retencion_hasta` |
| `arqueo` | `[A]` | `fecha_retencion_hasta` |
| `salidas` | `[A]` | `fecha_retencion_hasta` |

Nota adicional (no pedida explícitamente, pero real): otras 3 tablas también están particionadas por el mismo mecanismo — `pairing_tokens` y `revoked_sync_jwts` por `fecha_retencion_hasta`, y `sync_queue_lw_buffer` por `buffered_at` (particionado diario, no mensual). El privilegio de `rol_app` sobre una tabla particionada se hereda automáticamente a todas sus particiones desde PostgreSQL 11 (nota explícita de la migración `0021`).

**RNF-PERF-02 — Límites de tasa por endpoint de sync** (protegen al cloud de saturación por sucursales): `push` 60/min, `pull` 120/min (compartido con `events`), `heartbeat` 10/min, `rotate-jwt` 1/min, emisión de pairing-token 5/hora por administrador. Fuente: `api/v1/sync_router.py`, `api/rate_limit_pairing.py`.

**RNF-PERF-03 — `lock_timeout` corto en migraciones**: toda migración que toca privilegios usa `SET lock_timeout = '5s'` antes de ejecutar `GRANT`/`REVOKE` (migración `0021`), para no dejar una migración colgada esperando un lock en producción.

**RNF-PERF-04 [Por definir]**: no se verificaron en esta pasada objetivos numéricos de rendimiento (throughput esperado de ingresos/hora por sucursal, latencia máxima de un ciclo de sync). El único límite de tamaño confirmado es el de documentos administrativos en base64 (1 MB, `test_documentos_b64_cap.py`).

## 5. Disponibilidad y continuidad — offline-first

**RNF-DISP-01 — La sucursal es autónoma**: cada sucursal tiene su propio PostgreSQL local y debe seguir operando sin conexión a cloud. Confirmado explícitamente para el flujo más crítico: *"the branch emits and numbers locally, online or offline, with no behavioural difference"* (`AGENTS.md` § DIAN) — la emisión de factura electrónica y su numeración DIAN no dependen de conectividad; solo el envío al proveedor DIAN (exclusivo de cloud) queda pendiente hasta que la sucursal vuelva a sincronizar.

**RNF-DISP-02 — La reimpresión nunca depende de un round-trip a cloud**: el documento es final en el momento de su emisión; lo único potencialmente pendiente es el acuse de DIAN, que es un indicador de estado sobre el documento, no una condición para reimprimirlo (`AGENTS.md` § Frontend).

**RNF-DISP-03 — Recuperación ante caída de un worker de sync**: `WorkerRunner` expone health check en `:9999/healthz`; tras 3 fallos consecutivos, Docker reinicia el contenedor. El worker también sale con código `1` ante una excepción no manejada, delegando el reinicio al orquestador de contenedores.

**RNF-DISP-04 [Roadmap]**: alta disponibilidad de `job_sync_cloud` — hoy corre con `deploy.replicas: 1` (verificado por `docker compose config`); HA con locks asesores de PostgreSQL por `uuid_sucursal` está diferida a una versión futura (`AGENTS.md`, Risk Register).

**RNF-DISP-05 [Roadmap]**: registro externo de sucursales (`PARKOS_REGISTRY_URL`) diferido a una versión futura; hoy el descubrimiento es 100% por consulta a la base de datos (`sync_log` + `pairing_tokens`).

## 6. Auditabilidad e integridad

**RNF-AUD-01 — Cadena de hash SHA-256, dos instancias independientes**: `log_transaccional` (bitácora general) y `revocacion_factura` (evidencia DIAN) mantienen cada una su propia cadena `hash_anterior → hash_actual`, calculada por `uuid_sucursal` (`repo/hash_chain.py::append`). El cómputo ocurre en Python y se re-verifica en un trigger de base de datos al hacer commit (`fn_extend_hash_chain()`), que aborta con `HASH_CHAIN_MISMATCH` si diverge.

**RNF-AUD-02 — Bootstrap de cadena (fila génesis)**: la primera fila de una sucursal nunca vista antes de bootstrapea automáticamente en vez de fallar por falta de `hash_anterior` (`repo/hash_chain.py::_ensure_genesis_row`) — evitó, según el propio `AGENTS.md`, un primer intento de login fallando por "no genesis row" cuando la inserción se hacía sin pasar por este helper.

**RNF-AUD-03 — Verificación continua, no solo al escribir**: `job_sync_cloud.hash_chain_verifier_loop` recorre la cadena periódicamente (`PARKOS_SYNC_VERIFY_INTERVAL_S`, por defecto 3600 s) y genera `alerta tipo_alerta='hash_chain_anomaly'` ante una ruptura silenciosa — complementa, no reemplaza, la verificación transaccional del punto anterior. Procedimiento operativo asociado ya documentado: [../runbooks/sync/chain_break.md](../runbooks/sync/chain_break.md).

**RNF-AUD-04 — Todo cambio deja rastro**: cada fila `[V]`/`[L]`/`[A]` carga como mínimo `created_at` + `created_by` (`AuditMixin`, obligatorio, `AGENTS.md` §1); `created_by` deliberadamente **no** es una FK a `usuarios`, para que el rastro de auditoría sobreviva aunque el usuario que lo originó sea versionado/cerrado después.

**RNF-AUD-05 — Modelo bi-temporal**: cada fila `[V]`/`[L]` distingue tiempo de validez (`vigente_desde`/`vigente_hasta` — cuándo el hecho fue cierto en el negocio) de tiempo de transacción (`created_at` — cuándo la base de datos lo registró), permitiendo reconstruir el estado del sistema en cualquier punto del pasado sin ambigüedad.

## 7. Accesibilidad (frontend)

**RNF-ACC-01**: `apps/web_admin` corre `@axe-core/playwright` como gate de CI para WCAG 2.1 AA (`AGENTS.md` § Frontend / DevOps) — no se verificó en esta pasada el resultado actual de esa suite ni su cobertura de pantallas; solo se confirmó que el gate existe en la configuración documentada.

**RNF-ACC-02 [Por definir]**: `web_sucursal` (frontend de sucursal) todavía no existe como código — el requisito de accesibilidad para esa superficie queda abierto hasta que se implemente (ver [historias-usuario.md § Roadmap](historias-usuario.md#roadmap--historias-no-implementadas)).

## 8. Observabilidad

**RNF-OBS-01 — Logging estructurado**: `structlog` en todo el backend (`AGENTS.md` § Tech Stack); los workers registran `worker_started`, `cycle_error`, `worker_fatal`, `env_validation_failed`, etc. como eventos estructurados, no texto libre.

**RNF-OBS-02 — Diagnóstico de arranque**: `parkos-core doctor` (`parkos_core/cli/doctor.py`) reporta en un solo comando la presencia de variables de entorno, alcanzabilidad de la base de datos y permisos de escritura del path del token de sync — pensado para diagnosticar un despliegue de sucursal nuevo sin acceso directo a logs del contenedor.

**RNF-OBS-03 — Métricas de sync por ciclo**: `sync_log` (`[A]`) registra, por cada ciclo de sincronización de cada sucursal: operaciones enviadas, exitosas, fallidas, conflictos y duración en milisegundos — es la fuente de las alertas `sync_failure` y `branch_offline`, y de los runbooks ya existentes en [../runbooks/sync/](../runbooks/sync/) (`sync_backlog.md`, `client_volume.md`, `conflict_rate.md`).

**RNF-OBS-04 — Métricas Prometheus, definidas pero sin endpoint de scrape expuesto**: `sync/observability/metrics.py` define y actualiza en tiempo real un `Counter`/`Gauge` real de `prometheus_client` (`sync_apply_total`, `sync_dependency_wait`, `catalog_rows_total`, `sync_deferred_total`, `catalog_backfill_complete`), con la garantía explícita, verificada por test (`test_observability_metrics.py`), de que ninguna etiqueta expone contenido de fila (solo identificadores estructurales: tabla, estado, `uuid_sucursal`, clase de auditoría). **[Roadmap]**: el propio módulo documenta que exponer un endpoint HTTP `/metrics` para que Prometheus las recolecte es "a deploy-pipeline concern out of this PR's scope" — las métricas se calculan, pero nada las sirve todavía por HTTP.

---

## Resumen de huecos y "por definir"

| # | Ítem | Sección |
|---|---|---|
| 1 | SLA numérico de disponibilidad y de tiempo de respuesta | § 2 |
| 2 | Valor exacto (en años) de las retenciones operacionales no-DIAN | § 1 |
| 3 | Trigger equivalente al de las 11 tablas `[A]` originales para las 36 tablas recién restringidas (asimetría ante un superusuario) | § 3.3 |
| 4 | Gestión de secretos en producción para la contraseña de `parkos_app` | § 3.3 |
| 5 | Objetivos numéricos de throughput/latencia más allá de los límites de tasa de sync | § 4 |
| 6 | Resultado y cobertura reales del gate WCAG 2.1 AA | § 7 |
| 7 | Accesibilidad de `web_sucursal` (no existe aún) | § 7 |
| 8 | Lista blanca de orígenes CORS para producción (hoy `allow_origins=["*"]` + `allow_credentials=True` en ambos servicios) | § 3.3 |
| 9 | Endpoint HTTP `/metrics` para exponer las métricas Prometheus ya definidas | § 8 |
