# Estándares de código

Convenciones reales de easypunto_parkos, verificadas contra `backend/pyproject.toml`, los `pyproject.toml` de cada paquete, `apps/web_admin/eslint.config.js`, `apps/web_admin/.prettierrc.json`, `AGENTS.md` y el historial de `git log`.

## Backend (Python 3.13)

### Ruff

Configurado en dos niveles:

- **Workspace** (`backend/pyproject.toml`): `line-length = 100`, `target-version = "py313"`, `select = ["E", "F", "I", "UP", "B", "ASYNC", "SIM", "PT", "RUF"]`. Se usa `select` (no `extend-select`) a propósito: así ningún `pyproject.toml` de paquete puede reducir el set de reglas del workspace al usar `extend-select` con una lista distinta.
- **Por paquete** (ej. `parkos_core/pyproject.toml`): repite `line-length`/`target-version` y añade `extend-select = ["I", "UP", "B", "ASYNC", "SIM", "PT", "RUF"]` (sin `E`/`F` explícitos porque ruff ya los habilita por defecto).

**`extend-exclude`** (solo a nivel workspace) excluye rutas con hallazgos de ruff preexistentes que no son responsabilidad del refactor puntual PR1c: routers de API, modelos ORM, repos, auth, motor de DB, `env.py` de Alembic, el schema inicial de 2000 líneas (`0001_initial_schema.py`) y `scripts/apply_migration.py`. Lo que **sí** se lintea siempre: `tests/**`, `migrations/versions/0002_seed_permisos_canonicos.py` y el placeholder `api/v1/__init__.py`. Objetivo: `ruff check backend/` sale en 0 sobre el código posterior a PR1c sin tener que arreglar deuda preexistente fuera de alcance.

`per-file-ignores` relevantes:

| Ruta | Reglas ignoradas | Motivo |
|---|---|---|
| `tests/**` | `B`, `PT011`, `S101` | convenciones de `assert` y bugbear no aplican a tests |
| `migrations/**`, `**/models/V/*` | `E501` | listas largas de columnas / SQL inline superan la longitud de línea con frecuencia |
| `backend/**/api/v1/auth.py`, `backend/**/api/v1/catalogos.py` | `B008` | `Depends(...)` como default-arg es idiomático en FastAPI, aunque bugbear lo marque |

Comando: `uv run ruff check .` (desde `backend/`). No se encontró configuración ni uso de `ruff format` en el repo — no lo documentamos como paso real hasta confirmarlo.

### mypy

Configurado únicamente en `parkos_core/pyproject.toml` (no en `api_admin`/`api_sucursal`): `strict = true`, `disallow_untyped_defs`, `disallow_incomplete_defs`, `warn_return_any`, `warn_unused_ignores`, `no_implicit_optional`. Overrides con `ignore_missing_imports` para `factory.*`, `faker.*`, `alembic.*`.

CI corre mypy **solo** contra `packages/parkos_core/src`:

```bash
uv run mypy packages/parkos_core/src
```

### Pytest

- `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"`, `asyncio_default_test_loop_scope = "session"` — fixtures async de sesión compartida (p. ej. `pg_engine`) viven en un único loop.
- `addopts` locales: `-q --tb=short --cov=parkos_core.sync --cov-report=term-missing`. **No** incluyen `--cov-fail-under=80`: ese umbral vive solo en `.github/workflows/ci.yml` porque un `--cov-fail-under` global rompería cualquier invocación de test focalizada (evidencia reproducida: 19/19 tests en verde con exit code no-cero solo por el umbral contra una porción del 3.66 % del código).
- `testpaths = ["tests"]`.

### Estructura de módulos (`models/`)

`parkos_core/src/parkos_core/models/` particiona cada tabla en una de 5 clases de auditoría (`models/base.py`, `AGENTS.md §1`). El total real es **49 tablas**:

| Carpeta | Base abstracta | Semántica | Tablas |
|---|---|---|---|
| `models/V/` | `VersionedBase` | Bi-temporal *close+insert* (`vigente_desde`/`vigente_hasta`/`estado`); nunca se actualiza una fila in-place | 26 |
| `models/L_E/` | `LifecycleEventBase` | Evento de ciclo de vida, solo inserción (`ingreso`, `facturas`, `factura_electronica`) | 3 |
| `models/L_W/` | `WorkflowBase` | Transiciones de máquina de estados (`alerta`, `anulaciones`, `envio_dian`, `reclamos`, `reimpresion_ticket`, `validacion_evento`) | 6 |
| `models/L_S/` | `SessionBase` | Ciclo de vida de sesión (`login`, `sesion`) | 2 |
| `models/A/` | `AppendOnlyBase` | Append-only con retención DIAN; `REVOKE UPDATE, DELETE` a nivel de rol de BD + trigger `BEFORE UPDATE OR DELETE` | 12 |

Mixins compartidos (`models/base.py`): `IdMixin` (PK `uuid`), `AuditMixin` (`created_at`/`created_by`, obligatorio en toda tabla), `SyncMixin` (`sync_status`/`sync_timestamp`/`sync_attempts`), `VersionedMixin` (solo `[V]`), `RetentionMixin` (`fecha_retencion_hasta`, solo `[A]`), `HashChainMixin` (`hash_anterior`/`hash_actual`, **solo** `log_transaccional` y `revocacion_factura`). Cada base abstracta lleva además un marcador de clase (`__close_and_insert_only__`, `__record_only__`, `__workflow_only__`, `__session_only__`, `__write_only__`) que un scan AST en `tests/static/` usa para verificar en CI que nadie mutó una tabla `[A]` fuera de `repo/append_only.py`.

`models/__init__.py` importa **las 5 carpetas completas**: cualquier import parcial deja tablas referenciadas por `ForeignKey("prod.<tabla>.uuid")` (por nombre, no por clase) sin registrar en el metadata compartido de SQLAlchemy, y falla con `NoReferencedTableError` al correr un test aislado.

### Contrato de API: Consulta, Inserción, Actualización — sin DELETE físico

Regla de arquitectura no negociable (`AGENTS.md`, principio 3): la API expone solo tres operaciones por recurso. "Actualización" es bi-temporal (cierra la fila vigente + inserta una nueva); **no existe operación DELETE en ninguna capa**. Toda corrección conceptual se modela como una fila nueva en una tabla de workflow (`anulaciones`, `reclamos`, `alerta`, etc.) o como una fila compensatoria (`factura_pagos.tipo_movimiento = 'reverso'`). Se aplica en defensa en profundidad: API (sin endpoint DELETE), ORM (helpers close+insert, sin hard delete en `[V]`/`[A]`) y DB (`REVOKE DELETE` + trigger). Ver `api-reference.md` para el patrón CRUD real que expone `router_factory.make_router`.

## Convención de commits

Conventional Commits (`tipo(scope): descripción`), sin `Co-Authored-By` ni atribución de IA. Ejemplos reales de `git log --oneline`:

```
fix(db): la app deja de conectarse como superusuario, ahora usa un rol de mínimo privilegio real
test(sync): acota el conteo de sync_conflict a la fila propia del test
feat(sync): implementa /sync/pull real y genérico por JWT de la sucursal, ya no es un stub
chore(sync-overhaul): archiva el change y fusiona sus specs al canon del proyecto, corrige el guard R21 tras el archivado (#55)
```

Tipos observados en el historial reciente: `feat`, `fix`, `test`, `chore`. El scope identifica el módulo o dominio afectado (`db`, `sync`, `api`, `auth`, `sync-overhaul`, …). Algunos commits terminan con el número de PR entre paréntesis (p. ej. `(#55)`) por squash-merge de GitHub. El mensaje describe el motivo del cambio, no solo el qué (varios ejemplos citan el defecto real corregido).

## Frontend (TypeScript / React)

### ESLint

`apps/web_admin/eslint.config.js` es *flat config* (ESLint 9.x): extiende `@eslint/js` recommended + `typescript-eslint` recommended + `eslint-plugin-react-hooks` recommended, más `eslint-plugin-react-refresh`. Reglas propias:

- `@typescript-eslint/no-unused-vars`: error, ignora identificadores prefijados con `_`
- `@typescript-eslint/consistent-type-imports`: error
- `react-refresh/only-export-components`: warn (permite `allowConstantExport`)

El chequeo de tipos se delega a `tsc -b` (dentro del script `build`), no a ESLint. Comando: `npm run lint` → `eslint . --ext .ts,.tsx --max-warnings 0` (cero warnings tolerados).

### Prettier

`.prettierrc.json`: `semi: true`, `singleQuote: true`, `trailingComma: "all"`, `printWidth: 100`, `tabWidth: 2`, `arrowParens: "always"`, `endOfLine: "lf"`. No hay script npm dedicado a Prettier en `package.json` — para validar formato manualmente: `npx prettier --check .`.

### Estructura (`apps/web_admin/src/`)

```
src/
├── components/ui/   # generado por shadcn — no editar a mano
├── i18n/            # i18next + locales
├── lib/             # helpers (cn(), servicios)
├── pages/           # componentes de ruta (Login, Dashboard, ...)
├── App.tsx          # router
├── main.tsx         # entrypoint
├── index.css        # Tailwind + variables CSS de shadcn
└── test-setup.ts    # matchers de @testing-library/jest-dom
e2e/                 # specs de Playwright
```

## CI (referencia de orden real)

`.github/workflows/ci.yml` corre, en orden estricto (cualquier paso que falla detiene el job), sobre PRs y pushes a `dev` que tocan `backend/**` u `openspec/scripts/**`:

1. `uv sync --frozen --all-extras --dev`
2. Guard de carve-out de `sync_queue` (`openspec/scripts/check_sync_queue_carveout.py`)
3. Guard de drift de catálogo (`openspec/scripts/check_catalog_drift.py`)
4. `uv run ruff check .`
5. `uv run mypy packages/parkos_core/src`
6. `uv run pytest --cov --cov-report=xml --cov-fail-under=80`
7. Escaneo Trivy (solo en push a `dev`)

## Siguiente paso

- Instalación y ejecución local → [`setup.md`](./setup.md)
- Endpoints reales → [`api-reference.md`](./api-reference.md)
- Decisiones de arquitectura → `../02-arquitectura/decisiones-tecnicas.md`
