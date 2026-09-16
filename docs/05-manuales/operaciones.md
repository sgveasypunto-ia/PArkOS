# Manual de operaciones — DevOps / SRE

> Guía real de despliegue, configuración y observabilidad de los nodos Docker Compose de easypunto_parkos, verificada contra `infra/deploy/`, `infra/docker/`, `infra/scripts/`, `infra/grafana/alerts/sync.yaml` y el validador de entorno del backend (`runtime/env.py`).

## Topología de despliegue

Tres archivos Compose en `infra/deploy/`, cada uno para un rol distinto:

| Archivo | Rol | Cuándo usarlo |
|---|---|---|
| `docker-compose.cloud.yml` | Nodo cloud (central) | Desplegar el admin central: DB, `api-admin`, `job-sync-cloud`. |
| `docker-compose.branch.yml` | Nodo de sucursal | Desplegar una sucursal real, apuntando a un cloud ya desplegado. |
| `docker-compose.local.yml` | Combinado local | Desarrollo: levanta una sucursal sobre la red del cloud ya corriendo en el mismo host. |

Cada nodo corre su API FastAPI (`api-admin` / `api-sucursal`) y su worker de sync (`job-sync-cloud` / `job-sync-sucursal`) desde la **misma imagen multi-stage** (`infra/docker/Dockerfile.cloud` o `Dockerfile.branch`), diferenciados por `BUILD_TARGET`/`SERVICE_NAME`.

## Desplegar el nodo cloud

```bash
docker compose -f infra/deploy/docker-compose.cloud.yml up -d
docker compose -f infra/deploy/docker-compose.cloud.yml logs -f job_sync_cloud
docker compose -f infra/deploy/docker-compose.cloud.yml down   # detener
```

Servicios: `cloud-db` (Postgres 16 + pg_partman, puerto 5432), `api-admin` (puerto 8000), `job-sync-cloud`. El worker de sync corre con `replicas: 1` obligatorio — dos instancias en paralelo competirían por la misma cadena de hashes SHA-256. Variables obligatorias en la sección [Variables de entorno](#variables-de-entorno); en particular `PARKOS_DIAN_PROVIDER_URL` no tiene default y el stack no arranca sin ella.

## Desplegar un nodo de sucursal

```bash
docker compose -f infra/deploy/docker-compose.branch.yml up -d
docker compose -f infra/deploy/docker-compose.branch.yml logs -f job_sync_sucursal
docker compose -f infra/deploy/docker-compose.branch.yml down   # detener
```

Servicios: `branch-db` (puerto 5433, para no chocar con el cloud si comparten host), `api-sucursal` (puerto 8000, expuesto a la LAN — pensado para la futura PWA de sucursal, ver [usuario-final.md](./usuario-final.md)), `job-sync-sucursal`. Variables obligatorias sin default: `PARKOS_SUCURSAL_UUID` (UUIDv4) y `PARKOS_CLOUD_API_URL`.

**Emparejamiento (pairing) en el primer arranque** — la sucursal necesita un JWT de sync emitido por el cloud:

```bash
docker compose -f infra/deploy/docker-compose.branch.yml exec api-sucursal \
  parkos-core pair --cloud-url "$PARKOS_CLOUD_API_URL" --admin-jwt "$PARKOS_ADMIN_JWT"
```

Para un entorno local/dev, `infra/scripts/bootstrap_pairing.py` automatiza este flujo de punta a punta (ver [Scripts operativos](#scripts-operativos-infrascripts)).

## Entorno combinado local (desarrollo)

`docker-compose.local.yml` levanta una sucursal sobre la misma red Docker que ya creó el stack cloud, para que el worker de sucursal resuelva `api-admin` como hostname sin exponer puertos extra:

```bash
# 1. Levantar el cloud primero (crea la red parkos-cloud_parkos-cloud-net)
docker compose -f infra/deploy/docker-compose.cloud.yml up -d

# 2. Levantar la sucursal combinada sobre esa misma red
docker compose -f infra/deploy/docker-compose.local.yml --env-file .env.local up -d --build
```

Puertos ajustados para no chocar con el cloud en el mismo host: DB de sucursal en 5433 (el cloud usa 5432), `api-sucursal` en 8100 (en vez de 8000).

## Imágenes Docker

`Dockerfile.cloud` y `Dockerfile.branch` comparten el mismo patrón multi-stage: builder con `uv sync`, runtime slim sobre Python 3.13, usuario no root (`parkos`), `tini` como PID 1, y un `HEALTHCHECK` interno contra `/healthz:9999` (no expuesto fuera de la red Docker; solo lo usan Compose/K8s para `depends_on.condition: service_healthy`). El build-arg `BUILD_TARGET` selecciona el entrypoint: `api_admin` / `job_sync_cloud` (solo en `Dockerfile.cloud`) o `api_sucursal` / `job_sync_sucursal` (solo en `Dockerfile.branch`).

```bash
docker build -f infra/docker/Dockerfile.cloud . \
  --build-arg BUILD_TARGET=job_sync_cloud --build-arg UID=1000 \
  -t parkos:job-sync-cloud-test

docker build -f infra/docker/Dockerfile.branch . \
  --build-arg BUILD_TARGET=job_sync_sucursal --build-arg UID=1000 \
  -t parkos:job-sync-sucursal-test
```

Frontera DIAN: la imagen de sucursal excluye el paquete que habla con el proveedor de facturación electrónica en la nube desde el `.dockerignore` del build (nunca llega al filesystem de una sucursal); la imagen de cloud sí lo incluye. Es la primera de 3 capas de aislamiento — las otras 2 (un guard a nivel de módulo por `PARKOS_DEPLOY` y un filtro de tags en el OpenAPI) viven en el propio backend.

## Variables de entorno

Fuente de verdad en runtime: `backend/packages/parkos_core/src/parkos_core/runtime/env.py` (`load_config()`), que valida todo lo siguiente **antes** de que el proceso toque red o base de datos, y falla rápido (exit code 2) listando todas las variables con problema de una sola vez.

**Comunes a cloud y a sucursal (obligatorias):**

| Variable | Descripción |
|---|---|
| `PARKOS_DEPLOY` | `cloud` o `branch`. Define cuál de las dos validaciones siguientes aplica. |
| `PARKOS_DB_URL` | DSN de Postgres para la app (driver `psycopg`). Se conecta con el rol de mínimo privilegio (`parkos_app` por defecto en dev), nunca como superusuario. |
| `PARKOS_JWT_KEY_PATH` | Ruta al secreto de firma JWT (HS256 en modo dev). El directorio padre debe existir o falla el arranque. |

**Solo sucursal:**

| Variable | Obligatoria | Descripción |
|---|---|---|
| `PARKOS_SUCURSAL_UUID` | Sí | UUID **v4** de la sucursal (rechaza cualquier otra versión de UUID). |
| `PARKOS_CLOUD_API_URL` | Sí | URL del nodo cloud al que sincroniza. |
| `PARKOS_SYNC_JWT_PATH` | Sí | Dónde queda persistido el JWT de sync emitido en el pairing. |
| `PARKOS_SYNC_POLL_INTERVAL_S` | No (10) | Intervalo de polling del worker, en segundos. |
| `PARKOS_SYNC_BATCH_SIZE` | No (100) | Filas por lote de aplicación. |
| `PARKOS_SYNC_HEARTBEAT_S` | No (60) | Frecuencia del heartbeat del worker. |
| `PARKOS_SYNC_VERIFY_INTERVAL_S` | No (3600) | Intervalo del verificador de cadena de hashes. También aparece seteada en `docker-compose.cloud.yml`, pero `env.py` solo la tipa dentro de la config de sucursal (ver huecos más abajo). |

**Solo cloud:**

| Variable | Obligatoria | Descripción |
|---|---|---|
| `PARKOS_DIAN_PROVIDER_URL` | Sí | URL del proveedor de facturación electrónica (FE) integrado. Sin default: el stack no arranca sin definirla. |
| `PARKOS_DIAN_PROVIDER_TOKEN_PATH` | Sí | Ruta al token de autenticación contra ese proveedor, montado como secreto. |
| `PARKOS_DIAN_TIMEOUT_S` | No (30) | Timeout de las llamadas al proveedor FE. |
| `PARKOS_DIAN_RETRY_MAX` | No (3) | Reintentos máximos ante fallos del proveedor FE. |

**Presentes en los Compose pero fuera de `env.py`** (no están en la validación fail-fast; se resuelven con su default si faltan):

| Variable | Dónde aparece | Descripción |
|---|---|---|
| `PARKOS_SYNC_ENGINE` | los 3 compose | Motor de sync activo: `legacy` (default en cloud) o `catalog_branch` (default en sucursal y en el combinado local). |
| `PARKOS_APP_DB_USER` / `PARKOS_APP_DB_PASSWORD` | cloud.yml, local.yml | Credenciales del rol de aplicación de mínimo privilegio (default solo de dev: `parkos_app` / `parkos_app_dev`) con las que se arma `PARKOS_DB_URL`/`DATABASE_URL`. |
| `DATABASE_URL` | los 3 compose | Mismo DSN que `PARKOS_DB_URL` pero con driver `asyncpg`; es el que usa Alembic (`migrations/env.py`) para aplicar migraciones. |

## Scripts operativos (`infra/scripts/`)

| Script | Qué hace | Cuándo correrlo |
|---|---|---|
| `bootstrap_pairing.py` | Crea un usuario admin de desarrollo en cloud-db, emite su JWT, solicita un token de pairing y empareja una sucursal (`POST /sync/pair`), dejando el JWT de sync listo en disco. También asegura las particiones DEFAULT de pg_partman necesarias para la primera escritura. | Levantar un entorno local/dev de punta a punta sin pasar por UI (todavía no hay login real, ver [usuario-final.md](./usuario-final.md)). No usar en producción — usuario y credencial son fijos y el propio script los marca como dev-only. |
| `seed_catalogs.py` | Inserta filas de catálogo (por ejemplo tipos de vehículo) vía la API admin HTTP, autenticándose con un JWT propio. | Pruebas de humo locales del transporte de sync, cuando hacen falta datos mínimos de catálogo. |
| `seed_alert_types.py` | Siembra de forma idempotente las 8 filas de `prod.alert_types` (`hash_chain_anomaly`, `dian_rechazada`, `dian_timeout`, `dian_error`, `branch_offline_reauth_required`, `orphan_workflow_chain`, `fe_provider_error`, `fe_numbering_exhausted`) por conexión directa a Postgres, sin pasar por la API admin. | Después de aprovisionar o restaurar una base (cloud o de sucursal) que no tenga ya estas filas — por ejemplo, un snapshot anterior a la migración que las siembra. Debe correr igual contra cloud y contra cada sucursal. |
| `parkos_docker_verify.py` | Verificación estática (no toca el daemon de Docker) de que los 4 entrypoints tienen `BUILD_TARGET` + `HEALTHCHECK` en su Dockerfile y de que los compose fuerzan `replicas: 1` en los workers de sync. | Antes de commitear cambios a Dockerfiles/compose, o como chequeo rápido en CI previo al build real (el build/run real de Docker ocurre en CI, no en este script). |
| `clean_coauthored_trailers.sh` | Inventaría — sin reescribir historia — los commits de un rango que traen trailers `Co-authored-by:` de agentes de IA, lo cual viola la política del proyecto de no atribución a IA. | Antes de fusionar una rama de release (`dev` → `main`), para decidir si hace falta una reescritura de historia coordinada. El propio script deja documentado el comando de `rebase -i` para aplicarla, pero no lo ejecuta — es una operación manual, solo para mantenedores. |

## Observabilidad y alertas de sync

Las reglas de alerta viven como config-as-code en `infra/grafana/alerts/sync.yaml` (formato de *file-based alert-rule provisioning* de Grafana, `apiVersion: 1`).

**Hueco importante, documentado en el propio archivo fuente:** hoy esto es solo declarativo — no hay una instancia de Grafana/Prometheus en vivo conectada, y varias métricas que las reglas referencian (`sync_queue_pending_rows`, `sync_chain_anomalies_total`, `orphan_workflow_chain_alerts_total`, `sync_import_errors_total`, `alerta_total`) **todavía no existen** como métricas reales en el backend, ni existe todavía un endpoint `GET /metrics`. Las únicas métricas ya implementadas son `sync_apply_total`, `sync_dependency_wait`, `catalog_rows_total`, `sync_deferred_total` y `catalog_backfill_complete`. No asumas que estas alertas ya disparan en un entorno real hasta confirmar que ese endpoint y esas métricas existen.

Las 8 reglas definidas:

| Regla | Condición | Severidad |
|---|---|---|
| SyncBacklogHigh | `sync_queue_pending_rows > 1000` por 10 min | warning |
| SyncConflictRateHigh | tasa de `CONFLICT` > 0.5% de los applies en 1h, sostenida 15 min | warning |
| HashChainBreak | `sync_chain_anomalies_total > 0` por 5 min | critical |
| OrphanWorkflowChain | `rate(orphan_workflow_chain_alerts_total[1h]) > 0` por 5 min | warning |
| BranchImportError | `rate(sync_import_errors_total[5m]) > 0` por 5 min | critical |
| CatalogBackfillIncomplete | `catalog_backfill_complete == 0` durante 48h tras el pairing | warning |
| FEProviderError | `rate(alerta_total{tipo_alerta="fe_provider_error"}[1h]) > 0` por 5 min | critical |
| FENumberingExhausted | `rate(alerta_total{tipo_alerta="fe_numbering_exhausted"}[1h]) > 0` por 5 min | critical |

## Runbooks de incidentes de sync

Los 8 runbooks reales viven en `docs/runbooks/sync/` (índice de solo lectura; no se tocan desde este manual):

| Runbook | Alerta que documenta | Severidad | Cuándo se usa |
|---|---|---|---|
| [`sync_backlog.md`](../runbooks/sync/sync_backlog.md) | SyncBacklogHigh | warning | La cola de sync supera 1000 filas pendientes por más de 10 min — el worker no drena al ritmo de ingreso. |
| [`conflict_rate.md`](../runbooks/sync/conflict_rate.md) | SyncConflictRateHigh | warning | Más de 0.5% de los applies de la última hora resuelven como CONFLICT. |
| [`chain_break.md`](../runbooks/sync/chain_break.md) | HashChainBreak | critical | El verificador detecta una ruptura de integridad en la cadena de hashes — incidente de integridad de datos, resolución manual únicamente. |
| [`orphan_workflow.md`](../runbooks/sync/orphan_workflow.md) | OrphanWorkflowChain | warning | Una fila en el buffer de dependencias expiró sin que llegara su fila padre. |
| [`import_error.md`](../runbooks/sync/import_error.md) | BranchImportError | critical | El worker de una sucursal falla al aplicar filas recibidas desde cloud. |
| [`backfill_stalled.md`](../runbooks/sync/backfill_stalled.md) | CatalogBackfillIncomplete | warning | El backfill inicial de catálogos de una sucursal recién emparejada lleva 48h sin completar (bloquea el avance de cutover). |
| [`dependency_wait.md`](../runbooks/sync/dependency_wait.md) | FEProviderError † | critical | El intercambio con el proveedor de facturación electrónica agotó su presupuesto de reintentos. |
| [`client_volume.md`](../runbooks/sync/client_volume.md) | FENumberingExhausted † | critical | Se agotó el rango de numeración autorizado de facturación de una sucursal. |

† **Mismatch documentado, no corregido todavía**: el nombre de archivo de estos 2 runbooks no corresponde al nombre de la alerta que realmente documentan (arrastran nombres de una versión de diseño ya reemplazada). Tanto `sync.yaml` como el encabezado de cada runbook lo señalan explícitamente; la tabla de arriba ya refleja qué alerta documenta cada uno en la práctica, no lo que sugiere el nombre del archivo.

## Ver también

- [Manual de usuario final](./usuario-final.md)
- [Modelo de datos](../02-arquitectura/modelo-datos.md)
- [Seguridad](../02-arquitectura/seguridad.md)
- [Configuración de desarrollo](../03-desarrollo/setup.md)
