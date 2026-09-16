# Referencia de API

Endpoints reales verificados con `codegraph_explore` contra el código fuente de `backend/packages/parkos_core/src/parkos_core/api/`. Todos los routers viven en el paquete compartido `parkos_core` y se montan bajo `/api/v1` a través de la fábrica `parkos_core.api.app_factory:create_app`, que carga `api_admin_main.app` o `api_sucursal_main.app` según la variable de entorno `PARKOS_DEPLOY` (`cloud` | `branch`). El router DIAN (`parkos_core.dian.cloud_router`) es exclusivo de cloud: si `PARKOS_DEPLOY=branch`, el módulo lanza `ImportError` al cargarse — está físicamente ausente en la imagen de sucursal (frontera REQ-X3).

## Patrón CRUD genérico (`router_factory.make_router`)

Catálogos, configuración y empresa reutilizan la misma fábrica. Salvo excepción indicada, cada recurso `{prefix}` expone:

| Método | Ruta | Comportamiento |
|---|---|---|
| GET | `/{prefix}` | Lista paginada por cursor (`cursor`, `limit` 1–200, default 50); en tablas `[V]` solo devuelve filas vigentes (`vigente_hasta IS NULL`) |
| GET | `/{prefix}/{uuid}` | Versión vigente de un registro |
| GET | `/{prefix}/{uuid}/history` | Histórico completo de versiones (solo si la tabla es bi-temporal) |
| POST | `/{prefix}` | Inserta una fila nueva (201) |
| PUT | `/{prefix}/{uuid}` | Actualización bi-temporal: cierra la fila vigente e inserta la nueva |

Nunca hay `DELETE` (ver `estandares.md` — contrato Consulta/Inserción/Actualización).

## Auth — `/api/v1/auth`

| Método | Ruta | Propósito |
|---|---|---|
| POST | `/api/v1/auth/login` | Autentica `email` + `password`, emite par de JWT (access 1h / refresh 7d) |
| POST | `/api/v1/auth/refresh` | Canjea un refresh token vigente por un nuevo access token |
| POST | `/api/v1/auth/logout` | Cierra la fila `login` activa del usuario autenticado |

## Catálogos — `/api/v1/catalogos` (9 recursos, todos `[V]`)

Issuer `admin-,operador-` (admin escribe, operador solo lee vía el patrón CRUD genérico), permiso `config_catalogo`.

| Recurso | Contenido |
|---|---|
| `tipo-persona` | natural \| juridica |
| `tipos-vehiculo` | carro \| moto \| bicicleta |
| `tipo-subscripciones` | planes comerciales |
| `tipo-tarifa` | hora \| fraccion \| plena \| nocturna |
| `tipo-sucursal` | modelo operativo de sucursal (incluye `caracteristicas` JSONB) |
| `tipo-arqueo` | cierre_turno \| auditoria \| cierre_sesion |
| `impuestos` | catálogo de impuestos (IVA, INC) |
| `otros-cobros` | cobros adicionales facturables |
| `costos-servicios` | servicios internos (reimpresión de ticket, etc.) |

## Configuración — `/api/v1/configuracion`

| Método | Ruta | Propósito |
|---|---|---|
| GET/POST/PUT | `/api/v1/configuracion/configuracion-tolerancias` | CRUD genérico, permiso `config_tolerancias` |
| GET/POST/PUT | `/api/v1/configuracion/configuracion-seguridad` | CRUD genérico, permiso `config_seguridad` |
| GET | `/api/v1/configuracion/configuracion-seguridad/efectiva` | Resuelve el valor efectivo: override por sucursal (`uuid_sucursal`) o default global si no existe override; 404 si no hay ninguno |

## Empresa — `/api/v1/empresa`

| Recurso | Issuer | Permiso |
|---|---|---|
| `empresa` | admin-,operador- | `config_empresa` |
| `sucursal` | admin-,operador- | `config_sucursal` |
| `documentos` | admin-,operador- | `admin_documentos` |
| `resolucion-facturacion` | **admin- únicamente** (raíz DIAN, cloud-only) | `admin_resolucion_facturacion` |
| `tarifas-sucursal` | admin-,operador- | `config_tarifas` |
| `cantidad-vehiculos-sucursal` | admin-,operador- | `config_cupos` |

Todos siguen el patrón CRUD genérico bajo `/api/v1/empresa/{recurso}`.

## Sucursal — `/api/v1/sucursal`

| Método | Ruta | Propósito |
|---|---|---|
| GET | `/api/v1/sucursal/{uuid}/pairing-token` | Emite un token de emparejamiento de un solo uso (JWT, 24h). Solo issuer `admin-`, solo cloud |

El operador de sucursal canjea ese token por un JWT `sync-agent-` de larga duración en `POST /api/v1/sync/pair`.

## Caja y arqueo — `/api/v1/caja` (solo lectura)

| Recurso | Issuer | Permiso | Escritura |
|---|---|---|---|
| `caja` | operador-,admin- | `emitir_factura` | deshabilitada (`write_enabled=False`) |
| `arqueo` | operador-,admin- | `emitir_factura` | deshabilitada |

Ambas son tablas `[A]` (append-only). Solo exponen `GET /api/v1/caja/{recurso}`, `GET /api/v1/caja/{recurso}/{uuid}` y su historial; las escrituras se hacen por endpoints dedicados que llaman a `repo.append_only.append_event` (fuera de esta pasada de verificación).

## Sync — `/api/v1/sync` (protocolo sucursal ↔ nube)

Todos requieren JWT `sync-agent-` salvo `hello`.

| Método | Ruta | Propósito |
|---|---|---|
| GET | `/api/v1/sync/hello` | Handshake de protocolo dual, sin autenticación (la sucursal aún no decidió qué applier usar); responde versión de protocolo + revisión de catálogo |
| POST | `/api/v1/sync/pair` | Canjea un pairing-token por un JWT `sync-agent-` de larga duración (201) |
| POST | `/api/v1/sync/push` | Sucursal → nube: empuja un lote de filas (applier legado); 207 Multi-Status por fila; rate-limit 60/min; idempotente vía header `X-Request-Id` |
| POST | `/api/v1/sync/pull` | Sucursal ← nube: hala filas nuevas a partir de `since_seq`; rate-limit 120/min |
| POST | `/api/v1/sync/events` | Empuje catalog-driven (motor nuevo), alternativa a `/push` según auto-detección de protocolo |
| POST | `/api/v1/sync/heartbeat` | Mantiene viva la señal de la sucursal en la nube (o viceversa); body `{"state": {...}}`; rate-limit 10/min; 204 |
| POST | `/api/v1/sync/rotate-jwt` | Rota el JWT `sync-agent-` vigente; devuelve el nuevo JWT + `grace_until` para el anterior; rate-limit 1/min |

## Admin — `/api/v1/admin` (issuer `admin-` únicamente)

| Método | Ruta | Propósito |
|---|---|---|
| GET | `/api/v1/admin/sucursales` | Lista de sucursales con paginación por cursor (vista administrativa, filtrada por `sucursales_permitidas` del JWT) |
| GET | `/api/v1/admin/sucursales/{uuid}/dashboard` | KPIs de una sucursal: conteo/monto de ingresos, facturas emitidas y electrónicas, alertas abiertas, salud de sync (`last_sync_at`, `lag_seconds`, `queue_depth`) |

`admin_views.py` define también un schema `AdminMeResponse`; no se pudo confirmar en esta pasada si existe un endpoint `GET /api/v1/admin/me` activo — verificar contra Swagger (`/docs`) antes de darlo por definitivo.

## Operación — `/api/v1/operacion`

Router confirmado (`prefix="/operacion"`, `tag="operacion"`, issuer `operador-,admin-`) para el flujo de ingreso de vehículos (usa el schema `IngresoRead`, tabla `[L-E]` `ingreso`). Las rutas HTTP exactas del archivo no se lograron extraer completas en esta pasada de exploración — **verificar contra `/docs` antes de tratarlas como definitivas.**

## DIAN — sin prefijo propio (cloud-only)

`parkos_core.dian.cloud_router` (montado directamente bajo `/api/v1`, sin prefijo adicional para no duplicar `/api/v1/api/v1/...`). Issuer `admin-,operador-`. Por sus imports confirmados, orquesta el despacho de facturación electrónica y revocaciones hacia el proveedor DIAN (Factus): usa `dispatch_factura_electronica`, `dispatch_revocacion` y `next_consecutivo`, sobre los modelos `FacturaElectronica` (`[L-E]`), `RevocacionFactura` (`[A]`) y `EnvioDian`/`ValidacionEvento` (`[L-W]`). **No disponible en absoluto en despliegues de sucursal.** Rutas HTTP exactas no confirmadas en esta pasada — verificar contra `/docs` en el despliegue cloud.

## Salud e infraestructura

| Método | Ruta | Propósito |
|---|---|---|
| GET | `/health` (fuera de `/api/v1`) | Responde `{"status": "ok", "service": "parkos-api-sucursal", "deploy": "branch"}` (confirmado en `api_sucursal_main/app.py`; se asume paridad estructural en `api_admin_main/app.py`, no verificado línea por línea) |
| GET | `/openapi.json` | Usado como healthcheck por Docker Compose (`docker-compose.*.yml`) |
| GET | `/docs` | Swagger UI (automático de FastAPI, sin personalizar en el código revisado) |

## Siguiente paso

- Instalación y ejecución local → [`setup.md`](./setup.md)
- Estilo de código y contrato C/Q/U → [`estandares.md`](./estandares.md)
- Modelo de datos completo (49 tablas) → `../02-arquitectura/modelo-datos.md`
