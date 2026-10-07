# Configuración del entorno de desarrollo

Esta guía cubre la instalación y ejecución local real de easypunto_parkos: backend (`backend/`, workspace `uv`) y frontend (`apps/`, workspace `npm`). Todos los comandos están verificados contra los `pyproject.toml`, `package.json` y archivos `docker-compose.*.yml` reales del repositorio.

## Requisitos previos

| Herramienta | Versión | Uso |
|---|---|---|
| Python | 3.13 | `requires-python = ">=3.13"` en los 4 `pyproject.toml` del backend |
| [uv](https://docs.astral.sh/uv/) | 0.4+ | Gestor de paquetes y workspace del backend (`backend/pyproject.toml` → `[tool.uv.workspace]`) |
| Node.js | 20+ (recomendado) | Requerido por Vite 5 / TypeScript 5.6 / ESLint 9 |
| npm | el que trae Node | Gestor de paquetes del frontend — ver nota abajo |
| Docker + Docker Compose v2 | — | Postgres 16 (`pg_partman` 5.5.0 instalado, pero **sin mantenimiento automático** — ver la nota de particionado más abajo) + APIs FastAPI |

> **Aviso de particionado (2026-10-01).** `pg_partman` está instalado y `pg_partman_bgw` está en `shared_preload_libraries`, pero **nadie invoca `run_maintenance_proc()`**: no hay `pg_cron` en la imagen. Por eso las particiones las crea la migración `0064_ensure_forward_partitions` de forma explícita. Si borras el volumen y recreas el Postgres, corré `SELECT prod.fn_ensure_partitions();` (idempotente) y verificá que `python openspec/scripts/check_schema_match.py --database-url ...` no reporte fallos en (h). Detalle completo en [ADR-004](../02-arquitectura/decisiones-tecnicas.md#adr-004-particionado-sin-mantenimiento-automático-real).
>
> **Migraciones al levantar el stack**: los compose de `infra/deploy/` (`cloud`, `branch`, `local`, `local-e2e`) incluyen un servicio `migrate` de un solo disparo (`e2e-migrate` en `local-e2e`) que ejecuta `alembic upgrade head` antes de que arranquen las APIs y los jobs de sync. Usa la misma imagen que la API, `restart: "no"` y se conecta como superusuario de Postgres, porque el usuario de la app no tiene `CREATE` sobre el esquema `prod` (`InsufficientPrivilege`).
>
> ```powershell
> docker compose -f infra/deploy/docker-compose.cloud.yml up -d --build
> docker compose -f infra/deploy/docker-compose.cloud.yml logs migrate   # salida de alembic
> ```
>
> - Credenciales del superusuario: variables `PARKOS_DB_SUPER_USER` / `PARKOS_DB_SUPER_PASSWORD` (por defecto `parkos` / `parkos`, solo desarrollo). Definilas igual para la base y para `migrate`; en un despliegue real defínelas en el `.env` y evitá caracteres reservados de URL en la clave.
> - Estas variables solo se aplican al inicializar un volumen nuevo de Postgres; con un volumen existente, cambiar la clave requiere `ALTER USER` en la base (si no, `migrate` falla por autenticación). En `branch` las APIs y los sync jobs usan estas mismas credenciales (comportamiento previo, ahora parametrizado).
- Si `migrate` falla, las APIs y los jobs **no arrancan**; el error se ve en `docker compose logs migrate`. Un segundo `up` es un no-op (alembic es idempotente). Hay un único `migrate` por nodo y los jobs de sync corren con 1 réplica, por lo que no hay migraciones concurrentes (no se usa advisory lock).
> - **Para aplicar una actualización (código y migraciones nuevas) hay que reconstruir las imágenes**: `docker compose -f <archivo> up -d --build` (o `build` y luego `up -d`). Las migraciones van copiadas dentro de la imagen (`COPY backend/packages`), no montadas como volumen; `migrate` usa la misma imagen que los demás servicios, así que sin `--build` no ve las migraciones nuevas y termina con éxito en el head anterior, sin error. En `local-e2e` los servicios reutilizan imágenes ya construidas por `docker-compose.local.yml`: reconstruí allí primero.
> - Para correrlo a mano (diagnóstico): `docker compose -f <archivo> run --rm migrate`.


**Gestor de paquetes del frontend confirmado: npm.** `apps/package.json` usa `npm --workspace=web_admin run <script>` y `npm-run-all`; `apps/web_admin/README.md` documenta explícitamente `npm --workspace=web_admin run <script>` como forma de invocación desde la raíz. No se encontró `pnpm-lock.yaml` ni `yarn.lock` en el repo. **Hueco**: tampoco se encontró `package-lock.json` versionado en `apps/` ni `apps/web_admin/` — ver huecos al final.

## Backend (`backend/`)

### 1. Instalar dependencias

```bash
cd backend
uv sync --all-extras --dev
```

Esto resuelve el workspace completo (`[tool.uv.workspace] members = ["packages/*"]`): `parkos_core` (librería compartida: modelos SQLAlchemy, schemas Pydantic, auth, sync, Alembic), `api_admin` (entrypoint FastAPI cloud) y `api_sucursal` (entrypoint FastAPI de sucursal). Ambos paquetes API declaran `parkos-core = { workspace = true }` en `[tool.uv.sources]`.

### 2. Levantar Postgres + APIs con Docker Compose

Hay **3 archivos reales** en `infra/deploy/`, cada uno con un propósito distinto:

| Archivo | Qué levanta | Red |
|---|---|---|
| `docker-compose.cloud.yml` | `cloud-db` (Postgres, puerto 5432) + `api-admin` (puerto 8000) + `job-sync-cloud` | crea `parkos-cloud-net` (bridge) |
| `docker-compose.branch.yml` | `branch-db` (Postgres, puerto 5433) + `api-sucursal` (puerto 8000) + `job-sync-sucursal` | red propia `parkos-branch-net`, standalone (requiere `PARKOS_CLOUD_API_URL` apuntando a una nube real) |
| `docker-compose.local.yml` | Combina cloud + **una** sucursal local en la misma red Docker (sucursal en `api-sucursal:8100`, `branch-db:5433`) | reutiliza la red externa `parkos-cloud_parkos-cloud-net` creada por `docker-compose.cloud.yml` |

Flujo real para desarrollo local (`docker-compose.local.yml` depende de que la nube ya esté arriba):

```bash
docker compose -f infra/deploy/docker-compose.cloud.yml up -d --build
docker compose -f infra/deploy/docker-compose.local.yml --env-file .env.local up -d --build
```

Variables de entorno **requeridas sin default** (el compose falla explícitamente si faltan):

- `PARKOS_SUCURSAL_UUID` (UUID v4 de la sucursal)
- `PARKOS_DIAN_PROVIDER_URL` (solo cloud)
- `PARKOS_CLOUD_API_URL` (solo `docker-compose.branch.yml` standalone; en `docker-compose.local.yml` se resuelve internamente como `http://api-admin:8000`)

Variables con default de desarrollo (nunca valores reales de producción, según los comentarios del propio compose):

- `PARKOS_APP_DB_USER` / `PARKOS_APP_DB_PASSWORD` → `parkos_app` / `parkos_app_dev`
- `PARKOS_SYNC_ENGINE` → `legacy` en `docker-compose.cloud.yml`, `catalog_branch` en `docker-compose.local.yml`/`docker-compose.branch.yml`

La app se conecta como el rol de mínimo privilegio `parkos_app` (migración `0021`), **no** como el superusuario `parkos` (ver commit `5edb317`, `fix(db)`). El healthcheck de cada API golpea `GET /openapi.json`; además existe un endpoint real `GET /health` (confirmado en `api_sucursal_main/app.py`) que responde `{"status": "ok", "service": "...", "deploy": "cloud"|"branch"}`.

**Hueco**: no existe `.env.local` ni ningún `.env.example` en `infra/deploy/` — hay que crearlo a mano con al menos `PARKOS_SUCURSAL_UUID` antes del segundo comando.

### 3. Migraciones (Alembic)

Alembic vive en `backend/packages/parkos_core/migrations/` (`env.py` hace `from parkos_core.models import *`, `include_schemas=True` para el esquema `prod.*`).

```bash
cd backend
uv run alembic upgrade head
```

Alternativa vía script (usa `testcontainers` para levantar un Postgres efímero): `uv run python scripts/apply_migration.py`.

### 3.1 Cola de sync: reinicio operativo y cierres de sesión atrasados

La migración `0092` hace dos cosas: el cierre de una `sesion` (UPDATE) ahora se encola igual que su apertura, y `sync_queue.tabla` lleva siempre el nombre de la tabla padre (nunca `*_p_2026_10` ni `*_default`). Las filas ya encoladas antes de `0092` no se reescriben ni se borran (la regla "sin DELETE" aplica también a `sync_queue`); se reinician SOLO los campos operativos:

```sql
-- filas fallidas o atascadas con error (cloud y sucursal): vuelven a la cola
UPDATE prod.sync_queue
   SET estado = 'pendiente', intentos = 0, next_retry_at = NULL, ultimo_error = NULL
 WHERE estado = 'fallido' OR (estado = 'pendiente' AND ultimo_error IS NOT NULL);
```

El worker de la nube normaliza el nombre de partición (`log_transaccional_p_2026_10` -> `log_transaccional`) y liquida como `exitoso` las filas cuyo uuid ya existe en su propia tabla (se originaron en ese nodo y reaplicarlas duplicaría la cadena hash).

Los cierres de sesión ocurridos ANTES de `0092` nunca se encolaron. Para reponerlos, en la sucursal (idempotente: la nube aplica el cierre sobre el mismo uuid y un cierre repetido es un no-op). El `created_at` de cada fila es el instante de cierre, para que se aplique antes de la apertura posterior del mismo operador:

```sql
INSERT INTO prod.sync_queue (uuid, uuid_sucursal, operacion, tabla, uuid_registro, datos,
                             prioridad, estado, intentos, created_at, created_by,
                             sync_status, sync_attempts)
SELECT gen_random_uuid(), s.uuid_sucursal, 'UPDATE', 'sesion', s.uuid,
       jsonb_set(to_jsonb(s), '{seq}',
                 to_jsonb((SELECT COALESCE(MAX((q.datos->>'seq')::bigint), 0)
                             FROM prod.sync_queue q
                            WHERE q.uuid_sucursal IS NOT DISTINCT FROM s.uuid_sucursal)
                          + ROW_NUMBER() OVER (PARTITION BY s.uuid_sucursal
                                               ORDER BY s.timestamp_cierre))),
       1, 'pendiente', 0, s.timestamp_cierre, s.created_by, 'pendiente', 0
  FROM prod.sesion s
 WHERE s.timestamp_cierre IS NOT NULL
   AND s.timestamp_cierre >= TIMESTAMP '2026-10-06';
```

### 3.2 Filas de catálogo sembradas con uuid distinto por nodo

`0029` sembraba `costos_servicios.concepto='reimpresion'` con `gen_random_uuid()` en cada nodo, y `costos_servicios` solo replica nube -> sucursal. Una `reimpresion_ticket` creada en la sucursal nombra el uuid local, que la nube no tiene: su push falla con violación de FK para siempre. `0093` hace que todo nodo converja en el uuid determinista `08e06c53-60cf-5392-8b96-51024d6d3c9e` (uuid5, mismo namespace que `0019`/`0056`); la fila anterior se cierra, nunca se borra.

Las `reimpresion_ticket` ya emitidas apuntan al uuid aleatorio de la sucursal (la FK local lo sigue satisfaciendo: la versión cerrada permanece). Para que su push se aplique, en la **nube** se registra el alias uuid-sucursal -> uuid-determinista (tabla `[A]` local de sync; el motor reescribe `uuid_costo_servicio` al aplicar). Después se reinician solo los campos operativos de esas filas en la **sucursal** (§3.1):

```sql
-- nube: <uuid_sucursal> = uuid de costos_servicios que el push no encuentra (ultimo_error / datos->>'uuid_costo_servicio')
INSERT INTO prod.sync_identity_alias (tabla, uuid_origen, uuid_resuelto)
VALUES ('costos_servicios', '<uuid_sucursal>', '08e06c53-60cf-5392-8b96-51024d6d3c9e')
ON CONFLICT (uuid_origen) DO NOTHING;

-- sucursal: solo las filas que fallaron por esa FK
UPDATE prod.sync_queue
   SET estado = 'pendiente', intentos = 0, next_retry_at = NULL, ultimo_error = NULL
 WHERE tabla = 'reimpresion_ticket' AND estado = 'pendiente' AND ultimo_error IS NOT NULL;
```

Auditoría de las demás siembras con uuid aleatorio por nodo (no tocadas por `0093`): `tipo_arqueo` (`0040`) y `tipos_vehiculo` (`0062`) divergen entre nodos y hoy funcionan solo porque la nube tiene el alias de cada uno; `configuracion_seguridad` y una fila de `configuracion_tolerancias` (`0001`/`0041`) divergen pero ninguna tabla transaccional las referencia por FK. Un nodo nuevo repetirá el fallo en `arqueo.uuid_tipo_arqueo` hasta que se les dé uuid determinista o se registre su alias.

### 4. Tests backend

```bash
uv run pytest
```

Puntos reales de `backend/pyproject.toml` a tener en cuenta:

- `asyncio_mode = "auto"` — no hace falta `@pytest.mark.asyncio` en cada test.
- `asyncio_default_fixture_loop_scope = "session"` — los fixtures async compartidos (`pg_engine`, etc.) viven en un único loop de sesión; es obligatorio para que la suite completa no choque con "Future attached to a different loop".
- `addopts` trae `--cov=parkos_core.sync --cov-report=term-missing` — la cobertura instrumentada localmente está acotada a `parkos_core.sync`, no a todo el backend.
- **No** hay `--cov-fail-under=80` en `addopts` (decisión deliberada y documentada en el propio `pyproject.toml`: un umbral global ahí rompería cualquier invocación focalizada, p. ej. `uv run pytest tests/unit/test_engine_flag.py -q`). Ese gate del 80% solo se aplica en CI.
- Los tests de integración usan `testcontainers[postgres]` — Docker debe estar corriendo.

Para correr un subconjunto: `uv run pytest tests/unit/test_engine_flag.py -q`.

### 5. Lint y type-check (paridad con CI)

```bash
uv run ruff check .
uv run mypy packages/parkos_core/src
```

Ver `estandares.md` para el detalle de reglas, exclusiones y su justificación.

## Frontend (`apps/web_admin`)

### 1. Instalar dependencias

```bash
cd apps
npm install
```

`apps/` es la raíz del workspace npm (`workspaces: ["ui-kit", "web_admin"]`). `ui-kit` (clientes API generados) se resuelve por enlace de workspace; hoy no tiene scripts propios de `dev`/`build` en la raíz (`apps/package.json` solo define `dev:web_admin`, `build:web_admin`, `lint:web_admin`, `test:web_admin`).

### 2. Levantar en desarrollo

```bash
npm --workspace=web_admin run dev
```

Vite sirve en `http://localhost:5173` (puerto fijado en `vite.config.ts` y en `playwright.config.ts`). Equivalente: `cd apps/web_admin && npm run dev`.

### 3. Tests

```bash
npm --workspace=web_admin run test       # vitest run — jsdom, una sola pasada (no watch)
npm --workspace=web_admin run test:e2e   # playwright test — levanta "npm run dev" automáticamente
```

**Hueco**: no hay script npm que ejecute `npx playwright install`; la primera vez puede ser necesario instalar los navegadores de Playwright manualmente.

### 4. Lint y build

```bash
npm --workspace=web_admin run lint    # eslint . --ext .ts,.tsx --max-warnings 0
npm --workspace=web_admin run build   # tsc -b && vite build
```

El chequeo de tipos ocurre en `build` (`tsc -b`), no en `lint` — ver `estandares.md`.

## Checklist de verificación

- [ ] `uv run pytest` corre en verde (backend)
- [ ] `docker compose -f infra/deploy/docker-compose.cloud.yml ps` muestra los servicios `healthy`
- [ ] `npm --workspace=web_admin run dev` sirve en `http://localhost:5173`
- [ ] `npm --workspace=web_admin run lint` y `npm --workspace=web_admin run build` terminan sin errores
- [ ] `npm --workspace=web_admin run test:e2e` pasa (requiere navegadores de Playwright instalados)

## Siguiente paso

- Estilo de código y convenciones → [`estandares.md`](./estandares.md)
- Endpoints reales → [`api-reference.md`](./api-reference.md)
- Arquitectura y modelo de datos → `../02-arquitectura/modelo-datos.md`
- Runbooks de sync ya existentes → `../runbooks/sync/`
