# Diseño técnico — HU-F2.2 Cliente HTTP parkosFetch + IPC bridge + authStore

> **Change**: `hu-f2-2-parkos-fetch-ipc-auth-store` · **Folder**: `openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store/`
> **Phase**: design (sdd-design) · **Status**: ready for `sdd-tasks`
> **HU ID**: HU-F2.2 (Fase 2 — capa de infraestructura HTTP/IPC/authStore; transversal, primera HU con HTTP behavior contract)
> **Working dir**: `E:/easypunto_parkos` · **Branch**: `feat/fase-2-electron-scaffold` (HEAD `5bdf857`, F2.1 archivado 2026-09-15)
> **Inputs**: `proposal.md` (16 secciones, 8 DEC-FETCH-NN, ~770 LOC), `exploration.md` (17 secciones, 8 DEC-FETCH-NN, 7 tasks T1..T7, ~870 LOC), `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/design.md` (16 secciones + 2 apéndices, ~1100 LOC — referencia de estructura clonada verbatim).
> **Language**: español neutro profesional · **Conventional commits**: feat(ui-kit) / feat(electron) / test(electron) — sin Co-authored-by.

---

## 0. Metadata

| Campo | Valor |
|---|---|
| **HU ID** | HU-F2.2 |
| **Fase** | 2 (Andamiaje Electron + Capa de Infraestructura HTTP/IPC/authStore) |
| **Change name** | `hu-f2-2-parkos-fetch-ipc-auth-store` |
| **Folder** | `openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store/` |
| **State** | design ready |
| **Branch** | `feat/fase-2-electron-scaffold` |
| **PR target** | `origin/dev` |
| **Author** | Parkos Dev |
| **Date** | 2026-09-15 |
| **Phase precedente** | sdd-propose (proposal.md) + sdd-explore (exploration.md) |
| **Próximo phase** | sdd-tasks (tras sdd-spec también listo) |
| **Language** | español neutro profesional |
| **Conventional commits** | feat(ui-kit) / feat(electron) / test(electron) — sin Co-authored-by |
| **LOC target** | ~440 producción + ~410 tests = ~850 LOC total |

---

## 1. Visión general y objetivos

### 1.1 Objetivo primario

Definir la arquitectura técnica HOW de las tres primitives de infraestructura transversal que F2.2 entrega:

1. **`parkosFetch`** — wrapper único `fetch` extendido (retry 5xx + refresh-once 401 + Idempotency-Key SHA-256 + Zod validation + AbortController timeout) ubicado en `apps/ui-kit/src/fetch/parkosFetch.ts` y consumido por `web_admin` (re-exporter) + `electron-sucursal` (renderer).
2. **Bridge IPC tipado** — `apps/electron-sucursal/electron/bridge.d.ts` con `BridgeSurface` interface (8 métodos en 6 grupos) + `preload.ts` con whitelist explícita.
3. **`authStore` Zustand + `useAuth()` SWR** — store con `persist` middleware contra `electron-store` (path `app.getPath('userData')/auth.json`) + hook que hidrata desde `/auth/me` cada 5 minutos.

Estas tres primitives desbloquean **11 HUs downstream** (F3.1 login UI, F3.2 lockout visible, F3.3 turno, IT-3..IT-10 vehículo/factura/caja/anulación/alerta/reimpresión/cliente) que las consumirán sin renegociar el contrato HTTP.

### 1.2 Objetivos secundarios

- **Defense in depth XR6**: 5 capas activas (auth HTTP + engineering TS strict + a11y axe-core + contract Zod + retry-budget timeout + refresh-once Mutex).
- **DRY cross-app**: una sola implementación de `parkosFetch` consumida por web_admin y electron-sucursal vía `@parkos/ui-kit/fetch` workspace package.
- **Tipado end-to-end**: `bridge.d.ts` previene drift entre main process y renderer; `tsc --noEmit` lo enforce en CI.
- **Persistencia robusta para kiosko**: electron-store sobrevive DevTools reset + OS storage clear + profile corruption (vs. localStorage frágil).
- **Cobertura >90%** en `parkosFetch.ts` y >80% en `authStore.ts` + `useAuth.ts` (vitest --coverage threshold).
- **TDD estricto**: cada test escrito ANTES de la implementación; 8 acceptance gates (G1..G8) deben pasar antes de merge.

### 1.3 No-objetivos (cross-ref exploration §13)

- Backend `/health` endpoint — F2.3 lo crea (consumer de `bridge.apiStatus.get()`).
- Generación automática de Zod schemas desde Pydantic — deferred Fase 3.
- Refresh-token rotation detection — PR1b no rota; F2.2 trata refresh token como long-lived.
- Multi-tab login UI — kiosko single-tab por F2.3 single-instance lock.
- 2FA / WebAuthn — futuro.
- Login UI (F3.1), Lockout UI (F3.2), Turno (F3.3), Auto-update (F2.3), Single-instance lock (F2.3), Kiosko mode PIN (F2.3), Logging electron-log (F2.3) — todas deferidas.
- Handlers reales del main process para `print:ticket`, `usb:list`, `kiosk:toggle` — F2.3 los conecta.
- Backend migrations, nuevas tablas, nuevos permisos — F2.2 es consumer-only.

---

## 2. Arquitectura y patrones

### 2.1 Vista de capas (ASCII)

```
┌─────────────────────────────── Renderer (React 18, Vite 5) ──────────────────────────────┐
│                                                                                          │
│   ┌─────────────────┐   HTTP    ┌─────────────────┐                                       │
│   │ parkosFetch<T>  │──────────►│ useAuthStore()  │                                       │
│   │ (apps/ui-kit)   │           │ (Zustand+persist)│                                       │
│   └────────┬────────┘           └────────┬────────┘                                       │
│            │                             │                                                │
│            │                             │                                                │
│   ┌────────▼────────┐           ┌────────▼────────┐                                        │
│   │ parkosFetchRaw  │           │ electronStore   │                                        │
│   │  - headers      │           │ Adapter (Zustand│                                        │
│   │  - retry loop   │           │  createJSON     │                                        │
│   │  - mutex 401    │           │  Storage)       │                                        │
│   │  - idempotency  │           └────────┬────────┘                                        │
│   │  - zod schema   │                    │                                                 │
│   │  - abort ctrl   │   IPC invoke       │                                                 │
│   └────────┬────────┘────────────┐       │                                                 │
│            │                     │       │                                                 │
│   ┌────────▼────────┐  ┌────────▼───────▼────────┐                                         │
│   │ useAuth()       │  │ window.bridge           │                                         │
│   │ useSWR('/auth/me')│ │   .imprimir            │                                         │
│   │ refreshInterval │  │   .usb.list            │                                         │
│   │ 5 * 60 * 1000   │  │   .kiosk.toggle        │                                         │
│   └─────────────────┘  │   .app.quit            │                                         │
│                        │   .apiStatus.get        │                                         │
│                        │   .authStore.{get,set, │                                         │
│                        │     delete}             │                                         │
│                        └────────────┬────────────┘                                         │
└─────────────────────────────────────┼──────────────────────────────────────────────────────┘
                                      │ contextBridge.exposeInMainWorld('bridge', ...)
                                      │ (whitelist explicita, NO spread)
                                      ▼
┌─────────────────────────────── Main Process (Electron 30) ──────────────────────────────┐
│                                                                                          │
│   ipcMain.handle('auth-store:get'  , ...) ──► electron-store (app.getPath('userData'))  │
│   ipcMain.handle('auth-store:set'  , ...)        ↓                                       │
│   ipcMain.handle('auth-store:delete', ...)     /auth.json                                │
│                                                                                          │
│   ipcMain.handle('print:ticket'    , ...) ──► STUB (F2.3 conecta escpos-usb)             │
│   ipcMain.handle('usb:list'        , ...) ──► STUB (F2.3 conecta usb detection)          │
│   ipcMain.handle('kiosk:toggle'    , ...) ──► STUB (F2.3 conecta single-instance lock)   │
│   ipcMain.handle('app:quit'        , ...) ──► app.quit() (real en F2.3)                  │
│   ipcMain.handle('api:status'      , ...) ──► STUB (F2.3 conecta /health)                │
│                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │ HTTPS
                                      ▼
                         ┌──────────────────────────┐
                         │ Backend FastAPI          │
                         │ http://127.0.0.1:8000    │
                         │ /api/v1/auth/{login,     │
                         │   refresh, logout, me}   │
                         └──────────────────────────┘
```

### 2.2 Patrón de fetch wrapper

**Patrón**: Decorador sobre `fetch` nativo que orquesta headers + retry + refresh + idempotency + timeout + zod en una sola función.

```typescript
// pipeline interno (simplificado)
async function parkosFetch<T>(input, init, schema?) {
  const finalInit = await buildInit(input, init);   // (1) inject headers
  const res = await parkosFetchRaw(input, finalInit); // (2) retry+refresh loop
  if (!res.ok) throw new ParkosHttpError(res.status, await res.text());
  const json = await res.json();
  return schema ? schema.parse(json) : (json as T);   // (3) zod boundary
}
```

**Por qué wrapper y no interceptor**: React Query / axios interceptors añaden una capa global implícita que oculta el orden de operaciones. Wrapper explícito en cada callsite facilita testing (MSW mockea `fetch` global, no el wrapper) y debugging (un solo stack trace).

### 2.3 Patrón de Mutex singleton para refresh

**Patrón**: variable módulo-level `refreshPromise: Promise<string|null> | null` que actúa como slot singleton.

```typescript
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;          // (a) ya hay uno en curso → esperar
  refreshPromise = doRefresh().finally(() => {
    refreshPromise = null;                            // (b) limpiar slot al terminar
  });
  return refreshPromise;
}
```

**Garantías**:
- 5 requests concurrentes con 401 disparan **UN** solo `POST /auth/refresh`.
- Las otras 4 esperan el resultado del singleton y reintentan con el nuevo access token.
- Si refresh 401, `refreshPromise` resuelve a `null` y cada caller propaga el error independientemente.

**Por qué módulo-level y no Zustand state**: el Mutex debe sobrevivir entre renders React (no re-inicializarse en cada mount). Zustand es para estado compartido entre componentes; Mutex es para serializar side-effects dentro de un módulo.

### 2.4 Patrón de Zustand persist con storage custom

**Patrón**: Zustand `persist` middleware con `createJSONStorage(() => electronStoreAdapter)`.

```typescript
const electronStore = {
  getItem:    async (key)       => window.bridge.authStore.get(key),
  setItem:    async (key, value) => window.bridge.authStore.set(key, value),
  removeItem: async (key)        => window.bridge.authStore.delete(key),
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({ /* ... */ }),
    {
      name: 'parkos.auth',
      storage: createJSONStorage(() => electronStore),
      partialize: (state) => ({ /* solo tokens */ }),
    }
  )
);
```

**Adapter pattern**: Zustand `persist` espera una API tipo `Storage` (`getItem`/`setItem`/`removeItem`). El adapter envuelve el bridge IPC en esa API. **Por qué adapter y no `electron-store` directo**: electron-store corre en main process; el renderer no puede importarlo directamente (contextIsolation=true + nodeIntegration=false). El bridge IPC es el único canal legítimo.

**`partialize` whitelist**: Zustand guarda TODO el state por default; `partialize` filtra explícitamente qué campos persisten. Solo `{accessToken, refreshToken, expiresAt}` cruzan la frontera al filesystem; `user`, `permisos`, `sucursal` viven en SWR cache y se rehidratan vía `/auth/me`.

---

## 3. parkosFetch — diseño detallado

### 3.1 API surface (signature TypeScript)

```typescript
// apps/ui-kit/src/fetch/parkosFetch.ts

import type { z } from 'zod';

export interface ParkosFetchInit extends Omit<RequestInit, 'signal'> {
  /** Timeout en ms. Default 30_000. AbortController dispara AbortError. */
  timeoutMs?: number;
  /** Override del AbortController (útil para tests con vi.useFakeTimers). */
  signal?: AbortSignal;
  /** Skip Idempotency-Key (default false; auto true para POST /auth/login). */
  skipIdempotencyKey?: boolean;
}

export class ParkosHttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    public readonly url: string,
  ) {
    super(`parkosFetch ${status} ${url}: ${body.slice(0, 200)}`);
    this.name = 'ParkosHttpError';
  }
}

/** Raw — retorna Response (permite callers inspeccionar status antes de parsear). */
export async function parkosFetchRaw(
  input: RequestInfo | URL,
  init?: ParkosFetchInit,
): Promise<Response>;

/** Typed — parsea JSON y valida opcionalmente con Zod schema. */
export async function parkosFetch<T>(
  input: RequestInfo | URL,
  init?: ParkosFetchInit,
  schema?: z.ZodType<T>,
): Promise<T>;
```

### 3.2 Header injection pipeline (orden: auth → X-Sucursal → Idempotency-Key)

```typescript
// dentro de buildInit(input, init) — pseudocódigo
async function buildInit(input: RequestInfo | URL, init: ParkosFetchInit): Promise<RequestInit> {
  const headers = new Headers(init?.headers);
  const url = typeof input === 'string' ? input : input.toString();
  const method = (init?.method ?? 'GET').toUpperCase();

  // (1) Authorization Bearer desde authStore (NO localStorage)
  const { accessToken } = useAuthStore.getState();
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  // (2) X-Sucursal-Context (idéntico a F2.1 behaviour — getSucursalHeader)
  const sucursalHeader = getSucursalHeader(); // apps/web_admin/src/lib/sucursal-context.ts
  if (sucursalHeader) {
    headers.set('X-Sucursal-Context', sucursalHeader);
  }

  // (3) Idempotency-Key para mutacionales (skip para /auth/login)
  const isMutational = ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method);
  if (isMutational && !init?.skipIdempotencyKey && !url.endsWith('/auth/login')) {
    headers.set('Idempotency-Key', await idempotencyKey(method, url, init?.body));
  }

  // (4) Content-Type default si body y no header
  if (init?.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  return { ...init, headers };
}
```

**Orden importa**: `Authorization` primero (antes de idempotency) garantiza que un refresh concurrente no invalide la key. `X-Sucursal-Context` después (header de contexto, no de auth). `Idempotency-Key` último (depende de method+url+body finales).

### 3.3 Retry loop (mockup TypeScript con delay(ms))

```typescript
const BACKOFF_MS = [300, 600, 1200] as const;

async function parkosFetchRaw(
  input: RequestInfo | URL,
  init?: ParkosFetchInit,
  attempt = 1,
): Promise<Response> {
  const finalInit = await buildInit(input, init);
  const controller = new AbortController();
  const timeoutId = setTimeout(
    () => controller.abort(new Error('parkosFetch timeout')),
    init?.timeoutMs ?? 30_000,
  );

  try {
    const res = await fetch(input, { ...finalInit, signal: controller.signal });

    // Caso 1: 2xx/3xx → retornar inmediatamente
    if (res.ok) return res;

    // Caso 2: 4xx no-retry (excepto 408)
    if (res.status >= 400 && res.status < 500 && res.status !== 408) {
      if (res.status === 401) return handle401(input, init, res, attempt);
      return res;
    }

    // Caso 3: 5xx o 408 → retry si quedan intentos
    if (attempt >= 3) return res;
    await delay(BACKOFF_MS[attempt - 1]!);
    return parkosFetchRaw(input, init, attempt + 1);
  } catch (err) {
    // NetworkError o AbortError → retry si quedan intentos
    if (attempt >= 3) throw err;
    await delay(BACKOFF_MS[attempt - 1]!);
    return parkosFetchRaw(input, init, attempt + 1);
  } finally {
    clearTimeout(timeoutId);
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
```

**Notas críticas**:
- `attempt >= 3` → máximo 3 intentos totales (1 inicial + 2 retries). Cobertura: `parkosFetch.test.ts` con `vi.useFakeTimers({ shouldAdvanceTime: true })`.
- `NetworkError` (fetch threw) se trata igual que 5xx — ambos son transitorios.
- 408 (Request Timeout) sí reintenta — es timeout del server, no del cliente.
- 401 NO es caso de retry simple — va por `handle401` (refresh-once).

### 3.4 401 refresh-once con Mutex (mockup TypeScript con refreshPromise)

```typescript
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;          // (a) singleton slot
  refreshPromise = (async () => {
    try {
      const { refreshToken } = useAuthStore.getState();
      if (!refreshToken) return null;
      const res = await fetch('/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const pair: TokenPair = await res.json();
      useAuthStore.getState().setTokens(
        pair.access_token,
        pair.refresh_token,
        pair.expires_in,
      );
      return pair.access_token;
    } catch {
      return null;
    } finally {
      refreshPromise = null;                         // (b) liberar slot
    }
  })();
  return refreshPromise;
}

async function handle401(
  input: RequestInfo | URL,
  init: ParkosFetchInit | undefined,
  res: Response,
  attempt: number,
): Promise<Response> {
  // Solo UN refresh-once por cadena de parkosFetchRaw
  if (attempt > 1) return res;
  const newToken = await refreshAccessToken();
  if (!newToken) {
    // Refresh falló → clear authStore + emitir evento para redirect
    useAuthStore.getState().clear();
    window.dispatchEvent(new CustomEvent('parkos:auth:cleared'));
    return res;
  }
  // Refresh OK → reintentar request original con nuevo token (UNA vez)
  return parkosFetchRaw(input, init, attempt + 1);
}
```

**Garantías (cross-ref DEC-FETCH-03 + exploration §8 R1)**:
- `attempt > 1` previene **doble-401**: si el retry tras refresh también devuelve 401, propaga sin re-intentar refresh.
- `refreshPromise` singleton previene **stampede**: N requests concurrentes con 401 disparan UN solo refresh.
- `window.dispatchEvent('parkos:auth:cleared')` notifica al router (F3.1 implementa el listener para `redirect('/login?next=<path>')`).

### 3.5 Idempotency-Key SHA-256 (mockup con crypto.subtle)

```typescript
async function idempotencyKey(
  method: string,
  url: string,
  body: unknown,
): Promise<string> {
  const enc = new TextEncoder();
  const payload = enc.encode(
    `${method.toUpperCase()}|${url}|${JSON.stringify(body ?? null)}`,
  );
  const hash = await crypto.subtle.digest('SHA-256', payload);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
```

**Por qué SHA-256 y no uuid v4** (cross-ref DEC-FETCH-04 + exploration §4.3):
- **Determinismo**: dos requests idénticos (mismo método+ruta+cuerpo) producen la MISMA key. El backend puede deduplicar retries sin doble-ejecutar.
- **Estándar W3C**: `crypto.subtle.digest` está disponible en renderer Electron (nodeIntegration=false + contextIsolation=true pero `window.crypto.subtle` se expone por V8).
- **EXCEPCIÓN**: `POST /auth/login` NO lleva Idempotency-Key — es idempotente por naturaleza (bcrypt determinístico + UNIQUE constraint en `prod.login`).

### 3.6 Zod validation (mockup con schema.parse)

```typescript
export async function parkosFetch<T>(
  input: RequestInfo | URL,
  init?: ParkosFetchInit,
  schema?: z.ZodType<T>,
): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) {
    throw new ParkosHttpError(res.status, await res.text(), String(input));
  }
  const json = await res.json();
  if (schema) return schema.parse(json);   // throws ZodError si falla
  return json as T;
}
```

**Uso en callsite**:
```typescript
import { z } from 'zod';
const SucursalesResponse = z.object({
  sucursales_permitidas: z.array(SucursalItemSchema),
});
const data = await parkosFetch('/auth/me', {}, SucursalesResponse);
```

**Por qué Zod y no TypeScript types solos** (cross-ref DEC-FETCH-05):
- TS types se borran en compilación — no validan runtime.
- Zod validation catches drift backend/frontend en dev/test antes de llegar a producción.
- Auto-gen Zod desde Pydantic via `datamodel-code-generator` — DEFERRED Fase 3.

### 3.7 ParkosHttpError class

```typescript
export class ParkosHttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: string,
    public readonly url: string,
  ) {
    super(`parkosFetch ${status} ${url}: ${body.slice(0, 200)}`);
    this.name = 'ParkosHttpError';
  }
}
```

**Por qué custom error class**:
- `instanceof ParkosHttpError` permite a callers discriminar (`if (err instanceof ParkosHttpError && err.status === 429)`).
- `body` preserva el response body raw para logging/debugging.
- `url` permite correlation con telemetry sin parsear stack traces.

---

## 4. authStore Zustand — diseño detallado

### 4.1 Schema del estado

```typescript
// apps/ui-kit/src/store/authStore.ts

export interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: string | null;   // ISO 8601 UTC

  setTokens: (access: string, refresh: string, expiresIn: number) => void;
  clear: () => void;
}
```

**Invariantes**:
- `accessToken === null` ↔ `refreshToken === null` ↔ `expiresAt === null` (atomic clear).
- `expiresAt` se deriva de `Date.now() + expiresIn * 1000` en `setTokens` (no se persiste `expiresIn` raw porque es absoluto).
- Sin campo `user` / `permisos` — esos viven en SWR cache (cross-ref DEC-FETCH-07).

### 4.2 electronStoreAdapter (mockup con window.bridge.authStore)

```typescript
import { create } from 'zustand';
import { persist, createJSONStorage, type StateStorage } from 'zustand/middleware';

const electronStore: StateStorage = {
  getItem: async (key: string) => {
    const value = await window.bridge.authStore.get(key);
    return value ?? null;
  },
  setItem: async (key: string, value: string) => {
    await window.bridge.authStore.set(key, value);
  },
  removeItem: async (key: string) => {
    await window.bridge.authStore.delete(key);
  },
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      expiresAt: null,

      setTokens: (access, refresh, expiresIn) => {
        const expiresAt = new Date(Date.now() + expiresIn * 1000).toISOString();
        set({ accessToken: access, refreshToken: refresh, expiresAt });
      },

      clear: () => {
        set({ accessToken: null, refreshToken: null, expiresAt: null });
      },
    }),
    {
      name: 'parkos.auth',
      storage: createJSONStorage(() => electronStore),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        expiresAt: state.expiresAt,
      }),
      version: 1,
    },
  ),
);
```

**Notas críticas**:
- `window.bridge.authStore.get/set/delete` son async → `StateStorage` API de Zustand 4.x los acepta nativamente (retorna `Promise<string|null>`).
- `version: 1` para que futuras migraciones de shape usen `migrate` callback (cross-ref Fase 3).
- `partialize` retorna solo los 3 campos token — excluye funciones (set/clear) y derivados.

### 4.3 partialize whitelist

```typescript
partialize: (state) => ({
  accessToken: state.accessToken,
  refreshToken: state.refreshToken,
  expiresAt: state.expiresAt,
})
```

**Por qué whitelist explícita** (no persist todo):
- Zustand `persist` por default guarda TODO el state. Funciones y objetos derivados se serializarían innecesariamente.
- Whitelist explicita previene drift: si alguien agrega `user: UserItem` al state sin actualizar `partialize`, NO se persiste (fail-safe).
- Cross-ref DEC-FETCH-06 + exploration §2.3 R-AUTH-* + R-FETCH-4 mitigation.

### 4.4 clear() chain (logout + doble-401)

```typescript
clear: () => {
  set({ accessToken: null, refreshToken: null, expiresAt: null });
}
```

**Callsites de `clear()`**:
1. **Logout handler** (F3.1+) — `parkosFetch('/auth/logout', { method: 'POST' })` → `useAuthStore.getState().clear()`.
2. **Doble-401 fallido** (parkosFetch.ts §3.4) — refresh-once 401 → `clear()` + `window.dispatchEvent('parkos:auth:cleared')`.
3. **Expiración natural** (forward hook Fase 3) — interval check `expiresAt < Date.now()`.

**Event `parkos:auth:cleared`**:
- CustomEvent en `window` para que el router de la SPA lo intercepte.
- F3.1 implementa listener: `router.navigate('/login?next=' + encodeURIComponent(location.pathname))`.

---

## 5. useAuth() SWR hook — diseño detallado

### 5.1 Contrato retornado ({user, sucursal, sucursalesPermitidas, permisos, expiresAt, isAuthenticated, isLoading, error, refresh})

```typescript
// apps/ui-kit/src/hooks/useAuth.ts

import useSWR from 'swr';
import { useAuthStore } from '../store/authStore';
import { parkosFetch } from '../fetch/parkosFetch';
import type { AuthMeResponse } from '../schemas/auth';

export interface UseAuthReturn {
  user: UserItem | null;
  sucursal: SucursalItem | null;
  sucursalesPermitidas: SucursalItem[];
  permisos: string[];
  expiresAt: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<AuthMeResponse | undefined>;
}

export function useAuth(): UseAuthReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const { data, error, isLoading, mutate } = useSWR<AuthMeResponse>(
    accessToken ? '/auth/me' : null,            // key null cuando !accessToken
    parkosFetch,
    {
      refreshInterval: 5 * 60 * 1000,          // 5 min — plan.md:1208 verbatim
      revalidateOnFocus: true,
      shouldRetryOnError: (err) =>
        !(err instanceof ParkosHttpError && err.status === 401),
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          window.dispatchEvent(new CustomEvent('parkos:auth:cleared'));
        }
      },
    },
  );

  return {
    user: data?.user ?? null,
    sucursal: data?.sucursal ?? null,
    sucursalesPermitidas: data?.sucursales_permitidas ?? [],
    permisos: data?.permisos ?? [],
    expiresAt: data?.expires_at ?? null,
    isAuthenticated: !!accessToken,
    isLoading,
    error,
    refresh: mutate,
  };
}
```

### 5.2 SWR config (key null cuando !accessToken, refreshInterval 5min, onError 401 → clear)

| Config | Valor | Razón |
|---|---|---|
| `key` | `accessToken ? '/auth/me' : null` | SWR no fetchea cuando key es null. Cuando no hay token, retorna `isAuthenticated:false` sin request. |
| `fetcher` | `parkosFetch` | Reusa wrapper centralizado (retry/refresh/idempotency/Zod). |
| `refreshInterval` | `5 * 60 * 1000` | 5 min verbatim per `plan.md:1208`. Balance entre freshness y bandwidth. |
| `revalidateOnFocus` | `true` | Cuando el renderer vuelve a foreground, revalida (útil tras kiosk idle). |
| `shouldRetryOnError` | `(err) => !(err instanceof ParkosHttpError && err.status === 401)` | 401 NO retry — significa refresh falló; ya está manejado por `onError`. |
| `onError` | `(err) => { if (401) clear() }` | Doble-cinturón: si 401 escapa del retry de parkosFetch, limpia store aquí. |

### 5.3 Mutex pattern inheritance

`useAuth()` **NO** implementa Mutex propio — hereda el Mutex de `parkosFetch` (DEC-FETCH-03). El SWR hook solo configura; la lógica de refresh vive en `parkosFetch.refreshAccessToken()`. Esto evita duplicación de la lógica crítica de concurrencia.

**Inheritance chain**:
```
useAuth() → SWR → parkosFetch (wrapped) → parkosFetchRaw → handle401 → refreshAccessToken (Mutex)
```

Cualquier request que `/auth/me` (u otro endpoint protegido) haga con 401 pasa por la misma lógica Mutex. Garantía: **un solo refresh activo en toda la app**, sin importar cuántos componentes monten `useAuth()`.

---

## 6. Bridge IPC — diseño detallado

### 6.1 BridgeSurface interface completa (cross-ref exploration §5.3)

```typescript
// apps/electron-sucursal/electron/bridge.d.ts

export interface PrintPayload {
  ticketId: string;
  lines: Array<{ text: string; bold?: boolean; align?: 'left' | 'center' | 'right' }>;
  cut: boolean;
  cashDrawer?: boolean;
}

export interface USBDevice {
  vendorId: number;
  productId: number;
  productName: string | null;
  serialNumber: string | null;
}

export interface ApiStatus {
  online: boolean;
  lastSync: string | null;  // ISO 8601 UTC
}

export interface BridgeSurface {
  /** Imprime ticket en impresora térmica USB (escpos-usb). F5.1+ consumer. */
  imprimir(payload: PrintPayload): Promise<{ ok: boolean }>;

  usb: {
    /** Lista dispositivos USB conectados. F5.1+ consumer. */
    list(): Promise<USBDevice[]>;
  };

  kiosk: {
    /** Habilita/deshabilita kiosko mode. F2.3 consumer. */
    toggle(on: boolean): void;
  };

  app: {
    /** Cierra la app. F2.3 consumer (logout cleanup). */
    quit(): void;
  };

  apiStatus: {
    /** Health check del backend (ping /health). F11.x consumer. */
    get(): Promise<ApiStatus>;
  };

  authStore: {
    /** electron-store read. F2.2 authStore consumer. */
    get(key: string): Promise<string | null>;
    /** electron-store write. F2.2 authStore consumer. */
    set(key: string, value: string): Promise<void>;
    /** electron-store delete. F2.2 authStore consumer. */
    delete(key: string): Promise<void>;
  };
}

declare global {
  interface Window {
    bridge: BridgeSurface;
  }
}
```

### 6.2 Preload whitelist (cada método declarado, NO spread)

```typescript
// apps/electron-sucursal/electron/preload.ts

import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('bridge', {
  imprimir: (payload) => ipcRenderer.invoke('print:ticket', payload),
  usb: { list: () => ipcRenderer.invoke('usb:list') },
  kiosk: { toggle: (on) => ipcRenderer.send('kiosk:toggle', on) },
  app: { quit: () => ipcRenderer.send('app:quit') },
  apiStatus: { get: () => ipcRenderer.invoke('api:status') },
  authStore: {
    get: (key) => ipcRenderer.invoke('auth-store:get', key),
    set: (key, value) => ipcRenderer.invoke('auth-store:set', key, value),
    delete: (key) => ipcRenderer.invoke('auth-store:delete', key),
  },
});
```

**Crítico — NO spread**:
```typescript
// MAL — expone TODO ipcRenderer
contextBridge.exposeInMainWorld('bridge', { ...ipcRenderer });

// BIEN — whitelist explícita
contextBridge.exposeInMainWorld('bridge', {
  imprimir: (payload) => ipcRenderer.invoke('print:ticket', payload),
  // ...cada método declarado
});
```

El spread filtraría el renderer a TODO lo que ofrece Electron — anti-pattern de seguridad. Whitelist explícita es auditable y revisa-able en code review.

### 6.3 Triple-slash reference

```typescript
// apps/electron-sucursal/src/renderer/global.d.ts

/// <reference types="../../electron/bridge.d.ts" />

// Permite que en renderer (TS) window.bridge.imprimir() autocomplete correctamente
```

`tsconfig.renderer.json` (F2.1 ya configurado) incluye `src/renderer/global.d.ts` automáticamente. El triple-slash reference importa los tipos de `bridge.d.ts` sin runtime overhead — solo tsc lo lee.

### 6.4 IPC channel naming convention (`<group>:<method>`)

| Channel | Dirección | Bridge method | Handler real (F2.3) |
|---|---|---|---|
| `print:ticket` | renderer → main (invoke) | `bridge.imprimir(payload)` | `ipcMain.handle('print:ticket', escposUsbHandler)` |
| `usb:list` | renderer → main (invoke) | `bridge.usb.list()` | `ipcMain.handle('usb:list', listUsbDevices)` |
| `kiosk:toggle` | renderer → main (send, fire-and-forget) | `bridge.kiosk.toggle(on)` | `ipcMain.on('kiosk:toggle', setKioskMode)` |
| `app:quit` | renderer → main (send) | `bridge.app.quit()` | `ipcMain.on('app:quit', () => app.quit())` |
| `api:status` | renderer → main (invoke) | `bridge.apiStatus.get()` | `ipcMain.handle('api:status', pingHealth)` |
| `auth-store:get` | renderer → main (invoke) | `bridge.authStore.get(key)` | `ipcMain.handle('auth-store:get', electronStore.get)` |
| `auth-store:set` | renderer → main (invoke) | `bridge.authStore.set(key, value)` | `ipcMain.handle('auth-store:set', electronStore.set)` |
| `auth-store:delete` | renderer → main (invoke) | `bridge.authStore.delete(key)` | `ipcMain.handle('auth-store:delete', electronStore.delete)` |

**Convención**: `<group>:<method>` con `:` separador. `group` ∈ {print, usb, kiosk, app, api, auth-store}. Permite grep cross-cutting: `grep -r "auth-store:" electron/` lista todos los handlers+invokes de auth-store.

**Handlers reales NO se implementan en F2.2** — F2.3 los conecta vía HU-F2.3-T5.

---

## 7. Testing strategy

### 7.1 Unit (Vitest + MSW) — 14+8+5 escenarios

**`apps/ui-kit/src/fetch/parkosFetch.test.ts`** (14 escenarios MSW):

| # | Escenario | Aserción clave |
|---|---|---|
| U1 | Bearer header injection desde authStore | `expect(req.headers.get('Authorization')).toBe('Bearer xxx')` |
| U2 | X-Sucursal-Context header (F2.1 behaviour) | `expect(req.headers.get('X-Sucursal-Context')).toBe('<uuid>')` |
| U3 | Retry 5xx (500) con backoff 300/600/1200ms | 3 llamadas a MSW, timing verificado con `vi.useFakeTimers({ shouldAdvanceTime: true })` |
| U4 | Retry 408 (Request Timeout) | 3 llamadas, backoff igual |
| U5 | NO retry 4xx (400/403/404) | 1 sola llamada, retorna Response directo |
| U6 | NetworkError → retry | mock `fetch` rejects 2 veces, succeeds 3ra |
| U7 | 401 refresh-once → retry con nuevo token | 1 refresh + 1 retry, MSW valida segundo Bearer header |
| U8 | 401 refresh-fail → clear + evento | `expect(window.dispatchEvent).toHaveBeenCalledWith('parkos:auth:cleared')` |
| U9 | Mutex concurrency: 5 requests 401 disparan 1 refresh | 1 sola llamada a `/auth/refresh` |
| U10 | Idempotency-Key SHA-256 en POST mutacionales | hash computed + header assertion |
| U11 | Idempotency-Key skip en POST /auth/login | header `Idempotency-Key` ausente |
| U12 | Timeout AbortController dispara | `vi.advanceTimersByTime(30_000)` → AbortError thrown |
| U13 | Zod schema pass | `schema.parse` retorna data typed |
| U14 | Zod schema fail lanza ZodError | `expect(() => ...).toThrow(ZodError)` |

**`apps/ui-kit/src/store/authStore.test.ts`** (8 escenarios):

| # | Escenario |
|---|---|
| A1 | Initial state vacío |
| A2 | `setTokens` actualiza state + deriva `expiresAt` ISO 8601 |
| A3 | `getState` restaura desde electron-store (mock bridge.authStore.get) |
| A4 | `clear()` borra state + invoca bridge.authStore.delete |
| A5 | `partialize` excluye funciones y derivados |
| A6 | Mutex refresh dedupe (mockea `refreshAccessToken`, 5 calls concurrentes → 1 POST /auth/refresh) |
| A7 | Refresh fail limpia state + emite `parkos:auth:cleared` |
| A8 | Expiración validada en read (`expiresAt < Date.now()` → tratar como null) |

**`apps/ui-kit/src/hooks/useAuth.test.ts`** (5 escenarios):

| # | Escenario |
|---|---|
| H1 | Sin `accessToken` retorna `isAuthenticated:false` sin fetch |
| H2 | Con `accessToken` hidrata `/auth/me` |
| H3 | `refreshInterval: 5 * 60 * 1000` verbatim |
| H4 | `revalidateOnFocus:true` configurado |
| H5 | 401 dispara `useAuthStore.clear()` |

### 7.2 E2E (Playwright _electron) — 22 escenarios

**`apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts`** (14 escenarios, verbatim `plan.md:1214-1227`):

1. `parkosFetch retries 5xx con backoff 300/600/1200ms`
2. `parkosFetch NO retry 4xx (excepto 408)`
3. `parkosFetch refresh-once 401 con Mutex`
4. `parkosFetch emits Idempotency-Key SHA-256 en POST`
5. `parkosFetch skips Idempotency-Key en POST /auth/login`
6. `parkosFetch timeout AbortController`
7. `parkosFetch Zod validation pass`
8. `parkosFetch Zod validation fail lanza ZodError`
9. `parkosFetch X-Sucursal-Context header preserved`
10. `parkosFetch Bearer header desde authStore electron-store`
11. `parkosFetch double-401 limpia authStore y emite evento`
12. `parkosFetch NetworkError retry`
13. `parkosFetch 408 retry`
14. `parkosFetch 5xx retry exhausted (3 attempts) retorna Response final`

**`apps/electron-sucursal/e2e/auth/bridge.spec.ts`** (8 escenarios):

1. `bridge.imprimir acepta PrintPayload e invoca 'print:ticket'`
2. `bridge.usb.list retorna USBDevice[]`
3. `bridge.kiosk.toggle(on) envía 'kiosk:toggle'`
4. `bridge.app.quit cierra la app`
5. `bridge.apiStatus.get retorna ApiStatus`
6. `bridge.authStore.get retorna valor persistido`
7. `bridge.authStore.set persiste valor en electron-store`
8. `bridge.authStore.delete remueve valor de electron-store`

### 7.3 A11y (axe-core WCAG 2.1 AA)

```typescript
// apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts

import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('WCAG 2.1 AA — 0 violaciones en login screen', async ({ page }) => {
  await page.goto('http://localhost:5173/login');
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(results.violations).toEqual([]);
});
```

Cross-ref RNF-022 (`docs/01-requisitos/no-funcionales.md:126`).

### 7.4 Cobertura requirements (>90% parkosFetch.ts)

```typescript
// apps/ui-kit/vitest.config.ts (extracto)

export default defineConfig({
  test: {
    environment: 'jsdom',
    coverage: {
      provider: 'v8',
      thresholds: {
        'src/fetch/parkosFetch.ts': { lines: 90, functions: 90, branches: 85 },
        'src/store/authStore.ts':   { lines: 80, functions: 80, branches: 75 },
        'src/hooks/useAuth.ts':     { lines: 80, functions: 80, branches: 75 },
      },
    },
  },
});
```

### 7.5 Contract test (preload vs bridge.d.ts shape)

```typescript
// apps/electron-sucursal/electron/__tests__/preload.contract.test.ts

import { describe, it, expect } from 'vitest';
import type { BridgeSurface } from '../bridge';
import * as bridgeModule from '../preload';

describe('preload contract vs bridge.d.ts', () => {
  it('expone exactamente los 8 métodos de BridgeSurface', () => {
    const exposed = (bridgeModule as any).bridge;  // bridge es export opcional
    expect(typeof exposed.imprimir).toBe('function');
    expect(typeof exposed.usb.list).toBe('function');
    expect(typeof exposed.kiosk.toggle).toBe('function');
    expect(typeof exposed.app.quit).toBe('function');
    expect(typeof exposed.apiStatus.get).toBe('function');
    expect(typeof exposed.authStore.get).toBe('function');
    expect(typeof exposed.authStore.set).toBe('function');
    expect(typeof exposed.authStore.delete).toBe('function');
  });

  it('NO expone ipcRenderer raw', () => {
    const exposed = (bridgeModule as any).bridge;
    expect(exposed.ipcRenderer).toBeUndefined();
    expect(exposed.contextBridge).toBeUndefined();
  });

  it('NO expone métodos fuera de la whitelist', () => {
    const exposed = (bridgeModule as any).bridge;
    const allowed = new Set([
      'imprimir', 'usb', 'kiosk', 'app', 'apiStatus', 'authStore',
    ]);
    expect(Object.keys(exposed).every((k) => allowed.has(k))).toBe(true);
  });
});
```

---

## 8. Configuración y deployment

### 8.1 package.json changes (apps/ui-kit + electron-sucursal)

**`apps/ui-kit/package.json`** (MODIFY, T1+T4):

```json
{
  "name": "@parkos/ui-kit",
  "version": "0.2.0",
  "dependencies": {
    "zustand": "^4.5.0"
  },
  "peerDependencies": {
    "react": "^18.3.0",
    "swr": "^2.2.5",
    "radix-slot": "^1.1.0",
    "cva": "^1.0.0",
    "clsx": "^2.1.0",
    "lucide-react": "^0.460.0",
    "tailwind-merge": "^2.5.0"
  },
  "devDependencies": {
    "zod": "^3.23.0",
    "msw": "^2.4.0",
    "@testing-library/react": "^16.0.0",
    "fake-indexeddb": "^6.0.0",
    "vitest": "^2.1.0"
  },
  "exports": {
    ".": "./src/index.ts",
    "./fetch": "./src/fetch/index.ts",
    "./store": "./src/store/index.ts",
    "./hooks": "./src/hooks/index.ts"
  }
}
```

**`apps/electron-sucursal/package.json`** (sin nuevas deps — F2.1 ya incluye electron-store + vitest + playwright + axe-core).

### 8.2 tsconfig changes (electron-sucursal main)

**`apps/electron-sucursal/tsconfig.main.json`** (MODIFY, T2):

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true
  },
  "include": [
    "electron/**/*.ts",
    "electron/bridge.d.ts"
  ]
}
```

**`apps/electron-sucursal/tsconfig.renderer.json`** (F2.1 ya incluye `src/renderer/global.d.ts` — T2 solo agrega el triple-slash ref).

### 8.3 electron-store path (app.getPath('userData')/auth.json)

```typescript
// apps/electron-sucursal/electron/main.ts (F2.3 conecta — F2.2 NO modifica main)

// F2.3 pseudocódigo:
import Store from 'electron-store';
const store = new Store({ name: 'auth' });
// store path: app.getPath('userData')/auth.json
// macOS: ~/Library/Application Support/<app>/auth.json
// Linux: ~/.config/<app>/auth.json
// Windows: %APPDATA%/<app>/auth.json

ipcMain.handle('auth-store:get',   (_, key) => store.get(key));
ipcMain.handle('auth-store:set',   (_, key, value) => store.set(key, value));
ipcMain.handle('auth-store:delete',(_, key) => store.delete(key));
```

**Cross-platform verified** (F2.1 DEC-ELEC-09 ya cerró R6). Path normalizado por Electron, no requiere código platform-specific.

---

## 9. Compatibilidad y migración

### 9.1 web_admin/src/lib/fetch.ts → re-export

```typescript
// apps/web_admin/src/lib/fetch.ts (POST-T1 — verbatim re-export)
export {
  parkosFetch,
  parkosFetchRaw,
  ParkosHttpError,
  type ParkosFetchInit,
} from '@parkos/ui-kit/fetch';

// Backward compat: legacy setAuthToken/getAuthToken locales deprecadas
// (web_admin migrará a useAuthStore en F3.1+)
```

**NO breaking change**: consumers que importan `import { parkosFetch } from '@/lib/fetch'` siguen funcionando. Las capabilities nuevas (retry/refresh/idempotency/Zod) se AÑADEN transparentemente.

### 9.2 preload.ts: 11 → 50 LOC (whitelist explicita)

```diff
- // apps/electron-sucursal/electron/preload.ts (F2.1 — 11 LOC)
- import { contextBridge } from 'electron';
- contextBridge.exposeInMainWorld('bridge', {});
+ // apps/electron-sucursal/electron/preload.ts (F2.2 — ~50 LOC)
+ import { contextBridge, ipcRenderer } from 'electron';
+
+ contextBridge.exposeInMainWorld('bridge', {
+   imprimir: (payload) => ipcRenderer.invoke('print:ticket', payload),
+   usb: { list: () => ipcRenderer.invoke('usb:list') },
+   kiosk: { toggle: (on) => ipcRenderer.send('kiosk:toggle', on) },
+   app: { quit: () => ipcRenderer.send('app:quit') },
+   apiStatus: { get: () => ipcRenderer.invoke('api:status') },
+   authStore: {
+     get: (key) => ipcRenderer.invoke('auth-store:get', key),
+     set: (key, value) => ipcRenderer.invoke('auth-store:set', key, value),
+     delete: (key) => ipcRenderer.invoke('auth-store:delete', key),
+   },
+ });
```

### 9.3 consumer de web_admin: sucursal-context.ts intacto

`apps/web_admin/src/lib/sucursal-context.ts` (READ ONLY) sigue exportando `getSucursalHeader()`. `parkosFetch` lo importa via `@parkos/web/lib/sucursal-context` (path alias F2.1). **No requiere migración** — F2.2 consume el helper existente.

---

## 10. Observabilidad y logging

### 10.1 Structured logs (opcional, Fase 3)

F2.2 NO introduce logging centralizado. Errors se propagan como `ParkosHttpError {status, body, url}` para que callers (F3.1+) decidan UX (toast, redirect, retry manual).

**Forward hook Fase 3**: integrar `electron-log` con rotation 10MB×5 JSON files. Logs en `app.getPath('logs')/main-YYYY-MM-DD.log`.

### 10.2 Error reporting (placeholder para Sentry/etc.)

**NO este sprint**. Forward hook: `apps/electron-sucursal/electron/main.ts` (F2.3) inicializa Sentry con `Sentry.init({ dsn: process.env.SENTRY_DSN })` y envuelve `ipcMain.handle` con `Sentry.captureException(err)`.

Patrón local para parkosFetch (sin Sentry):
```typescript
catch (err) {
  if (attempt >= 3) {
    console.error('[parkosFetch]', { url, method: init?.method, err });
    throw err;
  }
  // ...
}
```

---

## 11. Riesgos y mitigaciones técnicas (cross-ref exploration §8)

| # | Riesgo | Probabilidad | Severidad | Mitigación |
|---|---|---|---|---|
| **R1** | Race condition 401 refresh — N requests concurrentes disparan N refreshes paralelos | HIGH | HIGH | DEC-FETCH-03: Mutex singleton en `refreshPromise`. Solo UN refresh activo a la vez; los demás esperan el resultado. Validado por test U9 (Mutex concurrency). |
| **R2** | electron-store stale key TTL — refresh token expirado persiste | MEDIUM | MEDIUM | DEC-FETCH-06: `clear()` en logout handler + doble-401 fallido. `partialize` solo persiste `{accessToken, refreshToken, expiresAt}`. Validación de expiración en read (forward hook Fase 3 con interval check). |
| **R3** | Idempotency-Key collisions en multi-tab | LOW | LOW | DEC-FETCH-04: SHA-256(method+path+body) garantiza uniqueness por contenido. Kiosko Electron es single-tab por diseño (F2.3 single-instance lock). |
| **R4** | Bridge IPC type drift — main process cambia handler sin actualizar d.ts | MEDIUM | MEDIUM | DEC-FETCH-08: `preload.contract.test.ts` valida shape en CI (T3). `tsc --noEmit` catches drift. Triple-slash reference fuerza import en renderer. |
| **R5** | Zod schema drift backend/frontend | MEDIUM | MEDIUM | DEC-FETCH-05: Zod validation runtime catches drift en dev/test. Auto-generación desde Pydantic via `datamodel-code-generator` — DEFERRED Fase 3 (forward hook). |
| **R6** | electron-store path differs across OS (Windows/Linux/macOS) | LOW | LOW | electron-store normaliza via `app.getPath('userData')`. F2.1 ya verificó 3-target support (DEC-ELEC-09). |
| **R7** | SHA-256 async overhead — `crypto.subtle.digest` es async; impacta latency | LOW | LOW | Pre-computar key en `buildInit` (no bloqueante crítico). Web Crypto API es nativo del V8 — overhead ~0.5ms por request. |
| **R8** | vitest fake timers + AbortController interaction | LOW | LOW | `vi.useFakeTimers({ shouldAdvanceTime: true })` preserva timers reales durante AbortController. Test U12 verifica. |

**Riesgos cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

---

## 12. Decisiones arquitectónicas (cross-ref proposal §4 — 8 DEC-FETCH-NN)

### DEC-FETCH-01 — Extraer parkosFetch a @parkos/ui-kit/fetch (DRY)

**Choice**: Mover `apps/web_admin/src/lib/fetch.ts:1-66` a `apps/ui-kit/src/fetch/parkosFetch.ts` con extensiones (retry, refresh, idempotency, Zod). `apps/web_admin/src/lib/fetch.ts` se convierte en re-exporter transparente.

**Alternatives considered**:
- (a) Mantener parkosFetch duplicado en web_admin y electron-sucursal → dos copias divergen, bug fixes se aplican en 2 sitios.
- (b) Crear un nuevo paquete `@parkos/fetch` separado de ui-kit → overhead de workspace topology change; ui-kit ya existe y es la home natural de cross-cutting primitives.

**Rationale**: web_admin y electron-sucursal comparten el mismo backend API. Sin extracción, dos copias divergen. F2.1 ya shippeó `@parkos/ui-kit` como workspace package (DEC-ELEC-08); F2.2 continúa la tendencia DRY.

### DEC-FETCH-02 — Retry 5xx + 408 con backoff 300/600/1200ms (NO retry 4xx)

**Choice**: `parkosFetch` reintenta 3 veces con backoff 300/600/1200ms ONLY sobre respuestas `5xx`, `408 Request Timeout`, y `NetworkError`. NO retry sobre `4xx` excepto 408.

**Alternatives considered**:
- (a) Exponential backoff con jitter (`2^attempt * 100ms + random(50)`) → variabilidad complica testing determinista.
- (b) Retry ilimitado → DoS al backend si el bug es persistente.
- (c) Linear backoff (300/300/300ms) → menos diferenciación entre attempt 1 y 3.

**Rationale**: 5xx es transitorio (DB blip, restart del backend). 408 es timeout del server. 4xx es bug del cliente — retry no soluciona. `plan.md:1204` verbatim.

### DEC-FETCH-03 — 401 refresh-once con Mutex singleton

**Choice**: Mutex singleton `refreshPromise` para serializar refreshes. `handle401` solo intenta refresh en `attempt === 1` (doble-401 propagation).

**Alternatives considered**:
- (a) Refresh por cada 401 sin Mutex → stampede paraleliza N refreshes contra backend (R1).
- (b) Refresh bajo Zustand state `isRefreshing` → race condition entre `set` y `get` (React renders mid-flight).
- (c) Refresh bajo `useRef` en componente → se pierde entre renders (hooks re-mounted).

**Rationale**: Mutex módulo-level sobrevive entre renders. Garantiza que 2+ requests con 401 disparan UN solo refresh; los demás esperan. Validado por test U9.

### DEC-FETCH-04 — Idempotency-Key SHA-256(método+ruta+cuerpo)

**Choice**: SHA-256(method.toUpperCase() + "|" + url + "|" + JSON.stringify(body ?? null)) para POST/PUT/DELETE/PATCH. Excepción: `POST /auth/login` NO lleva key.

**Alternatives considered**:
- (a) UUID v4 → no determinístico; retries idénticos producen keys distintas (R3 + dedup backend fails).
- (b) SHA-256(method+url) sin body → no captura mutaciones con body distinto (false positives).
- (c) UUID v7 (time-ordered) → mejor que v4 pero aún no determinístico para retries.

**Rationale**: `plan.md:1203` verbatim. Determinismo > randomness: dos requests idénticos producen la MISMA key → backend puede dedupe retries sin doble-ejecutar.

### DEC-FETCH-05 — Zod validation en boundary via parkosFetch<T>(url, schema)

**Choice**: `parkosFetch<T>(url, init, schema?)` acepta Zod schema opcional. Si proveído, valida response.

**Alternatives considered**:
- (a) TypeScript types solos → borrados en compilación, no validan runtime (R5).
- (b) Yup / io-ts / runtypes → Zod tiene mejor TS inference y menor bundle size.
- (c) Auto-generación desde Pydantic en build-time → DEFERRED Fase 3 (forward hook).

**Rationale**: Defense in depth (XR6 layer 4 — contract). Catches drift backend/frontend en dev/test antes de producción.

### DEC-FETCH-06 — authStore Zustand + persist contra electron-store (NO localStorage)

**Choice**: `useAuthStore` con `persist` + `createJSONStorage(() => electronStoreAdapter)`. Path: `app.getPath('userData')/auth.json`.

**Alternatives considered**:
- (a) localStorage como F1.x/F2.1 → frágil en kiosko Electron (R-FETCH-4 FAIL).
- (b) sessionStorage en main process → no sobrevive app restart.
- (c) IndexedDB en renderer → electron-store es más simple y suficiente para KV tokens.

**Rationale**: electron-store es más robusto para kiosko: (a) DevTools reset; (b) OS-level storage clear; (c) profile corruption. F2.1 ya agregó electron-store como dep.

### DEC-FETCH-07 — useAuth() hook SWR consume authStore

**Choice**: `useAuth()` combina Zustand (tokens) + SWR (profile data). `refreshInterval: 5 * 60 * 1000`.

**Alternatives considered**:
- (a) React Query en lugar de SWR → más features pero bundle más pesado; SWR suficiente.
- (b) Zustand-only (sin SWR) → sin cache, sin revalidation, sin deduplicación.
- (c) SWR-only (sin Zustand) → tokens en SWR cache no persisten; pierde en refresh.

**Rationale**: Zustand = tokens (small, sync, frequently updated). SWR = profile data (large, async, infrequently fetched). Separación de concerns. 5-min refresh per `plan.md:1208`.

### DEC-FETCH-08 — Bridge IPC typed surface (8 métodos) via bridge.d.ts

**Choice**: `BridgeSurface` interface con 8 métodos en 6 grupos. `preload.ts` materializa con whitelist explícita. Triple-slash ref en renderer.

**Alternatives considered**:
- (a) Hand-rolled IPC sin tipos → drift entre main y renderer (R4).
- (b) `...spread` de ipcRenderer → expone TODO Electron al renderer (anti-pattern de seguridad).
- (c) Single method `bridge.invoke(channel, ...args)` → pierde type safety per-method.

**Rationale**: Tipado end-to-end previene drift. `tsc --noEmit` enforce en CI. Whitelist explícita previene leak de `ipcRenderer` raw.

---

## 13. Performance y benchmark

### 13.1 SHA-256 overhead (negligible)

`crypto.subtle.digest('SHA-256', data)` sobre ~1KB string (method+url+body) tarda ~0.1-0.5ms en V8 moderno (Electron 30 usa V8 12.x). Pre-computado en `buildInit` antes del fetch — no bloquea el request path crítico.

**Bench target**: <1ms por request para Idempotency-Key computation. Si supera, fallback a `crypto.subtle.worker` pool (forward hook).

### 13.2 Retry budget impact en UX (max 2.1s para backoff total)

Retry budget worst-case = 300ms + 600ms + 1200ms = **2100ms** entre primer attempt y último retry. En UX:
- Request simple (GET /auth/me) retry 1x: 300ms extra → tolerable (loading spinner).
- Request crítico (POST /auth/login) retry 2x: 1800ms extra → visible (toast "Reintentando...").
- Después de 3 attempts fallidos: throw `ParkosHttpError` → caller decide UX.

**Mitigación UX**: callers pueden deshabilitar retry via flag (forward hook) para acciones instant-feedback (e.g., validación de campo).

### 13.3 SWR refresh 5min — impact en bandwidth

`useAuth()` con `refreshInterval: 5 * 60 * 1000` dispara 1 GET /auth/me cada 5 minutos por mount. Con kiosko single-tab y idle largo:
- 12 requests/hora bandwidth: `AuthMeResponse` ~500 bytes JSON = **6 KB/hora**, **144 KB/día** — negligible.
- Si kiosko idle >24h: 1 wake-up refresh al volver a focus (`revalidateOnFocus: true`).

**Bench target**: <1% CPU overhead. SWR deduplica si 2+ componentes montan `useAuth()` simultáneamente.

---

## 14. Seguridad

- **JWT never persisted to electron-store en plaintext clear text**: electron-store escribe el JSON serializado en `auth.json` en `app.getPath('userData')`. En sistemas con FileVault (macOS) o EFS (Windows), el filesystem está cifrado at-rest. En kiosko sin cifrado, riesgo residual aceptable (no hay master key disponible). **Forward hook Fase 3**: cifrar `auth.json` con `safeStorage` (Electron API) usando OS keychain.

- **CSP y sandbox del renderer** (F2.1 ya configurado): CSP en `apps/electron-sucursal/index.html` bloquea `unsafe-inline`, `unsafe-eval`, scripts externos. Sandbox del renderer via `webPreferences: { sandbox: true }` (F2.1 default).

- **contextIsolation=true + nodeIntegration=false** (F2.1 default): renderer NO tiene acceso a `require`, `process`, ni Node.js APIs. Único canal legítimo es `window.bridge` (whitelist explícita).

- **Bridge surface whitelist (no spread)**: `preload.ts` declara cada método individualmente. `ipcRenderer` raw nunca se expone. Validado por `preload.contract.test.ts` U3 ("NO expone métodos fuera de la whitelist").

- **No expongo ipcRenderer raw**: `contextBridge.exposeInMainWorld('bridge', { ...whitelist })`. El renderer solo ve las funciones declaradas, no el handle interno de `ipcRenderer`.

---

## 15. Internacionalización

### 15.1 Mensajes de error en español desde apps/ui-kit/src/i18n/auth.json (crear si no existe)

F2.1 shippeó 7 namespaces i18n en `apps/electron-sucursal/src/i18n/`: `auth`, `errors`, `common`, `dashboard`, `turno`, `vehiculo`, `config`. F2.2 **NO agrega keys nuevos** — los mensajes de error vienen del backend (`detail` field en JSON response) o son técnicos en inglés (`ParkosHttpError`, `ZodError`).

**Forward hook F3.1**: cuando se implemente login UI, agregar keys a `auth.json`:
```json
{
  "auth": {
    "errors": {
      "invalid_credentials": "Email o contraseña incorrectos.",
      "account_locked": "Cuenta bloqueada. Intenta de nuevo en {{minutes}} minutos.",
      "network_error": "Error de conexión. Verifica tu red.",
      "session_expired": "Tu sesión ha expirado. Vuelve a iniciar sesión."
    }
  }
}
```

**Cross-ref** (`exploration.md` §13 out-of-scope): login UI es F3.1, no F2.2. F2.2 expone el wrapper HTTP; F3.1 renderiza la UI con i18n.

---

## 16. Plan de rollout

### 16.1 C1 (T1..T3) — primera sesión

| Task | Commit | Output |
|---|---|---|
| T1 | `feat(ui-kit): adicionar parkosFetch con retry 5xx, refresh-once 401, Idempotency-Key SHA-256, Zod validation, AbortController timeout` | `apps/ui-kit/src/fetch/{parkosFetch,index}.ts` + tests + `web_admin/src/lib/fetch.ts` re-export |
| T2 | `feat(electron): adicionar bridge IPC typed surface en bridge.d.ts con 8 métodos (imprimir, usb, kiosk, app, apiStatus, authStore)` | `apps/electron-sucursal/electron/bridge.d.ts` + `tsconfig.main.json` include |
| T3 | `feat(electron): wire bridge IPC handlers en preload con whitelist de 8 métodos` | `apps/electron-sucursal/electron/preload.ts` (11→50 LOC) + `preload.contract.test.ts` |

**Gates activados en C1**: G1 (retry 5xx+408), G2 (refresh-once), G3 (Idempotency-Key), G4 (Zod), G5 (tsc clean).

### 16.2 C2 (T4..T5) — segunda sesión

| Task | Commit | Output |
|---|---|---|
| T4 | `feat(ui-kit): adicionar authStore Zustand con persist electron-store y Mutex refresh-once` | `apps/ui-kit/src/store/authStore.ts` + tests + `package.json` (zustand) |
| T5 | `feat(ui-kit): adicionar useAuth SWR hook con refresh 5min y auto-clear en 401` | `apps/ui-kit/src/hooks/useAuth.ts` + tests |

**Gates activados en C2**: G6 (authStore 8 tests), G7 (useAuth 5 tests).

### 16.3 C3 (T6..T7) — tercera sesión

| Task | Commit | Output |
|---|---|---|
| T6 | `test(electron): adicionar 22 e2e auth scenarios via MSW (14 parkosFetch + 8 bridge)` | `apps/electron-sucursal/e2e/auth/{parkos-fetch,bridge}.spec.ts` |
| T7 | `test(electron): adicionar axe-core WCAG 2.1 AA gate (RNF-022)` | `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` |

**Gates activados en C3**: G8 completo (22 e2e + axe-core 0 violaciones).

### 16.4 Verificación: sdd-verify

Tras C3 verde, `sdd-verify` corre:
- `tsc --noEmit` en 3 workspaces (ui-kit + web_admin + electron-sucursal).
- `vitest --coverage` en ui-kit.
- `playwright e2e` en electron-sucursal.
- `axe-core scan` en electron-sucursal.
- `eslint --max-warnings 0` en 3 workspaces.
- Cross-check contra `proposal.md` §15 Definition of Done.

### 16.5 Archive: 0.5 sesión

`openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store/` se mueve a `openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/` con 7 artefactos (exploration + proposal + design + spec + tasks + apply-report + verify-report). `openspec/CHANGELOG.md` recibe entrada "2026-09-15 — HU-F2.2 parkosFetch + IPC bridge + authStore archived".

---

## Appendix A: Mockups de código (~200 LOC, snippets TS)

### A.1 parkosFetch.ts skeleton

```typescript
// apps/ui-kit/src/fetch/parkosFetch.ts (~120 LOC target)

import type { z } from 'zod';
import { useAuthStore } from '../store/authStore';
import { getSucursalHeader } from '@parkos/web/lib/sucursal-context';

const BACKOFF_MS = [300, 600, 1200] as const;
const DEFAULT_TIMEOUT_MS = 30_000;
const BASE_URL = import.meta.env.PARKOS_API_BASE ?? 'http://127.0.0.1:8000/api/v1';

export class ParkosHttpError extends Error {
  constructor(public readonly status: number, public readonly body: string, public readonly url: string) {
    super(`parkosFetch ${status} ${url}: ${body.slice(0, 200)}`);
    this.name = 'ParkosHttpError';
  }
}

export interface ParkosFetchInit extends Omit<RequestInit, 'signal'> {
  timeoutMs?: number;
  signal?: AbortSignal;
  skipIdempotencyKey?: boolean;
}

async function idempotencyKey(method: string, url: string, body: unknown): Promise<string> {
  const enc = new TextEncoder();
  const data = enc.encode(`${method.toUpperCase()}|${url}|${JSON.stringify(body ?? null)}`);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const { refreshToken } = useAuthStore.getState();
      if (!refreshToken) return null;
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const pair = await res.json();
      useAuthStore.getState().setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
      return pair.access_token;
    } catch { return null; } finally { refreshPromise = null; }
  })();
  return refreshPromise;
}

function delay(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

async function buildInit(input: RequestInfo | URL, init?: ParkosFetchInit): Promise<RequestInit> {
  const headers = new Headers(init?.headers);
  const url = typeof input === 'string' ? input : input.toString();
  const method = (init?.method ?? 'GET').toUpperCase();

  const { accessToken } = useAuthStore.getState();
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);

  const sucHeader = getSucursalHeader();
  if (sucHeader) headers.set('X-Sucursal-Context', sucHeader);

  const isMutational = ['POST', 'PUT', 'DELETE', 'PATCH'].includes(method);
  if (isMutational && !init?.skipIdempotencyKey && !url.endsWith('/auth/login')) {
    headers.set('Idempotency-Key', await idempotencyKey(method, url, init?.body));
  }

  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');

  return { ...init, headers };
}

async function handle401(input: RequestInfo | URL, init: ParkosFetchInit | undefined, res: Response, attempt: number): Promise<Response> {
  if (attempt > 1) return res;
  const newToken = await refreshAccessToken();
  if (!newToken) {
    useAuthStore.getState().clear();
    window.dispatchEvent(new CustomEvent('parkos:auth:cleared'));
    return res;
  }
  return parkosFetchRaw(input, init, attempt + 1);
}

export async function parkosFetchRaw(input: RequestInfo | URL, init?: ParkosFetchInit, attempt = 1): Promise<Response> {
  const finalInit = await buildInit(input, init);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), init?.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  try {
    const res = await fetch(input, { ...finalInit, signal: controller.signal });
    if (res.ok) return res;
    if (res.status >= 400 && res.status < 500 && res.status !== 408) {
      if (res.status === 401) return handle401(input, init, res, attempt);
      return res;
    }
    if (attempt >= 3) return res;
    await delay(BACKOFF_MS[attempt - 1]!);
    return parkosFetchRaw(input, init, attempt + 1);
  } catch (err) {
    if (attempt >= 3) throw err;
    await delay(BACKOFF_MS[attempt - 1]!);
    return parkosFetchRaw(input, init, attempt + 1);
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function parkosFetch<T>(input: RequestInfo | URL, init?: ParkosFetchInit, schema?: z.ZodType<T>): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) throw new ParkosHttpError(res.status, await res.text(), String(input));
  const json = await res.json();
  return schema ? schema.parse(json) : (json as T);
}
```

### A.2 authStore.ts skeleton

```typescript
// apps/ui-kit/src/store/authStore.ts (~80 LOC target)

import { create } from 'zustand';
import { persist, createJSONStorage, type StateStorage } from 'zustand/middleware';

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: string | null;
  setTokens: (access: string, refresh: string, expiresIn: number) => void;
  clear: () => void;
}

const electronStore: StateStorage = {
  getItem: async (key) => (await window.bridge.authStore.get(key)) ?? null,
  setItem: async (key, value) => { await window.bridge.authStore.set(key, value); },
  removeItem: async (key) => { await window.bridge.authStore.delete(key); },
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      expiresAt: null,
      setTokens: (access, refresh, expiresIn) => {
        const expiresAt = new Date(Date.now() + expiresIn * 1000).toISOString();
        set({ accessToken: access, refreshToken: refresh, expiresAt });
      },
      clear: () => set({ accessToken: null, refreshToken: null, expiresAt: null }),
    }),
    {
      name: 'parkos.auth',
      storage: createJSONStorage(() => electronStore),
      partialize: (s) => ({ accessToken: s.accessToken, refreshToken: s.refreshToken, expiresAt: s.expiresAt }),
      version: 1,
    },
  ),
);
```

### A.3 useAuth.ts skeleton

```typescript
// apps/ui-kit/src/hooks/useAuth.ts (~50 LOC target)

import useSWR from 'swr';
import { useAuthStore } from '../store/authStore';
import { parkosFetch, ParkosHttpError } from '../fetch/parkosFetch';
import type { AuthMeResponse, UserItem, SucursalItem } from '../schemas/auth';

export interface UseAuthReturn {
  user: UserItem | null;
  sucursal: SucursalItem | null;
  sucursalesPermitidas: SucursalItem[];
  permisos: string[];
  expiresAt: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: Error | undefined;
  refresh: () => Promise<AuthMeResponse | undefined>;
}

export function useAuth(): UseAuthReturn {
  const accessToken = useAuthStore((s) => s.accessToken);
  const { data, error, isLoading, mutate } = useSWR<AuthMeResponse>(
    accessToken ? '/auth/me' : null,
    parkosFetch,
    {
      refreshInterval: 5 * 60 * 1000,
      revalidateOnFocus: true,
      shouldRetryOnError: (err) => !(err instanceof ParkosHttpError && err.status === 401),
      onError: (err) => {
        if (err instanceof ParkosHttpError && err.status === 401) {
          useAuthStore.getState().clear();
          window.dispatchEvent(new CustomEvent('parkos:auth:cleared'));
        }
      },
    },
  );
  return {
    user: data?.user ?? null,
    sucursal: data?.sucursal ?? null,
    sucursalesPermitidas: data?.sucursales_permitidas ?? [],
    permisos: data?.permisos ?? [],
    expiresAt: data?.expires_at ?? null,
    isAuthenticated: !!accessToken,
    isLoading,
    error,
    refresh: mutate,
  };
}
```

### A.4 preload.ts expansion

```typescript
// apps/electron-sucursal/electron/preload.ts (~50 LOC)

import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('bridge', {
  imprimir: (payload) => ipcRenderer.invoke('print:ticket', payload),
  usb: { list: () => ipcRenderer.invoke('usb:list') },
  kiosk: { toggle: (on) => ipcRenderer.send('kiosk:toggle', on) },
  app: { quit: () => ipcRenderer.send('app:quit') },
  apiStatus: { get: () => ipcRenderer.invoke('api:status') },
  authStore: {
    get: (key) => ipcRenderer.invoke('auth-store:get', key),
    set: (key, value) => ipcRenderer.invoke('auth-store:set', key, value),
    delete: (key) => ipcRenderer.invoke('auth-store:delete', key),
  },
});
```

### A.5 bridge.d.ts

```typescript
// apps/electron-sucursal/electron/bridge.d.ts (~60 LOC)

export interface PrintPayload {
  ticketId: string;
  lines: Array<{ text: string; bold?: boolean; align?: 'left' | 'center' | 'right' }>;
  cut: boolean;
  cashDrawer?: boolean;
}

export interface USBDevice {
  vendorId: number;
  productId: number;
  productName: string | null;
  serialNumber: string | null;
}

export interface ApiStatus {
  online: boolean;
  lastSync: string | null;
}

export interface BridgeSurface {
  imprimir(payload: PrintPayload): Promise<{ ok: boolean }>;
  usb: { list(): Promise<USBDevice[]> };
  kiosk: { toggle(on: boolean): void };
  app: { quit(): void };
  apiStatus: { get(): Promise<ApiStatus> };
  authStore: {
    get(key: string): Promise<string | null>;
    set(key: string, value: string): Promise<void>;
    delete(key: string): Promise<void>;
  };
}

declare global {
  interface Window { bridge: BridgeSurface; }
}
```

---

## Appendix B: Map de archivos (cross-ref exploration §17)

### B.1 NEW (12 archivos)

| Path | Task | LOC target |
|---|---|---|
| `apps/ui-kit/src/fetch/parkosFetch.ts` | T1 | 120 |
| `apps/ui-kit/src/fetch/parkosFetch.test.ts` | T1 | 120 |
| `apps/ui-kit/src/fetch/index.ts` | T1 | 5 |
| `apps/ui-kit/src/store/authStore.ts` | T4 | 80 |
| `apps/ui-kit/src/store/authStore.test.ts` | T4 | 60 |
| `apps/ui-kit/src/hooks/useAuth.ts` | T5 | 50 |
| `apps/ui-kit/src/hooks/useAuth.test.ts` | T5 | 40 |
| `apps/electron-sucursal/electron/bridge.d.ts` | T2 | 60 |
| `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` | T3 | 50 |
| `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` | T6 | 60 |
| `apps/electron-sucursal/e2e/auth/bridge.spec.ts` | T6 | 50 |
| `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` | T7 | 30 |

### B.2 MODIFY (5 archivos)

| Path | Task | Delta LOC |
|---|---|---|
| `apps/web_admin/src/lib/fetch.ts` | T1 | 66 → 8 (re-export) |
| `apps/electron-sucursal/electron/preload.ts` | T3 | 11 → 50 |
| `apps/electron-sucursal/tsconfig.main.json` | T2 | +1 include |
| `apps/ui-kit/package.json` | T1+T4 | +deps |
| `apps/electron-sucursal/src/renderer/global.d.ts` | T2 | +1 triple-slash ref |

### B.3 READ ONLY (6 archivos)

| Path | Razón |
|---|---|
| `apps/web_admin/src/lib/sucursal-context.ts` | `getSucursalHeader()` consumer; F2.2 lo importa sin modificar |
| `backend/.../api/v1/auth.py` | 4 endpoints consumidos sin modificar |
| `backend/.../schemas/auth.py` | Pydantic shapes consumidas |
| `apps/ui-kit/src/{Button,cn,tokens}.{tsx,ts}` | F2.1 primitives intactos |
| `apps/electron-sucursal/electron/main.ts` | Handlers IPC se mockean; F2.3 conecta los reales |
| `openspec/specs/operations/spec.md` | F2.2 NO crea nuevos REQ-OPS-NNN (DEC-ELEC-10 precedent) |

### B.4 Total de impacto

- **NEW**: 12 archivos (~725 LOC).
- **MODIFY**: 5 archivos (~80 LOC delta).
- **READ ONLY**: 6 archivos.
- **TOTAL IMPACT**: 17 archivos, **~805 LOC nuevos + 80 LOC delta**.

---

**End of design.**