# Tasks — HU-F2.2 Cliente HTTP parkosFetch + IPC bridge + authStore

> Estado: drafted (sdd-tasks)
> Fecha: 2026-09-15
> Branch: `feat/fase-2-electron-scaffold`
> Cross-refs: `proposal.md` §15, `design.md` §14, `exploration.md` §8-§10
> Prereq change: `hu-f2-1-electron-scaffold` archived

## 0. Metadata

| Campo | Valor |
|---|---|
| Change | `hu-f2-2-parkos-fetch-ipc-auth-store` |
| HU | F2.2 — Cliente HTTP `parkosFetch` + IPC bridge + `authStore` Zustand |
| Owner | Parkos Dev <dev@parkos.local> |
| Working tree | `E:\easypunto_parkos` |
| Branch base | `feat/fase-2-electron-scaffold` (F2.1 ya merged) |
| PR target | `feat/fase-2-electron-scaffold` (intra-fase, no a main) |
| Total tasks | 7 atomic (T1..T7) |
| Total clusters | 4 (C1 implementacion + C2 implementacion + C3 testing + C4 archive) |
| Production LOC budget | ~770 LOC (delta sobre F2.1) |
| Test LOC budget | ~410 LOC |
| Total LOC budget | ~1180 LOC |
| Atomic commits | 7 (C1: T1,T2,T3 + C2: T4,T5 + C3: T6,T7) + 2 archive (C4) |
| Review actor | `sdd-verify` post-apply |
| Archive actor | orchestrator (post-verify) |

## 1. Resumen de clusters

| Cluster | Tasks | Tipo | LOC prod | LOC tests | Commit prefix |
|---|---|---|---|---|---|
| C1 — HTTP infra + IPC bridge | T1, T2, T3 | feature | ~400 | ~120 | `feat(ui-kit|electron)` |
| C2 — State management | T4, T5 | feature | ~130 | ~100 | `feat(ui-kit)` |
| C3 — Testing & a11y gates | T6, T7 | test | 0 | ~190 | `test(electron)` |
| C4 — Verify + archive | (orchestrator) | chore | 0 | 0 | `chore(docs)` |
| **TOTAL** | **7 atomic + 2 archive** | mixed | **~770** | **~410** | — |

**Paralelización intra-cluster**:
- T1 → T2 pueden ejecutarse en paralelo (T2 solo necesita T1 conceptual, no funcional).
- T3 depende de T2 (preload consume d.ts).
- T4 depende de T3 (authStore invoca `bridge.authStore.get/set/delete`).
- T5 depende de T4 (useAuth consume useAuthStore).
- T6 depende de T1..T5 (e2e necesita infra completa).
- T7 depende de T6 (axe corre sobre routes con auth completo).

**Dependencias entre clusters**:
- C1 (T1..T3) → C2 (T4..T5) → C3 (T6..T7) → C4 (verify + archive).

## 2. Convenciones (cross-ref proposal §15 + design §14)

- **Conventional commits neutrales en español** (ver §10 design).
- **NO trailers**: confirmar sin `Co-authored-by`, sin firmas IA, sin trailers Signed-off-by automáticos.
- **TDD estricto**: RED → GREEN → REFACTOR en cada task. Ningún commit con tests rojos.
- **Defense in depth XR6 layers**:
  - Layer 1 — `parkosFetch` (request shape: idempotency, retry, timeout).
  - Layer 2 — `bridge.authStore` (persist electron-store).
  - Layer 3 — `authStore` Zustand (estado en memoria + Mutex).
  - Layer 4 — `useAuth` SWR (refresh + 401 handling).
  - Layer 5 — preload `contextBridge` (whitelist filtering).
  - Layer 6 — main process IPC handlers (validate ctx isolation).
- **Naming**:
  - `parkosFetch` (camelCase, sin `F` mayúscula) — ver proposal §3.
  - `BridgeSurface` interface export.
  - `useAuthStore` selector hook + `useAuth` SWR hook.
- **Localization**: mensajes de error UI en i18n namespace `errors` (F2.1 ya tiene 7 namespaces).
- **Coverage thresholds** (vitest):
  - `parkosFetch.ts` ≥90%.
  - `authStore.ts` ≥80%.
  - `useAuth.ts` ≥80%.

## 3. Cluster C1 — Infraestructura HTTP + Bridge IPC (T1, T2, T3)

### C1.0 Pre-requisitos

- branch: `feat/fase-2-electron-scaffold` checked out.
- working tree: `clean` (`git status --short` retorna vacío).
- pre-flight local:
  - `pnpm --filter @parkos/ui-kit test --run` verde.
  - `pnpm --filter @parkos/web_admin tsc --noEmit` clean.
  - `pnpm --filter @parkos/electron-sucursal tsc --noEmit` clean (main + renderer).
- F2.1 ya archivado en `openspec/changes/archive/2026-09-15-hu-f2-1-electron-scaffold/`.

### T1 — Extraer y extender parkosFetch en ui-kit

**Type**: feature
**Atomicidad**: sí (1 commit, ~240 LOC delta)
**Order**: 1 (primera del cambio)
**Cluster**: C1
**Pre-requisitos**: F2.1 cerrado

**Files**:
- NEW: `apps/ui-kit/src/fetch/parkosFetch.ts` (~120 LOC)
- NEW: `apps/ui-kit/src/fetch/parkosFetch.test.ts` (~120 LOC, 14 escenarios MSW)
- NEW: `apps/ui-kit/src/fetch/index.ts` (~5 LOC, barrel export)
- MODIFY: `apps/ui-kit/package.json` (~+10 LOC, agregar `zod@^3.23.0` y `swr@^2.2.5` en `peerDependencies`; `msw@^2.4.0` y `vitest@^1.6.0` en `devDependencies`)
- MODIFY: `apps/web_admin/src/lib/fetch.ts` (~-50 / +10 LOC, re-export `parkosFetch` desde `@parkos/ui-kit`)

**Acceptance gates** (verificación):
- G1: `parkosFetch` retries 5xx + 408 con backoff 300/600/1200 ms (jitter ±20%) — 5 unit tests MSW verde.
- G2: 401 refresh-once Mutex (Promise singleton; segundo 401 concurrent rechaza con error tipado) — 2 unit tests verde con Mutex validation.
- G3: `Idempotency-Key` SHA-256 determinístico sobre `method|path|body` — 2 unit tests verde con hash assertion (`/^[0-9a-f]{64}$/`).
- G4: Zod validation lanza `ZodError` con `error.flatten()` enriquecido — 2 unit tests verde con schema inválido.
- `parkosFetch.test.ts` cobertura ≥90% (verified via `vitest --coverage`).
- `tsc --noEmit` limpio en `apps/ui-kit/` y `apps/web_admin/`.
- `web_admin` consumers (`sucursal-context.ts` y demás) siguen funcionando sin cambios (import path compatible: `@/lib/fetch` re-exporta `parkosFetch`).
- Backoff sequence verificada con `vi.useFakeTimers({ shouldAdvanceTime: true })` y assertion sobre `vi.advanceTimersByTimeAsync`.

**Commit message**:

```
feat(ui-kit): adicionar parkosFetch con retry 5xx, refresh-once 401, Idempotency-Key SHA-256, Zod validation, AbortController timeout
```

**Author**: `Parkos Dev <dev@parkos.local>`
**No trailers**: confirmar sin `Co-authored-by`, sin trailers IA, sin Signed-off-by.

---

### T2 — `bridge.d.ts` typed surface en electron-sucursal

**Type**: feature
**Atomicidad**: sí (1 commit, ~60 LOC)
**Order**: 2
**Cluster**: C1
**Pre-requisitos**: T1 completado (parkosFetch ya existe, aunque T2 no lo consume — son funcionalmente independientes; T2 solo necesita F2.1 cerrado).

**Files**:
- NEW: `apps/electron-sucursal/electron/bridge.d.ts` (~60 LOC)
- MODIFY: `apps/electron-sucursal/tsconfig.main.json` (agregar `"include": ["electron/**/*.ts", "electron/**/*.d.ts"]`)

**Acceptance gates**:
- G5 parcial: bridge IPC typed surface compilable sin `any` (`tsc --noEmit` limpio en `electron-sucursal/main + renderer`).
- `BridgeSurface` interface exportada con 8 métodos en 6 grupos:
  - `imprimir` group: `{ imprimir: (payload: PrintPayload) => Promise<PrintResult> }`.
  - `usb` group: `{ list: () => Promise<UsbDevice[]> }`.
  - `kiosk` group: `{ toggle: () => Promise<{ active: boolean }> }`.
  - `app` group: `{ quit: () => Promise<void>; version: () => Promise<string> }`.
  - `apiStatus` group: `{ get: () => Promise<{ ok: boolean; latencyMs: number }> }`.
  - `authStore` group: `{ get: () => Promise<AuthPersisted>; set: (data: AuthPersisted) => Promise<void>; delete: () => Promise<void> }`.
- Global `window.bridge: BridgeSurface` declaration funcional en `electron/bridge.d.ts`.
- Sin uso de `any` (verificado por `tsc --strict --noImplicitAny`).

**Commit message**:

```
feat(electron): adicionar bridge IPC typed surface en bridge.d.ts con 8 métodos (imprimir, usb, kiosk, app, apiStatus, authStore)
```

**Author**: `Parkos Dev <dev@parkos.local>`

---

### T3 — `preload.ts` IPC wiring en electron-sucursal

**Type**: feature
**Atomicidad**: sí (1 commit, ~100 LOC delta)
**Order**: 3
**Cluster**: C1
**Pre-requisitos**: T2 completado (`bridge.d.ts` debe existir antes que `preload.ts` lo implemente — `tsc` lo exige).

**Files**:
- MODIFY: `apps/electron-sucursal/electron/preload.ts` (11 LOC → ~50 LOC)
- NEW: `apps/electron-sucursal/electron/__tests__/preload.contract.test.ts` (~50 LOC)

**Acceptance gates**:
- G5: contract test valida que cada método del `d.ts` está implementado en `preload` (8 `it()` blocks verde, uno por método).
- Whitelist filtering: ningún `ipcRenderer` raw expuesto en `window.*` (verificado por inspection + contract test).
- `contextBridge.exposeInMainWorld('bridge', ...)` expone exactamente 8 métodos en 6 grupos.
- Error mapping: errores IPC se serializan como `{ code: string; message: string; cause?: unknown }`.

**Commit message**:

```
feat(electron): wire bridge IPC handlers en preload con whitelist de 8 métodos
```

**Author**: `Parkos Dev <dev@parkos.local>`

---

## 4. Cluster C2 — State management (T4, T5)

### T4 — `authStore` Zustand + persist electron-store en ui-kit

**Type**: feature
**Atomicidad**: sí (1 commit, ~140 LOC delta)
**Order**: 4 (post-C1)
**Cluster**: C2
**Pre-requisitos**: T3 completado (`authStore.ts` necesita `window.bridge.authStore.{get,set,delete}` expuestos por T3).

**Files**:
- NEW: `apps/ui-kit/src/store/authStore.ts` (~80 LOC)
- NEW: `apps/ui-kit/src/store/authStore.test.ts` (~60 LOC, 8 escenarios unit)
- MODIFY: `apps/ui-kit/package.json` (agregar `zustand@^4.5.0` en `dependencies`)

**Acceptance gates** (G6):
- 8 unit tests verde:
  1. `setTokens` actualiza estado + invoca `bridge.authStore.set`.
  2. `clear` resetea estado + invoca `bridge.authStore.delete`.
  3. `getState` retorna estado actual sincronizado.
  4. `persist read` carga desde electron-store al iniciar.
  5. `persist write` serializa a electron-store en cada cambio.
  6. `persist delete` borra electron-store en `clear`.
  7. `partialize` excluye campos derivados (solo `accessToken`, `refreshToken`, `expiresAt`).
  8. Mutex refresh: dos `setTokens` concurrentes serializan vía Promise singleton.
- `electron-store` adapter invoca `window.bridge.authStore.{get,set,delete}` correctamente (mockeado en tests con `vi.stubGlobal('window', { bridge: ... })`).
- `partialize` excluye campos derivados (solo `accessToken`, `refreshToken`, `expiresAt`).
- `clear()` invocable en logout handler + doble-401 fallido.

**Commit message**:

```
feat(ui-kit): adicionar authStore Zustand con persist electron-store y Mutex refresh-once
```

**Author**: `Parkos Dev <dev@parkos.local>`

---

### T5 — `useAuth()` SWR hook en ui-kit

**Type**: feature
**Atomicidad**: sí (1 commit, ~90 LOC delta)
**Order**: 5 (post-T4)
**Cluster**: C2
**Pre-requisitos**: T4 completado (`useAuth` consume `useAuthStore`).

**Files**:
- NEW: `apps/ui-kit/src/hooks/useAuth.ts` (~50 LOC)
- NEW: `apps/ui-kit/src/hooks/useAuth.test.ts` (~40 LOC, 5 escenarios unit)

**Acceptance gates** (G7):
- 5 unit tests verde:
  1. No auth (sin `accessToken`) → `data` es `null`, `isAuthenticated` es `false`, no fetch.
  2. With auth (con `accessToken` válido) → SWR fetcha `/me` con Bearer.
  3. 401 handling: `onError` con `status === 401` dispara `useAuthStore.getState().clear()`.
  4. Refresh mutation: SWR `mutate()` re-fetcha `/me` sin re-disparar refresh interno.
  5. `isAuthenticated` derivation: deriva de `useAuthStore.getState().accessToken !== null` y `!isExpired`.
- `refreshInterval: 5 * 60 * 1000` verbatim per `plan.md:1208`.
- `shouldRetryOnError: false` en 401 (otros errores sí retry x2).
- `onError` con `status === 401` dispara `useAuthStore.getState().clear()`.
- SWR `key: null` cuando `!accessToken` (no fetch redundante).

**Commit message**:

```
feat(ui-kit): adicionar useAuth SWR hook con refresh 5min y auto-clear en 401
```

**Author**: `Parkos Dev <dev@parkos.local>`

---

## 5. Cluster C3 — Testing & accessibility gates (T6, T7)

### T6 — 22 e2e auth scenarios via MSW

**Type**: test
**Atomicidad**: sí (1 commit, ~110 LOC delta tests only)
**Order**: 6 (post-C2)
**Cluster**: C3
**Pre-requisitos**: T1..T5 completados (e2e tests necesitan infra completa para correr).

**Files**:
- NEW: `apps/electron-sucursal/e2e/auth/parkos-fetch.spec.ts` (~60 LOC, 14 escenarios)
- NEW: `apps/electron-sucursal/e2e/auth/bridge.spec.ts` (~50 LOC, 8 escenarios)

**Acceptance gates** (G8 parcial):
- 14 `parkosFetch` scenarios verde per `plan.md:1214-1227` verbatim:
  1. GET exitoso sin cabeceras extra.
  2. POST incluye `Idempotency-Key` SHA-256(`method|path|body`).
  3. Dos POST idénticos producen mismo `Idempotency-Key` (idempotencia).
  4. `X-Sucursal-Context` presente en toda mutación (POST/PUT/PATCH/DELETE).
  5. 5xx reintenta con backoff 300 ms.
  6. Segundo reintento a 600 ms.
  7. Tercer reintento a 1200 ms.
  8. Agotados 3 reintentos, propaga el error (status final visible).
  9. 4xx no dispara ningún reintento (assert `expect(spy).toHaveBeenCalledTimes(1)`).
  10. 401 dispara refresh único.
  11. Refresh exitoso reintenta automáticamente (request original con nuevo Bearer).
  12. Segundo 401 consecutivo limpia `authStore` (`bridge.authStore.delete` invocado).
  13. `NetworkError` (sin conexión, `error.code === 'ECONNREFUSED'`) trata como 5xx.
  14. Timeout con `timeoutMs: 1000` aborta vía `AbortController` (`AbortError` propagado).
- 8 `bridge` scenarios verde per `plan.md:1229` verbatim:
  1. `imprimir` OK con `PrintPayload` válido.
  2. `imprimir` con `printer_offline` (error tipado).
  3. `usb.list` retorna array vacío.
  4. `usb.list` con 2 dispositivos mockeados.
  5. `kiosk.toggle` activa (`{ active: true }`).
  6. `kiosk.toggle` desactiva (`{ active: false }`).
  7. `app.quit` invoca `app.exit(0)` (verificado por spy).
  8. `apiStatus.get` retorna `{ ok: true, latencyMs: 23 }`.
- Cobertura >90% en `parkosFetch.ts` verificada post-tests via `vitest --coverage`.

**Commit message**:

```
test(electron): adicionar 22 e2e auth scenarios via MSW (14 parkosFetch + 8 bridge)
```

**Author**: `Parkos Dev <dev@parkos.local>`

---

### T7 — axe-core WCAG 2.1 AA gate

**Type**: test
**Atomicidad**: sí (1 commit, ~30 LOC delta tests only)
**Order**: 7 (post-T6, última implementación)
**Cluster**: C3
**Pre-requisitos**: T6 completado (axe-core corre sobre routes con auth completo).

**Files**:
- NEW: `apps/electron-sucursal/e2e/a11y/wcag-2.1-aa.spec.ts` (~30 LOC)

**Acceptance gates** (RNF-022):
- axe-core scan en `/login` (placeholder F3.1) y `/` (placeholder F2.1 router) retorna **0 violaciones** con tags `['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']`.
- `AxeBuilder` importado desde `@axe-core/playwright`.
- Helper `runAxe(page, path)` reusable para futuros cambios (F3.x).

**Commit message**:

```
test(electron): adicionar axe-core WCAG 2.1 AA gate (RNF-022)
```

**Author**: `Parkos Dev <dev@parkos.local>`

---

## 6. Cluster C4 — Verificación y archivo (post-apply)

### C4.0 Pre-archive housekeeping

- `verify-report.md` (~560 LOC) authored por sub-agente `sdd-verify` (post-apply).
- `archive-report.md` (~500 LOC) authored por orchestrator (post-verify PASS).
- `git mv openspec/changes/hu-f2-2-parkos-fetch-ipc-auth-store/ openspec/changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/`.
- update `pending.md`: marcar F2.2 cerrado.
- 2 atomic commits:
  1. `chore(docs): archivar change hu-f2-2-parkos-fetch-ipc-auth-store con 9 artefactos SDD` (proposal + exploration + design + tasks + verify + archive + ...).
  2. `chore(docs): pending.md marcar HU-F2.2 cerrado tras archive`.

### C4.1 Verificación previa al archive (sdd-verify)

- 8/8 acceptance gates PASS (G1..G8).
- Cobertura cumplida (parkosFetch ≥90%, authStore ≥80%, useAuth ≥80%).
- 0 regresiones en F1 / F2.1.
- Sin trailers IA en los 7 commits de implementación.
- Branch limpio, working tree clean.

### C4.2 Archive

- Directorio movido a `changes/archive/2026-09-15-hu-f2-2-parkos-fetch-ipc-auth-store/`.
- `pending.md` actualizado.
- Tag opcional `f2.2-complete` en `feat/fase-2-electron-scaffold` (decisión orchestrator).

---

## 7. DoD global (Definition of Done — cross-ref proposal §15)

- [ ] 7 atomic commits T1..T7 en `feat/fase-2-electron-scaffold` con author `Parkos Dev`, sin `Co-authored-by`, sin trailers IA.
- [ ] 8/8 acceptance gates PASS (G1..G8).
- [ ] `parkosFetch.ts` cobertura ≥90%.
- [ ] `authStore.ts` cobertura ≥80%.
- [ ] `useAuth.ts` cobertura ≥80%.
- [ ] `tsc --noEmit` limpio en `ui-kit` + `web_admin` + `electron-sucursal` (main + renderer).
- [ ] `vitest --run` en `ui-kit` verde.
- [ ] `playwright e2e` 22/22 verde.
- [ ] axe-core 0 violaciones WCAG 2.1 AA en `/login` y `/`.
- [ ] 0 regresiones en F1/F2.1 (ver `design.md` §11 compatibility).
- [ ] `docs/README.md` actualizados (`ui-kit` + `electron-sucursal`).
- [ ] `git status --short` retorna solo M legítimos o nada.
- [ ] Branch limpio, working tree clean pre-archive.
- [ ] 2 atomic commits `chore(docs)` post-verify (archive + pending.md).

---

## 8. Mapa de ejecución (visual)

```
Día 1 (C1):
  ├─ git checkout feat/fase-2-electron-scaffold
  ├─ T1: parkosFetch.ui-kit (~240 LOC, ~30 min)
  │   └─ git commit "feat(ui-kit): adicionar parkosFetch..."
  ├─ T2: bridge.d.ts (~60 LOC, ~10 min)
  │   └─ git commit "feat(electron): adicionar bridge IPC typed surface..."
  └─ T3: preload.ts IPC (~100 LOC, ~15 min)
      └─ git commit "feat(electron): wire bridge IPC handlers..."

Día 2 (C2):
  ├─ T4: authStore.ui-kit (~140 LOC, ~25 min)
  │   └─ git commit "feat(ui-kit): adicionar authStore..."
  └─ T5: useAuth.ui-kit (~90 LOC, ~15 min)
      └─ git commit "feat(ui-kit): adicionar useAuth SWR hook..."

Día 3 (C3):
  ├─ T6: 22 e2e scenarios (~110 LOC, ~30 min)
  │   └─ git commit "test(electron): adicionar 22 e2e auth scenarios..."
  └─ T7: axe-core gate (~30 LOC, ~10 min)
      └─ git commit "test(electron): adicionar axe-core WCAG 2.1 AA gate..."

Día 4 (C4):
  ├─ sdd-verify → verify-report.md (~560 LOC)
  ├─ sdd-archive → archive-report.md (~500 LOC)
  ├─ git mv changes → changes/archive
  ├─ update pending.md
  └─ 2 atomic commits chore(docs)
```

---

## 9. Riesgos por task (cross-ref exploration §8 + design §11)

| Task | Riesgos aplicables | Mitigación |
|---|---|---|
| T1 | R7 (SHA-256 async), R8 (fake timers + AbortController) | pre-computar key en build request; `vi.useFakeTimers({ shouldAdvanceTime: true })` |
| T2 | R4 (bridge type drift) | `tsc --noEmit` strict; contract test en T3 |
| T3 | R4 (bridge type drift) | `preload.contract.test.ts` valida shape |
| T4 | R1 (race condition), R2 (electron-store stale) | Mutex singleton en refresh; `clear()` en logout + doble-401 |
| T5 | R1 (race via SWR cache) | `shouldRetryOnError: false` en 401, `onError clear()` |
| T6 | R3 (key collision), R7 (SHA-256) | tests assert hash determinístico (`/^[0-9a-f]{64}$/`) |
| T7 | ninguno | axe-core es determinístico |

### Riesgos descartados (no aplican a F2.2)

- R5 (memoria en electron-store >1MB) — `authStore` solo persiste 3 strings pequeños (~200 bytes).
- R6 (CSP violation con `unsafe-eval`) — `parkosFetch` no usa `eval` ni `new Function`.
- R9 (TS slow compile) — solo se modifican 8 archivos, no se espera regresión >5s.

---

## 10. Out of scope (NO se ejecuta en estos tasks)

- Backend `/health` endpoint — F2.3 (cuello de botella para `apiStatus.get`).
- Login UI completa — F3.1.
- Lockout + countdown UI — F3.2.
- Turno abrir/cerrar — F3.3.
- Auto-update — F2.3.
- Single-instance lock — F2.3.
- Kiosko PIN bcrypt — F2.3.
- Logging/electron-log rotation — F2.3.
- Zod auto-gen desde Pydantic — Fase 3 (forward hook).
- Refresh-token rotation detection — PR7 backend (forward hook).
- 2FA / WebAuthn — futuro, fuera de Fase 2.

---

## CHANGELOG

- (2026-09-15) F2.2 tasks — 7 atomic commits T1..T7 across 3 implementation clusters C1..C3 (C4 post-archive). Layout replica verbatim F2.1 archived tasks para consistencia.