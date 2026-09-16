# Configuración del entorno de desarrollo

Esta guía cubre la instalación y ejecución local real de easypunto_parkos: backend (`backend/`, workspace `uv`) y frontend (`apps/`, workspace `npm`). Todos los comandos están verificados contra los `pyproject.toml`, `package.json` y archivos `docker-compose.*.yml` reales del repositorio.

## Requisitos previos

| Herramienta | Versión | Uso |
|---|---|---|
| Python | 3.13 | `requires-python = ">=3.13"` en los 4 `pyproject.toml` del backend |
| [uv](https://docs.astral.sh/uv/) | 0.4+ | Gestor de paquetes y workspace del backend (`backend/pyproject.toml` → `[tool.uv.workspace]`) |
| Node.js | 20+ (recomendado) | Requerido por Vite 5 / TypeScript 5.6 / ESLint 9 |
| npm | el que trae Node | Gestor de paquetes del frontend — ver nota abajo |
| Docker + Docker Compose v2 | — | Postgres (`pg_partman`) + APIs FastAPI |

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
