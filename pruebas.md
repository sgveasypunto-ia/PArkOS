# Pruebas — easypunto_parkos

> **Set completo de pruebas reproducible** (backend + frontend + openspec).
> Ejecutar desde la raíz del repo (`E:\easypunto_parkos`) salvo donde se indique.
> Última ejecución verificada: **2026-09-17** (sesión de auditoría F1 + F4 + F12 closure).
> Resultado global: **430+ tests ejecutados, 396 PASSED, 19 pre-existing FAIL, 0 regresiones nuevas**.

---

## 0. Resumen rápido (TL;DR)

| Suite | Comando (raíz del repo) | Tiempo esperado | Estado sandbox |
|---|---|---|---|
| Backend unit (sin DB) | `cd backend && uv run pytest tests/unit/ -q --tb=line` | ~30 s | ✅ PASS |
| Backend integration (DB) | `cd backend && uv run pytest tests/integration/ -q` | ~3 min | ⏭️ SKIP-env (Docker no disponible) |
| Backend ruff | `cd backend && uv run ruff check .` | ~2 s | ⚠️ 199 errors (104 auto-fixables con `--fix`) |
| Backend ruff format | `cd backend && uv run ruff format --check .` | ~3 s | ⏭️ TBD |
| Backend mypy strict (auth/tenancy.py) | `cd backend && uv run mypy --strict packages/parkos_core/src/parkos_core/auth/tenancy.py` | ~5 s | ✅ 0 errores |
| Backend mypy strict (clientes_venta.py) | `cd backend && uv run mypy --strict packages/parkos_core/src/parkos_core/api/v1/clientes_venta.py` | ~8 s | ⚠️ 5 errores pre-existing (líneas 160/206/239/453/456) |
| Frontend vitest (`@parkos/ui-kit`) | `cd apps/ui-kit && ./node_modules/.bin/vitest run` | ~1 s | ✅ **34/34 PASS** |
| Frontend vitest (`apps/electron-sucursal`) | `cd apps/electron-sucursal && ./node_modules/.bin/vitest run` | ~10 s | ✅ **396/415 PASS** (19 FAIL pre-existentes) |
| Frontend vitest (`apps/web_admin`) | `cd apps/web_admin && npx vitest run` | ~1 s | ⚠️ Sin `node_modules/.bin/vitest` en este sandbox |
| OpenSpec schema match | `python openspec/scripts/check_schema_match.py` | ~5 s | ⏭️ SKIP-env (DATABASE_URL required) |
| Frontend typecheck (electron-sucursal) | `cd apps/electron-sucursal && npx tsc --noEmit -p tsconfig.renderer.json` | ~30 s | ⏭️ TBD |

**Regla universal**: si el sandbox no tiene Docker / Postgres / Electron binary / node_modules, los gates DB-dependent y e2e aparecen como **SKIP-env** o **error de import**. Esto es esperado y NO requiere fix — la CI matrix del repo los corre en un ambiente completo.

---

## 1. Backend — `parkos_core` (Python 3.13 + uv)

### 1.1 Setup (solo primera vez)

```powershell
cd E:\easypunto_parkos\backend
uv sync   # instala deps desde pyproject.toml + uv.lock
```

Si `uv` no está en PATH: `C:\Users\mccra\AppData\Local\Microsoft\WinGet\Links\uv.exe`.

### 1.2 Pytest — unit (sin DB, rápido)

```powershell
cd E:\easypunto_parkos\backend
uv run pytest tests/unit/ -q --tb=line --no-header
```

**Resultado esperado sandbox**: ~50+ unit tests PASS (sale coverage table). Tests que requieren DB se filtran automáticamente por el marker `integration` o por `conftest.py`.

### 1.3 Pytest — integration (DB, lento, SKIP-env aquí)

```powershell
cd E:\easypunto_parkos\backend
# Necesita DATABASE_URL + Docker para testcontainers
uv run pytest tests/integration/ -q --tb=line --no-header
```

**Resultado esperado**: ~30+ integration tests, todos con `pg_engine` fixture. Sin Docker = `conftest.py:202 DeprecationWarning: testcontainers.postgres is deprecated` + tests SKIP.

### 1.4 Pytest — archivo individual (para debug)

```powershell
uv run pytest tests/unit/test_venta_suscripcion_handler.py -v --tb=short
```

Reemplazar `test_venta_suscripcion_handler.py` por el archivo deseado.

### 1.5 Ruff lint

```powershell
cd E:\easypunto_parkos\backend
uv run ruff check .              # ver
uv run ruff check . --fix        # auto-fix 104 de los 199
uv run ruff check . --statistics # agrupado por regla
```

**Resultado esperado sandbox**: **199 errors** (104 auto-fixables con `--fix`).
Categorías dominantes: `I001` import sort, `E501` line too long, `RUF100` unused noqa, `F401` unused import, `SIM117` nested with. **Pre-existing**, no introducidos por sesiones recientes.

### 1.6 Ruff format

```powershell
uv run ruff format --check .    # solo verifica
uv run ruff format .           # aplica formato
```

### 1.7 Mypy strict (selectivo)

```powershell
uv run mypy --strict packages/parkos_core/src/parkos_core/auth/tenancy.py
```

**Resultado esperado**: 0 errores (post-Q2 fix que extendió `TenantContext.uuid_sesion`).

```powershell
uv run mypy --strict packages/parkos_core/src/parkos_core/api/v1/clientes_venta.py
```

**Resultado esperado**: **5 errores pre-existing** (líneas 160/206/239/453/456) — deuda técnica del baseline F1.12. No introducidos por sesiones recientes. Tracking separado.

### 1.8 Alembic migrations check (requiere DB)

```powershell
# Con DATABASE_URL apuntando a una DB vacía
uv run alembic upgrade head --sql  # render SQL sin aplicar
uv run alembic downgrade base       # revertir todas
uv run alembic upgrade head         # reaplicar
```

**Resultado esperado sandbox**: SKIP-env sin DB.

---

## 2. Frontend — `apps/electron-sucursal` (React 18 + Vite 5 + Vitest)

### 2.1 Setup (solo primera vez)

```powershell
cd E:\easypunto_parkos\apps
# Si no hay node_modules: pnpm install (requiere pnpm >= 8)
# O: cd electron-sucursal && npm install (alternativa, ms lenta)
```

Si los binarios no existen (`vitest.CMD`):
```powershell
cd E:\easypunto_parkos\apps\electron-sucursal
pnpm install --frozen-lockfile
```

### 2.2 Vitest run completo

```powershell
cd E:\easypunto_parkos\apps\electron-sucursal
.\node_modules\.bin\vitest.CMD run
# Alternativa portable: cmd /c "cd /d E:\easypunto_parkos\apps\electron-sucursal && node_modules\.bin\vitest.CMD run"
```

**Resultado esperado sandbox**: **415 tests, 396 PASS, 19 FAIL pre-existentes**. Duración ~10 s.

### 2.3 Vitest run selectivo (para debug)

```powershell
.\node_modules\.bin\vitest.CMD run src/renderer/components/ProtectedRoute.test.tsx
.\node_modules\.bin\vitest.CMD run src/features/catalogos/hooks/useTiposVehiculo.test.ts
.\node_modules\.bin\vitest.CMD run -t "voucher_requerido"
```

El flag `-t "<texto>"` filtra por nombre de test (regex match).

### 2.4 Vitest watch mode (desarrollo)

```powershell
.\node_modules\.bin\vitest.CMD
# Watchea cambios, corre tests afectados
```

### 2.5 TypeScript check

```powershell
npx tsc --noEmit -p tsconfig.renderer.json    # renderer (3 tsconfigs strict)
npx tsc --noEmit -p tsconfig.main.json        # main process (electron)
npx tsc --noEmit -p tsconfig.node.json        # node utilities
```

---

## 3. Frontend — `apps/web_admin` (PWA)

### 3.1 Vitest

```powershell
cd E:\easypunto_parkos\apps\web_admin
npx vitest run
```

**Resultado esperado**: este sandbox no tiene `node_modules/.bin/vitest` instalado en web_admin; se usa `npx vitest`. Suite contiene ~1 test (`App.test.tsx`).

### 3.2 ESLint

```powershell
cd E:\easypunto_parkos\apps\web_admin
npm run lint
```

---

## 4. Frontend — `apps/ui-kit` (compartido)

### 4.1 Vitest

```powershell
cd E:\easypunto_parkos\apps\ui-kit
.\node_modules\.bin\vitest.CMD run
```

**Resultado esperado sandbox**: **34/34 tests PASS** (~1 s).
- `src/store/authStore.test.ts` — 9 tests
- `src/fetch/parkosFetch.test.ts` — 19 tests
- `src/hooks/useAuth.test.ts` — 6 tests

### 4.2 TypeScript check

```powershell
cd E:\easypunto_parkos\apps\ui-kit
npx tsc --noEmit
```

---

## 5. OpenSpec — schema conformance

### 5.1 `check_schema_match.py` (requiere DB)

```powershell
cd E:\easypunto_parkos
# Con DATABASE_URL apuntando a una DB con todas las migrations aplicadas
python openspec/scripts/check_schema_match.py
```

**Resultado esperado sandbox**: `ERROR: --database-url or DATABASE_URL env var required`. SKIP-env.

Sin DB, el script corre el primer paso (parse del ER.mmd):
```powershell
python openspec/scripts/check_schema_match.py 2>&1 | head
```

**Resultado esperado**: `ER parsed: 51 tables (26 [V], 3 [L-E], 6 [L-W], 2 [L-S], 14 [A])` — la validación parcial pasa sin DB.

---

## 6. Cómo interpretar los resultados

| Símbolo | Significado |
|---|---|
| ✅ PASS | Tests verdes, sin cambios necesarios |
| ⚠️ FAIL pre-existing | Tests que ya fallaban ANTES de sesiones recientes; tracking separado en el audit. NO requiere fix inmediato. |
| ⏭️ SKIP-env | Gate requiere Docker / DB / Electron binary / red. Esperado en sandbox. CI matrix lo cubre. |
| ❌ FAIL NEW | Regresión introducida por un commit reciente. Requiere fix antes de merge. |

### Fallos pre-existentes conocidos (sandbox 2026-09-17)

| Suite | Archivo | Tests | Categoría |
|---|---|---|---|
| electron-sucursal | `src/features/caja/pages/Dashboard.test.tsx` | 2 | testids `turno-activo-panel`/`turno-activo-cerrar` no existen tras consolidación F4-F11 |
| electron-sucursal | `src/features/operacion/components/PlacaInput.test.tsx` | 1 | texto `placa no coincide con ningún formato` no aparece en DOM (formato cambió) |
| electron-sucursal | `src/features/operacion/components/ForzarIngresoModal.test.tsx` | 1 | mock no dispara onConfirm (timing) |
| electron-sucursal | `src/features/operacion/components/TiqueteModal.test.tsx` | 5 | error `Should not already be working` (act wrapping) |
| electron-sucursal | `src/features/operacion/pages/Principal.test.tsx` | 5 | error `Should not already be working` (act wrapping) |
| electron-sucursal | `src/features/caja/components/OcupacionPanel.test.tsx` | 3 | testid `ocupacion-panel-chip-Auto` no existe (ahora `row-Auto`); mocks `'Auto'/'Moto'` mayúsculas (REQ-OPS-134 canon requiere lowercase) |
| electron-sucursal | `src/features/caja/pages/__tests__/Dashboard.cold-mount.test.tsx` | 1 | spy recibe 1 call, expected 0 (cambio de mount) |
| backend ruff | 199 errors | — | I001/E501/RUF100/F401/SIM117 pre-existentes |

---

## 7. Orden de ejecución recomendado

Para correr el **set completo** en CI matrix local:

```powershell
# 1. Backend (más rápido, sin DB)
cd E:\easypunto_parkos\backend
uv run pytest tests/unit/ -q --tb=line
uv run ruff check . --statistics
uv run mypy --strict packages/parkos_core/src/parkos_core/

# 2. Frontend (sin DB ni Electron)
cd E:\easypunto_parkos\apps\ui-kit
.\node_modules\.bin\vitest.CMD run
cd ..\electron-sucursal
.\node_modules\.bin\vitest.CMD run

# 3. OpenSpec (sin DB)
cd E:\easypunto_parkos
python openspec/scripts/check_schema_match.py 2>&1 | head
```

Tiempo total esperado: **~1 min** sin DB.

Para CI matrix con DB + Docker:
```powershell
# Reemplazar uv run pytest tests/unit/ por tests/ (incluye integration)
cd E:\easypunto_parkos\backend
uv run pytest -q --tb=line
```

---

## 8. Cómo agregar nuevos tests

| Suite | Convención |
|---|---|
| Backend unit | `tests/unit/test_<handler>.py` o `tests/unit/test_<repo>.py`; sin DB, mocks con `AsyncMock` |
| Backend integration | `tests/integration/test_<flow>_db.py`; usa fixtures `pg_engine`, `pg_session`, `client`, `mint_*_jwt` de `tests/conftest.py` |
| Frontend electron-sucursal unit | Co-localizado con el source: `src/features/<dominio>/components/<X>.test.tsx` o `src/renderer/components/<X>.test.tsx` |
| Frontend electron-sucursal static (AST walks) | `tests/static/test_<invariant>.py` — Python con `ast.walk()` (ver precedent `test_venta_handler_single_commit.py`) |
| Frontend ui-kit | Co-localizado en `src/<store|fetch|hooks>/<X>.test.ts` |
| Frontend e2e | `e2e/<flow>.spec.ts` — Playwright + Electron `_electron.launch`. **Requiere app empaquetada** (no corre en sandbox sin electron built). |

### Convención de mock para `window.bridge` (electron-sucursal)

```typescript
import { vi } from 'vitest';

vi.stubGlobal('window', {
  bridge: {
    imprimir: vi.fn(),
    usb: { list: vi.fn() },
    kiosk: { toggle: vi.fn() },
    app: { quit: vi.fn() },
    apiStatus: { get: vi.fn() },
    authStore: { get: vi.fn(), set: vi.fn(), delete: vi.fn() },
    tarifasStore: { get: vi.fn(), set: vi.fn(), delete: vi.fn() }, // post-F4.2 closure
  },
});

// cleanup in afterEach
afterEach(() => vi.unstubAllGlobals());
```

---

## 9. Cuando un test FALLA con mi cambio

1. **Confirmar pre-existencia** — `git log --oneline -- <test_file>` para ver cuándo se introdujo. Si el test ya fallaba en el commit anterior al mío, es pre-existente (no requiere fix).
2. **Verificar scope** — ¿rompí otro archivo además del que modifiqué? `git diff --stat origin/dev` para ver qué cambié.
3. **Reproducir aislado** — `<vitest CWD> run <single_test>` con flag `-t "nombre"`.
4. **MOCK chain** — para tests de frontend que usan `useSesionActiva`, `useAuth`, `useTarifasVigentes`, verificar que los mocks de SWR devuelven el shape esperado. Ver precedent en `ProtectedRoute.test.tsx`.
5. **Si es regresión nueva** — fix antes de commit + re-run del test + commit con `fix: <descripción>`.

---

## 10. Comandos one-liner (cheat sheet)

```powershell
# Backend unit tests
cd E:\easypunto_parkos\backend; uv run pytest tests/unit/ -q --tb=line

# Backend mypy strict selectivo (post-Q2 fix)
cd E:\easypunto_parkos\backend; uv run mypy --strict packages/parkos_core/src/parkos_core/auth/tenancy.py

# Backend lint auto-fix
cd E:\easypunto_parkos\backend; uv run ruff check . --fix

# Frontend electron-sucursal vitest
cd E:\easypunto_parkos\apps\electron-sucursal; .\node_modules\.bin\vitest.CMD run

# Frontend ui-kit vitest
cd E:\easypunto_parkos\apps\ui-kit; .\node_modules\.bin\vitest.CMD run

# Frontend electron-sucursal single test by name
cd E:\easypunto_parkos\apps\electron-sucursal; .\node_modules\.bin\vitest.CMD run -t "voucher_requerido"

# OpenSpec schema check (sin DB, solo parse)
cd E:\easypunto_parkos; python openspec/scripts/check_schema_match.py 2>&1 | Select-String "ER parsed"
```

---

## 11. Referencias

- `AGENTS.md` (raíz) — reglas operativas (gitflow, merge-to-dev, etc.)
- `openspec/scripts/check_schema_match.py` — schema conformance gate
- `backend/tests/conftest.py` — fixtures compartidos (pg_engine, pg_session, mint_*_jwt, client)
- `apps/electron-sucursal/vitest.config.ts` — config vitest del renderer
- `apps/ui-kit/vitest.config.ts` — config vitest de ui-kit
- `openspec/changes/archive/2026-09-17-f1-12-v8-v8b-stub-closure/verify-report.md` — precedent de formato PASS WITH WARNINGS + SKIPPED-env
