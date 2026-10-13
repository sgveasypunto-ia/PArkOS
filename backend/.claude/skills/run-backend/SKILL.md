---
name: run-backend
description: Levanta, verifica y ejecuta el backend de Parkos (api-admin :8000, api-sucursal :8100, jobs de sync, Postgres cloud/branch). Úsala para run, start, smoke, health, login, comprobar sync, probar código interno de parkos_core con uv, correr tests unitarios/integración o check_schema_match.
---

# run-backend

Backend Python (FastAPI + SQLAlchemy async) desplegado con Docker Compose en dos nodos locales: `parkos-cloud` (api-admin `:8000`, DB `:5432`, job-sync-cloud) y `parkos-local` (api-sucursal `:8100`, DB `:5433`, job-sync-sucursal). El driver es `smoke.py` (solo stdlib) más `docker exec psql` para inspeccionar. Todas las rutas son relativas a la raíz del repo (`E:\easypunto_parkos`), no a `backend/`.

## Prerrequisitos

- Docker Desktop corriendo. Si `docker ps` falla con `dockerDesktopLinuxEngine`, arráncalo (ver Gotchas).
- `uv` (probado con 0.11.32). Las dependencias ya están en `backend/.venv`; usa `--offline`.
- Credenciales: operador QA y admin en `AGENTS.md` ("Dev Credentials"); no se copian aquí.

## Ejecutar (ruta del agente)

Estado de la stack (7 contenedores `healthy`):

```bash
docker ps --format '{{.Names}}\t{{.Status}}'
```

Smoke completo (health ×2, login, `sync/estado`, round-trip sucursal→nube; ~30 s):

```bash
python backend/.claude/skills/run-backend/smoke.py
```

Salida esperada: `PASS` en health, login operador, `sync/estado` y `sync sucursal->nube`; el login admin puede salir `SKIP` (ver Gotchas). Exit 0 si no hay `FAIL`.

Health y esquema de login a mano:

```bash
curl -s -m 8 http://127.0.0.1:8100/health
curl -s -m 8 http://127.0.0.1:8000/health
```

Login es `POST /api/v1/auth/login` con `{"email","password"}` (password 8–128 chars) en ambas APIs. Devuelve `access_token`, `refresh_token`, `temporary_token`, `expires_in`, `must_change_password`. El JWT del operador lleva el claim `sucursal` (uuid), que `GET /api/v1/sync/estado?uuid_sucursal=<uuid>` exige.

Inspección de BD (solo lectura; usuario `parkos`, base `parkos`):

```bash
docker exec parkos-branch-db psql -U parkos -d parkos -Atc "select estado, count(*) from prod.sync_queue group by 1"
docker exec parkos-cloud-db psql -U parkos -d parkos -Atc "select email, rol, estado from prod.usuarios order by created_at limit 10"
docker logs --tail 8 parkos-job-sync-sucursal
```

### Código interno sin levantar nada

```bash
cd backend && uv run --offline python -c "from parkos_core.sync.motor.pull_scope import build_scope_predicate; print(build_scope_predicate.__name__)"
```

### Tests

Corre siempre desde la raíz con `PYTHONPATH=.`: varios tests importan `backend.tests.conftest`, y desde `backend/` fallan en la colección con `No module named 'backend'`. `-o addopts=` evita el cobertura global y deja ver el resumen.

```bash
PYTHONPATH=. uv run --project backend --offline pytest backend/tests/unit -o addopts= -q --tb=no -W ignore -p no:cacheprovider -c backend/pyproject.toml --rootdir backend
```

Integración (testcontainers: necesita Docker y la imagen con pg_partman, que ya existe localmente):

```bash
TEST_PG_IMAGE=parkos-postgres:16-pgpartman PYTHONPATH=. uv run --project backend --offline pytest backend/tests/integration/test_sync_pull_scope_matrix.py -o addopts= -q --tb=short -W ignore -p no:cacheprovider -c backend/pyproject.toml --rootdir backend
```

Verificado: 32 passed. Sin `TEST_PG_IMAGE` el mismo archivo da `2 passed, 30 skipped` ("alembic upgrade head failed") porque `postgres:16-alpine` no trae pg_partman.

Paridad del esquema con `modelo_datos_er.mmd` (necesita DSN de la nube; la clave se lee del contenedor sin imprimirla):

```bash
PW=$(docker exec parkos-cloud-db printenv POSTGRES_PASSWORD); DATABASE_URL="postgresql://parkos:${PW}@127.0.0.1:5432/parkos" timeout 100 uv run --project backend --offline python openspec/scripts/check_schema_match.py
```

Termina en `OK: 100% match`.

### Reconstruir tras cambiar código o migraciones

Las migraciones van dentro de la imagen; sin `--build` el servicio `migrate` sale 0 sobre el head viejo. No lo ejecutes si otros agentes usan `:8000`/`:8100` (los reinicia). Comando documentado, **no ejecutado en esta sesión**:

```bash
docker compose -p parkos-cloud --env-file infra/deploy/.env.cloud -f infra/deploy/docker-compose.cloud.yml up -d --build
```

## Gotchas

- **Docker apagado**: con el daemon caído `docker ps` falla y `:8000/:8100` no responden (el servicio de Windows `com.docker.service` estaba `Stopped`). Docker Desktop está instalado en `%LOCALAPPDATA%\Programs\DockerDesktop\` (no en Program Files; ahí no existe). En esta sesión el daemon apareció por sí solo unos 20 s después de intentar lanzarlo, y los 7 contenedores volvieron `healthy` en ~30 s sin `compose up`. No verifiqué el arranque manual de la app: si no sube, ábrela desde el menú Inicio.
- **Login admin**: la contraseña de `admin@parkos.local` en la BD ya no coincide con la de `infra/scripts/bootstrap_pairing.py` (401). Tras varios intentos fallidos la API responde **429**; no insistas. Exporta `PARKOS_ADMIN_PASSWORD` para que `smoke.py` la use. El operador QA no entra por la API admin (401): cada API acepta sus propios emisores.
- **Cada login escribe `log_transaccional`** y encola sync; el smoke tiene ese efecto lateral (inofensivo, append-only).
- **Cola de sync nunca llega a 0 aquí**: `sync_queue` tenía ~35 `pendiente` y el job registra `push_ok status=207` (respuesta parcial) cada pocos segundos. Es estado previo del dato local, no un fallo del smoke; el round-trip se comprueba porque `log_transaccional` de la nube crece.
- **Postgres**: usuario `parkos`, no `postgres` (`role "postgres" does not exist`).
- **Suite unitaria no está limpia**: 32 failed / 1795 passed / 272 skipped en `tests/unit`, y 22 failed en `tests/static` (p. ej. un escaneo de `apps/web_admin/dist` que encuentra `consecutivo_actual`, y rutas admin sin importar `tenancy`). Verifica contra `git stash`/`dev` antes de atribuirte un fallo.
- Con el `addopts` del proyecto el `tail -1` de pytest no mostraba la línea `N passed, M failed`; con `-o addopts=` sí.

## Troubleshooting

| Síntoma | Causa y arreglo |
|---|---|
| `failed to connect to the docker API ... dockerDesktopLinuxEngine` | Docker Desktop apagado; arráncalo y espera ~30 s. |
| `ModuleNotFoundError: No module named 'backend'` al colectar | Correr pytest desde `backend/`; usa la raíz con `PYTHONPATH=.`. |
| Integración: `skipped: alembic upgrade head failed (exit 1)` | Falta `TEST_PG_IMAGE=parkos-postgres:16-pgpartman`. |
| `ERROR: --database-url or DATABASE_URL env var required` | `check_schema_match.py` necesita `DATABASE_URL`; ver comando arriba. |
| `ERROR: ER file not found: modelo_datos_er.mmd` | El script se ejecutó desde `backend/`; hazlo desde la raíz. |
| Login `429` | Bloqueo por intentos fallidos; espera antes de reintentar. |
