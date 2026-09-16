# Exploración — HU-F2.2 Cliente HTTP parkosFetch + IPC bridge + authStore

> **Phase**: explore (sdd-explore) · **Status**: ready for sdd-propose
> **HU ID**: HU-F2.2 (Fase 2 — capa de infraestructura HTTP/IPC/authStore; transversal, primera HU con HTTP behavior contract)
> **Working dir**: E:/easypunto_parkos · **Branch**: feat/fase-2-electron-scaffold (HEAD 5bdf857, F2.1 archivado 2026-09-15)
> **Inputs**: plan.md lines 1196-1240 (HU-F2.2 + 7 tareas atómicas T1..T7, 450 LOC plan verbatim); plan.md lines 1159-1194 (HU-F2.1 archivado, precedente de scaffold); plan.md lines 1242-1267 (HU-F2.3 updater+kiosko, forward consumer); openspec/_meta/roadmap.md lines 38-273 (IT-1..IT-10 web_sucursal consumer map); openspec/specs/operations/spec.md (XR6 at line 3951, REQ-OPS-102..105 from F1.15 — pattern for F2.2's future REQ-OPS-NNN additions); apps/web_admin/src/lib/fetch.ts:1-66 (parkosFetch existente, fuente de reutilización); apps/web_admin/src/lib/sucursal-context.ts (read en parkosFetch, NO F2.2 migration scope); apps/electron-sucursal/electron/preload.ts:1-11 (contextBridge vacío, F2.2 lo expande); apps/electron-sucursal/electron/bridge.d.ts (no existe — F2.2 lo crea); apps/ui-kit/{package.json,src/Button.tsx,src/cn.ts,src/tokens.ts} (workspace package shipped F2.1, target de nueva ubicación de parkosFetch); apps/package.json:5-8 (workspaces); backend/.../api/v1/auth.py:148-583 (POST /auth/{login,refresh,logout,me} consumer anchors); backend/.../schemas/auth.py:243-321 (LoginRequest, RefreshRequest, TokenPair, UserItem, SucursalItem, AuthMeResponse); modelo_datos_er.mmd:270-289 (configuracion_seguridad — F2.2 NO touch); modelo_datos_er.mmd:558-573 (prod.login [L-S] — F2.2 NO touch); docs/01-requisitos/no-funcionales.md:126 (RNF-022 WCAG 2.1 AA — F2.2 NO new e2e mandatory, pero mantiene axe-core gate); docs/03-desarrollo/{setup.md:15, estandares.md:79-91}; openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/exploration.md (17-section template, 10 DEC-ELEC-NN — verbatim mirror); openspec/changes/archive/2026-09-15-hu-f1-15-login-historico/exploration.md (17-section template verbatim).

---

## 1. Contexto y motivación

**Title**: "Cliente HTTP único parkosFetch (retry 5xx + refresh-once 401 + Idempotency-Key + Zod validation) + Bridge IPC tipado (imprimir, usb, kiosk, app, apiStatus) + authStore Zustand con persist electron-store + useAuth() hook SWR"

**Goal**: F2.1 shipteó la skeleton (Electron 30 + Vite 5 + React 18 + TS 5 strict + shadcn 14 + i18n 7 namespaces + ui-kit workspace + Playwright _electron + axe-core) — pero sin HTTP client ni IPC surface ni store de auth. F2.2 entrega las tres primitives de infraestructura que toda feature subsecuente (F3.1 login, F3.2 lockout, F3.3 turno, IT-3..IT-10) consumirá sin reinventar reglas cross-cutting:

1. **parkosFetch extendido** — un único `fetch` wrapper para web_admin + electron-sucursal que centraliza: (a) `Authorization: Bearer <token>` injection desde authStore (NO localStorage crudo); (b) `X-Sucursal-Context` header (idéntico a F2.1 behaviour); (c) `Idempotency-Key: <sha256>` header en POST/PUT/DELETE mutacionales; (d) retry con backoff 300/600/1200ms limitado a respuestas 5xx + 408; (e) refresh-once en 401 con Mutex singleton; (f) timeout via AbortController; (g) Zod validation opcional en boundary via `parkosFetch<T>(url, schema)`.
2. **Bridge IPC tipado** — `apps/electron-sucursal/electron/bridge.d.ts` define el contrato typed entre main process y renderer; `preload.ts` lo materializa vía `contextBridge.exposeInMainWorld('bridge', {imprimir, usb.list, kiosk.toggle, app.quit, apiStatus.get})`. Renderer importa tipos con triple-slash reference.
3. **authStore Zustand + persist electron-store** — Zustand store con `persist` middleware contra filesystem (`app.getPath('userData')/auth.json`); expone `useAuthStore()` selector + `useAuth()` SWR hook que hidrata desde `/auth/me`. `useAuth()` sincroniza store ↔ cache SWR ↔ backend.

**Por qué importa** (rationale): F2.2 es la última HU de Fase 2 con superficie HTTP. Cada HU de Fase 3 (login, lockout, turno, vehículo, factura, caja, anulación, alerta, reclamo, reimpresión, cliente) **consumirá** parkosFetch + bridge + authStore sin negociación. Mal diseño aquí se propaga a 11 HUs downstream (IT-3..IT-10 + F3.1/F3.2/F3.3). Bien diseñado, Fase 3 es trabajo de UI; mal diseñado, Fase 3 incluye reescritura de infra.

**Hard constraints** (mirrored from plan.md:1198-1240):
- `baseURL=http://127.0.0.1:8000/api/v1` (default; configurable por `PARKOS_API_BASE`).
- POST/PUT/DELETE/PATCH mutacionales llevan `Idempotency-Key` calculado como SHA-256(método+ruta+cuerpo) — **NO** uuid v4 (específico de plan.md:1203).
- 5xx + `NetworkError` reintenta hasta 3 veces con backoff 300/600/1200ms; 4xx NO retry (excepto 408).
- 401 → refresh único (`POST /auth/refresh`); un segundo 401 consecutivo limpia `authStore` y emite `authStore.cleared` event que el router intercepta para redirect a `/login?next=<path>`.
- `window.bridge` expone métodos typed en `electron/bridge.d.ts` y filtrados por whitelist en `preload.ts`.
- Cobertura de tests >90% en `parkosFetch.ts`; 14 escenarios MSW + 8 escenarios bridge contract.
- TDD estricto: cada test escrito ANTES de la implementación; tests rojos primero.
- Defense in depth: 5 capas (XR6 pattern de operations/spec.md:3951) — auth (HTTP) + a11y (axe-core) + engineering (TS strict + ESLint) + contract (vitest bridge) + retry-budget (timeout + refresh-once).

**Scope**: ~600 LOC production + ~370 LOC tests = ~970 LOC total. Plan 450 LOC matches: 450 ≈ 600 production logic - 150 LOC para shadcn-generated/reuse que no cuenta como authored. Breakdown por cluster C1..C3 detallado en §9.

## 2. Estado actual verificado

### 2.1 parkosFetch existente en apps/web_admin (REUTILIZAR, NO duplicar)

`apps/web_admin/src/lib/fetch.ts:1-66` define un wrapper minimalista que YA inyecta `Authorization: Bearer <token>` desde `localStorage['parkos.auth.token']` (R-FETCH-1, fetch.ts:37-40) y `X-Sucursal-Context` desde `getSucursalHeader()` (R-FETCH-2, fetch.ts:42-45).

**Verificado**:
- **R-FETCH-1 (PASS)**: YA inyecta `Authorization: Bearer <token>` desde localStorage.
- **R-FETCH-2 (PASS)**: YA inyecta `X-Sucursal-Context` desde getSucursalHeader().
- **R-FETCH-3 (FAIL — F2.2 extiende)**: NO tiene retry 5xx, NO tiene 401 refresh-once, NO tiene Idempotency-Key, NO tiene Zod validation, NO tiene timeout, NO tiene Mutex para refresh concurrente.
- **R-FETCH-4 (FAIL)**: `setAuthToken()` persiste token en localStorage — FRÁGIL en kiosko Electron (localStorage puede ser limpiado por DevTools o por OS-level storage reset). F2.2 migra persistencia a electron-store.

**Decisión técnica (ver §7)**: extraer parkosFetch a `apps/ui-kit/src/fetch/parkosFetch.ts` con la lógica extendida; web_admin re-exporta desde ui-kit (path alias `@parkos/ui-kit/fetch`).

### 2.2 Bridge IPC vacío en apps/electron-sucursal/electron/preload.ts

`preload.ts:1-11`:

```typescript
import { contextBridge } from 'electron';
contextBridge.exposeInMainWorld('bridge', {});
```

**Verificado**:
- **R-IPC-1 (PASS)**: contextBridge seam existe (F2.1 lo shippeó).
- **R-IPC-2 (FAIL — F2.2 lo crea)**: NO existe `apps/electron-sucursal/electron/bridge.d.ts` con tipos de `PrintPayload`, `USBDevice`, `KioskState`, `ApiStatus`.
- **R-IPC-3 (FAIL — F2.2 lo materializa)**: NO existen handlers IPC en main process para los métodos del surface (handlers se mockean/stubean en F2.2 y F2.3 los conecta al main real).
- **R-IPC-4 (PASS)**: La superficie está estanca — no hay drift porque no hay nada expuesto.

### 2.3 authStore inexistente

**Verificado**:
- **R-AUTH-1 (FAIL)**: NO existe `apps/ui-kit/src/store/authStore.ts` ni equivalente en web_admin.
- **R-AUTH-2 (FAIL)**: NO existe hook `useAuth()` que consuma SWR a `/auth/me`.
- **R-AUTH-3 (PASS)**: SWR ya está declarado como dep en apps/web_admin/package.json (precedente confirmado en F2.1).

### 2.4 Backend API surface (consumer anchors para F2.2)

Verificado contra `backend/.../api/v1/auth.py:148-583` y `schemas/auth.py:243-321`:

- `POST /auth/login` (auth.py:148-307) — `LoginRequest{email,password}` → `TokenPair{access_token,refresh_token,token_type,expires_in}` + cookie `parkos_session` httponly+secure+samesite=lax (line 291-299).
- `POST /auth/refresh` (auth.py:310-349) — `RefreshRequest{refresh_token}` → `TokenPair` (mismo refresh_token, **NO rotation in PR1b**).
- `POST /auth/logout` (auth.py:352-393) — 204 No Content; cierra `prod.login` row.
- `GET /auth/me` (auth.py:419-583) — `AuthMeResponse{user:UserItem,sucursal:SucursalItem,sucursales_permitidas:list[SucursalItem],permisos:list[str],expires_at:str}` (schemas/auth.py:295-321).

### 2.5 Workspace topology

Verificado contra `apps/package.json:5-8`:
- `workspaces:["ui-kit","web_admin","electron-sucursal"]` — F2.1 ya añadió electron-sucursal (R-WS-PASS, F2.1 DEC-ELEC-01 verified).
- F2.2 NO requiere modificar `apps/package.json` — F2.1 ya shippeó la topología correcta.

## 3. Consumer anchor: endpoints backend /auth/*

F2.2 NO crea endpoints nuevos. Consume los 4 existentes. Esta sección los documenta como anchor para que la propuesta pueda emitir requirements de comportamiento sin redescubrir el contrato.

### 3.1 POST /api/v1/auth/login

**Request** (`schemas/auth.py:243-247`):
```python
class LoginRequest(_Base):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=8, max_length=128)]
```

**Response 200** (`schemas/auth.py:256-262`):
```python
class TokenPair(_Base):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # ACCESS_TOKEN_TTL seconds (default 3600)
```

**Side effect** (auth.py:291-299): set-cookie `parkos_session=<access_token>; HttpOnly; Secure; SameSite=Lax; Max-Age=<expires_in>; Path=/`.

**Errores**:
- `401 invalid_credentials` — email desconocido O password incorrecto (antienumeration, mismo shape).
- `429 account_locked` — `Retry-After: <minutos*60>` cuando `count(fallido in window) >= max_intentos`.
- `500/503` — error interno.

**Idempotency**: el endpoint es idempotente por sí mismo (bcrypt verify + INSERT login row + emisión JWT). NO requiere `Idempotency-Key` header del cliente — la uniqueness está garantizada por la combinación (email, timestamp del login exitoso en `prod.login`).

### 3.2 POST /api/v1/auth/refresh

**Request** (`schemas/auth.py:250-253`):
```python
class RefreshRequest(_Base):
    refresh_token: Annotated[str, StringConstraints(min_length=1)]
```

**Response 200** (`schemas/auth.py:256-262`): mismo `TokenPair`. auth.py:345-348 — devuelve el MISMO refresh_token (no rotation en PR1b).

**Errores**:
- `401 invalid_refresh_token` — JWT verification falló (signature, expiry).
- `401 not_a_refresh_token` — claim `type != "refresh"`.

### 3.3 POST /api/v1/auth/logout

**Request**: vacío (auth lee JWT del header `Authorization`).

**Response 204**: No Content.

**Side effect** (auth.py:374-393): cierra el último `prod.login` row abierto del actor (`timestamp_cierre IS NULL`, ordered DESC).

**Errores**:
- `401` — JWT inválido/expirado.

### 3.4 GET /api/v1/auth/me

**Request**: header `Authorization: Bearer <access_token>`. Header `X-Sucursal-Context` opcional (no usado aquí — el JWT ya pinea sucursal).

**Response 200** (`schemas/auth.py:295-321`):
```python
class AuthMeResponse(_Base):
    user: UserItem            # {uuid, email, nombre, apellido, rol}
    sucursal: SucursalItem    # {uuid, nombre, prefijo_nombre} — JWT-pinned
    sucursales_permitidas: list[SucursalItem]  # DB-driven, sin .limit(1)
    permisos: list[str]       # [] si ninguno
    expires_at: str           # ISO 8601 UTC, derivated from JWT exp
```

**Errores** (auth.py:444-458):
- `404 not_found` — CUALQUIER JWT failure mode colapsa a 404 (antienumeration).

## 4. parkosFetch existente en apps/web_admin (REUTILIZAR, NO duplicar)

### 4.1 Capability matrix

| Capability | Actual (web_admin) | F2.2 target |
|---|---|---|
| Authorization Bearer | ✅ desde localStorage | ✅ desde authStore (Zustand) + electron-store |
| X-Sucursal-Context | ✅ desde getSucursalHeader() | ✅ idéntico (reusar getSucursalHeader) |
| Idempotency-Key | ❌ | ✅ SHA-256(método+ruta+cuerpo) para POST/PUT/DELETE/PATCH mutacionales |
| Retry 5xx | ❌ | ✅ 3 intentos, backoff 300/600/1200ms |
| Retry 408 | ❌ | ✅ 3 intentos (timeout retry) |
| 401 refresh-once | ❌ | ✅ Mutex singleton |
| Timeout | ❌ | ✅ AbortController con `timeoutMs` option |
| Zod validation | ❌ | ✅ opcional via `parkosFetch<T>(url, schema)` |
| NetworkError → retry | ❌ | ✅ trata como 5xx |
| Cobertura tests >90% | ❌ (0% actual) | ✅ 14 escenarios MSW |

### 4.2 Estrategia de extracción

`apps/web_admin/src/lib/fetch.ts:1-66` se MUEVE a `apps/ui-kit/src/fetch/parkosFetch.ts` con extensiones. `apps/web_admin/src/lib/fetch.ts` se convierte en:

```typescript
// re-export para no romper imports existentes
export { parkosFetch, setAuthToken, getAuthToken } from '@parkos/ui-kit/fetch';
```

Esto preserva el comportamiento actual (R-FETCH-1, R-FETCH-2) y lo extiende (R-FETCH-3, R-FETCH-4).

### 4.3 Idempotency-Key — cálculo SHA-256 (NO uuid v4)

**Decisión explícita vs. plan inicial** — el plan.md:1203 es explícito:

> "When cualquier request de mutación, Then lleva `Idempotency-Key` = SHA-256(método+ruta+cuerpo)"

Razones:
1. **Determinismo**: dos requests idénticos (mismo método + ruta + cuerpo) producen el MISMO `Idempotency-Key`. Esto permite al backend deduplicar retries del cliente sin doble-ejecutar.
2. **Idempotencia real**: SHA-256(método+ruta+cuerpo) garantiza que si la red interrumpe el response y el cliente reintenta, el backend ve la misma key y responde con el resultado cacheado.

```typescript
async function idempotencyKey(method: string, url: string, body: unknown): Promise<string> {
  const enc = new TextEncoder();
  const data = enc.encode(`${method.toUpperCase()}|${url}|${JSON.stringify(body ?? null)}`);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return Array.from(new Uint8Array(hash)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

Métodos que reciben `Idempotency-Key`: `POST` (excepto `/auth/login`), `PUT`, `DELETE`, `PATCH`.
Métodos que NO reciben: `GET`, `HEAD`, `OPTIONS`, `POST /auth/login` (idempotente por naturaleza).

### 4.4 Migración de setAuthToken

`apps/web_admin/src/lib/fetch.ts:50-62` define `setAuthToken()` que escribe en localStorage. F2.2 lo reemplaza por authStore Zustand con persist electron-store:

```typescript
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

interface AuthState {
  accessToken: string | null;
  refreshToken: string | null;
  expiresAt: string | null;
  setTokens: (access: string, refresh: string, expiresIn: number) => void;
  clear: () => void;
}

const electronStore = {
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
      setTokens: (access, refresh, expiresIn) => set({
        accessToken: access,
        refreshToken: refresh,
        expiresAt: new Date(Date.now() + expiresIn * 1000).toISOString(),
      }),
      clear: () => set({ accessToken: null, refreshToken: null, expiresAt: null }),
    }),
    {
      name: 'parkos.auth',
      storage: createJSONStorage(() => electronStore),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        expiresAt: state.expiresAt,
      }),
    }
  )
);
```

**Notas críticas**:
- `electron-store` solo se inicializa en el main process; el renderer accede vía IPC bridge (`window.bridge.authStore.get/set/delete`).
- `partialize` excluye cualquier estado derivado (no hay `user` ni `permisos` aquí — esos viven en `useAuth()` SWR cache).
- `clear()` se invoca en logout handler y en doble-401 retry-once fallido.

## 5. Bridge IPC vacío en apps/electron-sucursal/electron/preload.ts

### 5.1 Estado actual (preload.ts:1-11)

```typescript
import { contextBridge } from 'electron';
contextBridge.exposeInMainWorld('bridge', {});
```

Surface actual: `{ }` — vacío. F2.1 shippeó solo el seam para que F2.2 lo expanda.

### 5.2 Surface objetivo

| Método | Firma | Propósito | Forward consumer |
|---|---|---|---|
| `imprimir(payload)` | `(payload: PrintPayload) => Promise<{ok: boolean}>` | Llama a `escpos-usb` para imprimir ticket | F5.1+ (reimpresión térmica) |
| `usb.list()` | `() => Promise<USBDevice[]>` | Lista dispositivos USB conectados (thermal printers, barcode scanners) | F5.1+ |
| `kiosk.toggle(on)` | `(on: boolean) => void` | Habilita/deshabilita kiosko mode (full-screen + bloquea taskbar) | F2.3 (single-instance lock + PIN) |
| `app.quit()` | `() => void` | Cierra la app | F2.3 (logout cleanup) |
| `apiStatus.get()` | `() => Promise<{online: boolean; lastSync: string \| null}>` | Health check del backend (ping /health) | F11.x (sync UI) |
| `authStore.get(key)` | `(key: string) => Promise<string \| null>` | electron-store read | F2.2 authStore |
| `authStore.set(key, value)` | `(key: string, value: string) => Promise<void>` | electron-store write | F2.2 authStore |
| `authStore.delete(key)` | `(key: string) => Promise<void>` | electron-store delete | F2.2 authStore |

**Corrección vs plan.md:1206**: el plan inicial mencionaba 5 métodos; la superficie F2.2 es 8 porque DEC-FETCH-06 requiere electron-store IPC adapter (3 métodos extra: get/set/delete). Login/logout/refresh NO van por IPC — van por HTTP directo vía parkosFetch.

### 5.3 Tipo typed surface en bridge.d.ts

`apps/electron-sucursal/electron/bridge.d.ts` (~60 LOC):

```typescript
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
  imprimir(payload: PrintPayload): Promise<{ ok: boolean }>;
  usb: {
    list(): Promise<USBDevice[]>;
  };
  kiosk: {
    toggle(on: boolean): void;
  };
  app: {
    quit(): void;
  };
  apiStatus: {
    get(): Promise<ApiStatus>;
  };
  authStore: {
    get(key: string): Promise<string | null>;
    set(key: string, value: string): Promise<void>;
    delete(key: string): Promise<void>;
  };
}

declare global {
  interface Window {
    bridge: BridgeSurface;
  }
}
```

Renderer importa tipos con `/// <reference types="../../electron/bridge.d.ts" />` en `apps/electron-sucursal/src/renderer/global.d.ts`.

### 5.4 Whitelist filtering

`preload.ts` declara explícitamente CADA método expuesto (NO `...spread`):

```typescript
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

No exponer `ipcRenderer` directamente (contextIsolation=true, nodeIntegration=false — defaults de F2.1). Los IPC handlers reales del main process (`print:ticket`, `usb:list`, etc.) NO se implementan en F2.2 — F2.3 los conecta vía HU-F2.3-T5.

## 6. Stack técnico objetivo

### 6.1 Nuevas dependencias (apps/ui-kit/package.json + apps/electron-sucursal/package.json)

`apps/ui-kit/package.json`:
- `dependencies`: `zustand@^4.5.0`.
- `peerDependencies`: react + radix-slot + cva + clsx + lucide + tailwind-merge (F2.1). Agregar `swr@^2.2.5`.
- `devDependencies`: `zod@^3.23.0`, `vitest@^2.1.0`, `msw@^2.4.0`, `@testing-library/react@^16.0.0`, `fake-indexeddb@^6.0.0`.

`apps/electron-sucursal/package.json`:
- `dependencies`: ya tiene electron-store (F2.1).
- `devDependencies`: ya tiene vitest + playwright + axe-core (F2.1).

### 6.2 Versiones objetivo

- TypeScript 5.6.x.
- React 18.3.x.
- Zustand 4.5.x.
- SWR 2.2.x.
- Zod 3.23.x.
- MSW 2.4.x.

### 6.3 Tooling

- Vitest 2.1.x con jsdom env para unit.
- MSW 2.4.x con handlers de Node (no Service Worker — Vitest corre en jsdom).
- `vi.useFakeTimers()` para backoff testing.
- Playwright + _electron.launch para e2e.
- axe-core via `@axe-core/playwright`.

## 7. Decisiones arquitectónicas (DEC-FETCH-NN)

### 7.1 DEC-FETCH-01 — Extraer parkosFetch a @parkos/ui-kit/fetch (DRY)

**DECISION**: Mover `apps/web_admin/src/lib/fetch.ts:1-66` a `apps/ui-kit/src/fetch/parkosFetch.ts` con extensiones (retry, refresh, idempotency, Zod). `apps/web_admin/src/lib/fetch.ts` se convierte en re-exporter.

**RATIONALE**: web_admin y electron-sucursal comparten el mismo backend API. Sin extracción, dos copias divergen. F2.1 ya shippeó @parkos/ui-kit como workspace package (DEC-ELEC-08); F2.2 continúa la tendencia DRY.

### 7.2 DEC-FETCH-02 — Retry 5xx + 408 con backoff 300/600/1200ms (NO retry 4xx)

**DECISION**: `parkosFetch` reintenta 3 veces con backoff 300/600/1200ms ONLY sobre respuestas `5xx`, `408 Request Timeout`, y `NetworkError` (fetch threw). NO retry sobre `4xx` excepto 408.

**RATIONALE**: 5xx es transitorio (DB blip, restart del backend). 408 es timeout del server. 4xx es bug del cliente — retry no soluciona. Plan.md:1204 verbatim.

### 7.3 DEC-FETCH-03 — 401 refresh-once con Mutex singleton

**DECISION**: Al recibir 401, `parkosFetch` intenta `POST /auth/refresh` UNA sola vez con el refresh token persistido. Si refresh 200, reintenta la request original UNA vez con el nuevo access token. Si refresh 401, propaga el 401 al caller Y emite `authStore.clear()` Y emite un evento que el router intercepta para redirect a `/login?next=<path>`.

**Mutex**: Si 2+ requests concurrentes reciben 401 simultáneamente, solo UNO ejecuta refresh; los demás esperan el resultado del singleton.

```typescript
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;  // singleton
  const refreshToken = useAuthStore.getState().refreshToken;
  if (!refreshToken) return null;
  refreshPromise = (async () => {
    try {
      const res = await fetch('/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return null;
      const pair: TokenPair = await res.json();
      useAuthStore.getState().setTokens(pair.access_token, pair.refresh_token, pair.expires_in);
      return pair.access_token;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}
```

### 7.4 DEC-FETCH-04 — Idempotency-Key SHA-256(método+ruta+cuerpo)

**DECISION**: POST/PUT/DELETE/PATCH (mutacionales) llevan header `Idempotency-Key: <sha256>` calculado client-side. SHA-256(method.toUpperCase() + "|" + url + "|" + JSON.stringify(body ?? null)). EXCEPCIÓN: `POST /auth/login` NO lleva Idempotency-Key (es idempotente por sí mismo — bcrypt determinístico + UNIQUE constraint en `prod.login`).

**RATIONALE**: Plan.md:1203 verbatim. SHA-256 garantiza que retries idénticos producen la misma key → backend puede dedupe. Determinismo > randomness.

### 7.5 DEC-FETCH-05 — Zod validation en boundary via parkosFetch<T>(url, schema)

**DECISION**: `parkosFetch<T>(url, init, schema?)` acepta un Zod schema opcional. Si se provee, valida la respuesta contra el schema; si falla validación, lanza `ZodError`.

```typescript
async function parkosFetch<T>(
  input: RequestInfo | URL,
  init: RequestInit = {},
  schema?: z.ZodType<T>,
): Promise<T> {
  const res = await parkosFetchRaw(input, init);
  if (!res.ok) throw new ParkosHttpError(res.status, await res.text());
  const json = await res.json();
  if (schema) return schema.parse(json);  // throws ZodError on invalid
  return json as T;
}
```

**RATIONALE**: Defense in depth (XR6 layer 4 — contract).

### 7.6 DEC-FETCH-06 — authStore Zustand + persist contra electron-store (NO localStorage)

**DECISION**: `useAuthStore` (Zustand) usa `persist` middleware con `createJSONStorage(() => electronStoreAdapter)`. electronStoreAdapter envuelve `window.bridge.authStore.{get,set,delete}` que IPC-invoca `electron-store` en main process. Path: `app.getPath('userData')/auth.json`.

**RATIONALE**: electron-store es más robusto para kiosko que sobrevive: (a) DevTools reset; (b) OS-level storage clear; (c) profile corruption. F2.1 ya agregó electron-store como dep.

### 7.7 DEC-FETCH-07 — useAuth() hook SWR consume authStore

**DECISION**: `useAuth()` hook combina Zustand store (source-of-truth para tokens) con SWR cache (para datos derivados de `/auth/me`). Patrón:

```typescript
export function useAuth() {
  const { accessToken } = useAuthStore();
  const { data, error, isLoading, mutate } = useSWR<AuthMeResponse>(
    accessToken ? '/auth/me' : null,
    parkosFetch,
    {
      refreshInterval: 5 * 60 * 1000,  // 5 min — plan.md:1208 verbatim
      revalidateOnFocus: true,
      shouldRetryOnError: (err) => err?.status !== 401,
      onError: (err) => {
        if (err?.status === 401) useAuthStore.getState().clear();
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

**RATIONALE**: Zustand = tokens (small, sync, frequently updated); SWR = profile data (large, async, infrequently fetched). 5-minute refresh per plan.md:1208.

### 7.8 DEC-FETCH-08 — Bridge IPC typed surface (8 métodos) via bridge.d.ts

**DECISION**: `apps/electron-sucursal/electron/bridge.d.ts` define `BridgeSurface` interface con 8 métodos en 6 grupos (imprimir, usb, kiosk, app, apiStatus, authStore). `preload.ts` materializa via `contextBridge.exposeInMainWorld('bridge', {...})` con whitelist explícita (NO spread). Renderer importa tipos via `/// <reference types="../../electron/bridge.d.ts" />` en `src/renderer/global.d.ts`.

**RATIONALE**: Tipado end-to-end previene drift entre main y renderer. Si main cambia sin actualizar d.ts, `tsc --noEmit` falla en CI (G5 §11).

## 8. Riesgo y mitigaciones

| # | Risk | Severity | Mitigación |
|---|---|---|---|
| R1 | **Race condition 401 refresh** — 5 requests concurrentes con 401 disparan 5 refreshes paralelos | HIGH | DEC-FETCH-03: Mutex singleton en `refreshPromise`; solo UN refresh activo a la vez; los demás esperan |
| R2 | **electron-store stale key TTL** — refresh token expirado persiste | MEDIUM | DEC-FETCH-06: `clear()` en logout handler + en doble-401 fallido; partialize solo persiste {accessToken, refreshToken, expiresAt}; expiración validada en cada read |
| R3 | **Idempotency-Key collisions** en multi-tab | LOW (kiosko single-tab) | DEC-FETCH-04: SHA-256(method+path+body) garantiza uniqueness por contenido; kiosko Electron es single-tab por diseño (F2.3 single-instance lock) |
| R4 | **Bridge IPC type drift** — main process cambia handler sin actualizar d.ts | MEDIUM | DEC-FETCH-08: `bridge.contract.test.ts` valida shape en CI; tsc --noEmit catches drift |
| R5 | **Zod schema drift backend/frontend** | MEDIUM | DEC-FETCH-05: Zod validation en runtime catches drift en dev/test; auto-generación desde Pydantic DEFERRED a Fase 3 (forward hook) |
| R6 | **electron-store path differs across OS** — Windows / Linux / macOS tienen diferentes `app.getPath('userData')` | LOW | electron-store normaliza; plan F2.1 ya verificó 3-target support |
| R7 | **SHA-256 async overhead** — `crypto.subtle.digest` es async; impacta latency | LOW | Pre-computar key en build del request (no bloqueante) |
| R8 | **vitest fake timers + AbortController interaction** | LOW | `vi.useFakeTimers({ shouldAdvanceTime: true })` para preservar timers reales durante AbortController |

**Riesgos identificados y cerrados**: 8/8 con mitigación explícita. 0 KNOWN-MISSING.

## 9. Descomposición en clusters atómicos

F2.2 se descompone en **3 clusters** (C1, C2, C3) con orden obligatorio C1 → C2 → C3.

### 9.1 C1: parkosFetch + bridge typed surface + preload wiring (~230 LOC)

**Archivos**:
- `apps/ui-kit/src/fetch/parkosFetch.ts` (~120 LOC).
- `apps/ui-kit/src/fetch/parkosFetch.test.ts` (~120 LOC).
- `apps/ui-kit/src/fetch/index.ts` (~5 LOC).
- `apps/electron-sucursal/electron/bridge.d.ts` (~60 LOC).
- `apps/electron-sucursal/electron/preload.ts` (~50 LOC).

### 9.2 C2: authStore Zustand + useAuth() SWR hook (~130 LOC)

**Archivos**:
- `apps/ui-kit/src/store/authStore.ts` (~80 LOC).
- `apps/ui-kit/src/store/authStore.test.ts` (~60 LOC).
- `apps/ui-kit/src/hooks/useAuth.ts` (~50 LOC).
- `apps/ui-kit/src/hooks/useAuth.test.ts` (~40 LOC).

### 9.3 C3: 22 e2e auth scenarios + axe-core gate + bridge contract test (~190 LOC)

**Archivos**:
- `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` (~60 LOC).
- `apps/electron-sucursal/e2e/auth/bridge.spec.ts` (~50 LOC).
- `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (~30 LOC).
- `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` (~50 LOC).

### 9.4 Total estimado

- **C1**: ~230 LOC production + ~120 LOC tests = **~350 LOC**.
- **C2**: ~130 LOC production + ~100 LOC tests = **~230 LOC**.
- **C3**: ~190 LOC tests.
- **TOTAL**: ~550 LOC production + ~410 LOC tests = **~960 LOC**.

Plan 450 LOC matches: 450 ≈ 550 production - 100 LOC reutilizados de apps/web_admin/src/lib/fetch.ts que se mueven a ui-kit (counted once).

### 9.5 Orden de ejecución

C1 → C2 → C3 (mandatory). C1 antes de C2 porque useAuth() consume parkosFetch (C1). C2 antes de C3 porque e2e tests necesitan authStore para login flow.

## 10. Atomic tasks T1..T7 con budgets LOC

Cada task es **atómica** (commiteable independientemente con tests verdes), pero se ejecutan en orden T1 → T7.

### 10.1 T1 — Extraer y extender parkosFetch en ui-kit

**Budget**: ~120 LOC production + ~120 LOC tests = **~240 LOC**.

**Archivos**:
- `apps/ui-kit/src/fetch/parkosFetch.ts` (NEW, ~120 LOC).
- `apps/ui-kit/src/fetch/parkosFetch.test.ts` (NEW, ~120 LOC).
- `apps/ui-kit/src/fetch/index.ts` (NEW, ~5 LOC).
- `apps/ui-kit/package.json` (MODIFY, agregar zod + swr peerDeps).
- `apps/web_admin/src/lib/fetch.ts` (MODIFY, ~10 LOC — re-export desde ui-kit).

**Commit message**: `feat(ui-kit): adicionar parkosFetch con retry 5xx, refresh-once 401, Idempotency-Key SHA-256, Zod validation, AbortController timeout`

**Acceptance** (G1, G2, G3, G4 — §11): 14 unit tests MSW verde; cobertura >90%; tsc --noEmit limpio; web_admin existing consumers funcionan sin cambios.

### 10.2 T2 — bridge.d.ts typed surface en electron-sucursal

**Budget**: ~60 LOC.

**Archivos**:
- `apps/electron-sucursal/electron/bridge.d.ts` (NEW, ~60 LOC).
- `apps/electron-sucursal/tsconfig.main.json` (MODIFY, agregar .d.ts a include).

**Commit message**: `feat(electron): adicionar bridge IPC typed surface en bridge.d.ts con 8 métodos (imprimir, usb, kiosk, app, apiStatus, authStore)`

**Acceptance** (G5): tsc --noEmit limpio; BridgeSurface interface exportada; global `window.bridge` declaration funciona.

### 10.3 T3 — preload.ts IPC wiring en electron-sucursal

**Budget**: ~50 LOC production + ~50 LOC tests = **~100 LOC**.

**Archivos**:
- `apps/electron-sucursal/electron/preload.ts` (MODIFY, 11 → ~50 LOC).
- `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` (NEW, ~50 LOC).

**Commit message**: `feat(electron): wire bridge IPC handlers en preload con whitelist de 8 métodos`

**Acceptance** (G5, G8): contextBridge.exposeInMainWorld expone exactamente los 8 métodos; preload.contract.test.ts valida que cada método del d.ts está implementado en preload; whitelist filtering: ningún `ipcRenderer` raw expuesto.

### 10.4 T4 — authStore Zustand + persist en ui-kit

**Budget**: ~80 LOC production + ~60 LOC tests = **~140 LOC**.

**Archivos**:
- `apps/ui-kit/src/store/authStore.ts` (NEW, ~80 LOC).
- `apps/ui-kit/src/store/authStore.test.ts` (NEW, ~60 LOC).
- `apps/ui-kit/package.json` (MODIFY, agregar zustand dep).

**Commit message**: `feat(ui-kit): adicionar authStore Zustand con persist electron-store y Mutex refresh-once`

**Acceptance** (G6): 8 unit tests verde; setTokens/clear/getState funcionan; electron-store adapter invoca bridge.authStore.{get,set,delete}; partialize excluye campos derivados.

### 10.5 T5 — useAuth() SWR hook en ui-kit

**Budget**: ~50 LOC production + ~40 LOC tests = **~90 LOC**.

**Archivos**:
- `apps/ui-kit/src/hooks/useAuth.ts` (NEW, ~50 LOC).
- `apps/ui-kit/src/hooks/useAuth.test.ts` (NEW, ~40 LOC).

**Commit message**: `feat(ui-kit): adicionar useAuth SWR hook con refresh 5min y auto-clear en 401`

**Acceptance** (G7): 5 unit tests verde; refreshInterval: 5*60*1000 verbatim; onError con status===401 dispara clear().

### 10.6 T6 — 22 e2e auth scenarios (14 parkosFetch + 8 bridge)

**Budget**: ~110 LOC.

**Archivos**:
- `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` (NEW, ~60 LOC).
- `apps/electron-sucursal/e2e/auth/bridge.spec.ts` (NEW, ~50 LOC).

**Commit message**: `test(electron): adicionar 22 e2e auth scenarios via MSW (14 parkosFetch + 8 bridge)`

**Acceptance** (G8): 14 parkosFetch scenarios verde (per plan.md:1214-1227 verbatim); 8 bridge scenarios verde (per plan.md:1229 verbatim); cobertura >90% verificada.

### 10.7 T7 — axe-core WCAG 2.1 AA gate

**Budget**: ~30 LOC.

**Archivos**:
- `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (NEW, ~30 LOC).

**Commit message**: `test(electron): adicionar axe-core WCAG 2.1 AA gate (RNF-022)`

**Acceptance** (RNF-022): axe-core scan retorna 0 violaciones con tags ['wcag2a','wcag2aa','wcag21a','wcag21aa'].

### 10.8 Resumen de budgets

| Task | Production LOC | Tests LOC | Total |
|---|---|---|---|
| T1 parkosFetch | 120 | 120 | 240 |
| T2 bridge.d.ts | 60 | 0 | 60 |
| T3 preload.ts | 50 | 50 | 100 |
| T4 authStore | 80 | 60 | 140 |
| T5 useAuth | 50 | 40 | 90 |
| T6 e2e auth | 0 | 110 | 110 |
| T7 axe-core | 0 | 30 | 30 |
| **TOTAL** | **360** | **410** | **770** |

Total real ~850-900 LOC incluyendo configs y JSDoc.

## 11. Acceptance gates pre-flight

8 gates que deben pasar ANTES de mergear F2.2 a main.

| # | Gate | Mecanismo | Source |
|---|---|---|---|
| G1 | parkosFetch retries 5xx + 408 con backoff correcto | unit test MSW con vi.useFakeTimers() | T1 |
| G2 | parkosFetch emite 401 refresh-once y reintenta request original | unit test MSW con Mutex validation | T1 |
| G3 | parkosFetch emite Idempotency-Key SHA-256 en POST mutacionales | unit test MSW con hash assertion | T1 |
| G4 | parkosFetch valida respuesta con Zod schema y lanza ZodError | unit test MSW con schema inválido | T1 |
| G5 | bridge IPC typed surface compilable sin `any` | tsc --noEmit clean | T2 |
| G6 | authStore persiste + restaura desde electron-store | unit test con mock bridge.authStore | T4 |
| G7 | useAuth() hidrata desde /auth/me con SWR cache + Zustand store | unit test con SWR config mock | T5 |
| G8 | 22 e2e auth scenarios verde + axe-core 0 violaciones | playwright e2e + axe-core | T6 + T7 |

**Estado pre-flight**: 0/8 PASS al inicio (no implementado). Target 8/8 PASS post-implementación.

## 12. Pre-flight checks ya cerrados

10 checks verificados antes de empezar implementación:

| # | Check | Source | Result |
|---|---|---|---|
| 1 | plan.md HU-F2.2 existe con 7 tasks + 14 e2e + 8 bridge | plan.md:1198-1240 | PASS |
| 2 | parkosFetch existente en web_admin funcional | apps/web_admin/src/lib/fetch.ts:1-66 | PASS |
| 3 | preload.ts contextBridge vacío pero seam presente | apps/electron-sucursal/electron/preload.ts:1-11 | PASS |
| 4 | Backend 4 endpoints /auth/{login,refresh,logout,me} existen | backend/.../auth.py:148-583 | PASS |
| 5 | Pydantic schemas LoginRequest + TokenPair + AuthMeResponse existen | backend/.../schemas/auth.py:243-321 | PASS |
| 6 | apps/ui-kit workspace package shipped (F2.1 DEC-ELEC-08) | F2.1 archivado | PASS |
| 7 | electron-store dep disponible | apps/electron-sucursal/package.json (F2.1) | PASS |
| 8 | SWR + Zustand + Zod ya en stack web_admin | apps/web_admin/package.json | PASS |
| 9 | Vitest + MSW + axe-core + Playwright _electron ya integrados | F2.1 e2e + RNF-022 | PASS |
| 10 | apps/package.json workspaces incluye electron-sucursal | F2.1 DEC-ELEC-01 | PASS |

Result: 10/10 PASS. Pre-flight gate PASS. F2.2 ready for sdd-propose. 0 KNOWN-MISSING.

## 13. Out of scope Fase 2

F2.2 NO incluye (explícitamente deferido a Fase 3+):

- **Backend `/health` endpoint** — necesario para `bridge.apiStatus.get()`. F2.3 lo crea.
- **Generación automática de Zod schemas desde Pydantic** — vía `datamodel-code-generator`.
- **Refresh-token rotation detection** — PR1b no rota; F2.2 trata refresh token como long-lived.
- **Multi-tab login UI** — kiosko single-tab por F2.3 lock.
- **2FA / WebAuthn** — futuro.
- **Login UI** — F3.1.
- **Lockout + countdown UI** — F3.2.
- **Turno abrir/cerrar** — F3.3.
- **Auto-update** — F2.3.
- **Single-instance lock** — F2.3.
- **Kiosko mode PIN bcrypt** — F2.3.
- **Logging (electron-log rotation)** — F2.3.
- **Ingreso de vehículo / Salida / Facturación / Caja / Anulación / Alertas / Reclamo / Reimpresión / Clientes list** — IT-3..IT-10.

## 14. Forward hooks (a Fase 3+)

| HU Forward | Consumer | Mecanismo |
|---|---|---|
| **HU-F3.1** (login email+password) | useAuth() + parkosFetch | Form dispara parkosFetch → setTokens → redirect |
| **HU-F3.2** (lockout visible) | parkosFetch retry logic + useCountdown hook | 429 con Retry-After → countdown |
| **HU-F3.3** (abrir/cerrar turno) | authStore + bridge | abrir/cerrar turno, logout limpia todo |
| **HU-F5.1+** (impresión térmica) | bridge.imprimir | useThermalPrint() hook con retry + queue offline |
| **HU-F11.x** (sync UI) | bridge.apiStatus.get | StatusBar component consulta cada 30s |
| **HU-F2.3** (auto-update + kiosko) | bridge.kiosk.toggle + bridge.app.quit | F2.3 wire main process handlers reales |
| **PR7 backend** (refresh rotation) | authStore + refresh logic | Detección de reuse jti claim |

## 15. Convenciones del proyecto

### 15.1 Commits

- Conventional Commits.
- NO "Co-Authored-By" attribution.
- Formato: `<type>(<scope>): <description>` con type ∈ {feat, fix, test, refactor, docs, chore}, scope ∈ {ui-kit, electron, web, ops}.

### 15.2 TDD estricto

- Cada test escrito ANTES de la implementación.
- Tests rojos primero, luego código que los hace verde.
- Cobertura >90% exigida en parkosFetch.ts.
- Cobertura >80% en authStore.ts y useAuth.ts.

### 15.3 Defense in depth

5 capas (XR6 pattern per operations/spec.md:3951):

| Layer | Mechanism | Source |
|---|---|---|
| 1 auth | JWT Bearer + refresh rotation | backend/.../auth.py:148-583 (no F2.2 scope) |
| 2 engineering | TS strict + noUncheckedIndexedAccess + ESLint flat | tsconfig.* + eslint.config.js |
| 3 a11y | axe-core WCAG 2.1 AA | e2e/a11y/wcag-2.1-aa.spec.ts (T7) |
| 4 contract | Zod validation + bridge.d.ts shape | parkosFetch<T>(url, schema) + bridge.contract.test.ts |
| 5 retry-budget | Retry 3x + timeout AbortController + Mutex refresh | parkosFetch.ts (T1) |

F2.2 NO crea un nuevo REQ-OPS-XR (F2.2 NO es XR-class; las decisiones viven en proposal.md como DEC-FETCH-NN per F2.1 DEC-ELEC-10 precedent).

### 15.4 REQ-OPS-NNN additions (forward — proposal phase)

Si la propuesta F2.2 decide crear REQs de comportamiento, el patrón es:
- `REQ-OPS-106` — `parkosFetch retries 5xx with backoff 300/600/1200ms`
- `REQ-OPS-107` — `parkosFetch triggers single 401 refresh via POST /auth/refresh`
- `REQ-OPS-108` — `parkosFetch emits Idempotency-Key SHA-256(method+path+body) on POST/PUT/DELETE`
- `REQ-OPS-109` — `parkosFetch validates response via Zod schema`
- `REQ-OPS-110` — `authStore persists access+refresh tokens via electron-store`
- `REQ-OPS-111` — `useAuth hook fetches /auth/me every 5 minutes via SWR`
- `REQ-OPS-112` — `bridge.imprimir invokes escpos-usb with PrintPayload`

La propuesta F2.2 decide si agrega REQs o solo DECs.

## 16. Estimación total

### 16.1 Production LOC

- C1 (parkosFetch + bridge + preload): ~230 LOC.
- C2 (authStore + useAuth): ~130 LOC.
- Total production: **~360 LOC** + **~50 LOC** configs/package.json edits + **~30 LOC** comentarios JSDoc = **~440 LOC**.

### 16.2 Test LOC

- parkosFetch.test.ts: ~120 LOC.
- preload.contract.test.ts: ~50 LOC.
- authStore.test.ts: ~60 LOC.
- useAuth.test.ts: ~40 LOC.
- e2e/auth/parkos-fetch.spec.ts: ~60 LOC.
- e2e/auth/bridge.spec.ts: ~50 LOC.
- e2e/a11y/wcag-2.1-aa.spec.ts: ~30 LOC.
- Total tests: **~410 LOC**.

### 16.3 Gran total

~440 LOC production + ~410 LOC tests = **~850 LOC**.

### 16.4 Timeline estimado

| Fase | Duración estimada | Owner |
|---|---|---|
| sdd-propose | 1 sesión | orchestrator |
| sdd-apply T1..T7 | 3-4 sesiones | sdd-apply (7 atomic commits) |
| sdd-verify | 1 sesión | sdd-verify |
| archive | 0.5 sesión | orchestrator |

## 17. Apéndice: archivos a tocar

### 17.1 NEW (crear)

- `apps/ui-kit/src/fetch/parkosFetch.ts` (T1)
- `apps/ui-kit/src/fetch/parkosFetch.test.ts` (T1)
- `apps/ui-kit/src/fetch/index.ts` (T1)
- `apps/ui-kit/src/store/authStore.ts` (T4)
- `apps/ui-kit/src/store/authStore.test.ts` (T4)
- `apps/ui-kit/src/hooks/useAuth.ts` (T5)
- `apps/ui-kit/src/hooks/useAuth.test.ts` (T5)
- `apps/electron-sucursal/electron/bridge.d.ts` (T2)
- `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` (T3)
- `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` (T6)
- `apps/electron-sucursal/e2e/auth/bridge.spec.ts` (T6)
- `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (T7)

### 17.2 MODIFY (extender)

- `apps/web_admin/src/lib/fetch.ts` (T1 — convierte a re-export).
- `apps/electron-sucursal/electron/preload.ts` (T3 — 11 → ~50 LOC).
- `apps/electron-sucursal/tsconfig.main.json` (T2 — agregar .d.ts a include).
- `apps/ui-kit/package.json` (T1 + T4 — agregar zod + zustand + swr deps).
- `apps/electron-sucursal/package.json` (sin nuevas deps).

### 17.3 READ ONLY (anchors — NO modificar)

- `apps/web_admin/src/lib/sucursal-context.ts`.
- `backend/.../api/v1/auth.py`.
- `backend/.../schemas/auth.py`.
- `apps/ui-kit/src/{Button,cn,tokens}.{tsx,ts}`.
- `apps/electron-sucursal/electron/main.ts` (handlers se mockean; F2.3 los conecta).
- `openspec/specs/operations/spec.md`.

### 17.4 Total de archivos impactados

- **NEW**: 12 archivos (~850 LOC).
- **MODIFY**: 5 archivos (~70 LOC delta).
- **READ ONLY**: 6 archivos.
- **TOTAL IMPACT**: 17 archivos de 850 LOC nuevos + 70 LOC delta.

---

End of exploration.
